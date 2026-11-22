# Tham chiếu bằng ID thay vì nhúng toàn bộ aggregate khác

Trong **Spring Data Relational JDBC**, aggregate là ranh giới nhất quán mà ứng dụng tải, thay đổi và lưu như một đơn vị. Khi một aggregate cần liên hệ với aggregate khác, cách thiết kế thông thường là giữ **ID của aggregate được tham chiếu** thay vì nhúng toàn bộ object graph của nó vào trong root hiện tại.

Ví dụ, một đơn hàng thuộc về một khách hàng. Đơn hàng cần biết khách hàng nào đã đặt, nhưng khách hàng có vòng đời riêng: tên, email, địa chỉ, trạng thái tài khoản và các đơn hàng khác. Nếu nhúng toàn bộ object `Customer` vào `PurchaseOrder`, ranh giới sở hữu trở nên mơ hồ và một thay đổi nhỏ của đơn hàng có thể kéo theo tải/lưu dữ liệu khách hàng. Tham chiếu bằng ID giúp hai aggregate giữ quyền sở hữu và vòng đời độc lập.

Spring Data JDBC cung cấp kiểu `AggregateReference<T, ID>` để biểu diễn một tham chiếu đến aggregate root khác. Ứng dụng cũng có thể lưu một ID đơn giản như `Long customerId`. Hai cách đều thể hiện quan hệ bằng định danh; `AggregateReference` làm rõ hơn trong kiểu Java rằng ID đó trỏ đến một aggregate thuộc loại nào.

## 1. Vì sao phải xác định ranh giới aggregate?

Aggregate là một nhóm entity/value object cần được bảo vệ bởi một ranh giới nhất quán. Aggregate root là điểm truy cập bên ngoài để thay đổi trạng thái bên trong nhóm.

Giả sử hệ thống bán hàng có:

~~~text
Customer aggregate
  Customer (root)
    id
    name
    email
    accountStatus
    addresses

PurchaseOrder aggregate
  PurchaseOrder (root)
    id
    customerId  --------------------+
    status                          |
    lines                           |
                                    |
                                    v
                              Customer root
~~~

`Customer` và `PurchaseOrder` là hai aggregate root độc lập:

- Khách hàng có thể tồn tại trước khi đặt đơn và tiếp tục tồn tại sau khi đơn hoàn tất.
- Một khách hàng có thể có nhiều đơn hàng.
- Thay đổi thông tin hồ sơ khách hàng không nhất thiết phải lưu lại toàn bộ các đơn hàng.
- Cập nhật trạng thái một đơn không cần thay đổi object graph của khách hàng.
- Mỗi aggregate có thể được đọc và lưu qua repository riêng.

**Ranh giới aggregate không được quyết định chỉ bởi quan hệ khóa ngoại hoặc quan hệ một-nhiều trong database.** Nó được quyết định bởi quy tắc nghiệp vụ nào phải được bảo vệ trong cùng một đơn vị thay đổi.

### 1.1. Quy tắc nhất quán bên trong aggregate

Ví dụ trong `PurchaseOrder`:

- Không xác nhận đơn hàng không có dòng hàng.
- Tổng tiền phải khớp với các dòng hàng.
- Đơn đã xác nhận không được thêm dòng hàng theo quy tắc của miền.

Những quy tắc này liên quan trực tiếp đến trạng thái đơn hàng, nên root có trách nhiệm kiểm soát.

Ngược lại, quy tắc như “không được đặt đơn nếu tài khoản khách hàng đã bị khóa” liên quan đến trạng thái của aggregate `Customer`. Ứng dụng cần kiểm tra trạng thái khách hàng tại thời điểm thực hiện nghiệp vụ, nhưng không vì vậy mà biến toàn bộ khách hàng thành một phần sở hữu của đơn hàng.

### 1.2. Quan hệ object không đồng nghĩa với quyền sở hữu

Một thuộc tính Java có kiểu `Customer` bên trong `PurchaseOrder` dễ tạo cảm giác rằng đơn hàng sở hữu hoặc quản lý khách hàng. Trong Spring Data JDBC, quan hệ object được hiểu theo mô hình aggregate mapping; việc đưa trực tiếp root khác vào graph có thể làm framework xem nó như một thành phần thuộc aggregate đang lưu.

Đối với một aggregate độc lập, giữ ID hoặc `AggregateReference` để biểu diễn mối liên hệ. Nếu muốn thay đổi khách hàng, gọi repository của khách hàng và thực hiện hành vi qua root của khách hàng.

## 2. Nhúng object graph và tham chiếu ID khác nhau thế nào?

Hãy so sánh hai cách mô hình hóa:

**Nhúng toàn bộ object:**

~~~java
class PurchaseOrder {
    private Customer customer;
}
~~~

**Giữ tham chiếu bằng ID:**

~~~java
class PurchaseOrder {
    private Long customerId;
}
~~~

Hoặc dùng kiểu chuyên biệt:

~~~java
class PurchaseOrder {
    private AggregateReference<Customer, Long> customer;
}
~~~

| Tiêu chí | Nhúng object aggregate khác | Tham chiếu bằng ID |
| --- | --- | --- |
| Quyền sở hữu | Dễ làm mờ ranh giới giữa hai aggregate | Mỗi aggregate giữ repository và vòng đời riêng |
| Tải dữ liệu | Có nguy cơ kéo theo graph lớn hoặc mapping quan hệ không đúng ý định | Chỉ đọc root hiện tại; tải root được tham chiếu khi nghiệp vụ cần |
| Lưu dữ liệu | Có thể làm phát sinh thao tác lưu trên graph không thuộc root | Lưu root hiện tại không đồng nghĩa lưu root được tham chiếu |
| Đồng thời | Một graph lớn làm tăng phạm vi dữ liệu dễ xung đột | Mỗi aggregate có thể được kiểm soát phiên bản riêng |
| Hiệu năng | Dễ tải nhiều dữ liệu hơn cần thiết | Có thể chọn thời điểm và cách tải dữ liệu liên quan |
| API miền | Quan hệ object có thể khuyến khích sửa root khác trực tiếp | Thể hiện rõ đây là tham chiếu, cần thao tác qua repository phù hợp |

Không có nghĩa là mọi object lồng nhau đều phải chuyển thành ID. **Value object và entity con thuộc cùng aggregate vẫn nên được biểu diễn trong aggregate root** nếu chúng cần cùng tính nhất quán và có vòng đời phụ thuộc root.

Ví dụ:

~~~text
PurchaseOrder aggregate
  PurchaseOrder
    shippingAddress: ShippingAddress (value object)
    lines: List<OrderLine>           (child objects)
    customer: AggregateReference     (aggregate khác)
~~~

Địa chỉ giao hàng chụp tại thời điểm đặt hàng có thể là value object thuộc đơn hàng. Dòng hàng là thành phần của đơn. Khách hàng là aggregate độc lập được tham chiếu bằng ID.

## 3. Tham chiếu bằng ID đơn giản

Giải pháp trực tiếp nhất là lưu ID của aggregate khác như một thuộc tính scalar:

~~~java
@Table("purchase_order")
public class PurchaseOrder {

    @Id
    private Long id;

    @Column("customer_id")
    private Long customerId;

    private String status;
}
~~~

Ưu điểm:

- Đơn giản, dễ hiểu và ít phụ thuộc vào API đặc thù của Spring Data JDBC.
- Không kéo object graph của khách hàng vào aggregate đơn hàng.
- Có thể truyền ID qua service, event hoặc API một cách rõ ràng.
- Dễ viết SQL, index và foreign key.

Nhược điểm là kiểu `Long` không thể hiện loại aggregate được tham chiếu. Nếu code có nhiều loại ID cùng kiểu, lập trình viên có thể vô tình truyền nhầm `supplierId` vào vị trí `customerId`. Có thể giảm rủi ro bằng ID value object riêng hoặc dùng `AggregateReference`.

Ví dụ service:

~~~java
PurchaseOrder order = orderRepository.findById(orderId)
        .orElseThrow();

Customer customer = customerRepository.findById(order.getCustomerId())
        .orElseThrow(() -> new IllegalStateException(
                "Đơn hàng tham chiếu khách hàng không tồn tại"
        ));
~~~

Ứng dụng quyết định rõ khi nào cần tải khách hàng. Repository của đơn hàng không tự động nạp khách hàng qua một lazy proxy.

## 4. `AggregateReference<T, ID>` trong Spring Data JDBC

Spring Data JDBC cung cấp `AggregateReference` để biểu diễn tham chiếu đến một aggregate root khác. Kiểu tổng quát gồm:

- `T`: loại aggregate root được tham chiếu.
- `ID`: kiểu identifier của aggregate đó.

Ví dụ:

~~~java
AggregateReference<Customer, Long>
~~~

Ý nghĩa là “một tham chiếu đến aggregate `Customer`, được định danh bằng `Long`”.

Import:

~~~java
import org.springframework.data.jdbc.core.mapping.AggregateReference;
~~~

Tạo tham chiếu từ ID:

~~~java
AggregateReference<Customer, Long> customerReference =
        AggregateReference.to(customerId);
~~~

Lấy ID từ tham chiếu:

~~~java
Long referencedCustomerId = customerReference.getId();
~~~

`AggregateReference` không chứa toàn bộ dữ liệu khách hàng. Nó chỉ giữ ID và thông tin kiểu ở mức Java. Khi Spring Data JDBC ánh xạ entity, giá trị ID của tham chiếu được lưu vào cột tương ứng.

### 4.1. Vì sao kiểu tham chiếu có lợi?

So với `Long customerId`, kiểu `AggregateReference<Customer, Long>` thể hiện ý nghĩa rõ hơn:

~~~java
AggregateReference<Customer, Long> customer;
AggregateReference<Supplier, Long> supplier;
~~~

Hai thuộc tính cùng chứa ID kiểu `Long` nhưng khác loại aggregate. Compiler có thể phát hiện một số trường hợp truyền nhầm kiểu tham chiếu khi generic type không khớp.

`AggregateReference` không phải object proxy đại diện cho một `Customer` đã tải. Không có phương thức `getName()` hay `getEmail()` trên nó. Muốn lấy thông tin khách hàng, ứng dụng phải dùng ID để truy vấn aggregate tương ứng.

### 4.2. Khai báo trong aggregate root

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.jdbc.core.mapping.AggregateReference;
import org.springframework.data.relational.core.mapping.Column;
import org.springframework.data.relational.core.mapping.Table;

@Table("purchase_order")
public class PurchaseOrder {

    @Id
    private Long id;

    @Column("customer_id")
    private AggregateReference<Customer, Long> customer;

    private String status;

    public PurchaseOrder(
            Long id,
            AggregateReference<Customer, Long> customer,
            String status
    ) {
        this.id = id;
        this.customer = customer;
        this.status = status;
    }

    public Long getId() {
        return id;
    }

    public AggregateReference<Customer, Long> getCustomer() {
        return customer;
    }

    public String getStatus() {
        return status;
    }
}
~~~

`@Column("customer_id")` làm rõ tên cột lưu ID tham chiếu. Tên bảng/cột thực tế cần khớp schema và naming strategy của ứng dụng.

### 4.3. Tạo đơn hàng với tham chiếu

~~~java
Long customerId = 25L;

AggregateReference<Customer, Long> customerReference =
        AggregateReference.to(customerId);

PurchaseOrder order = new PurchaseOrder(
        null,
        customerReference,
        "DRAFT"
);

PurchaseOrder saved = orderRepository.save(order);
~~~

Trong ví dụ này, ứng dụng tạo đơn với ID khách hàng đã biết. Việc tạo `AggregateReference` không truy vấn database để xác minh khách hàng tồn tại và cũng không lưu khách hàng. Nếu cần xác nhận khách hàng tồn tại hoặc còn được phép đặt đơn, service phải thực hiện bước kiểm tra nghiệp vụ riêng.

### 4.4. Đọc ID và tải aggregate được tham chiếu

~~~java
PurchaseOrder order = orderRepository.findById(orderId)
        .orElseThrow();

Long customerId = order.getCustomer().getId();

Customer customer = customerRepository.findById(customerId)
        .orElseThrow(() -> new IllegalStateException(
                "Không tìm thấy khách hàng được tham chiếu"
        ));
~~~

Lần đọc đơn hàng trả về tham chiếu có ID. Lần gọi `customerRepository.findById` mới đọc aggregate khách hàng. Việc tải dữ liệu là chủ động và có thể được đặt trong service, query handler hoặc một projection chuyên biệt.

## 5. Schema quan hệ: cột ID và foreign key

Tham chiếu bằng ID trong Java nên được hỗ trợ bởi schema quan hệ phù hợp. Ví dụ:

~~~sql
CREATE TABLE customer (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    email VARCHAR(320) NOT NULL UNIQUE
);

CREATE TABLE purchase_order (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    customer_id BIGINT NOT NULL,
    status VARCHAR(24) NOT NULL,
    CONSTRAINT fk_purchase_order_customer
        FOREIGN KEY (customer_id)
        REFERENCES customer(id)
);

CREATE INDEX idx_purchase_order_customer
    ON purchase_order(customer_id);
~~~

Ở đây:

- `customer_id` là cột lưu ID tham chiếu.
- Foreign key bảo đảm đơn hàng không trỏ đến customer ID không tồn tại tại thời điểm database kiểm tra constraint.
- Index hỗ trợ truy vấn đơn hàng theo khách hàng và các thao tác join phù hợp.
- `NOT NULL` thể hiện mọi đơn hàng phải có khách hàng; nếu nghiệp vụ cho phép đơn hàng chưa gắn khách hàng, schema và model phải phản ánh điều đó.

**`AggregateReference` không tự tạo foreign key constraint.** Nó mô tả giá trị tham chiếu trong mapping object. Constraint và index cần được khai báo trong schema/migration của database.

### 5.1. Có cần foreign key nếu đã dùng AggregateReference?

Thông thường, nếu quan hệ phải luôn trỏ đến một khách hàng hợp lệ trong cùng database, foreign key là lớp bảo vệ dữ liệu hữu ích. Nó ngăn lỗi do:

- Một đoạn code lưu nhầm ID.
- Dữ liệu được ghi từ SQL thủ công.
- Một batch import không qua service.
- Một tiến trình khác tạo tham chiếu không hợp lệ.

Tuy nhiên, có những kiến trúc chủ động không dùng foreign key vật lý, ví dụ dữ liệu tham chiếu thuộc database/service khác hoặc cần quy trình xóa/tách dữ liệu riêng. Khi đó, ứng dụng phải có chính sách phát hiện và xử lý tham chiếu mồ côi. Việc không có FK cần là quyết định kiến trúc có chủ đích.

### 5.2. Xóa aggregate được tham chiếu

Nếu `customer` đang được `purchase_order` tham chiếu, database có thể từ chối xóa customer do foreign key. Đây thường là hành vi phù hợp với dữ liệu lịch sử đơn hàng.

Không nên chọn `ON DELETE CASCADE` một cách tùy tiện. Nếu xóa khách hàng làm mất luôn các đơn hàng lịch sử, hệ thống có thể vi phạm yêu cầu kiểm toán hoặc lưu trữ nghiệp vụ. Các lựa chọn thường gặp:

- Ngăn xóa customer khi còn đơn hàng tham chiếu.
- Soft delete/deactivate customer nhưng giữ ID.
- Lưu snapshot thông tin cần thiết trong đơn hàng để giữ lịch sử.
- Dùng quy trình archive/anonymize riêng khi có yêu cầu bảo vệ dữ liệu.

Chính sách xóa phải được xác định ở tầng nghiệp vụ và schema; `AggregateReference` không quyết định cascade.

## 6. Không nhúng aggregate khác không có nghĩa không dùng object lồng nhau

Một lỗi thường gặp là hiểu quy tắc “tham chiếu aggregate khác bằng ID” thành “mọi thuộc tính lồng nhau đều phải đổi thành ID”. Điều đó làm mô hình mất đi những thành phần thực sự thuộc aggregate.

Phân biệt theo vòng đời và tính nhất quán:

| Thành phần | Quan hệ với root | Cách mô hình thường dùng |
| --- | --- | --- |
| `ShippingAddress` được chụp tại lúc đặt đơn | Value object thuộc đơn hàng | Nhúng giá trị vào aggregate, ví dụ `@Embedded` |
| `OrderLine` chỉ tồn tại trong vòng đời đơn | Entity con/giá trị thuộc aggregate | Collection được ánh xạ bằng `@MappedCollection` hoặc mapping tương ứng |
| `Customer` có vòng đời riêng | Aggregate root độc lập | ID scalar hoặc `AggregateReference<Customer, Long>` |
| `Product` có kho, giá, trạng thái riêng | Aggregate root độc lập | Tham chiếu ID; lưu snapshot tên/giá đã chốt nếu đơn cần lịch sử |
| `Payment` có quy trình xử lý độc lập | Có thể là aggregate riêng tùy miền | ID tham chiếu và quy trình phối hợp riêng |

Ví dụ cấu trúc:

~~~text
PurchaseOrder aggregate
  PurchaseOrder
    customer: AggregateReference<Customer, Long>
    shippingAddress: ShippingAddress
    lines: List<OrderLine>

Customer aggregate
  Customer
    name
    email
    accountStatus

Product aggregate
  Product
    sku
    currentPrice
    inventoryPolicy
~~~

Đơn hàng giữ ID của khách hàng và sản phẩm để nhận biết các aggregate liên quan. Nhưng đơn hàng có thể giữ `ShippingAddress` và `OrderLine` bên trong vì chúng thuộc trạng thái đơn hàng.

### 6.1. Snapshot nghiệp vụ khác với nhúng aggregate

Khi khách hàng đặt hàng, đơn cần lưu tên sản phẩm, giá tại thời điểm mua và địa chỉ giao hàng đã chọn. Nếu chỉ giữ `productId` rồi mỗi lần xem lịch sử lại lấy tên/giá hiện tại từ Product, lịch sử có thể thay đổi theo dữ liệu catalog.

Vì vậy có thể lưu:

~~~text
OrderLine
  productId
  productNameAtPurchase
  unitPriceAtPurchase
  quantity
~~~

`productId` là tham chiếu đến aggregate Product. `productNameAtPurchase` và `unitPriceAtPurchase` là snapshot thuộc đơn hàng. Snapshot không phải toàn bộ aggregate Product; nó là dữ liệu cần thiết để bảo toàn ý nghĩa giao dịch.

## 7. Tham chiếu ID không tự tải dữ liệu và không có lazy loading

Với Spring Data JDBC, `AggregateReference` không hoạt động như lazy proxy của JPA. Khi đọc `PurchaseOrder`:

~~~text
SELECT ... FROM purchase_order WHERE id = ?
                    |
                    v
PurchaseOrder(customer = AggregateReference.to(25))
~~~

Framework không tự thực hiện một truy vấn bổ sung để nạp toàn bộ `Customer` chỉ vì thuộc tính tham chiếu tồn tại.

Điều này có các hệ quả:

- Không có lời gọi `order.getCustomer().getName()`.
- Không có lazy-loading exception như mô hình proxy của JPA.
- Không tự phát sinh N+1 query do truy cập getter trên proxy.
- Nếu màn hình cần tên khách hàng, ứng dụng phải truy vấn dữ liệu đó có chủ đích.

### 7.1. Tải dữ liệu khi cần

Một service đơn giản:

~~~java
@Service
public class OrderDetailService {

    private final PurchaseOrderRepository orderRepository;
    private final CustomerRepository customerRepository;

    public OrderDetailService(
            PurchaseOrderRepository orderRepository,
            CustomerRepository customerRepository
    ) {
        this.orderRepository = orderRepository;
        this.customerRepository = customerRepository;
    }

    @Transactional(readOnly = true)
    public OrderDetail loadDetail(Long orderId) {
        PurchaseOrder order = orderRepository.findById(orderId)
                .orElseThrow();

        Customer customer = customerRepository.findById(
                order.getCustomer().getId()
        ).orElseThrow();

        return new OrderDetail(order, customer);
    }
}
~~~

`OrderDetail` ở đây là DTO/projection do ứng dụng định nghĩa. Ví dụ giả định các repository và constructor tương ứng đã tồn tại. Transaction read-only có thể giúp các thao tác đọc nằm trong cùng một ranh giới transaction theo cấu hình transaction manager.

### 7.2. Tránh N+1 khi tải nhiều aggregate

Nếu tải 100 đơn hàng rồi gọi `customerRepository.findById` cho từng đơn, ứng dụng có thể phát ra 101 truy vấn:

~~~text
1 query: tải 100 đơn hàng
100 queries: tải customer của từng đơn
-------------------------------
101 queries
~~~

Tham chiếu ID giúp tránh tự động tải graph, nhưng không tự giải quyết nhu cầu hiển thị dữ liệu liên quan. Khi xử lý danh sách, hãy cân nhắc:

- Lấy tập customer ID duy nhất từ danh sách đơn.
- Dùng truy vấn theo tập ID (`IN`) để tải khách hàng theo lô.
- Tạo projection/query chuyên biệt join các bảng cho màn hình đọc.
- Dùng read model riêng nếu nhu cầu đọc phức tạp hơn mô hình aggregate ghi.

Ví dụ SQL projection:

~~~sql
SELECT
    po.id AS order_id,
    po.status,
    c.id AS customer_id,
    c.name AS customer_name
FROM purchase_order po
JOIN customer c ON c.id = po.customer_id
WHERE po.id = ?;
~~~

Query join này phục vụ việc đọc dữ liệu hiển thị. Nó không có nghĩa `Customer` trở thành một phần aggregate được lưu cùng `PurchaseOrder`.

## 8. Kiểm tra tham chiếu và quy tắc nghiệp vụ

`AggregateReference.to(customerId)` chỉ tạo một tham chiếu. Nó không chứng minh customer tồn tại, đang hoạt động hoặc được phép đặt hàng.

Ví dụ service tạo đơn:

~~~java
@Transactional
public PurchaseOrder placeOrder(Long customerId, List<OrderLine> lines) {
    Customer customer = customerRepository.findById(customerId)
            .orElseThrow(() -> new IllegalArgumentException(
                    "Khách hàng không tồn tại"
            ));

    if (!customer.isActive()) {
        throw new IllegalStateException("Tài khoản khách hàng không hoạt động");
    }

    PurchaseOrder order = PurchaseOrder.create(
            AggregateReference.to(customer.getId()),
            lines
    );

    return orderRepository.save(order);
}
~~~

Ví dụ minh họa giả định `Customer.isActive()` và factory `PurchaseOrder.create(...)` tồn tại trong mô hình. Quy tắc xác minh customer được thực hiện tại application service trước khi tạo đơn.

### 8.1. Kiểm tra trước không thay thế foreign key

Giữa lúc đọc customer và lưu order, một tiến trình khác có thể xóa customer. Nếu database có foreign key, thao tác insert order sẽ bị từ chối nếu customer không còn tồn tại. Nếu không có foreign key, hệ thống cần cơ chế đảm bảo tham chiếu hợp lệ khác.

Đây là khác biệt giữa:

- **Kiểm tra nghiệp vụ:** customer tồn tại và đang được phép đặt hàng ở thời điểm kiểm tra.
- **Ràng buộc tham chiếu:** hàng customer tồn tại tại thời điểm database thực thi insert/update.
- **Đồng bộ trạng thái:** account có thể bị khóa ngay sau bước kiểm tra; yêu cầu xử lý race condition này tùy mức độ chặt của nghiệp vụ.

Nếu nghiệp vụ đòi hỏi không thể đặt đơn khi tài khoản vừa bị khóa đồng thời, cần thiết kế concurrency/transaction/locking phù hợp. Chỉ kiểm tra một lần ở Java chưa chắc đảm bảo quy tắc trong mọi cuộc đua.

### 8.2. Tham chiếu đến aggregate ở service khác

Nếu customer nằm trong một service/database khác, không thể tạo foreign key vật lý xuyên database theo cách thông thường. Khi đó:

- Lưu ID định danh ổn định do service sở hữu cấp.
- Gọi API hoặc dùng event để kiểm tra/đồng bộ trạng thái theo hợp đồng.
- Xử lý trường hợp service kia không khả dụng.
- Xác định cách xử lý ID không còn tồn tại hoặc dữ liệu đã bị xóa.
- Cân nhắc lưu snapshot dữ liệu cần thiết cho lịch sử giao dịch.

Trong trường hợp này, `AggregateReference` có thể giúp diễn tả ID tham chiếu ở model Java nếu kiểu ID phù hợp, nhưng nó không cung cấp giao tiếp mạng hay phân tán transaction. Tham chiếu xuyên service là một hợp đồng tích hợp, không phải quan hệ object tự động.

## 9. Thay đổi và xóa aggregate được tham chiếu

Giả sử khách hàng thay đổi email hoặc tên sau khi đã đặt đơn. Vì đơn hàng chỉ giữ ID:

- Đơn hàng vẫn trỏ tới cùng customer ID.
- Nếu đọc thông tin hiện tại từ Customer repository, ứng dụng thấy dữ liệu mới.
- Nếu đơn cần giữ thông tin tại thời điểm đặt, snapshot trong đơn vẫn giữ giá trị cũ.

Đây là quyết định quan trọng: **tham chiếu ID trả lời aggregate nào liên quan; snapshot trả lời dữ liệu nào cần giữ lại tại thời điểm nghiệp vụ.**

### 9.1. Không cascade cập nhật toàn bộ aggregate

Khi lưu `PurchaseOrder`, không nên kỳ vọng framework tự lưu `Customer` được tham chiếu. Muốn cập nhật customer, gọi repository/hành vi của customer riêng. Điều này ngăn một thao tác cập nhật đơn vô tình ghi đè thông tin khách hàng đã thay đổi ở nơi khác.

### 9.2. Xóa tham chiếu

Nếu một customer bị xóa, có một số khả năng:

| Chính sách | Ý nghĩa |
| --- | --- |
| Restrict/RESTRICT | Không cho xóa customer khi còn đơn hàng tham chiếu |
| Soft delete | Đánh dấu customer không còn hoạt động nhưng giữ hàng và ID |
| SET NULL | Cho phép đơn tồn tại mà không còn liên kết customer; chỉ hợp lý nếu cột nullable và miền cho phép |
| Archive/anonymize | Giữ bản ghi nghiệp vụ cần thiết, thay đổi hoặc ẩn dữ liệu cá nhân theo chính sách |

`ON DELETE CASCADE` thường không phù hợp với đơn hàng cần lưu lịch sử, vì nó có thể xóa dữ liệu giao dịch cùng customer. Chọn chính sách theo yêu cầu lưu trữ, pháp lý và nghiệp vụ.

## 10. Tham chiếu ID và transaction

Hai aggregate độc lập thường được lưu bằng repository riêng. Nếu một use case cần thay đổi cả hai, application service có thể điều phối trong transaction database chung khi chúng dùng cùng datasource/transaction manager và database hỗ trợ phạm vi đó.

Ví dụ:

~~~java
@Transactional
public PurchaseOrder reserveOrder(Long customerId, List<OrderLine> lines) {
    Customer customer = customerRepository.findById(customerId)
            .orElseThrow();

    customer.ensureCanPlaceOrder();

    Customer updatedCustomer = customer.recordOrderAttempt();
    customerRepository.save(updatedCustomer);

    PurchaseOrder order = PurchaseOrder.create(
            AggregateReference.to(customerId),
            lines
    );
    return orderRepository.save(order);
}
~~~

Đây là ví dụ điều phối nghiệp vụ; việc cập nhật customer trong cùng transaction chỉ nên làm khi quy tắc nhất quán thực sự yêu cầu và hai repository dùng cùng transaction manager. Nếu hai aggregate được lưu trong hai database hoặc hai service khác nhau, `@Transactional` cục bộ không tạo distributed transaction một cách tự động.

### 10.1. Giữ aggregate nhỏ để giảm xung đột

Nếu mọi thao tác đơn hàng đều phải tải và lưu khách hàng, những thay đổi không liên quan có thể tranh chấp cùng một aggregate hoặc cùng transaction lâu hơn. Tham chiếu ID giúp giảm phạm vi dữ liệu cần tải và thay đổi:

~~~text
Thao tác đổi trạng thái đơn
  -> load PurchaseOrder
  -> kiểm tra invariant của đơn
  -> save PurchaseOrder

Không cần load/save Customer nếu nghiệp vụ không cần trạng thái Customer.
~~~

Đây cũng là cách giảm thời gian giữ connection và số SQL phát sinh cho một use case.

### 10.2. Khi cần phối hợp bất đồng bộ

Nếu nghiệp vụ liên quan đến nhiều aggregate hoặc nhiều service nhưng không cần một transaction ACID duy nhất, có thể dùng:

- Domain event để thông báo thay đổi đã xảy ra.
- Outbox pattern để ghi event cùng transaction với aggregate phát sinh event.
- Saga/process manager để điều phối nhiều bước và compensation.
- Eventual consistency với trạng thái trung gian rõ ràng.

Ví dụ đặt hàng và thanh toán: đơn hàng có thể được tạo ở trạng thái `PENDING_PAYMENT`; payment service xử lý riêng; event kết quả cập nhật trạng thái đơn. Không nhúng toàn bộ aggregate Payment vào Order chỉ để mong một lần save có thể điều phối tất cả.

## 11. Dùng ID value object hay AggregateReference?

Ngoài `Long`, ứng dụng có thể định nghĩa kiểu ID riêng:

~~~java
public record CustomerId(Long value) {
    public CustomerId {
        if (value == null || value <= 0) {
            throw new IllegalArgumentException("CustomerId không hợp lệ");
        }
    }
}
~~~

Kiểu này giúp tránh truyền nhầm các ID cùng kiểu primitive. Tuy nhiên, việc ánh xạ ID wrapper vào cột JDBC cần converter/mapping phù hợp. Đừng giả định mọi record ID tự động được Spring Data JDBC chuyển thành scalar chỉ vì nó có một component.

So sánh:

| Kiểu tham chiếu | Điểm mạnh | Cân nhắc |
| --- | --- | --- |
| `Long customerId` | Đơn giản, dễ bind SQL, ít phụ thuộc framework | Không thể hiện loại aggregate bằng kiểu |
| `CustomerId` | Type-safe trong domain, có thể chứa validation | Cần mapping/converter nếu persistence không tự ánh xạ theo mong muốn |
| `AggregateReference<Customer, Long>` | Thể hiện rõ đây là tham chiếu đến aggregate Customer | Phụ thuộc API Spring Data JDBC và vẫn chỉ chứa ID |
| `Customer customer` | Dễ gọi thuộc tính object nếu đã có dữ liệu | Có nguy cơ nhầm lẫn ownership và graph mapping giữa aggregate |

Chọn cách biểu diễn dựa trên mức độ type-safety cần thiết, API framework của phiên bản dự án và sự rõ ràng của domain model.

## 12. Truy vấn dữ liệu liên quan cho màn hình đọc

Aggregate boundary phù hợp cho mô hình ghi, nhưng một màn hình có thể cần dữ liệu từ nhiều aggregate. Không cần phá ranh giới ghi để đáp ứng truy vấn.

### 12.1. Query handler dùng nhiều repository

Với một đơn hàng:

1. Đọc `PurchaseOrder`.
2. Lấy customer ID từ `AggregateReference`.
3. Đọc `Customer`.
4. Tạo DTO hiển thị.

Cách này đơn giản khi dữ liệu ít và use case chỉ tải một số aggregate.

### 12.2. Projection SQL cho danh sách

Với danh sách lớn, join có thể hiệu quả hơn việc gọi repository trong vòng lặp:

~~~sql
SELECT
    po.id AS order_id,
    po.status AS order_status,
    po.customer_id,
    c.name AS customer_name
FROM purchase_order po
JOIN customer c ON c.id = po.customer_id
WHERE po.status = ?
ORDER BY po.id DESC
LIMIT ? OFFSET ?;
~~~

Kết quả nên ánh xạ vào DTO/projection chuyên cho màn hình. Query read này có thể join các bảng mà không biến các root thành một aggregate ghi duy nhất.

### 12.3. Khi read model phát triển phức tạp

Nếu nhiều màn hình cần kết hợp dữ liệu từ nhiều aggregate, cân nhắc read model hoặc materialized view phù hợp. Dữ liệu đọc có thể được cập nhật đồng bộ hoặc bất đồng bộ tùy yêu cầu nhất quán. Điều quan trọng là không để nhu cầu hiển thị làm phình aggregate ghi.

## 13. Những sai lầm thường gặp

| Sai lầm | Hệ quả | Cách thiết kế lại |
| --- | --- | --- |
| Nhúng trực tiếp root Customer vào PurchaseOrder | Làm mờ ownership và có thể kéo graph ngoài ý muốn vào mapping | Giữ customer ID hoặc AggregateReference |
| Nghĩ AggregateReference tự tải Customer | Code mong có lazy loading nhưng chỉ nhận ID | Dùng ID gọi repository hoặc query projection |
| Nghĩ save Order sẽ cascade save Customer | Thay đổi customer có thể không được lưu như kỳ vọng | Lưu aggregate riêng qua repository của nó |
| Dùng AggregateReference như foreign key constraint | Database vẫn có thể chứa ID mồ côi nếu không có constraint | Tạo FK/index trong schema khi phù hợp |
| Dùng @MappedCollection cho aggregate root khác | Root khác bị coi như child thuộc aggregate hiện tại | Dùng tham chiếu ID qua ranh giới aggregate |
| Chuyển mọi object lồng thành ID | Mất value object/child cần cùng invariant | Giữ thành phần thuộc cùng aggregate ở trong root |
| Chỉ giữ productId và lấy giá hiện tại khi xem đơn cũ | Lịch sử giao dịch có thể thay đổi theo catalog | Lưu snapshot tên/giá tại thời điểm mua |
| Gọi repository trong vòng lặp cho danh sách lớn | N+1 queries, tăng round-trip và latency | Batch lookup hoặc query projection |
| Không xử lý customer bị xóa | Tham chiếu mồ côi hoặc mất lịch sử | Chọn FK/delete policy/soft delete phù hợp |
| Nghĩ @Transactional bao trùm nhiều service/database | Transaction cục bộ không tự trở thành distributed transaction | Dùng outbox/saga hoặc cơ chế phân tán được thiết kế rõ |

## 14. Tình huống vận dụng

### Tình huống A — Đơn hàng và khách hàng

Một khách hàng có hàng nghìn đơn. Khi nhân viên đổi trạng thái một đơn, hệ thống chỉ cần cập nhật đơn đó.

**Thiết kế:** `PurchaseOrder` lưu `AggregateReference<Customer, Long>` hoặc `customerId`. Thay đổi trạng thái đơn chỉ tải và lưu root đơn hàng; customer chỉ được tải khi use case cần thông tin hoặc cần kiểm tra trạng thái.

### Tình huống B — Đơn hàng và địa chỉ giao hàng

Khách hàng có thể thay địa chỉ mặc định sau khi mua. Đơn cũ phải giữ đúng địa chỉ đã dùng khi đặt.

**Thiết kế:** đơn hàng lưu snapshot `ShippingAddress` như value object thuộc aggregate. Nếu cần biết địa chỉ hồ sơ hiện tại, có thể tham chiếu customer và truy vấn riêng. Không dùng tham chiếu động thay cho snapshot lịch sử.

### Tình huống C — Sản phẩm và dòng hàng

Sản phẩm là aggregate độc lập, còn dòng hàng thuộc đơn. Dòng hàng phải giữ số lượng, tên và giá đã chốt.

**Thiết kế:** `OrderLine` nằm trong aggregate `PurchaseOrder`; nó giữ `productId` để tham chiếu sản phẩm và lưu snapshot thông tin cần cho lịch sử. Thay đổi catalog không tự làm thay đổi đơn đã đặt.

### Tình huống D — Customer ở service khác

Đơn hàng và khách hàng nằm ở hai service với hai database độc lập.

**Thiết kế:** lưu customer ID theo hợp đồng định danh giữa các service. Không có FK vật lý xuyên database; cần quy trình kiểm tra, đồng bộ và xử lý ID không còn hợp lệ. Nếu cần giữ thông tin khách hàng lúc đặt, lưu snapshot trong đơn.

## 15. Quy trình thiết kế một tham chiếu aggregate

Khi một aggregate cần liên hệ với aggregate khác, hãy đi theo trình tự:

1. **Xác định ownership.** Thành phần được tham chiếu có vòng đời riêng hay là child/value object thuộc root hiện tại?
2. **Xác định dữ liệu cần giữ.** Chỉ cần ID hay cần snapshot nghiệp vụ tại thời điểm phát sinh?
3. **Chọn kiểu tham chiếu.** Dùng ID scalar, ID value object hoặc `AggregateReference<T, ID>` theo nhu cầu type-safety và mapping.
4. **Thiết kế schema.** Tạo cột tham chiếu, foreign key và index khi phù hợp; quyết định nullable và delete policy.
5. **Thiết kế use case.** Chỉ tải aggregate được tham chiếu khi cần; kiểm tra quy tắc nghiệp vụ tại thời điểm phù hợp.
6. **Tránh N+1.** Với danh sách, dùng batch lookup hoặc query projection.
7. **Xác định nhất quán.** Quyết định transaction chung, event/outbox/saga hay eventual consistency.
8. **Kiểm thử vòng đời.** Kiểm tra insert/load/update/delete, tham chiếu không tồn tại, xóa root và xử lý đồng thời.

## Ghi nhớ

Một aggregate root nên quản lý trạng thái mà nó sở hữu. Khi cần liên hệ với aggregate độc lập, giữ **ID hoặc `AggregateReference`** để biểu diễn quan hệ. Spring Data JDBC lưu giá trị ID tham chiếu, nhưng không tự nạp toàn bộ aggregate, không cascade lưu aggregate khác và không tự tạo foreign key trong database.

Giữ value object và entity con bên trong aggregate khi chúng cần cùng ranh giới nhất quán. Dùng snapshot cho dữ liệu lịch sử cần giữ nguyên, query projection cho màn hình cần kết hợp nhiều root, và transaction hoặc cơ chế event phù hợp khi một use case phải phối hợp nhiều aggregate. Cách thiết kế này giúp mô hình ghi rõ ownership, giảm graph không cần thiết và kiểm soát tốt hơn chi phí truy cập cơ sở dữ liệu.
