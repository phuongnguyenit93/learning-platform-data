# Cân bằng kết nối ở tầng mạng và cân bằng yêu cầu ở phía gọi

RSocket có thể giữ một kết nối TCP hoặc WebSocket trong thời gian dài và multiplex nhiều interaction trên cùng kết nối. Đặc điểm này ảnh hưởng trực tiếp đến cách cân bằng tải. Load balancer ở tầng mạng thường chọn backend khi một kết nối mới được thiết lập; sau đó toàn bộ các request-response, request-stream hoặc request-channel trên kết nối đó tiếp tục đi tới cùng backend. Trong khi đó, cân bằng yêu cầu ở phía gọi cho phép client chọn một instance cho từng interaction mới, miễn là client có các kết nối tới nhiều instance.

Hai cách tiếp cận giải quyết hai cấp khác nhau. Cân bằng kết nối phân phối socket và bảo vệ hạ tầng mạng; cân bằng yêu cầu phân phối công việc nghiệp vụ giữa các instance. Một hệ thống RSocket có thể dùng cả hai, nhưng cần hiểu nơi quyết định backend, thời điểm quyết định và phạm vi của một interaction.

Bài học này phân tích load balancing ở tầng L4/L7, cách RSocket multiplex các interaction, lựa chọn instance ở phía gọi, connection pool, service discovery, health check, affinity, retry và graceful draining.

Sau bài học, bạn có thể:

- Phân biệt cân bằng kết nối với cân bằng từng request/interaction.
- Giải thích vì sao một RSocket connection dài hạn có thể làm tải lệch dù số connection được chia đều.
- Hiểu giới hạn của L4 load balancer và HTTP/WebSocket L7 proxy.
- Thiết kế client-side load balancing dựa trên service discovery và connection pool.
- Chọn round-robin, weighted, least-loaded hoặc consistent-hash theo workload.
- Xử lý health, timeout, reconnect, retry và session affinity.
- Chọn đúng ranh giới cân bằng cho request-response, request-stream và request-channel.
- Thiết kế graceful shutdown/draining khi scale hoặc triển khai phiên bản mới.
- Kiểm thử phân phối tải và quan sát hiệu quả theo instance.

## 1. Hai cấp độ cân bằng tải

Giả sử Inventory Service có ba instance chạy độc lập. Order Service cần gọi route inventory.check qua RSocket.

Có hai nơi có thể chọn instance:

1. Network load balancer nhận kết nối mới và chọn một backend.
2. Client-side load balancer chọn instance trước khi gửi một interaction.

~~~mermaid
flowchart TD
    C[Order Service / RSocket client] --> N[Network Load Balancer]
    N --> I1[Inventory instance A]
    N --> I2[Inventory instance B]
    N --> I3[Inventory instance C]
    C -. Client-side discovery and selection .-> P[Connection pool per instance]
    P --> I1
    P --> I2
    P --> I3
~~~

| Tiêu chí | Network-side balancing | Client-side request balancing |
|---|---|---|
| Nơi chọn backend | Load balancer/proxy | Client gọi dịch vụ |
| Đơn vị phân phối | Thường là TCP/WebSocket connection | Interaction mới hoặc request mới |
| Client có biết instance? | Không cần | Có danh sách instance hoặc resolver |
| Yêu cầu hạ tầng | LB, proxy, health check | Discovery, connection pool, selection policy |
| Thích hợp | Che giấu topology, kiểm soát ingress | Phân phối công việc chi tiết, giảm hop |
| Hạn chế chính | Một connection dài có thể giữ tải lâu ở một backend | Client phải quản lý discovery, connection và health |

Network balancing và client balancing không loại trừ nhau. Ví dụ browser kết nối qua WebSocket gateway được cân bằng ở tầng mạng; backend Java service lại dùng client-side balancing để chọn một trong nhiều RSocket server nội bộ.

## 2. RSocket connection là đơn vị multiplex

Một RSocket connection có thể mang nhiều interaction đồng thời. Sau khi SETUP thành công, requester và responder trao đổi frame trên cùng transport connection. Các interaction được phân biệt bằng stream ID và có thể chạy song song.

~~~mermaid
flowchart LR
    C[RSocket client] -->|One TCP connection| S[RSocket server instance A]
    subgraph M[Multiplexed interactions]
        R1[REQUEST_RESPONSE]
        R2[REQUEST_STREAM]
        R3[REQUEST_CHANNEL]
        R4[FIRE_AND_FORGET]
    end
    S --- R1
    S --- R2
    S --- R3
    S --- R4
~~~

Nếu client mở một connection tới instance A và gửi 10.000 request qua connection đó, tất cả interaction vẫn được xử lý bởi instance A. Một L4 load balancer không nhìn thấy mỗi request-response như một TCP connection mới để chia lại cho instance B hoặc C.

Điều này khác với mô hình HTTP stateless trong đó client có thể tạo nhiều request độc lập và một proxy có thể chọn backend cho từng HTTP request. Với WebSocket, sau HTTP upgrade, kết nối trở thành một đường truyền hai chiều tồn tại lâu dài. RSocket frame tiếp tục đi trên đường truyền đó.

Vì vậy, cần phân biệt:

- **Connection distribution**: phân phối số socket hoặc phiên transport.
- **Interaction distribution**: chọn instance cho từng request hoặc stream mới.
- **Workload distribution**: phân phối theo chi phí xử lý, số request đang chạy, độ trễ hoặc tài nguyên thực tế.

Một hệ thống có số connection bằng nhau chưa chắc có lượng công việc bằng nhau. Một connection có thể chỉ mang vài heartbeat; connection khác có thể mang hàng nghìn stream và request.

## 3. Cân bằng tải ở tầng L4

L4 load balancer hoạt động ở tầng transport, thường dựa trên thông tin IP và TCP/UDP như địa chỉ nguồn, địa chỉ đích và port. Với RSocket TCP, load balancer chọn backend khi client mở TCP connection.

Một số thuật toán phổ biến:

- Round robin: lần lượt phân phối connection mới cho các backend.
- Least connections: ưu tiên backend đang có ít connection hơn.
- Source hashing: giữ một source IP hoặc tuple ở cùng backend.
- Weighted distribution: backend có trọng số cao nhận nhiều connection mới hơn.

~~~mermaid
flowchart TD
    A[New TCP connection] --> B[L4 load balancer]
    B --> C{Select backend}
    C -->|Connection 1| D[Instance A]
    C -->|Connection 2| E[Instance B]
    C -->|Connection 3| F[Instance C]
    D --> G[Many RSocket interactions]
    E --> H[Many RSocket interactions]
    F --> I[Many RSocket interactions]
~~~

Sau khi TCP connection được gán cho một backend, các frame RSocket trên connection đó tiếp tục tới backend đó. L4 load balancer không thể chuyển một nửa interaction trên connection sang instance khác mà vẫn giữ nguyên RSocket session.

### Khi nào L4 phù hợp?

L4 phù hợp khi:

- Muốn có một địa chỉ kết nối ổn định cho nhiều RSocket client.
- Muốn che giấu danh sách instance phía sau.
- Muốn kiểm soát kết nối TCP, giới hạn connection và health backend.
- Client không cần biết topology nội bộ.
- Có đủ số lượng connection và workload phân bố tương đối đồng đều.

### Điểm yếu với kết nối dài hạn

Nếu chỉ có một vài client mở connection lâu dài, round robin theo connection có thể tạo phân phối lệch. Ví dụ 9 connection được chia đều cho 3 backend, nhưng một connection tạo ra 90% request. Số connection nhìn cân bằng nhưng CPU và request rate lại lệch mạnh.

Least connections cũng không giải quyết hoàn toàn vấn đề này vì một connection nhàn rỗi và một connection đang mang nhiều stream đều được tính là một connection. Một số LB hỗ trợ metric hoặc thuật toán nâng cao, nhưng L4 vẫn không có ngữ nghĩa nghiệp vụ của từng RSocket interaction.

## 4. Cân bằng tải ở tầng L7 với WebSocket

Browser thường kết nối RSocket qua WebSocket hoặc WSS. L7 proxy có thể nhìn thấy HTTP request bắt tay WebSocket trước khi upgrade, ví dụ host, path và một số header được phép. Nó có thể chọn backend dựa trên các thông tin đó.

Sau khi upgrade thành công, proxy chuyển tiếp dữ liệu WebSocket hai chiều. RSocket route như inventory.check nằm trong RSocket metadata của frame nhị phân, không nằm trong HTTP path của từng interaction.

~~~mermaid
sequenceDiagram
    participant B as Browser
    participant P as L7 Proxy
    participant S as RSocket Server A
    B->>P: HTTP WebSocket handshake /rsocket
    P->>S: Forward handshake to selected backend
    S-->>P: 101 Switching Protocols
    P-->>B: WebSocket established
    B->>P: RSocket SETUP frame
    P->>S: Forward frame
    B->>P: REQUEST_RESPONSE route=inventory.check
    P->>S: Forward frame on same WebSocket
~~~

Một HTTP L7 proxy thông thường không tự chọn backend mới cho từng RSocket route bên trong WebSocket. Nó thường giữ kết nối đã upgrade tới backend đã chọn. Chỉ một proxy hiểu RSocket protocol mới có thể đưa ra quyết định dựa trên metadata/route của từng interaction; đây là năng lực riêng, không nên giả định ở mọi ingress controller hoặc reverse proxy.

### L7 có thể cân bằng theo điều gì?

Trước WebSocket upgrade, proxy có thể chọn backend theo:

- Host hoặc domain.
- Path endpoint như /rsocket.
- Cookie hoặc thông tin handshake được phép.
- TLS SNI khi proxy kết thúc TLS.
- Trọng số backend và health status.

Không nên đặt token hoặc dữ liệu nhạy cảm trong URL query để làm khóa routing. URL có thể xuất hiện trong access log, browser history hoặc hệ thống quan sát.

### Sticky session

Nếu trạng thái session RSocket chỉ nằm trong memory của một backend, client có thể cần quay lại đúng backend khi reconnect hoặc resume. Sticky session có thể dùng cookie, source affinity hoặc routing key.

Sticky session có giới hạn:

- Backend đã chọn có thể quá tải trong khi backend khác còn rảnh.
- Backend restart hoặc bị loại bỏ thì affinity không còn hữu ích.
- Source IP hashing có thể gom nhiều client sau cùng NAT vào một backend.
- Sticky session không thay thế việc lưu trạng thái bền vững hoặc chia sẻ state khi cần HA.

Chỉ bật affinity khi session/resume hoặc stateful workflow thực sự cần nó. Với service stateless, phân phối linh hoạt thường dễ scale hơn.

## 5. Vì sao RSocket thường cần client-side request balancing?

Một client có thể duy trì một pool gồm các RSocket connection tới nhiều instance. Khi có interaction mới, client chọn một instance theo chính sách rồi gửi request qua connection tương ứng.

~~~mermaid
flowchart TD
    A[Business call] --> B[Client-side load balancer]
    B --> C[Instance list + health]
    C --> D[Selection policy]
    D --> E[Connection pool]
    E --> F[RSocket connection to A]
    E --> G[RSocket connection to B]
    E --> H[RSocket connection to C]
~~~

Ví dụ:

- Request 1 chọn instance A.
- Request 2 chọn instance B.
- Request 3 chọn instance C.
- Request 4 chọn instance A.

Mỗi request vẫn dùng một RSocket connection đã thiết lập tới instance được chọn. Client không cần tạo TCP handshake mới cho từng request; nó tái sử dụng connection pool.

### Cân bằng ở ranh giới interaction

Request-response có thể chọn instance tại lúc bắt đầu request. Request-stream cũng chọn một instance khi stream được mở; toàn bộ response item của stream đó đến từ responder đã chọn. Request-channel cũng gắn với một responder trong suốt interaction hai chiều.

Không chia từng frame của một stream cho nhiều backend. Việc đó phá vỡ ngữ nghĩa interaction, thứ tự và state cục bộ của responder.

## 6. Service discovery và danh sách instance

Client-side balancing cần biết những instance nào có thể nhận request. Nguồn danh sách có thể là:

- Service registry như Consul, Eureka hoặc Kubernetes service discovery.
- DNS có nhiều A/AAAA records.
- Kubernetes EndpointSlice hoặc headless service.
- Cấu hình tĩnh trong môi trường nhỏ.
- Một discovery API của nền tảng.

Danh sách instance nên có các trường cần thiết:

| Trường | Mục đích |
|---|---|
| instanceId | Định danh ổn định của instance |
| host | Hostname hoặc IP |
| port | TCP port |
| transport | TCP hoặc WebSocket |
| zone/region | Lựa chọn gần client hoặc giới hạn vùng |
| weight/capacity | Trọng số hoặc năng lực tương đối |
| health/readiness | Instance có nhận workload mới không |
| version | Phiên bản service nếu cần routing theo compatibility |

Discovery phải cập nhật khi instance scale lên/xuống hoặc bị loại bỏ. Không nên resolve danh sách một lần khi application start rồi giữ vĩnh viễn.

### DNS và cache

DNS có thể trả nhiều địa chỉ, nhưng JVM, OS và thư viện client có thể cache kết quả theo TTL khác nhau. DNS round robin không đồng nghĩa mỗi request được chọn một IP mới. Nếu client giữ một connection lâu dài, mọi request trên connection đó vẫn đi tới cùng instance.

Với hệ thống cần cân bằng rõ ràng, hãy xác định TTL, refresh strategy, xử lý địa chỉ lỗi và cách loại bỏ connection cũ khi endpoint biến mất.

## 7. Connection pool theo từng instance

Client-side load balancer nên tái sử dụng connection tới từng instance. Mở connection mới cho mỗi request sẽ gây nhiều handshake, socket, keepalive và allocation; nó cũng làm tải cân bằng bị nhiễu bởi chi phí kết nối.

Một pool có thể lưu:

- RSocketRequester hoặc RSocket session theo instance.
- Trạng thái kết nối và thời điểm kết nối.
- Số interaction đang chạy hoặc metric tải ước lượng.
- Trạng thái health/circuit breaker.
- Thời điểm last-used và deadline drain.
- Giới hạn connection/session theo instance.

~~~mermaid
flowchart LR
    A[Load balancer] --> B[Connection pool]
    B --> C[Instance A: RSocket session]
    B --> D[Instance B: RSocket session]
    B --> E[Instance C: RSocket session]
    C --> F[Concurrent streams]
    D --> G[Concurrent requests]
    E --> H[Channels and streams]
~~~

Một connection có thể multiplex nhiều interaction, vì vậy không nhất thiết cần một socket cho mỗi request. Số connection cần thiết phụ thuộc vào giới hạn concurrency, throughput, memory, transport và khả năng của server.

### Ví dụ tạo requester cho một instance

Trong Spring, có thể tạo một RSocketRequester gắn với từng địa chỉ instance và giữ nó trong pool:

~~~java
Mono<RSocketRequester> connectTo(
        ServiceInstance instance,
        RSocketStrategies strategies) {

    return RSocketRequester.builder()
        .rsocketStrategies(strategies)
        .dataMimeType(MimeTypeUtils.APPLICATION_JSON)
        .metadataMimeType(COMPOSITE_METADATA)
        .connectTcp(instance.host(), instance.port());
}
~~~

Đây là bước mở một connection tới một instance cụ thể. Pool chịu trách nhiệm cache requester, tránh tạo lại liên tục, kiểm tra connection lifecycle và dispose requester khi instance bị loại khỏi discovery.

Đối với browser hoặc endpoint WebSocket, dùng phương thức kết nối WebSocket tương ứng của Spring RSocketRequester; backend TCP và browser WSS có thể dùng cùng contract payload nhưng khác transport.

## 8. Chọn thuật toán ở phía gọi

Không có thuật toán tốt nhất cho mọi workload. Cần chọn theo độ đồng đều của request cost, khả năng của instance và yêu cầu affinity.

| Thuật toán | Cách hoạt động | Phù hợp |
|---|---|---|
| Round robin | Lần lượt chọn từng instance | Instance đồng cấu hình, request cost tương đối đều |
| Weighted round robin | Instance có weight cao nhận nhiều request hơn | Backend khác capacity |
| Random | Chọn ngẫu nhiên | Đơn giản, phân phối tốt khi số request lớn |
| Least outstanding | Chọn instance có ít interaction đang chạy | Request có thời gian xử lý khác nhau |
| Least latency | Ưu tiên instance có latency thấp | Cần phản ứng theo chất lượng gần đây |
| Consistent hashing | Cùng key thường về cùng instance | Cache locality hoặc state affinity |
| Zone-aware | Ưu tiên instance cùng zone | Giảm network latency/cost |

### Round robin

~~~java
final class RoundRobinSelector {

    private final List<ServiceInstance> instances;
    private final AtomicInteger cursor = new AtomicInteger();

    RoundRobinSelector(List<ServiceInstance> instances) {
        this.instances = List.copyOf(instances);
    }

    ServiceInstance next() {
        if (instances.isEmpty()) {
            throw new IllegalStateException("No healthy instance");
        }

        int index = Math.floorMod(
            cursor.getAndIncrement(),
            instances.size()
        );

        return instances.get(index);
    }
}
~~~

Đây là ví dụ đơn giản. Trong production, danh sách instance phải được cập nhật an toàn khi discovery thay đổi; selector không nên giữ một snapshot cũ mãi mãi.

### Weighted selection

Giả sử instance A có capacity gấp đôi B và C. Có thể gán weight A=2, B=1, C=1. Trong một chu kỳ bốn lượt, A được chọn hai lần còn B/C mỗi instance một lần.

Weight nên dựa trên capacity đo được hoặc cấu hình vận hành có chủ đích. Không tăng weight chỉ vì instance đang có ít connection; một instance ít connection vẫn có thể đang chạy tác vụ rất nặng.

### Least outstanding interactions

Nếu request có thời gian xử lý khác nhau, số interaction đang chạy có thể phản ánh tải tốt hơn số connection. Cần cập nhật counter khi interaction bắt đầu và khi complete/error/cancel.

Với request-stream dài hạn, một stream có thể tồn tại nhiều phút. Đếm mỗi stream là một interaction giúp nhận biết chi phí giữ tài nguyên, nhưng không phản ánh số byte hoặc CPU chính xác. Có thể kết hợp số interaction, latency, throughput và metric server.

## 9. Ví dụ chọn instance cho từng request

Một abstraction có thể tách discovery, selector và connection pool:

~~~java
public interface RSocketRequesterPool {
    Mono<RSocketRequester> requesterFor(ServiceInstance instance);
}

public interface InstanceSelector {
    Mono<ServiceInstance> choose(String serviceId);
}
~~~

Client service:

~~~java
public class InventoryClient {

    private final InstanceSelector selector;
    private final RSocketRequesterPool requesterPool;

    public InventoryClient(
            InstanceSelector selector,
            RSocketRequesterPool requesterPool) {
        this.selector = selector;
        this.requesterPool = requesterPool;
    }

    public Mono<InventoryResult> check(
            InventoryCheckRequest request) {

        return selector.choose("inventory")
            .flatMap(requesterPool::requesterFor)
            .flatMap(requester ->
                requester.route("inventory.check")
                    .data(request)
                    .retrieveMono(InventoryResult.class)
            );
    }
}
~~~

Đây là skeleton minh họa ranh giới trách nhiệm:

- InstanceSelector chọn một instance khỏe cho interaction mới.
- RSocketRequesterPool trả requester đã kết nối hoặc tạo connection khi cần.
- InventoryClient thực hiện route qua requester đã chọn.

Trong triển khai thật, selector và pool cần phối hợp để không chọn instance đã bị drain, xử lý race giữa discovery refresh và connection creation, giới hạn connection attempt và loại bỏ connection lỗi.

Nếu dùng Spring Cloud LoadBalancer, có thể tái sử dụng các abstraction discovery/selection của Spring Cloud Commons, nhưng không nên giả định RSocketRequester tự động được cân bằng giống WebClient. Cần adapter hoặc lớp gọi chủ động lấy ServiceInstance rồi dùng requester/connection tương ứng.

## 10. Cân bằng theo interaction, không theo từng frame

Một điểm quan trọng là đơn vị lựa chọn khác nhau theo interaction:

| Interaction | Thời điểm chọn instance | Phạm vi gắn với instance |
|---|---|---|
| Request-response | Khi bắt đầu request | Một request |
| Fire-and-forget | Khi gửi interaction | Một interaction, không có response |
| Request-stream | Khi mở stream | Toàn bộ stream cho tới terminal/cancel |
| Request-channel | Khi mở channel | Toàn bộ interaction hai chiều |

Với request-stream, nếu chọn backend A rồi A phát 10.000 item, client-side balancer không chọn lại backend cho từng item. Muốn chuyển sang instance khác, cần kết thúc stream và mở một stream mới theo giao thức ứng dụng, thường kèm cursor hoặc sequence để tiếp tục từ vị trí đã nhận.

Với request-channel, request và response hai chiều gắn với cùng interaction. Không thể gửi nửa input stream tới A và nửa còn lại tới B trừ khi ứng dụng tự chia dữ liệu thành các interaction độc lập có ID và thứ tự rõ ràng.

## 11. Affinity, state và RSocket resume

Một số dịch vụ giữ state trong memory của connection hoặc session. Nếu client reconnect tới instance khác, state cục bộ đó có thể không tồn tại.

Các trường hợp cần cân nhắc affinity:

- RSocket resume yêu cầu peer có thể khôi phục session/resume state.
- Một workflow gắn với state cục bộ của một instance.
- Cache local có giá trị lớn và muốn giữ locality.
- Stream cần tiếp tục từ cursor gắn với một backend cụ thể.

Có ba hướng:

1. Sticky routing để reconnect quay lại cùng instance.
2. Lưu session/workflow state ở kho dùng chung hoặc có replication.
3. Thiết kế reconnect ở cấp ứng dụng: mở interaction mới tới instance bất kỳ và tiếp tục bằng cursor/sequence bền vững.

RSocket resume và application-level replay là hai cơ chế khác nhau. Resume khôi phục một RSocket session theo khả năng protocol và cấu hình; cursor ứng dụng khôi phục vị trí dữ liệu nghiệp vụ. Nếu không có state/resume buffer ở peer mới, chỉ đổi backend không tự phục hồi session.

Affinity cũng có thể làm giảm hiệu quả phân phối tải. Chỉ sử dụng khi yêu cầu session thực sự cần nó và có chính sách khi instance bị mất hoàn toàn.

## 12. Health check và loại bỏ instance lỗi

Service discovery có thể trả instance tồn tại trong registry nhưng instance đó không còn phục vụ được. Cần kết hợp:

- Readiness: instance có nhận request mới không?
- Liveness: process còn hoạt động không?
- Active health check: client hoặc LB kiểm tra định kỳ.
- Passive health: ghi nhận connect failure, timeout và protocol error.
- Circuit breaker: tạm ngừng chọn instance có lỗi liên tục.
- Recovery probe: thử lại có giới hạn để đưa instance trở lại pool.

Không nên coi TCP port mở là đủ để kết luận ứng dụng sẵn sàng. RSocket server có thể chưa hoàn tất startup hoặc dependency quan trọng đang unavailable.

Client-side balancer nên ngừng chọn instance khi readiness chuyển false hoặc failure rate vượt ngưỡng. Tuy nhiên, cần phân biệt lỗi của một request với lỗi toàn instance. Validation error hoặc business rejection không nên làm instance bị đánh dấu unhealthy.

## 13. Retry và circuit breaker

Nếu connect hoặc interaction thất bại, client có thể thử instance khác. Nhưng retry có thể tạo side effect trùng lặp nếu server đã xử lý request trước khi response bị mất.

Quy tắc:

- Lỗi kết nối trước khi gửi payload thường có thể retry an toàn hơn.
- Timeout sau khi gửi request là kết quả không xác định; server có thể đã commit.
- Command ghi dữ liệu cần idempotency key ổn định qua các lần retry.
- Chỉ retry lỗi tạm thời; không retry validation, authentication hoặc business conflict.
- Dùng exponential backoff và jitter để tránh nhiều client cùng reconnect đồng thời.
- Giới hạn số lần thử và deadline tổng.
- Circuit breaker ngăn client tiếp tục dồn tải vào instance đang lỗi.

~~~java
Mono<InventoryResult> checkWithRetry(
        InventoryCheckRequest request) {

    return checkOnce(request)
        .retryWhen(
            Retry.backoff(2, Duration.ofMillis(100))
                .maxBackoff(Duration.ofSeconds(1))
                .filter(this::isRetryable)
        );
}
~~~

Đoạn code chỉ minh họa retry theo policy. Để retry sang instance khác, mỗi lần attempt cần chọn lại từ danh sách instance còn khỏe; nếu chỉ resubscribe vào một Mono đã capture cùng requester thì có thể vẫn gọi lại đúng backend lỗi.

Với request-stream đang chạy, không tự động chuyển giữa các instance sau khi stream phát một phần dữ liệu. Cần cursor/sequence và quy tắc replay để không mất hoặc lặp event.

## 14. Graceful draining khi scale hoặc deploy

Khi một instance chuẩn bị shutdown, cần ngừng nhận interaction mới nhưng cho các connection/stream đang chạy có thời gian hoàn tất.

Quy trình draining điển hình:

1. Đánh dấu instance không còn ready để discovery/LB ngừng chọn mới.
2. Client-side balancer loại instance khỏi danh sách lựa chọn.
3. Giữ các connection hiện tại trong một khoảng drain window.
4. Cho request-response ngắn hoàn tất.
5. Cho stream hoàn tất tự nhiên hoặc kết thúc theo deadline/cursor policy.
6. Sau deadline, đóng connection và để client reconnect có jitter.
7. Dispose resource và dừng process.

~~~mermaid
stateDiagram-v2
    [*] --> Ready
    Ready --> Draining: Readiness=false
    Draining --> NoNewInteractions: Removed from selection
    NoNewInteractions --> WaitingForActiveStreams
    WaitingForActiveStreams --> Closed: Active count=0
    WaitingForActiveStreams --> ForcedClose: Drain deadline
    ForcedClose --> Closed
    Closed --> [*]
~~~

Nếu load balancer chỉ bỏ backend khỏi danh sách nhưng connection hiện tại vẫn tồn tại, nó không tự chuyển các stream đang chạy. Việc đóng connection phải phối hợp với client reconnect, resume hoặc application cursor.

## 15. Cân bằng tải theo loại workload

| Workload | Cách cân bằng gợi ý | Lưu ý |
|---|---|---|
| Request-response ngắn, stateless | Client-side round robin hoặc weighted | Có thể chọn instance cho từng request |
| Request-response có chi phí khác nhau | Least outstanding/latency-aware | Cần metric và giới hạn counter |
| Fire-and-forget telemetry | L4 hoặc client-side pool | Xác định rõ khi không có ACK |
| Request-stream dài | Chọn instance khi mở stream | Cần affinity hoặc cursor khi reconnect |
| Request-channel | Chọn instance khi mở channel | Một interaction gắn với một responder |
| Session stateful | Sticky/session-aware routing | Có kế hoạch khi node mất |
| Event cần bền vững | Broker/outbox kết hợp RSocket API | Không dựa vào connection LB để bảo đảm delivery |

Một số hệ thống dùng network LB ở ingress cho browser và client-side balancing ở backend. Đây là cách kết hợp hợp lý: ingress đơn giản hóa truy cập bên ngoài; backend client có thông tin service discovery và có thể cân bằng theo từng interaction.

## 16. Quan sát hiệu quả cân bằng tải

Không chỉ quan sát số connection. Hãy đo theo từng instance:

- Số connection RSocket đang mở.
- Số interaction đang chạy theo loại.
- Request rate và stream count.
- Số payload/byte vào-ra.
- CPU, heap, direct memory và event-loop utilization.
- Latency p50/p95/p99.
- Connect failure, timeout, protocol error và reconnect.
- Circuit breaker open/close.
- Số request bị retry và số request chuyển sang instance khác.
- Số stream bị đóng khi draining.

Một dashboard hữu ích nên đặt cạnh nhau connection count, active interaction count, throughput và latency. Nếu connection count đồng đều nhưng throughput lệch mạnh, có thể client đang multiplex quá nhiều workload trên một số ít connection.

Không gắn requestId hoặc userId duy nhất vào metric label vì cardinality tăng nhanh. Có thể dùng instanceId, serviceId, zone, interaction type và outcome làm dimension có kiểm soát.

## 17. Kiểm thử cân bằng tải

Cần kiểm thử cả thuật toán chọn instance và hành vi transport thực.

| Kịch bản | Điều cần xác nhận |
|---|---|
| Nhiều request-response | Phân phối theo policy đã chọn |
| Một connection mang nhiều request | Tất cả interaction trên connection vẫn tới cùng backend |
| Nhiều client connection qua L4 | Connection được phân phối theo thuật toán LB |
| Browser WebSocket qua L7 | Backend được chọn ở handshake và giữ cho connection |
| Thêm instance mới | Discovery refresh đưa instance vào lựa chọn |
| Instance readiness=false | Request mới không chọn instance đó |
| Instance mất đột ngột | Circuit breaker/health loại node và client reconnect |
| Timeout sau server commit | Retry cùng idempotency key không tạo duplicate |
| Stream dài khi drain | Stream hoàn tất hoặc reconnect theo cursor policy |
| Một instance chậm | Least outstanding/latency policy phản ứng đúng |
| Affinity được bật | Reconnect quay về node phù hợp hoặc có fallback rõ |
| Pool quá nhiều connection | Giới hạn pool ngăn socket/resource tăng vô hạn |

### Kiểm thử selection policy

~~~java
@Test
void roundRobinDistributesAcrossHealthyInstances() {
    List<ServiceInstance> instances = List.of(
        instance("a"),
        instance("b"),
        instance("c")
    );

    RoundRobinSelector selector =
        new RoundRobinSelector(instances);

    assertThat(selector.next().instanceId()).isEqualTo("a");
    assertThat(selector.next().instanceId()).isEqualTo("b");
    assertThat(selector.next().instanceId()).isEqualTo("c");
    assertThat(selector.next().instanceId()).isEqualTo("a");
}
~~~

### Kiểm thử connection affinity

Tạo ba server với instance ID riêng. Client mở một RSocket connection tới LB và gửi nhiều request trên cùng requester; xác nhận các request được xử lý bởi backend đã nhận connection. Sau đó mở nhiều connection mới và quan sát phân phối của L4.

Test riêng client-side balancing bằng cách gửi mỗi request qua requester pool đã chọn; xác nhận request mới có thể tới các instance khác nhau theo selector.

## 18. Các nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu đúng |
|---|---|
| L4 round robin chia từng RSocket request | Nó thường chia connection mới; interaction trên connection giữ nguyên backend |
| WebSocket L7 proxy chọn lại backend cho từng RSocket route | Proxy thông thường chọn ở handshake rồi giữ tunnel |
| Một connection bằng một request | Một RSocket connection multiplex nhiều interaction |
| Chỉ cần số connection đồng đều | Cần quan sát interaction, throughput, latency và tài nguyên |
| Mở connection mới cho mỗi request | Tạo handshake/socket overhead; nên dùng pool |
| Có DNS round robin là cân bằng từng request | DNS cache và connection reuse có thể giữ client ở một endpoint |
| Có thể chuyển một stream đang chạy sang node khác | Stream gắn với responder; cần resume hoặc mở stream mới bằng cursor |
| Retry timeout luôn an toàn | Server có thể đã commit; cần idempotency key |
| Sticky session luôn tốt | Affinity có thể tạo hotspot và giảm khả năng failover |
| Bỏ node khỏi registry là đủ để drain | Connection cũ vẫn tồn tại; cần drain và close policy |
| Spring Cloud LoadBalancer tự cân bằng RSocketRequester | Cần tích hợp/adapter để chọn ServiceInstance và connection tương ứng |

## 19. Quy trình thiết kế cân bằng tải cho RSocket

Khi triển khai một RSocket service có nhiều instance, hãy thực hiện theo thứ tự:

1. Xác định client kết nối qua TCP, WebSocket hay gateway.
2. Xác định LB đang phân phối connection hay interaction.
3. Xác định connection RSocket có multiplex nhiều request/stream hay không.
4. Chọn network LB, client-side LB hoặc kết hợp cả hai.
5. Thiết kế service discovery, readiness và health policy.
6. Tạo connection pool theo instance và giới hạn tài nguyên.
7. Chọn thuật toán theo capacity và workload.
8. Xác định interaction nào cần affinity hoặc state sharing.
9. Định nghĩa retry, idempotency, circuit breaker và reconnect.
10. Thiết kế draining cho request và stream dài hạn.
11. Đo connection, interaction, throughput, latency và failure theo instance.
12. Kiểm thử phân phối, node failure, timeout, stream cancellation và rolling deploy.

Cân bằng kết nối ở tầng mạng giúp phân phối socket và đơn giản hóa điểm truy cập. Cân bằng yêu cầu ở phía gọi giúp chọn instance cho từng interaction mới. Với RSocket, hai cấp này cần được phân biệt vì một connection dài hạn có thể mang nhiều request và stream. Chọn đúng ranh giới, quản lý connection pool và thiết kế retry/affinity theo lifecycle interaction sẽ giúp hệ thống phân phối tải tốt mà vẫn giữ đúng ngữ nghĩa realtime.

## Ghi nhớ

- L4 load balancer thường chọn backend cho một TCP connection mới.
- L7 proxy chọn backend khi xử lý HTTP/WebSocket handshake; tunnel đã upgrade thường giữ nguyên backend.
- Một RSocket connection multiplex nhiều interaction và không tự cân bằng lại từng request ở tầng mạng.
- Client-side balancing chọn instance cho interaction mới qua connection pool.
- Request-stream và request-channel gắn với một responder trong suốt interaction.
- Service discovery phải cập nhật instance, health và readiness.
- Round robin phù hợp khi capacity tương tự; weighted/least-outstanding phù hợp workload không đồng đều.
- Affinity cần thiết khi session state yêu cầu nhưng có thể tạo hotspot.
- Retry timeout phải tính tới kết quả không xác định và idempotency.
- Draining cần ngừng request mới, chờ stream cũ và phối hợp reconnect.
- Đo cả connection, active interaction, throughput, latency và lỗi theo instance.

## Tài liệu tham khảo

- [RSocket Protocol](https://rsocket.io/about/protocol/)
- [Spring Framework — RSocket](https://docs.spring.io/spring-framework/reference/rsocket.html)
- [Spring Framework — RSocketRequester API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/rsocket/RSocketRequester.html)
- [Spring Cloud Commons — Spring Cloud LoadBalancer](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/loadbalancer.html)
- [NGINX — TCP and UDP Load Balancing](https://docs.nginx.com/nginx/admin-guide/load-balancer/tcp-udp-load-balancer/)
- [HAProxy — Configuration Manual](https://docs.haproxy.org/)

