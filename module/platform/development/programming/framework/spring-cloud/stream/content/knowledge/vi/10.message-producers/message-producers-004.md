# Supplier trả một phần tử và Supplier trả luồng Flux

Trong Spring Cloud Stream, `Supplier` là nguồn phát dữ liệu cho binding đầu ra. Có hai cách phổ biến để xây dựng nguồn này: trả về một giá trị cho mỗi lần được gọi bằng `Supplier<T>`, hoặc trả về một publisher phát nhiều giá trị bằng `Supplier<Flux<T>>`. Hai chữ ký đều tạo binding đầu ra theo tên bean, nhưng cơ chế kích hoạt và vòng đời phát dữ liệu khác nhau.

`Supplier<T>` phù hợp khi ứng dụng có thể tạo một sự kiện tại mỗi lần được poller gọi. `Supplier<Flux<T>>` phù hợp khi nguồn dữ liệu tự nhiên là một luồng reactive, có thể phát nhiều phần tử theo thời gian và hỗ trợ xử lý bất đồng bộ. Chọn đúng kiểu giúp kiểm soát nhịp phát, tài nguyên và cách xử lý lỗi khi triển khai.

## 1. Supplier là nguồn của binding đầu ra

Spring Cloud Function nhận diện bean hàm theo các kiểu hàm chuẩn của Java. Với `Supplier<T>`, hàm không nhận đầu vào và tạo ra giá trị đầu ra. Spring Cloud Stream kết nối giá trị đó với binding đầu ra của ứng dụng.

Ví dụ bean có tên `orderEventSupplier`:

```java
import java.time.Instant;
import java.util.UUID;
import java.util.function.Supplier;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

public record OrderCreated(String orderId, Instant createdAt) {}

@Configuration
public class OrderEventSources {

    @Bean
    public Supplier<OrderCreated> orderEventSupplier() {
        return () -> new OrderCreated(
                "ORD-" + UUID.randomUUID(),
                Instant.now()
        );
    }
}
```

Tên binding đầu ra mặc định là:

```text
orderEventSupplier-out-0
```

Tên binding được hình thành từ tên bean và hướng `out`, với index đầu tiên là `0`. Kiểu trả về `OrderCreated` xác định payload mà hàm tạo ra. Tên binding không phụ thuộc payload là record, chuỗi hay kiểu Java khác.

## 2. Supplier trả một phần tử: Supplier<T>

Với `Supplier<T>`, mỗi lần gọi `get()` tạo ra một giá trị `T`. Trong mô hình nguồn phát thông thường của Spring Cloud Stream, framework dùng poller để gọi supplier theo chu kỳ. Giá trị trả về được chuyển đổi thành message và gửi qua binding đầu ra.

Có thể hình dung luồng xử lý như sau:

```mermaid
flowchart LR
    A[Poller đến chu kỳ] --> B[Gọi Supplier.get()]
    B --> C[Tạo một object T]
    C --> D[Chuyển đổi thành Message]
    D --> E[Binding out-0]
    E --> F[Binder]
    F --> G[Destination trên broker]
```

Supplier không tự tạo thread hoặc bộ lập lịch riêng trong ví dụ thông thường. Poller quản lý thời điểm gọi. Cấu hình mặc định của poller có khoảng cách giữa các lần poll là 1.000 ms và số message tối đa mỗi lần poll là 1. Với một supplier trả đúng một object, mỗi lần gọi tạo một sự kiện.

### Cấu hình chu kỳ poll

Ví dụ cấu hình binding và poller:

```yaml
spring:
  cloud:
    function:
      definition: orderEventSupplier
    stream:
      poller:
        initial-delay: 1000
        fixed-delay: 5000
        max-messages-per-poll: 1
      bindings:
        orderEventSupplier-out-0:
          destination: orders.created
          content-type: application/json
```

Trong ví dụ:

- `initial-delay` đặt thời gian chờ trước lần poll đầu tiên, tính bằng mili giây.
- `fixed-delay` đặt khoảng nghỉ giữa các lần poll, tính bằng mili giây.
- `max-messages-per-poll` giới hạn số message được tạo trong một lần poll.
- `destination` là tài nguyên nhận sự kiện trên broker.
- `content-type` khai báo định dạng payload đầu ra; `application/json` cho phép framework chuyển record thành JSON khi dùng cơ chế chuyển đổi thông thường.

Các thuộc tính poller ở trên là cấu hình chung của poller trong ứng dụng. Nếu nhiều supplier cùng được kích hoạt, cần xem xét tác động của cấu hình chung và nhu cầu nhịp phát của từng nguồn. Không đặt `fixed-delay` quá thấp nếu việc tạo hoặc gửi message tiêu tốn nhiều tài nguyên hơn khả năng xử lý của broker.

### Khi nào nên dùng Supplier<T>?

Kiểu này phù hợp với các nguồn phát có nhịp đều và mỗi lần gọi có thể tạo một sự kiện độc lập, chẳng hạn:

- Phát snapshot trạng thái dịch vụ theo chu kỳ.
- Tạo sự kiện tổng hợp theo lịch.
- Đọc một bản ghi từ nguồn dữ liệu mỗi lần poll.
- Phát tín hiệu kiểm tra sức khỏe hoặc số liệu định kỳ.

Supplier nên tạo giá trị mới hoặc giá trị đại diện cho trạng thái hiện tại tại thời điểm được gọi. Tránh trả lại cùng một object mutable rồi thay đổi object đó sau khi đã phát, vì message đã gửi có thể chia sẻ tham chiếu với mã ứng dụng.

## 3. Supplier trả luồng: Supplier<Flux<T>>

`Flux<T>` là một publisher của Project Reactor có thể phát không, một hoặc nhiều phần tử theo thời gian. Khi bean khai báo `Supplier<Flux<T>>`, supplier trả về publisher thay vì một object đơn lẻ.

Ví dụ tạo một sự kiện mới mỗi hai giây:

```java
import java.time.Duration;
import java.time.Instant;
import java.util.function.Supplier;

import reactor.core.publisher.Flux;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

public record MetricSample(long sequence, Instant capturedAt) {}

@Configuration
public class MetricEventSources {

    @Bean
    public Supplier<Flux<MetricSample>> metricStream() {
        return () -> Flux.interval(Duration.ofSeconds(2))
                .map(sequence -> new MetricSample(sequence, Instant.now()));
    }
}
```

Binding đầu ra mặc định là:

```text
metricStream-out-0
```

Điểm khác biệt quan trọng: với supplier trả về reactive type, Spring Cloud Function gọi supplier để lấy publisher rồi đăng ký subscription vào publisher đó. Supplier reactive không được gọi lặp lại theo poller cho từng phần tử như `Supplier<T>`. Publisher chịu trách nhiệm phát các phần tử tiếp theo. Vì vậy, `fixed-delay` của poller không điều khiển nhịp từng phần tử do `Flux` phát ra.

Với `Flux.interval(Duration.ofSeconds(2))`, publisher tự phát một số tuần tự theo chu kỳ hai giây. Hàm `map` chuyển từng số thành `MetricSample`. Mỗi phần tử đi qua binding đầu ra như một message riêng.

### Cấu hình binding cho Flux

```yaml
spring:
  cloud:
    function:
      definition: metricStream
    stream:
      bindings:
        metricStream-out-0:
          destination: metrics.samples
          content-type: application/json
```

Không cần cấu hình poller để tạo chu kỳ hai giây trong ví dụ này. Nhịp phát đã được thể hiện trong `Flux.interval`. Nếu thay đổi thời gian phát, sửa `Duration` hoặc áp dụng toán tử Reactor phù hợp.

## 4. So sánh hai kiểu Supplier

| Đặc điểm | `Supplier<T>` | `Supplier<Flux<T>>` |
| --- | --- | --- |
| Giá trị supplier trả về | Một object `T` mỗi lần gọi | Một publisher `Flux<T>` |
| Cơ chế phát | Poller gọi supplier theo chu kỳ | Supplier được gọi để lấy publisher; subscription nhận các phần tử do publisher phát |
| Điều khiển nhịp | `fixed-delay`, `initial-delay`, `max-messages-per-poll` | Toán tử hoặc nguồn phát của Reactor, ví dụ `interval`, `delayElements` |
| Số phần tử | Thông thường một phần tử cho mỗi lần gọi | Không, một hoặc nhiều phần tử trong một subscription |
| Hoàn tất | Kết thúc sau khi gửi giá trị của lần poll | Publisher có thể hoàn tất hoặc tiếp tục chạy |
| Phù hợp với | Nguồn dữ liệu được lấy theo chu kỳ | Nguồn dữ liệu liên tục hoặc bất đồng bộ |

Hai kiểu vẫn dùng chung quy ước binding đầu ra `<function>-out-0`. Sự khác biệt nằm ở kiểu trả về và vòng đời phát dữ liệu, không nằm ở tên binding.

## 5. Flux hữu hạn và Flux vô hạn

Một `Flux` có thể phát một số lượng hữu hạn phần tử rồi hoàn tất:

```java
@Bean
public Supplier<Flux<String>> startupEvents() {
    return () -> Flux.just(
            "SERVICE_STARTED",
            "CACHE_READY",
            "CONSUMER_READY"
    );
}
```

Publisher `Flux.just` phát ba giá trị rồi gửi tín hiệu hoàn tất (`onComplete`). Sau khi publisher hoàn tất, subscription đó kết thúc. Framework không tự động gọi lại supplier theo chu kỳ poller chỉ vì Flux đã hoàn tất. Nếu cần phát lại một chuỗi hữu hạn, phải thiết kế việc lặp lại rõ ràng bằng toán tử Reactor như `repeat`, hoặc tạo một publisher mới theo cơ chế phù hợp với vòng đời ứng dụng.

Một `Flux` vô hạn có thể tiếp tục phát cho tới khi subscription bị hủy hoặc publisher gặp lỗi:

```java
@Bean
public Supplier<Flux<Long>> heartbeat() {
    return () -> Flux.interval(Duration.ofSeconds(10));
}
```

Nguồn heartbeat này không hoàn tất tự nhiên. Khi ứng dụng dừng, subscription cần được hủy để publisher và tài nguyên liên quan ngừng hoạt động. Các toán tử nguồn như `interval` quản lý scheduler của Reactor; với nguồn tự tạo kết nối hoặc tài nguyên bên ngoài, cần thiết kế giải phóng tài nguyên khi bị hủy.

## 6. Cold publisher và hot publisher

Khi xây dựng `Supplier<Flux<T>>`, cần hiểu nguồn phát là cold hay hot:

- **Cold publisher** thường tạo dữ liệu riêng cho mỗi subscription. `Flux.just`, `Flux.fromIterable` và `Flux.interval` là những ví dụ thường gặp. Khi có subscription mới, publisher bắt đầu phát theo định nghĩa của nó.
- **Hot publisher** phát dữ liệu độc lập với từng subscriber. Một subscriber đến muộn có thể không nhận các sự kiện đã phát trước đó. Nguồn callback, cảm biến hoặc event bus có thể có đặc tính hot.

Spring Cloud Stream thường đăng ký subscription cho publisher được supplier trả về trong vòng đời binding. Vì thế, cần chọn publisher phù hợp với cách ứng dụng muốn quản lý subscriber. Nếu dùng hot source, phải xem xét thời điểm bắt đầu phát, buffering, chính sách khi chưa có subscriber và cách xử lý khi subscriber bị hủy.

Không nên tạo hot source toàn cục trong một static field rồi giả định mọi instance ứng dụng đều nhận đủ mọi sự kiện. Khi chạy nhiều instance, mỗi instance có thể có một nguồn phát riêng; nếu nguồn bên ngoài không chia sẻ hoặc không phân vùng, hệ thống có thể phát trùng hoặc mất dữ liệu theo thiết kế nguồn.

## 7. Kết hợp Flux với các toán tử Reactor

Reactor cung cấp các toán tử để điều khiển dữ liệu trước khi message đi vào binding đầu ra.

### Biến đổi từng phần tử

```java
@Bean
public Supplier<Flux<String>> normalizedCodes() {
    return () -> Flux.just(" ab-01 ", "cd-02 ", " ef-03 ")
            .map(String::trim)
            .map(String::toUpperCase);
}
```

`map` biến đổi từng phần tử đồng bộ. Mỗi chuỗi sau biến đổi được phát như một phần tử của Flux.

### Lọc phần tử

```java
@Bean
public Supplier<Flux<Integer>> validMeasurements() {
    return () -> Flux.range(1, 20)
            .filter(value -> value % 2 == 0);
}
```

`filter` chỉ giữ phần tử thỏa điều kiện. Các giá trị bị lọc không được gửi tới binding.

### Giới hạn và gom nhóm

```java
import java.util.List;

@Bean
public Supplier<Flux<List<Integer>>> measurementBatches() {
    return () -> Flux.range(1, 100)
            .buffer(10);
}
```

`buffer(10)` gom các phần tử thành danh sách tối đa mười giá trị. Lúc này payload của mỗi message đầu ra là một danh sách, không còn là một số nguyên riêng lẻ. Consumer cần hiểu đúng schema mới.

### Gọi dịch vụ bất đồng bộ

```java
@Bean
public Supplier<Flux<OrderSummary>> orderSummaries() {
    return () -> Flux.fromIterable(loadPendingOrderIds())
            .flatMap(this::loadSummaryAsync, 8);
}
```

Ví dụ này minh họa `flatMap` với giới hạn tám tác vụ đồng thời. Trong ứng dụng thực tế, `loadPendingOrderIds` và `loadSummaryAsync` phải được cung cấp bởi bean phù hợp. Giới hạn concurrency giúp kiểm soát số yêu cầu đồng thời và áp lực lên dịch vụ phụ thuộc.

## 8. Backpressure và tốc độ phát

Reactive Streams có cơ chế backpressure để subscriber yêu cầu dữ liệu theo khả năng xử lý. Tuy nhiên, không phải mọi nguồn phát đều có thể tạm dừng. Ví dụ, `Flux.interval` có nhịp đồng hồ riêng; nếu downstream không theo kịp, Reactor có thể báo lỗi overflow theo chính sách của nguồn thay vì lưu vô hạn mọi phần tử.

Khi thiết kế nguồn Flux:

- Chọn tốc độ phát phù hợp với khả năng ghi của binder và broker.
- Dùng buffer có giới hạn nếu cần hấp thụ dao động ngắn hạn; xác định rõ hành vi khi buffer đầy.
- Giới hạn concurrency khi gọi dịch vụ bên ngoài bằng `flatMap`.
- Tránh `block()` trong chuỗi reactive vì thao tác này có thể chặn thread xử lý.
- Theo dõi độ trễ, tốc độ phát, số lỗi và lượng dữ liệu bị buffer hoặc loại bỏ.

Backpressure của Reactor không đồng nghĩa broker sẽ lưu message vô hạn. Cách binder yêu cầu và truyền dữ liệu xuống producer phụ thuộc implementation, cấu hình và broker. Cần kiểm thử tải với binder thực tế để xác định giới hạn throughput và hành vi khi broker chậm.

## 9. Xử lý lỗi trong Supplier và Flux

Với `Supplier<T>`, lỗi có thể xảy ra khi poller gọi supplier, ví dụ nguồn dữ liệu không truy cập được hoặc phép tính phát sinh exception. Với `Supplier<Flux<T>>`, lỗi có thể xảy ra khi tạo publisher hoặc trong lúc publisher đang phát phần tử.

Một số toán tử Reactor hỗ trợ xử lý lỗi:

```java
import java.time.Duration;

@Bean
public Supplier<Flux<String>> resilientSource() {
    return () -> readEvents()
            .retryWhen(reactor.util.retry.Retry.backoff(3, Duration.ofSeconds(1)))
            .onErrorResume(error -> {
                log.error("Event source stopped", error);
                return Flux.empty();
            });
}
```

Đoạn mã minh họa thử lại tối đa ba lần với backoff trước khi chuyển sang Flux rỗng. `readEvents()` và `log` đại diện cho các thành phần ứng dụng cần được cung cấp. Nếu dùng `onErrorResume` để trả về `Flux.empty()`, publisher sẽ hoàn tất sau khi lỗi được xử lý; nguồn không tự tiếp tục vô hạn. Hãy chọn hành vi fallback theo yêu cầu nghiệp vụ và không âm thầm bỏ mất sự kiện.

Retry ở cấp publisher, retry của Spring Cloud Stream và retry hoặc redelivery của broker là các cơ chế khác nhau. Cấu hình retry cho consumer không tự động bảo đảm nguồn Supplier sẽ phát lại dữ liệu đã lỗi khi gửi. Với nguồn dữ liệu quan trọng, cần thiết kế lưu trạng thái, xác nhận, phát lại và idempotency rõ ràng.

## 10. Kiểm soát trùng lặp và bảo đảm giao nhận

Supplier có thể phát lại cùng một dữ liệu khi ứng dụng khởi động lại, retry hoặc chạy nhiều instance. Vì vậy, không nên giả định mỗi sự kiện chỉ được phát đúng một lần.

Một số biện pháp thực tế:

1. Tạo event ID ổn định từ nguồn nghiệp vụ để consumer nhận diện message trùng.
2. Dùng outbox hoặc một nguồn dữ liệu có checkpoint nếu cần bảo đảm sự kiện không bị mất giữa cập nhật dữ liệu và phát message.
3. Thiết kế consumer idempotent để xử lý an toàn khi cùng sự kiện được giao lại.
4. Chọn partition key phù hợp nếu thứ tự theo thực thể nghiệp vụ quan trọng.
5. Theo dõi lỗi gửi, retry, broker acknowledgement và số message chưa được xử lý.

`Supplier<Flux<T>>` không tự tạo ra bảo đảm exactly-once. Nó chỉ cung cấp mô hình phát reactive. Mức bảo đảm giao nhận phụ thuộc binder, broker, cấu hình producer và consumer, transaction, lưu trạng thái nguồn và logic idempotency của ứng dụng.

## 11. Kiểm thử Supplier trả một phần tử

Với `Supplier<T>`, có thể kiểm tra giá trị trả về và việc mỗi lần gọi tạo sự kiện theo mong muốn:

```java
import static org.junit.jupiter.api.Assertions.assertNotNull;

import org.junit.jupiter.api.Test;

class OrderEventSourcesTest {

    @Test
    void createsAnOrderEvent() {
        OrderEventSources sources = new OrderEventSources();
        OrderCreated event = sources.orderEventSupplier().get();

        assertNotNull(event.orderId());
        assertNotNull(event.createdAt());
    }
}
```

Nếu supplier cần gọi repository hoặc dịch vụ ngoài, hãy inject dependency qua constructor hoặc bean method và mock dependency đó trong unit test. Kiểm thử riêng logic tạo sự kiện giúp xác định lỗi nguồn phát mà không cần khởi chạy broker.

## 12. Kiểm thử Supplier trả Flux

Với publisher hữu hạn, Reactor Test cung cấp `StepVerifier` để xác minh chuỗi phần tử và tín hiệu hoàn tất:

```java
import java.time.Duration;

import org.junit.jupiter.api.Test;
import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

class MetricEventSourcesTest {

    @Test
    void emitsThreeValuesAndCompletes() {
        StepVerifier.create(Flux.just(1L, 2L, 3L))
                .expectNext(1L, 2L, 3L)
                .verifyComplete();
    }

    @Test
    void emitsPeriodicValues() {
        StepVerifier.withVirtualTime(() -> Flux.interval(Duration.ofSeconds(2)))
                .thenAwait(Duration.ofSeconds(6))
                .expectNext(0L, 1L, 2L)
                .thenCancel()
                .verify();
    }
}
```

Ví dụ thứ hai dùng virtual time để kiểm tra publisher theo thời gian mà không phải chờ sáu giây thực. Trong mã kiểm thử đầy đủ, cần import `Flux` và các kiểu Reactor Test tương ứng. Với nguồn vô hạn, luôn hủy subscription trong test để tránh giữ scheduler hoặc tài nguyên.

Test binder của Spring Cloud Stream có thể kiểm tra message đầu ra được phát qua binding. Kiểm thử tích hợp với Kafka, RabbitMQ hoặc Pulsar vẫn cần thiết để xác nhận serialization, tốc độ producer, hành vi khi broker chậm và khả năng phục hồi sau lỗi.

## 13. Chọn kiểu Supplier cho bài toán thực tế

| Nhu cầu | Kiểu phù hợp | Lý do |
| --- | --- | --- |
| Mỗi phút đọc một bản ghi trạng thái từ repository | `Supplier<StatusSnapshot>` | Poller điều khiển chu kỳ gọi và mỗi lần tạo một object. |
| Phát dữ liệu liên tục từ bộ đếm thời gian | `Supplier<Flux<MetricSample>>` | `Flux.interval` quản lý nhịp phát của publisher. |
| Phát một danh sách sự kiện đã biết rồi kết thúc | `Supplier<Flux<Event>>` | `Flux.fromIterable` phát nhiều phần tử và hoàn tất. |
| Nhận callback từ một API bất đồng bộ | `Supplier<Flux<Event>>` hoặc một adapter reactive phù hợp | Có thể chuyển nguồn callback thành publisher, nhưng cần xác định buffering và vòng đời. |
| Đọc một bản ghi mỗi lần poll để giới hạn tải nguồn | `Supplier<Record>` | Mỗi lần gọi có thể đọc một đơn vị dữ liệu và cập nhật checkpoint phù hợp. |

Không nên chọn `Flux` chỉ vì nó có vẻ hiện đại hơn. Nếu nguồn dữ liệu thực chất là thao tác đồng bộ trả một object theo chu kỳ, `Supplier<T>` đơn giản và dễ kiểm soát hơn. Ngược lại, nếu nguồn vốn là luồng sự kiện bất đồng bộ, `Supplier<Flux<T>>` giúp mô tả trực tiếp mô hình phát.

## 14. Checklist khi triển khai

Trước khi đưa Supplier vào production, cần xác định:

- Bean nào được chọn qua `spring.cloud.function.definition`.
- Binding đầu ra `<function>-out-0` có destination và content type chính xác.
- Nếu dùng `Supplier<T>`, poller có chu kỳ và giới hạn message phù hợp.
- Nếu dùng `Supplier<Flux<T>>`, publisher là cold hay hot, hữu hạn hay vô hạn, và ai quản lý vòng đời subscription.
- Tốc độ phát, concurrency và buffer có giới hạn.
- Lỗi nguồn, lỗi chuyển đổi và lỗi gửi được quan sát và xử lý theo chính sách rõ ràng.
- Sự kiện có ID ổn định hoặc cơ chế chống trùng phù hợp.
- Unit test, test binder và integration test bao phủ hành vi quan trọng.

## Kết luận

`Supplier<T>` tạo một giá trị cho mỗi lần poller gọi supplier; nhịp phát được điều khiển bằng cấu hình poller. `Supplier<Flux<T>>` trả về một publisher và Spring đăng ký subscription để nhận nhiều phần tử; nhịp phát nằm trong nguồn và các toán tử Reactor, không nằm ở poller. Cả hai cùng tạo binding đầu ra `<function>-out-0`. Khi chọn giữa chúng, hãy dựa vào bản chất nguồn dữ liệu, vòng đời publisher, backpressure, xử lý lỗi và yêu cầu giao nhận của hệ thống.
