# Kết nối RxJava với Reactive Streams và Reactor

RxJava và Project Reactor đều hỗ trợ lập trình bất đồng bộ bằng các publisher, nhưng chúng có bộ kiểu dữ liệu và cách tổ chức API riêng. Một hệ thống Java có thể dùng RxJava ở một thư viện cũ, dùng Reactor trong Spring WebFlux hoặc cần tích hợp một thành phần phát dữ liệu theo Reactive Streams. Khi kết nối các thư viện này, điều quan trọng là giữ đúng hợp đồng subscription, demand, cancellation và terminal signal.

Điểm nối tự nhiên giữa RxJava và Reactor là chuẩn **Reactive Streams**. Trong RxJava 2 và RxJava 3, `Flowable<T>` triển khai `org.reactivestreams.Publisher<T>`. Reactor `Flux<T>` và `Mono<T>` cũng triển khai hợp đồng Publisher. Vì vậy, có thể chuyển publisher giữa hai thư viện mà không cần chuyển từng phần tử qua callback thủ công. Tuy nhiên, không phải mọi kiểu RxJava đều là Reactive Streams Publisher: `Observable<T>` không hỗ trợ backpressure và cần một chính sách chuyển đổi rõ ràng trước khi đưa vào Reactor.

## 1. Vai trò của Reactive Streams trong tích hợp

Reactive Streams định nghĩa một hợp đồng nhỏ để các thư viện streaming có thể giao tiếp:

- `Publisher<T>` phát các phần tử và terminal signal.
- `Subscriber<T>` nhận subscription, phần tử, lỗi và hoàn tất.
- `Subscription` cho phép subscriber yêu cầu số phần tử bằng `request(n)` và hủy bằng `cancel()`.
- `Processor<T, R>` vừa là subscriber của kiểu T vừa là publisher của kiểu R.

Một luồng tín hiệu cơ bản:

~~~mermaid
sequenceDiagram
    participant S as Subscriber
    participant P as Publisher
    S->>P: subscribe(this)
    P-->>S: onSubscribe(subscription)
    S->>P: request(2)
    P-->>S: onNext(item 1)
    P-->>S: onNext(item 2)
    S->>P: request(1)
    P-->>S: onNext(item 3)
    P-->>S: onComplete()
~~~

Subscriber không nên nhận nhiều phần tử hơn demand đã yêu cầu. `onError` và `onComplete` là terminal signal: sau một trong hai tín hiệu đó, publisher không được phát thêm `onNext` hoặc terminal signal khác. Cancellation là yêu cầu từ subscriber để dừng việc phát dữ liệu; nó không phải một `onError`.

Khi RxJava và Reactor cùng sử dụng `org.reactivestreams.Publisher`, adapter có thể chuyển tiếp hợp đồng này. Demand và cancellation được truyền qua ranh giới thư viện theo cách triển khai adapter. Việc dùng chung giao diện không có nghĩa mọi semantics riêng của RxJava và Reactor biến mất; scheduler, hot/cold behavior, replay và chính sách lỗi vẫn phụ thuộc publisher gốc và các toán tử đã lắp ráp.

## 2. Chọn đúng kiểu RxJava

RxJava có hai nhóm API thường gặp:

| Kiểu | Cardinality | Backpressure | Reactive Streams Publisher |
| --- | --- | --- | --- |
| `Flowable<T>` | 0 đến nhiều phần tử | Có | Có |
| `Observable<T>` | 0 đến nhiều phần tử | Không | Không |
| `Single<T>` | Chính xác một kết quả hoặc lỗi | Không áp dụng demand theo stream | Không trực tiếp |
| `Maybe<T>` | 0 hoặc một kết quả | Không áp dụng demand theo stream | Không trực tiếp |
| `Completable` | Chỉ complete hoặc error | Không có phần tử | Không trực tiếp |

`Flowable` là lựa chọn tự nhiên khi cần tích hợp với Reactor qua Reactive Streams. `Observable` phù hợp với các nguồn không dùng backpressure, ví dụ sự kiện UI hoặc callback API, nhưng cần chọn cách điều tiết khi chuyển sang `Flowable`. `Single`, `Maybe` và `Completable` biểu diễn kết quả có cardinality riêng; có thể chuyển qua các adapter `Flowable` hoặc API tương ứng của phiên bản RxJava đang dùng.

Các ví dụ trong bài dùng RxJava 3 với package `io.reactivex.rxjava3.*` và Reactor Core. RxJava 2 có package `io.reactivex.*`; không trộn kiểu RxJava 2 và RxJava 3 trong cùng một pipeline nếu không có adapter chuyển đổi rõ ràng.

## 3. Đưa RxJava Flowable vào Reactor

Vì `Flowable<T>` là Reactive Streams Publisher, Reactor có thể nhận trực tiếp bằng `Flux.from(...)` hoặc `Mono.from(...)`.

~~~java
import io.reactivex.rxjava3.core.Flowable;
import reactor.core.publisher.Flux;

Flowable<Integer> rxNumbers = Flowable.range(1, 5)
    .map(number -> number * 10);

Flux<Integer> reactorNumbers = Flux.from(rxNumbers);
~~~

`Flux.from` tạo một publisher Reactor từ publisher đầu vào. Khi có subscriber, Reactor đăng ký với Flowable và nhận các tín hiệu theo hợp đồng Reactive Streams. Nếu downstream yêu cầu demand, adapter truyền yêu cầu đó về upstream thông qua Subscription.

Ví dụ dùng trong một service Reactor:

~~~java
Flux<PriceUpdate> prices() {
    Flowable<PriceUpdate> rxFeed = legacyPriceClient.updates();

    return Flux.from(rxFeed)
        .filter(PriceUpdate::isValid)
        .map(this::normalize);
}
~~~

Service có thể dùng các toán tử Reactor ở phía sau mà không cần chuyển đổi từng phần tử bằng listener. `Flux.from` cũng giữ nguyên đặc tính nguồn: nếu Flowable là cold thì mỗi subscription có thể tạo một lần thực thi mới; nếu Flowable là hot thì subscriber chỉ nhận dữ liệu theo semantics của nguồn hot.

### Khi nào dùng Mono.from?

`Mono.from(Publisher)` phù hợp khi cần lấy tối đa một phần tử từ publisher. Nếu upstream là Flowable có nhiều phần tử, Mono lấy phần tử đầu tiên rồi hủy subscription upstream. Nếu upstream hoàn tất mà không phát phần tử, Mono hoàn tất rỗng; nếu upstream lỗi trước khi có phần tử, Mono phát lỗi.

~~~java
Mono<User> firstUser = Mono.from(
    Flowable.just(userA, userB, userC)
);
~~~

Đoạn mã chỉ giữ `userA`; các phần tử sau không thuộc kết quả Mono. Đừng dùng `Mono.from` nếu yêu cầu là xác minh publisher phải phát chính xác một phần tử. Khi cần kiểm tra cardinality, hãy dùng toán tử kiểm tra phù hợp hoặc chuyển đổi nguồn theo hợp đồng rõ ràng.

## 4. Đưa Reactor Flux hoặc Mono vào RxJava

Ở chiều ngược lại, RxJava `Flowable.fromPublisher(...)` nhận bất kỳ Reactive Streams Publisher nào, bao gồm `Flux` và `Mono`.

~~~java
import io.reactivex.rxjava3.core.Flowable;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

Flux<Integer> reactorFlux = Flux.range(1, 4)
    .map(number -> number + 100);

Flowable<Integer> rxFlowable =
    Flowable.fromPublisher(reactorFlux);

Mono<String> reactorMono = Mono.just("ready");

Flowable<String> rxSingleValue =
    Flowable.fromPublisher(reactorMono);
~~~

`Flowable.fromPublisher` đăng ký vào publisher Reactor khi RxJava subscriber đăng ký. Với Flux, các phần tử được chuyển tiếp theo demand. Với Mono, Flowable nhận không quá một phần tử rồi complete, hoặc complete rỗng hay error theo tín hiệu Mono.

Có thể đóng gói adapter ở ranh giới module:

~~~java
Flowable<OrderEvent> rxOrderEvents() {
    return Flowable.fromPublisher(orderService.orderEvents());
}
~~~

Giữ kiểu Reactive Streams ở ranh giới giúp phần còn lại của module không phải phụ thuộc trực tiếp vào các kiểu nội bộ của Reactor. Ngược lại, nếu ứng dụng chủ yếu dùng Reactor, hãy chuyển Flowable thành Flux một lần ở adapter và giữ pipeline bên trong thống nhất.

## 5. Chuyển đổi Observable cần chính sách backpressure

`Observable<T>` không triển khai Reactive Streams Publisher và không có giao thức `request(n)`. Vì vậy, không thể đưa Observable trực tiếp vào `Flux.from` như với Flowable. Cần chuyển nó thành Flowable và chọn `BackpressureStrategy`.

~~~java
import io.reactivex.rxjava3.core.BackpressureStrategy;
import io.reactivex.rxjava3.core.Flowable;
import io.reactivex.rxjava3.core.Observable;
import reactor.core.publisher.Flux;

Observable<SensorEvent> observable = sensorApi.events();

Flowable<SensorEvent> flowable =
    observable.toFlowable(BackpressureStrategy.LATEST);

Flux<SensorEvent> events = Flux.from(flowable);
~~~

Trong ví dụ, `LATEST` giữ giá trị mới nhất khi downstream chưa theo kịp. Điều này có thể phù hợp với telemetry hiển thị trạng thái hiện tại, nhưng có thể bỏ qua các event trung gian. Nếu mọi event đều cần được xử lý hoặc kiểm toán, `LATEST` không phù hợp.

Các chính sách thường gặp:

| BackpressureStrategy | Hành vi | Trường hợp cần cân nhắc |
| --- | --- | --- |
| `BUFFER` | Đệm các phần tử chờ demand | Chỉ dùng khi lượng dữ liệu có giới hạn hoặc buffer được kiểm soát; có thể tăng bộ nhớ |
| `LATEST` | Giữ phần tử mới nhất, thay thế giá trị chờ trước đó | Snapshot/trạng thái mà chỉ giá trị mới nhất quan trọng |
| `DROP` | Bỏ phần tử đến khi downstream chưa sẵn sàng | Dữ liệu có thể mất mà nghiệp vụ vẫn chấp nhận |
| `ERROR` | Báo lỗi khi không thể phát theo demand | Muốn phát hiện nguồn nhanh hơn consumer và xử lý overflow rõ ràng |
| `MISSING` | Không áp dụng chiến lược tại điểm chuyển đổi | Khi sẽ tự cấu hình xử lý backpressure ở bước downstream |

`BUFFER` không phải giải pháp vô hạn an toàn. Nếu producer liên tục nhanh hơn consumer, hàng đợi có thể tăng đến khi cạn heap. `DROP` và `LATEST` chủ động đánh đổi tính đầy đủ dữ liệu. `ERROR` làm vấn đề quá tải trở nên quan sát được nhưng cần chính sách xử lý lỗi. Chọn chiến lược theo ý nghĩa dữ liệu, tốc độ nguồn và ngân sách bộ nhớ.

### Ví dụ phát hiện overflow

~~~java
Flowable<SensorEvent> checked = observable
    .toFlowable(BackpressureStrategy.ERROR);

Flux<SensorEvent> events = Flux.from(checked);
~~~

Nếu nguồn phát nhanh hơn khả năng tiêu thụ và không thể tuân thủ demand, downstream có thể nhận lỗi backpressure. Có thể đặt `onErrorResume` để chuyển sang trạng thái lỗi hoặc kích hoạt cảnh báo, nhưng không nên âm thầm bỏ lỗi nếu điều đó làm mất dữ liệu quan trọng.

## 6. Chuyển đổi Single, Maybe và Completable

RxJava `Single<T>` đại diện cho một kết quả hoặc lỗi; `Maybe<T>` đại diện cho không hoặc một kết quả. Chúng có thể chuyển thành publisher một phần tử để dùng trong Reactor:

~~~java
Mono<User> user = Mono.from(
    legacyUserClient.findUser(userId).toFlowable()
);

Mono<Profile> maybeProfile = Mono.from(
    legacyProfileClient.findProfile(userId).toFlowable()
);
~~~

Với `Maybe`, `toFlowable()` có thể hoàn tất rỗng nếu không có giá trị. Vì vậy, `Mono.from(maybe.toFlowable())` giữ được semantics không hoặc một phần tử. Với `Single`, thành công luôn phát một giá trị; lỗi được chuyển thành onError.

`Completable` chỉ biểu diễn hoàn tất hoặc lỗi. Khi cần nối nó vào pipeline Reactor, có thể chuyển qua publisher hoàn tất của RxJava hoặc dùng adapter tương ứng trong phiên bản thư viện. Hãy kiểm tra kiểu generic mà API chuyển đổi trả về và chỉ quan tâm terminal signal, không tạo một giá trị giả nếu nghiệp vụ không cần.

Với `Single`, `Maybe` và `Completable`, cần xác định cách ánh xạ empty, success và error sang Mono. Không giả định tất cả các kiểu đều có thể thay thế cho nhau: Single không có nhánh empty, còn Maybe có thể complete mà không phát giá trị.

## 7. Demand và cancellation qua ranh giới thư viện

Một adapter đúng chuẩn Reactive Streams phải chuyển tiếp demand và cancellation:

- Reactor subscriber gọi `request(n)`; yêu cầu được truyền tới publisher RxJava.
- Reactor subscriber hủy; subscription upstream được cancel.
- RxJava phát `onNext`, `onError` hoặc `onComplete`; Reactor nhận cùng loại tín hiệu.
- Không publisher nào được phát `null` qua `onNext`.

Ví dụ, một consumer Reactor chỉ yêu cầu hai phần tử đầu:

~~~java
Flux<Integer> values = Flux.from(
    Flowable.range(1, 100)
);

StepVerifier.create(values, 2)
    .expectNext(1, 2)
    .thenCancel()
    .verify();
~~~

Downstream chỉ yêu cầu hai phần tử rồi hủy. Cancellation cần đi qua adapter đến Flowable để nguồn có cơ hội dừng. Nếu nguồn thực hiện một side effect không thể hủy, ví dụ request đã gửi đến hệ thống bên ngoài, cancellation không tự đảo ngược side effect đó.

Khi tích hợp một publisher tự viết hoặc một adapter không chuẩn, cần kiểm tra nó có tôn trọng demand, phát tín hiệu tuần tự và dừng sau cancel hay không. Việc hai thư viện cùng có kiểu Publisher không sửa được lỗi trong implementation của publisher tùy chỉnh.

## 8. Scheduler của hai thư viện không tự hợp nhất

RxJava và Reactor đều có scheduler riêng:

| Ý định | RxJava | Reactor |
| --- | --- | --- |
| Điều phối subscription/source | `subscribeOn(...)` | `subscribeOn(...)` |
| Chuyển nơi chạy tín hiệu downstream | `observeOn(...)` | `publishOn(...)` |
| Scheduler cho tính toán CPU | `Schedulers.computation()` | `Schedulers.parallel()` |
| Scheduler cho tác vụ blocking | `Schedulers.io()` hoặc scheduler phù hợp | `Schedulers.boundedElastic()` |

Khi chuyển Flowable sang Flux, các ranh giới scheduler đã đặt trong RxJava vẫn có tác dụng với phần upstream RxJava. Nếu thêm `publishOn` trong Reactor, đó là một lần chuyển scheduler nữa ở phía Reactor. Hai hệ thống scheduler không tự động gộp thành một scheduler chung.

Ví dụ:

~~~java
Flowable<Integer> rxSource = Flowable.range(1, 10)
    .observeOn(io.reactivex.rxjava3.schedulers.Schedulers.computation())
    .map(this::cpuTransform);

Flux<Integer> reactorPipeline = Flux.from(rxSource)
    .publishOn(reactor.core.scheduler.Schedulers.parallel())
    .map(this::enrich);
~~~

Ví dụ có hai ranh giới chuyển thread. Chúng có thể cần thiết nếu mỗi thư viện sở hữu một giai đoạn công việc riêng, nhưng cũng có thể tạo thêm context switch và hàng đợi. Khi thiết kế tích hợp, hãy xác định thư viện nào sở hữu từng giai đoạn, tránh đặt `observeOn` và `publishOn` lặp lại chỉ vì thói quen.

`subscribeOn` ở một phía có thể ảnh hưởng thread đăng ký publisher ở phía kia vì subscription đi qua adapter. Tuy nhiên, nếu cả RxJava và Reactor đều đặt subscribeOn, thứ tự operator và thời điểm subscribe sẽ quyết định tác động thực tế. Chỉ đặt ranh giới scheduler tại nơi cần kiểm soát thread; không dùng scheduler để che giấu một API blocking mà chưa xác định rõ.

## 9. Truyền lỗi qua adapter

`onError` là terminal signal của Reactive Streams. Nếu RxJava Flowable phát lỗi, Flux nhận lỗi tương ứng; nếu Reactor Flux phát lỗi, Flowable nhận lỗi tương ứng. Có thể xử lý lỗi ở phía thư viện sở hữu logic nghiệp vụ hoặc tại adapter tùy hợp đồng:

~~~java
Flux<Order> orders = Flux.from(legacyOrderClient.findOrders())
    .onErrorMap(
        LegacyClientException.class,
        error -> new OrderLookupException("Không thể tải đơn hàng", error)
    );
~~~

Ví dụ chuyển lỗi riêng của thư viện cũ sang exception miền nghiệp vụ để phần Reactor không phụ thuộc kiểu lỗi nội bộ. Không nên đổi mọi lỗi thành empty hoặc giá trị mặc định nếu consumer cần phân biệt lỗi hệ thống với không có dữ liệu.

Thứ tự retry và fallback cũng quan trọng. Retry đặt trước adapter hoặc sau adapter đều có thể subscribe lại publisher upstream, nhưng chính sách retry chỉ có ý nghĩa nếu nguồn cho phép thực hiện lại an toàn. Với thao tác có side effect, retry có thể lặp giao dịch hoặc gửi message hai lần; cần idempotency key hoặc cơ chế đối soát.

Khi cancellation và error xảy ra đồng thời, lỗi đến sau khi downstream đã hủy có thể không còn được chuyển cho subscriber. Một số thư viện có cơ chế báo lỗi không thể giao (undeliverable error) qua global error handler. Cần cấu hình handler ở cấp ứng dụng và ghi nhận lỗi này, thay vì giả định mọi exception luôn đến được `onError` của consumer cuối.

## 10. Hot/cold behavior không đổi chỉ vì chuyển thư viện

Adapter không tự biến nguồn hot thành cold hoặc ngược lại:

- Một `Flowable.defer(...)` có thể tạo nguồn mới cho mỗi subscription; chuyển nó thành Flux vẫn giữ đặc tính đó.
- Một Flowable hot có thể phát trước khi Flux subscriber đăng ký; adapter không tự replay dữ liệu đã bỏ lỡ.
- Một Flux cold chuyển thành Flowable vẫn có thể thực thi lại mỗi lần subscribe.
- `share`, `publish`, `replay` hoặc `cache` có thể thay đổi lifecycle ở vị trí được áp dụng, nhưng phải chọn rõ chính sách đó.

Ví dụ chuyển một Flowable hot:

~~~java
Flowable<Notification> hotNotifications = notificationBus.events();

Flux<Notification> notifications =
    Flux.from(hotNotifications);
~~~

Nếu `notificationBus` không replay, subscriber Reactor đăng ký muộn chỉ nhận notification phát sau thời điểm tham gia. Nếu cần trạng thái gần nhất hoặc lịch sử, phải yêu cầu nguồn cung cấp replay/snapshot hoặc áp dụng chính sách lưu giữ phù hợp.

## 11. Tích hợp theo ranh giới module

Trong hệ thống có cả RxJava và Reactor, nên xác định một thư viện làm mô hình chính cho từng module. Ví dụ, một adapter bao quanh SDK RxJava có thể trả `Flux<T>` cho phần còn lại của ứng dụng Reactor:

~~~java
final class RxJavaPaymentAdapter {
    private final LegacyPaymentClient client;

    Flux<PaymentEvent> paymentEvents() {
        return Flux.from(client.paymentEvents());
    }

    Mono<PaymentResult> charge(ChargeCommand command) {
        return Mono.from(client.charge(command).toFlowable());
    }
}
~~~

Đoạn mã giả định `paymentEvents()` trả `Flowable<PaymentEvent>` và `charge()` trả kiểu RxJava `Maybe<PaymentResult>` hoặc một kiểu có `toFlowable()` phù hợp. Nếu `charge()` là Single, kết quả luôn có một giá trị khi thành công; nếu là Maybe, nó có thể hoàn tất rỗng. Adapter cần giữ đúng khác biệt đó.

Ranh giới module nên chịu trách nhiệm:

- Chuyển kiểu publisher.
- Ánh xạ exception nội bộ sang exception của module.
- Chọn backpressure strategy nếu nguồn là Observable.
- Quy định scheduler nếu SDK có yêu cầu thread cụ thể.
- Giữ nguyên semantics empty, cancellation và hot/cold.
- Định nghĩa test contract cho adapter.

Không nên để kiểu RxJava lan vào mọi tầng của ứng dụng Reactor nếu phần lớn code chỉ cần Mono/Flux. Ngược lại, nếu module hiện tại đã chuẩn hóa RxJava, đừng chuyển qua lại giữa hai thư viện trong từng method mà không có lợi ích cụ thể.

## 12. Kiểm thử adapter hai chiều

Kiểm thử nên xác minh cả dữ liệu lẫn hợp đồng subscription. Có thể dùng `StepVerifier` cho publisher Reactor và `TestSubscriber` cho RxJava.

### RxJava Flowable sang Reactor Flux

~~~java
Flowable<Integer> rxSource = Flowable.range(1, 3)
    .map(value -> value * 2);

Flux<Integer> reactorSource = Flux.from(rxSource);

StepVerifier.create(reactorSource)
    .expectNext(2, 4, 6)
    .verifyComplete();
~~~

Test xác minh các phần tử và thứ tự được chuyển tiếp.

### Reactor Flux sang RxJava Flowable

~~~java
Flux<Integer> reactorSource = Flux.range(1, 3)
    .map(value -> value + 10);

Flowable<Integer> rxSource =
    Flowable.fromPublisher(reactorSource);

TestSubscriber<Integer> subscriber = new TestSubscriber<>(0L);
rxSource.subscribe(subscriber);

subscriber.assertNoValues();
subscriber.requestMore(2);
subscriber.assertValues(11, 12);
subscriber.cancel();
~~~

Subscriber bắt đầu với demand bằng 0, sau đó yêu cầu hai phần tử và hủy. Test này giúp kiểm tra publisher có tôn trọng demand qua adapter. Có thể bổ sung assertion về trạng thái hoàn tất hoặc cancellation tùy nguồn.

### Kiểm thử chính sách Observable

Với Observable chuyển thành Flowable, hãy test trường hợp producer nhanh hơn consumer và xác minh strategy:

- `ERROR`: consumer nhận lỗi backpressure theo kịch bản overflow.
- `DROP`: chỉ nhận các phần tử đến khi demand không đủ theo semantics của strategy.
- `LATEST`: nhận giá trị mới nhất còn lại sau khi downstream sẵn sàng.
- `BUFFER`: nhận đủ phần tử trong test có lượng dữ liệu hữu hạn, đồng thời kiểm tra giới hạn tải trong bài test áp lực.

Không dùng test đồng bộ với nguồn nhỏ để kết luận `BUFFER` an toàn trong production. Cần test lượng dữ liệu lớn hoặc tốc độ producer/consumer chênh lệch để phát hiện nguy cơ tăng hàng đợi.

## 13. Những lỗi thường gặp

- **Đưa Observable trực tiếp vào Flux.from:** Observable không phải Reactive Streams Publisher; chuyển qua Flowable và chọn backpressure strategy.
- **Chọn BUFFER cho nguồn vô hạn:** producer nhanh hơn consumer có thể làm bộ nhớ tăng không giới hạn.
- **Dùng LATEST cho event cần kiểm toán:** các cập nhật trung gian có thể bị thay thế và mất.
- **Nhầm Mono.from với kiểm tra đúng một phần tử:** Mono.from lấy phần tử đầu tiên rồi hủy upstream; nó không xác minh nguồn chỉ phát một phần tử.
- **Cho rằng adapter đổi hot thành cold:** hot/cold behavior thuộc nguồn và operator chia sẻ/replay, không thuộc tên kiểu đích.
- **Đặt scheduler ở cả hai thư viện mà không có lý do:** observeOn và publishOn có thể tạo nhiều hàng đợi và context switch.
- **Nuốt lỗi thành empty:** consumer không phân biệt được không có dữ liệu với lỗi nguồn.
- **Giả định cancel đảo ngược side effect:** request đã gửi hoặc giao dịch đã commit cần idempotency/compensation riêng.
- **Trộn RxJava 2 và RxJava 3:** package và dependency khác nhau; thống nhất phiên bản hoặc dùng adapter chuyên dụng.
- **Để kiểu RxJava lan qua toàn ứng dụng Reactor:** adapter ở ranh giới giúp module có hợp đồng nhất quán.
- **Không kiểm thử demand:** test chỉ xác minh giá trị có thể bỏ sót lỗi backpressure hoặc cancellation.
- **Bỏ qua undeliverable error:** lỗi đến sau cancellation cần được quan sát ở global error handler phù hợp.

## 14. Quy trình chọn cách tích hợp

Trước khi nối RxJava với Reactor, hãy xác định:

1. Nguồn đang là `Flowable`, `Observable`, `Single`, `Maybe` hay `Completable`?
2. Nguồn có triển khai Reactive Streams Publisher không?
3. Nếu là Observable, dữ liệu có được phép buffer, drop, latest hoặc phát lỗi overflow không?
4. Consumer cần toàn bộ stream, tối đa một phần tử hay một kết quả đơn?
5. Nguồn là cold hay hot? Subscriber đến muộn cần replay hay snapshot không?
6. Demand và cancellation có được truyền qua adapter đúng không?
7. Scheduler nào sở hữu từng giai đoạn? Có ranh giới observeOn/publishOn thừa không?
8. Lỗi có cần ánh xạ, retry hoặc fallback không? Retry có an toàn với side effect không?
9. Adapter có giữ đúng semantics empty, error và complete không?
10. Test có kiểm tra dữ liệu, demand, cancellation, backpressure và lỗi không?

RxJava và Reactor có thể kết hợp tự nhiên khi dùng Reactive Streams làm hợp đồng chung. `Flowable` là cầu nối trực tiếp: dùng `Flux.from(flowable)` để đưa RxJava vào Reactor và `Flowable.fromPublisher(flux)` để đưa Reactor sang RxJava. `Mono.from` phù hợp khi chỉ cần tối đa một phần tử. Với `Observable`, phải chuyển thành Flowable và chọn chiến lược backpressure theo ý nghĩa dữ liệu. Adapter không tự thay đổi hot/cold behavior, scheduler, lỗi hay lifecycle của nguồn. Hãy đặt ranh giới chuyển đổi rõ ràng, giữ một mô hình chính cho mỗi module và kiểm thử demand, cancellation cùng terminal signal để việc tích hợp không làm mất các bảo đảm của Reactive Streams.
