# Tạo nguồn

## Tạo nguồn từ hàm gọi lại và bộ lắng nghe sự kiện

Trong mô-đun **REACTIVE_PROGRAMMING**, ta học cách tổ chức ứng dụng quanh các luồng sự kiện bất đồng bộ, hợp đồng Publisher–Subscriber và cơ chế backpressure của Reactive Streams. Reactor cung cấp `Mono` và `Flux` để mô tả các nguồn dữ liệu, kết hợp toán tử, điều khiển scheduler, xử lý lỗi và kiểm thử pipeline. Trong thực tế, nhiều thư viện Java không trả về Publisher; chúng cung cấp API theo kiểu callback hoặc đăng ký bộ lắng nghe sự kiện. Ta cần một lớp chuyển đổi để đưa các API đó vào pipeline reactive.

Reactor cung cấp `Mono.create` và `Flux.create` để tạo Publisher từ callback, cùng `Flux.push` cho nguồn phát từ một thread. Khi chuyển một API sự kiện thành Publisher, ta phải quản lý vòng đời listener, chuyển tín hiệu lỗi và hoàn tất, xử lý cancellation, đồng thời chọn chính sách khi nguồn phát nhanh hơn Subscriber. Nếu bỏ qua các chi tiết này, adapter có thể gây rò rỉ listener, mất sự kiện hoặc tăng bộ nhớ không giới hạn.

### Mục tiêu học tập

Sau bài này, bạn có thể:

- Chuyển API callback một kết quả thành `Mono` và API sự kiện nhiều phần tử thành `Flux`.
- Phân biệt `Mono.create`, `Flux.create`, `Flux.push` và `Flux.generate`.
- Đăng ký và gỡ bộ lắng nghe theo vòng đời của subscription.
- Chuyển callback thành `onNext`, `onError` và `onComplete` đúng quy tắc.
- Chọn chính sách overflow phù hợp với khả năng điều tiết của nguồn và ý nghĩa dữ liệu.
- Dùng demand, cancellation và scheduler đúng cách khi bọc API callback.
- Kiểm thử adapter bằng Reactor Test và một nguồn sự kiện giả lập.

## 1. Vì sao cần adapter cho API callback?

Nhiều API Java truyền thống dùng callback để báo kết quả:

~~~java
legacyClient.fetchCustomer(
    customerId,
    customer -> handleCustomer(customer),
    error -> handleError(error)
);
~~~

Một API khác đăng ký listener để nhận nhiều sự kiện:

~~~java
eventBus.addListener(event -> handleEvent(event));
~~~

Các API này có thể hoạt động bất đồng bộ, nhưng chúng không trực tiếp tham gia hợp đồng Reactive Streams. Ta không thể ghép chúng với `map`, `flatMap`, `timeout`, `retry` hoặc `StepVerifier` một cách tự nhiên nếu chưa chuyển đổi thành Publisher.

Adapter reactive tạo ranh giới giữa hai mô hình:

~~~mermaid
flowchart LR
    A[API callback hoặc listener] --> B[Adapter Reactor]
    B --> C[Mono hoặc Flux]
    C --> D[Toán tử xử lý]
    D --> E[Subscriber]
    E -. demand / cancel .-> C
~~~

Adapter chịu trách nhiệm chuyển callback của thư viện thành tín hiệu Reactive Streams. Sau khi chuyển đổi, các bước nghiệp vụ có thể được ghép trong cùng pipeline và được điều khiển qua subscription.

Điều quan trọng là adapter không tự biến một nguồn không hỗ trợ backpressure thành nguồn có thể điều tiết. Nếu thư viện ngoài cứ phát sự kiện bất kể Subscriber có nhu cầu hay không, adapter phải chọn cách buffer, bỏ phần tử, giữ phần tử mới nhất hoặc báo lỗi khi quá tải.

## 2. Chọn API tạo nguồn phù hợp

Reactor có một số API tạo Publisher từ hàm gọi lại:

| API | Dạng nguồn | Cách hoạt động | Trường hợp phù hợp |
|---|---|---|---|
| `Mono.create` | 0 hoặc 1 kết quả | Callback hoàn tất bằng giá trị hoặc lỗi | API bất đồng bộ trả về một kết quả |
| `Flux.create` | 0 đến nhiều phần tử | Callback có thể phát nhiều tín hiệu, kể cả từ nhiều thread | API listener hoặc callback phát nhiều sự kiện |
| `Flux.push` | 0 đến nhiều phần tử | Callback phát từ một thread đơn | Nguồn callback đảm bảo chỉ có một thread phát |
| `Flux.generate` | 0 đến nhiều phần tử | Hàm đồng bộ tạo từng tín hiệu theo yêu cầu | Sinh phần tử tuần tự, có state, không dựa vào callback bất đồng bộ |

### Mono.create cho callback một kết quả

Giả sử thư viện cũ cung cấp một API lấy hồ sơ khách hàng:

~~~java
interface Cancellable {
    void cancel();
}

interface LegacyCustomerClient {
    Cancellable fetch(
        String id,
        Consumer<Customer> onSuccess,
        Consumer<Throwable> onFailure
    );
}
~~~

Có thể chuyển thành `Mono<Customer>`:

~~~java
Mono<Customer> findCustomer(String id) {
    return Mono.create(sink ->
        legacyClient.fetch(
            id,
            sink::success,
            sink::error
        )
    );
}
~~~

`Mono.create` cung cấp một `MonoSink`. Callback thành công gọi `success(value)`; callback lỗi gọi `error(error)`. Nếu API hoàn tất mà không có giá trị, có thể gọi `success()` để phát Mono rỗng.

Với API có khả năng trả về nhiều callback thành công do retry nội bộ hoặc lỗi lập trình, cần bảo đảm chỉ một kết quả được chấp nhận. `Mono` chỉ phát tối đa một phần tử và một tín hiệu kết thúc. Không nên giả định một thư viện callback luôn tuân thủ điều đó nếu hợp đồng của nó không nói rõ.

Nếu API trả về handle để hủy request, hãy nối handle đó với cancellation:

~~~java
Mono<Customer> findCustomer(String id) {
    return Mono.create(sink -> {
        Cancellable request = legacyClient.fetch(
            id,
            sink::success,
            sink::error
        );

        sink.onCancel(request::cancel);
    });
}
~~~

Ví dụ giả định `fetch` trả về một đối tượng `Cancellable` có phương thức `cancel()`. Khi Subscriber hủy trước khi callback hoàn tất, Reactor gọi hàm hủy đã đăng ký. Nếu thư viện không hỗ trợ hủy, adapter không thể tự dừng công việc ở phía thư viện; nó chỉ có thể ngừng chuyển kết quả tới Subscriber.

### Flux.create cho listener nhiều sự kiện

Với API phát nhiều sự kiện, ta cần `Flux.create`:

~~~java
Flux<OrderEvent> orderEvents() {
    return Flux.create(sink -> {
        EventListener listener = sink::next;

        sink.onDispose(() ->
            eventSource.removeListener(listener)
        );

        eventSource.addListener(listener);
    });
}
~~~

Ví dụ minh họa ý tưởng: khi có subscription, adapter đăng ký listener; mỗi callback gọi `sink.next(event)`; khi subscription kết thúc hoặc bị hủy, listener được gỡ khỏi nguồn.

Trong mã sản xuất, nên giữ đúng cùng một đối tượng listener để gỡ đăng ký và đăng ký cleanup trước khi nguồn có thể phát callback đồng bộ. Ví dụ đầy đủ hơn:

~~~java
Flux<OrderEvent> orderEvents() {
    return Flux.create(sink -> {
        AtomicBoolean active = new AtomicBoolean(true);

        EventListener listener = event -> {
            if (active.get()) {
                sink.next(event);
            }
        };

        sink.onDispose(() -> {
            active.set(false);
            eventSource.removeListener(listener);
        });

        try {
            eventSource.addListener(listener);
        } catch (RuntimeException error) {
            sink.error(error);
        }
    }, FluxSink.OverflowStrategy.LATEST);
}
~~~

Ở đây:

- Listener chỉ phát khi adapter còn hoạt động.
- `onDispose` được gọi khi luồng hoàn tất, lỗi hoặc bị hủy; callback đặt cờ dừng và gỡ listener.
- Nếu việc đăng ký listener ném exception, adapter chuyển lỗi thành `onError`.
- `LATEST` giữ giá trị mới nhất khi downstream không theo kịp; các giá trị trung gian có thể bị bỏ qua.

Đây là lựa chọn phù hợp cho trạng thái cập nhật liên tục mà chỉ giá trị mới nhất có ý nghĩa, chẳng hạn vị trí hiện tại của con trỏ hoặc nhiệt độ hiển thị trên dashboard. Không dùng chính sách này cho giao dịch, lệnh hoặc sự kiện kiểm toán cần xử lý đầy đủ.

## 3. Quản lý vòng đời listener

Một adapter listener phải xử lý cả thời điểm đăng ký lẫn thời điểm gỡ đăng ký. Nếu mỗi subscription đăng ký một listener nhưng không gỡ listener khi subscription kết thúc, listener cũ tiếp tục nhận sự kiện, giữ tham chiếu đến đối tượng không còn dùng và có thể gây rò rỉ bộ nhớ.

Có hai callback vòng đời thường cần phân biệt:

- `sink.onCancel(...)` chạy khi Subscriber hủy subscription.
- `sink.onDispose(...)` chạy khi subscription kết thúc do complete, error hoặc cancel.

Nếu cần dọn tài nguyên trong mọi trường hợp, `onDispose` thường là điểm thích hợp. Nếu hành động chỉ có ý nghĩa khi Subscriber chủ động hủy, dùng `onCancel`. Có thể đăng ký cả hai, nhưng tránh thực hiện cleanup hai lần nếu thao tác không idempotent.

~~~java
Flux<SensorEvent> sensorEvents() {
    return Flux.create(sink -> {
        SensorListener listener = sink::next;

        sink.onCancel(() -> {
            metrics.incrementCancelledSubscriptions();
            sensor.removeListener(listener);
        });

        sink.onDispose(() -> {
            metrics.incrementDisposedSubscriptions();
        });

        sensor.addListener(listener);
    });
}
~~~

Ví dụ này dùng callback hủy để gỡ listener và callback dispose để ghi nhận kết thúc. Trong thực tế, cần cân nhắc cả complete và error: nếu nguồn có thể tự hoàn tất hoặc báo lỗi, listener cũng phải được gỡ trong các trường hợp đó. Một cleanup chung trong `onDispose` thường dễ bảo đảm hơn:

~~~java
sink.onDispose(() -> sensor.removeListener(listener));
~~~

Nếu `removeListener` có thể được gọi nhiều lần, hãy thiết kế nó idempotent hoặc bảo vệ bằng cờ trạng thái. Cũng cần xử lý trường hợp đăng ký listener thất bại một phần, ví dụ nguồn đã lưu listener rồi mới ném lỗi.

### Một subscription tương ứng với một listener hay dùng chung listener?

Đoạn `Flux.create` trên được gọi cho mỗi subscription. Vì vậy, nếu ba Subscriber đăng ký, adapter có thể tạo ba listener riêng trên nguồn. Đây là hành vi hợp lý nếu mỗi Subscriber cần một đăng ký độc lập.

Nếu việc mở kết nối cảm biến tốn kém và nhiều Subscriber cần cùng một nguồn vật lý, hãy cân nhắc chia sẻ Publisher ở tầng phù hợp bằng `share()` hoặc quản lý một listener dùng chung. Khi chia sẻ, phải xác định ai sở hữu kết nối và khi nào kết nối được đóng. Đừng dùng một listener toàn cục mà không có chính sách vòng đời rõ ràng.

## 4. Chọn chính sách overflow và backpressure

Reactive Streams dùng demand để Subscriber thông báo số phần tử sẵn sàng nhận. Một nguồn callback bên ngoài có thể không biết demand này và vẫn gọi listener liên tục. `Flux.create` cung cấp các chính sách overflow:

| Chính sách | Hành vi khi downstream chưa có đủ demand | Phù hợp khi |
|---|---|---|
| `BUFFER` | Lưu phần tử chờ tiêu thụ | Có thể chấp nhận buffer tăng và có giới hạn tài nguyên ở nơi khác |
| `DROP` | Bỏ phần tử mới không thể chuyển ngay | Phần tử có thể mất mà không ảnh hưởng nghiệp vụ |
| `LATEST` | Giữ phần tử mới nhất, thay phần tử chờ cũ | Chỉ cần trạng thái mới nhất |
| `ERROR` | Báo lỗi khi không thể phát theo demand | Quá tải cần được thể hiện rõ để tầng gọi xử lý |
| `IGNORE` | Bỏ qua demand của downstream | Chỉ dùng khi nguồn và consumer được kiểm soát để không bị quá tải |

Mặc định của `Flux.create` là `BUFFER`. Buffer mặc định có thể tăng không giới hạn nếu nguồn liên tục phát nhanh hơn tốc độ tiêu thụ. Điều này trì hoãn quá tải chứ không giải quyết nó; bộ nhớ có thể tăng cho tới khi ứng dụng gặp GC pressure hoặc hết heap.

Hãy chọn chính sách theo ý nghĩa dữ liệu:

- Dashboard trạng thái hiện tại thường có thể dùng `LATEST`.
- Bộ đếm hoặc telemetry có thể dùng `DROP` nếu mất mẫu được chấp nhận và có metric đo số mẫu bị bỏ.
- Một sự kiện quan trọng không được phép mất cần được ghi vào hàng đợi bền vững hoặc cơ chế lưu trữ có thể đọc lại; buffer trong bộ nhớ không đủ để bảo đảm giao nhận.
- `ERROR` phù hợp khi quá tải cần làm workflow thất bại rõ ràng thay vì âm thầm mất dữ liệu.
- `IGNORE` có thể khiến downstream nhận nhiều tín hiệu hơn khả năng xử lý; chỉ dùng khi đã chứng minh được nguồn bị giới hạn hoặc consumer có khả năng chịu tải.

### Khi nguồn có thể nhận demand

Một số API callback có thể điều tiết nguồn, ví dụ message client hỗ trợ request thêm số message. Khi đó, adapter có thể chuyển demand từ Subscriber sang nguồn bằng `onRequest`:

~~~java
Flux<Message> messages = Flux.create(sink -> {
    MessageListener listener = sink::next;

    sink.onDispose(() -> client.removeListener(listener));
    sink.onRequest(client::request);

    client.addListener(listener);
}, FluxSink.OverflowStrategy.ERROR);
~~~

Ví dụ giả định `client.request(long n)` yêu cầu nguồn gửi thêm tối đa `n` message. Khi nguồn thực sự hỗ trợ demand, việc chuyển tiếp yêu cầu giúp hạn chế buffer và phối hợp tốc độ giữa hai phía.

Nếu API không hỗ trợ điều tiết, `onRequest` không thể buộc nguồn dừng phát. Adapter vẫn phải áp dụng buffer, drop, latest hoặc error. Không nên gọi một API không có cơ chế demand là "backpressure-aware" chỉ vì Publisher đầu ra triển khai Reactive Streams.

### Buffer có giới hạn

`FluxSink.OverflowStrategy.BUFFER` là chính sách buffer của sink và không nhận tham số kích thước. Nếu cần giới hạn bộ đệm, hãy thiết kế rõ một hàng đợi hữu hạn trong adapter hoặc dùng một cơ chế trung gian có giới hạn và xử lý trường hợp đầy. Khi hàng đợi đầy, chính sách phải là một quyết định nghiệp vụ: từ chối, báo lỗi, drop theo quy tắc hoặc ghi vào lưu trữ bền vững.

## 5. Flux.create và Flux.push khác nhau thế nào?

`Flux.create` phù hợp khi callback có thể được gọi từ nhiều thread. Reactor điều phối các tín hiệu đồng thời từ nhiều thread để downstream nhận chuỗi tín hiệu được tuần tự hóa theo hợp đồng.

`Flux.push` dành cho nguồn phát từ một thread đơn. Nó có thể giảm chi phí điều phối khi API bảo đảm chỉ một thread gọi callback. Nếu callback có thể đồng thời chạy trên nhiều thread, không dùng `push`; chọn `create` hoặc đồng bộ hóa nguồn trước khi phát.

~~~java
Flux<Reading> readingsFromSingleThread() {
    return Flux.push(sink -> {
        SensorCallback callback = reading -> sink.next(reading);

        sink.onDispose(() -> sensor.removeCallback(callback));
        sensor.addCallback(callback);
    }, FluxSink.OverflowStrategy.LATEST);
}
~~~

Ví dụ chỉ hợp lệ nếu `sensor` bảo đảm callback luôn được gọi trên một thread phát duy nhất. Nếu thư viện không cam kết điều đó, hãy dùng `Flux.create`.

`Flux.generate` có mục đích khác: tạo tín hiệu đồng bộ, từng phần tử một, dựa trên state. Nó không phải công cụ bọc listener bất đồng bộ:

~~~java
Flux<Integer> sequence =
    Flux.generate(
        () -> 0,
        (state, sink) -> {
            if (state < 3) {
                sink.next(state);
                return state + 1;
            }

            sink.complete();
            return state;
        }
    );
~~~

Mỗi lần generator được gọi, nó phát tối đa một phần tử hoặc một tín hiệu kết thúc và trả về state tiếp theo. Dùng `generate` cho thuật toán sinh tuần tự, không dùng để đăng ký callback từ thư viện ngoài.

## 6. Đưa callback vào pipeline nghiệp vụ

Sau khi chuyển API listener thành `Flux`, ta có thể dùng toán tử Reactor để xử lý sự kiện:

~~~java
Flux<OrderEvent> processedEvents =
    orderEvents()
        .filter(OrderEvent::isRelevant)
        .flatMap(event ->
            orderService.process(event),
            8
        )
        .doOnError(error ->
            log.error("Event processing failed", error)
        );
~~~

`filter` bỏ các sự kiện không liên quan. `flatMap` ghép Publisher xử lý của từng sự kiện và giới hạn tối đa tám tác vụ con đồng thời. Lỗi đi vào pipeline kết quả để có thể được xử lý bằng `onErrorResume`, retry có giới hạn hoặc một chính sách khác.

Nếu cần xử lý tuần tự, dùng `concatMap`:

~~~java
Flux<ProcessedEvent> processedSequentially =
    orderEvents()
        .concatMap(orderService::process);
~~~

Điều này hữu ích khi thứ tự sự kiện có ý nghĩa, nhưng một callback nguồn quá nhanh có thể khiến hàng đợi tăng. Cần chọn overflow strategy hoặc cơ chế demand phù hợp ngay ở adapter.

Nếu callback phát lỗi, adapter gọi `sink.error(error)`. Sau tín hiệu lỗi, luồng kết thúc; các callback đến sau không được xem như một luồng mới. Nếu nguồn có thể tự kết thúc, gọi `sink.complete()` và gỡ listener qua cleanup hook. Không phát thêm tín hiệu sau terminal signal.

## 7. Threading và scheduler

Callback của thư viện ngoài thường được gọi trên thread do thư viện đó quản lý: event loop, thread I/O hoặc thread phát sự kiện. `Flux.create` không tự động chuyển callback sang `Schedulers.parallel()` hay `Schedulers.boundedElastic()`.

Nếu cần chuyển các bước downstream sang scheduler khác, dùng `publishOn`:

~~~java
Flux<ProcessedEvent> processed =
    orderEvents()
        .publishOn(Schedulers.parallel())
        .map(this::cpuBoundTransform);
~~~

Các toán tử downstream sau `publishOn` được thực thi trên scheduler đã chọn. Nếu cần chuyển việc subscribe hoặc thiết lập nguồn sang scheduler khác, có thể dùng `subscribeOn`, nhưng callback sau đó vẫn có thể được gọi trên thread mà thư viện ngoài chọn.

Nếu callback thực hiện công việc blocking, không nên chặn event loop hoặc thread phát sự kiện. Có thể chuyển đoạn blocking sang `boundedElastic`:

~~~java
Flux<Result> results =
    orderEvents()
        .flatMap(event ->
            Mono.fromCallable(() -> legacyBlockingService.process(event))
                .subscribeOn(Schedulers.boundedElastic()),
            16
        );
~~~

Trong ví dụ, mỗi tác vụ blocking được bọc thành Mono và chạy trên bounded elastic scheduler, còn concurrency được giới hạn ở 16. Chuyển scheduler không thay thế việc giới hạn tải hoặc timeout.

## 8. Xử lý cancellation và tài nguyên

Khi Subscriber cuối hủy subscription, adapter cần ngừng nhận callback nếu thư viện hỗ trợ gỡ listener hoặc hủy request. Nếu không làm vậy, nguồn có thể tiếp tục phát vào sink đã bị hủy và giữ tài nguyên không cần thiết.

Ví dụ adapter nên gỡ listener khi dispose:

~~~java
Flux<ConnectionEvent> connectionEvents() {
    return Flux.create(sink -> {
        ConnectionListener listener = sink::next;

        sink.onDispose(() ->
            connection.removeListener(listener)
        );

        connection.addListener(listener);
    }, FluxSink.OverflowStrategy.ERROR);
}
~~~

Nếu listener được đăng ký thành công, dispose sẽ gỡ nó khi subscription hoàn tất, lỗi hoặc bị hủy. Với nguồn có thể tự hoàn tất, hãy gọi `sink.complete()` khi biết không còn sự kiện nào; cleanup hook vẫn được chạy.

Cancellation không phải rollback. Nếu callback đã kích hoạt một lệnh ghi hoặc giao dịch ở hệ thống từ xa, hủy subscription không bảo đảm tác dụng phụ đó được hoàn tác. Với thao tác nghiệp vụ, cần idempotency, timeout và trạng thái xử lý rõ ràng.

Cũng cần xác định ai sở hữu listener khi Publisher được chia sẻ. Với Publisher cold, mỗi subscription thường tạo listener riêng. Nếu dùng `share()`, nhiều Subscriber có thể cùng dùng một listener upstream; listener thường được gỡ khi subscription upstream được dispose theo chính sách chia sẻ. Kiểm thử để xác nhận số lần đăng ký và gỡ listener.

## 9. Kiểm thử adapter callback

Adapter cần kiểm thử ít nhất bốn hành vi: đăng ký listener, chuyển sự kiện, chuyển lỗi và gỡ listener khi cancellation hoặc kết thúc.

Giả sử có một nguồn sự kiện đơn giản:

~~~java
interface EventSource {
    void addListener(Consumer<String> listener);
    void removeListener(Consumer<String> listener);
}
~~~

Một kiểm thử có thể dùng nguồn giả:

~~~java
AtomicReference<Consumer<String>> registered =
    new AtomicReference<>();

EventSource fakeSource = new EventSource() {
    @Override
    public void addListener(Consumer<String> listener) {
        registered.set(listener);
    }

    @Override
    public void removeListener(Consumer<String> listener) {
        registered.compareAndSet(listener, null);
    }
};

Flux<String> events = Flux.create(sink -> {
    Consumer<String> listener = sink::next;
    sink.onDispose(() -> fakeSource.removeListener(listener));
    fakeSource.addListener(listener);
});

StepVerifier.create(events)
    .then(() -> registered.get().accept("created"))
    .expectNext("created")
    .thenCancel()
    .verify();

assertThat(registered.get()).isNull();
~~~

Kiểm thử này xác nhận listener được đăng ký, sự kiện được chuyển thành `onNext`, và listener được gỡ khi Subscriber hủy. Trong mã kiểm thử đầy đủ, cần thêm kiểm thử khi nguồn ném lỗi lúc đăng ký, khi callback báo lỗi, khi nguồn hoàn tất và khi nhiều Subscriber cùng tham gia.

Một số trường hợp nên kiểm thử riêng:

- Callback phát sự kiện đồng bộ ngay trong `addListener`; cleanup hook phải được đăng ký trước khi callback có thể chạy.
- Callback được gọi từ nhiều thread; adapter dùng `Flux.create` nếu nguồn không bảo đảm một thread.
- Subscriber hủy; listener phải được gỡ và callback đến muộn không được tạo tác dụng phụ.
- Nguồn phát nhanh hơn demand; chính sách overflow phải tạo đúng hành vi buffer/drop/latest/error.
- Hai subscription độc lập; số lần đăng ký listener có đúng với thiết kế không?
- Publisher được chia sẻ; listener upstream có được mở một lần và đóng đúng lúc không?

## 10. Những nhầm lẫn thường gặp

- **`Flux.create` tự động làm nguồn có backpressure:** nó cung cấp chính sách overflow; nguồn callback không hỗ trợ demand vẫn có thể phát nhanh hơn consumer.
- **Buffer mặc định luôn an toàn:** buffer có thể tăng không giới hạn và làm cạn bộ nhớ.
- **Gỡ listener chỉ khi cancel là đủ:** nguồn cũng có thể complete hoặc error; dùng cleanup bao quát như `onDispose` khi cần.
- **`Flux.push` và `Flux.create` giống nhau:** push dành cho một thread phát; create phù hợp khi callback có thể đến từ nhiều thread.
- **`Flux.generate` dùng để bọc mọi callback:** generate là nguồn đồng bộ từng phần tử, còn callback bất đồng bộ cần create/push hoặc API thích hợp.
- **Cancellation sẽ dừng mọi tác vụ từ xa:** nó chỉ gửi tín hiệu hủy; thư viện ngoài phải hỗ trợ hủy và tác dụng phụ đã xảy ra có thể không đảo ngược.
- **Mỗi subscription luôn dùng chung một listener:** Publisher cold thường tạo nguồn riêng theo subscription; muốn chia sẻ phải thiết kế rõ bằng share/replay hoặc một thành phần sở hữu nguồn dùng chung.
- **Callback có thể gọi sink sau khi luồng đã kết thúc:** adapter nên ngừng phát sau terminal signal và gỡ listener đúng lúc.

## 11. Bài tập vận dụng

Một thư viện đọc dữ liệu cảm biến cung cấp API:

~~~java
interface SensorApi {
    void register(Consumer<SensorReading> listener);
    void unregister(Consumer<SensorReading> listener);
}
~~~

Callback được gọi từ một thread I/O riêng và có thể phát hàng nghìn mẫu mỗi giây. Màn hình chỉ cần giá trị gần nhất, còn dịch vụ phân tích cần xử lý mọi mẫu trong giới hạn năng lực đã định.

Hãy thiết kế adapter:

1. Vì sao `Flux.create` phù hợp hơn `Flux.push` nếu thư viện có thể thay đổi và phát callback từ nhiều thread?
2. Viết `Flux<SensorReading>` đăng ký listener khi có subscription và gỡ listener khi dispose.
3. Màn hình nên dùng chính sách overflow nào? Vì sao?
4. Dịch vụ phân tích cần chính sách nào nếu không được phép mất mẫu? Buffer vô hạn có phải giải pháp an toàn không?
5. Nếu API cảm biến có phương thức `request(long n)`, bạn sẽ nối demand bằng callback nào của sink?
6. Nếu Subscriber hủy, điều gì cần xảy ra với listener và các callback đến muộn?
7. Bạn sẽ viết các kiểm thử nào để xác nhận hành vi overflow, cancellation và nhiều subscription?

**Gợi ý:** dùng `Flux.create` với `LATEST` cho nhánh hiển thị trạng thái mới nhất. Với phân tích không được mất mẫu, cần một cơ chế tiếp nhận có giới hạn hoặc hàng đợi bền vững và một chính sách rõ khi đầy. Đăng ký cleanup bằng `onDispose`, và chỉ dùng `onRequest` để chuyển demand khi API nguồn thực sự hỗ trợ điều tiết.

## Kết luận

`Mono.create` và `Flux.create` giúp đưa API callback hoặc listener vào mô hình Publisher–Subscriber. Adapter phải chuyển callback thành tín hiệu đúng loại, quản lý listener theo vòng đời subscription, xử lý lỗi và cancellation, đồng thời chọn chính sách overflow theo ý nghĩa dữ liệu. `Flux.push` phù hợp với nguồn phát từ một thread; `Flux.generate` dành cho nguồn đồng bộ từng phần tử. Khi hiểu giới hạn của nguồn ngoài và kiểm thử đăng ký, demand, overflow cùng cleanup, ta có thể ghép các API Java truyền thống vào pipeline Reactor mà vẫn kiểm soát được tài nguyên và hành vi khi tải thay đổi.
