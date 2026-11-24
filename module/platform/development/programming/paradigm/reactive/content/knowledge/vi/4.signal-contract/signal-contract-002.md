# Tín hiệu kết thúc và giới hạn phát dữ liệu sau khi kết thúc

Trong Reactive Streams, Publisher phát các phần tử dữ liệu qua `onNext(value)` và kết thúc một subscription bằng một trong hai tín hiệu: `onComplete()` hoặc `onError(error)`. Hai tín hiệu này đánh dấu ranh giới cuối cùng của luồng. Sau khi đã phát một tín hiệu kết thúc, Publisher không được phát thêm phần tử dữ liệu hay tín hiệu kết thúc khác trên cùng subscription.

Quy tắc này giúp Subscriber biết chính xác khi nào có thể ngừng chờ dữ liệu, giải phóng tài nguyên và chuyển sang bước tiếp theo. Nó cũng ngăn một luồng rơi vào trạng thái mơ hồ, chẳng hạn đã báo hoàn tất nhưng sau đó lại phát thêm kết quả.

## 1. Hai tín hiệu kết thúc của một subscription

Một subscription có thể kết thúc theo hai cách:

- **Hoàn tất bình thường — `onComplete()`:** Publisher đã phát xong các phần tử dữ liệu dự kiến.
- **Kết thúc do lỗi — `onError(Throwable error)`:** Publisher không thể tiếp tục luồng vì một lỗi.

Cả hai đều là tín hiệu vòng đời, không phải phần tử dữ liệu kiểu `T`. Chúng được gửi từ Publisher đến Subscriber và không tiêu thụ demand đã được yêu cầu bằng `request(n)`.

Ví dụ, một luồng phát ba mã đơn hàng rồi hoàn tất:

~~~java
Flux<String> orderIds = Flux.just("ORD-101", "ORD-102", "ORD-103");
~~~

Khi có Subscriber đăng ký và yêu cầu đủ dữ liệu, Publisher phát ba lần `onNext`, sau đó phát một lần `onComplete`. Nếu nguồn kết thúc sớm hơn số phần tử Subscriber đã yêu cầu, Publisher vẫn có thể phát `onComplete` ngay sau phần tử cuối cùng. Tín hiệu hoàn tất không phải chờ Subscriber sử dụng hết demand.

Một nguồn khác có thể kết thúc bằng lỗi:

~~~java
Flux<String> orderIds = Flux.concat(
    Flux.just("ORD-101", "ORD-102"),
    Flux.error(new IllegalStateException("Không thể đọc đơn hàng tiếp theo"))
);
~~~

Subscriber nhận hai phần tử dữ liệu, sau đó nhận `onError`. Với subscription này, Publisher không được phát thêm `onNext` sau lỗi.

## 2. Vòng đời: từ hoạt động đến kết thúc

Có thể mô hình hóa vòng đời của một subscription bằng các trạng thái sau:

~~~mermaid
stateDiagram-v2
    [*] --> Active: onSubscribe
    Active --> Active: onNext(value)
    Active --> Completed: onComplete()
    Active --> Failed: onError(error)
    Active --> Cancelled: cancel()
    Completed --> [*]
    Failed --> [*]
    Cancelled --> [*]
~~~

Khi ở trạng thái hoạt động, Publisher có thể phát các phần tử dữ liệu theo demand. Subscription rời trạng thái hoạt động khi xảy ra một trong ba tình huống:

- Publisher hoàn tất bình thường.
- Publisher kết thúc bằng lỗi.
- Subscriber yêu cầu hủy bằng `cancel()`.

Hai trạng thái đầu được thông báo bằng tín hiệu terminal đến Subscriber. Hủy subscription là thao tác điều khiển từ Subscriber; nó không tạo ra callback `onCancelled()` và không bắt buộc Publisher phải gửi `onComplete()` để xác nhận.

Một khi `onComplete()` hoặc `onError()` đã được phát, subscription được xem là đã kết thúc. Không thể quay lại trạng thái hoạt động bằng cách gọi `request()` thêm lần nữa. Nếu ứng dụng cần chạy một luồng mới, nó phải tạo subscription mới hoặc đăng ký một Publisher khác.

## 3. Quy tắc không phát tín hiệu sau terminal

Reactive Streams yêu cầu Publisher tuân thủ các quy tắc kết thúc:

1. Một subscription chỉ có thể kết thúc bằng tối đa một tín hiệu `onComplete()` hoặc `onError()`.
2. Sau tín hiệu terminal, Publisher không được phát thêm `onNext`, `onError` hay `onComplete` trên subscription đó.
3. Nếu Publisher kết thúc bình thường, nó phải báo `onComplete()`.
4. Nếu Publisher kết thúc do lỗi, nó phải báo `onError(error)`.
5. Tín hiệu `onNext`, `onError` và `onComplete` phải được phát tuần tự, không chồng lấn theo cách vi phạm hợp đồng.
6. Sau khi subscription bị hủy, Publisher phải ngừng phát tín hiệu đến Subscriber. Việc dừng ở nguồn có thể cần thời gian để hoàn tất nếu đang có công việc hoặc tín hiệu trong quá trình thực thi.

Có thể nhìn quy tắc terminal qua một chuỗi tín hiệu hợp lệ:

~~~text
onSubscribe(subscription)
onNext(value1)
onNext(value2)
onComplete()
~~~

Chuỗi sau không hợp lệ:

~~~text
onSubscribe(subscription)
onNext(value1)
onComplete()
onNext(value2)       // Không được phát sau onComplete
onError(error)       // Không được phát terminal lần thứ hai
~~~

Tương tự, sau `onError(error)` cũng không được phát thêm `onNext` hoặc `onComplete`. Publisher không được dùng `onComplete()` như một tín hiệu phụ sau lỗi; lỗi đã là tín hiệu kết thúc duy nhất của subscription đó.

Các quy tắc này áp dụng cho từng subscription. Một Publisher có thể phục vụ nhiều Subscriber độc lập; việc một subscription kết thúc không có nghĩa mọi subscription khác của Publisher cũng đã kết thúc.

## 4. Terminal không phụ thuộc vào demand

`request(n)` điều khiển số phần tử dữ liệu mà Subscriber cho phép Publisher phát. Demand chỉ đếm các lần `onNext(value)`, không đếm `onSubscribe`, `onError` hay `onComplete`.

Ví dụ, Subscriber yêu cầu năm phần tử nhưng nguồn chỉ có hai phần tử:

~~~java
Flux<Integer> source = Flux.just(10, 20);

source.subscribe(new BaseSubscriber<Integer>() {
    @Override
    protected void hookOnSubscribe(Subscription subscription) {
        request(5);
    }

    @Override
    protected void hookOnNext(Integer value) {
        process(value);
    }

    @Override
    protected void hookOnComplete() {
        log.info("Nguồn đã phát hết dữ liệu");
    }
});
~~~

Publisher chỉ phát `10` và `20`, sau đó phát `onComplete()`. Không cần ba phần tử còn lại để hoàn tất. Tín hiệu terminal có thể đi qua ngay cả khi demand chưa được sử dụng hết.

Một nguồn rỗng cũng có thể hoàn tất mà không phát phần tử nào:

~~~java
Mono<String> optionalName = Mono.empty();
Flux<Integer> noEvents = Flux.empty();
~~~

Khi đăng ký, các Publisher này phát `onComplete()` mà không phát `onNext`. Đây là hành vi hợp lệ và thường được dùng để biểu diễn kết quả không có dữ liệu nhưng thao tác đã hoàn tất bình thường.

Ngược lại, Publisher có thể phát `onError()` mà không phát bất kỳ phần tử dữ liệu nào:

~~~java
Mono<Order> failedOrder =
    Mono.error(new IllegalArgumentException("Mã đơn hàng không hợp lệ"));
~~~

Vì vậy, không nên suy luận rằng một subscription phải phát ít nhất một phần tử dữ liệu mới có thể kết thúc.

## 5. Hủy subscription khác với kết thúc bằng tín hiệu

`cancel()` được Subscriber gọi trên Subscription để thông báo rằng nó không còn muốn nhận dữ liệu. Publisher phải ngừng phát tín hiệu cho Subscriber đó và giải phóng tài nguyên có thể giải phóng.

Tuy nhiên, cancellation khác với terminal:

| Hành vi | Ai khởi tạo? | Subscriber nhận tín hiệu gì? | Có cần `onComplete()` không? |
|---|---|---|---|
| Hoàn tất bình thường | Publisher | `onComplete()` | Đây chính là tín hiệu hoàn tất. |
| Kết thúc do lỗi | Publisher | `onError(error)` | Không. |
| Hủy subscription | Subscriber | Không có callback xác nhận hủy riêng | Không. |

Hủy subscription có tính hợp tác. Nếu một tác vụ I/O đã được gửi xuống driver hoặc hệ thống bên ngoài, việc gọi `cancel()` không bảo đảm mọi công việc vật lý dừng ngay lập tức. Tầng nguồn cần hỗ trợ cancellation để có thể dừng tác vụ và thu hồi tài nguyên hiệu quả.

Việc hủy cũng có thể cạnh tranh với một tín hiệu đang được phát. Một tín hiệu đã bắt đầu trước khi Publisher xử lý xong yêu cầu hủy có thể đang trên đường đến Subscriber. Hợp đồng yêu cầu Publisher cuối cùng phải ngừng phát; ứng dụng không nên dựa vào giả định rằng mọi tầng bên dưới dừng đồng bộ ngay tại thời điểm gọi `cancel()`.

Ví dụ, toán tử `take(2)` chỉ cho downstream nhận hai phần tử. Khi đủ số lượng, nó hủy subscription upstream và hoàn tất luồng downstream:

~~~java
Flux<Integer> firstTwo = Flux.range(1, 100)
    .doOnCancel(() -> log.info("Upstream nhận yêu cầu hủy"))
    .take(2);

StepVerifier.create(firstTwo)
    .expectNext(1, 2)
    .verifyComplete();
~~~

Ở đây có hai sự kiện khác nhau: upstream nhận cancellation do `take(2)` không cần thêm dữ liệu; downstream nhận `onComplete()` vì Publisher do `take` tạo ra đã hoàn tất sau hai phần tử. Không nên diễn giải việc upstream bị hủy thành việc upstream đã phát `onComplete()`.

## 6. Xử lý lỗi không làm sống lại subscription đã kết thúc

Khi một Publisher phát `onError`, subscription upstream đó đã kết thúc. Trong Project Reactor, các toán tử như `onErrorResume` có thể thay thế nhánh lỗi bằng một Publisher dự phòng để downstream tiếp tục nhận dữ liệu.

~~~java
Flux<String> result = Flux.concat(
        Flux.just("A", "B"),
        Flux.error(new IllegalStateException("Nguồn gặp lỗi"))
    )
    .onErrorResume(error -> Flux.just("FALLBACK"));

StepVerifier.create(result)
    .expectNext("A", "B", "FALLBACK")
    .verifyComplete();
~~~

Downstream nhận `A`, `B`, rồi `FALLBACK` và hoàn tất bình thường. Điều này không có nghĩa Publisher ban đầu đã phát dữ liệu sau `onError`. Khi lỗi xảy ra, nhánh nguồn ban đầu đã kết thúc; `onErrorResume` đăng ký hoặc sử dụng Publisher dự phòng và nối kết quả của nhánh đó vào luồng downstream.

Tương tự, `onErrorReturn` chuyển lỗi thành một giá trị dự phòng:

~~~java
Mono<String> displayName = loadName()
    .onErrorReturn("Không thể tải tên");
~~~

Nếu cần thử lại nguồn, `retry` cũng tạo một lần đăng ký mới với Publisher nguồn. Nó không xóa tín hiệu lỗi đã xảy ra trong subscription cũ hoặc tiếp tục subscription cũ từ vị trí bị lỗi.

~~~java
Mono<Order> order = loadOrder(orderId)
    .retry(2);
~~~

Mỗi lần thử lại là một lần subscribe mới. Nếu tất cả lần thử đều thất bại, lỗi cuối cùng sẽ được truyền đến downstream bằng `onError`, trừ khi một toán tử phía sau tiếp tục xử lý lỗi.

Điểm quan trọng là các toán tử phục hồi lỗi xây dựng một luồng downstream mới hoặc thay thế nhánh xử lý. Chúng không cho phép Publisher vi phạm quy tắc terminal trên subscription ban đầu.

## 7. Biểu diễn các trường hợp kết thúc trong Reactor

Project Reactor có các Publisher thể hiện trực tiếp những kết quả vòng đời khác nhau:

| Publisher | Phần tử dữ liệu | Tín hiệu kết thúc |
|---|---|---|
| `Flux.just("A", "B")` | `A`, `B` | `onComplete()` |
| `Flux.empty()` | Không có | `onComplete()` |
| `Mono.empty()` | Không có | `onComplete()` |
| `Mono.error(error)` | Không có | `onError(error)` |
| `Flux.concat(Flux.just("A"), Flux.error(error))` | `A` | `onError(error)` |

Có thể quan sát các trường hợp này bằng `doFinally`:

~~~java
Flux<String> source = Flux.just("A", "B")
    .doFinally(signalType ->
        log.info("Kết thúc subscription: {}", signalType)
    );
~~~

`doFinally` được gọi khi subscription kết thúc do hoàn tất, lỗi hoặc hủy. Tham số `SignalType` giúp phân biệt `ON_COMPLETE`, `ON_ERROR` và `CANCEL`. Đây là hook quan sát vòng đời; nó không thay đổi tín hiệu terminal đã gửi đến Subscriber.

Một số toán tử hữu ích khác:

- `doOnComplete` quan sát hoàn tất bình thường.
- `doOnError` quan sát lỗi.
- `doOnCancel` quan sát yêu cầu hủy.
- `onErrorResume` chuyển sang Publisher dự phòng khi có lỗi.
- `retry` đăng ký lại Publisher nguồn theo chính sách thử lại.
- `take(n)` giới hạn số phần tử downstream nhận và có thể hủy upstream khi đã đủ.

Khi đọc log, cần phân biệt hook nào quan sát terminal ở upstream và hook nào quan sát terminal ở downstream. Một toán tử phục hồi lỗi có thể khiến upstream kết thúc bằng lỗi trong khi downstream hoàn tất bình thường sau khi nhận Publisher dự phòng.

## 8. Kiểm thử hợp đồng kết thúc bằng StepVerifier

`StepVerifier` cho phép xác minh thứ tự phần tử và tín hiệu kết thúc mà không cần chạy một ứng dụng đầy đủ.

Kiểm thử hoàn tất bình thường:

~~~java
@Test
void luongHoanTatSauHaiPhanTu() {
    StepVerifier.create(Flux.just("A", "B"))
        .expectNext("A")
        .expectNext("B")
        .verifyComplete();
}
~~~

`verifyComplete()` yêu cầu Publisher phát `onComplete()` sau các phần tử đã khai báo. Nếu Publisher phát lỗi hoặc không kết thúc trong thời hạn kiểm thử, phép thử sẽ thất bại.

Kiểm thử kết thúc do lỗi:

~~~java
@Test
void luongKetThucBangLoi() {
    RuntimeException expected =
        new IllegalStateException("Không đọc được nguồn");

    StepVerifier.create(
            Flux.concat(Flux.just("A"), Flux.error(expected))
        )
        .expectNext("A")
        .expectErrorMatches(error -> error == expected)
        .verify();
}
~~~

Kiểm thử này xác nhận `A` được phát trước và subscription kết thúc bằng lỗi mong đợi. Không có bước `expectNext` nào sau `expectError`, vì không được có phần tử dữ liệu sau terminal.

Kiểm thử hủy subscription:

~~~java
@Test
void huySubscriptionDungViecNhanThemDuLieu() {
    StepVerifier.create(Flux.interval(Duration.ofMillis(100)))
        .expectNext(0L)
        .thenCancel()
        .verify();
}
~~~

Trong trường hợp này, `thenCancel()` yêu cầu StepVerifier hủy subscription. Publisher không cần phát `onComplete()` để xác nhận thao tác hủy. Khi kiểm thử nguồn bất đồng bộ, có thể dùng virtual time để tránh chờ đồng hồ thực.

Ngoài ra, nên kiểm tra các tình huống sau:

- Publisher rỗng phát `onComplete()` mà không có `onNext`.
- Publisher lỗi ngay từ đầu phát `onError()` mà không có `onNext`.
- Publisher phát một số phần tử rồi lỗi thì không phát thêm phần tử sau lỗi.
- `onErrorResume` tạo kết quả dự phòng downstream và kết thúc đúng theo Publisher dự phòng.
- `retry` thực hiện subscription mới theo số lần thử được cấu hình.
- Khi `take(n)` đủ số phần tử, upstream nhận cancellation và downstream hoàn tất.

## 9. Cách chẩn đoán lỗi vi phạm terminal

Nếu log cho thấy một phần tử được phát sau `onComplete()` hoặc `onError()`, hãy kiểm tra Publisher tùy chỉnh, adapter callback và cách đồng bộ hóa giữa các thread. Một Publisher tự triển khai có thể phát terminal quá sớm, phát tín hiệu cạnh tranh hoặc tiếp tục gọi Subscriber sau khi subscription đã kết thúc.

Nếu Subscriber nhận hai terminal signals trên cùng subscription, hãy tìm nhánh lỗi và nhánh hoàn tất đang cùng phát tín hiệu. Ví dụ, một callback có thể gọi `onError` trong khi một callback khác gọi `onComplete` mà không có cơ chế tuần tự hóa hoặc trạng thái kết thúc dùng chung.

Nếu log chỉ ghi nhận `cancel()` mà không có `onComplete()`, điều đó thường là hành vi bình thường. Hủy là yêu cầu ngừng nhận dữ liệu; nó không phải một terminal callback gửi đến Subscriber.

Một cách đọc log hữu ích là ghép các tín hiệu theo từng subscription:

~~~text
onSubscribe
request(2)
onNext(A)
onNext(B)
onComplete
~~~

Nếu thấy `onNext(C)` sau `onComplete`, Publisher đã vi phạm hợp đồng. Nếu thấy `cancel` nhưng không có terminal callback, cần kiểm tra xem tầng nguồn có dừng công việc và giải phóng tài nguyên hay không, thay vì chờ một `onComplete` không bắt buộc.

Trong ứng dụng Java, việc tuân thủ ranh giới terminal giúp các pipeline `Mono` và `Flux` có vòng đời rõ ràng, tránh phát dữ liệu muộn, quản lý tài nguyên đúng lúc và xử lý lỗi nhất quán. Đây là điều kiện nền tảng để xây dựng các luồng bất đồng bộ đáng tin cậy bằng Reactive Streams và Project Reactor.

