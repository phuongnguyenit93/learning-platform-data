# Đóng SSE, WebSocket và các luồng phản hồi dài hạn khi Spring Boot dừng có kiểm soát

> **Module:** Spring Boot - web-runtime · **Nhóm:** Dừng có kiểm soát. Bài học hướng dẫn đóng đúng vòng đời **Server-Sent Events (SSE)**, **WebSocket (raw và STOMP)**, **StreamingResponseBody**, `ResponseBodyEmitter`/`DeferredResult` và các luồng **WebFlux/reactive** trong quá trình deploy, rolling restart, autoscaling, pod termination hoặc shutdown service. Mục tiêu không chỉ là JVM thoát: phải ngăn kết nối mới, cho client biết cách chuyển hướng hoặc kết nối lại, giải phóng subscriptions/tasks/buffers, không để process chờ vô hạn và không làm mất sự kiện nghiệp vụ không thể khôi phục. Ví dụ dùng **Java 17+**, **Spring Boot 4.1.2**, Spring MVC/Tomcat, Actuator readiness, `SseEmitter`, raw WebSocket, cùng các phép thử với cURL, browser, SIGTERM và Kubernetes.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt **graceful shutdown của embedded HTTP server**, **ứng dụng chủ động drain phiên**, **protocol close handshake** và **process termination**; hiểu vì sao chúng không tự động thay thế nhau.
2. Mô tả trạng thái shutdown: **RUNNING → DRAINING → CLOSING → TERMINATED**, thứ tự cập nhật readiness, chặn luồng mới, thông báo clients, dừng producers, chờ công việc hợp lệ và đóng transport.
3. Dùng `spring.lifecycle.timeout-per-shutdown-phase`, `server.shutdown`, `ReadinessState.REFUSING_TRAFFIC`, readiness probes và Kubernetes `preStop`/`terminationGracePeriodSeconds`.
4. Quản lý vòng đời `SseEmitter`: `onCompletion`/`onTimeout`/`onError`, gửi sự kiện `server-draining` nếu có thể, `complete()` đúng trường hợp, heartbeat phát hiện client đã mất kết nối, cleanup registry idempotent.
5. Đóng raw WebSocket bằng `WebSocketSession.close(CloseStatus.GOING_AWAY)` (**close code 1001**) và giải phóng session state; phân biệt close frame, lỗi mạng và ý nghĩa `SessionDisconnectEvent` trong STOMP.
6. Dừng `StreamingResponseBody`/phản hồi chunked bằng cancellation token, executor có giới hạn, completion/cleanup; hiểu giới hạn sau khi HTTP response đã commit.
7. Với WebFlux, liên kết vòng đời `Flux`/`Mono` với cancellation, `doFinally`/`takeUntilOther`/`WebSocketSession.close(...)` và bảo đảm không có hot publishers/connection queues giữ process sống.
8. Xây và chạy project Spring Boot MVC minh họa: SSE, WebSocket, phản hồi streaming, endpoint drain dùng nội bộ, readiness và callback khi context đóng.
9. Thiết kế client reconnect có backoff+jitter, id/cursor/Last-Event-ID/replay, tránh reconnect storm và không hứa đảm bảo delivery chỉ vì đã ghi terminal event.
10. Kiểm tra hành vi thật dưới SIGTERM, client chậm, proxy/LB, timeout/force kill và đo active streams, dropped events, close reasons, drain duration.

## 2. Tại sao kết nối dài khiến graceful shutdown khó hơn REST thông thường?

Một REST request ngắn có thể kết thúc trong vài chục mili giây. Trong khi đó:

- **SSE** giữ response `text/event-stream` mở hàng phút/giờ để phát liên tục.
- **WebSocket** nâng cấp HTTP thành kênh hai chiều tồn tại lâu; thông thường không có HTTP response kết thúc theo từng message.
- **STOMP over WebSocket** còn có broker, subscriptions, queues, heartbeats, session lifecycle.
- **StreamingResponseBody**, NDJSON, file export, gRPC streaming hoặc reactive `Flux` có thể trả bytes trong một khoảng rất dài.
- Streaming output có thể đang bị **backpressure** bởi client chậm hoặc proxy, không thể coi hoàn tất sau khi controller return.

~~~text
Load balancer / Kubernetes Service
             |
        Spring Boot pod A
             |
       +-----+-----+--------------------+
       |           |                    |
     REST         SSE                 WebSocket
     40 ms     2 giờ mở                1 giờ mở
       |           |                    |
       v           v                    v
  thường xong   cần chủ động           cần close frame
  trước grace   thông báo/complete      + cleanup session
             |
    Deployment SIGTERM / drain
             |
             v
  Nếu chỉ "chờ tất cả request kết thúc":
    SSE và streaming có thể KHÔNG tự kết thúc kịp grace
~~~

Điều quan trọng: **graceful shutdown không đồng nghĩa “giữ mọi WebSocket/SSE cho tới khi chúng tự đóng”**. Một kết nối dài có thể kéo dài mãi; thời gian cho phép của server, container và orchestrator luôn hữu hạn. Khi hết hạn, process có thể bị buộc dừng trước khi gửi xong thông điệp cuối.

### 2.1. Bốn tầng đóng kết nối

| Tầng | Ví dụ | Có thể bảo đảm gì? |
| --- | --- | --- |
| Application admission control | `draining=true`, từ chối stream mới | Không tạo thêm long-lived work trên instance cũ |
| Protocol signaling | SSE terminal event, WebSocket close 1001, app control frame | **Cố gắng** nói với client phải chuyển sang kết nối khác |
| Transport/server lifecycle | Embedded Tomcat/Jetty/Netty graceful stop | Ngăn requests mới và cho in-flight work thời gian hoàn tất |
| Process/orchestrator | SIGTERM, grace period, SIGKILL | Đặt deadline cuối; không bảo đảm client nhìn thấy thông điệp |

Để đóng đúng, cần phối hợp **tất cả các tầng**. Một webhook `preStop` chỉ đóng WebSocket mà không hạ readiness có thể bị LB chuyển thêm clients mới vào pod cũ. Ngược lại, hạ readiness nhưng không kết thúc SSE/WS đã thiết lập có thể khiến các kết nối đó chiếm tài nguyên đến hết thời hạn.

### 2.2. Đóng HTTP response khác với đóng WebSocket

- **HTTP response bình thường:** commit headers/status, ghi body, kết thúc body/connection theo HTTP semantics.
- **SSE:** là HTTP response streaming; `SseEmitter.complete()` kết thúc stream thành công qua async completion, nhưng điều đó không phải application-level ACK rằng browser đã xử lý event cuối.
- **WebSocket:** sau HTTP 101 upgrade, hai bên trao đổi WebSocket frames; `session.close(status)` gửi close handshake theo khả năng transport. Không có HTTP 200/503 mới cho chính WebSocket session đã nâng cấp.
- **STOMP:** là subprotocol chạy **trong** WebSocket; client có thể gửi STOMP `DISCONNECT`, còn một WebSocket close hoặc mất mạng cũng có thể phát sinh SessionDisconnectEvent phía Spring.
- **NDJSON/file streaming:** client có thể nhận một phần body và bị ngắt; checksum, cursor, Range hoặc job status là trách nhiệm application protocol.

## 3. Spring Boot 4.1.2 graceful shutdown thực sự làm gì?

Theo tài liệu Spring Boot 4.1, graceful shutdown đã **được bật mặc định** với embedded **Tomcat, Jetty và Reactor Netty**, cả Servlet và reactive. Nó xảy ra trong lúc đóng application context, ở giai đoạn sớm của việc stop `SmartLifecycle` beans. Trong khoảng grace, server cố không nhận **requests mới** và cho các requests hiện tại hoàn thành.

Đặt rõ policy để người đọc biết timeout:

~~~properties
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=20s
~~~

- `server.shutdown=graceful` ở đây là khai báo tường minh; ở Boot 4.1 nó thường đã là mặc định.
- `spring.lifecycle.timeout-per-shutdown-phase=20s` là thời gian timeout cho **mỗi shutdown phase**, **không** là bảo đảm “toàn bộ process luôn thoát sau đúng 20 giây” hay “mọi kết nối dài chắc chắn tự đóng sau 20 giây”.
- Có thể dùng `server.shutdown=immediate` để vô hiệu graceful shutdown trong trường hợp thực sự cần, nhưng không nên dùng để khắc phục một stream không chịu kết thúc.
- Embedded server có thể từ chối requests mới ở network layer hoặc bằng hành vi khác tùy connector và keep-alive; **không hardcode mọi request mới phải nhận HTTP 503**.
- Một shutdown bằng nút **Stop** trong IDE có thể giết process không theo đúng SIGTERM/graceful behavior; kiểm bằng process signal ở môi trường gần production.

**Điểm giới hạn:** tài liệu graceful shutdown của embedded web server **không hứa mọi SSE/WebSocket có ứng dụng producer riêng sẽ được dừng đúng ngữ nghĩa nghiệp vụ**. Server có thể ngừng nhận connections mới, nhưng producer, broker subscriptions, raw WebSocket sessions, async tasks và custom queues vẫn cần vòng đời rõ trong ứng dụng.

### 3.1. Không nhầm `timeout-per-shutdown-phase` với async request timeout

Những timeout khác nhau:

| Timeout | Áp vào đâu? | Dễ nhầm |
| --- | --- | --- |
| `spring.lifecycle.timeout-per-shutdown-phase` | Stop lifecycle beans khi context đóng | Không phải request idle timeout |
| `spring.mvc.async.request-timeout` | Servlet MVC async request handling | Không phải tổng Kubernetes grace period |
| `new SseEmitter(timeoutMs)` | Một SSE response cụ thể | Không tự kích hoạt server drain |
| WebSocket idle timeout | Kết nối không hoạt động | Không tự đóng mọi phiên khi deploy |
| STOMP heartbeat | Phát hiện peer không đáp ứng | Không phải delivery ACK hay drain |
| Reverse proxy/LB idle timeout | Kết nối ở biên | Có thể ngắt trước app |
| Kubernetes `terminationGracePeriodSeconds` | Tổng thời gian pod được hoàn tất trước force kill | Bao gồm cả preStop hook |

Thứ tự và giá trị phải **tương thích**. Nếu ứng dụng cho phép 30 giây drain nhưng Kubernetes chỉ có 10 giây tổng thời gian, pod vẫn có thể bị SIGKILL trước. Ngược lại, đặt mọi timeout thành vô hạn sẽ khiến termination không hoàn tất.

## 4. Quy trình drain-first phù hợp rolling deployment

Một kịch bản khuyến nghị:

~~~text
RUNNING
   |
   | 1. Nhận yêu cầu drain (deploy/preStop/admin)
   v
DRAINING
   |
   +-- readiness = REFUSING_TRAFFIC
   +-- chặn SSE/WebSocket/long stream mới (kể cả race trong admission)
   +-- dừng tạo new jobs/publish vào sessions cũ
   +-- cố gửi terminal control event tới SSE/STOMP clients
   +-- WebSocket close 1001 (going away)
   +-- SSE complete(), stream cancellation token -> cleanup
   +-- chờ finite in-flight critical work hoặc handoff
   v
CLOSING
   |
   +-- SIGTERM / application context close
   +-- Boot graceful shutdown / lifecycle timeout
   +-- stop background workers / close broker clients/resources
   v
TERMINATED
   |
   +-- remaining work phải dựa vào durable state/replay
~~~

**Trật tự chính xác có thể khác tùy platform và version**, nhưng các invariants cần giữ:

1. Từ lúc vào `DRAINING`, request mới không tạo phiên dài mới.
2. Việc drain có thể gọi nhiều lần mà không tạo nhiều terminal events, không double-remove và không ném lỗi chỉ vì session đã đóng.
3. Mỗi session đã được đăng ký có callback cleanup ở close/timeout/error.
4. Có deadline tổng: nếu một client đọc chậm, không chờ nó vô hạn.
5. Sau đóng kết nối, client có cách lấy lại trạng thái bị mất từ lưu trữ bền hoặc snapshot.

### 4.1. Readiness khác liveness

- **Readiness:** instance có nhận **traffic mới** không? Khi drain, chuyển sang `ReadinessState.REFUSING_TRAFFIC`.
- **Liveness:** process đang hoạt động đúng hay cần restart? Không cố chuyển liveness thành BROKEN chỉ vì đang draining.
- **Startup:** chưa sẵn sàng nhận traffic là trạng thái bình thường trong giai đoạn boot, không phải liveness failure.

Spring Boot có `AvailabilityChangeEvent.publish(context, ReadinessState.REFUSING_TRAFFIC)`. Kubernetes readiness probe có thể đọc `/actuator/health/readiness` nếu đã bật probes và endpoint truy cập được. Tuy nhiên readiness propagation qua Service/LB/Ingress **không đồng bộ tức thì**; các connections đang tồn tại thường không tự chuyển sang pod khác khi readiness giảm.

### 4.2. Race giữa việc mở stream mới và drain

Kiểm tra một lần:

~~~java
if (!draining) {
    registerLongLivedSession();
}
~~~

vẫn có race: sau khi thread đọc `draining=false`, thread khác bật draining rồi snapshot sessions để đóng, request đầu mới đăng ký sau snapshot và có thể bị **bỏ sót**.

Cần **admission check trước và sau đăng ký**, hoặc một cơ chế lock/gate bảo đảm atomicity. Bản lab dùng `AtomicBoolean`, concurrent sets/maps và kiểm lần hai sau khi thêm. Production có thể dùng state machine/lock và session ownership có kiểm soát.

### 4.3. Drain endpoint không được là cửa hậu public

Trong lab có thể gọi `POST /internal/drain` từ localhost. Production phải bảo vệ bằng management plane, auth/RBAC, network policies, mTLS hoặc sidecar local IPC và có audit. Nếu public client có thể gọi endpoint drain, họ có thể liên tục ngắt toàn bộ người dùng (denial of service).

Đừng dùng một GET URL public để gây side-effect shutdown. Việc hạ readiness chưa stop process; cần bước triển khai/orchestrator tiếp theo để gửi SIGTERM đúng cách.

## 5. SSE: đúng semantics của `SseEmitter`

Trong Spring MVC, `SseEmitter` kế thừa `ResponseBodyEmitter`. Controller có thể trả emitter rồi gửi events từ thread khác; response ở chế độ Servlet async và vẫn đang mở.

~~~java
// Fragment trong Spring MVC @RestController.
@GetMapping(path = "/events", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
public SseEmitter events() {
    SseEmitter emitter = new SseEmitter(180_000L);
    // Đăng ký vào registry, thiết lập callbacks và gửi từ thread khác.
    return emitter;
}
~~~

**Các callbacks cần biết:**

- `emitter.onCompletion(Runnable)`: được gọi khi async request complete, kể cả một số đường error/timeout; dùng để bỏ session khỏi registry.
- `emitter.onTimeout(Runnable)`: xử lý timeout; không giữ emitter trong registry.
- `emitter.onError(Consumer<Throwable>)`: xử lý lỗi container/async; cleanup và telemetry.
- `emitter.complete()`: ứng dụng yêu cầu hoàn tất response bình thường; Spring hoàn thiện async handling/dispatch, **không** là delivery ACK.
- `emitter.completeWithError(Throwable)`: ứng dụng báo error với async handling; **không** dùng bừa khi I/O đã báo remote disconnect.

### 5.1. Gửi event kết thúc trước khi complete

Một event SSE điều khiển có thể là:

~~~text
event: server-draining
data: reconnect
retry: 3000

~~~

Đây là **định dạng SSE hợp lệ** để browser nhận `server-draining` và có chỉ thị retry. Nhưng:

- Nếu browser đang mất mạng hoặc proxy buffer, nó **có thể không thấy event cuối**.
- Việc `send(...)` trả về **không có nghĩa JS đã xử lý**; TCP/HTTP buffers vẫn còn.
- Nếu HTTP headers/body đã commit, server không thể đổi status sang HTTP 503 để biểu thị drain.
- Nếu muốn giữ dữ liệu đúng đắn qua ngắt kết nối, phải có `id:` của **business event**, retention và replay.

Cách gửi Spring MVC:

~~~java
// Fragment, yêu cầu emitter đang còn active.
emitter.send(SseEmitter.event()
        .name("server-draining")
        .data("reconnect")
        .reconnectTime(3000L));
emitter.complete();
~~~

### 5.2. Error khi client mất kết nối

Tài liệu Spring MVC nêu rõ Servlet API **không có callback tức thì đáng tin khi peer biến mất**. Thông thường chỉ phát hiện khi **ghi dữ liệu tiếp** bị lỗi I/O. Vì vậy cần heartbeat/comment events định kỳ và callback cleanup.

Với `SseEmitter.send(...)` ném `IOException` do remote đã mất kết nối, **không** gọi `complete()` hay `completeWithError(...)` ngay trong catch một cách máy móc: Spring/Servlet container sẽ xử lý AsyncListener error notification và hoàn tất luồng lỗi. Ứng dụng nên remove registry entry, log gọn và tránh double-complete.

~~~java
// Fragment từ task phát SSE.
try {
    emitter.send(SseEmitter.event().comment("heartbeat"));
}
catch (IOException disconnected) {
    activeEmitters.remove(emitter);
    // Không completeWithError ở nhánh IOException: container xử lý lỗi.
}
~~~

Heartbeat giúp phát hiện disconnect và giữ một số proxy không idle-timeout, **không bảo đảm client đã parse/business-ACK events** và có thể không đủ khi mạng/proxy đã treo. Đặt interval theo proxy policies.

### 5.3. EventSource sẽ tự reconnect nếu không được kiểm soát

Browser `EventSource` mặc định có cơ chế reconnect khi stream chấm dứt bất thường. Nếu pod đang drain và liên tục từ chối kết nối mới, client có thể tạo **reconnect storm**. Khi nhận sự kiện `server-draining`, client có thể `EventSource.close()`, chờ backoff+jitter rồi nối lại qua hostname/load balancer tới instance mới.

Nếu client **không** nhận terminal event, nó cần handle `onerror`, trạng thái mạng và retry không đồng loạt. Một số phản hồi HTTP như 204 hoặc các lỗi status có semantics riêng với EventSource; đừng giả định browser luôn retry sau mọi HTTP status. Kiểm behavior theo trình duyệt và EventSource spec.

### 5.4. Last-Event-ID và replay

Ví dụ server phát:

~~~text
id: 101
event: order-updated
data: {"orderId":"o-1","state":"processing"}

id: 102
event: order-updated
data: {"orderId":"o-1","state":"completed"}

~~~

Nếu kết nối cắt sau event 101, client có thể reconnect và gửi header `Last-Event-ID: 101`. Nhưng **Spring không tự lưu events** trong `SseEmitter`; server phải có durable event log/cursor và biết replay đúng thứ tự, tenant, quyền truy cập, retention, deduplication.

Không dùng timestamp millisecond từ nhiều pods làm sequence liên tục nếu không có ordering contract. Nếu ứng dụng chỉ phát trạng thái mới nhất, client có thể gọi REST snapshot sau reconnect thay vì replay từng transition.

## 6. WebSocket: đóng bằng frame và dọn state

WebSocket sau handshake HTTP 101 là một connection độc lập về mặt ứng dụng. Khi server shutdown, nó có thể gọi:

~~~java
// Fragment trong lớp quản lý raw WebSocket session.
if (session.isOpen()) {
    session.close(CloseStatus.GOING_AWAY);
}
~~~

Trong Spring WebSocket, `CloseStatus.GOING_AWAY` là **1001**, phù hợp khi server “going away” vì restart/điều hướng. Code **1000** là normal closure khi nhiệm vụ được hoàn thành; **1006** là mã reserved, không được gửi như close frame. Không nhầm close code 1012 từ các registry khác với hằng số Spring hiện có mà không kiểm version.

### 6.1. Close handshake không phải cam kết delivery

Một đường đi bình thường:

~~~text
Server muốn dừng
   |
   +-- (tùy) gửi app control message "server-draining"
   |
   +-- WebSocket close frame code=1001
   |
   <--- client close frame (nếu nhận/đáp ứng)
   |
   +-- underlying TCP close / resource cleanup
~~~

Mạng có thể đứt trước khi client nhận frame. Một socket bị SIGKILL có thể khiến browser báo abnormal close, code **1006** (observed locally), không phải server chủ động gửi 1006.

Không dùng một lời gọi `session.close(...)` để chứng minh messages trước đó đã được browser xử lý. Với payment/order, cần ACK/replay riêng.

### 6.2. Registry và cleanup

Một raw `TextWebSocketHandler` có callbacks:

- `afterConnectionEstablished(WebSocketSession)`: đăng ký session, từ chối bằng close nếu draining.
- `afterConnectionClosed(WebSocketSession, CloseStatus)`: xóa session khỏi registry và cleanup resources.
- `handleTransportError(WebSocketSession, Throwable)`: quan sát lỗi, cleanup.
- `handleTextMessage(...)`: xử lý app messages; không enqueue thêm work nếu draining.

Dùng concurrent registry theo session ID, remove **idempotent** vì error/close/drain có thể chạy đồng thời. Nếu một session có background subscription, timer, broker consumer hoặc queue riêng, phải hủy những resources này; xóa khỏi Map không tự động hủy upstream producer.

### 6.3. Không trộn WebSocket và STOMP DISCONNECT

Trong STOMP over WebSocket:

- Client thường gửi STOMP `DISCONNECT`, có thể sử dụng `receipt` nếu broker hỗ trợ.
- Khi WebSocket bị đóng không gửi STOMP DISCONNECT, Spring vẫn có thể phát `SessionDisconnectEvent`.
- Theo tài liệu, **SessionDisconnectEvent có thể được publish nhiều hơn một lần cho cùng một session**; cleanup listener phải idempotent.
- Spring STOMP simple broker giữ subscriptions trong memory; sau disconnect chúng không tự có durable replay.
- Nếu dùng broker relay, đóng client WebSocket không nhất thiết đóng ngay external broker/system connection; broker listener lifecycle/ack policy là chuyện riêng.

Nếu muốn client STOMP chủ động chuyển pod, có thể publish **một app-level message** trên topic riêng để báo drain, chờ khoảng hợp lý rồi cho framework đóng WebSocket. Tuy nhiên broker/send buffer có thể chậm; không bảo đảm message drain đến mọi subscriber trước close.

### 6.4. Client WebSocket reconnect

Browser client thường xử lý:

~~~javascript
socket.onclose = event => {
  if (event.code === 1001) {
    console.log("Server going away; reconnect with backoff");
  }
  // Mọi close/error path đều cần bounded retry và state reconciliation.
};
~~~

Dùng exponential backoff + jitter, limit retry, authentication refresh nếu cần và **re-subscribe** sau khi kết nối mới thành công. Không hardcode reconnect ngay liên tục khi 10.000 clients cùng mất socket. Với STOMP subscriptions, client cần đăng ký lại sau reconnect theo cấu trúc ứng dụng.

## 7. StreamingResponseBody, NDJSON và các phản hồi HTTP dài

Spring MVC `StreamingResponseBody` trả callback ghi vào `OutputStream` trên một thread async; dù controller đã return, request vẫn chưa xong.

~~~java
// Fragment trong MVC controller; truyền cancellation token có lifecycle rõ.
@GetMapping("/slow")
public StreamingResponseBody slow() {
    return out -> {
        for (int i = 0; i < 60 && !draining.get(); i++) {
            out.write(("part-" + i + "\n").getBytes(StandardCharsets.UTF_8));
            out.flush();
            try {
                Thread.sleep(1000);
            }
            catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
                break;
            }
        }
    };
}
~~~

Đây là **fragment**, không có field `draining` khai báo; ví dụ chạy được ở mục 11. Điều quan trọng là kiểm cancellation flag giữa các chunks, giữ số chunks và thời gian hữu hạn, xử lý interrupt và chắc chắn cleanup trong `finally`.

### 7.1. Sau khi response đã commit

Một phản hồi 200 streaming có thể đã gửi headers và 100 chunks. Khi server dừng trước chunk 101, nó **không thể quay lại thay status thành 503** hay “rollback” bytes đã gửi. Client phải có:

- Checksum/length/trailer hoặc kết thúc ứng dụng rõ ràng.
- Sequence/cursor để tải tiếp.
- HTTP Range/206 khi là file hỗ trợ resume, cùng ETag/version.
- Với export jobs, tách **job completion** khỏi kết nối download; lưu artifact bền và cho client polling/download lại.

Không coi “server đóng socket” luôn có nghĩa response đã thành công. Chunked HTTP/1.1 có end marker; abnormal truncation có thể khiến client báo I/O error, nhưng app-level data integrity vẫn cần hợp đồng rõ.

### 7.2. Executor và dừng producers

Spring MVC streaming có thể dùng blocking I/O trên `AsyncTaskExecutor`. Nếu có 1.000 streams nhưng pool chỉ có 8 threads, phần còn lại có thể bị queue/reject theo cấu hình. Không dùng unbounded queues hoặc cứ tăng threads để giữ streams vĩnh viễn. Khi drain:

1. Không nhận thêm stream mới.
2. Phát cancellation signal tới producers.
3. Cho chunk đã ghi hoàn tất trong deadline.
4. Đóng/cancel công việc upstream và giữ state để resumable.
5. Đợi số stream active về 0 hoặc hết thời gian được phép.
6. Không giữ request executor sống vô hạn chỉ vì một client không đọc.

Với Spring MVC `DeferredResult`, khi cần dừng có thể gọi `setResult`/`setErrorResult` nếu request chưa hoàn tất, cùng `onCompletion`/`onTimeout`; đừng kết thúc kết quả đã được set. Với `ResponseBodyEmitter`, dùng `complete()` hoặc error path đúng như SSE.

### 7.3. Không ghi bất tận trong drain

Nếu thread đang block ở socket write, kiểm `draining.get()` ở đầu vòng lặp **không có cơ hội chạy** cho đến khi write trở về. Cần network I/O timeout/proxy/connector policy, bounded producer queues và shutdown deadline. Không bảo đảm một flag Java sẽ cắt ngay một kernel write đang block.

## 8. Ví dụ chạy được: Spring Boot 4.1.2 MVC với SSE, WebSocket và drain

Demo có các endpoints:

| Endpoint | Chức năng |
| --- | --- |
| `GET /events` | SSE giữ mở và nhận heartbeat; cuối phiên có thể nhận `server-draining` |
| `GET /ws` | Raw WebSocket handshake, server lưu session; drain gửi Close 1001 |
| `GET /slow-stream` | HTTP response text dài tối đa 120 chunks, mỗi giây một chunk |
| `POST /internal/drain` | Chuyển readiness, chặn stream mới, cố gửi terminal SSE và đóng sockets |
| `GET /internal/status` | Trả JSON số sessions/streams và trạng thái drain |
| `GET /actuator/health/readiness` | Readiness probe ở Spring Boot khi bật probes |
| `GET /demo.html` | Browser client xem SSE và raw WebSocket |

**Phạm vi:** demo localhost, không có authentication và không có durable event log. Không deploy công khai; endpoint drain phải bị chặn ở management/control plane production. Demo chứng minh **lifecycle** chứ không cam kết event delivery.

### 8.1. Cấu trúc project

~~~text
long-lived-shutdown-lab/
  pom.xml
  src/main/java/com/example/longshutdown/
    LongShutdownApplication.java
    StreamRegistry.java
    LiveController.java
    RawSocketHandler.java
    WebSocketConfig.java
    AsyncMvcConfig.java
  src/main/resources/
    application.properties
    static/demo.html
~~~

### 8.2. pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>4.1.2</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>long-lived-shutdown-lab</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-websocket</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-actuator</artifactId>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

`spring-boot-starter-websocket` của Boot 4.1.2 cung cấp Spring MVC WebSocket support, bao gồm Servlet MVC cần cho controller và raw WebSocket handler. Actuator cung cấp readiness endpoint; không cần thêm WebFlux starter cho demo blocking MVC. Nếu sử dụng WebFlux/Netty, dùng project cấu hình tương ứng, không mix API Servlet vào server reactive.

### 8.3. application.properties

~~~properties
# Lab chỉ lắng nghe localhost, KHÔNG cho truy cập từ Internet.
server.address=127.0.0.1
server.port=8080

# Boot 4 đã graceful mặc định; khai rõ để học.
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=20s

# Async Servlet write có deadline riêng.
spring.mvc.async.request-timeout=180s

# Health/readiness, chỉ expose mức cần cho demo.
management.endpoint.health.probes.enabled=true
management.endpoints.web.exposure.include=health,info

# Không log raw messages/headers.
logging.level.com.example.longshutdown=INFO
~~~

**Quan trọng:** Khi đưa lên Kubernetes, không thể giữ `server.address=127.0.0.1` mà mong readiness traffic bên ngoài pod hoạt động như deployment chuẩn. Lab cố ý bind loopback; production cấu hình listener và management network theo cluster, kết hợp auth/network policies.

### 8.4. LongShutdownApplication.java

~~~java
package com.example.longshutdown;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.scheduling.annotation.EnableScheduling;

@SpringBootApplication
@EnableScheduling
public class LongShutdownApplication {

    public static void main(String[] args) {
        SpringApplication.run(LongShutdownApplication.class, args);
    }
}
~~~

`@EnableScheduling` kích hoạt heartbeat gửi comment SSE định kỳ trong StreamRegistry. Trong production, một scheduler single-thread bị block bởi một slow client có thể ảnh hưởng các clients khác; xem mục 13 để thiết kế writer/queue riêng.

### 8.5. StreamRegistry.java

~~~java
package com.example.longshutdown;

import java.io.IOException;
import java.util.List;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.boot.availability.AvailabilityChangeEvent;
import org.springframework.boot.availability.ReadinessState;
import org.springframework.context.ApplicationContext;
import org.springframework.context.event.ContextClosedEvent;
import org.springframework.context.event.EventListener;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;
import org.springframework.web.socket.CloseStatus;
import org.springframework.web.socket.WebSocketSession;

@Component
public class StreamRegistry {

    private final AtomicBoolean draining = new AtomicBoolean(false);
    private final Set<SseEmitter> emitters = ConcurrentHashMap.newKeySet();
    private final ConcurrentMap<String, WebSocketSession> sockets =
            new ConcurrentHashMap<>();
    private final AtomicInteger activeHttpStreams = new AtomicInteger();
    private final ApplicationContext applicationContext;

    public StreamRegistry(ApplicationContext applicationContext) {
        this.applicationContext = applicationContext;
    }

    public boolean isDraining() {
        return draining.get();
    }

    public int sseCount() {
        return emitters.size();
    }

    public int websocketCount() {
        return sockets.size();
    }

    public int longStreamCount() {
        return activeHttpStreams.get();
    }

    public void streamStarted() {
        activeHttpStreams.incrementAndGet();
    }

    public void streamFinished() {
        activeHttpStreams.decrementAndGet();
    }

    public SseEmitter registerSse() {
        if (draining.get()) {
            return null;
        }

        SseEmitter emitter = new SseEmitter(180_000L);
        emitter.onCompletion(() -> emitters.remove(emitter));
        emitter.onTimeout(() -> emitters.remove(emitter));
        emitter.onError(error -> emitters.remove(emitter));
        emitters.add(emitter);

        // Kiểm lại để không bỏ sót phiên mở song song với drain.
        if (draining.get()) {
            emitters.remove(emitter);
            emitter.complete();
            return null;
        }
        return emitter;
    }

    public void registerWebSocket(WebSocketSession session)
            throws IOException {
        if (draining.get()) {
            session.close(CloseStatus.GOING_AWAY);
            return;
        }

        sockets.put(session.getId(), session);

        // Nếu drain đã xảy ra ngay sau thao tác put.
        if (draining.get() &&
                sockets.remove(session.getId(), session)) {
            session.close(CloseStatus.GOING_AWAY);
        }
    }

    public void unregisterWebSocket(WebSocketSession session) {
        sockets.remove(session.getId(), session);
    }

    @Scheduled(fixedDelay = 5_000)
    public void heartbeat() {
        if (draining.get()) {
            return;
        }
        for (SseEmitter emitter : emitters) {
            if (draining.get()) {
                return;
            }
            try {
                // Comment SSE: client bỏ qua nội dung, proxy thấy data.
                emitter.send(SseEmitter.event().comment("heartbeat"));
            }
            catch (IOException disconnected) {
                // Servlet container xử lý async error path.
                emitters.remove(emitter);
            }
        }
    }

    public boolean drain() {
        if (!draining.compareAndSet(false, true)) {
            return false;
        }

        AvailabilityChangeEvent.publish(
                applicationContext, ReadinessState.REFUSING_TRAFFIC);

        for (SseEmitter emitter : List.copyOf(emitters)) {
            try {
                emitter.send(SseEmitter.event()
                        .name("server-draining")
                        .data("reconnect")
                        .reconnectTime(3000L));
                emitter.complete();
            }
            catch (IOException | IllegalStateException cannotSend) {
                // Có thể peer đã rời đi. Không completeWithError sau
                // IOException từ Servlet write: container xử lý.
            }
            finally {
                emitters.remove(emitter);
            }
        }

        for (WebSocketSession session : List.copyOf(sockets.values())) {
            try {
                if (session.isOpen()) {
                    session.close(CloseStatus.GOING_AWAY);
                }
            }
            catch (IOException cannotClose) {
                // Peer có thể đã mất mạng. Ghi metric/log có giới hạn
                // nếu đây là một app production.
            }
            finally {
                sockets.remove(session.getId(), session);
            }
        }
        return true;
    }

    @EventListener(ContextClosedEvent.class)
    public void onContextClosed() {
        // Fallback nếu môi trường gửi SIGTERM mà không gọi /internal/drain.
        // Delivery terminal event chỉ best-effort, không là ACK.
        drain();
    }
}
~~~

**Phân tích kỹ concurrency:**

- `AtomicBoolean.compareAndSet(false,true)` làm drain **idempotent**; nhiều requests drain chỉ lần đầu thực hiện đóng.
- `ConcurrentHashMap.newKeySet()` và concurrent map cho phép callbacks xóa phiên đồng thời với drain.
- Kiểm `draining` **sau** khi register tránh phiên lọt vào registry sau snapshot của drain.
- `onCompletion`/`onTimeout`/`onError` đều remove; operation remove là idempotent.
- `List.copyOf(emitters)` tạo snapshot để iterate khi callback đồng thời remove.
- Nếu SSE send ném IOException, **không** gọi `completeWithError`/`complete` trong catch; Spring MVC sẽ nhận async error từ container. Nếu send thành công thì gọi `complete()` để request có cơ hội hoàn tất.
- WebSocket gọi `close(CloseStatus.GOING_AWAY)` và remove trong finally, ngay cả khi client đã đóng. Callback afterConnectionClosed có thể remove lại an toàn.
- `@EventListener(ContextClosedEvent.class)` là **fallback**: điều kiện context close không bảo đảm mọi event sẽ đến peer hoặc mọi appender/broker còn sẵn; production cần chủ động drain **trước** SIGTERM khi nền tảng hỗ trợ.
- Heartbeat ở đây gửi tuần tự trên một scheduler, phù hợp **lab ít clients**. Production không nên để một client block quá lâu làm delay heartbeat của mọi clients.
- `activeHttpStreams` là số callback StreamingResponseBody đã bắt đầu chạy, không phải tổng số HTTP requests/response bytes; số liệu real production cần phân biệt streams đã accepted nhưng chưa được thread pool schedule.

### 8.6. RawSocketHandler.java

~~~java
package com.example.longshutdown;

import org.springframework.stereotype.Component;
import org.springframework.web.socket.CloseStatus;
import org.springframework.web.socket.WebSocketSession;
import org.springframework.web.socket.handler.TextWebSocketHandler;

@Component
public class RawSocketHandler extends TextWebSocketHandler {

    private final StreamRegistry registry;

    public RawSocketHandler(StreamRegistry registry) {
        this.registry = registry;
    }

    @Override
    public void afterConnectionEstablished(WebSocketSession session)
            throws Exception {
        registry.registerWebSocket(session);
    }

    @Override
    public void afterConnectionClosed(
            WebSocketSession session, CloseStatus status) {
        registry.unregisterWebSocket(session);
    }

    @Override
    public void handleTransportError(
            WebSocketSession session, Throwable exception) {
        registry.unregisterWebSocket(session);
    }
}
~~~

Handler không echo messages vì bài tập trung vào **đóng phiên**. Nếu bạn thêm background producers hoặc trả lời messages, phải đảm bảo chúng không gửi song song vào cùng raw WebSocket session, có bounded queue/send time limit; khi drain dừng producers trước khi close. Có thể dùng `ConcurrentWebSocketSessionDecorator` nếu có nhiều threads gửi cùng session; **giữ một decorator duy nhất per session**.

### 8.7. WebSocketConfig.java

~~~java
package com.example.longshutdown;

import org.springframework.context.annotation.Configuration;
import org.springframework.web.socket.config.annotation.EnableWebSocket;
import org.springframework.web.socket.config.annotation.WebSocketConfigurer;
import org.springframework.web.socket.config.annotation.WebSocketHandlerRegistry;

@Configuration(proxyBeanMethods = false)
@EnableWebSocket
public class WebSocketConfig implements WebSocketConfigurer {

    private final RawSocketHandler handler;

    public WebSocketConfig(RawSocketHandler handler) {
        this.handler = handler;
    }

    @Override
    public void registerWebSocketHandlers(
            WebSocketHandlerRegistry registry) {
        registry.addHandler(handler, "/ws")
                .setAllowedOrigins("http://localhost:8080");
    }
}
~~~

Chỉ cho phép origin của browser demo. **Origin không phải authentication**, vì non-browser clients có thể không gửi hoặc giả mạo Origin. Production dùng authentication/authorization tại handshake, session expiry, tenant quotas và TLS/WSS.

### 8.8. AsyncMvcConfig.java

~~~java
package com.example.longshutdown;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.web.servlet.config.annotation.AsyncSupportConfigurer;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration(proxyBeanMethods = false)
public class AsyncMvcConfig {

    @Bean
    ThreadPoolTaskExecutor streamTaskExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(8);
        executor.setQueueCapacity(32);
        executor.setThreadNamePrefix("mvc-stream-");
        return executor;
    }

    @Bean
    WebMvcConfigurer asyncWebMvcConfigurer(
            ThreadPoolTaskExecutor streamTaskExecutor) {
        return new WebMvcConfigurer() {
            @Override
            public void configureAsyncSupport(
                    AsyncSupportConfigurer configurer) {
                configurer.setTaskExecutor(streamTaskExecutor);
                configurer.setDefaultTimeout(180_000L);
            }
        };
    }
}
~~~

Con số 4/8/32 **chỉ cho lab**, không phải sizing production. Executor có queue bounded để không tích tụ vô hạn khi nhiều long streams; một request có thể bị reject nếu vượt capacity, cần contract/metrics xử lý. Số lượng long-lived blocking writes tăng sẽ chiếm threads lâu; WebFlux có non-blocking I/O nhưng vẫn phải quản lý memory/buffer/cancellation.

### 8.9. LiveController.java

~~~java
package com.example.longshutdown;

import java.nio.charset.StandardCharsets;
import java.util.Map;

import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;
import org.springframework.web.servlet.mvc.method.annotation.StreamingResponseBody;

@RestController
public class LiveController {

    private final StreamRegistry registry;

    public LiveController(StreamRegistry registry) {
        this.registry = registry;
    }

    @GetMapping("/events")
    public ResponseEntity<?> events() {
        SseEmitter emitter = registry.registerSse();
        if (emitter == null) {
            return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE)
                    .contentType(MediaType.TEXT_PLAIN)
                    .body("server draining");
        }
        return ResponseEntity.ok()
                .contentType(MediaType.TEXT_EVENT_STREAM)
                .body(emitter);
    }

    @GetMapping("/slow-stream")
    public ResponseEntity<?> stream() {
        if (registry.isDraining()) {
            return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE)
                    .contentType(MediaType.TEXT_PLAIN)
                    .body("server draining");
        }

        StreamingResponseBody body = out -> {
            registry.streamStarted();
            try {
                for (int i = 1;
                     i <= 120 && !registry.isDraining();
                     i++) {

                    out.write(("part-" + i + "\n")
                            .getBytes(StandardCharsets.UTF_8));
                    out.flush();

                    try {
                        Thread.sleep(1000L);
                    }
                    catch (InterruptedException interrupted) {
                        Thread.currentThread().interrupt();
                        break;
                    }
                }
            }
            finally {
                registry.streamFinished();
            }
        };

        return ResponseEntity.ok()
                .contentType(MediaType.TEXT_PLAIN)
                .body(body);
    }

    @GetMapping("/internal/status")
    public Map<String, Object> status() {
        return Map.of(
                "draining", registry.isDraining(),
                "sseSessions", registry.sseCount(),
                "websocketSessions", registry.websocketCount(),
                "activeStreamingCallbacks", registry.longStreamCount());
    }

    @PostMapping("/internal/drain")
    public ResponseEntity<String> drain() {
        boolean first = registry.drain();
        return ResponseEntity.ok(
                first ? "drain started" : "already draining");
    }
}
~~~

**Cần phân biệt:** `/slow-stream` là response đã có HTTP 200; khi drain, callback dừng ở chunk tiếp theo, không thể thay status thành 503 sau commit. Để download/export có tính toàn vẹn, thêm artifact ID/cursor/checksum và cơ chế resume. Sample loop tối đa 120 giây để không trở thành luồng vô hạn. Nếu thread đang block ở `out.write()`, flag chỉ được kiểm khi call quay về; còn cần transport timeout và deadline.

Với `/events`, kiểm drain trước và sau đăng ký được thực hiện tại registry. Trường hợp đã drain, trả HTTP 503 để không mở stream mới. Với `/internal/drain`, việc gọi trực tiếp có thể tốn thời gian nếu có nhiều clients chậm: production nên dùng **bounded control-plane worker/deadline** thay vì gửi tuần tự trên request thread như lab.

### 8.10. static/demo.html

HTML nhỏ không cần external JavaScript library; tạo một SSE stream và một raw WebSocket để quan sát đóng:

~~~html
<!doctype html>
<html lang="vi">
<head>
  <meta charset="utf-8">
  <title>SSE & WebSocket shutdown lab</title>
  <style>
    body { font-family: system-ui, sans-serif; margin: 2rem; }
    button { padding: .5rem; margin-right: .5rem; }
    pre { border: 1px solid #aaa; height: 280px; overflow: auto; }
  </style>
</head>
<body>
  <h1>Long-lived connections lab</h1>
  <button id="connect">Open SSE + WebSocket</button>
  <button id="drain">Drain this server</button>
  <button id="close">Close clients</button>
  <pre id="log"></pre>
  <script>
    let sse = null;
    let ws = null;
    const log = line => {
      const p = document.getElementById("log");
      p.textContent += line + "\n";
      p.scrollTop = p.scrollHeight;
    };

    document.getElementById("connect").onclick = () => {
      if (sse) sse.close();
      if (ws && ws.readyState === WebSocket.OPEN) ws.close();

      sse = new EventSource("/events");
      sse.onopen = () => log("SSE open");
      sse.onerror = () => log("SSE error/end; may reconnect");
      sse.addEventListener("server-draining", event => {
        log("SSE terminal: " + event.data);
        sse.close(); // Tránh tự reconnect liên tục vào pod draining.
        sse = null;
      });

      const protocol = location.protocol === "https:" ? "wss://" : "ws://";
      ws = new WebSocket(protocol + location.host + "/ws");
      ws.onopen = () => log("WebSocket open");
      ws.onerror = () => log("WebSocket error");
      ws.onclose = event => log(
        "WebSocket close code=" + event.code
        + " reason=" + event.reason);
    };

    document.getElementById("drain").onclick = async () => {
      const response = await fetch("/internal/drain", { method: "POST" });
      log("Drain API: " + response.status + " " + await response.text());
    };

    document.getElementById("close").onclick = () => {
      if (sse) sse.close();
      sse = null;
      if (ws && ws.readyState === WebSocket.OPEN) ws.close();
    };
  </script>
</body>
</html>
~~~

Đây là **lab client**. Nó **không triển khai reconnect/backoff hoặc durable replay**: người học cần thấy close events; ứng dụng production nên kết nối lại qua Service/LB, có backoff+jitter, refresh token và fetch snapshot/cursor. Nút Drain cố ý mở cho localhost để test, tuyệt đối không đưa lên public endpoint.

## 9. Chạy và đối chiếu kết quả

### 9.1. Khởi động

Từ thư mục `long-lived-shutdown-lab`:

~~~bash
mvn spring-boot:run
~~~

Mở:

~~~text
http://localhost:8080/demo.html
~~~

Bấm **Open SSE + WebSocket**. Nếu chưa có lỗi kết nối, console trên trang có thể xuất:

~~~text
SSE open
WebSocket open
~~~

Thứ tự và thời điểm tùy browser/network, không phải stdout cố định. Gửi periodic SSE comments `:heartbeat` không kích hoạt `onmessage` mặc định; nó chủ yếu giữ stream hoạt động và giúp phát hiện disconnect khi ghi.

Xem registry từ terminal:

~~~bash
curl -s http://127.0.0.1:8080/internal/status
~~~

Với đúng một tab đang kết nối thành công, response JSON có các trường:

~~~json
{
  "draining": false,
  "sseSessions": 1,
  "websocketSessions": 1,
  "activeStreamingCallbacks": 0
}
~~~

Số phiên thay đổi theo số tabs, refresh, scheduling và timeout. Không khẳng định response luôn bằng 1 khi chỉ vừa bấm nút hoặc proxy/Origin chưa cho phép kết nối.

### 9.2. Test SSE bằng cURL

Ở terminal khác:

~~~bash
curl -N -i -H "Accept: text/event-stream" \
  http://127.0.0.1:8080/events
~~~

`-N`/`--no-buffer` tắt output buffering của cURL để thấy stream sớm hơn. Response thường có `Content-Type: text/event-stream` và các dòng heartbeat như:

~~~text
:heartbeat

~~~

Không phải mọi proxy đều flush comment ngay. Để đánh giá live SSE ở production, thử qua đường đi của ingress/LB, không chỉ localhost.

### 9.3. Test phản hồi HTTP dài

Chạy:

~~~bash
curl -N -i http://127.0.0.1:8080/slow-stream
~~~

Bạn sẽ thấy các dòng:

~~~text
part-1
part-2
part-3
~~~

Dữ liệu tiếp tục tới khi đạt 120 chunks, timeout, client đóng, hoặc drain; thực tế `curl -i` có headers ban đầu và timing phụ thuộc async execution. Nếu server bị drain giữa chừng, response đã commit có thể kết thúc với **một số chunks**, không chuyển thành HTTP 503.

### 9.4. Thực hiện drain

Khi browser và curl còn kết nối:

~~~bash
curl -i -X POST http://127.0.0.1:8080/internal/drain
~~~

Lần đầu, controller tạo body:

~~~text
drain started
~~~

Lần sau:

~~~text
already draining
~~~

Đây là **body** do demo tạo; headers/status line khác theo HTTP client. Về logic:

- Trạng thái drain được bật bằng CAS.
- Readiness được publish `REFUSING_TRAFFIC`.
- SSE emitters trong snapshot nhận một event `server-draining` nếu gửi kịp, rồi complete.
- Raw WebSockets trong snapshot nhận close code **1001** nếu close handshake đi qua mạng.
- Stream `/slow-stream` kết thúc khi callback kiểm cờ `draining` ở vòng tiếp theo.
- Các requests mở stream mới được từ chối hoặc không được routing do readiness/stack tùy vị trí; controller trả 503 nếu vẫn đến được code.

Sau drain, kiểm:

~~~bash
curl -s http://127.0.0.1:8080/internal/status
curl -i http://127.0.0.1:8080/events
curl -i http://127.0.0.1:8080/slow-stream
~~~

Trạng thái có `"draining":true`, số SSE/WebSocket sessions sau cleanup thường giảm về 0. Hai endpoints tạo stream mới trả HTTP **503** nếu request đến được controller. **Chú ý:** gọi endpoint internal sau khi server đã nhận SIGTERM có thể bị từ chối ngay tại network layer nên cURL không nhất thiết nhận response HTTP.

### 9.5. Readiness probe trong lab

Với probes enabled:

~~~bash
curl -i http://127.0.0.1:8080/actuator/health/readiness
~~~

Trước drain, readiness thường là `UP` khi app đã ready. Sau `AvailabilityChangeEvent.publish(...REFUSING_TRAFFIC)`, readiness tương ứng là `OUT_OF_SERVICE` và health HTTP status thường 503 theo status mapping mặc định. **Không gán liveness = BROKEN** chỉ vì graceful shutdown.

Nếu probe endpoint không xuất hiện, kiểm Actuator dependency, `management.endpoint.health.probes.enabled=true`, management port/path mapping và exposure/access policy; đừng tắt bảo mật toàn bộ Actuator để chữa lỗi.

### 9.6. Test SIGTERM đúng quy trình

Đóng gói:

~~~bash
mvn package
~~~

Chạy JAR bằng Java trong POSIX shell (Linux/macOS/WSL), từ root project:

~~~bash
java -jar target/long-lived-shutdown-lab-0.0.1-SNAPSHOT.jar &
APP_PID=$!
echo "java pid=$APP_PID"
~~~

Mở browser/SSE trên terminal khác, sau đó gửi:

~~~bash
kill -TERM "$APP_PID"
wait "$APP_PID"
~~~

Khi Spring Boot process nhận SIGTERM thông thường, application context bắt đầu đóng. Callback `@EventListener(ContextClosedEvent.class)` trong demo gọi `drain()` như fallback để đóng SSE/WebSocket trước hoặc trong lifecycle close. Embedded server cũng thực hiện graceful shutdown theo cấu hình. **Không hứa** terminal event chắc chắn tới mọi browser hoặc process sẽ dừng trong chính xác 20 giây; thứ tự, timeout, connector và cả shutdown hooks khác có thể ảnh hưởng.

Không dùng `kill -9` để test graceful shutdown: SIGKILL **không chạy** Java shutdown hooks, @EventListener hoặc `@PreDestroy`. Với Windows, phương pháp gửi process signal khác, và nút Stop IDE có thể là immediate kill.

## 10. Kubernetes: preStop, readiness và thời hạn SIGTERM

Một rolling deployment điển hình nên phối hợp:

1. Chuyển pod sang **not ready** trước khi dừng quá trình phục vụ để LB/Service ngừng định tuyến traffic mới.
2. Chặn sessions/streams mới ngay trong application.
3. Gửi terminal control event, đóng WebSocket và SSE, cho client reconnect tới pod khác.
4. Dành thời gian cho propagation và finite in-flight work.
5. Gửi SIGTERM và cho Spring Boot graceful shutdown diễn ra.
6. Dừng sau grace period hoặc force kill nếu deadline hết.

### 10.1. Pod manifest fragment

~~~yaml
apiVersion: v1
kind: Pod
metadata:
  name: long-shutdown-demo
spec:
  terminationGracePeriodSeconds: 45
  containers:
    - name: app
      image: example/long-shutdown-demo:1.0
      ports:
        - containerPort: 8080
      readinessProbe:
        httpGet:
          path: /actuator/health/readiness
          port: 8080
        periodSeconds: 2
        failureThreshold: 1
      lifecycle:
        preStop:
          exec:
            command:
              - /bin/sh
              - -c
              - "curl -fsS -X POST http://127.0.0.1:8080/internal/drain; sleep 5"
~~~

**Đây là deployment fragment minh họa, không phải production manifest đầy đủ**: image chưa được tạo, securityContext/resources/Service/replicas/ingress không có. Image tối giản có thể **không chứa curl hoặc /bin/sh**; khi đó dùng sidecar, lifecycle endpoint thông qua control plane hoặc một hook khác có hỗ trợ. Với Kubernetes, **phải bỏ** `server.address=127.0.0.1` của lab để probe và Service có thể đến app trên pod IP; vẫn chỉ cho management traffic đáng tin.

### 10.2. Tính deadline

Ví dụ:

~~~text
Kubernetes grace total:   45 s
  preStop drain + sleep:   5 s (có thể dài hơn nếu slow client)
  app SIGTERM/grace:      20 s / lifecycle phase (cấu hình minh họa)
  dư cho runtime/hooks:   không chắc cố định
~~~

Thời gian `preStop` **được tính trong** Kubernetes terminationGracePeriodSeconds; nó không phải bonus sau deadline. Hook có thể bị kill nếu quá hạn, trong khi external LB/readiness propagation cũng có độ trễ. Đừng thiết kế “preStop 40s + Spring grace 40s” khi pod grace chỉ 45s.

### 10.3. Readiness propagation không tức thì

Một pod `NotReady` có thể mất thời gian mới bị gỡ khỏi endpoints của Service/LB/Ingress. Vì vậy admission control trong ứng dụng cần từ chối **mới** khi draining, kể cả nếu một request tới trong cửa sổ propagation. Existing WebSocket/SSE thường gắn vào pod A, Kubernetes **không tự migrate TCP/WebSocket connection** sang pod B.

Client phải tự reconnect qua stable Service URL, làm lại authentication/subscriptions, lấy snapshot/replay. Nếu kết nối đã được thiết lập qua proxy, proxy idle/termination policies cũng có thể đóng trước ứng dụng.

### 10.4. Không gọi /internal/drain khi chưa có pod thay thế

Rolling deployment cần đảm bảo **readiness của pod mới** và số replicas đủ capacity trước khi pod cũ thoát. Nếu tất cả instances cùng drain, clients sẽ reconnect vào một Service không có backend khỏe, gây lỗi/hàng đợi retry. Cần `maxUnavailable`/`maxSurge`, PodDisruptionBudget và autoscaler policy phù hợp.

## 11. STOMP over WebSocket: subscriptions, broker và session events

Nếu ứng dụng dùng `@EnableWebSocketMessageBroker` thay raw WebSocket, cách quản lý khác:

~~~text
Client WebSocket + STOMP CONNECT
   |
   +-- SUBSCRIBE /topic/orders
   |
   v
Spring simple broker hoặc broker relay
   |
   +-- server sends STOMP MESSAGE frames
   |
   v
drain
   |
   +-- stop publishing new events to old session
   +-- (tùy) app notice "server-draining"
   +-- close WebSocket / stop transport
   +-- SessionDisconnectEvent / cleanup
   +-- client reconnect + new CONNECT + SUBSCRIBE
~~~

### 11.1. SessionDisconnectEvent có thể lặp

Một listener minh họa idempotency:

~~~java
// Fragment trong Spring-managed @Component.
@EventListener
public void onSessionDisconnect(SessionDisconnectEvent event) {
    String sessionId = event.getSessionId();
    if (activeSessionIds.remove(sessionId)) {
        // Hủy subscription/job/resource chỉ đúng một lần.
    }
}
~~~

`activeSessionIds` là registry do ứng dụng tự quản, đoạn trên **không phải file Java độc lập**. Event có thể phát khi STOMP DISCONNECT từ client hoặc khi WebSocket đã đóng, và có thể được publish **nhiều lần**. Không double decrement counters hoặc double charge/refund vì lặp event.

### 11.2. Broker relay không thay durable replay contract

Khi dùng external broker (RabbitMQ/ActiveMQ), có thể có acknowledgments/queues/retention tùy cấu hình STOMP destination và broker. Nhưng việc client WebSocket disconnect **không tự chứng minh** đã xử lý hết các business events. Cần phân biệt:

- Event được app tạo.
- Event được broker nhận/commit.
- Event nằm trong queue/subscription.
- Event gửi vào outbound WebSocket.
- Browser nhận và xử lý event.
- Application-level ACK/transaction hoàn tất.

Nếu không có durable store và ACK nghiệp vụ, một event được gửi ngay trước drain có thể bị mất với client. Với payments/audit, không được dựa trên “đã gửi STOMP MESSAGE” mà coi giao dịch đã thành công.

### 11.3. Shutdown order của broker

Nếu stop broker connection/producer quá sớm, client không nhận được app notice; nếu đợi broker quá lâu, pod hết deadline. Phân pha:

1. Gate new sends/subscriptions khi draining.
2. Cố gửi control notice hoặc persist cần thiết.
3. Đóng sessions.
4. Hủy application-level consumers/actors.
5. Stop broker relay/client connection theo lifecycle.
6. Shutdown context và HTTP server.

Trong production, lifecycle hooks nên phối hợp với `SmartLifecycle`/ApplicationContext closure và deadlines; không giả định thứ tự các bean `@PreDestroy` tùy tiện là đủ.

## 12. WebFlux: hủy Publisher và WebSocket đúng lifecycle

Spring WebFlux dùng non-blocking pipelines, không phải Servlet `SseEmitter`. HTTP SSE thường trả:

~~~java
// Fragment trong WebFlux @RestController.
@GetMapping(value = "/events", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
public Flux<ServerSentEvent<String>> events() {
    return eventSource
            .takeUntilOther(drainingSignal)
            .doFinally(signal -> subscriptions.releaseCurrent());
}
~~~

Đoạn trên chỉ **minh họa logic**: `eventSource`, `drainingSignal` và `subscriptions` là các biến ứng dụng giả định; mã không thể chạy độc lập. Cần phân biệt `takeUntilOther(Publisher)` dừng stream khi publisher khác **phát tín hiệu**, không tự được kích hoạt khi Boolean flag đổi. `doFinally` chạy ở complete/error/cancel và nên cleanup idempotent.

### 12.1. Sse với Flux không đồng nghĩa browser nhận event cuối

Khi `takeUntilOther(shutdownSignal)` kết thúc `Flux`, kết nối HTTP có thể complete nhưng việc terminal control event có đi ra trước completion không phụ thuộc tự động. Nếu muốn gửi một event cuối, xây state-machine/publisher được **serialize** đúng thứ tự:

~~~text
business events -> server-draining control event -> onComplete
~~~

Nếu nhiều publishers phát đồng thời, phải có synchronization/sinks chính xác; không tùy tiện gọi `sink.tryEmitNext` sau khi `tryEmitComplete` rồi mong event được nhận.

### 12.2. WebFlux WebSocket

Theo tài liệu Spring WebFlux:

- `WebSocketSession.receive()` trả `Flux<WebSocketMessage>` và complete khi connection đóng.
- `WebSocketSession.send(Publisher<WebSocketMessage>)` trả `Mono<Void>` khi source hoàn thành và gửi xong theo contract của connector.
- `WebSocketHandler.handle(session)` phải trả một `Mono<Void>` phản ánh lifecycle của inbound/outbound streams.
- Có thể dùng `session.close(CloseStatus.GOING_AWAY)` theo WebFlux CloseStatus API tương ứng, nhưng phải nối Mono vào pipeline để **subscribe thật**; gọi một reactive method rồi bỏ Mono không gây side-effect.

Ví dụ concept:

~~~java
// Fragment trong một WebFlux WebSocketHandler; không độc lập.
// shutdownSignal phải là Publisher phát một tín hiệu khi drain.
Mono<Void> outbound = session.send(
        outboundMessages.takeUntilOther(shutdownSignal)
                .map(session::textMessage));

Mono<Void> inbound = session.receive()
        .doOnNext(message -> {
            // validate/route; không block event loop
        })
        .then();

return Mono.whenDelayError(inbound, outbound)
        .doFinally(signal -> cleanupSession(session.getId()));
~~~

Đây là ví dụ **cơ chế**: `outboundMessages`, `shutdownSignal` và `cleanupSession` không được định nghĩa. Trong trường hợp source outbound kết thúc khi drain nhưng inbound chưa xong, `whenDelayError` có thể **tiếp tục chờ inbound**. Để đóng ngay, thiết kế lifecycle với race/cancellation hoặc chủ động gọi `session.close(...)` và ghép nó vào publisher. Không copy fragment này rồi tuyên bố WebSocket chắc chắn đóng đúng deadline.

### 12.3. Hot streams và cancellation

Một hot source có thể tiếp tục phát sau khi subscriber bị cancel nếu producer không tôn trọng demand/cancellation hoặc không được cleanup. Với Reactor:

- `doFinally`/`usingWhen` để cleanup resources theo complete/error/cancel.
- `takeUntilOther` để gắn stream với drain signal.
- `onBackpressureBuffer(maxSize, ...)` phải bounded nếu dùng.
- `Sinks.Many.tryEmitNext` cần xử lý EmitResult khi subscriber chậm/đã đóng.
- Không gọi `block()` trên Netty event loop chỉ để chờ drain.
- Khi shutdown, hủy subscriptions, timers, database change streams, message broker consumers và HTTP clients theo ownership.

Graceful server ở Reactor Netty có behavior riêng về connection lifecycle; test qua Netty server và gateway thật, không áp quy tắc Servlet worker thread trực tiếp.

## 13. Slow client, backpressure và deadline tổng

Một kết nối dài có thể không đóng nhanh vì:

- Client đọc TCP chậm, kernel send buffer đầy.
- TLS write hoặc proxy forward bị nghẽn.
- Scheduler heartbeat/terminal SSE đang block trên một phiên.
- WebSocket outbound queue có nhiều messages chờ trước control event.
- STOMP client chưa ack và broker đang đợi.
- Long-running database/export task chưa nhận cancellation.

Không tạo một drain loop duy nhất **gửi tuần tự** terminal events tới 100.000 SSE clients trong request thread mà không có deadline. Dùng control plane worker pool bounded, per-session write queues với limit, deadline và metrics.

### 13.1. Ưu tiên kết thúc theo thứ tự

1. Ngừng upstream producers tạo events mới vào sessions cũ.
2. Đặt readiness `REFUSING_TRAFFIC` và admission gate.
3. Gửi control event có ưu tiên hoặc đưa vào một writer queue đã serialize.
4. Cho thời gian ngắn theo policy để client nhận close notice, nếu không vẫn đóng.
5. Close WebSocket/SSE/stream với cleanup.
6. Cancel tasks/queues/outstanding subscriptions.
7. Handoff durable state hoặc để client replay từ nguồn bền.
8. Hết deadline thì cho shutdown tiếp; không block liveness mãi.

Một **buffered SSE write** thành công chỉ nói server ghi vào tầng output, không phải client render. Tương tự, WebSocket close 1001 có thể không bao giờ tới browser nếu đường truyền chết. Vì thế state ở backend phải độc lập với thông điệp tạm thời.

### 13.2. Chính sách cho các loại dữ liệu

| Dữ liệu | Khi drain | Khôi phục |
| --- | --- | --- |
| Dashboard latest state | Đóng/reconnect tương đối sớm | GET snapshot mới |
| Chat messages | Ngừng publish vào session cũ, đóng socket | Lấy messages sau cursor |
| Order/payment events | Persist/outbox trước khi gửi | Replay idempotent/ACK nghiệp vụ |
| Audit events | Flush durable log theo SLA | Durable log consumer resume |
| Video/large download | Cho finite time hoặc ngắt có kiểm soát | Resume Range/ETag nếu hỗ trợ |
| SSE price ticker | Terminal notice, complete | Reconnect + latest snapshot |
| WebSocket game actions | Ngừng nhận action mới, save state | Resume session/game state theo policy |

“Đã ngắt socket” không nên làm xóa business work chưa commit. Tách **stream connection lifecycle** khỏi **durable business transaction lifecycle**.

## 14. Proxy, Ingress, HTTP/2 và các edge cases

### 14.1. Load balancer không di chuyển connection hiện có

Gỡ pod khỏi Service endpoints chỉ ảnh hưởng routing **kết nối/request mới**. Existing TCP/WebSocket connections thường giữ với pod cũ cho tới close hoặc LB drain policy. HTTP keep-alive có thể còn requests trên một connection cũ; embedded server có cách từ chối request mới tùy connector.

### 14.2. SSE bị proxy buffer

Proxy buffering có thể giữ terminal SSE event tới khi đủ bytes hoặc kết nối đóng. Client có thể không thấy `server-draining` trước khi response kết thúc. Kiểm các options phù hợp trên proxy cho stream endpoints (ví dụ hạn chế buffering đúng route), idle timeout, HTTP/2 behavior, compression và flush semantics.

### 14.3. HTTP/2 GOAWAY không phải WebSocket close frame

HTTP/2 có cơ chế `GOAWAY` để báo ngừng nhận streams mới trên connection. WebSocket close code 1001 là frame của **WebSocket protocol**. SSE là HTTP response streaming. Không lấy một loại frame thay cho loại kia; proxy/LB có thể là nơi kết thúc HTTP/2/TLS và mở HTTP/1.1 mới tới Spring Boot.

### 14.4. Timeout ingress/LB trước ứng dụng

Ngay cả khi Spring MVC SseEmitter timeout 30 phút, LB idle timeout 60 giây vẫn có thể cắt kết nối sau 60 giây không có bytes đi qua. Heartbeat giúp nhưng không đảm bảo nếu proxy buffer, network hỏng hoặc app blocked. Test đường đi **thật**, không chỉ localhost. Không đặt client heartbeat interval 5 phút khi ingress idle timeout là 1 phút.

### 14.5. TLS termination và reconnect

Nếu browser kết nối `wss://service.example` qua Ingress tới pod A, khi pod A dừng browser nên reconnect tới **cùng public hostname**, không dùng Pod IP hoặc internal raw socket URL cũ. App cần dùng đúng auth token/session policy; nếu token hết hạn trong lúc drain, refresh hợp lệ trước khi re-subscribe.

## 15. Trạng thái, replay và tránh reconnect storm

### 15.1. Event IDs và business cursor

Nếu event log có các ID tăng ổn định:

~~~text
101 -> created
102 -> paid
103 -> shipped
104 -> delivered
~~~

Client vừa xử lý tới 102 rồi mất socket. Nó có thể gọi `GET /events?after=102` hoặc gửi `Last-Event-ID: 102` khi SSE reconnect. Backend phải **validate tenant ownership**, truy vấn durable log, chọn retention, xử lý duplicate và kết thúc replay trước live stream để tránh gap.

Một WebSocket mới không tự kế thừa subscriptions hoặc state của socket cũ; phải tái xác thực và gửi thông tin last processed cursor. Không dùng **server send attempt** làm last ACKed cursor.

### 15.2. Exponential backoff + jitter

Một reconnect sequence minh họa:

~~~text
attempt 1 -> random 0.5–1.5 s
attempt 2 -> random 1–3 s
attempt 3 -> random 2–6 s
attempt 4 -> random 4–12 s
max retry delay -> 30 s, có jitter
~~~

Những mốc này là **ví dụ**, không phải tiêu chuẩn bắt buộc. Mục đích: khi hàng nghìn clients nhận close code 1001 cùng lúc, không tạo 10.000 WebSocket handshakes vào một giây. Server cũng nên rate-limit handshakes, auth, subscriptions và replay API; client cần xử lý offline state, retry limit, token renewal và loading UX.

### 15.3. Client nhận 1001 rồi phải làm gì?

1. Đóng resource của old WebSocket, không tiếp tục gửi vào socket cũ.
2. Không coi close là xác nhận mọi outbound business command đã được nhận/commit.
3. Reconnect sau backoff qua Service URL đến instance khỏe.
4. Xác thực lại và re-subscribe.
5. Lấy snapshot hoặc replay theo cursor/offset của **sự kiện đã xử lý**.
6. Deduplicate bằng event ID/idempotency key.
7. Đánh dấu UI “reconnecting” khi data stale.
8. Giới hạn retries và hiển thị degraded state nếu không có backend khỏe.

## 16. Observability khi shutdown long-lived connections

### 16.1. Metrics cần theo dõi

| Metric đề xuất | Ý nghĩa |
| --- | --- |
| `active_sse_connections` | Số SSE emitters còn quản lý |
| `active_websocket_sessions` | Số raw/STOMP sessions đang mở |
| `active_streaming_callbacks` | Async streaming tasks đang thực thi |
| `draining_state` | 0/1 hoặc status của instance |
| `drain_duration_seconds` | Thời gian từ bắt đầu drain tới khi sessions còn 0/deadline |
| `stream_terminations_total{reason=...}` | normal, timeout, error, drain, force-close |
| `websocket_close_total{code=...}` | Close codes giới hạn tập giá trị |
| `sse_emit_error_total` | I/O errors và terminal send failures |
| `reconnect_rate` | Số reconnects/giây sau deploy |
| `replay_lag_seconds` | Độ trễ phục hồi từ durable log |
| `discarded_events_total` | Dữ liệu bị drop vì queue/overflow |
| `shutdown_timeouts_total` | Hết grace trước hoàn tất |
| `readiness_state` | Instance có chấp nhận traffic mới không |

Không phải tất cả metrics có sẵn tự động trong Boot Actuator; cần custom Micrometer gauges/counters, tracing và management platform metrics. Tránh gắn session IDs, user IDs hoặc raw URLs vào metric labels (cardinality và privacy).

### 16.2. Khi nào tính là “drain thành công”?

**Không chỉ** “process exit code 0”. Một bộ tiêu chí tốt gồm:

- Sau khi trạng thái draining được bật, không có **long-lived sessions mới** được nhận trên instance.
- Readiness bị hạ và routing dần chuyển sang pods khỏe.
- SSE/WS active sessions giảm về 0 hoặc dưới số exception đã giải thích.
- Không có queue/broker subscription/timer/resource bị leak sau close.
- Streams quan trọng được complete hoặc có **durable resume/cursor**.
- HTTP/WS client reconnect rate không vượt budget.
- Không có lỗi 5xx/timeout tăng đột biến quá SLO trong rollout.
- Time-to-termination nằm trong tổng grace period của orchestrator.
- Events có delivery contract không bị mất do shutdown race.

### 16.3. Logs gọn và an toàn

Một shutdown log cần:

~~~text
drain_started instance=pod-a active_sse=12 active_ws=30
drain_finished instance=pod-a remaining_sse=0 remaining_ws=0
~~~

Đây là log format minh họa, **không phải stdout cố định** của lab. Không log raw SSE data, WebSocket payload, Authorization header, session cookie hoặc user PII. Có thể thêm trace/correlation ID nhưng tránh label cardinality cao.

## 17. Kế hoạch test và chaos test

### 17.1. Ma trận test đề xuất

| Test | Cách tạo | Kết quả đúng |
| --- | --- | --- |
| No connections | Gọi drain khi registry trống | Không lỗi; state chuyển đúng |
| SSE normal | Mở EventSource, drain | Nhận terminal khi gửi kịp, emitter complete/cleanup |
| SSE already disconnected | Client ngắt trước drain | Cleanup không throw/double-complete |
| WS normal | Mở WebSocket, drain | Client có thể thấy code 1001; registry cleanup |
| WS abnormal | Kill browser/network trước drain | Server không giữ session leak vô hạn |
| Many clients | Mở N sessions, drain đồng thời | Thời gian/memory không tăng vô hạn |
| Drain called twice | POST hai lần | Thực thi đóng một lần; lần hai idempotent |
| New requests during drain | Race mở SSE/WS với POST drain | Không có session mới tồn tại sau drain |
| Slow HTTP stream | Client đọc chậm | Deadline/timeout áp dụng; không treo shutdown mãi |
| SIGTERM | Kill -TERM trên Java process | Callback/lifecycle được kích hoạt nếu runtime hỗ trợ |
| SIGKILL | Kill -9 | Không có graceful hooks; client/replay vẫn phục hồi |
| K8s preStop | Rolling deploy | Readiness và streams chuyển dần; pod thoát trong grace |
| Proxy idle timeout | Qua ingress thực | Heartbeat/reconnect phù hợp |
| STOMP SessionDisconnectEvent duplicate | Gửi và nhận event lặp | Cleanup chỉ một lần |
| Durable replay | Disconnect giữa event 102/103 | Client lấy lại data đúng, không duplicate effects |

### 17.2. Stress đúng cách

- Giới hạn test trong môi trường riêng, không chạy ở shared production.
- Dùng client load generator có WebSocket/SSE support và network shaping; browser JS delay **không chắc** làm TCP reader chậm.
- Test với queue/buffer pressure, large payload và băng thông thấp.
- Giữ một nhóm client nhanh để kiểm fairness trong khi nhóm khác bị slow.
- Đo pending bytes, active write threads, scheduling latency và heap/GC.
- Dùng canary rolling deploy dưới load; không chỉ test một process đóng khi không có traffic.
- Đảm bảo không phải traffic generator/broker/CPU client đang bão hòa trước server.

### 17.3. Race conditions cần cố ý thử

1. Client connect vừa xong, ngay lúc drain snapshot registry.
2. Browser nhận terminal SSE event nhưng WebSocket close chưa được gửi.
3. SseEmitter onTimeout chạy cùng lúc drain gọi complete.
4. WebSocket afterConnectionClosed chạy cùng lúc drain remove map entry.
5. Connection write chậm/blocked khi deadline shutdown tới.
6. Broker publish message mới sau khi draining=true.
7. SIGTERM tới khi preStop chưa hoàn tất.
8. Pod mới chưa ready nhưng old pod đã not ready.
9. Client reconnect tới old pod trong thời gian LB endpoints chưa cập nhật.
10. Replay trả duplicate/out-of-order events sau reconnect.

Mỗi tình huống cần assertions về **state và resource cleanup**, không chỉ HTTP status.

## 18. Những sai lầm phổ biến

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Chỉ bật `server.shutdown=graceful` | SSE/WS có thể còn mở tới hết deadline | App-level drain và close |
| Chỉ hạ readiness | Existing sockets không tự migrate | SSE terminal, WebSocket close, client reconnect |
| Chỉ đóng socket mà không hạ readiness | LB vẫn chuyển streams mới tới pod cũ | Drain state + readiness + admission gate |
| Không kiểm race sau khi register | Session mới có thể lọt sau snapshot | Atomic gate/check-after-add |
| Gọi `completeWithError` ngay sau IOException SSE write | Double async error handling | Để container xử lý I/O error, cleanup registry |
| Nghĩ `SseEmitter.complete()` là client đã ACK | Có thể mất event cuối | Durable log/snapshot/replay |
| Gửi close code 1006 | 1006 là reserved, không được truyền trên wire | Dùng CloseStatus.GOING_AWAY/1001 phù hợp |
| Coi WebSocket close và STOMP DISCONNECT như nhau | Sai cleanup/ACK semantics | Phân biệt subprotocol và transport |
| STOMP disconnect event xử lý không idempotent | Double cleanup/counters/billing | Remove-if-present, idempotency |
| SIGKILL để test graceful | Hooks không chạy | Test SIGTERM, và separately force-kill recovery |
| preStop dài hơn K8s grace | Pod bị kill giữa cleanup | Tính chung grace và deadline |
| Unbounded terminal sends tuần tự | Một slow client giữ shutdown control thread | Bounded worker/deadline per session |
| Không stop producers | Queue tiếp tục đầy khi đang close | Gate publishing/cancel subscriptions |
| Return HTTP 200 đã stream nửa chừng | Client tưởng download đủ | Checksum/cursor/Range/job state |
| Không hủy timers/queues | Memory/session leak qua restart/drain | Cleanup onComplete/onClose/doFinally |
| Reconnect ngay không jitter | Reconnect storm sau rollout | Exponential backoff+jitter |
| WebFlux hủy Mono mà bỏ subscribe | Reactive close không thực thi | Compose/subscribe qua lifecycle flow |
| Dùng `Thread.sleep` trên Netty event loop | Block nhiều connections | Non-blocking scheduling, bounded tasks |
| Chỉ đo active connections mà không đo backlog | Không thấy slow consumer overload | Pending bytes/queue/latency metrics |
| Public `/internal/drain` endpoint | Bất kỳ ai cũng có thể ngắt service | Management-plane auth/RBAC/network policy |
| Kết nối WebSocket theo Pod IP | Reconnect thất bại sau pod replace | Stable Service DNS/Ingress |
| Không có replay/ACK | Mất event trong shutdown race | Durable event log, cursor, idempotency |
| Gọi app drain từ @PreDestroy quá muộn | Broker/HTTP server có thể đã stop | Chủ động preStop/early lifecycle hook |
| Bỏ qua proxy buffering của SSE | Terminal event không thấy ở browser | Test qua ingress và cấu hình stream |

## 19. Checklist production trước khi triển khai

### Quản lý vòng đời

- [ ] Đã liệt kê mọi loại long-lived connection: SSE, raw WS, STOMP, file streaming, NDJSON, reactive Flux?
- [ ] Có một draining state idempotent, chặn new sessions và kiểm race sau register?
- [ ] Readiness REFUSING_TRAFFIC được publish trước khi tắt listener?
- [ ] Có đường preStop/control-plane an toàn, fallback on context close và deadline thực?
- [ ] Thời gian preStop + app grace phù hợp Kubernetes terminationGracePeriodSeconds?
- [ ] Không dùng SIGKILL như phương pháp shutdown thường xuyên?
- [ ] Embedded server graceful settings đúng version và behavior đã được test?

### SSE/streaming

- [ ] SseEmitter có onCompletion/onTimeout/onError cleanup?
- [ ] Heartbeat đủ phát hiện disconnected peers và tránh idle proxy timeout?
- [ ] Có terminal control event khi drain, nhưng không nhầm với client ACK?
- [ ] Exception IOException ở send được để container xử lý, không double-complete?
- [ ] HTTP streaming có cancellation flag, interrupt handling và finally cleanup?
- [ ] Trường hợp response đã commit có checksum/cursor/restart policy?
- [ ] AsyncTaskExecutor bounded, không giữ vô hạn slow client writes?

### WebSocket/STOMP

- [ ] WS registry có afterConnectionClosed/transport error cleanup idempotent?
- [ ] Server close GOING_AWAY/1001 thay vì gửi reserved codes?
- [ ] Client có onclose/onerror/reconnect backoff+jitter?
- [ ] STOMP subscriptions/SessionDisconnectEvent cleanup idempotent?
- [ ] Broker producers/queues stopped/canceled theo lifecycle?
- [ ] Có sequence/replay/snapshot cho data không được mất?
- [ ] Có per-user quotas, auth, rate limit, session expiry và client reconnect budget?

### Hạ tầng và quan sát

- [ ] Proxy/LB/Ingress đã được test với SSE buffering/idle timeout và WS keepalive?
- [ ] Có đủ pods healthy trước khi drain old pod?
- [ ] Metrics active sessions, drain duration, close reasons, dropped events, replay lag và timeout?
- [ ] Có canary deploy/chaos test SIGTERM và force kill riêng?
- [ ] Không gắn PII/session IDs vào metrics tags hoặc raw payload vào logs?
- [ ] Endpoint drain và Actuator đã được bảo vệ bằng network/auth/RBAC?
- [ ] Có runbook khi grace hết mà một worker/socket còn blocked?

## 20. Câu hỏi tự kiểm tra có đáp án

**Câu 1.** Spring Boot 4.1 mặc định graceful shutdown với Tomcat/Netty, vậy có phải SSE và WebSocket sẽ tự đóng theo đúng business protocol?

**Đáp án:** Không. Graceful server quản lý admission và in-flight requests theo timeout; application còn cần drain registry, dừng producers, phát terminal event, close frame, cleanup và deadline.

**Câu 2.** Đã chuyển readiness sang REFUSING_TRAFFIC, các WebSocket hiện có có tự chuyển qua pod mới không?

**Đáp án:** Không. Kết nối hiện có thường vẫn gắn với pod cũ; server phải đóng, client reconnect qua Service URL và khôi phục subscriptions/state.

**Câu 3.** SSE gửi `server-draining` rồi `complete()` có chứng minh browser đã nhận/ACK thông điệp cuối?

**Đáp án:** Không. Send/complete ở server không bảo đảm delivery end-to-end. Cần event IDs/cursor/replay cho dữ liệu quan trọng.

**Câu 4.** Vì sao khi `SseEmitter.send` ném IOException do client disconnect không nên gọi `completeWithError` ngay?

**Đáp án:** Spring MVC Servlet async error path do container xử lý khi write lỗi; app nên cleanup registry và tránh double-complete.

**Câu 5.** `CloseStatus.GOING_AWAY` có mã nào? Có được gửi 1006 không?

**Đáp án:** GOING_AWAY là **1001**; **1006** là mã dành riêng mô tả abnormal close, không được gửi trong close frame.

**Câu 6.** Khi dùng STOMP, có phải SessionDisconnectEvent chỉ xảy ra đúng một lần cho mỗi client?

**Đáp án:** Không. Spring docs nói event có thể lặp; cleanup phải idempotent.

**Câu 7.** Một stream `StreamingResponseBody` trả HTTP 200 rồi gửi 50/100 chunks, server có thể đổi HTTP status thành 503 lúc drain không?

**Đáp án:** Không nếu headers đã commit. Phải có application-level integrity/resume/cursor/checksum hoặc job-state contract.

**Câu 8.** Vì sao kiểm `draining=false` trước khi add vào concurrent Set chưa đủ?

**Đáp án:** Drain có thể bật và snapshot giữa check và add; cần kiểm lại sau add hoặc đồng bộ admission với drain.

**Câu 9.** Trong Kubernetes, có nên đặt preStop sleep 30 giây khi terminationGracePeriodSeconds chỉ 20 giây?

**Đáp án:** Không. preStop nằm **trong tổng grace budget**; pod có thể bị kill trước khi app nhận SIGTERM hoặc hoàn tất cleanup.

**Câu 10.** Nếu WebFlux `takeUntilOther(shutdownSignal)` đã complete output, WebSocket chắc chắn đóng?

**Đáp án:** Không nhất thiết; còn inbound publisher/lifecycle composition. Phải ghép close/cancel vào returned Mono hoặc session.close một cách được subscribe đúng.

**Câu 11.** Một client báo WebSocket close code 1006 có nghĩa server đã gửi close code 1006?

**Đáp án:** Không. 1006 reserved, client báo khi kết nối đóng bất thường mà không nhận close frame hợp lệ.

**Câu 12.** Vì sao client reconnect ngay khi nhận close 1001 có thể khiến deploy thất bại?

**Đáp án:** Hàng nghìn clients cùng reconnect/re-auth/re-subscribe/replay tạo storm. Dùng backoff+jitter, quotas và scale pods đủ.

**Câu 13.** Nếu ứng dụng phát events từ Kafka/RabbitMQ, đóng WebSocket là đủ để đảm bảo payment events không mất?

**Đáp án:** Không. Cần durable log, business ACK/idempotency, consumer offsets và replay theo tenant; WebSocket send không là commit nghiệp vụ.

**Câu 14.** Khi drain gọi hai lần, có nên gửi terminal event và close mọi session thêm một lần?

**Đáp án:** Không cần; nên idempotent. CAS flag và remove-if-present ngăn double effects, đồng thời cleanup callbacks có thể chạy nhiều lần.

## 21. Tài liệu chính thức và tham khảo

- [Spring Boot 4.1 — Graceful Shutdown](https://docs.spring.io/spring-boot/reference/web/graceful-shutdown.html) — default grace ở Tomcat/Jetty/Netty, `timeout-per-shutdown-phase` và cách từ chối requests mới.
- [Spring Boot — Actuator Endpoints: Kubernetes Probes và Readiness](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html) — lifecycle, readiness/liveness, shutdown, preStop.
- [Spring Boot 4.1 API — AvailabilityChangeEvent](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/availability/AvailabilityChangeEvent.html) — `publish(ApplicationContext, ReadinessState)`.
- [Spring Boot — Application Properties](https://docs.spring.io/spring-boot/appendix/application-properties/) — server.shutdown, lifecycle timeout, async MVC timeout, Actuator probes.
- [Spring Framework — Asynchronous Requests on Spring MVC](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-async.html) — SseEmitter, ResponseBodyEmitter, StreamingResponseBody, disconnect errors và Servlet async lifecycle.
- [Spring Framework Javadoc — SseEmitter](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/servlet/mvc/method/annotation/SseEmitter.html).
- [Spring Framework Javadoc — SseEmitter.SseEventBuilder](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/servlet/mvc/method/annotation/SseEmitter.SseEventBuilder.html).
- [Spring Framework — WebSocket on Servlet Stack](https://docs.spring.io/spring-framework/reference/web/websocket/server.html).
- [Spring Framework Javadoc — WebSocketSession](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/socket/WebSocketSession.html).
- [Spring Framework Javadoc — CloseStatus](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/socket/CloseStatus.html).
- [Spring Framework — STOMP WebSocket Events](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/application-context-events.html) — SessionDisconnectEvent và broker state.
- [Spring Framework — WebFlux WebSockets](https://docs.spring.io/spring-framework/reference/web/webflux-websocket.html).
- [Spring Framework — WebFlux Server-Sent Events](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/return-types.html).
- [Spring Boot — Managed Dependencies](https://docs.spring.io/spring-boot/appendix/dependency-versions/coordinates.html) — Boot 4.1.2 WebSocket starter.
- [RFC 6455 — WebSocket Close Control Frame](https://www.rfc-editor.org/rfc/rfc6455).
- [WHATWG HTML — Server-Sent Events / EventSource](https://html.spec.whatwg.org/multipage/server-sent-events.html).
- [Kubernetes — Container Lifecycle Hooks](https://kubernetes.io/docs/concepts/containers/container-lifecycle-hooks/).
- [Kubernetes — Pod Termination](https://kubernetes.io/docs/concepts/workloads/pods/pod-lifecycle/#pod-termination).
- [Reactor — Reactive Streams Cancellation](https://projectreactor.io/docs/core/release/reference/coreFeatures/error-handling.html).
- [OWASP — WebSocket Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/WebSocket_Security_Cheat_Sheet.html).

**Kết luận:** Với Spring Boot 4.1, graceful embedded server **ngăn requests mới và cho in-flight requests một khoảng thời gian**, nhưng SSE, WebSocket và các streaming responses có thể không tự kết thúc đúng lúc. Cần **drain-first**: chuyển readiness, chặn admission, dừng producers, cố báo client (SSE `server-draining`, WS close `GOING_AWAY/1001`), hoàn tất/hủy streams, cleanup registry và subscriptions, rồi mới chốt shutdown trong deadline. Delivery của sự kiện cuối luôn best-effort; correctness phải dựa trên **cursor/replay/ACK/idempotency và durable state**, không chỉ trên việc TCP/WebSocket đã đóng.