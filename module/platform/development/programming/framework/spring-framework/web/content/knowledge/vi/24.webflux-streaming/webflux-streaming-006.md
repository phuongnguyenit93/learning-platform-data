# Hủy đăng ký, client ngắt kết nối và dọn dẹp tài nguyên trong Streaming WebFlux

## 1. Bài toán: client ngừng đọc nhưng server vẫn đang phát stream

Một endpoint Spring WebFlux có thể trả về `Flux<ServerSentEvent<T>>` để đẩy sự kiện liên tục tới trình duyệt, hoặc trả `Flux<DataBuffer>` để truyền tệp lớn. Khác response JSON một lần, một stream có thể sống lâu, chứa nhiều sự kiện/bytes và có **tài nguyên gắn với từng subscription**: timer, đăng ký broker, database cursor, upstream HTTP connection, file channel hay pooled buffers.

Ví dụ:

~~~java
@GetMapping(
        path = "/api/ticks",
        produces = MediaType.TEXT_EVENT_STREAM_VALUE)
public Flux<ServerSentEvent<String>> ticks() {
    return Flux.interval(Duration.ofSeconds(1))
            .map(i -> ServerSentEvent.<String>builder()
                    .event("tick")
                    .id(Long.toString(i))
                    .data("tick-" + i)
                    .build());
}
~~~

Đây là **fragment** cần class Spring `@RestController` cùng imports. Browser có thể dùng `EventSource`, sau vài sự kiện đóng tab hoặc gọi `eventSource.close()`. Nếu client đã không quan tâm, server nên ngừng gửi dữ liệu, huỷ upstream subscription và dọn tài nguyên. Nhưng phải phân biệt:

- **`cancel()`**: tín hiệu trong Reactive Streams/Project Reactor, do downstream hủy subscription.
- **Client disconnect**: sự kiện ở socket HTTP/transport, có thể dẫn đến `cancel()` trên response publisher **khi adapter phát hiện được**.
- **Resource cleanup**: giải phóng đối tượng thực (listener/file/DB connection/pooled buffer), không phải chỉ tăng một counter “cancelled”.
- **Business rollback**: hoàn tác tác dụng đã xảy ra; không tự xảy ra chỉ vì một subscription bị hủy.

**Không được khẳng định rằng client đóng tab thì server tức thì nhận `SignalType.CANCEL`, hoặc rằng `cancel` chắc chắn dừng JDBC query đang block.** Thời điểm và cách transport phát hiện disconnect phụ thuộc TCP/HTTP, read/write activity, proxy, server adapter và timing.

### Mục tiêu

Sau bài này bạn có thể:
1. Phân biệt ba sự kiện `onComplete`, `onError`, `cancel` và callback tương ứng của Reactor.
2. Hiểu luồng tín hiệu từ browser `EventSource.close()` hoặc hủy HTTP stream đến Netty/WebFlux/Publisher.
3. Dùng đúng `doOnCancel`, `doFinally(SignalType)`, `Flux.using` và `Flux.usingWhen`.
4. Đảm bảo cleanup ở **mọi** kết cục: thành công, lỗi, timeout, hủy; tránh double-close và resource leak.
5. Làm rõ cleanup **đồng bộ** so với cleanup **bất đồng bộ**, cũng như vị trí của `doOnDiscard`/`DataBufferUtils.release`.
6. Kiểm tra cold/hot publishers, subscriptions độc lập, shared upstream và multiplex nhiều clients.
7. Thiết kế SSE heartbeat/reconnect, timeout, proxy buffering và shutdown graceful.
8. Viết Java 17 + Spring Boot 3.3.5 WebFlux demo, test `StepVerifier.thenCancel()` và HTTP `WebTestClient`.
9. Nhận diện khi client disconnect **không** nên rollback job/transaction hoặc huỷ một workflow bền vững.

Bài giới hạn ở **Spring WebFlux/Project Reactor và streaming HTTP**, không nhầm cơ chế này với Servlet MVC `SseEmitter`/`DeferredResult`. Mã demo tương thích Spring Framework 6.1.x và Reactor 3.6.x được Spring Boot 3.3.5 quản lý.

## 2. Reactive Streams: subscription là một hợp đồng có vòng đời

Một `Publisher<T>` phát tín hiệu cho `Subscriber<T>` qua một `Subscription`. Trong Reactor, `Flux<T>` và `Mono<T>` thực thi hợp đồng này.

~~~text
Publisher<T>  ---onSubscribe(subscription)--->  Subscriber<T>
                 <------ request(n) ----------
                 ------ onNext(item) -------->
                 ------ onNext(item) -------->
                 ------ onComplete() -------->  [terminal]

hoặc           ------ onError(error) -------->  [terminal]

hoặc           <---------- cancel() ----------  [downstream hủy]
~~~

Ba tình huống cuối khác nhau:
- **Complete**: nguồn thông báo đã phát hết thành công; Subscriber nhận `onComplete`.
- **Error**: nguồn kết thúc bằng một lỗi; Subscriber nhận `onError`.
- **Cancel**: phía downstream gọi `Subscription.cancel()`; nó **không phải onComplete/onError gửi xuống subscriber**, và có thể xảy ra trước khi nguồn kết thúc.

Hợp đồng Reactive Streams nói về **ngừng yêu cầu/nhận thêm signals** sau cancel, trong phạm vi bất đồng bộ và race conditions. Nó không tự xác định HTTP status, transaction semantics, file descriptor cleanup hoặc lý do client đóng TCP.

### 2.1. Một request có thể tạo một subscription, nhưng đừng coi đó là định luật cho mọi publisher

Với annotated WebFlux controller trả `Flux`, framework thường là bên subscribe để viết HTTP response. Nhưng một logical request có thể kích hoạt nhiều publisher/inner subscriptions qua `flatMap`, `retryWhen`, `switchIfEmpty`, `zip` hoặc HTTP codec. Mỗi subscription có lifecycle riêng; ví dụ `retryWhen` có thể **subscribe lại** một cold source.

Vì vậy:
- Resource **per-subscription** phải được mở/đóng theo mỗi lượt subscribe.
- `doOnSubscribe` không mặc định chỉ chạy một lần trên mọi HTTP request trong mọi cấu hình.
- Một `Flux` được cache/share/hot multicast có thể không bị hủy upstream ngay khi **một** client rời đi.

### 2.2. Demand không đồng nghĩa giữ kết nối

`request(n)` mô tả số items downstream có thể nhận thêm (backpressure). `cancel()` chấm dứt subscription. Giảm demand không nhất thiết là cancel, và một subscriber tạm chậm không có nghĩa browser đã disconnect.

### 2.3. Terminal signals thường chỉ có một

Một nguồn chuẩn phát `onComplete` **hoặc** `onError` một lần, không cả hai. Cancellation là yêu cầu bất đồng bộ và có thể đua với terminal signal đang trên đường xử lý.

Điều này làm cho cleanup phải **idempotent** và không được phụ thuộc vào assumption một callback cụ thể sẽ luôn thắng mọi race.

## 3. Dòng sự kiện: từ HTTP client đến Reactor cancellation

### 3.1. SSE client chủ động đóng

~~~javascript
const source = new EventSource("/api/ticks");

source.addEventListener("tick", event => {
  console.log(event.data);
});

document.querySelector("#stop").addEventListener("click", () => {
  source.close();
});
~~~

Đây là đoạn browser JavaScript cho một trang đã có nút `#stop`, không phải project frontend đầy đủ. `EventSource.close()` yêu cầu ngừng EventSource connection và tự động reconnect; nó không gửi một HTTP endpoint "cancel" riêng.

Ở server:

~~~text
Browser EventSource
      |
      | HTTP GET /api/ticks
      v
Reactor Netty HTTP connection
      |
      v
WebFlux HandlerResultHandler / SSE writer
      |
      v
Flux<ServerSentEvent> subscription
      |
      +--- onNext(event 0) --> encoded bytes --> network
      +--- onNext(event 1) --> encoded bytes --> network
      |
      ... browser closes / network breaks ...
      |
      +--- adapter detects disconnect/write error
      |
      +--- may cancel response subscription
      |           |
      |           +--> doOnCancel
      |           +--> doFinally(CANCEL)
      |           +--> using/usingWhen cleanup
      |
      +--- or error/termination path according to transport/timing
~~~

**Sơ đồ thể hiện khả năng thường gặp**, không hứa một ánh xạ 1:1 rằng HTTP disconnect luôn báo chính xác một `CANCEL` tức thì. Trong thực tế có thể thấy `ON_ERROR` do write failure hoặc kết thúc request khác; một client mất mạng đột ngột đôi khi chỉ được phát hiện sau lần write tiếp theo/timeout.

### 3.2. Không có bảo đảm "client đã đọc xong sự kiện"

Server đã emit `onNext(event)` không chứng minh browser đã:
1. Nhận đủ TCP bytes.
2. Parse SSE event.
3. Chạy listener JavaScript.
4. Ghi nhận nghiệp vụ.
5. Lưu event bền vững.

Nếu sự kiện quan trọng cần **at-least-once delivery** hoặc acknowledgement, cần event IDs, replay store, consumer offset/ack protocol và idempotency. `onNext`/write completion không thay application-level acknowledgement.

### 3.3. Graceful close, abrupt disconnect và proxy

Client có thể dừng vì `EventSource.close()`, rời trang, network mất, refresh, request timeout hoặc reverse proxy ngắt idle connection. Proxy có thể giữ socket với upstream trong khi downstream browser đã đi, hoặc buffering/timeout làm delay phát hiện disconnect.

Không xây logic cleanup chỉ dựa vào "browser luôn gửi FIN tức thì". Cần:
- Bounded timeouts và server-side liveness policy.
- Periodic heartbeat nếu streaming protocol phù hợp.
- Upstream cancellation-aware clients.
- Cleanup per subscription và cleanup khi server shutdown.

## 4. Reactor operators: complete, error, cancel và finally

### 4.1. `doOnComplete` chỉ dành cho hoàn thành bình thường

~~~java
Flux<Long> stream = Flux.range(1, 3)
        .map(Integer::longValue)
        .doOnComplete(() -> recordCompleted());
~~~

`recordCompleted()` là fragment chưa định nghĩa. Callback chỉ chạy khi source hoàn thành thành công; nó **không đủ** để dọn resource với một stream vô hạn hoặc bị cancel.

### 4.2. `doOnError` chỉ nhận lỗi

~~~java
Flux<String> stream = fetchEvents()
        .doOnError(ex -> logSafeFailure(ex));
~~~

`fetchEvents`/`logSafeFailure` là fragments. DoOnError dành cho observability trên lỗi, không thực hiện retry/recovery và không tự chạy khi chỉ cancel. Tránh log raw headers/tokens hoặc message chứa dữ liệu cá nhân.

### 4.3. `doOnCancel` chạy khi subscription bị cancel

~~~java
Flux<Long> stream = Flux.interval(Duration.ofSeconds(1))
        .doOnCancel(() -> incrementCancelledSubscriptions());
~~~

Đối với Reactor, callback được thực thi trước khi cancel được chuyển upstream ở điểm operator đó. Nếu cancellation xảy ra vì `take(2)` hoặc `timeout`, callback có thể chạy dù không có browser đóng kết nối.

Không đánh đồng metric `cancelledSubscriptions` với số "người đóng tab": downstream operators, tests, retries, server shutdown và other cancellation paths đều có thể gây cancel.

### 4.4. `doFinally(SignalType)` bao phủ cả ba tình huống

~~~java
Flux<Long> stream = Flux.interval(Duration.ofSeconds(1))
        .doFinally(signal -> {
            switch (signal) {
                case ON_COMPLETE -> record("complete");
                case ON_ERROR -> record("error");
                case CANCEL -> record("cancel");
                default -> record("other");
            }
        });
~~~

`record` là một fragment chưa định nghĩa. Reactor `SignalType` có các hằng số khác, nhưng ba loại trên là quan trọng cho termination. Callback `doFinally` được gọi khi sequence kết thúc hoặc bị cancel; có thể chạy **sau khi terminal signal đã đi qua downstream**, và các `doFinally` nối tiếp có thể chạy thứ tự ngược.

**Cảnh báo trong test:** một `StepVerifier.verifyComplete()` đã return không phải lúc nào cũng bảo đảm các side effects ở `doFinally` bất đồng bộ đã hiển thị ngay; cần synchronization/latch/await có timeout khi assertions phụ thuộc callback đó.

### 4.5. Bảng so sánh callback

| Operator | onComplete | onError | cancel | Dùng cho |
| --- | --- | --- | --- | --- |
| `doOnComplete` (Flux) | Có | Không | Không | Theo dõi thành công |
| `doOnError` | Không | Có | Không | Log/metric lỗi |
| `doOnCancel` | Không | Không | Có | Theo dõi hủy |
| `doOnTerminate` | Có | Có | Không | Side effect khi có terminal signal |
| `doAfterTerminate` | Có | Có | Không | Side effect sau complete/error |
| `doFinally` | Có | Có | Có | Ghi metric kết thúc/latency |
| `using` | Có | Có | Có | Sở hữu/đóng tài nguyên đồng bộ |
| `usingWhen` | Có | Có | Có | Lifecycle tài nguyên với cleanup publisher async |

**Điểm mấu chốt:** `doFinally` là callback cho side effects; **không phải phép màu biến việc đóng một connection async thành một giao dịch có thể await**. Khi cleanup là async, `usingWhen` là abstraction mạnh hơn.

## 5. Tài nguyên phải thuộc subscription, không thuộc method controller

### 5.1. Anti-pattern: mở tài nguyên quá sớm

~~~java
@GetMapping("/events")
public Flux<Event> events() {
    ExternalSubscription subscription = registerListener();
    return subscription.events();
}
~~~

Đây là **fragment anti-pattern** với `Event` và `ExternalSubscription` chưa khai báo. Listener được mở ngay lúc controller method chạy, trước khi upstream reactive publisher được subscribe, và không có đường đóng khi request cancel. Nếu response thất bại trước subscription hoặc retry tạo nhiều subscribers, có thể leak.

Cần thiết kế producer dạng lazy:

~~~java
return Flux.defer(() -> {
    ExternalSubscription listener = registerListener();
    return listener.events()
            .doFinally(signal -> listener.close());
});
~~~

Đây vẫn là fragment minh họa, chỉ phù hợp nếu `close()` **đồng bộ, ngắn, idempotent** và listener chỉ thuộc đúng subscription này. Với resource ownership thực sự, ưu tiên `Flux.using`; với cleanup cần publisher async, dùng `Flux.usingWhen`.

### 5.2. `Flux.defer`

`Flux.defer(Supplier<Publisher<T>>)` xây một publisher mới cho **mỗi subscription**. Nó hữu ích để tránh mở listener khi chưa có subscription, nhưng không tự bảo đảm close nếu bạn quên gắn cleanup operator.

### 5.3. Một resource dùng chung cho nhiều clients

Nếu bạn đặt một WebSocket/Kafka consumer hoặc `Sinks.Many` global rồi nhiều HTTP SSE clients cùng subscribe, **một** client hủy không được phép `close()` shared resource cho tất cả.

Hai thiết kế khác nhau:
- **Per-client**: mỗi subscription có listener/resource riêng; `using`/`usingWhen` đóng đúng resource của client đó.
- **Shared hot source**: một resource phục vụ nhiều subscribers; lifetime thuộc application/shared service, dùng reference counting có kiểm soát hoặc application shutdown; per-client cleanup chỉ hủy **nhánh subscription của client**.

Không gắn `doFinally(sharedConnection::close)` trên từng client response, vì client đầu tiên rời đi có thể phá stream của mọi người.

## 6. `Flux.using`: mở/đóng tài nguyên đồng bộ

`Flux.using` giống tinh thần Java `try-with-resources` cho một publisher có lifecycle dài:

~~~java
Flux<String> lines = Flux.using(
        () -> openResource(),
        resource -> resource.events(),
        resource -> resource.close());
~~~

Fragment này cần `openResource()` trả resource có `events()` và `close()`. Reactor gọi resource supplier **khi subscribe**, sử dụng source publisher, rồi đóng resource khi stream complete, error hoặc cancel.

### 6.1. Quy tắc "một resource, một owner"

Mỗi subscription mới cần một resource riêng nếu resource không share-safe:
- Mở tài nguyên trong supplier của `using`, không từ một biến global eager.
- Chỉ resource creator/owner chính thức được close, không nhiều operators cùng release.
- Cleanup nên idempotent nếu môi trường bên ngoài có thể phát tín hiệu dừng thêm một lần.
- Không cất resource trong `ThreadLocal`: Reactor operators có thể đổi thread qua scheduler.
- Khi close có thể block, đừng thực hiện trong Netty event-loop callback; dùng async API hoặc scheduler thích hợp.

### 6.2. Cleanup khi `take(n)`

~~~java
Flux<Long> finiteView =
        Flux.using(
                () -> openCounterResource(),
                resource -> Flux.interval(Duration.ofMillis(50)),
                resource -> resource.close())
            .take(2);
~~~

`openCounterResource` là fragment. `take(2)` thường gửi cancellation upstream sau hai items; resource vẫn được cleanup. **`take` downstream có thể báo onComplete cho subscriber, trong khi upstream nhận cancel**. Do đó không dùng `doFinally(CANCEL)` làm bằng chứng duy nhất cho "client đứt kết nối": test `take` cũng tạo CANCEL.

### 6.3. Cleanup phải nhanh nếu đồng bộ

Nếu `close()` thực hiện:
- blocking network call lâu,
- `Future.get()`,
- chờ database lock,
- flush file hàng giây,

thì nó có thể chiếm event-loop thread khi cancellation đi qua operator. Khi tài nguyên hỗ trợ close bất đồng bộ, dùng `usingWhen`. Nếu bắt buộc close blocking legacy, isolate qua bounded worker và tôn trọng giới hạn queue/timeout; không gắn `Thread.sleep` vào `doFinally` trên Netty loop.

## 7. `Flux.usingWhen`: tài nguyên có cleanup bất đồng bộ

Khi resource mở và đóng đều là publishers, dùng `usingWhen`. Ví dụ nguyên tắc:

~~~java
Flux<Event> events = Flux.usingWhen(
        openAsyncConnection(),                      // Mono<Connection>
        connection -> connection.events(),           // Flux<Event>
        connection -> connection.closeAsync(),       // Mono<Void> on complete
        (connection, error) -> connection.closeAsync(), // Mono<Void> on error
        connection -> connection.closeAsync());      // Mono<Void> on cancel
~~~

Đây là **fragment** cho một API external giả định, không phải code runnable độc lập. `openAsyncConnection()`, `Connection.events()` và `closeAsync()` cần thực sự non-blocking, trả publishers và có resource ownership rõ.

### 7.1. Vì sao đủ ba cleanup paths?

Overload đầy đủ nhận:
1. `asyncComplete` khi publisher resource sử dụng hoàn tất bình thường.
2. `asyncError` khi lỗi; có thể điều chỉnh rollback/cleanup tùy error.
3. `asyncCancel` khi downstream cancel.

Nếu cleanup completion/error thất bại, `usingWhen` có quy tắc ưu tiên/suppression errors cần kiểm theo Reactor Javadoc, không tự cho rằng lỗi body gốc luôn còn nguyên như message trả cho client. **On cancel không có downstream consumer để nhận một error response mới**; lỗi cleanup phải được log/metric đúng layer và có retry/bù trừ nếu policy yêu cầu.

### 7.2. Resource đơn giản vs transaction

Ví dụ database reactive có thể dùng một transaction:
- **Complete** ⇒ commit.
- **Error** ⇒ rollback.
- **Cancel** ⇒ xử lý cancellation theo transaction policy (thường rollback nếu transaction còn mở).

Nhưng không tự kết luận dùng `usingWhen` là đủ thay `ReactiveTransactionManager` hoặc `TransactionalOperator` của Spring. Transaction management có nhiều edge cases (savepoints, context, driver, connection reuse, isolation). Với R2DBC, nên dùng Spring reactive transaction facilities, không tự chế lệnh commit/rollback trên mọi SSE subscription.

### 7.3. Không dùng `doFinally` thay thế indiscriminately

Sai với async close:

~~~java
return resource.events()
        .doFinally(signal ->
                resource.closeAsync().subscribe());
~~~

Fragment này “fire-and-forget”: cleanup subscribe tách rời, error khó giám sát và không được compose vào resource lifecycle. `usingWhen` cho bạn một operator quản lý completion/error/cancel cleanup có contract rõ hơn.

## 8. `Disposable`, Scheduler và cancellation của timer

`Flux.interval(...)` dùng một scheduler để phát các tick, và upstream subscription thường ngừng scheduling khi cancelled. Khi trả `Flux.interval` từ WebFlux handler, **không tự gọi `subscribe()` trong controller** để lưu một `Disposable` nếu chỉ muốn stream kết quả cho client.

Sai:

~~~java
@GetMapping("/wrong")
public Flux<Long> wrong() {
    Disposable orphan = Flux.interval(Duration.ofSeconds(1))
            .subscribe(i -> audit(i));
    return Flux.interval(Duration.ofSeconds(1));
}
~~~

Đây là fragment minh họa với `audit` chưa định nghĩa. `orphan` là subscription độc lập, client disconnect của returned Flux **không hủy** nó; nếu không dispose, timer/audit vẫn chạy. Sửa bằng cách return một publisher được compose:

~~~java
@GetMapping("/right")
public Flux<Long> right() {
    return Flux.interval(Duration.ofSeconds(1))
            .doOnNext(i -> recordSafeMetric(i));
}
~~~

`recordSafeMetric` cũng là fragment, nhưng side effect gắn với actual response subscription. Nếu cần một background broadcast dùng chung, quản lý lifecycle trong service application (khởi động/đóng theo bean lifecycle) chứ không khởi động `subscribe()` mới trên mỗi HTTP request.

### 8.1. `Disposable.dispose()` và `Subscription.cancel()`

Reactor `Disposable` được trả khi tự `subscribe(...)` thường cho phép `dispose()`, qua đó yêu cầu hủy subscription. Ở WebFlux controller, framework sở hữu subscriber của HTTP response; bạn **không cần** gọi dispose thủ công. Với custom scheduler hoặc shared consumer do application tự tạo, application phải nắm quyền sở hữu lifecycle và dispose ở shutdown.

## 9. SSE: heartbeat, reconnect và event IDs

### 9.1. Vì sao SSE cần heartbeat?

Một SSE stream có thể không có business event trong vài phút. Một số reverse proxies, load balancers hoặc browser/network middleboxes có idle timeouts; nếu không có bytes được truyền, connection có thể bị đóng. Heartbeat có thể:
- Phát SSE **comment** như `: keepalive`, được EventSource bỏ qua như event business.
- Phát một event `heartbeat` riêng, frontend có thể nhận/ignore.
- Phát ping theo infrastructure-specific protocol khi phù hợp.

Heartbeat giúp **phát hiện/giữ connection** ở một số môi trường, không bảo đảm mọi proxy cho phép stream sống vô hạn. Thêm intervals phù hợp giới hạn idle timeout, và kiểm proxy response buffering.

### 9.2. SSE event format

~~~text
id: 42
event: book-updated
data: {"id":7,"version":3}

: keepalive

~~~

Dòng rỗng kết thúc một SSE event. `id` có thể giúp client gửi `Last-Event-ID` khi reconnect. **EventSource tự reconnect theo browser policy** nhưng server chỉ có thể replay mất event nếu ứng dụng giữ history/offset; số ID được phát không tự bảo đảm delivery exactly-once.

### 9.3. EventSource reconnect có thể mở subscription mới

Nếu client mất kết nối và browser reconnect:
- Server có thể thấy **subscription cũ cancel/close**.
- Request mới tạo **subscription mới** và resource mới.
- Nếu có replay dựa trên Last-Event-ID, việc đọc offset/authorizing stream phải tính đến user/tenant và retention.
- Duplicate events là khả năng thực tế; frontend phải idempotent nếu apply side effects.

Không thiết kế cleanup "cũ xong mới được mở mới": network race có thể khiến stream mới mở trước khi stream cũ được server phát hiện đã chết.

### 9.4. Ứng dụng nên giới hạn stream lifetime

Một endpoint SSE có thể stream indefinitely, nhưng phải có chính sách:
- Giới hạn subscription concurrency per user/tenant nếu cần.
- Giới hạn backend listeners/connections và số lần reconnect.
- Heartbeat / idle timeout / maximum session lifetime.
- Backpressure/slow consumer policy.
- Graceful shutdown/rolling deploy strategy.
- Auth token expiry/re-auth behavior.

Giữ SSE vô hạn không đồng nghĩa giữ transaction DB mở vô hạn; thường không làm vậy.

## 10. Client disconnect không phải lúc nào cũng là `CANCEL` ngay

### 10.1. Không thể luôn biết ngay người dùng đã đóng tab

Với TCP, server có thể chỉ phát hiện một disconnect khi:
- Đọc/ghi socket nhận lỗi hoặc EOF.
- Transport/HTTP server callback báo channel inactive.
- Keepalive/heartbeat hay idle timeout phát hiện.
- Proxy upstream connection bị đóng.

Nếu server không gửi dữ liệu trong thời gian dài, một network break có thể chưa được thấy ngay. Một pipeline `Flux.never()` không phát gì còn khiến application không dễ nhận ra client đã biến mất, tùy adapter/proxy. Vì vậy streaming nên cân nhắc heartbeat/liveness và cleanup on timeout.

### 10.2. `doFinally` không đo "số tab đã đóng"

Thống kê lý tưởng cần phân loại:
- `ON_COMPLETE`: stream kết thúc theo hợp đồng.
- `ON_ERROR`: stream lỗi từ upstream, encoding hoặc transport.
- `CANCEL`: downstream không cần dữ liệu từ một subscription này nữa.
- Network diagnostics: riêng logs/metrics của socket/HTTP, proxy disconnect.
- Business session changes: login/logout/revocation, không phải raw transport.

Cùng một client ngừng stream có thể không phát đúng cùng một terminal signal trong mọi stack/version.

### 10.3. `doOnError` trên source có thấy lỗi ghi socket không?

Không phải luôn. Một lỗi socket có thể xảy ra **downstream của source Flux** trong HTTP writer, rồi writer hủy source; `doOnError` trên upstream source có thể không nhận onError mà nhận CANCEL. Do đó muốn quan sát transport errors phải dùng instrumentation ở WebFlux/Netty layer hoặc server metrics, ngoài doOnError trên business publisher.

## 11. Cleanup khi response đã commit

Streaming HTTP thường ghi headers/status trước khi body hoàn tất. Khi SSE đã phát vài events, status 200 có thể đã **commit**. Sau đó upstream exception:
- Không chắc có thể đổi thành status 500 cùng `ProblemDetail`.
- Không chắc có thể gửi event "error" hợp lệ cho client đã disconnect.
- Có thể cần đóng stream và để client reconnect.
- Nếu protocol cho phép in-band error event, phải thiết kế event schema, nhưng không thay HTTP status đã gửi.

Với `ServerHttpResponse.isCommitted()`, bạn biết response đã được đánh dấu committed trong abstraction, nhưng không nên tự diễn giải nó như rollback switch. Error handling trước commit và sau commit là hai bài toán khác nhau.

### 11.1. Đừng đăng ký cleanup bằng `then` sau một stream vô hạn

~~~java
return response.writeWith(dataBuffers)
        .then(Mono.fromRunnable(resource::close));
~~~

Đây là fragment; nếu publisher streaming vô hạn, `then` có thể **không chạy** cho đến complete, và khi bị cancel, `then` không phải cơ chế cleanup tin cậy. Dùng resource operator `using`/`usingWhen` hoặc `doFinally` phù hợp lifecycle.

## 12. Streaming DataBuffer: pooled memory và ownership

Khi stream bytes trực tiếp:

~~~java
Flux<DataBuffer> body = request.getBody();
return response.writeWith(body);
~~~

Đây là fragment, không phải một proxy HTTP hoàn chỉnh. `DataBuffer` có thể backed by pooled Netty `ByteBuf`; release/retain đúng nơi đặc biệt quan trọng khi request/response bị cancel.

### 12.1. Quy tắc cơ bản

- **Producer sở hữu** buffer trong thời gian chưa bàn giao cho downstream.
- Khi đã gửi `DataBuffer` tới `ServerHttpResponse.writeWith(...)`, response writer có trách nhiệm tiêu thụ/phối hợp release theo contract; không release cùng buffer **trước khi writer đọc**.
- Nếu ứng dụng tự đọc buffer rồi **không** chuyển nó đi, cần `DataBufferUtils.release(buffer)` khi xử lý xong, kể cả error paths.
- Nếu một operator bỏ/discard buffers trước khi downstream nhận chúng, `doOnDiscard(DataBuffer.class, DataBufferUtils::release)` có thể hữu ích khi operator hỗ trợ discard hooks.
- Cancellation có thể khiến buffers đã buffered/prefetched bị discard; phải kiểm actual operator semantics và test Netty leak-detection trong môi trường phù hợp.
- Nếu giữ buffer sang asynchronous task/subscriber khác, `DataBufferUtils.retain`/`release` cần cân bằng theo ownership; không dùng buffer đã release.

**Đừng blindly gọi release ở tất cả operators**: double release hoặc use-after-release có thể phá dữ liệu/native memory. Dựa trên contract của Spring/Reactor codec, khi không cần thao tác raw bytes thì **để codecs/Resource abstractions** quản lý là tốt nhất.

### 12.2. Anti-pattern: release trước khi ghi

~~~java
Flux<DataBuffer> broken = source
        .doOnNext(DataBufferUtils::release);

return response.writeWith(broken);
~~~

Sai vì response writer nhận một buffer có thể đã release.

### 12.3. Anti-pattern: consume mà không release

~~~java
return DataBufferUtils.join(request.getBody())
        .map(buffer -> {
            byte[] bytes = new byte[buffer.readableByteCount()];
            buffer.read(bytes);
            return bytes; // nếu pooled, chưa release!
        });
~~~

Ngoài thiếu release, `join` không giới hạn có thể gây memory exhaustion. Đối với body nhỏ, dùng overload `join(publisher, maxByteCount)` và:

~~~java
return DataBufferUtils.join(request.getBody(), 1024)
        .map(buffer -> {
            try {
                byte[] bytes = new byte[buffer.readableByteCount()];
                buffer.read(bytes);
                return bytes;
            } finally {
                DataBufferUtils.release(buffer);
            }
        });
~~~

Đây là fragment cần `request` và các imports; quá max bytes sẽ gây `DataBufferLimitException`. Với payload lớn, **không** aggregate; stream sang file/object store có giới hạn rõ và xử lý partial upload/cancel.

### 12.4. Cancellation khi ghi file

Nếu dùng `DataBufferUtils.write(...)`, hiểu contract của overload đang dùng:
- Một số overload **không tự release source DataBuffers**; docs yêu cầu bạn subscribe `DataBufferUtils.releaseConsumer()` cho source buffers khi cần.
- Các overload ghi tới Path hoặc AsynchronousFileChannel có ownership và completion semantics riêng.
- Khi upload bị cancel, file có thể là **partial file**. Cần chính sách xóa temp file hoặc sử dụng staged upload rồi atomic rename khi complete.
- Đừng chuyển một file upload chưa hoàn tất thành "thành công" trong database chỉ vì đã mở file và ghi vài chunks.

## 13. Cancellation có dừng upstream thật không?

### 13.1. Reactive HTTP client như WebClient

Nếu handler stream dữ liệu từ `WebClient`:

~~~java
return webClient.get()
        .uri("/upstream/events")
        .retrieve()
        .bodyToFlux(Event.class);
~~~

Đây là fragment có bean `WebClient` và type `Event`. Khi subscriber cancel, Reactor Netty client có thể cancel/đóng exchange hoặc ngừng đọc theo implementation/timing, giúp tránh dùng tài nguyên thừa. Nhưng không đảm bảo remote server đã rollback tác dụng hoặc không phát thêm events trước khi nhận disconnect.

### 13.2. JDBC hoặc legacy blocking code

~~~java
return Flux.fromIterable(ids)
        .map(id -> blockingRepository.findById(id));
~~~

Nếu `blockingRepository` là JDBC/JPA sync, `map` có thể block event loop. Cancel downstream khi JDBC call đang chạy **không chắc chắn interrupt được driver** hoặc rollback query. Cần:
- Driver statement/query/socket timeouts.
- Bounded executor/scheduler cho blocking legacy calls.
- Connection pool limits, circuit breaker/overload policy.
- Idempotency và transaction boundaries.
- Explicit cancel API nếu driver hỗ trợ, có race handling.

Với I/O reactive hoàn toàn (R2DBC/WebClient), compose publisher không gọi `block()`. Không hứa "return Flux" tự làm database non-blocking.

### 13.3. CPU-bound work

Một phép tính CPU-bound lớn có thể không chú ý cancellation cho đến khi hoàn thành một khối tính toán. Nếu muốn interruptible, chia thành chunks nhỏ, kiểm cancellation/cooperative flags đúng API và phân bổ compute pool phù hợp. Hủy subscriber không tự dừng một JVM native CPU routine ngay lập tức.

## 14. Timeout, retry và cancel khác nhau

### 14.1. `timeout` thường tạo error rồi cancel upstream

~~~java
Flux<Long> guarded = Flux.interval(Duration.ofSeconds(2))
        .timeout(Duration.ofMillis(500));
~~~

Ở downstream, `timeout` phát `TimeoutException`. Ở upstream `Flux.interval`, operator có thể nhận `CANCEL` vì timeout đã hủy subscription cũ. Vì vậy cùng một request có thể có:
- downstream `doFinally(ON_ERROR)` sau timeout,
- upstream `doFinally(CANCEL)` do timeout cancel.

Kết luận: **SignalType phụ thuộc vị trí đặt operator**, không phải nhãn tuyệt đối của toàn HTTP request.

### 14.2. Retry tạo lại resource và subscription

~~~java
Flux<Event> stream = openEvents()
        .retryWhen(Retry.backoff(3, Duration.ofMillis(200)));
~~~

Đây là fragment. Khi lỗi, `retryWhen` có thể subscribe lại, mở một resource mới. Với `using`/`usingWhen`, lần subscribe cũ phải được cleanup trước/tương ứng lifecycle trước khi resource mới được dùng. Tránh retry vô hạn trên SSE: có thể gây reconnect storm, duplicated side effects và hết subscription quotas.

### 14.3. Một request bị cancel không đồng nghĩa timeout response 504

HTTP 504 là gateway timeout theo semantics; 503 là service unavailable; 408 là request timeout theo server policy. Client disconnect thường **không còn response receiver** để gửi error body/status mới, nên đừng tự chuyển mọi `CANCEL` thành một HTTP 504.

## 15. Shared streams: `publish().refCount()`, `share()` và lifecycle

Nếu service giữ một nguồn sự kiện "hot" dùng chung:

~~~java
Flux<Event> shared = source.publish().refCount(1);
~~~

Đây là fragment có `source` phát event objects. `refCount(1)` subscribe upstream khi có ít nhất một subscriber và có thể cancel upstream khi số subscribers về 0. Tuy nhiên behavior chi tiết còn phụ thuộc `refCount(n,gracePeriod)`, sources và operators khác.

**Quan trọng:** nếu resource dùng chung thuộc toàn ứng dụng, không close nó ngay khi một SSE subscriber cancel. Có thể dùng:
- Sinks.Many với application-level owner.
- Shared broker consumer có ref counting.
- Per-client subscription disposable được quản lý, không đóng broker consumer.
- Replay/history store có giới hạn khi cần Last-Event-ID.
- Backpressure/slow consumer policy cho từng client.

### 15.1. `cache()` có thể giữ dữ liệu và upstream

Một `Flux.cache()` hoặc `replay()` có thể giữ items trong memory theo chính sách và cho subscriber mới xem lại. Với infinite streams, cache không giới hạn có nguy cơ memory leak và upstream không dừng khi người cuối đi. Đừng thêm `cache()` vào SSE chỉ để "tránh duplicate DB calls" mà chưa xác định lifecycle/retention.

### 15.2. `Sinks.Many`: per-subscriber cleanup vs shared sink

Khi nhiều SSE clients đọc từ một shared sink, hủy một subscriber cần dừng nhánh nhận của subscriber đó; nó không tự hoàn thành shared sink cho mọi clients. Nếu bạn tự đăng ký listener trên sink/hot data structure, dọn listener reference/metadata để tránh growing lists, và theo dõi `currentSubscriberCount` hoặc metrics phù hợp.

## 16. Ví dụ runnable: Spring Boot 3.3.5 / Java 17 / WebFlux SSE

Ví dụ có ba endpoint:
- `GET /api/stream`: SSE vô hạn, mỗi subscription mở một resource `StreamLease` và đóng khi complete/error/cancel qua `Flux.using`; ghi counters.
- `GET /api/finite`: SSE hữu hạn gồm hai sự kiện để test HTTP encoding/response completion.
- `GET /api/metrics`: snapshot counters `active`, `closed`, `cancelled` mang tính chẩn đoán.

Demo không dùng DB, Kafka, credentials, proxy hay external HTTP dependencies. Mỗi `StreamLease` chỉ chứa một counter, vì vậy `close` **nhanh, đồng bộ** và an toàn cho `Flux.using`. Khi thay bằng broker listener/DB connection có close async, áp dụng `usingWhen` thay vì ngồi chờ trong `close`.

~~~text
webflux-stream-lifecycle/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/com/example/streamdemo/
    │   ├── StreamDemoApplication.java
    │   ├── stream/StreamLease.java
    │   ├── stream/StreamService.java
    │   └── web/StreamController.java
    └── test/java/com/example/streamdemo/
        ├── StreamServiceTest.java
        └── StreamHttpTest.java
~~~

### 16.1. Gradle config

`settings.gradle`:

~~~groovy
rootProject.name = 'webflux-stream-lifecycle'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

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
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.projectreactor:reactor-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Chỉ dùng `spring-boot-starter-webflux` để Boot chạy Reactor Netty theo setup tiêu chuẩn. Java 17+ và Gradle wrapper tương thích cần có trong project khi chạy lệnh. `spring-boot-starter-web` có thể khiến Boot chọn MVC type nếu dùng cùng WebFlux starter.

### 16.2. Main application

`src/main/java/com/example/streamdemo/StreamDemoApplication.java`:

~~~java
package com.example.streamdemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class StreamDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(StreamDemoApplication.class, args);
    }
}
~~~

### 16.3. `StreamLease`: chủ sở hữu resource per subscription

`src/main/java/com/example/streamdemo/stream/StreamLease.java`:

~~~java
package com.example.streamdemo.stream;

import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;

final class StreamLease implements AutoCloseable {

    private final AtomicInteger active;
    private final AtomicInteger closed;
    private final AtomicBoolean disposed = new AtomicBoolean();

    StreamLease(AtomicInteger active, AtomicInteger closed) {
        this.active = active;
        this.closed = closed;
        active.incrementAndGet();
    }

    @Override
    public void close() {
        if (disposed.compareAndSet(false, true)) {
            active.decrementAndGet();
            closed.incrementAndGet();
        }
    }
}
~~~

`AtomicBoolean.compareAndSet(false, true)` bảo đảm close idempotent, tránh decrement active hai lần nếu một thành phần khác vô tình cố đóng thêm. Việc dùng AtomicIntegers không đại diện cho distributed metrics across pods; production cần monitoring ngoài JVM hoặc labeled counters/gauges thích hợp.

### 16.4. `StreamService`: tạo resource đúng lúc subscribe

`src/main/java/com/example/streamdemo/stream/StreamService.java`:

~~~java
package com.example.streamdemo.stream;

import java.time.Duration;
import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Flux;
import reactor.core.publisher.SignalType;

@Service
public class StreamService {

    private final AtomicInteger active = new AtomicInteger();
    private final AtomicInteger closed = new AtomicInteger();
    private final AtomicInteger cancelled = new AtomicInteger();

    public Flux<ServerSentEvent<String>> events() {
        return Flux.using(
                () -> new StreamLease(active, closed),
                lease -> Flux.interval(
                        Duration.ZERO, Duration.ofMillis(100))
                        .map(index -> ServerSentEvent.<String>builder()
                                .event("tick")
                                .id(Long.toString(index))
                                .data("tick-" + index)
                                .build()),
                StreamLease::close)
                .doFinally(signal -> {
                    if (signal == SignalType.CANCEL) {
                        cancelled.incrementAndGet();
                    }
                });
    }

    public Flux<ServerSentEvent<String>> finite() {
        return Flux.just("alpha", "beta")
                .map(word -> ServerSentEvent.<String>builder()
                        .event("word")
                        .data(word)
                        .build());
    }

    public int activeCount() {
        return active.get();
    }

    public int closedCount() {
        return closed.get();
    }

    public int cancelledCount() {
        return cancelled.get();
    }
}
~~~

Các quyết định có chủ đích:
1. Không tạo `StreamLease` ở controller hoặc singleton constructor: `Flux.using` gọi supplier khi **mỗi subscriber** subscribe.
2. `Flux.interval(Duration.ZERO, 100 ms)` phát tick không dùng `Thread.sleep`. Event loop không bị giữ trong lúc chờ timer.
3. Tạo `ServerSentEvent` có event name `tick`, event id số thứ tự và text payload.
4. `StreamLease::close` do `using` gọi trên cả complete/error/cancel; nó idempotent.
5. `doFinally(CANCEL)` chỉ ghi **subscription cancellation**, không được quảng cáo là bằng chứng 100% client rời trang.
6. `finite()` tách ra để test HTTP body SSE hữu hạn.
7. `active` có thể lên/xuống khi clients subscribe/cancel; metrics endpoint chỉ là snapshot bất đồng bộ, không phải transactional invariant cùng thời điểm.
8. Nếu client mất mạng âm thầm, `active` có thể vẫn dương đến khi transport phát hiện/timeout. Tăng heartbeat/monitoring, không tự force-close khi một metric thay đổi.

### 16.5. Controller SSE + metrics

`src/main/java/com/example/streamdemo/web/StreamController.java`:

~~~java
package com.example.streamdemo.web;

import com.example.streamdemo.stream.StreamService;
import java.util.Map;
import org.springframework.http.MediaType;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api")
public class StreamController {

    private final StreamService streams;

    public StreamController(StreamService streams) {
        this.streams = streams;
    }

    @GetMapping(
            path = "/stream",
            produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public Flux<ServerSentEvent<String>> stream() {
        return streams.events();
    }

    @GetMapping(
            path = "/finite",
            produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public Flux<ServerSentEvent<String>> finite() {
        return streams.finite();
    }

    @GetMapping(
            path = "/metrics",
            produces = MediaType.APPLICATION_JSON_VALUE)
    public Mono<Map<String, Integer>> metrics() {
        return Mono.fromSupplier(() -> Map.of(
                "active", streams.activeCount(),
                "closed", streams.closedCount(),
                "cancelled", streams.cancelledCount()));
    }
}
~~~

Không có `subscribe()` hoặc `block()` trong controller. WebFlux quản lý subscription và SSE HTTP writer. Vì là demo, endpoint metrics công khai; production metrics phải tuân deployment security policy và không lộ dữ liệu client/user chi tiết.

### 16.6. Vì sao demo không dùng `doFinally(close)` để đóng resource?

`doFinally(lease::close)` vẫn có thể đúng với một resource **độc lập per subscriber**, close nhanh và được tạo đúng lúc; nhưng `using` biểu đạt **quyền sở hữu** rõ hơn và tránh lỗi mở resource eagerly ngoài reactive chain. Khi close cần non-blocking publisher, chuyển sang `usingWhen`.

## 17. Unit test: cancellation chắc chắn do test chủ động tạo

`StepVerifier` có thể kiểm subscription lifecycle **deterministically ở Reactor level**, không cần giả lập mạng hỏng.

`src/test/java/com/example/streamdemo/StreamServiceTest.java`:

~~~java
package com.example.streamdemo;

import com.example.streamdemo.stream.StreamService;
import java.time.Duration;
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Flux;
import reactor.core.publisher.SignalType;
import reactor.test.StepVerifier;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicReference;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class StreamServiceTest {

    @Test
    void cancelStopsSourceAndReleasesOwnedResource() {
        StreamService service = new StreamService();

        StepVerifier.create(service.events())
                .expectNextCount(2)
                .thenCancel()
                .verify(Duration.ofSeconds(3));

        assertEquals(0, service.activeCount());
        assertEquals(1, service.closedCount());
    }

    @Test
    void usingClosesWhenSourceCompletesNormally() {
        AtomicBoolean closed = new AtomicBoolean();

        Flux<String> flux = Flux.using(
                () -> "resource",
                resource -> Flux.just("a", "b"),
                resource -> closed.set(true));

        StepVerifier.create(flux)
                .expectNext("a", "b")
                .verifyComplete();

        assertTrue(closed.get());
    }

    @Test
    void usingClosesWhenSourceErrors() {
        AtomicBoolean closed = new AtomicBoolean();

        Flux<String> flux = Flux.using(
                () -> "resource",
                resource -> Flux.concat(
                        Flux.just("a"),
                        Flux.error(new IllegalStateException("broken"))),
                resource -> closed.set(true));

        StepVerifier.create(flux)
                .expectNext("a")
                .expectErrorMessage("broken")
                .verify();

        assertTrue(closed.get());
    }

    @Test
    void doFinallySeesCancelButThatDoesNotMeanNetworkDisconnect() {
        AtomicReference<SignalType> reason = new AtomicReference<>();

        Flux<Long> flux = Flux.interval(Duration.ofMillis(10))
                .doFinally(reason::set);

        StepVerifier.create(flux)
                .expectNextCount(2)
                .thenCancel()
                .verify(Duration.ofSeconds(3));

        // doFinally callback có thể trễ so với downstream;
        // không assert reason.get() ngay tức thì ở đây.
    }
}
~~~

**Giải thích assertions:**
- Test đầu dùng **test subscriber tự thenCancel**, không có TCP client. Nó chứng minh `using` cleanup theo cancellation, **không chứng minh Netty phát hiện browser close trong 0 ms**.
- Test complete/error chứng minh close ở hai nhánh khác.
- Test cuối cố ý không assert `doFinally` ngay sau verify vì callbacks downstream/upstream có ordering subtleties; nếu cần chắc chắn reason, hãy dùng `CountDownLatch` trong callback và `await` với timeout thay vì `Thread.sleep` vô hạn.
- Dữ liệu chính xác của hai ticks không được assert vì timestamp/scheduler có thể thay đổi; chỉ đếm số items rồi cancel.
- Với `Flux.using` sync cleanup đơn giản, trạng thái resource đóng có thể kiểm ngay sau StepVerifier termination/cancellation trong demo.
- Tất cả tests nên hoàn thành trong vài giây khi scheduler hoạt động bình thường; CI chậm vẫn có thể gây timeout test nếu máy quá tải, cần cấu hình phù hợp.

### 17.1. Test `doFinally(CANCEL)` bằng latch khi cần

Nếu muốn assert chính xác callback:

~~~java
CountDownLatch finalized = new CountDownLatch(1);
AtomicReference<SignalType> reason = new AtomicReference<>();

Flux<Long> flux = Flux.interval(Duration.ofMillis(10))
        .doFinally(signal -> {
            reason.set(signal);
            finalized.countDown();
        });

StepVerifier.create(flux)
        .expectNextCount(2)
        .thenCancel()
        .verify(Duration.ofSeconds(3));

assertTrue(finalized.await(2, TimeUnit.SECONDS));
assertEquals(SignalType.CANCEL, reason.get());
~~~

Đây là **fragment cho một test JUnit** có imports `CountDownLatch`, `TimeUnit`, `Flux`, `StepVerifier`, `AtomicReference` và assertions. Dùng bounded `await` trong test, **không** dùng `CountDownLatch.await()` trong event-loop handler ở production.

## 18. WebTestClient: kiểm SSE thật mà không giả định disconnect tức thì

Test qua HTTP/Netty có thể xác nhận stream hữu hạn được encode thành SSE, còn cancellation service-level đã được test ở mục trước.

`src/test/java/com/example/streamdemo/StreamHttpTest.java`:

~~~java
package com.example.streamdemo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class StreamHttpTest {

    @Autowired
    WebTestClient client;

    @Test
    void finiteSseHasEventFramingAndCompletes() {
        client.get()
                .uri("/api/finite")
                .accept(MediaType.TEXT_EVENT_STREAM)
                .exchange()
                .expectStatus().isOk()
                .expectHeader().contentTypeCompatibleWith(
                        MediaType.TEXT_EVENT_STREAM)
                .expectBody(String.class)
                .value(body -> {
                    assertTrue(body.contains("event:word"));
                    assertTrue(body.contains("data:alpha"));
                    assertTrue(body.contains("data:beta"));
                });
    }

    @Test
    void metricsEndpointIsReadable() {
        client.get()
                .uri("/api/metrics")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.active").isNumber()
                .jsonPath("$.closed").isNumber()
                .jsonPath("$.cancelled").isNumber();
    }
}
~~~

Không cần sleep hoặc mở vô hạn connection trong test HTTP này. Khi muốn test real TCP disconnect:
1. Dùng một client có API hủy response-body subscription/đóng connection có kiểm soát.
2. Nhận ít nhất một SSE event để biết stream thật sự đã được subscribe và có hoạt động I/O.
3. Hủy body subscription hoặc đóng client connection.
4. Chờ **bounded deadline** cho metric `active` về giá trị phù hợp, không assert tức thì.
5. Test cả proxy/load balancer thật nếu production có các tầng đó.

Không bịa assertion deterministic “Netty luôn phát CANCEL trong 1 ms” ở mọi OS/container/CI. HTTP tests và Reactor unit tests **bổ sung cho nhau**.

### 18.1. Ví dụ WebTestClient chủ động cancel response body

~~~java
FluxExchangeResult<ServerSentEvent<String>> result =
        client.get()
                .uri("/api/stream")
                .accept(MediaType.TEXT_EVENT_STREAM)
                .exchange()
                .expectStatus().isOk()
                .returnResult(
                        new ParameterizedTypeReference<ServerSentEvent<String>>() {});

StepVerifier.create(result.getResponseBody())
        .expectNextCount(2)
        .thenCancel()
        .verify(Duration.ofSeconds(5));
~~~

Fragment này cần imports `FluxExchangeResult`, `ServerSentEvent`, `ParameterizedTypeReference`, `StepVerifier`, `Duration` và field `WebTestClient client`. Nó chủ động cancel downstream body publisher; không khẳng định HTTP connection/socket được server quan sát ra sao ở từng transport/runtime. Muốn assert server cleanup, dùng bounded polling/await trên server metrics và giữ test isolation.

## 19. Chạy demo bằng curl

Ở project có Gradle wrapper hợp lệ:

~~~bash
./gradlew test
./gradlew bootRun
~~~

Trên Windows PowerShell:

~~~powershell
.\gradlew.bat test
.\gradlew.bat bootRun
~~~

Chạy các lệnh theo thứ tự ở shell, không khởi động `bootRun` nếu tests chưa hoàn tất. Các file `build.gradle`/`settings.gradle` không tự tạo Gradle wrapper; nếu thiếu, cần tạo wrapper bằng Gradle tương thích.

### 19.1. Stream không kết thúc

~~~bash
curl -N -i 'http://localhost:8080/api/stream' \
  -H 'Accept: text/event-stream'
~~~

Ví dụ payload xuất hiện lặp lại:

~~~text
id:0
event:tick
data:tick-0

id:1
event:tick
data:tick-1

id:2
event:tick
data:tick-2

~~~

Trong terminal, nhấn Ctrl+C để hủy phía client. `curl -N` tắt output buffering của curl, giúp quan sát events ngay hơn. **Không** diễn giải ví dụ này là raw HTTP bytes luôn có đúng thứ tự/line endings trên mọi server; Spring SSE encoder có thể sắp xếp fields khác nhau theo implementation.

### 19.2. Quan sát counters

~~~bash
curl -i 'http://localhost:8080/api/metrics'
~~~

Ví dụ khi đang có một subscriber:

~~~json
{"active":1,"closed":0,"cancelled":0}
~~~

Sau khi cancel đã được server quan sát và cleanup xong, có thể thấy:

~~~json
{"active":0,"closed":1,"cancelled":1}
~~~

**Chỉ là output ví dụ cho một JVM mới chạy với một subscriber**. Nếu có nhiều clients, reconnect, HTTP tests hoặc timing khác nhau, counters khác. Browser/client disconnect không luôn làm chúng đổi ngay lập tức.

### 19.3. SSE hữu hạn

~~~bash
curl -N -i 'http://localhost:8080/api/finite'
~~~

Dự kiến HTTP 200, `Content-Type: text/event-stream` và hai events, rồi response kết thúc. Cách này giúp phân biệt một stream `ON_COMPLETE` có thật với một stream bị cancel.

### 19.4. Test trình duyệt

~~~javascript
const events = new EventSource("http://localhost:8080/api/stream");
events.addEventListener("tick", e => console.log(e.lastEventId, e.data));

// Sau đó:
events.close();
~~~

Nếu frontend nằm ở **origin khác**, phải cấu hình **CORS cho SSE GET** tương ứng, và xem chính sách cookies/auth nếu dùng credentials. Demo không tự bật CORS, nên ví dụ browser này dễ kiểm nhất từ trang cùng origin hoặc môi trường development có CORS được phép. Không thêm wildcard origin + credentials một cách tùy tiện.

## 20. Cleanup tài nguyên thực: file, subscription broker, connection, cursor

| Tài nguyên | Khi mở | Cleanup đúng | Cẩn trọng |
| --- | --- | --- | --- |
| Timer `Flux.interval` | Khi subscribe | Cancel upstream schedule | Không tự subscribe tạo timer orphan |
| Per-client message listener | Khi subscriber đăng ký | Unregister listener đúng ID/token | Không unregister shared listener toàn app |
| Broker topic subscription | Khi tạo streaming subscription | Cancel/close tương ứng | Shared consumer có owner riêng |
| Database R2DBC cursor/connection | Khi reactive query/transaction bắt đầu | Driver reactive close/rollback theo framework | Không giữ DB transaction vô hạn cho SSE |
| JDBC cursor (blocking) | Trong bounded worker | Close connection/result set + driver timeout | Cancel signal không chắc interrupt query |
| InputStream/FileChannel | Khi bắt đầu đọc file | Close channel on complete/error/cancel | Blocking close không chạy trên Netty loop |
| File upload temp file | Khi tạo staged file | Delete temp on error/cancel, atomic finalize on success | Tránh partial upload được công nhận thành công |
| DataBuffer/Netty ByteBuf | Khi cấp phát/nhận buffer | Release đúng owner, discard hook khi cần | Double release/use-after-release |
| WebClient upstream HTTP | Khi downstream subscribe | Cancel body publisher/network exchange | Remote side effects không rollback |
| Thread pool/Scheduler shared | Lúc bean start | Dispose ở application shutdown | Không shutdown pool global theo mỗi client |
| Hot source/Sink dùng chung | Lúc application setup | Close theo shared owner/ref count | Một client cancel không dừng mọi clients |

Không mở resource như singleton rồi đóng nó bằng `doFinally` trên **mọi** user stream: đó là nguồn của nhiều lỗi “người dùng A ngắt kết nối làm B mất dữ liệu”.

## 21. Shutdown và rolling deployment

### 21.1. Graceful shutdown không giống mọi stream đều complete

Khi deployment rolling restart:
- Server có thể ngừng nhận connections mới nhưng long-lived SSE còn đang hoạt động.
- Grace period của HTTP server, load balancer và orchestrator có thể giới hạn thời gian chờ.
- Nếu grace period hết, connection vẫn có thể bị cắt và Reactor stream nhận cancellation/error tùy stack.
- Browser EventSource có thể tự reconnect đến pod mới.
- Nếu cần replay, event offsets phải lưu bên ngoài pod.

Với Spring Boot, cấu hình graceful shutdown và phase timeout theo phiên bản, rồi test thực tế với long-lived streams; đừng giả định server sẽ chờ vô hạn.

### 21.2. Không giữ mutable state per-client trong static map mãi mãi

Nếu quản lý subscription registry, phải unregister khi complete/error/cancel, giới hạn số entries, tránh giữ `ServerWebExchange`/credentials/body buffers lâu dài. Nếu process chết đột ngột, không có `doFinally` nào chạy được — phải dựa vào TTL/leases/recovery ở external resources.

### 21.3. Distributed cancellation

Trong hệ nhiều replicas:
- Mỗi HTTP connection thuộc một server instance.
- Redis/Kafka/DB cursor có thể nằm ngoài instance và cần ownership/lease semantics.
- Reconnect có thể đến replica khác.
- Cleanup của replica cũ có thể chậm hoặc không chạy khi node crash.
- Dùng TTL, durable offsets, idempotency và external lease expiration khi trạng thái sống lâu quan trọng.

## 22. Khả năng quan sát và metric đúng nghĩa

Nên đo:
- Active SSE subscriptions theo endpoint/feature (không gắn raw user ID làm high-cardinality label).
- Subscriptions completed/errored/cancelled theo signal, **không** gọi cancelled là "user closed tab".
- Duration và bytes/events delivered (định nghĩa rõ "sent" vs client acknowledged).
- Resource leases opened/closed, pending cleanup, cleanup error count.
- Upstream client/DB pool active/idle, cancellations, driver timeout rates.
- Netty HTTP connections, network write failures, proxy idle timeouts.
- Reconnect rate, Last-Event-ID replay lag và duplicate event handling.
- Scheduler queue/threads cho any blocking legacy cleanup.
- Unreleased DataBuffer/direct memory/leak detector logs trong staging.

Khi log, chỉ dùng safe trace/request IDs; không log Authorization, cookies, raw SSE personal payload hoặc entire client IP history trái policy. Reactor Context hữu ích để truyền trace metadata qua callbacks đổi thread; không assume ThreadLocal/MDC tự lan khắp reactive chain.

### 22.1. Phân biệt logical stream, HTTP connection và upstream source

Một logical user session có thể mở nhiều HTTP connections do reconnect. Một connection có thể liên quan tới một response publisher, trong khi nhiều publishers có thể dùng chung broker consumer. Metrics phải thể hiện đúng tầng thay vì đếm tất cả là "active users".

### 22.2. Cleanup metric không đủ để phát hiện memory leak

Counter `opened == closed` sau load test là chỉ báo tốt nhưng không bảo đảm pooled ByteBuf đã release, buffers trong queues đã giải phóng hoặc listener references không bị giữ. Kết hợp heap/native memory profiling, Netty leak detection, resource metrics, test cancellation và review code ownership.

## 23. Những lỗi phổ biến và cách sửa

| Triệu chứng | Nguyên nhân | Cách khắc phục |
| --- | --- | --- |
| Đóng tab nhưng broker listener vẫn tồn tại | Mở ngoài subscription và không unregister | `using`/`usingWhen` đúng per-subscriber owner |
| `doOnComplete` không chạy với SSE vô hạn | Stream chưa complete hoặc bị cancel | `doFinally`/resource operator |
| `doOnError` không chạy khi client disconnect | Write error nằm downstream, upstream nhận cancel | Theo dõi Netty/HTTP error và cleanup cancellation |
| Counter CANCEL tăng khi dùng `take(1)` | `take` cancel upstream sau đủ items | Đừng gọi đó là tab close |
| Stream mới mở khi reconnect, stream cũ chưa close | Network/proxy phát hiện trễ | Bounded idle timeout/heartbeat, TTL/leases |
| Một client disconnect làm mọi clients mất dữ liệu | Per-client cleanup đóng shared resource | Phân tách ownership/ref counting |
| Timeout rồi query JDBC vẫn chạy | Blocking driver không ngừng theo cancel | Driver timeout, bounded worker, explicit cancel if supported |
| `.block()` trong cleanup làm Netty lag | Blocking close trên event loop | `usingWhen`/non-blocking close hoặc scheduler phù hợp |
| Cleanup tạo publisher rồi bỏ qua | Gọi `closeAsync()` nhưng không compose | `usingWhen` hoặc return publisher quản lý đúng |
| `subscribe()` trong controller chạy mãi | Orphan subscription không thuộc response | Return publisher thay vì tự subscribe |
| Buffered upload sau cancel còn file rác | Không cleanup partial files | Staging + delete on error/cancel |
| Native memory tiếp tục tăng | DataBuffer retain/release không cân bằng | Ownership review, doOnDiscard, leak detector |
| 500 JSON không trả được giữa SSE | Response đã commit 200 | In-band error/reconnect/close policy |
| Unit test cleanup flaky | Assert quá sớm sau doFinally | Latch/await bounded, đừng Thread.sleep tùy ý |
| Client không phát hiện stream chết | Proxy giữ idle connection | SSE heartbeat và timeout phù hợp |
| Khi rolling restart stream bị cắt | Grace period/long-lived connections | Reconnect+replay, graceful shutdown policy |
| Duplicate event sau reconnect | Không dùng event ID/idempotency | Last-Event-ID/history và idempotent consumer |
| Event bị mất khi client đóng | onNext không là ACK | Durable event log/offset/ack protocol |
| Cache Flux vô hạn gây memory leak | `cache()` không bound | Bounded replay/refCount/retention |
| Spring MVC `SseEmitter` được dùng trong Netty WebFlux | Nhầm hai web stacks | `Flux<ServerSentEvent<T>>` của WebFlux |

### Quy trình debug

1. Xác minh `spring-boot-starter-webflux`, reactive runtime và đúng package imports.
2. Vẽ đường data: controller → publishers/operators → HTTP writer → Netty/socket.
3. Xác định resource được **mở ở lúc nào** và **ai là owner**.
4. Tìm `subscribe()` thủ công, `block()`, `Thread.sleep` hoặc resource eager construction.
5. Kiểm `doFinally` và `using/usingWhen` gắn vào đúng upstream boundary.
6. Xác định source là cold/per-client hay hot/shared, tránh close nhầm shared source.
7. Với disconnect thật, xem Netty logs/HTTP connection metrics/proxy idle timeout.
8. Kiểm buffer ownership, release/discard/cancel và partial file cleanup.
9. Test complete/error/cancel bằng StepVerifier; test HTTP SSE bằng WebTestClient.
10. Đặt bound cho test async cleanup; không ép assertions real disconnect ở mốc thời gian tùy tiện.
11. Load-test nhiều clients, reconnect storm và slow consumers.
12. Kiểm app shutdown/pod kill để thấy trường hợp callback cleanup không chạy và cần TTL.

## 24. Checklist production

- [ ] Mỗi per-client stream subscription có resource owner/lifetime rõ.
- [ ] Resource mở lazy khi subscribe, không mở eager rồi bỏ mặc.
- [ ] Dọn được complete/error/cancel qua `using/usingWhen`.
- [ ] Cleanup đồng bộ ngắn; close async không bị `subscribe()` rời rạc trong finally.
- [ ] Close idempotent để đối phó race/double-notification.
- [ ] Không gọi `block()` hoặc blocking JDBC trong Netty event loop.
- [ ] Driver/client timeout và cancellation semantics được hiểu đúng.
- [ ] Client disconnect được xem là best-effort signal, không hứa phát hiện tức thì.
- [ ] Có SSE heartbeat, reconnect policy và event IDs/replay khi cần.
- [ ] Side effects có idempotency; cancel không ngầm rollback committed transaction.
- [ ] Shared hot sources có owner/refCount riêng, không bị một client close toàn bộ.
- [ ] Raw DataBuffers release theo ownership; xử lý discard/cancel/partial file.
- [ ] Timeout/slow consumer/overload/backpressure có giới hạn.
- [ ] Status/headers sau commit không bị sửa như response chưa gửi.
- [ ] Test StepVerifier đủ complete/error/cancel, có timeout bounded.
- [ ] Test HTTP SSE và cancellation qua WebTestClient/client thực ở staging.
- [ ] Metrics tách ON_COMPLETE/ON_ERROR/CANCEL/HTTP disconnect và cleanup result.
- [ ] Graceful shutdown không thay durable replay/lease expiry.
- [ ] Logs/tracing không chứa tokens, cookies và raw personal SSE events.

### Câu hỏi tự kiểm tra

**1.** `cancel()` khác `onComplete()` như thế nào?

**Trả lời:** cancel là downstream yêu cầu ngừng một subscription; onComplete là tín hiệu nguồn phát kết thúc thành công. Cancel không phải một onComplete truyền đến subscriber.

**2.** `doOnError` có bắt mọi client disconnect không?

**Trả lời:** Không. Lỗi ghi socket có thể nằm downstream, upstream chỉ nhận cancel, hoặc disconnect chưa được phát hiện ngay.

**3.** Muốn cleanup cả complete, error, cancel nên dùng gì?

**Trả lời:** `doFinally` khi cần callback/metric; `Flux.using` cho tài nguyên đóng đồng bộ; `Flux.usingWhen` nếu cleanup là publisher async.

**4.** Vì sao `take(2)` có thể khiến upstream `doFinally(CANCEL)` chạy?

**Trả lời:** Sau khi nhận đủ hai items, take có thể cancel upstream dù downstream subscriber nhận complete bình thường.

**5.** Client ngắt kết nối có chắc rollback DB update vừa commit không?

**Trả lời:** Không. Transport cancel không phải business transaction rollback; cần transaction boundaries/idempotency/compensation cụ thể.

**6.** Nếu một shared sink có 50 SSE clients, client đầu tiên cancel có nên close sink không?

**Trả lời:** Không, trừ khi shared owner/refCount policy quyết định resource không còn ai sử dụng. Per-client cleanup chỉ dọn subscription riêng.

**7.** Vì sao `Flux.usingWhen` phù hợp hơn `doFinally(() -> closeAsync().subscribe())`?

**Trả lời:** usingWhen gắn publisher cleanup vào lifecycle của resource, xử lý complete/error/cancel một cách có cấu trúc; subscribe trong callback tách khỏi flow và khó theo dõi lỗi.

**8.** Raw `DataBuffer` bị release trong `doOnNext` rồi truyền vào `writeWith` có an toàn không?

**Trả lời:** Không. Writer có thể đọc buffer đã release; phải giữ ownership rõ, chỉ release đúng nơi kết thúc sử dụng.

**9.** SSE `id` có bảo đảm exactly-once delivery không?

**Trả lời:** Không. Cần replay store, offsets/ack và idempotent consumer tùy yêu cầu reliability.

**10.** StepVerifier cancel thành công có chứng minh Netty báo client close ngay lập tức không?

**Trả lời:** Không. Nó chỉ test Reactor cancellation semantics; transport/proxy disconnect detection phải test riêng bằng HTTP client và staging network.

## 25. Tài liệu tham khảo chính thức

- [Spring Framework — WebFlux Annotated Return Values](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller/ann-methods/return-types.html): `Flux<ServerSentEvent>` và HTTP streaming.
- [Spring Framework — WebFlux Functional Endpoints](https://docs.spring.io/spring-framework/reference/6.2/web/webflux-functional.html): functional handlers/router và reactive response streaming.
- [Spring Framework — WebFlux Overview](https://docs.spring.io/spring-framework/reference/web/webflux.html): Reactive Streams server infrastructure và non-blocking I/O.
- [Spring Framework — Data Buffers and Codecs](https://docs.spring.io/spring-framework/reference/core/databuffer-codec.html): pooled buffers, ownership/release, codecs.
- [Spring Framework — DataBufferUtils Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/core/io/buffer/DataBufferUtils.html): `retain`, `release`, `join`, `write` utilities.
- [Project Reactor 3.6 — Handling Errors / Using Resources and Finally](https://projectreactor.io/docs/core/3.6.11/reference/index.html#_using_resources_and_the_finally_block): `using`/`doFinally`.
- [Project Reactor — Reactor Core API: Flux](https://projectreactor.io/docs/core/3.6.11/api/reactor/core/publisher/Flux.html): `using`, `usingWhen`, `doOnCancel`, `doFinally`.
- [Project Reactor — Testing with StepVerifier](https://projectreactor.io/docs/core/3.6.11/reference/index.html#testing): `thenCancel` và timeout.
- [Project Reactor — Hot Versus Cold](https://projectreactor.io/docs/core/3.6.11/reference/index.html#reactor.hotCold): `share`, `refCount`, per-subscription behavior.
- [Spring Framework — WebTestClient](https://docs.spring.io/spring-framework/reference/testing/webtestclient.html): reactive HTTP tests.
- [Spring Framework — ServerSentEvent Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/http/codec/ServerSentEvent.html): `event`, `data`, `id`, `retry`.
- [Reactive Streams Specification](https://www.reactive-streams.org/): `Subscription.request(n)` và `Subscription.cancel()`.
- [MDN — Using Server-Sent Events](https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events/Using_server-sent_events): `EventSource`, event stream format, reconnect và browser lifecycle.

**Ghi nhớ:** Khi HTTP streaming client dừng quan tâm, downstream **có thể** hủy reactive subscription và yêu cầu upstream ngừng phát. Nhưng `cancel` không đồng nhất với disconnect ngay lập tức, không phải transaction rollback và không tự bảo đảm close mọi tài nguyên. Hãy mở resource theo subscription, dùng `using`/`usingWhen` để cleanup đủ complete/error/cancel, hiểu Buffer ownership, quản lý heartbeat/reconnect và kiểm transport bằng tests riêng. Với shared sources, tách lifetime per-client khỏi lifetime application.
