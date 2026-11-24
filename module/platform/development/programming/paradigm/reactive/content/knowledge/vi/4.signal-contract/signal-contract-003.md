# Hợp đồng tín hiệu

## Phân biệt hoàn thành bình thường, lỗi và hủy đăng ký

Một pipeline reactive không chỉ truyền các phần tử dữ liệu. Nó còn truyền thông tin cho biết luồng đã kết thúc bình thường, kết thúc do lỗi hay subscriber không còn muốn nhận dữ liệu. Ba tình huống này có ý nghĩa khác nhau và dẫn đến cách xử lý khác nhau trong ứng dụng Java.

Trong Reactive Streams, **onComplete** và **onError** là hai tín hiệu kết thúc (terminal signal) do Publisher gửi đến Subscriber. Hủy đăng ký (cancellation) được Subscriber yêu cầu thông qua **Subscription.cancel()**. Cancellation điều khiển việc truyền dữ liệu và không phải là một tín hiệu kết thúc được gửi đến Subscriber. Hiểu rõ ranh giới này giúp thiết kế pipeline Project Reactor đúng vòng đời, giải phóng tài nguyên và xử lý lỗi có chủ đích.

### 1. Vòng đời tín hiệu của một subscription

Sau khi Subscriber đăng ký với Publisher, Publisher cung cấp một **Subscription** thông qua **onSubscribe**. Subscriber dùng đối tượng này để yêu cầu dữ liệu hoặc hủy đăng ký. Một subscription có thể phát không hoặc nhiều phần tử, sau đó kết thúc bằng đúng một trong hai tín hiệu **onComplete** hoặc **onError**.

| Tín hiệu hoặc thao tác | Hướng | Ý nghĩa |
| --- | --- | --- |
| **onSubscribe(subscription)** | Publisher → Subscriber | Cung cấp subscription để subscriber điều khiển nhu cầu và vòng đời |
| **request(n)** | Subscriber → Publisher | Yêu cầu thêm tối đa n phần tử |
| **onNext(value)** | Publisher → Subscriber | Truyền một phần tử dữ liệu |
| **onComplete()** | Publisher → Subscriber | Kết thúc bình thường; không còn phần tử tiếp theo |
| **onError(error)** | Publisher → Subscriber | Kết thúc do lỗi |
| **cancel()** | Subscriber → Publisher | Yêu cầu ngừng truyền dữ liệu cho subscription |

Trình tự khái quát:

~~~text
Subscriber                         Publisher
    |                                  |
    |------------ subscribe() -------->|
    |<--------- onSubscribe(sub) ------|
    |                                  |
    |------------ request(2) --------->|
    |<----------- onNext(A) -----------|
    |<----------- onNext(B) -----------|
    |                                  |
    |<----------- onComplete() --------|  hoặc
    |<----------- onError(error) ------|
~~~

Publisher phải gửi **onSubscribe** trước các tín hiệu khác. Sau đó có thể phát không hoặc nhiều **onNext**, rồi phát một tín hiệu kết thúc. **onComplete** và **onError** loại trừ lẫn nhau: một subscription không thể vừa kết thúc bình thường vừa kết thúc do lỗi. Sau tín hiệu kết thúc, Publisher không được gửi thêm tín hiệu cho subscription đó.

Các tín hiệu phải được tuần tự hóa theo hợp đồng Reactive Streams. Subscriber không nên giả định rằng mỗi callback luôn chạy trên cùng một thread; thư viện có thể điều phối tín hiệu qua scheduler. Tuy vậy, việc điều phối thread không thay đổi ý nghĩa của tín hiệu kết thúc.

### 2. Hoàn thành bình thường: onComplete

**onComplete()** cho biết Publisher đã phát xong dữ liệu và kết thúc bình thường. Subscriber không cần yêu cầu thêm phần tử sau tín hiệu này. Hoàn thành có thể xảy ra sau nhiều phần tử, sau một phần tử hoặc ngay lập tức mà không có phần tử nào.

Ví dụ một luồng phát ba trạng thái:

~~~java
Flux<String> orderStates =
    Flux.just("CREATED", "PAID", "SHIPPED");

orderStates.subscribe(
    state -> System.out.println("Trạng thái: " + state),
    error -> System.err.println("Lỗi: " + error.getMessage()),
    () -> System.out.println("Đã nhận hết trạng thái")
);
~~~

Subscriber nhận ba lần **onNext**, sau đó nhận **onComplete**. Callback hoàn tất chỉ chạy khi nguồn kết thúc bình thường. Nó phù hợp để thực hiện công việc phụ thuộc vào việc toàn bộ luồng đã kết thúc, chẳng hạn ghi nhận một đợt nhập dữ liệu đã xử lý xong.

Một luồng rỗng cũng hoàn thành bình thường:

~~~java
Mono<Order> lookup = Mono.empty();

lookup.subscribe(
    order -> display(order),
    error -> showFailure(error),
    () -> showNotFound()
);
~~~

**Mono.empty()** không phát **onNext**, nhưng vẫn phát **onComplete**. Vì vậy, hoàn thành không có nghĩa là subscriber chắc chắn đã nhận được một giá trị. Trong ví dụ tra cứu, ứng dụng có thể diễn giải kết quả rỗng thành “không tìm thấy”, tùy hợp đồng của tầng dịch vụ.

### 3. Kết thúc do lỗi: onError

**onError(error)** cho biết Publisher không thể tiếp tục phát dữ liệu do một lỗi. Đây là tín hiệu kết thúc. Sau khi Subscriber nhận **onError**, subscription đó không phát thêm **onNext** hoặc **onComplete**.

Ví dụ:

~~~java
Flux<Integer> parsedValues =
    Flux.just("12", "7x", "25")
        .map(Integer::parseInt);

parsedValues.subscribe(
    value -> System.out.println("Giá trị: " + value),
    error -> System.err.println(
        "Không thể phân tích dữ liệu: " + error.getMessage()
    ),
    () -> System.out.println("Đã hoàn tất")
);
~~~

Publisher phát **12**, sau đó phép chuyển đổi **"7x"** ném **NumberFormatException**. Reactor chuyển lỗi đó thành **onError**; phần tử **"25"** không được xử lý trong subscription hiện tại và callback hoàn tất bình thường không chạy.

Trong reactive, lỗi được truyền qua kênh tín hiệu của Publisher. Nó không đơn thuần là một ngoại lệ được ném ngược qua mọi lời gọi hàm như trong mã đồng bộ. Vì thế, cần đặt chiến lược xử lý lỗi trong pipeline hoặc cung cấp error callback khi subscribe. Nếu không có error handler phù hợp ở điểm đăng ký, Reactor có thể chuyển lỗi đến cơ chế xử lý lỗi mặc định của thư viện.

### 4. Phục hồi lỗi và ý nghĩa của tín hiệu cuối

Một toán tử phục hồi có thể thay thế lỗi bằng giá trị dự phòng hoặc một Publisher khác. Khi phục hồi thành công, downstream có thể nhận dữ liệu thay thế và kết thúc bằng **onComplete**. Điều này có nghĩa lỗi đã được xử lý trong pipeline; nó không còn được truyền như tín hiệu kết thúc lỗi đến subscriber cuối.

Ví dụ dùng **onErrorResume**:

~~~java
Flux<Integer> values =
    Flux.just("12", "7x", "25")
        .map(Integer::parseInt)
        .onErrorResume(
            NumberFormatException.class,
            error -> Flux.just(-1)
        );

values.subscribe(
    value -> System.out.println("Giá trị: " + value),
    error -> System.err.println("Pipeline thất bại: " + error),
    () -> System.out.println("Pipeline đã hoàn tất")
);
~~~

Kết quả là **12**, sau đó **-1** từ Publisher dự phòng, rồi hoàn tất bình thường. Phần tử **"25"** vẫn không được xử lý vì lỗi đã kết thúc nguồn upstream hiện tại; **onErrorResume** chuyển sang Publisher thay thế tại vị trí lỗi. Nếu Publisher dự phòng cũng phát lỗi, downstream sẽ nhận **onError**.

Một số toán tử thường dùng:

| Toán tử | Hành vi |
| --- | --- |
| **onErrorReturn(value)** | Thay lỗi bằng một giá trị dự phòng rồi hoàn tất |
| **onErrorResume(error → publisher)** | Chuyển sang Publisher dự phòng được chọn theo lỗi |
| **retry(n)** | Đăng ký lại upstream khi có lỗi, tối đa n lần thử lại |
| **timeout(duration)** | Phát lỗi timeout nếu không có tín hiệu phù hợp trong khoảng thời gian quy định |

Retry cần được dùng cẩn thận. Mỗi lần thử lại thường tạo một subscription mới đến upstream; các phần tử đã phát trước lỗi có thể được phát lại. Nếu pipeline đã thực hiện thao tác ghi dữ liệu, trừ tiền hoặc gửi yêu cầu đến dịch vụ ngoài, thử lại có thể lặp tác dụng phụ. Chỉ retry khi thao tác an toàn để lặp, có khóa idempotency hoặc có cơ chế đối soát phù hợp. Nên đặt giới hạn và khoảng chờ thay vì thử lại vô hạn.

### 5. Hủy đăng ký: Subscriber không muốn nhận thêm dữ liệu

Cancellation xảy ra khi Subscriber gọi **Subscription.cancel()** để yêu cầu Publisher ngừng truyền dữ liệu. Đây là thao tác điều khiển từ phía Subscriber, không phải **onComplete** hay **onError**. Khi Subscriber chủ động hủy, nó không nhận một tín hiệu kết thúc thay thế để thông báo “đã hủy”.

Trong Reactor, lời gọi **subscribe** thường trả về một **Disposable**. Gọi **dispose()** sẽ hủy subscription tương ứng:

~~~java
Disposable subscription =
    Flux.interval(Duration.ofSeconds(1))
        .doOnCancel(() -> System.out.println("Nguồn nhận yêu cầu hủy"))
        .subscribe(
            tick -> System.out.println("Tick: " + tick),
            error -> System.err.println("Lỗi: " + error),
            () -> System.out.println("Hoàn tất bình thường")
        );

// Khi màn hình hoặc thành phần không còn cần dữ liệu:
subscription.dispose();
~~~

Sau khi dispose, nguồn nhận yêu cầu cancellation và dừng việc phát dữ liệu cho subscription khi có thể. Callback **onComplete** không chạy chỉ vì subscriber đã dispose. **doOnCancel** có thể quan sát thao tác hủy ở vị trí được đặt trong pipeline.

Cancellation có thể xảy ra trong khi tín hiệu đang được truyền hoặc đang chờ xử lý. Theo hợp đồng, Publisher phải dần ngừng gửi tín hiệu sau khi nhận yêu cầu hủy; Subscriber vẫn cần chịu được một tín hiệu **onNext** đang chờ tại thời điểm gọi **cancel**. Vì vậy, không nên xem cancellation là một ranh giới đồng bộ bảo đảm mọi công việc đang chạy lập tức biến mất.

### 6. Cancellation khác với hoàn thành do toán tử giới hạn

Một điểm dễ nhầm là toán tử giới hạn số phần tử. Ví dụ:

~~~java
Flux<Integer> firstThree =
    Flux.range(1, 100)
        .take(3);

firstThree.subscribe(
    value -> System.out.println(value),
    error -> System.err.println(error),
    () -> System.out.println("Đã lấy đủ ba phần tử")
);
~~~

**take(3)** chỉ cho downstream nhận ba phần tử. Khi đã đủ số lượng, toán tử hủy subscription upstream để ngừng lấy phần tử tiếp theo, đồng thời phát **onComplete** cho downstream. Như vậy, cùng một thao tác nội bộ có thể có hai kết quả ở hai phía:

- Upstream nhận cancellation vì downstream không cần thêm dữ liệu.
- Downstream nhận completion vì publisher **take** đã hoàn thành công việc được giao.

Điều này không có nghĩa mọi cancellation đều biến thành completion. Nếu subscriber cuối cùng tự gọi **cancel** hoặc **dispose**, subscriber đó không nhận **onComplete** do chính hành động hủy của mình.

### 7. Dọn dẹp tài nguyên theo đúng vòng đời

Một nguồn reactive có thể giữ socket, cursor cơ sở dữ liệu, listener hoặc một tác vụ nền. Tài nguyên cần được giải phóng khi luồng hoàn tất, lỗi hoặc bị hủy. Chỉ đặt thao tác dọn dẹp trong callback **onComplete** là chưa đủ, vì callback đó không chạy khi subscription bị hủy hoặc kết thúc bằng lỗi.

Reactor cung cấp **doFinally** để quan sát cả ba kiểu kết thúc:

~~~java
Flux<OrderEvent> events =
    orderEventSource.events()
        .doFinally(signalType ->
            resourceTracker.finish(signalType)
        );
~~~

**SignalType** cho biết luồng kết thúc bằng **ON_COMPLETE**, **ON_ERROR** hay **CANCEL**. Hook này hữu ích cho log, metric và dọn dẹp tài nguyên đơn giản. Với tài nguyên có vòng đời bất đồng bộ như kết nối hoặc transaction cần đóng bằng một publisher, nên dùng các API quản lý tài nguyên phù hợp như **usingWhen** để mô tả cả quá trình mở và đóng.

Khi tạo adapter từ callback bên ngoài, cần gắn việc hủy đăng ký listener vào cancellation/disposal. Nếu không, consumer có thể đã rời màn hình nhưng nguồn vẫn giữ listener và tiếp tục phát sự kiện, gây rò rỉ tài nguyên hoặc giữ tham chiếu không cần thiết.

### 8. Kiểm thử ba trường hợp bằng StepVerifier

Kiểm thử pipeline reactive nên xác minh cả phần tử và tín hiệu kết thúc. **StepVerifier** trong module **reactor-test** cho phép mô tả những gì subscriber mong đợi.

Kiểm thử hoàn thành bình thường:

~~~java
StepVerifier.create(Flux.just("CREATED", "PAID"))
    .expectNext("CREATED", "PAID")
    .verifyComplete();
~~~

Kiểm thử kết thúc do lỗi:

~~~java
StepVerifier.create(Mono.error(new IllegalStateException("database unavailable")))
    .expectErrorMessage("database unavailable")
    .verify();
~~~

Kiểm thử cancellation:

~~~java
AtomicBoolean cancelled = new AtomicBoolean();

StepVerifier.create(
        Flux.<Long>never()
            .doOnCancel(() -> cancelled.set(true))
    )
    .thenCancel()
    .verify();

assertTrue(cancelled.get());
~~~

Trong kiểm thử cuối, **thenCancel()** yêu cầu StepVerifier hủy subscription. Hook **doOnCancel** xác nhận yêu cầu hủy đã đến được pipeline. Không dùng **verifyComplete()** cho trường hợp này, vì cancellation không phải là completion.

### 9. Cách chọn hành vi phù hợp với nghiệp vụ

Khi thiết kế một pipeline, hãy xác định ý nghĩa của từng kết quả cuối:

- Dùng **onComplete** khi nguồn đã cung cấp xong dữ liệu theo hợp đồng, kể cả khi không có phần tử nào.
- Dùng **onError** để biểu diễn lỗi khiến pipeline không thể tiếp tục theo luồng hiện tại.
- Dùng **onErrorReturn** hoặc **onErrorResume** khi có một phương án phục hồi rõ ràng và hợp lệ với nghiệp vụ.
- Dùng retry có giới hạn khi thao tác có thể lặp an toàn và lỗi có khả năng tạm thời.
- Dùng cancellation khi consumer không còn quan tâm đến kết quả hoặc thành phần sở hữu subscription đang dừng.
- Dọn dẹp tài nguyên cho cả completion, error và cancellation.

Trong hệ sinh thái Java reactive, ba trường hợp hoàn thành, lỗi và hủy đăng ký tạo nên ranh giới vòng đời của một luồng dữ liệu. Phân biệt đúng chúng giúp ứng dụng không báo thành công khi thao tác bị hủy, không bỏ qua lỗi thật và không giữ tài nguyên sau khi subscriber đã ngừng quan tâm. Đây là nền tảng để xây dựng và kiểm thử các pipeline **Mono**/**Flux** có hành vi rõ ràng.
