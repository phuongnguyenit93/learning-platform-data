# Phân biệt thời điểm tạo Mono hoặc Flux với thời điểm đăng ký và thực thi

Trong Reactor, một phương thức trả về **Mono** hoặc **Flux** thường chỉ tạo ra một mô tả cho chuỗi xử lý. Việc gọi phương thức và nhận publisher không có nghĩa dữ liệu đã được tải, truy vấn đã được gửi hoặc tác vụ đã chạy xong. Với phần lớn publisher dạng cold, công việc chỉ bắt đầu khi có Subscriber đăng ký. Sau đó các tín hiệu mới đi qua chuỗi operator và có thể tiếp tục bất đồng bộ trên những thread khác nhau.

Sự khác biệt giữa **assembly time** (thời điểm lắp ráp publisher), **subscription time** (thời điểm đăng ký) và **signal time** (thời điểm phát tín hiệu) ảnh hưởng trực tiếp đến logic nghiệp vụ, số lần gọi hệ thống bên ngoài và cách đo metrics. Nếu đặt Timer quanh lời gọi tạo Mono, ứng dụng có thể chỉ đo thời gian lắp ráp chuỗi rồi kết thúc trước khi công việc thực tế bắt đầu.

## 1. Ba thời điểm trong vòng đời Reactor

Một chuỗi reactive thường trải qua ba giai đoạn:

| Giai đoạn | Điều gì xảy ra? | Ví dụ |
|---|---|---|
| Assembly time | Tạo publisher và nối các operator thành pipeline | Gọi Mono.defer, map, flatMap, timeout |
| Subscription time | Subscriber đăng ký; subscription được truyền ngược về source | Gọi subscribe hoặc framework WebFlux đăng ký publisher |
| Signal/execution time | Source phát onNext, onError hoặc onComplete; operator xử lý tín hiệu | Gửi HTTP request, đọc database, biến đổi dữ liệu |

Sơ đồ dưới đây minh họa thứ tự thường gặp với một cold publisher:

~~~mermaid
sequenceDiagram
    participant App as Mã ứng dụng
    participant P as Mono/Flux
    participant S as Subscriber
    participant Src as Source / Operator
    App->>P: Tạo publisher và nối operator
    Note over P: Assembly time - chưa chạy pipeline cold
    App-->>P: Trả publisher cho caller
    S->>P: subscribe()
    P->>Src: Truyền subscription ngược upstream
    Note over S,Src: Subscription time
    Src-->>S: onSubscribe
    Src->>Src: Thực thi công việc
    Src-->>S: onNext / onError / onComplete
    Note over S,Src: Signal time
~~~

Trong ứng dụng WebFlux, framework thường là bên đăng ký publisher sau khi controller trả về Mono hoặc Flux. Do đó method controller có thể đã return trong khi HTTP response body vẫn đang được tạo và gửi.

Không phải publisher nào cũng là cold hoặc đợi subscriber mới bắt đầu. Hot source, sink hoặc publisher đã được kết nối có thể phát dữ liệu độc lập với subscriber. Vì vậy, hãy xác định loại publisher và ranh giới công việc thực tế trước khi kết luận thời điểm thực thi.

## 2. Assembly time: tạo pipeline chưa đồng nghĩa thực thi

Các lời gọi như map, filter, flatMap, timeout và doOnNext thường tạo operator mới để mô tả cách xử lý tín hiệu. Lambda được truyền vào operator thường chưa chạy tại thời điểm lắp ráp.

~~~java
AtomicInteger mapped = new AtomicInteger();

Mono<Integer> result = Mono.just(10)
    .map(value -> {
        mapped.incrementAndGet();
        return value * 2;
    });

System.out.println(mapped.get()); // 0
~~~

Khi tạo result, Reactor đã có pipeline gồm source Mono.just và operator map. Hàm bên trong map chỉ chạy khi có subscription và source phát dữ liệu.

Tuy nhiên, biểu thức Java được truyền làm đối số vẫn được Java đánh giá ngay khi gọi phương thức. Đây là nguồn gốc của nhiều lỗi khi dùng Mono.just:

~~~java
Mono<Customer> customer = Mono.just(customerClient.loadCustomer(id));
~~~

Phương thức loadCustomer được gọi ngay trong lúc tạo publisher. Mono.just chỉ giữ lại kết quả đã có. Nếu loadCustomer thực hiện I/O đồng bộ, I/O đã xảy ra ở assembly time và có thể chặn thread đang tạo publisher.

Điều này không có nghĩa Mono.just phát onNext trước khi có subscriber. Subscriber vẫn cần đăng ký để nhận tín hiệu; phần xảy ra sớm là việc Java đánh giá biểu thức đối số và Mono chụp lại giá trị đó.

Tương tự, Flux.just nhận các giá trị đã được đánh giá trước khi gọi Flux.just:

~~~java
Flux<String> names = Flux.just(loadName(1), loadName(2), loadName(3));
~~~

Ba lời gọi loadName chạy ngay khi biểu thức trên được thực thi. Flux chỉ phát lại các giá trị đã được tạo khi có subscriber.

## 3. Subscription time: khi nào công việc bắt đầu?

Với cold publisher, mỗi subscriber mới kích hoạt một lần đăng ký vào source. Các factory như fromCallable, fromSupplier và defer cho phép trì hoãn việc tạo giá trị hoặc publisher đến subscription.

~~~java
Mono<Customer> customer = Mono.fromCallable(
    () -> customerClient.loadCustomer(id)
);
~~~

Ở đây lambda chưa được gọi khi tạo Mono. Khi subscriber đăng ký, Reactor gọi Callable để tạo kết quả. Nếu không có subscriber, phương thức loadCustomer không chạy.

Dùng defer khi cần trì hoãn cả việc tạo publisher con:

~~~java
Mono<Customer> customer = Mono.defer(
    () -> customerClient.loadCustomerReactive(id)
);
~~~

Supplier của defer được gọi cho mỗi subscriber. Publisher được trả về từ supplier sau đó được đăng ký để chạy chuỗi xử lý thực tế.

Có thể so sánh ba cách:

| Cách tạo | Khi biểu thức nguồn chạy | Mỗi subscriber có chạy lại không? |
|---|---|---|
| Mono.just(load()) | Ngay lúc assembly | Không; mọi subscriber nhận giá trị đã chụp |
| Mono.fromCallable(() -> load()) | Khi source được subscribe | Có, với mỗi subscription độc lập |
| Mono.defer(() -> createMono()) | Supplier tạo Mono chạy khi subscribe | Có, mỗi subscription nhận publisher được tạo mới |

Ví dụ đếm số lần gọi:

~~~java
AtomicInteger calls = new AtomicInteger();

Mono<Integer> eager = Mono.just(calls.incrementAndGet());
Mono<Integer> lazy = Mono.fromCallable(calls::incrementAndGet);
Mono<Integer> deferred = Mono.defer(
    () -> Mono.just(calls.incrementAndGet())
);
~~~

Sau khi tạo ba biến trên, calls đã tăng một lần vì eager gọi increment ngay. Hai publisher còn lại chưa gọi increment. Mỗi lần subscribe vào lazy hoặc deferred sẽ làm bộ đếm tăng thêm một lần.

## 4. fromCallable và defer không tự làm công việc trở thành bất đồng bộ

Trì hoãn thực thi đến subscription không có nghĩa công việc tự chạy trên thread nền. Mono.fromCallable chạy Callable trên thread thực hiện subscription, trừ khi pipeline được chỉ định Scheduler phù hợp.

Nếu Callable gọi API blocking, có thể chuyển source sang boundedElastic:

~~~java
Mono<Customer> customer = Mono.fromCallable(
        () -> blockingCustomerClient.load(id)
    )
    .subscribeOn(Schedulers.boundedElastic());
~~~

subscribeOn tác động đến quá trình subscription và source upstream. Nó không biến API blocking thành non-blocking; nó chỉ chuyển công việc blocking sang Scheduler phù hợp hơn để tránh chặn event-loop.

publishOn có vai trò khác: nó chuyển việc xử lý các tín hiệu downstream kể từ vị trí operator đó sang Scheduler được chọn.

~~~java
Mono<String> result = customer
    .publishOn(Schedulers.parallel())
    .map(Customer::displayName);
~~~

Không cần thêm subscribeOn hoặc publishOn chỉ để “kích hoạt” một publisher. Subscription mới là điều kích hoạt cold source; Scheduler chỉ quyết định nơi các phần của pipeline thực thi.

## 5. Signal time: dữ liệu đi qua pipeline như thế nào?

Sau khi subscription được thiết lập, source có thể phát một hoặc nhiều tín hiệu:

- **onNext**: có phần tử dữ liệu mới.
- **onError**: chuỗi kết thúc do lỗi.
- **onComplete**: chuỗi kết thúc bình thường.
- **cancel**: subscriber yêu cầu hủy subscription; đây là tín hiệu điều khiển đi ngược về upstream, không phải kết quả thành công.

Mono phát tối đa một phần tử rồi kết thúc, hoặc hoàn tất rỗng, hoặc phát lỗi. Flux có thể phát nhiều phần tử trước khi kết thúc. Với source bất đồng bộ như WebClient, tín hiệu có thể đến sau một khoảng thời gian và trên thread khác.

~~~java
Flux<String> names = Flux.just("an", "binh", "chi")
    .doOnSubscribe(subscription -> log.info("Đã đăng ký"))
    .map(String::toUpperCase)
    .doOnNext(name -> log.info("Nhận được {}", name))
    .doOnComplete(() -> log.info("Hoàn tất"));
~~~

Các callback doOnSubscribe, doOnNext và doOnComplete chỉ được gọi khi có subscription và các tín hiệu tương ứng xảy ra. Tạo biến names không in ra log nào.

Backpressure cũng ảnh hưởng đến nhịp phát dữ liệu. Subscriber có thể yêu cầu một số phần tử nhất định; source tuân thủ demand sẽ phát theo số lượng được yêu cầu. Vì vậy, khoảng thời gian giữa subscription và tín hiệu đầu tiên có thể chứa thời gian chờ demand, lập lịch hoặc I/O.

## 6. Cold publisher và hot publisher

Cold publisher thường tạo dữ liệu mới cho từng subscriber. Ví dụ:

~~~java
Flux<Integer> numbers = Flux.range(1, 3)
    .doOnNext(value -> log.info("Tạo {}", value));

numbers.subscribe(value -> log.info("Subscriber A: {}", value));
numbers.subscribe(value -> log.info("Subscriber B: {}", value));
~~~

Pipeline chạy hai lần. Mỗi subscriber nhận các phần tử 1, 2, 3 và doOnNext được gọi ba lần cho từng subscription.

Hot publisher có thể phát dữ liệu mà không phụ thuộc số lượng subscriber. Subscriber đến muộn có thể chỉ nhận những phần tử được phát sau khi nó đăng ký.

~~~java
Sinks.Many<String> sink =
    Sinks.many().multicast().directBestEffort();

Flux<String> events = sink.asFlux();

events.subscribe(value -> log.info("A: {}", value));
sink.tryEmitNext("created").orThrow();

events.subscribe(value -> log.info("B: {}", value));
sink.tryEmitNext("updated").orThrow();
~~~

Subscriber A nhận cả created và updated. Subscriber B chỉ nhận updated vì nó đăng ký sau khi sự kiện created đã được phát.

Không nên giả định mọi Mono hoặc Flux đều là cold. Một số operator thay đổi hành vi chia sẻ:

| Operator hoặc nguồn | Hành vi quan trọng |
|---|---|
| Mono.just / Flux.just | Chụp sẵn giá trị tại assembly rồi phát cho subscriber |
| Mono.defer / Flux.defer | Tạo source con theo từng subscription |
| share() | Chia sẻ một subscription upstream giữa các subscriber đồng thời sau khi kết nối |
| cache() | Giữ và phát lại tín hiệu đã nhận cho subscriber sau |
| replay() | Có thể phát lại một phần hoặc toàn bộ tín hiệu đã phát |
| Sinks.Many | Cho phép đẩy tín hiệu vào publisher theo chính sách sink |

share và cache làm thay đổi số lần công việc upstream chạy. Một publisher đã được chia sẻ có thể chỉ gọi hệ thống bên ngoài một lần dù có nhiều subscriber.

## 7. Nhiều subscriber có thể làm metrics tăng nhiều lần

Với cold publisher, mỗi subscription thường là một lần thực thi mới. Nếu cùng một Mono được subscribe hai lần, lời gọi HTTP hoặc database bên trong có thể chạy hai lần.

~~~java
AtomicInteger requests = new AtomicInteger();

Mono<String> source = Mono.fromCallable(() -> {
    requests.incrementAndGet();
    return "ok";
});

source.subscribe();
source.subscribe();
~~~

requests bằng 2 sau hai subscription. Nếu instrumentation đặt trong pipeline cold, metrics cũng thường được ghi hai lần.

Với publisher đã cache, source có thể chỉ thực thi một lần nhưng nhiều subscriber vẫn nhận kết quả đã cache. Cần phân biệt hai câu hỏi:

- Muốn đo số lần công việc upstream thực sự chạy?
- Muốn đo số subscriber đã nhận hoặc chờ kết quả?

Đặt instrumentation **trước share/cache** để đo vòng đời thực thi upstream. Đặt instrumentation **sau share/cache** để đo từng subscription downstream. Vị trí operator quyết định ý nghĩa của số liệu.

Ví dụ:

~~~java
Mono<Result> sharedWork = Mono.defer(() -> {
    Timer.Sample sample = Timer.start(registry);

    return Mono.defer(() -> client.fetchResult())
        .doFinally(signal -> sample.stop(
            registry.timer("remote.work.duration")
        ));
}).cache();
~~~

Timer ở đây đo lần thực thi upstream mà cache chia sẻ. Subscriber đến sau và nhận kết quả đã lưu không tạo một lần đo mới cho remote work.

Nếu cần đo thời gian mỗi subscriber chờ kết quả, hãy bọc sharedWork ở phía downstream bằng một ranh giới đo riêng.

## 8. Vì sao Timer quanh method trả Mono có thể đo sai?

Xét một service method:

~~~java
public Mono<Order> findOrder(String id) {
    Timer.Sample sample = Timer.start(registry);

    Mono<Order> result = repository.findById(id);

    sample.stop(registry.timer("orders.lookup.duration"));
    return result;
}
~~~

Timer dừng ngay sau khi repository trả về publisher. Với cold reactive source, truy vấn database có thể chưa được đăng ký. Số liệu thu được chủ yếu phản ánh thời gian lắp ráp publisher, không phải thời gian truy vấn và nhận kết quả.

Đây là vấn đề khi dùng cách đo imperative quanh method trả Mono hoặc Flux. AOP aspect bao quanh lời gọi method cũng có thể chỉ nhìn thấy method tạo publisher rồi return. Không giả định một Timer hoặc @Timed thông thường tự chờ reactive pipeline kết thúc.

Tài liệu API của Micrometer mô tả rõ trường hợp @Timed chờ một method trả về CompletionStage hoàn tất. Mono và Flux triển khai Reactive Streams Publisher, không phải CompletionStage; vì vậy không suy rộng bảo đảm đó sang Reactor. Nếu muốn đo đến terminal signal hoặc cancellation của Mono/Flux, hãy gắn Timer hoặc Observation vào chính publisher như các ví dụ bên dưới, hoặc dùng instrumentation reactive do framework cung cấp.

Spring WebFlux có thể tự tạo Observation cho vòng đời HTTP server request. Observation đó đo request ở tầng web, bao gồm thời gian xử lý reactive response theo tích hợp của framework. Nó không nhất thiết đại diện cho một thao tác nghiệp vụ cụ thể bên trong service. Nếu cần đo riêng thao tác nghiệp vụ, hãy gắn instrumentation vào publisher tại ranh giới phù hợp.

## 9. Đo toàn bộ vòng đời một subscription bằng Timer

Để đo thời gian từ lúc subscription bắt đầu đến khi publisher hoàn tất, đặt Timer.Sample bên trong defer và dừng bằng doFinally:

~~~java
public Mono<Customer> findCustomer(String id) {
    return Mono.defer(() -> {
        Timer.Sample sample = Timer.start(registry);

        return Mono.defer(() -> customerClient.findReactive(id))
            .doFinally(signalType -> {
                String outcome = switch (signalType) {
                    case ON_COMPLETE -> "complete";
                    case ON_ERROR -> "error";
                    case CANCEL -> "cancelled";
                    default -> "other";
                };

                sample.stop(
                    registry.timer(
                        "customer.lookup.duration",
                        "outcome", outcome
                    )
                );
            });
    });
}
~~~

Mono.defer tạo một sample riêng cho mỗi subscription. doFinally được gọi khi subscription kết thúc bình thường, bằng lỗi hoặc bị hủy. Nhờ đó Timer ghi nhận cả thời gian chờ I/O và xử lý trong pipeline.

Lớp Mono.defer bên trong cũng có chủ đích: nếu phương thức tạo publisher ném exception đồng bộ trước khi trả Mono, Reactor chuyển exception đó thành onError. doFinally bên ngoài vẫn nhận được tín hiệu lỗi và dừng sample. Cùng nguyên tắc này được dùng trong ví dụ Flux và Observation.

Các giá trị outcome có tập hữu hạn: complete, error, cancelled và other. Không đưa exception message, request ID hoặc customer ID vào tag.

Với Flux, cách đo tương tự ghi một thời lượng cho toàn bộ subscription, không phải một thời lượng cho từng phần tử:

~~~java
public Flux<Event> streamEvents() {
    return Flux.defer(() -> {
        Timer.Sample sample = Timer.start(registry);

        return Flux.defer(() -> eventClient.stream())
            .doFinally(signalType -> {
                sample.stop(
                    registry.timer(
                        "events.stream.duration",
                        "termination", normalize(signalType)
                    )
                );
            });
    });
}
~~~

Một Flux có thể phát hàng nghìn phần tử nhưng Timer vẫn chỉ ghi một lần khi subscription kết thúc. Nếu muốn đếm phần tử, dùng Counter trong doOnNext:

~~~java
return eventClient.stream()
    .doOnNext(event -> eventsReceived.increment());
~~~

Không dùng doOnNext để dừng Timer toàn stream, vì như vậy chỉ đo đến phần tử đầu tiên hoặc mỗi phần tử lại tạo một lần đo không đúng mục tiêu.

## 10. Hủy subscription là một kết quả riêng

doFinally nhận cả ba kiểu kết thúc chính: ON_COMPLETE, ON_ERROR và CANCEL. Hủy subscription không đồng nghĩa với thành công hoặc lỗi nghiệp vụ.

Ví dụ, client HTTP có thể ngừng chờ vì người dùng đóng kết nối. Flux bị cancel và source có thể dừng việc đọc dữ liệu. Nếu metrics chỉ có success/failure, việc gộp cancellation vào success sẽ làm sai cách diễn giải.

Nên phân loại rõ:

| SignalType | Diễn giải | Ví dụ outcome |
|---|---|---|
| ON_COMPLETE | Publisher hoàn tất bình thường | complete |
| ON_ERROR | Publisher kết thúc do lỗi | error |
| CANCEL | Subscriber chủ động hủy | cancelled |

Nếu chỉ quan tâm thời gian các lần hoàn tất bình thường, có thể ghi Timer ở nhánh complete và ghi riêng Counter cho cancellation. Nếu cần thời gian mọi subscription, hãy ghi cả ba outcome như ví dụ trước.

Lưu ý doFinally chạy sau khi terminal signal đã được chuyển xuống downstream. Trong test, callback có thể chạy ngay sau khi StepVerifier nhận tín hiệu cuối; nếu kiểm tra side effect của callback, cần đồng bộ hoặc chờ điều kiện thay vì giả định callback luôn chạy trước khi verifyComplete trả về.

## 11. LongTaskTimer cho publisher chạy lâu hoặc không kết thúc

Timer chỉ ghi thời lượng khi subscription kết thúc. Với Flux dài hạn hoặc stream có thể chạy vô thời hạn, dashboard không thấy thời lượng hiện tại nếu chỉ dùng Timer.

Có thể dùng LongTaskTimer để theo dõi các subscription đang active:

~~~java
public Flux<Message> consumeMessages() {
    return Flux.defer(() -> {
        LongTaskTimer.Sample active = activeStreams.start();

        return Flux.defer(() -> messageClient.consume())
            .doFinally(signalType -> active.stop());
    });
}
~~~

Mỗi subscription bắt đầu một sample LongTaskTimer. Trong lúc stream còn chạy, registry công bố activeTasks, duration và max. Khi stream hoàn tất, phát lỗi hoặc bị hủy, sample được dừng và không còn nằm trong tập active.

LongTaskTimer không lưu lịch sử thời lượng đã hoàn tất. Nếu cần phân tích thời gian của các stream sau khi kết thúc, kết hợp với Timer riêng.

## 12. Retry làm thay đổi ranh giới đo

retry tạo subscription mới vào upstream. Vì vậy vị trí đặt instrumentation quyết định đo từng attempt hay toàn bộ thao tác logic.

Đo từng attempt:

~~~java
Mono<Result> oneAttempt = Mono.defer(() -> {
    Timer.Sample sample = Timer.start(registry);

    return Mono.defer(() -> client.call())
        .doFinally(signal -> sample.stop(
            registry.timer("client.call.attempt.duration")
        ));
});

return oneAttempt.retry(2);
~~~

Mỗi lần retry resubscribe vào oneAttempt, tạo sample mới. Timer ghi một lần cho từng attempt, kể cả attempt lỗi trước khi retry.

Đo toàn bộ thao tác bao gồm retry:

~~~java
return Mono.defer(() -> {
    Timer.Sample sample = Timer.start(registry);

    return Mono.defer(() -> client.call())
        .retry(2)
        .doFinally(signal -> sample.stop(
            registry.timer("client.call.operation.duration")
        ));
});
~~~

Ở đây doFinally nằm sau retry, nên chỉ ghi một lần cho toàn bộ subscription logic sau khi retry hoàn tất, thất bại hoặc bị cancel.

Hai phép đo trả lời câu hỏi khác nhau:

- Attempt duration giúp biết từng lần gọi phụ thuộc bên ngoài chậm hay lỗi ra sao.
- Operation duration giúp biết người dùng phải chờ bao lâu cho cả quy trình có retry.

Có thể giữ cả hai nếu tên meter thể hiện rõ ý nghĩa và tag outcome được giới hạn.

## 13. Observation và Reactor Context

Micrometer Observation cho phép ghi nhận vòng đời một thao tác để nhiều ObservationHandler có thể tạo metrics, tracing hoặc log. Với reactive pipeline, Observation cần bắt đầu khi subscription bắt đầu và dừng khi publisher kết thúc.

~~~java
public Mono<Product> findProduct(String id) {
    return Mono.defer(() -> {
        Observation observation = Observation
            .createNotStarted("catalog.product.lookup", observationRegistry)
            .lowCardinalityKeyValue("operation", "lookup")
            .start();

        return Mono.defer(() -> productClient.find(id))
            .doOnError(observation::error)
            .doFinally(signalType -> observation.stop());
    });
}
~~~

Observation được tạo bên trong defer, vì vậy mỗi subscription có một vòng đời riêng. doOnError ghi nhận lỗi; doFinally dừng Observation cho complete, error hoặc cancel. ObservationHandler đã đăng ký trong ObservationRegistry quyết định metrics hoặc tracing nào được tạo.

Reactor Context là nơi phù hợp để gắn dữ liệu theo subscription như correlation ID hoặc Observation. Context không phải ThreadLocal toàn cục. Nó gắn với Subscriber và được truyền theo cơ chế subscription từ downstream ngược lên upstream.

~~~java
Mono<String> result = Mono.deferContextual(context -> {
    String requestId = context.get("requestId");
    return Mono.just("request=" + requestId);
});

StepVerifier.create(
        result.contextWrite(context -> context.put("requestId", "req-42"))
    )
    .expectNext("request=req-42")
    .verifyComplete();
~~~

Không giả định ThreadLocal hoặc MDC tự động đi theo mọi lần đổi Scheduler. Nếu ứng dụng cần cầu nối từ Reactor Context sang ThreadLocal để tích hợp thư viện cũ, hãy dùng Micrometer Context Propagation và kiểm tra cấu hình theo phiên bản. Với Reactor 3.5.3 trở lên, có thể bật automatic context propagation bằng Hooks.enableAutomaticContextPropagation(); tính năng này cần các phiên bản Micrometer Context Propagation và Micrometer tương thích. Không bật hook chỉ vì đang dùng Mono hoặc Flux; hãy xác định nhu cầu truyền context và đánh giá chi phí.

Tài liệu Micrometer hiện nêu các mức tối thiểu cho hook này là Reactor 3.5.3, Micrometer Context Propagation 1.0.3, Micrometer 1.10.8 và Micrometer Tracing 1.0.7. Các dự án nên đồng bộ phiên bản qua BOM tương thích và kiểm tra lại hướng dẫn khi nâng cấp.

## 14. Không tự subscribe trong service

Một lỗi phổ biến là gọi subscribe bên trong service rồi trả về một publisher khác hoặc trả void:

~~~java
public void refresh() {
    repository.loadAll()
        .doOnNext(this::update)
        .subscribe();
}
~~~

Cách này tạo một subscription độc lập do service tự quản lý. Caller không còn kiểm soát trực tiếp cancellation, error handling, backpressure hoặc thời điểm hoàn tất của công việc đó. Trong WebFlux, nó cũng có thể làm mất liên kết với request lifecycle và Reactor Context.

Thông thường nên trả publisher để framework hoặc tầng gọi quyết định subscribe:

~~~java
public Mono<Void> refresh() {
    return repository.loadAll()
        .doOnNext(this::update)
        .then();
}
~~~

Subscriber ở tầng trên có thể kết hợp timeout, retry, cancellation và Observation trên cùng một chuỗi. Trong test, StepVerifier hoặc block có kiểm soát có thể tạo subscription. Trong WebFlux handler, để framework đăng ký publisher thay vì tự subscribe.

## 15. Kiểm thử assembly và subscription bằng StepVerifier

StepVerifier giúp kiểm tra publisher mà không cần tự quản lý callback phức tạp. Một kiểm thử quan trọng là xác nhận publisher cold chưa thực thi khi được tạo:

~~~java
@Test
void fromCallableRunsOnlyAfterSubscription() {
    AtomicInteger calls = new AtomicInteger();

    Mono<Integer> source =
        Mono.fromCallable(calls::incrementAndGet);

    assertEquals(0, calls.get());

    StepVerifier.create(source)
        .expectNext(1)
        .verifyComplete();

    assertEquals(1, calls.get());

    StepVerifier.create(source)
        .expectNext(2)
        .verifyComplete();

    assertEquals(2, calls.get());
}
~~~

Kiểm thử cho Mono.just cho thấy giá trị được chụp ngay khi assembly:

~~~java
@Test
void justCapturesValueAtAssemblyTime() {
    AtomicInteger calls = new AtomicInteger();

    Mono<Integer> source = Mono.just(calls.incrementAndGet());

    assertEquals(1, calls.get());

    StepVerifier.create(source)
        .expectNext(1)
        .verifyComplete();

    StepVerifier.create(source)
        .expectNext(1)
        .verifyComplete();

    assertEquals(1, calls.get());
}
~~~

Kiểm thử cho defer xác nhận publisher con được tạo cho từng subscription:

~~~java
@Test
void deferCreatesSourceForEachSubscriber() {
    AtomicInteger calls = new AtomicInteger();

    Mono<Integer> source = Mono.defer(
        () -> Mono.just(calls.incrementAndGet())
    );

    assertEquals(0, calls.get());

    StepVerifier.create(source)
        .expectNext(1)
        .verifyComplete();

    StepVerifier.create(source)
        .expectNext(2)
        .verifyComplete();

    assertEquals(2, calls.get());
}
~~~

Ngoài ra, nên kiểm tra cancellation và nhiều subscriber:

- Publisher cold thực hiện source một lần cho mỗi subscription.
- Publisher shared chỉ thực hiện upstream theo quy tắc kết nối và chia sẻ.
- Cache phát lại kết quả đã lưu mà không gọi lại source.
- Cancel kích hoạt doFinally với SignalType.CANCEL.
- Retry tạo lại subscription upstream theo số lần thử.
- Timer hoặc Observation bắt đầu ở subscription và dừng ở terminal/cancel.
- Reactor Context vẫn đọc được sau khi pipeline chuyển Scheduler.

Khi kiểm tra doFinally, nhớ callback chạy sau khi terminal signal được chuyển downstream. Dùng cơ chế đồng bộ phù hợp nếu assertion phụ thuộc vào side effect trong callback.

## 16. Những lỗi thường gặp

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Gọi I/O trong đối số Mono.just | I/O chạy ngay ở assembly và có thể block thread | Dùng fromCallable, fromSupplier hoặc defer |
| Nghĩ fromCallable tự chạy trên thread nền | Callable có thể chạy trên thread subscribe | Chọn Scheduler phù hợp bằng subscribeOn |
| Nghĩ tạo Mono là đã thực thi | Công việc cold có thể chưa chạy vì không có subscriber | Xác định ai subscribe và thời điểm subscribe |
| Đo Timer quanh method trả Mono | Chỉ đo thời gian tạo publisher | Đặt Timer.Sample trong defer và dừng ở doFinally |
| Đo Flux bằng Timer cho từng phần tử | Đếm sai số lần thực thi và thời lượng | Timer một lần cho subscription; Counter cho từng onNext |
| Không tính cancellation | Bỏ sót thời gian subscription bị hủy | Phân loại SignalType.CANCEL |
| Gắn instrumentation sai phía share/cache | Đo subscriber thay vì upstream hoặc ngược lại | Chọn ranh giới trước/sau operator chia sẻ |
| Đặt Timer trước retry nhưng tưởng đo toàn operation | Mỗi attempt tạo một phép đo riêng | Đặt instrumentation sau retry nếu muốn đo toàn operation |
| Tự subscribe trong service | Mất quyền kiểm soát lifecycle ở caller | Trả Mono/Flux để tầng trên subscribe |
| Dùng ThreadLocal như context toàn cục | Context có thể mất khi đổi Scheduler | Dùng Reactor Context và Micrometer Context Propagation |
| Chỉ dùng Timer cho stream vô hạn | Không có số đo cho đến khi stream kết thúc hoặc cancel | Dùng LongTaskTimer cho trạng thái active |

## 17. Checklist instrumentation reactive

- [ ] Phân biệt rõ assembly time, subscription time và signal time.
- [ ] Kiểm tra các biểu thức Java được đánh giá ngay khi tạo Mono/Flux.
- [ ] Dùng fromCallable/fromSupplier/defer cho công việc cần trì hoãn.
- [ ] Không giả định defer tự chuyển công việc sang thread nền.
- [ ] Xác định publisher cold, hot, shared hoặc cached.
- [ ] Quyết định đo một lần thực thi upstream hay từng subscriber.
- [ ] Bắt đầu Timer.Sample bên trong defer nếu cần đo từng subscription.
- [ ] Dừng phép đo ở complete, error và cancel theo ngữ nghĩa mong muốn.
- [ ] Dùng Counter trong doOnNext nếu cần đếm phần tử.
- [ ] Dùng LongTaskTimer cho stream hoặc subscription kéo dài.
- [ ] Đặt instrumentation trước/sau share, cache và retry đúng ranh giới.
- [ ] Trả publisher về caller; tránh tự subscribe trong service.
- [ ] Dùng Reactor Context cho dữ liệu gắn với subscription.
- [ ] Kiểm tra Context Propagation khi pipeline đổi Scheduler.
- [ ] Kiểm thử assembly, nhiều subscription, cache/share, retry và cancel bằng StepVerifier.

Tạo Mono hoặc Flux thường chỉ lắp ráp pipeline; subscription kích hoạt cold source và các tín hiệu mới thể hiện công việc thực tế. Các factory như fromCallable và defer trì hoãn thao tác đến subscription, còn share/cache có thể thay đổi số lần upstream chạy. Đặt instrumentation theo đúng ranh giới cần đo: trong defer để tạo sample theo subscription, doFinally để kết thúc cả complete/error/cancel, và trước hoặc sau operator chia sẻ tùy muốn đo công việc upstream hay thời gian của từng subscriber.

## Tài liệu tham khảo

- [Project Reactor — Hot Versus Cold](https://projectreactor.io/docs/core/release/reference/advancedFeatures/reactor-hotCold.html)
- [Project Reactor — Adding a Context to a Reactive Sequence](https://projectreactor.io/docs/core/release/reference/advancedFeatures/context.html)
- [Reactor Mono API](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Mono.html)
- [Micrometer — Instrumentation of Reactive Libraries](https://docs.micrometer.io/micrometer/reference/observation/instrumenting.html)
- [Micrometer — Observation Components](https://docs.micrometer.io/micrometer/reference/observation/components.html)
- [Micrometer — Timers and @Timed](https://docs.micrometer.io/micrometer/reference/concepts/timers.html)
- [Micrometer — Timed Annotation API](https://javadoc.io/doc/io.micrometer/micrometer-core/latest/io/micrometer/core/annotation/Timed.html)

