# Phân biệt lắp ghép chuỗi với thực thi khi đăng ký (Mono và Flux)

## 1. Mục tiêu và trực giác cốt lõi

Khi đọc code **Project Reactor** trong Spring WebFlux, phải tách bạch hai thời điểm:

1. **Assembly (lắp ghép pipeline):** chương trình gọi các phương thức như `Mono.just(...)`, `map(...)`, `flatMap(...)`, `filter(...)`, `doOnNext(...)` để tạo đối tượng mô tả một chuỗi xử lý. Việc **gọi phương thức Java để xây dựng chuỗi** diễn ra ngay lúc dòng code đó chạy.
2. **Subscription (đăng ký/đặt mua):** một subscriber gắn vào publisher bằng `subscribe(...)`, hoặc framework làm điều tương đương. Việc đăng ký khởi tạo tương tác theo giao thức Reactive Streams; publisher có thể bắt đầu phát tín hiệu và thực hiện những tác vụ đã trì hoãn khi nhận yêu cầu dữ liệu (demand).

Đối với **cold publisher** thường gặp như `Mono.fromSupplier(...)` hoặc `Flux.range(...)`, công việc tạo tín hiệu thường gắn với **mỗi subscription**. Vì thế, *khai báo một chuỗi xử lý* không đồng nghĩa với *đã chạy xong chuỗi đó*.

Nhưng **“mọi thứ trong `Mono`/`Flux` đều đợi tới `subscribe()`” là một kết luận sai**. Biểu thức Java chạy khi lắp ghép vẫn có thể tạo giá trị, gọi API blocking, in log hoặc ném exception ngay lập tức. Hot publisher có thể đã phát dữ liệu trước khi subscriber mới đến; scheduler cũng có thể khiến xử lý xảy ra bất đồng bộ sau khi `subscribe()` trả về.

Hãy giữ ba câu hỏi khi đọc code:

- **Dòng này chỉ đang tạo publisher, hay đang gọi một hàm Java ngay lúc lắp ghép?**
- **Nguồn dữ liệu được tạo mới cho từng subscription, hay đang chia sẻ/caching một nguồn?**
- **Khi subscription xảy ra, tín hiệu chạy đồng bộ hay được lên lịch trên một luồng khác?**

## 2. Ba lớp thời điểm: assembly, subscribe và signal

| Giai đoạn | Điều gì có thể xảy ra? | Ví dụ |
| --- | --- | --- |
| **Assembly time** | Chạy các biểu thức Java để dựng pipeline, tạo wrapper operator, kiểm tra tham số; các đối số không nằm trong lambda trì hoãn được tính ngay | `Mono.just(load())` gọi `load()` ngay; `source.map(fn)` tạo một publisher mới |
| **Subscription time** | Subscriber đăng ký, `onSubscribe` xuất hiện, nguồn lạnh có thể khởi động; nhiều hàm tạo nguồn chạy khi nguồn nhận demand | `source.subscribe(...)`; callback `doOnSubscribe` |
| **Signal-processing time** | Nguồn gửi `onNext`, `onError`, `onComplete`; toán tử xử lý tín hiệu và chuyển tiếp | Lambda trong `map`/`flatMap`, callback `doOnNext`, `onErrorResume` khi có lỗi |

Reactive Streams còn có thao tác **request(n)** sau `onSubscribe`: subscriber yêu cầu số lượng phần tử mà mình sẵn sàng nhận. Vì vậy nói “thực thi khi đăng ký” là cách học khái quát; nói chính xác hơn là **subscription thiết lập pipeline, rồi demand và các tín hiệu nguồn điều khiển phần việc cụ thể**. Một số tác vụ diễn ra lúc `subscribe()`; có tác vụ chờ `request(n)` hoặc chờ tín hiệu bất đồng bộ.

Luồng khái niệm với cold publisher:

```text
Tạo Mono/Flux -> gắn map/filter/flatMap -> giữ publisher (assembly)
                                               |
                                               | subscribe()
                                               v
                                 onSubscribe -> request(n)
                                               |
                                               v
                                 nguồn phát onNext/onError/onComplete
                                               |
                                               v
                                 các operator xử lý và chuyển tín hiệu
                                               |
                                               v
                                      subscriber nhận kết quả
```

Trong Reactor, `Mono<T>` đại diện tối đa một phần tử, còn `Flux<T>` là 0..N phần tử. Cả hai mô tả pipeline và đều có quy tắc về subscription; không phải vì `Mono` chỉ có một giá trị mà nó tự động chạy ngay tại thời điểm được tạo.

## 3. Ví dụ Java 17+ chạy được: một pipeline, hai lần đăng ký

Đây là một chương trình Java độc lập **ở mức class**, cần dependency `reactor-core` trong classpath. Có thể đặt tệp `src/main/java/demo/AssemblyVsSubscriptionDemo.java` trong dự án Spring Boot/WebFlux (đã có Project Reactor) rồi chạy hàm `main` từ IDE. Với dự án Spring Boot dùng Gradle và quản lý dependency qua Spring Boot BOM, `spring-boot-starter-webflux` đã đưa Reactor vào classpath; không cần thêm một Reactor version riêng.

```java
package demo;

import java.util.concurrent.atomic.AtomicInteger;
import reactor.core.publisher.Mono;

public class AssemblyVsSubscriptionDemo {
    public static void main(String[] args) {
        AtomicInteger sourceRuns = new AtomicInteger();

        System.out.println("A: before assembly");

        Mono<Integer> pipeline = Mono.fromSupplier(() -> {
                    int run = sourceRuns.incrementAndGet();
                    System.out.println("source run #" + run);
                    return run;
                })
                .map(value -> {
                    System.out.println("map " + value);
                    return value * 10;
                })
                .doOnSubscribe(subscription ->
                        System.out.println("doOnSubscribe"));

        System.out.println("B: after assembly, runs=" + sourceRuns.get());

        pipeline.subscribe(value ->
                System.out.println("first subscriber: " + value));

        System.out.println("C: after first subscribe, runs=" + sourceRuns.get());

        pipeline.subscribe(value ->
                System.out.println("second subscriber: " + value));

        System.out.println("D: after second subscribe, runs=" + sourceRuns.get());
    }
}
```

**Stdout chính xác cho ví dụ này** (nguồn đồng bộ, không có scheduler hoặc I/O ngoài):

```text
A: before assembly
B: after assembly, runs=0
doOnSubscribe
source run #1
map 1
first subscriber: 10
C: after first subscribe, runs=1
doOnSubscribe
source run #2
map 2
second subscriber: 20
D: after second subscribe, runs=2
```

Giải thích từng mốc:

1. Dòng `Mono.fromSupplier(...)` và các lời gọi `.map(...)`, `.doOnSubscribe(...)` **tạo mô tả xử lý**. Chúng chưa gọi lambda bên trong `fromSupplier` hoặc `map`. Do đó sau assembly, `sourceRuns` vẫn là 0.
2. Lần `subscribe` thứ nhất thiết lập subscription; `doOnSubscribe` nhận thông báo trước khi nguồn đồng bộ phát giá trị; supplier chạy, trả 1, rồi `map` biến 1 thành 10.
3. Lần `subscribe` thứ hai **đăng ký lại cùng publisher lạnh**. Supplier chạy thêm lần nữa, trả 2, `map` thành 20. Hai subscriber không cùng chia sẻ “kết quả đã chạy lần đầu”.
4. Trong **đúng ví dụ đồng bộ này**, `subscribe(...)` hoàn tất xử lý trước khi dòng in tiếp theo chạy. Không suy rộng điều đó sang `WebClient`, `Mono.delay`, nguồn qua scheduler hoặc bất kỳ nguồn bất đồng bộ nào.

Điểm khó dễ nhầm: dù lambda trong `map` chưa chạy khi assembly, đối tượng hàm/lambda và lớp operator `map` **đã được tạo**. “Lazy” nói về việc phát sinh và xử lý tín hiệu, **không phủ nhận mọi chi phí hay side effect của mã Java xây dựng pipeline**.

## 4. `Mono.just(...)` khác `fromSupplier(...)`, `fromCallable(...)` và `defer(...)` ra sao?

### 4.1. `Mono.just(expression)`: biểu thức đối số chạy ngay

Java phải tính `expression` trước khi gọi `Mono.just(...)`. Vì vậy:

```java
Mono<String> result = Mono.just(expensiveCall());
```

`expensiveCall()` chạy **ngay ở assembly time**, trước mọi subscription, dù lời gọi đó gọi network, JDBC, đọc file hoặc tính toán đắt đỏ. Publisher `Mono.just` giữ giá trị đã nhận; mỗi subscriber thường nhận lại **chính giá trị đó**. Nếu `expensiveCall()` ném exception, lỗi có thể xảy ra **ngay lúc dựng chuỗi**, trước khi có publisher để gắn `onErrorResume`. Nếu truyền `null` vào `Mono.just`, sẽ phát sinh lỗi tại thời điểm xây dựng thay vì phát một `null`.

Ngược lại, `Mono.just("ready")` là hoàn toàn hợp lý: hằng/giá trị đã có sẵn được dùng lại trong nhiều lần đăng ký, không có công việc đắt đỏ nào cần trì hoãn.

### 4.2. `Mono.fromSupplier(...)` và `Mono.fromCallable(...)`: trì hoãn lời gọi

```java
Mono<String> fromSupplier = Mono.fromSupplier(() -> expensiveCall());

Mono<String> fromCallable = Mono.fromCallable(() -> mayThrowCheckedException());
```

Hai lambda được truyền vào ngay khi lắp ghép, nhưng **phần thân lambda chỉ chạy khi nguồn được kích hoạt trong quá trình đăng ký/yêu cầu dữ liệu**. Mỗi lần subscribe vào cold publisher có thể thực hiện lời gọi mới. `fromCallable` tiện khi công việc có thể ném checked exception: Reactor chuyển exception ở thời điểm thực thi thành tín hiệu `onError`, để downstream xử lý bằng `onErrorResume`/`onErrorMap`.

Nếu supplier/callable trả `null`, các factory này hoàn thành **rỗng** (không phát giá trị) thay vì phát `null`. Nếu cần bắt buộc có một phần tử, hãy kiểm tra và chuyển kết quả rỗng thành lỗi nghiệp vụ, chẳng hạn bằng `switchIfEmpty(...)`.

**Cảnh báo:** trì hoãn ≠ không chặn. `Mono.fromCallable(() -> jdbcRepository.findById(id))` vẫn gọi JDBC blocking khi thực thi. Nếu nguồn này chạy trên event-loop WebFlux, nó có thể chặn event-loop. Khi phải tích hợp tạm thời mã blocking, cần chuyển phần thực thi sang scheduler phù hợp, ví dụ `subscribeOn(Schedulers.boundedElastic())`, đồng thời giới hạn concurrency và tài nguyên. Cách này **không biến JDBC thành non-blocking**.

### 4.3. `Mono.defer(...)`: trì hoãn cả việc lựa chọn và tạo publisher

`Mono.defer(Supplier<Mono<T>>)` gọi hàm tạo publisher **cho mỗi subscription**. Khác biệt với `fromSupplier`: `fromSupplier` trì hoãn việc sinh **giá trị**; `defer` trì hoãn việc tạo **một publisher** (có thể là `Mono.empty()`, `Mono.error(...)`, hoặc một publisher khác).

```java
Mono<String> chosenAtSubscription = Mono.defer(() -> {
    boolean enabled = featureFlagIsEnabled();
    return enabled ? Mono.just("new-path") : Mono.just("old-path");
});
```

Trong đoạn **minh họa** trên, `featureFlagIsEnabled()` chỉ được hỏi khi có subscription. Đây không phải chương trình độc lập: phương thức kiểm tra flag do ứng dụng cung cấp.

Nếu viết `Mono.just(featureFlagIsEnabled() ? "new-path" : "old-path")`, flag được đọc **tại lúc dựng publisher**, nên các lần subscribe sau vẫn phát giá trị đã chọn. Nếu muốn chọn theo cấu hình hiện tại của từng request, `defer` đúng hơn.

### 4.4. Ví dụ so sánh thời điểm một cách cô lập

Đoạn sau có thể đưa vào `main` của một class Java có Reactor, giả sử thêm phương thức tĩnh `load()` như đã định nghĩa:

```java
static int load() {
    System.out.println("load called");
    return 7;
}

// Đặt trong main:
Mono<Integer> eager = Mono.just(load());
Mono<Integer> lazy = Mono.fromSupplier(() -> load());
System.out.println("assembled");

eager.subscribe(value -> System.out.println("eager: " + value));
lazy.subscribe(value -> System.out.println("lazy #1: " + value));
lazy.subscribe(value -> System.out.println("lazy #2: " + value));
```

Stdout cho **đoạn mã này**:

```text
load called
assembled
eager: 7
load called
lazy #1: 7
load called
lazy #2: 7
```

Lưu ý rằng giá trị kết quả đều là 7 không chứng minh công việc đã chạy số lần như nhau. Số lần gọi `load()` mới cho thấy một lần ở assembly với `just`, hai lần tại subscription với `fromSupplier`.

## 5. Assembly là tạo mô tả, không phải là “hoàn toàn không chạy gì”

Xem ví dụ:

```java
System.out.println("before");
Mono<String> mono = Mono.just("hello")
        .map(value -> {
            System.out.println("inside map");
            return value.toUpperCase();
        });
System.out.println("after");
```

Chưa có subscriber, nên stdout mới có:

```text
before
after
```

Nếu sau đó gọi `mono.subscribe(System.out::println)`, phần xử lý đồng bộ tiếp theo là:

```text
inside map
HELLO
```

Nhưng khi bạn gọi:

```java
Mono<String> mono = Mono.just(fetchBlocking());
```

thì `fetchBlocking()` vẫn chạy ngay, bởi đây là **lệnh Java dùng để tính đối số**. Khác biệt nằm ở vị trí đặt công việc: **ngoài lambda** và **bên trong lambda/operator được thực thi theo tín hiệu**.

Một nhầm lẫn tương tự xuất hiện trong:

```java
Mono<String> pipeline = source.map(value -> transform(value));
pipeline.map(value -> decorate(value));  // Kết quả bị bỏ, không thay đổi pipeline
return pipeline;                          // Chỉ có bước transform khi thực thi
```

Các operator của Reactor thường trả về **publisher mới**, không sửa ngầm publisher gốc. Để bổ sung thao tác, phải gán lại hoặc return kết quả:

```java
return source
        .map(value -> transform(value))
        .map(value -> decorate(value));
```

Hai đoạn này chỉ là minh họa vì `source`, `transform`, `decorate` chưa được định nghĩa. Điều quan trọng là chuỗi sau mỗi operator phải được giữ lại.

## 6. Một lần `subscribe()` có nhất thiết hoàn thành ngay không?

**Không.** Đăng ký và hoàn thành là hai sự kiện khác nhau.

- Nguồn đồng bộ, ví dụ `Mono.just(1)`, `Flux.range(1, 3)` và các operator đồng bộ thông thường, có thể phát toàn bộ tín hiệu trong lúc phương thức `subscribe()` còn trên stack.
- Nguồn bất đồng bộ, ví dụ `WebClient`, `Mono.delay(...)`, polling/scheduler hoặc một nguồn được nối với message broker, có thể hoàn thành **sau khi `subscribe()` đã trả về**. Dữ liệu đến từ callback/scheduler khi có kết quả.
- `subscribeOn(...)` tác động đến nơi việc subscription và công việc nguồn được sắp lịch (tùy nguồn); `publishOn(...)` tác động đến nơi tín hiệu downstream tiếp tục. Chúng không làm thay đổi quy tắc Java rằng đối số `Mono.just(expensiveCall())` đã được tính từ trước.
- Subscriber có thể hủy subscription trước khi có kết quả; không có gì đảm bảo mọi `doOnNext` hoặc `map` sẽ chạy. Một publisher rỗng có thể chỉ phát `onComplete`, không có `onNext`.

Ví dụ `Mono.delay(Duration.ofMillis(100))` có thể tiếp tục trên thread scheduler sau khi `subscribe()` trả về. Vì vậy viết:

```java
Mono.delay(java.time.Duration.ofMillis(100))
        .subscribe(value -> System.out.println("done"));
System.out.println("after subscribe");
```

không được dùng như **chứng cứ rằng callback đã hoàn tất khi đi qua dòng `subscribe()`**. Với nguồn async, chương trình độc lập còn cần duy trì vòng đời process đủ lâu để callback chạy, còn ứng dụng WebFlux sẽ có vòng đời server quản lý. Không dựa vào thứ tự log từ nhiều thread để suy luận sai về thứ tự lắp ghép.

### 6.1. `block()` cũng tạo subscription

Trong một ứng dụng dòng lệnh hoặc bài kiểm thử, `mono.block()` có thể thuận tiện để chờ kết quả. Nó **đăng ký** vào publisher, chờ kết quả cuối và trả giá trị; với cold publisher, gọi `block()` hai lần có thể chạy nguồn hai lần. `Flux.blockLast()` cũng kích hoạt subscription và chờ phần tử cuối.

**Không dùng `block()` để lấy giá trị ngay bên trong đường xử lý WebFlux event-loop.** Vừa mất lợi ích non-blocking, vừa có thể gây lỗi trên các thread không cho phép blocking. Để truyền kết quả giữa service/controller, return `Mono` hoặc `Flux`; tại ranh giới imperative phải chủ động xét cách cô lập chờ.

## 7. Cold và hot quyết định tác dụng của mỗi subscription

### 7.1. Cold publisher: mỗi subscriber có thể bắt đầu công việc riêng

`Mono.fromSupplier(...)`, `Mono.defer(...)` và `Flux.range(...)` thông thường là cold. Mỗi subscription nhận quá trình phát tín hiệu riêng. Nếu cold source chứa HTTP request hoặc truy vấn DB, **đăng ký lại** có thể gây **gọi HTTP/query lại**.

Ví dụ:

```java
Mono<Integer> cold = Mono.fromSupplier(counter::incrementAndGet);
```

Đây là ví dụ minh họa (cần biến `counter` kiểu `AtomicInteger`). Hai subscription khác nhau lần lượt có thể nhận 1 và 2. Nếu publisher được `retry(...)` hoặc `repeat(...)` tái đăng ký, side effect ở upstream có thể xảy ra thêm lần nữa. Điều này đặc biệt nguy hiểm với thao tác ghi tiền, thanh toán, gửi email hoặc create resource nếu không có cơ chế idempotency.

### 7.2. Hot publisher: nguồn có thể đã chạy, subscriber mới không nhất thiết thấy lịch sử

Một `Sinks.Many` phát sự kiện vào luồng nóng (hot) có thể có tín hiệu xảy ra **không phụ thuộc vào thời điểm một subscriber cụ thể tới**. Subscriber muộn có thể bỏ lỡ tín hiệu đã phát, hoặc chỉ nhận replay theo cấu hình sink. Không thể áp dụng máy móc quy tắc “mỗi subscribe chạy nguồn từ đầu”.

Các toán tử tạo **chia sẻ/caching** cũng làm thay đổi hành vi:

- `share()` có thể dùng một upstream subscription chung cho những downstream subscriber đang tham gia; hành vi khi các subscriber rời đi hay đến muộn phụ thuộc loại publisher/toán tử.
- `cache()` lưu tín hiệu để các subscriber sau dùng lại; những subscription sau có thể không tái thực hiện phần nguồn đã được cache.
- `publish().refCount(...)`, `replay(...)` và những toán tử tương tự thay đổi thời điểm nối nguồn, điều kiện khởi chạy và cách phát lại dữ liệu.

Một điểm tinh tế: `Mono.just(value)` đã giữ **giá trị** ngay lúc assembly, nhưng thường vẫn là publisher cold theo nghĩa **mỗi subscriber được phát lại giá trị đó khi đăng ký**. Việc tính giá trị sớm không tự động làm nguồn đó thành “hot”. Tương tự, `Flux.interval(...)` không mặc nhiên là một luồng hot chia sẻ toàn cục: mỗi lần subscription thường thiết lập lịch phát riêng nếu chưa biến đổi thành nguồn chia sẻ.

**Cần phân biệt ba chuyện:** (1) lúc tính giá trị/khởi động nguồn; (2) mỗi subscriber có subscription riêng hay chia sẻ upstream; (3) dữ liệu quá khứ được phát lại hay không.

## 8. Trong Spring WebFlux, ai gọi `subscribe()`?

Controller WebFlux thường **trả về publisher** cho framework:

```java
@GetMapping("/products/{id}")
public Mono<ProductDto> get(@PathVariable String id) {
    System.out.println("controller: build pipeline");
    return webClient.get()
            .uri("http://catalog-service/products/{id}", id)
            .retrieve()
            .bodyToMono(ProductDto.class)
            .map(this::toDto);
}
```

Đây là **đoạn minh họa controller**, cần có `webClient`, `ProductDto` và `toDto` do ứng dụng định nghĩa, không phải class Java độc lập. Khi handler được gọi, log `controller: build pipeline` chạy tại lúc controller **tạo và trả publisher**. Lời gọi HTTP non-blocking tương ứng với `WebClient` thường được bắt đầu khi subscription diễn ra; callback `map` chỉ chạy sau khi có dữ liệu đầu vào.

**Spring WebFlux là bên subscribe** vào publisher trả về để tạo response và quản lý completion/error/cancellation theo vòng đời request. Không tự gọi `subscribe()` ở controller/service chỉ để “kích hoạt” một pipeline vốn cần trả về cho framework:

```java
// SAI về vòng đời HTTP: publisher bị kích hoạt bên lề,
// còn framework không chờ được kết quả/không quản lý được lỗi.
service.save(item).subscribe();
return Mono.just("accepted");
```

Đoạn trên là **minh họa lỗi** (các biểu thức `service`, `item` là giả định). Nếu thao tác save là bắt buộc trước khi trả kết quả, nên ghép vào publisher được return:

```java
return service.save(item)
        .thenReturn("saved");
```

`thenReturn` chỉ phát "saved" sau khi `save(item)` hoàn tất bình thường; nếu `save(item)` báo lỗi, kết quả cũng báo lỗi thay vì tạo thành công giả. **Ghi chú:** việc *gọi* `service.save(item)` để lấy publisher vẫn nằm trong pha lắp ghép; bên trong service phải tránh công việc blocking/eager ngoài publisher nếu muốn mọi công việc được trì hoãn.

Nếu business thực sự cần tác vụ nền độc lập với response, phải thiết kế lifecycle, error handling, observability, retry và tính bền vững riêng (ví dụ message queue/outbox). Gọi `subscribe()` tùy tiện để tạo một công việc không được quản lý là khó kiểm soát.

## 9. Logging và debugging: log nào báo assembly, log nào báo execution?

Ví dụ:

```java
System.out.println("assembly start");
Mono<Integer> pipeline = Mono.just(3)
        .doOnSubscribe(s -> System.out.println("subscription attached"))
        .map(i -> i * 2)
        .doOnNext(i -> System.out.println("next: " + i))
        .doFinally(signal -> System.out.println("finally: " + signal));
System.out.println("assembly end");
pipeline.subscribe(i -> System.out.println("subscriber: " + i));
```

Vì nguồn đồng bộ và chỉ hoàn tất bình thường, thứ tự đầu ra là:

```text
assembly start
assembly end
subscription attached
next: 6
subscriber: 6
finally: onComplete
```

Cách diễn giải:

- Log nằm ngoài lambda trong method dựng chain được in **khi method đó chạy**, dù chưa có subscription.
- `doOnSubscribe` cho biết nguồn nhận subscription; nó **không xác nhận** đã hoàn thành thao tác I/O hay đã có dữ liệu.
- `doOnNext` chỉ chạy nếu có phần tử; không chạy với `Mono.empty()`.
- `doOnError` chỉ chạy khi có tín hiệu lỗi; `doFinally` thấy completion, error hoặc cancellation, vì vậy dùng để kiểm tra đường kết thúc sau subscription.
- Reactor `log()` giúp quan sát subscription, request, onNext, onComplete, cancel nhưng có thể tạo log rất nhiều dưới tải cao. Chỉ bật phù hợp trong debug, tránh log dữ liệu nhạy cảm.

Đối với async chain, các log từ nhiều thread có thể xen kẽ; thêm **request/correlation ID** và tracing phù hợp với Reactor Context giúp xác định tín hiệu thuộc request nào. Không suy luận rằng cùng một subscription luôn chạy trên một thread duy nhất.

## 10. Những lỗi phổ biến và cách sửa

| Cách hiểu/cách viết dễ sai | Vấn đề | Hướng đúng |
| --- | --- | --- |
| `Mono.just(blockingCall())` để trì hoãn I/O | `blockingCall()` chạy ngay ở assembly; còn có thể chặn event-loop | Dùng non-blocking API; nếu bắt buộc bridge, `fromCallable(...).subscribeOn(boundedElastic())` có giới hạn |
| “Tạo `Mono` là dữ liệu đã được truy vấn” | Đã dựng publisher nhưng chưa chắc có subscription/demand | Xác định nơi publisher được return và ai subscribe |
| Tự `subscribe()` trong controller rồi trả `Mono.just("ok")` | Tách tác vụ ra khỏi response và mất error/cancel propagation | Return chain, ví dụ `service.save(...).thenReturn(...)` |
| Gọi hai lần `subscribe()` vào cold HTTP source để lấy một kết quả | Có thể gây hai request thực sự | Chia sẻ/caching có chủ đích hoặc compose trong một pipeline |
| Tưởng `map`, `flatMap` chạy khi gắn vào chain | Lambda chỉ xử lý khi xuất hiện tín hiệu tương ứng | Dùng log tại assembly và tại signal để phân biệt |
| Gọi `pipeline.map(...)` nhưng bỏ kết quả | Pipeline gốc không thay đổi | Return/gán publisher mới |
| Gọi `block()` trên event-loop | Blocking, mất lợi ích WebFlux và có thể bị từ chối | Giữ return type `Mono`/`Flux` qua các tầng |
| Tưởng `subscribeOn` làm `Mono.just(blockingCall())` an toàn | Đối số Java được tính trước khi publisher tồn tại | Đưa lời gọi vào lambda trì hoãn rồi chọn scheduler phù hợp |
| Đồng nhất `subscribe()` với hoàn thành tức thì | Nguồn async có thể chạy sau khi subscribe trả về | Theo dõi `onNext`/`onError`/`onComplete` và dùng test bất đồng bộ |
| Dùng `retry` cho nguồn có side effect không idempotent | Có thể lặp lại ghi/HTTP call khi resubscribe | Thiết kế idempotency, điều kiện retry, backoff và giới hạn số lần |
| Coi mọi publisher là cold | Hot/cached/shared publisher có thể phát từ trước hoặc dùng chung upstream | Kiểm tra sink, `share`, `cache`, `publish` và replay policy |

### 10.1. Đặc biệt lưu ý với `flatMap`

`flatMap(value -> asyncCall(value))` chỉ gọi lambda để tạo publisher con khi upstream **phát một giá trị phù hợp**. Sau đó Reactor subscribe vào publisher con để ghép kết quả; nó không tương đương với việc đã gọi `asyncCall(...)` tại assembly time của pipeline bên ngoài.

Nếu `asyncCall` tự thực hiện side effect blocking trước khi return publisher, side effect đó vẫn chạy **tại lúc lambda được gọi**, thường trong giai đoạn xử lý signal. Dù nằm trong `flatMap`, blocking vẫn có thể xảy ra trên event-loop. Vì vậy phải xem **thân hàm**, không chỉ nhìn kiểu trả về `Mono<T>`.

`flatMap` cũng có thể mở nhiều publisher con đồng thời, trong khi `concatMap` thường giữ thứ tự tuần tự của các inner subscription. Với `Flux` lớn, cần cân nhắc giới hạn concurrency, memory và backpressure trước khi thực thi.

### 10.2. Điều kiện `switchIfEmpty` cũng có thể phát sinh việc dựng publisher sớm

Ví dụ `source.switchIfEmpty(fallbackPublisher())` **gọi phương thức Java `fallbackPublisher()` ngay lúc lắp ghép** để lấy đối số publisher, dù nguồn chính sau này có phát giá trị. Nếu phương thức đó chỉ *tạo một publisher lazy*, các tín hiệu của fallback không được chạy nếu nguồn không rỗng; nhưng side effect diễn ra trong lúc *tạo* fallback vẫn xuất hiện sớm.

Để trì hoãn cả việc gọi hàm chọn fallback, có thể viết:

```java
return source.switchIfEmpty(Mono.defer(() -> fallbackPublisher()));
```

Đây là đoạn minh họa với `source` và `fallbackPublisher()` giả định. Quy tắc chung: một lambda trì hoãn ở đúng **ranh giới có tác vụ** mới đảm bảo tác vụ ấy không bị gọi sớm.

## 11. Kiểm thử đúng thời điểm thực thi

Test quan trọng là chứng minh rằng code chưa làm việc trước subscription và chỉ làm việc khi publisher được kích hoạt. Với `reactor-test`, có thể dùng `StepVerifier` để xác nhận signals; đồng thời đo side effect bằng counter.

Ví dụ minh họa bên trong một test JUnit 5 với `reactor-test`:

```java
import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;
import static org.junit.jupiter.api.Assertions.assertEquals;

class SubscriptionTimingTest {
    @Test
    void coldSourceRunsForEachSubscription() {
        AtomicInteger counter = new AtomicInteger();
        Mono<Integer> source = Mono.fromSupplier(counter::incrementAndGet);

        assertEquals(0, counter.get()); // Assembly chưa chạy source

        StepVerifier.create(source)
                .expectNext(1)
                .verifyComplete();

        assertEquals(1, counter.get());

        StepVerifier.create(source)
                .expectNext(2)
                .verifyComplete();

        assertEquals(2, counter.get());
    }
}
```

Cần `org.junit.jupiter:junit-jupiter` và `io.projectreactor:reactor-test` trong test dependencies (phiên bản do Spring Boot BOM quản lý nếu dùng Spring Boot); chạy bằng trình chạy JUnit/Gradle test của dự án. Test này không cần `Thread.sleep(...)` và không dựa vào timing ngẫu nhiên.

Có thể mở rộng kiểm thử với `Mono.defer` để chứng minh biến flag được đánh giá ở từng lần subscribe; dùng `StepVerifier.withVirtualTime(...)` cho publisher dựa vào thời gian như `delay`/`interval`; dùng `PublisherProbe` để xác nhận một nhánh fallback thật sự được subscribe. Với lỗi/cancellation, test cần khẳng định đường `onError` và `doFinally(CANCEL)` tương ứng thay vì chỉ kiểm số dòng log.

## 12. Checklist áp dụng khi đọc code thực tế

Với một method trả `Mono`/`Flux`, lần lượt đánh dấu:

1. **Điểm dựng:** những lời gọi Java nào xảy ra trước khi return publisher? Chúng có thể blocking hoặc thay đổi trạng thái không?
2. **Nguồn:** `just`, `fromSupplier`, `defer`, `WebClient`, R2DBC, sink hot hay publisher được cache? Có sự kiện nào phát từ trước không?
3. **Điểm subscription:** controller WebFlux, test `StepVerifier`, code CLI `block()` hay một consumer có vòng đời riêng? Có gọi `subscribe()` ngoài ý muốn không?
4. **Điểm phát dữ liệu:** toán tử nào chạy theo `onNext`, nhánh nào chỉ chạy khi empty/error, nguồn nào chỉ khởi động khi nhận demand?
5. **Tái đăng ký:** `retry`, `repeat`, nhiều subscriber và replay/cache sẽ tạo thêm I/O hay reuse kết quả? Side effect có idempotent không?
6. **Thread và hủy:** có nguồn bất đồng bộ hoặc scheduler không; có code blocking chạy trên event-loop; timeout/cancel có giải phóng resource và ngừng công việc đúng không?

## 13. Ghi nhớ

**Assembly tạo và nối các publisher; subscription thiết lập việc tiêu thụ, từ đó nguồn và operator xử lý dữ liệu theo demand và tín hiệu.** Với cold publisher, mỗi subscription thường khởi động chuỗi nguồn riêng; với hot/shared/cached publisher, hành vi còn phụ thuộc cách chia sẻ và replay.

Hãy nhớ ba ví dụ đối chiếu: `Mono.just(call())` gọi `call()` ngay; `Mono.fromSupplier(() -> call())` gọi khi nguồn được kích hoạt; `Mono.defer(() -> buildPublisher())` trì hoãn cả việc tạo publisher. Trong Spring WebFlux, hãy **return publisher cho framework quản lý subscription**, đặt side effect trong ranh giới hợp lý và quan sát tín hiệu thực tế thay vì đoán qua vị trí lời gọi `map` hay `subscribe()`.
