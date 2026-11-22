# Thực thể, đối tượng giá trị và ranh giới cụm nghiệp vụ (aggregate)

Trong Domain-Driven Design (DDD), mô hình miền mô tả những khái niệm và quy tắc của nghiệp vụ bằng các đối tượng có trách nhiệm rõ ràng. Ba khái niệm nền tảng là **Entity (thực thể)**, **Value Object (đối tượng giá trị)** và **Aggregate (cụm nghiệp vụ)**. Chúng giúp trả lời ba câu hỏi khác nhau: một đối tượng được nhận diện như thế nào, điều gì làm nên giá trị của nó, và những thay đổi nào phải được bảo vệ cùng nhau.

Với Spring Data REST, việc hiểu các khái niệm này rất quan trọng: framework có thể xuất repository thành REST resource, nhưng thiết kế ranh giới nghiệp vụ và bảo vệ invariant vẫn là trách nhiệm của mô hình miền và ứng dụng.

## 1. Bức tranh tổng thể

Hãy hình dung hệ thống bán hàng có đơn hàng, dòng hàng, sản phẩm và tiền tệ:

- Một **đơn hàng** có mã định danh và trạng thái thay đổi theo thời gian.
- Một **dòng hàng** thuộc về một đơn hàng; số lượng hoặc giá có thể thay đổi trong lúc đơn còn ở trạng thái nháp.
- Một **giá tiền** được xác định bởi số tiền và đơn vị tiền tệ. Hai giá trị có cùng số tiền nhưng khác tiền tệ không phải cùng một giá trị.
- Một **đơn hàng** cần bảo đảm các quy tắc như không xác nhận đơn rỗng, không thêm dòng hàng sau khi đã xác nhận, và mọi dòng hàng dùng cùng tiền tệ với đơn.

Mô hình có thể biểu diễn như sau:

~~~text
PurchaseOrder (Aggregate Root / Entity)
|
+-- OrderLine (Entity nội bộ)
|   +-- productId (tham chiếu đến aggregate Product)
|   +-- quantity
|   +-- unitPrice (Value Object: Money)
|
+-- status
+-- currencyCode
+-- version

Money (Value Object)
+-- amount
+-- currencyCode
~~~

Trong ví dụ này, `PurchaseOrder` là aggregate root. `OrderLine` có danh tính riêng trong phạm vi đơn hàng nhưng không phải aggregate root độc lập. `Money` không có danh tính; nó được xác định hoàn toàn bằng các thuộc tính.

## 2. Entity — đối tượng có danh tính

**Entity** là đối tượng mà ta cần theo dõi xuyên suốt vòng đời của nó. Hai entity có thể có cùng dữ liệu nhưng vẫn là hai đối tượng khác nhau nếu chúng có danh tính khác nhau.

Ví dụ:

- Hai khách hàng có cùng tên và địa chỉ vẫn là hai khách hàng khác nhau nếu ID khác nhau.
- Một đơn hàng có thể đổi trạng thái từ `DRAFT` sang `CONFIRMED`, nhưng vẫn là cùng đơn hàng vì danh tính của nó không đổi.
- Tên sản phẩm có thể thay đổi; ID sản phẩm vẫn giữ vai trò nhận diện sản phẩm.

### 2.1. Danh tính khác với các thuộc tính

Giả sử hai đối tượng sau:

| Thuộc tính | Đơn hàng A | Đơn hàng B |
|---|---|---|
| ID | 1001 | 1002 |
| Trạng thái | DRAFT | DRAFT |
| Tiền tệ | VND | VND |
| Tổng tiền | 500.000 | 500.000 |

Hai đơn có cùng trạng thái và tổng tiền, nhưng không phải cùng một entity. Chúng có danh tính khác nhau và có thể có lịch sử, chủ sở hữu hoặc quyền truy cập khác nhau.

Trong Java, entity thường có một thuộc tính ID:

~~~java
// Customer.java
package com.example.orders.domain;

import jakarta.persistence.*;

@Entity
public class Customer {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false)
    private String name;

    protected Customer() {
        // Constructor dành cho JPA.
    }

    public Customer(String name) {
        this.name = name;
    }

    public Long getId() {
        return id;
    }

    public String getName() {
        return name;
    }

    public void rename(String newName) {
        if (newName == null || newName.isBlank()) {
            throw new IllegalArgumentException("Tên khách hàng không được để trống");
        }
        this.name = newName;
    }
}
~~~

Đây là ví dụ mapping JPA; lớp cần nằm trong một ứng dụng Spring Boot có cấu hình persistence và database phù hợp. Entity không phải chỉ là một dòng dữ liệu: nó còn có danh tính, trạng thái và các hành vi thay đổi trạng thái hợp lệ.

### 2.2. Quy tắc khi thiết kế entity

- Dùng ID hoặc business key ổn định để nhận diện; đừng dùng tên, địa chỉ hoặc trạng thái có thể thay đổi làm danh tính.
- Đặt các thao tác thay đổi trạng thái trong những method có ý nghĩa nghiệp vụ như `rename()`, `confirm()` hoặc `cancel()`.
- Kiểm tra dữ liệu đầu vào và invariant ngay tại nơi trạng thái được thay đổi.
- Không công khai setter cho mọi thuộc tính nếu việc thay đổi tùy ý có thể làm đối tượng rơi vào trạng thái không hợp lệ.
- Tránh sinh `equals()` và `hashCode()` từ toàn bộ field mutable của entity. Điều đó có thể làm entity biến mất khỏi `HashSet` hoặc không tìm thấy trong `HashMap` sau khi một field thay đổi.

Với ID được sinh khi lưu, cần đặc biệt cẩn thận khi viết `equals()` và `hashCode()`: hai entity mới có ID null không được vô tình coi là bằng nhau. Có thể dùng business key thực sự bất biến nếu domain có một khóa như vậy, hoặc chọn chiến lược so sánh theo ID có xử lý đúng trạng thái chưa persist. Không dùng `@Data` của Lombok một cách máy móc cho entity vì nó thường sinh equality và `toString()` dựa trên nhiều field, dễ gây lỗi với quan hệ lazy hoặc vòng lặp hai chiều.

## 3. Value Object — đối tượng được xác định bằng giá trị

**Value Object** là đối tượng không có danh tính riêng trong domain. Hai instance được xem là bằng nhau khi toàn bộ thuộc tính có ý nghĩa của chúng bằng nhau.

Ví dụ, giá tiền `Money(100000, "VND")` được xác định bởi số tiền và tiền tệ. Ta không cần một `moneyId` để nhận ra giá trị này. Tương tự, địa chỉ giao hàng có thể là một value object gồm đường, thành phố và mã bưu chính.

### 3.1. Đặc điểm của Value Object

- **Không có identity riêng:** không cần ID database để phân biệt từng instance.
- **So sánh theo giá trị:** mọi thuộc tính tham gia định nghĩa giá trị đều được dùng khi so sánh.
- **Nên bất biến (immutable):** sau khi tạo, không thay đổi nội dung. Muốn có giá trị khác thì tạo instance mới.
- **Tự bảo vệ tính hợp lệ:** constructor hoặc factory method kiểm tra dữ liệu ngay khi tạo.
- **Có thể thay thế:** vì không có identity, có thể thay một instance bằng instance khác có cùng giá trị mà không làm đổi ý nghĩa domain.

Value Object giúp tránh truyền các kiểu nguyên thủy rời rạc. Thay vì truyền một `BigDecimal` và một `String` không liên quan, ta truyền một `Money` để bảo đảm số tiền luôn đi cùng đơn vị tiền tệ.

### 3.2. Ví dụ Money bằng Java

~~~java
// Money.java
package com.example.orders.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Embeddable;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.Currency;
import java.util.Locale;
import java.util.Objects;

@Embeddable
public class Money {

    @Column(name = "amount", precision = 19, scale = 2, nullable = false)
    private BigDecimal amount;

    @Column(name = "currency_code", length = 3, nullable = false)
    private String currencyCode;

    protected Money() {
        // JPA cần constructor không tham số có visibility public/protected.
    }

    public Money(BigDecimal amount, String currencyCode) {
        if (amount == null || amount.signum() < 0) {
            throw new IllegalArgumentException("Số tiền phải lớn hơn hoặc bằng 0");
        }
        if (currencyCode == null || currencyCode.isBlank()) {
            throw new IllegalArgumentException("Phải có mã tiền tệ");
        }

        String normalizedCode = currencyCode.toUpperCase(Locale.ROOT);
        Currency.getInstance(normalizedCode);

        this.amount = amount.setScale(2, RoundingMode.UNNECESSARY);
        this.currencyCode = normalizedCode;
    }

    public BigDecimal getAmount() {
        return amount;
    }

    public String getCurrencyCode() {
        return currencyCode;
    }

    public Money plus(Money other) {
        Objects.requireNonNull(other, "other");
        if (!currencyCode.equals(other.currencyCode)) {
            throw new IllegalArgumentException("Không thể cộng hai loại tiền tệ khác nhau");
        }
        return new Money(amount.add(other.amount), currencyCode);
    }

    @Override
    public boolean equals(Object other) {
        if (this == other) {
            return true;
        }
        if (!(other instanceof Money money)) {
            return false;
        }
        return amount.equals(money.amount)
            && currencyCode.equals(money.currencyCode);
    }

    @Override
    public int hashCode() {
        return Objects.hash(amount, currencyCode);
    }

    @Override
    public String toString() {
        return amount + " " + currencyCode;
    }
}
~~~

Một số điểm đáng chú ý:

1. `@Embeddable` cho biết `Money` được lưu như một phần trạng thái của entity sở hữu nó, không có bảng và identity riêng chỉ vì nó là một value object.
2. Không có setter công khai. Ứng dụng tạo giá trị qua constructor để kiểm tra số tiền và mã tiền tệ.
3. `setScale(2, RoundingMode.UNNECESSARY)` yêu cầu dữ liệu có tối đa hai chữ số thập phân có ý nghĩa; nếu cần làm tròn, domain phải chọn chính sách làm tròn rõ ràng thay vì để framework tự quyết định.
4. `plus()` chỉ cộng khi cùng loại tiền tệ.
5. `equals()` và `hashCode()` dựa trên giá trị. Constructor chuẩn hóa scale của `BigDecimal` để tránh trường hợp `10.0` và `10.00` bị coi là khác nhau chỉ vì scale.

Ví dụ sử dụng:

~~~java
import java.math.BigDecimal;

Money price = new Money(new BigDecimal("125000.00"), "VND");
Money shipping = new Money(new BigDecimal("15000.00"), "VND");

Money total = price.plus(shipping);

System.out.println(total);
~~~

Output:

~~~text
140000.00 VND
~~~

Đây là đoạn mã Java minh họa cách dùng Value Object; để chạy, đặt nó trong một lớp có `main()` và cấu hình dependency Jakarta Persistence phù hợp nếu dùng annotation JPA. Phần tính toán `Money` tự nó không cần database.

### 3.3. Mapping Value Object bằng JPA

Có một số cách lưu value object:

- `@Embeddable` + `@Embedded`: các thuộc tính của object được lưu trong bảng của entity sở hữu nó.
- `@ElementCollection`: lưu một tập hợp basic value hoặc embeddable value thuộc entity; các phần tử không có identity độc lập.
- `AttributeConverter`: chuyển một value object thành một kiểu cột đơn, ví dụ một mã trạng thái hoặc value object đơn giản thành chuỗi.

Ví dụ `Money` được nhúng trong `OrderLine`. Vì bảng dòng hàng có thể chứa nhiều cột giá, ta đổi tên cột bằng `@AttributeOverrides`:

~~~java
@Embedded
@AttributeOverrides({
    @AttributeOverride(
        name = "amount",
        column = @Column(name = "unit_price_amount", precision = 19, scale = 2)
    ),
    @AttributeOverride(
        name = "currencyCode",
        column = @Column(name = "unit_price_currency", length = 3)
    )
})
private Money unitPrice;
~~~

JPA field access được dùng trong ví dụ vì annotation mapping đặt trên field. Provider có thể đọc/ghi field persistent trực tiếp; vì thế value object có thể giữ API bất biến ở tầng ứng dụng dù vẫn có constructor không tham số cho persistence. Với các mapping phức tạp, hãy kiểm tra yêu cầu của phiên bản Jakarta Persistence và provider đang dùng.

## 4. Aggregate — ranh giới nhất quán của domain

**Aggregate** là một nhóm entity và value object được xem như một đơn vị nhất quán nghiệp vụ. **Aggregate Root** là entity gốc, là điểm truy cập công khai để bên ngoài yêu cầu thay đổi trạng thái bên trong aggregate.

Aggregate không đơn giản là một nhóm bảng có quan hệ khóa ngoại. Ranh giới aggregate được chọn theo những invariant nào phải được bảo vệ cùng nhau trong một thao tác nghiệp vụ.

Ví dụ với đơn hàng:

- Đơn hàng không thể được xác nhận nếu không có dòng hàng.
- Chỉ đơn hàng nháp mới được thêm hoặc xóa dòng hàng.
- Số lượng mỗi dòng phải lớn hơn 0.
- Tiền tệ của giá từng dòng phải khớp với tiền tệ của đơn.
- Dòng hàng không được chuyển sang đơn hàng khác bằng cách sửa một thuộc tính tùy ý.

Những quy tắc này liên quan đến trạng thái của đơn hàng và các dòng hàng. Vì vậy, `PurchaseOrder` là aggregate root, còn `OrderLine` nằm bên trong aggregate.

### 4.1. Aggregate Root chịu trách nhiệm gì?

Aggregate root:

1. Cung cấp các method nghiệp vụ để thay đổi aggregate.
2. Kiểm tra invariant trước khi thay đổi trạng thái.
3. Kiểm soát việc tạo, thêm, sửa hoặc xóa entity nội bộ.
4. Là điểm mà các đối tượng bên ngoài tham chiếu đến aggregate.
5. Xác định ranh giới transaction cho các thay đổi cần nhất quán cùng nhau.

Code bên ngoài không nên lấy một `OrderLine` rồi sửa trực tiếp số lượng hoặc chuyển nó sang đơn khác. Nó nên yêu cầu `PurchaseOrder.addLine(...)` hoặc một command tương ứng trên root. Nhờ đó, root có đủ ngữ cảnh để kiểm tra trạng thái đơn, tiền tệ, số lượng và các quy tắc liên quan.

### 4.2. Tham chiếu aggregate khác bằng ID

Nếu đơn hàng cần tham chiếu đến sản phẩm, sản phẩm thường là một aggregate riêng. Đơn hàng có thể lưu `productId` thay vì giữ một object graph chứa toàn bộ entity Product.

Lợi ích:

- Aggregate Order không cần nạp và khóa toàn bộ aggregate Product chỉ để thêm một dòng hàng.
- Ranh giới thay đổi của hai aggregate rõ hơn.
- Giảm nguy cơ cascade ghi/xóa xuyên qua các aggregate.
- Có thể truy vấn thông tin sản phẩm qua một service/repository khác khi cần.

Nếu nghiệp vụ yêu cầu lưu lại tên hoặc giá sản phẩm tại thời điểm đặt hàng, có thể lưu snapshot đó trong OrderLine. Snapshot là dữ liệu lịch sử của đơn hàng; nó không biến Product thành một phần của aggregate Order.

Không có quy tắc tuyệt đối rằng mọi quan hệ JPA đều phải là ID scalar. Điều quan trọng là hiểu ranh giới nhất quán: một quan hệ object hoặc foreign key trong database không tự quyết định aggregate boundary.

## 5. Ví dụ aggregate PurchaseOrder hoàn chỉnh hơn

Ví dụ dưới đây dùng một entity root `PurchaseOrder`, entity nội bộ `OrderLine` và value object `Money`. Mỗi public class nằm trong file riêng cùng package `com.example.orders.domain`.

### 5.1. OrderLine — entity nội bộ của aggregate

~~~java
// OrderLine.java
package com.example.orders.domain;

import jakarta.persistence.*;

import java.math.BigDecimal;
import java.util.Objects;

@Entity
@Table(name = "purchase_order_lines")
public class OrderLine {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "order_id", nullable = false)
    private PurchaseOrder order;

    @Column(name = "product_id", nullable = false)
    private Long productId;

    @Column(nullable = false)
    private int quantity;

    @Embedded
    @AttributeOverrides({
        @AttributeOverride(
            name = "amount",
            column = @Column(name = "unit_price_amount", precision = 19, scale = 2, nullable = false)
        ),
        @AttributeOverride(
            name = "currencyCode",
            column = @Column(name = "unit_price_currency", length = 3, nullable = false)
        )
    })
    private Money unitPrice;

    protected OrderLine() {
        // JPA cần constructor không tham số.
    }

    OrderLine(PurchaseOrder order, Long productId, int quantity, Money unitPrice) {
        this.order = Objects.requireNonNull(order, "order");
        this.productId = Objects.requireNonNull(productId, "productId");
        if (quantity <= 0) {
            throw new IllegalArgumentException("Số lượng phải lớn hơn 0");
        }
        this.quantity = quantity;
        this.unitPrice = Objects.requireNonNull(unitPrice, "unitPrice");
    }

    public Long getId() {
        return id;
    }

    public Long getProductId() {
        return productId;
    }

    public int getQuantity() {
        return quantity;
    }

    public Money getUnitPrice() {
        return unitPrice;
    }

    Money subtotal() {
        BigDecimal lineAmount = unitPrice.getAmount()
            .multiply(BigDecimal.valueOf(quantity));
        return new Money(lineAmount, unitPrice.getCurrencyCode());
    }
}
~~~

Constructor của `OrderLine` có package visibility, nên code bên ngoài package không thể tùy ý tạo dòng hàng. Trong ví dụ, chỉ `PurchaseOrder` tạo dòng hàng mới. Entity này có ID persistence, nhưng vẫn là thành phần nội bộ của aggregate Order.

### 5.2. PurchaseOrder — aggregate root

~~~java
// PurchaseOrder.java
package com.example.orders.domain;

import jakarta.persistence.*;

import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Objects;

@Entity
@Table(name = "purchase_orders")
public class PurchaseOrder {

    public enum Status {
        DRAFT,
        CONFIRMED,
        CANCELLED
    }

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Version
    private long version;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 20)
    private Status status;

    @Column(name = "currency_code", nullable = false, length = 3)
    private String currencyCode;

    @OneToMany(
        mappedBy = "order",
        cascade = CascadeType.ALL,
        orphanRemoval = true
    )
    private List<OrderLine> lines = new ArrayList<>();

    protected PurchaseOrder() {
        // JPA cần constructor không tham số.
    }

    public PurchaseOrder(String currencyCode) {
        this.currencyCode = new Money(
            BigDecimal.ZERO,
            currencyCode
        ).getCurrencyCode();
        this.status = Status.DRAFT;
    }

    public void addLine(Long productId, int quantity, Money unitPrice) {
        ensureDraft();

        Objects.requireNonNull(productId, "productId");
        Objects.requireNonNull(unitPrice, "unitPrice");

        if (quantity <= 0) {
            throw new IllegalArgumentException("Số lượng phải lớn hơn 0");
        }
        if (!currencyCode.equals(unitPrice.getCurrencyCode())) {
            throw new IllegalArgumentException(
                "Tiền tệ của dòng hàng phải khớp với đơn hàng"
            );
        }
        if (lines.stream().anyMatch(line -> line.getProductId().equals(productId))) {
            throw new IllegalArgumentException(
                "Sản phẩm đã có trong đơn; hãy dùng một thao tác cập nhật riêng"
            );
        }

        lines.add(new OrderLine(this, productId, quantity, unitPrice));
    }

    public void removeLine(Long productId) {
        ensureDraft();
        boolean removed = lines.removeIf(
            line -> line.getProductId().equals(productId)
        );
        if (!removed) {
            throw new IllegalArgumentException("Không tìm thấy sản phẩm trong đơn");
        }
    }

    public void confirm() {
        ensureDraft();
        if (lines.isEmpty()) {
            throw new IllegalStateException("Không thể xác nhận đơn hàng rỗng");
        }
        status = Status.CONFIRMED;
    }

    public Money total() {
        Money result = new Money(BigDecimal.ZERO, currencyCode);
        for (OrderLine line : lines) {
            result = result.plus(line.subtotal());
        }
        return result;
    }

    private void ensureDraft() {
        if (status != Status.DRAFT) {
            throw new IllegalStateException(
                "Chỉ đơn hàng nháp mới được thay đổi"
            );
        }
    }

    public Long getId() {
        return id;
    }

    public long getVersion() {
        return version;
    }

    public Status getStatus() {
        return status;
    }

    public String getCurrencyCode() {
        return currencyCode;
    }

    public List<OrderLine> getLines() {
        return Collections.unmodifiableList(lines);
    }
}
~~~

Các quyết định quan trọng trong ví dụ:

- Không có setter công khai cho `status`, `currencyCode` hoặc `lines`.
- `addLine()` kiểm tra trạng thái đơn, số lượng, tiền tệ và sản phẩm trùng trước khi tạo entity nội bộ.
- `confirm()` kiểm tra invariant của toàn aggregate.
- `orphanRemoval = true` giúp persistence provider xóa dòng hàng khi nó bị loại khỏi collection và thay đổi được flush.
- `cascade = CascadeType.ALL` áp dụng thao tác persistence từ root đến các dòng hàng thuộc root. Cascade là cơ chế persistence; bản thân nó không thay thế quy tắc domain.
- `@Version` khai báo optimistic locking cho entity root. Cơ chế version giúp phát hiện cập nhật đồng thời xung đột trên entity được version hóa. Nếu cần version của root bảo vệ cả thay đổi collection con, hãy kiểm tra lock scope và hành vi của persistence provider với mapping cụ thể; có thể cần chiến lược force-increment hoặc cập nhật version rõ ràng.

### 5.3. Repository đặt ở aggregate root

~~~java
// PurchaseOrderRepository.java
package com.example.orders.domain;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.rest.core.annotation.RepositoryRestResource;

@RepositoryRestResource(
    path = "orders",
    collectionResourceRel = "orders"
)
public interface PurchaseOrderRepository
        extends JpaRepository<PurchaseOrder, Long> {
}
~~~

Theo hướng thiết kế DDD, repository này là cổng truy cập aggregate Order. Không cần tạo một repository REST công khai cho `OrderLine` chỉ để thao tác các dòng hàng bên trong đơn. Những thao tác đó nên đi qua `PurchaseOrder`.

Nếu cần truy vấn theo productId, trạng thái hoặc ngày tạo, có thể thêm query method vào repository root; query phục vụ đọc không nhất thiết làm thay đổi ranh giới aggregate. Cần cân nhắc riêng nếu một query trả về entity nội bộ hoặc cho phép cập nhật trực tiếp entity đó.

## 6. Aggregate boundary và Spring Data REST

Spring Data REST **xuất Spring Data repository thành REST resource**. Ví dụ repository `PurchaseOrderRepository` có thể tạo collection resource `/orders` và item resource `/orders/{id}`. Mặc định, response dùng HAL và các association của domain type có thể được biểu diễn bằng link. Đường dẫn có thể đổi bằng `@RepositoryRestResource`.

Một số request thường gặp:

~~~http
GET /orders
GET /orders/1001
~~~

Client có thể khám phá các link từ URL gốc của ứng dụng. Representation HAL thường có `_links`, và collection có thể dùng `_embedded` cùng metadata phân trang.

### 6.1. Spring Data REST không tự tạo aggregate boundary

Đây là điểm cần nhớ nhất:

- DDD định nghĩa aggregate boundary dựa trên invariant và nhất quán nghiệp vụ.
- JPA định nghĩa mapping entity, association, cascade, ownership và lifecycle persistence.
- Spring Data REST định nghĩa repository nào được xuất bản và HTTP resource nào được tạo từ repository.

Ba lớp này liên quan với nhau nhưng không đồng nghĩa. Việc chỉ tạo `PurchaseOrderRepository` không tự động chứng minh mọi đường ghi đều đi qua method `addLine()` hoặc `confirm()`. Một request REST được framework xử lý thông qua repository method được expose; ví dụ `POST` collection và `PUT/PATCH` item có thể gọi `save()`. Chúng không tự gọi các domain method tùy chỉnh chỉ vì những method đó tồn tại trên entity.

Nếu client có thể gửi dữ liệu để thay đổi trạng thái theo cách bỏ qua invariant, mô hình có nguy cơ bị phá vỡ dù code domain có method kiểm tra đúng.

### 6.2. Cách giữ ranh giới khi xuất API

1. **Chỉ xuất repository của aggregate root.** Tránh tạo public repository cho entity nội bộ nếu không có nhu cầu thực sự.
2. **Rà soát repository detection.** Mặc định Spring Data REST có thể xuất các public repository; có thể dùng `@RepositoryRestResource(exported = false)` hoặc cấu hình detection strategy để kiểm soát repository nào được expose.
3. **Kiểm soát method ghi.** `@RestResource(exported = false)` có thể ẩn repository method khỏi HTTP. Cấu hình exposure cũng có thể giới hạn method HTTP. Nếu cần API đọc qua Spring Data REST nhưng command ghi phải đi qua service, hãy tắt các write method tương ứng.
4. **Đặt command ở application service/controller.** Các thao tác như thêm dòng hàng, xác nhận đơn, hủy đơn nên gọi domain method trên root trong một transaction.
5. **Bảo vệ bằng authorization.** Không xem việc ẩn repository hoặc link là thay thế Spring Security. Quyền đọc collection, đọc item, ghi, xóa và thực hiện command cần được thiết kế rõ.
6. **Kiểm tra association resource.** Spring Data REST có thể cung cấp resource con cho association. Các thao tác association như liên kết URI của resource đã tồn tại không phải là một command nghiệp vụ tùy chỉnh; cần kiểm tra chúng có phù hợp với aggregate invariant hay không.

Ví dụ application service cho command xác nhận đơn:

~~~java
// OrderCommandService.java
package com.example.orders.application;

import com.example.orders.domain.PurchaseOrder;
import com.example.orders.domain.PurchaseOrderRepository;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
@Transactional
public class OrderCommandService {

    private final PurchaseOrderRepository repository;

    public OrderCommandService(PurchaseOrderRepository repository) {
        this.repository = repository;
    }

    public void confirm(Long orderId) {
        PurchaseOrder order = repository.findById(orderId)
            .orElseThrow(() -> new IllegalArgumentException("Không tìm thấy đơn hàng"));

        order.confirm();
        // Entity đang được quản lý trong transaction; JPA dirty checking
        // sẽ ghi thay đổi khi transaction commit.
    }
}
~~~

Controller có thể công khai command với endpoint có ý nghĩa nghiệp vụ:

~~~java
// OrderCommandController.java
package com.example.orders.api;

import com.example.orders.application.OrderCommandService;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/orders")
public class OrderCommandController {

    private final OrderCommandService service;

    public OrderCommandController(OrderCommandService service) {
        this.service = service;
    }

    @PostMapping("/{orderId}/confirm")
    @ResponseStatus(HttpStatus.NO_CONTENT)
    public void confirm(@PathVariable Long orderId) {
        service.confirm(orderId);
    }
}
~~~

Để tránh hai đường ghi có quy tắc khác nhau, hãy quyết định rõ route nào là đường ghi chính. Nếu command controller phải bảo vệ invariant, không để các write endpoint của repository công khai cho phép client sửa cùng dữ liệu theo cách bỏ qua command. Có thể tắt write method của repository bằng `@RestResource(exported = false)` hoặc chọn không export repository đó và cung cấp API riêng.

## 7. Transaction và tính nhất quán giữa các aggregate

Một aggregate được thiết kế để các invariant của nó được giữ trong một transaction. Khi thêm dòng hàng, thay đổi trạng thái và tính tổng tiền, các thay đổi cần thiết cho một đơn hàng phải được lưu cùng nhau.

Không nên gom mọi entity liên quan vào một aggregate lớn chỉ để có một transaction. Ví dụ, Product, Customer, Inventory và PurchaseOrder có thể là các aggregate riêng vì chúng có vòng đời, quy tắc và tần suất thay đổi khác nhau.

Khi một use case ảnh hưởng nhiều aggregate:

- Tham chiếu aggregate khác bằng ID.
- Giữ transaction ngắn và tập trung vào một aggregate khi có thể.
- Nếu cần đồng bộ giữa nhiều aggregate, cân nhắc domain event, application event, outbox hoặc workflow/saga tùy yêu cầu.
- Chấp nhận eventual consistency ở những phần nghiệp vụ cho phép; không dùng eventual consistency cho invariant phải đúng tức thời.
- Dùng idempotency cho command có thể được gửi lại, nhất là khi client retry do timeout.

Không phải mọi thao tác nhiều aggregate đều bắt buộc dùng saga. Nếu cùng một database và invariant thực sự cần transaction nguyên tử, một transaction nhiều repository có thể phù hợp. Tuy nhiên, lựa chọn đó nên là quyết định có chủ đích vì nó làm các aggregate phụ thuộc chặt hơn.

### 7.1. Optimistic locking

Nếu nhiều người dùng có thể cùng cập nhật một đơn, `@Version` giúp persistence provider phát hiện xung đột khi phiên bản trong database đã thay đổi so với phiên bản mà transaction đang cập nhật.

Khi xảy ra optimistic lock failure, ứng dụng nên trả lỗi xung đột phù hợp, yêu cầu client tải lại trạng thái mới và quyết định lại thao tác. Không nên tự động ghi đè dữ liệu mới bằng bản cũ.

Optimistic locking bảo vệ cập nhật đồng thời theo mapping/version scope được provider áp dụng. Hãy kiểm thử trường hợp hai transaction cùng thay đổi root và child collection; đừng giả định mọi thay đổi quan hệ đều tự động tăng version của root trong mọi mapping.

## 8. Khi nào dùng Entity, Value Object và Aggregate?

| Tình huống | Mô hình phù hợp | Lý do |
|---|---|---|
| Khách hàng có ID, có lịch sử và có thể đổi tên | Entity | Cần theo dõi cùng một khách hàng qua thời gian |
| Giá tiền gồm số tiền và tiền tệ | Value Object | Giá trị được xác định bởi toàn bộ thuộc tính |
| Địa chỉ giao hàng chỉ có ý nghĩa trong đơn hàng | Value Object | Không cần identity độc lập |
| Dòng hàng chỉ sống trong một đơn hàng và chịu quy tắc của đơn | Entity nội bộ của aggregate | Có thể có ID cục bộ, nhưng lifecycle do root kiểm soát |
| Đơn hàng có quy tắc xác nhận và quản lý dòng hàng | Aggregate với PurchaseOrder root | Nhiều trạng thái cần được bảo vệ cùng nhau |
| Sản phẩm có vòng đời và quy tắc giá/tồn kho riêng | Aggregate riêng | Không nên để đơn hàng kiểm soát trực tiếp trạng thái Product |

Một câu hỏi hữu ích khi phân loại là: **nếu hai instance có cùng mọi thuộc tính, domain có cần phân biệt chúng không?** Nếu có, thường là Entity. Nếu không và chỉ cần so sánh giá trị, thường là Value Object. Nếu nhiều entity/value object phải thay đổi cùng nhau để giữ invariant, hãy xem xét gom chúng thành một Aggregate.

## 9. Lỗi thiết kế thường gặp

1. **Mọi bảng đều thành một entity độc lập có repository công khai.** Điều này có thể làm lộ cấu trúc persistence và cho phép sửa dữ liệu bỏ qua aggregate root.
2. **Value Object có ID không cần thiết.** Nếu object không có vòng đời độc lập, ID chỉ làm mô hình phức tạp hơn.
3. **Value Object mutable.** Một instance dùng chung bị thay đổi có thể âm thầm ảnh hưởng nhiều nơi. Hãy ưu tiên immutable và tạo instance mới khi giá trị đổi.
4. **Entity equality dựa trên tất cả field.** Khi field mutable thay đổi, cấu trúc collection dựa trên hash có thể hỏng; quan hệ lazy còn có thể kích hoạt query ngoài ý muốn.
5. **Aggregate quá lớn.** Một thao tác đơn giản phải tải và khóa quá nhiều object, tăng cạnh tranh và làm transaction dài.
6. **Aggregate quá nhỏ.** Một invariant phải đúng tức thời lại bị chia qua nhiều root, khiến ứng dụng phải điều phối nhiều transaction.
7. **Để controller hoặc serializer sửa field tùy ý.** Setter công khai không thay thế các method nghiệp vụ.
8. **Nhầm cascade với aggregate boundary.** Cascade chỉ mô tả hành vi persistence; nó không tự xác định đối tượng nào được phép thay đổi đối tượng nào.
9. **Cho rằng Spring Data REST tự gọi service.** Repository exporter gọi các repository method được expose. Domain method tùy chỉnh không tự trở thành HTTP command endpoint.
10. **Chỉ ẩn link mà không kiểm soát quyền.** Client có thể gọi URL trực tiếp; cần authorization thực sự ở server.

## 10. Kiểm thử mô hình miền

Nên kiểm thử invariant mà không cần database trước, sau đó kiểm thử mapping và API ở tầng tích hợp.

### Unit test cho Value Object

- Cùng số tiền và cùng tiền tệ thì bằng nhau.
- Khác tiền tệ thì không bằng nhau.
- Không cộng được hai loại tiền tệ khác nhau.
- Giá trị âm hoặc mã tiền tệ không hợp lệ bị từ chối.
- Quy tắc scale và rounding được kiểm tra rõ.

### Unit test cho Aggregate Root

- Không thể xác nhận đơn rỗng.
- Không thể thêm dòng hàng sau khi xác nhận.
- Không thể thêm số lượng bằng 0 hoặc âm.
- Không thể thêm giá có tiền tệ khác đơn.
- Không thể thêm cùng sản phẩm hai lần nếu domain quy định một dòng cho mỗi sản phẩm.
- Xóa dòng hàng khỏi đơn nháp làm tổng tiền thay đổi đúng.

### Integration test

- `@Embedded` lưu `Money` vào các cột dự kiến.
- `cascade` và `orphanRemoval` hoạt động theo mapping.
- Chỉ repository được phép mới xuất hiện trong HAL root.
- HTTP method bị tắt thực sự trả `405 Method Not Allowed`.
- Command controller gọi domain method và transaction rollback nếu invariant thất bại.
- Security chặn người dùng không có quyền.
- Hai transaction cập nhật đồng thời được xử lý theo optimistic locking.

## 11. Quy trình thiết kế thực tế

Khi bắt đầu một module mới, có thể làm theo thứ tự sau:

1. Liệt kê các khái niệm nghiệp vụ và xác định đối tượng nào cần identity.
2. Tìm các nhóm dữ liệu được xác định hoàn toàn bằng giá trị; mô hình hóa chúng thành Value Object.
3. Viết ra các invariant cần luôn đúng sau một thao tác.
4. Nhóm các entity/value object phải thay đổi cùng nhau để bảo vệ invariant.
5. Chọn Aggregate Root và chỉ mở các method nghiệp vụ hợp lệ trên root.
6. Thiết kế repository cho aggregate root và quyết định repository nào được Spring Data REST export.
7. Chọn đường ghi: repository CRUD phù hợp với invariant đơn giản, hoặc command service/controller khi thao tác cần workflow và quy tắc nghiệp vụ rõ.
8. Viết unit test cho invariant trước, rồi integration test cho JPA mapping, transaction, REST representation và security.

## 12. Kết luận

- **Entity** trả lời câu hỏi “đây là cùng một đối tượng qua thời gian hay không?” bằng identity.
- **Value Object** trả lời câu hỏi “hai giá trị có cùng ý nghĩa hay không?” bằng các thuộc tính và equality theo giá trị.
- **Aggregate** trả lời câu hỏi “những thay đổi nào phải được bảo vệ cùng nhau?” bằng ranh giới nhất quán và aggregate root.
- **Spring Data REST** xuất repository thành REST resource. Nó hỗ trợ xây API nhanh, nhưng không tự thiết kế aggregate, không tự bảo vệ mọi invariant và không tự biến domain method thành command endpoint.

Khi mô hình miền rõ ràng, repository, JPA mapping và REST API có thể được tổ chức quanh cùng ranh giới nghiệp vụ. Điều đó giúp API dễ hiểu hơn, giảm đường ghi ngoài ý muốn và làm các quy tắc quan trọng có một nơi chịu trách nhiệm.

## 13. Tài liệu tham khảo

- [Spring Data REST — Repository resources](https://docs.spring.io/spring-data/rest/reference/repository-resources.html): cách repository được xuất thành collection, item, association và query resources; HTTP method được ánh xạ tới repository method.
- [Spring Data REST — Customizing repository exposure](https://docs.spring.io/spring-data/rest/reference/customizing-sdr.html): repository detection strategy và cách ẩn repository method khỏi HTTP.
- [Jakarta Persistence — Embeddable](https://jakarta.ee/specifications/platform/11/apidocs/jakarta/persistence/embeddable): cách khai báo kiểu được lưu như một phần trạng thái của entity sở hữu.
- [Jakarta Persistence — Entity](https://jakarta.ee/specifications/platform/11/apidocs/jakarta/persistence/Entity.html): yêu cầu identity và mapping của entity.
- [Jakarta Persistence — Version](https://jakarta.ee/specifications/persistence/3.2/apidocs/jakarta.persistence/jakarta/persistence/Version.html): optimistic locking và các kiểu dữ liệu hợp lệ cho version field.
- [Jakarta Persistence Specification](https://jakarta.ee/specifications/persistence/3.2/jakarta-persistence-spec-3.2.pdf): mô tả embeddable, entity state và persistence mapping.
