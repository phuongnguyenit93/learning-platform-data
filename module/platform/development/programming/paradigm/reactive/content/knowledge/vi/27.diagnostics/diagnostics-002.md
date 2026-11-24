# Ghi log tín hiệu và truy theo vòng đời đăng ký

Khi một pipeline reactive cho kết quả sai hoặc chậm, chỉ ghi lại giá trị cuối cùng thường không đủ để tìm nguyên nhân. Ta cần biết Publisher được subscribe khi nào, Subscriber yêu cầu bao nhiêu phần tử, tín hiệu đi qua những toán tử nào, lỗi xuất hiện ở đâu và subscription kết thúc bằng complete, error hay cancel. Ghi log theo vòng đời giúp tái dựng diễn biến của một lần xử lý mà không làm thay đổi hợp đồng của luồng.

Bài học thuộc chương **Chẩn đoán** của module **REACTIVE_PROGRAMMING**. Module hướng dẫn tư duy theo các luồng sự kiện bất đồng bộ, hợp đồng Publisher–Subscriber và backpressure của Reactive Streams; người học thực hành **Mono**, **Flux**, kết hợp toán tử, kiểm soát scheduler, xử lý lỗi và kiểm thử pipeline trong hệ sinh thái Java. Bài này tập trung vào các tín hiệu của Reactive Streams, hook quan sát trong Reactor, correlation ID theo subscription và cách kiểm thử vòng đời đăng ký.

## Vòng đời một subscription gồm những gì?

Khi Subscriber đăng ký với Publisher, một chuỗi tín hiệu và yêu cầu được hình thành:

1. Subscriber gọi `subscribe`.
2. Publisher gửi `onSubscribe` kèm một `Subscription`.
3. Subscriber gọi `request(n)` để yêu cầu phần tử, hoặc gọi `cancel()` để hủy.
4. Publisher phát không quá số phần tử đã được yêu cầu qua `onNext`.
5. Luồng kết thúc bằng `onComplete` hoặc `onError`; Subscriber cũng có thể hủy trước khi kết thúc.

Sơ đồ thể hiện luồng chính của tín hiệu:

~~~mermaid
sequenceDiagram
    participant S as Subscriber
    participant P as Publisher
    S->>P: subscribe()
    P-->>S: onSubscribe(subscription)
    S->>P: request(n)
    P-->>S: onNext(value)
    P-->>S: onNext(value)
    alt Hoàn tất bình thường
        P-->>S: onComplete()
    else Có lỗi
        P-->>S: onError(error)
    else Subscriber hủy
        S->>P: cancel()
    end
~~~

`request(n)` và `cancel()` là lời gọi từ Subscriber qua Subscription, không phải tín hiệu `on...` mà Publisher gửi tới Subscriber. Phân biệt hai chiều này rất quan trọng khi đọc log: log `request(10)` cho biết downstream đang xin thêm demand, còn log `onNext` cho biết một phần tử thực sự đã được phát.

Một subscription chỉ có một tín hiệu kết thúc: `onComplete` hoặc `onError`, hoặc bị hủy trước khi một tín hiệu kết thúc được gửi. Sau khi đã cancel, Subscriber không còn chờ nhận tín hiệu kết thúc từ Publisher. Vì vậy, cancellation cần được quan sát riêng.

## Chọn hook theo tín hiệu cần quan sát

Reactor cung cấp các toán tử `doOn...` để thực hiện side effect khi một sự kiện của subscription hoặc tín hiệu đi qua vị trí toán tử:

| Hook | Thời điểm chạy | Dùng để quan sát |
|---|---|---|
| `doOnSubscribe` | Khi nhận Subscription | Bắt đầu một lần đăng ký |
| `doOnRequest` | Khi demand được yêu cầu upstream qua vị trí hook | Số phần tử downstream đang yêu cầu |
| `doOnNext` | Khi một phần tử đi qua | Giá trị hoặc mã định danh của phần tử |
| `doOnEach` | Khi tín hiệu `onNext`, `onError` hoặc `onComplete` đi qua | Quan sát nhiều loại tín hiệu cùng một nơi |
| `doOnError` | Khi lỗi đi qua | Ghi exception và thông tin chẩn đoán |
| `doOnComplete` | Khi hoàn tất bình thường | Ghi nhận luồng đã hoàn tất |
| `doOnCancel` | Khi cancellation được yêu cầu | Ghi nhận downstream đã hủy |
| `doFinally` | Sau khi kết thúc bằng complete, error hoặc cancel | Ghi nhận loại kết thúc cho mọi nhánh |

Các hook này không thay thế lẫn nhau. `doOnComplete` không chạy khi luồng lỗi hoặc bị hủy. `doOnError` không chạy khi Subscriber cancel. Nếu cần một điểm ghi nhận chung cho mọi kiểu kết thúc, dùng `doFinally`.

Ví dụ quan sát vòng đời của một luồng đơn hàng:

~~~java
Flux<Order> orders = orderRepository.findOrders()
    .doOnSubscribe(subscription ->
        log.info("orders subscribed"))
    .doOnRequest(n ->
        log.debug("orders demand={}", n))
    .doOnNext(order ->
        log.debug("order emitted id={}", order.id()))
    .doOnError(error ->
        log.warn("orders failed", error))
    .doOnComplete(() ->
        log.info("orders completed"))
    .doOnCancel(() ->
        log.info("orders cancelled"))
    .doFinally(signalType ->
        log.info("orders terminated signal={}", signalType));
~~~

Đoạn mã ghi nhận thời điểm đăng ký, demand, phần tử được phát và nhánh kết thúc. Trong ứng dụng thực tế, hãy thêm mã tương quan để phân biệt nhiều request chạy đồng thời và tránh ghi toàn bộ payload nếu dữ liệu có thể chứa thông tin nhạy cảm.

## Đặt hook ở đâu sẽ quyết định log nhìn thấy điều gì

Các hook quan sát tín hiệu tại vị trí chúng xuất hiện trong chuỗi toán tử. Do đó, thứ tự đặt hook có ý nghĩa:

~~~java
Flux<String> names = source
    .doOnNext(value ->
        log.debug("before map value={}", value))
    .map(String::trim)
    .doOnNext(value ->
        log.debug("after map value={}", value));
~~~

Hook đầu tiên ghi giá trị trước khi `map` biến đổi; hook thứ hai ghi giá trị sau khi `map` hoàn tất. Nếu đặt `doOnError` trước một toán tử chuyển lỗi hoặc phục hồi lỗi, hook có thể thấy lỗi gốc; nếu đặt sau, nó có thể thấy lỗi đã được ánh xạ hoặc lỗi mới phát sinh.

`doOnRequest` cũng phụ thuộc vị trí. Hook quan sát demand đi qua điểm đặt hook theo hướng upstream. Một toán tử như `publishOn`, `buffer` hoặc `flatMap` có thể thay đổi cách demand được chia lô, prefetch hoặc chuyển tiếp. Vì vậy, số được ghi tại một vị trí không nhất thiết bằng số phần tử downstream cuối cùng nhận được.

Đừng diễn giải `request(n)` là “ứng dụng đã xử lý n phần tử”. Đó là demand được yêu cầu tại một ranh giới của pipeline. Nguồn có thể chưa phát đủ, luồng có thể lỗi hoặc bị cancel trước khi phát hết phần tử đã yêu cầu.

## Dùng log() để xem tín hiệu của Reactor

Reactor có toán tử `log()` để ghi các sự kiện của subscription và tín hiệu tại một vị trí trong pipeline:

~~~java
Flux<Order> orders = orderRepository.findOrders()
    .log("orders.repository")
    .map(this::toOrderView)
    .log("orders.view");
~~~

Hai vị trí log giúp so sánh tín hiệu trước và sau phép ánh xạ. Log có thể cho thấy `onSubscribe`, request, `onNext`, `onComplete`, `onError` và cancel tùy loại tín hiệu được bật trong overload đang dùng.

`log()` hữu ích khi điều tra tại môi trường phát triển hoặc khi cần kiểm tra nhanh thứ tự tín hiệu. Trong production, log từng phần tử có thể tạo lượng log rất lớn, tăng chi phí định dạng và ghi log, đồng thời làm lộ dữ liệu. Khi đã hiểu vấn đề, nên chuyển sang hook chọn lọc hoặc cấu hình category/level phù hợp.

Log của Reactor thường chứa tên category, thread, subscription và tín hiệu. Hãy dùng chúng để xác định ranh giới xử lý, nhưng đừng dựa riêng vào tên thread để xác định request vì worker có thể được tái sử dụng cho nhiều subscription.

## Gắn correlation ID theo subscription bằng Reactor Context

Một hệ thống xử lý nhiều request đồng thời cần biết các log thuộc về request nào. Có thể truyền `requestId` trong Reactor Context và đọc nó tại các hook:

~~~java
Flux<Order> tracedOrders = Flux.deferContextual(context -> {
    String requestId =
        context.getOrDefault("requestId", "unknown");

    return orderRepository.findOrders()
        .doOnSubscribe(subscription ->
            log.info("request={} subscribed", requestId))
        .doOnRequest(n ->
            log.debug("request={} demand={}", requestId, n))
        .doOnNext(order ->
            log.debug("request={} order={}",
                requestId, order.id()))
        .doOnError(error ->
            log.warn("request={} failed", requestId, error))
        .doFinally(signalType ->
            log.info("request={} terminated as {}",
                requestId, signalType));
});
~~~

Khi đăng ký, đặt Context cho subscription:

~~~java
tracedOrders
    .contextWrite(context ->
        context.put("requestId", requestId))
    .subscribe(
        this::handleOrder,
        error -> log.error("request failed", error)
    );
~~~

`deferContextual` đọc Context tại thời điểm subscribe, nên mỗi subscription có thể nhận một `requestId` khác nhau dù cùng dùng một Publisher đã khai báo trước. Context được truyền theo subscription và không phụ thuộc thread hiện tại.

Cũng có thể đọc Context trực tiếp từ `Signal` trong `doOnEach`:

~~~java
Flux<Order> traced = orderRepository.findOrders()
    .doOnEach(signal -> {
        String requestId = signal.getContextView()
            .getOrDefault("requestId", "unknown");

        if (signal.isOnNext()) {
            log.debug("request={} next order={}",
                requestId, signal.get().id());
        } else if (signal.isOnError()) {
            log.warn("request={} error",
                requestId, signal.getThrowable());
        } else if (signal.isOnComplete()) {
            log.debug("request={} complete", requestId);
        }
    });
~~~

`doOnEach` quan sát các tín hiệu `onNext`, `onError` và `onComplete`; nó không thay thế `doOnSubscribe` hoặc `doOnRequest`. Dùng `Signal.getContextView()` để lấy metadata gắn với tín hiệu, đặc biệt hữu ích khi không muốn đóng biến request ID trong nhiều lambda.

Reactor Context không phải MDC của logging. Nếu thư viện log đọc MDC từ ThreadLocal, việc đặt request ID trong Context không tự động khiến MDC có giá trị sau mỗi lần đổi scheduler. Hãy dùng tích hợp context propagation phù hợp hoặc truyền metadata tường minh; tránh tự đặt ThreadLocal trong một hook rồi giả định hook khác sẽ chạy trên cùng thread.

## Theo dõi một pipeline qua nhiều ranh giới

Với pipeline gồm gọi dịch vụ, biến đổi và ghi dữ liệu, nên dùng cùng một correlation ID ở mỗi ranh giới:

~~~java
Mono<Receipt> processOrder(String orderId) {
    return orderService.load(orderId)
        .doOnSubscribe(s ->
            log.debug("load order subscribed id={}", orderId))
        .flatMap(order ->
            paymentService.authorize(order)
                .doOnSubscribe(s ->
                    log.debug("payment subscribed order={}",
                        order.id())))
        .flatMap(payment ->
            receiptRepository.save(payment)
                .doOnNext(receipt ->
                    log.info("receipt saved id={}", receipt.id())))
        .checkpoint("order.process");
}
~~~

Ví dụ cho thấy có thể đặt hook ở các bước nghiệp vụ để xác định pipeline dừng ở đâu. Trong hệ thống thực tế, hãy đưa `requestId`, `orderId` hoặc trace ID vào Context để mọi tầng dùng cùng mã tương quan, thay vì chỉ đóng biến cục bộ như ví dụ ngắn này.

Log theo subscription và distributed tracing phục vụ hai mục tiêu liên quan nhưng khác nhau. Log ghi sự kiện và dữ liệu chẩn đoán; tracing tạo span, quan hệ cha-con và thời gian qua nhiều dịch vụ. Với hệ thống có Micrometer Tracing hoặc OpenTelemetry, hãy dùng instrumentation tương ứng để tạo và truyền span context. Không nên tự tạo một span cho từng `onNext` nếu luồng có hàng triệu phần tử; thường span ở ranh giới thao tác hoặc batch có ích hơn.

## Dùng checkpoint để truy dấu lỗi về nơi lắp ráp

Pipeline reactive thường được lắp ráp ở một phương thức rồi mới subscribe ở một nơi khác. Stack trace lúc lỗi có thể tập trung vào nơi tín hiệu được phát, không cho thấy đầy đủ vị trí lắp ráp chuỗi toán tử.

`checkpoint(description)` thêm một marker có tên vào thông tin lỗi:

~~~java
Mono<Invoice> invoice = invoiceRepository.findById(invoiceId)
    .map(this::calculateTotal)
    .checkpoint("invoice.calculate-total");
~~~

Marker giúp nhận diện ranh giới pipeline trong stack trace khi lỗi đi qua. `checkpoint()` không tham số có thể thu thập stack trace lúc lắp ráp để chẩn đoán sâu hơn, nhưng chi phí cao hơn. Hãy ưu tiên checkpoint có mô tả ở những ranh giới quan trọng; chỉ bật chế độ debug toàn cục khi cần điều tra.

`Hooks.onOperatorDebug()` bật chế độ ghi nhận thông tin lắp ráp cho các operator được tạo sau khi hook được bật. Chế độ này có chi phí runtime và có thể làm giảm throughput. Nếu sử dụng để điều tra, hãy bật sớm trước khi tạo pipeline cần theo dõi, giới hạn phạm vi môi trường và gọi `Hooks.resetOnOperatorDebug()` khi không còn cần thiết. Đừng xem nó là cấu hình mặc định miễn phí cho production.

## Đừng để hook làm thay đổi hành vi pipeline

Các toán tử `doOn...` dành cho side effect quan sát. Chúng không nên thực hiện công việc nghiệp vụ, chặn thread hoặc ném exception mới:

- Ghi log đồng bộ nặng có thể làm chậm thread đang phát tín hiệu.
- Gọi HTTP hoặc database trong `doOnNext` khiến hook trở thành một bước xử lý ẩn.
- Ném exception từ callback quan sát có thể làm thay đổi kết quả pipeline.
- Ghi toàn bộ object có thể tiết lộ token, thông tin cá nhân hoặc dữ liệu nghiệp vụ.

Nếu cần thực hiện một thao tác bất đồng bộ và kết quả của nó ảnh hưởng tới luồng, hãy dùng toán tử chuyển đổi như `flatMap`, `concatMap` hoặc `then`, không dùng hook quan sát. Nếu chỉ cần metric hoặc log, hãy giữ callback ngắn và không chặn.

Với luồng có tần suất cao, nên ghi số liệu tổng hợp thay vì log mọi phần tử. Có thể đếm số phần tử, ghi thời gian bắt đầu/kết thúc, số lỗi theo loại và số lần cancel. Dùng sampling hoặc log theo mức chi tiết có kiểm soát để giảm overhead.

## Kiểm thử vòng đời bằng StepVerifier

Kiểm thử có thể xác nhận subscription, demand và cancellation mà không cần dựa vào log văn bản. Ví dụ sau kiểm tra một subscriber yêu cầu hai phần tử rồi hủy:

~~~java
AtomicInteger subscriptions = new AtomicInteger();
AtomicLong requested = new AtomicLong();
AtomicReference<SignalType> termination = new AtomicReference<>();

Flux<Integer> source = Flux.range(1, 5)
    .doOnSubscribe(s -> subscriptions.incrementAndGet())
    .doOnRequest(requested::addAndGet)
    .doFinally(termination::set);

StepVerifier.create(source, 0)
    .thenRequest(2)
    .expectNext(1, 2)
    .thenCancel()
    .verify();

assertEquals(1, subscriptions.get());
assertEquals(2L, requested.get());
assertEquals(SignalType.CANCEL, termination.get());
~~~

Test bắt đầu với demand bằng 0, sau đó yêu cầu hai phần tử. `doFinally` ghi nhận `CANCEL`, còn `doOnRequest` quan sát demand tại vị trí hook. Nếu đặt thêm operator có prefetch trước hook, giá trị demand quan sát được có thể khác; hãy đặt hook ở đúng ranh giới cần kiểm tra.

Kiểm tra nhánh hoàn tất:

~~~java
AtomicReference<SignalType> termination = new AtomicReference<>();

StepVerifier.create(
        Flux.just("a", "b").doFinally(termination::set))
    .expectNext("a", "b")
    .verifyComplete();

assertEquals(SignalType.ON_COMPLETE, termination.get());
~~~

Kiểm tra nhánh lỗi:

~~~java
RuntimeException failure = new IllegalStateException("database unavailable");
AtomicReference<SignalType> termination = new AtomicReference<>();

StepVerifier.create(
        Flux.<String>error(failure).doFinally(termination::set))
    .expectErrorSame(failure)
    .verify();

assertEquals(SignalType.ON_ERROR, termination.get());
~~~

Các kiểm thử này xác nhận hành vi của pipeline bằng trạng thái quan sát được. Nếu cần kiểm tra nội dung log, có thể dùng appender test của logging framework, nhưng không nên biến câu chữ log thành hợp đồng nghiệp vụ nếu không thật sự cần.

## Những lỗi thường gặp

| Cách làm | Vấn đề | Cách xử lý |
|---|---|---|
| Chỉ log `onNext` | Không biết subscription bắt đầu, demand ra sao hoặc kết thúc thế nào | Theo dõi cả subscribe, request và finally |
| Cho rằng `doOnComplete` chạy khi cancel | Cancellation không phải complete | Dùng `doOnCancel` hoặc `doFinally` |
| Xem `request(n)` là số phần tử đã xử lý | Demand có thể chưa được đáp ứng hoặc bị chia lô | Phân biệt request với `onNext` |
| Đặt hook ở một vị trí bất kỳ | Giá trị và demand quan sát được có thể thuộc ranh giới khác | Đặt hook trước/sau operator theo mục tiêu |
| Dùng ThreadLocal làm correlation ID | Ngữ cảnh có thể mất khi đổi scheduler hoặc bị lẫn trên worker dùng chung | Dùng Reactor Context và context propagation |
| Log mọi payload ở production | Tăng overhead và có thể lộ dữ liệu nhạy cảm | Log ID, metadata đã lọc và metric tổng hợp |
| Gọi dịch vụ khác trong `doOnNext` | Tạo side effect ẩn và khó điều phối lỗi | Dùng `flatMap` hoặc operator phù hợp |
| Bật operator debug toàn cục lâu dài | Tăng chi phí runtime | Dùng checkpoint có tên và bật debug có thời hạn |
| Không truyền error consumer vào subscribe | Lỗi có thể đi vào cơ chế dropped/unhandled | Xử lý lỗi ở pipeline hoặc cung cấp error consumer rõ ràng |

## Nguyên tắc thiết kế log và tracing

Khi thêm khả năng quan sát cho một pipeline reactive, hãy xác định:

1. Cần biết subscription bắt đầu, demand, phần tử, lỗi hay kiểu kết thúc nào?
2. Hook được đặt ở ranh giới nào để quan sát đúng tín hiệu cần tìm?
3. Mỗi subscription có correlation ID riêng được truyền bằng Context chưa?
4. Log có tránh payload nhạy cảm và giới hạn số dòng ở luồng tần suất cao không?
5. Hook có ngắn, không blocking và không làm thay đổi hành vi nghiệp vụ không?
6. Lỗi cần checkpoint ở những ranh giới lắp ráp nào?
7. Distributed trace được tạo bằng instrumentation phù hợp hay đang bị nhầm với log?
8. Kiểm thử có bao phủ complete, error, request và cancel không?

Ghi log theo vòng đời giúp xác định một subscription đã bắt đầu ở đâu, yêu cầu bao nhiêu demand, phát những tín hiệu nào và kết thúc ra sao. Khi đặt hook đúng vị trí, truyền correlation ID bằng Reactor Context và kiểm thử các nhánh kết thúc, ta có thể chẩn đoán pipeline reactive mà không phụ thuộc vào giả định rằng toàn bộ công việc chạy trên một thread.
