# Theo dõi chuỗi tín hiệu bằng log và các toán tử doOn trong Reactor

## 1. Vì sao cần theo dõi tín hiệu reactive?

Một chuỗi Reactor không chạy như đoạn code tuần tự ngay tại thời điểm gọi các method. Khi viết:

~~~java
Mono<Product> product = repository.findById(id)
        .map(this::toResponse)
        .doOnNext(response -> log.info("mapped {}", response));
~~~

ta đang **lắp ráp một pipeline**. Nguồn dữ liệu thường chỉ bắt đầu thực thi khi có subscription và demand phù hợp. Trong một request WebFlux, framework là thành phần subscribe vào Publisher mà controller trả về.

Khi debug, cần trả lời được:

- Pipeline đã được subscribe chưa?
- Subscriber đã yêu cầu bao nhiêu phần tử?
- Nguồn có phát onNext không?
- Phần tử có bị filter hoặc discard ở đâu?
- Pipeline hoàn tất bình thường hay phát error?
- Consumer có hủy subscription trước khi nguồn hoàn tất không?
- Callback doOn nằm ở vị trí nào trong chuỗi và đang quan sát giá trị trước hay sau transformation?

Reactor cung cấp hai nhóm công cụ chính:

1. **log():** ghi lại các tín hiệu Reactive Streams đi qua vị trí của operator.
2. **Các toán tử doOn...:** gọi callback khi một loại tín hiệu hoặc sự kiện cụ thể xuất hiện, mà không chủ đích biến đổi phần tử.

Các công cụ này giúp quan sát pipeline. Chúng không thay thế map, flatMap, onErrorResume, retry hoặc logic nghiệp vụ.

## 2. Hiểu vòng đời subscription và tín hiệu

Reactive Streams có bốn tín hiệu chính từ Publisher tới Subscriber:

- **onSubscribe(Subscription):** Publisher cung cấp Subscription để Subscriber điều khiển demand và cancellation.
- **onNext(value):** Publisher phát một phần tử.
- **onError(error):** Publisher kết thúc bằng lỗi.
- **onComplete():** Publisher kết thúc thành công.

Subscriber cũng gọi hai method điều khiển ngược về Publisher:

- **request(n):** yêu cầu tối đa n phần tử tiếp theo.
- **cancel():** hủy subscription, yêu cầu Publisher dừng phát dữ liệu.

Mô hình đơn giản:

~~~text
Subscriber                         Publisher
    |                                  |
    |<------ onSubscribe(subscription)-|
    |                                  |
    |---------- request(2) ------------>|
    |                                  |
    |<------------- onNext(A) ----------|
    |<------------- onNext(B) ----------|
    |                                  |
    |---------- request(1) ------------>|
    |<------------- onNext(C) ----------|
    |<------------- onComplete() -------|
~~~

Nếu subscriber hủy trước khi nguồn kết thúc:

~~~text
Subscriber                         Publisher
    |                                  |
    |<------ onSubscribe(subscription)-|
    |---------- request(1) ------------>|
    |<------------- onNext(A) ----------|
    |---------- cancel() -------------->|
    |                                  |
    |       Không còn onNext mới        |
~~~

request(n) là cơ chế backpressure. Nó mô tả demand, không phải số phần tử chắc chắn đã xử lý. Nguồn có thể phát ít hơn demand, kết thúc sớm hoặc lỗi. Một số operator còn điều chỉnh/prefetch demand upstream nên giá trị doOnRequest phụ thuộc vị trí đặt operator.

cancel() không phải onComplete() và cũng không phải onError(). Vì vậy, chỉ log doOnComplete hoặc doOnError sẽ bỏ lỡ trường hợp client đóng kết nối hoặc downstream chủ động dừng stream.

### 2.1. Mono và Flux có terminal signal khác nhau

- **Mono<T>** phát tối đa một onNext(T), sau đó onComplete(), hoặc phát onComplete() rỗng, hoặc onError().
- **Flux<T>** phát từ 0 đến nhiều onNext, sau đó onComplete() hoặc onError().
- **Mono.empty()** hoàn tất thành công nhưng không phát giá trị.
- **Mono.error(error)** kết thúc bằng lỗi mà không phát giá trị.

Điểm này đặc biệt quan trọng với Mono.doOnSuccess: callback được gọi cả khi Mono có giá trị và khi Mono hoàn tất rỗng. Trong trường hợp rỗng, giá trị truyền vào callback là null. doOnNext chỉ chạy khi có phần tử.

## 3. Lắp ráp pipeline khác với thực thi pipeline

~~~java
Flux<Integer> numbers = Flux.defer(() -> {
    log.info("source factory invoked");
    return Flux.range(1, 3);
}).doOnSubscribe(subscription ->
        log.info("subscribed"));
~~~

Khi chạy dòng khai báo numbers, pipeline được tạo nhưng Flux.defer chưa gọi supplier. Khi có subscriber:

1. defer tạo nguồn cho subscription đó.
2. doOnSubscribe quan sát subscription.
3. Subscriber yêu cầu demand.
4. Nguồn phát các phần tử và terminal signal.

Nếu cold publisher được subscribe hai lần, nguồn có thể chạy hai lần và các callback cũng chạy hai lần. Vì thế log trùng không nhất thiết có nghĩa một request đã xử lý hai lần; có thể ứng dụng đã tạo hai subscription.

Trong WebFlux, controller nên trả Mono/Flux để framework quản lý subscription:

~~~java
@GetMapping("/products")
Flux<Product> products() {
    return service.findAll();
}
~~~

Không gọi subscribe() thủ công trong controller chỉ để "cho nó chạy". Việc subscribe tách rời làm framework không còn sở hữu đầy đủ lifecycle, cancellation và error của công việc đó.

## 4. Bảng tra cứu các toán tử doOn

| Operator | Khi nào callback chạy? | Dùng để quan sát |
| --- | --- | --- |
| doFirst | Trước khi upstream được subscribe | Điểm bắt đầu subscription |
| doOnSubscribe | Khi nhận Subscription | Một subscription mới |
| doOnRequest | Khi nhận request(n) | Demand/backpressure |
| doOnNext | Khi có phần tử onNext | Giá trị tại vị trí operator |
| doOnEach | Khi có onNext, onError hoặc onComplete | Tín hiệu Subscriber ở dạng Signal |
| doOnError | Khi nguồn kết thúc bằng error | Exception và mã lỗi |
| Flux.doOnComplete | Khi Flux hoàn tất thành công | Hoàn tất Flux |
| Mono.doOnSuccess | Khi Mono hoàn tất thành công, có hoặc không có giá trị | Giá trị hoặc null nếu empty |
| doOnCancel | Khi downstream gọi cancel | Hủy subscription |
| doOnTerminate | Khi hoàn tất hoặc lỗi, trước khi terminal signal được chuyển tiếp | Kết thúc success/error |
| doAfterTerminate | Sau khi onComplete/onError đã được chuyển tiếp | Công việc sau terminal signal |
| doFinally | Sau complete, error hoặc cancel | Kết thúc mọi kiểu |
| doOnDiscard | Khi operator hỗ trợ discard loại bỏ phần tử upstream | Cleanup tài nguyên bị loại bỏ |

Các callback doOn... được thiết kế cho side effect. Chúng không biến đổi phần tử đang đi qua pipeline. Nếu cần thay đổi dữ liệu, dùng map, flatMap, filter hoặc operator tương ứng.

### 4.1. doOnSubscribe và doFirst

~~~java
Flux<Integer> pipeline = Flux.range(1, 2)
        .doFirst(() -> log.info("doFirst"))
        .doOnSubscribe(subscription ->
                log.info("doOnSubscribe"));
~~~

doFirst chạy trước khi upstream được subscribe. doOnSubscribe chạy khi Subscription được truyền tới subscriber ở vị trí operator.

Nếu xếp nhiều doFirst liên tiếp, thứ tự callback có thể ngược với thứ tự khai báo do subscription truyền ngược từ downstream về upstream. Đừng dùng thứ tự log của các doFirst nối tiếp như một cơ chế nghiệp vụ.

### 4.2. doOnRequest

~~~java
Flux<Integer> pipeline = Flux.range(1, 10)
        .doOnRequest(n ->
                log.info("upstream demand={}", n));
~~~

doOnRequest hữu ích khi kiểm tra consumer có yêu cầu unbounded demand hay không, hoặc operator đang prefetch bao nhiêu phần tử.

Ví dụ một test chủ động yêu cầu từng phần tử:

~~~java
StepVerifier.create(pipeline, 0)
        .thenRequest(2)
        .expectNext(1, 2)
        .thenCancel()
        .verify();
~~~

Với pipeline đơn giản không có operator điều chỉnh demand, callback có thể quan sát request(2). Khi thêm publishOn, flatMap, buffer hoặc operator prefetch, demand upstream có thể lớn hơn request trực tiếp từ subscriber.

Không cộng các giá trị request để suy ra số business record đã xử lý. Dùng doOnNext hoặc metric ở vị trí phù hợp để đo số phần tử thực tế.

### 4.3. doOnNext

~~~java
Flux<Integer> pipeline = Flux.range(1, 3)
        .doOnNext(value ->
                log.info("received value={}", value));
~~~

Callback chạy khi một phần tử được phát qua vị trí doOnNext. Nó không chạy cho Mono.empty() hoặc Flux.empty().

Đặt callback trước hay sau filter sẽ quan sát tập phần tử khác nhau:

~~~java
Flux.range(1, 5)
        .doOnNext(value -> log.info("source={}", value))
        .filter(value -> value % 2 == 0)
        .doOnNext(value -> log.info("accepted={}", value))
        .map(value -> value * 10)
        .doOnNext(value -> log.info("mapped={}", value));
~~~

Các giá trị quan sát:

- source: 1, 2, 3, 4, 5.
- accepted: 2, 4.
- mapped: 20, 40.

Đây là kỹ thuật rất hiệu quả để tìm operator đã loại bỏ hoặc thay đổi dữ liệu ở đoạn nào.

### 4.4. doOnEach

doOnEach nhận Signal<T>. Có thể phân biệt:

- signal.isOnNext() và lấy signal.get().
- signal.isOnError() và lấy signal.getThrowable().
- signal.isOnComplete() để nhận biết complete.

Ví dụ:

~~~java
Flux.range(1, 2)
        .doOnEach(signal -> {
            if (signal.isOnNext()) {
                log.info("next={}", signal.get());
            } else if (signal.isOnError()) {
                log.warn("error", signal.getThrowable());
            } else if (signal.isOnComplete()) {
                log.info("complete");
            }
        });
~~~

doOnEach hữu ích khi cần một callback tập trung cho ba loại tín hiệu Subscriber. Nó không thay thế doOnRequest hoặc doOnCancel, vì request và cancel là các thao tác điều khiển Subscription, không phải onNext/onError/onComplete.

Nếu chỉ cần log một giá trị, doOnNext ngắn gọn hơn. Nếu cần context hoặc cần phân biệt complete/error ngay trong một callback, doOnEach phù hợp hơn.

### 4.5. doOnError không phục hồi lỗi

~~~java
Mono<Product> product = repository.findById(id)
        .doOnError(error ->
                log.warn("find product failed", error));
~~~

doOnError quan sát lỗi nhưng lỗi vẫn tiếp tục truyền downstream. Nếu muốn thay thế lỗi bằng fallback, dùng operator phục hồi:

~~~java
Mono<Product> product = repository.findById(id)
        .doOnError(error ->
                log.warn("find product failed", error))
        .onErrorResume(error ->
                cache.findById(id));
~~~

Không đặt logic phục hồi trong logger. Giữ riêng nhiệm vụ quan sát và nhiệm vụ thay đổi control flow để dễ kiểm thử.

### 4.6. doOnSuccess của Mono và giá trị null

~~~java
Mono.<String>empty()
        .doOnSuccess(value ->
                log.info("success value={}", value));
~~~

Callback vẫn chạy dù không có onNext; value là null. Điều đó khác với doOnNext, vốn không được gọi trong trường hợp này.

Nếu cần phân biệt empty và value, có thể kiểm tra null trong doOnSuccess, hoặc dùng switchIfEmpty để xử lý empty như một nhánh riêng.

### 4.7. doOnComplete, doOnTerminate và doAfterTerminate

- Flux.doOnComplete chỉ quan sát complete thành công của Flux.
- doOnTerminate quan sát complete hoặc error, không quan sát cancel.
- doAfterTerminate chạy sau khi complete/error đã được chuyển tiếp downstream; nó cũng không chạy khi cancel.
- Với Mono, onNext là phần tử cuối trước complete; doOnSuccess thường diễn đạt rõ ý hơn nếu cần giá trị thành công.

Không dùng các operator này để đảm bảo cleanup khi consumer hủy stream. Dùng doFinally hoặc doOnCancel tùy mục đích.

### 4.8. doOnCancel và doFinally

~~~java
Flux<Long> ticks = Flux.interval(Duration.ofMillis(200))
        .doOnCancel(() ->
                log.info("downstream cancelled"))
        .doFinally(signalType ->
                log.info("terminated by {}", signalType));
~~~

doOnCancel chạy khi subscription bị hủy. doFinally nhận SignalType và chạy sau khi pipeline kết thúc bởi:

- ON_COMPLETE
- ON_ERROR
- CANCEL

Vì doFinally chạy sau khi terminal signal đã được chuyển tiếp downstream, callback có thể xuất hiện sau assertion hoặc code xử lý complete của subscriber. Nó thích hợp để kết thúc timer, ghi metric hoặc cleanup nhẹ.

Nếu nhiều doFinally được nối liên tiếp, callback có thể chạy theo thứ tự ngược với thứ tự khai báo. Không dựa vào thứ tự đó để phối hợp tài nguyên quan trọng; dùng usingWhen, doFinally ở một ranh giới lifecycle rõ ràng hoặc abstraction quản lý resource phù hợp.

### 4.9. doOnDiscard

Một số operator có thể loại bỏ phần tử đã được prefetch hoặc buffer khi downstream filter/cancel/error. doOnDiscard cho phép đăng ký cleanup cho các kiểu phần tử mà operator upstream hỗ trợ discard:

~~~java
Flux<DataBuffer> buffers = source
        .filter(this::isUseful)
        .doOnDiscard(DataBuffer.class, DataBufferUtils::release);
~~~

Đây là ví dụ minh họa cho DataBuffer có ownership theo contract. doOnDiscard chỉ có tác dụng với operator hỗ trợ discard và phải đặt đúng vị trí trong chain. Cleanup callback cần idempotent và an toàn với mọi instance cùng kiểu.

Không thêm doOnDiscard tùy tiện cho mọi object. Với DataBuffer/pooled resource, hãy tuân theo hướng dẫn ownership và retain/release của API đang dùng.

## 5. log(): xem tín hiệu ở một vị trí trong pipeline

### 5.1. Cách dùng cơ bản

~~~java
Flux<Integer> result = Flux.range(1, 3)
        .log("example.reactor.source")
        .map(value -> value * 10);
~~~

log() ghi nhận các tín hiệu Reactive Streams đi qua operator đó, thường gồm subscription, request, onNext, onComplete, onError và cancel. Nó hữu ích khi cần nhìn tổng thể thay vì tự viết nhiều callback.

Reactor dùng Loggers để tích hợp logging framework phổ biến qua SLF4J, chẳng hạn Logback hoặc Log4j. Nếu không có logging backend tương thích, cơ chế fallback có thể ghi ra console. Ứng dụng production nên cấu hình logging backend không gây blocking cho event-loop.

### 5.2. Vị trí log quyết định giá trị được quan sát

~~~java
Flux.range(1, 3)
        .log("before-map")
        .map(value -> value * 10)
        .log("after-map");
~~~

Log trước map thấy 1, 2, 3; log sau map thấy 10, 20, 30. Operator log quan sát tín hiệu ở vị trí của nó trong chain, nên có thể đặt nhiều log category ngắn tại các ranh giới quan trọng.

Tương tự với filter:

~~~java
Flux.range(1, 5)
        .log("before-filter")
        .filter(value -> value % 2 == 0)
        .log("after-filter");
~~~

before-filter nhìn thấy cả năm giá trị. after-filter chỉ nhìn thấy 2 và 4.

### 5.3. Chọn category và mức log

Có thể dùng category riêng để bật/tắt trong application.yml hoặc cấu hình Logback:

~~~java
Flux.range(1, 3)
        .log("app.reactor.catalog", Level.DEBUG);
~~~

Ví dụ cấu hình:

~~~yaml
logging:
  level:
    root: INFO
    app.reactor.catalog: DEBUG
~~~

Nếu bật log chi tiết trên mọi pipeline production, log volume có thể tăng mạnh. Chỉ bật ở component hoặc request cần điều tra, sau đó tắt khi hoàn tất.

### 5.4. log() và doOn... khác nhau thế nào?

| Công cụ | Ưu điểm | Hạn chế |
| --- | --- | --- |
| log() | Quan sát nhiều signal và request/cancel ở một vị trí | Log có thể khá nhiều, khó tùy biến business fields |
| doOnNext | Ghi một giá trị cụ thể | Không thấy error/cancel nếu không thêm operator khác |
| doOnEach | Nhận Signal và có thể đọc Reactor Context | Cần phân nhánh signal |
| doOnError | Ghi exception có chủ đích | Không phục hồi lỗi |
| doFinally | Quan sát complete/error/cancel | Không cung cấp phần tử cuối hoặc exception trực tiếp |
| doOnRequest | Quan sát demand | Demand không đồng nghĩa số record đã xử lý |

Thực tế thường kết hợp: log() tạm thời để thấy toàn bộ signal, sau đó giữ một số doOn... có ý nghĩa vận hành như error, duration, cancellation và trace ID.

## 6. Ví dụ minh họa vị trí operator

Xét pipeline:

~~~java
Flux<Integer> result = Flux.range(1, 5)
        .doOnSubscribe(s -> log.info("subscribed"))
        .doOnRequest(n -> log.info("requested={}", n))
        .doOnNext(v -> log.info("raw={}", v))
        .filter(v -> v % 2 == 0)
        .doOnNext(v -> log.info("filtered={}", v))
        .map(v -> v * 10)
        .doOnNext(v -> log.info("mapped={}", v))
        .doOnComplete(() -> log.info("completed"))
        .doFinally(type -> log.info("finally={}", type));
~~~

Khi subscriber yêu cầu đủ dữ liệu, các giá trị đi qua các điểm quan sát như sau:

| Điểm quan sát | Giá trị |
| --- | --- |
| raw | 1, 2, 3, 4, 5 |
| filtered | 2, 4 |
| mapped | 20, 40 |
| doOnComplete | Một lần khi Flux hoàn tất |
| doFinally | Một lần với ON_COMPLETE |

Nếu downstream cancel sau khi nhận 20, doOnComplete không chạy; doFinally nhận CANCEL. Đây là ví dụ điển hình vì sao log terminal signal phải phân biệt complete với cancel.

## 7. Reactor Context, trace ID và MDC

### 7.1. Vì sao ThreadLocal dễ gây lỗi?

Reactive pipeline có thể chuyển qua nhiều thread khi dùng publishOn, subscribeOn, scheduler hoặc connector. ThreadLocal/MDC truyền thống gắn dữ liệu với thread hiện tại, không tự động gắn với subscriber.

Không nên giả định:

~~~java
MDC.put("traceId", traceId);
return service.call();
~~~

rằng mọi callback về sau đều nhìn thấy MDC đó. Khi pipeline đổi thread, MDC có thể mất hoặc mang giá trị của một request khác nếu không được quản lý đúng.

### 7.2. Dùng Reactor Context

Reactor Context là dữ liệu gắn với subscriber, phù hợp để mang correlation ID qua pipeline:

~~~java
Flux<String> pipeline = Flux.just("A", "B")
        .doOnEach(signal -> {
            if (signal.isOnNext()) {
                String traceId = signal.getContextView()
                        .getOrDefault("traceId", "unknown");

                log.info("trace={} value={}",
                        traceId, signal.get());
            }
        })
        .contextWrite(context ->
                context.put("traceId", "req-42"));
~~~

contextWrite cung cấp context theo hướng subscription từ downstream lên upstream. Vì vậy vị trí của nó quan trọng; đặt context ở nhánh không liên quan có thể khiến operator không đọc được key mong muốn.

Context immutable theo cách sử dụng API; contextWrite tạo context mới cho subscription thay vì sửa một global map dùng chung.

### 7.3. Kết hợp MDC

Nếu log format yêu cầu MDC, dùng cơ chế context propagation tương thích với phiên bản Reactor/Spring và logging backend, chẳng hạn Micrometer Context Propagation khi ứng dụng đã tích hợp. Cấu hình automatic context propagation hoặc hook toàn cục phải được hiểu rõ và kiểm thử; không thêm global hook tùy tiện chỉ để một dòng log có trace ID.

Cách đơn giản và an toàn là lấy trace ID từ Signal.getContextView() tại callback cần log, rồi truyền nó như một structured logging field. Nếu dùng MDC thủ công, phải restore/clear giá trị trong mọi nhánh để tránh rò context giữa request.

## 8. Debug lỗi assembly và operator chain

### 8.1. checkpoint()

Khi một error xuất hiện sâu trong pipeline, stack trace có thể chỉ rõ nơi error được phát nhưng không cho thấy đầy đủ nơi chain được lắp ráp.

Thêm checkpoint có tên:

~~~java
Mono<Product> product = repository.findById(id)
        .map(this::toResponse)
        .checkpoint("CatalogService.findProduct");
~~~

Checkpoint giúp thêm dấu mốc vào assembly traceback. Có thể dùng full stack trace:

~~~java
.checkpoint("CatalogService.findProduct", true)
~~~

Full stack capture có chi phí cao hơn. Chỉ bật khi cần chẩn đoán.

### 8.2. Hooks.onOperatorDebug()

~~~java
Hooks.onOperatorDebug();
~~~

Hook này bật assembly tracing rộng hơn cho các operator được tạo sau khi hook được kích hoạt. Nó hữu ích trong môi trường phát triển, nhưng có overhead; không bật vô điều kiện trên production traffic lớn.

Nếu cần agent hỗ trợ debug hiệu quả hơn, Reactor cung cấp ReactorDebugAgent qua dependency reactor-tools ở những phiên bản tương thích. Đọc hướng dẫn đúng version và khởi tạo agent trước khi pipeline được tạo.

### 8.3. Phân biệt error gốc và lỗi từ callback

doOnError chỉ nên ghi log. Nếu callback doOn tự ném exception, callback có thể làm thay đổi kết quả pipeline hoặc tạo lỗi operator. Vì vậy:

- Logger phải an toàn và nhanh.
- Không parse/serialize payload lớn trong callback log.
- Không gọi API blocking hoặc database từ callback.
- Không để formatter hoặc redaction code tự phát sinh exception.
- Nếu cần biến đổi lỗi, dùng onErrorMap; nếu cần fallback, dùng onErrorResume.

## 9. Logging trong WebFlux: các quy tắc vận hành

### 9.1. Không block event-loop

Logging synchronous nặng, ghi file/network chậm hoặc format object lớn có thể làm chậm event-loop. Dùng backend và appender phù hợp; tránh log nguyên body lớn trong callback.

### 9.2. Không log dữ liệu nhạy cảm

Không ghi:

- Authorization header, access token, refresh token.
- Session ID, cookie, CSRF token.
- Password, API key, private key.
- Dữ liệu cá nhân hoặc payload chứa thông tin thanh toán.
- Toàn bộ request/response body khi chưa redaction.

Nên ghi metadata hữu ích: trace ID, route, method, status, duration, upstream name, item count và mã lỗi đã chuẩn hóa.

### 9.3. Không biến log thành metric

Log mỗi phần tử của một Flux rất lớn có thể tạo hàng triệu dòng. Để đo throughput, error rate hoặc latency, dùng Micrometer metrics/observation hoặc tracing phù hợp. Log chi tiết giúp điều tra một request; metric giúp nhìn xu hướng toàn hệ thống.

### 9.4. Không tạo side effect nghiệp vụ trong doOn

Ví dụ không nên:

~~~java
orders.doOnNext(order -> paymentService.charge(order));
~~~

doOnNext không phải nơi phù hợp để thực hiện một tác vụ reactive bất đồng bộ mà không compose kết quả. Nếu charge trả Mono, dùng flatMap:

~~~java
orders.flatMap(paymentService::charge);
~~~

Dùng doOn để quan sát; dùng operator biến đổi/compose để điều khiển nghiệp vụ.

## 10. Dự án chạy được: Java 17+, Spring Boot 3.5 và Reactor

Ví dụ tạo một WebFlux application có các endpoint:

- GET /debug/numbers: phát bốn số đã biến đổi, log subscription/request/value/complete.
- GET /debug/failure: phát hai giá trị rồi kết thúc bằng lỗi để quan sát doOnError.
- GET /debug/events: stream event theo thời gian; khi client ngắt, doOnCancel và doFinally ghi nhận cancellation.
- GET /debug/context: minh họa trace ID đi qua Reactor Context.

Test dùng StepVerifier để xác nhận value, error, signal order, context và cancellation mà không phụ thuộc thời gian mạng.

### 10.1. Cấu trúc project

~~~text
reactor-signal-tracing/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/example/tracing/
    │   │   ├── SignalTraceApplication.java
    │   │   ├── SignalTraceService.java
    │   │   └── SignalTraceController.java
    │   └── resources/application.yml
    └── test/java/example/tracing/
        └── SignalTraceServiceTest.java
~~~

### 10.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>example</groupId>
    <artifactId>reactor-signal-tracing</artifactId>
    <version>1.0.0</version>

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

Spring Boot quản lý phiên bản Reactor tương thích qua dependency management; không cần tự override reactor-core nếu chưa có lý do rõ ràng.

### 10.3. SignalTraceApplication.java

~~~java
package example.tracing;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SignalTraceApplication {

    public static void main(String[] args) {
        SpringApplication.run(SignalTraceApplication.class, args);
    }
}
~~~

### 10.4. SignalTraceService.java

~~~java
package example.tracing;

import java.time.Duration;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Signal;

@Service
public class SignalTraceService {

    private static final Logger log =
            LoggerFactory.getLogger(SignalTraceService.class);

    public Flux<Integer> numbers() {
        return Flux.range(1, 4)
                .name("debug-numbers")
                .doOnSubscribe(subscription ->
                        log.info("numbers subscribed"))
                .doOnRequest(n ->
                        log.info("numbers requested={}", n))
                .log("example.tracing.source")
                .map(value -> value * 10)
                .doOnNext(value ->
                        log.info("mapped value={}", value))
                .doOnEach(signal -> logSignal("numbers", signal))
                .doOnComplete(() ->
                        log.info("numbers completed"))
                .doFinally(type ->
                        log.info("numbers finally={}", type))
                .checkpoint("SignalTraceService.numbers");
    }

    public Flux<Integer> failure() {
        return Flux.just(1, 2)
                .concatWith(Flux.error(
                        new IllegalStateException("demo failure")))
                .doOnNext(value ->
                        log.info("before error value={}", value))
                .doOnError(error ->
                        log.warn("failure pipeline error", error))
                .doFinally(type ->
                        log.info("failure finally={}", type))
                .checkpoint("SignalTraceService.failure");
    }

    public Flux<Long> events() {
        return Flux.interval(Duration.ofMillis(250))
                .doOnRequest(n ->
                        log.info("events requested={}", n))
                .doOnNext(value ->
                        log.debug("event sequence={}", value))
                .doOnCancel(() ->
                        log.info("events cancelled"))
                .doFinally(type ->
                        log.info("events finally={}", type));
    }

    public Flux<Integer> withTraceId(String traceId) {
        return Flux.range(1, 2)
                .doOnEach(signal -> {
                    if (signal.isOnNext()) {
                        String id = signal.getContextView()
                                .getOrDefault("traceId", "unknown");
                        log.info("trace={} value={}", id, signal.get());
                    }
                })
                .contextWrite(context ->
                        context.put("traceId", traceId));
    }

    private void logSignal(String pipeline, Signal<Integer> signal) {
        if (signal.isOnNext()) {
            log.info("{} onNext={}", pipeline, signal.get());
        } else if (signal.isOnError()) {
            log.warn("{} onError", pipeline, signal.getThrowable());
        } else if (signal.isOnComplete()) {
            log.info("{} onComplete", pipeline);
        }
    }
}
~~~

log() nằm trước map nên quan sát giá trị nguồn 1, 2, 3, 4. doOnNext nằm sau map nên log 10, 20, 30, 40. Vị trí này cố ý cho thấy cách đặt operator làm thay đổi góc quan sát.

doOnEach ở sau map nên nhìn thấy giá trị đã biến đổi. doFinally ghi lại complete/error/cancel. Phương thức events() là stream vô hạn; khi browser ngắt kết nối, cancellation được truyền ngược lên pipeline.

### 10.5. SignalTraceController.java

~~~java
package example.tracing;

import org.springframework.http.MediaType;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Flux;

@RestController
@RequestMapping("/debug")
public class SignalTraceController {

    private final SignalTraceService service;

    public SignalTraceController(SignalTraceService service) {
        this.service = service;
    }

    @GetMapping("/numbers")
    public Flux<Integer> numbers() {
        return service.numbers();
    }

    @GetMapping("/failure")
    public Flux<Integer> failure() {
        return service.failure();
    }

    @GetMapping(
            path = "/events",
            produces = MediaType.TEXT_EVENT_STREAM_VALUE
    )
    public Flux<ServerSentEvent<Long>> events() {
        return service.events()
                .map(value -> ServerSentEvent.<Long>builder(value)
                        .id(Long.toString(value))
                        .event("tick")
                        .build());
    }

    @GetMapping("/context")
    public Flux<Integer> context(
            @RequestHeader(
                    name = "X-Trace-Id",
                    defaultValue = "local"
            ) String traceId) {
        return service.withTraceId(traceId);
    }
}
~~~

Controller trả Publisher trực tiếp; không subscribe hoặc block. Spring WebFlux quản lý subscription theo lifecycle của HTTP request. Với /debug/events, khi browser/curl đóng stream, cancellation có thể đi tới doOnCancel và doFinally.

### 10.6. SignalTraceServiceTest.java

~~~java
package example.tracing;

import java.time.Duration;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.atomic.AtomicLong;
import java.util.concurrent.atomic.AtomicReference;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.core.publisher.SignalType;
import reactor.test.StepVerifier;
import reactor.util.context.Context;

import static org.assertj.core.api.Assertions.assertThat;

class SignalTraceServiceTest {

    private SignalTraceService service;

    @BeforeEach
    void setUp() {
        service = new SignalTraceService();
    }

    @Test
    void emitsMappedNumbersAndCompletes() {
        StepVerifier.create(service.numbers())
                .expectNext(10, 20, 30, 40)
                .verifyComplete();
    }

    @Test
    void logsErrorWithoutConsumingIt() {
        StepVerifier.create(service.failure())
                .expectNext(1, 2)
                .expectErrorMessage("demo failure")
                .verify();
    }

    @Test
    void doOnEachObservesNextAndComplete() {
        List<String> observed = new ArrayList<>();

        Flux<Integer> source = Flux.just(7, 8)
                .doOnEach(signal -> {
                    if (signal.isOnNext()) {
                        observed.add("next:" + signal.get());
                    } else if (signal.isOnComplete()) {
                        observed.add("complete");
                    }
                });

        StepVerifier.create(source)
                .expectNext(7, 8)
                .verifyComplete();

        assertThat(observed)
                .containsExactly("next:7", "next:8", "complete");
    }

    @Test
    void doOnSuccessReceivesNullForEmptyMono() {
        AtomicReference<String> observed = new AtomicReference<>("unset");

        Mono<String> empty = Mono.<String>empty()
                .doOnSuccess(observed::set);

        StepVerifier.create(empty)
                .verifyComplete();

        assertThat(observed.get()).isNull();
    }

    @Test
    void doOnRequestObservesDemand() {
        AtomicLong requested = new AtomicLong();

        Flux<Integer> source = Flux.range(1, 5)
                .doOnRequest(requested::set);

        StepVerifier.create(source, 0)
                .thenRequest(2)
                .expectNext(1, 2)
                .thenCancel()
                .verify();

        assertThat(requested.get()).isEqualTo(2);
    }

    @Test
    void doFinallyObservesCancellation() {
        AtomicReference<SignalType> finalSignal =
                new AtomicReference<>();

        Flux<Long> source = Flux.interval(Duration.ofMillis(10))
                .doFinally(finalSignal::set);

        StepVerifier.create(source)
                .expectNext(0L)
                .thenCancel()
                .verify();

        assertThat(finalSignal.get()).isEqualTo(SignalType.CANCEL);
    }

    @Test
    void doOnEachCanReadReactorContext() {
        AtomicReference<String> observedTraceId =
                new AtomicReference<>();

        Flux<Integer> source = Flux.just(1)
                .doOnEach(signal -> {
                    if (signal.isOnNext()) {
                        observedTraceId.set(
                                signal.getContextView()
                                        .get("traceId"));
                    }
                })
                .contextWrite(Context.of("traceId", "req-42"));

        StepVerifier.create(source)
                .expectNext(1)
                .verifyComplete();

        assertThat(observedTraceId.get()).isEqualTo("req-42");
    }
}
~~~

Test doOnSuccessReceivesNullForEmptyMono chỉ subscribe publisher có callback; vì thế callback được gọi và giá trị quan sát là null.

### 10.7. application.yml

~~~yaml
spring:
  application:
    name: reactor-signal-tracing

logging:
  level:
    root: INFO
    example.tracing: DEBUG
    example.tracing.source: INFO
~~~

Mức log DEBUG cho package service giúp nhìn giá trị event. Trong production nên đặt mức theo nhu cầu và không bật trace toàn bộ mọi request nếu lưu lượng lớn.

### 10.8. Chạy ứng dụng và kiểm tra

Tại thư mục chứa pom.xml:

~~~bash
mvn test
~~~

Khởi động:

~~~bash
mvn spring-boot:run
~~~

Gọi pipeline bình thường:

~~~bash
curl -i http://localhost:8080/debug/numbers
~~~

Response body dự kiến:

~~~json
[10,20,30,40]
~~~

Log sẽ cho thấy subscription, demand, signal từ log() trước map, các giá trị sau map và terminal signal. Dòng log thực tế có timestamp, thread, logger name và format tùy cấu hình backend.

Kiểm tra error:

~~~bash
curl -i http://localhost:8080/debug/failure
~~~

Response sẽ kết thúc bằng lỗi HTTP server; log doOnError ghi exception demo failure. Việc log không làm lỗi biến mất.

Kiểm tra Reactor Context:

~~~bash
curl -i -H "X-Trace-Id: req-42" \
  http://localhost:8080/debug/context
~~~

Body:

~~~json
[1,2]
~~~

Log service có trace ID req-42 khi doOnEach đọc ContextView.

Kiểm tra cancellation của stream:

~~~bash
curl -N http://localhost:8080/debug/events
~~~

Sau khi nhận một vài event, nhấn Ctrl+C. Subscription bị hủy; log có thể ghi events cancelled và events finally=CANCEL.

Không coi timestamp/thread name trong log là output cố định. Chúng phụ thuộc runtime, scheduler, connector và logging pattern. Body HTTP ở ví dụ trên là kết quả theo code demo.

## 11. Đọc log theo tình huống thực tế

### 11.1. Không thấy bất kỳ log doOn nào

Kiểm tra:

- Có subscriber thực sự subscribe không?
- Controller có trả Publisher cho WebFlux hay đã bỏ quên kết quả?
- Có Mono.never() hoặc publisher không phát tín hiệu?
- Có nhánh filter/empty khiến doOnNext không chạy?
- Có đang chờ một nguồn hot đã phát xong trước subscription?

Đừng thêm subscribe() ngay lập tức. Trước hết xác định ai sở hữu lifecycle của Publisher.

### 11.2. Có subscribe nhưng không có onNext

Kiểm tra:

- Nguồn có phát giá trị không?
- Subscriber đã request chưa?
- Operator có buffer/prefetch và đang chờ demand?
- filter, filterWhen, switchIfEmpty có loại phần tử không?
- Publisher là Mono.empty() hay Flux.empty()?

Đặt doOnRequest và doOnNext ở hai phía của operator đáng nghi để khoanh vùng.

### 11.3. Có onNext nhưng không có complete

Có thể:

- Nguồn là stream vô hạn như Flux.interval.
- Connection vẫn đang mở và chờ dữ liệu.
- Downstream không cancel.
- Nguồn bị treo do một dependency không phát terminal signal.
- Pipeline đang chờ một inner publisher chưa hoàn tất.

Với stream lâu dài, không có onComplete có thể là hành vi bình thường. Theo dõi idle timeout, heartbeat, cancellation và session duration.

### 11.4. Chỉ thấy doFinally=CANCEL

Đây có thể là bình thường khi:

- Browser đóng tab.
- Client hủy HTTP request.
- take(n) nhận đủ phần tử rồi cancel upstream.
- StepVerifier gọi thenCancel().
- Timeout hoặc switch-to-fallback hủy nguồn cũ.

Không mặc định coi cancel là lỗi. Cần đối chiếu với request lifecycle và metric disconnect.

### 11.5. Có log error nhưng HTTP response khác dự kiến

onErrorResume, retry hoặc exception handler có thể thay đổi kết quả sau vị trí log. Đặt log trước và sau operator phục hồi để thấy:

- Lỗi gốc.
- Số lần retry.
- Fallback được gọi.
- Kết quả cuối cùng.

Nếu log nằm trước onErrorResume, nó có thể ghi error dù client cuối cùng nhận HTTP 200 từ fallback. Đây là hành vi hợp lệ.

## 12. Lỗi phổ biến khi dùng doOn và log

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Nghĩ pipeline chạy ngay lúc khai báo | Không thấy log khi chưa có subscriber | Xác định subscription boundary |
| Gọi subscribe() trong controller | Framework không quản lý đầy đủ lifecycle của tác vụ phụ | Trả Mono/Flux cho WebFlux |
| Dùng doOnNext để biến đổi dữ liệu | Side effect không diễn đạt transformation | Dùng map/flatMap |
| Nghĩ doOnError xử lý xong lỗi | Error vẫn truyền downstream | Dùng onErrorResume/onErrorMap nếu cần |
| Chỉ log doOnComplete | Bỏ lỡ error và cancellation | Dùng doOnError và doFinally |
| Nghĩ cancel là complete | Đếm lifecycle sai | Phân biệt ON_COMPLETE, ON_ERROR và CANCEL |
| Dùng Mono.doOnSuccess cho empty mà không kiểm tra null | Log có giá trị null gây hiểu nhầm | Dùng doOnNext hoặc kiểm tra empty |
| Đặt log sai vị trí | Thấy giá trị trước/sau map khác mong đợi | Đặt log ở ranh giới operator cần quan sát |
| Nghĩ request(10) nghĩa là đã xử lý 10 record | Nhầm demand với emission | Đo onNext hoặc metric xử lý |
| Log mọi payload production | Log volume lớn và có thể lộ dữ liệu | Log metadata, redaction, sampling |
| Gọi logger/appender blocking trên event-loop | Tăng latency toàn pipeline | Dùng logging backend/appender phù hợp |
| Dùng MDC ThreadLocal mà không propagation | Trace ID mất hoặc lẫn giữa request | Dùng Reactor Context và context propagation |
| Gọi API blocking trong doOn | Chặn thread xử lý reactive | Compose Publisher hoặc chuyển blocking work sang scheduler phù hợp |
| Dựa vào thứ tự nhiều doFinally nối tiếp | Callback có thể chạy thứ tự ngược | Gom cleanup vào một callback hoặc resource abstraction |
| Dùng doOnDiscard như cleanup tổng quát | Operator không hỗ trợ discard thì hook không chạy | Kiểm tra discard support và đặt đúng vị trí |
| Bật Hooks.onOperatorDebug toàn production | Overhead assembly tracing | Chỉ bật trong debug/test có chủ đích |
| Cho rằng log() chỉ log onNext | Bỏ qua request, subscribe, error, complete, cancel | Đọc log signal theo đúng vị trí operator |

## 13. Checklist quan sát một pipeline

Khi một reactive chain có vấn đề, làm theo thứ tự:

1. Xác định ai subscribe vào Publisher.
2. Đặt doOnSubscribe để xác nhận subscription.
3. Đặt doOnRequest để xem demand.
4. Đặt log() tại ranh giới nguồn hoặc operator nghi ngờ.
5. Đặt doOnNext trước/sau filter/map để so sánh giá trị.
6. Dùng doOnEach nếu cần quan sát onNext/onError/onComplete hoặc Reactor Context.
7. Dùng doOnError để ghi lỗi gốc trước khi fallback.
8. Dùng doFinally để phân biệt complete/error/cancel.
9. Dùng checkpoint("meaningful-name") để bổ sung assembly marker.
10. Kiểm tra log có chứa token, cookie, PII hoặc payload nhạy cảm không.
11. Dùng StepVerifier để tái hiện tín hiệu trong test.
12. Tắt log/debug hook tạm thời sau khi điều tra và theo dõi lại latency.

## 14. Ghi nhớ

- Reactive pipeline được lắp ráp trước; cold source thường chỉ chạy khi có subscription.
- Reactive Streams có onSubscribe, onNext, onError, onComplete; request và cancel là thao tác điều khiển Subscription.
- doOnSubscribe quan sát Subscription; doOnRequest quan sát demand; doOnNext quan sát phần tử tại vị trí operator.
- doOnEach quan sát onNext/onError/onComplete dưới dạng Signal; dùng doOnRequest và doOnCancel cho demand/cancel.
- Mono.doOnSuccess chạy cả khi empty và nhận null; doOnNext chỉ chạy khi có giá trị.
- doOnError chỉ quan sát lỗi; onErrorResume hoặc onErrorMap mới thay đổi error flow.
- doOnTerminate và doAfterTerminate không bao phủ cancellation; doFinally bao phủ complete/error/cancel.
- log() ghi nhiều Reactive Streams signal tại vị trí operator; vị trí log quyết định dữ liệu quan sát.
- doOn... dành cho side effect nhanh, an toàn; dùng map/flatMap cho transformation và async business work.
- Dùng Reactor Context cho trace metadata; không giả định ThreadLocal/MDC tự truyền qua mọi scheduler.
- checkpoint() và Hooks.onOperatorDebug() hỗ trợ debug assembly nhưng có overhead khác nhau.
- Không log credential, token, cookie, CSRF token hoặc payload nhạy cảm; dùng metric/tracing cho quan sát dài hạn.

**Tài liệu chính thức:**
- [Project Reactor 3.7.17 — Reference Guide, Peeking into a Sequence](https://projectreactor.io/docs/core/3.7.17/reference/index.html)
- [Project Reactor 3.7.17 — Flux Javadoc](https://projectreactor.io/docs/core/3.7.17/api/reactor/core/publisher/Flux.html)
- [Project Reactor 3.7.17 — Mono Javadoc](https://projectreactor.io/docs/core/3.7.17/api/reactor/core/publisher/Mono.html)
- [Project Reactor — Debugging Reactor](https://projectreactor.io/docs/core/release/reference/debugging.html)
- [Project Reactor — Context](https://projectreactor.io/docs/core/release/reference/advancedFeatures/context.html)
- [Spring Framework 6.2 — WebFlux Reactive Core](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/reactive-spring.html)
- [Spring Boot 3.5 — Logging](https://docs.spring.io/spring-boot/3.5/reference/features/logging.html)
