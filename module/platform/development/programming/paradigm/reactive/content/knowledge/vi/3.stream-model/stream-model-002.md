# Phần tử dữ liệu và tín hiệu điều khiển trong một luồng

Khi quan sát một luồng reactive, ta thường chú ý đến những giá trị mà ứng dụng nhận được: số đơn hàng, nhiệt độ, thông điệp hoặc kết quả tìm kiếm. Tuy nhiên, một luồng trong Reactive Streams còn có các tín hiệu giao thức để hai phía phối hợp việc đăng ký, yêu cầu dữ liệu, hủy đăng ký và kết thúc luồng.

Phân biệt hai nhóm này giúp đọc đúng hành vi của Publisher và Subscriber:

- **Phần tử dữ liệu** là giá trị kiểu `T` được Publisher phát cho Subscriber thông qua `onNext(value)`.
- **Tín hiệu và thao tác điều khiển** quản lý vòng đời subscription và nhu cầu nhận dữ liệu, chẳng hạn `onSubscribe`, `request(n)`, `cancel()`, `onError` và `onComplete`.

Các thao tác điều khiển không phải là phần tử dữ liệu của luồng. Chúng là một phần của giao thức để luồng hoạt động đúng, đặc biệt khi tốc độ phát và tốc độ tiêu thụ khác nhau.

## 1. Một luồng có dữ liệu và có giao thức

Giả sử một dịch vụ phát các mã đơn hàng mới. Các mã như `ORD-101`, `ORD-102` và `ORD-103` là dữ liệu. Subscriber có thể xử lý từng mã để cập nhật màn hình hoặc tính tổng số đơn hàng.

Nhưng trước khi nhận được dữ liệu, Subscriber cần đăng ký với Publisher. Publisher gửi một Subscription để Subscriber có thể yêu cầu số phần tử muốn nhận. Khi không cần nhận thêm, Subscriber có thể hủy subscription. Khi nguồn dữ liệu kết thúc, Publisher báo hoàn tất hoặc báo lỗi.

Vì vậy, một luồng reactive không chỉ là danh sách các giá trị. Nó còn có một giao thức trao đổi tín hiệu giữa hai phía:

~~~mermaid
sequenceDiagram
    participant S as Subscriber
    participant P as Publisher
    participant U as Subscription

    S->>P: subscribe(subscriber)
    P->>S: onSubscribe(subscription)
    S->>U: request(2)
    P-->>S: onNext(ORD-101)
    P-->>S: onNext(ORD-102)
    S->>U: request(1)
    P-->>S: onNext(ORD-103)
    P-->>S: onComplete()
~~~

Trong sơ đồ, ba mã đơn hàng là phần tử dữ liệu. Các lời gọi đăng ký, yêu cầu dữ liệu và tín hiệu kết thúc điều khiển cách Subscriber tham gia vào luồng.

## 2. Các thành phần và hướng truyền tín hiệu

Reactive Streams dành cho Java định nghĩa bốn giao diện chính:

| Thành phần | Vai trò |
|---|---|
| `Publisher<T>` | Cung cấp dữ liệu cho Subscriber đã đăng ký. |
| `Subscriber<T>` | Nhận phần tử dữ liệu và các tín hiệu vòng đời. |
| `Subscription` | Đại diện cho một lần đăng ký; cho phép yêu cầu dữ liệu hoặc hủy đăng ký. |
| `Processor<T, R>` | Vừa là Subscriber nhận `T`, vừa là Publisher phát `R`. |

Các tín hiệu và thao tác đi theo hai hướng:

| Hướng | Tên | Ý nghĩa |
|---|---|---|
| Subscriber gọi Publisher | `subscribe(subscriber)` | Bắt đầu một lần đăng ký. |
| Publisher gọi Subscriber | `onSubscribe(subscription)` | Báo rằng subscription đã được thiết lập và trao Subscription cho Subscriber. |
| Subscriber gọi Subscription | `request(n)` | Báo nhu cầu nhận thêm tối đa `n` phần tử. |
| Subscriber gọi Subscription | `cancel()` | Yêu cầu hủy đăng ký và ngừng nhận dữ liệu. |
| Publisher gọi Subscriber | `onNext(value)` | Phát một phần tử dữ liệu kiểu `T`. |
| Publisher gọi Subscriber | `onError(error)` | Kết thúc luồng bằng lỗi. |
| Publisher gọi Subscriber | `onComplete()` | Kết thúc luồng bình thường. |

`subscribe` là phương thức đăng ký trên Publisher. Sau đó, Publisher gọi `onSubscribe` để chuyển Subscription cho Subscriber. Subscriber sử dụng Subscription này để gọi `request` hoặc `cancel`.

Trong các callback của Subscriber, `onNext` là tín hiệu mang phần tử dữ liệu. `onSubscribe` là bước bắt tay giao thức. `onError` và `onComplete` là hai tín hiệu kết thúc. Ở chiều ngược lại, `request` và `cancel` là thao tác điều khiển do Subscriber gửi qua Subscription.

## 3. Phần tử dữ liệu được phát qua onNext

`onNext(T value)` mang một giá trị thuộc kiểu dữ liệu của Publisher. Ví dụ, với `Flux<OrderEvent>`, mỗi lần gọi `onNext` chuyển một `OrderEvent` đến Subscriber:

~~~java
import reactor.core.publisher.Flux;

Flux<OrderEvent> events = eventSource.events();

events.subscribe(event -> {
    orderProjection.apply(event);
});
~~~

Trong ví dụ này, mỗi `event` là một phần tử dữ liệu. Logic trong lambda xử lý giá trị đó. Đoạn `subscribe(Consumer)` là cách đăng ký tiện lợi của Reactor; nó không làm cho các phần tử dữ liệu trở thành tín hiệu điều khiển.

Một số quy tắc quan trọng của phần tử dữ liệu:

- Mỗi lần gọi `onNext(value)` mang một phần tử.
- `value` không được là `null` theo hợp đồng Reactive Streams.
- Publisher chỉ được phát số phần tử phù hợp với demand hiện có của Subscriber.
- Các lời gọi tín hiệu của một subscription phải được phát tuần tự, không chồng lấn theo cách vi phạm hợp đồng.
- Sau tín hiệu kết thúc `onComplete` hoặc `onError`, Publisher không được phát thêm `onNext` cho subscription đó.

Phần tử dữ liệu có thể là một object phức tạp, một chuỗi, một số hoặc một sự kiện miền nghiệp vụ. Reactive Streams không áp đặt cấu trúc nội dung của `T`; ứng dụng quyết định kiểu dữ liệu và ý nghĩa nghiệp vụ.

## 4. Tín hiệu vòng đời và điều khiển subscription

### onSubscribe: bước bắt tay

Publisher gọi `onSubscribe(subscription)` để báo Subscriber rằng một subscription đã được tạo. Đây là callback đầu tiên mà Publisher phải gọi trên Subscriber cho lần đăng ký đó. Subscriber có thể giữ Subscription để yêu cầu dữ liệu hoặc hủy đăng ký sau này.

~~~java
import org.reactivestreams.Subscription;

@Override
public void onSubscribe(Subscription subscription) {
    this.subscription = subscription;
    subscription.request(5);
}
~~~

Trong ví dụ, Subscriber giữ tham chiếu đến Subscription và yêu cầu năm phần tử. Lời gọi `request(5)` không phát ra năm giá trị ngay tại chỗ của Subscriber; nó thông báo lượng demand mà Publisher cần tôn trọng khi phát dữ liệu.

### request(n): báo nhu cầu dữ liệu

`request(n)` là thao tác điều khiển backpressure. Tham số `n` biểu thị số phần tử Subscriber có thể nhận thêm. Nếu Subscriber gọi `request(5)`, Publisher có thể phát tối đa năm phần tử theo nhu cầu đó; Publisher có thể phát ít hơn nếu nguồn kết thúc sớm hoặc hiện chưa có dữ liệu.

Nhiều lần gọi request được cộng dồn vào nhu cầu chưa được đáp ứng. Ví dụ, nếu Subscriber yêu cầu hai phần tử rồi yêu cầu thêm ba phần tử trước khi nhận dữ liệu, tổng demand là năm phần tử. `request(Long.MAX_VALUE)` được dùng để biểu thị nhu cầu không giới hạn thực tế.

Demand đếm số lần phát `onNext`, không đếm các tín hiệu `onSubscribe`, `onError` hoặc `onComplete`. Tín hiệu kết thúc có thể được phát khi không còn phần tử dữ liệu nào cần gửi, kể cả khi Subscriber chưa dùng hết demand đã yêu cầu.

`request(0)` hoặc yêu cầu số âm vi phạm hợp đồng. Publisher phải báo lỗi `IllegalArgumentException` qua `onError`. Vì vậy, Subscriber cần yêu cầu một số dương khi muốn nhận phần tử.

### cancel(): yêu cầu ngừng nhận dữ liệu

`cancel()` cho Publisher biết Subscriber không còn quan tâm đến subscription. Publisher cần ngừng phát tín hiệu cho subscription đã bị hủy và giải phóng tài nguyên có thể giải phóng.

~~~java
subscription.cancel();
~~~

Hủy subscription là thao tác một chiều, không có callback xác nhận riêng như `onCancelled` trong giao diện Reactive Streams. Subscriber không nên chờ `onComplete` như một lời xác nhận hủy. Việc hủy cũng có thể cạnh tranh với một tín hiệu đang được phát; do đó, ứng dụng cần thiết kế để xử lý đúng việc subscription kết thúc và không dựa vào một thứ tự đồng bộ tức thời ở mọi tầng bên dưới.

## 5. onError và onComplete: hai cách kết thúc luồng

Một subscription kết thúc bằng một trong hai tín hiệu:

- `onComplete()` báo Publisher đã phát xong dữ liệu bình thường.
- `onError(Throwable error)` báo Publisher kết thúc vì lỗi.

Hai tín hiệu này là tín hiệu vòng đời, không phải phần tử dữ liệu `T`. Sau khi một trong hai tín hiệu được phát, subscription đã ở trạng thái kết thúc và không được phát thêm `onNext` hoặc tín hiệu kết thúc thứ hai.

Điều đó có nghĩa là một luồng không nhất thiết phải phát phần tử dữ liệu mới có thể kết thúc. Ví dụ:

~~~java
Flux<String> noValues = Flux.empty();
Mono<String> failed = Mono.error(new IllegalStateException("catalog unavailable"));
Mono<Void> completed = Mono.empty();
~~~

`Flux.empty()` hoàn tất mà không phát `onNext`. `Mono.error(...)` kết thúc bằng `onError` mà không phát giá trị. `Mono.empty()` cũng hoàn tất bình thường mà không có phần tử dữ liệu. Đây là những trường hợp hữu ích khi thao tác chỉ biểu thị việc hoàn tất hoặc lỗi.

Trong ứng dụng, có thể quan sát hai tín hiệu kết thúc để ghi log hoặc cập nhật trạng thái:

~~~java
events
    .doOnComplete(() -> log.info("Luồng đã hoàn tất"))
    .doOnError(error -> log.warn("Luồng kết thúc do lỗi", error))
    .subscribe(this::handleEvent, this::handleError);
~~~

`doOnComplete` và `doOnError` là toán tử quan sát trong Reactor. Chúng không thay thế tín hiệu kết thúc và không biến lỗi thành dữ liệu. Nếu cần chuyển lỗi thành một giá trị miền nghiệp vụ, hãy dùng các toán tử xử lý lỗi như `onErrorResume` một cách có chủ đích.

## 6. Backpressure: liên hệ giữa dữ liệu và demand

Backpressure là cơ chế để Subscriber kiểm soát lượng phần tử dữ liệu mà Publisher được phép phát. Nó tách hai việc:

- Publisher có dữ liệu để phát hay không.
- Subscriber có yêu cầu nhận thêm dữ liệu hay không.

Giả sử một Subscriber chỉ xử lý một phần tử tại một thời điểm. Nó có thể yêu cầu một phần tử khi đăng ký, xử lý phần tử đó, rồi mới yêu cầu phần tử tiếp theo. Như vậy, demand phản ánh khả năng tiêu thụ của Subscriber.

~~~java
import org.reactivestreams.Subscription;
import reactor.core.publisher.BaseSubscriber;

Flux<Integer> numbers = Flux.range(1, 3);

numbers.subscribe(new BaseSubscriber<Integer>() {
    @Override
    protected void hookOnSubscribe(Subscription subscription) {
        request(1);
    }

    @Override
    protected void hookOnNext(Integer value) {
        process(value);
        request(1);
    }
});
~~~

Trong ví dụ, Subscriber yêu cầu một phần tử ban đầu. Sau khi xử lý mỗi giá trị, Subscriber mới gọi request(1) để báo có thể nhận thêm một phần tử. Với nguồn đồng bộ như `Flux.range`, việc phát có thể tiếp tục ngay khi có request mới; ví dụ không hàm ý mỗi phần tử được xử lý trên một thread riêng.

Backpressure không phải là một phần tử dữ liệu đặc biệt nằm trong `Flux<Integer>`. Nó là giao thức điều khiển lượng phần tử `onNext` được phép phát. Subscriber có thể nhận các phần tử theo nhu cầu, còn Publisher chịu trách nhiệm tuân thủ nhu cầu đó.

Cần phân biệt backpressure với một số cơ chế khác:

| Cơ chế | Điều khiển điều gì? | Ví dụ |
|---|---|---|
| Backpressure | Số phần tử Subscriber yêu cầu từ Publisher. | `request(10)` cho phép phát thêm tối đa 10 phần tử. |
| Rate limiting | Tốc độ yêu cầu hoặc phát trong một khoảng thời gian. | Giới hạn API ở 100 request mỗi giây. |
| Buffering | Tạm giữ phần tử khi tốc độ đến và tốc độ xử lý khác nhau. | Đệm một số sự kiện trước khi xử lý. |
| Sampling / dropping | Chọn hoặc bỏ phần tử theo chính sách. | Chỉ giữ mẫu nhiệt độ mới nhất mỗi giây. |

Một pipeline có backpressure vẫn có thể sử dụng buffer hoặc chính sách bỏ phần tử ở một số toán tử. Vì vậy, cần đọc chính sách cụ thể của nguồn và từng toán tử khi đánh giá bộ nhớ, độ trễ và khả năng mất dữ liệu.

## 7. Quan sát dữ liệu và tín hiệu trong Project Reactor

Project Reactor cung cấp các toán tử để quan sát nhiều thời điểm trong vòng đời của một luồng. Chúng hữu ích khi debug, ghi log hoặc đo lường hành vi pipeline.

| Toán tử | Quan sát điều gì? |
|---|---|
| `doOnSubscribe` | Có Subscriber đăng ký và nhận Subscription. |
| `doOnRequest` | Subscriber yêu cầu thêm bao nhiêu phần tử. |
| `doOnNext` | Một phần tử dữ liệu được phát. |
| `doOnError` | Luồng kết thúc do lỗi. |
| `doOnComplete` | Luồng hoàn tất bình thường. |
| `doOnCancel` | Subscription bị hủy. |
| `doFinally` | Tín hiệu kết thúc của subscription, gồm hoàn tất, lỗi hoặc hủy. |

Ví dụ kết hợp quan sát dữ liệu với điều khiển demand:

~~~java
import org.reactivestreams.Subscription;
import reactor.core.publisher.BaseSubscriber;

Flux<Integer> observed = Flux.range(1, 3)
    .doOnSubscribe(subscription -> log.info("Đã đăng ký"))
    .doOnRequest(n -> log.info("Demand: {}", n))
    .doOnNext(value -> log.info("Dữ liệu: {}", value))
    .doOnComplete(() -> log.info("Hoàn tất"))
    .doOnCancel(() -> log.info("Đã hủy"));

observed.subscribe(new BaseSubscriber<Integer>() {
    @Override
    protected void hookOnSubscribe(Subscription subscription) {
        request(1);
    }

    @Override
    protected void hookOnNext(Integer value) {
        process(value);
        request(1);
    }
});
~~~

Các hook cho thấy hai nhóm sự kiện khác nhau: `doOnNext` quan sát phần tử dữ liệu; `doOnRequest` và `doOnCancel` quan sát thao tác điều khiển. `doOnComplete` quan sát kết thúc bình thường. Nếu Subscriber yêu cầu lần lượt từng phần tử như ví dụ, log demand sẽ cho thấy các lần yêu cầu phát sinh trong quá trình tiêu thụ.

Các toán tử quan sát không nên được dùng để thay đổi nghiệp vụ hoặc tạo side effect khó kiểm soát. Chúng phù hợp cho log, metric và chẩn đoán. Việc xử lý dữ liệu vẫn nên nằm trong các toán tử biến đổi như `map`, `filter`, `flatMap` hoặc trong Subscriber xử lý phần tử.

## 8. Một số quy tắc giao thức cần nhớ

Reactive Streams đặt ra các quy tắc để Publisher và Subscriber có thể phối hợp an toàn:

1. Mỗi lần đăng ký tạo một Subscription. Publisher gọi `onSubscribe` trước các callback khác của Subscriber trong lần đăng ký đó.
2. Subscriber phải nhận Subscription trước khi có thể yêu cầu dữ liệu qua Subscription.
3. Publisher không phát nhiều phần tử hơn demand đã nhận.
4. Tín hiệu của một subscription phải được phát tuần tự.
5. `onNext` không được mang `null`.
6. Một subscription kết thúc bằng tối đa một trong hai tín hiệu `onError` hoặc `onComplete`.
7. Sau khi kết thúc, Publisher không phát thêm phần tử hoặc tín hiệu kết thúc cho subscription đó.
8. `cancel` yêu cầu Publisher ngừng phát và giải phóng tài nguyên; Subscriber không cần chờ một tín hiệu xác nhận hủy riêng.

Những quy tắc này giúp các thư viện khác nhau có thể trao đổi luồng dữ liệu theo cùng một hợp đồng. Khi một thư viện như Project Reactor triển khai Reactive Streams, các kiểu `Mono` và `Flux` cung cấp API tiện lợi, còn giao thức Publisher–Subscriber vẫn điều phối demand và vòng đời subscription.

## 9. Cách đọc một luồng khi debug

Khi quan sát log hoặc một pipeline Java, hãy lần lượt xác định:

- **Dữ liệu nào đang được phát?** Tìm kiểu `T` và các điểm `onNext` hoặc `doOnNext`.
- **Subscription được tạo lúc nào?** Quan sát `subscribe` và `onSubscribe`.
- **Subscriber đang yêu cầu bao nhiêu dữ liệu?** Tìm các lần `request(n)` hoặc `doOnRequest`.
- **Ai hủy subscription?** Tìm `cancel` hoặc `doOnCancel`; kiểm tra điều kiện khiến luồng không còn cần thiết.
- **Luồng kết thúc ra sao?** Phân biệt `onComplete` với `onError` và kiểm tra cách ứng dụng xử lý lỗi.
- **Có phần tử nào vượt quá nhu cầu hoặc xuất hiện sau khi kết thúc không?** Đây là dấu hiệu vi phạm giao thức cần được điều tra ở Publisher hoặc toán tử liên quan.

Ví dụ, nếu thấy `doOnRequest` ghi nhận demand tăng nhưng chưa có `doOnNext`, có thể nguồn chưa có dữ liệu hoặc đang chờ I/O. Nếu có `doOnCancel` khi người dùng chuyển sang màn hình khác, đó có thể là vòng đời bình thường của subscription. Nếu `onError` xuất hiện, hãy xác định lỗi được truyền tiếp, chuyển thành dữ liệu hay làm kết thúc pipeline.

Phân biệt phần tử dữ liệu và tín hiệu điều khiển giúp hiểu chính xác cách một luồng vận hành: dữ liệu mang nội dung nghiệp vụ, còn giao thức điều khiển quyết định khi nào dữ liệu được gửi, Subscriber có thể nhận bao nhiêu và subscription kết thúc như thế nào. Đây là nền tảng để đọc các pipeline Mono, Flux và hiểu cơ chế backpressure trong ứng dụng Java.

