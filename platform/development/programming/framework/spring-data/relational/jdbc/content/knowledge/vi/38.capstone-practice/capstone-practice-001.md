# Phân tích bài toán quản lý đơn hàng và xác định ranh giới aggregate

Khi thiết kế một hệ thống quản lý đơn hàng bằng Spring Data JDBC, quyết định quan trọng đầu tiên không phải là tạo bao nhiêu bảng hay repository. Cần xác định **dữ liệu nào phải luôn nhất quán trong cùng một thay đổi nghiệp vụ**, đối tượng nào sở hữu dữ liệu đó và phần nào có vòng đời độc lập.

Một đơn hàng thường liên quan đến khách hàng, sản phẩm, tồn kho, thanh toán và giao hàng. Nếu gom tất cả vào một aggregate lớn, mọi thao tác có thể trở nên nặng nề và gây contention. Nếu tách từng bảng thành một aggregate riêng mà không xét invariant, hệ thống lại dễ có trạng thái không nhất quán.

Trong Domain-Driven Design, aggregate là ranh giới nhất quán. Aggregate root là cổng truy cập duy nhất để thay đổi các entity thuộc aggregate. Spring Data JDBC dựa trên mô hình này: một repository đại diện cho một aggregate root; các entity được tham chiếu từ root được xem là thành phần của aggregate và được lưu cùng root.

Bài học sử dụng bài toán quản lý đơn hàng để phân tích yêu cầu, nhận diện invariant, chọn aggregate root, phân biệt entity/value object/reference và thiết kế các repository cùng transaction boundary phù hợp với Spring Data JDBC.

## 1. Mô tả bài toán quản lý đơn hàng

Một cửa hàng trực tuyến cần hỗ trợ các nghiệp vụ:

- Khách hàng xem sản phẩm và giá bán.
- Khách hàng tạo đơn hàng với nhiều dòng sản phẩm.
- Hệ thống lưu địa chỉ giao hàng và thông tin giá tại thời điểm đặt hàng.
- Hệ thống kiểm tra và giữ tồn kho.
- Đơn hàng được xác nhận và thanh toán.
- Kho chuẩn bị hàng, tạo lô giao và cập nhật trạng thái giao hàng.
- Khách hàng có thể hủy đơn trong những trạng thái được phép.
- Nhân viên có thể xem lịch sử và xử lý hoàn tiền.

Một đơn hàng có thể chứa nhiều sản phẩm. Một sản phẩm có thể xuất hiện trong nhiều đơn hàng. Một khách hàng có thể có nhiều đơn hàng. Một sản phẩm có thể có nhiều lần cập nhật giá và tồn kho.

Các mối quan hệ này cho thấy mô hình quan hệ có nhiều khóa ngoại, nhưng chưa cho biết aggregate nào nên chứa aggregate nào.

### 1.1. Các khái niệm nghiệp vụ

| Khái niệm | Ý nghĩa |
| --- | --- |
| Customer | Người mua và thông tin tài khoản khách hàng |
| Product | Sản phẩm trong catalog, mô tả và giá hiện hành |
| InventoryItem | Số lượng tồn kho của một SKU tại một kho |
| Order | Đơn hàng và trạng thái nghiệp vụ của đơn |
| OrderLine | Một dòng sản phẩm trong đơn hàng |
| Payment | Giao dịch thanh toán và trạng thái thanh toán |
| Shipment | Lô giao hàng và trạng thái vận chuyển |
| Address | Địa chỉ giao hàng hoặc thanh toán |
| Money | Giá trị tiền cùng đơn vị tiền tệ |

Đây là danh sách ứng viên. Không phải mỗi khái niệm đều cần một aggregate root riêng; quyết định cuối cùng phụ thuộc vòng đời, invariant và nhu cầu cập nhật.

### 1.2. Vòng đời đơn hàng

Một luồng đơn hàng đơn giản:

~~~text
DRAFT
  |
  v
PENDING_PAYMENT
  |
  +---- payment failed ----> PAYMENT_FAILED
  |
  v
PAID
  |
  v
FULFILLING
  |
  v
SHIPPED
  |
  v
DELIVERED
~~~

Hủy đơn có thể được phép từ một số trạng thái, chẳng hạn DRAFT hoặc PENDING_PAYMENT. Khi đơn đã SHIPPED, yêu cầu hủy có thể phải chuyển thành quy trình trả hàng hoặc hoàn tiền.

Các trạng thái này là quy tắc domain. Không nên cho phép mọi service tùy ý cập nhật một cột status mà không kiểm tra state transition.

## 2. Aggregate là ranh giới nhất quán

Một aggregate là nhóm entity được bảo đảm nhất quán trong một lần thay đổi nguyên tử. Aggregate có đúng một root; mọi thay đổi đối với entity bên trong phải đi qua root.

Ví dụ kinh điển:

~~~text
Order aggregate
      |
      +-- Order
      |
      +-- OrderLine 1
      |
      +-- OrderLine 2
      |
      +-- OrderLine 3
~~~

Nếu đơn hàng có thuộc tính totalAmount, thay đổi số lượng hoặc thêm/xóa dòng hàng phải cập nhật tổng tiền theo cùng một thao tác domain. Đây là invariant giữa Order và OrderLine, nên chúng thuộc cùng aggregate.

Ngược lại, Customer và Product có vòng đời riêng. Một khách hàng có thể được cập nhật địa chỉ hoặc trạng thái mà không cần tải và lưu lại tất cả đơn hàng. Một sản phẩm có thể đổi mô tả hoặc giá hiện hành mà không được phép làm thay đổi các đơn hàng đã tạo.

Vì vậy, Customer và Product nên là các aggregate riêng, được Order tham chiếu bằng ID.

### 2.1. Aggregate root là cổng thay đổi

Một service không nên lấy OrderLine từ repository riêng rồi cập nhật độc lập. Thay đổi dòng hàng phải đi qua Order:

~~~java
order.addLine(productId, quantity, priceSnapshot);
order.changeQuantity(lineNumber, newQuantity);
order.removeLine(lineNumber);
order.confirm();
~~~

Các method của root có thể kiểm tra:

- Chỉ đơn DRAFT mới được thêm dòng.
- Số lượng phải lớn hơn 0.
- Không thể xác nhận đơn rỗng.
- Không thể thay đổi giá snapshot sau khi đơn đã xác nhận.
- Không thể hủy đơn đã giao.

Nhờ vậy, invariant được bảo vệ tại một nơi.

### 2.2. Một aggregate có thể ánh xạ thành nhiều bảng

Aggregate không đồng nghĩa với một bảng. Order và OrderLine có thể nằm trong hai bảng riêng nhưng vẫn thuộc cùng aggregate.

Tương tự, một bảng có thể chứa nhiều hàng thuộc nhiều aggregate root khác nhau.

Ranh giới aggregate được xác định bởi domain và consistency, không phải bởi số lượng bảng hoặc quan hệ foreign key.

## 3. Xác định invariant trước khi chia aggregate

Hãy liệt kê những quy tắc phải luôn đúng sau một command.

| Invariant | Dữ liệu liên quan | Ranh giới đề xuất |
| --- | --- | --- |
| Số lượng của mỗi dòng đơn phải dương | OrderLine | Order aggregate |
| Đơn hàng không được xác nhận nếu không có dòng hàng | Order, OrderLine | Order aggregate |
| Tổng tiền phải bằng tổng các dòng và chiết khấu | Order, OrderLine | Order aggregate |
| Giá tại thời điểm đặt hàng không thay đổi khi Product đổi giá | OrderLine snapshot, Product | Order giữ snapshot; Product riêng |
| Tồn kho không được âm | InventoryItem | Inventory aggregate |
| Một payment không được ghi nhận thành công hai lần | Payment | Payment aggregate hoặc payment provider |
| Shipment chỉ được tạo khi đơn đủ điều kiện fulfillment | Order, Shipment | Application service/process manager điều phối |
| Địa chỉ giao hàng của đơn đã đặt phải giữ nguyên | Order address snapshot | Order aggregate |

Điểm quan trọng là không phải mọi invariant đều phải nằm trong một aggregate. Một số quy tắc có thể được bảo đảm trong một transaction database bao quanh nhiều repository; một số quy tắc phân tán cần Saga, outbox hoặc quy trình bù trừ.

### 3.1. Invariant nội bộ aggregate

Ví dụ: tổng tiền của đơn hàng phải bằng tổng các dòng hàng.

Nếu thay đổi một dòng mà không cập nhật tổng tiền, dữ liệu sai ngay sau command. Vì Order sở hữu OrderLine, root có thể thực hiện cả hai thay đổi cùng lúc.

### 3.2. Invariant giữa các aggregate

Ví dụ: đơn hàng không được xác nhận nếu tồn kho không đủ.

Order và InventoryItem có vòng đời riêng. Không nên gộp toàn bộ inventory vào Order chỉ để thực hiện kiểm tra này.

Application service có thể điều phối hai aggregate trong cùng transaction nếu chúng dùng chung database resource và yêu cầu nghiệp vụ cần commit đồng thời. Nếu inventory nằm ở service/database khác, cần thiết kế quy trình phân tán, thường dùng Saga hoặc reservation workflow.

Aggregate boundary không cấm service phối hợp nhiều root; nó xác định nơi nào chịu trách nhiệm bảo vệ invariant cục bộ.

## 4. Xác định Order aggregate

Order thường là aggregate root trung tâm của bài toán.

Order sở hữu:

- Trạng thái đơn hàng.
- Danh sách dòng hàng.
- Địa chỉ giao hàng snapshot.
- Địa chỉ thanh toán snapshot nếu nghiệp vụ cần.
- Tổng tiền, thuế và chiết khấu đã chốt.
- Thời điểm tạo/xác nhận.
- Thông tin khách hàng được tham chiếu bằng ID.
- Version phục vụ optimistic locking.

OrderLine thuộc Order vì nó không có vòng đời độc lập ngoài đơn hàng. Nếu xóa đơn hàng theo chính sách nghiệp vụ, các dòng hàng của nó cũng được xử lý cùng aggregate.

### 4.1. OrderLine là child entity hay value object?

Một dòng hàng có thể được mô hình hóa như entity nội bộ nếu cần định danh ổn định trong phạm vi đơn hàng, ví dụ lineNumber. Nếu không cần identity độc lập, nó cũng có thể được xem như value object.

Trong Spring Data JDBC, cả hai trường hợp đều có thể được ánh xạ như nested entity thuộc aggregate. Điều quan trọng là không tạo OrderLineRepository riêng nếu dòng hàng không có vòng đời độc lập.

### 4.2. Snapshot dữ liệu sản phẩm

Không nên chỉ lưu Product ID rồi mỗi lần hiển thị đơn hàng lại đọc giá hiện tại từ Product.

Giả sử khách đặt một sản phẩm với giá 100.000 đồng. Ngày hôm sau giá catalog đổi thành 120.000 đồng. Đơn hàng cũ vẫn phải thể hiện giá 100.000 đồng tại thời điểm đặt.

OrderLine nên lưu snapshot:

- Product ID.
- SKU tại thời điểm đặt.
- Tên sản phẩm tại thời điểm đặt.
- Đơn giá.
- Đơn vị tiền tệ.
- Số lượng.
- Thuế/chiết khấu nếu cần.

Product ID là reference đến aggregate Product. Các giá trị mô tả và giá bán là snapshot thuộc OrderLine.

### 4.3. Địa chỉ giao hàng là snapshot

Khách hàng có thể đổi địa chỉ mặc định sau khi đặt hàng. Đơn cũ vẫn phải giao đến địa chỉ đã được xác nhận lúc đặt.

Do đó, Order nên giữ một Address value object riêng:

~~~java
public record Address(
        String recipientName,
        String phone,
        String street,
        String city,
        String postalCode,
        String countryCode
) {
}
~~~

Address không cần repository hoặc ID riêng. Nó thuộc Order và được ánh xạ vào cùng bảng Order bằng @Embedded hoặc thành cấu trúc value object phù hợp.

## 5. Xác định các aggregate khác

### 5.1. Customer aggregate

Customer có vòng đời riêng:

- Đăng ký tài khoản.
- Đổi tên, email hoặc số điện thoại.
- Thay đổi trạng thái hoạt động.
- Quản lý địa chỉ mặc định.
- Cập nhật tùy chọn nhận thông báo.

Order không nên chứa toàn bộ Customer object. Nó chỉ cần customer ID và các snapshot cần giữ cho lịch sử đơn.

Ví dụ:

~~~java
AggregateReference<Customer, Long> customer;
~~~

Khi tạo Order:

~~~java
AggregateReference<Customer, Long> customerRef =
        AggregateReference.to(customerId);
~~~

AggregateReference là wrapper quanh ID của một aggregate khác. Nó biểu đạt rõ rằng Order tham chiếu Customer nhưng không sở hữu Customer.

### 5.2. Product aggregate

Product quản lý:

- SKU.
- Tên và mô tả.
- Giá hiện hành.
- Trạng thái bán.
- Thuộc tính catalog.
- Danh mục hoặc thông tin phân loại.

Product không nằm trong Order aggregate. Nếu giá sản phẩm thay đổi, đơn hàng cũ vẫn giữ snapshot giá đã chốt.

OrderLine có thể lưu productId dưới dạng Long hoặc AggregateReference<Product, Long>. AggregateReference giúp thể hiện rõ kiểu aggregate được tham chiếu.

### 5.3. InventoryItem aggregate

InventoryItem có invariant riêng:

- availableQuantity không được âm.
- reservedQuantity không được vượt tổng tồn.
- Một reservation phải được giải phóng hoặc xác nhận theo quy trình.
- Cập nhật tồn kho cần concurrency control.

Có thể mô hình hóa theo SKU và warehouse:

~~~java
@Table("inventory_items")
public record InventoryItem(
        @Id Long id,
        String sku,
        Long warehouseId,
        int availableQuantity,
        int reservedQuantity,
        @Version Long version
) {
}
~~~

Nếu tồn kho thay đổi liên tục, InventoryItem có thể có contention cao. Tách nó khỏi Order giúp cập nhật kho không phải tải và lưu lại toàn bộ đơn hàng.

### 5.4. Payment aggregate

Payment có trạng thái và vòng đời riêng:

- INITIATED.
- AUTHORIZED.
- CAPTURED.
- FAILED.
- REFUNDED.

Một đơn hàng có thể có nhiều payment attempt hoặc refund. Payment cần được truy vết độc lập và có idempotency key để tránh xử lý thanh toán trùng.

Không đưa thông tin thẻ hoặc dữ liệu thanh toán nhạy cảm vào Order aggregate. Order chỉ giữ payment reference và trạng thái nghiệp vụ cần thiết.

### 5.5. Shipment aggregate

Shipment quản lý:

- Đơn vị vận chuyển.
- Mã vận đơn.
- Các kiện hàng.
- Thời điểm bàn giao.
- Trạng thái giao hàng.
- Lịch sử tracking.

Shipment có thể được tạo, cập nhật hoặc hủy độc lập theo quy trình vận chuyển. Order giữ shipment reference hoặc trạng thái fulfillment tổng hợp nếu cần.

## 6. Sơ đồ aggregate đề xuất

Một thiết kế ban đầu:

~~~text
Customer aggregate
  Customer
    |
    +-- Addresses (nếu địa chỉ thuộc hồ sơ khách)
          |
          v
     CustomerRepository

Product aggregate
  Product
    |
    +-- Catalog attributes
          |
          v
     ProductRepository

Inventory aggregate
  InventoryItem
          |
          v
     InventoryRepository

Order aggregate
  Order
    |
    +-- OrderLine 1
    +-- OrderLine 2
    +-- OrderLine 3
    +-- ShippingAddress snapshot
          |
          v
      OrderRepository

Payment aggregate
  Payment
          |
          v
     PaymentRepository

Shipment aggregate
  Shipment
          |
          v
    ShipmentRepository
~~~

Các aggregate tham chiếu nhau bằng ID. Application service điều phối use case cần nhiều aggregate.

### 6.1. Bảng ranh giới aggregate

| Aggregate root | Thành phần sở hữu | Tham chiếu ra ngoài |
| --- | --- | --- |
| Customer | Hồ sơ và dữ liệu thuộc khách hàng | Không cần chứa Order |
| Product | Catalog và giá hiện hành | Category ID nếu Category là aggregate riêng |
| InventoryItem | Số lượng và reservation của một SKU/kho | Product ID |
| Order | OrderLine, địa chỉ snapshot, tổng tiền, trạng thái đơn | Customer ID, Product ID, Payment ID, Shipment ID |
| Payment | Payment attempt, trạng thái, provider reference | Order ID |
| Shipment | Kiện hàng, tracking và trạng thái giao | Order ID |

Bảng này là thiết kế khởi đầu. Nếu domain có quy tắc khác, hãy điều chỉnh theo invariant và vòng đời thực tế.

## 7. Ánh xạ Order aggregate trong Spring Data JDBC

### 7.1. OrderLine

~~~java
import java.math.BigDecimal;

public record OrderLine(
        Long productId,
        String skuSnapshot,
        String productNameSnapshot,
        BigDecimal unitPrice,
        String currency,
        int quantity
) {

    public OrderLine {
        if (quantity <= 0) {
            throw new IllegalArgumentException(
                    "Quantity must be positive"
            );
        }

        if (unitPrice == null || unitPrice.signum() < 0) {
            throw new IllegalArgumentException(
                    "Unit price must not be negative"
            );
        }
    }

    public BigDecimal lineTotal() {
        return unitPrice.multiply(
                BigDecimal.valueOf(quantity)
        );
    }
}
~~~

OrderLine không có repository riêng. Nó được lưu cùng Order root.

### 7.2. Order root

Ví dụ rút gọn:

~~~java
import java.math.BigDecimal;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;

import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Version;
import org.springframework.data.jdbc.core.mapping.AggregateReference;
import org.springframework.data.relational.core.mapping.Embedded;
import org.springframework.data.relational.core.mapping.MappedCollection;
import org.springframework.data.relational.core.mapping.Table;

@Table("purchase_orders")
public class PurchaseOrder {

    @Id
    private Long id;

    private AggregateReference<Customer, Long> customer;

    private OrderStatus status;

    @Embedded(prefix = "shipping_")
    private Address shippingAddress;

    @MappedCollection(
            idColumn = "order_id",
            keyColumn = "line_number"
    )
    private List<OrderLine> lines = new ArrayList<>();

    private Instant createdAt;

    @Version
    private Long version;

    protected PurchaseOrder() {
    }

    public PurchaseOrder(
            AggregateReference<Customer, Long> customer,
            Address shippingAddress,
            Instant createdAt
    ) {
        this.customer = customer;
        this.shippingAddress = shippingAddress;
        this.createdAt = createdAt;
        this.status = OrderStatus.DRAFT;
    }

    public void addLine(OrderLine line) {
        ensureDraft();
        lines.add(line);
    }

    public void removeLine(int index) {
        ensureDraft();
        lines.remove(index);
    }

    public BigDecimal totalAmount() {
        return lines.stream()
                .map(OrderLine::lineTotal)
                .reduce(BigDecimal.ZERO, BigDecimal::add);
    }

    public void confirm() {
        ensureDraft();

        if (lines.isEmpty()) {
            throw new IllegalStateException(
                    "Cannot confirm an empty order"
            );
        }

        status = OrderStatus.PENDING_PAYMENT;
    }

    private void ensureDraft() {
        if (status != OrderStatus.DRAFT) {
            throw new IllegalStateException(
                    "Order can only be changed while in DRAFT"
            );
        }
    }

    public Long getId() {
        return id;
    }

    public OrderStatus getStatus() {
        return status;
    }

    public List<OrderLine> getLines() {
        return List.copyOf(lines);
    }
}
~~~

Ví dụ này tập trung vào ranh giới aggregate. Một implementation production cần bổ sung constructor/persistence mapping phù hợp, method state transition, xử lý currency/tax/discount và kiểm tra dữ liệu đầu vào.

### 7.3. Enum trạng thái

~~~java
public enum OrderStatus {
    DRAFT,
    PENDING_PAYMENT,
    PAID,
    FULFILLING,
    SHIPPED,
    DELIVERED,
    CANCELLED,
    PAYMENT_FAILED
}
~~~

Không nên cho phép service đặt status bất kỳ. Các method domain như confirm(), markPaid(), cancel() nên kiểm tra trạng thái hiện tại và điều kiện chuyển tiếp.

### 7.4. Repository chỉ dành cho aggregate root

~~~java
import org.springframework.data.repository.CrudRepository;

public interface OrderRepository
        extends CrudRepository<PurchaseOrder, Long> {
}
~~~

Không tạo OrderLineRepository nếu OrderLine là child thuộc Order aggregate.

Các repository khác:

~~~java
public interface CustomerRepository
        extends CrudRepository<Customer, Long> {
}

public interface ProductRepository
        extends CrudRepository<Product, Long> {
}

public interface InventoryRepository
        extends CrudRepository<InventoryItem, Long> {
}
~~~

Mỗi repository quản lý một aggregate root. Application service có thể phối hợp nhiều repository trong một use case.

## 8. Schema quan hệ tương ứng

Một schema minh họa:

~~~sql
CREATE TABLE customers (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    email VARCHAR(320) NOT NULL UNIQUE,
    status VARCHAR(30) NOT NULL
);

CREATE TABLE products (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    sku VARCHAR(80) NOT NULL UNIQUE,
    name VARCHAR(200) NOT NULL,
    current_price DECIMAL(12, 2) NOT NULL,
    currency CHAR(3) NOT NULL,
    active BOOLEAN NOT NULL
);

CREATE TABLE inventory_items (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    sku VARCHAR(80) NOT NULL,
    warehouse_id BIGINT NOT NULL,
    available_quantity INTEGER NOT NULL,
    reserved_quantity INTEGER NOT NULL,
    version BIGINT NOT NULL,
    UNIQUE (sku, warehouse_id),
    CHECK (available_quantity >= 0),
    CHECK (reserved_quantity >= 0)
);

CREATE TABLE purchase_orders (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    customer_id BIGINT NOT NULL,
    status VARCHAR(40) NOT NULL,
    created_at TIMESTAMP NOT NULL,
    shipping_recipient_name VARCHAR(200),
    shipping_phone VARCHAR(40),
    shipping_street VARCHAR(250),
    shipping_city VARCHAR(120),
    shipping_postal_code VARCHAR(30),
    shipping_country_code CHAR(2),
    version BIGINT NOT NULL,
    CONSTRAINT fk_order_customer
        FOREIGN KEY (customer_id) REFERENCES customers(id)
);

CREATE TABLE order_lines (
    order_id BIGINT NOT NULL,
    line_number INTEGER NOT NULL,
    product_id BIGINT NOT NULL,
    sku_snapshot VARCHAR(80) NOT NULL,
    product_name_snapshot VARCHAR(200) NOT NULL,
    unit_price DECIMAL(12, 2) NOT NULL,
    currency CHAR(3) NOT NULL,
    quantity INTEGER NOT NULL,
    PRIMARY KEY (order_id, line_number),
    CONSTRAINT fk_order_line_order
        FOREIGN KEY (order_id) REFERENCES purchase_orders(id),
    CHECK (quantity > 0),
    CHECK (unit_price >= 0)
);
~~~

Schema trên minh họa mapping và constraint. DDL identity, boolean và timestamp có thể cần điều chỉnh theo database vendor.

### 8.1. Vì sao order_lines có order_id?

OrderLine là entity được sở hữu bởi Order. Spring Data JDBC dùng cột tham chiếu ngược để tìm các child thuộc root.

Với @MappedCollection:

- idColumn xác định cột chứa ID của aggregate root.
- keyColumn lưu chỉ số List hoặc key của Map.

OrderLine không cần repository riêng và không được cập nhật độc lập khỏi Order.

### 8.2. Vì sao customer_id là reference?

Customer là aggregate khác. Order giữ ID tham chiếu đến Customer.

AggregateReference<Customer, Long> giúp biểu đạt rõ kiểu tham chiếu trong Java. Nó không tự tải Customer khi đọc Order; nếu cần thông tin khách hàng, application service hoặc query phù hợp phải đọc Customer riêng.

Foreign key database có thể được khai báo để bảo vệ tham chiếu, nhưng không nên cascade delete Customer sang Order nếu lịch sử đơn hàng phải được giữ lại.

## 9. Spring Data JDBC quản lý aggregate như thế nào?

Spring Data JDBC lưu aggregate root và các entity được sở hữu từ root.

Khi INSERT aggregate mới:

1. INSERT root.
2. Nhận ID root.
3. INSERT các child entities với foreign key trỏ về root.

Khi UPDATE aggregate đã tồn tại, implementation hiện tại có thể xóa các entity được tham chiếu, cập nhật root rồi insert lại các entity con theo trạng thái aggregate mới.

Điều này có một số hệ quả:

- Thay đổi một OrderLine có thể làm nhiều child rows được ghi lại.
- Aggregate quá lớn làm thao tác save nặng.
- Không nên đưa lịch sử giao hàng hoặc hàng triệu event vào collection của Order.
- Child entity không nên được cập nhật qua repository độc lập.
- Aggregate root cần giữ các invariant của collection.

Nếu Order có hàng chục nghìn dòng hoặc lịch sử thay đổi không giới hạn, hãy cân nhắc mô hình hóa phần dữ liệu tăng trưởng độc lập thành aggregate riêng.

## 10. Xác định transaction boundary cho use case

### 10.1. Tạo đơn hàng

Use case tạo đơn có thể:

1. Tải Customer.
2. Kiểm tra Customer đang hoạt động.
3. Tải Product cho từng dòng.
4. Chốt giá, tên và SKU vào OrderLine snapshot.
5. Tạo Order root.
6. Lưu Order aggregate.

Ví dụ service:

~~~java
@Service
public class CreateOrderService {

    private final CustomerRepository customerRepository;
    private final ProductRepository productRepository;
    private final OrderRepository orderRepository;
    private final Clock clock;

    public CreateOrderService(
            CustomerRepository customerRepository,
            ProductRepository productRepository,
            OrderRepository orderRepository,
            Clock clock
    ) {
        this.customerRepository = customerRepository;
        this.productRepository = productRepository;
        this.orderRepository = orderRepository;
        this.clock = clock;
    }

    @Transactional
    public PurchaseOrder create(CreateOrderCommand command) {
        Customer customer = customerRepository
                .findById(command.customerId())
                .orElseThrow();

        if (!customer.isActive()) {
            throw new IllegalStateException(
                    "Customer is not active"
            );
        }

        PurchaseOrder order = new PurchaseOrder(
                AggregateReference.to(customer.getId()),
                command.shippingAddress(),
                Instant.now(clock)
        );

        for (CreateOrderLineCommand line : command.lines()) {
            Product product = productRepository
                    .findById(line.productId())
                    .orElseThrow();

            if (!product.isActive()) {
                throw new IllegalStateException(
                        "Product is not available"
                );
            }

            order.addLine(new OrderLine(
                    product.getId(),
                    product.getSku(),
                    product.getName(),
                    product.getCurrentPrice(),
                    product.getCurrency(),
                    line.quantity()
            ));
        }

        order.confirm();

        return orderRepository.save(order);
    }
}
~~~

Đây là ví dụ minh họa. Command DTO và các getter/domain method cần được định nghĩa trong ứng dụng thực tế.

Transaction bao quanh thao tác đọc Customer/Product và ghi Order nếu tất cả repository dùng cùng DataSource và transaction manager. Nếu chỉ cần snapshot dữ liệu sản phẩm tại thời điểm đặt hàng, việc đọc Product không có nghĩa Product trở thành một phần của Order aggregate.

### 10.2. Giữ tồn kho

Giữ tồn kho là thay đổi trên Inventory aggregate. Có thể có service riêng:

~~~java
@Transactional
public void reserve(
        String sku,
        Long warehouseId,
        int quantity
) {
    InventoryItem inventory = repository
            .findBySkuAndWarehouseId(sku, warehouseId)
            .orElseThrow();

    repository.save(inventory.reserve(quantity));
}
~~~

Inventory root bảo vệ invariant không âm và dùng @Version hoặc khóa phù hợp để xử lý cạnh tranh.

Không đưa toàn bộ tồn kho vào Order aggregate chỉ để tránh một lời gọi repository.

### 10.3. Khi cần nhiều aggregate cùng commit

Nếu Order và Inventory cùng nằm trong một database và yêu cầu nghiệp vụ là tạo đơn cùng giữ hàng phải commit/rollback đồng thời, application service có thể đặt @Transactional bao quanh cả hai repository.

Tuy nhiên, điều đó làm transaction giữ nhiều aggregate cùng lúc và có thể tăng contention. Hãy đánh giá:

- Số lượng inventory rows cần khóa/cập nhật.
- Thời gian transaction.
- Khả năng optimistic conflict.
- Thứ tự lấy khóa.
- Connection pool.
- Cách rollback nếu một sản phẩm hết hàng.

Nếu quy trình kéo dài hoặc có hệ thống bên ngoài, dùng reservation state, outbox và Saga thường phù hợp hơn.

### 10.4. Thanh toán và giao hàng

Không giữ transaction JDBC mở trong lúc gọi payment gateway hoặc carrier API.

Một quy trình thường gặp:

1. Tạo Order ở trạng thái PENDING_PAYMENT.
2. Ghi outbox event trong cùng transaction.
3. Commit.
4. Worker gọi payment provider với idempotency key.
5. Ghi Payment result và cập nhật Order qua transaction mới.
6. Khi thanh toán thành công, bắt đầu fulfillment.
7. Shipment được tạo và quản lý bởi Shipment aggregate.

Database transaction không thể rollback side effect đã xảy ra ở payment provider. Vì vậy cần idempotency, outbox và quy trình bù trừ.

## 11. Khi nào nên tách OrderLine thành aggregate riêng?

Thông thường OrderLine thuộc Order. Tuy nhiên, có thể cần tách nếu dòng hàng có:

- Vòng đời độc lập kéo dài sau khi Order kết thúc.
- Quy trình xử lý riêng và nhiều writer độc lập.
- Khối lượng dữ liệu lớn, cập nhật với tần suất cao.
- Nhiều aggregate khác tham chiếu trực tiếp đến từng dòng.
- Invariant riêng không cần tải toàn bộ Order.

Nếu tách, Order chỉ giữ tham chiếu đến OrderLine aggregate hoặc các ID dòng. Nhưng cần cân nhắc rằng tổng tiền và trạng thái đơn sẽ không còn được bảo vệ tự động trong một aggregate.

Đừng tách chỉ vì muốn có một repository cho mỗi bảng. Repository trong Spring Data JDBC nên đại diện cho aggregate root, không phải mọi table.

## 12. Thiết kế command và domain behavior

Application service điều phối các aggregate; domain method bảo vệ invariant bên trong root.

Ví dụ command:

~~~java
public record CreateOrderCommand(
        Long customerId,
        Address shippingAddress,
        List<CreateOrderLineCommand> lines
) {
}

public record CreateOrderLineCommand(
        Long productId,
        int quantity
) {
}
~~~

Một số method domain:

~~~java
public void addLine(OrderLine line) {
    ensureDraft();
    lines.add(line);
}

public void confirm() {
    ensureDraft();

    if (lines.isEmpty()) {
        throw new IllegalStateException(
                "An order must contain at least one line"
        );
    }

    status = OrderStatus.PENDING_PAYMENT;
}

public void markPaid() {
    if (status != OrderStatus.PENDING_PAYMENT) {
        throw new IllegalStateException(
                "Only pending orders can be paid"
        );
    }

    status = OrderStatus.PAID;
}

public void cancel() {
    if (status != OrderStatus.DRAFT
            && status != OrderStatus.PENDING_PAYMENT) {
        throw new IllegalStateException(
                "Order cannot be cancelled in current state"
        );
    }

    status = OrderStatus.CANCELLED;
}
~~~

Đặt state transition trong root giúp repository không trở thành nơi chứa logic nghiệp vụ.

## 13. Những câu hỏi cần trả lời trước khi chốt aggregate boundary

| Câu hỏi | Dấu hiệu thiết kế |
| --- | --- |
| Dữ liệu có phải thay đổi cùng nhau để giữ invariant không? | Nếu có, cân nhắc cùng aggregate |
| Đối tượng có vòng đời riêng không? | Nếu có, cân nhắc aggregate riêng |
| Có nhiều nơi cập nhật độc lập không? | Tránh aggregate quá lớn |
| Có cần tham chiếu từ nhiều aggregate khác không? | Dùng ID/AggregateReference |
| Dữ liệu có cần snapshot lịch sử không? | Lưu snapshot trong aggregate nghiệp vụ |
| Có collection tăng không giới hạn không? | Tách phần tăng trưởng hoặc dùng event store |
| Có yêu cầu atomic commit qua nhiều aggregate không? | Application transaction hoặc Saga |
| Có gọi dịch vụ ngoài không? | Outbox/idempotency, không giữ DB transaction mở |
| Có contention cao không? | Xem lại aggregate size, version và lock strategy |
| Spring Data JDBC có phải ghi lại toàn bộ child collection không? | Đánh giá chi phí save aggregate |

## 14. Những lỗi thiết kế thường gặp

**“Mỗi bảng phải có một repository.”** Không. Spring Data JDBC khuyến nghị repository cho aggregate root. Child entity thuộc aggregate được thao tác qua root.

**“Order phải chứa toàn bộ Customer và Product object.”** Không. Đây là các aggregate khác; Order nên lưu ID tham chiếu và snapshot cần thiết.

**“OrderLine cần repository riêng để cập nhật số lượng.”** Không nếu OrderLine thuộc Order. Hãy gọi method trên Order root để bảo vệ invariant.

**“Foreign key nghĩa là cùng aggregate.”** Không. Foreign key là ràng buộc quan hệ database; aggregate là ranh giới consistency trong domain.

**“Một aggregate càng lớn càng dễ giữ nhất quán.”** Không. Aggregate quá lớn làm transaction nặng, tăng contention và khiến save ghi lại nhiều child rows.

**“Giá đơn hàng luôn lấy từ Product hiện tại.”** Không. OrderLine cần snapshot giá và thông tin mô tả tại thời điểm đặt hàng.

**“Order và Inventory phải là cùng aggregate vì đặt hàng cần giữ kho.”** Không nhất thiết. Chúng có invariant và vòng đời khác nhau; application service điều phối thao tác giữa các root.

**“Có thể gọi payment API trong @Transactional.”** Không nên. JDBC rollback không hoàn tác giao dịch ở payment provider.

**“AggregateReference tự tải aggregate được tham chiếu.”** Không. Nó biểu diễn ID của aggregate khác; muốn đọc dữ liệu phải truy vấn riêng.

**“Mọi quy tắc liên aggregate đều phải eventual consistency.”** Không. Nếu cùng database và yêu cầu atomicity, service có thể dùng một transaction qua nhiều repository. Nhưng ranh giới aggregate vẫn riêng.

**“Lưu toàn bộ lịch sử OrderStatus trong một collection vô hạn.”** Không. Lịch sử có thể phát triển không giới hạn; hãy cân nhắc audit/event table hoặc event store riêng.

## 15. Quy trình phân tích và xác định aggregate

1. **Thu thập use case:** tạo đơn, xác nhận, thanh toán, giữ kho, giao hàng, hủy và hoàn tiền.
2. **Lập glossary:** thống nhất Order, OrderLine, Product, Inventory, Payment, Shipment.
3. **Liệt kê invariant:** xác định quy tắc nào phải đúng sau từng command.
4. **Nhóm dữ liệu nhất quán:** các entity cần thay đổi nguyên tử thuộc cùng aggregate.
5. **Xác định root:** chọn entity chịu trách nhiệm bảo vệ invariant.
6. **Tách lifecycle độc lập:** Customer, Product, Inventory, Payment và Shipment có thể là aggregate riêng.
7. **Xác định reference:** dùng ID hoặc AggregateReference cho quan hệ giữa aggregate.
8. **Xác định snapshot:** lưu giá, SKU, tên và địa chỉ tại thời điểm đơn hàng được chốt.
9. **Thiết kế repository:** một repository cho mỗi aggregate root.
10. **Thiết kế transaction:** xác định thao tác nào cần cùng transaction và cùng DataSource.
11. **Đánh giá contention:** kiểm tra aggregate size, collection growth và optimistic locking.
12. **Thiết kế integration flow:** dùng outbox/Saga cho các bước liên hệ hệ thống ngoài.
13. **Kiểm thử invariant:** unit test domain, integration test mapping và transaction.
14. **Xem lại theo workload:** điều chỉnh boundary khi dữ liệu hoặc tần suất cập nhật thay đổi.

~~~mermaid
flowchart TD
    A["Phân tích use case quản lý đơn hàng"] --> B["Liệt kê entity, value object và nghiệp vụ"]
    B --> C["Xác định invariant cần giữ cùng nhau"]
    C --> D{"Các đối tượng cần thay đổi nguyên tử?"}
    D -->|Có| E["Gom vào một aggregate"]
    D -->|Không| F["Tách thành aggregate riêng"]
    E --> G["Chọn aggregate root"]
    F --> H["Tham chiếu bằng ID/AggregateReference"]
    G --> I["Thiết kế repository cho root"]
    H --> I
    I --> J["Xác định transaction và integration flow"]
    J --> K["Kiểm thử invariant, mapping và concurrency"]
~~~

## 16. Bài tập thực hành

Hãy thiết kế một ứng dụng bán hàng với Customer, Product, InventoryItem, Order, Payment và Shipment.

### Bài 1: Phân tích yêu cầu

1. Viết use case tạo đơn hàng.
2. Viết use case xác nhận đơn.
3. Viết use case thanh toán.
4. Viết use case hủy đơn.
5. Viết use case giao hàng.
6. Liệt kê invariant của từng use case.

### Bài 2: Chọn aggregate root

1. Xác định Order có sở hữu OrderLine không.
2. Xác định Customer có nằm trong Order aggregate không.
3. Xác định Product có nằm trong Order aggregate không.
4. Xác định InventoryItem có nằm trong Order aggregate không.
5. Giải thích lý do dựa trên lifecycle và invariant.
6. Tạo bảng mapping aggregate root với repository.

### Bài 3: Thiết kế domain model

1. Tạo Order root.
2. Tạo OrderLine child entity/value object.
3. Tạo Address snapshot.
4. Tạo Customer và Product aggregate riêng.
5. Dùng AggregateReference hoặc ID cho cross-aggregate references.
6. Viết method addLine(), confirm() và cancel() để bảo vệ invariant.

### Bài 4: Mapping Spring Data JDBC

1. Dùng @Table cho từng aggregate root.
2. Dùng @MappedCollection cho OrderLine.
3. Dùng @Embedded cho Address.
4. Dùng @Version trên Order và InventoryItem.
5. Tạo schema và foreign key.
6. Kiểm tra save/load toàn bộ Order aggregate.

### Bài 5: Thiết kế transaction boundary

1. Tạo Order cùng các OrderLine trong một transaction.
2. Điều phối giữ kho qua InventoryRepository.
3. Tạo Payment flow với outbox.
4. Xác định rollback khi một bước nội bộ thất bại.
5. Xác định Saga/compensation khi payment provider thất bại.
6. Kiểm tra không giữ transaction JDBC trong lúc gọi HTTP.

### Bài 6: Kiểm thử aggregate

1. Unit test Order không xác nhận khi rỗng.
2. Unit test quantity không hợp lệ.
3. Unit test không sửa Order sau khi xác nhận.
4. Integration test Order lưu cùng OrderLine.
5. Integration test Product đổi giá không làm thay đổi OrderLine snapshot.
6. Integration test optimistic locking cho Order.
7. Integration test rollback khi tạo Order thất bại.

## 17. Ghi nhớ

- Aggregate là ranh giới consistency; aggregate root là cổng thay đổi duy nhất.
- Một aggregate có thể ánh xạ thành nhiều bảng; một bảng không quyết định aggregate boundary.
- Order và OrderLine thường thuộc cùng aggregate vì tổng tiền, trạng thái và dòng hàng cần nhất quán.
- Customer, Product, InventoryItem, Payment và Shipment thường có lifecycle riêng nên là aggregate khác.
- Cross-aggregate references nên dùng ID hoặc AggregateReference, không nhúng toàn bộ object.
- OrderLine cần snapshot SKU, tên, giá, tiền tệ và dữ liệu nghiệp vụ tại thời điểm đặt hàng.
- Địa chỉ giao hàng nên được lưu như snapshot trong Order nếu cần giữ lịch sử.
- Spring Data JDBC khuyến nghị một repository cho mỗi aggregate root.
- @MappedCollection ánh xạ child collection bằng foreign key và key column.
- @Embedded ánh xạ value object vào cùng bảng với root.
- Spring Data JDBC hiện có thể xóa và tạo lại các entity được sở hữu khi save aggregate; tránh aggregate quá lớn hoặc collection tăng không giới hạn.
- Application service có thể phối hợp nhiều aggregate trong một transaction nếu dùng chung resource và yêu cầu nghiệp vụ cần atomicity.
- Payment và hệ thống giao hàng bên ngoài cần idempotency, outbox hoặc Saga; JDBC transaction không rollback được side effect từ xa.
- Xác định boundary từ invariant, lifecycle, concurrency và workload, không chỉ từ sơ đồ bảng.

**Ranh giới aggregate tốt giữ những dữ liệu phải nhất quán cùng nhau trong một root, đồng thời cho phép các phần có vòng đời riêng được cập nhật độc lập.** Với Spring Data JDBC, quyết định này trực tiếp định hình repository, mapping, transaction và cách ứng dụng điều phối nghiệp vụ quản lý đơn hàng.

## Tài liệu tham khảo

- [Spring Data Relational 4.1.2 — Domain Driven Design and Relational Databases](https://docs.spring.io/spring-data/relational/reference/jdbc/domain-driven-design.html)
- [Spring Data Relational 4.1.2 — Mapping and Aggregate References](https://docs.spring.io/spring-data/relational/reference/jdbc/mapping.html)
- [Spring Data Relational 4.1.2 — AggregateReference API](https://docs.spring.io/spring-data/relational/reference/api/java/org/springframework/data/jdbc/core/mapping/AggregateReference.html)
- [Spring Data Relational 4.1.2 — Persisting Entities](https://docs.spring.io/spring-data/relational/reference/jdbc/entity-persistence.html)
- [Spring Data Relational 4.1.2 — Transactionality](https://docs.spring.io/spring-data/relational/reference/jdbc/transactions.html)

