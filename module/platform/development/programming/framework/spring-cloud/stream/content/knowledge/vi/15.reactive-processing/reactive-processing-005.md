# Đánh giá áp lực ngược (backpressure) theo khả năng thực tế của binder

Backpressure là cơ chế giúp một thành phần tiêu thụ chậm báo cho thành phần phát dữ liệu biết nó có thể nhận thêm bao nhiêu phần tử. Trong Reactor, cơ chế này được biểu diễn bằng nhu cầu (demand) qua Reactive Streams. Tuy nhiên, một ứng dụng Spring Cloud Stream còn có broker, binder, listener/polling loop, hàng đợi nội bộ và consumer group. Nhu cầu của một `Flux` không mặc nhiên trở thành lệnh điều tiết trực tiếp tới Kafka, RabbitMQ hoặc Pulsar.

Vì vậy, đánh giá backpressure cần trả lời hai câu hỏi riêng: pipeline reactive trong ứng dụng có truyền và giới hạn demand đúng không; binder/broker có cơ chế flow control nào thực sự được kích hoạt khi downstream chậm? Câu trả lời phải dựa trên phiên bản binder, cấu hình đang chạy và phép đo khi tải tăng, không chỉ dựa vào việc code có dùng `Flux`.

## 1. Phân biệt backpressure với flow control của broker

Trong Reactive Streams, subscriber gửi yêu cầu số lượng phần tử bằng `request(n)`. Publisher chỉ được phát tối đa số phần tử đã được yêu cầu. Khi downstream chậm, demand giảm; upstream có thể tạm dừng phát cho tới khi có demand mới.

~~~text
Reactive pipeline trong ứng dụng

Publisher ---> Operator ---> Subscriber
    ^                            |
    |                            |
    +-------- request(n) --------+
            demand signal
~~~

Đây là backpressure ở ranh giới Reactive Streams. Broker có các cơ chế flow control riêng:

- Kafka consumer chủ động gọi `poll()` để lấy record; số record và nhịp poll chịu ảnh hưởng bởi cấu hình consumer, partition assignment và vòng đời poll.
- RabbitMQ đẩy delivery tới consumer; QoS/prefetch giới hạn số message chưa được xác nhận mà broker gửi cho consumer.
- Pulsar consumer nhận message qua client; client dùng receiver queue và flow permits để điều tiết lượng message đang được gửi tới consumer.

Các cơ chế này có thể giới hạn lượng dữ liệu đang chờ ở broker/client, nhưng không đồng nghĩa chúng tự động hiểu `request(1)` từ một subscriber Reactor. Binder là cầu nối giữa hai mô hình. Cần kiểm tra binder chuyển demand thành pause/resume, prefetch, permits hay chỉ đưa message vào một hàng đợi nội bộ.

| Lớp | Cơ chế cần quan sát | Câu hỏi |
|---|---|---|
| Reactor | `request(n)`, operator prefetch, queue, overflow | Downstream có thể điều tiết upstream không? |
| Spring Cloud Stream | Function adapter, channel, executor và buffer | Có hàng đợi trung gian nào nhận message trước khi function xử lý không? |
| Binder | Poll, listener container, ack, pause/resume hoặc flow permits | Binder phản ứng thế nào khi function chậm? |
| Broker | Kafka fetch/partition, Rabbit prefetch/unacked, Pulsar receiver queue/permits | Broker có giới hạn delivery và backlog ra sao? |
| Hệ thống | CPU, heap, GC, latency, lag và throughput | Khi tải vượt khả năng xử lý, hệ thống ổn định hay tăng backlog vô hạn? |

Không được kết luận “có backpressure end-to-end” chỉ vì function nhận `Flux<T>`. Cần có bằng chứng rằng demand từ consumer được truyền tới nơi có thể điều tiết việc lấy message, hoặc có giới hạn buffer rõ ràng ở mọi ranh giới.

## 2. Reactive function trong Spring Cloud Stream

Spring Cloud Function hỗ trợ kiểu hàm reactive như `Function<Flux<I>, Flux<O>>`. Function nhận một publisher và thiết lập các toán tử xử lý. Ví dụ:

~~~java
import java.time.Duration;
import java.util.function.Function;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import reactor.core.publisher.Flux;

@Configuration
public class OrderReactiveFunctions {

    @Bean
    Function<Flux<OrderEvent>, Flux<OrderEvent>> processOrders() {
        return events -> events
            .map(this::normalize)
            .filter(this::isValid)
            .delayElements(Duration.ofMillis(50));
    }

    private OrderEvent normalize(OrderEvent event) {
        return new OrderEvent(
            event.eventId(),
            event.orderId() == null ? null : event.orderId().trim(),
            event.total()
        );
    }

    private boolean isValid(OrderEvent event) {
        return event.orderId() != null
            && !event.orderId().isBlank()
            && event.total() > 0;
    }

    public record OrderEvent(
        String eventId,
        String orderId,
        long total
    ) {}
}
~~~

Trong ví dụ, `delayElements` làm chậm tốc độ phát kết quả để mô phỏng downstream chậm. Function reactive được gọi để tạo pipeline; các phần tử được xử lý khi publisher được subscribe. Không gọi `subscribe()` thủ công bên trong function vì framework quản lý vòng đời subscription. Không dùng `block()` để chờ từng message trong luồng production.

Cấu hình input/output binding:

~~~yaml
spring:
  cloud:
    function:
      definition: processOrders

    stream:
      bindings:
        processOrders-in-0:
          destination: orders.raw
          group: order-processor
          content-type: application/json

        processOrders-out-0:
          destination: orders.processed
          content-type: application/json
~~~

Đây là ví dụ reactive function có output. Nếu dùng `Consumer<Flux<T>>`, function không có output binding; nếu dùng `Function<Flux<T>, Flux<R>>`, kết quả đi tới output binding. Cần chọn đúng kiểu hàm cho mục đích kiểm thử.

### Theo dõi demand trong pipeline

Có thể quan sát demand và thời điểm một phần tử đi qua:

~~~java
return events
    .doOnRequest(n ->
        log.debug("Reactive downstream requested {} events", n))
    .doOnNext(event ->
        log.debug("Processing eventId={}", event.eventId()))
    .limitRate(64)
    .map(this::normalize);
~~~

`doOnRequest` cho biết subscriber/operator yêu cầu bao nhiêu phần tử ở ranh giới quan sát đó. `limitRate(64)` chia request thành các đợt nhỏ hơn để điều tiết demand được gửi lên publisher phía trước. Đây là công cụ điều tiết trong Reactive Streams; nó không tự cấu hình Kafka poll, Rabbit prefetch hay Pulsar permits nếu binder không nối các cơ chế đó với demand.

Đặt log demand ở mức DEBUG hoặc dùng metric tổng hợp. Không tạo metric có label event ID vì cardinality sẽ tăng theo từng message.

## 3. Operator có thể làm thay đổi backpressure

Một pipeline có thể hỗ trợ demand ở đầu vào nhưng lại tạo buffer lớn ở giữa. Cần hiểu hành vi của từng operator:

| Operator | Tác động | Điều cần đánh giá |
|---|---|---|
| `map` | Biến đổi đồng bộ một phần tử | Thường giữ demand theo luồng |
| `filter` | Bỏ phần tử không đạt điều kiện | Có thể cần đọc thêm phần tử để đáp ứng demand đầu ra |
| `concatMap` | Xử lý publisher con tuần tự | Giữ thứ tự, nhưng tốc độ bị giới hạn bởi phần tử chậm |
| `flatMap` | Chạy nhiều publisher con đồng thời | Tăng throughput; giới hạn concurrency và prefetch |
| `flatMapSequential` | Xử lý đồng thời nhưng phát theo thứ tự nguồn | Có thể phải giữ kết quả hoàn thành sớm trong buffer |
| `publishOn` | Chuyển xử lý sang scheduler khác | Có hàng đợi và prefetch ở ranh giới scheduler |
| `limitRate` | Chia nhỏ request gửi upstream | Không bảo đảm điều tiết broker nếu adapter không truyền demand |
| `onBackpressureBuffer` | Giữ phần tử khi downstream không theo kịp | Cần giới hạn dung lượng và chính sách overflow |
| `onBackpressureDrop` | Bỏ phần tử khi không có demand | Chỉ phù hợp dữ liệu được phép mất |
| `onBackpressureLatest` | Giữ giá trị mới nhất | Phù hợp snapshot/trạng thái, không phù hợp event cần xử lý đủ |
| `onBackpressureError` | Phát lỗi khi không thể đáp ứng demand | Cần định nghĩa retry, DLQ hoặc dừng pipeline |

Ví dụ buffer có giới hạn:

~~~java
import reactor.core.publisher.BufferOverflowStrategy;

return events
    .onBackpressureBuffer(
        500,
        dropped -> log.error(
            "Backpressure buffer overflow for eventId={}",
            dropped.eventId()
        ),
        BufferOverflowStrategy.ERROR
    )
    .map(this::normalize);
~~~

Khi buffer đạt giới hạn, pipeline phát lỗi thay vì tiếp tục tăng bộ nhớ vô hạn. Tùy vị trí operator và nguồn publisher, `onBackpressureBuffer` có thể yêu cầu upstream phát không giới hạn rồi tự đệm. Điều đó có nghĩa nó có thể chuyển áp lực từ upstream sang buffer, chứ không truyền nguyên vẹn backpressure về nguồn. Hãy xem đây là một chính sách giới hạn và overflow, không phải bằng chứng flow control của broker.

Với dữ liệu telemetry có thể mất, `onBackpressureDrop` có thể phù hợp nếu có metric đếm số phần tử bị bỏ. Với trạng thái chỉ cần giá trị mới nhất, `onBackpressureLatest` có thể hữu ích. Với đơn hàng, thanh toán hoặc event kiểm toán, drop/latest thường không chấp nhận được; cần buffer bền vững, retry, broker retention và phục hồi có kiểm soát.

## 4. Kafka binder: poll, partition và giới hạn lượng đọc

Kafka consumer dùng mô hình pull: consumer gọi `poll()` để lấy record từ các partition đã được gán. Các thuộc tính như `max.poll.records` giới hạn số record trả về trong một lần poll. `fetch.min.bytes` và `fetch.max.wait.ms` ảnh hưởng cách broker gom dữ liệu trước khi trả fetch response.

Ví dụ cấu hình giới hạn số record mỗi lần poll:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        processOrders-in-0:
          consumer:
            concurrency: 2

      kafka:
        bindings:
          processOrders-in-0:
            consumer:
              configuration:
                max.poll.records: 100
                fetch.max.wait.ms: 500
~~~

`max.poll.records` là giới hạn số record trả về cho một lần poll của Kafka consumer; nó không phải giới hạn tổng số message đang tồn tại trong binder, Reactor hoặc ứng dụng. `concurrency` tạo nhiều consumer thread theo binding. Với Kafka, số consumer có thể hoạt động hữu ích trong một group bị giới hạn bởi số partition được gán.

Khi đánh giá tải, theo dõi:

- Consumer lag theo topic-partition và group.
- Số record mỗi poll, thời gian xử lý batch và thời gian giữa các lần poll.
- Số lần rebalance và thời gian consumer không có partition.
- Heap, GC và số message đang chờ trong ứng dụng.
- Thời gian xử lý từng event và tỷ lệ lỗi/retry.

Nếu downstream chậm, lag Kafka có thể tăng dù ứng dụng không tích lũy toàn bộ backlog trong heap. Đây là backlog được lưu bền vững ở broker. Tuy nhiên, batch đã được poll và các queue trung gian vẫn chiếm bộ nhớ. Cần đo số message đang in-flight và kích thước batch thực tế.

Không tăng `max.poll.records` chỉ để cải thiện throughput nếu xử lý batch làm vượt `max.poll.interval.ms` hoặc tăng bộ nhớ quá mức. Cũng không tăng concurrency khi số partition không đủ hoặc dịch vụ downstream đã quá tải. Việc điều tiết broker và việc điều tiết Reactor là hai lớp riêng; hãy kiểm tra binder version để xác nhận cơ chế pause/resume hoặc adapter cụ thể trước khi tuyên bố demand reactive được truyền tới Kafka poll loop.

## 5. RabbitMQ binder: prefetch và unacknowledged messages

RabbitMQ thường đẩy message tới consumer. QoS/prefetch giới hạn số delivery chưa được acknowledge mà consumer có thể giữ. Khi consumer xử lý chậm và đạt giới hạn prefetch, broker ngừng gửi thêm delivery cho consumer đó cho tới khi có acknowledgment và dung lượng được giải phóng.

Ví dụ:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        processOrders-in-0:
          destination: orders.raw
          group: order-processor

      rabbit:
        bindings:
          processOrders-in-0:
            consumer:
              prefetch: 50
~~~

`prefetch` là giới hạn delivery chưa được xác nhận theo cấu hình consumer/channel của binder. Giá trị hữu ích phụ thuộc kích thước message, thời gian xử lý, concurrency và số consumer. Prefetch quá thấp có thể giảm throughput do consumer thường xuyên chờ broker; quá cao có thể tăng lượng message in-flight, bộ nhớ và thời gian một message nằm trong consumer.

Khi thử nghiệm, theo dõi:

- Ready messages trong queue.
- Unacknowledged messages.
- Consumer utilization và tốc độ ack.
- Queue depth và tuổi message cũ nhất.
- Số lần redelivery, retry và DLQ.
- Số consumer, concurrency và prefetch hiệu lực.

Prefetch giới hạn delivery chưa xác nhận ở phía RabbitMQ. Nó không tự chứng minh rằng mọi queue Reactor trong ứng dụng đều có giới hạn tương ứng. Nếu binder đã nhận delivery rồi chuyển vào một hàng đợi nội bộ, cần đo cả queue đó và heap. Đọc tài liệu đúng phiên bản Rabbit binder để xác nhận quan hệ giữa listener container, acknowledgment và reactive function.

## 6. Pulsar binder: receiver queue và flow permits

Pulsar consumer dùng cơ chế flow control dựa trên permits. Client duy trì receiver queue để chứa message đã nhận trước khi ứng dụng xử lý. Khi queue được tiêu thụ, client gửi thêm permits để nhận message mới. Kích thước receiver queue ảnh hưởng lượng dữ liệu có thể nằm sẵn trong client.

Ví dụ minh họa cấu hình extended consumer property:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        processOrders-in-0:
          destination: orders.raw
          group: order-processor

      pulsar:
        bindings:
          processOrders-in-0:
            consumer:
              receiverQueueSize: 100
~~~

Tên property và cách ánh xạ có thể thay đổi theo phiên bản Spring Cloud Stream Pulsar binder và Pulsar client. Hãy xác nhận schema cấu hình của phiên bản đang dùng trước khi triển khai. Không suy ra giá trị mặc định hoặc semantics chỉ từ ví dụ YAML.

Khi đánh giá, đo:

- Subscription backlog và số message đang chờ.
- Receiver queue size hiệu lực.
- Tốc độ permit/delivery và acknowledgment.
- Số consumer đang attach vào subscription.
- Subscription type: Exclusive, Failover, Shared hoặc Key_Shared.
- Redelivery, negative acknowledgment và ack timeout.
- Bộ nhớ client và thời gian xử lý message.

Receiver queue và permits là flow control của Pulsar client. Chúng không tự chứng minh demand của một `Flux` đã truyền ngược tới broker. Cần kiểm tra binder có adapter reactive nào và cách adapter điều tiết consumer hay không. Đặc biệt khi dùng Shared hoặc Key_Shared, cần kiểm tra cách phân phối, thứ tự theo key và lượng message đang được giữ bởi mỗi consumer.

## 7. So sánh khả năng thực tế theo binder

| Binder | Cơ chế broker nổi bật | Tham số thường cần đo/điều chỉnh | Giới hạn cần lưu ý |
|---|---|---|---|
| Kafka | Pull bằng poll, fetch theo partition | `max.poll.records`, fetch settings, concurrency, partition count | Poll batch và lag; không mặc định demand Reactor điều khiển poll |
| RabbitMQ | Push delivery, QoS/prefetch, ack | `prefetch`, concurrency, ack mode | Prefetch giới hạn unacked delivery, nhưng queue nội bộ vẫn cần đo |
| Pulsar | Receiver queue và flow permits | `receiverQueueSize`, subscription type, ack/redelivery settings | Client queue/permits không đồng nghĩa Reactive Streams demand end-to-end |

Không có một con số prefetch hoặc concurrency phù hợp cho mọi binder. Kích thước message, thời gian xử lý, số partition/consumer, số instance, độ trễ mạng và giới hạn dịch vụ phụ thuộc đều ảnh hưởng kết quả.

Hãy lập bảng năng lực cho đúng phiên bản đang chạy:

| Câu hỏi đánh giá | Bằng chứng cần thu thập |
|---|---|
| Function có nhận `Flux<T>` không? | Kiểu function và log khởi động |
| Binder có truyền demand về consumer không? | Tài liệu phiên bản, mã/metric adapter hoặc phép thử có kiểm soát |
| Buffer nội bộ nằm ở đâu? | Cấu hình channel/executor/listener và số liệu queue/heap |
| Có giới hạn số message in-flight không? | Poll batch, prefetch, receiver queue, concurrency |
| Khi downstream dừng nhận, broker làm gì? | Lag/backlog tăng, delivery pause, permit ngừng cấp hoặc queue unacked đạt giới hạn |
| Khi buffer đầy, điều gì xảy ra? | Overflow error, drop, retry, redelivery hoặc tăng heap |
| Message được ack/commit lúc nào? | Ack mode, offset commit, transaction và log thực nghiệm |
| Khôi phục sau restart ra sao? | Replay, redelivery, duplicate và idempotency test |

## 8. Đo tốc độ vào, tốc độ xử lý và backlog

Backpressure chỉ hữu ích khi biết tốc độ đầu vào và năng lực xử lý. Gọi:

- `λ` (lambda): tốc độ message đến, tính bằng message/giây.
- `μ` (mu): năng lực xử lý ổn định, tính bằng message/giây.
- `B`: backlog đang chờ xử lý.

Nếu `λ < μ` trong thời gian đủ dài, hệ thống có thể bắt kịp dữ liệu. Nếu `λ > μ` kéo dài, backlog tăng xấp xỉ theo chênh lệch `λ - μ`, trừ khi broker hoặc nguồn có cơ chế điều tiết, dữ liệu bị drop hoặc producer bị giảm tốc.

Ví dụ một consumer xử lý tuần tự mất trung bình 100 ms cho mỗi message thì năng lực lý thuyết xấp xỉ 10 message/giây, chưa tính overhead. Nếu có bốn tác vụ độc lập chạy đồng thời và downstream chịu được tải, năng lực có thể tăng gần bốn lần; thực tế còn phụ thuộc CPU, I/O, lock, partition và giới hạn API.

Đo tối thiểu các chỉ số sau:

| Chỉ số | Cách dùng |
|---|---|
| Ingress rate | Xác định tốc độ producer đưa dữ liệu vào |
| Completion rate | Đo tốc độ xử lý thành công |
| Processing latency | Phát hiện bước nào chậm |
| Backlog/lag | Đo lượng công việc đang chờ |
| In-flight/unacked | Đo message đã giao nhưng chưa hoàn tất |
| Buffer occupancy | Phát hiện queue nội bộ gần đầy |
| Overflow/drop count | Xác định dữ liệu bị mất hoặc pipeline bị lỗi |
| Heap/GC | Phát hiện buffer gây áp lực bộ nhớ |
| Retry/redelivery | Phát hiện lỗi làm tăng công việc lặp |

Không chỉ nhìn throughput trung bình. Dùng p95/p99 latency, backlog theo thời gian và độ tuổi message cũ nhất để phát hiện tình trạng hàng đợi tăng dù throughput trung bình vẫn có vẻ ổn định.

## 9. Thiết kế phép thử backpressure có kiểm soát

Phép thử cần tạo ra tải lớn hơn khả năng xử lý trong một khoảng thời gian, rồi quan sát nơi backlog xuất hiện.

### Bước 1: Thiết lập baseline

- Chạy một broker và một consumer instance.
- Gửi message với tốc độ thấp hơn khả năng xử lý dự kiến.
- Ghi ingress rate, completion rate, latency, lag/backlog và heap.
- Xác nhận không có lỗi serialization, retry hoặc redelivery ngoài dự kiến.

### Bước 2: Làm chậm downstream

Tạm thời làm chậm function bằng một độ trễ có kiểm soát:

~~~java
@Bean
Function<Flux<OrderEvent>, Flux<OrderEvent>> slowProcessor() {
    return events -> events
        .doOnRequest(n -> log.debug("requested={}", n))
        .concatMap(event ->
            Mono.delay(Duration.ofMillis(100))
                .thenReturn(event)
        );
}
~~~

Đoạn minh họa cần các import `reactor.core.publisher.Mono`, `reactor.core.publisher.Flux`, `java.time.Duration` và `java.util.function.Function`. Dùng `concatMap` để xử lý tuần tự; với độ trễ 100 ms, một subscription chỉ xử lý khoảng 10 message/giây theo lý thuyết.

### Bước 3: Tăng tải theo từng mức

Tăng tốc độ producer theo từng bậc, ví dụ 5, 10, 20, 50 và 100 message/giây. Mỗi mức giữ đủ lâu để backlog và latency thể hiện xu hướng ổn định hoặc tăng dần. Không nhảy ngay lên tải cực đại vì khó xác định ngưỡng bắt đầu mất ổn định.

### Bước 4: Quan sát từng lớp

- Reactor: demand, operator prefetch, buffer occupancy và overflow.
- Ứng dụng: heap, GC, số task đang chạy, thread và latency.
- Binder: poll batch, listener concurrency, prefetch hoặc receiver queue.
- Broker: Kafka lag, Rabbit ready/unacked, Pulsar subscription backlog.
- Nghiệp vụ: số event hoàn tất, duplicate, drop và lỗi.

### Bước 5: Thử giảm tải và phục hồi

Giảm tốc độ producer xuống thấp hơn năng lực consumer. Backlog phải giảm dần và hệ thống phải trở về latency bình thường. Sau đó restart một consumer khi còn backlog để kiểm tra message được tiếp tục, redeliver hoặc replay theo đúng semantics đã cấu hình.

## 10. Cách diễn giải kết quả thử nghiệm

| Quan sát | Diễn giải có thể | Việc cần kiểm tra |
|---|---|---|
| Reactor demand giảm, Kafka lag tăng, heap ổn định | Broker giữ phần lớn backlog; consumer không kéo kịp | Poll cadence, batch và partition |
| Reactor demand giảm nhưng Rabbit unacked tăng tới prefetch | Broker đã giao tối đa số message cho phép | Ack timing, listener/binder buffer |
| Pulsar receiver queue đầy và permits chậm cấp | Client đang hạn chế nhận thêm message | Receiver queue, ack và subscription type |
| Heap tăng đều khi ingress lớn hơn completion | Có buffer hoặc queue nội bộ tăng | Tìm queue không giới hạn, operator prefetch, executor |
| Backlog không tăng nhưng drop counter tăng | Chính sách drop đang loại dữ liệu | Xác nhận dữ liệu có được phép mất không |
| Latency tăng mạnh trước khi backlog tăng | Consumer hoặc dependency bắt đầu bão hòa | CPU, I/O, connection pool, concurrency |
| Restart làm message được xử lý lại | Ack/commit chưa hoàn tất hoặc offset chưa được lưu | Idempotency và transaction boundary |
| Tăng concurrency không tăng throughput | Bottleneck nằm ở partition, CPU hoặc dependency | Partition count, downstream rate limit và lock |

Một phép thử đạt yêu cầu không nhất thiết phải giữ backlog bằng 0. Với hệ thống event, broker thường là nơi lưu backlog bền vững khi producer nhanh hơn consumer. Mục tiêu là backlog tăng có kiểm soát, bộ nhớ ứng dụng có giới hạn, không mất message ngoài chính sách, và hệ thống có thể bắt kịp sau khi tải giảm.

## 11. Chọn chính sách khi downstream không theo kịp

Có bốn lựa chọn phổ biến. Mỗi lựa chọn có hệ quả nghiệp vụ khác nhau:

| Chính sách | Khi phù hợp | Rủi ro |
|---|---|---|
| Điều tiết nguồn/consumer | Có thể giảm tốc producer hoặc broker delivery | Tăng độ trễ, backlog nằm ở broker hoặc nguồn |
| Buffer có giới hạn | Cần hấp thụ burst ngắn | Khi đầy phải có overflow policy |
| Drop/latest | Dữ liệu telemetry hoặc snapshot được phép mất | Không phù hợp event nghiệp vụ cần đầy đủ |
| Fail/retry/persist | Event quan trọng cần được xử lý lại | Có thể tăng backlog, retry storm hoặc redelivery |

Không dùng buffer vô hạn để che giấu việc consumer không đủ năng lực. Buffer chỉ chuyển nơi lưu backlog và có thể làm heap tăng tới mức ứng dụng bị OOM. Với event quan trọng, ưu tiên broker retention, consumer lag có thể quan sát, retry có giới hạn và idempotency.

Khi dùng `onBackpressureBuffer`, đặt giới hạn và định nghĩa hành vi khi đầy. Khi dùng drop, phải có counter và cảnh báo. Khi fail, bảo đảm lỗi đi vào cơ chế phục hồi phù hợp và không bị chuyển thành success giả. Khi giảm tốc producer, cần xác định ai chịu trách nhiệm điều tiết và cách xử lý khi producer không thể pause.

## 12. Kiểm thử bằng StepVerifier và test binder

Unit test với Reactor có thể xác nhận pipeline tôn trọng demand ở cấp publisher:

~~~java
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

class BackpressurePipelineTest {

    @Test
    void emitsOnlyWhenTheSubscriberRequests() {
        Flux<Integer> source = Flux.range(1, 5);

        StepVerifier.create(source, 0)
            .thenRequest(2)
            .expectNext(1, 2)
            .thenRequest(1)
            .expectNext(3)
            .thenRequest(2)
            .expectNext(4, 5)
            .verifyComplete();
    }
}
~~~

Test này chứng minh publisher Reactor phát theo demand. Nó không chứng minh binder chuyển `request(n)` thành Kafka pause, Rabbit prefetch hoặc Pulsar permits.

Test binder của Spring Cloud Stream giúp kiểm tra function và binding trong ứng dụng. Tuy nhiên, test binder không mô phỏng đầy đủ flow control của broker thật. Cần integration test riêng cho từng binder:

- Kafka: tạo topic có nhiều partition, làm chậm consumer, quan sát lag, poll batch, rebalance và heap.
- RabbitMQ: đặt prefetch hữu hạn, làm chậm handler, quan sát ready/unacked và acknowledgment.
- Pulsar: đặt receiver queue phù hợp, làm chậm handler, quan sát backlog, permits, ack và subscription type.

Trong integration test, ghi lại phiên bản Spring Cloud Stream, binder, broker, cấu hình và kết quả. Nếu nâng version, chạy lại phép thử vì adapter, listener container và thuộc tính binder có thể thay đổi.

## 13. Checklist đánh giá binder trước khi triển khai

| Hạng mục | Bằng chứng cần có |
|---|---|
| Reactive API | Function có dùng đúng kiểu `Flux`/`Mono` và không tự subscribe/block |
| Demand propagation | Có bằng chứng binder truyền demand hoặc mô tả rõ ranh giới không hỗ trợ |
| Internal buffering | Biết các queue, executor và prefetch nằm ở đâu |
| Buffer bounds | Có giới hạn kích thước và overflow policy |
| Broker flow control | Đã cấu hình và đo poll, prefetch hoặc receiver queue/permits |
| In-flight limit | Biết số message có thể đang xử lý hoặc chờ ack đồng thời |
| Ack/commit | Xác định thời điểm message được xác nhận |
| Failure recovery | Retry, redelivery, DLQ/quarantine và replay đã được kiểm thử |
| Data integrity | Không drop event quan trọng; consumer idempotent |
| Observability | Có ingress/completion rate, latency, lag/backlog, heap và overflow |
| Load test | Có kết quả ở baseline, overload và recovery |
| Version evidence | Ghi lại version Spring Cloud Stream, binder và broker |

## 14. Trình tự thực hành và tiêu chí hoàn thành

Thực hiện cùng một function xử lý đơn hàng trên các binder được sử dụng trong dự án:

1. Viết reactive function nhận `Flux<OrderEvent>` và trả `Flux<OrderEvent>`.
2. Thêm `doOnRequest` để quan sát demand, dùng `limitRate` để thử chia request.
3. Tạo một downstream chậm có độ trễ xác định.
4. Chạy baseline và ghi ingress rate, completion rate, latency, backlog và heap.
5. Với Kafka, thay đổi `max.poll.records`, concurrency và partition count; quan sát lag và poll behavior.
6. Với RabbitMQ, thay đổi `prefetch`; quan sát ready/unacked và ack rate.
7. Với Pulsar, thay đổi receiver queue size; quan sát backlog, permits và ack.
8. Thử buffer hữu hạn và overflow; xác nhận ứng dụng không tăng heap vô hạn.
9. Thử drop/latest chỉ trên dữ liệu giả lập được phép mất và đo số phần tử bị bỏ.
10. Dừng consumer, khởi động lại và xác nhận redelivery/replay không làm lặp side effect.
11. Ghi lại giới hạn thực tế của từng binder và chọn cấu hình theo kết quả đo.

Hoàn thành bài khi có thể phân biệt Reactive Streams demand với broker flow control; giải thích được binder cụ thể đang điều tiết ở đâu; đo được giới hạn in-flight và backlog; xác định được buffer có giới hạn hay không; và chứng minh hệ thống chịu được overload rồi phục hồi mà không mất event ngoài chính sách.

## 15. Tài liệu tham khảo chính thức

- [Spring Cloud Stream Reference](https://docs.spring.io/spring-cloud-stream/reference/index.html) — mô hình function, binding và binder.
- [Spring Cloud Stream — Reactive programming](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/reactive-programming.html) — cách dùng reactive function trong Spring Cloud Stream.
- [Spring Cloud Stream — Kafka binder](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-binder/overview.html) — cấu hình Kafka consumer và binder.
- [Apache Kafka — Consumer configs](https://kafka.apache.org/documentation/#consumerconfigs) — poll, fetch và giới hạn record.
- [Spring Cloud Stream — RabbitMQ binder](https://docs.spring.io/spring-cloud-stream/docs/current/reference/html/spring-cloud-stream-binder-rabbit.html) — prefetch, concurrency và consumer properties.
- [RabbitMQ — Consumer prefetch](https://www.rabbitmq.com/docs/confirms#channel-qos-prefetch) — QoS và giới hạn unacknowledged delivery.
- [Spring Cloud Stream — Pulsar binder](https://docs.spring.io/spring-cloud-stream/reference/pulsar/pulsar_binder.html) — consumer properties của Pulsar binder.
- [Apache Pulsar — Messaging](https://pulsar.apache.org/docs/concepts-messaging/) — consumer, subscription và flow control.
- [Reactive Streams Specification](https://www.reactive-streams.org/) — demand và giao thức backpressure.
- [Project Reactor — Backpressure](https://projectreactor.io/docs/core/release/reference/coreFeatures/backpressure.html) — operator và chiến lược backpressure.
- [Project Reactor — StepVerifier](https://projectreactor.io/docs/test/release/api/reactor/test/StepVerifier.html) — kiểm thử demand và publisher.

