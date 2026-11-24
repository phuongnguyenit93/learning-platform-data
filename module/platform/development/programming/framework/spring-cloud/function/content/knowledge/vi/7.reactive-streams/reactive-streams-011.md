# Xử lý lỗi theo phần tử và lỗi kết thúc cả luồng

## 1. Bài toán: một đơn hàng hỏng có nên dừng tất cả đơn còn lại?

Giả sử hệ thống xử lý lần lượt ba sự kiện **A, B, C**. A hợp lệ, B chứa thông tin thiếu hoặc một dịch vụ bên ngoài bị lỗi, C vẫn hợp lệ. Kết quả mong muốn phụ thuộc quy tắc nghiệp vụ:

- **Dừng cả luồng:** nếu xử lý B không an toàn, phải dừng để không làm sai trạng thái của C.
- **Đánh dấu B thất bại rồi tiếp tục:** nếu các sự kiện độc lập và có cơ chế ghi nhận lỗi đáng tin cậy, vẫn có thể xử lý C.
- **Thử lại B rồi quyết định:** nếu lỗi do mạng hoặc hệ thống tạm thời, retry có giới hạn trước khi dừng hoặc chuyển B vào dead-letter.
- **Trả kết quả nghiệp vụ cho B:** nếu B chỉ bị từ chối theo quy tắc hợp lệ, nên biểu diễn bằng một trạng thái dữ liệu, không nhất thiết phát `onError`.

Trong **Spring Cloud Function**, logic có thể đóng gói thành `Supplier`, `Function` và `Consumer`, tra cứu bằng `FunctionCatalog`, ghép bằng composition và triển khai cùng một hàm qua HTTP, message/event binder hoặc môi trường serverless. Với chữ ký `Function<Flux<T>, Flux<R>>`, một quyết định đặt toán tử xử lý lỗi **bên trong hay bên ngoài publisher con** có thể quyết định việc C có còn được xử lý không.

Bài này thuộc chương **Luồng phản ứng** và tập trung vào sự khác biệt quan trọng:

> **Lỗi của một phần tử trong logic nghiệp vụ không nhất thiết phải là tín hiệu `onError` kết thúc toàn subscription.** Khi một `Flux` thực sự phát `onError`, subscription đó kết thúc. Muốn tiếp tục, phải thiết kế phạm vi phục hồi trước khi lỗi lan thành terminal signal của toàn pipeline.

### Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt **kết quả nghiệp vụ thất bại** với **tín hiệu `onError`** của Reactive Streams.
2. Giải thích tại sao `onErrorResume` đặt sau toàn bộ `Flux` không tiếp tục các phần tử còn lại của nguồn đã lỗi.
3. Sử dụng `concatMap`/`flatMap` và `Mono` con để cô lập lỗi theo từng phần tử.
4. Chọn `onErrorReturn`, `onErrorResume`, `onErrorMap`, `onErrorComplete`, `retryWhen` và các biến thể `delayError` phù hợp.
5. Nhận diện rủi ro khi dùng `onErrorContinue`, fallback im lặng và retry toàn bộ luồng.
6. Tổ chức dead-letter, idempotency, timeout, acknowledgment và quan sát lỗi theo đúng đơn vị công việc.
7. Kiểm thử chính sách fail-fast, tiếp tục sau lỗi và retry bằng `StepVerifier`.

## 2. Reactive Streams: onError là terminal signal

Trong Reactive Streams, một publisher có thể phát:

~~~text
onSubscribe
  └── onNext(T) × 0..N
        └── onComplete
        hoặc
        └── onError(Throwable)
~~~

`onComplete` và `onError` là **hai tín hiệu kết thúc loại trừ nhau** đối với cùng một subscription. Một nguồn đã phát `onError` sẽ không tiếp tục phát thêm `onNext` xuống cùng subscriber như thể chưa có chuyện gì xảy ra.

Ví dụ:

~~~java
Flux<String> source = Flux.concat(
    Flux.just("A"),
    Flux.error(new IllegalStateException("Cannot read B")),
    Flux.just("C")
);
~~~

Subscriber nhận A rồi `onError`; phần `Flux.just("C")` không được đi qua trong cùng subscription vì `concat` gặp lỗi tại phần trước.

~~~mermaid
flowchart LR
    A["onNext(A)"] --> B["onError(B)"]
    B --> STOP["Subscription kết thúc"]
    STOP -.-> C["C không được phát"]
~~~

### 2.1. Lỗi kết thúc khác với hủy đăng ký

- `onComplete`: publisher kết thúc bình thường.
- `onError`: publisher kết thúc với lỗi.
- `cancel()`: subscriber không còn muốn nhận thêm và yêu cầu dừng upstream; **không phải** một `onError` hay `onComplete` tự phát xuống downstream.

Lỗi có thể khiến framework hoặc downstream hủy các publisher con đang chạy, nhưng không nên đồng nhất *hủy* với *thất bại nghiệp vụ*. Với hệ thống có I/O ngoài, một tác vụ bị hủy vẫn có thể đã gửi request hoặc commit trước đó.

### 2.2. Lỗi xảy ra ở đâu?

| Vị trí | Ví dụ | Hậu quả nếu không xử lý |
| --- | --- | --- |
| Tạo nguồn | `Flux.error(exception)` | Luồng phát `onError` |
| Mapper đồng bộ | `map(order -> validateOrThrow(order))` | Exception được chuyển thành `onError` |
| Publisher con | `flatMap(order -> client.call(order))` | Một inner error có thể làm toàn `Flux` lỗi |
| Chuyển đổi payload | Converter không đọc được dữ liệu | Tùy adapter: lỗi xảy ra trước hoặc trong function |
| Binder/broker | Gửi message/ack thất bại | Có thể nằm ngoài phạm vi toán tử Reactor đang viết |
| Cleanup | Đóng connection/commit lỗi | Có thể làm thay đổi tín hiệu terminal quan sát được |

**Một lỗi Java trong function không nhất thiết có cùng cơ chế retry hoặc acknowledgment với lỗi transport**. Khi đưa function qua HTTP, Spring Cloud Stream hay serverless, cần phân biệt lỗi của Reactor pipeline và lỗi do adapter phát hiện.

## 3. Ví dụ dễ nhầm nhất: onErrorResume ngoài toàn luồng

Giả sử đầu vào có ba số, và số 2 gây lỗi:

~~~java
Flux<Integer> source = Flux.just(1, 2, 3)
    .map(n -> {
        if (n == 2) {
            throw new IllegalArgumentException("bad item: 2");
        }
        return n * 10;
    });
~~~

Nếu chỉ subscribe, downstream nhận `10` rồi `onError("bad item: 2")`; `30` không xuất hiện.

Có người thêm:

~~~java
Flux<Integer> recovered = source
    .onErrorResume(error -> Flux.just(-1));
~~~

Kết quả là:

~~~text
10, -1, onComplete
~~~

**Không phải**:

~~~text
10, -1, 30, onComplete
~~~

Vì `onErrorResume` ở đây **thay thế toàn bộ upstream đã kết thúc bằng một publisher fallback**. Nó không “quay lại trong `map` để bỏ số 2 và tiếp tục số 3”.

### 3.1. Sơ đồ phạm vi phục hồi

~~~mermaid
flowchart TD
    S["Flux: 1, 2, 3"] --> MAP["map: 1→10; 2→exception"]
    MAP --> ERROR["onError"]
    ERROR --> RESUME["onErrorResume bên ngoài"]
    RESUME --> FALLBACK["Flux.just(-1)"]
    FALLBACK --> DONE["onComplete"]
    MAP -.-> LOST["Phần tử 3 không còn được xử lý"]
~~~

**Quy tắc:** để lỗi của B không giết cả nguồn A–B–C, phải tạo một **ranh giới publisher con dành riêng cho B** và phục hồi lỗi *bên trong* ranh giới đó.

### 3.2. Một fallback không đồng nghĩa thành công

`-1` ở ví dụ trên là giá trị kỹ thuật đơn giản, nhưng trong nghiệp vụ cần một kết quả có ý nghĩa: `REJECTED` (bị từ chối hợp lệ), `UNAVAILABLE` (không kiểm tra được), `FAILED` (đã ghi nhận lỗi), hoặc một bản ghi dead-letter.

Không nên trả `true`, `APPROVED` hoặc `Mono.empty()` cho mọi lỗi chỉ để pipeline tiếp tục chạy. Làm vậy có thể che giấu dữ liệu chưa được xử lý.

## 4. Cô lập lỗi theo phần tử bằng concatMap và Mono con

Thay vì ném lỗi ở một `map` chung, xây một publisher độc lập cho mỗi phần tử:

~~~java
Flux<Integer> safe = Flux.just(1, 2, 3)
    .concatMap(n ->
        Mono.fromCallable(() -> {
            if (n == 2) {
                throw new IllegalArgumentException("bad item: 2");
            }
            return n * 10;
        })
        .onErrorResume(error -> Mono.just(-1))
    );
~~~

Khi subscribe, output là:

~~~text
10, -1, 30, onComplete
~~~

Giải thích:

1. `concatMap` nhận phần tử 1 và subscribe vào `Mono` xử lý số 1; kết quả là 10.
2. Với số 2, `Mono.fromCallable` phát `onError`.
3. `onErrorResume` **bên trong** publisher của số 2 thay lỗi bằng `Mono.just(-1)`.
4. Publisher con của số 2 hoàn tất bình thường; `concatMap` tiếp tục số 3.
5. Nguồn tổng thể không nhận `onError` chưa xử lý, nên có thể phát 30 rồi hoàn tất.

### 4.1. Vì sao phải dùng publisher con?

`Mono.fromCallable` biến exception ném trong `Callable` thành tín hiệu `onError` **của chính Mono đó** khi subscribe. Nhờ vậy `onErrorResume` chỉ xử lý thất bại của một phần tử.

~~~java
Function<Integer, Mono<Integer>> perItem = n ->
    Mono.fromCallable(() -> validateAndConvert(n))
        .onErrorResume(error -> Mono.just(-1));

Flux<Integer> all = Flux.just(1, 2, 3)
    .concatMap(perItem);
~~~

`validateAndConvert` là phương thức nghiệp vụ đồng bộ giả định. Khi hàm trả publisher con bất đồng bộ, mẫu tương tự:

~~~java
Flux<Decision> decisions = events.concatMap(event ->
    riskClient.check(event)
        .onErrorResume(error ->
            Mono.just(Decision.unavailable(event.eventId()))
        )
);
~~~

`riskClient.check(event)` trả `Mono<Decision>`; `Decision.unavailable` là factory method minh họa. Quan trọng là vị trí `onErrorResume`: nằm trong lambda cho **mỗi event**.

### 4.2. concatMap hay flatMap?

| Toán tử | Cách xử lý | Giữ thứ tự kết quả | Có thể chạy nhiều tác vụ cùng lúc |
| --- | --- | --- | --- |
| `concatMap` | Subscribe từng publisher con lần lượt | Có, theo thứ tự nguồn | Không chạy nhiều inner đồng thời |
| `flatMap` | Subscribe nhiều publisher con, trộn kết quả | Không bảo đảm | Có |
| `flatMapSequential` | Subscribe nhiều publisher con, phát theo thứ tự nguồn | Có ở đầu ra | Có |

Nếu các event độc lập và ưu tiên throughput:

~~~java
Flux<Decision> decisions = events.flatMap(event ->
    riskClient.check(event)
        .onErrorResume(error ->
            Mono.just(Decision.unavailable(event.eventId()))
        ),
    8
);
~~~

Số `8` giới hạn inner publishers đồng thời trong **một subscription** của toán tử. Lỗi được phục hồi ở từng inner publisher, nhưng **thứ tự kết quả có thể đổi**. Với cập nhật cùng một aggregate cần tuần tự nghiêm ngặt, `concatMap` dễ suy luận hơn.

### 4.3. Sai phạm vi dù đã dùng flatMap

~~~java
// Cả Flux có thể dừng khi bất kỳ inner nào lỗi.
Flux<Decision> wrong = events
    .flatMap(riskClient::check, 8)
    .onErrorResume(error ->
        Flux.just(Decision.unavailable("unknown"))
    );
~~~

Một publisher con B phát lỗi khiến `flatMap` thông báo lỗi xuống downstream, hủy các tác vụ khác theo chính sách mặc định và chuyển sang fallback chung. Đây **không phải** mẫu cô lập lỗi từng event.

## 5. Phân biệt “không hợp lệ” với “hạ tầng thất bại”

Không phải mọi tình huống thất bại đều phải được thể hiện bằng exception. Ví dụ:

- Đơn có số tiền âm: **quy tắc validation từ chối**; có thể trả kết quả `REJECTED`.
- Dịch vụ kiểm tra bị timeout: **hạ tầng chưa đưa ra quyết định**; có thể retry rồi đánh dấu `UNAVAILABLE`.
- Database không ghi được: **chưa bảo đảm kết quả đã được lưu**; có thể dừng stream hoặc ghi dead-letter bền vững.
- Payload bị lỗi định dạng tại HTTP/binder: có thể bị adapter từ chối **trước khi** function nhận được event.

Một kiểu dữ liệu kết quả tường minh:

~~~java
public enum ProcessingStatus {
    APPROVED,
    REJECTED,
    UNAVAILABLE
}

public record ProcessingResult(
    String eventId,
    ProcessingStatus status,
    String reasonCode
) {}
~~~

`REJECTED` có thể là kết luận nghiệp vụ hoàn toàn bình thường: publisher phát `onNext(ProcessingResult)` rồi tiếp tục. `UNAVAILABLE` diễn đạt một lỗi hạ tầng đã được kiểm soát; không nên đánh đồng nó với `APPROVED`.

### 5.1. Vì sao kết quả nghiệp vụ tường minh hữu ích?

| Hợp đồng | Người nhận hiểu gì? | Hậu quả |
| --- | --- | --- |
| `onNext(APPROVED)` | Đã có kết luận chấp thuận | Tiếp tục quy trình |
| `onNext(REJECTED)` | Đã có kết luận từ chối | Ghi nhận lý do |
| `onNext(UNAVAILABLE)` | Chưa thể đưa ra kết luận | Đối soát, retry sau hoặc dead-letter |
| `onError(IllegalStateException)` | Publisher không thể tiếp tục bình thường | Tùy caller/adapter xử lý lỗi terminal |
| `onComplete` | Subscription kết thúc bình thường | Không tự chứng minh mọi tác dụng phụ đã commit ngoài hệ thống |

Nếu cần downstream nhận **một kết quả cho mỗi event**, hãy chọn `Function<Flux<Event>, Flux<Result>>` thay vì dùng `Mono.empty()` để làm mất thông tin thất bại.

## 6. Ví dụ Spring Cloud Function hoàn chỉnh: phục hồi theo đơn hàng

Một ứng dụng kiểm tra đơn hàng cần ba yêu cầu:

1. Mỗi event hợp lệ được kiểm tra bằng một API reactive.
2. Nếu kiểm tra lỗi, bản ghi thất bại phải được lưu vào nơi xử lý lại trước khi phát kết quả `UNAVAILABLE`.
3. Nếu **việc ghi bản ghi thất bại cũng lỗi**, không được tự nhận rằng đã xử lý xong: hãy để lỗi lan ra pipeline để vận hành can thiệp.

Cấu hình sau dùng Java 17+ và Reactor. Các interface là hợp đồng ví dụ của ứng dụng, không phải API dựng sẵn từ Spring Cloud Function.

~~~java
package demo.reactive.errors;

import java.util.function.Function;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Configuration
public class OrderErrorFunctions {

    public record OrderEvent(
        String eventId,
        String orderId,
        long amountCents
    ) {}

    public enum DecisionStatus {
        APPROVED, REJECTED, UNAVAILABLE
    }

    public record ProcessingResult(
        String eventId,
        DecisionStatus status,
        String reasonCode
    ) {}

    public interface RiskService {
        Mono<DecisionStatus> evaluate(OrderEvent event);
    }

    public interface FailedEventStore {
        // Mono hoàn tất sau khi lỗi đã được lưu bền vững
        // theo hợp đồng triển khai thực tế.
        Mono<Void> save(OrderEvent event, Throwable cause);
    }

    @Bean
    public Function<Flux<OrderEvent>, Flux<ProcessingResult>> processOrders(
            RiskService riskService,
            FailedEventStore failedEventStore) {

        return incoming -> incoming.concatMap(event ->
            riskService.evaluate(event)
                .map(status -> new ProcessingResult(
                    event.eventId(),
                    status,
                    status == DecisionStatus.REJECTED
                        ? "BUSINESS_REJECTED"
                        : "CHECKED"
                ))
                .onErrorResume(error ->
                    failedEventStore.save(event, error)
                        .thenReturn(new ProcessingResult(
                            event.eventId(),
                            DecisionStatus.UNAVAILABLE,
                            "RISK_SERVICE_FAILED"
                        ))
                )
        );
    }
}
~~~

### 6.1. Tại sao lỗi của FailedEventStore vẫn được truyền ra ngoài?

`failedEventStore.save(event, error).thenReturn(result)` chỉ phát `result` **sau khi publisher lưu thất bại hoàn tất thành công**. Nếu nơi ghi dead-letter/audit trả `onError`, publisher con cũng lỗi; `concatMap` mặc định truyền lỗi đó ra toàn pipeline.

Nói cách khác, mẫu này cố tình có **hai mức chính sách**:

- Lỗi từ `RiskService`: được phục hồi theo phần tử nếu lưu trạng thái thất bại thành công.
- Lỗi từ `FailedEventStore`: là sự cố nghiêm trọng, có thể dừng toàn luồng để không báo thành công giả.

**Ranh giới độ bền:** bình luận trong interface yêu cầu `save` hoàn tất sau khi ghi bền vững; nhưng tính bền vững thực sự còn phụ thuộc cách triển khai database/queue, transaction và acknowledgment. `thenReturn` không tự nâng một API “fire-and-forget” thành commit bền vững.

### 6.2. Luồng xử lý

~~~mermaid
flowchart TD
    EVENT["onNext(OrderEvent)"] --> CHECK["RiskService.evaluate(event)"]
    CHECK --> OK{"Tín hiệu từ RiskService?"}
    OK -->|onNext DecisionStatus| RESULT["ProcessingResult thành công / từ chối"]
    OK -->|onError| STORE["FailedEventStore.save"]
    STORE --> STORED{"Ghi lỗi hoàn tất?"}
    STORED -->|Có| UNAVAILABLE["ProcessingResult UNAVAILABLE"]
    STORED -->|Lỗi| ABORT["onError kết thúc luồng"]
    RESULT --> NEXT["concatMap: event tiếp theo"]
    UNAVAILABLE --> NEXT
~~~

### 6.3. Nếu dùng flatMap để tăng throughput

Có thể thay `concatMap` bằng `flatMap(..., 8)` khi các event độc lập:

~~~java
return incoming -> incoming.flatMap(event ->
    riskService.evaluate(event)
        .map(status -> new ProcessingResult(
            event.eventId(), status, "CHECKED"
        ))
        .onErrorResume(error ->
            failedEventStore.save(event, error)
                .thenReturn(new ProcessingResult(
                    event.eventId(),
                    DecisionStatus.UNAVAILABLE,
                    "RISK_SERVICE_FAILED"
                ))
        ),
    8
);
~~~

Khi một event thất bại ở `FailedEventStore`, lỗi terminal có thể hủy các publisher con khác đã được subscribe. Một số tác vụ ngoài có thể đã hoàn tất trước cancellation, nên vẫn cần idempotency và ghi nhận trạng thái.

### 6.4. Nếu validation là lỗi nghiệp vụ có thể dự đoán

Thay vì ném exception để xử lý một số tiền âm, có thể trả kết quả:

~~~java
Mono<ProcessingResult> validate(OrderEvent event) {
    if (event.amountCents() <= 0) {
        return Mono.just(new ProcessingResult(
            event.eventId(),
            DecisionStatus.REJECTED,
            "INVALID_AMOUNT"
        ));
    }
    return Mono.empty(); // Chưa có kết quả; xử lý bước tiếp.
}
~~~

Đây là ví dụ một bước validation riêng. Khi lắp vào pipeline, cần xác định rõ `Mono.empty()` nghĩa “đi tiếp” hay “không có kết quả”; không nên thay cả luồng bằng `empty` rồi vô tình bỏ phần tử. Một mô hình tốt hơn thường là `validateAndEvaluate(event)` trả **đúng một `ProcessingResult`** cho mỗi event theo hợp đồng.

## 7. Các toán tử xử lý lỗi phổ biến và phạm vi tác dụng

| Toán tử | Cơ chế | Điều phải chú ý |
| --- | --- | --- |
| `doOnError(callback)` | Quan sát lỗi rồi cho lỗi tiếp tục truyền | **Không** phải phục hồi |
| `onErrorReturn(value)` | Thay lỗi terminal bằng một giá trị cố định | Không tiếp tục upstream cũ |
| `onErrorResume(fn)` | Chuyển sang publisher fallback | Phạm vi đặt toán tử quyết định phạm vi lỗi |
| `onErrorMap(fn)` | Chuyển exception này thành exception khác | Không làm luồng tiếp tục |
| `onErrorComplete()` | Chuyển lỗi thành completion | Có thể che lỗi và mất dữ liệu |
| `retry(n)` | Subscribe lại khi lỗi | Có thể lặp tác dụng phụ |
| `retryWhen(Retry)` | Retry theo bộ quy tắc có điều kiện/backoff | Cần giới hạn, phân loại lỗi và idempotency |
| `onErrorContinue(...)` | Hỗ trợ bỏ qua phần tử gây lỗi ở một số operator | **Không phải** chiến lược mặc định an toàn |
| `concatMapDelayError` / `flatMapDelayError` | Trì hoãn phát lỗi để xử lý thêm publisher con | Vẫn phát terminal error, không tự biến lỗi thành thành công |

### 7.1. doOnError chỉ dùng để quan sát

~~~java
Flux<ProcessingResult> traced = results
    .doOnError(error ->
        logger.error("Processing stream failed", error)
    );
~~~

Lỗi vẫn truyền xuống subscriber. Nếu muốn phục hồi, phải có thêm toán tử khác có chức năng phục hồi.

### 7.2. onErrorReturn dễ che nguyên nhân

~~~java
Flux<Integer> mapped = Flux.just(1, 2, 3)
    .map(n -> {
        if (n == 2) throw new IllegalStateException("failed");
        return n * 10;
    })
    .onErrorReturn(-1);
~~~

Kết quả là 10, -1, completion. Không có 30, và giá trị -1 không cho biết event nào thất bại nếu không mang metadata. Với luồng nghiệp vụ, một DTO kết quả có `eventId` và `reasonCode` thường phù hợp hơn.

### 7.3. onErrorMap giữ lỗi là lỗi

~~~java
Mono<Decision> normalized = riskClient.check(event)
    .onErrorMap(java.io.IOException.class,
        cause -> new RiskServiceUnavailableException(cause)
    );
~~~

`RiskServiceUnavailableException` là exception ứng dụng cần định nghĩa, có constructor nhận cause. Đoạn này chuyển lỗi I/O sang loại domain/infrastructure rõ hơn, nhưng publisher vẫn kết thúc bằng `onError` nếu không có bước phục hồi sau đó.

Điều này hữu ích khi caller phân loại lỗi để retry, thống kê hoặc chuyển thành HTTP status; không nên dùng `onErrorMap` để biến một validation bình thường thành ngoại lệ nghiêm trọng không cần thiết.

### 7.4. onErrorComplete là quyết định bỏ lỗi, không phải sửa lỗi

~~~java
Flux<String> hidden = failingSource.onErrorComplete();
~~~

Khi có lỗi, output có thể kết thúc bình thường. Nếu lỗi xảy ra sau một phần các event, consumer có thể hiểu nhầm đã xử lý hết batch. Chỉ dùng khi hành vi **bỏ qua thất bại** được chấp nhận rõ ràng, đã có metrics/alert và không làm mất nghĩa vụ xử lý.

## 8. Vì sao onErrorContinue thường không nên là lựa chọn đầu tiên?

`onErrorContinue` có thể khiến một số operator hỗ trợ cơ chế *drop phần tử lỗi và tiếp tục*. Điều này trông giống giải pháp đơn giản:

~~~java
Flux<Integer> result = Flux.just(1, 2, 3)
    .map(n -> {
        if (n == 2) throw new IllegalArgumentException("bad 2");
        return n * 10;
    })
    .onErrorContinue((error, value) ->
        logger.warn("Skipping {}: {}", value, error.toString())
    );
~~~

Với operator `map` hỗ trợ hành vi này, người học có thể quan sát output 10, 30. Nhưng **không được coi đây là hợp đồng chung cho mọi pipeline hoặc mọi lỗi**.

Các điểm nguy hiểm:

1. `onErrorContinue` chỉ có tác dụng với các operator hỗ trợ, không phải mọi publisher đều xử lý lỗi theo cách này.
2. Chính sách có thể ảnh hưởng **ngược upstream** tới operator không do bạn sở hữu; khó suy luận khi ghép nhiều function/thư viện.
3. Một số lỗi từ publisher con bất đồng bộ không thể an toàn “bỏ phần tử rồi tiếp tục”.
4. Khi phần tử chứa resource, việc discard/cleanup phải được xem xét riêng.
5. Lỗi bị bỏ qua có thể làm thiếu sự kiện quan trọng mà downstream không biết.
6. Khi refactor pipeline, thêm `flatMap`/retry/toán tử khác có thể khiến hành vi khó dự đoán.

**Ưu tiên:** tách công việc từng phần tử thành `Mono`/`Flux` con, đặt `onErrorResume` trong lambda của `concatMap` hoặc `flatMap` và trả kết quả thất bại tường minh.

### 8.1. onErrorStop dùng khi nào?

Reactor có `onErrorStop` để đưa một đoạn pipeline về ngữ nghĩa lỗi bình thường trong bối cảnh downstream có chế độ `onErrorContinue`. Đây là công cụ nâng cao để hạn chế tác động ngược lên một đoạn operator, không phải cơ chế phục hồi lỗi chính.

Nếu bạn chưa thực sự cần `onErrorContinue`, không cần thêm `onErrorStop`. Thiết kế có các publisher con và chính sách lỗi tại từng ranh giới thường dễ kiểm thử hơn.

### 8.2. Khi nào bỏ phần tử là hợp lý?

Với dữ liệu telemetry hoặc mẫu đo tạm thời, có thể chấp nhận bỏ một phần tử lỗi nếu:

- Có quy tắc xác định rõ loại lỗi được bỏ.
- Có metric số phần tử bị bỏ và lý do.
- Không làm mất nghĩa vụ nghiệp vụ.
- Có dữ liệu để đối soát hoặc tái tạo khi cần.
- Đã kiểm chứng hành vi của operator và phiên bản Reactor thực tế.

Với đơn hàng, thanh toán, hóa đơn hoặc sự kiện có tính pháp lý, mặc định phải lưu lại bản ghi thất bại hoặc dừng một cách có kiểm soát thay vì im lặng bỏ dữ liệu.

## 9. Retry từng phần tử khác retry cả nguồn

`retry` và `retryWhen` không “chạy lại dòng code từ chỗ ném exception”. Chúng thường **subscribe lại publisher ở phía upstream của toán tử retry**. Vị trí đặt retry vì thế rất quan trọng.

### 9.1. Retry bên ngoài: có thể xử lý lại cả A

~~~java
Flux<Decision> retriedAll = events
    .concatMap(riskClient::check)
    .retry(2);
~~~

Nếu A đã thành công, B lỗi, publisher tổng thể phát `onError`. `retry(2)` ở ngoài có thể subscribe lại **events**, nên A có thể được kiểm tra lại trước khi tới B.

Với nguồn cold như `Flux.just(A, B, C)`, việc phát lại đầu vào thường xảy ra. Với nguồn hot hoặc broker, chính sách replay, offset và acknowledgment phụ thuộc adapter/nguồn.

### 9.2. Retry trong từng publisher con

~~~java
Flux<Decision> retryEach = events.concatMap(event ->
    riskClient.check(event)
        .retryWhen(
            reactor.util.retry.Retry.backoff(
                2,
                Duration.ofMillis(200)
            )
        )
);
~~~

Ở đây retry dành cho **lệnh kiểm tra của event hiện tại**, thay vì subscribe lại toàn bộ `events` chỉ vì B lỗi.

Tuy nhiên, retry B vẫn có thể gọi `riskClient.check(B)` nhiều lần. Nếu một lời gọi đã thực hiện side effect ở hệ thống ngoài nhưng phản hồi bị mất, có nguy cơ trùng.

### 9.3. Retry lỗi tạm thời, không retry lỗi nghiệp vụ

Một chính sách tốt nên phân loại:

~~~java
Retry retryTransient = Retry.backoff(
        3,
        Duration.ofMillis(200)
    )
    .filter(error ->
        error instanceof TransientRiskServiceException
    );
~~~

`TransientRiskServiceException` là loại exception ứng dụng giả định. Hãy xem xét retry khi timeout/network lỗi tạm thời; không retry vô nghĩa cho `INVALID_AMOUNT` hoặc dữ liệu thiếu trường bắt buộc.

Dù dùng retry có giới hạn, vẫn cần timeout và giới hạn concurrency để tránh “retry storm” khi nhiều event cùng lỗi. Với giao dịch quan trọng, cần idempotency key xuyên suốt các lần thử.

### 9.4. Kết hợp retry rồi fallback per-item

~~~java
Flux<Decision> processed = events.concatMap(event ->
    riskClient.check(event)
        .retryWhen(retryTransient)
        .onErrorResume(error ->
            persistFailure(event, error)
                .thenReturn(Decision.unavailable(event.eventId()))
        )
);
~~~

Trong mẫu này, `persistFailure` trả `Mono<Void>` và `Decision.unavailable` là factory method do ứng dụng cung cấp.

- Lỗi tạm thời được thử lại có giới hạn.
- Lỗi còn lại được lưu trước khi phát kết quả thất bại.
- Nếu `persistFailure` lỗi, pipeline không tự thông báo thành công.
- `concatMap` có thể chuyển sang event sau khi publisher hiện tại hoàn tất.

## 10. Trì hoãn lỗi với concatMapDelayError và flatMapDelayError

Có những bài toán cần **xử lý càng nhiều công việc càng tốt trước khi báo lỗi cuối luồng**. Reactor có các biến thể *delay-error* cho một số toán tử flatten.

Ví dụ:

~~~java
Flux<Integer> delayed = Flux.just(1, 2, 3)
    .concatMapDelayError(n ->
        n == 2
            ? Mono.error(new IllegalStateException("bad 2"))
            : Mono.just(n * 10)
    );
~~~

Với nguồn hữu hạn và các inner publisher như trên, downstream có thể nhận `10`, `30` rồi **nhận lỗi terminal**. Lỗi không bị bỏ; nó chỉ được báo **sau** khi các phần xử lý được phép tiếp tục kết thúc.

### 10.1. Delay-error không phải per-item recovery

| Mục đích | Cách triển khai nên cân nhắc |
| --- | --- |
| B lỗi, muốn phát `Result(B, FAILED)` và xử lý C | `onErrorResume` **trong** publisher con |
| B lỗi, muốn vẫn xử lý C nhưng cuối batch trả lỗi tổng | `concatMapDelayError` hoặc thiết kế tổng hợp lỗi |
| B lỗi, phải dừng ngay để tránh sai trạng thái | `concatMap`/`flatMap` mặc định, để lỗi lan |
| Muốn xử lý A–B–C đồng thời, trì hoãn lỗi | `flatMapDelayError` với concurrency/prefetch được cấu hình |
| Muốn bỏ lỗi hoàn toàn | Chỉ khi chính sách nghiệp vụ cho phép, có audit/metric |

### 10.2. Chi phí của delay-error

- Các lỗi cần được giữ/tổng hợp để báo sau, có chi phí bộ nhớ và quan sát.
- Một nguồn vô hạn có thể không bao giờ đi tới mốc phát lỗi bị trì hoãn.
- Với `flatMapDelayError`, các kết quả vẫn có thể khác thứ tự nguồn.
- Nếu các thao tác trước đã commit dữ liệu, lỗi tổng ở cuối không tự rollback chúng.
- Error cuối cùng có thể chứa thông tin nhiều nguyên nhân; downstream phải ghi nhận đầy đủ, không chỉ lấy một message ngắn rồi bỏ các nguyên nhân khác.

**Đừng dùng delay-error như cách “bảo đảm tất cả event được xử lý thành công”.** Nó là lựa chọn về **thời điểm thông báo lỗi**, không phải cơ chế khôi phục.

## 11. Timeout và cancellation: lỗi nào là của phần tử, lỗi nào của luồng?

Một request tới dịch vụ ngoài có thể bị treo. Có hai vị trí đặt `timeout` với ý nghĩa khác nhau.

### 11.1. Timeout cho từng event

~~~java
Flux<Decision> decisions = events.concatMap(event ->
    riskClient.check(event)
        .timeout(Duration.ofSeconds(2))
        .onErrorResume(java.util.concurrent.TimeoutException.class,
            error -> Mono.just(
                Decision.unavailable(event.eventId())
            )
        )
);
~~~

Nếu lời gọi cho B quá hai giây, publisher con của B nhận timeout và được thay bằng kết quả `UNAVAILABLE`. `concatMap` vẫn có thể tiếp tục C.

Nếu hệ thống phải lưu sự kiện thất bại, đừng chỉ trả fallback mà quên ghi vào durable store. Hãy ghép publisher ghi lỗi trước khi trả kết quả.

### 11.2. Timeout cho toàn batch

~~~java
Mono<java.util.List<Decision>> batch = events
    .concatMap(riskClient::check)
    .collectList()
    .timeout(Duration.ofSeconds(30));
~~~

`timeout` ngoài cùng áp dụng cho việc **nhận một kết quả list cuối cùng** của batch, không phải tự đặt hai giây cho từng `riskClient.check`. Nếu batch chưa hoàn tất trong 30 giây, downstream có thể nhận lỗi timeout và upstream bị hủy.

**Cảnh báo:** cancellation không bảo đảm các request I/O bên ngoài đã rollback; nhiều lệnh đã bắt đầu có thể vẫn tiếp tục ở dịch vụ đích. Bởi vậy, với dữ liệu có side effect, cần client timeout, idempotency, kiểm soát transaction và đối soát.

### 11.3. Quan sát doFinally theo đúng ranh giới

~~~java
Mono<Decision> checked = riskClient.check(event)
    .doFinally(signal -> metrics.recordInner(signal.name()))
    .timeout(Duration.ofSeconds(2))
    .doFinally(signal -> metrics.recordOuter(signal.name()));
~~~

Tùy vị trí, hook ở inner publisher có thể thấy `CANCEL` do timeout, trong khi hook downstream có thể thấy `ON_ERROR`. Cả hai quan sát phản ánh các ranh giới khác nhau và không mâu thuẫn.

`doFinally` thích hợp đo terminal signals; **không** biến lỗi thành fallback và không thay thế `usingWhen` khi cần cleanup bất đồng bộ.

## 12. Vấn đề trong stream dài hạn: một onError có thể dừng tiêu thụ

Giả sử một reactive function nhận `Flux<OrderEvent>` sống dài hạn từ adapter sự kiện:

~~~java
@Bean
Function<Flux<OrderEvent>, Flux<Decision>> assess(
        RiskService riskService) {

    return incoming -> incoming.flatMap(
        riskService::check,
        8
    );
}
~~~

Nếu một `riskService.check` phát `onError` không được xử lý, `flatMap` mặc định có thể làm cả publisher đầu ra kết thúc bằng lỗi. Kết quả là các event sau đó **không tự tiếp tục trong cùng subscription**.

Trong một event pipeline dài hạn, việc này có thể có hậu quả lớn hơn một request HTTP hữu hạn: một event lỗi không kiểm soát có thể dừng cả xử lý của stream.

### 12.1. Phục hồi bên trong khi muốn duy trì stream

~~~java
@Bean
Function<Flux<OrderEvent>, Flux<Decision>> assessResilient(
        RiskService riskService,
        FailedEventStore failures) {

    return incoming -> incoming.flatMap(
        event -> riskService.check(event)
            .onErrorResume(error ->
                failures.save(event, error)
                    .thenReturn(
                        Decision.unavailable(event.eventId())
                    )
            ),
        8
    );
}
~~~

Đây là pattern phổ biến khi các event độc lập. Nó vẫn có một nhánh **fail toàn luồng** khi không thể lưu sự cố vào `FailedEventStore`. Chính sách đó cần được quyết định có chủ đích.

### 12.2. Retry cả stream không giống restart đúng điểm

~~~java
Flux<Decision> risky = incoming
    .flatMap(riskService::check)
    .retryWhen(retryPolicy);
~~~

Nếu nguồn hot hoặc adapter broker có điểm offset/ack riêng, resubscribe không tự có nghĩa “bắt đầu từ event kế tiếp chưa được xử lý”. Nó có thể phát lại, mất event hoặc tạo pipeline mới tùy source/transport.

Khi cần độ tin cậy trên sự kiện quan trọng, hãy thiết kế cơ chế broker, checkpoint, partition, transaction, idempotency và dead-letter theo hợp đồng binder; không dựa vào một toán tử retry ở cuối Flux để đảm bảo exactly-once.

## 13. Consumer<Flux<T>> và Function<Flux<T>, Mono<Void>> khi có lỗi

Với reactive `Consumer<Flux<T>>`:

~~~java
@Bean
Consumer<Flux<OrderEvent>> unsafeConsumer() {
    return incoming ->
        incoming.doOnNext(this::persistOrder).subscribe();
}
~~~

`accept` trả `void`. Consumer tự subscribe nhưng không giữ `Disposable` và không cung cấp handler lỗi rõ ràng. Nếu `persistOrder` là blocking hoặc ném exception, toàn subscription có thể kết thúc; framework không có publisher kết quả để quan sát lỗi hoặc completion.

Một cách tốt hơn khi caller/adapter hỗ trợ publisher kết quả:

~~~java
@Bean
Function<Flux<OrderEvent>, Mono<Void>> persistAll(
        ReactiveOrderRepository repository) {

    return incoming -> incoming
        .concatMap(repository::save)
        .then();
}
~~~

`Mono<Void>` không phát payload nhưng có `onComplete` hoặc `onError` để caller quản lý.

**Lưu ý:** Nếu input là một `Flux` dài hạn không bao giờ hoàn tất, `Mono<Void>` cũng có thể không phát completion bình thường cho toàn stream. Kết quả cuối luồng **không thay thế** acknowledgment theo từng message.

### 13.1. Nếu bắt buộc dùng Consumer<Flux<T>>

Hãy thiết kế subscription, xử lý lỗi và lifecycle rõ ràng:

~~~java
Consumer<Flux<OrderEvent>> consumer = incoming -> {
    Disposable handle = incoming
        .concatMap(event ->
            repository.save(event)
                .onErrorResume(error ->
                    failures.save(event, error)
                )
        )
        .subscribe(
            ignored -> {},
            error -> logger.error("Consumer stream stopped", error),
            () -> logger.info("Consumer stream completed")
        );

    subscriptionRegistry.register(handle);
};
~~~

`repository.save` và `failures.save` là API giả định trả publisher tương thích, `subscriptionRegistry` là thành phần ứng dụng quản lý `Disposable` để hủy khi shutdown. Đây là phác thảo, không phải chương trình độc lập.

Nếu lưu lỗi cũng thất bại, subscriber sẽ nhận `onError` trong callback, cần chính sách vận hành để tái khởi động/đối soát chứ không chỉ log rồi bỏ.

## 14. Lỗi trong FunctionCatalog và composition

Giả sử có hai bean:

~~~java
@Bean
Function<Flux<OrderEvent>, Flux<OrderEvent>> validEvents() {
    return input -> input.filter(event ->
        event.amountCents() > 0
    );
}

@Bean
Function<Flux<OrderEvent>, Flux<Decision>> evaluate(
        RiskService service) {
    return input -> input.concatMap(service::check);
}
~~~

Có thể chọn composition:

~~~properties
spring.cloud.function.definition=validEvents|evaluate
~~~

Một lỗi ở `evaluate` có thể kết thúc publisher composition. Nếu đầu vào từ một broker, cách framework xử lý lỗi ngoài pipeline còn phụ thuộc Spring Cloud Stream và binder.

### 14.1. Không dùng filter để che lỗi mà nghiệp vụ cần ghi nhận

Ví dụ `validEvents` lọc event có `amountCents <= 0` thì các event đó biến mất khỏi output. Đó **không phải** xử lý lỗi có truy vết đầy đủ. Nếu những đơn bị loại cần được ghi audit hoặc gửi message từ chối, hãy đổi bước validation thành `Function<Flux<OrderEvent>, Flux<ValidationResult>>` để phát kết quả cho mỗi event.

Đối với composition, nên phân định rõ:

- **Bước chuẩn hóa/validation:** trả trạng thái nghiệp vụ cho input không hợp lệ.
- **Bước gọi dịch vụ bên ngoài:** có retry và xử lý lỗi tạm thời theo event.
- **Bước ghi kết quả:** chỉ báo hoàn tất khi đã đạt mốc lưu trữ theo hợp đồng.
- **Adapter:** mapping payload/header, lỗi transport và acknowledgment.

Một wrapper của `FunctionCatalog` không tự biến pipeline lỗi thành nhiều kết quả hợp lệ hoặc tự tạo cơ chế dead-letter.

### 14.2. Tách mapper lỗi sang một function riêng

~~~java
@Bean
Function<Flux<OrderEvent>, Flux<ProcessingResult>> safeEvaluate(
        RiskService service,
        FailedEventStore failures) {

    return input -> input.concatMap(event ->
        service.evaluate(event)
            .map(status -> new ProcessingResult(
                event.eventId(), status, "CHECKED"
            ))
            .onErrorResume(error ->
                failures.save(event, error)
                    .thenReturn(new ProcessingResult(
                        event.eventId(),
                        DecisionStatus.UNAVAILABLE,
                        "FAILED"
                    ))
            )
    );
}
~~~

Ví dụ sử dụng các record và interface đã định nghĩa ở mục 6. Chính sách xử lý lỗi nằm trong function, dễ tái sử dụng qua adapter, nhưng việc ghi dead-letter và mã trạng thái vẫn phải phù hợp nghiệp vụ.

## 15. HTTP, broker và serverless: lỗi nào được adapter nhìn thấy?

Spring Cloud Function tách logic Java khỏi giao thức, **không làm mọi môi trường có cùng ngữ nghĩa lỗi**.

| Môi trường | Ranh giới lỗi chính | Điều cần xác minh |
| --- | --- | --- |
| Gọi Java trực tiếp | Caller subscribe publisher | Có quan sát `onError` và xử lý cancellation đúng không? |
| `FunctionCatalog` | Catalog tra cứu, wrap và composition | Lỗi xảy ra ở chuyển đổi kiểu hay trong publisher? |
| HTTP adapter | Request/response, serialization, timeout | Adapter chuyển `onError` thành status/body nào? Có trả một kết quả cho mỗi phần tử không? |
| Spring Cloud Stream | Binding, binder, message delivery | Ack, retry, DLQ, offset/partition và lỗi trong pipeline reactive |
| Serverless adapter | Một invocation có deadline | Runtime có chờ publisher kết thúc? Lỗi/timeout có khiến event được gọi lại không? |

### 15.1. HTTP: lỗi trên stream có thể tới sau khi response bắt đầu

Với một response dạng streaming, vài phần tử có thể đã được ghi ra kết nối trước khi publisher phát `onError`. Khi đó server **không nhất thiết còn khả năng thay toàn bộ response bằng một JSON lỗi chuẩn hoặc đổi HTTP status** vì headers/body có thể đã được gửi.

Nếu API cần một phản hồi lỗi duy nhất cho một batch hữu hạn, có thể chủ động thu thập kết quả trong giới hạn bộ nhớ/thời gian trước khi trả; đổi lại là độ trễ và chi phí buffer. Cần chọn hợp đồng API tường minh.

### 15.2. Spring Cloud Stream: lỗi reactive không luôn giống lỗi per-message imperative

Một `Function<T,R>` imperative thường có một lời gọi xử lý trên một message do adapter cung cấp. Một `Function<Flux<T>, Flux<R>>` reactive có thể được gọi **một lần cho cả Flux dài hạn**; lỗi chỉ xuất hiện sau đó qua subscription.

Do đó, **không mặc định** cơ chế retry/DLQ mà binder áp dụng cho exception của imperative handler cũng xử lý giống hệt lỗi `onError` bên trong publisher reactive. Cần tham khảo tài liệu binder/version và test integration.

Nếu input là `Flux<Message<OrderEvent>>`, nên giữ `eventId` và correlation ID trong mỗi kết quả hoặc bản ghi lỗi; tránh dùng vị trí đầu ra để suy event đầu vào, đặc biệt khi `flatMap` có concurrency.

### 15.3. Serverless: fallback phải kết thúc trong thời hạn invocation

Một function có thể retry nhiều lần nhưng runtime serverless có timeout cứng. Nếu publisher chưa hoàn tất khi invocation kết thúc, nền tảng có thể hủy hoặc ngừng xử lý mà không chờ cleanup Java. Cần giới hạn tổng thời gian, retry, concurrency và số phần tử mỗi invocation.

Không phụ thuộc vào `subscribe()` fire-and-forget sau khi handler đã trả kết quả. Lỗi của công việc nền có thể không được runtime coi là invocation thất bại, khiến cơ chế redelivery không hoạt động như mong đợi.

## 16. Dead-letter, idempotency và độ tin cậy khi phục hồi

Khi lỗi theo phần tử, quyết định “tiếp tục” chỉ an toàn khi biết **điều gì xảy ra với phần tử lỗi**.

### 16.1. Ba chiến lược rõ ràng

| Chính sách | Điều kiện phù hợp | Rủi ro cần kiểm soát |
| --- | --- | --- |
| **Fail-fast** | Các event phụ thuộc nhau, lỗi làm trạng thái không an toàn | Cả stream dừng, cần khả năng replay/restart |
| **Ghi nhận lỗi rồi tiếp tục** | Event độc lập, có nơi lưu thất bại bền vững | Không được báo thành công trước khi lưu lỗi |
| **Retry có giới hạn, hết retry thì ghi lỗi** | Lỗi tạm thời có thể khôi phục | Retry trùng side effect, quá tải, thiếu idempotency |

### 16.2. Idempotency theo eventId

Giả sử broker giao lại một event do mất kết nối sau khi database đã commit. Nếu consumer xử lý lại mà không kiểm tra `eventId`, có thể ghi trùng.

Một thiết kế phổ biến:

- Mỗi event có ID bất biến.
- Database có unique constraint hoặc bảng trạng thái xử lý theo ID.
- Xử lý event và cập nhật trạng thái trong transaction phù hợp.
- Chỉ commit/ack message khi đạt mốc nghiệp vụ đã xác định.
- Phân loại event bị từ chối hợp lệ, event chưa xử lý được và event đã xử lý.

`onErrorResume` tự nó **không** đưa ra bảo đảm exactly-once. Nó chỉ chuyển đổi tín hiệu trong một subscription.

### 16.3. Không ghi dead-letter bằng thao tác “quên kết quả”

~~~java
// Sai: không chờ publisher lưu dead-letter.
.onErrorResume(error -> {
    failedEventStore.save(event, error).subscribe();
    return Mono.just(Decision.unavailable(event.eventId()));
})
~~~

Publisher trả về có thể báo `UNAVAILABLE` trước khi lưu thất bại hoàn tất; nếu lưu lỗi thất bại, caller không thấy qua cùng pipeline.

Đúng hơn:

~~~java
.onErrorResume(error ->
    failedEventStore.save(event, error)
        .thenReturn(Decision.unavailable(event.eventId()))
)
~~~

Như vậy một nhánh lỗi vẫn gắn với **tín hiệu hoàn tất của thao tác lưu lỗi**.

### 16.4. DLQ của broker khác với FailedEventStore ứng dụng

`FailedEventStore` trong ví dụ là cơ chế nghiệp vụ tự triển khai. Một binder có thể có dead-letter topic/queue riêng, nhưng chế độ xử lý lỗi và thời điểm broker chuyển message vào DLQ phụ thuộc binder và cấu hình. Không mặc định rằng gọi `onErrorResume` trong function sẽ kích hoạt DLQ của binder; nếu lỗi đã được phục hồi, adapter có thể không thấy `onError` nữa.

## 17. Quan sát lỗi ở cả mức phần tử và toàn luồng

Nếu pipeline phục hồi thành công mọi lỗi của `RiskService`, bộ đếm **terminal errors** của toàn stream có thể bằng 0 trong khi hàng nghìn event đã thất bại nghiệp vụ. Vì vậy cần đo **hai tầng**:

| Nhóm metric | Ví dụ | Mục đích |
| --- | --- | --- |
| Per-event | `event.processed`, `event.rejected` | Số event theo kết quả |
| Per-event | `event.retry_count`, `event.fallback` | Mức độ lỗi tạm thời/khôi phục |
| Dead-letter | `event.failed_store.success/error` | Xác nhận có lưu lại event lỗi |
| Stream | `stream.on_error`, `stream.on_complete`, `stream.cancel` | Vòng đời subscription |
| I/O | Timeout, p95/p99 latency, connection saturation | Phát hiện dịch vụ đích kém ổn định |
| Transport | Redelivery, ack, lag, DLQ count | Đối chiếu với broker/binder |

Một mẫu:

~~~java
Flux<ProcessingResult> observed = incoming
    .concatMap(event -> processOne(event)
        .doOnError(error ->
            metrics.recordItemFailure(event.eventId(), error)
        )
        .onErrorResume(error ->
            recordFailure(event, error)
        )
    )
    .doOnError(error ->
        logger.error("Whole stream failed", error)
    )
    .doFinally(signal ->
        metrics.recordStreamTermination(signal.name())
    );
~~~

`processOne` và `recordFailure` là phương thức giả định trả `Mono<ProcessingResult>`. Nếu `recordFailure` lỗi, lỗi terminal đi ra ngoài và được `doOnError` cuối ghi nhận.

Không log payload có dữ liệu nhạy cảm chỉ để debug; nên log eventId, loại lỗi và correlation ID có kiểm soát. Tránh phát metric/tag riêng cho mỗi ID dẫn tới cardinality quá cao; dùng ID trong tracing/log phù hợp, còn metric tags nên dùng loại lỗi/nhóm nghiệp vụ hữu hạn.

### 17.1. onError ở một ranh giới không nhất thiết là terminal ở ranh giới khác

~~~java
Mono<Decision> one = riskClient.check(event)
    .doOnError(error -> metrics.innerError())
    .onErrorResume(error ->
        Mono.just(Decision.unavailable(event.eventId()))
    );
~~~

`doOnError` trước `onErrorResume` quan sát lỗi từ API, nhưng publisher `one` có thể hoàn tất bình thường sau fallback. Vì vậy việc log “stream failed” chỉ dựa vào hook lỗi bên trong mà không xét chính sách phục hồi sẽ gây hiểu nhầm.

## 18. Kiểm thử bằng StepVerifier: lỗi từng phần tử vs lỗi terminal

`reactor-test` hỗ trợ `StepVerifier` để xác minh thứ tự tín hiệu. Những test dưới đây dùng JUnit 5, Java 17+ và Project Reactor, không cần broker thật.

### 18.1. Ngoài cùng: lỗi dừng nguồn và fallback không tiếp tục C

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.Test;

import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

class ErrorScopeTest {

    @Test
    void outerResumeReplacesFailedSequence() {
        AtomicInteger executed = new AtomicInteger();

        Flux<Integer> source = Flux.just(1, 2, 3)
            .map(n -> {
                executed.incrementAndGet();

                if (n == 2) {
                    throw new IllegalStateException("bad 2");
                }
                return n * 10;
            })
            .onErrorResume(error -> Flux.just(-1));

        StepVerifier.create(source)
            .expectNext(10, -1)
            .verifyComplete();

        // Số 3 không đi qua mapper.
        assertEquals(2, executed.get());
    }
}
~~~

Test chứng minh `onErrorResume` đặt ngoài cùng chuyển sang fallback thay vì quay lại upstream cũ.

### 18.2. Trong publisher con: C vẫn được xử lý

~~~java
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

class PerItemRecoveryTest {

    @Test
    void recoversOnlyTheFailedItem() {
        Flux<Integer> source = Flux.just(1, 2, 3)
            .concatMap(n ->
                Mono.fromCallable(() -> {
                    if (n == 2) {
                        throw new IllegalStateException("bad 2");
                    }
                    return n * 10;
                })
                .onErrorResume(error -> Mono.just(-1))
            );

        StepVerifier.create(source)
            .expectNext(10, -1, 30)
            .verifyComplete();
    }
}
~~~

### 18.3. Dead-letter thành công thì tiếp tục

Ví dụ kiểm thử `OrderErrorFunctions` ở mục 6:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.Test;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

class OrderErrorFunctionsTest {

    @Test
    void recordsFailedOrderAndContinues() {
        OrderErrorFunctions config = new OrderErrorFunctions();
        AtomicInteger failedWrites = new AtomicInteger();

        OrderErrorFunctions.RiskService service = event ->
            "B".equals(event.eventId())
                ? Mono.error(new IllegalStateException("unavailable"))
                : Mono.just(
                    OrderErrorFunctions.DecisionStatus.APPROVED
                );

        OrderErrorFunctions.FailedEventStore store =
            (event, error) -> Mono.fromRunnable(
                failedWrites::incrementAndGet
            );

        var function = config.processOrders(service, store);

        var events = Flux.just(
            new OrderErrorFunctions.OrderEvent("A", "O-1", 100),
            new OrderErrorFunctions.OrderEvent("B", "O-2", 200),
            new OrderErrorFunctions.OrderEvent("C", "O-3", 300)
        );

        StepVerifier.create(function.apply(events))
            .expectNext(
                new OrderErrorFunctions.ProcessingResult(
                    "A",
                    OrderErrorFunctions.DecisionStatus.APPROVED,
                    "CHECKED"
                ),
                new OrderErrorFunctions.ProcessingResult(
                    "B",
                    OrderErrorFunctions.DecisionStatus.UNAVAILABLE,
                    "RISK_SERVICE_FAILED"
                ),
                new OrderErrorFunctions.ProcessingResult(
                    "C",
                    OrderErrorFunctions.DecisionStatus.APPROVED,
                    "CHECKED"
                )
            )
            .verifyComplete();

        assertEquals(1, failedWrites.get());
    }
}
~~~

`Mono.fromRunnable` ở failed store được subscribe như một phần của pipeline; do đó test thấy một lượt ghi thất bại. Với store thực tế, cần integration test xác nhận khi publisher báo complete thì dữ liệu đã đủ bền vững theo thiết kế.

### 18.4. Dead-letter lỗi thì toàn luồng dừng

~~~java
@Test
void failedDeadLetterStoreTerminatesStream() {
    OrderErrorFunctions config = new OrderErrorFunctions();

    OrderErrorFunctions.RiskService service = event ->
        "B".equals(event.eventId())
            ? Mono.error(new IllegalStateException("risk down"))
            : Mono.just(
                OrderErrorFunctions.DecisionStatus.APPROVED
            );

    OrderErrorFunctions.FailedEventStore brokenStore =
        (event, error) -> Mono.error(
            new IllegalStateException("failed store down")
        );

    var function = config.processOrders(service, brokenStore);

    StepVerifier.create(function.apply(Flux.just(
            new OrderErrorFunctions.OrderEvent("A", "O-1", 100),
            new OrderErrorFunctions.OrderEvent("B", "O-2", 200),
            new OrderErrorFunctions.OrderEvent("C", "O-3", 300)
        )))
        .expectNext(
            new OrderErrorFunctions.ProcessingResult(
                "A",
                OrderErrorFunctions.DecisionStatus.APPROVED,
                "CHECKED"
            )
        )
        .expectErrorMessage("failed store down")
        .verify();
}
~~~

Test trên là phương thức có thể thêm vào class `OrderErrorFunctionsTest` với các import ở test trước. Nó xác nhận rằng function **không báo thành công giả** khi nơi lưu thất bại cũng bị lỗi.

### 18.5. Delay-error: tiếp tục phát giá trị rồi báo lỗi cuối cùng

~~~java
@Test
void concatMapDelayErrorReportsAtEnd() {
    Flux<Integer> source = Flux.just(1, 2, 3)
        .concatMapDelayError(n -> n == 2
            ? Mono.<Integer>error(
                new IllegalStateException("bad 2")
              )
            : Mono.just(n * 10)
        );

    StepVerifier.create(source)
        .expectNext(10, 30)
        .expectErrorMessage("bad 2")
        .verify();
}
~~~

Đây là test cho nguồn hữu hạn và inner publisher đơn giản. `concatMapDelayError` báo lỗi sau khi đã xử lý những inner publishers còn lại, nhưng **không chuyển lỗi thành kết quả thành công**.

## 19. Kiểm thử retry có backoff bằng thời gian ảo

Chờ thật nhiều giây trong unit test là chậm và dễ không ổn định. `StepVerifier.withVirtualTime` cho phép điều khiển một số scheduler Reactor khi publisher được tạo **trong supplier của test**.

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.time.Duration;
import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.Test;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;
import reactor.util.retry.Retry;

class RetryPerItemTest {

    @Test
    void retriesOnlyBThenContinuesC() {
        AtomicInteger bAttempts = new AtomicInteger();

        StepVerifier.withVirtualTime(() ->
                Flux.just("A", "B", "C")
                    .concatMap(id ->
                        Mono.defer(() -> {
                            if ("B".equals(id)
                                    && bAttempts.incrementAndGet() == 1) {
                                return Mono.<String>error(
                                    new IllegalStateException("temporary")
                                );
                            }
                            return Mono.just(id);
                        })
                        .retryWhen(
                            Retry.fixedDelay(
                                1,
                                Duration.ofSeconds(5)
                            )
                        )
                    )
            )
            .expectNext("A")
            .thenAwait(Duration.ofSeconds(5))
            .expectNext("B", "C")
            .verifyComplete();

        assertEquals(2, bAttempts.get());
    }
}
~~~

B bị lỗi đúng lần đầu và được thử lại sau năm giây **thời gian ảo**; A và C không cần retry. Bài test không mô phỏng response thật của HTTP client, database hay retry/ack của broker.

### 19.1. Điều StepVerifier không chứng minh

Unit test kiểm tra publisher thuần không tự chứng minh:

- Broker đã xác nhận đúng message nào.
- Một HTTP response đã được gửi và mapping lỗi đúng status chưa.
- Dead-letter topic có nhận bản ghi bền vững không.
- Cancellation đã rollback transaction của database chưa.
- Tình huống nhiều instance cùng xử lý một `eventId` có được khóa an toàn không.

Phải bổ sung integration test với adapter, binder/driver và cấu hình production tương ứng.

## 20. Checklist quyết định chính sách lỗi

~~~mermaid
flowchart TD
    START["Một event bị lỗi"] --> CLASS{"Lỗi nghiệp vụ dự kiến?"}
    CLASS -->|Có| DATA["Trả Result(REJECTED) có eventId"]
    CLASS -->|Không| RETRY{"Lỗi hạ tầng tạm thời,\nđược phép retry?"}
    RETRY -->|Có| TRY["retryWhen có giới hạn + timeout"]
    RETRY -->|Không hoặc hết retry| DEP{"Event độc lập,\ncó thể tiếp tục an toàn?"}
    TRY --> DEP
    DEP -->|Có| STORE["Ghi thất bại bền vững"]
    STORE --> OK{"Ghi lỗi thành công?"}
    OK -->|Có| CONTINUE["Trả UNAVAILABLE và xử lý event kế"]
    OK -->|Không| FAIL["onError: dừng luồng có kiểm soát"]
    DEP -->|Không| FAIL
    DATA --> CHECK["Kiểm chứng ack/retry/idempotency"]
    CONTINUE --> CHECK
    FAIL --> CHECK
~~~

Trước khi quyết định đặt `onErrorResume` hoặc `retryWhen` ở đâu, hãy trả lời:

1. **Đơn vị công việc** là một event, một batch hay toàn stream?
2. **Lỗi có dự đoán được không?** Nên trả kết quả `REJECTED` hay phát `onError`?
3. **Các event có độc lập không?** Nếu B thất bại thì C vẫn an toàn để chạy chứ?
4. **Retry có lặp side effect không?** Đã có idempotency key/unique constraint chưa?
5. **Có thể mất event không?** Nếu không, nơi lưu thất bại có đủ bền vững không?
6. **Phục hồi được đặt trong publisher con chưa?** Hay `onErrorResume` ngoài cùng sẽ ngừng upstream cũ?
7. **Nếu dead-letter thất bại thì sao?** Có fail toàn stream để báo động không?
8. **Khi luồng dài hạn gặp lỗi:** ai tái tạo subscription và từ offset/checkpoint nào?
9. **Ack xảy ra ở đâu?** Broker có thực sự biết công việc đã commit chưa?
10. **Lỗi từ converter/transport** có đi vào function hay được adapter xử lý riêng?
11. **Metric** có phân biệt số item fallback và số stream terminal errors không?
12. **Có test** cho A thành công – B lỗi – C thành công, retry, DLQ lỗi, timeout và restart không?

## 21. Các hiểu nhầm thường gặp

| Hiểu nhầm | Sự thật cần nhớ |
| --- | --- |
| “`onErrorResume` ở cuối Flux bỏ qua B rồi tiếp tục C.” | Nó thay publisher upstream đã lỗi bằng fallback; phần C của nguồn cũ không được xử lý tiếp trong cùng subscription. |
| “Một event lỗi thì mọi stream bắt buộc dừng.” | Có thể cô lập lỗi bằng publisher con và phục hồi theo event nếu nghiệp vụ cho phép. |
| “`doOnError` sửa lỗi.” | Nó chỉ quan sát; lỗi vẫn truyền tiếp. |
| “`onErrorMap` tiếp tục luồng.” | Nó đổi exception, nhưng vẫn phát terminal error nếu không có bước phục hồi khác. |
| “`onErrorComplete` luôn an toàn.” | Nó có thể che lỗi và làm downstream tưởng batch thành công. |
| “`onErrorContinue` hoạt động với mọi operator.” | Chỉ một số operator hỗ trợ, hành vi có thể khó suy luận và ảnh hưởng upstream. |
| “`concatMapDelayError` bỏ qua mọi lỗi.” | Nó trì hoãn terminal error chứ không biến lỗi thành thành công. |
| “Retry ngoài cùng chỉ thử lại event B.” | Nó có thể subscribe lại toàn nguồn, xử lý A lần nữa. |
| “Retry theo event không gây trùng.” | Mỗi lần thử có thể làm lại side effect; cần idempotency. |
| “Một fallback `Mono.empty()` luôn có nghĩa đã xử lý.” | Nó có thể khiến event biến mất khỏi output mà không có ghi nhận. |
| “Gửi DLQ bằng `subscribe()` rồi return thành công là đủ.” | Không chờ/quan sát kết quả lưu DLQ trong cùng pipeline. |
| “Stream hoàn tất nghĩa broker đã ack mọi message.” | Completion Reactor và acknowledgment transport có hợp đồng riêng. |
| “Reactive function có cùng retry behavior với imperative handler.” | Ranh giới invocation/error khác nhau; cần kiểm tra binder. |
| “Timeout chắc chắn rollback request đã gửi.” | Cancellation có thể không hủy/rollback tác vụ ngoài. |
| “Cứ log onError cuối là biết đủ số event lỗi.” | Những lỗi đã phục hồi theo event không còn là terminal errors của toàn stream. |

## 22. Câu hỏi tự đánh giá

1. `onError` khác một `ProcessingResult(REJECTED)` ở cấp hợp đồng như thế nào?
2. Với nguồn `Flux.just(1,2,3)`, mapper ném lỗi ở 2 và `onErrorResume` đặt ngoài cùng, vì sao 3 không được xử lý?
3. Làm thế nào để B thất bại nhưng vẫn xử lý được C một cách tường minh?
4. Khi `concatMap` xử lý một `Mono` con đã phục hồi lỗi, kết quả terminal của toàn `Flux` sẽ ra sao?
5. `flatMap(..., 8)` và `concatMap` khác nhau thế nào về thứ tự, concurrency và phản ứng trước lỗi?
6. Lỗi `RiskService` và lỗi `FailedEventStore` có nên có cùng chính sách không? Vì sao?
7. Khi nào `onErrorReturn` hợp lý và khi nào nó làm mất correlation ID?
8. Vì sao `onErrorContinue` có thể gây bất ngờ trong composition hoặc khi thư viện thay đổi operator?
9. `retry(2)` bên ngoài toàn luồng khác gì `retryWhen` bên trong publisher con?
10. `concatMapDelayError` có làm stream thành công sau khi một item lỗi không?
11. Vì sao timeout của một publisher có thể khiến inner hook thấy `CANCEL` nhưng downstream thấy `ON_ERROR`?
12. Trong stream dài hạn, một `onError` không xử lý có thể ảnh hưởng việc nhận các event sau thế nào?
13. Tại sao cần chờ `FailedEventStore.save(...)` hoàn tất trước khi phát kết quả `UNAVAILABLE`?
14. Nếu binder redeliver event sau crash, làm sao tránh side effect lặp?
15. Tại sao metric terminal `onError` của toàn stream có thể bằng 0 dù nhiều item đã fallback?
16. Bạn sẽ viết `StepVerifier` nào để chứng minh A xử lý, B thất bại có ghi nhận, C vẫn xử lý?
17. Vì sao unit test Reactor thành công chưa chứng minh DLQ/ack của Spring Cloud Stream đã đúng?
18. Khi HTTP response đang stream đã gửi vài item, server có luôn đổi được status sang lỗi không?

## 23. Tài liệu tham khảo

- [Project Reactor — Reference Guide](https://projectreactor.io/docs/core/release/reference/) — Reactive Streams, terminal signals, `onErrorResume`, `retryWhen` và các toán tử flatten.
- [Project Reactor — Error Handling](https://projectreactor.io/docs/core/release/reference/coreFeatures/error-handling.html) — phân biệt các dạng xử lý lỗi, fallback, retry và lưu ý về `onErrorContinue`.
- [Project Reactor — Flux API](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Flux.html) — hợp đồng `concatMap`, `concatMapDelayError`, `flatMapDelayError` và operator lỗi.
- [Project Reactor — Testing](https://projectreactor.io/docs/test/release/reference/) — `StepVerifier` và thời gian ảo.
- [Spring Cloud Function — Programming Model](https://docs.spring.io/spring-cloud-function/reference/spring-cloud-function/programming-model.html) — hàm imperative/reactive, `FunctionCatalog` và composition.
- [Spring Cloud Stream — Producing and Consuming Messages](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/producing-and-consuming-messages.html) — xử lý hàm reactive và ranh giới binder.

Các ví dụ sử dụng Java 17+, Spring Cloud Function và Reactor. Các chi tiết thuộc HTTP adapter, binder, retry/DLQ, transaction và acknowledgment cần kiểm chứng theo phiên bản thư viện và giao thức thực tế.

**Ghi nhớ:** `onError` là tín hiệu **kết thúc subscription**, không phải một thông báo “phần tử này bị lỗi rồi hãy tiếp tục”. Muốn phục hồi lỗi **theo phần tử**, hãy tạo publisher con cho từng event bằng `concatMap`/`flatMap` và đặt `onErrorResume`, retry hoặc ghi dead-letter **bên trong** ranh giới đó. Nếu sự cố làm mất tính nhất quán hoặc không thể lưu bản ghi thất bại, nên để lỗi lan ra và dừng stream có kiểm soát. Trong Spring Cloud Function, một publisher xử lý được lỗi không đồng nghĩa broker đã ack đúng hoặc giao dịch đã commit; cần idempotency, quan sát, integration test và chính sách khôi phục phù hợp với từng adapter.
