# Streaming, backpressure và vòng đời kết nối dài

Trong Spring Cloud LoadBalancer, `WebClient` có thể gọi một dịch vụ bằng **service ID** thay vì địa chỉ host/port cố định. Với response thông thường, request được gửi tới một `ServiceInstance` và hoàn tất trong thời gian ngắn. Nhưng khi response là **luồng dài** như Server-Sent Events (SSE) hoặc NDJSON liên tục, một lần lựa chọn instance có thể gắn với nhiều giây, nhiều phút, thậm chí lâu hơn. Cách quản lý **backpressure, kết nối, hủy đăng ký, timeout và retry** lúc này ảnh hưởng trực tiếp tới tài nguyên và độ tin cậy.

Bài thuộc chương **WebClient** của module **SPRING_CLOUD_SERVICE_COMMUNICATION_LOAD_BALANCING**. Mục tiêu là hiểu giao tiếp reactive không chặn với `Mono` và `Flux`, cách LoadBalancer chọn instance cho luồng, giới hạn của backpressure trên HTTP, và vận dụng với **service discovery, health check, retry, timeout và observability**. `RestClient` và OpenFeign cũng có thể gọi theo tên dịch vụ, nhưng ví dụ dưới đây tập trung vào vòng đời reactive stream của `WebClient`.

> Bối cảnh: sử dụng Spring Boot WebFlux và phiên bản Spring Cloud tương thích, Java 17+. Ví dụ là một bài thực hành tự chứa, không yêu cầu Eureka: hai instance được khai báo bằng `SimpleDiscoveryClient`. Không dùng endpoint thử nghiệm để gửi dữ liệu thật hoặc tải production.

## 1. Streaming khác một HTTP response ngắn như thế nào?

Với request JSON thông thường:

~~~text
GET /api/items/42  ->  HTTP 200 + một JSON object  ->  Kết thúc response
~~~

Với server streaming, một HTTP response có thể mang nhiều bản tin liên tiếp:

~~~text
GET /api/stock/events  ->  HTTP 200 Content-Type: text/event-stream
                          event: stock
                          data: {"sku":"sku-42","quantity":8}

                          event: stock
                          data: {"sku":"sku-42","quantity":9}

                          ... tiếp tục cho đến khi đóng/hủy/lỗi
~~~

Có ba khái niệm cần tách biệt:

- **HTTP connection/stream**: kênh vận chuyển; ở HTTP/1.1 có thể giữ một kết nối hoạt động lâu, còn HTTP/2 có thể multiplex nhiều HTTP stream trên một kết nối TCP.
- **Reactive publisher**: `Flux<T>` đại diện cho dãy nhiều phần tử bất đồng bộ, có thể hoàn tất, thất bại hoặc kéo dài vô hạn.
- **Service instance được chọn**: nơi WebClient gửi **request HTTP cụ thể**; LoadBalancer không tự chuyển mỗi phần tử trong response sang instance mới.

Một `Flux` không mặc nhiên có nghĩa response đang streaming qua mạng: `Flux.just(...)` có thể phát các phần tử đã có sẵn. Ngược lại, `bodyToFlux(...)` với `text/event-stream` hoặc NDJSON có thể giải mã từng phần tử khi dữ liệu tới.

## 2. Mô hình lựa chọn instance cho một subscription

Giả sử `order-service` gọi `catalog-service` qua `@LoadBalanced WebClient.Builder`.

~~~mermaid
sequenceDiagram
    autonumber
    participant Caller as order-service
    participant WC as WebClient
    participant LB as Spring Cloud LoadBalancer
    participant Supplier as ServiceInstanceListSupplier
    participant A as catalog-a
    participant B as catalog-b

    Caller->>WC: Subscribe vào Flux SSE
    WC->>LB: Chọn catalog-service
    LB->>Supplier: Lấy ứng viên
    Supplier-->>LB: [A, B]
    LB-->>WC: Chọn B
    WC->>B: GET /api/stock/events
    B-->>WC: HTTP 200 text/event-stream
    B-->>WC: SSE event #1
    WC-->>Caller: StockEvent #1
    B-->>WC: SSE event #2
    WC-->>Caller: StockEvent #2
    Note over Caller,B: B giữ request stream này cho đến khi kết thúc/hủy/lỗi
~~~

Điểm quan trọng: **mỗi HTTP request/subscription được chọn một instance**; event #1 và #2 không lần lượt chuyển giữa A/B theo Round Robin. Khi có **subscription mới** hoặc **resubscription sau retry**, LoadBalancer có thể thực hiện một lần lựa chọn khác, tùy hành vi filter, policy và cấu hình retry.

Từ đó suy ra:

1. Khi B trả luồng đang chạy, một health check mới đánh dấu B unhealthy **không bảo đảm luồng đang mở được tự động chuyển sang A**.
2. Nếu B dừng đột ngột, luồng có thể phát tín hiệu lỗi hoặc bị timeout. Muốn phục hồi cần chính sách reconnect/resubscribe có kiểm soát.
3. Instance mới xuất hiện trong discovery thường ảnh hưởng các **lời gọi mới**, không chia lại những luồng đã được thiết lập.
4. Nếu một số subscriber nhận luồng rất dài, chúng có thể tập trung trên số instance được chọn lúc đầu; round-robin trên số **kết nối được mở** không đồng nghĩa cân bằng số event, CPU hay số subscriber đang hoạt động.

## 3. Cấu hình WebClient gọi theo service ID

Trong Gradle có Spring Boot/Spring Cloud BOM tương thích:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.cloud:spring-cloud-starter-loadbalancer'
}
~~~

Ở ứng dụng caller, khai báo hai instance `catalog-service` bằng discovery tĩnh:

~~~yaml
server:
  port: 18090

spring:
  application:
    name: order-service
  cloud:
    discovery:
      client:
        simple:
          instances:
            catalog-service:
              - uri: http://localhost:18081
              - uri: http://localhost:18082
~~~

Spring Cloud cung cấp tích hợp LoadBalancer cho `WebClient.Builder` đánh dấu `@LoadBalanced`:

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration(proxyBeanMethods = false)
class CatalogWebClientConfiguration {

    @Bean
    @LoadBalanced
    WebClient.Builder loadBalancedWebClientBuilder() {
        return WebClient.builder();
    }

    @Bean
    WebClient catalogWebClient(
            @Qualifier("loadBalancedWebClientBuilder")
            WebClient.Builder builder) {
        return builder
            .baseUrl("http://catalog-service")
            .build();
    }
}
~~~

Khi thực hiện `catalogWebClient.get().uri("/api/stock/events")`, host trong base URL được hiểu là service ID. Sau khi chọn instance, tích hợp LoadBalancer thay thế đích logic bằng địa chỉ thực.

**Sai lầm thường gặp:** sử dụng `WebClient.create("http://catalog-service")` hoặc builder tự tạo không nhận cấu hình `@LoadBalanced`, rồi cho rằng nó vẫn sẽ dùng Spring Cloud discovery. Trường hợp đó request có thể chuyển sang DNS bình thường, không đi qua LoadBalancer.

## 4. Viết một SSE server có thể chạy ở hai instance

Để tự quan sát kết nối dài, ví dụ backend tạo một SSE event mỗi giây. Khởi chạy **cùng ứng dụng WebFlux** trên hai cổng với `instance.id` khác nhau.

~~~java
import java.time.Duration;
import java.time.Instant;

import org.springframework.core.env.Environment;
import org.springframework.http.MediaType;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Flux;

record StockEvent(
    String sku,
    int quantity,
    String instanceId,
    long sequence,
    Instant generatedAt
) {}

@RestController
class StockEventController {

    private final String instanceId;

    StockEventController(Environment environment) {
        this.instanceId = environment.getProperty(
            "instance.id", "catalog-unknown");
    }

    @GetMapping(
        value = "/api/stock/events",
        produces = MediaType.TEXT_EVENT_STREAM_VALUE
    )
    Flux<ServerSentEvent<StockEvent>> events() {
        return Flux.interval(Duration.ofSeconds(1))
            .map(sequence -> {
                StockEvent event = new StockEvent(
                    "sku-42",
                    10 + (int) (sequence % 5),
                    instanceId,
                    sequence,
                    Instant.now()
                );

                return ServerSentEvent.<StockEvent>builder()
                    .id(Long.toString(sequence))
                    .event("stock")
                    .data(event)
                    .build();
            });
    }
}
~~~

Cần có ứng dụng Spring Boot entrypoint, chẳng hạn class mang `@SpringBootApplication`, cùng dependency `spring-boot-starter-webflux`. Giả sử ứng dụng được đóng gói thành `catalog-events.jar`:

~~~bash
java -jar catalog-events.jar --server.port=18081 --instance.id=catalog-a
java -jar catalog-events.jar --server.port=18082 --instance.id=catalog-b
~~~

Trước khi dùng LoadBalancer, xác nhận hai instance tự phục vụ SSE:

~~~bash
curl -N -i http://localhost:18081/api/stock/events
curl -N -i http://localhost:18082/api/stock/events
~~~

Tùy chọn `-N` của curl tắt output buffering khi hiển thị, giúp quan sát bản tin SSE tới liên tục. Dừng bằng Ctrl+C.

**Lưu ý về dữ liệu demo:** `sequence` sinh từ `Flux.interval` bắt đầu lại cho mỗi subscription, không phải offset bền vững. Vì vậy ví dụ này **không bảo đảm replay** hoặc dữ liệu exactly-once khi reconnect. Trong production, cần nguồn sự kiện và cơ chế ID/cursor ổn định.

## 5. Đọc SSE bằng WebClient và bodyToFlux

Spring Framework cung cấp `ServerSentEvent<T>` để biểu diễn ID, event name và data của SSE. Dùng `ParameterizedTypeReference` để giữ kiểu generic của data:

~~~java
import java.util.Objects;

import org.springframework.core.ParameterizedTypeReference;
import org.springframework.http.MediaType;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.stereotype.Service;
import org.springframework.web.reactive.function.client.WebClient;

import reactor.core.publisher.Flux;

@Service
class CatalogEventGateway {

    private final WebClient catalogWebClient;

    CatalogEventGateway(WebClient catalogWebClient) {
        this.catalogWebClient = catalogWebClient;
    }

    Flux<StockEvent> stockEvents() {
        return catalogWebClient.get()
            .uri("/api/stock/events")
            .accept(MediaType.TEXT_EVENT_STREAM)
            .retrieve()
            .bodyToFlux(
                new ParameterizedTypeReference<
                    ServerSentEvent<StockEvent>>() {}
            )
            .map(ServerSentEvent::data)
            .filter(Objects::nonNull);
    }
}
~~~

`StockEvent` bên caller cần có JSON-compatible fields tương ứng với backend, ví dụ cùng record năm trường. Publisher trả về từ `stockEvents()` thường là **cold** đối với request HTTP: mỗi subscription có thể khởi tạo một request mới, tương ứng một lần chọn instance và một luồng SSE riêng.

Nếu chỉ cần payload chứ không cần ID/event name, có thể đọc bằng các decoder phù hợp; nhưng nếu dự kiến reconnect/replay, nên giữ `ServerSentEvent<T>` đầy đủ để lấy `id()`.

### Trả tiếp luồng cho client của caller

Ví dụ một WebFlux controller làm proxy stream:

~~~java
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Flux;

@RestController
class StockStreamController {

    private final CatalogEventGateway gateway;

    StockStreamController(CatalogEventGateway gateway) {
        this.gateway = gateway;
    }

    @GetMapping(
        value = "/demo/stock-stream",
        produces = MediaType.TEXT_EVENT_STREAM_VALUE
    )
    Flux<StockEvent> stockStream() {
        return gateway.stockEvents();
    }
}
~~~

Bắt đầu luồng qua caller:

~~~bash
curl -N http://localhost:18090/demo/stock-stream
~~~

Nhìn vào trường `instanceId` của từng event: trong một subscription bình thường, các event liên tiếp đến từ cùng instance. Mở **hai terminal curl** tạo hai subscription riêng, chúng có thể được chọn đến các instance khác nhau.

Vì WebFlux quản lý subscription của request HTTP, controller chỉ **trả publisher**, không gọi `subscribe()` thủ công. Khi downstream hủy kết nối, tín hiệu cancel thông thường được truyền upstream để giải phóng request đang chạy.

## 6. Subscription, demand và ba tín hiệu kết thúc

Reactive Streams xác định giao thức giữa publisher và subscriber:

1. Subscriber gọi `onSubscribe(subscription)`.
2. Subscriber thể hiện nhu cầu bằng `request(n)` với n dương.
3. Publisher phát tối đa lượng phần tử tương ứng với demand chưa tiêu thụ qua `onNext`.
4. Stream kết thúc bằng **`onComplete`**, **`onError`** hoặc bị subscriber gọi **`cancel`**.

Một sơ đồ đơn giản:

~~~mermaid
sequenceDiagram
    participant S as Subscriber
    participant P as Publisher
    S->>P: subscribe()
    P-->>S: onSubscribe(subscription)
    S->>P: request(2)
    P-->>S: onNext(event1)
    P-->>S: onNext(event2)
    Note over P,S: Chưa có demand mới thì không được vượt hợp đồng request(n)
    S->>P: request(1)
    P-->>S: onNext(event3)
    S->>P: cancel()
    Note over P,S: Dừng phát và dọn tài nguyên
~~~

**Backpressure** nghĩa là nhu cầu từ downstream có thể tác động đến tốc độ phát/đệm dữ liệu của upstream trong một pipeline reactive. Nhưng cần hiểu giới hạn quan trọng: **một server SSE bên ngoài không bắt buộc hiểu hay tôn trọng demand `request(n)` của Reactor**.

`WebClient.bodyToFlux` và các decoder có thể kết hợp demand với quá trình nhận/giải mã. Tuy nhiên, socket, bộ đệm HTTP, TCP receive window, HTTP/2 flow control và cách server gửi dữ liệu mới quyết định lượng byte thực tế vẫn đang đến. Backpressure ở Java pipeline **không phải cam kết end-to-end** rằng server sẽ dừng sản xuất sự kiện khi subscriber chậm.

### Ví dụ quá tải subscriber

Nếu server sinh 1.000 event/giây nhưng consumer chỉ xử lý được 100 event/giây, lưu trữ toàn bộ sự kiện chờ xử lý có thể tăng rất nhanh. Tăng số bộ đệm mà không có giới hạn chỉ trì hoãn việc hết bộ nhớ.

Cần chọn chính sách rõ ràng: giảm tốc nguồn, giới hạn concurrency, gộp sự kiện, bỏ các bản tin trung gian chỉ khi nghiệp vụ cho phép, hoặc từ chối/đóng kết nối để client reconnect và đọc lại từ nguồn bền vững.

## 7. Các toán tử backpressure: dùng đúng mục đích

| Toán tử | Công dụng | Bẫy cần tránh |
|---|---|---|
| `limitRate(n)` | Điều chỉnh kích thước yêu cầu upstream theo đợt | Không phải giới hạn events/giây và không tự làm chậm server bên ngoài |
| `onBackpressureBuffer(...)` | Đệm sự kiện khi downstream chưa theo kịp | Buffer không giới hạn có thể hết RAM; cần capacity và overflow policy |
| `onBackpressureDrop(...)` | Bỏ sự kiện khi không có demand | Không phù hợp cho giao dịch cần xử lý đủ mọi event |
| `onBackpressureLatest()` | Giữ sự kiện gần nhất, bỏ sự kiện cũ | Phù hợp snapshot/cập nhật trạng thái, không phù hợp audit log |
| `sample(Duration)` | Giữ mẫu theo thời gian, giảm tần suất quan sát | Làm mất các sự kiện ở giữa |
| `flatMap(..., concurrency)` | Giới hạn số tác vụ bất đồng bộ cùng chạy | Không tự hạn chế tốc độ mạng; thứ tự event có thể thay đổi |
| `concatMap(...)` | Xử lý tuần tự, giữ thứ tự | Throughput giảm nếu một tác vụ chậm |

Với **dòng cập nhật giá hoặc stock dạng snapshot** cho giao diện, chỉ giữ trạng thái gần nhất đôi khi chấp nhận được. Với **ledger, chuyển tiền, đơn hàng hoặc CDC có thứ tự**, bỏ sự kiện là sai hợp đồng; cần durable broker, offset, cơ chế replay và xử lý idempotent.

### Ví dụ kiểm soát số công việc đồng thời

Giả sử `persistAsync(event)` trả về `Mono<Void>` từ một thư viện lưu trữ **non-blocking**:

~~~java
Flux<StockEvent> events = gateway.stockEvents();

Flux<Void> processed = events
    .limitRate(32)
    .flatMap(event -> persistAsync(event), 4);
~~~

`flatMap(..., 4)` giới hạn tối đa bốn thao tác async cùng đang chạy trong phần xử lý này. `limitRate(32)` điều chỉnh request upstream; nó **không** tương đương “chỉ nhận 32 event/giây”. Nếu phải giữ thứ tự, cân nhắc `concatMap` hoặc chiến lược tuần tự hóa phù hợp.

Ví dụ này là đoạn pipeline minh họa: `persistAsync` là hàm do ứng dụng cài đặt, không phải API có sẵn của Spring Cloud.

### Ví dụ chỉ giữ trạng thái mới nhất

~~~java
Flux<StockEvent> latestForUi = gateway.stockEvents()
    .onBackpressureLatest()
    .sample(Duration.ofSeconds(1));
~~~

Nó phù hợp khi event chỉ thể hiện **ảnh chụp hiện tại** của tồn kho và người dùng không cần mọi giá trị trung gian. Nó **không phù hợp** nếu mỗi event là một thay đổi `+1` hoặc `-1` phải được áp dụng đầy đủ; bỏ một sự kiện sẽ cho ra tổng sai.

Nếu chọn `onBackpressureBuffer`, hãy đặt giới hạn dung lượng và quyết định rõ overflow sẽ báo lỗi, bỏ dữ liệu hay ngắt kết nối; không dùng buffer vô hạn cho luồng kéo dài không xác định.

## 8. Không chặn event-loop trong xử lý event

`WebClient` với Reactor Netty thường sử dụng event-loop để thực hiện network I/O và đẩy tín hiệu qua reactive pipeline. Nếu gọi hàm blocking (JDBC thuần, `Thread.sleep`, xử lý file chậm) ngay trong `map`, `doOnNext` hoặc callback trên event-loop, ứng dụng có thể làm nghẽn nhiều kết nối cùng lúc.

**Không nên:**

~~~java
return gateway.stockEvents()
    .doOnNext(event -> blockingRepository.save(event));
~~~

Nếu bắt buộc tích hợp thư viện blocking, cô lập nó bằng scheduler thích hợp và giới hạn concurrency:

~~~java
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

Flux<StockEvent> saved = gateway.stockEvents()
    .flatMap(event ->
        Mono.fromCallable(() -> blockingRepository.save(event))
            .subscribeOn(Schedulers.boundedElastic()),
        4
    );
~~~

`boundedElastic` hỗ trợ công việc blocking có giới hạn, nhưng không biến API blocking thành non-blocking. Cần kiểm soát số connection, số tác vụ chờ và khả năng cạn thread; nếu có reactive database driver phù hợp, ưu tiên pipeline non-blocking từ đầu.

Đừng gọi `block()`, `blockLast()` hay `toIterable()` trong handler WebFlux reactive: các thao tác đó chặn thread và có thể làm gián đoạn vòng event-loop.

## 9. Vòng đời một kết nối streaming dài

Một subscription SSE thường đi qua các pha:

~~~mermaid
stateDiagram-v2
    [*] --> NEW
    NEW --> SELECTING: subscribe
    SELECTING --> CONNECTING: đã chọn ServiceInstance
    SELECTING --> FAILED: không có instance
    CONNECTING --> STREAMING: HTTP 200 và nhận body stream
    CONNECTING --> FAILED: lỗi kết nối / timeout
    STREAMING --> STREAMING: nhận event tiếp
    STREAMING --> COMPLETED: server đóng bình thường
    STREAMING --> FAILED: I/O error / read timeout
    STREAMING --> CANCELLED: subscriber cancel
    FAILED --> RETRYING: policy cho phép
    RETRYING --> SELECTING: subscribe lại, chọn instance mới
    COMPLETED --> [*]
    CANCELLED --> [*]
    FAILED --> [*]
~~~

Cần quản lý rõ:

- **Lúc mở**: xin connection hoặc một logical HTTP stream; có thể chờ connection pool.
- **Lúc đang chạy**: giữ tài nguyên transport và decoder trong suốt response; request không hoàn tất sau event đầu.
- **Lúc server hoàn tất**: xử lý completion; kết nối vật lý chỉ có thể tái sử dụng theo điều kiện HTTP client/transport.
- **Lúc lỗi**: giải phóng tài nguyên và quyết định retry/reconnect; không giữ publisher vô thời hạn trong bộ nhớ.
- **Lúc cancel**: ngừng đọc upstream và giải phóng tài nguyên tương ứng; behavior phụ thuộc connector, trạng thái socket và protocol.

Với HTTP/1.1, một SSE response đang mở thường chiếm một kết nối đang hoạt động. Với HTTP/2, nhiều logical streams có thể dùng chung một TCP connection, nhưng **mỗi stream vẫn chiếm tài nguyên server/client**. Không coi “số TCP connections” là đủ để đánh giá tải streaming.

### Vì sao connection pool cần chú ý?

Một caller có 500 người dùng mở SSE đồng thời tới cùng service ID có thể duy trì hàng trăm logical requests. Nếu pool/transport hoặc server có giới hạn thấp, kết nối mới có thể xếp hàng để được cấp tài nguyên; pending acquire lâu có thể sinh lỗi hoặc timeout.

Với các kết nối dài, nên đo:

| Metric | Mục đích |
|---|---|
| Active/pending/idle connections | Pool còn capacity cấp request mới không? |
| Active SSE/HTTP streams | Có bao nhiêu luồng đang được duy trì? |
| Độ dài stream và số event nhận | Stream có hoạt động hay bị đứng? |
| Tần suất reconnect / lỗi I/O | Có flap giữa các instance không? |
| Heap/direct memory, decoder buffers | Có rò hoặc phình buffer không? |
| Instance được chọn và số stream theo instance | LoadBalancer có tạo hotspot kết nối không? |
| Time-to-first-event và khoảng cách giữa event | Có vấn đề heartbeat hoặc nguồn dữ liệu không? |

Việc đo pool metrics phụ thuộc connector (ví dụ Reactor Netty) và cấu hình observability, không phải mọi ứng dụng mặc định đều có toàn bộ nhãn này.

## 10. Timeout và heartbeat cho luồng không kết thúc

Với HTTP response ngắn, nhiều đội cấu hình response/read timeout nhỏ. Nhưng SSE có thể **cố ý im lặng** một khoảng thời gian dài khi không có sự kiện. Nếu HTTP client hiểu sự im lặng là không nhận dữ liệu trong thời gian timeout, nó có thể đóng luồng khỏe mạnh.

Phân biệt:

- **Connect timeout**: giới hạn thời gian mở kết nối tới instance.
- **Response/read timeout**: tùy HTTP connector, có thể giới hạn khoảng thời gian không nhận dữ liệu trên connection/response.
- **Time-to-first-event**: thời gian từ subscribe tới bản tin đầu tiên.
- **Application idle deadline**: ngưỡng riêng do ứng dụng đặt để phát hiện nguồn stream ngừng phát, tùy nghiệp vụ.

Ví dụ cấu hình Reactor Netty cho client **dùng với các SSE event/heartbeat có khoảng cách ngắn hơn 45 giây**:

~~~java
import java.time.Duration;

import io.netty.channel.ChannelOption;
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.reactive.ReactorClientHttpConnector;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.netty.http.client.HttpClient;

@Configuration(proxyBeanMethods = false)
class StreamingClientConfiguration {

    @Bean
    @LoadBalanced
    WebClient.Builder loadBalancedWebClientBuilder() {
        HttpClient httpClient = HttpClient.create()
            .option(ChannelOption.CONNECT_TIMEOUT_MILLIS, 3_000)
            .responseTimeout(Duration.ofSeconds(45));

        return WebClient.builder()
            .clientConnector(new ReactorClientHttpConnector(httpClient));
    }
}
~~~

Đây là **cách cấu hình thay thế** cho bean builder đã trình bày ở phần 3, không phải bean thứ hai cần đăng ký cùng tên. `responseTimeout` ở Reactor Netty cần hiểu theo cơ chế connector và phiên bản: với stream có khoảng im lặng lớn hơn ngưỡng, request có thể bị đóng dù socket còn tồn tại. Không tự chọn timeout 45 giây cho mọi hệ thống mà không xác nhận tần suất event, heartbeat và proxy/load balancer hạ tầng.

### Heartbeat

Server SSE có thể gửi comment dòng bắt đầu bằng `:` theo định dạng SSE hoặc phát một event heartbeat để giữ đường truyền hoạt động. Ví dụ ý tưởng:

~~~text
: heartbeat

event: stock
data: {"sku":"sku-42","quantity":8}

: heartbeat
~~~

Heartbeat giúp phát hiện hoặc ngăn một số proxy/client đóng kết nối vì im lặng, nhưng phải phù hợp timeout ở mọi tầng: server, ingress, gateway, proxy, connector và application. Cần tránh đặt heartbeat quá dày khi số subscriber lớn.

**`Flux.timeout(Duration)`** có thể áp dụng deadline giữa các event, nhưng không nhất thiết giống timeout đọc byte ở HTTP connector; một comment SSE có thể giữ socket sống mà không tạo phần tử `StockEvent`. Do đó, đặt cả hai cần hiểu đúng tín hiệu được theo dõi.

## 11. Cancellation: đóng request khi người dùng rời trang

Nếu controller trả `Flux` trực tiếp, WebFlux thường chuyển tín hiệu hủy từ HTTP client ngắt kết nối vào publisher upstream. Có thể gắn log vòng đời để kiểm chứng:

~~~java
import reactor.core.publisher.SignalType;

Flux<StockEvent> stream = gateway.stockEvents()
    .doOnSubscribe(s -> log.info("SSE subscribed"))
    .doOnCancel(() -> log.info("SSE cancelled"))
    .doFinally(signal -> log.info("SSE finished: {}", signal));
~~~

`doFinally` chạy khi stream hoàn tất, lỗi hoặc bị cancel; `SignalType` có thể là `ON_COMPLETE`, `ON_ERROR` hoặc `CANCEL`. Ví dụ trên giả định có logger tên `log` do ứng dụng khai báo.

Trong unit/integration test, dùng `take(5)` để chủ động kết thúc một subscription dài sau năm phần tử:

~~~java
Flux<StockEvent> fiveEvents = gateway.stockEvents().take(5);
~~~

Khi đủ năm phần tử, `take` hủy upstream và giải phóng subscription đó theo vòng đời reactive. Đừng kỳ vọng mọi SSE đều tự đóng sau năm event; đây là chính sách do caller thêm vào để hạn chế thời gian thử nghiệm.

**Tránh gọi `subscribe()` thủ công trong service** chỉ để làm cho HTTP request “chạy ngay”. Nếu mất reference tới `Disposable`, ứng dụng khó cancel khi người dùng ngắt kết nối. Controller nên trả publisher để framework quản lý; nếu thật sự có background subscription, phải sở hữu và dispose nó đúng lifecycle ứng dụng.

## 12. Xử lý HTTP 4xx/5xx và lỗi trong khi stream đang chạy

Với `retrieve()`, lỗi HTTP status `4xx/5xx` từ response ban đầu thường được biểu diễn bằng `WebClientResponseException`, trừ khi ứng dụng tùy biến `onStatus`:

~~~java
Flux<ServerSentEvent<StockEvent>> events =
    catalogWebClient.get()
        .uri("/api/stock/events")
        .accept(MediaType.TEXT_EVENT_STREAM)
        .retrieve()
        .onStatus(
            status -> status.value() == 404,
            response -> Mono.error(
                new IllegalStateException("SSE endpoint not found"))
        )
        .bodyToFlux(
            new ParameterizedTypeReference<
                ServerSentEvent<StockEvent>>() {}
        );
~~~

`onStatus` chỉ xử lý **HTTP response status**. Nếu LoadBalancer không chọn được instance, connect timeout, lỗi DNS hoặc kết nối bị reset giữa stream, có thể chưa có HTTP response phù hợp để callback `onStatus` chạy.

Sau khi server đã gửi HTTP 200 và bắt đầu stream, một sự cố giữa chừng **không thể đổi status đã gửi thành 503 cho chính response đó**. Thông thường luồng sẽ phát tín hiệu error/cancel/close. Nếu bản tin SSE chứa một payload nghiệp vụ kiểu `{"error":"..."}`, đó là **event dữ liệu** và phải được thiết kế contract riêng, không tự tương đương HTTP 5xx.

### Sai lầm: nuốt lỗi thành stream rỗng

~~~java
// Cẩn trọng: bỏ mọi lỗi khiến caller khó biết rằng dữ liệu bị gián đoạn.
return gateway.stockEvents()
    .onErrorResume(error -> Flux.empty());
~~~

Đoạn này có thể khiến stream kết thúc bình thường trong mắt caller dù dependency đã lỗi. Chỉ dùng fallback khi nghiệp vụ có thể chấp nhận và phải có observability/cảnh báo. Với thông tin tồn kho hoặc giá, việc im lặng có thể nguy hiểm hơn trả lỗi có thể nhận biết.

## 13. Retry và reconnect: resubscribe chứ không nối tiếp stream cũ

Với stream dài, retry không chỉ là “gọi lại request ngắn”. Khi kết nối bị ngắt, một subscription mới có thể chọn một instance khác. Nhưng producer không mặc nhiên biết subscriber đã nhận event nào trước khi lỗi.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant LB as LoadBalancer
    participant B as catalog-b
    participant A as catalog-a

    C->>LB: Subscribe SSE
    LB-->>C: Chọn B
    C->>B: GET /events
    B-->>C: event id=101
    B-->>C: event id=102
    Note over B: B dừng đột ngột
    B--xC: Stream lỗi
    Note over C: Retry/backoff với giới hạn
    C->>LB: Subscribe lại
    LB-->>C: Có thể chọn A
    C->>A: GET /events (cursor nếu có)
    A-->>C: Tiếp tục hoặc phát lại theo contract
~~~

Ví dụ retry **có giới hạn** cho lỗi I/O có thể phục hồi:

~~~java
import java.time.Duration;

import org.springframework.web.reactive.function.client.WebClientRequestException;
import reactor.util.retry.Retry;

Flux<StockEvent> resilient = gateway.stockEvents()
    .retryWhen(
        Retry.backoff(5, Duration.ofSeconds(1))
            .maxBackoff(Duration.ofSeconds(15))
            .filter(error ->
                error instanceof WebClientRequestException)
    );
~~~

Code này chỉ là ví dụ tối giản:

- `retryWhen` resubscribe sau lỗi phù hợp; mỗi lần có thể thực hiện lại khâu chọn instance.
- Sau số lần cho phép, lỗi cuối vẫn cần được xử lý/quan sát; không tạo vòng reconnect vô hạn không có kiểm soát.
- Lỗi từ server dưới dạng HTTP `503` có thể cần policy khác và `Retry-After`; không tự động retry mọi `4xx` hay lỗi JSON.
- Một số lỗi kết nối giữa luồng có thể nằm dưới loại exception khác với `WebClientRequestException`. Cần quan sát class/cause thực tế của connector rồi điều chỉnh predicate.
- Retry sau khi đã nhận event có thể **lặp event** hoặc **bỏ sót event**, ngay cả khi request mới thành công.

### Last-Event-ID và replay

SSE hỗ trợ trường `id` ở mỗi event; một client có thể gửi lại header `Last-Event-ID` khi reconnect. Với `WebClient`, ứng dụng **phải tự duy trì cursor/reconnect logic** nếu muốn tính năng này; `retryWhen` đơn giản ở trên không bảo đảm tự mang theo ID event mới nhất.

Ví dụ gửi cursor đã được lưu bởi caller:

~~~java
Flux<ServerSentEvent<StockEvent>> eventsFrom(String lastId) {
    return catalogWebClient.get()
        .uri("/api/stock/events")
        .headers(headers -> {
            if (lastId != null && !lastId.isBlank()) {
                headers.set("Last-Event-ID", lastId);
            }
        })
        .accept(MediaType.TEXT_EVENT_STREAM)
        .retrieve()
        .bodyToFlux(
            new ParameterizedTypeReference<
                ServerSentEvent<StockEvent>>() {}
        );
}
~~~

Đây chỉ là **phần tạo request với cursor**, không phải triển khai reconnect đầy đủ. Để hỗ trợ tiếp tục đúng từ event bị gián đoạn, server cần:

1. Phát **event ID ổn định toàn hệ thống** (không phải counter reset cho mỗi connection).
2. Lưu dữ liệu vào nguồn có thể replay theo ID/offset.
3. Cho mọi instance được chọn sau reconnect truy cập cùng vùng dữ liệu hoặc cơ chế chuyển tiếp tương thích.
4. Quy định khi cursor đã hết hạn, không còn dữ liệu để replay hoặc client đã nhận trùng event.
5. Hỗ trợ xử lý idempotent/deduplication ở consumer khi cần.

Trong ví dụ `Flux.interval` phần 4, event ID sẽ lặp lại sau mỗi subscription, nên header `Last-Event-ID` **không đủ để khôi phục chính xác**. Không tuyên bố đạt exactly-once chỉ vì đã thêm retry và Last-Event-ID.

## 14. LoadBalancer, health check và kết nối đang mở

LoadBalancer chọn ứng viên từ danh sách `ServiceInstanceListSupplier`. Chuỗi supplier có thể kết hợp discovery, cache, zone preference hoặc health check. Những cơ chế đó giúp **request mở mới** tránh instance không còn phù hợp, nhưng không tự chuyển một SSE response đã mở sang server khác.

Ví dụ:

| Sự kiện | Subscription đang nhận từ B | Subscription mới |
|---|---|---|
| B vẫn healthy | Tiếp tục nhận event | Có thể chọn A hoặc B |
| Health check đánh dấu B unhealthy nhưng socket còn sống | Có thể tiếp tục nhận từ B | Có thể tránh B theo supplier policy |
| B dừng, TCP bị reset | Luồng lỗi/cancel; cần reconnect | Có thể chọn A nếu A nằm trong danh sách |
| A vừa được thêm vào discovery | Luồng B không tự chuyển sang A | Có thể chọn A khi supplier cập nhật |
| Tất cả instance bị lọc khỏi danh sách | Luồng đã mở không nhất thiết mất ngay | Request mới có thể thất bại ở bước chọn |

Hành vi health khi **không còn instance healthy** có thể có fallback tùy supplier/phiên bản. Không giả định mọi trường hợp đều trả danh sách rỗng; cần kiểm chứng tập ứng viên thực tế.

Nếu ứng dụng yêu cầu phiên streaming **bám session** hoặc state chỉ lưu ở B, việc reconnect sang A có thể mất trạng thái. Khi đó, cần thiết kế event store dùng chung, session replication hoặc routing affinity có kiểm soát thay vì mong Round Robin duy trì tính liên tục.

## 15. Quan sát luồng dài trong production

Đối với SSE, chỉ đo số HTTP request không đủ. Một request có thể kéo dài cả giờ và truyền hàng triệu event.

| Nhóm tín hiệu | Gợi ý đo |
|---|---|
| Load balancing | Service ID, instance được chọn, tỷ lệ mở stream theo instance |
| Kết nối | Active SSE streams, active/pending connections, kết nối lỗi |
| Chất lượng luồng | Time-to-first-event, khoảng cách event, độ dài stream |
| Backpressure | Consumer throughput, bounded queue size, overflow/drop count |
| Retry | Số lần reconnect, backoff, lý do ngắt và instance sau reconnect |
| Health | Tập instance từ discovery, tình trạng probe, thời gian hội tụ |
| Dữ liệu | Event ID mới nhất, duplicate/gap count nếu có replay |
| Tài nguyên | Heap/direct memory, CPU, event-loop latency, pool saturation |

Có thể kết hợp Micrometer/Actuator, Reactor Netty metrics, server metrics và log vòng đời `doOnSubscribe`/`doFinally`. Nên dùng cùng correlation/trace ID để nối việc mở stream, chọn instance và kết thúc stream. Tránh log toàn bộ payload SSE hoặc gắn event ID/user ID không giới hạn vào metric tags vì vấn đề bảo mật và cardinality.

### Lab kiểm chứng cancellation và chuyển instance

1. Khởi động hai backend ở cổng `18081`, `18082` và caller ở `18090`.
2. Mở `curl -N http://localhost:18090/demo/stock-stream`. Ghi lại `instanceId` từ các event; xác nhận các event trong một kết nối đến từ một instance.
3. Mở thêm vài terminal/consumer; quan sát việc tạo nhiều subscription độc lập và phân phối theo LoadBalancer.
4. Dừng consumer bằng Ctrl+C; xác nhận log `doOnCancel` hoặc `doFinally(CANCEL)` và số active streams giảm.
5. Dừng backend đang phục vụ một stream; quan sát lỗi/ngắt kết nối. Nếu có retry policy, kiểm tra lần subscribe mới và instance được chọn.
6. Khởi động lại backend; xác minh request mới có thể dùng nó sau khi discovery/supplier cập nhật.
7. Làm consumer chậm có kiểm soát; đo queue/memory, sau đó thử bounded concurrency hoặc chính sách drop phù hợp nghiệp vụ.
8. Tăng số concurrent SSE connections trong môi trường test để kiểm tra pool limit, pending acquisition và server capacity. Không dùng bài stress test này trên môi trường đang phục vụ người dùng.

Kết quả cần ghi:

| Kịch bản | Kỳ vọng cần quan sát | Điều cần phân biệt |
|---|---|---|
| Một subscriber SSE | Một instance phục vụ toàn luồng | Không Round Robin theo từng event |
| Nhiều subscriber | Mỗi subscription có thể được chọn riêng | Công bằng số kết nối khác công bằng tải |
| Client hủy | Upstream được cancel và giải phóng tài nguyên | Không giữ background subscribe ngoài ý muốn |
| Backend chết giữa luồng | Lỗi hoặc đóng connection | HTTP status đã gửi không đổi thành 503 |
| Reconnect | Request mới và khả năng chọn instance khác | Không mặc nhiên có replay event |
| Consumer chậm | Buffer/concurrency lộ điểm nghẽn | Demand không luôn điều khiển tốc độ server |
| Heartbeat thưa hơn timeout | Có thể bị đóng vì idle | Kết nối còn sống khác event nghiệp vụ |
| Health loại B | Request mới có thể tránh B | Stream hiện hữu không tự migrate |

## 16. Các lỗi thiết kế thường gặp

- Tưởng rằng `@LoadBalanced` chọn instance mới cho **mỗi event** trong một SSE response; thực tế nó chọn đích ở bước gửi HTTP request.
- Dùng `WebClient.create()` thay vì builder `@LoadBalanced` rồi hy vọng URL service ID vẫn đi qua Spring Cloud discovery.
- Dùng `collectList()` hoặc `blockLast()` trên `Flux` vô hạn: request không hoàn tất hoặc bộ nhớ tăng không kiểm soát.
- Dùng `cache()` của Reactor trên `Flux` vô hạn mà không giới hạn lịch sử: có thể giữ vô hạn sự kiện đã phát, khác hoàn toàn instance cache của LoadBalancer.
- Dùng `onBackpressureBuffer()` không giới hạn khi server gửi nhanh hơn subscriber xử lý.
- Dùng `onBackpressureLatest()` cho event nghiệp vụ không được phép mất.
- Gọi mã blocking trực tiếp trên reactor event-loop.
- Mở subscription bằng `subscribe()` thủ công nhưng không sở hữu `Disposable` để hủy.
- Cấu hình read/response timeout quá ngắn so với khoảng event/heartbeat.
- Retry không giới hạn mà không bảo đảm replay, idempotency và xử lý duplicate/gap.
- Gộp lỗi HTTP status ban đầu với lỗi I/O **sau khi luồng đã bắt đầu** thành cùng một nhóm mà không có trace.
- Chỉ đo request rate mà không đo concurrent streams, event rate, connection pool và thời gian stream tồn tại.

## 17. Checklist triển khai và kết luận

Trước khi phát hành một dịch vụ streaming sử dụng WebClient với Spring Cloud LoadBalancer, cần trả lời:

1. Đây là SSE/NDJSON có thể stream liên tục hay là JSON hữu hạn nên dùng `Mono<T>`?
2. Có bean `@LoadBalanced WebClient.Builder` và service ID đúng với discovery không?
3. Đối với mỗi subscription, hiểu instance sẽ được **chọn một lần** và giữ trong suốt HTTP response chưa?
4. Luồng có khi nào tự hoàn tất? Ai hủy nó khi downstream ngắt?
5. Demand của Reactor có thể áp dụng đến nguồn thật không, hay chỉ ảnh hưởng đến buffer/decoder?
6. Consumer chậm thì chính sách là bounded queue, drop snapshot, load shedding hay replay?
7. Có tác vụ blocking nào đang chạy trên event-loop không?
8. Connect, response/read idle và application idle timeout có phù hợp heartbeat không?
9. Số active connections/streams và pending acquisition có được giới hạn, đo và cảnh báo không?
10. Khi retry, có bảo vệ số lần thử và cung cấp cursor/Last-Event-ID nếu nghiệp vụ đòi hỏi không bỏ sót dữ liệu không?
11. Nếu reconnect sang instance khác, cả hai có thể truy cập cùng nguồn event và replay không?
12. Health check và discovery có được thiết kế cho **request mới**, thay vì giả định sẽ tự migrate stream đang mở, không?
13. Có log/tracing đủ để phân biệt lựa chọn instance, response ban đầu, lỗi I/O, cancel và reconnect không?

**Nguyên tắc cốt lõi:** `WebClient` hỗ trợ xử lý response streaming theo mô hình reactive, nhưng **backpressure chỉ hiệu quả trong phạm vi những thành phần tôn trọng demand**; nó không tự kiểm soát hoàn toàn tốc độ dữ liệu từ server HTTP. Spring Cloud LoadBalancer chọn `ServiceInstance` cho **mỗi HTTP request** chứ không phân phối từng SSE event. Để vận hành kết nối dài ổn định, phải kết hợp streaming decoder, cancellation đúng vòng đời, giới hạn concurrency và buffer, timeout phù hợp heartbeat, retry/replay có ngữ nghĩa rõ ràng, và quan sát liên tục tải trên từng instance.

