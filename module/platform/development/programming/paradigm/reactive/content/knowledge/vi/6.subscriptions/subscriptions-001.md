# Đăng ký nhận dữ liệu và quyền sở hữu vòng đời subscription

Trong Reactive Streams, Publisher mô tả nguồn dữ liệu và Subscriber là bên muốn nhận dữ liệu. Việc gọi `subscribe` tạo ra một lần đăng ký riêng, được đại diện bởi `Subscription`. Từ thời điểm đó, hai phía phối hợp việc phát dữ liệu, điều tiết nhu cầu và kết thúc việc nhận.

Hiểu ai sở hữu vòng đời subscription rất quan trọng khi xây dựng ứng dụng Java. Thành phần khởi tạo đăng ký thường là nơi quyết định khi nào bắt đầu nhận dữ liệu, yêu cầu bao nhiêu phần tử và khi nào không còn cần dữ liệu nữa. Nếu bỏ qua quyền sở hữu này, ứng dụng có thể tạo đăng ký trùng, tiếp tục xử lý sau khi người dùng rời màn hình hoặc giữ tài nguyên lâu hơn cần thiết.

## 1. subscribe bắt đầu một lần đăng ký

Một Publisher có thể được tạo trước khi có dữ liệu được tiêu thụ. Khi một Subscriber gọi `subscribe`, Publisher thiết lập quan hệ đăng ký và gửi Subscription qua callback `onSubscribe`.

Vòng đời cơ bản:

~~~mermaid
sequenceDiagram
    participant C as Thành phần tiêu thụ
    participant P as Publisher
    participant S as Subscription
    participant R as Subscriber

    C->>P: subscribe(subscriber)
    P->>R: onSubscribe(subscription)
    R->>S: request(n)
    P-->>R: onNext(value)
    R->>S: request(n tiếp theo)
    P-->>R: onComplete() hoặc onError(error)
~~~

Các bước chính:

1. Thành phần tiêu thụ gọi `subscribe` để đăng ký Subscriber với Publisher.
2. Publisher gọi `onSubscribe(subscription)` để trao Subscription cho Subscriber.
3. Subscriber quyết định lượng dữ liệu muốn nhận bằng `request(n)`.
4. Publisher phát các phần tử qua `onNext(value)` theo demand đã nhận.
5. Luồng kết thúc bằng `onComplete()` hoặc `onError(error)`, hoặc Subscriber có thể hủy bằng `cancel()`.

Không có Subscriber thì một Publisher lạnh (cold Publisher) thường chưa thực hiện công việc phát dữ liệu. Việc tạo pipeline và việc đăng ký là hai thời điểm khác nhau:

~~~java
import reactor.core.publisher.Flux;

Flux<String> names = repository.findAllNames()
    .filter(name -> !name.isBlank());

// Pipeline đã được mô tả, nhưng chưa có Subscriber đăng ký.
names.subscribe(name -> log.info("Tên: {}", name));
~~~

Dòng `subscribe` cuối cùng bắt đầu tiêu thụ. Với nguồn lạnh, mỗi lần đăng ký có thể kích hoạt một lần thực thi riêng.

## 2. Ai sở hữu Subscription?

Subscription đại diện cho một lần đăng ký cụ thể giữa một Publisher và một Subscriber. Mỗi lần gọi `subscribe` tạo một quan hệ đăng ký độc lập; Subscriber nhận Subscription tương ứng trong `onSubscribe`.

Thành phần khởi tạo đăng ký thường chịu trách nhiệm quản lý vòng đời của nó:

- **Bắt đầu:** gọi `subscribe` khi thật sự cần nhận dữ liệu.
- **Điều tiết:** quyết định lượng demand phù hợp với khả năng xử lý.
- **Hủy:** gọi `cancel` khi kết quả không còn cần thiết, chẳng hạn người dùng đóng màn hình hoặc một tác vụ mới thay thế tác vụ cũ.
- **Giải phóng:** bảo đảm tài nguyên gắn với luồng được thu hồi khi hoàn tất, lỗi hoặc hủy.

Publisher chịu trách nhiệm tuân thủ giao thức và phối hợp với nguồn dữ liệu. Subscriber chịu trách nhiệm xử lý phần tử và báo nhu cầu. Subscription là đối tượng nối hai trách nhiệm này.

Một Publisher có thể có nhiều Subscriber. Mỗi Subscriber có Subscription riêng, demand riêng và có thể hủy độc lập. Hủy một subscription không mặc nhiên hủy các subscription khác đang tiêu thụ cùng Publisher.

## 3. Các cách subscribe trong Project Reactor

Project Reactor cung cấp một số overload `subscribe` để phù hợp với nhu cầu tiêu thụ khác nhau.

| Cách đăng ký | Khi nào dùng | Giá trị trả về |
|---|---|---|
| `subscribe()` | Bắt đầu tiêu thụ khi không cần xử lý từng phần tử trong đoạn mã gọi. | `Disposable` |
| `subscribe(value -> ...)` | Xử lý từng phần tử bằng một callback. | `Disposable` |
| `subscribe(value -> ..., error -> ...)` | Xử lý dữ liệu và lỗi bằng callback riêng. | `Disposable` |
| `subscribe(value -> ..., error -> ..., complete -> ...)` | Cần xử lý dữ liệu, lỗi và hoàn tất. | `Disposable` |
| `subscribe(Subscriber)` | Cần triển khai trực tiếp các callback của Reactive Streams. | Phương thức đăng ký không trả về `Disposable` |

Ví dụ dùng callback:

~~~java
import reactor.core.Disposable;
import reactor.core.publisher.Flux;

Disposable handle = Flux.range(1, 5)
    .subscribe(
        value -> log.info("Nhận {}", value),
        error -> log.error("Luồng lỗi", error),
        () -> log.info("Luồng hoàn tất")
    );
~~~

Các overload tiện lợi của Reactor yêu cầu demand không giới hạn thực tế (`Long.MAX_VALUE`). Điều này thuận tiện cho những luồng nhỏ hoặc khi bên tiêu thụ có thể xử lý mọi phần tử được phát. Với nguồn lớn hoặc không giới hạn, cần cân nhắc khả năng tiêu thụ và chính sách backpressure thay vì mặc định nhận toàn bộ dữ liệu.

Khi cần kiểm soát demand, có thể dùng `BaseSubscriber`:

~~~java
import org.reactivestreams.Subscription;
import reactor.core.publisher.BaseSubscriber;
import reactor.core.publisher.Flux;

Flux<Integer> numbers = Flux.range(1, 100);

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

Subscriber này yêu cầu một phần tử ban đầu và yêu cầu phần tử kế tiếp sau khi xử lý xong giá trị hiện tại. Trong ứng dụng thực tế, `process` cần hoàn tất thao tác tiêu thụ trước khi gọi `request(1)` tiếp theo nếu mục tiêu là giữ tối đa một phần tử đang được xử lý.

## 4. Phân biệt Subscription và Disposable

Trong Reactive Streams, `Subscription` là giao diện giao thức được Publisher chuyển cho Subscriber. Nó có hai thao tác chính:

- `request(n)`: báo nhu cầu nhận thêm phần tử.
- `cancel()`: yêu cầu ngừng nhận dữ liệu.

Project Reactor cung cấp `Disposable` như một abstraction để quản lý và hủy các hoạt động đã đăng ký. Các overload `subscribe` tiện lợi trả về `Disposable` để bên gọi có thể chủ động hủy:

~~~java
import reactor.core.Disposable;

Disposable subscriptionHandle = eventStream.subscribe(this::handleEvent);

// Khi thành phần không còn cần nhận sự kiện:
subscriptionHandle.dispose();
~~~

`Disposable` không phải là `Subscription` của Reactive Streams. Nó là handle của Reactor; khi dispose, Reactor hủy việc tiêu thụ tương ứng. Với `BaseSubscriber`, có thể gọi `dispose()` để hủy subscription mà subscriber đang quản lý.

Một số điểm cần nhớ:

- `Subscription` là giao diện giao thức, có cả demand và cancellation.
- `Disposable` là handle quản lý vòng đời trong Reactor, tập trung vào khả năng hủy.
- `dispose()` tương ứng với ý định hủy việc tiêu thụ; nó không gửi một tín hiệu `onComplete()` để xác nhận.
- Không nên ép kiểu `Disposable` thành `Subscription`; hai abstraction có mục đích và hợp đồng khác nhau.

Ví dụ dùng `Disposable` phù hợp khi một thành phần giao diện tự đăng ký một luồng sự kiện và cần hủy đăng ký khi thành phần bị đóng:

~~~java
import reactor.core.Disposable;

final class DashboardController {
    private Disposable eventSubscription;

    void open() {
        eventSubscription = eventStream.subscribe(this::render);
    }

    void close() {
        if (eventSubscription != null) {
            eventSubscription.dispose();
        }
    }

    private void render(DashboardEvent event) {
        // Cập nhật trạng thái hiển thị.
    }
}
~~~

Trong ứng dụng thực tế, cần bảo đảm `close()` được gọi đúng lúc trong vòng đời giao diện. Nếu đăng ký mới mỗi lần `open()` mà không dispose đăng ký trước, cùng một sự kiện có thể được xử lý nhiều lần.

## 5. Hủy đăng ký khi không còn cần dữ liệu

Cancellation là một phần bình thường của vòng đời subscription. Nó hữu ích khi:

- Người dùng đóng màn hình hoặc rời trang.
- Một yêu cầu mới thay thế yêu cầu cũ.
- Một luồng chỉ cần một số phần tử giới hạn.
- Ứng dụng dừng một tác vụ nền.
- Một nguồn dữ liệu không còn được tiêu thụ.

Ví dụ, `take(3)` chỉ cho downstream nhận ba phần tử. Khi đã đủ, toán tử hủy subscription upstream và hoàn tất luồng downstream:

~~~java
import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

Flux<Integer> firstThree = Flux.range(1, 100)
    .doOnCancel(() -> log.info("Nguồn nhận yêu cầu hủy"))
    .take(3);

StepVerifier.create(firstThree)
    .expectNext(1, 2, 3)
    .verifyComplete();
~~~

Ở đây, downstream nhận ba phần tử rồi `onComplete()`. Upstream nhận cancellation vì không cần phát thêm dữ liệu. Đây là hai sự kiện ở hai phía của toán tử.

Hủy subscription có tính hợp tác. Nó yêu cầu nguồn ngừng phát và giải phóng tài nguyên, nhưng một tác vụ I/O đã gửi xuống driver có thể không dừng vật lý ngay tức thì. Khả năng dừng thực tế phụ thuộc vào việc nguồn và driver có hỗ trợ cancellation hay không.

Không nên chờ `onComplete()` sau khi gọi `cancel()`. Cancellation không phải terminal signal gửi đến Subscriber và không có callback xác nhận hủy riêng trong giao diện Reactive Streams.

## 6. Nhiều Subscriber và vòng đời độc lập

Một Publisher có thể được đăng ký nhiều lần. Với nguồn lạnh, mỗi subscription thường tạo một lần thực thi riêng:

~~~java
import reactor.core.publisher.Mono;

Mono<String> greeting = Mono.fromSupplier(() -> {
    log.info("Tạo lời chào");
    return "Xin chào";
});

greeting.subscribe(value -> log.info("Subscriber A: {}", value));
greeting.subscribe(value -> log.info("Subscriber B: {}", value));
~~~

Supplier có thể được gọi một lần cho mỗi subscription. Hai Subscriber nhận kết quả từ hai lần thực thi độc lập.

Nguồn nóng (hot Publisher) có thể phát sự kiện độc lập với thời điểm Subscriber đăng ký. Một Subscriber đăng ký muộn có thể không nhận được các sự kiện đã phát trước đó. Ví dụ, một kênh sự kiện dùng chung có thể tiếp tục phát trong khi nhiều thành phần đăng ký và hủy ở những thời điểm khác nhau.

Các toán tử chia sẻ như `share()` hoặc `publish().refCount()` thay đổi cách nhiều Subscriber dùng chung một nguồn. Khi dùng chia sẻ, cần hiểu chính sách kết nối và hủy kết nối của toán tử. Việc một Subscriber hủy không nhất thiết làm nguồn chung dừng nếu vẫn còn Subscriber khác; nguồn có thể tiếp tục khi còn người tiêu thụ.

Vì vậy, hãy phân biệt:

- Vòng đời của Publisher: nguồn hoặc pipeline có thể được tái sử dụng.
- Vòng đời của từng Subscription: mỗi lần đăng ký có demand và cancellation riêng.
- Vòng đời của nguồn chia sẻ: có thể phụ thuộc vào số Subscriber đang kết nối và chính sách của toán tử chia sẻ.

## 7. Giải phóng tài nguyên khi luồng kết thúc

Một subscription có thể giữ kết nối, cursor, file handle hoặc tài nguyên khác. Tài nguyên phải được giải phóng khi nguồn hoàn tất, lỗi hoặc bị hủy.

Với tài nguyên đồng bộ, Reactor cung cấp `using`:

~~~java
import reactor.core.publisher.Flux;

Flux<String> lines = Flux.using(
    () -> openBufferedReader(path),
    reader -> readLines(reader),
    reader -> closeQuietly(reader)
);
~~~

Hàm tạo tài nguyên chỉ chạy khi có subscription. Reactor gọi hàm dọn dẹp khi luồng kết thúc hoặc bị hủy. Cách này phù hợp với tài nguyên có thao tác giải phóng đồng bộ.

Nếu thao tác dọn dẹp cũng bất đồng bộ, có thể dùng `usingWhen` để mô tả Publisher tạo tài nguyên, Publisher sử dụng tài nguyên và các Publisher dọn dẹp tương ứng:

~~~java
import reactor.core.publisher.Mono;

Mono<Result> result = Mono.usingWhen(
    connectionFactory.create(),
    connection -> query(connection),
    connection -> connection.close(),
    (connection, error) -> connection.rollback().then(connection.close()),
    connection -> connection.close()
);
~~~

Ví dụ minh họa ba đường dọn dẹp: hoàn tất, lỗi và cancellation. Cần điều chỉnh theo API kết nối thực tế; trong trường hợp lỗi, có thể rollback trước khi đóng kết nối. `usingWhen` giúp gắn việc dọn dẹp bất đồng bộ với vòng đời Publisher thay vì phải tự quản lý ở nhiều callback rời rạc.

Các hook `doFinally`, `doOnCancel`, `doOnComplete` và `doOnError` hữu ích để quan sát vòng đời. Tuy nhiên, nếu cần bảo đảm đóng tài nguyên, nên dùng cơ chế quản lý tài nguyên như `using` hoặc `usingWhen` phù hợp với loại tài nguyên.

## 8. Tránh đăng ký lồng nhau trong tầng nghiệp vụ

Một lỗi thiết kế thường gặp là gọi `subscribe()` bên trong một phương thức nghiệp vụ rồi trả về `void` hoặc một giá trị không phản ánh kết quả bất đồng bộ:

~~~java
void sendWelcomeEmail(User user) {
    emailClient.send(user.email())
        .subscribe();
}
~~~

Cách này tạo một subscription mà caller không quản lý được kết quả, lỗi hoặc vòng đời. Nếu caller cần biết khi nào gửi xong, cần kết hợp Publisher và trả nó về cho caller:

~~~java
Mono<Void> sendWelcomeEmail(User user) {
    return emailClient.send(user.email());
}
~~~

Caller quyết định thời điểm subscribe và có thể kết hợp thao tác này với các bước khác:

~~~java
Mono<Void> register(User user) {
    return userRepository.save(user)
        .flatMap(saved -> sendWelcomeEmail(saved));
}
~~~

Trong ứng dụng Spring WebFlux, controller thường trả `Mono` hoặc `Flux` để framework đăng ký và quản lý việc tiêu thụ ở ranh giới HTTP. Trong ứng dụng desktop hoặc thành phần giao diện, một controller có thể tự subscribe, nhưng cần giữ `Disposable` và dispose khi thành phần kết thúc.

Nguyên tắc thực hành là để thành phần sở hữu vòng đời quyết định thời điểm bắt đầu và kết thúc subscription. Các tầng nghiệp vụ nên trả Publisher để caller có thể kết hợp pipeline, xử lý lỗi và quản lý cancellation ở đúng ranh giới.

## 9. Kiểm thử vòng đời đăng ký

`StepVerifier` có thể kiểm tra dữ liệu, tín hiệu kết thúc và cancellation. Ví dụ kiểm tra một luồng hoàn tất bình thường:

~~~java
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

@Test
void subscriptionNhanDuLieuVaHoanTat() {
    StepVerifier.create(Flux.just("A", "B"))
        .expectNext("A", "B")
        .verifyComplete();
}
~~~

Kiểm tra nguồn nhận cancellation khi downstream chỉ lấy hai phần tử:

~~~java
import java.util.concurrent.atomic.AtomicBoolean;
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;
import static org.junit.jupiter.api.Assertions.assertTrue;

@Test
void takeHuyNguonSauHaiPhanTu() {
    AtomicBoolean cancelled = new AtomicBoolean();

    Flux<Integer> source = Flux.range(1, 10)
        .doOnCancel(() -> cancelled.set(true));

    StepVerifier.create(source.take(2))
        .expectNext(1, 2)
        .verifyComplete();

    assertTrue(cancelled.get());
}
~~~

Kiểm tra một `Disposable` có thể hủy luồng không giới hạn:

~~~java
import org.junit.jupiter.api.Test;
import java.util.concurrent.atomic.AtomicBoolean;
import reactor.core.Disposable;
import reactor.core.publisher.Flux;
import static org.junit.jupiter.api.Assertions.assertTrue;

@Test
void disposeHuyDangKy() {
    AtomicBoolean cancelled = new AtomicBoolean();

    Disposable handle = Flux.<Long>never()
        .doOnCancel(() -> cancelled.set(true))
        .subscribe();

    handle.dispose();

    assertTrue(cancelled.get());
}
~~~

Các bài kiểm thử này xác nhận ba khía cạnh khác nhau: Subscriber nhận đúng dữ liệu, toán tử giới hạn hủy upstream đúng lúc và handle do `subscribe` trả về có thể kết thúc việc tiêu thụ.

Khi kiểm thử bất đồng bộ hoặc có scheduler, có thể dùng virtual time để tránh chờ thời gian thực. Với tài nguyên, nên bổ sung kiểm thử xác nhận cleanup chạy trên cả ba đường: hoàn tất, lỗi và cancellation.

Quyền sở hữu vòng đời subscription là một phần của thiết kế ứng dụng reactive. Khi biết thành phần nào bắt đầu đăng ký, thành phần nào điều khiển demand và thành phần nào chịu trách nhiệm hủy, ta có thể tránh đăng ký trùng, giới hạn công việc không còn cần thiết và giải phóng tài nguyên đúng lúc. Đây là nền tảng để kết hợp Mono, Flux và các toán tử Reactor thành những pipeline có vòng đời rõ ràng trong Java.

