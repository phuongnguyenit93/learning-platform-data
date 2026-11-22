# Điều khiển request ban đầu và thenRequest khi kiểm thử Reactor với StepVerifier

## 1. Mục tiêu của bài học

Khi kiểm thử `Mono` hoặc `Flux` trong Reactor, ta thường viết:

~~~java
StepVerifier.create(Flux.just(1, 2, 3))
    .expectNext(1, 2, 3)
    .verifyComplete();
~~~

Ví dụ này xác nhận chuỗi phát các giá trị đúng rồi hoàn tất. Nhưng nó chưa kiểm tra cách Publisher phản ứng khi Subscriber **chỉ yêu cầu một số lượng phần tử giới hạn**.

Đối với Reactive Streams, Subscriber không thụ động nhận mọi giá trị. Sau `onSubscribe`, Subscriber điều khiển tốc độ tiêu thụ bằng `Subscription.request(n)`. Số lượng item còn được phép phát gọi là **outstanding demand**. Nhu cầu kiểm thử này đặc biệt quan trọng với nguồn dữ liệu lớn, phân trang, stream, queue, backpressure, operator prefetch hoặc một Publisher do nhóm tự triển khai.

`StepVerifier` trong module `reactor-test` cho phép:

- Thiết lập demand ban đầu qua `StepVerifier.create(publisher, initialRequest)`.
- Cấu hình tương đương bằng `StepVerifierOptions.initialRequest(long)`.
- Chủ động xin thêm item tại từng điểm bằng `thenRequest(n)`.
- Khẳng định item xuất hiện đúng sau những lần request với `expectNext` / `expectNextCount`.
- Phân biệt tín hiệu `onNext` với terminal `onComplete`, `onError` và `cancel`.
- Phát hiện các kịch bản test tự yêu cầu ít item hơn số item đang mong đợi qua kiểm tra under-requesting.
- Quan sát downstream demand và upstream request khác nhau khi có operator làm thay đổi request.

**Ý chính:** Điều khiển demand giúp kiểm thử cơ chế phối hợp Publisher–Subscriber, không chỉ kiểm thử nội dung của list.

## 2. Nền tảng Reactive Streams: ai yêu cầu dữ liệu?

Đối thoại cơ bản:

~~~text
Subscriber                    Publisher
    |                             |
    |------ subscribe() --------->|
    |<----- onSubscribe(sub) ------|
    |                             |
    |------ sub.request(2) ------>|
    |<----- onNext(item1) ---------|
    |<----- onNext(item2) ---------|
    |                             |
    |------ sub.request(3) ------>|
    |<----- onNext(item3) ---------|
    |<----- onNext(item4) ---------|
    |<----- onNext(item5) ---------|
    |<----- onComplete() ----------|
~~~

Các quy tắc:

1. `onSubscribe` cung cấp `Subscription` cho Subscriber.
2. `request(n)` với `n > 0` cấp quyền phát tối đa n tín hiệu `onNext` tiếp theo, tính trên demand còn lại.
3. Nếu Subscriber request thêm, nhu cầu được **cộng dồn**, không thay thế demand cũ.
4. `onNext` tiêu thụ một đơn vị demand; `onComplete` và `onError` là tín hiệu kết thúc, không phải item và không tiêu thụ demand.
5. `cancel()` yêu cầu dừng subscription; sau khi hủy không được phát `onNext` cho subscriber đó theo hợp đồng.
6. `Long.MAX_VALUE` được dùng để biểu thị demand không giới hạn.
7. `request(0)` hoặc số âm không phải request dữ liệu hợp lệ theo Reactive Streams; đừng dùng chúng như một cách "tạm dừng".

### Công thức theo dõi outstanding demand

Khi không có trường hợp unbounded hoặc over-request:

~~~text
outstanding demand mới
  = outstanding demand cũ
  + số lượng request được thêm
  - số onNext đã phát
~~~

Ví dụ:

| Thao tác | Outstanding demand |
| --- | ---: |
| Subscribe với initialRequest = 0 | 0 |
| request(2) | 2 |
| Publisher phát item A | 1 |
| request(3) | 4 |
| Publisher phát item B | 3 |
| Publisher phát item C | 2 |

Khi số đếm được cộng vượt ngưỡng, Reactor dùng phép cộng bão hòa tại `Long.MAX_VALUE` chứ không để overflow biến demand thành số âm.

**Giới hạn quan trọng:** Công thức này mô tả demand nhìn tại một Subscription cụ thể. Khi có `buffer`, `flatMap`, `publishOn` hoặc `limitRate`, upstream có thể thấy request khác với downstream vì các operator biến đổi nhu cầu và prefetch.

## 3. StepVerifier hoạt động như một Subscriber kiểm thử

`StepVerifier` là API xây dựng một "kịch bản tín hiệu" rồi subscribe vào Publisher để xác nhận. Ví dụ:

~~~java
Flux<Integer> source = Flux.just(10, 20, 30);

StepVerifier.create(source)
    .expectSubscription()
    .expectNext(10)
    .expectNext(20, 30)
    .verifyComplete();
~~~

Cần phân biệt hai thời điểm:

- **Assembly:** gọi `create`, `expectNext`, `thenRequest` để khai báo kịch bản.
- **Verification:** gọi `verify()`, `verifyComplete()` hoặc một API verify tương tự để thực sự subscribe và chạy kiểm thử.

Nếu chỉ xây dựng kịch bản mà không gọi verify, test có thể kết thúc mà chưa kiểm tra bất kỳ tín hiệu nào.

### Default demand là bao nhiêu?

Theo `StepVerifierOptions` Javadoc, overload:

~~~java
StepVerifier.create(source)
~~~

mặc định tạo initial request **không giới hạn**, tương đương `Long.MAX_VALUE`.

Đây là lý do test đơn giản thường nhận ngay mọi phần tử. Nếu chỉ muốn xác nhận values, default này hoàn toàn hợp lý. Nhưng nếu muốn kiểm tra từng đợt request, phải **chủ động cấu hình initial demand**.

### Vì sao thenRequest sau default unbounded không hữu ích?

~~~java
StepVerifier.create(source)
    .expectNext(10)
    .thenRequest(1)
    .expectNext(20, 30)
    .verifyComplete();
~~~

Kịch bản trên không kiểm tra "chỉ phát item sau thenRequest(1)": Subscriber đã cấp demand vô hạn ngay từ đầu. `thenRequest(1)` không làm số demand còn lại giảm hay "bật chế độ giới hạn".

Muốn khẳng định request được chia thành từng đợt, dùng:

~~~java
StepVerifier.create(source, 0)
    .expectSubscription()
    .thenRequest(1)
    .expectNext(10)
    .thenRequest(2)
    .expectNext(20, 30)
    .verifyComplete();
~~~

## 4. Điều khiển initialRequest bằng create(Publisher, long)

Cú pháp:

~~~java
StepVerifier.create(publisher, initialRequest)
~~~

Overload thứ hai chọn số lượng item được request ban đầu khi subscription bắt đầu.

### Bắt đầu không request gì

~~~java
Flux<Integer> source = Flux.range(1, 5);

StepVerifier.create(source, 0)
    .expectSubscription()
    .thenRequest(2)
    .expectNext(1, 2)
    .thenRequest(3)
    .expectNext(3, 4, 5)
    .verifyComplete();
~~~

Diễn giải:

1. `create(source, 0)`: ngay lúc subscribe chưa xin item nào.
2. `expectSubscription()`: xác nhận Subscriber nhận `onSubscribe`.
3. `thenRequest(2)`: gọi `request(2)`, source được phép phát tối đa 2 item.
4. `expectNext(1, 2)`: xác nhận đúng hai item đầu.
5. `thenRequest(3)`: yêu cầu thêm 3 item.
6. `expectNext(3, 4, 5)`: xác nhận ba item còn lại.
7. `verifyComplete()`: mong nguồn kết thúc thành công.

Đây là tình huống nền tảng để học `thenRequest`. `Flux.range` là Publisher cold hỗ trợ backpressure, nên kết quả có tính xác định và không cần sleep hoặc network.

### Bắt đầu với một lượng demand dương

~~~java
StepVerifier.create(Flux.range(1, 4), 2)
    .expectSubscription()
    .expectNext(1, 2)
    .thenRequest(2)
    .expectNext(3, 4)
    .verifyComplete();
~~~

Ở đây ngay từ đầu Subscriber đã request 2, nên hai phần tử đầu được phát mà không cần gọi `thenRequest`. Sau đó thêm 2 để nhận hai phần tử còn lại.

### Bắt đầu bằng demand không giới hạn

~~~java
StepVerifier.create(Flux.range(1, 4), Long.MAX_VALUE)
    .expectNext(1, 2, 3, 4)
    .verifyComplete();
~~~

Dùng cách này khi mục tiêu chỉ là dữ liệu và kết thúc; không dùng để chứng minh backpressure từng đợt.

### So sánh

| Lệnh | Initial demand | Tình huống |
| --- | ---: | --- |
| `StepVerifier.create(source)` | Long.MAX_VALUE | Test value/error/complete thông thường |
| `StepVerifier.create(source, 0)` | 0 | Chủ động xin từng đợt bằng thenRequest |
| `StepVerifier.create(source, 2)` | 2 | Bắt đầu với một hạn mức nhỏ |
| `StepVerifier.create(source, Long.MAX_VALUE)` | Không giới hạn | Xác định rõ ý định unbounded |

Không dùng request âm hoặc giá trị 0 trong `thenRequest`. `initialRequest(0)` là cấu hình hợp lệ của verifier, **không đồng nghĩa** với việc phát lệnh `Subscription.request(0)` trái quy tắc.

## 5. StepVerifierOptions.initialRequest và các option hữu ích

Ngoài overload nhận số trực tiếp, có thể dùng `StepVerifierOptions`:

~~~java
import reactor.test.StepVerifier;
import reactor.test.StepVerifierOptions;

StepVerifierOptions options = StepVerifierOptions.create()
    .initialRequest(0)
    .scenarioName("Flux numbers - phased demand")
    .checkUnderRequesting(true);

StepVerifier.create(Flux.range(1, 3), options)
    .expectSubscription()
    .thenRequest(1)
    .expectNext(1)
    .thenRequest(2)
    .expectNext(2, 3)
    .verifyComplete();
~~~

Các option liên quan:

| Option | Ý nghĩa |
| --- | --- |
| `initialRequest(long)` | Chỉ định demand lúc subscription |
| `scenarioName(String)` | Gắn tên cho toàn bộ kịch bản để lỗi dễ đọc hơn |
| `checkUnderRequesting(boolean)` | Bật/tắt cảnh báo test đang expect nhiều onNext hơn demand đã cấp |
| `withInitialContext(Context)` | Cung cấp Reactor Context ban đầu khi subscribe |
| `virtualTimeSchedulerSupplier(...)` | Cấu hình scheduler cho kiểm thử virtual time nâng cao |

`checkUnderRequesting` **mặc định là true**. Nó giúp phát hiện một kịch bản tự khóa vì chưa request đủ số item mà các bước `expectNext` đang chờ.

**Không nên tắt mặc định này** chỉ để test "chạy qua". Nếu một kịch bản chờ ba giá trị nhưng chỉ request hai, hãy thêm `thenRequest` hợp lý hoặc sửa kỳ vọng.

### Ví dụ thường bị lỗi under-requesting

~~~java
// MINH HỌA SAI: kịch bản này yêu cầu 2 nhưng muốn 3 item.
StepVerifier.create(Flux.range(1, 3), 0)
    .thenRequest(2)
    .expectNext(1, 2, 3)
    .verifyComplete();
~~~

StepVerifier có thể cảnh báo thiếu request khi thiết lập hoặc chạy kịch bản, tùy dạng bước. Đừng hiểu lỗi này là publisher không có backpressure: **chính test chưa cấp đủ demand**.

Cách sửa:

~~~java
StepVerifier.create(Flux.range(1, 3), 0)
    .thenRequest(2)
    .expectNext(1, 2)
    .thenRequest(1)
    .expectNext(3)
    .verifyComplete();
~~~

## 6. thenRequest(n) chính xác làm gì?

`thenRequest(n)` là bước hành động của StepVerifier: yêu cầu thêm n phần tử từ Subscription trong lúc kiểm thử.

~~~java
.thenRequest(5)
~~~

tương đương về ý nghĩa với một Subscriber chủ động gọi `subscription.request(5)`.

### thenRequest cộng dồn, không đặt lại hạn mức

Giả sử ban đầu request 2, mới nhận 1 item, sau đó `thenRequest(3)`:

~~~text
Ban đầu            : request(2)   -> outstanding = 2
Phát 1 item         : onNext      -> outstanding = 1
Thêm yêu cầu        : request(3)   -> outstanding = 4
Phát 4 item tiếp    : onNext x4   -> outstanding = 0
~~~

`thenRequest(3)` **không có nghĩa** "giờ chỉ cho phép tối đa 3 item"; nó thêm 3 vào phần demand còn lại.

### Không dùng thenRequest như một thao tác điều khiển thời gian

`thenRequest` không phải `Thread.sleep` hoặc “thực thi sau n mili giây”. Kịch bản StepVerifier chạy theo thứ tự các bước và gửi request đúng lúc đó.

Nếu cần điều khiển thời gian:

- `thenAwait(Duration)`: chờ/tiến thời gian.
- `expectNoEvent(Duration)`: xác nhận không quan sát được event trong thời lượng đã cho.
- `withVirtualTime(...)`: kiểm thử operator thời gian bằng virtual scheduler.

Với test chỉ kiểm tra demand của nguồn synchronous như `Flux.range`, **không cần virtual time**.

### Thứ tự request trước expectNext là quan trọng

~~~java
StepVerifier.create(Flux.range(1, 2), 0)
    .expectSubscription()
    .thenRequest(1)
    .expectNext(1)
    .thenRequest(1)
    .expectNext(2)
    .verifyComplete();
~~~

Nếu đặt `expectNext(1)` trước khi xin request đầu tiên, verifier không có dữ liệu để tiến tới bước `thenRequest` nằm phía sau; test có thể thất bại do under-requesting hoặc bị kẹt nếu tắt kiểm tra an toàn.

## 7. expectSubscription và expectNoEvent khi initialRequest = 0

Một subscription cũng là một event được StepVerifier quan sát, dù nó không phải `onNext`. Vì vậy:

~~~java
// Thường sai: expectNoEvent ngay bước đầu có thể thấy onSubscribe.
StepVerifier.create(Flux.range(1, 3), 0)
    .expectNoEvent(Duration.ofMillis(30))
    .thenRequest(3)
    .expectNext(1, 2, 3)
    .verifyComplete();
~~~

Kịch bản chuẩn hơn:

~~~java
StepVerifier.create(Flux.range(1, 3), 0)
    .expectSubscription()
    .expectNoEvent(Duration.ofMillis(30))
    .thenRequest(3)
    .expectNext(1, 2, 3)
    .verifyComplete();
~~~

Ở đây:

- `expectSubscription` khẳng định `onSubscribe` đã xảy ra.
- Chưa có demand nên một Publisher tuân thủ Reactive Streams không được phát `onNext`.
- `expectNoEvent` có thể được dùng để quan sát rằng chưa có event nào khác trong 30 ms.
- Sau `thenRequest(3)`, nguồn phát ba giá trị.

**Không khái quát hóa rằng mọi Publisher đều phải im lặng khi initial demand bằng 0.** Một nguồn `Mono.empty()` có thể phát `onComplete`, và `Mono.error(error)` có thể phát `onError` khi chưa có request. Các tín hiệu terminal không bị ràng buộc bởi onNext demand.

Vì `expectNoEvent(Duration)` dùng real time trong test thông thường, nó làm test chậm và có thể chịu ảnh hưởng scheduler. Chỉ dùng khi thực sự cần chứng minh “không có tín hiệu”. Với nguồn synchronous deterministic, `thenRequest` kết hợp các kỳ vọng là phần cốt lõi.

## 8. onNext và terminal signal không cùng quy tắc demand

So sánh các trường hợp:

~~~java
Flux<Integer> values = Flux.just(1, 2);
Mono<Integer> empty = Mono.empty();
Mono<Integer> failed = Mono.error(
    new IllegalStateException("boom")
);
~~~

| Source | Initial demand 0 | Kết luận |
| --- | --- | --- |
| `Flux.just(1, 2)` | Không được phát `onNext` trước request | onNext bị backpressure điều tiết |
| `Mono.just(1)` | Giá trị cần request mới phát | onNext cần demand |
| `Mono.empty()` | Có thể complete ngay | Complete không tiêu thụ demand |
| `Mono.error(e)` | Có thể error ngay | Error không tiêu thụ demand |

Ví dụ kiểm thử Mono rỗng:

~~~java
StepVerifier.create(Mono.<Integer>empty(), 0)
    .expectSubscription()
    .verifyComplete();
~~~

Ví dụ kiểm thử lỗi:

~~~java
StepVerifier.create(
        Mono.<Integer>error(new IllegalStateException("boom")), 0
    )
    .expectSubscription()
    .expectErrorMessage("boom")
    .verify();
~~~

`thenRequest` dùng để xin thêm các giá trị `onNext`, không phải điều kiện bắt buộc để Publisher được phép complete hoặc error.

### Mono thường chỉ cần một request

~~~java
StepVerifier.create(Mono.just("OK"), 0)
    .expectSubscription()
    .thenRequest(1)
    .expectNext("OK")
    .verifyComplete();
~~~

Nếu Mono hoàn tất rỗng thì request(1) cũng không làm nó “tạo ra” một phần tử.

## 9. expectNextCount, assertNext và test dữ liệu không biết trước toàn bộ

Với một Publisher phát nhiều item, không nhất thiết phải viết tất cả giá trị bằng `expectNext`:

~~~java
StepVerifier.create(Flux.range(1, 10), 0)
    .expectSubscription()
    .thenRequest(4)
    .expectNextCount(4)
    .thenRequest(6)
    .expectNextCount(6)
    .verifyComplete();
~~~

Kịch bản trên xác nhận số lượng theo từng đợt, nhưng không kiểm tra từng giá trị. Khi thứ tự và nội dung quan trọng, nên kết hợp:

~~~java
StepVerifier.create(Flux.range(10, 5), 0)
    .thenRequest(2)
    .expectNext(10, 11)
    .thenRequest(1)
    .assertNext(value -> assertEquals(12, value))
    .thenRequest(2)
    .expectNext(13, 14)
    .verifyComplete();
~~~

Lệnh `assertEquals` trong snippet thuộc `org.junit.jupiter.api.Assertions`. Nó chỉ mang ý nghĩa khi có import JUnit tương ứng.

Các lựa chọn khác:

- `expectNextMatches(predicate)`: kiểm tra một phần tử theo điều kiện.
- `assertNext(consumer)`: dùng assertion phong phú với phần tử.
- `expectNextSequence(iterable)`: so sánh chuỗi các phần tử.
- `thenConsumeWhile(predicate)`: tiêu thụ thêm các phần tử thỏa điều kiện.

Với bất kỳ lựa chọn nào, vẫn phải tính đủ demand trước các kỳ vọng onNext. `expectNextCount(10)` không tự request thêm 10 item.

## 10. Test Publisher phản ứng với request bằng doOnRequest

Reactor cung cấp `doOnRequest` để quan sát upstream request trong pipeline:

~~~java
AtomicLong requests = new AtomicLong();

Flux<Integer> source = Flux.range(1, 5)
    .doOnRequest(requests::addAndGet);

StepVerifier.create(source, 0)
    .expectSubscription()
    .then(() -> assertEquals(0L, requests.get()))
    .thenRequest(2)
    .expectNext(1, 2)
    .then(() -> assertEquals(2L, requests.get()))
    .thenRequest(3)
    .expectNext(3, 4, 5)
    .then(() -> assertEquals(5L, requests.get()))
    .verifyComplete();
~~~

Đây là test đơn giản, không có operator thay đổi nhu cầu giữa StepVerifier và `doOnRequest`, nên thấy các request tương ứng với tổng lượng 2 rồi 5.

### then(Runnable) dùng để làm gì?

`then(() -> ...)` cho phép thực hiện một tác vụ hoặc assertion đúng vị trí trong kịch bản, sau các bước trước đó đã được xử lý.

Ví dụ:

~~~java
.then(() -> assertEquals(2L, requests.get()))
~~~

Khác với `thenRequest(2)`:

- `thenRequest` gửi demand.
- `then(Runnable)` thực hiện code kiểm tra/điều khiển test.
- `thenCancel` hủy subscription.

Các method cùng bắt đầu bằng từ "then" nhưng ý nghĩa khác nhau; đừng nhầm.

### Không dùng phép cộng long naïve với demand unbounded

Ví dụ `requests.addAndGet(n)` phù hợp khi đang đo các request nhỏ và hữu hạn. Với `Long.MAX_VALUE` hoặc khi cộng vượt giới hạn, counter tự tạo có thể overflow. Để quan sát demand thực tế ở production, dùng metric/probe phù hợp thay vì cộng mù mọi giá trị long.

## 11. Operator có thể thay đổi số lượng request gửi upstream

Một điểm dễ hiểu sai: `StepVerifier.thenRequest(n)` gửi demand ở **đầu dưới cùng** của pipeline, nhưng source ở đầu trên không nhất thiết nhận cùng một n.

Ví dụ:

~~~java
Flux<List<Integer>> batches = Flux.range(1, 9)
    .buffer(3);

StepVerifier.create(batches, 0)
    .expectSubscription()
    .thenRequest(1)
    .expectNext(List.of(1, 2, 3))
    .thenRequest(1)
    .expectNext(List.of(4, 5, 6))
    .thenCancel()
    .verify();
~~~

Một item downstream ở đây là `List<Integer>` có ba phần tử. Khi downstream yêu cầu một list, `buffer(3)` cần request tương ứng ba item nguồn để tạo list đó.

Có thể quan sát:

~~~java
AtomicLong upstreamRequests = new AtomicLong();

Flux<List<Integer>> batches = Flux.range(1, 9)
    .doOnRequest(upstreamRequests::addAndGet)
    .buffer(3);

StepVerifier.create(batches, 0)
    .expectSubscription()
    .thenRequest(1)
    .expectNext(List.of(1, 2, 3))
    .then(() -> assertEquals(3L, upstreamRequests.get()))
    .thenRequest(1)
    .expectNext(List.of(4, 5, 6))
    .then(() -> assertEquals(6L, upstreamRequests.get()))
    .thenCancel()
    .verify();
~~~

**Vị trí của doOnRequest rất quan trọng:**

~~~text
StepVerifier request(1 List)
             |
             v
           buffer(3)
             |
             | request(3 Integer)
             v
          doOnRequest
             |
             v
      Flux.range(1, 9)
~~~

Nếu đặt `doOnRequest` sau `buffer(3)`, bạn sẽ quan sát request ở **phía downstream** của buffer, tức request(1 List), chứ không phải request(3 Integer).

### Những operator có thể reshape request

| Operator | Thay đổi cần lưu ý |
| --- | --- |
| `buffer(size)` | Một item downstream có thể cần nhiều item upstream |
| `limitRate(highTide)` | Chia request lớn thành nhiều đợt request nhỏ hơn |
| `publishOn(scheduler, prefetch)` | Có prefetch và queue giữa scheduler |
| `flatMap(mapper, concurrency, prefetch)` | Yêu cầu và buffer ở nhiều inner Publisher |
| `concatMap(mapper)` | Có cơ chế prefetch/queue phụ thuộc overload |
| `take(n)` | Giới hạn tổng số item, có thể cancel khi đã đủ |
| `onBackpressureBuffer` | Có buffer trung gian và chiến lược xử lý khi quá tải |

Không viết assertion rằng `thenRequest(2)` phải làm mọi source/DB client chính xác nhận `request(2)`. Hãy chọn tầng đo demand và hiểu operator nằm giữa.

## 12. thenRequest và limitRate

`limitRate` giúp chia demand lớn thành những đợt nhỏ hơn khi truyền upstream.

Ví dụ:

~~~java
Flux<Integer> source = Flux.range(1, 20)
    .limitRate(4);

StepVerifier.create(source, 0)
    .expectSubscription()
    .thenRequest(2)
    .expectNext(1, 2)
    .thenRequest(3)
    .expectNext(3, 4, 5)
    .thenCancel()
    .verify();
~~~

Test này kiểm chứng downstream nhận đúng 5 item sau tổng 5 demand. Nó **không** tự chứng minh upstream nhận chính xác các đợt 2 và 3. `limitRate(4)` có chính sách request lên source của riêng nó.

Nếu cần quan sát:

~~~java
Flux<Integer> observed = Flux.range(1, 20)
    .doOnRequest(n -> System.out.println("upstream request=" + n))
    .limitRate(4);
~~~

Hãy nhớ:

- Đây chỉ là logging minh họa, không phải stdout cố định cho mọi cấu hình.
- Prefetch/replenishment có thể thay đổi theo operator và phiên bản Reactor.
- Để test ít brittle, tập trung kiểm tra contract người dùng nhìn thấy (onNext, order, complete, cancel), sau đó thêm assertion nội bộ khi thông số đó thật sự là yêu cầu kỹ thuật.

## 13. Test hủy subscription sau một phần dữ liệu

Không phải mọi nguồn đều hoàn tất trong test. Với stream dài hoặc vô hạn, ta thường muốn:

1. Nhận một số lượng item có kiểm soát.
2. Cancel.
3. Xác nhận upstream nhận cancellation.

Ví dụ:

~~~java
AtomicBoolean cancelled = new AtomicBoolean(false);

Flux<Integer> source = Flux.range(1, 100)
    .doOnCancel(() -> cancelled.set(true));

StepVerifier.create(source, 0)
    .expectSubscription()
    .thenRequest(2)
    .expectNext(1, 2)
    .thenCancel()
    .verify();

assertTrue(cancelled.get());
~~~

`thenCancel()` là một bước kết thúc kịch bản: không cần `expectComplete()` nữa. Đây là lựa chọn đúng khi ta cố tình dừng sau một phần item.

### Vì sao expectComplete sẽ bị treo nếu không request đủ?

~~~java
// Minh họa sai: chỉ request 2/100 item nhưng lại mong source complete.
StepVerifier.create(Flux.range(1, 100), 0)
    .thenRequest(2)
    .expectNext(1, 2)
    .verifyComplete();
~~~

`Flux.range(1,100)` chưa thể phát hết 98 giá trị còn lại nên chưa thể hoàn tất một cách bình thường. Test có thể chờ không giới hạn nếu không đặt timeout.

Cách sửa tùy mục tiêu:

- Muốn consume toàn bộ: thêm `thenRequest(98)` và kiểm tra 98 item còn lại.
- Muốn kiểm tra hai item đầu: kết thúc bằng `thenCancel()`.
- Muốn test timeout: xây dựng kỳ vọng timeout tường minh.

## 14. Error signal có thể xuất hiện khi không còn demand

Giả sử một pipeline phát hai item rồi lỗi:

~~~java
Flux<Integer> source = Flux.concat(
    Flux.just(10, 20),
    Flux.error(new IllegalStateException("boom"))
);

StepVerifier.create(source, 0)
    .expectSubscription()
    .thenRequest(2)
    .expectNext(10, 20)
    .expectErrorMatches(error ->
        error instanceof IllegalStateException
            && "boom".equals(error.getMessage())
    )
    .verify();
~~~

Sau hai `onNext`, outstanding demand có thể về 0, nhưng nguồn vẫn được phép phát `onError`. Tín hiệu lỗi không phải item dữ liệu và không cần `thenRequest(1)` riêng.

Phân biệt:

- `expectError(...)`: xác nhận Publisher kết thúc bằng lỗi.
- `expectComplete()`: xác nhận kết thúc thành công.
- `thenCancel()`: tester chủ động hủy, không đòi terminal từ source.

**Không thay `expectError` bằng `onErrorComplete()` trong production chỉ để test xanh.** Việc nuốt lỗi làm sai contract nghiệp vụ.

## 15. Kiểm thử nguồn hot bằng TestPublisher

`reactor-test` còn có `TestPublisher` để chủ động kích hoạt tín hiệu dữ liệu trong test.

~~~java
TestPublisher<Integer> publisher = TestPublisher.create();

StepVerifier.create(publisher.flux(), 0)
    .expectSubscription()
    .then(() -> publisher
        .assertSubscribers()
        .assertMaxRequested(0))
    .thenRequest(1)
    .then(() -> publisher
        .assertMinRequested(1)
        .next(99)
        .complete())
    .expectNext(99)
    .verifyComplete();
~~~

Ý nghĩa:

- `TestPublisher.create()` tạo nguồn do test điều khiển.
- `assertSubscribers()` xác nhận có subscriber.
- `assertMaxRequested(0)` xác nhận lúc đầu subscriber chưa xin item nào.
- Sau `thenRequest(1)`, `assertMinRequested(1)` xác nhận có demand.
- `next(99)` và `complete()` phát tín hiệu cho subscriber.
- `expectNext(99)` và `verifyComplete()` xác nhận kết quả.

Các method như `assertMinRequested`, `assertMaxRequested` và `assertNoRequestOverflow` giúp quan sát state của TestPublisher.

### Không lẫn TestPublisher với nguồn production

TestPublisher thường là hot và được điều khiển bởi test. Nó không tự đảm bảo semantics cold/replay của repository hoặc HTTP client. Để kiểm thử một operator với nguồn có lỗi giao thức, `TestPublisher.createNoncompliant(Violation...)` có thể tạo Publisher cố ý vi phạm Reactive Streams, nhưng chỉ dùng cho kiểm thử resilience có chủ đích. Không dùng Publisher vi phạm trong ứng dụng thực tế.

Nếu phát `onNext` khi không có demand, đó là lỗi giao thức; `TestPublisher` có API ghi nhận request overflow, nhưng không được tắt kiểm tra chỉ để coi hành vi sai là hợp lệ.

## 16. under-requesting không giống upstream backpressure violation

Hai vấn đề dễ bị nhầm:

### Test thiếu request

~~~java
StepVerifier.create(Flux.range(1, 3), 0)
    .thenRequest(1)
    .expectNext(1, 2)
    .verifyComplete();
~~~

Bản thân verifier mong hai item nhưng chỉ cấp demand cho một. `checkUnderRequesting` giúp báo sai sót của kịch bản.

### Publisher phát vượt demand

Nếu Subscriber request(1) mà nguồn phát hai `onNext` trước request tiếp theo, Publisher có thể vi phạm Reactive Streams. Đây là lỗi của nguồn hoặc adapter, không phải do test yêu cầu quá ít.

Để phân biệt, kiểm tra:

- Kịch bản đã xin đủ demand cho các `expectNext` chưa?
- `doOnRequest` được đặt ở vị trí nào?
- Operator nào có prefetch/reshaping?
- Có nguồn custom hoặc adapter không tuân thủ giao thức không?
- Source có buffer và chính sách overflow được cấu hình không?

`StepVerifier` hữu ích, nhưng test values/thenRequest **không thay thế** việc kiểm tra đúng Reactive Streams specification cho một Publisher tự viết. Với thư viện Publisher custom, có thể bổ sung TCK và test backpressure/cancellation độc lập.

## 17. Virtual time và demand: hai trục độc lập

Có hai nguyên nhân thường khiến Publisher chưa phát item:

1. **Chưa có demand**: subscriber chưa gọi request(n) đủ.
2. **Chưa tới thời điểm phát**: nguồn bị delay, interval hoặc phụ thuộc scheduler.

`thenRequest(n)` giải quyết nguyên nhân thứ nhất. `thenAwait(duration)` và `withVirtualTime` giải quyết nguyên nhân thứ hai.

Ví dụ chỉ kiểm tra thời gian (không cần demand thủ công):

~~~java
StepVerifier.withVirtualTime(
        () -> Flux.interval(Duration.ofSeconds(1)).take(3))
    .expectSubscription()
    .thenAwait(Duration.ofSeconds(3))
    .expectNext(0L, 1L, 2L)
    .verifyComplete();
~~~

`withVirtualTime` nhận Supplier để tạo Publisher **sau** khi virtual scheduler được thiết lập; không tạo Flux.interval trước rồi chỉ return biến đã có.

Nếu kết hợp virtual time với manual demand:

~~~java
StepVerifier.withVirtualTime(
        () -> Flux.interval(Duration.ofSeconds(1)).take(2), 0)
    .expectSubscription()
    .thenRequest(2)
    .thenAwait(Duration.ofSeconds(2))
    .expectNext(0L, 1L)
    .verifyComplete();
~~~

Đặt `thenRequest(2)` trước khi advance virtual clock để `Flux.interval` không gặp thiếu demand ở tick đầu. Nếu cố tiến thời gian trong khi không có demand, Flux.interval có thể báo lỗi overflow/backpressure tùy nguồn và thời điểm.

Lưu ý: virtual time chỉ kiểm soát scheduler được hook phù hợp. Nó không biến network/database thật thành virtual I/O.

## 18. Kiểm thử Reactor không đồng nghĩa đo mọi tầng HTTP

Trong Spring WebFlux, một controller có thể trả:

~~~java
@GetMapping(
    path = "/events",
    produces = MediaType.APPLICATION_NDJSON_VALUE
)
public Flux<Event> stream() {
    return eventService.events();
}
~~~

Unit test StepVerifier có thể kiểm tra `eventService.events()` với initialRequest=0 và thenRequest từng đợt.

Nhưng kiểm thử StepVerifier không tự chứng minh:

- HTTP client gửi demand chính xác mỗi đợt theo mong đợi.
- Reactor Netty socket không buffer thêm bytes.
- JSON codec flush từng item ngay.
- Reverse proxy và browser nhận data ngay khi source phát.
- Database driver áp dụng cùng số request qua mọi operator.

Để kiểm thử HTTP, dùng `WebTestClient` hoặc integration test với client thật và media type phù hợp. Để kiểm chứng behavior dưới tải, đo throughput, pending queue, memory và buffer.

Backpressure là cơ chế phối hợp nội bộ qua Reactive Streams; nó không phải cam kết "mỗi request(n) bằng một TCP packet".

## 19. Dự án Java 17 chạy được bằng Maven

Dự án hoàn chỉnh này minh họa các nội dung chính:

- `initialRequest = 0` và xin nhiều đợt.
- Initial demand khác 0.
- `StepVerifierOptions`.
- Quan sát request bằng `doOnRequest` và `then(Runnable)`.
- Dùng `buffer(3)` minh họa request reshaping.
- Kiểm tra `thenCancel` và `doOnCancel`.
- Kiểm tra terminal error khi demand đã hết.
- Dùng `TestPublisher`.
- Đặt timeout cho verifier để tránh test treo lâu.

Project không chạy HTTP server: bài tập trung **unit test cơ chế request/backpressure của Reactor**, là kiến thức áp dụng trực tiếp cho các Flux/Mono do Spring WebFlux service trả về.

### 19.1. Cấu trúc project

~~~text
reactor-demand-tests/
├── pom.xml
└── src/
    ├── main/java/com/example/demand/
    │   └── DemandService.java
    └── test/java/com/example/demand/
        └── DemandServiceTest.java
~~~

### 19.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>reactor-demand-tests</artifactId>
    <version>1.0.0</version>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-core</artifactId>
        </dependency>
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
~~~

Spring Boot parent cung cấp dependency management và test plugin tương thích Java 17. Dự án chỉ minh họa Reactor, vì vậy không cần `@SpringBootApplication`, controller hoặc database. Có thể tích hợp các test này vào ứng dụng `spring-boot-starter-webflux` thực tế mà không đổi ý tưởng kiểm thử.

### 19.3. DemandService.java

~~~java
package com.example.demand;

import java.util.List;

import reactor.core.publisher.Flux;

public class DemandService {

    public Flux<Integer> numbers() {
        return Flux.range(1, 5);
    }

    public Flux<Integer> doubled() {
        return numbers().map(n -> n * 2);
    }

    public Flux<List<Integer>> batches() {
        return Flux.range(1, 9).buffer(3);
    }

    public Flux<Integer> failsAfterTwo() {
        return Flux.concat(
            Flux.just(10, 20),
            Flux.error(new IllegalStateException("boom"))
        );
    }
}
~~~

`numbers` dùng nguồn cold, synchronous và backpressure-aware. `batches` tạo từng nhóm ba item, còn `failsAfterTwo` minh họa terminal error.

### 19.4. DemandServiceTest.java

~~~java
package com.example.demand;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.time.Duration;
import java.util.List;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicLong;

import org.junit.jupiter.api.Test;

import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;
import reactor.test.StepVerifierOptions;
import reactor.test.publisher.TestPublisher;

class DemandServiceTest {

    private final DemandService service = new DemandService();

    @Test
    void initialZeroAndPhasedRequests() {
        StepVerifier.create(service.numbers(), 0)
            .expectSubscription()
            .thenRequest(2)
            .expectNext(1, 2)
            .thenRequest(3)
            .expectNext(3, 4, 5)
            .expectComplete()
            .verify(Duration.ofSeconds(2));
    }

    @Test
    void initialTwoAndOneAdditionalRequest() {
        StepVerifier.create(Flux.range(1, 3), 2)
            .expectSubscription()
            .expectNext(1, 2)
            .thenRequest(1)
            .expectNext(3)
            .expectComplete()
            .verify(Duration.ofSeconds(2));
    }

    @Test
    void optionsCanConfigureInitialRequest() {
        StepVerifierOptions options = StepVerifierOptions.create()
            .initialRequest(0)
            .scenarioName("doubled with staged demand")
            .checkUnderRequesting(true);

        StepVerifier.create(service.doubled(), options)
            .expectSubscription()
            .thenRequest(2)
            .expectNext(2, 4)
            .thenRequest(3)
            .expectNext(6, 8, 10)
            .expectComplete()
            .verify(Duration.ofSeconds(2));
    }

    @Test
    void noItemBeforeInitialRequest() {
        StepVerifier.create(service.numbers(), 0)
            .expectSubscription()
            .expectNoEvent(Duration.ofMillis(20))
            .thenRequest(5)
            .expectNext(1, 2, 3, 4, 5)
            .expectComplete()
            .verify(Duration.ofSeconds(2));
    }

    @Test
    void observesDemandBeforeAndAfterEachRequest() {
        AtomicLong requested = new AtomicLong();
        Flux<Integer> source = service.numbers()
            .doOnRequest(requested::addAndGet);

        StepVerifier.create(source, 0)
            .expectSubscription()
            .then(() -> assertEquals(0L, requested.get()))
            .thenRequest(2)
            .expectNext(1, 2)
            .then(() -> assertEquals(2L, requested.get()))
            .thenRequest(3)
            .expectNext(3, 4, 5)
            .then(() -> assertEquals(5L, requested.get()))
            .expectComplete()
            .verify(Duration.ofSeconds(2));
    }

    @Test
    void bufferChangesUpstreamRequestUnits() {
        AtomicLong upstreamRequested = new AtomicLong();

        Flux<List<Integer>> batches = Flux.range(1, 9)
            .doOnRequest(upstreamRequested::addAndGet)
            .buffer(3);

        StepVerifier.create(batches, 0)
            .expectSubscription()
            .thenRequest(1)
            .expectNext(List.of(1, 2, 3))
            .then(() -> assertEquals(3L, upstreamRequested.get()))
            .thenRequest(1)
            .expectNext(List.of(4, 5, 6))
            .then(() -> assertEquals(6L, upstreamRequested.get()))
            .thenCancel()
            .verify(Duration.ofSeconds(2));
    }

    @Test
    void cancellationReachesSource() {
        AtomicBoolean cancelled = new AtomicBoolean();

        Flux<Integer> source = Flux.range(1, 100)
            .doOnCancel(() -> cancelled.set(true));

        StepVerifier.create(source, 0)
            .expectSubscription()
            .thenRequest(2)
            .expectNext(1, 2)
            .thenCancel()
            .verify(Duration.ofSeconds(2));

        assertTrue(cancelled.get());
    }

    @Test
    void terminalErrorDoesNotNeedAnotherRequest() {
        StepVerifier.create(service.failsAfterTwo(), 0)
            .expectSubscription()
            .thenRequest(2)
            .expectNext(10, 20)
            .expectErrorMatches(error ->
                error instanceof IllegalStateException
                    && "boom".equals(error.getMessage())
            )
            .verify(Duration.ofSeconds(2));
    }

    @Test
    void testPublisherObservesRequests() {
        TestPublisher<Integer> publisher = TestPublisher.create();

        StepVerifier.create(publisher.flux(), 0)
            .expectSubscription()
            .then(() -> publisher
                .assertSubscribers()
                .assertMaxRequested(0))
            .thenRequest(1)
            .then(() -> publisher
                .assertMinRequested(1)
                .next(99)
                .complete())
            .expectNext(99)
            .expectComplete()
            .verify(Duration.ofSeconds(2));
    }
}
~~~

### 19.5. Chạy test

Yêu cầu JDK 17+ và Maven. Từ thư mục `reactor-demand-tests`:

~~~bash
mvn test
~~~

Maven sẽ biên dịch source, chạy JUnit 5 tests, và trả exit code 0 nếu toàn bộ assertions đều pass. Output Maven chứa tên phiên bản và thời gian chạy phụ thuộc môi trường; phần quan trọng cần thấy là không có failures/errors, ví dụ:

~~~text
Tests run: 9, Failures: 0, Errors: 0, Skipped: 0
BUILD SUCCESS
~~~

Đây là hình dạng kết quả kỳ vọng, không phải cam kết chính xác toàn bộ stdout của Maven trên mọi máy. Với ví dụ standalone này, không cần bật Spring context, cấu hình database hoặc có mạng để gửi HTTP request (ngoại trừ lần đầu Maven tải dependencies).

### 19.6. Tại sao dự án giúp học đúng thenRequest?

- Test 1 cho thấy demand tăng từ 0 → 2 → 3 item bổ sung.
- Test 2 cho thấy initialRequest dương đã có hiệu lực trước thenRequest.
- Test 3 cho thấy `StepVerifierOptions` tương đương overload số.
- Test 4 chứng minh không có onNext trước khi request với nguồn `Flux.range`.
- Test 5 quan sát demand tại vị trí không có reshaping.
- Test 6 cho thấy downstream request một `List` nhưng upstream phải cung cấp ba số.
- Test 7 hủy subscription sau khi tiêu thụ một phần.
- Test 8 xác nhận error terminal sau khi item demand đã về 0.
- Test 9 xác nhận `TestPublisher` nhận request theo đúng kịch bản.

## 20. Các test âm nên hiểu thay vì đưa vào suite chạy thường xuyên

Đôi khi cần học bằng những ví dụ **dự kiến thất bại**, nhưng không nên để chúng trong một test suite yêu cầu tất cả pass.

### Lỗi 1: mặc định unbounded làm test không thể kiểm tra từng đợt

~~~java
StepVerifier.create(Flux.range(1, 5))
    .thenRequest(1)
    .expectNext(1)
    .thenRequest(4)
    .expectNext(2, 3, 4, 5)
    .verifyComplete();
~~~

Test này có thể pass, nhưng không chứng minh upstream đợi `thenRequest` vì initial demand đã là Long.MAX_VALUE. Vấn đề nằm ở **ý nghĩa của test**, không phải chỉ ở pass/fail.

### Lỗi 2: expect nhiều hơn request

~~~java
StepVerifier.create(Flux.range(1, 3), 0)
    .thenRequest(1)
    .expectNext(1, 2)
    .verifyComplete();
~~~

Test thiếu demand cho item thứ hai. Cần thêm `thenRequest(1)` trước khi mong item thứ hai; để hoàn tất còn phải xử lý item thứ ba hoặc cancel theo mục tiêu.

### Lỗi 3: đợi complete sau khi chỉ request một phần

~~~java
StepVerifier.create(Flux.range(1, 100), 0)
    .thenRequest(1)
    .expectNext(1)
    .verifyComplete();
~~~

Publisher chưa có quyền phát 99 item còn lại, nên không thể hoàn tất bình thường sau khi phát hết 100. Hãy `thenCancel()` nếu chỉ kiểm tra item đầu, hoặc request đủ dữ liệu.

### Lỗi 4: expectNoEvent trước expectSubscription

~~~java
StepVerifier.create(Flux.range(1, 3), 0)
    .expectNoEvent(Duration.ofMillis(20))
    .thenRequest(3)
    .expectNext(1, 2, 3)
    .verifyComplete();
~~~

Subscription cũng là event; hãy dùng `expectSubscription()` trước khi đo khoảng không có event.

### Lỗi 5: đo upstream request nhưng quên operator prefetch

~~~java
Flux<Integer> source = repository.findAll()
    .publishOn(Schedulers.parallel());
~~~

Một `thenRequest(1)` phía dưới publishOn không nhất thiết biến thành `request(1)` ở repository; `publishOn` có prefetch. Khi test behavior của source, phải xác định vị trí `doOnRequest` và chính sách của operator.

## 21. Timeout và tính quyết định của test

Theo Javadoc StepVerifier, `verify()` mặc định **không có timeout tổng thể** trừ khi đã cấu hình default. Điều này rất dễ khiến CI treo khi test thiếu request.

Dùng:

~~~java
StepVerifier.create(Flux.range(1, 3), 0)
    .thenRequest(3)
    .expectNext(1, 2, 3)
    .expectComplete()
    .verify(Duration.ofSeconds(2));
~~~

Thời hạn trong `verify(Duration)` giới hạn thời gian đợi test, không làm Publisher tự có demand mới.

Có thể đặt timeout mặc định toàn cục:

~~~java
StepVerifier.setDefaultTimeout(Duration.ofSeconds(3));
~~~

Tuy nhiên đây là state ảnh hưởng tới các StepVerifier tạo sau đó trong cùng test process; nếu có nhiều test chạy song song, cần thận trọng và reset bằng `StepVerifier.resetDefaultTimeout()` khi thích hợp. Đối với test học tập, truyền timeout cụ thể vào `verify(Duration)` giúp rõ ràng hơn.

### Tránh dùng thời gian thực khi không cần

- `Flux.range` phù hợp kiểm tra demand từng đợt, không cần scheduler.
- `expectNoEvent(Duration)` thêm thời gian chờ thực nếu không dùng virtual time.
- `Flux.interval` và `delayElements` nên được kiểm thử bằng virtual time khi mục tiêu là thời gian.
- Không xây dựng test phụ thuộc vào scheduler interleaving mà yêu cầu một thứ tự không được hợp đồng đảm bảo.

### Cách đặt tên test

Tên test nên mô tả quan hệ demand–signal, ví dụ:

- `noItemBeforeInitialRequest`.
- `thenRequestAddsDemand`.
- `bufferChangesUpstreamRequestUnits`.
- `cancelAfterTwoItemsStopsSubscription`.
- `terminalErrorDoesNotNeedDemand`.

Khi test fail, tên này cho biết hợp đồng nào bị vi phạm nhanh hơn một tên chung chung như `testFlux`.

## 22. Checklist khi viết test điều khiển demand

- [ ] Mục tiêu là test values đơn thuần hay test request/backpressure?
- [ ] Nếu test demand, đã dùng initialRequest hữu hạn hoặc 0 chưa?
- [ ] Có biết `StepVerifier.create(source)` mặc định request Long.MAX_VALUE không?
- [ ] Các bước `thenRequest(n)` có cộng dồn đúng với demand còn lại không?
- [ ] Tổng demand có đủ cho các `expectNext` hoặc `expectNextCount` không?
- [ ] Có dùng `expectSubscription` khi kiểm tra `expectNoEvent` ngay sau subscribe không?
- [ ] Đã phân biệt onNext với onComplete/onError không?
- [ ] Test kết thúc bằng verifyComplete, expectError hay thenCancel đúng mục tiêu?
- [ ] Đã đặt thời hạn verify để tránh test treo khi thiếu request chưa?
- [ ] Có operator nào reshape request như buffer, publishOn, flatMap, limitRate không?
- [ ] `doOnRequest` được đặt ở phía nào của operator cần quan sát?
- [ ] Nếu dùng TestPublisher, có chỉ phát item khi có demand và kiểm tra overflow không?
- [ ] Có tránh tự subscribe Publisher trước khi StepVerifier subscribe không?
- [ ] Có tránh tắt checkUnderRequesting chỉ để che kịch bản thiếu demand không?
- [ ] Có dùng virtual time đúng lúc nếu pipeline phụ thuộc timer không?
- [ ] Có phân biệt unit test Reactor với HTTP integration test không?

## 23. Câu hỏi tự kiểm tra và đáp án

**1.** `StepVerifier.create(source)` mặc định request bao nhiêu? Long.MAX_VALUE, tức unbounded.

**2.** `StepVerifier.create(source, 0)` có gửi `request(0)` trái chuẩn không? Không; nó cấu hình verifier chưa gửi request item ban đầu.

**3.** `thenRequest(2)` là gì? Gửi thêm demand cho 2 item, tương tự `Subscription.request(2)`.

**4.** Nếu outstanding demand đang là 1 rồi `thenRequest(3)`, còn bao nhiêu? 4 trước khi có thêm onNext.

**5.** Vì sao `expectNext(1,2)` trước khi request đủ có thể thất bại? Test đang mong nhiều item hơn demand đã cấp, dẫn tới under-requesting.

**6.** `checkUnderRequesting` mặc định ra sao? Bật (true).

**7.** Có nên tắt `checkUnderRequesting` để sửa test bị treo không? Không; nên sửa demand và các kỳ vọng.

**8.** `expectNoEvent` có coi `onSubscribe` là event không? Có; hãy dùng `expectSubscription` trước khi kiểm tra khoảng im lặng.

**9.** `Mono.empty()` có cần request(1) để được complete không? Không nhất thiết; terminal signal không bị điều tiết như onNext.

**10.** `thenRequest` có bắt source `Flux.range` chạy trên thread mới không? Không; nó không phải scheduler operator.

**11.** `thenRequest(1)` sau `buffer(3)` có thể tạo request bao nhiêu ở nguồn? 3 item nguồn cho một List item downstream.

**12.** `doOnRequest` trước và sau `buffer(3)` có thể quan sát khác nhau không? Có; operator reshape request.

**13.** Khi chỉ muốn kiểm tra hai item đầu của một Flux dài, kết thúc test thế nào? `thenCancel().verify(...)`.

**14.** Nếu muốn kiểm tra completion của Flux.range(1,100), request 2 item có đủ không? Không; cần request đủ 100 item hoặc thay mục tiêu thành cancellation.

**15.** `onError` có tiêu thụ outstanding demand không? Không; error là terminal signal.

**16.** Khi dùng `TestPublisher`, có thể kiểm tra subscriber đã request chưa bằng gì? `assertMinRequested`, `assertMaxRequested`; ngoài ra có `assertNoRequestOverflow`.

**17.** `then(Runnable)` có xin thêm item không? Không; nó chạy task/assertion trong kịch bản.

**18.** Nếu muốn test operator thời gian, chỉ thêm `thenRequest` có đủ không? Không; cần `thenAwait` hoặc `withVirtualTime` khi phù hợp.

**19.** `verify()` mặc định có timeout không? Không có timeout tổng thể mặc định; dùng `verify(Duration)` để giới hạn.

**20.** Một test StepVerifier pass có chứng minh HTTP proxy flush đúng mỗi item không? Không; đó là trách nhiệm của integration/transport test.

## 24. Tổng kết

Điều khiển initial request và `thenRequest` giúp biến kiểm thử Reactor thành một kịch bản có kiểm soát về demand:

~~~java
StepVerifier.create(source, 0)
    .expectSubscription()
    .thenRequest(2)
    .expectNext(item1, item2)
    .thenRequest(1)
    .expectNext(item3)
    .verifyComplete();
~~~

Đọc kịch bản theo thứ tự: **subscribe → request → nhận item → request thêm → nhận item → terminal**.

Nếu đang test backpressure, đừng để initial demand mặc định unbounded. Hãy hiểu request được cộng dồn, terminal signals không tiêu thụ demand, và các operator có thể chuyển đổi request upstream. Test cần đủ request để tiến tới terminal hoặc kết thúc chủ động bằng cancel. Kết hợp `doOnRequest`, `TestPublisher`, `StepVerifierOptions` và `verify(Duration)` để kịch bản rõ ràng, có thể tái lập và không treo CI.

**Tài liệu tham khảo chính thức:**

- [Project Reactor — Testing (StepVerifier, PublisherProbe, TestPublisher)](https://projectreactor.io/docs/core/release/reference/testing.html)
- [StepVerifier Javadoc — create, verify, withVirtualTime](https://projectreactor.io/docs/test/release/api/reactor/test/StepVerifier.html)
- [StepVerifier.Step Javadoc — thenRequest, thenCancel, expectNoEvent](https://projectreactor.io/docs/test/release/api/reactor/test/StepVerifier.Step.html)
- [StepVerifierOptions Javadoc — initialRequest, checkUnderRequesting](https://projectreactor.io/docs/test/release/api/reactor/test/StepVerifierOptions.html)
- [TestPublisher Javadoc — request assertions](https://projectreactor.io/docs/test/release/api/reactor/test/publisher/TestPublisher.html)
- [Reactor Reference Guide — Backpressure and reshaping requests](https://projectreactor.io/docs/core/release/reference/subscribe-backpressure.html)
- [Reactive Streams Specification](https://github.com/reactive-streams/reactive-streams-jvm#specification).