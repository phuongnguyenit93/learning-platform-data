# Tính trì hoãn, đăng ký thực thi và vòng đời một chuỗi reactive trong Spring WebFlux

## 1. Bài toán: khai báo một pipeline có phải là chạy nó?

Trong lập trình mệnh lệnh, lời gọi `service.findById(id)` thường thực thi ngay lúc chương trình đi qua dòng lệnh. Trong Project Reactor, một biểu thức như `Mono.defer(() -> service.findReactive(id))` thường chỉ **mô tả cách tạo nguồn dữ liệu khi có subscription**. Dựng một pipeline, đăng ký một subscriber, yêu cầu phần tử, phát các tín hiệu và dọn tài nguyên là các pha khác nhau.

Đây là kiến thức nền tảng của **Spring WebFlux**, nơi controller thường trả `Mono<T>` hoặc `Flux<T>` để HTTP infrastructure đăng ký và xử lý response. Không phân biệt các pha sẽ dẫn đến lỗi: gọi API quá sớm, gửi email/thanh toán hai lần khi có retry, tưởng source đã được thực thi dù không ai subscribe, tự `subscribe()` rồi mất quản lý lỗi và cancellation, hoặc quên đóng tài nguyên khi client ngắt kết nối.

Mục tiêu:

- Phân biệt **assembly time** (dựng chuỗi), **subscription time** (đăng ký), **request/demand**, **signal processing**, **termination/cancellation** và **resource cleanup**.
- Biết `Mono.just(...)` khác `Mono.defer(...)`, `Mono.fromSupplier(...)` và `Mono.fromCallable(...)` ở đâu; không nói “mọi thứ trong Mono đều lazy”.
- Hiểu đường truyền `subscribe` từ downstream lên upstream, còn `onNext/onError/onComplete` truyền từ upstream xuống downstream.
- Giải thích vì sao một chuỗi cold được subscribe hai lần có thể kích hoạt hai lần truy vấn/side effects; so sánh với hot/shared/cached publisher.
- Quan sát `doFirst`, `doOnSubscribe`, `doOnRequest`, `doOnNext`, `doOnError`, `doOnComplete`, `doFinally`.
- Quản lý `Disposable`, `cancel()`, timeout, retry, resource acquisition/release và client disconnect.
- Tích hợp đúng với WebFlux annotated controller, WebClient và Reactive Repository; không tự đăng ký trong controller.
- Thực hành **Java 17+, Spring Framework 6.x, Spring Boot 3.x, Reactor Core** bằng mã runnable và kiểm thử `StepVerifier`/`WebTestClient`.

**Phạm vi:** Spring WebFlux/Reactor, không phải chỉ Spring MVC `Callable`/Servlet async. Reactor xây trên Reactive Streams; một nguồn có thể phát **đồng bộ ngay trong `subscribe`/`request`**, nên reactive không đồng nghĩa tự tạo thread mới. Ví dụ không đòi framework chạy trên một phiên bản Reactor cụ thể hơn bản Spring Boot 3.x quản lý tương thích.

## 2. Sơ đồ vòng đời một chuỗi

```text
T0: ASSEMBLY — tạo Flux/Mono, nối operators
    Flux.range(1, 3).map(...).filter(...)
             |
             | (chưa có terminal consumer)
             v
T1: SUBSCRIBE — downstream Subscriber đăng ký
    subscriber -> filter -> map -> source
             |
             v
T2: onSubscribe(Subscription), demand request(n)
    downstream -------------> upstream
             |
             v
T3: SIGNALS
    upstream -> onNext(value)* -> downstream
    upstream -> onComplete()/onError() -> downstream
             |
             v
T4: FINALLY/CLEANUP
    complete | error | cancel
    release file/connection/registration
```

Các mốc không nhất thiết cách nhau theo thời gian: với `Flux.range(1,3)`, subscribe/request/onNext/complete có thể diễn ra **cùng thread và cùng call stack**. Với `WebClient` hoặc database reactive driver, phát tín hiệu có thể đến từ network I/O callbacks sau đó. Một publisher dài vô hạn có thể không bao giờ onComplete; nó cần cancellation hoặc chính sách kết thúc riêng.

**Quy tắc trách nhiệm:** Dựng pipeline chưa có nghĩa HTTP response đã gửi. Đăng ký cũng không có nghĩa đã nhận phần tử: demand `request(n)` và cách source phát tín hiệu quyết định. Completion/error/cancel cần kiểm soát tài nguyên, không xem việc method controller return là hoàn tất của operation.

## 3. Reactive Streams: Publisher, Subscriber, Subscription

Ba giao diện chính trong `org.reactivestreams`:

```java
public interface Publisher<T> {
    void subscribe(Subscriber<? super T> subscriber);
}

public interface Subscriber<T> {
    void onSubscribe(Subscription subscription);
    void onNext(T item);
    void onError(Throwable failure);
    void onComplete();
}

public interface Subscription {
    void request(long n);
    void cancel();
}
```

Đây là **chữ ký API minh họa**, không phải source file cần tự tạo lại vì thư viện cung cấp sẵn.

- **Publisher:** nguồn có thể cung cấp 0..N phần tử; `Mono` đại diện 0..1, `Flux` đại diện 0..N.
- **Subscriber:** người nhận callbacks và quyết định demand; phần lớn code WebFlux không phải tự viết Subscriber.
- **Subscription:** hợp đồng gắn một upstream-downstream relationship, nhận `request(n)` và `cancel()`.
- **Processor:** vừa Subscriber vừa Publisher; nhiều operators bên trong Reactor tạo các boundary tương đương.
- **Disposable:** kiểu tiện ích Reactor trả về từ các overload `subscribe` để hủy đăng ký, **không đồng nhất với API `Subscription` chuẩn**.

Giao thức có dạng:

```text
onSubscribe → onNext* → (onError | onComplete)?
```

`onError` và `onComplete` là terminal signals loại trừ nhau; chúng không cần có demand mới phát. `onNext` không được vượt số `request(n)` đã được chấp nhận, không gửi null và không gửi tiếp sau terminal. `cancel()` làm publisher cuối cùng ngừng phát, nhưng không nhất thiết cắt ngay công việc đang chạy hoặc rollback transaction.

## 4. Assembly time: khi nào Java đã chạy code?

Ví dụ:

```java
System.out.println("A");
Mono<String> mono = Mono.just(expensiveCall());
System.out.println("B");
```

Ở đây **`expensiveCall()` được đánh giá ngay** khi chương trình dựng argument truyền cho `Mono.just`, trước khi `mono` được gán. `Mono.just` giữ giá trị đã có. Nếu `expensiveCall()` gọi network hoặc JDBC blocking, việc này không được “biến thành lazy” nhờ bọc kết quả trong Mono.

Trái lại:

```java
Mono<String> mono = Mono.fromSupplier(() -> expensiveCall());
```

Lambda mô tả công việc sẽ được gọi khi có subscription (và logic source thực thi theo semantics của operator). Tạo biến `mono` chưa gọi `expensiveCall`.

**Cạm bẫy thứ hai:**

```java
Mono<String> mono = Mono.just("hello")
    .map(value -> value.toUpperCase());
```

Lambda `map` chưa chạy ở assembly; tuy nhiên biểu thức `Mono.just("hello")` và việc tạo operator objects đã thực thi. Không nên nói mọi dòng bên trong một biểu thức reactive đều deferred. **Dựng pipeline là thao tác Java bình thường; deferred là phần công việc được đặt vào các publisher/operator để chạy khi có subscription.**

### Khác biệt Mono.just, fromSupplier, fromCallable, defer

| Cách tạo | Khi tính value/source? | Ghi chú |
| --- | --- | --- |
| `Mono.just(value)` | `value` đã được tính **trước** lời gọi | Từ value non-null, phát lại giá trị này với subscriber |
| `Mono.justOrEmpty(nullable)` | `nullable` đã được tính trước | Null → complete empty, không onNext(null) |
| `Mono.fromSupplier(supplier)` | Supplier gọi trên subscription | Supplier trả null → empty theo Reactor contract |
| `Mono.fromCallable(callable)` | Callable gọi trên subscription | Checked exception được chuyển thành onError; null → empty |
| `Mono.defer(supplierOfMono)` | Factory tạo **một Publisher mới mỗi subscription** | Hữu ích khi cần đọc state/tạo pipeline tại subscribe time |
| `Flux.defer(supplierOfFlux)` | Tương tự nhưng 0..N | Không tự thay đổi thread model |
| `Mono.empty()` | Nguồn không có onNext | Vẫn có subscription/completion |
| `Mono.error(exception)` | Nguồn phát onError khi subscribe | Exception object có thể tạo tại assembly |
| `Mono.error(exceptionSupplier)` | Tạo exception theo factory khi subscribe | Thích hợp exception chứa thông tin subscription-local |

`Mono.defer` không chỉ “trì hoãn một phép tính”: nó hoãn **việc tạo cả Publisher** dựa trên trạng thái mới tại mỗi subscription. `fromSupplier`/`fromCallable` thường phù hợp tính đúng **một giá trị**. Nếu source phải được tái cấu hình theo Reactor Context của từng subscriber, dùng `Mono.deferContextual(...)`.

## 5. Ví dụ rõ nhất: giá trị eager và lazy khi subscribe hai lần

Tệp Java đầy đủ dưới đây yêu cầu Reactor Core (ví dụ trong Spring Boot WebFlux Maven project). Lớp `LazinessDemo.java`:

```java
package com.example.demo;

import java.util.concurrent.atomic.AtomicInteger;
import reactor.core.publisher.Mono;

public class LazinessDemo {

    public static void main(String[] args) {
        AtomicInteger counter = new AtomicInteger();

        int eagerValue = counter.incrementAndGet();
        Mono<Integer> eager = Mono.just(eagerValue);

        Mono<Integer> lazy = Mono.fromSupplier(
                counter::incrementAndGet);

        System.out.println("assembled=" + counter.get());
        System.out.println("eager1=" + eager.block());
        System.out.println("eager2=" + eager.block());
        System.out.println("lazy1=" + lazy.block());
        System.out.println("lazy2=" + lazy.block());
        System.out.println("final=" + counter.get());
    }
}
```

Trong một Maven project đã có `spring-boot-starter-webflux`, chạy main từ IDE hoặc `mvn exec:java` khi đã cấu hình exec plugin; **không** dùng `javac LazinessDemo.java` trần khi thiếu Reactor jars. `block()` chỉ được dùng ở **ranh giới main demo đồng bộ**, không dùng trong WebFlux handler/event-loop.

Stdout chính xác với nguồn đồng bộ:

```text
assembled=1
eager1=1
eager2=1
lazy1=2
lazy2=3
final=3
```

Giải thích:
1. `counter.incrementAndGet()` trước `just` chạy ngay, dù chưa subscriber: counter=1.
2. Hai `block()` trên `Mono.just(1)` tạo hai subscriptions nhưng vẫn phát **cùng giá trị đã chụp** là 1.
3. Hai `block()` trên `Mono.fromSupplier(counter::incrementAndGet)` tạo hai subscriptions khác nhau, gọi supplier thêm hai lần → 2 rồi 3.
4. `block()` bản thân là **một terminal operation khởi tạo subscription mới** cho Mono mỗi lần gọi.

Điều này dẫn tới câu hỏi quan trọng: nếu supplier **ghi database/gửi email/thanh toán**, việc subscribe lại có thể chạy side effect thêm một lần. Vì vậy không đặt non-idempotent side effects vào nguồn cold và cho `retry`/nhiều subscribers tùy ý mà không có bảo vệ nghiệp vụ.

## 6. Đăng ký: subscribe() thực sự làm gì?

Lời gọi `publisher.subscribe(subscriber)` tạo mối quan hệ giữa Subscriber và Publisher, thiết lập operator chain và truyền `Subscription` đến downstream.

Với một pipeline:

```java
Flux<Integer> stream = Flux.range(1, 3)
    .map(n -> n * 10)
    .filter(n -> n >= 20);

stream.subscribe(System.out::println);
```

Phần tạo `stream` chưa tiêu thụ phần tử. `subscribe(...)` khởi tạo quá trình; với `Flux.range` synchronous có thể thấy:

```text
20
30
```

Nhưng đây là trường hợp synchronous: `subscribe()` có thể không chờ network I/O hoàn tất trong nguồn async, và không đảm bảo mã sau `subscribe()` chạy sau `onComplete`.

### Subscription đi từ downstream về upstream

```text
downstream subscribe
     |
     v
filter.subscribe -> map.subscribe -> source.subscribe
                                        |
onSubscribe(subscription) <-------------|
      |
request(n) -----------------------------> upstream
                                        |
onNext / onComplete --------------------> downstream
```

Operator có thể bọc Subscription và biến đổi demand nội bộ. Một terminal Subscriber gọi `request(1)` không bảo đảm upstream nhận đúng một `request(1)` khi có `buffer`/`flatMap`/prefetch.

Các overload Reactor `subscribe()`/`subscribe(Consumer)` thông dụng thường yêu cầu unbounded demand; nếu muốn **quan sát request từng phần tử**, dùng `BaseSubscriber` hoặc `StepVerifier.create(publisher, 0)` với `thenRequest(n)`.

## 7. Demand: subscribe chưa chắc được nhận onNext

Reactive Streams yêu cầu Publisher **không được gửi nhiều hơn số onNext đã request**. Mới subscribe mà demand bằng 0, một source tuân thủ protocol không được phát dữ liệu `onNext`. Tuy nhiên nó có thể gửi terminal `onComplete`/`onError` không cần demand.

Ví dụ Reactor Test:

```java
StepVerifier.create(Flux.range(1, 3), 0)
    .expectSubscription()
    .thenRequest(1)
    .expectNext(1)
    .thenRequest(2)
    .expectNext(2, 3)
    .verifyComplete();
```

Đoạn này nằm trong Java test method đã có imports. Demand cộng dồn, không reset: `request(1)` rồi `request(2)` cấp tổng 3 quyền onNext.

Các lưu ý:

- `request(0)` và giá trị âm không phải “pause”; vi phạm spec, active Subscription phải báo `IllegalArgumentException` qua `onError`.
- `request(Long.MAX_VALUE)` được coi là unbounded demand, không có nghĩa source chắc chắn phát vô hạn.
- `cancel()` yêu cầu ngừng subscription; một số signals đang in-flight có thể đến ngay sau cancel.
- Các nhà vận chuyển hot dữ liệu không thể tự chậm lại có thể phải buffer/drop/fail theo chính sách; `Flux` không biến tất cả upstream thành backpressure-capable.
- Khi dùng `publishOn`, `flatMap`, `buffer`, `limitRate`, upstream demand và final subscriber demand có thể khác.

## 8. Lifecycle hooks: doFirst, doOnSubscribe, doOnRequest, doOnNext

Reactor có nhiều operator chỉ quan sát lifecycle mà không biến đổi dữ liệu.

| Hook | Mốc quan sát | Ghi chú |
| --- | --- | --- |
| `doFirst(Runnable)` | Trước khi subscription bắt đầu đi vào nguồn | Được gọi từ luồng subscribe, các doFirst nối tiếp chạy theo thứ tự ngược khai báo |
| `doOnSubscribe(Consumer<Subscription>)` | Subscription đã được tạo/đi qua operator | Hữu ích metrics; không dùng để chiếm quyền quản lý Subscription tùy tiện |
| `doOnRequest(LongConsumer)` | Một request(n) đi qua boundary | Quan sát demand tại vị trí operator, không phải request HTTP |
| `doOnNext(Consumer<T>)` | Nguồn phát một value qua operator | Có thể lặp với mỗi subscription, không tự giới hạn đến một lần |
| `doOnComplete(Runnable)` | Flux hoàn tất thành công | Chỉ Flux; không được gọi khi error/cancel |
| `doOnSuccess(Consumer<T>)` | Mono hoàn tất thành công | Nhận **null** khi Mono complete empty |
| `doOnError(Consumer<Throwable>)` | Lỗi đi qua operator | Không phục hồi lỗi; muốn fallback dùng onErrorResume |
| `doOnCancel(Runnable)` | Downstream cancel operator | Không nhất thiết giống thời điểm hoàn tất I/O vật lý |
| `doFinally(Consumer<SignalType>)` | Sau complete, error **hoặc cancel** | Quan trọng để release/log cuối cùng |
| `doOnDiscard(Class, Consumer)` | Cleanup các phần tử bị một số operator discard | Chỉ áp với operators hỗ trợ discard; không phải hook bắt mọi object |

**Thứ tự hook** còn phụ thuộc vị trí operator, tính synchronous/async của source và khả năng reentrant request. Không giả định log `doOnNext` luôn xuất hiện trước mọi `doOnSubscribe` trong pipeline; nhưng protocol vẫn đảm bảo subscriber phải nhận onSubscribe trước onNext.

### doFirst theo hướng subscription (ngược thứ tự khai báo)

```java
Mono.just("x")
    .doFirst(() -> System.out.println("one"))
    .doFirst(() -> System.out.println("two"))
    .subscribe();
```

Stdout đồng bộ:

```text
two
one
```

Vì `doFirst` có ý nghĩa “làm trước khi subscribe vào phần upstream”, hook được nối sau chạy trước. Đừng dùng `doFirst` cho non-idempotent mutation rồi dựa vào một subscription duy nhất, bởi subscribe lại/`retry` có thể chạy hook lại.

### doFinally xảy ra sau tín hiệu downstream

Một đoạn:

```java
Mono.just("x")
    .doFinally(signal -> cleanup())
    .subscribe(System.out::println);
```

Đây là snippet cần method `cleanup()`. `doFinally` được gọi khi sequence kết thúc vì complete/error/cancel, nhưng callback này có thể **chạy sau khi tín hiệu đã truyền xuống downstream**. Vì vậy test đọc biến cleanup ngay sau `block()` hoặc `verifyComplete()` đôi khi gặp race tùy scheduling; hãy đồng bộ đúng hoặc dùng công cụ test quan sát signal.

**Phân biệt `doFinally` và `doOnTerminate`:** `doOnTerminate` chỉ quan sát complete/error, không bảo đảm được gọi khi cancel; `doFinally` bao phủ cả cancellation. Với resource mang lifecycle riêng, `using`/`usingWhen` thường an toàn và diễn đạt ownership tốt hơn gắn cleanup thủ công vào mọi nhánh.

## 9. Mono empty, onSuccess(null), lỗi và cancel

`Mono<T>` có ba kiểu completion cơ bản:

```text
success with value: onSubscribe -> onNext(value) -> onComplete
success empty:      onSubscribe -> onComplete
error:              onSubscribe -> onError(ex)
cancel:             onSubscribe -> ...cancel (không nhất thiết onComplete)
```

`Mono#doOnSuccess(Consumer<T>)` khác `doOnNext`: doOnSuccess được gọi cả khi Mono hoàn tất rỗng, với argument `null`; `doOnNext` **không** được gọi cho empty.

Ví dụ:

```java
Mono<String> noValue = Mono.<String>empty()
    .doOnNext(v -> System.out.println("next=" + v))
    .doOnSuccess(v -> System.out.println("success=" + v));

noValue.subscribe();
```

Output:

```text
success=null
```

Đây là **null argument cho hook**, không phải `onNext(null)`. Reactive Streams **không cho phép** publisher gửi null value bằng onNext. Muốn diễn tả không có bản ghi, thường dùng `Mono.empty()` và map tới response status 404/204 phù hợp thay vì `Mono.just(null)`.

Lỗi `onError` là terminal: pipeline upstream không tiếp tục onNext sau lỗi. Operator `onErrorResume` có thể chuyển qua **publisher dự phòng**, không phải “phát tiếp sau terminal” từ subscription cũ. `retry(n)` làm **subscribe lại** vào upstream source, có thể lặp lại side effects.

## 10. Cold và hot: subscribe lại có thể chạy lại hay chia sẻ

### Cold publisher

`Flux.range(1,3)` là cold: mỗi subscription thường tạo một quá trình phát 1,2,3 riêng.

`Mono.defer(() -> repository.findById(id))` là lazy factory, nếu mỗi subscription dẫn tới một truy vấn reactive repository mới, subscribe hai lần có thể chạy truy vấn hai lần.

```java
Mono<String> cold = Mono.fromSupplier(
        () -> expensiveOperation());

cold.subscribe(v -> useFirst(v));
cold.subscribe(v -> useSecond(v));
```

Đây là **snippet** có ba methods được cung cấp bởi ứng dụng. Hai subscriptions là hai cuộc tiêu thụ, và supplier thông thường chạy hai lần. Không gọi `subscribe()` lần một để “warm up” rồi assume lần hai chỉ đọc response có sẵn.

### Hot/shared publisher

Hot sources như một `Sinks.Many` nhận sự kiện kể cả khi subscribers khác nhau hoặc đăng ký muộn. Một số share/replay operators tạo dạng multicast/caching khác nhau:

| Operator/cách dùng | Mục tiêu | Cảnh báo |
| --- | --- | --- |
| `Flux.share()` | Chia sẻ một subscription upstream trong lúc có subscribers | Late subscribers có thể bỏ lỡ dữ liệu cũ |
| `publish().refCount(n)` | Kết nối upstream khi đủ n subscribers, có thể disconnect khi giảm | Ngưỡng/scheduling/reconnect cần test |
| `Mono.cache()` | Cache terminal signal/value cho subscriptions về sau | Giữ lỗi hoặc kết quả lâu, cần cân nhắc TTL và tài nguyên |
| `Flux.cache(history)` | Replay số lượng item đã lưu | Giới hạn history/memory quan trọng |
| `Sinks.Many` | Phát các sự kiện từ producer thủ công | Buffer/overflow/backpressure policy phải rõ |

**Không mặc định cache là an toàn:** cache một response theo user/tenant trên bean singleton có thể làm rò dữ liệu giữa requests; cần cache key, TTL, invalidation và authorization. `Mono.cache()` mặc định có thể giữ kết quả/lỗi vô thời hạn theo lifecycle Mono instance; không dùng tùy tiện cho dữ liệu thay đổi hoặc chứa secrets.

### Hotness không phải đặc tính của Flux type

Hai biến cùng kiểu `Flux<String>` có thể một cold và một hot. Tính hot/cold do **source và sharing strategy**, không do tên lớp.

## 11. retry và repeat đều là re-subscription

`retry` không phải “chạy lại đoạn xử lý đã thất bại trong một subscription đang tiếp tục”. Thông thường nó **subscribe lại upstream** sau onError, chịu ảnh hưởng của `retry(n)`, backoff, loại lỗi và trạng thái nguồn.

```java
AtomicInteger attempts = new AtomicInteger();

Mono<String> result = Mono.fromCallable(() -> {
    int attempt = attempts.incrementAndGet();
    if (attempt < 3) {
        throw new IllegalStateException("temporary");
    }
    return "ok";
}).retry(2);
```

Đây là đoạn trong method có import `java.util.concurrent.atomic.AtomicInteger`. Khi subscribe một lần với source đồng bộ, attempt #1 và #2 lỗi, #3 thành công; `retry(2)` cho phép hai lần thử lại sau lần đầu. Nếu gọi `result.block()` lần thứ hai, đó lại là một subscription khác, biến `attempts` vẫn được giữ bên ngoài nên kết quả có thể khác.

`repeat` tái đăng ký sau complete (theo semantics/operator cụ thể), không chỉ sau error. `retryWhen` có thể dùng retry budget/backoff nhưng phải phân loại lỗi có thể retry; không retry tất cả HTTP 4xx hoặc các write không idempotent.

**Production:** Với payment/order creation, dùng idempotency key và DB uniqueness/transaction để ngăn side effects trùng nếu client retry hoặc Reactor retry; chỉ dựa vào operator là không đủ.

## 12. Thread và scheduler không do subscribe tự sinh

Reactive Streams không bắt buộc callback chạy thread riêng. `Flux.range`/`Mono.just` có thể tạo tín hiệu đồng bộ ngay trong call stack subscription. Reactor `Schedulers` cho phép chuyển execution context:

- `subscribeOn(scheduler)`: ảnh hưởng tới nơi subscription/upstream work được thực thi; thường dùng để chuyển blocking nguồn legacy ra worker.
- `publishOn(scheduler)`: chuyển xử lý downstream kể từ vị trí đó sang worker scheduler.
- `Schedulers.parallel()`: phù hợp CPU tasks ngắn, không dành cho blocking I/O lâu.
- `Schedulers.boundedElastic()`: bounded scheduler dành cho bridge tới blocking legacy code, vẫn tốn threads/queue.
- `WebClient` và reactive database drivers: thường có I/O non-blocking, không cần tự bọc bằng `fromCallable` khi client đã trả Mono/Flux.

Ví dụ tích hợp legacy API:

```java
Mono<String> callLegacy() {
    return Mono.fromCallable(
            () -> legacyJdbcService.queryOne())
        .subscribeOn(Schedulers.boundedElastic());
}
```

Đây là **snippet** cần bean `legacyJdbcService`. Source deferred đến subscription và chạy trên boundedElastic worker; **JDBC vẫn blocking**. Không gọi `Mono.just(legacyJdbcService.queryOne())` trong WebFlux controller, vì `queryOne()` chạy **ngay trên thread gọi method**, có thể là Netty event loop.

### block() cũng tạo subscription

`mono.block()` là một terminal consumer tạo subscription **mới** rồi chờ; không dùng trong WebFlux handler hoặc reactor-netty event-loop. Ở Java console/demo/tests khi ở thread blocking cho phép, `block()` có thể là công cụ minh họa nhưng không phải giải pháp production cho reactive pipeline.

`blockOptional()`/`block(Duration)` cũng khởi tạo subscription; timeout của blocking caller không đồng nghĩa nguồn I/O đã rollback side effects.

## 13. doOnNext và side effects: quan sát khác xử lý nghiệp vụ

`doOnNext` được thiết kế cho logging, metrics, tracing hoặc một side effect kiểm soát được:

```java
Flux<Order> monitored = orders
    .doOnSubscribe(s -> metrics.started())
    .doOnNext(order -> metrics.itemReceived())
    .doOnError(e -> metrics.failed())
    .doFinally(signal -> metrics.finished(signal));
```

Đây là snippet phụ thuộc `orders` và `metrics`. Nếu được subscribe hai lần, các hooks có thể chạy hai lần. Nếu `metrics.finished` ném exception hoặc block, nó làm khó lifecycle; hooks nên nhanh, không làm thay đổi business semantics.

**Không dùng `doOnNext(order -> paymentService.charge(order))` làm cơ chế đảm bảo charge exactly once**. Retry/repeat/multiple subscriptions có thể gọi lại. Nếu side effect là một phần nghiệp vụ, diễn tả nó qua một reactive operator trả Publisher (`flatMap`/`then`) với idempotency và transaction phù hợp; không tạo fire-and-forget subscribe bên trong hook.

### Sai anti-pattern

```java
// Sai: chạy background subscription ngoài quản lý của caller.
return repository.save(order)
    .doOnNext(saved -> sendEmail(saved).subscribe());
```

Đây là **snippet phản ví dụ**, không phải method độc lập. Nếu WebFlux HTTP caller cancel sau khi `repository.save` phát value, email đã được subscribe riêng và có thể tiếp tục độc lập; error của email cũng có thể mất. Một lựa chọn hợp lý hơn:

```java
return repository.save(order)
    .flatMap(saved ->
        sendEmail(saved).thenReturn(saved));
```

Ở đây `sendEmail(saved)` trả `Mono<Void>`; chuỗi cha quản lý completion/error/cancel của email. Cách này vẫn không cung cấp exactly-once transactional email, nên production có thể dùng outbox/message broker/idempotency.

## 14. Quản lý tài nguyên qua complete, error và cancel

Một nguồn có thể mở tệp, database cursor, websocket session hoặc lease. Cleanup chỉ trong `doOnComplete` sẽ bỏ lỡ `onError` và `cancel`.

### Dùng resource scope

Reactor có `Flux.using`/`Mono.using` và `usingWhen`:

- `using(resourceSupplier, sourceFactory, resourceCleanup)`: phù hợp resource xử lý đồng bộ/`AutoCloseable`, liên kết resource lifecycle với subscription.
- `usingWhen(resourcePublisher, resourceClosure, asyncCompleteCleanup, asyncErrorCleanup, asyncCancelCleanup)`: phù hợp resource acquire/cleanup **bất đồng bộ** (ví dụ reactive connection/transaction), với callback riêng cho terminal paths.

Ví dụ một source từ file resource (minh họa):

```java
Flux<String> lines = Flux.using(
    () -> java.nio.file.Files.lines(path),
    stream -> Flux.fromStream(stream),
    java.util.stream.Stream::close);
```

Đây là snippet method đã có `java.nio.file.Path path`, Reactor dependency và import `Flux`. `Files.lines` là blocking file I/O; trên WebFlux không nên chạy nó trực tiếp trên Netty event-loop. Nếu buộc đọc file theo kiểu này, cân nhắc `subscribeOn(Schedulers.boundedElastic())` hoặc API I/O phù hợp, đồng thời giới hạn số file, size và tài nguyên.

Đừng tự giả định `doFinally` luôn hoàn tất cleanup **trước khi** downstream nhận complete. Với `usingWhen`, thứ tự cleanup và truyền terminal signal có semantics riêng, cần kiểm tra tài liệu/phiên bản. Khi có transaction, dùng Reactor-aware transaction management thay vì trộn ThreadLocal JDBC transaction manager.

### Cleanup trên cancel và HTTP disconnect

Khi WebFlux subscriber HTTP bị cancel (client disconnect/timeout downstream), upstream có thể nhận `cancel`. Các callbacks `doFinally(SignalType.CANCEL)`, `usingWhen` asyncCancel handler giúp dọn resources. Tuy nhiên `cancel` **không bảo đảm** network/database request vật lý dừng ngay hoặc rollback side effects đã commit.

Nếu pipeline giữ message broker consumer hoặc event listener, cleanup phải unsubscribe/remove listener; không lưu references trong static map vô hạn. Cancel có thể đến từ downstream operator `take`/`timeout`, không chỉ browser đóng tab.

## 15. onErrorResume, timeout, take và doFinally

Một số operator làm subscription chấm dứt theo các con đường khác nhau:

| Operator/tình huống | Điều có thể xảy ra |
| --- | --- |
| `take(3)` với nguồn còn dữ liệu | Lấy đủ ba phần tử, cancel upstream, downstream có thể complete |
| `timeout(Duration)` | Khi không có tín hiệu đúng hạn, cancel upstream và phát TimeoutException downstream |
| `onErrorResume(e -> fallback)` | Chuyển sang publisher dự phòng khi upstream lỗi |
| `switchIfEmpty(fallback)` | Khi upstream complete empty, subscribe fallback |
| `retry(2)` | Sau onError, subscribe upstream lại tối đa hai lần |
| HTTP client disconnect | Downstream HTTP subscriber có thể cancel |
| `doFinally` | Nhận `ON_COMPLETE`/`ON_ERROR`/`CANCEL` trên boundary tương ứng |

**Quan trọng:** Một pipeline có thể có **nhiều `doFinally` ở các vị trí khác nhau**. Ví dụ source nằm trước `take(3)` nhận cancel, còn downstream sau `take(3)` nhận complete. Vì thế không khẳng định “toàn bộ chuỗi có đúng một signal type duy nhất” khi các operators biến đổi terminal behavior.

Một `Flux` kết thúc rỗng (no values) vẫn có subscription/completion; `switchIfEmpty` có thể kích hoạt một publisher khác. Nếu fallback là `Mono.just(expensiveCall())`, expensive call **đã chạy** khi tạo fallback tại assembly; dùng `Mono.defer(...)` nếu chỉ muốn gọi khi thật sự rỗng.

## 16. Reactor Context: dữ liệu gắn subscription, không phải ThreadLocal

Trong WebFlux, request processing và signals có thể đi qua nhiều threads/schedulers. Do đó không nên dựa vào một `ThreadLocal` thường để giữ request ID, locale, user context hoặc tracing data xuyên suốt pipeline. Reactor có `Context`/`ContextView` gắn với **Subscriber chain**, phù hợp metadata bất biến thuộc subscription.

Ví dụ:

```java
Mono<String> message = Mono.deferContextual(ctx ->
    Mono.just("request=" + ctx.get("requestId")));

String result = message
    .contextWrite(ctx -> ctx.put("requestId", "r-42"))
    .block();
```

Đây là snippet cho main/test thread với Reactor dependency. Giá trị `result` là:

```text
request=r-42
```

Lưu ý `block()` dùng ở ranh giới demo, không trong WebFlux event-loop. Reactor Context không phải một bản sao toàn bộ Servlet request; không tự chứa user/token trừ khi ứng dụng/framework đặt vào đúng context. Security reactive context có APIs riêng của Spring Security.

### Context và subscription boundaries

Mỗi lần subscribe tạo subscription context tương ứng. `contextWrite` ảnh hưởng các operators upstream theo quy tắc Reactor; không phải một global ThreadLocal được update cho mọi task. Nếu bạn tự `subscribe()` bên trong controller/service, bạn có thể tạo **subscription mới không mang cùng Context** của HTTP request, làm mất trace/security metadata.

Muốn truyền metadata qua service, có thể dùng method params explicit hoặc `Mono.deferContextual` có chủ đích, không giấu business inputs trong context khi chúng nên là tham số rõ ràng.

## 17. WebFlux: framework subscribe ở HTTP boundary

Trong controller WebFlux:

```java
@GetMapping("/products/{id}")
public Mono<ProductDto> one(@PathVariable String id) {
    return productService.find(id);
}
```

Controller chỉ trả một Publisher. **Spring WebFlux HTTP infrastructure là downstream subscriber**, đăng ký để đọc kết quả và ghi response. Nó sở hữu phần quan trọng của lifecycle: demand, response encoding, cancellation và xử lý errors trước khi response commit.

Không cần (và thường không được) làm:

```java
@GetMapping("/bad")
public Mono<Void> bad() {
    productService.saveSomething().subscribe();
    return Mono.empty();
}
```

Đây là **anti-pattern minh họa**, không phải file có sẵn. Server có thể gửi HTTP thành công trước khi `saveSomething` hoàn tất, lỗi bị tách khỏi HTTP, cancellation không lan truyền và context có thể thất lạc.

Thay bằng:

```java
@GetMapping("/good")
public Mono<Void> good() {
    return productService.saveSomething();
}
```

Đây cũng là snippet cần bean. Khi method trả Publisher, framework quản lý subscription. Nếu operation đã là background workflow độc lập, hãy dùng queue/broker/task management có giám sát, không giấu nó trong `subscribe()` của một request handler.

### Controller method gọi lúc nào?

**Sự kiện gọi method controller để tạo Mono/Flux là phần xử lý HTTP request; nó có thể chạy trước khi publisher được subscribe.** Nếu code gọi hàm blocking trước khi return, ví dụ `Mono.just(repository.find())`, hàm đó chạy ngay khi handler được gọi. **Lazy là logic được hoãn trong Publisher, không phải toàn bộ method controller.**

## 18. Ví dụ Spring Boot WebFlux có thể chạy: eager, lazy, request lifecycle

Tạo một Maven project từ Spring Initializr:

- Java 17+ và Spring Boot 3.x.
- `spring-boot-starter-webflux`.
- `spring-boot-starter-test` (test scope) và `io.projectreactor:reactor-test` (test scope nếu chưa có).
- **Không thêm `spring-boot-starter-web`** nếu bạn muốn Boot tự chọn WebFlux reactive application type khi cả hai starters có mặt.

Cấu trúc:

```text
src/main/java/com/example/demo/
  DemoApplication.java
  SequenceService.java
  SequenceController.java
src/test/java/com/example/demo/
  SequenceControllerTest.java
  LifecycleTest.java
```

App không cần database. `AtomicInteger` tạo số đếm per service singleton, giúp quan sát hành vi khi có các HTTP requests; đây là teaching demo, không phải nguồn sequence/version phân tán an toàn.

### 18.1. DemoApplication.java

```java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
```

### 18.2. SequenceService.java

```java
package com.example.demo;

import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
public class SequenceService {

    private final AtomicInteger sequence = new AtomicInteger();

    public Mono<ValueResponse> nextValue() {
        // Tạo một publisher tại invocation time; chưa tăng counter.
        return Mono.fromSupplier(() ->
            new ValueResponse(sequence.incrementAndGet()));
    }

    public Mono<ValueResponse> echoLazy(String value) {
        // Mono.defer tạo Publisher tại subscription time.
        return Mono.defer(() -> Mono.just(
            new ValueResponse(value.length())));
    }

    public record ValueResponse(int value) {}
}
```

`sequence.incrementAndGet()` chỉ chạy khi có subscription tới `nextValue()`, không phải ngay khi method service return Mono. `echoLazy` dùng `defer` nhằm minh họa factory theo subscription; với chuỗi immutable đã biết `value.length()` không tốn đáng kể, nên trong production không nhất thiết phải dùng `defer` cho việc nhỏ như vậy.

### 18.3. SequenceController.java

```java
package com.example.demo;

import java.time.Duration;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;
import org.springframework.http.HttpStatus;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api/lifecycle")
public class SequenceController {

    private final SequenceService service;

    public SequenceController(SequenceService service) {
        this.service = service;
    }

    @GetMapping(path = "/next",
                produces = MediaType.APPLICATION_JSON_VALUE)
    public Mono<SequenceService.ValueResponse> next() {
        // WebFlux subscribe, controller KHÔNG gọi subscribe/block.
        return service.nextValue();
    }

    @GetMapping(path = "/double",
                produces = MediaType.APPLICATION_JSON_VALUE)
    public Mono<SequenceService.ValueResponse> doubleNext() {
        // zip hai Mono khác nhau tạo hai subscriptions tới source.
        return Mono.zip(service.nextValue(), service.nextValue())
            .map(tuple -> new SequenceService.ValueResponse(
                tuple.getT1().value() + tuple.getT2().value()));
    }

    @GetMapping(path = "/stream/{count}",
                produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public Flux<SequenceService.ValueResponse> stream(
            @PathVariable int count) {

        if (count < 1 || count > 5) {
            return Flux.error(new ResponseStatusException(
                HttpStatus.BAD_REQUEST,
                "count must be 1..5"));
        }

        return Flux.range(1, count)
            .delayElements(Duration.ofMillis(80))
            .map(SequenceService.ValueResponse::new);
    }

    @GetMapping(path = "/empty",
                produces = MediaType.APPLICATION_JSON_VALUE)
    public Mono<SequenceService.ValueResponse> empty() {
        return Mono.empty();
    }
}
```

**Giải thích endpoint:**

- `GET /next` trả một `Mono.fromSupplier`; mỗi HTTP request thông thường có subscription riêng, làm counter tăng một lần. Nếu proxy/client retry HTTP, counter có thể tăng thêm; không dùng GET có side effects quan trọng như demo này trong production.
- `GET /double` tạo **hai Mono khác nhau** và `zip` subscribe cả hai; khi có một subscription vào zip, counter thường tăng hai lần và output là tổng hai số liên tiếp, nhưng concurrency/scheduling giữa nhiều HTTP requests khiến tổng không deterministic. Dùng bài test riêng/isolated để kiểm.
- `GET /stream/{count}` phát một `Flux` finite dưới dạng server-sent events; `delayElements` dùng scheduler theo thời gian, không bảo đảm đúng từng millisecond.
- `GET /empty` complete không có item; WebFlux có thể tạo một response rỗng với status mặc định tùy handling. Nếu muốn **404** rõ ràng khi không có dữ liệu, dùng `switchIfEmpty(Mono.error(new ResponseStatusException(HttpStatus.NOT_FOUND)))` hoặc `ResponseEntity` phù hợp.
- Controller không tự `subscribe()`. Nếu client dừng đọc stream, WebFlux có thể cancel subscription và Reactor dọn timers/operators theo semantics.

**Lưu ý API design:** Demo `GET /next` cố ý có side effect tăng counter để dễ quan sát subscription, **không phù hợp HTTP safe-method semantics trong dịch vụ thực**. Với state mutation, dùng POST/PUT đúng business contract, authorization/idempotency và transaction. Nếu không muốn client caching/prefetch làm thay đổi counter, đừng sử dụng GET cho side effects ngoài demo.

### 18.4. Chạy demo

Với Maven wrapper của project:

```bash
./mvnw spring-boot:run
```

Windows PowerShell:

```powershell
.\mvnw.cmd spring-boot:run
```

Mặc định server nhận ở port 8080 khi chưa tùy chỉnh `server.port`. Mã trên cần classpath Spring Boot/Reactor/Jackson; `javac SequenceController.java` riêng lẻ **không** đủ dependencies.

## 19. curl: quan sát subscription và response

### Mỗi GET /next sinh một kết quả

```bash
curl -i 'http://localhost:8080/api/lifecycle/next'
curl -i 'http://localhost:8080/api/lifecycle/next'
```

Nếu mới khởi động app và không có request cạnh tranh đến `/next` hoặc `/double`, JSON lần lượt:

```json
{"value":1}
```

và:

```json
{"value":2}
```

Counter nằm trong một singleton service và reset khi restart; **không** kết luận mọi môi trường/tất cả concurrent requests đều cho đúng dãy 1,2. Nếu HTTP client tự retry, một request người dùng có thể có nhiều subscription ở server.

### Hai subscriptions trong một request /double

```bash
curl -i 'http://localhost:8080/api/lifecycle/double'
```

Nếu counter hiện là 2 và không có concurrent calls, hai `nextValue()` suppliers trả 3 và 4; response:

```json
{"value":7}
```

`Mono.zip` chỉ hoàn tất khi cả hai sources có value; nếu một source `Mono.empty()`, zip có thể complete empty và các source khác có thể bị cancel. Đừng dùng zip cho việc cần bảo đảm cả hai side effects được thực thi dù một source empty.

### Streaming events

```bash
curl -N -i 'http://localhost:8080/api/lifecycle/stream/3'
```

Dữ liệu SSE (minh họa phần body):

```text
data:{"value":1}

data:{"value":2}

data:{"value":3}

```

Lệnh `-N` giảm buffering từ curl. Thời điểm các events phụ thuộc scheduler/network, không lấy thời gian 80ms làm hard guarantee. Một event không nhất thiết trùng một TCP packet.

### Empty Mono và lỗi validation

```bash
curl -i 'http://localhost:8080/api/lifecycle/empty'
curl -i 'http://localhost:8080/api/lifecycle/stream/100'
```

`/empty` có HTTP response không có JSON value; `/stream/100` phát lỗi 400 nếu chưa commit response. Cách trình bày body lỗi phụ thuộc Spring Boot/Problem Details configuration; không hardcode JSON nếu chưa định nghĩa error handler riêng.

## 20. StepVerifier: test chính xác vòng đời trong Reactor

Với `reactor-test`, kiểm thử subscription được trigger tại `verify...()`, không phải ngay khi tạo biến StepVerifier. Tệp `src/test/java/com/example/demo/LifecycleTest.java`:

```java
package com.example.demo;

import java.time.Duration;
import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.Test;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.*;

class LifecycleTest {

    @Test
    void justCapturesBeforeSubscription() {
        AtomicInteger counter = new AtomicInteger();

        Mono<Integer> eager = Mono.just(counter.incrementAndGet());

        assertEquals(1, counter.get());
        StepVerifier.create(eager)
            .expectNext(1)
            .verifyComplete();
        StepVerifier.create(eager)
            .expectNext(1)
            .verifyComplete();
        assertEquals(1, counter.get());
    }

    @Test
    void deferFactoryRunsOnEverySubscription() {
        AtomicInteger counter = new AtomicInteger();

        Mono<Integer> lazy = Mono.defer(() ->
            Mono.just(counter.incrementAndGet()));

        assertEquals(0, counter.get());

        StepVerifier.create(lazy)
            .expectNext(1)
            .verifyComplete();
        StepVerifier.create(lazy)
            .expectNext(2)
            .verifyComplete();

        assertEquals(2, counter.get());
    }

    @Test
    void backpressureRequiresRequestForOnNext() {
        StepVerifier.create(Flux.range(1, 3), 0)
            .expectSubscription()
            .thenRequest(1)
            .expectNext(1)
            .thenRequest(2)
            .expectNext(2, 3)
            .verifyComplete();
    }

    @Test
    void emptyMonoCompletesWithoutValue() {
        StepVerifier.create(Mono.empty(), 0)
            .expectSubscription()
            .verifyComplete();
    }

    @Test
    void retryTriggersNewSourceSubscriptions() {
        AtomicInteger count = new AtomicInteger();

        Mono<String> eventual = Mono.defer(() -> {
            int attempt = count.incrementAndGet();
            if (attempt < 3) {
                return Mono.error(
                    new IllegalStateException("temporary"));
            }
            return Mono.just("ok");
        }).retry(2);

        StepVerifier.create(eventual)
            .expectNext("ok")
            .verifyComplete();

        assertEquals(3, count.get());
    }

    @Test
    void cancellationStopsFiniteSequence() {
        StepVerifier.create(Flux.range(1, 100), 0)
            .expectSubscription()
            .thenRequest(2)
            .expectNext(1, 2)
            .thenCancel()
            .verify();
    }

    @Test
    void timeoutPropagatesErrorWithVirtualTime() {
        StepVerifier.withVirtualTime(() ->
                Mono.never().timeout(Duration.ofSeconds(5)))
            .expectSubscription()
            .thenAwait(Duration.ofSeconds(5))
            .expectError(java.util.concurrent.TimeoutException.class)
            .verify();
    }
}
```

**Kiểm thử này không dùng network** và không giả định một executor bất kỳ. `StepVerifier.withVirtualTime` yêu cầu publisher với time operators được tạo **bên trong lambda supplier** như ở ví dụ; tạo `Mono.delay` trước lambda có thể làm virtual-time test sai. Khi cần biết `doFinally` đã chạy, hãy xét callback có thể được thực thi sau downstream terminal, dùng đồng bộ test đúng thay vì đọc một boolean ở thời điểm chưa bảo đảm.

Đặt `StepVerifier.create(publisher, 0)` rồi `expectNext(...)` ngay **không** `thenRequest(...)` sẽ khiến source đúng protocol không phát item; test không phải chứng minh source lỗi. Cần có `expectSubscription` hoặc request step phù hợp.

## 21. WebTestClient: test HTTP WebFlux từ controller

Tệp `src/test/java/com/example/demo/SequenceControllerTest.java`:

```java
package com.example.demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

@SpringBootTest(webEnvironment =
        SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class SequenceControllerTest {

    @Autowired
    WebTestClient client;

    @Test
    void nextProducesOneValue() {
        client.get().uri("/api/lifecycle/next")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.value").isNumber();
    }

    @Test
    void invalidStreamingCountReturns400() {
        client.get().uri("/api/lifecycle/stream/100")
            .exchange()
            .expectStatus().isBadRequest();
    }

    @Test
    void streamCompletesAfterThreeEvents() {
        Flux<String> response = client.get()
            .uri("/api/lifecycle/stream/3")
            .accept(MediaType.TEXT_EVENT_STREAM)
            .exchange()
            .expectStatus().isOk()
            .returnResult(String.class)
            .getResponseBody();

        StepVerifier.create(response)
            .expectNextMatches(s -> s.contains("\"value\":1"))
            .expectNextMatches(s -> s.contains("\"value\":2"))
            .expectNextMatches(s -> s.contains("\"value\":3"))
            .verifyComplete();
    }
}
```

**SSE codec caveat:** String decoding với `text/event-stream` phụ thuộc message readers và cấu hình WebTestClient/Reactor Netty; trong dự án thực có thể decode thành `ServerSentEvent<ValueResponse>` hoặc object DTO bằng `ParameterizedTypeReference` phù hợp nếu codec không trả mỗi event thành một String. Đừng coi mỗi TCP chunk là một Reactor element, và đừng khẳng định streaming luôn flush đúng từng khoảng thời gian.

**Độ ổn định của test:** Không assert counter chính xác giữa nhiều test HTTP vì singleton state có thể được chia sẻ với test khác và JUnit chạy theo thứ tự không cố định. Với Spring Security, test cần user/authorization/CSRF theo endpoint. Mock WebTestClient và HTTP server thực có khác biệt về transport/disconnect, nên cần thêm integration tests để xác minh cancellation từ client.

Chạy:

```bash
./mvnw test
```

PowerShell:

```powershell
.\mvnw.cmd test
```

Đây là ví dụ có thể chạy trong Boot 3 project đúng dependencies; không phải tuyên bố đã chạy trên workspace người dùng.

## 22. Side effects, HTTP, WebClient và retry đúng ranh giới

### WebClient Mono thường không gửi HTTP khi chỉ được dựng

Ví dụ:

```java
Mono<ProductDto> product = webClient.get()
    .uri("/products/{id}", id)
    .retrieve()
    .bodyToMono(ProductDto.class);
```

Đây là snippet trong class có `webClient`, `id` và `ProductDto`. Việc dựng `Mono` **thường chưa gửi HTTP request**; network exchange diễn ra khi subscriber subscribe. Nếu gọi `product.block()` hai lần hoặc có hai independent subscribers tới nguồn cold, có thể có **hai outbound HTTP requests**, trừ khi source có sharing/cache semantics khác.

Với WebFlux controller, **trả Mono này cho framework**, không `subscribe()` để “gửi request trước” rồi return Mono khác.

### Khi side effect phải chạy chính xác một lần

Reactive Streams không cung cấp exactly-once mutation semantics. Nếu một `POST`/payment pipeline có:
- client retry HTTP,
- `retryWhen`,
- duplicate subscription,
- network timeout sau server commit,

thì side effects có thể chạy lại. Phải có idempotency keys, transaction/outbox, uniqueness constraints, authorized ownership và retry policy. Cache một Mono trong memory **không thay thế** cơ chế lưu durable cho exactly-once trên nhiều pods/restarts.

### Không trộn blocking service call vào assembly

Sai:

```java
@GetMapping("/bad")
public Mono<String> bad() {
    return Mono.just(jdbcService.fetch());
}
```

Ở đây `jdbcService.fetch()` block ngay khi handler method chạy. Nếu bắt buộc tích hợp legacy JDBC:

```java
@GetMapping("/bridge")
public Mono<String> bridge() {
    return Mono.fromCallable(() -> jdbcService.fetch())
        .subscribeOn(Schedulers.boundedElastic());
}
```

Đây là **snippets** cần bean `jdbcService` và imports; muốn code compile trong sample controller phải thêm dependency/data service tương ứng. BoundedElastic chỉ **di chuyển** blocking work sang bounded workers; không biến JDBC thành reactive driver hoặc tự giải quyết connection pool, timeout, cancellation.

## 23. Những sai lầm cần tránh

1. **“Khai báo Flux tức là chạy dữ liệu”**: với cold source, chưa subscribe thường chưa phát data.
2. **“Mọi thứ trong Mono đều lazy”**: argument `Mono.just(expensiveCall())` đã chạy tại assembly.
3. **“Subscribe luôn chạy trên thread khác”**: nguồn đồng bộ như `Flux.range` có thể phát ngay trên cùng thread.
4. **“subscribe không có request thì vẫn onNext”**: publisher đúng protocol phải đợi demand.
5. **“block() không ảnh hưởng”**: nó tạo subscription mới, chặn thread và có thể lặp side effects.
6. **Tự subscribe trong WebFlux controller**: đánh mất response lifecycle/error/cancellation control.
7. **Đọc resource trong controller trước khi return Mono**: có thể block event loop.
8. **Dùng `Mono.just(null)`**: onNext(null) không hợp lệ; dùng Mono.empty/justOrEmpty.
9. **Dùng `doOnNext` để gửi email/thanh toán**: có thể chạy nhiều lần khi retry hoặc multi-subscribe.
10. **Tin cold source được cache tự động**: mỗi subscription có thể query lần nữa.
11. **Tin `Mono.cache()` phù hợp dữ liệu user nhạy cảm**: cần key, TTL, auth, invalidation.
12. **Dùng `retry` với non-idempotent POST**: có thể tạo duplicate records/charges.
13. **Tin `onErrorResume` tiếp tục upstream sau onError**: thực chất chuyển sang fallback publisher.
14. **Tin `take(3)` luôn gửi complete tới upstream**: thường cancel upstream sau đủ dữ liệu.
15. **Chỉ cleanup trong `doOnComplete`**: bỏ sót lỗi và cancel.
16. **Cho rằng doFinally đã chạy trước khi downstream thấy completion**: callback thường sau terminal propagation.
17. **Gọi Subscription.request(0) để tạm dừng**: sai protocol.
18. **Kỳ vọng request(1) cuối pipeline = request(1) database**: operator prefetch/reshaping.
19. **Dùng ThreadLocal như request context trên mọi scheduler**: Reactor Context có semantics riêng.
20. **Cho rằng cancel rollback side effects**: resource/task có thể đã commit.
21. **Đặt một hot source vào pipeline rồi giả định mọi subscriber thấy lịch sử**: replay phải cấu hình.
22. **Không giới hạn buffers từ hot source**: nguy cơ OOM.
23. **Dùng StepVerifier với initialRequest=0 và expectNext ngay**: test bị treo vì thiếu demand.
24. **Đặt source timed ngoài withVirtualTime lambda**: không điều khiển được scheduler ảo đúng.
25. **Hardcode thứ tự/tên thread khi có publishOn**: scheduler semantics cần test có kiểm soát.
26. **Dùng block trong WebFlux event loop**: thread starvation hoặc Reactor NonBlockingThread exception.
27. **Không giải phóng file/connection khi client disconnect**: leak.
28. **Không test no-value/error/cancel, chỉ test happy path**: bỏ sót terminal lifecycle.
29. **Dùng GET có side effect mutation để biểu diễn API thật**: vi phạm kỳ vọng safe method/retry/cache.
30. **Nghĩ HTTP response hoàn tất ngay khi controller return Mono**: nó hoàn tất khi publisher xử lý terminal và writer flush.
31. **Lấy một Reactive Repository Mono rồi subscribe trong service**: ngắt transaction/retry/error tracing khỏi caller.
32. **Gộp mọi lỗi thành Mono.empty**: đánh mất lý do failure; phân biệt 404/no value với outage.
33. **Không xét cancellation khi kết nối SSE dài**: giữ timer/broker subscription không cần thiết.
34. **Tin Mono.fromCallable không block**: Callable vẫn có thể block thread nó chạy.
35. **Mỗi lần subscribe một publisher hot cũng tạo HTTP request mới**: hot/shared semantics phải được xem theo implementation.

## 24. Checklist dùng trong code review và production

### Dựng pipeline và subscribe

- [ ] Mọi lời gọi có side effects tại assembly time được xác định rõ?
- [ ] `Mono.just(...)` chỉ nhận value đã có, không bao một blocking call ngoài ý muốn?
- [ ] Khi cần value per subscription, dùng `defer/fromSupplier/fromCallable` đúng?
- [ ] Biết publisher cold/hot/shared/cache hay không trước khi tạo nhiều subscriptions?
- [ ] Các nguồn có state mutable per subscription được tạo đúng chỗ (defer nếu cần)?
- [ ] WebFlux controller trả Mono/Flux, không `subscribe/block`?
- [ ] Background job thật sự độc lập có executor/queue/monitoring riêng?

### Signals, error, cancel, cleanup

- [ ] Các callbacks terminal không bị phát hai lần?
- [ ] `request(n)` dương và demand không bị vượt?
- [ ] Các operators `flatMap`/`buffer`/`publishOn` có resource/concurrency/prefetch budget?
- [ ] `retry/repeat` có phân loại lỗi, backoff và idempotency?
- [ ] Cleanup có đường hoàn tất, lỗi **và cancellation**?
- [ ] `using/usingWhen` được dùng khi sở hữu connection/file resource?
- [ ] Event/broker subscriptions được dọn khi client disconnect?
- [ ] Không coi cancellation là transaction rollback?
- [ ] Reactor Context/security/trace được bảo toàn qua publisher chain?

### Kiểm thử

- [ ] Test phân biệt eager `just` và lazy `fromSupplier/defer`?
- [ ] Test hai subscriptions kích hoạt bao nhiêu lần supplier?
- [ ] Test demand ban đầu 0, `thenRequest` và `thenCancel`?
- [ ] Test `Mono.empty`, onError, fallback và retry resubscription?
- [ ] Test timeout bằng `withVirtualTime` và lazy publisher supplier?
- [ ] Test SSE/JSON HTTP qua WebTestClient/curl đúng lifecycle?
- [ ] Không assert timer hoặc scheduler thread name cứng trong test async?
- [ ] HTTP client disconnect được integration-test nếu API streaming dài?
- [ ] Không cache/replay dữ liệu riêng tư giữa users/tenants?

## 25. Câu hỏi tự kiểm tra

**1.** Khi `Mono.just(service.load())` được tạo, `service.load()` chạy lúc nào?

**Đáp án:** Ngay tại assembly khi đánh giá argument trước lời gọi `just`; không đợi subscribe.

**2.** Khi `Mono.fromSupplier(service::load)` được tạo, method chạy khi nào?

**Đáp án:** Khi có subscription và source được thực thi; mỗi subscription thông thường gọi supplier lại.

**3.** `Mono.defer(...)` khác `fromSupplier(...)` ra sao?

**Đáp án:** `defer` nhận factory tạo Publisher mới theo subscription; `fromSupplier` nhận factory cho một value.

**4.** `publisher.subscribe(subscriber)` trả kiểu gì theo Reactive Streams JVM spec?

**Đáp án:** `void`; Subscription đi qua `subscriber.onSubscribe(subscription)`. Một số Reactor overload subscribe trả `Disposable`.

**5.** Chỉ subscribe mà không request có bảo đảm nhận onNext không?

**Đáp án:** Không; publisher chỉ được phát onNext khi có demand, nhưng có thể onComplete/onError không cần demand.

**6.** Vì sao hai lần `mono.block()` có thể gửi hai outbound HTTP requests?

**Đáp án:** Mỗi block là subscription mới. Nếu nguồn cold như WebClient body Mono chưa cache/share, mỗi subscription có thể tạo một exchange mới.

**7.** `doOnSuccess(null)` có phải là Reactor phát onNext(null) không?

**Đáp án:** Không; hook dùng null để báo Mono complete empty. `onNext(null)` bị cấm.

**8.** Khi `Flux.take(3)` đủ ba item, upstream thường nhận gì?

**Đáp án:** Cancel upstream; downstream nhận completion, hai boundary có thể có `doFinally` signal type khác nhau.

**9.** `doFinally` xử lý những con đường kết thúc nào?

**Đáp án:** Complete, error và cancel. Cleanup có thể chạy sau khi terminal đã tới downstream; để quản lý resource hãy cân nhắc using/usingWhen.

**10.** Có nên `repository.save(...).subscribe()` trong controller rồi return `Mono.empty()`?

**Đáp án:** Không. Nó tạo fire-and-forget ngoài HTTP lifecycle, mất propagated error/cancel/trace. Trả publisher cho framework quản lý.

**11.** `retry(2)` có chỉ “tiếp tục” một Subscription thất bại?

**Đáp án:** Không; thường subscribe lại upstream tối đa hai lần nữa, có thể chạy lại side effects.

**12.** Một `Flux` có chắc cold và phát lại toàn bộ cho late subscriber?

**Đáp án:** Không. Hot/shared sources có thể không replay; cache/replay có policy riêng.

**13.** `subscribeOn(boundedElastic)` biến JDBC thành non-blocking driver không?

**Đáp án:** Không. Nó di chuyển blocking call sang worker pool, JDBC vẫn blocking.

**14.** Khi WebFlux handler trả Mono nhưng không tự subscribe, ai subscribe?

**Đáp án:** Spring WebFlux HTTP infrastructure, để quản lý viết response và cancellation.

**15.** Reactor Context có phải một global ThreadLocal không?

**Đáp án:** Không. Nó gắn với Subscriber chain và được truyền theo protocol/scheduling rules, khác biến thread-local thông thường.

## 26. Tài liệu tham khảo

- Project Reactor reference — Reactor Core, building and subscribing: https://projectreactor.io/docs/core/release/reference/
- Reactor — Simple ways to create a Flux/Mono and subscribe: https://projectreactor.io/docs/core/release/reference/coreFeatures/simple-ways-to-create-a-flux-or-mono-and-subscribe-to-it.html
- Reactor — Which operator do I need? `defer`, `fromCallable`, `just`: https://projectreactor.io/docs/core/release/reference/apdx-operatorChoice.html
- Reactor Core API — `Mono`, `doFirst`/`doFinally`/`doOnSuccess`: https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Mono.html
- Reactor Core API — `Flux`, `using`/`usingWhen` and lifecycle: https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Flux.html
- Reactor — Testing with `StepVerifier`: https://projectreactor.io/docs/core/release/reference/testing.html
- Reactor Test API — `StepVerifier.withVirtualTime`: https://projectreactor.io/docs/test/release/api/reactor/test/StepVerifier.html
- Reactor — Schedulers and threading: https://projectreactor.io/docs/core/release/reference/coreFeatures/schedulers.html
- Reactor — Adding a Context: https://projectreactor.io/docs/core/release/reference/advancedFeatures/context.html
- Spring Framework — WebFlux overview/non-blocking principles: https://docs.spring.io/spring-framework/reference/web/webflux.html
- Spring Framework — WebFlux annotated controllers: https://docs.spring.io/spring-framework/reference/web/webflux/controller.html
- Spring Framework — WebFlux return values: https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/return-types.html
- Spring Framework — WebTestClient: https://docs.spring.io/spring-framework/reference/testing/webtestclient.html
- Reactive Streams JVM specification and TCK: https://github.com/reactive-streams/reactive-streams-jvm
- Java 17 — Flow API and reactive streams: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Flow.html
