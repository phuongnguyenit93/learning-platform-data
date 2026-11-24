# Reactive Streams

## Publisher: vai trò phát dữ liệu và tiếp nhận đăng ký

Trong mô-đun **REACTIVE_PROGRAMMING**, ta học cách tổ chức ứng dụng quanh các luồng sự kiện bất đồng bộ, hợp đồng Publisher–Subscriber và cơ chế backpressure của Reactive Streams. Ta sẽ thực hành với `Mono`, `Flux`, các toán tử kết hợp, scheduler, xử lý lỗi và kiểm thử pipeline trong hệ sinh thái Java. Để hiểu cách một luồng bắt đầu hoạt động, trước tiên cần nắm vai trò của **Publisher**: thành phần cung cấp tín hiệu dữ liệu và tiếp nhận yêu cầu đăng ký từ Subscriber.

Publisher định nghĩa một điểm đăng ký cho bên tiêu thụ. Khi Subscriber gọi `subscribe`, Publisher thiết lập một phiên trao đổi thông qua `Subscription`. Phiên này cho phép Subscriber thể hiện nhu cầu bằng `request(n)` và hủy việc nhận dữ liệu bằng `cancel()`. Publisher chịu trách nhiệm phát các tín hiệu theo hợp đồng, tôn trọng nhu cầu đã nhận và kết thúc bằng tín hiệu hoàn tất hoặc lỗi.

Publisher không đồng nghĩa với một luồng dữ liệu đã chạy ngay khi đối tượng được tạo. Trong Reactor, một `Flux<T>` hoặc `Mono<T>` có thể mô tả nguồn dữ liệu và các bước xử lý; việc đăng ký mới khởi động quá trình tương ứng với loại nguồn đó. Hiểu ranh giới này giúp ta dự đoán đúng thời điểm truy vấn, phát sự kiện và thực hiện tác dụng phụ.

### Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích vai trò và hợp đồng chính của `Publisher<T>` trong Reactive Streams.
- Đọc chữ ký `subscribe(Subscriber<? super T>)` và hiểu quan hệ generic giữa Publisher với Subscriber.
- Mô tả chuỗi đăng ký từ lời gọi `subscribe` đến `onSubscribe`, demand và các tín hiệu dữ liệu.
- Phân biệt Publisher, Subscription và Subscriber theo trách nhiệm của từng thành phần.
- Nhận biết Publisher cold, hot, hữu hạn và vô hạn trong những tình huống sử dụng khác nhau.
- Hiểu cách `Mono` và `Flux` của Reactor thể hiện hợp đồng Publisher.
- Viết Subscriber đơn giản để quan sát quá trình đăng ký và yêu cầu dữ liệu.

## 1. Publisher là điểm cung cấp dữ liệu trong giao thức

Reactive Streams là một đặc tả giao tiếp bất đồng bộ giữa bên phát dữ liệu và bên tiêu thụ dữ liệu. Đặc tả chuẩn hóa các vai trò và cách chúng trao đổi tín hiệu để những thư viện khác nhau có thể kết nối với nhau.

Publisher là phía cung cấp dữ liệu. Nó có thể lấy phần tử từ collection, đọc từ cơ sở dữ liệu, nhận sự kiện từ message broker, tạo giá trị theo thời gian hoặc kết hợp kết quả từ những Publisher khác. Publisher cung cấp phương thức để Subscriber đăng ký nhận tín hiệu.

API cốt lõi trong `org.reactivestreams` có dạng:

~~~java
public interface Publisher<T> {
    void subscribe(Subscriber<? super T> subscriber);
}
~~~

Ý nghĩa của chữ ký:

- `T` là kiểu phần tử mà Publisher có thể phát.
- `Subscriber<? super T>` cho phép đăng ký một Subscriber có thể tiêu thụ kiểu `T` hoặc một kiểu cha của `T`.
- `subscribe` tiếp nhận một Subscriber để thiết lập phiên giao tiếp. Publisher sẽ thông báo Subscription thông qua `onSubscribe` trước khi phát các tín hiệu khác.

Ví dụ, một Publisher phát `OrderEvent` có thể chấp nhận Subscriber xử lý `OrderEvent`, hoặc một Subscriber nhận kiểu cha chung như `DomainEvent` nếu quan hệ kiểu phù hợp. Quy tắc generic này giúp API linh hoạt mà vẫn giữ an toàn kiểu tại thời điểm biên dịch.

Trong Reactor, `Flux<T>` và `Mono<T>` đều triển khai hợp đồng Publisher. `Flux<T>` biểu diễn từ 0 đến nhiều phần tử, còn `Mono<T>` biểu diễn tối đa một phần tử hoặc kết thúc rỗng. Cả hai đều có thể được dùng ở nơi cần một Publisher tương ứng với kiểu phần tử.

## 2. Publisher chịu trách nhiệm gì?

Publisher không chỉ là nơi giữ một danh sách giá trị. Nó có trách nhiệm thiết lập và duy trì giao thức với từng Subscriber.

### Tiếp nhận đăng ký

Khi nhận lời gọi `subscribe(subscriber)`, Publisher tạo hoặc kết nối một phiên đăng ký thích hợp. Publisher phải gọi `onSubscribe(subscription)` trên Subscriber trước khi gửi `onNext`, `onError` hoặc `onComplete`.

Lời gọi `onSubscribe` cung cấp cho Subscriber một đối tượng `Subscription`. Đó là kênh điều khiển riêng cho phiên đăng ký này. Subscriber dùng nó để yêu cầu thêm phần tử hoặc hủy phiên.

Việc tiếp nhận đăng ký không nhất thiết có nghĩa Publisher đã đọc toàn bộ dữ liệu hoặc đã hoàn thành công việc. Nó chỉ thiết lập quan hệ để hai phía bắt đầu trao đổi theo giao thức.

### Phát tín hiệu dữ liệu theo nhu cầu

Sau khi đăng ký, Publisher không được tùy ý phát số phần tử vượt quá nhu cầu đã được Subscriber yêu cầu. Nếu Subscriber gọi `request(5)`, Publisher có thể phát tối đa năm phần tử qua `onNext` cho Subscription đó, trừ khi luồng kết thúc sớm bằng `onComplete` hoặc `onError`.

Quy tắc này là nền tảng của backpressure. Bên tiêu thụ báo khả năng tiếp nhận; bên phát điều chỉnh lượng dữ liệu theo demand. Publisher phải theo dõi demand và bảo đảm không phát vượt số phần tử đã được yêu cầu.

### Kết thúc hoặc báo lỗi

Một luồng có thể kết thúc bình thường bằng `onComplete()`, hoặc kết thúc do lỗi bằng `onError(Throwable)`. Khi đã phát tín hiệu kết thúc, Publisher không được phát thêm phần tử hay một tín hiệu kết thúc khác trên cùng Subscription.

Một Publisher hữu hạn có thể phát một số phần tử rồi hoàn tất. Một Publisher vô hạn có thể tiếp tục phát cho tới khi Subscriber hủy hoặc xảy ra lỗi. Một Publisher có thể hoàn tất ngay mà không phát phần tử nào; đây là trường hợp luồng rỗng.

### Tôn trọng cancellation

Subscriber có thể gọi `cancel()` để thông báo rằng nó không còn muốn nhận dữ liệu. Publisher cần dừng hoặc thu hẹp công việc có thể dừng, giải phóng tài nguyên gắn với Subscription và không tiếp tục gửi tín hiệu tới Subscriber đã hủy.

Cancellation là tín hiệu điều khiển bất đồng bộ. Nó không bảo đảm hoàn tác một tác dụng phụ đã xảy ra, chẳng hạn một lệnh ghi đã được cơ sở dữ liệu xác nhận hoặc một HTTP request đã được dịch vụ từ xa xử lý.

## 3. Trình tự đăng ký và phát tín hiệu

Một phiên trao đổi cơ bản diễn ra theo trình tự:

~~~mermaid
sequenceDiagram
    participant C as Mã ứng dụng
    participant P as Publisher
    participant S as Subscriber
    participant U as Subscription
    C->>P: subscribe(S)
    P->>S: onSubscribe(U)
    S->>U: request(2)
    U->>P: cập nhật demand
    P-->>S: onNext(item 1)
    P-->>S: onNext(item 2)
    S->>U: request(3)
    U->>P: cập nhật demand
    P-->>S: onNext(item 3)
    P-->>S: onNext(item 4)
    P-->>S: onNext(item 5)
    P-->>S: onComplete()
~~~

Các bước có thể được diễn giải như sau:

1. Mã ứng dụng gọi `publisher.subscribe(subscriber)`.
2. Publisher thiết lập Subscription và gọi `subscriber.onSubscribe(subscription)`.
3. Subscriber quyết định lượng dữ liệu nó sẵn sàng nhận bằng `subscription.request(n)`.
4. Publisher phát tối đa số phần tử tương ứng với demand đã nhận.
5. Subscriber có thể yêu cầu thêm, hoặc hủy Subscription khi không cần nhận tiếp.
6. Publisher kết thúc luồng bằng `onComplete` hoặc `onError` khi điều kiện kết thúc xảy ra.

Trong thực tế, các bước có thể diễn ra đồng bộ trên cùng thread hoặc bất đồng bộ qua scheduler, executor hay event loop. Không nên giả định rằng lời gọi `subscribe` luôn trả về trước khi Subscriber nhận phần tử đầu tiên. Điều cần dựa vào là hợp đồng tín hiệu và demand, không phải một lịch thực thi thread cố định.

## 4. Một Publisher có thể nhận nhiều Subscriber

Một Publisher có thể được nhiều Subscriber đăng ký. Mỗi lần đăng ký tạo một quan hệ Subscription riêng, với demand và cancellation độc lập.

~~~mermaid
flowchart TD
    P[Publisher]
    P --> U1[Subscription A]
    P --> U2[Subscription B]
    P --> U3[Subscription C]
    U1 --> S1[Subscriber A]
    U2 --> S2[Subscriber B]
    U3 --> S3[Subscriber C]
~~~

Ví dụ, cùng một Publisher được hai Subscriber đăng ký:

~~~java
Flux<String> messages = Flux.just("created", "paid", "shipped");

messages.subscribe(value -> log.info("Audit: {}", value));
messages.subscribe(value -> log.info("Metrics: {}", value));
~~~

Với nguồn cold như `Flux.just`, mỗi subscription thông thường nhận một lần thực thi độc lập của nguồn và thấy các phần tử từ đầu. Subscriber đầu tiên không tiêu thụ mất dữ liệu của Subscriber thứ hai.

Tuy nhiên, hành vi này phụ thuộc loại Publisher. Một nguồn hot có thể phát sự kiện độc lập với thời điểm Subscriber đăng ký. Subscriber đến muộn chỉ nhận các sự kiện từ thời điểm nó tham gia, trừ khi nguồn hỗ trợ replay hoặc lưu trữ. Vì vậy, khi thiết kế nguồn, cần xác định rõ liệu mỗi Subscriber có nhận một luồng độc lập hay cùng quan sát một luồng sự kiện đang diễn ra.

Cũng cần lưu ý rằng nhiều Subscription có thể đồng nghĩa với nhiều lần thực hiện tác dụng phụ. Nếu Publisher cold bọc một truy vấn cơ sở dữ liệu, hai subscription có thể tạo hai truy vấn. Nếu Publisher phát lệnh thanh toán, việc đăng ký hai lần có thể kích hoạt hai lần thanh toán. Muốn chia sẻ một lần thực thi hoặc một kết quả, cần dùng cơ chế chia sẻ phù hợp và hiểu vòng đời của nó.

## 5. Publisher cold và hot

Hai cách tổ chức nguồn thường gặp là cold Publisher và hot Publisher.

| Đặc điểm | Cold Publisher | Hot Publisher |
|---|---|---|
| Thời điểm nguồn phát | Thường bắt đầu theo từng subscription | Có thể phát độc lập với subscription cụ thể |
| Dữ liệu Subscriber mới nhận | Thường bắt đầu từ đầu nguồn | Thường chỉ nhận sự kiện từ khi đăng ký |
| Ví dụ | `Flux.fromIterable(list)`, `Mono.fromCallable(...)` | Sự kiện từ UI, cảm biến hoặc luồng broker đang chạy |
| Số lần thực thi | Thường một lần cho mỗi subscription | Phụ thuộc nguồn và chính sách chia sẻ |
| Vấn đề cần quan tâm | Tránh lặp tác dụng phụ ngoài ý muốn | Xử lý Subscriber đến muộn và chính sách replay/buffer |

Ví dụ nguồn cold:

~~~java
Flux<Integer> cold = Flux.defer(() -> {
    log.info("Create a source for this subscriber");
    return Flux.range(1, 3);
});

cold.subscribe(value -> log.info("A: {}", value));
cold.subscribe(value -> log.info("B: {}", value));
~~~

Mỗi subscription gọi supplier trong `defer` và tạo một luồng mới. Cả A và B đều nhận các giá trị từ 1 đến 3.

Với nguồn hot, sự kiện có thể đã bắt đầu trước khi một Subscriber đăng ký. Trong Reactor, `Sinks.Many` có thể dùng để minh họa nguồn sự kiện được phát bởi một thành phần khác:

~~~java
Sinks.Many<String> sink = Sinks.many().multicast().onBackpressureBuffer();
Flux<String> hot = sink.asFlux();

hot.subscribe(value -> log.info("Listener A: {}", value));

sink.tryEmitNext("event-1");

hot.subscribe(value -> log.info("Listener B: {}", value));

sink.tryEmitNext("event-2");
~~~

Với cấu hình multicast này, Listener A nhận `event-1` và `event-2`; Listener B đăng ký sau khi `event-1` đã phát nên chỉ nhận `event-2`. Chính sách cụ thể phụ thuộc loại Sink và cấu hình buffer/replay được chọn.

Không nên xem cold luôn tốt hơn hot. Cold phù hợp khi mỗi Subscriber cần một lần tính toán hoặc đọc nguồn riêng. Hot phù hợp khi nhiều thành phần cần quan sát một luồng sự kiện đang diễn ra. Quyết định cần dựa trên ý nghĩa dữ liệu, chi phí tạo nguồn và yêu cầu về sự kiện bị bỏ lỡ.

## 6. Quan hệ giữa Publisher, Subscriber và Subscription

Ba thành phần tạo thành giao thức nhưng có trách nhiệm khác nhau:

| Thành phần | Vai trò | Phương thức / hành động chính |
|---|---|---|
| Publisher | Cung cấp luồng và tiếp nhận đăng ký | `subscribe(Subscriber)` |
| Subscriber | Nhận tín hiệu và quyết định nhu cầu | `onSubscribe`, `onNext`, `onError`, `onComplete` |
| Subscription | Điều khiển một phiên đăng ký | `request(n)`, `cancel()` |

Publisher không nhận `request(n)` trực tiếp từ Subscriber qua API `Publisher`. Subscriber nhận Subscription trong `onSubscribe`, sau đó điều khiển nhu cầu thông qua đối tượng này. Cách phân chia này cho phép mỗi Subscriber có một lượng demand và trạng thái hủy độc lập ngay cả khi nhiều Subscriber dùng chung một Publisher.

API Subscription:

~~~java
public interface Subscription {
    void request(long n);
    void cancel();
}
~~~

`request(n)` yêu cầu Publisher phát thêm tối đa `n` phần tử cho Subscription. Giá trị `n` phải dương; yêu cầu không hợp lệ phải được xử lý theo hợp đồng Reactive Streams. Các yêu cầu tích lũy được quản lý như demand còn lại, có thể tăng qua nhiều lần gọi `request`.

`cancel()` thông báo Subscriber dừng nhận tín hiệu. Việc hủy không trả về kết quả và không phải một lệnh đồng bộ bảo đảm mọi hoạt động nền đã dừng ngay tại thời điểm gọi.

## 7. Ví dụ Subscriber tự điều khiển demand

Trong Reactor, các overload `subscribe` tiện lợi thường tự yêu cầu dữ liệu để người dùng tập trung vào callback xử lý. Để nhìn rõ giao thức, ta có thể cài đặt một Subscriber từ API Reactive Streams:

~~~java
import org.reactivestreams.Subscriber;
import org.reactivestreams.Subscription;
import reactor.core.publisher.Flux;

final class TwoAtATimeSubscriber<T> implements Subscriber<T> {
    private Subscription subscription;
    private int received;

    @Override
    public void onSubscribe(Subscription subscription) {
        this.subscription = subscription;
        subscription.request(2);
    }

    @Override
    public void onNext(T value) {
        System.out.println("Received: " + value);
        received++;

        if (received % 2 == 0) {
            subscription.request(2);
        }
    }

    @Override
    public void onError(Throwable error) {
        System.err.println("Stream failed: " + error.getMessage());
    }

    @Override
    public void onComplete() {
        System.out.println("Stream completed");
    }
}

Flux.range(1, 5)
    .subscribe(new TwoAtATimeSubscriber<>());
~~~

Subscriber yêu cầu hai phần tử đầu tiên trong `onSubscribe`. Sau mỗi hai phần tử nhận được, nó yêu cầu thêm hai phần tử. Publisher có thể phát phần tử theo demand và kết thúc khi nguồn hữu hạn đã phát đủ năm phần tử.

Ví dụ trên tập trung vào minh họa giao thức. Trong ứng dụng thực tế, cần xử lý trường hợp Subscriber hủy, tránh gọi `request` sau khi đã kết thúc và bảo đảm các callback an toàn khi có tín hiệu bất đồng bộ. Không nên dùng `subscribe()` tùy tiện ở giữa một pipeline đang xây dựng vì nó tạo một subscription độc lập, tách luồng công việc khỏi chuỗi lỗi và cancellation của pipeline bên ngoài.

## 8. Publisher trong Reactor: Mono và Flux

Reactor cung cấp hai kiểu Publisher phổ biến:

- `Mono<T>`: phát tối đa một phần tử, sau đó hoàn tất; hoặc hoàn tất rỗng; hoặc kết thúc bằng lỗi.
- `Flux<T>`: phát từ không đến nhiều phần tử, sau đó hoàn tất; hoặc kết thúc bằng lỗi.

~~~java
Mono<String> one = Mono.just("hello");

Flux<String> many = Flux.just("alpha", "beta", "gamma");
~~~

Cả hai đều là Publisher, do đó có thể được truyền cho toán tử nhận Publisher, được subscribe bởi Subscriber hoặc ghép vào pipeline khác.

Một Publisher có thể được tạo từ nhiều nguồn:

~~~java
Mono<User> fromDatabase = userRepository.findById(userId);

Flux<Event> fromCollection = Flux.fromIterable(events);

Flux<Long> ticks = Flux.interval(Duration.ofSeconds(1));
~~~

Các ví dụ có đặc tính khác nhau:

- `fromDatabase` thường chỉ bắt đầu truy vấn khi có subscription theo cách triển khai repository reactive.
- `fromCollection` có thể phát lần lượt phần tử từ collection cho từng subscription.
- `ticks` là nguồn phát theo thời gian và có thể tiếp tục cho đến khi bị hủy.

Publisher cũng có thể được tạo bằng cách kết hợp nguồn khác:

~~~java
Flux<Receipt> receipts =
    orderIds
        .flatMap(orderId -> paymentClient.findReceipt(orderId), 16);
~~~

Ở đây, kết quả là một Publisher mới. Toán tử `flatMap` nhận Publisher nguồn, đăng ký với Publisher con khi có phần tử đầu vào và ghép các tín hiệu kết quả thành luồng đầu ra. Giới hạn concurrency là 16 Publisher con hoạt động đồng thời trong ví dụ.

### `subscribe` tiện lợi trong Reactor

Reactor cung cấp các overload tiện lợi:

~~~java
Flux.range(1, 3)
    .subscribe(value -> log.info("Value: {}", value));
~~~

Lời gọi trên đăng ký một Subscriber và dùng hành vi yêu cầu dữ liệu tự động của overload tiện lợi. Nó hữu ích ở điểm bắt đầu một luồng độc lập, nhưng trong chuỗi xử lý nghiệp vụ, thường nên trả về `Mono` hoặc `Flux` để caller ghép tiếp các toán tử, quản lý lỗi và quyết định subscription ở biên thích hợp.

Có hai cách dùng `subscribe` cần phân biệt:

~~~java
// Đăng ký bằng Subscriber theo hợp đồng Reactive Streams.
publisher.subscribe(customSubscriber);

// Overload tiện lợi của Reactor, trả về Disposable.
Disposable disposable = flux.subscribe(value -> process(value));
~~~

`Disposable` trong Reactor là handle tiện lợi để hủy subscription. Nó không thay thế kiểu `Subscription` trong giao thức Reactive Streams khi làm việc trực tiếp với `Subscriber`.

## 9. Các quy tắc giao thức Publisher cần giữ

Khi tự triển khai Publisher hoặc tích hợp một nguồn dữ liệu bên ngoài, cần bảo đảm những quy tắc cơ bản sau:

1. Gọi `onSubscribe` trước bất kỳ tín hiệu nào khác tới Subscriber.
2. Không phát nhiều phần tử hơn lượng demand còn lại của Subscription.
3. Các tín hiệu `onNext` của một Subscription phải được tuần tự hóa, không gọi chồng lấn đồng thời.
4. Luồng kết thúc bằng tối đa một tín hiệu `onComplete` hoặc `onError`.
5. Không phát thêm tín hiệu sau tín hiệu kết thúc hoặc sau khi Subscriber đã hủy.
6. Tôn trọng yêu cầu cancellation và giải phóng tài nguyên có thể giải phóng.
7. Không dùng `request(n)` như một cơ chế giới hạn tốc độ theo thời gian; nó biểu thị số phần tử mà Subscriber sẵn sàng nhận.

Một Publisher tự viết phải xử lý đồng bộ hóa demand và phát tín hiệu cẩn thận. Các race condition giữa `request`, `cancel` và việc nguồn phát dữ liệu có thể dẫn tới phát vượt demand, phát sau khi hủy hoặc phát tín hiệu đồng thời. Trong hầu hết ứng dụng, nên dùng các Publisher và operator đã được thư viện kiểm chứng thay vì tự xây dựng giao thức từ đầu.

## 10. Những nhầm lẫn thường gặp

- **Publisher là một collection:** collection lưu các phần tử có sẵn; Publisher mô tả hoặc cung cấp một giao thức phát tín hiệu có thể bất đồng bộ và chịu backpressure.
- **Gọi `subscribe` nghĩa là toàn bộ dữ liệu được tải ngay:** subscription thiết lập phiên trao đổi. Lượng dữ liệu được phát phụ thuộc demand và đặc tính nguồn.
- **Publisher chỉ nhận được một Subscriber:** nhiều Publisher hỗ trợ nhiều subscription độc lập; hành vi dữ liệu mỗi Subscriber nhận phụ thuộc nguồn cold hay hot.
- **Publisher tự nhận demand:** Subscriber nhận `Subscription` trong `onSubscribe` và gọi `request(n)` trên Subscription đó.
- **`request(10)` nghĩa là 10 phần tử mỗi giây:** demand là số phần tử, không phải tốc độ theo thời gian.
- **Hủy subscription sẽ hoàn tác tác vụ đã thực hiện:** cancellation yêu cầu dừng công việc còn có thể dừng; nó không đảo ngược side effect đã được xác nhận.
- **Mọi Publisher đều bắt đầu phát từ đầu cho Subscriber mới:** nguồn hot có thể đã phát sự kiện trước khi Subscriber đăng ký.
- **Gọi `subscribe` trong mọi hàm xử lý là cách ghép pipeline:** subscribe lồng nhau tạo luồng độc lập, có thể làm mất khả năng truyền lỗi, backpressure và cancellation từ pipeline ngoài.

## 11. Bài tập vận dụng

Một ứng dụng có Publisher phát sự kiện trạng thái đơn hàng. Hai thành phần cần đăng ký: một thành phần ghi audit và một thành phần cập nhật màn hình quản trị. Thành phần audit xử lý chậm hơn thành phần giao diện.

Hãy trả lời:

1. Publisher cần làm gì khi hai Subscriber cùng gọi `subscribe`?
2. Vì sao mỗi Subscriber cần một Subscription riêng?
3. Nếu Publisher là cold, hai Subscriber có thể nhận cùng toàn bộ sự kiện theo cách nào? Nếu Publisher là hot và đã phát một sự kiện trước khi Subscriber thứ hai đăng ký, điều gì có thể xảy ra?
4. Nếu audit chỉ yêu cầu `request(1)` còn giao diện yêu cầu `request(20)`, Publisher phải tôn trọng demand của từng Subscription ra sao?
5. Khi giao diện đóng và gọi `cancel()`, audit có cần bị hủy theo không? Vì sao?
6. Nếu audit không thể xử lý kịp tốc độ sự kiện, cần xem xét backpressure, buffer hoặc chính sách lưu bền vững nào?

**Gợi ý:** hai Subscriber có trạng thái demand và cancellation độc lập. Với nguồn cold, mỗi subscription thường có một lần thực thi riêng. Với nguồn hot multicast, cần quyết định rõ hành vi khi Subscriber chậm và Subscriber đến muộn; không giả định rằng mọi Subscriber tự động nhận lại lịch sử sự kiện.

## Kết luận

Publisher là điểm cung cấp tín hiệu và tiếp nhận đăng ký trong Reactive Streams. Khi Subscriber đăng ký, Publisher thiết lập Subscription, phát tín hiệu `onSubscribe`, rồi điều phối dữ liệu theo demand cho tới khi hoàn tất, gặp lỗi hoặc bị hủy. `Mono` và `Flux` đưa hợp đồng này vào hệ sinh thái Reactor, cho phép xây dựng nguồn cold hoặc hot và kết hợp nhiều luồng bằng toán tử. Khi hiểu Publisher, Subscription và Subscriber như ba trách nhiệm riêng, ta có thể thiết kế điểm phát dữ liệu rõ ràng, kiểm soát backpressure và dự đoán được hành vi khi có nhiều thành phần cùng đăng ký.
