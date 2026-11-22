# Cô lập tác vụ chặn với scheduler phù hợp và giới hạn đồng thời trong Streaming WebFlux

## 1. Bài toán: một lời gọi chặn có thể làm nghẽn nhiều HTTP streams

Spring WebFlux sử dụng mô hình xử lý HTTP không chặn trên một số lượng tương đối nhỏ các **event-loop threads**. Reactor Netty tiếp nhận request, giải mã và ghi response trong các luồng xử lý I/O. Vì vậy, nếu một handler chạy JDBC đồng bộ, `Thread.sleep`, `InputStream.read` trên nguồn chậm hoặc một SDK chỉ có blocking API ngay trên event loop, toàn bộ những request khác cùng chia sẻ thread đó có thể bị trì hoãn.

```text
             HTTP requests / SSE / NDJSON
                       |
                       v
           Reactor Netty event loops
             |       |       |
             |  +----+-------+-----+
             |  |  Blocking SDK   |   <- SAI: giữ event loop
             |  |  chờ 2 giây     |
             |  +-----------------+
             |
         các HTTP requests khác phải chờ

Cách tốt hơn:
 event loop -> Mono.fromCallable(...) -> boundedElastic worker
      |                                      |
      | request thread không bị giữ          | Blocking SDK/read/write
      |                                      |
      +<-------- asynchronous result --------+
                       |
             encode/write HTTP response
```

Khi chuyển blocking task khỏi event loop, bạn chỉ giải quyết **thread isolation**. Nếu 10.000 người dùng đồng thời gọi một dịch vụ legacy mà nó chỉ chịu được 20 requests, scheduler có thể có hàng nghìn task xếp hàng, độ trễ tăng, connection pool cạn và overload lan sang các hệ thống khác. Cần thêm **giới hạn đồng thời, hàng đợi có giới hạn, timeout, kiểm soát lỗi, cancellation và metrics**.

Bài học thuộc **Streaming WebFlux** vì áp lực càng rõ trên endpoint trả NDJSON/SSE/file stream: mỗi connection có thể tồn tại lâu, producer và consumer có tốc độ khác nhau, việc phát dữ liệu ở tốc độ không kiểm soát có thể gây thêm queue và direct-memory pressure.

**Baseline:** Java 17+, Spring Boot 3.5.x, Spring Framework 6.2.x, Project Reactor 3.7.x, Reactor Netty. Với Java 21+ có thêm tùy chọn virtual threads cho Reactor boundedElastic được trình bày ở phần sau.

## 2. Mục tiêu kiến thức và tiêu chí hoàn thành

Sau bài này, có thể:

1. Nhận diện thao tác **blocking** trong controller, service, codec, publisher và callback.
2. Hiểu `Schedulers.parallel()`, `single()`, `boundedElastic()` và `newBoundedElastic(...)` khác nhau thế nào.
3. Biết vì sao công thức được Reactor khuyến nghị là **`Mono.fromCallable(blockingCall).subscribeOn(Schedulers.boundedElastic())`**.
4. Phân biệt `subscribeOn` với `publishOn` và vị trí chuyển thread.
5. Dùng scheduler **riêng, có giới hạn** để tránh một dependency legacy chiếm hết global pool.
6. Điều chỉnh `flatMap(mapper, concurrency)` hoặc `flatMapSequential` để giới hạn số task **trong một stream**.
7. Phân biệt concurrency per-stream với **global concurrency** qua toàn bộ HTTP requests/nodes.
8. Dùng non-blocking admission như `Semaphore.tryAcquire` hoặc bulkhead khi cần, không gọi `acquire` trên event loop.
9. Biết timeout/cancel không tự bảo đảm dừng ngay blocking I/O hoặc rollback side effects.
10. Viết Java 17 WebFlux.fn demo và WebTestClient/StepVerifier tests mà không chặn Netty event loop.

Không có một scheduler nào làm biến mất bản chất blocking của JDBC, file I/O hoặc HTTP client đồng bộ. Nó chỉ chọn nơi hoạt động blocking được thực thi; mục tiêu dài hạn có thể là driver/reactive client đúng nghĩa hoặc chuyển công việc sang background job.

## 3. Blocking là gì? Phân loại theo nguồn

| Công việc | Có thể block? | Cách tiếp cận |
| --- | --- | --- |
| `Thread.sleep` | Có | Không gọi trên event loop; demo dùng để mô phỏng |
| JDBC `ResultSet.next` / `Connection.execute` | Có | Driver reactive như R2DBC nếu phù hợp; nếu chưa có, tách sang boundedElastic |
| `RestTemplate` / blocking HTTP SDK | Có | Ưu tiên WebClient; khi bắt buộc dùng, tách và giới hạn |
| `Files.readAllBytes` | Có và dùng RAM lớn | Stream file phù hợp; nếu API blocking, tách executor và giới hạn bytes |
| `InputStream.read` / `OutputStream.write` | Có | Cô lập nếu API đồng bộ; chú ý client chậm và resource cleanup |
| `Synchronized`/locks chờ dài | Có thể | Loại bỏ contention, không chỉ đổi scheduler |
| `Mono.block()` / `Flux.blockLast()` | Có | Không dùng trong reactive request pipeline |
| CPU-heavy JSON transformation | Không I/O, nhưng chiếm CPU | `parallel` hoặc dedicated compute pool, giới hạn công việc |
| Jackson HTTP codec thường | Có thể dùng CPU/allocations đáng kể | Giới hạn payload; codec không nên tự thêm blocking I/O |
| WebClient non-blocking | Thông thường không block thread gọi | Dùng reactive composition, connection pool/timeout/limit |
| Reactive database driver | Thiết kế non-blocking | Vẫn cần pool/concurrency/backpressure |
| `Mono.just(expensiveCall())` | **Có**, chạy expensiveCall trước | Dùng `fromCallable` để hoãn side effect |
| `Mono.fromCallable(...)` | Bản thân lazy, không tự chuyển thread | Thêm `subscribeOn(boundedElastic)` khi callable block |

Nếu thư viện được quảng cáo là “async” nhưng thực ra dùng sync I/O và giữ thread, vẫn cần đo/kiểm tra. Nếu chỉ đổi tên method thành `Mono<...>` mà bên trong gọi blocking code trên event loop, hệ thống vẫn bị nghẽn.

### 3.1. Khả năng event loop chịu tải không vô hạn

Netty event loops phù hợp các callback ngắn, không blocking. Ví dụ một event loop có 100 connections; chỉ một handler giữ thread 500 ms cũng có thể làm nhiều connections khác trễ dù CPU hầu như rảnh. Khi streaming, điều này biểu hiện thành event SSE đến thành cụm, NDJSON response chậm hoặc health endpoint có latency spikes.

Đừng sửa bằng cách tăng mù quáng số Netty event-loop threads. Nếu thread đang bị block 2 giây, thêm vài threads không giải quyết được điểm nghẽn gốc hoặc capacity của downstream.

## 4. Các Scheduler quan trọng trong Reactor

| Scheduler | Đặc điểm | Phù hợp | Không phù hợp |
| --- | --- | --- | --- |
| `Schedulers.immediate()` | Chạy task tại thread hiện có | Đoạn xử lý nhẹ | Không cô lập blocking |
| `Schedulers.single()` | Chia sẻ một thread chuyên dụng | Công việc tuần tự nhẹ | Một task blocking sẽ giữ mọi task chung |
| `Schedulers.parallel()` | Fixed pool dựa theo CPU | CPU-bound calculations ngắn | JDBC, blocking socket, file I/O chờ |
| `Schedulers.boundedElastic()` | Shared pool chuyên dành cho blocking có **giới hạn threads và pending tasks** | Legacy blocking I/O, migration | Không tự bảo vệ toàn hệ thống khỏi request flood |
| `Schedulers.newBoundedElastic(...)` | Pool riêng với cap/queue có thể định cấu hình | Isolate một dependency theo SLA/quotas | Không thay admission control của toàn app |
| `Schedulers.fromExecutorService(...)` | Bọc Java ExecutorService | Tích hợp pool hiện có có lifecycle rõ | Không nên mặc định dùng common unbounded executor |

Một số chú ý:

- `Schedulers.elastic()` cũ không được khuyến nghị để cô lập lượng blocking lớn, vì có thể tạo quá nhiều threads và che vấn đề backpressure.
- `Schedulers.parallel()` và `single()` đánh dấu threads thuộc diện **non-blocking**; gọi `block()` trên chúng có thể ném `IllegalStateException`.
- `boundedElastic` là nơi hợp lý để chờ một thư viện blocking, **không** làm cho external library có HTTP/TCP backpressure.
- Scheduler không phải Reactive Streams Subscriber. `request(n)` là tín hiệu demand; scheduler là nơi task chạy. Hai cơ chế bổ sung nhưng không thay nhau.

### 4.1. Giới hạn mặc định của boundedElastic trong Reactor 3.7

Theo Javadoc/Reactor 3.7:

- Shared `boundedElastic()` có giới hạn **tối đa mặc định 10 × số CPU processors** ở runtime cho backing platform threads.
- Mức queue mặc định là **100.000 task đang đợi trên mỗi backing thread**, không phải một hàng đợi 100.000 toàn hệ thống.
- Sau khi queue/capacity tương ứng đầy, việc schedule có thể ném **`RejectedExecutionException`**.
- Idle pools có thể được thu hồi sau một khoảng thời gian (mặc định khoảng 60 giây với platform-thread implementation).
- Các defaults có thể được điều chỉnh bằng system properties `reactor.schedulers.defaultBoundedElasticSize` và `reactor.schedulers.defaultBoundedElasticQueueSize` **trước khi global scheduler khởi tạo**.

Các số mặc định này **không phải capacity recommendation cho mọi server**. Thí dụ 8 CPUs có thể cho phép khoảng 80 backing threads và rất nhiều tasks được queue; downstream DB pool chỉ có 10 connections vẫn có thể overload hoặc gây latency lớn. 100.000 queued tasks **mỗi backing thread** là giới hạn kỹ thuật, không phải hàng đợi ngắn tốt cho interactive HTTP API.

Đừng đặt toàn bộ endpoint legacy, export lớn và log blocking vào cùng shared scheduler mà không có ranh giới, nếu từng workload có SLO và tải khác nhau.

## 5. Mẫu cơ bản đúng: fromCallable + subscribeOn

### 5.1. Sai: gọi blocking trước khi tạo Mono

```java
// Anti-pattern: legacyClient.fetch(id) chạy ngay trên
// thread hiện tại, có thể là Netty event loop.
return Mono.just(legacyClient.fetch(id));
```

`Mono.just(...)` chỉ bọc **giá trị đã được tính xong**. Java đánh giá `fetch(id)` trước khi `Mono.just` được gọi. Dù thêm `.subscribeOn(boundedElastic())` sau đó, thao tác `fetch` vẫn đã chạy **trước** khi scheduling.

### 5.2. Đúng: trì hoãn và chuyển subscription

```java
Mono<Customer> find(String id) {
    return Mono.fromCallable(() -> legacyClient.fetch(id))
            .subscribeOn(Schedulers.boundedElastic());
}
```

Đây là **fragment**, giả định `legacyClient.fetch` có blocking contract và trả một `Customer`. Nó là `Mono` lazy; callable được gọi khi subscription diễn ra trên một boundedElastic worker. Reactor khuyến nghị đặt `subscribeOn` gần nguồn blocking.

`Mono.fromCallable` có thể complete empty nếu callable trả null; nếu null là lỗi nghiệp vụ, chọn `switchIfEmpty(Mono.error(...))` để tạo 404/502 phù hợp.

### 5.3. Với thao tác blocking không trả kết quả

```java
Mono<Void> writeAudit(AuditLine input) {
    return Mono.fromRunnable(() -> blockingAuditSink.write(input))
            .subscribeOn(Schedulers.boundedElastic())
            .then();
}
```

Đây là fragment. `Mono.fromRunnable` phù hợp với tác vụ chỉ side effect không trả result. Đừng dùng `subscribe()` trong service để “fire-and-forget” mà không có owner/lifecycle/error tracking; HTTP request kết thúc có thể khiến lỗi audit bị mất. Nếu audit phải durable, cân nhắc outbox/message broker/job và transaction boundary.

### 5.4. Kiểm tra thread bằng log

```java
Mono.fromCallable(() -> {
    String name = Thread.currentThread().getName();
    return "read-on=" + name;
}).subscribeOn(Schedulers.boundedElastic());
```

Đây là fragment; muốn thấy kết quả phải subscribe qua test/HTTP pipeline. **Không assert chính xác tên thread ở production**: implementation có thể khác theo Reactor version, scheduler custom hoặc Java 21 virtual-thread mode.

### 5.5. Đừng gọi block() để “hoàn tất” pipeline

```java
// Sai trong handler WebFlux:
Customer c = find(id).block();
return ServerResponse.ok().bodyValue(c);
```

Thay bằng:

```java
return find(id)
        .flatMap(customer ->
                ServerResponse.ok().bodyValue(customer));
```

Functional WebFlux handler trả `Mono<ServerResponse>` và framework subscribe. `block()` trên event loop có thể ném lỗi hoặc cản trở các HTTP requests khác.

## 6. subscribeOn khác publishOn như thế nào?

### 6.1. subscribeOn: ảnh hưởng upstream subscription/source

```java
Mono<String> pipeline =
        Mono.fromCallable(() -> blockingGateway.read())
            .subscribeOn(Schedulers.boundedElastic())
            .map(String::trim);
```

`subscribeOn` tác động nơi source/subscription được thực thi. Với blocking source, vị trí gần nguồn giúp người đọc biết nguyên nhân scheduling.

### 6.2. publishOn: chuyển execution context downstream

```java
Flux<Result> pipeline =
        incoming
            .publishOn(Schedulers.parallel())
            .map(this::expensiveCpuTransform);
```

`publishOn` tạo ranh giới scheduler cho các operators phía sau cho tới ranh giới khác; nó có **prefetch/queue** riêng. Phù hợp tách CPU-heavy transform có giới hạn; không nên dùng `parallel` cho blocking JDBC hoặc `Thread.sleep`.

Một cách khác để cô lập blocking stage:

```java
return source
        .flatMap(item ->
            Mono.fromCallable(() -> blockingGateway.fetch(item))
                .subscribeOn(Schedulers.boundedElastic()),
            4);
```

Đây là fragment: tạo **một Mono lazy cho mỗi item**, chạy blocking call trên boundedElastic, tối đa bốn inner publishers active trong subscription đó.

### 6.3. Thứ tự/cấu trúc mới là điều quyết định

Chỉ thêm `publishOn(boundedElastic)` ở cuối chain **không quay ngược thời gian** để di chuyển blocking call đã chạy trước đó. Ví dụ sau vẫn có nguy cơ block event loop:

```java
return source
        .map(id -> blockingGateway.fetch(id))  // chạy trước
        .publishOn(Schedulers.boundedElastic());
```

Nếu bạn thực sự cần di chuyển toàn bộ đoạn `map` xuống pool, phải đặt `publishOn` **trước** `map` — nhưng dùng `flatMap(id -> Mono.fromCallable(...).subscribeOn(...), n)` thường làm ranh giới blocking và concurrency rõ hơn.

## 7. Tự tạo scheduler riêng cho hệ thống legacy

Dùng `newBoundedElastic` để phân vùng riêng:

```java
@Configuration
class LegacySchedulerConfig {
    @Bean(destroyMethod = "dispose")
    Scheduler legacyIoScheduler() {
        return Schedulers.newBoundedElastic(
                4,              // tối đa 4 backing threads
                32,             // queue cap mỗi backing thread
                "legacy-io");   // tên thread prefix
    }
}
```

Đây là **class fragment**, cần imports `@Configuration`, `@Bean`, `reactor.core.scheduler.Scheduler`/`Schedulers`. `dispose()` khi Spring context đóng giải phóng scheduler riêng. Với Spring Boot 3.5, bean type Scheduler có thể được injected theo qualifier.

**4 threads, 32 pending tasks/thread** là con số **để học**, không phải thông số production. Tham số thứ hai của `Schedulers.newBoundedElastic(threadCap, queuedTaskCap, name)` là **queue capacity PER BACKING THREAD**, không phải 32 task cho toàn pool; đừng trình bày nó như global request quota.

Lợi ích của scheduler riêng:

- Một dependency chậm không chiếm toàn bộ shared boundedElastic.
- Dễ thu thập metrics theo tên scheduler.
- Có thể áp timeout/rejection policy riêng.
- Thread cap phản ánh giới hạn sơ bộ của downstream.
- Có lifecycle rõ; không tạo một scheduler mới **trong mỗi HTTP request**.

Không nên:

```java
// Anti-pattern: mỗi request tạo pool mới, dễ leak resources:
Mono.fromCallable(this::blockingWork)
        .subscribeOn(
            Schedulers.newBoundedElastic(4, 32, "per-request"));
```

Scheduler tạo theo request mà không dispose gây resource leak và chi phí quản lý. Dùng singleton Spring bean hoặc shared scheduler khi phù hợp.

## 8. Giới hạn đồng thời bằng flatMap và flatMapSequential

Một `Flux<ID>` có thể nhận hàng trăm ID. Nếu viết:

```java
return ids.flatMap(id -> legacyService.find(id));
```

`flatMap` có default concurrency/prefetch nhất định, có thể tạo nhiều inner subscriptions và queue. Với blocking downstream, **đặt concurrency rõ**:

```java
Flux<Result> responses = ids
        .flatMap(
            id -> legacyService.find(id),
            4);
```

Trong **một subscription** của pipeline này, `flatMap(..., 4)` giới hạn số inner publishers được subscribe cùng lúc, giúp chỉ có tối đa bốn calls đang được điều phối đồng thời trong stream đó.

Lưu ý:

- `flatMap` có thể phát kết quả **khác thứ tự ID đầu vào** vì task hoàn thành khác nhau.
- `flatMapSequential(mapper, 4)` cho phép inner tasks concurrent nhưng **giữ thứ tự output**; để giữ thứ tự có thể phải buffer các kết quả hoàn thành sớm.
- `concatMap` thực hiện inner publishers **tuần tự** (thường concurrency hiệu dụng 1) và giữ thứ tự.
- `flatMap(mapper, concurrency, prefetch)` có tham số prefetch bổ sung, ảnh hưởng demand/queues; không phải hard byte memory cap.
- Nếu một item là object 10 MB, concurrency 4 vẫn có thể giữ hàng chục MB + codec overhead.
- Với nguồn hot, concurrency control không tự điều khiển broker hoặc sensor đang push bất chấp demand.

### 8.1. Khác biệt giữa per-stream và global concurrency

Giả sử mỗi HTTP request gọi:

```java
Flux.range(1, 100)
    .flatMap(this::blockingFetch, 4);
```

Nếu có **200 HTTP requests** đồng thời, tổng số inner subscriptions được phép tới mức lý thuyết `200 × 4 = 800` (trước khi scheduler/downstream giới hạn). Vì vậy **`flatMap(...,4)` không phải giới hạn toàn ứng dụng 4 calls**.

Ngoài per-stream cap, cần cân nhắc:

1. Global concurrency/bulkhead theo dependency.
2. Scheduler thread cap và queue cap.
3. HTTP client connection pool / JDBC pool.
4. Gateway limits, tenant quotas, fairness.
5. Timeouts và circuit breaker.
6. Memory dùng cho buffered outputs và in-flight items.

Nếu deploy ba instances, mỗi instance cap 4 vẫn có thể có 12 calls toàn cụm. Global/cross-node quota cần coordinator/broker/gateway hoặc service-side policy, không chỉ `Semaphore` trong JVM.

## 9. Non-blocking bulkhead với Semaphore.tryAcquire

Một `Semaphore` có thể giới hạn số blocking operations **đang thực thi**, nhưng phải dùng cẩn thận để không chặn event loop.

**Sai:**

```java
// Anti-pattern nếu chạy trong reactive event-loop thread:
semaphore.acquire(); // BLOCK đến khi có permit!
try {
    blockingGateway.fetch();
} finally {
    semaphore.release();
}
```

**Tốt hơn:** nếu cần cap, dùng `tryAcquire()` không blocking bên trong callable đã được schedule:

```java
Mono<Result> fetchBounded(String id) {
    return Mono.fromCallable(() -> {
        if (!slots.tryAcquire()) {
            throw new LegacyBusyException();
        }
        try {
            return blockingGateway.fetch(id);
        } finally {
            slots.release();
        }
    }).subscribeOn(legacyScheduler);
}
```

Đây là **fragment**, giả định singleton `Semaphore slots`, dedicated `Scheduler legacyScheduler` và exceptions/types có thật. Khi hết permits, task chạy trên worker sẽ fail-fast thay vì chờ permit. Nhưng task vẫn có thể **chờ trong scheduler queue trước khi chạy đến tryAcquire**. Vì vậy:

- Scheduler queue vẫn cần giới hạn và theo dõi.
- Nếu yêu cầu reject *ngay khi vào HTTP endpoint*, cần admission control ở request boundary/gateway hoặc cơ chế acquire non-blocking **trước** scheduling với cancellation-safe ownership.
- Không dùng `tryAcquire(timeout, unit)` trên event loop; dù có timeout nó vẫn **blocking**.
- Permit phải release trong `finally` đúng lúc blocking call thực sự kết thúc, không chỉ khi downstream cancel.
- Nếu release permit trong `doFinally` mà blocking thread vẫn đang chạy sau cancel/timeout, bạn có thể đếm thiếu active calls và cho phép quá nhiều work thực. Hãy gắn permit lifetime vào **actual blocking task** hoặc dùng bulkhead library có contract cancellation rõ.
- Nếu task bị queue rồi bị cancel **trước khi bắt đầu**, phương án acquire bên trong callable không leak permit.

Với tính năng phức tạp (fairness, metrics, global distribution, slow queue, circuit breaker), dùng thư viện bulkhead/rate-limiter được duy trì hoặc ingress admission controls; `Semaphore` demo chỉ minh họa nguyên tắc.

## 10. RejectedExecutionException, overload và HTTP status

Khi `newBoundedElastic` hết backing threads và hàng đợi cho task, scheduling có thể ném `RejectedExecutionException`. Nếu dependency đang quá bận và custom bulkhead `tryAcquire` trả false, chúng ta có thể trả **503 Service Unavailable** với `Retry-After` có kiểm soát.

```java
return legacyService.find(id)
        .flatMap(result ->
            ServerResponse.ok().bodyValue(result))
        .onErrorResume(
            RejectedExecutionException.class,
            ex -> ServerResponse.status(503)
                    .header("Retry-After", "1")
                    .bodyValue(Map.of(
                        "code", "LEGACY_CAPACITY_EXCEEDED")));
```

Đây là **fragment**. Không coi `503 Retry-After: 1` là một công thức chung. Chọn retry hint dựa trên service semantics, SLO, load và jitter/backoff. Trên request đã trả một phần stream, có thể **không đổi** status 200 sang 503; xem phần streaming phía dưới.

### 10.1. Phân biệt 429 và 503

- **429 Too Many Requests:** client/tenant đã vượt request rate/quota theo chính sách.
- **503 Service Unavailable:** phụ thuộc/instance tạm thời không có capacity.
- **504 Gateway Timeout:** gateway không nhận response từ upstream đúng hạn trong mô hình tương ứng.
- **500 Internal Server Error:** lỗi nội bộ không phân loại hoặc bug.
- **408 Request Timeout:** client không gửi request đủ đúng hạn theo HTTP semantics.

Không map toàn bộ `TimeoutException` thành 429, hay toàn bộ `RejectedExecutionException` thành lỗi 400. Cần nhất quán error code, metrics và policy retries.

## 11. Timeout và cancellation không phải phép màu

Một cách giới hạn thời gian:

```java
return legacyService.find(id)
        .timeout(Duration.ofMillis(500));
```

`timeout` phát `TimeoutException` cho downstream nếu quá hạn và thường cancel subscription upstream. Tuy nhiên:

- Thread đang chạy trong blocking JDBC/SDK có thể **không dừng ngay** hoặc không hỗ trợ interrupt.
- Task trong queue có thể chưa bắt đầu; cancel có thể ngăn nó chạy trong những trường hợp scheduler hỗ trợ.
- `Thread.interrupt` không đồng nghĩa network socket/DB operation chắc hủy được.
- Side effect đã commit (ví dụ thanh toán hoặc gửi email) không được rollback chỉ vì downstream timeout.
- Nếu client retry sau timeout mà server vẫn xử lý, request có thể chạy **hai lần**.
- `doOnCancel` và `doFinally(CANCEL)` thông báo vòng đời publisher, không bảo đảm hoàn tất cleanup của external work.

### 11.1. Deadline và timeout nhiều tầng

Một lời gọi legacy nên có:

1. HTTP client/request deadline.
2. Connection acquisition timeout.
3. Socket/connect/read timeout của **SDK hoặc database driver** thực tế.
4. Bulkhead/queue-wait deadline.
5. Reactor `timeout` cho end-to-end promise.
6. Gateway/ingress timeout và retry policy.
7. Idempotency key/transaction semantics cho operations có side effects.

Nếu Reactor timeout 200 ms nhưng JDBC driver chỉ timeout 30 s, client có thể được trả lỗi sớm trong khi thread/connection DB vẫn bị giữ lâu. Tốt hơn là thiết kế **timeout tại nguồn blocking** và hạn chế inflight operations.

### 11.2. Không retry vô hạn khi đang overload

```java
// Không nên:
return legacyService.find(id).retry();
```

Với dependency đang cạn capacity, retry vô hạn tạo **retry storm**, giữ scheduler queue và connection pool đầy. Dùng retry có hạn mức, exponential backoff/jitter, chỉ với lỗi retryable, và chỉ khi operation idempotent hoặc có dedupe key. Request đã streaming một phần thường không retry lại mà không có framing/checkpoint.

## 12. Streaming WebFlux: producer chậm, consumer chậm và buffering

### 12.1. Dùng NDJSON

HTTP response kiểu NDJSON:

```http
HTTP/1.1 200 OK
Content-Type: application/x-ndjson

{"id":"A","value":"value-A"}
{"id":"B","value":"value-B"}
{"id":"C","value":"value-C"}
```

Một `Flux<Record>` trả về `ServerResponse.body(flux, Record.class)` có thể được encode theo từng record nếu content type là `application/x-ndjson`. Nhưng:

- `flatMap` mặc định có thể reorder; `flatMapSequential` hoặc `concatMap` nếu phải giữ input ordering.
- Codec có thể có buffer per record, network có outbound queues.
- Proxy/CDN có thể gom nhiều events và chỉ flush cuối.
- `subscribeOn(boundedElastic)` cô lập nguồn blocking, không trực tiếp điều khiển TCP flush.
- Nếu client ngắt, downstream có thể cancel stream nhưng task blocking đã bắt đầu có thể còn chạy.
- Nếu lỗi tại record 20 và HTTP 200 đã committed, response có thể chỉ chứa 19 records mà không có JSON error hoàn chỉnh.

**Dữ liệu mỗi record vẫn cần validation và total stream quotas.** Trong demo, nhập vào là danh sách IDs tối đa tám để giới hạn số task; bản production cần validate IDs/authorization/tenant boundary.

### 12.2. Với SSE

Một live dashboard có thể gửi:

```text
id: 7
event: progress
data: {"percent":70}

id: 8
event: complete
data: {"percent":100}

```

SSE `ServerSentEvent<T>` được WebFlux encode thành `text/event-stream`. Nếu dữ liệu được tạo bởi blocking SDK, wrap từng call bằng bounded scheduler hoặc tốt hơn dùng asynchronous source. **Không tạo một blocking thread cho mỗi SSE subscriber rồi `while(true) Thread.sleep(...)`**: nó giữ worker rất lâu, cạn pool.

Cân nhắc:

- Dùng scheduler timer/reactive `Flux.interval` cho heartbeat thay vì sleeping workers.
- Shared pub/sub nguồn dữ liệu và per-client bounded queue/drop/latest strategy (nếu cho phép mất update).
- Khi cần mọi event đầy đủ, dùng durable broker + IDs + replay.
- Connection limits/heartbeat/reconnect/backoff.
- Không coi Reactor demand là một HTTP wire command `request(n)` từ browser EventSource.

### 12.3. Slow consumers và response encoding

Khi client nhận chậm, Reactor Netty có thể điều tiết demand dựa trên write readiness, nhưng operator queues, JSON encoding và proxy buffers vẫn tồn tại. Nếu mỗi response item chứa vài MB dữ liệu, concurrency 2 cũng có thể dùng rất nhiều heap/direct memory.

Không dùng `onBackpressureBuffer()` unbounded để “chữa” slow network; nó có thể gây OOM. Nếu dữ liệu cho phép mất mẫu, chọn `onBackpressureLatest`/`onBackpressureDrop` với policy; nếu dữ liệu quan trọng, backpressure tới nguồn hoặc dùng broker/replay.

## 13. Ứng dụng runnable: Spring Boot 3.5 + WebFlux.fn + bounded legacy calls

Demo gồm hai endpoints:

- `GET /api/legacy/{id}`: gọi một service **blocking mô phỏng**, chạy trên dedicated boundedElastic, trả JSON khi thành công.
- `GET /api/legacy/stream?ids=A,B,C`: trả **NDJSON stream** giữ thứ tự đầu vào nhờ `flatMapSequential(..., 2)`; tối đa tám IDs mỗi request.
- Mỗi blocking call sử dụng `Semaphore.tryAcquire` trong **worker** để giới hạn **ba calls đang thực thi trong một JVM**.
- Scheduler riêng có tối đa bốn backing platform threads và queue cap 32 trên mỗi backing thread. Khi không còn capacity, custom exception hoặc scheduler rejection được map thành 503 cho endpoint single; với stream đã bắt đầu, phải xem giới hạn HTTP committed response.
- Tests dùng `WebTestClient` thật qua HTTP và `StepVerifier`/metrics để xác nhận output và tính chất concurrency.

**Phạm vi:** demo chỉ có read-only simulated service. `Thread.sleep(70)` minh họa blocking SDK; đây **không** phải hành vi nên để trong production. Chưa có auth/tenant quota, DB/HTTP client thật, distributed concurrency limiter hoặc guaranteed flow control qua proxy.

### 13.1. Tạo project Gradle

Chọn Java 17, Spring Boot 3.5.x, Gradle và **Spring Reactive Web** trong Initializr. Trong project có Boot plugin, dependency management, Maven Central và toolchain, dependencies:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.projectreactor:reactor-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Đây là **fragment của build.gradle**, không phải file Gradle độc lập. Không thêm `spring-boot-starter-web` vào demo nếu muốn WebFlux/Netty: Boot 3.x thường chọn Servlet MVC khi cả MVC và WebFlux starters có mặt.

### 13.2. Java source: một file hoàn chỉnh

Tạo **`src/main/java/demo/isolation/IsolationApplication.java`**:

```java
package demo.isolation;

import java.util.Arrays;
import java.util.List;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.Semaphore;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.stereotype.Service;
import org.springframework.web.reactive.function.server.RouterFunction;
import org.springframework.web.reactive.function.server.RouterFunctions;
import org.springframework.web.reactive.function.server.ServerRequest;
import org.springframework.web.reactive.function.server.ServerResponse;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Scheduler;
import reactor.core.scheduler.Schedulers;

@SpringBootApplication
public class IsolationApplication {
    public static void main(String[] args) {
        SpringApplication.run(IsolationApplication.class, args);
    }
}

record LegacyRecord(String id, String value) {}

record ApiError(String code) {}

class LegacyBusyException extends RuntimeException {}

@Configuration
class IsolationConfig {

    @Bean(destroyMethod = "dispose")
    Scheduler legacyIoScheduler() {
        // Demo: 4 threads, 32 queued tasks per backing thread.
        return Schedulers.newBoundedElastic(
                4, 32, "legacy-io");
    }

    @Bean
    RouterFunction<ServerResponse> legacyRoutes(
            LegacyHandler handler) {
        return RouterFunctions.route()
                // Static route trước variable route.
                .GET("/api/legacy/stream", handler::stream)
                .GET("/api/legacy/{id}", handler::single)
                .build();
    }
}

@Component
class LegacyBlockingGateway {
    private final Semaphore slots = new Semaphore(3);
    private final AtomicInteger active = new AtomicInteger();
    private final AtomicInteger peak = new AtomicInteger();

    LegacyRecord fetch(String id) throws InterruptedException {
        // Chỉ chạy bên trong scheduled callable.
        if (!slots.tryAcquire()) {
            throw new LegacyBusyException();
        }

        int inFlight = active.incrementAndGet();
        peak.accumulateAndGet(inFlight, Math::max);

        try {
            // Mô phỏng SDK đồng bộ/legacy API.
            Thread.sleep(70L);
            return new LegacyRecord(id, "value-" + id);
        } finally {
            active.decrementAndGet();
            slots.release();
        }
    }

    int peakActive() {
        return peak.get();
    }

    int activeNow() {
        return active.get();
    }
}

@Service
class LegacyService {
    private final LegacyBlockingGateway gateway;
    private final Scheduler legacyScheduler;

    LegacyService(
            LegacyBlockingGateway gateway,
            @Qualifier("legacyIoScheduler")
            Scheduler legacyScheduler) {
        this.gateway = gateway;
        this.legacyScheduler = legacyScheduler;
    }

    Mono<LegacyRecord> fetch(String id) {
        return Mono.fromCallable(() -> gateway.fetch(id))
                .subscribeOn(legacyScheduler);
    }
}

@Component
class LegacyHandler {
    private final LegacyService service;

    LegacyHandler(LegacyService service) {
        this.service = service;
    }

    private Mono<ServerResponse> invalidIds() {
        return ServerResponse.badRequest()
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(new ApiError("INVALID_IDS"));
    }

    private Mono<ServerResponse> overloaded() {
        return ServerResponse
                .status(HttpStatus.SERVICE_UNAVAILABLE)
                .header(HttpHeaders.RETRY_AFTER, "1")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(new ApiError("LEGACY_OVERLOADED"));
    }

    Mono<ServerResponse> single(ServerRequest request) {
        String id = request.pathVariable("id");
        if (!id.matches("[A-Za-z0-9-]{1,16}")) {
            return invalidIds();
        }

        return service.fetch(id)
                .flatMap(record ->
                    ServerResponse.ok()
                        .contentType(MediaType.APPLICATION_JSON)
                        .bodyValue(record))
                .onErrorResume(
                    LegacyBusyException.class,
                    error -> overloaded())
                .onErrorResume(
                    RejectedExecutionException.class,
                    error -> overloaded());
    }

    Mono<ServerResponse> stream(ServerRequest request) {
        String raw = request.queryParam("ids")
                .orElse("");

        List<String> ids = Arrays.stream(
                raw.split(",", -1))
                .map(String::trim)
                .toList();

        if (ids.isEmpty() || ids.size() > 8
                || ids.stream().anyMatch(id ->
                    !id.matches("[A-Za-z0-9-]{1,16}"))) {
            return invalidIds();
        }

        Flux<LegacyRecord> records =
                Flux.fromIterable(ids)
                    // Concurrency per HTTP response = 2.
                    // Giữ thứ tự dù blocking call hoàn tất khác nhau.
                    .flatMapSequential(service::fetch, 2);

        return ServerResponse.ok()
                .contentType(MediaType.APPLICATION_NDJSON)
                .body(records, LegacyRecord.class);
    }
}
```

**Cấu trúc Java:** `IsolationApplication` là public class duy nhất trong một file Java 17; các records/classes package-private cùng package nên Spring component scan phát hiện `IsolationConfig`, `LegacyBlockingGateway`, `LegacyService` và `LegacyHandler`.

**Chú thích an toàn/semantics:**

- `LegacyService.fetch` tạo Mono **lazy**, callable chạy trên custom scheduler khi subscribe; Netty event loop không chạy `Thread.sleep(70L)`.
- `LegacyBlockingGateway.fetch` dùng `Semaphore.tryAcquire` bên trong scheduled work nên **không block khi chờ permit**. `finally` trả permit ngay khi actual fetch kết thúc, kể cả exception/interrupt. Nếu task bị cancel trước khi bắt đầu, chưa acquire permit.
- `peakActive`/`activeNow` là local JVM metrics **cho test/giải thích**, không phải toàn cluster. Không trả thông tin này ra public API production nếu không cần.
- `flatMapSequential(...,2)` chỉ giới hạn concurrency **mỗi HTTP stream**; các request khác dùng cùng scheduler/bulkhead.
- `ids.size() ≤ 8` là quota per-request cho demo. ID regex giới hạn cú pháp/độ dài, nhưng không phải authorization hoặc defense chống toàn bộ request floods.
- `ServerResponse.body(flux, LegacyRecord.class)` là body writer của WebFlux.fn; `application/x-ndjson` giúp writer phát mỗi record theo dòng.
- `onErrorResume(Rejection...)` xử lý **single** trước khi `ServerResponse` được tạo. Đối với `stream`, response có thể commit trong lúc ghi những records đầu; không bảo đảm có thể trả 503 JSON khi task thứ N bị reject.
- ``32 queued tasks per backing thread`` không phải cap 32 cho toàn endpoint; nếu 200 requests đồng thời, một số có thể bị queue trước khi gateway `tryAcquire`.
- Nếu một external SDK bỏ qua interruption, Reactor cancellation không bảo đảm release permit sớm: permit thuộc vòng đời thực của `fetch`.
- Nếu muốn một bulkhead **reject ngay tại lúc HTTP admission** chứ không phải lúc worker bắt đầu, cần thiết kế cancellation-safe acquisition ở request boundary và bounded queues độc lập.

### 13.3. Chạy và thử HTTP

Khởi chạy:

```bash
./gradlew bootRun
```

**Gọi một ID:**

```bash
curl -i \
  'http://localhost:8080/api/legacy/A'
```

Khi không bị overload, body dự kiến:

```json
{"id":"A","value":"value-A"}
```

**NDJSON stream nhiều ID:**

```bash
curl -N -i \
  -H 'Accept: application/x-ndjson' \
  'http://localhost:8080/api/legacy/stream?ids=A,B,C'
```

Body dự kiến, theo thứ tự input nhờ `flatMapSequential`:

```text
{"id":"A","value":"value-A"}
{"id":"B","value":"value-B"}
{"id":"C","value":"value-C"}
```

**ID không hợp lệ hoặc quá nhiều IDs:**

```bash
curl -i \
  'http://localhost:8080/api/legacy/stream?ids=A,B,not%20allowed'
```

Response dự kiến 400:

```json
{"code":"INVALID_IDS"}
```

**Để thử overload thật**, cần load test tạo nhiều simultaneous HTTP clients và đo `activeNow`/`peakActive`, scheduler queue và rejection counts. Một lệnh curl đơn lẻ không chứng minh bulkhead đã hoạt động trong trạng thái quá tải.

Các output minh họa ở đây là **dự kiến từ thiết kế**, **không phải kết quả chạy Gradle hoặc load test thực tế**.

## 14. Kiểm thử WebTestClient và StepVerifier

### 14.1. Vì sao cần hai loại test?

- **`WebTestClient` qua RANDOM_PORT:** kiểm tra HTTP codec, route, status, NDJSON framing và response contents trên embedded Reactor Netty.
- **`StepVerifier` với `Mono/Flux`:** kiểm tra publisher signals, error, cancel, terminal state mà không cần HTTP.
- **Load test slow consumers:** đo actual inflight work, queue depth, latency, CPU, direct memory và behavior khi cùng lúc có nhiều clients.
- **Thread assertion:** chỉ là hỗ trợ, không nên hardcode tên exact thread; Java21 virtual threads/scheduler implementations có thể đổi naming.

### 14.2. Bài kiểm thử cho Java 17 demo

Tạo **`src/test/java/demo/isolation/IsolationApplicationTests.java`**:

```java
package demo.isolation;

import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;
import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class IsolationApplicationTests {

    @Autowired
    WebTestClient client;

    @Autowired
    LegacyService service;

    @Autowired
    LegacyBlockingGateway gateway;

    @Test
    void singleReadRespondsWithJson() {
        client.get()
                .uri("/api/legacy/A")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.id").isEqualTo("A")
                .jsonPath("$.value").isEqualTo("value-A");
    }

    @Test
    void invalidIdIsRejectedBeforeSchedulingWork() {
        client.get()
                .uri("/api/legacy/invalid_id")
                .exchange()
                .expectStatus().isBadRequest()
                .expectBody()
                .jsonPath("$.code")
                    .isEqualTo("INVALID_IDS");
    }

    @Test
    void streamingEndpointPreservesRecordOrder() {
        Flux<LegacyRecord> body = client.get()
                .uri("/api/legacy/stream?ids=A,B,C,D")
                .accept(MediaType.APPLICATION_NDJSON)
                .exchange()
                .expectStatus().isOk()
                .expectHeader().contentTypeCompatibleWith(
                        MediaType.APPLICATION_NDJSON)
                .returnResult(LegacyRecord.class)
                .getResponseBody();

        StepVerifier.create(body)
                .expectNext(new LegacyRecord("A", "value-A"))
                .expectNext(new LegacyRecord("B", "value-B"))
                .expectNext(new LegacyRecord("C", "value-C"))
                .expectNext(new LegacyRecord("D", "value-D"))
                .verifyComplete();
    }

    @Test
    void streamRejectsTooManyIds() {
        client.get()
                .uri("/api/legacy/stream?ids=A,B,C,D,E,F,G,H,I")
                .exchange()
                .expectStatus().isBadRequest()
                .expectBody()
                .jsonPath("$.code")
                    .isEqualTo("INVALID_IDS");
    }

    @Test
    void serviceIsLazyUntilSubscriberConsumes() {
        // Constructor creates a Mono; it does not execute Gateway.
        var publisher = service.fetch("LAZY");
        StepVerifier.create(publisher)
                .expectNext(new LegacyRecord(
                        "LAZY", "value-LAZY"))
                .verifyComplete();
    }

    @Test
    void perStreamConcurrencyIsAtMostTwo() {
        StepVerifier.create(
                Flux.fromIterable(List.of(
                    "1", "2", "3", "4", "5", "6"))
                    .flatMapSequential(service::fetch, 2))
                .expectNextCount(6)
                .verifyComplete();

        // Without concurrent unrelated tests, peak is bounded by 2.
        assertTrue(gateway.peakActive() <= 2);
        assertTrue(gateway.activeNow() == 0);
    }
}
```

Lệnh chạy:

```bash
./gradlew test
```

**Sáu tests được thiết kế để pass** khi chạy đúng baseline và mặc định JUnit chạy các test methods tuần tự. Đây **chỉ là expected behavior từ review API/mã**, **không có bằng chứng Gradle đã thực thi**. Test `peakActive() <=2` phụ thuộc trạng thái bean dùng chung và không cho phép test khác đồng thời chạy background blocking calls; nếu CI chạy tests parallel hoặc cùng app nhận traffic ngoài, hãy cô lập test context/gateway hoặc dùng test instrumentation riêng.

**Điểm yếu cần tránh:** `serviceIsLazyUntilSubscriberConsumes` ở trên **chỉ xác minh output sau subscribe**, chưa trực tiếp chứng minh “không có side effect trước subscribe” vì nó không assert counter trước đó. Một test nghiêm ngặt hơn nên inject fake gateway hoặc spy, gọi `service.fetch(id)`, assert invocation count = 0, rồi subscribe và assert count = 1. Mục đích đoạn hiện tại là test successful publisher integration.

### 14.3. Test deterministic về concurrency bằng StepVerifier

Nếu cần chứng minh concurrency cap mà không phụ thuộc thời gian Thread.sleep/CPU load, có thể tạo một source test với `AtomicInteger` và async fake tasks dùng `Mono.defer`/`Sinks.One`, chủ động điều khiển khi từng inner hoàn tất. Sau đó verify max active subscriptions theo `flatMap(...,2)`. Tránh assert wall-clock kiểu “phải nhanh hơn 140 ms” vì CI tải không ổn định.

Một test đơn giản về error propagation:

```java
StepVerifier.create(
        Mono.<String>error(
                new LegacyBusyException()))
        .expectError(LegacyBusyException.class)
        .verify();
```

Đây là **fragment** cho unit test; chỉ chứng minh Reactor truyền typed error. Test HTTP 503 cần tạo trạng thái bulkhead đầy có kiểm soát rồi assert error mapping tại handler hoặc WebTestClient.

## 15. Vì sao virtual threads không thay thế concurrency limits?

Từ Reactor 3.6, `boundedElastic` có thể hỗ trợ execution trên virtual threads khi chạy **Java 21+** và bật system property:

```properties
reactor.schedulers.defaultBoundedElasticOnVirtualThreads=true
```

Đây là **Reactor system property**, cần đặt đủ sớm (trước khi scheduler shared init), không tự suy ra nó là Spring Boot `application.properties` binding mặc định. Trong process Java, thường truyền dưới dạng:

```bash
java -Dreactor.schedulers.defaultBoundedElasticOnVirtualThreads=true \
  -jar app.jar
```

Với Java 17 baseline demo, **tùy chọn này không bật virtual threads**. Trong Java 21+, shared `Schedulers.boundedElastic()` có thể dùng virtual-thread-per-task implementation theo cấu hình Reactor; custom `Schedulers.newBoundedElastic(4,32,...)` có overload/semantics khác, đừng mặc định nghĩ mọi custom pool tự chuyển sang virtual threads.

Virtual threads giúp giảm chi phí thread bị park ở nhiều blocking calls, nhưng:

- Số connections DB vẫn bị giới hạn.
- Remote service vẫn chỉ chịu được số QPS/concurrency nhất định.
- CPU, heap, network và thread pinning vẫn có thể là bottleneck.
- Queued tasks vẫn cần capacity/timeout.
- Gọi blocking native library có thể có semantics khác pinning/interruption.
- Không bỏ bulkhead, admission controls và observability.

**Một triệu virtual threads không biến database 10 connections thành database có một triệu connections**. Chọn virtual threads dựa trên profiling và phiên bản JDK/Reactor; ưu tiên những giải pháp giảm blocking gốc khi có thể.

## 16. Scheduler lifecycle, metrics và quyết định sizing

### 16.1. Những thông số cần đo

| Metric | Ý nghĩa |
| --- | --- |
| Active running legacy tasks | Inflight blocking operations thật |
| Peak inflight / permitted slots | Bulkhead có sát capacity không |
| Scheduler backing thread count | Có thường xuyên chạm thread cap không |
| Scheduler pending queue depth | Có backlog do blocking calls quá lâu không |
| Oldest queued wait time | Client đang chờ quá lâu dù CPU rảnh? |
| Scheduled task rejections | Quá tải scheduler hoặc queue cap |
| HTTP 503 / 429 / timeout rates | Dấu hiệu policy bảo vệ đang hoạt động |
| Dependency connection pool active/pending | Nút thắt DB/HTTP client thực |
| Latency P50/P95/P99 per route | Kinh nghiệm người dùng và SLO |
| SSE time-to-first-event/event lag | Streaming client nhận chậm vì producer hay proxy |
| JVM heap + Netty direct memory | Backpressure/buffer pressure |
| Cancellation vs task completion | Task có tiếp tục chạy sau HTTP timeout không |
| Retry count and downstream QPS | Phát hiện retry storm |

Reactor có khả năng dùng Micrometer scheduler metrics khi tích hợp `reactor-core-micrometer` và đăng ký scheduler với `Micrometer.timedScheduler(...)` theo API phiên bản tương ứng. Nếu project không dùng Micrometer module, hãy đo qua runtime/JVM metrics và metrics từ service. Không bật logging mọi item/payload khi traffic cao hoặc có dữ liệu nhạy cảm.

### 16.2. Quy tắc chọn pool size (không có một con số chung)

Khi downstream legacy chỉ chịu tối đa `C` concurrent requests, scheduler thread cap và bulkhead per-instance nên được chọn với:

- Tổng traffic từ tất cả instances/clients.
- Số DB/HTTP connections thực.
- Request latency và timeout của dependency.
- Memory mỗi task/response item.
- Workload khác chia sẻ scheduler.
- Mức queuing được chấp nhận và HTTP deadline.
- Fairness giữa tenant/request class.
- Cold start/peak bursts, autoscaling và headroom.

Ví dụ hướng nghĩ:

```text
DB pool = 10 connections
Web app = 2 instances
Cần dành 4 connections cho jobs/admin/migrations

Không thể chọn mỗi app 10 blocking calls
rồi giả định tổng 20 lúc cao điểm đều an toàn.
Phải phân bổ quota theo service budget + các consumers.
```

Con số trên chỉ minh họa nguyên tắc capacity planning, không phải công thức tối ưu chung.

### 16.3. Backpressure không tự giải quyết scheduler queue

Reactive Streams `request(n)` giúp điều tiết số phần tử trong pipeline nhưng một callable blocking đã được schedule có thể giữ thread rất lâu. Nếu downstream request 1000 items từ `flatMap` với concurrency cao, rất nhiều tasks có thể vào scheduler queue. Kết hợp:

- `flatMap` explicit concurrency.
- Bounded scheduling queue.
- Bulkhead/admission control.
- Demand-aware source/records limits.
- Response writer backpressure, không tạo unbounded buffers.
- Retry/timeout policy với worker cleanup.

## 17. Bảo mật, resource ownership và yêu cầu production

1. **Không chạy blocking crypto/file scan/server-side request (SSRF) trên Netty event loop**. Nếu SDK blocking, isolate nhưng vẫn phải kiểm soát destination URLs/allowlists.
2. **Không cho user tự quyết định path/file/DB key** khi export qua blocking file API; validate/authorize trước operation.
3. Đặt **max request body, upload bytes, response record size, number of IDs, concurrency** theo tenant và endpoint.
4. Không trả raw `RejectedExecutionException`, JDBC error hoặc stack trace vào API response.
5. Không log password, Authorization, Cookie, signed URL hoặc PII trong scheduler task MDC.
6. ThreadLocal/MDC **không tự truyền xuyên scheduling boundary**. Dùng Reactor Context và context-propagation/tracing integration đúng phiên bản, explicit immutable context cho legacy library khi cần.
7. Cancellation phải giải phóng DB connections, streams và buffers đúng lifecycle, nhưng không giả định một interrupt luôn có tác dụng.
8. Nếu multiple tenants dùng shared pool, một tenant có thể chiếm queue; cần per-tenant fairness/admission.
9. Bulkhead rejection không thay rate limiting/authorization; HTTP client có thể spam nhỏ khiến queue đầy.
10. Với side effects (payment, email, job), phải có idempotency/reconciliation dù đã dùng bounded scheduler.
11. Circuit breaker đặt dựa trên failure/latency của dependency, không đóng/mở chỉ vì một lỗi input 400.
12. Sử dụng health checks và alerts có tín hiệu để không che overload bằng auto-retry vô hạn.

## 18. Troubleshooting: hiện tượng và nguyên nhân

| Triệu chứng | Nguyên nhân khả dĩ | Hướng xử lý |
| --- | --- | --- |
| WebFlux throughput thấp dù CPU nhàn | JDBC/SDK/Thread.sleep trên event loop | Profile thread dumps, cô lập blocking source |
| `Mono.just(blockingCall())` vẫn block | Tính toán diễn ra trước Mono | `Mono.fromCallable(...).subscribeOn(...)` |
| `subscribeOn` đặt sau `Mono.just` không giúp | Blocking call đã chạy | Đưa blocking work vào callable |
| `publishOn` cuối chain không giúp | Blocking `map` chạy trước boundary | Chuyển boundary trước map hoặc wrap inner Mono |
| `block()` ném IllegalStateException | Reactor non-blocking thread | Không block, dùng reactive composition |
| CPU-bound code trên boundedElastic gây queue | Dùng sai pool cho compute | Đưa compute ngắn sang `parallel`/dedicated compute |
| Pool có nhiều pending tasks | Downstream chậm, cap/queue quá rộng | Bulkhead, timeout, fail-fast, metrics |
| Global pool cạn khi export chạy | Workloads dùng chung boundedElastic | Dedicated scheduler / job queue |
| `flatMap(...,4)` nhưng có 100 calls | Nhiều HTTP requests độc lập | Global semaphore/admission + pool limits |
| Stream NDJSON kết quả không đúng thứ tự | Dùng flatMap merge kết quả | flatMapSequential/concatMap |
| NDJSON chỉ hiển thị sau nhiều giây | Proxy/codec/client buffering | `curl -N`, inspect proxy, actual first-event timings |
| Timeout HTTP nhưng DB query vẫn chạy | Driver không cancel/interrupt | Configure driver timeouts và DB statement cancellation |
| `doFinally` release permit nhưng overload vượt cap | Task vẫn chạy sau client cancel | Release permit trong actual blocking task |
| 503 tăng khi nhiều clients | Scheduler/bulkhead reject | Kiểm tra queue/dependency latency/QPS |
| Retry storm | Clients retry ngay vô hạn | Backoff, jitter, Retry-After, idempotency |
| CPU/heap tăng do `collectList()` | Tích lũy full stream | Stream response / bounded batch |
| Client đóng tab, task vẫn hoạt động | Cancellation không ngay hoặc SDK bỏ qua interrupt | Track task lifecycle, SDK cancel API |
| Streaming lỗi giữa chừng vẫn status 200 | Response committed | Protocol error, partial-stream contract |
| Số queued tasks lớn nhưng memory không đoán được | Item/task metadata và buffers khác nhau | Theo dõi queue bytes/memory và heap profile |
| Khi bật virtual threads vẫn nghẽn DB | DB/HTTP connection cap không đổi | Bulkhead/pool sizing theo dependency |

### Quy trình chẩn đoán

1. Dùng metrics/thread dump xác định **thread nào block và ở method nào**.
2. Xác nhận runtime đang dùng WebFlux/Netty, không vô tình MVC.
3. Tìm `block()`, `Thread.sleep`, JDBC, synchronous HTTP SDK trong handlers/operators.
4. Kiểm tra blocking code có nằm **bên trong lazy `fromCallable`** hay không.
5. Xem `subscribeOn`/`publishOn` xuất hiện trước/sau stage nào.
6. Kiểm tra `flatMap` concurrency mỗi stream và số simultaneous HTTP requests.
7. Kiểm tra scheduler cap/queue, DB/HTTP client pool, bulkhead permits.
8. Kiểm tra timeout thực tế ở client/driver, cancellation propagation.
9. Nếu streaming chậm, phân biệt producer, codec, proxy và browser.
10. Load test nhiều concurrent clients rồi kiểm tra heap/direct memory, QPS, p99, rejection và resource cleanup.

## 19. So sánh những lựa chọn kiến trúc

| Nhu cầu | Lựa chọn nên cân nhắc | Điều cần bảo vệ |
| --- | --- | --- |
| Một legacy SDK blocking ngắn | `Mono.fromCallable` + boundedElastic | Timeout, pool cap |
| Legacy SDK shared bởi nhiều routes | Dedicated `newBoundedElastic` bean | Queue/rejection, cross-route fairness |
| Batch IDs từ request | `flatMap(mapper,n)` | Per-stream cap, total count/bytes |
| Kết quả phải giữ thứ tự | `flatMapSequential` hoặc `concatMap` | Out-of-order buffering |
| Global concurrency tại JVM | Non-blocking bulkhead/semaphore | Permit lifetime, cancel |
| Across multiple nodes | Gateway/distributed quotas, downstream pool policies | Không dựa local semaphore |
| Blocking DB nhưng cần reactive API | Temporary boundedElastic isolation | Migration sang R2DBC nếu phù hợp |
| Số lượng tác vụ kéo dài hàng phút | Background job/queue + 202/GET status | Durable state, retry, DLQ |
| Streaming live updates không mất events | Broker + SSE/WebSocket | Replay, ordered IDs, slow consumers |
| Streaming chỉ cần trạng thái mới nhất | BackpressureLatest/coalescing | Cho phép mất intermediate updates |
| Native async client tồn tại | WebClient / reactive DB driver | Connection pooling, cancellation |

Một API không cần realtime và mất vài phút để tạo báo cáo có thể tốt hơn với `POST /exports` trả `202 Accepted` + job ID, sau đó download file đã hoàn tất; giữ hàng nghìn HTTP streaming requests trên blocking workers không phải lựa chọn tối ưu.

## 20. Các khác biệt phiên bản quan trọng

| Version | Ghi chú |
| --- | --- |
| Reactor 3.3+ | BoundedElastic được giới thiệu để thay cách dùng elastic không có thread cap |
| Reactor 3.6/3.7 | `boundedElastic` có thêm lựa chọn virtual-thread implementation trên Java 21+ khi bật system property |
| Spring Framework 6.2 / Boot 3.5 | Java17 baseline; WebFlux.fn trả `Mono<ServerResponse>` và hỗ trợ NDJSON/SSE |
| Java 17 | Không có Java virtual threads production như Java 21 |
| Java 21+ | Có thể dùng Reactor boundedElastic virtual threads theo điều kiện/configuration |
| Spring Framework 7 / Boot 4 | Kiểm tra dependency/API/test module/config migration; concepts vẫn hữu ích |

Không giả định toàn bộ Boot `spring.threads.virtual.enabled=true` đồng nghĩa shared Reactor `boundedElastic()` luôn chạy virtual threads trong mọi version. Đọc chính xác Reactor Javadoc/system property và test thread/capacity thực tế.

## 21. Checklist production

- [ ] Không có blocking JDBC/HTTP/file operation trực tiếp trên Netty event loop.
- [ ] Blocking source nằm trong `Mono.fromCallable`/`fromRunnable` lazy và có `subscribeOn` phù hợp.
- [ ] Không gọi `block()`/`blockLast()` trong WebFlux handler.
- [ ] Không tạo scheduler mới mỗi request; có bean lifecycle và dispose.
- [ ] Dedicated scheduler theo downstream khi cần workload isolation.
- [ ] Pool thread cap/queue cap đo theo service capacity, không lấy defaults làm SLO.
- [ ] `flatMap` concurrency được khai báo rõ cho các batch/streams.
- [ ] Global HTTP/dependency concurrency có bulkhead/admission riêng.
- [ ] Không `Semaphore.acquire` trên event loop; permit release theo actual task completion.
- [ ] Driver/socket/connection timeouts cùng deadline/Retry-After hợp lý.
- [ ] Cancellation/timeout không tạo duplicate side effects hoặc leaked resources.
- [ ] NDJSON/SSE phù hợp framing; không commit error status muộn.
- [ ] Streaming producer và consumer có bounded queue/backpressure policy.
- [ ] Rate limit/tenant quota, authn/authz không phụ thuộc scheduler.
- [ ] Logs/metrics không lộ credentials/PII hoặc raw rejected payload.
- [ ] Metrics có scheduler pending, active, rejection, p95/p99, dependency pool usage.
- [ ] Unit StepVerifier và WebTestClient integration tests; thêm load test concurrent clients.
- [ ] Test qua proxy thực với slow-client/reconnect/timeout/disconnect.
- [ ] Có kế hoạch migration sang non-blocking driver hoặc durable job khi tải tăng.

## 22. Bài tập tự đánh giá

1. Vì sao `Mono.just(legacy.read())` vẫn chặn event loop dù viết `subscribeOn(boundedElastic())` phía sau?
2. Hãy sửa code trên bằng `Mono.fromCallable` và giải thích lúc nào callable được gọi.
3. `Schedulers.parallel()` khác `boundedElastic()` ở mục tiêu nào? Chạy JDBC trên parallel có gì nguy hiểm?
4. So sánh tác động của `subscribeOn` và `publishOn` đối với operator `map` có blocking call.
5. Một `flatMap(...,4)` ở endpoint và 100 clients đồng thời sẽ cho phép tối đa bao nhiêu inner subscriptions nếu không có global limit?
6. `Schedulers.newBoundedElastic(4,32,"io")` có nghĩa toàn ứng dụng chỉ queue 32 tasks không? Tra Javadoc.
7. Vì sao không tạo `newBoundedElastic` trong từng HTTP request?
8. Nếu `Semaphore.tryAcquire` thực thi **bên trong scheduled callable**, requests bị queue trước đó đã được reject ngay tại HTTP admission chưa?
9. Vì sao `Semaphore.acquire` trên Netty event loop là anti-pattern?
10. Nếu HTTP timeout và `doFinally` release permit nhưng blocking query còn chạy, tác hại gì?
11. `flatMapSequential` và `concatMap` khác nhau về concurrency, order, latency và buffering thế nào?
12. Một NDJSON stream trả 100 items, item 40 lỗi sau khi 39 items đã ghi. Có thể đổi HTTP status sang 500/503 không?
13. Khi client EventSource đóng tab, blocking SDK có lập tức dừng không? Giải thích cancellation limitations.
14. Một ứng dụng có 4 instances, mỗi instance bulkhead 3. Tổng calls tới DB có thể là bao nhiêu? Muốn global 6 cần giải pháp gì?
15. Nếu DB pool chỉ có 10 connections, để `boundedElastic` mặc định nhiều threads có chắc an toàn không?
16. `Retry-After` nên được trả lúc nào? Phân biệt 429 (quota) và 503 (capacity).
17. Kết hợp timeout, circuit breaker và retry thế nào để không tạo retry storm?
18. Khi chạy Java 21, bật virtual threads cho Reactor boundedElastic bằng property nào? Nó có giải quyết DB connection limits không?
19. Nếu one response record là 5MB, concurrency 2 bảo vệ memory thế nào và chưa bảo vệ ở đâu?
20. Thêm test tạo 20 requests đồng thời, xác minh `activeNow() ≤ 3` và overload response phù hợp; tránh phụ thuộc wall clock.
21. Thiết kế streaming endpoint qua proxy NGINX có buffering; vì sao `curl -N` trên origin chưa chắc mô tả browser UX thật?
22. Chọn giữa WebClient reactive, boundedElastic-wrapped RestTemplate, R2DBC và background job cho ba kiểu workload: lấy dữ liệu nhanh, báo cáo dài, import nhiều GB.
23. Nếu downstream chậm 5 giây nhưng WebFlux timeout 500ms, workers/DB connections có thể còn bị giữ bao lâu?
24. Nếu log chứa `ThreadLocal` traceId ở handler nhưng mất ở boundedElastic worker, cần Reactor Context/tracing integration như thế nào?
25. Làm sao tạo custom dedicated scheduler metrics không làm lộ user IDs vào tags?
26. Vì sao `onBackpressureBuffer()` unbounded không giải quyết blocking pool saturation?

## 23. Tài liệu chính thức và hướng đọc

- [Project Reactor 3.7 — Threading and Schedulers](https://docs.spring.io/projectreactor/reactor-core/docs/3.7.x/reference/html/coreFeatures/schedulers.html): khác biệt scheduler, `publishOn`/`subscribeOn`, boundedElastic threads/queues và virtual threads.
- [Project Reactor 3.7 — FAQ: Wrap a synchronous blocking call](https://docs.spring.io/projectreactor/reactor-core/docs/3.7.x/reference/html/faq.html): `Mono.fromCallable(...).subscribeOn(Schedulers.boundedElastic())`.
- [Project Reactor 3.7 — Schedulers Javadoc](https://projectreactor.io/docs/core/3.7.8/api/reactor/core/scheduler/Schedulers.html): `newBoundedElastic`, thread/queue caps, global defaults, virtual threads property.
- [Project Reactor 3.7 — Flux Javadoc](https://projectreactor.io/docs/core/3.7.8/api/reactor/core/publisher/Flux.html): `flatMap`, `flatMapSequential`, `concatMap`, concurrency/prefetch.
- [Project Reactor 3.7 — Mono Javadoc](https://projectreactor.io/docs/core/3.7.8/api/reactor/core/publisher/Mono.html): `fromCallable`, `fromRunnable`, `subscribeOn`, `timeout` và cancellation.
- [Spring Framework 6.2 — WebFlux Reactive Core](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/reactive-spring.html): non-blocking I/O, event loops, backpressure, reactive streams.
- [Spring Framework 6.2 — WebFlux Functional Endpoints](https://docs.spring.io/spring-framework/reference/6.2/web/webflux-functional.html): RouterFunction, HandlerFunction, ServerResponse.body/NDJSON.
- [Spring Framework 6.2 — WebFlux HTTP Streaming](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller/ann-methods/responsebody.html): reactive streaming media types, codecs và flush.
- [Spring Framework — WebTestClient](https://docs.spring.io/spring-framework/reference/testing/webtestclient.html): HTTP tests cho streaming và reactive response bodies.
- [Spring Boot 3.5 — Reactive Web Applications](https://docs.spring.io/spring-boot/3.5/reference/web/reactive.html): WebFlux/embedded Netty setup.
- [Reactive Streams JVM Specification](https://www.reactive-streams.org/): request(n), cancellation và publisher/subscriber contract.
