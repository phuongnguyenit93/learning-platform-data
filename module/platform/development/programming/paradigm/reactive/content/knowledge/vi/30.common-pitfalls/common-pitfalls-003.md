# Gọi block trên vòng lặp sự kiện hoặc trong chuỗi đang chạy

Trong ứng dụng Java reactive, `Mono` và `Flux` mô tả một quy trình xử lý bất đồng bộ. Các toán tử kết hợp công việc mà không cần giữ một thread để chờ kết quả. Gọi `block()` giữa quy trình đó làm mất lợi ích này: thread hiện tại phải dừng cho đến khi Publisher phát kết quả hoặc kết thúc.

Lỗi thường gặp là gọi `block()` trong controller WebFlux, trong `map` hoặc `flatMap`, trong callback của `subscribe`, hoặc trên scheduler dành cho công việc không chặn. Hậu quả có thể là event loop bị chiếm, throughput giảm, queue tăng, timeout dây chuyền và thậm chí deadlock khi công việc đang chờ cần chính thread hoặc scheduler bị chặn.

Bài học này chỉ ra các vị trí nguy hiểm, cách nối Publisher bằng `map`, `flatMap`, `zip` và `then`, cách cô lập API blocking cũ bằng `fromCallable` cùng `boundedElastic`, và trường hợp hiếm hoi có thể chấp nhận chờ đồng bộ ở ranh giới imperative.

## 1. block() thực sự làm gì?

Các phương thức như `Mono.block()`, `Mono.block(Duration)`, `Mono.blockOptional()`, `Flux.blockFirst()` và `Flux.blockLast()` đăng ký vào Publisher rồi chờ thread gọi nhận được kết quả hoặc tín hiệu kết thúc.

~~~java
Mono<User> userPublisher = userRepository.findById(userId);

// Thread gọi dừng tại đây cho đến khi Mono phát kết quả hoặc hoàn tất.
User user = userPublisher.block();
~~~

`block()` không biến nguồn thành API đồng bộ an toàn. Nó chỉ tạo một subscription và chờ kết quả trên thread hiện tại. Nếu Publisher cần một thread đang bị giữ để tiếp tục phát tín hiệu, việc chờ có thể làm hệ thống không tiến triển.

Cũng cần nhớ:

- Mỗi lần gọi `block()` tạo một subscription mới. Với Publisher cold, I/O hoặc side effect có thể chạy lại.
- Nếu `Mono` hoàn tất rỗng, `block()` trả về `null`; `blockOptional()` biểu diễn trường hợp này bằng `Optional.empty()`.
- Nếu Publisher phát lỗi, lỗi được ném về thread gọi.
- `block(Duration)` đặt giới hạn thời gian chờ, nhưng không biến thao tác thành non-blocking. Khi timeout, Reactor yêu cầu hủy subscription; việc dừng I/O thực tế còn phụ thuộc nguồn và driver.
- Với `Flux`, `blockFirst()` và `blockLast()` chờ phần tử tương ứng; chúng không phải cách tiêu thụ stream phù hợp trong một pipeline reactive.

Một lời gọi blocking ở ranh giới imperative có thể hữu ích trong một chương trình command-line hoặc adapter đồng bộ có kiểm soát. Trong request path reactive, nó thường là dấu hiệu thiết kế sai.

## 2. Vì sao event loop không được phép chờ?

WebFlux thường dùng một số lượng nhỏ event loop thread để xử lý nhiều kết nối. Event loop nhận sự kiện socket, điều phối đọc/ghi và tiếp tục các callback khi dữ liệu sẵn sàng. Mỗi thread phải quay lại xử lý các kết nối khác thay vì ngồi chờ một database query hoặc HTTP response.

~~~mermaid
flowchart TD
    A["Event loop nhận request"] --> B["Chạy handler reactive"]
    B --> C{"Có gọi block()?"}
    C -->|Không| D["Đăng ký I/O rồi trả thread về event loop"]
    D --> E["Event loop xử lý kết nối khác"]
    E --> F["I/O hoàn tất, callback tiếp tục pipeline"]
    C -->|Có| G["Thread bị giữ để chờ kết quả"]
    G --> H["Các kết nối khác phải chờ"]
    H --> I["Queue và latency tăng"]
~~~

Nếu một event loop bị chặn, những kết nối được gán cho loop đó cũng bị ảnh hưởng. Khi nhiều request cùng gọi `block()`, số thread sẵn có không tăng theo số request; hệ thống có thể giảm throughput dù CPU vẫn chưa đạt mức cao.

Một số thread Reactor được đánh dấu là non-blocking. Nếu gọi các blocking API của Reactor trên những thread này, Reactor có thể ném `IllegalStateException` để phát hiện lỗi. Việc không nhận exception không chứng minh lời gọi an toàn: thread vẫn có thể bị chặn trong một môi trường không có cơ chế phát hiện tương ứng.

## 3. Không gọi block() trong controller WebFlux

Ví dụ dưới đây chặn thread đang thực thi handler:

~~~java
@GetMapping("/users/{id}")
Mono<UserView> getUser(@PathVariable String id) {
    User user = userService.findById(id).block();
    return Mono.just(UserView.from(user));
}
~~~

Handler khai báo trả về `Mono`, nhưng nó đã chờ kết quả trước khi trả Publisher. Nếu handler chạy trên event loop, thread đó bị giữ trong suốt thời gian truy vấn.

Hãy trả về Publisher và để WebFlux subscribe:

~~~java
@GetMapping("/users/{id}")
Mono<UserView> getUser(@PathVariable String id) {
    return userService.findById(id)
        .map(UserView::from);
}
~~~

Nếu dữ liệu có thể không tồn tại, hãy định nghĩa rõ hợp đồng empty:

~~~java
@GetMapping("/users/{id}")
Mono<ResponseEntity<UserView>> getUser(@PathVariable String id) {
    return userService.findById(id)
        .map(UserView::from)
        .map(ResponseEntity::ok)
        .defaultIfEmpty(ResponseEntity.notFound().build());
}
~~~

Cách này cho phép server điều phối I/O và phản hồi theo tín hiệu của Publisher. Không cần tự gọi `subscribe()` hoặc `block()` trong controller.

## 4. Không gọi block() trong map hoặc flatMap

`map` dành cho phép biến đổi đồng bộ, nhanh trên giá trị hiện có. Nếu hàm bên trong cần gọi một Publisher khác, dùng `flatMap` để nối hai quy trình.

Ví dụ sai:

~~~java
Mono<OrderView> view = orderRepository.findById(orderId)
    .map(order -> {
        Stock stock = inventoryClient.check(order.sku()).block();
        return new OrderView(order, stock);
    });
~~~

Mapper đang giữ thread phát tín hiệu của `orderRepository` để đợi `inventoryClient`. Nếu mapper chạy trên event loop hoặc scheduler non-blocking, nó chặn nơi Reactor cần tiếp tục xử lý.

Cách đúng:

~~~java
Mono<OrderView> view = orderRepository.findById(orderId)
    .flatMap(order ->
        inventoryClient.check(order.sku())
            .map(stock -> new OrderView(order, stock))
    );
~~~

`flatMap` nhận Publisher con và ghép tín hiệu của Publisher đó vào pipeline cha. Thread không cần chờ đồng bộ; Reactor điều phối subscription và kết quả theo giao thức reactive.

Nếu bước tiếp theo chỉ biến đổi một giá trị đã có, giữ `map`. Nếu bước tiếp theo trả về `Mono` hoặc `Flux`, thường dùng `flatMap`, `concatMap` hoặc toán tử kết hợp phù hợp với thứ tự nghiệp vụ.

## 5. Kết hợp các nguồn độc lập bằng zip

Không cần gọi `block()` lần lượt để lấy hai kết quả độc lập rồi tạo object tổng hợp.

Ví dụ sai:

~~~java
User user = userRepository.findById(userId).block();
List<Order> orders = orderRepository.findByUserId(userId).collectList().block();

return Mono.just(new Dashboard(user, orders));
~~~

Cách viết này tạo hai subscription đồng bộ và giữ thread trong khi chờ từng nguồn.

Hãy kết hợp hai nguồn thành một Publisher:

~~~java
Mono<Dashboard> dashboard = Mono.zip(
    userRepository.findById(userId),
    orderRepository.findByUserId(userId).collectList(),
    Dashboard::new
);
~~~

`Mono.zip` đợi các nguồn phát giá trị rồi gọi hàm kết hợp. Các nguồn có thể tiến hành bất đồng bộ; pipeline không cần giữ thread gọi để chờ từng nguồn.

Nếu một nguồn có thể hoàn tất rỗng, hãy xác định ý nghĩa nghiệp vụ trước khi kết hợp. Có thể dùng `defaultIfEmpty` khi giá trị mặc định thực sự hợp lệ hoặc `switchIfEmpty` để phát lỗi miền. Đừng dùng `null` làm giá trị thay thế vì Reactive Streams không cho phép `onNext(null)`.

## 6. Khi chỉ cần chờ nhiều thao tác hoàn tất

Nếu các thao tác không cần trả về giá trị để ghép, hãy dùng `Mono.when` hoặc `Mono.whenDelayError` thay cho việc block từng thao tác:

~~~java
Mono<Void> saveAll(Order order, AuditRecord audit) {
    return Mono.when(
        orderRepository.save(order),
        auditRepository.save(audit)
    ).then();
}
~~~

`Mono.when` hoàn tất khi các nguồn hoàn tất và phát lỗi nếu một nguồn lỗi theo semantics của operator. Nếu cần giữ lại lỗi cho đến khi các nguồn khác kết thúc, xem xét `whenDelayError`.

Không dùng `Mono.zip` để ghép nhiều `Mono<Void>` rồi mong nhận được tuple: `Mono<Void>` thường hoàn tất rỗng, không phát giá trị để tạo tuple. Chọn operator theo hợp đồng dữ liệu cần nhận.

## 7. Cô lập API blocking cũ bằng fromCallable

Đôi khi ứng dụng phải gọi thư viện cũ chỉ có phương thức đồng bộ, chẳng hạn JDBC, SDK legacy hoặc file API blocking. Không thể biến phương thức đó thành non-blocking chỉ bằng cách đặt nó trong `Mono.just`.

Ví dụ sai:

~~~java
Mono<Customer> customer = Mono.just(
    legacyClient.loadCustomer(customerId)
);
~~~

Đối số của `Mono.just` được tính ngay khi xây dựng pipeline. Lời gọi blocking xảy ra trước khi subscription bắt đầu, trên thread gọi phương thức.

Dùng `Mono.fromCallable` và chuyển lời gọi sang `Schedulers.boundedElastic()`:

~~~java
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

Mono<Customer> customer = Mono.fromCallable(
        () -> legacyClient.loadCustomer(customerId)
    )
    .subscribeOn(Schedulers.boundedElastic());
~~~

`fromCallable` trì hoãn việc gọi phương thức cho đến subscription. `subscribeOn(boundedElastic())` đưa công việc blocking sang scheduler dành cho tác vụ có thể chờ lâu. Event loop được trả về để xử lý request khác.

Nếu API legacy trả về một giá trị có thể `null`, `fromCallable` biểu diễn `null` bằng completion rỗng. Hãy xử lý bằng `switchIfEmpty` hoặc `defaultIfEmpty` theo hợp đồng miền.

Đối với một lời gọi blocking duy nhất, đây là mẫu chuyển đổi thông dụng. Không bọc một chuỗi reactive rồi gọi `block()` trong `fromCallable` nếu có thể gọi trực tiếp API blocking gốc; hãy cô lập đúng thao tác blocking cần tích hợp.

## 8. Chọn scheduler đúng và hiểu giới hạn của nó

`subscribeOn` ảnh hưởng nơi subscription và nguồn bắt đầu thực thi. `publishOn` chuyển việc xử lý các operator phía sau sang scheduler được chỉ định. Cả hai đều không làm cho một API blocking trở thành non-blocking; chúng chỉ quyết định nơi công việc chạy.

| Loại công việc | Cách tổ chức thường dùng |
|---|---|
| I/O reactive không chặn, như R2DBC hoặc WebClient | Giữ pipeline reactive; thường không cần scheduler bổ sung chỉ để “chạy nền”. |
| API blocking không thể thay thế | `fromCallable(...).subscribeOn(Schedulers.boundedElastic())`. |
| Tính toán CPU-bound | `publishOn(Schedulers.parallel())` hoặc scheduler CPU chuyên biệt. |
| Điều phối event loop của server | Không gọi blocking API trên thread đó. |

Không chuyển một Publisher sang `Schedulers.parallel()` rồi gọi `block()` trong `map`. `parallel` dành cho công việc CPU-bound và các thread của nó được đánh dấu non-blocking; blocking API của Reactor có thể ném exception tại đó.

Cũng không nên xem `boundedElastic` là nơi đặt mọi thứ. Scheduler có giới hạn worker và queue. Nếu đẩy nhiều tác vụ blocking hơn capacity, các task sẽ chờ trong queue và latency tăng. Hãy đo và cấu hình giới hạn phù hợp với hệ thống legacy.

## 9. Deadlock khi chờ công việc cần cùng scheduler

Một trường hợp nguy hiểm là thread đang chạy một tác vụ lại block để đợi Publisher cần chính scheduler đó thực thi.

~~~mermaid
sequenceDiagram
    participant W as Worker duy nhất
    participant P as Pipeline ngoài
    participant I as Publisher bên trong

    W->>P: Chạy callback
    P->>I: Subscribe Publisher con
    P->>W: block() chờ kết quả
    Note over W: Worker bị giữ, không thể chạy tác vụ khác
    I--xW: Cần cùng worker để phát kết quả
    Note over P,I: Không có tiến triển cho đến khi timeout hoặc bị hủy
~~~

Ví dụ minh họa:

~~~java
Mono<String> result =
    Mono.just("start")
        .publishOn(Schedulers.single())
        .map(value ->
            Mono.delay(Duration.ofMillis(10), Schedulers.single())
                .map(tick -> value + "-done")
                .block()
        );
~~~

Callback `map` chạy trên scheduler single rồi chờ một Publisher có timer cần chính scheduler đó để phát tín hiệu. Thread single bị giữ bởi `block()`, nên timer không thể được xử lý cho đến khi thread được giải phóng. Trên các cấu hình có phát hiện blocking, Reactor có thể ném `IllegalStateException` trước khi tình huống treo kéo dài.

Nối Publisher con bằng `flatMap` để thread không phải đợi:

~~~java
Mono<String> result =
    Mono.just("start")
        .flatMap(value ->
            Mono.delay(Duration.ofMillis(10))
                .map(tick -> value + "-done")
        );
~~~

Ví dụ này cho thấy lý do cần giữ pipeline ở dạng composition: scheduler có thể xử lý tín hiệu khi tác vụ trước đó đã trả quyền điều khiển.

## 10. Không block trong callback subscribe hoặc doOnNext

Các callback của `subscribe`, `doOnNext`, `doOnSuccess` và `doOnEach` thường chạy trên thread đang phát tín hiệu. Gọi API blocking ở đó có thể chặn thread phát dữ liệu.

Ví dụ không nên làm:

~~~java
source.subscribe(value -> {
    AuditResult audit = auditClient.write(value).block();
    log.info("audit={}", audit);
});
~~~

Nếu audit là một bước bắt buộc trong workflow, hãy đưa nó vào pipeline:

~~~java
Mono<Result> result = source
    .flatMap(value ->
        auditClient.write(value)
            .thenReturn(Result.from(value))
    );
~~~

Nếu chỉ ghi log hoặc metrics, callback nên ngắn và không chờ I/O. Với side effect bất đồng bộ, hãy dùng operator composition để lỗi và cancellation vẫn thuộc cùng pipeline.

Cũng tránh gọi `subscribe()` lồng nhau trong phương thức nghiệp vụ để khởi chạy Publisher con rồi bỏ qua kết quả. Subscription tách rời khiến caller không thể điều phối lỗi, cancellation hoặc thời điểm hoàn tất của công việc con.

## 11. Dùng block chỉ tại ranh giới imperative có kiểm soát

Có những chương trình không có runtime reactive bên ngoài, chẳng hạn CLI, migration utility hoặc adapter phải trả về kiểu đồng bộ. Ở ranh giới đó, việc chờ kết quả có thể là một lựa chọn có chủ đích.

Nếu buộc phải chờ:

- Chỉ thực hiện trên thread dành cho caller imperative, không phải event loop hoặc scheduler non-blocking.
- Đặt timeout hữu hạn bằng `block(Duration)` để không chờ vô hạn.
- Xác định cách xử lý `Mono.empty()` và lỗi.
- Hiểu rằng mỗi lần gọi `block` tạo subscription mới.
- Không giữ lock hoặc transaction không cần thiết trong lúc chờ.
- Xác minh cancellation của nguồn khi timeout có thể dừng công việc thực tế hay không.

Ví dụ ở một adapter đồng bộ được gọi từ worker thread chuyên dụng:

~~~java
User loadUserForLegacyCaller(String userId) {
    return userService.findById(userId)
        .block(Duration.ofSeconds(2));
}
~~~

Đoạn này là ranh giới chuyển từ reactive sang imperative; caller phải bảo đảm phương thức không được gọi từ event loop hoặc thread non-blocking. Nếu API imperative có thể chấp nhận `CompletableFuture`, `Mono.toFuture()` thường giúp giữ bất đồng bộ xuyên qua ranh giới mà không cần chờ.

Không đặt `block()` vào controller WebFlux, repository reactive, service reactive hoặc callback của pipeline chỉ vì một tầng gọi muốn nhận giá trị trực tiếp. Hãy để tầng ngoài cùng chịu trách nhiệm chọn cách tiêu thụ.

## 12. Chuyển sang CompletableFuture mà không chờ đồng bộ

Nếu một API tích hợp yêu cầu `CompletableFuture`, có thể chuyển `Mono` bằng `toFuture()`:

~~~java
CompletableFuture<User> future =
    userService.findById(userId).toFuture();
~~~

`toFuture()` đăng ký vào Mono và trả về một future. Caller có thể nối tiếp bằng `thenApply`, `thenCompose` hoặc `thenCombine` mà không gọi `get()`:

~~~java
CompletableFuture<UserView> view =
    userService.findById(userId)
        .toFuture()
        .thenApply(UserView::from);
~~~

Nếu cần chuyển từ `CompletableFuture` vào Reactor, dùng `Mono.fromFuture`. Không gọi `join()` để lấy kết quả trước khi tạo Mono:

~~~java
Mono<User> user =
    Mono.fromFuture(() -> legacyClient.findUserAsync(userId));
~~~

Supplier trì hoãn việc tạo future đến lúc subscription. Cách này giữ pipeline lazy nếu client bắt đầu công việc ngay khi tạo future.

## 13. Kiểm thử mà không cần block trong pipeline

Dùng `StepVerifier` để xác minh giá trị, empty, lỗi và completion. `verifyComplete()` chờ terminal signal ở test harness; không cần gọi `block()` trong logic ứng dụng.

~~~java
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

@Test
void serviceKetHopPublisherCon() {
    Mono<String> result = Mono.just("order-1")
        .flatMap(orderId ->
            Mono.just(orderId + "-checked")
        );

    StepVerifier.create(result)
        .expectNext("order-1-checked")
        .verifyComplete();
}
~~~

Có thể kiểm tra rằng API blocking chỉ chạy khi có subscription và chạy trên scheduler dự kiến:

~~~java
import java.util.concurrent.atomic.AtomicReference;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Scheduler;
import reactor.core.scheduler.Schedulers;
import reactor.test.StepVerifier;
import static org.junit.jupiter.api.Assertions.assertTrue;

@Test
void blockingApiChayTrenSchedulerDuocCachLy() {
    AtomicReference<String> executingThread = new AtomicReference<>();
    Scheduler io = Schedulers.newBoundedElastic(2, 10, "blocking-test");

    try {
        Mono<String> legacy = Mono.fromCallable(() -> {
                executingThread.set(Thread.currentThread().getName());
                return "loaded";
            })
            .subscribeOn(io);

        StepVerifier.create(legacy)
            .expectNext("loaded")
            .verifyComplete();

        assertTrue(executingThread.get().startsWith("blocking-test"));
    } finally {
        io.dispose();
    }
}
~~~

Ví dụ tạo scheduler có tên riêng để kiểm tra điểm thực thi và dispose scheduler sau test. Trong ứng dụng, scheduler nên được quản lý ở vòng đời bean hoặc thành phần sở hữu thay vì tạo mới cho từng request.

## 14. Những lời gọi cần rà soát trong code review

| Dấu hiệu | Rủi ro | Hướng sửa |
|---|---|---|
| `block()` trong WebFlux controller | Chặn event loop | Trả về `Mono` hoặc `Flux`. |
| `block()` trong `map` | Chờ Publisher con trên thread phát tín hiệu | Dùng `flatMap`. |
| `block()` trong `doOnNext` hoặc `subscribe` | Chặn callback và tách side effect khỏi pipeline | Nối side effect bằng operator. |
| `Mono.just(blockingCall())` | Blocking xảy ra ngay khi dựng pipeline | Dùng `fromCallable` và `boundedElastic`. |
| `future.join()` hoặc `future.get()` trong handler | Chờ đồng bộ trên request thread | Dùng `Mono.fromFuture` hoặc giữ `CompletableFuture`. |
| `block()` trên `single` hoặc `parallel` | Có thể bị Reactor từ chối hoặc gây starvation | Tránh blocking; cô lập API blocking trên `boundedElastic`. |
| Gọi `block()` nhiều lần trên cùng cold Publisher | Tạo nhiều subscription và có thể lặp I/O | Kết hợp một lần bằng `zip` hoặc chia sẻ kết quả có chủ đích. |
| Dùng `block(Duration)` như cách chữa mọi vấn đề | Timeout không làm API trở thành non-blocking | Sửa composition và quản lý cancellation. |

Trong code review, tìm cả các biến thể blocking: `block`, `blockOptional`, `blockFirst`, `blockLast`, `toIterable`, `toStream`, `Future.get`, `CompletableFuture.join`, `CountDownLatch.await` và các API đồng bộ tương tự. Xem xét thread nơi chúng được gọi, không chỉ tên phương thức chứa chúng.

## 15. Checklist giữ pipeline không chặn

Trước khi chấp nhận một thay đổi reactive, hãy kiểm tra:

1. Controller và service reactive có trả về Publisher thay vì chờ kết quả không?
2. Mọi lời gọi trả về `Mono` hoặc `Flux` được kết hợp bằng operator phù hợp không?
3. `map` chỉ làm phép biến đổi đồng bộ, còn Publisher con được nối bằng `flatMap` hoặc operator tương ứng không?
4. API blocking cũ có được đặt trong `fromCallable` và chạy trên scheduler phù hợp không?
5. Không có `block`, `get`, `join` hoặc `await` trên event loop và scheduler non-blocking không?
6. Có tránh subscription lồng nhau và side effect detached không?
7. Empty, lỗi, timeout và cancellation có chính sách rõ ràng không?
8. Nếu bắt buộc có ranh giới imperative, nó có thread riêng và timeout hữu hạn không?
9. Test dùng `StepVerifier` để kiểm tra tín hiệu thay vì block trong code nghiệp vụ không?

Reactive Programming chỉ giữ được khả năng mở rộng khi thread không bị giữ để chờ những công việc vốn đã bất đồng bộ. Hãy kết hợp Publisher bằng `map`, `flatMap`, `zip` và `then`; cô lập API blocking bằng `fromCallable` cùng `boundedElastic`; và chỉ dùng `block` tại ranh giới imperative có kiểm soát. Việc rà soát đúng thread thực thi, vòng đời subscription và cancellation giúp tránh event loop starvation, scheduler starvation và deadlock trong ứng dụng Java reactive.

