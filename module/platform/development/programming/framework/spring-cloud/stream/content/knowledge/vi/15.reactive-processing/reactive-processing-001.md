# Phân biệt hàm xử lý từng thông điệp với hàm nối các luồng dữ liệu

Trong Spring Cloud Stream, một hàm có thể xử lý từng message riêng lẻ hoặc làm việc với cả một luồng dữ liệu bất đồng bộ. Hai cách viết này trông khá giống nhau vì đều dùng `Supplier`, `Function` và `Consumer`, nhưng cách framework gọi hàm, cách dữ liệu đi qua ứng dụng và cách xử lý lỗi có những khác biệt quan trọng.

**Hàm xử lý từng thông điệp (imperative function)** nhận một payload hoặc một `Message<?>` cho mỗi lần gọi. **Hàm xử lý luồng (reactive function)** nhận một publisher như `Flux<T>` và trả về publisher khác để mô tả chuỗi xử lý dữ liệu liên tục. Spring Cloud Stream kết nối các hàm đó với binding và binder để truyền dữ liệu qua Kafka, RabbitMQ hoặc Pulsar.

Hiểu đúng hai mô hình giúp lựa chọn cách xử lý phù hợp với yêu cầu nghiệp vụ, tránh tạo subscription thủ công, kiểm soát backpressure và không nhầm một message chứa nhiều phần tử với một luồng message.

## 1. Hai cách nhìn về dữ liệu

Ở mô hình từng message, ứng dụng nhận một payload, xử lý rồi trả kết quả hoặc thực hiện tác dụng nghiệp vụ. Framework gọi hàm cho từng message được giao:

```text
Message A -> Function(A) -> Result A
Message B -> Function(B) -> Result B
Message C -> Function(C) -> Result C
```

Ở mô hình reactive, ứng dụng nhận một publisher đại diện cho chuỗi phần tử. Hàm được gọi để xây dựng pipeline xử lý; các toán tử mô tả cách mỗi phần tử được biến đổi, lọc, gom nhóm hoặc kết hợp:

```text
Flux<A, B, C, ...> -> Function(Flux) -> Flux<Result A, Result B, ...>
```

Sự khác biệt cốt lõi nằm ở kiểu đầu vào và vòng đời gọi hàm:

| Đặc điểm | Xử lý từng message | Xử lý luồng reactive |
|---|---|---|
| Kiểu đầu vào | `T` hoặc `Message<T>` | `Flux<T>` hoặc publisher tương ứng |
| Cách gọi hàm | Một lần cho mỗi message | Thường một lần để nhận publisher và xây dựng pipeline |
| Đơn vị xử lý | Một message | Một luồng gồm nhiều phần tử theo thời gian |
| Biến đổi | Xử lý trực tiếp payload | Dùng toán tử như `map`, `filter`, `flatMap`, `buffer`, `window` |
| Điều phối | Framework/binder gọi hàm theo từng lần giao message | Reactor điều phối subscription, tín hiệu và backpressure trong pipeline |
| Phù hợp với | Logic nghiệp vụ độc lập theo từng message | Luồng liên tục, biến đổi nhiều phần tử, xử lý theo nhóm hoặc kết hợp stream |

Một `Message<List<T>>` vẫn là một message có payload là danh sách. Nó khác với `Flux<T>`, vốn là một publisher có thể phát nhiều phần tử theo thời gian và có vòng đời subscription riêng.

## 2. Hàm xử lý từng message với Supplier, Function và Consumer

Trong mô hình imperative, các chữ ký hàm thường dùng là:

```java
Supplier<OrderCreated>
Function<OrderCreated, OrderEnriched>
Consumer<OrderCreated>
```

- `Supplier<T>` tạo một giá trị đầu ra mỗi lần được gọi. Với Spring Cloud Stream, supplier imperative thường được poll theo lịch để tạo message.
- `Function<T, R>` nhận một payload kiểu `T`, xử lý và trả một kết quả kiểu `R` cho message đó.
- `Consumer<T>` nhận một payload kiểu `T` và thực hiện tác dụng nghiệp vụ mà không tạo output binding từ giá trị trả về.

Ví dụ function xử lý một sự kiện đơn hàng:

```java
import java.util.function.Function;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class OrderFunctions {

    @Bean
    Function<OrderCreated, OrderEnriched> enrichOrder(
            CustomerDirectory customerDirectory) {
        return event -> new OrderEnriched(
            event.orderId(),
            customerDirectory.displayName(event.customerId()),
            event.totalAmount()
        );
    }
}

record OrderCreated(String orderId, String customerId, long totalAmount) {}
record OrderEnriched(String orderId, String customerName, long totalAmount) {}
```

Khi message đi vào `enrichOrder-in-0`, framework chuyển payload thành `OrderCreated` rồi gọi function. Kết quả `OrderEnriched` được gửi qua `enrichOrder-out-0`. Mỗi lần gọi function tương ứng với một message đầu vào.

Một consumer imperative phù hợp khi mỗi message cần cập nhật một bản ghi hoặc gọi một service:

```java
@Bean
Consumer<OrderCreated> updateOrderProjection(OrderProjectionService service) {
    return event -> service.apply(event);
}
```

Ở đây, `Consumer` không có output binding. Framework gọi consumer cho từng `OrderCreated` được giao. Nếu consumer ghi database, cần xác định thời điểm commit và ACK/offset, đồng thời làm cho thao tác an toàn khi message được giao lại.

## 3. Hàm reactive nhận và trả Flux

Với Reactor, `Flux<T>` biểu diễn một chuỗi có thể phát từ 0 đến nhiều phần tử. `Mono<T>` biểu diễn tối đa một phần tử. Spring Cloud Stream có thể kết nối reactive function với binding bằng các chữ ký như `Function<Flux<T>, Flux<R>>`.

Ví dụ biến đổi một luồng sự kiện:

```java
import java.util.function.Function;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import reactor.core.publisher.Flux;

@Configuration
class ReactiveOrderFunctions {

    @Bean
    Function<Flux<OrderCreated>, Flux<OrderEnriched>> enrichOrders() {
        return orders -> orders
            .filter(order -> order.totalAmount() > 0)
            .map(order -> new OrderEnriched(
                order.orderId(),
                order.customerId().toUpperCase(),
                order.totalAmount()
            ));
    }
}
```

Framework cung cấp một `Flux<OrderCreated>` cho function. Function trả về một `Flux<OrderEnriched>` mô tả pipeline biến đổi. Framework quản lý việc subscribe pipeline theo mô hình tích hợp của Spring Cloud Stream. Không gọi `subscribe()` bên trong function chỉ để làm cho pipeline chạy; tự subscribe có thể tách công việc khỏi vòng đời do framework quản lý, khiến lỗi và tín hiệu hoàn tất khó được phối hợp đúng.

Một reactive function thường được gọi một lần để thiết lập pipeline thay vì được gọi lại riêng cho từng message như imperative function. Các phần tử được xử lý khi publisher phát tín hiệu và subscriber yêu cầu dữ liệu.

## 4. Binding của hàm imperative và reactive

Tên binding được suy ra từ tên bean và hướng dữ liệu giống nhau ở cả hai mô hình. Khác biệt nằm ở kiểu payload mà hàm nhận và trả:

| Bean | Binding đầu vào | Binding đầu ra |
|---|---|---|
| `Function<OrderCreated, OrderEnriched> enrichOrder` | `enrichOrder-in-0` | `enrichOrder-out-0` |
| `Function<Flux<OrderCreated>, Flux<OrderEnriched>> enrichOrders` | `enrichOrders-in-0` | `enrichOrders-out-0` |
| `Consumer<OrderCreated> updateProjection` | `updateProjection-in-0` | Không có |

Ví dụ cấu hình reactive function:

```yaml
spring:
  cloud:
    function:
      definition: enrichOrders
    stream:
      bindings:
        enrichOrders-in-0:
          destination: orders.created
          group: order-enrichment
          content-type: application/json
        enrichOrders-out-0:
          destination: orders.enriched
          content-type: application/json
```

Binder nhận message từ destination `orders.created`, chuyển payload thành phần tử của luồng đầu vào và chuyển kết quả từ publisher đầu ra tới `orders.enriched`. Cách binder thực hiện nhận, xác nhận và điều phối message phụ thuộc broker và cấu hình cụ thể.

Không cần tạo một binding riêng cho từng phần tử trong `Flux`. Một binding đại diện cho luồng dữ liệu của function; các phần tử được phát qua publisher đó.

## 5. Nối các toán tử để xử lý luồng

Reactive function có thể ghép nhiều toán tử thành một pipeline. Một số toán tử thường dùng:

| Toán tử | Vai trò | Ví dụ sử dụng |
|---|---|---|
| `map` | Biến đổi từng phần tử đồng bộ. | Chuyển `OrderCreated` thành `OrderSummary`. |
| `filter` | Chỉ giữ phần tử thỏa điều kiện. | Bỏ sự kiện không có giá trị hợp lệ. |
| `flatMap` | Chuyển mỗi phần tử thành publisher khác và hợp nhất kết quả. | Gọi service reactive để làm giàu dữ liệu. |
| `concatMap` | Xử lý publisher con theo thứ tự, tuần tự. | Giữ thứ tự khi từng sự kiện cần hoàn tất trước sự kiện kế tiếp. |
| `buffer(n)` | Gom tối đa `n` phần tử thành một collection. | Ghi nhiều bản ghi theo lô. |
| `window(n)` | Chia luồng thành các luồng con. | Xử lý từng cửa sổ dữ liệu riêng. |
| `distinct` | Loại phần tử trùng theo tiêu chí được chọn. | Giảm phần tử lặp trong phạm vi pipeline. |
| `take(n)` | Chỉ lấy tối đa `n` phần tử đầu. | Giới hạn dữ liệu trong một tác vụ hữu hạn. |

Ví dụ kết hợp lọc, làm giàu bất đồng bộ và gom nhóm:

```java
Function<Flux<OrderCreated>, Flux<List<OrderEnriched>>> enrichInBatches = orders ->
    orders
        .filter(order -> order.totalAmount() > 0)
        .flatMap(order -> customerClient.findCustomer(order.customerId())
            .map(customer -> new OrderEnriched(
                order.orderId(), customer.name(), order.totalAmount()
            )))
        .buffer(50);
```

Trong ví dụ, mỗi phần tử hợp lệ được làm giàu qua một lời gọi reactive, sau đó tối đa 50 kết quả được gom thành một danh sách. Kiểu đầu ra lúc này là `Flux<List<OrderEnriched>>`, không còn là `Flux<OrderEnriched>`. Consumer phía sau cần hiểu rằng mỗi message đầu ra có thể mang một danh sách thay vì một sự kiện đơn lẻ.

`flatMap` cho phép các thao tác bất đồng bộ chạy chồng lấp nên thứ tự kết quả có thể khác thứ tự đầu vào. Nếu cần giữ thứ tự, cân nhắc `concatMap` hoặc `flatMapSequential` và đánh giá ảnh hưởng throughput.

## 6. Backpressure và điều tiết tốc độ

Backpressure là cơ chế cho phép subscriber báo cho publisher số phần tử mà nó sẵn sàng nhận. Trong Reactor, subscriber có thể yêu cầu dữ liệu theo nhu cầu thay vì buộc publisher phát toàn bộ dữ liệu ngay lập tức.

Backpressure hữu ích khi tốc độ phát dữ liệu lớn hơn tốc độ xử lý. Các toán tử như `limitRate`, `buffer`, `onBackpressureBuffer` hoặc `onBackpressureDrop` có thể điều chỉnh cách pipeline phản ứng với chênh lệch tốc độ, nhưng mỗi lựa chọn có hệ quả khác nhau:

- `limitRate` điều chỉnh lượng yêu cầu upstream theo từng đợt.
- `buffer` giữ dữ liệu trong bộ nhớ cho tới khi đủ phần tử hoặc điều kiện phát buffer được đáp ứng.
- `onBackpressureBuffer` giữ các phần tử chờ xử lý, nhưng cần giới hạn dung lượng để tránh tăng bộ nhớ vô hạn.
- `onBackpressureDrop` loại phần tử khi downstream không theo kịp; chỉ phù hợp khi nghiệp vụ cho phép mất các phần tử bị loại.

Ví dụ giới hạn số phần tử được yêu cầu theo từng đợt:

```java
Function<Flux<OrderCreated>, Flux<OrderCreated>> controlledOrders = orders ->
    orders.limitRate(100);
```

Backpressure trong Reactor không đồng nghĩa broker tự động dừng publish hoặc mọi binder đều chuyển demand theo cùng cách tới broker. Một số binder dùng cơ chế polling, prefetch, buffer nội bộ hoặc acknowledgement riêng. Vì vậy, cần hiểu giới hạn ở cả pipeline Reactor lẫn broker: queue depth, consumer lag, prefetch, số partition và tốc độ producer.

## 7. Không chặn luồng reactive bằng API blocking

Một pipeline reactive chỉ có lợi khi các thao tác trong đó không giữ thread chờ I/O một cách không cần thiết. Nếu gọi JDBC đồng bộ, `RestTemplate`, `Thread.sleep()` hoặc một API blocking trong `map`, thread thực thi có thể bị giữ cho tới khi thao tác hoàn tất.

Nếu có client reactive, hãy kết hợp publisher bằng `flatMap`:

```java
Function<Flux<OrderCreated>, Flux<OrderEnriched>> enrichReactively = orders ->
    orders.flatMap(order ->
        customerWebClient.getCustomer(order.customerId())
            .map(customer -> new OrderEnriched(
                order.orderId(), customer.name(), order.totalAmount()
            ))
    );
```

Nếu bắt buộc gọi API blocking, cần cô lập thao tác đó trên scheduler phù hợp và giới hạn concurrency. Ví dụ dưới đây minh họa kỹ thuật Reactor; cần chọn scheduler và giới hạn theo tải thực tế:

```java
import reactor.core.scheduler.Schedulers;

Function<Flux<OrderCreated>, Flux<OrderEnriched>> enrichBlocking = orders ->
    orders.flatMap(order ->
        reactor.core.publisher.Mono.fromCallable(() ->
            blockingCustomerService.load(order.customerId())
        )
        .subscribeOn(Schedulers.boundedElastic())
        .map(customer -> new OrderEnriched(
            order.orderId(), customer.name(), order.totalAmount()
        )),
        8
    );
```

Giới hạn concurrency ở `flatMap` giúp không tạo quá nhiều tác vụ blocking cùng lúc. Tuy nhiên, dùng scheduler không biến API blocking thành API reactive thực sự; cần theo dõi thread, queue và timeout.

## 8. Supplier imperative và Supplier reactive

Supplier imperative như `Supplier<OrderCreated>` thường được gọi theo poller để tạo từng message. Ngược lại, `Supplier<Flux<OrderCreated>>` trả về một publisher có thể phát nhiều phần tử.

```java
@Bean
Supplier<Flux<OrderCreated>> orderEvents(OrderEventService service) {
    return service::liveEvents;
}
```

Với reactive supplier liên tục, framework thường lấy publisher và subscribe theo vòng đời binding; supplier không được gọi lại mỗi giây như supplier imperative chỉ vì có default poller. Nếu publisher là luồng liên tục, việc tạo nhiều subscription lặp lại có thể gây đọc trùng hoặc tiêu tốn tài nguyên.

Nếu supplier reactive trả về một luồng hữu hạn và cần được poll định kỳ, Spring Cloud Function cung cấp `@PollableBean` để đánh dấu supplier reactive cần được poll:

```java
import java.util.function.Supplier;

import org.springframework.cloud.function.context.PollableBean;
import reactor.core.publisher.Flux;

@PollableBean
Supplier<Flux<OrderCreated>> pendingOrders(OrderEventService service) {
    return () -> Flux.fromIterable(service.findPendingOrders());
}
```

Khi dùng `@PollableBean`, cần hiểu cấu hình poller, cách tách phần tử và trạng thái nguồn. Nếu nguồn trả lại cùng một danh sách ở lần poll tiếp theo, message có thể bị phát lặp. Cần claim hoặc đánh dấu dữ liệu một cách an toàn và thiết kế consumer idempotent.

## 9. Xử lý lỗi trong pipeline reactive

Lỗi trong pipeline reactive được truyền dưới dạng tín hiệu `onError`. Khi một toán tử phát sinh exception, pipeline có thể kết thúc trừ khi lỗi được xử lý bằng toán tử phù hợp.

Một số cách xử lý:

- `onErrorMap`: chuyển lỗi sang kiểu exception có ý nghĩa hơn.
- `onErrorResume`: chuyển sang publisher dự phòng hoặc luồng phục hồi.
- `onErrorContinue`: bỏ qua một phần tử gây lỗi và tiếp tục trong những trường hợp toán tử hỗ trợ; cần thận trọng vì có thể che lỗi dữ liệu.
- `retry`/`retryWhen`: đăng ký lại publisher theo chính sách thử lại.

Ví dụ retry một thao tác tra cứu có thể gặp lỗi tạm thời:

```java
Function<Flux<OrderCreated>, Flux<OrderEnriched>> enrichWithRetry = orders ->
    orders.flatMap(order ->
        customerWebClient.getCustomer(order.customerId())
            .map(customer -> new OrderEnriched(
                order.orderId(), customer.name(), order.totalAmount()
            ))
            .retryWhen(reactor.util.retry.Retry.backoff(3, java.time.Duration.ofMillis(200)))
    );
```

Retry ở tầng Reactor là retry thao tác publisher trong pipeline. Nó khác với retry/redelivery do binder hoặc broker quản lý. Nếu toàn bộ function thất bại, cách message được xác nhận, giao lại hoặc chuyển DLQ phụ thuộc binder và cấu hình. Không nên xếp chồng nhiều tầng retry mà không tính tổng số lần thử và thời gian chờ.

Phân biệt lỗi tạm thời với lỗi dữ liệu không thể sửa bằng retry. Message sai schema hoặc vi phạm hợp đồng thường cần xử lý theo error channel/DLQ, thay vì retry liên tục.

## 10. Thứ tự và tính đồng thời trong reactive stream

Reactive pipeline có thể xử lý nhiều phần tử đồng thời. Các toán tử `flatMap` và `parallel` có thể tăng throughput, nhưng kết quả có thể hoàn tất không theo thứ tự đầu vào. `concatMap` tuần tự hóa các publisher con; `flatMapSequential` cho phép thực hiện đồng thời nhưng phát kết quả theo thứ tự nguồn.

Chọn toán tử theo yêu cầu nghiệp vụ:

| Yêu cầu | Toán tử gợi ý | Đánh đổi |
|---|---|---|
| Biến đổi đồng bộ từng phần tử | `map` | Không tạo concurrency I/O. |
| Gọi nhiều dịch vụ reactive song song | `flatMap` | Có thể thay đổi thứ tự kết quả; cần giới hạn concurrency. |
| Xử lý bất đồng bộ nhưng phát theo thứ tự nguồn | `flatMapSequential` | Có thể phải giữ kết quả hoàn tất sớm trong bộ đệm. |
| Xử lý tuần tự từng phần tử | `concatMap` | Giữ thứ tự nhưng throughput có thể thấp hơn. |

Thứ tự của một Flux trong ứng dụng cũng không tự mở rộng bảo đảm thứ tự của broker. Kafka chỉ bảo đảm thứ tự trong partition; RabbitMQ và Pulsar có quy tắc riêng theo queue/subscription. Nếu function chạy nhiều partition hoặc consumer, cần xác định phạm vi thứ tự mà nghiệp vụ yêu cầu.

## 11. Message, batch và stream không phải một khái niệm

Các cách biểu diễn sau có ý nghĩa khác nhau:

| Kiểu | Ý nghĩa |
|---|---|
| `OrderCreated` | Một payload nghiệp vụ. |
| `Message<OrderCreated>` | Một message gồm payload và headers. |
| `List<OrderCreated>` | Một collection nằm trong một đối tượng/payload. |
| `Message<List<OrderCreated>>` | Một message có payload là collection. |
| `Flux<OrderCreated>` | Publisher phát nhiều phần tử theo thời gian. |
| `Flux<Message<OrderCreated>>` | Publisher phát các message, mỗi message có payload và headers riêng. |

Nếu binder giao một message có payload là danh sách, function imperative có thể nhận `List<OrderCreated>` và xử lý một batch trong một lần gọi. Nếu function nhận `Flux<OrderCreated>`, framework đang cung cấp một publisher gồm nhiều phần tử. Không nên suy ra rằng bật batch mode sẽ tự biến chữ ký `Function<T,R>` thành `Function<Flux<T>,Flux<R>>`; batch mode và reactive processing là hai lựa chọn mô hình khác nhau.

## 12. Khi nào nên chọn từng mô hình?

Chọn hàm imperative khi mỗi message là một đơn vị nghiệp vụ độc lập, logic đơn giản, cần kiểm soát rõ ràng việc xử lý từng message hoặc team chưa cần pipeline reactive. Mô hình này dễ đọc, dễ debug và phù hợp với phần lớn consumer xử lý CRUD, cập nhật projection hoặc thực hiện một tác vụ riêng lẻ.

Chọn reactive function khi bài toán thực sự cần xử lý chuỗi dữ liệu: biến đổi nhiều phần tử, gọi nhiều dịch vụ reactive, lọc, gom nhóm, kết hợp luồng hoặc điều tiết tốc độ bằng backpressure. Reactive model có thể giảm chi phí thread khi I/O bất đồng bộ và pipeline được thiết kế đúng.

Không nên chuyển mọi function sang reactive chỉ để dùng `Flux`. Nếu xử lý chỉ gồm một thao tác đồng bộ cho từng message, `Function<T,R>` hoặc `Consumer<T>` thường đơn giản hơn. Reactive code có thêm khái niệm subscription, demand, cancellation, scheduler và error signal; chỉ nên dùng khi những khả năng này mang lại giá trị thực tế.

## 13. Kiểm thử imperative và reactive function

Imperative function có thể kiểm thử bằng cách gọi trực tiếp hàm với một payload:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.function.Function;

import org.junit.jupiter.api.Test;

// Dùng cùng các record OrderCreated và OrderEnriched đã khai báo ở trên.
class ImperativeFunctionTest {

    private final Function<OrderCreated, OrderEnriched> function = event ->
        new OrderEnriched(event.orderId(), event.customerId(), event.totalAmount());

@Test
void enrichesOneOrder() {
    OrderCreated input = new OrderCreated("order-1", "customer-1", 500);

    OrderEnriched result = function.apply(input);

    assertEquals("order-1", result.orderId());
}
}
```

Reactive function nên được kiểm thử bằng Reactor Test (`StepVerifier`) để xác minh các phần tử, thứ tự, completion và lỗi:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.function.Function;

import org.junit.jupiter.api.Test;
import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

// Dùng cùng các record OrderCreated và OrderEnriched đã khai báo ở trên.
class ReactiveFunctionTest {

    private final Function<Flux<OrderCreated>, Flux<OrderEnriched>> reactiveFunction =
        orders -> orders.map(order -> new OrderEnriched(
            order.orderId(), order.customerId(), order.totalAmount()
        ));

@Test
void transformsOrderStream() {
    Flux<OrderCreated> input = Flux.just(
        new OrderCreated("order-1", "customer-1", 100),
        new OrderCreated("order-2", "customer-2", 200)
    );

    Flux<OrderEnriched> output = reactiveFunction.apply(input);

    StepVerifier.create(output)
        .expectNextMatches(order -> order.orderId().equals("order-1"))
        .expectNextMatches(order -> order.orderId().equals("order-2"))
        .verifyComplete();
}
}
```

Các kiểm thử khác nên xác minh:

- Luồng rỗng có hoàn tất đúng không.
- Phần tử không hợp lệ được lọc, chuyển lỗi hoặc phục hồi đúng hợp đồng.
- `flatMap` có giới hạn concurrency phù hợp.
- Thứ tự được giữ khi nghiệp vụ yêu cầu.
- Cancellation và timeout không để lại subscription hoặc tài nguyên treo.
- Binding chuyển đổi đúng payload và header khi dùng Test Binder.

Test Binder giúp kiểm thử tích hợp binding trong phạm vi ứng dụng, nhưng không mô phỏng đầy đủ backpressure, partition assignment, ACK và mọi đặc tính broker. Với bảo đảm phụ thuộc Kafka, RabbitMQ hoặc Pulsar, cần kiểm thử tích hợp bằng binder/broker tương ứng.

## 14. Quan sát pipeline reactive khi vận hành

Ngoài metric broker, cần theo dõi thời gian xử lý từng phần tử, tốc độ phát/tiêu thụ, số phần tử đang được buffer, lỗi theo loại, số lần retry và độ trễ từ lúc message được nhận tới khi output được gửi. Với pipeline có `flatMap`, cần theo dõi số tác vụ đồng thời và thời gian chờ dịch vụ phụ thuộc.

Gắn `eventId` và `correlationId` vào log/trace để liên kết các chặng. Tránh log toàn bộ payload nhạy cảm. Nếu backlog tăng dù CPU thấp, có thể downstream I/O đang chậm hoặc demand bị giới hạn. Nếu bộ nhớ tăng, kiểm tra buffer không giới hạn, `collectList()` trên luồng dài hạn hoặc các publisher không được giải phóng.

Không dùng `block()` hoặc `subscribe()` tùy tiện bên trong function để “lấy kết quả ngay”. Những lời gọi này có thể phá vỡ mô hình điều phối reactive, gây deadlock hoặc tách lỗi khỏi binder. Hãy để dữ liệu tiếp tục đi qua publisher và các toán tử composition.

## 15. Quy trình lựa chọn mô hình

Trước khi viết một hàm xử lý trong Spring Cloud Stream, hãy trả lời:

1. Hàm cần xử lý từng payload độc lập hay cần nhìn thấy cả luồng dữ liệu?
2. Một lần gọi hàm nên tạo đúng một kết quả, không kết quả hay nhiều kết quả?
3. Có cần lọc, gom nhóm, kết hợp hoặc điều tiết tốc độ giữa các phần tử không?
4. Các dịch vụ phụ thuộc có API reactive hay chỉ có API blocking?
5. Có yêu cầu giữ thứ tự theo partition, key hoặc entity không?
6. Backpressure, buffering và giới hạn concurrency được kiểm soát ở đâu?
7. Lỗi trong một phần tử có làm hỏng toàn bộ pipeline hay cần phục hồi riêng?
8. Binder đang dùng hỗ trợ hành vi giao nhận và reactive integration nào?
9. Test nào xác minh được payload, completion, lỗi và đặc tính broker cần thiết?

Nếu câu trả lời chỉ yêu cầu xử lý một message tại một thời điểm, hãy bắt đầu với `Function<T,R>` hoặc `Consumer<T>`. Nếu bài toán cần nối và điều phối một chuỗi phần tử bất đồng bộ, dùng `Function<Flux<T>, Flux<R>>` và các toán tử Reactor phù hợp. Lựa chọn dựa trên hình dạng dữ liệu và yêu cầu xử lý sẽ giúp ứng dụng rõ ràng, dễ kiểm thử và vận hành ổn định hơn.
