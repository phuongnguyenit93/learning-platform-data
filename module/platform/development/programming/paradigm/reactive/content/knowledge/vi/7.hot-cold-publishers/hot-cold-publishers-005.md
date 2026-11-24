# Kết nối thủ công, tự kết nối và đếm số bên đăng ký

Một nguồn dữ liệu lạnh thường bắt đầu công việc riêng cho mỗi Subscriber. Điều này phù hợp khi mỗi người nhận cần một lần thực thi độc lập, nhưng có thể gây lặp I/O hoặc tính toán nếu nhiều người cần cùng một luồng sự kiện. Với nguồn nóng hoặc luồng được chia sẻ, nhiều Subscriber có thể quan sát cùng một lần phát dữ liệu. Trong Project Reactor, `ConnectableFlux` cho phép tách thời điểm đăng ký khỏi thời điểm kết nối nguồn; các toán tử `autoConnect` và `refCount` giúp quyết định khi nào kết nối được mở và khi nào được đóng.

Chủ đề này thuộc chương **Nguồn nóng và lạnh** của REACTIVE_PROGRAMMING. Module học tư duy reactive qua các luồng sự kiện bất đồng bộ, hợp đồng Publisher–Subscriber và backpressure của Reactive Streams, sau đó thực hành Mono, Flux, kết hợp toán tử, scheduler, xử lý lỗi và kiểm thử pipeline trong hệ sinh thái Java. Khi chia sẻ nguồn, ta cần hiểu rõ ai kích hoạt nguồn, số Subscriber tối thiểu là bao nhiêu, và vòng đời kết nối phụ thuộc vào việc Subscriber đăng ký hoặc hủy như thế nào.

## Vì sao cần điều khiển kết nối?

Giả sử một dịch vụ đọc luồng giá thị trường từ một kết nối mạng. Ba thành phần cùng cần dữ liệu: bộ ghi lịch sử, bộ tính chỉ báo và màn hình giám sát. Nếu mỗi Subscriber tạo một subscription độc lập tới một nguồn lạnh đại diện cho kết nối mạng, ứng dụng có thể mở ba kết nối và thực hiện ba lần đọc giống nhau. Nếu mục tiêu là chia sẻ cùng một lần đọc, ta cần một Publisher có khả năng multicast.

Trong Reactor, `publish()` chuyển một `Flux` thành `ConnectableFlux<T>`. Các Subscriber có thể đăng ký trước; nguồn chỉ bắt đầu phát khi ứng dụng gọi `connect()` hoặc dùng một chính sách kết nối tự động. Điều này tạo ra hai giai đoạn:

1. **Đăng ký (subscribe):** Subscriber tham gia luồng được chia sẻ và chuẩn bị nhận tín hiệu.
2. **Kết nối (connect):** nguồn upstream được kích hoạt để bắt đầu phát dữ liệu.

```text
Subscriber A ── subscribe ──┐
                            ├── ConnectableFlux ── connect ── Source
Subscriber B ── subscribe ──┘
```

Khi nguồn bắt đầu, các Subscriber đang tham gia cùng quan sát lần phát đó. Vì đây là chia sẻ một subscription upstream, dữ liệu không được tạo lại riêng cho từng Subscriber như với nguồn lạnh chưa chia sẻ.

## Kết nối thủ công bằng `publish()` và `connect()`

`publish()` tạo một `ConnectableFlux`, nhưng chưa tự kích hoạt nguồn. Ứng dụng gọi `connect()` sau khi đã đăng ký các bên nhận cần thiết:

```java
import reactor.core.publisher.ConnectableFlux;
import reactor.core.publisher.Flux;
import reactor.core.Disposable;

ConnectableFlux<String> sharedEvents = Flux.just(
        "ORDER_CREATED",
        "PAYMENT_CONFIRMED",
        "ORDER_SHIPPED"
    )
    .publish();

sharedEvents.subscribe(event ->
    System.out.println("Audit: " + event)
);

sharedEvents.subscribe(event ->
    System.out.println("Metrics: " + event)
);

Disposable connection = sharedEvents.connect();
```

Hai Subscriber được đăng ký trước khi gọi `connect()`. Khi kết nối được mở, nguồn phát một lần và cả hai bên nhận các sự kiện tương ứng. `connect()` trả về `Disposable` đại diện cho kết nối upstream; ứng dụng có thể gọi `connection.dispose()` để ngắt kết nối trước khi nguồn tự kết thúc.

Thứ tự gọi rất quan trọng. Nếu nguồn là đồng bộ và ứng dụng gọi `connect()` trước khi đăng ký Subscriber, nguồn có thể phát và hoàn tất ngay lập tức. Các Subscriber đăng ký sau đó sẽ bỏ lỡ những phần tử đã phát:

```java
ConnectableFlux<Integer> numbers = Flux.range(1, 3).publish();

numbers.connect();                 // Nguồn đồng bộ có thể phát hết ngay tại đây
numbers.subscribe(System.out::println); // Có thể không nhận được phần tử nào
```

Với nguồn bất đồng bộ hoặc nguồn kéo dài, Subscriber đăng ký sau khi đã kết nối có thể nhận các phần tử được phát về sau, nhưng không nhận lại những phần tử đã phát trước lúc đăng ký. `ConnectableFlux` không mặc định lưu toàn bộ lịch sử để phát lại. Nếu cần Subscriber đến muộn nhận các giá trị trước đó, hãy xem xét `replay()` với giới hạn bộ nhớ hoặc thời gian phù hợp.

### Khi nào nên tự gọi `connect()`?

Kết nối thủ công hữu ích khi ứng dụng có một thời điểm khởi động rõ ràng, chẳng hạn chỉ kết nối sau khi tất cả thành phần giám sát đã sẵn sàng. Nó cũng hữu ích khi vòng đời nguồn được điều khiển bởi một thành phần quản lý cấp cao.

Điểm cần quản lý là vòng đời `Disposable` trả về từ `connect()`. Nếu không giữ tham chiếu tới nó, ứng dụng có thể mất khả năng chủ động ngắt một nguồn vô hạn. Với nguồn hữu hạn, nguồn có thể tự hoàn tất; với nguồn liên tục, cần xác định sự kiện nào sẽ đóng kết nối, ví dụ khi ứng dụng dừng hoặc không còn thành phần nào cần dữ liệu.

## Tự kết nối sau một số Subscriber bằng `autoConnect`

Nếu không muốn gọi `connect()` thủ công, có thể chuyển `ConnectableFlux` thành `Flux` tự kết nối bằng `autoConnect(n)`. Nguồn được kết nối khi có ít nhất `n` Subscriber đăng ký:

```java
import java.time.Duration;
import reactor.core.publisher.Flux;

Flux<Long> sharedTicks = Flux.interval(Duration.ofMillis(500))
    .take(6)
    .publish()
    .autoConnect(2);

sharedTicks.subscribe(tick ->
    System.out.println("Dashboard: " + tick)
);

sharedTicks.subscribe(tick ->
    System.out.println("Recorder: " + tick)
);
```

Subscriber đầu tiên đăng ký nhưng chưa đủ ngưỡng hai bên, vì vậy nguồn chưa bắt đầu. Khi Subscriber thứ hai đăng ký, Reactor tự kết nối upstream. Cả hai cùng nhận các tick phát sau thời điểm kết nối.

`autoConnect(1)` phù hợp khi muốn bắt đầu ngay khi Subscriber đầu tiên xuất hiện. Ngưỡng lớn hơn một hữu ích khi cần chờ một nhóm thành phần tham gia trước khi kích hoạt nguồn. Tuy nhiên, `autoConnect` không phải chính sách tự ngắt khi các Subscriber rời đi. Khi ngưỡng đã đạt và nguồn đã kết nối, việc tất cả Subscriber hủy đăng ký không tự động làm kết nối upstream bị dispose. Nguồn tiếp tục cho đến khi kết thúc hoặc kết nối được quản lý và ngắt bằng cách phù hợp.

Có thể truyền callback cho `autoConnect` để nhận `Disposable` của kết nối:

```java
ConnectableFlux<Long> connectable = Flux.interval(Duration.ofSeconds(1))
    .publish();

Flux<Long> automatic = connectable.autoConnect(2, connection ->
    System.out.println("Connected; handle=" + connection)
);
```

Callback này hữu ích để quan sát hoặc lưu lại handle kết nối trong một thành phần quản lý vòng đời. Không nên bỏ qua việc quản lý nguồn vô hạn chỉ vì kết nối đã được tự động tạo.

## Kết nối theo nhóm Subscriber đang hoạt động bằng `refCount`

`refCount(n)` cũng đợi ít nhất `n` Subscriber trước khi kết nối. Khác biệt quan trọng là nó theo dõi vòng đời các Subscriber: khi tất cả Subscriber hiện tại đã hủy hoặc kết thúc, kết nối upstream được ngắt. Một nhóm Subscriber mới có thể kích hoạt một kết nối mới tới nguồn:

```java
import java.time.Duration;
import reactor.core.publisher.Flux;

Flux<Long> sharedTicks = Flux.interval(Duration.ofMillis(500))
    .publish()
    .refCount(2);
```

Với `refCount(2)`, Subscriber đầu tiên chưa kích hoạt nguồn. Khi Subscriber thứ hai tham gia, nguồn được kết nối. Nếu một trong hai hủy nhưng Subscriber còn lại vẫn hoạt động, kết nối vẫn được giữ. Khi không còn Subscriber nào trong nhóm, Reactor ngắt kết nối upstream. Đây là điểm khác với `autoConnect(2)`, vốn tiếp tục giữ kết nối sau khi đã đạt ngưỡng.

`refCount` phù hợp với nguồn có thể mở lại, chẳng hạn một Publisher lạnh tạo kết nối mới khi được subscribe lại. Với nguồn bên ngoài không thể khởi động lại hoặc có side effect không lặp an toàn, cần xem xét kỹ hành vi khi nhóm Subscriber rời đi rồi đăng ký lại.

### Chờ một khoảng grace period trước khi ngắt

Một số ứng dụng có Subscriber đến và đi trong thời gian ngắn. Nếu ngắt nguồn ngay khi Subscriber cuối cùng rời đi, rồi kết nối lại ngay khi Subscriber mới xuất hiện, hệ thống có thể tạo nhiều lần kết nối mạng không cần thiết. Có thể dùng `refCount(n, gracePeriod)` để chờ một khoảng thời gian trước khi ngắt:

```java
Flux<Long> sharedTicks = Flux.interval(Duration.ofSeconds(1))
    .publish()
    .refCount(1, Duration.ofSeconds(5));
```

Với chính sách này, khi Subscriber cuối cùng rời đi, Reactor bắt đầu thời gian chờ năm giây. Nếu Subscriber mới xuất hiện trong khoảng chờ, kết nối có thể tiếp tục được duy trì; nếu không, upstream được ngắt. Grace period có thể giảm churn kết nối, nhưng cũng có nghĩa nguồn tiếp tục tiêu thụ tài nguyên trong lúc tạm thời không có người nhận.

## So sánh `connect`, `autoConnect`, `refCount` và `share`

| Cách kết nối | Thời điểm mở nguồn | Khi Subscriber rời đi | Trường hợp thường dùng |
|---|---|---|---|
| `publish()` + `connect()` | Khi ứng dụng gọi `connect()` | Ứng dụng quản lý `Disposable`; kết nối không tự đóng chỉ vì không còn Subscriber | Điều khiển thời điểm và vòng đời một cách tường minh |
| `autoConnect(n)` | Khi số Subscriber đạt ngưỡng `n` | Không tự ngắt khi tất cả Subscriber hủy; kết nối tiếp tục đến khi nguồn kết thúc hoặc được quản lý riêng | Chờ đủ thành phần rồi chạy một lần |
| `refCount(n)` | Khi số Subscriber đạt ngưỡng `n` | Ngắt upstream khi tất cả Subscriber của nhóm hiện tại rời đi | Chia sẻ trong lúc có người tiêu thụ |
| `refCount(n, gracePeriod)` | Khi số Subscriber đạt ngưỡng `n` | Chờ grace period rồi mới ngắt nếu không có Subscriber quay lại | Tránh mở/đóng nguồn liên tục khi Subscriber dao động |
| `share()` | Khi Subscriber đầu tiên đăng ký | Chia sẻ trong khi có Subscriber; ngắt khi không còn Subscriber | Cách viết gọn cho chia sẻ với ngưỡng một |

Trong cách dùng thông thường, `share()` tương đương mô hình `publish().refCount(1)`. Các phiên bản Reactor có thể bổ sung chi tiết xử lý race ở thời điểm subscribe/cancel; khi phụ thuộc vào hành vi biên, hãy kiểm tra tài liệu của phiên bản đang dùng. Dù chọn cách nào, cần nhớ rằng chia sẻ một luồng không đồng nghĩa với phát lại lịch sử cho Subscriber đến muộn.

## Đếm số Subscriber đang hoạt động

Để quan sát số bên nhận đang tham gia, có thể dùng `doOnSubscribe` để tăng bộ đếm và `doFinally` để giảm bộ đếm khi subscription kết thúc, lỗi hoặc bị hủy. Dùng `AtomicInteger` vì các callback có thể chạy trên nhiều thread:

```java
import java.util.concurrent.atomic.AtomicInteger;
import reactor.core.publisher.Flux;

AtomicInteger activeSubscribers = new AtomicInteger();

Flux<Integer> shared = Flux.range(1, 5)
    .publish()
    .refCount(2);

Flux<Integer> observed = shared
    .doOnSubscribe(subscription -> {
        int count = activeSubscribers.incrementAndGet();
        System.out.println("Active subscribers: " + count);
    })
    .doFinally(signal -> {
        int count = activeSubscribers.decrementAndGet();
        System.out.println("Active subscribers: " + count + ", signal=" + signal);
    });

observed.subscribe(value -> System.out.println("A: " + value));
observed.subscribe(value -> System.out.println("B: " + value));
```

Hai hook được đặt **sau** `publish().refCount(2)`, tại phía downstream mà mỗi Subscriber đi qua. Vì vậy mỗi lần đăng ký của A hoặc B đều làm bộ đếm tăng; khi subscription đó hoàn tất, lỗi hoặc bị hủy, `doFinally` giảm bộ đếm. Với nguồn `Flux.range` hữu hạn, hai subscription có thể hoàn tất nhanh và bộ đếm trở về không.

Vị trí đặt hook quyết định ý nghĩa của số đếm. Nếu đặt `doOnSubscribe` trước `publish()`, hook nằm ở upstream và thường chỉ quan sát subscription kết nối nguồn, không đếm từng Subscriber downstream. Muốn đo số bên nhận đang hoạt động, hãy đặt hook ở phía sau ranh giới chia sẻ.

### Đếm tổng lượt đăng ký và số đang hoạt động

Hai số liệu này trả lời hai câu hỏi khác nhau:

- **Tổng lượt đăng ký:** có bao nhiêu lần subscribe đã xảy ra trong một khoảng thời gian. Chỉ cần tăng bộ đếm trong `doOnSubscribe` và không giảm.
- **Số Subscriber đang hoạt động:** hiện có bao nhiêu subscription chưa kết thúc. Tăng trong `doOnSubscribe`, giảm trong `doFinally`.

Ví dụ dùng hai bộ đếm:

```java
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicLong;
import reactor.core.publisher.Flux;

AtomicLong totalSubscriptions = new AtomicLong();
AtomicInteger activeSubscriptions = new AtomicInteger();

Flux<Integer> shared = Flux.range(1, 5)
    .publish()
    .refCount(2);

Flux<Integer> monitored = shared
    .doOnSubscribe(s -> {
        totalSubscriptions.incrementAndGet();
        activeSubscriptions.incrementAndGet();
    })
    .doFinally(signal -> activeSubscriptions.decrementAndGet());
```

`totalSubscriptions` là số lượt đăng ký đã quan sát tại vị trí hook; `activeSubscriptions` là số subscription hiện chưa kết thúc. Nếu có retry, resubscribe hoặc subscriber đăng ký lại sau khi cancel, mỗi subscription mới sẽ được tính như một lượt mới. Vì vậy, hãy đặt tên metric phản ánh đúng phạm vi đo, chẳng hạn `downstream_active_subscriptions` thay vì gọi chung là “số kết nối”.

### Không nhầm số Subscriber với ngưỡng kết nối

Tham số `n` trong `autoConnect(n)` hoặc `refCount(n)` là ngưỡng tối thiểu để kích hoạt kết nối. Nó không phải API truy vấn số Subscriber hiện tại và không thay thế metric quan sát. Muốn hiển thị số người đang nghe, hãy đo tại ranh giới downstream như ví dụ trên hoặc dùng cơ chế instrumentation/metrics của ứng dụng.

Số subscription cũng không nhất thiết bằng số người dùng, số HTTP request hay số kết nối mạng. Một thành phần có thể tạo nhiều subscription; một subscription có thể phục vụ một phiên nghiệp vụ; và một kết nối upstream có thể được chia sẻ cho nhiều Subscriber. Cần xác định rõ đơn vị muốn đếm trước khi đặt tên metric.

## Những lưu ý về dữ liệu và vòng đời

**Subscriber đến muộn có thể bỏ lỡ dữ liệu đã phát.** `publish()` chia sẻ các tín hiệu từ lúc kết nối. Nếu cần replay một số phần tử cũ, hãy cân nhắc `replay()` và đặt giới hạn kích thước hoặc thời gian để tránh giữ lịch sử không giới hạn.

**Một Subscriber chậm có thể ảnh hưởng đến luồng chia sẻ.** `publish()` phối hợp nhu cầu của các Subscriber và có thể tạm dừng phát khi nhu cầu của nhóm không cho phép tiến lên. Điều này khác với việc mỗi Subscriber có một bản sao độc lập. Cần thiết kế buffer, prefetch và chính sách xử lý chậm theo đặc tính dữ liệu.

**`autoConnect` không tự giải phóng nguồn vô hạn.** Nếu nguồn không kết thúc, hãy lưu và quản lý handle kết nối hoặc chọn `refCount` nếu vòng đời nguồn nên gắn với nhóm Subscriber.

**`refCount` có thể khởi động lại nguồn.** Khi nhóm cũ rời đi và nhóm mới đăng ký, nguồn lạnh có thể được subscribe lại và thực thi lại side effect. Không dùng mô hình này cho thao tác không thể lặp lại nếu chưa có idempotency hoặc cơ chế quản lý tương ứng.

**Hủy một Subscriber không đồng nghĩa hủy toàn bộ luồng chia sẻ.** Với `refCount`, upstream chỉ ngắt khi không còn Subscriber trong nhóm. Với `autoConnect`, kết nối vẫn tiếp tục sau khi ngưỡng đã đạt. Hiểu đúng điều này giúp tránh dừng dữ liệu của các thành phần vẫn còn cần nguồn.

## Kiểm thử chính sách kết nối

Có thể dùng `StepVerifier` để xác nhận dữ liệu được chia sẻ và nguồn chỉ bắt đầu sau khi đủ Subscriber. Ví dụ sau kiểm tra `publish().autoConnect(2)`:

```java
import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;
import static org.junit.jupiter.api.Assertions.assertEquals;

class SharedPublisherTest {
    @Test
    void autoConnectStartsAfterSecondSubscriber() {
        Flux<Integer> shared = Flux.range(1, 3)
            .publish()
            .autoConnect(2);

        List<Integer> secondSubscriberValues = new CopyOnWriteArrayList<>();

        StepVerifier.create(shared)
            .then(() -> shared.subscribe(secondSubscriberValues::add))
            .expectNext(1, 2, 3)
            .verifyComplete();

        assertEquals(List.of(1, 2, 3), secondSubscriberValues);
    }
}
```

Với ngưỡng lớn hơn một, test cần tạo và đăng ký đủ Subscriber trước khi chờ terminal signal của từng bên. Có thể dùng hai `StepVerifier` được điều phối bằng `then(...)`, `TestPublisher` hoặc một Subscriber kiểm thử có latch. Không nên viết test chỉ đăng ký một verifier rồi đợi hoàn tất, bởi nguồn `autoConnect(2)` sẽ chưa kết nối và verifier có thể chờ mãi.

Các hành vi nên được kiểm thử riêng:

- `connect()`: nguồn không phát trước khi kết nối; các Subscriber đã đăng ký cùng nhận lần phát sau khi kết nối.
- `autoConnect(n)`: nguồn chưa chạy khi số Subscriber nhỏ hơn `n`; kết nối bắt đầu khi đủ ngưỡng và không tự ngắt chỉ vì các Subscriber hủy.
- `refCount(n)`: nguồn kết nối khi đủ ngưỡng; khi tất cả Subscriber hủy, upstream được dispose; một nhóm mới có thể tạo kết nối mới.
- Grace period: Subscriber quay lại trong khoảng chờ thì kết nối được duy trì theo chính sách; hết thời gian chờ mà không có ai quay lại thì upstream được ngắt.
- Đếm Subscriber: mỗi subscribe tăng đúng một lần và mỗi terminal/cancel giảm đúng một lần; bộ đếm không âm sau khi tất cả subscription kết thúc.

Với các test liên quan đến thời gian, ưu tiên virtual time hoặc scheduler kiểm thử để kết quả ổn định. Nếu cần xác nhận nguồn thật sự được subscribe lại, hãy gắn bộ đếm subscription vào nguồn lạnh bằng `Flux.defer` và kiểm tra số lần khởi tạo thay vì suy luận từ số dòng log.

## Tự kiểm tra

1. Vì sao `publish()` chưa làm nguồn bắt đầu phát? Vai trò của `connect()` là gì?
2. Với `autoConnect(2)`, điều gì xảy ra sau khi Subscriber đầu tiên đăng ký? Điều gì xảy ra khi Subscriber thứ hai tham gia?
3. Khi nào `refCount(2)` ngắt kết nối upstream? Nếu chỉ một trong hai Subscriber hủy thì sao?
4. Điểm khác nhau quan trọng nhất giữa `autoConnect` và `refCount` là gì khi tất cả Subscriber rời đi?
5. Vì sao hook đếm Subscriber nên được đặt sau `publish()` hoặc `refCount()`?
6. Phân biệt tổng lượt đăng ký với số Subscriber đang hoạt động. Hook nào phù hợp để cập nhật từng chỉ số?
7. Một Subscriber đăng ký sau khi nguồn nóng đã phát ba phần tử. Vì sao Subscriber đó không tự nhận lại ba phần tử cũ?

Khi điều khiển được thời điểm kết nối, ngưỡng Subscriber và vòng đời ngắt nguồn, bạn có thể chia sẻ một lần phát dữ liệu cho nhiều thành phần, tránh tạo công việc trùng lặp và đo chính xác số subscription đang hoạt động trong pipeline Reactor.
