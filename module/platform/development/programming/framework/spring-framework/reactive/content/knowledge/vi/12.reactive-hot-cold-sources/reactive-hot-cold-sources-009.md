# Vòng đời bên nhận, đăng ký muộn và nguy cơ rò rỉ trong Reactor

## 1. Vấn đề cần hiểu

Trong Project Reactor, một publisher mô tả cách phát dữ liệu; subscriber đăng ký để nhận dữ liệu và điều khiển nhu cầu. Publisher có thể là **cold** (mỗi subscription thường khởi động một lần thực thi riêng) hoặc **hot** (sự kiện được phát độc lập với một subscriber cụ thể). Khác biệt này quyết định điều gì xảy ra khi có người đăng ký muộn, khi subscriber ngừng nhận dữ liệu và khi ứng dụng giữ một luồng sự kiện sống lâu.

Ba câu hỏi phải trả lời khi thiết kế:

1. **Ai sở hữu vòng đời nguồn?** Một request, một subscriber, một bean ứng dụng, hay một dịch vụ phát sự kiện dùng chung?
2. **Subscriber đến lúc nào?** Nếu đến sau khi hot source đã phát dữ liệu, nó có nhận được lịch sử không?
3. **Ai chịu trách nhiệm kết thúc?** Khi client ngắt kết nối hoặc không còn người nhận, upstream có được hủy và tài nguyên có được giải phóng không?

Nếu bỏ qua các câu hỏi này, ứng dụng có thể gọi API nhiều lần ngoài ý muốn, bỏ lỡ sự kiện, giữ connection hoặc scheduler hoạt động sau khi request đã kết thúc, hoặc lưu một lịch sử dữ liệu không giới hạn trong heap.

## 2. Vòng đời của một subscriber

Một subscription Reactive Streams có vòng đời tổng quát:

```text
Publisher.subscribe(subscriber)
          |
          v
Subscriber.onSubscribe(subscription)
          |
          v
Subscriber.request(n)  ----->  Publisher có thể phát dữ liệu theo demand
          |                              |
          |                         onNext(value)
          |                              |
          |<-----------------------------+
          |
          +---- onComplete()   (hoàn tất thành công)
          |
          +---- onError(error) (kết thúc lỗi)

Bất cứ khi nào trước terminal:
Subscriber.cancel()  ----->  yêu cầu ngừng nhận dữ liệu / hủy upstream
```

Các quy tắc:

- `onSubscribe` thiết lập subscription và thường chỉ xuất hiện một lần cho subscriber đó.
- `request(n)` biểu thị nhu cầu nhận tối đa thêm `n` phần tử. Toán tử trung gian có thể điều chỉnh demand trước khi truyền lên upstream.
- `onNext` mang dữ liệu; một `Mono` phát tối đa một giá trị, còn `Flux` có thể phát nhiều giá trị.
- `onComplete` và `onError` là tín hiệu kết thúc (terminal), loại trừ nhau. Sau terminal, subscription không phát thêm `onNext`.
- `cancel()` là yêu cầu từ subscriber. Nó **không phải** `onComplete` hay `onError` gửi xuống subscriber.

Khi subscriber hủy, operator cố gắng truyền cancellation ngược lên upstream để dừng công việc và giải phóng tài nguyên. Việc tác vụ vật lý có dừng ngay hay không còn phụ thuộc nguồn, driver và API được gọi. Một SDK blocking không hỗ trợ interruption có thể tiếp tục chạy dù caller đã cancel.

### Các callback quan sát vòng đời

| Operator | Thời điểm |
|---|---|
| `doOnSubscribe` | Khi subscriber đăng ký |
| `doOnRequest` | Khi upstream nhận demand qua vị trí operator đó |
| `doOnNext` | Khi có phần tử |
| `doOnComplete` | Khi hoàn tất thành công |
| `doOnError` | Khi kết thúc bằng lỗi |
| `doOnCancel` | Khi nhận yêu cầu cancellation |
| `doFinally` | Sau complete, error hoặc cancel; nhận `SignalType` tương ứng |

`doFinally` hữu ích để đo vòng đời, nhưng callback của nó đồng bộ và không phải cơ chế chờ cleanup bất đồng bộ. Nếu cần trả connection reactive, commit/rollback hoặc close qua publisher, dùng cơ chế resource scope như `usingWhen`.

## 3. Cold source: mỗi subscriber có thể khởi động một lần thực thi riêng

Cold publisher thường bắt đầu tạo dữ liệu khi có subscription. Mỗi subscriber độc lập có thể nhận toàn bộ sequence và kích hoạt một lần thực thi mới.

```java
Flux<String> cold = Flux.defer(() ->
        Flux.just("A", "B", "C")
);

cold.subscribe(System.out::println);
cold.subscribe(System.out::println);
```

Hai subscription sẽ lần lượt nhận `A, B, C`. `Flux.defer` gọi supplier khi có subscriber, nên supplier chạy hai lần.

Một nguồn cold điển hình trong ứng dụng có thể là publisher do `WebClient` tạo:

```java
Mono<Customer> customer = webClient.get()
        .uri("/customers/{id}", customerId)
        .retrieve()
        .bodyToMono(Customer.class);
```

Thông thường mỗi lần subscribe publisher này sẽ khởi động một HTTP request mới. Nếu hai nơi cùng subscribe, có thể có hai request thật. Đây là điểm quan trọng khi publisher được lưu trong field rồi dùng ở nhiều chỗ.

### `defer` và `just` khác nhau về thời điểm đánh giá

```java
AtomicInteger counter = new AtomicInteger();

Mono<Integer> captured = Mono.just(counter.incrementAndGet());
Mono<Integer> perSubscription =
        Mono.defer(() -> Mono.just(counter.incrementAndGet()));
```

- `Mono.just(...)` đánh giá đối số **ngay khi tạo publisher**. Giá trị được chụp một lần rồi phát lại cho các subscriber.
- `Mono.defer(...)` chạy supplier ở mỗi subscription; subscriber mới có thể nhận giá trị mới.

Ví dụ `Mono.just(loadFromDatabase())` gọi `loadFromDatabase()` ngay tại assembly time, có thể gây I/O trước subscription và thậm chí block thread đang tạo publisher. Nếu muốn trì hoãn lời gọi đồng bộ đến subscription, dùng `Mono.fromCallable(...)` và chọn scheduler phù hợp khi thao tác blocking. Nếu muốn mỗi subscription thực hiện một request reactive, tạo publisher bên trong `defer` khi cần khởi tạo lại client call.

**Lưu ý:** Không phải mọi publisher có thể subscribe nhiều lần đều có ngữ nghĩa giống nhau. Đọc contract của driver/client và kiểm tra xem nó có cho phép nhiều subscription hay response body chỉ tiêu thụ một lần.

## 4. Hot source: sự kiện tồn tại độc lập với một subscriber

Hot publisher có thể phát sự kiện theo thời gian mà không đợi subscriber cụ thể. Ví dụ:

- Nguồn giá thị trường hoặc telemetry đang được cập nhật.
- Event bus của ứng dụng.
- Một luồng thông báo được đẩy vào `Sinks.Many`.
- Một nguồn đã được connect và chia sẻ giữa nhiều request.

Một subscriber hot source thường chỉ nhận sự kiện kể từ lúc nó tham gia, trừ khi nguồn có cơ chế replay hoặc lưu lịch sử.

```text
Thời gian:       t1       t2       t3       t4
Hot source:      E1 ------ E2 ------ E3 ------ E4
Subscriber A:    subscribe -------------------->
Nhận A:                   E2       E3       E4

Subscriber B:                         subscribe
Nhận B:                                        E4
```

A tham gia trước E2 nên thấy E2, E3, E4. B tham gia gần t4 nên chỉ thấy E4. Nếu E1–E3 quan trọng, hot source không replay sẽ không thể tự khôi phục các sự kiện đó cho B.

### Không nên gắn nhãn chỉ dựa vào class

- `Flux.defer(...)` thường là cold vì supplier chạy cho mỗi subscriber.
- `Flux.interval(...)` tạo lịch phát riêng cho mỗi subscription; hai subscriber có thể có hai nhịp độc lập. Nếu muốn chia sẻ cùng một clock, cần chia sẻ publisher.
- `Mono.just(value)` chụp giá trị tại thời điểm assembly và phát lại giá trị đã chụp; nó không tương đương `defer`.
- Một `Sinks.Many` là cổng phát tín hiệu chủ động; chính loại sink và cách kết nối quyết định subscriber mới có thấy lịch sử hay chỉ thấy sự kiện tương lai.

Điều cần xác định là **thời điểm tạo dữ liệu, thời điểm subscribe, và chính sách lưu/replay**, không chỉ tên lớp.

## 5. Đăng ký muộn: mất lịch sử hay nhận lại dữ liệu?

Khi subscriber đến muộn, kết quả phụ thuộc operator/sink đứng trước nó:

| Cơ chế | Subscriber đến muộn nhận gì? | Điểm cần cân nhắc |
|---|---|---|
| Cold publisher (`defer`, request mới) | Một lần thực thi mới từ đầu | Có thể lặp HTTP/DB side effect |
| Hot multicast không replay | Chỉ sự kiện phát sau khi đăng ký | Sự kiện trước đó bị bỏ lỡ |
| `replay(n)` / replay sink giới hạn | Một số phần tử gần nhất và phần tử mới | Bộ nhớ, dữ liệu nhạy cảm, độ dài lịch sử |
| `cache(n)` trên Flux | Lịch sử gần nhất theo giới hạn và tín hiệu kết thúc | Chạy nguồn một lần, giữ dữ liệu cho subscriber sau |
| `cache()` không giới hạn lịch sử trên Flux | Có thể giữ toàn bộ phần tử | Nguy cơ heap tăng với stream dài/vô hạn |
| `share()` / `publish().refCount(1)` | Tham gia luồng đang được chia sẻ; không replay lịch sử | Upstream sống theo số subscriber |
| `autoConnect(n)` | Tham gia sau khi nguồn đã kết nối | Kết nối không tự ngắt khi subscriber về 0 |

### Ví dụ timeline

Giả sử một hot source phát `E1`, `E2`, `E3`, rồi B đăng ký:

- Multicast không replay: B chỉ thấy `E4` trở đi.
- Replay 2 phần tử: B thấy `E2`, `E3`, sau đó E4...
- Cold source: B khởi động một lần thực thi mới và có thể thấy E1, E2, E3 của lần thực thi riêng đó.
- Cache: B nhận các giá trị đã cache, có thể không gây thêm lần gọi upstream.

Đừng dùng replay/cache để thay thế một event store bền vững nếu dữ liệu phải tồn tại qua restart, deploy hoặc sự cố process. Cache trong bộ nhớ của một JVM không phải lịch sử durable.

## 6. Chia sẻ nguồn với `publish`, `refCount`, `share` và `autoConnect`

Reactor cung cấp `ConnectableFlux` để điều khiển khi nào một nguồn bắt đầu phát tới nhiều subscriber.

### 6.1. `publish()` và `connect()`

```java
ConnectableFlux<Long> connectable =
        Flux.interval(Duration.ofSeconds(1)).publish();

Disposable connection = connectable.connect();
```

`publish()` tạo một publisher có thể được connect. `connect()` bắt đầu upstream và trả về `Disposable` đại diện connection. Subscriber đăng ký vào connectable để nhận tín hiệu; nếu connect trước khi subscriber vào, sự kiện có thể đã phát trước khi subscriber tham gia.

Khi ứng dụng sở hữu connection thủ công, phải giữ `Disposable` và dispose khi không còn cần:

```java
connection.dispose();
```

Đừng gọi `connect()` nhiều lần tùy tiện. Cần hiểu contract kết nối và giữ handle của connection do ứng dụng quản lý.

### 6.2. `autoConnect(n)`

```java
Flux<Long> sharedAfterTwo =
        Flux.interval(Duration.ofSeconds(1))
                .publish()
                .autoConnect(2);
```

Nguồn chỉ bắt đầu connect khi đủ hai subscriber. `autoConnect` phù hợp khi số subscriber tối thiểu là điều kiện bắt đầu. Sau khi đã connect, việc subscriber rời đi **không tự động ngắt upstream theo kiểu ref-count**. Với một nguồn vô hạn, nó có thể tiếp tục chạy khi không còn ai quan sát nếu không có cách quản lý connection phù hợp.

### 6.3. `refCount(n)` và `share()`

```java
Flux<Long> sharedWhileObserved =
        Flux.interval(Duration.ofSeconds(1))
                .publish()
                .refCount(1);
```

`refCount(1)` bắt đầu kết nối khi có ít nhất một subscriber và ngắt upstream khi số subscriber giảm xuống dưới ngưỡng. Với ngưỡng 1, nguồn được chia sẻ trong khi còn người nhận. Đây là cách phù hợp hơn khi vòng đời upstream cần gắn với subscriber đang quan sát.

`share()` là cách viết ngắn cho mô hình chia sẻ/ref-count thông dụng:

```java
Flux<Long> shared = Flux.interval(Duration.ofSeconds(1)).share();
```

Không nên dựa vào giả định rằng mọi subscriber mới sẽ nhận lịch sử. `share()` không phải replay cache. Các chi tiết tái kết nối sau terminal/cancel có thể phụ thuộc phiên bản và trạng thái nguồn; nếu hành vi reconnect là yêu cầu quan trọng, viết test cho phiên bản Reactor đang dùng.

### So sánh nhanh

| Operator | Bắt đầu nguồn | Khi subscriber cuối rời đi | Replay |
|---|---|---|---|
| `publish().connect()` | Khi gọi `connect()` | Không tự động; chủ sở hữu dispose connection | Không |
| `publish().autoConnect(n)` | Khi đủ n subscriber | Không tự ref-count về 0 | Không |
| `publish().refCount(n)` | Khi đạt ngưỡng n | Hủy upstream khi giảm dưới ngưỡng theo contract | Không |
| `share()` | Khi có subscriber đầu tiên | Gắn với số subscriber đang quan sát | Không |
| `replay(n).autoConnect(...)` | Khi connect/đạt ngưỡng | Tùy cách quản lý connection | Có, giữ lịch sử giới hạn |

Chọn operator theo lifecycle mong muốn, không chỉ theo số dòng code.

## 7. `cache` và `replay`: tránh giữ lịch sử vô hạn

### Cache một lần thực thi

```java
Mono<Product> product = fetchProduct(productId).cache();
```

Với `Mono.cache()`, kết quả terminal được cache để subscriber sau có thể nhận lại mà không gọi upstream lại. Điều này có thể hữu ích cho một kết quả immutable, dùng chung và có chính sách thời gian sống phù hợp. Tuy nhiên, nếu dữ liệu phụ thuộc user, quyền truy cập, tenant hoặc thay đổi theo thời gian, cache dùng chung có thể trả nhầm dữ liệu hoặc giữ thông tin quá lâu.

Với `Flux`:

```java
Flux<Event> recent = eventSource.cache(100);
```

Overload giới hạn lịch sử giữ số phần tử gần nhất theo giới hạn. Ngược lại, `cache()` không giới hạn lịch sử có thể giữ toàn bộ phần tử đã phát. Với stream vô hạn, điều này có thể dẫn đến heap tăng không giới hạn.

### Replay có giới hạn

```java
ConnectableFlux<Event> replayed =
        eventSource.replay(50);
```

`replay(50)` giữ một cửa sổ tối đa 50 phần tử cho subscriber đến sau. Có thể kết hợp `autoConnect` hoặc `refCount` theo lifecycle cần thiết. Giới hạn theo số phần tử không phải giới hạn byte: 50 object lớn vẫn có thể chiếm nhiều bộ nhớ.

### Chọn TTL và phạm vi cache

Trước khi cache, xác định:

- Dữ liệu có thay đổi không? Khi nào hết hạn?
- Có được chia sẻ giữa user/tenant không?
- Kết quả có chứa token, PII hoặc dữ liệu nhạy cảm không?
- Số phần tử và kích thước mỗi phần tử là bao nhiêu?
- Cache được giữ đến terminal hay trong thời gian TTL?
- Khi lỗi, có cache lỗi hay cho phép subscriber sau thử lại?

Cache không chỉ là tối ưu hiệu năng; nó thay đổi ngữ nghĩa thực thi, số lần gọi upstream, thời điểm quan sát dữ liệu và thời gian giữ dữ liệu trong bộ nhớ.

## 8. Dùng `Sinks.Many` làm nguồn hot

`Sinks.Many<T>` là API chủ động phát dữ liệu vào một `Flux`. Ứng dụng có thể giữ sink trong bean và gọi `tryEmitNext` khi có sự kiện.

### Các kiểu sink thường gặp

| Loại sink | Hành vi chính | Trường hợp phù hợp |
|---|---|---|
| `many().unicast()` | Chỉ một subscriber; có thể buffer trước khi subscriber đến theo cấu hình | Một consumer sở hữu stream |
| `many().multicast().onBackpressureBuffer()` | Nhiều subscriber, phối hợp demand và buffer | Broadcast có xử lý backpressure |
| `many().multicast().directAllOrNothing()` | Nếu một subscriber không đủ demand, emission có thể thất bại cho tất cả | Cần phát đồng bộ cho mọi người nhận hoặc báo lỗi |
| `many().multicast().directBestEffort()` | Phát cho subscriber có demand; subscriber chậm có thể bỏ lỡ emission | Telemetry/notification cho phép mất event ở subscriber chậm |
| `many().replay().limit(n)` | Subscriber mới nhận lại tối đa n sự kiện gần nhất | Snapshot/history ngắn hạn |

Lựa chọn sink là quyết định chính sách dữ liệu. Nếu mất một sự kiện là không chấp nhận được, `directBestEffort` không phù hợp; cần buffer, retry, durable broker hoặc lưu trữ sự kiện.

### Ví dụ phát và nhận sự kiện

```java
Sinks.Many<String> sink =
        Sinks.many().multicast().directBestEffort();

Flux<String> events = sink.asFlux();

Disposable subscription = events.subscribe(
        value -> System.out.println("received=" + value),
        error -> System.err.println("error=" + error)
);

Sinks.EmitResult result = sink.tryEmitNext("order-created");

if (result.isFailure()) {
    System.err.println("event not delivered: " + result);
}

subscription.dispose();
```

Đây là snippet có import `reactor.core.Disposable`, `reactor.core.publisher.Flux` và `reactor.core.publisher.Sinks`. `tryEmitNext` trả `EmitResult` để caller xử lý trường hợp không thể phát; không được bỏ qua kết quả nếu event quan trọng.

Một số lý do thất bại thường gặp:

- Không có subscriber trong loại sink yêu cầu subscriber hiện diện.
- Subscriber không có demand ở sink áp backpressure.
- Buffer đầy.
- Gọi emission đồng thời không được serialize theo contract; có thể nhận `FAIL_NON_SERIALIZED`.
- Sink đã complete/error hoặc bị dispose.

Không gọi `tryEmitNext` rồi giả định event chắc chắn đã tới tất cả client. Chọn cách xử lý lỗi theo nghiệp vụ: retry có kiểm soát, queue durable, báo overload hoặc bỏ qua có chủ đích.

### Đồng thời nhiều producer

Các `Sinks` an toàn phát hiện concurrent access và báo kết quả lỗi phù hợp. Nếu nhiều thread cùng phát, cần serialize producer hoặc dùng cơ chế retry/serialization có kiểm soát. Tránh dùng `Sinks.unsafe()` trừ khi ứng dụng đã bảo đảm tuyệt đối chỉ một producer phát tại một thời điểm.

## 9. Subscriber chậm, backpressure và buffer

Khi một hot source phát nhanh hơn tốc độ tiêu thụ, phải quyết định điều gì xảy ra với subscriber chậm:

1. **Buffer**: giữ sự kiện chờ subscriber. Cần giới hạn kích thước và hành vi khi đầy.
2. **Drop**: bỏ sự kiện không thể giao kịp. Phù hợp telemetry không cần đầy đủ.
3. **Latest**: chỉ giữ giá trị mới nhất. Phù hợp trạng thái hiện tại như nhiệt độ/giá hiển thị.
4. **Fail**: phát lỗi hoặc từ chối emission khi không đáp ứng demand.
5. **Durable queue**: lưu ngoài heap (broker/database/log) nếu sự kiện phải được giao lại sau restart.

Không có chính sách nào đúng cho mọi hệ thống. Chọn theo ý nghĩa dữ liệu:

- Số đo CPU mỗi 100 ms có thể chấp nhận drop.
- Thông báo “đơn hàng đã thanh toán” thường cần lưu bền vững và giao lại.
- Giá trị dashboard có thể dùng latest.
- Stream lớn cần giới hạn buffer, số subscriber và kích thước payload.

**Backpressure không đồng nghĩa với lưu trữ vô hạn.** Một subscriber không request dữ liệu sẽ không thể buộc hệ thống giữ mọi sự kiện mãi mãi. Buffer phải có giới hạn hoặc có chính sách từ chối/drop.

## 10. Hủy subscription và quản lý `Disposable`

Mỗi lần gọi `.subscribe(...)` thường trả về `Disposable`. Đối với nguồn sống lâu, ứng dụng phải giữ handle để dừng đúng lúc:

```java
Disposable subscription = source.subscribe(
        this::handleEvent,
        this::handleError
);

// Khi bean/request không còn sở hữu stream:
subscription.dispose();
```

Nếu không giữ `Disposable`, ứng dụng có thể mất khả năng hủy subscription thủ công. Một nguồn interval hoặc hot event stream vẫn có thể tiếp tục phát, giữ callback và tham chiếu tới object đã không còn được dùng.

### Nhiều subscription: `Disposable.Composite`

```java
Disposable.Composite subscriptions = Disposables.composite();

subscriptions.add(sourceA.subscribe(this::handleA));
subscriptions.add(sourceB.subscribe(this::handleB));

// Khi component dừng:
subscriptions.dispose();
```

Cần import `reactor.core.Disposable` và `reactor.core.Disposables`. Composite giúp gom lifecycle của nhiều subscription do cùng một component sở hữu. Không chia sẻ một composite toàn cục giữa các request độc lập nếu không có thiết kế ownership rõ ràng.

### `dispose()` không giống complete

- `dispose()` yêu cầu hủy subscription.
- `onComplete` là nguồn báo đã hoàn tất thành công.
- `onError` là nguồn báo lỗi.
- `doFinally` có thể quan sát `SignalType.CANCEL` khi subscriber hủy.

Đối với publisher đã complete/error, dispose không phát một terminal mới. Với nguồn bất đồng bộ, dispose cũng không bảo đảm một tác vụ blocking bên ngoài lập tức ngừng nếu API đó không hỗ trợ cancellation.

## 11. Các kiểu rò rỉ thường gặp

### 11.1. Subscribe trong controller rồi trả một publisher khác

Sai:

```java
@GetMapping("/events")
Flux<Event> events() {
    eventSource.subscribe(this::process);
    return Flux.empty();
}
```

Controller đã tạo một subscription tách rời khỏi vòng đời HTTP response, rồi trả `Flux.empty()`. Khi client ngắt kết nối, subscription thủ công không tự động bị hủy bởi WebFlux; nó có thể tiếp tục chạy và giữ tài nguyên.

Đúng:

```java
@GetMapping("/events")
Flux<Event> events() {
    return eventSource;
}
```

Để WebFlux sở hữu subscription của response. Khi client cancel/disconnect, cancellation có thể truyền ngược lên publisher theo contract.

### 11.2. Subscribe thủ công mà không giữ Disposable

```java
source.subscribe(this::handle);
```

Nếu đây là subscription sống lâu do component khởi tạo, giữ `Disposable` và dispose khi component dừng. Nếu chỉ muốn biến đổi dữ liệu, trả publisher và compose operator; đừng tạo subscription lồng nhau.

### 11.3. `autoConnect` với nguồn vô hạn

```java
Flux<Long> clock = Flux.interval(Duration.ofSeconds(1))
        .publish()
        .autoConnect(1);
```

Sau subscriber đầu tiên, nguồn bắt đầu chạy. Nếu mọi subscriber rời đi nhưng upstream không complete, `autoConnect` không tự ref-count về 0; timer có thể tiếp tục chạy. Dùng `refCount` nếu lifecycle phải gắn với người quan sát, hoặc quản lý connection `Disposable` rõ ràng.

### 11.4. Cache/replay không giới hạn

```java
Flux<Event> dangerous = eventSource.cache();
```

Với stream dài hoặc vô hạn, cache có thể giữ toàn bộ phần tử đã phát trong heap. Dùng history limit/TTL hoặc external store khi cần lịch sử lâu dài.

### 11.5. Không hủy nguồn khi request hết hạn

Một request fan-out nhiều upstream có thể timeout nhưng công việc còn tiếp tục nếu subscription bị tách ra bằng `.subscribe()` thủ công, hoặc thư viện nguồn không hỗ trợ cancellation. Giữ công việc trong cùng pipeline; cấu hình timeout ở client/driver và quan sát cancel.

### 11.6. Giữ tham chiếu tới subscriber hoặc request context

Hot source sống lâu mà giữ callback/closure có thể giữ luôn service, request context, buffer hoặc dữ liệu nhạy cảm. Tránh đưa object request ngắn hạn vào cấu trúc singleton; chỉ lưu dữ liệu cần thiết, và gỡ listener/subscription khi kết thúc.

## 12. Spring WebFlux: thiết kế stream broadcast cho HTTP

Một bean có thể cung cấp nguồn sự kiện dùng chung:

```java
@Component
class EventHub {
    private final Sinks.Many<Event> sink =
            Sinks.many().multicast().onBackpressureBuffer(256);

    Flux<Event> events() {
        return sink.asFlux();
    }

    Sinks.EmitResult publish(Event event) {
        return sink.tryEmitNext(event);
    }
}
```

Đây là snippet cấu trúc, cần định nghĩa `Event` và xử lý kết quả `EmitResult` ở nơi gọi. Buffer 256 là giới hạn theo **số phần tử**, không phải byte; cần chính sách khi đầy và metric cho overflow. Với dữ liệu quan trọng, một sink trong bộ nhớ không thay thế durable message broker.

Controller có thể trả SSE:

```java
@GetMapping(value = "/events", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
Flux<ServerSentEvent<Event>> events() {
    return eventHub.events()
            .map(event -> ServerSentEvent.builder(event).build());
}
```

Đây là snippet cần `eventHub`, `MediaType`, `ServerSentEvent`, `GetMapping` và class `Event`. Spring quản lý subscription gắn với response. Khi client disconnect, upstream cancellation có thể giảm subscriber count của sink/share nếu pipeline được compose đúng.

### Bảo vệ dữ liệu giữa tenant/user

Không chia sẻ một stream đã lọc theo request-specific security context một cách thiếu kiểm soát. Nếu nhiều người dùng cùng subscribe một publisher hot, hãy xác định rõ:

- Phân vùng sink theo tenant/topic hoặc áp dụng kiểm tra quyền ở mỗi subscriber.
- Không đưa token hoặc dữ liệu cá nhân vào cache/replay dùng chung.
- Đảm bảo subscriber mới không nhận lịch sử thuộc tenant khác.
- Có giới hạn số subscriber, buffer và tốc độ phát theo tenant.
- Xác định cách revoke quyền và dispose subscription khi session hết hạn.

Một publisher được `share()` có upstream subscription dùng chung; không nên giả định mỗi subscriber sẽ có một lần thực thi upstream riêng để tự động áp `Reactor Context` riêng biệt. Đặt xác thực/authorization ở ranh giới đúng và kiểm thử với nhiều subscriber khác nhau.

## 13. `doFinally` đặt trước hay sau `share`?

Vị trí operator ảnh hưởng việc callback chạy theo từng subscriber hay theo subscription upstream được chia sẻ:

```java
Flux<Event> source = eventSource
        .doFinally(signal -> logUpstreamEnd(signal))
        .share();

Flux<Event> perSubscriberObserved = eventSource
        .share()
        .doFinally(signal -> logSubscriberEnd(signal));
```

- `doFinally` **trước** `share()` quan sát lifecycle của subscription upstream dùng chung. Khi subscriber đầu tiên tham gia, upstream được subscribe; khi shared source bị hủy/terminal, callback tương ứng chạy.
- `doFinally` **sau** `share()` quan sát lifecycle của từng subscriber downstream. Mỗi subscriber có thể có `CANCEL`, `ON_COMPLETE` hoặc `ON_ERROR` riêng.

Điều này giúp phân biệt “một client rời stream” với “toàn bộ nguồn dùng chung đã dừng”. Khi debug subscriber leak, ghi nhận cả hai tầng và đừng đếm upstream callback như số người nhận.

## 14. Kiểm thử đăng ký muộn, replay và cancellation

Một bài test tốt cần kiểm soát thời điểm subscribe và phát event, tránh dựa vào `Thread.sleep`. Dùng `Sinks` để điều khiển sự kiện đồng bộ và `StepVerifier` để xác nhận terminal/cancel.

### Dự án Maven Java 17+

Cấu trúc:

```text
reactor-subscriber-lifecycle/
├── pom.xml
└── src/test/java/edu/demo/SubscriberLifecycleTest.java
```

`pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>edu.demo</groupId>
    <artifactId>reactor-subscriber-lifecycle</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-core</artifactId>
            <version>3.6.6</version>
        </dependency>
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-test</artifactId>
            <version>3.6.6</version>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>5.10.2</version>
            <scope>test</scope>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.2.5</version>
            </plugin>
        </plugins>
    </build>
</project>
```

`src/test/java/edu/demo/SubscriberLifecycleTest.java`:

```java
package edu.demo;

import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;

import org.junit.jupiter.api.Test;
import reactor.core.Disposable;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Sinks;
import reactor.core.publisher.SignalType;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;

class SubscriberLifecycleTest {

    @Test
    void coldDeferStartsOneExecutionPerSubscriber() {
        AtomicInteger executions = new AtomicInteger();

        Flux<Integer> cold = Flux.defer(() -> {
            executions.incrementAndGet();
            return Flux.just(1, 2, 3);
        });

        StepVerifier.create(cold)
                .expectNext(1, 2, 3)
                .verifyComplete();

        StepVerifier.create(cold)
                .expectNext(1, 2, 3)
                .verifyComplete();

        assertEquals(2, executions.get());
    }

    @Test
    void lateSubscriberToHotMulticastMissesPastEvents() {
        Sinks.Many<Integer> sink =
                Sinks.many().multicast().directBestEffort();

        List<Integer> early = new ArrayList<>();
        Disposable first = sink.asFlux().subscribe(early::add);

        assertEquals(Sinks.EmitResult.OK, sink.tryEmitNext(1));
        first.dispose();

        List<Integer> late = new ArrayList<>();
        Disposable second = sink.asFlux().subscribe(late::add);

        assertEquals(Sinks.EmitResult.OK, sink.tryEmitNext(2));
        second.dispose();
        sink.tryEmitComplete();

        assertEquals(List.of(1), early);
        assertEquals(List.of(2), late);
    }

    @Test
    void replaySinkGivesLateSubscriberRecentHistory() {
        Sinks.Many<Integer> replay = Sinks.many().replay().limit(2);

        assertEquals(Sinks.EmitResult.OK, replay.tryEmitNext(1));
        assertEquals(Sinks.EmitResult.OK, replay.tryEmitNext(2));
        assertEquals(Sinks.EmitResult.OK, replay.tryEmitNext(3));
        assertEquals(Sinks.EmitResult.OK, replay.tryEmitComplete());

        StepVerifier.create(replay.asFlux())
                .expectNext(2, 3)
                .verifyComplete();
    }

    @Test
    void cacheRunsColdSourceOnceAndReplaysLastTwoValues() {
        AtomicInteger executions = new AtomicInteger();

        Flux<Integer> cached = Flux.defer(() -> {
            executions.incrementAndGet();
            return Flux.just(1, 2, 3);
        }).cache(2);

        StepVerifier.create(cached)
                .expectNext(1, 2, 3)
                .verifyComplete();

        StepVerifier.create(cached)
                .expectNext(2, 3)
                .verifyComplete();

        assertEquals(1, executions.get());
    }

    @Test
    void sharedUpstreamCancelsWhenLastSubscriberLeaves() {
        AtomicReference<SignalType> upstreamEnd = new AtomicReference<>();

        Flux<Long> shared = Flux.<Long>never()
                .doFinally(upstreamEnd::set)
                .share();

        Disposable first = shared.subscribe();
        Disposable second = shared.subscribe();

        first.dispose();
        assertEquals(null, upstreamEnd.get());

        second.dispose();
        assertEquals(SignalType.CANCEL, upstreamEnd.get());
    }

    @Test
    void subscriberCancellationIsNotCompletion() {
        AtomicReference<SignalType> finalSignal = new AtomicReference<>();

        StepVerifier.create(
                        Flux.<Integer>never()
                                .doFinally(finalSignal::set))
                .expectSubscription()
                .thenCancel()
                .verify();

        assertEquals(SignalType.CANCEL, finalSignal.get());
    }
}
```

Chạy trong thư mục dự án:

```bash
mvn test
```

Khi dependency được tải và các assertion đúng, **6 test PASS**. Bài test xác nhận:

1. `defer` thực thi supplier một lần trên mỗi subscriber.
2. Subscriber hot đến muộn không nhận lại event đã phát trước đó.
3. Replay sink giữ hai sự kiện gần nhất cho subscriber muộn.
4. `cache(2)` chỉ thực thi nguồn một lần và phát lại hai phần tử cuối ở subscription sau.
5. Shared upstream chỉ bị cancel khi subscriber cuối cùng rời đi.
6. `cancel` được quan sát là `SignalType.CANCEL`, không phải complete.

Các test dùng sink phát đồng bộ nên không cần `Thread.sleep`. Trong ứng dụng thật, cần thêm integration test cho connection pool, broker, client HTTP và shutdown lifecycle.

## 15. Checklist chống subscriber leak trong ứng dụng

Trước khi đưa stream sống lâu vào production:

- Có biết ai tạo subscription và ai sở hữu `Disposable` không?
- Subscription có bị tách khỏi HTTP request bằng `.subscribe()` thủ công không?
- Khi client disconnect, cancellation có truyền về upstream không?
- Nếu dùng `autoConnect`, ai sẽ dispose connection?
- Nếu dùng `share/refCount`, điều gì xảy ra khi subscriber cuối rời đi?
- Cache/replay có giới hạn số phần tử hoặc TTL không?
- Nguồn hot có chính sách cho subscriber chậm và overflow không?
- Event sink có giới hạn số subscriber và buffer không?
- Callback có giữ request/session/object lớn quá lâu không?
- Có metrics cho subscriber count, active connections, queue, cancellation và lỗi emission không?
- Có xử lý shutdown để dispose subscription, scheduler, connection và sink không?
- Có kiểm thử late subscription, repeated subscription, cancellation, reconnect và lỗi upstream không?

### Dấu hiệu nhận biết rò rỉ

- Số subscriber hoặc connection tăng theo thời gian nhưng không giảm sau khi client rời đi.
- Thread/timer tiếp tục hoạt động sau khi component đã shutdown.
- Heap tăng theo số sự kiện đã phát do replay/cache không giới hạn.
- Callback còn giữ tham chiếu tới request, session hoặc bean không còn cần thiết.
- Một client disconnect nhưng downstream HTTP call hoặc database query vẫn tiếp tục.
- Các event phát ra sink thường xuyên trả `FAIL_OVERFLOW` hoặc `FAIL_NON_SERIALIZED` mà ứng dụng bỏ qua.
- Một nguồn `Flux.never()`/`interval()` không có chủ sở hữu lifecycle rõ ràng.

## 16. Lỗi phổ biến và cách sửa

| Lỗi | Hậu quả | Cách sửa |
|---|---|---|
| Nghĩ hot source replay toàn bộ lịch sử | Subscriber muộn bỏ lỡ event | Chọn replay/cache/durable log có giới hạn |
| Subscribe một WebClient Mono hai lần mà không biết | Gửi hai HTTP request | Dùng một subscription được compose hoặc cache có TTL nếu ngữ nghĩa phù hợp |
| Dùng `Mono.just(expensiveCall())` | Call chạy ngay khi tạo publisher | Dùng publisher lazy phù hợp (`defer`/`fromCallable`) |
| Gọi `.subscribe()` trong controller | Subscription tách khỏi HTTP lifecycle | Trả `Mono`/`Flux` cho Spring |
| Bỏ `Disposable` của subscription lâu dài | Không thể dừng nguồn có kiểm soát | Lưu và dispose theo lifecycle component |
| `autoConnect` trên nguồn vô hạn nhưng không quản lý connection | Nguồn tiếp tục chạy khi không còn subscriber | Dùng refCount hoặc quản lý Disposable connection |
| Dùng `cache()` không giới hạn trên Flux vô hạn | Heap tăng liên tục | `cache(n)`, replay giới hạn, TTL hoặc durable store |
| Dùng `directBestEffort` cho event không được phép mất | Subscriber chậm có thể không nhận event | Dùng buffer/durable broker và xử lý overflow |
| Chia sẻ publisher có dữ liệu phụ thuộc tenant | Rò dữ liệu giữa người dùng | Phân vùng stream và kiểm tra quyền ở đúng ranh giới |
| Cho rằng cancel luôn dừng tác vụ vật lý | SDK blocking vẫn có thể tiếp tục | Timeout/cancel ở driver, giới hạn queue và giám sát |
| Dùng `doFinally` như cleanup async | Terminal không đợi cleanup publisher | Dùng `usingWhen` hoặc lifecycle manager thích hợp |
| Không kiểm tra `EmitResult` | Mất event hoặc lỗi cạnh tranh bị bỏ qua | Xử lý từng kết quả phát theo chính sách |

## 17. Bài tập tự kiểm tra

**Bài 1.** Một `WebClient` tạo `Mono<Customer>`. Hai controller/service cùng subscribe một publisher đó. Có thể phát sinh bao nhiêu HTTP request?

**Đáp án:** Thông thường hai subscription cold tạo hai HTTP request độc lập. Nếu cần chia sẻ một kết quả, có thể cache/coalesce, nhưng phải xem TTL, quyền truy cập và dữ liệu có thay đổi không.

**Bài 2.** Hot multicast đã phát `E1`, `E2`, `E3`; subscriber B đăng ký sau E3. B nhận gì?

**Đáp án:** Không replay thì B chỉ nhận sự kiện phát sau khi đăng ký. Muốn B thấy lịch sử, nguồn phải có replay/cache hoặc event store.

**Bài 3.** `publish().autoConnect(1)` đang chia sẻ `Flux.interval`. Subscriber cuối dispose. Timer có chắc dừng không?

**Đáp án:** Không. `autoConnect` không ref-count về 0; connection đã mở cần được quản lý riêng. Dùng `refCount` nếu muốn dừng upstream khi không còn subscriber.

**Bài 4.** Vì sao `Flux.cache()` có thể gây OOM trên nguồn vô hạn?

**Đáp án:** Cache không giới hạn lịch sử giữ phần tử đã phát để subscriber muộn nhận lại. Dùng history limit/TTL hoặc lưu trữ ngoài heap.

**Bài 5.** Vì sao controller không nên gọi `eventSource.subscribe()` rồi trả `Flux.empty()`?

**Đáp án:** Subscription tự tạo không gắn với HTTP response. Client disconnect không tự hủy subscription đó; stream có thể tiếp tục giữ tài nguyên.

**Bài 6.** Một sink trả `FAIL_NON_SERIALIZED`. Điều đó có thể báo hiệu điều gì?

**Đáp án:** Nhiều producer đang cố phát đồng thời mà không được serialize theo contract của sink. Cần serialize producer hoặc dùng cơ chế phát có xử lý retry/lock phù hợp.

**Bài 7.** Đặt `doFinally` trước `share()` và sau `share()` khác nhau ra sao?

**Đáp án:** Trước `share()` quan sát vòng đời upstream dùng chung; sau `share()` quan sát vòng đời từng subscriber downstream. Hai tầng có thể kết thúc ở thời điểm khác nhau.

## 18. Ghi nhớ

- **Cold** thường khởi động một lần thực thi cho mỗi subscription; **hot** phát sự kiện độc lập với subscriber cụ thể.
- **Late subscriber** chỉ nhận lịch sử nếu nguồn có replay/cache; multicast trực tiếp thường chỉ chuyển tiếp sự kiện mới.
- `share/refCount` gắn vòng đời upstream với subscriber; `autoConnect` kết nối sau ngưỡng nhưng không tự ngắt khi subscriber về 0.
- `cache/replay` thay đổi ngữ nghĩa số lần chạy và thời gian giữ dữ liệu; luôn đặt giới hạn phù hợp.
- Mọi subscription sống lâu cần **owner và cơ chế dispose**. Controller WebFlux nên trả publisher để framework quản lý vòng đời HTTP.
- Hot stream dùng chung phải có chính sách tenant/security, backpressure, overflow, shutdown và quan sát subscriber.

Khi có đăng ký muộn hoặc nghi ngờ rò rỉ, hãy lần theo ba mốc: **nguồn bắt đầu lúc nào, subscriber được gắn vào lúc nào, và ai hủy kết nối khi không còn người nhận**.

## Tài liệu chính thức

- Project Reactor, **Hot Versus Cold**: https://projectreactor.io/docs/core/3.6.6/reference/advancedFeatures/reactor-hotCold.html
- Project Reactor, **ConnectableFlux / publish, replay, refCount, autoConnect**: https://projectreactor.io/docs/core/3.6.6/reference/advancedFeatures/advanced-broadcast-multiple-subscribers-connectableflux.html
- Project Reactor, **Sinks**: https://projectreactor.io/docs/core/3.6.6/reference/coreFeatures/sinks.html
- Project Reactor, **Flux API** (`cache`, `share`, `publish`, `replay`, `refCount`): https://projectreactor.io/docs/core/3.6.6/api/reactor/core/publisher/Flux.html
- Project Reactor, **Disposable API**: https://projectreactor.io/docs/core/3.6.6/api/reactor/core/Disposable.html
- Project Reactor, **Testing with StepVerifier**: https://projectreactor.io/docs/core/3.6.6/reference/testing.html
- Spring Framework, **WebFlux**: https://docs.spring.io/spring-framework/reference/web/webflux.html