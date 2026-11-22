# Timeout, hủy đăng ký và tác động lên lời gọi đang chạy

Trong Spring Cloud LoadBalancer, `WebClient` có thể gọi một dịch vụ bằng service ID, chẳng hạn `http://inventory-service`, thay vì địa chỉ IP cố định. LoadBalancer chọn `ServiceInstance` thích hợp từ discovery, nhưng **việc chọn được instance không có nghĩa request sẽ hoàn tất đúng hạn**. Một bản sao có thể phản hồi chậm, kết nối bị gián đoạn, client ngừng quan tâm đến kết quả hoặc service đích bị gỡ khỏi registry khi request đang chạy.

Bài thuộc chương **WebClient** của module `SPRING_CLOUD_SERVICE_COMMUNICATION_LOAD_BALANCING`. Mục tiêu của module là hiểu cơ chế client-side load balancing theo service ID, discovery, health check và chính sách định tuyến; kết hợp `RestClient`, `WebClient`, OpenFeign, retry/timeout và quan sát lỗi để giao tiếp dịch vụ ổn định. Bài này đi sâu vào ba vấn đề dễ bị trộn lẫn: **timeout**, **hủy subscription** trong lập trình reactive và **tác động lên lời gọi HTTP đã được khởi động**.

Cụm từ *hủy đăng ký* trong ngữ cảnh Reactor/WebClient chủ yếu có nghĩa **cancel hoặc dispose một `Subscription`**, tức người nhận không còn yêu cầu kết quả từ `Publisher`. Nó **khác** với thao tác *deregister* một `ServiceInstance` khỏi service registry. Bài sẽ phân biệt hai cách hiểu và giải thích tác động của từng cách đối với request đang bay (*in-flight request*).

## 1. Kết quả cần đạt

Sau bài học, bạn có thể:

- Giải thích tại sao `WebClient` trả về `Mono` hoặc `Flux` và thời điểm HTTP request thực sự bắt đầu.
- Phân biệt connect timeout, response/read timeout, timeout của pipeline Reactor và thời hạn tổng thể (*deadline*).
- Hiểu `timeout(...)` phát lỗi cho downstream đồng thời hủy subscription phía upstream như thế nào.
- Phân biệt **client ngừng chờ**, **transport được giải phóng** và **server ngừng xử lý**: ba việc này không đồng nghĩa.
- Thiết kế retry, timeout và fallback không tạo request trùng hoặc làm quá tải bản sao đích.
- Kiểm chứng hành vi hủy bằng `doOnCancel`, `doFinally`, test reactive và quan sát server.
- Giải thích điều gì xảy ra nếu một `ServiceInstance` bị deregister khi request tới instance đó đã được gửi đi.

## 2. Một WebClient request có vòng đời như thế nào?

Giả sử trong `order-service` có client gọi `inventory-service`:

~~~java
Mono<StockResponse> result = webClient.get()
    .uri("http://inventory-service/api/stock/{sku}", "SKU-42")
    .retrieve()
    .bodyToMono(StockResponse.class);
~~~

Biểu thức trên mô tả một pipeline reactive. **Bản thân việc tạo `Mono` không đồng nghĩa HTTP request đã được gửi ngay.** Với `WebClient`, request được kích hoạt khi có subscriber: WebFlux runtime subscribe vào `Mono` được controller trả về, hoặc một thành phần khác gọi `subscribe()`, `block()` trong ngữ cảnh được phép, hoặc dùng operator tương đương dẫn đến subscription.

~~~mermaid
sequenceDiagram
    participant App as Order application
    participant M as Mono/Subscriber
    participant LB as Reactive LoadBalancer
    participant Sup as Instance supplier
    participant Inv as Inventory replica
    App->>M: Xây pipeline WebClient
    Note over App,M: Chưa nhất thiết có HTTP request
    App->>M: Subscribe
    M->>LB: Khởi động request tới inventory-service
    LB->>Sup: Lấy ServiceInstance
    Sup-->>LB: Tập ứng viên
    LB->>LB: Chọn inv-b
    LB->>Inv: HTTP request tới host:port
    Inv-->>LB: HTTP response
    LB-->>M: Body / completion hoặc lỗi
    M-->>App: onNext, onComplete / onError
~~~

Nếu cùng một `Mono` lạnh (*cold publisher*) được subscribe nhiều lần, mỗi subscription có thể khởi động **một lời gọi HTTP riêng**. Điều này đặc biệt quan trọng khi retry, repeat hoặc một đoạn code subscribe thủ công rồi WebFlux framework cũng subscribe.

### Các trạng thái quan trọng

| Trạng thái | Mô tả | Có thể hủy không? |
|---|---|---|
| Chỉ mới tạo pipeline | Chưa có subscription | Không có HTTP request đang chạy để hủy |
| Đang chờ chọn instance | Đang truy xuất supplier/LoadBalancer | Cancellation có thể ngừng chờ trước khi gửi HTTP |
| Đang chờ connection | Pool đang cấp hoặc tạo kết nối | Cancellation có thể hủy nhu cầu kết nối, tùy transport |
| Request đang gửi/đã gửi | Server có thể đã nhận request | Client có thể hủy subscription nhưng không bảo đảm server ngừng |
| Đang đọc response body | Dữ liệu có thể được stream nhiều phần | Hủy thường dừng việc nhận dữ liệu còn lại ở client |
| Đã complete hoặc error | Pipeline đã kết thúc | Hủy sau đó không đảo ngược tác động đã xảy ra |

`Mono` đại diện cho tối đa một phần tử dữ liệu, còn `Flux` có thể phát nhiều phần tử. Cả hai đều tuân theo cơ chế `Subscription` của Reactive Streams và có thể nhận tín hiệu cancellation.

## 3. Timeout không phải một cấu hình duy nhất

Khi gọi HTTP, có nhiều giai đoạn khác nhau:

~~~text
Subscribe
   |
   +--> Chọn ServiceInstance qua LoadBalancer
   +--> DNS / tìm địa chỉ vật lý
   +--> Chờ lấy connection trong pool
   +--> Thiết lập TCP và TLS (nếu dùng HTTPS)
   +--> Gửi request
   +--> Chờ response headers
   +--> Đọc response body
   +--> Deserialize / xử lý reactive operators
   |
   v
Complete / Error / Cancel
~~~

Mỗi timeout thường bao phủ một phần khác nhau:

| Loại | Điểm áp dụng | Khi quá hạn |
|---|---|---|
| **Connect timeout** | Thời gian thiết lập kết nối TCP | Transport phát lỗi kết nối |
| **Pool acquisition timeout** | Chờ có connection từ pool | Không lấy được connection đúng hạn |
| **TLS handshake timeout** | Giai đoạn thiết lập TLS | Lỗi handshake/transport |
| **Response/read timeout** | Chờ hoặc đọc response theo semantics của HTTP client | Lỗi timeout từ transport |
| **`Mono.timeout(Duration)`** | Khoảng chờ tín hiệu từ upstream theo operator Reactor | Downstream nhận lỗi `TimeoutException`; upstream bị cancel |
| **Deadline tổng thể** | Ngân sách thời gian cho toàn bộ nghiệp vụ | Cần được thiết kế xuyên các attempt, backoff, xử lý và downstream |

Hai lỗi timeout không nhất thiết có cùng exception. `Mono.timeout(Duration)` sử dụng cơ chế timeout của Reactor; một timeout ở Netty hoặc pool có thể phát ra loại lỗi khác, có thể được bọc trong exception của HTTP client.

**Không nên chỉ đặt response timeout rồi tuyên bố lời gọi có deadline tổng thể.** Khoảng chờ trong pool, chọn instance, handshake, decode và retry có thể không được bao phủ giống nhau. Ngược lại, `Mono.timeout` tính thời gian trong pipeline chứ không trực tiếp điều chỉnh toàn bộ socket timeout bên dưới.

## 4. Tích hợp WebClient với Spring Cloud LoadBalancer

Ví dụ sử dụng WebClient trong `order-service` để gọi hostname logic `inventory-service`.

Về dependency, ứng dụng caller cần phiên bản Spring Boot/Spring Cloud tương thích, phần WebClient của Spring WebFlux và Spring Cloud LoadBalancer. Một cấu hình Gradle minh họa:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.cloud:spring-cloud-starter-loadbalancer'
}
~~~

Spring Cloud BOM cần được quản lý tương thích với Spring Boot. Nếu dùng Eureka/Consul/Kubernetes, bổ sung discovery adapter tương ứng; nếu dùng SimpleDiscoveryClient cho bài thử nghiệm, có thể khai báo danh sách instance tĩnh.

Khai báo `WebClient.Builder` có load balancing:

~~~java
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration(proxyBeanMethods = false)
public class WebClientConfiguration {

    @Bean
    @LoadBalanced
    WebClient.Builder loadBalancedWebClientBuilder() {
        return WebClient.builder();
    }

    @Bean
    WebClient inventoryWebClient(
            @LoadBalanced WebClient.Builder builder) {
        return builder.clone()
                .baseUrl("http://inventory-service")
                .build();
    }
}
~~~

Khi được cấu hình đúng, Spring Cloud đưa cơ chế `ReactorLoadBalancerExchangeFilterFunction` hoặc thành phần tương ứng vào `WebClient.Builder` có marker `@LoadBalanced`. Hostname `inventory-service` được hiểu như **service ID** để chọn `ServiceInstance`; request cuối vẫn là HTTP tới host/port đã chọn.

Cấu hình đơn giản cho local:

~~~yaml
spring:
  application:
    name: order-service
  cloud:
    discovery:
      client:
        simple:
          instances:
            inventory-service:
              - uri: http://localhost:8081
              - uri: http://localhost:8082
~~~

Hai bản sao đích phải thực sự chạy ở các port đó. SimpleDiscoveryClient chỉ cung cấp địa chỉ tĩnh; nó không tự xóa một instance vừa chết. `@LoadBalanced` cũng không tự thêm timeout hay retry phù hợp cho nghiệp vụ.

## 5. Timeout bằng operator Reactor

Giả sử `inventoryWebClient` là bean `WebClient` được cấu hình ở trên:

~~~java
import java.time.Duration;
import org.springframework.stereotype.Component;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;

@Component
public class InventoryGateway {

    private final WebClient inventoryWebClient;

    public InventoryGateway(WebClient inventoryWebClient) {
        this.inventoryWebClient = inventoryWebClient;
    }

    public Mono<StockResponse> getStock(String sku) {
        return inventoryWebClient.get()
                .uri("/api/stock/{sku}", sku)
                .retrieve()
                .bodyToMono(StockResponse.class)
                .timeout(Duration.ofSeconds(2));
    }
}
~~~

Hợp đồng response có thể là:

~~~java
public record StockResponse(
        String sku,
        boolean available,
        int quantity
) {}
~~~

`timeout(Duration.ofSeconds(2))` ở đây được áp dụng cho `Mono` response. Nếu upstream không phát tín hiệu cần thiết trong thời gian quy định, downstream nhận `TimeoutException`, đồng thời Reactor gửi tín hiệu **cancel** tới upstream.

Với một `Mono` chỉ có kết quả sau khi đọc và decode toàn bộ response, timeout có thể bao phủ thời gian chờ **đến khi Mono phát ra phần tử hoặc kết thúc**. Với `Flux`, overload `timeout(Duration)` thông thường giám sát thời gian chờ tín hiệu đầu và khoảng cách giữa các tín hiệu, **không phải luôn là tổng thời lượng của cả stream**. Nếu cần deadline toàn phiên streaming, phải thiết kế khác thay vì giả định một timeout giữa các phần tử là đủ.

### Đặt timeout trước hay sau xử lý?

Ví dụ:

~~~java
return inventoryWebClient.get()
        .uri("/api/stock/{sku}", sku)
        .retrieve()
        .bodyToMono(StockResponse.class)
        .timeout(Duration.ofSeconds(2))
        .map(this::normalize);
~~~

Trong ví dụ này, `timeout` đứng trước `map`. Nó giám sát pipeline upstream tới lúc có response, không áp đặt một deadline riêng lên công việc `normalize` ở downstream. Nếu muốn bao phủ cả xử lý reactive sau response, có thể đặt timeout ở ngoài chuỗi bao gồm bước xử lý đó.

Operator placement là một phần của hợp đồng thời gian, không chỉ là cách sắp xếp code.

## 6. Cancellation: hủy Subscription có nghĩa gì?

Trong Reactor, `subscribe()` tạo một subscription vào publisher. API `subscribe(...)` thường trả một `Disposable`; gọi `dispose()` là một cách chủ động yêu cầu hủy subscription đó.

Ví dụ **chỉ dùng để minh họa**, không phải mẫu khuyến nghị cho code controller:

~~~java
import reactor.core.Disposable;

Disposable subscription = inventoryWebClient.get()
        .uri("/api/stock/SKU-42")
        .retrieve()
        .bodyToMono(StockResponse.class)
        .subscribe(
            response -> System.out.println(response),
            error -> System.err.println(error)
        );

// Khi thực sự không còn cần kết quả:
subscription.dispose();
~~~

Nếu `dispose()` được gọi trước khi pipeline hoàn tất, subscriber ngừng nhận kết quả. Trong WebFlux, **không nên tự gọi `subscribe()` trong controller** chỉ để kích hoạt một request rồi trả về; hãy trả `Mono` hoặc `Flux` để framework quản lý lifecycle và chuyển cancellation khi client phía trước ngắt kết nối.

Phân biệt ba trường hợp:

1. **Complete**: publisher đã trả kết quả và kết thúc bình thường.
2. **Error**: publisher kết thúc bằng tín hiệu lỗi.
3. **Cancel**: downstream nói rằng không còn quan tâm đến dữ liệu upstream.

Cancellation **không phải** `onError`. Khi subscriber tự cancel, nó thường không nhận thêm `onError` hoặc `onComplete`. Tại một operator `timeout`, downstream thấy lỗi timeout, nhưng upstream bị hủy; hai tín hiệu nằm ở **hai phía khác nhau của operator**.

## 7. `timeout()` và `doOnCancel()` khác nhau ra sao?

Ví dụ quan sát cả hai phía của một timeout:

~~~java
import java.time.Duration;
import java.util.concurrent.TimeoutException;
import reactor.core.publisher.Mono;
import reactor.core.publisher.SignalType;

Mono<StockResponse> source =
    inventoryWebClient.get()
        .uri("/api/stock/SKU-42")
        .retrieve()
        .bodyToMono(StockResponse.class)
        .doOnCancel(() ->
            System.out.println("Upstream cancelled"))
        .doFinally(signal ->
            System.out.println("Upstream: " + signal));

Mono<StockResponse> result = source
    .timeout(Duration.ofSeconds(2))
    .doFinally(signal ->
        System.out.println("Downstream: " + signal));
~~~

Nếu `source` không có kết quả trong 2 giây:

- Operator `timeout` phát `TimeoutException` xuống downstream.
- `source` ở upstream nhận tín hiệu hủy.
- `doOnCancel` ở upstream có thể chạy.
- `doFinally` đặt **trước** timeout quan sát `SignalType.CANCEL`.
- `doFinally` đặt **sau** timeout thường quan sát `SignalType.ON_ERROR`.

Tình huống này dễ dẫn đến log tưởng như mâu thuẫn: cùng một request có **CANCEL** ở upstream và **ERROR** ở downstream. Thực tế, đó là hai cách nhìn về cùng một thời điểm timeout ở hai vị trí trong chuỗi operator.

`doFinally` cũng chạy khi publisher hoàn tất bình thường, nên nó thích hợp để giải phóng một số tài nguyên hoặc ghi kết quả theo tín hiệu kết thúc. Tuy nhiên, không đưa xử lý blocking hay IO nặng trực tiếp vào callback theo cách cản trở event loop.

## 8. Hủy subscription có dừng HTTP request ở server không?

Đây là phân biệt quan trọng nhất.

~~~mermaid
sequenceDiagram
    participant Caller as Order WebClient
    participant Netty as HTTP transport
    participant Server as Inventory service
    Caller->>Netty: Subscribe, gửi GET/POST
    Netty->>Server: HTTP request
    Note over Server: Server bắt đầu xử lý
    Note over Caller: Deadline 2 giây hết hạn
    Caller->>Caller: timeout -> downstream onError
    Caller->>Netty: Cancel upstream
    Netty--xServer: Có thể đóng/hủy trao đổi HTTP
    Note over Server: Xử lý có thể đã chạy hoặc đã commit
    Note over Caller,Server: Cancellation không phải rollback giao dịch
~~~

Cơ chế transport, ví dụ Reactor Netty, có thể phản ứng với cancellation bằng cách dừng đọc response, hủy request chưa gửi hoặc đóng/giải phóng tài nguyên mạng tùy trạng thái hiện tại. Nhưng **không có bảo đảm tổng quát rằng server sẽ dừng công việc ngay lập tức**.

Nếu server đã nhận `POST /orders`, nó có thể đã ghi database trước khi caller timeout. Trường hợp caller không nhận response **không chứng minh server chưa xử lý**.

| Vị trí khi hủy | Điều có thể xảy ra | Điều không được mặc định |
|---|---|---|
| Trước khi có kết nối | Hủy chờ connection | Đã có HTTP request trên server |
| Trước khi gửi toàn bộ request | Dừng truyền tiếp | Server chắc chắn không nhận phần nào |
| Sau khi server nhận request | Client thôi chờ/đọc | Server tự động dừng logic nghiệp vụ |
| Sau khi server commit | Caller vẫn có thể báo timeout | Giao dịch được rollback |
| Khi stream body | Dừng nhận các phần tiếp theo | Mọi tác vụ downstream đều được hủy |

Vì vậy, hãy tách ba câu hỏi vận hành: *client còn chờ không?*, *connection/stream còn hoạt động không?*, và *server đã hoàn tất nghiệp vụ chưa?* Ba kết quả có thể khác nhau.

## 9. Cấu hình timeout tại HTTP transport: Reactor Netty

Bên cạnh timeout ở pipeline Reactor, bạn có thể đặt timeout liên quan trực tiếp đến transport khi ứng dụng sử dụng Reactor Netty:

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
public class InventoryHttpTimeoutConfiguration {

    @Bean
    @LoadBalanced
    WebClient.Builder loadBalancedWebClientBuilder() {
        HttpClient httpClient = HttpClient.create()
            .option(ChannelOption.CONNECT_TIMEOUT_MILLIS, 1_000)
            .responseTimeout(Duration.ofSeconds(3));

        return WebClient.builder()
            .clientConnector(new ReactorClientHttpConnector(httpClient));
    }
}
~~~

Với cấu hình này:

- `CONNECT_TIMEOUT_MILLIS` giới hạn một giai đoạn thiết lập kết nối TCP.
- `responseTimeout(Duration)` của Reactor Netty áp dụng timeout phản hồi theo semantics của phiên bản transport.
- Timeout từ Netty có thể mang loại exception khác với `java.util.concurrent.TimeoutException` do Reactor `Mono.timeout` phát ra.
- Các timeout trên không bao hàm mọi bước từ chọn instance, chờ pool, retry tới deserialize theo cùng một ngân sách tổng thể.

**Đây là cấu hình thay thế** cho bean `@LoadBalanced WebClient.Builder` ở phần 4, không phải bean thứ hai cùng loại nên khai báo song song. Khi dùng một `WebClient` cho nhiều service, cần cân nhắc dùng chung connector và connection pool, tránh tạo `HttpClient` mới cho mỗi request.

Một số hệ thống dùng HTTP client implementation khác. Khi đó, thuộc tính timeout và loại exception cụ thể phải dựa trên transport thực tế, không áp đặt cấu hình Reactor Netty cho tất cả WebClient.

## 10. Deadline cho toàn bộ lời gọi và chuỗi retry

Timeout của mỗi attempt và deadline tổng thể là hai khái niệm khác nhau.

Giả sử mỗi lần thử được phép tối đa 800 ms, tối đa 1 lần retry và có backoff. Nếu không có deadline tổng, tổng thời gian có thể vượt xa 800 ms.

~~~mermaid
flowchart LR
    A["Subscribe"] --> B["Attempt 1: timeout 800ms"]
    B --> C{"Thành công?"}
    C -- Không --> D["Backoff"]
    D --> E["Attempt 2: timeout 800ms"]
    E --> F["Kết quả"]
    C -- Có --> F
    G["Deadline 2s"] -.-> B
    G -.-> D
    G -.-> E
~~~

Ví dụ:

~~~java
import java.time.Duration;
import java.util.concurrent.TimeoutException;
import reactor.core.publisher.Mono;
import reactor.util.retry.Retry;

public Mono<StockResponse> getStockWithRetry(String sku) {
    Mono<StockResponse> oneAttempt = Mono.defer(() ->
        inventoryWebClient.get()
            .uri("/api/stock/{sku}", sku)
            .retrieve()
            .bodyToMono(StockResponse.class)
            .timeout(Duration.ofMillis(800)));

    return oneAttempt
        .retryWhen(Retry.backoff(1, Duration.ofMillis(150))
            .filter(TimeoutException.class::isInstance))
        .timeout(Duration.ofSeconds(2));
}
~~~

Ở đây:

1. `Mono.defer` tạo lại phần gọi HTTP khi có subscription cho mỗi attempt.
2. Timeout `800 ms` nằm **bên trong** `retryWhen`, nên được áp dụng riêng cho mỗi attempt.
3. `Retry.backoff(1, ...)` cho phép nhiều nhất một lần thử lại sau lần đầu đối với lỗi được lọc; tổng tối đa hai attempt.
4. Timeout `2 giây` nằm **bên ngoài** `retryWhen`, nên giới hạn cả attempt và backoff của chuỗi này.

Đây là ví dụ định hướng, không phải policy phù hợp với tất cả API. Lỗi connect timeout từ HTTP client có thể là loại khác nên không nhất thiết được predicate `TimeoutException.class::isInstance` nhận diện. Cần xác định loại exception thật và giới hạn retry riêng cho từng lớp lỗi.

Nếu timeout tổng kích hoạt giữa backoff hoặc giữa một attempt, subscription upstream bị cancel. Retry không nên tiếp tục tạo thêm attempt mới sau khi caller đã hết deadline và hủy chuỗi.

## 11. Đặt `retryWhen` trước hay sau `timeout`?

Hai cách bố trí dưới đây có semantics khác nhau:

**Timeout theo attempt; có thể retry sau timeout:**

~~~java
source.timeout(Duration.ofMillis(800))
      .retryWhen(retrySpec);
~~~

Lỗi timeout của attempt được chuyển vào retry operator, nên có thể tạo subscription/request mới nếu policy cho phép.

**Timeout toàn chuỗi retry:**

~~~java
source.retryWhen(retrySpec)
      .timeout(Duration.ofSeconds(2));
~~~

Deadline ở ngoài có thể hủy chuỗi retry khi tổng thời gian vượt giới hạn.

Trong ứng dụng thực, thường cần **cả ngân sách mỗi attempt và ngân sách tổng** (như ví dụ trước), đồng thời xét retry của proxy, service mesh hoặc các lớp downstream. Retry của mỗi tầng có thể nhân số lời gọi đến server và làm tải tăng nhanh.

Với `GET` chỉ đọc dữ liệu, retry có kiểm soát thường hợp lý hơn. Với `POST` tạo đơn hàng, thanh toán hoặc ghi dữ liệu, cần idempotency key, kiểm tra trạng thái giao dịch hoặc hợp đồng retry rõ ràng. **Timeout không biến một operation có side effect thành operation an toàn để gửi lại**.

## 12. Fallback không đồng nghĩa server đã dừng xử lý

Ví dụ fallback khi pipeline hết thời gian:

~~~java
import java.time.Duration;
import java.util.concurrent.TimeoutException;
import reactor.core.publisher.Mono;

public Mono<StockResponse> getStockOrUnknown(String sku) {
    return inventoryWebClient.get()
        .uri("/api/stock/{sku}", sku)
        .retrieve()
        .bodyToMono(StockResponse.class)
        .timeout(Duration.ofSeconds(2))
        .onErrorResume(
            TimeoutException.class,
            ex -> Mono.just(new StockResponse(sku, false, -1))
        );
}
~~~

Ở ví dụ này, `quantity=-1` là mã quy ước minh họa cho trạng thái chưa xác định, **không phải số tồn kho hợp lệ**. Nếu nghiệp vụ cần phân biệt không có hàng với không biết do timeout, nên dùng một DTO biểu diễn rõ `UNKNOWN`, `AVAILABLE`, `UNAVAILABLE` thay vì nhập nhằng một giá trị boolean.

Dù caller nhận fallback, request gốc có thể đã đến server. Với thao tác ghi, không được trả “chắc chắn thất bại, chưa ghi gì” chỉ vì client timeout.

Cũng nên phân biệt `onErrorResume` với `onErrorReturn`: cả hai xử lý tín hiệu lỗi downstream, nhưng không tạo bảo đảm mới về trạng thái server hoặc network request đã gửi.

## 13. Hủy đăng ký ở service registry là chuyện khác

Trong hệ thống service discovery, “hủy đăng ký instance” cũng có thể có nghĩa **deregister một `ServiceInstance` khỏi Eureka, Consul hoặc danh sách endpoint của nền tảng**. Hành động này khác hoàn toàn với `Subscription.cancel()` của Reactor.

Giả sử:

~~~text
t0: order-service chọn inv-b từ discovery
t1: HTTP request đã gửi tới inv-b
t2: inv-b được gỡ khỏi registry hoặc chuyển not-ready
t3: inv-b vẫn đang xử lý request đã nhận
t4: request thành công hoặc lỗi tùy tình trạng thực tế
~~~

Deregister ảnh hưởng chủ yếu đến **các lượt lựa chọn instance mới sau khi discovery/supplier cập nhật**. Nó **không tự động hủy socket, HTTP exchange hay transaction đã mở** trên `inv-b`.

~~~mermaid
sequenceDiagram
    participant O as Order WebClient
    participant LB as LoadBalancer
    participant R as Registry
    participant I as inv-b
    O->>LB: Gọi inventory-service
    LB->>R: Danh sách instance hiện biết
    R-->>LB: inv-a, inv-b
    LB->>I: Gửi HTTP request tới inv-b
    Note over I: Request đang được xử lý
    I-->>R: Deregister / Not-ready
    Note over R,LB: Discovery/cache có thể cập nhật trễ
    I-->>O: Có thể vẫn trả response
~~~

Tác động thực tế phụ thuộc server shutdown:

- **Graceful shutdown / connection draining**: cho phép request đang chạy hoàn tất trong một khoảng thời gian, đồng thời ngừng nhận request mới theo chính sách.
- **Kill ngay lập tức**: có thể cắt request đang chạy, gây lỗi kết nối ở caller.
- **Registry/cache cập nhật chậm**: caller có thể tiếp tục chọn instance đang rời hệ thống cho đến khi danh sách được làm mới.
- **Retry**: nếu được cấu hình, lần thử tiếp theo có thể chọn instance khác; điều này không bảo đảm attempt đầu chưa thực hiện side effect.

Vì vậy, hãy phối hợp readiness, deregistration, thời gian drain, termination grace period và timeout của client. Mục tiêu là giảm request mới vào replica sắp tắt, đồng thời cho request in-flight có cơ hội hoàn tất.

## 14. WebClient `Flux` và hủy giữa luồng dữ liệu

Với response streaming (Server-Sent Events, NDJSON hoặc stream các phần tử), hủy subscription có thể xảy ra **sau khi đã nhận một phần dữ liệu**.

~~~java
import java.time.Duration;
import reactor.core.publisher.Flux;

public Flux<EventDto> streamEvents() {
    return inventoryWebClient.get()
        .uri("/api/events")
        .retrieve()
        .bodyToFlux(EventDto.class)
        .take(10);
}
~~~

`take(10)` có thể gửi cancellation upstream sau khi nhận đủ 10 phần tử, vì downstream không cần phần tử tiếp theo. Không phải mọi cancellation là lỗi: việc ngừng đọc một stream dài sau khi đạt mục tiêu có thể là hành vi đúng.

Nếu thay bằng:

~~~java
return inventoryWebClient.get()
    .uri("/api/events")
    .retrieve()
    .bodyToFlux(EventDto.class)
    .timeout(Duration.ofSeconds(3));
~~~

thì timeout ở `Flux` thông thường phát sinh khi chờ phần tử đầu hoặc **khoảng giữa các phần tử** vượt thời hạn. Một stream có phần tử liên tục có thể chạy lâu hơn 3 giây mà không timeout.

Khi cần giới hạn tổng thời gian stream, cần một chính sách lifecycle/đếm thời gian dành cho toàn phiên, đồng thời quy định rõ stream kết thúc tự nhiên, bị cancel hoặc phát lỗi. Với stream lớn, tránh vô tình gọi `collectList()` chỉ để dễ timeout vì có thể gom toàn bộ dữ liệu vào bộ nhớ.

## 15. Cancellation và tài nguyên: connection, DataBuffer, transaction

Một hệ thống reactive ổn định cần quan sát không chỉ exception mà cả việc giải phóng tài nguyên.

| Tài nguyên hoặc công việc | Khi cancellation xuất hiện | Điều cần kiểm chứng |
|---|---|---|
| Connection chưa được cấp | Việc chờ có thể dừng | Pending acquire có giảm, pool có rò rỉ không? |
| Connection đang dùng | Transport có thể kết thúc exchange, đóng hoặc trả connection về pool khi an toàn | Theo dõi connection active/idle và lỗi transport |
| Response body streaming | Ngừng đọc phần còn lại | Không giữ reference tới body/DataBuffer không được giải phóng |
| Server handler reactive | Có thể nhận cancellation nếu kết nối downstream phản ánh tín hiệu | Thao tác nghiệp vụ có thực sự ngừng hay vẫn chạy? |
| Database transaction phía server | Không có rollback xuyên mạng chỉ vì client cancel | Ghi nhận idempotency, commit và trạng thái kết quả |
| Observability tracing | Span phía client có thể kết thúc timeout trong khi server tiếp tục | Correlation ID và thời gian giữa các span |

Khi dùng `retrieve().bodyToMono(...) ` hoặc `bodyToFlux(...)`, Spring WebFlux/HTTP client có cơ chế quản lý body thông thường. Nếu thao tác thủ công với `ClientResponse`, `DataBuffer` hay streaming API thấp hơn, phải tuân thủ quy tắc tiêu thụ và giải phóng buffer của API sử dụng; không giữ buffer sau cancellation mà không có cơ chế release phù hợp.

Không sử dụng `Thread.interrupt()` như một thay thế tổng quát cho reactive cancellation. WebClient dùng giao thức Reactor và event loop; tín hiệu cancellation không tương đương với ngắt một thread đang thực hiện toàn bộ công việc.

## 16. Quan sát chính xác: CANCEL, TIMEOUT, HTTP 5xx và transport error

Một timeout có thể hiển thị dưới nhiều dạng log hoặc metric. Hãy phân tách:

| Quan sát | Có thể biểu thị | Không nhất thiết biểu thị |
|---|---|---|
| `TimeoutException` sau `Mono.timeout` | Operator Reactor hết thời gian chờ upstream | Server chưa nhận request |
| `doOnCancel` ở upstream | Downstream không còn cần kết quả | Remote transaction đã rollback |
| `doFinally(CANCEL)` | Phần pipeline đó bị cancel | Lỗi nghiệp vụ HTTP `5xx` |
| `WebClientResponseException` | Server đã gửi HTTP response lỗi được `retrieve()` xử lý | Kết nối mạng không thiết lập được |
| Network/connect/read timeout | Giai đoạn transport lỗi hoặc hết hạn | Luôn có thể retry an toàn |
| `No servers available` / no-instance | Không có ứng viên trong LoadBalancer | Server trả HTTP response thành công |

Ví dụ instrument theo từng subscription:

~~~java
import reactor.core.publisher.Mono;
import reactor.core.publisher.SignalType;

Mono<StockResponse> monitored = inventoryWebClient.get()
    .uri("/api/stock/{sku}", sku)
    .retrieve()
    .bodyToMono(StockResponse.class)
    .doOnSubscribe(s -> log.debug("inventory request subscribed"))
    .doOnCancel(() -> log.info("inventory upstream cancelled"))
    .doFinally(signal -> {
        if (signal == SignalType.CANCEL) {
            log.info("inventory upstream finished: cancel");
        }
    })
    .timeout(Duration.ofSeconds(2));
~~~

Trong snippet này, `log` giả định là logger đã có trong class. Các callback đặt **trước** timeout nhằm quan sát phía upstream; downstream sẽ nhận `TimeoutException` nếu chính operator này hết hạn.

Nên đo thời gian bằng metric tại lớp client, ghi service ID, mục đích nghiệp vụ, loại lỗi và trạng thái kết thúc. Cần kiểm soát cardinality: không dùng toàn bộ URL chứa ID động, trace ID hoặc request ID làm label metric không giới hạn. Correlation ID phù hợp hơn với structured log/tracing.

Khi kiểm tra một request thực tế, hãy đối chiếu ít nhất hai phía: log/tracing ở caller và log giao dịch ở server. Một `TimeoutException` chỉ cho biết **caller đã hết thời gian chờ theo quy tắc của nó**.

## 17. Kiểm thử cancellation mà không cần gửi HTTP thật

Có thể kiểm tra semantics của Reactor bằng test dùng `reactor-test` và thời gian ảo. Ví dụ:

~~~java
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.time.Duration;
import java.util.concurrent.TimeoutException;
import java.util.concurrent.atomic.AtomicBoolean;

import org.junit.jupiter.api.Test;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

class ReactorCancellationTest {

    @Test
    void timeoutCancelsUpstream() {
        AtomicBoolean cancelled = new AtomicBoolean();

        StepVerifier.withVirtualTime(() ->
                Mono.delay(Duration.ofSeconds(5))
                    .doOnCancel(() -> cancelled.set(true))
                    .timeout(Duration.ofSeconds(1)))
            .thenAwait(Duration.ofSeconds(1))
            .expectError(TimeoutException.class)
            .verify();

        assertTrue(cancelled.get());
    }
}
~~~

Test này chỉ chứng minh **timeout gửi cancel cho upstream Reactor**. Nó không chứng minh connection đã đóng hay server ngừng xử lý. Để kiểm thử HTTP end-to-end, cần môi trường kiểm soát được tốc độ phản hồi của server (ví dụ server thử nghiệm có endpoint delay), rồi kiểm tra:

1. Request được gửi đến đúng service ID và instance.
2. Caller nhận timeout theo ngưỡng đã đặt.
3. Connection pool không giữ tài nguyên vô hạn sau cancel.
4. Server có hay không tiếp tục công việc sau khi caller timeout.
5. Retry có tạo attempt tiếp theo không và có gửi trùng request không.
6. Deregister/stop instance giữa request có ảnh hưởng thế nào tới request hiện tại và request mới.

Khi dùng virtual time, cần tạo publisher và operator phụ thuộc scheduler trong lambda của `withVirtualTime` như ví dụ, để test thực sự điều khiển được thời gian. Với kiểm thử mạng thực, thời gian ảo không thay thế được timeout socket và lịch của HTTP transport.

## 18. Bài thực hành: timeout sau khi đã chọn instance

Giả sử có hai bản sao `inventory-service`:

~~~text
inv-a: localhost:8081 — trả lời nhanh trong khoảng 50ms
inv-b: localhost:8082 — giả lập xử lý chậm khoảng 5s
~~~

Cấu hình SimpleDiscoveryClient ở caller trỏ đến hai instance như phần trước. Cả hai phục vụ endpoint:

~~~http
GET /api/stock/SKU-42
~~~

Caller sử dụng `Mono.timeout(Duration.ofSeconds(2))` cho request.

**Các bước:**

1. Gọi nhiều lần và ghi instance ID trong response/tracing, thời gian chờ, kết quả `onComplete`/`onError`.
2. Khi request chọn `inv-a`, kỳ vọng trả kết quả trước deadline nếu hạ tầng ổn định.
3. Khi request chọn `inv-b`, kỳ vọng `Mono.timeout` kích hoạt nếu upstream không phát tín hiệu trong 2 giây.
4. Quan sát `doOnCancel` phía upstream và `onError` phía downstream.
5. Kiểm tra log server `inv-b`: có thể server vẫn xử lý đến hết 5 giây hoặc đã được thông báo client disconnect, tùy cách server xử lý.
6. Thử thêm retry giới hạn và đo số attempt thay vì chỉ đếm yêu cầu nghiệp vụ.
7. Dừng `inv-b` khi một request đang xử lý; so sánh graceful shutdown với dừng đột ngột nếu môi trường thử nghiệm cho phép.
8. Điều chỉnh timeout từ 2 giây sang giá trị hợp lý, đánh giá lỗi giả và độ trễ người dùng.

**Mẫu ghi nhận:**

| Tình huống | Client quan sát | Upstream Reactor | Server quan sát |
|---|---|---|---|
| Instance nhanh | Complete | Complete | Hoàn tất request |
| Instance chậm hơn deadline | `TimeoutException` | CANCEL | Có thể tiếp tục hoặc dừng |
| Caller chủ động `dispose()` | Không tiếp tục nhận response | CANCEL | Không bảo đảm rollback |
| Lỗi kết nối | Transport error | Error/cancel tùy operator | Có thể chưa nhận request |
| Instance deregister giữa request | Phụ thuộc connection và server | Có thể complete/error | Request đang chạy có thể tiếp tục |

Các kết quả “có thể” là chủ ý: không có phép thử thực tế được ngầm khẳng định đã chạy, và hành vi phụ thuộc transport, server, chính sách shutdown cùng thời điểm xảy ra sự kiện.

## 19. Những lỗi thiết kế thường gặp

- **Dùng `block()` trên event-loop thread.** Điều này có thể gây lỗi hoặc chặn luồng xử lý non-blocking; trong WebFlux hãy compose `Mono`/`Flux` thay vì block.
- **Tạo Mono rồi nghĩ request đã chạy.** Không subscribe thì không nhất thiết có HTTP call; subscribe lặp lại có thể tạo nhiều call.
- **Chỉ đặt connect timeout và quên deadline tổng.** Caller vẫn có thể chờ lâu ở pool, response hoặc retry.
- **Chỉ đặt `Mono.timeout` rồi tin rằng network luôn bị đóng ngay.** Cancellation là tín hiệu best-effort đối với transport; thời điểm giải phóng tùy trạng thái.
- **Coi timeout như một câu trả lời nghiệp vụ chắc chắn.** Server có thể đã hoàn tất ghi dữ liệu dù client báo timeout.
- **Retry mọi `POST` sau timeout.** Có nguy cơ tạo hiệu ứng lặp; cần idempotency và giới hạn attempt.
- **Coi `doFinally(CANCEL)` là lỗi HTTP.** Hủy stream có thể là hành vi chủ động, ví dụ sau `take(10)`.
- **Dùng `Flux.timeout(Duration)` như giới hạn tổng thời gian streaming.** Nó thường là giới hạn chờ tín hiệu, không phải tổng thời lượng stream.
- **Giả định deregistration cắt ngay request đã chọn instance.** Thay đổi danh sách discovery chủ yếu áp dụng cho lần chọn mới; request in-flight cần graceful draining.
- **Tạo client/connection pool mới theo mỗi request.** Làm tăng số connection và khó quản lý timeout, tài nguyên.
- **Che giấu lỗi bằng fallback không phân biệt UNKNOWN và FAILED.** Dễ khiến lớp nghiệp vụ đưa ra kết luận không được chứng minh.

## 20. Checklist trước khi đưa vào production

| Hạng mục | Câu hỏi kiểm chứng |
|---|---|
| Service ID | WebClient đang dùng hostname logic đúng và builder `@LoadBalanced` chứ? |
| Supplier | Discovery, cache, health check và policy đang trả tập ứng viên hợp lệ chứ? |
| Timeout | Phân biệt connect, pool, response và Reactor timeout chưa? |
| Deadline | Toàn bộ attempt và backoff có ngân sách tổng phù hợp không? |
| Retry | Đã lọc loại lỗi, giới hạn số attempt, tính idempotency chưa? |
| Cancellation | Có hiểu downstream ERROR khác upstream CANCEL không? |
| Remote side effects | Có cơ chế xác nhận trạng thái giao dịch sau timeout không? |
| Streaming | Đã xác định timeout chờ phần tử khác deadline tổng stream chưa? |
| Graceful shutdown | Có readiness/deregistration, thời gian drain, termination grace period không? |
| Observability | Có metric latency, timeout, cancel, selected instance và attempt count không? |
| Tài nguyên | Connection pool, body stream, DataBuffer có được giải phóng phù hợp không? |
| Kiểm thử | Đã thử instance nhanh/chậm, timeout, cancel, retry và deregistration chưa? |

## 21. Tổng kết

- `WebClient` tạo một pipeline reactive; HTTP request thường được kích hoạt khi có **subscription**.
- `Mono.timeout(Duration)` phát `TimeoutException` cho downstream khi upstream quá hạn và **cancel upstream**.
- `dispose()` hoặc cancellation từ subscriber nói rằng client không còn cần kết quả, nhưng **không bảo đảm server ngừng xử lý hay rollback dữ liệu**.
- Timeout của HTTP transport và deadline của pipeline có phạm vi khác nhau; nên phối hợp thay vì nhầm lẫn.
- Vị trí `timeout` so với `retryWhen` quyết định timeout tính **theo attempt** hay **toàn chuỗi retry**.
- `Flux.timeout` có semantics dựa trên việc chờ tín hiệu; phải thiết kế riêng nếu cần giới hạn **tổng thời lượng** stream.
- **Hủy đăng ký ServiceInstance khỏi registry khác hoàn toàn việc cancel Reactor Subscription**. Deregistration không tự động hủy HTTP exchange đã mở; graceful shutdown giúp bảo vệ lời gọi in-flight.
- Cần kết hợp timeout, retry hợp lý, health/discovery cập nhật, idempotency, connection draining và observability để có hệ thống giao tiếp dịch vụ ổn định.

Hiểu đúng cancellation và timeout giúp ứng dụng dùng Spring Cloud LoadBalancer biết khi nào nên ngừng chờ, khi nào có thể retry, và vì sao một lời gọi HTTP ở server vẫn có thể tiếp tục ngay cả khi phía WebClient đã không còn nhận kết quả.

