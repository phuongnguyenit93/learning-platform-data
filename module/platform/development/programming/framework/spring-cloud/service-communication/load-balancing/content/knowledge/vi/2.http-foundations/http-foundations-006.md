# Giao tiếp chặn luồng và không chặn luồng

Trong giao tiếp giữa các dịch vụ, một ứng dụng gửi HTTP request và chờ dịch vụ đích xử lý rồi trả HTTP response. Cách ứng dụng chờ response ảnh hưởng trực tiếp đến việc sử dụng thread, khả năng xử lý nhiều request đồng thời và cách tổ chức mã nguồn.

Trong module **SPRING_CLOUD_SERVICE_COMMUNICATION_LOAD_BALANCING**, nội dung này là nền tảng để chọn và sử dụng **RestClient**, **WebClient** hoặc **OpenFeign** khi Spring Cloud LoadBalancer định tuyến request đến một service instance. Load balancer quyết định request sẽ đến instance nào; kiểu chặn luồng hay không chặn luồng quyết định thread của ứng dụng xử lý thời gian chờ I/O như thế nào.

## 1. Chặn luồng và không chặn luồng là gì?

HTTP là giao thức request/response. Một request vẫn đi qua mạng, được server xử lý và nhận response bất kể client sử dụng mô hình chặn luồng hay không chặn luồng. Hai khái niệm này mô tả cách chương trình phía gọi quản lý công việc trong lúc chờ I/O.

### Giao tiếp chặn luồng (blocking)

Một lời gọi chặn luồng chỉ trả kết quả khi thao tác hoàn tất hoặc phát sinh lỗi. Trong lúc chờ kết nối, dữ liệu hoặc response, thread thực hiện lời gọi bị giữ lại và không thể tiếp tục xử lý công việc khác.

Ví dụ, khi gọi một phương thức đồng bộ để lấy thông tin sản phẩm, luồng xử lý phải chờ server phản hồi rồi mới chạy câu lệnh tiếp theo:

~~~java
ItemDto item = catalogClient.getItem(itemId);
orderService.continueProcessing(item);
~~~

Nếu request mất 400 ms, thread gọi phương thức phải dành thời gian đó để chờ. Thread không nhất thiết tiêu thụ CPU liên tục trong khoảng chờ, nhưng vẫn bị chiếm dụng và không thể phục vụ một request khác.

### Giao tiếp không chặn luồng (non-blocking)

Một lời gọi không chặn luồng khởi tạo thao tác I/O rồi trả quyền điều khiển cho thread hiện tại. Khi dữ liệu sẵn sàng, thư viện mạng phát tín hiệu hoàn tất; chương trình tiếp tục xử lý kết quả thông qua callback, future hoặc một luồng dữ liệu phản ứng.

Ví dụ với **WebClient**, phương thức có thể trả về **Mono<ItemDto>** trước khi response đến:

~~~java
Mono<ItemDto> itemPublisher = webClient.get()
    .uri("http://catalog-service/api/items/{id}", itemId)
    .retrieve()
    .bodyToMono(ItemDto.class);
~~~

Mono là một publisher biểu diễn một kết quả có thể xuất hiện sau này. Việc tạo publisher chưa đồng nghĩa request đã được gửi. Với Reactor, request được thực thi khi publisher được subscribe; trong ứng dụng WebFlux, framework thường đảm nhiệm việc subscribe ở ranh giới xử lý request.

Không chặn luồng không có nghĩa là request hoàn tất ngay lập tức, không sử dụng thread hoặc luôn nhanh hơn. Nó có nghĩa thread gọi không phải nằm chờ response trong suốt thời gian I/O.

### Phân biệt với đồng bộ và bất đồng bộ

Trong ứng dụng Java, các khái niệm thường đi cùng nhau nhưng không hoàn toàn đồng nghĩa:

- **Đồng bộ** mô tả cách luồng điều khiển nhận kết quả: lời gọi trả về kết quả ngay trong luồng thực thi hiện tại.
- **Bất đồng bộ** mô tả cách kết quả được thông báo sau khi công việc bắt đầu, chẳng hạn qua callback hoặc publisher.
- **Chặn luồng** mô tả việc thread hiện tại có phải chờ thao tác hoàn tất hay không.
- **Không chặn luồng** mô tả việc thread có thể tiếp tục làm công việc khác trong khi I/O đang diễn ra hay không.

Một API bất đồng bộ vẫn có thể bị sử dụng theo cách chặn nếu chương trình gọi **block()** hoặc chờ kết quả bằng một cơ chế tương đương. Ngược lại, việc đưa một lời gọi đồng bộ vào một thread pool chỉ chuyển nơi bị chặn sang thread khác; bản thân thao tác I/O vẫn là blocking.

## 2. Vòng đời của một HTTP request chặn luồng

Với client đồng bộ, luồng xử lý đi qua các bước theo thứ tự:

1. Ứng dụng gọi phương thức client.
2. Spring Cloud LoadBalancer nhận service ID, lấy danh sách instance khả dụng và chọn một instance.
3. HTTP client thiết lập hoặc tái sử dụng kết nối rồi gửi request.
4. Thread gọi chờ response từ dịch vụ đích.
5. Client đọc response, chuyển dữ liệu thành đối tượng Java và trả kết quả cho ứng dụng.
6. Các câu lệnh sau lời gọi mới được thực thi.

~~~mermaid
sequenceDiagram
    autonumber
    participant App as Ứng dụng gọi
    participant T as Request thread
    participant LB as Spring Cloud LoadBalancer
    participant S as Service instance

    App->>T: Gọi phương thức đồng bộ
    T->>LB: Resolve service ID
    LB-->>T: Trả về instance được chọn
    T->>S: Gửi HTTP request
    Note over T: Thread chờ response
    S-->>T: HTTP response
    T-->>App: Trả DTO hoặc lỗi
    App->>T: Tiếp tục xử lý
~~~

### Ví dụ với RestClient

Ở các phiên bản Spring Cloud có hỗ trợ tích hợp load balancing cho **RestClient**, có thể đăng ký builder được đánh dấu **@LoadBalanced**:

~~~java
@Configuration
class HttpClientConfiguration {

    @Bean
    @LoadBalanced
    RestClient.Builder loadBalancedRestClientBuilder() {
        return RestClient.builder();
    }
}
~~~

Client sử dụng service ID trong URL:

~~~java
@Service
class CatalogClient {

    private final RestClient restClient;

    CatalogClient(@LoadBalanced RestClient.Builder builder) {
        this.restClient = builder.build();
    }

    public ItemDto getItem(String itemId) {
        return restClient.get()
            .uri("http://catalog-service/api/items/{id}", itemId)
            .retrieve()
            .body(ItemDto.class);
    }
}
~~~

**catalog-service** là tên logic của dịch vụ. Spring Cloud LoadBalancer chuyển tên này thành địa chỉ của instance được chọn trước khi request được gửi đi. Phương thức **getItem()** trả về **ItemDto** trực tiếp, vì vậy caller chờ cho đến khi response được đọc và giải mã xong.

### Ví dụ với OpenFeign

Spring Cloud OpenFeign cung cấp một cách khai báo client bằng interface. Cách gọi thông thường của OpenFeign là đồng bộ và chặn luồng:

~~~java
@FeignClient(name = "catalog-service")
public interface CatalogFeignClient {

    @GetMapping("/api/items/{id}")
    ItemDto getItem(@PathVariable("id") String itemId);
}
~~~

Khi gọi **getItem()**, thread hiện tại chờ kết quả. Tên trong thuộc tính **name** xác định service ID để tích hợp với cơ chế khám phá dịch vụ và Spring Cloud LoadBalancer. Người gọi không cần tự lấy địa chỉ IP của từng instance.

## 3. Vòng đời của một HTTP request không chặn luồng

Với client không chặn luồng, thread khởi tạo request không phải chờ response. Thư viện I/O quản lý kết nối và thông báo khi có dữ liệu. Trong mô hình reactive của Spring WebFlux, Reactor Netty thường sử dụng một nhóm event loop để xử lý nhiều kết nối I/O.

Luồng xử lý khái quát:

1. Ứng dụng tạo và trả về publisher.
2. Khi publisher được subscribe, WebClient bắt đầu thực thi request.
3. Bộ lọc load balancing phân giải service ID và chọn instance.
4. Event loop quản lý thao tác gửi, nhận dữ liệu mạng. Trong thời gian chờ dữ liệu, event loop có thể xử lý sự kiện của kết nối khác.
5. Khi response đến, publisher phát dữ liệu hoặc lỗi để các toán tử tiếp theo xử lý.

~~~mermaid
sequenceDiagram
    autonumber
    participant App as Ứng dụng
    participant P as Mono / Flux
    participant E as Event loop
    participant LB as Spring Cloud LoadBalancer
    participant S as Service instance

    App->>P: Tạo publisher
    P->>E: Subscribe và bắt đầu request
    E->>LB: Resolve service ID
    LB-->>E: Trả về instance được chọn
    E->>S: Gửi HTTP request
    Note over App,E: Thread gọi được giải phóng để làm việc khác
    S-->>E: HTTP response
    E-->>P: Phát dữ liệu hoặc lỗi
    P-->>App: Chạy bước xử lý tiếp theo
~~~

### Ví dụ với WebClient

Có thể tạo builder dành cho request đến các dịch vụ được cân bằng tải:

~~~java
@Configuration
class ReactiveHttpClientConfiguration {

    @Bean
    @LoadBalanced
    WebClient.Builder loadBalancedWebClientBuilder() {
        return WebClient.builder();
    }

    @Bean
    WebClient catalogWebClient(
            @LoadBalanced WebClient.Builder builder) {
        return builder.build();
    }
}
~~~

Client trả về **Mono<ItemDto>** thay vì đối tượng đã có sẵn:

~~~java
@Service
class ReactiveCatalogClient {

    private final WebClient webClient;

    ReactiveCatalogClient(WebClient catalogWebClient) {
        this.webClient = catalogWebClient;
    }

    public Mono<ItemDto> getItem(String itemId) {
        return webClient.get()
            .uri("http://catalog-service/api/items/{id}", itemId)
            .retrieve()
            .bodyToMono(ItemDto.class);
    }
}
~~~

Phương thức trên mô tả một chuỗi xử lý. Nó chưa cần chặn thread để chờ dữ liệu. Khi được subscribe, WebClient gửi request và phát kết quả khi response sẵn sàng.

Có thể kết hợp nhiều request trong cùng một pipeline. Nếu request thứ hai phụ thuộc dữ liệu của request thứ nhất, dùng **flatMap**:

~~~java
public Mono<OrderView> getOrderView(String orderId) {
    return orderClient.getOrder(orderId)
        .flatMap(order ->
            catalogClient.getItem(order.itemId())
                .map(item -> new OrderView(order, item))
        );
}
~~~

Nếu hai request độc lập và cần cả hai kết quả, có thể kết hợp bằng **Mono.zip**:

~~~java
return Mono.zip(
        customerClient.getCustomer(customerId),
        catalogClient.getItem(itemId)
    )
    .map(tuple ->
        new CheckoutView(tuple.getT1(), tuple.getT2())
    );
~~~

Các toán tử này biểu diễn quan hệ phụ thuộc và cách ghép kết quả. Chúng không tự bảo đảm dịch vụ đích có đủ năng lực xử lý; giới hạn kết nối, giới hạn concurrency và timeout vẫn cần được cấu hình phù hợp.

## 4. So sánh hai mô hình

| Tiêu chí | Chặn luồng | Không chặn luồng |
|---|---|---|
| Thread khi chờ response | Bị giữ lại cho đến khi I/O hoàn tất | Có thể xử lý công việc khác trong khi I/O chờ |
| Kiểu API thường gặp | RestClient, RestTemplate, OpenFeign | WebClient với Mono hoặc Flux |
| Cách nhận kết quả | Giá trị trả về trực tiếp hoặc exception | Publisher, callback hoặc tín hiệu hoàn tất |
| Cách tổ chức mã | Tuần tự, dễ đọc với luồng nghiệp vụ đơn giản | Chuỗi toán tử, cần hiểu composition và reactive |
| Tài nguyên cần quản lý | Thread pool, connection pool, timeout | Event loop, connection pool, concurrency, backpressure |
| Rủi ro thường gặp | Cạn thread khi nhiều request chờ I/O | Chặn event loop hoặc tạo pipeline không giới hạn |
| Trường hợp phù hợp | Ứng dụng imperative, tải vừa phải, nghiệp vụ tuần tự | Nhiều I/O đồng thời, pipeline reactive xuyên suốt |

Không nên kết luận rằng non-blocking luôn nhanh hơn blocking. Với tải nhỏ, client đồng bộ có thể đơn giản và đủ hiệu quả. Với nhiều request cùng chờ các dịch vụ bên ngoài, mô hình không chặn luồng có thể giảm số thread cần duy trì. Hiệu năng thực tế vẫn phụ thuộc độ trễ mạng, thời gian xử lý server, cấu hình connection pool, CPU và giới hạn của các dịch vụ phía sau.

## 5. Spring Cloud LoadBalancer hoạt động ở đâu trong hai mô hình?

Spring Cloud LoadBalancer là cơ chế cân bằng tải phía client. Ứng dụng gọi dịch vụ bằng một service ID logic, chẳng hạn **catalog-service**. Load balancer lấy các **ServiceInstance** từ nguồn cung cấp instance, áp dụng bộ lọc hoặc chính sách lựa chọn rồi trả về instance để client gửi request.

Quá trình khái quát:

~~~mermaid
flowchart TD
    A["Ứng dụng gọi catalog-service"] --> B["HTTP client"]
    B --> C["Spring Cloud LoadBalancer"]
    C --> D["ServiceInstance supplier"]
    D --> E["Danh sách instance khả dụng"]
    E --> F["Chọn instance theo chính sách"]
    F --> G["Thay service ID bằng địa chỉ instance"]
    G --> H["Gửi HTTP request"]
    H --> I["Nhận HTTP response"]
~~~

Điểm quan trọng là load balancing và blocking/non-blocking thuộc hai lớp trách nhiệm khác nhau:

- LoadBalancer giải quyết câu hỏi **gửi request đến instance nào**.
- HTTP client giải quyết câu hỏi **gửi request và quản lý việc chờ response ra sao**.
- **RestClient** và **OpenFeign** cung cấp cách gọi đồng bộ, thường chặn thread.
- **WebClient** hỗ trợ I/O không chặn luồng khi được sử dụng theo reactive pipeline.
- Việc gắn **@LoadBalanced** giúp client phân giải service ID qua Spring Cloud LoadBalancer; annotation này không tự biến một client đồng bộ thành client không chặn luồng.

Vì vậy, cùng một service ID có thể được sử dụng từ các loại client khác nhau nếu ứng dụng cấu hình đúng tích hợp tương ứng. Danh sách instance có thể đến từ service discovery hoặc nguồn cung cấp instance được cấu hình trong ứng dụng. Chính sách chọn instance và bộ lọc instance ảnh hưởng đến đích của request, còn mô hình thread của client vẫn do API và thư viện I/O quyết định.

## 6. Timeout, lỗi và retry trong cả hai mô hình

Không chặn luồng không loại bỏ độ trễ mạng. Một request có thể chờ rất lâu vì DNS, kết nối TCP, dịch vụ quá tải hoặc server không gửi response. Do đó cả hai mô hình đều cần giới hạn thời gian chờ.

Các loại timeout thường cần xem xét:

- **Connect timeout**: thời gian tối đa để thiết lập kết nối đến instance.
- **Response timeout**: thời gian tối đa chờ response hoặc dữ liệu phản hồi theo cấu hình của HTTP client.
- **Connection-pool acquire timeout**: thời gian tối đa chờ lấy một kết nối từ pool khi pool đã bận.
- **Deadline của nghiệp vụ**: tổng thời gian tối đa mà luồng nghiệp vụ cho phép một thao tác hoàn tất, bao gồm nhiều request nối tiếp nhau.

Tên thuộc tính và cách cấu hình cụ thể phụ thuộc HTTP client bên dưới và phiên bản Spring. Cần cấu hình timeout cho từng client thực tế đang sử dụng, đồng thời bảo đảm tổng deadline của nghiệp vụ lớn hơn hoặc bằng ngân sách thời gian dành cho các bước con.

### Xử lý lỗi response

Với WebClient, có thể ánh xạ HTTP status thành lỗi của ứng dụng:

~~~java
public Mono<ItemDto> getItem(String itemId) {
    return webClient.get()
        .uri("http://catalog-service/api/items/{id}", itemId)
        .retrieve()
        .onStatus(
            status -> status.value() == 404,
            response -> Mono.error(
                new ItemNotFoundException(itemId)
            )
        )
        .bodyToMono(ItemDto.class);
}
~~~

Với RestClient, OpenFeign hoặc WebClient, ứng dụng đều cần phân biệt lỗi kết nối, timeout, lỗi HTTP từ server và lỗi giải mã response. Các lỗi này có ý nghĩa khác nhau khi quyết định có retry hay trả lỗi cho caller.

### Retry cần có giới hạn

Retry có thể hữu ích khi một instance tạm thời không sẵn sàng hoặc kết nối gặp lỗi nhất thời. Tuy nhiên, retry làm tăng số request thực tế. Nếu mọi client cùng retry khi dịch vụ đang quá tải, lượng request tăng thêm có thể khiến sự cố nghiêm trọng hơn.

Một chính sách retry nên:

- Giới hạn số lần thử và tổng thời gian retry.
- Chỉ retry lỗi có khả năng hồi phục, chẳng hạn một số lỗi kết nối hoặc lỗi server tạm thời.
- Ưu tiên thao tác idempotent. Với thao tác ghi dữ liệu, cần cơ chế idempotency key hoặc bảo đảm nghiệp vụ tương đương trước khi retry.
- Dùng backoff và jitter để tránh nhiều client gửi lại cùng thời điểm.
- Phối hợp retry của HTTP client với retry của Spring Cloud LoadBalancer để tránh nhân số lần thử ngoài dự kiến.

Retry không đồng nghĩa chắc chắn sẽ chuyển sang instance khác. Việc chọn instance cho lần thử tiếp theo phụ thuộc cấu hình retry và chính sách load balancing. Cần kiểm tra hành vi thực tế của phiên bản và cấu hình đang chạy.

## 7. Những lỗi thường gặp khi dùng WebClient

### Gọi block() trong pipeline reactive

~~~java
ItemDto item = webClient.get()
    .uri("http://catalog-service/api/items/{id}", itemId)
    .retrieve()
    .bodyToMono(ItemDto.class)
    .block();
~~~

**block()** chờ publisher hoàn tất và giữ thread gọi lại. Nếu được gọi trên event loop, nó có thể làm event loop không xử lý được các kết nối khác hoặc gây lỗi trong môi trường Reactor. Khi đã chọn WebClient cho pipeline reactive, nên trả về **Mono** hoặc **Flux** và nối các bước bằng toán tử reactive. Chỉ chuyển sang blocking tại ranh giới imperative có chủ đích, trên thread phù hợp.

### Gọi subscribe() bên trong service rồi trả kết quả ngay

~~~java
public void refreshItem(String itemId) {
    webClient.get()
        .uri("http://catalog-service/api/items/{id}", itemId)
        .retrieve()
        .bodyToMono(ItemDto.class)
        .subscribe(this::updateCache);
}
~~~

Cách làm này tạo một luồng xử lý tách rời khỏi vòng đời của phương thức. Caller không biết khi nào công việc hoàn tất, khó nhận lỗi, khó phối hợp transaction và khó kiểm soát việc hủy request. Với nghiệp vụ cần kết quả, hãy trả publisher để caller kết hợp và quyết định thời điểm subscribe. Chỉ dùng fire-and-forget khi nghiệp vụ chấp nhận rõ ràng việc xử lý độc lập và đã có cơ chế theo dõi lỗi phù hợp.

### Bọc lời gọi blocking trong Mono nhưng không đổi cách thực thi I/O

~~~java
Mono.fromCallable(() -> restClient.get()
        .uri("http://catalog-service/api/items/{id}", itemId)
        .retrieve()
        .body(ItemDto.class));
~~~

Đoạn mã trên tạo publisher từ một callable, nhưng thao tác RestClient bên trong vẫn là blocking khi callable được thực thi. Nếu cần tích hợp tạm thời một thư viện blocking vào ứng dụng reactive, phải chuyển công việc sang scheduler dành cho tác vụ blocking, thường là **Schedulers.boundedElastic()**, và giới hạn tải phù hợp:

~~~java
Mono.fromCallable(() -> legacyClient.getItem(itemId))
    .subscribeOn(Schedulers.boundedElastic());
~~~

Đây là biện pháp cô lập phần blocking, không biến nó thành I/O không chặn luồng. Nếu phần lớn chuỗi giao tiếp đều blocking, nên cân nhắc giữ mô hình imperative xuyên suốt thay vì tạo một pipeline reactive chỉ để bọc các lời gọi blocking.

### Chặn event loop bằng tác vụ CPU hoặc I/O blocking

Event loop cần quay lại nhanh để xử lý sự kiện mạng. Không nên thực hiện truy vấn JDBC blocking, gọi API blocking, chờ lock lâu hoặc tính toán CPU nặng trực tiếp trên event loop. Các công việc đó cần được chuyển sang scheduler hoặc executor phù hợp, có giới hạn concurrency và có giám sát.

### Tạo concurrency không giới hạn

Non-blocking giúp quản lý nhiều thao tác I/O đồng thời, nhưng không có nghĩa ứng dụng nên gửi số lượng request không giới hạn. Quá nhiều request có thể làm cạn connection pool, tăng bộ nhớ giữ response, gây quá tải dịch vụ đích và tạo hàng đợi lớn. Hãy giới hạn concurrency, áp dụng backpressure khi phù hợp và theo dõi số request đang hoạt động.

## 8. Chọn mô hình nào cho dịch vụ?

Chọn client đồng bộ như RestClient hoặc OpenFeign khi mã nghiệp vụ chủ yếu imperative, số lượng request đồng thời nằm trong giới hạn thread pool, và tính đơn giản của luồng xử lý có giá trị cao. Đây cũng thường là lựa chọn dễ tích hợp với các thư viện đồng bộ như JDBC và transaction imperative.

Chọn WebClient theo mô hình non-blocking khi ứng dụng cần xử lý nhiều thao tác I/O đồng thời, có thể duy trì pipeline reactive từ controller qua service đến HTTP client, và đội ngũ có khả năng vận hành Reactor/WebFlux. Lợi ích sẽ giảm đáng kể nếu mỗi bước reactive lại gọi một API blocking hoặc thường xuyên dùng **block()**.

Trước khi quyết định, hãy trả lời các câu hỏi sau:

1. Một request nghiệp vụ gọi bao nhiêu dịch vụ và các lời gọi phụ thuộc nhau hay độc lập?
2. Độ trễ trung bình và độ trễ ở percentile cao của các dịch vụ là bao nhiêu?
3. Số request đồng thời dự kiến là bao nhiêu, và thread pool hoặc connection pool hiện có giới hạn ra sao?
4. Các thư viện truy cập database, cache và message broker đang dùng blocking hay non-blocking?
5. Ứng dụng có cần backpressure, hủy request và ghép nhiều luồng dữ liệu hay không?
6. Hệ thống đã có timeout, retry, giới hạn concurrency và metric để phát hiện quá tải chưa?

Dù chọn mô hình nào, hãy gọi dịch vụ bằng service ID để Spring Cloud LoadBalancer có thể chọn instance theo cấu hình, đặt timeout rõ ràng và quan sát được request. Khi kiểm thử tải, cần đo cả throughput, latency, số thread hoạt động, connection pool, tỷ lệ timeout và phân bố request giữa các instance. Những số liệu này cho biết mô hình đang sử dụng tài nguyên ra sao và load balancer có phân phối request như mong đợi hay không.

