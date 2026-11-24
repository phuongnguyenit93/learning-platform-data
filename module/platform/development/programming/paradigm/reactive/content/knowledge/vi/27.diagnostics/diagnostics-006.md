# Chẩn đoán

## Đo độ trễ, thông lượng, lỗi, hủy và số đăng ký đang hoạt động

Trong mô-đun **REACTIVE_PROGRAMMING**, ta học tư duy reactive qua các luồng sự kiện bất đồng bộ, hợp đồng Publisher–Subscriber và cơ chế backpressure của Reactive Streams. Ta thực hành `Mono`, `Flux`, kết hợp toán tử, kiểm soát scheduler, xử lý lỗi và kiểm thử pipeline trong hệ sinh thái Java. Khi một pipeline chạy trong môi trường thật, chỉ biết nó trả về đúng dữ liệu là chưa đủ. Ta cần quan sát nó mất bao lâu, xử lý được bao nhiêu công việc, thất bại ở đâu, có bao nhiêu subscription bị hủy và hiện có bao nhiêu subscription đang hoạt động.

Các chỉ số này giúp trả lời những câu hỏi vận hành cụ thể: request chậm vì dependency hay vì hàng đợi? Thông lượng giảm vì CPU bão hòa hay vì connection pool? Tỷ lệ lỗi tăng do dữ liệu đầu vào hay do dịch vụ phụ thuộc? Client disconnect có thực sự hủy công việc? Có subscription nào bị giữ quá lâu và làm tài nguyên không được giải phóng?

Bài học này tập trung vào cách đo những tín hiệu đó trong Project Reactor và Java, sử dụng các hook ở đúng ranh giới của pipeline và ví dụ với Micrometer. Một nguyên tắc quan trọng là xác định rõ **đang đo cái gì và đo ở đâu**. Thời gian sống của một Flux stream không giống độ trễ của một HTTP request; số phần tử phát ra không giống số request hoàn tất; cancellation không phải lỗi; và số subscription đang hoạt động không phải số thread đang chạy.

### Mục tiêu học tập

Sau bài này, bạn có thể:

- Phân biệt latency, throughput, error rate, cancellation rate và số subscription đang hoạt động.
- Đo thời gian từ lúc subscribe đến khi pipeline kết thúc bằng Timer.
- Đo thời gian tới phần tử đầu tiên và thời gian xử lý từng phần tử khi cần.
- Đếm phần tử phát ra và số request bắt đầu/hoàn tất.
- Phân loại lỗi, complete và cancel bằng `doOnError` và `doFinally`.
- Dùng Gauge để theo dõi số subscription đang hoạt động mà không làm rò rỉ bộ đếm.
- Hiểu vị trí instrumentation ảnh hưởng đến ý nghĩa của metric, nhất là khi có retry, fallback và Publisher con.
- Tránh metric cardinality cao và callback quan sát blocking.
- Kiểm thử các hook đo lường bằng `StepVerifier` và đồng hồ giả khi phù hợp.

## 1. Xác định ranh giới cần quan sát

Một ứng dụng reactive thường có nhiều lớp:

- HTTP request đi vào controller.
- Service tạo và kết hợp `Mono`/`Flux`.
- Repository hoặc HTTP client gọi dependency.
- Các toán tử chuyển scheduler, retry hoặc fallback.
- Subscriber cuối nhận kết quả hoặc hủy subscription.

Cùng một request có thể tạo nhiều subscription con. Vì vậy, một metric ở controller trả lời câu hỏi khác với metric ở HTTP client hoặc repository.

Ví dụ, thời gian HTTP request đo toàn bộ thời gian từ lúc ứng dụng bắt đầu xử lý request đến lúc response kết thúc. Thời gian repository chỉ đo đoạn truy vấn dữ liệu. Nếu chỉ đo repository, ta có thể bỏ sót thời gian chờ scheduler, xử lý dữ liệu hoặc ghi response. Nếu chỉ đo toàn request, ta thấy triệu chứng nhưng khó xác định dependency nào gây chậm.

~~~mermaid
flowchart LR
    A[HTTP request] --> B[Controller]
    B --> C[Service pipeline]
    C --> D[Repository / HTTP client]
    D --> E[Publisher kết quả]
    E --> F[Response Subscriber]
    M1[Metric request] -. đo toàn luồng .-> A
    M2[Metric dependency] -. đo lời gọi con .-> D
    M3[Metric subscription] -. đo vòng đời .-> C
~~~

Trước khi thêm metric, hãy định nghĩa đơn vị quan sát:

| Ranh giới | Đơn vị cần đo | Ví dụ câu hỏi |
|---|---|---|
| HTTP endpoint | Một request/response | p95 của endpoint là bao nhiêu? |
| Service method | Một lần chạy workflow | Workflow hoàn tất hay bị hủy? |
| Dependency client | Một lần gọi dịch vụ ngoài | API kho có chậm hoặc lỗi không? |
| Flux stream | Một subscription và các phần tử | Stream sống bao lâu, phát bao nhiêu event? |
| Consumer | Một message được xử lý | Message mất bao lâu từ nhận tới ack? |
| Pipeline con | Một lần thực thi inner Publisher | Bước nào gây chờ hoặc retry? |

Không nên cộng các metric ở nhiều ranh giới rồi coi chúng là cùng một loại request. Một request HTTP có thể gọi ba dependency; số lần gọi dependency vì thế có thể lớn hơn số request HTTP.

## 2. Latency: đo thời gian hoàn tất của một pipeline

Latency là thời gian một đơn vị công việc cần để đi từ điểm bắt đầu tới một mốc kết thúc đã chọn. Với `Mono`, thường đo thời gian từ subscription tới khi phát `onNext`/complete hoặc error. Với `Flux`, cần quyết định đang đo thời gian tới phần tử đầu tiên, thời gian giữa các phần tử hay toàn bộ thời gian sống của subscription.

Micrometer cung cấp `Timer` để ghi nhận thời lượng và số lần ghi nhận. Có thể dùng `Timer.Sample` để bắt đầu đo khi subscription bắt đầu và dừng khi subscription kết thúc.

Ví dụ một lớp instrumentation cho Flux:

~~~java
final class ReactivePipelineMetrics {
    private final MeterRegistry registry;
    private final AtomicLong activeSubscriptions = new AtomicLong();
    private final Counter emittedEvents;
    private final Counter errors;

    ReactivePipelineMetrics(MeterRegistry registry) {
        this.registry = registry;

        this.emittedEvents = Counter.builder("app.reactive.events")
            .tag("flow", "order-updates")
            .register(registry);

        this.errors = Counter.builder("app.reactive.errors")
            .tag("flow", "order-updates")
            .register(registry);

        Gauge.builder(
                "app.reactive.subscriptions.active",
                activeSubscriptions,
                AtomicLong::get
            )
            .tag("flow", "order-updates")
            .register(registry);
    }

    Flux<OrderUpdate> observe(Flux<OrderUpdate> source) {
        return Flux.defer(() -> {
            Timer.Sample sample = Timer.start(registry);
            activeSubscriptions.incrementAndGet();

            return source
                .doOnNext(ignored -> emittedEvents.increment())
                .doOnError(ignored -> errors.increment())
                .doFinally(signal -> {
                    activeSubscriptions.decrementAndGet();

                    sample.stop(registry.timer(
                        "app.reactive.subscription.duration",
                        "flow", "order-updates",
                        "termination", termination(signal)
                    ));
                });
        });
    }

    private String termination(SignalType signal) {
        return switch (signal) {
            case ON_COMPLETE -> "complete";
            case ON_ERROR -> "error";
            case CANCEL -> "cancel";
            default -> "other";
        };
    }
}
~~~

Các điểm cần chú ý:

- `Flux.defer` tạo một `Timer.Sample` và tăng bộ đếm cho mỗi subscription, không phải một lần khi lắp ráp pipeline.
- `doOnNext` đếm phần tử thực sự đi qua ranh giới instrumentation.
- `doOnError` đếm lỗi được truyền qua ranh giới này.
- `doFinally` chạy khi complete, error hoặc cancel; nó giảm bộ đếm active và dừng timer.
- Tag `termination` có tập giá trị giới hạn, giúp phân biệt ba kiểu kết thúc.

Giữ `AtomicLong` trong field để đối tượng được Gauge tham chiếu tồn tại trong suốt vòng đời meter. Nếu tạo một Gauge với một biến cục bộ rồi không giữ tham chiếu, một số cấu hình Micrometer có thể không giữ được đối tượng đo như mong muốn.

Đây là một ví dụ instrumentation tại ranh giới subscription của stream. Trong ứng dụng thực tế, nên tạo metric một lần ở thành phần sở hữu pipeline và tái sử dụng, tránh đăng ký lại cùng tên/tag cho từng request.

## 3. Đo latency của Mono và request hoàn tất

Với `Mono`, thời gian từ subscribe tới terminal signal thường gần với thời gian xử lý của một request hoặc một workflow. Có thể tạo một helper tương tự:

~~~java
<T> Mono<T> observeMono(
    Mono<T> source,
    MeterRegistry registry,
    Timer timer
) {
    return Mono.defer(() -> {
        Timer.Sample sample = Timer.start(registry);

        return source.doFinally(signal -> sample.stop(timer));
    });
}
~~~

Timer được truyền vào để thành phần sở hữu tạo sẵn với tên và tag ổn định:

~~~java
Timer orderLookupTimer = Timer.builder("app.order.lookup.duration")
    .tag("operation", "find-by-id")
    .register(registry);

Mono<Order> findOrder(String orderId) {
    return observeMono(
        orderRepository.findById(orderId),
        registry,
        orderLookupTimer
    );
}
~~~

Timer ghi thời lượng của subscription tới khi kết thúc bằng complete, error hoặc cancel. Nếu cần phân tích riêng kiểu kết thúc, hãy dùng timer riêng theo outcome hoặc một metric counter theo outcome. Không nên dùng ID đơn hàng hoặc request ID làm tag.

Một Mono rỗng vẫn có thể hoàn tất bình thường. Vì vậy, nếu muốn đo số request thành công, hãy quyết định rõ liệu "không tìm thấy" có được tính là thành công kỹ thuật hay là một outcome nghiệp vụ riêng. `doOnSuccess` của Mono được gọi cả khi hoàn tất rỗng, với giá trị null; `doOnNext` chỉ chạy khi có phần tử.

Ví dụ đếm các outcome ở ranh giới service:

~~~java
Mono<Order> order =
    orderRepository.findById(orderId)
        .doOnNext(ignored -> foundCounter.increment())
        .doOnSuccess(value -> {
            if (value == null) {
                notFoundCounter.increment();
            }
        })
        .doOnError(error -> failureCounter.increment());
~~~

Metric nên phản ánh hợp đồng của endpoint. Nếu 404 là kết quả hợp lệ khi không có đơn hàng, đừng gộp nó vào lỗi hạ tầng.

## 4. Phân biệt request latency, first-item latency và stream lifetime

Với `Flux`, một stream có thể sống hàng giờ. Đo thời gian từ subscribe đến complete có thể không hữu ích nếu stream được thiết kế để chạy liên tục. Thay vào đó, chọn các phép đo phù hợp:

- **Subscription lifetime:** thời gian từ subscribe đến complete/error/cancel.
- **Time to first item:** thời gian từ subscribe đến phần tử đầu tiên.
- **Inter-arrival time:** khoảng cách giữa hai phần tử liên tiếp.
- **Per-item processing time:** thời gian một phần tử đi qua một bước xử lý cụ thể.
- **Request latency:** thời gian hoàn tất một thao tác request/response có giới hạn.

Ví dụ đo thời gian tới phần tử đầu tiên:

~~~java
Flux<PriceTick> observed(Flux<PriceTick> source, MeterRegistry registry) {
    return Flux.defer(() -> {
        Timer.Sample firstItemSample = Timer.start(registry);
        AtomicBoolean firstItem = new AtomicBoolean();

        return source.doOnNext(item -> {
            if (firstItem.compareAndSet(false, true)) {
                firstItemSample.stop(
                    registry.timer("app.price-stream.time-to-first-item")
                );
            }
        });
    });
}
~~~

Nếu nguồn hoàn tất hoặc lỗi mà không phát phần tử, sample này chưa được dừng. Trong ứng dụng thực tế, hãy ghi nhận outcome "empty" hoặc "error-before-first-item" trong `doFinally` để không mất khả năng phân tích những subscription không phát dữ liệu.

Đo inter-arrival time cần cẩn thận với nhiều thread. Nếu một Flux có thể phát tín hiệu tuần tự theo Reactive Streams, có thể lưu timestamp của phần tử trước bằng một biến trạng thái riêng cho subscription. Không dùng một timestamp static chia sẻ giữa các subscriber.

Đối với stream dài hạn, thường hữu ích hơn khi theo dõi số phần tử mỗi giây, thời gian xử lý mỗi phần tử, độ trễ từ event source tới consumer và số subscription đang hoạt động, thay vì chỉ xem tổng lifetime.

## 5. Throughput: đo số công việc hoàn tất

Throughput là số đơn vị công việc hoàn tất trong một khoảng thời gian. Cần xác định đơn vị:

- HTTP requests hoàn tất mỗi giây.
- Messages được ack mỗi giây.
- Events phát ra từ một Flux mỗi giây.
- Bản ghi được lưu thành công mỗi giây.
- Tác vụ xử lý thành công mỗi giây.

Với Flux, `doOnNext` có thể tăng counter cho mỗi phần tử đi qua:

~~~java
Flux<OrderEvent> events =
    eventSource.events()
        .doOnNext(event -> processedEvents.increment());
~~~

Counter là giá trị tích lũy. Hệ thống metric có thể tính tốc độ tăng của counter theo cửa sổ thời gian. Không nên tự đặt một Gauge "events per second" bằng cách chia trong callback nếu backend đã hỗ trợ rate function; counter thường giữ được thông tin tốt hơn qua restart và scrape interval.

Đếm request bắt đầu và hoàn tất ở ranh giới service:

~~~java
Mono<OrderReceipt> process(OrderCommand command) {
    return Mono.defer(() -> {
        requestsStarted.increment();

        return orderService.process(command)
            .doOnSuccess(ignored -> requestsCompleted.increment())
            .doOnError(ignored -> requestsFailed.increment());
    });
}
~~~

Trong ví dụ này, `doOnSuccess` cũng chạy khi Mono hoàn tất rỗng. Nếu nghiệp vụ cần phân biệt thành công có receipt và kết quả rỗng, hãy kiểm tra giá trị hoặc dùng các metric outcome riêng.

Nếu đo throughput của một endpoint, chỉ đếm request bắt đầu sẽ không cho biết bao nhiêu request hoàn tất thành công. Nên theo dõi ít nhất started, completed, failed và cancelled để thấy các outcome khác nhau.

### Throughput không đồng nghĩa với concurrency

Một hệ thống có 100 request đang hoạt động không nhất thiết hoàn tất 100 request mỗi giây. Concurrency là số công việc đang được tiến hành tại cùng thời điểm; throughput là tốc độ hoàn tất. Theo định luật Little, trong điều kiện ổn định, số công việc trung bình đang ở trong hệ thống liên hệ với throughput và thời gian lưu lại trung bình. Khi latency tăng, số request đang hoạt động có thể tăng ngay cả khi throughput không đổi.

Do đó, hãy xem throughput cùng latency và active count. Chỉ nhìn một chỉ số có thể dẫn đến kết luận sai về năng lực hệ thống.

## 6. Đếm lỗi và phân biệt lỗi cuối với lỗi từng lần retry

`doOnError` quan sát lỗi đi qua vị trí đặt toán tử. Vị trí đó rất quan trọng khi pipeline có retry.

~~~java
Mono<Inventory> inventory =
    Mono.defer(() -> inventoryClient.find(productId))
        .doOnError(error -> attemptErrors.increment())
        .retryWhen(
            Retry.backoff(2, Duration.ofMillis(100))
                .filter(this::isTransient)
        )
        .doOnError(error -> requestFailures.increment());
~~~

Ở đây:

- `attemptErrors` đếm lỗi của từng lần thử trước retry.
- `requestFailures` chỉ đếm lỗi cuối cùng nếu toàn bộ chuỗi retry vẫn thất bại.
- Nếu lần thử thứ hai thành công, lỗi lần đầu vẫn được ghi ở attempt metric nhưng request không được tính là thất bại cuối.

Nếu đặt `doOnError` chỉ sau retry, ta không thấy những lỗi tạm thời đã được retry thành công. Nếu chỉ đặt trước retry, ta có thể đánh giá quá cao tỷ lệ request cuối cùng thất bại. Cả hai metric đều hữu ích nhưng có ý nghĩa khác nhau.

### Phân loại lỗi theo nhóm ổn định

Không nên gắn exception message làm tag vì message có thể chứa ID, URL, câu truy vấn hoặc dữ liệu biến thiên. Dùng mã lỗi đã chuẩn hóa:

~~~java
String errorKind(Throwable error) {
    if (error instanceof TimeoutException) {
        return "timeout";
    }
    if (error instanceof WebClientRequestException) {
        return "connection";
    }
    if (error instanceof BusinessRuleException) {
        return "business";
    }
    if (error instanceof InvalidDataException) {
        return "invalid-data";
    }
    return "other";
}
~~~

Sau đó, tăng counter theo tập tag có giới hạn:

~~~java
Map<String, Counter> errorCounters = Map.of(
    "timeout", registry.counter("app.reactive.errors", "operation", "inventory-lookup", "kind", "timeout"),
    "connection", registry.counter("app.reactive.errors", "operation", "inventory-lookup", "kind", "connection"),
    "business", registry.counter("app.reactive.errors", "operation", "inventory-lookup", "kind", "business"),
    "invalid-data", registry.counter("app.reactive.errors", "operation", "inventory-lookup", "kind", "invalid-data"),
    "other", registry.counter("app.reactive.errors", "operation", "inventory-lookup", "kind", "other")
);

.doOnError(error -> errorCounters.get(errorKind(error)).increment())
~~~

Tạo sẵn counter cho tập tag dự kiến ở thành phần instrumentation, sau đó callback chỉ tra cứu và tăng counter. Cách này tránh tạo builder hoặc đăng ký meter trong mỗi tín hiệu lỗi.

Không ghi nguyên exception hoặc payload vào metric. Log có thể chứa stack trace và trace ID đã lọc, còn metric nên dùng nhãn ngắn, ổn định và có cardinality thấp.

## 7. Cancellation là outcome riêng, không phải error

Khi Subscriber hủy subscription, downstream không nhận một `onError` chỉ vì cancellation xảy ra. Reactor cung cấp `doOnCancel` để quan sát cancel và `doFinally` để phân biệt các kiểu kết thúc.

~~~java
Flux<Reading> readings =
    sensor.readings()
        .doOnCancel(() -> cancellations.increment())
        .doFinally(signal -> {
            switch (signal) {
                case ON_COMPLETE -> completedStreams.increment();
                case ON_ERROR -> failedStreams.increment();
                case CANCEL -> cancelledStreams.increment();
                default -> otherTerminations.increment();
            }
        });
~~~

Không nên tăng cả error counter và cancellation counter cho cùng một hành động hủy chỉ vì một request bị đóng. Cancellation thường là hành vi bình thường: người dùng rời trang, client không còn cần dữ liệu hoặc một toán tử như `take` đã nhận đủ phần tử.

Tuy nhiên, tỷ lệ cancellation tăng bất thường có thể là tín hiệu cần điều tra:

- Client timeout hoặc disconnect nhiều hơn bình thường.
- Downstream hủy vì người dùng điều hướng liên tục.
- Một timeout nội bộ kích hoạt quá sớm.
- Một bước xử lý chậm khiến caller bỏ cuộc.
- Một consumer bị dừng hoặc rebalance.

Metric cần cho biết cancellation xảy ra ở ranh giới nào và có nguồn gốc nào nếu hệ thống có thể xác định. Không đưa request ID vào metric tag; dùng trace/log có correlation ID để điều tra từng trường hợp.

### Cancellation upstream và lỗi đến muộn

Khi cancellation được truyền tới nguồn, adapter có thể dừng request, gỡ listener hoặc giải phóng tài nguyên. Nếu callback lỗi đến sau khi subscription đã hủy, lỗi đó có thể không còn nơi nhận và trở thành dropped error. Hãy quan sát riêng dropped error bằng hook toàn cục phù hợp; đừng gộp nó vào error rate của request thông thường.

Cancellation không rollback tác dụng phụ đã commit ở hệ thống từ xa. Với thao tác ghi, vẫn cần idempotency và đối soát trạng thái.

## 8. Số subscription đang hoạt động bằng Gauge

Gauge biểu diễn giá trị tại thời điểm quan sát, phù hợp với số subscription đang hoạt động. Cách phổ biến là tăng bộ đếm khi subscription bắt đầu và giảm khi subscription kết thúc bằng bất kỳ outcome nào.

~~~java
final class ActiveSubscriptionMetric {
    private final AtomicLong active = new AtomicLong();

    ActiveSubscriptionMetric(MeterRegistry registry, String flow) {
        Gauge.builder("app.reactive.subscriptions.active", active, AtomicLong::get)
            .tag("flow", flow)
            .register(registry);
    }

    <T> Flux<T> track(Flux<T> source) {
        return Flux.defer(() -> {
            active.incrementAndGet();

            return source.doFinally(signal -> active.decrementAndGet());
        });
    }
}
~~~

Dùng `Flux.defer` để bộ đếm tăng một lần cho mỗi subscription. `doFinally` đảm bảo giảm khi complete, error hoặc cancel. Vì callback có thể chạy từ các thread khác nhau, dùng `AtomicLong` thay cho biến số nguyên không đồng bộ.

Một số lưu ý:

- Nếu có nhiều Subscriber, mỗi subscription được tính riêng.
- Nếu cùng một Flux được subscribe hai lần, active count tăng hai.
- Nếu pipeline có inner Publisher, metric đặt ngoài và trong inner có thể đếm hai cấp khác nhau.
- Nếu nguồn không bao giờ kết thúc và không bị hủy, subscription vẫn active; điều đó có thể đúng với stream dài hạn.
- Nếu active count tăng liên tục mà không giảm, hãy điều tra subscription bị giữ, listener không được dispose hoặc client không hủy.

Đừng gọi metric này là "số thread đang chạy". Một subscription có thể chờ I/O mà không giữ thread; một subscription cũng có thể dùng nhiều thread qua các scheduler.

### Đo active subscriptions cho Mono

Có thể dùng cùng mẫu với `Mono.defer`:

~~~java
<T> Mono<T> track(Mono<T> source) {
    return Mono.defer(() -> {
        active.incrementAndGet();

        return source.doFinally(signal -> active.decrementAndGet());
    });
}
~~~

Đặt instrumentation ở ranh giới phù hợp. Nếu đo active HTTP request, hãy đặt ở controller hoặc WebFilter; nếu đo active dependency call, đặt ở client adapter. Một request có thể tạo nhiều subscription con nên các Gauge này không có cùng ý nghĩa.

## 9. Kết hợp latency, throughput, errors, cancellation và active count

Một dashboard hữu ích nên ghép các chỉ số thay vì xem riêng từng metric.

| Metric | Loại | Câu hỏi được trả lời |
|---|---|---|
| `app.reactive.subscription.duration` | Timer | Một subscription sống bao lâu? |
| `app.reactive.events` | Counter | Bao nhiêu phần tử đi qua ranh giới? |
| `app.reactive.errors` | Counter | Bao nhiêu lỗi xảy ra và thuộc nhóm nào? |
| `app.reactive.cancelled` | Counter | Bao nhiêu subscription kết thúc do cancel? |
| `app.reactive.subscriptions.active` | Gauge | Hiện có bao nhiêu subscription đang hoạt động? |
| `app.reactive.requests.started` | Counter | Bao nhiêu request bắt đầu? |
| `app.reactive.requests.completed` | Counter | Bao nhiêu request hoàn tất? |

Ví dụ cách diễn giải:

- Latency tăng, active subscriptions tăng, throughput không đổi: có thể công việc đang chờ ở dependency hoặc queue.
- Error tăng cùng timeout: dependency có thể chậm hoặc quá tải.
- Cancellation tăng nhưng error ổn định: client có thể rời đi nhiều hơn hoặc deadline phía caller ngắn hơn.
- Active count không giảm sau khi traffic giảm: có thể có stream dài hạn hợp lệ hoặc subscription/resource bị giữ.
- Throughput giảm, CPU thấp, active count cao: kiểm tra I/O pool, connection pool và dependency.
- Throughput giảm, CPU bão hòa: kiểm tra phép tính CPU, số worker và scheduler queue.

Các dấu hiệu trên là giả thuyết điều tra, không phải kết luận tự động. Hãy đối chiếu log, trace, queue lag, scheduler và dependency metrics trước khi thay đổi cấu hình.

## 10. Đặt instrumentation ở đúng vị trí trong pipeline

Vị trí của toán tử đo lường xác định phần công việc được đo. Ví dụ:

~~~java
Mono<Order> order = Mono.defer(() -> {
    Timer.Sample sample = Timer.start(registry);

    return orderRepository.findById(orderId)
        .doOnError(error -> repositoryErrors.increment())
        .onErrorMap(this::translateRepositoryError)
        .timeout(Duration.ofMillis(500))
        .doFinally(signal -> sample.stop(requestTimer));
});
~~~

Ở đây, metric lỗi repository chỉ quan sát lỗi phát ra từ repository trước khi chuyển đổi. Timer ngoài cùng đo cả bước repository, chuyển đổi lỗi và timeout. Nếu timeout kích hoạt, upstream có thể nhận cancellation trong khi pipeline ngoài kết thúc bằng error timeout. Vì vậy, metric cancellation ở ranh giới upstream và error ở ranh giới downstream có thể cùng tăng cho một request; đó không phải đếm trùng nếu tên metric thể hiện rõ mỗi ranh giới.

Một cách tổ chức rõ hơn:

~~~java
Mono<Order> dependencyCall =
    orderRepository.findById(orderId)
        .transform(repositoryMetrics::observe);

Mono<Order> request =
    dependencyCall
        .timeout(Duration.ofMillis(500))
        .transform(requestMetrics::observe);
~~~

`transform` áp dụng một hàm biến đổi Publisher tại assembly. Hàm instrumentation cần tạo state riêng theo subscription bằng `defer`, như các ví dụ trước. Cách đặt tên metric nên phân biệt dependency với request.

Đừng đặt metric ở một vị trí rồi diễn giải nó như đo toàn bộ request. Hãy ghi chú ranh giới trong tên hoặc tag operation.

## 11. Micrometer và Observation trong ứng dụng Spring

Micrometer cung cấp các loại meter cơ bản:

- `Counter` cho số lần sự kiện xảy ra.
- `Timer` cho số lần và thời lượng.
- `Gauge` cho giá trị hiện tại như active subscription.
- `DistributionSummary` cho phân phối các giá trị như payload size hoặc batch size.

Trong ứng dụng Spring Boot, `MeterRegistry` thường được inject từ context. Có thể tạo một component riêng để đăng ký meter một lần và dùng lại ở service hoặc adapter. Không nên tạo registry mới cho mỗi request.

Với tracing và observation, Spring/Micrometer Observation có thể gắn context và tạo span cho các ranh giới nghiệp vụ. Reactor có cơ chế tích hợp context propagation tùy phiên bản và cấu hình. Hãy dùng một cơ chế thống nhất trong ứng dụng để tránh tạo span trùng hoặc mất trace context khi chuyển scheduler.

Một quy tắc thực tế:

- Dùng metric để biết xu hướng tổng thể và cảnh báo.
- Dùng trace để theo dõi một request qua nhiều dependency.
- Dùng log có cấu trúc để điều tra chi tiết một lỗi hoặc một cancellation.
- Dùng profile/thread dump khi cần tìm CPU hotspot hoặc blocking call.

Metric không thay thế trace; trace cũng không thay thế metric. Metric cho biết "điều gì đang xảy ra trên diện rộng", còn trace hỗ trợ tìm "request cụ thể đã đi qua đâu".

## 12. Tránh cardinality cao và rò rỉ metric

Mỗi tổ hợp tên metric và tag có thể tạo một time series riêng. Nếu tag chứa giá trị không giới hạn, số series có thể tăng rất nhanh.

Không nên dùng các giá trị sau làm metric tag:

- User ID hoặc customer ID.
- Order ID, request ID hoặc message ID.
- URL có path parameter.
- Exception message.
- Tên tenant không giới hạn.
- Payload hoặc giá trị tìm kiếm.

Ưu tiên tag có tập giá trị nhỏ và ổn định:

~~~java
Counter.builder("app.reactive.errors")
    .tag("operation", "order-lookup")
    .tag("dependency", "order-db")
    .tag("kind", "timeout")
    .register(registry);
~~~

Nếu cần điều tra một order cụ thể, dùng trace ID hoặc log đã lọc thay vì tag metric.

Một lỗi khác là đăng ký meter mới trong mỗi subscription với tag khác nhau. Điều này vừa tăng cardinality vừa có thể làm bộ nhớ registry tăng. Hãy tạo meter ở constructor hoặc cấu hình khởi động và chỉ cập nhật giá trị trong callback.

Gauge nên tham chiếu tới một object có vòng đời rõ ràng. Tránh tạo một Gauge mới cho mỗi request; active count là một giá trị chia sẻ ở đúng ranh giới instrumentation, không phải một meter riêng cho từng subscription.

## 13. Callback đo lường phải nhẹ và không blocking

Các callback như `doOnNext`, `doOnError`, `doFinally` thường chạy trên thread phát tín hiệu. Nếu callback ghi file, gọi HTTP blocking hoặc chờ lock, nó có thể làm chậm pipeline và thay đổi chính latency mà ta đang đo.

Nên:

- Cập nhật Counter/Gauge/Timer đồng bộ với thao tác nhẹ.
- Tránh I/O blocking trong callback.
- Không serialize payload lớn chỉ để ghi metric.
- Không ném exception từ callback instrumentation.
- Dùng logger bất đồng bộ hoặc queue có giới hạn cho log cần xử lý thêm.
- Tránh tính toán nặng hoặc truy cập database trong hook quan sát.

Instrumentation nên ít ảnh hưởng tới hệ thống. Nếu callback đo lường quá nặng, metric sẽ phản ánh chi phí của chính việc đo thay vì hành vi ứng dụng.

## 14. Kiểm thử instrumentation

Không chỉ kiểm thử kết quả nghiệp vụ; hãy kiểm tra metric tăng/giảm đúng theo tín hiệu.

Ví dụ với Micrometer `SimpleMeterRegistry`:

~~~java
SimpleMeterRegistry registry = new SimpleMeterRegistry();
Counter events = registry.counter("test.events");

Flux<Integer> source =
    Flux.just(1, 2, 3)
        .doOnNext(value -> events.increment());

StepVerifier.create(source)
    .expectNext(1, 2, 3)
    .verifyComplete();

assertThat(events.count()).isEqualTo(3.0);
~~~

Kiểm thử cancellation và active count:

~~~java
SimpleMeterRegistry registry = new SimpleMeterRegistry();
AtomicLong active = new AtomicLong();

Gauge.builder("test.active", active, AtomicLong::get)
    .register(registry);

Flux<Integer> tracked =
    Flux.defer(() -> {
        active.incrementAndGet();

        return Flux.range(1, 10)
            .doFinally(signal -> active.decrementAndGet());
    });

StepVerifier.create(tracked, 0)
    .expectSubscription()
    .then(() -> assertThat(active.get()).isEqualTo(1))
    .thenRequest(2)
    .expectNext(1, 2)
    .thenCancel()
    .verify();

assertThat(active.get()).isZero();
assertThat(registry.get("test.active").gauge().value()).isZero();
~~~

Test này xác minh active count tăng khi subscription được tạo và giảm sau cancellation. Cần có assertion sau `verify()` vì `thenCancel` kết thúc kịch bản rồi callback `doFinally` được thực thi.

Kiểm thử latency có thể dùng `MockClock` hoặc clock được kiểm soát nếu API timer trong phiên bản Micrometer hỗ trợ; tránh `Thread.sleep` dài. Nếu mục tiêu chỉ là xác minh Timer được ghi nhận, kiểm tra count trước; nếu kiểm tra duration, dùng clock giả hoặc test chuyên biệt cho helper đo thời gian.

Các trường hợp nên kiểm thử:

- Complete bình thường: active giảm, completion counter tăng.
- Error: active giảm, error counter tăng.
- Cancel: active giảm, cancellation counter tăng nhưng error counter không tăng chỉ vì cancel.
- Mono rỗng: request hoàn tất nhưng không có onNext.
- Retry: phân biệt số lỗi từng attempt với số request cuối thất bại.
- Fallback: metric nguồn chính và fallback được gắn đúng operation.
- Nhiều subscription đồng thời: active count phản ánh số subscription đang sống.
- Nguồn dài hạn: active count giữ ở mức phù hợp cho tới khi cancel hoặc complete.

## 15. Những nhầm lẫn thường gặp

- **Latency của Flux luôn là request latency:** stream dài hạn có thể sống hàng giờ; hãy đo first-item, inter-arrival hoặc per-item latency theo mục tiêu.
- **Throughput là số subscription đang hoạt động:** throughput đo tốc độ hoàn tất; active count đo công việc đang diễn ra.
- **Mọi onError đều là lỗi cuối của request:** lỗi trước retry có thể được phục hồi; phân biệt attempt error và final failure.
- **Cancellation là error:** cancel là outcome riêng; dùng `doOnCancel` và `doFinally`.
- **doFinally chỉ chạy khi complete:** nó chạy với complete, error và cancel.
- **doOnNext đo số request thành công:** nó đếm phần tử; Mono rỗng không phát onNext nhưng vẫn có thể hoàn tất bình thường.
- **Active subscriptions là số thread:** một subscription có thể đang chờ I/O mà không giữ thread.
- **Đặt Timer ở bất kỳ đâu cũng đo toàn request:** timer chỉ đo đoạn nằm trong ranh giới Publisher được instrument.
- **Retry không ảnh hưởng metric lỗi:** vị trí doOnError trước/sau retry quyết định đang đếm từng attempt hay lỗi cuối.
- **Metric tag có thể chứa mọi ID để dễ debug:** tag cardinality cao làm tăng chi phí và có thể gây quá tải hệ thống metrics.
- **Callback instrumentation có thể blocking:** callback chạy trên thread phát tín hiệu; blocking có thể làm chậm pipeline.
- **Gauge có thể được tạo trong mỗi request:** meter nên được đăng ký một lần và cập nhật qua object có vòng đời rõ ràng.

## 16. Bài tập vận dụng

Một endpoint WebFlux trả về `Flux<Notification>` cho client đang theo dõi trạng thái đơn hàng. Mỗi subscription đọc event từ broker, biến đổi thành notification và ghi vào response. Client có thể disconnect; broker đôi khi giao lại message; một dependency có thể timeout.

Hãy thiết kế bộ metric và cách kiểm thử:

1. Đo latency nào phù hợp: thời gian sống stream, thời gian tới notification đầu tiên hay thời gian xử lý mỗi message?
2. Throughput nên đếm message nhận, message xử lý thành công hay notification thực sự phát tới response?
3. Phân biệt lỗi của từng lần retry với lỗi cuối cùng của subscription ra sao?
4. Cancellation khi client disconnect được ghi nhận bằng hook nào?
5. Gauge active subscriptions được tăng/giảm ở đâu để không bị lệch khi complete, error hoặc cancel?
6. Làm thế nào để biết stream đang hoạt động nhưng không phát dữ liệu?
7. Những tag nào an toàn và có cardinality thấp?
8. Nếu `flatMap` gọi nhiều dependency, metric ở service boundary và dependency boundary khác nhau ra sao?
9. Viết test bằng `StepVerifier` cho complete, error, cancel và active count.
10. Nếu một message bị giao lại, metric nào giúp phát hiện duplicate mà không dùng message ID làm tag?

**Gợi ý:** đặt một instrumentation boundary cho subscription response và một boundary riêng cho mỗi dependency. Dùng Timer cho lifetime hoặc time-to-first-item, Counter cho event/attempt/final outcome, Gauge cho active subscription. Dùng `doFinally` để giảm active count trên mọi kiểu kết thúc. Tag theo operation, dependency và error kind đã chuẩn hóa; dùng trace/log để tra cứu ID cụ thể. Với message duplicate, dùng counter theo outcome `duplicate` và idempotency logic ở consumer.

## Kết luận

Chẩn đoán một hệ thống reactive cần đo đúng đơn vị và đúng ranh giới: Timer cho latency, Counter cho throughput và lỗi, outcome riêng cho cancellation, Gauge cho số subscription đang hoạt động. `doOnNext`, `doOnError`, `doOnCancel` và `doFinally` cho phép gắn quan sát vào vòng đời Publisher, còn `defer` bảo đảm trạng thái đo được tạo riêng theo subscription. Hãy phân biệt request latency với stream lifetime, lỗi từng attempt với lỗi cuối, và active subscription với thread. Giữ tag có cardinality thấp, callback nhẹ và kiểm thử cả complete/error/cancel để metric phản ánh đúng hành vi của pipeline `Mono`/`Flux` trong môi trường vận hành.
