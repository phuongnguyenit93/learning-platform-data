# Giới thiệu rsocket-load-balancer và lựa chọn máy chủ theo tải

RSocket Java cung cấp `rsocket-load-balancer` để cân bằng tải ở phía client. Thay vì cố định một địa chỉ server trong suốt vòng đời ứng dụng, client duy trì một tập các kết nối RSocket tới những máy chủ đang được khám phá và chọn một kết nối cho mỗi interaction mới.

Thư viện có hai chiến lược dựng sẵn: `RoundRobinLoadbalanceStrategy` phân phối request theo vòng tròn; `WeightedLoadbalanceStrategy` cân nhắc availability và thống kê sử dụng của từng kết nối. Danh sách máy chủ đến từ một `Publisher<List<LoadbalanceTarget>>`, vì vậy ứng dụng có thể nối thư viện với Eureka, Consul, Kubernetes discovery hoặc một registry riêng và cập nhật pool khi topology thay đổi.

## 1. Cân bằng tải ở phía client là gì?

Với RSocket, một client có thể mở kết nối tới nhiều server instance. Mỗi kết nối có thể multiplex nhiều stream và interaction. Client-side load balancing chọn kết nối nào sẽ nhận một request mới.

```text
                 Service Discovery
                 orders-service
                       |
                       | danh sách instance
                       v
              LoadbalanceTarget publisher
                       |
                       v
              LoadbalanceRSocketClient
                 /       |       \
                /        |        \
               v         v         v
          RSocket A   RSocket B   RSocket C
             |           |           |
             v           v           v
          Server A    Server B    Server C
```

Các thành phần có trách nhiệm riêng:

- **Service discovery** tìm những instance đang được đăng ký và cung cấp endpoint/transport để kết nối.
- **`LoadbalanceTarget`** biểu diễn một server cùng khóa định danh duy nhất và `ClientTransport` dùng để mở RSocket.
- **`LoadbalanceRSocketClient`** duy trì pool các RSocket và chọn một kết nối cho interaction mới.
- **`LoadbalanceStrategy`** quyết định chọn RSocket nào trong tập kết nối hiện có.
- **RSocket server** tiếp tục xử lý request theo interaction model và flow control thông thường.

`rsocket-load-balancer` là client-side load balancer. Nó không phải proxy L4/L7 đứng trước cụm server và cũng không tự đăng ký hoặc khám phá service. Ứng dụng phải cung cấp danh sách target từ một nguồn discovery.

## 2. Thêm dependency

Module được phát hành với Maven coordinates `io.rsocket:rsocket-load-balancer`. Tại thời điểm biên soạn, bản phát hành mới nhất trên trang Releases của `rsocket-java` là `1.1.5`; các module RSocket nên được căn cùng một version.

Với Gradle:

```kotlin
dependencies {
    implementation("io.rsocket:rsocket-load-balancer:1.1.5")
    implementation("io.rsocket:rsocket-transport-netty:1.1.5")
}
```

Với Maven:

```xml
<dependencies>
    <dependency>
        <groupId>io.rsocket</groupId>
        <artifactId>rsocket-load-balancer</artifactId>
        <version>1.1.5</version>
    </dependency>
    <dependency>
        <groupId>io.rsocket</groupId>
        <artifactId>rsocket-transport-netty</artifactId>
        <version>1.1.5</version>
    </dependency>
</dependencies>
```

Nếu ứng dụng dùng Spring Boot RSocket, giữ dependency Spring tương thích với phiên bản RSocket được quản lý trong dependency management. Khi override RSocket version, hãy căn đồng bộ `rsocket-core`, `rsocket-load-balancer` và transport; tránh để classpath chứa các module RSocket khác phiên bản.

Các API load balancing nằm trong package `io.rsocket.loadbalance`, gồm `LoadbalanceRSocketClient`, `LoadbalanceTarget`, `LoadbalanceStrategy`, `RoundRobinLoadbalanceStrategy` và `WeightedLoadbalanceStrategy`.

## 3. LoadbalanceTarget và target publisher

`LoadbalanceTarget` chứa hai thông tin:

- `key`: định danh duy nhất của server instance trong pool.
- `transport`: `ClientTransport` dùng để kết nối tới server đó, ví dụ TCP hoặc WebSocket.

Tạo target bằng factory method:

```java
LoadbalanceTarget target = LoadbalanceTarget.from(
        "orders-node-a",
        TcpClientTransport.create("10.20.0.11", 7000)
);
```

`key` nên ổn định trong suốt vòng đời của một instance. Có thể dùng instance ID do service registry cấp. Không dùng một key chung cho mọi node; nếu hai endpoint có cùng key, pool không thể phân biệt chúng như hai target độc lập. Khi một instance bị thay bằng incarnation mới có endpoint khác, hãy dùng identity mới do registry cấp để pool nhận biết target mới.

`LoadbalanceRSocketClient` nhận một `Publisher<List<LoadbalanceTarget>>`. Mỗi lần publisher phát ra một list, list đó mô tả snapshot các target mà client nên cân bằng tải. Publisher có thể phát snapshot mới định kỳ khi server được thêm, xóa hoặc thay endpoint.

Ví dụ một cụm tĩnh:

```java
Flux<List<LoadbalanceTarget>> targets = Flux.just(List.of(
        LoadbalanceTarget.from(
                "orders-a",
                TcpClientTransport.create("10.20.0.11", 7000)),
        LoadbalanceTarget.from(
                "orders-b",
                TcpClientTransport.create("10.20.0.12", 7000)),
        LoadbalanceTarget.from(
                "orders-c",
                TcpClientTransport.create("10.20.0.13", 7000))
));
```

Snapshot trên phù hợp với danh sách endpoint cố định. Với môi trường có autoscaling hoặc instance thay đổi IP/port, cần publisher tiếp tục phát các snapshot mới.

## 4. LoadbalanceRSocketClient

`LoadbalanceRSocketClient` triển khai `RSocketClient`. Nó được xây dựng từ target publisher và một `RSocketConnector` mẫu. Connector mẫu được dùng để kết nối tới transport của từng target, vì vậy các cấu hình chung như keepalive, MIME type, authentication metadata hoặc interceptor được áp dụng cho các kết nối trong pool.

Tạo client với round-robin:

```java
LoadbalanceRSocketClient client = LoadbalanceRSocketClient
        .builder(targets)
        .connector(RSocketConnector.create()
                .keepAlive(Duration.ofSeconds(30), Duration.ofMinutes(2)))
        .roundRobinLoadbalanceStrategy()
        .build();
```

`roundRobinLoadbalanceStrategy()` là chiến lược mặc định, vì vậy có thể viết ngắn hơn:

```java
LoadbalanceRSocketClient client = LoadbalanceRSocketClient.create(
        RSocketConnector.create(),
        targets
);
```

Nếu muốn dùng weighted strategy:

```java
LoadbalanceRSocketClient client = LoadbalanceRSocketClient
        .builder(targets)
        .connector(RSocketConnector.create())
        .weightedLoadbalanceStrategy()
        .build();
```

Builder cũng nhận một `LoadbalanceStrategy` tùy chỉnh qua `.loadbalanceStrategy(strategy)`. Client hỗ trợ các interaction như request-response, fire-and-forget, request-stream, request-channel và metadata push.

Khi ứng dụng kết thúc, dispose client để đóng các thành phần và kết nối do pool quản lý:

```java
client.dispose();
```

Trong ứng dụng Spring, hãy quản lý vòng đời client/requester theo lifecycle của bean, thay vì tạo một load balancer mới cho từng request.

## 5. RoundRobinLoadbalanceStrategy

Round-robin chọn lần lượt các RSocket trong danh sách hiện có. Ví dụ với ba server:

```text
Request 1  -> Server A
Request 2  -> Server B
Request 3  -> Server C
Request 4  -> Server A
Request 5  -> Server B
Request 6  -> Server C
```

Ưu điểm:

- Dễ hiểu, ít cấu hình.
- Phân phối tương đối đều số interaction mới khi các server có năng lực tương đương.
- Phù hợp khi tải request tương đối đồng nhất và chưa có số liệu để phân biệt năng lực từng server.

Giới hạn:

- Mỗi request được tính như nhau dù thời gian xử lý khác nhau.
- Không cân bằng theo CPU, memory hoặc độ trễ của server.
- Nếu một server xử lý request lâu hơn nhiều, số request được phân phối đều không có nghĩa tải thực tế được phân phối đều.

Round-robin phù hợp làm baseline để so sánh trong test tải. Nếu server có năng lực khác nhau hoặc thời gian xử lý biến động lớn, hãy đánh giá weighted strategy và số liệu thực tế.

## 6. WeightedLoadbalanceStrategy

`WeightedLoadbalanceStrategy` gán trọng số cho mỗi RSocket dựa trên availability và thống kê sử dụng. Trọng số được dùng để chọn kết nối có khả năng phục vụ request tốt hơn.

Các số liệu được API `WeightedStats` cung cấp gồm:

| Số liệu | Ý nghĩa |
| --- | --- |
| `weightedAvailability()` | Availability đã được tính trọng số của RSocket |
| `pending()` | Số request đang chờ/xử lý được theo dõi |
| `predictedLatency()` | Độ trễ dự đoán dựa trên thống kê request |
| `lowerQuantileLatency()` | Mốc độ trễ ở quantile thấp |
| `higherQuantileLatency()` | Mốc độ trễ ở quantile cao |

Availability của `RSocket` là một tín hiệu dương biểu thị mức sẵn sàng; số càng cao càng tốt và `0.0` có nghĩa là không khả dụng. Đây không phải phần trăm CPU. Không nên diễn giải availability trực tiếp thành CPU utilization hoặc memory usage.

Khi `WeightedLoadbalanceStrategy` được dùng thông qua `LoadbalanceRSocketClient`, strategy tự cấu hình `WeightedStatsRequestInterceptor` vào connector để theo dõi vòng đời request và cập nhật thống kê. Ứng dụng không cần tự tạo `weightedStatsResolver` trong trường hợp này.

Tạo strategy bằng factory:

```java
WeightedLoadbalanceStrategy strategy = WeightedLoadbalanceStrategy.create();
```

Hoặc tùy chỉnh số lần thử chọn cặp RSocket có availability khác 0:

```java
WeightedLoadbalanceStrategy strategy = WeightedLoadbalanceStrategy.builder()
        .maxPairSelectionAttempts(8)
        .build();
```

Mặc định `maxPairSelectionAttempts` là 5. Khi pool có hơn hai kết nối, strategy thử chọn ngẫu nhiên một cặp kết nối có availability khác 0; nếu vượt số lần thử, cặp được chọn cuối cùng sẽ được sử dụng. Weighted strategy là lựa chọn dựa trên thống kê request và availability, không phải bộ điều khiển trực tiếp CPU/memory của toàn cluster.

### 6.1. Khi nào nên chọn weighted?

Weighted strategy đáng thử khi:

- Các server có cấu hình hoặc năng lực xử lý khác nhau.
- Thời gian xử lý request thay đổi đáng kể.
- Có server thỉnh thoảng chậm do GC, downstream hoặc tải nền.
- Client tạo đủ traffic để các số liệu latency và pending có ý nghĩa.

Không nên kỳ vọng weighted strategy tạo ra phân phối giống hệt nhau giữa các server. Một server nhanh hơn có thể nhận nhiều request hơn; điều này có thể là kết quả mong muốn nếu mục tiêu là giảm latency và tận dụng năng lực.

## 7. Availability không đồng nghĩa với tải CPU

`RSocket.availability()` cung cấp tín hiệu sẵn sàng cho việc lựa chọn kết nối. Weighted strategy còn theo dõi request lifecycle và latency ở phía client. Hai loại tín hiệu này hữu ích hơn round-robin thuần túy, nhưng không tự động thay thế monitoring của server.

Nếu nghiệp vụ cần chọn theo CPU, memory, queue depth hoặc giới hạn tenant, cần thiết kế thêm feedback từ server hoặc một strategy tùy chỉnh. Ví dụ, server có thể công bố availability dựa trên trạng thái nhận tải của ứng dụng, hoặc registry có thể cung cấp metadata/weight được cập nhật theo chu kỳ.

Không đưa số liệu CPU cũ hoặc health check quá chậm vào quyết định mà không xét độ trễ cập nhật. Một server vừa quá tải có thể tiếp tục nhận request trong thời gian registry chưa phát snapshot mới. Cần đặt ngưỡng, hysteresis và thời gian làm mới phù hợp để tránh thay đổi target liên tục.

## 8. Kết nối với Spring RSocketRequester

Spring Framework từ phiên bản 5.3 hỗ trợ load balancing trực tiếp qua `RSocketRequester.Builder.transports(...)`. Phương thức này nhận:

- `Publisher<List<LoadbalanceTarget>>`: publisher cung cấp snapshot target, có thể được cập nhật định kỳ.
- `LoadbalanceStrategy`: chiến lược chọn target.

Ví dụ dùng danh sách target tĩnh:

```java
RSocketRequester requester = RSocketRequester.builder()
        .transports(targets, new RoundRobinLoadbalanceStrategy());
```

Khi đó code nghiệp vụ dùng requester như bình thường:

```java
Mono<OrderView> order = requester
        .route("orders.find")
        .data(new FindOrder("ORD-2026-018"))
        .retrieveMono(OrderView.class);
```

Có thể thay round-robin bằng weighted strategy mà không đổi cách gọi route:

```java
RSocketRequester requester = RSocketRequester.builder()
        .transports(targets, WeightedLoadbalanceStrategy.create());
```

Với Spring RSocketRequester, framework quản lý serialization data/metadata và cung cấp API cấp cao cho request. Cấu hình `RSocketStrategies`, authentication metadata, keepalive và interceptor vẫn cần tương thích với server.

## 9. Cập nhật target list từ Spring Cloud Discovery

`rsocket-load-balancer` không gọi Eureka, Consul hoặc Kubernetes API thay ứng dụng. Một cách tích hợp phổ biến là dùng `ReactiveDiscoveryClient` từ Spring Cloud Commons để lấy các `ServiceInstance`, chuyển chúng thành `LoadbalanceTarget` rồi phát snapshot định kỳ. Ứng dụng cần có discovery starter/implementation tương ứng với registry đang dùng.

Ví dụ dưới đây giả định registry trả đúng cổng RSocket TCP trong `ServiceInstance.getPort()`. Nếu ứng dụng đăng ký HTTP port và RSocket port riêng, hãy lưu RSocket port trong metadata của registry và đọc trường đó thay cho `getPort()`.

```java
@Configuration
public class OrdersRSocketClientConfiguration {

    private static final Logger log = LoggerFactory.getLogger(
            OrdersRSocketClientConfiguration.class);

    @Bean
    RSocketRequester ordersRequester(
            RSocketRequester.Builder builder,
            ReactiveDiscoveryClient discoveryClient) {

        AtomicReference<List<LoadbalanceTarget>> lastKnownTargets =
                new AtomicReference<>(List.of());

        Flux<List<LoadbalanceTarget>> targetUpdates = Flux.defer(() ->
                discoveryClient.getInstances("orders-service")
                        .map(instance -> LoadbalanceTarget.from(
                                instance.getInstanceId() != null
                                        ? instance.getInstanceId()
                                        : instance.getHost() + ":" + instance.getPort(),
                                TcpClientTransport.create(
                                        instance.getHost(), instance.getPort())))
                        .collectList()
                        .timeout(Duration.ofSeconds(3))
                        .doOnNext(lastKnownTargets::set)
                        .onErrorResume(error -> {
                            log.warn("Không thể làm mới danh sách RSocket targets", error);
                            return Mono.just(lastKnownTargets.get());
                        })
                        .flux()
        ).repeatWhen(repeats -> repeats.delayElements(Duration.ofSeconds(5)));

        return builder
                .rsocketConnector(connector -> connector.keepAlive(
                        Duration.ofSeconds(30), Duration.ofMinutes(2)))
                .transports(targetUpdates, WeightedLoadbalanceStrategy.create());
    }
}
```

Luồng cập nhật hoạt động như sau:

1. `Flux.defer` gọi service discovery mỗi lần publisher được subscribe lại.
2. Mỗi `ServiceInstance` được chuyển thành `LoadbalanceTarget` với key là instance ID và transport TCP.
3. `collectList()` tạo một snapshot hoàn chỉnh để pool nhận cùng lúc.
4. `lastKnownTargets` lưu snapshot thành công gần nhất.
5. Nếu discovery lỗi hoặc timeout, publisher phát lại snapshot gần nhất thay vì kết thúc luồng cập nhật.
6. `repeatWhen` chờ 5 giây rồi truy vấn lại discovery.

Khi discovery trả về một snapshot rỗng thành công, ví dụ không còn instance nào được đăng ký, snapshot rỗng được phát và pool không còn target để chọn. Khi discovery lỗi tạm thời, ví dụ registry không truy cập được, snapshot thành công gần nhất được giữ lại. Cần cân nhắc thời hạn tối đa cho dữ liệu cũ; không nên giữ endpoint cũ vô thời hạn nếu thông tin discovery đã lỗi kéo dài.

Trong hệ thống WebSocket, thay `TcpClientTransport` bằng `WebsocketClientTransport` với URI WebSocket đầy đủ, gồm scheme, host, port và mapping path mà server mở. Dùng `wss://` khi kết nối qua TLS.

## 10. Vì sao target publisher phải tiếp tục phát?

Pool có thể loại một kết nối không còn khỏe khỏi tập kết nối đang hoạt động. Nếu target publisher chỉ phát một lần bằng `Flux.just(initialTargets)` rồi hoàn tất, nó không thể thông báo một instance mới hoặc một instance cũ đã phục hồi.

Ví dụ tình huống:

```text
T0: Discovery phát [A, B, C]
T1: Client kết nối tới A, B, C
T2: B ngừng hoạt động; pool loại kết nối B bị lỗi
T3: Discovery phát [A, C, D]
T4: Pool nhận snapshot mới và có thể kết nối tới D
T5: B được khởi động lại và đăng ký lại
T6: Discovery phát [A, B, C, D]
T7: Pool nhận snapshot mới để xem xét B như một target
```

Publisher phải còn sống để phát các snapshot sau này. Nếu publisher hoàn tất sau lần phát đầu, pool không nhận được thông tin về target xuất hiện lại. Đây cũng là nguyên nhân có thể dẫn đến lỗi `Pool is exhausted` khi tất cả kết nối trong pool đã bị loại mà không có snapshot mới.

Giữ key ổn định cho một instance giúp pool nhận diện target giữa các snapshot. Khi instance thay IP hoặc port, hãy cập nhật transport trong snapshot và đảm bảo key phản ánh đúng identity mà registry sử dụng.

## 11. Cân bằng tải không phải retry hoặc resumption

Ba cơ chế này giải quyết các vấn đề khác nhau:

| Cơ chế | Mục tiêu | Điều không tự đảm bảo |
| --- | --- | --- |
| Load balancing | Chọn một RSocket trong pool cho interaction mới | Không tự phát lại một request đã thất bại |
| Reconnect | Tạo lại kết nối khi transport bị mất theo chính sách connector | Không tự chọn một instance khác nếu transport vẫn trỏ tới endpoint cũ |
| Session resumption | Tiếp tục session/stream khi client và server cùng hỗ trợ resume | Không phải cơ chế phân phối request mới giữa nhiều server độc lập |

Nếu một server chết khi request-response đang chạy, request có thể kết thúc bằng lỗi. Caller cần quyết định có retry hay không. Với thao tác có side effect, chỉ retry khi có idempotency key hoặc cơ chế chống thực hiện trùng.

Một request-stream hoặc request-channel đã được mở sẽ gắn với RSocket được chọn cho interaction đó. Các payload tiếp theo trong cùng stream không được load balancer phân phối lại sang server khác. Khi kết nối chết, stream cần được xử lý theo lỗi/cancel và ứng dụng có thể mở interaction mới sau khi có target khả dụng.

## 12. Pool kết nối và quy mô client

`LoadbalanceRSocketClient` quản lý một pool các RSocket thay vì mở kết nối mới cho mỗi request. Điều này tận dụng multiplexing của RSocket và giảm chi phí thiết lập transport cho các request liên tiếp.

Tuy nhiên, số kết nối cần tính theo số client process và số target. Một ứng dụng client có nhiều target có thể giữ nhiều kết nối RSocket đồng thời. Nếu hàng chục nghìn thiết bị đều tự tạo pool tới mọi backend instance, tổng connection count ở server có thể tăng nhanh.

Trước khi triển khai diện rộng, hãy ước tính:

```text
Tổng kết nối xấp xỉ
  = số client process đang hoạt động
  × số target RSocket được kết nối trong mỗi pool
```

Đây là ước lượng capacity, không phải cam kết số kết nối nội bộ chính xác của mọi cấu hình. Hãy đo connection count thực tế với phiên bản thư viện, transport và cách khởi tạo client đang dùng.

Công thức trên giả định mỗi target tạo một kết nối trong mỗi pool. Số thực tế còn phụ thuộc cách triển khai pool, thời điểm target được kết nối, trạng thái health và cách client dispose.

Với nhiều client rất lớn, cân nhắc một gateway/proxy hoặc lớp trung gian chịu trách nhiệm giữ các kết nối backend, để thiết bị chỉ cần kết nối tới một hoặc một số ít endpoint. Việc chọn mô hình phụ thuộc vào yêu cầu latency, isolation, topology, security và khả năng vận hành.

## 13. Khi nào dùng RoundRobin, Weighted hoặc custom strategy?

| Chiến lược | Tín hiệu chính | Nên dùng khi |
| --- | --- | --- |
| Round robin | Thứ tự trong danh sách pool | Server tương đương và tải request gần đồng nhất |
| Weighted | Availability và usage statistics của RSocket | Năng lực/latency không đồng đều, muốn chọn theo khả năng phục vụ |
| Custom `LoadbalanceStrategy` | Quy tắc do ứng dụng định nghĩa | Cần affinity, region, tenant, zone hoặc tín hiệu load riêng |

Một custom strategy có thể sử dụng `RSocket.availability()` để loại những kết nối có availability bằng 0. Ví dụ đơn giản nhất chọn kết nối có availability cao nhất:

```java
public final class HighestAvailabilityStrategy implements LoadbalanceStrategy {

    @Override
    public RSocket select(List<RSocket> sockets) {
        return sockets.stream()
                .filter(socket -> socket.availability() > 0.0)
                .max(Comparator.comparingDouble(RSocket::availability))
                .orElseThrow(() -> new IllegalStateException(
                        "Không có RSocket khả dụng trong pool"));
    }
}
```

Đây chỉ là ví dụ minh họa một tín hiệu đơn. Nó không theo dõi latency hoặc pending requests như weighted strategy. Với custom policy phức tạp, hãy tránh gọi discovery, database hoặc HTTP service đồng bộ bên trong `select()`, vì đây là đường chọn request và cần nhanh, không blocking.

## 14. Quan sát và vận hành

Để biết load balancer có thực sự phân phối tải tốt, hãy quan sát cả pool và server:

- Số target trong snapshot discovery và thời điểm snapshot gần nhất.
- Số kết nối RSocket đang hoạt động, đang kết nối và đã bị loại.
- Số request được gửi tới từng server.
- Pending request, latency trung vị/quantile và error rate theo server.
- Số lần `Pool is exhausted`, connect failure và reconnect.
- Thời gian từ lúc instance đăng ký lại đến khi nó nhận request đầu tiên.
- Tỷ lệ retry và số request bị retry sau lỗi transport.
- Số stream dài hạn bị ngắt khi server hoặc mạng gặp sự cố.

Không chỉ nhìn tổng request count. Một server có thể nhận ít request hơn nhưng xử lý mỗi request lâu hơn, khiến pending work và latency cao hơn. Cũng không nên dùng CPU là tín hiệu duy nhất; GC, downstream latency, connection limit và queue depth có thể là nguyên nhân chính.

## 15. Kiểm thử lựa chọn và phục hồi target

Kiểm thử nên chạy với target publisher có thể thay đổi, không chỉ dùng một `Flux.just` cố định.

| Kịch bản | Điều cần xác minh |
| --- | --- |
| Hai hoặc ba target khỏe | Round-robin phân phối các interaction mới qua các target |
| Weighted strategy | Kết nối có availability/usage tốt được ưu tiên theo số liệu theo dõi |
| Một target ngừng hoạt động | Kết nối lỗi bị loại khỏi tập đang hoạt động và request mới dùng target còn khỏe |
| Discovery thêm instance | Snapshot mới đưa target mới vào pool |
| Discovery xóa instance | Target không còn được quảng bá bị loại theo cập nhật pool |
| Instance phục hồi | Snapshot mới được phát; kiểm tra instance có được kết nối và tham gia chọn lại |
| Discovery tạm thời lỗi | Publisher không hoàn tất; hành vi giữ snapshot cũ đúng chính sách |
| Không còn target | Request thất bại có kiểm soát, metric `Pool is exhausted` tăng |
| Request đang chạy khi node chết | Stream/request nhận lỗi; không giả định tự chuyển sang node khác |
| Request có side effect | Retry không tạo tác vụ trùng khi có idempotency key |
| Tải không đồng đều | So sánh latency, pending và throughput giữa RoundRobin và Weighted |

Đặc biệt, cần có bài test fail-recover: dừng một server, xác nhận nó bị loại; khởi động lại, xác nhận registry phát snapshot mới và server được kết nối lại. Có một issue công khai trong `rsocket-java` báo cáo trường hợp node phục hồi không tham gia lại load-balancing pool (issue #1123, báo cáo trên 1.1.3). Issue này là tín hiệu cần regression-test với đúng phiên bản đang dùng; không nên mặc định mọi bản phát hành đều có cùng hành vi.

## 16. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| `Pool is exhausted` | Không còn RSocket khả dụng hoặc target publisher không phát snapshot mới | Kiểm tra discovery, publisher lifecycle và trạng thái kết nối |
| Server mới không nhận request | Publisher chỉ phát danh sách ban đầu hoặc registry chưa cập nhật | Dùng publisher refresh định kỳ và xác minh instance đăng ký đúng |
| Server phục hồi nhưng vẫn không được chọn | Target không được đưa lại vào snapshot hoặc hành vi pool theo version | Kiểm thử fail-recover với đúng artifact; xem issue #1123 |
| Request vẫn lỗi sau khi server khác khỏe | Request hiện tại đã bắt đầu trên kết nối lỗi và chưa được retry | Áp dụng retry có giới hạn cho thao tác an toàn/idempotent |
| Phân phối không đều theo CPU | Round-robin chỉ đếm request; weighted stats không phải CPU telemetry | Chọn weighted hoặc custom strategy với feedback phù hợp |
| Kết nối tăng đột biến | Mỗi client process giữ pool tới nhiều target | Ước tính connection count, giới hạn target hoặc dùng gateway |
| Discovery lỗi làm pool mất hết node | Publisher phát list rỗng hoặc kết thúc khi registry tạm lỗi | Giữ snapshot gần nhất khi lỗi và đặt timeout/expiry rõ ràng |
| Requester không chọn đúng route | Client/server không thống nhất MIME type hoặc route metadata | Kiểm tra `RSocketStrategies` và routing metadata |

## 17. Checklist triển khai

- [ ] Thêm `rsocket-load-balancer` và transport module cùng version.
- [ ] Chọn `RoundRobinLoadbalanceStrategy` hay `WeightedLoadbalanceStrategy` theo workload.
- [ ] Tạo `LoadbalanceTarget` với key duy nhất và ổn định cho mỗi server instance.
- [ ] Cung cấp target publisher phát `List<LoadbalanceTarget>` và cập nhật khi topology đổi.
- [ ] Không để publisher hoàn tất sau snapshot ban đầu nếu service có thể scale hoặc phục hồi.
- [ ] Đặt timeout cho discovery và xác định chính sách khi discovery lỗi hoặc trả danh sách rỗng.
- [ ] Đảm bảo target transport trỏ tới đúng RSocket port hoặc WebSocket path.
- [ ] Cấu hình connector chung: keepalive, authentication, MIME type và interceptor.
- [ ] Với weighted strategy, theo dõi latency/pending/availability; không xem availability là CPU percent.
- [ ] Quản lý dispose/lifecycle của load-balanced client hoặc requester.
- [ ] Kiểm thử node down, node recovery, discovery refresh và pool exhausted.
- [ ] Chỉ retry thao tác an toàn hoặc có idempotency key.
- [ ] Đo connection count khi số client và số target tăng.

`rsocket-load-balancer` giúp client Java chọn một RSocket từ pool dựa trên chiến lược đã cấu hình. Round-robin là điểm bắt đầu đơn giản; weighted strategy sử dụng availability và thống kê request để lựa chọn thích ứng hơn. Để hệ thống chịu được autoscaling và lỗi node, target publisher phải tiếp tục nhận snapshot từ service discovery, còn ứng dụng cần kiểm thử cả quá trình node rời cụm và quay lại. Load balancing chọn nơi gửi interaction mới; retry, resume và phục hồi stream vẫn cần chính sách riêng.

## Tài liệu tham khảo

- [RSocket Java — `LoadbalanceRSocketClient` API](https://javadoc.io/static/io.rsocket/rsocket-core/1.1.5/io/rsocket/loadbalance/LoadbalanceRSocketClient.html)
- [RSocket Java — `LoadbalanceTarget` API](https://javadoc.io/static/io.rsocket/rsocket-core/1.1.5/io/rsocket/loadbalance/LoadbalanceTarget.html)
- [RSocket Java — `LoadbalanceRSocketClient.Builder` API](https://javadoc.io/static/io.rsocket/rsocket-core/1.1.5/io/rsocket/loadbalance/LoadbalanceRSocketClient.Builder.html)
- [RSocket Java — `WeightedLoadbalanceStrategy` API](https://javadoc.io/static/io.rsocket/rsocket-core/1.1.5/io/rsocket/loadbalance/WeightedLoadbalanceStrategy.html)
- [RSocket Java — `WeightedStats` API](https://javadoc.io/static/io.rsocket/rsocket-core/1.1.5/io/rsocket/loadbalance/WeightedStats.html)
- [Spring Framework — `RSocketRequester.Builder.transports`](https://docs.spring.io/spring-framework/docs/6.0.18/javadoc-api/org/springframework/messaging/rsocket/RSocketRequester.Builder.html)
- [Spring Framework — RSocket reference](https://docs.spring.io/spring-framework/reference/rsocket.html)
- [RSocket Java — Releases](https://github.com/rsocket/rsocket-java/releases)
- [RSocket Java — Issue #1123: node recovery and load balancing](https://github.com/rsocket/rsocket-java/issues/1123)
- [RSocket Java — Spring RSocketRequester load balancing discussion](https://stackoverflow.com/questions/65254112/correct-usage-of-loadbalancersocketclient-with-springs-rsocketrequester)
