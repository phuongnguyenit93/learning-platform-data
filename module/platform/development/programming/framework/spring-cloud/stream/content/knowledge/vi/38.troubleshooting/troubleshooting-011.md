# Reactive pipeline ngừng xử lý hoặc không có subscriber

Một ứng dụng Spring Cloud Stream có thể chạy bình thường, kết nối Kafka/RabbitMQ/Pulsar không báo lỗi nhưng vẫn **không xử lý message**. Một tình huống thường gặp là developer dựng một chuỗi thao tác Reactor (`Flux` hoặc `Mono`) mà không có subscriber. Trong tình huống khác, pipeline đã có subscriber nhưng phát tín hiệu `onError` rồi kết thúc, nguồn `Flux` đã `onComplete`, subscription bị cancel, hoặc broker không cấp thêm message. Những trường hợp này nhìn bề ngoài giống nhau: log xử lý nghiệp vụ biến mất và backlog tăng.

Trong Spring Cloud Stream, phải phân biệt rõ reactive **Function** với reactive **Consumer**. Với `Function<Flux<T>, Flux<R>>`, framework lấy Publisher kết quả để nối vào binding output; ứng dụng thường không cần và không nên tự `subscribe()` bên trong function. Ngược lại, `Consumer<Flux<T>>` trả về `void`, framework không có Publisher kết quả để subscribe thay; nếu chọn dạng này, developer phải tự thiết lập subscription và quản lý vòng đời của nó. Spring Cloud Stream khuyến nghị cân nhắc `Function<Flux<T>, Mono<Void>>` làm reactive sink nếu không cần output event.

Bài học thuộc chương **Chẩn đoán sự cố** của module SPRING_CLOUD_STREAM, áp dụng cho ứng dụng xử lý sự kiện bằng `Supplier`/`Function`/`Consumer`, binding/binder Kafka, RabbitMQ hoặc Pulsar. Ví dụ dùng Project Reactor và functional model của Spring Cloud Stream 5.1; hãy kiểm tra khả năng hỗ trợ và tên property của binder/version thực tế khi triển khai.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Phân biệt **assembly**, **subscription**, **request**, **onNext**, **onError**, **onComplete** và **cancel** trong Reactor.
- Nhận diện chuỗi `map`/`flatMap`/`doOnNext` có khai báo nhưng chưa ai subscribe.
- So sánh `Function<Flux, Flux>`, `Consumer<Flux>` và `Function<Flux, Mono<Void>>`.
- Phát hiện publisher hoàn tất, bị cancel hoặc kết thúc bởi lỗi.
- Xác minh bean function thực sự được bind bằng `spring.cloud.function.definition`.
- Phân biệt Kafka regular binder với Kafka Reactive Binder và giới hạn backpressure.
- Tránh `subscribe()` phụ, `block()` sai thread và retry làm chết subscription.
- Chọn chiến lược `onErrorResume`/`retryWhen`, DLQ/quarantine và acknowledgment phù hợp.
- Dùng Reactor diagnostics, Micrometer/Actuator, StepVerifier và broker metrics để điều tra.
- Xây runbook khôi phục pipeline an toàn, tránh mất và xử lý trùng message.

## 1. Nhận diện triệu chứng trước khi sửa code

Không phải mọi pipeline im lặng đều thiếu subscriber. Hãy phân loại từ tín hiệu quan sát được:

| Triệu chứng | Khả năng chính | Bước xác minh đầu tiên |
|---|---|---|
| Log tạo bean xuất hiện, nhưng không có log xử lý từng event | Chưa subscribe; function không được bind; topic rỗng | Kiểm tra binding và `doOnSubscribe` |
| Có log `onSubscribe` nhưng không có `onNext` | Chưa có data; không có demand; nguồn bị pause | Kiểm tra request, assignment, lag/queue depth |
| Xử lý vài event rồi dừng hẳn | `onError`, `onComplete` hoặc `cancel` | Đặt `doOnError`/`doFinally`; kiểm tra terminal signal |
| Consumer group có lag nhưng ứng dụng vẫn healthy | Subscriber đã mất, handler chậm, partition không assigned | Kiểm tra subscription và Kafka group assignment |
| Input có event nhưng output topic trống | Output chưa được subscribe/bind; operator lọc; send lỗi | Kiểm tra `Function` output binding, `filter` và producer error |
| Sau deploy/restart mới có event | Shared/hot source bắt đầu trước subscriber; lifecycle race | Kiểm tra cold/hot và thời điểm subscribe |
| CPU cao, xử lý không tiến | `block()`, lock, blocking I/O, scheduler starvation | Xem thread dump và Reactor scheduler |
| DLQ tăng, dữ liệu không tiếp tục | Poison message/retry exhausted | Kiểm tra error path và broker semantics |

Quy trình triage nên trả lời theo thứ tự: **đã có input ở broker chưa → binding có kết nối đúng chưa → có subscription chưa → có request/demand chưa → có onNext chưa → đã kết thúc ở đâu → offset/ack ra sao?**

## 2. Publisher không tự chạy chỉ vì được tạo

Project Reactor là hệ thống Publisher/Subscriber theo Reactive Streams. Các operator như `map`, `filter`, `flatMap` hay `doOnNext` mô tả một kế hoạch xử lý. Với đa số nguồn cold, phần lớn công việc chỉ bắt đầu khi một Subscriber subscribe vào Publisher.

~~~java
Flux<String> pipeline = Flux.just("order-1", "order-2")
        .map(String::toUpperCase)
        .doOnNext(value -> log.info("processed {}", value));

log.info("pipeline assembled");
// Không subscribe => các giá trị từ Flux.just chưa được xử lý.
~~~

Đoạn code trên chỉ xây pipeline. Nó không chủ động publish message tới Kafka, không tạo subscriber và không phải cách triển khai một Function trong Spring Cloud Stream.

Để minh họa ở **một chương trình thử nghiệm Reactor độc lập**:

~~~java
pipeline.subscribe(
        value -> log.info("received {}", value),
        error -> log.error("pipeline failed", error),
        () -> log.info("pipeline completed"));
~~~

Khi triển khai `Function<Flux, Flux>` trong Spring Cloud Stream, **không chèn lệnh `subscribe()` này vào function**. Framework cần nắm Publisher trả về để gắn với output binding và quản lý lifecycle.

### 2.1. Sáu tín hiệu quan trọng

~~~mermaid
sequenceDiagram
    participant P as Publisher
    participant S as Subscriber
    S->>P: subscribe()
    P-->>S: onSubscribe(subscription)
    S->>P: request(n)
    P-->>S: onNext(event 1)
    P-->>S: onNext(event 2)
    alt Hết dữ liệu
        P-->>S: onComplete()
    else Lỗi không được xử lý
        P-->>S: onError(error)
    else Hủy xử lý
        S->>P: cancel()
    end
~~~

`onComplete` và `onError` là hai tín hiệu terminal của một subscription; `cancel` là hành động của Subscriber khiến luồng dừng theo cơ chế cancel. Sau một terminal signal, subscription đó không tiếp tục phát `onNext`. Với nguồn broker chạy lâu, việc toàn bộ subscription kết thúc bất ngờ thường cần điều tra.

### 2.2. map và doOnNext không phải subscribe

~~~java
// Sai nếu đứng riêng: chỉ tạo publisher, không thực thi.
Flux<String> ignored = source
        .doOnNext(log::info)
        .map(String::toUpperCase);
~~~

`doOnNext` chỉ quan sát signal đi qua. Nó không thay thế terminal subscriber và không bảo đảm side effect đã diễn ra. Trong ứng dụng Spring Cloud Stream, Publisher phải được trả về cho framework hoặc được consumer subscribe một cách có trách nhiệm.

### 2.3. Cold so với hot source

**Cold Publisher** (ví dụ `Flux.defer`, `Flux.just`) thường tạo sequence theo subscription; subscribe mới có thể chạy lại pipeline. **Hot Publisher** (ví dụ một `Sinks.Many` phát liên tục) có thể phát dữ liệu trước khi subscriber xuất hiện; subscriber vào sau có thể bỏ lỡ sự kiện tùy loại sink và replay/buffer policy.

| Nguồn | Nếu subscriber đến muộn | Chú ý |
|---|---|---|
| `Flux.just` | Có thể nhận toàn bộ dữ liệu khi subscribe | Finite; hoàn tất nhanh |
| `Flux.defer` | Tạo publisher khi mỗi subscription diễn ra | Tác vụ side effect có thể chạy lại |
| `Sinks.Many` multicast | Có thể mất hoặc từ chối phát khi không có subscriber, tùy loại sink | Theo dõi `EmitResult` |
| `replay()`/replay sink | Có thể phát lại một phần dữ liệu theo cấu hình | Giới hạn memory/retention |
| Broker consumer flux | Lấy dữ liệu theo cơ chế binder và broker | Ack/offset không giống replay trong bộ nhớ |

Không “sửa” sự cố thiếu subscriber bằng cách đặt `share()` hoặc `cache()` bừa bãi. Những operator này đổi lifetime và replay semantics; có thể tạo late-subscriber data loss hoặc memory pressure.

## 3. Spring Cloud Stream gọi reactive Function như thế nào?

Imperative function:

~~~java
@Bean
Function<String, String> upperCase() {
    return value -> value.toUpperCase(Locale.ROOT);
}
~~~

Thường được framework gọi **mỗi message một lần**. Reactive function lại được gọi chủ yếu lúc khởi tạo đường xử lý để lấy Publisher:

~~~java
@Bean
Function<Flux<String>, Flux<String>> upperCase() {
    return inbound -> inbound
            .map(value -> value.toUpperCase(Locale.ROOT))
            .doOnSubscribe(s -> log.info("reactive processing subscribed"))
            .doOnNext(value -> log.debug("transformed item"));
}
~~~

Đối với reactive function, phần lambda `inbound -> ...` thường được framework gọi **một lần để lắp chuỗi Flux**; điều đó không có nghĩa chỉ xử lý một event. Từng message được xử lý qua các operator khi Publisher đã được framework kết nối và subscribe.

### 3.1. Cấu hình binding chuẩn

~~~yaml
spring:
  cloud:
    function:
      definition: upperCase
    stream:
      bindings:
        upperCase-in-0:
          destination: raw.events
          group: uppercase-processors
        upperCase-out-0:
          destination: normalized.events
~~~

Các tên `upperCase-in-0` và `upperCase-out-0` được suy từ tên function bean. Tên cấu hình phải khớp chính xác. Khi ứng dụng có nhiều function, nên khai báo `spring.cloud.function.definition` để framework bind đúng function. Nếu bạn khai báo một bean nhưng không đưa nó vào definition được kích hoạt, việc bean tồn tại không chứng minh nó được nối vào broker.

### 3.2. Lỗi trả về Publisher rồi tự subscribe phụ

~~~java
// Mẫu cần tránh: tạo subscription riêng và trả Flux khác.
@Bean
Function<Flux<String>, Flux<String>> badFunction() {
    return inbound -> {
        inbound.map(this::expensiveOperation).subscribe();
        return inbound;
    };
}
~~~

Đoạn code trên tạo một subscription “ngoài luồng” với side effect không nằm trong Publisher trả về. Có thể làm nguồn bị consume hai lần, xử lý trùng, lỗi không tới output/error handling, hoặc tạo subscription không có lifecycle cleanup. Hãy mô tả toàn bộ xử lý bên trong Publisher được **trả về**:

~~~java
@Bean
Function<Flux<String>, Flux<String>> goodFunction() {
    return inbound -> inbound
            .map(this::expensiveOperation)
            .doOnError(error -> log.error("processing failed", error));
}
~~~

Nếu `expensiveOperation` là blocking I/O, không gọi trực tiếp trong `map` trên thread reactive; mục về scheduler sẽ trình bày cách xử lý.

## 4. Consumer<Flux<T>>: nguyên nhân thiếu subscriber phổ biến

`Consumer<Flux<T>>` có kiểu trả về `void`. Framework không nhận được Publisher từ lời gọi `accept(flux)` để subscribe. Vì thế một consumer reactive chỉ xây pipeline rồi bỏ mặc là **không xử lý message**.

### 4.1. Ví dụ sai: dựng pipeline nhưng không subscribe

Việc đặt các operator trong thân một Consumer không khiến chúng tự chạy:

~~~java
@Bean
Consumer<Flux<OrderCreated>> brokenSink() {
    return input -> {
        Flux<OrderCreated> unused = input
                .map(order -> {
                    log.info("would process {}", order.orderId());
                    return order;
                });
        // Không làm gì với unused.
    };
}
~~~

Bean có thể được gọi để thiết lập luồng nhưng không có subscriber, nên mapper và repository không chạy.

### 4.2. Cách ưu tiên: Function<Flux<T>, Mono<Void>>

Tài liệu Spring Cloud Stream khuyến nghị với reactive sink có thể dùng `Function<Flux<T>, Mono<Void>>`. Khi function **trả** `Mono<Void>`, framework giữ Publisher để subscribe:

~~~java
@Bean
Function<Flux<OrderCreated>, Mono<Void>> persistOrders(OrderService service) {
    return input -> input
            .concatMap(service::saveReactively)
            .doOnSubscribe(s -> log.info("persistOrders subscribed"))
            .doOnError(error -> log.error("persistOrders failed", error))
            .doFinally(signal -> log.warn(
                    "persistOrders terminated: {}", signal))
            .then();
}
~~~

Giả sử `OrderService.saveReactively(OrderCreated)` trả về `Mono<Void>` và hoàn tất **sau khi dữ liệu đã được lưu bền vững**. `concatMap` giúp xử lý tuần tự (phù hợp trường hợp cần giữ thứ tự), còn `then()` tạo một Mono kết thúc khi input hoàn tất, không phát payload.

Ví dụ binding cho sink:

~~~yaml
spring:
  cloud:
    function:
      definition: persistOrders
    stream:
      bindings:
        persistOrders-in-0:
          destination: orders.created
          group: order-persistence
~~~

Đây là kiểu được tài liệu framework khuyến nghị để tránh mất subscription. Nếu phiên bản binder cụ thể cần xử lý offset/ack riêng, vẫn phải cấu hình và kiểm chứng theo broker; có subscriber **không** tự bảo đảm at-least-once.

### 4.3. Nếu bắt buộc dùng Consumer<Flux<T>>

Khi API/lifecycle yêu cầu reactive Consumer, subscribe một lần và quản lý Disposable:

~~~java
@Component
class OrderSinkSubscription {
    private final AtomicReference<Disposable> current =
            new AtomicReference<>();

    Consumer<Flux<OrderCreated>> consumer(OrderService service) {
        return input -> {
            Disposable subscription = input
                    .concatMap(service::saveReactively)
                    .doOnSubscribe(s -> log.info("sink subscribed"))
                    .doOnError(e -> log.error("sink terminated", e))
                    .doFinally(s -> log.info("sink finished: {}", s))
                    .subscribe(
                            ignored -> { },
                            error -> log.error("terminal error", error));
            Disposable previous = current.getAndSet(subscription);
            if (previous != null) {
                previous.dispose();
            }
        };
    }

    @PreDestroy
    void close() {
        Disposable subscription = current.getAndSet(null);
        if (subscription != null) {
            subscription.dispose();
        }
    }
}

@Configuration
class SinkConfiguration {
    @Bean
    Consumer<Flux<OrderCreated>> orderSink(
            OrderSinkSubscription subscription,
            OrderService service) {
        return subscription.consumer(service);
    }
}
~~~

Ví dụ minh họa chủ sở hữu của subscription và phương thức cleanup. `dispose()` gây cancel, không chờ chắc chắn mọi thao tác bất đồng bộ đã hoàn tất. Với production, cần thiết kế shutdown/drain, phối hợp offset/ack và hiểu publisher có hỗ trợ cancel an toàn không. Đừng gọi `subscribe()` nhiều lần trên cùng inbound Flux hoặc mỗi message nếu chỉ cần một subscription.

**Không dùng `subscribe()` như cách sửa mặc định cho mọi reactive pipeline.** Với reactive `Function`, đó thường là antipattern; với explicit reactive `Consumer`, nó là trách nhiệm của ứng dụng.

## 5. Functional composition có thể biến Function thành Consumer

Spring Cloud Function hỗ trợ composition, ví dụ:

~~~properties
spring.cloud.function.definition=transform|sink
~~~

Khi một reactive Function được ghép với một imperative Consumer, kết quả composition có thể trở thành reactive Consumer với kiểu trả `void`. Khi đó framework không thể tự lấy Publisher cuối cùng để subscribe. Vì vậy một pipeline trước đây chạy khi đứng một mình có thể dừng khi thêm consumer cuối chuỗi.

Kiểm tra:

1. Type Java thực sự của từng bean: `Function<Flux<A>, Flux<B>>` hay `Consumer<B>`?
2. Type kết quả sau composition là Function, Consumer hay Supplier?
3. Có terminal Subscriber được tạo đúng lifecycle không?
4. Có thể chuyển consumer cuối thành xử lý reactive nằm trong `Function<Flux, Mono<Void>>` không?
5. Nếu không, liệu mô hình imperative theo message có dễ quản lý hơn không?

Không đánh giá chỉ qua `spring.cloud.function.definition`; một composition hợp lệ về cú pháp vẫn có thể khiến đoạn cuối không được subscribe theo kỳ vọng.

## 6. Phân biệt onComplete, onError và cancel

Ba tình huống này dẫn tới pipeline không còn xử lý data, nhưng cách phục hồi khác nhau.

### 6.1. onComplete: nguồn hữu hạn đã kết thúc

~~~java
@Bean
Supplier<Flux<String>> sampleSupplier() {
    return () -> Flux.just("a", "b", "c");
}
~~~

Đây là Supplier reactive **hữu hạn**. Với Spring Cloud Stream, reactive Supplier thường được khởi tạo/được gọi một lần để cung cấp stream. Sau ba phần tử, nguồn hoàn tất. Nó không tự “sống lại” mỗi giây như imperative Supplier được poll.

Nếu mục đích là định kỳ tạo một tập dữ liệu hữu hạn, có thể dùng `@PollableBean` theo tài liệu Spring Cloud Function:

~~~java
@PollableBean(splittable = true)
Supplier<Flux<String>> pollSomeRecords() {
    return () -> Flux.just("a", "b", "c");
}
~~~

Điều này báo cho framework biết Supplier là finite và có thể cần poll. Không dùng một finite Flux trong vai trò stream vô hạn rồi kết luận pipeline hỏng khi nhận `onComplete`.

### 6.2. onError: một exception kết thúc stream

~~~java
Flux<String> values = Flux.just("ok", "bad", "later");

values.map(value -> {
    if (value.equals("bad")) {
        throw new IllegalStateException("unexpected data");
    }
    return value;
}).subscribe(
        value -> log.info("next {}", value),
        error -> log.error("terminated", error));
~~~

Khi gặp `bad`, stream phát `onError` và kết thúc. `later` không được xử lý trong subscription đó. Với một function chạy lâu trên broker input, lỗi không được xử lý có thể làm mất subscriber; nếu broker vẫn tiếp tục nhận message, backlog sẽ tăng.

### 6.3. cancel: subscriber bị hủy

Cancel có thể đến từ `take(n)`, `timeout`, `switchMap` thay thế inner source, ứng dụng gọi `dispose()` hoặc shutdown của binder/lifecycle.

~~~java
Flux<Long> shortStream = Flux.interval(Duration.ofSeconds(1))
        .take(3)
        .doFinally(signal -> log.info("finished: {}", signal));
~~~

`take(3)` cố ý giới hạn luồng. Nếu operator này lỡ nằm trong pipeline event vô hạn, sau ba event subscriber sẽ dừng. Không dùng `take(1)` trong code production để “test nhanh” rồi quên xóa.

### 6.4. Phân biệt bằng logging

~~~java
Function<Flux<String>, Flux<String>> observed() {
    return input -> input
            .doOnSubscribe(s -> log.info("SUBSCRIBED"))
            .doOnRequest(n -> log.info("REQUEST {}", n))
            .doOnNext(v -> log.debug("NEXT"))
            .doOnError(e -> log.error("ERROR", e))
            .doOnCancel(() -> log.warn("CANCELLED"))
            .doFinally(signal -> log.warn("FINAL SIGNAL {}", signal));
}
~~~

Đặt instrumentation tại đầu luồng, sau các operator quan trọng và gần output binding nếu cần tìm nơi signal biến mất. Không ghi payload nhạy cảm hoặc event ID động vào metric tag; dùng log/tracing có kiểm soát.

## 7. Có subscriber nhưng không có demand

Reactive Streams yêu cầu downstream phát `request(n)` để nhận data. Nếu subscriber đã subscribe nhưng không request, Publisher tuân thủ backpressure có thể không phát `onNext`.

Ví dụ minh họa không request:

~~~java
Flux.range(1, 5).subscribe(new BaseSubscriber<Integer>() {
    @Override
    protected void hookOnSubscribe(Subscription subscription) {
        log.info("subscribed but no request");
        // Không request(1): không có item ở nguồn tôn trọng demand.
    }

    @Override
    protected void hookOnNext(Integer value) {
        log.info("next {}", value);
        request(1);
    }
});
~~~

Đây là ví dụ kỹ thuật Reactor độc lập, không phải một binder production. Khi debug, `doOnSubscribe` xuất hiện mà `doOnNext` không có, hãy kiểm tra `doOnRequest`, các operator làm chậm hoặc chặn downstream, nguồn dữ liệu, scheduler và binder. Không suy ra ngay lỗi thiếu subscriber.

Trong regular Kafka/Rabbit binder, sử dụng kiểu Flux **không có nghĩa** broker có backpressure end-to-end tương đương Reactive Streams. Việc giảm demand ở ứng dụng không nhất thiết điều khiển trực tiếp tốc độ broker giao data.

## 8. Block() và I/O đồng bộ có thể làm pipeline đứng

Một nguồn khác của hiện tượng ngừng xử lý là **subscriber vẫn tồn tại nhưng thread hoặc scheduler bị nghẽn**.

Mẫu dễ gây vấn đề:

~~~java
@Bean
Function<Flux<OrderCreated>, Flux<OrderAccepted>> badBlocking() {
    return source -> source.map(order -> {
        // Repository truy cập DB đồng bộ hoặc HTTP call blocking.
        String result = blockingRemoteClient.call(order.orderId());
        return new OrderAccepted(order.orderId(), result);
    });
}
~~~

Nếu chạy trên event-loop hoặc scheduler dùng cho tác vụ nonblocking, I/O đồng bộ có thể làm nghẽn các signal khác; một số trường hợp gọi `block()` từ thread nonblocking sẽ bị Reactor từ chối bằng exception.

Nếu chưa thể thay dependency bằng API nonblocking, có thể cô lập lời gọi blocking:

~~~java
@Bean
Function<Flux<OrderCreated>, Flux<OrderAccepted>> boundedBlocking() {
    return source -> source.concatMap(order ->
            Mono.fromCallable(() ->
                    new OrderAccepted(
                            order.orderId(),
                            blockingRemoteClient.call(order.orderId())))
                .subscribeOn(Schedulers.boundedElastic()));
}
~~~

`boundedElastic` dành cho việc chuyển các tác vụ blocking có kiểm soát sang thread pool phù hợp, không biến API blocking thành nonblocking. Cần giới hạn concurrency, timeout, connection pool và số tác vụ chờ. Nếu nghiệp vụ cho phép xử lý song song, có thể dùng `flatMap(..., concurrency)` nhưng phải hiểu tác động tới thứ tự message và acknowledgment.

## 9. Không nhầm reactive API với reactive binder

Spring Cloud Stream cho phép định nghĩa `Function<Flux<T>, Flux<R>>` ngay cả khi dùng regular Kafka binder hoặc RabbitMQ binder. Tuy nhiên, reactive Publisher trong business function **không đồng nghĩa toàn tuyến từ broker tới producer đã có Reactive Streams backpressure**.

| Binder | Consumer/producer nền tảng | Điều cần lưu ý |
|---|---|---|
| Regular Kafka binder | Spring for Apache Kafka message-listener container | Reactive API bên trong function; không giả định backpressure end-to-end |
| Kafka Reactive Binder | Reactor Kafka `KafkaReceiver` và `KafkaSender` | Hỗ trợ reactive end-to-end; ack/offset semantics riêng |
| RabbitMQ binder | Spring AMQP/Spring Integration | Queue delivery, prefetch và consumer ack; không phải Kafka Reactor |
| Pulsar binder | Tùy thế hệ binder/client và hỗ trợ reactive | Kiểm tra subscriber/ack theo implementation thực tế |

Artifact Kafka Reactive Binder:

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-stream-binder-kafka-reactive</artifactId>
</dependency>
~~~

Chỉ dùng artifact này với version được BOM hỗ trợ và khi thực sự cần mô hình reactive Kafka. Không thêm đồng thời hai binder Kafka để “sửa” một luồng im lặng nếu chưa kiểm tra type selection và binding. Điều chỉnh Binder cần có integration test vì có thể thay semantics offset, retry, conversion và backpressure.

## 10. Kafka Reactive Binder: subscriber không thay thế ack

Trong Kafka Reactive Binder, mặc định offset **không tự commit** theo cách giống regular Kafka binder. Theo tài liệu bản 4.0.2 trở lên, message nhận có thể chứa header `KafkaHeaders.ACKNOWLEDGMENT` mang `ReceiverOffset` để ứng dụng xác nhận sau khi xử lý. `reactiveAtmostOnce` và `reactiveAutoCommit` là hai lựa chọn khác, có semantics khác nhau và không có acknowledgment header trong những mode đó.

| Mode | Điểm commit offset | Rủi ro |
|---|---|---|
| Manual ack/commit | Ứng dụng gọi acknowledge/commit sau xử lý | Quên ack làm lag; ack sớm có thể làm mất side effect |
| `reactiveAtmostOnce=true` | Binder commit trước khi xử lý các record poll | Có thể mất tác dụng nghiệp vụ khi crash |
| `reactiveAutoCommit=true` | Binder auto commit theo batch đã xử lý | Cần hiểu batch Flux lồng nhau, failure semantics |

Trong mode manual, cần **đảm bảo side effect hoàn tất trước ack**. Ví dụ minh họa Reactor flow:

~~~java
@Bean
Function<Flux<Message<OrderCreated>>, Mono<Void>> consumeOrders(
        OrderService service) {

    return inbound -> inbound.concatMap(message ->
            service.saveReactively(message.getPayload())
                .doOnSuccess(ignored -> {
                    ReceiverOffset offset = message.getHeaders()
                            .get(KafkaHeaders.ACKNOWLEDGMENT,
                                 ReceiverOffset.class);
                    if (offset != null) {
                        offset.acknowledge();
                    }
                }))
        .doOnError(e -> log.error("reactive Kafka sink failed", e))
        .then();
}
~~~

Các import cần có gồm `reactor.core.publisher.Flux`, `reactor.core.publisher.Mono`, `org.springframework.messaging.Message`, `org.springframework.kafka.support.KafkaHeaders` và `reactor.kafka.receiver.ReceiverOffset`. Ví dụ giả định đúng Kafka Reactive Binder/version, mode manual và `saveReactively` thực sự hoàn tất sau khi lưu bền vững. Nó không áp dụng cho regular Kafka binder, nơi acknowledgment header có thể là kiểu Spring Kafka `Acknowledgment`. Hãy kiểm tra version API và không ack trong `doOnNext` trước khi một `Mono` xử lý bất đồng bộ hoàn tất.

**Chú ý lỗi nguy hiểm:** sửa pipeline thiếu subscriber bằng `subscribe()` mà quên acknowledgment khiến application có log “processed” nhưng committed offsets không tiến. Khi crash, record được giao lại. Ngược lại, ack quá sớm có thể bỏ qua side effect khi crash.

### 10.1. Mode reactiveAutoCommit có Flux lồng nhau

Tài liệu Kafka Reactive Binder mô tả `reactiveAutoCommit` có thể tạo cấu trúc `Flux<Flux<ConsumerRecord<...>>>`, trong đó inner Flux tương ứng tập record của một poll/batch. Ứng dụng phải xử lý đúng các inner Flux và native deserializer; không chỉ subscribe outer Flux rồi bỏ inner Flux.

Không đổi sang `reactiveAutoCommit` chỉ để làm metric lag giảm. Hãy kiểm tra cả payload conversion, acknowledgment, batch completion và failure test. Chức năng này từng có semantics khác ở các patch version cũ, vì vậy kiểm tra documentation khớp version triển khai.

## 11. onError là terminal: thiết kế recovery ở đâu?

Trong Reactor, lỗi không được xử lý đi tới Subscriber dưới dạng `onError` và kết thúc subscription. Một pipeline nối broker có thể nhận 100 event thành công, gặp event thứ 101 lỗi và không bao giờ nhận event tiếp theo. Đây là lý do quan trọng khiến monitoring phải ghi **terminal signal** chứ không chỉ đếm exception của từng message.

### 11.1. Sai: bắt lỗi ở cuối rồi kết thúc toàn luồng

~~~java
Function<Flux<OrderEvent>, Flux<OrderResult>> badRecovery() {
    return incoming -> incoming
            .map(this::transform)
            .onErrorResume(error -> {
                log.error("failed", error);
                return Flux.empty();
            });
}
~~~

`onErrorResume` ở đây áp dụng cho **lỗi của toàn upstream Flux**. Khi một event làm `transform` ném exception, pipeline chuyển sang `Flux.empty()` và kết thúc. Nó **không quay lại** xử lý các event tiếp theo. Nếu handler cần tiếp tục sau một lỗi nghiệp vụ riêng lẻ, phải cấu trúc recovery theo phạm vi **mỗi event**.

### 11.2. Đúng mục tiêu hơn: xử lý lỗi bên trong mỗi Mono

~~~java
@Bean
Function<Flux<OrderEvent>, Mono<Void>> resilientSink(
        OrderService service,
        QuarantineService quarantine) {

    return source -> source.concatMap(event ->
            Mono.defer(() -> service.process(event))
                .timeout(Duration.ofSeconds(10))
                .retryWhen(Retry.backoff(3, Duration.ofMillis(250))
                        .filter(error -> error instanceof TimeoutException))
                .onErrorResume(error -> {
                    log.error("event failed after retries", error);
                    return quarantine.storeDurably(event, error);
                }))
        .doOnError(error -> log.error(
                "terminal upstream or recovery error", error))
        .doFinally(signal -> log.warn(
                "resilientSink stopped: {}", signal))
        .then();
}
~~~

Giả định `OrderService.process` và `QuarantineService.storeDurably` đều trả `Mono<Void>`. `Mono.defer` khiến việc gọi service được tạo lại khi retry; `retryWhen` chỉ retry phần xử lý của một event; `onErrorResume` chuyển event lỗi sang nơi lưu bền vững. Khi quarantine thành công, chuỗi có thể tiếp tục với event khác.

Đây là mẫu điều khiển lỗi trong pipeline, **chưa phải bảo đảm giao nhận cuối cùng**. Nếu dùng manual ack, ứng dụng cần ack khi xử lý nghiệp vụ hoặc lưu quarantine đã bền vững. Nếu quarantine cũng thất bại, lỗi phải được đưa tới cơ chế redelivery/dừng/pause được thiết kế; không tự động bỏ message rồi báo xử lý thành công.

**Lưu ý về retry:** timeout/cancellation có thể xảy ra sau khi side effect đã thực hiện nhưng trước khi ứng dụng nhận response. Retry có thể tạo side effect lặp; dùng event ID/idempotency key và transaction database hoặc API idempotent cho hành động quan trọng.

### 11.3. Tránh onErrorComplete và onErrorContinue khi chưa rõ hậu quả

- `onErrorComplete()` biến lỗi thành complete, có thể khiến subscription vô hạn kết thúc âm thầm.
- `onErrorReturn(...)` có thể tạo một giá trị giả rồi kết thúc upstream sau lỗi.
- `onErrorContinue(...)` có semantics phụ thuộc operator và có thể làm trạng thái khó suy luận; Reactor khuyến nghị xử lý lỗi trong inner Publisher nếu muốn cô lập từng item.
- `retry()` ở cấp toàn pipeline có thể resubscribe nguồn, nhưng với nguồn hot hoặc broker consumer có thể phát sinh replay, duplicate hoặc vòng lặp lỗi liên tục.

Không dùng các operator này chỉ để làm log lỗi biến mất. Mọi nhánh lỗi cần policy: retry có giới hạn, quarantine/DLQ, redelivery, cảnh báo hoặc dừng có chủ đích.

### 11.4. Retry của binder imperative không mặc định áp dụng cho reactive Function

Spring Cloud Stream áp dụng cơ chế retry/error handling ở tầng framework cho imperative function được gọi theo từng message. Reactive function thường chỉ được gọi một lần lúc lắp Publisher; sau đó framework không có cùng khả năng bọc từng invocation. Vì vậy, không giả định `maxAttempts`, `retryableExceptions` hoặc binder DLQ config sẽ xử lý exception phát sinh **bên trong** Reactor chain như với imperative handler.

Đối với reactive function, phải chọn operator Reactor và cơ chế broker ack/retry tương ứng. Một DLQ được cấu hình ở broker có thể vẫn xử lý một số loại lỗi transport/deserialization, nhưng không có nghĩa mọi lỗi async trong `flatMap` đều tự tới đó. Kiểm thử từng lỗi bằng integration test.

## 12. Các operator khiến pipeline “im lặng” ngoài ý muốn

Một số operator không gây exception nhưng chặn hoặc kết thúc output:

| Operator | Bẫy phổ biến | Cách nhận diện |
|---|---|---|
| `filter` | Predicate luôn false | Đếm số item trước/sau filter |
| `take(n)` | Hoàn tất sau n message | Xem `doFinally` = onComplete/cancel |
| `next()` | Chỉ lấy phần tử đầu từ Flux | Kiểm tra chữ ký trả Mono |
| `takeUntil`/`takeWhile` | Điều kiện kết thúc sớm | Log điều kiện; test boundary |
| `timeout` | Không có item trong khoảng thời gian → onError | Kiểm tra timeout log, retry policy |
| `onErrorResume(Flux.empty())` | Lỗi bị chuyển thành complete | Tìm global fallback |
| `ignoreElements`/`then()` | Bỏ output `onNext` có chủ đích | Chỉ dùng cho sink không có output |
| `zip` với một Mono empty | Không có tuple đầu ra | Đếm emission từng nhánh |
| `switchMap` | Hủy inner task cũ khi event mới tới | Dùng `flatMap`/`concatMap` nếu không muốn cancel |
| `collectList` trên Flux vô hạn | Chờ complete rồi mới emit | Tránh gom toàn bộ stream vô hạn |
| `buffer`/`window` | Chờ đủ số item/thời gian trước khi phát | Kiểm tra size, timeout, demand |
| `publish().autoConnect(n)` | Chưa đủ n subscriber nên chưa connect | Theo dõi số subscriber |
| `publish().refCount(n)` | Có thể disconnect khi subscriber giảm | Xác minh lifecycle và refCount |

### 12.1. Đừng đợi Flux vô hạn complete

~~~java
// Anti-pattern: stream từ broker không bao giờ complete bình thường.
Mono<List<OrderEvent>> allEvents = incoming.collectList();
~~~

Nếu `incoming` là live event stream, `collectList` không phát kết quả trước khi upstream complete, đồng thời có thể giữ vô hạn phần tử trong RAM. Với aggregation, hãy dùng `bufferTimeout`, `windowTimeout`, window theo key hoặc state store đúng mục tiêu và giới hạn dung lượng.

### 12.2. switchMap có thể hủy công việc đang chạy

~~~java
Flux<OrderResult> results = incoming
        .switchMap(service::processAndReturn);
~~~

Khi event mới đến trước khi inner Publisher cũ hoàn tất, `switchMap` hủy subscription cũ. Với xử lý đơn hàng, đó thường không phải semantics mong muốn. Dùng `concatMap` để giữ thứ tự và chỉ một công việc tại một thời điểm, hoặc `flatMap(..., concurrency)` khi có thể xử lý song song và side effect chịu được đảo thứ tự.

### 12.3. flatMap không giới hạn hợp lý có thể làm downstream nghẽn

`flatMap` cho phép nhiều inner Publisher hoạt động đồng thời, và với backend chậm có thể làm số request chờ, connection và buffer tăng. Cấu hình concurrency hữu hạn:

~~~java
Flux<OrderResult> results = incoming.flatMap(
        event -> service.processAndReturn(event)
                .timeout(Duration.ofSeconds(8)),
        16);
~~~

Giá trị `16` chỉ minh họa. Đo database pool, HTTP client limits, ordering và ack semantics trước khi điều chỉnh; tăng concurrency không thay thế khả năng backpressure của binder.

## 13. Reactive Supplier được gọi một lần và nguồn bị hoàn tất

Spring Cloud Function phân biệt imperative `Supplier<T>` (thường được poll) với reactive `Supplier<Flux<T>>` (thường trả stream chạy liên tục và được invoke một lần).

### 13.1. Dùng finite Supplier rồi chờ message mới

~~~java
@Bean
Supplier<Flux<String>> threeMessagesOnly() {
    return () -> Flux.just("one", "two", "three");
}
~~~

Nếu ứng dụng chỉ phát ba message rồi ngừng, đó là hành vi đúng của finite Flux, không phải subscriber chết. Nếu cần nguồn vô hạn, hãy thiết kế Publisher sống lâu đúng cách, ví dụ nguồn Reactor/connector phát khi có sự kiện, có kiểm soát lifecycle/cancel.

### 13.2. Đừng dùng share để tạo luồng vô hạn giả

`share()` biến cold source thành hot khi có subscription, nhưng **không biến** `Flux.just` hữu hạn thành vô hạn. Sau khi phát hết, stream vẫn hoàn tất. `repeat()` có thể lặp lại dữ liệu, nhưng với sự kiện nghiệp vụ dễ tạo duplicate không mong muốn.

### 13.3. Finite source có thể được poll theo chủ đích

Với chức năng đọc dữ liệu hàng loạt định kỳ, `@PollableBean` có thể báo framework rằng reactive Supplier finite cần được poll theo cơ chế tương thích. Kiểm tra `spring.integration.poller.*` và per-binding poller settings, không dùng polling để chữa một output publisher bị lỗi hoặc bị cancel.

## 14. Hot Sinks: emit trước khi subscriber có mặt

Với nguồn ngoại lai (HTTP/websocket, callback SDK, custom connector), developer có thể dùng `Sinks.Many` làm cầu nối:

~~~java
class EventGateway {
    private final Sinks.Many<String> sink =
            Sinks.many().multicast().directBestEffort();

    Sinks.EmitResult publish(String value) {
        return sink.tryEmitNext(value);
    }

    Flux<String> flux() {
        return sink.asFlux();
    }
}
~~~

Với `multicast().directBestEffort()`, khi không có subscriber, phát dữ liệu có thể nhận `FAIL_ZERO_SUBSCRIBER`. Nếu code bỏ qua `EmitResult`, upstream có thể nghĩ message đã được chuyển đi mặc dù không có consumer. Khi dùng Sinks:

1. Kiểm tra `EmitResult` thay vì coi mọi lời gọi emit là thành công.
2. Đăng ký subscriber trước khi chấp nhận event, hoặc chọn replay/buffer phù hợp.
3. Nếu sự kiện quan trọng, dùng hàng đợi/nhật ký bền vững (Kafka/RabbitMQ/Pulsar) thay vì chỉ giữ trong RAM.
4. Giới hạn buffer và có policy khi overflow/backpressure.
5. Đóng hoặc phát error/complete có chủ đích khi shutdown.

In-memory sink không tự cung cấp replay sau process crash. Đổi từ direct-best-effort sang replay/buffer có thể giảm mất event trước subscriber nhưng tăng sử dụng RAM và thay semantics, nên cần thiết kế retention rõ ràng.

## 15. Xác minh Function đã được bind thật

Khi Reactor code đúng nhưng không có event, quay lại Spring Cloud Stream wiring. Bean tồn tại trong Spring context **không đủ**; nó phải được chọn và bind vào đúng middleware.

### 15.1. Kiểm tra definition và binding name

~~~yaml
spring:
  cloud:
    function:
      definition: normalize
    stream:
      bindings:
        normalize-in-0:
          destination: raw.orders
          group: normalize-service
        normalize-out-0:
          destination: clean.orders
~~~

Java:

~~~java
@Bean
Function<Flux<OrderEvent>, Flux<OrderEvent>> normalize() {
    return source -> source.map(this::normalizeEvent);
}
~~~

Với function `normalize`, tên đúng là `normalize-in-0` và `normalize-out-0`. Những lỗi thường gặp:

- Property `definition` trỏ sang một bean khác.
- Bean tên `normalize` không phải bean functional được chọn.
- Có nhiều bean `Supplier`/`Function`/`Consumer` mà không chọn definition tường minh.
- Property `spring.cloud.stream.function.autodetect=false` làm tắt auto-discovery trong cấu hình khác.
- Đổi sang function composition nhưng không cập nhật binding name/alias.
- Input destination, consumer group, binder name, serializer/deserializer hoặc content type sai.
- Output binding chưa khai báo đúng hoặc middleware đích không thể publish.

Không kết luận do thiếu subscriber nếu ngay cả `BindingService` chưa bind input.

### 15.2. Kiểm tra actuator bindings khi được hỗ trợ

Nếu application có Spring Boot Actuator và endpoint bindings của Spring Cloud Stream được bật ở version hiện dùng, có thể kiểm tra trạng thái binding qua `/actuator/bindings`. Endpoint và quyền truy cập phải được cấu hình tường minh; không expose actuator công khai.

Ví dụ cấu hình có thể dùng:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics,bindings
~~~

Hãy xem binding có `STARTED`, `STOPPED` hoặc trạng thái khác theo binder/version. Endpoint này giúp chẩn đoán binding lifecycle, **không chứng minh** mọi Reactor subscription bên trong function vẫn sống hoặc message nghiệp vụ đã được xử lý.

### 15.3. Phân biệt đúng broker source

| Broker | Điều cần kiểm tra |
|---|---|
| Kafka | Topic, group ID, partition assignment, committed offset, lag, deserialization error |
| RabbitMQ | Queue name/vhost, exchange binding, ready/unacked, số consumer, ack/prefetch |
| Pulsar | Topic/subscription name/type, backlog, cursor, ack/redelivery, authentication |

Kafka group có 6 consumer trên topic 3 partition có thể khiến vài consumer không được assign partition; những instance ấy không có event dù reactive subscription hợp lệ. RabbitMQ cùng queue chia delivery giữa các consumer; một instance có thể nhận ít event. Pulsar subscription type (Shared/Failover/Key_Shared) cũng ảnh hưởng phân phối. Hãy kiểm tra broker state trước khi thêm `subscribe()` vào code.

## 16. Logging Reactor đúng vị trí

Đặt log ở nhiều vị trí để biết event biến mất ở bước nào:

~~~java
@Bean
Function<Flux<String>, Flux<String>> tracePipeline() {
    return input -> input
            .doOnSubscribe(s -> log.info("01 input subscribed"))
            .doOnRequest(n -> log.debug("02 requested {}", n))
            .doOnNext(v -> log.debug("03 input event received"))
            .map(this::normalize)
            .doOnNext(v -> log.debug("04 after normalize"))
            .filter(this::isAllowed)
            .doOnNext(v -> log.debug("05 after filter"))
            .doOnError(e -> log.error("06 error", e))
            .doFinally(signal -> log.warn("07 terminal {}", signal))
            .checkpoint("normalize-orders");
}
~~~

Diễn giải:

- Không có `01`: không có subscription trên Publisher được instrument, hoặc function không được gắn.
- Có `01`, không có `02`: điều tra downstream demand; cũng kiểm tra nguồn.
- Có `02`, không có `03`: broker có data chưa, group assignment thế nào?
- Có `03`, không có `04`: xử lý transform có throw/block/cancel?
- Có `04`, không có `05`: predicate filter có loại mọi event?
- Có `06` hoặc `07`: xem nguyên nhân terminal và nơi subscriber bị mất.

`checkpoint("normalize-orders")` gắn nhãn assembly để trace đường lỗi với chi phí thấp hơn `Hooks.onOperatorDebug()` toàn cục. Chỉ bật global debug hook trong thời gian chẩn đoán hoặc môi trường test nếu cần, vì việc capture stack trace cho mọi operator có chi phí đáng kể.

### 16.1. Không log từng payload ở production

Logging `onNext` cho mọi event ở lưu lượng cao sẽ tốn I/O và có thể lộ dữ liệu. Dùng sampling, aggregate counters, event ID/correlation ID có kiểm soát, error trace và metric. Không dùng event ID/user ID làm Prometheus label vì cardinality tăng không giới hạn.

## 17. Metrics xác định subscription còn sống

Theo dõi đồng thời:

| Metric/tín hiệu | Ý nghĩa |
|---|---|
| `stream.reactive.subscriptions.started` | Tổng lượt onSubscribe |
| `stream.reactive.subscriptions.active` | Số subscription đang hoạt động (gauge) |
| `stream.reactive.termination` | Complete/error/cancel theo nhãn hữu hạn |
| `stream.messages.received` | Tổng số event đi vào pipeline |
| `stream.messages.processed` | Số event xử lý thành công |
| `stream.messages.failed` | Số event lỗi |
| `stream.processing.duration` | Timer/histogram thời gian xử lý |
| `stream.last.onnext.age` | Thời gian từ onNext gần nhất |
| Kafka consumer lag | Record còn tồn ở group/partition |
| RabbitMQ ready/unacked | Message trong queue đã chờ/đã giao |
| Pulsar subscription backlog | Message chưa được subscription xử lý |

Các tên `stream.*` là **metric do ứng dụng tự định nghĩa**, không phải metric mặc định chắc chắn có trong Spring Cloud Stream. Trạng thái subscription nên được ghi nhận từ `doOnSubscribe`/`doFinally` hoặc lifecycle phù hợp, không suy diễn từ Actuator health.

Ví dụ tăng/giảm gauge:

~~~java
AtomicInteger subscriptions = new AtomicInteger();

Gauge.builder("stream.reactive.subscriptions.active", subscriptions,
        AtomicInteger::get)
    .tag("binding", "normalize-in-0")
    .register(meterRegistry);

Flux<String> observed = incoming
        .doOnSubscribe(s -> subscriptions.incrementAndGet())
        .doFinally(signal -> subscriptions.decrementAndGet());
~~~

Đây là instrumentation minh họa. Nên đăng ký gauge một lần trong component thay vì tạo lại meter mỗi message; cần đảm bảo một `doFinally` tương ứng một `doOnSubscribe` của cùng subscription. Nếu có nhiều replica, aggregate theo binding/instance nhưng giới hạn cardinality.

### 17.1. Đọc tín hiệu kết hợp

| Subscription active | Broker backlog | Xử lý thành công | Cách hiểu |
|---|---|---|---|
| 0 | Tăng | 0 | Có thể mất subscriber hoặc binding chưa start |
| 1 | Tăng | 0 | Có subscription nhưng bị block, demand=0 hoặc lỗi xử lý |
| 1 | 0 | 0 | Có thể nguồn thực sự không có message |
| 1 | Tăng | Tăng chậm | Thiếu capacity, downstream chậm hoặc retry |
| 1 | Giảm | Tăng | Pipeline đang rút backlog |

Với Kafka, nếu instance không được assign partition, `active=1` và không có `onNext` có thể bình thường. Đừng tạo alert chỉ dựa trên `lastOnNextAge` mà không xét event arrival rate và partition assignment.

## 18. Kiểm thử bằng StepVerifier

Project Reactor cung cấp `reactor-test` và `StepVerifier` để kiểm tra Publisher thực sự phát event, hoàn tất hay lỗi. Ví dụ unit test cho transform Function:

~~~java
@Test
void normalizeProcessesEveryItemOnSubscription() {
    Function<Flux<String>, Flux<String>> fn =
            input -> input.map(String::toUpperCase);

    StepVerifier.create(fn.apply(Flux.just("a", "b")))
            .expectNext("A", "B")
            .verifyComplete();
}
~~~

Lời gọi `StepVerifier.create` là Subscriber được test tạo, nên các operator của function mới được thực thi.

### 18.1. Test không subscriber thì không thực thi

~~~java
@Test
void coldSourceNeedsSubscriber() {
    AtomicInteger executions = new AtomicInteger();

    Flux<Integer> source = Flux.defer(() -> {
        executions.incrementAndGet();
        return Flux.just(1, 2);
    });

    assertEquals(0, executions.get());

    StepVerifier.create(source)
            .expectNext(1, 2)
            .verifyComplete();

    assertEquals(1, executions.get());
}
~~~

Test chứng minh với nguồn cold, chỉ assembly không chạy công việc. Nếu loại publisher là hot, semantics khác và cần test riêng.

### 18.2. Test lỗi ở từng phần tử

~~~java
@Test
void perEventRecoveryKeepsFollowingEvents() {
    Flux<Integer> source = Flux.just(1, 2, 3);
    Flux<Integer> result = source.concatMap(value ->
            Mono.fromCallable(() -> {
                if (value == 2) {
                    throw new IllegalArgumentException("bad event");
                }
                return value * 10;
            }).onErrorResume(error -> Mono.empty()));

    StepVerifier.create(result)
            .expectNext(10, 30)
            .verifyComplete();
}
~~~

Đây chỉ là test Reactor semantics; trong production, không được bỏ event lỗi nếu yêu cầu nghiệp vụ phải quarantine/DLQ hoặc redelivery. Test recovery thực tế cần xác minh lưu message lỗi bền vững.

### 18.3. Test terminal signal

~~~java
@Test
void unhandledErrorTerminatesFlux() {
    Flux<String> source = Flux.just("ok", "bad", "later")
            .map(value -> {
                if (value.equals("bad")) {
                    throw new IllegalStateException("broken");
                }
                return value;
            });

    StepVerifier.create(source)
            .expectNext("ok")
            .expectError(IllegalStateException.class)
            .verify();
}
~~~

Thêm test cancel (`thenCancel`), timeout (virtual time nếu thích hợp), hot sink không subscriber và lifecycle disposal khi phù hợp.

### 18.4. Test binder chứ không chỉ test Flux

Unit test `StepVerifier` không phát hiện:

- Sai `spring.cloud.function.definition`.
- Output binding không tồn tại.
- Kafka group không được assign partition.
- RabbitMQ queue hoặc Pulsar subscription sai tên.
- Kafka Reactive Binder không commit offset sau xử lý.
- Producer send thất bại sau khi callback `doOnNext` ghi log.

Hãy bổ sung Spring Cloud Stream Test Binder cho function/binding và **integration test với broker thật** (ví dụ Testcontainers Kafka/RabbitMQ) để kiểm tra startup, subscription, ack, retry, DLQ và process restart. Test Binder không mô phỏng đầy đủ semantics broker-specific.

## 19. Tình huống thực tế: reactive Kafka sink ngừng sau lỗi đầu tiên

Một ứng dụng dùng Kafka Reactive Binder đọc `orders.created` với function:

~~~java
@Bean
Function<Flux<OrderCreated>, Mono<Void>> sink(OrderService service) {
    return flux -> flux
            .flatMap(service::saveReactively)
            .then();
}
~~~

Ban đầu consumer xử lý bình thường. Khi một event lỗi DB, inner `Mono` phát `onError`; `flatMap` lan lỗi ra ngoài; `then()` cũng kết thúc lỗi; subscription chấm dứt. Spring Boot process vẫn có thể healthy theo HTTP. Event mới tích tụ ở Kafka và lag tăng.

Chẩn đoán:

1. Xác minh `sink-in-0` được bind và đúng Kafka group.
2. Kiểm tra `doOnSubscribe` đã chạy.
3. Thêm `doOnError`, `doFinally`, `checkpoint`.
4. Quan sát thấy terminal `ON_ERROR` ngay sau exception DB.
5. Kiểm tra mode ack/offset: message lỗi đã ack hay còn cần redelivery?
6. Đặt retry/quarantine **bên trong inner Mono mỗi event**.
7. Kiểm thử restart và duplicate delivery trước khi triển khai.

Mẫu khắc phục có thể là `resilientSink` ở mục 11, cộng với acknowledgment/quarantine rõ ràng. Không chỉ thêm `onErrorResume(error -> Mono.empty())` ở cuối: cách đó làm cả subscription complete và không xử lý event tiếp theo.

## 20. Runbook khi pipeline không còn xử lý message

### Bước 1 — Xác minh có message thật ở nguồn

Kiểm tra topic/queue/subscription và lượng message tại broker:

~~~bash
kafka-consumer-groups.sh \
  --bootstrap-server kafka.example.net:9092 \
  --describe \
  --group order-persistence
~~~

Với RabbitMQ, kiểm tra `messages_ready`, `messages_unacknowledged` và consumer count. Với Pulsar, kiểm tra subscription backlog và trạng thái consumer. Không bỏ qua quyền đọc, TLS và deserializer.

### Bước 2 — Xác minh function và binding

Kiểm tra bean name, `spring.cloud.function.definition`, input/output binding names, binder type, consumer group và destination. Xem log startup và `/actuator/bindings` nếu endpoint hỗ trợ và được bật. Một Bean được tạo nhưng không được bind chưa phải một reactive subscription.

### Bước 3 — Xác minh subscription và demand

Thêm `doOnSubscribe`, `doOnRequest`, `doOnNext` ở đầu Reactor pipeline. Nếu `Consumer<Flux>` chỉ dựng Publisher, chuyển sang `Function<Flux, Mono<Void>>` hoặc thiết lập subscription có lifecycle. Nếu là Function reactive, bỏ `subscribe()` phụ và trả đúng Publisher cho framework.

### Bước 4 — Tìm terminal signal

Thêm `doOnError`, `doOnCancel`, `doFinally`. Tìm `take`, `next`, `onErrorComplete`, `onErrorResume(Flux.empty())`, `timeout` và operator gộp chờ nguồn complete. Xem stack trace nhờ `checkpoint`.

### Bước 5 — Kiểm tra scheduler và downstream

Xem thread dump, connection pool, HTTP/DB latency, blocking calls và queue capacity. Đưa blocking operation sang scheduler phù hợp có giới hạn hoặc viết client nonblocking. Không tự tăng concurrency/timeout để giấu deadlock.

### Bước 6 — Kiểm tra offset, ack và retry

Với Kafka Reactive Binder, xác minh manual ack hoặc mode auto commit đúng semantics. Với regular Kafka/Rabbit/Pulsar binder, dùng cơ chế ack/transaction của binder đó, không copy code Reactor Kafka. Kiểm tra poison message, retry exhausted, DLQ và trạng thái subscription sau lỗi.

### Bước 7 — Phục hồi có kiểm soát

Nếu subscription đã terminal, nó không tự sống lại bằng cách chờ thêm. Khắc phục nguyên nhân và khởi tạo lại luồng qua lifecycle hợp lệ (ví dụ restart service có kiểm soát) **sau khi đã bảo đảm offset/ack và idempotency**. Không tạo vòng lặp resubscribe vô hạn với cùng record lỗi; có thể gây retry storm, duplicate và broker overload.

### Bước 8 — Xác nhận đã xử lý ổn định

Xem event tiếp tục đi qua các checkpoint, processed rate tăng, Kafka lag/Rabbit queue/Pulsar backlog giảm, terminal errors không lặp, DLQ theo chính sách và side effect không trùng. Theo dõi đủ lâu qua nhiều batch và tải cao; một event thành công chưa chứng minh lỗi đã hết.

## 21. Bảng quyết định sửa lỗi nhanh

| Bằng chứng | Chẩn đoán ưu tiên | Thay đổi nên thử |
|---|---|---|
| `Consumer<Flux>` tạo pipeline rồi return | Không subscribe | Dùng `Function<Flux,Mono<Void>>` hoặc consumer tự subscribe |
| `Function<Flux,Flux>` gọi `subscribe()` rồi return Flux khác | Detached subscription | Trả một chuỗi operator duy nhất cho framework |
| `doOnSubscribe` không xuất hiện | Wiring hoặc Publisher chưa được subscribe | Xem definition/binding; không sửa broker vội |
| Subscribe có, request bằng 0 | Demand/backpressure | Kiểm tra Subscriber/operator và nguồn |
| `doFinally` = `ON_ERROR` | Lỗi terminal | Recovery per event, log/trace, ack policy |
| `doFinally` = `ON_COMPLETE` | Nguồn finite hoặc operator kết thúc | Kiểm tra Supplier, `take`, `collectList` |
| `doFinally` = `CANCEL` | Cancel/dispose/`switchMap`/shutdown | Tìm owner của subscription |
| onNext có trước filter, không có sau | Filter toàn bộ event | Kiểm tra predicate và schema |
| Kafka lag tăng, không có assignment | Consumer group/partition hoặc connection | Kiểm tra group state/partition count |
| Output rỗng, function input có data | Output binding/operator send | Xem destination, serialization, producer errors |
| `Publisher` nóng phát trước subscriber | Early emission | Xử lý `EmitResult`, lifecycle, durable queue |
| Có subscription nhưng CPU cao/đứng | Blocking/scheduler starvation | Thread dump, boundedElastic hoặc nonblocking I/O |
| Lag không giảm sau khi subscribe | Thiếu ack, lỗi downstream hoặc source không xử lý | Kiểm tra offset, ack, retry và DB |

## 22. Những sai lầm thường gặp

1. **Nghĩ tạo Flux là đã xử lý:** operator chỉ được thực thi khi có subscription phù hợp.
2. **Cho rằng mọi Consumer reactive được framework subscribe:** `Consumer<Flux<?>>` trả `void` nên cần trách nhiệm subscriber phía ứng dụng.
3. **Tự subscribe bên trong reactive Function:** có thể tạo hai luồng độc lập, side effect trùng và lỗi thất lạc.
4. **Bỏ qua terminal signal:** một `onError` hoặc `onComplete` có thể làm pipeline im lặng mãi.
5. **Dùng `onErrorResume(Flux.empty())` ở cuối stream:** kết thúc toàn luồng sau lỗi thay vì phục hồi từng event.
6. **Dùng `onErrorContinue` để nuốt mọi exception:** semantics phức tạp, có thể làm mất dữ liệu.
7. **Đặt `collectList()` trên nguồn broker vô hạn:** chờ hoàn tất vô hạn và tăng memory.
8. **Dùng `take(1)` hoặc `next()` trong luồng production:** chỉ tiêu thụ một số ít event rồi kết thúc.
9. **Dùng `switchMap` cho side effect phải hoàn tất:** tác vụ cũ có thể bị cancel khi event mới tới.
10. **Dùng blocking I/O trên event-loop:** gây starvation hoặc exception khi gọi `block()`.
11. **Cho rằng regular Kafka binder đã reactive end-to-end vì function dùng Flux:** không mặc nhiên có Reactive Streams backpressure toàn tuyến.
12. **Đổi sang Reactive Kafka Binder nhưng không xử lý acknowledgment:** consumer chạy nhưng offsets không tiến hoặc commit sai thời điểm.
13. **Cho rằng `maxAttempts` của binder imperative chữa lỗi async Reactor:** cần policy reactive và integration test.
14. **Không kiểm tra function definition/binding:** Bean tồn tại không có nghĩa đã nhận broker data.
15. **Thấy không có onNext rồi thêm subscribe mới:** nếu Kafka partition không assign, cách làm này không giải quyết nguyên nhân.
16. **Coi Actuator health UP là subscriber sống:** phải theo dõi subscription lifecycle và business throughput.
17. **Chỉ test Flux bằng StepVerifier:** không phát hiện sai binder, offset, DLQ và broker disconnect.
18. **Restart liên tục để phục hồi:** có thể tạo rebalance, replay và retry storm nếu lỗi gốc chưa sửa.

## Kết luận

Khi Spring Cloud Stream reactive pipeline ngừng xử lý, trước hết phân biệt **chưa có subscriber**, **có subscriber nhưng không có demand/data**, và **subscription đã kết thúc** do complete/error/cancel. `Function<Flux,Flux>` thường phải **trả** Publisher để framework subscribe, còn `Consumer<Flux>` cần tự subscribe; với reactive sink, `Function<Flux,Mono<Void>>` là lựa chọn được tài liệu khuyến nghị. Reactive Supplier hữu hạn có thể kết thúc đúng thiết kế chứ không phải lỗi.

Để khôi phục bền vững, đừng chỉ thêm `subscribe()` hoặc restart Pod. Hãy kiểm tra `spring.cloud.function.definition` và binding, đặt instrumentation Reactor tại đầu/giữa/cuối pipeline, xác định terminal signal, xử lý lỗi theo từng event, cấu hình ack/offset đúng binder và kiểm thử duplicate/replay. Reactor API không tự thay đổi semantics của Kafka/RabbitMQ/Pulsar. Chỉ khi cả subscription lẫn broker backlog/processing metrics đều ổn định mới coi pipeline đã phục hồi.

## Tài liệu tham khảo

- [Spring Cloud Stream — Producing and Consuming Messages: Consumer (Reactive) và Reactive Functions Support](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/producing-and-consuming-messages.html)
- [Spring Cloud Function — Programming Model: Reactive Function và Consumer](https://docs.spring.io/spring-cloud-function/reference/spring-cloud-function/programming-model.html)
- [Spring Cloud Stream — Kafka Reactive Binder Basic Examples](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-reactive-binder/examples.html)
- [Spring Cloud Stream — Kafka Reactive Binder Consuming Records](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-reactive-binder/consuming.html)
- [Project Reactor — Reference Guide](https://projectreactor.io/docs/core/release/reference/)
- [Project Reactor — Debugging Reactor](https://projectreactor.io/docs/core/release/reference/debugging.html)
- [Spring Cloud Stream — Testing](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/spring_integration_test_binder.html)

