# Khái niệm aggregate trong Spring Data Relational và phạm vi hỗ trợ của R2DBC

## 1. Vì sao cần mô hình aggregate khi làm việc với dữ liệu quan hệ?

Trong một ứng dụng nghiệp vụ, một đối tượng thường không tồn tại độc lập. Một đơn hàng có thể gồm nhiều dòng hàng; một phiếu giao hàng có địa chỉ nhận; một tài khoản có các thiết lập hoặc thông tin phụ. Khi lưu dữ liệu, ứng dụng phải xác định phần nào thuộc cùng một đơn vị nghiệp vụ và phần nào chỉ được tham chiếu đến.

Nếu xem mọi bảng là những entity độc lập rồi nối chúng tùy ý, tầng nghiệp vụ dễ bị phụ thuộc vào cấu trúc database. Một thao tác cập nhật có thể vô tình thay đổi nhiều đối tượng không liên quan, hoặc một đối tượng được tải lên rồi ghi lại kéo theo một đồ thị dữ liệu quá lớn.

**Aggregate** là cách tổ chức mô hình miền thành một cụm đối tượng có ranh giới rõ ràng. Cụm này có một **aggregate root** làm điểm truy cập chính. Những đối tượng nằm bên trong được quản lý thông qua root và thuộc cùng một đơn vị nhất quán nghiệp vụ.

Spring Data Relational sử dụng cách tiếp cận aggregate-centric khi ánh xạ dữ liệu quan hệ. Spring Data JDBC và Spring Data R2DBC cùng dựa trên mô hình mapping relational này. R2DBC bổ sung cách thực hiện I/O reactive và non-blocking; nó không biến mô hình aggregate thành ORM đầy đủ như JPA/Hibernate.

## 2. Aggregate, aggregate root và các đối tượng thành phần

### 2.1. Aggregate là gì?

Một aggregate là một nhóm entity và value object được xem như một đơn vị trong mô hình miền. Nhóm đó được thiết kế quanh một số quy tắc nghiệp vụ cần được bảo vệ cùng nhau.

Ví dụ, một đơn hàng có thể bao gồm:

- Đơn hàng với mã đơn, trạng thái và thời điểm tạo.
- Các dòng hàng với mã sản phẩm, số lượng và đơn giá tại thời điểm đặt hàng.
- Địa chỉ giao hàng được chụp lại tại thời điểm đặt hàng.

Các đối tượng này thường được tạo, cập nhật hoặc xóa như một phần của vòng đời đơn hàng. Địa chỉ giao hàng trong đơn hàng là dữ liệu lịch sử của đơn hàng; nó không nhất thiết là cùng một đối tượng với địa chỉ hiện tại trong hồ sơ khách hàng.

~~~text
Order aggregate
       |
       v
+-----------------------------+
| Order (Aggregate Root)      |
| id, status, createdAt       |
|                             |
|  +-----------------------+  |
|  | OrderLine             |  |
|  | sku, quantity, price  |  |
|  +-----------------------+  |
|                             |
|  +-----------------------+  |
|  | ShippingAddress       |  |
|  | street, city, zip     |  |
|  +-----------------------+  |
+-----------------------------+

Order ---- customerId ----> Customer aggregate
          (chỉ tham chiếu)
~~~

Ranh giới aggregate không đơn thuần là cách gom các bảng có quan hệ khóa ngoại. Nó phản ánh cách nghiệp vụ muốn quản lý vòng đời, tính nhất quán và quyền thay đổi dữ liệu.

### 2.2. Aggregate root là gì?

Aggregate root là entity gốc của aggregate. Nó có danh tính riêng, thường được đánh dấu bằng **@Id**, và là điểm vào mà các tầng khác sử dụng để đọc hoặc thay đổi aggregate.

Trong ví dụ đơn hàng:

- **Order** là aggregate root.
- **OrderLine** là entity thành phần nằm trong aggregate Order.
- **ShippingAddress** có thể là value object được lưu cùng Order.
- **Customer** là một aggregate riêng; Order giữ thông tin định danh khách hàng mà nó tham chiếu.

Các quy tắc nghiệp vụ liên quan đến đơn hàng nên được thực thi qua Order. Ví dụ, không nên cho một tầng bất kỳ cập nhật trực tiếp số lượng của một OrderLine mà bỏ qua việc kiểm tra trạng thái đơn hàng, giới hạn số lượng hoặc quy tắc tính tổng tiền.

### 2.3. Entity và value object bên trong aggregate

Entity có danh tính được dùng để phân biệt đối tượng qua thời gian. Value object được nhận diện bằng giá trị của các thuộc tính và thường không có vòng đời độc lập.

Ví dụ:

| Thành phần | Loại thường gặp | Đặc điểm |
|---|---|---|
| Order | Aggregate root / entity | Có ID và quản lý vòng đời đơn hàng |
| OrderLine | Entity thành phần | Thuộc về một Order; không phải điểm truy cập độc lập của module |
| ShippingAddress | Value object | Được mô tả bằng các trường địa chỉ; thường lưu cùng Order |
| Customer | Aggregate root khác | Có vòng đời và quy tắc nghiệp vụ riêng |

Một đối tượng có thể là entity trong mô hình Java nhưng vẫn chỉ là thành phần của aggregate trong mô hình miền. Điều quyết định là ranh giới sở hữu và vòng đời nghiệp vụ, không chỉ là tên class hoặc việc bảng có khóa chính hay không.

## 3. Ranh giới aggregate và tính nhất quán nghiệp vụ

Aggregate giúp xác định nơi bảo vệ các invariant (quy tắc luôn phải đúng). Ví dụ, một đơn hàng đã thanh toán không được tùy tiện thêm dòng hàng mới; số lượng mỗi dòng hàng phải lớn hơn 0; tổng tiền phải được tính từ các dòng hàng hợp lệ.

Nếu những quy tắc này thuộc aggregate Order, thao tác thay đổi phải đi qua Order root. Điều này tạo ra một ranh giới rõ ràng cho việc kiểm tra dữ liệu trước khi lưu.

Có thể dùng các nguyên tắc sau để thiết kế ranh giới:

- Đưa vào cùng aggregate những đối tượng cần được thay đổi như một đơn vị nghiệp vụ.
- Giữ aggregate nhỏ vừa đủ để một thao tác không phải tải và ghi quá nhiều dữ liệu.
- Để aggregate root kiểm soát các thay đổi đối với các thành phần bên trong.
- Tham chiếu aggregate khác bằng định danh khi không cần sở hữu vòng đời của nó.
- Tránh tạo quan hệ object graph hai chiều chỉ vì các bảng có khóa ngoại.

Ví dụ, Order có thể lưu customer ID để biết đơn hàng thuộc về khách hàng nào. Việc đổi email, khóa tài khoản hoặc cập nhật hồ sơ Customer là trách nhiệm của Customer aggregate. Không nên nhúng toàn bộ Customer vào Order rồi để thao tác lưu Order vô tình ghi lại dữ liệu khách hàng.

Aggregate thường được xem là một ranh giới nhất quán trong thiết kế domain-driven design. Tuy nhiên, điều đó không có nghĩa hệ thống không bao giờ được dùng một transaction database bao trùm nhiều aggregate. Nếu một nghiệp vụ cần cập nhật nhiều aggregate trong cùng database và yêu cầu atomicity, tầng ứng dụng có thể xác định transaction phù hợp. Ranh giới aggregate vẫn giúp xác định quyền sở hữu và cách thay đổi dữ liệu.

## 4. Spring Data Relational nhìn aggregate như thế nào?

Spring Data Relational cung cấp mapping cho các đối tượng Java với bảng và cột quan hệ. Mô hình này được dùng trong Spring Data JDBC và Spring Data R2DBC.

Một số annotation quan trọng:

| Annotation / API | Vai trò |
|---|---|
| **@Table** | Chỉ định bảng tương ứng với entity hoặc aggregate root |
| **@Id** | Đánh dấu định danh của aggregate root |
| **@Column** | Chỉ định tên cột trong database |
| **@MappedCollection** | Ánh xạ collection các đối tượng thành phần của aggregate vào bảng liên quan |
| **@Embedded** | Ánh xạ value object vào các cột của cùng hàng dữ liệu |
| **@Version** | Hỗ trợ optimistic locking bằng version field |
| **AggregateReference** | Biểu diễn tham chiếu đến một aggregate khác bằng định danh |

Spring Data Relational dùng metadata mapping để xác định bảng, cột và quan hệ thuộc aggregate. Nó không cần một persistence context kiểu JPA để theo dõi mọi object được đọc trong suốt một session.

### 4.1. Aggregate root với @Table và @Id

Ví dụ một aggregate Order đơn giản:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Table;

@Table("orders")
public class Order {

    @Id
    private Long id;

    private String status;

    public Order() {
    }

    public Order(String status) {
        this.status = status;
    }

    public Long getId() {
        return id;
    }

    public String getStatus() {
        return status;
    }

    public void setStatus(String status) {
        this.status = status;
    }
}
~~~

**@Table("orders")** xác định bảng của aggregate root. **@Id** xác định trường định danh. Spring Data dùng metadata này để tạo câu SQL đọc hoặc ghi theo mapping strategy.

Ví dụ này dùng class và getter/setter để dễ thấy cách mapping hoạt động. Có thể dùng constructor, record hoặc immutable entity nếu phù hợp với phiên bản Spring Data và mô hình ứng dụng.

### 4.2. Value object với @Embedded

Một value object thường không cần bảng riêng hoặc ID riêng nếu nó chỉ tồn tại như một phần của aggregate. Có thể ánh xạ các trường của nó vào cùng hàng của bảng root bằng **@Embedded**.

~~~java
import org.springframework.data.relational.core.mapping.Embedded;

public record ShippingAddress(
        String street,
        String city,
        String postalCode
) {}

@Table("orders")
public class Order {

    @Id
    private Long id;

    private String status;

    @Embedded(prefix = "shipping_")
    private ShippingAddress shippingAddress;
}
~~~

Với prefix **shipping_**, các thuộc tính của ShippingAddress có thể được ánh xạ thành các cột như shipping_street, shipping_city và shipping_postal_code. Tên cột cuối cùng phụ thuộc naming strategy và annotation mapping của dự án.

Value object giúp nhóm những trường luôn có ý nghĩa cùng nhau. Ví dụ, thay vì để street, city và postalCode rời rạc trong Order, có thể dùng ShippingAddress để thể hiện khái niệm địa chỉ giao hàng.

Không phải mọi object lồng nhau đều nên dùng @Embedded. Nếu đối tượng có danh tính riêng và vòng đời riêng, cần xem xét nó có phải entity thành phần của aggregate hay một aggregate khác được tham chiếu.

## 5. Ánh xạ entity thành phần bằng @MappedCollection

### 5.1. Collection thuộc aggregate root

Một đơn hàng có thể có nhiều dòng hàng. Nếu các dòng hàng thuộc vòng đời của đơn hàng, có thể ánh xạ chúng thành collection bằng **@MappedCollection**.

~~~java
import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.List;

import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.MappedCollection;
import org.springframework.data.relational.core.mapping.Table;

@Table("orders")
public class Order {

    @Id
    private Long id;

    private String status;

    @MappedCollection(idColumn = "order_id", keyColumn = "line_no")
    private List<OrderLine> lines = new ArrayList<>();

    public Long getId() {
        return id;
    }

    public List<OrderLine> getLines() {
        return lines;
    }

    public void addLine(OrderLine line) {
        lines.add(line);
    }
}

public record OrderLine(
        String sku,
        int quantity,
        BigDecimal unitPrice
) {}
~~~

**idColumn** chỉ định cột ở bảng thành phần dùng để tham chiếu ID của aggregate root. Với collection dạng List, **keyColumn** có thể được dùng để lưu vị trí hoặc khóa của phần tử trong collection. Cần thiết kế schema tương ứng với kiểu collection và mapping strategy của dự án.

Một schema minh họa:

~~~sql
CREATE TABLE orders (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    status VARCHAR(30) NOT NULL
);

CREATE TABLE order_lines (
    order_id BIGINT NOT NULL REFERENCES orders(id),
    line_no INTEGER NOT NULL,
    sku VARCHAR(80) NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    unit_price NUMERIC(18, 2) NOT NULL CHECK (unit_price >= 0),
    PRIMARY KEY (order_id, line_no)
);
~~~

Bảng order_lines có khóa ngoại về orders. Mỗi dòng hàng gắn với một đơn hàng. Trong một mô hình khác, có thể dùng Set thay vì List hoặc cấu trúc khóa khác; cần bảo đảm mapping và schema nhất quán.

Tên bảng của các đối tượng thành phần và tên cột có thể được suy ra theo naming strategy hoặc chỉ định bằng annotation. Ví dụ SQL ở trên mô tả cấu trúc quan hệ mong muốn; khi triển khai, hãy xác nhận tên thực tế mà mapping strategy của phiên bản Spring Data đang dùng tạo ra.

### 5.2. Vòng đời của entity thành phần

OrderLine thuộc aggregate Order. Tầng nghiệp vụ thao tác với dòng hàng qua Order, chẳng hạn:

~~~java
public void changeQuantity(int lineNumber, int newQuantity) {
    if (newQuantity <= 0) {
        throw new IllegalArgumentException("Quantity must be positive");
    }

    OrderLine current = lines.get(lineNumber);
    lines.set(lineNumber, new OrderLine(
            current.sku(),
            newQuantity,
            current.unitPrice()
    ));
}
~~~

Ví dụ chỉ minh họa việc thay đổi một phần tử trong collection; code production cần xử lý chỉ số hoặc định danh dòng hàng phù hợp với mô hình. Quy tắc số lượng được đặt ở nơi kiểm soát aggregate để mọi thay đổi đều tuân thủ invariant.

Không nên tạo một repository độc lập cho OrderLine chỉ để cập nhật nó từ mọi nơi nếu OrderLine không có vòng đời độc lập. Nếu nghiệp vụ thực sự cần truy cập và quản lý dòng hàng độc lập, cần xem lại ranh giới aggregate thay vì chỉ thêm repository cho tiện.

### 5.3. Lưu aggregate

Repository thường được khai báo cho aggregate root:

~~~java
import org.springframework.data.repository.reactive.ReactiveCrudRepository;
import reactor.core.publisher.Flux;

public interface OrderRepository
        extends ReactiveCrudRepository<Order, Long> {

    Flux<Order> findByStatus(String status);
}
~~~

Tầng nghiệp vụ nhận Order từ repository, thay đổi root hoặc các thành phần thuộc aggregate rồi lưu root:

~~~java
public Mono<Order> addLine(Long orderId, OrderLine line) {
    return orderRepository.findById(orderId)
            .switchIfEmpty(Mono.error(
                    new IllegalArgumentException("Order not found")))
            .flatMap(order -> {
                if (!"DRAFT".equals(order.getStatus())) {
                    return Mono.error(
                            new IllegalStateException("Order is not editable"));
                }

                order.addLine(line);
                return orderRepository.save(order);
            });
}
~~~

Đây là ví dụ rút gọn; trong ứng dụng thực tế, các phương thức nghiệp vụ nên được đóng gói trong aggregate và xử lý lỗi theo quy ước của domain. Ý tưởng chính là repository làm việc với root, còn collection thành phần được quản lý như một phần của aggregate.

Spring Data Relational có thể thực hiện nhiều câu SQL để lưu root và các thành phần. Không nên giả định một lời gọi save luôn tương ứng với đúng một câu SQL hoặc framework sẽ tự tính diff từng object như ORM có dirty checking. Cách ghi collection và SQL cụ thể phụ thuộc mapping, phiên bản và trạng thái entity; nếu hiệu năng quan trọng, hãy quan sát SQL và đo với dữ liệu thực tế.

## 6. Tham chiếu đến aggregate khác

### 6.1. Không nhúng toàn bộ aggregate khác vào aggregate hiện tại

Giả sử Order cần biết Customer nào đã đặt hàng. Customer có vòng đời riêng và được quản lý bởi CustomerRepository. Nếu Order chứa cả object Customer như một thành phần được sở hữu, ranh giới giữa hai aggregate sẽ bị xóa nhòa.

Một cách phù hợp là giữ customer ID:

~~~java
@Table("orders")
public class Order {

    @Id
    private Long id;

    @Column("customer_id")
    private Long customerId;

    private String status;
}
~~~

Trong schema, cột customer_id có thể là foreign key đến customers.id. Nhưng về mặt mô hình miền, Order chỉ giữ tham chiếu đến Customer; nó không sở hữu vòng đời của Customer.

Spring Data Relational cũng cung cấp kiểu **AggregateReference** để diễn đạt rõ hơn tham chiếu đến aggregate root khác. Ví dụ về mặt ý tưởng:

~~~java
@Table("orders")
public class Order {

    @Id
    private Long id;

    @Column("customer_id")
    private AggregateReference<Customer, Long> customer;

    private String status;
}
~~~

Khi tạo Order, có thể gán tham chiếu từ ID Customer bằng factory method **AggregateReference.to(customerId)**. Kiểu tham chiếu này giúp mô hình thể hiện rằng thuộc tính đang trỏ đến một aggregate khác thông qua ID. Nó không có nghĩa Spring Data sẽ tự tải Customer khi đọc Order.

Nếu dùng một trường Long customerId trực tiếp, ý nghĩa tham chiếu vẫn có thể được thể hiện rõ trong tên trường và domain API. AggregateReference hữu ích khi muốn biểu đạt ranh giới aggregate ngay trong kiểu dữ liệu.

### 6.2. Đọc aggregate được tham chiếu một cách tường minh

Nếu nghiệp vụ cần thông tin khách hàng, hãy truy vấn CustomerRepository riêng và kết hợp các publisher. Ví dụ dưới đây giả định Order dùng thuộc tính AggregateReference và có getter tương ứng:

~~~java
public Mono<OrderDetails> findOrderDetails(Long orderId) {
    return orderRepository.findById(orderId)
            .flatMap(order ->
                    customerRepository.findById(order.getCustomer().getId())
                            .map(customer ->
                                    new OrderDetails(order, customer)));
}
~~~

Ví dụ giả định Order có phương thức getCustomer và CustomerRepository trả về Mono<Customer>. Nếu Customer không tồn tại, cần xác định rõ nghiệp vụ sẽ báo lỗi, trả kết quả thiếu thông tin hay dùng một snapshot đã lưu trong đơn hàng. Nếu mô hình dùng trường Long customerId trực tiếp, truyền order.getCustomerId() vào findById thay cho việc lấy ID từ AggregateReference.

Cách đọc tường minh giúp người phát triển nhìn thấy chi phí truy vấn và quyết định có cần tải aggregate khác hay không. Nó cũng tránh việc một thao tác đọc Order bất ngờ kéo theo một đồ thị object lớn.

### 6.3. Không đồng nhất tham chiếu aggregate với quan hệ ORM

Trong JPA, một thuộc tính có thể được đánh dấu @ManyToOne hoặc @OneToMany và được quản lý bởi persistence context. Với Spring Data Relational, không nên mặc định dùng annotation quan hệ JPA hoặc kỳ vọng lazy loading, cascade và dirty checking tương tự.

Mô hình relational của Spring Data tập trung vào aggregate root, entity thành phần được mapping và tham chiếu bằng ID. Khi cần kết hợp dữ liệu từ nhiều aggregate, hãy dùng truy vấn phù hợp hoặc compose các thao tác reactive ở tầng ứng dụng.

## 7. Repository và phạm vi thao tác của aggregate

### 7.1. Repository đại diện cho aggregate root

Repository thường được tạo cho mỗi aggregate root cần được truy cập độc lập:

~~~java
public interface OrderRepository
        extends ReactiveCrudRepository<Order, Long> {
}

public interface CustomerRepository
        extends ReactiveCrudRepository<Customer, Long> {
}
~~~

OrderRepository quản lý Order aggregate; CustomerRepository quản lý Customer aggregate. Việc có hai repository giúp thể hiện hai ranh giới vòng đời khác nhau.

Các thao tác CRUD của ReactiveCrudRepository trả về kiểu reactive như Mono và Flux. Vì vậy, tầng service có thể ghép các bước đọc, kiểm tra, thay đổi và ghi vào cùng một pipeline mà không chặn thread để lấy kết quả.

### 7.2. Derived query và truy vấn tùy chỉnh

Có thể tạo derived query theo thuộc tính của aggregate root:

~~~java
Flux<Order> findByStatus(String status);
~~~

Khi cần SQL tùy chỉnh, có thể dùng **@Query** hoặc **DatabaseClient**. Ví dụ, truy vấn tổng hợp số đơn hàng theo khách hàng có thể là một truy vấn SQL chuyên biệt thay vì cố tạo một object graph nhiều tầng.

~~~java
@Query("""
    SELECT customer_id, COUNT(*) AS order_count
    FROM orders
    GROUP BY customer_id
    """)
Flux<CustomerOrderCount> countOrdersByCustomer();
~~~

Projection CustomerOrderCount có thể là record chứa customerId và orderCount. Câu SQL cần được điều chỉnh theo database, naming và mapping thực tế.

Spring Data Relational không cấm JOIN hoặc truy vấn nhiều bảng. Điểm cần phân biệt là truy vấn SQL có JOIN không đồng nghĩa các aggregate được hợp nhất thành một aggregate hoặc framework tự quản lý vòng đời của tất cả object trong kết quả.

### 7.3. Khi nào dùng DatabaseClient?

Repository phù hợp với CRUD và truy vấn thường gắn với aggregate root. **DatabaseClient** hữu ích khi cần:

- Câu SQL phức tạp hoặc dùng tính năng riêng của database.
- Truy vấn báo cáo và tổng hợp trên nhiều bảng.
- Projection không tương ứng trực tiếp với một aggregate.
- Batch hoặc thao tác dữ liệu đặc thù cần kiểm soát SQL.
- Truy vấn phục vụ đọc mà không cần khôi phục toàn bộ aggregate.

Dùng DatabaseClient không làm mất lợi ích reactive. Các thao tác vẫn trả về Publisher và có thể được compose trong Reactor. Tuy nhiên, khi ghi dữ liệu nghiệp vụ, cần giữ quy tắc domain và transaction boundary rõ ràng; tránh để SQL tùy ý phá vỡ invariant của aggregate.

## 8. Phạm vi hỗ trợ aggregate của Spring Data R2DBC

### 8.1. Những gì R2DBC hỗ trợ

Spring Data R2DBC sử dụng mô hình mapping của Spring Data Relational. Ở mức tổng quát, có thể:

- Ánh xạ aggregate root với bảng thông qua @Table và @Id.
- Ánh xạ thuộc tính Java với cột bằng naming strategy hoặc @Column.
- Ánh xạ value object vào cùng hàng bằng @Embedded.
- Ánh xạ collection các entity thành phần bằng @MappedCollection.
- Biểu diễn tham chiếu đến aggregate khác bằng ID hoặc AggregateReference.
- Thực hiện CRUD và truy vấn thông qua ReactiveCrudRepository.
- Dùng R2dbcEntityTemplate hoặc DatabaseClient cho thao tác linh hoạt hơn.
- Kết hợp các thao tác đọc/ghi bằng Mono, Flux và các operator Reactor.
- Sử dụng reactive transaction manager khi cần ranh giới transaction.

Điểm quan trọng: R2DBC không thay đổi nguyên tắc aggregate-centric của Spring Data Relational. Sự khác biệt chính nằm ở giao tiếp database non-blocking và API reactive.

### 8.2. Những gì R2DBC không cung cấp như một ORM đầy đủ

Spring Data R2DBC không có toàn bộ các tính năng persistence context thường gặp ở JPA/Hibernate. Cụ thể:

- **Không có lazy-loading proxy theo kiểu JPA.** Không thể gọi một getter trên entity để tự động truy vấn quan hệ chưa tải.
- **Không có dirty checking của persistence context.** Thay đổi object trong bộ nhớ không tự động được phát hiện và flush khi transaction kết thúc.
- **Không có EntityManager hoặc session cache kiểu JPA.** Mỗi thao tác repository là một thao tác dữ liệu được quản lý qua API reactive.
- **Không có cascade graph tùy ý giữa các aggregate.** Tham chiếu đến aggregate khác không khiến aggregate đó tự động được lưu hoặc xóa.
- **Không tự đồng bộ mọi quan hệ object hai chiều.** Mô hình quan hệ cần được thiết kế theo mapping relational và SQL schema.
- **Không cung cấp mọi annotation quan hệ JPA.** Các annotation như @OneToMany, @ManyToOne và @ManyToMany không phải cơ chế mapping quan hệ của Spring Data Relational.
- **Không tự biến một truy vấn nhiều bảng thành object graph có lifecycle ORM.** Cần chủ động dùng projection, JOIN hoặc compose repository query.

R2DBC là API truy cập database reactive. Từ reactive không có nghĩa là ORM tự động hoặc object graph được quản lý đầy đủ. Cần thiết kế rõ phần dữ liệu nào thuộc aggregate, phần nào là tham chiếu, và khi nào phải truy vấn dữ liệu khác.

### 8.3. Đọc aggregate không đồng nghĩa lazy loading

Với mô hình aggregate, các entity thành phần được xem là một phần của root. Spring Data Relational có thể tải những phần được mapping để tái tạo aggregate theo repository operation. Việc đó được thực hiện qua các truy vấn SQL và publisher reactive; nó không tạo proxy lazy để chờ đến lúc gọi getter mới truy vấn.

Do đó, cần chú ý kích thước aggregate. Một root có collection rất lớn có thể khiến thao tác đọc aggregate tốn nhiều tài nguyên. Nếu màn hình chỉ cần vài trường hoặc một trang dữ liệu con, hãy cân nhắc projection, query chuyên biệt hoặc phân trang thay vì tải toàn bộ aggregate.

Cách tải cụ thể và SQL được thực hiện phụ thuộc vào mapping, driver và phiên bản Spring Data. Hãy xác nhận bằng integration test và quan sát truy vấn khi mô hình có quan hệ phức tạp.

## 9. Transaction và optimistic locking

### 9.1. Nhiều câu SQL trong một thao tác aggregate

Lưu một aggregate có thể cần ghi root và các entity thành phần vào nhiều bảng. Nếu một thao tác phải bảo đảm tất cả thay đổi thành công hoặc cùng rollback, cần có transaction reactive phù hợp.

Ví dụ với service:

~~~java
import org.springframework.transaction.annotation.Transactional;
import reactor.core.publisher.Mono;

@Transactional
public Mono<Order> saveOrder(Order order) {
    return orderRepository.save(order);
}
~~~

Trong ứng dụng R2DBC, transaction manager phải được cấu hình cho ConnectionFactory. Với những thao tác kết hợp nhiều repository, hãy đặt transaction boundary bao quanh publisher tổng thể:

~~~java
@Transactional
public Mono<Void> confirmOrder(Long orderId) {
    return orderRepository.findById(orderId)
            .flatMap(order -> {
                order.confirm();
                return orderRepository.save(order);
            })
            .then();
}
~~~

Đây là ví dụ minh họa; các phương thức domain và repository phải tồn tại trong ứng dụng thực tế. Publisher cần được trả về cho Spring quản lý. Không tự gọi subscribe() bên trong phương thức transactional vì subscription đó có thể chạy ngoài transaction mà Spring đang điều phối.

Nếu cần quản lý transaction bằng code, có thể dùng **TransactionalOperator** để bao một publisher. Phạm vi transaction phải được thiết kế theo nghiệp vụ và được kiểm thử với database thật hoặc Testcontainers.

### 9.2. Optimistic locking với @Version

Khi nhiều request có thể cùng cập nhật một aggregate, optimistic locking giúp phát hiện việc một bản ghi đã bị thay đổi kể từ lần đọc trước.

~~~java
@Table("orders")
public class Order {

    @Id
    private Long id;

    @Version
    private Long version;

    private String status;
}
~~~

Spring Data sử dụng version field để kiểm tra và cập nhật phiên bản khi ghi. Nếu một tiến trình cố ghi bằng version cũ sau khi tiến trình khác đã cập nhật, thao tác có thể thất bại với lỗi optimistic locking thay vì âm thầm ghi đè dữ liệu mới.

Database cần có cột version tương ứng và schema phải nhất quán với mapping. Ứng dụng nên xử lý lỗi xung đột theo nghiệp vụ: tải lại aggregate, tính lại thay đổi hoặc trả lỗi conflict để người gọi xử lý.

Optimistic locking không thay thế transaction. Nó giải quyết xung đột cập nhật theo version; transaction giải quyết tính atomic của một nhóm thao tác database.

## 10. Thiết kế aggregate vừa đủ cho R2DBC

### 10.1. Tránh aggregate quá lớn

Một aggregate có hàng chục nghìn child rows có thể khiến thao tác tải hoặc lưu root trở nên nặng. Khi dùng Spring Data Relational, hãy xem xét liệu toàn bộ child collection có thực sự cần được quản lý cùng root hay không.

Ví dụ, một Order có vài dòng hàng phù hợp với collection trong aggregate. Một Customer có hàng triệu sự kiện đăng nhập thì không nên tải toàn bộ lịch sử sự kiện như một collection thuộc Customer chỉ vì chúng có khóa ngoại.

Các dữ liệu lớn, có vòng đời độc lập hoặc có nhu cầu truy vấn riêng nên được tách thành aggregate khác hoặc được truy cập qua query chuyên biệt.

### 10.2. Tham chiếu bằng ID thay vì object graph lớn

Tham chiếu ID giúp aggregate giữ liên kết cần thiết mà không sở hữu dữ liệu của aggregate khác. Khi cần thông tin chi tiết, service truy vấn riêng và compose publisher. Điều này làm rõ chi phí I/O và tránh tải dữ liệu ngoài phạm vi nghiệp vụ.

### 10.3. Tách query model khi nhu cầu đọc khác nhu cầu ghi

Mô hình aggregate thường tối ưu cho các quy tắc ghi và consistency boundary. Màn hình báo cáo có thể cần JOIN nhiều bảng hoặc dữ liệu tổng hợp không khớp với aggregate. Không cần ép mọi truy vấn đọc đi qua repository aggregate root.

Có thể sử dụng projection, DatabaseClient hoặc một read model riêng cho các truy vấn này. Điều quan trọng là những thao tác ghi vẫn tuân thủ quy tắc domain và không bỏ qua kiểm soát aggregate root.

### 10.4. Quan hệ nhiều-nhiều

Quan hệ many-to-many giữa hai aggregate thường cần một bảng liên kết. Không nên xem hai aggregate là collection sở hữu lẫn nhau.

Ví dụ, Student và Course có thể là hai aggregate riêng, còn Enrollment là mô hình liên kết có thể mang thêm thuộc tính như enrolledAt, grade hoặc status. Nếu Enrollment có hành vi và vòng đời riêng, có thể mô hình hóa nó thành aggregate root. Truy vấn danh sách khóa học của sinh viên có thể dùng JOIN hoặc query chuyên biệt.

Cách thiết kế cụ thể phụ thuộc nghiệp vụ. Spring Data R2DBC cho phép thực thi SQL cần thiết, nhưng không cung cấp cơ chế quản lý many-to-many object graph như ORM JPA.

## 11. So sánh aggregate trong Spring Data Relational với JPA/Hibernate

| Tiêu chí | Spring Data Relational / R2DBC | JPA / Hibernate |
|---|---|---|
| Định hướng mô hình | Aggregate-centric, root quản lý phần thuộc aggregate | Entity graph và quan hệ ORM |
| Repository | Repository thường đại diện aggregate root | Repository có thể thao tác entity theo persistence context |
| Mapping collection thành phần | @MappedCollection | @OneToMany và các annotation quan hệ |
| Tham chiếu aggregate khác | ID hoặc AggregateReference | @ManyToOne, @OneToOne và các mapping liên quan |
| Lazy loading | Không có lazy proxy kiểu JPA | Có thể hỗ trợ theo cấu hình |
| Dirty checking | Không có persistence context để tự phát hiện mọi thay đổi | Có trong persistence context |
| Cascade | Quản lý phần thuộc aggregate theo mapping; không phải cascade graph tùy ý giữa aggregate | Có các tùy chọn cascade ORM |
| I/O | R2DBC non-blocking, API reactive | Thông thường JDBC blocking |
| Transaction | Reactive transaction manager và Reactor context | Transaction imperative thường qua JDBC/JPA |

Không nên kết luận công nghệ nào tốt hơn trong mọi trường hợp. Spring Data R2DBC phù hợp với ứng dụng cần truy cập relational database theo mô hình reactive và chấp nhận cách quản lý aggregate tường minh. JPA/Hibernate phù hợp với ứng dụng cần các tính năng ORM phong phú và mô hình imperative quen thuộc.

Nếu ứng dụng cần lazy loading, dirty checking hoặc entity graph phức tạp, cần đánh giá xem R2DBC có đáp ứng được mô hình đó hay không. Có thể thay đổi cách thiết kế domain và query, nhưng không nên kỳ vọng chỉ đổi JDBC thành R2DBC là giữ nguyên toàn bộ hành vi ORM.

## 12. Những lưu ý khi triển khai thực tế

### 12.1. Thiết kế schema phù hợp với aggregate mapping

Đảm bảo foreign key, nullability, unique constraint và tên cột phù hợp với mapping. Với collection thành phần, xác định rõ cột tham chiếu root và cột thứ tự hoặc khóa collection nếu cần. Ràng buộc ở database bổ sung lớp bảo vệ cho invariant.

### 12.2. Quan sát SQL được tạo

Khi aggregate có nhiều collection hoặc mapping lồng nhau, số lượng SQL statement có thể lớn hơn dự kiến. Theo dõi log SQL trong môi trường phát triển, đo latency và kiểm tra query plan khi cần. Không bật log tham số nhạy cảm trên production.

### 12.3. Giữ transaction reactive xuyên suốt

Nếu nhiều thao tác phải atomic, trả về cùng một publisher chain và đặt transaction boundary phù hợp. Tránh gọi subscribe() hoặc block() tùy tiện trong tầng service, vì chúng có thể làm tách pipeline hoặc chặn event-loop thread.

### 12.4. Kiểm thử với database thực tế

Dùng Testcontainers hoặc database test riêng để xác nhận mapping, foreign key, collection, optimistic locking, transaction và SQL dialect. Mock repository không thể phát hiện lỗi tên cột, kiểu dữ liệu, constraint hoặc hành vi driver.

### 12.5. Không dùng mapping để thay thế quy tắc domain

Annotation chỉ mô tả cách lưu dữ liệu. Nó không thay thế việc kiểm tra trạng thái đơn hàng, quyền sở hữu, giới hạn số lượng hay invariant nghiệp vụ. Những quy tắc đó nên nằm trong domain model hoặc service chịu trách nhiệm điều phối aggregate.

## 13. Kết luận

Aggregate là ranh giới tổ chức dữ liệu và hành vi nghiệp vụ. Aggregate root là điểm truy cập chính, quản lý vòng đời các entity thành phần và bảo vệ invariant. Những aggregate khác được tham chiếu bằng ID để giữ rõ quyền sở hữu và phạm vi thay đổi.

Spring Data Relational cung cấp mapping aggregate thông qua các API như @Table, @Id, @Embedded, @MappedCollection và AggregateReference. Spring Data R2DBC dùng mô hình mapping đó với repository và publisher reactive, cho phép truy cập relational database theo hướng non-blocking.

Phạm vi hỗ trợ này đủ cho nhiều ứng dụng cần mô hình aggregate rõ ràng, nhưng không phải ORM đầy đủ. R2DBC không cung cấp persistence context, lazy loading proxy hay dirty checking kiểu JPA. Khi thiết kế, cần xác định aggregate vừa đủ, truy vấn aggregate khác một cách tường minh, quản lý transaction reactive và dùng query chuyên biệt cho nhu cầu đọc nhiều bảng hoặc báo cáo.

