# Giao tiếp đồng bộ, bất đồng bộ và ranh giới của module

Trong hệ thống microservice, một dịch vụ thường cần gọi dịch vụ khác để lấy dữ liệu hoặc yêu cầu thực hiện một nghiệp vụ. Cách gọi có thể đồng bộ, bất đồng bộ qua HTTP hoặc thông qua message broker. Mỗi cách có cách chờ kết quả, xử lý lỗi và quản lý tài nguyên khác nhau.

Trong module **Spring Cloud LoadBalancer**, trọng tâm là việc chọn một instance của dịch vụ đích ở phía client. Load balancing hỗ trợ các client HTTP giao tiếp với dịch vụ qua service ID, nhưng không quyết định toàn bộ kiến trúc giao tiếp. Muốn thiết kế đúng, cần phân biệt cơ chế đồng bộ và bất đồng bộ, đồng thời đặt rõ trách nhiệm của client, discovery, load balancer, transport và dịch vụ đích.

## 1. Hai chiều phân biệt: kiểu thực thi và kiểu trao đổi thông điệp

Hai khái niệm thường bị trộn lẫn là *đồng bộ/bất đồng bộ* và *blocking/non-blocking*.

- **Đồng bộ (synchronous)** mô tả cách bên gọi chờ kết quả: luồng xử lý gọi hàm và cần kết quả trước khi đi tiếp.
- **Bất đồng bộ (asynchronous)** mô tả cách bên gọi tiếp tục công việc trong khi kết quả được hoàn thành hoặc gửi về sau.
- **Blocking** mô tả việc một thread bị giữ lại trong lúc chờ I/O.
- **Non-blocking** mô tả việc thread có thể xử lý công việc khác trong lúc I/O đang chờ.

Một lời gọi HTTP đồng bộ thường blocking, ví dụ gọi bằng RestClient. WebClient cho phép xây dựng lời gọi HTTP reactive, non-blocking. Message broker thường tạo ra giao tiếp bất đồng bộ theo kiểu gửi sự kiện hoặc lệnh và xử lý ở consumer sau đó.

Không nên coi “dùng WebClient” là đồng nghĩa với “giao tiếp qua message broker”. WebClient vẫn gửi một HTTP request đến một endpoint và thường vẫn nhận một HTTP response. Khác biệt chính là cách ứng dụng tổ chức việc chờ và tiếp tục xử lý.

| Hình thức | Cách bên gọi tiếp tục | Kênh trao đổi thường gặp | Đặc điểm |
|---|---|---|---|
| HTTP đồng bộ | Chờ response trước khi trả kết quả cho luồng gọi | RestClient, OpenFeign | Dễ đọc theo luồng tuần tự; thread có thể bị giữ trong lúc chờ |
| HTTP reactive | Trả về publisher; kết quả được xử lý khi có dữ liệu | WebClient | Có thể non-blocking; dễ kết hợp nhiều tác vụ I/O |
| Messaging bất đồng bộ | Gửi message rồi tiếp tục; consumer xử lý độc lập | Kafka, RabbitMQ | Tách thời điểm gửi và xử lý; thường cần xử lý eventual consistency |

Việc chọn hình thức nào phụ thuộc vào yêu cầu nghiệp vụ, độ trễ, khả năng chịu tải và cách hệ thống cần xử lý lỗi. Load balancer không tự chuyển một lời gọi đồng bộ thành bất đồng bộ.

## 2. Spring Cloud LoadBalancer nằm ở đâu trong luồng giao tiếp?

Một client thường biết tên logic của dịch vụ cần gọi, chẳng hạn `inventory-service`, thay vì biết trước địa chỉ IP và port của từng instance. Service discovery cung cấp danh sách instance đang được đăng ký. Spring Cloud LoadBalancer nhận danh sách phù hợp, áp dụng chính sách chọn instance và trả về instance được chọn cho HTTP client thực hiện request.

Luồng tổng quát:

~~~mermaid
flowchart LR
    A["Application service"] --> B["Client của dịch vụ"]
    B --> C{"HTTP client"}
    C -->|"RestClient"| D["Blocking load-balancer integration"]
    C -->|"WebClient"| E["Reactive load-balancer integration"]
    D --> F["ServiceInstance supplier / discovery"]
    E --> F
    F --> G["Chọn ServiceInstance"]
    G --> H["HTTP transport"]
    H --> I["Dịch vụ đích"]
~~~

Các thành phần có trách nhiệm khác nhau:

1. **Application service** quyết định nghiệp vụ nào cần dữ liệu hoặc hành động từ dịch vụ khác.
2. **Service client** đóng gói endpoint, request, response và cách ánh xạ lỗi của dịch vụ đích.
3. **Service discovery** cung cấp thông tin instance, ví dụ host, port và metadata.
4. **Spring Cloud LoadBalancer** chọn một ServiceInstance từ danh sách được cung cấp.
5. **HTTP client và transport** mở kết nối, gửi request, nhận response, áp dụng cấu hình timeout và xử lý giao thức.
6. **Dịch vụ đích** xác thực request, thực thi nghiệp vụ và trả kết quả.

Khi URI dùng service ID như `http://inventory-service/api/items/42`, client được cấu hình load-balanced có thể phân giải tên logic đó thành một instance cụ thể. Nếu truyền trực tiếp URI chứa host và port của một instance, ứng dụng đã bỏ qua ý nghĩa lựa chọn theo service ID của load balancer.

Service discovery và load balancing là hai bước liên quan nhưng khác nhau. Discovery trả lời câu hỏi “có những instance nào?”, còn load balancer trả lời câu hỏi “request này sẽ đi đến instance nào?”. Danh sách instance có thể đến từ registry hoặc nguồn cấu hình khác; LoadBalancer làm việc thông qua cơ chế cung cấp ServiceInstance tương ứng.

## 3. Gọi HTTP đồng bộ bằng RestClient

RestClient phù hợp với ứng dụng imperative, nơi phương thức gọi thường cần trả về dữ liệu ngay cho luồng xử lý hiện tại. Lời gọi HTTP chặn thread cho đến khi nhận response hoặc gặp lỗi/timeout.

Cấu hình một RestClient.Builder có hỗ trợ load balancing:

~~~java
@Configuration
public class HttpClientConfiguration {

    @Bean
    @LoadBalanced
    RestClient.Builder loadBalancedRestClientBuilder() {
        return RestClient.builder();
    }
}
~~~

Tạo client chuyên trách giao tiếp với dịch vụ inventory:

~~~java
@Service
public class InventoryClient {

    private final RestClient restClient;

    public InventoryClient(
            @LoadBalanced RestClient.Builder builder) {
        this.restClient = builder
                .baseUrl("http://inventory-service")
                .build();
    }

    public InventoryResponse getInventory(String sku) {
        return restClient.get()
                .uri("/api/inventory/{sku}", sku)
                .retrieve()
                .body(InventoryResponse.class);
    }
}
~~~

Khi phương thức `getInventory` được gọi, ứng dụng chờ HTTP response và nhận một InventoryResponse. Tên `inventory-service` là service ID; lớp tích hợp load balancing chọn instance phù hợp trước khi request được gửi đi.

Một luồng gọi điển hình:

~~~text
OrderService
    |
    | getInventory("SKU-001")
    v
InventoryClient
    |
    | GET http://inventory-service/api/inventory/SKU-001
    v
LoadBalancer chọn instance
    |
    | ví dụ: inventory-2.internal:8080
    v
HTTP transport gửi request
    |
    v
Inventory service trả response
    |
    v
OrderService tiếp tục xử lý
~~~

RestClient giúp code tuần tự và dễ theo dõi. Đổi lại, thời gian chờ mạng chiếm dụng thread đang thực hiện lời gọi. Nếu một request nghiệp vụ gọi nhiều dịch vụ tuần tự, tổng thời gian chờ có thể cộng dồn. Cần đặt timeout kết nối và timeout đọc phù hợp ở HTTP request factory/transport được sử dụng; bản thân việc chọn instance không thay thế cấu hình timeout.

Với ứng dụng đang dùng RestTemplate, Spring Cloud cũng hỗ trợ tích hợp load balancing qua bean RestTemplate được đánh dấu `@LoadBalanced`. Khi phát triển mới trên nền tảng hỗ trợ RestClient, có thể cân nhắc RestClient cho phong cách imperative hiện đại hơn.

## 4. Gọi HTTP bất đồng bộ theo kiểu reactive bằng WebClient

WebClient cung cấp API reactive. Một phương thức có thể trả về Mono hoặc Flux thay vì chờ response rồi trả về đối tượng trực tiếp. Khi ứng dụng sử dụng pipeline reactive đúng cách, thread không cần bị giữ trong lúc chờ I/O.

Cấu hình WebClient.Builder có hỗ trợ load balancing:

~~~java
@Configuration
public class ReactiveHttpClientConfiguration {

    @Bean
    @LoadBalanced
    WebClient.Builder loadBalancedWebClientBuilder() {
        return WebClient.builder();
    }
}
~~~

Client gọi dịch vụ inventory:

~~~java
@Service
public class ReactiveInventoryClient {

    private final WebClient webClient;

    public ReactiveInventoryClient(
            @LoadBalanced WebClient.Builder builder) {
        this.webClient = builder
                .baseUrl("http://inventory-service")
                .build();
    }

    public Mono<InventoryResponse> getInventory(String sku) {
        return webClient.get()
                .uri("/api/inventory/{sku}", sku)
                .retrieve()
                .bodyToMono(InventoryResponse.class);
    }
}
~~~

Phương thức trả về Mono ngay khi xây dựng pipeline. Request được thực thi khi publisher được subscribe. Khi response đến, dữ liệu tiếp tục đi qua pipeline reactive:

~~~java
public Mono<OrderSummary> createOrder(CreateOrderRequest request) {
    return inventoryClient.getInventory(request.sku())
            .flatMap(inventory -> orderService.create(request, inventory));
}
~~~

WebClient vẫn gọi HTTP đến một dịch vụ cụ thể. Load balancing vẫn chọn một ServiceInstance từ danh sách instance của service ID. Điểm khác biệt là client reactive biểu diễn kết quả bằng publisher và cho phép kết hợp các thao tác I/O mà không phải chặn thread tại mỗi bước.

Trong một luồng xử lý WebFlux, tránh gọi `block()` để chờ Mono hoặc Flux. `block()` biến đoạn xử lý đó thành chờ đồng bộ và có thể làm nghẽn event-loop thread nếu dùng sai chỗ. Nếu ứng dụng không cần reactive end-to-end, RestClient thường đơn giản hơn và dễ phù hợp với mô hình imperative.

Cũng cần nhớ rằng WebClient không tự bảo đảm mọi đoạn code xung quanh đều non-blocking. Nếu một pipeline gọi JDBC blocking, đọc file blocking hoặc gọi một thư viện blocking trên event-loop thread, lợi ích non-blocking có thể bị mất. Cần chọn driver và cách thực thi phù hợp với mô hình của toàn luồng.

## 5. Messaging bất đồng bộ khác HTTP reactive như thế nào?

HTTP reactive vẫn là mô hình request/response: client gửi request đến một endpoint và thường chờ response để tiếp tục pipeline. Messaging bất đồng bộ tách thời điểm gửi message khỏi thời điểm consumer xử lý.

Ví dụ, khi Order service tạo đơn hàng, nó có thể phát một sự kiện `OrderCreated`. Inventory service nhận sự kiện và cập nhật tồn kho sau đó. Producer không cần giữ một kết nối HTTP đến Inventory service để chờ xử lý hoàn tất. Hai phía phối hợp thông qua broker và hợp đồng message.

~~~mermaid
sequenceDiagram
    participant O as Order service
    participant B as Message broker
    participant I as Inventory service
    O->>B: Publish OrderCreated
    B-->>O: Xác nhận nhận message
    Note over O: Tiếp tục luồng xử lý riêng
    B->>I: Deliver message
    I->>I: Xử lý và cập nhật tồn kho
    I-->>B: Acknowledge
~~~

Cách này giảm phụ thuộc thời gian giữa producer và consumer, nhưng phát sinh các vấn đề như giao nhận lặp, thứ tự message, retry, dead-letter queue, idempotency và eventual consistency. Producer có thể nhận xác nhận broker đã nhận message mà chưa biết nghiệp vụ ở consumer đã hoàn tất hay chưa.

Spring Cloud LoadBalancer tập trung vào lựa chọn instance cho các client giao tiếp theo mô hình service instance, phổ biến nhất là HTTP. Nó không chọn consumer cho một Kafka topic, không cân bằng partition và không thay thế cơ chế định tuyến của broker. Nếu hệ thống dùng messaging, hãy cấu hình và vận hành broker/client theo cơ chế của nền tảng messaging tương ứng.

## 6. Ranh giới trách nhiệm giữa các module

Một thiết kế dễ bảo trì cần để mỗi thành phần quản lý đúng loại quyết định của nó.

| Thành phần | Chịu trách nhiệm | Không nên gánh |
|---|---|---|
| Domain/application của dịch vụ gọi | Quy tắc nghiệp vụ, thời điểm cần gọi dịch vụ khác, xử lý kết quả theo nghiệp vụ | Chọn IP/port instance, tự truy vấn registry |
| Service client/adapter | API contract, endpoint theo service ID, DTO, ánh xạ lỗi từ xa | Quyết định instance vật lý cho từng request |
| Service discovery | Đăng ký, khám phá và cung cấp metadata instance | Quyết định nghiệp vụ của request |
| Spring Cloud LoadBalancer | Chọn ServiceInstance theo chính sách và dữ liệu được cung cấp | Thực thi nghiệp vụ, quản lý transaction phân tán |
| HTTP transport | Kết nối, TLS, connection pool, timeout, gửi/nhận HTTP | Quyết định dịch vụ nào sở hữu dữ liệu |
| Resilience components | Retry, circuit breaker, rate limiting, bulkhead theo cấu hình | Thay thế service discovery hoặc sửa lỗi nghiệp vụ |
| Dịch vụ được gọi | API và dữ liệu do dịch vụ đó sở hữu; xác thực và thực thi nghiệp vụ | Phụ thuộc vào địa chỉ instance do caller tự lưu |

Có thể đặt service client ở lớp adapter/infrastructure. Lớp application gọi một interface thể hiện nhu cầu nghiệp vụ, còn adapter triển khai interface đó bằng RestClient hoặc WebClient. Nhờ vậy, domain không phải phụ thuộc vào annotation `@LoadBalanced`, DiscoveryClient hay các lớp của Spring Cloud.

Ví dụ về ranh giới:

~~~java
public interface InventoryGateway {
    InventoryResult findBySku(String sku);
}
~~~

Một adapter ở lớp infrastructure có thể triển khai interface này bằng RestClient:

~~~java
@Component
public class HttpInventoryGateway implements InventoryGateway {

    private final InventoryClient client;

    public HttpInventoryGateway(InventoryClient client) {
        this.client = client;
    }

    @Override
    public InventoryResult findBySku(String sku) {
        InventoryResponse response = client.getInventory(sku);
        return InventoryResult.from(response);
    }
}
~~~

Đây là cách tổ chức minh họa. Với hệ thống reactive, interface có thể trả về Mono hoặc kiểu kết quả bất đồng bộ tương ứng. Điều quan trọng là chọn một mô hình nhất quán ở ranh giới module và không để code nghiệp vụ tùy tiện trộn lời gọi blocking với reactive.

Mỗi service client nên đại diện cho một API hoặc một nhóm thao tác có cùng chủ sở hữu. Tránh tạo một lớp HTTP tổng quát chứa URL, DTO và logic của mọi dịch vụ. Một client rõ trách nhiệm giúp thay đổi contract, timeout và chính sách lỗi của một dịch vụ mà ít ảnh hưởng đến phần còn lại.

## 7. Load balancing, timeout và retry phối hợp ra sao?

Chọn được instance không có nghĩa request chắc chắn thành công. Instance có thể dừng giữa lúc được chọn và lúc kết nối, mạng có thể chậm, dịch vụ có thể quá tải hoặc trả về lỗi nghiệp vụ.

Cần phân biệt các cơ chế sau:

- **Load balancing** chọn instance cho request.
- **Timeout** giới hạn thời gian chờ kết nối hoặc response.
- **Retry** thử lại một thao tác sau lỗi phù hợp.
- **Circuit breaker** tạm ngăn lời gọi đến một dịch vụ đang liên tục thất bại.
- **Bulkhead** giới hạn tài nguyên dành cho một nhóm lời gọi.
- **Health check/instance filtering** giúp loại instance không đáp ứng điều kiện được cấu hình khỏi danh sách có thể chọn.

Các cơ chế này có thể phối hợp nhưng không tự động thay thế nhau. Ví dụ, timeout ngăn một request chờ vô hạn nhưng không tự chọn instance khác. Retry có thể phát sinh thêm request và cần được cấu hình rõ. Không nên giả định mọi HTTP client đều retry tự động khi instance lỗi.

Một chính sách retry an toàn cần xét:

1. **Tính idempotent:** thao tác đọc thường dễ retry hơn thao tác tạo thanh toán hoặc trừ tồn kho. Nếu thao tác có thể được thực hiện hai lần, cần idempotency key hoặc cơ chế chống xử lý lặp.
2. **Loại lỗi:** lỗi kết nối tạm thời hoặc một số mã trạng thái có thể retry; lỗi validation hoặc nghiệp vụ thường không nên retry.
3. **Giới hạn số lần và thời gian:** đặt số lần thử, backoff và tổng deadline để request không kéo dài ngoài ngân sách thời gian của caller.
4. **Tải lên dịch vụ đích:** retry đồng loạt có thể làm dịch vụ đang quá tải nặng hơn. Cần phối hợp với circuit breaker, rate limiting hoặc backoff.
5. **Lựa chọn instance khi retry:** cần hiểu retry đang được áp dụng ở tầng nào và có yêu cầu load balancer chọn lại instance hay không; không mặc định mọi lần retry đều đi đến instance khác.

Với giao tiếp đồng bộ, deadline của request bên ngoài cần đủ lớn cho tổng thời gian các lời gọi bên trong và phần xử lý còn lại. Với reactive, hãy truyền và giới hạn thời gian trong pipeline theo cùng ngân sách đó. Dù dùng kiểu nào, cần ghi log hoặc trace service ID, instance đã chọn khi phù hợp, thời gian gọi, kết quả và nguyên nhân lỗi để điều tra sự cố.

## 8. Chọn mô hình giao tiếp theo nhu cầu

| Nhu cầu | Lựa chọn thường phù hợp | Lý do |
|---|---|---|
| API nội bộ cần kết quả ngay để hoàn tất request | RestClient hoặc OpenFeign | Luồng xử lý tuần tự, dễ theo dõi |
| Ứng dụng WebFlux cần gọi nhiều dịch vụ I/O | WebClient | Kết hợp publisher và tránh chặn thread trong pipeline |
| Gửi sự kiện để dịch vụ khác xử lý sau | Kafka hoặc RabbitMQ | Tách thời điểm gửi khỏi thời điểm xử lý |
| Tác vụ dài cần trạng thái và tra cứu kết quả | API nhận yêu cầu cộng với job/event hoặc workflow | Không giữ request HTTP mở trong toàn bộ thời gian xử lý |
| Giao tiếp cần phản hồi nghiệp vụ ngay | HTTP request/response | Caller cần biết kết quả để quyết định bước tiếp theo |

Không có lựa chọn nào luôn tốt hơn. Một hệ thống có thể dùng HTTP đồng bộ cho truy vấn cần phản hồi ngay, WebClient cho luồng I/O reactive và messaging cho sự kiện nghiệp vụ. Hãy chọn theo semantics của nghiệp vụ trước, rồi chọn client và chính sách load balancing phù hợp.

## 9. Các lỗi thiết kế thường gặp

**Gắn cứng địa chỉ instance trong code.** Khi instance thay đổi hoặc mở rộng số lượng, caller phải sửa cấu hình hoặc triển khai lại. Hãy dùng service ID và để discovery cùng load balancer xử lý danh sách instance.

**Để lớp nghiệp vụ tự chọn instance.** Việc gọi DiscoveryClient rồi tự chọn host/port làm rò rỉ chi tiết hạ tầng vào nghiệp vụ và dễ tạo nhiều cách chọn không nhất quán. Hãy đặt lựa chọn instance ở client integration.

**Dùng WebClient nhưng gọi block trong WebFlux.** Cách này có thể chiếm dụng event-loop thread và làm giảm khả năng xử lý đồng thời. Hãy trả về và kết hợp Mono/Flux xuyên suốt luồng reactive; chỉ chuyển sang blocking ở ranh giới được kiểm soát khi thực sự cần.

**Cho rằng reactive HTTP là messaging.** WebClient vẫn cần endpoint và response của HTTP. Nếu nghiệp vụ cần producer và consumer tách thời điểm xử lý, hãy dùng message broker cùng cơ chế giao nhận phù hợp.

**Retry mọi lỗi.** Retry thao tác không idempotent có thể tạo dữ liệu trùng hoặc thực hiện nghiệp vụ nhiều lần. Hãy phân loại lỗi và thiết kế idempotency trước khi bật retry.

**Đưa toàn bộ logic gọi dịch vụ vào một HTTP utility chung.** Utility quá tổng quát khiến contract và xử lý lỗi của các dịch vụ bị trộn lẫn. Hãy tạo client có tên và trách nhiệm rõ theo dịch vụ hoặc API.

## 10. Checklist khi thiết kế giao tiếp giữa dịch vụ

- [ ] Xác định caller cần response ngay, cần pipeline reactive hay chỉ cần phát message.
- [ ] Dùng service ID cho URI của HTTP client được cấu hình load balancing.
- [ ] Đảm bảo discovery cung cấp đúng danh sách ServiceInstance cho service ID.
- [ ] Chọn RestClient/OpenFeign cho luồng imperative hoặc WebClient cho luồng reactive.
- [ ] Đặt timeout theo deadline của request nghiệp vụ.
- [ ] Chỉ retry lỗi phù hợp và bảo đảm an toàn khi xử lý lặp.
- [ ] Xác định rõ trách nhiệm API contract, DTO và ánh xạ lỗi trong service client.
- [ ] Giữ domain/application tránh phụ thuộc trực tiếp vào chi tiết discovery và load balancing.
- [ ] Với messaging, xác định ack, retry, idempotency, thứ tự và cách xử lý message lỗi.
- [ ] Theo dõi service ID, độ trễ, lỗi và instance được chọn để vận hành hệ thống.

Spring Cloud LoadBalancer cung cấp một điểm tích hợp quan trọng cho giao tiếp HTTP giữa các dịch vụ: ứng dụng gọi bằng tên logic, còn client integration chọn một instance phù hợp để gửi request. Hiểu rõ kiểu giao tiếp và ranh giới module giúp đặt load balancing đúng tầng, giữ code nghiệp vụ độc lập với hạ tầng và xử lý lỗi theo đúng semantics của từng lời gọi.
