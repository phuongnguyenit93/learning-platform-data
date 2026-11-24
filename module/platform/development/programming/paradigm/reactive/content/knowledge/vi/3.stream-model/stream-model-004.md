# Luồng hữu hạn, vô hạn, rỗng và không kết thúc

Trong **REACTIVE_PROGRAMMING**, mô hình luồng giúp ta mô tả dữ liệu được phát theo thời gian, cách một `Publisher` kết thúc và cách consumer kiểm soát vòng đời đăng ký. Reactive Streams cung cấp hợp đồng `Publisher–Subscriber` cùng cơ chế backpressure; Reactor hiện thực các khái niệm đó qua `Mono` và `Flux`. Vì vậy, khi thiết kế pipeline, cần phân biệt một nguồn sẽ hoàn tất, một nguồn có thể phát mãi, một nguồn hoàn tất mà không có dữ liệu và một nguồn không phát bất kỳ tín hiệu nào.

Những khác biệt này ảnh hưởng trực tiếp đến việc ghép toán tử, xử lý trường hợp không có kết quả, giới hạn tài nguyên và kiểm thử pipeline.

## 1. Vòng đời tín hiệu của một Publisher

Sau khi Subscriber đăng ký, Publisher gọi `onSubscribe` để cung cấp `Subscription`. Tiếp đó Publisher có thể phát không hoặc nhiều phần tử qua `onNext`, rồi kết thúc bằng đúng một tín hiệu đầu cuối: `onComplete` hoặc `onError`.

```text
onSubscribe
    |
    +---- onNext (0..n lần) ----+
    |                           |
    +---------------------------+
                                |
                    +-----------+-----------+
                    |                       |
                onComplete               onError
```

`onComplete` biểu thị nguồn đã phát xong bình thường. `onError` biểu thị nguồn kết thúc do lỗi. Sau một trong hai tín hiệu này, Publisher không được phát thêm `onNext` hay một tín hiệu kết thúc khác cho cùng subscription. Subscriber có thể gọi `request(n)` để yêu cầu dữ liệu và gọi `cancel()` để hủy đăng ký trước khi nguồn kết thúc. Hủy đăng ký là tín hiệu điều khiển từ Subscriber, không phải `onComplete`.

Có thể phân loại luồng dựa trên số phần tử và khả năng kết thúc:

| Loại luồng | Dữ liệu | Tín hiệu kết thúc bình thường | Ví dụ trong Reactor |
|---|---|---|---|
| Hữu hạn | Có số phần tử hữu hạn, có thể bằng 0 | `onComplete` sau phần tử cuối | `Flux.range(1, 3)` |
| Vô hạn | Có thể tiếp tục phát phần tử không giới hạn | Không có điểm hoàn tất tự nhiên | `Flux.interval(...)` |
| Rỗng | Không phát `onNext` | `onComplete` ngay | `Flux.empty()`, `Mono.empty()` |
| Không kết thúc (`never`) | Không phát `onNext` | Không phát `onComplete` hoặc `onError` | `Flux.never()`, `Mono.never()` |

Một nguồn vô hạn vẫn có thể bị hủy hoặc kết thúc do lỗi. Từ “vô hạn” mô tả việc nguồn không có điểm hoàn tất tự nhiên trong hoạt động bình thường. `never` là trường hợp cụ thể hơn: nguồn không phát dữ liệu và cũng không phát tín hiệu kết thúc.

## 2. Luồng hữu hạn

Luồng hữu hạn phát một số lượng phần tử xác định rồi hoàn tất. Đây là dạng thường gặp khi đọc một danh sách, kết quả truy vấn, một trang dữ liệu hoặc một tập bản ghi đã có giới hạn.

```java
Flux<Integer> numbers = Flux.range(1, 3);

numbers.subscribe(
    value -> System.out.println("value = " + value),
    error -> System.err.println("error = " + error.getMessage()),
    () -> System.out.println("completed")
);
```

Kết quả theo thứ tự là `1`, `2`, `3`, sau đó là `completed`. `Flux.range(1, 3)` phát ba phần tử và gọi `onComplete`. Một nguồn hữu hạn cũng có thể phát không phần tử nào; khi đó nó chính là một luồng rỗng.

`Mono<T>` cũng là Publisher hữu hạn với tối đa một phần tử. Nó có thể phát một giá trị rồi hoàn tất, hoặc hoàn tất ngay mà không phát giá trị. Vì vậy, `Mono` không đồng nghĩa với “chắc chắn có một kết quả”.

```java
Mono<String> found = Mono.just("Reactive Streams");
Mono<String> missing = Mono.empty();
```

Luồng hữu hạn phù hợp với các phép biến đổi cần biết thời điểm hoàn tất, chẳng hạn `collectList`, `reduce` hoặc `then`. Với nguồn có khả năng không hoàn tất, các phép toán chờ toàn bộ luồng như `collectList` sẽ không tạo ra kết quả cho đến khi nhận được tín hiệu kết thúc.

## 3. Luồng vô hạn

Luồng vô hạn có thể tiếp tục phát dữ liệu mà không có điểm hoàn tất tự nhiên. Các nguồn sự kiện, dữ liệu cảm biến, thông điệp từ broker hoặc nhịp thời gian định kỳ thường có hình dạng này.

```java
Flux<Long> ticks = Flux.interval(Duration.ofSeconds(1));

ticks.subscribe(tick -> System.out.println("tick = " + tick));
```

`Flux.interval` phát các giá trị `Long` tăng dần theo chu kỳ. Nếu không có thao tác giới hạn hoặc hủy đăng ký, subscription tiếp tục tồn tại và không nhận `onComplete` từ nguồn này.

Khi consumer chỉ cần một số lượng phần tử nhất định, có thể giới hạn luồng bằng `take`:

```java
Flux<Long> firstFiveTicks = Flux.interval(Duration.ofSeconds(1))
    .take(5);
```

`take(5)` cho downstream nhận tối đa năm phần tử. Khi đã nhận đủ, toán tử hoàn tất downstream và hủy subscription upstream để nguồn không tiếp tục phát dữ liệu cho pipeline đó. Nhờ vậy, một nguồn vốn vô hạn có thể tạo thành luồng hữu hạn ở phía sau toán tử.

Một số toán tử khác như `take(Duration)` hoặc `takeUntil` cũng có thể giới hạn thời gian hay điều kiện nhận dữ liệu. Cần chọn điều kiện phù hợp với nghiệp vụ: giới hạn số phần tử, giới hạn thời gian và điều kiện dừng mang ý nghĩa khác nhau.

Backpressure và giới hạn luồng giải quyết hai vấn đề khác nhau. Backpressure điều tiết số phần tử downstream yêu cầu thông qua `request(n)`; nó không tự biến nguồn vô hạn thành nguồn hữu hạn. Muốn pipeline kết thúc, cần một điều kiện kết thúc như `take`, tín hiệu từ nguồn, lỗi hoặc thao tác hủy subscription.

## 4. Luồng rỗng

Luồng rỗng không phát phần tử nào nhưng hoàn tất bình thường. Trong Reactor, `Flux.empty()` và `Mono.empty()` biểu diễn trường hợp này.

```java
Mono<String> username = Mono.empty();

username
    .doOnNext(value -> System.out.println("username = " + value))
    .doOnSuccess(value -> System.out.println("lookup completed"))
    .subscribe();
```

Không có `onNext` nào được phát ra, nhưng Publisher vẫn gửi `onComplete`. Với `Mono`, callback `doOnSuccess` được gọi khi Mono hoàn tất thành công; giá trị truyền vào callback là `null` nếu Mono rỗng. Điều đó không có nghĩa Reactor phát một phần tử `null`: Reactive Streams không cho phép `null` làm phần tử dữ liệu.

Luồng rỗng hữu ích khi một truy vấn không tìm thấy bản ghi, một điều kiện lọc loại bỏ toàn bộ phần tử hoặc một thao tác bất đồng bộ hoàn tất mà không cần trả dữ liệu. Khi muốn thay thế trường hợp rỗng bằng giá trị mặc định, có thể dùng `defaultIfEmpty` hoặc `switchIfEmpty`:

```java
Mono<String> displayName = Mono.<String>empty()
    .defaultIfEmpty("Khách vãng lai");

Mono<String> profile = Mono.<String>empty()
    .switchIfEmpty(loadGuestProfile());
```

`defaultIfEmpty` phát một giá trị thay thế khi nguồn hoàn tất mà không có phần tử. `switchIfEmpty` đăng ký Publisher dự phòng trong cùng trường hợp. Cả hai đều cần nguồn phát tín hiệu hoàn tất để xác định rằng luồng không có dữ liệu.

Không nên nhầm luồng rỗng với `null`, chuỗi rỗng hoặc một luồng lỗi. `Mono.empty()` là một Publisher hợp lệ có kết quả “không có phần tử”; `Mono.just("")` có một phần tử là chuỗi rỗng; còn `Mono.error(...)` kết thúc bằng `onError`.

## 5. Luồng không kết thúc (`never`)

Luồng `never` không phát phần tử và cũng không phát tín hiệu kết thúc. Trong Reactor, có thể biểu diễn bằng `Mono.never()` hoặc `Flux.never()`.

```java
Mono<String> pending = Mono.never();
```

Sau khi Subscriber đăng ký, subscription vẫn mở cho đến khi bị hủy hoặc chịu tác động từ một thành phần bên ngoài. Không có `onNext`, `onComplete` hay `onError` tự phát. Đây là khác biệt quan trọng so với `Mono.empty()`, vốn hoàn tất ngay lập tức.

Vì `never` không hoàn tất, các toán tử thay thế khi rỗng không được kích hoạt:

```java
Mono<String> result = Mono.<String>never()
    .switchIfEmpty(Mono.just("Giá trị dự phòng"));
```

`result` không phát giá trị dự phòng. `switchIfEmpty` đang chờ `onComplete` để xác nhận nguồn rỗng, nhưng `never` không gửi tín hiệu đó. Tương tự, `collectList`, `then` và các thao tác chờ hoàn tất cũng không tự tạo kết quả từ một nguồn `never`.

Trong ứng dụng thực tế, `never` thường hữu ích để mô hình hóa một nguồn chưa phát tín hiệu hoặc để kiểm thử hành vi của pipeline khi không có tín hiệu đầu vào. Nếu dùng trong luồng nghiệp vụ, cần có cơ chế quản lý vòng đời rõ ràng, ví dụ `timeout` để phát lỗi khi chờ quá lâu hoặc `takeUntil` để dừng khi có điều kiện bên ngoài. Nếu không, các tài nguyên gắn với subscription có thể bị giữ lâu hơn dự kiến.

## 6. Phân biệt các trường hợp thường bị nhầm

| Trường hợp | Có `onNext`? | Có tín hiệu kết thúc? | `switchIfEmpty` có chạy? |
|---|---:|---|---:|
| `Flux.range(1, 3)` | Có | `onComplete` sau ba phần tử | Không |
| `Flux.empty()` | Không | `onComplete` ngay | Có |
| `Flux.never()` | Không | Không | Không |
| `Flux.error(error)` | Không | `onError` | Không |
| `Flux.interval(...).take(3)` | Có | `onComplete` sau ba phần tử | Không |

Hai câu hỏi giúp xác định đúng hành vi là: nguồn có phát phần tử không, và nguồn có gửi tín hiệu kết thúc không? Chỉ nhìn vào việc “chưa thấy dữ liệu” thì chưa thể kết luận nguồn rỗng. Nguồn có thể đang chờ, có thể phát dữ liệu trong tương lai, hoặc có thể đã hoàn tất mà không có dữ liệu.

`onError` cũng là một tín hiệu kết thúc, nhưng không phải hoàn tất rỗng. Các toán tử `switchIfEmpty` và `defaultIfEmpty` xử lý trường hợp `onComplete` không có phần tử; chúng không biến lỗi thành giá trị mặc định. Muốn xử lý lỗi, cần các toán tử như `onErrorResume` hoặc `onErrorReturn` theo chính sách nghiệp vụ.

## 7. Kiểm thử từng loại luồng với StepVerifier

`StepVerifier` của Reactor Test cho phép mô tả chuỗi tín hiệu mong đợi. Với luồng hữu hạn và rỗng, cần xác minh cả dữ liệu lẫn tín hiệu hoàn tất:

```java
StepVerifier.create(Flux.range(1, 3))
    .expectNext(1, 2, 3)
    .verifyComplete();

StepVerifier.create(Flux.empty())
    .verifyComplete();
```

Với `never`, bài kiểm thử cần xác nhận không có tín hiệu trong khoảng quan sát rồi chủ động hủy subscription:

```java
StepVerifier.create(Flux.never())
    .expectSubscription()
    .expectNoEvent(Duration.ofMillis(100))
    .thenCancel()
    .verify();
```

Với nguồn định kỳ, có thể dùng thời gian ảo để kiểm thử mà không phải chờ đồng hồ thực:

```java
StepVerifier.withVirtualTime(
        () -> Flux.interval(Duration.ofSeconds(1)).take(3)
    )
    .expectSubscription()
    .thenAwait(Duration.ofSeconds(3))
    .expectNext(0L, 1L, 2L)
    .verifyComplete();
```

Kiểm thử thời gian ảo đặc biệt hữu ích khi pipeline có `interval`, `delayElements`, `timeout` hoặc các toán tử dựa trên scheduler. Hãy xác minh cả kết quả lẫn cách subscription kết thúc; một bài kiểm thử chỉ kiểm tra các phần tử phát ra có thể bỏ sót lỗi pipeline không hoàn tất hoặc không hủy nguồn đúng lúc.

## 8. Chọn mô hình luồng theo nhu cầu

- Dùng luồng hữu hạn khi nguồn có điểm kết thúc xác định, chẳng hạn danh sách, trang kết quả hoặc tập bản ghi.
- Dùng luồng vô hạn khi xử lý sự kiện liên tục; xác định rõ điều kiện hủy, giới hạn thời gian hoặc phạm vi subscription.
- Dùng luồng rỗng khi thao tác hoàn tất hợp lệ nhưng không có dữ liệu để phát; dùng `defaultIfEmpty` hoặc `switchIfEmpty` nếu nghiệp vụ yêu cầu nhánh thay thế.
- Dùng `never` khi chủ đích là không phát tín hiệu; trong kiểm thử, luôn đặt thời gian quan sát và hủy subscription để bài kiểm thử kết thúc.

Khi đọc một pipeline Reactor, hãy kiểm tra nơi phát `onComplete` hoặc `onError`, các toán tử có thể giới hạn luồng và nơi thực hiện `cancel`. Nắm rõ ba điểm này giúp dự đoán được pipeline sẽ trả dữ liệu, hoàn tất rỗng, tiếp tục chạy hay chờ vô thời hạn.
