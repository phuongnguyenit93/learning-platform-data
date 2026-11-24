# Ranh giới giữa mã phản ứng và mã chặn trong hệ thống hỗn hợp

Trong **REACTIVE_PROGRAMMING**, `Mono` và `Flux` biểu diễn các kết quả và luồng dữ liệu bất đồng bộ theo hợp đồng `Publisher–Subscriber`. Một ứng dụng Java thực tế thường không hoàn toàn reactive: nó có thể dùng WebClient và R2DBC ở một số nơi, nhưng vẫn phải gọi JDBC, thư viện file đồng bộ, SDK cũ hoặc API blocking ở nơi khác.

Hệ thống hỗn hợp có thể hoạt động ổn định nếu ranh giới giữa mã reactive và mã blocking được đặt rõ ràng. Mục tiêu là cô lập thao tác chặn trên scheduler phù hợp, giới hạn lượng công việc đồng thời, giữ transaction và tài nguyên trong đúng phạm vi, đồng thời bảo toàn ngữ nghĩa lỗi, timeout và cancellation. Chỉ bọc một lời gọi blocking trong `Mono` không tự biến lời gọi đó thành non-blocking.

## 1. Nhận diện mã blocking trước khi ghép vào pipeline

Một lời gọi blocking giữ thread hiện tại cho đến khi thao tác hoàn tất, bị timeout hoặc bị ngắt theo khả năng của API. Các ví dụ thường gặp:

- JDBC và các thư viện database đồng bộ.
- `RestTemplate`, HTTP client đồng bộ hoặc SDK gọi dịch vụ từ xa.
- `Files.readAllBytes`, đọc file đồng bộ hoặc thao tác trên stream blocking.
- `InputStream.read()`, `Socket.read()` và các API chờ dữ liệu.
- `Thread.sleep`, `Future.get()` hoặc `CompletableFuture.join()` khi kết quả chưa sẵn sàng.
- Thư viện legacy dùng lock hoặc chờ một thread khác hoàn tất.

Một phương thức trả về `Mono<T>` chưa chắc đã non-blocking. Ví dụ sau vẫn gọi JDBC ngay trên thread thực thi callback:

```java
Mono<Customer> wrong = Mono.just(jdbcRepository.findById(customerId));
```

Java đánh giá đối số `Mono.just(...)` trước khi gọi `just`, vì vậy `findById` chạy ngay trong lúc lắp ráp pipeline. Nếu phương thức này được gọi trên event loop của WebFlux, event loop bị chặn.

Ngay cả khi dùng `map`, lời gọi blocking vẫn chặn thread đang phát tín hiệu:

```java
Mono<Customer> alsoWrong = customerIds
    .map(jdbcRepository::findById);
```

`map` là phép biến đổi đồng bộ. Nó không tự chuyển công việc sang thread khác.

## 2. Tạo adapter lazy bằng fromCallable và subscribeOn

Với một lời gọi blocking trả về một giá trị, dùng `Mono.fromCallable` để trì hoãn lời gọi đến lúc subscription. Sau đó dùng `subscribeOn` để thực thi nguồn trên scheduler dành cho blocking:

```java
Mono<Customer> customer = Mono.fromCallable(
        () -> jdbcRepository.findById(customerId)
    )
    .subscribeOn(Schedulers.boundedElastic());
```

`fromCallable` chỉ gọi repository khi có subscription. `subscribeOn` đưa quá trình subscribe nguồn và lời gọi JDBC lên bounded elastic, nhờ đó event loop không phải chờ database đồng bộ.

Có thể đóng gói ranh giới này thành adapter riêng:

```java
final class BlockingCustomerAdapter {
    private final JdbcCustomerRepository repository;
    private final Scheduler blockingScheduler;

    BlockingCustomerAdapter(
            JdbcCustomerRepository repository,
            Scheduler blockingScheduler) {
        this.repository = repository;
        this.blockingScheduler = blockingScheduler;
    }

    Mono<Customer> findById(String id) {
        return Mono.fromCallable(() -> repository.findById(id))
            .subscribeOn(blockingScheduler);
    }
}
```

Controller và service phía trên chỉ nhìn thấy `Mono<Customer>`. Chi tiết JDBC và scheduler được giữ ở adapter, giúp phần còn lại của ứng dụng không phải tự quyết định thread cho từng lời gọi.

Nếu lời gọi blocking có thể trả `null`, `Mono.fromCallable` hoàn tất rỗng. Hãy xác định rõ ý nghĩa nghiệp vụ của kết quả rỗng; nếu cần báo không tìm thấy, có thể dùng `switchIfEmpty` để chuyển thành lỗi domain.

## 3. Chọn đúng scheduler cho từng loại công việc

Reactor có một số scheduler thường dùng:

| Scheduler | Mục đích | Dùng cho |
|---|---|---|
| `Schedulers.boundedElastic()` | Pool có giới hạn thread và queue task chờ | Tích hợp API blocking hoặc thư viện cũ |
| `Schedulers.parallel()` | Pool thread cố định hướng đến công việc CPU-bound, không blocking | Tính toán độc lập, xử lý dữ liệu ngắn |
| `Schedulers.single()` | Một thread dùng chung | Công việc tuần tự, ngắn và không blocking |
| `Schedulers.immediate()` | Thực thi trên thread gọi | Trường hợp cần thực thi trực tiếp |

Không chạy JDBC, `InputStream.read()` hoặc SDK blocking trên `parallel`. Các thread parallel được dùng chung cho nhiều pipeline; một lời gọi chặn lâu có thể làm các tác vụ CPU khác bị đói thread.

Thông thường, hãy dùng bounded elastic dùng chung của Reactor cho lời gọi blocking. Chỉ tạo scheduler riêng khi cần một giới hạn hoặc vùng cô lập riêng biệt, và component sở hữu scheduler phải dispose nó khi dừng. Không tạo scheduler mới cho mỗi request hoặc mỗi phần tử.

## 4. Bọc một luồng blocking nhiều phần tử

Nếu thư viện cũ trả về một collection đã tải toàn bộ dữ liệu, có thể dùng `Flux.defer` để trì hoãn thao tác lấy dữ liệu:

```java
Flux<Customer> customers = Flux.defer(() ->
        Flux.fromIterable(legacyRepository.loadAll())
    )
    .subscribeOn(Schedulers.boundedElastic());
```

Lời gọi `loadAll()` chạy khi subscribe trên bounded elastic. Tuy nhiên, phương thức này vẫn tải toàn bộ collection vào bộ nhớ trước khi phát phần tử đầu tiên. Nếu tập dữ liệu lớn, đây không phải cách streaming hiệu quả.

Nếu thư viện cung cấp cursor hoặc iterator blocking, hãy quản lý vòng đời và đóng nó khi complete, error hoặc cancel:

```java
Flux<Customer> customers = Flux.using(
        legacyRepository::openCursor,
        cursor -> Flux.fromIterable(cursor),
        CustomerCursor::close
    )
    .subscribeOn(Schedulers.boundedElastic());
```

Ví dụ giả định `CustomerCursor` triển khai `Iterable<Customer>` và `close()` đồng bộ. `using` tạo cursor theo subscription và cleanup khi luồng kết thúc. Vì việc đọc iterator có thể blocking, subscription của nguồn được đưa lên bounded elastic.

Với cursor thực tế, cần kiểm tra cách thư viện triển khai `hasNext()`/`next()`, cách cancellation được quan sát và liệu thao tác đọc có thể dừng giữa một lần gọi hay không. Nếu cursor có API đọc bất đồng bộ hoặc publisher native, ưu tiên adapter non-blocking chính thức.

## 5. Giới hạn concurrency khi nhiều request cùng gọi mã blocking

`flatMap` cho phép gọi nhiều adapter cùng lúc. Tham số concurrency giới hạn số inner Publisher đang hoạt động trong một subscription:

```java
Flux<Customer> customers = customerIds
    .flatMap(
        id -> blockingCustomerAdapter.findById(id),
        8
    );
```

Tối đa tám lời gọi inner được subscribe đồng thời ở operator này. Điều đó giúp tránh tạo hàng nghìn lời gọi JDBC cùng lúc trong một pipeline.

Nhưng giới hạn này áp dụng cho từng subscription. Nếu 100 request cùng chạy pipeline trên và mỗi request có concurrency 8, tổng số lời gọi có thể được khởi chạy vẫn lên đến khoảng 800. Vì vậy cần phối hợp:

- Concurrency của `flatMap` trong mỗi pipeline.
- Giới hạn thread và queue của scheduler.
- Kích thước connection pool JDBC.
- Pending acquire limit và timeout của pool.
- Bulkhead hoặc admission control ở cấp ứng dụng khi cần giới hạn tổng tải.

Nếu thứ tự xử lý phải được giữ, cân nhắc `concatMap` thay cho `flatMap`; đổi lại chỉ có một inner Publisher hoạt động tại một thời điểm trong phạm vi operator đó.

## 6. Đừng tạo thêm queue để che giấu quá tải

Bounded elastic có giới hạn thread và số task chờ. Khi tất cả thread bận và queue đã đầy, scheduler có thể từ chối task. Đây là tín hiệu quá tải cần được xử lý, không phải lý do để tạo thêm scheduler hoặc queue không giới hạn.

Các dấu hiệu cần quan sát:

- Thời gian chờ task trên bounded elastic tăng.
- Connection pool JDBC có nhiều pending acquire.
- Request timeout tăng dù database vẫn hoạt động.
- Heap hoặc số task chờ tăng liên tục.
- `RejectedExecutionException` xuất hiện khi scheduler bão hòa.

Nếu queue tăng liên tục, hãy giảm lượng request mới, giới hạn concurrency, cải thiện thời gian xử lý hoặc tăng năng lực dependency trong giới hạn cho phép. Tăng queue chỉ làm backlog tồn tại lâu hơn và tăng latency.

## 7. Giữ transaction blocking trong cùng ranh giới thực thi

Một transaction JDBC thường gắn với thread hoặc connection mà transaction manager cấp. Không nên mở transaction trên một thread rồi chuyển từng bước database sang scheduler khác nếu transaction manager là imperative và phụ thuộc `ThreadLocal`.

Hãy thực hiện toàn bộ công việc đồng bộ thuộc transaction bên trong cùng một callable:

```java
Mono<Order> createOrder(CreateOrder command) {
    return Mono.fromCallable(() -> transactionTemplate.execute(status -> {
            Order order = jdbcOrderRepository.insert(command);
            jdbcInventoryRepository.reserve(order.items());
            jdbcAuditRepository.recordCreated(order.id());
            return order;
        }))
        .subscribeOn(Schedulers.boundedElastic());
}
```

`TransactionTemplate` mở, commit hoặc rollback transaction quanh callback đồng bộ. Các lời gọi JDBC nằm trong cùng callback nên được thực hiện trong cùng transaction và cùng ranh giới thread.

Không nên làm như sau:

```java
// Không an toàn với transaction manager imperative phụ thuộc thread.
Mono<Order> order = Mono.fromCallable(() -> jdbcOrderRepository.insert(command))
    .subscribeOn(Schedulers.boundedElastic())
    .publishOn(Schedulers.parallel())
    .flatMap(saved -> Mono.fromCallable(() ->
        jdbcAuditRepository.recordCreated(saved.id())
    ));
```

Hai thao tác có thể chạy trên các thread khác nhau và không còn nằm trong cùng transaction imperative như mong muốn. Nếu cần transaction reactive xuyên suốt pipeline, dùng reactive driver và reactive transaction manager, chẳng hạn R2DBC. Không trộn JDBC blocking với reactive transaction manager rồi kỳ vọng `ThreadLocal` được giữ đúng.

## 8. ThreadLocal, MDC và Reactor Context

Nhiều thư viện cũ lưu transaction, security principal hoặc MDC trong `ThreadLocal`. Trong pipeline reactive, execution có thể chuyển thread; giá trị `ThreadLocal` không tự động đi theo subscription.

Reactor Context cung cấp metadata gắn với subscription:

```java
Mono<String> userName = Mono.deferContextual(context ->
    Mono.just(context.get("userName"))
);

Mono<String> request = userName
    .contextWrite(context -> context.put("userName", "minh"));
```

`deferContextual` đọc dữ liệu từ Context của subscription. Context không phải `ThreadLocal`; nó được truyền theo cơ chế của Reactor qua các operator tương thích.

Khi gọi thư viện blocking cần `ThreadLocal`, có thể dùng cơ chế context propagation được cấu hình rõ ràng hoặc thiết lập/khôi phục context bên trong adapter. Không nên đọc `ThreadLocal` ở một thread rồi giả định giá trị vẫn còn sau `publishOn` hoặc `subscribeOn`.

Với transaction imperative, cách an toàn thường là thực hiện toàn bộ transaction trong một callback blocking duy nhất như ví dụ `TransactionTemplate`. Với logging, dùng integration MDC/context propagation phù hợp phiên bản framework; luôn khôi phục giá trị sau khi callback kết thúc để tránh rò rỉ context giữa các tác vụ dùng chung thread.

## 9. Timeout reactive không nhất thiết dừng được lời gọi blocking

Có thể đặt timeout quanh adapter:

```java
Mono<Customer> customer = blockingCustomerAdapter.findById(customerId)
    .timeout(Duration.ofSeconds(2));
```

Khi hết hai giây, `timeout` phát lỗi và hủy subscription upstream. Nhưng cancellation không thể bảo đảm một lời gọi JDBC hoặc SDK blocking đang chạy sẽ bị dừng ngay. Nếu thư viện không hỗ trợ interrupt/cancel, task có thể tiếp tục giữ thread bounded elastic và connection cho đến khi chính thao tác đó kết thúc.

Vì vậy, cần cấu hình timeout ở tầng blocking thật sự:

- JDBC query timeout hoặc socket/network timeout của driver.
- Connection acquisition timeout của pool.
- Read/connect timeout của HTTP client đồng bộ.
- Timeout của SDK hoặc API file/network nếu thư viện hỗ trợ.
- Deadline tổng thể ở pipeline reactive để caller không chờ quá lâu.

Timeout reactive bảo vệ thời gian chờ của caller; timeout của dependency bảo vệ tài nguyên đang thực hiện công việc. Cần cả hai khi thao tác blocking có thể kéo dài.

## 10. Retry chỉ an toàn khi tác dụng phụ có thể lặp

Nếu một callable thực hiện ghi dữ liệu, retry có thể gọi lại thao tác sau timeout hoặc lỗi. Timeout không chứng minh database chưa commit. Một lần ghi có thể thành công nhưng response bị mất, khiến retry tạo bản ghi trùng.

```java
Mono<Receipt> receipt = Mono.fromCallable(() ->
        transactionTemplate.execute(status ->
            jdbcRepository.createReceipt(command, command.idempotencyKey())
        )
    )
    .subscribeOn(Schedulers.boundedElastic())
    .retryWhen(
        Retry.backoff(2, Duration.ofMillis(200))
            .filter(this::isTransientDatabaseFailure)
    );
```

Ví dụ chỉ an toàn nếu repository bảo đảm idempotency bằng khóa ổn định hoặc ràng buộc duy nhất và `isTransientDatabaseFailure` loại trừ lỗi nghiệp vụ không thể phục hồi. Không retry mọi `RuntimeException` hoặc lỗi validation.

Retry cũng cần giới hạn tổng thời gian và phối hợp với timeout của pool/driver. Nếu database đã bão hòa, retry dồn dập có thể làm tình trạng nặng hơn; backoff và jitter giúp giãn tải nhưng không thay thế admission control.

## 11. Đặt ranh giới kiến trúc ở adapter

Trong hệ thống hỗn hợp, nên để domain/application service phụ thuộc vào một cổng (port) có hợp đồng rõ ràng. Adapter quyết định công nghệ blocking hay reactive:

```text
WebFlux Controller
       |
       v
Application Service (Mono/Flux)
       |
       v
Port / Adapter interface
       |
       +---- Reactive adapter: WebClient / R2DBC
       |
       +---- Blocking adapter: JDBC / legacy SDK
                         |
                         v
                fromCallable + boundedElastic
```

Ví dụ interface của application layer:

```java
interface CustomerGateway {
    Mono<Customer> findById(String id);
}
```

Adapter reactive có thể dùng WebClient hoặc R2DBC. Adapter blocking có thể dùng JDBC và bọc lời gọi trong `Mono.fromCallable(...).subscribeOn(boundedElastic)`. Application service chỉ sử dụng `Mono<Customer>` và không cần biết chi tiết scheduler.

Nếu dự án muốn domain layer không phụ thuộc Reactor, có thể giữ port ở dạng domain interface đồng bộ hoặc kiểu trung lập rồi tạo adapter reactive ở application boundary. Lựa chọn này phụ thuộc kiến trúc và mức độ chấp nhận Reactor trong application layer; điều quan trọng là không để scheduler và chi tiết thread rải rác trong domain logic.

## 12. Tích hợp API blocking ở mép của ứng dụng

Đôi khi một thành phần imperative cần gọi một API reactive. Có thể chặn tại một ranh giới đồng bộ được kiểm soát, chẳng hạn một command-line runner hoặc một job imperative:

```java
Report report = reportService.generate()
    .block(Duration.ofSeconds(10));
```

Chỉ dùng cách này ở mép imperative, nơi thread có thể chờ và deadline được xác định. Không gọi `block()` trong WebFlux controller, event loop, callback của `map`/`flatMap` hoặc thread scheduler dành cho non-blocking work.

Nếu thành phần gọi có thể thay đổi API, tốt hơn là trả `Mono<Report>` để caller tiếp tục composition. Một lần `block()` ở ranh giới có chủ đích có thể chấp nhận được; nhiều lần block rải rác trong pipeline sẽ làm mất lợi ích của mô hình reactive và khiến timeout/cancellation khó phối hợp.

## 13. Kiểm thử ranh giới blocking/reactive

Kiểm thử nên xác minh cả giá trị lẫn vị trí thực thi, giới hạn concurrency và hành vi khi lỗi hoặc cancel.

### Kiểm thử adapter lazy

```java
AtomicInteger calls = new AtomicInteger();

Mono<String> result = Mono.fromCallable(() -> {
    calls.incrementAndGet();
    return "ok";
}).subscribeOn(Schedulers.boundedElastic());

assertEquals(0, calls.get());

StepVerifier.create(result)
    .expectNext("ok")
    .verifyComplete();

assertEquals(1, calls.get());
```

Assertion trước subscription xác minh lời gọi được trì hoãn. `StepVerifier` subscribe và kiểm tra kết quả; sau đó bộ đếm xác nhận callable chạy đúng một lần.

### Kiểm thử giới hạn concurrency

Có thể dùng bộ đếm số tác vụ đang hoạt động và giá trị lớn nhất quan sát được để xác minh `flatMap` không vượt concurrency đặt tại operator. Test nên dùng latch hoặc nguồn có thể điều khiển để tránh phụ thuộc timing ngẫu nhiên.

### Kiểm thử blocking call không chạy trên event loop

BlockHound có thể phát hiện một số thao tác blocking chạy trên thread được đánh dấu non-blocking. Có thể cài trong test integration phù hợp và xác minh adapter blocking được chuyển sang bounded elastic. BlockHound không thay thế việc kiểm tra timeout của driver hoặc khả năng hủy thực tế của thư viện.

### Kiểm thử cancellation và cleanup

Với cursor, stream hoặc resource blocking, test cần hủy subscription và xác minh resource được đóng. Dùng `using` cho cleanup đồng bộ hoặc `usingWhen` nếu cleanup bất đồng bộ. Nếu thao tác blocking không thể dừng tức thì, test phải xác minh nó có timeout riêng và không giữ tài nguyên vô hạn.

## 14. Những lỗi thường gặp trong hệ thống hỗn hợp

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| `Mono.just(blockingCall())` | Lời gọi chạy ngay khi lắp ráp, có thể chặn event loop | Dùng `fromCallable` và `subscribeOn(boundedElastic)` |
| Đặt lời gọi blocking trong `map` | Chặn thread đang phát tín hiệu | Tạo inner Publisher blocking có scheduler phù hợp |
| Chạy JDBC trên `parallel` | Chiếm thread CPU/non-blocking dùng chung | Dùng bounded elastic hoặc executor blocking riêng |
| Không giới hạn `flatMap` | Tạo quá nhiều lời gọi blocking đồng thời | Đặt concurrency và giới hạn pool/bulkhead toàn cục |
| Tạo scheduler cho từng request | Tăng thread, queue và rò rỉ lifecycle | Tái sử dụng scheduler có chủ sở hữu rõ ràng |
| Chuyển thread giữa các bước của transaction JDBC | Mất ngữ cảnh transaction imperative | Đặt toàn bộ transaction trong cùng callback blocking |
| Dựa vào ThreadLocal sau scheduler hop | Mất hoặc lẫn context giữa các request | Dùng Reactor Context hoặc context propagation rõ ràng |
| Chỉ dùng reactive timeout | Callable blocking có thể tiếp tục chạy | Cấu hình timeout ở driver/SDK và deadline pipeline |
| Retry thao tác ghi không idempotent | Có thể tạo side effect trùng | Dùng idempotency key và retry có lọc/giới hạn |
| Gọi `block()` trong controller reactive | Chặn event loop và làm giảm throughput | Trả Publisher cho framework subscribe |

## 15. Checklist thiết kế ranh giới reactive/blocking

Trước khi tích hợp một thư viện đồng bộ, hãy xác định:

1. Lời gọi nào thực sự blocking và có thể kéo dài bao lâu?
2. Có API reactive hoặc non-blocking chính thức thay thế không?
3. Nếu phải blocking, lời gọi đã được trì hoãn bằng `fromCallable`/`defer` chưa?
4. Nó chạy trên bounded elastic hoặc executor blocking được quản lý chưa?
5. Concurrency theo request và giới hạn tổng thể có phù hợp với connection pool không?
6. Transaction imperative có nằm trọn trong một callback/thread scope không?
7. ThreadLocal/MDC/security context được truyền qua ranh giới như thế nào?
8. Timeout của pipeline có đi cùng timeout thật của driver/SDK không?
9. Cancellation có dừng được tác vụ hay chỉ dừng caller chờ kết quả?
10. Retry có an toàn với side effect và có idempotency key không?
11. Resource như cursor, stream và connection có cleanup khi complete/error/cancel không?
12. Test có xác minh lazy execution, concurrency, thread phù hợp, timeout và cleanup không?

Hệ thống hỗn hợp không cần chuyển mọi thư viện sang reactive ngay lập tức. Hãy cô lập mã blocking trong adapter, trì hoãn lời gọi bằng `fromCallable` hoặc `defer`, thực thi trên bounded elastic, giới hạn concurrency và giữ transaction imperative trong một phạm vi đồng bộ duy nhất. Kết hợp timeout ở cả pipeline lẫn dependency, idempotency cho retry và cleanup theo lifecycle giúp phần reactive và phần blocking phối hợp an toàn mà không làm event loop bị chặn.
