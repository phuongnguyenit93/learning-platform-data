# Từ yêu cầu nghiệp vụ đến sơ đồ aggregate và schema quan hệ

Trong Spring Data JDBC, thiết kế mô hình dữ liệu nên bắt đầu từ **quy tắc nghiệp vụ và ranh giới nhất quán** rồi mới đến class Java và bảng SQL. Nếu bắt đầu từ danh sách bảng hoặc quan hệ khóa ngoại, ta dễ biến một đồ thị quan hệ lớn thành một aggregate duy nhất, khiến việc đọc, lưu và kiểm soát thay đổi trở nên tốn kém.

Bài học này hướng dẫn một quy trình có thể lặp lại:

1. Thu thập tình huống sử dụng và thuật ngữ nghiệp vụ.
2. Viết các **bất biến** (invariants) phải luôn đúng.
3. Chọn **aggregate root** và xác định dữ liệu thuộc quyền sở hữu của nó.
4. Phân biệt **thành phần thuộc aggregate** với **tham chiếu sang aggregate khác**.
5. Vẽ sơ đồ aggregate, sau đó ánh xạ sang bảng, khóa chính và khóa ngoại.
6. Cài đặt mô hình bằng Spring Data JDBC, repository và transaction.
7. Dự đoán tác động của quyết định thiết kế đối với truy vấn, cập nhật đồng thời và thay đổi schema.

Ví dụ xuyên suốt là một hệ thống bán hàng cho phép khách hàng tạo đơn nháp, thêm sản phẩm, chỉnh số lượng và xác nhận đơn. Các tên `SalesOrder`, `OrderLine`, `Customer` và `Product` chỉ là tên mẫu; quy trình thiết kế áp dụng tương tự cho đơn đặt phòng, phiếu nhập kho, hóa đơn hoặc hồ sơ nghiệp vụ khác.

## 1. Bắt đầu bằng yêu cầu nghiệp vụ, không bắt đầu bằng entity

Giả sử nhóm sản phẩm mô tả hệ thống như sau:

> Một khách hàng có thể tạo nhiều đơn hàng. Mỗi đơn có nhiều dòng sản phẩm. Khi đơn còn ở trạng thái nháp, khách hàng được thêm, sửa hoặc xóa dòng. Dòng hàng phải có số lượng dương và giá bán được chốt tại thời điểm thêm vào đơn. Không thể xác nhận đơn trống. Sau khi xác nhận, người dùng không được tự ý đổi các dòng hàng. Khách hàng và danh mục sản phẩm được quản lý độc lập với đơn hàng.

Trước khi viết `@Table` hoặc DDL, hãy tách mô tả thành những câu hỏi quyết định ranh giới:

- **Thao tác nào cần bảo đảm nhất quán ngay lập tức?** Ví dụ không cho xác nhận đơn trống, hoặc không cho sửa dòng của đơn đã xác nhận.
- **Đối tượng nào cùng vòng đời?** Một dòng hàng thuộc về đúng một đơn; xóa đơn thì dòng hàng thường không còn ý nghĩa độc lập.
- **Đối tượng nào có vòng đời riêng?** Khách hàng và sản phẩm vẫn tồn tại dù đơn hàng bị hủy.
- **Đâu là dữ liệu lịch sử phải giữ nguyên?** Giá của sản phẩm trong đơn đã đặt không được tự đổi khi bảng giá hiện tại thay đổi.
- **Điều gì diễn ra đồng thời?** Hai thao tác có thể cùng sửa một đơn; cần ngăn việc ghi đè thay đổi của nhau.
- **Chỉ đọc hay phải sửa?** Màn hình thống kê có thể cần join nhiều bảng, nhưng việc join khi đọc không có nghĩa các bảng đó thuộc một aggregate.

Các câu hỏi này giúp tránh việc đồng nhất một quan hệ nghiệp vụ với một quan hệ sở hữu trong mô hình aggregate.

## 2. Chuyển yêu cầu thành use case và bất biến

**Use case** mô tả điều người dùng hoặc hệ thống muốn thực hiện. **Bất biến** mô tả điều phải luôn đúng sau một thao tác nghiệp vụ hoàn chỉnh.

| Use case | Dữ liệu cần đọc/đổi | Bất biến cần bảo vệ |
|---|---|---|
| Tạo đơn nháp | Khách hàng được chọn, trạng thái đơn | Đơn thuộc về một khách hàng hợp lệ |
| Thêm sản phẩm | Các dòng của đơn, thông tin giá hiện tại của sản phẩm | Số lượng lớn hơn 0, giá không âm, đơn phải còn nháp |
| Sửa số lượng | Một dòng thuộc đơn | Không được sửa đơn đã xác nhận; số lượng mới hợp lệ |
| Xóa dòng | Danh sách dòng | Chỉ sửa khi đơn còn nháp |
| Xác nhận đơn | Trạng thái và toàn bộ dòng | Không xác nhận đơn trống; mỗi dòng hợp lệ |
| Hiển thị lịch sử đơn | Đơn và thông tin giá đã chốt | Thay đổi giá danh mục không làm đổi giá trong đơn cũ |
| Đổi tên khách hàng | Hồ sơ khách hàng | Không cần ghi lại tất cả đơn hàng của khách |

Bất biến định hướng quyết định: nếu một quy tắc đòi hỏi cùng lúc kiểm tra trạng thái đơn và các dòng hàng, thì các dữ liệu đó là ứng viên tốt để nằm **trong cùng một aggregate**.

Ngược lại, đổi tên khách hàng không cần sửa đồng thời mọi đơn đã đặt. Điều này ủng hộ việc `Customer` là aggregate riêng.

### 2.1. Phân biệt bất biến của aggregate và quy tắc liên aggregate

Có thể chia quy tắc thành hai nhóm:

**Bất biến nội bộ của đơn hàng**

- Một đơn có một trạng thái rõ ràng: `DRAFT`, `CONFIRMED` hoặc `CANCELLED`.
- Mỗi dòng có số lượng dương.
- Đơn đã xác nhận không cho phép thay đổi dòng bằng các thao tác dành cho đơn nháp.
- Đơn không có dòng thì không được xác nhận.

Những điều này có thể được thực thi bởi các phương thức của `SalesOrder`.

**Quy tắc liên quan aggregate khác**

- `customerId` phải chỉ tới khách hàng được phép mua hàng.
- `productId` phải tương ứng với một sản phẩm có thể đặt.
- Giá lấy từ danh mục sản phẩm tại thời điểm thêm vào đơn.
- Kiểm tra và giữ tồn kho theo quy tắc của hệ thống kho.

Các quy tắc này cần application service, repository khác hoặc cơ chế phối hợp quy trình. Một lời gọi `orderRepository.save(order)` không tự bảo đảm mọi aggregate khác đều đã được xác thực, cập nhật hoặc khóa.

## 3. Chọn aggregate root dựa trên ranh giới nhất quán

**Aggregate** là một tập hợp đối tượng domain được xem như một đơn vị nhất quán khi thực hiện thay đổi. **Aggregate root** là điểm vào có trách nhiệm kiểm soát các thay đổi bên trong tập hợp đó.

Với ví dụ bán hàng:

- `SalesOrder` là **aggregate root**: sở hữu trạng thái đơn và danh sách dòng.
- `OrderLine` là thành phần thuộc aggregate `SalesOrder`, không được tự ý thay đổi ngoài các phương thức nghiệp vụ của root.
- `Customer` là aggregate root độc lập.
- `Product` là aggregate root độc lập.

Một dòng hàng thường không cần repository riêng; để cập nhật dòng, ứng dụng tải `SalesOrder`, gọi hành vi domain và lưu lại `SalesOrder`.

Sơ đồ khái niệm:

~~~mermaid
flowchart LR
    subgraph OA["Aggregate: SalesOrder"]
        O["SalesOrder (root)"]
        L["OrderLine (0..n)"]
        O -->|"sở hữu, kiểm soát vòng đời"| L
    end

    subgraph CA["Aggregate: Customer"]
        C["Customer (root)"]
    end

    subgraph PA["Aggregate: Product"]
        P["Product (root)"]
    end

    O -.->|"customerId"| C
    L -.->|"productId"| P
~~~

Mũi tên liền biểu thị **sở hữu trong cùng aggregate**. Mũi tên nét đứt biểu thị **tham chiếu bằng định danh sang aggregate khác**.

Đây là sơ đồ ranh giới nghiệp vụ, chưa phải ERD của database. Quan hệ tham chiếu bằng ID vẫn có thể được database bảo vệ bằng foreign key mà không biến hai bên thành cùng aggregate.

### 3.1. Vì sao không đưa Customer và Product vào SalesOrder?

Giả sử một đơn gồm 20 sản phẩm. Nếu đưa mọi `Product` cùng thông tin tồn kho, giá hiện tại, danh mục và lịch sử vào bên trong `SalesOrder`, aggregate sẽ phình to. Mỗi lần sửa đơn, việc tải và lưu có thể chạm đến rất nhiều dữ liệu không thuộc vòng đời của đơn.

Hơn nữa, cùng một `Product` được nhiều đơn tham chiếu. Một thay đổi tên hoặc giá sản phẩm không nên yêu cầu cập nhật toàn bộ các aggregate đơn hàng đang tồn tại.

Vì vậy, mỗi `OrderLine` giữ `productId` và các thông tin **snapshot** cần bảo toàn lịch sử, ví dụ `skuSnapshot` và `unitPrice`. Tên/giá hiện tại vẫn nằm trong aggregate `Product`.

### 3.2. Aggregate không đồng nghĩa với một bảng

Một aggregate có thể trải qua nhiều bảng: `SalesOrder` có bảng root và bảng dòng hàng. Ngược lại, một hệ thống database có thể thiết lập foreign key giữa hai bảng thuộc **hai aggregate khác nhau**.

Bảng quan hệ mô tả sự toàn vẹn dữ liệu ở mức lưu trữ. Aggregate mô tả những **thao tác nghiệp vụ nào phải được quản lý cùng một ranh giới nhất quán**.

## 4. Viết mô hình domain trước khi viết schema

Từ những phân tích trên, mô hình có thể được diễn đạt bằng một bảng thiết kế:

| Khái niệm | Vai trò | Thuộc tính chính | Ai có quyền thay đổi? |
|---|---|---|---|
| `SalesOrder` | Aggregate root | `id`, `version`, `customerId`, `status`, `lines` | Các hành vi trên `SalesOrder` |
| `OrderLine` | Thành phần thuộc đơn | `productId`, `skuSnapshot`, `quantity`, `unitPrice` | Thông qua root `SalesOrder` |
| `Customer` | Aggregate độc lập | `id`, hồ sơ khách hàng | Nghiệp vụ quản lý khách hàng |
| `Product` | Aggregate độc lập | `id`, `sku`, giá hiện tại | Nghiệp vụ danh mục sản phẩm |

**Hành vi quan trọng hơn getter/setter.** Thay vì để application service tự ý gọi `order.getLines().clear()` hoặc `order.setStatus(...)`, root có thể cung cấp:

~~~text
SalesOrder.createDraft(customerId)
SalesOrder.addLine(productId, skuSnapshot, quantity, unitPrice)
SalesOrder.changeQuantity(lineIndex, newQuantity)
SalesOrder.removeLine(lineIndex)
SalesOrder.confirm()
SalesOrder.totalAmount()
~~~

Mỗi phương thức bảo vệ quy tắc nghiệp vụ liên quan. Các trường collection nên được đóng gói để code bên ngoài không sửa trực tiếp mà bỏ qua kiểm tra của root.

### 4.1. Giá hiện tại và giá lịch sử

Giá hiện tại nằm trên `Product`; giá thực tế đã chọn cho dòng hàng nằm trên `OrderLine.unitPrice`.

Ví dụ:

~~~text
Ngày 1: Product #20 có giá 120.000
        Order #15 thêm Product #20
        OrderLine.unitPrice = 120.000

Ngày 8: Product #20 đổi giá thành 135.000
        OrderLine của Order #15 vẫn có giá 120.000
~~~

Nếu chỉ lưu `productId` rồi luôn join lấy giá từ `Product` khi tính tổng, lịch sử đơn có thể bị thay đổi ngoài ý muốn. Snapshot giá là một quyết định nghiệp vụ, không đơn thuần là tối ưu truy vấn.

### 4.2. Tổng tiền: tính từ dòng hay lưu thành cột?

Với ví dụ này, tổng đơn được suy ra từ các dòng:

\[
\text{totalAmount}=\sum_{i=1}^{n} \text{quantity}_i\times\text{unitPrice}_i
\]

Có thể triển khai `totalAmount()` trong root và không thêm cột `total_amount` để tránh giữ hai nguồn dữ liệu có nguy cơ lệch nhau.

Nếu báo cáo hoặc yêu cầu hiệu năng thực sự cần lưu tổng tiền, hãy bổ sung quy tắc **cập nhật tổng cùng lúc với mọi thay đổi dòng** và cân nhắc cách kiểm chứng tính nhất quán. Việc thêm cột tính sẵn không phải là bước bắt buộc của mọi thiết kế.

## 5. Từ sơ đồ aggregate sang schema quan hệ

Khi đã xác định ranh giới, ta mới quyết định bảng và khóa.

Ánh xạ đề xuất:

| Aggregate / thành phần | Bảng quan hệ | Khóa | Liên kết |
|---|---|---|---|
| `Customer` | `customers` | `id` | Độc lập |
| `Product` | `products` | `id` | Độc lập |
| `SalesOrder` | `sales_orders` | `id` | `customer_id` tham chiếu `customers.id` |
| `OrderLine` thuộc đơn | `sales_order_lines` | `(order_id, line_no)` | `order_id` liên kết root; `product_id` tham chiếu `products.id` |

Ở ví dụ này, một `OrderLine` được xác định trong phạm vi đơn bởi vị trí `line_no` trong danh sách. Nó không có vòng đời và repository riêng. Nếu nghiệp vụ đòi hỏi mã định danh ổn định cho từng dòng bất kể đổi thứ tự, cần chọn thiết kế khóa khác thay vì coi vị trí danh sách là ID nghiệp vụ bất biến.

Sơ đồ quan hệ:

~~~mermaid
erDiagram
    CUSTOMERS ||--o{ SALES_ORDERS : "customer_id"
    SALES_ORDERS ||--o{ SALES_ORDER_LINES : "order_id"
    PRODUCTS ||--o{ SALES_ORDER_LINES : "product_id"

    CUSTOMERS {
        bigint id PK
        varchar display_name
    }
    PRODUCTS {
        bigint id PK
        varchar sku
        numeric current_price
    }
    SALES_ORDERS {
        bigint id PK
        bigint version
        bigint customer_id FK
        varchar status
    }
    SALES_ORDER_LINES {
        bigint order_id PK,FK
        integer line_no PK
        bigint product_id FK
        varchar sku_snapshot
        integer quantity
        numeric unit_price
    }
~~~

Đường nối trong ERD là **quan hệ dữ liệu vật lý**. Đường nối `Customer → SalesOrder` hoặc `Product → OrderLine` không hàm ý rằng Customer/Product là thành phần sở hữu bởi aggregate đơn hàng.

### 5.1. DDL mẫu cho PostgreSQL

Đoạn SQL dưới đây là một schema tối giản, có thể dùng làm điểm xuất phát. Trong ứng dụng thực tế, nên quản lý nó bằng Flyway hoặc Liquibase.

~~~sql
CREATE TABLE customers (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    display_name VARCHAR(160) NOT NULL
);

CREATE TABLE products (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    sku VARCHAR(64) NOT NULL UNIQUE,
    current_price NUMERIC(15, 2) NOT NULL
        CHECK (current_price >= 0)
);

CREATE TABLE sales_orders (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    version BIGINT NOT NULL,
    customer_id BIGINT NOT NULL,
    status VARCHAR(20) NOT NULL,
    CONSTRAINT fk_order_customer
        FOREIGN KEY (customer_id) REFERENCES customers (id)
        ON DELETE RESTRICT,
    CONSTRAINT ck_order_status
        CHECK (status IN ('DRAFT', 'CONFIRMED', 'CANCELLED'))
);

CREATE TABLE sales_order_lines (
    order_id BIGINT NOT NULL,
    line_no INTEGER NOT NULL,
    product_id BIGINT NOT NULL,
    sku_snapshot VARCHAR(64) NOT NULL,
    quantity INTEGER NOT NULL,
    unit_price NUMERIC(15, 2) NOT NULL,

    CONSTRAINT pk_order_line
        PRIMARY KEY (order_id, line_no),
    CONSTRAINT fk_order_line_order
        FOREIGN KEY (order_id) REFERENCES sales_orders (id)
        ON DELETE CASCADE,
    CONSTRAINT fk_order_line_product
        FOREIGN KEY (product_id) REFERENCES products (id)
        ON DELETE RESTRICT,
    CONSTRAINT ck_order_line_no
        CHECK (line_no >= 0),
    CONSTRAINT ck_order_line_quantity
        CHECK (quantity > 0),
    CONSTRAINT ck_order_line_price
        CHECK (unit_price >= 0)
);

CREATE INDEX idx_sales_orders_customer
    ON sales_orders (customer_id);

CREATE INDEX idx_order_lines_product
    ON sales_order_lines (product_id);
~~~

**Ý nghĩa của các ràng buộc:**

- `PRIMARY KEY (order_id, line_no)`: mỗi vị trí dòng chỉ xuất hiện một lần trong một đơn.
- `FOREIGN KEY (order_id)`: mọi dòng phải thuộc một đơn tồn tại.
- `ON DELETE CASCADE` trên `order_id`: ở tầng database, các dòng không bị mồ côi nếu đơn bị xóa. Đây là cơ chế bảo vệ dữ liệu; Spring Data JDBC vẫn quản lý vòng đời các thành phần con theo aggregate.
- `FOREIGN KEY (customer_id)` và `FOREIGN KEY (product_id)`: bảo vệ tham chiếu nếu các aggregate cùng database và nghiệp vụ yêu cầu.
- `ON DELETE RESTRICT` đối với Customer/Product: tránh xóa các bản ghi còn được đơn hàng lịch sử tham chiếu. Hệ thống có thể dùng vô hiệu hóa mềm thay vì xóa vật lý.
- `CHECK`: tăng cường những bất biến có thể kiểm tra bằng một bản ghi SQL đơn lẻ.
- `version`: hỗ trợ optimistic locking ở aggregate root.

**Giới hạn của CHECK:** Ràng buộc `CHECK (quantity > 0)` kiểm tra được từng dòng; nhưng quy tắc “chỉ xác nhận khi có ít nhất một dòng” phụ thuộc vào trạng thái root và số lượng bản ghi con. Với schema đơn giản này, quy tắc đó được bảo vệ chủ yếu ở domain/application layer; nếu có nhiều luồng ghi trực tiếp vào database, cần thiết kế cơ chế kiểm soát bổ sung.

### 5.2. Thứ tự và vòng đời của OrderLine

Cột `line_no` đi cùng kiểu Java `List<OrderLine>`, phản ánh vị trí các phần tử. Thứ tự có thể thay đổi khi xóa, chèn hoặc sắp xếp lại danh sách. Do đó:

- Không dùng `line_no` như một định danh lâu dài khi các hệ thống khác giữ tham chiếu đến từng dòng.
- Nếu nghiệp vụ cần sửa một dòng bằng mã ổn định, hãy thiết kế định danh riêng và kiểm tra cách Spring Data JDBC ánh xạ khóa con.
- Không tự động thêm một repository riêng cho OrderLine nếu nó vẫn thuộc vòng đời của SalesOrder.

Một kiểu collection khác như `Set` hoặc `Map` có thể dẫn đến cách ánh xạ khóa khác; phải thiết kế cột và tính duy nhất tương ứng.

## 6. Ánh xạ aggregate bằng Spring Data JDBC

Ví dụ sử dụng các annotation của Spring Data Relational:

- `@Table`: tên bảng.
- `@Id`: khóa chính của aggregate root.
- `@Version`: kiểm soát optimistic locking.
- `@Column`: tên cột khi cần diễn đạt tường minh.
- `@MappedCollection`: cách liên kết collection con với root thông qua cột ID và khóa phần tử.

Không dùng `@OneToMany` hoặc `@ManyToOne` của JPA để giả định Spring Data JDBC có persistence context, proxy lazy hoặc chiến lược cascade tương tự Hibernate.

### 6.1. Enum trạng thái đơn

~~~java
package com.example.shop.order.domain;

public enum OrderStatus {
    DRAFT,
    CONFIRMED,
    CANCELLED
}
~~~

Trong ví dụ này, trạng thái được ánh xạ thành tên enum tương ứng với các giá trị cột `status` trong DDL.

### 6.2. Thành phần OrderLine

~~~java
package com.example.shop.order.domain;

import java.math.BigDecimal;
import java.util.Objects;
import org.springframework.data.relational.core.mapping.Column;
import org.springframework.data.relational.core.mapping.Table;

@Table("sales_order_lines")
public class OrderLine {

    @Column("product_id")
    private Long productId;

    @Column("sku_snapshot")
    private String skuSnapshot;

    private int quantity;

    @Column("unit_price")
    private BigDecimal unitPrice;

    private OrderLine() {
        // Dành cho cơ chế materialization khi đọc từ database.
    }

    public OrderLine(
            Long productId,
            String skuSnapshot,
            int quantity,
            BigDecimal unitPrice
    ) {
        if (productId == null) {
            throw new IllegalArgumentException("Product id is required");
        }
        if (skuSnapshot == null || skuSnapshot.isBlank()) {
            throw new IllegalArgumentException("SKU snapshot is required");
        }
        if (quantity <= 0) {
            throw new IllegalArgumentException("Quantity must be positive");
        }
        Objects.requireNonNull(unitPrice, "Unit price is required");
        if (unitPrice.signum() < 0 || unitPrice.scale() > 2) {
            throw new IllegalArgumentException(
                    "Unit price must be non-negative and have up to 2 decimals"
            );
        }

        this.productId = productId;
        this.skuSnapshot = skuSnapshot;
        this.quantity = quantity;
        this.unitPrice = unitPrice;
    }

    public Long getProductId() {
        return productId;
    }

    public String getSkuSnapshot() {
        return skuSnapshot;
    }

    public int getQuantity() {
        return quantity;
    }

    public BigDecimal getUnitPrice() {
        return unitPrice;
    }

    public BigDecimal lineTotal() {
        return unitPrice.multiply(BigDecimal.valueOf(quantity));
    }

    public OrderLine withQuantity(int newQuantity) {
        return new OrderLine(
                productId, skuSnapshot, newQuantity, unitPrice
        );
    }
}
~~~

Class này không có `@Id` riêng. Trong ví dụ, nó được quản lý như thành phần thuộc `SalesOrder`. Nếu sửa số lượng, root có thể thay thế `OrderLine` tại một vị trí để giữ cho việc kiểm soát bất biến nằm trong phương thức nghiệp vụ của root.

**Lưu ý về tiền tệ:** `NUMERIC(15,2)` được dùng để đơn giản hóa ví dụ. Hệ thống có nhiều loại tiền tệ hoặc quy tắc làm tròn khác nhau nên thiết kế thêm currency và một kiểu dữ liệu/value object cho tiền; không nên tùy tiện mặc định mọi đơn vị tiền đều có hai chữ số thập phân.

### 6.3. Aggregate root SalesOrder

~~~java
package com.example.shop.order.domain;

import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Version;
import org.springframework.data.relational.core.mapping.Column;
import org.springframework.data.relational.core.mapping.MappedCollection;
import org.springframework.data.relational.core.mapping.Table;

@Table("sales_orders")
public class SalesOrder {

    @Id
    private Long id;

    @Version
    private Long version;

    @Column("customer_id")
    private Long customerId;

    private OrderStatus status;

    @MappedCollection(
            idColumn = "order_id",
            keyColumn = "line_no"
    )
    private List<OrderLine> lines = new ArrayList<>();

    private SalesOrder() {
        // Dùng khi Spring Data JDBC dựng aggregate từ dữ liệu lưu trữ.
    }

    public SalesOrder(Long customerId) {
        if (customerId == null) {
            throw new IllegalArgumentException("Customer id is required");
        }
        this.customerId = customerId;
        this.status = OrderStatus.DRAFT;
    }

    public void addLine(
            Long productId,
            String skuSnapshot,
            int quantity,
            BigDecimal unitPrice
    ) {
        requireDraft();
        lines.add(new OrderLine(
                productId, skuSnapshot, quantity, unitPrice
        ));
    }

    public void changeQuantity(int lineIndex, int newQuantity) {
        requireDraft();
        OrderLine current = lines.get(lineIndex);
        lines.set(lineIndex, current.withQuantity(newQuantity));
    }

    public void removeLine(int lineIndex) {
        requireDraft();
        lines.remove(lineIndex);
    }

    public void confirm() {
        requireDraft();
        if (lines.isEmpty()) {
            throw new IllegalStateException(
                    "Cannot confirm an order without lines"
            );
        }
        status = OrderStatus.CONFIRMED;
    }

    public BigDecimal totalAmount() {
        return lines.stream()
                .map(OrderLine::lineTotal)
                .reduce(BigDecimal.ZERO, BigDecimal::add);
    }

    private void requireDraft() {
        if (status != OrderStatus.DRAFT) {
            throw new IllegalStateException(
                    "Only a draft order can be changed"
            );
        }
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

    public List<OrderLine> getLines() {
        return Collections.unmodifiableList(lines);
    }
}
~~~

Hành vi `confirm()` buộc trạng thái của root và các dòng phải nhất quán. `getLines()` trả về danh sách không thể sửa trực tiếp ở bên ngoài; code nghiệp vụ cần gọi phương thức của aggregate.

Chú ý tới `@MappedCollection`:

- `idColumn = "order_id"`: mỗi dòng con lưu ID của `SalesOrder` cha.
- `keyColumn = "line_no"`: cột dùng ghi khóa vị trí cho `List<OrderLine>`.
- `OrderLine` là thành phần **owned** của root, khác với một `Product` độc lập được tham chiếu bằng `productId`.

Trong Spring Data JDBC, collection con thuộc aggregate được tải thông qua thao tác đọc aggregate, không phải proxy lazy kiểu JPA. Khi lưu lại một aggregate đã tồn tại, Spring Data JDBC có thể xóa và tạo lại các dòng con để phản ánh trạng thái collection; nó không dirty-check từng trường của từng entity như JPA. Cần dự kiến chi phí này khi quyết định kích thước aggregate.

### 6.4. Repository chỉ dành cho aggregate root

~~~java
package com.example.shop.order.repository;

import com.example.shop.order.domain.SalesOrder;
import org.springframework.data.repository.CrudRepository;

public interface SalesOrderRepository
        extends CrudRepository<SalesOrder, Long> {
}
~~~

Ta lưu aggregate thông qua root:

~~~java
SalesOrder order = new SalesOrder(customerId);
order.addLine(productId, "SKU-100", 2, new BigDecimal("125.00"));

SalesOrder saved = salesOrderRepository.save(order);
Long orderId = saved.getId();
~~~

Ví dụ trên giả định `customerId` và `productId` đã được xác thực ở tầng ứng dụng. Cần dùng đối tượng mà `save(...)` trả về, nhất là trong các mô hình immutable hoặc có ID/version sinh bởi persistence layer.

Không nên tạo `OrderLineRepository` chỉ để gọi `save(line)` trực tiếp nếu `OrderLine` là thành phần không được thay đổi độc lập. Làm vậy có thể bỏ qua bất biến của root.

## 7. Application service nối các aggregate qua ID

Aggregate root bảo vệ bất biến **nội bộ**. Application service phối hợp các repository và transaction để thực hiện use case.

Repository của sản phẩm có thể được khai báo độc lập:

~~~java
package com.example.shop.catalog.repository;

import com.example.shop.catalog.domain.Product;
import org.springframework.data.repository.CrudRepository;

public interface ProductRepository
        extends CrudRepository<Product, Long> {
}
~~~

Trong ví dụ, `Product` là một aggregate riêng có các getter `getId()`, `getSku()` và `getCurrentPrice()`. Để thêm sản phẩm vào đơn, service đọc giá hiện tại của Product rồi sao chép giá đó sang OrderLine:

~~~java
package com.example.shop.order.service;

import com.example.shop.catalog.domain.Product;
import com.example.shop.catalog.repository.ProductRepository;
import com.example.shop.order.domain.SalesOrder;
import com.example.shop.order.repository.SalesOrderRepository;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderApplicationService {

    private final SalesOrderRepository orderRepository;
    private final ProductRepository productRepository;

    public OrderApplicationService(
            SalesOrderRepository orderRepository,
            ProductRepository productRepository
    ) {
        this.orderRepository = orderRepository;
        this.productRepository = productRepository;
    }

    @Transactional
    public Long createDraft(Long customerId) {
        // Trước đó cần xác thực customerId theo chính sách nghiệp vụ.
        SalesOrder order = new SalesOrder(customerId);
        return orderRepository.save(order).getId();
    }

    @Transactional
    public void addProduct(
            Long orderId,
            Long productId,
            int quantity
    ) {
        Product product = productRepository.findById(productId)
                .orElseThrow(() -> new IllegalArgumentException(
                        "Product not found: " + productId
                ));

        SalesOrder order = orderRepository.findById(orderId)
                .orElseThrow(() -> new IllegalArgumentException(
                        "Order not found: " + orderId
                ));

        order.addLine(
                product.getId(),
                product.getSku(),
                quantity,
                product.getCurrentPrice()
        );
        orderRepository.save(order);
    }

    @Transactional
    public void confirm(Long orderId) {
        SalesOrder order = orderRepository.findById(orderId)
                .orElseThrow(() -> new IllegalArgumentException(
                        "Order not found: " + orderId
                ));

        order.confirm();
        orderRepository.save(order);
    }
}
~~~

Luồng thêm sản phẩm:

~~~text
ApplicationService.addProduct(orderId, productId, quantity)
        |
        +-- ProductRepository.findById(productId)
        |      -> đọc SKU và giá hiện tại
        |
        +-- SalesOrderRepository.findById(orderId)
        |      -> tải root và các thành phần trong aggregate
        |
        +-- SalesOrder.addLine(productId, sku, quantity, price)
        |      -> kiểm tra bất biến nội bộ
        |
        +-- SalesOrderRepository.save(order)
               -> ghi trạng thái aggregate
~~~

Phần đọc `Product` nhằm **lấy thông tin sản phẩm hiện tại**, không đưa Product vào quyền sở hữu của SalesOrder. Sau khi lưu, OrderLine giữ snapshot giá mà đơn hàng đã sử dụng.

### 7.1. Giá thay đổi đồng thời thì xử lý thế nào?

Nếu giá sản phẩm thay đổi sau khi service tải `Product` nhưng trước khi lưu `SalesOrder`, hệ thống cần có chính sách rõ ràng: chấp nhận snapshot giá tại thời điểm đọc, kiểm tra lại ở bước xác nhận, hay dùng phiên bản bảng giá/giá chốt bởi dịch vụ định giá.

Không có một ranh giới aggregate “đúng” duy nhất giải quyết mọi chính sách giá. Điều quan trọng là yêu cầu nghiệp vụ chỉ rõ **thời điểm giá trở thành cam kết** và cơ chế nhất quán phù hợp.

### 7.2. Tồn kho không tự nằm trong đơn hàng

Tồn kho thường thuộc aggregate hoặc service khác. Xác nhận đơn có thể cần giữ tồn kho, đặt trước thanh toán hoặc xử lý từ chối khi hết hàng.

Nếu đơn và tồn kho nằm trong cùng database, application service có thể phối hợp nhiều thao tác repository trong một transaction nếu yêu cầu bảo đảm nguyên tử và cách khóa phù hợp. Nếu các thành phần nằm ở những service/database khác nhau, cần một quy trình có thể phục hồi như reservation, sự kiện và outbox.

**Một transaction có thể chạm nhiều aggregate, nhưng Spring Data JDBC không tự tạo quy trình phối hợp liên aggregate chỉ từ các ID tham chiếu.** Đó vẫn là quyết định kiến trúc dựa trên yêu cầu nghiệp vụ.

## 8. Kiểm soát cập nhật đồng thời bằng @Version

Giả sử hai yêu cầu cùng tải Order #15 khi nó còn ở version cũ:

~~~text
Transaction A            Transaction B
-------------            -------------
Đọc Order #15, v3        Đọc Order #15, v3
Thêm dòng A              Thêm dòng B
save(order) -> thành công
                         save(order) -> xung đột version
~~~

Nếu không có cơ chế ngăn lost update, phiên ghi sau có thể ghi đè trạng thái từ phiên ghi trước. `@Version` trên root cho phép Spring Data JDBC thực hiện **optimistic locking**: thao tác cập nhật chỉ thành công khi version được lưu còn phù hợp; nếu version đã đổi, framework có thể ném lỗi nhóm `OptimisticLockingFailureException`.

Bất biến và version giải quyết hai vấn đề khác nhau:

- Phương thức domain bảo đảm **trạng thái một đơn hợp lệ**.
- Optimistic locking giúp ngăn **hai người cùng sửa một bản cũ mà âm thầm ghi đè lẫn nhau**.

Ứng dụng phải chọn chính sách xử lý xung đột: thông báo người dùng, tải lại và yêu cầu xác nhận, hoặc thử lại khi thao tác an toàn và có thể lặp. Không nên retry mù quáng khi thao tác có tác dụng phụ như gửi thanh toán.

`@Transactional` vẫn có vai trò quản lý transaction và rollback khi cần, dù Spring Data JDBC không có persistence context và dirty checking kiểu JPA. Việc thay đổi một đối tượng Java không tự ghi SQL; service phải gọi `save(...)`.

## 9. Chi phí lưu aggregate và quyết định kích thước

Spring Data JDBC ưu tiên vòng đời nhất quán của aggregate. Khi lưu một aggregate đã tồn tại với tập hợp entity con, framework thường phải thực hiện các thao tác ghi cho phần con như xóa rồi chèn lại để phản ánh trạng thái mới, thay vì theo dõi sự khác biệt của từng trường theo kiểu JPA dirty checking.

Với đơn có 5 dòng, việc ghi lại collection có thể chấp nhận được. Với aggregate gồm 50.000 dòng và mỗi giây thay một dòng, thiết kế này có thể tạo ra nhiều thao tác SQL không cần thiết.

Hãy cân nhắc trước khi đưa một collection vào cùng root:

| Câu hỏi | Nếu câu trả lời là “có” |
|---|---|
| Các phần tử cần được kiểm soát nhất quán cùng root trong một thao tác nghiệp vụ? | Có lý do mạnh để chúng cùng aggregate |
| Các phần tử có vòng đời độc lập, cần được sửa bởi nhiều use case riêng? | Cân nhắc aggregate riêng |
| Số lượng phần tử có thể tăng rất lớn? | Đo chi phí đọc/ghi và xem lại ranh giới |
| Chỉ cần một báo cáo ghép dữ liệu từ nhiều bảng? | Tạo read query/DTO, không nhất thiết gộp aggregate |
| Có hệ thống khác tham chiếu trực tiếp đến từng phần tử? | Cân nhắc ID ổn định và vòng đời độc lập |
| Có cần transaction xuyên nhiều aggregate? | Thiết kế application service và tính nhất quán tường minh |

Ví dụ, một giao dịch ngân hàng nhiều năm lịch sử không nên mặc định chứa mọi bút toán trong một collection con được tải và lưu lại mỗi lần cập nhật số dư. Bản chất nghiệp vụ có thể yêu cầu một mô hình aggregate khác, hoặc một cơ chế append-only riêng.

## 10. Schema phục vụ ghi và query phục vụ đọc

Aggregate quyết định cách **bảo vệ thao tác ghi**, không cấm SQL join khi đọc.

Ví dụ màn hình lịch sử đơn cần ID, trạng thái, số dòng và tổng tiền:

~~~sql
SELECT
    o.id,
    o.customer_id,
    o.status,
    COUNT(l.line_no) AS line_count,
    COALESCE(SUM(l.quantity * l.unit_price), 0) AS total_amount
FROM sales_orders o
LEFT JOIN sales_order_lines l ON l.order_id = o.id
WHERE o.customer_id = :customerId
GROUP BY o.id, o.customer_id, o.status
ORDER BY o.id DESC;
~~~

Có thể dùng `NamedParameterJdbcTemplate` hoặc repository query/DTO phù hợp để lấy báo cáo này, thay vì dựng mọi `SalesOrder` đầy đủ chỉ để hiển thị vài cột.

Đặc biệt, truy vấn đọc có thể join cả `Customer` và `Product` mà **không thay đổi ranh giới aggregate**. Sơ đồ aggregate là mô hình nhất quán của việc ghi; SQL projection là mô hình đọc tối ưu cho tình huống sử dụng.

Trong các hệ thống lớn, thiết kế read model riêng đôi khi hữu ích; ở hệ thống đơn giản, một truy vấn SQL tường minh có thể đã đủ.

## 11. Các quyết định thiết kế dễ sai

### 11.1. “Có foreign key nên phải nằm cùng aggregate”

Sai về cách suy luận. Khóa ngoại `sales_orders.customer_id → customers.id` bảo vệ tính hợp lệ của tham chiếu, nhưng `Customer` vẫn có thể là aggregate độc lập.

Hãy xác định ownership bằng vòng đời và bất biến, không chỉ dựa vào quan hệ bảng.

### 11.2. “Mỗi bảng đều cần repository”

Không cần. `OrderLine` thuộc `SalesOrder` nên thường được thao tác thông qua `SalesOrderRepository`. Tạo CRUD độc lập cho `OrderLine` có thể làm mất quyền kiểm soát của root.

### 11.3. “Một aggregate luôn chỉ có một bảng”

Không đúng. `SalesOrder` và các `OrderLine` thuộc cùng aggregate nhưng được lưu ở hai bảng riêng.

### 11.4. “Mọi đối tượng liên quan đều phải nhúng vào aggregate”

Không. `Product` được nhiều đơn tham chiếu và có vòng đời riêng. Lưu `productId` cùng snapshot lịch sử là lựa chọn tự nhiên hơn việc đưa toàn bộ Product vào SalesOrder.

### 11.5. “Có @Transactional thì sửa object sẽ tự lưu”

Không. Spring Data JDBC không dùng dirty checking kiểu JPA. Sau khi gọi phương thức domain, application service vẫn cần thao tác ghi như `repository.save(order)`.

### 11.6. “save chỉ cập nhật đúng một dòng thay đổi”

Không thể giả định như vậy với collection thuộc aggregate. Phải hiểu chiến lược persistence của Spring Data JDBC và kiểm tra lượng SQL khi chọn kích thước aggregate.

### 11.7. “Mọi thứ phải nhất quán trong cùng một aggregate”

Nếu mở rộng aggregate để bao trùm khách hàng, đơn hàng, sản phẩm, kho và thanh toán, hệ thống có thể trở nên quá khó vận hành. Hãy chỉ giữ những bất biến thực sự cần được kiểm soát cùng root; quy trình liên aggregate được giải quyết bằng transaction hoặc orchestration phù hợp.

### 11.8. “Schema tự thực thi toàn bộ nghiệp vụ”

Ràng buộc SQL bảo vệ tốt `NOT NULL`, `UNIQUE`, `CHECK` và `FOREIGN KEY`. Nhưng những quy tắc phụ thuộc nhiều bản ghi, thời điểm nghiệp vụ hoặc hệ thống khác thường cần logic domain và application layer, đôi khi kèm cơ chế khóa hoặc ràng buộc database nâng cao.

## 12. Một quy trình thiết kế có thể áp dụng cho dự án khác

Khi chuyển một yêu cầu mới thành Spring Data JDBC aggregate, có thể viết tài liệu thiết kế theo khuôn sau:

**Bước 1 — Tóm tắt một tình huống nghiệp vụ.** Nêu ai thực hiện, kết quả cần có và trạng thái nào được phép thay đổi.

**Bước 2 — Liệt kê các bất biến.** Viết thành câu có thể kiểm chứng, ví dụ “Không thể xác nhận phiếu rỗng”, “Tổng tiền bằng tổng các dòng”, “Không sửa phiếu sau khi khóa”.

**Bước 3 — Xác định vòng đời.** Đối tượng nào được tạo/xóa cùng nhau? Đối tượng nào được nhiều quy trình hoặc aggregate khác tham chiếu?

**Bước 4 — Chọn root và các thành phần con.** Root cần cung cấp hành vi nghiệp vụ có chủ đích. Không để code ngoài tự ý sửa collection và trạng thái.

**Bước 5 — Đánh dấu tham chiếu liên aggregate.** Dùng ID thay vì lồng cả domain object. Quyết định có cần snapshot dữ liệu lịch sử hay không.

**Bước 6 — Vẽ sơ đồ aggregate.** Thể hiện ranh giới ownership và đường tham chiếu ID bằng hai kiểu đường khác nhau.

**Bước 7 — Chuyển sang schema.** Chọn bảng, cột, khóa, index, foreign key, delete policy và các constraint có thể đưa xuống database.

**Bước 8 — Ánh xạ Spring Data JDBC.** Dùng `@Id`, `@Table`, `@MappedCollection` và `@Version` khi phù hợp. Repository được tạo cho root.

**Bước 9 — Thiết kế service và transaction.** Service phối hợp các aggregate độc lập; root bảo vệ bất biến nội bộ.

**Bước 10 — Xem xét các kịch bản thay đổi.** Ước lượng số dòng con, tần suất ghi, tranh chấp đồng thời, yêu cầu đọc báo cáo và giới hạn của hệ thống bên ngoài.

Kết quả tối thiểu nên có:

~~~text
Yêu cầu nghiệp vụ
    |
    v
Use case + bất biến
    |
    v
Aggregate boundary
    |       \
    |        \--> Các aggregate khác chỉ tham chiếu bằng ID
    v
Sơ đồ root + owned children
    |
    v
Schema quan hệ + constraints
    |
    v
Spring Data JDBC mapping
    |
    v
Repository + application service + transaction
~~~

## 13. Bài tập suy luận từ một yêu cầu khác

Giả sử hệ thống thư viện có:

- `Book`: thông tin đầu sách, được nhiều chi nhánh sử dụng.
- `LibraryMember`: thông tin độc giả.
- `Loan`: phiếu mượn, gồm các dòng sách mượn và hạn trả.
- Quy tắc: không được xác nhận phiếu trống; sau khi xác nhận, không được tự thay đổi các dòng mượn; trạng thái trả sách có thể cập nhật theo nghiệp vụ.

Hãy tự xác định:

1. Aggregate root nào quản lý các dòng sách mượn?
2. `Book` và `LibraryMember` nên nằm trong cùng aggregate với `Loan` hay nên tham chiếu bằng ID?
3. Các bảng cần khóa chính và khóa ngoại nào?
4. Quy tắc nào nên đưa vào domain method, quy tắc nào đưa vào SQL constraint?
5. Nếu số dòng mượn có thể tăng lên hàng chục nghìn, ranh giới aggregate có còn phù hợp không?

Một phương án xuất phát là `Loan` làm root, các dòng `LoanItem` thuộc root, còn `Book` và `LibraryMember` là aggregate độc lập. Tuy nhiên, việc theo dõi trả sách từng bản sao, chống mượn trùng bản sao hay giới hạn số sách đang mượn có thể dẫn đến những ranh giới aggregate và cơ chế phối hợp khác; cần quay lại **bất biến thực tế** trước khi chốt thiết kế.

## 14. Kết nối các quyết định

Khi thực hiện bài toán bán hàng, chuỗi quyết định có thể được ghi lại:

| Quyết định | Lý do nghiệp vụ | Hệ quả kỹ thuật |
|---|---|---|
| `SalesOrder` là aggregate root | Trạng thái đơn và dòng phải nhất quán | Tạo `SalesOrderRepository` |
| `OrderLine` thuộc `SalesOrder` | Không sống độc lập với đơn | `@MappedCollection`, bảng con có `order_id` |
| `Customer` là aggregate riêng | Hồ sơ khách hàng có vòng đời độc lập | Lưu `customerId`, có thể dùng foreign key |
| `Product` là aggregate riêng | Giá/danh mục được quản lý độc lập | Lưu `productId` và snapshot giá |
| Giá đơn được chốt vào từng dòng | Giá danh mục thay đổi không làm đổi lịch sử | Cột `unit_price` trong bảng dòng |
| `@Version` trên root | Tránh lost update khi cùng sửa đơn | Cột `version` và xử lý optimistic locking |
| Tổng tiền suy ra từ dòng | Tránh lệch dữ liệu tính sẵn | Tính trong domain hoặc SQL projection |
| Query báo cáo độc lập | Màn hình không cần tải mọi chi tiết aggregate | SQL join/DTO dành cho đọc |

**Tư duy cốt lõi:** xuất phát từ thao tác nghiệp vụ và bất biến, chọn root cùng thành phần con, giữ aggregate khác ở dạng tham chiếu ID, rồi mới vẽ ERD và viết mapping. Với Spring Data JDBC, cách tiếp cận này khớp với cơ chế lưu theo aggregate, khiến ranh giới nhất quán rõ ràng và chi phí đọc/ghi dễ dự đoán hơn.
