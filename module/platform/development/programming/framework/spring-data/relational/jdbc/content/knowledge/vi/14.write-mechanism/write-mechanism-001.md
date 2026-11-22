# Luồng insert aggregate root rồi ghi entity con

Trong Spring Data Relational JDBC, một **aggregate** được lưu thông qua aggregate root. Khi ứng dụng tạo một đơn hàng mới gồm thông tin chung và nhiều dòng hàng, Spring Data JDBC ghi hàng của root trước, lấy định danh của root, rồi sử dụng định danh đó để ghi các entity con vào bảng tương ứng.

Thứ tự này bảo đảm cột khóa ngoại ở bảng con có thể tham chiếu tới hàng cha đã tồn tại. Nó cũng thể hiện ranh giới aggregate: ứng dụng gửi một thao tác lưu trên root, còn Spring Data JDBC điều phối việc ghi các thành phần thuộc aggregate.

Bài học đi theo luồng insert của một aggregate mới, từ object Java đến các câu SQL khái niệm, giải thích cách ID được truyền xuống entity con, vai trò của `@MappedCollection`, transaction và cách xử lý lỗi khi một phần dữ liệu không thể insert.

## 1. Aggregate root và entity con

Giả sử ứng dụng bán hàng có một đơn hàng gồm thông tin chung và nhiều dòng hàng:

- `PurchaseOrder` là **aggregate root**, đại diện cho đơn hàng và là điểm truy cập để lưu aggregate.
- `OrderLine` là entity con thuộc vòng đời của đơn hàng.
- Một đơn hàng có thể chứa nhiều dòng hàng.
- Mỗi dòng hàng phải tham chiếu tới đúng đơn hàng sở hữu nó.

Mô hình quan hệ:

~~~mermaid
erDiagram
    PURCHASE_ORDERS ||--o{ ORDER_LINES : contains
    PURCHASE_ORDERS {
        bigint id PK
        bigint customer_id
        varchar status
    }
    ORDER_LINES {
        bigint id PK
        bigint order_id FK
        integer line_no
        varchar sku
        integer quantity
    }
~~~

Bảng `purchase_orders` chứa một hàng cho mỗi đơn hàng. Bảng `order_lines` chứa nhiều hàng, mỗi hàng là một dòng hàng. Cột `order_lines.order_id` là khóa ngoại trỏ tới `purchase_orders.id`.

Trong Spring Data JDBC, aggregate root là đối tượng mà repository lưu. Entity con được khai báo qua mapping trong aggregate, không cần tạo repository độc lập chỉ để lưu từng dòng hàng thuộc đơn.

### Aggregate root không đồng nghĩa với bảng cha trong mọi mô hình

Aggregate là ranh giới nhất quán trong mô hình miền nghiệp vụ. Trong ví dụ này nó tương ứng với một bảng root và một bảng child. Một aggregate cũng có thể có embedded value object được lưu trong cùng hàng root, nhiều loại entity con ở các bảng khác nhau hoặc entity con lồng nhau, miễn là chúng thuộc cùng ranh giới aggregate.

Một aggregate khác như `Customer` có vòng đời độc lập. Đơn hàng có thể lưu ID khách hàng để tham chiếu, nhưng thao tác lưu đơn hàng không tự động insert hoặc cập nhật aggregate khách hàng.

## 2. Mapping root và child bằng Spring Data JDBC

Aggregate root dùng `@Table` để chỉ định bảng và `@Id` để đánh dấu định danh. Collection entity con dùng `@MappedCollection` để chỉ ra cột khóa ngoại trong bảng con.

### 2.1. Entity con

~~~java
import java.math.BigDecimal;

import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Column;
import org.springframework.data.relational.core.mapping.Table;

@Table("order_lines")
public class OrderLine {

    @Id
    private Long id;

    @Column("sku")
    private String sku;

    @Column("quantity")
    private int quantity;

    @Column("unit_price")
    private BigDecimal unitPrice;

    protected OrderLine() {
    }

    public OrderLine(String sku, int quantity, BigDecimal unitPrice) {
        if (sku == null || sku.isBlank()) {
            throw new IllegalArgumentException("sku must not be blank");
        }
        if (quantity <= 0) {
            throw new IllegalArgumentException("quantity must be positive");
        }
        if (unitPrice == null || unitPrice.signum() < 0) {
            throw new IllegalArgumentException("unitPrice must be non-negative");
        }

        this.sku = sku;
        this.quantity = quantity;
        this.unitPrice = unitPrice;
    }

    public Long getId() {
        return id;
    }

    public String getSku() {
        return sku;
    }
}
~~~

`OrderLine.id` là định danh riêng của hàng dòng hàng. Nó không phải khóa ngoại trỏ tới đơn hàng. Khóa ngoại của child được Spring Data JDBC quản lý qua mapping collection.

### 2.2. Aggregate root

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Column;
import org.springframework.data.relational.core.mapping.MappedCollection;
import org.springframework.data.relational.core.mapping.Table;

@Table("purchase_orders")
public class PurchaseOrder {

    @Id
    private Long id;

    @Column("customer_id")
    private Long customerId;

    private String status;

    @MappedCollection(idColumn = "order_id", keyColumn = "line_no")
    private List<OrderLine> lines = new ArrayList<>();

    protected PurchaseOrder() {
    }

    public PurchaseOrder(Long customerId, List<OrderLine> lines) {
        this.customerId = Objects.requireNonNull(customerId);
        this.status = "NEW";
        this.lines = new ArrayList<>(Objects.requireNonNull(lines));

        if (this.lines.isEmpty()) {
            throw new IllegalArgumentException("An order needs at least one line");
        }
    }

    public void addLine(OrderLine line) {
        lines.add(Objects.requireNonNull(line));
    }

    public Long getId() {
        return id;
    }

    public List<OrderLine> getLines() {
        return List.copyOf(lines);
    }
}
~~~

Các chi tiết quan trọng:

- `@Id` trên `PurchaseOrder.id` đánh dấu định danh của root.
- `@MappedCollection(idColumn = "order_id")` chỉ ra cột trong bảng con chứa ID của root.
- `keyColumn = "line_no"` chỉ ra cột lưu vị trí phần tử trong `List`.
- `OrderLine` không cần khai báo một trường Java `orderId` chỉ để lặp lại back reference mà mapping collection đã quản lý.
- `PurchaseOrderRepository` là điểm lưu aggregate.

`idColumn` là tên cột **ở bảng con**, không phải tên thuộc tính Java của root. Với mapping trên, mỗi dòng hàng được ghi vào `order_lines` và có `order_id` bằng ID của `purchase_orders`.

Nếu dùng `Set<OrderLine>` thay vì `List<OrderLine>`, không có vị trí phần tử ổn định như danh sách. Nếu dùng `Map<K, OrderLine>`, key column lưu khóa map. Hãy chọn collection theo ý nghĩa nghiệp vụ và thiết kế schema tương ứng.

## 3. Schema quan hệ phải có trước

Spring Data JDBC ánh xạ object sang schema, không tự động tạo bảng hoặc constraint chỉ vì entity có annotation. Dùng migration (Flyway, Liquibase hoặc công cụ quản trị schema của dự án) để tạo các bảng và khóa ngoại.

Ví dụ PostgreSQL:

~~~sql
CREATE TABLE purchase_orders (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    customer_id BIGINT NOT NULL,
    status VARCHAR(30) NOT NULL
);

CREATE TABLE order_lines (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    order_id BIGINT NOT NULL,
    line_no INTEGER NOT NULL,
    sku VARCHAR(80) NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    unit_price NUMERIC(19, 4) NOT NULL CHECK (unit_price >= 0),

    CONSTRAINT fk_order_lines_order
        FOREIGN KEY (order_id)
        REFERENCES purchase_orders(id),

    CONSTRAINT uq_order_lines_position
        UNIQUE (order_id, line_no)
);
~~~

Ở đây:

- Root có khóa chính tự sinh.
- Child có khóa chính riêng tự sinh.
- `order_lines.order_id` là khóa ngoại tới root.
- `line_no` lưu thứ tự của phần tử trong `List`.
- `UNIQUE(order_id, line_no)` ngăn hai dòng cùng vị trí trong một đơn hàng.
- `CHECK(quantity > 0)` bảo vệ quy tắc số lượng ở database.

Tên bảng/cột phải khớp với mapping của Spring Data JDBC, bao gồm naming strategy và quy tắc quote identifier nếu dự án có cấu hình riêng.

### Vì sao cần cột khóa ngoại ở bảng con?

Một hàng `order_lines` phải xác định được nó thuộc đơn hàng nào. Khi root được insert, database sinh ID. Child insert sau đó ghi ID này vào `order_id`.

Nếu không có khóa ngoại, ứng dụng có thể tạo một dòng hàng trỏ tới đơn hàng không tồn tại. Constraint SQL là lớp bảo vệ cuối cùng, kể cả khi dữ liệu được ghi qua một công cụ ngoài Spring Data JDBC.

### Vì sao cột vị trí là một phần của schema?

`List` có thứ tự. Nếu muốn thứ tự đó được lưu và khôi phục, bảng con cần một cột key/index, ví dụ `line_no`. Constraint duy nhất trên cặp `(order_id, line_no)` bảo đảm một vị trí không bị lặp trong cùng đơn hàng.

Không nên đặt `UNIQUE(line_no)` đơn lẻ: khi đó hai đơn hàng khác nhau không thể cùng có dòng ở vị trí 0, dù đó là điều hoàn toàn hợp lệ.

## 4. Luồng insert tổng quát: root trước, child sau

Khi repository lưu một aggregate mới, trình tự khái niệm là:

1. Spring Data JDBC nhận aggregate root.
2. Framework xác định aggregate là mới dựa trên metadata định danh/version hoặc chiến lược newness.
3. Framework tạo lệnh insert cho bảng root.
4. Database insert root và sinh ID nếu dùng cơ chế tự sinh.
5. Spring Data JDBC nhận giá trị ID được sinh và cập nhật/đưa giá trị đó vào quá trình ghi aggregate.
6. Framework insert các entity con, đặt cột back reference bằng ID của root.
7. Các entity con lồng nhau tiếp tục được ghi theo cấu trúc quan hệ và thứ tự phụ thuộc khóa ngoại.
8. Giao dịch hoàn tất bằng commit nếu mọi thao tác thành công.

~~~mermaid
sequenceDiagram
    participant App as Application Service
    participant Repo as PurchaseOrderRepository
    participant SD as Spring Data JDBC
    participant DB as Database

    App->>Repo: save(newOrder)
    Repo->>SD: persist aggregate
    SD->>DB: INSERT purchase_orders
    DB-->>SD: generated order id
    SD->>SD: associate generated id with aggregate
    loop each OrderLine
        SD->>DB: INSERT order_lines(order_id, line_no, ...)
        DB-->>SD: child result / generated child id
    end
    SD-->>Repo: saved aggregate
    Repo-->>App: savedOrder
~~~

Root-first có ý nghĩa trực tiếp với khóa ngoại: child chỉ có thể tham chiếu tới root sau khi root đã được tạo. Spring Data JDBC không yêu cầu ứng dụng tự insert root, lấy ID rồi gọi repository child theo từng bước thủ công; framework điều phối việc lưu thành phần thuộc aggregate.

### SQL khái niệm được thực thi

Câu lệnh cụ thể phụ thuộc database dialect, cách sinh khóa và phiên bản framework. Về mặt logic, nó tương đương:

~~~sql
INSERT INTO purchase_orders (customer_id, status)
VALUES (42, 'NEW')
RETURNING id;
~~~

Giả sử database trả về ID đơn hàng là `9001`, các dòng hàng tiếp theo có dạng:

~~~sql
INSERT INTO order_lines
    (order_id, line_no, sku, quantity, unit_price)
VALUES
    (9001, 0, 'BOOK-01', 2, 120000.00);

INSERT INTO order_lines
    (order_id, line_no, sku, quantity, unit_price)
VALUES
    (9001, 1, 'PEN-02', 3, 15000.00);
~~~

`9001` chỉ là ID minh họa. Ứng dụng không được đoán ID hoặc tự gán giá trị giả định cho child. ID thực tế đến từ database trong lần insert root.

Một số database/driver sử dụng cơ chế lấy generated keys khác với cú pháp `RETURNING`. Vì vậy, không nên kết luận log SQL của mọi hệ quản trị đều phải giống ví dụ PostgreSQL.

## 5. ID của root được truyền xuống child như thế nào?

Với root dùng ID tự sinh, trước khi insert, thuộc tính ID của object mới thường chưa có giá trị:

~~~java
PurchaseOrder order = new PurchaseOrder(customerId, lines);

assert order.getId() == null;
~~~

Khi root insert thành công, database trả lại ID. Spring Data JDBC dùng ID đó làm giá trị cột back reference cho các child trong aggregate.

~~~text
Trước khi insert:

PurchaseOrder.id = null
  ├── OrderLine[0]
  └── OrderLine[1]

Sau khi insert root, database trả id = 9001:

PurchaseOrder.id = 9001
  ├── OrderLine[0] -> order_id = 9001
  └── OrderLine[1] -> order_id = 9001
~~~

Khóa ngoại child lấy ID của root, không lấy ID riêng của child. Mỗi child có thể có ID riêng do bảng `order_lines` sinh ra.

### ID tự sinh và ID được gán trước

Có hai trường hợp phổ biến:

| Cách định danh root | Trước khi lưu | Luồng insert |
| --- | --- | --- |
| Database-generated ID | Thường là null với kiểu wrapper như Long | Insert root, lấy ID, rồi insert child |
| Application-assigned ID | Đã có ID hợp lệ | Insert root với ID đã cấp, rồi insert child dùng ID đó |

Ví dụ ID do ứng dụng cấp:

~~~java
PurchaseOrder order = new PurchaseOrder(9001L, customerId, lines);
repository.save(order);
~~~

Constructor và chiến lược newness phải phù hợp với ID được gán trước. Spring Data JDBC cần biết aggregate là mới hay đã tồn tại; không nên chỉ đổi ID từ null sang một giá trị bất kỳ mà không hiểu quy tắc xác định trạng thái mới của entity.

Với kiểu wrapper như `Long`, null thường là dấu hiệu thuận tiện cho ID chưa được sinh. Với kiểu nguyên thủy `long`, giá trị mặc định là 0, vì vậy phải hiểu cách framework nhận diện trạng thái mới và cân nhắc `@Version` hoặc `Persistable` khi chiến lược ID yêu cầu.

### Dùng aggregate được trả về từ save

Nên dùng giá trị trả về từ repository:

~~~java
PurchaseOrder saved = repository.save(order);

Long orderId = saved.getId();
~~~

Với entity bất biến hoặc mapping dùng constructor/property accessor để tạo instance mới, framework có thể trả về một instance chứa ID được sinh thay vì sửa object ban đầu tại chỗ. Vì vậy, đừng mặc định biến `order` ban đầu luôn được cập nhật ID trong mọi mô hình.

## 6. Repository chỉ lưu aggregate root

Repository có thể được khai báo đơn giản:

~~~java
import org.springframework.data.repository.CrudRepository;

public interface PurchaseOrderRepository
        extends CrudRepository<PurchaseOrder, Long> {
}
~~~

Service tạo root và child rồi gọi một lần `save`:

~~~java
import java.math.BigDecimal;
import java.util.List;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderApplicationService {

    private final PurchaseOrderRepository orders;

    public OrderApplicationService(PurchaseOrderRepository orders) {
        this.orders = orders;
    }

    @Transactional
    public Long placeOrder(Long customerId) {
        List<OrderLine> lines = List.of(
            new OrderLine("BOOK-01", 2, new BigDecimal("120000.00")),
            new OrderLine("PEN-02", 3, new BigDecimal("15000.00"))
        );

        PurchaseOrder order = new PurchaseOrder(customerId, lines);
        PurchaseOrder saved = orders.save(order);

        return saved.getId();
    }
}
~~~

Một thao tác nghiệp vụ tạo đơn hàng chỉ cần lưu aggregate root. Spring Data JDBC chịu trách nhiệm ghi các entity con đã được khai báo trong aggregate.

Không cần làm theo cách thủ công: insert root trước, lấy ID, rồi gọi một repository khác cho từng child. Cách đó tách việc ghi child khỏi aggregate, làm lộ khóa ngoại và khiến ứng dụng tự quản lý thứ tự/transaction. Nó cũng không còn phản ánh đúng ý nghĩa rằng các dòng hàng thuộc vòng đời của đơn hàng. Chỉ dùng repository riêng cho child khi mô hình thực sự xác định child là một aggregate root độc lập.

### Không tự động insert aggregate khác

Giả sử `PurchaseOrder` có `customerId` hoặc `AggregateReference<Customer, Long>`. Đây là tham chiếu tới aggregate khách hàng riêng. Khi lưu đơn hàng:

- Spring Data JDBC dùng ID khách hàng để ghi cột `customer_id`.
- Nó không tự insert `Customer` nếu ID đó chưa tồn tại.
- Nếu database có foreign key, một ID khách hàng không tồn tại sẽ khiến insert root bị từ chối.
- Việc tạo khách hàng là một thao tác riêng theo ranh giới aggregate và nghiệp vụ.

Điều này khác với `OrderLine` được khai báo là entity con trong `@MappedCollection`.

## 7. @MappedCollection quyết định cột liên kết

`@MappedCollection` mô tả cách collection entity con được lưu trong bảng khác:

~~~java
@MappedCollection(
    idColumn = "order_id",
    keyColumn = "line_no"
)
private List<OrderLine> lines;
~~~

Hai thuộc tính có ý nghĩa khác nhau:

- `idColumn`: tên cột trong bảng con chứa ID của aggregate root.
- `keyColumn`: tên cột chứa key của collection; với `List`, đó là vị trí phần tử.

Ví dụ bảng con:

~~~sql
CREATE TABLE order_lines (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    order_id BIGINT NOT NULL REFERENCES purchase_orders(id),
    line_no INTEGER NOT NULL,
    sku VARCHAR(80) NOT NULL,
    quantity INTEGER NOT NULL
);
~~~

Trong class `OrderLine`, không nhất thiết phải có trường `orderId`. Spring Data JDBC biết cột liên kết thông qua mapping collection của root.

### Collection List

Với `List`, thứ tự phần tử có ý nghĩa:

~~~java
List<OrderLine> lines = List.of(
    new OrderLine("A", 1, new BigDecimal("10.00")),
    new OrderLine("B", 2, new BigDecimal("20.00"))
);
~~~

Framework lưu key/index tương ứng trong cột `line_no`. Khi đọc aggregate, các phần tử được dựng lại theo key của collection.

Nếu thứ tự nghiệp vụ cần ổn định, schema nên bảo vệ cặp `(order_id, line_no)` bằng unique constraint. Nếu thứ tự chỉ mang tính trình bày tạm thời, cần quyết định có lưu nó hay không.

### Collection Set và Map

`Set` không biểu diễn vị trí như `List`. Nếu thứ tự không có ý nghĩa, dùng Set có thể phù hợp. Equality/hashCode của child cần được thiết kế cẩn thận, nhất là khi entity có ID do database sinh và ID chỉ có sau insert.

Với `Map<K, OrderLine>`, key column lưu khóa map. Kiểu khóa phải có thể ánh xạ sang kiểu SQL phù hợp. Hãy khai báo `keyColumn` tường minh khi schema có tên cột nghiệp vụ cụ thể.

## 8. Root có embedded value object và entity con

Một aggregate có thể chứa cả embedded object và child entity:

~~~java
@Table("purchase_orders")
public class PurchaseOrder {

    @Id
    private Long id;

    @Embedded(prefix = "shipping_")
    private Address shippingAddress;

    @MappedCollection(idColumn = "order_id", keyColumn = "line_no")
    private List<OrderLine> lines = new ArrayList<>();
}
~~~

Luồng ghi có hai loại dữ liệu:

- Các thuộc tính của `Address` được ghi vào các cột `shipping_*` trong hàng root.
- Các `OrderLine` được ghi thành những hàng riêng trong bảng `order_lines`, với `order_id` trỏ tới root.

Không có insert riêng cho `Address` vì nó không phải entity con ở bảng khác. Đây là khác biệt quan trọng khi đọc SQL log: số lượng câu insert phụ thuộc cấu trúc aggregate và các loại mapping.

## 9. Transaction bảo vệ toàn bộ luồng ghi

Một thao tác lưu aggregate có thể thực thi nhiều câu SQL:

1. Insert root.
2. Insert child thứ nhất.
3. Insert child thứ hai.
4. Insert các entity con lồng nhau nếu có.

Các thao tác ghi của repository được quản lý trong transaction theo cấu hình Spring Data JDBC; service có thể dùng `@Transactional` để mở rộng ranh giới cho nhiều thao tác nghiệp vụ.

Ví dụ:

~~~java
@Transactional
public Long placeOrder(Long customerId) {
    PurchaseOrder order = buildOrder(customerId);
    PurchaseOrder saved = orders.save(order);

    auditRepository.save(
        OrderAudit.created(saved.getId())
    );

    return saved.getId();
}
~~~

Đoạn này giả định audit được ghi vào cùng database và cùng transaction manager. Nếu cả lưu đơn hàng và ghi audit thuộc cùng một transaction, lỗi ở bước audit có thể rollback cả đơn hàng.

### Nếu một child insert bị lỗi thì sao?

Giả sử dòng hàng thứ hai vi phạm unique constraint hoặc check constraint. Nếu cả luồng nằm trong transaction:

- Database từ chối insert thứ hai.
- Exception được chuyển qua lớp Spring JDBC/Spring Data.
- Transaction manager rollback transaction.
- Hàng root và child đã insert trước đó trong cùng transaction cũng được rollback.

Nếu code bắt exception rồi nuốt lỗi bên trong một transaction mà không đánh dấu rollback, ứng dụng có thể khiến transaction commit trong tình trạng không như dự định. Hãy để lỗi truyền ra hoặc đánh dấu rollback theo quy tắc phù hợp.

### Cùng một DataSource và transaction manager

Để các thao tác cùng tham gia transaction:

- Repository và JDBC operations cần dùng cùng DataSource.
- Transaction manager phải quản lý DataSource đó.
- Lời gọi cần nằm trong cùng ngữ cảnh transaction Spring.
- Không tự mở connection độc lập bằng `DriverManager` rồi commit riêng.

Một transaction JDBC thông thường gắn với luồng thực thi. Chuyển việc ghi child sang luồng bất đồng bộ không tự động truyền transaction của luồng gọi.

## 10. Thứ tự insert và constraint khóa ngoại

Vì child tham chiếu root, thứ tự insert là root trước rồi child sau. Nếu cố insert child trước với một `order_id` chưa tồn tại, database từ chối do foreign key.

~~~sql
-- Không hợp lệ nếu order_id 9001 chưa tồn tại.
INSERT INTO order_lines(order_id, line_no, sku, quantity, unit_price)
VALUES (9001, 0, 'BOOK-01', 2, 120000.00);
~~~

Sau khi root được insert:

~~~sql
INSERT INTO purchase_orders(customer_id, status)
VALUES (42, 'NEW')
RETURNING id;
~~~

và database trả ID hợp lệ, các insert child mới có thể tham chiếu tới ID đó.

Không nên tắt foreign key hoặc trì hoãn constraint chỉ để cho phép sai thứ tự insert. Spring Data JDBC đã tổ chức luồng ghi theo quan hệ aggregate; schema cần phản ánh đúng quan hệ này.

### Nhiều tầng entity con

Giả sử aggregate có root, order line và một tập thuộc tính con của từng dòng:

~~~mermaid
flowchart TD
    A["PurchaseOrder"] --> B["OrderLine 1"]
    A --> C["OrderLine 2"]
    B --> D["LineAdjustment 1"]
    B --> E["LineAdjustment 2"]
    C --> F["LineAdjustment 3"]
~~~

Mỗi tầng có bảng và cột back reference riêng. Hàng cha của một entity con phải được tạo trước khi ghi những hàng phụ thuộc vào nó. Khi thiết kế nhiều tầng, cần xác định rõ aggregate boundary, khóa ngoại và các mapping collection; đừng mô hình hóa mọi liên kết object thành một aggregate lồng nhau nếu chúng có vòng đời độc lập.

## 11. Generated ID của child

Child có thể có ID riêng:

~~~java
@Id
private Long id;
~~~

Nếu schema khai báo ID tự sinh, mỗi child insert có thể nhận một ID từ database. ID này khác với `order_id`:

| Cột | Ý nghĩa |
| --- | --- |
| `order_lines.id` | Định danh của dòng hàng |
| `order_lines.order_id` | ID của đơn hàng sở hữu dòng hàng |
| `order_lines.line_no` | Vị trí dòng hàng trong List |

Một hàng child có thể có:

~~~text
id = 501
order_id = 9001
line_no = 0
sku = BOOK-01
~~~

`501` là ID riêng của dòng hàng; `9001` là ID root. Không nhầm hai giá trị này chỉ vì chúng đều là số.

Không phải mọi entity con đều bắt buộc có một ID nghiệp vụ riêng. Tùy mô hình và mapping, có thể dùng khóa khác hoặc tổ hợp cột phù hợp. Dù chọn cấu trúc nào, phải đảm bảo hàng child được nhận diện và cập nhật/xóa theo cách tương thích với Spring Data JDBC và schema.

## 12. Những điều luồng insert không làm

| Giả định | Thực tế |
| --- | --- |
| Gọi `save(root)` chỉ insert một hàng | Nếu aggregate có child, framework còn ghi các entity con thuộc aggregate |
| Spring Data JDBC tự tạo bảng và FK | Schema cần được tạo bằng migration/công cụ quản lý schema |
| Child tự biết ID root qua một field bắt buộc | Mapping collection cung cấp back reference qua `idColumn` |
| Root save tự insert Customer được tham chiếu | Aggregate khác có vòng đời riêng; tham chiếu chỉ dùng ID |
| `@MappedCollection` giống `@OneToMany` của JPA | Đây là mapping của Spring Data JDBC với semantics aggregate riêng |
| `@Embedded Address` được insert vào bảng addresses | Embedded fields nằm trong hàng root |
| ID sinh luôn sửa object ban đầu | Nên dùng aggregate được trả về từ `save`, nhất là với object bất biến |
| Bắt mọi exception rồi tiếp tục là an toàn | Có thể làm transaction commit sai nếu không rollback |
| Tắt FK giúp insert dễ hơn | Làm mất lớp bảo vệ toàn vẹn dữ liệu |

Spring Data JDBC không phải ORM có persistence context theo kiểu JPA. Nó lưu aggregate qua repository theo mô hình aggregate, không theo dõi mọi object tùy ý trong toàn bộ ứng dụng.

## 13. Xử lý lỗi và quan sát luồng insert

Một số lỗi thường gặp:

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| Root insert thành công nhưng child không được ghi | Child không được khai báo là property persistent/collection mapping | Kiểm tra `@MappedCollection` và kiểu thuộc tính |
| Child insert báo FK violation | Cột `idColumn` sai, root ID không hợp lệ hoặc schema FK sai | So khớp mapping và DDL |
| Child bị ghi vào sai cột back reference | Tên `idColumn` không khớp schema | Khai báo `idColumn` tường minh |
| Thứ tự List bị mất | Thiếu hoặc mapping sai `keyColumn` | Dùng cột key/index phù hợp |
| Hai child cùng vị trí | Key column không unique theo root | Tạo `UNIQUE(root_id, key)` |
| Insert root bị lỗi unique | Dữ liệu root vi phạm constraint | Xử lý dữ liệu và chuyển lỗi nghiệp vụ phù hợp |
| Lưu child lỗi nhưng root còn lại | Thao tác nằm ngoài transaction chung hoặc có connection độc lập | Kiểm tra transaction manager/DataSource |
| Không thấy ID trong object ban đầu | Entity immutable hoặc save trả về instance mới | Dùng object được trả về từ `save` |
| Repository không tìm thấy bảng/cột | Mapping tên không khớp migration | Kiểm tra `@Table`, `@Column`, NamingStrategy và schema |

### Quan sát SQL ở môi trường phát triển

Có thể bật logging Spring JDBC khi dùng Spring Boot:

~~~yaml
logging:
  level:
    org.springframework.jdbc.core: DEBUG
~~~

Log giúp xác nhận:

- Root insert được thực thi trước.
- Giá trị ID root được dùng cho các child insert.
- Tên bảng/cột khớp schema.
- Các tham số bind có giá trị dự kiến.

Log SQL có thể chứa dữ liệu nhạy cảm trong tham số. Chỉ bật mức chi tiết phù hợp trong môi trường phát triển và kiểm soát việc ghi log trong production.

### Kiểm tra dữ liệu sau insert

Với PostgreSQL:

~~~sql
SELECT id, customer_id, status
FROM purchase_orders
ORDER BY id DESC
LIMIT 5;

SELECT id, order_id, line_no, sku, quantity
FROM order_lines
WHERE order_id = 9001
ORDER BY line_no;
~~~

Thay `9001` bằng ID thật trả về từ repository. Truy vấn này giúp xác nhận root và các child cùng thuộc một aggregate.

## 14. Thiết kế service và transaction hợp lý

Một service nên đặt transaction ở ranh giới nghiệp vụ, ví dụ tạo đơn hàng:

~~~java
@Service
public class OrderApplicationService {

    private final PurchaseOrderRepository orders;

    public OrderApplicationService(PurchaseOrderRepository orders) {
        this.orders = orders;
    }

    @Transactional
    public Long createOrder(CreateOrderCommand command) {
        List<OrderLine> lines = command.lines().stream()
            .map(line -> new OrderLine(
                line.sku(),
                line.quantity(),
                line.unitPrice()
            ))
            .toList();

        PurchaseOrder order = new PurchaseOrder(
            command.customerId(),
            lines
        );

        return orders.save(order).getId();
    }
}
~~~

Transaction giúp thao tác tạo aggregate hoàn tất như một đơn vị. Service cũng là nơi phù hợp để kiểm tra quy tắc nghiệp vụ xuyên qua nhiều dữ liệu, nhưng các constraint quan trọng như FK, unique và check vẫn phải được bảo vệ ở database.

Nếu service cần thêm một thao tác khác như ghi outbox trong cùng database, có thể đặt thao tác đó trong cùng transaction. Nếu gửi email hoặc gọi API bên ngoài, không nên giả định transaction JDBC có thể rollback side effect bên ngoài. Với sự kiện cần phát đi sau commit, hãy cân nhắc transactional outbox hoặc cơ chế after-commit phù hợp.

### Tránh chia nhỏ thao tác lưu aggregate

Nếu mỗi dòng hàng được lưu bằng một repository độc lập, ứng dụng phải tự đảm bảo:

- Root đã tồn tại.
- ID root được truyền đúng.
- Tất cả child cùng transaction.
- Vị trí collection không bị trùng.
- Khi một child lỗi, các thao tác trước đó rollback.

Lưu qua root giúp Spring Data JDBC giữ trách nhiệm điều phối trong một nơi. Tách child ra khỏi aggregate chỉ khi mô hình miền nghiệp vụ thực sự yêu cầu child có vòng đời độc lập.

## 15. Bài tập tự thực hành

### Bài 1 — Quan sát thứ tự SQL

Tạo aggregate `PurchaseOrder` với hai `OrderLine`. Bật SQL logging, gọi repository `save` một lần. Ghi lại thứ tự các câu insert và giải thích vì sao root phải được insert trước child.

### Bài 2 — Theo dõi ID được sinh

Để `PurchaseOrder.id` null trước khi save. Sau khi save, kiểm tra ID trong object trả về và các giá trị `order_id` ở bảng `order_lines`. Giải thích vì sao không được hardcode ID.

### Bài 3 — Thay đổi cột back reference

Đổi `@MappedCollection(idColumn = "order_id")` thành một tên khác nhưng không đổi schema. Quan sát lỗi. Sau đó cập nhật migration và giải thích quan hệ giữa annotation với cột vật lý.

### Bài 4 — List và key column

Dùng `List<OrderLine>` với `keyColumn = "line_no"`. Lưu ba dòng hàng, đọc lại aggregate và xác nhận thứ tự. Thử tạo unique constraint trên `(order_id, line_no)` rồi thử insert thủ công hai dòng cùng vị trí.

### Bài 5 — Transaction rollback

Tạo constraint khiến child thứ hai vi phạm (ví dụ quantity phải lớn hơn 0). Xác nhận repository save thất bại và không còn hàng root/child nào được commit trong transaction. Thực hiện trong database thử nghiệm.

### Bài 6 — Aggregate reference

Thêm `customerId` vào root và tạo FK tới bảng customers. Thử lưu đơn hàng với ID khách hàng không tồn tại. Giải thích vì sao Spring Data JDBC không tự tạo Customer khi lưu PurchaseOrder.

### Bài 7 — Embedded và child table

Thêm `Address` embedded vào root cùng với `List<OrderLine>`. Quan sát số lượng bảng/câu insert và phân biệt dữ liệu nào nằm trong hàng root, dữ liệu nào được insert thành hàng riêng.

## 16. Tài liệu tham khảo chính thức

- [Spring Data Relational — JDBC Mapping](https://docs.spring.io/spring-data/relational/reference/jdbc/mapping.html): mapping aggregate, entity references và collection.
- [Spring Data Relational — JDBC Repositories](https://docs.spring.io/spring-data/relational/reference/jdbc/repositories.html): cách repository lưu aggregate.
- [Spring Data Relational — Object Mapping](https://docs.spring.io/spring-data/relational/reference/object-mapping.html): cách Spring Data tạo object và quản lý metadata mapping.
- [Spring Data Relational — `@MappedCollection` API](https://docs.spring.io/spring-data/relational/reference/api/java/org/springframework/data/relational/core/mapping/MappedCollection.html): khai báo cột ID liên kết và key column cho collection.
- [Spring Framework — Declarative Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative.html): ranh giới và hành vi transaction của `@Transactional`.

Luồng insert root trước rồi ghi entity con là cách Spring Data JDBC duy trì quan hệ aggregate: root được tạo để có ID, ID đó trở thành khóa ngoại của các child, và toàn bộ thao tác được thực hiện trong transaction phù hợp. Khi mapping collection, schema FK và ranh giới transaction được thiết kế nhất quán, ứng dụng có thể lưu một aggregate bằng một lời gọi repository mà vẫn bảo vệ được tính toàn vẹn của dữ liệu.
