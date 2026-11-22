# Kho lưu trữ (Repository) và lớp truy cập dữ liệu

Trong ứng dụng MVC, Controller tiếp nhận request và gọi ca sử dụng; ca sử dụng phối hợp quy tắc nghiệp vụ; dữ liệu cần được đọc và ghi thông qua một cơ chế lưu trữ. Nếu logic nghiệp vụ phụ thuộc trực tiếp vào SQL, EntityManager hoặc API của một ORM, thay đổi cơ sở dữ liệu có thể lan rộng vào nhiều lớp và làm kiểm thử khó hơn.

Repository cung cấp một hợp đồng để phần nghiệp vụ làm việc với các đối tượng cần lưu trữ mà không phải biết chi tiết truy vấn hoặc công nghệ cơ sở dữ liệu. Lớp truy cập dữ liệu (data access layer) triển khai hợp đồng đó bằng JDBC, JPA, Spring Data hoặc một nguồn dữ liệu khác.

Bài học này giải thích vai trò của Repository trong MVC, phân biệt Repository với DAO, xác định ranh giới aggregate, tổ chức adapter truy cập dữ liệu và xử lý các vấn đề thực tế như giao dịch, phân trang, hiệu năng, đồng thời và kiểm thử.

Các đoạn Java trong bài là ví dụ theo Spring/JPA. Một số import, kiểu miền và phần cấu hình không liên quan trực tiếp đến ranh giới đang giải thích được lược bỏ; cần bổ sung theo mô hình thực tế của dự án khi sử dụng.

## 1. Mục tiêu

Sau bài học, bạn có thể:

- Giải thích Repository giải quyết vấn đề gì trong ứng dụng MVC.
- Phân biệt Repository, DAO, ORM Entity và Domain Entity.
- Xác định đối tượng gốc (aggregate root) mà một Repository quản lý.
- Thiết kế interface Repository và implementation truy cập dữ liệu.
- Kết nối Repository với Spring Data JPA mà không làm rò rỉ API persistence vào Controller.
- Đặt ranh giới giao dịch ở cấp ca sử dụng.
- Xử lý truy vấn đọc, phân trang, N+1 và cập nhật đồng thời.
- Kiểm thử nghiệp vụ, Repository adapter và luồng tích hợp.

## 2. Repository trong kiến trúc MVC

Một request web thường đi qua các thành phần:

1. Router chọn Controller.
2. Controller binding dữ liệu và kiểm tra hợp đồng đầu vào.
3. Controller gọi ca sử dụng hoặc application service.
4. Application phối hợp Domain Model và các phụ thuộc cần thiết.
5. Repository đọc hoặc ghi dữ liệu lâu dài.
6. Kết quả được trả về Controller để tạo View hoặc response.

~~~mermaid
flowchart LR
    Browser["Trình duyệt / API client"]
    Controller["Controller"]
    App["Application Service"]
    Domain["Domain Model"]
    Repo["Repository"]
    Adapter["Data Access Adapter"]
    DB[("Database")]

    Browser --> Controller
    Controller --> App
    App --> Domain
    App --> Repo
    Repo -. "interface / port" .-> Adapter
    Adapter --> DB
~~~

Repository nằm giữa phần nghiệp vụ và nơi lưu trữ. Nó cung cấp cách truy xuất các đối tượng theo ngôn ngữ của miền hoặc nhu cầu của ứng dụng. Phần nghiệp vụ có thể yêu cầu tìm một đơn hàng theo mã, lưu một đơn hàng hoặc lấy các đơn hàng thỏa điều kiện. Nó không cần biết dữ liệu nằm trong bảng nào, câu SQL được viết ra sao hoặc ORM tạo câu lệnh thế nào.

Repository không thay thế Domain Model. Domain Model vẫn giữ trạng thái và quy tắc nghiệp vụ. Repository chỉ đảm nhiệm việc truy xuất và lưu trữ đối tượng theo hợp đồng đã xác định.

## 3. Repository là gì?

Repository là một abstraction mô phỏng tập hợp các đối tượng nghiệp vụ có thể truy vấn và lưu thay đổi. Thay vì để application thao tác trực tiếp với bảng hoặc câu lệnh SQL, Repository cung cấp những phương thức có ý nghĩa đối với nghiệp vụ.

Ví dụ:

~~~java
public interface OrderRepository {
    Optional<Order> findById(OrderId id);

    void save(Order order);
}
~~~

Application có thể sử dụng hợp đồng này:

~~~java
public class CancelOrderService {
    private final OrderRepository orders;

    public CancelOrderService(OrderRepository orders) {
        this.orders = orders;
    }

    public void cancel(OrderId id) {
        Order order = orders.findById(id)
            .orElseThrow(OrderNotFoundException::new);

        order.cancel();
        orders.save(order);
    }
}
~~~

Ca sử dụng biết rằng nó cần một đơn hàng và cần lưu thay đổi. Nó không biết Order được tải bằng JPQL, SQL, cache hay một dịch vụ lưu trữ khác.

Một Repository được thiết kế tốt thường có các đặc điểm:

- Tên phương thức phản ánh nhu cầu truy xuất có ý nghĩa.
- Trả về đối tượng hoặc kết quả phù hợp với hợp đồng của phần nghiệp vụ.
- Che giấu chi tiết bảng, câu SQL và ORM.
- Quản lý dữ liệu theo ranh giới nhất quán của domain.
- Không chứa logic điều khiển giao diện hoặc xử lý HTTP.
- Không biến thành nơi chứa mọi quy tắc nghiệp vụ.

Không nhất thiết phải tạo Repository cho mọi lớp hoặc mọi bảng. Hãy tạo nó khi cần một ranh giới truy cập dữ liệu có ý nghĩa và giúp tách phụ thuộc.

## 4. Phân biệt Repository, DAO và ORM Entity

Các thuật ngữ này liên quan nhưng không hoàn toàn đồng nghĩa.

| Thành phần | Trách nhiệm chính | Ví dụ |
|---|---|---|
| Repository | Cung cấp tập hợp truy xuất và lưu đối tượng theo ngôn ngữ nghiệp vụ | OrderRepository.findById |
| DAO (Data Access Object) | Đóng gói thao tác đọc/ghi dữ liệu ở mức kỹ thuật | OrderDao.findRowById |
| ORM Entity | Biểu diễn dữ liệu được ORM ánh xạ với bảng hoặc cấu trúc lưu trữ | OrderEntity |
| Domain Entity | Biểu diễn đối tượng có định danh và hành vi nghiệp vụ | Order |
| Spring Data Repository | Interface do Spring Data hiện thực để cung cấp thao tác persistence | JpaRepository<OrderEntity, UUID> |

DAO thường có thể tập trung vào thao tác dữ liệu gần với bảng hoặc truy vấn. Repository theo cách tiếp cận Domain-Driven Design thường hướng đến aggregate root và ngôn ngữ nghiệp vụ. Trong một dự án, một lớp có thể mang đặc điểm của cả hai; tên gọi không quan trọng bằng trách nhiệm và ranh giới thực tế.

Spring Data Repository là abstraction của framework persistence. Nó có thể được dùng trực tiếp trong ứng dụng CRUD đơn giản. Với ứng dụng có Domain Model và ranh giới nghiệp vụ rõ, thường nên đặt một port Repository ở phía trong rồi viết adapter chuyển đổi giữa domain và Spring Data.

### 4.1. Vì sao không nên để Controller gọi DAO trực tiếp?

Ví dụ không phù hợp:

~~~java
@PostMapping("/orders/{id}/cancel")
public String cancel(@PathVariable UUID id) {
    OrderEntity entity = entityManager.find(OrderEntity.class, id);
    entity.setStatus("CANCELLED");
    entityManager.merge(entity);

    return "redirect:/orders";
}
~~~

Controller đang trực tiếp truy cập persistence và tự thay đổi trạng thái. Quy tắc hủy đơn có thể bị bỏ qua; API hoặc tác vụ nền có thể lặp lại logic tương tự; kiểm thử Controller cũng phải hiểu cấu trúc lưu trữ.

Cách tổ chức tốt hơn:

- Controller chuyển request thành lệnh nghiệp vụ.
- Application service gọi OrderRepository.
- Domain Model kiểm tra thao tác hủy có hợp lệ không.
- Repository adapter thực hiện đọc và ghi.

### 4.2. Không đồng nhất Domain Entity với ORM Entity

Một lớp có thể vừa là Domain Entity vừa là JPA Entity trong ứng dụng đơn giản. Đây là lựa chọn thực dụng nếu mô hình ít quy tắc và phụ thuộc ORM không gây khó khăn.

Khi domain phức tạp, có nhiều cách lưu trữ hoặc cần kiểm soát phụ thuộc chặt chẽ, tách hai loại có thể hữu ích:

- Domain Entity chứa trạng thái và hành vi nghiệp vụ.
- ORM Entity chứa annotation, quan hệ và cấu trúc phù hợp với persistence.
- Mapper chuyển đổi giữa hai mô hình.

Không nên tách máy móc nếu chi phí mapping lớn hơn lợi ích. Hãy căn cứ vào độ phức tạp và lý do thay đổi của từng mô hình.

## 5. Repository và Aggregate Root

Trong Domain-Driven Design, aggregate là một cụm đối tượng nghiệp vụ được quản lý như một đơn vị nhất quán. Aggregate root là điểm vào bên ngoài để truy cập và thay đổi cụm đó.

Ví dụ, một đơn hàng có thể chứa các dòng hàng:

~~~text
Order (Aggregate Root)
├── OrderLine
├── OrderLine
└── OrderLine
~~~

Nếu OrderLine chỉ có ý nghĩa bên trong một Order, phần bên ngoài nên thay đổi dòng hàng thông qua hành vi của Order:

~~~java
order.addLine(productCode, quantity, unitPrice);
order.removeLine(lineId);
order.confirm();
~~~

Không nên tạo OrderLineRepository riêng chỉ vì bảng order_line tồn tại. Repository thường được đặt theo aggregate root:

~~~java
public interface OrderRepository {
    Optional<Order> findById(OrderId id);
    void save(Order order);
}
~~~

Cách này giúp Domain Model bảo vệ các bất biến giữa đơn hàng và các dòng hàng. Nếu mỗi dòng được cập nhật độc lập qua một repository khác, quy tắc tổng tiền, trạng thái và tính hợp lệ của đơn có thể bị phá vỡ.

### 5.1. Chọn ranh giới aggregate hợp lý

Không nên gom mọi đối tượng liên quan vào một aggregate lớn. Aggregate quá lớn làm tăng khóa cạnh tranh, khiến cập nhật tốn kém và khó mở rộng.

Một số nguyên tắc:

- Gom các đối tượng cần duy trì bất biến cùng nhau trong một giao dịch nghiệp vụ.
- Dùng định danh để tham chiếu aggregate khác thay vì nhúng toàn bộ object graph.
- Chỉ tải những dữ liệu cần thiết cho hành vi đang thực hiện.
- Chấp nhận rằng một số quy tắc giữa các aggregate có thể cần eventual consistency hoặc quy trình nhiều bước.
- Tránh dùng Repository để trả về một object graph khổng lồ cho mọi màn hình.

Ví dụ, Order có thể tham chiếu CustomerId thay vì giữ toàn bộ Customer bên trong aggregate. Khi cần tên khách hàng cho trang chi tiết, một query có thể kết hợp dữ liệu từ hai nguồn.

### 5.2. Repository không phải một phương thức cho mỗi bảng

Repository nên phục vụ nhu cầu của aggregate hoặc ứng dụng, không phải phản chiếu nguyên trạng schema. Nếu có bảng audit, bảng join hoặc bảng phụ trợ, chúng có thể được xử lý bên trong adapter hoặc qua query riêng.

Điều này giúp schema có thể thay đổi mà không buộc mọi lớp nghiệp vụ thay đổi theo.

## 6. Đặt interface Repository ở đâu?

Có hai cách tổ chức phổ biến, tùy kiến trúc và quyền sở hữu hợp đồng.

### 6.1. Interface thuộc Domain

Trong DDD, Repository thường được định nghĩa gần aggregate mà nó quản lý:

~~~text
domain/
└── order/
    ├── Order.java
    ├── OrderLine.java
    └── OrderRepository.java
~~~

Domain định nghĩa cách aggregate cần được truy xuất và lưu. Infrastructure triển khai interface đó.

Cách này phù hợp khi Repository là một phần của mô hình domain và trả về aggregate root.

### 6.2. Interface thuộc Application

Trong kiến trúc ports and adapters, application có thể định nghĩa output port mô tả điều ca sử dụng cần:

~~~text
application/
└── port/
    └── LoadOrderPort.java
~~~

Port có thể được thiết kế theo một use case cụ thể, ví dụ tải đơn hàng để hủy hoặc tìm danh sách đơn theo điều kiện. Infrastructure cung cấp adapter thực hiện port.

Cách này phù hợp khi hợp đồng phản ánh nhu cầu của application hơn là khái niệm Repository của domain.

### 6.3. Chọn một vị trí nhất quán

Không có quy tắc rằng mọi interface Repository luôn phải nằm trong domain hoặc luôn phải nằm trong application. Hãy xác định ai sở hữu hợp đồng:

- Nếu nó biểu đạt cách aggregate được lưu và truy xuất, domain có thể sở hữu.
- Nếu nó biểu đạt một nhu cầu cụ thể của ca sử dụng, application có thể sở hữu.
- Implementation truy cập database nằm ở infrastructure.

Điều quan trọng là application và domain không phụ thuộc ngược vào implementation JPA hoặc JDBC.

## 7. Triển khai Repository bằng Spring Data JPA

Spring Data JPA giúp giảm mã truy cập dữ liệu bằng cách cung cấp interface repository và sinh implementation dựa trên khai báo.

Ví dụ interface persistence:

~~~java
public interface SpringDataOrderJpaRepository
        extends JpaRepository<OrderEntity, UUID> {
    Optional<OrderEntity> findByOrderNumber(String orderNumber);
}
~~~

Spring Data có thể cung cấp các thao tác cơ bản như findById, save, delete và hỗ trợ query method theo tên.

Trong một kiến trúc có adapter, interface này chỉ làm việc với ORM Entity. Nó không cần được inject trực tiếp vào Controller hoặc Domain Model.

### 7.1. Adapter triển khai Domain Repository

Giả sử Domain có hợp đồng:

~~~java
public interface OrderRepository {
    Optional<Order> findById(OrderId id);
    void save(Order order);
}
~~~

Adapter chuyển đổi giữa Domain Model và JPA Entity:

~~~java
@Repository
public class JpaOrderRepositoryAdapter implements OrderRepository {
    private final SpringDataOrderJpaRepository dataRepository;
    private final OrderPersistenceMapper mapper;

    public JpaOrderRepositoryAdapter(
            SpringDataOrderJpaRepository dataRepository,
            OrderPersistenceMapper mapper) {
        this.dataRepository = dataRepository;
        this.mapper = mapper;
    }

    @Override
    public Optional<Order> findById(OrderId id) {
        return dataRepository.findById(id.value())
            .map(mapper::toDomain);
    }

    @Override
    public void save(Order order) {
        OrderEntity entity = mapper.toEntity(order);
        dataRepository.save(entity);
    }
}
~~~

Adapter là nơi phù hợp để:

- Gọi Spring Data, JPA hoặc JDBC.
- Chuyển đổi giữa ORM Entity và Domain Entity.
- Chọn fetch strategy cho truy vấn.
- Chuyển lỗi persistence thành lỗi ở hợp đồng application/domain khi cần.
- Che giấu chi tiết database và framework.

Nếu Domain Entity và JPA Entity là cùng một lớp, mapper có thể không cần thiết. Nhưng khi hai mô hình khác nhau, cần xác định rõ cách ánh xạ định danh, trạng thái, version và các quan hệ.

Phương thức save của Spring Data thường tham gia persistence context và transaction hiện tại; câu lệnh SQL có thể chỉ được flush xuống database ở thời điểm sau đó, chẳng hạn khi transaction commit. Vì vậy, không nên giả định mọi constraint của database đã được kiểm tra ngay tại dòng gọi save. Chỉ dùng flush khi luồng thực sự cần phát hiện lỗi ghi sớm hoặc cần đồng bộ persistence context.

### 7.2. Mapper giữa Domain và Persistence

Ví dụ minh họa:

~~~java
@Component
public class OrderPersistenceMapper {

    public OrderEntity toEntity(Order order) {
        OrderEntity entity = new OrderEntity();
        entity.setId(order.id().value());
        entity.setCustomerId(order.customerId().value());
        entity.setStatus(order.status().name());

        entity.setLines(
            new ArrayList<>(order.lines().stream()
                .map(this::toLineEntity)
                .toList())
        );

        return entity;
    }

    public Order toDomain(OrderEntity entity) {
        List<OrderLine> lines = entity.getLines().stream()
            .map(this::toDomainLine)
            .toList();

        return Order.reconstitute(
            new OrderId(entity.getId()),
            new CustomerId(entity.getCustomerId()),
            lines,
            OrderStatus.valueOf(entity.getStatus())
        );
    }

    private OrderLineEntity toLineEntity(OrderLine line) {
        OrderLineEntity entity = new OrderLineEntity();
        entity.setProductCode(line.productCode().value());
        entity.setQuantity(line.quantity());
        entity.setUnitPrice(line.unitPrice().amount());
        entity.setCurrency(line.unitPrice().currency().getCurrencyCode());
        return entity;
    }

    private OrderLine toDomainLine(OrderLineEntity entity) {
        return OrderLine.reconstitute(
            new ProductCode(entity.getProductCode()),
            entity.getQuantity(),
            new Money(
                entity.getUnitPrice(),
                Currency.getInstance(entity.getCurrency())
            )
        );
    }
}
~~~

Các phương thức reconstitute và kiểu phụ trợ là ví dụ minh họa. Trong hệ thống thực tế, việc tái tạo aggregate cần bảo đảm bất biến; không nên dùng setter công khai để đưa đối tượng vào trạng thái bất kỳ.

Một mapper cũng cần xử lý version, quan hệ hai chiều và các trường hợp null theo hợp đồng. Khi ánh xạ collection hai chiều của JPA, adapter cần đồng bộ cả phía sở hữu quan hệ (ví dụ gán Order cho từng OrderLineEntity), không chỉ gán danh sách ở một phía. Nếu aggregate dùng optimistic locking, version phải được đưa qua mapper và adapter cần giữ lại version mới sau khi lưu. Không nên âm thầm bỏ qua trường dữ liệu có ý nghĩa nghiệp vụ.

## 8. Spring Data JPA và query method

Spring Data JPA cho phép khai báo truy vấn bằng tên phương thức:

~~~java
public interface SpringDataOrderJpaRepository
        extends JpaRepository<OrderEntity, UUID> {

    List<OrderEntity> findByCustomerId(UUID customerId);

    Optional<OrderEntity> findByOrderNumber(String orderNumber);

    Page<OrderEntity> findByStatus(
        OrderStatusEntity status,
        Pageable pageable
    );
}
~~~

Cách này phù hợp với truy vấn đơn giản và tên phương thức vẫn dễ hiểu. Khi truy vấn phức tạp, có thể dùng:

- @Query với JPQL.
- Native SQL khi cần tính năng đặc thù của database.
- Criteria API hoặc Specification.
- Projection để chỉ lấy các cột cần thiết.
- Query riêng trong read model.

Không nên để Controller phụ thuộc vào Pageable, Page, Sort hoặc Specification của Spring Data nếu muốn giữ ranh giới application độc lập với framework. Có thể chuyển chúng thành kiểu phân trang nội bộ rồi adapter ánh xạ sang API Spring Data.

## 9. Truy vấn đọc và mô hình ghi

Không phải mọi màn hình đều cần tải một aggregate hoàn chỉnh. Một trang danh sách đơn hàng có thể chỉ cần mã đơn, ngày tạo, tên khách hàng và tổng tiền.

Nếu mỗi hàng trong danh sách đều tải đầy đủ aggregate cùng các quan hệ, truy vấn có thể nặng và không cần thiết.

Có thể tách hai nhu cầu:

- **Write model:** tải aggregate để thực hiện hành vi và bảo vệ bất biến.
- **Read model:** truy vấn projection hoặc DTO chứa đúng dữ liệu cần hiển thị.

Ví dụ một query service:

~~~java
public interface OrderQueries {
    PageResult<OrderSummary> search(OrderSearchCriteria criteria);
}
~~~

OrderSummary có thể chứa dữ liệu đã tổng hợp cho danh sách:

~~~java
public record OrderSummary(
    UUID orderId,
    String orderNumber,
    String customerName,
    BigDecimal totalAmount,
    String currency,
    String status
) {}
~~~

Infrastructure có thể triển khai query này bằng JPQL projection, SQL hoặc Spring Data projection. Controller nhận kết quả đã phù hợp với View, không cần duyệt qua từng entity và tự tổng hợp.

Đây là một dạng tách read/write ở mức ứng dụng. Không nhất thiết phải triển khai CQRS đầy đủ với database riêng; chỉ cần tách query khỏi aggregate khi điều đó làm truy vấn rõ ràng và hiệu quả hơn.

### 9.1. Không đưa logic trình bày vào Repository

Repository không nên trả HTML hoặc chuỗi đã định dạng theo giao diện. Nó có thể trả dữ liệu có kiểu như BigDecimal, Instant hoặc OrderStatus; presentation quyết định cách hiển thị ngày, tiền tệ và nhãn trạng thái.

Tương tự, không nên trả Model của Spring MVC từ Repository.

## 10. Phân trang, sắp xếp và lọc

Danh sách dữ liệu lớn không nên tải toàn bộ vào bộ nhớ. Phân trang giúp giới hạn lượng dữ liệu trả về và kiểm soát chi phí truy vấn.

Một hợp đồng phân trang độc lập framework có thể là:

~~~java
public record PageRequestData(
    int page,
    int size,
    String sortBy,
    SortDirection direction
) {
    public PageRequestData {
        if (page < 0) {
            throw new IllegalArgumentException("Page must not be negative");
        }
        if (size < 1 || size > 100) {
            throw new IllegalArgumentException("Page size is out of range");
        }
    }
}
~~~

Kết quả:

~~~java
public record PageResult<T>(
    List<T> items,
    int page,
    int size,
    long totalElements
) {}
~~~

Adapter chuyển PageRequestData thành Pageable của Spring Data và ánh xạ Page trở lại PageResult.

Cần kiểm soát sortBy bằng allowlist. Không đưa trực tiếp tên cột do client gửi vào câu SQL hoặc JPQL động. Nếu dùng Sort, chỉ ánh xạ các khóa sắp xếp được hỗ trợ như createdAt, orderNumber hoặc totalAmount.

Với dữ liệu thay đổi thường xuyên, offset pagination có thể bỏ qua hoặc lặp bản ghi giữa các trang khi dữ liệu được thêm/xóa. Với danh sách rất lớn hoặc cần duyệt ổn định, cân nhắc keyset pagination dựa trên cursor và khóa sắp xếp có tính duy nhất.

## 11. Giao dịch và ranh giới lưu trữ

Một use case có thể đọc nhiều nguồn và ghi nhiều đối tượng. Nếu mỗi phương thức Repository tự mở một giao dịch riêng, thao tác tổng thể có thể bị chia thành nhiều phần không nguyên tử.

Ví dụ, tạo đơn hàng có thể cần:

1. Đọc giá sản phẩm.
2. Kiểm tra tồn kho.
3. Tạo đơn.
4. Lưu đơn và các dòng hàng.
5. Giữ hoặc trừ tồn kho.

Các thao tác cần tính nguyên tử phải nằm trong ranh giới transaction phù hợp. Thông thường, ranh giới giao dịch được đặt ở application service hoặc use case vì đó là nơi biết toàn bộ thao tác cần hoàn thành.

~~~java
@Service
public class PlaceOrderService {
    private final ProductRepository products;
    private final OrderRepository orders;

    public PlaceOrderService(
            ProductRepository products,
            OrderRepository orders) {
        this.products = products;
        this.orders = orders;
    }

    @Transactional
    public OrderId place(PlaceOrderCommand command) {
        Product product = products.findByCode(command.productCode())
            .orElseThrow(ProductNotFoundException::new);

        Order order = Order.create(
            command.customerId(),
            product,
            command.quantity()
        );

        orders.save(order);
        return order.id();
    }
}
~~~

Trong ứng dụng Spring, @Transactional thường được dùng ở service hoặc use case để xác định ranh giới giao dịch. Nếu application module cần độc lập hoàn toàn với Spring, có thể dùng transaction decorator hoặc adapter điều phối giao dịch ở composition layer.

Một vài lưu ý:

- Không mở transaction quá rộng quanh tác vụ chờ người dùng hoặc gọi mạng lâu.
- Không gọi dịch vụ ngoài trong transaction database dài nếu có thể tránh.
- Dùng rollback policy phù hợp với loại exception.
- Đảm bảo thao tác đọc và ghi liên quan nằm trong transaction đúng.
- Không giả định hai database hoặc database và message broker cùng commit nguyên tử nếu chưa có cơ chế phân tán phù hợp.

### 11.1. Transaction không tự giải quyết mọi vấn đề đồng thời

Transaction bảo vệ một nhóm thao tác theo isolation level của database, nhưng không tự ngăn mọi xung đột nghiệp vụ. Khi nhiều request cùng cập nhật một đơn hàng, cần cân nhắc optimistic locking, pessimistic locking hoặc các ràng buộc dữ liệu.

## 12. Cập nhật đồng thời và optimistic locking

Giả sử hai người cùng mở một đơn hàng ở version 4. Người thứ nhất cập nhật và lưu version 5. Người thứ hai vẫn gửi dữ liệu dựa trên version 4. Nếu không có cơ chế phát hiện xung đột, thay đổi sau có thể ghi đè thay đổi trước.

JPA hỗ trợ optimistic locking bằng @Version:

~~~java
@Entity
@Table(name = "orders")
public class OrderEntity {
    @Id
    private UUID id;

    @Version
    private long version;

    // Các trường persistence khác.
}
~~~

Khi cập nhật, JPA dùng version để phát hiện dữ liệu đã bị thay đổi. Nếu version không còn khớp, thao tác có thể thất bại với lỗi optimistic locking.

Application hoặc adapter cần chuyển xung đột này thành kết quả phù hợp, chẳng hạn lỗi OrderChangedException. Controller có thể trả HTTP 409 hoặc hiển thị yêu cầu tải lại dữ liệu.

Pessimistic locking có thể phù hợp với một số luồng cần khóa bản ghi trong transaction, nhưng có nguy cơ chờ khóa và deadlock. Chọn chiến lược theo mức cạnh tranh và yêu cầu nhất quán thực tế.

## 13. Hiệu năng và các vấn đề thường gặp

### 13.1. N+1 query

N+1 xảy ra khi một truy vấn tải danh sách entity, sau đó mỗi entity lại phát sinh một truy vấn riêng để tải quan hệ lazy.

Ví dụ, tải 100 đơn hàng rồi truy cập từng khách hàng có thể tạo thêm 100 query. Cách khắc phục tùy tình huống:

- Dùng fetch join hoặc EntityGraph cho quan hệ thực sự cần.
- Dùng projection để chỉ lấy dữ liệu cần hiển thị.
- Dùng batch fetching khi phù hợp.
- Tránh mở rộng fetch graph quá lớn gây Cartesian product.
- Kiểm tra số lượng query trong integration test hoặc log SQL.

Không nên mặc định mọi quan hệ đều eager. Eager loading quá rộng có thể gây tải thừa và làm truy vấn khó kiểm soát.

### 13.2. Chỉ lấy những cột cần thiết

Một trang danh sách không cần toàn bộ nội dung ghi chú, lịch sử hoặc quan hệ của đơn hàng. Projection hoặc DTO query giúp giảm dữ liệu đọc và chi phí chuyển đổi.

### 13.3. Index và điều kiện truy vấn

Các trường thường dùng để tìm kiếm, join hoặc sắp xếp có thể cần index. Index không miễn phí: nó làm tăng chi phí ghi và dung lượng lưu trữ. Dựa vào query thực tế và execution plan để quyết định.

### 13.4. Tránh truy vấn động không an toàn

Dùng parameter binding cho giá trị truy vấn. Nếu cần sort hoặc chọn cột động, ánh xạ từ một danh sách khóa cho phép. Không nối trực tiếp chuỗi request vào SQL.

### 13.5. Không tải dữ liệu vô hạn

Đặt giới hạn kích thước trang, giới hạn collection binding và giới hạn truy vấn. Với export lớn, dùng streaming hoặc batch processing thay vì tải toàn bộ dữ liệu vào heap.

## 14. Xử lý lỗi ở lớp truy cập dữ liệu

Lỗi persistence có thể đến từ:

- Vi phạm unique constraint.
- Vi phạm foreign key.
- Timeout hoặc mất kết nối.
- Deadlock.
- Optimistic locking conflict.
- Dữ liệu không thể ánh xạ hoặc chuyển đổi.
- Transaction rollback.

Không nên để exception JDBC hoặc JPA lan thẳng đến View. Adapter hoặc lớp ứng dụng có thể chuyển những lỗi đã hiểu thành lỗi có ý nghĩa hơn. Ví dụ:

| Lỗi persistence | Ý nghĩa ở ứng dụng |
|---|---|
| Unique constraint | Mã đơn hoặc email đã tồn tại |
| Foreign key | Dữ liệu tham chiếu không còn hợp lệ |
| Optimistic locking | Bản ghi đã được người khác thay đổi |
| Timeout | Tạm thời không thể hoàn thành thao tác |
| Connection failure | Hệ thống lưu trữ không khả dụng |

Không phải mọi lỗi database đều nên được chuyển thành lỗi validation. Lỗi kỹ thuật cần được log với correlation ID và trả thông báo an toàn; lỗi nghiệp vụ có thể dự đoán được thì ánh xạ thành kết quả có thể xử lý.

Trong Spring, exception translation có thể chuyển một số lỗi persistence thành họ DataAccessException. Controller advice hoặc exception mapper có thể chuyển lỗi ứng dụng sang response phù hợp. Tránh trả SQL, tên bảng, stack trace hoặc thông tin kết nối cho client.

## 15. Kiểm thử Repository và lớp truy cập dữ liệu

Mỗi tầng cần loại kiểm thử phù hợp.

### 15.1. Unit test cho Domain

Kiểm tra hành vi và bất biến của aggregate mà không cần database:

- Đơn rỗng không thể xác nhận nếu nghiệp vụ cấm.
- Không thể hủy đơn ở trạng thái không cho phép.
- Tổng tiền được tính đúng.
- Dòng hàng không thể làm thay đổi trạng thái aggregate ngoài hành vi công khai.

### 15.2. Unit test cho Application

Dùng fake Repository để kiểm tra ca sử dụng:

~~~java
class InMemoryOrderRepository implements OrderRepository {
    private final Map<OrderId, Order> data = new HashMap<>();

    @Override
    public Optional<Order> findById(OrderId id) {
        return Optional.ofNullable(data.get(id));
    }

    @Override
    public void save(Order order) {
        data.put(order.id(), order);
    }
}
~~~

Test application xác nhận use case gọi đúng hợp đồng, xử lý trường hợp không tìm thấy và chỉ lưu khi quy tắc nghiệp vụ thành công.

Fake phải giữ hành vi đủ phù hợp với hợp đồng. Nó không thay thế integration test vì không mô phỏng constraint, transaction hoặc SQL thật.

### 15.3. Integration test cho JPA adapter

Với Spring Boot, @DataJpaTest có thể kiểm thử mapping và truy vấn repository trong môi trường persistence. Nên kiểm tra:

- Lưu rồi tải lại aggregate có giữ đúng dữ liệu không.
- Quan hệ giữa aggregate và các dòng hàng có đúng không.
- Query method trả kết quả đúng.
- Constraint và version hoạt động như kỳ vọng.
- Mapper tái tạo đúng trạng thái domain.

Với database có hành vi đặc thù, dùng Testcontainers hoặc một database cùng loại trong môi trường test để giảm khác biệt so với production.

### 15.4. Kiểm thử transaction và concurrency

Một số lỗi chỉ xuất hiện khi nhiều thao tác cùng chạy. Cần có integration test cho optimistic locking, rollback và các ràng buộc quan trọng. Không nên chỉ dựa vào mock để kết luận transaction hoạt động đúng.

### 15.5. Kiểm thử truy vấn và hiệu năng

Theo dõi số query, thời gian thực thi và kế hoạch truy vấn cho các luồng quan trọng. Test có thể xác nhận số lượng query không tăng bất thường khi danh sách lớn lên, nhưng cần tránh khóa cứng vào chi tiết SQL không ổn định nếu không cần thiết.

## 16. Tổ chức package cho Repository

Một cấu trúc package theo feature có thể như sau:

~~~text
com/example/shop/
└── order/
    ├── web/
    │   ├── OrderController.java
    │   └── OrderViewMapper.java
    ├── application/
    │   ├── PlaceOrderService.java
    │   ├── PlaceOrderCommand.java
    │   └── OrderQueries.java
    ├── domain/
    │   ├── Order.java
    │   ├── OrderLine.java
    │   ├── OrderStatus.java
    │   └── OrderRepository.java
    └── infrastructure/
        └── persistence/
            ├── JpaOrderRepositoryAdapter.java
            ├── SpringDataOrderJpaRepository.java
            ├── OrderEntity.java
            └── OrderPersistenceMapper.java
~~~

Cấu trúc này giúp người đọc tìm được toàn bộ mã liên quan đến đơn hàng. Trong dự án nhỏ, có thể dùng package-by-layer; điều quan trọng là interface và implementation có ranh giới rõ.

Nếu application sở hữu một query port hoặc repository port cụ thể cho use case, đặt interface trong application/port cũng hợp lý. Không cần ép mọi repository vào một package duy nhất nếu các hợp đồng có chủ sở hữu khác nhau.

## 17. Những lỗi thiết kế thường gặp

### Repository trở thành nơi chứa toàn bộ nghiệp vụ

Repository nên truy xuất và lưu trữ. Không đặt quy tắc tính giá, xác nhận đơn hoặc phân quyền phức tạp trong phương thức repository. Đưa các quy tắc đó vào Domain Model hoặc application service.

### Một Repository cho mỗi bảng

Cách này thường phản ánh schema thay vì mô hình nghiệp vụ. Nếu nhiều bảng thuộc một aggregate, Repository của aggregate root có thể quản lý chúng như một đơn vị.

### Controller gọi Spring Data trực tiếp

Điều này làm Controller phụ thuộc persistence và dễ trộn truy vấn với trình bày. Hãy để Controller gọi application service hoặc query service.

### Rò rỉ kiểu Spring Data ra application

Không để Page, Pageable, Sort, Specification hoặc JpaRepository xuất hiện trong hợp đồng application nếu mục tiêu là độc lập framework. Dùng kiểu dữ liệu của ứng dụng và ánh xạ trong adapter.

### Mỗi phương thức Repository tự mở transaction

Điều này có thể làm một use case gồm nhiều thao tác không còn nguyên tử. Đặt transaction ở ranh giới ca sử dụng khi các thao tác cần cùng thành công hoặc cùng rollback.

### Trả ORM Entity trực tiếp cho View

View không nên phụ thuộc lazy proxy, quan hệ ORM hoặc cấu trúc bảng. Dùng View Model hoặc DTO được chuẩn bị từ query.

### Lạm dụng eager loading

Tải toàn bộ quan hệ cho mọi truy vấn làm tăng dữ liệu và có thể gây Cartesian product. Chọn fetch plan theo nhu cầu của từng use case.

### Chỉ kiểm thử bằng mock

Mock không kiểm tra mapping, SQL, constraint, transaction hoặc optimistic locking. Bổ sung integration test cho adapter và database.

## 18. Quy trình thiết kế Repository

Khi xây dựng một chức năng có lưu trữ, hãy thực hiện theo trình tự:

1. **Xác định aggregate hoặc nhu cầu truy vấn.** Làm rõ đối tượng nào cần được tải và lưu như một đơn vị nhất quán.
2. **Xác định hợp đồng Repository.** Chọn phương thức theo ngôn ngữ nghiệp vụ hoặc nhu cầu của application.
3. **Đặt interface ở phía sở hữu nhu cầu.** Domain hoặc application định nghĩa port phù hợp.
4. **Chọn persistence technology.** JPA, JDBC, document database hoặc nguồn dữ liệu khác.
5. **Tạo adapter.** Triển khai port, xử lý mapping và chi tiết truy vấn.
6. **Xác định ranh giới transaction.** Đặt giao dịch quanh ca sử dụng cần tính nguyên tử.
7. **Thiết kế query đọc.** Dùng projection, phân trang và sắp xếp có kiểm soát khi cần.
8. **Xem xét concurrency.** Chọn optimistic/pessimistic locking hoặc constraint phù hợp.
9. **Ánh xạ lỗi.** Chuyển lỗi persistence thành lỗi ứng dụng có ý nghĩa và thông báo an toàn.
10. **Kiểm thử từng tầng.** Domain unit test, application test với fake, adapter integration test và kiểm thử concurrency.

Trước khi hoàn thành, hãy tự hỏi:

- Repository có quản lý aggregate root hoặc nhu cầu truy vấn rõ ràng không?
- Controller có biết SQL, EntityManager hoặc Spring Data không?
- Interface có nằm ở phía sở hữu hợp đồng không?
- ORM Entity có bị lộ ra View hoặc API không?
- Transaction có bao trùm đúng một use case không?
- Truy vấn có tránh N+1 và tải dữ liệu thừa không?
- Phân trang và sắp xếp có giới hạn an toàn không?
- Cập nhật đồng thời có thể ghi đè dữ liệu không?
- Có integration test cho mapping, constraint và transaction không?

## 19. Kết luận

Repository tạo ranh giới giữa nghiệp vụ và cách dữ liệu được lưu trữ. Trong MVC, Controller nên gọi ca sử dụng; application phối hợp Domain Model và Repository; adapter truy cập dữ liệu triển khai hợp đồng bằng JPA, JDBC hoặc công nghệ phù hợp.

Thiết kế Repository theo aggregate root hoặc nhu cầu truy vấn giúp bảo vệ tính nhất quán, giảm phụ thuộc framework và làm kiểm thử rõ ràng hơn. Khi kết hợp với transaction đúng ranh giới, query projection, phân trang, kiểm soát concurrency và integration test, lớp truy cập dữ liệu có thể thay đổi mà không kéo theo thay đổi không cần thiết ở giao diện và quy tắc nghiệp vụ.

