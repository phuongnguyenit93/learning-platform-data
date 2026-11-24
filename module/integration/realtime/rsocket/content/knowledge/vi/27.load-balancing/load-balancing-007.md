# Giảm tải có kiểm soát khi loại một máy chủ khỏi cụm

RSocket giữ kết nối lâu dài và multiplex nhiều interaction trên cùng một connection. Khi một máy chủ bị loại khỏi cụm, cập nhật service discovery hoặc xóa địa chỉ khỏi load balancer chỉ ngăn các kết nối mới được phân phối tới node đó; những TCP/WebSocket connection đang mở vẫn có thể tiếp tục gửi request và giữ stream.

Drain là giai đoạn chuyển node từ trạng thái nhận traffic sang trạng thái rời cụm. Quy trình an toàn cần đánh dấu node không còn nhận traffic mới, thông báo cho requester hiện tại ngừng khởi tạo request mới, rồi chờ hoặc chủ động kết thúc các interaction đang chạy trước khi đóng server. RSocket LEASE hỗ trợ bước thứ hai; readiness, service discovery, chính sách xử lý stream và graceful shutdown hoàn thiện toàn bộ quy trình.

## Mục tiêu học tập

Sau bài học, người học có thể:

- Giải thích vì sao loại node khỏi load balancer không tự kết thúc các RSocket connection đang mở.
- Phân biệt readiness, service discovery, LEASE và graceful shutdown.
- Bật LEASE ở server và requester Java.
- Gửi lease rỗng để ngừng cấp quyền tạo request mới.
- Từ chối SETUP mới khi node đã vào trạng thái draining.
- Phân phối request mới sang các node còn khả dụng bằng client-side load balancing.
- Xử lý request-response, fire-and-forget, request-stream và request-channel đang chạy.
- Thiết kế grace period, timeout, retry và cơ chế resume nghiệp vụ.
- Kiểm thử việc rút một node khỏi cụm mà không làm gián đoạn toàn bộ dịch vụ.

## 1. Vì sao cần drain thay vì tắt máy chủ ngay?

RSocket là giao thức có trạng thái. Sau SETUP, một connection có thể tồn tại trong thời gian dài và mang nhiều stream đồng thời. Ví dụ một gateway mở một connection tới mỗi server trong cụm; trên connection đó có thể có truy vấn trạng thái, event một chiều và stream telemetry.

Nếu tắt server ngay khi orchestrator yêu cầu thay thế instance:

- Request-response đang xử lý có thể bị lỗi giữa chừng.
- Fire-and-forget có thể đã gửi nhưng client không biết server đã xử lý hay chưa.
- Request-stream và request-channel có thể bị ngắt khi đang trao đổi dữ liệu.
- Client có thể reconnect liên tục vào node đang chuẩn bị dừng nếu service discovery chưa cập nhật.
- Retry đồng loạt có thể dồn tải lên các node còn lại.

| Trạng thái | Nhận kết nối mới | Nhận request mới trên connection cũ | Xử lý interaction đang chạy |
|---|---|---|---|
| READY | Có | Có | Tiếp tục |
| DRAINING | Không | Không, nếu requester tuân thủ LEASE | Hoàn tất hoặc kết thúc theo chính sách |
| STOPPING | Không | Không | Chỉ còn cleanup trong thời gian cuối |
| STOPPED | Không | Không | Không còn |

~~~mermaid
stateDiagram-v2
    [*] --> READY
    READY --> DRAINING: readiness false + deregister
    DRAINING --> DRAINING: LEASE zero + chờ in-flight
    DRAINING --> STOPPING: hết việc hoặc hết grace period
    STOPPING --> STOPPED: đóng transport và giải phóng tài nguyên
    STOPPED --> [*]
~~~

## 2. Phân biệt bốn cơ chế điều phối

Không có một cơ chế đơn lẻ nào thực hiện toàn bộ drain.

| Cơ chế | Phạm vi | Tác dụng khi rút node |
|---|---|---|
| Readiness / service discovery | Cụm và load balancer | Ngừng đưa node vào danh sách nhận kết nối mới |
| RSocket LEASE | Từng RSocket connection | Ngăn requester bắt đầu request mới trên connection đó |
| Application drain signal | Từng stream hoặc nghiệp vụ | Báo cho stream/channel dừng tại checkpoint hoặc phát tín hiệu kết thúc |
| Graceful shutdown | Vòng đời ứng dụng và transport | Chờ trong thời gian giới hạn rồi đóng server |

Ví dụ, Kubernetes readiness probe có thể đánh dấu pod là REFUSING_TRAFFIC. Service discovery sau đó loại endpoint khỏi danh sách node khả dụng. Tuy nhiên, kết nối RSocket đã được mở trước đó vẫn tồn tại. LEASE được gửi trên connection để requester biết node không còn nhận request mới.

Một load balancer tầng TCP/L4 thường chỉ chọn backend lúc tạo connection. Nó không tự chuyển các stream đang chạy sang backend khác. Với RSocket, cần phối hợp cả client-side load balancing và quản lý connection lifecycle.

## 3. LEASE hoạt động như thế nào?

LEASE là frame do responder gửi cho requester. Frame này cấp số request tối đa mà requester được phép khởi tạo trong một khoảng TTL. Requester phải tuân thủ số lượng request và thời hạn của lease.

Một lease thông thường có hai giá trị:

- timeToLive: thời gian lease còn hiệu lực.
- numberOfRequests: số request mới được phép gửi trong khoảng thời gian đó.

LEASE áp dụng cho mọi interaction khởi tạo request: request-response, fire-and-forget, request-stream và request-channel. Khi lease hết hạn hoặc số request được cấp đã dùng hết, requester không được khởi tạo thêm request cho đến khi nhận lease mới.

Protocol cho phép responder dừng cấp request mới bằng lease có số request bằng 0 hoặc TTL bằng 0. Trong rsocket-java, Lease.empty() là cách biểu diễn lease rỗng.

### Luồng drain qua LEASE

~~~mermaid
sequenceDiagram
    participant O as Orchestrator
    participant S as RSocket Server A
    participant C as RSocket Client
    participant B as RSocket Server B
    O->>S: Bắt đầu drain
    O->>S: Đánh dấu readiness REFUSING_TRAFFIC
    S-->>C: LEASE (0 request)
    Note over C,S: Không khởi tạo request mới trên connection A
    C->>B: Request mới qua connection B
    Note over S: Request/stream đã mở trên A tiếp tục theo chính sách
    S-->>C: Hoàn tất response hoặc drain marker
    O->>S: Hết in-flight hoặc hết grace period
    S-->>C: Đóng connection
    O->>S: Dừng server
~~~

Một số điểm cần nhớ:

1. Client phải thông báo trong SETUP rằng nó sẽ tuân thủ LEASE bằng cờ L.
2. Server chỉ có thể dựa vào LEASE khi requester đã thương lượng tính năng này.
3. Lease mới nhất thay thế lease trước đó trên connection.
4. Lease rỗng ngăn request mới; nó không gửi CANCEL cho stream đang chạy.
5. LEASE không di chuyển connection hoặc stream sang node khác.
6. LEASE không thay thế readiness hoặc service discovery vì nó không ngăn một client tạo TCP/WebSocket connection mới tới node.

Nếu client không bật LEASE hoặc implementation không tuân thủ lease, server vẫn cần từ chối request ở tầng ứng dụng hoặc đóng connection sau grace period.

## 4. Bật LEASE ở requester Java

Với rsocket-java, RSocketConnector.lease() bật cờ tuân thủ lease trong SETUP. Ví dụ:

~~~java
import io.rsocket.core.RSocketConnector;

RSocketConnector connector = RSocketConnector.create()
        .lease(spec -> spec.maxPendingRequests(0));
~~~

maxPendingRequests(0) khiến request bị từ chối ngay khi chưa có lease khả dụng (thay vì được giữ trong hàng đợi chờ lease). Ứng dụng có thể bắt lỗi này và chọn connection khác hoặc fail fast nếu không còn capacity.

Nếu dùng Spring Boot và RSocketRequester.Builder, có thể áp dụng cấu hình cho connector qua RSocketConnectorConfigurer:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.rsocket.RSocketConnectorConfigurer;

@Configuration
public class RSocketClientConfiguration {

    @Bean
    RSocketConnectorConfigurer honorServerLease() {
        return connector ->
                connector.lease(spec -> spec.maxPendingRequests(0));
    }
}
~~~

Spring Boot áp dụng các RSocketConnectorConfigurer bean cho requester builder được auto-configure. Requester được tạo sau đó sẽ gửi SETUP với lease enabled.

Không giả định mọi client RSocket đều tự động bật LEASE. Với JavaScript, mobile client hoặc thư viện đa ngôn ngữ khác, hãy xác minh implementation có hỗ trợ và tuân thủ cờ L trước khi dựa vào lease để drain.

## 5. Phát lease ở server bằng rsocket-java

RSocketServer.lease(...) cho phép cấu hình một LeaseSender phát lease cho từng connection. Ví dụ server cấp tối đa 500 request trong 30 giây khi node đang READY:

~~~java
import io.rsocket.core.RSocketServer;
import io.rsocket.lease.Lease;
import reactor.core.publisher.Flux;

import java.time.Duration;

// socketAcceptor là SocketAcceptor đã được cấu hình cho ứng dụng.
RSocketServer server = RSocketServer.create(socketAcceptor)
        .lease(spec -> spec.sender(() ->
                Flux.just(Lease.create(
                        Duration.ofSeconds(30),
                        500))));
~~~

Trong production, server thường phát lease định kỳ dựa trên capacity thay vì cấp một lease tĩnh. Có thể giảm số request trong lease khi CPU, queue hoặc số stream đang hoạt động tăng cao. Khi node bắt đầu drain, server phát lease rỗng thay cho lease cấp request mới.

Lease là trạng thái theo connection. Nếu một server có 100 client connection, mỗi connection cần nhận tín hiệu drain. Không gửi một lease cho một connection rồi giả định tất cả requester trong cụm đều đã nhận.

### Quản lý lease động cho các connection

Một coordinator có thể phát lease ban đầu cho từng connection và broadcast lease rỗng khi bắt đầu drain. Dùng replay sink để các connection đang hoạt động nhận được tín hiệu, đồng thời connection đăng ký muộn vẫn nhìn thấy trạng thái mới nhất.

~~~java
import io.rsocket.lease.Lease;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Sinks;

import java.time.Duration;

public final class DrainLeaseCoordinator {

    private final Object monitor = new Object();
    private boolean draining;

    private final Sinks.Many<Lease> leases =
            Sinks.many().replay().latest();

    public DrainLeaseCoordinator() {
        emit(Lease.create(Duration.ofSeconds(30), 500));
    }

    public boolean isDraining() {
        synchronized (monitor) {
            return draining;
        }
    }

    public Flux<Lease> leasesForConnection() {
        return leases.asFlux();
    }

    public void publishCapacityLease(int requestBudget) {
        synchronized (monitor) {
            if (!draining) {
                emit(Lease.create(Duration.ofSeconds(30), requestBudget));
            }
        }
    }

    public void beginDrain() {
        synchronized (monitor) {
            if (!draining) {
                draining = true;
                emit(Lease.empty());
            }
        }
    }

    private void emit(Lease lease) {
        Sinks.EmitResult result = leases.tryEmitNext(lease);
        if (result.isFailure()) {
            throw new IllegalStateException("Cannot publish RSocket lease: " + result);
        }
    }
}
~~~

Replay publisher giữ lease mới nhất cho mỗi connection subscriber. Khi READY, coordinator phát lease ban đầu và capacity controller gọi publishCapacityLease(...) định kỳ hoặc khi tải thay đổi. Khi beginDrain() được gọi, monitor tuần tự hóa thao tác này với việc cấp lease mới, đặt trạng thái draining rồi phát lease rỗng. Nhờ vậy, một lease bình thường không thể được phát sau lease rỗng. Connection đã được chấp nhận nhưng đăng ký lease sender muộn vẫn nhận lease rỗng; @ConnectMapping từ chối SETUP mới.

Trong hệ thống thật, capacity controller không được gọi publishCapacityLease(...) sau khi drain bắt đầu. Ví dụ kiểm tra EmitResult và fail rõ ràng nếu sink không nhận lease; đồng thời ghi metric và bảo đảm coordinator tồn tại suốt vòng đời của RSocket server.

### Gắn coordinator vào Spring Boot server

Với RSocket server độc lập được Spring Boot tạo qua embedded Netty server, có thể dùng RSocketServerCustomizer để gắn lease sender:

~~~java
import org.springframework.boot.rsocket.server.RSocketServerCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class RSocketLeaseConfiguration {

    @Bean
    RSocketServerCustomizer leaseCustomizer(
            DrainLeaseCoordinator coordinator) {

        return server -> server.lease(
                spec -> spec.sender(coordinator::leasesForConnection));
    }
}
~~~

RSocketServerCustomizer có từ Spring Boot 2.3.0. Nếu ứng dụng gắn RSocket WebSocket vào WebFlux server bằng spring.rsocket.server.mapping-path, hãy xác minh extension point của phiên bản Spring Boot đang dùng để bảo đảm lease sender được gắn vào đúng RSocketServer đang phục vụ endpoint. Ví dụ customizer trên mô tả cấu hình server độc lập.

## 6. Từ chối SETUP mới khi node đang DRAINING

LEASE kiểm soát request trên connection đã thương lượng. Nó không tự từ chối một TCP/WebSocket connection mới. Vì vậy server cần một cổng kiểm tra trạng thái khi xử lý SETUP.

Trong Spring, @ConnectMapping xử lý frame SETUP. Nếu handler trả error khi có connection mới, Spring từ chối connection đó:

~~~java
import io.rsocket.exceptions.RejectedSetupException;
import org.springframework.messaging.rsocket.annotation.ConnectMapping;
import org.springframework.stereotype.Controller;
import reactor.core.publisher.Mono;

@Controller
public class ConnectionDrainController {

    private final DrainLeaseCoordinator drainCoordinator;

    public ConnectionDrainController(
            DrainLeaseCoordinator drainCoordinator) {
        this.drainCoordinator = drainCoordinator;
    }

    @ConnectMapping
    Mono<Void> onConnect() {
        if (drainCoordinator.isDraining()) {
            return Mono.error(
                    new RejectedSetupException("server is draining"));
        }

        return Mono.empty();
    }
}
~~~

Handler này giữ SETUP ngắn gọn và không thực hiện request ngược tới client. Ví dụ giả định ứng dụng không dùng METADATA_PUSH. @ConnectMapping cũng có thể xử lý metadata push; nếu ứng dụng có dùng, cần phân biệt loại frame và không trả RejectedSetupException cho một metadata push như thể đó là SETUP mới.

Trong một hệ thống có race giữa kiểm tra readiness và SETUP, trạng thái draining phải được cập nhật nguyên tử trước khi gửi lease rỗng. Như vậy một connection mới đến đúng thời điểm chuyển trạng thái vẫn bị từ chối.

## 7. Kết hợp readiness và service discovery

Ngay khi bắt đầu drain, node phải chặn SETUP tại chỗ; sau đó readiness giúp load balancer và service discovery ngừng chọn node cho các connection mới. Với Spring Boot Actuator, có thể chuyển readiness sang REFUSING_TRAFFIC:

~~~java
import org.springframework.boot.availability.AvailabilityChangeEvent;
import org.springframework.boot.availability.ReadinessState;
import org.springframework.context.ApplicationContext;

public void refuseNewTraffic(ApplicationContext context) {
    AvailabilityChangeEvent.publish(
            context, ReadinessState.REFUSING_TRAFFIC);
}
~~~

Readiness probe cần được load balancer, Kubernetes hoặc service registry sử dụng. Nếu chỉ đổi readiness state mà không có thành phần nào đọc nó, traffic vẫn có thể được gửi tới node.

Quy trình nên bắt đầu bằng cổng chặn tại chính node rồi mới cập nhật trạng thái cụm:

1. Gọi beginDrain() để đặt trạng thái DRAINING, từ chối SETUP mới và phát LEASE rỗng tới các connection hiện tại.
2. Đánh dấu readiness là REFUSING_TRAFFIC.
3. Yêu cầu service registry hoặc load balancer loại node khỏi danh sách endpoint cho kết nối mới.
4. Chờ thời gian propagation để các client và proxy cập nhật danh sách.
5. Theo dõi và drain các interaction đã mở.

Không đánh dấu liveness là lỗi chỉ để loại node. Liveness thất bại có thể khiến orchestrator restart hoặc kill process ngay, phá vỡ quá trình drain. Readiness điều khiển việc nhận traffic; liveness cho biết process còn sống và có thể tiếp tục cleanup.

## 8. Client-side load balancing chuyển request sang node khác

RSocket Java có package io.rsocket.loadbalance để duy trì pool các RSocket connection tới nhiều target và chọn connection cho mỗi request. LoadbalanceRSocketClient có từ rsocket-core 1.1.0. WeightedLoadbalanceStrategy xét availability và thống kê sử dụng để chọn connection.

Ví dụ dưới đây giả định service discovery phát snapshot danh sách target định kỳ:

~~~java
import io.rsocket.core.RSocketConnector;
import io.rsocket.loadbalance.LoadbalanceRSocketClient;
import io.rsocket.loadbalance.LoadbalanceTarget;
import io.rsocket.transport.netty.client.TcpClientTransport;
import reactor.core.publisher.Flux;

import java.time.Duration;
import java.util.List;

Flux<List<LoadbalanceTarget>> targetSnapshots =
        Flux.interval(Duration.ZERO, Duration.ofSeconds(5))
                .concatMap(tick -> discoveryService.currentPoolTargets())
                .map(instances -> instances.stream()
                        .map(instance -> LoadbalanceTarget.from(
                                instance.id(),
                                TcpClientTransport.create(
                                        instance.host(), instance.port())))
                        .toList());

RSocketConnector connector = RSocketConnector.create()
        .lease(spec -> spec.maxPendingRequests(0));

LoadbalanceRSocketClient client =
        LoadbalanceRSocketClient.builder(targetSnapshots)
                .connector(connector)
                .weightedLoadbalanceStrategy()
                .build();
~~~

discoveryService.currentPoolTargets() là API minh họa do ứng dụng định nghĩa; nó trả snapshot của pool, gồm cả target đang drain cho tới khi các interaction cũ kết thúc. Connector bật LEASE để client tôn trọng capacity do từng server cấp.

Khi server A phát lease rỗng, availability của RSocket connection A về 0. Weighted strategy có thể chọn các connection còn khả dụng như B. Giữ connection A trong snapshot của pool trong thời gian drain để các stream hiện hữu tiếp tục; chỉ loại A khỏi snapshot sau khi drain hoàn tất. Nếu loại target khỏi pool quá sớm, implementation có thể dispose connection và cắt các interaction đang chạy. Ở lớp service discovery dùng cho kết nối mới, A vẫn phải được đánh dấu không khả dụng ngay từ đầu.

RSocketRequester thông thường đại diện cho một connection cụ thể; nó không tự phân phối từng request qua nhiều server. Nếu cần client-side load balancing, dùng một client pool/strategy phù hợp hoặc tích hợp lớp cân bằng tải ở tầng ứng dụng.

Nếu tất cả target đều hết lease hoặc không khả dụng, client cần chính sách rõ ràng: fail fast, chờ có capacity trong giới hạn hoặc trả lỗi overload. Khi pool có hơn hai connection, WeightedLoadbalanceStrategy cố ưu tiên cặp có availability dương nhưng có giới hạn số lần thử; khi hết lượt, nó có thể dùng lựa chọn cuối. Nếu cần fail fast tuyệt đối khi không có target khả dụng, hãy thêm guard/custom strategy kiểm tra availability trước khi dispatch. Không tạo hàng đợi vô hạn ở client vì điều đó chỉ chuyển quá tải từ server sang bộ nhớ client.

## 9. Điều gì xảy ra với request đang chạy?

LEASE chỉ ngăn khởi tạo request mới. Nó không hủy các stream đã mở, không gửi CANCEL và không chuyển state của stream sang node khác.

| Interaction | Khi node bắt đầu drain | Chính sách đề xuất |
|---|---|---|
| Request-response | Request đã nhận tiếp tục xử lý | Cho hoàn tất trong grace period |
| Fire-and-forget | Không có response để xác nhận nghiệp vụ | Dùng event ID, idempotency và outbox nếu cần retry an toàn |
| Request-stream | Stream có thể tồn tại lâu sau khi lease bằng 0 | Hoàn tất tại checkpoint, phát drain marker rồi client mở stream mới |
| Request-channel | Hai chiều có thể tiếp tục gửi PAYLOAD trên stream hiện tại | Phát tín hiệu dừng, ngừng nhận batch mới và đóng tại checkpoint |

Một connection có thể không tạo thêm request mới nhưng vẫn mang nhiều PAYLOAD frame của request-channel đang hoạt động. Vì vậy LEASE không phải cơ chế giới hạn mọi byte hoặc mọi message trên các stream cũ.

### Request-response

Với request-response ngắn, hãy cho handler hoàn tất. Theo dõi số request đang xử lý và thời gian xử lý còn lại. Nếu vượt grace period, đóng connection hoặc trả lỗi có thể retry; client chỉ retry các command an toàn hoặc có idempotency key.

### Fire-and-forget

Fire-and-forget không trả ACK nghiệp vụ. Nếu client mất kết nối sau khi gửi, nó không thể biết server đã commit side effect hay chưa. Khi drain, các event quan trọng nên có event ID ổn định, consumer deduplicate và producer lưu outbox trước khi gửi lại qua node khác.

### Request-stream

Stream dài hạn nên có checkpoint hoặc cursor. Server có thể phát một event cuối như DRAINED kèm sequence cuối cùng, sau đó hoàn tất stream. Client kết nối tới node khác và mở stream mới từ sequence đã nhận cuối cùng.

Ví dụ handler minh họa:

~~~java
@MessageMapping("telemetry.readings")
public Flux<ReadingEvent> readings(
        @Payload ReadingQuery query) {

    return readingService.stream(query.deviceId())
            .takeUntilOther(drainCoordinator.onDrain())
            .concatWith(Mono.fromSupplier(() ->
                    ReadingEvent.drained(
                            checkpointStore.lastSequence(query.deviceId()))));
}
~~~

onDrain() và lastSequence(...) là API do ứng dụng định nghĩa. Checkpoint phải đại diện cho dữ liệu đã gửi/được xác nhận theo hợp đồng. Nếu chỉ lấy sequence cuối của producer mà client chưa nhận, có thể bỏ sót dữ liệu.

### Request-channel

Với channel, client và server đều có thể gửi payload trên cùng interaction. Khi drain, server nên ngừng yêu cầu batch mới, báo client hoàn tất batch hiện tại, ghi checkpoint rồi kết thúc channel. Client mở channel mới trên node còn khả dụng và tiếp tục từ checkpoint.

## 10. Grace period và thời điểm đóng server

Grace period là khoảng thời gian node dành cho công việc đã nhận trước khi đóng transport. Thời lượng phải dựa trên latency thực tế và thời gian sống của stream.

Một trình tự có thể triển khai:

1. **Đặt trạng thái DRAINING:** chặn SETUP mới và phát lease rỗng tới connection hiện tại.
2. **Tắt readiness:** node không còn được service discovery chọn cho connection mới.
3. **Đợi propagation:** cho các proxy và client-side pool cập nhật endpoint.
4. **Drain in-flight:** đợi request-response và stream hoàn tất hoặc dừng tại checkpoint.
5. **Deadline:** khi hết grace period, hủy các stream còn lại theo chính sách và ghi log các interaction bị ngắt.
6. **Đóng server:** đóng RSocket server, WebSocket/TCP transport và các tài nguyên phụ thuộc.

Cấu hình Spring Boot:

~~~yaml
server:
  shutdown: graceful

spring:
  lifecycle:
    timeout-per-shutdown-phase: 45s
~~~

server.shutdown=graceful cho phép embedded web server từ chối traffic mới trong khi xử lý request đang chạy. spring.lifecycle.timeout-per-shutdown-phase giới hạn thời gian của một phase trong quá trình dừng SmartLifecycle beans.

Các thuộc tính này không tự phát LEASE, không đếm active RSocket stream và không bảo đảm một stream dài hạn hoàn tất. Ứng dụng vẫn cần drain coordinator và chính sách cho các RSocket interaction.

Với Kubernetes, terminationGracePeriodSeconds phải đủ dài cho preStop, thời gian cập nhật endpoint, grace period của ứng dụng và cleanup. Không đặt timeout của orchestrator ngắn hơn thời gian drain dự kiến, nếu không process có thể bị kill trước khi hoàn tất.

## 11. Session resumption không phải chuyển stream sang node mới

RSocket session resumption được thiết kế để khôi phục một session sau khi transport bị mất, với điều kiện hai phía còn giữ đủ state và resume buffer. Đây không phải cơ chế tự động chuyển stream sang một server instance bất kỳ.

Khi rút node A khỏi cụm:

- Nếu client reconnect vào node B không có state của session A, resumption có thể bị từ chối.
- Nếu dùng shared resume store và các node chia sẻ đúng session state, có thể thiết kế khả năng resume xuyên node, nhưng cần xác minh bằng integration test.
- LEASE không được kế thừa qua connection mới; server phải phát lease mới sau SETUP/RESUME theo protocol.
- Ứng dụng vẫn cần idempotency và checkpoint cho nghiệp vụ có side effect.

Với nhiều hệ thống, cách dễ kiểm soát hơn là kết thúc stream có chủ đích, gửi cursor/checkpoint, rồi mở interaction mới ở node còn khả dụng.

## 12. Theo dõi tiến trình drain

Không nên đóng node chỉ dựa trên một khoảng sleep cố định. Hãy theo dõi các chỉ số thực tế:

| Metric | Ý nghĩa | Điều kiện để tiếp tục shutdown |
|---|---|---|
| rsocket_active_connections | Số connection đang mở | Giảm về ngưỡng mục tiêu |
| rsocket_active_streams | Số stream đang chạy | Không còn stream quan trọng |
| rsocket_inflight_requests | Request đã nhận nhưng chưa kết thúc | Về 0 hoặc nằm trong giới hạn deadline |
| rsocket_lease_zero_sent | Số connection đã nhận lease rỗng | Bằng số connection cần drain |
| rsocket_setup_rejected_draining | SETUP mới bị từ chối | Tăng trong giai đoạn đầu rồi giảm |
| rsocket_drain_duration | Thời gian drain | Nằm trong ngân sách shutdown |
| rsocket_forced_cancellations | Interaction bị hủy khi hết deadline | Theo dõi và cảnh báo |

Theo dõi theo node ID và connection ID để biết connection nào chưa thoát. Không gắn dữ liệu cá nhân hoặc credential vào metric label.

Nếu số active connection không giảm, kiểm tra client có bật LEASE hay không, pool có loại target không, stream có thời hạn hay không và proxy có giữ connection cũ không.

## 13. Xử lý lỗi và tình huống biên

| Tình huống | Nguyên nhân | Cách xử lý |
|---|---|---|
| Node readiness false nhưng vẫn có request mới | Load balancer chưa đọc readiness hoặc endpoint cache chưa cập nhật | Kiểm tra service discovery và thời gian propagation |
| Server phát lease rỗng nhưng client vẫn gửi request | Client không bật cờ L hoặc không tuân thủ LEASE | Từ chối ở tầng ứng dụng, cập nhật client |
| Request mới bị lỗi vì hết lease | Không có node khả dụng hoặc client không chuyển target | Chọn node khác, fail fast nếu toàn cụm quá tải |
| Stream không kết thúc | Stream không có drain signal hoặc checkpoint | Thêm giới hạn tuổi stream và terminal marker |
| Request-channel vẫn gửi PAYLOAD | LEASE chỉ chặn request mới, không dừng stream hiện hữu | Dùng application signal để dừng channel |
| Retry làm lặp side effect | Request đã được xử lý nhưng response bị mất | Idempotency key, deduplication và outbox |
| Client reconnect vào đúng node đang drain | DNS/cache hoặc pool chưa cập nhật | Từ chối SETUP và refresh target list |
| Shutdown timeout trước khi drain xong | Grace period quá ngắn | Điều chỉnh timeout và terminationGracePeriodSeconds |
| Resume sang node khác thất bại | Resume state không được chia sẻ | Dùng application checkpoint và mở interaction mới |

Nếu client cũ không hỗ trợ LEASE, có thể triển khai drain bằng cách loại node khỏi discovery, từ chối SETUP mới, đánh dấu connection cũ để không nhận request qua interceptor hoặc policy ứng dụng, rồi đóng connection sau grace period. Cách này cần test theo từng client implementation.

## 14. Kiểm thử rút một node khỏi cụm

Một integration test nên có ít nhất hai server, A và B, cùng một client có khả năng mở connection tới cả hai.

| Ca kiểm thử | Thao tác | Kết quả mong đợi |
|---|---|---|
| Drain node A | Đánh dấu A REFUSING_TRAFFIC | Discovery ngừng trả A cho connection mới |
| Lease negotiation | Client mở SETUP với cờ L | A phát lease ban đầu |
| Lease zero | Bắt đầu drain A | Client không khởi tạo request mới trên connection A |
| Request chuyển node | Gửi request sau khi A drain | Load balancer chọn B |
| SETUP mới vào A | Cố mở connection mới trực tiếp tới A | @ConnectMapping từ chối SETUP |
| Request-response đang chạy | Bắt đầu request trước drain | Request hoàn tất trong grace period |
| Stream dài hạn | Mở stream rồi drain A | Server phát drain marker và client mở stream mới trên B |
| Channel đang chạy | Mở channel hai chiều rồi drain A | Batch đang xử lý hoàn tất, channel đóng theo policy |
| FNF retry | Gửi event rồi ngắt connection | Consumer deduplicate event ID |
| Deadline hết hạn | Giữ một stream không kết thúc | Stream bị cancel và metric forced cancellation tăng |
| Không còn node khả dụng | Drain toàn bộ target | Client fail fast hoặc chờ theo bounded policy |
| Rollback drain | Hủy thao tác drain trước khi dừng server | Readiness và lease được khôi phục có kiểm soát |

Nên test cả client có LEASE và client không có LEASE. Một test chỉ chạy với Java client đã bật connector.lease() không chứng minh các client khác trong hệ thống đều tuân thủ protocol.

## 15. Checklist trước khi loại node khỏi cụm

- [ ] Readiness được chuyển sang REFUSING_TRAFFIC.
- [ ] Service discovery/load balancer đã loại node khỏi danh sách connection mới.
- [ ] Client requester bật LEASE và gửi cờ L trong SETUP.
- [ ] Server phát lease rỗng tới mọi connection đang hoạt động.
- [ ] @ConnectMapping từ chối SETUP mới trong trạng thái DRAINING.
- [ ] Client-side load balancer có node khác còn khả dụng.
- [ ] Request-response có giới hạn thời gian hoàn tất.
- [ ] Fire-and-forget có event ID và cơ chế deduplicate khi retry.
- [ ] Stream dài hạn có drain marker và checkpoint.
- [ ] Request-channel có tín hiệu ngừng gửi batch mới.
- [ ] Có metric active connection, stream, in-flight request và forced cancellation.
- [ ] Grace period nhỏ hơn thời gian termination tối đa của orchestrator.
- [ ] Đã kiểm thử rollback, client không hỗ trợ LEASE và tình huống toàn cụm hết capacity.

## Kết luận

Loại một máy chủ khỏi cụm RSocket cần phối hợp readiness, service discovery, LEASE và graceful shutdown. Readiness ngăn cấp connection mới; LEASE rỗng ngăn requester đã kết nối khởi tạo request mới; application drain signal giúp stream/channel kết thúc tại checkpoint; grace period cho các request đang chạy thời gian hoàn tất trước khi transport đóng. LEASE không hủy hoặc di chuyển stream đang hoạt động, vì vậy client cần có chiến lược reconnect, cursor và idempotency phù hợp. Khi thực hiện đúng trình tự, có thể rút từng node khỏi cụm mà vẫn giữ các node còn lại phục vụ request mới.

## Tài liệu tham khảo

- [RSocket Protocol – LEASE Frame and Lease Semantics](https://rsocket.io/about/protocol/)
- [RSocket Java 1.1.5 – RSocketServer](https://javadoc.io/static/io.rsocket/rsocket-core/1.1.5/io/rsocket/core/RSocketServer.html)
- [RSocket Java 1.1.5 – RSocketConnector](https://javadoc.io/static/io.rsocket/rsocket-core/1.1.5/io/rsocket/core/RSocketConnector.html)
- [RSocket Java 1.1.5 – Lease](https://javadoc.io/static/io.rsocket/rsocket-core/1.1.5/io/rsocket/lease/Lease.html)
- [RSocket Java 1.1.5 – LoadbalanceRSocketClient](https://javadoc.io/static/io.rsocket/rsocket-core/1.1.5/io/rsocket/loadbalance/LoadbalanceRSocketClient.html)
- [RSocket Java 1.1.5 – WeightedLoadbalanceStrategy](https://javadoc.io/static/io.rsocket/rsocket-core/1.1.5/io/rsocket/loadbalance/WeightedLoadbalanceStrategy.html)
- [RSocket Java 1.1.5 – WeightedLoadbalanceStrategy.Builder](https://javadoc.io/static/io.rsocket/rsocket-core/1.1.5/io/rsocket/loadbalance/WeightedLoadbalanceStrategy.Builder.html)
- [Spring Framework Reference – RSocket and @ConnectMapping](https://docs.spring.io/spring-framework/reference/rsocket.html)
- [Spring Framework API – RSocketConnectorConfigurer](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/rsocket/RSocketConnectorConfigurer.html)
- [Spring Boot Reference – RSocket](https://docs.spring.io/spring-boot/reference/messaging/rsocket.html)
- [Spring Boot API – RSocketServerCustomizer](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/rsocket/server/RSocketServerCustomizer.html)
- [Spring Boot Reference – Graceful Shutdown](https://docs.spring.io/spring-boot/reference/web/graceful-shutdown.html)
- [Spring Boot Reference – Actuator Readiness and Liveness](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html)
