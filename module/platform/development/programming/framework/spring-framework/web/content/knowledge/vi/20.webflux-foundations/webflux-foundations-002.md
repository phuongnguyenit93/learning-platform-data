# Mono, Flux và ý nghĩa của không có, một hoặc nhiều giá trị trong Spring WebFlux

## 1. Mục tiêu của bài học

Khi bắt đầu học Spring WebFlux, hai kiểu dễ gặp nhất là `Mono<T>` và `Flux<T>`. Chúng có vẻ như “một object” và “một List” nhưng cách hiểu đó **không chính xác**. Cả hai đều là **Publisher** theo Reactive Streams, mô tả quá trình phát tín hiệu theo thời gian. Chúng biểu diễn **khả năng nhận một chuỗi giá trị**, không đơn thuần là một object đã có sẵn trong bộ nhớ.

- `Mono<T>`: phát **0 hoặc 1** giá trị kiểu `T`, sau đó kết thúc thành công, **hoặc** phát tín hiệu lỗi. Mono cũng có thể không kết thúc nếu publisher không bao giờ phát terminal signal.
- `Flux<T>`: phát **0 đến N** giá trị kiểu `T` (N có thể rất lớn hoặc không giới hạn), sau đó kết thúc thành công, **hoặc** phát lỗi. Publisher dài hạn có thể tiếp tục cho tới khi bị hủy.
- **Không có giá trị** trong reactive stream là một trạng thái có nghĩa: `onComplete` mà không có `onNext`, không phải Java `null` được phát như một giá trị.
- **Một giá trị** là một tín hiệu `onNext(value)`; khi sequence kết thúc thành công sẽ có `onComplete`.
- **Nhiều giá trị** là nhiều `onNext(value)` trước một terminal signal; cần quan tâm tới demand, cancellation và backpressure.

Đây là chủ đề nền tảng của WebFlux vì controller, WebClient, reactive repository và streaming API đều phải chọn một kiểu phản ánh **cardinality** thật sự của kết quả.

### Sau bài này bạn sẽ làm được

1. Đọc chuỗi tín hiệu Reactive Streams `onSubscribe → onNext* → (onComplete | onError)` và phân biệt **empty**, **single**, **multiple**, **error**, **never**.
2. Chọn `Mono<T>`, `Mono<Void>`, `Flux<T>` và `Mono<List<T>>` phù hợp với nghiệp vụ HTTP.
3. Hiểu các factory methods: `Mono.just`, `justOrEmpty`, `empty`, `error`, `fromCallable`, `defer`; `Flux.just`, `fromIterable`, `range`, `empty`, `error`.
4. Dùng `map`, `flatMap`, `filter`, `switchIfEmpty`, `defaultIfEmpty`, `collectList`, `next`, `single`, `singleOrEmpty`, `then`, `onErrorResume` mà không đánh mất ý nghĩa số lượng kết quả.
5. Phân biệt **assembly** với **subscription**, cold/hot publisher, backpressure, cancellation, threading và ảnh hưởng của việc `block()`.
6. Tạo Spring Boot WebFlux API thực tế với endpoints trả Mono và Flux, trả 404 khi Mono trống, JSON array và SSE.
7. Dùng `StepVerifier` và `WebTestClient` để kiểm tra giá trị, completion, error, 404 và HTTP streaming.

**Bối cảnh:** Java 17+, Spring Framework 6.x / Spring Boot 3.x, Reactor Core 3.x và Spring WebFlux. API của `reactor.core.publisher.Mono`/`Flux` không phải Java `Optional`, `Stream`, `Future`, hay `java.util.concurrent.Flow.Publisher` dù các abstractions có những ý tưởng liên quan.

## 2. Reactive Streams: không chỉ dữ liệu, mà còn có tín hiệu

`Mono` và `Flux` của Project Reactor triển khai `org.reactivestreams.Publisher<T>`. Một downstream `Subscriber<T>` đăng ký với Publisher, nhận `Subscription` và có thể yêu cầu dữ liệu theo một số lượng `request(n)`.

Giao thức tín hiệu cơ bản:

```text
Publisher<T>
     │
     │ subscriber.subscribe(...)
     ▼
onSubscribe(subscription)
     │
     ├── subscription.request(n)  ← downstream yêu cầu dữ liệu
     │
     ├── onNext(item #1)
     ├── onNext(item #2)
     ├── ...
     │
     └── một trong hai:
           onComplete()   ← thành công và không còn dữ liệu
           onError(err)   ← lỗi terminal
```

Một chuỗi tuân thủ Reactive Streams không được phát thêm `onNext` sau terminal signal; `onComplete` và `onError` loại trừ nhau. Subscriber cũng có thể gọi `cancel()` để hủy; cancellation không nên bị diễn giải như một sự kiện nghiệp vụ thành công.

### 2.1. Mono có bao nhiêu onNext?

**Mono rỗng:**

```text
onSubscribe
onComplete
          → 0 onNext
```

**Mono có một giá trị:**

```text
onSubscribe
onNext("OK")
onComplete
          → 1 onNext
```

**Mono bị lỗi:**

```text
onSubscribe
onError(IllegalStateException)
          → 0 onNext, kết thúc thất bại
```

`Mono<T>` có tối đa một `onNext` thành công. Một `Mono.never()` thì không phát onNext, onComplete hay onError cho tới lúc bị cancel — vì thế “0..1” nói về **số phần tử có thể phát**, không cam kết thời gian kết thúc.

### 2.2. Flux có bao nhiêu onNext?

```text
Flux.empty()        onSubscribe → onComplete

Flux.just("A")      onSubscribe → onNext(A) → onComplete

Flux.just("A","B")  onSubscribe → onNext(A) → onNext(B) → onComplete

Flux.error(ex)      onSubscribe → onError(ex)

Flux.interval(...)  onSubscribe → onNext(0) → onNext(1) → ...
                    (có thể chạy không giới hạn nếu không take/cancel)
```

`Flux` không mặc nhiên có nhiều phần tử. `Flux.empty()` là hoàn toàn hợp lệ, và `Flux.just(1)` cũng là Flux. Khác biệt quan trọng là **contract**: loại này cho phép nhiều phần tử; không phải thực tế mọi subscription đều nhận nhiều giá trị.

### 2.3. Các trạng thái không đồng nghĩa với nhau

| Trạng thái | Có onNext? | Terminal signal? | Ý nghĩa |
| --- | ---: | --- | --- |
| `Mono.empty()` | 0 | `onComplete` | Thành công, không có item |
| `Mono.just(value)` | 1 | `onComplete` | Thành công, có một item |
| `Mono.error(ex)` | 0 | `onError` | Thất bại |
| `Mono.never()` | 0 | Chưa có | Pending vô thời hạn nếu không bị hủy |
| `Flux.empty()` | 0 | `onComplete` | Sequence rỗng |
| `Flux.just(a,b)` | 2 | `onComplete` | Hai phần tử |
| `Flux.error(ex)` | 0 | `onError` | Sequence lỗi |
| `Flux.just(a).concatWith(Mono.error(ex))` | 1 | `onError` | Đã có item rồi mới gặp lỗi |

**Chú ý:** `Flux` có thể phát một số item rồi mới lỗi. `Mono` không phát item rồi mới lỗi ở một subscription tuân thủ hợp đồng: sau một item, Mono thành công và kết thúc. Khi làm HTTP streaming, lỗi giữa chừng có thể xảy ra sau khi headers/body đã bắt đầu gửi; không phải lúc nào cũng đổi được sang HTTP 500 nữa.

## 3. Mono.empty() không phải Mono.just(null)

Đây là điểm cần nắm ngay vì Reactor **không cho phép null như một phần tử `onNext`**.

```java
Mono<String> present = Mono.just("hello");
Mono<String> absent  = Mono.empty();
Mono<String> nullable = Mono.justOrEmpty((String) null);
```

- `present` phát một string và hoàn tất.
- `absent` hoàn tất không phát string nào.
- `nullable` cũng là Mono rỗng.
- `Mono.just(null)` **ném `NullPointerException` ngay khi gọi factory**; không tạo được Mono hợp lệ chứa null.

Nếu nguồn synchronous trả về null và bạn muốn chuyển thành Mono empty, dùng `Mono.justOrEmpty(possiblyNull)` hoặc `Mono.fromCallable(() -> possiblyNull)` theo ngữ nghĩa API. Đừng ghép `map(x -> null)` để loại item: Reactor sẽ báo lỗi vì mapper phải trả non-null.

### 3.1. Mono<Void> mang ý nghĩa gì?

`Mono<Void>` thường đại diện **công việc không có giá trị trả về**, chỉ cần biết thành công hoặc thất bại:

```java
Mono<Void> saveOrDelete = repository.deleteById(42L);
```

Hợp đồng:

```text
thành công: onSubscribe → onComplete
thất bại:   onSubscribe → onError(exception)
```

Nó **không** có một object `Void` để subscriber sử dụng. Vì vậy:

```java
Mono<Void> done = Mono.empty();

done.map(v -> "mapped"); // lambda sẽ KHÔNG chạy
```

Nếu muốn thực hiện bước tiếp theo sau completion, dùng `then(...)` hoặc `thenReturn(value)`:

```java
Mono<String> result =
        repository.deleteById(42L)
                  .thenReturn("deleted");
```

Với API HTTP, `Mono<Void>` là biểu diễn phổ biến của completion không payload; controller cần xác định đúng status (thường `204 No Content` cho DELETE thành công). Không giả định `Mono<Void>` tự mang HTTP 204; status do Spring handler/ResponseEntity và configuration quyết định.

### 3.2. Mono.empty và Optional.empty

Một `Optional.empty()` là **giá trị Java hiện có ngay** cho biết không có object. `Mono.empty()` là một **Publisher**, có thể được subscribe rồi phát completion (có thể asynchronous). Chuyển Optional sang Mono:

```java
Optional<String> maybeName = repository.findNameById(42L);
Mono<String> name = Mono.justOrEmpty(maybeName);
```

Đây là đoạn minh họa từ synchronous repository; nếu repository truy vấn blocking thì việc **gọi `findNameById` đã chạy trước** khi tạo Mono. Bọc nó trong Mono sau đó không khiến DB call tự trở thành non-blocking. Muốn trì hoãn việc truy vấn, xem `Mono.fromCallable(...).subscribeOn(Schedulers.boundedElastic())` ở phần threading.

## 4. Chương trình Java 17 độc lập: các trường hợp cơ bản

Dùng Maven Reactor Core nếu chạy trong một project Spring Boot có `spring-boot-starter-webflux`. Chương trình có thể đặt trong `src/main/java/example/ReactorCardinalityDemo.java`. Nó không cần HTTP server.

```java
package example;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public class ReactorCardinalityDemo {

    public static void main(String[] args) {
        System.out.println("Mono present:");
        Mono.just("A")
                .subscribe(
                    value -> System.out.println("next=" + value),
                    err -> System.out.println("error=" + err),
                    () -> System.out.println("complete"));

        System.out.println("Mono empty:");
        Mono.<String>empty()
                .subscribe(
                    value -> System.out.println("next=" + value),
                    err -> System.out.println("error=" + err),
                    () -> System.out.println("complete"));

        System.out.println("Flux several:");
        Flux.just(10, 20, 30)
                .subscribe(
                    value -> System.out.println("next=" + value),
                    err -> System.out.println("error=" + err),
                    () -> System.out.println("complete"));
    }
}
```

Vì cả ba publishers là **synchronous cold factories**, không có `delayElement`, `publishOn` hay asynchronous source, stdout theo thứ tự:

```text
Mono present:
next=A
complete
Mono empty:
complete
Flux several:
next=10
next=20
next=30
complete
```

**Cẩn thận:** nếu thay bằng `Flux.interval`, WebClient hoặc producer async, `subscribe()` thường trả quyền điều khiển nhanh và output có thể đến sau; không dùng chương trình in console ngay lập tức rồi nghĩ Publisher “không phát gì”.

### 4.1. Không có subscriber thì sao?

`Mono.just("x").map(...)` tạo một pipeline/description; các operators thường **chưa xử lý dữ liệu** cho tới khi có subscription. `Mono.just(...)` bản thân nhận sẵn object tại lúc assembly, vì vậy **giá trị đưa vào `just` phải được tính trước**; không được nói mọi side effect trong mọi source luôn đợi subscribe.

Ví dụ:

```java
AtomicInteger calls = new AtomicInteger();

Mono<Integer> lazy =
    Mono.fromCallable(calls::incrementAndGet);

System.out.println(calls.get()); // 0
System.out.println(lazy.block()); // 1
System.out.println(lazy.block()); // 2
```

Ở đây `Mono.fromCallable` trì hoãn việc gọi function tới subscription, còn `block()` chủ động subscribe và chờ kết quả. **Chỉ dùng `block()` trong main/test/ranh giới imperative thích hợp, không dùng trong WebFlux request event-loop để gọi chain reactive.**

## 5. Tạo Mono và Flux: chọn đúng factory

### 5.1. Các cách tạo Mono

| Factory | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `Mono.just(value)` | Có sẵn một giá trị non-null | `Mono.just("ok")` |
| `Mono.justOrEmpty(valueOrOptional)` | Một giá trị hoặc không có | `Mono.justOrEmpty(optional)` |
| `Mono.empty()` | Complete ngay, 0 item | `Mono.<String>empty()` |
| `Mono.error(ex)` | Terminal error | `Mono.error(new IllegalStateException("x"))` |
| `Mono.defer(supplierOfMono)` | Tạo Mono mới khi subscribe | `Mono.defer(() -> Mono.just(clockValue()))` |
| `Mono.fromCallable(callable)` | Gọi Callable khi subscribe, null → empty | `Mono.fromCallable(() -> blockingRead())` |
| `Mono.fromSupplier(supplier)` | Gọi Supplier khi subscribe | `Mono.fromSupplier(() -> "hello")` |
| `Mono.never()` | Không tự emit/complete/error | `Mono.<String>never()` |
| `Mono.delay(duration)` | Phát một `Long` sau delay | `Mono.delay(Duration.ofSeconds(1))` |

**Không dùng `Mono.just(expensiveCall())` để trì hoãn `expensiveCall()`**, vì biểu thức argument được tính trước khi factory được gọi. Dùng `Mono.fromCallable(...)` hoặc `Mono.defer(...)` nếu cần lazy semantics.

### 5.2. Các cách tạo Flux

| Factory | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `Flux.just(a,b,c)` | Một dãy giá trị đã có | `Flux.just(1,2,3)` |
| `Flux.fromIterable(iterable)` | Duyệt collection khi subscribe | `Flux.fromIterable(List.of(1,2))` |
| `Flux.range(start,count)` | Dãy số nguyên hữu hạn | `Flux.range(5,3)` phát 5,6,7 |
| `Flux.empty()` | Hoàn tất không có item | `Flux.<String>empty()` |
| `Flux.error(ex)` | Terminal error | `Flux.error(new IllegalStateException())` |
| `Flux.defer(factory)` | Tạo publisher tại subscription | `Flux.defer(() -> fetchCurrentItems())` |
| `Flux.interval(duration)` | Phát số tăng dần theo nhịp scheduler | `Flux.interval(Duration.ofSeconds(1))` |
| `Flux.from(publisher)` | Adapt Publisher | `Flux.from(otherPublisher)` |
| `Flux.generate(...)` | Stateful synchronous sink 1 item mỗi vòng | Cần state/termination rõ |
| `Flux.create(...)` | Bridge callback producer | Cần xử lý demand/backpressure/cancellation |

**Không mặc định dùng `Flux.create` hoặc `Sinks` cho mọi collection.** Với danh sách sẵn có, `Flux.fromIterable` đơn giản và an toàn hơn nhiều.

### 5.3. Flux.range: count, không phải endInclusive

`Flux.range(5, 3)` phát 5, 6, 7. Tham số thứ hai là **số phần tử**, không phải giá trị kết thúc. Với `Flux.range(1, 0)`, Publisher hoàn tất không phát phần tử.

### 5.4. Tạo nguồn khi subscribe để phản ánh dữ liệu mới

`Mono.just(service.readNow())` chạy `readNow()` lúc assembly. Nếu đó là một truy vấn DB blocking, bạn đã block ngay tại điểm tạo Mono.

`Mono.defer(() -> Mono.justOrEmpty(repository.findById(id)))` trì hoãn cuộc gọi đến lúc subscription, nhưng **vẫn blocking** nếu repository là JDBC/JPA synchronous. Muốn ngăn blocking trên event loop, phải dùng driver non-blocking (như R2DBC) hoặc offload tạm thời qua scheduler phù hợp. “Lazy” và “non-blocking” không phải một khái niệm.

## 6. Operators quan trọng theo số lượng giá trị

### 6.1. map: 1 → 1 với mỗi item

```java
Flux<Integer> doubled = Flux.just(1, 2, 3)
        .map(n -> n * 2);
// onNext 2, 4, 6; onComplete
```

Với Mono:

```java
Mono<String> upper =
        Mono.just("spring").map(String::toUpperCase);
// SPRING
```

Nếu nguồn là `Mono.empty()`, lambda của `map` **không chạy**. `map` xử lý item; nó không chạy khi chỉ có onComplete.

### 6.2. filter: item có thể biến mất

```java
Mono<Integer> removed = Mono.just(3)
        .filter(n -> n % 2 == 0);
// Kết quả: Mono.empty() vì 3 không qua predicate.
```

`Flux.just(1,2,3).filter(n -> n > 2)` chỉ còn 3. Một kết quả rỗng sau `filter` **không phải lỗi**.

### 6.3. flatMap: mỗi item mở ra một Publisher

```java
Mono<String> name =
        Mono.just(42L)
            .flatMap(id -> reactiveRepository.findNameById(id));
```

Khi service trả `Mono<String>`, dùng `flatMap` để tránh `Mono<Mono<String>>`. Với Flux, `flatMap` có thể **trộn kết quả, thay đổi thứ tự hoàn thành** của các inner publishers; dùng `concatMap` nếu cần bảo toàn thứ tự và tuần tự hóa inner subscriptions.

Ví dụ:

```java
Flux<String> processed = Flux.just("A", "B")
        .flatMap(code -> webClient.get()
                .uri("/lookup/{code}", code)
                .retrieve()
                .bodyToMono(String.class));
```

Đây là **snippet minh họa cần WebClient được cấu hình**, không phải class standalone. Không dựa vào thứ tự output A rồi B với `flatMap` khi hai HTTP calls có latency khác nhau.

### 6.4. switchIfEmpty và defaultIfEmpty

```java
Mono<String> fallbackValue =
        Mono.<String>empty()
            .defaultIfEmpty("unknown");

Mono<String> fallbackPublisher =
        Mono.<String>empty()
            .switchIfEmpty(Mono.just("from-backup"));
```

Cả hai có thể phát một item fallback rồi complete. Khác biệt:

- `defaultIfEmpty(value)` nhận **một value non-null**, thích hợp với hằng/đối tượng có sẵn.
- `switchIfEmpty(otherMono)` chuyển sang **publisher khác** nếu upstream complete empty; publisher fallback có thể lazy, gọi DB khác, trả empty hoặc error.
- `onErrorResume` xử lý **error**, không xử lý empty.
- `switchIfEmpty` xử lý **empty**, không tự bắt exception của upstream.

Nếu fallback cần đọc tài nguyên tốn kém, dùng `Mono.defer`:

```java
Mono<Item> source = repository.findById(id);

Mono<Item> selected = source.switchIfEmpty(
        Mono.defer(() -> backupRepository.findById(id)));
```

*Các repository là dependency minh họa; code cần được đặt trong method và có kiểu Item thực tế. Chỉ gọi backup khi source rỗng và fallback được subscribe.*

### 6.5. collectList: Flux<T> → Mono<List<T>>

```java
Mono<List<Integer>> numbers =
        Flux.just(1, 2, 3).collectList();
```

Khi subscription kết thúc thành công, Mono phát **một danh sách** chứa 3 phần tử, rồi complete.

Đặc biệt:

```java
Mono<List<Integer>> emptyList =
        Flux.<Integer>empty().collectList();
```

Kết quả **không phải Mono.empty()**. Nó phát **một giá trị List rỗng** (`[]`) rồi complete.

Đây là sự khác biệt cardinality rất quan trọng:

```text
Flux.empty():
  onComplete                  (0 items)

Flux.empty().collectList():
  onNext([]) → onComplete      (1 item: một List rỗng)
```

Khi dùng `collectList` trên Flux vô hạn hoặc chưa complete, nó phải tích lũy tới khi complete: **có nguy cơ giữ toàn bộ dữ liệu trong heap mãi mãi**. Không dùng `collectList()` cho stream không giới hạn nếu chưa có `take`, `timeout` hoặc cửa sổ hữu hạn rõ ràng.

### 6.6. next, single, singleOrEmpty

Đây là các chuyển đổi từ Flux nhiều giá trị sang Mono và có semantics khác nhau.

| Operator | Flux rỗng | Flux có 1 item | Flux có từ 2 item |
| --- | --- | --- | --- |
| `next()` | Mono.empty | Item đầu rồi complete | Chỉ item đầu, cancel/không cần phần còn lại |
| `single()` | Error (không đúng 1 item) | Mono có item | Error (quá 1 item) |
| `singleOrEmpty()` | Mono.empty | Mono có item | Error (quá 1 item) |
| `collectList()` | Mono phát `[]` | Mono phát `[x]` | Mono phát `[x,y,...]` |
| `count()` | Mono phát 0L | Mono phát 1L | Mono phát số phần tử |

**Lỗi thường gặp:** dùng `next()` để xác nhận chỉ có **một** kết quả DB. `next()` chỉ lấy item đầu, không kiểm tra có item thứ hai hay không. Nếu nghiệp vụ yêu cầu duy nhất chính xác, dùng `single()` hoặc repository query có unique constraint và phương thức reactive phù hợp.

### 6.7. then và thenReturn: chỉ quan tâm completion

```java
Mono<Void> saveCompleted =
        repository.save(entity).then();
```

`then()` bỏ qua giá trị trước đó và tạo `Mono<Void>` biểu diễn complete/error.

```java
Mono<String> greetingAfterSave =
        repository.save(entity)
                  .thenReturn("saved");
```

Khi source complete thành công, `thenReturn` phát giá trị cố định; khi source lỗi, lỗi propagate. Không có gì “đã lưu” chỉ vì đã tạo Publisher — vẫn cần subscribe (trong WebFlux, framework thực hiện subscribe cho return value của handler).

### 6.8. zip: cần giá trị từ mỗi nguồn

```java
Mono<Tuple2<String, Integer>> combined =
        Mono.zip(Mono.just("A"), Mono.just(10));
```

Kết quả là **một tuple**, sau đó complete.

Tuy nhiên:

```java
Mono<Tuple2<String, Integer>> noTuple =
        Mono.zip(Mono.just("A"), Mono.<Integer>empty());
```

Result hoàn tất **rỗng**: nếu một bên không phát item thì không đủ giá trị để ghép. Với zipped chains phức tạp, có thể xảy ra short-circuit và không phải tất cả nguồn đều được subscribe; không dùng zip như “cơ chế chắc chắn chạy side effects của mọi nguồn”. Chọn `defaultIfEmpty` hoặc redesign pipeline nếu empty là trạng thái chấp nhận được.

## 7. Empty không đồng nghĩa HTTP 404 trong WebFlux

Một method của `@RestController`:

```java
@GetMapping("/api/items/{id}")
Mono<Item> get(@PathVariable long id) {
    return repository.findById(id);
}
```

Nếu `repository.findById(id)` trả `Mono.empty()`, framework không có item để serialize. **Không mặc nhiên được bảo đảm 404** chỉ vì Publisher rỗng. Nếu HTTP API contract yêu cầu “không tìm thấy → 404”, trả `Mono<ResponseEntity<Item>>` và xử lý rõ:

```java
@GetMapping("/api/items/{id}")
Mono<ResponseEntity<Item>> get(@PathVariable long id) {
    return repository.findById(id)
            .map(item -> ResponseEntity.ok(item))
            .defaultIfEmpty(ResponseEntity.notFound().build());
}
```

*Đoạn minh họa có repository/Item được inject; code hoàn chỉnh ở mục 12.*

Phân biệt các kết quả:

| Reactive value | Ý nghĩa ở tầng dữ liệu | Contract HTTP cần quyết định |
| --- | --- | --- |
| `Mono.empty()` | Không có item | Có thể là body rỗng, 404, 204... tùy endpoint |
| `Mono.just(item)` | Có một item | Thường 200 + JSON item |
| `Flux.empty()` | Tập hợp rỗng | Thường 200 + `[]` với JSON array |
| `Mono.just(List.of())` | Có **một danh sách rỗng** | Thường 200 + `[]` |
| `Mono.error(ex)` | Truy xuất thất bại | Error handling quyết định 4xx/5xx |
| `Mono<Void>` complete | Tác vụ không có payload | Có thể 204 khi API định nghĩa no-content |

**Không dùng empty để che giấu lỗi database.** “Không tìm thấy bản ghi” có thể là empty; “không kết nối được DB” là error và cần xử lý đúng. Nếu biến mọi error thành empty, client sẽ tưởng dữ liệu không tồn tại dù sự cố hạ tầng đang xảy ra.

### 7.1. Mono<ResponseEntity<T>> khác ResponseEntity<Mono<T>>

WebFlux hỗ trợ các kiểu:

```java
Mono<ResponseEntity<Item>>
ResponseEntity<Mono<Item>>
ResponseEntity<Flux<Item>>
```

Điểm khác:

- `Mono<ResponseEntity<Item>>`: **status, headers và body** có thể được quyết định **sau** khi một Mono resolve. Hợp với trường hợp cần `404` nếu empty.
- `ResponseEntity<Mono<Item>>`: status/headers được chọn ngay, body sẽ đến async; không thuận tiện nếu status phải đổi theo việc body có item hay không.
- `ResponseEntity<Flux<Item>>`: status/headers đã chọn, body nhiều items đến theo thời gian. Khi response đã commit rồi gặp error, không thể tùy ý đổi status.

Chọn type theo **thời điểm biết status**, không chỉ do coder thích Mono bọc ở ngoài hay bên trong.

## 8. Mono và Flux trong annotated WebFlux controllers

Các ví dụ thường gặp:

### 8.1. Mono<Item> cho detail

```java
@GetMapping("/api/items/{id}")
Mono<ResponseEntity<Item>> item(@PathVariable long id) {
    return service.find(id)
            .map(ResponseEntity::ok)
            .defaultIfEmpty(ResponseEntity.notFound().build());
}
```

### 8.2. Flux<Item> cho danh sách

```java
@GetMapping("/api/items")
Flux<Item> items() {
    return service.all();
}
```

Với `application/json`, một finite Flux nhiều giá trị thường được serialize như JSON array; client có thể nhận sau khi encoding/buffering tùy writer/streaming media type. Không khẳng định “Flux là streaming từng item ngay lập tức” trong mọi content type.

### 8.3. Flux<ServerSentEvent<Item>> cho streaming

```java
@GetMapping(
        value = "/api/items/events",
        produces = MediaType.TEXT_EVENT_STREAM_VALUE)
Flux<ServerSentEvent<Item>> events() {
    return service.all()
            .map(item -> ServerSentEvent.<Item>builder()
                    .event("item")
                    .data(item)
                    .build());
}
```

Với SSE (`text/event-stream`), mỗi item có thể được gửi/flush như một event; tránh `collectList` nếu muốn giữ semantics streaming và backpressure. Client disconnect có thể phát cancellation; dùng `doFinally` để cleanup resources chứ không đợi `onComplete` mãi.

### 8.4. Mono<Void> cho operation không payload

```java
@DeleteMapping("/api/items/{id}")
Mono<ResponseEntity<Void>> delete(@PathVariable long id) {
    return service.delete(id)
            .thenReturn(ResponseEntity.noContent().build());
}
```

*Snippet minh họa, cần service.delete(id) có contract rõ (không tồn tại ID thì 204 hay 404?)*. Nếu method delete là `Mono<Void>`, `thenReturn` phát ResponseEntity sau khi complete. Nhưng nếu muốn status 404 cho ID không tồn tại, phải dùng business decision riêng; `Mono<Void>` không tự mang thông tin đó.

### 8.5. Body publisher từ request

Với WebFlux:

```java
@PostMapping("/api/items")
Mono<ResponseEntity<Item>> create(
        @RequestBody Mono<CreateItem> requestBody) {

    return requestBody
            .flatMap(service::create)
            .map(saved -> ResponseEntity
                    .created(URI.create("/api/items/" + saved.id()))
                    .body(saved));
}
```

Đây là snippet minh họa, cần classes/service/URI imports. Nếu request body empty, `flatMap` không chạy và Mono ngoài cũng empty trừ khi thêm `switchIfEmpty` để quy định 400. Với input validation phức tạp, dùng validation support và trả lỗi có schema ổn định; không mong `flatMap` tự xử lý null/empty.

## 9. Assembly, subscription, cold và hot

### 9.1. Phân biệt assembly time với execution time

```java
AtomicInteger counter = new AtomicInteger();

Mono<Integer> lazy = Mono.fromCallable(counter::incrementAndGet);

System.out.println(counter.get()); // 0
lazy.subscribe();
System.out.println(counter.get()); // 1
lazy.subscribe();
System.out.println(counter.get()); // 2
```

Với synchronous `fromCallable`, hai subscriptions dẫn tới hai lần gọi Callable. Trong WebFlux, **không tự gọi `subscribe()` bên trong controller cho Publisher sẽ trả về**, nếu muốn kết quả đó trở thành HTTP response. Trả Publisher và để WebFlux subscribe; tự subscribe có thể tạo thêm execution song song, double DB writes, mất error handling và cancellation.

### 9.2. Cold publisher

Phần lớn factories `Mono.just`, `Mono.defer`, `Flux.fromIterable` biểu diễn nguồn có thể phát lại cho từng subscriber; mỗi subscription có own lifecycle. `Mono.just(value)` đã capture value lúc assembly, nên không chạy lại expression đã tính để tạo value. Ngược lại `Mono.defer` tạo source mới khi subscribe.

`Flux.range(1,3)` là cold:
 
```text
Subscriber A: 1 → 2 → 3 → complete
Subscriber B: 1 → 2 → 3 → complete
```

### 9.3. Hot publisher

Hot source có thể phát khi đang có subscribers, không nhất thiết replay quá khứ cho người đến sau. Các ví dụ gồm message/event bus được bridge vào Reactor qua `Sinks.Many<T>`. Khi dùng `Sinks.many().multicast()`, cần hiểu behavior của nhiều subscribers, buffer và overflow; backpressure của external producer có thể không tự nhiên khớp tốc độ consumer.

Một đoạn minh họa, không phải service hoàn chỉnh:

```java
Sinks.Many<String> sink = Sinks.many()
        .multicast()
        .onBackpressureBuffer();

Flux<String> events = sink.asFlux();
// Publisher có thể chia sẻ emissions cho subscribers.
// Cần xử lý EmitResult, buffer policy và cancellation.
```

Dùng `tryEmitNext(value)` và kiểm tra `Sinks.EmitResult` thay vì giả định mọi emit sẽ thành công. Hot streams có nguy cơ bỏ lỡ sự kiện, tràn buffer hoặc khiến client chậm kéo ảnh hưởng các subscribers. Thiết kế replay/durability tách biệt với việc chọn Flux.

### 9.4. cache, share, replay và sự thật về số lần gọi DB

Các operators có thể đổi cách chia sẻ:

- `Mono.cache()` cache terminal result (giá trị, empty hoặc error theo API semantics) cho subscriptions sau, có TTL overloads.
- `Flux.share()` tạo sharing behavior phù hợp hot subscription cho nhiều subscribers.
- `Flux.replay(n)`/`ConnectableFlux` hỗ trợ replay theo số phần tử (và biến thể).
- Các lựa chọn này có memory/TTL/error semantics cần kiểm soát kỹ.

**Đừng bật cache() vô hạn cho response cá nhân hoặc dữ liệu biến động** nếu chưa xét invalidation và privacy; reactive cache không thay authentication, transaction hoặc distributed cache design.

## 10. Backpressure: Flux 0..N phải tôn trọng tốc độ tiêu thụ

Reactive Streams có cơ chế **demand**. Subscriber nhận `Subscription` rồi gọi `request(n)` để yêu cầu số item tối đa tiếp theo. Nếu producer tôn trọng demand, nó không flood consumer không giới hạn.

Ví dụ:

```java
Flux.range(1, 5)
    .subscribe(new BaseSubscriber<Integer>() {
        @Override
        protected void hookOnSubscribe(Subscription subscription) {
            request(2);
        }

        @Override
        protected void hookOnNext(Integer value) {
            System.out.println(value);
            request(1);
        }
    });
```

*Snippet cần imports `BaseSubscriber` và `org.reactivestreams.Subscription`. Mục đích là mô tả demand theo API; với cơ chế này eventual output là 1..5 rồi complete, nếu không bị cancel.*

### 10.1. subscribe() thường request vô hạn

Các overloads như `subscribe(value -> ...)` và `block()` phổ biến thường request **unbounded** (`Long.MAX_VALUE`). Không dùng việc “đã gọi subscribe” làm bằng chứng rằng client tiêu thụ có giới hạn.

Trong WebFlux, reactive HTTP integration sẽ quản lý subscription và flow control theo WebFlux/Netty và từng writer; ứng dụng vẫn phải kiểm soát upstream DB/WebClient và consumer làm việc đắt đỏ.

### 10.2. Backpressure không tự bảo vệ mọi producer

- Nguồn synchronous `Flux.range`, `Flux.fromIterable` thường tôn trọng request demand.
- Nguồn push kiểu callback/hot events có thể phát nhanh hơn, cần buffering/dropping/latest/error strategy hoặc upstream flow control.
- `onBackpressureBuffer()` có thể tốn heap nếu producer nhanh hơn consumer trong thời gian dài.
- `limitRate(n)` điều chỉnh demand downstream-upstream theo batch, không biến database/remote broker thành zero-cost.
- `buffer(n)` biến nhiều items thành một `List<T>` mỗi batch; không biến mỗi batch thành complete stream.
- `take(n)` giới hạn số items và thường hủy upstream sau khi đủ số item.

### 10.3. Cancellation

Trong HTTP streaming, khi client ngắt kết nối, subscription có thể bị cancel. Thiết kế cleanup:

```java
Flux<Item> stream = repository.streamItems()
    .doFinally(type -> {
        // cleanup/metrics nhẹ khi complete, error hoặc cancel;
        // đừng block event loop.
    });
```

*Ví dụ minh họa cần repository thực. `doFinally` nhận `SignalType`; tránh lập luận rằng mọi network disconnection có thể được phát hiện ngay lập tức ở mọi proxy.*

Không đặt logic release resource chỉ trong `doOnComplete`: nếu pipeline lỗi hoặc cancel, callback đó không chạy. Dùng `usingWhen`/`doFinally` phù hợp lifecycle và bản chất resource.

## 11. Threading: reactive không đồng nghĩa chạy nhiều thread

`Mono.just(1).map(i -> i + 1)` thường chạy synchronous trên thread thực hiện subscribe. Việc dùng Mono/Flux **không tự làm task chạy nền**. Sự thay đổi thread chỉ xảy ra nếu source đã async, framework/scheduler/driver quyết định, hoặc bạn đặt `subscribeOn`/`publishOn`.

### 11.1. subscribeOn và publishOn

- `subscribeOn(scheduler)` tác động tới quá trình subscription/upstream execution (vị trí tương đối trong chain có semantics riêng).
- `publishOn(scheduler)` chuyển execution context cho các operators **sau nó**.
- Không đặt `publishOn` bừa bãi để “chữa blocking” nếu trước đó đã block event-loop.

Ví dụ:

```java
Mono<String> value =
    Mono.fromCallable(() -> legacyJdbc.queryOne())
        .subscribeOn(Schedulers.boundedElastic());
```

Đây là cầu nối tạm cho call synchronous **có giới hạn**. `boundedElastic` thiết kế cho blocking work tương đối phù hợp hơn event loop, nhưng không biến JDBC thành non-blocking I/O và có giới hạn/queue. Cần set timeout, connection pool và tránh quá tải. Nếu cả data stack đã reactive, ưu tiên driver non-blocking (ví dụ R2DBC) và không dùng wrapper blocking không cần thiết.

### 11.2. Vì sao .block() nguy hiểm trong WebFlux handler?

Trong request xử lý bởi Reactor Netty event-loop, `block()`/`blockFirst()`/`blockLast()` có thể gây chặn event-loop hoặc Reactor báo `IllegalStateException` trên các non-blocking threads. Một ít request chặn có thể khiến nhiều kết nối bị ảnh hưởng.

**Sai:**

```java
@GetMapping("/wrong")
String wrong() {
    return webClient.get().uri("/remote")
        .retrieve().bodyToMono(String.class).block();
}
```

**Đúng hơn:**

```java
@GetMapping("/right")
Mono<String> right() {
    return webClient.get().uri("/remote")
        .retrieve().bodyToMono(String.class);
}
```

Đây là hai snippets minh họa, cần `WebClient` instance được inject. Thực tế production còn cần deadlines, status handling, circuit breaker/backoff và connection pooling. Trong unit test hoặc command-line boundary, `block()` có thể chấp nhận khi mục đích chủ động chuyển về synchronous world.

### 11.3. Reactor Context thay vì ThreadLocal mù quáng

Reactive chain có thể chuyển thread; `ThreadLocal`/MDC không tự được bảo đảm có cùng giá trị ở mọi operator. Reactor cung cấp **Context** per subscriber:

```java
Mono<String> trace =
    Mono.deferContextual(ctx ->
            Mono.just(ctx.getOrDefault("traceId", "absent")))
        .contextWrite(Context.of("traceId", "req-123"));
```

Trong real app, để log MDC, tracing và security context xuyên thread phải dùng Spring/Reactor context propagation tích hợp phù hợp. Không truyền principal/credential bí mật bằng request header tự do rồi tin đó là identity.

## 12. Ứng dụng Spring Boot WebFlux + Java 17 có thể chạy

Tạo project Maven sử dụng **Spring Boot 3.3.13**, JDK 17+, dependency `spring-boot-starter-webflux`. **Không** thêm `spring-boot-starter-web` nếu muốn Boot mặc định chọn reactive web application; khi cả MVC và WebFlux starters cùng có mặt, Boot thường ưu tiên MVC auto-configuration trừ khi cấu hình khác.

Ứng dụng minh họa dữ liệu cố định và reactive repository tối giản trong memory:

- `GET /api/items` trả `Flux<Item>` → JSON array có 2 items.
- `GET /api/items/1` trả `Mono<ResponseEntity<Item>>` → 200 + item.
- `GET /api/items/999` → empty source được chuyển thành 404.
- `GET /api/items?contains=boot` → Flux.filter, có thể 0..N.
- `GET /api/items/first` → `Flux.next()`, chuyển sang Mono.
- `GET /api/items/summary` → `collectList()`, tạo một Summary object.
- `GET /api/items/events` → finite SSE Flux với hai event.
- `GET /api/items/none` → `Mono<Void>`/204, minh họa completion không body.

### 12.1. Cấu trúc

```text
mono-flux-cardinality/
├── pom.xml
└── src/
    ├── main/java/example/
    │   ├── ReactiveCardinalityApplication.java
    │   ├── Item.java
    │   ├── CatalogService.java
    │   └── ItemController.java
    └── test/java/example/
        ├── ReactorCardinalityTest.java
        └── ItemControllerTest.java
```

### 12.2. pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/xsd/maven-4.0.0.xsd https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>mono-flux-cardinality</artifactId>
    <version>1.0.0</version>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
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
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
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
```

`spring-boot-starter-webflux` cung cấp Spring WebFlux, Reactor Core và Reactor Netty runtime mặc định; `reactor-test` cung cấp `StepVerifier` cho tests. Không cần chỉ định Reactor version bằng tay vì Spring Boot dependency management chọn bộ versions tương thích.

### 12.3. ReactiveCardinalityApplication.java

```java
package example;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ReactiveCardinalityApplication {
    public static void main(String[] args) {
        SpringApplication.run(ReactiveCardinalityApplication.class, args);
    }
}
```

### 12.4. Item.java

```java
package example;

public record Item(long id, String name) {}
```

Java record có constructor và accessors `id()`, `name()`; Jackson được Boot cấu hình để encode JSON object.

### 12.5. CatalogService.java

```java
package example;

import java.util.List;

import org.springframework.stereotype.Service;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Service
public class CatalogService {
    private final List<Item> items = List.of(
        new Item(1L, "Spring WebFlux"),
        new Item(2L, "Spring Boot")
    );

    public Flux<Item> all() {
        // Cold source: mỗi subscriber duyệt cùng snapshot.
        return Flux.defer(() -> Flux.fromIterable(items));
    }

    public Mono<Item> find(long id) {
        return Mono.defer(() ->
            Mono.justOrEmpty(
                items.stream()
                    .filter(item -> item.id() == id)
                    .findFirst()
            )
        );
    }
}
```

Đây là data store cố định trong memory, **không phải reactive DB driver**. Vì dữ liệu List quá nhỏ, synchronous lookup là đủ cho mục đích demo; trong hệ thống thật, không dùng cách này để bọc một JPA query blocking lớn trên event-loop. Với R2DBC/reactive repository, các methods trả Mono/Flux mà I/O không cần giữ thread trong lúc chờ như JDBC.

Hai methods dùng `defer` để tạo Publisher/lookup vào lúc subscription. `all()` phát hai items rồi complete. `find(999)` hoàn tất rỗng mà không báo lỗi.

### 12.6. ItemController.java

```java
package example;

import java.time.Duration;
import java.util.List;
import java.util.Locale;

import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@RestController
public class ItemController {

    public record Summary(int count, List<String> names) {}

    private final CatalogService service;

    public ItemController(CatalogService service) {
        this.service = service;
    }

    @GetMapping("/api/items")
    public Flux<Item> list(
            @RequestParam(required = false) String contains) {

        Flux<Item> source = service.all();

        if (contains == null || contains.isBlank()) {
            return source;
        }

        String wanted = contains.trim().toLowerCase(Locale.ROOT);
        return source.filter(item ->
            item.name().toLowerCase(Locale.ROOT).contains(wanted));
    }

    @GetMapping("/api/items/first")
    public Mono<ResponseEntity<Item>> first() {
        return service.all()
            .next()
            .map(item -> ResponseEntity.ok(item))
            .defaultIfEmpty(ResponseEntity.notFound().build());
    }

    @GetMapping("/api/items/summary")
    public Mono<Summary> summary() {
        return service.all()
            .collectList()
            .map(items -> new Summary(
                items.size(),
                items.stream().map(Item::name).toList()
            ));
    }

    @GetMapping("/api/items/none")
    public Mono<ResponseEntity<Void>> none() {
        return Mono.<Void>empty()
            .thenReturn(ResponseEntity.noContent().build());
    }

    @GetMapping(
        value = "/api/items/events",
        produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public Flux<ServerSentEvent<Item>> events() {
        return service.all()
            .delayElements(Duration.ofMillis(20))
            .map(item -> ServerSentEvent.<Item>builder()
                .event("item")
                .data(item)
                .build());
    }

    @GetMapping("/api/items/{id}")
    public Mono<ResponseEntity<Item>> get(@PathVariable long id) {
        return service.find(id)
            .map(item -> ResponseEntity.ok(item))
            .defaultIfEmpty(ResponseEntity.notFound().build());
    }
}
```

**Vì sao chọn các return types như vậy?**

- `list`: có 0..N item, trả `Flux<Item>` thay vì `Mono<Item>`; với `application/json` trên kết quả finite, browser thường nhận JSON array.
- `first`: `Flux.next()` lấy một item đầu; nếu source không có item, controller chủ động trả 404 thay vì mặc nhiên 200 body rỗng.
- `summary`: `collectList` tạo một List rồi map sang **một Summary**; nếu items rỗng, summary vẫn có thể là `{count:0,names:[]}` chứ không phải 404.
- `none`: `Mono<Void>` hoàn tất thành công, `thenReturn` cung cấp ResponseEntity 204 để HTTP status được xác định tường minh.
- `events`: `Flux<ServerSentEvent<Item>>` cùng media type SSE biểu diễn nhiều events được gửi theo thời gian; demo chỉ có hai events rồi complete để tránh stream vô hạn trong test.
- `get`: `Mono.empty()` từ repository được biến thành `ResponseEntity.notFound()`. Đây là lựa chọn API contract, không phải behavior mặc định của Mono.
- Annotated route `/api/items/first` và `/api/items/{id}` cùng tồn tại: Spring path matching chọn route literal cụ thể hơn; thứ tự khai báo methods trong class không phải yếu tố chính.

### 12.7. Lệnh chạy và response mẫu

Ở thư mục chứa `pom.xml`:

```bash
mvn test
mvn spring-boot:run
```

Gọi GET danh sách:

```bash
curl -i http://localhost:8080/api/items
```

HTTP 200, JSON body:

```json
[
  {"id":1,"name":"Spring WebFlux"},
  {"id":2,"name":"Spring Boot"}
]
```

Whitespace thực tế thường compact, nhưng JSON structure như trên.

GET một item:

```bash
curl -i http://localhost:8080/api/items/1
```

HTTP 200, body:

```json
{"id":1,"name":"Spring WebFlux"}
```

Không tồn tại:

```bash
curl -i http://localhost:8080/api/items/999
```

HTTP **404 Not Found**, do controller xử lý `Mono.empty()` thành `ResponseEntity.notFound()`. Response body lỗi chính xác có thể do Boot default error handler quyết định; đừng assert một JSON error text không có trong controller.

Lọc thành công:

```bash
curl -i "http://localhost:8080/api/items?contains=boot"
```

HTTP 200:

```json
[{"id":2,"name":"Spring Boot"}]
```

Lọc không có kết quả:

```bash
curl -i "http://localhost:8080/api/items?contains=unknown"
```

HTTP 200 với JSON array rỗng:

```json
[]
```

Tóm tắt:

```bash
curl -i http://localhost:8080/api/items/summary
```

HTTP 200:

```json
{"count":2,"names":["Spring WebFlux","Spring Boot"]}
```

Không có body:

```bash
curl -i http://localhost:8080/api/items/none
```

HTTP **204 No Content**, không có JSON body.

SSE:

```bash
curl -N -i -H "Accept: text/event-stream" \
  http://localhost:8080/api/items/events
```

Phần body minh họa (dạng encoding cụ thể, khoảng trắng và các headers có thể thay đổi):

```text
event:item
data:{"id":1,"name":"Spring WebFlux"}

event:item
data:{"id":2,"name":"Spring Boot"}

```

`curl -N` tắt output buffering phía curl để dễ xem từng event. Khi response stream dài, client cần xử lý reconnect, ID, cancellation, timeouts và backpressure; đừng cho rằng sự tồn tại của Flux bảo đảm delivery durable.

## 13. Unit tests Reactor: StepVerifier kiểm tra signals, không chỉ data

`reactor-test` cung cấp `StepVerifier` để kiểm tra những gì Publisher phát:

- `expectNext(...)`: dự kiến một/một số onNext values.
- `expectNextCount(n)`: dự kiến n phần tử mà không quan tâm giá trị.
- `verifyComplete()`: xác nhận completion thành công.
- `expectError(...)`/`expectErrorMatches(...)`: xác nhận terminal error.
- `thenCancel()`: hủy stream dài hạn.
- `withVirtualTime(...)`: kiểm tra publisher có delay mà không đợi thời gian thực quá dài, nếu publisher được tạo sau khi virtual scheduler được thiết lập.

### 13.1. ReactorCardinalityTest.java

```java
package example;

import java.util.List;
import java.util.NoSuchElementException;

import org.junit.jupiter.api.Test;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class ReactorCardinalityTest {

    @Test
    void monoJustEmitsOneItemThenCompletes() {
        StepVerifier.create(Mono.just("A"))
            .expectNext("A")
            .verifyComplete();
    }

    @Test
    void monoEmptyCompletesWithoutNext() {
        StepVerifier.create(Mono.<String>empty())
            .verifyComplete();
    }

    @Test
    void monoJustNullIsNotAllowed() {
        assertThrows(NullPointerException.class,
            () -> Mono.just((String) null));
    }

    @Test
    void monoJustOrEmptyNullIsEmpty() {
        StepVerifier.create(Mono.justOrEmpty((String) null))
            .verifyComplete();
    }

    @Test
    void monoErrorIsNotSuccessfulCompletion() {
        StepVerifier.create(
                Mono.<String>error(
                    new IllegalStateException("boom")))
            .expectErrorMatches(ex ->
                ex instanceof IllegalStateException &&
                "boom".equals(ex.getMessage()))
            .verify();
    }

    @Test
    void fluxCanEmitMoreThanOneItem() {
        StepVerifier.create(Flux.just(1, 2, 3))
            .expectNext(1, 2, 3)
            .verifyComplete();
    }

    @Test
    void fluxCanBeEmpty() {
        StepVerifier.create(Flux.<Integer>empty())
            .verifyComplete();
    }

    @Test
    void collectListTurnsEmptyFluxIntoOneEmptyList() {
        StepVerifier.create(
                Flux.<Integer>empty().collectList())
            .expectNext(List.of())
            .verifyComplete();
    }

    @Test
    void nextTakesOnlyFirst() {
        StepVerifier.create(Flux.just(9, 8, 7).next())
            .expectNext(9)
            .verifyComplete();
    }

    @Test
    void singleRequiresExactlyOneValue() {
        StepVerifier.create(Flux.just(9).single())
            .expectNext(9)
            .verifyComplete();

        StepVerifier.create(Flux.<Integer>empty().single())
            .expectError(NoSuchElementException.class)
            .verify();

        StepVerifier.create(Flux.just(1, 2).single())
            .expectError(IndexOutOfBoundsException.class)
            .verify();
    }

    @Test
    void singleOrEmptyAllowsZeroButNotTwoValues() {
        StepVerifier.create(Flux.<Integer>empty().singleOrEmpty())
            .verifyComplete();

        StepVerifier.create(Flux.just(1, 2).singleOrEmpty())
            .expectError(IndexOutOfBoundsException.class)
            .verify();
    }

    @Test
    void fallbackForEmptyIsNotFallbackForError() {
        StepVerifier.create(
                Mono.<String>empty().defaultIfEmpty("fallback"))
            .expectNext("fallback")
            .verifyComplete();

        StepVerifier.create(
                Mono.<String>error(new IllegalStateException())
                    .defaultIfEmpty("fallback"))
            .expectError(IllegalStateException.class)
            .verify();
    }

    @Test
    void collectListCountsAllFiniteItems() {
        StepVerifier.create(
                Flux.range(5, 3).collectList())
            .expectNext(List.of(5, 6, 7))
            .verifyComplete();
    }

    @Test
    void thenReturnWaitsForCompletion() {
        StepVerifier.create(
                Mono.just("ignored").thenReturn("done"))
            .expectNext("done")
            .verifyComplete();
    }

    @Test
    void monoZipWithEmptyCannotEmitTuple() {
        StepVerifier.create(Mono.zip(
                Mono.just("A"), Mono.<Integer>empty()))
            .verifyComplete();
    }
}
```

Các tests này có scope **signal/cardinality** và không cần HTTP server. `single()` với quá nhiều items được Reactor 3.6 báo lỗi `IndexOutOfBoundsException`; với source empty, `single()` báo `NoSuchElementException`. Kiểm thử không chỉ dùng `block()` rồi so giá trị, vì `block()` trên Mono rỗng có thể trả null và dễ làm người đọc lẫn lộn empty với null.

### 13.2. Test virtual time cho stream có thời gian

Ví dụ bổ sung:

```java
@Test
void timedFluxCanBeTestedWithoutRealDelay() {
    StepVerifier.withVirtualTime(() ->
            Flux.interval(Duration.ofHours(1)).take(2))
        .expectSubscription()
        .thenAwait(Duration.ofHours(2))
        .expectNext(0L, 1L)
        .verifyComplete();
}
```

Đặt method này vào class trên và thêm `import java.time.Duration;`. **Publisher phải được tạo trong Supplier của `withVirtualTime`**, nếu tạo trước, timer có thể đã gắn vào scheduler thực và test không điều khiển được. Virtual-time tests hữu ích cho `delayElement`, `interval`, `timeout` và retries; tránh `Thread.sleep` làm test chậm/flaky.

## 14. WebTestClient: kiểm tra Mono/Flux qua HTTP

Bài kiểm thử dưới đây khởi động reactive Spring Boot context qua `@SpringBootTest(webEnvironment = RANDOM_PORT)` và dùng `WebTestClient`; không ép phải dùng Servlet MockMvc. `@AutoConfigureWebTestClient` cấu hình client test Spring WebFlux.

### 14.1. ItemControllerTest.java

```java
package example;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class ItemControllerTest {

    @Autowired
    WebTestClient client;

    @Test
    void listFluxBecomesJsonArray() {
        client.get().uri("/api/items")
            .exchange()
            .expectStatus().isOk()
            .expectHeader()
                .contentTypeCompatibleWith(MediaType.APPLICATION_JSON)
            .expectBody()
                .jsonPath("$[0].name").isEqualTo("Spring WebFlux")
                .jsonPath("$[1].name").isEqualTo("Spring Boot");
    }

    @Test
    void existingItemMonoReturns200() {
        client.get().uri("/api/items/1")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
                .jsonPath("$.id").isEqualTo(1)
                .jsonPath("$.name").isEqualTo("Spring WebFlux");
    }

    @Test
    void emptyMonoIsExplicitlyMappedTo404() {
        client.get().uri("/api/items/999")
            .exchange()
            .expectStatus().isNotFound();
    }

    @Test
    void filterFluxCanReturnZeroItems() {
        client.get()
            .uri("/api/items?contains=missing")
            .exchange()
            .expectStatus().isOk()
            .expectBody().json("[]");
    }

    @Test
    void firstConvertsFluxToMono() {
        client.get().uri("/api/items/first")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
                .jsonPath("$.id").isEqualTo(1);
    }

    @Test
    void summaryCollectsFiniteFluxIntoSingleObject() {
        client.get().uri("/api/items/summary")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
                .jsonPath("$.count").isEqualTo(2)
                .jsonPath("$.names[0]")
                    .isEqualTo("Spring WebFlux");
    }

    @Test
    void completionWithoutBodyReturns204() {
        client.get().uri("/api/items/none")
            .exchange()
            .expectStatus().isNoContent()
            .expectBody().isEmpty();
    }

    @Test
    void sseEndpointProducesEventStream() {
        client.get().uri("/api/items/events")
            .accept(MediaType.TEXT_EVENT_STREAM)
            .exchange()
            .expectStatus().isOk()
            .expectHeader()
                .contentTypeCompatibleWith(MediaType.TEXT_EVENT_STREAM);
    }
}
```

**Tại sao test dùng RANDOM_PORT?** Nó kiểm tra WebFlux HTTP server stack (Reactor Netty mặc định), Spring Boot routing và encoding thật hơn test chỉ unit controller. Với kiểm thử streaming/cancellation có yêu cầu mạnh, cần consume body qua `returnResult(...)` và dùng StepVerifier, không chỉ assert headers. Test này không thay thế load test network backpressure hoặc reliability khi client disconnect.

### 14.2. Kiểm thử lỗi không phải không có item

Nếu service trả `Mono.error(new IllegalStateException("db unavailable"))`, đó là lỗi hạ tầng; không được tự chuyển thành 404. Với Spring WebFlux có thể cấu hình `@RestControllerAdvice`, `ErrorWebExceptionHandler` hoặc `onErrorResume` theo contract. Nhưng đừng áp `onErrorResume(ex -> Mono.empty())` cho mọi exception vì sẽ biến sự cố thành “không tìm thấy”, che mất alert và thông tin cần debug.

## 15. Lựa chọn Mono/Flux trong WebClient, repository và business API

### 15.1. WebClient trả một object

```java
Mono<Item> item = webClient.get()
        .uri("/api/items/{id}", 42L)
        .retrieve()
        .bodyToMono(Item.class);
```

Nếu server HTTP 404, `retrieve()` mặc định có thể sinh `WebClientResponseException.NotFound`, **không tự biến status 404 thành Mono.empty()**. Muốn phân biệt 404 với lỗi khác, viết status handler hoặc dùng `exchangeToMono(...)`:

```java
Mono<Item> selected = webClient.get()
    .uri("/api/items/{id}", 42L)
    .exchangeToMono(response -> {
        if (response.statusCode().value() == 404) {
            return Mono.empty();
        }
        if (response.statusCode().is2xxSuccessful()) {
            return response.bodyToMono(Item.class);
        }
        return response.createError();
    });
```

*Đoạn minh họa, cần WebClient/Item imports và xử lý các status nghiệp vụ khác nếu cần. Không dùng code mẫu để nuốt mọi lỗi 5xx thành empty.*

### 15.2. WebClient trả nhiều items

```java
Flux<Item> items = webClient.get()
        .uri("/api/items")
        .retrieve()
        .bodyToFlux(Item.class);
```

Nếu endpoint trả JSON array, WebClient có thể decode thành nhiều Item signals. Nhưng server phát JSON array hữu hạn và server phát SSE/infinite stream có lifecycle khác; consumer phải hiểu content type, buffering và cancellation.

### 15.3. ReactiveCrudRepository

Các repository reactive phổ biến đưa về cardinality như:

| Operation | Kiểu thường gặp |
| --- | --- |
| `findById(id)` | `Mono<T>`: 0..1 |
| `findAll()` | `Flux<T>`: 0..N |
| `save(entity)` | `Mono<T>`: saved object hoặc lỗi |
| `deleteById(id)` | `Mono<Void>`: completion/error |
| `count()` | `Mono<Long>` |
| `existsById(id)` | `Mono<Boolean>` |

Đây là contract kiểu phổ biến trong Spring Data reactive repositories. Một empty result của `findById` không nhất thiết tương ứng với HTTP 404 cho mọi use case; HTTP policy thuộc service/controller.

### 15.4. Business cardinality so với technical cardinality

Nếu entity phải duy nhất theo email, `Mono<User>` là API tốt, nhưng **không bảo đảm DB unique constraint**. Cần database uniqueness/transaction. Nếu endpoint findAll trả `Flux<User>` nhưng yêu cầu page size 20, đừng stream toàn bộ hàng triệu users không giới hạn; dùng pagination/limits và query database phù hợp.

## 16. Lỗi phổ biến: 20 bẫy cần tránh

| Nhầm lẫn | Hậu quả | Cách hiểu đúng |
| --- | --- | --- |
| “Mono luôn có đúng 1 item” | Không xử lý empty | Mono phát 0 hoặc 1 |
| “Flux luôn có nhiều items” | Không biết Flux.empty | Flux phát 0..N |
| “Mono.empty() là Mono.just(null)” | NPE hoặc logic sai | Null không phải onNext hợp lệ |
| “Mono.error là Mono.empty” | Che mất sự cố | Error terminal khác complete empty |
| “Mono<Void> chứa object Void” | map không chạy | Chỉ completion hoặc error |
| “Mono<List<T>> giống Flux<T>” | Sai cardinality và streaming | Một List là một item |
| “Flux.empty().collectList() vẫn empty Mono” | Sai response/test | Nó phát `[]` |
| “Flux.next kiểm tra đúng một item” | Dữ liệu trùng bị bỏ qua | next chỉ lấy item đầu |
| “Flux.single có thể bỏ qua item thừa” | Lỗi cardinality | single yêu cầu đúng một item |
| “Flux.singleOrEmpty chấp nhận mọi số items” | Error khi >1 | Nó chỉ cho 0 hoặc 1 |
| “switchIfEmpty bắt exception” | Lỗi không được xử lý | Dùng onErrorResume khi thật sự muốn fallback lỗi |
| “onErrorResume dùng cho not found” | Đổi mọi lỗi DB thành 404 | Empty và error phải tách |
| “zip với Mono.empty luôn chạy side effects bên kia” | Side effects bị short-circuit | Không dùng zip để kích hoạt tác vụ bắt buộc |
| “Mono.just(blockingCall()) là lazy” | Blocking chạy lúc assembly | defer/fromCallable và scheduler phù hợp |
| “Mono.fromCallable làm JDBC non-blocking” | Event loop vẫn bị block | Reactive driver hoặc boundedElastic bridge |
| “subscribe bên trong controller để nhanh hơn” | Double execution, mất cancellation | Return Publisher để WebFlux subscribe |
| “block() trong WebFlux handler là vô hại” | Event-loop starvation/lỗi | Compose reactive operators |
| “Flux là streaming tức browser thấy item ngay” | Mất kỳ vọng về media type | JSON array vs SSE/NDJSON khác nhau |
| “Flux hot luôn replay data cho người mới” | Mất events | Chọn replay/buffer policy rõ |
| “Backpressure tự tồn tại trong mọi callback source” | Overflow/OOM | Design demand/backpressure |
| “collectList trên Flux vô hạn cho kết quả” | Không complete, heap tăng | Giới hạn take/window hoặc stream |
| “Cancellation là onComplete” | Cleanup thiếu | doFinally/usingWhen đúng semantics |
| “Mỗi operator tạo thread mới” | Sai performance model | Scheduler chỉ thay khi được chỉ định |
| “HTTP 404 tự đến khi Mono rỗng” | Sai API contract | Explicit ResponseEntity.notFound |
| “WebClient retrieve 404 trả Mono.empty” | 404 thành error | onStatus/exchangeToMono theo policy |
| “Một ETag/security token là reactive context” | Sai trust boundary | Xác thực và context riêng |
| “Reactive nghĩa mọi thư viện đều non-blocking” | JDBC/file I/O vẫn block | Kiểm tra toàn call chain |
| “map xử lý completion empty” | Side effect không chạy | then/doOnSuccess/doFinally theo semantics |
| “Flux flatMap luôn giữ thứ tự” | Output không ổn định | concatMap/flatMapSequential nếu cần |
| “Producer cancel thì data đã được lưu chắc rollback” | Side effect mơ hồ | Transaction/idempotency rõ |

## 17. Checklist thiết kế Mono hay Flux

Trước khi định nghĩa return type cho method, trả lời:

1. Nghiệp vụ trả **không**, **một** hay **nhiều** object?
2. “Không có object” là thành công hợp lệ, HTTP 404, hay lỗi business?
3. “Không có body” nghĩa thao tác thành công không payload (`Mono<Void>`/204) hay entity không tồn tại?
4. Nếu nhiều objects, cần JSON array hữu hạn hay SSE/NDJSON streaming?
5. Source hữu hạn hay có thể phát vô hạn? Ai và khi nào cancel?
6. Cần giữ thứ tự items? `flatMap` có thể reorder không?
7. Lỗi xuất hiện **trước** hay **sau** khi HTTP response committed?
8. Driver repository/WebClient có thực sự non-blocking không?
9. Có upstream demand/backpressure khi producer nhanh hơn consumer không?
10. Có giữ toàn data bằng `collectList()` và cần giới hạn memory không?
11. Có accidental double subscription gây DB queries hoặc duplicate writes không?
12. Có retry mà operation không idempotent không?
13. Đã phân biệt `switchIfEmpty` với `onErrorResume` rõ chưa?
14. HTTP 404, 204, 400, 500 có được mapping tường minh đúng contract không?
15. Tests đã assert completion, error, empty, một giá trị và nhiều giá trị chưa?
16. Test async có dùng virtual time thay `Thread.sleep` khi cần không?
17. Có log/metrics cancellation, demand, latency và retries mà không leak dữ liệu không?
18. Context/security đi qua reactive chain đúng cách, không phụ thuộc ThreadLocal tùy tiện?
19. Khi trộn MVC và WebFlux starters, ứng dụng thực chạy stack nào?
20. Có cần pagination hoặc rate limit thay vì để client subscribe vào stream vô hạn?

## 18. Câu hỏi tự kiểm tra

**1.** `Mono<T>` có nhất thiết phát một giá trị không?  
**Đáp án:** Không; nó có 0 hoặc 1 item, kết thúc thành công hoặc lỗi, và có thể không kết thúc nếu source never.

**2.** `Flux<T>` có thể rỗng không?  
**Đáp án:** Có; `Flux.empty()` hoàn tất không phát item.

**3.** Vì sao `Mono.just(null)` không hợp lệ?  
**Đáp án:** Reactive Streams không cho phát null qua onNext; Reactor factory ném NullPointerException.

**4.** `Mono.justOrEmpty((String)null)` biểu diễn gì?  
**Đáp án:** Mono empty, hoàn tất không có onNext.

**5.** `Mono<Void>` có onNext(Void) không?  
**Đáp án:** Không; chủ yếu biểu diễn completion/error không payload.

**6.** `Flux.empty().collectList()` phát bao nhiêu item?  
**Đáp án:** Một item: empty List.

**7.** `Flux.just(1,2).next()` phát gì?  
**Đáp án:** Phát 1 rồi hoàn tất; không kiểm tra item 2.

**8.** `Flux.just(1,2).single()` thì sao?  
**Đáp án:** Error vì có hơn một item.

**9.** `Flux.empty().single()` thì sao?  
**Đáp án:** Error vì yêu cầu đúng một item.

**10.** `Flux.empty().singleOrEmpty()` thì sao?  
**Đáp án:** Complete empty, hợp lệ.

**11.** `switchIfEmpty` xử lý trường hợp error không?  
**Đáp án:** Không, cần error handling riêng.

**12.** `Mono.error(ex).defaultIfEmpty(v)` phát v không?  
**Đáp án:** Không, error propagate.

**13.** Mono.zip với một nguồn Mono.empty tạo kết quả không?  
**Đáp án:** Không, tuple không có đủ thành phần.

**14.** Tại sao `Mono.just(expensive())` không trì hoãn expensive?  
**Đáp án:** Java đánh giá argument trước khi gọi just.

**15.** Gọi `subscribe()` ngay trong WebFlux controller thường có nên không?  
**Đáp án:** Không; return Publisher cho Framework quản lý subscription/lifecycle.

**16.** Khi client disconnect từ SSE, điều gì có thể xảy ra?  
**Đáp án:** Subscription bị cancel, cần cleanup; không nhất thiết onComplete.

**17.** `flatMap` trên Flux có bảo toàn thứ tự của async inner publishers không?  
**Đáp án:** Không bảo đảm; dùng concatMap hoặc lựa chọn giữ thứ tự.

**18.** `publishOn` và `subscribeOn` cùng tác động đến execution context không?  
**Đáp án:** Có, nhưng ở phạm vi downstream và subscription/upstream khác nhau.

**19.** Dùng `.block()` bên trong WebFlux request event-loop có nguy hiểm không?  
**Đáp án:** Có thể block hoặc bị Reactor từ chối, giảm khả năng xử lý concurrent connections.

**20.** HTTP GET tìm ID không có, service trả Mono.empty, có tự 404 không?  
**Đáp án:** Không bảo đảm; dùng explicit ResponseEntity.notFound nếu contract cần 404.

**21.** Flux trả JSON array có luôn flush mỗi item không?  
**Đáp án:** Không; phụ thuộc writer/media type. SSE/NDJSON dùng streaming semantics rõ hơn.

**22.** WebClient.retrieve() với 404 có mặc định trả Mono.empty không?  
**Đáp án:** Không; thường sinh WebClientResponseException tương ứng.

**23.** Mono.zip dùng để chắc chắn chạy side effects của mọi nguồn có tốt không?  
**Đáp án:** Không; empty có thể short-circuit subscriptions.

**24.** `Mono.cache()` có phù hợp lưu mãi thông tin riêng tư mọi user không?  
**Đáp án:** Không nếu chưa xét key/TTL/invalidation/security.

**25.** Backpressure giải quyết vấn đề gì?  
**Đáp án:** Cho downstream thông báo demand để upstream phù hợp tốc độ tiêu thụ, khi nguồn có thể tôn trọng demand.

## 19. Nguồn đọc chính thức

- [Project Reactor — Reactor 3 Reference Guide](https://projectreactor.io/docs/core/3.6.12/reference/index.html): Mono 0..1, Flux 0..N, backpressure, cold/hot, assembly/subscription, operators.
- [Reactor Core 3.6 — Mono Javadoc](https://projectreactor.io/docs/core/3.6.15/api/reactor/core/publisher/Mono.html): `justOrEmpty`, `defer`, `switchIfEmpty`, `defaultIfEmpty`, `thenReturn`, subscribe.
- [Project Reactor — Flux Javadoc](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Flux.html): `fromIterable`, `next`, `single`, `singleOrEmpty`, `collectList`.
- [Project Reactor — Testing with StepVerifier](https://projectreactor.io/docs/test/release/api/reactor/test/StepVerifier.html): kiểm thử onNext/onComplete/onError/virtual time.
- [Spring Framework 6.2 — WebFlux Annotated Controllers](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller.html): Mono/Flux return types trong REST controllers.
- [Spring Framework 6.2 — WebFlux Controller Return Values](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller/ann-methods/return-types.html): HTTP encoding theo media type, Flux stream vs response buffering.
- [Spring Framework 6.2 — ResponseEntity](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller/ann-methods/responseentity.html): `Mono<ResponseEntity<T>>` khác `ResponseEntity<Mono<T>>`/`ResponseEntity<Flux<T>>`.
- [Spring Framework — WebClient](https://docs.spring.io/spring-framework/reference/6.2/web/webflux-webclient.html): `bodyToMono`/`bodyToFlux`, error handling.
- [Spring Framework — WebTestClient](https://docs.spring.io/spring-framework/reference/6.2/testing/webtestclient.html): HTTP tests của WebFlux.
- [Reactive Streams specification](https://www.reactive-streams.org/): Publisher, Subscriber, Subscription, demand, terminal signals.

**Ghi nhớ cốt lõi:** `Mono<T>` là **0 hoặc 1 item**; `Flux<T>` là **0 đến nhiều items**. Cả hai còn phát **completion/error/cancellation semantics** và chịu subscription/backpressure. **Empty không phải null, error không phải empty, Flux.empty().collectList() không phải Mono.empty().** Đọc đúng những khác biệt này giúp thiết kế API WebFlux có HTTP status, memory footprint, streaming và error handling đáng tin cậy.
