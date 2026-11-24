# Dừng có kiểm soát và xử lý các luồng đang hoạt động

RSocket thường duy trì connection trong thời gian dài và multiplex nhiều interaction trên cùng một connection. Vì vậy, dừng một instance không đơn giản là đóng socket hoặc kết thúc process. Nếu server ngừng đột ngột, request-response đang xử lý có thể mất response, request-stream bị cắt giữa chừng, request-channel mất một chiều trao đổi, còn client có thể đồng loạt reconnect và tạo thêm tải cho các instance còn lại.

Graceful shutdown cần một quy trình có thứ tự: rút instance khỏi luồng nhận traffic mới, chặn interaction mới trên các connection hiện hữu, cho interaction đang chạy hoàn tất trong một khoảng thời gian, xử lý các stream quá hạn, đóng transport và giải phóng tài nguyên. Client cũng cần biết cách kết nối lại, resume hoặc khôi phục công việc ở cấp ứng dụng.

Bài học này tập trung vào RSocket TCP/WebSocket với Java và Spring Boot. Mục tiêu là thiết kế quy trình dừng có kiểm soát cho request-response, fire-and-forget, request-stream và request-channel trong rolling deployment, scale-in hoặc sự cố cần thay thế instance.

Sau bài học, bạn có thể:

- Giải thích vì sao readiness=false chưa đủ để dừng một RSocket instance an toàn.
- Phân biệt ngừng nhận connection mới với ngừng nhận interaction mới trên connection cũ.
- Thiết kế admission gate và theo dõi số interaction đang hoạt động.
- Chọn cách hoàn tất, hủy hoặc phục hồi từng loại interaction.
- Đặt drain deadline và xử lý các stream dài hạn.
- Phối hợp readiness, service discovery, load balancer và container termination.
- Quản lý lifecycle của RSocket server trong Spring Boot.
- Thiết kế client reconnect, resume và application recovery sau khi server đóng.
- Kiểm thử rolling deployment, scale-in và shutdown khi còn nhiều stream.

## 1. Vì sao cần graceful shutdown?

Một RSocket connection có thể tồn tại hàng giờ. Trên connection đó, client có thể mở nhiều request-response, fire-and-forget, request-stream và request-channel. Một server có thể đang phục vụ hàng nghìn interaction khi orchestrator gửi SIGTERM.

Nếu process dừng ngay:

- Request-response có thể đã commit nghiệp vụ nhưng response chưa tới client.
- Fire-and-forget không có response protocol để xác nhận server đã xử lý xong.
- Request-stream bị cắt trước khi complete.
- Request-channel mất khả năng trao đổi hai chiều.
- Subscriber/listener và buffer có thể chưa được cleanup.
- Client reconnect cùng lúc tạo connection storm.
- Load balancer tiếp tục chuyển traffic tới instance đang shutdown nếu trạng thái readiness chưa lan truyền.

Graceful shutdown giảm xác suất các tình huống này bằng cách tạo một khoảng thời gian để hệ thống ngừng nhận việc mới và hoàn tất việc cũ.

~~~mermaid
flowchart TD
    A[Instance Ready] --> B[Mark Not Ready]
    B --> C[Close interaction admission gate]
    C --> D[Remove from discovery / load balancer]
    D --> E[Drain active interactions]
    E --> F{All drained before deadline?}
    F -->|Yes| G[Close RSocket connections]
    F -->|No| H[Cancel or force close remaining]
    H --> G
    G --> I[Dispose transport and resources]
    I --> J[Process exits]
~~~

Graceful shutdown không đảm bảo mọi interaction luôn hoàn tất. Nó đặt ra một thời hạn và một policy rõ ràng cho interaction chưa thể hoàn tất khi thời hạn kết thúc.

## 2. Hai cấp độ cần dừng: connection và interaction

Rút một instance khỏi load balancer thường ngăn connection mới được phân phối tới instance đó. Nhưng RSocket connection hiện có vẫn có thể tiếp tục gửi interaction mới.

Ví dụ một WebSocket đã được upgrade và giữ mở từ sáng. Khi pod chuyển readiness=false, load balancer có thể ngừng đưa WebSocket mới vào pod đó, nhưng browser đang kết nối vẫn có thể gửi request-response mới trên connection hiện hữu.

Do đó, cần quản lý hai cấp:

| Cấp độ | Việc cần làm | Mục tiêu |
|---|---|---|
| Connection admission | Ngừng nhận TCP/WebSocket connection mới | Không tạo thêm session vào instance đang drain |
| Interaction admission | Từ chối request/stream/channel mới trên session hiện có | Giới hạn công việc mới trong lúc drain |
| Active interaction | Theo dõi request/stream/channel đang chạy | Biết khi nào có thể đóng an toàn |
| Transport shutdown | Đóng connection còn lại sau deadline | Giải phóng socket và tài nguyên |

~~~mermaid
flowchart LR
    C[Existing RSocket connection] --> A{Admission gate}
    A -->|Open| B[New interaction]
    A -->|Draining| X[Reject new interaction]
    B --> D[Active interaction registry]
    D --> E[Complete / cancel / recover]
~~~

Một triển khai chỉ đặt readiness=false mà không có admission gate có thể vẫn nhận workload mới qua connection dài hạn. Đây là nguyên nhân phổ biến khiến drain không bao giờ kết thúc.

## 3. Readiness, liveness và trạng thái draining

Readiness trả lời câu hỏi instance có nên nhận traffic mới hay không. Liveness trả lời process có còn sống và cần được restart hay không.

Khi bắt đầu graceful shutdown:

- Chuyển readiness sang false.
- Giữ liveness ở trạng thái healthy trong thời gian drain.
- Cập nhật service registry hoặc endpoint discovery.
- Chờ load balancer/ingress cập nhật endpoint.
- Chặn interaction mới tại server.
- Chỉ kết thúc process sau khi drain hoàn tất hoặc deadline hết.

Không nên làm liveness fail ngay khi bắt đầu drain. Nếu orchestrator thấy liveness fail, nó có thể kill process trước khi các interaction đang chạy được hoàn tất.

Trạng thái lifecycle gợi ý:

| Trạng thái | Readiness | Liveness | Nhận connection mới | Nhận interaction mới |
|---|---|---|---|---|
| STARTING | false | true | Theo policy | Không |
| READY | true | true | Có | Có |
| DRAINING | false | true | Không | Không |
| FORCING_CLOSE | false | true | Không | Không |
| STOPPED | false | false/process exit | Không | Không |

Readiness cần chuyển false đủ sớm để endpoint propagation hoàn tất. Nhưng readiness propagation không thay thế admission gate ở tầng RSocket.

## 4. Quy trình graceful shutdown theo pha

Một quy trình thực tế có thể chia thành các pha:

1. **Announce drain:** đánh dấu instance đang drain và readiness=false.
2. **Stop new interactions:** đóng admission gate ngay để connection hiện hữu không mở thêm interaction mới.
3. **Withdraw endpoint:** gỡ instance khỏi service discovery/load balancer và chờ propagation.
4. **Stop new connections:** ngừng accept connection mới nhưng giữ connection hiện hữu trong drain window nếu transport hỗ trợ tách riêng listener.
5. **Drain active work:** chờ request-response và các stream có thể hoàn tất.
6. **Apply deadline policy:** cancel, close hoặc lưu checkpoint cho interaction quá hạn.
7. **Close connections:** gửi tín hiệu connection close phù hợp nếu protocol stack hỗ trợ, sau đó đóng transport.
8. **Dispose resources:** giải phóng listener, scheduler, sink, pool và dependency.
9. **Exit:** hoàn tất callback lifecycle để process dừng.

~~~mermaid
sequenceDiagram
    participant O as Orchestrator
    participant L as Load balancer / Discovery
    participant S as RSocket server
    participant C as Existing clients
    O->>S: SIGTERM / drain request
    S->>S: readiness = false
    S->>S: Close interaction admission gate
    S->>L: Withdraw instance
    L-->>S: Endpoint propagation window
    S->>S: Stop accepting new connections
    C->>S: Existing stream continues
    S->>S: Wait for active work
    alt Work completes before deadline
        S->>C: Complete interaction
    else Deadline expires
        S->>C: Close/cancel remaining work
    end
    S->>C: Connection close / transport close
    S->>O: Lifecycle stop completed
~~~

Các pha phải có timeout riêng hoặc ngân sách tổng. Không để bước chờ load balancer propagation tiêu thụ hết thời gian dành cho active stream.

## 5. Admission gate cho interaction mới

Admission gate là cơ chế ứng dụng quyết định interaction mới có được phép bắt đầu hay không. Gate cần được kiểm tra ở mọi route có thể tạo workload.

Ví dụ một bộ đếm đơn giản:

~~~java
public final class DrainGate {

    private final AtomicBoolean accepting = new AtomicBoolean(true);
    private final AtomicInteger active = new AtomicInteger();
    private final Sinks.Empty<Void> drained = Sinks.empty();

    public boolean tryEnter() {
        if (!accepting.get()) {
            return false;
        }

        active.incrementAndGet();

        if (!accepting.get()) {
            leave();
            return false;
        }

        return true;
    }

    public void leave() {
        int remaining = active.decrementAndGet();

        if (remaining == 0 && !accepting.get()) {
            drained.tryEmitEmpty();
        }
    }

    public void stopAccepting() {
        accepting.set(false);

        if (active.get() == 0) {
            drained.tryEmitEmpty();
        }
    }

    public Mono<Void> awaitDrained() {
        return drained.asMono();
    }

    public int activeCount() {
        return active.get();
    }

    public boolean isAccepting() {
        return accepting.get();
    }
}
~~~

Cơ chế này minh họa admission gate và counter. Trong ứng dụng thực tế, cần bổ sung policy cho trường hợp gate đã drain trước khi có subscriber chờ, xử lý lỗi emit, metrics và lifecycle reset nếu đối tượng được tái sử dụng. Thường mỗi process lifecycle chỉ drain một lần.

### Bọc interaction bằng gate

Với request-response:

~~~java
public Mono<InventoryResult> check(InventoryRequest request) {
    return Mono.defer(() -> {
        if (!drainGate.tryEnter()) {
            return Mono.error(new ServiceDrainingException());
        }

        return Mono.defer(() -> inventoryService.check(request))
            .doFinally(signal -> drainGate.leave());
    });
}
~~~

Với request-stream:

~~~java
public Flux<PriceTick> watch(WatchRequest request) {
    return Flux.defer(() -> {
        if (!drainGate.tryEnter()) {
            return Flux.error(new ServiceDrainingException());
        }

        return Flux.defer(() -> priceFeed.watch(request))
            .doFinally(signal -> drainGate.leave());
    });
}
~~~

doFinally được gọi khi interaction complete, error hoặc cancel. Mỗi lần tryEnter thành công phải có đúng một lần leave. Nếu một handler tạo nhiều publisher lồng nhau, hãy đặt counter ở ranh giới interaction, không tăng/giảm counter cho từng item.

Trong ứng dụng lớn, nên bọc logic này thành interceptor hoặc một lớp điều phối chung để tránh quên gate ở một route.

## 6. Từ chối interaction mới một cách rõ ràng

Khi instance đang drain, client cần nhận được tín hiệu rằng interaction mới chưa được nhận xử lý. Có thể dùng lỗi ứng dụng có mã ổn định như SERVICE_DRAINING, kèm retry hint hoặc endpoint/service discovery mới.

Nếu protocol implementation hỗ trợ semantics từ chối request mà bảo đảm responder chưa xử lý request, có thể ánh xạ phù hợp với error code REJECTED. Cần xác minh cách Spring/RSocket version đang dùng biểu diễn error này; một exception thông thường có thể được chuyển thành APPLICATION_ERROR thay vì protocol REJECTED.

Không dùng một thông báo lỗi chung khiến client nghĩ rằng server đã commit command. Quy ước cần phân biệt:

- Chưa nhận request: client có thể chọn instance khác.
- Đã nhận và đang xử lý: kết quả có thể chưa xác định nếu connection mất.
- Đã commit nhưng response mất: client cần idempotency key hoặc truy vấn trạng thái.

Với request-response command có side effect, giữ nguyên request ID/idempotency key khi retry qua instance khác.

## 7. Xử lý từng interaction model

Mỗi interaction có lifecycle và policy drain khác nhau.

| Interaction | Điều cần chờ | Policy khi hết deadline |
|---|---|---|
| Request-response | Handler hoàn tất và response được phát | Nếu chưa commit, hủy an toàn; nếu kết quả chưa rõ, client tra cứu/retry idempotent |
| Fire-and-forget | Công việc server-side đã được nhận và xử lý xong | Dựa vào application work tracker/outbox; client không có protocol response xác nhận |
| Request-stream | Stream complete hoặc được checkpoint | Hoàn tất tự nhiên, hoặc cancel và client resume/reopen từ cursor |
| Request-channel | Input/output interaction kết thúc | Hoàn tất channel, checkpoint rồi reconnect, hoặc cancel cả interaction |

### Request-response

Request-response thường ngắn. Khi gate đóng, không nhận request mới nhưng cho request đang chạy hoàn tất. Theo dõi thời gian xử lý và số request in-flight.

Nếu deadline hết, hủy publisher có thể không rollback được side effect đã thực hiện. Với thao tác ghi dữ liệu, dùng transaction và idempotency.

### Fire-and-forget

Fire-and-forget không trả response payload để xác nhận xử lý xong. Server vẫn có thể chạy handler bất đồng bộ sau khi nhận request. Vì vậy, không thể chỉ dựa vào số request đã gửi từ client để biết công việc đã hoàn tất.

Nếu FNF dùng cho command quan trọng:

- Ghi nhận công việc vào durable queue/outbox trước khi xác nhận nội bộ.
- Theo dõi số handler đang chạy.
- Đảm bảo shutdown chờ công việc trong ngân sách.
- Client dùng event/ack nghiệp vụ hoặc truy vấn trạng thái nếu cần xác nhận.

Nếu FNF chỉ dùng cho telemetry có thể mất, policy drain có thể cho phép drop sau deadline.

### Request-stream

Stream có thể kéo dài lâu hơn drain window. Cần quyết định stream nào được phép hoàn tất, stream nào cần checkpoint/cursor và stream nào có thể cancel.

Một subscription giá realtime có thể kết thúc nhanh bằng cách gửi terminal signal sau khi producer ngừng phát. Một stream lịch sử lớn có thể cần cursor để client mở lại từ item cuối cùng đã xử lý.

Không chuyển một stream đang chạy sang server khác bằng cách đổi connection. Interaction đã gắn với responder hiện tại; muốn tiếp tục cần RSocket RESUME còn hiệu lực hoặc mở stream mới ở tầng ứng dụng.

### Request-channel

Request-channel có hai luồng dữ liệu hai chiều trong một interaction. Drain cần xử lý cả inbound và outbound:

- Ngừng nhận channel mới.
- Quyết định có tiếp tục đọc input của channel hiện tại không.
- Hoàn tất output khi đủ điều kiện.
- Ghi checkpoint cho message đã xử lý.
- Cancel channel khi deadline hết.

Nếu chỉ đóng output mà không xử lý input completion/cancel, resource phía client hoặc server có thể còn giữ.

## 8. Xử lý stream dài hạn

Stream dài hạn là thách thức lớn nhất của graceful shutdown. Nếu server chờ mọi stream complete tự nhiên, drain có thể không bao giờ kết thúc.

Các chiến lược phổ biến:

| Chiến lược | Cách làm | Phù hợp |
|---|---|---|
| Natural completion | Ngừng phát dữ liệu mới, hoàn tất stream | Stream hữu hạn |
| Bounded drain | Chờ tối đa một khoảng thời gian | Stream có thể tự hoàn tất |
| Checkpoint and resume | Lưu cursor rồi mở lại sau reconnect | Event stream dài |
| Application re-subscribe | Client tạo stream mới từ sequence đã nhận | Subscription realtime |
| Cancel at deadline | Hủy stream còn lại | Stream có thể khôi phục |
| Persist and replay | Ghi event vào broker/store | Không được mất dữ liệu |

Với event stream, nên dùng sequence hoặc offset bền vững. Client lưu vị trí đã xử lý thành công và gửi cursor khi mở lại. Đừng chỉ lưu item cuối đã nhận nếu client có thể nhận item nhưng chưa commit xử lý.

Ví dụ payload subscription:

~~~json
{
  "topic": "prices",
  "partition": "A",
  "afterSequence": 18420
}
~~~

Server mới bắt đầu phát từ sequence sau vị trí đã xử lý. Cần xác định semantics inclusive/exclusive và xử lý duplicate.

## 9. Graceful completion và cancel

Complete và cancel khác nhau:

- Complete: publisher kết thúc tự nhiên; downstream nhận tín hiệu hoàn tất.
- Error: publisher kết thúc do lỗi.
- Cancel: subscriber không còn muốn nhận dữ liệu; upstream cần dừng và cleanup.

Trong drain, ưu tiên complete nếu nghiệp vụ có thể kết thúc tự nhiên. Dùng cancel khi client rời đi, deadline hết hoặc công việc không còn cần thiết.

Ví dụ server ngừng nguồn event rồi complete stream:

~~~java
Sinks.Many<PriceTick> priceEvents =
    Sinks.many().multicast().onBackpressureBuffer(512);

Flux<PriceTick> watchPrices() {
    return priceEvents.asFlux();
}

void stopPriceProducer() {
    priceEvents.tryEmitComplete();
}
~~~

tryEmitComplete chỉ kết thúc sink; mọi publisher/subscriber phía trên cần xử lý terminal signal và cleanup. Nếu sink dùng chung cho nhiều consumer, cần xác định việc complete là hành động cấp service hay chỉ của một partition.

Không gọi complete cho một nguồn dùng chung quá sớm nếu request đang xử lý cần tiếp tục đọc từ nó.

## 10. Theo dõi active interaction

Drain coordinator cần biết còn bao nhiêu interaction và chúng đã chạy bao lâu.

Metric gợi ý:

| Metric | Ý nghĩa |
|---|---|
| rsocket.drain.state | Trạng thái ready/draining/stopped |
| rsocket.interactions.active | Số interaction đang chạy |
| rsocket.interactions.started | Tổng interaction đã nhận |
| rsocket.interactions.completed | Interaction hoàn tất |
| rsocket.interactions.cancelled | Interaction bị cancel |
| rsocket.interactions.rejected | Interaction bị gate từ chối |
| rsocket.interactions.duration | Thời gian interaction |
| rsocket.drain.duration | Tổng thời gian drain |
| rsocket.drain.remaining | Số interaction còn lại |
| rsocket.drain.forced | Số interaction bị đóng cưỡng bức |
| rsocket.connection.active | Connection đang mở |
| rsocket.connection.closed | Connection đã đóng trong drain |

Tag nên giới hạn ở service, route template, interaction type, transport và outcome. Không đưa stream ID hoặc request ID duy nhất vào metric label.

Log mỗi lần chuyển trạng thái:

~~~json
{
  "event": "rsocket.drain.started",
  "service": "inventory-service",
  "instance": "inventory-7",
  "activeInteractions": 42,
  "activeConnections": 8,
  "deadlineSeconds": 30
}
~~~

Log khi kết thúc:

~~~json
{
  "event": "rsocket.drain.completed",
  "service": "inventory-service",
  "durationMs": 18420,
  "completedInteractions": 39,
  "cancelledInteractions": 3,
  "remainingInteractions": 0
}
~~~

Đây là log mẫu. Các trường cần lấy từ counter thực tế; không suy ra số interaction complete chỉ từ số connection đóng.

## 11. Drain coordinator với deadline

Một coordinator điều phối các bước drain và deadline. Ví dụ dưới đây dùng abstraction cho transport vì API đóng listener/connection khác nhau giữa RSocket TCP, WebSocket và cách Spring Boot khởi tạo server.

~~~java
public interface RSocketTransportLifecycle {

    Mono<Void> stopAcceptingNewConnections();

    Mono<Void> signalConnectionClose();

    Mono<Void> closeRemainingConnections();

    Mono<Void> disposeServer();
}
~~~

Các method trên là contract của adapter trong ứng dụng, không phải tên API chuẩn có sẵn của mọi RSocket library.

Coordinator:

~~~java
public class RSocketDrainCoordinator {

    private final DrainGate gate;
    private final RSocketTransportLifecycle transport;
    private final Duration propagationDelay;
    private final Duration drainTimeout;

    public Mono<Void> drain() {
        return markNotReady()
            .then(Mono.fromRunnable(gate::stopAccepting))
            .then(Mono.delay(propagationDelay))
            .then(transport.stopAcceptingNewConnections())
            .then(transport.signalConnectionClose())
            .then(
                gate.awaitDrained()
                    .timeout(drainTimeout)
                    .onErrorResume(TimeoutException.class, error ->
                        cancelRemainingInteractions()
                    )
            )
            .then(transport.closeRemainingConnections())
            .then(transport.disposeServer());
    }

    private Mono<Void> markNotReady() {
        return Mono.fromRunnable(() -> readiness.setRefusingTraffic());
    }

    private Mono<Void> cancelRemainingInteractions() {
        return interactionRegistry.cancelAll();
    }
}
~~~

Đây là skeleton để thể hiện thứ tự. Trong triển khai thực tế:

- stopAcceptingNewConnections cần giữ connection hiện hữu nếu transport hỗ trợ tách listener khỏi accepted channels.
- signalConnectionClose chỉ thực hiện nếu protocol implementation có API phù hợp.
- cancelRemainingInteractions cần cancel đúng subscription và giải phóng tài nguyên.
- interactionRegistry phải đồng bộ với DrainGate để không bỏ sót interaction mới.
- readiness và interactionRegistry là dependency của ứng dụng, không phải biến global.
- Mỗi bước cần timeout và log riêng để một thao tác hạ tầng bị treo không khóa toàn bộ shutdown.

Đừng gọi block trên event-loop. Lifecycle thread có thể chờ có giới hạn nếu framework yêu cầu, hoặc dùng callback bất đồng bộ để báo hoàn tất.

## 12. Spring Boot và lifecycle của RSocket server

Spring Boot có hỗ trợ graceful shutdown cho embedded web server. Tuy nhiên, không nên mặc định rằng cấu hình graceful shutdown HTTP tự động drain mọi RSocket TCP session và mọi stream lâu dài.

Cấu hình web server thường dùng:

~~~yaml
server:
  shutdown: graceful

spring:
  lifecycle:
    timeout-per-shutdown-phase: 45s
~~~

Cấu hình này giúp Spring quản lý graceful shutdown của embedded web server theo khả năng của server implementation. Nếu RSocket được phục vụ qua WebSocket trên cùng web server, việc đóng HTTP server có thể tác động tới WebSocket connection; cần kiểm thử behavior của phiên bản và transport cụ thể.

Với RSocket TCP server hoặc session/stream cần policy riêng, triển khai một lifecycle component để:

1. Chuyển readiness sang false.
2. Đóng admission gate.
3. Chờ active interaction.
4. Hủy interaction quá deadline.
5. Đóng RSocket transport.
6. Báo lifecycle hoàn tất.

Có thể tích hợp qua SmartLifecycle hoặc một lifecycle manager phù hợp. Ví dụ khung:

~~~java
@Component
public class RSocketGracefulLifecycle implements SmartLifecycle {

    private final RSocketDrainCoordinator coordinator;
    private final AtomicBoolean running = new AtomicBoolean(true);
    private final AtomicBoolean callbackInvoked = new AtomicBoolean();
    private final AtomicReference<Mono<Void>> drainOperation =
        new AtomicReference<>();

    private Mono<Void> drainOnce() {
        Mono<Void> current = drainOperation.get();
        if (current != null) {
            return current;
        }

        Mono<Void> candidate = coordinator.drain().cache();
        return drainOperation.compareAndSet(null, candidate)
            ? candidate
            : drainOperation.get();
    }

    @Override
    public void start() {
        running.set(true);
    }

    @Override
    public void stop(Runnable callback) {
        drainOnce()
            .doFinally(signal -> {
                running.set(false);
                if (callbackInvoked.compareAndSet(false, true)) {
                    callback.run();
                }
            })
            .subscribe(
                ignored -> {},
                error -> log.error("RSocket drain failed", error)
            );
    }

    @Override
    public void stop() {
        drainOnce()
            .doFinally(signal -> running.set(false))
            .subscribe();
    }

    @Override
    public boolean isRunning() {
        return running.get();
    }

    @Override
    public boolean isAutoStartup() {
        return true;
    }

    @Override
    public int getPhase() {
        return Integer.MAX_VALUE;
    }
}
~~~

Đây là skeleton minh họa. Cần chọn phase để lifecycle dừng theo đúng thứ tự dependency: RSocket server nên drain khi các dependency mà handler cần vẫn còn hoạt động. SmartLifecycle phase cao thường start sau và stop trước, vì vậy cần cân nhắc thứ tự thực tế của ứng dụng.

Trong code production, cần bảo đảm stop() và stop(Runnable) không vô tình chạy drain hai lần. Nên gom vào một Mono dùng chung hoặc một state machine idempotent, có timeout tổng và xử lý lỗi trước khi gọi callback.

## 13. Kubernetes và container termination

Trong Kubernetes, Pod termination có nhiều bước:

- Pod chuyển sang trạng thái terminating.
- EndpointSlice và các thành phần mạng cập nhật endpoint.
- preStop hook được chạy nếu cấu hình.
- Container nhận SIGTERM.
- Process có thời gian tới terminationGracePeriodSeconds.
- Sau thời hạn, runtime có thể gửi SIGKILL.

preStop và thời gian ứng dụng xử lý SIGTERM cùng tiêu thụ ngân sách terminationGracePeriodSeconds. Cần đặt tổng thời gian phù hợp.

Ví dụ cấu hình minh họa:

~~~yaml
spec:
  terminationGracePeriodSeconds: 60
  containers:
    - name: rsocket-service
      lifecycle:
        preStop:
          httpGet:
            path: /internal/drain
            port: 8081
~~~

Endpoint /internal/drain là endpoint quản trị do ứng dụng tự triển khai; Kubernetes không tự tạo endpoint này. Nó nên đánh dấu readiness false và kích hoạt drain state. Nếu preStop chỉ sleep, thời gian propagation có thể được tạo nhưng ứng dụng chưa chắc đã ngừng nhận interaction qua connection hiện hữu.

Một ngân sách mẫu:

| Giai đoạn | Thời gian |
|---|---:|
| Endpoint propagation | 5 giây |
| Stop admission và drain | 35 giây |
| Force close và dispose | 10 giây |
| Safety margin | 10 giây |
| Tổng | 60 giây |

Đây chỉ là ví dụ. terminationGracePeriodSeconds phải lớn hơn tổng drain budget cộng margin. Nếu stream có thể chạy hàng giờ, không thể chờ tất cả stream hoàn tất trong thời gian pod termination; phải có checkpoint/re-subscribe hoặc policy cancel.

### Readiness probe

Readiness endpoint phải phản ánh trạng thái drain:

~~~java
@GetMapping("/internal/ready")
ResponseEntity<Void> readiness() {
    if (drainGate.isAccepting()) {
        return ResponseEntity.ok().build();
    }

    return ResponseEntity.status(503).build();
}
~~~

Ví dụ giả định readiness được gắn với admission state. Hệ thống thật có thể có readiness tổng hợp từ dependency và lifecycle state. Liveness không nên trả fail chỉ vì gate đang drain.

## 14. Load balancer và connection dài hạn

Load balancer thường chọn backend khi TCP connection hoặc WebSocket handshake được thiết lập. Sau đó connection hiện hữu tiếp tục gắn với backend đã chọn.

Khi instance bắt đầu drain:

- Ngừng nhận connection mới bằng discovery/LB.
- Thông báo hoặc đóng dần connection hiện tại.
- Chặn interaction mới trên connection cũ.
- Client reconnect tới một instance healthy khác.

Với WebSocket, HTTP upgrade đã hoàn tất nên proxy thường giữ tunnel tới backend cũ. Thay đổi readiness không tự di chuyển tunnel sang backend khác.

Với TCP, việc đóng listener không nhất thiết đóng accepted socket nếu transport cho phép tách riêng. Nhưng API server cụ thể có thể đóng cả listener lẫn connection. Phải xác minh behavior của transport adapter và test thực tế.

Nếu proxy có timeout hoặc connection draining feature, phối hợp timeout của proxy với drain window của ứng dụng. Không để proxy đóng connection trước khi server có cơ hội gửi tín hiệu hoặc hoàn tất interaction.

## 15. Client xử lý connection close và reconnect

Khi server báo đang đóng connection hoặc transport đóng, client cần:

1. Ngừng gửi interaction mới vào session cũ.
2. Đánh dấu connection không còn nhận workload.
3. Chờ hoặc xử lý kết quả của interaction đang chạy.
4. Kết nối tới một instance healthy khác.
5. Thử RSocket RESUME nếu đã bật và session state còn đủ.
6. Nếu resume thất bại, tạo session mới.
7. Khôi phục stream/channel ở cấp ứng dụng bằng cursor hoặc sequence.
8. Retry command với idempotency key ổn định.

RSocket có connection-level error code CONNECTION_CLOSE để biểu thị connection đang được đóng theo cách có kiểm soát; CONNECTION_ERROR biểu thị lỗi kết nối. Cần kiểm tra cách implementation phát và xử lý các tín hiệu này. Không giả định mọi dispose trong thư viện đều tự gửi đúng frame CONNECTION_CLOSE.

Client không nên reconnect vô hạn với delay cố định. Dùng exponential backoff có jitter và giới hạn attempt/deadline để tránh thundering herd khi nhiều instance cùng được deploy.

## 16. Resume không thay thế application recovery

RSocket RESUME có thể khôi phục một session khi hai phía giữ đủ resume state và frame buffer. Nó không bảo đảm một session có thể được resume sau khi process đã shutdown và xóa toàn bộ state.

Trong rolling deployment:

- Nếu session state không được chia sẻ hoặc lưu bền vững, client reconnect vào instance mới có thể nhận REJECTED_RESUME.
- Khi đó client cần tạo session mới.
- Request-stream cần cursor/offset để mở lại từ vị trí đã xử lý.
- Request-channel cần protocol ứng dụng để khôi phục hai chiều.
- Request-response command cần idempotency hoặc status query.

Không chờ resume thành công sau khi instance đã dispose session state. Nếu yêu cầu continuity cao, thiết kế state ngoài process và replay semantics từ đầu.

## 17. Deadline và policy cho interaction quá hạn

Drain cần deadline tổng và có thể có deadline riêng theo interaction.

| Interaction | Deadline gợi ý | Hành động khi quá hạn |
|---|---|---|
| Request-response ngắn | Vài giây tới vài chục giây | Hủy nếu an toàn; client xử lý kết quả chưa xác định |
| Fire-and-forget command | Theo thời gian xử lý nghiệp vụ | Hoàn tất durable work hoặc lưu outbox |
| Telemetry FNF | Ngắn | Có thể drop theo policy |
| Request-stream realtime | Vài giây tới drain window | Complete hoặc checkpoint/cancel |
| Request-stream lịch sử | Theo batch/cursor | Lưu checkpoint và mở lại |
| Request-channel | Theo protocol nghiệp vụ | Hoàn tất input/output hoặc checkpoint/cancel |

Các con số phải dựa trên latency và yêu cầu của hệ thống. Không đặt drain timeout dài hơn termination grace period của container.

Nếu interaction có thể chạy lâu hơn deadline, cần chủ động thiết kế checkpoint. Chỉ kéo dài timeout không giải quyết được rolling deployment khi số stream không bao giờ về 0.

## 18. Drain producer và Reactor Sinks

Nếu handler phát dữ liệu từ Reactor Sinks, drain cần dừng producer trước rồi cho subscriber nhận phần dữ liệu đã được chấp nhận.

Trình tự thường là:

1. Ngừng nhận command tạo event mới.
2. Dừng scheduler/job phát event.
3. Flush dữ liệu cần giữ vào durable store nếu có.
4. Complete sink nếu đây là nguồn chỉ thuộc instance đang drain.
5. Chờ subscriber nhận terminal signal hoặc hết deadline.
6. Dispose subscription và resource còn lại.

Ví dụ:

~~~java
public Mono<Void> stopProducer() {
    return Mono.fromRunnable(() -> {
        scheduledProducer.dispose();
        Sinks.EmitResult result = events.tryEmitComplete();

        if (result != Sinks.EmitResult.OK &&
            result != Sinks.EmitResult.FAIL_TERMINATED) {
            log.warn("Could not complete event sink: {}", result);
        }
    });
}
~~~

Nếu sink được chia sẻ giữa nhiều producer hoặc nhiều tenant, không complete sink toàn cục chỉ vì một instance dừng. Cần xác định ownership của publisher và chỉ dừng nguồn thuộc instance đó.

Đối với buffer, phải có giới hạn. Drain không nên cố flush một queue vô hạn khi consumer đã mất kết nối.

## 19. Trình tự shutdown cho nhiều dependency

Một RSocket handler có thể phụ thuộc database, broker, cache, scheduler và HTTP client. Nếu đóng dependency trước khi interaction kết thúc, drain sẽ làm request đang chạy thất bại.

Thứ tự khuyến nghị:

1. Ngừng nhận traffic mới và đóng admission gate.
2. Dừng producer/job có thể tạo interaction hoặc event mới.
3. Flush/commit durable work và complete nguồn dữ liệu thuộc instance đang drain.
4. Chờ active interaction sử dụng dependency hoàn tất hoặc tới deadline.
5. Đóng RSocket transport.
6. Đóng outbound client, database pool và broker client.
7. Dừng scheduler, executor và event loop còn lại do ứng dụng sở hữu.
8. Hoàn tất Spring context shutdown.

Thứ tự cụ thể phụ thuộc dependency graph. Ví dụ nếu scheduler phát event cho stream, phải dừng scheduler trước khi complete stream; nhưng database cần còn mở cho đến khi handler cuối cùng hoàn tất.

## 20. Kiểm thử graceful shutdown

Cần kiểm thử cả hành vi bình thường và khi drain không thể hoàn tất.

| Kịch bản | Điều cần xác nhận |
|---|---|
| Không có interaction | Instance dừng nhanh |
| Request-response đang chạy | Request hoàn tất trước khi transport đóng |
| FNF command đang chạy | Server theo dõi công việc và xử lý theo policy |
| Stream hữu hạn | Stream complete tự nhiên |
| Stream vô hạn | Checkpoint/cancel trước deadline |
| Request-channel đang chạy | Cả hai chiều kết thúc có kiểm soát |
| Connection cũ mở request mới | Admission gate từ chối |
| Client kết nối mới trong drain | Load balancer không chọn instance |
| Deadline hết | Interaction còn lại bị cancel/force close |
| Client reconnect | Chọn instance healthy và dùng jitter |
| RESUME thành công | Session tiếp tục nếu state còn đủ |
| RESUME bị từ chối | Application recovery không mất/lặp nghiệp vụ |
| WebSocket browser | Tunnel đóng và browser reconnect |
| SIGTERM từ Kubernetes | Process thoát trước termination grace period |
| Liveness trong drain | Không bị restart sớm |
| Dependency shutdown | DB/broker còn sống tới khi handler cuối hoàn tất |

### Test admission gate

- Mở một interaction và giữ nó chạy.
- Gọi stopAccepting.
- Thử mở interaction mới qua cùng connection.
- Xác nhận interaction mới bị từ chối.
- Cho interaction cũ complete.
- Xác nhận active count về 0 và drain signal hoàn tất.

### Test deadline

- Mở một stream không complete.
- Bắt đầu drain với deadline ngắn.
- Xác nhận stream được cancel khi deadline hết.
- Xác nhận counter giảm đúng một lần.
- Xác nhận listener/buffer/subscription được cleanup.
- Xác nhận transport dispose và process lifecycle callback hoàn tất.

## 21. Các lỗi thường gặp

| Lỗi | Hậu quả | Cách khắc phục |
|---|---|---|
| Chỉ đặt readiness=false | Connection cũ vẫn gửi interaction mới | Admission gate hoặc connection drain |
| Đóng listener ngay | Có thể đóng cả connection đang hoạt động tùy transport | Xác minh API và tách listener/accepted channel |
| Chờ mọi stream vô hạn | Shutdown không kết thúc | Deadline và checkpoint/cancel |
| Dừng database trước RSocket | Request đang chạy lỗi | Drain handler trước dependency |
| Liveness fail ngay khi drain | Orchestrator kill process sớm | Giữ liveness healthy trong drain |
| Retry cùng lúc | Reconnect storm | Exponential backoff + jitter |
| Giả định dispose gửi CONNECTION_CLOSE | Client không nhận tín hiệu dự kiến | Kiểm tra protocol behavior của implementation |
| Dựa vào RESUME sau khi process mất state | Resume bị từ chối | Application recovery |
| Không đếm FNF work | Command có thể bị bỏ dở | Durable queue/work tracker |
| Counter tăng/giảm sai | Drain kết thúc quá sớm hoặc treo | Một enter/leave cho mỗi interaction |
| Complete sink dùng chung | Làm gián đoạn instance khác | Quản lý ownership của producer/sink |
| Gọi block trên event loop | Treo I/O và làm timeout hàng loạt | Lifecycle thread/callback bất đồng bộ |

## 22. Runbook khi cần dừng một RSocket instance

1. Xác nhận instance thay thế đang healthy và capacity còn đủ.
2. Kích hoạt drain state, readiness=false và đóng admission gate.
3. Xác nhận endpoint đã rút khỏi discovery/load balancer.
4. Ngừng accept connection mới sau propagation window, giữ accepted connection trong drain window.
5. Theo dõi active interaction theo route và interaction type.
6. Dừng producer/scheduler thuộc instance.
7. Chờ request-response và stream hữu hạn hoàn tất.
8. Theo dõi stream dài và checkpoint khi cần.
9. Khi hết deadline, cancel interaction còn lại theo policy.
10. Gửi connection-close signal nếu transport/protocol implementation hỗ trợ.
11. Đóng connection và dispose RSocket server.
12. Đóng dependency theo thứ tự lifecycle.
13. Xác nhận process thoát trước termination grace period.
14. Kiểm tra client reconnect, resume hoặc application recovery.
15. Kiểm tra metric drain, lỗi và resource cleanup sau shutdown.

Nếu drain không tiến triển, kiểm tra route nào còn active, stream nào không có deadline, publisher nào không complete và task nào đang block event loop. Không tăng termination grace period vô hạn để che giấu một stream leak.

## Ghi nhớ

- RSocket connection dài hạn có thể tiếp tục mở interaction sau khi instance đã rút khỏi load balancer.
- Readiness=false chỉ ngăn traffic mới theo cơ chế discovery/LB; cần admission gate cho connection hiện hữu.
- Theo dõi active interaction, không chỉ active connection.
- Request-response, FNF, stream và channel cần policy drain khác nhau.
- FNF không có response protocol xác nhận xử lý xong; command quan trọng cần durable work tracking.
- Stream dài hạn cần natural completion, cursor/checkpoint hoặc cancel theo deadline.
- CONNECTION_CLOSE và CONNECTION_ERROR có ý nghĩa khác nhau; kiểm tra behavior của implementation.
- RSocket RESUME không thay thế application recovery khi process mất session state.
- Giữ liveness healthy trong thời gian drain; chỉ readiness chuyển false.
- Drain phải kết thúc trước terminationGracePeriodSeconds, có safety margin.
- Dừng RSocket interaction trước khi đóng dependency mà handler đang sử dụng.
- Client reconnect cần backoff/jitter và idempotency/cursor để tránh mất hoặc lặp dữ liệu.

## Tài liệu tham khảo

- [RSocket Protocol — Connection and Error Semantics](https://rsocket.io/about/protocol/)
- [RSocket Protocol Specification](https://github.com/rsocket/rsocket/blob/master/Protocol.md)
- [Spring Boot — Graceful Shutdown](https://docs.spring.io/spring-boot/reference/web/graceful-shutdown.html)
- [Spring Framework — SmartLifecycle](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/context/SmartLifecycle.html)
- [Spring Framework — RSocket](https://docs.spring.io/spring-framework/reference/rsocket.html)
- [Kubernetes — Pod Lifecycle](https://kubernetes.io/docs/concepts/workloads/pods/pod-lifecycle/)
- [Kubernetes — Configure Liveness, Readiness and Startup Probes](https://kubernetes.io/docs/tasks/configure-pod-container/configure-liveness-readiness-startup-probes/)
- [Project Reactor — Sinks](https://projectreactor.io/docs/core/release/reference/coreFeatures/sinks.html)

