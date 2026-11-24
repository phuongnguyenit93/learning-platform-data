# Xử lý lỗi bằng onErrorResume, retryWhen và phạm vi phục hồi

Trong ứng dụng reactive, lỗi là một tín hiệu kết thúc của `Mono` hoặc `Flux`. Khi một publisher phát `onError`, chuỗi xử lý hiện tại kết thúc trừ khi có toán tử phục hồi thay thế tín hiệu lỗi hoặc đăng ký lại nguồn. Với Spring Cloud Stream, điều này đặc biệt quan trọng khi một hàm nhận luồng message, gọi dịch vụ bên ngoài rồi phát kết quả trở lại broker.

Reactor cung cấp hai toán tử thường dùng cho tình huống này. `onErrorResume` chuyển lỗi thành một publisher dự phòng; `retryWhen` đăng ký lại publisher khi lỗi thỏa điều kiện retry. Chúng có thể được kết hợp, nhưng vị trí đặt toán tử quyết định phạm vi phục hồi: chỉ một message, một bước trong pipeline hay toàn bộ luồng. Đặt sai vị trí có thể làm mất message, dừng cả stream hoặc lặp lại tác dụng phụ đã thực hiện.

Bài thuộc chương **Xử lý phản ứng** của module `SPRING_CLOUD_STREAM`. Module sử dụng mô hình hàm `Supplier`/`Function`/`Consumer`, binding và binder cho Kafka, RabbitMQ hoặc Pulsar. Ta sẽ dùng Reactor `Mono`/`Flux` để minh họa xử lý lỗi trong function reactive, đồng thời phân biệt retry trong ứng dụng với retry, redelivery và xác nhận message ở tầng binder/broker.

## 1. Lỗi trong Reactor là tín hiệu của publisher

Một `Mono<T>` có thể phát một giá trị rồi hoàn tất, hoàn tất mà không có giá trị hoặc phát lỗi. Một `Flux<T>` có thể phát nhiều giá trị rồi hoàn tất hoặc phát lỗi. Khi một publisher phát `onError`, publisher đó không tiếp tục phát các phần tử sau lỗi.

```text
Flux<OrderEvent>
     |
     +--> onNext(event 1)
     +--> onNext(event 2)
     +--> onError(exception)
     |
     +--> kết thúc chuỗi hiện tại
```

Điều này khác với vòng lặp imperative có thể bắt exception ở từng lần lặp rồi tiếp tục. Với reactive stream, nếu một phép xử lý trong `flatMap` phát lỗi và lỗi thoát ra ngoài, lỗi có thể kết thúc publisher tổng thể. Muốn cô lập lỗi của từng message, cần đặt cơ chế phục hồi bên trong publisher xử lý message đó.

Trong một function reactive của Spring Cloud Stream, ví dụ `Function<Flux<OrderEvent>, Flux<OrderResult>>`, framework kết nối luồng message đầu vào với publisher đầu ra. Hàm nên biểu diễn rõ lỗi nào được phục hồi, lỗi nào được thử lại và lỗi nào phải truyền ra ngoài để tầng xử lý lỗi tiếp theo quyết định.

## 2. Phân biệt `onErrorResume` và `retryWhen`

| Toán tử | Hành vi | Dùng khi |
|---|---|---|
| `onErrorResume` | Khi publisher lỗi, gọi hàm dự phòng và chuyển sang publisher mới | Có kết quả thay thế, muốn ghi nhận lỗi hoặc chuyển message sang luồng cách ly |
| `retryWhen` | Khi lỗi thỏa chính sách retry, đăng ký lại publisher nguồn | Lỗi có tính tạm thời và thao tác có thể thực hiện lại an toàn |

`onErrorResume` không tự chạy lại thao tác đã lỗi. Nó thay tín hiệu lỗi bằng một publisher khác. Publisher dự phòng có thể trả kết quả mặc định, phát kết quả nghiệp vụ như `REJECTED`, ghi message vào DLQ rồi hoàn tất, hoặc tiếp tục phát lỗi.

`retryWhen` không tạo ra một kết quả dự phòng. Nó đăng ký lại publisher theo một chính sách, có thể gồm số lần thử, khoảng nghỉ, backoff và điều kiện lọc loại lỗi. Khi retry hết giới hạn, lỗi cuối cùng được phát ra nếu không có chính sách khác.

Ví dụ đơn giản:

```java
Mono<OrderResult> result = orderService.process(order)
    .onErrorResume(InsufficientStockException.class,
        error -> Mono.just(OrderResult.rejected(order.orderId())))
    .retryWhen(Retry.max(2));
```

Đoạn code này không phải cách kết hợp tốt cho mọi tình huống: khi `onErrorResume` đã biến lỗi thành kết quả thành công, `retryWhen` phía sau không còn thấy lỗi đó để thử lại. Thứ tự toán tử cần được chọn theo ý định phục hồi. Phần tiếp theo trình bày cách đặt retry trước fallback.

## 3. Dùng `onErrorResume` để thay thế lỗi

`onErrorResume` nhận một lỗi và trả về publisher thay thế. Có thể chọn publisher dự phòng theo kiểu exception:

```java
Mono<OrderResult> result = orderService.process(order)
    .onErrorResume(InsufficientStockException.class,
        error -> Mono.just(
            OrderResult.rejected(order.orderId(), error.getMessage())
        ));
```

Khi thiếu tồn kho là một kết quả nghiệp vụ có thể dự đoán, ứng dụng có thể trả về `REJECTED` thay vì để lỗi kỹ thuật kết thúc luồng. Đây là phục hồi ở tầng nghiệp vụ; nó không có nghĩa đơn hàng đã được xử lý thành công.

Một số dạng fallback thường gặp:

```java
// Trả một kết quả thay thế cùng kiểu.
source.onErrorResume(error -> Mono.just(fallbackValue));

// Bỏ qua phần tử/lần xử lý hiện tại bằng cách hoàn tất rỗng.
source.onErrorResume(error -> Mono.empty());

// Chuyển sang một publisher khác, ví dụ ghi nhận trạng thái.
source.onErrorResume(error -> auditService.record(error).thenReturn(fallbackValue));

// Không phục hồi một loại lỗi; tiếp tục phát lỗi cho tầng bên ngoài.
source.onErrorResume(error -> Mono.error(error));
```

Publisher thay thế phải phù hợp với kiểu đầu ra của chuỗi. Với `Mono<OrderResult>`, fallback thường phải trả `Mono<OrderResult>`. Dùng `Mono.empty()` có nghĩa không phát kết quả cho phần tử đó; cần xác định rõ việc bỏ kết quả có phù hợp với hợp đồng nghiệp vụ hay không.

Không nên dùng một giá trị mặc định như `OrderResult.success()` chỉ để làm stream không lỗi. Nếu thao tác thực tế thất bại, kết quả giả thành công có thể khiến hệ thống downstream cập nhật trạng thái sai.

## 4. Dùng `retryWhen` cho lỗi tạm thời

Các lỗi như timeout ngắn, kết nối database tạm gián đoạn hoặc dịch vụ phụ thuộc trả lỗi 503 có thể phục hồi sau một khoảng thời gian. Có thể dùng `Retry.backoff` để thử lại với khoảng nghỉ tăng dần:

```java
import java.time.Duration;

import reactor.util.retry.Retry;

Mono<Reservation> reservation = inventoryClient.reserve(order)
    .retryWhen(
        Retry.backoff(3, Duration.ofMillis(200))
            .maxBackoff(Duration.ofSeconds(2))
            .filter(this::isTransientFailure)
    );
```

Trong ví dụ:

- `3` là số lần retry tối đa sau lần thử ban đầu. Vì vậy có thể có tối đa bốn lần thực thi: một lần đầu và ba lần retry.
- Khoảng nghỉ bắt đầu ở 200 mili giây và tăng theo backoff.
- `maxBackoff` giới hạn khoảng nghỉ tối đa ở 2 giây.
- `filter` chỉ cho phép retry những exception được xem là tạm thời.

Ví dụ phân loại lỗi:

```java
private boolean isTransientFailure(Throwable error) {
    return error instanceof java.util.concurrent.TimeoutException
        || error instanceof TransientOrderDependencyException;
}
```

Không nên retry mọi exception. Lỗi dữ liệu không hợp lệ, thiếu quyền, vi phạm quy tắc nghiệp vụ hoặc schema sai thường không tự hết khi chờ. Retry chúng chỉ làm tăng tải và kéo dài thời gian xử lý.

Có thể thêm jitter để nhiều instance không cùng retry đúng một thời điểm:

```java
Retry.backoff(3, Duration.ofMillis(200))
    .maxBackoff(Duration.ofSeconds(2))
    .jitter(0.5)
    .filter(this::isTransientFailure);
```

Jitter ngẫu nhiên hóa khoảng nghỉ quanh lịch backoff, giúp giảm hiện tượng nhiều consumer đồng loạt gọi lại một dependency sau khi dịch vụ phục hồi.

## 5. Vì sao nên đặt `Mono.defer` quanh thao tác cần retry?

`retryWhen` đăng ký lại publisher upstream. Để mỗi lần đăng ký thực sự tạo một lần gọi nghiệp vụ mới, có thể dùng `Mono.defer`:

```java
Mono<Reservation> reservation = Mono.defer(
        () -> inventoryClient.reserve(order))
    .retryWhen(
        Retry.backoff(3, Duration.ofMillis(200))
            .filter(this::isTransientFailure)
    );
```

`Mono.defer` trì hoãn việc gọi `reserve` cho đến lúc có subscription. Mỗi lần retry đăng ký lại, lambda được chạy lại và tạo publisher mới. Cách này cũng đưa exception phát sinh đồng bộ trong lúc tạo publisher vào chuỗi reactive để có thể xử lý bằng các toán tử phía sau.

Nếu publisher đã được tạo theo cách cold và thao tác chỉ chạy khi subscribe, retry có thể đăng ký lại publisher đó. Dù vậy, `defer` làm ranh giới thực thi rõ ràng và thường an toàn hơn khi lời gọi service có thể phát sinh exception ngay lúc gọi phương thức.

Lưu ý: `Mono.defer` không tự làm thao tác idempotent. Nếu lần đầu đã ghi dữ liệu hoặc trừ tiền trước khi timeout, lần retry có thể lặp tác dụng phụ. Cần có idempotency key, unique constraint hoặc cơ chế transaction phù hợp.

## 6. Phạm vi phục hồi: một message hay toàn bộ Flux?

Đây là quyết định quan trọng nhất khi xử lý lỗi trong một reactive function.

### Phục hồi từng message

Đặt `retryWhen` và `onErrorResume` bên trong publisher của từng phần tử. Một message lỗi có thể được retry hoặc cách ly mà không làm dừng các message khác:

```java
Flux<OrderResult> results = events.flatMap(event ->
    Mono.defer(() -> orderService.process(event))
        .retryWhen(retryPolicy)
        .onErrorResume(error -> handleFailure(event, error))
);
```

`flatMap` tạo một publisher con cho mỗi event. Nếu publisher con tự xử lý lỗi và hoàn tất, các event khác vẫn có thể tiếp tục. Nếu lỗi thoát khỏi publisher con, lỗi có thể truyền ra ngoài và kết thúc `Flux` tổng.

### Phục hồi toàn bộ stream

Đặt `onErrorResume` sau các toán tử xử lý `Flux` sẽ phục hồi lỗi ở phạm vi toàn chuỗi:

```java
Flux<OrderResult> results = events
    .flatMap(orderService::process)
    .onErrorResume(error -> fallbackForWholeStream(error));
```

Nếu một event làm `flatMap` phát lỗi ra ngoài, `Flux` đầu vào đã đi vào trạng thái lỗi. `onErrorResume` thay toàn bộ phần còn lại của stream bằng publisher fallback. Nó không tự quay lại event tiếp theo của nguồn ban đầu. Những event chưa được xử lý trong subscription đó có thể không đi qua function theo cách ứng dụng mong đợi.

### Sơ đồ phạm vi

```text
Phục hồi từng message

Flux<Event> -> flatMap(
                 event -> process(event)
                            .retryWhen(...)
                            .onErrorResume(...)
              ) -> Flux<Result>

Phục hồi toàn stream

Flux<Event> -> flatMap(process)
                    |
                    +-- một lỗi thoát ra ngoài
                    v
              onErrorResume(fallback)
                    |
                    v
              fallback cho phần còn lại của stream
```

Với xử lý message độc lập, thường nên phục hồi bên trong publisher của từng event. Phục hồi toàn stream phù hợp khi lỗi làm toàn bộ luồng không thể tiếp tục, chẳng hạn nguồn cấu hình hoặc dependency chung không còn hợp lệ và ứng dụng muốn chuyển sang một luồng fallback có chủ đích.

## 7. Ví dụ function reactive xử lý từng đơn hàng

Ví dụ dưới đây minh họa ba bước: thử lại lỗi tạm thời, chuyển lỗi nghiệp vụ đã biết thành kết quả từ chối, và đưa lỗi còn lại vào một publisher cách ly. Các service được giả định trả về Reactor publisher.

```java
import java.time.Duration;
import java.util.concurrent.TimeoutException;
import java.util.function.Function;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.util.retry.Retry;

record OrderEvent(String eventId, String orderId, long total) {}

record OrderResult(String orderId, String status, String reason) {
    static OrderResult rejected(String orderId, String reason) {
        return new OrderResult(orderId, "REJECTED", reason);
    }
}

@Configuration
class ReactiveOrderConfiguration {

    @Bean
    Function<Flux<OrderEvent>, Flux<OrderResult>> processOrders(
            OrderService orderService,
            DeadLetterPublisher deadLetterPublisher) {

        return events -> events.flatMap(event ->
            Mono.defer(() -> orderService.process(event))
                .retryWhen(
                    Retry.backoff(3, Duration.ofMillis(200))
                        .maxBackoff(Duration.ofSeconds(2))
                        .filter(error ->
                            error instanceof TimeoutException
                                || error instanceof TransientOrderDependencyException)
                        .onRetryExhaustedThrow((spec, signal) -> signal.failure())
                )
                .onErrorResume(InsufficientStockException.class, error ->
                    Mono.just(OrderResult.rejected(
                        event.orderId(), error.getMessage()))
                )
                .onErrorResume(error ->
                    deadLetterPublisher.publish(event, error)
                        .then(Mono.<OrderResult>empty())
                )
        );
    }
}
```

Các điểm cần hiểu:

1. `events.flatMap(...)` xử lý từng message bằng một publisher con.
2. `Mono.defer` gọi `orderService.process(event)` khi publisher được subscribe.
3. `retryWhen` thử lại timeout và lỗi dependency tạm thời, tối đa ba lần.
4. `InsufficientStockException` được chuyển thành kết quả nghiệp vụ `REJECTED`.
5. Các lỗi còn lại được gửi đến `DeadLetterPublisher`; chỉ sau khi publisher DLQ hoàn tất, publisher con mới hoàn tất rỗng.
6. Nếu gửi DLQ cũng thất bại, lỗi của `deadLetterPublisher` tiếp tục truyền ra ngoài vì fallback chưa hoàn tất thành công.

Đoạn code là mẫu minh họa; `OrderService`, `DeadLetterPublisher` và các exception là thành phần ứng dụng cần triển khai. Nếu muốn giữ thứ tự xử lý và phát kết quả theo thứ tự đầu vào, cân nhắc `concatMap` thay cho `flatMap`, đổi lại giảm khả năng xử lý song song. `flatMapSequential` có thể thực hiện publisher con đồng thời nhưng giữ thứ tự phát kết quả; nó không bảo đảm các tác dụng phụ bên trong hoàn tất theo thứ tự.

## 8. Thứ tự đặt toán tử làm thay đổi hành vi

Thông thường, đặt retry trước fallback để lỗi có cơ hội được thử lại trước khi chuyển sang kết quả thay thế:

```java
source
    .retryWhen(retryPolicy)
    .onErrorResume(error -> fallback(error));
```

Ở đây `onErrorResume` nhận lỗi còn lại sau khi retry không áp dụng được hoặc đã hết số lần thử.

Nếu đảo thứ tự:

```java
source
    .onErrorResume(error -> fallback(error))
    .retryWhen(retryPolicy);
```

thì khi fallback hoàn tất bình thường, `retryWhen` phía sau không còn nhận tín hiệu lỗi để retry. Đây có thể là chủ đích nếu fallback là kết quả cuối cùng, nhưng không phù hợp nếu muốn thử lại thao tác nguồn trước.

Một mẫu tổng quát:

```java
Mono<Result> recover(Mono<Result> source) {
    return source
        .retryWhen(retryTransientErrors())
        .onErrorResume(KnownBusinessException.class,
            this::businessFallback)
        .onErrorResume(UnexpectedException.class,
            this::unexpectedFailurePath);
}
```

Không nên nối nhiều fallback rộng mà không có phân loại lỗi. Một `onErrorResume(Throwable.class, ...)` đặt quá sớm có thể che khuất lỗi lập trình, lỗi cấu hình hoặc lỗi dữ liệu cần được phát hiện.

## 9. Retry trong Reactor không đồng nghĩa broker redelivery

Trong Spring Cloud Stream, có nhiều tầng có thể thử lại:

- **Reactor retry:** đăng ký lại publisher upstream trong ứng dụng.
- **Retry của binder/framework:** xử lý lỗi mà framework/binder quan sát được tại ranh giới message handler.
- **Broker redelivery:** broker giao lại message chưa được xác nhận theo cơ chế của broker.
- **Retry nghiệp vụ:** ứng dụng lưu một tác vụ cần thử lại sau đó, thường qua database, outbox hoặc retry destination.

Các cơ chế này không tương đương nhau. `retryWhen` bên trong một publisher xử lý event thường lặp lại thao tác downstream như gọi API hoặc database; nó không tự yêu cầu Kafka, RabbitMQ hoặc Pulsar giao lại message từ đầu. Ngược lại, nếu lỗi thoát khỏi function, cách binder xác nhận, rollback, retry hoặc để broker giao lại phụ thuộc binder, phiên bản và cấu hình.

Khi `onErrorResume` biến lỗi thành kết quả hoặc hoàn tất rỗng, tầng ngoài có thể quan sát publisher hoàn tất bình thường. Vì vậy, không nên giả định binder sẽ redeliver message ban đầu. Nếu muốn broker/binder xử lý lỗi, cần để lỗi truyền ra ngoài theo cách mà cơ chế đó hỗ trợ, hoặc dùng error channel/DLQ theo cấu hình phù hợp.

Với reactive binding, acknowledgement và commit offset có thể được gắn với quá trình tiêu thụ publisher; chi tiết khác nhau theo binder. Hãy kiểm thử hành vi thực tế thay vì suy ra từ việc `Mono` đã hoàn tất trong code.

## 10. Chọn nơi phục hồi: trong hàm hay ở binder?

| Nhu cầu | Phục hồi trong Reactor | Phục hồi ở binder/broker |
|---|---|---|
| Retry một lời gọi HTTP tạm lỗi cho một event | Phù hợp với `retryWhen` quanh lời gọi đó | Binder không nhất thiết biết lời gọi HTTP thất bại ở tầng nào |
| Chuyển lỗi nghiệp vụ thành `REJECTED` | Phù hợp với `onErrorResume` có kiểu exception cụ thể | Không cần broker redelivery nếu đó là kết quả nghiệp vụ cuối |
| Message không thể deserialize trước khi gọi function | Không thể dùng toán tử trong function chưa được gọi | Xử lý ở ranh giới binder/conversion/error handling |
| Muốn broker giao lại message khi function thất bại | Truyền lỗi ra ngoài; không nuốt bằng fallback thành công | Dùng retry/ack/redelivery của binder và broker |
| Cách ly message lỗi vĩnh viễn | Có thể publish DLQ trong function nếu hợp đồng cho phép | Có thể dùng DLQ/error channel của binder |
| Lỗi nguồn chung khiến toàn bộ stream không thể tiếp tục | Phục hồi ở phạm vi stream hoặc để lỗi thoát ra | Có thể restart/reconnect consumer theo cơ chế binder |

Chọn một tầng làm nơi chịu trách nhiệm retry chính cho từng loại lỗi. Nếu Reactor retry bốn lần tính cả lần đầu, binder cũng redeliver nhiều lần và broker còn có retry policy riêng, tổng số lần gọi dependency có thể tăng rất lớn. Cần tính ngân sách retry tổng thể và tránh các tầng retry lồng nhau không giới hạn.

## 11. Phục hồi lỗi khi ghép nhiều hàm

Một pipeline composition có thể gồm nhiều bước:

```text
orders.created
      |
      v
normalizeOrder
      |
      v
validateOrder
      |
      v
reserveInventory
      |
      v
orders.ready
```

Nếu một bước reactive phát lỗi và không phục hồi, lỗi có thể truyền qua composition và làm lần xử lý message thất bại. Có thể đặt `onErrorResume` trong từng bước nếu bước đó có một fallback hợp lệ, hoặc đặt một chính sách chung ở ranh giới xử lý một message.

Không nên đặt fallback ở cuối một `Flux` nhiều message nếu ý định chỉ là bỏ qua một message lỗi. Khi đó lỗi của một phần tử có thể kết thúc cả publisher tổng trước khi fallback được gọi. Hãy tạo publisher riêng cho mỗi message và xử lý lỗi bên trong publisher đó.

Nếu một bước có tác dụng phụ, chẳng hạn giữ hàng, cần thiết kế bù trừ hoặc idempotency. Ví dụ `reserveInventory` thành công nhưng bước thanh toán lỗi; retry cả pipeline có thể giữ hàng lần nữa. Có thể lưu trạng thái saga, dùng command có idempotency key và phát sự kiện bù trừ khi cần.

## 12. Retry phải an toàn với tác dụng phụ

Retry có nghĩa là một thao tác có thể được thực hiện nhiều lần. Trước khi dùng `retryWhen`, hãy xác định:

- Thao tác chỉ đọc hay có ghi dữ liệu?
- Lần đầu có thể đã thành công nhưng phản hồi bị timeout không?
- API đích có hỗ trợ idempotency key không?
- Database có unique constraint hoặc inbox để ngăn ghi trùng không?
- Có transaction nào bao trùm toàn bộ thao tác hay chỉ một phần?
- Khi retry hết giới hạn, trạng thái message và nghiệp vụ được lưu ở đâu?

Ví dụ, khi tạo yêu cầu thanh toán, dùng một idempotency key ổn định theo đơn hàng hoặc event ID:

```java
Mono<PaymentResult> authorize(OrderEvent event) {
    return paymentClient.authorize(
        event.orderId(),
        event.eventId() // idempotency key do hợp đồng API quy định
    );
}
```

Nếu payment client hỗ trợ idempotency, nhiều lần gọi cùng key có thể trả về cùng kết quả thay vì tạo nhiều giao dịch. Tên tham số và semantics thực tế phụ thuộc API thanh toán; không phải mọi dịch vụ đều hỗ trợ cơ chế này.

Với database, có thể ghi `eventId` vào inbox table và cập nhật trạng thái nghiệp vụ trong cùng transaction. Với luồng phát sự kiện sau khi ghi database, transactional outbox giúp đồng bộ việc lưu thay đổi và ghi lại event cần publish. Những mẫu này bổ sung cho retry; bản thân `retryWhen` không tạo bảo đảm exactly-once.

## 13. Timeout, backoff và giới hạn tải

Retry cần có giới hạn. Nếu mỗi lần gọi dependency có timeout 3 giây, retry ba lần cùng backoff có thể khiến một event tồn tại trong pipeline nhiều giây. Cần thiết kế timeout tổng thể cho một event và cân nhắc số event đồng thời.

Các biện pháp thường phối hợp:

- Đặt timeout cho từng lời gọi dependency bằng `timeout(Duration)`.
- Dùng backoff và jitter để tránh retry đồng loạt.
- Chỉ retry lỗi tạm thời; không retry lỗi dữ liệu hoặc quyền.
- Giới hạn concurrency của `flatMap` để không tạo quá nhiều request đồng thời.
- Dùng circuit breaker hoặc bulkhead khi dependency mất khả năng phục vụ kéo dài.
- Có deadline nghiệp vụ; nếu quá hạn, chuyển trạng thái hoặc cách ly thay vì giữ message vô thời hạn.

Ví dụ giới hạn concurrency:

```java
events.flatMap(event -> processOne(event), 16);
```

Giá trị `16` giới hạn số publisher con được subscribe đồng thời trong toán tử này. Nó không phải số partition, số instance hay số retry. Hãy chọn theo năng lực database, API và broker.

## 14. Kiểm thử `onErrorResume` và `retryWhen`

Kiểm thử reactive nên xác nhận số lần subscribe, kết quả fallback, phạm vi lỗi và việc lỗi có được truyền ra ngoài hay không. Reactor Test cung cấp `StepVerifier` để kiểm tra tín hiệu của publisher.

Ví dụ kiểm tra retry rồi thành công:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.time.Duration;
import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.Test;

import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;
import reactor.util.retry.Retry;

class RetryPolicyTest {

    @Test
    void retriesTransientFailureThenSucceeds() {
        AtomicInteger attempts = new AtomicInteger();

        Mono<String> source = Mono.defer(() -> {
            if (attempts.incrementAndGet() < 3) {
                return Mono.error(new TransientOrderDependencyException());
            }
            return Mono.just("accepted");
        });

        Mono<String> result = source.retryWhen(
            Retry.backoff(3, Duration.ofMillis(1))
                .maxBackoff(Duration.ofMillis(5))
                .filter(error -> error instanceof TransientOrderDependencyException)
        );

        StepVerifier.create(result)
            .expectNext("accepted")
            .verifyComplete();

        assertEquals(3, attempts.get());
    }
}
```

Các tình huống nên có trong test suite:

| Kịch bản | Điều cần xác minh |
|---|---|
| Lỗi tạm thời rồi thành công | `retryWhen` đăng ký lại publisher đúng số lần |
| Lỗi không được retry | Predicate `filter` từ chối retry và lỗi đi đến fallback hoặc caller |
| Hết số lần retry | Lỗi cuối cùng được phát ra hoặc chuyển theo `onRetryExhaustedThrow` |
| Lỗi nghiệp vụ đã biết | `onErrorResume` trả kết quả nghiệp vụ đúng |
| Một event lỗi trong nhiều event | Publisher của event đó được phục hồi; event khác vẫn được xử lý theo chính sách |
| Lỗi ở phạm vi Flux tổng | Xác nhận fallback toàn stream thay thế phần còn lại đúng như thiết kế |
| DLQ publish lỗi | Lỗi DLQ không bị nuốt và có thể được quan sát ở tầng ngoài |
| Retry lặp tác dụng phụ | Idempotency bảo đảm không tạo dữ liệu hoặc giao dịch trùng |
| Broker redelivery | Integration test xác nhận ack/retry/DLQ đúng với binder thật |

Unit test với `StepVerifier` xác nhận logic Reactor. Integration test với binder test hoặc broker thật mới xác nhận được cách Spring Cloud Stream và broker xử lý acknowledgement, redelivery, offset và DLQ.

## 15. Quan sát lỗi và retry trong production

Nên đo lường riêng các hoạt động sau:

- Số lần retry theo loại lỗi và dependency.
- Số event thành công sau retry và số event hết ngân sách retry.
- Số fallback nghiệp vụ như `REJECTED` hoặc `PENDING`.
- Số message được gửi đến DLQ và số lần DLQ publish thất bại.
- Thời gian xử lý một event, tổng thời gian retry và timeout.
- Consumer lag/backlog và tuổi message cũ nhất.
- Số lỗi thoát khỏi reactive function đến binder.

Log nên có `eventId`, `correlationId`, `orderId` hoặc định danh nghiệp vụ phù hợp, loại lỗi, số lần thử và tên dependency. Tránh ghi toàn bộ payload hoặc thông tin bí mật. Với metric, không dùng ID message tùy ý làm label vì cardinality có thể tăng không giới hạn.

Khi một message liên tục retry, cần biết nó đang retry trong Reactor, được binder redeliver hay đang nằm trong retry topic/queue. Nếu không phân biệt các tầng, việc điều tra có thể dẫn đến tăng retry ở nhiều nơi và làm tải hệ thống xấu hơn.

## 16. Quy trình chọn chính sách phục hồi

Khi thiết kế một reactive function trong Spring Cloud Stream:

1. Xác định lỗi có thể xảy ra ở bước nào: deserialize, validation, gọi dependency, ghi database hay publish output.
2. Phân loại lỗi thành lỗi nghiệp vụ, lỗi tạm thời và lỗi không thể phục hồi tự động.
3. Xác định phạm vi: một message, một bước trong composition hay toàn bộ Flux.
4. Dùng `retryWhen` quanh publisher của thao tác tạm thời và có thể lặp an toàn.
5. Dùng `onErrorResume` cho fallback có ý nghĩa nghiệp vụ, cách ly hoặc chuyển lỗi sang publisher khác.
6. Đặt retry trước fallback nếu muốn thử lại trước khi thay thế kết quả.
7. Bảo đảm thao tác có tác dụng phụ idempotent hoặc có transaction/outbox/inbox phù hợp.
8. Quyết định lỗi nào được truyền ra binder để áp dụng acknowledgement, retry hoặc DLQ ở tầng đó.
9. Đặt timeout, backoff, jitter, concurrency và ngân sách retry tổng thể.
10. Kiểm thử từng event lỗi, lỗi toàn stream, DLQ failure, redelivery và duplicate.
11. Theo dõi retry, fallback, DLQ, lag và thời gian phục hồi trong production.

## 17. Tự kiểm tra

- [ ] Giải thích được lỗi là tín hiệu kết thúc của `Mono`/`Flux`.
- [ ] Phân biệt được `onErrorResume` với `retryWhen`.
- [ ] Biết dùng `Retry.backoff`, `maxBackoff` và `filter` để giới hạn retry lỗi tạm thời.
- [ ] Giải thích được vì sao `Mono.defer` hữu ích quanh thao tác cần đăng ký lại.
- [ ] Phân biệt phục hồi bên trong publisher của từng message với phục hồi toàn `Flux`.
- [ ] Biết thứ tự `retryWhen` và `onErrorResume` làm thay đổi hành vi.
- [ ] Phân biệt Reactor retry với binder retry và broker redelivery.
- [ ] Nhận diện nguy cơ lặp tác dụng phụ và áp dụng idempotency.
- [ ] Thiết kế được fallback, DLQ, timeout, backoff và giới hạn concurrency.
- [ ] Kiểm thử được retry, fallback, phạm vi lỗi và hành vi acknowledgement thực tế.

## Kết luận

`onErrorResume` thay tín hiệu lỗi bằng một publisher dự phòng; `retryWhen` đăng ký lại publisher khi lỗi thỏa chính sách retry. Trong reactive function xử lý nhiều message, vị trí đặt các toán tử quyết định phạm vi phục hồi: đặt bên trong publisher của từng event để cô lập lỗi từng message, hoặc đặt ngoài chuỗi để phục hồi toàn stream khi đó là chủ đích. Retry phải có giới hạn, phân loại lỗi và thao tác idempotent. Đồng thời, cần phân biệt retry trong Reactor với retry/redelivery/acknowledgement của binder và broker; chỉ integration test trên binder phù hợp mới xác nhận được hành vi giao nhận thực tế.
