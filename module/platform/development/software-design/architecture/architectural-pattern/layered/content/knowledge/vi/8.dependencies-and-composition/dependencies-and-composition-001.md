# Phân biệt phụ thuộc mã nguồn, lời gọi khi chạy và hướng truyền dữ liệu

Bài học này thuộc module **SOFTWARE_DESIGN_ARCHITECTURE_ARCHITECTURAL_PATTERN_LAYERED** — **Học tổ chức phần mềm theo kiến trúc phân tầng**, trong chương **Tổ chức phụ thuộc và lắp ráp ứng dụng**. Khi phân tích một ứng dụng phân tầng, cần tách ba câu hỏi: mã nguồn nào cần biết đến mã nguồn nào để biên dịch; lúc chạy thành phần nào gọi thành phần nào; và dữ liệu đi từ đâu đến đâu trong quá trình xử lý. Ba hướng này có liên quan nhưng không đồng nhất. Vẽ chúng thành các sơ đồ riêng giúp tránh nhầm lẫn khi thiết kế layer, dependency injection và luồng xử lý.

## 1. Ba hướng trả lời ba câu hỏi khác nhau

### Phụ thuộc mã nguồn

**Phụ thuộc mã nguồn (source-code dependency)** là quan hệ giữa các module, package hoặc kiểu mà mã nguồn cần biết để biên dịch. Một lớp phụ thuộc vào kiểu được dùng trong field, constructor parameter, method signature, câu lệnh import, lớp cha hoặc interface mà nó triển khai. Nếu một service khai báo field có kiểu **OrderRepository**, mã nguồn service cần biết định nghĩa của **OrderRepository**.

Mũi tên trong dependency graph thường đi từ bên sử dụng sang bên được sử dụng: **A → B** có nghĩa mã nguồn A cần B. Có thể kiểm tra hướng này qua import, khai báo kiểu, module descriptor và cấu hình build.

### Lời gọi khi chạy

**Hướng gọi khi chạy (runtime call direction)** mô tả luồng điều khiển khi chương trình thực thi một tình huống. Mũi tên đi từ caller đến callee: controller gọi use case, service gọi repository, adapter gọi thư viện persistence. Call stack, breakpoint, trace và sequence diagram giúp quan sát hướng này.

Khi lời gọi được thực hiện qua interface hoặc abstract class, kiểu của tham chiếu ở mã nguồn có thể khác lớp thực tế nhận lời gọi. Cơ chế đa hình của Java dispatch phương thức đến implementation của object tại thời điểm chạy.

### Hướng truyền dữ liệu

**Hướng truyền dữ liệu (data flow)** mô tả giá trị được tạo, chuyển giao, biến đổi hoặc lưu ở đâu. Dữ liệu đầu vào có thể đi từ HTTP request vào request DTO, được chuyển thành command, rồi thành đối tượng domain và entity persistence. Kết quả có thể đi theo chiều ngược lại: từ domain/application trở về response. Dữ liệu cũng có thể được phát qua message hoặc event mà không có một lời gọi đồng bộ trực tiếp giữa nơi tạo và nơi nhận.

Mũi tên data flow nên được hiểu là **giá trị đi từ nguồn đến nơi nhận**, không phải lời gọi phương thức. Cần ghi rõ loại dữ liệu trên mũi tên để người đọc biết đó là command, entity, event, response hay bản ghi lưu trữ.

| Góc nhìn | Câu hỏi | Hướng mũi tên | Bằng chứng |
|---|---|---|---|
| Phụ thuộc mã nguồn | A cần biết kiểu hoặc module nào? | Bên sử dụng kiểu → nơi định nghĩa kiểu | Import, field, tham số, implements, module dependency |
| Lời gọi khi chạy | Ai gọi ai trong một lần xử lý? | Caller → callee thực tế | Call stack, trace, breakpoint, sequence diagram |
| Truyền dữ liệu | Giá trị đi từ đâu đến đâu? | Nguồn dữ liệu → nơi nhận hoặc lưu | DTO mapping, tham số, kết quả, message, persistence mapping |

Đừng dùng một sơ đồ không chú thích để thể hiện cả ba loại mũi tên. Cùng một cặp thành phần có thể có hướng gọi và hướng dữ liệu khác nhau, hoặc có thể không có dependency mã nguồn trực tiếp đến implementation đang chạy.

## 2. Ví dụ xuyên suốt: tạo đơn hàng trong Spring

Giả sử ứng dụng nhận yêu cầu tạo đơn hàng. Một cách tổ chức có thể gồm:

- **Presentation:** **OrderController** nhận HTTP request, kiểm tra cấu trúc đầu vào và chuyển request DTO thành command.
- **Application:** **CreateOrderService** điều phối use case, tải dữ liệu cần thiết, gọi hành vi domain và lưu kết quả.
- **Domain:** **Order** và các kiểu liên quan bảo vệ quy tắc như số lượng dương và trạng thái đơn hợp lệ.
- **Infrastructure / Data access:** **JpaOrderRepository** triển khai hợp đồng lưu trữ bằng Spring Data JPA.

Đây là cách chia trách nhiệm minh họa, không phải quy định mọi ứng dụng phải có đúng bốn layer hoặc phải sử dụng DDD. Một hệ thống nhỏ có thể gộp package hoặc lớp; điều cần giữ là ranh giới và quy tắc phụ thuộc phải dễ hiểu.

### Dependency graph: mã nguồn cần biết kiểu nào?

Application định nghĩa hợp đồng use case và repository mà nó cần:

~~~java
public interface CreateOrderUseCase {
    CreateOrderResult handle(CreateOrderCommand command);
}

public interface OrderRepository {
    OrderId save(Order order);
}

public record CreateOrderCommand(
        String customerId,
        List<CreateOrderLine> lines
) {}

public record CreateOrderLine(String productId, int quantity) {}

public record CreateOrderResult(String orderId) {}
~~~

Service triển khai use case và sử dụng repository qua interface:

~~~java
public class CreateOrderService implements CreateOrderUseCase {
    private final OrderRepository orders;

    public CreateOrderService(OrderRepository orders) {
        this.orders = orders;
    }

    @Override
    public CreateOrderResult handle(CreateOrderCommand command) {
        CustomerId customerId = new CustomerId(command.customerId());
        List<OrderLine> lines = command.lines().stream()
                .map(line -> OrderLine.of(
                        new ProductId(line.productId()), line.quantity()))
                .toList();
        Order order = Order.place(customerId, lines);
        OrderId id = orders.save(order);
        return new CreateOrderResult(id.value());
    }
}
~~~

Trong ví dụ, **CreateOrderCommand** là kiểu đầu vào của application, còn **OrderLine** và **ProductId** là kiểu domain. Phương thức **OrderLine.of** và **Order.place** được giả định thực hiện kiểm tra bất biến tương ứng. Nhờ bước ánh xạ này, dữ liệu thô từ request không trở thành mô hình lưu trữ hoặc quy tắc miền.

Adapter persistence triển khai hợp đồng:

~~~java
public class JpaOrderRepository implements OrderRepository {
    private final SpringDataOrderJpaRepository jpa;

    public JpaOrderRepository(SpringDataOrderJpaRepository jpa) {
        this.jpa = jpa;
    }

    @Override
    public OrderId save(Order order) {
        OrderEntity entity = OrderEntity.from(order);
        OrderEntity saved = jpa.save(entity);
        return new OrderId(saved.getId());
    }
}
~~~

Hướng phụ thuộc mã nguồn có thể mô tả như sau:

~~~mermaid
flowchart TD
    C[OrderController] -->|uses| U[CreateOrderUseCase]
    S[CreateOrderService] -->|implements| U
    S -->|uses| R[OrderRepository]
    A[JpaOrderRepository] -->|implements| R
    A -->|uses| J[SpringDataOrderJpaRepository]
    J --> L[Spring Data JPA]
~~~

Mũi tên có nghĩa là mã nguồn ở đầu mũi tên cần biết hợp đồng hoặc API ở cuối mũi tên. **JpaOrderRepository** phải biết **OrderRepository** để triển khai interface đó. **CreateOrderService** chỉ cần biết interface **OrderRepository**; nó không cần import **JpaOrderRepository**. Đây là một cách áp dụng dependency inversion: application định nghĩa abstraction theo nhu cầu của use case, infrastructure cung cấp implementation.

### Runtime call flow: object nào thực sự nhận lời gọi?

Khi ứng dụng chạy, Spring tạo các bean và inject implementation phù hợp. Luồng điều khiển của request có thể là:

~~~mermaid
sequenceDiagram
    actor User as Người dùng
    participant C as OrderController
    participant S as CreateOrderService
    participant A as JpaOrderRepository
    participant J as Spring Data JPA
    participant DB as Database

    User->>C: POST /orders
    C->>S: handle(command)
    S->>A: save(order)
    A->>J: save(entity)
    J->>DB: INSERT hoặc UPDATE
    DB-->>J: Kết quả lưu
    J-->>A: Entity đã lưu
    A-->>S: OrderId
    S-->>C: CreateOrderResult
    C-->>User: HTTP 201 Created
~~~

Ở thời điểm chạy, **CreateOrderService** gọi object **JpaOrderRepository** qua tham chiếu có kiểu **OrderRepository**. Vì vậy:

- Dependency mã nguồn của service hướng đến interface **OrderRepository**.
- Lời gọi khi chạy từ service được dispatch đến object **JpaOrderRepository**.
- Adapter gọi tiếp API của Spring Data JPA.

Hai mũi tên đầu tiên mô tả hai quan hệ khác nhau. Không thể nhìn dependency graph rồi kết luận chính xác implementation runtime nếu chưa biết cấu hình bean. Ngược lại, quan sát call stack cho biết object nào đã nhận lời gọi trong một lần chạy, nhưng không tự nó mô tả toàn bộ quy tắc phụ thuộc mã nguồn của module.

## 3. Data flow: giá trị di chuyển và biến đổi ra sao?

Trong cùng use case, dữ liệu đầu vào và kết quả có thể đi theo các bước:

~~~mermaid
flowchart TD
    H[HTTP JSON request] -->|deserialize| DTO[CreateOrderRequest]
    DTO -->|map| CMD[CreateOrderCommand]
    CMD -->|input values| S[CreateOrderService]
    S -->|create| D[Order domain object]
    D -->|map| E[OrderEntity]
    E -->|persist| DB[(Database row)]
    DB -->|generated identifier| A[JpaOrderRepository]
    A -->|OrderId| S
    S -->|CreateOrderResult| C[OrderController]
    C -->|serialize| R[HTTP response]
~~~

Ở đây, các mũi tên thể hiện dữ liệu được chuyển giao hoặc biến đổi:

1. JSON được framework giải mã thành **CreateOrderRequest**.
2. Controller ánh xạ request DTO thành **CreateOrderCommand**, là dữ liệu đầu vào của use case.
3. Application dùng command để yêu cầu domain tạo **Order**.
4. Adapter chuyển **Order** thành **OrderEntity** phù hợp với persistence model.
5. Database lưu entity và có thể tạo identifier.
6. Identifier được chuyển ngược qua repository và application thành **CreateOrderResult**.
7. Controller ánh xạ kết quả thành HTTP response.

Ở bước gọi **orders.save(order)**, lời gọi điều khiển đi từ service đến adapter; đồng thời giá trị **order** được truyền từ service sang adapter. Khi adapter trả về **OrderId**, lời gọi kết thúc và dữ liệu kết quả đi ngược lại. Hai luồng này thường xuất hiện cùng nhau trong lời gọi đồng bộ nhưng vẫn là hai khái niệm riêng.

Không phải mọi dữ liệu đều cần đi xuyên qua tất cả layer. Controller không nhất thiết chuyển nguyên HTTP request vào application; adapter không nên đưa entity JPA vào domain; response không nhất thiết là bản sao của entity. Mỗi ranh giới nên có kiểu dữ liệu phù hợp với trách nhiệm của nó.

## 4. Lắp ráp ứng dụng: dependency được nối với implementation ở đâu?

**Composition** là việc tạo và nối các object cần thiết thành một object graph có thể chạy được. **Composition root** là vị trí cấu hình hoặc khởi tạo graph đó. Trong ứng dụng Spring, container thường đóng vai trò này: nó tạo bean, quản lý vòng đời và inject dependency qua constructor.

Ví dụ cấu hình tường minh:

~~~java
@Configuration
public class OrderPersistenceConfiguration {
    @Bean
    OrderRepository orderRepository(SpringDataOrderJpaRepository jpa) {
        return new JpaOrderRepository(jpa);
    }
}
~~~

Service nhận interface qua constructor:

~~~java
@Service
public class CreateOrderService implements CreateOrderUseCase {
    private final OrderRepository orders;

    public CreateOrderService(OrderRepository orders) {
        this.orders = orders;
    }

    // handle(...) như ví dụ phía trên
}
~~~

Khi khởi động, Spring tìm bean **OrderRepository**, gọi factory method để tạo **JpaOrderRepository** rồi truyền object đó vào constructor của service. Composition root là nơi biết cả interface lẫn implementation cụ thể. Service vẫn chỉ cần biết interface.

Constructor injection làm dependency của lớp hiện rõ, giúp kiểm thử bằng fake hoặc mock và tránh object ở trạng thái thiếu dependency. Dependency injection không làm biến mất phụ thuộc; nó làm cho việc cung cấp dependency được quản lý ở nơi lắp ráp. Nếu có nhiều implementation cùng phù hợp, cần chọn rõ ràng bằng **@Qualifier**, **@Primary**, profile hoặc cấu hình có điều kiện. Cấu hình phải bảo đảm mỗi use case nhận đúng implementation cho môi trường đang chạy.

Trong dự án dùng component scanning, **@Component**, **@Repository** và **@Service** có thể giảm lượng cấu hình tường minh. Dù dùng cách nào, nhóm vẫn cần biết bean nào được tạo, phụ thuộc nào được inject và cấu hình nào chọn implementation. Với ứng dụng không dùng Spring, composition root có thể là hàm khởi tạo ở **main**, một factory hoặc bootstrap module.

## 5. Khi ba hướng không giống nhau

Hãy xét một service khai báo:

~~~java
private final OrderRepository orders;
~~~

và gọi:

~~~java
orders.save(order);
~~~

Tại đây có thể xác định:

- **Phụ thuộc mã nguồn:** **CreateOrderService** cần kiểu **OrderRepository**.
- **Lời gọi khi chạy:** object được tham chiếu thực tế có thể là **JpaOrderRepository**.
- **Truyền dữ liệu:** object **Order** đi từ service đến adapter; **OrderId** đi từ adapter trở về service.

Nếu thay adapter JPA bằng adapter lưu trữ khác, dependency mã nguồn của service không cần đổi miễn là interface và hợp đồng không đổi. Object nhận lời gọi runtime sẽ thay đổi theo composition. Dữ liệu vẫn được truyền theo hợp đồng **save**, dù cách adapter biến đổi và lưu dữ liệu có thể khác.

Trong một luồng bất đồng bộ, ba hướng còn dễ phân biệt hơn. Ví dụ, service ghi một event vào outbox; worker đọc event và gửi message đến broker; consumer nhận message sau đó. Nơi phát event không nhất thiết gọi trực tiếp consumer. Dependency mã nguồn giữa hai ứng dụng có thể không tồn tại, runtime call trực tiếp giữa chúng cũng không có, nhưng dữ liệu event vẫn di chuyển qua broker. Khi đó, event schema và hợp đồng message là ranh giới dữ liệu cần quản lý.

## 6. Cách kiểm tra từng hướng trong dự án

### Kiểm tra phụ thuộc mã nguồn

1. Xem import, field, constructor parameter, method signature, **extends** và **implements**.
2. Kiểm tra module build nào khai báo dependency đến module nào.
3. Đối chiếu các quan hệ đó với quy tắc layer. Ví dụ, domain có import Spring Data hoặc web framework không; application có import adapter cụ thể không?
4. Có thể dùng ArchUnit hoặc quy tắc build để tự động kiểm tra package/module không phụ thuộc sai chiều.

### Kiểm tra lời gọi khi chạy

1. Bắt đầu từ entry point như controller, message listener hoặc scheduled job.
2. Dùng breakpoint, call stack hoặc distributed trace để theo luồng điều khiển.
3. Khi lời gọi đi qua interface, kiểm tra class thực tế của object nhận lời gọi.
4. Xem thêm proxy của framework, transaction interceptor và các lời gọi bất đồng bộ nếu chúng xuất hiện trong luồng.

### Kiểm tra hướng truyền dữ liệu

1. Xác định nguồn dữ liệu: request, database, cache, message hay hệ thống bên ngoài.
2. Theo dõi các bước deserialize, mapping, validation, chuyển đổi đơn vị và lưu trữ.
3. Ghi rõ kiểu dữ liệu qua từng ranh giới: DTO, command, domain object, persistence entity, event hoặc response.
4. Kiểm tra dữ liệu nhạy cảm, dữ liệu cũ và metadata cần giữ để truy vết.

Ba cách kiểm tra bổ sung cho nhau. Một test kiến trúc có thể phát hiện import sai layer nhưng không chứng minh luồng runtime chọn đúng bean. Một integration test có thể chứng minh Spring nối bean và persistence hoạt động, nhưng không tự chứng minh dữ liệu được chuyển đổi đúng ngữ nghĩa. Cần chọn bằng chứng tương ứng với câu hỏi.

## 7. Những nhầm lẫn thường gặp

- **Dùng một mũi tên cho cả ba loại sơ đồ.** Hãy đặt tên sơ đồ và chú thích mũi tên là **depends on**, **calls** hay **data**.
- **Cho rằng interface là object thực thi.** Interface là kiểu mà caller biết; object runtime là instance của implementation được cung cấp.
- **Cho rằng dependency injection xóa dependency.** Lớp vẫn phụ thuộc vào kiểu trong constructor; container chỉ đảm nhiệm việc cung cấp object.
- **Cho rằng dữ liệu luôn đi cùng chiều lời gọi.** Tham số thường đi từ caller đến callee, kết quả thường trở về caller; event có thể đi qua broker mà không có lời gọi trực tiếp.
- **Đưa mọi kiểu dữ liệu vào chung một model.** HTTP DTO, domain object và JPA entity có vòng đời, mục đích và ràng buộc khác nhau.
- **Suy ra runtime graph chỉ từ source graph.** Cần xem composition và cấu hình môi trường để biết implementation nào thực sự được nối.
- **Đảo chiều mọi dependency một cách máy móc.** Hướng phụ thuộc nên tuân theo ranh giới và mục tiêu thay đổi của hệ thống; abstraction chỉ hữu ích khi nó biểu đạt một hợp đồng có ý nghĩa.

## 8. Checklist khi thiết kế và review

Khi review một luồng xử lý, hãy tự hỏi:

- Dependency mã nguồn của mỗi layer đang hướng đến kiểu hoặc module nào?
- Caller gọi qua abstraction nào và implementation runtime được chọn ở đâu?
- Dữ liệu đầu vào, dữ liệu domain, persistence model và response được chuyển đổi ở ranh giới nào?
- Có adapter hoặc DTO của framework lọt vào layer không nên biết đến chúng không?
- Composition root có nối đủ và đúng các dependency cho môi trường hiện tại không?
- Có cách kiểm tra độc lập dependency graph, runtime call flow và data flow không?
- Nếu thay implementation hoặc giao thức bên ngoài, phần nào của ứng dụng cần thay đổi?

Một thiết kế phân tầng dễ hiểu khi ba hướng được mô tả và kiểm tra riêng. Dependency graph cho biết mã nguồn cần biết điều gì; runtime call flow cho biết chương trình thực sự gọi thành phần nào; data flow cho biết giá trị được chuyển đổi và lưu ở đâu. Composition root nối các implementation để hệ thống chạy được. Phân biệt rõ ba góc nhìn này giúp nhóm thay đổi adapter, kiểm soát ranh giới layer và theo dõi dữ liệu mà không nhầm một quan hệ với quan hệ khác.
