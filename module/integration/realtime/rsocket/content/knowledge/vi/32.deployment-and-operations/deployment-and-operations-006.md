# Kiểm tra sức khỏe, readiness và khả năng chấp nhận kết nối mới

Một RSocket service có thể vẫn chạy process nhưng không còn sẵn sàng nhận request: listener chưa bind xong, cấu hình chưa tải đủ, instance đang quá tải hoặc ứng dụng chuẩn bị shutdown. Ngược lại, một dependency bên ngoài có thể tạm lỗi trong khi process và RSocket server vẫn hoạt động bình thường. Nếu gom tất cả các trạng thái này thành một cờ `healthy`, orchestrator có thể restart nhầm instance hoặc tiếp tục gửi traffic vào node đang rời cụm.

Triển khai vận hành cần tách bốn câu hỏi:

| Khái niệm | Câu hỏi | Hành động thường tương ứng |
| --- | --- | --- |
| Liveness | Process còn hoạt động và có khả năng tự phục hồi không? | Nếu lỗi không thể tự phục hồi, restart instance |
| Readiness | Instance có thể xử lý traffic mới ở thời điểm này không? | Nếu chưa sẵn sàng, ngừng định tuyến traffic tới instance |
| Startup | Instance đã hoàn tất khởi tạo cần thiết chưa? | Cho phép khởi động lâu hơn trước khi liveness bắt đầu |
| Admission / drain | Server có nhận connection hoặc interaction mới không, và request đang chạy còn bao nhiêu? | Từ chối công việc mới, chờ công việc đang chạy kết thúc rồi dừng server |

Readiness là tín hiệu cho hệ thống định tuyến. Nó không tự đóng listener RSocket, không tự từ chối một `SETUP` trực tiếp và không tự kết thúc các stream đang chạy. Muốn shutdown có kiểm soát, ứng dụng cần một admission gate và quy trình drain riêng.

## 1. Vì sao RSocket cần health check riêng?

RSocket thường giữ một kết nối TCP hoặc WebSocket trong thời gian dài. Nhiều interaction có thể multiplex trên cùng một connection; request-response, fire-and-forget, request-stream và request-channel không nhất thiết tạo một connection mới cho mỗi request.

```text
Kubernetes / Load balancer
          |
          | readiness + service discovery
          v
   RSocket instance A
     | listener TCP / WebSocket
     | RSocket SETUP
     +-----------------------------+
     | connection 1                | connection 2
     |  RR  Stream  FNF             | Channel  Stream
     |                              |
     +---------- handlers ----------+
```

Có hai loại kiểm tra khác nhau:

- **Health endpoint** thường là HTTP Actuator, ví dụ `/actuator/health/readiness`. Nó báo trạng thái của process và RSocket listener cho Kubernetes hoặc load balancer.
- **RSocket protocol health check** mở một RSocket connection và gọi một route kiểm tra, ví dụ `health.ping`. Nó kiểm tra sâu hơn đường đi RSocket, nhưng cần được giới hạn tần suất và timeout để không trở thành tải phụ.

Với RSocket chạy TCP trên cổng 7000, Actuator có thể chạy ở cổng quản trị HTTP 8081. Hai cổng phục vụ hai giao thức khác nhau; health endpoint trên 8081 chỉ đáng tin khi nó kiểm tra cả trạng thái listener RSocket ở cổng 7000.

## 2. Phân biệt liveness, readiness và startup

### 2.1. Liveness: process có thể tiếp tục chạy không?

Liveness nên kiểm tra các lỗi nội bộ nghiêm trọng khiến instance không thể tiếp tục phục vụ, chẳng hạn event loop bị kẹt, invariant quan trọng bị phá vỡ hoặc một thành phần cốt lõi đã chết và không có cách phục hồi tại chỗ.

Không đưa database, message broker, service discovery hoặc API dùng chung của toàn hệ thống vào liveness. Nếu một database dùng chung tạm ngừng, Kubernetes có thể restart tất cả RSocket instances cùng lúc. Các instance mới lại cố kết nối tới database đang lỗi, làm tăng tải và tạo cascading failure.

### 2.2. Readiness: instance có thể nhận traffic mới không?

Readiness phản ánh khả năng phục vụ tại thời điểm kiểm tra. Với RSocket service, readiness thường cần xác minh:

- RSocket listener đã bind và đang hoạt động.
- Ứng dụng đã hoàn tất tải cấu hình, migration hoặc warm-up bắt buộc.
- Admission gate đang cho phép nhận công việc mới.
- Những dependency riêng của instance mà nghiệp vụ không thể hoạt động nếu thiếu chúng đang sẵn sàng.
- Instance không ở trạng thái drain, maintenance hoặc overload cần được loại khỏi pool.

Không mặc định đưa mọi dependency bên ngoài vào readiness. Nếu một dependency dùng chung bị lỗi, hãy cân nhắc ứng dụng có thể dùng cache, circuit breaker, fallback hoặc trả lỗi có kiểm soát hay không. Chỉ đánh dấu tất cả instances unready khi thực sự không có request nào có thể được xử lý an toàn.

### 2.3. Startup probe: cho phép khởi động lâu hơn

Startup probe phù hợp khi ứng dụng cần thời gian để tải dữ liệu, khởi tạo RSocket listener, tạo connection pool hoặc thực hiện tác vụ startup. Khi startup probe chưa thành công, Kubernetes chưa chạy liveness và readiness probe. Nhờ vậy, không cần đặt liveness delay quá dài chỉ để chờ một lần khởi động chậm.

Nếu startup thông thường mất 20 giây nhưng đôi khi cần 90 giây, hãy đặt startup budget đủ lớn cho trường hợp xấu đã đo được. Không đặt ngưỡng vô hạn để che lỗi startup thật.

## 3. Spring Boot Actuator cho readiness

Spring Boot có `ApplicationAvailability` và hai trạng thái `LivenessState`/`ReadinessState`. Actuator cung cấp các health group:

- `/actuator/health/liveness`
- `/actuator/health/readiness`

Trong Spring Boot, readiness thường chuyển sang `ACCEPTING_TRAFFIC` sau khi `ApplicationReadyEvent` và các runner hoàn tất. Khi shutdown, readiness chuyển sang `REFUSING_TRAFFIC`. Có thể chủ động cập nhật trạng thái khi ứng dụng bước vào maintenance hoặc drain.

Ví dụ cấu hình RSocket TCP cùng cổng quản trị HTTP riêng:

```yaml
spring:
  rsocket:
    server:
      transport: tcp
      port: 7000
  lifecycle:
    timeout-per-shutdown-phase: 45s

management:
  server:
    port: 8081
  endpoints:
    web:
      exposure:
        include: health
  endpoint:
    health:
      probes:
        enabled: true
      show-details: never
      group:
        readiness:
          include: "readinessState,rsocketAdmission"
```

`rsocketAdmission` là health contributor tùy chỉnh sẽ được tạo ở phần tiếp theo. Nó xác minh trạng thái listener/admission của RSocket server. Nếu không có health contributor này, readiness group mặc định chỉ biết trạng thái availability của Spring Boot, chưa chắc biết RSocket TCP listener có đang hoạt động hay không.

Ví dụ giả định ứng dụng có HTTP server để expose Actuator. Nếu ứng dụng chỉ chạy RSocket TCP và không có HTTP server, cần bổ sung management web server phù hợp hoặc dùng probe `exec`/sidecar có RSocket client; chỉ khai báo `management.server.port` không tự tạo ra một health endpoint nếu ứng dụng không có web infrastructure.

Nếu ứng dụng có HTTP server chính và muốn đặt probe trên cùng cổng với traffic ứng dụng, có thể bật:

```yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
        add-additional-paths: true
```

Spring Boot khi đó cung cấp thêm `/livez` và `/readyz` trên main server port. Nếu Actuator ở management port riêng, hãy kiểm tra health endpoint trên cổng quản trị và đảm bảo readiness group vẫn kiểm tra được listener RSocket thực tế. Một management port khỏe không tự chứng minh cổng RSocket khỏe.

Chỉ expose health endpoint cần thiết. Không bật toàn bộ Actuator endpoints ra Internet và không trả chi tiết connection, credential, địa chỉ nội bộ hoặc exception nhạy cảm trong health response.

## 4. Health indicator theo dõi trạng thái RSocket

Một admission gate đơn giản có thể giữ trạng thái listener và khả năng nhận kết nối mới:

```java
@Component
public class RSocketAdmissionGate {

    private final AtomicBoolean listenerBound = new AtomicBoolean(false);
    private final AtomicBoolean accepting = new AtomicBoolean(false);

    public void markListenerBound() {
        listenerBound.set(true);
    }

    public void startAccepting() {
        if (!listenerBound.get()) {
            throw new IllegalStateException("RSocket listener is not bound");
        }
        accepting.set(true);
    }

    public void refuseNewWork() {
        accepting.set(false);
    }

    public boolean isListenerBound() {
        return listenerBound.get();
    }

    public boolean isAccepting() {
        return accepting.get();
    }

    public boolean isReady() {
        return listenerBound.get() && accepting.get();
    }
}
```

Đánh dấu listener bound sau khi server thực sự bind thành công. Với Spring Boot server được quản lý trong application lifecycle, có thể cập nhật trạng thái ở bước lifecycle tương ứng sau khi server đã start; nếu server được bind thủ công, cập nhật ngay sau `bind()` thành công. Khi listener dừng hoặc lỗi, phải xóa trạng thái bound. Không đặt `listenerBound=true` chỉ vì ApplicationContext đã được tạo.

Đăng ký health contributor có tên `rsocketAdmission` để readiness group sử dụng:

```java
@Configuration
public class RSocketHealthConfiguration {

    @Bean("rsocketAdmission")
    HealthIndicator rsocketAdmissionHealthIndicator(RSocketAdmissionGate gate) {
        return () -> {
            if (gate.isReady()) {
                return Health.up().build();
            }

            return Health.outOfService()
                    .withDetail("listenerBound", gate.isListenerBound())
                    .withDetail("acceptingNewWork", gate.isAccepting())
                    .build();
        };
    }
}
```

Khi listener chưa bind hoặc admission gate đã đóng, readiness trả trạng thái không phục vụ. Spring Boot ánh xạ `OUT_OF_SERVICE` thành health status không thành công cho probe. Liveness vẫn có thể `UP`, vì instance đang drain có chủ đích và không cần bị restart.

## 5. Đồng bộ readiness với vòng đời ứng dụng

Spring Boot tự chuyển readiness sang `ACCEPTING_TRAFFIC` khi ứng dụng hoàn tất startup. Ứng dụng cần đồng bộ admission gate với thời điểm listener RSocket thực sự sẵn sàng.

Ví dụ lifecycle signal cho một RSocket listener do Spring Boot quản lý:

```java
@Component
public class RSocketAvailabilityLifecycle {

    private final RSocketAdmissionGate gate;
    private final ApplicationEventPublisher events;

    public RSocketAvailabilityLifecycle(
            RSocketAdmissionGate gate,
            ApplicationEventPublisher events) {
        this.gate = gate;
        this.events = events;
    }

    @EventListener(ApplicationReadyEvent.class)
    public void onApplicationReady() {
        // Giả định RSocket server đã bind trong lifecycle của Boot.
        // Với server bind thủ công, cập nhật listenerBound ngay sau bind thành công.
        gate.markListenerBound();
        gate.startAccepting();
    }

    public void beginDrain() {
        gate.refuseNewWork();
        events.publishEvent(new AvailabilityChangeEvent<>(
                this, ReadinessState.REFUSING_TRAFFIC));
    }
}
```

`beginDrain()` nên được gọi bởi shutdown coordinator hoặc một hook quản trị nội bộ đã được bảo vệ. Không cần mở một REST endpoint drain công khai. Trong hệ thống có server restart độc lập với Spring Context, cần nối sự kiện stop/error thực tế của listener vào gate để health phản ánh đúng trạng thái sau khi server gặp sự cố.

## 6. Readiness không tự chặn RSocket connection mới

Khi readiness chuyển sang `REFUSING_TRAFFIC`, Kubernetes sẽ đánh dấu Pod không sẵn sàng và loại địa chỉ Pod khỏi EndpointSlice của Service. Load balancer hoặc service discovery sau đó ngừng chọn instance này cho traffic mới.

Tuy nhiên, readiness chỉ là tín hiệu định tuyến. Nó không đóng socket hiện có. Với RSocket, điều này đặc biệt quan trọng vì client có thể giữ connection lâu và gửi nhiều interaction trên cùng connection. Một load balancer có thể không chuyển connection đã thiết lập sang Pod khác.

Cần phân biệt ba lớp admission:

| Lớp | Ngăn điều gì? | Cách triển khai |
| --- | --- | --- |
| Readiness | Router chọn instance cho traffic mới | Actuator readiness / Kubernetes Service |
| Connection admission | RSocket peer thiết lập session mới | Kiểm tra `SETUP` trong `SocketAcceptor` |
| Interaction admission | Client mở request mới trên connection đang tồn tại | Gate ở responder `RSocket` hoặc chính sách LEASE |

### 6.1. Từ chối SETUP mới với SocketAcceptorInterceptor

RSocket Java cho phép chặn connection ở thời điểm xử lý `SETUP`. Ví dụ dưới đây dùng `RSocketServerCustomizer` của Spring Boot và `SocketAcceptorInterceptor` của RSocket Java:

```java
@Configuration
public class RSocketAdmissionConfiguration {

    @Bean
    RSocketServerCustomizer admissionCustomizer(RSocketAdmissionGate gate) {
        return server -> server.interceptors(registry ->
                registry.forSocketAcceptor(delegate -> (setup, sendingSocket) -> {
                    if (!gate.isAccepting()) {
                        return Mono.error(new RejectedSetupException(
                                "RSocket instance is draining"));
                    }

                    return delegate.accept(setup, sendingSocket);
                }));
    }
}
```

Đây là ví dụ cho Netty RSocket server được Spring Boot quản lý. Nếu ứng dụng expose RSocket qua WebFlux WebSocket route, hãy áp dụng admission policy ở đúng WebSocket/RSocket handler của phiên bản Spring đang dùng.

Gate được kiểm tra khi xử lý RSocket `SETUP`. Với TCP, TCP handshake có thể đã hoàn tất trước khi server từ chối `SETUP`; client vẫn nhận được lỗi setup và không có RSocket session hoạt động. Client nên xử lý lỗi từ chối bằng backoff có giới hạn, tránh reconnect liên tục vào node đang drain.

### 6.2. Chặn interaction mới trên persistent connection

Chỉ chặn `SETUP` chưa đủ. Một client có thể đã kết nối từ trước và tiếp tục mở request-response, stream hoặc channel trong lúc server đang drain. Có thể bọc responder bằng `RSocketProxy` để kiểm tra admission ở thời điểm subscribe. Đoạn sau được thêm vào cùng callback `server.interceptors(registry -> { ... })` của customizer ở phần trước:

```java
registry.forResponder(source -> new RSocketProxy(source) {

    @Override
    public Mono<Void> fireAndForget(Payload payload) {
        return Mono.defer(() -> gate.isAccepting()
                ? super.fireAndForget(payload)
                : Mono.error(new RejectedException("Instance is draining")));
    }

    @Override
    public Mono<Payload> requestResponse(Payload payload) {
        return Mono.defer(() -> gate.isAccepting()
                ? super.requestResponse(payload)
                : Mono.error(new RejectedException("Instance is draining")));
    }

    @Override
    public Flux<Payload> requestStream(Payload payload) {
        return Flux.defer(() -> gate.isAccepting()
                ? super.requestStream(payload)
                : Flux.error(new RejectedException("Instance is draining")));
    }

    @Override
    public Flux<Payload> requestChannel(Publisher<Payload> payloads) {
        return Flux.defer(() -> gate.isAccepting()
                ? super.requestChannel(payloads)
                : Flux.error(new RejectedException("Instance is draining")));
    }
});
```

Đoạn interceptor này có thể đăng ký cùng `forSocketAcceptor` trong cùng `RSocketServerCustomizer`. `Mono.defer`/`Flux.defer` đảm bảo gate được kiểm tra khi interaction bắt đầu. Request đã được chấp nhận trước thời điểm drain tiếp tục chạy; request mới sau khi gate đóng bị từ chối.

`RejectedException` và `RejectedSetupException` là các loại lỗi từ chối có thể retry theo protocol. Client vẫn cần backoff, tôn trọng readiness/service discovery và giới hạn số lần thử. Nếu không muốn retry ngay, hãy cấu hình retry policy ở client phù hợp với trạng thái drain.

## 7. Theo dõi request đang chạy để drain

Không thể biết thời điểm an toàn để dừng server chỉ bằng số connection. Một connection có thể không có request nào, hoặc có một request-stream kéo dài hàng giờ. Cần theo dõi active interactions, cancellation và terminal signal.

RSocket Java có `RequestInterceptor` để quan sát vòng đời request. Ví dụ đếm số interaction đang hoạt động trên toàn server:

Đăng ký đoạn interceptor này trong callback `server.interceptors(registry -> { ... })` của `RSocketServerCustomizer`, cùng các interceptor admission ở phần trước:

```java
AtomicInteger inFlight = new AtomicInteger();
AtomicLong rejected = new AtomicLong();

server.interceptors(registry -> registry.forRequestsInResponder(socket ->
        new RequestInterceptor() {

            @Override
            public void onStart(int streamId, FrameType requestType, ByteBuf metadata) {
                inFlight.incrementAndGet();
            }

            @Override
            public void onTerminate(int streamId, FrameType requestType, Throwable error) {
                inFlight.decrementAndGet();
            }

            @Override
            public void onCancel(int streamId, FrameType requestType) {
                inFlight.decrementAndGet();
            }

            @Override
            public void onReject(Throwable reason, FrameType requestType, ByteBuf metadata) {
                rejected.incrementAndGet();
            }
        }));
```

`onStart` được gọi khi request đã được chấp nhận và bắt đầu. Sau đó request kết thúc qua `onTerminate` hoặc `onCancel`; hai callback này loại trừ nhau. `onReject` chỉ ghi nhận request bị từ chối, không giảm bộ đếm vì request đó chưa được tính vào `inFlight`.

Trong code thực tế, đặt các bộ đếm này trong bean metrics dùng chung và xuất gauge/counter qua Micrometer. Nếu cần chờ chính xác đến `inFlight == 0`, hãy đồng bộ thao tác đóng admission với việc tăng bộ đếm để tránh race giữa request vừa được nhận và drain vừa bắt đầu. Có thể dùng lock/semaphore hoặc một drain coordinator có cơ chế atomic admission.

Đặt deadline cho drain. Một request-response thường có thể hoàn tất trong thời gian ngắn; request-stream và request-channel có thể kéo dài lâu hơn nhiều. Nếu stream không kết thúc trước deadline, ứng dụng cần chính sách cụ thể: gửi tín hiệu kết thúc nghiệp vụ, cancel stream, đóng session hoặc buộc đóng connection. Không giữ Pod mãi chỉ vì một subscription không bao giờ complete.

## 8. Quy trình graceful drain khi shutdown

Một quy trình shutdown có kiểm soát thường theo thứ tự:

1. **Đánh dấu unready:** đóng admission gate và phát `ReadinessState.REFUSING_TRAFFIC`.
2. **Chờ định tuyến hội tụ:** cho Kubernetes EndpointSlice, service discovery và load balancer thời gian cập nhật.
3. **Từ chối công việc mới:** từ chối `SETUP` mới và interaction mới trên các connection đang tồn tại.
4. **Theo dõi công việc đang chạy:** chờ `inFlight` giảm về 0 hoặc đến drain deadline.
5. **Đóng listener:** dừng nhận transport connection mới; sau đó đóng các session/stream còn lại theo chính sách.
6. **Kết thúc process:** để Spring lifecycle hoàn tất trước khi Kubernetes hết termination grace period.

Với RSocket TCP server được quản lý bởi Spring Boot, `org.springframework.boot.rsocket.server.RSocketServer` có lifecycle `start()`/`stop()`. Với RSocket Java core, `RSocketServer.bind(...)` trả về một `Closeable` có thể dispose để dừng server. Các API này điều khiển server listener; không mặc định rằng chúng tự chờ mọi application stream hoàn tất. Hãy kết hợp admission gate, in-flight tracking và test shutdown trên đúng transport/version.

Ví dụ cấu hình graceful shutdown cho embedded HTTP server:

```yaml
server:
  shutdown: graceful

spring:
  lifecycle:
    timeout-per-shutdown-phase: 45s
```

`server.shutdown=graceful` áp dụng cho embedded web server của Spring Boot. Nếu RSocket chạy trên TCP listener riêng, cần quản lý lifecycle của RSocket server riêng. Nếu RSocket chạy qua WebSocket trên WebFlux, graceful shutdown của HTTP server giúp xử lý HTTP listener/handshake, nhưng các WebSocket session đã upgrade vẫn là kết nối dài hạn và cần chính sách drain/cancel riêng.

### 8.1. Kubernetes preStop và termination grace period

Kubernetes gọi `preStop` trước khi gửi TERM tới container. Thời gian chạy `preStop` được tính vào `terminationGracePeriodSeconds`; không cộng thêm sau grace period. Vì vậy cần chọn grace period lớn hơn tổng thời gian:

```text
terminationGracePeriodSeconds
  >= preStop / trigger drain
   + thời gian load balancer ngừng gửi traffic
   + thời gian chờ in-flight interactions
   + thời gian đóng listener và cleanup
   + safety margin
```

Hook `preStop` có thể gọi một lệnh drain nội bộ hoặc trigger cơ chế shutdown coordinator. Nếu cần chờ EndpointSlice/LB hội tụ, dùng khoảng chờ đã đo trong môi trường triển khai. Không dựa vào một `sleep` tùy ý mà không đo thời gian cập nhật endpoint.

Ví dụ Kubernetes probe cho management HTTP port:

```yaml
spec:
  terminationGracePeriodSeconds: 90
  containers:
    - name: rsocket-service
      ports:
        - name: rsocket
          containerPort: 7000
        - name: management
          containerPort: 8081
      startupProbe:
        httpGet:
          path: /actuator/health/liveness
          port: management
        periodSeconds: 5
        failureThreshold: 30
        timeoutSeconds: 2
      livenessProbe:
        httpGet:
          path: /actuator/health/liveness
          port: management
        periodSeconds: 10
        failureThreshold: 3
        timeoutSeconds: 2
      readinessProbe:
        httpGet:
          path: /actuator/health/readiness
          port: management
        periodSeconds: 5
        failureThreshold: 2
        timeoutSeconds: 2
```

Các giá trị là ví dụ để bắt đầu, không phải ngưỡng dùng chung cho mọi ứng dụng. Startup budget ở ví dụ là khoảng 150 giây theo `failureThreshold × periodSeconds`. Readiness cần đủ nhạy để loại instance đang drain; liveness cần đủ ổn định để không restart do một đợt quá tải ngắn.

Nếu Actuator nằm trên main HTTP port, có thể dùng `/livez` và `/readyz` khi đã bật `management.endpoint.health.probes.add-additional-paths=true`. Nếu ứng dụng chỉ có RSocket TCP và management HTTP port riêng, giữ probe ở management port nhưng đảm bảo custom health indicator kiểm tra listener TCP thực tế.

`tcpSocket` probe vào cổng 7000 chỉ xác nhận TCP port có thể mở kết nối. Nó không xác minh RSocket `SETUP`, MIME type, authentication, route hoặc khả năng xử lý request. Nếu cần kiểm tra end-to-end protocol, tạo một probe client RSocket nhẹ gọi route health chuyên dụng với timeout ngắn; không dùng route nghiệp vụ nặng làm health probe.

## 9. Readiness cho dependency và overload

Readiness có thể chuyển sang `REFUSING_TRAFFIC` sau startup nếu instance không còn đủ khả năng nhận việc mới. Ví dụ:

- Connection pool cục bộ đã hết và không thể phục hồi.
- Bộ nhớ hoặc queue nội bộ đã chạm ngưỡng admission.
- Instance đang thay chứng thư hoặc thay cấu hình transport.
- Server đang drain để rolling deployment.
- Một dependency chỉ tồn tại riêng cho instance này đã mất và không có fallback.

Không nên đánh dấu unready chỉ vì CPU tăng nhẹ hoặc một request chậm. Nếu mọi instance đều unready cùng lúc, Service có thể không còn endpoint và client không kết nối được. Với overload ngắn, cân nhắc giới hạn request, backpressure, RSocket LEASE, circuit breaker hoặc từ chối một phần traffic trước khi rút toàn bộ instance khỏi pool.

Nếu dùng RSocket LEASE, cả hai phía phải hỗ trợ và client phải yêu cầu dùng lease. Server có thể kiểm soát số request được phép trong một khoảng thời gian. Khi drain, có thể ngừng cấp lease mới hoặc cấp lease với quota thấp; các lease đã cấp vẫn có thể còn hiệu lực tới khi hết hạn. LEASE là cơ chế điều tiết request, không thay thế readiness và connection admission.

## 10. Quan sát sức khỏe và quá trình drain

Health endpoint cho biết trạng thái tổng quát. Để hiểu tại sao instance không sẵn sàng hoặc shutdown bị kéo dài, hãy thu thập thêm metrics:

| Metric / trạng thái | Ý nghĩa |
| --- | --- |
| `rsocket_listener_bound` | Listener đã bind và đang được quản lý |
| `rsocket_accepting_connections` | Admission gate cho phép `SETUP` mới |
| `rsocket_active_connections` | Số RSocket session đang tồn tại |
| `rsocket_in_flight_interactions` | Số request đang chạy, gồm stream/channel chưa kết thúc |
| `rsocket_rejected_setups_total` | Số connection setup bị từ chối khi drain |
| `rsocket_rejected_requests_total` | Số interaction mới bị từ chối trên connection cũ |
| `rsocket_drain_duration_seconds` | Thời gian từ lúc bắt đầu drain đến khi listener đóng |
| `rsocket_drain_remaining_interactions` | Số request còn lại tại thời điểm drain deadline |

Ghi log các lần chuyển readiness, thời điểm đóng admission, số request còn hoạt động và lý do force close. Khi có nhiều instance, gắn instance ID và trace/correlation ID để xác định client còn kết nối vào node nào.

## 11. Kiểm thử health, readiness và admission

Không chỉ kiểm tra `/actuator/health` trả HTTP 200 khi ứng dụng mới khởi động. Hãy kiểm tra các trạng thái theo lifecycle:

| Kịch bản | Liveness | Readiness | Hành vi RSocket cần xác minh |
| --- | --- | --- | --- |
| Ứng dụng đang khởi động | Chưa live hoặc chưa probe | Refusing traffic | Chưa nhận SETUP mới |
| RSocket listener bind thành công | UP | Accepting traffic | SETUP và route health hoạt động |
| Dependency cục bộ bắt buộc chưa sẵn sàng | UP | Refusing traffic | Không nhận traffic nghiệp vụ |
| Dependency dùng chung tạm lỗi, có fallback | UP | Theo policy ứng dụng | Không restart hàng loạt instance |
| Instance bắt đầu drain | UP | Refusing traffic | SETUP mới bị từ chối |
| Client đã kết nối trước khi drain | UP | Refusing traffic | Interaction mới bị từ chối hoặc theo chính sách drain |
| Stream đang chạy khi drain | UP | Refusing traffic | Stream được chờ, kết thúc hoặc cancel theo deadline |
| Listener RSocket chết ngoài dự kiến | Có thể vẫn UP nếu process còn sống | Refusing traffic | Health indicator phát hiện listener không còn hoạt động |
| Drain deadline hết | UP cho tới khi process dừng | Refusing traffic | Listener đóng, connection còn lại bị cleanup |

Các test quan trọng:

1. Startup không chuyển readiness sang UP trước khi listener bind thành công.
2. Health indicator báo OUT_OF_SERVICE khi gate đóng.
3. Một client mới bị từ chối ở `SETUP` sau khi drain bắt đầu.
4. Client đã kết nối không thể mở interaction mới nếu request admission gate đã bật.
5. Request đang chạy trước drain vẫn được đếm và có thể hoàn tất.
6. Cancel stream làm giảm `inFlight` đúng một lần.
7. Một stream không complete không làm shutdown chờ vô hạn; drain deadline kết thúc theo chính sách.
8. Sau listener stop, readiness không quay lại UP cho tới khi listener bind lại thành công.
9. WebSocket test xác minh cả handshake mới và session đã upgrade trước khi shutdown.
10. Kubernetes preStop + TERM hoàn tất trong `terminationGracePeriodSeconds` ở môi trường gần production.

Nên có integration test chạy server thật và client RSocket thật để kiểm tra `SETUP`, persistent connection và request cancellation. Unit test cho gate không đủ để chứng minh transport đã từ chối kết nối đúng cách.

## 12. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
| --- | --- | --- |
| Pod `Ready` nhưng RSocket TCP không bind | Readiness chỉ dùng `readinessState` của Spring Boot | Thêm `rsocketAdmission` indicator kiểm tra listener |
| Management health UP nhưng main service lỗi | Management port tách khỏi transport chính | Kiểm tra listener RSocket trong custom health contributor |
| Liveness restart tất cả Pod khi database lỗi | Liveness phụ thuộc dependency dùng chung | Loại dependency ngoài khỏi liveness; đánh giá readiness/fallback |
| Pod unready nhưng client cũ vẫn gửi request | Persistent RSocket connection chưa bị đóng | Thêm request admission gate hoặc LEASE policy |
| Server nhận SETUP mới trong lúc drain | Readiness chỉ ảnh hưởng router | Kiểm tra gate ở `SocketAcceptor` |
| Shutdown mất nhiều phút | Request-stream/channel không complete | Đếm active interactions, đặt drain deadline và chính sách cancel |
| Client reconnect liên tục vào Pod đang drain | Lỗi setup bị retry ngay | Dùng backoff/jitter và cập nhật discovery/readiness |
| Pod bị SIGKILL trước khi drain xong | `preStop` + drain vượt grace period | Tăng grace period hoặc giảm drain deadline; đo từng pha |
| WebSocket session bị ngắt đột ngột | HTTP shutdown không có chính sách cho session dài hạn | Theo dõi session và thông báo reconnect/resume ở tầng ứng dụng |
| TCP probe báo khỏe nhưng route RSocket lỗi | TCP probe chỉ kiểm tra cổng mở | Thêm protocol health client hoặc test route chuyên dụng |

## 13. Checklist triển khai

- [ ] Liveness chỉ phát hiện lỗi nội bộ không thể tự phục hồi.
- [ ] Readiness xác minh RSocket listener và admission gate.
- [ ] Startup probe có ngân sách đủ cho startup thực tế.
- [ ] Actuator chỉ expose health endpoints cần thiết và được giới hạn truy cập.
- [ ] Readiness group có `readinessState` và health contributor RSocket.
- [ ] Management port riêng không tạo health check giả khi RSocket listener chết.
- [ ] Có gate từ chối RSocket `SETUP` mới khi instance drain.
- [ ] Có policy cho request mới trên persistent connection.
- [ ] Theo dõi active interactions và cancellation.
- [ ] Drain có deadline; long-lived stream có chính sách kết thúc/reconnect.
- [ ] Server listener chỉ dừng sau khi hết thời gian drain hoặc hết deadline.
- [ ] `terminationGracePeriodSeconds` đủ cho preStop, endpoint propagation và cleanup.
- [ ] WebSocket upgraded sessions được kiểm thử riêng.
- [ ] Client có retry/backoff phù hợp khi gặp rejected setup/request.
- [ ] Metrics ghi nhận listener, admission, active sessions, in-flight requests và drain duration.

Health check trả lời instance đang ở trạng thái nào; readiness quyết định router có nên gửi traffic mới tới instance; admission gate thực thi quyết định đó tại RSocket server. Khi kết hợp ba lớp với in-flight tracking và drain deadline, hệ thống có thể rolling update hoặc bảo trì mà giảm request lỗi, đồng thời tránh restart hàng loạt khi một dependency bên ngoài gặp sự cố.

## Tài liệu tham khảo

- [Spring Boot — Actuator Endpoints và Kubernetes Probes](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html)
- [Spring Boot — Application Availability và Readiness State](https://docs.spring.io/spring-boot/reference/features/spring-application.html)
- [Spring Boot — Graceful Shutdown](https://docs.spring.io/spring-boot/reference/web/graceful-shutdown.html)
- [Spring Boot 3.5 — `RSocketServer` lifecycle API](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/rsocket/server/RSocketServer.html)
- [Spring Boot 3.5 — `RSocketServerCustomizer`](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/rsocket/server/RSocketServerCustomizer.html)
- [RSocket Java 1.1.5 — `RSocketServer`](https://javadoc.io/static/io.rsocket/rsocket-core/1.1.5/io/rsocket/core/RSocketServer.html)
- [RSocket Java 1.1.5 — `SocketAcceptor`](https://javadoc.io/static/io.rsocket/rsocket-core/1.1.5/io/rsocket/SocketAcceptor.html)
- [RSocket Java 1.1.5 — `SocketAcceptorInterceptor`](https://javadoc.io/static/io.rsocket/rsocket-core/1.1.5/io/rsocket/plugins/SocketAcceptorInterceptor.html)
- [RSocket Java 1.1.5 — `RSocketProxy`](https://javadoc.io/static/io.rsocket/rsocket-core/1.1.5/io/rsocket/util/RSocketProxy.html)
- [RSocket Java 1.1.5 — `RequestInterceptor`](https://javadoc.io/static/io.rsocket/rsocket-core/1.1.5/io/rsocket/plugins/RequestInterceptor.html)
- [RSocket Java 1.1.5 — `RejectedSetupException`](https://javadoc.io/static/io.rsocket/rsocket-core/1.1.5/io/rsocket/exceptions/RejectedSetupException.html)
- [RSocket Java 1.1.5 — `RejectedException`](https://javadoc.io/static/io.rsocket/rsocket-core/1.1.5/io/rsocket/exceptions/RejectedException.html)
- [Kubernetes — Liveness, Readiness, and Startup Probes](https://kubernetes.io/docs/concepts/workloads/pods/probes/)
- [Kubernetes — Pod Termination](https://kubernetes.io/docs/concepts/workloads/pods/pod-termination/)
- [Kubernetes — Container Lifecycle Hooks](https://kubernetes.io/docs/concepts/containers/container-lifecycle-hooks/)
