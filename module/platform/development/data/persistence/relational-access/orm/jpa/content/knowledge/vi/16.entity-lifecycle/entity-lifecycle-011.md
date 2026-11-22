# Thiết kế phương thức nghiệp vụ dựa trên trạng thái entity thực tế trong JPA

## 1. Vấn đề: entity đang ở trạng thái nào, và nghiệp vụ được phép làm gì?

Khi làm việc với **Data Persistence / Relational Access / ORM / JPA**, một entity có **hai loại trạng thái khác nhau** mà người lập trình thường nhầm lẫn:

1. **Trạng thái vòng đời JPA** (*persistence lifecycle state*): đối tượng đang là **new/transient**, **managed**, **detached** hay **removed** đối với một persistence context?
2. **Trạng thái nghiệp vụ** (*business state*): đơn hàng đang là **DRAFT**, **PLACED**, **PAID** hay **CANCELLED**, và những hành động nào được phép?

Hai loại trạng thái này độc lập về khái niệm. Một đơn hàng có `status = PLACED` có thể đang **managed** trong transaction hiện tại, **detached** sau khi entity manager đóng, hoặc vừa được truy xuất lại trong một persistence context khác. Ngược lại, một entity đang **managed** không có nghĩa nghiệp vụ cho phép người dùng sửa, xác nhận hay hủy nó.

Ví dụ:

```text
                  Trạng thái vòng đời JPA
        +------------+----------+----------+---------+
        | New        | Managed  | Detached | Removed |
        +------------+----------+----------+---------+
                ^          ^          ^          ^
                |          |          |          |
   Trạng thái   | DRAFT    | DRAFT    | DRAFT    | DRAFT
   nghiệp vụ    | PLACED   | PLACED   | PLACED   | PLACED
                | PAID     | PAID     | PAID     | PAID
                | CANCELLED| CANCELLED| CANCELLED| CANCELLED
```

Sơ đồ chỉ minh họa rằng **hai chiều thông tin khác nhau**, không có nghĩa mọi tổ hợp đều là một thao tác hợp lệ trong ứng dụng.

Giả sử đối tượng đơn hàng có phương thức:

```java
order.place();
```

Một thiết kế tốt phải trả lời đồng thời:

- **Theo nghiệp vụ:** chỉ đơn ở `DRAFT`, đã có dòng hàng hợp lệ mới được đặt.
- **Theo JPA:** nếu muốn trạng thái mới được lưu, object phải được persist trong một transaction phù hợp, hoặc đang là managed entity được provider dirty checking.
- **Theo dữ liệu thực tế:** đơn có bị người khác hủy/đặt trước đó không? Có cơ chế phát hiện state cũ và xung đột cập nhật không?
- **Theo quyền truy cập:** người yêu cầu có được phép đặt đơn hàng này không? Điều này thường do service/application layer kiểm soát trước khi gọi domain method.

Mục tiêu không phải biến entity thành một tập setter tùy ý, mà là xây dựng **phương thức nghiệp vụ thể hiện hành động thật**, kiểm tra invariant và được gọi trong một vòng đời persistence được tổ chức rõ ràng.

## 2. Ôn lại bốn trạng thái vòng đời entity trong JPA

### 2.1. New / transient

Entity **new** là object Java chưa được quản lý trong một persistence context:

```java
PurchaseOrder order = new PurchaseOrder(customerId);
```

Lúc này, object có thể đã có `status = DRAFT` và danh sách dòng hàng, nhưng **JPA chưa theo dõi** các thay đổi của nó. Gọi một domain method trên new entity hoàn toàn có thể hợp lệ:

```java
order.addLine("BOOK-001", 2, new BigDecimal("120000.00"));
```

Tuy nhiên, không có dữ liệu nào được tự động ghi vào database chỉ vì object Java đã thay đổi.

### 2.2. Managed

Sau khi persist hoặc tìm trong một persistence context thích hợp:

```java
em.persist(order);
// Hoặc:
PurchaseOrder order = em.find(PurchaseOrder.class, orderId);
```

entity có thể ở trạng thái **managed**. Provider theo dõi state để đồng bộ thay đổi với database theo cơ chế *dirty checking* khi flush/commit.

```java
PurchaseOrder order = em.find(PurchaseOrder.class, orderId);
order.place();

// Không nhất thiết phải gọi em.merge(order).
// Provider có thể tự phát hiện status thay đổi khi flush/commit.
```

Điều này chỉ đúng khi operation thực hiện trong context/transaction phù hợp. Một managed entity ngoài transaction không có nghĩa bất kỳ thay đổi nào cũng đã được commit.

### 2.3. Detached

Entity **detached** có identity của một entity đã tồn tại nhưng không còn được quản lý trong context đang sử dụng. Ví dụ:

```java
EntityManager em = emf.createEntityManager();
PurchaseOrder order = em.find(PurchaseOrder.class, orderId);
em.close();

// order là object Java còn tồn tại,
// nhưng không còn được entity manager vừa đóng quản lý.
order.cancel("Khách yêu cầu hủy");
```

Gọi `cancel()` có thể đổi `status` trong object Java, nhưng không tự ghi vào database. Đây là tình huống dễ gây lỗi nếu ứng dụng giữ entity trong HTTP session, cache tự tạo hoặc truyền entity ra nhiều tầng rồi giả định mọi sửa đổi đều được JPA lưu.

### 2.4. Removed

Khi một managed entity được đánh dấu xóa:

```java
PurchaseOrder order = em.find(PurchaseOrder.class, orderId);
em.remove(order);
```

Nó bước vào trạng thái **removed** theo vòng đời persistence. SQL `DELETE` thường được thực thi khi đồng bộ thay đổi, tùy transaction và provider.

**Removed không đồng nghĩa với `status = CANCELLED`.** Hủy đơn hàng thường là một **chuyển trạng thái nghiệp vụ**, vẫn cần giữ record để audit hoặc tra cứu. `em.remove()` là yêu cầu xóa dữ liệu thực thể khỏi persistence store; đây là quyết định khác.

### 2.5. Sơ đồ vòng đời cơ bản

```text
 new / transient
       |
       | em.persist(entity)
       v
    managed ----------------------> removed
       |          em.remove(entity)   |
       |                              | flush / commit -> DELETE SQL
       |
       | em.detach(entity) / em.clear()
       | em.close() / context kết thúc
       v
    detached
       |
       | em.merge(detached)
       |   -> trả về managed instance
       |      (không tự đổi detached thành managed)
       v
    managed instance mới hoặc hiện có trong context
```

Sơ đồ là mô hình học tập đơn giản. Thời điểm SQL thực hiện, cách provider tạo identifier, xử lý rollback và lifecycle trong container còn phụ thuộc transaction/context thực tế.

## 3. Đừng dùng `id != null` để suy ra một entity đang managed

Một anti-pattern:

```java
public void saveOrder(PurchaseOrder order) {
    if (order.getId() == null) {
        em.persist(order);
    } else {
        // Giả định có ID nghĩa là đang managed.
        order.place();
    }
}
```

Sai ở chỗ **identity và trạng thái managed là hai khái niệm khác nhau**:

- Entity mới có thể sử dụng **ID do ứng dụng gán** nên `id != null` dù chưa được persist.
- Entity đã persist có thể đã **detached** nên vẫn `id != null` nhưng thay đổi không được theo dõi.
- Entity dùng khóa sinh tự động có thể chưa có ID ngay trước thời điểm provider cấp khóa.
- Một object từ bên ngoài có `id` trùng với row tồn tại không có nghĩa nó được quản lý hoặc phản ánh dữ liệu hiện hành.

Khi cần kiểm tra chính xác một object có đang được **EntityManager cụ thể** quản lý hay không, JPA cung cấp:

```java
boolean managedByThisContext = em.contains(order);
```

`em.contains(order)` kiểm tra quan hệ với **persistence context đang dùng**, không phải một phép hỏi toàn cục “đối tượng này đã từng được lưu chưa”. Nếu trả `false`, object có thể là new, detached hoặc thuộc tình huống khác; chỉ từ kết quả false không phân biệt được toàn bộ vòng đời.

Trong thiết kế nghiệp vụ, thường tốt hơn là **service bảo đảm entity được tìm và thao tác trong transaction**, thay vì cho domain method tự hỏi một `EntityManager` xem mình có managed hay không.

## 4. Phân biệt lifecycle state với business state

Lấy đơn hàng làm ví dụ:

```java
public enum OrderStatus {
    DRAFT,
    PLACED,
    PAID,
    CANCELLED
}
```

Trạng thái nghiệp vụ diễn đạt các quy tắc:

- `DRAFT`: được thêm/sửa dòng hàng, chưa đặt chính thức.
- `PLACED`: đã đặt, không được tự ý thêm dòng, đang chờ thanh toán.
- `PAID`: đã thanh toán; không thể dùng thao tác hủy đơn thông thường để đảo ngược giao dịch tài chính.
- `CANCELLED`: đã hủy; không được thanh toán hoặc thêm dòng.

Chính cùng một entity có thể trải qua các trạng thái JPA:

| Tình huống | Lifecycle JPA | Business status |
|---|---|---|
| `new PurchaseOrder(...)` | New | DRAFT |
| `em.persist(order)` trong transaction | Managed | DRAFT |
| `order.place()` trên managed entity | Managed | PLACED |
| Đóng entity manager sau commit | Detached | PLACED |
| Entity manager mới `find(id)` | Managed trong context mới | PLACED |
| `order.markPaid(...)` và commit | Managed khi thao tác | PAID |
| Đóng context | Detached | PAID |
| `em.remove(order)` | Removed | Có thể vẫn PAID trong object Java, nhưng được đánh dấu xóa |

Không nên thiết kế như sau:

```java
// Sai: xét lifecycle bằng enum nghiệp vụ.
if (order.getStatus() == OrderStatus.DRAFT) {
    // Kết luận order chưa persist.
}
```

Một đơn `DRAFT` hoàn toàn có thể đã lưu trong database. Tương tự, `PLACED` không tự bảo đảm entity hiện đang managed.

**Quy tắc thiết kế:** phương thức domain quyết định **chuyển trạng thái nghiệp vụ**; application service/repository và transaction manager quyết định **cách thao tác đúng vòng đời JPA**.

## 5. Thiết kế phương thức thể hiện hành động, không phơi bày setter trạng thái

### 5.1. Setter công khai tạo đường tắt phá vỡ invariant

Thiết kế yếu:

```java
@Entity
public class PurchaseOrder {
    @Enumerated(EnumType.STRING)
    private OrderStatus status;

    public void setStatus(OrderStatus status) {
        this.status = status;
    }
}
```

Bất kỳ code nào cũng có thể:

```java
order.setStatus(OrderStatus.PAID);
```

ngay cả khi đơn chưa được đặt, không có sản phẩm hoặc chưa thanh toán. Setter không cho biết **vì sao** trạng thái thay đổi và không bảo vệ **điều kiện chuyển trạng thái**.

### 5.2. Phương thức nghiệp vụ có tên rõ ý định

Thiết kế tốt hơn:

```java
order.addLine(...);
order.place();
order.markPaid(paymentReference);
order.cancel(reason);
```

Mỗi phương thức được kỳ vọng:

1. Kiểm tra trạng thái hiện tại có cho phép hành động không.
2. Kiểm tra dữ liệu đầu vào, invariant và điều kiện nghiệp vụ thuộc trách nhiệm entity.
3. Thay đổi những thuộc tính cần thiết trong **một đơn vị nhất quán**.
4. Không tùy tiện kết nối database hoặc gọi hệ thống ngoài từ entity.
5. Không cho code ngoài “đi đường tắt” bằng setter tùy ý.

Bảng chuyển trạng thái:

| Trạng thái hiện tại | Hành động | Trạng thái mới | Điều kiện |
|---|---|---|---|
| DRAFT | `addLine` | DRAFT | SKU hợp lệ, số lượng dương, đơn giá hợp lệ. |
| DRAFT | `place` | PLACED | Có ít nhất một dòng hàng. |
| PLACED | `markPaid` | PAID | Giao dịch thanh toán đã được xác minh ở service. |
| DRAFT | `cancel` | CANCELLED | Có lý do hủy hợp lệ. |
| PLACED | `cancel` | CANCELLED | Nghiệp vụ cho phép hủy trước khi thanh toán. |
| PAID | `markPaid` cùng mã giao dịch | PAID | Có thể được coi là gọi lặp idempotent. |
| PAID | `cancel` | **Không hợp lệ** | Cần quy trình hoàn tiền riêng. |
| CANCELLED | `markPaid` | **Không hợp lệ** | Đơn đã hủy. |
| PLACED / PAID / CANCELLED | `addLine` | **Không hợp lệ** | Đơn không còn ở DRAFT. |

Bảng này là **quy tắc mẫu của hệ thống ví dụ**, không phải JPA tự quy định. Domain khác có thể chọn transition khác, nhưng phải thể hiện chúng nhất quán.

## 6. Entity minh họa: `PurchaseOrder` kiểm soát invariant

### 6.1. Định nghĩa trạng thái

```java
package com.example.orders;

public enum OrderStatus {
    DRAFT,
    PLACED,
    PAID,
    CANCELLED
}
```

Enum thể hiện trạng thái nghiệp vụ, lưu bằng tên với `@Enumerated(EnumType.STRING)` để tránh phụ thuộc thứ tự khai báo enum.

### 6.2. Entity `PurchaseOrder`

```java
package com.example.orders;

import jakarta.persistence.CascadeType;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.FetchType;
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
import java.util.Objects;

@Entity
@Table(name = "purchase_orders")
public class PurchaseOrder {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Version
    @Column(name = "row_version", nullable = false)
    private Long version;

    @Column(name = "customer_id", nullable = false)
    private Long customerId;

    @Enumerated(EnumType.STRING)
    @Column(name = "order_status", nullable = false, length = 20)
    private OrderStatus status;

    @Column(name = "payment_reference", length = 100, unique = true)
    private String paymentReference;

    @Column(name = "cancel_reason", length = 300)
    private String cancelReason;

    @OneToMany(
        mappedBy = "order",
        fetch = FetchType.LAZY,
        cascade = CascadeType.ALL,
        orphanRemoval = true
    )
    private List<PurchaseOrderLine> lines = new ArrayList<>();

    protected PurchaseOrder() {
        // Constructor không tham số dành cho JPA.
    }

    public PurchaseOrder(Long customerId) {
        this.customerId = Objects.requireNonNull(
            customerId, "customerId"
        );
        this.status = OrderStatus.DRAFT;
    }

    public Long getId() {
        return id;
    }

    public Long getVersion() {
        return version;
    }

    public Long getCustomerId() {
        return customerId;
    }

    public OrderStatus getStatus() {
        return status;
    }

    public String getPaymentReference() {
        return paymentReference;
    }

    public List<PurchaseOrderLine> getLines() {
        return Collections.unmodifiableList(lines);
    }

    public void addLine(
            String sku,
            int quantity,
            BigDecimal unitPrice
    ) {
        requireStatus(OrderStatus.DRAFT, "thêm dòng hàng");
        lines.add(new PurchaseOrderLine(
                this, sku, quantity, unitPrice
        ));
    }

    public BigDecimal totalAmount() {
        return lines.stream()
                .map(PurchaseOrderLine::lineTotal)
                .reduce(BigDecimal.ZERO, BigDecimal::add);
    }

    public void place() {
        requireStatus(OrderStatus.DRAFT, "đặt đơn");

        if (lines.isEmpty()) {
            throw new IllegalStateException(
                "Không thể đặt đơn khi chưa có dòng hàng"
            );
        }

        status = OrderStatus.PLACED;
    }

    /**
     * Chỉ gọi sau khi application service đã xác minh
     * giao dịch thanh toán với nguồn đáng tin cậy.
     *
     * @return true nếu lần này chuyển trạng thái sang PAID,
     *         false nếu cùng paymentReference đã ghi nhận.
     */
    public boolean markPaid(String reference) {
        if (reference == null || reference.isBlank()) {
            throw new IllegalArgumentException(
                "Mã giao dịch thanh toán không hợp lệ"
            );
        }

        String normalized = reference.trim();

        // Webhook có thể được gửi lại: không nhân đôi hiệu ứng.
        if (status == OrderStatus.PAID) {
            if (normalized.equals(paymentReference)) {
                return false;
            }
            throw new IllegalStateException(
                "Đơn đã được thanh toán bằng giao dịch khác"
            );
        }

        requireStatus(OrderStatus.PLACED, "ghi nhận thanh toán");

        paymentReference = normalized;
        status = OrderStatus.PAID;
        return true;
    }

    public void cancel(String reason) {
        if (reason == null || reason.isBlank()) {
            throw new IllegalArgumentException(
                "Cần cung cấp lý do hủy đơn"
            );
        }

        if (status != OrderStatus.DRAFT
                && status != OrderStatus.PLACED) {
            throw new IllegalStateException(
                "Không thể hủy đơn ở trạng thái " + status
            );
        }

        cancelReason = reason.trim();
        status = OrderStatus.CANCELLED;
    }

    private void requireStatus(
            OrderStatus expected,
            String action
    ) {
        if (status != expected) {
            throw new IllegalStateException(
                "Không thể " + action + " khi đơn đang ở " + status
            );
        }
    }
}
```

Phân tích thiết kế:

- **Constructor tạo state khởi đầu hợp lệ:** `DRAFT`.
- **Không có `setStatus(...)` công khai:** không thể đổi thành `PAID` chỉ vì một controller gán enum.
- **`place()` kiểm tra invariant:** phải ở `DRAFT` và có dòng hàng.
- **`markPaid(...)` tách khỏi xác minh thanh toán bên ngoài:** entity chỉ ghi nhận một giao dịch đã được service xác nhận.
- **`cancel(...)` có điều kiện theo state:** không hủy thẳng đơn đã thanh toán.
- **`@Version`** giúp provider phát hiện các cập nhật entity dựa trên phiên bản cũ.
- **`@OneToMany`** biểu diễn dòng hàng có vòng đời phụ thuộc đơn trong mô hình mẫu.
- **`getLines()`** trả một view không sửa trực tiếp; các thay đổi được buộc đi qua domain method.

`@Column(unique = true)` trên `payment_reference` chỉ giúp thể hiện unique constraint khi sinh schema; ở database production cần migration bảo đảm constraint thực tế và làm rõ cách UNIQUE xử lý NULL. Nó không thay cho quy tắc idempotency của cổng thanh toán nếu nhiều callback/phiên ứng dụng cùng chạy.

### 6.3. Entity `PurchaseOrderLine`

```java
package com.example.orders;

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
@Table(name = "purchase_order_lines")
public class PurchaseOrderLine {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "order_id", nullable = false)
    private PurchaseOrder order;

    @Column(name = "sku", nullable = false, length = 80)
    private String sku;

    @Column(name = "quantity", nullable = false)
    private Integer quantity;

    @Column(
        name = "unit_price",
        nullable = false,
        precision = 15,
        scale = 2
    )
    private BigDecimal unitPrice;

    protected PurchaseOrderLine() {
        // Constructor không tham số dành cho JPA.
    }

    PurchaseOrderLine(
            PurchaseOrder order,
            String sku,
            int quantity,
            BigDecimal unitPrice
    ) {
        this.order = Objects.requireNonNull(order, "order");

        if (sku == null || sku.isBlank()) {
            throw new IllegalArgumentException("SKU không hợp lệ");
        }
        if (quantity <= 0) {
            throw new IllegalArgumentException(
                "Số lượng phải lớn hơn 0"
            );
        }
        Objects.requireNonNull(unitPrice, "unitPrice");
        if (unitPrice.signum() < 0) {
            throw new IllegalArgumentException(
                "Đơn giá không được âm"
            );
        }

        this.sku = sku.trim();
        this.quantity = quantity;
        this.unitPrice = unitPrice;
    }

    public Long getId() {
        return id;
    }

    public String getSku() {
        return sku;
    }

    public Integer getQuantity() {
        return quantity;
    }

    public BigDecimal getUnitPrice() {
        return unitPrice;
    }

    public BigDecimal lineTotal() {
        return unitPrice.multiply(
            BigDecimal.valueOf(quantity)
        );
    }
}
```

`PurchaseOrderLine` là một entity riêng về mặt JPA vì có `@Id`, nhưng vòng đời nghiệp vụ do `PurchaseOrder` điều phối. Mã tạo dòng là **package-private** để hạn chế code bên ngoài tự sinh dòng hàng không gắn với aggregate.

Trong mô hình ví dụ:

- `PurchaseOrder.lines` là phía inverse của `@OneToMany(mappedBy = "order")`.
- `PurchaseOrderLine.order` là phía sở hữu FK `order_id`.
- `addLine(...)` tạo dòng mới với `order = this`, nhờ vậy hai phía object graph nhất quán ngay khi thêm.
- `cascade = ALL` và `orphanRemoval = true` là quyết định nghiệp vụ cho aggregate này. Không nên tự sao chép cấu hình đó sang quan hệ entity có vòng đời độc lập.
- `lineTotal()` là phép tính từ state của dòng; không truy vấn DB hoặc gọi repository.

**Chú ý:** `List` trong ví dụ không khai báo `@OrderColumn` hoặc `@OrderBy`. Nếu cần lưu **thứ tự dòng ổn định sau khi tải lại từ database**, phải thiết kế thêm số thứ tự/ordering phù hợp. Việc dùng `List` riêng không phải cam kết thứ tự SQL.

## 7. Phương thức nghiệp vụ có thể chạy trên new entity nhưng không tự persist

Entity mới hoàn toàn có thể áp dụng các bước hợp lệ trước khi gọi JPA:

```java
PurchaseOrder order = new PurchaseOrder(123L);

order.addLine(
    "BOOK-001",
    2,
    new BigDecimal("120000.00")
);

order.addLine(
    "PEN-002",
    3,
    new BigDecimal("15000.00")
);

System.out.println(order.totalAmount()); // 285000.00
order.place();
```

Lúc này:

- `order` vẫn có thể là **new/transient**.
- `order.getStatus() == PLACED`.
- Chưa có SQL được phát chỉ vì gọi `place()`.
- Nếu không gọi `em.persist(order)`, state vẫn chỉ sống trong object Java.

Đây là một điểm mạnh của domain method: **nó có thể bảo vệ invariant dù object chưa gắn với persistence context**.

Service sau đó có thể persist aggregate mới:

```java
em.persist(order);
```

Nếu quan hệ `@OneToMany(cascade = ALL)` được cấu hình như ví dụ và provider xử lý đúng trong transaction, các `PurchaseOrderLine` sẽ được persist cùng owner.

**Không bắt buộc mọi hành động nghiệp vụ phải chạy trên entity managed.** Phải phân biệt “method kiểm tra và thay đổi object đúng theo domain” với “state được đồng bộ bền vững xuống database”. Cả hai đều cần thiết, nhưng thuộc những trách nhiệm khác nhau.

## 8. Phương thức nghiệp vụ trên managed entity: dirty checking và transaction

Khi làm việc với entity đã lưu, use case nên nạp entity vào **persistence context của đơn vị công việc hiện tại** rồi gọi hành động domain.

### 8.1. Đặt đơn đã tồn tại

Ví dụ JPA Java SE với transaction cục bộ:

```java
public void placeOrder(
        EntityManagerFactory emf,
        Long orderId
) {
    EntityManager em = emf.createEntityManager();
    EntityTransaction tx = em.getTransaction();

    try {
        tx.begin();

        PurchaseOrder order = em.find(
            PurchaseOrder.class,
            orderId
        );

        if (order == null) {
            throw new IllegalArgumentException(
                "Không tìm thấy đơn hàng"
            );
        }

        order.place();

        // Với managed entity, không cần em.merge(order).
        // Dirty checking phát hiện thay đổi status.
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

Các import cần thiết gồm `jakarta.persistence.EntityManager`, `EntityManagerFactory`, `EntityTransaction`.

Luồng:

```text
Service transaction
       |
       v
em.find(PurchaseOrder.class, id)
       |
       v
Managed PurchaseOrder
       |
       v
order.place()
  - status phải là DRAFT
  - phải có dòng hàng
  - status -> PLACED
       |
       v
tx.commit() / flush
  - provider phát hiện thay đổi
  - kiểm tra version (@Version)
  - UPDATE và commit
```

Domain method **không cần nhận `EntityManager`**. Nó diễn đạt business rule; service cung cấp lifecycle/transaction boundary.

### 8.2. Không biến service thành tập lệnh setter

Một service thiếu domain encapsulation thường viết:

```java
if (order.getStatus() == OrderStatus.DRAFT) {
    if (!order.getLines().isEmpty()) {
        order.setStatus(OrderStatus.PLACED);
    }
}
```

Lối viết này khiến quy tắc nằm rải rác ở service, controller, job nền, listener, dẫn đến mỗi nơi hiểu một kiểu. Nếu cần đặt đơn ở nhiều entry point, một chỗ có thể quên kiểm tra dòng hàng hoặc trạng thái.

Thay bằng:

```java
order.place();
```

Service vẫn chịu trách nhiệm quyền truy cập, giao dịch, truy vấn và tích hợp; entity tập trung invariant áp dụng được với mọi caller.

## 9. Tại sao không nên cho entity tự gọi `persist()` hoặc `merge()`?

Một cách thiết kế phụ thuộc persistence:

```java
// Không nên trộn cơ sở dữ liệu vào domain entity:
public void place(EntityManager em) {
    if (status != OrderStatus.DRAFT) {
        throw new IllegalStateException();
    }
    status = OrderStatus.PLACED;
    em.merge(this);
}
```

Vấn đề:

- Entity bị ràng buộc vào JPA API và cần `EntityManager` khi kiểm tra hành động.
- Domain method không thể dùng tự nhiên trên new entity trong unit test thuần Java.
- `merge()` có semantics khác với “save self”, nhất là khi `this` detached.
- Business rule và transaction boundary bị trộn vào nhau.
- Dễ tạo các transaction rời rạc, thiếu atomicity khi một use case thay nhiều entity.

Thiết kế tách trách nhiệm:

```java
// Trong entity:
public void place() {
    requireStatus(OrderStatus.DRAFT, "đặt đơn");
    if (lines.isEmpty()) {
        throw new IllegalStateException("Đơn hàng trống");
    }
    status = OrderStatus.PLACED;
}

// Trong application service:
public void placeOrder(Long id) {
    PurchaseOrder order = em.find(PurchaseOrder.class, id);
    // Check not found, authorization, concurrency...
    order.place();
}
```

Phương thức nghiệp vụ không cần biết entity có đang managed hay không để **bảo vệ business invariant**. Còn application service cần biết mình đang thao tác lên object thích hợp để **thay đổi được lưu đúng cách**.

## 10. Detached entity: đừng sửa rồi mong database tự cập nhật

Giả sử một controller giữ entity sau request trước:

```java
PurchaseOrder orderFromOldRequest = ...;
// EntityManager cũ đã đóng. Object đang detached.

orderFromOldRequest.place();
```

Trong Java, `status` sẽ đổi sang `PLACED` nếu điều kiện domain hợp lệ. Nhưng thay đổi này **không tự được persistence context hiện tại ghi xuống DB**.

Cách xử lý đáng tin cậy trong phần lớn hệ thống REST:

1. Nhận **ID, hành động và dữ liệu cần thiết** dưới dạng command/DTO.
2. Mở transaction mới.
3. `find` entity theo ID trong context mới.
4. Kiểm tra quyền và phiên bản state từ client.
5. Gọi domain method trên **managed entity hiện hành**.
6. Commit và trả kết quả.

```java
public void placeFromCommand(Long orderId) {
    // Transaction được service quản lý.
    PurchaseOrder managed = em.find(
        PurchaseOrder.class,
        orderId
    );

    if (managed == null) {
        throw new IllegalArgumentException("Đơn không tồn tại");
    }

    managed.place();
}
```

### 10.1. `merge()` không phải “làm object cũ thành managed”

JPA cho phép:

```java
PurchaseOrder managedCopy = em.merge(detachedOrder);
```

`merge()` **sao chép state** của detached entity vào một managed instance phù hợp và trả về instance đó. Đối tượng `detachedOrder` truyền vào vẫn **không tự trở thành managed**.

Sai lầm phổ biến:

```java
em.merge(detachedOrder);
detachedOrder.place(); // Thao tác trên object vẫn detached.
```

Với code cần merge, phải sử dụng **instance được trả về**. Nhưng trong use case web, **không nên merge toàn bộ entity nhận từ client một cách mù quáng** vì snapshot cũ có thể ghi đè các field đã được người khác thay đổi hoặc field mà client không được quyền sửa.

### 10.2. Merge không giải quyết conflict nghiệp vụ

Nếu detached entity có `status = DRAFT` trong khi database đã là `CANCELLED`, gọi `merge()` không tự chọn transition hợp lệ theo domain. Tùy version và provider, thao tác có thể gặp optimistic locking conflict; không thể coi merge là “hợp nhất thông minh”.

Đối với command `placeOrder`, nên đọc entity mới trong transaction và gọi `place()`; nếu database đã là `CANCELLED`, domain method sẽ từ chối ngay theo state hiện tại.

## 11. Entity đang managed có thể vẫn chứa dữ liệu đã cũ

Một giả định sai khác:

> “Entity đã managed thì state chắc chắn mới nhất.”

**Managed** chỉ nói rằng entity được context quản lý. Trong một context tồn tại lâu, object có thể đã được tải trước khi transaction khác cập nhật row.

Ví dụ:

```text
Context A: load order #10 -> status DRAFT, version 3
Context B: load order #10 -> status DRAFT, version 3

Context B: cancel()
           commit -> status CANCELLED, version 4

Context A: vẫn giữ status DRAFT, version 3
           place() trên state cũ
```

Domain method `place()` chỉ thấy state trong **object A**, nên nó có thể cho phép chuyển từ DRAFT sang PLACED theo invariant cục bộ. Nhưng ở database, phiên bản đã thay đổi thành CANCELLED.

Đó là lý do thiết kế cần cả hai tầng:

- **Entity method** kiểm tra quy tắc chuyển trạng thái của object.
- **Transaction + optimistic locking** kiểm tra rằng object chưa bị thay đổi bởi transaction khác trước khi ghi.

Nếu `PurchaseOrder` có `@Version`, khi A flush/commit dựa trên version cũ, provider có thể phát hiện xung đột và từ chối cập nhật.

**Không thể chỉ dựa vào domain guard clause để giải quyết concurrent write.** Tại thời điểm gọi method, state trong bộ nhớ có thể đã cũ; version/lock mới là lớp kiểm soát tính cạnh tranh.

## 12. `@Version` và optimistic locking bảo vệ chuyển trạng thái

### 12.1. Version đi cùng một bản ghi entity

Trong `PurchaseOrder`:

```java
@Version
@Column(name = "row_version", nullable = false)
private Long version;
```

Provider quản lý version theo cơ chế optimistic locking. Ứng dụng không tự set hoặc tăng field này để vượt qua kiểm tra.

Một timeline:

```text
Ban đầu:
  order_id = 10
  order_status = DRAFT
  row_version = 3

Transaction A                     Transaction B
--------------------------        --------------------------
Tải DRAFT, version=3              Tải DRAFT, version=3
                                  cancel("Đổi ý")
                                  UPDATE ... version 3 -> 4
                                  COMMIT
place()
UPDATE dựa trên version=3
Không còn khớp version DB
=> OptimisticLockException / rollback
```

SQL provider có thể tương tự:

```sql
UPDATE purchase_orders
SET order_status = 'PLACED',
    row_version = 4
WHERE id = 10 AND row_version = 3;
```

Nếu không còn row phù hợp vì version đã đổi, provider phát hiện conflict. SQL thực tế, thời điểm tăng version và cách phát hiện phụ thuộc provider; ý nghĩa chính là **tránh ghi đè im lặng**.

### 12.2. Catch conflict ở ranh giới transaction

`OptimisticLockException` có thể xảy ra khi flush hoặc commit, không nhất thiết đúng tại dòng `order.place()`.

```java
try {
    tx.begin();

    PurchaseOrder order =
            em.find(PurchaseOrder.class, orderId);

    order.place();
    em.flush(); // Có thể phát hiện conflict tại đây.

    tx.commit();
} catch (OptimisticLockException ex) {
    if (tx.isActive()) {
        tx.rollback();
    }

    // Báo xung đột. Không retry bằng cách ghi đè im lặng.
    throw new IllegalStateException(
        "Đơn hàng đã được người khác thay đổi",
        ex
    );
}
```

Trong thực tế, framework có thể bọc lỗi optimistic locking vào exception khác tại transaction boundary. Sau conflict nên kết thúc unit of work và dùng **context/transaction mới** nếu cần tải lại state, thay vì cố tiếp tục transaction đã lỗi.

### 12.3. `@Version` có giải quyết mọi thay đổi trên object graph?

Không tự động. Một điểm tinh tế là một **aggregate** có nhiều bảng/collection:

```text
purchase_orders             purchase_order_lines
  id, status, version  <---- order_id, sku, quantity, price
```

Nếu chỉ một child entity `PurchaseOrderLine` bị sửa ở transaction A, không thể mặc định rằng version của **PurchaseOrder root** luôn tăng theo mọi phép thay đổi child trong mọi provider/mapping. Việc cập nhật version parent khi collection thay đổi phụ thuộc quy tắc mapping/provider và loại thay đổi.

Nếu nghiệp vụ cần bảo vệ invariant **toàn aggregate** — ví dụ một transaction đặt đơn trong lúc transaction khác thêm dòng hàng — cần thiết kế **ranh giới khóa** phù hợp:

- Thực hiện các thao tác trên aggregate trong transaction ngắn.
- Cân nhắc lock root entity bằng `OPTIMISTIC_FORCE_INCREMENT` cho thao tác chỉ đổi child nhưng phải cạnh tranh với thay đổi trạng thái parent.
- Dùng `PESSIMISTIC_WRITE` khi cần serialize thao tác có cạnh tranh cao trong transaction ngắn.
- Có version riêng ở child nếu child có cập nhật độc lập.
- Kiểm tra ràng buộc và kết quả nghiệp vụ tại thời điểm transaction có thể commit.

Ví dụ application service có thể chủ động tăng version root khi một use case thay child nhưng cần bảo vệ transition đồng thời:

```java
PurchaseOrder order = em.find(
    PurchaseOrder.class,
    orderId
);

em.lock(order, LockModeType.OPTIMISTIC_FORCE_INCREMENT);

order.addLine(
    "BOOK-003",
    1,
    new BigDecimal("90000.00")
);
```

`OPTIMISTIC_FORCE_INCREMENT` cần được dùng theo quy tắc lock/version của JPA và provider trong transaction phù hợp. Không phải mọi use case cần force increment; đây là quyết định concurrency ở application layer, không phải bản thân `addLine()` phải gọi `em.lock(...)`.

## 13. Form web dài: trạng thái thực tế nằm ở database, không phải form cũ

Một form đặt đơn có thể được mở từ lúc 09:00, đến 09:15 người dùng mới nhấn “Đặt đơn”. Trong thời gian đó, một người khác đã hủy đơn hoặc thay đổi nội dung.

### 13.1. Đưa version ra DTO

Khi tải màn hình, service trả:

```json
{
  "orderId": 10,
  "status": "DRAFT",
  "version": 3,
  "totalAmount": "285000.00"
}
```

Client gửi hành động:

```json
{
  "orderId": 10,
  "expectedVersion": 3
}
```

`status` từ browser có thể hỗ trợ UI nhưng không được coi là nguồn thật của chuyển trạng thái. Service phải tìm entity và dựa trên state đang được quản lý trong transaction.

### 13.2. Service kiểm tra version từ client, rồi dùng domain method

```java
public void placeOrder(
        EntityManagerFactory emf,
        Long orderId,
        Long expectedVersion
) {
    EntityManager em = emf.createEntityManager();
    EntityTransaction tx = em.getTransaction();

    try {
        tx.begin();

        PurchaseOrder order = em.find(
            PurchaseOrder.class,
            orderId
        );

        if (order == null) {
            throw new IllegalArgumentException(
                "Không tìm thấy đơn hàng"
            );
        }

        if (!Objects.equals(
                order.getVersion(),
                expectedVersion
        )) {
            throw new IllegalStateException(
                "Đơn đã thay đổi từ khi người dùng mở form"
            );
        }

        order.place();

        // @Version vẫn bảo vệ race condition xảy ra
        // sau bước kiểm tra thủ công.
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
}
```

Imports gồm `jakarta.persistence.*` và `java.util.Objects`.

**Hai kiểm tra có vai trò khác nhau:**

1. So sánh `expectedVersion` với version vừa load giúp nhận ra **form đã cũ** trước khi sửa.
2. `@Version` của provider kiểm tra xung đột khi ghi, kể cả có transaction khác update **sau lúc service vừa đọc**.

Nếu API HTTP sử dụng ETag và `If-Match`, một conflict do precondition không khớp có thể được báo bằng **412 Precondition Failed**. Với application-level conflict, **409 Conflict** là một lựa chọn thường gặp. Không tự retry vô hạn rồi ghi lại payload cũ, vì đó có thể là lost update bị che giấu.

### 13.3. Không giữ transaction DB mở trong lúc user nhập form

Luồng phù hợp thường là:

```text
GET /orders/10
  -> transaction đọc ngắn
  -> DTO {id, status, version, lines}
  -> kết thúc context/transaction

User chỉnh sửa hoặc cân nhắc trong browser
  -> không giữ DB transaction

POST /orders/10/place
  -> transaction ghi ngắn
  -> load entity mới, kiểm tra quyền/version
  -> order.place()
  -> flush/commit
  -> trả kết quả hoặc conflict
```

Một **extended persistence context** có thể hữu ích trong một số workflow stateful được quản lý chặt, nhưng đối với REST/stateless service, lưu DTO + version thường đơn giản và an toàn hơn.

## 14. Thiết kế theo aggregate: ai được phép thay đổi entity con?

`PurchaseOrder` chứa các `PurchaseOrderLine`. Nếu service khác có repository độc lập cho line và tự ý sửa:

```java
PurchaseOrderLine line = em.find(
    PurchaseOrderLine.class,
    lineId
);

// Một code path riêng sửa quantity/price không qua PurchaseOrder.
```

nó có thể bỏ qua quy tắc “chỉ được sửa dòng khi đơn ở DRAFT”. Nếu line có setter công khai, nhiều entry point có thể phá invariant dù `PurchaseOrder.place()` được viết rất cẩn thận.

### 14.1. Tập trung hành động ở aggregate root

Một cách tổ chức là để `PurchaseOrder` cung cấp API:

```java
order.addLine(sku, quantity, unitPrice);
order.place();
order.cancel(reason);
```

Các thay đổi của line đi qua root hoặc một domain service có kiểm soát. Khi cần sửa số lượng, có thể thêm phương thức:

```java
public void changeLineQuantity(
        Long lineId,
        int newQuantity
) {
    requireStatus(OrderStatus.DRAFT, "sửa số lượng");

    PurchaseOrderLine line = lines.stream()
            .filter(it -> Objects.equals(it.getId(), lineId))
            .findFirst()
            .orElseThrow(() -> new IllegalArgumentException(
                "Không tìm thấy dòng hàng"
            ));

    line.changeQuantity(newQuantity);
}
```

Để áp dụng ví dụ này, `PurchaseOrderLine` cần thêm method **package-private**:

```java
void changeQuantity(int newQuantity) {
    if (newQuantity <= 0) {
        throw new IllegalArgumentException(
            "Số lượng phải lớn hơn 0"
        );
    }
    this.quantity = newQuantity;
}
```

Phương thức trên nhằm minh họa nguyên tắc: **root kiểm tra trạng thái của đơn trước khi cho phép sửa child**. Nếu có nhiều lối đi khác để sửa line mà không qua root, invariant sẽ không còn được bảo đảm.

### 14.2. Ranh giới aggregate không đồng nghĩa ranh giới fetch tất cả

Một aggregate root điều phối invariant không có nghĩa mọi truy vấn phải fetch mọi child trong mọi use case. Service có thể dùng DTO projection khi chỉ cần danh sách/summary.

Nhưng khi hành động domain cần kiểm tra tất cả dòng hàng, chẳng hạn `place()` cần bảo đảm có ít nhất một line, service phải tải hoặc bảo đảm collection cần thiết được truy cập trong persistence context còn hoạt động.

**Lazy loading là vấn đề dữ liệu cần thiết cho method**, không phải lý do bỏ kiểm tra invariant.

## 15. Lazy loading và phương thức nghiệp vụ

Trong `PurchaseOrder`:

```java
@OneToMany(mappedBy = "order", fetch = FetchType.LAZY)
private List<PurchaseOrderLine> lines;
```

Nếu `place()` gọi:

```java
if (lines.isEmpty()) {
    throw new IllegalStateException("Đơn hàng trống");
}
```

và `lines` là một lazy collection chưa khởi tạo, provider có thể cần truy vấn database để biết collection có phần tử hay không.

Trong transaction service:

```java
PurchaseOrder order = em.find(PurchaseOrder.class, orderId);
order.place(); // Có context đang hoạt động để đọc lines.
```

Thông thường có thể phù hợp. Nhưng nếu `order` đã detached và collection chưa tải:

```java
em.close();
order.place(); // Có thể lỗi khi truy cập lazy collection.
```

Tùy provider, lỗi như `LazyInitializationException` có thể xuất hiện. Không nên vì thế mà:

- Tự động đổi tất cả collections sang `EAGER`.
- Bỏ kiểm tra `lines.isEmpty()`.
- Mở một entity manager mới bên trong domain entity.
- Bắt exception lazy loading rồi coi đơn hàng hợp lệ.

Giải pháp là **application service chuẩn bị đủ state để domain method chạy**:

- Thực thi command trong transaction/persistence context thích hợp.
- Dùng `JOIN FETCH` hoặc entity graph theo nhu cầu.
- Xác định rõ phần state phải được tải cho hành động.
- Giữ các phép kiểm tra thuần từ state của aggregate đã có.

### 15.1. Truy vấn một đơn và các dòng cần thiết

```java
PurchaseOrder order = em.createQuery(
    """
    SELECT DISTINCT o
    FROM PurchaseOrder o
    LEFT JOIN FETCH o.lines
    WHERE o.id = :id
    """,
    PurchaseOrder.class
)
.setParameter("id", orderId)
.getResultStream()
.findFirst()
.orElseThrow(() -> new IllegalArgumentException(
    "Không tìm thấy đơn hàng"
));

order.place();
```

Dùng `LEFT JOIN FETCH` vì order ở DRAFT có thể chưa có dòng, và domain method cần trả lỗi nghiệp vụ “đơn hàng trống”, thay vì bị loại khỏi kết quả query do `INNER JOIN`.

Nếu một aggregate có nhiều collection lớn, không nên fetch join tất cả một cách mù quáng vì có thể nhân số hàng SQL và gây tốn bộ nhớ. Hãy chọn đúng state cần thiết cho action.

## 16. Không dùng lifecycle callback để thay thế phương thức nghiệp vụ

JPA cung cấp những callback như:

- `@PrePersist`, `@PostPersist`.
- `@PreUpdate`, `@PostUpdate`.
- `@PreRemove`, `@PostRemove`.
- `@PostLoad`.

Chúng hữu ích cho một số hành vi gắn với **sự kiện persistence**, nhưng **không thay thế domain action**.

### 16.1. Anti-pattern: đặt đơn trong `@PrePersist`

```java
@PrePersist
public void beforeInsert() {
    status = OrderStatus.PLACED;
}
```

Cách này biến mọi đối tượng mới được persist thành đơn đã đặt, kể cả use case chỉ muốn tạo bản nháp. Nó trộn thao tác nghiệp vụ “place” với sự kiện kỹ thuật “INSERT”.

Một phản ví dụ khác:

```java
@PreUpdate
public void onUpdate() {
    if (status == OrderStatus.DRAFT) {
        status = OrderStatus.PLACED;
    }
}
```

Bất kỳ update nào — kể cả sửa mô tả hoặc dữ liệu kỹ thuật — có thể kích hoạt chuyển trạng thái ngoài ý muốn. Ngoài ra, không nên dựa vào callback để xử lý những trường hợp bulk JPQL UPDATE hay SQL trực tiếp, vốn không áp dụng callback entity thông thường theo cách update managed entity.

### 16.2. Callback hợp với việc kỹ thuật nào?

Ví dụ điển hình là một timestamp cho audit:

```java
@PrePersist
void onCreate() {
    if (createdAt == null) {
        createdAt = Instant.now();
    }
}
```

Hoặc kiểm tra một invariant cục bộ đơn giản tại thời điểm persistence. Tuy nhiên, nếu invariant là “chỉ một đơn đã đặt mới được ghi nhận thanh toán”, nên có domain method `markPaid()` và các guard rõ ràng, thay vì che giấu transition bên trong callback.

Các callback có quy tắc riêng về thao tác được phép trên entity context. Không nên đặt trong callback một quy trình phức tạp gọi repository, gửi email, truy cập HTTP hoặc quản lý transaction.

### 16.3. Có cần kiểm tra trong cả entity và database?

Nên kết hợp các lớp:

- **Domain method**: bảo vệ hành vi/invariant của entity trước khi thay đổi.
- **Bean Validation** (khi có): kiểm tra input, property constraints hoặc custom validation.
- **Database constraints**: bảo vệ `NOT NULL`, `UNIQUE`, `FOREIGN KEY`, `CHECK` khi dữ liệu được ghi từ nhiều nguồn.
- **Optimistic/pessimistic locking**: bảo vệ cạnh tranh cập nhật.

Không lớp nào hoàn toàn thay thế các lớp còn lại.

## 17. Vì sao `@Version` quan trọng nhưng vẫn chưa đủ cho một số invariant?

Giả sử có hai aggregate `Account`, `PurchaseOrder`, và một yêu cầu: khách hàng không được đặt đơn vượt hạn mức tín dụng. `place()` chỉ có thể kiểm tra trạng thái và dòng hàng của bản thân order; hạn mức tín dụng thuộc account/customer và có thể bị nhiều transaction thay đổi.

Nếu chỉ kiểm tra:

```java
if (customer.getAvailableCredit().compareTo(order.totalAmount()) >= 0) {
    order.place();
}
```

hai transaction có thể cùng nhìn số dư cho phép và đặt hai đơn vượt tổng hạn mức — dù mỗi order có `@Version` riêng. Đây là **invariant trải qua nhiều aggregate/row**, không giải quyết chỉ bằng version của từng order.

Cần thiết kế use case tại application/domain service với:

- Transaction boundary bao trùm những thay đổi cần atomic.
- Version/lock cho dữ liệu dùng quyết định hạn mức.
- DB constraints khi biểu diễn được.
- Cơ chế đặt chỗ hạn mức, ledger hoặc reservation phù hợp nghiệp vụ.
- Xử lý conflict/retry có điều kiện.

**Entity method chỉ nên cam kết những điều kiện nó có đủ dữ liệu và quyền sở hữu để bảo vệ.** Một method ở `PurchaseOrder` không nên lén gọi SQL để kiểm tra hạn mức mà không kiểm soát concurrency.

## 18. Quy trình thanh toán: state transition và side effect bên ngoài

`markPaid(reference)` trong ví dụ chỉ là **ghi nhận thanh toán đã được xác minh**. Nó không thực hiện HTTP request đến cổng thanh toán.

Một luồng đúng về mặt tổ chức:

```text
Payment provider gửi webhook
       |
       v
HTTP controller
  - xác thực chữ ký, kiểm tra request
       |
       v
Application service
  - kiểm tra giao dịch/mã order, quyền, idempotency
  - mở transaction
  - load PurchaseOrder managed
  - order.markPaid(reference)
  - lưu dấu vết/outbox nếu cần
  - commit
       |
       v
Xử lý các side effect sau commit qua cơ chế đáng tin cậy
```

### 18.1. Không gửi email bên trong `markPaid()`

Một entity method kiểu:

```java
public void markPaid(String reference) {
    status = OrderStatus.PAID;
    emailClient.sendReceipt(...);
}
```

có thể gửi email trước khi transaction commit. Nếu commit thất bại do optimistic locking hoặc DB error, khách hàng đã nhận email “Thanh toán thành công” dù trạng thái không được lưu.

Domain method nên đổi state và kiểm tra invariant. Nếu phải phát sự kiện hay gửi email, application layer nên phối hợp với commit, ví dụ **transactional outbox** hoặc một cơ chế đáng tin cậy sau commit phù hợp. Không coi việc gọi email ngay trong transaction là atomic cùng database.

### 18.2. Idempotency không chỉ là kiểm tra `status == PAID`

Webhook thường có thể được gửi lại nhiều lần. Trong ví dụ:

```java
if (status == OrderStatus.PAID
        && normalized.equals(paymentReference)) {
    return false;
}
```

giúp một entity đã ở `PAID` phản hồi an toàn với cùng mã thanh toán. Nhưng để idempotency đầy đủ trong môi trường nhiều transaction:

- Xác định mã giao dịch duy nhất tại cổng thanh toán.
- Cân nhắc unique constraint cho `paymentReference` hoặc bảng giao dịch thanh toán riêng.
- Kiểm soát cạnh tranh bằng version/lock.
- Tách xử lý external side effects khỏi update state; dùng outbox khi cần.
- Định nghĩa hành vi nếu cùng mã giao dịch xuất hiện ở **hai đơn khác nhau**.

Mục tiêu là giữ một business transition có ý nghĩa đúng **một lần**, không chỉ tránh exception trong một object Java.

## 19. Removed state khác với cancel/soft delete

Một đơn `CANCELLED` có thể vẫn phải tồn tại trong database để kiểm toán, đối soát, chăm sóc khách hàng và báo cáo.

```java
order.cancel("Khách đổi địa chỉ");
```

đây là một **domain transition**:

```text
DRAFT/PLACED -> CANCELLED
Database row vẫn tồn tại
```

Trong khi:

```java
em.remove(order);
```

là một thao tác **persistence removal**:

```text
managed entity -> removed
Khi đồng bộ transaction, provider yêu cầu DELETE row
```

Không dùng `em.remove` để “hủy đơn” nếu nghiệp vụ phải giữ lịch sử. Nếu domain cần **soft delete**, có thể có thuộc tính riêng như `deletedAt` hoặc trạng thái vô hiệu hóa, với quy tắc query, unique constraint và audit thích hợp.

Một entity bị đánh dấu removed vẫn là một object Java; gọi một method làm đổi `status` trên object đó không biến nó thành một update bình thường. Application service phải quyết định rõ use case đang **chuyển trạng thái** hay **xóa entity**.

### 19.1. Không ép một business state chỉ vì JPA lifecycle

Không nên suy luận:

- `new` → bắt buộc DRAFT trong mọi domain.
- `managed` → bắt buộc ACTIVE.
- `detached` → bắt buộc ARCHIVED.
- `removed` → bắt buộc CANCELLED.

Đó là hai trục hoàn toàn khác nhau. Một domain có thể cần khởi tạo entity mới ngay với trạng thái `PLACED`, hoặc một entity đã lưu vẫn ở `DRAFT` trong nhiều tuần. Thiết kế phụ thuộc quy tắc nghiệp vụ, không phụ thuộc thuật ngữ lifecycle.

## 20. State machine trong entity: guard clause, transition table và exception

Với số lượng trạng thái nhỏ, guard clause trong domain method thường đủ rõ:

```java
public void place() {
    if (status != OrderStatus.DRAFT) {
        throw new IllegalStateException(
            "Chỉ có thể đặt đơn ở trạng thái DRAFT"
        );
    }
    if (lines.isEmpty()) {
        throw new IllegalStateException(
            "Đơn cần ít nhất một dòng hàng"
        );
    }
    status = OrderStatus.PLACED;
}
```

Khi số lượng trạng thái tăng, có thể ghi lại transition table:

| Hành động | DRAFT | PLACED | PAID | CANCELLED |
|---|---|---|---|---|
| Add line | Cho phép | Chặn | Chặn | Chặn |
| Place | Sang PLACED | Chặn | Chặn | Chặn |
| Mark paid | Chặn | Sang PAID | Idempotent nếu cùng reference | Chặn |
| Cancel | Sang CANCELLED | Sang CANCELLED | Chặn / refund workflow | Chặn |

### 20.1. Exception nói đúng loại lỗi

Cần phân biệt:

- **Input invalid:** `IllegalArgumentException` hoặc một exception validation phù hợp.
- **Transition không hợp lệ:** `IllegalStateException` hoặc domain exception có ý nghĩa.
- **Không tìm thấy entity:** application service trả lỗi not-found phù hợp.
- **Không đủ quyền:** policy/service báo forbidden, không nhờ domain entity tự hỏi HTTP user.
- **Concurrency conflict:** xử lý `OptimisticLockException` / version mismatch ở boundary transaction.
- **Database constraint:** nguyên nhân và mapping tới response phải được xử lý ở persistence/application layer.

Có thể tạo domain exception riêng:

```java
public class InvalidOrderTransitionException
        extends RuntimeException {

    public InvalidOrderTransitionException(String message) {
        super(message);
    }
}
```

Domain exception giúp phân loại lỗi rõ hơn, nhưng không tự biến exception thành HTTP response. Controller/application layer chịu trách nhiệm chuyển sang status/code/API contract tương ứng.

### 20.2. Trạng thái trong domain có thể khác state giao diện

Giao diện có thể hiển thị nhãn `"Chờ thanh toán"` cho `PLACED`, nhưng không nên để UI tự quyết định enum mới rồi gửi `status = "PAID"` để server set thẳng.

API nên diễn đạt **command**:

```text
POST /orders/{id}/place
POST /orders/{id}/cancel
POST /payment-webhooks
```

Command dễ gắn đúng quyền, version check, audit và business transition hơn endpoint “PATCH status sang giá trị bất kỳ”.

## 21. Tương tác với transaction-scoped và extended persistence context

### 21.1. Transaction-scoped context

Một use case stateless thường:

```text
begin transaction
 -> load managed order
 -> check permissions
 -> call domain method
 -> flush/commit
 -> context kết thúc; entity có thể detached
```

Đây là mô hình đơn giản và phổ biến cho REST/service thông thường.

### 21.2. Extended persistence context

Với một **extended persistence context**, entity có thể được giữ managed qua nhiều transaction và nhiều bước hội thoại. Điều đó hỗ trợ một số wizard phức tạp nhưng tạo nguy cơ:

- Managed object đã cũ so với database.
- Một domain method kiểm tra state trong bộ nhớ cũ.
- Pending changes tích lũy qua nhiều bước.
- Flush xảy ra lúc context tham gia transaction không như người dùng tưởng.
- Giữ nhiều entity/collection gây chiếm bộ nhớ.

`@Version` giúp phát hiện nhiều xung đột lúc commit, nhưng không làm cho việc đọc trong context dài luôn mới. Khi phải đọc lại state từ DB, có thể cân nhắc `em.refresh(managedEntity)` nếu chấp nhận bỏ pending local changes, hoặc dùng transaction/context mới.

Không giữ một transaction DB xuyên suốt thời gian người dùng nhập form nhiều phút. Với stateless application, DTO + version và transaction ngắn thường đơn giản hơn.

### 21.3. `EntityManager` không thread-safe

Không giữ một `EntityManager` trong singleton để tất cả request cùng thao tác lên managed entities. Một `EntityManagerFactory` có thể được quản lý dùng chung, còn `EntityManager` cần scope/lifecycle phù hợp.

Trạng thái một entity đang managed là thông tin **gắn với context cụ thể**, không phải “managed bởi cả ứng dụng”.

## 22. Các thao tác JPA thường bị dùng nhầm khi thiết kế domain method

| Thao tác | Ý nghĩa kỹ thuật | Không nên hiểu là |
|---|---|---|
| `persist(entity)` | Yêu cầu đưa new entity vào quản lý và lưu. | “Xác nhận đơn” theo business. |
| `find(Class, id)` | Tìm entity theo PK trong context. | Luôn trả snapshot mới nhất bất kể cache/isolation. |
| `merge(detached)` | Sao chép detached state vào managed instance, trả về managed instance. | Tự hợp nhất thông minh và giải quyết stale data. |
| `remove(entity)` | Đánh dấu entity để xóa khỏi persistence store. | Chuyển trạng thái business sang CANCELLED. |
| `flush()` | Đồng bộ pending changes xuống DB trong transaction. | Commit hoặc làm mới entity. |
| `refresh(entity)` | Làm mới state của managed entity từ persistence store. | Bảo đảm conflict-free hoặc giữ lại mọi pending local change. |
| `clear()` | Detach mọi managed entity trong context. | Xóa tất cả bản ghi DB. |
| `detach(entity)` | Đưa entity ra khỏi context. | Đổi entity sang business state ARCHIVED. |
| `contains(entity)` | Kiểm tra entity có thuộc context đó hay không. | Kiểm tra chắc chắn row có tồn tại trong DB. |
| `lock(entity, ...)` | Áp dụng cơ chế khóa/version tùy lock mode. | Thay thế điều kiện nghiệp vụ trong method. |
| `@Version` | Bảo vệ optimistic locking của entity. | Tự giải quyết merge hoặc kiểm tra mọi invariant đa bảng. |

Bảng này đặc biệt hữu ích khi codebase có repository tên `save()`. Từ “save” ở tầng repository có thể bao hàm logic persist hoặc merge, **không có nghĩa domain action đã hợp lệ**. Cần gọi method nghiệp vụ ở nơi đúng trước khi persistence operation được thực thi.

## 23. Kiểm thử phương thức nghiệp vụ theo state thực tế

### 23.1. Unit test thuần Java cho business transitions

Vì entity method không phụ thuộc `EntityManager`, có thể kiểm tra transition mà không cần database:

```java
@Test
void cannotPlaceEmptyOrder() {
    PurchaseOrder order = new PurchaseOrder(123L);

    assertThrows(
        IllegalStateException.class,
        order::place
    );
}

@Test
void placingDraftOrderWithLinesSucceeds() {
    PurchaseOrder order = new PurchaseOrder(123L);
    order.addLine(
        "BOOK-001", 2, new BigDecimal("120000.00")
    );

    order.place();

    assertEquals(OrderStatus.PLACED, order.getStatus());
}

@Test
void cannotAddLineAfterPlaced() {
    PurchaseOrder order = new PurchaseOrder(123L);
    order.addLine(
        "BOOK-001", 1, new BigDecimal("50000.00")
    );
    order.place();

    assertThrows(
        IllegalStateException.class,
        () -> order.addLine(
            "PEN-002", 1, new BigDecimal("10000.00")
        )
    );
}
```

Ví dụ dùng JUnit 5: `org.junit.jupiter.api.Test`, `Assertions.assertThrows`, `Assertions.assertEquals`; cùng imports `java.math.BigDecimal`.

Các kiểm thử này xác nhận **quy tắc nghiệp vụ**. Chúng không xác nhận mapping JPA hoặc SQL.

### 23.2. Test idempotency của markPaid

```java
@Test
void samePaymentCallbackIsIdempotent() {
    PurchaseOrder order = new PurchaseOrder(123L);
    order.addLine(
        "BOOK-001", 1, new BigDecimal("50000.00")
    );
    order.place();

    assertTrue(order.markPaid("TXN-123"));
    assertFalse(order.markPaid("TXN-123"));

    assertEquals(OrderStatus.PAID, order.getStatus());

    assertThrows(
        IllegalStateException.class,
        () -> order.markPaid("TXN-DIFFERENT")
    );
}
```

Đây là unit test cho **một object**, chưa kiểm tra cạnh tranh giữa hai transaction hoặc độ duy nhất toàn database. Các trường hợp đó cần integration/concurrency tests.

### 23.3. Integration test cho managed state và dirty checking

Một test kết hợp JPA:

1. Tạo đơn mới với dòng hàng, persist và commit.
2. Mở `EntityManager` mới, `find` đơn theo ID.
3. Gọi `order.place()` trong transaction.
4. Commit và đóng context.
5. Mở `EntityManager` khác, đọc lại và xác nhận `status = PLACED`.

Test này xác nhận: mapping phù hợp, lifecycle managed hoạt động, provider dirty checking lưu thay đổi.

### 23.4. Integration test cho detached state

Một test khác:

1. Load order vào `EntityManager A`.
2. Đóng A.
3. Gọi `order.place()` trên detached object.
4. Mở `EntityManager B`, đọc lại order từ DB.
5. Xác nhận database **chưa đổi** nếu không có persistence operation thích hợp.

Test giúp ngăn giả định “mọi object có ID đều được tự lưu”.

### 23.5. Test xung đột optimistic locking

Dùng hai entity manager độc lập:

```text
EM A: begin, find Order (version 5)
EM B: begin, find Order (version 5)

EM B: cancel() -> commit, version 6

EM A: place() -> flush/commit
      -> kỳ vọng optimistic lock conflict
```

Cách sắp xếp transaction và isolation cần phù hợp database thử nghiệm; test nên kiểm tra **không bị lost update**, không dựa vào số lệnh SQL cụ thể.

Nếu invariant trải qua child collection, thêm test hai transaction cùng sửa order lines/đặt đơn để kiểm tra strategy lock root thực tế.

## 24. Bản thiết kế tổng thể cho use case an toàn

Một service “đặt đơn” có thể thực hiện theo sơ đồ:

```text
             Request: PlaceOrder(orderId, expectedVersion)
                                |
                                v
                     Application service
                                |
                  +-------------+-------------+
                  |                           |
                  v                           v
           Authorization                Begin transaction
           ai được đặt đơn?                    |
                                               v
                                   Find managed PurchaseOrder
                                               |
                                               v
                                    Kiểm tra tồn tại/version
                                               |
                                               v
                                     order.place()
                                  - DRAFT?
                                  - Có dòng hàng?
                                  - đổi status sang PLACED
                                               |
                                               v
                                     Flush / Commit
                                  - optimistic locking
                                  - database constraints
                                               |
                          +--------------------+-------------------+
                          |                                        |
                          v                                        v
                       Thành công                              Conflict/lỗi
                          |                                        |
                          v                                        v
                  Trả DTO trạng thái mới               Rollback và trả lỗi phù hợp
```

Service không thay thế domain method; entity không thay thế service. Sự phân chia này cho phép:

- Unit test domain rule không phụ thuộc DB.
- Integration test persistence lifecycle riêng.
- Mỗi use case kiểm soát transaction và quyền rõ ràng.
- Thay đổi business transition ở một chỗ.
- Xử lý stale state/optimistic locking đúng tại ranh giới commit.
- Có một nơi xử lý retry, audit, outbox và external integration theo chính sách.

## 25. Những lỗi thiết kế thường gặp

| Vấn đề | Nguyên nhân | Hướng khắc phục |
|---|---|---|
| Có `id != null` nhưng sửa entity không lưu | Entity đã detached hoặc ID tự gán, không managed. | Service nạp managed entity trong transaction, hoặc xử lý persist/merge đúng semantics. |
| `setStatus(PAID)` được gọi trước khi thanh toán | Setter công khai không có invariant. | Cung cấp `markPaid(reference)` và chỉ gọi sau xác minh ở service. |
| Controller gọi `em.remove(order)` để “hủy đơn” | Nhầm persistence removed với business CANCELLED. | Gọi `order.cancel(reason)` nếu nghiệp vụ cần giữ lịch sử. |
| Đặt đơn trống vẫn thành công | Business rule chỉ nằm trong một controller, các entry point khác bỏ qua. | Đưa kiểm tra vào `PurchaseOrder.place()`. |
| Gọi `order.place()` trên detached object nhưng DB không đổi | Không còn context theo dõi entity. | Mở transaction, `find` managed order, áp dụng command. |
| Dùng `merge()` rồi sửa tiếp object gốc | `merge` trả instance managed khác; object gốc vẫn detached. | Dùng kết quả `em.merge(...)` khi thực sự cần merge. |
| Merge payload cũ làm mất cập nhật | Sao chép toàn bộ detached state không kiểm tra version/field. | Đọc entity mới, check version, áp dụng command có chủ đích. |
| Hai transaction cùng đặt/hủy đơn gây trạng thái sai | Chỉ kiểm tra state Java, thiếu concurrency control. | Dùng `@Version` hoặc lock đúng ranh giới aggregate. |
| Có `@Version` trên root nhưng chỉ sửa child vẫn xung đột không được phát hiện | Root version không nhất thiết tăng với mọi thay đổi child. | Thiết kế lock/version trên phạm vi invariant, cân nhắc `OPTIMISTIC_FORCE_INCREMENT`. |
| Domain method ném lazy-loading exception sau request | Detached entity, collection chưa tải. | Thực thi method trong context còn sống và fetch state cần thiết. |
| Callback `@PreUpdate` tự đổi status bất ngờ | Đưa business transition vào persistence callback. | Dùng domain action; callback chỉ cho logic kỹ thuật phù hợp. |
| Entity gọi HTTP/payment gateway trong transaction | Tác dụng phụ ngoài DB không atomic cùng commit. | Service xác minh trước, cập nhật state trong transaction; outbox cho side effect. |
| Hủy đơn PAID chỉ bằng đổi enum | Thiếu quy trình hoàn tiền/đối soát. | Tách refund workflow có invariant và external coordination. |
| Client gửi `status = PAID` và server tin ngay | Tin state từ request không xác minh. | API nhận command, authorize, load entity và gọi domain method. |
| `em.flush()` được coi là lưu thành công cuối cùng | Flush chưa phải commit. | Commit transaction và xử lý rollback/errors ở boundary. |
| `em.refresh(order)` gọi bừa để “tránh stale” | Có thể mất local pending changes. | Freshness có chủ đích, version check và context mới khi cần. |
| Domain method trực tiếp truy cập repository | Trộn persistence với invariant, khó test và khó kiểm soát transaction. | Domain giữ logic trên state của mình; service phối hợp repository. |
| Đơn bị update bằng bulk SQL bypass invariant | Bulk update không gọi domain methods/callback như thao tác managed entity. | Hạn chế bulk state transition hoặc triển khai đúng predicate/version/constraints và audit. |
| EntityManager dùng chung nhiều thread | Context không thread-safe và giữ state lâu. | Quản lý EM theo scope/transaction phù hợp, chia sẻ EMF thay vì EM. |

## 26. Khi nào dùng domain method, domain service hoặc application service?

Không phải mọi rule đều nên bị nhét vào một entity.

### 26.1. Domain method trên entity

Dùng khi rule chủ yếu phụ thuộc vào **state của entity/aggregate mà entity sở hữu**:

- Đơn đang DRAFT mới được thêm dòng.
- Không đặt đơn nếu danh sách dòng trống.
- Đơn PAID không được hủy trực tiếp.
- Chỉ ghi nhận một payment reference đã được xác minh.

Các rule này đủ dữ liệu để đánh giá trong entity nếu service đã chuẩn bị state cần thiết.

### 26.2. Domain service

Dùng khi một quyết định có **ngữ nghĩa miền nghiệp vụ** nhưng không thuộc tự nhiên vào một entity duy nhất, ví dụ:

- Tính hạn mức sử dụng từ nhiều tài khoản/đơn.
- Chính sách phân bổ tồn kho giữa nhiều kho.
- Quy tắc đối soát nhiều sổ cái.

Domain service có thể nhận các đối tượng, policy/result đã được chuẩn bị và trả quyết định; nếu cần truy cập persistence, nên xác định rõ interface/transaction boundary thay vì để entity tự gọi DB trong getter hoặc callback.

### 26.3. Application service

Dùng để điều phối use case:

- Nhận command từ HTTP/message.
- Xác thực và phân quyền.
- Mở transaction.
- Tìm managed entity và fetch dữ liệu cần thiết.
- Kiểm tra version/concurrency.
- Gọi domain method/domain service.
- Ghi dữ liệu, tích hợp outbox/side effects, xử lý lỗi.
- Trả DTO/API response.

Đây là ranh giới đặc biệt quan trọng với JPA vì domain method **không tự chịu trách nhiệm** về managed/detached, flush, commit và rollback.

## 27. Checklist tư duy khi viết một phương thức mới

Trước khi thêm một method như `approve()`, `activate()`, `close()` hoặc `cancel()` vào entity, hãy tự hỏi:

1. **Ý nghĩa hành động là gì?** Tên method có diễn đạt một nghiệp vụ hay chỉ là setter kỹ thuật?
2. **Trạng thái nghiệp vụ hiện tại nào được phép?** Có bảng chuyển trạng thái rõ ràng không?
3. **Invariant cục bộ nào phải bảo vệ?** Entity có đủ state để kiểm tra không?
4. **Kết quả là gì?** Thay đổi state, trả kết quả idempotent, ném domain exception hay tạo một domain event?
5. **Object có cần đang managed không?** Domain method có thể chạy thuần Java; nếu cần lưu, service phải dùng context/transaction phù hợp.
6. **Có lazy association cần thiết không?** Use case phải fetch dữ liệu trước khi method sử dụng.
7. **Trạng thái từ client có thể cũ không?** Có expectedVersion/ETag hoặc chính sách concurrency thích hợp không?
8. **Nhiều entity/row cùng tham gia invariant không?** Nếu có, version/lock root hoặc transaction phối hợp ra sao?
9. **Có tác dụng phụ ngoài database không?** Email, thanh toán, thông báo cần xử lý nhất quán với commit.
10. **Nếu người dùng gọi lại command thì sao?** Hành động có idempotent không, hoặc phải trả lỗi rõ ràng?
11. **Nếu transaction rollback thì sao?** Có dọn tài nguyên và giữ lại trạng thái nghiệp vụ nhất quán không?
12. **Có cần xóa entity hay chỉ đổi trạng thái?** Phân biệt `remove` với `cancel/disable/archive`.
13. **Có cách nào từ bên ngoài bỏ qua method?** Setter public, repository line độc lập hoặc bulk update có phá invariant không?
14. **Có thể test rule thuần Java không?** Nếu không, entity có đang phụ thuộc quá chặt vào repository/framework không?

Danh sách này không phải điều kiện JPA bắt buộc. Nó là công cụ thiết kế để tách rõ **domain state**, **persistence lifecycle** và **concurrency**.

## 28. Bài tập tự kiểm tra

**1. Một entity có `id = 100` có chắc chắn đang managed không?**

Không. Nó có thể detached hoặc có ID do ứng dụng gán. `EntityManager.contains(entity)` cho biết entity có đang thuộc context cụ thể không, nhưng không phân loại mọi lifecycle state chỉ từ false.

**2. Một đơn đang `DRAFT` có thể đã được lưu trong DB chưa?**

Có. `DRAFT` là business status, không có nghĩa entity new/transient.

**3. Vì sao nên dùng `order.place()` thay cho `order.setStatus(PLACED)`?**

`place()` là hành động nghiệp vụ có thể kiểm tra state/invariant trước khi thay đổi. Setter công khai cho phép code đi vòng qua những điều kiện đó.

**4. Gọi `place()` trên detached entity có khiến JPA tự ghi database không?**

Không. Detached object không được context hiện tại theo dõi; service cần nạp managed entity hoặc xử lý persistence operation phù hợp.

**5. Vì sao không nhất thiết gọi `em.merge(order)` sau `order.place()` trên managed entity?**

Vì JPA dirty checking theo dõi thay đổi của managed entity và đồng bộ khi flush/commit trong transaction thích hợp.

**6. `@Version` thay thế phương thức `place()` có guard clause được không?**

Không. `@Version` phát hiện xung đột cập nhật; guard clause bảo vệ transition nghiệp vụ. Cần cả hai khi có cạnh tranh.

**7. Nếu người dùng đã mở form version 5 nhưng DB đang version 6 thì sao?**

Nên báo conflict và cho người dùng xem lại dữ liệu, không lặng lẽ áp dụng payload cũ. Optimistic locking vẫn cần bảo vệ race khi flush/commit.

**8. `em.remove(order)` có tương đương `order.cancel(reason)` không?**

Không. `remove` yêu cầu xóa entity khỏi persistence store; `cancel` chuyển business status và thường giữ lịch sử.

**9. `@PreUpdate` có thích hợp để gửi email “Đơn đã thanh toán” không?**

Không nên. Callback là sự kiện persistence, có thể xảy ra trước commit và không phải nơi an toàn để thực hiện side effects bên ngoài.

**10. Vì sao `order.place()` có thể ném lazy-loading exception nếu gọi sau khi entity manager đóng?**

Vì nó cần đọc `lines`, nhưng collection LAZY chưa được tải và entity đã detached. Service cần fetch state trong context phù hợp.

**11. Nếu hai transaction cùng thay đổi line và trạng thái order, `@Version` trên root luôn đủ không?**

Không thể giả định. Tùy mapping/provider, cập nhật child có thể không làm tăng root version. Cần bảo vệ invariant toàn aggregate bằng chiến lược lock/version phù hợp.

**12. Một webhook thanh toán được gửi lại hai lần phải xử lý sao?**

Thiết kế idempotency theo transaction reference, đảm bảo không nhân đôi business effect và kiểm soát concurrency/unique ở persistence layer.

**13. Có nên mở transaction SQL từ lúc user vào trang đến lúc user nhấn Save 20 phút sau không?**

Không nên. Dùng transaction ngắn, trả DTO + version và kiểm tra lại state khi xử lý command Save.

**14. `merge()` có làm detached object được truyền vào trở thành managed không?**

Không. `merge()` trả về một managed instance; đối tượng gốc vẫn detached.

**15. Nếu quy tắc liên quan đến tồn kho ở nhiều kho, có nên cho `PurchaseOrder.place()` tự query database không?**

Thường không. Nên để application/domain service phối hợp các nguồn dữ liệu và transaction/locking; entity method giữ những invariant mà nó sở hữu.

## 29. Tổng kết

Thiết kế phương thức nghiệp vụ dựa trên **trạng thái entity thực tế** đòi hỏi phân biệt và phối hợp **ba tầng**:

1. **Trạng thái vòng đời JPA:** new, managed, detached, removed. Tầng này quyết định **đối tượng có được theo dõi và đồng bộ dữ liệu hay không**.
2. **Trạng thái nghiệp vụ:** DRAFT, PLACED, PAID, CANCELLED... Tầng này quyết định **hành động nào hợp lệ và invariant nào cần bảo vệ**.
3. **Trạng thái hiện hành và cạnh tranh:** database có thể bị thay đổi bởi transaction khác. Tầng này đòi hỏi **version/locking, transaction boundary và xử lý conflict**.

Phân công trách nhiệm nên rõ ràng:

```text
Controller / Consumer
        |
        v
Application service
  - Auth + authorization
  - Transaction + EntityManager
  - Load managed entity
  - Expected version / lock
        |
        v
Entity domain method
  - place()
  - cancel()
  - markPaid()
  - bảo vệ invariant, chuyển business state
        |
        v
JPA provider
  - Dirty checking
  - @Version / optimistic locking
  - Flush / commit
        |
        v
Database
  - PK, FK, UNIQUE, CHECK
  - Dữ liệu đã commit
```

Mẫu gọn cần ghi nhớ:

```java
// Entity: tự bảo vệ ý nghĩa nghiệp vụ.
public void place() {
    if (status != OrderStatus.DRAFT || lines.isEmpty()) {
        throw new IllegalStateException(
            "Đơn chưa đủ điều kiện để đặt"
        );
    }
    status = OrderStatus.PLACED;
}

// Service: quản lý persistence state và transaction.
PurchaseOrder managed = em.find(
    PurchaseOrder.class,
    orderId
);
managed.place();
// Provider đồng bộ thay đổi khi flush/commit,
// với optimistic locking nếu có @Version.
```

**Một entity ở `DRAFT` không nhất thiết là transient; một entity đang managed không nhất thiết mới nhất; một entity detached vẫn có thể thay đổi trong Java nhưng không tự được lưu.** Hiểu đúng ba điều này sẽ giúp thiết kế domain method vừa rõ nghiệp vụ, vừa an toàn khi thực thi qua JPA và nhiều transaction đồng thời.

### Tài liệu tham khảo

- [Jakarta Persistence — đặc tả](https://jakarta.ee/specifications/persistence/)
- [Jakarta Persistence API — `EntityManager`](https://jakarta.ee/specifications/persistence/3.1/apidocs/jakarta.persistence/jakarta/persistence/entitymanager)
- [Jakarta Persistence API — `@Version`](https://jakarta.ee/specifications/persistence/3.1/apidocs/jakarta.persistence/jakarta/persistence/version)
- [Jakarta Persistence API — `@OneToMany`](https://jakarta.ee/specifications/persistence/3.1/apidocs/jakarta.persistence/jakarta/persistence/onetomany)
