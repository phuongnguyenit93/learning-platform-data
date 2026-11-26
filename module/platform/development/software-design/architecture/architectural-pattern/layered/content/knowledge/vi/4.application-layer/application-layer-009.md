# Lần theo luồng tạo đơn hàng từ tầng trình bày đến lưu trữ

Một request tạo đơn hàng đi qua nhiều trách nhiệm trước khi dữ liệu được ghi vào cơ sở dữ liệu. Tầng trình bày tiếp nhận giao tiếp HTTP; tầng ứng dụng điều phối ca sử dụng; mô hình nghiệp vụ quyết định đơn hàng có hợp lệ hay không; tầng truy cập dữ liệu chuyển đổi và lưu trạng thái. Hiểu được toàn bộ đường đi giúp xác định đúng nơi đặt logic, ranh giới giao dịch và cách kiểm thử từng phần.

Bài học này lần theo một request POST /api/orders trong ứng dụng Java dùng Spring. Ví dụ minh họa cách tổ chức phần mềm theo kiến trúc phân tầng: phân biệt tầng logic với tiến trình triển khai, làm rõ hợp đồng giữa các tầng và theo dõi cả lời gọi lẫn dữ liệu. Một ứng dụng có thể dùng số tầng hoặc cách đặt tên khác; các vai trò dưới đây là cách phân chia trách nhiệm hữu ích, không phải công thức bắt buộc cho mọi hệ thống.

## 1. Các vai trò trên đường đi của request

Ví dụ đặt hàng có bốn nhóm trách nhiệm:

| Thành phần | Trách nhiệm trong luồng tạo đơn |
|---|---|
| Tầng trình bày (presentation) | Nhận HTTP request, kiểm tra cấu trúc đầu vào, chuyển dữ liệu giao tiếp thành lệnh ứng dụng và tạo HTTP response |
| Tầng ứng dụng (application) | Điều phối ca sử dụng, lấy thông tin cần thiết qua các cổng, xác định ranh giới giao dịch và yêu cầu lưu đơn hàng |
| Tầng miền (domain) | Biểu diễn đơn hàng và thực thi quy tắc nghiệp vụ như số lượng hợp lệ, đơn hàng phải có dòng hàng và trạng thái hợp lệ |
| Tầng hạ tầng/truy cập dữ liệu (infrastructure) | Hiện thực cổng lưu trữ, ánh xạ mô hình nghiệp vụ sang entity persistence và làm việc với JPA/cơ sở dữ liệu |

Đây là các **tầng logic**. Trong một ứng dụng Spring Boot thông thường, controller, service, domain object và adapter JPA có thể cùng chạy trong một tiến trình và được đóng gói trong một file JAR. Chia thành tầng không tự động có nghĩa là chia thành các máy chủ hoặc dịch vụ triển khai riêng.

Một request đi qua các thành phần theo thứ tự khái quát sau:

~~~mermaid
sequenceDiagram
    actor Client
    participant Web as Filter chain / DispatcherServlet
    participant C as OrderController
    participant A as PlaceOrderService
    participant P as PricingPort
    participant D as Order domain
    participant R as JpaOrderRepository
    participant J as Spring Data JPA
    participant DB as Database

    Client->>Web: POST /api/orders
    Web->>C: Gọi controller sau khi định tuyến
    C->>C: Bind JSON và validate request
    C->>A: place(PlaceOrderCommand)
    A->>P: Lấy giá hiện hành theo SKU
    P-->>A: Các dòng hàng đã định giá
    A->>D: Order.place(...)
    D-->>A: Đơn hàng hợp lệ
    A->>R: save(order) qua repository port
    Note over A,R: Runtime dispatch đến adapter JPA được Spring inject
    R->>J: Chuyển đổi và gọi save(entity)
    J->>DB: Ghi SQL khi flush
    DB-->>J: Kết quả ghi
    J-->>R: Hoàn tất thao tác persistence
    R-->>A: Hoàn tất save
    Note over A,DB: Transaction interceptor commit khi phương thức ứng dụng kết thúc thành công
    A-->>C: PlaceOrderResult
    C-->>Client: 201 Created + response body
~~~

Sơ đồ là đường đi điển hình của một request đồng bộ. Các chi tiết như bảo mật, cache, logging, tracing hoặc message broker có thể bổ sung vào hệ thống tùy nhu cầu.

## 2. Bước 1 — HTTP request đi vào tầng trình bày

Client gửi JSON tới endpoint:

~~~http
POST /api/orders
Content-Type: application/json

{
  "customerId": "4a88b6b0-6a2a-4ec7-9a9e-bda8b5c9f0a1",
  "items": [
    { "sku": "BOOK-101", "quantity": 2 },
    { "sku": "PEN-205", "quantity": 3 }
  ]
}
~~~

Trên ứng dụng Spring MVC, request thường đi qua servlet filter chain trước khi DispatcherServlet chọn controller phù hợp. Filter có thể xử lý xác thực, phân quyền ở mức request, CORS hoặc ghi nhận thông tin tương quan. DispatcherServlet tìm handler dựa trên mapping của controller rồi chuyển request đến phương thức tương ứng.

Controller là điểm vào của giao tiếp HTTP. Nó hiểu đường dẫn, JSON, mã trạng thái và các kiểu dữ liệu của API. Controller có thể kiểm tra cấu trúc đầu vào bằng Bean Validation, nhưng không nên tự quyết định các quy tắc nghiệp vụ như khách hàng có được mua mặt hàng này hay tổng số lượng có vượt giới hạn đặt hàng hay không.

Ví dụ DTO nhận request:

~~~java
public record CreateOrderRequest(
    @NotNull UUID customerId,
    @NotEmpty List<@Valid OrderItemRequest> items
) {}

public record OrderItemRequest(
    @NotBlank String sku,
    @Min(1) int quantity
) {}
~~~

Controller chuyển DTO giao tiếp thành command của ca sử dụng:

~~~java
@RestController
@RequestMapping("/api/orders")
public class OrderController {
    private final PlaceOrderUseCase placeOrder;

    public OrderController(PlaceOrderUseCase placeOrder) {
        this.placeOrder = placeOrder;
    }

    @PostMapping
    public ResponseEntity<CreateOrderResponse> create(
            @Valid @RequestBody CreateOrderRequest request) {

        var command = new PlaceOrderCommand(
            request.customerId(),
            request.items().stream()
                .map(item -> new RequestedItem(item.sku(), item.quantity()))
                .toList()
        );

        var result = placeOrder.place(command);
        var response = new CreateOrderResponse(result.orderId());
        var location = URI.create("/api/orders/" + result.orderId());
        return ResponseEntity.created(location).body(response);
    }
}
~~~

Các kiểu CreateOrderRequest và CreateOrderResponse thuộc hợp đồng HTTP. PlaceOrderCommand và PlaceOrderResult thuộc hợp đồng của ca sử dụng. Việc chuyển đổi ở controller giúp tầng ứng dụng không phải phụ thuộc vào annotation hoặc cấu trúc JSON của Spring MVC.

Trong ví dụ, controller chỉ chuyển dữ liệu và định dạng kết quả. Nếu request sai cấu trúc, Bean Validation có thể từ chối trước khi gọi use case. Lỗi xác thực hoặc quy tắc nghiệp vụ sẽ được ánh xạ sang HTTP response ở một nơi phù hợp, thường là @RestControllerAdvice.

## 3. Bước 2 — Tầng ứng dụng điều phối ca sử dụng

Tầng ứng dụng nhận một yêu cầu có ý nghĩa đối với nghiệp vụ: tạo đơn hàng cho khách hàng với các SKU và số lượng đã yêu cầu. Nó quyết định cần gọi những khả năng nào, theo thứ tự nào và trong phạm vi giao dịch nào.

Ví dụ, giá bán phải được lấy từ nguồn đáng tin cậy phía máy chủ. Không nên mặc định sử dụng đơn giá do client gửi lên, vì người gọi có thể tự sửa JSON. Tầng ứng dụng có thể yêu cầu một cổng định giá cung cấp giá hiện hành, sau đó chuyển dữ liệu đã định giá cho mô hình miền.

Các kiểu lệnh và kết quả:

~~~java
public record RequestedItem(String sku, int quantity) {}

public record PlaceOrderCommand(
    UUID customerId,
    List<RequestedItem> items
) {}

public record PlaceOrderResult(UUID orderId) {}
~~~

Cổng định giá và cổng lưu đơn hàng mô tả những khả năng mà ca sử dụng cần:

~~~java
public interface ProductPricing {
    List<OrderLine> price(List<RequestedItem> items);
}

public interface OrderRepository {
    void save(Order order);
}
~~~

Ví dụ service điều phối:

~~~java
public interface PlaceOrderUseCase {
    PlaceOrderResult place(PlaceOrderCommand command);
}

@Service
public class PlaceOrderService implements PlaceOrderUseCase {
    private final ProductPricing pricing;
    private final OrderRepository orders;

    public PlaceOrderService(ProductPricing pricing, OrderRepository orders) {
        this.pricing = pricing;
        this.orders = orders;
    }

    @Override
    @Transactional
    public PlaceOrderResult place(PlaceOrderCommand command) {
        var pricedLines = pricing.price(command.items());
        var order = Order.place(command.customerId(), pricedLines);
        orders.save(order);
        return new PlaceOrderResult(order.id());
    }
}
~~~

Service không cần biết dữ liệu được lấy từ bảng nào, entity JPA có tên gì hay câu SQL được viết ra sao. Nó biết các hợp đồng ProductPricing và OrderRepository, rồi điều phối chúng để hoàn thành ca sử dụng.

Tùy hệ thống, interface use case và các cổng có thể được đặt trong package ứng dụng hoặc một module hợp đồng riêng. Một dự án nhỏ có thể không cần interface cho mọi service. Điều quan trọng là các phụ thuộc phải thể hiện rõ ai cung cấp khả năng nào và tầng ứng dụng không bị buộc vào chi tiết lưu trữ cụ thể.

## 4. Bước 3 — Mô hình miền thực thi quy tắc đơn hàng

Sau khi có thông tin giá từ nguồn phía máy chủ, tầng ứng dụng yêu cầu miền tạo đơn hàng. Miền chịu trách nhiệm bảo vệ các bất biến của đơn hàng, bất kể yêu cầu đến từ HTTP, tác vụ nền hay một luồng xử lý khác.

Ví dụ tối giản:

~~~java
public record OrderLine(String sku, int quantity, Money unitPrice) {
    public OrderLine {
        if (sku == null || sku.isBlank()) {
            throw new IllegalArgumentException("SKU is required");
        }
        if (quantity <= 0) {
            throw new IllegalArgumentException("Quantity must be positive");
        }
        if (unitPrice == null || unitPrice.isNegative()) {
            throw new IllegalArgumentException("Unit price is invalid");
        }
    }
}

public class Order {
    private final UUID id;
    private final UUID customerId;
    private final List<OrderLine> lines;

    private Order(UUID id, UUID customerId, List<OrderLine> lines) {
        this.id = id;
        this.customerId = customerId;
        this.lines = List.copyOf(lines);
    }

    public static Order place(UUID customerId, List<OrderLine> lines) {
        if (customerId == null) {
            throw new IllegalArgumentException("Customer is required");
        }
        if (lines == null || lines.isEmpty()) {
            throw new IllegalArgumentException("An order needs at least one item");
        }
        return new Order(UUID.randomUUID(), customerId, lines);
    }

    public UUID id() {
        return id;
    }

    public UUID customerId() {
        return customerId;
    }

    public List<OrderLine> lines() {
        return lines;
    }
}
~~~

Đây là mô hình minh họa, chưa phải mô hình đơn hàng đầy đủ cho sản phẩm thực tế. Hệ thống có thể cần quy tắc về tồn kho, hạn mức khách hàng, tiền tệ, thuế, giảm giá, địa chỉ giao hàng hoặc trạng thái. Những quy tắc thuộc về tính đúng đắn của đơn hàng nên được đặt tại mô hình miền hoặc thành phần nghiệp vụ có quyền sở hữu rõ ràng, thay vì chỉ kiểm tra trong controller.

Không phải ứng dụng nào cũng cần một domain model phong phú. Với nghiệp vụ đơn giản, mô hình có thể gồm các kiểu dữ liệu và hàm kiểm tra nhỏ. Khi quy tắc phức tạp và thay đổi thường xuyên, việc tập trung bất biến vào đối tượng miền giúp các luồng gọi khác nhau cùng tuân thủ một cách nhất quán.

## 5. Bước 4 — Từ repository port đến adapter JPA

Sau khi đơn hàng được tạo hợp lệ, tầng ứng dụng yêu cầu OrderRepository lưu đơn hàng. Đây là một hợp đồng về khả năng lưu và truy xuất đơn hàng; nó không quy định phải dùng JPA, SQL hay một hệ quản trị cơ sở dữ liệu cụ thể.

Tầng hạ tầng cung cấp adapter hiện thực hợp đồng:

~~~java
@Repository
public class JpaOrderRepository implements OrderRepository {
    private final SpringDataOrderJpaRepository jpa;

    public JpaOrderRepository(SpringDataOrderJpaRepository jpa) {
        this.jpa = jpa;
    }

    @Override
    public void save(Order order) {
        jpa.save(OrderEntity.from(order));
    }
}
~~~

OrderEntity là mô hình persistence, có thể mang annotation JPA và cấu trúc quan hệ phù hợp với cơ sở dữ liệu:

~~~java
@Entity
@Table(name = "orders")
public class OrderEntity {
    @Id
    private UUID id;

    @Column(name = "customer_id", nullable = false)
    private UUID customerId;

    @OneToMany(
        mappedBy = "order",
        cascade = CascadeType.ALL,
        orphanRemoval = true
    )
    private List<OrderLineEntity> lines = new ArrayList<>();

    protected OrderEntity() {}

    public static OrderEntity from(Order order) {
        var entity = new OrderEntity();
        entity.id = order.id();
        entity.customerId = order.customerId();
        entity.lines = order.lines().stream()
            .map(line -> OrderLineEntity.from(line, entity))
            .collect(Collectors.toCollection(ArrayList::new));
        return entity;
    }
}
~~~

Đoạn mã chỉ minh họa hướng ánh xạ; các phương thức truy cập, constructor và entity dòng hàng cần được hoàn thiện theo cấu hình JPA cụ thể của dự án. Điểm cần chú ý là adapter chịu trách nhiệm chuyển từ mô hình miền sang mô hình lưu trữ. Controller và service ứng dụng không cần import OrderEntity hoặc SpringDataOrderJpaRepository.

Spring Data JPA cung cấp thao tác repository ở mức persistence. Khi adapter gọi save, JPA có thể quản lý entity trong persistence context. Lệnh SQL thực tế có thể được gửi ngay hoặc được trì hoãn đến thời điểm flush. Vì vậy, save() trả về không nhất thiết có nghĩa là transaction đã commit hoặc dữ liệu đã được xác nhận bền vững trong cơ sở dữ liệu.

## 6. Bước 5 — Hiểu ranh giới transaction và thời điểm ghi dữ liệu

Trong ví dụ, @Transactional đặt trên phương thức của service ứng dụng. Khi phương thức được gọi qua Spring proxy, transaction interceptor bắt đầu hoặc tham gia transaction theo cấu hình propagation. Nếu phương thức kết thúc bình thường, interceptor thực hiện commit; nếu gặp exception phù hợp với quy tắc rollback, transaction được rollback.

Trình tự thường gặp là:

1. Spring mở hoặc tham gia transaction trước khi gọi phương thức ứng dụng.
2. Service lấy giá và tạo đơn hàng.
3. Adapter gọi JPA để lưu entity; entity được quản lý trong persistence context.
4. Khi flush, JPA đồng bộ thay đổi thành câu lệnh SQL và gửi đến cơ sở dữ liệu.
5. Transaction manager commit transaction khi phương thức ứng dụng kết thúc thành công.
6. Quyền điều khiển trở về controller sau khi lời gọi qua proxy hoàn tất; controller tạo HTTP response.

Thời điểm phát sinh SQL phụ thuộc thao tác, chiến lược sinh ID, flush mode và provider JPA. Một số thao tác có thể buộc flush sớm; một số thao tác chỉ được đồng bộ khi transaction commit. Constraint của cơ sở dữ liệu cũng có thể chỉ được kiểm tra ở thời điểm flush hoặc commit, tùy loại constraint và cấu hình.

Vì vậy, không nên diễn giải repository.save() như bằng chứng chắc chắn rằng dữ liệu đã được commit. Nếu cần xác nhận lỗi ràng buộc ngay tại một điểm cụ thể, có thể cân nhắc flush có chủ đích, nhưng flush vẫn không tương đương commit.

@Transactional của Spring thường dựa trên proxy. Một lời gọi nội bộ từ phương thức này sang phương thức khác trong cùng bean có thể không đi qua proxy và do đó không kích hoạt ranh giới transaction như người viết mong đợi. Đặt transaction ở phương thức ứng dụng được gọi từ bên ngoài thường giúp ranh giới dễ hiểu hơn. Transaction cũng chỉ bao phủ các tài nguyên được transaction manager quản lý; gọi API bên ngoài hoặc gửi email không tự động trở thành một phần nguyên tử của transaction cơ sở dữ liệu.

## 7. Bước 6 — Trả kết quả về tầng trình bày

Khi service trả PlaceOrderResult, tầng ứng dụng chỉ cung cấp dữ liệu cần thiết cho ca sử dụng, chẳng hạn mã đơn hàng. Controller chuyển kết quả đó thành hợp đồng HTTP:

~~~java
public record CreateOrderResponse(UUID orderId) {}
~~~

Với request tạo mới thành công, API thường trả 201 Created, có thể kèm header Location trỏ đến tài nguyên vừa tạo và response body chứa mã đơn hàng. Cách biểu diễn cụ thể phụ thuộc hợp đồng API của hệ thống.

Lỗi ở từng bước cũng cần được ánh xạ có chủ đích:

| Nguồn lỗi | Ví dụ | Cách phản hồi HTTP thường gặp |
|---|---|---|
| Binding/validation ở tầng trình bày | JSON sai kiểu, thiếu SKU, số lượng nhỏ hơn 1 | 400 Bad Request |
| Quy tắc nghiệp vụ | Khách hàng không đủ điều kiện đặt hàng, mặt hàng không thể bán | 409 Conflict hoặc 422 Unprocessable Content, tùy hợp đồng |
| Tài nguyên không tồn tại | Không tìm thấy khách hàng hoặc SKU | 404 Not Found nếu API biểu diễn trường hợp này như tài nguyên không tồn tại |
| Hạ tầng/cơ sở dữ liệu | Database tạm thời không khả dụng | Thường là lỗi máy chủ như 5xx; không trả chi tiết SQL cho client |

Một @RestControllerAdvice có thể chuyển các exception đã được định nghĩa thành response nhất quán. Không nên bắt mọi exception rồi trả 400, vì lỗi cấu hình hoặc lỗi cơ sở dữ liệu không phải lúc nào cũng do client gửi request sai. Thông tin kỹ thuật chi tiết nên được ghi log ở phía máy chủ với mã tương quan, tránh đưa dữ liệu nhạy cảm hoặc câu SQL nội bộ vào response.

## 8. Kiểm thử luồng theo từng ranh giới

Có thể kiểm thử từng trách nhiệm độc lập rồi bổ sung kiểm thử tích hợp cho đường đi xuyên suốt:

| Loại kiểm thử | Phạm vi | Điều cần xác nhận |
|---|---|---|
| Unit test cho miền | Order, OrderLine, quy tắc nghiệp vụ | Đơn hàng rỗng, số lượng sai hoặc giá không hợp lệ bị từ chối; đơn hợp lệ giữ đúng dữ liệu |
| Unit test cho tầng ứng dụng | PlaceOrderService cùng các port giả lập | Gọi định giá, tạo đơn và yêu cầu lưu đúng thứ tự; kết quả trả đúng mã đơn |
| Web/MVC test | Controller với use case giả lập | Mapping endpoint, binding JSON, validation, mã trạng thái và response body |
| Persistence integration test | JpaOrderRepository, JPA mapping và cơ sở dữ liệu kiểm thử | Entity và dòng hàng được ánh xạ, lưu và đọc lại đúng |
| End-to-end/integration test | Request HTTP qua Spring context đến database kiểm thử | Các thành phần được wiring đúng, transaction và phản hồi HTTP hoạt động như hợp đồng |

Ví dụ, unit test cho service có thể dùng fake hoặc mock ProductPricing và OrderRepository để xác nhận orchestration mà không cần khởi động Spring hay cơ sở dữ liệu. Persistence test nên dùng database tương thích với hành vi cần kiểm tra, nhất là khi phụ thuộc vào kiểu dữ liệu, constraint hoặc SQL đặc thù. Một test chỉ mock repository không chứng minh JPA mapping hoạt động.

Không cần mọi thay đổi đều chạy toàn bộ bộ end-to-end chậm. Hãy chọn mức kiểm thử theo rủi ro của phần vừa thay đổi, đồng thời giữ ít nhất một số kiểm thử tích hợp để phát hiện lỗi cấu hình và wiring giữa các tầng.

## 9. Những lỗi thiết kế thường gặp khi lần theo luồng

- **Controller làm quá nhiều:** controller tự tính giá, kiểm tra tồn kho, tạo entity và gọi repository. Khi đó giao tiếp HTTP nắm giữ logic nghiệp vụ và khó tái sử dụng ca sử dụng từ nguồn khác.
- **Service ứng dụng biết chi tiết JPA:** service import entity hoặc repository Spring Data cụ thể. Điều này buộc orchestration phụ thuộc công nghệ lưu trữ và làm việc thay thế adapter khó hơn.
- **Đưa mọi quy tắc vào application service:** service chỉ điều phối là hợp lý, nhưng nếu các bất biến của đơn hàng bị rải ở nhiều nhánh service, những luồng tạo hoặc cập nhật khác có thể bỏ sót. Quy tắc thuộc về trạng thái đơn hàng nên được bảo vệ bởi mô hình nghiệp vụ thích hợp.
- **Tin dữ liệu giá từ client:** người gọi có thể sửa giá trong JSON. Giá và các dữ liệu có thẩm quyền cần được xác định từ nguồn phía máy chủ.
- **Nhầm save với commit:** thao tác lưu trong repository có thể chỉ cập nhật persistence context. Lỗi có thể xuất hiện khi flush hoặc commit.
- **Đặt transaction sai ranh giới:** transaction quá nhỏ có thể không bao phủ toàn bộ thay đổi nghiệp vụ cần nguyên tử; transaction quá rộng có thể giữ kết nối và khóa lâu. Hãy chọn ranh giới quanh ca sử dụng cần tính nhất quán.
- **Để entity persistence đi ra API:** thay đổi schema hoặc mapping có thể buộc tầng HTTP thay đổi. DTO API nên phản ánh hợp đồng giao tiếp, không phải cấu trúc bảng.

## 10. Cân nhắc khi áp dụng

Một luồng tạo đơn có thể được triển khai bằng controller, application service, domain object, repository port và adapter persistence như ví dụ. Tuy nhiên, không phải hệ thống nào cũng cần một interface use case riêng, một DTO cho mọi lần chuyển tầng hay một domain model phức tạp. Với ứng dụng nhỏ, một số thành phần có thể gọn hơn; với nghiệp vụ lớn, ranh giới có thể cần rõ và chặt hơn.

Hãy chọn mức phân tách dựa trên những điều cần thay đổi độc lập và những quy tắc cần bảo vệ. Tầng trình bày nên chịu trách nhiệm giao tiếp; tầng ứng dụng nên điều phối; mô hình nghiệp vụ nên giữ các bất biến cần thiết; adapter hạ tầng nên xử lý chi tiết công nghệ. Nếu một thành phần đang làm thay trách nhiệm của tầng khác, hãy xem lại hợp đồng và hướng phụ thuộc.

Khi lần theo một request thực tế, hãy tự trả lời được sáu câu hỏi: request được tiếp nhận ở đâu, dữ liệu được chuyển thành command ở đâu, ai điều phối ca sử dụng, quy tắc đơn hàng được kiểm tra ở đâu, ai chuyển mô hình sang dữ liệu lưu trữ, và transaction được commit vào thời điểm nào. Trả lời rõ các câu hỏi này giúp bạn đọc code theo luồng nghiệp vụ thay vì chỉ lần theo tên lớp hoặc package.
