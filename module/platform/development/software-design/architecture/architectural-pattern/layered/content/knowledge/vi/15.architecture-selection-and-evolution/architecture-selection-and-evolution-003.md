# So sánh layered với hexagonal theo ranh giới và khả năng cô lập hạ tầng

Layered architecture (kiến trúc phân tầng) và hexagonal architecture (kiến trúc lục giác, còn gọi là Ports and Adapters) đều giúp tổ chức ứng dụng thành các phần có trách nhiệm rõ ràng. Chúng thường được so sánh như hai lựa chọn thay thế, nhưng thực tế chúng tập trung vào hai góc nhìn khác nhau. Layered nhấn mạnh cách chia trách nhiệm thành các tầng; hexagonal nhấn mạnh ranh giới giữa lõi ứng dụng và thế giới bên ngoài thông qua port và adapter.

Trong module SOFTWARE_DESIGN_ARCHITECTURE_ARCHITECTURAL_PATTERN_LAYERED — học tổ chức phần mềm theo kiến trúc phân tầng — bài học này so sánh hai cách tiếp cận theo ranh giới và khả năng cô lập hạ tầng. Mục tiêu là hiểu hướng phụ thuộc, đường đi của lời gọi, cách đặt interface và adapter, chi phí kiểm thử, và khi nào nên giữ một cấu trúc phân tầng đơn giản hoặc bổ sung các ranh giới kiểu hexagonal.

Hai kiến trúc không loại trừ nhau. Một ứng dụng có thể chia thành các tầng presentation, application, domain và infrastructure, đồng thời dùng ports và adapters để giữ lõi ứng dụng độc lập với HTTP, database, message broker hoặc nhà cung cấp bên ngoài. Không có yêu cầu rằng mọi ứng dụng phải áp dụng đầy đủ DDD hoặc phải chuyển sang microservices để dùng hexagonal.

## 1. Layered architecture tập trung vào trách nhiệm của các tầng

Kiến trúc phân tầng chia ứng dụng theo nhóm trách nhiệm. Một cách chia thường gặp gồm:

- Presentation: tiếp nhận giao tiếp như HTTP, giao diện, command line hoặc message.
- Application: điều phối ca sử dụng, quản lý giao dịch và gọi các thành phần cần thiết.
- Domain/business: mô hình hóa khái niệm, hành vi và quy tắc nghiệp vụ.
- Data access/infrastructure: truy cập database, file, message broker và dịch vụ bên ngoài.

Luồng gọi điển hình trong một ứng dụng Spring:

~~~mermaid
flowchart TD
    HTTP[HTTP Controller] --> APP[Application Service]
    APP --> DOMAIN[Domain Model / Policy]
    APP --> REPO[Repository]
    REPO --> DB[(Database)]
~~~

Ví dụ, endpoint đặt đơn nhận request DTO, chuyển thành command, gọi application service. Service tải hoặc tạo entity nghiệp vụ, thực hiện hành vi, rồi yêu cầu repository lưu dữ liệu. Controller chịu trách nhiệm HTTP; service điều phối; domain bảo vệ quy tắc; repository xử lý lưu trữ.

Một cấu trúc package có thể như sau:

~~~text
com.example.shop
├── presentation
│   └── OrderController
├── application
│   └── PlaceOrderService
├── domain
│   ├── Order
│   └── OrderPolicy
└── infrastructure
    └── JpaOrderRepository
~~~

Điểm mạnh của layered architecture là dễ giải thích và dễ bắt đầu. Nhóm có thể nhìn vào tên tầng để biết một lớp thường làm công việc gì. Với ứng dụng nhỏ hoặc vừa, một số package và interface repository có thể đủ để giữ cấu trúc rõ ràng.

Tuy nhiên, tên tầng không tự bảo đảm hướng phụ thuộc tốt. Nếu domain import Spring Data JPA, application service tạo trực tiếp HTTP client, hoặc controller truy cập entity và repository nội bộ, các tầng đã bị gắn với chi tiết triển khai. Một dự án có package presentation/domain/infrastructure vẫn có thể phụ thuộc chặt chẽ nếu không có quy tắc bảo vệ ranh giới.

## 2. Hexagonal architecture tập trung vào lõi và ranh giới bên ngoài

Hexagonal architecture tổ chức ứng dụng quanh một lõi chứa hành vi và chính sách của ứng dụng. Lõi không cần biết nó được gọi từ HTTP, message broker, giao diện dòng lệnh hay một test. Nó cũng không cần biết dữ liệu được lưu bằng PostgreSQL, MongoDB, file hoặc dịch vụ từ xa.

Các thành phần bên ngoài kết nối với lõi qua những hợp đồng gọi là **port**. Một thành phần cụ thể thực hiện hợp đồng đó được gọi là **adapter**.

- Inbound/primary port mô tả cách một actor bên ngoài yêu cầu ứng dụng thực hiện một ca sử dụng.
- Outbound/secondary port mô tả khả năng mà lõi cần từ bên ngoài, ví dụ lưu đơn, gửi thông báo hoặc lấy tỷ giá.
- Inbound adapter chuyển giao thức bên ngoài thành lời gọi port, ví dụ HTTP controller hoặc message listener.
- Outbound adapter hiện thực port bằng công nghệ cụ thể, ví dụ JPA repository, JDBC, Kafka producer hoặc HTTP client.

~~~mermaid
flowchart TD
    HTTP[HTTP Adapter] --> IN[Inbound Port / Use Case]
    CLI[CLI Adapter] --> IN
    MSG[Message Adapter] --> IN
    IN --> CORE[Application and Domain Core]
    CORE --> OUT[Outbound Port]
    OUT -.implemented by.-> DBAD[Database Adapter]
    OUT -.implemented by.-> APIAD[External API Adapter]
    DBAD --> DB[(Database)]
    APIAD --> EXT[External Service]
~~~

Sơ đồ nhấn mạnh rằng các adapter là cách kết nối thế giới bên ngoài với lõi. Lõi định nghĩa những hợp đồng cần thiết; adapter phụ thuộc vào hợp đồng đó và cung cấp cách thực thi.

Một cấu trúc package minh họa:

~~~text
com.example.shop
├── domain
│   ├── Order
│   └── OrderPolicy
├── application
│   ├── port
│   │   ├── in
│   │   │   └── PlaceOrderUseCase
│   │   └── out
│   │       └── OrderRepository
│   └── service
│       └── PlaceOrderService
└── adapter
    ├── in
    │   └── web
    │       └── OrderController
    └── out
        └── persistence
            └── JpaOrderRepositoryAdapter
~~~

Cách đặt package chỉ là một lựa chọn. Port có thể thuộc application hoặc domain tùy hợp đồng phục vụ nhu cầu nào. Điều quan trọng là hợp đồng nằm ở phía sở hữu nhu cầu và không kéo chi tiết adapter vào lõi.

## 3. Khác biệt chính: cách nhìn về ranh giới và phụ thuộc

| Góc nhìn | Layered | Hexagonal |
|---|---|---|
| Trục tổ chức chính | Nhóm trách nhiệm thành các tầng | Phân biệt lõi ứng dụng với actor và công nghệ bên ngoài |
| Câu hỏi trung tâm | Thành phần thuộc tầng trách nhiệm nào? | Lõi cần khả năng nào và bên ngoài kết nối qua port nào? |
| Hướng phụ thuộc | Thường đi từ tầng trên xuống tầng dưới; cần quy tắc để tránh phụ thuộc ngược | Adapter phụ thuộc vào port của lõi; lõi không phụ thuộc adapter |
| Giao tiếp bên ngoài | Thường được đặt trong presentation hoặc infrastructure | Được thể hiện rõ bằng inbound/outbound adapter |
| Cô lập hạ tầng | Có thể đạt được nếu interface và dependency direction được thiết kế tốt | Là mục tiêu được thể hiện trực tiếp qua port và adapter |
| Kiểm thử lõi | Có thể unit test nếu không gắn chặt với framework | Thường dễ thay adapter bằng fake để kiểm thử lõi |
| Độ phức tạp ban đầu | Thường thấp hơn | Có thêm port, adapter và quy tắc lắp ráp |
| Phù hợp | Ứng dụng có luồng xử lý rõ, nhu cầu cách ly vừa phải | Ứng dụng cần nhiều cách giao tiếp, nhiều nguồn dữ liệu hoặc muốn bảo vệ lõi khỏi thay đổi hạ tầng |

Layered trả lời câu hỏi về cách phân chia trách nhiệm; hexagonal trả lời câu hỏi về cách cô lập lõi khỏi thế giới bên ngoài. Một kiến trúc có thể dùng cả hai: các tầng được tổ chức bên trong lõi, còn adapter nằm ở rìa và chỉ kết nối qua port.

## 4. So sánh hướng phụ thuộc lúc biên dịch và lời gọi lúc chạy

Một nhầm lẫn phổ biến là cho rằng hướng gọi lúc chạy phải giống hướng phụ thuộc mã nguồn. Trong hexagonal, hai hướng này thường khác nhau.

Giả sử application layer định nghĩa port:

~~~java
public interface OrderRepository {
    void save(Order order);
    Optional<Order> findById(OrderId id);
}
~~~

Application service phụ thuộc vào port:

~~~java
public final class PlaceOrderService {
    private final OrderRepository orders;

    public PlaceOrderService(OrderRepository orders) {
        this.orders = orders;
    }

    public OrderId place(PlaceOrderCommand command) {
        Order order = Order.create(command.customerId(), command.lines());
        order.place();
        orders.save(order);
        return order.id();
    }
}
~~~

Adapter hạ tầng triển khai port bằng Spring Data JPA:

~~~java
@Repository
@RequiredArgsConstructor
class JpaOrderRepositoryAdapter implements OrderRepository {
    private final SpringDataOrderRepository repository;
    private final OrderMapper mapper;

    @Override
    public void save(Order order) {
        repository.save(mapper.toEntity(order));
    }

    @Override
    public Optional<Order> findById(OrderId id) {
        return repository.findById(id.value()).map(mapper::toDomain);
    }
}
~~~

Hướng phụ thuộc mã nguồn:

~~~mermaid
flowchart LR
    APP[Application Service] --> PORT[OrderRepository port]
    ADAPTER[JPA Adapter] --> PORT
    BOOT[Composition Root] --> APP
    BOOT --> ADAPTER
~~~

Lúc chạy, application service gọi phương thức qua tham chiếu OrderRepository. Đối tượng thực tế được tiêm vào là JpaOrderRepositoryAdapter; runtime dispatch lời gọi đến adapter đó. Vì vậy, lời gọi lúc chạy đi từ lõi ra adapter, nhưng mã nguồn của adapter lại phụ thuộc vào port do lõi định nghĩa.

Đây là cách áp dụng Dependency Inversion Principle. Chi tiết hạ tầng phụ thuộc vào abstraction ổn định của phía cần nó, thay vì lõi phải phụ thuộc vào lớp JPA hoặc JDBC cụ thể.

## 5. Ví dụ cùng một ca sử dụng trong hai cách tổ chức

Xét chức năng tạo đơn hàng. Client gửi yêu cầu HTTP, ứng dụng kiểm tra dữ liệu, tạo đơn, lưu database và trả mã đơn.

### Cách tổ chức layered đơn giản

Controller gọi application service; service phụ thuộc repository interface:

~~~java
@RestController
@RequiredArgsConstructor
@RequestMapping("/orders")
class OrderController {
    private final PlaceOrderService placeOrderService;

    @PostMapping
    ResponseEntity<OrderResponse> place(@Valid @RequestBody PlaceOrderRequest request) {
        OrderId id = placeOrderService.place(request.toCommand());
        return ResponseEntity.status(HttpStatus.CREATED)
            .body(new OrderResponse(id.value()));
    }
}
~~~

~~~java
@Service
@RequiredArgsConstructor
class PlaceOrderService {
    private final OrderRepository orderRepository;

    @Transactional
    public OrderId place(PlaceOrderCommand command) {
        Order order = Order.create(command.customerId(), command.lines());
        order.place();
        orderRepository.save(order);
        return order.id();
    }
}
~~~

Cách này đã có một mức cô lập hạ tầng vì service phụ thuộc interface repository. Nếu interface được định nghĩa ở package application và adapter JPA triển khai nó, hướng phụ thuộc có thể gần với hexagonal. Nếu service phụ thuộc trực tiếp vào Spring Data repository hoặc entity ORM, mức cô lập thấp hơn.

### Cách diễn đạt theo hexagonal

Có thể làm rõ port vào và port ra:

~~~java
public interface PlaceOrderUseCase {
    OrderId place(PlaceOrderCommand command);
}

public interface SaveOrderPort {
    void save(Order order);
}
~~~

Service hiện thực inbound port và sử dụng outbound port:

~~~java
public final class PlaceOrderService implements PlaceOrderUseCase {
    private final SaveOrderPort saveOrder;

    public PlaceOrderService(SaveOrderPort saveOrder) {
        this.saveOrder = saveOrder;
    }

    @Override
    public OrderId place(PlaceOrderCommand command) {
        Order order = Order.create(command.customerId(), command.lines());
        order.place();
        saveOrder.save(order);
        return order.id();
    }
}
~~~

HTTP controller là inbound adapter gọi PlaceOrderUseCase. JpaOrderRepositoryAdapter là outbound adapter triển khai SaveOrderPort. Composition root nối chúng lại bằng Spring configuration hoặc dependency injection.

Điểm khác biệt chính không nằm ở số lượng class. Nó nằm ở việc hợp đồng thể hiện rõ cách actor gọi lõi và khả năng lõi cần từ hạ tầng. Nếu ứng dụng chỉ có một đường HTTP và một repository đơn giản, việc tạo hai interface port riêng có thể chưa đem lại lợi ích đủ lớn. Nếu ứng dụng có HTTP, message consumer, batch job và nhiều adapter lưu trữ, các port có thể giúp lõi độc lập và dễ kiểm thử hơn.

## 6. Khả năng cô lập hạ tầng

Cô lập hạ tầng nghĩa là thay đổi database, HTTP client, broker hoặc framework không buộc phải sửa quy tắc cốt lõi nếu hợp đồng nghiệp vụ vẫn giữ nguyên.

Một số dấu hiệu cho thấy lõi chưa được cô lập tốt:

- Domain import annotation JPA hoặc kiểu dữ liệu riêng của Hibernate.
- Application service tạo trực tiếp WebClient, RestTemplate hoặc SDK nhà cung cấp.
- Logic nghiệp vụ đọc biến môi trường hoặc tự lấy credential.
- Controller trả trực tiếp entity ORM và serialization phụ thuộc quan hệ lazy.
- Unit test phải khởi động Spring context và database chỉ để kiểm tra một quy tắc đơn giản.
- Đổi database buộc sửa nhiều service vì chúng gọi API của driver hoặc ORM trực tiếp.

Hexagonal làm rõ nơi đặt adapter để tập trung các chi tiết này. Layered vẫn có thể cô lập tốt nếu có interface ở ranh giới, DTO phù hợp, dependency direction và quy tắc package rõ ràng.

### Cô lập không đồng nghĩa loại bỏ mọi thư viện

Một ứng dụng không cần cấm mọi thư viện trong mọi tầng. Ví dụ, dùng Spring ở controller hoặc dùng Bean Validation tại biên HTTP là hợp lý. Câu hỏi là liệu thư viện đó có làm cho lõi phụ thuộc vào một chi tiết mà nó không cần biết hay không.

Một số hệ thống chấp nhận domain model có annotation JPA để giảm mapping và độ phức tạp. Đó là lựa chọn có đánh đổi: mô hình miền gắn hơn với persistence nhưng có thể đơn giản hơn cho ứng dụng. Nếu cần thay ORM, chia sẻ domain model giữa nhiều adapter hoặc kiểm thử lõi độc lập, việc tách persistence model có thể đáng giá hơn.

Không có yêu cầu hexagonal phải có domain model thuần Java tuyệt đối. Hãy xác định mức phụ thuộc được chấp nhận và ghi rõ hệ quả.

## 7. Khả năng kiểm thử và thay thế adapter

Cả hai cách tổ chức đều có thể kiểm thử tốt. Khác biệt là hexagonal làm rõ các điểm thay thế bằng port, nên có thể truyền fake hoặc stub trực tiếp vào application service.

Ví dụ test use case mà không cần Spring hoặc database:

~~~java
final class InMemorySaveOrder implements SaveOrderPort {
    private final Map<OrderId, Order> saved = new HashMap<>();

    @Override
    public void save(Order order) {
        saved.put(order.id(), order);
    }

    Optional<Order> find(OrderId id) {
        return Optional.ofNullable(saved.get(id));
    }
}

@Test
void placesOrderThroughTheUseCase() {
    InMemorySaveOrder saveOrder = new InMemorySaveOrder();
    PlaceOrderUseCase useCase = new PlaceOrderService(saveOrder);

    OrderId id = useCase.place(validCommand());

    assertTrue(saveOrder.find(id).isPresent());
}
~~~

Test này chứng minh hành vi use case và sự phối hợp với port thay thế. Nó không chứng minh JPA mapping, SQL hoặc transaction database đúng. Những thuộc tính đó cần integration test với database phù hợp.

Một chiến lược kiểm thử theo ranh giới có thể gồm:

| Phần cần kiểm tra | Test phù hợp |
|---|---|
| Domain entity và policy | Unit test với object thật |
| Application use case | Unit test với fake/stub cho outbound port |
| HTTP inbound adapter | MVC test cho binding, validation và status |
| JPA outbound adapter | Integration test với database tương thích |
| Message adapter | Test serialization và integration với broker khi cần |
| Composition root | Spring context test để xác minh bean wiring |
| Luồng xuyên suốt | End-to-end test cho một số hành trình quan trọng |

Đừng mock chính domain object đang cần kiểm tra. Cũng không dùng fake repository để kết luận SQL, constraint hoặc transaction thật hoạt động đúng.

## 8. Khi nào layered là đủ?

Layered thường là lựa chọn hợp lý khi:

- Ứng dụng có một đường giao tiếp chính và một số ít adapter.
- Nghiệp vụ tương đối đơn giản, thay đổi hạ tầng ít.
- Nhóm nhỏ và cần cấu trúc dễ hiểu, ít ceremony.
- Một interface repository hoặc gateway đơn giản đã đủ tách phần cần thay thế.
- Chi phí thêm inbound/outbound port cho từng thao tác lớn hơn lợi ích thu được.

Một cấu trúc phân tầng tốt vẫn cần giữ các nguyên tắc cơ bản: trách nhiệm rõ, dependency direction dễ hiểu, controller không chứa nghiệp vụ, domain không phụ thuộc presentation, và chi tiết lưu trữ không rò rỉ không cần thiết.

## 9. Khi nào hexagonal đem lại lợi ích rõ hơn?

Hexagonal đáng cân nhắc khi:

- Cùng một ca sử dụng được gọi từ nhiều actor: HTTP, message, batch, CLI hoặc scheduler.
- Ứng dụng có nhiều nguồn dữ liệu hoặc cần thay adapter theo môi trường.
- Hạ tầng thay đổi thường xuyên hoặc có nguy cơ khóa chặt vào nhà cung cấp.
- Muốn kiểm thử application core mà không khởi động framework hoặc database.
- Nghiệp vụ quan trọng và cần bảo vệ khỏi chi tiết giao tiếp, serialization và persistence.
- Có nhiều nhóm phát triển adapter và lõi với hợp đồng cần được kiểm soát.

Ví dụ, một chức năng nhận thanh toán có thể được gọi từ HTTP API, consumer nhận message và tác vụ đối soát. Nếu cả ba đường vào cùng gọi một use case, các adapter có thể dùng chung inbound port. Use case sử dụng outbound port để lưu payment attempt và gọi cổng thanh toán. Điều này giúp quy tắc xử lý thanh toán không bị sao chép theo từng giao thức.

## 10. Những hiểu lầm và chi phí cần tránh

### Nghĩ rằng hexagonal bắt buộc phải có rất nhiều interface

Port chỉ cần xuất hiện ở ranh giới có ý nghĩa. Không cần tạo interface cho mọi class hoặc mọi lời gọi nội bộ. Một abstraction không có nhu cầu thay thế, không bảo vệ hợp đồng và không làm rõ dependency có thể chỉ tăng gián tiếp.

### Nghĩ rằng layered luôn phụ thuộc hạ tầng

Một ứng dụng phân tầng có thể đặt interface repository ở phía application, adapter JPA ở infrastructure và dùng dependency inversion. Khi đó, nó đã áp dụng nhiều ý tưởng của hexagonal dù vẫn tổ chức package theo tầng.

### Nghĩ rằng hexagonal là microservices

Hexagonal mô tả cách lõi kết nối với adapter. Các thành phần có thể chạy trong cùng một tiến trình và một deployment. Nó không yêu cầu HTTP giữa các module hoặc database riêng cho mỗi adapter.

### Để port sao chép API của framework

Một interface trả EntityManager, ResultSet, JpaRepository hoặc DTO riêng của nhà cung cấp không tạo ra ranh giới độc lập. Hợp đồng nên dùng kiểu dữ liệu và thao tác mà consumer thực sự cần.

### Tách adapter nhưng vẫn để lõi biết chi tiết bên ngoài

Nếu application service vẫn kiểm tra mã lỗi HTTP, tên topic Kafka hoặc trạng thái riêng của nhà cung cấp, adapter chưa chuyển đổi đủ trách nhiệm. Hãy ánh xạ giao thức ngoài thành kết quả nội bộ có ý nghĩa.

### Tạo quá nhiều lớp chuyển tiếp

Nếu controller gọi một interface chỉ để gọi một class rồi class đó gọi tiếp một interface khác mà không tạo ranh giới hay hành vi rõ, cấu trúc có thể trở nên khó theo dõi. Giữ số lớp phù hợp với trách nhiệm thực tế.

## 11. Kết hợp layered và hexagonal trong cùng một ứng dụng

Một lựa chọn phổ biến là dùng layered để tổ chức trách nhiệm bên trong mỗi module và dùng hexagonal để kiểm soát các điểm giao tiếp ra/vào. Ví dụ:

~~~text
orders
├── presentation
│   └── OrderController
├── application
│   ├── PlaceOrderService
│   └── port
│       ├── in
│       │   └── PlaceOrderUseCase
│       └── out
│           ├── SaveOrderPort
│           └── InventoryPort
├── domain
│   ├── Order
│   └── OrderPolicy
└── infrastructure
    ├── persistence
    │   └── JpaOrderAdapter
    └── inventory
        └── HttpInventoryAdapter
~~~

Trong cấu trúc này:

- Presentation là inbound adapter nhận HTTP và gọi inbound port.
- Application điều phối use case và sử dụng outbound port.
- Domain chứa quy tắc nghiệp vụ.
- Infrastructure triển khai outbound port bằng JPA hoặc HTTP.
- Composition root của Spring nối các implementation phù hợp.

Đây là cách kết hợp, không phải một khuôn mẫu bắt buộc. Có thể đặt inbound port trong application package, còn domain chỉ chứa mô hình nghiệp vụ. Với ứng dụng đơn giản hơn, controller có thể gọi trực tiếp application service và service phụ thuộc một repository interface mà không cần tạo nhiều package port riêng.

## 12. Cách tiến hóa từ layered sang hexagonal khi có nhu cầu

Không cần viết lại ứng dụng để áp dụng hexagonal. Có thể tiến hóa từng ranh giới có vấn đề:

1. Xác định một dependency đang làm application hoặc domain phụ thuộc vào chi tiết hạ tầng, ví dụ service gọi trực tiếp SDK thanh toán.
2. Viết rõ khả năng mà use case cần, như authorize payment hoặc save payment attempt.
3. Định nghĩa port bằng kiểu dữ liệu nội bộ, không đưa SDK hoặc kiểu framework vào chữ ký.
4. Tạo adapter hiện thực port và chuyển đổi request/response của nhà cung cấp.
5. Đưa việc chọn adapter về composition root qua Spring configuration hoặc dependency injection.
6. Viết unit test cho use case bằng fake port; viết integration test riêng cho adapter.
7. Thêm quy tắc kiến trúc để ngăn lõi import package adapter hoặc thư viện không được phép.
8. Lặp lại với những ranh giới khác khi lợi ích thực tế xuất hiện.

Hãy bắt đầu từ dependency có biến động lớn, khó kiểm thử hoặc đang làm lộ chi tiết bên ngoài. Không cần chuyển mọi repository, clock hoặc helper thành port ngay lập tức. Sau mỗi bước, kiểm tra xem thay đổi nhà cung cấp hoặc cách giao tiếp có thực sự được giới hạn trong adapter hay không.

## 13. Quy trình lựa chọn theo nhu cầu

Khi lựa chọn giữa layered, hexagonal hoặc cách kết hợp, hãy trả lời:

1. Ứng dụng có bao nhiêu loại actor hoặc giao thức cần gọi cùng một hành vi?
2. Có bao nhiêu nguồn dữ liệu và dịch vụ ngoài, và chúng thay đổi thường xuyên đến mức nào?
3. Quy tắc nghiệp vụ có cần được kiểm thử độc lập với Spring, database và mạng không?
4. Những chi tiết hạ tầng nào hiện đang rò rỉ vào application hoặc domain?
5. Interface hiện có đã tạo được hợp đồng ổn định chưa, hay chỉ bọc lại một class framework?
6. Nhóm có đủ lý do và năng lực để duy trì thêm port, adapter và cấu hình lắp ráp không?
7. Có thể áp dụng ranh giới hexagonal cho một vài điểm biến động trước khi mở rộng không?

| Tình huống | Hướng lựa chọn có thể phù hợp |
|---|---|
| CRUD nhỏ, một database, một HTTP API | Layered đơn giản |
| Layered đã có repository interface và adapter độc lập | Tiếp tục layered, bổ sung quy tắc dependency nếu cần |
| Nhiều loại inbound adapter cùng gọi một use case | Bổ sung inbound port |
| Nhiều nguồn dữ liệu hoặc nhà cung cấp có thể thay thế | Bổ sung outbound port và adapter |
| Lõi nghiệp vụ cần kiểm thử độc lập với framework | Tổ chức application/domain core theo hexagonal |
| Hệ thống lớn nhưng vẫn muốn một deployment | Kết hợp modular monolith, layered bên trong module và ports/adapters tại ranh giới |

Không có số lượng tầng, port hoặc adapter bắt buộc. Quyết định nên dựa trên rủi ro coupling, mức biến động của hạ tầng, yêu cầu kiểm thử và chi phí bảo trì.

## 14. Tự đánh giá ranh giới kiến trúc

Trước khi kết thúc review một module, hãy tự hỏi:

- Tầng nào sở hữu hành vi và quy tắc đang được thực hiện?
- Lõi có import lớp controller, ORM, driver hoặc SDK nhà cung cấp không?
- Adapter có thực sự chuyển đổi giao thức ngoài thành hợp đồng nội bộ không?
- Consumer có phụ thuộc vào API ổn định hay cấu trúc lưu trữ cụ thể?
- Có thể thay database adapter hoặc HTTP adapter mà không sửa quy tắc nghiệp vụ không?
- Test nào chứng minh hành vi lõi, test nào chứng minh tích hợp hạ tầng?
- Abstraction mới có giải quyết một nhu cầu thực tế hay chỉ tăng số lượng interface?

Layered giúp phân chia trách nhiệm theo tầng; hexagonal giúp bảo vệ lõi bằng các port và adapter ở ranh giới bên ngoài. Một ứng dụng có thể dùng riêng từng cách hoặc kết hợp chúng. Hãy chọn mức cô lập tương xứng với nhu cầu: giữ cấu trúc đơn giản khi phụ thuộc ổn định và ít biến động, tăng cường port/adapter khi nhiều actor, hạ tầng hoặc yêu cầu kiểm thử làm cho ranh giới trở nên quan trọng. Điều cần bảo vệ là hướng phụ thuộc và quyền sở hữu hợp đồng, không phải việc tuân theo một sơ đồ cố định.
