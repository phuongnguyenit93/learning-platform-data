# Kết thúc, hủy đăng ký và giải phóng tài nguyên

## 1. Vì sao vòng đời quan trọng trong Spring Cloud Function?

Một hàm phản ứng không chỉ biến đổi dữ liệu. Nó còn sở hữu hoặc sử dụng các tài nguyên có vòng đời: kết nối HTTP, cursor đọc dữ liệu, phiên giao dịch, subscription sự kiện, bộ đếm thời gian, file và bộ nhớ đệm. Nếu không biết **khi nào một publisher kết thúc** và **ai chịu trách nhiệm dừng nó**, ứng dụng có thể bị rò rỉ tài nguyên hoặc hiểu nhầm rằng một tác vụ đã thành công.

Trong **Spring Cloud Function**, logic được đóng gói thành `Supplier`, `Function` và `Consumer`. `FunctionCatalog` hỗ trợ tra cứu và composition; adapter có thể đưa cùng một hàm ra HTTP, sự kiện qua Spring Cloud Stream hoặc môi trường serverless. Khi hàm trả `Mono<T>` hoặc `Flux<T>`, câu hỏi vòng đời trở nên quan trọng:

- Ai gọi `get()`, `apply()` hoặc `accept()`?
- Ai **subscribe** vào publisher kết quả?
- Khi nào nguồn phát `onComplete` hoặc `onError`?
- Khi client ngắt kết nối hoặc ứng dụng shutdown, ai gọi `cancel()`?
- Kết nối, phiên giao dịch và tài nguyên được mở cho **mỗi subscription** hay dùng chung toàn ứng dụng?
- Việc hủy subscription có thực sự hủy được yêu cầu mạng hoặc giao dịch đang chạy không?

Hãy xét một nguồn heartbeat:

~~~java
Supplier<Flux<Long>> heartbeats =
    () -> Flux.interval(Duration.ofSeconds(1));
~~~

Publisher này có thể phát liên tục mà **không tự `onComplete`**. Nếu adapter hoặc code ứng dụng không hủy subscription khi hết nhu cầu, luồng vẫn có thể duy trì timer và các công việc liên quan.

Ngược lại, nguồn hữu hạn:

~~~java
Supplier<Flux<String>> exportOnce =
    () -> Flux.just("ORD-101", "ORD-102");
~~~

sẽ phát hai phần tử rồi `onComplete` trong một subscription bình thường. **Hoàn tất publisher không có nghĩa ứng dụng Spring Boot tự tắt**, cũng không đảm bảo những message phát ra đã được broker xác nhận hoặc lưu bền vững.

Bài học thuộc chương **Luồng phản ứng** này tập trung vào ba kết cục khác nhau: **hoàn tất bình thường, kết thúc do lỗi và hủy đăng ký**, cùng các công cụ Reactor giúp giải phóng tài nguyên an toàn.

### Mục tiêu học tập

Sau bài, bạn có thể:

1. Phân biệt `onComplete`, `onError` và `cancel` theo hợp đồng Reactive Streams.
2. Biết khi nào dùng `doOnComplete`, `doOnError`, `doOnCancel`, `doOnTerminate` và `doFinally`.
3. Quản lý subscription thủ công bằng `Disposable` và dừng luồng dài hạn khi ứng dụng đóng.
4. Gắn vòng đời của tài nguyên với subscription bằng `Flux.using` và `Flux.usingWhen`.
5. Phân biệt **cleanup đồng bộ** với **cleanup bất đồng bộ** cần được chờ.
6. Xử lý timeout, retry, tác vụ blocking không hủy được ngay và giao dịch chưa xác nhận.
7. Hiểu ranh giới vòng đời khi kết hợp `FunctionCatalog`, HTTP, broker và serverless.
8. Viết test `StepVerifier` cho completion, error, cancellation và việc đóng tài nguyên.

## 2. Hợp đồng vòng đời của một Publisher

Reactive Streams xác định chuỗi tín hiệu cơ bản:

~~~mermaid
flowchart TD
    S["Subscriber đăng ký"] --> O["onSubscribe(Subscription)"]
    O --> N["request(n) và onNext(T)"]
    N --> Q{"Dòng xử lý tiếp tục?"}
    Q -->|Có dữ liệu| N
    Q -->|Hoàn tất bình thường| C["onComplete"]
    Q -->|Có lỗi| E["onError"]
    O -->|Không còn nhu cầu| X["cancel"]
    N -->|Downstream hủy| X
~~~

**`onComplete` và `onError` là hai tín hiệu terminal mà publisher phát cho subscriber**. Chúng loại trừ nhau trong một subscription tuân thủ hợp đồng. Sau một terminal signal, publisher không được phát thêm `onNext` xuống subscriber đó.

**`cancel()` khác hai tín hiệu trên.** Đây là thao tác subscriber gọi trên `Subscription` để thông báo không cần dữ liệu nữa. Nó không phải một `onComplete` được publisher phát và cũng không phải một `onError`. Thông thường downstream **không nhận thêm terminal callback** chỉ vì tự hủy.

| Kết cục | Bên chủ động | Subscriber nhìn thấy | Ý nghĩa |
| --- | --- | --- | --- |
| `onComplete` | Publisher | Callback hoàn tất | Nguồn kết thúc bình thường trong subscription này |
| `onError(e)` | Publisher | Callback lỗi | Nguồn kết thúc bất thường với exception |
| `cancel()` | Subscriber hoặc toán tử downstream | Không tự nhận `onComplete`/`onError` chỉ do hủy | Không còn muốn nhận tín hiệu; upstream cần ngừng công việc trong khả năng hỗ trợ |

Tất cả đều có thể dẫn đến **cleanup**, nhưng **không đồng nghĩa nghiệp vụ đã thành công**.

### 2.1. Ba phạm vi vòng đời phải tách riêng

1. **Vòng đời bean/function:** Spring quản lý bean `Supplier`, `Function`, `Consumer` và các dependency từ lúc khởi động tới lúc context đóng.
2. **Vòng đời subscription:** mỗi lần subscribe vào publisher có thể tạo một lượt xử lý riêng. Nguồn cold có thể phát lại cùng dữ liệu khi subscribe lần nữa.
3. **Vòng đời tài nguyên ngoài:** kết nối, giao dịch, file hoặc broker session có thể được tạo khi subscribe, nhưng thời điểm chúng thực sự đóng/commit phụ thuộc API sử dụng.

Một bean sống nhiều ngày không có nghĩa một subscription phải sống nhiều ngày; ngược lại, một subscription dài hạn có thể tồn tại tới lúc ứng dụng đóng. Cleanup phải gắn với **đúng phạm vi sở hữu**.

## 3. Hoàn tất bình thường với onComplete

Một `Flux` hữu hạn thường phát `onNext` một hoặc nhiều lần rồi `onComplete`:

~~~java
Flux<String> orders = Flux.just("A", "B", "C");

orders.subscribe(
    order -> System.out.println("received " + order),
    error -> System.err.println("failed: " + error),
    () -> System.out.println("completed")
);
~~~

Với nguồn đồng bộ trong ví dụ, subscriber thấy A, B, C rồi callback `completed`. Nguồn rỗng cũng kết thúc bình thường:

~~~java
Flux<String> nothingToSend = Flux.empty();
// Không onNext; có onComplete.
~~~

`Mono<Void>` thường biểu diễn **chỉ có hoàn tất hoặc lỗi, không có payload**:

~~~java
Function<Flux<OrderEvent>, Mono<Void>> persist = events ->
    events.concatMap(repository::append).then();
~~~

`repository.append` là API giả định trả `Mono<Void>`. Khi caller subscribe publisher kết quả, `then()` chỉ phát `onComplete` sau khi upstream hữu hạn và các tác vụ con hoàn tất thành công **theo hợp đồng của từng publisher con**.

Nếu upstream vô hạn, `then()` cũng có thể không hoàn tất bình thường khi stream còn hoạt động.

### 3.1. Completion không phải “đã commit thành công mọi hệ thống”

Giả sử một publisher phát `onComplete` sau khi **đưa** một công việc vào queue chứ chưa đợi database commit. Subscriber nhận completion nhưng giao dịch thực tế có thể vẫn đang chạy. Tín hiệu Reactor chỉ phản ánh hợp đồng của nguồn và các publisher đã ghép vào pipeline, không thể nâng mức đảm bảo của driver/broker bên ngoài.

Vì vậy:

- Với ghi database, kiểm tra publisher hoàn tất **sau** commit hay sau khi enqueue.
- Với broker, phân biệt publish request, broker acknowledgment và consumer acknowledgment.
- Với HTTP, phân biệt hoàn tất body/response và việc service downstream đã xử lý bền vững.
- Nếu cần exactly-once hoặc at-least-once, hãy thiết kế transaction, checkpoint và idempotency riêng.

### 3.2. Vì sao callback completion không chạy sau cancel?

~~~java
Flux<Long> source = Flux.interval(Duration.ofSeconds(1));

Disposable handle = source.subscribe(
    tick -> System.out.println(tick),
    error -> System.err.println(error),
    () -> System.out.println("completed")
);

handle.dispose();
~~~

Nếu subscription chưa phát terminal signal trước khi bị hủy, callback `completed` **không được tự gọi chỉ vì `dispose()`**. Muốn quan sát cả trường hợp hủy, dùng `doFinally` ở đúng vị trí.

## 4. Kết thúc do lỗi với onError

Một publisher có thể kết thúc bằng lỗi:

~~~java
Flux<String> failing = Flux.concat(
    Flux.just("A", "B"),
    Flux.error(new IllegalStateException("source unavailable"))
);
~~~

Một subscriber bình thường nhận A, B rồi `onError`. Không có `onComplete` sau đó.

~~~java
failing.subscribe(
    value -> System.out.println(value),
    error -> System.err.println("failed: " + error.getMessage()),
    () -> System.out.println("completed")
);
~~~

Các exception phát sinh **trong callback operator** như `map` hoặc `flatMap` cũng có thể được chuyển thành `onError` theo ngữ nghĩa của Reactor.

### 4.1. doOnError là quan sát, không phải phục hồi

~~~java
Flux<String> observed = failing
    .doOnError(error -> logger.error("Failure", error));
~~~

`doOnError` thêm một side effect quan sát lỗi rồi vẫn cho lỗi đi qua. Muốn thay thế publisher bị lỗi bằng một fallback, dùng toán tử phục hồi phù hợp:

~~~java
Flux<String> fallback = failing
    .onErrorResume(error -> Flux.just("FALLBACK"));
~~~

Với nguồn đã phát A và B, fallback có thể khiến downstream nhận A, B, FALLBACK rồi hoàn tất. **Nó không tiếp tục publisher cũ từ phần tử tiếp theo** sau lỗi; publisher cũ đã kết thúc.

### 4.2. Xử lý lỗi theo từng phần tử

Nếu muốn tiếp tục xử lý các đơn hàng khác khi một API thất bại và nghiệp vụ cho phép:

~~~java
Function<Flux<OrderEvent>, Flux<Decision>> check = orders ->
    orders.concatMap(order ->
        riskClient.check(order)
            .onErrorResume(error ->
                Mono.just(Decision.unavailable(order.orderId()))
            )
    );
~~~

`OrderEvent`, `Decision`, `riskClient` là API/DTO minh họa. `onErrorResume` nằm **bên trong** mỗi tác vụ, vì vậy lỗi của một `riskClient.check` có thể được chuyển thành một kết quả rõ ràng trước khi `concatMap` tiếp tục phần tử sau.

Dù chọn fail-fast hay phục hồi, việc đóng resource đã mở vẫn phải diễn ra; đó là lý do `using/usingWhen` cần thiết cho tài nguyên sở hữu riêng.

## 5. Hủy đăng ký: cancel không phải thành công hay thất bại

Người dùng đóng trình duyệt, request timeout, ứng dụng dừng, downstream chỉ cần vài phần tử đầu, hoặc subscriber không còn cần feed dữ liệu. Tất cả đều có thể dẫn tới cancellation.

### 5.1. Hủy trực tiếp bằng Disposable

~~~java
import reactor.core.Disposable;

Disposable subscription = Flux.interval(Duration.ofSeconds(1))
    .subscribe(
        tick -> System.out.println("tick=" + tick),
        error -> System.err.println(error)
    );

// Tại thời điểm muốn ngừng nhận:
subscription.dispose();
~~~

`subscribe(...)` của Reactor trả một `Disposable` đại diện cho khả năng dừng subscription. `dispose()` yêu cầu hủy. Trong pipeline bình thường, điều này dẫn đến yêu cầu hủy upstream và giải phóng tài nguyên **nếu các nguồn/toán tử hỗ trợ đúng**.

Không suy ra rằng:

- Một HTTP request bên ngoài chắc chắn được hủy ngay.
- Một JDBC query đang chạy sẽ dừng tức thì.
- Một giao dịch đã commit sẽ được rollback.
- Một message đã gửi tới broker sẽ bị thu hồi.
- Downstream được gọi `onComplete` chỉ vì bạn đã hủy.

### 5.2. take(n) gây cancel ở upstream, nhưng hoàn tất ở downstream

~~~java
Flux<Long> upstream = Flux.interval(Duration.ofMillis(100))
    .doFinally(signal -> System.out.println("upstream: " + signal));

Flux<Long> firstThree = upstream.take(3)
    .doFinally(signal -> System.out.println("downstream: " + signal));
~~~

Khi subscribe `firstThree` và nhận đủ ba tick:

- `take(3)` **hủy** subscription với nguồn `interval` vì không cần tick tiếp theo.
- `firstThree` phát `onComplete` tới subscriber của nó.
- Hook `doFinally` ở phía **upstream** của `take` có thể quan sát `CANCEL`.
- Hook ở phía **downstream** của `take` quan sát `ON_COMPLETE`.

Hai kết quả không mâu thuẫn: **vị trí của toán tử quyết định phạm vi vòng đời được quan sát**.

~~~mermaid
flowchart LR
    INT["Flux.interval"] --> U["doFinally: upstream"]
    U --> TAKE["take(3)"]
    TAKE --> D["doFinally: downstream"]
    D --> SUB["Subscriber"]
    TAKE -.->|"cancel upstream sau 3 tick"| U
    TAKE -->|"onComplete"| SUB
~~~

### 5.3. Timeout cũng có thể hủy upstream

~~~java
Mono<Decision> bounded = riskClient.check(order)
    .timeout(Duration.ofSeconds(2));
~~~

Nếu nguồn không cung cấp tín hiệu cần thiết trong thời hạn, `timeout` có thể hủy subscription nguồn và phát lỗi timeout xuống downstream. **Lỗi timeout ở đầu ra** và **cancellation ở đầu vào** là hai cách quan sát khác nhau của cùng một ranh giới toán tử.

Với thao tác blocking không hỗ trợ cancellation, công việc phía ngoài có thể tiếp tục chạy sau khi downstream nhận timeout. Cần cấu hình timeout **tại HTTP client/JDBC driver** và chính sách đối soát tác dụng phụ.

### 5.4. Các trường hợp hủy thường gặp

| Tình huống | Nơi phát sinh cancel | Hậu quả cần xử lý |
| --- | --- | --- |
| `take(n)`, `next()` | Toán tử downstream | Upstream không cần phát thêm |
| HTTP client disconnect | Web adapter nếu truyền được cancellation | Ngừng streaming, đóng resources theo request |
| `timeout` | Toán tử giới hạn thời gian | Upstream bị hủy; downstream có thể nhận lỗi timeout |
| App shutdown / binding stop | Adapter hoặc code quản lý lifecycle | Đóng stream dài hạn, giải phóng kết nối |
| Retry/resubscribe | Toán tử và nguồn theo chính sách phục hồi | Có thể tạo resource/subscription mới và phát lại tác dụng phụ |
| User bấm nút dừng feed | Caller giữ `Disposable` | Hủy subscription hiện tại |

Những tình huống trên còn tùy connector, phiên bản framework và nguồn dữ liệu. Cần kiểm tra tại adapter thật khi cancellation có ảnh hưởng nghiệp vụ.

## 6. Chọn đúng hook quan sát tín hiệu terminal

Reactor cung cấp nhiều hook với phạm vi khác nhau. Tên tương tự nhau nhưng không thể dùng thay thế tùy ý.

| Hook | Hoàn tất bình thường | Có lỗi | Hủy đăng ký | Mục đích |
| --- | --- | --- | --- | --- |
| `doOnComplete(Runnable)` (Flux) | Có | Không | Không | Quan sát hoàn tất thành công |
| `doOnError(Consumer)` | Không | Có | Không | Ghi log/metric lỗi |
| `doOnTerminate(Runnable)` | Có | Có | **Không** | Quan sát cả hai terminal signals |
| `doAfterTerminate(Runnable)` | Có | Có | **Không** | Side effect sau khi truyền terminal |
| `doOnCancel(Runnable)` | Không | Không | Có | Quan sát yêu cầu cancel |
| `doFinally(Consumer<SignalType>)` | Có | Có | **Có** | Dọn metric/đánh dấu kết thúc tổng quát |

`doOnComplete` chỉ áp dụng cho `Flux`; với `Mono` có thể dùng các hook tương ứng như `doOnSuccess` (lưu ý callback có thể nhận `null` khi Mono hoàn tất rỗng), `doOnError` hoặc `doFinally`. Với mục tiêu bao phủ **mọi** kết cục, `doFinally` là công cụ quan sát thuận tiện.

### 6.1. Quan sát và ghi metric bằng doFinally

~~~java
Flux<OrderEvent> observed = source
    .doOnSubscribe(subscription -> metrics.streamStarted())
    .doOnError(error -> logger.error("Stream failed", error))
    .doFinally(signal -> {
        metrics.streamStopped(signal.name());

        if (signal == reactor.core.publisher.SignalType.CANCEL) {
            metrics.streamCancelled();
        }
    });
~~~

`doFinally` nhận `SignalType` như `ON_COMPLETE`, `ON_ERROR` hoặc `CANCEL`. Hook chạy **sau khi terminal signal được chuyển tiếp xuống downstream**, nên một phép assert hoặc thao tác ghi metric thực hiện *ngay sau* `verifyComplete()` đôi khi có thể chạy trước hook `doFinally` tương ứng.

Không lấy `doFinally` làm bằng chứng một transaction đã commit bền vững. Nó là hook vòng đời publisher, thường thích hợp cho cleanup đồng bộ nhẹ và quan sát metric.

### 6.2. Đừng dùng doOnTerminate để xử lý cancel

~~~java
source
    .doOnTerminate(() -> logger.info("terminated"))
    .subscribe();
~~~

Nếu subscriber hủy mà nguồn chưa phát `onComplete` hay `onError`, `doOnTerminate` có thể không chạy. Khi tài nguyên cần được đóng cả trên cancel, dùng `using`, `usingWhen` hoặc một chủ thể sở hữu resource có cơ chế cleanup cho cả ba nhánh.

### 6.3. Vì sao thứ tự doFinally có thể gây bất ngờ?

~~~java
Flux<String> stream = Flux.just("A")
    .doFinally(a -> logger.info("first: {}", a))
    .doFinally(b -> logger.info("second: {}", b));
~~~

Với các hook `doFinally` xếp liên tiếp, chúng có thể chạy theo thứ tự **ngược chiều khai báo** khi terminal đi qua pipeline. Không đặt logic nghiệp vụ nhạy cảm với thứ tự commit vào chuỗi hook này; nên dùng resource operator hoặc transaction API thể hiện thứ tự rõ ràng.

### 6.4. doOnDiscard dành cho một tình huống khác

Khi các toán tử như `filter`, `take`, `buffer` hoặc prefetch loại bỏ những đối tượng cần cleanup, `doOnDiscard` có thể hỗ trợ giải phóng *các phần tử bị loại* ở những toán tử có hỗ trợ cơ chế discard:

~~~java
Flux<ReferenceCountedBuffer> buffers = source
    .filter(ReferenceCountedBuffer::isRelevant)
    .doOnDiscard(
        ReferenceCountedBuffer.class,
        ReferenceCountedBuffer::release
    );
~~~

Đây là ví dụ khái niệm: `ReferenceCountedBuffer` là kiểu đối tượng có phương thức `release()` và `isRelevant()`. **`doOnDiscard` không phải hook chạy cho mọi phần tử hay cho mọi operator**, cũng không thay thế việc đóng một connection/session sở hữu riêng. Cần đọc tài liệu discard-support của từng operator và tránh release hai lần.

## 7. Ghép tài nguyên đồng bộ với subscription bằng Flux.using

Khi publisher được xây dựng từ một tài nguyên như file, cursor hoặc handle, mẫu an toàn giống `try-with-resources` nhưng phù hợp lazy subscription là `Flux.using`.

### 7.1. Ví dụ tự chứa với AutoCloseable

~~~java
import java.util.List;
import java.util.concurrent.atomic.AtomicBoolean;

import reactor.core.publisher.Flux;

public class UsingExample {

    static final class OrderCursor implements AutoCloseable {
        private final AtomicBoolean closed;

        OrderCursor(AtomicBoolean closed) {
            this.closed = closed;
        }

        Flux<String> read() {
            return Flux.fromIterable(List.of("ORD-101", "ORD-102"));
        }

        @Override
        public void close() {
            closed.set(true);
        }
    }

    static Flux<String> readOrders(AtomicBoolean closed) {
        return Flux.using(
            () -> new OrderCursor(closed),
            OrderCursor::read
        );
    }
}
~~~

Một lần subscribe vào `readOrders(closed)`:

1. Gọi supplier tạo **OrderCursor mới**.
2. Lấy một publisher từ tài nguyên bằng `OrderCursor::read`.
3. Subscribe và tiêu thụ nguồn.
4. Đóng tài nguyên khi nguồn kết thúc hoặc subscription bị hủy theo hợp đồng `using`.

Không phải gọi `readOrders(...)` là resource đã được mở: với `Flux.using`, resource supplier được gọi **khi có subscription**.

### 7.2. Lỗi hoặc cancel vẫn cần close

Nếu `OrderCursor.read()` trả publisher phát `onError`, operator `using` vẫn xử lý cleanup. Nếu downstream chỉ lấy phần tử đầu rồi cancel, tài nguyên của subscription đó vẫn được giải phóng.

**Phân biệt eager và non-eager:** overload `using` có tham số `eager` điều khiển cleanup xảy ra trước hay sau khi terminal signal được chuyển xuống downstream. Lỗi trong cleanup có thể tác động đến terminal signal theo lựa chọn này. Khi cleanup exception có ý nghĩa nghiệp vụ, cần đọc chính xác hợp đồng của overload đang dùng và kiểm thử tình huống `close()` lỗi.

### 7.3. Không mở một AutoCloseable trước Flux rồi mới using

~~~java
// Đáng nghi: mở resource trước khi có subscription.
OrderCursor cursor = new OrderCursor(closed);

Flux<String> stream = Flux.using(
    () -> cursor,
    OrderCursor::read
);
~~~

Ở đây nhiều subscription **cùng dùng một instance đã bị đóng** sau lần chạy đầu, dễ gây lỗi hoặc race. Nếu resource thuộc phạm vi subscription, supplier phải **tạo/đăng ký resource đúng mỗi subscription**.

Trường hợp resource được dùng chung toàn ứng dụng, chẳng hạn HTTP connection pool, không đóng pool trong mỗi lần subscribe; để lifecycle bean/container sở hữu việc đóng pool.

### 7.4. using là cleanup đồng bộ, không tự chờ cleanup asynchronous

`AutoCloseable.close()` là phương thức đồng bộ. Nếu API trả một publisher `Mono<Void>` để đóng kết nối, đừng làm thế này:

~~~java
// Sai mục đích: closeAsync() trả Mono nhưng không có subscription.
.doFinally(signal -> connection.closeAsync());
~~~

Không có ai subscribe vào `Mono<Void>` của `closeAsync()`. Vì vậy, cleanup có thể **không chạy**. Để Reactor quản lý một bước cleanup bất đồng bộ được chờ, dùng `usingWhen`.

## 8. Cleanup bất đồng bộ bằng usingWhen

Một connection/session reactive có thể mở, đọc, commit, rollback và đóng đều bằng publisher. Reactor cung cấp `Flux.usingWhen` và `Mono.usingWhen` để đưa các thao tác đó vào một phạm vi resource.

### 8.1. API giả định của một phiên làm việc reactive

~~~java
interface ReactiveOrderSession {
    Flux<OrderEvent> readPending();

    Mono<Void> commitAndClose();
    Mono<Void> rollbackAndClose(Throwable cause);
    Mono<Void> cancelAndClose();
}

interface ReactiveSessionFactory {
    Mono<ReactiveOrderSession> open();
}
~~~

Ở đây các phương thức hoàn tất khi thao tác tương ứng đã thực hiện xong theo hợp đồng của client. Đây là các interface minh họa, không phải API dựng sẵn của Spring Cloud Function hoặc một driver cụ thể.

### 8.2. usingWhen với ba đường cleanup khác nhau

~~~java
Flux<OrderEvent> pending = Flux.usingWhen(
    sessionFactory.open(),

    // Resource dùng để tạo publisher nguồn:
    session -> session.readPending(),

    // Nguồn hoàn tất bình thường:
    session -> session.commitAndClose(),

    // Nguồn phát lỗi:
    (session, error) -> session.rollbackAndClose(error),

    // Subscriber hủy:
    session -> session.cancelAndClose()
);
~~~

Các đối số lần lượt có ý nghĩa:

1. `resourceSupplier`: publisher cấp một resource cho subscription.
2. `resourceClosure`: tạo publisher sử dụng resource.
3. `asyncComplete`: cleanup khi nguồn kết thúc bình thường.
4. `asyncError`: cleanup khi nguồn lỗi.
5. `asyncCancel`: cleanup khi bị hủy.

~~~mermaid
flowchart TD
    ACQ["Mở resource (Mono<Resource>)"] --> USE["Publisher dùng resource"]
    USE --> END{"Đã kết thúc theo cách nào?"}
    END -->|onComplete| COMMIT["asyncComplete: commit/close"]
    END -->|onError| ROLLBACK["asyncError: rollback/close"]
    END -->|cancel| CANCEL["asyncCancel: cancel/close"]
    COMMIT --> NEXT["Terminal xuống downstream"]
    ROLLBACK --> ERROR["Error xuống downstream"]
    CANCEL --> STOP["Không tự phát completion"]
~~~

**Điểm khác `doFinally`:** `usingWhen` có thể **subscribe và đợi cleanup publisher** ở các nhánh kết thúc theo ngữ nghĩa operator, thay vì chỉ chạy một callback side effect rồi bỏ publisher trả về. Trên nhánh completion/error, kết quả terminal có thể bị trì hoãn cho tới khi cleanup hoàn tất.

### 8.3. Lưu ý về dữ liệu đã phát trước cleanup

Với `Flux.usingWhen`, các `onNext` có thể đã đến downstream **trước** lúc cleanup cuối chạy. Nếu bước commit thất bại, một số item có thể đã được subscriber nhìn thấy, dù giao dịch cuối cùng không thành công.

Do đó, không dùng `Flux.usingWhen` làm bằng chứng rằng “mọi item đã phát chắc chắn được commit”. Nếu downstream cần **chỉ nhận kết quả sau khi commit**, có thể phải thiết kế một **batch hữu hạn** và chỉ phát kết quả sau khi transaction hoàn tất, hoặc dùng API giao dịch phù hợp.

### 8.4. Nếu cleanup tự thất bại thì sao?

Nếu cleanup bất đồng bộ phát lỗi, terminal quan sát được có thể bị thay bằng lỗi cleanup; một lỗi cleanup có thể che lấp hoặc gắn thông tin về lỗi ban đầu theo ngữ nghĩa Reactor của overload. Điều quan trọng là **không âm thầm nuốt lỗi cleanup**.

Với cancellation, subscriber đã không còn nhận kết quả, nên không thể mặc định lỗi cleanup sẽ được gửi lại cho subscriber đã hủy. Hãy có logging, metrics và cơ chế giám sát/reconciliation riêng.

Nếu tài nguyên chỉ cần một cách đóng chung ở mọi nhánh, overload ba tham số của `Flux.usingWhen(resourcePublisher, resourceClosure, asyncCleanup)` có thể ngắn hơn; khi cần phân biệt commit/rollback/cancel, overload năm tham số rõ ràng hơn.

### 8.5. Cần giữ mọi thao tác cần resource bên trong closure

Đừng tạo một resource bên ngoài rồi cho các toán tử dùng nó sau khi resource operator đã kết thúc:

~~~java
// Mẫu dễ sai: resource có thể đã đóng trước thao tác phụ thuộc nó.
// Flux.usingWhen(...).flatMap(event -> session.fetchMore(event))
~~~

Thay vào đó, toàn bộ pipeline cần cùng phiên phải nằm trong `resourceClosure` hoặc nằm trong transaction scope tương ứng:

~~~java
Flux<Decision> decisions = Flux.usingWhen(
    sessionFactory.open(),
    session -> session.readPending()
        .concatMap(event -> decisionService.decide(session, event)),
    ReactiveOrderSession::commitAndClose,
    (session, error) -> session.rollbackAndClose(error),
    ReactiveOrderSession::cancelAndClose
);
~~~

`decisionService.decide(session, event)` là API giả định trả `Mono<Decision>`. Nhờ đặt trong closure, resource không bị đóng chỉ vì operator đọc nguồn đã kết thúc trong khi tác vụ phía sau vẫn cần phiên.

## 9. Resource do ai sở hữu? Không phải cứ doFinally là close

Cần xác định **tài nguyên mở ở đâu, sống bao lâu và ai chịu trách nhiệm đóng**.

| Tài nguyên | Phạm vi thường gặp | Cách quản lý nên cân nhắc |
| --- | --- | --- |
| File/cursor riêng cho mỗi lượt đọc | Một subscription | `Flux.using`, `try-with-resources` trong đơn vị blocking được offload |
| Reactive connection/session riêng | Một subscription hoặc transaction | `usingWhen`/transaction API của driver |
| HTTP client và connection pool dùng chung | Cả ứng dụng | Bean/container quản lý, đóng khi shutdown |
| Timer của `Flux.interval` | Một subscription | Hủy upstream khi không còn nhu cầu; adapter quản lý handle |
| WebSocket connection riêng cho client | Một session/request | Cleanup khi client disconnect và khi lỗi |
| Subscription lâu dài do consumer tự tạo | Vòng đời bean/binding | Giữ `Disposable` và hủy khi shutdown |
| Message broker consumer | Vòng đời binder/container | Đóng binding theo framework, không tự đóng toàn broker trong mỗi message |
| Transaction/offset của broker | Một batch/message theo cấu hình | Commit/ack theo binder, không chỉ theo terminal hook |

### 9.1. “Đóng quá sớm” cũng là lỗi

Ví dụ một function dùng HTTP client chung để tra cứu dữ liệu:

~~~java
@Bean
Function<Flux<OrderEvent>, Flux<Decision>> checkOrders(
        ReactiveRiskClient client) {
    return events -> events.flatMap(client::check, 8);
}
~~~

`client` là dependency có vòng đời do Spring quản lý. Không thêm:

~~~java
// Sai nếu đây là client chia sẻ cho cả ứng dụng:
events.doFinally(signal -> client.close());
~~~

Mỗi subscription kết thúc sẽ đóng client dùng chung, làm hỏng các request khác. Hãy đóng client/pool **khi ứng dụng đóng** theo đúng hợp đồng của bean.

### 9.2. “Đóng quá muộn” cũng là lỗi

Nếu một source mở file riêng mỗi subscription nhưng chỉ có cleanup khi context đóng, hàng nghìn subscriptions đã hoàn tất có thể để lại hàng nghìn file handles chưa được giải phóng. Với resource thuộc một subscription, cleanup phải theo subscription chứ không chỉ chờ JVM shutdown.

## 10. Quản lý subscription dài hạn trong Consumer<Flux<T>>

`Consumer<Flux<T>>` là trường hợp đặc biệt của Spring Cloud Function: `accept` trả `void`, vì vậy framework không nhận được publisher kết quả để subscribe. Với reactive consumer tường minh, chính consumer thường cần subscribe input và quản lý handle của subscription.

### 10.1. Ví dụ một consumer chỉ giữ một luồng đang hoạt động

~~~java
package demo.lifecycle;

import java.util.function.Consumer;

import reactor.core.Disposable;
import reactor.core.Disposables;
import reactor.core.publisher.Flux;

public final class LiveAuditConsumer
        implements Consumer<Flux<String>>, Disposable {

    private final Disposable.Swap current = Disposables.swap();

    @Override
    public void accept(Flux<String> source) {
        Disposable next = source.subscribe(
            event -> System.out.println("audit " + event),
            error -> System.err.println("audit failed " + error),
            () -> System.out.println("audit completed")
        );

        // Chính sách: subscription mới thay thế subscription cũ.
        current.update(next);
    }

    @Override
    public void dispose() {
        current.dispose();
    }

    @Override
    public boolean isDisposed() {
        return current.isDisposed();
    }
}
~~~

Để Spring gọi cleanup khi đóng context:

~~~java
@Configuration
class AuditConsumerConfiguration {

    @Bean(destroyMethod = "dispose")
    LiveAuditConsumer liveAuditConsumer() {
        return new LiveAuditConsumer();
    }
}
~~~

`Disposable.Swap` hỗ trợ thay handle và hủy handle cũ; `dispose()` kết thúc quyền sở hữu của holder. Đây là chính sách phù hợp khi ứng dụng **chỉ muốn một subscription hoạt động cùng lúc**.

**Không dùng nguyên mẫu này khi mỗi lần `accept` phải giữ một stream độc lập.** Khi đó cần một `Disposable.Composite` hoặc cơ chế quản lý nhiều subscription với giới hạn số lượng và xóa các subscription đã kết thúc. Phải xác định ai có quyền hủy từng stream.

### 10.2. Vì sao không nên subscribe rồi bỏ handle?

~~~java
@Bean
Consumer<Flux<String>> leakingStyle() {
    return source -> source.subscribe(System.out::println);
}
~~~

Với nguồn vô hạn, đoạn này không cung cấp cách dừng rõ ràng từ chính bean và không có callback lỗi. Nếu framework gọi `accept` nhiều lần, số subscriptions có thể tăng. Không phải mọi subscription đều gây rò rỉ thực tế, nhưng thiết kế này **khó chứng minh không có rò rỉ** khi shutdown, rebalance hoặc reconnect.

Đối với phần lớn xử lý bất đồng bộ cần báo kết quả, cân nhắc `Function<Flux<T>, Mono<Void>>` thay vì `Consumer<Flux<T>>`, để caller/adapter quản lý publisher kết quả.

### 10.3. Sở hữu một handle khác với sở hữu toàn hệ thống

Dù bean tự dispose, binder có thể giữ subscription, event loop và kết nối riêng. Không tự gọi đóng toàn bộ Scheduler/broker từ consumer trừ khi bean **thực sự sở hữu** resource đó. Hệ thống cần một kế hoạch shutdown thống nhất giữa source, adapter và xử lý nghiệp vụ.

## 11. Function<Flux<T>, Mono<Void>> và trách nhiệm hoàn tất

Một reactive function trả kết quả có thể giúp caller thấy terminal signal:

~~~java
@Bean
Function<Flux<OrderEvent>, Mono<Void>> persistOrders(
        ReactiveOrderRepository repository) {

    return incoming -> incoming
        .concatMap(repository::save)
        .then();
}
~~~

`repository.save` là API giả định trả `Mono<Void>`. Khi nguồn hữu hạn hoàn tất và các tác vụ ghi đã hoàn tất theo hợp đồng publisher, kết quả `Mono<Void>` phát `onComplete`.

**Không gọi `subscribe()` ngay trong function rồi trả `Mono.empty()`:**

~~~java
// Sai hợp đồng: trả thành công trước khi thao tác ngoài hoàn tất.
Function<Flux<OrderEvent>, Mono<Void>> wrong = source -> {
    source.concatMap(repository::save).subscribe();
    return Mono.empty();
};
~~~

Đây là *fire-and-forget* không kết nối lỗi/cancellation với publisher trả về. Khi shutdown hoặc timeout, caller không có handle để đợi công việc đã tạo.

### 11.1. Luồng vô hạn không phát completion theo từng message

Nếu input là `Flux` chạy liên tục, `then()` đợi **toàn bộ** input kết thúc. Các lần lưu từng sự kiện có thể hoàn thành, nhưng `Mono<Void>` tổng thể có thể không bao giờ phát completion thành công khi luồng còn sống.

Vì vậy, terminal signal của `Function<Flux<T>, Mono<Void>>` **không thể tự dùng làm acknowledgment cho từng message** trong một event stream vô hạn. Bước này cần cơ chế per-message/batch trong adapter và repository, tùy giao thức.

### 11.2. Khi nào nên trả Flux<R> thay vì Mono<Void>?

Nếu downstream cần một kết quả cho từng sự kiện:

~~~java
@Bean
Function<Flux<OrderEvent>, Flux<Decision>> decideOrders(
        RiskClient riskClient) {

    return incoming -> incoming.flatMap(riskClient::decide, 8);
}
~~~

Output `Flux<Decision>` mang kết quả từng phần tử. Adapter có thể subscribe và gửi từng kết quả ra ngoài. Tín hiệu `onComplete` cuối luồng và việc broker xác nhận từng message vẫn là hai việc khác nhau.

## 12. Kết hợp với FunctionCatalog, composition và adapter

`FunctionCatalog` đăng ký và tra cứu các functional bean. Ví dụ một pipeline lọc dữ liệu rồi gọi service:

~~~java
@Bean
Function<Flux<OrderEvent>, Flux<OrderEvent>> validOrders() {
    return orders -> orders.filter(o -> o.amountCents() > 0);
}

@Bean
Function<Flux<OrderEvent>, Flux<Decision>> evaluate(
        RiskClient riskClient) {
    return orders -> orders.concatMap(riskClient::decide);
}
~~~

Có thể chọn composition:

~~~properties
spring.cloud.function.definition=validOrders|evaluate
~~~

Tại đây `validOrders` và `evaluate` cùng tham gia **một chuỗi publisher logic**. Khi downstream hủy, cancellation có thể lan qua các toán tử Reactor hỗ trợ tới upstream. Nhưng nếu một bước tự subscribe riêng, cầu nối trách nhiệm hủy đó có thể bị cắt.

### 12.1. HTTP adapter

Khi client ngắt request hoặc đóng một streaming response, HTTP adapter có thể hủy subscription đầu ra. Nếu resource mở cho mỗi request, cần cleanup đúng lúc. Tuy nhiên:

- Không khẳng định mọi client disconnect đều được phát hiện tức thì.
- Một yêu cầu HTTP đã gửi tới hệ thống ngoài có thể tiếp tục chạy.
- Một tác vụ đã commit không được tự rollback bởi cancellation.
- HTTP status và nội dung error response phụ thuộc adapter; không suy trực tiếp từ `SignalType`.

### 12.2. Spring Cloud Stream và binder sự kiện

Với Spring Cloud Stream, một `Function<Flux<T>, Flux<R>>` có thể được áp dụng cho **publisher dài hạn**, không phải mỗi message là một lần Java `apply`. Khi binding ngừng, binder/rebalance hoặc context đóng, adapter phải quản lý subscription và kết nối transport theo hợp đồng thực tế.

Không giả định:

- `doFinally(ON_COMPLETE)` tương đương broker ack mọi event.
- `doFinally(CANCEL)` tự rollback offset hoặc transaction.
- `Flux.usingWhen` tự làm broker commit chính xác một lần.
- Một lỗi reactive được binder xử lý giống hệt lỗi imperative theo từng message.

Cần kiểm tra tài liệu và integration test ở phiên bản Spring Cloud Stream/binder đang chạy.

### 12.3. Serverless adapter

Một invocation serverless thường có timeout và giới hạn runtime. Một `Flux` vô hạn có thể không phù hợp nếu invocation phải chờ kết quả. Khi invocation timeout, runtime có thể hủy subscription hoặc kết thúc môi trường, nhưng **không hứa cleanup Java luôn có cơ hội chạy** khi process bị kill đột ngột.

Với công việc quan trọng, thiết kế nguồn hữu hạn, checkpoint/broker bền vững và idempotency; đừng chỉ dựa vào shutdown hook trong process serverless.

### 12.4. Supplier và polling

Một `Supplier<Flux<T>>` hữu hạn có thể hoàn tất sau một batch, nhưng **không tự được gọi lại** chỉ vì đã phát `onComplete`. Với Spring Cloud Stream, `@PollableBean` có thể đánh dấu reactive supplier cần được poll lại; lịch gọi thuộc poller/adapter, không phải Spring Cloud Function Core.

Một `Supplier<Flux<T>>` phát liên tục cần được hủy khi binding dừng. Cần xác định ai tạo subscription và ai sở hữu quyền dừng, thay vì mong `Supplier.get()` tự quản lý toàn bộ vòng đời.

## 13. Timeout, retry và thực tế cancellation không đảm bảo rollback

### 13.1. Timeout của publisher và timeout của driver

~~~java
Mono<Decision> result = Mono
    .fromCallable(() -> legacyClient.check(order))
    .subscribeOn(Schedulers.boundedElastic())
    .timeout(Duration.ofSeconds(2));
~~~

Publisher trên có thể phát timeout sau hai giây và yêu cầu hủy upstream. Nhưng `legacyClient.check` là API blocking: thread nền hoặc driver **có thể tiếp tục chạy** cho tới khi lời gọi trả về. Hãy đặt timeout ngay tại client JDBC/HTTP và giải phóng kết nối theo hợp đồng driver.

`Schedulers.boundedElastic()` giúp tránh chặn event loop, **không tạo bảo đảm cancellation mạnh hơn khả năng của SDK**.

### 13.2. Retry và ranh giới resource mới

~~~java
Flux<OrderEvent> retried = Flux.usingWhen(
    sessionFactory.open(),
    ReactiveOrderSession::readPending,
    ReactiveOrderSession::commitAndClose,
    (session, error) -> session.rollbackAndClose(error),
    ReactiveOrderSession::cancelAndClose
).retry(2);
~~~

Đây là ví dụ phác thảo có thể tạo **resource/session mới trong mỗi lần subscribe lại** do retry. Nếu lần trước đã phát một số event trước lỗi, chúng có thể được phát lại. Cần idempotency và thiết kế transaction/checkpoint phù hợp.

Đừng hiểu retry là chỉ “tiếp tục từ phần tử sau khi lỗi”. Với nguồn cold, retry thường subscribe lại upstream; với nguồn hot, có thể không khôi phục dữ liệu đã mất.

### 13.3. Shutdown cưỡng bức và tác dụng phụ đã bắt đầu

Không tồn tại bảo đảm tuyệt đối rằng callback Java sẽ chạy khi process bị kill cưỡng bức, mất điện hoặc hệ thống bên ngoài đóng kết nối đột ngột. Bởi vậy, resource cleanup trong Reactor là một phần của thiết kế ổn định **khi JVM có cơ hội thực thi**, không thay thế:

- Transaction và rollback/commit của database.
- Outbox hoặc durable message queue.
- Idempotency key cho thao tác được retry.
- Lease/heartbeat và cơ chế hết hạn khi client biến mất.
- Quy trình reconciliation sau sự cố.

## 14. Dữ liệu bị loại, resource bị hủy và giới hạn của backpressure

Một dòng sự kiện có thể có phần tử bị bỏ qua do `filter`, `take`, buffer overflow, sampling hoặc cancellation. Nếu phần tử chứa resource có reference count, nó có thể cần release khi bị discard. Đó là tình huống khác với đóng connection/session đã tạo publisher.

| Vấn đề | Công cụ nên cân nhắc |
| --- | --- |
| Muốn ngừng nhận toàn bộ stream | `cancel` / `Disposable.dispose()` |
| Muốn cleanup đồng bộ cho resource theo subscription | `Flux.using` / `Mono.using` |
| Muốn cleanup bất đồng bộ, phân biệt complete/error/cancel | `Flux.usingWhen` / `Mono.usingWhen` |
| Muốn ghi metric cho mọi kết cục | `doFinally` |
| Muốn release phần tử bị discard bởi operator hỗ trợ | `doOnDiscard` |
| Muốn giới hạn nhu cầu phần tử | `request(n)` / các toán tử backpressure |
| Muốn giới hạn I/O đang chạy | `flatMap(mapper, concurrency)` / `concatMap` |
| Muốn đóng client/pool chia sẻ | Lifecycle bean/container |

Một `Flux` tuân thủ backpressure không tự đóng đúng cách một resource mà ứng dụng mở bên ngoài publisher. Tương tự, gọi `dispose()` không làm tất cả bộ đệm và object reference biến mất ngay tức thì. Cần quản lý đầy đủ cả ownership và discard semantics khi xử lý dữ liệu nhạy cảm với tài nguyên.

## 15. Kiểm thử vòng đời bằng StepVerifier

Unit test nên xác nhận **tín hiệu** và **việc cleanup**, không chỉ so sánh các giá trị `onNext`. `reactor-test` hỗ trợ `StepVerifier` để subscribe, yêu cầu hủy và xác minh lỗi/completion.

### 15.1. Test hoàn tất thành công

~~~java
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

class LifecycleTest {

    @Test
    void finiteSourceCompletes() {
        StepVerifier.create(Flux.just("A", "B"))
            .expectNext("A", "B")
            .verifyComplete();
    }
}
~~~

Test này kiểm tra `onComplete` của publisher hữu hạn; nó chưa xác minh cleanup của tài nguyên bên ngoài.

### 15.2. Test onError không trở thành onComplete

~~~java
@Test
void errorTerminatesTheSequence() {
    Flux<String> source = Flux.concat(
        Flux.just("A"),
        Flux.error(new IllegalStateException("read failed"))
    );

    StepVerifier.create(source)
        .expectNext("A")
        .expectErrorMessage("read failed")
        .verify();
}
~~~

Nội dung này là một phương thức test độc lập, có thể đặt trong class `LifecycleTest` với các import ở mục trên.

### 15.3. Test cancel kích hoạt doOnCancel

~~~java
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.concurrent.atomic.AtomicBoolean;

@Test
void cancelIsNotCompleteButNotifiesUpstream() {
    AtomicBoolean cancelled = new AtomicBoolean();

    Flux<String> source = Flux.<String>never()
        .doOnCancel(() -> cancelled.set(true));

    StepVerifier.create(source)
        .expectSubscription()
        .thenCancel()
        .verify();

    assertTrue(cancelled.get());
}
~~~

`Flux.never()` không phát phần tử cũng không terminal signal. Test chủ động cancel, nhờ vậy không treo đợi completion.

### 15.4. Test resource dùng Flux.using được đóng cả khi cancel

~~~java
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.concurrent.atomic.AtomicBoolean;

import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

@Test
void usingClosesResourceOnCancel() {
    AtomicBoolean closed = new AtomicBoolean();

    class Lease implements AutoCloseable {
        @Override
        public void close() {
            closed.set(true);
        }
    }

    Flux<String> source = Flux.using(
        Lease::new,
        lease -> Flux.concat(
            Flux.just("A"),
            Flux.<String>never()
        )
    );

    StepVerifier.create(source)
        .expectNext("A")
        .thenCancel()
        .verify();

    assertTrue(closed.get());
}
~~~

**Chú ý:** Ví dụ trên minh họa overload `Flux.using(Callable, Function)` cho resource `AutoCloseable`; resource được đóng theo semantics của operator. Đối tượng `Lease` không cần tự được trả xuống downstream.

### 15.5. Test usingWhen cleanup bất đồng bộ

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.concurrent.atomic.AtomicInteger;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

@Test
void usingWhenWaitsForAsyncCleanupBeforeCompleting() {
    AtomicInteger cleanupCount = new AtomicInteger();

    Flux<String> source = Flux.usingWhen(
        Mono.just("resource"),
        resource -> Flux.just("A", "B"),
        resource -> Mono.fromRunnable(
            cleanupCount::incrementAndGet
        )
    );

    StepVerifier.create(source)
        .expectNext("A", "B")
        .verifyComplete();

    assertEquals(1, cleanupCount.get());
}
~~~

Ở đây cleanup là `Mono.fromRunnable` được operator subscribe như một bước kết thúc bất đồng bộ hợp đồng; ví dụ tuy chạy đồng bộ trong test nhưng chứng minh nguồn cleanup **thực sự được thực thi và chờ trước completion**. Trong hệ thống thật, cleanup có thể là `connection.close()` trả publisher I/O.

### 15.6. Test hủy nguồn theo thời gian bằng virtual time

~~~java
import java.time.Duration;

import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

@Test
void takeThreeCompletesDownstream() {
    StepVerifier.withVirtualTime(
            () -> Flux.interval(Duration.ofSeconds(1)).take(3)
        )
        .thenAwait(Duration.ofSeconds(3))
        .expectNext(0L, 1L, 2L)
        .verifyComplete();
}
~~~

Publisher `take(3)` hoàn tất bình thường dù nó đã hủy `interval` ở upstream. **Virtual time chỉ điều khiển scheduler Reactor tham gia nguồn được tạo trong factory**; nó không mô phỏng tài nguyên database, socket hoặc broker ngoài đời thật.

### 15.7. Cẩn thận khi assert ngay sau doFinally

Vì `doFinally` thường chạy **sau** khi terminal signal đã được chuyển xuống downstream, viết:

~~~java
AtomicBoolean finalHookCalled = new AtomicBoolean();

Flux.just("A")
    .doFinally(signal -> finalHookCalled.set(true));
~~~

rồi khẳng định flag ngay sau một phép verify có thể phụ thuộc vào thời điểm callback. Khi test tác dụng phụ của `doFinally`, cần sử dụng cơ chế đồng bộ test thích hợp (ví dụ `CountDownLatch` với timeout hữu hạn) hoặc kiểm tra bằng công cụ quan sát có thể chờ. **Đừng xây logic giao dịch dựa trên giả định hook luôn hoàn tất trước observer của terminal signal.**

## 16. Quan sát hoạt động và phát hiện rò rỉ tài nguyên

Khi vận hành luồng dài hạn, chỉ đếm số message nhận được là chưa đủ. Cần theo dõi **subscription** và **resource**.

| Metric / tín hiệu | Câu hỏi cần trả lời |
| --- | --- |
| Số subscription đang hoạt động | Có feed nào không được hủy khi client rời đi? |
| `doFinally` phân theo `ON_COMPLETE`/`ON_ERROR`/`CANCEL` | Có quá nhiều cancellation hoặc lỗi bất thường không? |
| Số kết nối/cursor/file handles đang mở | Resource có giảm sau mỗi batch hoặc request không? |
| Thời gian cleanup | Đóng session có bị treo hoặc chậm không? |
| Số lỗi cleanup | Resource bị đóng thất bại có gây thất thoát hoặc khóa dữ liệu không? |
| HTTP connection pool active/pending | Có rò rỉ hoặc bão hòa pool không? |
| Event loop/timer/tasks đang hoạt động | Có nguồn vô hạn chạy ngoài ý muốn không? |
| Broker lag, ack, redelivery | Dữ liệu có còn chờ, lặp hoặc mất sau shutdown không? |
| Memory/heap và reference count | Dữ liệu bị discard có được release đúng không? |

Một công cụ quan sát có thể lưu:

~~~java
Flux<String> monitored = source
    .doOnSubscribe(s -> metrics.incrementActive())
    .doFinally(signal -> {
        metrics.decrementActive();
        metrics.recordTermination(signal.name());
    });
~~~

Chỉ dùng cách đếm này nếu mỗi subscription đi qua cùng hai hook đúng một lần theo thiết kế, và metric callbacks không chặn các thread nhạy cảm. `doFinally` không cung cấp “commit” nghiệp vụ; nó phục vụ quan sát vòng đời.

### 16.1. Một số dấu hiệu lỗi thường gặp

- Subscription active tăng nhưng không giảm sau khi client đóng.
- Số connection/cursor mở tăng theo mỗi request.
- Callback `onComplete` không bao giờ xuất hiện do nguồn vô hạn; shutdown cũng không có cancel.
- Nhiều task chờ trong `boundedElastic` sau timeout, vì driver blocking không hủy kịp.
- Giữ `Disposable` trong collection nhưng không xóa sau completion, làm tăng tham chiếu bộ nhớ.
- Một `usingWhen` cleanup thất bại nhưng bị log bỏ qua, khiến resource bị giữ.
- Retry hoặc resubscription đọc lại bản ghi đã ghi trước lỗi.

Cần phân biệt **số subscriber hiện tại** với **số tài nguyên mở**; một subscription có thể sử dụng nhiều tài nguyên, và một pool có thể được chia sẻ qua nhiều subscriptions.

## 17. Quy trình shutdown có kiểm soát

Khi ứng dụng cần tắt để deploy hoặc scale down, mục tiêu thường là **không nhận thêm việc mới**, xử lý/ghi nhận phần việc đang chạy, rồi đóng resource trong phạm vi cho phép.

Một quy trình tham khảo:

1. **Ngừng nhận mới:** yêu cầu adapter/binder ngừng cung cấp message mới hoặc ngừng chấp nhận request.
2. **Quyết định drain hay cancel:** với stream dài hạn, không thể chờ `onComplete` vô hạn; cần timeout cho giai đoạn chờ công việc đang chạy.
3. **Đợi công việc đã nhận** theo chính sách: transaction/ack sau khi đủ điều kiện hoàn thành, hoặc ghi trạng thái có thể replay.
4. **Hủy subscriptions còn sống** bằng cơ chế của framework hoặc handle đã giữ; cleanup phải xử lý nhánh cancel.
5. **Đóng resources chia sẻ** như HTTP client, connection pool và scheduler tùy chỉnh theo lifecycle bean.
6. **Ghi nhận phần còn dang dở** để khôi phục khi restart: offset/checkpoint, idempotency, trạng thái công việc hoặc dead-letter.

Quy trình cụ thể phụ thuộc Spring Boot, adapter HTTP, binder và nền tảng triển khai. **Không nên tự viết một shutdown hook đóng toàn bộ resource trước khi binder kịp ngừng nhận/ack**, vì có thể gây lỗi giữa chừng.

### 17.1. Shutdown mềm không thay thế khôi phục sau crash

Ngay cả với graceful shutdown, process vẫn có thể bị kill khi vượt timeout của nền tảng. Vì vậy, các event quan trọng cần một đường dữ liệu có khả năng khôi phục (broker/outbox/checkpoint) và tiêu thụ idempotent. Resource cleanup tối ưu **độ ổn định khi có thời gian đóng bình thường**, chứ không thể bảo đảm tính bền vững trong mọi sự cố.

## 18. Các nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu đúng |
| --- | --- |
| “cancel cũng là onComplete.” | Cancel là yêu cầu từ subscriber; không tự phát completion xuống downstream. |
| “doOnTerminate chạy khi hủy.” | Hook này dành cho `onComplete`/`onError`, không bao phủ cancel. |
| “doFinally chỉ dùng cho lỗi.” | Nó quan sát complete, error và cancel. |
| “doFinally bảo đảm transaction đã commit.” | Đây là hook vòng đời publisher, không phải cơ chế commit bền vững. |
| “Gọi closeAsync() trong doFinally là đủ.” | Nếu API trả `Mono` lạnh, không ai subscribe cleanup đó; cân nhắc `usingWhen`. |
| “Một resource mở ngoài publisher có thể dùng lại qua mọi subscription.” | Resource đã đóng ở lần đầu có thể không còn hợp lệ; phải xác định đúng ownership. |
| “Flux.usingWhen chỉ cần đóng trên onComplete.” | Phải xét cả lỗi và cancel, đặc biệt khi có transaction. |
| “Hủy Mono.fromCallable chắc chắn dừng JDBC.” | Driver blocking có thể tiếp tục chạy; timeout/cancellation không bảo đảm rollback. |
| “take(3) khiến upstream cũng phát onComplete.” | Downstream hoàn tất, upstream có thể nhận cancel. |
| “Một Consumer<Flux<T>> chỉ cần subscribe(), không cần giữ handle.” | Luồng dài hạn cần quản lý lỗi, lifecycle và quyền hủy. |
| “Mono<Void> hoàn tất cho mỗi event trong stream vô hạn.” | Nó hoàn tất khi toàn pipeline hữu hạn kết thúc, không tự ack mỗi message. |
| “Spring Boot đóng là mọi callback Java chắc chắn chạy.” | Process kill/crash có thể ngăn cleanup; cần phục hồi bền vững. |
| “Đóng client chung ở cuối mỗi request là tốt.” | Resource chia sẻ cần đóng theo lifecycle bean, không theo từng subscription. |
| “Unit test Reactor chứng minh binder đã ack đúng.” | Cần integration test với broker và cấu hình delivery thật. |
| “Retry không ảnh hưởng cleanup hay dữ liệu.” | Retry có thể mở resource mới, phát lại và lặp side effect. |

## 19. Checklist thiết kế nguồn có quản lý vòng đời

~~~mermaid
flowchart TD
    START["Tạo Flux/Mono cho tác vụ"] --> OWNER{"Tài nguyên thuộc phạm vi nào?"}
    OWNER -->|Mỗi subscription| PER["using / usingWhen"]
    OWNER -->|Bean dùng chung| BEAN["Container lifecycle"]
    OWNER -->|Không có resource riêng| NONE["Pipeline thông thường"]
    PER --> CLEAN{"Cleanup có bất đồng bộ?"}
    CLEAN -->|Có| WHEN["usingWhen: complete/error/cancel"]
    CLEAN -->|Không| USING["using: AutoCloseable"]
    USING --> OBS["Quan sát bằng doFinally"]
    WHEN --> OBS
    BEAN --> OBS
    NONE --> OBS
    OBS --> LONG{"Luồng có thể chạy dài hạn?"}
    LONG -->|Có| CANCEL["Quản lý Disposable, shutdown/cancel"]
    LONG -->|Không| FINITE["Xác minh onComplete/onError"]
    CANCEL --> VERIFY["Test cleanup và adapter"]
    FINITE --> VERIFY
~~~

Trước khi đưa function vào production, trả lời đầy đủ:

1. **Ai tạo resource** và lúc nào? Khi tạo bean, khi gọi `apply` hay khi subscribe?
2. **Ai sở hữu resource**? Một request, một subscription, một transaction hay cả ứng dụng?
3. **Có ba đường kết thúc** không? Hoàn tất, lỗi và cancel dẫn tới cleanup gì?
4. **Cleanup có publisher trả về** không? Nếu có, ai subscribe và chờ nó?
5. **Các tác vụ cần resource** có nằm trong closure của `usingWhen` không?
6. **Cancellation có hỗ trợ thực sự** ở HTTP/JDBC client hay chỉ dừng nhận tín hiệu?
7. **Tín hiệu completion** có nghĩa toàn batch thành công hay chỉ quá trình đã enqueue?
8. **Retry có mở lại resource và chạy lại side effect** không?
9. **Stream có thể chạy vô hạn** không, và ai giữ/hủy handle?
10. **Adapter có phản ánh lỗi/ack/transaction** như mong đợi không?
11. **Crash giữa chừng** được khôi phục ra sao nếu callback cleanup không chạy?
12. **Có test** cho complete, error, cancel, timeout, retry và shutdown không?

## 20. Câu hỏi tự đánh giá

1. `onComplete`, `onError` và `cancel()` khác nhau thế nào về hướng tín hiệu và callback?
2. Vì sao `doOnComplete` hoặc `doOnTerminate` không đủ để giải phóng tài nguyên trên đường cancel?
3. Khi `Flux.interval(...).take(3)` kết thúc, vì sao upstream có thể quan sát `CANCEL` còn downstream quan sát `ON_COMPLETE`?
4. `Disposable.dispose()` có đảm bảo một JDBC query đã dừng và rollback không?
5. Vì sao `Flux.using` phù hợp với tài nguyên `AutoCloseable` thuộc mỗi subscription?
6. Điều gì có thể xảy ra nếu tạo resource bên ngoài `Flux.using` rồi dùng lại cùng instance cho nhiều subscriptions?
7. Vì sao `doFinally(signal -> connection.closeAsync())` có thể không thực sự đóng connection?
8. `Flux.usingWhen` có những callback cleanup nào cho complete, error và cancel?
9. Nếu bước commit của `Flux.usingWhen` lỗi, các item đã được phát trước đó có chắc chắn chưa đến downstream không?
10. Vì sao không nên đóng HTTP connection pool dùng chung ở cuối từng subscription?
11. Với `Consumer<Flux<T>>` tự subscribe, tại sao phải quản lý `Disposable` hoặc holder của các subscriptions?
12. `Function<Flux<T>, Mono<Void>>` có tự xác nhận từng message trên một nguồn vô hạn không?
13. `retry(2)` có thể tạo lại tài nguyên và phát trùng dữ liệu ra sao?
14. Vì sao quy trình shutdown mềm không thay thế idempotency và cơ chế khôi phục sau crash?
15. Viết `StepVerifier` như thế nào để kiểm tra resource được đóng trên đường cancel?
16. Những metric nào giúp phân biệt rò rỉ subscription với rò rỉ connection pool?

## 21. Tài liệu tham khảo

- [Project Reactor — Reference Guide](https://projectreactor.io/docs/core/release/reference/) — vòng đời subscription, cancellation, `doFinally` và `using`.
- [Project Reactor — Flux API](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Flux.html) — mô tả chính xác `using`, `usingWhen`, `doOnCancel`, `doOnTerminate`, `doFinally`.
- [Project Reactor — Mono API](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Mono.html) — `Mono.usingWhen`, terminal hooks và cleanup.
- [Project Reactor — Testing](https://projectreactor.io/docs/test/release/reference/) — `StepVerifier`, cancellation và thời gian ảo.
- [Spring Cloud Function — Programming Model](https://docs.spring.io/spring-cloud-function/reference/spring-cloud-function/programming-model.html) — `Supplier`, `Function`, `Consumer` và chữ ký reactive.
- [Spring Cloud Stream — Producing and Consuming Messages](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/producing-and-consuming-messages.html) — reactive Consumer, subscription và ranh giới binder.

Ngữ nghĩa cụ thể của cleanup, phiên giao dịch, cancel và ack còn phụ thuộc Reactor, Spring Cloud Function/Stream và driver/binder ở phiên bản được dùng. Cần đối chiếu dependency/BOM của dự án và kiểm thử với adapter thật.

**Ghi nhớ:** `onComplete` báo publisher kết thúc bình thường; `onError` báo kết thúc do lỗi; `cancel` là yêu cầu từ subscriber để ngừng nhận, **không tự là một terminal signal xuống downstream**. `doFinally` giúp quan sát cả ba đường, còn `Flux.using` và `Flux.usingWhen` gắn việc giải phóng tài nguyên với vòng đời subscription. Hãy xác định rõ resource thuộc mỗi subscription hay cả ứng dụng, quản lý `Disposable` cho các stream dài hạn và coi cancellation như một yêu cầu ngừng công việc — **không phải bảo đảm rollback hoặc giao hàng đúng một lần**. Khi triển khai Spring Cloud Function qua HTTP, broker hoặc serverless, phải kiểm chứng thêm lifecycle, timeout, acknowledgment, retry và khôi phục sau sự cố của adapter.
