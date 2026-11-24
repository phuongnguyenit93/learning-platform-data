# Đăng ký nhận dữ liệu (subscription) và thời điểm thực thi

Trong lập trình reactive, một `Mono<T>` hoặc `Flux<T>` mô tả một nguồn dữ liệu sẽ phát ra kết quả trong tương lai. Việc tạo pipeline chỉ ghép các thao tác xử lý; nguồn dữ liệu thường chưa bắt đầu làm việc cho đến khi có một **subscription**. Subscription kết nối bên nhận với publisher, truyền yêu cầu về số phần tử cần nhận và cho phép hủy luồng khi không còn nhu cầu.

Khái niệm này đặc biệt quan trọng khi dùng RSocket. Một lời gọi `request-response` hoặc `request-stream` thường được biểu diễn bằng `Mono` hoặc `Flux`. Khi publisher đó được subscribe, tương tác RSocket mới được khởi động; sau đó demand và tín hiệu hủy có thể truyền ngược qua chuỗi reactive để điều tiết luồng dữ liệu.

## 1. Publisher, Subscriber và Subscription

Reactive Streams định nghĩa ba vai trò chính:

| Thành phần | Trách nhiệm |
|---|---|
| `Publisher<T>` | Cung cấp một chuỗi phần tử, lỗi hoặc tín hiệu hoàn tất. Trong Reactor, `Mono<T>` phát tối đa một phần tử, còn `Flux<T>` phát từ không đến nhiều phần tử. |
| `Subscriber<T>` | Đăng ký nhận dữ liệu và xử lý các tín hiệu `onNext`, `onError`, `onComplete`. |
| `Subscription` | Đại diện cho mối quan hệ giữa subscriber và publisher; cho phép yêu cầu thêm dữ liệu bằng `request(n)` hoặc dừng nhận bằng `cancel()`. |

Trình tự cơ bản của một subscription như sau:

1. Subscriber gọi `subscribe()` trên publisher.
2. Publisher gọi `onSubscribe(subscription)` để cung cấp đối tượng điều khiển luồng.
3. Subscriber gọi `request(n)` để báo rằng nó sẵn sàng nhận tối đa `n` phần tử.
4. Publisher phát các phần tử qua `onNext(value)` theo demand hiện có.
5. Luồng kết thúc bằng đúng một tín hiệu terminal: `onComplete()` hoặc `onError(error)`. Subscriber cũng có thể gọi `cancel()` trước khi luồng kết thúc.

```text
Subscriber                         Publisher
    |                                  |
    |----------- subscribe() --------->|
    |<------ onSubscribe(subscription)-|
    |                                  |
    |----------- request(2) ---------->|
    |<----------- onNext(A) -----------|
    |<----------- onNext(B) -----------|
    |                                  |
    |<--------- onComplete() ----------|
```

`request(n)` là cơ chế backpressure của Reactive Streams. Subscriber có thể yêu cầu từng phần tử, theo từng lô hoặc yêu cầu không giới hạn bằng `Long.MAX_VALUE`. Các overload `subscribe()` tiện dụng của Reactor thường yêu cầu không giới hạn; vì vậy, nếu cần kiểm soát demand, hãy dùng một subscriber có chiến lược yêu cầu rõ ràng.

Ví dụ sau xử lý từng phần tử rồi mới yêu cầu phần tử tiếp theo:

```java
Flux.range(1, 5)
    .subscribe(new BaseSubscriber<Integer>() {
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
```

Demand thể hiện khả năng tiếp nhận của subscriber, không phải một cam kết về tốc độ theo giây. Publisher có thể dùng bộ đệm hoặc cơ chế prefetch nội bộ, nhưng phải tuân thủ quy tắc không phát nhiều phần tử hơn demand mà subscriber đã cho phép.

## 2. Bốn thời điểm cần phân biệt

Khi đọc một pipeline reactive, hãy phân biệt thời điểm tạo pipeline, đăng ký, yêu cầu dữ liệu và nhận tín hiệu.

| Thời điểm | Điều xảy ra | Ví dụ |
|---|---|---|
| Assembly time (lắp ráp) | Các publisher và operator được ghép thành một pipeline. Thông thường, logic bên trong các operator chưa chạy. | Gọi `map`, `filter`, `flatMap` để tạo chuỗi xử lý. |
| Subscription time (đăng ký) | Subscriber gắn vào publisher; quá trình subscribe truyền từ downstream về upstream. Nguồn cold thường bắt đầu công việc ở giai đoạn này. | Gọi `mono.subscribe()` hoặc framework subscribe publisher được trả về. |
| Request time (yêu cầu) | Subscriber phát demand bằng `request(n)`. Publisher được phép phát dữ liệu theo nhu cầu đó. | `BaseSubscriber.request(1)`. |
| Signal time (phát tín hiệu) | Các callback nhận `onNext`, `onError` hoặc `onComplete`. Tùy nguồn và scheduler, tín hiệu có thể đến ngay hoặc đến sau. | Callback trong `subscribe(onNext, onError, onComplete)`. |

Với nguồn đồng bộ như `Flux.range`, các phần tử có thể được phát ngay trên thread gọi `subscribe()`. Vì vậy, callback `onNext` thậm chí có thể chạy trước khi lời gọi `subscribe()` trả về. Với nguồn bất đồng bộ như luồng mạng hoặc `Flux.interval`, tín hiệu thường đến sau đó.

Điểm cốt lõi là **tạo publisher không đồng nghĩa với thực thi publisher**. Tuy nhiên, cần kiểm tra cách tạo giá trị đầu vào: một biểu thức Java được đánh giá trước khi truyền vào `Mono.just(...)` vẫn chạy ngay tại thời điểm assembly.

## 3. Lazy execution: chạy khi có subscription

So sánh hai cách tạo `Mono`:

```java
// readProfile() được gọi ngay khi dòng này được thực thi.
Mono<Profile> eager = Mono.just(readProfile());

// readProfile() chỉ được gọi khi có subscription.
Mono<Profile> lazy = Mono.fromCallable(this::readProfile);
```

`Mono.just(value)` giữ lại giá trị đã có. Nó không trì hoãn việc tính toán biểu thức dùng để tạo `value`. Ngược lại, `Mono.fromCallable(...)` giữ một tác vụ và gọi tác vụ đó khi publisher được subscribe. Nếu tác vụ ném exception, Reactor chuyển exception thành tín hiệu `onError`.

Khi cần tạo một publisher mới cho mỗi subscriber, dùng `defer`:

```java
Mono<Profile> profilePerSubscriber = Mono.defer(() ->
    Mono.fromCallable(this::readProfile)
);
```

Hàm bên trong `defer` được gọi mỗi lần có subscription. Điều này hữu ích khi cần đọc trạng thái mới nhất, tạo request riêng hoặc lấy thời điểm hiện tại cho từng lần gọi.

```java
Mono<Instant> requestTime = Mono.defer(() -> Mono.just(Instant.now()));
```

Nếu một cold publisher được subscribe hai lần, công việc nguồn thường được thực hiện hai lần:

```java
Mono<Profile> profile = Mono.fromCallable(this::readProfile);

profile.subscribe(this::useProfile);
profile.subscribe(this::auditProfile);
```

Hai subscription độc lập có thể tạo ra hai lần đọc dữ liệu. Đây cũng là điều cần nhớ với publisher đại diện cho lời gọi RSocket: trong trường hợp thông thường, mỗi subscription vào publisher request sẽ khởi tạo một tương tác riêng với peer từ xa. Các operator như `cache`, `share` hoặc cơ chế chia sẻ khác có thể thay đổi hành vi này; không nên giả định mọi publisher đều tạo request mới hoặc đều dùng chung một request.

## 4. Cold publisher và hot publisher

Subscription có ý nghĩa khác nhau tùy loại nguồn:

- **Cold publisher** bắt đầu phát dữ liệu cho từng subscriber. Mỗi subscriber thường có một luồng thực thi riêng và nhận chuỗi dữ liệu bắt đầu từ đầu. Các publisher tạo từ `Mono.fromCallable`, `Flux.range` hoặc một lời gọi request RSocket thông thường thường có hành vi cold.
- **Hot publisher** có thể phát dữ liệu độc lập với subscriber. Subscriber tham gia muộn có thể bỏ lỡ những phần tử đã phát trước đó. Các sự kiện được đẩy từ một nguồn dùng chung, chẳng hạn một `Sinks.Many`, là ví dụ thường gặp.

```java
// Mỗi subscription tạo một chuỗi mới.
Flux<Integer> cold = Flux.defer(() -> Flux.range(1, 3));

// Nhiều subscriber có thể cùng quan sát một nguồn được chia sẻ.
Flux<Integer> shared = Flux.range(1, 3).share();
```

`share()` thay đổi vòng đời và cách phân phối dữ liệu giữa các subscriber. Hãy chọn cold hay hot theo yêu cầu nghiệp vụ: một client cần kết quả độc lập cho từng request, hay nhiều client cần quan sát cùng một luồng sự kiện đang diễn ra.

## 5. Subscription khởi động tương tác RSocket

Trong Spring RSocket, `RSocketRequester` tạo publisher cho các kiểu tương tác. Việc gọi `route(...)`, `data(...)` và `retrieveMono(...)` hoặc `retrieveFlux(...)` xây dựng publisher. Khi publisher được subscribe, client mới thực hiện tương tác với server.

### Request-response

```java
Mono<Quote> latestQuote = requester
    .route("quotes.latest")
    .data("ACME")
    .retrieveMono(Quote.class);

return latestQuote;
```

Publisher có kiểu `Mono<Quote>` vì tương tác trả về tối đa một kết quả. Nếu phương thức service hoặc controller trả `Mono` này cho framework, framework sẽ subscribe ở ranh giới xử lý request. Nếu tự gọi `subscribe()` ở đây, ứng dụng có thể tách luồng công việc khỏi vòng đời request của framework.

### Request-stream

```java
Flux<Quote> quotes = requester
    .route("quotes.stream")
    .data(new QuoteRequest("ACME"))
    .retrieveFlux(Quote.class);

return quotes
    .take(10)
    .doOnNext(this::handleQuote)
    .doFinally(signal -> log.debug("Quote stream ended: {}", signal));
```

Khi publisher được subscribe, client mở request-stream. `Flux` đại diện cho nhiều kết quả và demand của subscriber được dùng để điều tiết việc nhận dữ liệu. Trong ví dụ, `take(10)` hoàn tất sau tối đa mười phần tử và hủy subscription upstream; việc hủy được truyền qua chuỗi để RSocket có thể dừng luồng đang được yêu cầu.

### Fire-and-forget

```java
Mono<Void> sendAuditEvent = requester
    .route("audit.record")
    .data(event)
    .send();

return sendAuditEvent;
```

`send()` trả về `Mono<Void>`. Subscription khởi động thao tác gửi. Vì fire-and-forget không có response payload từ server, việc publisher hoàn tất không nên được hiểu là nghiệp vụ phía server đã xử lý xong và thành công; nó chỉ phản ánh vòng đời gửi theo API và transport.

### Request-channel

Request-channel cho phép client gửi một publisher đầu vào và đồng thời nhận một publisher đầu ra:

```java
Flux<PriceUpdate> updates = requester
    .route("prices.channel")
    .data(clientCommands)
    .retrieveFlux(PriceUpdate.class);

return updates;
```

Ở đây, `clientCommands` là nguồn dữ liệu client gửi lên; `updates` là các phần tử server trả về. Việc subscribe vào `updates` khởi động tương tác channel. Hai chiều có thể tiếp tục hoạt động trong cùng một tương tác và đều cần được quản lý theo vòng đời subscription.

Ở phía server, Spring có thể quản lý subscription cho publisher được trả về từ handler:

```java
@MessageMapping("quotes.stream")
public Flux<Quote> stream(QuoteRequest request) {
    return quoteService.stream(request.symbol());
}
```

Handler trả về `Flux` để framework kết nối nó với request RSocket đến. Không cần gọi `subscribe()` bên trong handler. Khi tự subscribe, handler có thể tạo một luồng phụ mà framework không còn kiểm soát được demand, lỗi và việc hủy theo kết nối của client.

## 6. Điều khiển thread và thời điểm chạy

Subscription quyết định khi nào nguồn được kích hoạt; scheduler quyết định nơi một phần công việc được thực thi. Hai khái niệm này liên quan nhưng không đồng nhất. Một pipeline reactive không tự động chạy song song chỉ vì nó dùng `Flux` hoặc `Mono`.

```java
Mono<Profile> profile = Mono.fromCallable(() -> repository.loadProfile("u-42"))
    .subscribeOn(Schedulers.boundedElastic())
    .map(this::toProfileView)
    .publishOn(Schedulers.parallel())
    .map(this::calculateSummary);

return profile;
```

- `subscribeOn(...)` ảnh hưởng đến nơi subscription được thực hiện và nguồn upstream bắt đầu chạy. `boundedElastic` phù hợp khi phải gọi API đồng bộ hoặc thư viện blocking.
- `publishOn(...)` chuyển việc xử lý các tín hiệu downstream kể từ vị trí operator đó sang scheduler được chọn. Trong ví dụ, `calculateSummary` chạy trên scheduler dành cho tác vụ CPU.
- Nếu không chỉ định scheduler, operator đồng bộ thường chạy trên thread phát tín hiệu. Nguồn bất đồng bộ có thể phát trên thread riêng do chính nguồn hoặc thư viện quản lý.

Với RSocket, I/O mạng thường được runtime xử lý trên các event loop. Không nên gọi thao tác blocking như `block()`, truy vấn JDBC đồng bộ hoặc `Thread.sleep()` trực tiếp trên event loop, vì một thread bị chặn có thể làm chậm nhiều kết nối. Nếu phải dùng API blocking, hãy cô lập tác vụ đó trên scheduler phù hợp; ưu tiên driver và API reactive khi có thể.

## 7. Hủy subscription và quản lý vòng đời

Subscription không chỉ dùng để bắt đầu nhận dữ liệu. Nó còn là cách biểu đạt rằng bên nhận không còn cần luồng nữa. Reactor cung cấp `Disposable` từ các overload `subscribe()`:

```java
Disposable subscription = quotes.subscribe(
    this::handleQuote,
    error -> log.error("Cannot receive quotes", error),
    () -> log.info("Quote stream completed")
);

// Khi màn hình đóng hoặc người dùng rời khỏi luồng:
subscription.dispose();
```

`dispose()` hủy subscription. Với request-stream hoặc request-channel, tín hiệu cancel được truyền qua pipeline và có thể khiến tương tác RSocket dừng. Thời điểm giải phóng tài nguyên ở phía xa còn phụ thuộc vào publisher, transport và cách handler xử lý hủy.

Có thể quan sát tín hiệu kết thúc để dọn dẹp tài nguyên:

```java
Flux<Data> stream = dataService.stream()
    .doFinally(signalType -> releaseLocalResources());
```

`doFinally` được gọi khi luồng hoàn tất, lỗi hoặc bị hủy. Với tài nguyên bất đồng bộ có quy trình đóng riêng, hãy dùng các operator quản lý tài nguyên phù hợp của Reactor, chẳng hạn `usingWhen`, để việc cleanup nằm trong vòng đời reactive.

Một subscriber phải xử lý lỗi. Nếu dùng `subscribe()` mà không có error consumer, lỗi có thể đi vào cơ chế xử lý lỗi mặc định của Reactor và khó được gắn với ngữ cảnh request. Với service và controller, thường nên để lỗi tiếp tục đi trong `Mono` hoặc `Flux`, rồi xử lý ở ranh giới ứng dụng.

## 8. Những lỗi thường gặp

| Cách làm | Hệ quả | Cách xử lý |
|---|---|---|
| Tạo publisher nhưng không bao giờ subscribe và cũng không trả nó cho framework | Cold publisher không được kích hoạt, nên công việc dự kiến không chạy. | Trả `Mono`/`Flux` cho caller hoặc subscribe tại ranh giới sở hữu vòng đời tác vụ. |
| Gọi `subscribe()` bên trong service rồi trả về một publisher khác | Tạo subscription phụ; caller không còn kiểm soát đầy đủ lỗi, cancellation và thời điểm hoàn tất của công việc đó. | Kết hợp tác vụ bằng `map`, `flatMap`, `then` hoặc operator phù hợp và trả một pipeline duy nhất. |
| Dùng `Mono.just(expensiveCall())` với kỳ vọng lazy | `expensiveCall()` đã chạy trước khi `Mono.just` được tạo. | Dùng `fromCallable`, `fromSupplier` hoặc `defer` tùy yêu cầu. |
| Subscribe nhiều lần vào cold publisher | Có thể thực hiện lặp lại truy vấn, side effect hoặc request RSocket. | Xác định rõ có cần một tương tác cho mỗi subscriber hay cần chia sẻ/kết quả cache. |
| Chặn event loop bằng `block()` hoặc API blocking | Giảm khả năng phục vụ các kết nối đồng thời và có thể gây nghẽn. | Giữ pipeline non-blocking; cô lập phần blocking trên scheduler phù hợp. |
| Không quản lý subscription của một stream dài hạn | Stream có thể tiếp tục giữ tài nguyên sau khi người dùng không còn cần dữ liệu. | Giữ `Disposable` khi tự subscribe và hủy nó khi vòng đời sử dụng kết thúc; ưu tiên để framework quản lý nếu có thể. |

## 9. Cách kiểm tra thời điểm thực thi

Khi một request RSocket không phát dữ liệu hoặc phát dữ liệu nhiều lần, hãy lần lượt kiểm tra:

1. Publisher đã được subscribe chưa? Nếu được trả về từ controller hoặc handler, xác định framework nào chịu trách nhiệm subscribe.
2. Nguồn là cold hay hot? Một subscription mới có tạo lại request hoặc side effect không?
3. Giá trị được tính lúc assembly hay lúc subscription? Kiểm tra các lời gọi nằm bên trong đối số của `just(...)`.
4. Subscriber đã tạo demand chưa? Có operator nào giới hạn, giữ hoặc hủy demand như `take`, `limitRate` hay `onBackpressure...` không?
5. Subscription kết thúc theo `onComplete`, `onError` hay `cancel`? Kiểm tra error handler và cleanup bằng `doFinally` khi cần.
6. Công việc chạy trên thread nào? Tìm thao tác blocking có thể đang chiếm event loop hoặc scheduler dùng chung.

Có thể thêm log ở những điểm quan trọng mà không tự tạo subscription mới:

```java
Flux<Quote> traced = requester
    .route("quotes.stream")
    .data(new QuoteRequest("ACME"))
    .retrieveFlux(Quote.class)
    .doOnSubscribe(s -> log.debug("Quote subscription started"))
    .doOnRequest(n -> log.debug("Quote demand: {}", n))
    .doOnNext(quote -> log.debug("Received quote: {}", quote))
    .doOnError(error -> log.warn("Quote stream failed", error))
    .doFinally(signal -> log.debug("Quote subscription ended: {}", signal));
```

Các hook trên quan sát vòng đời của subscription hiện có. Chúng hữu ích để phân biệt publisher đã được tạo nhưng chưa chạy, stream đã chạy nhưng chưa có demand, và stream đã kết thúc do lỗi hoặc cancellation.

## Kết luận

Subscription là điểm nối giữa publisher và bên tiêu thụ dữ liệu: nó kích hoạt nguồn cold, thiết lập demand, nhận tín hiệu và cho phép hủy luồng. Khi làm việc với RSocket, hãy xác định publisher nào đại diện cho tương tác mạng, ai chịu trách nhiệm subscribe, demand được quản lý ra sao và subscription kết thúc lúc nào. Nắm rõ các thời điểm này giúp dự đoán chính xác khi request được gửi, dữ liệu bắt đầu đến, tác vụ chạy trên thread nào và tài nguyên được giải phóng khi client ngừng nhận dữ liệu.
