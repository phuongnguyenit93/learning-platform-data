# Giới hạn việc tách chuỗi reactive bằng `subscribe()` hoặc chuyển sang API mệnh lệnh

> **Module:** Spring Framework – reactive  
> **Chủ đề cha:** Tích hợp hệ sinh thái  
> **Trọng tâm:** nhận biết ranh giới reactive ↔ imperative, vì sao gọi `subscribe()` giữa service/controller thường làm đứt chuỗi xử lý, khi nào `block()`/`toFuture()`/`toIterable()` được phép, cách tích hợp API blocking và callback cũ, và cách giữ nguyên error, cancellation, backpressure, transaction cùng Reactor Context. Ví dụ sử dụng Java 17+, Spring Boot 4.0.9 và Spring WebFlux.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích “assembly” và “subscription” trong Reactor, sự khác nhau giữa cold và hot Publisher.
2. Xác định bên nào phải sở hữu subscription tại mỗi ranh giới: WebFlux, WebClient, messaging framework, test hoặc một imperative entry point thực sự.
3. Phát hiện anti-pattern `service.doWork().subscribe(); return ...` làm lỗi không trở về caller, mất cancellation và có thể trả HTTP thành công quá sớm.
4. Thay nested `subscribe()` bằng `map`, `flatMap`, `then`, `zip`, `when`, `onErrorResume` và các operator composition thích hợp.
5. Giải thích tại sao `Mono.just(blockingCall())` và `publishOn` sau lời gọi đó không giải quyết blocking.
6. Cô lập JDBC, JPA, filesystem hoặc SDK đồng bộ bằng `Mono.fromCallable` + `Schedulers.boundedElastic()` với concurrency hữu hạn.
7. Chuyển giữa `Mono` và `CompletableFuture` có ý thức về eager/lazy execution và cancellation.
8. Giới hạn sử dụng `block`, `blockOptional`, `blockFirst`, `blockLast`, `toIterable` và `toStream` tại boundary đồng bộ được kiểm soát.
9. Phân biệt side-effect để quan sát với thao tác nghiệp vụ bắt buộc hoàn tất trước response.
10. Giữ Reactor Context, reactive transaction, security identity và cleanup trong cùng subscription.
11. Viết WebFlux endpoint đúng và test chứng minh lazy execution, thứ tự completion, lỗi và cancellation.
12. Quyết định khi nào nên dừng dùng WebFlux và để cả ứng dụng ở mô hình imperative nhất quán.

**Quy tắc ngắn:** trong code nghiệp vụ reactive, **hãy trả về hoặc compose `Publisher`, đừng tự `subscribe()` để “cho nó chạy”**. Chỉ chuyển sang mệnh lệnh tại một boundary rõ ràng khi caller buộc phải nhận giá trị đồng bộ; đừng chặn Netty event-loop.

## 2. Phân biệt mô tả công việc và thực thi công việc

Một Reactor pipeline thường được **lắp ráp** trước, rồi được một `Subscriber` **kích hoạt**. Với Publisher cold như phần lớn request WebClient hoặc nguồn `Mono.defer`, việc subscribe bắt đầu tác vụ cho từng subscriber.

~~~java
Mono<String> description = Mono.fromSupplier(() -> {
    System.out.println("source started");
    return "done";
});

// Chưa subscribe: nguồn chưa chạy.
description.map(String::toUpperCase);

// Test hoặc framework cuối cùng sẽ subscribe.
~~~

`map()` tạo một Publisher mới; nếu không dùng giá trị trả về thì operator vừa tạo không thuộc chain cuối. Để giữ phép biến đổi:

~~~java
Mono<String> transformed = description.map(String::toUpperCase);
~~~

`Mono.just(value)` thì khác: **Java đánh giá `value` ngay lúc assembly**. Nếu đối số gọi DB hoặc HTTP đồng bộ, operation đã chạy trước khi có subscription:

~~~java
Mono<String> wrong = Mono.just(legacyClient.readSync());
~~~

Với nguồn có side-effect hoặc blocking cần trì hoãn:

~~~java
Mono<String> deferred = Mono.fromCallable(legacyClient::readSync);
~~~

Lời gọi `fromCallable` chưa tự chuyển thread. Để offload nguồn blocking, dùng thêm scheduler phù hợp ở mục 7.

### 2.1. Cold và hot Publisher

| Đặc tính | Cold Publisher | Hot Publisher |
| --- | --- | --- |
| Bắt đầu phát dữ liệu | Thường theo từng subscription | Có thể phát dù chưa có subscriber |
| Subscribe nhiều lần | Có thể thực hiện lại operation | Có thể nhận các event từ thời điểm tham gia |
| Ví dụ | `Mono.defer`, `Mono.fromCallable`, nhiều WebClient calls | Sự kiện thời gian thực từ `Sinks.Many` |
| Rủi ro | Duplicate POST hoặc database write khi subscribe hai lần | Mất sự kiện, overflow hoặc subscriber đến muộn |
| Kỹ thuật liên quan | Idempotency, `cache`, `share` có chủ đích | Buffer/replay/broadcast có giới hạn và chính sách rõ |

Câu “không có gì chạy trước subscribe” có ngoại lệ: `Mono.just` đã tính giá trị ở assembly, hot source có thể phát từ trước, còn một `CompletableFuture` được tạo sẵn có thể đã chạy. Luôn xem tính chất nguồn, không áp dụng quy tắc một cách máy móc.

### 2.2. Một chain, một vòng đời

~~~text
HTTP request
    |
    v
Spring WebFlux subscribes
    |
    v
Controller returns Mono/Flux
    |
    v
Service operators
    |
    v
Repository / WebClient / callback adapter
    |
    +---- onNext / onComplete --> HTTP response
    +---- onError -----------> HTTP error handling
    +---- cancel ------------> cleanup upstream
~~~

Khi không tự tách subscription, request có một đường chính để truyền tín hiệu error, cancellation và demand. Đây là nền tảng để transaction và tracing đi xuyên suốt.

## 3. Ai là chủ sở hữu subscription?

`subscribe()` không phải cú pháp thay cho `await` và cũng không phải cách ép một task chạy xong. Nó tạo một subscription và trả `Disposable` cho caller quản lý.

| Boundary | Bên thường sở hữu subscribe | Ứng dụng nên trả gì? |
| --- | --- | --- |
| Spring WebFlux controller | WebFlux runtime | `Mono<T>` / `Flux<T>` / `Mono<Void>` |
| Spring WebFlux `WebFilter` | WebFlux runtime | `Mono<Void>` của toàn filter chain |
| WebClient call trong service | Outer caller/framework subscribe khi cần | `Mono` / `Flux`, chưa gọi `.subscribe()` |
| Reactive repository/transaction | Outer reactive chain | Publisher đã compose |
| `StepVerifier` trong test | `StepVerifier` | Publisher để verify |
| Command-line `main`, UI listener imperative, lifecycle task được quản lý | Code boundary | Có thể `subscribe` và giữ `Disposable` |
| Hàm đồng bộ buộc trả `T` | Imperative caller | Có thể `block(timeout)` ngoài event-loop theo chính sách |

Không phải cứ thấy `subscribe()` là sai. Sai là **subscribe vô chủ** giữa một chain mà framework hoặc caller đã sở hữu subscription.

### 3.1. Anti-pattern trong controller

~~~java
@PostMapping("/orders/{id}/audit")
Mono<String> wrong(@PathVariable String id) {
    auditService.audit(id).subscribe();
    return Mono.just("AUDIT_OK");
}
~~~

Lỗi của ví dụ:
- HTTP có thể trả `AUDIT_OK` trước khi audit ghi xong.
- Lỗi audit không truyền vào HTTP response như một error signal.
- Client disconnect không nhất thiết cancel task audit đang chạy.
- Tracing/security/transaction Context của request có thể không đi vào subscription tách.
- Retry request có thể khiến audit chạy trùng.
- Không có chủ thể giữ `Disposable` để hủy hoặc cleanup.

Cách sửa:

~~~java
@PostMapping("/orders/{id}/audit")
Mono<String> correct(@PathVariable String id) {
    return auditService.audit(id).thenReturn("AUDIT_OK");
}
~~~

Ở đây HTTP chỉ thành công khi `auditService.audit` đã complete. Nếu audit lỗi, outer chain lỗi và WebFlux có thể xử lý đúng theo exception mapping.

### 3.2. Anti-pattern trong service

~~~java
public Mono<Order> submit(Order order) {
    repository.save(order).subscribe();
    return Mono.just(order);
}
~~~

Hai vấn đề độc lập: operation `save` chạy trong subscription tách và caller nhận `order` trước khi persistence xác nhận. Thay bằng:

~~~java
public Mono<Order> submit(Order order) {
    return repository.save(order);
}
~~~

Nếu phải cập nhật thêm một hệ thống:

~~~java
public Mono<Order> submit(Order order) {
    return repository.save(order)
        .flatMap(saved ->
            auditClient.record(saved).thenReturn(saved));
}
~~~

Chain này chờ cả save lẫn audit. Tuy nhiên hai thao tác không tự thành distributed transaction; nếu cần đảm bảo publish-event cùng DB commit, cân nhắc outbox pattern.

## 4. Sử dụng operator thay nested `subscribe`

### 4.1. `map` cho biến đổi đồng bộ, nhanh

~~~java
Mono<OrderView> view = repository.findById(id)
    .map(order -> new OrderView(order.id(), order.status()));
~~~

`map` dành cho phép biến đổi một giá trị, không tự gọi một Publisher khác. Tránh đặt blocking JDBC, HTTP sync hoặc tác vụ CPU nặng trong `map` chạy trên event-loop.

### 4.2. `flatMap` cho operation trả Mono

Sai:

~~~java
Mono<Mono<Receipt>> nested = repository.save(order)
    .map(saved -> auditClient.record(saved).thenReturn(
        new Receipt(saved.id(), "AUDITED")));
~~~

Đúng:

~~~java
Mono<Receipt> receipt = repository.save(order)
    .flatMap(saved ->
        auditClient.record(saved)
            .thenReturn(new Receipt(saved.id(), "AUDITED")));
~~~

`flatMap` nối tín hiệu của inner Publisher vào outer chain, giữ error và cancellation. `Mono<Mono<T>>` thường là dấu hiệu bạn cần `flatMap`, không phải `.subscribe()` bên trong `map`.

### 4.3. `then`, `thenReturn`, `thenMany`

| Operator | Dùng khi | Kết quả |
| --- | --- | --- |
| `then()` | Chỉ quan tâm completion của upstream | `Mono<Void>` |
| `thenReturn(value)` | Sau khi upstream complete, trả giá trị hằng | `Mono<V>` |
| `then(otherMono)` | Làm bước sau theo thứ tự | Kết quả của `otherMono` |
| `thenMany(otherFlux)` | Sau upstream, bắt đầu stream khác | `Flux<T>` |

Ví dụ:

~~~java
public Mono<Void> deleteThenNotify(String id) {
    return repository.deleteById(id)
        .then(notificationClient.deleted(id));
}
~~~

`notificationClient.deleted(id)` được chạy theo subscription của `then` khi bước xóa hoàn tất; nếu xóa lỗi, notification không chạy. Nếu notification lỗi sau khi xóa đã commit, cần chính sách khôi phục nghiệp vụ thay vì giả định rollback toàn hệ thống.

### 4.4. Song song và có thứ tự

Khi hai operation độc lập:

~~~java
Mono<Tuple2<Customer, Cart>> combined =
    Mono.zip(customerClient.find(customerId),
             cartClient.load(customerId));
~~~

Khi chỉ cần cả hai complete:

~~~java
Mono<Void> finished = Mono.when(
    cache.invalidate(id),
    searchIndex.remove(id));
~~~

`Mono.when` thực hiện các nguồn trong cùng outer subscription; khi một nguồn lỗi, combinator phát lỗi và có thể cancel các nguồn còn lại.

Nếu bước B phụ thuộc bước A, dùng `flatMap` hoặc `then`, không dùng `zip` chỉ để ép hai thao tác chạy cùng lúc.

**Lưu ý `Mono<Void>`:** `zip` cần mỗi nguồn phát một giá trị. Nguồn hoàn thành rỗng có thể khiến `zip` không gọi combinator. Với tác vụ `Mono<Void>`, dùng `then`, `when` hoặc chọn cách biến completion thành giá trị tường minh.

### 4.5. Đừng biến `doOnNext` thành business transaction

`doOnNext`, `doOnError`, `doOnSuccess`, `doFinally` phù hợp cho metrics, log và quan sát lifecycle:

~~~java
return repository.findById(id)
    .doOnNext(item -> metrics.recordFound())
    .doOnError(error -> metrics.recordFailure());
~~~

Nếu ghi audit bắt buộc thành công, đừng gọi `.subscribe()` hay khởi tạo tác vụ bất đồng bộ trong `doOnNext`:

~~~java
// Sai nếu audit phải hoàn tất trước response.
return repository.findById(id)
    .doOnNext(item -> auditClient.record(item).subscribe());
~~~

Hãy dùng `flatMap`/`then`. Không xem `doOnError` là catch/recovery: operator này chỉ quan sát lỗi; muốn chuyển lỗi hoặc fallback, dùng `onErrorMap`, `onErrorResume` hoặc `onErrorReturn` theo policy.

## 5. Lỗi bị “mất” khi tự subscribe

~~~java
Mono<Void> audit = auditClient.record(order);

audit.subscribe();
return Mono.just("OK");
~~~

Subscription bên trong có error channel riêng. Lỗi không truyền tới outer `Mono.just("OK")`, nên caller không thể biết operation đã thất bại. Việc gọi `subscribe()` không có error consumer còn có thể dẫn đến lỗi không được quan sát đúng cách.

Đúng:

~~~java
return auditClient.record(order)
    .thenReturn("OK")
    .onErrorMap(error ->
        new AuditUnavailableException("Audit failed", error));
~~~

`AuditUnavailableException` là kiểu exception ứng dụng tự định nghĩa trong fragment này. Khi trả HTTP, map exception sang status/error DTO an toàn bằng `@ControllerAdvice`/`ErrorWebExceptionHandler`; không trả raw stack trace hoặc credential.

### 5.1. Error recovery phải có ý nghĩa

~~~java
return catalogClient.get(id)
    .onErrorResume(
        WebClientResponseException.NotFound.class,
        notFound -> Mono.empty());
~~~

Có thể xem 404 là không tồn tại tùy nghiệp vụ; nhưng không làm:

~~~java
return catalogClient.get(id)
    .onErrorResume(error -> Mono.empty());
~~~

nếu điều đó che mất 401, 503, timeout hoặc lỗi parse dữ liệu.

### 5.2. Timeout trên toàn operation

~~~java
return auditClient.record(order)
    .timeout(Duration.ofSeconds(2))
    .thenReturn("AUDIT_OK");
~~~

Khi timeout, outer chain phát lỗi và gửi cancellation về upstream. Việc upstream thật sự dừng I/O/SDK còn phụ thuộc driver/adapter. Với JDBC đã bắt đầu blocking call, cancel Reactor không bảo đảm driver hủy query ngay.

## 6. Khi nào gọi `subscribe()` thủ công là hợp lệ?

Một entry point không nhận/trả Publisher có thể buộc phải chủ động bắt đầu tác vụ, ví dụ:
- Desktop UI action, command-line job.
- Một callback library thuần mệnh lệnh.
- Startup/shutdown lifecycle được quản lý.
- Integration với framework có API callback và không nhận Publisher.

Trong các trường hợp đó, **boundary code chính là owner** và phải xử lý error, cancellation, shutdown, concurrency, idempotency.

### 6.1. Giữ Disposable và error handler

~~~java
Disposable running = taskService.execute(command)
    .subscribe(
        ignored -> { },
        error -> log.warn("Task failed", error),
        () -> log.info("Task completed")
    );

// Khi người dùng hủy hoặc thành phần bị đóng:
running.dispose();
~~~

Đây là fragment minh họa: `taskService`, `command`, `log` phải được cung cấp bởi ứng dụng. `Disposable.dispose()` gửi cancel signal; nó không bảo đảm một external blocking operation dừng tức khắc.

**Không bỏ `Disposable` nếu task có vòng đời cần hủy.** Có thể dùng `Disposables.composite()` để quản lý nhiều subscription cùng sống theo một màn hình hoặc component, rồi dispose cả group khi component đóng.

### 6.2. Không gọi `block()` để chờ trong event handler của WebFlux

Một callback có thể được gọi từ event-loop hoặc thread dành riêng. Nếu không biết caller thread, tuyệt đối không dùng `block()` chỉ vì API callback trả `void`. Hãy tìm extension point async của framework hoặc đưa task sang một worker được quản lý.

Nếu buộc phải fire-and-forget, phải có:
- Error consumer.
- Quản lý Disposable.
- Quota/concurrency limit.
- Cách shutdown/cancel.
- Logging/metrics theo job ID.
- Idempotency/retry budget.
- Cơ chế durable queue nếu task bắt buộc không được mất.

`subscribe()` không phải message queue; nếu JVM chết, task trong memory có thể biến mất.

## 7. Bọc API blocking bằng boundedElastic: cầu nối, không phải biến đổi phép màu

### 7.1. Sai: blocking eager

~~~java
public Mono<Customer> load(String id) {
    return Mono.just(legacyJpa.findById(id));
}
~~~

Java gọi `findById` trước khi tạo `Mono`, có thể trên Netty event-loop.

### 7.2. Đúng: lazy source và offload

~~~java
public Mono<Customer> load(String id) {
    return Mono.fromCallable(() -> legacyJpa.findById(id))
        .subscribeOn(Schedulers.boundedElastic());
}
~~~

`fromCallable` trì hoãn operation đến lúc subscribe, `subscribeOn(boundedElastic())` đặt nguồn blocking lên scheduler dành cho việc chờ I/O. Nếu callable trả `null`, Mono hoàn thành rỗng; dùng `switchIfEmpty` khi cần 404.

Trường hợp kết quả đồng bộ trả `void`:

~~~java
public Mono<Void> writeLegacy(Order order) {
    return Mono.fromRunnable(() -> legacyWriter.write(order))
        .subscribeOn(Schedulers.boundedElastic())
        .then();
}
~~~

**Lưu ý:** đây vẫn là blocking code. Nó giữ một worker thread và JDBC connection trong khi chờ. `boundedElastic` có giới hạn thread/task queue để tránh phình tài nguyên vô hạn; cần giới hạn thêm concurrency và pool của từng dependency.

### 7.3. Vì sao `publishOn` sau `Mono.just` không cứu được?

~~~java
// Sai: readSync() đã chạy trước khi publishOn có hiệu lực.
Mono<String> wrong = Mono.just(legacyClient.readSync())
    .publishOn(Schedulers.boundedElastic());

// Đúng: nguồn deferred và subscribeOn.
Mono<String> correct =
    Mono.fromCallable(legacyClient::readSync)
        .subscribeOn(Schedulers.boundedElastic());
~~~

`subscribeOn` tác động tới quá trình subscription/emission phía nguồn; `publishOn` chuyển context cho operator phía sau vị trí đặt nó. Không dùng `publishOn` để vá một lời gọi blocking eager.

### 7.4. Tính đúng transaction JDBC/JPA

`@Transactional` của JPA/JDBC thông thường dùng thread-bound resources. Đừng bắt đầu transaction ở Netty thread rồi offload từng dòng JDBC sang thread khác.

Một boundary rõ ràng:

~~~java
@Service
class LegacyBillingService {

    @Transactional
    public Receipt chargeSync(Command command) {
        // Tất cả JDBC/JPA operations nằm trong một
        // lời gọi đồng bộ được Spring transaction proxy bọc.
        return legacyRepository.charge(command);
    }
}
~~~

Bọc bên ngoài:

~~~java
Mono<Receipt> charge(Command command) {
    return Mono.fromCallable(
            () -> legacyBillingService.chargeSync(command))
        .subscribeOn(Schedulers.boundedElastic());
}
~~~

Đây là fragment minh họa, cần có `legacyRepository`, `Receipt`, `Command` và bean JPA/JDBC tương ứng. Transaction phải mở/commit trong cùng lời gọi blocking trên worker thread; đừng truyền JPA lazy entity ra ngoài rồi truy cập khi transaction đã đóng.

### 7.5. Giới hạn concurrency

~~~java
Flux<Receipt> chargeBatch(Flux<Command> commands) {
    return commands.flatMap(
        cmd -> Mono.fromCallable(
                () -> legacyBillingService.chargeSync(cmd))
            .subscribeOn(Schedulers.boundedElastic()),
        8
    );
}
~~~

`flatMap(..., 8)` giới hạn số inner subscriptions đồng thời **trong mỗi batch**. Nếu có nhiều HTTP requests, tổng concurrency vẫn có thể cao. Dùng thêm bulkhead hoặc semaphore ở cấp dependency, cùng Hikari pool size, timeout và giới hạn số request.

## 8. Chuyển từ reactive sang API mệnh lệnh

Có những boundary đòi hỏi một `T` ngay lập tức, chẳng hạn CLI `main` hoặc SDK chỉ nhận kết quả đồng bộ. Cần chọn cách rõ ràng, biết điều gì sẽ block.

### 8.1. `block(Duration)` tại imperative boundary

~~~java
public static void main(String[] args) {
    Mono<String> result = Mono.just("READY");
    String value = result.block(Duration.ofSeconds(2));
    System.out.println(value);
}
~~~

Output:

~~~text
READY
~~~

Trên Java 17+ với Reactor dependency, ví dụ đơn giản này in `READY`. `block(Duration)` chờ tín hiệu hoặc timeout; mỗi lần gọi có thể tạo một subscription mới. Không dùng `block` bên trong WebFlux controller, `WebFilter` hoặc operator trên Reactor non-blocking thread.

Reactor có thể ném `IllegalStateException` nếu `block()`/`blockFirst()`/`blockLast()` chạy trên scheduler đánh dấu non-blocking (ví dụ event-loop/parallel scheduler). Ngoài trường hợp bị cấm, blocking vẫn chiếm thread và ảnh hưởng capacity.

### 8.2. `blockOptional`, `blockFirst`, `blockLast`

| API | Kiểu kết quả | Rủi ro |
| --- | --- | --- |
| `Mono.block(timeout)` | `T` hoặc null khi empty | Chặn caller, có thể tạo subscription mới |
| `Mono.blockOptional(timeout)` | `Optional<T>` | Vẫn chặn caller |
| `Flux.blockFirst(timeout)` | Phần tử đầu, cancel phần còn lại | Có thể gây mất phần tử nếu nguồn hot |
| `Flux.blockLast(timeout)` | Phần tử cuối sau onComplete | Vô hạn nếu stream không bao giờ kết thúc |
| `Flux.toIterable()` | Iterable đọc theo kiểu blocking/pull | Có thể chờ vô hạn và giữ resource |
| `Flux.toStream()` | Java Stream đồng bộ | Cần `close()`, cẩn thận cancellation/resource |
| `Mono.toFuture()` | `CompletableFuture<T>` | Tạo subscription; `get/join` sau đó vẫn chặn nếu chưa hoàn tất |

Với dữ liệu có giới hạn cần trả `List<T>` tại boundary đồng bộ, có thể dùng:

~~~java
List<String> values = Flux.just("A", "B", "C")
    .collectList()
    .block(Duration.ofSeconds(2));
~~~

`collectList()` giữ toàn bộ phần tử trong memory. Chỉ làm khi số lượng đã được giới hạn; không chuyển stream vô hạn thành list hay cố duyệt một `Flux` lớn bằng `toIterable()` trên event-loop.

### 8.3. `toFuture()` có phải non-blocking không?

~~~java
CompletableFuture<String> future =
    webClient.get()
        .uri("/status")
        .retrieve()
        .bodyToMono(String.class)
        .toFuture();
~~~

`toFuture()` tạo bridge từ `Mono` sang `CompletableFuture` và khởi động subscription. Nếu caller đăng ký `thenApply`/`whenComplete`, nó có thể tiếp tục async. Nếu caller gọi `future.get()` hoặc `future.join()`, caller lại chặn thread.

Trong code cần trả Publisher, không tạo `toFuture()` rồi lập tức `Mono.fromFuture(...)` chỉ để quay về `Mono`; điều đó thêm boundary và thay đổi thời điểm subscribe/cancel không cần thiết.

### 8.4. Không block bên trong `map`/`flatMap`

~~~java
// Sai: chặn thread đang chạy operator.
return orderRepository.findById(id)
    .map(order -> pricingClient.price(order).block());
~~~

Thay bằng composition:

~~~java
return orderRepository.findById(id)
    .flatMap(order ->
        pricingClient.price(order)
            .map(price -> new PricedOrder(order, price)));
~~~

`PricedOrder` là DTO fragment minh họa. `flatMap` giữ reactive chain và tránh chặn thread chỉ để lấy giá trị từ một Mono khác.

## 9. Tích hợp CompletableFuture và CompletionStage

### 9.1. Future được tạo sẵn thường đã chạy

~~~java
CompletableFuture<User> eager = legacyAsyncApi.fetchUser(id);
Mono<User> mono = Mono.fromFuture(eager);
~~~

`fetchUser(id)` có thể đã khởi động I/O tại assembly. `Mono.fromFuture` chỉ nối vào kết quả Future đã có; không làm operation trở thành lazy.

### 9.2. Tạo Future khi subscribe

~~~java
Mono<User> lazy = Mono.fromFuture(
    () -> legacyAsyncApi.fetchUser(id));
~~~

Supplier chỉ được gọi khi có subscription. Với `CompletionStage` không phải `CompletableFuture`, có overload `Mono.fromCompletionStage(() -> api.fetch(id))`.

Theo Reactor API, khi `Mono.fromFuture` bị cancel, nó mặc định cố cancel `CompletableFuture`; có overload `suppressCancel` nếu không muốn truyền cancel. Tuy nhiên Future cancellation không bảo đảm HTTP request, database query hoặc task bên dưới thật sự dừng. Cần xác minh SDK có implement cancellation/interrupt hay không.

### 9.3. `toFuture` ở ranh giới đồng bộ-bất đồng bộ

Khi một Java API bắt buộc trả `CompletableFuture`:

~~~java
public CompletableFuture<Receipt> submitAsFuture(Command command) {
    return reactiveService.submit(command).toFuture();
}
~~~

Chọn boundary ở đây **có chủ đích**, không rải `toFuture()` qua từng service method. Khi Future consumer không còn cần kết quả, phải có chính sách cancel. Với operation có side-effect không idempotent, hủy chờ không nhất thiết hủy side-effect đã commit.

## 10. Tích hợp API callback một lần

Nhiều thư viện legacy có dạng:

~~~java
legacyApi.request(
    value -> handleSuccess(value),
    error -> handleError(error)
);
~~~

Để trả `Mono` thay vì tự subscribe, dùng `Mono.create`:

~~~java
Mono<String> lookup(CallbackApi api, String key) {
    return Mono.create(sink -> {
        Registration registration = api.lookup(
            key,
            sink::success,
            sink::error
        );
        sink.onDispose(registration::close);
    });
}
~~~

Đây là **fragment minh họa adapter**, cần định nghĩa `CallbackApi.lookup(key, success, error)` trả `Registration` có `close()`. Các điểm cần đảm bảo:

1. Gọi callback success/error tối đa một lần.
2. Cleanup registration cả khi complete, error hoặc cancellation.
3. Adapter không chặn thread đăng ký callback.
4. Nếu API callback chỉ thông báo progress nhiều lần, dùng `Flux.create`/`Sinks.Many` có chính sách buffer/demand phù hợp thay vì `Mono.create`.
5. Không nuốt lỗi của callback hoặc ghi ra biến shared không đồng bộ.
6. Nếu registration có thể trả về sau khi callback chạy đồng bộ, triển khai cleanup thật sự thread-safe/race-safe.

`Mono.create` là cầu nối callback, **không tự biến** underlying SDK blocking thành non-blocking. Nếu `api.lookup` thực hiện operation blocking ngay trước khi trả Registration, cần offload phần đăng ký phù hợp hoặc sửa SDK wrapper.

## 11. Push event và Reactive Streams demand

Một callback có thể phát sự kiện nhanh hơn consumer. Reactive Streams có `request(n)` để downstream điều tiết upstream; callback API có thể không có cơ chế giảm tốc tương ứng.

Khi dùng `Flux.create` hoặc `Sinks.Many`:
- Xác định event được broadcast, replay hay chỉ một subscriber.
- Có giới hạn buffer và xử lý overflow; không buffer vô hạn.
- Khi cancel, unregister listener và giải phóng buffer.
- Nếu dữ liệu bắt buộc không được mất, ưu tiên queue durable hoặc protocol flow control.
- Không giả định emitter bên ngoài tuân theo backpressure chỉ vì đã bọc thành `Flux`.

Ví dụ fragment:

~~~java
Flux<PriceEvent> prices(ListenerApi api) {
    return Flux.create(sink -> {
        Registration reg = api.register(
            event -> sink.next(event),
            sink::error,
            sink::complete
        );
        sink.onDispose(reg::close);
    });
}
~~~

`PriceEvent`, `ListenerApi`, `Registration` là kiểu của integration cần tự triển khai. Chính sách overflow và lifecycle phải được lựa chọn theo đặc tính nguồn thực tế trước khi dùng production.

## 12. Reactive transaction và Reactor Context

Một reactive transaction không được nhận diện chỉ bằng Java thread. `ReactiveTransactionManager` và `TransactionalOperator` dùng Reactor subscriber `Context` để giữ transaction-bound resource khi các operator chuyển thread.

~~~java
Mono<Receipt> process(Command command) {
    return repository.reserve(command.productId())
        .then(repository.save(command.toEntity()))
        .map(this::toReceipt)
        .as(transactionalOperator::transactional);
}
~~~

Đây là fragment khái niệm, giả định repository dùng driver reactive và `transactionalOperator` được tạo từ đúng `ReactiveTransactionManager`. Cả hai DB operations phải nằm trong cùng outer chain/subscriber Context.

Sai:

~~~java
Mono<Receipt> processWrong(Command command) {
    repository.reserve(command.productId()).subscribe();
    return repository.save(command.toEntity())
        .map(this::toReceipt);
}
~~~

Lệnh `reserve` đã rời khỏi subscription/transaction của thao tác save. Nó có thể tiếp tục sau khi request thất bại, commit ngoài boundary hoặc mất tracing/security information.

### 12.1. Context không phải ThreadLocal

`ThreadLocal` có thể thay đổi khi `publishOn`, `subscribeOn` hoặc asynchronous callback đổi thread. Truyền thông tin quan trọng trong Reactor Context hoặc context propagation integration phù hợp.

~~~java
Mono<String> currentTrace() {
    return Mono.deferContextual(ctx ->
        Mono.just(ctx.getOrDefault("traceId", "unknown")));
}

Mono<String> workflow = currentTrace()
    .contextWrite(context ->
        context.put("traceId", "trace-123"));
~~~

Đây là fragment tự chứa về Reactor Context. Giá trị context được gắn với subscription, không được lấy qua một biến global hoặc thread name.

Không lưu JWT, secret hay raw user data vào log/metric tag chỉ vì chúng đã có trong Context. Với Spring Security reactive, dùng API `ReactiveSecurityContextHolder` thay vì tự tạo ThreadLocal security context.

### 12.2. `@Transactional` và subscription

Với method reactive được proxy `@Transactional` và chọn đúng reactive transaction manager, transaction được thực hiện tại subscription time. Tự subscribe bên trong method khiến operation đó đi ra khỏi transaction ngầm của caller.

JDBC/JPA `PlatformTransactionManager` dùng thread-bound resources; nó không tự tham gia R2DBC transaction. Nếu tích hợp JPA blocking, giữ toàn bộ transaction JPA trong một lời gọi synchronous và offload boundary như mục 7. Không kỳ vọng một `@Transactional` bao cả JPA và R2DBC tự tạo atomic distributed transaction.

## 13. Cancellation và resource cleanup

Khi client HTTP ngắt kết nối, WebFlux có thể cancel Publisher đang phục vụ response. Nếu code giữ một subscription phụ, cancellation từ request không tự cancel subscription đó.

Pipeline tự nhiên:

~~~java
return webClient.get()
    .uri("/large-report")
    .retrieve()
    .bodyToFlux(ReportPart.class)
    .doOnCancel(() -> metrics.recordCancelled())
    .doFinally(signal -> metrics.recordFinished(signal));
~~~

`doFinally` nhận `SignalType` để phân biệt `ON_COMPLETE`, `ON_ERROR` và `CANCEL`. Không dùng `doFinally` để tự `subscribe()` một cleanup task rồi giả định caller sẽ đợi task đó.

### 13.1. `using` và `usingWhen`

Khi tự sở hữu tài nguyên:
- `using` phù hợp resource có cleanup đồng bộ.
- `usingWhen` phù hợp acquire/cleanup bất đồng bộ, ví dụ connection hoặc temporary resource mở/đóng qua Publisher.
- Cleanup cần có nhánh complete, error và cancellation khi resource semantics đòi hỏi chúng.

Ví dụ khái niệm:

~~~java
Mono<Result> operation = Mono.usingWhen(
    asyncResourceFactory.open(),
    resource -> resource.run(),
    resource -> resource.close()
);
~~~

`asyncResourceFactory`, `Result` và `resource` là các kiểu minh họa. Với resource có rollback/cleanup khác khi lỗi hoặc cancel, dùng overload `usingWhen` có các callback `asyncComplete`, `asyncError`, `asyncCancel`. Đừng đóng resource trước khi Publisher xử lý xong.

### 13.2. Không nhầm cancel với rollback nghiệp vụ

Cancellation báo “downstream không còn cần dữ liệu”. Nó không thể hoàn tác một write đã commit ở database hoặc một payment gateway đã thực hiện charge. Với operation có side-effect bắt buộc, dùng idempotency key, durable outbox/job và trạng thái nghiệp vụ rõ ràng; không dựa vào cancellation như một transaction rollback tổng quát.

## 14. Subscribe hai lần có thể chạy operation hai lần

~~~java
Mono<Receipt> operation = paymentClient.charge(command);

operation.subscribe();
operation.subscribe();
~~~

Với cold Publisher gọi HTTP, hai subscription có thể gửi **hai payment requests**. Trong ứng dụng thật, đó là bug nghiêm trọng. Dùng idempotency key và chỉ subscribe ở boundary quản lý.

Cũng cần lưu ý:

~~~java
Mono<Receipt> operation = paymentClient.charge(command);

Receipt a = operation.block(Duration.ofSeconds(5));
Receipt b = operation.block(Duration.ofSeconds(5));
~~~

Hai lần `block` có thể tạo hai subscription và thực hiện lại side-effect.

### 14.1. `cache()`/`share()` không phải thuốc chữa mặc định

`cache()` có thể memoize kết quả cho các subscriber sau, nhưng làm thay đổi semantics và lifecycle. Khi data theo user/tenant, cache dùng chung sai scope có thể làm lộ dữ liệu hoặc trả giá trị stale. Với payment hoặc write operation, idempotency ở tầng business vẫn cần ngay cả khi dùng cache.

Cẩn thận khi chọn cache TTL, memory limit, error caching và stale data. Không thêm `cache()` chỉ để che một lỗi nested subscription.

## 15. Giới hạn dùng `block()` trong WebFlux

### 15.1. Tại sao event-loop nhạy cảm?

Netty event-loop thường phục vụ nhiều socket với số thread nhỏ. Nếu gọi JDBC, `Thread.sleep`, `Future.get` hoặc `Mono.block` trên thread đó, nhiều request khác phải chờ.

~~~text
WebFlux event loop
   |
   +-- handle Request A
   |       |
   |       +-- block 2 seconds  <-- chiếm thread
   |
   +-- Request B, C, D cùng thread phải chờ
~~~

R2DBC hoặc WebClient reactive không giữ thread chờ I/O theo cùng mô hình JDBC. Tuy nhiên CPU-bound work lớn cũng có thể chiếm event-loop; có thể cần scheduler riêng, phân tải hoặc bounded executor.

### 15.2. Boundary được chấp nhận

`block(timeout)` có thể hợp lý tại:
- `main` của một command-line tool ngắn.
- Một lệnh migration hoặc batch synchronous có timeout.
- Unit test ngoài event-loop (dù `StepVerifier` thường tốt hơn).
- Adapter tạm thời cho library chỉ nhận value synchronous, với capacity budget rõ ràng.

`block()` trong WebFlux controller/service/filter đang xử lý request thì không phù hợp. Nếu phần lớn hệ thống đều imperative, **Spring MVC + JDBC/JPA** thường đơn giản hơn ép mọi lời gọi vào `Mono` rồi lại block.

### 15.3. Virtual threads không biến blocking thành reactive

Virtual threads (trên JDK hỗ trợ) có thể giảm chi phí thread chờ, nhưng không làm JDBC API non-blocking, không thay đổi transaction model hoặc năng lực database. Demo Java 17 không dựa trên virtual threads. Hãy chọn kiến trúc nhất quán thay vì coi `subscribe()`/`block()` là kỹ thuật tối ưu vô điều kiện.

## 16. Ví dụ hoàn chỉnh: WebFlux gọi một hệ thống blocking legacy và một API reactive

Project minh họa có thể chạy không cần database hoặc external API:
- `LegacyOrderGateway` giả lập API đồng bộ bằng `Thread.sleep` để cho thấy blocking boundary.
- `ReactiveAuditGateway` giả lập thao tác async non-blocking bằng `Mono.delay`.
- `OrderBoundaryService` nối hai thao tác, không gọi `.subscribe()` và không block event-loop.
- Controller trả Mono để WebFlux quản lý subscription.
- Test `StepVerifier` và HTTP integration test kiểm tra thứ tự, lazy execution, 404 và lỗi.

**Các legacy gateway trong demo là mô phỏng có chủ đích**, không phải JDBC driver thật. Khi thay bằng JDBC/JPA, cần cấu hình DataSource/pool/transaction ở module legacy, giữ pattern `fromCallable + boundedElastic` và không bỏ các giới hạn concurrency.

### 16.1. Cấu trúc thư mục

~~~text
reactive-boundary-demo/
├── pom.xml
├── src/main/java/com/example/boundary/
│   ├── BoundaryApplication.java
│   ├── OrderView.java
│   ├── AuditReceipt.java
│   ├── LegacyOrderGateway.java
│   ├── ReactiveAuditGateway.java
│   ├── OrderBoundaryService.java
│   └── OrderBoundaryController.java
└── src/test/java/com/example/boundary/
    ├── OrderBoundaryServiceTest.java
    └── OrderBoundaryHttpTest.java
~~~

### 16.2. pom.xml

Spring Boot 4.0.9 và Java 17+. Trong Boot 4, starter WebFlux runtime và starter WebFlux test là các artifact riêng.

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>4.0.9</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>reactive-boundary-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Parent quản lý version của Spring/Reactor. Không cần khai báo version riêng cho `reactor-test` khi dùng dependency management của Spring Boot.

### 16.3. BoundaryApplication.java

~~~java
package com.example.boundary;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class BoundaryApplication {

    public static void main(String[] args) {
        SpringApplication.run(BoundaryApplication.class, args);
    }
}
~~~

### 16.4. OrderView.java và AuditReceipt.java

`OrderView.java`:

~~~java
package com.example.boundary;

public record OrderView(String id, String status) {}
~~~

`AuditReceipt.java`:

~~~java
package com.example.boundary;

public record AuditReceipt(String id, String outcome) {}
~~~

Chúng là immutable DTO, tách biệt với các thành phần thực hiện I/O.

### 16.5. LegacyOrderGateway.java

~~~java
package com.example.boundary;

import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.stereotype.Component;

@Component
public class LegacyOrderGateway {

    private final AtomicInteger invocations = new AtomicInteger();

    public OrderView find(String id) {
        invocations.incrementAndGet();

        try {
            // Giả lập một lời gọi JDBC/JPA hoặc SDK đồng bộ.
            Thread.sleep(40);
        }
        catch (InterruptedException error) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException(
                "legacy operation interrupted", error);
        }

        if ("missing".equals(id)) {
            return null;
        }

        return new OrderView(id, "READY");
    }

    public int invocationCount() {
        return invocations.get();
    }
}
~~~

`Thread.sleep` chỉ nằm trong gateway giả lập để thể hiện nguồn blocking. Không dùng `Thread.sleep` trong controller hoặc reactive operator thực tế. Khi thay gateway bằng JPA, mọi thao tác đồng bộ và transaction phải nằm trong phương thức gateway/transaction service và được offload qua service wrapper.

### 16.6. ReactiveAuditGateway.java

~~~java
package com.example.boundary;

import java.time.Duration;

import org.springframework.stereotype.Component;

import reactor.core.publisher.Mono;

@Component
public class ReactiveAuditGateway {

    public Mono<Void> record(OrderView order) {
        return Mono.delay(Duration.ofMillis(40))
            .flatMap(ignored -> {
                if ("fail".equals(order.id())) {
                    return Mono.<Void>error(
                        new IllegalStateException(
                            "simulated audit failure"));
                }
                return Mono.<Void>empty();
            });
    }
}
~~~

`Mono.delay` giả lập I/O completion mà không `Thread.sleep`. Đường `"fail"` phát error signal; outer chain phải truyền lỗi tới HTTP response, không trả thành công giả. Trong ứng dụng thật, thay method bằng WebClient/R2DBC reactive call.

### 16.7. OrderBoundaryService.java

~~~java
package com.example.boundary;

import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.web.server.ResponseStatusException;

import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

@Service
public class OrderBoundaryService {

    private final LegacyOrderGateway legacyOrderGateway;
    private final ReactiveAuditGateway reactiveAuditGateway;

    public OrderBoundaryService(
            LegacyOrderGateway legacyOrderGateway,
            ReactiveAuditGateway reactiveAuditGateway) {
        this.legacyOrderGateway = legacyOrderGateway;
        this.reactiveAuditGateway = reactiveAuditGateway;
    }

    public Mono<OrderView> find(String id) {
        return Mono.fromCallable(() ->
                legacyOrderGateway.find(id))
            .subscribeOn(Schedulers.boundedElastic())
            .switchIfEmpty(Mono.error(
                new ResponseStatusException(
                    HttpStatus.NOT_FOUND, "order not found")));
    }

    public Mono<AuditReceipt> audit(String id) {
        return find(id)
            .flatMap(order ->
                reactiveAuditGateway.record(order)
                    .thenReturn(
                        new AuditReceipt(order.id(), "AUDITED")));
    }
}
~~~

Đây là phần trọng tâm:
- `fromCallable` làm source lazy; khi chưa có subscriber, `LegacyOrderGateway.find` chưa chạy.
- `subscribeOn(boundedElastic())` offload nguồn blocking khỏi Netty event-loop.
- `switchIfEmpty` tạo lỗi 404 nếu gateway trả null.
- `flatMap` nối audit vào cùng subscription.
- `thenReturn` chỉ trả receipt khi audit hoàn tất bình thường.
- Nếu audit phát lỗi, HTTP không nhận `AUDITED`; không có nested `subscribe()`.

### 16.8. OrderBoundaryController.java

~~~java
package com.example.boundary;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api/orders")
public class OrderBoundaryController {

    private final OrderBoundaryService service;

    public OrderBoundaryController(OrderBoundaryService service) {
        this.service = service;
    }

    @GetMapping("/{id}")
    public Mono<OrderView> get(@PathVariable String id) {
        return service.find(id);
    }

    @PostMapping("/{id}/audit")
    public Mono<AuditReceipt> audit(@PathVariable String id) {
        return service.audit(id);
    }
}
~~~

Không có `.subscribe()`, `.block()` hay `.toFuture()` trong controller. Spring WebFlux là owner của subscription và chờ publisher hoàn thành để tạo response.

### 16.9. OrderBoundaryServiceTest.java

~~~java
package com.example.boundary;

import java.time.Duration;
import java.util.concurrent.atomic.AtomicBoolean;

import org.junit.jupiter.api.Test;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class OrderBoundaryServiceTest {

    @Test
    void blockingGatewayIsLazyUntilSubscription() {
        LegacyOrderGateway legacy = new LegacyOrderGateway();
        ReactiveAuditGateway audit = new ReactiveAuditGateway();
        OrderBoundaryService service =
            new OrderBoundaryService(legacy, audit);

        Mono<OrderView> pipeline = service.find("42");

        assertEquals(0, legacy.invocationCount());

        StepVerifier.create(pipeline)
            .expectNext(new OrderView("42", "READY"))
            .verifyComplete();

        assertEquals(1, legacy.invocationCount());
    }

    @Test
    void auditCompletesBeforeReceiptIsEmitted() {
        OrderBoundaryService service =
            new OrderBoundaryService(
                new LegacyOrderGateway(),
                new ReactiveAuditGateway());

        StepVerifier.create(service.audit("42"))
            .expectNext(new AuditReceipt("42", "AUDITED"))
            .verifyComplete();
    }

    @Test
    void innerAuditFailureReachesOuterSubscriber() {
        OrderBoundaryService service =
            new OrderBoundaryService(
                new LegacyOrderGateway(),
                new ReactiveAuditGateway());

        StepVerifier.create(service.audit("fail"))
            .expectErrorMatches(error ->
                error instanceof IllegalStateException
                    && error.getMessage().contains(
                        "simulated audit failure"))
            .verify();
    }

    @Test
    void cancellationPropagatesIntoSource() {
        AtomicBoolean cancelled = new AtomicBoolean();

        Flux<Long> source = Flux.interval(
                Duration.ofMillis(10))
            .doOnCancel(() -> cancelled.set(true));

        StepVerifier.create(source)
            .expectNext(0L)
            .thenCancel()
            .verify(Duration.ofSeconds(2));

        assertTrue(cancelled.get());
    }

    @Test
    void operatorDoesNotRunUntilSubscribed() {
        AtomicBoolean called = new AtomicBoolean();

        Mono<String> pipeline = Mono.fromSupplier(() -> {
            called.set(true);
            return "ok";
        });

        assertEquals(false, called.get());

        StepVerifier.create(pipeline)
            .expectNext("ok")
            .verifyComplete();

        assertTrue(called.get());
    }
}
~~~

Tests xác minh lazy source, audit completion, error propagation và cancellation. Chúng dùng StepVerifier làm subscriber, không tự `.subscribe()` rồi sleep để chờ result. Test cancellation đo tín hiệu Reactor; nó không khẳng định mọi JDBC/SDK có thể bị hủy ngay lập tức.

### 16.10. OrderBoundaryHttpTest.java

~~~java
package com.example.boundary;

import java.time.Duration;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class OrderBoundaryHttpTest {

    @Value("${local.server.port}")
    int port;

    private WebTestClient http() {
        return WebTestClient.bindToServer()
            .baseUrl("http://localhost:" + port)
            .responseTimeout(Duration.ofSeconds(5))
            .build();
    }

    @Test
    void getUsesLegacyBoundaryWithoutBlockingWebFlux() {
        http().get()
            .uri("/api/orders/42")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.id").isEqualTo("42")
            .jsonPath("$.status").isEqualTo("READY");
    }

    @Test
    void auditWaitsForReactiveSideEffect() {
        http().post()
            .uri("/api/orders/42/audit")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.id").isEqualTo("42")
            .jsonPath("$.outcome").isEqualTo("AUDITED");
    }

    @Test
    void missingOrderReturns404() {
        http().get()
            .uri("/api/orders/missing")
            .exchange()
            .expectStatus().isNotFound();
    }

    @Test
    void auditFailureDoesNotReturnSuccess() {
        http().post()
            .uri("/api/orders/fail/audit")
            .exchange()
            .expectStatus().is5xxServerError();
    }
}
~~~

HTTP tests chứng minh endpoint, status và JSON contract hoạt động khi WebFlux quản lý subscription. Chúng không chứng minh bằng thời gian đơn lẻ rằng server hoàn toàn non-blocking; để làm điều đó cần profiler, BlockHound trong môi trường test phù hợp, connection pool metrics và load test.

### 16.11. Chạy project

Yêu cầu Java 17+ và Maven:

~~~bash
java -version
mvn -version
mvn test
mvn spring-boot:run
~~~

Trong Windows CMD, thử:

~~~bat
curl -i http://localhost:8080/api/orders/42
curl -i -X POST http://localhost:8080/api/orders/42/audit
curl -i http://localhost:8080/api/orders/missing
curl -i -X POST http://localhost:8080/api/orders/fail/audit
~~~

Kết quả kỳ vọng:

| Request | Status | Body hoặc ý nghĩa |
| --- | --- | --- |
| GET `/api/orders/42` | 200 | `{"id":"42","status":"READY"}` |
| POST `/api/orders/42/audit` | 200 | `{"id":"42","outcome":"AUDITED"}` chỉ sau audit complete |
| GET `/api/orders/missing` | 404 | Error response do WebFlux tạo |
| POST `/api/orders/fail/audit` | 5xx | Audit error không bị che bởi response thành công |

Với đường audit, tổng thời gian phản hồi bao gồm lời gọi legacy chặn (đã offload) cộng thời gian audit reactive; việc response chờ đủ hai bước là **đúng contract**. Các con số delay chỉ dùng để mô phỏng.

## 17. Kiểm tra bằng kiến trúc thay vì chỉ “đếm subscribe”

Không cấm `subscribe()` trong toàn bộ codebase. Vấn đề là vị trí và trách nhiệm. Quy trình kiểm tra:

1. Tìm mọi `subscribe(` và xác định caller/framework đã có subscription hay chưa.
2. Nếu ở controller/service/filter, thử thay bằng operator composition.
3. Nếu ở imperative entry point, phải thấy error consumer, Disposable owner, cancel/shutdown và metrics.
4. Tìm `block(`, `blockFirst`, `blockLast`, `toIterable`, `toStream`, `toFuture`, `Future.get`, `join`, `Thread.sleep`.
5. Xác định chúng có chạy trên Netty event-loop hay scheduler non-blocking không.
6. Với blocking I/O, tạo lazy source và offload đúng boundary; không chỉ đổi kiểu trả về thành Mono.
7. Với nguồn future/callback, kiểm tra lazy execution và cancellation của SDK.
8. Với database, kiểm tra transaction manager/thread-bound vs Reactor Context.
9. Với HTTP outbound, kiểm tra response body đã được consume/release.
10. Kiểm tra lỗi inner operation có truyền về caller, không bị mất trong nested subscription.
11. Kiểm tra các side-effects bắt buộc completion có dùng `flatMap/then` không.
12. Kiểm tra số lần subscription với operation có side-effect; thêm idempotency khi cần.

### 17.1. Dấu hiệu cần alert

- Request HTTP trả 2xx nhưng audit/payment/DB write vẫn thất bại sau đó.
- `ErrorCallbackNotImplemented` hoặc lỗi “dropped” không gắn với request ID.
- CPU/event-loop latency tăng khi thêm JDBC/SDK đồng bộ.
- Số active tasks tăng dù clients đã disconnect.
- Thread pool `boundedElastic` và Hikari pending queue tăng đồng thời.
- Duplicate outbound POST khi retry hoặc subscribe nhiều lần.
- Reactive transaction rollback nhưng một side-effect ở subscription tách vẫn commit.

## 18. Sai lầm thường gặp và cách sửa

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| `.subscribe()` trong controller | Framework không chờ task, lỗi/cancel bị tách | Return Publisher |
| `.subscribe()` trong `map` | Tạo nested subscription | `flatMap`/`then` |
| `.subscribe()` trong `doOnNext` để ghi audit | Không ràng buộc completion nghiệp vụ | `flatMap` và `thenReturn` |
| `Mono.just(blockingCall())` | Blocking chạy eager | `fromCallable` + `subscribeOn(boundedElastic)` |
| `publishOn` sau lời gọi eager | Đổi thread quá muộn | Tạo lazy source trước |
| `block()` trên Netty event-loop | Chặn request khác hoặc bị từ chối | Compose reactive chain |
| `Flux.blockLast()` với nguồn vô hạn | Không bao giờ complete | Giới hạn stream và timeout |
| `toIterable()` trên dữ liệu không giới hạn | Blocking và memory pressure | Duy trì Flux hoặc phân trang |
| `Mono.toFuture().get()` trong handler | Blocking vòng về | Dùng Mono trực tiếp |
| `Mono.fromFuture(alreadyRunningFuture)` rồi nghĩ lazy | Future có thể đã chạy | Supplier overload |
| Callback không unregister | Leak listener/resource khi cancel | `sink.onDispose` |
| Một nguồn cold có nhiều subscriber | Side-effect chạy lại | Một owner và idempotency |
| `onErrorResume(error -> Mono.empty())` mọi lỗi | Che 401/503/timeouts | Fallback theo loại lỗi |
| `zip` với `Mono<Void>` | Combiner không chạy do nguồn empty | `then` hoặc `when` |
| `collectList()` toàn bộ stream vô hạn | Không bounded memory | Backpressure + LIMIT/stream |
| Dùng `boundedElastic` không giới hạn demand | Scheduler và DB pool saturation | Bulkhead, concurrency, timeout |
| Manual subscribe trong reactive transaction | Mất Context/transaction liên quan | Compose một chain |
| Giả định cancellation rollback payment | External write có thể đã commit | Idempotency/outbox/job state |
| `doOnError` thay cho error recovery | Lỗi vẫn propagate | `onErrorMap`/`onErrorResume` |
| Không đóng `toStream()` | Có thể giữ resource | `try-with-resources` nếu dùng |
| Fire-and-forget cho tác vụ bắt buộc | Task mất khi process crash | Durable queue/outbox |

## 19. Chiến lược chuyển đổi code mệnh lệnh sang reactive

Không cần chuyển toàn bộ hệ thống một lần. Có thể làm theo các bước:

1. **Xác định entry point:** controller WebFlux, listener imperative, scheduled job, CLI hoặc callback.
2. **Chọn hướng nhất quán:** inbound/reactive service trả Mono/Flux; imperative boundary có thể block hoặc subscribe với ownership.
3. **Khoanh vùng blocking APIs:** JDBC/JPA, RestTemplate, filesystem, SDK sync, `Future.get`.
4. **Offload tạm thời:** wrapper bằng lazy source và bounded scheduler; log latency và giới hạn concurrency.
5. **Thay bằng native reactive API khi đáng giá:** WebClient, R2DBC, reactive drivers.
6. **Chuyển sequencing thành operators:** `flatMap`, `then`, `when` thay nested subscribe.
7. **Làm rõ transaction:** không tự tách operation trong transaction.
8. **Thống nhất error contract:** map nguyên nhân đúng; timeout/cancel không bị che.
9. **Test correctness trước throughput:** completion, errors, cancellation, one subscription.
10. **Benchmark thật:** CPU, memory, request p95/p99, worker/event-loop latency, DB pool và target SLO.

Nếu phần lớn workload vẫn là blocking I/O và JPA ORM phức tạp, cân nhắc giữ Spring MVC + JPA thay vì ép code imperative vào WebFlux rồi dùng `block()` khắp nơi.

## 20. Bài tập thực hành

**Bài 1 – Lazy và eager.** Dùng `AtomicInteger`, so sánh `Mono.just(counter.incrementAndGet())` với `Mono.fromSupplier(counter::incrementAndGet)` trước/sau subscription.

**Bài 2 – Sửa nested subscribe.** Cho `save` thành công nhưng `audit` thất bại. Chứng minh code cũ trả 200; đổi sang `flatMap/thenReturn` để lỗi đi tới outer subscriber.

**Bài 3 – Offload legacy.** Gọi một SDK đồng bộ giả lập bằng `Thread.sleep`. Bọc trong `fromCallable` và `boundedElastic`, đo event-loop responsiveness.

**Bài 4 – Timeout.** Thêm `timeout` cho audit. Ghi nhận error signal/cancel, phân biệt với rollback nghiệp vụ thực tế.

**Bài 5 – CompletableFuture.** Viết một async API ghi nhận số lần bắt đầu. So sánh `Mono.fromFuture(api.fetch())` và `Mono.fromFuture(() -> api.fetch())`.

**Bài 6 – CLI boundary.** Trong `main`, dùng `block(Duration)` để lấy một giá trị với timeout; giữ WebFlux controller không block.

**Bài 7 – Repeated subscription.** Một `Mono.defer` có counter: subscribe hai lần, xác nhận side-effect chạy hai lần. Thiết kế idempotency.

**Bài 8 – Callback adapter.** Dùng `Mono.create`, gửi callback success/error và kiểm tra unregister khi cancellation.

**Bài 9 – Transaction Context.** Tạo hai R2DBC operations trong `TransactionalOperator`, rồi thử cố tình dùng nested subscribe và kiểm tra sự khác biệt trong rollback.

**Bài 10 – Concurrency.** Dùng `Flux.range` và `flatMap(..., 8)` gọi legacy adapter, quan sát worker/pool; so sánh với `flatMap` concurrency không được giới hạn.

**Bài 11 – Security Context.** Đọc trace ID bằng `Mono.deferContextual`, chuyển scheduler và xác nhận Context vẫn đi qua outer chain; so sánh với subscription tách.

**Bài 12 – HTTP.** Chạy demo mục 16, kiểm tra 200/404/5xx và xem việc audit response chỉ phát khi operation hoàn tất.

## 21. Checklist production

- [ ] WebFlux controller/filter không tự `.subscribe()` hoặc `.block()` nghiệp vụ.
- [ ] Mỗi task có subscription owner rõ ràng.
- [ ] Side-effect bắt buộc được compose vào outer chain.
- [ ] Lỗi của inner operation tới được caller hoặc được map theo policy.
- [ ] Subscription thủ công ở boundary có error handler, Disposable và shutdown/cancel.
- [ ] Không dùng `Mono.just(blockingCall())`.
- [ ] Blocking I/O được đưa vào lazy wrapper và bounded scheduler.
- [ ] Có giới hạn concurrency/bulkhead, DB pool và timeout.
- [ ] Không chuyển Mono ↔ Future nhiều lần không cần thiết.
- [ ] `Future.get/join`, `toIterable`, `toStream` không chạy trên event-loop.
- [ ] Cold publisher có side-effect được bảo vệ bằng idempotency.
- [ ] Transaction và security Context không bị tách bởi nested subscription.
- [ ] Reactive resource cleanup xử lý completion, error và cancellation.
- [ ] Adapter callback unregister khi không còn subscriber.
- [ ] Không buffer stream vô hạn.
- [ ] Test kiểm tra lazy execution, completion, error, cancellation và repeated subscription.
- [ ] Có observability cho abandoned tasks, errors, queues và blocking calls.
- [ ] Không log PII, token hoặc stack trace nhạy cảm cho client.
- [ ] Có chiến lược durable execution cho job bắt buộc không được mất.
- [ ] Kiến trúc WebFlux hoặc MVC được chọn theo workload và dependency thực tế.

## 22. Tài liệu tham khảo chính thức

1. Reactor Reference – Introduction, assembly, subscribe, backpressure, hot/cold: https://projectreactor.io/docs/core/release/reference/reactiveProgramming.html
2. Reactor Reference – Subscribe patterns, Disposable và cancel: https://projectreactor.io/docs/core/release/reference/coreFeatures/simple-ways-to-create-a-flux-or-mono-and-subscribe-to-it.html
3. Reactor Reference – Threading and Schedulers: https://projectreactor.io/docs/core/release/reference/coreFeatures/schedulers.html
4. Reactor Reference – Wrapping Blocking Calls: https://projectreactor.io/docs/core/release/reference/faq.html
5. Reactor Javadoc – `Mono.fromCallable`, `fromFuture`, `toFuture`, `usingWhen`: https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Mono.html
6. Spring Framework – WebFlux annotated controllers: https://docs.spring.io/spring-framework/reference/web/webflux/controller.html
7. Spring Framework – Reactive WebClient: https://docs.spring.io/spring-framework/reference/web/webflux-webclient.html
8. Spring Framework – Reactive transactions: https://docs.spring.io/spring-framework/reference/data-access/transaction/programmatic.html
9. Spring Framework – Declarative transaction semantics: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-decl-explained.html
10. Spring Boot 4.0 – WebFlux and test starter coordinates: https://docs.spring.io/spring-boot/4.0/appendix/dependency-versions/coordinates.html
11. Spring Boot 4.0.9 release: https://spring.io/blog/2026/10/23/spring-boot-4-0-9-available-now/

**Tự đánh giá cuối:** Vì sao `Mono.just(jpa.find(...))` đã block trước `subscribeOn`? Khi `audit().subscribe()` trong controller lỗi, ai nhận lỗi và có thể HTTP 200 đã trả chưa? Khi nào dùng `flatMap` thay `map`? Vì sao `block()` có thể tạo subscription mới? Khi nào `Mono.fromFuture(() -> ...)` khác `Mono.fromFuture(future)`? Nếu client disconnect, subscription nào bị cancel? Nếu câu trả lời của bạn phân biệt được ownership, execution, error, cancellation và transaction boundaries, bạn đã nắm được giới hạn của việc tách reactive chain bằng `subscribe()` hoặc quay lại API mệnh lệnh.
