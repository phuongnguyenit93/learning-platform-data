# Tách business logic khỏi transport

## 1. Vấn đề: một nghiệp vụ, nhiều đường nhận thông điệp

Giả sử hệ thống đơn hàng nhận cùng một yêu cầu từ HTTP API, message broker và tác vụ nhập dữ liệu theo lịch. Cả ba đường vào đều cần kiểm tra đơn hàng, áp dụng quy tắc hạn mức, lưu trạng thái và phát kết quả. Nếu mỗi controller hoặc listener tự cài đặt toàn bộ quy tắc đó, ba phiên bản nghiệp vụ sẽ dần khác nhau:

- HTTP controller trả lỗi khi số lượng không hợp lệ, trong khi consumer Kafka vẫn lưu đơn.
- Listener có retry riêng khiến một đơn hàng có thể được ghi hai lần.
- Khi thay JSON bằng Avro hoặc đổi tên topic, nhà phát triển phải sửa cả lớp nghiệp vụ.
- Unit test muốn kiểm tra cách tính hạn mức phải khởi động web server hoặc broker.

Trong chương **Pipes and filters** của module **SPRING_INTEGRATION_PATTERN**, giải pháp là biến các bước xử lý thành những thành phần có đầu vào, đầu ra rõ ràng, nối với nhau qua **message channel**. Những bước hiểu HTTP, Kafka, AMQP hay định dạng tệp nằm ở **ranh giới transport**; các bước hiểu đơn hàng, tồn kho và quy tắc nghiệp vụ nằm ở **lõi ứng dụng**.

Mục tiêu không chỉ là chia nhỏ hàm. Sau bài này, bạn cần biết cách:

1. Xác định chính xác phần nào là business logic và phần nào là transport.
2. Thiết kế command/result và cổng gọi nghiệp vụ độc lập với HTTP hoặc broker.
3. Dùng **Gateway, Filter, Transformer, Router** và handler Spring Integration để kết nối các lớp mà không đưa API của transport vào domain.
4. Giữ correlation, idempotency, xử lý retry và error channel ở đúng ranh giới trách nhiệm.
5. Kiểm thử nghiệp vụ mà không cần broker, rồi kiểm thử adapter/flow tại các ranh giới tích hợp.

## 2. Pipes and Filters kết hợp Ports and Adapters

Hai cách tổ chức sau bổ sung cho nhau:

| Góc nhìn | Câu hỏi chính | Cách áp dụng |
|---|---|---|
| **Pipes and Filters** | Thông điệp đi qua những bước nào? | Mỗi filter/transformer/handler có đầu vào và đầu ra; channel nối các bước |
| **Ports and Adapters** | Lớp nào được phép biết framework hoặc giao thức? | Business service có cổng Java thuần; HTTP/Kafka/JDBC adapter gọi cổng đó |

**Pipe** trong Spring Integration thường là `MessageChannel`; **filter** ở nghĩa kiến trúc là bước xử lý nói chung, còn **Filter EIP** cụ thể là endpoint quyết định message được đi tiếp hay bị loại. Hai nghĩa này không nên nhầm lẫn. Một pipeline có thể gồm Transformer, Router, Service Activator và Aggregator, không bắt buộc mọi bước đều là `Filter` EIP.

~~~mermaid
flowchart LR
    subgraph Outside["Transport / hệ thống ngoài"]
      H["HTTP JSON"]
      K["Broker event"]
      S["Scheduled import"]
    end
    subgraph Boundary["Adapters và integration"]
      AH["HTTP adapter"]
      AK["Broker adapter"]
      AS["File/scheduled adapter"]
      G["Gateway → orders.in"]
      V["Filter: hợp đồng đầu vào"]
      T["Transformer: DTO → command"]
    end
    subgraph Core["Business core"]
      U["OrderUseCase"]
      P["RepositoryPort"]
    end
    H --> AH
    K --> AK
    S --> AS
    AH --> G
    AK --> G
    AS --> G
    G --> V --> T --> U --> P
    U --> O["Result / event nội bộ"]
    O --> OUT["Output adapters"]
~~~

Các transport adapter chuyển dữ liệu sang **hợp đồng ứng dụng chung**. Integration flow chịu trách nhiệm phối hợp và định tuyến. Business core không cần biết adapter nào đã gọi nó, thread nào đang chạy hay dữ liệu ban đầu được mã hóa bằng JSON hay byte array.

**Quy tắc phụ thuộc:** lớp domain/application không import `HttpServletRequest`, `ResponseEntity`, `ConsumerRecord`, `Message<?>`, `MessageHeaders`, `@KafkaListener` hoặc class channel của Spring Integration chỉ để thực hiện quy tắc nghiệp vụ. Adapter và flow có thể phụ thuộc vào core; core không phụ thuộc ngược vào chúng.

## 3. Phân loại trách nhiệm trước khi viết code

Ví dụ yêu cầu “đặt đơn hàng với số lượng dương, không vượt hạn mức; nhận qua HTTP hoặc broker” có thể phân chia như sau:

| Công việc | Nơi phù hợp | Lý do |
|---|---|---|
| Giải mã JSON/Avro, đọc header HTTP hoặc Kafka | Transport adapter | Phụ thuộc định dạng và giao thức |
| Kiểm tra content type, kích thước, trường bắt buộc theo wire schema | Inbound adapter/validation boundary | Chặn dữ liệu không thể hiểu được từ ngoài |
| Đổi DTO phiên bản 1 sang command chuẩn | Transformer/mapper | Chuyển hợp đồng ngoài thành kiểu ứng dụng |
| Kiểm tra số lượng dương, giới hạn sản phẩm, trạng thái khách hàng | Business use case | Quy tắc phải đúng với mọi transport |
| Chọn kênh xử lý theo quốc gia hoặc loại đơn | Router EIP, theo quyết định nghiệp vụ đã chuẩn hóa | Dễ quan sát nhánh và thay đổi hạ tầng |
| Lưu đơn hàng | Business service gọi `OrderRepositoryPort` | Core định nghĩa nhu cầu, adapter cung cấp cách lưu |
| HTTP status 201/400/409, response headers | HTTP adapter | Ý nghĩa thuộc hợp đồng HTTP |
| Ack/nack, retry broker, DLQ, partition, serialization | Broker adapter và cấu hình vận hành | Phụ thuộc cơ chế delivery |
| Correlation, trace, routing metadata qua channel | Integration boundary | Để theo dõi message xuyên các endpoint |
| Idempotency của thao tác tạo đơn | Application/business + storage thích hợp | Một message có thể được giao lại từ nhiều nguồn |

Có những trách nhiệm nằm ở cả hai bên nhưng **khác mục đích**. Ví dụ adapter kiểm tra trường `quantity` có thể parse được thành số nguyên, còn use case kiểm tra số lượng đó có phù hợp với quy tắc bán hàng hay không. Kiểm tra sơ bộ ở Filter giúp loại message không hợp đồng; use case vẫn phải bảo vệ invariant ngay cả khi bị gọi trực tiếp.

## 4. Đặt hợp đồng ổn định ở ranh giới ứng dụng

Thiết kế ba loại dữ liệu:

1. **Transport DTO:** mô tả cấu trúc bên ngoài, có thể thay đổi theo version hoặc giao thức.
2. **Application command:** mô tả ý định nghiệp vụ đã chuẩn hóa, không nhắc tới HTTP/Kafka.
3. **Business result:** trả kết quả nghiệp vụ; adapter quyết định diễn đạt thành response hay event.

~~~java
// DTO do API/event contract v1 quy định.
public record IncomingOrderV1(
    String requestId,
    String itemCode,
    int units,
    String market
) {}

// Kiểu dùng trong application core.
public record PlaceOrder(
    String orderId,
    String sku,
    int quantity,
    String region
) {}

public record OrderReceipt(
    String orderId,
    String status
) {}

public interface PlaceOrderUseCase {
    OrderReceipt place(PlaceOrder command);
}
~~~

Những record này chỉ chứa dữ liệu. Chúng không cần annotation HTTP, Kafka hoặc Spring Integration. `IncomingOrderV1` thuộc hợp đồng đầu vào và có thể sống trong module adapter; `PlaceOrder`, `OrderReceipt` và `PlaceOrderUseCase` thuộc hợp đồng lõi.

Giữ **khóa nghiệp vụ** và **định danh sự kiện** tách biệt. `orderId` xác định đơn; `eventId` xác định một lần phát sự kiện; `correlationId` nối các bước thuộc cùng một quy trình. Chúng có thể liên quan nhưng không mặc nhiên hoán đổi được. Khi cần chống trùng, use case/adapter lưu trữ phải dùng khóa được xác định trong hợp đồng nghiệp vụ.

### Business service không biết transport

~~~java
public final class DefaultPlaceOrderUseCase implements PlaceOrderUseCase {

    private final OrderRepositoryPort repository;

    public DefaultPlaceOrderUseCase(OrderRepositoryPort repository) {
        this.repository = repository;
    }

    @Override
    public OrderReceipt place(PlaceOrder command) {
        if (command == null || command.orderId() == null
                || command.orderId().isBlank()
                || command.sku() == null || command.sku().isBlank()
                || command.quantity() <= 0) {
            throw new InvalidOrderException("Invalid order command");
        }
        // Hàm này minh họa invariant nghiệp vụ:
        // Quy tắc kiểm tra không phụ thuộc nguồn HTTP hay broker.
        return repository.save(command);
    }
}

public interface OrderRepositoryPort {
    OrderReceipt save(PlaceOrder command);
}

public final class InvalidOrderException extends RuntimeException {
    public InvalidOrderException(String reason) {
        super(reason);
    }
}
~~~

`OrderRepositoryPort` là cổng đi ra. Adapter có thể cài đặt bằng JDBC/JPA hoặc một hệ thống khác mà không sửa `DefaultPlaceOrderUseCase`. Trong thực tế cần thêm transaction, điều kiện unique và chính sách idempotency cho thao tác ghi; ví dụ này chỉ thể hiện ranh giới trách nhiệm.

## 5. Transformer: một nơi đổi từ hợp đồng ngoài sang command

Một mapper cụ thể giúp tránh lặp lại việc chuẩn hóa ở controller và broker listener:

~~~java
public final class OrderMapper {
    public PlaceOrder toCommand(IncomingOrderV1 input) {
        return new PlaceOrder(
            input.requestId(),
            input.itemCode().trim(),
            input.units(),
            input.market().trim().toUpperCase(Locale.ROOT)
        );
    }
}
~~~

Đầu vào `IncomingOrderV1("O-105", " SKU-7 ", 2, " vn ")` được đổi thành `PlaceOrder("O-105", "SKU-7", 2, "VN")`. Việc đổi tên trường, trim và chuẩn hóa mã vùng là nhiệm vụ của **Transformer**; kiểm tra số lượng có được phép hay không vẫn thuộc business use case.

Điều kiện trước mapper: `itemCode` và `market` phải khác `null`. Nếu input không hợp lệ, Filter hoặc validation boundary phải trả lỗi rõ ràng. Không “sửa lỗi” bằng cách ngầm biến mọi giá trị rỗng thành một thị trường mặc định, trừ khi hợp đồng nghiệp vụ quy định như vậy.

**Phân biệt converter với Transformer nghiệp vụ:** converter chuyển JSON bytes thành `IncomingOrderV1`; Transformer chuyển `IncomingOrderV1` thành `PlaceOrder`. Một message có thể đã được parse thành object nhưng vẫn cần normalize trước khi đi vào core.

## 6. Kết nối bằng Spring Integration Java DSL

Spring Integration cho phép dùng **Messaging Gateway** làm điểm vào của flow. Gateway là API Java mà adapter có thể gọi; bên trong, framework đưa message vào channel. Đây là lớp glue giữa transport adapter và pipeline.

Ví dụ dưới dùng flow đồng bộ để nhận kết quả ngay. Các import Java/Spring/Spring Integration được lược bỏ, và các kiểu ở mục trước được dùng lại.

~~~java
@MessagingGateway(defaultRequestChannel = "orders.in")
public interface OrderMessageGateway {
    OrderReceipt submit(IncomingOrderV1 input);
}

@Configuration
@EnableIntegration
@IntegrationComponentScan
public class OrderIntegrationConfig {

    @Bean
    public OrderMapper orderMapper() {
        return new OrderMapper();
    }

    @Bean
    public IntegrationFlow orderFlow(
            PlaceOrderUseCase useCase, OrderMapper mapper) {
        return IntegrationFlow.from("orders.in")
            .filter(IncomingOrderV1.class,
                dto -> dto != null
                    && dto.requestId() != null
                    && !dto.requestId().isBlank()
                    && dto.itemCode() != null
                    && dto.market() != null,
                spec -> spec.throwExceptionOnRejection(true))
            .transform(IncomingOrderV1.class, mapper::toCommand)
            .handle(PlaceOrder.class,
                (command, headers) -> useCase.place(command))
            .get();
    }
}
~~~

Luồng này thực hiện ba việc riêng biệt:

- **Filter:** kiểm tra một phần hợp đồng kỹ thuật trước khi gọi mapper. Cấu hình `throwExceptionOnRejection(true)` khiến message bị từ chối tạo lỗi thay vì âm thầm biến mất trong một Gateway cần reply. Đây là quyết định của ví dụ, không phải cách xử lý bắt buộc cho mọi flow.
- **Transformer:** đổi payload `IncomingOrderV1` thành `PlaceOrder`, đồng thời Spring Integration thường giữ các headers hợp lệ khi tạo message kết quả.
- **Service Activator:** gọi `PlaceOrderUseCase` và trả `OrderReceipt` cho bên gọi Gateway. Use case chỉ nhận command thuần Java.

Trong đường đi sử dụng `DirectChannel` mặc định và không tạo ranh giới bất đồng bộ, Gateway có thể chờ handler hoàn thành rồi nhận reply. Nếu thay một phần bằng `ExecutorChannel` hoặc `QueueChannel`, hành vi chờ, timeout và lỗi có thể thay đổi; phải định nghĩa lại contract phản hồi và xử lý lỗi tương ứng.

**Lưu ý cấu hình:** bean `PlaceOrderUseCase` và bean cài đặt `OrderRepositoryPort` cần được khai báo tại application configuration. Đoạn code tập trung vào đường đi message, không bao gồm khởi tạo database hoặc cấu hình giao thức mạng.

~~~mermaid
flowchart LR
    A["Adapter: IncomingOrderV1"] --> G["Gateway: orders.in"]
    G --> F{"Filter: fields hợp lệ?"}
    F -->|"Có"| T["Transformer → PlaceOrder"]
    F -->|"Không"| X["Exception / error mapping"]
    T --> U["UseCase: place(command)"]
    U --> R["OrderReceipt"]
    R --> G
~~~

Không để `OrderMessageGateway` trở thành nơi chứa điều kiện nghiệp vụ; nó chỉ mô tả giao diện truyền message vào pipeline.

## 7. Hai transport adapter dùng cùng một flow

Một adapter HTTP có thể nhận JSON, parse thành `IncomingOrderV1` rồi gọi Gateway:

~~~java
@RestController
public class OrderHttpAdapter {
    private final OrderMessageGateway gateway;

    public OrderHttpAdapter(OrderMessageGateway gateway) {
        this.gateway = gateway;
    }

    @PostMapping("/orders")
    public OrderReceipt submit(@RequestBody IncomingOrderV1 request) {
        return gateway.submit(request);
    }
}
~~~

Ví dụ sử dụng Spring Kafka như một phương án transport adapter khác. Listener chỉ giải mã JSON và gọi đúng Gateway:

~~~java
public final class OrderKafkaAdapter {
    private final ObjectMapper objectMapper;
    private final OrderMessageGateway gateway;

    public OrderKafkaAdapter(ObjectMapper mapper, OrderMessageGateway gateway) {
        this.objectMapper = mapper;
        this.gateway = gateway;
    }

    @KafkaListener(topics = "orders.commands", groupId = "orders-service")
    public void onMessage(String json) throws JsonProcessingException {
        IncomingOrderV1 request =
            objectMapper.readValue(json, IncomingOrderV1.class);
        gateway.submit(request);
    }
}
~~~

Spring Kafka cần dependency, bean registration và consumer/error-handler configuration riêng; ví dụ minh họa *vai trò của adapter*, không mô tả đầy đủ cấu hình vận hành Kafka. Khi nhận sự kiện, listener không quyết định “số lượng tối đa được bán” hoặc “khi nào tạo hóa đơn”. Cùng `PlaceOrderUseCase` đảm nhiệm các quyết định đó cho cả HTTP và broker.

Kết quả ứng dụng `OrderReceipt` có thể được HTTP adapter biểu diễn thành HTTP response. Với message broker, adapter có thể phát một event kết quả riêng hoặc không cần phản hồi đồng bộ, tùy hợp đồng. **Đừng cố dùng HTTP status code làm business result** trong core và cũng đừng mặc định broker nhận ack nghĩa là giao dịch nghiệp vụ thành công.

### Khi adapter khác nhau thật sự cần xử lý khác nhau

HTTP cần mapping ngoại lệ sang `400`, `409` hoặc `5xx`; broker cần phân loại lỗi retry được và không retry được để ack/nack hoặc chuyển DLQ. Đó là *transport policy*. Cùng một `InvalidOrderException` có thể được HTTP mapper chuyển thành `400 Bad Request`, trong khi broker consumer ghi event lỗi vào kênh kiểm tra rồi ack thông điệp sai vĩnh viễn. **Quy tắc xác định thế nào là đơn không hợp lệ vẫn nằm ở use case**.

## 8. Router và nhiều nhánh vẫn giữ core độc lập

Không phải mọi flow chỉ có một đường thẳng. Ví dụ đơn nội địa cần cập nhật kho VN, còn đơn quốc tế cần bước tính phí khác. Có thể đặt **Router EIP** dựa trên `region` của command chuẩn:

~~~mermaid
flowchart LR
    I["DTO đã parse"] --> T["Transformer: PlaceOrder"]
    T --> R{"Router: region"}
    R -->|"VN"| V["orders.vn"]
    R -->|"Khác"| W["orders.other"]
    V --> S1["OrderUseCase với chính sách VN"]
    W --> S2["OrderUseCase với chính sách phù hợp"]
    S1 --> O["OrderReceipt"]
    S2 --> O
~~~

Trong từng nhánh, handler nên gọi **cổng nghiệp vụ** phù hợp, thay vì tự kiểm tra từng điều kiện giá hay tồn kho. Nếu lựa chọn nhánh mang ý nghĩa nghiệp vụ phức tạp, use case hoặc một domain policy có thể tính trước `ProcessingRoute`; Router chỉ dùng kết quả đó để chuyển message đến channel. Cách này giúp quy tắc nghiệp vụ vẫn test độc lập.

Một đoạn DSL minh họa routing:

~~~java
.route(PlaceOrder.class, PlaceOrder::region,
    spec -> spec.channelMapping("VN", "orders.vn")
                .defaultOutputChannel("orders.other"))
~~~

Đây là **đoạn nối trong một flow khác**, sau bước Transformer và trước các handler theo nhánh. Không dán trực tiếp vào cuối ví dụ Gateway đang trả reply nếu chưa cấu hình những handler cuối cùng và đường phản hồi. Với luồng request/reply, phải xác định mọi nhánh có kết quả hoặc lỗi rõ ràng; nhánh bị loại không phản hồi có thể khiến Gateway chờ đến timeout.

Nếu thêm **Splitter/Aggregator**, có thể tách một `PlaceOrder` thành danh sách dòng hàng, xử lý độc lập rồi gộp kết quả theo `orderId`/correlation. Nghiệp vụ tính giá từng dòng là dịch vụ thuần Java; Splitter/Aggregator chịu trách nhiệm phân phối, nhóm message, timeout và release, không phải nơi ẩn các phép tính giá.

## 9. Hợp đồng message: payload nghiệp vụ và headers vận hành

Spring Integration biểu diễn message bằng `Message<T>`, gồm **payload** và **headers**. Phân định trách nhiệm ngay từ đầu:

| Dữ liệu | Thường đặt ở đâu? | Ai dùng? |
|---|---|---|
| `orderId`, `sku`, `quantity` | Payload/command | Business use case |
| `region` đã chuẩn hóa | Payload/command | Domain policy, Router |
| `eventId`/idempotency key | Hợp đồng nghiệp vụ hoặc metadata đã thống nhất | Xử lý chống trùng |
| `correlationId`, `sequenceNumber`, `sequenceSize` | Message headers | Splitter/Aggregator, flow điều phối |
| `traceId` và tracing baggage | Header/context theo chuẩn tích hợp | Observability |
| HTTP request headers, Kafka offset, partition | Adapter metadata | Transport/error handling |

Không truyền `HttpServletRequest` hoặc `ConsumerRecord` vào `PlaceOrderUseCase` chỉ để lấy correlation ID. Nếu use case thực sự cần một định danh để bảo đảm idempotency, đưa nó vào một **kiểu ngữ cảnh ứng dụng thuần Java** hoặc trường của command, rồi mapper xác định rõ nguồn dữ liệu.

Tại ranh giới broker hoặc serialization, không giả định headers tự động được giữ nguyên. Kiểm tra header mapper và hợp đồng giữa producer–consumer. Với message được tạo lại sau retry, `MessageHeaders.ID` có thể khác; nó không thay thế idempotency key ổn định.

## 10. Error, retry và transaction đặt ở đúng lớp

Một thiết kế tách core khỏi transport không có nghĩa core không được phát lỗi. Core phải nêu rõ **lỗi nghiệp vụ**, còn adapter quyết định **cách biểu diễn và khôi phục**.

| Lỗi | Nơi phát hiện | Xử lý khuyến nghị |
|---|---|---|
| JSON sai cú pháp hoặc schema không giải mã được | Adapter/converter | HTTP 400 hoặc broker quarantine/DLQ theo policy |
| Giá trị thiếu trước bước Transformer | Validation/Filter | Rejected message hoặc exception có thông tin |
| Số lượng không hợp lệ, order đã đóng | Use case | Exception/result nghiệp vụ có mã lỗi ổn định |
| Database tạm thời unavailable | Repository adapter | Tạo lỗi kỹ thuật để tầng điều phối quyết định retry |
| Request bị phát lại | Application/idempotency store | Trả kết quả đã lưu hoặc bỏ qua side effect trùng |
| Gateway chờ reply quá hạn | Integration boundary | Timeout rõ ràng; không mặc định nghiệp vụ chưa chạy |

Với **DirectChannel**, exception từ handler đồng bộ có thể lan ngược lên HTTP controller hoặc broker listener. Khi flow chạy bằng `ExecutorChannel`, poller hay broker inbound adapter, lỗi xuất hiện trong ngữ cảnh khác và cần **error channel, retry advice, broker recovery** thích hợp. Không mặc định mọi exception tự tìm đến cùng một error channel.

**Phân biệt retry theo lớp:**

- Use case đảm bảo invariant và idempotency, vì nó không biết cùng một command sẽ được gửi mấy lần.
- Integration flow có thể retry thao tác kỹ thuật tạm thời với giới hạn và backoff.
- Broker adapter quyết định ack/nack, redelivery, DLQ theo hợp đồng delivery.
- HTTP adapter quyết định mã phản hồi và có nên cho client gửi lại request với cùng idempotency key hay không.

Trong các flow phân tán, message delivery *at-least-once* có thể khiến handler chạy lại. Nếu ghi dữ liệu thành công rồi lỗi xảy ra trước khi broker ack, việc giao lại có thể gây tác dụng phụ lần hai. Cần khóa unique/idempotency ledger, transaction thích hợp và đôi khi **transactional outbox** để liên kết thay đổi database với việc phát sự kiện.

**Không coi “đã đưa vào queue” là “đã hoàn tất nghiệp vụ”.** `QueueChannel` trong bộ nhớ không mặc định lưu bền vững hoặc khôi phục message sau khi handler thất bại; broker cũng cần cấu hình persistence và ack đúng.

## 11. Test theo từng ranh giới thay vì dựng cả hệ thống cho mọi bài test

Cách tổ chức này tạo ra ba tầng test bổ sung nhau.

| Tầng | Kiểm tra gì? | Cần hạ tầng gì? |
|---|---|---|
| **Use case unit test** | Invariant, kết quả nghiệp vụ, idempotency với fake repository | JUnit + Java thuần |
| **Integration flow test** | Filter, Transformer, Router, Gateway, headers, reply/error | Spring test context, test channel/handler |
| **Adapter contract test** | JSON, HTTP status, broker serialization, ack/retry và header mapping | Web integration test hoặc broker trong môi trường test |

Ví dụ đơn vị test lõi, không chạy Spring Integration:

~~~java
@Test
void rejectsNonPositiveQuantity() {
    OrderRepositoryPort repository = command ->
        new OrderReceipt(command.orderId(), "ACCEPTED");

    PlaceOrderUseCase useCase = new DefaultPlaceOrderUseCase(repository);

    assertThrows(InvalidOrderException.class, () ->
        useCase.place(new PlaceOrder("O-101", "SKU-1", 0, "VN")));
}

@Test
void acceptsValidOrderThroughPort() {
    OrderRepositoryPort repository = command ->
        new OrderReceipt(command.orderId(), "ACCEPTED");

    PlaceOrderUseCase useCase = new DefaultPlaceOrderUseCase(repository);

    OrderReceipt receipt =
        useCase.place(new PlaceOrder("O-102", "SKU-2", 3, "VN"));

    assertEquals("O-102", receipt.orderId());
    assertEquals("ACCEPTED", receipt.status());
}
~~~

Đối với flow, test thêm việc `IncomingOrderV1("O-103", " SKU-3 ", 2, " vn ")` trở thành `PlaceOrder("O-103", "SKU-3", 2, "VN")` và được đưa tới handler. Khi Filter từ chối, kiểm tra lỗi đến Gateway và không có lệnh ghi nào. Với Router, phải có test cho mọi nhánh, bao gồm default route và input lạ.

Đối với broker adapter, thêm test redelivery của một `eventId` và xác minh database chỉ có một tác dụng phụ. Kiểm tra rằng mất/kéo dài thời gian reply của Gateway được phân loại đúng, vì timeout của bên gọi không chứng minh được handler đã thất bại.

## 12. Quan sát flow mà không ràng buộc domain vào logger transport

Tách logic khỏi transport sẽ hiệu quả hơn nếu log/metric được thu thập ở boundary có đủ ngữ cảnh:

~~~text
HTTP / broker ingress
    └── decode_time, request_id, event_id
Gateway / orders.in
    └── message_count, correlation_id
Filter / Transformer / Router
    └── rejected_count, branch, mapping_error
OrderUseCase
    └── business_result, processing_duration
Repository adapter
    └── db_errors, retry_count, commit_duration
Outbound adapter
    └── publish_status, delivery_attempt, dlq_count
~~~

Không yêu cầu domain nhận trực tiếp đối tượng Kafka, servlet hoặc tracing span chỉ để ghi log. Có thể dùng observation/interceptor ở integration layer và định danh business ổn định ở input. Không log toàn bộ payload nếu chứa thông tin nhạy cảm; log mã đơn, loại event và mã lỗi khi cần truy vết.

Với Spring Integration và Micrometer/observation đã cấu hình, nên theo dõi message đi qua từng channel/endpoint, thời gian handler, số lần lỗi và backlog. Khi thêm `Splitter/Aggregator`, correlation và timeout phải quan sát được để giải thích vì sao một nhóm chưa phát kết quả.

## 13. Những cách làm dễ khiến các lớp dính chặt nhau

**Đưa business rule vào listener:** `@KafkaListener` vừa parse JSON, vừa tính giá, vừa lưu đơn. Kết quả là HTTP adapter phải sao chép thuật toán tương tự. Hãy để listener chỉ giải mã và gọi cổng chung.

**Đưa header transport vào domain:** `PlaceOrderUseCase.place(ConsumerRecord record)` khiến mọi test nghiệp vụ phải tạo metadata Kafka. Hãy map record thành command/context thuần Java.

**Cho mỗi channel dùng một payload ngẫu nhiên:** handler một nơi nhận `String`, nơi khác `byte[]` rồi tự ép kiểu. Cần một bước giải mã ở ingress và contract input/output rõ ràng cho từng filter.

**Lẫn domain Filter với Filter EIP:** `Filter` có thể loại message khỏi flow, nhưng một invariant quan trọng vẫn phải được bảo vệ trong use case. Nếu ai đó gọi use case trực tiếp, nghiệp vụ không được chấp nhận giá trị sai.

**Retry toàn bộ flow không giới hạn:** một lời gọi nghiệp vụ đã ghi dữ liệu rồi có thể thất bại khi gửi reply. Retry không có idempotency sẽ tạo dữ liệu trùng; giới hạn retry và xác định khóa chống trùng.

**Giữ request/reply qua queue mà không xác định timeout:** việc đổi DirectChannel thành QueueChannel tạo ranh giới thực thi; Gateway có thể chờ kết quả. Cần thiết kế reply channel, timeouts, error path hoặc chuyển hợp đồng sang async.

**Kiến trúc có quá nhiều lớp không mang giá trị:** mục tiêu là trách nhiệm và ranh giới rõ ràng. Một adapter đơn giản và một service thuần Java có thể đủ cho use case nhỏ. Chỉ thêm bước EIP khi thật sự cần biến đổi, định tuyến hoặc phối hợp thông điệp.

## 14. Bài thực hành: thay HTTP bằng broker mà không sửa core

Xây dựng một tính năng **tiếp nhận đơn hàng** theo các mốc:

1. **Định nghĩa contract:** `IncomingOrderV1` (transport DTO), `PlaceOrder` (command), `OrderReceipt` (result) và interface `PlaceOrderUseCase`.
2. **Viết use case:** kiểm tra invariant, gọi `OrderRepositoryPort`, phân biệt lỗi nghiệp vụ với lỗi hạ tầng. Unit test bằng fake repository.
3. **Viết flow Spring Integration:** Gateway → Filter cấu trúc → Transformer/mapper → Service Activator gọi use case. Test payload và reply.
4. **Viết HTTP adapter:** nhận JSON, map lỗi thành HTTP status và trả kết quả. Không nhân bản quy tắc của use case.
5. **Thêm broker adapter:** nhận event qua consumer phù hợp, decode và gọi Gateway; thử message bị giao lại. Không thay logic nghiệp vụ đang hoạt động.
6. **Thêm một Router:** chia theo `region` và quan sát mọi nhánh. Khi cần, thêm Splitter/Aggregator cho các dòng hàng và giữ correlation.
7. **Thử lỗi:** JSON sai, thiếu field, số lượng âm, database timeout, duplicate, reply timeout, worker restart. Ghi rõ nơi lỗi được phát hiện và chính sách khôi phục.

**Điều kiện hoàn thành:**

- Cùng một command hợp lệ cho kết quả nghiệp vụ tương đương dù đến từ HTTP hay broker.
- Business service không import thư viện HTTP/Kafka/Spring Integration và có unit test chạy độc lập.
- Thay đổi endpoint URL hoặc topic không cần sửa mã tính toán/quy tắc đơn hàng.
- Message lỗi có đường xử lý rõ; message bị giao lại không gây side effect trùng ngoài ý muốn.
- Test xác minh Filter, Transformer, Router, correlation, reply và error theo đúng ranh giới.
- Log/metric cho biết message đến từ đâu, đã qua nhánh nào, lúc nào thành công hoặc thất bại.

## 15. Checklist tự đánh giá thiết kế

| Câu hỏi | Tín hiệu đạt |
|---|---|
| Business rule có phụ thuộc đối tượng HTTP/Kafka không? | Không; chỉ dùng kiểu nghiệp vụ và port |
| Đầu vào từ nhiều transport có hợp đồng chung không? | Có DTO-to-command mapping xác định |
| Transformer có thay đổi đúng một trách nhiệm không? | Input/output type rõ; lỗi mapping được xử lý |
| Router và Filter có làm mất kết quả request/reply không? | Mọi nhánh có kết quả hoặc lỗi/timeout được định nghĩa |
| Correlation có đi được qua adapter, split và aggregate không? | Có kiểm thử và cấu hình header mapping |
| Retry có làm thực thi lại tác dụng phụ không? | Có idempotency key và chính sách recovery |
| Thay topic/URL có cần sửa use case không? | Không, chỉ sửa adapter/configuration |
| Test nghiệp vụ có cần khởi động broker không? | Không; chỉ integration/contract test mới cần |

## 16. Kết luận

**Tách business logic khỏi transport** là việc giữ quy tắc nghiệp vụ trong các service và port ổn định, còn giao thức, serialization, headers truyền nhận và chính sách delivery nằm ở adapter cùng integration flow. Spring Integration thực hiện kết nối bằng các channel và endpoint thuộc **Pipes and Filters**, để **Gateway, Filter, Transformer, Router, Splitter, Aggregator, retry và error channel** có trách nhiệm tường minh.

Một thiết kế tốt cho phép bổ sung HTTP, Kafka, AMQP hoặc nguồn theo lịch mà không sao chép logic đơn hàng; đồng thời giữ được kiểm thử độc lập, correlation, khả năng quan sát và chiến lược khôi phục khi flow trở thành hệ thống phân tán.
