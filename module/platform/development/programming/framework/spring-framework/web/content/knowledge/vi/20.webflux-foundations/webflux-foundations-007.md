# Spring WebFlux — Lỗi, hủy đăng ký, timeout và giải phóng tài nguyên

## 1. Mục tiêu và bối cảnh

Spring WebFlux dựa trên Reactive Streams và Reactor (`Mono`/`Flux`). Trong ứng dụng reactive, một HTTP request không nhất thiết đồng nghĩa một Servlet thread đang chờ đến khi controller return. Một request có thể là một **chuỗi tín hiệu bất đồng bộ** được subscription kích hoạt, xử lý qua operators rồi kết thúc bằng complete, error hoặc cancellation.

Tình huống thực tế:

- Client gọi API phụ thuộc upstream chậm, sau 2 giây cần timeout và trả thông báo an toàn.
- Browser mở Server-Sent Events (SSE), sau đó đóng tab: ứng dụng phải giải phóng subscription, tài nguyên stream và giảm số active connections.
- WebClient đã nhận response HTTP nhưng code không đọc body: pooled connection/DataBuffer có thể không được giải phóng nếu dùng API thấp không đúng cách.
- Service dùng resource bất đồng bộ (connection, session, cursor) và bị hủy giữa stream: cleanup phải chạy cả khi cancel, chứ không chỉ khi complete.
- Stream đã gửi status 200 cùng một số bytes rồi mới lỗi: HTTP response đã committed, không thể “đổi sang 500 JSON” trên cùng response.

Sau bài học, bạn có thể:

1. Phân biệt `onNext`, `onComplete`, `onError` và `cancel()` theo Reactive Streams; hiểu vì sao **cancel không phải onError**.
2. Sử dụng `onErrorResume`, `onErrorMap`, `onErrorReturn`, `doOnError`, `doFinally`, `doOnCancel` và `retryWhen` có kiểm soát.
3. Phân biệt `timeout(Duration)` của Reactor, network timeouts ở Reactor Netty/WebClient và gateway/client timeouts.
4. Dùng `Flux.using`/`Mono.using` cho resource synchronous, `usingWhen` cho asynchronous resource cleanup trên **complete/error/cancel**.
5. Biết khi nào phải release pooled `DataBuffer` và response body, đặc biệt khi tự làm việc với streaming/raw buffers.
6. Dùng WebFlux `@RestControllerAdvice`, `ProblemDetail`, `ResponseStatusException` và `WebExceptionHandler` đúng lớp, không lộ stacktrace cho client.
7. Thiết kế streaming SSE/WebClient resource lifecycle, backpressure, cancellation propagation, retry idempotency và observability.
8. Chạy demo **Java 17 / Spring Boot 3.5.0 / Spring Framework 6.2**, kiểm thử `WebTestClient` và `StepVerifier`.

**Phạm vi:** Spring WebFlux reactive stack. Spring MVC dùng Servlet async `SseEmitter`/`DeferredResult` và có lifecycle khác. Không dùng MVC `ResponseBodyEmitter` hoặc `AsyncRequestNotUsableException` như giải pháp chính cho WebFlux.

## 2. Reactive Streams: ba tín hiệu kết thúc và một hành động hủy

Một `Publisher<T>` có thể phát:

~~~text
onSubscribe(Subscription)
      |
      +-- request(n) -------------------------+
      |                                       |
      v                                       v
onNext(value) ... onNext(value) ...    onComplete()
      |                                       ^
      +-------------------------------> onError(error)
      |
      +-- cancel() [subscriber -> upstream]
~~~

Đồ thị trên mô tả các khả năng, không phải một chuỗi mà terminal signals cùng xuất hiện: theo protocol, sau **onComplete hoặc onError**, publisher không được tiếp tục phát onNext/terminal khác.

- `onNext(T)`: dữ liệu, có thể bằng 0 hoặc nhiều lần với `Flux`, tối đa một lần với `Mono`.
- `onComplete()`: kết thúc thành công, không còn dữ liệu.
- `onError(Throwable)`: kết thúc có lỗi, không tiếp tục onNext bình thường trong publisher đó.
- `Subscription.cancel()`: tín hiệu **từ downstream/subscriber lên upstream** để thông báo không cần dữ liệu nữa; **không phải onError** và không nhất thiết dẫn tới onComplete cho subscriber đã hủy.

**Hủy không đồng nghĩa lỗi.** Ví dụ `take(1)` chủ động cancel upstream sau khi nhận đủ một phần tử; đó là kết thúc đúng kỳ vọng, không phải lỗi hệ thống.

### 2.1. Tại sao phải hiểu cancel?

Nếu bạn chỉ có:

~~~java
.doOnError(error -> releaseResource())
~~~

thì resource có thể bị giữ khi browser đóng kết nối hoặc consumer gọi `take(1)` và cancel. Nếu chỉ dùng:

~~~java
.doOnComplete(() -> releaseResource())
~~~

thì cleanup cũng không chạy trên error hay cancel.

Phù hợp hơn khi chỉ cần side effect quan sát terminal:

~~~java
.doFinally(signal -> recordTermination(signal))
~~~

`SignalType` nhận giá trị như `ON_COMPLETE`, `ON_ERROR`, `CANCEL` tùy lifecycle. `doFinally` chạy khi sequence kết thúc vì bất kỳ nguyên nhân terminal/cancel theo Reactor semantics. Callback cần **không blocking** và xử lý thread-safety.

Đối với resource sở hữu cụ thể, ưu tiên **scope resource** bằng `using`/`usingWhen` thay vì chỉ ghép những callbacks thủ công.

### 2.2. Cold và hot publisher

| Loại | Ví dụ | Hệ quả khi cancel |
| --- | --- | --- |
| Cold | `Mono.fromCallable(...)`, repository reactive query | Subscription thường khởi phát riêng hoạt động; cancel request hủy upstream ở mức publisher |
| Hot/shared | Shared `Sinks.Many`, Kafka consumer dùng chung, `publish().refCount()` | Cancel một subscriber không nhất thiết dừng producer chung |
| Finite | `Flux.range(1, 10)` | Có thể complete rất nhanh trước khi quan sát cancel |
| Infinite | `Flux.interval(...)`, SSE/live updates | Phải quản lý cancellation, backpressure, request lifetime |

Một subscription bị cancel **không đảm bảo** toàn bộ công việc ngoài hệ thống đã dừng. Ví dụ một JDBC driver blocking, một HTTP request đã gửi tới upstream hoặc một job bên thứ ba có thể vẫn đang làm việc. Reactive cancellation là **cooperative/best-effort** tùy nguồn dữ liệu và adapter.

## 3. Operators xử lý lỗi: chọn đúng ngữ nghĩa

Trong Reactor, error là **terminal signal**. Các recovery operators không “quay lại chạy tiếp các phần tử còn lại của nguồn cũ”; thường chúng thay thế phần thất bại bằng một publisher/fallback mới.

### 3.1. Bảng lựa chọn

| Operator | Ý nghĩa | Khi dùng |
| --- | --- | --- |
| `doOnError(consumer)` | Side effect khi nhìn thấy lỗi; **không nuốt lỗi** | Logging/metrics/tracing |
| `onErrorReturn(value)` | Trả một giá trị fallback, rồi hoàn thành | Default rõ và an toàn |
| `onErrorResume(function)` | Chuyển sang publisher fallback | Cache fallback, dự phòng có chính sách |
| `onErrorMap(function)` | Đổi loại exception, vẫn là error | Mapping domain/transport exception |
| `onErrorComplete()` | Biến lỗi thành complete rỗng | Chỉ khi bỏ qua lỗi có chủ đích |
| `retryWhen(Retry...)` | Subscribe lại **nguồn** theo policy | Tạm lỗi, có idempotency và giới hạn |
| `doFinally(consumer)` | Quan sát complete/error/cancel | Metrics và terminal cleanup side effects |
| `doOnCancel(action)` | Chạy khi cancel | Dừng producer riêng hoặc ghi metric cancellation |
| `onErrorContinue(...)` | Tiếp tục xử lý một số phần tử theo semantics operator | Tránh làm giải pháp mặc định do scope/hành vi phức tạp |

### 3.2. doOnError không sửa lỗi

~~~java
Mono<Item> mono = service.load(id)
        .doOnError(error -> log.warn(
                "item_lookup_failed id={} kind={}",
                id, error.getClass().getSimpleName()));
~~~

Nếu upstream phát error, subscriber vẫn nhận error trừ khi phía dưới có operator phục hồi.

Không dùng `doOnError` làm nơi duy nhất quản lý resource cancellation. Và không log raw exception message cho mọi lỗi nghiệp vụ nếu message có SQL/password/PII.

### 3.3. onErrorResume có điều kiện

~~~java
Mono<Product> result = remoteCatalog.find(id)
        .onErrorResume(RemoteServiceUnavailable.class,
                ex -> cachedCatalog.find(id));
~~~

Đây là fragment: cần service/types của ứng dụng. Chỉ fallback cho loại lỗi có thể phục hồi. Đừng biến lỗi truy cập 403, validation 400 hoặc bug NullPointerException thành dữ liệu cache như thể đó là một success.

### 3.4. onErrorMap giữ nguyên ý nghĩa lỗi

~~~java
return upstream.fetch(id)
        .onErrorMap(TimeoutException.class,
                ex -> new CatalogTimeoutException(ex));
~~~

Mapping lỗi low-level thành domain-level giúp tầng WebFlux trả status ổn định. Bản demo phía dưới cũng map `TimeoutException` thành `ApiTimeoutException` rồi trả HTTP 504.

### 3.5. onErrorComplete có thể che lỗi

~~~java
Flux<AuditEvent> events = auditRepository.read()
        .onErrorComplete();
~~~

Nếu audit là dữ liệu quan trọng, việc biến lỗi thành complete có thể che mất mất mát dữ liệu. Chỉ dùng cho các hoạt động **tùy chọn**, đã có metrics và contract “best effort”.

### 3.6. onErrorResume sau timeout

~~~java
Mono<Item> result = remote.fetch(id)
        .timeout(Duration.ofMillis(500))
        .onErrorResume(TimeoutException.class,
                ex -> cache.find(id));
~~~

Ở đây operator timeout có thể phát `TimeoutException` xuống dưới và cancel upstream. Nếu cache fallback trả kết quả, downstream nhận success. Quan trọng: **đừng trả dữ liệu lỗi thời khi hợp đồng API đòi tính nhất quán tuyệt đối**.

## 4. Cancellation và hooks trong Reactor

### 4.1. doOnCancel so với doFinally

~~~java
Flux<Long> source = Flux.interval(Duration.ofSeconds(1))
        .doOnCancel(() -> metrics.incrementCancelled())
        .doFinally(signal -> metrics.incrementFinished(signal));
~~~

Đoạn trên minh họa với biến `metrics` tự định nghĩa. `doOnCancel` chỉ chạy khi cancellation; `doFinally` bao gồm cancel, complete và error.

Cần hiểu **operator placement**. Đặt `doFinally` **trước** `timeout` có thể quan sát CANCEL khi timeout hủy upstream; đặt **sau** `timeout` có thể quan sát ON_ERROR khi downstream nhận TimeoutException.

~~~java
Mono<String> result = remote()
        .doFinally(signal -> log.info("upstream={}", signal))
        .timeout(Duration.ofSeconds(2))
        .doFinally(signal -> log.info("downstream={}", signal));
~~~

Trong trường hợp `remote()` chưa kịp phát và timeout xảy ra, thường:

~~~text
upstream=CANCEL
downstream=ON_ERROR
~~~

Thứ tự log có thể không giống thứ tự dòng minh họa do propagation và scheduling; hãy test với `StepVerifier`. Đây là phân biệt quan trọng khi đặt metrics và không được đếm cả CANCEL+ERROR thành hai HTTP requests thất bại.

### 4.2. take(n) chủ động hủy nguồn

~~~java
Flux<Integer> firstTwo = Flux.range(1, 1_000_000)
        .doFinally(signal -> log.info("source={}", signal))
        .take(2);
~~~

Khi downstream đã nhận hai phần tử và complete, operator `take(2)` có thể cancel nguồn phía trước (trừ khi nguồn đã terminal trước). Source-side `doFinally` vì vậy có thể nhận `CANCEL`; subscriber-side thấy `ON_COMPLETE`. Đây là hành vi hợp lệ, không phải lỗi dữ liệu.

### 4.3. Cancellation do client disconnect

Trong WebFlux, khi connection/response consumer bị hủy, subscription phản hồi thường nhận cancel. Nhưng:

- Không có cam kết người dùng đóng tab sẽ được server nhận biết **ngay lập tức** trong mọi topology.
- Dữ liệu có thể bị buffer bởi socket, Netty hoặc reverse proxy.
- Nếu publisher là hot source dùng chung, hủy một subscription không tự đóng nguồn toàn cục.
- Nếu gọi thư viện blocking từ source, cancel có thể không dừng operation ngay.

Do đó, thiết kế cleanup theo **subscription lifecycle** và bảo vệ per-client resource scopes, không chỉ trông chờ exception “broken pipe”.

### 4.4. Không gọi subscribe() tùy tiện trong controller

Sai về ownership:

~~~java
@GetMapping("/start")
Mono<String> start() {
    remoteJob().subscribe(value -> log.info("job={}", value));
    return Mono.just("started");
}
~~~

Với cách này, subscription được tạo **ngoài lifecycle response**; client cancel không được truyền tự nhiên vào job ấy và errors có thể bị mất. Nếu đó là tác vụ phải sống lâu bất kể request, hãy dùng service/job queue được quản lý rõ. Nếu kết quả thuộc request, **return publisher** cho WebFlux subscribe/cancel.

Tương tự, tránh `block()` hoặc `Thread.sleep()` trên Netty event-loop; làm vậy giảm khả năng phục vụ nhiều requests. Với legacy blocking calls, dùng `Schedulers.boundedElastic()` có kiểm soát, ưu tiên native reactive drivers.

## 5. Timeout: Reactor operator, network, server và gateway

### 5.1. Reactor timeout

~~~java
Mono<String> response = remoteCall()
        .timeout(Duration.ofSeconds(2));
~~~

Nếu nguồn không phát tín hiệu theo yêu cầu trước deadline, Reactor phát `TimeoutException`, hủy subscription upstream và kết thúc downstream bằng error.

Biến thể fallback:

~~~java
Mono<String> response = remoteCall()
        .timeout(Duration.ofSeconds(2), Mono.just("cached"));
~~~

Downstream nhận fallback nếu timeout. Tuy nhiên operation remote ngoài hệ thống có thể vẫn chạy dù local Publisher đã nhận cancel; cancellation không thể “undo” một HTTP/SQL write đã thực thi.

### 5.2. Timeout vs deadline

Nếu API request trải qua A → B → C, mỗi tầng dùng timeout 2 giây riêng có thể dẫn tới tổng vượt SLA của client. Với deadline end-to-end, cần truyền remaining budget, cancel downstream khi hết hạn và đo thời gian từ request bắt đầu. Reactor `timeout` là operator-level policy, không tự tạo distributed deadline protocol.

### 5.3. Những loại timeout khác nhau

| Timeout | Tầng | Khi nào |
| --- | --- | --- |
| Reactor `timeout(Duration)` | Chuỗi Publisher | Bảo vệ logic và thời gian chờ tín hiệu |
| HTTP client response timeout | Reactor Netty HttpClient/WebClient | Chờ response read phù hợp với transport |
| Connect timeout | TCP/socket client | Mất quá lâu khi thiết lập kết nối |
| Read/write timeout | Network handlers | Socket không có tiến triển I/O |
| Server idle/request timeout | Netty/server config | Giới hạn connection/request tùy setup |
| Gateway/ingress timeout | Nginx/Envoy/CDN | Proxy tự đóng upstream/downstream |
| Caller/client deadline | Browser/mobile/other service | Caller ngừng chờ, có thể cancel |

Một request có thể bị client cancel **trước** timeout của server. Hoặc gateway timeout trước khi Reactor timeout và client chỉ thấy 504 do gateway tạo. Phải quan sát hai phía, không suy mọi `TimeoutException` có một nguyên nhân duy nhất.

### 5.4. Timeout của WebClient

Một fragment dùng Reactor Netty:

~~~java
HttpClient nettyClient = HttpClient.create()
        .responseTimeout(Duration.ofSeconds(3));

WebClient client = WebClient.builder()
        .clientConnector(new ReactorClientHttpConnector(nettyClient))
        .build();
~~~

Imports: `reactor.netty.http.client.HttpClient`, `org.springframework.http.client.reactive.ReactorClientHttpConnector`, `org.springframework.web.reactive.function.client.WebClient`. Đây là fragment cấu hình, không phải application đầy đủ. Connect timeout cần cấu hình channel option riêng nếu cần; không nhầm `responseTimeout` với tổng deadline toàn pipeline sau decoding/business processing.

### 5.5. Timeout và cleanup

Khi timeout hủy upstream Publisher, resource cleanup phụ thuộc source có hỗ trợ cancellation hay không. Với một resource bất đồng bộ, dùng `usingWhen(..., asyncCancel)` để thực hiện release khi cancel. Không chỉ dùng `doOnError` vì upstream có thể nhìn thấy `CANCEL` chứ không phải `ON_ERROR`.

## 6. Giải phóng resource bằng using và usingWhen

### 6.1. Flux.using — resource synchronous

Ví dụ tạo một `Lease` tăng active count khi subscribe và giảm khi complete/error/cancel:

~~~java
Flux<String> events = Flux.using(
        () -> new Lease(),
        lease -> Flux.interval(Duration.ofSeconds(1))
                .map(n -> "tick-" + n),
        Lease::close
);
~~~

`Lease` cần cài đặt `close()`; đây là fragment. Resource supplier chạy **khi subscribe** chứ không phải ngay lúc assembly. `Flux.using` đảm nhiệm cleanup đúng lifecycle của publisher.

So với tạo lease ngoài publisher:

~~~java
Lease lease = new Lease();
Flux<String> events = Flux.interval(Duration.ofSeconds(1))
        .doFinally(signal -> lease.close());
~~~

cách thứ hai tạo resource **ngay khi method được gọi**. Nếu publisher không được subscribe, lease có thể rò. `using` scope resource theo subscription đúng hơn.

### 6.2. Mono.using

Với tài nguyên có close đồng bộ:

~~~java
Mono<String> result = Mono.using(
        () -> new LocalHandle(),
        handle -> Mono.fromSupplier(handle::read),
        LocalHandle::close
);
~~~

Fragment này giả định `LocalHandle` có `read()` và `close()` không ném checked exception hoặc được xử lý đúng. Nếu read là blocking I/O, bản thân `Mono.fromSupplier` **không tự biến nó thành non-blocking**. Cần offload phù hợp hoặc dùng API reactive.

### 6.3. usingWhen — asynchronous resource

Với R2DBC transaction, reactive session hoặc resource cần close publisher:

~~~java
Mono<Result> result = Mono.usingWhen(
        connectionFactory.create(),
        connection -> executeQuery(connection),
        connection -> connection.close(),
        (connection, error) -> connection.close(),
        connection -> connection.close()
);
~~~

Đây là fragment tổng quát, trong đó `executeQuery(connection)` trả publisher phù hợp và `Result` do ứng dụng định nghĩa. Các cleanup functions lần lượt là:

1. **asyncComplete:** release khi source hoàn thành thành công.
2. **asyncError:** release khi source error (có cả Throwable).
3. **asyncCancel:** release khi subscription bị cancel.

Nếu resource close cũng có thể error, cần xác định cách xử lý lỗi cleanup. Đừng coi close error là “không quan trọng” nếu nó khiến pool cạn kiệt; log/metrics và recovery policy phải rõ, đồng thời tránh tiết lộ secrets.

### 6.4. Sự khác nhau giữa doFinally và usingWhen

- `doFinally`: side-effect callback đồng bộ, hữu ích cho logs/metrics/small release action.
- `using`: resource lifecycle có cleanup đồng bộ, thiết kế theo subscriber.
- `usingWhen`: cleanup **reactive/asynchronous**, có thể theo dõi Publisher đóng resource, phân nhánh complete/error/cancel.
- `doOnCancel`: bổ sung tín hiệu hủy, không đủ để giải phóng resource trên success/error.

Nếu cleanup là một network operation bất đồng bộ, một `doFinally(() -> resource.close().subscribe())` là **anti-pattern** phổ biến: bạn tự tạo fire-and-forget subscription, lỗi close không được gắn với lifecycle và khó test. Dùng `usingWhen` hoặc transactional reactive API.

### 6.5. Cleanup đúng một lần

Ở một pipeline, operator `using`/`usingWhen` quản lý resource theo subscription. Tuy nhiên nếu tài nguyên còn được chia sẻ bởi external callback, scheduler hay shutdown hook, bản thân chúng vẫn có thể gọi close cạnh tranh. Dùng state guard (ví dụ `AtomicBoolean.compareAndSet(false,true)`) nếu close không idempotent.

Đừng double-close bằng cách vừa `Flux.using(..., Lease::close)` vừa thêm `doFinally(sig -> lease.close())` không được bảo vệ, và đừng giữ một global singleton resource trong using rồi đóng nó mỗi subscriber nếu resource đó dùng chung toàn ứng dụng.

## 7. Backpressure, discard và pooled DataBuffer

### 7.1. Backpressure là phần của lifecycle

Reactive Streams cho phép subscriber yêu cầu số lượng phần tử `request(n)`. Nếu client chậm hoặc subscriber cancel, những phần tử đã được buffer/prefetch có thể bị discard. Các operators như `flatMap`, `publishOn`, `buffer`, `onBackpressureBuffer` có semantics và chi phí lưu trữ khác nhau.

Một `Flux.interval` nếu downstream không yêu cầu đủ có thể phát lỗi overflow thay vì tự chờ vô hạn. Không coi interval làm nguồn backpressure-safe cho mọi tải.

Chọn chính sách:

- Bounded queues, giới hạn per client.
- `onBackpressureLatest()` hoặc sample/throttle khi bài toán chỉ cần “giá trị mới nhất”.
- `limitRate`/prefetch tuning khi phù hợp.
- Durable storage/replay nếu mọi event cần được bảo toàn.
- Cancellation propagation tới producer thật, không chỉ dừng phần encode response.

### 7.2. DataBuffer có thể giữ pooled native memory

Trong Spring WebFlux, `DataBuffer` abstraction có implementations dùng pooled/reference-counted buffers như Netty `ByteBuf`. Khi ứng dụng tự giữ, cắt, bỏ hoặc chuyển buffers ngoài contract của codec, bạn có thể phải **release** những buffers mình sở hữu.

Ví dụ:

~~~java
DataBufferUtils.release(buffer);
~~~

Không áp dụng mù quáng khi framework vẫn sở hữu buffer và sẽ tự release; double release có thể gây lỗi. Chỉ release khi lifecycle ownership rõ.

### 7.3. DoOnDiscard với buffered elements

Một số operators có thể discard phần tử khi cancel/filter/overflow. Nếu ứng dụng đang xử lý pooled DataBuffer do mình sở hữu:

~~~java
Flux<DataBuffer> data = source
        .filter(this::shouldKeep)
        .doOnDiscard(DataBuffer.class, DataBufferUtils::release);
~~~

Đây là fragment: `source` là Flux<DataBuffer>, `shouldKeep` do ứng dụng định nghĩa; sự đúng đắn phụ thuộc operator placement và ownership. `doOnDiscard` chỉ giúp ở những operators hỗ trợ discard hooks, **không giải quyết tất cả đường rò bộ nhớ**. Đọc Javadoc từng operator và lập kế hoạch release cho retry, split, cancel, buffer/error paths.

### 7.4. Không tự decode DataBuffer bằng cách giữ raw ByteBuf vô hạn

Nếu có thể, dùng `bodyToMono(Dto.class)`, `bodyToFlux(Dto.class)`, codecs hoặc `DataBufferUtils.write/read` với lifecycle rõ. Chỉ thao tác raw DataBuffer khi thực sự cần streaming binary/protocol và đã có tests memory/resource cleanup.

Một `OutOfMemoryError: Direct buffer memory` có thể đến từ buffer leaks, backpressure không phù hợp, request body quá lớn hoặc network pipeline không được giới hạn. Đừng kết luận một nguyên nhân khi chưa có metrics/profiling.

## 8. WebClient: tiêu thụ và release HTTP response body

### 8.1. retrieve thường là điểm bắt đầu tốt

~~~java
Mono<ProductDto> product = webClient.get()
        .uri("/products/{id}", id)
        .retrieve()
        .bodyToMono(ProductDto.class);
~~~

Mặc định `retrieve()` biến 4xx/5xx thành `WebClientResponseException` theo WebClient semantics (trừ khi bạn tùy chỉnh). Với DTO decoding, framework quản lý phần lớn lifecycle của response body.

Đừng gọi `block()` trên WebFlux event loop; return `Mono<ProductDto>` hoặc compose tiếp.

### 8.2. exchangeToMono/exchangeToFlux

Cần điều khiển status theo response:

~~~java
Mono<ProductDto> product = webClient.get()
        .uri("/products/{id}", id)
        .exchangeToMono(response -> {
            if (response.statusCode().is2xxSuccessful()) {
                return response.bodyToMono(ProductDto.class);
            }
            if (response.statusCode().value() == 404) {
                return Mono.empty();
            }
            return response.createError();
        });
~~~

Theo tài liệu Spring Framework 6.2, sau khi Publisher mà `exchangeToMono`/`exchangeToFlux` trả về hoàn tất, response body **nếu chưa được tiêu thụ** sẽ được framework kiểm tra/release, giúp tránh leaks. Trong fragment trên, status 404 bỏ qua body có chủ đích; method `exchangeToMono` hỗ trợ release phần còn lại theo contract.

**Không decode body ở downstream sau khi exchangeToMono callback đã kết thúc**: body có thể đã được release. Nếu cần error content, hãy decode nó **bên trong response function**.

### 8.3. Tại sao exchange() cũ nguy hiểm?

API thấp `exchange()` đã bị deprecate vì code dễ quên tiêu thụ/release body ở một nhánh, khiến connection/memory leak. Tránh viết:

~~~java
// Anti-pattern với API exchange() legacy:
return webClient.get().uri("/resource")
        .exchange()
        .flatMap(response -> {
            if (response.statusCode().is2xxSuccessful()) {
                return Mono.just("ok"); // Bỏ body chưa xử lý!
            }
            return Mono.just("error");
        });
~~~

Ưu tiên `retrieve()` hoặc `exchangeToMono`/`exchangeToFlux`. Nếu dùng `ClientResponse` thủ công ở API thấp hơn, phải hiểu `bodyToMono`/`bodyToFlux`, `releaseBody()` và decoding pathways.

### 8.4. Timeout và WebClient errors

Các nguồn lỗi khác nhau:

| Lỗi | Gợi ý kiểm |
| --- | --- |
| DNS/connect failure | Host, proxy, connect timeout, network |
| HTTP 404/429/500/503 | WebClientResponseException/status policy |
| Reactor timeout | Operator timeout và cancellation propagation |
| Response decode error | Content-Type/body shape/max-in-memory-size |
| Client cancel | Downstream không cần response; không nhất thiết onError |
| Pool exhaustion | Connection leak, pool size, slow upstream, unconsumed body |
| OutOfMemoryError/DirectMemory | Pooled buffer ownership, unbounded buffering |

Đừng biến tất cả thành HTTP 500 "unknown" không phân loại. Cũng không đưa raw upstream URL với query tokens và response body chứa secrets vào public error payload.

## 9. HTTP exception handling trong WebFlux

### 9.1. Controller-level và global advice

WebFlux hỗ trợ `@ExceptionHandler` tại controller hoặc `@RestControllerAdvice`. Với HTTP APIs, dùng `ProblemDetail`/`ErrorResponse` để chuẩn hóa lỗi.

Ví dụ fragment:

~~~java
@RestControllerAdvice
class ApiErrorHandler {
    @ExceptionHandler(UpstreamTimeoutException.class)
    ResponseEntity<ProblemDetail> timeout(
            UpstreamTimeoutException ex) {
        ProblemDetail body = ProblemDetail.forStatusAndDetail(
                HttpStatus.GATEWAY_TIMEOUT,
                "Upstream service did not respond in time");
        body.setTitle("Gateway timeout");
        body.setProperty("code", "UPSTREAM_TIMEOUT");
        return ResponseEntity.status(HttpStatus.GATEWAY_TIMEOUT)
                .body(body);
    }
}
~~~

Đây là fragment; class exception/imports và application config phải tồn tại. `ProblemDetail` cung cấp HTTP status/title/detail/type/instance; extension properties có thể được serialize cùng JSON theo hỗ trợ Spring/Jackson.

### 9.2. WebExceptionHandler là lớp thấp hơn

`WebExceptionHandler` thuộc WebFlux processing chain, xử lý exceptions từ `WebFilter`/target `WebHandler`. Với API controller thông thường, ưu tiên `@RestControllerAdvice` và WebFlux default exception handling trước khi tự cài handler cấp thấp.

Một `WebExceptionHandler` tùy chỉnh có thể tạo thứ tự xử lý phức tạp và rủi ro khi response đã committed. Nếu đã committed, không thể tự reset status/headers như chưa có bytes nào được gửi.

### 9.3. 400/404/409/429/503/504/500

Đừng map mọi lỗi reactive thành 500. Một gợi ý:

| Điều kiện | HTTP status thường phù hợp | Lưu ý |
| --- | --- | --- |
| Request input sai | 400 | Validation, unsupported/missing parameters |
| Resource không tồn tại | 404 | Không lộ sự tồn tại tài nguyên forbidden |
| Business conflict/version mismatch | 409 hoặc 412 | Tùy contract |
| Rate limit | 429 | Có thể kèm Retry-After nếu phù hợp |
| Service tạm ngừng/overload | 503 | Có thể kèm retry policy |
| Gateway/upstream timeout | 504 | Khi ứng dụng đóng vai gateway tới upstream |
| Internal bug không xác định | 500 | Generic message, log correlation ID nội bộ |
| Subscriber cancel/client disconnected | **Không phải một HTTP status tự phát** | Không giả vờ đã trả 499/500 nếu client đã rời đi |

Một app gọi remote dependency mà timeout không nhất thiết luôn có status 504; đó là lựa chọn API contract. Cần phân biệt upstream timeout với **client** ngừng chờ. Lưu ý `499` trong logs Nginx là mã riêng proxy, không phải HTTP status chuẩn để WebFlux “trả sau cancel”.

### 9.4. Không lộ thông tin nhạy cảm

Error payload **không** bao gồm:

- Stack trace, class/method names nội bộ.
- Database URL, SQL, credentials, tokens, cookies.
- Raw upstream error body có thể chứa PII hoặc secret.
- File system paths, hostnames nội bộ, provider access keys.
- Arbitrary exception message có input người dùng không được sanitize.

Dùng mã lỗi ổn định và request/trace ID trong logs. Nếu client cần mã đối chiếu, expose một header được server tạo và hỗ trợ CORS nếu cross-origin. Không tin unvalidated request correlation ID để xây log fields vô hạn.

### 9.5. Khi HTTP response đã committed

Trong streaming SSE hoặc response body chunked:

~~~text
HTTP/1.1 200 OK
Content-Type: text/event-stream

event: update
data: {"progress":20}
~~~

nếu publisher gặp error sau khi headers/body bắt đầu, application **không thể đổi 200 thành 500 JSON** trong cùng HTTP response. Error handler chỉ có thể thay status nếu response chưa committed. Khi stream đã bắt đầu:

- Nếu kênh còn usable, có thể map business failure thành **SSE application error event** ngay trong stream protocol.
- Nếu transport/write đã lỗi, chỉ stop/cancel/release resources, log/metrics; không cố write một HTTP response thứ hai.
- Error publisher trong streaming không tự trở thành JSON ProblemDetail sau commit; connection có thể bị đóng và client xử lý reconnect/error.

## 10. Retry đúng cách và hủy subscription

### 10.1. retryWhen chỉ cho transient error

~~~java
return webClient.get()
        .uri("/catalog/{id}", id)
        .retrieve()
        .bodyToMono(CatalogDto.class)
        .retryWhen(Retry.backoff(2, Duration.ofMillis(100))
                .filter(this::isTransientFailure));
~~~

Fragment với `isTransientFailure` do ứng dụng định nghĩa. `retryWhen` **resubscribe** nguồn. Nếu nguồn có side effect như POST payment, retry có thể tạo giao dịch trùng nếu không có idempotency key/transaction deduplication.

Không retry:

- 400 validation error.
- 401/403 không có logic refresh token đã được thiết kế.
- 404 khi resource thật sự không tồn tại.
- Business conflict không thể tự sửa.
- Non-idempotent commands không có idempotency safeguards.

Có thể retry một số network resets/429/503 sau khi xét rate limit, jitter, caps và retry budget. Backoff tránh retry storm khi upstream đang quá tải.

### 10.2. Retry và timeout order

Hai cách sau **khác nhau**:

~~~java
remoteCall()
    .timeout(Duration.ofSeconds(1))
    .retryWhen(Retry.max(2));
~~~

Mỗi subscription attempt có timeout 1 giây. Trong khi:

~~~java
remoteCall()
    .retryWhen(Retry.max(2))
    .timeout(Duration.ofSeconds(1));
~~~

Một deadline 1 giây bao quanh cả sequence retries. Cần thiết kế **per-attempt timeout và overall budget** có chủ đích; không chỉ đổi thứ tự operators cho code “đẹp”.

### 10.3. Retry không phải tiếp tục nguồn cũ

Nếu một `Flux` đã phát 5 records rồi error, retry subscription có thể phát lại 5 records đó. Consumer phải hỗ trợ idempotency/deduplication hoặc dùng checkpoint/cursor để resume. Đặc biệt nguy hiểm với transactional writes hoặc event-stream processing.

### 10.4. Hủy sau retry/backoff

Khi client cancel trong lúc chờ backoff, subscription quản lý bởi Reactor sẽ dừng việc phát thêm kết quả/retry scheduling theo semantics operator. Tuy nhiên không được giả định mọi side effect ngoài tiến trình đã được rollback. Với các tasks tự tạo ở service, phải tự gắn ownership/cancellation vào publisher lifecycle.

## 11. SSE và client disconnect trong WebFlux

Một WebFlux endpoint có thể trả:

~~~java
@GetMapping(path = "/events",
            produces = MediaType.TEXT_EVENT_STREAM_VALUE)
Flux<ServerSentEvent<String>> events() {
    return Flux.interval(Duration.ofSeconds(1))
            .map(n -> ServerSentEvent.<String>builder()
                    .id(Long.toString(n))
                    .event("tick")
                    .data("tick-" + n)
                    .build())
            .doFinally(signal -> log.info(
                    "sse_terminated signal={}", signal));
}
~~~

Đây là fragment có `log`, imports cần thiết. `Flux.interval` là nguồn phát theo scheduler; khi downstream cancel, subscription có thể dừng timer. Nếu browser closes SSE, WebFlux network handler thường propagates cancel, nhưng detection timing còn phụ thuộc network và proxy.

### 11.1. SSE heartbeat

SSE comment có thể dùng làm heartbeat:

~~~text
: keepalive

~~~

Trong Spring WebFlux, builder:

~~~java
ServerSentEvent.<String>builder()
        .comment("keepalive")
        .build();
~~~

Comment-only SSE thường không trigger application message event trong browser, nhưng tạo bytes giúp proxy không xem connection idle. Nếu gateway buffer response, heartbeat có thể không tới client kịp. Test thật qua proxy với buffering disabled nếu cần.

### 11.2. Last-Event-ID và replay

Browser EventSource có reconnect, và có thể gửi `Last-Event-ID` nếu stream dùng event ID. Muốn resume không mất events, server cần lưu durable event IDs/retention và đọc lại từ cursor. Nếu stream chỉ tạo `Flux.interval` in-memory, **không được hứa exactly-once delivery**. Reconnect có thể tạo subscription mới và mất/nhận lại events tùy thiết kế.

### 11.3. Hot publisher chia sẻ nhiều clients

Ví dụ dùng `Sinks.Many<T>` làm producer toàn ứng dụng. Khi client A cancel, không được tự đóng Sink làm client B mất dữ liệu. Dọn **per-client subscription** hoặc resource riêng; shared producer có lifecycle ứng dụng độc lập. Trên nguồn hot, need to distinguish subscriber cancellation vs producer shutdown.

## 12. Dự án chạy được: Spring Boot 3.5, Java 17

Demo tập trung vào:

- `GET /api/items/ok`: trả JSON bình thường.
- `GET /api/items/slow`: Mono chậm, Reactor timeout 150ms, map thành custom exception rồi trả ProblemDetail HTTP 504.
- `GET /api/items/missing`: trả HTTP 404 qua ResponseStatusException.
- `GET /api/items/boom`: lỗi internal được advice map thành 500 generic, không lộ exception message.
- `GET /api/events`: SSE streaming dùng `Flux.using` với per-subscription lease và `doFinally`, dọn cả complete/error/cancel.
- `GET /api/active`: demo chỉ đếm active SSE subscriptions.
- Tests dùng WebTestClient và StepVerifier để kiểm HTTP error body, timeout, cancel/cleanup, virtual time.

### 12.1. Cấu trúc

~~~text
webflux-lifecycle-demo/
├── pom.xml
└── src/
    ├── main/
    │   └── java/demo/WebFluxLifecycleApplication.java
    └── test/
        └── java/demo/WebFluxLifecycleTest.java
~~~

### 12.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>webflux-lifecycle-demo</artifactId>
    <version>1.0.0</version>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
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
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-test</artifactId>
            <scope>test</scope>
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

**Không thêm `spring-boot-starter-web` vào demo.** Nếu cả MVC và WebFlux starters tồn tại, Spring Boot thường chọn MVC application type mặc định, khiến bài kiểm thử reactive stack sai mục tiêu.

### 12.3. WebFluxLifecycleApplication.java

Lưu toàn bộ Java sau vào `src/main/java/demo/WebFluxLifecycleApplication.java`. Chỉ có một public top-level class, những class/records còn lại package-private. Demo không gọi dịch vụ ngoài Internet, chạy độc lập khi có dependencies Maven.

~~~java
package demo;

import java.time.Duration;
import java.util.concurrent.TimeoutException;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.stereotype.Service;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.server.ResponseStatusException;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@SpringBootApplication
public class WebFluxLifecycleApplication {
    public static void main(String[] args) {
        SpringApplication.run(WebFluxLifecycleApplication.class, args);
    }
}

record Item(String id, String title) {
}

class ApiTimeoutException extends RuntimeException {
    ApiTimeoutException(Throwable cause) {
        super("The dependency timed out", cause);
    }
}

@Service
class ItemService {
    Mono<Item> find(String id) {
        return Mono.defer(() -> {
            if ("missing".equals(id)) {
                return Mono.error(new ResponseStatusException(
                        HttpStatus.NOT_FOUND, "Item not found"));
            }
            if ("boom".equals(id)) {
                return Mono.error(new IllegalStateException(
                        "internal database password=secret"));
            }

            Mono<Item> source = "slow".equals(id)
                    ? Mono.delay(Duration.ofSeconds(3))
                            .map(n -> new Item(id, "Late"))
                    : Mono.just(new Item(id, "Ready"));

            return source
                    .timeout(Duration.ofMillis(150))
                    .onErrorMap(TimeoutException.class,
                            ApiTimeoutException::new);
        });
    }
}

@Service
class EventService {
    private static final Logger LOG =
            LoggerFactory.getLogger(EventService.class);

    private final AtomicInteger active = new AtomicInteger();

    Flux<ServerSentEvent<String>> events() {
        return Flux.using(
                () -> new Lease(active),
                lease -> Flux.interval(Duration.ofMillis(100))
                        .map(n -> ServerSentEvent.<String>builder()
                                .id(Long.toString(n))
                                .event("tick")
                                .data("tick-" + n)
                                .build()),
                Lease::close
        ).doFinally(signal ->
                LOG.info("sse_terminated reason={}", signal));
    }

    int activeConnections() {
        return active.get();
    }

    private static final class Lease implements AutoCloseable {
        private final AtomicInteger active;
        private final AtomicBoolean closed = new AtomicBoolean();

        Lease(AtomicInteger active) {
            this.active = active;
            active.incrementAndGet();
        }

        @Override
        public void close() {
            if (closed.compareAndSet(false, true)) {
                active.decrementAndGet();
            }
        }
    }
}

@RestController
class ApiController {
    private final ItemService items;
    private final EventService events;

    ApiController(ItemService items, EventService events) {
        this.items = items;
        this.events = events;
    }

    @GetMapping("/api/items/{id}")
    Mono<Item> item(@PathVariable String id) {
        return items.find(id);
    }

    @GetMapping(path = "/api/events",
            produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    Flux<ServerSentEvent<String>> stream() {
        return events.events();
    }

    @GetMapping("/api/active")
    Mono<Integer> active() {
        return Mono.fromSupplier(events::activeConnections);
    }
}

@RestControllerAdvice
class ApiErrors {
    @ExceptionHandler(ApiTimeoutException.class)
    ResponseEntity<ProblemDetail> timeout(ApiTimeoutException ex) {
        ProblemDetail body = ProblemDetail.forStatusAndDetail(
                HttpStatus.GATEWAY_TIMEOUT,
                "Upstream did not respond in time");
        body.setTitle("Gateway timeout");
        body.setProperty("code", "UPSTREAM_TIMEOUT");
        return ResponseEntity.status(HttpStatus.GATEWAY_TIMEOUT)
                .body(body);
    }

    @ExceptionHandler(IllegalStateException.class)
    ResponseEntity<ProblemDetail> internal(IllegalStateException ex) {
        // Không gửi ex.getMessage() cho người dùng.
        ProblemDetail body = ProblemDetail.forStatusAndDetail(
                HttpStatus.INTERNAL_SERVER_ERROR,
                "An unexpected error occurred");
        body.setTitle("Internal server error");
        body.setProperty("code", "INTERNAL_ERROR");
        return ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR)
                .body(body);
    }
}
~~~

### 12.4. Những chi tiết thiết kế quan trọng

1. `Mono.defer` chỉ tạo publisher theo từng subscription, không khởi động tác vụ ngay ở thời điểm assembly.
2. `slow` dùng một source phát sau 3 giây, nhưng `timeout(150ms)` phát error; `onErrorMap` chuyển sang exception rõ nghiệp vụ.
3. HTTP 504 là **policy cho tình huống demo khi API đóng vai upstream gateway**. Trong ứng dụng khác có thể chọn 503 hoặc lỗi phù hợp hơn.
4. `boom` chứa message nội bộ để chứng minh advice trả message chung, không xuất secret.
5. `events()` tạo `Lease` bằng `Flux.using` **khi subscribe**; cleanup chạy khi downstream complete/error/cancel.
6. `AtomicBoolean` trong Lease bảo vệ double-close nếu ownership mở rộng hoặc external callback gọi close thêm.
7. `Flux.interval` có nguồn vô hạn; browser disconnect/cancel sẽ dừng per-subscription timer theo Reactor semantics thông thường.
8. `doFinally` chỉ log reason; cleanup thật nằm trong `using` để bảo đảm resource ownership.
9. `activeConnections` không phải metric security-grade; endpoint demo phải được bảo vệ/loại bỏ trong production.
10. Demo không có auth/CSRF, không tích hợp upstream thật, không có streaming buffers; ưu tiên dạy đúng lifecycle trước.

### 12.5. Chạy

~~~bash
mvn spring-boot:run
~~~

Trong terminal khác:

~~~bash
curl -i http://localhost:8080/api/items/ok
~~~

Response tương đương:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{"id":"ok","title":"Ready"}
~~~

Thử timeout:

~~~bash
curl -i http://localhost:8080/api/items/slow
~~~

Status 504 và JSON ProblemDetail tương đương:

~~~json
{
  "type":"about:blank",
  "title":"Gateway timeout",
  "status":504,
  "detail":"Upstream did not respond in time",
  "code":"UPSTREAM_TIMEOUT"
}
~~~

Response thực tế có thể bổ sung `instance` và headers; JSON field order không cố định.

Thử lỗi nội bộ:

~~~bash
curl -i http://localhost:8080/api/items/boom
~~~

Kỳ vọng 500, body chung không có chuỗi `password=secret`. Thử `missing` nhận HTTP 404.

### 12.6. Mở SSE và hủy client

~~~bash
curl -N -i http://localhost:8080/api/events
~~~

Ví dụ đầu stream:

~~~text
id:0
event:tick
data:tick-0

id:1
event:tick
data:tick-1

~~~

SSE formatter thực tế có thể khác thứ tự fields. Ở terminal khác:

~~~bash
curl -s http://localhost:8080/api/active
~~~

Nếu có một subscription, JSON có thể là:

~~~json
1
~~~

Sau Ctrl+C ở curl, cancel có thể lan về WebFlux Publisher và `Flux.using` đóng lease; active trở về 0 khi server **quan sát được** connection close/cancellation. Thời điểm không tuyệt đối vì TCP/proxy buffering.

## 13. Kiểm thử: WebTestClient và StepVerifier

Lưu `src/test/java/demo/WebFluxLifecycleTest.java`:

~~~java
package demo;

import java.time.Duration;
import java.util.concurrent.TimeoutException;
import java.util.concurrent.atomic.AtomicBoolean;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.WebFluxTest;
import org.springframework.context.annotation.Import;
import org.springframework.test.web.reactive.server.WebTestClient;

import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

@WebFluxTest(controllers = ApiController.class)
@Import({ItemService.class, EventService.class, ApiErrors.class})
class WebFluxLifecycleTest {
    @Autowired
    WebTestClient http;

    @Autowired
    EventService events;

    @Test
    void normalItemIs200() {
        http.get().uri("/api/items/ok").exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.id").isEqualTo("ok")
            .jsonPath("$.title").isEqualTo("Ready");
    }

    @Test
    void missingItemIs404() {
        http.get().uri("/api/items/missing").exchange()
            .expectStatus().isNotFound();
    }

    @Test
    void slowItemIsMappedTo504WithSafeBody() {
        http.get().uri("/api/items/slow").exchange()
            .expectStatus().isEqualTo(504)
            .expectBody()
            .jsonPath("$.code").isEqualTo("UPSTREAM_TIMEOUT")
            .jsonPath("$.detail").isEqualTo(
                    "Upstream did not respond in time");
    }

    @Test
    void internalErrorDoesNotExposeSecret() {
        http.get().uri("/api/items/boom").exchange()
            .expectStatus().is5xxServerError()
            .expectBody()
            .jsonPath("$.code").isEqualTo("INTERNAL_ERROR")
            .jsonPath("$.detail").isEqualTo(
                    "An unexpected error occurred")
            .jsonPath("$.detail").value(value ->
                    assertTrue(!String.valueOf(value)
                            .contains("password=secret")));
    }

    @Test
    void takeOneCancelsUpstreamAndCleansLease() {
        int before = events.activeConnections();

        StepVerifier.create(events.events().take(1))
            .expectNextMatches(event ->
                    "tick".equals(event.event())
                    && "tick-0".equals(event.data()))
            .verifyComplete();

        assertEquals(before, events.activeConnections());
    }

    @Test
    void timeoutCancelsUpstreamSource() {
        AtomicBoolean cancelled = new AtomicBoolean();

        StepVerifier.withVirtualTime(() ->
                Mono.<String>never()
                    .doOnCancel(() -> cancelled.set(true))
                    .timeout(Duration.ofSeconds(2)))
            .expectSubscription()
            .thenAwait(Duration.ofSeconds(2))
            .expectError(TimeoutException.class)
            .verify();

        assertTrue(cancelled.get());
    }

    @Test
    void onErrorResumeProvidesExplicitFallback() {
        StepVerifier.create(
                Mono.<String>error(
                        new IllegalStateException("temporary"))
                    .onErrorResume(IllegalStateException.class,
                            e -> Mono.just("fallback")))
            .expectNext("fallback")
            .verifyComplete();
    }
}
~~~

Chạy:

~~~bash
mvn test
~~~

**Ý nghĩa từng nhóm test:**

- WebTestClient kiểm HTTP response status/body của WebFlux controller và advice.
- StepVerifier kiểm cancellation/lease cleanup khi downstream `take(1)`, không dựa vào TCP socket giả.
- StepVerifier virtual time kiểm timeout/cancellation không chờ hai giây thật.
- OnErrorResume test chứng minh fallback là một **publisher thay thế**.
- Một test real-client-disconnect phải chạy qua embedded Netty/staging và đóng socket khi server đang ghi; `WebTestClient` slice tests không thay thế kiểm thử network/proxy.

**Hạn chế:** Test cleanup chịu điều kiện implementation của `Flux.using`. Nếu refactor sang shared/hot publisher, phải sửa ownership test. Test thời gian thực 150ms phụ thuộc scheduler của môi trường; có thể tăng test-specific timeout nếu CI cực chậm, nhưng không bỏ phân biệt error/cancel.

## 14. Kiểm thử tài nguyên bất đồng bộ và release

### 14.1. Test resource cleanup trên cả ba đường

Với `usingWhen`, thiết kế test:

~~~text
Case A: source emits value + completes
  -> asyncComplete runs
Case B: source emits error
  -> asyncError runs
Case C: downstream cancels subscription
  -> asyncCancel runs
~~~

Dùng counters hoặc mocked reactive connection và StepVerifier/PublisherProbe. Nếu cleanup Publisher của `usingWhen` cũng lỗi, phải quyết định liệu primary error bị thay thế/suppressed theo Reactor API và ghi log/metric chính xác.

### 14.2. Không dùng doFinally để subscribe fire-and-forget close

Sai:

~~~java
.doFinally(signal -> connection.close().subscribe())
~~~

Nếu `close()` trả Mono<Void>, đoạn này tự tạo một subscription ngoài ownership, khó xử lý close error và có thể không được test. Thay bằng `usingWhen` để close Publisher được framework đợi/quan sát theo contract.

### 14.3. Kiểm DataBuffer release

Khi code sở hữu pooled buffers, tests nên có path:

- Request complete bình thường, tất cả DataBuffers đã consumed/released.
- Cancel ở giữa stream.
- Downstream codec error.
- Filtering/drop/skip/prefetch discard.
- Concurrent subscribers (nếu source được chia sẻ).
- Bounded memory under slow reader.

Tránh tự tạo unit test “release hai lần cũng không sao”. Reference-counted buffers có thể báo lỗi khi double-release hoặc access after release. Không tái sử dụng DataBuffer đã được downstream release.

## 15. Phân biệt WebFlux cancellation với MVC Servlet disconnect

| Chủ đề | Spring WebFlux | Spring MVC |
| --- | --- | --- |
| Main model | Reactive Streams, non-blocking pipeline | Servlet stack; async processing dựa Servlet |
| Streaming return | `Flux<ServerSentEvent<T>>`, `Flux<DataBuffer>` | `SseEmitter`, `ResponseBodyEmitter`, `StreamingResponseBody` |
| Client cancel | Cancellation thường propagate vào subscription | Container async error/write failure callbacks |
| Cleanup | `using/usingWhen/doFinally/doOnCancel` | `onCompletion/onTimeout/onError` và resource owner |
| Timeout | Reactor `timeout`, Netty/HTTP/gateway timeouts | Servlet async timeout, emitter timeout, proxy |
| Error status sau commit | Không thể đổi HTTP status đã gửi | Cùng giới hạn HTTP |
| Blocking I/O | Tránh trên event loop | Có thể chạy ở worker nhưng vẫn tiêu tốn threads |
| Backpressure | Reactive Streams request/cancel | Phụ thuộc async write/callback và I/O behavior |

**Không dùng `SseEmitter.completeWithError` trong WebFlux** vì đó là Servlet MVC API. Tương tự, không coi việc WebFlux subscriber cancel giống hệt MVC `onCompletion` callback.

## 16. Các lỗi phổ biến cần tránh

1. **Coi CANCEL là onError.** `onErrorResume` không xử lý subscriber cancel; đặt cleanup trong `using/usingWhen/doFinally` theo ownership.
2. **Dùng doOnError để đóng resource.** Bỏ sót normal completion và cancellation.
3. **Fire-and-forget subscribe() để close resource.** Mất liên kết lifecycle/close errors.
4. **Tạo resource ngoài Mono.defer/using.** Nếu Publisher không được subscribe có thể leak.
5. **Đóng shared producer khi một client unsubscribe.** Ảnh hưởng các clients khác.
6. **retryWhen cho POST payment không idempotent.** Gây thao tác trùng.
7. **retry mọi lỗi 4xx và bug logic.** Làm lỗi nặng hơn và tăng tải.
8. **Dùng timeout mà không biết cancel propagation.** Background/side effects có thể vẫn chạy.
9. **Giữ DataBuffer pooled sau khi framework release.** Access-after-release/memory safety.
10. **Quên release body của WebClient exchange() cũ.** Connection pool/direct memory leak.
11. **Đưa response body raw vào error log/public error.** Lộ thông tin.
12. **Bắt Throwable rồi onErrorComplete vô điều kiện.** Che bug và tạo dữ liệu thiếu.
13. **Cố đổi status/headers khi stream committed.** Không thể phát response 500 mới.
14. **Dùng block() hoặc Thread.sleep() trên event loop.** Nghẽn toàn bộ reactive server.
15. **Lưu unbounded queue cho SSE clients chậm.** OOM khi mạng yếu.
16. **Dùng userId/requestId làm metric labels.** Cardinality bùng nổ.
17. **Không giới hạn concurrent connections và per-tenant subscriptions.** Cạn tài nguyên.
18. **Cho rằng cancel giúp rollback remote side effect.** Không có đảm bảo.
19. **Suy từ HTTP 499 là response chuẩn server phát.** Đây là ký hiệu gateway riêng.
20. **Chỉ kiểm HTTP status mà không test cleanup.** Dễ leak khi timeout/cancel xảy ra.
21. **Cho rằng successful send luôn tới client.** Proxy/TCP buffers có thể làm observation chậm.
22. **Chỉ dùng MockWebServer/slice tests để khẳng định socket disconnect semantics.** Cần integration test thật nếu high stakes.

## 17. Logging và observability

Nên phân biệt terminal signals:

~~~text
request_completed   status=200 result=success
request_failed      status=504 errorCategory=UPSTREAM_TIMEOUT
stream_cancelled    endpoint=/api/events reason=client-or-downstream-cancel
stream_terminated   endpoint=/api/events signal=CANCEL lifetimeMs=...
resource_released   type=reactive-lease outcome=closed
~~~

Các logs trên là **ví dụ**; không suy chính xác client đóng tab chỉ từ `SignalType.CANCEL`. Một `take(1)` hợp lệ cũng có thể cancel upstream.

Metrics có ích:

- HTTP status và latency theo route template.
- Upstream timeout/circuit-breaker rates.
- Active reactive subscriptions/SSE sessions.
- Cancellation count theo endpoint và finite reason groups.
- Resource lease active/acquired/released, cleanup failures.
- Netty connection pool active/idle/pending acquire.
- DataBuffer/direct memory và allocator metrics.
- Retry attempts, fallback rates, backpressure overflow.
- Event-loop saturation/blocked operations.
- Gateway client resets/read timeouts.

Không đưa token, cookie, raw body, stacktrace và PII vào response hoặc high-cardinality metrics. Correlation ID/trace ID phục vụ tìm logs, nhưng không tự là identity/authentication proof.

## 18. Checklist production

- [ ] Đã phân loại complete, error, cancel riêng trong lifecycle và metrics.
- [ ] Lỗi được map theo domain và HTTP status phù hợp, không rò exception internals.
- [ ] onErrorResume/onErrorComplete chỉ dùng khi fallback/suppression đúng contract.
- [ ] Retry có giới hạn, idempotency, jitter/backoff và overall deadline budget.
- [ ] Timeout operator được đặt đúng vị trí so với retry và recovery.
- [ ] Cancellation được propagate tới nguồn; external blocking side effects có cancellation riêng hoặc có chủ đích.
- [ ] Synchronous resources dùng using/try-with-resources đúng ownership; async resources dùng usingWhen hoặc reactive transaction API.
- [ ] Cleanup complete/error/cancel có tests và không double-close shared resource.
- [ ] WebClient response body được consume/release, không còn exchange() legacy dễ rò.
- [ ] Raw DataBuffers pooled được release khi thuộc quyền sở hữu app, kể cả discard/cancel.
- [ ] Streams dùng bounded queues/backpressure/quota, không tạo publisher vô hạn thiếu kiểm soát.
- [ ] Sau response committed không cố gửi HTTP status/ProblemDetail mới.
- [ ] SSE có reconnect/Last-Event-ID/replay contract và proxy buffering/timeout được kiểm thử.
- [ ] Không chạy blocking JDBC/filesystem calls trên Reactor Netty event-loop.
- [ ] Có WebTestClient, StepVerifier và embedded-network integration tests cho timeout/cancel/cleanup.
- [ ] Active resources/connection pools/cleanup failures được đo và alert.
- [ ] TLS/CORS/authz/cookie/CSRF được thiết kế riêng, không coi cancellation/timeout như biện pháp bảo mật.

## 19. Bài tập tự luyện

**Bài 1 — Ba tín hiệu:** Một `Flux.range(1,10).take(1)` kết thúc sau phần tử đầu. Upstream thấy signal nào? Downstream thấy gì? Vì sao không nên ghi error metric?

**Bài 2 — doFinally:** Viết `Mono.never().timeout(Duration.ofSeconds(2))` với doFinally trước và sau timeout. Dùng StepVerifier virtual time để ghi lại upstream CANCEL và downstream ON_ERROR.

**Bài 3 — Error mapping:** API gọi upstream trả TimeoutException. Dùng onErrorMap thành domain exception, advice trả ProblemDetail 504 với code ổn định và không lộ raw exception message.

**Bài 4 — Cancellation:** Client đóng EventSource đang đọc Flux.interval. Phân tích điều kiện cancel lan upstream, cleanup per subscription và tại sao producer hot dùng chung không nên bị shutdown.

**Bài 5 — Resource:** Viết Flux.using cho resource AutoCloseable. Test complete, error và cancel bằng StepVerifier; xác minh counter acquired == released.

**Bài 6 — Async close:** Một reactive DB session có close() trả Mono<Void>. Hãy dùng usingWhen với asyncComplete, asyncError và asyncCancel thay vì close().subscribe() trong doFinally.

**Bài 7 — WebClient:** Chuyển WebClient .exchange() cũ sang exchangeToMono, giải thích release body 404 và path lỗi. Nếu cần body lỗi, decode ở đâu?

**Bài 8 — DataBuffer:** Một Flux<DataBuffer> bị filter và discard khi cancel. Ai sở hữu buffer, khi nào dùng DataBufferUtils.release/doOnDiscard, và vì sao double release nguy hiểm?

**Bài 9 — Retry:** Thiết kế retry cho GET idempotent với backoff+jitter+deadline. Vì sao copy nguyên chính sách sang POST thanh toán là nguy hiểm?

**Bài 10 — Streaming commit:** SSE đã phát HTTP 200 và ba events rồi lỗi business. Vì sao không thể đổi status thành 500? Thiết kế in-band app-error event nếu stream còn usable.

**Bài 11 — Timeout layers:** Một browser thấy 504 sau 30s dù server Reactor timeout đặt 60s. Những tầng proxy/WebClient cần kiểm?

**Bài 12 — Backpressure:** Producer tạo 1000 events/giây, client đọc 10 events/giây. Chọn bounded queue/drop/coalesce hoặc durable replay cho dữ liệu progress và giao dịch.

**Bài 13 — Test:** Viết StepVerifier xác minh onErrorResume fallback không chạy khi source được cancel, và dùng PublisherProbe hoặc AtomicBoolean kiểm cleanup.

**Bài 14 — Blocking source:** Chuyển một legacy blocking SDK call thành Mono.fromCallable(...).subscribeOn(Schedulers.boundedElastic()), giải thích vì sao cancellation không bảo đảm lệnh SDK dừng tức thời.

## 20. Ghi nhớ

- Trong Reactor, **complete, error và cancel không giống nhau**; cancellation là tín hiệu downstream lên upstream, không phải một onError.
- `doFinally` có thể quan sát `ON_COMPLETE`, `ON_ERROR`, `CANCEL`; resource lifecycle nên dùng `using/usingWhen`.
- `timeout` phát TimeoutException downstream và cancel nguồn khi hết hạn, nhưng external operations có thể vẫn thực thi.
- `onErrorResume` tạo fallback Publisher, không phục hồi vị trí đã lỗi trong nguồn ban đầu.
- `retryWhen` resubscribe, có thể phát lại side effects/records; cần idempotency và deadline.
- WebClient `retrieve/exchangeToMono/exchangeToFlux` an toàn hơn `exchange()` cũ nếu không quản lý body release tường minh.
- Pooled `DataBuffer` đòi **ownership rõ** để tránh leak hoặc double release.
- Khi response đã committed, lỗi stream không thể được biến thành HTTP 500 JSON mới; dùng in-band event khi có thể hoặc cancel/cleanup.
- Hủy một subscription không có nghĩa dừng mọi shared producer hay remote side effect.
- Tests cần kiểm **cả dữ liệu/status lẫn release trên cancel/error/timeout**.

## 21. Tài liệu chính thức

- [Spring Framework 6.2 — WebFlux](https://docs.spring.io/spring-framework/reference/6.2/web/webflux.html): reactive stack, backpressure và tổng quan.
- [Spring Framework 6.2 — WebFlux Error Responses](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/ann-rest-exceptions.html): ProblemDetail/ErrorResponse và controller advice.
- [Spring Framework 6.2 — WebFlux Exceptions](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller/ann-exceptions.html): @ExceptionHandler.
- [Spring Framework 6.2 — WebClient exchange](https://docs.spring.io/spring-framework/reference/6.2/web/webflux-webclient/client-exchange.html): exchangeToMono/exchangeToFlux, response body release.
- [Spring Framework 6.2 — Data Buffers and Codecs](https://docs.spring.io/spring-framework/reference/6.2/core/databuffer-codec.html): DataBuffer pooled lifecycle và release.
- [Project Reactor — Error Handling](https://projectreactor.io/docs/core/release/reference/coreFeatures/error-handling.html): onErrorResume, onErrorMap, retry, doFinally, using.
- [Project Reactor — Dealing with Objects that Need Cleanup](https://projectreactor.io/docs/core/release/reference/advancedFeatures/cleanup.html): reference counting, discard, cleanup.
- [Reactor Flux API](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Flux.html): using, usingWhen, doFinally, timeout, doOnCancel.
- [Reactor StepVerifier](https://projectreactor.io/docs/test/release/api/reactor/test/StepVerifier.html): virtual time, cancellation/termination tests.
- [Reactive Streams 1.0.4 Specification](https://www.reactive-streams.org/reactive-streams-1.0.4-spec-javadoc/org/reactivestreams/Subscription.html): request(n), cancel contract.
- [HTTP Semantics — RFC 9110](https://www.rfc-editor.org/rfc/rfc9110): status, committed HTTP response semantics.
