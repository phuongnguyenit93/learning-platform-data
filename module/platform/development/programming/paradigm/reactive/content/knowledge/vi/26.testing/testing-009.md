# Kiểm thử nguồn nóng, đăng ký muộn và phát lại dữ liệu

## Vì sao thời điểm đăng ký là một phần của kết quả?

Với publisher cold, mỗi subscription thường khởi tạo một lần thực thi nguồn mới. Subscriber đến trước hay sau không làm thay đổi dữ liệu mà lần thực thi riêng của nó nhận được. Ngược lại, publisher hot phát tín hiệu theo một dòng sự kiện đang diễn ra; subscriber chỉ nhận những tín hiệu được phát trong khoảng thời gian nó đang tham gia, trừ khi nguồn có cơ chế lưu và phát lại lịch sử.

Sự khác biệt này rất quan trọng khi kiểm thử event bus, WebSocket, SSE, cảm biến, message stream hoặc một pipeline đã được chia sẻ giữa nhiều subscriber. Một test chỉ kiểm tra chuỗi giá trị có thể vẫn sai nếu nó không kiểm soát thời điểm subscribe, lúc nguồn bắt đầu phát và thời điểm subscriber hủy.

Trong `REACTIVE_PROGRAMMING`, `Mono` và `Flux` mô tả dữ liệu bất đồng bộ, còn Reactive Streams quy định vòng đời subscription, demand và cancellation. Khi kiểm thử nguồn nóng, cần xác nhận cả ba yếu tố: subscriber nào đang hoạt động lúc sự kiện phát ra, subscriber đến muộn có nhận lịch sử hay không và nguồn kết thúc hoặc được hủy như thế nào.

## Phân biệt nguồn cold, hot và replay

| Loại nguồn | Hành vi khi có subscriber mới | Ví dụ thường gặp |
|---|---|---|
| Cold | Mỗi subscriber khởi chạy một lần thực thi riêng và nhận chuỗi dữ liệu của lần đó | `Flux.range`, `Mono.fromCallable`, truy vấn reactive được đăng ký lại |
| Hot | Nguồn phát độc lập với subscriber; subscriber mới chỉ nhận sự kiện từ lúc tham gia | Event listener, cảm biến, luồng giá thị trường, nguồn multicast live |
| Replay | Nguồn phát sự kiện và giữ một phần hoặc toàn bộ lịch sử để subscriber đến muộn nhận lại | `Sinks.many().replay()`, `ConnectableFlux.replay()`, cache |

Cold/hot nói về quan hệ giữa việc đăng ký và quá trình phát. Replay nói về chính sách lịch sử của nguồn. Một nguồn hot có thể không replay gì, replay một số phần tử gần nhất hoặc cache toàn bộ tín hiệu. Không nên chỉ dựa vào kiểu `Flux<T>` để kết luận nguồn thuộc loại nào; cần xem cách publisher được tạo và các toán tử chia sẻ được dùng.

Ví dụ cold đơn giản:

```java
import reactor.core.publisher.Flux;

Flux<Integer> cold = Flux.range(1, 3);

cold.subscribe(value -> System.out.println("A: " + value));
cold.subscribe(value -> System.out.println("B: " + value));
```

Mỗi subscription chạy `range` riêng và nhận `1, 2, 3`. Nếu nguồn là `Mono.fromCallable`, callable cũng được gọi lại theo từng subscription. Lưu ý `Mono.just(value)` đánh giá `value` ngay khi dựng publisher; nó phát lại cùng giá trị đã được tạo, chứ không gọi lại biểu thức tạo giá trị.

Một nguồn hot có thể phát sự kiện ngay cả khi không có subscriber. Nếu nguồn không lưu lịch sử, subscriber đăng ký sau sẽ không nhận những sự kiện đã trôi qua. Đây là hành vi cần kiểm thử tường minh, nhất là khi subscriber được khởi tạo sau khi ứng dụng đã kết nối với nguồn.

## Kiểm soát thời điểm bằng TestPublisher

Reactor Test cung cấp `TestPublisher` để chủ động phát `onNext`, `onComplete` và `onError` trong test. `TestPublisher.create()` tạo publisher nóng: nó gửi tín hiệu đến subscriber đang đăng ký và không phát lại các phần tử cũ cho subscriber đến sau. `TestPublisher.createCold()` phù hợp khi cần một nguồn kiểm thử có hành vi phát lại chuỗi tín hiệu cho mỗi subscriber.

Ví dụ sau cho thấy subscriber đầu nhận sự kiện đầu tiên, còn subscriber đăng ký sau chỉ nhận sự kiện mới:

```java
import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;
import reactor.test.publisher.TestPublisher;

TestPublisher<String> source = TestPublisher.create();
Flux<String> hotEvents = source.flux();

StepVerifier.create(hotEvents)
    .then(() -> source.next("event-1"))
    .expectNext("event-1")
    .thenCancel()
    .verify();

StepVerifier.create(hotEvents)
    .then(() -> source.next("event-2"))
    .expectNext("event-2")
    .thenCancel()
    .verify();
```

Test thứ hai không nhận `event-1`, vì phần tử đó được phát trước khi subscription thứ hai được tạo. `then(...)` thực hiện thao tác phát sau khi StepVerifier đã subscribe, nhờ đó test kiểm soát được thứ tự sự kiện và đăng ký. Mỗi verifier hủy subscription của mình sau khi xác nhận sự kiện; `TestPublisher` vẫn có thể được dùng để kiểm soát lần đăng ký tiếp theo.

Không dùng `TestPublisher.createCold()` để kiểm tra hành vi mất lịch sử của nguồn hot. Nguồn cold sẽ phát lại dữ liệu cho subscriber mới và có thể khiến test che giấu lỗi timing thực tế. Chọn loại test publisher tương ứng với hợp đồng của nguồn trong production.

### Kiểm tra subscriber đến muộn khi subscriber đầu vẫn hoạt động

Trong một số tình huống, cần xác nhận hai subscriber cùng nghe một nguồn live nhưng subscriber thứ hai không nhận sự kiện đã phát trước thời điểm nó tham gia. Có thể giữ subscriber đầu hoạt động bằng một publisher kiểm thử điều khiển thủ công, hoặc dùng `Sinks.Many` để phát sự kiện sau khi từng subscription đã được thiết lập.

```java
import reactor.core.publisher.Flux;
import reactor.core.publisher.Sinks;
import reactor.test.StepVerifier;

Sinks.Many<Integer> live = Sinks.many()
    .multicast()
    .onBackpressureBuffer();

Flux<Integer> hot = live.asFlux();

StepVerifier.create(hot)
    .then(() -> live.emitNext(1, Sinks.EmitFailureHandler.FAIL_FAST))
    .expectNext(1)
    .thenCancel()
    .verify();

StepVerifier.create(hot)
    .then(() -> live.emitNext(2, Sinks.EmitFailureHandler.FAIL_FAST))
    .expectNext(2)
    .thenCancel()
    .verify();
```

Subscriber thứ hai chỉ nhận `2`. `multicast().onBackpressureBuffer()` chia sẻ các sự kiện mới cho subscriber đang tham gia; nó không giữ lịch sử đã phát để replay. Buffer trong sink phục vụ điều tiết subscriber hiện tại, không phải một kho lịch sử cho subscriber đến muộn.

Nếu muốn kiểm thử hai subscriber cùng hoạt động, có thể dùng hai verifier điều khiển bởi cùng một nguồn test trong một test fixture hoặc dùng `StepVerifier` kết hợp `PublisherProbe`/các assertion của `TestPublisher`. Điều quan trọng là phát sự kiện sau khi cả hai subscription đã được đăng ký, rồi phát một sự kiện khác sau khi subscriber thứ hai tham gia để so sánh những gì mỗi bên nhận.

Ví dụ dưới đây giữ subscriber đầu hoạt động bằng `BaseSubscriber`, sau đó đăng ký subscriber thứ hai bằng `StepVerifier`:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import org.reactivestreams.Subscription;
import reactor.core.publisher.BaseSubscriber;
import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;
import reactor.test.publisher.TestPublisher;

TestPublisher<String> source = TestPublisher.create();
Flux<String> hot = source.flux();
List<String> firstReceived = new ArrayList<>();

BaseSubscriber<String> first = new BaseSubscriber<String>() {
    @Override
    protected void hookOnSubscribe(Subscription subscription) {
        requestUnbounded();
    }

    @Override
    protected void hookOnNext(String value) {
        firstReceived.add(value);
    }
};

hot.subscribe(first);
source.next("before-second-subscriber");

StepVerifier.create(hot)
    .then(() -> source.next("after-second-subscriber"))
    .expectNext("after-second-subscriber")
    .thenCancel()
    .verify();

assertEquals(Arrays.asList(
    "before-second-subscriber",
    "after-second-subscriber"), firstReceived);
first.dispose();
```

Subscriber đầu nhận cả hai sự kiện. Subscriber thứ hai chỉ nhận sự kiện được phát sau khi nó đăng ký. Danh sách `firstReceived` chỉ được ghi bởi subscriber đầu trong test tuần tự này; nếu callback có thể chạy đồng thời, hãy dùng cấu trúc thread-safe hoặc đồng bộ hóa phù hợp.

## Kiểm tra replay có giới hạn bằng Sinks

Khi nguồn cần phát lại dữ liệu cho subscriber đến muộn, `Sinks.many().replay()` cung cấp các biến thể lưu lịch sử. `limit(n)` chỉ giữ lại tối đa `n` phần tử gần nhất; subscriber mới nhận phần lịch sử còn được giữ, sau đó tiếp tục nhận tín hiệu mới nếu nguồn còn hoạt động.

```java
import reactor.core.publisher.Flux;
import reactor.core.publisher.Sinks;
import reactor.test.StepVerifier;

Sinks.Many<Integer> replaySink = Sinks.many().replay().limit(2);
Flux<Integer> replayed = replaySink.asFlux();

StepVerifier.create(replayed)
    .then(() -> {
        replaySink.emitNext(10, Sinks.EmitFailureHandler.FAIL_FAST);
        replaySink.emitNext(20, Sinks.EmitFailureHandler.FAIL_FAST);
        replaySink.emitNext(30, Sinks.EmitFailureHandler.FAIL_FAST);
        replaySink.emitComplete(Sinks.EmitFailureHandler.FAIL_FAST);
    })
    .expectNext(10, 20, 30)
    .verifyComplete();

StepVerifier.create(replayed)
    .expectNext(20, 30)
    .verifyComplete();
```

Subscriber đầu đang hoạt động nên nhận cả ba phần tử. Sink chỉ giữ hai phần tử gần nhất trong lịch sử; subscriber thứ hai đăng ký sau khi nguồn hoàn tất nhận `20`, `30` rồi `onComplete`. Đây là cách kiểm tra chính sách replay có giới hạn và terminal signal được phát lại.

Replay không đồng nghĩa lưu trữ bền vững. Dữ liệu của sink nằm trong bộ nhớ tiến trình và mất khi ứng dụng dừng. Nếu cần phát lại message sau restart, xác nhận offset hoặc bảo đảm giao nhận, hãy dùng broker hoặc kho lưu trữ có persistence phù hợp.

## Phân biệt multicast, replay và cache

Các cơ chế chia sẻ trong Reactor có hành vi khác nhau:

| Cơ chế | Chia sẻ subscription upstream | Subscriber đến muộn | Điều cần kiểm thử |
|---|---|---|---|
| `publish().refCount(1)` / `share()` | Có trong thời gian kết nối được chia sẻ | Chỉ nhận tín hiệu từ lúc tham gia, không nhận lịch sử đã phát | Ngưỡng kết nối, subscriber rời đi và kết nối lại |
| `publish().autoConnect(n)` | Kết nối khi đủ `n` subscriber | Không replay tín hiệu trước thời điểm tham gia | Thời điểm bắt đầu nguồn và số subscriber kích hoạt |
| `publish()` + `connect()` | Kết nối do ứng dụng điều khiển | Subscriber đến sau chỉ nhận phần còn lại | Subscriber nào đã đăng ký trước `connect()` và ai dispose connection |
| `replay().limit(n)` | Chia sẻ một nguồn và lưu `n` phần tử gần nhất | Nhận lịch sử còn trong giới hạn | Giới hạn lịch sử, thứ tự replay và terminal signal |
| `cache()` | Chia sẻ và lưu tín hiệu đã phát | Có thể nhận lại giá trị, empty hoặc error đã cache | TTL, cache lỗi/empty và phạm vi dữ liệu được chia sẻ |
| `Sinks.many().multicast()` | Nhiều subscriber nhận sự kiện mới từ cùng sink | Không replay lịch sử | Hành vi khi không có subscriber, demand và overflow |

`share()` là cách viết tiện dụng cho publisher chia sẻ theo subscriber đang tham gia; nó không phải cache. Khi tất cả subscriber rời đi, kết nối upstream có thể bị hủy; một nhóm subscriber mới có thể kích hoạt lần thực thi mới. Với nguồn đã hoàn tất, hành vi khi subscribe lại còn phụ thuộc trạng thái và cách publisher được tạo; hãy viết test theo semantics cần có thay vì giả định `share()` lưu kết quả.

`autoConnect(n)` bắt đầu kết nối khi đủ số subscriber nhưng không tự ngắt nguồn chỉ vì subscriber giảm xuống dưới ngưỡng. `refCount(n)` theo dõi số subscriber và có thể hủy kết nối khi số lượng xuống dưới ngưỡng. Nếu quản lý kết nối thủ công bằng `connect()`, giữ `Disposable` trả về để có thể dừng nguồn khi ứng dụng không còn cần nó.

## Kiểm thử ConnectableFlux và thời điểm connect

`publish()` tạo `ConnectableFlux`, cho phép đăng ký subscriber trước rồi mới bắt đầu upstream bằng `connect()`. Đây là cách hữu ích khi cần bảo đảm nhiều consumer đã sẵn sàng trước khi nguồn phát:

```java
import java.time.Duration;
import java.util.concurrent.atomic.AtomicReference;
import reactor.core.Disposable;
import reactor.core.publisher.ConnectableFlux;
import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

AtomicReference<ConnectableFlux<Long>> sourceRef = new AtomicReference<>();
AtomicReference<Disposable> connectionRef = new AtomicReference<>();

StepVerifier.withVirtualTime(() -> {
        ConnectableFlux<Long> source = Flux.interval(Duration.ofSeconds(1))
            .take(3)
            .publish();
        sourceRef.set(source);
        return source;
    })
    .then(() -> connectionRef.set(sourceRef.get().connect()))
    .thenAwait(Duration.ofSeconds(3))
    .expectNext(0L, 1L, 2L)
    .verifyComplete();

connectionRef.get().dispose();
```

Ví dụ tạo `ConnectableFlux` bên trong supplier để virtual scheduler được cài trước khi `interval` được dựng. StepVerifier subscribe trước, gọi `connect()` trong `then`, rồi tiến virtual clock ba giây. `connectionRef` giữ handle để test có thể dispose sau khi hoàn tất; trong ứng dụng dài hạn, handle này phải thuộc về thành phần quản lý vòng đời nguồn. Tránh dùng `Thread.sleep`, vì test sẽ chậm và dễ chập chờn theo tải máy.

## Kiểm thử đăng ký muộn với replay và không replay

Một test hữu ích nên nêu rõ kỳ vọng của subscriber đầu và subscriber đến sau. Với nguồn không replay, subscriber thứ hai không được nhận các sự kiện cũ. Với nguồn replay có giới hạn, subscriber thứ hai phải nhận đúng phần lịch sử còn được lưu.

```java
import reactor.core.publisher.Sinks;
import reactor.test.StepVerifier;

Sinks.Many<String> live = Sinks.many().multicast().onBackpressureBuffer();
StepVerifier.create(live.asFlux())
    .then(() -> live.emitNext("A", Sinks.EmitFailureHandler.FAIL_FAST))
    .expectNext("A")
    .thenCancel()
    .verify();

Sinks.Many<String> history = Sinks.many().replay().limit(1);
StepVerifier.create(history.asFlux())
    .then(() -> {
        history.emitNext("A", Sinks.EmitFailureHandler.FAIL_FAST);
        history.emitNext("B", Sinks.EmitFailureHandler.FAIL_FAST);
    })
    .expectNext("A", "B")
    .thenCancel()
    .verify();

StepVerifier.create(history.asFlux())
    .expectNext("B")
    .thenCancel()
    .verify();
```

Hai trường hợp có hợp đồng khác nhau: `live` chỉ phát tín hiệu mới, còn `history` giữ một phần tử gần nhất. Khi test nguồn dài hạn chưa hoàn tất, dùng `thenCancel()` để kết thúc verifier và xác nhận subscriber có thể rời luồng. Nếu test cần kiểm tra nguồn hoàn tất, hãy phát `emitComplete` hoặc `emitError` rồi dùng `verifyComplete`/`expectError`.

## Kiểm tra terminal signal và cancellation

Nguồn hot có thể tiếp tục hoạt động sau khi một subscriber hủy nếu còn subscriber khác hoặc nếu nguồn có vòng đời độc lập. Vì vậy, test cần phân biệt hủy một subscription với dừng toàn bộ nguồn.

Với `Sinks.Many` multicast, có thể xác nhận một subscriber hủy mà subscriber khác vẫn nhận sự kiện mới bằng cách điều khiển hai subscription độc lập. Với `ConnectableFlux`, cần xác nhận liệu kết nối upstream còn hoạt động khi subscriber giảm xuống dưới ngưỡng `refCount`, hay vẫn chạy khi dùng `autoConnect`.

Các trường hợp nên kiểm tra:

- Subscriber đăng ký trước khi nguồn phát nhận được sự kiện tương ứng.
- Subscriber đăng ký sau một sự kiện không replay không nhận sự kiện cũ.
- Subscriber đăng ký muộn với replay nhận đúng số phần tử lịch sử được cấu hình.
- Subscriber mới sau `onComplete` hoặc `onError` nhận terminal signal và phần lịch sử đúng theo loại sink/cache.
- Một subscriber cancel không vô tình dừng nguồn đang được subscriber khác sử dụng.
- Khi không còn subscriber, nguồn được dừng hoặc tiếp tục đúng với semantics `refCount`, `autoConnect` hay kết nối thủ công.
- Nguồn phát nhanh hơn demand tuân theo chính sách buffer, drop, latest hoặc overflow đã chọn.
- Subscriber đến muộn không nhận dữ liệu của tenant/request khác nếu nguồn chia sẻ có phân vùng ngữ cảnh.

`TestPublisher` có thể xác nhận subscriber count, cancellation và request; `StepVerifier` xác nhận chuỗi tín hiệu quan sát được. Kết hợp hai công cụ giúp test không chỉ kiểm tra giá trị mà còn kiểm tra trạng thái subscription và demand.

## Kiểm thử demand và overflow của nguồn nóng

Một nguồn hot có thể phát độc lập với tốc độ downstream. Khi test, hãy kiểm tra điều gì xảy ra nếu subscriber ban đầu yêu cầu ít hoặc chưa yêu cầu dữ liệu. Với `TestPublisher`, có thể kiểm tra request được gửi đến nguồn; với `Sinks.Many`, chọn loại sink và overflow policy tương ứng.

```java
import reactor.core.publisher.Sinks;
import reactor.test.StepVerifier;

Sinks.Many<Integer> replay = Sinks.many().replay().limit(2);

StepVerifier.create(replay.asFlux(), 0)
    .then(() -> {
        replay.emitNext(1, Sinks.EmitFailureHandler.FAIL_FAST);
        replay.emitNext(2, Sinks.EmitFailureHandler.FAIL_FAST);
    })
    .thenRequest(1)
    .expectNext(1)
    .thenRequest(1)
    .expectNext(2)
    .thenCancel()
    .verify();
```

Verifier bắt đầu với demand bằng không. Sink giữ lịch sử theo giới hạn đã chọn, còn subscriber chỉ quan sát phần tử khi yêu cầu demand. Đây là test phối hợp giữa replay và backpressure; nó không có nghĩa mọi nguồn hot bên ngoài đều có thể bị dừng bằng request. Nếu nguồn gốc là push-only, cần kiểm tra buffer và overflow riêng.

Với overflow strategy, hãy tạo tình huống nguồn phát nhanh hơn subscriber rồi xác nhận chính sách. Ví dụ, với snapshot có thể chấp nhận giá trị mới nhất, test `onBackpressureLatest()` bằng cách chỉ yêu cầu một phần tử, phát nhiều giá trị, rồi yêu cầu thêm và xác nhận phần tử được giữ theo semantics mong muốn. Với audit event, test buffer hữu hạn phải xác nhận overflow phát lỗi hoặc kích hoạt handler; không chỉ kiểm tra trường hợp tải bình thường.

## Những lỗi thường gặp khi test nguồn nóng

- **Phát dữ liệu trước khi subscriber được thiết lập:** test bỏ lỡ sự kiện vì nguồn hot không replay. Đặt thao tác phát trong `then(...)` sau khi StepVerifier subscribe.
- **Dùng nguồn cold để mô phỏng event bus:** subscriber đến muộn nhận lại toàn bộ chuỗi và che giấu lỗi timing. Dùng `TestPublisher.create()` hoặc sink multicast.
- **Cho rằng `share()` lưu lịch sử:** subscriber mới chỉ nhận tín hiệu từ thời điểm tham gia; dùng replay/cache nếu cần lịch sử.
- **Nhầm buffer với replay:** buffer giữ phần tử đang chờ demand của subscriber hiện tại; replay lưu lịch sử cho subscriber đến sau.
- **Không kiểm tra terminal signal:** subscriber có thể nhận dữ liệu đúng nhưng nguồn không hoàn tất hoặc lỗi như hợp đồng yêu cầu.
- **Không kiểm tra cancellation:** listener hoặc connection upstream có thể tiếp tục chạy sau khi không còn subscriber.
- **Dùng `Thread.sleep` để tạo timing:** test phụ thuộc tốc độ máy và dễ flaky; dùng `StepVerifier.then`, `thenAwait` và virtual time.
- **Dựng publisher thời gian trước `withVirtualTime`:** scheduler ảo không kiểm soát được toán tử đã được tạo trước; tạo publisher bên trong supplier.
- **Replay không giới hạn:** test nhỏ vẫn qua nhưng production có thể giữ lịch sử lớn trong heap; xác định giới hạn hoặc TTL.
- **Bỏ qua lỗi emission của Sinks:** `tryEmitNext`/`emitNext` có thể báo thất bại khi sink đã kết thúc, không có subscriber hoặc emission không được tuần tự hóa; kiểm tra kết quả theo chính sách.

## Quy trình kiểm thử nguồn nóng và subscriber đến muộn

Trước tiên, mô tả hợp đồng nguồn: cold hay hot, có replay hay không, subscriber mới bắt đầu nhận từ thời điểm nào, nguồn kết thúc ra sao và cancellation của một subscriber có ảnh hưởng đến nguồn hoặc subscriber khác không. Chọn `TestPublisher` để điều khiển tín hiệu, `Sinks.Many` để kiểm tra hành vi sink và `ConnectableFlux` để kiểm tra thời điểm connect/refCount.

Tiếp theo, viết test với các mốc subscribe và emit rõ ràng. Xác nhận subscriber đầu, subscriber đến muộn, lịch sử replay, terminal signal, demand và cancellation. Dùng virtual time cho nguồn có timer hoặc khoảng thời gian; không dùng sleep để đồng bộ test. Với replay, đặt giới hạn lịch sử và kiểm tra cả trường hợp subscriber đến sau khi nguồn đã hoàn tất.

Cuối cùng, kiểm tra hành vi quá tải và vòng đời nguồn: buffer có đầy không, dữ liệu bị drop/latest theo đúng nghiệp vụ không, subscriber hủy có giải phóng tài nguyên không và subscriber còn lại có tiếp tục nhận sự kiện không. Kiểm thử đúng timing và chính sách replay giúp phát hiện các lỗi chỉ xuất hiện khi nhiều thành phần cùng nghe một luồng sự kiện trong môi trường thực tế.
