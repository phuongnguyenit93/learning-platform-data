# Quan sát reactive function theo phạm vi phần tử hoặc đoạn luồng

Trong Spring Cloud Stream, một reactive function thường nhận `Flux<T>` và trả về `Flux<R>` hoặc `Mono<Void>`. Khác với function imperative, reactive function không được framework gọi một lần cho từng message. Framework gọi function một lần khi khởi tạo để nối stream do ứng dụng khai báo với stream nguồn và đích của binder. Sau đó Reactor điều khiển việc subscribe, phát signal, xử lý lỗi và hoàn tất luồng.

Vì function reactive không được Spring Cloud Function bọc tự động bằng `ObservationFunctionAroundWrapper`, ứng dụng phải tự chọn phạm vi cần quan sát. Phạm vi đó có thể là một message, một lô message, một đoạn xử lý trong pipeline hoặc cả subscription của một stream. Reactor cung cấp `tap(Micrometer.observation(registry))` để gắn Micrometer Observation vào đúng đoạn đã chọn.

## 1. Vì sao reactive function cần quan sát thủ công?

Với function imperative, framework nhận một message, gọi function, đợi kết quả và kết thúc một invocation. Observation có thể bao quanh từng lần gọi, nên mỗi message thường tương ứng một Observation.

Reactive function có vòng đời khác:

1. Spring Cloud Stream gọi function lúc khởi động để nhận một `Flux`/`Mono` đã được khai báo.
2. Binder kết nối publisher nguồn với publisher đích.
3. Sau khi kết nối xong, Reactor điều khiển quá trình xử lý dữ liệu.
4. Một subscription có thể nhận nhiều message trong thời gian dài, thậm chí không bao giờ hoàn tất.

Do đó, không có một invocation tương ứng với từng message để framework tự động bọc. Nếu chỉ thêm dependency tracing rồi chờ framework tạo span cho từng event, có thể bạn sẽ không nhận được phạm vi quan sát mong muốn. Cần đặt Observation ở bên trong reactive pipeline.

| Mô hình | Cách function được gọi | Phạm vi Observation mặc định |
|---|---|---|
| Imperative `Function<T, R>` | Một lần cho mỗi message | Một Observation cho mỗi invocation khi hạ tầng observability đã có |
| Reactive `Function<Flux<T>, Flux<R>>` | Một lần khi khởi tạo pipeline | Không tự động tạo Observation cho từng phần tử |
| Reactive có `tap` trong `Mono` cho từng phần tử | Pipeline được lắp một lần; mỗi phần tử tạo một Mono | Một Observation cho từng message được xử lý |
| Reactive có `tap` trên một `Flux` | Pipeline được lắp một lần; Observation gắn với subscription của đoạn Flux | Một Observation cho cả subscription/đoạn luồng |

## 2. Observation, metrics và traces

Micrometer Observation là abstraction chung cho việc ghi nhận một hoạt động trong ứng dụng. Tùy cấu hình ObservationHandler và tracer bridge, một Observation có thể tạo metrics, trace span hoặc cả hai.

Trong một ứng dụng Spring Boot, các dependency cơ bản thường gồm:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>
<dependency>
    <groupId>io.projectreactor</groupId>
    <artifactId>reactor-core-micrometer</artifactId>
</dependency>
<dependency>
    <groupId>io.micrometer</groupId>
    <artifactId>micrometer-tracing-bridge-otel</artifactId>
</dependency>
~~~

Ví dụ dùng OpenTelemetry bridge. Có thể chọn một tracer bridge khác được Spring Boot hỗ trợ; nếu muốn xuất trace ra backend cụ thể, bổ sung exporter/registry tương ứng. Nên để Spring Boot dependency management quản lý phiên bản thay vì tự chọn các phiên bản rời rạc.

Spring Boot cấu hình `ObservationRegistry` khi các dependency observability phù hợp có mặt. Có thể inject registry vào bean function:

~~~java
@Bean
Function<Flux<String>, Flux<String>> processOrders(
        ObservationRegistry observationRegistry) {
    return events -> events
        .map(String::toUpperCase)
        .name("orders.normalize")
        .tap(Micrometer.observation(observationRegistry));
}
~~~

`ObservationRegistry` là điểm tiếp nhận Observation. `tap` là điểm trong Reactor pipeline tạo và quản lý Observation cho subscription. Chỉ inject registry mà không gắn `tap` thì chưa xác định được đoạn reactive nào cần đo.

## 3. `tap` xác định đơn vị quan sát

`tap` của Reactor nhận một `SignalListener` hoặc listener được tạo bởi thư viện tích hợp. Với Micrometer, dùng:

~~~java
.tap(Micrometer.observation(observationRegistry))
~~~

Observation được gắn vào publisher ở vị trí đặt `tap`. Thời gian được đo từ lúc subscription bắt đầu cho đến khi đoạn publisher hoàn tất, phát lỗi hoặc bị hủy. Vì vậy, vị trí `tap` quyết định phạm vi:

- Đặt trên một `Mono` tạo cho mỗi event: quan sát từng event.
- Đặt trên một `Mono` tạo cho mỗi batch: quan sát từng batch.
- Đặt trên một `Flux` đã giới hạn phạm vi: quan sát cả đoạn stream đó.
- Đặt trên một `Flux` sống lâu của consumer: Observation có thể kéo dài cho đến khi subscription bị hủy hoặc kết thúc.

Không có một lựa chọn mặc định phù hợp cho mọi reactive function. Hãy xác định trước câu hỏi vận hành cần trả lời: một message xử lý mất bao lâu, một batch mất bao lâu, hay cả pipeline đang hoạt động ra sao?

## 4. Quan sát từng message bằng `Mono`

Nếu muốn mỗi message có một Observation riêng, tạo một publisher `Mono` cho từng phần tử rồi đặt `tap` trên publisher đó:

~~~java
@Bean
Function<Flux<OrderEvent>, Flux<OrderResult>> observeEachOrder(
        ObservationRegistry observationRegistry) {

    return events -> events.flatMap(event ->
        Mono.just(event)
            .map(this::normalize)
            .flatMap(this::enrich)
            .name("orders.process")
            .tap(Micrometer.observation(observationRegistry))
    );
}
~~~

Ở đây, mỗi lần `flatMap` nhận một `OrderEvent`, nó tạo một `Mono` đại diện cho xử lý event đó. Observation bắt đầu khi Mono được subscribe và kết thúc khi chuỗi xử lý event hoàn tất, phát lỗi hoặc bị cancel. Nếu `enrich` là thao tác bất đồng bộ trả về `Mono<OrderResult>`, Observation bao gồm cả thời gian chờ publisher đó hoàn tất.

Tên `orders.process` ổn định và mô tả thao tác. Không đặt tên theo `eventId`, `orderId` hoặc giá trị thay đổi theo từng message, vì tên Observation thường tham gia vào metric identity và có thể tạo cardinality rất lớn.

`flatMap` có thể xử lý nhiều event đồng thời. Mỗi inner `Mono` vẫn có Observation riêng. Nếu cần giữ thứ tự đầu vào, cân nhắc `concatMap`; việc chọn `flatMap`, `concatMap` hay giới hạn concurrency là quyết định xử lý luồng, không phải tùy chọn của Observation.

## 5. Quan sát một batch hoặc một đoạn hữu hạn

Không phải lúc nào một message cũng là đơn vị phù hợp. Một pipeline có thể gom nhiều event rồi xử lý như một lô. Có thể dùng `bufferTimeout` để tạo batch theo số lượng hoặc thời gian:

~~~java
@Bean
Function<Flux<OrderEvent>, Flux<BatchResult>> observeOrderBatches(
        ObservationRegistry observationRegistry) {

    return events -> events
        .bufferTimeout(100, Duration.ofSeconds(1))
        .filter(batch -> !batch.isEmpty())
        .flatMap(batch ->
            Mono.fromSupplier(() -> aggregate(batch))
                .name("orders.batch")
                .tap(Micrometer.observation(observationRegistry))
                .flux()
        );
}
~~~

Mỗi batch tạo một `Mono`, vì vậy mỗi lần xử lý batch có một Observation. Ví dụ gom tối đa 100 event hoặc phát batch khi đã chờ một giây. Đây là thay đổi semantics của pipeline: nó ảnh hưởng latency, bộ nhớ và thời điểm phát kết quả. Chỉ dùng batching nếu nghiệp vụ cho phép.

Một đoạn xử lý hữu hạn cũng có thể được quan sát trực tiếp:

~~~java
Flux<OrderResult> normalizedSegment = events
    .map(this::normalize)
    .filter(this::isValid)
    .name("orders.normalize.segment")
    .tap(Micrometer.observation(observationRegistry));
~~~

Trong ví dụ này, Observation đo subscription của cả đoạn `normalize` và `filter`, không phải một Observation cho mỗi phần tử. Nếu upstream là một consumer stream liên tục, đoạn Flux có thể không hoàn tất trong thời gian dài. Khi đó timer của đoạn sẽ chỉ kết thúc khi có complete, error hoặc cancellation; không thể diễn giải duration của nó thành latency của một message.

## 6. Quan sát cả subscription của stream

Có thể đặt `tap` trên toàn bộ pipeline khi muốn biết thời gian sống, kết quả kết thúc và trạng thái của một subscription:

~~~java
@Bean
Function<Flux<OrderEvent>, Flux<OrderResult>> observeWholeStream(
        ObservationRegistry observationRegistry) {

    return events -> events
        .map(this::normalize)
        .filter(this::isValid)
        .flatMap(this::enrich)
        .name("orders.stream")
        .tap(Micrometer.observation(observationRegistry))
        .map(this::toResult);
}
~~~

Observation bao quanh phần publisher đứng trước `tap`; các toán tử đặt sau `tap` không thuộc đoạn được đo. Nếu muốn đo cả `toResult`, chuyển `tap` xuống sau toán tử đó.

Một Kafka consumer thường tạo subscription sống lâu. Nếu quan sát toàn bộ subscription như một Observation duy nhất, span/timer có thể mở trong nhiều giờ hoặc nhiều ngày. Điều này hữu ích cho một số chỉ số vòng đời stream, nhưng không thay thế message latency. Với consumer liên tục, thường nên có Observation riêng cho từng event hoặc batch, đồng thời dùng metrics riêng cho throughput, backlog và trạng thái consumer.

## 7. So sánh phạm vi quan sát

| Phạm vi | Cách đặt `tap` | Một Observation đại diện cho | Dùng khi |
|---|---|---|---|
| Một message | Trong `flatMap`, trên inner `Mono` | Một lần xử lý event | Đo latency và lỗi theo event |
| Một batch | Trong `flatMap` của batch, trên inner `Mono` | Một lần xử lý lô | Đo thời gian aggregate/bulk write |
| Một đoạn hữu hạn | Trên `Flux` đã giới hạn | Một subscription của đoạn đó | Đo một bước pipeline có điểm kết thúc |
| Cả stream | Trên publisher dài hạn | Vòng đời subscription | Theo dõi thời gian sống hoặc trạng thái của stream |

Khi chọn phạm vi, hãy xác định rõ Observation bắt đầu ở đâu và kết thúc ở đâu. Nếu cần đo thời gian chờ broker, cần instrumentation ở binder/producer/consumer tương ứng; `tap` trong function chỉ đo đoạn reactive pipeline mà nó bao quanh.

## 8. Đặt tên Observation và thêm metadata

Reactor cho phép đặt tên sequence bằng `name(String)`. Với Observation tap, tên đó được dùng để định danh Observation. Nên chọn tên ổn định theo thao tác:

~~~java
events
    .map(this::validate)
    .name("orders.validate")
    .tap(Micrometer.observation(observationRegistry));
~~~

Nếu cần custom metadata, có thể cung cấp một Observation supplier:

~~~java
events.flatMap(event ->
    Mono.just(event)
        .flatMap(this::enrich)
        .tap(Micrometer.observation(
            observationRegistry,
            registry -> Observation.createNotStarted(
                    "orders.enrich",
                    registry
                )
                .lowCardinalityKeyValue("stage", "enrich")
                .highCardinalityKeyValue("event.id", event.eventId())
        ))
);
~~~

`lowCardinalityKeyValue` phù hợp với thuộc tính có tập giá trị nhỏ và ổn định, chẳng hạn `stage=validate` hoặc `result=accepted`. Các giá trị này có thể được đưa vào metrics. `highCardinalityKeyValue` dành cho dữ liệu có nhiều giá trị khác nhau, ví dụ event ID; chúng phù hợp hơn với trace và không nên trở thành metric label.

Không đưa `orderId`, `customerId`, email, token hoặc payload nhạy cảm vào low-cardinality tags. High-cardinality trace attributes cũng có thể làm lộ dữ liệu cá nhân hoặc bí mật; chỉ thêm dữ liệu đã được phép ghi và thật sự cần cho điều tra.

## 9. Vị trí `tap` so với retry

Vị trí `tap` tương đối với `retryWhen` quyết định Observation đại diện cho một lần thử hay toàn bộ thao tác logic.

**Một Observation cho mỗi lần thử:**

~~~java
Mono.just(event)
    .flatMap(this::callRemoteService)
    .name("orders.remote.attempt")
    .tap(Micrometer.observation(observationRegistry))
    .retryWhen(retryPolicy);
~~~

`retryWhen` subscribe lại publisher đứng trước nó. Vì `tap` nằm trước `retryWhen`, mỗi lần thử tạo một subscription/Observation riêng. Cách này hữu ích khi cần đo số lần thử và latency của từng attempt.

**Một Observation cho cả thao tác, gồm các lần retry:**

~~~java
Mono.just(event)
    .flatMap(this::callRemoteService)
    .retryWhen(retryPolicy)
    .name("orders.remote.operation")
    .tap(Micrometer.observation(observationRegistry));
~~~

Ở đây, `tap` nằm sau retry. Nó quan sát kết quả cuối cùng của publisher sau khi retry kết thúc, nên duration bao gồm các lần thử và khoảng backoff. Nếu retry thành công, Observation của thao tác có thể kết thúc thành công dù các attempt trước đã lỗi. Nếu cần cả hai góc nhìn, tạo Observation cho attempt bên trong và Observation cho operation ở ngoài, với tên khác nhau.

## 10. Vị trí `tap` so với xử lý lỗi

`onErrorResume` có thể biến lỗi thành một kết quả dự phòng. Vị trí `tap` quyết định Observation nhìn thấy lỗi gốc hay kết quả phục hồi:

~~~java
Mono.just(event)
    .flatMap(this::enrich)
    .name("orders.enrich")
    .tap(Micrometer.observation(observationRegistry))
    .onErrorResume(this::fallbackResult);
~~~

Vì `tap` đứng trước `onErrorResume`, Observation thấy tín hiệu error từ `enrich`. Sau đó pipeline mới chuyển lỗi thành fallback result.

Nếu chuyển `tap` xuống sau `onErrorResume`, Observation sẽ thấy publisher đã phục hồi và có thể ghi nhận complete thay vì error:

~~~java
Mono.just(event)
    .flatMap(this::enrich)
    .onErrorResume(this::fallbackResult)
    .name("orders.enrich.with-fallback")
    .tap(Micrometer.observation(observationRegistry));
~~~

Hãy chọn theo câu hỏi cần trả lời. Nếu cần tỷ lệ lỗi kỹ thuật của bước enrich, đặt Observation trước recovery. Nếu cần kết quả cuối cùng mà pipeline cung cấp cho downstream, đặt Observation sau recovery. Không dùng fallback để che mất lỗi nếu hệ thống vẫn cần cảnh báo hoặc ghi nhận lỗi gốc.

## 11. Context propagation trong reactive pipeline

Trace context và các metadata liên quan thường được truyền qua Reactor Context. Khi pipeline chuyển thread bằng `publishOn`, `subscribeOn` hoặc thực hiện callback qua thư viện khác, cần bảo đảm context propagation được cấu hình phù hợp để trace/span và logging context không bị mất.

Ví dụ bật automatic context propagation ở lúc khởi động:

~~~java
public static void main(String[] args) {
    Hooks.enableAutomaticContextPropagation();
    SpringApplication.run(OrdersStreamApplication.class, args);
}
~~~

Hook này hỗ trợ đưa context qua các ranh giới xử lý Reactor được hỗ trợ. Nó không tự tạo Observation cho reactive function; vẫn cần đặt `tap`. Nếu ứng dụng dùng Spring Boot/Reactor với chế độ context propagation được cấu hình qua property, hãy dùng một cơ chế thống nhất theo phiên bản đang chạy, tránh bật nhiều cơ chế chồng lặp mà không có lý do.

Không truyền trace ID bằng cách tự gắn vào payload nghiệp vụ nếu mục đích chỉ là tracing. Dùng Observation/Micrometer context và cơ chế propagation của framework; chỉ đưa correlation ID nghiệp vụ vào header khi đó là một phần hợp đồng message.

## 12. Metrics được tạo từ Observation tap

Reactor Micrometer Observation tap có thể tạo timer cho thời lượng sequence và long-task timer cho sequence đang hoạt động. Các trạng thái kết thúc thường phân biệt:

| Trạng thái | Ý nghĩa |
|---|---|
| `completed` | Sequence phát ít nhất một phần tử rồi hoàn tất |
| `completedEmpty` | Sequence hoàn tất mà không phát phần tử |
| `error` | Sequence kết thúc bằng lỗi |
| `cancelled` | Subscription bị hủy |

Những trạng thái này hữu ích khi đọc metrics: một consumer có thể bị cancel do shutdown/rebalance, một filter có thể tạo sequence rỗng, hoặc một xử lý có thể kết thúc do exception. Đừng gộp cancellation thành lỗi nghiệp vụ nếu cancellation chỉ là lifecycle bình thường.

Tên sequence được đặt bằng `name` sẽ trở thành prefix/identity của Observation. Giữ số lượng tên hữu hạn và có ý nghĩa. Tránh tạo tên khác nhau theo từng event, tenant hoặc request.

## 13. Metrics theo đoạn và metrics theo phần tử không giống nhau

Nếu `tap` đặt trên một `Flux` dài hạn, số lần subscribe thường ít nhưng thời gian sống rất dài. Nếu đặt trên inner `Mono` cho từng event, số lượng Observation tăng theo số event. Hai cách trả lời những câu hỏi khác nhau:

- Stream Observation: subscription còn hoạt động không, đã kết thúc chưa, duration vòng đời là bao lâu?
- Element Observation: mỗi event xử lý mất bao lâu, lỗi ở bao nhiêu event?
- Batch Observation: mỗi lô xử lý mất bao lâu, kích thước lô và hiệu quả bulk operation ra sao?

Không dùng stream-level duration làm p95/p99 latency của message. Cũng không tạo trace cho mọi event với metadata không giới hạn nếu lưu lượng rất lớn và chi phí trace vượt ngân sách. Có thể dùng sampling cho traces và metrics có cardinality thấp để theo dõi xu hướng toàn bộ traffic.

## 14. Reactive function và binder không reactive

Việc function dùng `Flux`/`Mono` không đồng nghĩa nguồn và đích đều hỗ trợ reactive transport. Một số binder như regular Kafka Binder hoặc Rabbit binder có thể cung cấp message theo cơ chế imperative rồi được framework nối vào reactive API. Trong trường hợp đó, ứng dụng vẫn dùng được các toán tử Reactor và có thể gắn Observation vào pipeline, nhưng không nên mặc định rằng backpressure đầu-cuối hoặc mọi đặc tính reactive của transport đều được hỗ trợ.

Reactive Kafka binder có nguồn/đích reactive hơn và có các khả năng riêng. Dù dùng binder nào, Observation gắn bằng `tap` vẫn chỉ đo đoạn pipeline được đặt instrumentation; muốn đo publish/receive ở tầng broker, bật observability của binder hoặc dùng metrics của broker/client tương ứng.

## 15. Reactive Consumer nên có kiểu trả về thể hiện completion

Với reactive consumer, kiểu `Consumer<Flux<T>>` có `void` return nên framework không có publisher trả về để subscribe. Nếu cần reactive consumer, thường nên dùng `Function<Flux<T>, Mono<Void>>`:

~~~java
@Bean
Function<Flux<OrderEvent>, Mono<Void>> consumeOrders(
        ObservationRegistry observationRegistry) {

    return events -> events
        .flatMap(event ->
            Mono.just(event)
                .flatMap(this::persist)
                .name("orders.persist")
                .tap(Micrometer.observation(observationRegistry))
        )
        .then();
}
~~~

`then()` tạo `Mono<Void>` hoàn tất khi các xử lý phía trước hoàn tất. Nếu vẫn dùng `Consumer<Flux<T>>`, chính ứng dụng phải subscribe vào Flux vì kiểu `Consumer` không trả publisher để framework subscribe. Chỉ tạo một subscription có chủ đích; subscribe lặp có thể tạo nhiều luồng xử lý, làm khó kiểm soát lifecycle hoặc khiến acknowledgement không còn gắn với completion mong muốn.

## 16. Kiểm thử phạm vi Observation

Kiểm thử reactive function nên xác minh cả dữ liệu và vòng đời Observation:

1. Dùng `StepVerifier` để phát một hoặc nhiều event và xác nhận output.
2. Dùng `ObservationRegistry` có test handler để ghi lại Observation bắt đầu/kết thúc.
3. Với thiết kế per-item, gửi N event và xác nhận có N Observation tương ứng với các publisher Mono được subscribe.
4. Với thiết kế per-batch, gửi đủ event để tạo batch và xác nhận mỗi batch có một Observation.
5. Với stream-level, xác nhận Observation chỉ kết thúc khi sequence complete, error hoặc cancel.
6. Kiểm tra error và cancellation để chắc chắn trạng thái Observation phù hợp.
7. Kiểm tra retry với `tap` trước/sau retry để xác nhận số Observation đúng với ý định.
8. Kiểm tra context propagation khi pipeline có `publishOn` hoặc `subscribeOn`.
9. Kiểm tra metric labels chỉ dùng giá trị có cardinality phù hợp.

Ví dụ test hành vi dữ liệu:

~~~java
StepVerifier.create(processOrders(inputEvents))
    .expectNextMatches(result ->
        result.orderId().equals("order-1"))
    .verifyComplete();
~~~

Đây là test cho kết quả reactive. Nó không thay thế test Observation handler hoặc integration test với tracing backend; muốn xác minh trace xuất hiện trong backend, cần chạy cấu hình exporter và kiểm tra trace được xuất thành công.

## 17. Những lỗi quan sát thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Không có span cho từng message | Chỉ inject ObservationRegistry, không đặt `tap` trong pipeline | Tạo Observation per-item bằng inner Mono |
| Chỉ thấy một Observation rất dài | `tap` đặt trên Flux consumer sống lâu | Chọn per-item hoặc per-batch nếu cần latency |
| Observation không kết thúc | Sequence không complete và subscription chưa bị cancel | Xem lại đơn vị quan sát; dùng segment hữu hạn |
| Retry chỉ có một Observation | `tap` đặt sau `retryWhen` | Đặt tap trước retry nếu muốn một Observation mỗi attempt |
| Lỗi không xuất hiện trong Observation | `onErrorResume` chạy trước tap | Đặt tap trước recovery để ghi nhận lỗi gốc |
| Trace context mất sau đổi thread | Context propagation chưa được cấu hình đúng | Kiểm tra Reactor Context và automatic propagation |
| Metrics có quá nhiều time series | Dùng event ID/order ID làm metric tag hoặc name | Chuyển dữ liệu định danh sang trace/log đã kiểm soát |
| Không thấy trace ở backend | Thiếu tracer bridge/exporter hoặc exporter chưa cấu hình | Kiểm tra dependencies, ObservationHandler và exporter |
| Backpressure không hoạt động như mong đợi | Binder source/target không phải reactive transport | Xác minh khả năng của binder đang dùng |

## 18. Checklist triển khai

- [ ] Đã thêm Actuator, `reactor-core-micrometer` và tracer bridge/registry cần thiết.
- [ ] Đã xác nhận Spring Boot cung cấp `ObservationRegistry`.
- [ ] Đã nhớ reactive function chỉ được gọi để khởi tạo pipeline và không tự được bọc per-message.
- [ ] Đã chọn đơn vị Observation: một message, một batch, một segment hoặc cả subscription.
- [ ] Đã đặt `tap(Micrometer.observation(registry))` đúng vị trí trong pipeline.
- [ ] Đã đặt tên Observation ổn định bằng `name`.
- [ ] Đã quyết định Observation bao gồm hay tách riêng retry attempt.
- [ ] Đã đặt tap trước/sau error recovery theo ý nghĩa muốn ghi nhận.
- [ ] Đã cấu hình context propagation nếu pipeline đổi thread và cần giữ trace context.
- [ ] Metric tags có cardinality thấp; không đưa ID cá nhân/nghiệp vụ vào metric labels.
- [ ] Đã cân nhắc chi phí trace và sampling với lưu lượng thực tế.
- [ ] Đã phân biệt pipeline Observation với metrics/observability ở tầng broker.
- [ ] Đã kiểm thử completion, error, cancellation, retry và context propagation.

Reactive function không có một lần gọi cho mỗi message, nên framework không thể tự chọn đơn vị Observation thay ứng dụng. Dùng `tap(Micrometer.observation(registry))` để gắn Observation vào một đoạn publisher có phạm vi rõ: inner `Mono` cho từng event, `Mono` cho từng batch hoặc `Flux` cho một segment/subscription. Vị trí của tap so với retry và error recovery quyết định thời gian cùng trạng thái được ghi nhận. Khi kết hợp tên ổn định, cardinality có kiểm soát và context propagation phù hợp, metrics và traces sẽ phản ánh đúng đơn vị xử lý mà đội vận hành cần theo dõi.

## Tài liệu tham khảo

- [Spring Cloud Stream — Observability](https://docs.spring.io/spring-cloud-stream/reference/observability.html)
- [Spring Cloud Stream — Reactive Functions](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/producing-and-consuming-messages.html)
- [Project Reactor — Exposing Reactor Metrics and Micrometer Observation](https://projectreactor.io/docs/core/release/reference/metrics.html)
- [Project Reactor — Context Propagation Support](https://projectreactor.io/docs/core/release/reference/advanced-contextPropagation.html)
- [Spring Boot — Observability](https://docs.spring.io/spring-boot/reference/actuator/observability.html)
