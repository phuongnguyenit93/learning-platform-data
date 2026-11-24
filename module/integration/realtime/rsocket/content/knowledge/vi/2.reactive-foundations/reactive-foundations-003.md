# Tín hiệu onSubscribe, onNext, onError và onComplete

Trong lập trình reactive, dữ liệu được truyền dưới dạng một chuỗi tín hiệu bất đồng bộ. Thay vì gọi một hàm rồi chờ kết quả trả về ngay, bên tiêu thụ đăng ký nhận dữ liệu và xử lý từng tín hiệu khi chúng xuất hiện. Reactive Streams định nghĩa giao thức trao đổi này; Project Reactor hiện thực giao thức bằng các kiểu <code>Flux</code> và <code>Mono</code>, thường được dùng trong ứng dụng Spring Boot và giao tiếp RSocket.

Bốn tín hiệu <code>onSubscribe</code>, <code>onNext</code>, <code>onError</code> và <code>onComplete</code> mô tả vòng đời cơ bản của một lần đăng ký. Hiểu đúng ý nghĩa và thứ tự của chúng giúp ta kiểm soát nhu cầu dữ liệu, xử lý lỗi, giải phóng tài nguyên và chẩn đoán các luồng realtime.

## 1. Các thành phần tham gia vào luồng reactive

Reactive Streams có ba thành phần chính:

| Thành phần | Vai trò |
| --- | --- |
| <code>Publisher&lt;T&gt;</code> | Nguồn phát ra các phần tử kiểu <code>T</code> và thông báo kết thúc hoặc lỗi. |
| <code>Subscriber&lt;T&gt;</code> | Bên đăng ký nhận và xử lý các phần tử, lỗi và tín hiệu hoàn tất. |
| <code>Subscription</code> | Đại diện cho một lần đăng ký; cho phép Subscriber yêu cầu số phần tử và hủy đăng ký. |

Khi Subscriber gọi <code>publisher.subscribe(subscriber)</code>, Publisher tạo một Subscription và chuyển Subscription đó cho Subscriber thông qua <code>onSubscribe</code>. Sau đó, dữ liệu chỉ được phát theo nhu cầu mà Subscriber đã yêu cầu.

Một luồng thông thường có dạng:

~~~text
Subscriber                 Publisher
    |                          |
    |-------- subscribe() ---->|
    |<----- onSubscribe(s) ----|
    |                          |
    |------ request(n) ------->|  Subscriber yêu cầu tối đa n phần tử
    |<------- onNext(a) -------|
    |<------- onNext(b) -------|
    |<------- onNext(c) -------|
    |                          |
    |<------ onComplete() -----|  hoặc onError(error)
~~~

Publisher có thể phát không phần tử nào, một phần tử hoặc nhiều phần tử. Một lần đăng ký chỉ kết thúc theo một trong hai cách: phát <code>onComplete</code> để báo hoàn tất bình thường, hoặc phát <code>onError</code> để báo lỗi. Hai tín hiệu kết thúc này loại trừ lẫn nhau.

## 2. Tín hiệu onSubscribe

<code>onSubscribe(Subscription subscription)</code> là tín hiệu đầu tiên mà Subscriber nhận được trong một lần đăng ký hợp lệ. Publisher dùng nó để trao quyền điều khiển luồng dữ liệu cho Subscriber.

Trong <code>onSubscribe</code>, Subscriber thường thực hiện một hoặc nhiều việc sau:

- Lưu Subscription để có thể yêu cầu thêm dữ liệu hoặc hủy đăng ký về sau.
- Gọi <code>request(n)</code> để yêu cầu tối đa <code>n</code> phần tử.
- Gọi <code>cancel()</code> nếu không còn cần nhận dữ liệu.

Ví dụ một Subscriber yêu cầu từng phần tử:

~~~java
public final class OneByOneSubscriber<T> implements Subscriber<T> {
    private Subscription subscription;

    @Override
    public void onSubscribe(Subscription subscription) {
        this.subscription = subscription;
        subscription.request(1);
    }

    @Override
    public void onNext(T value) {
        process(value);
        subscription.request(1);
    }

    @Override
    public void onError(Throwable error) {
        log.error("Luồng dữ liệu thất bại", error);
    }

    @Override
    public void onComplete() {
        log.info("Luồng dữ liệu đã hoàn tất");
    }

    private void process(T value) {
        log.info("Đang xử lý: {}", value);
    }
}
~~~

<code>request(1)</code> trong <code>onSubscribe</code> cho phép Publisher phát tối đa một phần tử ban đầu. Sau khi xử lý phần tử đó, Subscriber yêu cầu thêm một phần tử trong <code>onNext</code>. Cách này minh họa backpressure: tốc độ phát dữ liệu được điều tiết theo khả năng tiếp nhận của bên tiêu thụ.

Tham số của <code>request</code> phải là số dương. Gọi <code>request(0)</code> hoặc <code>request</code> với số âm vi phạm giao thức và dẫn đến lỗi theo quy tắc Reactive Streams. <code>request(Long.MAX_VALUE)</code> biểu thị nhu cầu không giới hạn; cách gọi này thuận tiện nhưng làm mất lợi ích điều tiết theo số lượng yêu cầu hữu hạn.

Nếu Subscriber không còn quan tâm đến luồng, nó gọi <code>subscription.cancel()</code>. Hủy đăng ký không phải là <code>onComplete</code>: Publisher không có nghĩa vụ gửi tín hiệu hoàn tất cho một Subscriber đã hủy. Việc hủy cũng có thể cần thời gian để lan truyền đến nguồn dữ liệu, vì vậy ứng dụng không nên giả định rằng mọi công việc đang chạy dừng tức thì.

## 3. Tín hiệu onNext

<code>onNext(T value)</code> được gọi mỗi khi Publisher phát một phần tử đến Subscriber. Một luồng có thể phát không, một hoặc nhiều lần <code>onNext</code>, tùy loại Publisher và kết quả thực tế.

Ví dụ:

~~~java
Flux<String> events = Flux.just("CONNECTED", "MESSAGE", "DISCONNECTED");

events.subscribe(event -> log.info("Nhận sự kiện: {}", event));
~~~

Subscriber nhận ba lần <code>onNext</code>, lần lượt với các giá trị <code>CONNECTED</code>, <code>MESSAGE</code> và <code>DISCONNECTED</code>, sau đó nhận <code>onComplete</code>. Một Publisher tuân thủ Reactive Streams không được phát <code>null</code> qua <code>onNext</code>; nếu cần biểu diễn trạng thái không có dữ liệu, hãy dùng một luồng rỗng hoặc kiểu dữ liệu miền phù hợp.

Số lần <code>onNext</code> bị giới hạn bởi nhu cầu đã được yêu cầu qua Subscription. Nếu Subscriber đã yêu cầu ba phần tử, Publisher chỉ được phát tối đa ba phần tử cho đến khi có yêu cầu bổ sung. Đây là điểm khác biệt quan trọng giữa luồng reactive có backpressure và một cơ chế đẩy dữ liệu không có kiểm soát.

Trong callback <code>onNext</code>, nên xử lý nhanh và tránh thao tác chặn luồng như gọi I/O đồng bộ lâu, chờ khóa hoặc thực hiện tính toán nặng. Callback chặn có thể làm chậm việc tiêu thụ các phần tử tiếp theo. Với Reactor, có thể tổ chức lại nơi thực thi bằng các toán tử như <code>publishOn</code> hoặc <code>subscribeOn</code> khi phù hợp; cần hiểu rõ toán tử nào thay đổi luồng thực thi và vị trí áp dụng của nó.

## 4. Tín hiệu onError

<code>onError(Throwable error)</code> thông báo rằng Publisher không thể tiếp tục phát luồng theo cách bình thường. Đây là tín hiệu kết thúc: sau khi phát <code>onError</code>, Publisher không được phát thêm <code>onNext</code> hoặc <code>onComplete</code> cho cùng lần đăng ký.

Một số nguyên nhân thường gặp:

- Kết nối tới dịch vụ hoặc cơ sở dữ liệu bị lỗi.
- Dữ liệu đầu vào không hợp lệ trong quá trình chuyển đổi.
- Một thao tác bất đồng bộ hoàn thành bằng exception.
- Hệ thống downstream từ chối hoặc không thể xử lý dữ liệu.

Trong Reactor, có thể ghi log lỗi bằng <code>doOnError</code> và thay thế luồng lỗi bằng các toán tử phục hồi:

~~~java
Flux<Integer> result = Flux.just(1, 2)
    .concatWith(Mono.error(new IllegalStateException("Nguồn dữ liệu gặp lỗi")))
    .doOnError(error -> log.error("Đã nhận lỗi từ nguồn", error))
    .onErrorResume(error -> Flux.just(99));

result.subscribe(
    value -> log.info("Giá trị: {}", value),
    error -> log.error("Luồng kết thúc bằng lỗi", error),
    () -> log.info("Luồng hoàn tất")
);
~~~

Nguồn phát hai giá trị <code>1</code> và <code>2</code>, sau đó phát lỗi. <code>doOnError</code> chỉ thực hiện tác vụ phụ như ghi log; nó không tự xử lý hoặc loại bỏ lỗi. <code>onErrorResume</code> chuyển sang Publisher dự phòng phát giá trị <code>99</code>. Vì lỗi đã được phục hồi trong pipeline, Subscriber cuối cùng nhận <code>onNext(1)</code>, <code>onNext(2)</code>, <code>onNext(99)</code> rồi <code>onComplete</code>, thay vì nhận <code>onError</code>.

Một số toán tử xử lý lỗi thường dùng:

| Toán tử | Công dụng |
| --- | --- |
| <code>onErrorReturn(value)</code> | Thay lỗi bằng một giá trị dự phòng cố định. |
| <code>onErrorResume(fn)</code> | Chọn một Publisher khác dựa trên lỗi để tiếp tục luồng. |
| <code>onErrorMap(fn)</code> | Chuyển lỗi hiện tại thành một loại lỗi khác. |
| <code>retry(...)</code> hoặc <code>retryWhen(...)</code> | Đăng ký lại nguồn khi có lỗi theo chính sách thử lại. |

Thử lại có thể khiến nguồn được thực thi nhiều lần. Vì vậy, chỉ nên retry những thao tác có thể lặp lại an toàn hoặc đã được thiết kế idempotent. Không nên dùng <code>doOnError</code> như một cách thay thế cho xử lý lỗi; nếu không phục hồi, lỗi vẫn đi tới Subscriber.

## 5. Tín hiệu onComplete

<code>onComplete()</code> báo rằng Publisher đã phát xong dữ liệu một cách bình thường. Đây cũng là tín hiệu kết thúc. Sau <code>onComplete</code>, không được có thêm <code>onNext</code> hoặc <code>onError</code> trong cùng lần đăng ký.

Ví dụ:

~~~java
Flux.range(1, 3)
    .doOnNext(value -> log.info("Nguồn phát: {}", value))
    .doOnComplete(() -> log.info("Nguồn đã phát hết dữ liệu"))
    .subscribe(
        value -> log.info("Subscriber nhận: {}", value),
        error -> log.error("Subscriber nhận lỗi", error),
        () -> log.info("Subscriber nhận hoàn tất")
    );
~~~

Trong ví dụ này, Publisher phát ba phần tử rồi hoàn tất. <code>doOnComplete</code> là hook quan sát việc hoàn tất thành công của <code>Flux</code>; callback hoàn tất trong <code>subscribe</code> cũng được gọi khi Subscriber nhận <code>onComplete</code>.

Hoàn tất không có nghĩa là luồng nhất thiết phải có dữ liệu. Với <code>Mono</code>, ba trường hợp điển hình là:

| Publisher | Chuỗi tín hiệu quan sát được |
| --- | --- |
| <code>Mono.just("OK")</code> | <code>onSubscribe</code> → <code>onNext("OK")</code> → <code>onComplete</code> |
| <code>Mono.empty()</code> | <code>onSubscribe</code> → <code>onComplete</code> |
| <code>Mono.error(error)</code> | <code>onSubscribe</code> → <code>onError(error)</code> |

Vì vậy, cần phân biệt “không có kết quả” với “có lỗi”. <code>Mono.empty()</code> là kết thúc bình thường không có giá trị; <code>Mono.error(...)</code> là kết thúc do lỗi. Với <code>Mono</code>, hook <code>doOnSuccess</code> thường được dùng để quan sát kết quả thành công; callback của nó nhận <code>null</code> khi Mono hoàn tất rỗng. Cần xử lý trường hợp đó nếu dùng hook này.

## 6. Thứ tự tín hiệu và các quy tắc cần nhớ

Đối với một lần đăng ký, trình tự hợp lệ có thể tóm tắt như sau:

~~~text
onSubscribe
    |
    +---- 0..n lần onNext
    |
    +---- onComplete
    hoặc
    +---- onError(error)
~~~

Các quy tắc quan trọng:

1. <code>onSubscribe</code> phải đến trước mọi tín hiệu khác và chỉ xuất hiện một lần cho lần đăng ký đó.
2. <code>onNext</code> có thể xuất hiện không lần nào hoặc nhiều lần, nhưng không vượt quá nhu cầu Subscriber đã yêu cầu.
3. Một luồng kết thúc bằng đúng một trong hai tín hiệu <code>onComplete</code> hoặc <code>onError</code>.
4. Không có tín hiệu dữ liệu hoặc tín hiệu kết thúc nào được phát sau tín hiệu kết thúc.
5. Các tín hiệu gửi tới cùng một Subscriber phải được tuần tự hóa; Subscriber không phải xử lý hai callback tín hiệu đồng thời cho cùng một Subscription.
6. <code>cancel()</code> là thao tác hủy từ Subscriber, không phải một tín hiệu kết thúc thay thế cho <code>onComplete</code> hay <code>onError</code>.

Một điểm dễ nhầm là <code>doOnComplete</code> và <code>doOnError</code> chỉ quan sát hai nhánh kết thúc tương ứng. Nếu muốn quan sát cả hoàn tất, lỗi và hủy đăng ký, Reactor cung cấp <code>doFinally</code>, với <code>SignalType</code> cho biết luồng kết thúc theo cách nào. Điều này hữu ích khi cần dừng bộ đếm, ghi nhận thời lượng hoặc giải phóng tài nguyên bất kể kết quả.

## 7. Liên hệ với giao tiếp RSocket

RSocket sử dụng mô hình tương tác reactive và phối hợp với backpressure để truyền dữ liệu giữa client và server. Các tín hiệu Reactive Streams vẫn là cách ứng dụng quan sát vòng đời của Publisher trả về từ các thao tác RSocket.

| Kiểu tương tác RSocket | Kiểu kết quả thường gặp trong Java | Ý nghĩa tín hiệu |
| --- | --- | --- |
| Request-response | <code>Mono&lt;T&gt;</code> | Có thể nhận một giá trị rồi hoàn tất, hoàn tất rỗng hoặc kết thúc bằng lỗi. |
| Request-stream | <code>Flux&lt;T&gt;</code> | Có thể nhận nhiều giá trị theo nhu cầu, rồi hoàn tất hoặc lỗi. |
| Request-channel | <code>Flux&lt;T&gt;</code> | Hai phía trao đổi các luồng dữ liệu; mỗi phía có vòng đời và nhu cầu nhận dữ liệu riêng. |
| Fire-and-forget | Không có luồng phản hồi cho bên gửi | Bên gửi không nhận chuỗi <code>onNext</code> phản hồi từ bên nhận. |

Ví dụ một handler Spring Boot trả về luồng giá realtime:

~~~java
@MessageMapping("prices.stream")
public Flux<Price> streamPrices(String symbol) {
    return priceService.watch(symbol)
        .doOnSubscribe(subscription ->
            log.info("Bắt đầu theo dõi giá: {}", symbol))
        .doOnNext(price ->
            log.debug("Giá mới của {}: {}", symbol, price))
        .doOnError(error ->
            log.warn("Luồng giá {} gặp lỗi", symbol, error))
        .doOnComplete(() ->
            log.info("Luồng giá {} đã hoàn tất", symbol));
}
~~~

Khi client đăng ký route <code>prices.stream</code>, client nhận các giá trị dưới dạng <code>onNext</code>. Khi nguồn giá đóng bình thường, client nhận <code>onComplete</code>; khi nguồn gặp lỗi không được phục hồi, client nhận <code>onError</code>. Nếu client hủy đăng ký, luồng bị cancel và không nên chờ <code>onComplete</code> như một xác nhận hủy.

Nhu cầu mà Subscriber tạo ra được Reactor truyền ngược về nguồn. Với các tương tác stream của RSocket, nhu cầu này được phối hợp với cơ chế flow control của giao thức, trong đó các yêu cầu bổ sung được biểu diễn bằng <code>REQUEST_N</code>. Nhờ vậy, bên gửi có thể điều tiết số phần tử truyền đi theo khả năng tiêu thụ của bên nhận thay vì đẩy vô hạn dữ liệu vào bộ đệm.

Trong ứng dụng thực tế, nên để tầng framework hoặc tầng biên của ứng dụng thực hiện subscribe. Một service thường trả về <code>Mono</code> hoặc <code>Flux</code> để caller quyết định cách kết hợp, xử lý lỗi và hủy luồng. Nếu tự gọi <code>subscribe()</code> bên trong service rồi bỏ qua Publisher, luồng công việc có thể tách khỏi vòng đời của request RSocket; lỗi và cancellation cũng khó được truyền ngược đúng cách.

## 8. Kiểm thử các tín hiệu

Có thể dùng <code>StepVerifier</code> từ thư viện <code>reactor-test</code> để kiểm tra dữ liệu và tín hiệu kết thúc mà không cần dựa vào log:

~~~java
StepVerifier.create(Flux.range(1, 3))
    .expectNext(1, 2, 3)
    .verifyComplete();

StepVerifier.create(Flux.error(new IllegalStateException("boom")))
    .expectErrorMessage("boom")
    .verify();
~~~

Để kiểm tra backpressure, có thể bắt đầu với nhu cầu bằng không rồi yêu cầu từng nhóm phần tử:

~~~java
StepVerifier.create(Flux.range(1, 3), 0)
    .thenRequest(1)
    .expectNext(1)
    .thenRequest(2)
    .expectNext(2, 3)
    .verifyComplete();
~~~

Kiểu kiểm thử này xác nhận rằng Publisher chỉ phát dữ liệu sau khi có demand và cuối cùng gửi đúng tín hiệu hoàn tất. Có thể viết trường hợp tương tự cho nhánh lỗi, luồng rỗng và cancellation để bao phủ các trạng thái vòng đời mà ứng dụng cần xử lý.

## 9. Lỗi thường gặp khi đọc và xử lý tín hiệu

| Hiện tượng | Nguyên nhân có thể có | Hướng kiểm tra |
| --- | --- | --- |
| Không thấy <code>onNext</code> | Chưa có Subscriber, chưa có demand, nguồn chưa phát hoặc Publisher là luồng rỗng. | Xác nhận có subscribe, kiểm tra <code>request(n)</code> và trạng thái nguồn. |
| Không thấy <code>onComplete</code> | Luồng vẫn đang mở, nguồn không phát tín hiệu kết thúc, luồng đã lỗi hoặc Subscriber đã cancel. | Quan sát thêm <code>onError</code> và cancellation; kiểm tra điều kiện đóng nguồn. |
| Subscriber nhận <code>onError</code> | Một thao tác upstream phát sinh lỗi chưa được phục hồi. | Đọc stack trace và quyết định retry, fallback hoặc truyền lỗi lên tầng gọi. |
| Dữ liệu được xử lý nhiều lần | Có nhiều lần subscribe hoặc nguồn được kết nối tới nhiều Subscriber. | Kiểm tra vị trí gọi <code>subscribe()</code> và đặc tính cold/hot của nguồn. |
| Luồng chậm khi tải tăng | Callback xử lý chặn hoặc Subscriber yêu cầu dữ liệu quá nhanh so với khả năng xử lý. | Rút ngắn callback, xem lại scheduler và áp dụng demand phù hợp. |

Khi debug, hãy xác định tín hiệu cuối cùng mà Subscriber nhận được, sau đó lần ngược lên Publisher và các toán tử trong pipeline. Ghi log ở <code>doOnSubscribe</code>, <code>doOnNext</code>, <code>doOnError</code> và <code>doOnComplete</code> có thể giúp quan sát từng giai đoạn; dùng <code>doFinally</code> khi cần phân biệt hoàn tất, lỗi và hủy đăng ký.

## 10. Ghi nhớ

- <code>onSubscribe</code> trao Subscription để Subscriber yêu cầu dữ liệu hoặc hủy đăng ký.
- <code>onNext</code> mang từng phần tử và bị giới hạn bởi demand.
- <code>onError</code> kết thúc luồng do lỗi; cần phục hồi bằng toán tử phù hợp hoặc chuyển lỗi tới caller.
- <code>onComplete</code> kết thúc luồng bình thường, kể cả khi luồng không phát phần tử nào.
- <code>cancel()</code> là thao tác hủy, không đồng nghĩa với hoàn tất.
- Trong RSocket, các tín hiệu này giúp ứng dụng quản lý vòng đời request-response, request-stream và request-channel; backpressure phối hợp với flow control để điều tiết dữ liệu realtime.
