# Luồng Flux không được xử lý do thiếu đăng ký nhận dữ liệu

## 1. Triệu chứng: tạo được Flux nhưng không có xử lý nào xảy ra

Một ứng dụng Spring Cloud Function có function xử lý đơn hàng:

~~~java
@Bean
public Function<Flux<OrderEvent>, Flux<OrderReceipt>> processOrders() {
    return orders -> orders
        .map(this::normalize)
        .flatMap(orderService::process);
}
~~~

Code khởi động bình thường, bean xuất hiện trong Spring context, nhưng log trong `map` hoặc `orderService.process` không chạy. Các biểu hiện thường gặp:

- Gọi `Flux.just(...)` hoặc `Flux.fromIterable(...)` nhưng không thấy event được xử lý.
- Thêm `map`, `filter`, `doOnNext` nhưng không thấy side effect.
- Hàm trả về `Flux<OrderReceipt>`, nhưng caller chỉ lưu biến rồi không có kết quả.
- Đã gọi `collectList()` hoặc `then()` nhưng database/API vẫn chưa được gọi.
- Một `Supplier<Flux<T>>` được khai báo nhưng không phát message ra broker.
- Một `Consumer<Flux<T>>` nhận publisher nhưng consumer không chạy.
- Unit test tạo pipeline thành công nhưng không có assertion nào kích hoạt subscription.
- Ứng dụng chạy qua HTTP hoặc Spring Cloud Stream nhưng stream không có message, dù function bean đã được tạo.

Nguyên nhân thường gặp nhất là **chưa có Subscriber đăng ký vào Publisher**. Trong Project Reactor, `Flux` mô tả một chuỗi xử lý bất đồng bộ; nó không phải một collection đã thực thi xong. Các operator như `map`, `filter`, `flatMap` chỉ lắp ghép pipeline. Dữ liệu bắt đầu chảy khi có subscription và demand từ subscriber.

Bài thuộc chương **Chẩn đoán**, với đề mục **“Luồng Flux không được xử lý do thiếu đăng ký nhận dữ liệu”**, trong module **SPRING_CLOUD_FUNCTION**. Module học cách phát triển logic nghiệp vụ tái sử dụng bằng `Supplier`, `Function` và `Consumer`, tra cứu qua `FunctionCatalog`, chuyển đổi message và triển khai cùng một function qua HTTP, sự kiện hoặc serverless.

**Câu hỏi chẩn đoán đầu tiên:** ai đang subscribe vào publisher này?

### Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích vòng đời Publisher–Subscriber và vì sao không có subscription thì pipeline không chạy.
2. Phân biệt assembly, subscription, request, onNext, onError, onComplete và cancellation.
3. Nhận diện pipeline bị bỏ quên vì không return publisher hoặc không subscribe ở ranh giới gọi.
4. Chọn đúng chữ ký reactive cho `Function` và `Consumer`.
5. Hiểu Spring Cloud Stream kết nối và subscribe reactive function như thế nào.
6. Phân biệt reactive Supplier liên tục với reactive Supplier hữu hạn cần polling.
7. Chẩn đoán cold/hot publisher, nhiều subscription, backpressure, lỗi và cancellation.
8. Kiểm thử bằng `StepVerifier` để bảo đảm pipeline thực sự được thực thi.
9. Quản lý subscription thủ công đúng lifecycle khi thật sự cần tự subscribe.

## 2. Flux là mô tả luồng, không phải danh sách đã chạy

Một `Flux<T>` đại diện cho chuỗi có thể phát từ 0 đến N phần tử, rồi kết thúc bằng completion hoặc error. Khai báo:

~~~java
Flux<String> names = Flux.just("anna", "minh", "linh");
~~~

chỉ tạo một publisher. Chưa có subscriber nào yêu cầu dữ liệu.

Tương tự:

~~~java
Flux<String> upperNames = names.map(String::toUpperCase);
~~~

`map` tạo publisher mới mô tả phép biến đổi. Nó không tự chạy phép biến đổi ngay lúc dòng code được thực thi.

### 2.1. Assembly và subscription

~~~mermaid
flowchart TD
    A["Tạo source: Flux.just(...)"] --> B["Assembly: map / filter / flatMap"]
    B --> C["Publisher pipeline đã lắp ghép"]
    C --> D{"Có Subscriber?"}
    D -->|Không| E["Không có tín hiệu dữ liệu"]
    D -->|Có| F["Subscriber subscribe và request"]
    F --> G["Source phát onNext"]
    G --> H["Các operator xử lý"]
    H --> I{"Còn dữ liệu?"}
    I -->|Có| G
    I -->|Không| J["onComplete hoặc onError"]
~~~

Có ba giai đoạn cần phân biệt:

| Giai đoạn | Việc xảy ra | Có xử lý dữ liệu chưa? |
| --- | --- | --- |
| Assembly | Tạo source và nối operator | Thường chưa |
| Subscription | Subscriber đăng ký, subscription được thiết lập | Pipeline được kích hoạt |
| Demand/processing | Subscriber yêu cầu phần tử, source phát tín hiệu | Có |

Trong Reactive Streams, subscriber không chỉ báo “tôi quan tâm” mà còn điều khiển demand qua `request(n)`. Điều này tạo nền tảng cho backpressure.

### 2.2. Ví dụ pipeline chưa chạy

~~~java
Flux<Integer> numbers = Flux.range(1, 3);

numbers.map(number -> {
    System.out.println("Processing " + number);
    return number * 10;
});
~~~

Không có dòng `Processing ...` nào được in vì publisher kết quả không được subscribe và cũng không được trả cho một thành phần khác để subscribe.

### 2.3. Kích hoạt trong chương trình độc lập

~~~java
Flux<Integer> numbers = Flux.range(1, 3);

numbers
    .map(number -> number * 10)
    .subscribe(System.out::println);
~~~

Kết quả:

~~~text
10
20
30
~~~

`subscribe` tạo subscription và kích hoạt pipeline. Tuy nhiên, không nên biến việc gọi `subscribe()` thành thói quen trong mọi function Spring Cloud Function; ở môi trường có adapter quản lý reactive lifecycle, hãy trả publisher cho adapter.

## 3. Operator không tự subscribe

Những operator thường khiến người mới tưởng rằng pipeline đã chạy:

| Operator | Tác dụng | Tự subscribe? |
| --- | --- | --- |
| `map` | Biến đổi từng phần tử | Không |
| `filter` | Lọc phần tử | Không |
| `flatMap` | Chuyển từng phần tử thành publisher con | Không |
| `concatMap` | Ghép publisher con theo thứ tự | Không |
| `doOnNext` | Quan sát side effect khi có phần tử | Không |
| `doOnError` | Quan sát lỗi | Không |
| `publishOn` | Chuyển scheduler cho downstream | Không |
| `subscribeOn` | Chọn scheduler cho subscription upstream | Không |
| `collectList` | Gom phần tử thành `Mono<List<T>>` | Không |
| `then` | Tạo publisher chỉ phát completion sau upstream | Không |
| `retryWhen` | Mô tả việc subscribe lại khi có lỗi | Không |

### 3.1. Side effect trong doOnNext không chạy nếu chưa subscribe

~~~java
AtomicInteger processed = new AtomicInteger();

Flux<Integer> pipeline = Flux.range(1, 3)
    .doOnNext(value -> processed.incrementAndGet());

System.out.println(processed.get()); // 0
~~~

`doOnNext` là callback được gọi khi upstream phát phần tử. Nó không phải lệnh thực thi độc lập.

Sau khi subscribe:

~~~java
pipeline.subscribe();

System.out.println(processed.get()); // 3
~~~

### 3.2. collectList và then cũng chỉ tạo publisher mới

~~~java
Mono<List<Integer>> allNumbers =
    Flux.range(1, 3).collectList();

Mono<Void> completed =
    Flux.range(1, 3).then();
~~~

Cả hai biến vẫn là publisher. Muốn chạy trong test, dùng `StepVerifier` hoặc subscribe. Trong code reactive của ứng dụng, hãy trả publisher cho thành phần gọi thay vì tự block.

### 3.3. publishOn và subscribeOn không phải subscribe

~~~java
Flux<Integer> pipeline = Flux.range(1, 10)
    .subscribeOn(Schedulers.boundedElastic())
    .publishOn(Schedulers.parallel())
    .map(this::transform);
~~~

Hai operator trên chỉ thay đổi execution context khi subscription diễn ra. Chúng không tạo subscriber và không kích hoạt source.

## 4. Ba tín hiệu chính và vai trò của request

Một Reactive Streams publisher phát các tín hiệu:

- `onNext(value)`: có phần tử mới.
- `onError(error)`: chuỗi kết thúc vì lỗi.
- `onComplete()`: chuỗi kết thúc bình thường.

Subscriber đăng ký bằng `subscribe` và có thể yêu cầu dữ liệu thông qua `request(n)`.

~~~mermaid
sequenceDiagram
    participant S as Subscriber
    participant P as Publisher
    S->>P: subscribe()
    P-->>S: onSubscribe(subscription)
    S->>P: request(2)
    P-->>S: onNext(value 1)
    P-->>S: onNext(value 2)
    S->>P: request(2)
    P-->>S: onNext(value 3)
    P-->>S: onComplete()
~~~

### 4.1. Subscription chưa có demand

Một subscriber tự viết có thể subscribe nhưng không gọi `request`. Khi đó source không được yêu cầu phát phần tử.

Đây là một dạng “đã đăng ký nhưng không xử lý” khác với hoàn toàn không subscribe.

### 4.2. Không tự viết Subscriber nếu không cần

Trong hầu hết ứng dụng, dùng các overload `subscribe` của Reactor hoặc để Spring adapter quản lý subscription. Tự implement `Subscriber` chỉ phù hợp khi bạn cần điều khiển demand và hiểu rõ Reactive Streams contract.

### 4.3. Backpressure không phải mất message

Backpressure cho phép downstream yêu cầu số phần tử mà nó có thể xử lý. Nếu subscriber yêu cầu chậm, source có thể phát chậm theo demand; không nên kết luận dữ liệu bị mất chỉ vì không thấy toàn bộ event ngay lập tức.

## 5. Cách nhận biết publisher đã được subscribe

Có thể dùng các hook quan sát:

~~~java
Flux<OrderEvent> source = orderSource.events()
    .doOnSubscribe(subscription ->
        log.info("Order stream subscribed")
    )
    .doOnRequest(count ->
        log.info("Order stream requested {}", count)
    )
    .doOnNext(event ->
        log.debug("Received order {}", event.orderId())
    )
    .doOnError(error ->
        log.error("Order stream failed", error)
    )
    .doOnCancel(() ->
        log.warn("Order stream cancelled")
    )
    .doOnComplete(() ->
        log.info("Order stream completed")
    );
~~~

Các hook chỉ chạy nếu có subscription và tín hiệu tương ứng.

| Hook | Dùng để biết |
| --- | --- |
| `doOnSubscribe` | Có subscriber đăng ký |
| `doOnRequest` | Có demand từ downstream |
| `doOnNext` | Có phần tử được phát |
| `doOnError` | Pipeline kết thúc bằng lỗi |
| `doOnComplete` | Pipeline hoàn tất bình thường |
| `doOnCancel` | Subscription bị hủy |

Không log toàn bộ payload nếu có dữ liệu khách hàng, thanh toán hoặc bí mật. Dùng event ID, loại payload và correlation ID đã được phép.

## 6. Lỗi phổ biến: tạo pipeline nhưng bỏ kết quả

Ví dụ sai:

~~~java
public Flux<OrderReceipt> process(Flux<OrderEvent> orders) {
    orders.map(this::normalize)
        .flatMap(orderService::process);

    return Flux.empty();
}
~~~

Pipeline đã được tạo nhưng không được trả về. Hàm trả một publisher rỗng khác, nên caller chỉ nhận `Flux.empty()`.

Cách đúng:

~~~java
public Flux<OrderReceipt> process(Flux<OrderEvent> orders) {
    return orders
        .map(this::normalize)
        .flatMap(orderService::process);
}
~~~

### 6.1. Bỏ quên publisher con trong callback

Sai:

~~~java
orders.doOnNext(order ->
    orderService.save(order)
);
~~~

Nếu `save` trả `Mono<Void>`, publisher con bị bỏ qua. `doOnNext` không tự subscribe vào Mono con.

Đúng:

~~~java
return orders.concatMap(order ->
    orderService.save(order).thenReturn(order)
);
~~~

Hoặc nếu chỉ cần hoàn tất sau khi lưu:

~~~java
return orders.concatMap(order ->
    orderService.save(order)
).then();
~~~

### 6.2. Không lồng subscribe để “sửa” lỗi mất publisher con

Sai:

~~~java
orders.subscribe(order ->
    orderService.save(order).subscribe()
);
~~~

Đây là fire-and-forget lồng nhau. Pipeline ngoài không chờ pipeline trong, lỗi và cancellation khó truyền về caller, và backpressure không được điều phối xuyên suốt.

Hãy nối publisher bằng `flatMap` hoặc `concatMap`.

## 7. Function<Flux<T>, Flux<R>>: trả publisher cho framework

Spring Cloud Function hỗ trợ reactive function:

~~~java
@Bean
Function<Flux<OrderEvent>, Flux<OrderReceipt>> processOrders() {
    return orders -> orders
        .map(this::normalize)
        .flatMap(orderService::process);
}
~~~

Khi Spring Cloud Stream dùng function này, reactive function được gọi một lần để nối user processing pipeline với source/target stream của binder. Binder/framework quản lý việc kết nối và subscription.

Không cần viết:

~~~java
@Bean
Function<Flux<OrderEvent>, Flux<OrderReceipt>> processOrders() {
    return orders -> {
        orders
            .map(this::normalize)
            .flatMap(orderService::process)
            .subscribe();

        return Flux.empty();
    };
}
~~~

Đoạn sai này tự subscribe một pipeline tách rời rồi trả publisher rỗng. Framework không thể quản lý đúng output, lỗi và cancellation của pipeline đã bị tách ra.

### 7.1. Reactive function được invoke một lần trong Spring Cloud Stream

| Chữ ký | Invocation trong Spring Cloud Stream |
| --- | --- |
| `Function<OrderEvent,OrderReceipt>` | Một lần cho mỗi event |
| `Function<Flux<OrderEvent>,Flux<OrderReceipt>>` | Một lần khi khởi tạo để nối stream |
| `Consumer<OrderEvent>` | Một lần cho mỗi event |
| `Supplier<OrderEvent>` | Được poll để lấy từng giá trị |
| `Supplier<Flux<OrderEvent>>` | Thường được gọi một lần để tạo stream liên tục |

Reactive function là **stream initialization function**. Logic trong các operator được thực thi khi binder source phát dữ liệu và downstream subscription được thiết lập.

### 7.2. Chỉ có bean chưa có nghĩa là có subscriber

`@Bean Function<Flux<T>,Flux<R>>` được khai báo trong ApplicationContext chưa tự làm cho source chạy. Cần một execution context:

- Spring Cloud Stream bind input/output và kết nối stream.
- HTTP adapter nhận request và subscribe vào publisher response.
- Một caller trực tiếp gọi function và subscribe vào publisher trả về.
- Unit test dùng `StepVerifier` để kích hoạt publisher.

`FunctionCatalog` giúp đăng ký/tra cứu function; bản thân việc có tên trong catalog không phải một subscription.

## 8. Function<Flux<T>, Mono<Void>>: mẫu reactive consumer nên ưu tiên

Khi chỉ cần tiêu thụ stream và không phát output payload, Spring Cloud Stream khuyến nghị dùng `Function<Flux<T>,Mono<Void>>` thay vì `Consumer<Flux<T>>`.

Service:

~~~java
public interface OrderService {
    Mono<Void> persist(OrderEvent event);
}
~~~

Function:

~~~java
@Bean
Function<Flux<OrderEvent>, Mono<Void>> persistOrders(
        OrderService orderService) {

    return orders -> orders
        .concatMap(orderService::persist)
        .then();
}
~~~

`concatMap` gọi thao tác lưu theo thứ tự. `then()` tạo `Mono<Void>` chỉ hoàn tất khi upstream hoàn thành.

Framework nhận publisher output nên có thể quản lý subscription và lifecycle của pipeline.

### 8.1. Vì sao then() không phải subscribe?

~~~java
Mono<Void> completion = orders
    .concatMap(orderService::persist)
    .then();
~~~

`then()` biến chuỗi nhiều giá trị thành publisher chỉ phát completion. Nó vẫn chưa subscribe. Khi Spring Cloud Stream hoặc test subscribe vào `completion`, các thao tác persist mới thực thi.

### 8.2. Không dùng then() nếu cần output từng event

Nếu muốn phát `OrderReceipt` cho output binding, hãy trả `Flux<OrderReceipt>`:

~~~java
@Bean
Function<Flux<OrderEvent>, Flux<OrderReceipt>> processOrders(
        OrderService orderService) {

    return orders -> orders
        .concatMap(orderService::process);
}
~~~

Nếu trả `Mono<Void>`, không có output payload để gửi đi; đây là chủ ý của consumer-style function.

## 9. Consumer<Flux<T>> là trường hợp đặc biệt

Java `Consumer<T>` trả `void`. Với `Consumer<Flux<OrderEvent>>`, framework nhận callback nhưng không nhận được publisher kết quả để subscribe.

Ví dụ:

~~~java
@Bean
Consumer<Flux<OrderEvent>> auditOrders() {
    return orders -> orders
        .doOnNext(this::audit)
        .subscribe();
}
~~~

Theo tài liệu Spring Cloud Function/Spring Cloud Stream, nếu thật sự khai báo `Consumer<Flux<?>>` thì cần subscribe vào input Flux. Tuy nhiên, cách này khiến ứng dụng phải tự quản lý subscription, error handling và cancellation.

### 9.1. Ví dụ có error handler khi tự subscribe

~~~java
@Bean
Consumer<Flux<OrderEvent>> auditOrders() {
    return orders -> orders
        .doOnNext(this::audit)
        .subscribe(
            ignored -> { },
            error -> log.error("Audit stream failed", error)
        );
}
~~~

Đây là ví dụ cho trường hợp đặc biệt. Lỗi phát sinh trong subscription này không còn nằm trong publisher output mà framework có thể trực tiếp theo dõi như `Function<Flux<T>,Mono<Void>>`.

### 9.2. Khi nào nên dùng Consumer<Flux<T>>?

Chỉ dùng khi có lý do rõ ràng để sở hữu subscription bên trong consumer. Cần xác định:

- Ai giữ `Disposable`?
- Ai dispose khi ứng dụng shutdown?
- Lỗi được chuyển đến đâu?
- Retry/cancellation được quản lý ở đâu?
- Subscription có thể được tạo lặp lại không?
- Có nguy cơ tạo nhiều subscriber cho cùng nguồn không?

Với sink trong Spring Cloud Stream, mẫu `Function<Flux<T>,Mono<Void>>` thường rõ ràng và dễ kiểm thử hơn.

## 10. Đừng subscribe bên trong Function reactive

Một function reactive nên nối publisher đầu vào với publisher đầu ra:

~~~java
@Bean
Function<Flux<OrderEvent>, Flux<OrderReceipt>> processOrders() {
    return orders -> orders
        .filter(this::isValid)
        .concatMap(orderService::process);
}
~~~

Tránh:

~~~java
@Bean
Function<Flux<OrderEvent>, Flux<OrderReceipt>> processOrders() {
    return orders -> {
        orders
            .filter(this::isValid)
            .concatMap(orderService::process)
            .subscribe();

        return Flux.empty();
    };
}
~~~

Các vấn đề của cách thứ hai:

1. Tạo một subscription tách rời khỏi output publisher.
2. Framework không nhận được dữ liệu kết quả.
3. Lỗi có thể không được chuyển về adapter/binder theo đường xử lý chuẩn.
4. Cancellation từ downstream không nhất thiết hủy subscription nội bộ.
5. Retry có thể chạy lại một pipeline trong khi subscription cũ vẫn còn.
6. Side effect có thể bị thực hiện nhiều lần khi có nhiều subscription.
7. Test chỉ kiểm tra publisher trả về có thể thấy rỗng dù side effect chạy ở background.

**Nguyên tắc:** trong reactive Function, trả publisher đã được compose; để caller/adapter ở ranh giới subscribe.

## 11. Caller trực tiếp phải subscribe vào publisher được trả về

Khi gọi function từ Java code thông thường:

~~~java
@SuppressWarnings("unchecked")
Function<Flux<OrderEvent>, Flux<OrderReceipt>> function =
    (Function<Flux<OrderEvent>, Flux<OrderReceipt>>) catalog.lookup("processOrders");

Flux<OrderReceipt> output =
    function.apply(Flux.fromIterable(batch));
~~~

Nếu chỉ lưu `output` mà không có subscriber, pipeline chưa chạy.

Trong unit test:

~~~java
StepVerifier.create(output)
    .expectNextMatches(receipt ->
        receipt.orderId().equals("ORD-101")
    )
    .verifyComplete();
~~~

`verifyComplete()` kích hoạt subscription và đợi completion. Trong một ứng dụng reactive khác, caller thường tiếp tục compose publisher đó vào response hoặc pipeline lớn hơn. Không cần subscribe ngay tại mỗi tầng.

### 11.1. Đừng subscribe hai lần ngoài ý muốn

~~~java
Flux<OrderReceipt> output = function.apply(input);

output.subscribe(this::publishReceipt);
return output;
~~~

Nếu caller/framework tiếp tục subscribe vào publisher được return, có thể có hai subscription. Với cold publisher, upstream có thể chạy hai lần và tạo side effect trùng lặp.

Hãy chọn một đường tiêu thụ rõ ràng: return publisher cho framework hoặc subscribe ở ranh giới ứng dụng độc lập.

## 12. HTTP adapter: response lifecycle tạo subscription

Khi một reactive function được expose qua HTTP, adapter web có thể trả publisher cho HTTP response layer. Web runtime subscribe để ghi response body khi client đọc response.

Ví dụ:

~~~java
@Bean
Function<Flux<OrderEvent>, Flux<OrderReceipt>> processOrders() {
    return orders -> orders.map(this::toReceipt);
}
~~~

Khi gọi qua HTTP adapter, không cần gọi `subscribe()` bên trong function. Adapter chịu trách nhiệm kết nối request body và response publisher theo mapping của endpoint.

### 12.1. Vì sao gọi trực tiếp function trong test khác gọi HTTP?

- Unit test gọi `function.apply(input)` và phải subscribe publisher.
- HTTP integration test gửi request; adapter tạo và subscribe response pipeline.
- Nếu client disconnect, subscription có thể bị cancel.
- Nếu endpoint không nhận request, function reactive có thể chưa được kích hoạt.

### 12.2. HTTP request body không tự đảm bảo có phần tử

Một request có thể được nhận nhưng body rỗng, sai Content-Type hoặc không được map thành kiểu mong muốn. Khi đó subscriber vẫn có thể tồn tại nhưng source không phát event như dự kiến.

Kiểm tra riêng:
- HTTP route có được export?
- Request có vào đúng function?
- Body có được deserialize?
- Publisher có phát `onNext`?
- Client có đọc response body đến hết không?

Không quy mọi trường hợp không có log thành thiếu subscription.

## 13. Spring Cloud Stream: binder kết nối reactive stream

Spring Cloud Stream sử dụng Spring Cloud Function để khai báo source, processor và sink.

Ví dụ processor:

~~~java
@Bean
Function<Flux<String>, Flux<String>> uppercase() {
    return values -> values.map(String::toUpperCase);
}
~~~

Cấu hình:

~~~properties
spring.cloud.function.definition=uppercase
spring.cloud.stream.bindings.uppercase-in-0.destination=words-in
spring.cloud.stream.bindings.uppercase-out-0.destination=words-out
~~~

Binding mặc định theo convention:

- `uppercase-in-0` là input.
- `uppercase-out-0` là output.

Khi binder kết nối các destination, framework thiết lập subscription để nối source stream với function và output stream. Function reactive được gọi một lần lúc khởi tạo để đưa publisher vào pipeline.

### 13.1. Không có subscription khi chỉ khai báo bean và không có adapter

Nếu ứng dụng chỉ có:

~~~java
@Bean
Function<Flux<String>, Flux<String>> uppercase() {
    return values -> values.map(String::toUpperCase);
}
~~~

nhưng không dùng Spring Cloud Stream, web adapter hoặc caller trực tiếp, không có thành phần nào tự động tiêu thụ publisher. Bean tồn tại không đồng nghĩa có message source/target.

### 13.2. Kiểm tra binding name và destination

| Thành phần | Ví dụ | Cần xác minh |
| --- | --- | --- |
| Function definition | `uppercase` | Đã chọn đúng bean |
| Input binding | `uppercase-in-0` | Đã bind tới destination |
| Input destination | `words-in` | Producer thực sự gửi message |
| Output binding | `uppercase-out-0` | Đã có target |
| Output destination | `words-out` | Consumer đang đọc đúng nơi |

Nếu binding sai hoặc broker không có message, pipeline có thể đã subscribe nhưng không nhận `onNext`.

## 14. Reactive Function là stream initialization function trong Stream

Trong Spring Cloud Stream, reactive function khác imperative handler:

- Imperative function là message handler; với N message, function được gọi N lần.
- Reactive function được gọi một lần lúc startup để nối user processing code với source/target stream của binder.
- Sau khi nối, việc xử lý event nằm trong reactive API và subscription lifecycle.

~~~mermaid
flowchart LR
    A["Binder input source"] --> B["Subscription"]
    B --> C["Flux<OrderEvent>"]
    C --> D["Reactive Function"]
    D --> E["Flux<OrderReceipt>"]
    E --> F["Binder output target"]
~~~

Điều này giải thích vì sao log ở đầu method function có thể chỉ xuất hiện một lần lúc startup, trong khi log bên trong `doOnNext` xuất hiện nhiều lần theo event.

### 14.1. Phân biệt log lúc assembly và lúc xử lý event

~~~java
@Bean
Function<Flux<String>, Flux<String>> uppercase() {
    log.info("Creating reactive function");

    return values -> {
        log.info("Connecting reactive pipeline");

        return values.map(value -> {
            log.info("Processing value {}", value);
            return value.toUpperCase();
        });
    };
}
~~~

Trong Spring Cloud Stream, hai log đầu liên quan khởi tạo/assembly; log trong `map` chỉ chạy khi có phần tử được subscribe và phát tới.

Đừng dùng log “function method called once” làm bằng chứng stream chỉ xử lý một event.

## 15. Supplier<Flux<T>>: stream source cũng cần subscription

Reactive Supplier:

~~~java
@Bean
Supplier<Flux<String>> messages() {
    return () -> Flux.interval(Duration.ofSeconds(1))
        .map(sequence -> "event-" + sequence);
}
~~~

Trong Spring Cloud Stream, reactive Supplier thường được gọi một lần để tạo stream liên tục. Binder đăng ký vào publisher để nhận message.

`Supplier.get()` được gọi và trả `Flux` không có nghĩa các event đã phát. Source như `Flux.interval` bắt đầu phát khi có subscription.

### 15.1. Không subscribe trong Supplier

Sai:

~~~java
@Bean
Supplier<Flux<String>> messages() {
    return () -> {
        Flux<String> stream = createEvents();
        stream.subscribe(this::send);
        return Flux.empty();
    };
}
~~~

Cách này tách luồng phát khỏi output binding do binder quản lý. Trả trực tiếp publisher:

~~~java
@Bean
Supplier<Flux<String>> messages() {
    return this::createEvents;
}
~~~

### 15.2. Reactive Supplier liên tục khác imperative Supplier

| Supplier | Hành vi thường gặp trong Spring Cloud Stream |
| --- | --- |
| `Supplier<T>` | Poller gọi `get()` theo chu kỳ để tạo từng message |
| `Supplier<Flux<T>>` | Được gọi một lần để tạo stream liên tục, binder subscribe vào stream |
| `@PollableBean Supplier<Flux<T>>` | Reactive supplier hữu hạn được đánh dấu để polling framework có thể gọi lại |

Không áp dụng quy tắc polling của imperative Supplier cho mọi reactive Supplier.

## 16. Reactive Supplier hữu hạn: cần polling mechanism

Có trường hợp Supplier trả một stream hữu hạn, ví dụ đọc một batch từ database:

~~~java
@Bean
Supplier<Flux<OrderEvent>> pendingOrders() {
    return () -> orderRepository.findPendingOrders();
}
~~~

Publisher này có thể phát một số event rồi complete. Nếu chỉ được gọi một lần lúc startup, sau khi hoàn tất sẽ không tự tạo batch mới.

Spring Cloud Function cung cấp marker `@PollableBean` để báo reactive Supplier tạo stream hữu hạn và có thể cần được poll lại. Bản thân Spring Cloud Function không tự triển khai polling behavior cho annotation này; framework tích hợp như Spring Cloud Stream cung cấp polling mechanism.

Ví dụ:

~~~java
@PollableBean(splittable = true)
public Supplier<Flux<OrderEvent>> pendingOrders() {
    return () -> orderRepository.findPendingOrders();
}
~~~

### 16.1. PollableBean và splittable

Trong Spring Cloud Stream, `@PollableBean` báo rằng reactive Supplier cần được polling. Thuộc tính `splittable` điều khiển cách kết quả stream được phát ra:

- `splittable = true`: tách từng item thành message riêng; đây là mặc định theo tài liệu Spring Cloud Stream hiện hành.
- `splittable = false`: gửi publisher như một kết quả stream thay vì tách từng item.

Chọn theo contract output và binder.

### 16.2. Poller mặc định và cấu hình

Spring Cloud Stream cung cấp default poller. Tài liệu hiện hành mô tả fixed delay mặc định là 1000 ms.

~~~properties
spring.integration.poller.fixed-delay=5000
spring.integration.poller.max-messages-per-poll=1
~~~

Ví dụ trên thay đổi chu kỳ polling và số message tối đa trong mỗi poll. Với binding riêng, có thể dùng prefix poller theo binding:

~~~properties
spring.cloud.stream.bindings.pendingOrders-out-0.producer.poller.fixed-delay=5000
~~~

Kiểm tra đúng tên binding và cấu hình phiên bản đang dùng.

### 16.3. Đừng dùng PollableBean để chữa một Flux chưa subscribe tùy ý

`@PollableBean` dành cho reactive Supplier hữu hạn được tích hợp với polling mechanism. Nó không phải annotation chung để bắt mọi `Flux` trong ứng dụng tự chạy.

## 17. Consumer reactive: vì sao void return dễ bị bỏ subscription?

Một `Consumer<T>` trả `void`. Với imperative input, framework gọi consumer cho mỗi event và không cần publisher output.

Nhưng `Consumer<Flux<T>>` nhận publisher và trả void. Framework không nhận được một publisher kết quả để subscribe.

Spring Cloud Stream khuyến nghị dùng:

~~~java
Function<Flux<OrderEvent>, Mono<Void>>
~~~

thay cho:

~~~java
Consumer<Flux<OrderEvent>>
~~~

Ví dụ đúng:

~~~java
@Bean
Function<Flux<OrderEvent>, Mono<Void>> storeOrders(
        OrderService orderService) {

    return orders -> orders
        .concatMap(orderService::persist)
        .then();
}
~~~

Nếu vẫn dùng explicit reactive Consumer, phải subscribe vào Flux đầu vào và tự quản lý lifecycle. Đây là ngoại lệ cần cân nhắc, không phải mẫu mặc định.

## 18. Composition có thể tạo reactive Consumer không có nơi subscribe

Spring Cloud Function hỗ trợ composition giữa reactive và imperative functions, nhưng cần chú ý kiểu kết quả.

Ví dụ một reactive function ghép với imperative Consumer có thể tạo ra một reactive Consumer. Vì Consumer trả void nên không có publisher output để framework subscribe.

Đây là một giới hạn cần tránh khi thiết kế composition cho stream.

### 18.1. Cách sửa

- Đổi consumer thành `Function<Flux<T>,Mono<Void>>` để trả completion publisher.
- Hoặc thay phần xử lý thành imperative function/consumer nếu framework gọi từng event.
- Hoặc chỉ tự subscribe trong reactive Consumer khi bạn chủ động sở hữu subscription và chấp nhận quản lý lỗi/cancel.

### 18.2. Kiểm tra kiểu sau composition

Đừng chỉ nhìn từng function riêng lẻ. Hãy xác định kiểu cuối cùng của composition:

| Các bước | Kiểu kết quả |
| --- | --- |
| `Function<Flux<T>,Flux<R>>` | Reactive Function |
| `Function<Flux<T>,Mono<Void>>` | Reactive completion function |
| `Function<Flux<T>,...>` + imperative Consumer | Có thể trở thành reactive Consumer |
| `Supplier<Flux<T>>` + Function<Flux<T>,Flux<R>>` | Cần xem hợp đồng reactive supplier/function và subscription ở adapter |

Nếu kết quả là `Consumer<Flux<T>>`, hãy xem ai sẽ subscribe input publisher.

## 19. Cold và hot publisher: có subscription nhưng vẫn không thấy đủ event

Không phải mọi publisher đều phản ứng với subscription theo cùng một cách.

### 19.1. Cold publisher

Cold publisher bắt đầu tạo dữ liệu cho mỗi subscription:

~~~java
Flux<String> cold = Flux.defer(() ->
    Flux.just("one", "two", "three")
);
~~~

Mỗi subscriber có thể nhận lại toàn bộ chuỗi. Nếu không có subscription, source không phát dữ liệu.

### 19.2. Hot publisher

Hot publisher có thể phát dữ liệu độc lập với subscriber. Subscriber đến muộn có thể chỉ nhận các event phát sau thời điểm đăng ký.

~~~java
Sinks.Many<String> sink =
    Sinks.many().multicast().directBestEffort();

Flux<String> hot = sink.asFlux();

sink.tryEmitNext("before-subscribe");

hot.subscribe(System.out::println);

sink.tryEmitNext("after-subscribe");
~~~

Subscriber mới không nhận lại event đã phát trước subscription trong cấu hình multicast trực tiếp này.

### 19.3. Chọn đúng loại source

| Nhu cầu | Hướng chọn |
| --- | --- |
| Mỗi subscriber xử lý lại toàn bộ dữ liệu | Cold publisher |
| Chia sẻ event trực tiếp giữa subscriber hiện tại | Hot publisher/multicast |
| Subscriber đến muộn cần nhận lại một phần lịch sử | Replay/cache có giới hạn |
| Tạo source mới mỗi subscription | `defer` |
| Stream dài hạn từ event source | Publisher hot hoặc connector được quản lý lifecycle |

### 19.4. share và nhiều subscription

`share()` có thể chia sẻ một source giữa các subscriber sau khi subscription đầu tiên bắt đầu. Tuy nhiên, subscriber đến muộn không mặc định nhận lại lịch sử đã phát.

Đừng dùng `share()` như một cách “bật” publisher mà không hiểu số subscriber, thời điểm connect và semantics replay.

## 20. Nhiều subscription có thể làm xử lý trùng lặp

Với cold publisher:

~~~java
Flux<OrderEvent> orders = orderRepository.findAllPending();

orders.subscribe(this::process);
orders.subscribe(this::process);
~~~

Hai subscription có thể chạy hai truy vấn và xử lý cùng dữ liệu hai lần.

Tương tự, nếu function tự subscribe rồi framework tiếp tục subscribe publisher output, side effect có thể chạy lặp.

### 20.1. Kiểm tra số subscription

~~~java
AtomicInteger subscriptions = new AtomicInteger();

Flux<Integer> source = Flux.defer(() -> {
    subscriptions.incrementAndGet();
    return Flux.just(1, 2, 3);
});
~~~

Mỗi lần subscribe, counter tăng một lần. Có thể dùng kỹ thuật này trong test để phát hiện subscription ngoài ý muốn.

### 20.2. Idempotency vẫn cần thiết

Với event-driven processing, retry hoặc nhiều subscription có thể dẫn đến cùng event được xử lý lại. Dùng event ID, idempotency key hoặc unique constraint để bảo vệ side effect. Không dùng `cache()` hoặc `share()` thay cho cơ chế chống xử lý trùng ở tầng nghiệp vụ.

## 21. Source có subscription nhưng không phát dữ liệu

Một subscription thành công không đồng nghĩa source chắc chắn phát `onNext`.

| Source/pipeline | Hành vi |
| --- | --- |
| `Flux.empty()` | Complete ngay, không có item |
| `Flux.never()` | Không phát item, không complete, không error |
| `Flux.interval(...)` | Chỉ phát tick sau subscription và theo chu kỳ |
| `filter(...)` | Có thể lọc hết mọi phần tử |
| `take(0)` | Kết thúc mà không phát item |
| `Flux.create(...)` | Callback phải phát dữ liệu hoặc kết thúc sink |
| `onErrorResume(...)` | Có thể thay lỗi bằng publisher rỗng |
| `Mono<Void>` | Hoàn tất nhưng không phát payload |

### 21.1. Filter loại bỏ toàn bộ dữ liệu

~~~java
Flux<OrderEvent> accepted = incoming
    .filter(order -> order.total().signum() > 0);
~~~

Nếu tất cả order có total bằng 0 hoặc âm, pipeline subscribe bình thường nhưng không có event qua filter.

Thêm metric/counter trước và sau filter để phân biệt nguồn không phát với filter loại bỏ hết.

### 21.2. Flux.create không phát tín hiệu

~~~java
Flux<String> source = Flux.create(sink -> {
    // Không gọi sink.next(...), sink.error(...) hoặc sink.complete().
});
~~~

Publisher có subscriber nhưng không phát gì và không hoàn tất. Kiểm tra callback đăng ký nguồn, listener, emitter hoặc adapter đã thực sự đẩy dữ liệu vào sink chưa.

### 21.3. Mono<Void> hoàn tất không có payload

Nếu function dùng `Function<Flux<T>,Mono<Void>>`, việc không thấy output event là đúng thiết kế. Hãy quan sát side effect, completion và metrics thay vì chờ `onNext`.

## 22. Error và cancellation có thể làm stream dừng sớm

Publisher có thể đã subscribe nhưng dừng vì lỗi:

~~~java
Flux<OrderReceipt> receipts = orders
    .map(this::normalize)
    .concatMap(orderService::process)
    .doOnError(error ->
        log.error("Order processing failed", error)
    );
~~~

`onError` là terminal signal; sau lỗi, publisher không tiếp tục phát item như bình thường.

### 22.1. Phân biệt quan sát lỗi và phục hồi lỗi

~~~java
Flux<OrderReceipt> receipts = orders
    .concatMap(orderService::process)
    .doOnError(error -> log.error("Failed", error))
    .onErrorResume(error -> fallbackOrders());
~~~

- `doOnError` chỉ quan sát lỗi.
- `onErrorResume` thay thế phần còn lại của chuỗi bằng publisher khác.
- `retryWhen` tạo subscription lại theo policy.

Không dùng `onErrorComplete` hoặc fallback rỗng để che lỗi khi đang chẩn đoán; điều đó có thể khiến pipeline “chạy xong” nhưng dữ liệu đã bị bỏ.

### 22.2. Cancellation

Subscription có thể bị cancel khi:

- HTTP client ngắt kết nối.
- Binder dừng hoặc consumer bị shutdown.
- Operator `take(n)` đã lấy đủ số phần tử.
- `Disposable.dispose()` được gọi.
- Test gọi `thenCancel()`.
- Downstream không còn quan tâm kết quả.

Dùng `doOnCancel` để xác định stream dừng vì cancellation thay vì chờ event mới.

### 22.3. Retry có thể chạy lại side effect

`retryWhen` resubscribe upstream. Nếu source cold và các operator có side effect, chúng có thể chạy lại. Bảo đảm idempotency và đặt retry boundary đúng thao tác.

## 23. Backpressure: subscriber có thể chưa yêu cầu phần tử

Reactive Streams dùng demand để subscriber kiểm soát tốc độ phát.

Một custom subscriber có thể subscribe nhưng không request dữ liệu. Khi đó source chưa được yêu cầu phát item.

Trong test, có thể kiểm tra demand có kiểm soát:

~~~java
StepVerifier.create(Flux.range(1, 3), 0)
    .thenRequest(1)
    .expectNext(1)
    .thenRequest(1)
    .expectNext(2)
    .thenCancel()
    .verify();
~~~

Test trên bắt đầu với demand bằng 0, yêu cầu từng phần tử và cuối cùng cancel. Nó cho thấy subscription và demand là hai khái niệm liên quan nhưng khác nhau.

### 23.1. Binder không phát dữ liệu không nhất thiết do thiếu request

Nếu dùng binder không reactive, adapter có thể chuyển message thành publisher nhưng không cung cấp toàn bộ semantics backpressure của một transport reactive. Xác minh binder loại nào đang dùng và source thực tế có message hay không.

## 24. Đừng dùng block để che việc thiếu subscription

Các lệnh như:

~~~java
String value = mono.block();
OrderEvent last = flux.blockLast();
~~~

thực hiện subscription và chờ kết quả. Chúng có thể hữu ích trong test hoặc adapter imperative có ranh giới blocking rõ, nhưng không phải cách sửa mặc định cho reactive function.

### 24.1. Vì sao block trong pipeline nguy hiểm?

- Chặn thread đang phục vụ event loop.
- Làm giảm concurrency.
- Có thể gây deadlock khi block trên scheduler không cho phép blocking.
- Làm mất lợi ích non-blocking.
- Che khuất việc publisher lẽ ra phải được compose và trả về.

### 24.2. Dùng operator thay cho block

Sai:

~~~java
orders.map(order -> orderService.process(order).block());
~~~

Đúng:

~~~java
orders.flatMap(orderService::process);
~~~

Nếu phải giữ thứ tự xử lý:

~~~java
orders.concatMap(orderService::process);
~~~

## 25. Scheduler không thay thế subscription

`subscribeOn` và `publishOn` thường bị hiểu nhầm là làm stream tự chạy.

~~~java
Flux<OrderReceipt> result = orders
    .subscribeOn(Schedulers.boundedElastic())
    .publishOn(Schedulers.parallel())
    .flatMap(orderService::process);
~~~

Đây vẫn chỉ là một publisher. Phải có subscriber từ caller/framework.

### 25.1. Khi cần gọi API blocking

Nếu service legacy blocking, có thể cô lập phần blocking:

~~~java
Mono<OrderReceipt> processBlocking(OrderEvent event) {
    return Mono.fromCallable(() -> legacyService.process(event))
        .subscribeOn(Schedulers.boundedElastic());
}
~~~

Không gọi `subscribe()` bên trong helper này. Trả Mono để caller compose và quản lý subscription.

### 25.2. Đừng tạo thread thủ công cho từng event

Dùng `new Thread(...)` hoặc executor không được quản lý để ép side effect chạy có thể tách công việc khỏi lifecycle của stream. Ưu tiên Reactor scheduler, reactive client và binder-managed subscription.

## 26. Quản lý subscription thủ công khi thật sự cần

Có một số ứng dụng standalone phải tự kết nối publisher với subscriber. Khi đó subscription là một tài nguyên cần quản lý.

~~~java
@Component
class ExternalStreamBridge {

    private final ExternalEventSource source;
    private Disposable subscription;

    ExternalStreamBridge(ExternalEventSource source) {
        this.source = source;
    }

    @PostConstruct
    void start() {
        this.subscription = source.events()
            .subscribe(
                this::handle,
                error -> log.error("External stream failed", error)
            );
    }

    @PreDestroy
    void stop() {
        if (subscription != null && !subscription.isDisposed()) {
            subscription.dispose();
        }
    }

    private void handle(ExternalEvent event) {
        // Xử lý một event đã nhận.
    }
}
~~~

Ví dụ này minh họa ownership rõ ràng:

- Component tạo subscription khi lifecycle bắt đầu.
- Giữ `Disposable` để có thể kiểm tra/hủy.
- Xử lý lỗi ở subscription.
- Dispose khi Spring context shutdown.

Trong Spring Cloud Function/Spring Cloud Stream reactive Function, hãy để adapter/binder sở hữu subscription thay vì tạo một subscription thứ hai trong bean.

## 27. Test reactive function bằng StepVerifier

`StepVerifier` subscribe vào publisher và kiểm tra các tín hiệu theo thứ tự.

Function:

~~~java
Function<Flux<Integer>, Flux<Integer>> doubleNumbers =
    numbers -> numbers.map(number -> number * 2);
~~~

Test:

~~~java
@Test
void functionProcessesValuesWhenSubscribed() {
    Flux<Integer> result =
        doubleNumbers.apply(Flux.just(1, 2, 3));

    StepVerifier.create(result)
        .expectNext(2)
        .expectNext(4)
        .expectNext(6)
        .verifyComplete();
}
~~~

`verifyComplete()` kích hoạt subscription và đợi completion. Nếu chỉ tạo `result` mà không gọi verifier terminal, pipeline chưa được thực thi.

### 27.1. Test phát hiện thiếu subscription

~~~java
@Test
void noSideEffectBeforeSubscription() {
    AtomicInteger processed = new AtomicInteger();

    Flux<Integer> pipeline = Flux.range(1, 3)
        .doOnNext(value -> processed.incrementAndGet());

    assertThat(processed.get()).isZero();

    StepVerifier.create(pipeline)
        .expectNext(1, 2, 3)
        .verifyComplete();

    assertThat(processed.get()).isEqualTo(3);
}
~~~

Test xác nhận side effect chỉ xảy ra sau khi StepVerifier subscribe.

### 27.2. Test reactive consumer Function<Flux<T>,Mono<Void>>

~~~java
@Test
void consumerCompletesAfterAllEventsArePersisted() {
    List<Integer> stored = new ArrayList<>();

    Function<Flux<Integer>, Mono<Void>> consumer =
        values -> values
            .concatMap(value -> Mono.fromRunnable(
                () -> stored.add(value)
            ))
            .then();

    StepVerifier.create(consumer.apply(Flux.just(1, 2, 3)))
        .verifyComplete();

    assertThat(stored).containsExactly(1, 2, 3);
}
~~~

Đây là test quan trọng: publisher completion đại diện cho việc toàn bộ event đã được xử lý.

## 28. Test error, cancellation và backpressure

### 28.1. Test lỗi

~~~java
StepVerifier.create(
        Flux.just(1, 2)
            .concatWith(Mono.error(
                new IllegalStateException("source failed")
            ))
    )
    .expectNext(1, 2)
    .expectErrorMessage("source failed")
    .verify();
~~~

Test xác minh error signal được phát khi subscriber yêu cầu xử lý pipeline.

### 28.2. Test cancellation

~~~java
StepVerifier.create(Flux.interval(Duration.ofMillis(100)))
    .expectNext(0L)
    .thenCancel()
    .verify();
~~~

`thenCancel()` kiểm tra cancellation. Có thể kết hợp `doOnCancel` với counter để xác minh cleanup.

### 28.3. Test demand

~~~java
StepVerifier.create(Flux.range(1, 3), 0)
    .thenRequest(2)
    .expectNext(1, 2)
    .thenCancel()
    .verify();
~~~

Test này chứng minh source không cần phát toàn bộ dữ liệu ngay khi subscriber vừa được tạo; demand điều khiển số phần tử được yêu cầu.

## 29. Chẩn đoán trong Spring Cloud Stream

Khi function reactive không nhận message, kiểm tra theo thứ tự:

1. Function bean có tồn tại và có đúng generic signature không?
2. `spring.cloud.function.definition` có chọn đúng tên không?
3. Binding input/output có đúng tên convention không?
4. Destination và binder có đúng cấu hình không?
5. Producer có gửi message vào destination không?
6. Consumer group/subscription có được tạo không?
7. Reactive function có được gọi để nối stream lúc startup không?
8. Có `doOnSubscribe` ở đúng vị trí để xác nhận subscription?
9. Có demand và `onNext` không?
10. Filter/validation có loại bỏ toàn bộ item không?
11. Pipeline có `onError` hoặc cancellation không?
12. Output binding có consumer downstream và destination đúng không?

### 29.1. Cấu hình binding mẫu

~~~properties
spring.cloud.function.definition=processOrders
spring.cloud.stream.bindings.processOrders-in-0.destination=orders-in
spring.cloud.stream.bindings.processOrders-in-0.group=order-service
spring.cloud.stream.bindings.processOrders-out-0.destination=orders-out
~~~

Consumer group quyết định semantics phân phối/đăng ký consumer theo binder. Một ứng dụng có group khác có thể nhận một luồng message khác với ứng dụng bạn đang quan sát.

### 29.2. Kiểm tra startup log

Tìm log về:

- Function definition được chọn.
- Binding input/output được tạo.
- Binder connection và destination.
- Consumer group.
- Subscription/lifecycle của reactive function.
- Exception xảy ra trước khi binder kết nối.

Nếu startup log cho thấy binding đã được tạo, nhưng không có `onNext`, điều tra producer, destination, deserializer và filter trước khi kết luận thiếu subscription.

## 30. Bảng triệu chứng và hướng xử lý

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| Không có log trong map | Chưa subscribe | `doOnSubscribe`, caller/adapter |
| Có bean nhưng không có event | Chưa có adapter/source | Function definition và binding |
| Có subscribe nhưng không có onNext | Source rỗng, chưa emit hoặc demand bằng 0 | `doOnRequest`, source callback |
| Có onNext trước filter nhưng không có sau filter | Filter loại hết item | Counter trước/sau filter |
| Function trả Flux nhưng caller không thấy output | Caller không subscribe/consume | HTTP adapter hoặc StepVerifier |
| Consumer<Flux<T>> không chạy | Consumer không subscribe | Đổi sang Function<Flux<T>,Mono<Void>> |
| Supplier<Flux<T>> chỉ phát một batch | Stream hữu hạn chỉ được tạo một lần | Polling và @PollableBean |
| Event bị xử lý hai lần | Có nhiều subscription | `doOnSubscribe`, idempotency |
| Stream dừng sau một event | Error signal hoặc cancellation | `doOnError`, `doOnCancel` |
| Không có output nhưng Mono<Void> complete | Consumer không phát payload theo thiết kế | Kiểm tra side effect/completion |
| Output chậm | Backpressure hoặc source chậm | `doOnRequest`, scheduler, source latency |
| Test không chạy operator | Chưa gọi verify() | StepVerifier terminal assertion |
| subscribeOn đã cấu hình nhưng vẫn không chạy | Scheduler không tạo subscription | Caller/adapter |
| block() làm app treo | Blocking trong reactive pipeline | Loại bỏ block, compose publisher |
| Stream nóng bỏ lỡ event đầu | Subscriber đến muộn | Hot/cold, replay, source lifecycle |

## 31. Những hiểu nhầm phổ biến

| Hiểu nhầm | Sự thật |
| --- | --- |
| “Tạo Flux là dữ liệu bắt đầu chạy.” | Tạo publisher chỉ mô tả source/pipeline; subscription kích hoạt nó. |
| “map và filter là terminal operation.” | Chúng tạo publisher mới và không subscribe. |
| “doOnNext tự thực hiện side effect ngay khi khai báo.” | Callback chỉ chạy khi có item được phát. |
| “collectList() tự lấy dữ liệu.” | Nó trả Mono<List<T>>; vẫn cần subscription. |
| “then() subscribe vào Flux.” | then() tạo Mono<Void>, không tự subscribe. |
| “subscribeOn làm stream tự chạy.” | Nó chỉ chọn scheduler khi subscription diễn ra. |
| “Function reactive cần tự subscribe trong method.” | Thông thường hãy trả publisher cho adapter/binder quản lý. |
| “Consumer<Flux<T>> giống Function<Flux<T>,Mono<Void>>.” | Consumer trả void, framework không có publisher output để subscribe. |
| “Có bean trong FunctionCatalog là có subscriber.” | Catalog registration và subscription là hai việc khác nhau. |
| “Spring Cloud Stream gọi reactive function cho từng event.” | Reactive function được invoke một lần để nối stream. |
| “Reactive Supplier luôn được poll mỗi giây.” | Reactive Supplier liên tục thường được gọi một lần; finite supplier cần polling setup. |
| “@PollableBean tự triển khai poller trong SCF.” | Đây là marker; framework tích hợp như Stream cung cấp polling behavior. |
| “Một subscription luôn nhận toàn bộ lịch sử hot stream.” | Hot publisher có thể chỉ phát event mới cho subscriber đến muộn. |
| “Subscribe hai lần không ảnh hưởng.” | Cold publisher có thể chạy lại source và side effect hai lần. |
| “Có subscription thì chắc chắn có onNext.” | Source có thể empty/never, filter hết, chưa emit hoặc thiếu demand. |
| “Không có output nghĩa là stream chưa chạy.” | Mono<Void> có thể hoàn tất đúng mà không phát payload. |
| “block() là cách sửa reactive pipeline.” | block() tạo subscription nhưng chặn thread và có thể gây deadlock. |
| “Một Consumer reactive luôn được binder tự subscribe.” | Consumer<Flux<T>> trả void; cần tự subscribe hoặc đổi sang Function reactive. |
| “Lỗi trong subscribe nội bộ được framework quản lý như output Flux.” | Fire-and-forget subscription tách lỗi và cancellation khỏi pipeline chính. |

## 32. Checklist trước khi kết luận thiếu subscription

### 32.1. Publisher và caller

- [ ] Có publisher source thực sự được tạo?
- [ ] Các operator đã được nối vào publisher được return?
- [ ] Không có publisher con bị bỏ quên trong callback?
- [ ] Caller có subscribe hoặc tiếp tục compose publisher?
- [ ] Không có hai subscription ngoài ý muốn?
- [ ] Có demand và source có phát item?

### 32.2. Spring Cloud Function/Stream

- [ ] Function signature phản ánh đúng imperative/reactive model?
- [ ] Reactive Function trả Flux/Mono cho framework?
- [ ] Consumer<Flux<T>> có subscription rõ ràng hoặc đã đổi thành Function<Flux<T>,Mono<Void>>?
- [ ] Function definition chọn đúng bean?
- [ ] Binder đã tạo binding và kết nối destination?
- [ ] Reactive Supplier liên tục hay hữu hạn?
- [ ] Nếu finite Supplier, có polling mechanism phù hợp?
- [ ] Có phân biệt startup invocation với per-event processing?

### 32.3. Lifecycle và lỗi

- [ ] Có quan sát onError/onComplete/onCancel?
- [ ] Disposable thủ công được giữ và dispose đúng lúc?
- [ ] Retry có thể lặp side effect không?
- [ ] Backpressure có làm source chờ demand?
- [ ] Hot publisher có thể đã phát trước subscriber?
- [ ] Có test StepVerifier gọi terminal verify?

## 33. Câu hỏi tự đánh giá

1. `Flux` mô tả điều gì và vì sao nó không phải List đã thực thi?
2. Assembly và subscription khác nhau ở đâu?
3. Vì sao `map` không kích hoạt source?
4. Subscriber gửi những tín hiệu nào để bắt đầu nhận dữ liệu?
5. `request(n)` có vai trò gì?
6. `doOnNext` có tự subscribe không?
7. Vì sao `collectList()` vẫn chưa thực thi pipeline?
8. `publishOn` và `subscribeOn` có thay thế subscription không?
9. Vì sao reactive Function nên return publisher thay vì gọi subscribe bên trong?
10. Trong Spring Cloud Stream, reactive Function được invoke mấy lần và vào thời điểm nào?
11. Vì sao Consumer<Flux<T>> cần subscribe thủ công?
12. Vì sao Function<Flux<T>,Mono<Void>> là lựa chọn tốt hơn cho reactive sink?
13. `then()` khác `subscribe()` ở điểm nào?
14. Khi nào caller trực tiếp phải subscribe vào function output?
15. Vì sao subscribe hai lần có thể tạo side effect trùng?
16. Cold publisher và hot publisher khác nhau thế nào?
17. Vì sao hot publisher có thể làm subscriber đến muộn bỏ lỡ event?
18. `Supplier<Flux<T>>` liên tục khác finite supplier ra sao?
19. `PollableBean` có vai trò gì và framework nào thực hiện polling?
20. Vì sao có subscription nhưng không có onNext?
21. Filter có thể làm stream trông như không hoạt động như thế nào?
22. Error và cancellation khác nhau ra sao?
23. Vì sao retry có thể chạy lại side effect?
24. `StepVerifier.verifyComplete()` kích hoạt điều gì?
25. Làm thế nào kiểm tra binder đã tạo input binding và consumer group?
26. Vì sao `Mono<Void>` complete mà không có output payload vẫn có thể là đúng?
27. Khi nào quản lý Disposable thủ công là cần thiết?
28. Bạn sẽ phân biệt thiếu subscription với source không phát dữ liệu bằng những log nào?

## 34. Tài liệu tham khảo

- [Spring Cloud Function — Programming Model](https://docs.spring.io/spring-cloud-function/reference/spring-cloud-function/programming-model.html) — reactive Supplier, Function, Consumer; invocation semantics; `Consumer<Flux<?>>` cần subscribe; `PollableBean`.
- [Spring Cloud Stream — Producing and Consuming Messages](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/producing-and-consuming-messages.html) — binder wiring, reactive Consumer, `Function<Flux<?>,Mono<Void>>`, Supplier polling, PollableBean và poller properties.
- [Spring Cloud Stream — Observability](https://docs.spring.io/spring-cloud-stream/reference/observability.html) — reactive function là initialization function; khác biệt quan sát giữa imperative và reactive stream.
- [Project Reactor — Introduction to Reactive Programming](https://projectreactor.io/docs/core/release/reference/reactiveProgramming.html) — assembly, subscribe, request, backpressure và các tín hiệu Reactive Streams.
- [Project Reactor — Hot Versus Cold](https://projectreactor.io/docs/core/release/reference/advancedFeatures/reactor-hotCold.html) — semantics cold/hot, late subscriber, share và replay.
- [Project Reactor — Testing](https://projectreactor.io/docs/test/release/reference/) — `StepVerifier`, demand và cancellation.
- [Reactive Streams Specification](https://www.reactive-streams.org/) — contract Publisher, Subscriber, Subscription và backpressure.

Các ví dụ dùng Java 17+, Project Reactor và API của Spring Cloud Function/Spring Cloud Stream hiện hành. Tên binding, poller, binder capability và cách adapter quản lý subscription có thể khác theo BOM/phiên bản. Hãy kiểm tra đúng runtime adapter, signature và dependency của ứng dụng đang triển khai.

**Ghi nhớ:** `Flux` chỉ mô tả một chuỗi dữ liệu. Operator nối pipeline nhưng không tự chạy; subscription và demand mới kích hoạt việc phát dữ liệu. Trong reactive Function, hãy trả publisher để adapter/binder quản lý subscription. Với reactive Consumer, ưu tiên `Function<Flux<T>,Mono<Void>>` để framework có publisher completion; chỉ dùng `Consumer<Flux<T>>` khi chủ động subscribe và quản lý lỗi/cancel. Với reactive Supplier, phân biệt stream liên tục được subscribe một lần với stream hữu hạn cần polling. Khi chẩn đoán, quan sát subscription, request, onNext, onError, completion và cancellation; cuối cùng xác minh source/binding thực sự có dữ liệu bằng `StepVerifier` hoặc integration test.
