# Triển khai nhiều tầng logic trong một tiến trình hoặc monolith

Bài học này thuộc module **SOFTWARE_DESIGN_ARCHITECTURE_ARCHITECTURAL_PATTERN_LAYERED** — **Học tổ chức phần mềm theo kiến trúc phân tầng**, trong chương **Hiệu năng và triển khai**. Một ứng dụng có thể chia mã nguồn thành presentation, application, domain và data access nhưng vẫn đóng gói, triển khai và chạy như một ứng dụng duy nhất. Các layer khi đó là ranh giới logic bên trong chương trình; chúng không bắt buộc phải trở thành các máy chủ, container hay dịch vụ độc lập.

Kiểu triển khai này thường được gọi là **monolith** hoặc, khi các module nội bộ được tổ chức và bảo vệ ranh giới rõ ràng, là **modular monolith**. Hiểu đúng cách triển khai giúp nhóm giữ được cấu trúc bên trong, tận dụng lời gọi trong cùng tiến trình và đánh giá chính xác các đánh đổi về phát hành, mở rộng, độ tin cậy và vận hành.

## 1. Layer logic không đồng nghĩa với tier triển khai

**Layer logic** là cách chia trách nhiệm trong mã nguồn. Ví dụ, controller thuộc presentation, application service điều phối use case, domain chứa quy tắc nghiệp vụ và repository adapter thực hiện truy cập dữ liệu.

**Tier triển khai (deployment tier)** là ranh giới thực thi hoặc hạ tầng: tiến trình, máy ảo, container, máy chủ hay nhóm dịch vụ được triển khai riêng. Một tier có thể chứa nhiều layer logic; ngược lại, một layer logic cũng có thể được triển khai trên nhiều instance khi hệ thống được mở rộng.

Ví dụ, ứng dụng Spring Boot có thể chứa các package sau:

~~~text
com.example.shop
├── presentation
│   └── web
├── application
│   └── order
├── domain
│   └── order
└── infrastructure
    └── persistence
~~~

Các package này mô tả trách nhiệm trong mã nguồn. Khi build, ứng dụng có thể được đóng gói thành một file JAR thực thi và chạy trong một JVM. Controller gọi application service bằng lời gọi phương thức Java; application gọi domain và repository thông qua object được inject. Các layer không cần giao tiếp với nhau bằng HTTP chỉ vì chúng được chia thành các package riêng.

**Sơ đồ logic bên trong ứng dụng**

~~~mermaid
flowchart TD
    P[Presentation] --> A[Application]
    A --> D[Domain]
    A --> R[Repository port]
    I[Persistence adapter] --> R
    I --> DB[(Database)]
~~~

**Sơ đồ triển khai một monolith**

~~~mermaid
flowchart TB
    U[Browser / Client] -->|HTTP| APP
    subgraph APP["Một ứng dụng / một tiến trình JVM"]
        P[Presentation]
        A[Application]
        D[Domain]
        I[Infrastructure]
        P --> A
        A --> D
        A --> I
    end
    I -->|JDBC / protocol| DB[(Database)]
~~~

Trong sơ đồ triển khai, các layer cùng nằm trong một tiến trình ứng dụng. Database vẫn có thể là một hệ thống riêng bên ngoài. Vì vậy, “monolith” không có nghĩa toàn bộ hệ thống, kể cả database, phải nằm trong cùng một process.

## 2. Monolith vẫn có thể được phân tầng rõ ràng

Monolith mô tả cách đóng gói và triển khai ứng dụng. Layering mô tả cách tổ chức trách nhiệm và phụ thuộc bên trong. Hai khái niệm này bổ sung cho nhau:

- Một monolith có thể có ranh giới layer rõ, module nội bộ độc lập về trách nhiệm và hợp đồng.
- Một monolith cũng có thể trở thành khối mã khó bảo trì nếu mọi package gọi lẫn nhau và quy tắc nghiệp vụ bị phân tán.
- Chia thành nhiều service không tự động tạo ra kiến trúc tốt; nếu ranh giới không rõ, hệ thống chỉ chuyển sự rối rắm thành các lời gọi mạng và quy trình vận hành phức tạp hơn.

Một **modular monolith** thường có một đơn vị triển khai chính nhưng chia thành các module nghiệp vụ hoặc kỹ thuật có API nội bộ rõ ràng. Mỗi module kiểm soát dữ liệu và hành vi mà nó sở hữu. Các module có thể được đóng gói thành nhiều module build hoặc package, nhưng vẫn được lắp ráp vào cùng ứng dụng khi chạy.

Ví dụ một cửa hàng trực tuyến có thể chia module **orders**, **catalog**, **inventory** và **payments**. Module **orders** cung cấp use case đặt hàng; module **catalog** cung cấp cách tra cứu sản phẩm; module **inventory** quản lý tồn kho. Chúng có thể nằm trong cùng một JVM nhưng không nên truy cập tùy tiện vào bảng hoặc lớp nội bộ của nhau.

### Tổ chức package theo layer hoặc theo năng lực

Có hai cách sắp xếp phổ biến:

~~~text
shop/
├── presentation/
├── application/
├── domain/
└── infrastructure/
~~~

hoặc:

~~~text
shop/
├── orders/
│   ├── presentation/
│   ├── application/
│   ├── domain/
│   └── infrastructure/
├── catalog/
│   ├── application/
│   ├── domain/
│   └── infrastructure/
└── inventory/
    ├── application/
    ├── domain/
    └── infrastructure/
~~~

Tổ chức theo layer có thể dễ hiểu trong ứng dụng nhỏ, nhưng package của một chức năng bị trải rộng ở nhiều nơi. Tổ chức theo module nghiệp vụ giúp giữ các phần liên quan gần nhau và làm rõ quyền sở hữu. Một dự án có thể kết hợp cả hai: module nghiệp vụ là ranh giới lớn, bên trong mỗi module tiếp tục chia layer.

Không có một cấu trúc folder duy nhất phù hợp cho mọi dự án. Hãy chọn cách mà nhóm có thể hiểu, kiểm tra và duy trì; sau đó thực thi quy tắc phụ thuộc bằng visibility của package, module build hoặc công cụ kiểm tra kiến trúc.

## 3. Luồng xử lý trong cùng một tiến trình

Giả sử khách hàng gửi yêu cầu tạo đơn hàng. Một ứng dụng Spring Boot đơn tiến trình có thể xử lý như sau:

~~~java
@RestController
@RequestMapping("/orders")
public class OrderController {
    private final PlaceOrderUseCase placeOrder;

    public OrderController(PlaceOrderUseCase placeOrder) {
        this.placeOrder = placeOrder;
    }

    @PostMapping
    public ResponseEntity<OrderResponse> place(
            @RequestBody PlaceOrderRequest request) {
        PlaceOrderResult result = placeOrder.handle(
                new PlaceOrderCommand(
                        request.customerId(),
                        request.lines()));
        return ResponseEntity.status(201)
                .body(new OrderResponse(result.orderId()));
    }
}
~~~

Application service điều phối use case:

~~~java
@Service
public class PlaceOrderService implements PlaceOrderUseCase {
    private final OrderRepository orders;

    public PlaceOrderService(OrderRepository orders) {
        this.orders = orders;
    }

    @Override
    @Transactional
    public PlaceOrderResult handle(PlaceOrderCommand command) {
        Order order = Order.place(
                new CustomerId(command.customerId()),
                command.lines().stream()
                        .map(line -> OrderLine.of(
                                new ProductId(line.productId()),
                                line.quantity()))
                        .toList());

        OrderId savedId = orders.save(order);
        return new PlaceOrderResult(savedId.value());
    }
}
~~~

Trong ví dụ này, controller và service là các object trong cùng JVM. Controller gọi phương thức handle qua interface; Spring inject implementation PlaceOrderService. Service gọi domain và repository qua các object đã được cung cấp. Không có request HTTP nội bộ giữa presentation và application.

Luồng runtime khái quát:

~~~mermaid
sequenceDiagram
    actor Client as HTTP Client
    participant C as OrderController
    participant S as PlaceOrderService
    participant D as Order domain
    participant R as JpaOrderRepository
    participant DB as Database

    Client->>C: POST /orders
    C->>S: handle(command)
    S->>D: Order.place(...)
    D-->>S: Order
    S->>R: save(order)
    R->>DB: INSERT
    DB-->>R: Kết quả
    R-->>S: OrderId
    S-->>C: PlaceOrderResult
    C-->>Client: HTTP 201
~~~

Các layer có thể được kiểm tra và thay đổi độc lập về mặt mã nguồn, nhưng chúng chia sẻ tiến trình, heap, cấu hình và vòng đời triển khai. Một lỗi nghiêm trọng trong bất kỳ layer nào cũng có thể làm hỏng hoặc dừng toàn bộ tiến trình.

## 4. Đóng gói và triển khai một ứng dụng

Một quy trình triển khai đơn giản cho monolith thường gồm:

1. Build các module mã nguồn thành một ứng dụng có thể chạy.
2. Đóng gói dependency cần thiết vào executable JAR hoặc image container.
3. Cung cấp cấu hình môi trường như URL database, thông tin xác thực, giới hạn connection pool và logging.
4. Khởi động ứng dụng, kiểm tra readiness và kết nối các resource cần thiết.
5. Đưa instance vào nhận traffic; khi dừng, ngừng nhận request mới và hoàn tất hoặc giới hạn thời gian xử lý request đang chạy.

Ví dụ Dockerfile tối giản cho ứng dụng đã build:

~~~dockerfile
FROM eclipse-temurin:21-jre
WORKDIR /app
COPY build/libs/shop-app.jar app.jar
EXPOSE 8080
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
~~~

Container này chạy một artifact chứa nhiều layer logic. Khi triển khai, nhóm thay phiên bản artifact để cập nhật toàn bộ ứng dụng. Các cấu hình môi trường và bí mật nên được cung cấp qua cơ chế quản lý cấu hình/secret của môi trường chạy, không đóng cứng vào source code hoặc image.

### Một artifact có thể chạy nhiều instance

Monolith không đồng nghĩa ứng dụng chỉ có một bản chạy. Có thể triển khai nhiều replica của cùng artifact phía sau load balancer:

~~~mermaid
flowchart TD
    C[Clients] --> LB[Load balancer]
    LB --> A1[Shop application instance 1]
    LB --> A2[Shop application instance 2]
    LB --> A3[Shop application instance 3]
    A1 --> DB[(Shared database)]
    A2 --> DB
    A3 --> DB
~~~

Mỗi instance chứa cùng các layer và thường chạy cùng phiên bản ứng dụng trong một đợt rollout. Đây là mở rộng ngang của monolith. Nó khác với việc mở rộng riêng application layer hoặc data access layer thành các dịch vụ triển khai độc lập.

Nếu ứng dụng giữ session hoặc trạng thái quy trình trong bộ nhớ cục bộ, các request tiếp theo có thể được chuyển sang instance khác và không thấy trạng thái cũ. Có thể dùng session store dùng chung, token stateless hoặc cơ chế định tuyến phù hợp. Với tác vụ nền, cần bảo đảm nhiều replica không cùng xử lý một công việc ngoài dự kiến; dùng queue, distributed lock hoặc cơ chế claim công việc có tính nguyên tử khi thích hợp.

## 5. Lợi ích hiệu năng của lời gọi trong cùng tiến trình

Khi các layer ở cùng tiến trình, lời gọi giữa chúng thường là lời gọi phương thức trong bộ nhớ. So với giao tiếp qua mạng, cách này tránh được nhiều chi phí:

- Không cần mở kết nối mạng giữa các layer nội bộ.
- Không phải serialize và deserialize payload qua HTTP hoặc message protocol cho mỗi lời gọi.
- Không phải xử lý timeout mạng, retry mạng và discovery giữa các layer chỉ nằm trong cùng ứng dụng.
- Có thể truyền object hoặc value object trong bộ nhớ theo hợp đồng nội bộ.
- Một transaction có thể bao phủ nhiều thao tác nếu chúng cùng tham gia một transaction manager và resource phù hợp.

Điều đó thường làm giảm latency và đơn giản hóa luồng điều khiển. Tuy nhiên, lời gọi trong cùng JVM không miễn phí. Một truy vấn database chậm, thuật toán tốn CPU, khóa tranh chấp hoặc xử lý đồng bộ quá lâu vẫn có thể làm request chậm. Chia layer cũng không tự làm ứng dụng nhanh hơn; nó chủ yếu giúp tổ chức trách nhiệm. Hiệu năng cần được đo bằng profiling, tracing, metrics và kiểm tra tải.

### Tránh thêm lớp chuyển tiếp không có giá trị

Mỗi abstraction hoặc mapping có thể hữu ích để bảo vệ ranh giới, nhưng quá nhiều lớp chỉ chuyển tiếp dữ liệu mà không tạo hợp đồng hay chính sách rõ ràng có thể làm luồng xử lý khó lần theo. Không cần tạo một service, mapper hoặc wrapper cho mọi phương thức một cách máy móc. Hãy thêm ranh giới khi nó biểu đạt trách nhiệm, quy tắc hoặc khả năng thay đổi thực sự.

## 6. Transaction và tính nhất quán trong monolith

Một ưu điểm thực tế của monolith là nhiều thao tác nghiệp vụ có thể dùng chung database và transaction manager. Ví dụ, tạo đơn và các dòng đơn có thể được commit cùng nhau:

~~~java
@Transactional
public OrderId place(PlaceOrderCommand command) {
    Order order = createDomainOrder(command);
    orderRepository.save(order);
    auditRepository.append(OrderCreated.from(order));
    return order.id();
}
~~~

Nếu các repository tham gia cùng một transaction trên cùng resource, lỗi trong quá trình xử lý có thể khiến các thay đổi rollback như một đơn vị. Điều này giúp một số workflow đơn giản hơn so với việc phối hợp nhiều database độc lập.

Tuy nhiên, **cùng một tiến trình không tự động đồng nghĩa cùng một transaction**. Nếu các module dùng database khác nhau, transaction manager khác nhau, gọi HTTP ra ngoài hoặc gửi message đến broker, những tác động đó không tự được rollback cùng transaction của ứng dụng. Cần xem resource nào thực sự tham gia transaction và lựa chọn cơ chế như outbox hoặc quy trình bù trừ nếu workflow vượt qua ranh giới đó.

Một monolith cũng cần tránh để transaction mở quá lâu. Không nên giữ transaction database trong lúc chờ một API bên ngoài nếu có thể tách bước đọc/tra cứu ra trước hoặc dùng workflow bất đồng bộ. Transaction dài làm tăng thời gian giữ lock và có thể giảm throughput.

## 7. Mở rộng và giới hạn của một đơn vị triển khai

Monolith thường được mở rộng ngang bằng cách chạy thêm replica của toàn ứng dụng. Cách này đơn giản khi tải tăng tương đối đồng đều và mọi instance cần cùng một tập chức năng. Nhưng nếu chỉ một chức năng tiêu thụ nhiều CPU hoặc bộ nhớ, các replica vẫn phải mang theo toàn bộ ứng dụng và thường mở rộng các chức năng khác cùng lúc.

Các giới hạn thường gặp:

- **Mở rộng theo toàn ứng dụng:** không thể dễ dàng tăng riêng số instance của một layer logic.
- **Phát hành cùng nhau:** thay đổi một module thường dẫn đến build và triển khai lại artifact chung; cần quản lý tương thích giữa các module.
- **Ảnh hưởng chung:** lỗi rò rỉ bộ nhớ, cạn thread pool hoặc lỗi cấu hình có thể tác động mọi chức năng trong process.
- **Tài nguyên dùng chung:** thread pool, connection pool, heap và CPU có thể bị một chức năng chiếm dụng.
- **Vòng đời chung:** module khó có thể dùng runtime, phiên bản framework hoặc lịch phát hành hoàn toàn khác với ứng dụng chính.

Có thể giảm một số rủi ro bằng cách tách pool cho workload khác nhau, giới hạn concurrency, đặt timeout, bulkhead, rate limit và theo dõi tài nguyên theo chức năng. Những cơ chế này giúp cô lập tải ở mức logic hoặc tài nguyên trong cùng tiến trình, nhưng không tạo ra ranh giới lỗi mạnh như process độc lập.

## 8. Khi nào nên giữ monolith, khi nào cân nhắc tách service?

Monolith có thể là lựa chọn phù hợp khi:

- Sản phẩm còn nhỏ hoặc nhóm phát triển còn ít người.
- Các chức năng thay đổi cùng nhịp và thường cần phối hợp transaction trên cùng dữ liệu.
- Việc triển khai một artifact là đủ nhanh và đơn giản.
- Tải của các chức năng chưa cần mở rộng độc lập.
- Nhóm muốn giảm chi phí vận hành mạng, discovery, observability và xử lý lỗi phân tán.

Cân nhắc tách một module thành service riêng khi có nhu cầu thực tế như:

- Một năng lực cần mở rộng độc lập rõ rệt.
- Một module cần lịch phát hành hoặc mức độ sẵn sàng khác biệt.
- Có ranh giới dữ liệu và hợp đồng ổn định, ít phải truy cập trực tiếp dữ liệu nội bộ của module khác.
- Một nhóm có thể chịu trách nhiệm đầy đủ cho vòng đời, triển khai và vận hành service đó.
- Cần cô lập tài nguyên, lỗi hoặc yêu cầu bảo mật ở mức process/deployment.

Tách service đem lại tính độc lập triển khai và mở rộng, nhưng cũng thêm chi phí giao tiếp mạng, quản lý contract, versioning, retry, timeout, observability, bảo mật giữa service và nhất quán dữ liệu phân tán. Không nên tách chỉ vì package đã có tên layer hoặc vì muốn mỗi layer nằm trên một máy chủ riêng.

Một hướng tiến hóa thận trọng là bắt đầu bằng modular monolith: giữ module nội bộ có API và quyền sở hữu dữ liệu rõ; đo tải và tần suất thay đổi; chỉ tách module khi lợi ích vận hành và tổ chức lớn hơn chi phí phân tán.

## 9. Kiểm tra ranh giới trong một monolith

Triển khai chung không phải lý do để bỏ qua kiểm soát kiến trúc. Một số cách giữ ranh giới:

1. Dùng package hoặc module riêng cho từng layer/module nghiệp vụ.
2. Giới hạn visibility của lớp và constructor để tránh truy cập implementation nội bộ.
3. Để module khác gọi qua public API hoặc application port đã định nghĩa.
4. Tránh truy cập trực tiếp repository hoặc bảng dữ liệu thuộc module khác nếu không có hợp đồng rõ ràng.
5. Dùng ArchUnit hoặc test kiến trúc để phát hiện dependency sai chiều.
6. Có integration test cho wiring, transaction, persistence và cấu hình thực tế.

Ví dụ, có thể quy định domain không phụ thuộc Spring Web và application không import lớp JPA adapter. Một test kiến trúc có thể kiểm tra quy tắc này tự động. Các quy tắc nên phản ánh thiết kế thật của dự án; không cần áp đặt một bộ layer cố định cho mọi module.

## 10. Vận hành và triển khai an toàn

Vì toàn ứng dụng được triển khai cùng nhau, cần chú ý các vấn đề vận hành ở cấp process:

- **Health và readiness:** phân biệt process đã khởi động với ứng dụng đã sẵn sàng nhận traffic, đặc biệt khi cần kết nối database hoặc hệ thống thiết yếu.
- **Graceful shutdown:** ngừng nhận request mới, cho request đang chạy thời gian hoàn tất hợp lý và xử lý tác vụ nền đang hoạt động.
- **Database migration:** thay đổi schema theo trình tự tương thích với phiên bản ứng dụng trong giai đoạn rollout; tránh triển khai code đòi hỏi cột mới trước khi schema sẵn sàng.
- **Logging và tracing:** gắn request/correlation ID để theo dõi qua các layer; không ghi thông tin bí mật.
- **Giới hạn tài nguyên:** cấu hình thread pool, connection pool, heap, timeout và concurrency theo tải thực tế.
- **Triển khai nhiều replica:** bảo đảm scheduler, consumer và tác vụ định kỳ có cơ chế phối hợp để tránh chạy trùng không mong muốn.
- **Rollback phiên bản:** giữ tương thích schema và message contract đủ lâu để có thể quay về phiên bản trước khi cần.

Khi deploy một phiên bản mới, không phải mọi thay đổi database đều có thể rollback an toàn cùng với artifact. Với thay đổi phá vỡ tương thích, có thể dùng quy trình expand-and-contract: thêm cấu trúc mới tương thích, triển khai code chuyển tiếp, chuyển dữ liệu, rồi mới loại bỏ cấu trúc cũ khi không còn phiên bản nào sử dụng.

## 11. Checklist thiết kế và triển khai

Trước khi triển khai một ứng dụng phân tầng như monolith, hãy kiểm tra:

- Các layer logic có trách nhiệm và hướng phụ thuộc rõ ràng không?
- Package hoặc module có bảo vệ được ranh giới dù cùng một JVM không?
- Các layer giao tiếp bằng lời gọi nội bộ hay đang tạo network hop không cần thiết?
- Artifact triển khai có chứa đúng module và cấu hình runtime cần thiết không?
- Transaction có thực sự dùng chung resource/transaction manager như thiết kế giả định không?
- Thread pool, connection pool, timeout và giới hạn concurrency có phù hợp không?
- Nhiều replica có xử lý session, scheduled job và message consumer an toàn không?
- Health check, graceful shutdown, migration và rollback đã được tính đến chưa?
- Có số liệu về latency, throughput, lỗi và mức sử dụng tài nguyên để quyết định mở rộng không?
- Có lý do cụ thể, dựa trên nhu cầu vận hành, để tách một module thành service riêng không?

Triển khai nhiều layer logic trong một tiến trình cho phép ứng dụng giữ cấu trúc phân tầng mà vẫn có một artifact và vòng đời triển khai thống nhất. Lợi ích là lời gọi nội bộ đơn giản, độ trễ thấp hơn so với giao tiếp mạng giữa các layer và khả năng dùng transaction cục bộ khi các resource phù hợp. Đổi lại, các module chia sẻ tài nguyên và phát hành cùng nhau, nên cần bảo vệ ranh giới nội bộ, kiểm soát tải và vận hành process cẩn thận. Hãy đánh giá monolith theo quy mô, nhịp thay đổi và nhu cầu cô lập thực tế; số lượng layer logic không quyết định số lượng service phải triển khai.
