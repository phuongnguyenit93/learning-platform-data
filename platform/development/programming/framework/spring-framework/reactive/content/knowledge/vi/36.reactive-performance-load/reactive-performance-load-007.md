# Giới hạn hàng đợi, timeout và cơ chế từ chối khi quá tải trong Spring WebFlux

## 1. Mục tiêu: bảo vệ hệ thống khi tải vượt năng lực

Một ứng dụng reactive có thể xử lý nhiều request đồng thời mà không cần một thread riêng cho mỗi request. Tuy nhiên, **non-blocking không đồng nghĩa với năng lực vô hạn**. CPU, heap, direct memory, file descriptors, connection pool, database, event loop và downstream API đều có giới hạn.

Khi tốc độ request đến lớn hơn tốc độ hệ thống xử lý, công việc chờ sẽ tích lũy. Nếu mọi queue đều không giới hạn, hệ thống có thể gặp heap/direct memory tăng liên tục, request chờ lâu hơn deadline, timeout hàng loạt, connection pool bị chiếm hết, retry storm, event loop nghẽn và noisy-neighbor giữa các tenant.

Bảo vệ quá tải cần phối hợp ba cơ chế:

1. **Bounded queue:** giữ lượng công việc chờ hữu hạn để hấp thụ burst ngắn.
2. **Timeout/deadline:** ngừng chờ hoặc xử lý khi công việc không còn giá trị trong ngân sách thời gian.
3. **Load shedding/admission control:** từ chối công việc mới khi không còn năng lực an toàn.

Một hệ thống tốt không cố nhận mọi request. Nó nhận phần có khả năng hoàn tất trong SLA và từ chối phần vượt năng lực càng sớm càng tốt.

## 2. Bản đồ các hàng đợi trong một request WebFlux

~~~text
Client
  |
  v
Load balancer / ingress queue
  |
  v
OS listen / accept backlog
  |
  v
Reactor Netty connection + HTTP processing
  |
  v
WebFlux handler / application admission gate
  |
  +--> Reactor operator queues (flatMap / publishOn / buffer)
  |
  +--> Scheduler task queue
  |
  +--> WebClient ConnectionProvider pending-acquire queue
  |
  +--> Database connection pool / downstream service queue
  |
  v
Response
~~~

| Vị trí | Đơn vị được giữ | Ví dụ giới hạn | Hành vi khi đầy |
| --- | --- | --- | --- |
| Load balancer/ingress | Request | Max pending requests, queue timeout | Trả 429/503 hoặc từ chối tại edge |
| OS accept backlog | TCP connection chưa được accept | Socket backlog | Hành vi phụ thuộc OS; có thể từ chối/drop |
| Reactor Netty server | TCP connection | `HttpServer.maxConnections` | Đóng connection mới khi chạm trần |
| Admission gate | Request đang xử lý | Semaphore/bulkhead | Fail-fast 503/429 |
| Reactor operator | Item | Prefetch, bounded buffer | Chờ theo demand hoặc overflow |
| Scheduler | Runnable/task | Thread cap + queue capacity | Queue full/reject task |
| WebClient pool | Request chờ connection | `pendingAcquireMaxCount` | Acquire timeout/reject |
| Database pool | Request chờ connection | Max pool size + wait timeout | Pool timeout/reject |

Một queue có thể chứa TCP connection, HTTP request, Publisher item, task hoặc connection-acquire request. Chọn đúng tầng trước khi điều chỉnh.

## 3. Backpressure khác admission control

### 3.1. Backpressure điều tiết demand giữa Publisher và Subscriber

Reactive Streams truyền demand bằng `Subscription.request(n)`. Downstream yêu cầu số item nó sẵn sàng nhận; upstream chỉ phát theo demand nếu nó tuân thủ Reactive Streams.

~~~text
Downstream
    |
    | request(8)
    v
Operator / queue
    |
    | demand được truyền/điều chỉnh
    v
Upstream Publisher
    |
    v
  onNext(...)
~~~

Backpressure hữu ích khi toàn bộ pipeline nằm trong cùng reactive flow và nguồn biết cách tôn trọng demand.

### 3.2. Admission control quyết định có nhận việc mới không

Admission control kiểm tra năng lực trước khi bắt đầu công việc tốn tài nguyên: còn permit không, queue còn chỗ không, tenant có vượt quota không, downstream còn healthy không, deadline còn đủ dài không. Nếu không, request bị từ chối thay vì chờ vô hạn.

HTTP client có thể gửi request tới server độc lập với demand bên trong một Publisher. Việc một handler dùng `flatMap(concurrency)` không tự giới hạn số TCP connection, số HTTP request đang tới hoặc số request đã được framework nhận.

Backpressure cũng không tự điều tiết một callback/hot source không hỗ trợ demand. Khi nguồn đó tiếp tục phát, ứng dụng cần queue có giới hạn hoặc policy drop/reject.

Các cách subscribe tiện lợi như `subscribe()`, `block()` và `toIterable()` thường yêu cầu unbounded demand `Long.MAX_VALUE`. Tự subscribe bên trong WebFlux handler có thể phá lifecycle/backpressure mà framework đang quản lý.

**Dùng backpressure để điều tiết luồng dữ liệu; dùng admission control để bảo vệ năng lực xử lý request.**

## 4. Vì sao queue không giải quyết được quá tải kéo dài?

Gọi:

- \(\lambda\): tốc độ request đến (request/giây).
- \(\mu\): tốc độ xử lý hoàn tất (request/giây).
- \(Q\): số request đang chờ.
- \(S\): kích thước trung bình một request trong memory.

Nếu \(\lambda > \mu\) trong thời gian dài, queue sẽ tăng cho tới khi đạt giới hạn. Bounded queue xác định hệ thống giữ bao nhiêu việc chờ trước khi từ chối, chứ không làm tăng năng lực xử lý.

Định luật Little:

\[
L = \lambda \times W
\]

Trong trạng thái ổn định, \(L\) là số công việc trung bình đang ở trong hệ thống, \(\lambda\) là throughput thực tế, \(W\) là thời gian trung bình một công việc ở trong hệ thống.

Ví dụ service xử lý 100 request/giây. Nếu có trung bình 200 request đang chờ/đang xử lý, thời gian trung bình theo mô hình Little là khoảng 2 giây:

\[
W = \frac{L}{\lambda} = \frac{200}{100} = 2s
\]

Nếu SLA chỉ cho phép 500 ms, queue chứa 200 request là vô nghĩa: nhiều request đã quá deadline trước khi tới lượt.

### 4.1. Ước lượng thời gian chờ và memory

Với FIFO queue và tốc độ xử lý tương đối ổn định:

\[
T_{\text{queue}} \approx \frac{Q_{\text{ahead}}}{\mu}
\]

Nếu phía trước request có 80 việc và worker hoàn tất 40 việc/giây, thời gian chờ ước lượng là 2 giây. Nếu deadline còn 300 ms, nên từ chối thay vì đưa request vào queue.

Ước lượng memory:

\[
M_{\text{queue}} \approx Q \times S
\]

Nếu queue có 5.000 item, mỗi item giữ trung bình 24 KiB payload/object graph, riêng phần này xấp xỉ 117,2 MiB. Chưa tính queue node, wrapper, references, Netty direct buffers, decoded DTO, trace context và các queue khác.

**Queue phải có giới hạn theo cả memory budget lẫn deadline.**

## 5. Thiết kế bounded queue

Một bounded queue có capacity tối đa, quy tắc lấy item và overflow policy khi producer đưa thêm item vào lúc queue đầy.

| Policy | Khi đầy | Dùng khi |
| --- | --- | --- |
| Reject / error | Từ chối item mới | Command quan trọng, muốn fail-fast |
| Drop newest | Bỏ item mới | Telemetry có thể mất mẫu mới |
| Drop oldest | Loại item cũ nhất để nhận item mới | Giá trị mới quan trọng hơn lịch sử |
| Latest/coalesce | Chỉ giữ trạng thái mới nhất | Dashboard, trạng thái sensor |
| Durable queue | Ghi vào broker/storage có persistence | Job cần xử lý sau, cần replay |
| Priority queue | Ưu tiên nhóm công việc quan trọng | Nhiều cấp độ SLA |

Không chọn drop chỉ để tránh exception. Nếu item là payment, audit event, order command hoặc workflow cần bảo toàn, hãy dùng durable queue/outbox/broker và acknowledgement phù hợp.

### 5.1. onBackpressureBuffer(maxSize)

~~~java
Flux<Event> bounded = hotEvents.onBackpressureBuffer(
        256,
        BufferOverflowStrategy.ERROR);
~~~

Reactor API này yêu cầu unbounded demand từ upstream rồi giữ backlog tối đa 256 item nếu downstream chưa có demand. Khi vượt giới hạn, overflow strategy được áp dụng.

Điều đó có nghĩa `onBackpressureBuffer(maxSize)` là **bounded buffer với overflow policy**, không phải luôn là cách truyền demand ngược về một nguồn nóng. Nguồn vẫn có thể phát nhanh và queue sẽ đầy.

Các strategy có thể gồm ERROR, DROP_LATEST và DROP_OLDEST tùy overload/version. Chọn theo semantics nghiệp vụ và kiểm tra discarded item/resource được cleanup đúng cách.

### 5.2. Sinks với queue hữu hạn

Khi ứng dụng tự nối nhiều producer với một consumer reactive, có thể dùng unicast sink và queue hữu hạn:

~~~java
Queue<Command> queue = new ArrayBlockingQueue<>(128);

Sinks.Many<Command> commands =
        Sinks.many().unicast().onBackpressureBuffer(queue);

Sinks.EmitResult result = commands.tryEmitNext(command);

if (result == Sinks.EmitResult.FAIL_OVERFLOW) {
    // Queue đầy: reject/defer/durable persistence.
}
else if (result != Sinks.EmitResult.OK) {
    // Xử lý no subscriber/terminated/non-serialized.
}
~~~

- `ArrayBlockingQueue` giới hạn số command đang chờ.
- `tryEmitNext` không đợi queue có chỗ; nó trả kết quả ngay.
- `FAIL_OVERFLOW` là tín hiệu producer phải xử lý.
- `unicast` chỉ cho một Subscriber; mỗi worker/session cần topology phù hợp.
- Queue RAM không bền vững qua process restart.
- Nếu nhiều producer phát đồng thời, xử lý kết quả emission và concurrency theo contract của sink.

Không bỏ qua `EmitResult`. Nếu producer không kiểm tra kết quả, command có thể bị từ chối mà ứng dụng vẫn tưởng đã được nhận.

## 6. Giới hạn concurrency bằng flatMap và bulkhead

### 6.1. flatMap concurrency

~~~java
Flux<Result> results = requests.flatMap(
        request -> downstream.call(request),
        12,
        1);
~~~

12 là số inner Publisher tối đa được subscribe đồng thời; 1 là prefetch cho mỗi inner Publisher. Kết quả có thể xen kẽ theo thời điểm hoàn tất. Khi đạt concurrency, operator điều tiết việc subscribe inner mới và có thể giữ một lượng outer item theo demand/prefetch.

Đây là giới hạn concurrency bên trong pipeline, không phải rate limit theo giây và không tự tạo HTTP 429/503 cho request ở ingress.

### 6.2. concatMap

~~~java
Flux<Result> results = requests.concatMap(
        downstream::call,
        16);
~~~

`concatMap` chỉ xử lý một inner Publisher tại một thời điểm và giữ thứ tự. Tham số prefetch không có nghĩa 16 request downstream đang chạy đồng thời.

Dùng khi thứ tự command quan trọng hoặc state không cho phép xử lý song song. Nếu remote calls độc lập, concatMap có thể giới hạn throughput quá mạnh.

### 6.3. Bulkhead theo dependency

~~~text
WebFlux API
   |
   +--> Inventory bulkhead: 12 calls
   |
   +--> Billing bulkhead:    4 calls
   |
   +--> Search bulkhead:    20 calls
~~~

Bulkhead cô lập tài nguyên để một downstream chậm không chiếm hết năng lực của dependency khác. Resilience4j cung cấp `SemaphoreBulkhead` và `FixedThreadPoolBulkhead`. Reactor operator có thể phát `BulkheadFullException` khi bulkhead đầy.

Semaphore bulkhead phù hợp nhiều mô hình reactive/I/O vì không tạo thread pool thay thế. Đặt wait duration bằng 0 để fail-fast; chờ permit bằng cách block event loop là sai thiết kế.

ThreadPoolBulkhead có queue capacity. Đây là queue task riêng; cần giới hạn queue, thời gian chờ và xử lý rejection. Không dùng thread pool bulkhead như một cách vô tình biến toàn bộ reactive I/O thành blocking worker.

## 7. Rate limit khác concurrency limit

**Concurrency limit** giới hạn số công việc đang chạy tại cùng một thời điểm. **Rate limit** giới hạn số lần được phép bắt đầu trong một khoảng thời gian.

Ví dụ:
- Concurrency = 10: tối đa 10 request đang xử lý cùng lúc.
- Rate limit = 100 request/giây: tối đa 100 lần bắt đầu trong một giây theo thuật toán limiter.
- Một request có thể chạy 2 giây; với rate 100/giây, concurrency có thể vượt 10 nếu không có bulkhead.

| Cơ chế | Câu hỏi được trả lời | Phạm vi |
| --- | --- | --- |
| Semaphore/Bulkhead | Có bao nhiêu request đang chạy? | Concurrent calls |
| Token bucket/rate limiter | Trong khoảng thời gian này cho phép bao nhiêu request? | Requests/time |
| Queue capacity | Giữ tối đa bao nhiêu request chờ? | Pending work |
| Timeout | Chờ hoặc xử lý tối đa bao lâu? | Duration/deadline |

Rate limit thường được áp dụng theo API key, user, tenant, IP hoặc endpoint. Nếu chỉ rate limit toàn cục, một tenant lớn có thể chiếm hết quota của tenant khác.

Khi vượt quota của một caller, HTTP 429 thường phù hợp. Khi toàn bộ service không còn khả năng phục vụ tạm thời, 503 thường diễn tả đúng hơn.

## 8. Timeout: nhiều tầng, nhiều ý nghĩa

Không có một timeout duy nhất bảo vệ toàn bộ request. Một request WebFlux có thể trải qua client connect, DNS, TLS handshake, connection pool acquire, request upload/read, downstream response, Mono/Flux operation, server request-body read, overall request deadline và idle connection timeout.

| Timeout | Giới hạn điều gì? | API / vị trí |
| --- | --- | --- |
| Connect timeout | Thiết lập TCP connection tới remote | Reactor Netty `CONNECT_TIMEOUT_MILLIS` |
| Pool acquire timeout | Chờ mượn connection từ client pool | `pendingAcquireTimeout` |
| Response timeout | Khoảng thời gian chờ response/read theo Reactor Netty | `HttpClient.responseTimeout` |
| Mono/Flux timeout | Thời gian chờ signal của Publisher | `Mono.timeout`, `Flux.timeout` |
| Server read timeout | Khoảng cách giữa network reads của request body | `HttpServer.readTimeout` |
| Server request timeout | Tổng thời gian đọc request content | `HttpServer.requestTimeout` |
| Server idle timeout | Connection chờ HTTP request tiếp theo | `HttpServer.idleTimeout` |
| Overall deadline | Tổng thời gian xử lý được phép | Application/request deadline |

### 8.1. Pool acquire timeout khác response timeout

Giả sử client pool có 20 connection, tất cả đang bận:

- Request mới chờ connection trong pending queue.
- Nếu không có connection trước acquire timeout, request lỗi acquire.
- Nếu lấy được connection, request mới bắt đầu connect/write/read.
- Response timeout kiểm soát giai đoạn chờ response, không phải thời gian nằm trong pending queue.

~~~java
ConnectionProvider provider =
        ConnectionProvider.builder("orders-api")
                .maxConnections(20)
                .pendingAcquireMaxCount(40)
                .pendingAcquireTimeout(Duration.ofMillis(150))
                .build();

HttpClient client = HttpClient.create(provider)
        .option(ChannelOption.CONNECT_TIMEOUT_MILLIS, 500)
        .responseTimeout(Duration.ofMillis(800));
~~~

Các giá trị chỉ là ví dụ. `pendingAcquireMaxCount` hữu hạn bảo vệ queue; `pendingAcquireTimeout` giới hạn thời gian chờ. Reactor Netty hiện đặt default acquire timeout là 45 giây nếu không cấu hình, có thể quá dài so với SLA của một request API.

### 8.2. Timeout operator của Reactor

~~~java
Mono<PartnerResult> result = partnerClient.fetch()
        .timeout(Duration.ofMillis(700));
~~~

`timeout` giới hạn thời gian từ subscription tới signal theo semantics của Publisher. Với Mono chờ một kết quả, timeout phát lỗi nếu không có signal trước deadline. Với Flux, timeout mặc định áp dụng giữa các signal; nó không mặc nhiên là deadline tuyệt đối cho toàn bộ stream.

Nếu cần deadline toàn operation, xác định rõ semantics và đặt timeout ở boundary phù hợp. Không giả định `Flux.timeout(Duration)` đơn giản luôn giới hạn tổng thời gian của một stream vô hạn.

Khi timeout xảy ra, Reactor cancel upstream subscription. Nhưng cancellation không đảm bảo side effect đã gửi tới hệ thống ngoài được rollback hoặc dừng tức thì. Downstream có thể đã nhận command và tiếp tục xử lý.

Với thao tác ghi, cần idempotency key, transaction semantics hoặc trạng thái xử lý có thể tra cứu để tránh retry tạo giao dịch trùng.

### 8.3. Server readTimeout và requestTimeout không phải handler deadline

Reactor Netty server phân biệt:

- `readTimeout`: thời gian tối đa giữa các lần network-level read khi đọc request content.
- `requestTimeout`: tổng thời gian đọc request content.
- `idleTimeout`: thời gian connection mở và chờ HTTP request tiếp theo.

`requestTimeout` không phải deadline của toàn bộ controller/service. Nếu handler gọi downstream trong 3 giây, cần deadline cho reactive operation hoặc gateway/request deadline riêng.

~~~java
HttpServer server = HttpServer.create()
        .readTimeout(Duration.ofSeconds(5))
        .requestTimeout(Duration.ofSeconds(20))
        .idleTimeout(Duration.ofSeconds(60));
~~~

Các giá trị chỉ minh họa; hãy chọn theo kích thước body, client network, proxy timeout và API contract.

## 9. Deadline end-to-end

Nếu mỗi tầng tự đặt timeout độc lập mà không có ngân sách chung, timeout con có thể dài hơn deadline cha.

Ví dụ request có deadline 1.500 ms:

| Giai đoạn | Budget ví dụ |
| --- | ---: |
| Chờ admission/queue | 100 ms |
| Acquire connection | 100 ms |
| Connect/TLS | 200 ms |
| Downstream processing | 700 ms |
| Serialize/response | 150 ms |
| Safety margin | 250 ms |
| **Tổng** | **1.500 ms** |

Đây là ngân sách minh họa, không phải cấu hình mặc định.

- Admission queue chỉ giữ request nếu còn đủ thời gian để xử lý.
- Pool acquire timeout phải nhỏ hơn deadline còn lại.
- Downstream timeout phải dành thời gian cho serialize/response.
- Không retry nếu lần retry tiếp theo không còn đủ budget.
- Propagate deadline/remaining budget tới downstream nếu giao thức hỗ trợ.
- Khi deadline hết, cancel công việc có thể cancel và ghi metric timeout đúng tầng.

Nếu request đã chờ 1 giây trong queue, không nên bắt đầu downstream call có timeout 2 giây trong khi caller chỉ chờ tối đa 1,5 giây.

## 10. Chọn HTTP status khi từ chối hoặc timeout

| Status | Dùng khi | Ví dụ |
| --- | --- | --- |
| 429 Too Many Requests | Caller/tenant vượt rate quota | API key vượt 100 request/phút |
| 503 Service Unavailable | Service tạm quá tải hoặc maintenance | Admission gate hết permit, dependency không khả dụng |
| 504 Gateway Timeout | API/gateway không nhận được response kịp từ upstream | Orders API chờ Inventory API quá deadline |
| 408 Request Timeout | Server không nhận được request hoàn chỉnh trong thời gian cho phép | Client upload body quá chậm (tùy server behavior) |

`Retry-After` có thể biểu diễn số giây chờ hoặc HTTP-date. Khi trả 503 do overload tạm thời, server có thể gợi ý thời gian retry. Với 429, Retry-After cũng hữu ích khi quota có chu kỳ reset.

~~~http
HTTP/1.1 503 Service Unavailable
Content-Type: application/json
Retry-After: 2

{"code":"SERVICE_OVERLOADED"}
~~~

Không gửi một thời gian Retry-After quá lạc quan nếu hệ thống không biết khi nào sẽ hồi phục. Nếu không có estimate đáng tin, cân nhắc policy client backoff thay vì hứa một thời điểm cụ thể.

### 10.1. Lưu ý đặc biệt về maxConnections của server

`HttpServer.maxConnections(n)` giới hạn số TCP connection. Khi chạm giới hạn, Reactor Netty đóng connection mới ngay. Nó không đảm bảo request nhận được HTTP 503 vì HTTP connection chưa chắc được chấp nhận để xử lý request.

Với HTTP/2, nhiều stream có thể dùng cùng TCP connection; giới hạn connection không đồng nghĩa giới hạn số HTTP/2 stream/request.

Nếu cần trả status 429/503 có body và Retry-After, thực hiện admission/rate limit ở tầng đã nhận HTTP request hoặc tại gateway có khả năng trả response. Dùng connection cap như lớp bảo vệ transport bổ sung.

## 11. Fail-fast admission gate trong WebFlux

Một cách đơn giản để giới hạn số công việc đang chạy là dùng semaphore không chờ:

~~~java
@Component
class AdmissionGate {

    private final Semaphore permits = new Semaphore(20);

    <T> Mono<T> execute(Supplier<Mono<T>> work) {
        return Mono.defer(() -> {
            if (!permits.tryAcquire()) {
                return Mono.error(new OverloadedException());
            }

            return Mono.defer(work)
                    .doFinally(signal -> permits.release());
        });
    }
}
~~~

Cách hoạt động:

1. `Mono.defer` chỉ thử lấy permit khi có subscription.
2. `tryAcquire()` trả về ngay, không block event loop.
3. Nếu hết permit, trả lỗi overload ngay.
4. Nếu lấy được permit, subscribe công việc reactive.
5. `doFinally` trả permit khi complete, error hoặc cancel.

Đây là admission gate **không có queue chờ**. Nó ưu tiên fail-fast để tránh tạo thêm latency và memory pressure.

### 11.1. Map lỗi overload thành 503

~~~java
@RestControllerAdvice
class OverloadExceptionHandler {

    @ExceptionHandler(OverloadedException.class)
    ResponseEntity<Map<String, String>> overloaded() {
        return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE)
                .header(HttpHeaders.RETRY_AFTER, "1")
                .body(Map.of("code", "SERVICE_OVERLOADED"));
    }
}
~~~

Đây là ví dụ nếu service muốn trả 503 và có thể đề xuất retry sau 1 giây. Với quota riêng của một API key/tenant, dùng 429 và policy Retry-After phù hợp hơn.

Không bắt mọi `RuntimeException` rồi đổi thành 503. Chỉ map lỗi admission/bulkhead đã phân loại; lỗi input, authentication, authorization và bug phải giữ semantics riêng.

### 11.2. Vì sao doFinally là nơi release permit?

Permit phải được trả dù publisher hoàn tất thành công, phát lỗi, bị cancel do client disconnect hoặc bị timeout operator cancel.

Nếu chỉ release trong `doOnSuccess`, permit có thể bị leak khi error/cancel và hệ thống sẽ từ chối request vĩnh viễn sau một thời gian.

Trong code phức tạp, cân nhắc `usingWhen` hoặc abstraction có lifecycle rõ ràng để quản lý tài nguyên async.

## 12. Bounded queue chờ có kiểm soát

Có trường hợp cần hấp thụ burst ngắn thay vì từ chối ngay. Khi đó queue phải có capacity hữu hạn, timeout chờ, overflow policy, metric depth/age/rejection, cancellation khi caller hết deadline và cleanup khi process shutdown.

Ví dụ cấu hình Resilience4j ThreadPoolBulkhead:

~~~yaml
resilience4j:
  thread-pool-bulkhead:
    instances:
      partner:
        coreThreadPoolSize: 4
        maxThreadPoolSize: 8
        queueCapacity: 32
        keepAliveDuration: 20ms
~~~

Đây là cấu hình minh họa cho công việc được phép chạy trên worker thread pool. Queue capacity 32 là giới hạn số task chờ; task vượt giới hạn bị reject theo bulkhead behavior.

Với reactive I/O thuần, semaphore bulkhead thường phù hợp hơn vì không cần chuyển request sang thread pool riêng. Nếu phải chạy blocking SDK, dùng bounded scheduler hoặc thread pool có queue giới hạn và chuyển việc sang worker phù hợp.

### 12.1. Đặt queue timeout

Một request có thể được chấp nhận vào queue nhưng bị hủy trước khi bắt đầu nếu deadline hết. Đừng để request đã quá hạn vẫn chạy chỉ để hoàn thành công việc caller không còn chờ.

- Lưu thời điểm nhận request/deadline.
- Khi lấy item khỏi queue, tính remaining budget.
- Nếu remaining budget không đủ, bỏ/reject item trước khi gọi downstream.
- Nếu caller đã cancel, loại bỏ item khỏi queue nếu queue hỗ trợ remove/cancel.
- Không giữ payload lớn trong queue nếu chỉ cần request ID và metadata để fetch sau.

### 12.2. Queue FIFO hay priority?

FIFO dễ hiểu và công bằng theo thứ tự đến, nhưng một tác vụ rất chậm có thể làm các tác vụ nhỏ phía sau chờ lâu.

Priority queue có thể ưu tiên request quan trọng, nhưng cần tránh starvation cho nhóm ưu tiên thấp. Có thể dùng queue riêng theo tenant/service tier, weighted fair scheduling hoặc quota độc lập.

Không để một tenant chiếm toàn bộ queue toàn cục. Giới hạn per-tenant và global cap giúp tránh noisy-neighbor.

## 13. Timeout và cancellation phải đi cùng nhau

Khi một request timeout, WebFlux có thể cancel subscription của handler, Reactor operators truyền cancellation upstream, WebClient có thể hủy request theo connector semantics và connection pool/transport giải phóng hoặc xử lý connection theo trạng thái. Tuy nhiên, side effect đã tới database/remote service có thể vẫn đang chạy.

Vì vậy:

1. Dùng reactive client và publisher có cancellation semantics rõ.
2. Không tự subscribe để tách công việc khỏi request lifecycle nếu không có job system riêng.
3. Với job cần tiếp tục sau khi client disconnect, enqueue vào durable worker thay vì giữ request HTTP.
4. Với command ghi dữ liệu, dùng idempotency key và transaction.
5. Với retry, bảo đảm lần trước không còn khả năng commit trùng hoặc operation idempotent.

**Timeout là giới hạn thời gian chờ của caller; nó không phải rollback phân tán.**

## 14. Retry trong lúc overload có thể làm sự cố nặng hơn

Giả sử service chỉ xử lý được 100 request/giây nhưng đang nhận 150 request/giây. Nếu mọi client timeout rồi retry ngay, lượng request mới còn tăng hơn nữa.

Retry cần số lần thử tối đa, exponential backoff, jitter, chỉ retry lỗi transient và operation an toàn/idempotent, respect `Retry-After`, không retry 400/401/403 hoặc business validation errors, không retry liên tục khi bulkhead/rate limiter báo full, và tổng retry budget phải nằm trong deadline ban đầu.

~~~java
Retry retry = Retry.backoff(2, Duration.ofMillis(100))
        .maxBackoff(Duration.ofSeconds(1))
        .jitter(0.5)
        .filter(this::isTransientFailure);

Mono<Result> result = remoteCall()
        .retryWhen(retry);
~~~

Đây là snippet minh họa, cần định nghĩa `isTransientFailure` và phân loại exception. 2 là số retry sau lần gọi đầu, không phải tổng số lần gọi. Không retry lỗi overload đã được server trả có chủ đích nếu retry ngay sẽ làm queue dài thêm.

## 15. Circuit breaker, bulkhead và rate limiter phối hợp

| Pattern | Bảo vệ điều gì? | Khi kích hoạt |
| --- | --- | --- |
| Rate limiter | Tốc độ request mới | Quota/requests per time vượt ngưỡng |
| Bulkhead | Số công việc đồng thời | Đã dùng hết permits/threads |
| Bounded queue | Burst ngắn | Consumer tạm chậm |
| Timeout | Thời gian chờ/xử lý | Hết deadline |
| Circuit breaker | Dependency đang thất bại | Tỷ lệ lỗi/slow call vượt threshold |
| Retry | Lỗi transient | Thử lại có giới hạn/backoff |

Một cấu hình hợp lý thường theo thứ tự:

1. Rate limit/admission gate từ chối caller vượt ngưỡng.
2. Bulkhead giới hạn concurrent work theo dependency.
3. Queue hữu hạn chỉ hấp thụ burst ngắn nếu có lý do.
4. Timeout giữ request trong deadline.
5. Circuit breaker ngăn gọi dependency đang unhealthy.
6. Retry chỉ cho lỗi transient và nằm trong ngân sách deadline.

Không stack tất cả pattern một cách máy móc. Queue dài + retry nhiều + timeout dài có thể giữ request quá lâu và tạo thêm tải khi hệ thống yếu.

## 16. Cấu hình Reactor Netty server trong Spring Boot

Spring Boot WebFlux thường dùng Reactor Netty, nhưng có thể thay bằng server reactive khác. Với Reactor Netty, customizer cho phép cấu hình các giới hạn ở tầng HTTP server:

~~~java
@Configuration
class NettyServerConfiguration {

    @Bean
    WebServerFactoryCustomizer<NettyReactiveWebServerFactory>
    nettyCustomizer() {

        return factory -> factory.addServerCustomizers(server ->
                server
                        .maxConnections(500)
                        .readTimeout(Duration.ofSeconds(5))
                        .requestTimeout(Duration.ofSeconds(20))
                        .idleTimeout(Duration.ofSeconds(60)));
    }
}
~~~

Các con số chỉ là ví dụ:

- `maxConnections(500)`: giới hạn TCP connection.
- `readTimeout(5s)`: giới hạn khoảng im lặng giữa các lần đọc request body.
- `requestTimeout(20s)`: tổng thời gian đọc request content.
- `idleTimeout(60s)`: đóng connection chờ request tiếp theo quá lâu.

Các tham số này không thay thế application admission gate, queue timeout hoặc overall handler deadline.

Nếu ứng dụng dùng Tomcat/Jetty reactive server thay vì Reactor Netty, phải dùng cấu hình server tương ứng. Đừng copy Netty customizer sang một server khác.

## 17. Observability: phải đo cả queue và rejection

Một queue có thể đang tăng dù CPU chưa cao. Nếu chỉ xem CPU, đội vận hành có thể tăng concurrency rồi vô tình đẩy overload sang database hoặc downstream.

Các metric cần có:

| Metric | Ý nghĩa | Dấu hiệu cảnh báo |
| --- | --- | --- |
| `in_flight_requests` | Request đang xử lý | Chạm giới hạn liên tục |
| `queue_depth` | Số item đang chờ | Tăng liên tục |
| `queue_oldest_age` | Tuổi item chờ lâu nhất | Vượt deadline/SLA |
| `queue_wait_seconds` | Thời gian chờ queue | p95/p99 tăng |
| `rejected_total` | Số request bị từ chối | Tăng đột biến |
| `timeout_total{layer}` | Timeout theo tầng | Pool/server/downstream timeout tăng |
| `bulkhead_available` | Permit còn trống | Thường xuyên bằng 0 |
| `active_connections` | TCP connections đang dùng | Luôn sát max |
| `pending_acquires` | Request chờ client connection | Queue pool tăng |
| `scheduler_pending_tasks` | Task đang chờ worker | Scheduler bị nghẽn |
| `downstream_latency` | Độ trễ dependency | Tăng trước khi overload lan rộng |
| `event_loop_pending_tasks` | Task chờ event loop | Event loop không theo kịp |

Theo dõi p50/p95/p99, không chỉ average. Queue depth cần kết hợp oldest age; một queue có 20 item nhưng item đầu đã chờ 15 giây có thể nguy hiểm hơn queue 100 item được xử lý trong 20 ms.

Không dùng user ID, raw URL hoặc request ID làm metric label có cardinality không giới hạn. Dùng route template, service name, tenant tier và error category.

## 18. Load shedding theo mức ưu tiên

Khi tải vượt năng lực, có thể phân nhóm request:

- **Critical:** thanh toán, xác nhận đơn, security-sensitive operations.
- **Standard:** đọc/ghi nghiệp vụ thông thường.
- **Best effort:** gợi ý, analytics, telemetry, preview.
- **Background:** báo cáo, batch, export.

Một chiến lược load shedding có thể giữ capacity dự phòng cho critical path, hạn chế best-effort trước, từ chối tenant đã vượt quota, dừng enqueue job không còn deadline, bảo vệ downstream bằng bulkhead riêng và trả status/Retry-After phù hợp.

Không để request nặng như export/report dùng chung một queue và concurrency với request nhẹ như health/profile mà không có giới hạn. Có thể dùng route-specific semaphore, worker pool riêng hoặc asynchronous job API.

## 19. Chương trình Java 17+ chạy được: fail-fast admission

Ví dụ độc lập dùng Reactor Core để chứng minh admission gate giới hạn hai công việc đồng thời. Năm request được subscribe cùng lúc; hai request nhận permit, ba request còn lại bị từ chối ngay. Chương trình không dùng `Thread.sleep()` hoặc block trong pipeline.

### 19.1. Cấu trúc dự án

~~~text
webflux-overload-demo/
  pom.xml
  src/main/java/example/overload/AdmissionDemo.java
~~~

Yêu cầu JDK 17+, Maven 3.6.3+ và Maven Central để tải dependency lần đầu.

### 19.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>example</groupId>
    <artifactId>webflux-overload-demo</artifactId>
    <version>1.0.0</version>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>4.1.2</version>
        <relativePath/>
    </parent>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.3.0</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 19.3. AdmissionDemo.java

~~~java
package example.overload;

import java.time.Duration;
import java.util.List;
import java.util.concurrent.Semaphore;
import java.util.concurrent.atomic.AtomicInteger;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public final class AdmissionDemo {

    private static final Semaphore PERMITS = new Semaphore(2);

    private static final AtomicInteger ACTIVE = new AtomicInteger();
    private static final AtomicInteger MAX_ACTIVE = new AtomicInteger();
    private static final AtomicInteger ACCEPTED = new AtomicInteger();
    private static final AtomicInteger REJECTED = new AtomicInteger();

    static final class OverloadedException
            extends RuntimeException {
    }

    private static Mono<String> handle(int id) {
        return Mono.defer(() -> {
            if (!PERMITS.tryAcquire()) {
                REJECTED.incrementAndGet();
                return Mono.error(new OverloadedException());
            }

            ACCEPTED.incrementAndGet();

            int current = ACTIVE.incrementAndGet();
            MAX_ACTIVE.accumulateAndGet(current, Math::max);

            return Mono.delay(Duration.ofMillis(200))
                    .map(ignored -> "ok-" + id)
                    .doFinally(signal -> {
                        ACTIVE.decrementAndGet();
                        PERMITS.release();
                    });
        });
    }

    public static void main(String[] args) {
        List<String> results = Flux.range(1, 5)
                .flatMap(
                        id -> handle(id)
                                .onErrorResume(
                                        OverloadedException.class,
                                        error -> Mono.just(
                                                "rejected-" + id)),
                        5,
                        1)
                .sort()
                .collectList()
                .block(Duration.ofSeconds(5));

        List<String> expected = List.of(
                "ok-1",
                "ok-2",
                "rejected-3",
                "rejected-4",
                "rejected-5");

        if (!expected.equals(results)) {
            throw new AssertionError(
                    "Unexpected results: " + results);
        }

        if (ACCEPTED.get() != 2
                || REJECTED.get() != 3
                || MAX_ACTIVE.get() != 2
                || ACTIVE.get() != 0) {
            throw new AssertionError(
                    "Admission counters are inconsistent");
        }

        System.out.println("results=" + results);
        System.out.println("accepted=" + ACCEPTED.get());
        System.out.println("rejected=" + REJECTED.get());
        System.out.println("max-in-flight=" + MAX_ACTIVE.get());
    }
}
~~~

### 19.4. Chạy chương trình

Từ thư mục chứa `pom.xml`:

~~~bash
mvn -q clean compile exec:java -Dexec.mainClass=example.overload.AdmissionDemo
~~~

**Stdout dự kiến:**

~~~text
results=[ok-1, ok-2, rejected-3, rejected-4, rejected-5]
accepted=2
rejected=3
max-in-flight=2
~~~

Giải thích:

- `Semaphore(2)` chỉ cho phép hai công việc đang chạy.
- `tryAcquire()` không chờ và không block event loop.
- `Mono.defer` chỉ thử permit khi subscription bắt đầu.
- Ba request còn lại nhận `OverloadedException` và được demo chuyển thành kết quả `rejected`.
- `doFinally` trả permit ở cả complete, error và cancel.
- `flatMap(..., 5, 1)` cho phép năm inner Publisher được subscribe; admission gate mới là nơi giới hạn hai công việc thực sự được nhận.
- `block(Duration)` chỉ nằm ở main boundary để demo chờ kết quả; không dùng block trong WebFlux handler.

Đây là ví dụ admission control trong reactive pipeline, không phải một HTTP server hoàn chỉnh. Ở WebFlux controller, map `OverloadedException` thành 503/429 bằng exception handler thay vì trả chuỗi rejected.

## 20. Kiểm thử overload và timeout

Test cần chứng minh các hành vi sau:

| Test | Kỳ vọng |
| --- | --- |
| Dưới giới hạn concurrency | Request hoàn tất 2xx |
| Đúng capacity | Tất cả permit được sử dụng nhưng không vượt max |
| Vượt capacity | Request thừa nhận 503/429 theo policy |
| Queue đầy | Producer nhận overflow/rejection rõ ràng |
| Chờ queue quá lâu | Request bị timeout trước khi bắt đầu |
| Downstream timeout | Cancel upstream và trả lỗi đã phân loại |
| Client disconnect | Permit/queue item được cleanup |
| Downstream phục hồi | Queue depth và active count trở về baseline |
| Retry storm | Không tạo thêm tải vô hạn |
| Tenant noisy neighbor | Tenant khác vẫn có capacity riêng |

Dùng `StepVerifier.withVirtualTime` để test timeout/retry mà không chờ thời gian thực khi phù hợp. Dùng `WebTestClient` hoặc test load qua HTTP thật để kiểm tra status code, header Retry-After, client disconnect và behavior của embedded server.

Đối với Reactor Netty connection cap, cần integration/load test qua TCP thật; unit test một controller không chứng minh được kernel accept backlog hoặc connection rejection behavior.

## 21. Lỗi thiết kế thường gặp

| Sai lầm | Hậu quả | Hướng sửa |
| --- | --- | --- |
| Dùng queue vô hạn | Heap tăng tới OOM | Bounded queue + overflow policy |
| Chỉ tăng queue khi overload | Request chờ lâu hơn, không tăng service capacity | Giảm admission hoặc scale capacity |
| Chỉ dùng flatMap concurrency để bảo vệ ingress | HTTP requests vẫn có thể vào server | Admission gate/edge limit |
| Chặn event loop khi chờ semaphore | Các request khác bị treo | `tryAcquire()` hoặc async queue |
| Dùng onBackpressureBuffer mặc định cho hot source | Buffer vô hạn | maxSize và overflow strategy |
| Dùng buffer bounded nhưng không theo dõi overflow | Mất item âm thầm hoặc lỗi không được xử lý | Callback/metric/error policy |
| Queue không có timeout | Item cũ vẫn được chạy sau deadline | Queue wait deadline |
| Timeout mỗi tầng quá dài | Tổng request vượt SLA | End-to-end deadline |
| Coi server requestTimeout là handler timeout | Handler/downstream vẫn chạy quá lâu | Mono timeout/deadline riêng |
| Coi maxConnections là max HTTP/2 requests | Multiplexed streams vượt kỳ vọng | Giới hạn stream/admission ở tầng phù hợp |
| Retry ngay khi nhận 503 | Retry storm | Backoff, jitter, Retry-After, max attempts |
| Retry thao tác ghi không idempotent | Ghi trùng | Idempotency key/transaction |
| Bulkhead toàn cục cho mọi dependency | Dependency chậm chiếm toàn bộ permit | Bulkhead riêng theo dependency |
| Semaphore không release khi cancel | Permit leak, service từ chối vĩnh viễn | doFinally/usingWhen |
| Queue RAM cho job cần bảo toàn | Mất job khi process restart | Durable broker/outbox |
| Chỉ xem CPU | Bỏ qua queue wait và connection starvation | Metrics queue/latency/pending |
| Trả 200 với body “busy” | Client khó nhận diện lỗi và retry policy sai | 429/503 với error contract |
| Log payload khi overload | Tăng I/O và lộ dữ liệu | Structured metadata, sampling |

## 22. Checklist production

- [ ] Liệt kê tất cả queue từ load balancer tới database/downstream.
- [ ] Xác định queue nào giữ TCP connection, request, task, Publisher item hay connection acquire.
- [ ] Mọi queue có thể tăng theo tải đều có capacity hữu hạn hoặc durable storage.
- [ ] Chọn overflow policy theo semantics nghiệp vụ.
- [ ] Có admission control trước các công việc tốn tài nguyên.
- [ ] Giới hạn concurrency theo dependency.
- [ ] Rate limit theo user/tenant/API key khi cần.
- [ ] Không block Netty event loop để chờ permit/queue.
- [ ] Đặt queue wait timeout và loại bỏ item đã quá deadline.
- [ ] Có overall deadline và budget cho từng tầng.
- [ ] Phân biệt pool acquire, connect, TLS, response, server read và handler timeout.
- [ ] Biết cancellation có được truyền tới downstream hay không.
- [ ] Dùng idempotency cho side effects có retry.
- [ ] Trả 429 cho quota caller; 503 cho service overload; 504 cho upstream gateway timeout.
- [ ] Dùng Retry-After/backoff/jitter có kiểm soát.
- [ ] Không retry overload một cách tức thì.
- [ ] Theo dõi queue depth, oldest age, wait time, rejected count và in-flight.
- [ ] Theo dõi pending connections, event-loop tasks, heap/direct memory và downstream latency.
- [ ] Có load test steady-state, burst, slow consumer, downstream outage và recovery.
- [ ] Có runbook cho overload và scale-out/scale-in.

## 23. Câu hỏi tự kiểm tra

**Câu 1.** Bounded queue giải quyết vấn đề gì?

Giới hạn số công việc chờ và hấp thụ burst ngắn; nó không tăng throughput của consumer.

**Câu 2.** Nếu tốc độ đến lớn hơn tốc độ xử lý trong thời gian dài thì sao?

Queue tăng tới capacity; sau đó phải reject/drop hoặc ghi vào durable storage theo policy.

**Câu 3.** Backpressure khác admission control thế nào?

Backpressure điều tiết demand giữa Publisher/Subscriber; admission control quyết định có nhận request/công việc mới hay không.

**Câu 4.** `flatMap(concurrency)` có thay thế HTTP ingress rate limit không?

Không. Nó giới hạn inner subscriptions trong pipeline, không trực tiếp giới hạn request được nhận ở ingress.

**Câu 5.** Vì sao không nên dùng queue vô hạn?

Nó có thể giữ payload/object không giới hạn, tăng memory và latency tới OOM.

**Câu 6.** `onBackpressureBuffer(maxSize)` có luôn truyền demand ngược upstream không?

Không. API này yêu cầu unbounded demand từ upstream và giữ backlog hữu hạn; khi đầy áp dụng overflow strategy.

**Câu 7.** Semaphore `tryAcquire()` có ưu điểm gì trong WebFlux?

Nó kiểm tra permit ngay, không block event loop; nếu hết permit có thể reject fail-fast.

**Câu 8.** Vì sao release permit phải xử lý cancel?

Client disconnect hoặc timeout có thể cancel Publisher; nếu không release, permit bị leak.

**Câu 9.** Pool acquire timeout khác response timeout thế nào?

Acquire timeout giới hạn chờ connection trong pool; response timeout áp dụng giai đoạn chờ/đọc response theo semantics của HTTP client.

**Câu 10.** Reactor Netty server requestTimeout giới hạn gì?

Tổng thời gian đọc request content, không phải toàn bộ thời gian controller xử lý.

**Câu 11.** `maxConnections` của HttpServer giới hạn HTTP/2 stream không?

Không. Nó giới hạn TCP connections; nhiều HTTP/2 stream có thể multiplex trên một connection.

**Câu 12.** Khi nào trả 429?

Khi caller/tenant/API key vượt rate quota.

**Câu 13.** Khi nào trả 503?

Khi service tạm không thể xử lý do overload hoặc maintenance.

**Câu 14.** Khi nào trả 504?

Khi gateway/proxy không nhận được response kịp từ upstream cần thiết.

**Câu 15.** Vì sao retry có thể làm overload nặng hơn?

Retry làm tăng request rate đúng lúc service đang thiếu capacity; cần backoff, jitter, giới hạn attempts và idempotency.

**Câu 16.** Vì sao queue phải có deadline?

Request chờ quá lâu có thể hết giá trị trước khi được xử lý; bắt đầu công việc sau deadline chỉ tiêu tốn tài nguyên.

## 24. Tài liệu tham khảo chính thức

- [Project Reactor — Backpressure](https://projectreactor.io/docs/core/release/reference/subscribe-backpressure.html): Reactive Streams demand, unbounded request, backpressure và reshaping requests.
- [Project Reactor — Flux JavaDoc](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Flux.html): onBackpressureBuffer, bounded buffer, overflow strategies, drop/latest và discard behavior.
- [Project Reactor — Sinks Reference](https://projectreactor.io/docs/core/release/reference/coreFeatures/sinks.html): unicast sink, custom bounded queue, emission result và backpressure.
- [Reactor Netty — HTTP Server](https://projectreactor.io/docs/netty/release/reference/http-server.html): maxConnections, server readTimeout, requestTimeout, idleTimeout và server metrics.
- [Reactor Netty — HTTP Client](https://projectreactor.io/docs/netty/release/reference/http-client.html): connection pool pending queue, pendingAcquireMaxCount, pendingAcquireTimeout, response/connect timeout và pool metrics.
- [Spring Boot — Reactive Web Applications](https://docs.spring.io/spring-boot/reference/web/reactive.html): reactive server configuration và NettyReactiveWebServerFactory customizer.
- [Spring Boot — Embedded Web Servers](https://docs.spring.io/spring-boot/how-to/webserver.html): WebServerFactoryCustomizer và server-specific settings.
- [Resilience4j — Bulkhead](https://resilience4j.readme.io/docs/bulkhead): semaphore bulkhead, fixed thread pool bulkhead và bounded queue.
- [Resilience4j — RateLimiter](https://resilience4j.readme.io/docs/ratelimiter): request quota theo chu kỳ và cách xử lý vượt giới hạn.
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110.html): 503, 504 và Retry-After.
- [RFC 6585 — Additional HTTP Status Codes](https://www.rfc-editor.org/rfc/rfc6585.html): 429 Too Many Requests.

**Ghi nhớ:** Queue hữu hạn chỉ hấp thụ burst; admission control giới hạn công việc được nhận; timeout giữ mọi request trong deadline; overload phải được từ chối rõ ràng. Hãy đo queue depth/age, concurrency, pending connection và p95/p99 để biết nghẽn ở đâu. Dùng 429 cho quota của caller, 503 cho service tạm quá tải, 504 cho gateway chờ upstream; kết hợp Retry-After, backoff và idempotency để tránh retry storm.