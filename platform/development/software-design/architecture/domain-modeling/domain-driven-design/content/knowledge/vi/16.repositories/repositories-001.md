# Repository: giao diện truy xuất aggregate theo ngôn ngữ miền

Trong Domain-Driven Design (DDD), **Repository** là cơ chế cung cấp giao diện để tìm và lưu các Aggregate trong mô hình miền. Nó giúp mã nghiệp vụ làm việc với Aggregate Root như thể đang truy cập một tập hợp đối tượng, mà không cần biết dữ liệu được lưu trong cơ sở dữ liệu quan hệ, tài liệu, bộ nhớ hay một cơ chế khác.

Repository không đơn thuần là một lớp bao quanh câu lệnh SQL. Nó biểu diễn nhu cầu truy xuất của mô hình bằng ngôn ngữ của Bounded Context, thường tập trung vào một Aggregate Root. Các quy tắc nghiệp vụ vẫn thuộc Aggregate; Repository chịu trách nhiệm tìm và lưu Aggregate; Infrastructure cung cấp cách thực hiện bằng công nghệ cụ thể.

Ví dụ, Order Context có thể định nghĩa OrderRepository với các thao tác tìm đơn theo OrderId và lưu Order. Application Service tải Order qua Repository, gọi hành vi như order.confirm(), rồi lưu Aggregate. Order không biết JPA, SQL hay bảng dữ liệu nào được dùng.

## 1. Repository là gì?

Repository là một abstraction trung gian giữa mô hình miền và cơ chế lưu trữ. Nó cung cấp cách tìm Aggregate theo các tiêu chí có ý nghĩa đối với ứng dụng, đồng thời hỗ trợ lưu thay đổi của Aggregate.

Trong DDD, Repository thường có các đặc điểm:

- **Tập trung vào Aggregate Root:** một Repository thường tương ứng với một loại Aggregate Root.
- **Dùng ngôn ngữ miền:** tên và tham số thể hiện khái niệm như OrderId, CustomerId hoặc trạng thái đơn hàng.
- **Ẩn chi tiết lưu trữ:** caller không cần biết câu SQL, cấu trúc bảng, ORM hoặc cách ánh xạ dữ liệu.
- **Trả về mô hình miền:** khi tải dữ liệu, Repository cung cấp Aggregate có thể thực hiện hành vi nghiệp vụ.
- **Hỗ trợ lưu Aggregate:** thay đổi được lưu theo cơ chế phù hợp với giao dịch và tính nhất quán của hệ thống.

Ví dụ, các phương thức có thể là:

~~~java
import java.util.Optional;

public interface OrderRepository {
    Optional<Order> findById(Order.OrderId id);
    void save(Order order);
}
~~~

Hợp đồng này diễn đạt nhu cầu của Order Context. Nó không tiết lộ Order được lưu trong bảng orders, document store hay một cơ chế khác.

## 2. Vì sao DDD cần Repository?

Nếu mô hình miền tự truy cập cơ sở dữ liệu, các Entity có thể phụ thuộc vào SQL, ORM hoặc framework. Quy tắc nghiệp vụ khi đó khó kiểm thử độc lập và khó thay đổi công nghệ lưu trữ.

Nếu Application Service chứa trực tiếp câu truy vấn và ánh xạ dữ liệu, trách nhiệm truy xuất bị trộn với điều phối use case. Nhiều use case có thể lặp lại cùng cách tìm Aggregate, tạo ra các cách tải và lưu không nhất quán.

Repository giúp:

- **Tách mô hình miền khỏi lưu trữ:** Domain không cần biết dữ liệu nằm ở đâu hoặc được ánh xạ thế nào.
- **Giữ quyền sở hữu Aggregate rõ ràng:** bên ngoài lấy Root rồi gọi hành vi thay vì sửa trực tiếp các bản ghi.
- **Giảm lặp truy vấn:** các quy tắc tìm Aggregate có thể được tổ chức tại một abstraction phù hợp.
- **Dễ kiểm thử use case:** có thể thay Repository thật bằng implementation trong bộ nhớ hoặc test double khi cần.
- **Hỗ trợ thay đổi công nghệ:** thay JDBC bằng JPA hoặc đổi cách lưu trữ ít ảnh hưởng đến hợp đồng miền.
- **Làm rõ ngôn ngữ truy xuất:** phương thức như findPendingOrdersForCustomer() có ý nghĩa hơn một truy vấn SQL bị lặp trong nhiều nơi.

Repository không tự làm cho mô hình tốt. Một Repository có quá nhiều phương thức chung chung hoặc trả về cấu trúc dữ liệu của ORM có thể làm ranh giới giữa miền và hạ tầng bị mờ.

## 3. Repository thường được thiết kế quanh Aggregate Root

Một Aggregate là ranh giới nhất quán gồm Root và các đối tượng bên trong. Bên ngoài Aggregate chỉ tương tác thông qua Root. Vì vậy, Repository thường tải và lưu Aggregate Root như một đơn vị.

Ví dụ Order Aggregate có thể chứa:

- Order: Aggregate Root.
- OrderLine: các dòng hàng thuộc vòng đời của Order.
- Money: Value Object biểu diễn tiền.
- Address: Value Object biểu diễn địa chỉ.

Trong trường hợp này, thường chỉ cần OrderRepository. Khi cần sửa một OrderLine, Application tải Order, gọi hành vi trên Root như order.changeLineQuantity(...), rồi lưu Order. Không cần tạo OrderLineRepository nếu OrderLine không có vòng đời độc lập và không được truy cập như một Aggregate riêng.

### 3.1. Vì sao không tạo Repository cho mọi Entity?

Nếu tạo Repository cho từng Entity hoặc từng bảng, caller có thể tải một đối tượng con rồi sửa nó mà không thông qua Aggregate Root. Điều đó có thể phá vỡ bất biến của Aggregate.

Ví dụ, nếu OrderLineRepository cho phép xóa dòng cuối cùng của một đơn đã xác nhận, nó có thể bỏ qua quy tắc mà Order cần bảo vệ. Khi mọi thay đổi đi qua Order Root, mô hình có một điểm kiểm soát nhất quán.

Một Entity bên trong Aggregate có thể có định danh riêng nhưng điều đó không tự động khiến nó trở thành Aggregate Root. Hãy xác định ranh giới dựa trên bất biến, vòng đời và quyền sở hữu nghiệp vụ.

### 3.2. Khi nào một đối tượng cần Repository riêng?

Một đối tượng có thể là Aggregate Root riêng khi:

- Nó có vòng đời và quy tắc nhất quán độc lập.
- Các hành vi của nó cần được thay đổi mà không phải tải Aggregate khác.
- Nó có thể được tham chiếu từ nhiều Aggregate khác.
- Các cập nhật của nó có nhịp độ hoặc yêu cầu cạnh tranh riêng.

Ví dụ, Customer có thể là Aggregate Root riêng với CustomerRepository; Order tham chiếu Customer bằng CustomerId. Order không giữ trực tiếp toàn bộ Customer Aggregate chỉ để ghi nhận người mua.

## 4. Repository khác DAO và Data Mapper như thế nào?

Repository, DAO và Data Mapper đều có thể xuất hiện trong tầng truy xuất dữ liệu, nhưng chúng mô tả các trách nhiệm khác nhau.

| Khái niệm | Trách nhiệm | Góc nhìn |
| --- | --- | --- |
| Repository | Cung cấp giao diện tìm và lưu Aggregate theo nhu cầu của mô hình miền. | Domain/Application |
| DAO (Data Access Object) | Đóng gói thao tác truy cập dữ liệu hoặc câu truy vấn cụ thể. | Data access |
| Data Mapper | Chuyển đổi giữa mô hình miền và cấu trúc lưu trữ. | Persistence mapping |
| ORM | Hỗ trợ ánh xạ đối tượng và dữ liệu quan hệ. | Công nghệ triển khai |

Trong một ứng dụng, Repository implementation có thể sử dụng DAO, Data Mapper và ORM. Những khái niệm này có thể phối hợp nhưng không nhất thiết là một thứ.

Ví dụ, JpaOrderRepository có thể dùng Spring Data repository nội bộ và OrderMapper để chuyển đổi giữa Order và OrderEntity. Caller chỉ biết OrderRepository, không biết các thành phần kỹ thuật đó.

## 5. Thiết kế giao diện Repository theo ngôn ngữ miền

Giao diện Repository nên thể hiện các cách truy xuất có ý nghĩa với use case hoặc mô hình miền. Hãy tránh để hợp đồng trở thành bản sao của API ORM.

### 5.1. Dùng định danh có kiểu

Thay vì truyền String cho mọi loại ID, có thể dùng Value Object như OrderId, CustomerId hoặc ProductId. Kiểu miền giúp tránh nhầm định danh và cho phép xác thực ở một nơi.

~~~java
public record OrderId(String value) {
    public OrderId {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException("Order ID is required");
        }
    }
}
~~~

### 5.2. Chọn phương thức tìm kiếm theo nhu cầu thực tế

Một hợp đồng đơn giản có thể gồm:

~~~java
public interface OrderRepository {
    Optional<Order> findById(Order.OrderId id);
    void save(Order order);
    void remove(Order order);
}
~~~

Tùy ngữ cảnh, có thể cần các phương thức như:

- findByOrderNumber(OrderNumber number)
- findOpenOrderForCustomer(CustomerId customerId)
- existsByOrderNumber(OrderNumber number)

Tên phương thức nên diễn đạt điều kiện nghiệp vụ hoặc nhu cầu truy xuất ổn định. Không nên thêm hàng chục phương thức chỉ vì có thể tưởng tượng ra một bộ lọc; hãy để use case thực tế dẫn dắt thiết kế.

### 5.3. Tránh giao diện CRUD chung chung

Một interface tổng quát như:

~~~java
interface GenericRepository<T, ID> {
    T get(ID id);
    void insert(T entity);
    void update(T entity);
    void delete(ID id);
    List<T> findAll();
}
~~~

có thể hữu ích trong một số framework hoặc lớp hạ tầng, nhưng không nên mặc định dùng nó làm ngôn ngữ Repository của mọi Aggregate. Mỗi Aggregate có nhu cầu và vòng đời riêng. Ví dụ, xóa Order có thể không phải thao tác xóa vật lý mà là hủy đơn theo chính sách; phương thức CRUD chung không diễn đạt được sự khác biệt đó.

Không phải mọi thao tác đều phải mang tên nghiệp vụ riêng. findById() và save() có thể là abstraction phù hợp. Điều quan trọng là không để hợp đồng ép mô hình vào các thao tác kỹ thuật không phản ánh ý nghĩa miền.

### 5.4. Xác định rõ ngữ nghĩa của save()

Một số Repository dùng save() cho cả tạo mới và cập nhật. Một số khác tách add() và update(). Chọn cách nào tùy vòng đời Aggregate và cơ chế persistence, nhưng hợp đồng cần rõ:

- Khi nào một Aggregate được xem là mới?
- Ai cấp định danh?
- Lưu một Aggregate đã tồn tại có thể tạo bản ghi mới không?
- Nếu định danh đã tồn tại nhưng phiên bản cũ, kết quả là gì?
- Xóa là xóa vật lý, đánh dấu ngừng hoạt động hay thực hiện hành vi nghiệp vụ?

Nếu thao tác xóa là quyết định nghiệp vụ, thường nên thể hiện bằng hành vi như order.cancel(reason), còn Repository chỉ lưu trạng thái mới. remove() phù hợp hơn khi thật sự cần loại Aggregate khỏi tập hợp lưu trữ theo quy tắc kỹ thuật hoặc vòng đời đã định nghĩa.

### 5.5. Tránh trả về kiểu của ORM hoặc cơ sở dữ liệu

Không nên để Domain/Application nhận Page<EntityJpa>, CriteriaQuery, ResultSet, EntityManager hoặc một kiểu phụ thuộc nhà cung cấp. Hãy trả về Aggregate, Value Object hoặc kiểu kết quả thuộc ứng dụng.

Đối với truy vấn báo cáo, có thể dùng projection hoặc read model riêng. Không cần ép mọi kết quả truy vấn thành Aggregate nếu caller chỉ cần dữ liệu hiển thị.

## 6. Đặt interface và implementation ở đâu?

Một cách tổ chức phổ biến là đặt abstraction gần module bên trong sở hữu nhu cầu, còn implementation nằm ở Infrastructure.

Ví dụ:

~~~text
com.example.order
├── domain
│   ├── Order.java
│   ├── OrderId.java
│   └── OrderRepository.java
├── application
│   └── PlaceOrderService.java
└── infrastructure
    └── persistence
        ├── JpaOrderRepository.java
        ├── OrderEntity.java
        └── OrderMapper.java
~~~

Domain định nghĩa OrderRepository bằng ngôn ngữ miền. Infrastructure phụ thuộc vào interface đó và cung cấp implementation dùng công nghệ lưu trữ.

Trong một số kiến trúc, interface Repository được đặt ở Application Layer vì use case là bên trực tiếp cần cổng truy xuất. Cách này cũng có thể phù hợp, miễn là mô hình miền không phụ thuộc vào implementation hạ tầng và hợp đồng không bị lộ chi tiết persistence.

Không có quy tắc rằng mọi dự án phải đặt interface trong cùng một package. Hãy đặt nó gần nơi sở hữu ý nghĩa và nhu cầu của abstraction, đồng thời duy trì hướng phụ thuộc vào trong.

## 7. Ví dụ xuyên suốt: OrderRepository với Java

Giả sử Order Aggregate có các hành vi:

- Đơn nháp có thể thêm dòng hàng.
- Chỉ đơn có dòng hàng hợp lệ mới được xác nhận.
- Đơn đã xác nhận không được chỉnh sửa danh sách dòng theo luồng thông thường.
- Mỗi đơn có OrderId riêng.

### 7.1. Aggregate Root

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

public final class Order {
    private final OrderId id;
    private final List<OrderLine> lines = new ArrayList<>();
    private OrderStatus status = OrderStatus.DRAFT;

    public Order(OrderId id) {
        this.id = Objects.requireNonNull(id);
    }

    public void addLine(OrderLine line) {
        requireDraft();
        lines.add(Objects.requireNonNull(line));
    }

    public void confirm() {
        requireDraft();
        if (lines.isEmpty()) {
            throw new IllegalStateException("An empty order cannot be confirmed");
        }
        status = OrderStatus.CONFIRMED;
    }

    public OrderId id() {
        return id;
    }

    public OrderStatus status() {
        return status;
    }

    public List<OrderLine> lines() {
        return List.copyOf(lines);
    }

    private void requireDraft() {
        if (status != OrderStatus.DRAFT) {
            throw new IllegalStateException("Only draft orders can be changed");
        }
    }

    public record OrderId(String value) {
        public OrderId {
            if (value == null || value.isBlank()) {
                throw new IllegalArgumentException("Order ID is required");
            }
        }
    }

    public record OrderLine(String productCode, int quantity) {
        public OrderLine {
            if (productCode == null || productCode.isBlank() || quantity <= 0) {
                throw new IllegalArgumentException("Invalid order line");
            }
        }
    }

    public enum OrderStatus {
        DRAFT, CONFIRMED
    }
}
~~~

Đây là ví dụ rút gọn; trong dự án thật, OrderLine và OrderId có thể được tách thành kiểu riêng. Các quy tắc về giá, thanh toán, tồn kho và hủy đơn cần được bổ sung theo chính sách đã xác nhận.

### 7.2. Repository interface

~~~java
import java.util.Optional;

public interface OrderRepository {
    Optional<Order> findById(Order.OrderId id);
    void save(Order order);
}
~~~

Application chỉ cần biết hợp đồng này. Nó không biết Order được lưu trong một hay nhiều bảng.

### 7.3. Application Service sử dụng Repository

~~~java
public final class ConfirmOrderService {
    private final OrderRepository orders;

    public ConfirmOrderService(OrderRepository orders) {
        this.orders = orders;
    }

    public void confirm(Order.OrderId orderId) {
        Order order = orders.findById(orderId)
                .orElseThrow(() -> new OrderNotFound(orderId));

        order.confirm();
        orders.save(order);
    }
}
~~~

OrderNotFound là exception hoặc kết quả nghiệp vụ được định nghĩa trong ứng dụng. Application Service điều phối tải, gọi hành vi và lưu Aggregate. Nó không tự sửa status hoặc kiểm tra lại toàn bộ quy tắc của Order.

### 7.4. Infrastructure implementation

Implementation có thể dùng JPA, JDBC hoặc một cơ chế lưu trữ khác. Ví dụ khái niệm:

~~~java
public final class JpaOrderRepository implements OrderRepository {
    private final SpringDataOrderJpaRepository database;
    private final OrderMapper mapper;

    public JpaOrderRepository(
            SpringDataOrderJpaRepository database,
            OrderMapper mapper
    ) {
        this.database = database;
        this.mapper = mapper;
    }

    @Override
    public Optional<Order> findById(Order.OrderId id) {
        return database.findById(id.value())
                .map(mapper::toDomain);
    }

    @Override
    public void save(Order order) {
        database.save(mapper.toEntity(order));
    }
}
~~~

SpringDataOrderJpaRepository, OrderMapper và các kiểu persistence là chi tiết hạ tầng được giả định có sẵn. JpaOrderRepository chuyển đổi dữ liệu giữa mô hình lưu trữ và Aggregate. Domain không import các kiểu này.

### 7.5. Repository lưu Aggregate như một đơn vị

Order có thể được ánh xạ thành một bản ghi orders và nhiều bản ghi order_lines. Dù cơ sở dữ liệu dùng nhiều bảng, Repository vẫn cung cấp Aggregate Root theo hợp đồng. Khi tải Order, implementation cần khôi phục đủ dữ liệu cần thiết để Root bảo vệ các bất biến trong hành vi tiếp theo.

Không nên trả về một Order chỉ có một phần dữ liệu nhưng vẫn cho phép gọi hành vi cần thông tin chưa được tải. Nếu cần tối ưu hiệu năng, hãy xác định rõ aggregate loading strategy hoặc dùng read model cho truy vấn chỉ đọc.

## 8. Repository và ranh giới giao dịch

Repository chịu trách nhiệm truy xuất và lưu Aggregate, nhưng không nhất thiết là nơi quản lý toàn bộ giao dịch của use case. Application Layer thường xác định ranh giới ca sử dụng; transaction manager hoặc framework hạ tầng thực thi giao dịch.

Ví dụ:

1. Application bắt đầu transaction.
2. Repository tải Order.
3. Application gọi order.confirm().
4. Repository lưu Aggregate.
5. Transaction commit.

Nếu hành vi thất bại, transaction có thể rollback theo cơ chế triển khai. Chi tiết annotation hoặc API transaction thuộc Application/Infrastructure, không nên đưa vào Entity.

### 8.1. Một Repository không đồng nghĩa một transaction

Một use case có thể gọi nhiều Repository trong cùng transaction cơ sở dữ liệu nếu các Aggregate và dữ liệu cùng nằm trong một transaction boundary được hỗ trợ. Nhưng nếu các Repository trỏ đến những cơ sở dữ liệu hoặc Bounded Context độc lập, không thể mặc định rằng một transaction cục bộ sẽ bao phủ tất cả.

Khi phối hợp nhiều Aggregate độc lập hoặc nhiều hệ thống, có thể cần Domain Event, Outbox, Saga hoặc quy trình bù trừ. Repository không tự giải quyết tính nhất quán xuyên dịch vụ.

### 8.2. Xử lý cập nhật đồng thời

Hai request có thể cùng tải một phiên bản Aggregate rồi cùng sửa. Nếu không kiểm soát, lần ghi sau có thể ghi đè thay đổi của lần ghi trước.

Một số cơ chế thường dùng:

- **Optimistic locking:** Aggregate hoặc bản ghi có version; thao tác lưu kiểm tra version hiện tại.
- **Pessimistic locking:** cơ sở dữ liệu khóa dữ liệu trong phạm vi transaction khi cần.
- **Unique constraint:** bảo vệ các điều kiện duy nhất như mã đơn hàng.
- **Idempotency:** nhận diện yêu cầu lặp để tránh tạo hoặc áp dụng cùng một thay đổi nhiều lần.

Repository implementation có thể chuyển xung đột lưu trữ thành một lỗi hoặc kết quả phù hợp với Application. Chính sách xử lý xung đột cần được xác định theo nghiệp vụ, chẳng hạn yêu cầu người dùng tải lại và thử lại hoặc từ chối hành động.

## 9. Repository và truy vấn đọc

Không phải mọi truy vấn đều nên đi qua Repository Aggregate. Repository tập trung vào việc tải và lưu Aggregate để thực hiện hành vi miền. Các màn hình báo cáo hoặc danh sách cần dữ liệu tổng hợp có thể dùng query service, DAO hoặc read model riêng.

Ví dụ:

- Để hủy một đơn: tải Order Aggregate qua OrderRepository, gọi order.cancel(reason), rồi lưu.
- Để hiển thị danh sách 100 đơn với tên khách, tổng tiền và trạng thái: một query service có thể truy vấn projection tối ưu mà không cần khôi phục 100 Aggregate đầy đủ.
- Để tạo báo cáo doanh thu theo tháng: dùng truy vấn phân tích hoặc read model phù hợp thay vì gọi findAll() rồi tính trong bộ nhớ.

Sự phân biệt này đặc biệt hữu ích khi áp dụng CQRS:

- **Command side:** tải Aggregate qua Repository và thực hiện hành vi thay đổi.
- **Query side:** truy vấn dữ liệu theo nhu cầu hiển thị, có thể dùng projection hoặc read model.

Không cần triển khai CQRS đầy đủ cho mọi ứng dụng. Nguyên tắc thực tế là không ép Repository Aggregate thành công cụ cho mọi loại truy vấn.

## 10. Tìm kiếm linh hoạt mà vẫn giữ ngôn ngữ miền

Khi số lượng điều kiện tìm kiếm tăng, một Repository có thể cần phương thức tìm kiếm hoặc Specification.

Ví dụ:

~~~java
public interface OrderRepository {
    Optional<Order> findById(Order.OrderId id);
    List<Order> findOpenOrdersForCustomer(CustomerId customerId);
    void save(Order order);
}
~~~

Nếu điều kiện phức tạp, có thể dùng một đối tượng tiêu chí thuộc Application hoặc Domain tùy ý nghĩa:

~~~java
public record OpenOrderCriteria(
        CustomerId customerId,
        Instant createdAfter,
        int limit
) {}
~~~

Không nên để hợp đồng miền nhận các kiểu như JpaSpecificationExecutor, CriteriaBuilder hoặc SQL fragment. Implementation có thể chuyển tiêu chí thành truy vấn cụ thể.

Hãy cẩn trọng với findAll(). Tải toàn bộ Aggregate có thể gây tốn bộ nhớ, thời gian và tạo tải không cần thiết. Nên cung cấp phân trang, giới hạn hoặc truy vấn chuyên biệt khi use case yêu cầu.

## 11. Kiểm thử Repository

Repository có thể được kiểm thử ở nhiều mức:

### 11.1. Kiểm thử Domain độc lập

Kiểm thử hành vi Aggregate mà không cần cơ sở dữ liệu. Mục tiêu là xác nhận quy tắc như chỉ đơn nháp mới được sửa hoặc đơn rỗng không thể xác nhận.

### 11.2. Kiểm thử implementation

Kiểm thử JpaOrderRepository với cơ sở dữ liệu thử nghiệm để xác nhận:

- Aggregate được lưu và tải lại đúng.
- Entity con và Value Object được ánh xạ đúng.
- Các thay đổi được ghi nhận theo transaction.
- Version hoặc unique constraint hoạt động như mong đợi.
- Trạng thái null, quan hệ và dữ liệu cũ được xử lý phù hợp.

### 11.3. Kiểm thử hợp đồng Repository

Nếu có nhiều implementation, có thể dùng cùng bộ kiểm thử hợp đồng để bảo đảm mỗi implementation tuân theo hành vi của interface. Ví dụ, findById() trả Optional.empty() khi không tìm thấy, save() có ngữ nghĩa nhất quán và tải lại Aggregate giữ được dữ liệu cần thiết.

### 11.4. Khi nào dùng In-memory Repository?

Implementation trong bộ nhớ hữu ích cho kiểm thử Application Service hoặc thử nghiệm mô hình. Nó cần mô phỏng đúng ngữ nghĩa cần kiểm tra, chẳng hạn định danh duy nhất và lưu thay đổi. Tuy nhiên, nó không thể thay thế kiểm thử persistence thật về transaction, mapping, locking và constraint.

## 12. Những sai lầm thường gặp

### 12.1. Tạo Repository cho mỗi bảng

Repository trong DDD thường xoay quanh Aggregate Root, không phải một lớp cho từng bảng. Tạo repository cho OrderLine hoặc bảng phụ có thể làm lộ cấu trúc lưu trữ và bỏ qua Root.

### 12.2. Để Entity tự gọi Repository

Entity không nên tự truy vấn cơ sở dữ liệu để tìm đối tượng khác. Điều này khiến mô hình phụ thuộc persistence và làm hành vi khó kiểm thử. Application hoặc một Domain Service phù hợp có thể tải dữ liệu cần thiết rồi truyền vào mô hình.

### 12.3. Đặt SQL trong Domain

SQL, EntityManager, JDBC và kiểu ORM thuộc Infrastructure. Domain chỉ nên biết hợp đồng truy xuất cần thiết nếu nó thực sự thuộc ngôn ngữ miền.

### 12.4. Dùng Repository cho mọi truy vấn báo cáo

Khôi phục Aggregate đầy đủ cho một màn hình danh sách hoặc báo cáo có thể không hiệu quả. Hãy dùng query service hoặc projection cho nhu cầu đọc phù hợp.

### 12.5. Trả về persistence entity

Nếu Application nhận OrderEntity hoặc kiểu ORM, chi tiết lưu trữ đã rò rỉ ra ngoài. Hãy ánh xạ về Aggregate hoặc kiểu kết quả phù hợp.

### 12.6. Đưa mọi bộ lọc thành phương thức Repository

Một interface có hàng chục phương thức gần giống nhau khó duy trì. Hãy ưu tiên nhu cầu thực tế, tiêu chí có ý nghĩa và query service khi truy vấn không nhằm tải Aggregate để thay đổi.

### 12.7. Cho rằng Repository tự bảo đảm transaction

Repository không tự giải quyết mọi vấn đề giao dịch, đồng thời hoặc nhất quán phân tán. Cần xác định transaction boundary và cơ chế phối hợp ở cấp use case.

### 12.8. Tạo abstraction quá mức

Không cần một lớp generic repository, factory và adapter riêng cho mọi kiểu chỉ để tuân theo mẫu. Abstraction cần giải quyết một ranh giới thực sự và làm cho mô hình dễ hiểu hơn.

## 13. Quy trình thiết kế Repository

Khi thiết kế Repository cho một Bounded Context, có thể đi theo các bước:

1. **Xác định Aggregate Root:** làm rõ đối tượng nào có vòng đời và bất biến cần được quản lý như một đơn vị.
2. **Xác định nhu cầu truy xuất:** use case cần tải Aggregate theo ID, mã nghiệp vụ hay điều kiện nào?
3. **Thiết kế hợp đồng miền:** đặt tên phương thức theo thuật ngữ và nhu cầu thực tế; không để lộ SQL hoặc ORM.
4. **Xác định ngữ nghĩa lưu:** làm rõ tạo mới, cập nhật, xóa, version và xử lý không tìm thấy.
5. **Đặt abstraction đúng nơi:** đặt interface gần module sở hữu nhu cầu; implementation ở Infrastructure.
6. **Thiết kế mapping:** chuyển đổi dữ liệu lưu trữ và Aggregate mà không làm rò rỉ kiểu persistence.
7. **Xác định transaction và concurrency:** làm rõ transaction boundary, optimistic locking, unique constraint và idempotency.
8. **Tách truy vấn đọc khi cần:** dùng query service hoặc read model cho màn hình và báo cáo không cần Aggregate.
9. **Kiểm thử hợp đồng và implementation:** xác nhận hành vi truy xuất, mapping, transaction và lỗi.

~~~mermaid
flowchart TD
    A[Xác định Aggregate Root] --> B[Liệt kê nhu cầu truy xuất của use case]
    B --> C[Thiết kế Repository interface theo ngôn ngữ miền]
    C --> D[Đặt interface ở lớp sở hữu nhu cầu]
    D --> E[Infrastructure triển khai persistence adapter]
    E --> F[Kiểm thử mapping, transaction và concurrency]
    B --> G{Chỉ cần dữ liệu đọc/báo cáo?}
    G -->|Có| H[Dùng query service hoặc read model]
    G -->|Không| C
~~~

## 14. Checklist thiết kế Repository

- [ ] Repository được thiết kế quanh Aggregate Root.
- [ ] Hợp đồng dùng tên và kiểu dữ liệu theo ngôn ngữ miền.
- [ ] Repository trả về Aggregate hoặc kiểu kết quả phù hợp, không trả persistence entity.
- [ ] Đối tượng con không bị truy cập và sửa độc lập ngoài Aggregate Root.
- [ ] Phương thức tìm kiếm phản ánh nhu cầu thực tế của use case.
- [ ] Ngữ nghĩa save, add, update và remove đã rõ.
- [ ] Interface không phụ thuộc SQL, ORM hoặc framework cụ thể.
- [ ] Implementation nằm ở Infrastructure và thực hiện mapping phù hợp.
- [ ] Transaction boundary do use case hoặc cơ chế ứng dụng xác định rõ.
- [ ] Đã xem xét optimistic locking, unique constraint và idempotency.
- [ ] Truy vấn báo cáo hoặc màn hình đọc dùng query service/read model khi phù hợp.
- [ ] Có kiểm thử Domain, Repository implementation và hợp đồng khi cần.

## 15. Kết luận

Repository trong DDD cung cấp giao diện truy xuất Aggregate theo ngôn ngữ miền. Nó giúp Application tải Aggregate Root, gọi hành vi và lưu thay đổi mà không phụ thuộc vào cơ chế lưu trữ. Repository thường được thiết kế cho từng Aggregate Root; các Entity con thuộc vòng đời của Root không cần Repository riêng nếu không có ranh giới độc lập.

Hợp đồng Repository cần diễn đạt nhu cầu truy xuất thực tế, còn implementation ở Infrastructure chịu trách nhiệm SQL, ORM, mapping và chi tiết lưu trữ. Application quản lý luồng use case và transaction; Aggregate bảo vệ bất biến. Với truy vấn báo cáo hoặc dữ liệu chỉ đọc, query service và read model có thể phù hợp hơn việc khôi phục Aggregate đầy đủ. Khi các trách nhiệm này rõ ràng, Repository trở thành ranh giới giúp mô hình miền độc lập, dễ kiểm thử và dễ thay đổi theo thời gian.
