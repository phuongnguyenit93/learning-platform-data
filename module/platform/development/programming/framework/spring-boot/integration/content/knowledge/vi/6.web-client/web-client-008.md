# Giới hạn thời gian, hủy đăng ký và xử lý phản hồi theo luồng

## 1. Bối cảnh và mục tiêu

Trong module **SPRING_BOOT_INTEGRATION**, ứng dụng Spring Boot tích hợp với các hệ thống khác thông qua HTTP client, cơ sở dữ liệu, cache, message broker và adapter của Spring Integration. **WebClient** là HTTP client dựa trên Reactive Streams, phù hợp khi cần ghép nhiều lời gọi I/O bất đồng bộ, nhận dữ liệu theo luồng hoặc chuyển tiếp dữ liệu mà không giữ toàn bộ response trong bộ nhớ. Khi sử dụng WebClient, quản lý cấu hình, hợp đồng dữ liệu, giao dịch, lỗi, xử lý trùng lặp, kiểm thử và quan sát luồng tích hợp vẫn là trách nhiệm thiết kế của ứng dụng.

Chủ đề của bài thuộc chương **WebClient**: **giới hạn thời gian, hủy đăng ký và xử lý phản hồi theo luồng**. Ba khái niệm liên quan nhau nhưng không thể thay thế:

- **Timeout**: giới hạn một pha mạng, khoảng chờ tín hiệu hoặc thời gian toàn thao tác; hết hạn có thể dẫn đến tín hiệu lỗi và cancellation.
- **Cancellation**: downstream báo không cần dữ liệu từ một subscription nữa; upstream có thể dừng đọc và giải phóng tài nguyên theo khả năng thực tế.
- **Streaming**: nhận nhiều phần dữ liệu liên tiếp từ response, có thể xử lý ngay khi mỗi phần được giải mã thay vì đợi toàn bộ body.

Sau bài này, bạn cần:

1. Phân biệt **connect timeout**, **response timeout**, **pool acquire timeout**, **Mono.timeout** và **Flux.timeout**.
2. Hiểu vì sao WebClient chỉ bắt đầu gửi request khi pipeline được subscribe và cách cancellation lan truyền.
3. Xử lý phản hồi JSON thường, NDJSON, Server-Sent Events (SSE) và tải file lớn.
4. Đặt giới hạn bộ nhớ, số phần tử, backpressure và deadline phù hợp với hợp đồng upstream.
5. Giải thích vì sao hủy request không chắc đã hủy giao dịch trên server; thiết kế retry/idempotency khi cần.
6. Kiểm thử được timeout, hủy luồng, lỗi giữa dòng và giải phóng tài nguyên.

## 2. Mô hình thực thi của WebClient

Một lời gọi như **client.get().retrieve().bodyToMono(...)** tạo một mô tả xử lý bất đồng bộ. Với publisher cold thông thường của WebClient, request HTTP thực sự bắt đầu khi có subscription. **Mono** phát 0 hoặc 1 phần tử rồi kết thúc; **Flux** phát từ 0 đến nhiều phần tử.

~~~mermaid
flowchart TD
    A["Application service / HTTP controller"] --> B["WebClient request specification"]
    B --> C["Mono hoặc Flux chưa subscribe"]
    C -->|"Subscriber đăng ký"| D["Client connector / HTTP transport"]
    D --> E["DNS, pool, TCP, TLS, gửi request"]
    E --> F["Nhận status, headers và body"]
    F --> G{"Kiểu giải mã"}
    G -->|"bodyToMono"| H["Một object hoặc kết quả tổng hợp"]
    G -->|"bodyToFlux"| I["Nhiều object / chunk"]
    H --> J["onNext? → onComplete"]
    I --> J
    F -->|"Lỗi"| K["onError"]
    J --> L["Release tài nguyên"]
    K --> L
    C -->|"cancel / timeout / take"| M["Hủy subscription"]
    M --> L
~~~

Các tín hiệu chính của Reactive Streams:

| Tín hiệu | Ý nghĩa |
| --- | --- |
| **onSubscribe** | Downstream nhận subscription và có thể yêu cầu dữ liệu |
| **request(n)** | Downstream thể hiện nhu cầu tối đa n phần tử trong giao thức Reactive Streams |
| **onNext(value)** | Upstream phát một phần tử dữ liệu |
| **onComplete** | Upstream kết thúc thành công |
| **onError(error)** | Upstream kết thúc với lỗi |
| **cancel()** | Downstream không muốn nhận tiếp; đây là điều khiển subscription, không phải terminal signal do upstream phát |

**onComplete, onError và cancel có ngữ nghĩa khác nhau**. Khi consumer hủy stream trước khi nhận hết, không nên ghi metric “download thành công” chỉ vì không thấy exception. Trong WebFlux controller, thông thường nên **return Mono/Flux** để framework quản lý subscription, thay vì tự **subscribe()** bên trong service/controller.

Một ví dụ:

~~~java
public record StockSnapshot(String sku, int available) {}

public Mono<StockSnapshot> findStock(String sku) {
    return stockWebClient.get()
            .uri("/inventory/{sku}", sku)
            .retrieve()
            .bodyToMono(StockSnapshot.class);
}
~~~

Nếu gọi **findStock("SKU-01")** rồi bỏ qua giá trị trả về, request có thể không được thực thi. Nếu dùng **.block()** trên một pipeline reactive, ứng dụng chuyển sang đợi đồng bộ; điều này có thể chặn luồng event loop và gây lỗi tại runtime trong WebFlux. Chỉ block ở ranh giới đồng bộ được thiết kế rõ ràng, không block tùy tiện trong handler reactive.

## 3. Cấu hình transport: nơi đặt timeout mạng

WebClient là API cấp cao; TCP, TLS, pool và cách đọc socket phụ thuộc **ClientHttpConnector**. Ví dụ dưới đây dùng **Reactor Netty**, một lựa chọn thường gặp với Spring Boot và WebFlux.

### 3.1. Dependency và bean

Với dự án Maven quản lý phiên bản qua Spring Boot parent/BOM:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-webflux</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

Spring MVC vẫn có thể sử dụng WebClient làm HTTP client; thêm WebFlux starter **không tự động biến tất cả controller MVC thành reactive**. Nếu dự án không cần toàn bộ starter, có thể chọn dependency WebClient và transport phù hợp. Luôn kiểm tra dependency management của phiên bản Spring Boot thực tế.

Ví dụ cấu hình client cho truy vấn tồn kho (các import Java/Spring được lược bỏ trong ví dụ để nhấn mạnh API):

~~~java
@Configuration(proxyBeanMethods = false)
public class StockClientConfiguration {

    @Bean
    WebClient stockWebClient(
            WebClient.Builder builder,
            ReactorResourceFactory reactorResources) {

        HttpClient nettyClient = HttpClient
                .create(reactorResources.getConnectionProvider())
                .runOn(reactorResources.getLoopResources())
                .option(ChannelOption.CONNECT_TIMEOUT_MILLIS, 800)
                .responseTimeout(Duration.ofSeconds(4));

        return builder
                .baseUrl("https://inventory.example.internal")
                .clientConnector(new ReactorClientHttpConnector(nettyClient))
                .codecs(codecs -> codecs.defaultCodecs()
                        .maxInMemorySize(512 * 1024))
                .build();
    }
}
~~~

Các import chính gồm **reactor.netty.http.client.HttpClient**, **io.netty.channel.ChannelOption**, **org.springframework.http.client.ReactorResourceFactory**, **org.springframework.http.client.reactive.ReactorClientHttpConnector**, **org.springframework.web.reactive.function.client.WebClient** và **java.time.Duration**.

Ý nghĩa:

- **CONNECT_TIMEOUT_MILLIS = 800**: giới hạn pha thiết lập kết nối TCP theo Netty.
- **responseTimeout(4 giây)**: cấu hình timeout response ở tầng Reactor Netty; chi tiết cần hiểu theo **khoảng không có thao tác đọc mạng** khi nhận response, không nên coi là deadline tuyệt đối từ đầu đến cuối của cả nghiệp vụ.
- **maxInMemorySize(512 KiB)**: đặt giới hạn bộ đệm giải mã của các codec; không phải giới hạn tổng dung lượng truyền trên mạng.
- **WebClient.Builder** do Boot cung cấp giúp tái sử dụng các tùy biến client mà Boot và ứng dụng đã áp dụng, ví dụ observation, connector customizer hoặc filter. Khi ghi đè connector, cần kiểm tra những tùy biến còn phù hợp.
- **ReactorResourceFactory** tái sử dụng pool và event loop do Spring quản lý trong trường hợp Boot cấu hình Reactor Netty. Nếu ứng dụng tự sở hữu **ConnectionProvider/LoopResources**, phải quản lý vòng đời và đóng chúng đúng cách.

Các giá trị trên chỉ để minh họa. Cần xác định theo SLO, phân vị độ trễ, năng lực downstream và giới hạn tài nguyên. Đặc biệt với kết nối **SSE lâu dài**, việc áp cùng response timeout vài giây cho mọi request có thể làm ngắt stream hợp lệ giữa hai sự kiện.

### 3.2. Các loại thời gian chờ

~~~text
Chờ mượn connection từ pool
   → DNS
   → TCP connect
   → TLS handshake
   → gửi headers/body
   → chờ response headers
   → đọc response chunks
   → decode / xử lý nghiệp vụ
~~~

| Timeout / giới hạn | Phạm vi | Cấu hình thông thường |
| --- | --- | --- |
| **Pending acquire timeout** | Thời gian chờ một connection rảnh trong pool | Reactor Netty ConnectionProvider |
| **DNS resolve timeout** | Thời gian phân giải hostname | DNS resolver/transport |
| **Connect timeout** | Mở TCP tới upstream | ChannelOption.CONNECT_TIMEOUT_MILLIS |
| **TLS handshake timeout** | Bắt tay bảo mật | TLS/SSL configuration của client |
| **Read/write idle timeout** | Không có tiến triển đọc/ghi trong một khoảng nhất định | Netty ReadTimeoutHandler/WriteTimeoutHandler khi thích hợp |
| **Response timeout** | Chính sách chờ phản hồi ở transport | Reactor Netty HttpClient.responseTimeout |
| **Pipeline timeout** | Khoảng chờ tín hiệu của Mono/Flux | Reactor timeout(Duration) |
| **End-to-end deadline** | Tổng ngân sách cho nghiệp vụ gồm nhiều request, retry, backoff | Service/orchestration và deadline truyền xuống các tầng |

Ví dụ **responseTimeout** của Netty khác với **Mono.timeout**: một response có thể đang tải nhiều chunk trong thời gian dài mà không vi phạm timeout giữa các lần đọc; trong khi **Mono<Void>.timeout(30 giây)** có thể báo lỗi nếu tác vụ hoàn tất toàn bộ quá 30 giây.

**Đừng áp đặt một phép cộng timeout đơn giản như cam kết độ trễ.** Nếu service retry ba lần, mỗi lần response timeout hai giây, còn chờ pool và backoff, tổng thời gian xử lý có thể vượt sáu giây. Phải đặt ngân sách tổng ở tầng điều phối.

### 3.3. Timeout dành riêng cho một request

Khi chỉ một endpoint cho phép response lâu hơn (ví dụ báo cáo), có thể cấu hình transport cho request ấy khi dùng Reactor Netty:

~~~java
Mono<ReportStatus> status = stockWebClient.get()
        .uri("/reports/{id}/status", reportId)
        .httpRequest(request -> {
            HttpClientRequest nativeRequest = request.getNativeRequest();
            nativeRequest.responseTimeout(Duration.ofSeconds(12));
        })
        .retrieve()
        .bodyToMono(ReportStatus.class);
~~~

**HttpClientRequest** là loại từ **reactor.netty.http.client**. Đoạn mã phụ thuộc Reactor Netty connector, không phải API độc lập với mọi transport của WebClient; với JDK/Jetty/Apache connector phải tìm cách cấu hình tương ứng. Không đặt connection timeout toàn hệ thống bằng cách đoán request timeout này.

## 4. Mono.timeout và Flux.timeout khác nhau

### 4.1. Mono: chờ một kết quả

Ví dụ gọi dịch vụ tồn kho với một deadline ở cấp lời gọi:

~~~java
public Mono<StockSnapshot> fetchSnapshot(String sku) {
    return stockWebClient.get()
            .uri("/inventory/{sku}", sku)
            .retrieve()
            .bodyToMono(StockSnapshot.class)
            .timeout(Duration.ofSeconds(3))
            .onErrorMap(
                    TimeoutException.class,
                    ex -> new InventoryCallTimedOutException(
                            "inventory request exceeded 3 seconds", ex));
}

public final class InventoryCallTimedOutException
        extends RuntimeException {
    public InventoryCallTimedOutException(
            String message, Throwable cause) {
        super(message, cause);
    }
}
~~~

**Mono.timeout(3 giây)** bắt đầu đếm từ khi subscribe. Nếu không thấy **onNext**, **onComplete** hay tín hiệu kết thúc phù hợp trong thời hạn, Reactor tạo lỗi timeout và hủy subscription upstream. Với WebClient nhận một JSON object, điều này thường bao gồm thời gian chuẩn bị request, gửi/nhận và giải mã object.

Tuy nhiên:

- Nếu response lớn hoặc công việc downstream nằm ngoài Mono này, deadline không tự bao phủ những bước thực hiện sau đó.
- Lỗi từ **Reactor Netty responseTimeout** có thể mang kiểu exception khác với **java.util.concurrent.TimeoutException** của operator Reactor; **onErrorMap(TimeoutException.class, ...)** không bắt mọi lỗi timeout transport.
- Nếu đặt **timeout** trước **retryWhen**, mỗi lượt retry có timeout riêng; đặt bên ngoài chuỗi **retryWhen** sẽ giới hạn tổng thời gian của chuỗi đó. Thiết kế thứ tự operator theo nghĩa nghiệp vụ mong muốn.

### 4.2. Flux: chờ phần tử đầu tiên và khoảng cách giữa các phần tử

~~~java
Flux<PriceChanged> updates = priceWebClient.get()
        .uri("/prices/updates")
        .accept(MediaType.APPLICATION_NDJSON)
        .retrieve()
        .bodyToFlux(PriceChanged.class)
        .timeout(Duration.ofSeconds(15));
~~~

Với **Flux.timeout(Duration)**, timeout áp dụng khi chờ phần tử đầu tiên và **giữa các phần tử onNext liên tiếp**. Mỗi lần có phần tử mới, đồng hồ chờ phần tử tiếp theo được làm mới. Vì vậy, stream kéo dài hàng giờ nhưng đều có bản tin mỗi 10 giây có thể không bao giờ chạm timeout 15 giây.

Nếu mục tiêu là **giới hạn tổng thời gian nhận đủ một stream hữu hạn**, cần đếm đến **onComplete**:

~~~java
Mono<Long> totalItems = priceWebClient.get()
        .uri("/prices/export")
        .accept(MediaType.APPLICATION_NDJSON)
        .retrieve()
        .bodyToFlux(PriceChanged.class)
        .count()
        .timeout(Duration.ofSeconds(30));
~~~

**count()** chỉ hoàn tất khi stream hoàn tất, vì vậy **Mono.timeout** bên ngoài bao quát thời gian chờ hoàn tất. Đây là lựa chọn thích hợp cho stream hữu hạn; với SSE vô hạn, nó sẽ chỉ kết thúc khi có timeout chứ không có kết quả tổng tự nhiên.

Nếu muốn chủ động giới hạn **thời lượng đăng ký** cho một stream lâu dài, **take(Duration.ofMinutes(2))** có thể kết thúc stream sau khoảng thời gian đó bằng **onComplete** và cancel upstream. Phải ghi rõ đây là **dừng theo chính sách**, tránh nhầm việc hoàn tất do take với đã nhận hết dữ liệu.

### 4.3. Các kiểu hết hạn thời gian và kết quả quan sát

| Tình huống | Tín hiệu có thể quan sát | Điều chắc chắn? |
| --- | --- | --- |
| Không kết nối kịp | Lỗi transport/Netty | Không có HTTP response hợp lệ; không thể suy ra status code |
| Có TCP nhưng response im lặng quá lâu | Lỗi response/read timeout | Không xác nhận được kết quả xử lý tại server |
| Mono.timeout hết hạn | Reactor TimeoutException, upstream bị cancel | Caller ngừng chờ; server có thể vẫn xử lý |
| Flux.timeout hết hạn giữa hai event | Reactor TimeoutException, stream bị cancel | Stream không phát event đúng chu kỳ mong đợi |
| Consumer chủ động dispose | Tín hiệu cancel tại những operator quan sát cancellation | Không tự tạo onError hoặc bảo đảm server rollback |
| Upstream đóng stream bình thường | onComplete | Stream kết thúc theo giao thức; có đủ dữ liệu hay không còn tùy hợp đồng |

## 5. Cancellation: điều gì xảy ra khi không ai cần response nữa?

Trong Reactive Streams, subscriber có thể gọi **cancel()** để báo dừng nhu cầu. Reactor thường truyền tín hiệu này ngược upstream; WebClient/connector sẽ cố dừng nhận thêm dữ liệu và giải phóng tài nguyên liên quan. Cancellation có thể xuất phát từ:

- Browser/client đóng kết nối WebFlux trước khi nhận hết response được proxy.
- **take(n)** lấy đủ n phần tử rồi không cần phần còn lại.
- **timeout(...)** chuyển thành onError và cancel upstream.
- **switchMap** hủy luồng cũ khi có lựa chọn mới.
- Một **Disposable.dispose()** được gọi từ subscription do ứng dụng tạo.

Ví dụ minh họa explicit subscription trong một tác vụ độc lập:

~~~java
Disposable subscription = priceWebClient.get()
        .uri("/prices/updates")
        .retrieve()
        .bodyToFlux(PriceChanged.class)
        .subscribe(
                price -> processPrice(price),
                error -> recordFailure(error));

// Khi ứng dụng không còn cần luồng này:
subscription.dispose();
~~~

**Đây là ví dụ về quyền hủy khi ứng dụng tự quản lý subscription.** Trong một WebFlux controller hoặc method service được gọi từ pipeline, nên **return Flux/Mono**, không tự subscribe rồi để subscription sống ngoài vòng đời request.

### 5.1. Quan sát cancel khác với error

~~~java
Flux<PriceChanged> updates = priceWebClient.get()
        .uri("/prices/updates")
        .retrieve()
        .bodyToFlux(PriceChanged.class)
        .doFinally(signal -> {
            if (signal == SignalType.CANCEL) {
                metrics.recordStreamCancellation("prices");
            } else if (signal == SignalType.ON_ERROR) {
                metrics.recordStreamFailure("prices");
            } else if (signal == SignalType.ON_COMPLETE) {
                metrics.recordStreamCompleted("prices");
            }
        });
~~~

**SignalType** đến từ **reactor.core.publisher.SignalType**. **metrics** là thành phần minh họa do ứng dụng định nghĩa, không phải API có sẵn của Spring. **doFinally** chạy khi pipeline kết thúc do complete, error hoặc cancel; **doOnError** chỉ thấy lỗi, còn **doOnTerminate** không thay thế được quan sát cancel.

Với đường timeout do Reactor tạo ra, một operator phía **trên timeout** có thể thấy **CANCEL**, còn subscriber phía **dưới timeout** thấy **onError(TimeoutException)**. Để không đếm một sự cố thành cả “hủy người dùng” và “timeout”, phải xác định chính xác điểm đo và nhãn nguồn cancel/timeout.

### 5.2. Cancel là yêu cầu dừng, không phải giao dịch rollback

Giả sử gọi:

~~~java
Mono<PaymentResult> paid = paymentWebClient.post()
        .uri("/payments")
        .bodyValue(command)
        .retrieve()
        .bodyToMono(PaymentResult.class)
        .timeout(Duration.ofSeconds(3));
~~~

Nếu client timeout, lệnh POST có thể đã được gửi hoàn toàn và payment service đã commit trước khi response về. Việc cancel subscription **không đảm bảo remote server dừng xử lý, xóa dữ liệu hoặc rollback transaction**.

Do đó:

1. Với thao tác tạo/gửi tiền/ghi đơn hàng, dùng **idempotency key**, request ID hoặc cơ chế đối soát trạng thái.
2. Khi timeout, không tự động retry POST trừ khi API có hợp đồng xử lý trùng rõ ràng.
3. Nếu cần hủy nghiệp vụ thật, phải có **cancellation protocol riêng** ở server, chứ không chỉ hủy luồng HTTP từ client.
4. Nếu message broker retry sau timeout, idempotency phải áp dụng xuyên các lần redelivery.

## 6. Nhận phản hồi theo luồng: bodyToMono và bodyToFlux

### 6.1. Chọn kiểu kết quả theo định dạng dữ liệu

| Hợp đồng HTTP upstream | API đọc thường phù hợp | Lưu ý |
| --- | --- | --- |
| Một JSON object nhỏ | **bodyToMono(MyDto.class)** | Một kết quả, decode đầy đủ |
| JSON array hữu hạn | **bodyToFlux(MyDto.class)** hoặc **bodyToMono(List<MyDto>)** tùy codec/hợp đồng | Với array lớn, xem hỗ trợ streaming thực tế của codec và kích thước phần tử |
| **application/x-ndjson** | **bodyToFlux(MyDto.class)** | Mỗi JSON object được phân cách theo dòng và server cần flush |
| **text/event-stream (SSE)** | **bodyToFlux(ServerSentEvent<T>)** | Kết nối dài hạn; có ID event và khả năng resume nếu API hỗ trợ |
| File/binary lớn | **bodyToFlux(DataBuffer.class)** hoặc **DataBufferUtils.write** | Cần chính sách quản lý byte buffer, file chưa hoàn chỉnh và cancellation |
| Không cần body | **toBodilessEntity()** hoặc **bodyToMono(Void.class)** theo mục tiêu | Đừng bỏ quên body khi tự thao tác ClientResponse |

**Flux không đồng nghĩa với streaming ngay lập tức** nếu upstream chỉ gửi dữ liệu sau khi chuẩn bị xong toàn bộ response hoặc proxy trung gian đang buffer. Phải xác minh content type, cách codec xử lý, khả năng flush và proxy HTTP từ thực tế.

### 6.2. NDJSON: xử lý từng bản ghi

Giả sử downstream trả:

~~~http
HTTP/1.1 200 OK
Content-Type: application/x-ndjson

{"sku":"A-1","price":100}
{"sku":"B-2","price":250}
{"sku":"C-3","price":180}
~~~

DTO:

~~~java
public record PriceChanged(String sku, int price) {}
~~~

Client:

~~~java
public Flux<PriceChanged> streamPriceChanges() {
    return priceWebClient.get()
            .uri("/prices/changes")
            .accept(MediaType.APPLICATION_NDJSON)
            .retrieve()
            .bodyToFlux(PriceChanged.class)
            .limitRate(64)
            .doOnNext(change -> metrics.recordReceived("price-change"))
            .doFinally(signal -> metrics.recordTerminal(
                    "price-change", signal.name()));
}
~~~

**limitRate(64)** điều tiết yêu cầu phần tử xuống upstream ở Reactor. Nó **không bảo đảm** network server hoặc mọi proxy HTTP lập tức giảm tốc tương ứng: vẫn có buffer tại OS, connector, codec hoặc upstream. Phải theo dõi memory, tốc độ producer và số consumer đồng thời.

**Không dùng collectList() vô điều kiện** với stream chưa biết độ dài. Điều đó giữ tất cả item trong memory và làm mất lợi ích xử lý từng phần. Nếu phải gom dữ liệu, dùng **buffer(100)**, batch có giới hạn, phân trang hoặc cơ chế backpressure cụ thể.

### 6.3. SSE: dữ liệu mở lâu dài và sự kiện có ID

SSE thường dùng **text/event-stream**; upstream có thể phát:

~~~text
id: 91
event: order-progress
data: {"orderId":"O-10","state":"PACKING"}

id: 92
event: order-progress
data: {"orderId":"O-10","state":"SHIPPED"}

~~~

Client:

~~~java
public record OrderProgress(String orderId, String state) {}

public Flux<ServerSentEvent<OrderProgress>> followOrder(String orderId) {
    return orderWebClient.get()
            .uri("/orders/{id}/events", orderId)
            .accept(MediaType.TEXT_EVENT_STREAM)
            .retrieve()
            .bodyToFlux(
                    new ParameterizedTypeReference<
                            ServerSentEvent<OrderProgress>>() {})
            .timeout(Duration.ofSeconds(45));
}
~~~

**ServerSentEvent** thuộc **org.springframework.http.codec**; **ParameterizedTypeReference** thuộc **org.springframework.core**. Đọc kiểu generic giúp giữ metadata của SSE như **id**, **event** và **data**.

Với stream hợp lệ có thể im lặng hơn 45 giây, cấu hình trên sẽ hủy subscription không cần thiết. Hãy thống nhất chính sách heartbeat và khoảng chờ với upstream; nếu muốn tiếp tục từ vị trí cũ sau reconnect, API phải hỗ trợ event ID/Last-Event-ID hoặc cursor tương ứng. **Retry một SSE stream không tự động khôi phục đúng offset**, và phần tử trước reconnect có thể được phát lại.

Một lưu ý đặc biệt: SSE comment-only heartbeat ở tầng byte **không nhất thiết trở thành onNext** trong **Flux<ServerSentEvent<T>>**. Vì vậy, timeout của Flux đo khoảng cách giữa các event được decoder phát ra; nó không phải phép đo socket activity. Cấu hình timeout transport phải phù hợp với heartbeat thực tế.

## 7. Phản hồi tùy theo HTTP status với exchangeToFlux

**retrieve()** có hành vi mặc định: HTTP 4xx/5xx tạo **WebClientResponseException**, có thể tùy chỉnh bằng **onStatus**. Khi muốn quyết định decode khác nhau dựa trên status, dùng **exchangeToMono** hoặc **exchangeToFlux**.

~~~java
public Flux<PriceChanged> fetchChanges() {
    return priceWebClient.get()
            .uri("/prices/changes")
            .exchangeToFlux(response -> {
                if (response.statusCode().is2xxSuccessful()) {
                    return response.bodyToFlux(PriceChanged.class);
                }
                return response.createException()
                        .flatMapMany(ex -> Flux.error(ex));
            });
}
~~~

**createException()** đọc thông tin lỗi để tạo WebClientResponseException theo cơ chế Spring. Trong những trường hợp custom khác, cần có chiến lược xử lý hoặc giải phóng response body. Với **exchangeToMono/Flux**, Spring kiểm tra và giải phóng body chưa được tiêu thụ khi publisher trả về kết thúc; **ClientResponse không được giữ lại để giải mã tùy ý sau ranh giới callback**.

Đối với lỗi status cụ thể:

~~~java
Mono<StockSnapshot> result = stockWebClient.get()
        .uri("/inventory/{sku}", sku)
        .retrieve()
        .onStatus(
                status -> status.value() == 429,
                response -> response.createException())
        .bodyToMono(StockSnapshot.class);
~~~

Đây vẫn là lỗi HTTP status, **khác với timeout mạng và lỗi decode JSON**. Không nên bắt mọi Exception rồi trả **Mono.empty()**: như thế sẽ đánh đồng “SKU không có” với “upstream lỗi” và làm sai quyết định nghiệp vụ.

## 8. Streaming file lớn và DataBuffer

Đối với file lớn, phương pháp **bodyToMono(byte[].class)** có thể phải giữ toàn bộ nội dung trong bộ nhớ và vướng giới hạn codec. Nên xử lý **DataBuffer** theo chunk và ghi ra file đích.

Ví dụ tải về một file tạm để ứng dụng xử lý sau khi hoàn tất:

~~~java
public Mono<Path> downloadExport(String exportId, Path temporaryFile) {
    return exportWebClient.get()
            .uri("/exports/{id}", exportId)
            .exchangeToMono(response -> {
                if (!response.statusCode().is2xxSuccessful()) {
                    return response.createException()
                            .flatMap(ex -> Mono.<Path>error(ex));
                }

                Flux<DataBuffer> body =
                        response.bodyToFlux(DataBuffer.class);

                return DataBufferUtils.write(
                                body,
                                temporaryFile,
                                StandardOpenOption.CREATE,
                                StandardOpenOption.TRUNCATE_EXISTING,
                                StandardOpenOption.WRITE)
                        .thenReturn(temporaryFile);
            })
            .timeout(Duration.ofSeconds(40));
}
~~~

Ví dụ cần import **Path**, **StandardOpenOption**, **DataBuffer** và **DataBufferUtils**; giả định thư mục chứa file tạm đã tồn tại và ứng dụng có quyền ghi. **DataBufferUtils.write(Publisher<DataBuffer>, Path, ...)** cho phép ghi stream vào file và trả **Mono<Void>** khi hoàn tất; tránh tự gom toàn bộ body thành một byte array.

Trong ứng dụng thật:

1. Ghi vào **temporaryFile** riêng cho từng request, kiểm soát quyền truy cập và dung lượng ổ đĩa.
2. Chỉ đánh dấu file **COMPLETED** và chuyển/rename thành file chính thức **sau khi toàn bộ download thành công**; nếu cancel, timeout hoặc lỗi giữa chừng, file có thể chỉ chứa một phần dữ liệu.
3. Lên lịch xóa/đối soát file tạm sau lỗi hoặc cancellation, tránh thực hiện file I/O blocking ngay trên event loop; không giả định **doOnError** được gọi cho hủy chủ động.
4. Nếu sử dụng các overload **DataBufferUtils.write** trả **Flux<DataBuffer>** hoặc tự thao tác raw pooled DataBuffer, phải xem quyền sở hữu buffer và **release** sau sử dụng, nhất là khi đổi luồng, lọc, hủy hoặc gặp lỗi. Chỉ dùng **DataBufferUtils.release** đúng lúc; release hai lần cũng sai.
5. Xác minh **Content-Length**, checksum hoặc expected item count nếu hợp đồng có, vì một luồng kết thúc sớm vẫn có thể phát tín hiệu complete tùy upstream/giao thức.
6. Đặt giới hạn **tổng byte**, **thời gian** và **quota file** ở tầng ứng dụng nếu nguồn có thể trả vô hạn; **maxInMemorySize** không thay thế các giới hạn này.

### Vấn đề pooled DataBuffer

Với Reactor Netty, một **DataBuffer** có thể dùng native memory được quản lý bằng reference count. Nếu tự đọc/sao chép buffer, cần giải phóng đúng vòng đời:

~~~java
// Ví dụ nhỏ: chỉ xử lý một chunk rồi luôn release buffer.
Flux<Integer> sizes = response.bodyToFlux(DataBuffer.class)
        .map(buffer -> {
            try {
                return buffer.readableByteCount();
            } finally {
                DataBufferUtils.release(buffer);
            }
        });
~~~

Ví dụ **sizes** chỉ đếm byte theo chunk để minh họa ownership, không tải nội dung về. Nếu thêm operator có thể discard một số buffer trước khi **map**, phải xét thêm cơ chế release khi discard/cancel theo tài liệu Reactor và Spring DataBuffer. Khi dùng codec để giải mã trực tiếp thành DTO, vòng đời DataBuffer thường do codec quản lý.

## 9. Backpressure, concurrency và bộ nhớ

Streaming giảm nhu cầu gom toàn bộ response, nhưng không có nghĩa không bao giờ hết tài nguyên. Khi upstream nhanh hơn downstream, ứng dụng có thể tích lũy hàng nghìn object/buffer trong hàng đợi nội bộ.

| Cơ chế | Tác dụng | Giới hạn |
| --- | --- | --- |
| **limitRate(n)** | Điều chỉnh lượng request phần tử xuống upstream | Không phải rate limiter HTTP hay bảo đảm server dừng gửi ngay |
| **concatMap(...)** | Giữ thứ tự xử lý và chỉ chạy một inner sequence tại một thời điểm theo semantics của operator | Có thể làm thông lượng thấp nếu downstream chậm |
| **flatMap(fn, concurrency)** | Giới hạn số inner publisher thực thi đồng thời | Phải cân nhắc thứ tự, prefetch và số request upstream |
| **onBackpressureBuffer(maxSize)** | Bộ đệm có giới hạn cho nguồn không theo kịp demand | Khi đầy có thể error hoặc xử lý overflow theo cấu hình |
| **buffer(n)** | Gom từng batch có kích thước n | Tốn bộ nhớ cho từng batch; cần giới hạn cả số batch in-flight |
| **take(n)** | Lấy tối đa n phần tử và cancel upstream sau đó | Dừng có chủ ý, không đồng nghĩa upstream gửi đủ dữ liệu |
| **maxInMemorySize** | Giới hạn bộ đệm codec cho một đối tượng/đơn vị giải mã | Không phải giới hạn tổng byte của stream hoặc số connection |

Ví dụ xử lý thay đổi giá với giới hạn số tác vụ ghi database đồng thời:

~~~java
public Mono<Void> synchronizePrices() {
    return streamPriceChanges()
            .flatMap(
                    change -> priceRepository.upsertIdempotently(change),
                    8)
            .then();
}
~~~

Ở đây **priceRepository.upsertIdempotently(change)** được giả định trả về **Mono<?>** và thực sự không blocking. Nếu repository dùng JDBC/JPA blocking, không được chạy trực tiếp trên Netty event loop; cần một executor/scheduler dành cho blocking work và giới hạn concurrency phù hợp, hoặc dùng API truy cập dữ liệu reactive.

**flatMap** có thể xử lý phần tử không theo thứ tự. Nếu sự kiện cho cùng SKU có phiên bản tăng dần, kết quả đúng cần được bảo vệ bằng version check/conditional update hoặc tuần tự hóa theo key; không dựa vào thứ tự callback ngẫu nhiên. Nếu dữ liệu cần phát chính xác theo thứ tự nhận, cân nhắc **concatMap** hoặc thiết kế partition-by-key.

### Đừng dùng onBackpressureBuffer vô hạn

**onBackpressureBuffer()** không đối số có thể tích trữ dữ liệu lớn nếu consumer chậm kéo dài. Chọn biến thể có giới hạn, chiến lược overflow phù hợp và cảnh báo khi chạm ngưỡng. Với dữ liệu thanh toán hoặc ledger, **drop** một event có thể không chấp nhận được; thay vào đó cần phát lỗi, tạm dừng upstream, hoặc dùng broker có khả năng lưu và phát lại.

## 10. Lỗi trong stream và nguy cơ retry phát lại dữ liệu

Một stream có thể đã phát 500 sự kiện rồi mất kết nối. Nếu đặt:

~~~java
Flux<PriceChanged> updates = priceWebClient.get()
        .uri("/prices/export")
        .retrieve()
        .bodyToFlux(PriceChanged.class)
        .retry(2);
~~~

**retry(2)** subscribe lại **toàn bộ pipeline nguồn** tối đa hai lần khi lỗi, không tự tiếp tục từ bản ghi thứ 501. Nếu upstream gửi lại 500 bản ghi cũ, application service có thể nhận các bản ghi này hai lần.

Retry trên stream cần:

1. **Checkpoint/cursor/Last-Event-ID** được upstream hỗ trợ.
2. **Idempotency key** hoặc version cho từng bản ghi để chặn side effect trùng.
3. Chính sách phân biệt lỗi tạm thời và lỗi vĩnh viễn (401, JSON sai, 422 không nên retry mù).
4. Số lần retry, backoff, jitter và ngân sách thời gian/khả năng resume rõ ràng.
5. Xác minh rằng việc dừng/tiếp tục stream không làm sai thứ tự dữ liệu.

Với một request GET trả **một kết quả Mono**, retry có thể đơn giản hơn:

~~~java
Mono<StockSnapshot> snapshot = stockWebClient.get()
        .uri("/inventory/{sku}", sku)
        .retrieve()
        .bodyToMono(StockSnapshot.class)
        .retryWhen(
                Retry.backoff(2, Duration.ofMillis(200))
                        .filter(error ->
                                error instanceof WebClientResponseException ex
                                && ex.getStatusCode().value() == 503))
        .timeout(Duration.ofSeconds(3));
~~~

Đoạn này tối đa **hai lần retry** cho response HTTP 503, trong ngân sách của **timeout** bên ngoài chuỗi retry. Nó không tự retry lỗi DNS, TLS hoặc timeout transport vì bộ lọc không cho các loại lỗi đó đi qua. Với POST/PUT có side effect, phải thiết kế idempotency trước khi áp dụng chính sách tương tự.

### Lỗi sau khi HTTP response đã bắt đầu gửi

Nếu WebFlux controller trả một **Flux** làm response streaming cho browser, một exception sau vài event có thể xuất hiện **sau khi server đã gửi HTTP 200 và headers**. Khi đó không thể đơn giản đổi status thành 503 cho phần dữ liệu đã gửi.

Ứng dụng phải chọn hợp đồng lỗi ở tầng streaming: đóng kết nối có tín hiệu lỗi, SSE event loại **error**, checkpoint/resume, hoặc trạng thái trong payload. Không nên biến mọi onError thành onComplete im lặng vì client có thể tưởng đã nhận đủ dữ liệu.

## 11. Quan sát đúng timeout, cancellation và kết quả

Một luồng tích hợp đáng tin cậy cần tách các metric sau:

| Metric đề xuất | Khi nào tăng | Phân biệt với |
| --- | --- | --- |
| **http.client.request.started** | Bắt đầu subscribe/request thực tế | Số lần method Java được gọi |
| **http.client.request.timeout** | Timeout tại ranh giới xác định | User cancellation, lỗi 4xx/5xx |
| **http.client.stream.cancelled** | Nhận tín hiệu cancel tại điểm instrument | onComplete |
| **http.client.stream.completed** | Upstream hoàn tất bình thường | Đã xử lý hết nghiệp vụ ở downstream |
| **http.client.stream.failed** | Lỗi terminal của stream | Retry có thể chạy tiếp sau đó |
| **http.client.stream.items** | Nhận một phần tử đã decode | Số byte mạng / số event unique |
| **http.client.stream.bytes** | Đọc/ghi byte nếu đo được đáng tin cậy | Number of DTOs |
| **http.client.retry.started** | Retry attempt thực sự bắt đầu | Số retry được lên lịch |
| **http.client.connection.pending** | Chờ pool theo metric transport | Thời gian xử lý business |

Tên bảng là **contract metric đề xuất**, không phải mọi metric được Spring Boot tự động xuất. Sử dụng Spring Boot Actuator/Micrometer Observation và metric Reactor Netty để đo latency, status và pool ở tầng phù hợp; tự bổ sung metric cho outcome theo nghĩa nghiệp vụ.

**Không tăng chung một “error count” trong nhiều lớp** nếu cùng exception bị wrap qua client, service và handler. Phân loại bằng tập nhãn cardinality thấp như **downstream**, **operation**, **error_kind**; không dùng SKU, URL chứa ID, email hoặc requestId làm metric label.

Khi debug timeout hãy đối chiếu trace:

~~~text
WebFlux inbound
  → inventory service
    → WebClient subscribe
      → pool acquire 15 ms
      → connect 80 ms
      → wait for response 1.8 s
      → body decode 40 ms
    → mapping / transaction
  → HTTP response
~~~

**Hết deadline tại service** và **read idle timeout ở Netty** có thể được biểu diễn bằng exception khác nhau. Metric/log nên lưu **kind** đã chuẩn hóa và root cause an toàn để tránh hiểu nhầm.

## 12. Kiểm thử các hành vi khó nhận ra khi chỉ test HTTP 200

**StepVerifier** giúp kiểm tra tín hiệu reactive; **MockWebServer/WireMock** hoặc HTTP server test thật giúp kiểm tra timeout và streaming qua transport.

### 12.1. Mono.timeout bằng virtual time

~~~java
@Test
void failsWhenMonoHasNoSignalForTwoSeconds() {
    StepVerifier.withVirtualTime(
            () -> Mono.<StockSnapshot>never()
                    .timeout(Duration.ofSeconds(2)))
            .thenAwait(Duration.ofSeconds(2))
            .expectError(TimeoutException.class)
            .verify();
}
~~~

Test xác nhận semantics Reactor timeout **không có network**. Khi sử dụng virtual time phải tạo publisher bên trong supplier của **withVirtualTime** để scheduler ảo được áp dụng đúng.

### 12.2. Kiểm thử cancellation

~~~java
@Test
void takeCancelsUpstreamAfterTwoElements() {
    AtomicBoolean cancelled = new AtomicBoolean();

    Flux<Long> infinite = Flux.interval(Duration.ofMillis(10))
            .doOnCancel(() -> cancelled.set(true));

    StepVerifier.create(infinite.take(2))
            .expectNext(0L, 1L)
            .verifyComplete();

    assertTrue(cancelled.get());
}
~~~

Test này chứng minh operator **take(2)** phát cancellation upstream, **không** chứng minh HTTP server đã dừng ghi. Việc test hủy network cần endpoint test có khả năng theo dõi disconnect, cùng connector thực tế; thời điểm socket đóng có thể khác giữa hệ điều hành và transport.

### 12.3. Kiểm thử Flux timeout giữa các phần tử

~~~java
@Test
void streamTimesOutWhileWaitingForNextElement() {
    StepVerifier.withVirtualTime(() ->
            Flux.just("A", "B")
                    .concatWith(Flux.never())
                    .timeout(Duration.ofSeconds(5)))
            .expectNext("A", "B")
            .thenAwait(Duration.ofSeconds(5))
            .expectError(TimeoutException.class)
            .verify();
}
~~~

**Flux.just("A","B")** phát hai phần tử rồi **Flux.never()** không phát tiếp, nên timeout xảy ra **sau phần tử cuối** chứ không phải tại thời điểm tổng stream vượt một deadline cố định.

### 12.4. Tích hợp WebClient với server giả

Dùng MockWebServer/WireMock để dựng các tình huống thực tế:

| Trường hợp | Kỳ vọng |
| --- | --- |
| Server trì hoãn headers | Mono timeout hoặc response timeout đúng chính sách |
| Headers đến, body chậm hoặc ngừng giữa chừng | Phân biệt read idle timeout với end-to-end deadline |
| NDJSON phát nhiều chunk nhỏ | Handler xử lý từng item, không cần gom tất cả |
| SSE có khoảng im lặng dài | Không cắt stream hợp lệ nếu heartbeat/timeout được cấu hình phù hợp |
| Consumer hủy sau n event | Subscription upstream bị cancel, metric cancellation tăng |
| HTTP 503 hoặc 429 | Mapping lỗi đúng status và retry theo hợp đồng |
| HTTP 200 nhưng JSON lỗi giữa stream | Đã nhận item đầu nhưng stream kết thúc bằng onError |
| Response vượt giới hạn codec | DataBufferLimitException được phân loại, không tự nâng giới hạn vô hạn |
| File download bị cắt giữa chừng | Không publish file tạm như kết quả hoàn tất |
| Retry stream sau lỗi giữa chừng | Tránh ghi side effect trùng, resume đúng cursor/version |

Để kiểm tra **timeout connector**, phải sử dụng chính **ClientHttpConnector** và cấu hình transport dự kiến chạy production. Mock trực tiếp method service rồi ném TimeoutException chỉ xác nhận nhánh xử lý business, không chứng minh kết nối hoặc body streaming được cấu hình đúng.

## 13. Các lỗi thiết kế thường gặp

**“Gọi WebClient method là request đã chạy.”** Đối với pipeline cold, request chạy khi subscribe. Nếu không ai subscribe, có thể không có network I/O.

**“Mono.timeout và Flux.timeout đều là giới hạn tổng thời lượng.”** Mono thường chờ một kết quả/complete; Flux timeout(Duration) kiểm tra khoảng chờ đầu tiên và giữa các onNext. Stream đang phát liên tục có thể chạy mãi.

**“Response timeout của Reactor Netty luôn là deadline toàn workflow.”** Nó là timeout của transport. Cần thêm deadline nghiệp vụ tính cả pool, retry và backoff.

**“Cancel đồng nghĩa server rollback.”** Cancel không chứng minh remote write chưa commit. Với request có side effect, cần idempotency và tra cứu/đối soát trạng thái.

**“bodyToFlux luôn dùng bộ nhớ cố định.”** Bộ nhớ còn phụ thuộc codec, kích thước phần tử, buffer, concurrency, downstream và việc có collectList hay không.

**“SSE cứ 2 giây không có event là lỗi mạng.”** Stream có thể im lặng hợp lệ; cần hợp đồng heartbeat và timeout phù hợp.

**“retry(3) tiếp tục stream tại vị trí lỗi.”** Retry subscribe lại từ đầu trừ khi server và client có cursor/resume. Không được mặc định đúng thứ tự hoặc đúng một lần.

**“onErrorResume luôn biến timeout thành dữ liệu rỗng.”** Nếu API cần phân biệt upstream không sẵn sàng với kết quả không tồn tại, fallback rỗng sẽ làm sai nghiệp vụ.

**“Ghi file tạm xong vài chunk là đủ.”** File chỉ hoàn chỉnh khi stream thành công và được xác minh; cancel/error có thể để lại file thiếu.

**“Không có exception nghĩa là đã nhận đủ dữ liệu.”** **take(n)**, **take(Duration)** hoặc disconnect có thể dừng luồng trước khi upstream phát hết và downstream vẫn quan sát một kết thúc hợp lệ theo operator.

## 14. Checklist tích hợp WebClient chịu tải và chịu lỗi

1. Xác định endpoint trả JSON object, JSON array, NDJSON, SSE hay binary; chọn Mono/Flux đúng hợp đồng.
2. Chọn transport thực tế, cấu hình pool, connect timeout, response/read timeout và theo dõi giới hạn tài nguyên.
3. Đặt deadline ở cấp thao tác nghiệp vụ; phân biệt deadline toàn stream với **timeout giữa các event**.
4. Return Mono/Flux từ service/controller; chỉ chủ động subscribe tại ranh giới quản lý vòng đời rõ ràng.
5. Quan sát **onComplete**, **onError**, **CANCEL** riêng; hiểu operator timeout ở trên/dưới điểm đo khác nhau.
6. Với request ghi dữ liệu, chuẩn bị idempotency key và quy trình đối soát sau timeout/cancel.
7. Với stream dài, giới hạn buffer, concurrency, page size, số byte và thời lượng; không giữ toàn bộ dữ liệu trong memory.
8. Nếu dùng raw DataBuffer, hiểu ownership, release, discard và cách xử lý file tạm.
9. Chọn retry có giới hạn và cursor/checkpoint cho stream; chống trùng/đảo thứ tự ở tầng nghiệp vụ.
10. Test trên transport thật các tình huống delay, cancel, partial body, lỗi JSON, retry và server disconnect.
11. Gắn metric/tracing có nhãn hữu hạn; phân biệt lỗi mạng, timeout, thiếu dữ liệu, stream hoàn tất và hủy chủ động.

**Tư duy cần ghi nhớ:** WebClient diễn đạt một **pipeline HTTP được thực thi theo subscription**. Timeout quy định giới hạn chờ ở từng tầng; cancellation cắt nhu cầu của subscriber; streaming quyết định cách tiêu thụ body theo từng phần. Muốn một tích hợp đáng tin cậy, phải phối hợp cả ba với hợp đồng dữ liệu, tính lũy đẳng và chiến lược phục hồi sau lỗi.

## Tài liệu tham khảo

- [Spring Framework — WebClient](https://docs.spring.io/spring-framework/reference/web/webflux-webclient.html): mô hình reactive, streaming và các connector.
- [Spring Framework — WebClient Configuration](https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-builder.html): Reactor Netty, connection/response timeout và codec limit.
- [Spring Framework — retrieve()](https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-retrieve.html): bodyToMono, bodyToFlux và onStatus.
- [Spring Framework — exchangeToMono / exchangeToFlux](https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-exchange.html): tùy biến xử lý theo status và giải phóng response body.
- [Spring Framework — Data Buffers and Codecs](https://docs.spring.io/spring-framework/reference/core/databuffer-codec.html): pooled DataBuffer và quản lý bộ nhớ.
- [Spring Framework — DataBufferUtils API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/core/io/buffer/DataBufferUtils.html): ghi stream vào file và release buffer.
- [Reactor Core — Error Handling](https://projectreactor.io/docs/core/release/reference/coreFeatures/error-handling.html): onError, timeout, retry, doFinally và cancellation.
- [Reactor Netty — Reference Guide](https://projectreactor.io/docs/netty/release/reference/index.html): timeout transport, connection pool và quản lý tài nguyên.
- [Spring Boot — HTTP Clients](https://docs.spring.io/spring-boot/how-to/http-clients.html): cấu hình WebClient/ClientHttpConnector và dùng chung Reactor Netty resources.
