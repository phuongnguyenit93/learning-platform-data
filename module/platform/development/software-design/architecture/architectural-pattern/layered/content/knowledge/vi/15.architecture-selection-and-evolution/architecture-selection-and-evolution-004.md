# So sánh layered với onion và clean architecture theo hướng phụ thuộc

Bài học này thuộc module **SOFTWARE_DESIGN_ARCHITECTURE_ARCHITECTURAL_PATTERN_LAYERED** — **Học tổ chức phần mềm theo kiến trúc phân tầng**, trong chương **Lựa chọn và tiến hóa kiến trúc**. Layered, Onion Architecture và Clean Architecture đều giúp tổ chức phần mềm thành những vùng trách nhiệm có ranh giới. Điểm khác biệt đáng quan tâm khi lựa chọn không nằm ở hình vẽ nhiều tầng hay các vòng tròn, mà ở cách mỗi kiến trúc định hướng **phụ thuộc mã nguồn** và bảo vệ phần nghiệp vụ trước các chi tiết bên ngoài.

Ba cách tiếp cận có thể cùng dùng những khái niệm như presentation, application, domain và infrastructure. Tuy nhiên, chúng nhấn mạnh các quy tắc khác nhau. Layered truyền thống thường tổ chức theo trách nhiệm kỹ thuật và cho phép layer phía trên phụ thuộc layer phía dưới. Onion và Clean nhấn mạnh quy tắc phụ thuộc hướng vào lõi; abstraction được đặt ở phía trong, còn chi tiết kỹ thuật ở phía ngoài triển khai các hợp đồng đó. Đây là các mô hình thiết kế, không phải yêu cầu về số tiến trình, máy chủ hoặc container.

## 1. Phân biệt hướng phụ thuộc với hướng gọi khi chạy

Trước khi so sánh, cần phân biệt hai loại mũi tên:

- **Phụ thuộc mã nguồn (source-code dependency):** lớp hoặc module nào cần biết kiểu/API của lớp hoặc module nào để biên dịch. Nếu A import hoặc khai báo một kiểu của B, có thể nói A phụ thuộc B; mũi tên đi từ A đến B.
- **Hướng gọi khi chạy (runtime call direction):** thành phần nào thực sự gọi thành phần nào trong một lần xử lý. Mũi tên đi từ caller đến callee thực tế.

Trong thiết kế dùng interface, hai hướng này có thể khác nhau. Một use case gọi phương thức qua interface repository do application sở hữu; object nhận lời gọi thực tế có thể là adapter JPA nằm ở infrastructure. Mã nguồn application phụ thuộc vào interface phía trong, trong khi lời gọi runtime được dispatch đến object adapter phía ngoài.

Không nên nhìn một sequence diagram rồi kết luận về hướng phụ thuộc mã nguồn. Cũng không nên chỉ nhìn import để suy ra object runtime được Spring inject là lớp nào. Khi review kiến trúc, hãy kiểm tra riêng dependency graph, runtime call flow và nơi lắp ráp object.

## 2. Layered Architecture: tổ chức theo các layer trách nhiệm

Layered Architecture chia ứng dụng thành các layer có trách nhiệm khác nhau. Một cách tổ chức thường gặp:

| Layer | Trách nhiệm |
|---|---|
| Presentation | Nhận yêu cầu từ HTTP, giao diện hoặc giao thức khác; chuyển kết quả thành phản hồi |
| Application / Business | Điều phối ca sử dụng, trình tự thao tác và ranh giới giao dịch |
| Domain | Mô hình hóa khái niệm, hành vi và quy tắc nghiệp vụ |
| Data access / Infrastructure | Truy cập database, filesystem, message broker hoặc dịch vụ bên ngoài |

Trong layered truyền thống, một cách tổ chức phổ biến là layer phía trên gọi layer ngay bên dưới:

~~~mermaid
flowchart TD
    P[Presentation] --> A[Application / Business]
    A --> D[Domain]
    D --> R[Data access]
~~~

Sơ đồ này minh họa một biến thể phân tầng theo hướng gọi và phụ thuộc đi xuống. Một số hệ thống gộp domain vào business layer; một số khác để application service gọi domain và repository. Không có một số lượng layer bắt buộc cho mọi ứng dụng.

### Closed layering và open layering

Với **closed layering**, một layer chỉ được gọi layer kế tiếp ở phía dưới. Ví dụ, presentation gọi application, application gọi domain hoặc port lưu trữ; presentation không tự gọi thẳng persistence. Cách này làm luồng trách nhiệm dễ theo dõi và ngăn các layer bỏ qua nhau.

Với **open layering**, một layer có thể gọi xuyên qua một hoặc nhiều layer bên dưới khi có lý do. Cách này đôi khi hữu ích cho truy vấn đơn giản hoặc đường đọc tối ưu, nhưng nếu cho phép tùy tiện sẽ tạo layer bypass: controller tự gọi DAO, module nghiệp vụ tự truy cập bảng của module khác, hoặc các quy tắc bị sao chép ở nhiều nơi.

Closed/open layering nói về quy tắc truy cập giữa các layer. Nó không tự xác định mọi dependency phải hướng vào trong hay ra ngoài. Trong một layered architecture hiện đại, nhóm vẫn có thể dùng dependency inversion để application định nghĩa repository interface và infrastructure triển khai interface đó.

## 3. Onion Architecture: domain ở trung tâm

Onion Architecture đặt mô hình domain ở lõi và tổ chức các vùng trách nhiệm thành những vòng bao quanh. Các vòng phía trong không phụ thuộc vào vòng phía ngoài. Tên và số vòng có thể thay đổi theo cách triển khai, nhưng quy tắc quan trọng là **dependency hướng vào domain core**.

Một cách biểu diễn khái quát:

~~~mermaid
flowchart TB
    subgraph OUT["Infrastructure và giao diện bên ngoài"]
        subgraph APP["Application services"]
            subgraph DS["Domain services và domain model"]
                CORE["Entities và value objects"]
            end
        end
    end
~~~

Trong mô hình này:

- **Domain model** chứa entity, value object và các bất biến nghiệp vụ.
- **Domain services** biểu đạt hành vi nghiệp vụ không thuộc tự nhiên về một entity cụ thể.
- **Application services** điều phối use case, làm việc với domain và các abstraction cần thiết.
- **Infrastructure và UI** cung cấp giao tiếp với database, web framework, message broker và dịch vụ bên ngoài.

Các vòng phía ngoài được phép biết và sử dụng abstraction phía trong. Domain core không cần import Spring, JPA, HTTP client hoặc tên database. Nếu domain cần lưu một aggregate, hợp đồng lưu trữ được đặt ở phía trong theo nhu cầu domain/application; adapter ở vòng ngoài triển khai hợp đồng đó.

Onion nhấn mạnh việc bảo vệ domain khỏi các chi tiết kỹ thuật và làm cho domain có thể kiểm thử độc lập. Nó không có nghĩa mọi quy tắc điều phối use case phải nằm trong entity. Application service vẫn có vai trò điều phối; domain model giữ những hành vi và bất biến thuộc nghiệp vụ.

## 4. Clean Architecture: ranh giới use case và quy tắc phụ thuộc

Clean Architecture cũng tổ chức các vòng đồng tâm và yêu cầu source-code dependencies hướng vào trong. Một cách phân chia thường gặp:

~~~mermaid
flowchart TB
    subgraph F["Frameworks and Drivers"]
        subgraph IA["Interface Adapters"]
            subgraph UC["Use Cases"]
                E["Entities"]
            end
        end
    end
~~~

Các vùng có ý nghĩa:

- **Entities:** quy tắc nghiệp vụ cấp enterprise hoặc domain, có thể được dùng bởi nhiều use case.
- **Use Cases:** quy tắc ứng dụng cụ thể; mô tả ứng dụng làm gì để đạt một mục tiêu, điều phối entity và xác định các boundary cần thiết.
- **Interface Adapters:** chuyển đổi dữ liệu giữa giao thức bên ngoài và kiểu mà use case/entity cần. Controller, presenter, gateway hoặc repository adapter thường nằm ở vùng này.
- **Frameworks and Drivers:** framework web, ORM, database driver, message broker và các công nghệ cụ thể.

Clean Architecture nhấn mạnh **Dependency Rule**: mã nguồn ở vòng ngoài có thể phụ thuộc vào vòng trong; vòng trong không được biết tên hoặc chi tiết của vòng ngoài. Khi một use case cần lưu dữ liệu, nó định nghĩa output port hoặc interface cần thiết. Gateway/repository adapter ở ngoài triển khai interface đó.

Ranh giới use case thường được thể hiện bằng input boundary và output boundary. Controller chuyển request thành input data rồi gọi input port. Use case thực hiện công việc và gửi output data qua output port; presenter chuyển dữ liệu đó thành response phù hợp. Cách tổ chức cụ thể có thể gọn hơn, nhưng mục đích là để use case không phụ thuộc trực tiếp vào HTTP response, ORM entity hay framework.

Clean Architecture thường mô tả ranh giới và luồng dữ liệu use case rõ ràng hơn. Tuy nhiên, không cần tạo interface và lớp riêng cho mọi thao tác nếu chúng không đem lại giá trị. Hãy dùng boundary khi nó bảo vệ một hợp đồng hoặc lý do thay đổi có ý nghĩa.

## 5. So sánh theo hướng phụ thuộc

| Góc nhìn | Layered truyền thống | Onion Architecture | Clean Architecture |
|---|---|---|---|
| Cách tổ chức chính | Các layer theo trách nhiệm kỹ thuật | Các vòng quanh domain core | Các vòng theo entity, use case, adapter và framework |
| Hướng phụ thuộc điển hình | Thường từ layer trên xuống layer dưới | Từ vòng ngoài hướng vào domain core | Từ vòng ngoài hướng vào use case/entity |
| Trọng tâm | Phân chia trách nhiệm và thứ tự truy cập layer | Bảo vệ domain model khỏi chi tiết ngoài | Bảo vệ use case và entity bằng Dependency Rule |
| Abstraction lưu trữ | Có thể nằm ở data layer trong biến thể đơn giản; có thể đảo chiều trong layered hiện đại | Được định nghĩa ở phía trong, adapter nằm ngoài | Use case hoặc inner layer định nghĩa port; gateway nằm ngoài |
| Boundary giao diện | Controller/service theo cách chia layer | UI là vòng ngoài | Controller, presenter, gateway là interface adapters |
| Câu hỏi thiết kế nổi bật | Layer nào được gọi layer nào? | Domain có bị chi tiết bên ngoài chi phối không? | Use case giữ được độc lập với framework và delivery mechanism không? |

Không nên xem bảng này như ba công thức tuyệt đối. Layered có thể áp dụng dependency inversion; Onion và Clean cũng thường được triển khai bằng các package hoặc layer có tên tương tự layered. Khác biệt chủ yếu là quy tắc phụ thuộc được nhấn mạnh và cách làm rõ domain/use case boundary.

### Hình dung dependency graph

Trong layered truyền thống đơn giản, mã nguồn có thể phụ thuộc theo chiều:

~~~mermaid
flowchart TD
    P[Presentation] --> A[Application]
    A --> D[Domain]
    A --> I[Persistence implementation]
~~~

Trong thiết kế hướng vào trong, application định nghĩa port và adapter phụ thuộc vào port:

~~~mermaid
flowchart TD
    C[Controller / Adapter] --> U[Use case interface]
    S[Use case implementation] --> D[Domain]
    S --> R[Repository port]
    A[Repository adapter] --> R
    A --> DB[(Database)]
~~~

Ở sơ đồ thứ hai, adapter repository nằm ở infrastructure nhưng mã nguồn adapter phụ thuộc vào port phía trong để triển khai. Use case gọi repository qua port; object adapter được nối ở composition root. Vì vậy, source dependency có thể hướng vào trong trong khi runtime call từ use case đến object adapter đi ra ngoài.

## 6. Ví dụ Java/Spring: cùng một use case, ba cách nhìn

Giả sử ứng dụng cần tạo đơn hàng. Use case phải tạo aggregate hợp lệ và lưu đơn. Hợp đồng có thể được định nghĩa như sau:

~~~java
public interface PlaceOrderUseCase {
    PlaceOrderResult handle(PlaceOrderCommand command);
}

public interface OrderRepository {
    OrderId save(Order order);
}
~~~

Application service triển khai use case:

~~~java
public class PlaceOrderService implements PlaceOrderUseCase {
    private final OrderRepository orders;

    public PlaceOrderService(OrderRepository orders) {
        this.orders = orders;
    }

    @Override
    public PlaceOrderResult handle(PlaceOrderCommand command) {
        Order order = Order.place(command.customerId(), command.lines());
        OrderId id = orders.save(order);
        return new PlaceOrderResult(id.value());
    }
}
~~~

Adapter persistence ở infrastructure:

~~~java
@Repository
public class JpaOrderRepository implements OrderRepository {
    private final SpringDataOrderJpaRepository jpa;

    public JpaOrderRepository(SpringDataOrderJpaRepository jpa) {
        this.jpa = jpa;
    }

    @Override
    public OrderId save(Order order) {
        OrderEntity entity = OrderEntity.fromDomain(order);
        OrderEntity saved = jpa.save(entity);
        return new OrderId(saved.getId());
    }
}
~~~

Controller nhận request và gọi use case:

~~~java
@RestController
public class OrderController {
    private final PlaceOrderUseCase placeOrder;

    public OrderController(PlaceOrderUseCase placeOrder) {
        this.placeOrder = placeOrder;
    }

    @PostMapping("/orders")
    public ResponseEntity<OrderResponse> place(
            @RequestBody PlaceOrderRequest request) {
        PlaceOrderResult result =
                placeOrder.handle(request.toCommand());
        return ResponseEntity.status(201)
                .body(OrderResponse.from(result));
    }
}
~~~

Trong ví dụ này, có thể đọc ba quan hệ riêng:

1. **Source dependency:** controller phụ thuộc vào PlaceOrderUseCase; PlaceOrderService triển khai interface đó; PlaceOrderService phụ thuộc vào OrderRepository; JpaOrderRepository triển khai OrderRepository.
2. **Runtime call:** controller gọi object PlaceOrderService; service gọi phương thức save trên tham chiếu OrderRepository; object nhận lời gọi thực tế là JpaOrderRepository nếu Spring đã inject bean đó.
3. **Data flow:** request DTO được chuyển thành command; command tạo Order; Order được chuyển thành OrderEntity trong adapter; kết quả lưu được chuyển thành OrderId rồi thành response.

Trong Spring, constructor injection và cấu hình bean là một cách lắp ráp implementation. Nếu có nhiều bean triển khai cùng interface, cần cấu hình lựa chọn rõ ràng bằng qualifier, primary hoặc bean configuration. Dependency injection không tự đảo chiều source dependency; chính việc đặt interface ở phía trong và để adapter phía ngoài triển khai nó mới tạo ra hướng phụ thuộc mong muốn.

## 7. Chọn kiến trúc theo quy mô và nhu cầu

### Khi layered đơn giản là đủ

Layered có thể phù hợp khi ứng dụng nhỏ, nghiệp vụ chưa phức tạp, nhóm cần cấu trúc dễ hiểu và hầu hết thay đổi diễn ra trong cùng một phạm vi. Các layer có thể dùng repository abstraction nếu cần thay đổi persistence hoặc kiểm thử. Không cần xây dựng nhiều vòng, port và presenter chỉ để tuân theo một hình mẫu.

### Khi Onion có ích

Onion đáng cân nhắc khi domain có nhiều quy tắc, vòng đời và bất biến cần được bảo vệ; nhiều use case cùng sử dụng mô hình domain; hoặc framework/persistence có khả năng thay đổi. Việc đặt domain ở trung tâm giúp giảm tác động từ công nghệ bên ngoài và kiểm thử nghiệp vụ độc lập.

### Khi Clean có ích

Clean hữu ích khi use case có ranh giới rõ, ứng dụng có nhiều cách giao tiếp (REST, CLI, message consumer, batch) hoặc cần tách biệt rõ input/output contract khỏi framework. Nó giúp xác định ai gọi use case, use case cần những port nào và dữ liệu đi qua boundary ra sao.

### Các yếu tố cần cân nhắc

| Tiêu chí | Câu hỏi khi lựa chọn |
|---|---|
| Độ phức tạp nghiệp vụ | Có nhiều bất biến và hành vi domain cần bảo vệ không? |
| Số cách truy cập ứng dụng | Có nhiều controller, consumer, batch hoặc giao diện cùng gọi use case không? |
| Khả năng thay đổi hạ tầng | Database, framework hoặc nhà cung cấp có khả năng thay đổi đáng kể không? |
| Kiểm thử | Có cần kiểm thử domain/use case mà không khởi động framework hoặc database không? |
| Quy mô nhóm | Nhóm có đủ năng lực duy trì abstraction, module boundary và quy tắc kiến trúc không? |
| Chi phí tổ chức | Số lượng interface, mapper và module có giải quyết vấn đề thực tế không? |
| Cấu trúc triển khai | Ứng dụng chạy trong một process hay nhiều service? Đây là quyết định triển khai riêng, không được suy ra trực tiếp từ layered/onion/clean. |

Một hệ thống không nhất thiết chọn duy nhất một tên kiến trúc cho mọi module. Có thể dùng layered package structure, áp dụng dependency rule của Clean cho use case và giữ domain core theo tư tưởng Onion. Điều cần tránh là trộn các quy tắc mâu thuẫn mà không định nghĩa rõ module nào tuân theo quy tắc nào.

## 8. Các nhầm lẫn thường gặp

- **Cho rằng layered luôn phụ thuộc từ trên xuống:** đó là một biến thể phổ biến; layered hiện đại có thể đảo chiều phụ thuộc bằng port và adapter.
- **Cho rằng Onion và Clean là hai tên hoàn toàn đồng nghĩa:** chúng chia sẻ dependency direction hướng vào trong, nhưng cách nhấn mạnh domain core, use case boundary và interface adapter có khác biệt.
- **Cho rằng domain phải chứa toàn bộ nghiệp vụ:** domain giữ quy tắc và bất biến; application vẫn điều phối use case và các tác động bên ngoài.
- **Cho rằng vòng tròn đồng nghĩa với deployment tier:** các vòng là vùng logic; chúng có thể cùng nằm trong một JVM hoặc được phân phối theo nhu cầu triển khai riêng.
- **Cho rằng interface nào cũng phải nằm ở domain:** đặt abstraction nơi có trách nhiệm sở hữu hợp đồng; port có thể thuộc application hoặc domain tùy ngữ nghĩa.
- **Cho rằng dependency injection tự làm source dependency hướng vào trong:** container chỉ cung cấp object; hướng phụ thuộc được quyết định bởi các kiểu mà mã nguồn tham chiếu.
- **Tạo quá nhiều abstraction:** interface và mapper chỉ có ích khi bảo vệ ranh giới, biểu đạt hợp đồng hoặc hỗ trợ một nhu cầu thay đổi/kiểm thử cụ thể.

## 9. Cách đánh giá và tiến hóa từ layered

Khi một ứng dụng layered bắt đầu khó thay đổi, không cần viết lại toàn bộ kiến trúc ngay. Hãy đánh giá từng ranh giới:

1. Xác định domain rule hoặc use case nào đang phụ thuộc trực tiếp vào framework, ORM hoặc lớp persistence.
2. Xác định hợp đồng mà application/domain thực sự cần, ví dụ repository port, clock, payment gateway hoặc notification sender.
3. Đặt abstraction ở phía sở hữu nhu cầu; chuyển implementation kỹ thuật sang adapter bên ngoài.
4. Thay các lời gọi trực tiếp bằng constructor injection và nối adapter tại composition root.
5. Chuyển đổi DTO/persistence entity tại boundary để model nội bộ không bị schema hoặc giao thức chi phối.
6. Thêm test kiến trúc để kiểm tra hướng phụ thuộc, unit test cho domain/use case và integration test cho adapter.
7. Tiến hóa từng use case hoặc module, đo xem abstraction có làm thiết kế dễ thay đổi hơn không.

Ví dụ, một ứng dụng ban đầu có ApplicationService import trực tiếp JpaRepository. Có thể bắt đầu bằng cách định nghĩa interface repository theo nhu cầu use case, cho adapter JPA triển khai interface đó và inject qua constructor. Domain/use case được kiểm thử bằng fake repository; adapter được kiểm thử riêng với database thử nghiệm. Đây là bước tiến hóa theo dependency inversion mà không cần thay đổi cách đóng gói hay triển khai ứng dụng.

## 10. Checklist review hướng phụ thuộc

Khi chọn hoặc review layered, onion hay clean, hãy tự hỏi:

- Mỗi layer/vòng có trách nhiệm rõ ràng không?
- Mã nguồn ở phía trong có import framework, ORM hoặc adapter bên ngoài không?
- Hợp đồng repository/gateway được đặt ở nơi sở hữu nhu cầu hay bị đặt theo vị trí công nghệ?
- Adapter triển khai hợp đồng và được nối ở composition root chưa?
- Controller có phụ thuộc vào use case boundary thay vì tự điều phối domain và persistence không?
- Domain có bảo vệ bất biến mà không cần biết HTTP hoặc database không?
- Runtime call flow có được phân biệt với source dependency graph không?
- DTO, domain model và persistence model có bị trộn thành một kiểu chỉ vì tiện không?
- Quy tắc phụ thuộc có được kiểm tra tự động và có thể giải thích cho nhóm không?
- Độ phức tạp của abstraction có tương xứng với nhu cầu thay đổi và kiểm thử không?

Layered, Onion và Clean đều có thể hỗ trợ một ứng dụng dễ bảo trì nếu ranh giới trách nhiệm và hướng phụ thuộc được xác định rõ. Layered cung cấp cách chia trách nhiệm dễ tiếp cận; Onion nhấn mạnh domain core; Clean làm rõ use case và các interface adapter. Khi lựa chọn, hãy xem xét mức độ nghiệp vụ, cách thay đổi hạ tầng, các boundary cần kiểm soát và chi phí duy trì. Không chọn chỉ theo tên kiến trúc hoặc hình vẽ; hãy chọn quy tắc phụ thuộc mà nhóm có thể thực thi và kiểm tra trong chính hệ thống.
