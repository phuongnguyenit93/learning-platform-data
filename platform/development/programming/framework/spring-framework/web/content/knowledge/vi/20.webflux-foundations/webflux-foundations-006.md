# map, flatMap, kết hợp kết quả và lựa chọn mức đồng thời trong Spring WebFlux

> **Phạm vi:** Reactor Core (`Mono`, `Flux`, Reactive Streams), Spring WebFlux trên Spring Framework 6.2.x / Spring Boot 3.5.x với Java 17+. Trọng tâm gồm: **biến đổi dữ liệu bằng map/flatMap**, **ghép nhiều publishers bằng zip/merge/concat/combineLatest**, và **chọn concurrency/prefetch/backpressure/order phù hợp** khi gọi WebClient hoặc reactive repository. Ví dụ chạy với WebFlux server không block HTTP event loop, có cURL và WebTestClient/StepVerifier. Nếu đang dùng Spring Boot 4.x/Spring Framework 7.x, phải đối chiếu starter/test package tương ứng trước khi sao chép dependency.

## 1. Tình huống thực tế và sơ đồ

Một hệ thống nhận danh sách product IDs, cần gọi dịch vụ catalog rồi trả JSON. Khi tải một profile tổng hợp, cần kết hợp account và settings từ hai services độc lập.

```text
GET /api/items
    |
Flux<Integer> ids
    |
    + map(id -> key): giá trị -> giá trị mới ngay
    |
    + flatMap(id -> Mono<Item>, concurrency):
    |                 |
    |           nhiều I/O in-flight
    |                 |
    |         Flux<Item> (có thể đảo thứ tự)
    |
    + flatMapSequential(id -> Mono<Item>, n):
    |                 |
    |         Flux<Item> giữ thứ tự đầu vào
    |
    + concatMap(id -> Mono<Item>):
                      |
             mỗi inner chạy tuần tự

GET /api/profile/{id}
    |
    +--> Mono<Account> -------+
    |                         +--> Mono.zip(...) --> Mono<Profile>
    +--> Mono<Settings> ------+
```

**Câu hỏi phải giải quyết trước khi chọn operator:** mapper trả giá trị thuần hay Publisher? Các requests độc lập hay phụ thuộc nhau? Có phải giữ thứ tự **output**, hay cả thứ tự **side effects**? Downstream chịu được bao nhiêu request đồng thời? Có thể mất một item hay mọi item đều bắt buộc?

## 2. Nền tảng: Mono, Flux và tín hiệu

`Mono<T>` phát 0 hoặc 1 phần tử rồi hoàn tất, hoặc kết thúc bằng lỗi. `Flux<T>` phát 0 đến N phần tử (có thể vô hạn), hoàn tất hoặc lỗi. Một reactive pipeline thường **lazy**; operators như `map` và `flatMap` xây dựng mô tả tính toán, chưa thực thi cho đến khi có subscription. Spring WebFlux subscribe Publisher do controller trả trong response lifecycle.

Reactive Streams có các tín hiệu/khái niệm:
- `onSubscribe`: trao Subscription;
- `request(n)`: consumer yêu cầu số phần tử;
- `onNext`: một phần tử, không được null;
- `onComplete`: hoàn tất thành công;
- `onError`: lỗi terminal;
- `cancel`: hủy subscription.

Sau terminal `onComplete` hoặc `onError`, publisher không tiếp tục phát các phần tử bình thường. Cancellation từ browser/disconnected client có thể lan ngược upstream, tùy operator/source/HTTP connector.

```java
Flux<Integer> source = Flux.just(1, 2, 3);
Flux<Integer> output = source.map(x -> x * 10);
// Chưa gọi subscribe: các tác vụ thường chưa chạy.
```

Trong HTTP controller WebFlux: **return `Flux` hoặc `Mono`** để Spring điều phối subscription, không tự gọi `.subscribe()` ở handler và trả `null`. Trong unit tests có thể gọi `StepVerifier.create(output)` để kiểm tra tín hiệu mà không viết `block()`.

### 2.1. Cold vs hot source

`Flux.range(...)` và `Mono.defer(...)` thường là cold: mỗi subscription có thể phát lại hoặc thực hiện lại logic. Một hot stream có thể chia sẻ nguồn sự kiện đã và đang chạy. Concurrency trên `flatMap` giới hạn **số inner subscriptions của instance operator**, không tự hạn chế toàn bộ event rate của hot source dùng chung, connection pool của service hoặc tổng inbound HTTP requests.

## 3. map: một phần tử đầu vào thành một giá trị

`map(Function<T,R>)` thực hiện chuyển đổi **đồng bộ** khi một `onNext` tới:

```java
Flux<String> labels = Flux.just(1, 2, 3)
        .map(id -> "item-" + (id * 10));
```

Giá trị của `labels.collectList()` khi được subscribe tương đương:

```text
[item-10, item-20, item-30]
```

`map` thích hợp cho DTO mapping, chuẩn hóa string, tính toán giá trị thuần. Nó không tự mở thread hay biến logic blocking thành non-blocking. Mapper không được trả `null`; trả null là lỗi reactive contract.

**Sai trường hợp mapper trả một Mono:**

```java
Mono<Mono<User>> nested =
        Mono.just(42).map(id -> fetchUserReactive(id));
```

Nếu `fetchUserReactive(int)` trả `Mono<User>`, bên ngoài vẫn là Mono chứa một Mono. Muốn nhận `Mono<User>`, dùng `flatMap`:

```java
Mono<User> flattened =
        Mono.just(42).flatMap(id -> fetchUserReactive(id));
```

Hai đoạn này là snippets, cần method `fetchUserReactive` và class `User` được định nghĩa trước.

## 4. flatMap: tạo Publisher mới rồi làm phẳng

`Mono.flatMap(Function<T,Mono<R>>)` hợp với một request cần kết quả bất đồng bộ từ một giá trị. `Flux.flatMap(Function<T,Publisher<R>>)` hợp với nhiều items, có thể tạo nhiều inner publishers đang active.

```java
Mono<User> user = userIdMono
        .flatMap(id -> userRepository.findById(id));

Flux<Product> products = Flux.fromIterable(productIds)
        .flatMap(id -> webClient.get()
                .uri("/products/{id}", id)
                .retrieve()
                .bodyToMono(Product.class), 4);
```

Snippets cần `userIdMono`, `userRepository`, `productIds`, `webClient`, DTO. Ưu điểm là nhiều network calls non-blocking có thể **overlap latency**; nhược điểm: **không bảo đảm thứ tự output theo IDs**.

### 4.1. flatMap không tự tạo thread

Ví dụ:

```java
Flux<Integer> a = Flux.range(1, 4)
        .flatMap(i -> Mono.just(i * 10));

Flux<Integer> b = Flux.range(1, 4)
        .flatMap(i -> Mono.delay(Duration.ofMillis(100))
                .map(ignore -> i * 10), 2);
```

Ví dụ A phần lớn vẫn chạy đồng bộ trong subscription; B có timer async. `flatMap` là toán tử **flatten/merge**, không phải lệnh `new Thread(...)`.

Với nguồn blocking JDBC:

```java
// Anti-pattern trên WebFlux event loop.
return Flux.fromIterable(ids)
        .flatMap(id -> Mono.fromCallable(
                () -> jdbcRepository.findById(id)));
```

Nếu subscribe vào blocking Callable trên luồng hiện tại, event loop có thể vẫn bị block. Bridge tạm thời:

```java
return Flux.fromIterable(ids)
        .flatMap(id -> Mono.fromCallable(
                        () -> jdbcRepository.findById(id))
                .subscribeOn(Schedulers.boundedElastic()), 4);
```

Đoạn sau chuyển blocking call sang boundedElastic, **không biến JDBC thành reactive database driver**. Cần giới hạn số tasks, thread/queue, DB pool, và cân nhắc Spring MVC hoặc R2DBC tùy kiến trúc.

### 4.2. flatMapMany cho Mono đầu vào

Nếu từ một account ta lấy nhiều orders:

```java
Flux<Order> orders = accountMono
        .flatMapMany(account -> orderRepository.findByAccount(account.id()));
```

Ở đây repository trả `Flux<Order>`; `Mono.flatMapMany` chuyển từ 0..1 sang 0..N. Nếu chỉ `map(account -> Flux<Order>)`, kết quả là `Mono<Flux<Order>>`, không phải chuỗi orders.

### 4.3. flatMap khác map khi dữ liệu trống

Với `Mono.empty()`, không có `onNext` để gọi mapper của `map` hay `flatMap`. Muốn xử lý absence có chủ đích, dùng `switchIfEmpty(...)` hoặc `defaultIfEmpty(...)` nếu value hợp lệ, không mặc định kết luận “mapper bị lỗi”.

## 5. flatMap, flatMapSequential, concatMap: chọn theo thứ tự

```java
Flux<Item> fastest = ids.flatMap(this::fetch, 3);
Flux<Item> ordered = ids.flatMapSequential(this::fetch, 3);
Flux<Item> serial = ids.concatMap(this::fetch);
```

| Tiêu chí | flatMap(mapper,3) | flatMapSequential(mapper,3) | concatMap(mapper) |
| --- | --- | --- | --- |
| Có thể subscribe nhiều inner sớm | Có | Có | Không, các inner nối tuần tự |
| Tối đa inner active theo ví dụ | 3 | 3 | 1 |
| Output theo thứ tự input | Không bảo đảm | **Có** | **Có** |
| Interleave giữa giá trị các inners | Có | Không trong output theo source order | Không |
| Buffer khi kết quả sau đến trước | Không cần reorder theo source | Có thể phải queue để chờ inner trước | Không overlap async inner |
| Khi nào dùng | I/O độc lập, ưu tiên throughput | Giữ thứ tự output và overlap I/O | Side effects phải lần lượt |

**Điểm dễ nhầm:** `flatMapSequential` đảm bảo thứ tự **phát ra kết quả**, chứ các inner operations/side effects vẫn có thể diễn ra **đồng thời**. Nếu thao tác write A phải hoàn thành trước khi bắt đầu write B trên cùng aggregate, hãy dùng `concatMap` hoặc reactive sequencing thích hợp; vẫn cần DB transaction/versioning để bảo vệ tranh chấp từ **nhiều HTTP requests khác nhau**.

### 5.1. Ví dụ head-of-line

Input IDs [1,2,3], inner ID=1 tốn 300ms, ID=2 80ms, ID=3 40ms:
- `flatMap` có thể phát 3,2,1.
- `flatMapSequential` có thể hoàn thành 3,2 trước nhưng **giữ trong queue** rồi phát 1,2,3.
- `concatMap` đợi 1 hoàn tất mới đăng ký 2, sau đó mới 3.

Thời điểm/phân phối cụ thể còn phụ thuộc scheduler và nguồn. Test không nên assert một thứ tự fixed cho `flatMap`. Với `flatMapSequential` ở concurrency cao và item lớn, reorder queue làm tăng memory và time-to-first-byte khi inner đầu chậm.

### 5.2. Vì sao không sort sau flatMap?

`flatMap(...).sort(comparator)` hoặc `collectList().map(list -> sort(...))` phải gom dữ liệu đến khi source hoàn tất, không thích hợp với stream vô hạn và tạo memory theo kích thước dữ liệu. `flatMapSequential` dùng source-order semantics thay vì sort toàn bộ, dù vẫn có buffer cho inner đến sớm.

### 5.3. map giữ order không?

`Flux.map` thực hiện chuyển đổi lần lượt các `onNext` do upstream phát, không tự reorder nguồn. Nếu upstream đã bị reorder do `flatMap` trước đó, `map` **không khôi phục** thứ tự ban đầu.

## 6. concurrency: số inner đang được subscribe, không phải số threads

`Flux.flatMap(mapper, concurrency)` giới hạn số inner publishers đang active của pipeline đó. Nó không tự cấp thread, không giới hạn mọi callers trên server, và không tương đương HTTP connection pool max size.

Ví dụ:

```java
Flux<Product> result = Flux.fromIterable(ids)
        .flatMap(id -> client.get()
                .uri("/products/{id}", id)
                .retrieve()
                .bodyToMono(Product.class), 8);
```

Khi mỗi inner là `Mono<Product>` của WebClient, có thể có tối đa khoảng 8 HTTP exchanges đang in-flight do operator tại một subscription, tùy connector/pooling/response/retry. Nhưng 100 HTTP requests cùng lúc, mỗi request flatMap concurrency 8, có thể làm phát sinh **tới khoảng 800 inner operations** đang active (upper-bound trực giác, không phải 800 connections bảo đảm).

**Cần hai lớp hạn chế:**
- local per-pipeline concurrency (flatMap argument);
- global controls (client pool/bulkhead/rate limit, per-tenant quotas, ingress concurrency, downstream capacity).

### 6.1. Chọn mức concurrency như thế nào?

Không có một con số tốt cho mọi workload. Với 1 request fan-out 30 IDs, cần khảo sát:
- mỗi remote call latency trung bình/p95/p99;
- downstream RPS/concurrent request quota;
- HTTP client max connections/pending acquire;
- memory per in-flight request, payload size, JSON decoding;
- retries/429/503/timeout và bão hòa DB/CPU;
- số inbound requests hoạt động đồng thời.

Bắt đầu nhỏ (ví dụ 2–8 **chỉ là giá trị thí nghiệm**, không phải chuẩn) rồi tăng dần dưới load test, quan sát throughput, tail latency, memory và error rate. Khi downstream hoặc pool đã đạt ngưỡng, tăng concurrency thường chỉ tăng queue, timeout, retry storm.

### 6.2. prefetch khác concurrency

Một overload:

```java
Flux<R> output = source.flatMap(
        value -> mapperReturningFlux(value),
        4,   // số inner publishers đang active
        16   // prefetch: số item request-ahead cho mỗi inner
);
```

Snippet chưa độc lập; `source` và `mapperReturningFlux` là placeholders có ý nghĩa minh họa. `prefetch` điều chỉnh demand/queueing, **không** cấp 16 threads, và không có nghĩa luôn lưu đúng 16 items trong RAM.

Ước lượng kiểm tra áp lực trên inner multi-value streams: `concurrency × prefetch × average item size`. Đây chỉ là xấp xỉ, chưa gồm outer buffers, HTTP response encoder, Reactor/Netty buffers, object overhead và caches. Với inner chỉ có một giá trị như Mono, prefetch kém quan trọng hơn trường hợp mỗi inner là Flux dài.

### 6.3. Bảo vệ stream vô hạn và inner treo

Nếu một inner không bao giờ complete và concurrency slots đã kín, phần tử đầu vào tiếp theo có thể không được xử lý. Cần `timeout(Duration)`, client timeout, circuit-breaker/bulkhead khi phù hợp; với infinite/hot publishers phải xem semantics cancellation/buffering, không dùng `flatMap(concurrency=1000)` tùy hứng.

## 7. Kết hợp kết quả độc lập bằng Mono.zip

Một endpoint profile cần account và settings:

```java
Mono<Account> account = accountService.find(id);
Mono<Settings> settings = settingsService.find(id);

Mono<Profile> profile = Mono.zip(
        account, settings,
        (a, s) -> new Profile(a.id(), a.name(), s.theme()));
```

`Mono.zip` chỉ phát một kết quả khi **mỗi source đều có một value**. Nếu hai sources là asynchronous và độc lập, chúng có thể tiến triển chồng lấp latency. Nếu một nguồn lỗi, zip thường phát lỗi rồi hủy các nguồn khác còn chạy. Nếu một nguồn hoàn tất rỗng, zip không thể áp dụng combinator.

**Không hiểu sai:** zip hai remote calls không tạo distributed transaction, không bảo đảm snapshot consistency giữa hai databases và cũng không chứng minh người dùng có quyền đọc kết quả. Authorization trên từng nguồn/data scope vẫn cần được đảm bảo.

### 7.1. zipWith và tuple

```java
Mono<Tuple2<Account, Settings>> pair = accountMono.zipWith(settingsMono);

Mono<Profile> combined = accountMono.zipWith(
        settingsMono,
        (a, s) -> new Profile(a.id(), a.name(), s.theme()));
```

Đây là snippets, cần import `reactor.util.function.Tuple2` cùng DTO. Dùng `zipWith` khi một Mono đã là vế trái; semantics empty/error giống zip.

### 7.2. zipWhen cho dependent request

```java
Mono<Profile> profile = accountService.find(id)
        .zipWhen(account ->
                settingsService.findByAccount(account.id()))
        .map(pair -> new Profile(
                pair.getT1().id(),
                pair.getT1().name(),
                pair.getT2().theme()));
```

`zipWhen` tạo Publisher bên phải **sau khi có giá trị account**, do đó nó không tương đương “hai nguồn độc lập bắt đầu cùng lúc”. Với dependency chain đơn giản, cũng có thể dùng:

```java
Mono<Profile> profile = accountService.find(id)
        .flatMap(account -> settingsService.findByAccount(account.id())
                .map(settings -> new Profile(
                        account.id(), account.name(), settings.theme())));
```

Nếu không cần tuple, `flatMap`/`map` lồng nhau thường rõ ràng.

### 7.3. Zip với Mono.empty hoặc Mono<Void>

```java
Mono<User> user = userRepository.findById(id);
Mono<Settings> absent = Mono.empty();

Mono<Tuple2<User, Settings>> zipped = Mono.zip(user, absent);
```

`zipped` thường hoàn tất rỗng, không phát tuple. `Mono<Void>` cũng là “không có onNext” cho zip; không được dùng `Mono.zip(writeAuditReturningVoid, getUser)` và kỳ vọng luôn nhận cặp. Với trường hợp **chờ hoàn tất các tác vụ không trả giá trị**, dùng `Mono.when(publisherA,publisherB)` hoặc sequencing `then(...)`, đúng theo yêu cầu lỗi/transaction.

Nếu không tìm thấy user thì cần 404:

```java
Mono<User> user = userRepository.findById(id)
        .switchIfEmpty(Mono.error(
                new ResponseStatusException(
                        HttpStatus.NOT_FOUND, "User not found")));
```

Nếu settings là tùy chọn và có default hợp lệ:

```java
Mono<Settings> settings = settingsService.find(id)
        .defaultIfEmpty(new Settings("light"));
```

Không gán default mở rộng quyền truy cập khi permission service rỗng/lỗi. Reactor FAQ cũng cảnh báo với zip và nguồn rỗng, một vài nguồn có thể **không được subscribe** trong các trường hợp cụ thể; không gắn side effects bắt buộc vào giả định “zip subscribe hết tất cả” mà không có protocol đảm bảo.

## 8. Flux.zip, merge, concat và combineLatest

### 8.1. Flux.zip: ghép theo chỉ số

```java
Flux<String> zipped = Flux.zip(
        Flux.just("A", "B", "C"),
        Flux.just(1, 2),
        (letter, number) -> letter + number);
```

Output khi subscribe:

```text
A1
B2
```

Với hai Flux hữu hạn, zip ghép 1:1 từng vị trí và kết thúc khi không thể tạo thêm cặp vì một nguồn đã cạn. Phần `C` không có số để ghép nên không xuất hiện. Nếu một nguồn phát nhanh hơn, zip có thể queue/buffer để chờ nguồn còn lại.

### 8.2. Flux.merge: trộn theo thời điểm phát

```java
Flux<String> first = Flux.just("A1", "A2")
        .delayElements(Duration.ofMillis(100));
Flux<String> second = Flux.just("B1", "B2")
        .delayElements(Duration.ofMillis(60));
Flux<String> merged = Flux.merge(first, second);
```

Cả hai sources được subscribe sớm; output có thể interleave. Thứ tự ví dụ `B1,A1,B2,A2` chỉ là **một khả năng**. Không assert một thứ tự duy nhất trên những nguồn async có timing không được kiểm soát.

Dùng merge cho event streams độc lập khi thứ tự giữa sources không quan trọng, chẳng hạn hợp nhất notification topics.

### 8.3. Flux.concat: source A rồi source B

```java
Flux<String> out = Flux.concat(
        Flux.just("A1", "A2"),
        Flux.just("B1", "B2"));
```

Output deterministic:

```text
A1
A2
B1
B2
```

Concat đợi A hoàn tất trước khi xử lý B. Nếu A **vô hạn**, B không bao giờ được subscribe theo concat thông thường.

### 8.4. mergeSequential: subscribe sớm nhưng giữ source order

`Flux.mergeSequential(...)` có thể đăng ký nhiều sources sớm rồi phát theo thứ tự source; thích hợp khi muốn overlap async công việc nhưng thứ tự nhóm A trước B. Tương tự `flatMapSequential`, sẽ phải queue output từ source B khi A chậm. Nó **không** đảm bảo các side effects A/B xảy ra tuần tự.

### 8.5. combineLatest: trạng thái mới nhất

```java
Flux<String> dashboard = Flux.combineLatest(
        temperatureFlux,
        humidityFlux,
        (temperature, humidity) ->
                "temperature=" + temperature + ",humidity=" + humidity);
```

Sau khi mỗi source phát ít nhất một giá trị, combineLatest phát tổ hợp giá trị mới nhất mỗi khi nguồn bất kỳ cập nhật. Thích hợp dashboard/sensor state, không phải pairing theo index. Các values có thể đến từ thời điểm khác nhau, không bảo đảm DB transaction-consistent snapshot. Một source chưa từng phát thì chưa có đủ “latest values” để combine.

### 8.6. Bảng quyết định

| Mục tiêu | Operator |
| --- | --- |
| Ghép hai Mono độc lập, đủ cả hai value | `Mono.zip` |
| Nguồn phải biết output của nguồn trước | `flatMap` / `zipWhen` |
| Ghép từng phần tử theo index | `Flux.zip` |
| Trộn events giữa sources theo lúc đến | `merge` |
| Phát hết A rồi mới B | `concat` |
| Subscribe sớm nhưng giữ output theo source | `mergeSequential` |
| Ghép giá trị mới nhất của từng stream | `combineLatest` |
| Fan-out nhiều inner publishers ưu tiên throughput | `flatMap(fn,n)` |
| Fan-out nhưng giữ thứ tự output | `flatMapSequential(fn,n)` |
| Xử lý inner lần lượt, có execution order | `concatMap(fn)` |

## 9. Error handling khi compose

### 9.1. flatMap mặc định fail-fast

```java
Flux<Product> products = Flux.fromIterable(ids)
        .flatMap(id -> fetchProduct(id), 4);
```

Nếu một inner phát `onError`, composition thường phát lỗi terminal, cancel các inner còn lại. Nếu API yêu cầu **đủ mọi sản phẩm**, đây có thể là lựa chọn đúng.

Nếu một lỗi 404 được phép bỏ qua:

```java
Flux<Product> bestEffort = Flux.fromIterable(ids)
        .flatMap(id -> fetchProduct(id)
                .onErrorResume(ProductNotFoundException.class,
                        ex -> Mono.empty()), 4);
```

Đây là fragment: `ProductNotFoundException` cần định nghĩa. Không dùng fallback rỗng với mọi exception nếu ứng dụng cần biết sự cố 500/timeouts. Để ghi nhận partial failures, trả DTO từng item có success/error thay vì âm thầm drop.

### 9.2. Partial result DTO

```java
record ItemResult(int id, String value, String error) {}

Flux<ItemResult> result = Flux.fromIterable(ids)
        .flatMap(id -> fetchProduct(id)
                .map(p -> new ItemResult(id, p.name(), null))
                .onErrorResume(ex -> Mono.just(
                        new ItemResult(id, null, "remote_failed"))), 4);
```

Đây là snippet; `ids`, `fetchProduct`, `Product` phải tồn tại. Không gửi nguyên exception message chứa credentials/IP/SQL sang client. Nếu cần giữ thứ tự, dùng `flatMapSequential`; lựa chọn HTTP status cho partial success phải thuộc API contract.

### 9.3. Empty và error của zip

Nếu một source rỗng, zip có thể hoàn tất rỗng. Nếu một source lỗi, zip thường fail-fast/cancel những sources còn lại. Với permission service bị lỗi, **không** mặc định `onErrorReturn(new Permissions("ADMIN"))`; fail closed để không mở rộng quyền.

### 9.4. Retry + timeout + không tạo retry storm

```java
Mono<Product> call = fetchProduct(id)
        .timeout(Duration.ofSeconds(2))
        .retryWhen(Retry.backoff(2, Duration.ofMillis(100))
                .filter(ex -> ex instanceof TransientFailure));
```

Snippet cần import `reactor.util.retry.Retry` và class `TransientFailure`. `retryWhen` ở đây cho tối đa 2 retries bổ sung theo filter; backoff và deadline vẫn phải gắn với SLO và per-request budget. Với 100 inbound calls × 5 fan-out × 3 attempts, tải có thể tăng lớn khi dependency lỗi. Không retry mù 4xx/permission/side-effecting POST.

### 9.5. flatMapDelayError

`flatMapDelayError(mapper, concurrency, prefetch)` trì hoãn lỗi cho đến khi những hoạt động/backlog phù hợp được xử lý. Nó **không tự chuyển thành partial success**: cuối cùng vẫn có terminal error. Khi muốn báo cáo item-wise, per-inner error DTO thường rõ ràng hơn.

### 9.6. onErrorContinue là lựa chọn nhạy cảm

`onErrorContinue` có semantics phụ thuộc operators và có thể gây hành vi khó dự đoán ở upstream. Đừng dùng mặc định để “bỏ qua bất kỳ item lỗi nào”; prefer `onErrorResume` đặt **bên trong mapper** với contract rõ và metrics.

## 10. Schedulers và tránh blocking event loop

`flatMap` không tự tạo threads. Reactor có:
- `subscribeOn(scheduler)`: ảnh hưởng nơi nguồn/subscription và upstream chạy.
- `publishOn(scheduler)`: dịch execution context của operators phía sau.
- `Schedulers.boundedElastic()`: phù hợp để bridge một số blocking tasks có giới hạn.
- `Schedulers.parallel()`: cho một số công việc CPU có giới hạn; không dùng để chạy JDBC blocking.

```java
Mono<LegacyRecord> record = Mono.fromCallable(
                () -> jdbcService.findRecord(id))
        .subscribeOn(Schedulers.boundedElastic());
```

Không biến JDBC thành nonblocking; phải giới hạn pool/queue và cân nhắc Spring MVC cho kiến trúc chủ yếu blocking.

**Anti-pattern trong WebFlux controller:**

```java
@GetMapping("/bad")
Product bad() {
    return webClient.get().uri("/products/1").retrieve()
            .bodyToMono(Product.class).block();
}
```

Lệnh block terminal có thể block hoặc bị cấm trên Reactor nonblocking event-loop. Controller nên:

```java
@GetMapping("/good")
Mono<Product> good() {
    return webClient.get().uri("/products/1").retrieve()
            .bodyToMono(Product.class);
}
```

Hai snippets yêu cầu `webClient`, `Product` và `@RestController`; trong app thật trả Publisher cho Spring WebFlux để framework subscribe và điều khiển response. Không tạo detached `subscribe()` trong handler.

## 11. Demo runnable Spring Boot 3.5 + Java 17

Ví dụ sử dụng `Mono.delay` để mô phỏng async I/O, không có database hoặc external service. Các endpoints:
- `GET /api/demo/map`: map deterministic;
- `GET /api/demo/flat?concurrency=2`: flatMap có thể đảo order;
- `GET /api/demo/ordered`: flatMapSequential giữ ID order;
- `GET /api/demo/serial`: concatMap tuần tự;
- `GET /api/demo/profile/{id}`: zip account và settings độc lập;
- `GET /api/demo/zip`, `/concat`, `/merge`: các semantics ghép.

### 11.1. POM fragment

Tạo project tại [Spring Initializr](https://start.spring.io/), Maven/Java 17/Spring Boot 3.5.x, chọn **Spring Reactive Web (WebFlux)**. Dependency chính:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-webflux</artifactId>
</dependency>
```

Đây là fragment của POM do Initializr tạo, không phải toàn bộ POM. Để giữ server reactive, không thêm `spring-boot-starter-web` vào demo này; khi cả hai cùng có mặt trong Boot 3.x, Servlet MVC thường được ưu tiên.

### 11.2. Mã Java đầy đủ

Đặt toàn bộ nội dung vào `src/main/java/com/example/demo/DemoApplication.java`:

```java
package com.example.demo;

import java.time.Duration;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}

record ItemView(int id, String label) {}
record AccountView(int id, String name) {}
record SettingsView(String theme) {}
record ProfileView(int id, String name, String theme) {}

@Service
class AsyncDemoService {

    // Với ID 1..4, delay lần lượt 320, 240, 160, 80 ms.
    Mono<ItemView> loadItem(int id) {
        long millis = 80L * (5 - id);
        return Mono.delay(Duration.ofMillis(millis))
                .map(tick -> new ItemView(id, "item-" + id));
    }

    Mono<AccountView> loadAccount(int id) {
        return Mono.delay(Duration.ofMillis(100))
                .map(tick -> new AccountView(id, "user-" + id));
    }

    Mono<SettingsView> loadSettings(int id) {
        return Mono.delay(Duration.ofMillis(70))
                .map(tick -> new SettingsView("dark"));
    }
}

@RestController
@RequestMapping("/api/demo")
class DemoController {

    private final AsyncDemoService service;

    DemoController(AsyncDemoService service) {
        this.service = service;
    }

    @GetMapping("/map")
    Flux<Integer> mapped() {
        return Flux.range(1, 4).map(i -> i * 10);
    }

    @GetMapping("/flat")
    Flux<ItemView> flattened(
            @RequestParam(defaultValue = "2") int concurrency) {
        if (concurrency < 1 || concurrency > 4) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST,
                    "concurrency must be between 1 and 4");
        }
        return Flux.range(1, 4)
                .flatMap(service::loadItem, concurrency);
    }

    @GetMapping("/ordered")
    Flux<ItemView> ordered() {
        return Flux.range(1, 4)
                .flatMapSequential(service::loadItem, 3);
    }

    @GetMapping("/serial")
    Flux<ItemView> serial() {
        return Flux.range(1, 4)
                .concatMap(service::loadItem);
    }

    @GetMapping("/profile/{id}")
    Mono<ProfileView> profile(@PathVariable int id) {
        if (id < 1) {
            return Mono.error(new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, "id must be positive"));
        }
        return Mono.zip(
                service.loadAccount(id),
                service.loadSettings(id),
                (account, settings) -> new ProfileView(
                        account.id(), account.name(), settings.theme()));
    }

    @GetMapping("/zip")
    Flux<String> zipped() {
        return Flux.zip(
                Flux.just("A", "B", "C"),
                Flux.just(1, 2),
                (letter, number) -> letter + number);
    }

    @GetMapping("/concat")
    Flux<String> concatenated() {
        return Flux.concat(
                Flux.just("A1", "A2"),
                Flux.just("B1", "B2"));
    }

    @GetMapping("/merge")
    Flux<String> merged() {
        Flux<String> a = Flux.just("A1", "A2")
                .delayElements(Duration.ofMillis(100));
        Flux<String> b = Flux.just("B1", "B2")
                .delayElements(Duration.ofMillis(60));
        return Flux.merge(a, b);
    }
}
```

### 11.3. Giải thích code

File chỉ có một public top-level class và các records/classes package-private: hợp lệ trong Java 17. Spring Boot WebFlux subscribe publishers cho HTTP response, không có `.block()`/`.subscribe()` thủ công. `Mono.delay` tạo async timer giả lập, không chứng minh hệ thống có HTTP network traffic thực. `flatMap(concurrency)` chỉ giới hạn inner subscriptions cho mỗi request. `flatMapSequential`/`concatMap` phát ID 1..4, nhưng concatMap không tạo các inner cùng lúc. `Mono.zip` cần cả Account và Settings. `Flux.zip` bỏ chữ C vì không có số thứ ba. `Flux.merge` có output order không định trước.

Đây là demo không có auth/DB/CSRF/rate limiting/metrics; không public deploy làm API sản xuất.

### 11.4. Chạy

```bash
# macOS / Linux
./mvnw spring-boot:run

# Windows PowerShell / Command Prompt
mvnw.cmd spring-boot:run
```

Nếu không đổi server port, thử `http://localhost:8080`.

### 11.5. Đối chiếu các kết quả

**Map:**

```bash
curl -i http://localhost:8080/api/demo/map
```

Status 200, JSON body deterministic:

```json
[10,20,30,40]
```

**FlatMap (thứ tự tùy scheduling):**

```bash
curl -i 'http://localhost:8080/api/demo/flat?concurrency=3'
```

Response chứa đúng bốn objects ID=1..4, nhưng thứ tự có thể là [3,2,1,4] hoặc kiểu khác. **Không assert cứng một thứ tự** trong test. Nếu `concurrency=0` hoặc `concurrency=5`, endpoint trả 400 do kiểm tra range 1..4.

**FlatMapSequential:**

```bash
curl -i http://localhost:8080/api/demo/ordered
```

JSON array theo ID:

```json
[
 {"id":1,"label":"item-1"},
 {"id":2,"label":"item-2"},
 {"id":3,"label":"item-3"},
 {"id":4,"label":"item-4"}
]
```

**ConcatMap:**

```bash
curl -i http://localhost:8080/api/demo/serial
```

Cũng có ID 1,2,3,4, nhưng subscribe mỗi inner sau khi inner trước hoàn tất. Trong demo, tổng thời gian thường dài hơn việc gọi các inner overlapping; không cam kết latency chính xác.

**Mono.zip profile:**

```bash
curl -i http://localhost:8080/api/demo/profile/7
```

Body:

```json
{"id":7,"name":"user-7","theme":"dark"}
```

Hai nguồn trễ khoảng 100ms và 70ms; nếu overlap thực, tổng thời gian gần max latency cộng overhead, không mặc định bằng 170ms hay đúng 100ms. `id=0` trả 400.

**Flux.zip vs Flux.concat:**

```bash
curl -i http://localhost:8080/api/demo/zip
curl -i http://localhost:8080/api/demo/concat
```

Bodies lần lượt:

```json
["A1","B2"]
```

```json
["A1","A2","B1","B2"]
```

**Flux.merge:**

```bash
curl -i http://localhost:8080/api/demo/merge
```

Kết quả gồm A1,A2,B1,B2, nhưng thứ tự giữa hai nguồn phụ thuộc timing. A1 trước A2 trong nguồn A và B1 trước B2 trong nguồn B.

**PowerShell:** dùng `curl.exe` thay cho alias `curl` của một số phiên bản:

```powershell
curl.exe -i "http://localhost:8080/api/demo/map"
curl.exe -i "http://localhost:8080/api/demo/flat?concurrency=3"
curl.exe -i "http://localhost:8080/api/demo/ordered"
curl.exe -i "http://localhost:8080/api/demo/profile/7"
```

## 12. Test với WebTestClient và StepVerifier

### 12.1. Test dependencies

Thêm vào POM Spring Boot 3.5:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
<dependency>
    <groupId>io.projectreactor</groupId>
    <artifactId>reactor-test</artifactId>
    <scope>test</scope>
</dependency>
```

Boot BOM quản lý versions. `reactor-test` cung cấp `StepVerifier`, Spring Test và WebFlux stack hỗ trợ `WebTestClient`.

### 12.2. HTTP integration test

Lưu `src/test/java/com/example/demo/ReactiveCombinationTest.java`:

```java
package com.example.demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(webEnvironment =
        SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class ReactiveCombinationTest {

    @Autowired
    WebTestClient client;

    @Test
    void mapProducesValues() {
        client.get().uri("/api/demo/map")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .json("[10,20,30,40]");
    }

    @Test
    void orderedMaintainsInputOrder() {
        client.get().uri("/api/demo/ordered")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$[0].id").isEqualTo(1)
                .jsonPath("$[1].id").isEqualTo(2)
                .jsonPath("$[2].id").isEqualTo(3)
                .jsonPath("$[3].id").isEqualTo(4);
    }

    @Test
    void zipCombinesProfile() {
        client.get().uri("/api/demo/profile/7")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.id").isEqualTo(7)
                .jsonPath("$.name").isEqualTo("user-7")
                .jsonPath("$.theme").isEqualTo("dark");
    }

    @Test
    void invalidConcurrencyIsRejected() {
        client.get().uri("/api/demo/flat?concurrency=0")
                .exchange()
                .expectStatus().isBadRequest();
    }
}
```

Test không assert thứ tự `/flat` vì operator không hứa điều đó. Với môi trường CI quá chậm, cần xem timeout của WebTestClient/timeouts của app, không thay tests bằng `Thread.sleep()`.

### 12.3. Unit test operator

Lưu `src/test/java/com/example/demo/OperatorTest.java`:

```java
package com.example.demo;

import java.util.List;

import org.junit.jupiter.api.Test;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

class OperatorTest {

    @Test
    void mapIsDeterministic() {
        StepVerifier.create(Flux.just(1, 2, 3)
                        .map(i -> i * 10))
                .expectNext(10, 20, 30)
                .verifyComplete();
    }

    @Test
    void zipStopsWithShortest() {
        StepVerifier.create(Flux.zip(
                        Flux.just("A", "B", "C"),
                        Flux.just(1, 2),
                        (a, b) -> a + b))
                .expectNext("A1", "B2")
                .verifyComplete();
    }

    @Test
    void emptyMonoMakesZipEmpty() {
        StepVerifier.create(
                        Mono.zip(Mono.just(1),
                                Mono.<String>empty()))
                .verifyComplete();
    }

    @Test
    void concatKeepsBothSourcesInOrder() {
        StepVerifier.create(
                        Flux.concat(
                                Flux.just("A1", "A2"),
                                Flux.just("B1", "B2")))
                .expectNext("A1", "A2", "B1", "B2")
                .verifyComplete();
    }

    @Test
    void collectListProducesList() {
        StepVerifier.create(
                        Flux.just("A", "B").collectList())
                .expectNext(List.of("A", "B"))
                .verifyComplete();
    }
}
```

Đây là unit tests về **semantics** không dựa vào thời gian. Nếu cần test concurrency thực:
- instrument trong `Mono.defer(...)` để đếm active subscriptions;
- tăng `AtomicInteger` khi subscribe, giảm trong `doFinally(...)`;
- phát controlled completion bằng `Sinks.One`/virtual scheduler;
- assert peak active ≤ concurrency;
- không đo counter ở thời điểm **assembly**, vì assembly không phải subscription.

### 12.4. Chạy test

```bash
# macOS/Linux
./mvnw test

# Windows
mvnw.cmd test
```

## 13. Thực hành WebClient: tránh serial HTTP calls

Tổng hợp product và inventory độc lập:

```java
Mono<Product> product = catalogClient.get()
        .uri("/products/{id}", id).retrieve()
        .bodyToMono(Product.class);

Mono<Stock> stock = inventoryClient.get()
        .uri("/stock/{id}", id).retrieve()
        .bodyToMono(Stock.class);

Mono<ProductPage> page = Mono.zip(
        product, stock, ProductPage::new);
```

Snippet cần WebClient beans/DTO và id. Nếu recommendation phụ thuộc product category:

```java
Mono<RecommendationPage> page =
        catalogClient.get()
                .uri("/products/{id}", id)
                .retrieve()
                .bodyToMono(Product.class)
                .flatMap(product ->
                        recommendationClient.get()
                                .uri("/categories/{cat}/recommendations",
                                        product.category())
                                .retrieve()
                                .bodyToFlux(Product.class)
                                .take(10)
                                .collectList()
                                .map(items -> new RecommendationPage(
                                        product, items)));
```

Cần lấy product trước vì recommendation URL phụ thuộc category; `flatMap` biểu diễn dependency. Nếu muốn giữ order kết quả từ một danh sách IDs theo UI rank, dùng `flatMapSequential(this::fetchProduct, concurrency)`. Với updates cần strict side-effect order, dùng `concatMap` và transaction/version policy của datastore.

### 13.1. Các giới hạn cùng lúc

```java
Flux<Product> products = Flux.fromIterable(ids)
        .take(50)
        .flatMap(id -> fetchProduct(id)
                .timeout(Duration.ofSeconds(2)), 5);
```

`take(50)` cap số IDs từ Flux nhưng nếu `ids` đã materialize thành List rất lớn trước đó, memory của List vẫn tồn tại. Nên giới hạn ngay request parser/API boundary. `flatMap(...,5)` chỉ điều chỉnh concurrency của một subscription; HTTP client pool/global rate limit vẫn cần cài riêng.

## 14. Backpressure, bộ nhớ và response HTTP

Nguồn tăng memory thường gặp:
- `flatMapSequential` buffer inner đến sau hoàn tất trước;
- `zip` buffer từ source nhanh đợi source chậm;
- `collectList()` gom toàn source cho đến complete;
- `buffer(n)` gom batches;
- `cache()` trên hot/unbounded Flux không giới hạn lịch sử;
- `onBackpressureBuffer()` không maxSize;
- response conversion, decoder buffer, Netty ByteBuf, downstream client pool pending queue.

**Backpressure không có nghĩa heap luôn hữu hạn.** Mọi collection/queue và concurrency đều phải có business/storage limits.

Trong WebFlux, `Flux<T>` trả `application/json` có thể được encode/stream theo cơ chế non-blocking writer thay vì nhất thiết gom toàn bộ như MVC. Tuy nhiên nếu handler tự `collectList()`, phần dữ liệu đó đã được gom trước khi writer có thể stream; với stream vô hạn sẽ không có complete.

Với `text/event-stream` hoặc NDJSON, từng item có thể được flush/stream riêng; khi lỗi xảy ra **sau khi đã commit HTTP headers/body**, không thể bảo đảm đổi HTTP 200 thành 500. Thiết kế application event-error/connection-close và retry/cancellation cho streams dài. Với một Mono.zip trả DTO sau khi các dependencies xong, lỗi thường xuất hiện trước khi viết body, dễ mapping thành 4xx/5xx hơn.

### 14.1. combineLatest không tạo snapshot transaction

Nếu dashboard ghép giá A (lúc t=1) với số lượng B (lúc t=2), combineLatest có thể phát bản ghép từ những dữ liệu **không cùng transaction timestamp**. Với tài chính hoặc invariants quan trọng, cần API/DB snapshot/version chung, không chỉ combineLatest.

### 14.2. Cancellation không hoàn tác DB commit

Khi browser ngắt, upstream Publisher có thể bị cancel, nhưng DB side effect đã commit không rollback tự động. Đừng dùng HTTP cancellation như thay transaction hoặc distributed saga compensation. Dùng idempotency keys, transaction/outbox và operation status khi nghiệp vụ yêu cầu.

### 14.3. Context, auth và secrets

Reactor Context khác Java ThreadLocal. Đừng giả định MDC/SecurityContextHolder sẽ tự có trên mọi scheduler thread. Dùng Spring Security reactive context/context propagation phù hợp, truyền identity/tenant rõ ràng vào downstream, và giới hạn mọi truy vấn theo scope đã kiểm tra. Với concurrent fan-out, tránh lộ kết quả tenant khác hoặc ghi raw Authorization token trong lỗi/logs.

## 15. Lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách sửa |
| --- | --- | --- |
| `Mono<Mono<T>>` | Dùng map cho hàm trả Mono | flatMap |
| `Flux<Flux<T>>` | Dùng map cho hàm trả Flux | flatMap/concatMap |
| Item đảo thứ tự | flatMap merge theo completion time | flatMapSequential hoặc concatMap |
| Side effects ghi lộn thứ tự | Nhiều inner chạy đồng thời | concatMap, DB lock/version |
| Chậm vì chỉ xử lý từng item | concatMap với I/O độc lập | flatMap với concurrency đo được |
| Dữ liệu chờ lâu và memory tăng | flatMapSequential queue chờ inner đầu | Giảm concurrency/prefetch, bỏ ordering nếu được |
| Tăng concurrency nhưng throughput không tăng | Downstream/pool bão hòa hoặc nguồn blocking | Đo latency, pool, scheduler, RPS |
| Zip không có output | Một source empty/Mono<Void> | switchIfEmpty/when/then theo contract |
| Zip bên phụ không subscribe | Source rỗng khiến zip complete sớm | Không buộc side effect vào zip subscription |
| Zip bỏ phần dư | Một Flux ngắn hơn | Đúng semantics; chọn merge/combineLatest nếu khác mục tiêu |
| Concat không chạy B | A vô hạn | Thay merge hoặc ràng buộc A |
| merge không giữ global order | Giá trị interleave | concat |
| combineLatest chưa emit | Chưa nhận một value từ mỗi source | Thiết kế defaults/khởi tạo |
| WebFlux controller block event loop | Dùng block()/JDBC/Thread.sleep | Reactive I/O hoặc boundedElastic bridge |
| Queue cao, 429/503 tăng | Fan-out nhân concurrency inbound | Bulkhead/rate limit/pool limits |
| Một lỗi làm dừng cả batch | flatMap/zip fail-fast | Per-item onErrorResume/DTO result |
| Timeout/retry làm tải nặng hơn | Retry nhiều không có giới hạn | Deadline/backoff/filter/jitter |
| Partial errors bị che | onErrorResume trả empty mọi lỗi | Phân loại và báo thiếu item rõ |
| Concurrency test sai | Đếm mapper assembly thay subscriptions | Mono.defer + doFinally |
| HTTP lỗi không đổi được status | Response đã committed | Error event/close và pre-validation |
| collectList OOM | Nguồn quá lớn/vô hạn | Limit/pagination/stream |
| Context tenant bị mất | ThreadLocal không được propagate | Reactor Context/auth-scope propagation |
| Unit test order không ổn định | Assert fixed order của flatMap/merge | Assert tập items, không assume order |

## 16. Checklist review

1. Function trong map trả value hay Publisher?
2. Source là Mono (0..1), Flux (0..N), cold hay hot?
3. Có thể empty/Mono<Void>? Zip sẽ làm gì?
4. Có cần thứ tự output hoặc thứ tự side effects? Đó là hai yêu cầu khác.
5. Khi nào dùng flatMapSequential thay concatMap và chấp nhận queue?
6. Concurrency thực tế per request và trên toàn hệ thống có được giới hạn?
7. Prefetch/inner cardinality/item size có nguy cơ heap growth?
8. Retry, timeout, cancellation và downstream connection pool được cấu hình?
9. Với concurrent writes, DB transaction/optimistic locking có được áp?
10. Errors fail-fast hay per-item, client có nhận biết partial success?
11. Có blocking operations trên Netty/event-loop?
12. Có CORS/auth/tenant ACL/rate limits khi fan-out WebClient?
13. HTTP writer stream hay collectList? Lỗi sau committed response xử lý thế nào?
14. Có tests deterministic cho map/zip/concat và thứ tự flatMapSequential?
15. Có tests concurrency dựa vào subscription, không dựa vào thời gian?
16. Có đo p95/p99 latency, active connections, queue, 429/503 và memory với slow downstream?

## 17. Tự kiểm tra

**Câu 1.** Dùng `Mono<UserId>.map(id -> fetchUser(id))`, nếu `fetchUser` trả Mono<User> thì type kết quả là gì?

**Đáp án:** `Mono<Mono<User>>`. Dùng `flatMap` cho `Mono<User>`.

**Câu 2.** `flatMap(mapper, 3)` có nghĩa ứng dụng dùng đúng ba threads không?

**Đáp án:** Không. Nó giới hạn inner subscriptions/in-flight của operator, không phải số threads toàn ứng dụng.

**Câu 3.** Cần giữ thứ tự dữ liệu đầu ra nhưng vẫn overlap calls thì chọn gì?

**Đáp án:** `flatMapSequential`, chấp nhận buffer khi inner đến sau xong sớm.

**Câu 4.** Cần A commit trước khi B bắt đầu thì `flatMapSequential` đủ không?

**Đáp án:** Không. Dùng `concatMap`/sequencing và bảo vệ DB transaction/concurrency.

**Câu 5.** Một Mono trong `Mono.zip` rỗng thì sao?

**Đáp án:** Không có đủ dữ liệu để combine; zip thường hoàn tất rỗng.

**Câu 6.** Flux.zip("A","B","C" và 1,2) trả gì?

**Đáp án:** Các cặp A1, B2; C không có phần tử ở source kia nên không phát.

**Câu 7.** Dashboard cần giá trị mới nhất khi sensor bất kỳ cập nhật?

**Đáp án:** `combineLatest`, sau khi từng source có ít nhất một value.

**Câu 8.** Một trong hai source của Flux.concat không hoàn tất thì source sau thế nào?

**Đáp án:** Nguồn sau chờ mãi (nếu không có timeout/cancellation).

**Câu 9.** Tại sao concurrency 100 có thể chậm hơn 10?

**Đáp án:** Có thể làm downstream pool/CPU/queue/429/503 bão hòa; phải benchmark theo tải thực.

**Câu 10.** Dùng `.block()` trong WebFlux HTTP controller có hợp lý không?

**Đáp án:** Tránh; return Mono/Flux và compose async work thay vì chặn event loop.

## 18. Nguồn tham khảo chính thức

- [Spring Framework — WebFlux Overview](https://docs.spring.io/spring-framework/reference/web/webflux.html): Reactor/WebFlux non-blocking architecture.
- [Spring Framework — Reactive Core](https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html): Reactive Streams, Mono, Flux và backpressure.
- [Spring Framework — WebFlux Controller Return Values](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/return-types.html): Publisher response encoding, stream semantics.
- [Spring Framework — WebClient](https://docs.spring.io/spring-framework/reference/web/webflux-webclient.html): compose non-blocking HTTP calls.
- [Spring Framework — WebClient retrieve](https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-retrieve.html): bodyToMono/bodyToFlux.
- [Project Reactor Core — Reference Guide](https://projectreactor.io/docs/core/release/reference/): transforming/combining streams, schedulers, error handling, testing.
- [Project Reactor — Flux Javadoc](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Flux.html): flatMap, flatMapSequential, concatMap, merge, zip, combineLatest, prefetch.
- [Project Reactor — Mono Javadoc](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Mono.html): Mono.zip/zipWhen/flatMap.
- [Project Reactor FAQ — zipWith/zipWhen empty sources](https://projectreactor.io/docs/core/release/reference/faq.html#faq.zip.empty): nguyên nhân không emit với Mono<Void>/empty.
- [Spring Boot 3.5 — Reactive Web](https://docs.spring.io/spring-boot/3.5/reference/web/reactive.html): WebFlux starter, reactive server.
- [Spring Boot 3.5 — Application Testing](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html): WebTestClient.
- [Reactive Streams Specification](https://www.reactive-streams.org/): Publisher/Subscriber/Subscription demand, cancellation.

**Kết luận:** `map` tạo giá trị đồng bộ, `flatMap` nối kết quả Publisher và cho phép inner async tiến triển đồng thời nhưng không bảo đảm thứ tự; `flatMapSequential` giữ thứ tự **output**, `concatMap` tuần tự hóa **thực hiện inners**. Ghép kết quả độc lập bằng `Mono.zip`, phụ thuộc nhau bằng `flatMap`/`zipWhen`, từng cặp bằng `Flux.zip`, trộn theo thời gian bằng `merge`, nối theo thứ tự bằng `concat`, ghép trạng thái mới nhất bằng `combineLatest`. Chọn concurrency theo hạn mức downstream, total inbound load, backpressure/prefetch/memory, timeouts, error semantics và benchmarks thay vì “càng cao càng nhanh”.
