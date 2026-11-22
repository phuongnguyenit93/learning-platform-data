# ReactiveAdapterRegistry và tích hợp thư viện reactive khác trong Spring WebFlux

## 1. Vì sao Spring WebFlux cần một lớp adapter?

Spring WebFlux xây dựng trên Reactive Streams và Project Reactor. API nội bộ thường dùng `Mono<T>` cho kết quả 0..1 và `Flux<T>` cho luồng 0..N. Nhưng ứng dụng Java/Kotlin có thể đã dùng các kiểu bất đồng bộ khác:

- `CompletableFuture<T>` hoặc `CompletionStage<T>` của JDK.
- `java.util.concurrent.Flow.Publisher<T>` của JDK Flow API.
- `Flowable<T>`, `Single<T>`, `Maybe<T>`, `Completable` hoặc `Observable<T>` của RxJava 3.
- `Deferred<T>` và coroutine của Kotlin.
- `Uni<T>` và `Multi<T>` của SmallRye Mutiny.
- Một kiểu reactive/async do ứng dụng hoặc thư viện nội bộ định nghĩa.

Nếu buộc mọi thư viện đổi toàn bộ public API sang Mono/Flux, quá trình tích hợp trở nên tốn kém. `org.springframework.core.ReactiveAdapterRegistry` giải quyết bài toán này bằng cách lưu một tập adapter có khả năng chuyển **từ một reactive type sang Reactive Streams Publisher và ngược lại**.

~~~text
          Library A                    Spring WebFlux
       CompletableFuture<T>                 |
       RxJava3 Flowable<T>                  |
       RxJava3 Single<T>                    |
       Kotlin Deferred<T>                   |
       Mutiny Uni<T>/Multi<T>               |
       Custom AsyncType<T>                  |
                |                           |
                v                           |
       ReactiveAdapterRegistry              |
                |                           |
         ReactiveAdapter                    |
             /       \                      |
      toPublisher  fromPublisher            |
             \       /                      |
                v                           v
        org.reactivestreams.Publisher<T>
                      |
               Mono<T> / Flux<T>
                      |
             HTTP body / controller
~~~

Registry là một **cơ chế chuyển đổi kiểu** và metadata về ngữ nghĩa luồng, không phải runtime thay thế Reactor, scheduler mới, thread pool hay message broker.

## 2. Các thành phần quan trọng

| Thành phần | Trách nhiệm |
| --- | --- |
| `ReactiveAdapterRegistry` | Lưu, tìm và đăng ký adapter cho reactive/async type |
| `ReactiveAdapter` | Chuyển instance sang `Publisher` hoặc từ `Publisher` |
| `ReactiveTypeDescriptor` | Mô tả cardinality, empty completion và tính deferred của kiểu |
| `org.reactivestreams.Publisher<T>` | Giao diện Reactive Streams chuẩn được Spring dùng làm cầu nối |
| `Mono<T>` | Publisher Reactor với tối đa một phần tử |
| `Flux<T>` | Publisher Reactor với không hoặc nhiều phần tử |

Các API chính của registry:

~~~java
ReactiveAdapterRegistry registry = new ReactiveAdapterRegistry();

ReactiveAdapter adapter =
        registry.getAdapter(CompletableFuture.class);

ReactiveAdapter sharedAdapter =
        ReactiveAdapterRegistry.getSharedInstance()
                .getAdapter(CompletableFuture.class);
~~~

`new ReactiveAdapterRegistry()` tạo registry mới và tự đăng ký adapter mặc định tùy classpath. `getSharedInstance()` trả một registry mặc định dùng chung, được tạo lười. Theo JavaDoc, ứng dụng cần tùy biến nên truyền một registry đã cấu hình, có vòng đời dài, thay vì chỉnh sửa registry shared một cách tùy tiện.

## 3. Reactive Streams Publisher là giao diện trung gian

`org.reactivestreams.Publisher<T>` là hợp đồng giữa publisher và subscriber. Nó không đồng nghĩa với Reactor `Flux<T>`, dù Mono và Flux đều thực thi Publisher.

Một nguồn Publisher phát các tín hiệu:

~~~text
subscribe
   |
   v
onSubscribe(Subscription)
   |
   +-- request(n) --> onNext(value) ... (tối đa theo demand)
   |
   +-- onComplete()
   |
   +-- onError(error)
   |
   +-- cancel()
~~~

Reactive Streams đặt các quy tắc về backpressure, serialization của signal, terminal signal và cancellation. Khi adapter biến nguồn khác thành Publisher, nó phải duy trì hành vi phù hợp với hợp đồng này.

Ví dụ bridge từ một Publisher của thư viện khác về Reactor:

~~~java
Publisher<String> source = obtainPublisher();

Flux<String> flux = Flux.from(source);
Mono<String> first = Mono.from(source);
~~~

**Không xem hai cách trên là tương đương.** `Flux.from(source)` biểu diễn 0..N, còn `Mono.from(source)` lấy tối đa phần tử đầu và hủy upstream khi phù hợp. Nếu source chứa nhiều phần tử mà nghiệp vụ cần tất cả, dùng Mono sẽ làm mất các phần tử còn lại.

Trong functional endpoints và WebClient, Spring thường chấp nhận Publisher đầu vào, nhưng nếu chỉ truyền Publisher thuần, framework có thể chưa biết rõ cardinality. Khi đã biết kiểu là một kết quả hay nhiều kết quả, hãy wrap bằng `Mono` hoặc `Flux` để thể hiện ý định.

## 4. Metadata về cardinality: 0..1, 1, 0..N và không có giá trị

`ReactiveTypeDescriptor` mô tả kiểu reactive có thể phát bao nhiêu phần tử.

| Factory của descriptor | Ngữ nghĩa | Ví dụ khái niệm |
| --- | --- | --- |
| `multiValue(type, emptySupplier)` | 0..N | Flux, RxJava Flowable, Mutiny Multi |
| `singleOptionalValue(type, emptySupplier)` | 0..1 | Mono, RxJava Maybe, Mutiny Uni tùy implementation |
| `singleRequiredValue(type)` | Phải phát một giá trị để hoàn tất thành công | RxJava Single |
| `noValue(type, emptySupplier)` | 0 giá trị, chỉ báo complete/error | RxJava Completable |
| `nonDeferredAsyncValue(type, emptySupplier)` | Single optional nhưng việc tính toán có thể đã chạy trước lúc subscribe | CompletableFuture |

Đặc điểm cần nhớ:

- `isMultiValue()`: nguồn có thể phát nhiều giá trị.
- `isNoValue()`: nguồn chỉ báo hoàn tất, không mang giá trị dữ liệu.
- `supportsEmpty()`: kiểu chấp nhận hoàn tất không có giá trị.
- `isDeferred()` trên descriptor: ý nghĩa deferred subscription/lazy evaluation theo mô tả kiểu.

Ví dụ một controller trả một đối tượng không giống trả một danh sách. Spring dùng cardinality để chọn cách xử lý và ghi HTTP response. Một stream nhiều phần tử có thể được serialize thành JSON array nếu media type không phải streaming, trong khi NDJSON/SSE cho phép ghi từng phần tử.

**Không chọn descriptor theo “muốn trả một kết quả” nếu kiểu thực tế có thể phát nhiều giá trị.** Sai cardinality có thể làm mất dữ liệu, buffer không cần thiết hoặc hoàn tất response khác với dự kiến.

## 5. Những adapter mặc định được đăng ký khi thư viện có mặt

Trong Spring Framework 7.0.x, `ReactiveAdapterRegistry` kiểm tra classpath khi khởi tạo. Nó có hỗ trợ mặc định cho:

| Nền tảng | Các kiểu đáng chú ý | Điều kiện |
| --- | --- | --- |
| Reactor | `Mono`, `Flux` | reactor-core có trên classpath |
| JDK asynchronous | `CompletableFuture`, Java `Flow.Publisher` | Cầu nối tương ứng được đăng ký khi thư viện hỗ trợ có mặt |
| RxJava 3 | `Flowable`, `Observable`, `Single`, `Maybe`, `Completable` | RxJava 3 có trên classpath |
| Kotlin Coroutines | `Deferred` | Có Reactor và thư viện bridge coroutine-Reactor tương ứng |
| SmallRye Mutiny | `Uni`, `Multi` | Phiên bản Mutiny được Spring nhận diện có trên classpath |

Theo mô tả của Spring Framework 7.0.10, hỗ trợ Mutiny trong registry gắn với 1.x/2.x. Khi ứng dụng dùng major version khác, cần kiểm tra compatibility thật thay vì mặc nhiên cho rằng adapter sẽ được đăng ký.

Hỗ trợ Java `Flow.Publisher` khác giao diện `org.reactivestreams.Publisher`: đây là **hai interface riêng**, dù cấu trúc protocol rất gần nhau. Reactor cung cấp cầu nối JDK Flow tương ứng.

### 5.1. Classpath quyết định adapter có xuất hiện hay không

~~~java
ReactiveAdapterRegistry registry = new ReactiveAdapterRegistry();

ReactiveAdapter rxAdapter =
        registry.getAdapter(
                io.reactivex.rxjava3.core.Flowable.class);
~~~

Đoạn trên chỉ compile nếu project có RxJava 3. Khi RxJava 3 có trên runtime classpath, registry có thể tự nhận diện và đăng ký adapter. Nếu thư viện không có, không nên hard-code assumption rằng mọi type đều được nhận diện.

Một cách an toàn là:

~~~java
ReactiveAdapter adapter = registry.getAdapter(type);

if (adapter == null) {
    throw new IllegalArgumentException(
            "No reactive adapter for " + type.getName());
}
~~~

`getAdapter(...)` có thể trả `null`. Không gọi `toPublisher` trên adapter null.

### 5.2. RxJava 1/2 khác RxJava 3

Tài liệu Spring cũ từng mô tả adapter cho RxJava 1 hoặc RxJava 2. Những ví dụ đó không nên được sao chép như API hỗ trợ mặc định trong Spring 7.0.x. Khi chọn tích hợp RxJava, ưu tiên RxJava 3 và xác nhận package `io.reactivex.rxjava3.core`.

## 6. ReactiveAdapter: chuyển đổi hai chiều

Sau khi lấy được `ReactiveAdapter`:

~~~java
ReactiveAdapter adapter = registry.getAdapter(SomeType.class);
~~~

Có hai hướng:

### 6.1. toPublisher: từ type bên ngoài sang Reactive Streams

~~~java
Publisher<String> publisher =
        adapter.toPublisher(externalAsyncValue);

Flux<String> flux = Flux.from(publisher);
~~~

Adapter nhận một instance của reactive/async type và tạo Publisher tương ứng. Đây là hướng phổ biến khi bạn nhận dữ liệu từ SDK khác rồi đưa vào Reactor pipeline.

### 6.2. fromPublisher: từ Publisher sang type của thư viện

~~~java
Object externalValue =
        adapter.fromPublisher(Flux.just("alpha", "beta"));
~~~

Adapter tạo một instance của kiểu bên ngoài. Trả về `Object` vì registry xử lý nhiều type khác nhau. Caller phải biết adapter gắn với kiểu gì và cast có kiểm soát.

### 6.3. Đừng tự chế cú pháp chuyển đổi nếu thư viện đã có bridge

Khi chỉ cần làm việc với Reactor, đôi khi API trực tiếp rõ ràng hơn:

~~~java
Mono<String> mono = Mono.fromFuture(
        CompletableFuture.completedFuture("ready"));

Flowable<String> flowable =
        Flowable.fromPublisher(Flux.just("a", "b"));
~~~

`Mono.fromFuture` và `Flowable.fromPublisher` là bridge chuyên biệt. `ReactiveAdapterRegistry` hữu ích khi framework cần xử lý nhiều type một cách động, ví dụ nhận Class hoặc Object từ thư viện/extension.

## 7. CompletableFuture và CompletionStage

`CompletableFuture<T>` là kiểu bất đồng bộ của JDK. Spring có adapter khi Reactor có mặt.

~~~java
CompletableFuture<String> future =
        CompletableFuture.completedFuture("ready");

ReactiveAdapter adapter =
        registry.getAdapter(CompletableFuture.class);

Publisher<String> publisher =
        adapter.toPublisher(future);

String text = Mono.from(publisher).block();
~~~

Kết quả là `ready`.

### 7.1. Future không đồng nghĩa với Publisher lazy

Một CompletableFuture có thể đang chạy trước khi được chuyển thành Publisher:

~~~java
CompletableFuture<String> future =
        CompletableFuture.supplyAsync(this::loadData);
~~~

Phần code bên trong `supplyAsync` đã được lịch chạy độc lập với downstream subscription. Đổi future sang Mono không làm công việc tự nhiên trở thành lazy hay non-blocking.

Nếu muốn trì hoãn khởi tạo future cho tới lúc subscribe:

~~~java
Mono<String> lazy = Mono.defer(() ->
        Mono.fromFuture(
                CompletableFuture.supplyAsync(this::loadData)));
~~~

Đây là ví dụ minh họa, giả định có `loadData()`. Trong production, nên cung cấp Executor rõ ràng và bounded concurrency thay vì dựa vào Common ForkJoinPool cho mọi tác vụ.

### 7.2. Empty/null và exception

Reactive Streams không cho phép `onNext(null)`. Nếu CompletableFuture hoàn tất với null, bridge thường biểu diễn kết quả là empty completion thay vì phát null.

Nếu future hoàn tất exceptionally, Publisher phát onError. Nguyên nhân thực tế có thể được bọc bởi `CompletionException` hoặc lớp exception trung gian; giữ cause khi mapping sang domain error.

### 7.3. Cancellation

Cancellation của một Publisher không nhất thiết hủy được công việc đang chạy trong SDK khác. Một future có thể hỗ trợ cancel, nhưng operation I/O phía sau có thể vẫn tiếp tục. Cần test cancellation propagation khi ứng dụng dùng future để gọi HTTP, database hoặc tác vụ tốn tài nguyên.

Đừng cho rằng việc chuyển sang Mono sẽ tự đem lại backpressure nhiều phần tử: một future chỉ là một kết quả.

## 8. RxJava 3: Flowable, Single, Maybe, Completable và Observable

RxJava 3 có nhiều kiểu với các semantics khác nhau.

| Kiểu RxJava 3 | Số giá trị | Backpressure | Bridge Reactor thường dùng |
| --- | --- | --- | --- |
| `Flowable<T>` | 0..N | Có | `Flux.from(flowable)` |
| `Single<T>` | Đúng một giá trị hoặc lỗi | Không phải multi-item demand | `Mono.from(single.toFlowable())` |
| `Maybe<T>` | 0..1 | Không phải multi-item demand | `Mono.from(maybe.toFlowable())` |
| `Completable` | Không có giá trị | Completion/error | `Mono.from(completable.toFlowable())` |
| `Observable<T>` | 0..N | Không có Reactive Streams backpressure trực tiếp | Cần chiến lược chuyển sang Flowable |

Khi dùng `ReactiveAdapterRegistry`, Spring cung cấp các chuyển đổi mặc định tương ứng nếu thư viện có trên classpath.

### 8.1. Flowable: giao diện Reactive Streams tương thích

~~~java
Flowable<String> rx = Flowable.just("a", "b");

Flux<String> flux = Flux.from(rx);

List<String> values = flux.collectList().block();
~~~

`Flowable` thực thi Reactive Streams Publisher nên có thể đưa trực tiếp vào `Flux.from`. Với tập nhỏ và luồng hữu hạn, kết quả là `[a, b]`.

Nếu cần trả từ annotated controller Spring WebFlux, có thể khai báo `Flowable<Dto>` trực tiếp; registry hỗ trợ nhận diện đó là multi-value reactive type.

### 8.2. Single và Maybe

~~~java
Single<String> single = Single.just("ready");
Maybe<String> maybe = Maybe.empty();

Mono<String> one = Mono.from(single.toFlowable());
Mono<String> optional = Mono.from(maybe.toFlowable());
~~~

Single không có empty completion thành công; Maybe có thể empty. Điều này quan trọng khi route biểu diễn “không tìm thấy bản ghi” hoặc một trường tùy chọn.

### 8.3. Completable không phát dữ liệu

~~~java
Completable done = Completable.complete();

Mono<Void> completion =
        Mono.from(done.toFlowable()).then();
~~~

`Mono<Void>` phù hợp để mô tả tác vụ không có response body. Đừng cố map Completable thành DTO vì nó không phát value.

### 8.4. Observable thiếu backpressure

`Observable<T>` của RxJava 3 không thực thi Reactive Streams demand theo cách Flowable thực thi. Khi chuyển Observable sang Flowable phải chọn `BackpressureStrategy`.

Ví dụ:

~~~java
Flowable<String> bridge =
        Observable.just("a", "b")
                .toFlowable(BackpressureStrategy.BUFFER);
~~~

Theo source Spring Framework 7.0.10, adapter mặc định cho Observable dùng `BackpressureStrategy.BUFFER` để tạo Flowable. Với nguồn tốc độ cao hoặc vô hạn, buffer có thể tăng mạnh nếu downstream xử lý chậm.

Nếu cần điều tiết tải, ưu tiên Flowable hoặc chuyển đổi với backpressure strategy có chủ đích, giới hạn queue và đo overflow. Adapter không thể tạo ra năng lực backpressure thực sự ở một upstream không hỗ trợ nó.

## 9. Kotlin coroutines: Deferred và Flow

Kotlin có hai nhóm API cần phân biệt:

- `Deferred<T>`: một kết quả bất đồng bộ, gần với single-value.
- `kotlinx.coroutines.flow.Flow<T>`: một luồng nhiều giá trị dựa trên coroutine/suspension.

Spring WebFlux hỗ trợ controller Kotlin với `suspend fun` và các kiểu Flow thông qua tích hợp coroutine. Một số bridge cụ thể sử dụng `kotlinx-coroutines-reactor` và `kotlinx-coroutines-reactive`.

Registry Spring 7.0.x mô tả adapter được đăng ký theo classpath cho Kotlin `Deferred` thông qua Reactor bridge. **Không mặc định xem mọi Kotlin Flow đều được đăng ký trong ReactiveAdapterRegistry chỉ vì Spring hỗ trợ Kotlin Flow ở tầng controller.** Hỗ trợ Kotlin Flow có thể đi qua các cơ chế Kotlin/coroutine riêng ngoài adapter registry.

Ví dụ minh họa Kotlin controller:

~~~kotlin
@RestController
@RequestMapping("/api/kotlin")
class KotlinController {

    @GetMapping("/one")
    suspend fun one(): Greeting =
        Greeting("hello")

    @GetMapping("/events", produces = ["text/event-stream"])
    fun events(): Flow<Greeting> =
        flow {
            emit(Greeting("a"))
            emit(Greeting("b"))
        }
}
~~~

Đây là ví dụ minh họa Kotlin, cần Kotlin plugin, spring-webflux, kotlinx-coroutines-reactor và các dependency phù hợp; nó không nằm trong chương trình Java độc lập ở phần sau.

Khi chuyển giữa Reactor và Kotlin coroutines, cần quan tâm cancellation, context propagation và dispatcher. Không dùng `runBlocking` bên trong WebFlux handler để “đợi” coroutine vì có thể chặn event-loop.

## 10. SmallRye Mutiny: Uni và Multi

SmallRye Mutiny cung cấp:

- `Uni<T>`: một kết quả bất đồng bộ hoặc lỗi.
- `Multi<T>`: stream nhiều phần tử.

Spring Framework 7.0.x có registrar cho Mutiny khi thư viện được nhận diện trên classpath. Tuy nhiên, phạm vi major version được JavaDoc mô tả là Mutiny 1.x/2.x; cần kiểm tra riêng khi dùng Mutiny 3.x hoặc phiên bản mới hơn.

Ví dụ minh họa concept:

~~~java
// Ví dụ minh họa cần dependency SmallRye Mutiny tương thích.
Uni<String> uni = Uni.createFrom().item("ready");
Multi<String> multi =
        Multi.createFrom().items("a", "b");
~~~

`ReactiveAdapterRegistry` có thể chuyển chúng sang Publisher nếu adapter được đăng ký. Không cần wrap toàn bộ business service bằng Reactor trừ khi những operator của Reactor thực sự có giá trị trong boundary của ứng dụng.

Không dùng `Uni.await().indefinitely()` trong event-loop WebFlux. Blocking wait làm mất lợi ích reactive và có thể làm request khác bị chậm.

## 11. Annotated controller và functional API khác nhau

Tài liệu Spring WebFlux nhấn mạnh hai nhóm API.

### 11.1. Annotated controllers

Với `@RestController` và `@RequestMapping`, WebFlux có thể nhận biết reactive return type nhờ `ReactiveAdapterRegistry`:

~~~java
@RestController
@RequestMapping("/api/examples")
class ExampleController {

    @GetMapping("/future")
    CompletableFuture<String> future() {
        return CompletableFuture.completedFuture("ready");
    }

    @GetMapping("/rx")
    Flowable<String> rx() {
        return Flowable.just("alpha", "beta");
    }
}
~~~

Đây là snippet minh họa, cần có RxJava 3 trên classpath. Spring nhận biết CompletableFuture là single async value và Flowable là multi-value Publisher.

Khi response media type là JSON thường, một multi-value source có thể được serialize thành JSON array. Với `text/event-stream` hoặc `application/x-ndjson`, các giá trị có thể được phát/flush theo stream. Không dùng kiểu multi-value tùy tiện cho response mong đợi một DTO đơn lẻ.

### 11.2. Functional endpoints và WebClient

Các API functional chủ yếu dùng `Mono`/`Flux` để biểu thị kết quả và nhận `Publisher` cho input.

~~~java
HandlerFunction<ServerResponse> handler = request -> {
    Publisher<String> source = obtainPublisher();

    return ServerResponse.ok()
            .body(Flux.from(source), String.class);
};
~~~

Đây là đoạn minh họa, giả định `obtainPublisher()`. Khi nguồn có ngữ nghĩa single-value, dùng `Mono.from(source)`; khi có nhiều giá trị, dùng `Flux.from(source)`.

### 11.3. Vì sao cardinality ảnh hưởng HTTP encoding?

Một kết quả single-value thường tương ứng một JSON object:

~~~json
{"id":42,"name":"WebFlux"}
~~~

Một nguồn multi-value dưới `application/json` có thể trở thành một JSON array:

~~~json
[
  {"id":42,"name":"WebFlux"},
  {"id":43,"name":"Reactor"}
]
~~~

Với streaming media type, từng item có thể được gửi ngay khi sẵn sàng. Nếu một thư viện báo sai số lượng item (ví dụ thực tế 0..N nhưng descriptor báo single), kết quả HTTP có thể khác contract.

## 12. Đăng ký adapter cho kiểu tùy chỉnh

Giả sử ứng dụng có kiểu `Batch<T>` bao quanh Publisher nhưng không trực tiếp triển khai `Publisher`. Registry sẽ không tự hiểu `Batch` nếu chưa đăng ký.

Một adapter cần ba thành phần:

1. `ReactiveTypeDescriptor` mô tả cardinality và empty instance.
2. `toAdapter`: chuyển kiểu tùy chỉnh thành `Publisher<?>`.
3. `fromAdapter`: chuyển `Publisher<?>` thành kiểu tùy chỉnh.

~~~java
registry.registerReactiveType(
        ReactiveTypeDescriptor.multiValue(
                Batch.class,
                () -> new Batch(Flux.empty())),
        source -> ((Batch) source).publisher(),
        publisher -> new Batch(publisher));
~~~

Bản thân `Batch` có thể định nghĩa:

~~~java
record Batch(Publisher<?> publisher) {
}
~~~

Sau đăng ký:

~~~java
ReactiveAdapter adapter =
        registry.getAdapter(Batch.class);

Publisher<?> publisher =
        adapter.toPublisher(
                new Batch(Flux.just("a", "b")));

Batch restored =
        (Batch) adapter.fromPublisher(
                Flux.just(1, 2));
~~~

Đây là hai hàm bridge không chứa blocking hoặc subscription side effect. Publisher được subscribe bởi downstream theo nhu cầu.

### 12.1. registerReactiveType và registerReactiveTypeOverride

Có hai API:

- `registerReactiveType(...)`: đăng ký adapter sau các adapter đã có; phù hợp với type mới.
- `registerReactiveTypeOverride(...)`: đặt adapter ở đầu để có thể override adapter có sẵn.

Registry tìm exact match trước khi xét assignability. Đối với override phức tạp liên quan interface/base class và subtype, cần test cụ thể: đăng ký một interface chung không nhất thiết override exact match đã có cho từng subtype.

Hạn chế override adapter mặc định của Spring trừ khi có lý do thật sự rõ ràng. Thay đổi cardinality hoặc lifecycle của một type phổ biến có thể ảnh hưởng controller argument/return handling và các thành phần khác.

### 12.2. Đừng biến registry tùy chỉnh thành global side effect

~~~java
ReactiveAdapterRegistry registry = new ReactiveAdapterRegistry();
registry.registerReactiveType(...);
~~~

Đăng ký trên instance mới chỉ ảnh hưởng instance đó. Nó **không tự động** thay mọi registry mà Spring WebFlux đã cấu hình trong ứng dụng.

Nếu cần controller tự nhận biết custom type, phải bảo đảm registry tùy chỉnh được đưa vào đúng các thành phần xử lý handler arguments/return values và response body. Spring có API `RequestMappingHandlerAdapter.setReactiveAdapterRegistry(...)`, nhưng return-value/result handling cũng cần cùng semantics.

Trong nhiều dự án, cách ít rủi ro hơn là chuyển custom type sang Mono/Flux tại controller boundary. Chỉ tùy biến registry khi nhiều component/framework extension thật sự cần type đó được hiểu một cách xuyên suốt.

## 13. Chương trình Java 17+ chạy được: adapter mặc định và adapter tùy chỉnh

Ví dụ độc lập không cần khởi động server, chỉ cần JDK 17+, Maven và dependencies Spring/Reactor/RxJava3. Chương trình chứng minh:

1. Registry tự nhận adapter cho CompletableFuture.
2. Registry tự nhận adapter cho RxJava 3 Flowable khi RxJava có trên classpath.
3. App đăng ký adapter mới cho Batch.
4. Chuyển hai chiều custom type và Publisher.
5. Kết quả được kiểm tra bằng assertion trước khi in stdout.

Phiên bản được chọn: Spring Boot **4.1.2** (stable tháng 10/2026) với Spring Framework **7.0.10** theo BOM, và RxJava **3.1.12**.

### 13.1. Cấu trúc dự án

~~~text
reactive-adapter-demo/
  pom.xml
  src/main/java/example/adapter/RegistryDemo.java
~~~

### 13.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>example</groupId>
    <artifactId>reactive-adapter-demo</artifactId>
    <version>1.0.0</version>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>4.1.2</version>
        <relativePath/>
    </parent>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
        </dependency>

        <dependency>
            <groupId>io.reactivex.rxjava3</groupId>
            <artifactId>rxjava</artifactId>
            <version>3.1.12</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.3.0</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 13.3. RegistryDemo.java

~~~java
package example.adapter;

import java.time.Duration;
import java.util.List;
import java.util.Objects;
import java.util.concurrent.CompletableFuture;

import io.reactivex.rxjava3.core.Flowable;
import org.reactivestreams.Publisher;
import org.springframework.core.ReactiveAdapter;
import org.springframework.core.ReactiveAdapterRegistry;
import org.springframework.core.ReactiveTypeDescriptor;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public final class RegistryDemo {

    record Batch(Publisher<?> publisher) {
    }

    private static ReactiveAdapter required(
            ReactiveAdapterRegistry registry, Class<?> type) {

        return Objects.requireNonNull(
                registry.getAdapter(type),
                "Missing adapter for " + type.getName());
    }

    public static void main(String[] args) {
        ReactiveAdapterRegistry registry =
                new ReactiveAdapterRegistry();

        // 1) CompletableFuture -> Publisher -> Mono.
        ReactiveAdapter futureAdapter =
                required(registry, CompletableFuture.class);

        String futureValue = Mono.from(
                        futureAdapter.<String>toPublisher(
                                CompletableFuture.completedFuture("ready")))
                .block(Duration.ofSeconds(5));

        if (!"ready".equals(futureValue)) {
            throw new AssertionError("Wrong future value");
        }

        // 2) RxJava3 Flowable -> Publisher -> Flux.
        ReactiveAdapter rxAdapter =
                required(registry, Flowable.class);

        List<Integer> rxValues = Flux.from(
                        rxAdapter.<Integer>toPublisher(
                                Flowable.just(1, 2, 3)))
                .collectList()
                .block(Duration.ofSeconds(5));

        if (!List.of(1, 2, 3).equals(rxValues)) {
            throw new AssertionError("Wrong RxJava values");
        }

        // 3) Register a custom 0..N type.
        registry.registerReactiveType(
                ReactiveTypeDescriptor.multiValue(
                        Batch.class,
                        () -> new Batch(Flux.empty())),
                source -> ((Batch) source).publisher(),
                publisher -> new Batch(publisher));

        ReactiveAdapter batchAdapter =
                required(registry, Batch.class);

        // 4) Custom type -> Publisher.
        List<?> fromCustom = Flux.from(
                        batchAdapter.toPublisher(
                                new Batch(Flux.just("a", "b"))))
                .collectList()
                .block(Duration.ofSeconds(5));

        if (!List.of("a", "b").equals(fromCustom)) {
            throw new AssertionError("Wrong custom values");
        }

        // 5) Publisher -> custom type.
        Batch restored = (Batch) batchAdapter.fromPublisher(
                Flux.just(7, 9));

        List<?> toCustom = Flux.from(restored.publisher())
                .collectList()
                .block(Duration.ofSeconds(5));

        if (!List.of(7, 9).equals(toCustom)) {
            throw new AssertionError("Wrong round-trip");
        }

        System.out.println("future=" + futureValue);
        System.out.println("rxjava=" + rxValues);
        System.out.println("custom-toPublisher=" + fromCustom);
        System.out.println("custom-fromPublisher=" + toCustom);
    }
}
~~~

### 13.4. Chạy chương trình

Từ thư mục có `pom.xml`:

~~~bash
mvn -q clean compile exec:java -Dexec.mainClass=example.adapter.RegistryDemo
~~~

**Stdout dự kiến chính xác:**

~~~text
future=ready
rxjava=[1, 2, 3]
custom-toPublisher=[a, b]
custom-fromPublisher=[7, 9]
~~~

Giải thích:

- `CompletableFuture.completedFuture` có một giá trị nên Mono phát `ready`.
- `Flowable.just(1,2,3)` có ba giá trị nên Flux phát đủ danh sách.
- Batch không implements Publisher nhưng registry đã biết hai hàm bridge.
- `fromPublisher` tạo Batch giữ nguồn Publisher mới; khi downstream subscribe qua Flux.from, nó phát 7 và 9.
- Không cần tự gọi subscribe; `block` chỉ được dùng ở boundary của chương trình command-line độc lập.

Đây là ví dụ Java standalone minh họa và có assertion. Trong WebFlux controller/service reactive, không dùng `block()`; hãy trả Mono/Flux để framework quản lý subscription.

## 14. Ví dụ Spring Boot controller trả RxJava 3 trực tiếp

Nếu muốn quan sát Spring dùng adapter trong annotated controller, có thể tạo một app WebFlux tối thiểu.

### 14.1. Application class

~~~java
package example.adapter;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class AdapterWebApplication {

    public static void main(String[] args) {
        SpringApplication.run(
                AdapterWebApplication.class, args);
    }
}
~~~

### 14.2. Controller class

~~~java
package example.adapter;

import java.util.concurrent.CompletableFuture;

import io.reactivex.rxjava3.core.Flowable;
import io.reactivex.rxjava3.core.Single;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/reactive")
public class ReactiveController {

    public record Item(String source, int value) {
    }

    @GetMapping("/future")
    public CompletableFuture<Item> future() {
        return CompletableFuture.completedFuture(
                new Item("future", 1));
    }

    @GetMapping("/single")
    public Single<Item> single() {
        return Single.just(new Item("rx-single", 2));
    }

    @GetMapping("/flowable")
    public Flowable<Item> flowable() {
        return Flowable.just(
                new Item("rx-flowable", 3),
                new Item("rx-flowable", 4));
    }
}
~~~

Đây là một app bổ sung sử dụng cùng `pom.xml` của mục 13. Đặt hai class vào đúng đường dẫn:

~~~text
src/main/java/example/adapter/AdapterWebApplication.java
src/main/java/example/adapter/ReactiveController.java
~~~

Chạy app bằng:

~~~bash
mvn spring-boot:run -Dspring-boot.run.main-class=example.adapter.AdapterWebApplication
~~~

Gọi:

~~~bash
curl -s http://localhost:8080/api/reactive/future
curl -s http://localhost:8080/api/reactive/single
curl -s http://localhost:8080/api/reactive/flowable
~~~

Response JSON dự kiến:

~~~json
{"source":"future","value":1}
~~~

~~~json
{"source":"rx-single","value":2}
~~~

~~~json
[
  {"source":"rx-flowable","value":3},
  {"source":"rx-flowable","value":4}
]
~~~

Whitespaces của JSON có thể khác do serializer; điều quan trọng là cấu trúc single object và array. Với `Flowable` có nhiều phần tử, Spring nhận biết multi-value return type thông qua registry.

Cần thêm `spring-boot-maven-plugin` vào phần build của `pom.xml` nếu dự án Maven không có plugin này trong cấu hình kế thừa:

~~~xml
<plugin>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-maven-plugin</artifactId>
</plugin>
~~~

Trong ứng dụng thật, tách controller/service, dùng dependency injection và thêm validation, security, error handling phù hợp.

## 15. Backpressure, cancellation và lifecycle khi đổi thư viện

Chuyển kiểu không đồng nghĩa mọi đặc tính vận hành được bảo toàn một cách tuyệt đối.

### 15.1. Backpressure

`Flowable` và `Flux` tuân theo Reactive Streams request(n), nên demand có thể được truyền qua bridge.

Nhưng `Observable` có thể phát nhanh mà không quan tâm downstream demand. Nếu Spring chuyển Observable bằng buffer, queue tăng nếu consumer chậm. Cần cân nhắc:

- Dùng Flowable khi có thể.
- Giới hạn nguồn phát, size và queue.
- Chọn backpressure policy theo nghiệp vụ.
- Theo dõi overflow, dropped events và memory pressure.
- Tránh chuyển stream vô hạn thành `collectList()`.

### 15.2. Cancellation

Khi HTTP client ngắt kết nối, downstream có thể cancel Publisher. Một adapter chuẩn nên chuyển cancel đến nguồn nếu source hỗ trợ. Tuy nhiên:

- CompletableFuture có thể đã bắt đầu chạy.
- Coroutine có Job lifecycle riêng.
- Callback API tùy chỉnh có thể không cung cấp cancel.
- Một SDK có thể tiếp tục hoạt động dù Subscriber đã hủy.

Khi viết custom adapter, kiểm tra nguồn có thực sự hỗ trợ unsubscribe/dispose/cancel không và dọn tài nguyên theo contract của nó.

### 15.3. Error propagation

Ngoại lệ từ thư viện nguồn phải được đưa về `onError`, không bị nuốt hoặc chuyển thành giá trị bình thường ngoài ý muốn. Khi bridge một future bị lỗi, có thể có wrapper `CompletionException`; khi bridge RxJava, lỗi đã được truyền trong Publisher chain.

Không dùng:

~~~java
// Sai khi chỉ muốn chuyển kiểu: làm mất lỗi gốc.
source.onErrorResume(error -> Mono.empty());
~~~

trừ khi empty fallback là một quyết định nghiệp vụ có chủ đích.

### 15.4. Thread scheduling

`ReactiveAdapterRegistry` không chuyển tác vụ blocking thành non-blocking và không tự tạo scheduler riêng cho mỗi nguồn.

Nếu một SDK blocking được gọi trực tiếp trong event loop, việc bọc kết quả bằng Mono không giải quyết blocking.

Ví dụ nếu API blocking thật sự:

~~~java
Mono<Result> safe = Mono.fromCallable(
                () -> blockingClient.fetch())
        .subscribeOn(Schedulers.boundedElastic());
~~~

Đây là snippet minh họa cần `blockingClient` và `Result`. Dùng executor/scheduler phù hợp và giới hạn concurrency. Đừng chạy blocking I/O trên event-loop mặc định.

### 15.5. Context propagation

Reactor `Context`, Kotlin `CoroutineContext`, thread-local MDC và tracing context không phải một hệ thống tự động giống nhau. Khi qua thư viện khác, cần xác nhận trace ID/security context còn được truyền hay không. Dùng cơ chế context propagation được Spring/Reactor và thư viện tương ứng hỗ trợ; không đoán rằng chỉ đăng ký adapter là đủ.

## 16. Cấu hình registry tùy chỉnh trong ứng dụng lớn

Nếu ứng dụng có SDK dùng custom reactive type ở nhiều controller, có thể muốn chia sẻ một registry cấu hình sẵn.

Thiết kế được khuyến nghị:

1. Tạo một `ReactiveAdapterRegistry` mới.
2. Đăng ký type sau các built-in adapters.
3. Cấu hình registry đó vào các thành phần WebFlux cần sử dụng.
4. Test argument resolution, return-value handling và HTTP encoding.
5. Test error, empty, multi-value và cancellation.

Ví dụ đăng ký trong một factory method:

~~~java
static ReactiveAdapterRegistry newRegistry() {
    ReactiveAdapterRegistry registry =
            new ReactiveAdapterRegistry();

    registry.registerReactiveType(
            ReactiveTypeDescriptor.multiValue(
                    Batch.class,
                    () -> new Batch(Flux.empty())),
            source -> ((Batch) source).publisher(),
            Batch::new);

    return registry;
}
~~~

Chỉ tạo một bean `ReactiveAdapterRegistry` không đảm bảo mọi Spring WebFlux component tự dùng bean đó. Cần kiểm tra cấu hình framework theo phiên bản. API `RequestMappingHandlerAdapter.setReactiveAdapterRegistry` là một điểm cấu hình, nhưng các result handler và codec path liên quan cũng phải thống nhất.

Nếu không cần custom type trở thành controller return/argument type trực tiếp, chuyển Batch sang Mono/Flux trong controller thường đơn giản và dễ bảo trì hơn.

## 17. Kiểm thử adapter đúng cách

Khi custom adapter được thêm, tối thiểu nên test:

| Test case | Điều cần xác minh |
| --- | --- |
| 0 value | Empty completion đúng semantics |
| 1 value | Không thêm/làm mất giá trị |
| N values | Không truncate khi type là multi-value |
| Error | onError và cause được bảo toàn |
| Cancellation | Upstream dispose/cancel theo contract |
| Backpressure | Không phát quá demand nếu nguồn hỗ trợ |
| Null value | Không vi phạm Reactive Streams onNext(null) |
| Deferred source | Không chạy sớm ngoài subscription nếu descriptor deferred |
| Eager future | Hành vi đã bắt đầu trước subscription được hiểu đúng |
| Runtime classpath thiếu dependency | getAdapter trả null; lỗi rõ ràng |
| Override adapter | Exact/assignable precedence đúng |
| HTTP controller | JSON object/array/stream đúng với cardinality |
| Thread/context | Không block event loop; trace/security context có policy rõ |

### 17.1. Test StepVerifier cho Reactor bridge

~~~java
ReactiveAdapter adapter =
        registry.getAdapter(Flowable.class);

StepVerifier.create(
        Flux.from(adapter.<Integer>toPublisher(
                Flowable.just(1, 2, 3))))
        .expectNext(1, 2, 3)
        .verifyComplete();
~~~

Đây là snippet test minh họa, cần dependency `reactor-test` ở scope test.

### 17.2. Test lỗi

~~~java
Flowable<Integer> failed =
        Flowable.error(new IllegalStateException("boom"));

StepVerifier.create(Flux.from(
        adapter.<Integer>toPublisher(failed)))
        .expectErrorMessage("boom")
        .verify();
~~~

Không chỉ test happy path vì khác biệt lớn nhất giữa adapter thường xuất hiện ở error/cancel/backpressure.

## 18. Những hiểu lầm và lỗi phổ biến

| Hiểu lầm/lỗi | Vì sao sai | Cách xử lý |
| --- | --- | --- |
| ReactiveAdapterRegistry là Reactor scheduler | Registry chỉ quản lý chuyển đổi kiểu | Dùng scheduler riêng cho blocking API |
| Có RxJava3 dependency là mọi API đều chấp nhận RxJava type | Hành vi phụ thuộc boundary; controller và functional API khác nhau | Kiểm tra API contract và dùng Mono/Flux khi cần |
| Không tìm thấy adapter nghĩa là Spring không hỗ trợ reactive | Có thể thiếu thư viện trong runtime classpath | Kiểm tra dependency và getAdapter |
| Dùng Mono.from với Publisher nhiều phần tử | Chỉ lấy tối đa phần tử đầu | Dùng Flux.from cho multi-value |
| Dùng Flux cho single-value mà không mô tả semantics | Framework có thể xem như 0..N | Dùng Mono hoặc descriptor đúng |
| CompletableFuture tự trở nên lazy khi đổi sang Mono | Future có thể đã chạy từ trước | Dùng defer nếu muốn trì hoãn tạo future |
| Observable luôn có backpressure | Observable không theo demand của Reactive Streams | Chọn Flowable/BackpressureStrategy |
| Adapter tự giới hạn bộ nhớ | Buffer không giới hạn có thể tăng | Giới hạn queue và kiểm tra slow consumer |
| Adapter tự truyền toàn bộ trace context | Context models khác nhau | Cấu hình context propagation rõ ràng |
| Custom registry instance tự áp dụng cho mọi controller | Framework components có thể dùng registry khác | Wire đúng components hoặc convert tại boundary |
| registerReactiveTypeOverride luôn override mọi subtype | Exact match được xét trước assignability | Test precedence với từng type |
| Đổi type nghĩa là đổi thread | Adapter không tự đổi scheduler | Chọn scheduler/dispatcher phù hợp |
| Nuốt mọi error thành empty | Mất nguyên nhân và sai contract | Giữ onError trừ khi fallback có chủ đích |
| Retrying/cancel của wrapper chắc chắn hủy side effect | Nguồn có thể không hỗ trợ cancel | Test end-to-end và dùng idempotency |
| Dùng ví dụ RxJava 2 trong Spring 7 | API/package không còn là nền mặc định | Ưu tiên RxJava 3 |

## 19. Checklist tích hợp thư viện reactive

- [ ] Xác định version Spring Framework và library cần tích hợp.
- [ ] Xác định API đang làm việc với Mono, Flux, Publisher, Future hay type khác.
- [ ] Kiểm tra runtime classpath và getAdapter.
- [ ] Hiểu 0..1, 1, 0..N hoặc no-value semantics.
- [ ] Dùng Mono.from cho single và Flux.from cho multi.
- [ ] Ưu tiên built-in adapter hoặc bridge chính thức trước khi tự viết.
- [ ] Với Observable, chọn backpressure policy và giới hạn queue.
- [ ] Với Future, hiểu eager evaluation và cancellation.
- [ ] Với coroutine, xác nhận dispatcher và context.
- [ ] Với custom type, đăng ký descriptor + toPublisher + fromPublisher.
- [ ] Đảm bảo registry tùy chỉnh được wire vào đúng component nếu cần.
- [ ] Không block event-loop; xử lý blocking API trên scheduler riêng.
- [ ] Giữ exception cause và terminal signal.
- [ ] Test empty, error, cancel, backpressure, null và concurrency.
- [ ] Kiểm tra HTTP JSON object/array/stream qua integration test.
- [ ] Theo dõi latency, memory, dropped signals và context propagation.

## 20. Tự kiểm tra

**Câu 1.** ReactiveAdapterRegistry dùng để làm gì?

Quản lý adapter chuyển đổi các kiểu reactive/async khác sang Reactive Streams Publisher và từ Publisher về kiểu tương ứng.

**Câu 2.** ReactiveAdapter và ReactiveTypeDescriptor khác nhau thế nào?

ReactiveAdapter chứa hàm chuyển đổi; descriptor mô tả reactive type và cardinality/deferred/empty semantics.

**Câu 3.** Registry có tự đăng ký RxJava 3 khi thư viện không ở classpath không?

Không. Adapter mặc định được đăng ký tùy thư viện có mặt trên runtime classpath.

**Câu 4.** Vì sao Mono và Flux không hoàn toàn thay thế nhau?

Mono mang ngữ nghĩa 0..1, Flux mang ngữ nghĩa 0..N; cardinality ảnh hưởng việc xử lý, kết thúc và ghi HTTP response.

**Câu 5.** CompletableFuture có luôn lazy khi chuyển thành Mono không?

Không. CompletableFuture có thể đã khởi chạy trước khi Mono được subscribe.

**Câu 6.** RxJava Flowable và Observable khác nhau về backpressure thế nào?

Flowable tuân theo Reactive Streams demand; Observable không có demand/backpressure trực tiếp như Flowable.

**Câu 7.** Spring 7 có mặc định tích hợp RxJava 1 và RxJava 2 như các bản cũ không?

Không nên giả định. Spring 7.0.x mô tả adapter tích hợp RxJava 3.

**Câu 8.** Vì sao phải kiểm tra getAdapter trả null?

Vì thư viện có thể chưa có trên classpath hoặc type chưa được đăng ký.

**Câu 9.** Khi nào dùng registerReactiveTypeOverride?

Khi cần thay đổi adapter đã có một cách có chủ đích, sau khi hiểu precedence exact match/assignability và test đầy đủ.

**Câu 10.** Một registry new trong service có tự áp dụng cho controller Spring không?

Không. Registry mới chỉ ảnh hưởng code dùng instance đó; muốn tích hợp WebFlux phải wire vào đúng components.

**Câu 11.** Vì sao không đổi Observable thành Flowable BUFFER một cách vô điều kiện ở luồng lớn?

Vì buffer có thể tăng rất nhiều nếu upstream phát nhanh hơn downstream tiêu thụ.

**Câu 12.** Kotlin Flow và Deferred có cùng cơ chế tích hợp không?

Không nhất thiết. Deferred có adapter theo classpath; Kotlin Flow/controller coroutine còn có cơ chế tích hợp coroutine khác.

**Câu 13.** Adapter có tự làm một API blocking thành non-blocking không?

Không. Blocking API vẫn cần thread/scheduler phù hợp hoặc thay bằng API thật sự non-blocking.

**Câu 14.** Vì sao cần test cancellation và error, không chỉ giá trị?

Vì bridge sai có thể rò tài nguyên, nuốt exception hoặc không hủy upstream đúng contract.

## 21. Tài liệu tham khảo chính thức

- [Spring Framework — Reactive Libraries](https://docs.spring.io/spring-framework/reference/web/webflux-reactive-libraries.html): các thư viện reactive, WebFlux annotated controllers, functional APIs và ý nghĩa Mono/Flux.
- [ReactiveAdapterRegistry JavaDoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/ReactiveAdapterRegistry.html): đăng ký mặc định, getAdapter, registerReactiveType và registerReactiveTypeOverride.
- [ReactiveAdapter JavaDoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/ReactiveAdapter.html): toPublisher/fromPublisher, descriptor và metadata cardinality.
- [ReactiveTypeDescriptor JavaDoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/ReactiveTypeDescriptor.html): factory multiValue, singleOptionalValue, singleRequiredValue, noValue và nonDeferredAsyncValue.
- [Spring Framework — WebFlux](https://docs.spring.io/spring-framework/reference/web/webflux.html): reactive stack, annotated và functional endpoints.
- [Project Reactor — Reference Guide](https://projectreactor.io/docs/core/release/reference/): Mono, Flux, Reactive Streams và backpressure.
- [RxJava 3 — GitHub](https://github.com/ReactiveX/RxJava): Flowable, Observable, Maybe, Single và Completable.
- [Kotlin Coroutines — Reactor Integration](https://kotlinlang.org/api/kotlinx.coroutines/kotlinx-coroutines-reactor/): bridges giữa coroutine và Reactor.
- [SmallRye Mutiny — Guides](https://smallrye.io/smallrye-mutiny/latest/): Uni/Multi và integration patterns.
- [Reactive Streams Specification](https://www.reactive-streams.org/): Publisher, Subscriber, Subscription, backpressure và cancellation.
- [Spring Boot 4.1.2 release](https://spring.io/blog/2026/10/23/spring-boot-4-1-2-available-now/): phiên bản Boot ổn định dùng trong ví dụ.

**Ghi nhớ:** ReactiveAdapterRegistry là cầu nối type/semantics, không phải scheduler. Kiểm tra runtime classpath, xác định đúng cardinality, rồi dùng built-in adapter hoặc bridge để tích hợp. Mono/Flux vẫn là lựa chọn rõ ràng ở boundary WebFlux; custom adapter chỉ nên đăng ký khi thật sự cần hỗ trợ type bên ngoài xuyên suốt framework. Khi đổi thư viện, luôn kiểm tra backpressure, empty/error signals, cancellation, context propagation và hành vi blocking.