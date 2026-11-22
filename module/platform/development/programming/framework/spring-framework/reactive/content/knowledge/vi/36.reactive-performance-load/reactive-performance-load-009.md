# Đóng kết nối đang hoạt động và dừng ứng dụng có kiểm soát trong Spring WebFlux

## 1. Mục tiêu

Một ứng dụng Spring WebFlux có thể đang xử lý HTTP request, SSE, WebSocket, message consumer, tác vụ nền và lời gọi WebClient khi process nhận tín hiệu dừng. Nếu JVM kết thúc ngay, request đang chạy có thể bị cắt, message chưa được xác nhận có thể bị xử lý lại, WebSocket client mất kết nối bất ngờ và connection pool không được giải phóng đúng thứ tự.

**Graceful shutdown** là quy trình ngừng nhận công việc mới, cho công việc đang chạy một khoảng thời gian để hoàn tất, đóng các kết nối dài hạn theo giao thức, dừng worker và giải phóng tài nguyên trước khi process kết thúc.

Bài học này bao gồm:

1. Graceful shutdown mặc định của Spring Boot 3.5 với WebFlux/Reactor Netty.
2. Readiness, HTTP request đang xử lý và shutdown timeout.
3. Kết thúc SSE và đóng WebSocket session.
4. Dừng background worker, message consumer, Scheduler và connection pool.
5. Điều phối thứ tự bằng SmartLifecycle và callback bất đồng bộ.
6. Tính termination budget cho Kubernetes/container.
7. Kiểm thử cancellation, cleanup và SIGTERM.

## 2. Ba cấp độ lifecycle

| Cấp độ | Đối tượng | Việc cần làm |
| --- | --- | --- |
| Request | HTTP request/reactive operation | Cho operation đang chạy hoàn tất hoặc timeout có kiểm soát |
| Connection | SSE, WebSocket, client/database connection | Gửi tín hiệu kết thúc, đóng giao thức, release resource |
| Application | ApplicationContext, worker, scheduler, pool, server | Ngừng nhận việc mới, dừng theo thứ tự và chờ callback |

HTTP response hoàn tất không có nghĩa ứng dụng đã shutdown. Ngược lại, đóng TCP socket không chứng minh business transaction đã commit hoặc message đã được acknowledge.

Một Flux không kết thúc tự nhiên không thể được chờ vô hạn. Nó cần chính sách riêng: SSE event cuối, WebSocket Close frame, hủy broker subscription hoặc forced close khi hết deadline.

## 3. Spring Boot 3.5 graceful shutdown

Spring Boot hỗ trợ graceful shutdown mặc định với embedded Reactor Netty, Tomcat, Jetty và Undertow, cho cả ứng dụng reactive và servlet. Khi ApplicationContext đóng, server ngừng nhận request mới và cho request đang chạy một grace period để hoàn tất.

Cấu hình tường minh:

~~~properties
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=20s
~~~

Trong Boot 3.5, graceful shutdown đã bật mặc định cho embedded web server; khai báo tường minh giúp người đọc hiểu chủ đích. `spring.lifecycle.timeout-per-shutdown-phase` là timeout cho **mỗi phase của Spring Lifecycle**, không phải tổng thời gian của toàn process.

Với Reactor Netty, server ngừng nhận request mới ở tầng network. Request đã được chấp nhận có thể tiếp tục xử lý trong thời gian chờ. Cách từ chối request có thể khác nhau theo web server và persistent connection; không giả định mọi trường hợp luôn trả cùng HTTP status.

### 3.1. Luồng shutdown

~~~text
Orchestrator gửi SIGTERM
          |
          v
Spring ApplicationContext bắt đầu close
          |
          v
Readiness -> REFUSING_TRAFFIC
          |
          v
Application drain
  - từ chối công việc mới
  - kết thúc SSE
  - đóng WebSocket
  - dừng worker/consumer
          |
          v
Embedded server ngừng nhận request mới
          |
          v
Chờ in-flight HTTP trong grace period
          |
          v
Giải phóng custom pool / scheduler / resource
          |
          v
Destroy bean, đóng context, process kết thúc
~~~

Đây là trình tự mục tiêu. Thứ tự thực tế được điều khiển bởi phase của SmartLifecycle và cấu hình Spring Boot.

### 3.2. SIGTERM và SIGKILL

- SIGTERM yêu cầu process dừng; Spring có cơ hội đóng ApplicationContext và chạy lifecycle callback.
- SIGKILL kết thúc process ngay, không cho Java chạy cleanup callback.
- IDE hoặc process manager có thể không gửi SIGTERM đúng cách.
- Shutdown hook không bảo đảm hoàn tất nếu container hết termination deadline hoặc máy bị tắt đột ngột.

Hãy thử quy trình shutdown bằng đúng cơ chế mà production sử dụng.

## 4. Readiness: ngừng nhận traffic trước khi đóng tài nguyên

Readiness trả lời instance có sẵn sàng nhận traffic hay không. Khi shutdown bắt đầu, Spring Boot chuyển trạng thái sang `REFUSING_TRAFFIC` để hạ tầng ngừng route request mới tới instance.

Hai trạng thái:

| ReadinessState | Ý nghĩa |
| --- | --- |
| `ACCEPTING_TRAFFIC` | Instance sẵn sàng nhận traffic |
| `REFUSING_TRAFFIC` | Instance không muốn nhận traffic mới |

Spring Boot phát AvailabilityChangeEvent khi trạng thái thay đổi. Có thể cập nhật readiness chủ động:

~~~java
AvailabilityChangeEvent.publish(
    eventPublisher,
    this,
    ReadinessState.REFUSING_TRAFFIC
);
~~~

Với Kubernetes, readiness giúp Service/EndpointSlice loại Pod đang dừng khỏi traffic. Việc cập nhật endpoint/load balancer cần thời gian lan truyền; nếu cần, thiết kế preStop hook hoặc cơ chế quản trị phù hợp.

Không dùng liveness để báo instance đang drain. Liveness trả lời process có cần restart vì không còn khỏe hay không; readiness trả lời instance có nhận traffic mới hay không.

### 4.1. Health probe

~~~properties
management.endpoint.health.probes.enabled=true
management.endpoints.web.exposure.include=health,info
~~~

Các endpoint thường dùng:

~~~text
/actuator/health/liveness
/actuator/health/readiness
~~~

Trong giai đoạn shutdown, readiness có thể chuyển sang REFUSING_TRAFFIC và connector cũng đang dừng nhận request. Không dựa vào việc gọi probe liên tục sau khi HTTP connector đã đóng để biết process đã kết thúc chưa. Orchestrator cần quan sát trạng thái container/process.

Bảo vệ Actuator endpoint bằng network policy và security; chỉ expose endpoint cần thiết.

## 5. In-flight HTTP request và grace period

Với request hữu hạn, Spring Boot cho phép request đã được chấp nhận hoàn tất trong grace period. Ví dụ:

~~~java
@GetMapping("/work")
public Mono<String> work() {
    return Mono.delay(Duration.ofSeconds(5))
        .map(ignored -> "completed");
}
~~~

Nếu request bắt đầu trước khi server dừng nhận traffic và operation hoàn tất trong grace period, client có thể nhận response bình thường.

Nếu request kéo dài hơn grace period, server/process có thể kết thúc trước khi response hoàn tất. Không có cấu hình nào bảo đảm mọi request vô hạn đều được giữ sống.

Nguyên tắc:

- Giữ request processing hữu hạn và có timeout.
- Đặt timeout downstream nhỏ hơn request/shutdown budget.
- Không giữ database transaction trong stream vô hạn.
- Công việc cần tiếp tục sau khi HTTP client rời đi nên chuyển thành job/message workflow có trạng thái bền vững.
- Dùng idempotency key nếu client retry khi không rõ request đã commit hay chưa.
- Không trả 200 trước khi business operation đạt trạng thái mà API đã cam kết.

## 6. SSE: chủ động kết thúc stream đang mở

SSE trả `text/event-stream` và giữ HTTP response mở. Publisher như `Flux.interval(Duration.ofSeconds(1))` không tự complete. Chỉ bật graceful shutdown có thể khiến server phải chờ tới hết grace period.

Một chiến lược rõ ràng là phát event cuối tên `shutdown` rồi complete. Client nhận event này có thể đóng EventSource hoặc reconnect sang instance khác theo chính sách ứng dụng.

Wire format minh họa:

~~~text
event:shutdown
data:server-restarting

~~~

### 6.1. SseFeed dùng Sinks.One

~~~java
@Component
public class SseFeed {
    private final Sinks.One<Boolean> shutdownSignal = Sinks.one();

    public Flux<ServerSentEvent<String>> events() {
        Flux<ServerSentEvent<String>> ticks =
            Flux.interval(Duration.ofSeconds(1))
                .map(sequence ->
                    ServerSentEvent.<String>builder("tick-" + sequence)
                        .id(Long.toString(sequence))
                        .event("tick")
                        .build()
                );

        Mono<ServerSentEvent<String>> shutdownEvent =
            shutdownSignal.asMono()
                .map(ignored ->
                    ServerSentEvent.<String>builder("server-restarting")
                        .event("shutdown")
                        .build()
                );

        return Flux.merge(ticks, shutdownEvent)
            .takeUntil(event -> "shutdown".equals(event.event()));
    }

    public void beginShutdown() {
        shutdownSignal.tryEmitValue(Boolean.TRUE);
    }
}
~~~

`Sinks.One` giữ một tín hiệu shutdown cho subscriber hiện tại và subscriber đến sau. Khi tín hiệu được phát, Flux merge nhận event shutdown; `takeUntil` phát event cuối rồi complete stream, đồng thời cancel interval.

Client có thể đóng EventSource:

~~~javascript
const source = new EventSource("/api/stream");

source.addEventListener("tick", event => {
    console.log("tick:", event.data);
});

source.addEventListener("shutdown", event => {
    console.log("server restarting:", event.data);
    source.close();
});
~~~

Nếu muốn client tự reconnect, không gọi `source.close()`; hãy thiết kế backoff và resume semantics. Tránh để tất cả client reconnect đồng thời sau khi nhiều Pod restart.

### 6.2. Controller có drain gate

~~~java
@RestController
@RequestMapping("/api")
public class StreamController {
    private final SseFeed feed;
    private final DrainCoordinator drain;

    public StreamController(SseFeed feed, DrainCoordinator drain) {
        this.feed = feed;
        this.drain = drain;
    }

    @GetMapping(path = "/stream",
                produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public Flux<ServerSentEvent<String>> stream() {
        if (drain.isDraining()) {
            return Flux.error(new ResponseStatusException(
                HttpStatus.SERVICE_UNAVAILABLE,
                "instance is draining"
            ));
        }
        return feed.events();
    }
}
~~~

Drain gate chặn request SSE mới trong khoảng giữa lúc application bắt đầu drain và lúc server dừng nhận request ở tầng network. Với ứng dụng thực tế, có thể đặt WebFilter để áp dụng quy tắc cho route nghiệp vụ; cho phép readiness/management endpoint cần thiết tiếp tục trả trạng thái trong lúc connector còn hoạt động.

## 7. WebSocket: quản lý session đang hoạt động

WebSocket là kết nối hai chiều kéo dài. Server nên giữ registry session để:

1. Ngừng nhận session mới khi bắt đầu drain.
2. Gửi Close frame có status phù hợp.
3. Chờ close handshake trong giới hạn thời gian.
4. Hủy outbound publisher và release subscription/resource.
5. Cho client reconnect có backoff.

Spring WebFlux dùng WebSocketHandler và WebSocketSession. `session.receive()` là Flux inbound; `session.send(...)` ghi publisher outbound. Handler cần compose hai luồng thành một lifecycle thống nhất và trả Mono<Void> phản ánh khi xử lý session kết thúc.

### 7.1. Close status

| CloseStatus | Mã | Ý nghĩa |
| --- | ---: | --- |
| `NORMAL` | 1000 | Kết thúc bình thường |
| `GOING_AWAY` | 1001 | Endpoint đang rời đi, ví dụ server shutdown |
| `PROTOCOL_ERROR` | 1002 | Lỗi protocol |
| `POLICY_VIOLATION` | 1008 | Vi phạm policy |
| `SERVER_ERROR` | 1011 | Lỗi server không mong đợi |
| `SERVICE_RESTARTED` | 1012 | Server đang restart |
| `SERVICE_OVERLOAD` | 1013 | Service quá tải |

Ví dụ dùng `GOING_AWAY` (1001). Nếu client hiểu `SERVICE_RESTARTED`, có thể dùng 1012 và áp dụng reconnect delay có jitter. Không gửi reserved code như 1005 hoặc 1006 trong Close frame.

### 7.2. Registry thread-safe

~~~java
@Component
public class WebSocketSessionRegistry {
    private static final Logger log =
        LoggerFactory.getLogger(WebSocketSessionRegistry.class);

    private final ConcurrentMap<String, WebSocketSession> sessions =
        new ConcurrentHashMap<>();

    private final AtomicBoolean draining = new AtomicBoolean();

    public boolean register(WebSocketSession session) {
        if (draining.get()) {
            return false;
        }

        sessions.put(session.getId(), session);

        // Kiểm tra lần hai để xử lý race với lúc bắt đầu drain.
        if (draining.get()) {
            sessions.remove(session.getId(), session);
            return false;
        }
        return true;
    }

    public void remove(String id) {
        sessions.remove(id);
    }

    public int activeCount() {
        return sessions.size();
    }

    public Mono<Void> closeAll() {
        draining.set(true);

        return Flux.fromIterable(sessions.values())
            .flatMap(session ->
                session.close(CloseStatus.GOING_AWAY)
                    .doOnError(error ->
                        log.warn("Cannot close session {}",
                            session.getId(), error)
                    )
                    .onErrorResume(error -> Mono.empty()),
                32
            )
            .then();
    }

    public boolean isDraining() {
        return draining.get();
    }
}
~~~

ConcurrentHashMap hỗ trợ truy cập từ nhiều thread/event loop. Cờ draining được bật trước khi duyệt session. Phép kiểm tra hai lần trong `register` xử lý trường hợp handshake đến đúng lúc shutdown bắt đầu.

`closeAll()` đóng tối đa 32 session đồng thời trong ví dụ. Điều chỉnh concurrency theo số lượng connection và năng lực server; tránh tạo task không giới hạn cho hàng trăm nghìn session.

### 7.3. WebSocketHandler

~~~java
@Component
public class ManagedWebSocketHandler implements WebSocketHandler {
    private static final Logger log =
        LoggerFactory.getLogger(ManagedWebSocketHandler.class);

    private final WebSocketSessionRegistry registry;

    public ManagedWebSocketHandler(WebSocketSessionRegistry registry) {
        this.registry = registry;
    }

    @Override
    public Mono<Void> handle(WebSocketSession session) {
        if (!registry.register(session)) {
            return session.close(CloseStatus.GOING_AWAY);
        }

        Mono<Void> inbound = session.receive()
            .doOnNext(message ->
                log.debug("Received message type={}", message.getType())
            )
            .then();

        Flux<WebSocketMessage> outgoing =
            Flux.interval(Duration.ofSeconds(5))
                .map(sequence ->
                    session.textMessage("heartbeat:" + sequence)
                );

        Mono<Void> outbound = session.send(outgoing);

        return Mono.firstWithSignal(inbound, outbound)
            .doFinally(signal -> registry.remove(session.getId()));
    }
}
~~~

`Mono.firstWithSignal` hoàn tất khi một trong hai luồng inbound/outbound kết thúc và hủy luồng còn lại. Khi client đóng connection, inbound complete và outbound heartbeat bị cancel. Khi registry đóng session, connection đóng, inbound kết thúc và handler remove session khỏi registry.

Đây là demo lifecycle; ứng dụng thật cần xác thực Principal, giới hạn số session/user, validate message, serialize outbound send và quản lý broker subscription.

### 7.4. Đăng ký endpoint

~~~java
@Configuration
public class WebSocketConfiguration {
    @Bean
    HandlerMapping webSocketMapping(ManagedWebSocketHandler handler) {
        SimpleUrlHandlerMapping mapping = new SimpleUrlHandlerMapping();
        mapping.setUrlMap(Map.of("/ws/live", handler));
        mapping.setOrder(-1);
        return mapping;
    }
}
~~~

Endpoint là `/ws/live`. Handler từ chối session mới khi registry đã draining.

## 8. SmartLifecycle để phối hợp drain

`@PreDestroy` phù hợp cleanup đồng bộ ngắn. Khi cần cleanup bất đồng bộ và chờ Mono kết thúc, `SmartLifecycle.stop(Runnable callback)` phù hợp hơn.

Contract quan trọng: gọi callback sau khi bean hoàn tất việc dừng. Spring LifecycleProcessor chờ callback trong giới hạn timeout của phase.

Spring Boot 3.x dành các phase cho graceful shutdown: web server stop ở `SmartLifecycle.DEFAULT_PHASE - 1024` và graceful wait ở `DEFAULT_PHASE - 2048`. Spring dừng phase có giá trị cao trước. Vì vậy ví dụ đặt drain coordinator ở `DEFAULT_PHASE - 512` để phát readiness/drain signal và đóng WebSocket trước khi server stop.

### 8.1. DrainCoordinator

~~~java
@Component
public class DrainCoordinator implements SmartLifecycle {
    private static final Logger log =
        LoggerFactory.getLogger(DrainCoordinator.class);

    private final ApplicationEventPublisher events;
    private final SseFeed sseFeed;
    private final WebSocketSessionRegistry sessions;

    private final AtomicBoolean running = new AtomicBoolean();
    private final AtomicBoolean draining = new AtomicBoolean();

    public DrainCoordinator(
            ApplicationEventPublisher events,
            SseFeed sseFeed,
            WebSocketSessionRegistry sessions) {
        this.events = events;
        this.sseFeed = sseFeed;
        this.sessions = sessions;
    }

    @Override
    public void start() {
        running.set(true);
    }

    @Override
    public void stop(Runnable callback) {
        if (!running.getAndSet(false)) {
            callback.run();
            return;
        }

        if (!draining.compareAndSet(false, true)) {
            callback.run();
            return;
        }

        AvailabilityChangeEvent.publish(
            events, this, ReadinessState.REFUSING_TRAFFIC
        );

        sseFeed.beginShutdown();

        sessions.closeAll()
            .timeout(Duration.ofSeconds(8))
            .doOnError(error ->
                log.warn("WebSocket drain timed out", error)
            )
            .onErrorResume(error -> Mono.empty())
            .doFinally(signal -> callback.run())
            .subscribe();
    }

    @Override
    public void stop() {
        stop(() -> {});
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
        return DEFAULT_PHASE - 512;
    }

    public boolean isDraining() {
        return draining.get();
    }
}
~~~

`stop(Runnable)` chạy cleanup reactive và chỉ gọi callback sau khi closeAll complete hoặc timeout. Lỗi từng session được log; một session lỗi không chặn việc đóng các session khác.

`getPhase()` trong ví dụ dựa trên phase arrangement của Spring Boot 3.x. Nếu ứng dụng có Spring Cloud Stream, custom worker hoặc lifecycle bean khác, cần phối hợp phase theo dependency và kiểm thử thứ tự khi nâng cấp Boot.

### 8.2. Vì sao không block trong stop callback?

Không viết:

~~~java
sessions.closeAll().block();
~~~

trên event-loop hoặc lifecycle thread mà không đánh giá tác động. Contract của SmartLifecycle cung cấp callback để báo hoàn tất bất đồng bộ. Subscribe publisher, xử lý lỗi và gọi callback đúng một lần.

Không gọi callback ngay sau `subscribe()`; nếu gọi sớm, Spring có thể destroy dependency trong khi session vẫn đang đóng.

## 9. Background worker và message consumer

Worker có hai nhóm công việc:

- Công việc đang xử lý: hoàn tất, commit/checkpoint hoặc đưa về retry an toàn.
- Công việc mới: ngừng nhận khi drain bắt đầu.

Quy trình nên là:

1. Đặt cờ không nhận thêm message/job.
2. Pause consumer hoặc cancel upstream subscription.
3. Chờ số công việc in-flight về 0.
4. Commit offset/ack sau khi xử lý thành công.
5. Khi hết timeout, để message chưa ack được broker redeliver hoặc lưu checkpoint.
6. Gọi SmartLifecycle callback khi worker dừng.

Contract ví dụ:

~~~java
public interface DrainableWorker {
    Mono<Void> stopAccepting();
    Mono<Void> awaitInFlight();
}
~~~

Một lifecycle bean có thể compose:

~~~java
worker.stopAccepting()
    .then(worker.awaitInFlight())
    .timeout(Duration.ofSeconds(10))
    .doOnError(error -> log.warn("Worker drain timed out", error))
    .onErrorResume(error -> Mono.empty())
    .doFinally(signal -> callback.run())
    .subscribe();
~~~

Đây là snippet cho worker đã có implementation. Không ack message chỉ vì shutdown bắt đầu. Ack/commit phải tuân thủ business semantics. Nếu chưa hoàn tất trong grace period, để message redeliver và consumer phải idempotent.

Không tạo Flux vô hạn bên trong database transaction để chờ worker drain. Transaction nên ngắn và hữu hạn.

## 10. Dừng Scheduler và tài nguyên reactive

Scheduler riêng nên được khai báo thành Spring bean và dispose khi shutdown:

~~~java
@Bean(destroyMethod = "dispose")
Scheduler workerScheduler() {
    return Schedulers.newBoundedElastic(
        8, 200, "worker-io"
    );
}
~~~

Cách này phù hợp với Scheduler có cleanup đồng bộ. Nếu Scheduler đại diện worker cần ngừng nhận task và chờ task đang chạy, hãy quản lý bằng SmartLifecycle với callback và timeout.

Đừng gọi `Schedulers.shutdownNow()` trên global Scheduler nếu ứng dụng hoặc thư viện khác còn sử dụng nó. Chỉ dispose tài nguyên do ứng dụng sở hữu.

Với publisher vô hạn:

- Gắn cancellation vào lifecycle.
- Dùng `doFinally` để giải phóng subscription.
- Không gọi `subscribe()` độc lập mà không giữ handle để cancel.
- Đảm bảo cancel feed sẽ hủy broker subscription tương ứng.
- Không giữ queue không giới hạn khi consumer dừng.

## 11. Đóng WebClient connection pool

WebClient do Spring Boot auto-configure và tạo từ `WebClient.Builder` có thể dùng chung Reactor Netty resources với server. Đây là chế độ được khuyến nghị; Spring quản lý resource lifecycle.

Nếu tự tạo `ConnectionProvider`, ứng dụng sở hữu resource đó và phải dispose đúng lúc.

~~~java
ConnectionProvider provider =
    ConnectionProvider.builder("downstream")
        .maxConnections(32)
        .pendingAcquireMaxCount(64)
        .pendingAcquireTimeout(Duration.ofSeconds(3))
        .disposeTimeout(Duration.ofSeconds(5))
        .build();

HttpClient httpClient = HttpClient.create(provider);

WebClient client = WebClient.builder()
    .clientConnector(
        new ReactorClientHttpConnector(httpClient)
    )
    .build();
~~~

`ConnectionProvider.dispose()` là fire-and-forget. Nếu cần quan sát quá trình kết thúc, dùng `disposeLater()`:

~~~java
provider.disposeLater()
    .doFinally(signal -> callback.run())
    .subscribe();
~~~

Gọi dispose sau khi in-flight HTTP request hoàn tất. Khi pool bắt đầu dispose, acquire mới bị từ chối; pending acquire có grace period theo `disposeTimeout`. Không đóng pool trước khi service còn cần nó để hoàn tất request.

Không tự gọi `HttpResources.disposeLoopsAndConnections()` nếu đang dùng global Reactor Netty resources chia sẻ giữa server và client. Disposing global resources có thể ảnh hưởng tất cả client dùng chúng.

## 12. R2DBC/JDBC và database connection

Với R2DBC, Spring Boot quản lý ConnectionFactory/pool theo lifecycle bean. Không đóng connection thủ công ở mỗi request; transaction/repository phải kết thúc publisher để connection được trả về pool.

Trình tự:

1. Ngừng nhận request/job mới.
2. Chờ transaction đang chạy hoàn tất trong grace period.
3. Rollback/cancel transaction còn sống khi deadline hết.
4. Để pool/ConnectionFactory dispose khi bean lifecycle kết thúc.

Nếu tự tạo R2DBC pool, phải sở hữu và dispose bean đó. Với JDBC DataSource/Hikari, đóng DataSource sau khi request đang dùng connection đã kết thúc. Không đóng database pool ở phase sớm hơn phase chờ in-flight request.

Một transaction chưa commit không thể được xem là thành công chỉ vì client đã gửi request. Nếu shutdown cắt response sau khi DB commit, client có thể không biết kết quả; API có side effect nên có idempotency key hoặc cách truy vấn trạng thái.

## 13. Thứ tự shutdown và SmartLifecycle phase

Spring start lifecycle bean theo phase tăng dần; stop theo phase giảm dần. Bean phase cao hơn dừng sớm hơn.

Trong Spring Boot 3.x, phase arrangement cho graceful shutdown tạo ra khoảng trống để ứng dụng tham gia:

| Phase tương đối | Ví dụ | Thời điểm stop |
| --- | --- | --- |
| `DEFAULT_PHASE - 512` | DrainCoordinator | Trước web server stop |
| `DEFAULT_PHASE - 1024` | Web server stop | Ngừng nhận request mới |
| `DEFAULT_PHASE - 2048` | Graceful wait | Chờ request đang chạy |
| `DEFAULT_PHASE - 3072` | Custom outbound pool cleanup | Sau grace period |

Các phase là ví dụ tích hợp với Boot 3.x; cần kiểm tra phase của lifecycle bean khác. Spring Cloud Stream hoặc consumer lifecycle có thể cần phase riêng để stop theo đúng thứ tự.

Nếu worker cần tiếp tục phục vụ request đang chạy, không dừng worker ở phase cao hơn web server một cách tùy tiện. Nếu worker chỉ tiêu thụ background message và cần dừng intake trước khi HTTP server đóng, hãy thiết kế phase riêng và test thứ tự.

`spring.lifecycle.timeout-per-shutdown-phase` áp dụng theo phase. Nhiều phase bất đồng bộ có thể tiêu tốn nhiều hơn một lần timeout. Tính tổng budget theo các phase thực tế có callback chờ.

## 14. Kubernetes và terminationGracePeriodSeconds

Kubernetes có thời gian chờ kết thúc Pod. Khi Pod bị terminate:

- preStop hook chạy trước tín hiệu TERM.
- Sau preStop, container runtime gửi SIGTERM.
- Spring Boot bắt đầu đóng ApplicationContext và chạy graceful shutdown.
- Khi hết `terminationGracePeriodSeconds`, kubelet có thể gửi SIGKILL.

Ví dụ cấu hình budget:

~~~yaml
spec:
  terminationGracePeriodSeconds: 60
  containers:
    - name: reactive-api
      image: example/reactive-api:1.0
      lifecycle:
        preStop:
          exec:
            command: ["/bin/sh", "-c", "sleep 5"]
~~~

Đây chỉ là ví dụ. `sleep 5` tiêu thụ 5 giây trong termination budget; chỉ dùng khi cần thời gian để endpoint/load balancer cập nhật. Trong production, có thể dùng preStop hook gọi drain endpoint được bảo vệ hoặc phối hợp service mesh/load balancer.

Phép tính budget:

~~~text
terminationGracePeriodSeconds
    >= preStop duration
     + app drain phase
     + web server graceful wait
     + custom resource cleanup
     + safety margin
~~~

Ví dụ preStop 5s, drain 8s, HTTP grace 20s, pool cleanup 5s và margin 10s cần khoảng 48s. Cấu hình 60s tạo headroom. Đây là ví dụ; đo shutdown thực tế của service.

Nếu dùng rolling update, cân nhắc readiness propagation, PodDisruptionBudget, maxUnavailable/maxSurge và thời gian startup của Pod mới.

## 15. Client reconnect

Khi server đóng WebSocket hoặc SSE trong lúc restart, client cần biết đây là kết nối bị đóng có chủ đích và reconnect theo backoff.

### 15.1. WebSocket

Client nên:

- Phân biệt close code 1001/1012 với lỗi protocol hoặc authentication.
- Reconnect bằng exponential backoff và jitter.
- Khôi phục subscription sau khi kết nối mới thành công.
- Gửi cursor/last seen event ID nếu protocol hỗ trợ.
- Dùng idempotency key cho command có side effect.
- Giới hạn số lần reconnect và hiển thị trạng thái offline.

Không để tất cả client reconnect ngay lập tức sau cùng một close frame; điều đó tạo connection storm lên instance còn lại.

### 15.2. SSE

EventSource có cơ chế reconnect và có thể gửi Last-Event-ID. Tuy nhiên server chỉ replay được event nếu có event log/store để truy vấn lại. Một Flux.interval phát id 0,1,2 theo từng subscription không tự tạo durable replay.

Nếu event shutdown báo server restarting, client có thể đợi jitter rồi mở lại stream. Nếu có resume contract, server phải kiểm tra Last-Event-ID và phát event tiếp theo theo semantics đã định nghĩa.

## 16. Timeout, deadline và forced shutdown

Graceful shutdown là best effort trong giới hạn thời gian. Không thể bảo đảm mọi operation hoàn tất khi dependency treo, client không đọc response hoặc network bị phân đoạn.

| Loại công việc | Chính sách |
| --- | --- |
| HTTP request | Chờ trong server grace period |
| SSE | Gửi shutdown event rồi complete |
| WebSocket | Close frame, chờ handshake có giới hạn |
| Background job | Dừng intake, finish hoặc checkpoint |
| Message consumer | Pause, xử lý/ack hoặc để redelivery |
| WebClient custom pool | Dispose sau khi in-flight request kết thúc |
| Scheduler | Dừng task intake, chờ task, dispose |
| DB pool | Dispose sau request/transaction drain |

Mỗi cleanup nên có timeout. Nếu cleanup thất bại, log nguyên nhân, tăng metric và tiếp tục shutdown theo policy. Không chờ vô hạn trong callback SmartLifecycle.

Phân biệt:

- Graceful close: hai bên trao đổi protocol close và cleanup.
- Timeout close: hết grace period, framework/server buộc kết thúc.
- Process kill: JVM không còn cơ hội cleanup.

## 17. Logging và metrics

Một quy trình shutdown tốt cần quan sát được:

| Metric/log | Ý nghĩa |
| --- | --- |
| `app.shutdown.started` | Thời điểm bắt đầu drain |
| `app.shutdown.duration` | Tổng thời gian shutdown |
| `app.shutdown.phase.duration` | Thời gian từng phase |
| `app.shutdown.timeout` | Số phase hết timeout |
| `app.shutdown.inflight.requests` | Request còn đang chạy |
| `app.websocket.active` | Số WebSocket session đang mở |
| `app.websocket.closed.shutdown` | Session đóng do shutdown |
| `app.sse.active` | Số SSE subscription |
| `app.worker.inflight` | Công việc nền đang xử lý |
| `app.worker.unacked` | Message chưa ack/checkpoint |
| `app.resource.dispose.errors` | Lỗi giải phóng resource |

Log nên có instance ID, deployment version, shutdown reason, phase, elapsed time, số request/session còn lại và error class. Không log token, cookie, message payload nhạy cảm.

Log minh họa:

~~~text
INFO shutdown.started instance=api-7 reason=SIGTERM
INFO shutdown.readiness state=REFUSING_TRAFFIC
INFO shutdown.websocket closing=12
INFO shutdown.sse event=shutdown active=8
INFO shutdown.http waiting_inflight=3
INFO shutdown.complete durationMs=6420
~~~

Các dòng trên là output minh họa, không phải log mặc định của Spring Boot. Hãy tạo log/metric trong ứng dụng.

## 18. Demo hoàn chỉnh: Spring Boot 3.5.6, Java 17+, WebFlux

Demo có:

- HTTP request hữu hạn đang chạy trong grace period.
- SSE stream phát event shutdown rồi complete.
- WebSocket handler đăng ký session đang hoạt động.
- DrainCoordinator cập nhật readiness, đóng WebSocket và dừng SSE.
- Spring Boot dừng server và chờ request đang xử lý.
- Unit test cho SSE và WebSocket registry.

### 18.1. Cấu trúc dự án

~~~text
webflux-graceful-shutdown/
  settings.gradle
  build.gradle
  src/main/java/demo/shutdown/
    ShutdownApplication.java
    SseFeed.java
    StreamController.java
    WebSocketSessionRegistry.java
    ManagedWebSocketHandler.java
    WebSocketConfiguration.java
    DrainCoordinator.java
    LongTaskController.java
  src/main/resources/
    application.properties
  src/test/java/demo/shutdown/
    SseFeedTest.java
    WebSocketSessionRegistryTest.java
~~~

### 18.2. settings.gradle

~~~groovy
rootProject.name = 'webflux-graceful-shutdown'
~~~

### 18.3. build.gradle

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.6'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'demo'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.projectreactor:reactor-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Spring Boot dependency management quản lý phiên bản Spring Framework, Reactor và Reactor Netty. Không tự override các module Reactor sang version không tương thích.

### 18.4. application.properties

~~~properties
spring.application.name=webflux-graceful-shutdown
server.port=8080

server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=20s

management.endpoint.health.probes.enabled=true
management.endpoints.web.exposure.include=health,info
~~~

Grace period 20 giây là ví dụ. Termination grace period của container phải lớn hơn tổng thời gian các phase và preStop.

### 18.5. ShutdownApplication.java

~~~java
package demo.shutdown;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ShutdownApplication {
    public static void main(String[] args) {
        SpringApplication.run(
            ShutdownApplication.class,
            args
        );
    }
}
~~~

### 18.6. SseFeed.java

~~~java
package demo.shutdown;

import java.time.Duration;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.stereotype.Component;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.core.publisher.Sinks;

@Component
public class SseFeed {
    private final Sinks.One<Boolean> shutdownSignal = Sinks.one();

    public Flux<ServerSentEvent<String>> events() {
        Flux<ServerSentEvent<String>> ticks =
            Flux.interval(Duration.ofSeconds(1))
                .map(sequence ->
                    ServerSentEvent.<String>builder("tick-" + sequence)
                        .id(Long.toString(sequence))
                        .event("tick")
                        .build()
                );

        Mono<ServerSentEvent<String>> stopping =
            shutdownSignal.asMono()
                .map(ignored ->
                    ServerSentEvent.<String>builder("server-restarting")
                        .event("shutdown")
                        .build()
                );

        return Flux.merge(ticks, stopping)
            .takeUntil(event -> "shutdown".equals(event.event()));
    }

    public void beginShutdown() {
        shutdownSignal.tryEmitValue(Boolean.TRUE);
    }
}
~~~

### 18.7. WebSocketSessionRegistry.java

~~~java
package demo.shutdown;

import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.atomic.AtomicBoolean;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;
import org.springframework.web.reactive.socket.CloseStatus;
import org.springframework.web.reactive.socket.WebSocketSession;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Component
public class WebSocketSessionRegistry {
    private static final Logger log =
        LoggerFactory.getLogger(WebSocketSessionRegistry.class);

    private final ConcurrentMap<String, WebSocketSession> sessions =
        new ConcurrentHashMap<>();

    private final AtomicBoolean draining = new AtomicBoolean();

    public boolean register(WebSocketSession session) {
        if (draining.get()) {
            return false;
        }

        sessions.put(session.getId(), session);

        if (draining.get()) {
            sessions.remove(session.getId(), session);
            return false;
        }
        return true;
    }

    public void remove(String id) {
        sessions.remove(id);
    }

    public int activeCount() {
        return sessions.size();
    }

    public Mono<Void> closeAll() {
        draining.set(true);

        return Flux.fromIterable(sessions.values())
            .flatMap(session ->
                session.close(CloseStatus.GOING_AWAY)
                    .doOnError(error ->
                        log.warn("Could not close session {}",
                            session.getId(), error)
                    )
                    .onErrorResume(error -> Mono.empty()),
                32
            )
            .then();
    }

    public boolean isDraining() {
        return draining.get();
    }
}
~~~

### 18.8. ManagedWebSocketHandler.java

~~~java
package demo.shutdown;

import java.time.Duration;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;
import org.springframework.web.reactive.socket.CloseStatus;
import org.springframework.web.reactive.socket.WebSocketHandler;
import org.springframework.web.reactive.socket.WebSocketMessage;
import org.springframework.web.reactive.socket.WebSocketSession;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Component
public class ManagedWebSocketHandler implements WebSocketHandler {
    private static final Logger log =
        LoggerFactory.getLogger(ManagedWebSocketHandler.class);

    private final WebSocketSessionRegistry registry;

    public ManagedWebSocketHandler(
            WebSocketSessionRegistry registry) {
        this.registry = registry;
    }

    @Override
    public Mono<Void> handle(WebSocketSession session) {
        if (!registry.register(session)) {
            return session.close(CloseStatus.GOING_AWAY);
        }

        Mono<Void> inbound = session.receive()
            .doOnNext(message ->
                log.debug("Received message type={}", message.getType())
            )
            .then();

        Flux<WebSocketMessage> outgoing =
            Flux.interval(Duration.ofSeconds(5))
                .map(sequence ->
                    session.textMessage("heartbeat:" + sequence)
                );

        Mono<Void> outbound = session.send(outgoing);

        return Mono.firstWithSignal(inbound, outbound)
            .doFinally(signal -> registry.remove(session.getId()));
    }
}
~~~

### 18.9. WebSocketConfiguration.java

~~~java
package demo.shutdown;

import java.util.Map;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.HandlerMapping;
import org.springframework.web.reactive.handler.SimpleUrlHandlerMapping;
import org.springframework.web.reactive.socket.WebSocketHandler;

@Configuration
public class WebSocketConfiguration {
    @Bean
    HandlerMapping webSocketMapping(ManagedWebSocketHandler handler) {
        SimpleUrlHandlerMapping mapping = new SimpleUrlHandlerMapping();
        mapping.setUrlMap(Map.<String, WebSocketHandler>of(
            "/ws/live", handler
        ));
        mapping.setOrder(-1);
        return mapping;
    }
}
~~~

### 18.10. DrainCoordinator.java

~~~java
package demo.shutdown;

import java.time.Duration;
import java.util.concurrent.atomic.AtomicBoolean;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.availability.AvailabilityChangeEvent;
import org.springframework.boot.availability.ReadinessState;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.SmartLifecycle;
import org.springframework.stereotype.Component;
import reactor.core.publisher.Mono;

@Component
public class DrainCoordinator implements SmartLifecycle {
    private static final Logger log =
        LoggerFactory.getLogger(DrainCoordinator.class);

    private final ApplicationEventPublisher events;
    private final SseFeed sseFeed;
    private final WebSocketSessionRegistry sessions;

    private final AtomicBoolean running = new AtomicBoolean();
    private final AtomicBoolean draining = new AtomicBoolean();

    public DrainCoordinator(
            ApplicationEventPublisher events,
            SseFeed sseFeed,
            WebSocketSessionRegistry sessions) {
        this.events = events;
        this.sseFeed = sseFeed;
        this.sessions = sessions;
    }

    @Override
    public void start() {
        running.set(true);
    }

    @Override
    public void stop(Runnable callback) {
        if (!running.getAndSet(false)) {
            callback.run();
            return;
        }

        if (!draining.compareAndSet(false, true)) {
            callback.run();
            return;
        }

        AvailabilityChangeEvent.publish(
            events, this, ReadinessState.REFUSING_TRAFFIC
        );

        sseFeed.beginShutdown();

        sessions.closeAll()
            .timeout(Duration.ofSeconds(8))
            .doOnError(error ->
                log.warn("WebSocket drain timed out", error)
            )
            .onErrorResume(error -> Mono.empty())
            .doFinally(signal -> callback.run())
            .subscribe();
    }

    @Override
    public void stop() {
        stop(() -> {});
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
        return DEFAULT_PHASE - 512;
    }

    public boolean isDraining() {
        return draining.get();
    }
}
~~~

### 18.11. StreamController.java

~~~java
package demo.shutdown;

import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;
import reactor.core.publisher.Flux;

@RestController
@RequestMapping("/api")
public class StreamController {
    private final SseFeed feed;
    private final DrainCoordinator drain;

    public StreamController(SseFeed feed, DrainCoordinator drain) {
        this.feed = feed;
        this.drain = drain;
    }

    @GetMapping(path = "/stream",
                produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public Flux<ServerSentEvent<String>> stream() {
        if (drain.isDraining()) {
            return Flux.error(new ResponseStatusException(
                HttpStatus.SERVICE_UNAVAILABLE,
                "instance is draining"
            ));
        }
        return feed.events();
    }
}
~~~

### 18.12. LongTaskController.java

~~~java
package demo.shutdown;

import java.time.Duration;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api")
public class LongTaskController {
    @GetMapping("/work")
    public Mono<String> work(
            @RequestParam(defaultValue = "5") long seconds) {
        if (seconds < 1 || seconds > 15) {
            return Mono.error(
                new IllegalArgumentException(
                    "seconds must be between 1 and 15"
                )
            );
        }

        return Mono.delay(Duration.ofSeconds(seconds))
            .map(ignored -> "completed");
    }
}
~~~

## 19. Unit test cho SSE và WebSocket registry

### 19.1. SseFeedTest.java

~~~java
package demo.shutdown;

import static org.junit.jupiter.api.Assertions.assertEquals;

import java.time.Duration;
import org.junit.jupiter.api.Test;
import reactor.test.StepVerifier;

class SseFeedTest {
    @Test
    void shutdownEventCompletesAnInfiniteSseFeed() {
        SseFeed feed = new SseFeed();

        StepVerifier.withVirtualTime(feed::events)
            .expectSubscription()
            .thenAwait(Duration.ofSeconds(1))
            .assertNext(event ->
                assertEquals("tick", event.event())
            )
            .then(feed::beginShutdown)
            .assertNext(event -> {
                assertEquals("shutdown", event.event());
                assertEquals("server-restarting", event.data());
            })
            .verifyComplete();
    }

    @Test
    void lateSubscriberReceivesShutdownSignal() {
        SseFeed feed = new SseFeed();
        feed.beginShutdown();

        StepVerifier.create(feed.events())
            .assertNext(event ->
                assertEquals("shutdown", event.event())
            )
            .verifyComplete();
    }
}
~~~

Test đầu dùng virtual time để không chờ timer thật. Test thứ hai xác nhận subscriber đến sau khi drain vẫn nhận shutdown event từ Sinks.One.

### 19.2. WebSocketSessionRegistryTest.java

~~~java
package demo.shutdown;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import org.junit.jupiter.api.Test;
import org.springframework.web.reactive.socket.CloseStatus;
import org.springframework.web.reactive.socket.WebSocketSession;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

class WebSocketSessionRegistryTest {
    @Test
    void closesActiveSessionsAndRejectsNewOnes() {
        WebSocketSessionRegistry registry =
            new WebSocketSessionRegistry();

        WebSocketSession active = mock(WebSocketSession.class);
        when(active.getId()).thenReturn("session-1");
        when(active.close(CloseStatus.GOING_AWAY))
            .thenReturn(Mono.empty());

        assertTrue(registry.register(active));
        assertTrue(registry.activeCount() == 1);

        StepVerifier.create(registry.closeAll())
            .verifyComplete();

        verify(active).close(CloseStatus.GOING_AWAY);

        WebSocketSession late = mock(WebSocketSession.class);
        when(late.getId()).thenReturn("session-2");

        assertFalse(registry.register(late));
    }
}
~~~

Test xác minh session hiện tại được đóng bằng status 1001 và session mới bị từ chối sau khi registry bắt đầu drain. Đây là unit test registry, không mở socket network thật.

## 20. Chạy demo và kiểm tra thủ công

Cần Java 17 và Gradle:

~~~bash
gradle test
gradle bootRun
~~~

### 20.1. HTTP request đang chạy

Terminal 1:

~~~bash
curl -i "http://localhost:8080/api/work?seconds=10"
~~~

Trong lúc request chờ, gửi SIGTERM tới process ứng dụng trên Linux/container. Nếu grace period đủ dài, response có thể hoàn tất:

~~~text
HTTP/1.1 200 OK
Content-Type: text/plain;charset=UTF-8

completed
~~~

Đây là kết quả mong đợi khi request hoàn tất trước khi grace period hết.

### 20.2. SSE

Terminal khác:

~~~bash
curl -N -H "Accept: text/event-stream" \
  http://localhost:8080/api/stream
~~~

Event bình thường:

~~~text
id:0
event:tick
data:tick-0

id:1
event:tick
data:tick-1

~~~

Khi ứng dụng drain, stream phát event cuối:

~~~text
event:shutdown
data:server-restarting

~~~

Sau event shutdown, response complete và curl kết thúc.

### 20.3. WebSocket

Kết nối client tới:

~~~text
ws://localhost:8080/ws/live
~~~

Client nhận heartbeat mỗi 5 giây. Khi server dừng, registry gửi Close frame status 1001 GOING_AWAY.

Browser console:

~~~javascript
const socket = new WebSocket("ws://localhost:8080/ws/live");

socket.onmessage = event => console.log(event.data);

socket.onclose = event => {
    console.log("close code:", event.code);
    if (event.code === 1001) {
        console.log("server is going away; reconnect with backoff");
    }
};
~~~

### 20.4. Readiness

~~~bash
curl -i http://localhost:8080/actuator/health/readiness
~~~

Khi shutdown bắt đầu, readiness chuyển sang không sẵn sàng. Sau khi server ngừng nhận request, endpoint có thể không còn truy cập được qua HTTP connector.

## 21. Runbook khi shutdown không hoàn tất

| Triệu chứng | Nguyên nhân có thể | Việc cần kiểm tra |
| --- | --- | --- |
| Process bị kill trước callback | termination grace period quá ngắn | preStop + các lifecycle phase + margin |
| HTTP request bị cắt | request lâu hơn grace period | request/downstream timeout và p99 |
| SSE giữ process lâu | Flux không complete | shutdown event/cancel |
| WebSocket vẫn mở | Không quản lý session registry | CloseStatus và registry |
| Worker vẫn nhận message | Consumer chưa pause | stop intake, in-flight, ack/checkpoint |
| WebClient lỗi khi shutdown | Pool dispose quá sớm | Pool cleanup sau request drain |
| Scheduler task bị bỏ dở | Dispose trước task | Stop intake và chờ task |
| Callback không chạy | Lỗi cleanup chain hoặc quên callback | doFinally và callback đúng một lần |
| Shutdown treo | Mono cleanup không terminal | Timeout cho từng resource |
| Client reconnect đồng loạt | Không có backoff/jitter | Exponential backoff và jitter |
| DB operation không rõ kết quả | Response mất sau commit | Idempotency key và endpoint tra trạng thái |
| Kubernetes kill sau SIGTERM | terminationGracePeriodSeconds thiếu | Tăng budget hoặc rút ngắn cleanup |

Trình tự điều tra:

1. Xác nhận process nhận SIGTERM hay SIGKILL.
2. Đọc log shutdown và readiness state.
3. Xem phase nào chưa gọi callback.
4. Kiểm tra số HTTP request in-flight.
5. Kiểm tra SSE/WebSocket session còn hoạt động.
6. Kiểm tra worker/message consumer và message chưa ack.
7. Kiểm tra connection pool và Scheduler.
8. So sánh thời gian thực tế với timeout từng phase.
9. Điều chỉnh policy ở đúng resource.
10. Thử lại với request dài, client disconnect và dependency chậm.

Không tăng toàn bộ timeout lên rất lớn mà không biết resource nào đang giữ process. Một stream không bao giờ complete vẫn sẽ giữ ứng dụng đến hết deadline.

## 22. Anti-pattern thường gặp

| Anti-pattern | Hậu quả | Cách sửa |
| --- | --- | --- |
| Chỉ gọi System.exit(0) | Bỏ qua lifecycle cleanup | Đóng ApplicationContext theo cơ chế chuẩn |
| Chỉ dùng @PreDestroy cho cleanup async | Không có callback chờ publisher | SmartLifecycle.stop(Runnable) |
| Block vô hạn trong stop() | Lifecycle thread bị treo | Reactive cleanup có timeout |
| Gọi callback ngay sau subscribe | Destroy dependency quá sớm | Callback khi cleanup terminal |
| Đóng pool trước HTTP drain | In-flight request mất connection | Resource phase sau grace period |
| Không cập nhật readiness | Load balancer tiếp tục gửi traffic | REFUSING_TRAFFIC |
| Chờ Flux.interval complete | Stream không bao giờ complete | Shutdown signal/cancel |
| Không track WebSocket session | Socket bị cắt đột ngột | Registry và Close frame |
| Đóng WebSocket bằng TCP reset | Client không biết lý do | CloseStatus phù hợp |
| Không cancel broker subscription | Resource còn sống | doFinally/usingWhen |
| Ack message trước khi xử lý xong | Mất công việc khi kill | Ack sau commit, retry idempotent |
| Queue vô hạn khi consumer dừng | Memory tăng | Bounded queue và drain |
| Một timeout cho mọi resource | Một dependency treo chiếm hết budget | Timeout theo resource |
| Dispose global Reactor Netty resources | Ảnh hưởng nhiều client | Chỉ dispose custom provider |
| Reconnect ngay lập tức | Connection storm | Backoff + jitter |
| Dùng readiness làm liveness | Orchestrator restart nhầm | Tách readiness/liveness |
| Không test SIGTERM | Lỗi chỉ xuất hiện lúc deploy | Manual/integration shutdown test |

## 23. Checklist production

1. Embedded server có graceful shutdown enabled không?
2. timeout-per-shutdown-phase phù hợp với SLO và container budget không?
3. Readiness chuyển sang REFUSING_TRAFFIC trước khi dừng nhận traffic chưa?
4. Load balancer/service mesh có thời gian cập nhật endpoint không?
5. In-flight HTTP request có timeout hữu hạn không?
6. SSE có shutdown event và complete không?
7. WebSocket có registry, close status và reconnect policy không?
8. Client reconnect có exponential backoff và jitter không?
9. Worker có stop intake, drain và checkpoint không?
10. Message chỉ ack sau khi xử lý thành công không?
11. Scheduler riêng có lifecycle/dispose rõ ràng không?
12. WebClient custom ConnectionProvider có disposeLater sau request drain không?
13. R2DBC/JDBC pool chỉ đóng sau transaction/request hoàn tất không?
14. Async SmartLifecycle stop có callback đúng một lần không?
15. Cleanup có timeout và log lỗi không?
16. Có metric cho active request, session, worker và shutdown duration không?
17. Kubernetes terminationGracePeriodSeconds đủ cho preStop và các phase không?
18. Có test SIGTERM trong môi trường gần production không?
19. Có kiểm thử dependency treo, client disconnect và pool cạn không?
20. Có idempotency/recovery cho business operation bị cắt không?

## 24. Câu hỏi ôn tập có đáp án

**Câu 1. Spring Boot graceful shutdown làm gì?**

Ngừng nhận request mới và cho request đang xử lý một grace period để hoàn tất trước khi dừng server.

**Câu 2. server.shutdown=graceful có mặc định trong Boot 3.5 không?**

Có với embedded web server; khai báo tường minh vẫn giúp thể hiện cấu hình.

**Câu 3. timeout-per-shutdown-phase là tổng thời gian shutdown?**

Không. Nó áp dụng cho mỗi lifecycle phase; tổng thời gian có thể lớn hơn.

**Câu 4. Vì sao readiness phải chuyển sang REFUSING_TRAFFIC?**

Để orchestrator/load balancer ngừng route request mới tới instance đang drain.

**Câu 5. Vì sao SSE cần chính sách riêng?**

SSE có thể không complete tự nhiên. Server nên phát shutdown event rồi complete hoặc cancel publisher.

**Câu 6. CloseStatus.GOING_AWAY có mã nào?**

1001, dùng khi endpoint đang rời đi, ví dụ server shutdown.

**Câu 7. WebSocketHandler nên làm gì khi session đóng?**

Inbound complete và outbound bị cancel; handler compose hai stream và release registry/subscription trong doFinally.

**Câu 8. SmartLifecycle.stop(Runnable) dùng callback để làm gì?**

Báo Spring rằng quá trình stop bất đồng bộ đã hoàn tất và có thể chuyển phase.

**Câu 9. Vì sao không gọi callback ngay sau subscribe?**

Cleanup chưa hoàn tất; Spring có thể destroy dependency khi session/worker vẫn đang hoạt động.

**Câu 10. Khi nào dùng ConnectionProvider.disposeLater()?**

Khi ứng dụng sở hữu custom Reactor Netty pool và cần một Mono để quan sát/chờ disposal.

**Câu 11. Có nên dispose HttpResources global khi shutdown một WebClient custom không?**

Không. Global resources có thể được nhiều client/server chia sẻ; chỉ dispose resource do ứng dụng tự sở hữu.

**Câu 12. Message consumer nên ack lúc nào?**

Sau khi business operation xử lý và commit theo semantics broker; nếu chưa xong, để retry/redelivery an toàn.

**Câu 13. Vì sao cần exponential backoff và jitter?**

Để nhiều client không reconnect đồng loạt và tạo connection storm.

**Câu 14. terminationGracePeriodSeconds phải tính những gì?**

preStop duration, app drain, web server grace, custom resource cleanup và safety margin.

**Câu 15. SIGKILL có chạy @PreDestroy không?**

Không. SIGKILL kết thúc process ngay và không cho JVM chạy shutdown hook/lifecycle callback.

## 25. Tổng kết và tài liệu chính thức

- Spring Boot graceful shutdown ngừng nhận request mới và chờ in-flight HTTP request trong grace period.
- Readiness nên chuyển sang REFUSING_TRAFFIC để hạ tầng ngừng route traffic mới.
- SSE cần shutdown event/complete; WebSocket cần close handshake và session registry.
- SmartLifecycle.stop(Runnable) hỗ trợ cleanup bất đồng bộ và chờ callback.
- Background worker phải stop intake, drain in-flight và ack/checkpoint đúng nghiệp vụ.
- Custom WebClient ConnectionProvider nên dispose sau khi request drain; không tự dispose global Reactor Netty resources.
- Mỗi cleanup cần timeout; container deadline phải lớn hơn tổng shutdown budget.
- Client cần reconnect backoff/jitter và idempotency cho command có side effect.
- Kiểm thử bằng SIGTERM thật, không chỉ unit test lifecycle method.

Tài liệu tham khảo:

1. [Spring Boot 3.5 — Graceful Shutdown](https://docs.spring.io/spring-boot/3.5/reference/web/graceful-shutdown.html): embedded server, grace period và timeout per phase.
2. [Spring Boot 3.5 — Actuator Endpoints, Application Lifecycle and Probe States](https://docs.spring.io/spring-boot/3.5/reference/actuator/endpoints.html): readiness/liveness trong shutdown.
3. [Spring Boot 3.5 — Application Events and Availability](https://docs.spring.io/spring-boot/3.5/reference/features/spring-application.html): AvailabilityChangeEvent và readiness state.
4. [Spring Framework 6.2 — SmartLifecycle and Bean Lifecycle](https://docs.spring.io/spring-framework/reference/6.2/core/beans/factory-nature.html): phase ordering, stop callback và timeout.
5. [Spring Framework 6.2 — WebFlux WebSockets](https://docs.spring.io/spring-framework/reference/6.2/web/webflux-websocket.html): WebSocketHandler, receive/send và session lifecycle.
6. [Spring Framework 6.2 — WebFlux CloseStatus Javadoc](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/web/reactive/socket/CloseStatus.html): close codes 1000, 1001, 1012 và status khác.
7. [Reactor Netty — HTTP Client Connection Pool](https://projectreactor.io/docs/netty/release/reference/http-client.html): dispose, disposeLater, disposeTimeout và custom ConnectionProvider.
8. [Spring Boot 3 Migration Guide — Updated Graceful Shutdown Phases](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-3.0-Migration-Guide#updated-phases-for-graceful-shutdown): thứ tự phase graceful shutdown và web server.
9. [Spring Boot 3.5 — Reactive Web Applications](https://docs.spring.io/spring-boot/3.5/reference/web/reactive.html): WebFlux và Reactor Netty resources.
10. [Kubernetes — Container Lifecycle Hooks](https://kubernetes.io/docs/concepts/containers/container-lifecycle-hooks/): preStop, SIGTERM và termination grace period.
