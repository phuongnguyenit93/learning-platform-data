# Ứng dụng Web

## Ngắt kết nối từ phía người dùng và hủy chuỗi xử lý

Trong mô-đun **REACTIVE_PROGRAMMING**, ta học cách tổ chức ứng dụng quanh các luồng sự kiện bất đồng bộ, hợp đồng Publisher–Subscriber và cơ chế backpressure của Reactive Streams. Ta thực hành `Mono`, `Flux`, kết hợp toán tử, kiểm soát scheduler, xử lý lỗi và kiểm thử pipeline trong hệ sinh thái Java. Một request HTTP có thể kết thúc trước khi chuỗi xử lý phía server hoàn tất: người dùng đóng tab, trình duyệt điều hướng sang trang khác, ứng dụng mobile hủy request hoặc kết nối mạng bị ngắt. Với Spring WebFlux và Project Reactor, việc ngắt kết nối này thường được biểu diễn bằng **tín hiệu cancellation** truyền từ Subscriber của response ngược lên Publisher.

Cancellation giúp giải phóng công việc và tài nguyên không còn cần thiết. Khi framework phát hiện client không còn nhận response, nó có thể hủy subscription đang tạo nội dung phản hồi. Các toán tử Reactor truyền tín hiệu hủy về upstream; nguồn có thể dừng truy vấn, hủy request tới dịch vụ phụ thuộc, gỡ listener hoặc giải phóng tài nguyên. Hiệu quả thực tế phụ thuộc vào việc từng adapter và hệ thống bên ngoài có hỗ trợ cancellation hay không.

Cancellation không phải là một tín hiệu lỗi và cũng không tự động hoàn tác tác dụng phụ đã xảy ra. Vì vậy, một pipeline WebFlux cần được thiết kế để gắn vòng đời công việc với request, dọn tài nguyên đúng cách và xử lý những thao tác nghiệp vụ có thể đã hoàn tất ở hệ thống từ xa.

### Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích cách client disconnect dẫn tới cancellation của response Publisher trong WebFlux.
- Phân biệt cancellation với `onComplete`, `onError`, timeout và lỗi ghi response.
- Mô tả cách cancellation truyền qua các toán tử Reactor và Publisher con.
- Dùng `doOnCancel`, `doFinally`, `using` và `usingWhen` để quan sát hoặc giải phóng tài nguyên.
- Tránh nested subscription làm công việc nền sống ngoài vòng đời HTTP request.
- Xử lý callback đến muộn và adapter không hỗ trợ hủy thực sự.
- Đánh giá ảnh hưởng của cancellation tới transaction, request phụ thuộc và tác dụng phụ.
- Kiểm thử cancellation bằng `StepVerifier` và kiểm thử tích hợp WebFlux.

## 1. Client disconnect có ý nghĩa gì với WebFlux?

Trong ứng dụng WebFlux, controller thường trả về `Mono<T>` hoặc `Flux<T>`. Framework sở hữu subscription dùng để ghi kết quả vào HTTP response. Controller không cần tự gọi `subscribe()`; framework đăng ký Publisher, yêu cầu dữ liệu theo khả năng ghi response và chuyển các phần tử thành nội dung HTTP.

Ví dụ một endpoint phát dữ liệu liên tục:

~~~java
@RestController
class PriceController {
    private final PriceFeed priceFeed;

    PriceController(PriceFeed priceFeed) {
        this.priceFeed = priceFeed;
    }

    @GetMapping(
        value = "/prices/{symbol}/stream",
        produces = MediaType.TEXT_EVENT_STREAM_VALUE
    )
    Flux<ServerSentEvent<PriceTick>> stream(
        @PathVariable String symbol
    ) {
        return priceFeed.stream(symbol)
            .map(tick -> ServerSentEvent.builder(tick)
                .event("price")
                .build());
    }
}
~~~

Khi client giữ kết nối, WebFlux tiêu thụ Flux và ghi các Server-Sent Events vào response. Nếu người dùng đóng tab hoặc client hủy request, transport có thể phát hiện kết nối không còn sử dụng được. Khi việc ghi response không thể tiếp tục, WebFlux hủy subscription của Publisher đang cung cấp dữ liệu.

~~~mermaid
sequenceDiagram
    participant B as Browser / client
    participant W as WebFlux response writer
    participant P as Controller Publisher
    participant U as Upstream service
    B->>W: HTTP request
    W->>P: subscribe
    P->>U: subscribe / request
    U-->>P: onNext
    P-->>W: dữ liệu response
    W-->>B: ghi response
    B-xW: client disconnect
    W-xP: cancel subscription
    P-xU: cancellation truyền upstream
    Note over U: Dừng công việc nếu nguồn hỗ trợ hủy
~~~

Đây là hành vi mong đợi của một chuỗi reactive được gắn với response. Tín hiệu hủy đi ngược từ nơi tiêu thụ về nguồn, để các bước không còn cần thiết có cơ hội dừng.

### Server không phải lúc nào cũng biết ngay thời điểm người dùng đóng tab

Client disconnect là một sự kiện ở tầng mạng. Server thường chỉ phát hiện khi socket báo đóng, khi một lần ghi tiếp theo thất bại hoặc khi transport/proxy thông báo kết nối đã kết thúc. Nếu có reverse proxy, load balancer hoặc buffer response, thời điểm phát hiện có thể trễ so với thao tác của người dùng.

Do đó, không nên dựa vào cancellation như một đồng hồ chính xác. Với công việc có deadline, vẫn cần timeout riêng. Với tác vụ phải hoàn tất dù client rời đi, cần chuyển nó sang một workflow nền có chủ sở hữu và lưu trạng thái bền vững.

## 2. Cancellation khác với complete và error

Reactive Streams định nghĩa cancellation như hành động từ Subscriber gọi `Subscription.cancel()`. Đây không phải một tín hiệu terminal mà Publisher gửi tới Subscriber.

| Tình huống | Tín hiệu hoặc hành vi | Ý nghĩa |
|---|---|---|
| Nguồn hoàn tất bình thường | `onComplete` | Không còn dữ liệu; chuỗi kết thúc bình thường |
| Nguồn thất bại | `onError` | Chuỗi kết thúc do lỗi |
| Client không còn nhận response | `cancel()` | Subscriber yêu cầu dừng việc phát dữ liệu |
| Thao tác vượt thời hạn | `timeout` phát lỗi hoặc fallback | Chính sách thời gian của pipeline được kích hoạt |
| Ghi response thất bại | Lỗi transport/ghi response tùy thời điểm | Framework xử lý lỗi ghi và có thể hủy upstream |

Khi client disconnect, downstream thường không nhận thêm `onComplete` hoặc `onError` như thể response đã được gửi thành công. Thay vào đó, Subscriber hủy subscription. Vì vậy, `doOnError` không phải nơi đáng tin cậy để quan sát mọi lần client rời đi.

Reactor cung cấp `doOnCancel` để quan sát cancellation và `doFinally` để quan sát mọi kiểu kết thúc:

~~~java
Flux<DataChunk> response =
    dataService.streamChunks()
        .doOnCancel(() -> log.info("Response subscription cancelled"))
        .doFinally(signal -> log.info("Response terminated: {}", signal));
~~~

`doOnCancel` chỉ chạy khi subscription bị hủy. `doFinally` chạy khi chuỗi kết thúc bằng complete, error hoặc cancel; tham số `SignalType` cho biết kiểu kết thúc, ví dụ `ON_COMPLETE`, `ON_ERROR` hoặc `CANCEL`.

Không nên gọi một lần client disconnect là lỗi nghiệp vụ. Người dùng có thể chủ động rời màn hình và đây là hành vi bình thường. Hãy ghi nhận cancellation bằng metric hoặc log ở mức phù hợp, đồng thời phân biệt nó với lỗi dịch vụ phụ thuộc.

## 3. Cancellation truyền qua chuỗi Reactor như thế nào?

Khi Subscriber cuối hủy, Reactor truyền yêu cầu hủy qua các toán tử upstream. Mỗi toán tử có trách nhiệm chuyển cancellation tới Publisher nguồn hoặc Publisher con mà nó đang quản lý.

Ví dụ:

~~~java
Mono<OrderView> orderView =
    orderRepository.findById(orderId)
        .flatMap(order ->
            customerClient.findById(order.customerId())
                .map(customer -> new OrderView(order, customer))
        )
        .publishOn(Schedulers.parallel())
        .map(this::enrichForDisplay);
~~~

Nếu client disconnect trong lúc response đang được tạo:

1. WebFlux hủy subscription của `orderView`.
2. `map` và `publishOn` nhận cancellation.
3. `flatMap` hủy Publisher con đang hoạt động nếu còn subscription.
4. `customerClient` và `orderRepository` nhận cancellation nếu adapter hỗ trợ.
5. Cleanup hook của các nguồn được gọi theo hợp đồng của chúng.

Điều này không có nghĩa mọi công việc bên ngoài chắc chắn dừng ngay. Một driver có thể chỉ ngừng chuyển kết quả tới Subscriber, còn câu lệnh đã gửi tới server database vẫn đang thực thi. Một HTTP request có thể đã tới dịch vụ đích trước khi client hủy. Cancellation là yêu cầu dừng, không phải bằng chứng rằng tác dụng phụ chưa xảy ra.

### Cancellation và flatMap

Với `flatMap`, có thể có nhiều Publisher con đang hoạt động đồng thời. Khi subscription ngoài bị hủy, Reactor yêu cầu hủy các inner subscription mà toán tử đang quản lý:

~~~java
Flux<ProductView> views =
    productRepository.findVisible()
        .flatMap(product ->
            inventoryClient.findAvailability(product.id()),
            16
        );
~~~

Nếu client đóng trang trong lúc nhiều truy vấn tồn kho đang chạy, các inner đang hoạt động nhận cancellation. Adapter HTTP reactive có thể hủy request hoặc ngừng tiêu thụ response. Những request đã được dịch vụ từ xa xử lý có thể vẫn hoàn tất ở phía server.

Nếu dùng `concatMap`, chỉ một inner đang được subscribe tại một thời điểm; cancellation được truyền tới inner hiện tại và nguồn upstream. Các phần tử đang chờ trong hàng đợi không được xử lý tiếp.

### Cancellation không tự dừng subscription tách rời

Nếu một bước trong pipeline tự gọi `subscribe()`, nó tạo một subscription độc lập. Subscription đó không tự động thuộc vòng đời response:

~~~java
// Không nên: notification có subscription riêng.
Mono<OrderView> response =
    orderService.load(orderId)
        .doOnNext(order ->
            notificationService.sendViewed(order).subscribe()
        )
        .map(this::toView);
~~~

Client disconnect có thể hủy `response`, nhưng subscription notification đã được tạo riêng vẫn tiếp tục. Lỗi notification cũng không đi theo pipeline response.

Nếu notification là một phần của response workflow, hãy ghép nó:

~~~java
Mono<OrderView> response =
    orderService.load(orderId)
        .flatMap(order ->
            notificationService.sendViewed(order)
                .thenReturn(toView(order))
        );
~~~

Nếu notification phải tiếp tục kể cả khi client rời đi, hãy chuyển nó vào một job nền được quản lý riêng, ghi job vào kho bền vững hoặc outbox, rồi để worker có vòng đời độc lập xử lý. Không dùng nested `subscribe()` như một cơ chế job queue.

## 4. Quan sát cancellation bằng doOnCancel và doFinally

`doOnCancel` phù hợp khi cần biết subscription bị hủy, ví dụ tăng metric hoặc thông báo cho nguồn callback:

~~~java
Flux<PriceTick> ticks =
    priceFeed.stream(symbol)
        .doOnCancel(() ->
            metrics.incrementStreamCancelled(symbol)
        );
~~~

`doFinally` phù hợp khi cần ghi nhận mọi kiểu kết thúc:

~~~java
Mono<Report> report =
    reportService.generate(reportId)
        .doFinally(signal -> {
            switch (signal) {
                case CANCEL -> metrics.incrementReportCancelled();
                case ON_ERROR -> metrics.incrementReportFailed();
                case ON_COMPLETE -> metrics.incrementReportCompleted();
                default -> metrics.incrementOtherTermination();
            }
        });
~~~

Trong ví dụ, `doFinally` không biến cancellation thành lỗi và cũng không thay đổi kết quả Publisher. Nó chỉ quan sát kiểu kết thúc.

Các callback này nên ngắn và không blocking. Tránh gọi database đồng bộ, chờ lock lâu hoặc gửi HTTP blocking bên trong `doOnCancel`/ `doFinally`; việc cleanup chậm có thể làm chậm quá trình hủy và ảnh hưởng thread đang truyền tín hiệu.

Nếu cần cleanup bất đồng bộ hoặc quản lý tài nguyên có vòng đời rõ ràng, dùng `usingWhen` thay vì tự điều phối cleanup bằng side effect trong `doFinally`.

## 5. Giải phóng tài nguyên bằng using và usingWhen

Một pipeline có thể mở cursor, lấy connection, thuê buffer hoặc đăng ký một listener. Tài nguyên phải được giải phóng khi nguồn hoàn tất, lỗi hoặc bị hủy.

Với tài nguyên có cleanup đồng bộ, `using` quản lý vòng đời:

~~~java
Flux<Row> rows =
    Flux.using(
        () -> legacyCursor.open(query),
        cursor -> Flux.fromIterable(cursor.readAll()),
        LegacyCursor::close
    );
~~~

Supplier tạo tài nguyên khi subscribe; function thứ hai tạo Publisher sử dụng tài nguyên; cleanup được gọi khi luồng kết thúc hoặc bị hủy. Ví dụ giả định cursor có thể đọc dữ liệu đồng bộ; nếu `readAll()` blocking, cần cô lập thao tác trên scheduler phù hợp hoặc dùng driver reactive.

Với tài nguyên có cleanup bất đồng bộ, dùng `usingWhen`:

~~~java
Mono<List<Row>> rows =
    Mono.usingWhen(
        connectionPool.acquire(),
        connection -> queryService.findRows(connection, query).collectList(),
        connection -> connection.close(),
        (connection, error) -> connection.close(),
        connection -> connection.close()
    );
~~~

Các tham số cleanup lần lượt xử lý complete, error và cancel. Trong ví dụ, `Connection.close()` trả về `Mono<Void>`, nên việc giải phóng tài nguyên được ghép vào vòng đời reactive.

`usingWhen` đặc biệt hữu ích khi cleanup cần I/O, ví dụ trả connection về pool qua một API bất đồng bộ hoặc đóng một session reactive. Hãy bảo đảm cleanup idempotent nếu thư viện có thể gọi nhiều đường kết thúc trong các tình huống race hoặc adapter tùy chỉnh.

Không nên tự giữ connection trong một field dùng chung rồi đóng nó từ `doFinally` của từng request. Mỗi subscription cần sở hữu đúng tài nguyên của mình hoặc tham gia một cơ chế chia sẻ có quản lý vòng đời riêng.

## 6. Dọn listener trong adapter callback

Khi bọc một API listener thành `Flux`, adapter phải gỡ listener khi subscription bị hủy. Nếu không, client disconnect có thể hủy response nhưng listener vẫn giữ tham chiếu và tiếp tục nhận sự kiện.

~~~java
Flux<SensorEvent> sensorEvents() {
    return Flux.create(sink -> {
        SensorListener listener = sink::next;

        sink.onDispose(() ->
            sensor.removeListener(listener)
        );

        sensor.addListener(listener);
    }, FluxSink.OverflowStrategy.LATEST);
}
~~~

`onDispose` chạy khi sink hoàn tất, lỗi hoặc bị hủy. Nhờ đó, listener được gỡ trong cả ba trường hợp. Nếu chỉ cần hành động riêng cho cancellation, có thể dùng `sink.onCancel`; nếu cần cleanup chung, `onDispose` thường thích hợp hơn.

Trong adapter thực tế, cần xử lý thêm:

- Đăng ký cleanup trước khi nguồn có thể phát callback đồng bộ.
- Nếu `addListener` ném lỗi, chuyển lỗi vào sink và đảm bảo trạng thái đăng ký được dọn.
- Callback đến sau dispose không được tiếp tục tạo tác dụng phụ.
- Nếu nguồn phát từ nhiều thread, dùng API sink phù hợp với mô hình thread của nguồn.
- Chọn overflow strategy theo ý nghĩa dữ liệu và khả năng phát của nguồn.

Với một nguồn trạng thái chỉ cần giá trị mới nhất, `LATEST` có thể phù hợp. Với sự kiện nghiệp vụ không được phép mất, buffer trong bộ nhớ không đủ để bảo đảm giao nhận; cần một cơ chế lưu bền vững và ack phù hợp.

## 7. Client disconnect và các request phụ thuộc

Một request WebFlux có thể gọi nhiều dịch vụ phụ thuộc. Khi client disconnect, cancellation truyền qua pipeline để các request con có cơ hội dừng.

~~~java
Mono<OrderDetail> detail =
    orderClient.find(orderId)
        .flatMap(order ->
            Mono.zip(
                customerClient.find(order.customerId()),
                inventoryClient.find(order.items()),
                shippingClient.quote(order)
            )
            .map(tuple -> new OrderDetail(
                order,
                tuple.getT1(),
                tuple.getT2(),
                tuple.getT3()
            ))
        );
~~~

Các lời gọi WebClient được ghép trong cùng chuỗi. Nếu Subscriber cuối hủy khi các request đang hoạt động, Reactor hủy các subscription con. WebClient/Reactor Netty có thể dừng việc tiêu thụ response và hủy trao đổi đang hoạt động theo khả năng của transport.

Tuy nhiên, không nên giả định dịch vụ đích chưa thực hiện công việc. Server từ xa có thể đã nhận request, ghi dữ liệu hoặc bắt đầu xử lý trước khi cancellation tới. Với thao tác đọc, dừng tiêu thụ thường ít rủi ro nghiệp vụ hơn. Với thao tác ghi, thanh toán hoặc gửi lệnh, cần idempotency key, trạng thái giao dịch và cơ chế đối soát.

### Đừng dùng cancellation thay cho timeout

Client disconnect và timeout là hai điều kiện khác nhau:

- Disconnect là Subscriber không còn muốn nhận kết quả.
- Timeout là pipeline không nhận tín hiệu đúng thời hạn đã cấu hình.

Nếu client vẫn kết nối nhưng dịch vụ phụ thuộc treo, disconnect không xảy ra. Hãy đặt timeout theo ngân sách của request:

~~~java
Mono<OrderDetail> detail =
    orderService.loadDetail(orderId)
        .timeout(Duration.ofSeconds(3));
~~~

Khi timeout, toán tử phát lỗi hoặc chuyển sang fallback theo cấu hình và gửi cancellation upstream. Khi client disconnect, cancellation đến từ Subscriber. Cả hai có thể làm nguồn dừng, nhưng metric và chính sách xử lý khác nhau.

## 8. Tác vụ nào nên dừng và tác vụ nào nên tiếp tục?

Không phải mọi công việc bắt đầu từ HTTP request đều nên bị hủy khi client rời đi. Cần xác định hợp đồng nghiệp vụ.

| Loại công việc | Khi client disconnect | Thiết kế thường phù hợp |
|---|---|---|
| Tìm kiếm, đọc chi tiết, truy vấn dashboard | Dừng nếu không còn consumer | Gắn trực tiếp với response Publisher |
| Stream SSE hoặc WebSocket | Gỡ subscription và tài nguyên của stream | `doOnCancel`, cleanup listener, `usingWhen` |
| Tính toán preview tạm thời | Có thể dừng khi kết quả không còn cần | Cancellation-aware Publisher và giới hạn tài nguyên |
| Tạo báo cáo dài cần tải xuống ngay | Có thể dừng nếu client hủy tải | Gắn với response; có thể hỗ trợ resume nếu cần |
| Đặt hàng hoặc thanh toán đã được chấp nhận | Không nên coi disconnect là rollback | Job/transaction có trạng thái, idempotency và đối soát |
| Gửi email hoặc xử lý nền đã được chấp nhận | Tiếp tục độc lập với HTTP response | Outbox hoặc job queue bền vững |
| Đồng bộ dữ liệu quan trọng | Tiếp tục theo workflow đã được ghi nhận | Worker nền, retry và giám sát riêng |

Ví dụ, nếu endpoint nhận yêu cầu tạo báo cáo rồi trả về file trực tiếp, việc client đóng kết nối có thể khiến quá trình tạo file không còn cần thiết. Nhưng nếu endpoint nhận lệnh thanh toán, hệ thống không nên hủy hoặc đảo ngược thanh toán chỉ vì client mất kết nối sau khi lệnh đã được chấp nhận.

Một mẫu phù hợp cho tác vụ nền là ghi nhận yêu cầu trước khi trả response:

~~~java
Mono<JobAccepted> submitExport(ExportCommand command) {
    return exportJobRepository.create(command)
        .flatMap(job ->
            outboxRepository.append(ExportRequested.from(job))
                .thenReturn(new JobAccepted(job.id(), job.status()))
        );
}
~~~

Sau khi transaction lưu job và outbox commit, worker độc lập xử lý export. Client có thể disconnect rồi truy vấn trạng thái job sau đó. Tác vụ không phụ thuộc vòng đời subscription của response.

## 9. Cancellation không phải rollback

Một điểm dễ nhầm là nghĩ rằng hủy subscription sẽ hoàn tác mọi thứ đã xảy ra. Thực tế, cancellation chỉ yêu cầu ngừng phát hoặc ngừng công việc có thể dừng. Nó không thể đảo ngược một hành động đã được hệ thống ngoài xác nhận.

Ví dụ:

1. Server gửi lệnh giữ hàng tới dịch vụ kho.
2. Dịch vụ kho xử lý và giữ hàng thành công.
3. Client đóng kết nối trước khi nhận response.
4. WebFlux hủy subscription.
5. Ứng dụng không biết chắc client đã nhận kết quả hay chưa, trong khi kho đã thay đổi trạng thái.

Nếu hệ thống tự động giải phóng hàng chỉ vì response bị hủy, có thể gây ra trạng thái sai khi đơn hàng thực tế đã được tạo. Ngược lại, nếu không đối soát, trạng thái đơn hàng có thể không khớp với kho.

Với thao tác có tác dụng phụ, cần:

- ID lệnh ổn định hoặc idempotency key.
- Trạng thái workflow được lưu bền vững.
- Truy vấn kết quả khi client không nhận được phản hồi.
- Hành động bù trừ theo nghiệp vụ nếu cần.
- Retry có giới hạn và không tạo lệnh trùng.

Trong một reactive transaction, cancellation trước commit có thể kích hoạt rollback/cleanup theo transaction manager và driver. Nhưng cần kiểm tra hợp đồng của resource và transaction manager đang dùng. Không suy ra rằng mọi thao tác HTTP, message hoặc database đã gửi đều được rollback.

## 10. Tránh giữ tài nguyên sau khi response đã bị hủy

Những lỗi phổ biến khiến công việc tiếp tục sau client disconnect:

- Gọi `subscribe()` bên trong service hoặc callback.
- Tạo thread thủ công rồi không lưu handle để hủy.
- Đăng ký listener nhưng không gỡ khi dispose.
- Dùng scheduler tùy chỉnh nhưng không quản lý vòng đời.
- Bắt cancellation rồi bỏ qua cleanup.
- Tách một Publisher thành subscription nền không có hàng đợi hoặc chủ sở hữu.

Nếu buộc phải tạo tác vụ độc lập, hãy tạo một thành phần quản lý job với ID, trạng thái, cancellation policy, retry và persistence. Đừng dựa vào thread sống sót sau request như một cơ chế xử lý nền đáng tin cậy.

Với một tác vụ có thể hủy, giữ handle nếu API không thể biểu diễn bằng Publisher:

~~~java
Mono<Result> runLegacyTask() {
    return Mono.create(sink -> {
        Future<Result> future = executor.submit(legacyCallable);

        sink.onCancel(() -> future.cancel(true));

        executor.execute(() -> {
            try {
                if (!future.isCancelled()) {
                    sink.success(future.get());
                }
            } catch (CancellationException ignored) {
                // Subscriber đã hủy; không phát kết quả nữa.
            } catch (ExecutionException error) {
                sink.error(error.getCause());
            } catch (InterruptedException error) {
                Thread.currentThread().interrupt();
                sink.error(error);
            }
        });
    });
}
~~~

Đây là ví dụ minh họa việc nối cancellation với `Future.cancel(true)`; trong mã sản xuất cần tránh chờ `future.get()` trên cùng executor có thể bị bão hòa, và phải xử lý race giữa callback, cancel và completion. Ưu tiên API reactive hoặc adapter được thư viện cung cấp nếu có.

## 11. Quan sát và ghi nhận client disconnect

Metric và log nên giúp trả lời:

- Bao nhiêu response stream bị hủy?
- Request bị hủy ở bước nào?
- Có bao nhiêu request phụ thuộc đã được gửi trước khi cancellation?
- Cleanup listener/connection có hoàn tất không?
- Có callback hoặc lỗi đến muộn sau dispose không?
- Thời gian từ lúc bắt đầu request tới lúc cancellation là bao lâu?

Có thể đặt metric tại ranh giới response:

~~~java
Flux<ServerSentEvent<PriceTick>> stream(String symbol) {
    return priceFeed.stream(symbol)
        .map(tick -> ServerSentEvent.builder(tick).build())
        .doOnCancel(() ->
            metrics.incrementClientStreamCancelled(symbol)
        )
        .doFinally(signal ->
            metrics.recordStreamTermination(symbol, signal.name())
        );
}
~~~

Tránh gắn tag theo user ID, request ID hoặc giá trị symbol có cardinality không giới hạn nếu metric backend không hỗ trợ. Có thể ghi correlation ID trong log đã lọc hoặc trace thay vì metric label.

Không nên ghi mọi disconnect ở mức error. Client đóng tab hoặc mobile app chuyển mạng là hành vi thường gặp. Dùng mức debug/info và metric tổng hợp; chỉ nâng mức cảnh báo khi tỷ lệ cancellation bất thường hoặc cleanup thất bại.

Nếu hook cleanup phát lỗi sau cancellation, đó có thể trở thành dropped error vì không còn Subscriber để nhận. Cần quan sát riêng bằng hook toàn cục phù hợp và xử lý nguyên nhân ở adapter. Không dùng dropped-error hook để thay thế cleanup hoặc để coi cancellation là lỗi.

## 12. Kiểm thử cancellation trong Reactor

`StepVerifier` có thể kiểm tra Publisher nhận cancellation và chạy cleanup. Ví dụ với một luồng interval:

~~~java
AtomicBoolean cancelled = new AtomicBoolean();

StepVerifier.withVirtualTime(() ->
        Flux.interval(Duration.ofSeconds(1))
            .doOnCancel(() -> cancelled.set(true))
    )
    .expectSubscription()
    .thenAwait(Duration.ofSeconds(2))
    .expectNext(0L, 1L)
    .thenCancel()
    .verify();

assertThat(cancelled).isTrue();
~~~

Test tiến thời gian ảo để nhận hai phần tử, sau đó hủy subscription và xác minh callback cancellation đã chạy. Cách này không cần chờ hai giây thật.

Có thể kiểm tra cancellation của Publisher con:

~~~java
AtomicBoolean innerCancelled = new AtomicBoolean();

Flux<Integer> work =
    Flux.range(1, 10)
        .concatMap(value ->
            Mono.<Integer>never()
                .doOnCancel(() -> innerCancelled.set(true))
        );

StepVerifier.create(work)
    .thenCancel()
    .verify();

assertThat(innerCancelled).isTrue();
~~~

Với `concatMap`, inner đầu tiên đang hoạt động khi Subscriber hủy; test xác minh cancellation được truyền tới inner đó.

### Kiểm thử resource cleanup

Nếu dùng `usingWhen`, hãy tạo fake resource ghi nhận cleanup khi complete, error và cancel. Mỗi đường kết thúc cần được xác minh riêng vì cleanup callback khác nhau. Nếu cleanup bất đồng bộ, test phải chờ Publisher cleanup hoàn tất theo hợp đồng `usingWhen`.

### Kiểm thử tích hợp WebFlux

`StepVerifier` kiểm tra cancellation ở cấp Publisher. Để xác nhận client disconnect thực sự truyền tới response writer, cần một kiểm thử tích hợp có server WebFlux và client có thể hủy request/đóng kết nối:

1. Tạo endpoint streaming phát dữ liệu theo thời gian.
2. Gửi request bằng client kiểm thử và nhận một vài phần tử.
3. Hủy subscription hoặc đóng response body phía client.
4. Xác minh server-side cleanup hook được gọi.
5. Xác minh listener, connection hoặc Publisher con không còn hoạt động.
6. Lặp lại với complete bình thường và lỗi để bảo đảm cleanup đúng ở mọi đường kết thúc.

Hành vi phát hiện disconnect có thể phụ thuộc transport và proxy; test tích hợp nên chạy trên stack thực tế mà ứng dụng sử dụng, không chỉ dựa vào test Publisher thuần.

## 13. Những nhầm lẫn thường gặp

- **Client đóng tab luôn làm server biết ngay:** server chỉ phát hiện khi transport hoặc lần ghi response tiếp theo báo kết nối đã đóng; proxy có thể làm chậm việc phát hiện.
- **Cancellation là onError:** cancellation là hành động từ Subscriber, không phải terminal error được phát tới downstream.
- **doOnError quan sát được mọi disconnect:** cancellation không nhất thiết đi qua `onError`; dùng `doOnCancel` hoặc `doFinally`.
- **doFinally chỉ chạy khi complete:** nó chạy khi complete, error hoặc cancel; kiểm tra `SignalType` để phân biệt.
- **Hủy response tự hủy mọi công việc nền:** nested `subscribe()`, thread riêng hoặc job queue có vòng đời độc lập sẽ tiếp tục.
- **Cancellation chắc chắn dừng server từ xa:** hệ thống đích có thể đã nhận và thực hiện request; cancellation không rollback tác dụng phụ đã commit.
- **doOnCancel thay thế cleanup mọi trường hợp:** nó chỉ chạy khi cancel; cleanup cần cho cả complete/error nên dùng `doFinally`, `using` hoặc `usingWhen` đúng mục đích.
- **usingWhen chỉ cần một callback cleanup:** cần xác định cleanup cho complete, error và cancel.
- **Timeout và disconnect giống nhau:** timeout là chính sách thời gian của pipeline; disconnect là Subscriber không còn nhận response.
- **Có thể bỏ qua lỗi cleanup sau cancel:** lỗi đến muộn có thể thành dropped error; cần ghi nhận và sửa vòng đời nguồn.
- **Dùng thread nền để giữ tác vụ sau request là đủ:** tác vụ quan trọng cần job state, persistence, retry và chủ sở hữu rõ ràng.

## 14. Bài tập vận dụng

Một endpoint WebFlux phát tiến độ tạo báo cáo bằng Server-Sent Events. Việc tạo báo cáo gồm đọc dữ liệu, gọi một dịch vụ tính toán và phát từng mốc tiến độ. Người dùng có thể đóng tab bất cứ lúc nào.

Hãy thiết kế vòng đời:

1. Controller nên trả về `Flux<ServerSentEvent<Progress>>` hay tự subscribe để đẩy dữ liệu? Vì sao?
2. Khi client disconnect, cancellation cần truyền tới những Publisher nào?
3. Nếu dịch vụ tính toán hỗ trợ cancellation, adapter nên nối tín hiệu hủy bằng cách nào?
4. Nếu quá trình tạo báo cáo phải tiếp tục kể cả khi người dùng đóng tab, nên chuyển nó sang mô hình nào?
5. Dùng `doOnCancel` và `doFinally` để phân biệt cancellation với complete/error ra sao?
6. Nếu báo cáo đang giữ connection hoặc file handle, nên dùng `usingWhen` hay cleanup thủ công?
7. Nếu một request phụ thuộc đã được gửi và server từ xa có thể đã xử lý, làm sao đối soát thay vì giả định rollback?
8. Hãy đề xuất test `StepVerifier` và test tích hợp xác minh cleanup sau client disconnect.

**Gợi ý:** controller trả Publisher để WebFlux quản lý subscription. Nếu báo cáo chỉ phục vụ response hiện tại, cancellation nên dừng nguồn và giải phóng tài nguyên. Nếu báo cáo là công việc cần hoàn tất, tạo job có ID và trạng thái bền vững; endpoint chỉ gửi yêu cầu và trả ID, còn worker xử lý độc lập. Dùng `usingWhen` cho resource có cleanup bất đồng bộ và kiểm thử cả cancel lẫn complete/error.

## Kết luận

Khi client disconnect, WebFlux có thể hủy subscription đang tạo HTTP response; Reactor truyền cancellation ngược qua các toán tử và Publisher con để nguồn có cơ hội dừng công việc. Dùng `doOnCancel` để quan sát cancellation, `doFinally` để phân biệt mọi kiểu kết thúc và `usingWhen` để quản lý cleanup bất đồng bộ. Giữ tác vụ trong cùng Publisher khi nó thuộc vòng đời response; chuyển công việc cần tiếp tục sang job hoặc outbox có chủ sở hữu riêng. Cancellation không phải lỗi và không phải rollback, nên các thao tác có tác dụng phụ cần idempotency, trạng thái bền vững và đối soát. Kiểm thử cả Publisher lẫn HTTP transport giúp xác nhận client disconnect thực sự giải phóng tài nguyên trong ứng dụng WebFlux.
