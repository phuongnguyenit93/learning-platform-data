# Quản lý bộ đệm, tốc độ phát và giới hạn số tác vụ đồng thời

Trong hệ thống xử lý sự kiện, tốc độ message đến có thể cao hơn tốc độ ứng dụng xử lý. Nếu producer phát nhanh, consumer xử lý chậm hoặc một bước gọi dịch vụ ngoài bị nghẽn, message sẽ tích lũy trong bộ đệm. Bộ đệm không giới hạn có thể làm bộ nhớ tăng liên tục; quá nhiều tác vụ đồng thời có thể làm cạn connection pool, thread hoặc tài nguyên broker. Ngược lại, giới hạn quá thấp có thể khiến hệ thống xử lý không hết tải.

Reactive Streams và Project Reactor cung cấp cơ chế demand/backpressure để phối hợp tốc độ giữa publisher và subscriber. Spring Cloud Stream có thể kết nối các reactive function với destination thông qua binder, nhưng mức backpressure được truyền xuyên suốt tới broker còn phụ thuộc binder, client và cấu hình. Vì vậy, cần thiết kế đồng thời bộ đệm, tốc độ phát, concurrency và chính sách khi quá tải.

Bài học này tập trung vào cách quản lý các yếu tố đó trong ứng dụng Spring Cloud Stream: điều tiết demand, giới hạn buffer, gom message theo batch, giới hạn số tác vụ song song, xử lý lời gọi blocking và quan sát hệ thống khi tải tăng.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích demand và backpressure trong Reactive Streams.
- Phân biệt bộ đệm của Reactor, bộ đệm của client broker và message backlog trên broker.
- Dùng các operator như `limitRate`, `bufferTimeout`, `onBackpressureBuffer` và `onBackpressureDrop` có chủ đích.
- Giới hạn số tác vụ đang chạy bằng `flatMap`, `concatMap` và tham số concurrency.
- Điều tiết tốc độ phát và tránh tạo nguồn message nhanh hơn khả năng tiêu thụ.
- Xử lý tác vụ blocking trong pipeline reactive mà không chặn event-loop.
- Thiết kế hành vi khi bộ đệm đầy, timeout hoặc một bước xử lý lỗi.
- Kiểm thử backpressure và theo dõi queue, lag, latency, throughput trong vận hành.

## 1. Demand và backpressure là gì?

Reactive Streams định nghĩa giao thức giữa Publisher và Subscriber. Subscriber nhận Subscription và gửi yêu cầu số lượng phần tử mà nó sẵn sàng xử lý thông qua `request(n)`. Publisher chỉ nên phát số phần tử theo demand đã được yêu cầu. Khi subscriber xử lý chậm, nó có thể giảm tốc độ yêu cầu; publisher tuân thủ giao thức sẽ không tiếp tục đẩy vô hạn phần tử xuống subscriber.

Đây là backpressure: tín hiệu nhu cầu từ phía tiêu thụ được truyền ngược về phía phát để điều tiết luồng dữ liệu.

~~~mermaid
sequenceDiagram
    participant S as Subscriber
    participant P as Publisher
    S->>P: subscribe()
    S->>P: request(10)
    P-->>S: onNext(item 1..10)
    Note over S: Đang xử lý 10 phần tử
    S->>P: request(5)
    P-->>S: onNext(item 11..15)
    Note over S,P: Demand được điều tiết theo khả năng xử lý
~~~

Trong một pipeline reactive:

- Publisher tạo dữ liệu.
- Operator trung gian biến đổi, gom nhóm hoặc điều tiết dữ liệu.
- Subscriber nhận và xử lý dữ liệu.
- Demand quyết định số phần tử có thể được phát tiếp.
- Backpressure strategy quyết định hành vi khi một nguồn không thể hoặc không muốn tuân thủ demand.

Backpressure giúp kiểm soát lượng công việc đang được chuyển qua pipeline. Nó không tự động bảo đảm message không bị mất, không xử lý trùng hoặc được lưu giữ vô hạn. Những bảo đảm đó còn phụ thuộc broker, acknowledgement, offset, retry, retention và thiết kế ứng dụng.

## 2. Phân biệt các lớp bộ đệm

Một hệ thống Spring Cloud Stream có thể chứa nhiều bộ đệm độc lập. Cần xác định bộ đệm nào đang tăng trước khi điều chỉnh cấu hình.

| Lớp | Vị trí | Ví dụ | Dấu hiệu quá tải |
|---|---|---|---|
| Reactor operator buffer | Trong pipeline của ứng dụng | `buffer(100)`, `onBackpressureBuffer(500)` | Heap tăng, queue operator tăng |
| Scheduler queue | Trong thread pool của Reactor | `publishOn`, `boundedElastic` | Task chờ lâu, scheduler queue tăng |
| Binder/client buffer | Trong thư viện kết nối broker | Kafka producer buffer, client pending sends | Send latency tăng, client queue đầy |
| Broker backlog | Trên Kafka/RabbitMQ/Pulsar | Kafka consumer lag, RabbitMQ ready messages, Pulsar backlog | Message tồn đọng tăng |
| Business queue | Trong ứng dụng hoặc database | Hàng đợi công việc, outbox | Công việc chờ xử lý lâu |

Không nên tăng mọi bộ đệm khi thấy throughput giảm. Bộ đệm lớn hơn chỉ trì hoãn thời điểm quá tải lộ ra và có thể làm tăng bộ nhớ, độ trễ và thời gian phục hồi. Hãy đo vị trí tắc nghẽn trước: broker đang tích lũy message, binder không gửi kịp, pipeline không xử lý kịp hay một dịch vụ phụ thuộc đang chậm.

## 3. Reactive function trong Spring Cloud Stream

Spring Cloud Stream hỗ trợ mô hình hàm reactive dựa trên Reactor. Một reactive function thường nhận và trả về publisher, ví dụ:

~~~java
Function<Flux<OrderCreated>, Flux<EnrichedOrder>>
~~~

Khác với function imperative nhận một object cho mỗi lần gọi, reactive function nhận cả một luồng. Function được tạo thành một pipeline và các phần tử đi qua pipeline theo demand. Không nên giả định function reactive được gọi lại độc lập cho từng message như `Function<OrderCreated, EnrichedOrder>`.

Ví dụ:

~~~java
import java.util.function.Function;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import reactor.core.publisher.Flux;

@Configuration
public class ReactiveOrderFunctions {

    @Bean
    Function<Flux<OrderCreated>, Flux<EnrichedOrder>> enrichOrders() {
        return events -> events
            .filter(event -> event.total().signum() > 0)
            .map(event -> new EnrichedOrder(
                event.eventId(),
                event.orderId(),
                event.total(),
                "STANDARD"
            ));
    }
}
~~~

Binding có thể được cấu hình theo tên function:

~~~yaml
spring:
  cloud:
    function:
      definition: enrichOrders
    stream:
      bindings:
        enrichOrders-in-0:
          destination: orders
          group: order-enricher
          contentType: application/json
        enrichOrders-out-0:
          destination: enriched-orders
          contentType: application/json
~~~

Ví dụ minh họa ranh giới function và binding. Khả năng reactive, cách binder quản lý subscription, acknowledgement và demand phụ thuộc binder cùng phiên bản. Hãy xác nhận binder đang dùng hỗ trợ reactive function trước khi dựa vào backpressure end-to-end.

### Khi nào dùng imperative, khi nào dùng reactive?

| Tình huống | Lựa chọn thường phù hợp |
|---|---|
| Xử lý từng message độc lập, logic đơn giản | Imperative `Function<T, R>` hoặc `Consumer<T>` |
| Ghép nhiều bước bất đồng bộ theo luồng | Reactive `Function<Flux<T>, Flux<R>>` |
| Cần gom batch hoặc cửa sổ thời gian | Reactive pipeline với `buffer` hoặc `window` |
| Nhiều lời gọi I/O bất đồng bộ | Reactive client và giới hạn concurrency |
| Thư viện phụ thuộc blocking | Imperative hoặc cô lập blocking trong scheduler phù hợp |

Reactive không tự làm cho một thao tác blocking trở thành non-blocking. Nếu pipeline gọi JDBC blocking, file I/O blocking hoặc HTTP client đồng bộ, thread thực thi vẫn bị giữ trong suốt thời gian chờ.

## 4. Điều tiết demand bằng limitRate

`limitRate(n)` chia các yêu cầu upstream thành những đợt nhỏ hơn thay vì yêu cầu toàn bộ số phần tử có thể nhận. Nó giúp kiểm soát nhịp demand mà pipeline gửi về nguồn.

~~~java
Flux<OrderCreated> controlled =
    incoming.limitRate(100);
~~~

Với cấu hình này, pipeline yêu cầu upstream theo từng đợt có giới hạn thay vì phát một yêu cầu rất lớn ngay lập tức. Reactor có thể prefetch và yêu cầu tiếp trước khi toàn bộ đợt hiện tại hoàn tất, vì vậy `limitRate` không phải giới hạn tuyệt đối cho tổng số message đang nằm trong mọi queue.

Có thể điều chỉnh low tide để xác định khi nào Reactor gửi yêu cầu bổ sung:

~~~java
Flux<OrderCreated> controlled =
    incoming.limitRate(100, 25);
~~~

Ở đây, high tide là 100 và low tide là 25 theo semantics của Reactor. Khi demand còn lại xuống ngưỡng thích hợp, Reactor yêu cầu thêm phần tử để tiếp tục pipeline.

Dùng `limitRate` khi muốn kiểm soát lượng demand mà pipeline phát lên upstream. Nếu cần giới hạn tổng số công việc đang chạy, hãy kết hợp với giới hạn concurrency và giới hạn queue ở đúng tầng.

## 5. Quản lý bộ đệm khi downstream xử lý chậm

Một số nguồn không thể hoặc không tuân thủ backpressure. Khi tốc độ phát vượt khả năng tiêu thụ, pipeline cần một chính sách rõ ràng.

### Bộ đệm có giới hạn

`onBackpressureBuffer(capacity)` giữ phần tử khi downstream chưa yêu cầu thêm, nhưng chỉ cho phép số lượng tối đa theo capacity:

~~~java
Flux<OrderCreated> buffered =
    incoming.onBackpressureBuffer(
        500,
        item -> log.warn("Buffer overflow: {}", item.eventId())
    );
~~~

Nếu buffer đầy, Reactor gọi overflow callback và phát tín hiệu lỗi theo overload được chọn. Cần xử lý lỗi đó ở tầng phù hợp; callback chỉ ghi log không có nghĩa message đã được lưu bền vững hoặc xử lý thành công.

Không dùng buffer không giới hạn trong hệ thống có tốc độ đầu vào không kiểm soát. Khi downstream dừng lâu, bộ nhớ có thể tăng cho đến khi tiến trình bị ảnh hưởng.

### Chọn hành vi khi buffer đầy

Reactor cung cấp một số chiến lược backpressure:

| Operator | Hành vi khi downstream không theo kịp | Khi phù hợp |
|---|---|---|
| `onBackpressureBuffer(capacity)` | Giữ phần tử tới giới hạn; overflow phát lỗi hoặc xử lý theo overload | Không muốn bỏ message và có giới hạn bộ nhớ |
| `onBackpressureDrop()` | Bỏ phần tử đến khi downstream có demand | Dữ liệu có thể bỏ như telemetry tần suất cao |
| `onBackpressureLatest()` | Giữ phần tử mới nhất, bỏ các phần tử cũ hơn khi cần | Snapshot/trạng thái mới nhất quan trọng hơn lịch sử |
| `onBackpressureError()` | Phát lỗi khi không thể đáp ứng demand | Muốn fail-fast và để tầng trên xử lý |

Các chiến lược drop/latest làm mất một phần dữ liệu. Không dùng chúng cho sự kiện nghiệp vụ như thanh toán, đơn hàng hoặc thay đổi tồn kho nếu không có cơ chế khôi phục khác.

Ví dụ dùng latest cho dữ liệu trạng thái thiết bị:

~~~java
Flux<DeviceSnapshot> latestSnapshots =
    snapshots.onBackpressureLatest();
~~~

Nếu mục tiêu là giữ mọi sự kiện, hãy dùng nguồn có khả năng backpressure, queue bền vững hoặc broker backlog; đừng dựa vào buffer trong heap như nơi lưu trữ lâu dài.

### Buffer theo kích thước và thời gian

`buffer(n)` gom n phần tử thành một danh sách trước khi phát batch:

~~~java
Flux<List<OrderCreated>> batches =
    incoming.buffer(100);
~~~

Nếu luồng không đủ 100 phần tử, batch cuối có thể phải chờ lâu. Dùng `bufferTimeout(maxSize, maxTime)` để phát batch khi đủ số lượng hoặc hết thời gian:

~~~java
Flux<List<OrderCreated>> batches =
    incoming.bufferTimeout(100, Duration.ofSeconds(2));
~~~

Cách này cân bằng giữa throughput và latency: batch lớn có thể giảm chi phí gọi database hoặc dịch vụ ngoài, nhưng tăng thời gian chờ và bộ nhớ. Hãy chọn maxSize và maxTime dựa trên kích thước payload, tốc độ đầu vào và SLA.

`window(n)` tạo các Flux con thay vì gom tất cả phần tử vào List. Window hữu ích khi muốn xử lý từng cửa sổ như một luồng độc lập; cần bảo đảm các window được subscribe và tiêu thụ đúng cách.

## 6. Giới hạn số tác vụ đồng thời

Trong reactive pipeline, `flatMap` có thể chạy nhiều publisher con cùng lúc. Tham số concurrency giới hạn số publisher con đang được subscribe đồng thời.

~~~java
Flux<EnrichedOrder> enriched =
    incoming.flatMap(
        this::enrichAsync,
        16,
        1
    );
~~~

Trong ví dụ:

- Tối đa 16 lời gọi `enrichAsync` được xử lý đồng thời.
- Tham số cuối là prefetch cho mỗi publisher con.
- Kết quả có thể phát ra theo thứ tự hoàn thành, không nhất thiết theo thứ tự đầu vào.

Nếu cần giữ thứ tự đầu ra trong khi vẫn cho phép xử lý đồng thời, có thể dùng `flatMapSequential`. Nếu cần xử lý lần lượt, dùng `concatMap`:

~~~java
Flux<EnrichedOrder> ordered =
    incoming.concatMap(this::enrichAsync);
~~~

So sánh:

| Operator | Concurrency | Thứ tự đầu ra |
|---|---|---|
| `flatMap(mapper)` | Có thể nhiều publisher con cùng lúc | Theo thời điểm hoàn thành |
| `flatMap(mapper, concurrency)` | Bị giới hạn theo concurrency | Không đảm bảo thứ tự đầu vào |
| `flatMapSequential(mapper, concurrency)` | Xử lý đồng thời | Giữ thứ tự phát kết quả theo thứ tự nguồn |
| `concatMap(mapper)` | Một publisher con tại một thời điểm | Giữ thứ tự nguồn |

Giữ thứ tự có thể tạo hàng đợi kết quả nếu một phần tử đầu chậm hơn những phần tử phía sau. Do đó, `flatMapSequential` có thể cần thêm bộ nhớ khi một tác vụ bị treo. Chọn operator theo yêu cầu thứ tự nghiệp vụ, không chỉ theo throughput.

### Tính giới hạn concurrency tổng thể

Nếu mỗi instance xử lý tối đa 16 lời gọi song song và có 5 instance, hệ thống có thể tạo tới khoảng 80 lời gọi đồng thời cho bước đó. Nếu mỗi lời gọi giữ một connection database, connection pool phải đủ hoặc concurrency phải được giảm tương ứng.

Cần tính concurrency ở toàn hệ thống, không chỉ một pipeline:

- Số replica ứng dụng.
- Concurrency mỗi replica.
- Số partition hoặc consumer được gán.
- Connection pool và giới hạn của dịch vụ phụ thuộc.
- Thread pool và scheduler.
- Retry có thể tạo thêm lần gọi khi lỗi.

Một concurrency nhỏ trên từng instance vẫn có thể vượt khả năng của dịch vụ ngoài khi scale số replica.

## 7. Điều tiết tốc độ phát

Backpressure điều tiết demand, còn rate limiting đặt giới hạn tốc độ theo thời gian. Hai khái niệm liên quan nhưng khác nhau.

- **Demand control:** subscriber yêu cầu bao nhiêu phần tử từ upstream.
- **Concurrency control:** có bao nhiêu tác vụ được thực hiện cùng lúc.
- **Rate control:** trong một khoảng thời gian có bao nhiêu message hoặc request được phép phát.
- **Buffer control:** có bao nhiêu phần tử được giữ khi tốc độ đầu vào lớn hơn đầu ra.

Có thể làm chậm nguồn bằng `delayElements`:

~~~java
Flux<OrderCreated> paced =
    incoming.delayElements(Duration.ofMillis(20));
~~~

Ví dụ tạo khoảng cách tối thiểu giữa các phần tử được phát downstream. Đây là cách đơn giản để minh họa pacing; nó không thay thế token bucket hoặc rate limiter chính xác khi có nhiều subscriber, nhiều replica hay yêu cầu quota theo tenant.

Với giới hạn request tới dịch vụ ngoài, nên dùng rate limiter có cấu hình rõ ràng, có thể phối hợp với concurrency limit. Với producer broker, cần xem xét giới hạn của client và broker như batch size, linger, buffer memory, request quota hoặc flow control tương ứng.

Không nên chỉ dùng `delayElements` để kiểm soát quota production. Nó không cung cấp sẵn chính sách phân phối quota toàn cụm và có thể làm tăng latency đáng kể.

## 8. Xử lý I/O blocking trong pipeline reactive

Reactive pipeline nên giữ thread xử lý không bị chặn bởi các lời gọi đồng bộ. Nếu phải gọi thư viện blocking, hãy cô lập thao tác đó trên scheduler phù hợp.

Ví dụ:

~~~java
import reactor.core.scheduler.Schedulers;

Mono<CustomerProfile> profile =
    Mono.fromCallable(() -> blockingCustomerClient.load(customerId))
        .subscribeOn(Schedulers.boundedElastic());
~~~

`boundedElastic` phù hợp cho tác vụ blocking có thời gian chờ, với số thread và queue được giới hạn theo cấu hình Reactor. Không dùng `Schedulers.parallel()` cho I/O blocking; scheduler này phù hợp hơn với các tác vụ tính toán ngắn và CPU-bound.

Các operator quan trọng:

- `subscribeOn` ảnh hưởng scheduler thực thi quá trình subscribe và nguồn upstream.
- `publishOn` chuyển việc xử lý các operator phía sau sang scheduler được chọn.
- `parallel` và `runOn` có thể chia tác vụ CPU-bound thành nhiều rail, nhưng cần kiểm soát số rail và tài nguyên.

Không tạo scheduler mới cho từng message. Hãy tái sử dụng scheduler phù hợp, cấu hình giới hạn và đóng tài nguyên đúng vòng đời ứng dụng.

## 9. Kết hợp buffer, concurrency và rate control

Ba cơ chế cần được thiết kế cùng nhau. Ví dụ một pipeline nhận đơn hàng, gọi dịch vụ khách hàng bất đồng bộ, gom kết quả và ghi batch:

~~~java
@Bean
Function<Flux<OrderCreated>, Flux<EnrichedOrder>> enrichOrders(
        CustomerClient customerClient) {

    return events -> events
        .limitRate(100, 25)
        .flatMap(event ->
            customerClient.findProfile(event.orderId())
                .map(profile -> new EnrichedOrder(
                    event.eventId(),
                    event.orderId(),
                    event.total(),
                    profile.tier()
                )),
            16,
            1
        )
        .onBackpressureBuffer(
            500,
            item -> log.warn("Overflow for {}", item.orderId())
        );
}
~~~

Đoạn code minh họa cách phối hợp demand, concurrency và buffer, nhưng thứ tự operator rất quan trọng. `onBackpressureBuffer` đặt sau `flatMap` chỉ quan sát luồng đầu ra của bước đó; nó không giới hạn mọi queue nội bộ của flatMap, client hoặc binder. Trong một thiết kế thực tế, hãy đặt giới hạn tại đúng ranh giới có thể tích lũy dữ liệu và kiểm thử overflow.

Nếu muốn ghi batch, có thể nối thêm:

~~~java
events
    .bufferTimeout(100, Duration.ofSeconds(2))
    .concatMap(batch -> repository.saveAll(batch));
~~~

Khi repository trả về Publisher, `concatMap` đợi batch hiện tại hoàn tất rồi mới gửi batch kế tiếp. Điều này giới hạn số batch ghi đồng thời và giữ thứ tự batch. Nếu database hỗ trợ xử lý song song và cần throughput cao hơn, có thể tăng concurrency có giới hạn.

## 10. Backpressure end-to-end và giới hạn của binder

Reactive Streams điều tiết demand trong pipeline Reactor, nhưng broker không phải lúc nào cũng có cùng mô hình demand. Một số binder sử dụng client có khả năng pause/resume hoặc điều chỉnh lượng message đang được lấy; một số binder sử dụng listener container, prefetch, acknowledgement hoặc buffer riêng.

Do đó, cần phân biệt:

1. Backpressure giữa các operator Reactor.
2. Cơ chế nhận message của binder/client.
3. Flow control của broker.
4. Backlog bền vững trên broker.

Không nên giả định downstream tạm ngừng yêu cầu thêm phần tử sẽ khiến mọi broker ngừng gửi ngay lập tức. Client có thể đã prefetch message, listener container có thể có queue nội bộ và broker có thể tiếp tục tích lũy backlog.

### Kafka

Kafka consumer đọc theo poll và quản lý offset. Binder có thể dùng cơ chế poll, batch và consumer concurrency của Kafka client/container. Khi ứng dụng xử lý chậm, cần theo dõi consumer lag, poll interval, số partition và số consumer. Tùy binder và mô hình function, backpressure trong Reactor có thể không truyền trực tiếp thành demand ở broker.

### RabbitMQ

RabbitMQ có prefetch/QoS để giới hạn số message chưa được acknowledge mà consumer nhận cùng lúc. Prefetch quá lớn làm tăng lượng message nằm trong client; quá nhỏ có thể giảm throughput. Acknowledgement và queue backlog là các chỉ số quan trọng khi điều tiết consumer.

### Pulsar

Pulsar client có receiver queue size, subscription type và cơ chế flow control riêng. Receiver queue quá lớn làm tăng bộ nhớ phía consumer; quá nhỏ có thể ảnh hưởng throughput. Cần kiểm tra binder version và client properties để hiểu cách reactive pipeline liên hệ với số message client đã nhận trước.

Khi triển khai, hãy cấu hình giới hạn ở cả pipeline và binder/client nếu cần. Một giới hạn trong Reactor không thể thay thế prefetch, pause/resume hoặc quota của broker.

## 11. Xử lý lỗi, retry và overflow

Khi một phần tử lỗi trong pipeline, Reactor có thể kết thúc toàn bộ luồng nếu lỗi không được xử lý. Cần quyết định lỗi nào có thể retry, lỗi nào phải chuyển sang nhánh xử lý khác và lỗi nào cần dừng pipeline.

Ví dụ retry có giới hạn:

~~~java
Flux<EnrichedOrder> result =
    incoming.flatMap(
        event -> enrichAsync(event)
            .retryWhen(
                Retry.backoff(3, Duration.ofMillis(200))
                    .maxBackoff(Duration.ofSeconds(2))
            ),
        16
    );
~~~

Retry có thể phát sinh tác động lặp nếu lời gọi trước đã thành công ở dịch vụ ngoài nhưng response bị mất. Các thao tác ghi dữ liệu hoặc thanh toán cần idempotency key và cơ chế chống trùng.

Với message nghiệp vụ không thể bỏ, overflow không nên được xử lý bằng drop. Hãy phát lỗi có thể quan sát, để binder/broker áp dụng chính sách retry hoặc dead-letter theo cấu hình phù hợp. Cách acknowledgement, retry và DLQ trong reactive function phụ thuộc binder và phiên bản; kiểm thử trên broker thật trước khi dựa vào semantics đó.

Với telemetry có thể mất, `onBackpressureDrop` hoặc `onBackpressureLatest` có thể phù hợp, nhưng cần đếm số phần tử bị bỏ và hiển thị metric. Không âm thầm bỏ message mà không có quan sát.

## 12. Quan sát và vận hành dưới tải

Để biết giới hạn đang đặt đúng hay chưa, hãy theo dõi cả throughput lẫn thời gian chờ.

| Chỉ số | Điều cần quan sát |
|---|---|
| Input rate | Số message đến mỗi giây |
| Output rate | Số message xử lý xong mỗi giây |
| Processing latency | Thời gian từ nhận đến hoàn tất |
| Buffer occupancy | Số phần tử đang nằm trong buffer |
| Overflow/drop count | Số lần buffer đầy hoặc message bị bỏ |
| In-flight tasks | Số tác vụ đang xử lý đồng thời |
| Scheduler queue | Số task chờ thread thực thi |
| Broker backlog/lag | Message tồn đọng phía broker |
| Error/retry rate | Tỷ lệ lỗi và số lần retry |
| Heap/GC | Áp lực bộ nhớ do payload và queue |

Nếu input rate cao hơn output rate trong thời gian dài, backlog sẽ tăng. Hãy xác định hệ thống đang bị giới hạn bởi CPU, database, dịch vụ ngoài, số partition, connection pool hay binder. Tăng concurrency chỉ hữu ích khi tài nguyên phía sau còn dư.

Đặt cảnh báo cho buffer gần đầy, consumer lag tăng liên tục, queue ready tăng, backlog vượt ngưỡng, latency vượt SLA hoặc tỷ lệ retry cao. Khi cần, giảm tốc độ nguồn, tạm dừng tiếp nhận hoặc scale consumer theo giới hạn của broker và dịch vụ phụ thuộc.

## 13. Kiểm thử backpressure và concurrency

Kiểm thử cần xác minh hành vi khi downstream chậm, không chỉ trường hợp pipeline chạy bình thường.

### StepVerifier

Reactor Test cung cấp StepVerifier để điều khiển demand:

~~~java
@Test
void emitsOnlyRequestedElements() {
    Flux<Integer> source = Flux.range(1, 5);

    StepVerifier.create(source, 0)
        .thenRequest(2)
        .expectNext(1, 2)
        .thenRequest(1)
        .expectNext(3)
        .thenCancel()
        .verify();
}
~~~

Test này khởi tạo demand bằng 0, yêu cầu hai phần tử rồi thêm một phần tử. Nó xác minh publisher tuân thủ demand trong pipeline.

### Kiểm thử buffer và overflow

Tạo một nguồn nhanh hơn downstream, dùng buffer có giới hạn và xác minh overflow được quan sát. Với drop/latest, đếm số phần tử bị loại bỏ và xác minh phần tử cuối cùng hoặc phần tử được giữ đúng theo semantics.

### Kiểm thử concurrency

Dùng counter tăng khi tác vụ bắt đầu và giảm khi hoàn tất. Ghi nhận giá trị lớn nhất để xác minh concurrency không vượt giới hạn đã cấu hình. Tránh dùng test có thời gian cố định quá ngắn; dùng latch hoặc publisher điều khiển được để làm kết quả ổn định.

### Broker integration test

Dùng broker thật hoặc Testcontainers để kiểm tra:
- Prefetch/receiver queue/consumer poll có hoạt động theo cấu hình không.
- Broker backlog tăng khi consumer xử lý chậm.
- Consumer tiếp tục từ vị trí phù hợp sau khi được mở rộng hoặc khởi động lại.
- Retry, acknowledgement và DLQ không làm mất hoặc nhân đôi tác động nghiệp vụ ngoài dự kiến.
- Tải tăng không làm heap hoặc queue nội bộ vượt giới hạn.

Test binder hữu ích để kiểm tra function và binding, nhưng không thay thế kiểm thử flow control của Kafka, RabbitMQ hoặc Pulsar.

## 14. Quy trình thực hành

Xây dựng pipeline reactive xử lý sự kiện `OrderCreated`:

1. Khai báo `Function<Flux<OrderCreated>, Flux<EnrichedOrder>>`.
2. Cấu hình input binding đọc destination `orders` với group ổn định.
3. Dùng `limitRate` để điều tiết demand từ pipeline.
4. Dùng `flatMap` với concurrency hữu hạn khi gọi dịch vụ khách hàng.
5. Nếu cần ghi theo batch, dùng `bufferTimeout` với cả giới hạn số lượng và thời gian.
6. Giới hạn queue ở các ranh giới có thể tích lũy dữ liệu.
7. Chọn hành vi overflow phù hợp với tính chất dữ liệu; không drop sự kiện nghiệp vụ quan trọng.
8. Cô lập lời gọi blocking trên scheduler phù hợp hoặc thay bằng reactive client.
9. Chạy StepVerifier để xác minh demand và overflow.
10. Chạy broker integration test, quan sát backlog, latency và số tác vụ đồng thời.
11. Tăng input rate có kiểm soát để tìm điểm bão hòa.
12. Điều chỉnh concurrency, batch size, prefetch và số instance dựa trên số liệu đo.

Bảng nghiệm thu:

| Hạng mục | Kết quả cần xác nhận |
|---|---|
| Reactive function | Nhận/trả publisher đúng chữ ký |
| Demand | Pipeline không phát vượt demand trong phạm vi Reactive Streams |
| Buffer | Có giới hạn và hành vi overflow rõ ràng |
| Batch | Có giới hạn kích thước và thời gian chờ |
| Concurrency | Không vượt số tác vụ song song đã chọn |
| Rate | Tốc độ phát phù hợp giới hạn dịch vụ phụ thuộc |
| Blocking I/O | Không chặn event-loop |
| Binder | Hiểu và cấu hình prefetch/flow control tương ứng |
| Recovery | Retry, acknowledgement và DLQ được kiểm thử |
| Observability | Có metric cho lag, buffer, latency, error và drop |

## Kết luận

Quản lý bộ đệm, tốc độ phát và số tác vụ đồng thời là ba phần liên kết trong thiết kế reactive processing. Demand/backpressure giúp phối hợp tốc độ giữa publisher và subscriber; buffer giữ dữ liệu tạm thời khi downstream chậm; concurrency giới hạn số công việc đang chạy; rate control đặt giới hạn tốc độ theo thời gian.

Trong Spring Cloud Stream, hãy kết hợp operator Reactor với cấu hình binder và flow control của broker. Đặt giới hạn rõ ràng cho mọi queue, chọn chính sách overflow theo mức độ quan trọng của message, tránh blocking trên event-loop và kiểm thử khi tải vượt khả năng xử lý. Backpressure trong pipeline không tự động trở thành bảo đảm giao nhận của broker; cần đo backlog, acknowledgement, retry và DLQ trên môi trường thực tế.

