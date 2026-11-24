# Function<Flux<T>, Mono<Void>> cho xử lý bất đồng bộ không trả dữ liệu

## 1. Bài toán: hoàn thành công việc mà không cần trả payload

Một dịch vụ nhận sự kiện đơn hàng và lưu lịch sử kiểm toán có thể không cần tạo bản ghi phản hồi cho mỗi sự kiện. Tuy nhiên, hệ thống vẫn cần biết **việc ghi đã hoàn tất hay thất bại**. Hai câu hỏi này khác nhau:

- Có cần **trả dữ liệu nghiệp vụ** không? Ví dụ một `Decision`, `Receipt` hoặc `OrderSummary`.
- Có cần **truyền tín hiệu hoàn thành hoặc lỗi** không? Ví dụ chỉ thông báo rằng toàn bộ thao tác ghi đã xong.

Trong **Spring Cloud Function**, có thể đóng gói chức năng bằng Java `Supplier`, `Function` và `Consumer`, tra cứu qua `FunctionCatalog`, composition và đưa cùng logic vào HTTP, event binder hoặc serverless. Với Reactor, chữ ký:

~~~java
Function<Flux<OrderEvent>, Mono<Void>>
~~~

cho phép mô tả một chuỗi công việc bất đồng bộ nhận nhiều `OrderEvent` và **không phát payload đầu ra**, nhưng vẫn trả một publisher báo **`onComplete` hoặc `onError`**.

Ví dụ ý tưởng:

~~~java
Function<Flux<OrderEvent>, Mono<Void>> audit =
    orders -> orders
        .concatMap(order -> auditStore.append(order)) // Mono<Void>
        .then();
~~~

Đây là một hàm nhận **một publisher đầu vào**. Với mỗi phần tử, nó ghép một thao tác ghi bất đồng bộ vào pipeline. `then()` tạo `Mono<Void>` hoàn tất khi upstream xử lý xong, hoặc kết thúc bằng lỗi nếu upstream lỗi. Để thao tác thực sự chạy, **caller hoặc adapter phải subscribe publisher kết quả**.

Điểm mấu chốt:

> **“Không trả dữ liệu” không có nghĩa “không cần chờ kết quả”.** `Mono<Void>` vẫn là một hợp đồng bất đồng bộ, có tín hiệu hoàn tất/lỗi và có thể bị hủy.

### Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích chính xác ý nghĩa `Function<Flux<T>, Mono<Void>>`, `Mono<Void>` và `then()`.
2. Phân biệt hàm trả publisher với `Consumer<Flux<T>>` trả `void`.
3. Dùng `concatMap` hoặc `flatMap` để chờ các tác vụ bất đồng bộ trên từng phần tử.
4. Chọn vị trí xử lý lỗi, retry, timeout và cancellation đúng với nghiệp vụ.
5. Hiểu giới hạn của chữ ký này đối với luồng dài hạn, message acknowledgment và transaction.
6. Viết test Reactor kiểm tra tác dụng phụ, completion, error và hành vi lazy.
7. Biết cần xác minh gì khi đưa function qua HTTP, sự kiện hoặc serverless.

## 2. Đọc đúng chữ ký Function<Flux<T>, Mono<Void>>

Java `Function<I,O>` có phương thức:

~~~java
@FunctionalInterface
public interface Function<I, O> {
    O apply(I input);
}
~~~

Trong bài này, `I = Flux<T>` và `O = Mono<Void>`:

| Thành phần | Ý nghĩa |
| --- | --- |
| `Function<...>` | Hàm nhận một đầu vào, trả một kết quả khi gọi `apply(...)` |
| `Flux<T>` | Publisher phát 0 đến N phần tử `T` trong mỗi subscription |
| `Mono<Void>` | Publisher không phát giá trị nghiệp vụ, chỉ báo hoàn tất hoặc lỗi |
| `apply(flux)` | Lời gọi Java tạo publisher mô tả tác vụ; không nhất thiết đã xử lý `T` |
| `subscribe()` | Bắt đầu tiêu thụ publisher, kích hoạt chuỗi thao tác theo ngữ nghĩa Reactor |
| `onComplete` | Tín hiệu kết thúc bình thường của publisher |
| `onError` | Tín hiệu kết thúc do lỗi; không có `onComplete` sau đó |

`Void` ở đây là kiểu trả về của Java giúp biểu diễn **không có giá trị kết quả**. Không có đối tượng `Void` hay `null` nào được phát qua `onNext`: Reactor không cho phép phát giá trị `null`.

### 2.1. Phân biệt Mono<Void> với void

~~~java
// Không có kết quả trả về để caller quản lý.
Consumer<Flux<OrderEvent>> c = orders -> {
    // accept(...) trả void
};

// Có publisher đại diện cho quá trình xử lý.
Function<Flux<OrderEvent>, Mono<Void>> f = orders ->
    orders.then();
~~~

`Consumer.accept` chỉ trả về sau khi **thân Java của hàm** kết thúc. Nếu trong consumer khởi chạy tác vụ I/O bất đồng bộ bằng `subscribe()`, `accept` có thể trả `void` trước khi tác vụ hoàn tất. Caller không có publisher kết quả để theo dõi.

Ngược lại, `Function.apply` trả về `Mono<Void>`, và caller/adapter có thể subscribe, chờ completion, nhận error, hoặc hủy subscription. **Việc có thể theo dõi** không có nghĩa framework nào cũng sẽ chờ và áp dụng acknowledgement đúng lúc: điều này còn phụ thuộc adapter.

### 2.2. Mono.empty(), Mono<Void> và giá trị của tín hiệu

~~~java
Mono<Void> alreadyDone = Mono.empty();

Mono<Void> failed =
    Mono.error(new IllegalStateException("Cannot persist order"));

Mono<Void> delayed =
    Mono.delay(Duration.ofMillis(200)).then();
~~~

- `alreadyDone` khi subscribe sẽ hoàn tất mà không phát phần tử.
- `failed` phát `onError`.
- `delayed` chờ một publisher thời gian rồi chỉ báo hoàn tất.

`Mono<Void>` không đồng nghĩa thao tác đã chạy thành công trước thời điểm được trả về. Nó có thể đang *chờ được subscribe*.

## 3. then(): biến một pipeline thành tín hiệu hoàn thành

Toán tử `then()` bỏ qua các giá trị `onNext` của upstream nhưng **vẫn subscribe upstream** và theo dõi tín hiệu terminal:

~~~java
Mono<Void> completion = Flux.just("A", "B", "C")
    .map(String::trim)
    .then();
~~~

Với subscriber, upstream vẫn xử lý `A`, `B`, `C`. Tuy nhiên, `completion` không phát các chuỗi này: nó chỉ phát `onComplete` khi upstream kết thúc bình thường.

~~~mermaid
flowchart LR
    SOURCE["Flux<T> phát A, B, C"] --> OPERATORS["Toán tử xử lý từng T"]
    OPERATORS --> THEN["then()"]
    THEN --> RESULT["Mono<Void>"]
    RESULT --> OK["onComplete"]
    RESULT --> ERR["onError"]
~~~

`then()` **không** có nghĩa “bỏ qua việc xử lý upstream”. Nó chỉ bỏ qua **giá trị đầu ra**. Lỗi upstream vẫn được chuyển tới kết quả và cancellation vẫn có tác động đến subscription.

### 3.1. Không nhầm then() với doOnNext()

~~~java
Function<Flux<String>, Mono<Void>> logs = input ->
    input
        .doOnNext(System.out::println)
        .then();
~~~

Ở đây `doOnNext` chạy một **side effect đồng bộ** mỗi khi có phần tử. `then()` chỉ phát tín hiệu hoàn tất cuối cùng. Cách này có thể dùng để log nhanh, nhưng nếu muốn ghi dữ liệu **bất đồng bộ** thì `doOnNext` không phải công cụ thích hợp.

Ví dụ sai khi thư viện ghi trả `Mono<Void>`:

~~~java
// Sai: tạo Mono con rồi bỏ qua publisher; việc ghi không được chờ.
Function<Flux<OrderEvent>, Mono<Void>> wrong = events ->
    events
        .doOnNext(event -> auditStore.append(event))
        .then();
~~~

`auditStore.append(event)` có thể trả về một publisher cold mà chưa ai subscribe, nên dữ liệu chưa chắc được ghi. Phải **ghép inner publisher vào pipeline** bằng `concatMap` hoặc `flatMap`.

### 3.2. Những dạng then liên quan

| Toán tử | Hành vi chính | Kết quả |
| --- | --- | --- |
| `flux.then()` | Chờ upstream hoàn tất, bỏ `onNext` | `Mono<Void>` |
| `flux.thenReturn(value)` | Chờ upstream hoàn tất rồi phát một giá trị cố định | `Mono<R>` |
| `flux.then(mono)` | Chờ upstream hoàn tất rồi subscribe vào `mono` | `Mono<R>` |
| `flux.collectList()` | Gom tất cả phần tử khi luồng hoàn tất | `Mono<List<T>>` |
| `flux.ignoreElements()` | Bỏ qua phần tử, chỉ giữ terminal | `Mono<T>` với không có giá trị |

`collectList()` cần bộ nhớ đủ cho mọi phần tử và phải đợi luồng kết thúc. Với nghiệp vụ “ghi từng event rồi báo đã xong”, `then()` thường trực tiếp hơn và không cần gom payload.

## 4. Ví dụ hoàn chỉnh: audit đơn hàng bất đồng bộ

Giả sử ứng dụng nhận `OrderEvent` và cần ghi vào một kho kiểm toán có API reactive. Không yêu cầu phát message đầu ra cho từng đơn. Class cấu hình dưới đây dùng Java 17+ (vì có `record`), Spring Cloud Function/Spring Framework và Reactor.

~~~java
package demo.functions;

import java.util.function.Function;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Configuration
public class OrderAuditConfiguration {

    public record OrderEvent(String orderId, long amountCents) {}

    // Một bản ghi được lưu xong khi Mono do append trả về onComplete.
    public interface AuditStore {
        Mono<Void> append(OrderEvent order);
    }

    @Bean
    public Function<Flux<OrderEvent>, Mono<Void>> auditOrders(
            AuditStore auditStore) {

        return incoming -> incoming
            .concatMap(auditStore::append)
            .then();
    }
}
~~~

### 4.1. Từng bước pipeline thực thi

Giả sử caller đưa hai đơn:

~~~java
Flux<OrderAuditConfiguration.OrderEvent> input = Flux.just(
    new OrderAuditConfiguration.OrderEvent("ORD-101", 12_000),
    new OrderAuditConfiguration.OrderEvent("ORD-102", 15_000)
);

Function<
    Flux<OrderAuditConfiguration.OrderEvent>,
    Mono<Void>
> function = configuration.auditOrders(auditStore);

Mono<Void> completion = function.apply(input);
~~~

Ở đoạn trên, `configuration` và `auditStore` là các dependency được tạo trong ứng dụng/test. Sau `apply`, biến `completion` mô tả thao tác ghi; nó chưa chứng minh rằng hai đơn đã được lưu.

Khi một subscriber đăng ký:

1. `concatMap` nhận `ORD-101` và subscribe vào `auditStore.append(ORD-101)`.
2. Nếu thao tác đầu hoàn tất, `concatMap` tiếp tục `ORD-102`.
3. Khi thao tác thứ hai hoàn tất và `input` phát `onComplete`, `then()` hoàn tất.
4. Nếu một thao tác phát `onError` chưa được xử lý, publisher kết quả cũng phát `onError`.

Sơ đồ:

~~~mermaid
sequenceDiagram
    participant Caller as Caller / adapter
    participant F as auditOrders
    participant Flux as Input Flux
    participant Store as AuditStore

    Caller->>F: apply(input)
    F-->>Caller: Mono<Void>
    Caller->>F: subscribe(result)
    F->>Flux: subscribe input
    Flux-->>F: onNext(ORD-101)
    F->>Store: append(ORD-101)
    Store-->>F: onComplete
    Flux-->>F: onNext(ORD-102)
    F->>Store: append(ORD-102)
    Store-->>F: onComplete
    Flux-->>F: onComplete
    F-->>Caller: onComplete (không có payload)
~~~

**Điều kiện của ví dụ:** `AuditStore.append` phải trả publisher thực sự báo thành công sau khi thao tác ghi theo yêu cầu nghiệp vụ đã hoàn tất. Nếu API phát `onComplete` trước khi dữ liệu được commit bền vững, thì `Mono<Void>` của function cũng không thể tự nâng mức bảo đảm đó.

### 4.2. Vì sao concatMap thay vì map?

~~~java
// Không thực thi inner Mono theo ý định:
Flux<Mono<Void>> nested = input.map(auditStore::append);

// Ghép thao tác vào pipeline và đợi từng Mono:
Mono<Void> done = input
    .concatMap(auditStore::append)
    .then();
~~~

`map` ở dạng đầu chỉ phát **đối tượng Mono** như một phần tử của `Flux<Mono<Void>>`. `concatMap` mới subscribe từng inner publisher; nhờ vậy lỗi hoặc completion của việc ghi tham gia vào luồng chính.

### 4.3. Phần tử đầu vào rỗng thì sao?

~~~java
Mono<Void> emptyBatch = function.apply(Flux.empty());
~~~

Khi subscribe, nếu không có bản ghi, `concatMap` không gọi `AuditStore.append`, và `then()` hoàn tất. Điều này đúng nếu “không có dữ liệu” là kết quả hợp lệ. Nếu nghiệp vụ bắt buộc tối thiểu một sự kiện, cần thêm validation hoặc một toán tử phát lỗi khi rỗng.

## 5. Chọn concatMap hay flatMap khi ghi bất đồng bộ

Khi I/O của từng phần tử trả một publisher, chọn toán tử dựa trên **thứ tự, khả năng song song và giới hạn tải**.

| Toán tử | Số tác vụ con | Thứ tự xử lý | Khi nào dùng |
| --- | --- | --- | --- |
| `concatMap(mapper)` | Theo thứ tự, từng inner publisher một | Bảo đảm không có hai tác vụ inner đang chạy chồng nhau trong pipeline | Event cùng khóa phải ghi tuần tự, cần đơn giản hóa trạng thái |
| `flatMap(mapper, concurrency)` | Nhiều inner publisher đồng thời, có giới hạn | Thời điểm hoàn tất có thể khác thứ tự đầu vào | I/O độc lập, muốn tăng thông lượng |
| `flatMapSequential(mapper, concurrency)` | Có thể đồng thời, giữ thứ tự giá trị phát ra | Không bảo đảm **side effect bên ngoài** hoàn thành theo thứ tự | Cần thứ tự kết quả, nhưng thao tác con được phép đồng thời |

Với `Mono<Void>`, không có giá trị nội bộ để sắp xếp ở đầu ra. Vì vậy, **không được chọn `flatMapSequential` với kỳ vọng rằng các thao tác lưu database sẽ lần lượt commit đúng thứ tự**.

### 5.1. Chạy đồng thời tối đa tám thao tác

~~~java
@Bean
Function<Flux<OrderEvent>, Mono<Void>> auditInParallel(
        AuditStore auditStore) {

    return incoming -> incoming
        .flatMap(auditStore::append, 8)
        .then();
}
~~~

Đây là phương án thay thế cho bean `auditOrders` ở mục 4; khi đưa cả hai vào cùng ứng dụng cần đặt tên function/definition rõ ràng. Một lần apply tạo pipeline; khi có subscriber, tối đa tám inner publishers được subscribe đồng thời trong toán tử này.

Lưu ý:

- Các thao tác có thể hoàn thành khác thứ tự đầu vào.
- Concurrency chỉ giới hạn số inner publishers trong một subscription của toán tử; nếu nhiều lời gọi hoặc nhiều instance chạy đồng thời thì tổng tải còn cao hơn.
- Dù `flatMap` có concurrency, database/HTTP client vẫn cần pool, timeout và chính sách tải phù hợp.
- Với cùng khóa nghiệp vụ (ví dụ một `orderId`), giao dịch cập nhật tuần tự có thể cần `concatMap` hoặc phân vùng theo key.

### 5.2. Không chặn thread để đợi I/O

Sai lầm phổ biến:

~~~java
Function<Flux<OrderEvent>, Mono<Void>> blocking = incoming ->
    incoming
        .doOnNext(order -> auditStore.append(order).block())
        .then();
~~~

`block()` biến lời gọi thành chờ đồng bộ và có thể làm nghẽn event loop; ngoài ra việc subscribe nhiều lần có thể khiến upstream làm lại công việc.

Với JDBC hoặc API cũ thực sự blocking, cần cân nhắc cô lập trên `Schedulers.boundedElastic()`:

~~~java
Function<Flux<OrderEvent>, Mono<Void>> legacyAudit = incoming ->
    incoming
        .concatMap(order ->
            Mono.fromRunnable(() -> legacyStore.appendBlocking(order))
                .subscribeOn(
                    reactor.core.scheduler.Schedulers.boundedElastic()
                )
        )
        .then();
~~~

Ví dụ này giả sử `legacyStore.appendBlocking` trả `void`. `boundedElastic` di chuyển tác vụ blocking sang nhóm thread thích hợp; **nó không biến thư viện blocking thành non-blocking**. Vẫn phải quản lý concurrency, kết nối và timeout.

## 6. Vì sao Function<Flux<T>, Mono<Void>> thường tốt hơn Consumer<Flux<T>>?

Một reactive consumer tường minh có thể được viết:

~~~java
@Bean
Consumer<Flux<OrderEvent>> auditConsumer(AuditStore store) {
    return incoming -> incoming
        .concatMap(store::append)
        .subscribe(
            ignored -> {},
            error -> log.error("Audit stream failed", error)
        );
}
~~~

Vấn đề ở đây là `Consumer.accept` trả `void`, trong khi một `Disposable` từ `subscribe` bị bỏ qua. Caller không có kết quả mô tả tác vụ bất đồng bộ và không sở hữu cancellation. Log lỗi nội bộ không đồng nghĩa framework biết batch đã thất bại.

Còn:

~~~java
@Bean
Function<Flux<OrderEvent>, Mono<Void>> auditFunction(AuditStore store) {
    return incoming -> incoming
        .concatMap(store::append)
        .then();
}
~~~

trả một publisher có thể được caller/adapter subscribe và quản lý. Function **không tự gọi `subscribe()`**; nó biểu diễn cách xử lý bằng một pipeline.

| Tiêu chí | `Consumer<Flux<T>>` tự subscribe | `Function<Flux<T>, Mono<Void>>` |
| --- | --- | --- |
| Kết quả Java | `void` | `Mono<Void>` |
| Hợp đồng hoàn tất | Chủ yếu nằm trong callback/handle nội bộ | Phát qua publisher trả về |
| Báo lỗi | Consumer phải bắt và xử lý trong subscription của mình | `onError` có thể truyền tới caller |
| Hủy | Consumer cần quản lý `Disposable` | Caller có thể hủy subscription đầu ra |
| Composition | Là bước kết thúc mang `void` | Bước trả publisher terminal, có thể tham gia composition tương thích |
| Phát payload nghiệp vụ | Không | Không |
| Broker ack đúng một lần | Không tự bảo đảm | Không tự bảo đảm |

**Trường hợp cần `Consumer<Flux<T>>` vẫn tồn tại**, chẳng hạn một adapter bắt buộc chữ ký consumer hoặc consumer tự sở hữu một kết nối dài hạn và tự quản lý lifecycle. Khi đó phải quản lý `Disposable`, lỗi, hủy, tài nguyên và khả năng phục hồi tường minh.

### 6.1. Fire-and-forget không có cùng hợp đồng hoàn tất

Một anti-pattern khác:

~~~java
Function<Flux<OrderEvent>, Mono<Void>> misleading = input -> {
    input.subscribe(order -> auditStore.append(order).subscribe());
    return Mono.empty();
};
~~~

Hàm này báo `Mono.empty()` hoàn tất gần như ngay lập tức, trong khi các thao tác ghi chạy rời khỏi pipeline. Lỗi, cancellation và độ bền của việc ghi không còn gắn với kết quả. Hàm cũng tạo **nested subscribe** và không giới hạn concurrency.

**Quy tắc:** nếu caller cần chờ hoặc quan sát kết quả của một tác vụ asynchronous, hãy *trả publisher đại diện cho tác vụ đó* và ghép các publisher con, thay vì subscribe ngầm rồi trả `Mono.empty()`.

## 7. Lỗi của một bản ghi và lỗi của cả luồng

Trong Reactive Streams, `onError` là tín hiệu **kết thúc** subscription. Nếu một `append` lỗi và không được xử lý, pipeline sẽ kết thúc; `then()` phát lại lỗi cho subscriber.

### 7.1. Chính sách fail-fast

~~~java
Function<Flux<OrderEvent>, Mono<Void>> failFast = incoming ->
    incoming
        .concatMap(auditStore::append)
        .then();
~~~

Khi đơn thứ hai lỗi, đơn thứ ba có thể không được xử lý. Cách này hợp lý nếu lỗi là sự cố phải dừng, ví dụ không thể bảo đảm tuần tự hoặc tính nhất quán.

### 7.2. Xử lý lỗi độc lập từng phần tử

Nếu nghiệp vụ cho phép gửi bản ghi lỗi vào dead-letter store rồi **tiếp tục** xử lý phần tử sau:

~~~java
Function<Flux<OrderEvent>, Mono<Void>> withDeadLetter = incoming ->
    incoming
        .concatMap(order ->
            auditStore.append(order)
                .onErrorResume(error ->
                    deadLetterStore.append(order, error)
                )
        )
        .then();
~~~

Giả sử `deadLetterStore.append(order, error)` trả `Mono<Void>` và chỉ hoàn tất khi bản ghi lỗi đã được lưu. Khi ghi audit thất bại, pipeline chuyển sang ghi dead-letter. Nếu ghi dead-letter cũng lỗi, lỗi vẫn được truyền ra ngoài. Chính sách này tránh việc lặng lẽ bỏ dữ liệu mà không có dấu vết.

Chọn xử lý tiếp hay dừng phải dựa vào nghiệp vụ. Với thanh toán, cấp quyền hoặc sự kiện có yêu cầu thứ tự nghiêm ngặt, một phần tử lỗi có thể buộc dừng cả luồng. Không nên mặc định dùng `onErrorResume(... -> Mono.empty())` để che tất cả lỗi.

### 7.3. Vì sao onErrorResume ngoài cùng không tiếp tục phần còn lại?

~~~java
Mono<Void> hidden = incoming
    .concatMap(auditStore::append)
    .then()
    .onErrorResume(error -> Mono.empty());
~~~

Ở đây một lỗi trong upstream đã kết thúc subscription. `onErrorResume` bên ngoài thay thế lỗi bằng một completion thành công, **không tiếp tục tiêu thụ những phần tử đã bị hủy từ luồng nguồn**. Nó cũng khiến caller thấy thành công dù không chắc mọi phần tử đã được xử lý. Muốn xử lý lỗi theo từng đơn, đặt chính sách bên trong phần publisher tương ứng với từng đơn.

### 7.4. Timeout cho thao tác con

~~~java
Function<Flux<OrderEvent>, Mono<Void>> boundedWrite = incoming ->
    incoming
        .concatMap(order ->
            auditStore.append(order)
                .timeout(Duration.ofSeconds(3))
        )
        .then();
~~~

`timeout` ở trong `concatMap` áp dụng cho **từng thao tác ghi**. Nếu muốn giới hạn tổng thời gian của **cả batch**, đặt `timeout` sau `then()`:

~~~java
Mono<Void> batch = boundedWrite.apply(finiteInput)
    .timeout(Duration.ofSeconds(30));
~~~

Khi timeout, Reactor thường hủy upstream subscription, nhưng không thể suy ra giao dịch bên ngoài đã rollback; một lệnh ghi có thể đã hoàn tất tại dịch vụ đích dù subscriber không nhận được phản hồi.

## 8. Retry, phát trùng và idempotency

Nếu thêm retry ở cuối toàn pipeline:

~~~java
Mono<Void> retryAll = incoming
    .concatMap(auditStore::append)
    .then()
    .retry(2);
~~~

`retry(2)` thực hiện subscribe lại upstream khi có lỗi, tối đa hai lượt retry. Với publisher cold, những phần tử đã phát và đã ghi trước lỗi **có thể được phát và ghi lại**. Nếu đầu vào là hot hoặc đọc từ broker, khả năng replay còn phụ thuộc adapter/nguồn.

Với lệnh lưu đơn hàng, retry một thao tác không an toàn khi nó có side effect không idempotent. Có thể dùng các chiến lược:

- Mỗi event mang `eventId` duy nhất; insert với khóa duy nhất hoặc upsert theo ID.
- Ghi audit và cập nhật trạng thái trong transaction phù hợp.
- Retry có giới hạn, backoff và phân loại lỗi tạm thời.
- Checkpoint/offset chỉ cập nhật sau mốc xử lý bền vững được xác định rõ.
- Đưa bản ghi lỗi vào dead-letter hoặc quy trình đối soát khi hết retry.

Một mẫu retry *theo phần tử*, giả sử thao tác là idempotent:

~~~java
Function<Flux<OrderEvent>, Mono<Void>> retryEach = incoming ->
    incoming
        .concatMap(order ->
            auditStore.append(order)
                .retryWhen(
                    reactor.util.retry.Retry.backoff(
                        2, Duration.ofMillis(200)
                    )
                )
        )
        .then();
~~~

Điều này tránh subscribe lại **toàn bộ** input chỉ vì một lệnh ghi lỗi, nhưng vẫn có thể thử ghi cùng `order` nhiều lần. Cơ chế idempotency tại nơi lưu vẫn cần thiết.

## 9. Luồng hữu hạn và luồng liên tục: Mono<Void> hoàn tất lúc nào?

Chữ ký `Function<Flux<T>, Mono<Void>>` có thể nhận cả nguồn hữu hạn lẫn nguồn chạy liên tục, nhưng ý nghĩa **completion** thay đổi đáng kể.

### 9.1. Luồng hữu hạn: hoàn thành batch

~~~java
Flux<OrderEvent> batch = Flux.just(firstOrder, secondOrder);

Mono<Void> completed = auditOrders.apply(batch);
~~~

Khi batch phát hết phần tử, tất cả thao tác con đã hoàn tất và không có lỗi, `completed` mới phát `onComplete`. Vì vậy nó là một lựa chọn hợp lý cho thao tác **đồng bộ hóa một đợt sự kiện** hoặc một HTTP invocation hữu hạn.

### 9.2. Luồng liên tục: hoàn thành từng việc nhưng chưa kết thúc toàn luồng

~~~java
Flux<OrderEvent> continuous = eventSource.flux();

Mono<Void> lifetime = auditOrders.apply(continuous);
~~~

Nếu `eventSource.flux()` không phát `onComplete`, `lifetime` **không phát completion thành công** khi stream còn sống. Tuy nhiên, mỗi lệnh `auditStore.append(order)` vẫn có thể hoàn tất khi sự kiện đến.

**Hệ quả quan trọng:** Đừng dùng `Mono<Void>` terminal của toàn pipeline làm bằng chứng hoàn tất cho **mỗi message riêng lẻ** trong một nguồn liên tục. Completion có ý nghĩa vòng đời stream/batch, không tự cung cấp per-message acknowledgment.

### 9.3. Chia luồng dài hạn thành những phần hữu hạn

Khi cần completion theo từng cửa sổ, có thể chia cửa sổ theo số lượng rồi tạo một `Mono<Void>` cho mỗi cửa sổ:

~~~java
Function<Flux<OrderEvent>, Flux<Long>> auditInBatches = source ->
    source
        .buffer(100)
        .concatMap(batch ->
            Flux.fromIterable(batch)
                .concatMap(auditStore::append)
                .thenReturn((long) batch.size())
        );
~~~

Ở đây `buffer(100)` phát các batch đủ 100 phần tử; batch cuối chưa đủ 100 sẽ chỉ được phát khi upstream hoàn tất. `thenReturn` phát kích thước batch **sau khi tất cả lệnh ghi trong batch hoàn tất**. Đây là hàm **có kết quả**, không còn `Mono<Void>` cho toàn stream, nhằm minh họa thay đổi hợp đồng khi cần tín hiệu hoàn tất nhiều lần trong một nguồn dài hạn.

Nếu cần đẩy batch theo thời gian ngay cả khi chưa đủ phần tử, có thể cân nhắc `bufferTimeout`. Cần xét bộ nhớ, timeout, lỗi và ý nghĩa commit của từng batch.

## 10. Subscription, cancellation và nguồn tiêu thụ

### 10.1. Ai có trách nhiệm subscribe?

Mô hình thông thường:

~~~java
Mono<Void> result = auditOrders.apply(input);

// Trong unit test: StepVerifier subscribe và quan sát terminal.
StepVerifier.create(result).verifyComplete();
~~~

Trong Spring Cloud Function, `FunctionCatalog` có thể cung cấp function để adapter gọi. Với hàm trả publisher, **caller/adapter phải subscribe và quản lý subscription** để tác vụ chạy. Không cần và không nên tự gọi `subscribe()` trong chính thân function chỉ để kích hoạt dữ liệu.

Nếu caller thực sự cần chạy thủ công:

~~~java
Disposable subscription = result.subscribe(
    ignored -> {},
    error -> logger.error("Audit failed", error),
    () -> logger.info("Audit completed")
);
~~~

`Disposable` là handle để hủy subscription; handler `ignored` không nhận giá trị `Void` nào từ `Mono<Void>`. Trong ứng dụng thật, giữ handle hoặc quản lý qua lifecycle/container phù hợp; đừng subscribe rồi bỏ đi nếu luồng dài hạn.

### 10.2. Cancellation là tín hiệu riêng với completion

~~~java
Mono<Void> monitored = auditOrders.apply(input)
    .doFinally(signalType ->
        metrics.recordTermination(signalType.name())
    );
~~~

`doFinally` có thể quan sát `ON_COMPLETE`, `ON_ERROR` hoặc `CANCEL`. Khi caller hủy subscription, không có bảo đảm mọi tác vụ đang chạy đã hoàn tất. Cancel cũng không mặc nhiên rollback thao tác I/O tại dịch vụ ngoài.

### 10.3. Backpressure và giới hạn đồng thời

Dòng dữ liệu có thể phát nhanh hơn khả năng ghi. Reactor hỗ trợ backpressure thông qua `request(n)`; `concatMap` và `flatMap(concurrency)` có cách điều tiết nhu cầu riêng. Tuy nhiên:

- Backpressure trong Reactor không tự điều khiển tốc độ của một message broker hay SDK không tuân theo demand.
- Buffer lớn hoặc không giới hạn có thể làm tăng bộ nhớ.
- `flatMap(..., 8)` giới hạn thao tác con trong một pipeline, không giới hạn tổng tải của nhiều instance.
- Không nên dùng `onBackpressureDrop()` cho sự kiện cần lưu đầy đủ, trừ khi có cơ chế bù/khôi phục.
- Cần giám sát độ trễ ghi, số lỗi, hàng đợi và thời gian xử lý mỗi batch.

## 11. Dữ liệu nào được xem là “không trả về”?

`Mono<Void>` không phát payload, nhưng đôi khi nghiệp vụ thực sự cần một kết quả như mã lỗi, số lượng đã xử lý hoặc correlation ID. Khi đó **không nên ép mọi trạng thái vào completion**.

### 11.1. Không cần payload, chỉ cần thành công/thất bại

~~~java
Function<Flux<OrderEvent>, Mono<Void>> persist = events ->
    events.concatMap(auditStore::append).then();
~~~

Phù hợp khi caller cần chờ toàn batch và lỗi được thể hiện bằng `onError`.

### 11.2. Cần trả số bản ghi đã ghi

~~~java
Function<Flux<OrderEvent>, Mono<Long>> persistAndCount = events ->
    events
        .concatMap(order ->
            auditStore.append(order).thenReturn(1L)
        )
        .reduce(0L, Long::sum);
~~~

Hàm này phát `Mono<Long>` khi batch hoàn tất, bằng tổng số lệnh append đã hoàn tất thành công. Với nguồn vô hạn, phép `reduce` đợi nguồn hoàn tất. Nếu yêu cầu “đã nhận từ upstream” khác với “đã commit bền vững”, cần thiết kế cách đếm chính xác.

### 11.3. Cần phát kết quả từng phần tử

~~~java
Function<Flux<OrderEvent>, Flux<AuditResult>> persistAndReport =
    events -> events.concatMap(order ->
        auditStore.append(order)
            .thenReturn(new AuditResult(order.orderId(), true))
    );
~~~

`AuditResult` là DTO giả định. Trả `Flux<AuditResult>` giúp downstream quan sát kết quả của từng sự kiện; tuy nhiên, một lỗi chưa xử lý vẫn có thể dừng toàn stream. Chọn chữ ký theo yêu cầu đầu ra, tránh dùng `Mono<Void>` khi nghiệp vụ thật sự cần feedback chi tiết.

## 12. FunctionCatalog và composition của hàm không có dữ liệu đầu ra

Trong Spring Cloud Function, `FunctionCatalog` giúp tra cứu các bean và composition các hàm tương thích. Ví dụ tách validation khỏi lưu audit:

~~~java
@Bean
Function<Flux<OrderEvent>, Flux<OrderEvent>> validOrders() {
    return orders -> orders.filter(order -> order.amountCents() > 0);
}

@Bean
Function<Flux<OrderEvent>, Mono<Void>> auditOrders(AuditStore store) {
    return orders -> orders.concatMap(store::append).then();
}
~~~

Nếu adapter/phiên bản hỗ trợ composition tương ứng, có thể chọn:

~~~properties
spring.cloud.function.definition=validOrders|auditOrders
~~~

Hàm `validOrders` xử lý từng phần tử và phát `Flux<OrderEvent>` cho `auditOrders`, hàm cuối cùng trả `Mono<Void>`. Do kết quả cuối **không có payload**, composition này về bản chất là **terminal side-effect pipeline**.

Không nên giả định có thể ghép thêm một function nhận dữ liệu nghiệp vụ `OrderEvent` **sau** `auditOrders`: đầu ra lúc đó không còn `Flux<OrderEvent>`. Nếu cần tiếp tục biến đổi hoặc chuyển thông điệp, nên giữ pipeline trả `Flux<R>` hoặc thiết kế một kiểu kết quả cụ thể.

### 12.1. Có dùng lại qua HTTP, broker và serverless được không?

Logic Java trong `auditOrders` không biết mình đang chạy qua HTTP, message binder hay serverless. Đó là giá trị của Spring Cloud Function. Tuy nhiên, các adapter **khác nhau ở ranh giới invocation và cách xử lý publisher**:

| Môi trường | Điều cần xác định với `Mono<Void>` |
| --- | --- |
| Gọi Java/`FunctionCatalog` trực tiếp | Caller phải subscribe và quyết định chờ completion/lỗi |
| HTTP adapter | Response có thể không có body; cần biết adapter có đợi publisher hoàn tất trước khi trả status không |
| Spring Cloud Stream | Reactive function có thể nhận một `Flux` dài hạn; output `Mono<Void>` không tạo message có payload |
| Serverless adapter | Invocation có thời gian giới hạn; cần dùng nguồn hữu hạn và biết runtime chờ publisher đến khi nào |
| Batch job | `Mono<Void>` là dấu hiệu hữu ích cho hoàn tất toàn batch, nhưng không thay thế checkpoint hay transaction |

Không được mặc định rằng một function trả `Mono<Void>` sẽ khiến binder **ack từng message đúng sau thao tác ghi**. Cơ chế delivery, lỗi, retry, offset và acknowledgment thuộc adapter/binder; function reactive theo mô hình luồng có thể được gọi **một lần cho cả publisher**, không phải mỗi message.

### 12.2. Trạng thái HTTP không phản ánh mọi kiểu hoàn tất

Một web adapter có thể chuyển completion thành response không có body, nhưng status HTTP cụ thể phụ thuộc adapter và cách xử lý lỗi. Nếu function được gọi với đầu vào `Flux` vô hạn, một HTTP request yêu cầu chờ `Mono<Void>` hoàn tất có thể chờ mãi hoặc timeout. Vì vậy, với endpoint “gửi một batch rồi nhận kết quả”, nên đặt ranh giới nguồn hữu hạn và chính sách timeout rõ ràng.

### 12.3. Chuyển đổi thông điệp và metadata

Nếu sự kiện có correlation ID, routing key hoặc event ID, input có thể là `Flux<Message<OrderEvent>>`:

~~~java
Function<Flux<Message<OrderEvent>>, Mono<Void>> auditMessages =
    messages -> messages
        .concatMap(message ->
            auditStore.appendWithId(
                message.getPayload(),
                message.getHeaders().get("eventId")
            )
        )
        .then();
~~~

`appendWithId(...)` là API giả định trả `Mono<Void>`; `Message` là `org.springframework.messaging.Message`. Header `eventId` được dùng làm khóa idempotency nghiệp vụ. Nếu framework chuyển đổi payload hoặc binder thay đổi header, phải kiểm tra metadata thực tế ở từng adapter.

**Không có output `Message<?>`** với chữ ký trả `Mono<Void>`. Nếu downstream cần correlation ID của từng sự kiện để tạo response message, hãy chọn hàm có output tương ứng.

## 13. Kiểm thử với StepVerifier: chờ đúng tín hiệu

`reactor-test` cung cấp `StepVerifier` để tự subscribe vào publisher và khẳng định số tín hiệu, kết thúc hoặc lỗi. Đây là công cụ thích hợp để kiểm tra `Mono<Void>` vì không có giá trị `onNext` để so sánh.

### 13.1. Kiểm tra lazy và mọi bản ghi đều được ghi

Ví dụ hoàn chỉnh dưới đây dùng `OrderAuditConfiguration` ở mục 4:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.Test;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

class OrderAuditConfigurationTest {

    @Test
    void waitsUntilAllWritesComplete() {
        AtomicInteger writes = new AtomicInteger();
        OrderAuditConfiguration config = new OrderAuditConfiguration();

        OrderAuditConfiguration.AuditStore store = order ->
            Mono.fromRunnable(writes::incrementAndGet);

        var audit = config.auditOrders(store);

        Flux<OrderAuditConfiguration.OrderEvent> input = Flux.just(
            new OrderAuditConfiguration.OrderEvent("A", 100),
            new OrderAuditConfiguration.OrderEvent("B", 200),
            new OrderAuditConfiguration.OrderEvent("C", 300)
        );

        Mono<Void> completion = audit.apply(input);
        assertEquals(0, writes.get()); // Chưa subscribe.

        StepVerifier.create(completion)
            .verifyComplete();

        assertEquals(3, writes.get());
    }

    @Test
    void propagatesWriteFailure() {
        OrderAuditConfiguration config = new OrderAuditConfiguration();

        OrderAuditConfiguration.AuditStore store = order ->
            "B".equals(order.orderId())
                ? Mono.error(new IllegalStateException("audit failed"))
                : Mono.empty();

        var audit = config.auditOrders(store);

        StepVerifier.create(audit.apply(Flux.just(
                new OrderAuditConfiguration.OrderEvent("A", 100),
                new OrderAuditConfiguration.OrderEvent("B", 200)
            )))
            .expectErrorMessage("audit failed")
            .verify();
    }
}
~~~

Ở test đầu, nguồn cold và `Mono.fromRunnable` cho phép chứng minh side effect chưa xảy ra trước subscription. `verifyComplete()` xác nhận completion, không phải số lượng `onNext` (vì `Mono<Void>` không phát giá trị). Test thứ hai khẳng định lỗi từ repository được truyền ra caller.

### 13.2. Kiểm tra không có giá trị trả về

~~~java
Mono<Void> completion = Flux.just(1, 2, 3)
    .map(n -> n * 2)
    .then();

StepVerifier.create(completion)
    .expectComplete()
    .verify();
~~~

`expectComplete()` sẽ thất bại nếu có `onNext` không mong đợi hoặc `onError`. Nó diễn tả đúng hợp đồng “chỉ cần kết thúc”.

### 13.3. Test thời gian ảo cho thao tác bị trì hoãn

~~~java
StepVerifier.withVirtualTime(
        () -> Flux.just("A", "B")
            .concatMap(s ->
                Mono.delay(Duration.ofSeconds(1)).then()
            )
            .then()
    )
    .thenAwait(Duration.ofSeconds(2))
    .verifyComplete();
~~~

Trong ví dụ với `concatMap`, mỗi thao tác giả lập mất một giây, tổng khoảng hai giây thời gian ảo. Tạo publisher **bên trong factory** của `withVirtualTime` để Reactor dùng virtual scheduler; điều này không tự mô phỏng database/network thật hoặc timer của adapter/binder.

### 13.4. Test một batch rỗng và cancellation

Với batch rỗng:

~~~java
StepVerifier.create(audit.apply(Flux.empty()))
    .verifyComplete();
~~~

Với nguồn không kết thúc, nên **hủy subscription** trong test thay vì đợi completion vô hạn:

~~~java
StepVerifier.create(
        Flux.<OrderEvent>never()
            .concatMap(auditStore::append)
            .then()
    )
    .thenCancel()
    .verify();
~~~

`thenCancel()` chứng minh test có thể yêu cầu hủy; nó **không** chứng minh mọi tài nguyên hoặc I/O ngoại vi đã được dọn dẹp. Để kiểm tra cleanup, thêm `doFinally` hoặc test tích hợp client thực.

## 14. Các lỗi thiết kế thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Không thấy database ghi gì | Tạo `Mono<Void>` nhưng caller không subscribe | Trả publisher cho framework/caller và kiểm tra subscription |
| Hàm “thành công” ngay dù ghi chưa xong | Tự `subscribe()` tác vụ rồi trả `Mono.empty()` | Ghép publisher con bằng `concatMap`/`flatMap` và `then()` |
| `Flux<Mono<Void>>` không làm nhiệm vụ mong muốn | Dùng `map` với API trả publisher | Dùng toán tử flatten phù hợp |
| Thứ tự commit bị sai | `flatMap` chạy thao tác con đồng thời | Dùng `concatMap` khi cần tuần tự |
| Một bản ghi lỗi làm dừng toàn luồng | `onError` không được xử lý | Chọn fail-fast hoặc xử lý lỗi trong từng inner publisher |
| Mất dữ liệu nhưng completion báo OK | Bỏ lỗi bằng `onErrorResume(... -> Mono.empty())` | Chỉ che lỗi theo chính sách được chấp nhận; ghi dead-letter/metric |
| Ghi trùng sau retry | Subscribe lại publisher cold hoặc broker redelivery | Idempotency, transaction và checkpoint |
| Batch lớn ngốn tài nguyên | Concurrency/buffer quá lớn | Giới hạn đồng thời, phân trang và giám sát |
| Luồng liên tục không bao giờ `onComplete` | `then()` đợi upstream kết thúc | Tách batch/cửa sổ nếu cần completion định kỳ |
| HTTP request bị treo | Đầu vào vô hạn hoặc tác vụ không có timeout | Thiết kế invocation hữu hạn, timeout và cancellation |
| Broker ack không tương ứng lệnh ghi | Đánh đồng terminal stream với per-message delivery | Kiểm tra cơ chế ack/offset và binder thực tế |
| Test PASS nhưng production không chạy | Chỉ test Reactor, chưa có adapter subscribe/binding | Thêm integration test qua HTTP/broker/serverless runtime |

## 15. Quy trình lựa chọn chữ ký đúng với nghiệp vụ

~~~mermaid
flowchart TD
    START["Cần xử lý nhiều sự kiện T"] --> OUT{"Cần trả dữ liệu sau xử lý?"}
    OUT -->|Không| WAIT{"Cần quan sát hoàn tất hoặc lỗi?"}
    OUT -->|Có, cho mỗi phần tử| EACH["Function<Flux<T>,Flux<R>>"]
    OUT -->|Có, một kết quả tổng| RESULT["Function<Flux<T>,Mono<R>>"]
    WAIT -->|Có| VOID["Function<Flux<T>,Mono<Void>>"]
    WAIT -->|Không, consumer tự sở hữu lifecycle| CONS["Consumer<Flux<T>>"]
    VOID --> ASYNC{"Tác vụ mỗi T trả publisher?"}
    ASYNC -->|Có| FLAT["concatMap / flatMap + then"]
    ASYNC -->|Không, blocking| BLOCK["Reactive adapter hoặc boundedElastic"]
    FLAT --> VERIFY["Kiểm tra subscription, lỗi,\nretry, hủy và idempotency"]
    BLOCK --> VERIFY
    CONS --> VERIFY
    EACH --> VERIFY
    RESULT --> VERIFY
~~~

Có thể dùng checklist kỹ thuật sau trước khi đưa function lên môi trường thật:

1. **Đơn vị xử lý:** input là batch hữu hạn hay stream liên tục?
2. **I/O:** các API dùng trong `concatMap`/`flatMap` có thật sự trả publisher báo hoàn tất sau commit?
3. **Subscription:** ai subscribe `Mono<Void>` kết quả và có hủy được khi shutdown/timeout?
4. **Lỗi:** một event lỗi dừng toàn stream hay được lưu dead-letter rồi tiếp tục?
5. **Trùng dữ liệu:** retry, redelivery hoặc resubscription có thể ghi cùng event nhiều lần không?
6. **Tải:** concurrency, connection pool, số lượng phần tử và bộ nhớ có được giới hạn không?
7. **Adapter:** HTTP/broker/serverless có xử lý `Mono<Void>` theo ngữ nghĩa completion dự kiến không?
8. **Quan sát:** metric và log có ghi rõ từng lỗi, tổng số event, completion và cancellation không?

## 16. Câu hỏi tự đánh giá

1. Vì sao `Mono<Void>` vẫn là một kết quả hữu ích dù không phát payload?
2. `Function<Flux<Order>, Mono<Void>>` khác gì `Consumer<Flux<Order>>` về quyền sở hữu subscription và khả năng quan sát lỗi?
3. `then()` có bỏ qua việc xử lý từng phần tử upstream hay chỉ bỏ giá trị đầu ra?
4. Vì sao `doOnNext(order -> store.save(order))` không đảm bảo một `Mono<Void>` trả về từ `save` đã được thực thi?
5. Khi nào chọn `concatMap` thay vì `flatMap`? `flatMapSequential` có đảm bảo side effect commit theo thứ tự không?
6. `onErrorResume` đặt sau `then()` có giúp xử lý các phần tử còn lại trong cùng subscription không?
7. Vì sao `retry(2)` có thể ghi trùng dữ liệu, dù publisher trả `Mono<Void>`?
8. Với `Flux` liên tục không bao giờ `onComplete`, `Mono<Void>` toàn pipeline có hoàn tất bình thường không?
9. Vì sao subscription hoặc completion của `Mono<Void>` không tự bảo đảm message broker đã ack từng message?
10. Bạn sẽ dùng `StepVerifier` như thế nào để chứng minh thao tác chưa chạy trước subscription và đã hoàn tất sau subscription?
11. Khi nào nên thay `Mono<Void>` bằng `Mono<BatchSummary>` hoặc `Flux<AuditResult>`?
12. Tại sao integration test qua adapter vẫn cần thiết ngay cả khi unit test Reactor thành công?

## 17. Tài liệu nên tham khảo

- [Spring Cloud Function: Programming model](https://docs.spring.io/spring-cloud-function/reference/spring-cloud-function/programming-model.html) — các dạng function bean và reactive signatures.
- [Spring Cloud Stream: Producing and Consuming Messages](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/producing-and-consuming-messages.html) — reactive Consumer, binding và các ranh giới của stream processing.
- [Project Reactor: Reference Guide](https://projectreactor.io/docs/core/release/reference/) — `Mono`, `Flux`, toán tử và backpressure.
- [Project Reactor: Testing](https://projectreactor.io/docs/test/release/reference/) — `StepVerifier` và thời gian ảo.

Cần đối chiếu phiên bản Spring Cloud Function, Spring Cloud Stream và binder đang triển khai. Các cách adapter theo dõi publisher, xác nhận message hoặc chuyển lỗi thành phản hồi không nhất thiết đồng nhất giữa các phiên bản và môi trường.

**Ghi nhớ:** `Function<Flux<T>, Mono<Void>>` là một hợp đồng **xử lý bất đồng bộ không trả dữ liệu nghiệp vụ nhưng vẫn trả tín hiệu hoàn tất/lỗi**. Ghép các tác vụ con bằng `concatMap` hoặc `flatMap`, kết thúc bằng `then()` và trả publisher để caller/adapter quản lý subscription. Đối với batch hữu hạn, completion có thể đại diện cho toàn bộ công việc đã xong theo hợp đồng publisher; với stream liên tục, completion không phải xác nhận từng message. Tính bền vững, retry, idempotency và acknowledgment vẫn phải được thiết kế ở ranh giới hệ thống thực tế.
