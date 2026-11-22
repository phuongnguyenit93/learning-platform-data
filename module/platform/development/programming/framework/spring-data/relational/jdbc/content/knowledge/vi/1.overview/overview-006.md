# Triết lý đơn giản: không persistence context, dirty checking hay lazy loading

Trong hệ sinh thái Spring, **Spring Data JDBC** là một cách ánh xạ dữ liệu quan hệ vào đối tượng Java theo hướng đơn giản, minh bạch và lấy **aggregate** làm đơn vị làm việc. Nó cung cấp repository, ánh xạ bảng–đối tượng và quản lý vòng đời dữ liệu cần thiết, nhưng chủ động tránh nhiều cơ chế phức tạp quen thuộc trong JPA/Hibernate.

Ba đặc điểm quan trọng nhất của triết lý này là:

1. **Không có persistence context** theo mô hình JPA: framework không duy trì một vùng quản lý các entity đang được theo dõi trong suốt phiên làm việc.
2. **Không có dirty checking**: thay đổi trường của đối tượng Java không tự sinh câu lệnh `UPDATE` khi giao dịch kết thúc.
3. **Không có lazy loading tự động** cho các quan hệ được ánh xạ: framework không tạo proxy để trì hoãn việc truy vấn quan hệ đến lúc gọi getter.

Các lựa chọn đó có liên hệ với nhau. Khi đối tượng không được giữ trong một persistence context, framework không cần theo dõi trạng thái cũ để so sánh và cũng không phải quản lý proxy cùng vòng đời phiên truy cập dữ liệu. Đổi lại, ứng dụng phải thể hiện rõ **khi nào đọc, khi nào sửa và khi nào lưu**.

## 1. Spring Data JDBC nằm ở đâu trong hệ sinh thái Spring?

Cả Spring JDBC, Spring Data JDBC và Spring Data JPA đều giúp ứng dụng làm việc với cơ sở dữ liệu quan hệ, nhưng mức độ trừu tượng khác nhau.

| Công nghệ | Cách làm việc chủ yếu | Lập trình viên thường chịu trách nhiệm |
|---|---|---|
| Spring JDBC / `JdbcTemplate` | Viết SQL, truyền tham số, ánh xạ từng dòng kết quả | Thiết kế câu SQL và ánh xạ dữ liệu |
| **Spring Data JDBC** | Ánh xạ aggregate thành bảng, cung cấp repository và các thao tác lưu/tìm | Thiết kế ranh giới aggregate, chủ động gọi `save(...)`, hiểu chi phí ghi dữ liệu |
| Spring Data JPA (thường dùng Hibernate) | Ánh xạ entity và quan hệ theo JPA, có persistence context | Hiểu trạng thái entity, flush, dirty checking, fetch strategy và vòng đời session |

Spring Data JDBC không phải phiên bản rút gọn của Hibernate. Nó chọn một mô hình nhất quán khác: **aggregate root là điểm vào của dữ liệu**, các thành phần thuộc cùng aggregate được quản lý cùng vòng đời, còn quan hệ đến aggregate khác nên được thể hiện bằng định danh.

Ví dụ, một `PurchaseOrder` có thể sở hữu các `OrderLine`. Ngược lại, `Customer` thường là một aggregate độc lập: đơn hàng chỉ lưu `customerId` thay vì tải và quản lý toàn bộ đối tượng `Customer` như một thành phần bên trong.

## 2. Không có persistence context nghĩa là gì?

### 2.1. Persistence context trong JPA

Trong JPA, khi entity được tải và còn ở trạng thái *managed*, persistence context giữ thông tin để quản lý entity đó. Trong cùng một persistence context, việc tìm một entity theo cùng khóa định danh thường trả về cùng một instance đang được quản lý. Persistence context còn phối hợp việc đồng bộ dữ liệu xuống database khi *flush*.

Ví dụ về tư duy JPA:

~~~java
@Transactional
public void renameCustomer(Long id, String newName) {
    Customer customer = entityManager.find(Customer.class, id);
    customer.setName(newName);
    // Entity đang managed; JPA có thể tự phát hiện thay đổi khi flush.
}
~~~

Ở đây việc `UPDATE` có thể diễn ra khi flush/commit dù phương thức không gọi `save(...)`. Đó là hành vi gắn với trạng thái *managed* và dirty checking, không phải đặc tính của mọi công nghệ truy cập database.

### 2.2. Spring Data JDBC không quản lý đối tượng theo cách đó

Với Spring Data JDBC, một đối tượng được đọc qua repository là kết quả ánh xạ từ dữ liệu hiện có. Framework không duy trì identity map kiểu JPA để theo dõi instance đó trong suốt transaction.

~~~java
@Transactional(readOnly = true)
public void inspect(Long orderId) {
    PurchaseOrder first = repository.findById(orderId).orElseThrow();
    PurchaseOrder second = repository.findById(orderId).orElseThrow();

    System.out.println(first == second); // Thông thường: false
}
~~~

Mỗi lệnh tìm có thể truy vấn database và tạo đối tượng mới. Vì không có persistence context kiểu JPA, bạn không có quy trình làm việc dựa trên `attach`, `detach`, `merge` và `flush` các managed entity.

**Hệ quả thực tế:**

- Đừng giả định các lần tải cùng khóa sẽ dùng chung một đối tượng Java.
- Đừng trông đợi thay đổi ở một instance tự xuất hiện trong instance đã tải trước đó.
- Khi cần dữ liệu mới nhất sau một thao tác ghi, hãy truy vấn lại theo nhu cầu; đối tượng đã giữ trong bộ nhớ không được tự đồng bộ.
- Giao dịch database vẫn có thể tồn tại, nhưng giao dịch đó không biến đối tượng thành entity được theo dõi kiểu JPA.

> **Phân biệt hai khái niệm:** `@Transactional` quản lý transaction và kết nối database thông qua hạ tầng Spring. Persistence context của JPA quản lý trạng thái các entity. Spring Data JDBC hỗ trợ transaction dù không có persistence context theo mô hình JPA.

## 3. Không có dirty checking: thay đổi đối tượng không đồng nghĩa với lưu dữ liệu

*Dirty checking* là cơ chế phát hiện các trường đã thay đổi của entity được quản lý, từ đó sinh thao tác ghi khi flush. Spring Data JDBC không tự làm việc này.

Xem hai phương thức dưới đây:

~~~java
@Transactional
public void addLineWithoutSaving(Long orderId) {
    PurchaseOrder order = repository.findById(orderId).orElseThrow();
    order.addLine("BOOK-01", 2);

    // Không có repository.save(order).
    // Kết thúc transaction không tự lưu dòng hàng vừa thêm.
}

@Transactional
public void addLineAndSave(Long orderId) {
    PurchaseOrder order = repository.findById(orderId).orElseThrow();
    order.addLine("BOOK-01", 2);

    repository.save(order); // Yêu cầu Spring Data JDBC ghi aggregate.
}
~~~

Trong phương thức đầu, đối tượng Java đã thay đổi nhưng database chưa được yêu cầu ghi. Trong phương thức thứ hai, lời gọi `save(order)` thể hiện rõ thời điểm thực hiện thao tác ghi.

Có thể hình dung luồng này:

~~~text
Repository.findById(id)
        |
        v
Đọc dữ liệu từ database
        |
        v
Tạo aggregate Java
        |
        v
Gọi phương thức nghiệp vụ để đổi trạng thái
        |
        +---- Không gọi save(...) ---> Chỉ đổi trạng thái trong bộ nhớ
        |
        +---- Gọi save(...) --------> Thực thi thao tác ghi vào database
                                        |
                                        v
                                  Transaction commit
~~~

Điểm đáng chú ý là **transaction commit chỉ xác nhận các thao tác SQL đã thực hiện trong transaction**. Nó không duyệt mọi đối tượng Java đã được tải để tự quyết định phải cập nhật đối tượng nào.

### 3.1. `save(...)` không có nghĩa là chỉ cập nhật những cột đã đổi

Khi gọi `save(...)`, Spring Data JDBC làm việc với trạng thái của **aggregate** thay vì danh sách thuộc tính đã thay đổi. Tùy cấu trúc mapping và trạng thái mới/cũ, nó có thể thực hiện `INSERT`, `UPDATE` hoặc các thao tác liên quan đến phần tử con.

Đặc biệt, khi lưu lại aggregate có các thực thể con, cách lưu mặc định có thể **xóa và chèn lại các bản ghi con** để khớp trạng thái aggregate mới. Không nên mặc định rằng một thay đổi nhỏ trong collection luôn tạo đúng một câu `UPDATE` cho đúng một dòng con.

Điều này dẫn đến hai nguyên tắc thiết kế:

- Aggregate nên có ranh giới hợp lý, tránh gom một đồ thị đối tượng rất lớn vào một root.
- Những cập nhật cục bộ cần hiệu năng cao phải được đo bằng SQL thực tế. Khi cần, có thể thiết kế lại ranh giới aggregate hoặc dùng thao tác cập nhật tường minh phù hợp.

### 3.2. Giá trị trả về của `save(...)`

Thông thường nên sử dụng đối tượng mà `save(...)` trả về, đặc biệt khi thiết kế domain bất biến hoặc có khóa sinh tự động:

~~~java
PurchaseOrder newOrder = new PurchaseOrder("CUSTOMER-42");
PurchaseOrder savedOrder = repository.save(newOrder);

Long generatedId = savedOrder.getId();
~~~

Framework có thể cần cung cấp ID hoặc giá trị version sau khi lưu. Không nên giả định mọi kiểu đối tượng luôn được cập nhật tại chỗ.

## 4. Không có lazy loading: dữ liệu nào được tải phải được thiết kế rõ

Trong JPA/Hibernate, một số quan hệ có thể được ánh xạ lazy. Truy cập quan hệ sau đó có thể kích hoạt SQL thông qua proxy hoặc persistent collection, miễn là điều kiện truy cập và session phù hợp.

~~~java
// Minh họa ý tưởng JPA/Hibernate
Order order = entityManager.find(Order.class, orderId);
List<OrderLine> lines = order.getLines(); // Tùy mapping, có thể tải ở đây.
~~~

Spring Data JDBC không sử dụng proxy lazy loading tự động cho các quan hệ bên trong aggregate. Khi repository tải một aggregate theo mapping chuẩn, các thành phần thuộc aggregate được tải như một phần của thao tác đọc. Đọc `order.getLines()` sau đó là truy cập dữ liệu đã có trong đối tượng, không tự phát động một truy vấn lazy như JPA.

Điều này có lợi vì:

- Luồng truy cập database dễ quan sát: truy vấn diễn ra tại lời gọi repository hoặc truy vấn tường minh.
- Không phải dựa vào session JPA còn mở để truy cập một lazy proxy.
- Code domain không cần giả định getter có thể bất ngờ thực thi SQL.

Nhưng cần tránh hiểu sai:

- **Không có lazy loading không có nghĩa là mọi aggregate luôn chỉ cần một câu SQL.** Việc dựng một aggregate có collection vẫn có thể sử dụng nhiều truy vấn tùy mapping và cơ chế tải.
- Không có lazy loading cũng không tự loại bỏ bài toán **N+1 query**. Nếu bạn tải 100 aggregate bằng cách gọi repository 100 lần, ứng dụng vẫn thực hiện rất nhiều lần truy cập database.
- Nếu màn hình chỉ cần vài cột, không nhất thiết phải tải một aggregate lớn. Có thể dùng truy vấn rõ ràng, DTO/projection hoặc repository riêng phục vụ việc đọc.

### 4.1. Quan hệ đến aggregate khác

Giả sử đơn hàng cần biết khách hàng và sản phẩm. Trong mô hình Spring Data JDBC, thông thường:

~~~text
PurchaseOrder (aggregate root)
    |
    +-- OrderLine         (thành phần thuộc PurchaseOrder)
    |
    +-- customerId        (định danh tham chiếu đến Customer)

Customer (aggregate root riêng)
Product  (aggregate root riêng)
~~~

Không nên đặt trực tiếp một `Customer` độc lập vào trường quan hệ của `PurchaseOrder` rồi kỳ vọng Spring Data JDBC xử lý giống `@ManyToOne(fetch = LAZY)` của JPA. Hãy lưu khóa tham chiếu và chủ động tìm `Customer` qua repository hoặc một truy vấn phù hợp khi ứng dụng thực sự cần dữ liệu của khách hàng.

Spring Data JDBC cũng cung cấp kiểu `AggregateReference<T, ID>` để biểu diễn tham chiếu bằng ID ở những mô hình thích hợp; nó không mang ý nghĩa tự tải đối tượng được tham chiếu.

## 5. Ví dụ hoàn chỉnh: một aggregate đơn hàng

Ví dụ dưới đây sử dụng Spring Boot 3.x, Spring Data JDBC và mô hình quan hệ đơn giản. Mục tiêu là cho thấy việc đọc, thay đổi và lưu được thực hiện minh bạch.

### 5.1. Thiết kế bảng

Giả sử sử dụng cơ sở dữ liệu hỗ trợ cú pháp identity tương ứng:

~~~sql
CREATE TABLE purchase_orders (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    version BIGINT,
    customer_code VARCHAR(80) NOT NULL
);

CREATE TABLE order_lines (
    order_id BIGINT NOT NULL,
    line_position INTEGER NOT NULL,
    sku VARCHAR(100) NOT NULL,
    quantity INTEGER NOT NULL,
    PRIMARY KEY (order_id, line_position),
    CONSTRAINT fk_order_line_order
        FOREIGN KEY (order_id) REFERENCES purchase_orders(id)
);
~~~

Bảng `order_lines` có khóa ngoại `order_id` trỏ về aggregate root và `line_position` thể hiện vị trí phần tử trong danh sách.

Cú pháp `GENERATED BY DEFAULT AS IDENTITY` là ví dụ; khi dùng PostgreSQL, MySQL, H2 hoặc hệ khác, cần chọn DDL phù hợp với database thực tế.

### 5.2. Aggregate root `PurchaseOrder`

~~~java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Version;
import org.springframework.data.relational.core.mapping.MappedCollection;
import org.springframework.data.relational.core.mapping.Table;

@Table("purchase_orders")
public class PurchaseOrder {

    @Id
    private Long id;

    @Version
    private Long version;

    private String customerCode;

    @MappedCollection(idColumn = "order_id", keyColumn = "line_position")
    private List<OrderLine> lines = new ArrayList<>();

    private PurchaseOrder() {
        // Dùng cho quá trình materialize đối tượng từ database.
    }

    public PurchaseOrder(String customerCode) {
        if (customerCode == null || customerCode.isBlank()) {
            throw new IllegalArgumentException("Customer code is required");
        }
        this.customerCode = customerCode;
    }

    public void addLine(String sku, int quantity) {
        if (sku == null || sku.isBlank()) {
            throw new IllegalArgumentException("SKU is required");
        }
        if (quantity <= 0) {
            throw new IllegalArgumentException("Quantity must be positive");
        }
        lines.add(new OrderLine(sku, quantity));
    }

    public Long getId() {
        return id;
    }

    public Long getVersion() {
        return version;
    }

    public String getCustomerCode() {
        return customerCode;
    }

    public List<OrderLine> getLines() {
        return Collections.unmodifiableList(lines);
    }
}
~~~

`@Id` xác định khóa chính của root. `@Version` bật cơ chế **optimistic locking** khi lưu aggregate. `@MappedCollection` mô tả các phần tử thuộc aggregate và cột dùng để lưu liên kết/vị trí.

Đây là kiểu ánh xạ theo aggregate ownership: `OrderLine` thuộc vòng đời của `PurchaseOrder`. Collection không phải quan hệ lazy proxy.

### 5.3. Thành phần con `OrderLine`

~~~java
import org.springframework.data.relational.core.mapping.Table;

@Table("order_lines")
public class OrderLine {

    private String sku;
    private int quantity;

    private OrderLine() {
        // Dùng cho quá trình materialize.
    }

    public OrderLine(String sku, int quantity) {
        this.sku = sku;
        this.quantity = quantity;
    }

    public String getSku() {
        return sku;
    }

    public int getQuantity() {
        return quantity;
    }
}
~~~

Trong mô hình này, `OrderLine` là thành phần được lưu qua aggregate root. Ứng dụng không cần một repository độc lập để thay đổi vòng đời của từng `OrderLine`.

### 5.4. Repository

~~~java
import org.springframework.data.repository.CrudRepository;

public interface PurchaseOrderRepository
        extends CrudRepository<PurchaseOrder, Long> {
}
~~~

Spring Data JDBC triển khai các thao tác CRUD từ interface repository. Bạn không phải tự viết `INSERT` và `SELECT` cơ bản cho aggregate.

### 5.5. Application service thể hiện rõ thời điểm ghi

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class PurchaseOrderService {

    private final PurchaseOrderRepository repository;

    public PurchaseOrderService(PurchaseOrderRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public Long createOrder(String customerCode) {
        PurchaseOrder order = new PurchaseOrder(customerCode);
        PurchaseOrder saved = repository.save(order);
        return saved.getId();
    }

    @Transactional
    public void addProduct(Long orderId, String sku, int quantity) {
        PurchaseOrder order = repository.findById(orderId)
                .orElseThrow(() -> new IllegalArgumentException(
                        "Order not found: " + orderId));

        order.addLine(sku, quantity);
        repository.save(order);
    }

    @Transactional(readOnly = true)
    public PurchaseOrder getOrder(Long orderId) {
        return repository.findById(orderId)
                .orElseThrow(() -> new IllegalArgumentException(
                        "Order not found: " + orderId));
    }
}
~~~

Khi gọi `addProduct(...)`, ứng dụng thực hiện ba bước rành mạch:

1. Repository đọc `PurchaseOrder` từ database.
2. Phương thức domain `addLine(...)` thay đổi trạng thái đối tượng trong bộ nhớ.
3. Repository `save(...)` ghi trạng thái aggregate xuống database, trong phạm vi transaction do `@Transactional` quản lý.

Nếu bỏ bước 3, thay đổi ở bước 2 không tự được lưu. Nếu lưu thất bại và transaction bị rollback, các thao tác SQL trong transaction được rollback theo cơ chế transaction của database.

> Các class Java ở các đoạn trên tương ứng những file nguồn riêng trong một project. Ví dụ tập trung vào ánh xạ và vòng đời lưu dữ liệu; phần cấu hình datasource, dependency và migration được chuẩn bị như một ứng dụng Spring Boot thông thường.

## 6. Điều gì diễn ra khi lưu aggregate có collection?

Xét đơn hàng hiện có hai dòng hàng, sau đó thêm dòng thứ ba:

~~~text
Database ban đầu:
  purchase_orders: Order #10
  order_lines:      [A, B]

Trong Java sau addLine(...):
  PurchaseOrder #10
    lines:          [A, B, C]

Sau repository.save(order):
  Database phản ánh trạng thái aggregate [A, B, C]
~~~

Điều quan trọng là framework **không có bản chụp trạng thái managed entity kiểu JPA** để kết luận rằng chỉ dòng C thay đổi. Theo chiến lược ghi aggregate, các bản ghi con có thể được xử lý lại để tái tạo collection.

Vì vậy, khi dữ liệu có nhiều thành phần con, hãy cân nhắc:

- **Aggregate boundary:** Chỉ đưa dữ liệu vào cùng aggregate nếu chúng thực sự cần được kiểm soát nhất quán cùng một root.
- **Tần suất ghi:** Aggregate lớn nhưng chỉ thay đổi một phần tử thường xuyên có thể phát sinh chi phí ghi đáng kể.
- **Database constraints:** Khóa ngoại và ràng buộc duy nhất phải phù hợp với thứ tự ghi/xóa/chèn khi lưu collection.
- **Concurrency:** Nhiều yêu cầu có thể cùng đọc rồi lưu một root; dùng versioning hoặc quy tắc xử lý xung đột thích hợp.
- **Read model:** Với báo cáo và danh sách chỉ đọc, truy vấn DTO thường hợp lý hơn việc dựng toàn bộ aggregate.

Nếu hai đối tượng có vòng đời độc lập, nên tách chúng thành hai aggregate và liên kết bằng ID. Khi đó việc ghi từng aggregate là thao tác tường minh, dễ cân nhắc về tính nhất quán và hiệu năng.

## 7. Giao dịch và optimistic locking vẫn hoạt động

Không có persistence context và dirty checking **không có nghĩa là không hỗ trợ transaction**.

Spring Data JDBC dùng cơ chế transaction của Spring. Với `@Transactional`, nhiều thao tác repository có thể cùng tham gia một transaction khi dùng transaction manager và datasource được cấu hình thích hợp.

~~~java
@Transactional
public void changeTwoOrders(Long firstId, Long secondId) {
    PurchaseOrder first = repository.findById(firstId).orElseThrow();
    PurchaseOrder second = repository.findById(secondId).orElseThrow();

    first.addLine("PENCIL", 1);
    second.addLine("PAPER", 2);

    repository.save(first);
    repository.save(second);
    // Nếu có lỗi khiến transaction rollback,
    // các thao tác SQL trong transaction sẽ không được commit.
}
~~~

### 7.1. Optimistic locking với `@Version`

Khi root có trường `@Version`, repository có thể kiểm tra version hiện tại trong lúc cập nhật. Nếu một giao dịch khác đã thay đổi aggregate làm version trong database không còn khớp, thao tác lưu có thể thất bại với ngoại lệ thuộc nhóm `OptimisticLockingFailureException`.

Ví dụ theo thời gian:

| Thời điểm | Giao dịch A | Giao dịch B |
|---|---|---|
| T1 | Đọc Order #10, version 3 | |
| T2 | | Đọc Order #10, version 3 |
| T3 | Lưu thay đổi, version tăng | |
| T4 | | Cố lưu bản đã đọc ở version 3 |
| Kết quả | Ghi thành công | Phát hiện xung đột version; cần xử lý phù hợp |

Versioning là cơ chế kiểm soát ghi đồng thời, **không phải** dirty checking. Nó được dùng khi chương trình thực sự gọi thao tác lưu.

Ứng dụng cần quyết định có nên báo xung đột, đọc lại để người dùng chỉnh sửa hoặc thử lại tác vụ theo quy tắc nghiệp vụ. Không nên thử lại mù quáng khi thao tác có tác dụng phụ.

### 7.2. Transaction không làm phát sinh lazy loading

Một phương thức có `@Transactional` vẫn không làm cho `getLines()` trở thành lazy getter kiểu Hibernate. Transaction bảo vệ các thao tác database đã thực hiện; nó không tạo persistence context JPA hoặc thay đổi cách fetch của Spring Data JDBC.

## 8. Trường hợp nên chọn cách tiếp cận này

Spring Data JDBC thường phù hợp khi:

- Domain có ranh giới aggregate rõ, số lượng quan hệ con được kiểm soát tốt.
- Nhóm muốn luồng đọc/ghi minh bạch và dễ suy luận.
- Mô hình nghiệp vụ cho phép gọi `save(...)` rõ ràng sau khi thay đổi.
- Không muốn các thao tác SQL có thể xuất hiện do việc truy cập lazy proxy.
- Các tác vụ chủ yếu là CRUD theo aggregate, kết hợp một số truy vấn SQL riêng để đọc báo cáo.

JPA/Hibernate có thể phù hợp hơn khi ứng dụng cần một mô hình entity graph phong phú, nhiều chiến lược fetch, quản lý entity dài trong transaction và tận dụng sâu các khả năng của ORM. Những tính năng đó hữu ích trong nhiều hệ thống, nhưng đòi hỏi hiểu rõ trạng thái entity và chi phí truy vấn.

Đối với Spring Data JDBC, sự đơn giản chủ yếu nằm ở **mô hình vòng đời**, không có nghĩa việc thiết kế schema, query, transaction hay tối ưu hiệu năng tự động trở nên đơn giản.

## 9. Các hiểu lầm thường gặp

| Nhận định | Cách hiểu đúng |
|---|---|
| “Có `@Transactional` thì sửa object xong sẽ tự lưu.” | Không. Cần thao tác ghi như `repository.save(...)`. |
| “Không có persistence context nên mỗi method repository chạy ngoài transaction.” | Không. Spring transaction vẫn quản lý kết nối và tính nguyên tử của các thao tác SQL. |
| “Không lazy loading tức là một `findById(...)` luôn chạy một câu SQL.” | Không. Việc tải một aggregate có collection có thể cần nhiều câu SQL. |
| “Đã gọi `save(...)` thì chỉ trường bị sửa mới được `UPDATE`.” | Không có dirty checking để bảo đảm điều đó; các phần tử con có thể được ghi lại. |
| “Tải cùng ID hai lần luôn nhận cùng Java object.” | Không có identity map kiểu JPA bảo đảm điều đó. |
| “Spring Data JDBC chỉ là `JdbcTemplate` đổi tên.” | Không. Nó cung cấp ánh xạ aggregate, repository, lifecycle và optimistic locking ở mức trừu tượng cao hơn. |
| “Không có lazy loading thì hoàn toàn không thể gặp N+1 query.” | Không. Vòng lặp gọi repository nhiều lần vẫn có thể tạo N+1 hoặc nhiều truy vấn khác. |
| “Muốn tham chiếu Customer thì bắt buộc đưa Customer vào Order.” | Không. Thường nên lưu `customerId` và tải Customer tường minh như một aggregate khác. |

## 10. Bài tập tự suy luận

**Tình huống A — quên lưu:** Một service gọi `findById(...)`, thay đổi `customerCode` rồi kết thúc `@Transactional` mà không gọi `save(...)`. Database có được cập nhật không?

**Đáp án:** Không có cập nhật tự động chỉ vì đối tượng thay đổi. Chương trình phải chủ động gọi thao tác ghi.

**Tình huống B — đọc hai lần:** Trong cùng một transaction, hai lệnh `findById(10L)` trả về hai instance Java riêng. Đây có phải lỗi mapping không?

**Đáp án:** Không. Spring Data JDBC không cung cấp identity map của persistence context theo mô hình JPA.

**Tình huống C — mở collection:** Mã đã có `PurchaseOrder` từ repository, sau đó gọi `getLines()`. Có phải mặc định khởi chạy lazy query khi gọi getter không?

**Đáp án:** Không. Các thành phần được ánh xạ bên trong aggregate được tải theo cơ chế đọc aggregate, không thông qua proxy lazy mặc định.

**Tình huống D — cập nhật một dòng hàng:** Một đơn có hàng trăm `OrderLine` và người dùng chỉ sửa một số lượng. Có thể kết luận `save(order)` luôn chỉ chạy một câu `UPDATE order_lines` không?

**Đáp án:** Không. Cần hiểu chiến lược lưu aggregate và kiểm tra SQL phát sinh. Nếu việc sửa nhỏ nhưng diễn ra thường xuyên, hãy cân nhắc lại aggregate hoặc cách cập nhật.

## 11. Ghi nhớ mô hình hoạt động

~~~text
Spring Data JPA (minh họa phổ biến)
  load entity -> managed state -> sửa field
                            -> dirty checking / flush -> SQL

Spring Data JDBC
  repository.findById -> tạo aggregate -> sửa trạng thái trong Java
                                          |
                                          v
                                     repository.save
                                          |
                                          v
                                      Thực thi SQL
~~~

Ba lựa chọn **không persistence context, không dirty checking, không lazy loading tự động** là những phần của cùng một triết lý: Spring Data JDBC ưu tiên ranh giới aggregate và thao tác dữ liệu tường minh. Khi dùng nó, hãy thiết kế aggregate nhỏ và có ý nghĩa nghiệp vụ, chủ động chọn lúc tải/lưu, và đánh giá tác động SQL của từng lần `save(...)`.
