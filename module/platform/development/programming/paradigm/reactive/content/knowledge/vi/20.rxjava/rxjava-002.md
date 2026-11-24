# Observable và Flowable: khác biệt về hỗ trợ áp lực ngược

Trong **REACTIVE_PROGRAMMING**, ta xử lý các luồng dữ liệu bất đồng bộ bằng hợp đồng `Publisher–Subscriber`, cơ chế backpressure và các thư viện như Project Reactor. Trong RxJava, hai kiểu dữ liệu thường gặp để biểu diễn một luồng nhiều phần tử là **`Observable<T>`** và **`Flowable<T>`**. Cả hai đều có thể phát không hoặc nhiều phần tử, nhưng khác nhau ở hợp đồng tiêu thụ dữ liệu: `Flowable` hỗ trợ backpressure theo Reactive Streams, còn `Observable` không có giao thức demand `request(n)`.

Sự khác biệt này quyết định cách consumer xử lý khi nguồn phát nhanh hơn khả năng tiêu thụ. Chọn đúng kiểu nguồn giúp kiểm soát lượng dữ liệu đang chờ, tránh tích tụ bộ nhớ và kết nối RxJava với Reactor hoặc các thư viện Reactive Streams khác một cách rõ ràng.

## 1. Điểm khác biệt cốt lõi

`Observable` sử dụng giao thức Observer của RxJava. Observer nhận `onNext`, `onError` và `onComplete`, đồng thời có thể hủy đăng ký thông qua `Disposable`. Observer không gửi số lượng phần tử muốn nhận cho upstream.

`Flowable` triển khai giao diện `org.reactivestreams.Publisher`. Subscriber nhận một `Subscription` qua `onSubscribe`, sau đó có thể yêu cầu dữ liệu bằng `request(n)` và hủy bằng `cancel()`. Publisher phải tôn trọng demand và không phát `onNext` vượt số phần tử còn được yêu cầu.

| Đặc điểm | `Observable<T>` | `Flowable<T>` |
|---|---|---|
| Giao thức | Observer của RxJava | Reactive Streams `Publisher–Subscriber` |
| Đăng ký | `Observer` nhận `Disposable` | `Subscriber` nhận `Subscription` |
| Yêu cầu dữ liệu | Không có `request(n)` | Có `request(n)` |
| Backpressure | Không hỗ trợ ở cấp giao thức | Hỗ trợ theo hợp đồng Reactive Streams |
| Hủy đăng ký | `Disposable.dispose()` | `Subscription.cancel()` hoặc API dispose tương ứng của RxJava |
| Nguồn thường gặp | Sự kiện giao diện, callback, luồng sự kiện không có demand | Dữ liệu cần điều tiết, nguồn có thể phát theo nhu cầu, tích hợp Reactive Streams |

`Observable` và `Flowable` đều có thể là cold hoặc hot; cold/hot là đặc tính về thời điểm và cách nguồn phát dữ liệu, không phải tên gọi khác của có/không có backpressure. Một `Observable` cold vẫn không có `request(n)`, còn một `Flowable` hot vẫn phải xác định cách xử lý khi nguồn bên ngoài không thể giảm tốc.

## 2. Backpressure hoạt động như thế nào với Flowable?

Khi Subscriber đăng ký, Publisher cung cấp `Subscription`. Subscriber có thể bắt đầu với demand bằng 0 rồi yêu cầu thêm phần tử khi sẵn sàng:

```text
Subscriber                         Flowable
    |                                  |
    |--------- subscribe ------------>|
    |<-------- onSubscribe ------------|
    |                                  |
    |---------- request(2) ----------->|
    |<----------- onNext(A) -----------|
    |<----------- onNext(B) -----------|
    |                                  |
    |------ xử lý xong, request(1) --->|
    |<----------- onNext(C) -----------|
```

Nếu Subscriber chưa yêu cầu thêm dữ liệu, Flowable không được phát thêm `onNext` cho subscription đó. Khi consumer xử lý xong và có khả năng nhận thêm, nó gửi một yêu cầu mới.

Ví dụ, `Flowable.range` có thể phát theo đúng nhu cầu:

```java
Flowable<Integer> numbers = Flowable.range(1, 5);

TestSubscriber<Integer> subscriber = new TestSubscriber<>(0L);
numbers.subscribe(subscriber);

subscriber.assertNoValues();

subscriber.requestMore(2);
subscriber.assertValues(1, 2);

subscriber.requestMore(3);
subscriber.assertValues(1, 2, 3, 4, 5);
subscriber.assertComplete();
```

`TestSubscriber` bắt đầu với demand bằng 0. Hai phần tử đầu chỉ được phát sau `requestMore(2)`; ba phần tử còn lại được phát sau yêu cầu tiếp theo. Đây là cách kiểm thử trực tiếp việc nguồn tôn trọng demand.

Backpressure điều tiết số phần tử được phép phát, không phải giới hạn số phần tử mỗi giây. Nếu cần giới hạn request theo thời gian, vẫn phải dùng rate limiter hoặc toán tử điều tiết thời gian phù hợp.

## 3. Observable không có demand để điều tiết upstream

Với `Observable`, Observer đăng ký và nhận các phần tử khi nguồn phát. Không có API `request(n)` để Observer nói rằng mình chỉ sẵn sàng nhận thêm hai phần tử.

```java
Observable<Integer> numbers = Observable.range(1, 5);

numbers.subscribe(
    value -> System.out.println("received: " + value),
    error -> System.err.println("failed: " + error),
    () -> System.out.println("completed")
);
```

Nguồn phát các phần tử theo ngữ nghĩa của nó; consumer không điều tiết nguồn bằng demand. Nếu downstream chậm vì xử lý blocking hoặc vì một ranh giới bất đồng bộ có queue, dữ liệu có thể phải chờ trong queue đó. Khi tốc độ đến duy trì cao hơn tốc độ xử lý, lượng dữ liệu chờ có thể tăng và gây áp lực bộ nhớ.

Điều này không có nghĩa mọi `Observable` đều tự động tạo queue không giới hạn. Lượng dữ liệu được giữ phụ thuộc nguồn, toán tử và scheduler cụ thể. Điểm chắc chắn là giao thức `Observable` không cung cấp backpressure để yêu cầu upstream giảm lượng phát.

Với sự kiện giao diện, việc nhận mọi thay đổi trung gian đôi khi không cần thiết. Các toán tử như `debounce`, `sample` hoặc `throttleFirst` có thể giảm số sự kiện theo ý nghĩa nghiệp vụ. Đây là lọc hoặc lấy mẫu sự kiện; chúng không bổ sung giao thức `request(n)` cho `Observable`.

## 4. Chọn Observable hay Flowable?

Chọn kiểu dựa trên đặc tính nguồn và yêu cầu dữ liệu:

| Tình huống | Lựa chọn thường phù hợp | Lý do |
|---|---|---|
| Sự kiện giao diện hoặc callback có tốc độ vừa phải | `Observable` | API Observer đơn giản, thường không cần demand từng phần tử |
| Dữ liệu lớn cần consumer điều tiết | `Flowable` | Subscriber có thể yêu cầu số phần tử theo khả năng xử lý |
| Nguồn đã triển khai Reactive Streams | `Flowable` | Có thể kết nối trực tiếp qua `Publisher` |
| Nguồn đẩy liên tục, không thể giảm tốc | `Flowable` với chính sách overflow phù hợp hoặc `Observable` với lọc/lấy mẫu | Phải quyết định rõ giữ, bỏ, lấy mới nhất hay báo lỗi |
| Xử lý cần giữ mọi phần tử và có thể điều tiết nguồn | `Flowable` | Demand có thể lan ngược về nguồn hỗ trợ backpressure |
| Chỉ cần trạng thái mới nhất, các giá trị trung gian có thể bỏ | Có thể dùng `Observable` với `sample`/`debounce` hoặc `Flowable` với `onBackpressureLatest` | Chọn theo giao thức và ngữ nghĩa nguồn |

Không nên chuyển mọi `Observable` thành `Flowable` chỉ để đổi tên kiểu dữ liệu. Nếu nguồn không thể điều tiết, adapter phải chọn chính sách khi consumer không theo kịp. Việc chuyển kiểu không tự tạo ra năng lực backpressure ở thiết bị, callback hoặc API bên ngoài.

## 5. Chuyển nguồn không hỗ trợ backpressure sang Flowable

RxJava cung cấp `BackpressureStrategy` khi tạo Flowable từ một nguồn push hoặc chuyển `Observable` sang `Flowable`. Chiến lược này xác định điều gì xảy ra khi nguồn phát nhanh hơn demand downstream.

| Chiến lược | Hành vi | Khi nào cân nhắc |
|---|---|---|
| `BUFFER` | Giữ các phần tử chưa được tiêu thụ trong buffer; buffer có thể tăng lớn | Chỉ khi tải có giới hạn hoặc có biện pháp kiểm soát bộ nhớ rõ ràng |
| `DROP` | Bỏ phần tử mới khi không có demand | Dữ liệu có thể mất, như telemetry hoặc mẫu phụ |
| `LATEST` | Giữ giá trị mới nhất, thay thế giá trị đang chờ cũ hơn | Trạng thái hiện tại quan trọng hơn lịch sử trung gian |
| `ERROR` | Báo `MissingBackpressureException` khi không thể phát theo demand | Muốn phát hiện quá tải rõ ràng và để ứng dụng xử lý |
| `MISSING` | Không áp dụng chiến lược buffer/drop/error tại nguồn này | Khi sẽ đặt chính sách backpressure-aware ở một bước downstream phù hợp |

Ví dụ chuyển một `Observable` thành `Flowable` với chính sách bỏ phần tử mới khi downstream chưa theo kịp:

```java
Flowable<SensorReading> readings = sensorObservable
    .toFlowable(BackpressureStrategy.DROP);
```

Với `DROP`, các phần tử đến khi downstream không có demand có thể bị bỏ. Đây là lựa chọn nghiệp vụ: consumer sẽ không nhận đầy đủ mọi lần đo. Nếu mọi mẫu đều cần được lưu, chiến lược drop không phù hợp.

### Buffer không giới hạn có thể che giấu quá tải

```java
Flowable<Event> buffered = eventObservable
    .toFlowable(BackpressureStrategy.BUFFER);
```

`BUFFER` giữ các phần tử cho đến khi downstream yêu cầu và xử lý. Nếu nguồn phát nhanh hơn consumer trong thời gian dài, queue tăng theo tải và có thể làm cạn bộ nhớ. Buffer chỉ hấp thụ burst ngắn; nó không sửa được chênh lệch năng lực kéo dài.

### LATEST cho dữ liệu trạng thái

```java
Flowable<Position> latestPosition = positionObservable
    .toFlowable(BackpressureStrategy.LATEST);
```

Nếu consumer đang bận, chiến lược này giữ giá trị mới nhất và bỏ qua các giá trị cũ bị thay thế. Nó phù hợp khi giao diện hoặc thuật toán chỉ cần vị trí gần nhất. Không dùng cho lệnh giao dịch hoặc sự kiện cần kiểm toán đầy đủ.

### ERROR để từ chối quá tải rõ ràng

```java
Flowable<Event> checked = eventObservable
    .toFlowable(BackpressureStrategy.ERROR);
```

Nếu nguồn phát khi downstream không có đủ demand, luồng có thể kết thúc bằng `MissingBackpressureException`. Ứng dụng có thể ghi nhận lỗi, từ chối request hoặc chuyển dữ liệu sang một cơ chế lưu trữ khác. Không nên retry tức thì mà không có giới hạn vì điều đó có thể làm tình trạng quá tải nặng hơn.

## 6. Tạo Flowable từ nguồn push bằng create

Khi tự tích hợp callback hoặc thiết bị, `Flowable.create` yêu cầu chọn `BackpressureStrategy`:

```java
Flowable<Integer> sensorValues = Flowable.create(emitter -> {
    for (int value : readAvailableValues()) {
        if (emitter.isCancelled()) {
            return;
        }
        emitter.onNext(value);
    }
    emitter.onComplete();
}, BackpressureStrategy.ERROR);
```

Ví dụ kiểm tra cancellation để dừng phát khi Subscriber đã hủy. `ERROR` làm rõ trường hợp nguồn cố phát vượt demand. Với callback bất đồng bộ sống lâu, cần đăng ký listener khi subscribe và gỡ listener khi emitter bị dispose/cancel, thường thông qua `setCancellable` hoặc `setDisposable`:

```java
Flowable<SensorReading> sensorStream = Flowable.create(emitter -> {
    SensorListener listener = reading -> {
        if (!emitter.isCancelled()) {
            emitter.onNext(reading);
        }
    };

    sensor.register(listener);
    emitter.setCancellable(() -> sensor.unregister(listener));
}, BackpressureStrategy.LATEST);
```

Ở đây, `LATEST` giữ trạng thái gần nhất khi consumer chậm, còn `setCancellable` gỡ listener khi subscription bị hủy. Nếu nghiệp vụ yêu cầu lưu mọi sự kiện, cần một hàng đợi hữu hạn hoặc kho bền vững và chính sách overflow khác; `LATEST` sẽ làm mất các giá trị trung gian.

Không dùng vòng lặp phát dữ liệu vô hạn trên cùng thread subscribe nếu nó không kiểm tra cancellation và không có cơ chế điều tiết. Nguồn tự triển khai cần tôn trọng lifecycle, giải phóng listener/tài nguyên và chọn chiến lược phù hợp với khả năng phát thực tế.

## 7. Flowable có các toán tử backpressure chuyên dụng

Ngoài strategy tại thời điểm tạo nguồn, `Flowable` có các toán tử để chọn hành vi khi upstream không thể theo kịp demand downstream:

```java
Flowable<Long> ticks = Flowable.interval(Duration.ofMillis(10))
    .onBackpressureDrop()
    .observeOn(Schedulers.computation(), false, 32)
    .map(this::processTick);
```

`onBackpressureDrop` bỏ tick khi downstream chưa sẵn sàng. `observeOn` chuyển xử lý downstream sang scheduler computation và dùng prefetch 32. Nếu bỏ `onBackpressureDrop`, một nguồn thời gian như `interval` có thể phát sinh lỗi backpressure khi không thể phát tick theo demand. Chọn drop có nghĩa ứng dụng chấp nhận bỏ một số tick.

Có thể thay bằng `onBackpressureLatest()` nếu chỉ cần tick mới nhất, hoặc một dạng `onBackpressureBuffer(...)` nếu muốn giữ dữ liệu trong giới hạn cụ thể. Cần xác định rõ hành vi khi buffer đầy; không dùng buffer vô hạn như một cách trì hoãn vô thời hạn việc xử lý quá tải.

## 8. Scheduler không tự bổ sung backpressure

`subscribeOn` và `observeOn` điều khiển nơi thực thi, không thay thế giao thức demand. Một queue ở ranh giới scheduler có thể hấp thụ một lượng dữ liệu, nhưng nếu nguồn không thể giảm tốc, queue vẫn có nguy cơ tăng.

Với `Observable`, ví dụ:

```java
Observable<Event> events = eventSource()
    .observeOn(Schedulers.computation())
    .map(this::process);
```

`observeOn` chuyển callback downstream sang scheduler computation. Observer không có `request(n)` để yêu cầu nguồn tạm dừng; queue của toán tử có thể tích tụ nếu nguồn phát quá nhanh.

Với `Flowable`:

```java
Flowable<Event> events = flowableSource()
    .observeOn(Schedulers.computation(), false, 64)
    .map(this::process);
```

`observeOn` dùng prefetch để yêu cầu trước dữ liệu từ upstream và truyền demand theo cơ chế backpressure. Khi downstream chậm, việc yêu cầu thêm dữ liệu có thể được điều tiết. Tuy nhiên, các nguồn không hỗ trợ demand vẫn cần strategy ở ranh giới chuyển đổi.

## 9. Kiểm thử khác biệt bằng TestObserver và TestSubscriber

`TestObserver` kiểm tra tín hiệu của `Observable`. `TestSubscriber` kiểm tra `Flowable` và cho phép đặt demand ban đầu.

```java
Observable<Integer> observable = Observable.range(1, 3);

observable.test()
    .assertResult(1, 2, 3);
```

`Observable` phát theo giao thức Observer; test không thể điều khiển upstream bằng `request(n)`.

Với `Flowable`, có thể kiểm tra demand theo từng phần:

```java
TestSubscriber<Integer> subscriber = new TestSubscriber<>(0L);

Flowable.range(1, 3).subscribe(subscriber);

subscriber.assertNoValues();
subscriber.requestMore(1);
subscriber.assertValues(1);

subscriber.requestMore(2);
subscriber.assertValues(1, 2, 3);
subscriber.assertComplete();
```

Để kiểm tra chính sách drop khi bridge một nguồn push, có thể giữ demand bằng 0 và xác nhận không có giá trị nào được buffer lại:

```java
TestSubscriber<Integer> subscriber = new TestSubscriber<>(0L);

Observable.range(1, 5)
    .toFlowable(BackpressureStrategy.DROP)
    .subscribe(subscriber);

subscriber.assertNoValues();
subscriber.requestMore(5);
subscriber.assertNoValues();
subscriber.assertComplete();
```

Nguồn `Observable.range` phát đồng bộ khi subscribe; vì demand ban đầu bằng 0 và strategy là `DROP`, các phần tử được phát trong lúc chưa có demand bị bỏ. Test này thể hiện adapter không làm nguồn push chờ đến khi consumer yêu cầu.

Với `BUFFER`, cùng tình huống có thể giữ phần tử để phát sau khi demand đến. Nhưng test nhỏ không chứng minh buffer an toàn dưới tải lớn; cần kiểm thử giới hạn bộ nhớ và chính sách overflow ở quy mô phù hợp.

## 10. Tích hợp RxJava với Reactive Streams và Reactor

`Flowable` triển khai `org.reactivestreams.Publisher`, vì vậy có thể kết nối trực tiếp với Reactor:

```java
Flowable<Order> rxOrders = Flowable.fromPublisher(orderPublisher);

Flux<Order> reactorOrders = Flux.from(rxOrders);
```

Chiều ngược lại, `Flowable.fromPublisher` có thể nhận một `Publisher` như `Flux` của Reactor:

```java
Flowable<Order> rxOrders = Flowable.fromPublisher(reactorFlux);
```

`Observable` không triển khai Reactive Streams `Publisher`, do đó cần chuyển đổi qua `toFlowable` và chọn strategy:

```java
Flux<Event> reactorEvents = Flux.from(
    observableEvents.toFlowable(BackpressureStrategy.LATEST)
);
```

Chiến lược `LATEST` ở đây là một phần của hợp đồng tích hợp: Reactor chỉ nhận giá trị mới nhất trong khi downstream không theo kịp. Nếu cần giữ mọi sự kiện, hãy chọn chiến lược khác và giới hạn buffer phù hợp với yêu cầu dữ liệu.

## 11. Các nhầm lẫn thường gặp

| Nhầm lẫn | Thực tế |
|---|---|
| `Observable` và `Flowable` chỉ khác tên | `Flowable` có `Subscription.request(n)`; `Observable` không có demand protocol |
| Chuyển `Observable` sang `Flowable` tự làm nguồn chậm lại | Adapter phải chọn buffer, drop, latest, error hoặc missing; nguồn push có thể vẫn phát độc lập |
| `BUFFER` luôn an toàn | Buffer có thể tăng lớn và gây cạn bộ nhớ nếu tải vượt năng lực kéo dài |
| `DROP` chỉ giảm tốc độ | Drop làm mất phần tử; cần chắc chắn nghiệp vụ cho phép mất dữ liệu |
| `LATEST` tương đương xử lý đầy đủ | Các giá trị trung gian có thể bị thay thế trước khi consumer nhận |
| `observeOn` giải quyết backpressure | Scheduler đổi nơi thực thi; chỉ `Flowable` mới có demand protocol để điều tiết upstream |
| Có backpressure nghĩa là có rate limit | Demand đếm phần tử, không giới hạn số phần tử theo giây |
| Hot source luôn không hỗ trợ backpressure | Hot/cold và hỗ trợ demand là hai thuộc tính riêng; khả năng điều tiết phụ thuộc nguồn và adapter |

## 12. Quy trình lựa chọn

Trước khi chọn `Observable` hay `Flowable`, hãy trả lời:

1. Nguồn có thể tôn trọng demand và giảm tốc độ phát không?
2. Consumer có cần yêu cầu dữ liệu theo từng phần tử hoặc từng lô không?
3. Nếu nguồn không thể giảm tốc, dữ liệu có được phép drop hoặc thay thế bằng giá trị mới nhất không?
4. Nếu phải giữ mọi phần tử, buffer tối đa là bao nhiêu và khi đầy sẽ làm gì?
5. Subscription có cần hủy listener, callback hoặc tài nguyên nguồn không?
6. Khi kết nối với Reactor hoặc thư viện Reactive Streams, strategy chuyển đổi có giữ đúng semantics nghiệp vụ không?
7. Test có xác minh demand, overflow, drop/latest và cancellation không?

Chọn `Observable` khi giao thức Observer đơn giản đáp ứng được nguồn và consumer. Chọn `Flowable` khi cần phối hợp producer và consumer bằng demand hoặc cần kết nối với Reactive Streams. Với nguồn push không thể điều tiết, quyết định rõ buffer, drop, latest hay error tại ranh giới chuyển đổi. Nhờ đó, khác biệt giữa hai kiểu dữ liệu trở thành một quyết định kiến trúc có chủ đích về khả năng giữ dữ liệu, độ trễ và giới hạn tài nguyên.
