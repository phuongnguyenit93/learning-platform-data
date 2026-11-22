# PauseImmediate

Khi một Kafka consumer xử lý dữ liệu nhanh hơn khả năng tiếp nhận của database, HTTP API hoặc executor phía sau, hệ thống cần **backpressure** để ngăn downstream quá tải. Spring Kafka cho phép gọi **pause()** trên listener container để tạm ngừng giao records mới vào listener mà không phải stop và restart toàn bộ consumer.

**pauseImmediate** là thuộc tính của **ContainerProperties**, được bổ sung từ Spring Kafka 2.9. Nó thay đổi **thời điểm yêu cầu pause có hiệu lực với record listener**:

- **pauseImmediate=false (mặc định):** container tiếp tục xử lý hết các records từ lần poll trước, sau đó mới pause.
- **pauseImmediate=true:** container áp dụng pause sau khi **record đang xử lý hiện tại** kết thúc; records còn lại của poll được giữ trong bộ nhớ và giao cho listener khi resume.

Immediate **không có nghĩa interrupt method đang chạy**. Pause không tự acknowledge records, không làm mất dữ liệu Kafka và không thay thế retry. Bài này thuộc chương **Pause và backpressure** của **Spring Kafka Reliability Operations**, tập trung vào ranh giới xử lý, offset, API điều khiển, memory, concurrency và vận hành.

## 1. Vì sao cần pause listener container?

Giả sử orders consumer có ba pods, mỗi pod chạy concurrency=4. Tổng cộng có 12 consumer threads có khả năng gọi database song song. Khi database connection pool bão hòa, mỗi lời gọi chậm hơn và có thể timeout.

Nếu tiếp tục xử lý không giới hạn:

- Các listener invocations mới tạo thêm request vào pool đã quá tải.
- Timeout kéo theo retry, khiến tổng số request có thể tăng.
- Async executor queue phình to nếu listener chỉ submit task rồi return.
- Memory, thread pool và CPU có thể bị sử dụng quá mức.
- Consumer lag tăng vì tốc độ hoàn tất business processing giảm.
- Rebalance có thể xảy ra nếu listener không quay lại poll trong khoảng max.poll.interval.ms.

**Pause** làm giảm tốc độ giao thêm công việc, cho downstream có thời gian phục hồi. Nhưng producers vẫn có thể ghi vào Kafka. Vì thế lag có thể tiếp tục tăng trong lúc paused; cần theo dõi retention và khả năng catch up sau resume.

### 1.1 Pause khác stop

| API | Ý nghĩa | Hệ quả |
|---|---|---|
| container.pause() | Yêu cầu tạm ngừng tiêu thụ | Container vẫn chạy và có thể poll để duy trì consumer group |
| container.resume() | Yêu cầu tiếp tục tiêu thụ | Records được giao tiếp khi resume |
| container.stop() | Kết thúc lifecycle | Consumer đóng, partition có thể được gán lại |
| KafkaConsumer.pause(partitions) | API thấp trên một consumer | Phải tôn trọng consumer thread ownership |

Với backpressure tạm thời, dùng container.pause()/resume() thường phù hợp hơn stop/restart. Không gọi KafkaConsumer.pause() trực tiếp từ HTTP controller hay scheduler thread khác.

## 2. Vì sao pause mặc định có thể phản ứng chậm?

KafkaConsumer.poll() có thể trả về **nhiều records**. Với record listener, Spring Kafka gọi listener riêng cho các records trong kết quả poll.

Giả sử một poll đã trả A, B, C, D, E. Container đã hoàn tất A và B, hiện đang xử lý C. Một thread khác phát hiện downstream overload và gọi pause().

Khi pauseImmediate=false, chuỗi có thể là:

~~~text
poll -> [A, B, C, D, E]
handle(A) -> done
handle(B) -> done
handle(C) -> đang chạy
pause() requested
handle(C) -> done
handle(D) -> done
handle(E) -> done
consumer paused
~~~

Yêu cầu pause chỉ có hiệu lực sau khi container xử lý hết records từ poll đó. Nếu poll lớn và listener chậm, độ trễ từ lúc yêu cầu đến lúc paused có thể kéo dài.

### 2.1 pauseImmediate=true

Khi bật true, chuỗi trở thành:

~~~text
poll -> [A, B, C, D, E]
handle(A) -> done
handle(B) -> done
handle(C) -> đang chạy
pause() requested
handle(C) -> done
consumer paused
D, E retained in memory

... downstream phục hồi ...

resume()
handle(D) -> done
handle(E) -> done
~~~

D và E được giữ để tiếp tục sau resume. PauseImmediate giảm số listener invocations khởi động sau yêu cầu pause, không thay đổi nội dung các records đã được poll.

### 2.2 Không hủy record hiện tại

Nếu handle(C) chờ một HTTP call 40 giây, pauseImmediate=true vẫn không thể cắt ngang C. Container cần đợi invocation hiện tại hoàn tất hoặc được xử lý exception đúng cơ chế.

Điều này có nghĩa:

- Pause latency phụ thuộc thời gian còn lại của current record.
- Phải đặt timeout hữu hạn cho database/HTTP.
- Không dùng pause để che listener treo.
- Nếu listener không poll trở lại đúng hạn, max.poll.interval.ms vẫn có thể bị vượt.
- Với async work, pause không tự cancel các tasks đã submit.

## 3. Cấu hình trong ConcurrentKafkaListenerContainerFactory

Có thể đặt pauseImmediate trực tiếp trên ContainerProperties:

~~~java
@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
ordersListenerFactory(
        ConsumerFactory<String, OrderEvent> consumerFactory,
        CommonErrorHandler errorHandler) {

    var factory =
        new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();

    factory.setConsumerFactory(consumerFactory);
    factory.setCommonErrorHandler(errorHandler);
    factory.setConcurrency(3);
    factory.setBatchListener(false);

    factory.getContainerProperties().setPauseImmediate(true);
    factory.getContainerProperties().setAckMode(
        ContainerProperties.AckMode.RECORD
    );

    return factory;
}
~~~

Record listener sử dụng factory:

~~~java
@Component
public class OrderListener {

    private final OrderService service;

    public OrderListener(OrderService service) {
        this.service = service;
    }

    @KafkaListener(
        id = "orders-projection",
        topics = "orders",
        groupId = "orders-projection-prod",
        containerFactory = "ordersListenerFactory"
    )
    public void handle(OrderEvent event) {
        service.apply(event);
    }
}
~~~

OrderEvent, OrderService và errorHandler được giả định đã tồn tại trong ứng dụng; ví dụ cần imports, serializer/deserializer và consumer properties phù hợp.

**setPauseImmediate(true) chỉ cấu hình hành vi khi được yêu cầu pause.** Nó không khiến listener container khởi động trong trạng thái paused.

### 3.1 Phiên bản và phạm vi

- Thuộc tính được giới thiệu trong Spring Kafka **2.9**.
- Giá trị mặc định là **false**.
- Nó được mô tả cho **record listener**.
- Để cấu hình chắc chắn trên factory custom, dùng factory.getContainerProperties().setPauseImmediate(true).
- Không tự giả định một YAML property với tên tương tự có sẵn trong mọi Spring Boot version.
- Nếu có nhiều container factories, phải cấu hình đúng factory của listener muốn điều tiết.

### 3.2 Batch listener khác record listener

Batch listener nhận nhiều records trong **một lời gọi method**:

~~~java
@KafkaListener(
    topics = "orders",
    containerFactory = "ordersBatchFactory"
)
public void handleBatch(List<OrderEvent> events) {
    service.processBatch(events);
}
~~~

PauseImmediate không tự chia đôi lời gọi processBatch() đang chạy tại phần tử thứ N. Muốn backpressure ở giữa batch, phải thiết kế batch processing, sizing, acknowledgment và partial retry riêng.

Không dùng tính năng dành cho record listener như lời hứa “batch listener sẽ dừng giữa List ngay lập tức”.

## 4. Gọi pause() và resume() qua registry

Với @KafkaListener, có thể lấy container bằng listener ID qua KafkaListenerEndpointRegistry.

~~~java
@Service
public class OrderConsumptionControl {

    private final KafkaListenerEndpointRegistry registry;

    public OrderConsumptionControl(
            KafkaListenerEndpointRegistry registry) {
        this.registry = registry;
    }

    public void pause() {
        MessageListenerContainer container = container();
        if (!container.isPauseRequested()) {
            container.pause();
        }
    }

    public void resume() {
        MessageListenerContainer container = container();
        if (container.isPauseRequested()) {
            container.resume();
        }
    }

    public boolean pauseRequested() {
        return container().isPauseRequested();
    }

    public boolean consumerPaused() {
        return container().isConsumerPaused();
    }

    private MessageListenerContainer container() {
        MessageListenerContainer result =
            registry.getListenerContainer("orders-projection");

        if (result == null) {
            throw new IllegalStateException(
                "orders-projection container not found"
            );
        }
        return result;
    }
}
~~~

Nếu container không được @KafkaListener registry quản lý mà là bean khai báo trực tiếp, có thể inject bean đó thay vì tìm qua registry.

### 4.1 Pause request khác pause thực tế

**isPauseRequested()** báo đã có yêu cầu pause. **isConsumerPaused()** báo Kafka consumers bên dưới đã ở trạng thái pause thực tế, với cách tổng hợp thích hợp cho concurrent container.

Một trạng thái hoàn toàn hợp lệ:

~~~text
pauseRequested = true
consumerPaused = false
~~~

Lúc này record hiện tại có thể vẫn đang chạy hoặc một child chưa kịp áp dụng pause. API quản trị không nên trả “all consumers paused” ngay sau khi gọi pause(), nếu chưa xác minh trạng thái thực.

### 4.2 Không điều khiển KafkaConsumer trực tiếp từ thread khác

KafkaConsumer không thread-safe cho phần lớn operations. Container API cho phép yêu cầu pause/resume từ một service hoặc scheduler và để Spring Kafka áp dụng theo lifecycle consumer.

Không tự lấy Consumer object từ listener callback rồi gọi consumer.pause() trên HTTP request thread. Việc đó có thể gây race với poll và trạng thái assignment.

## 5. Poll vẫn quan trọng khi paused

Khi container paused, Spring Kafka vẫn có thể gọi poll phù hợp để duy trì group membership. Điều đó khác với việc chặn hẳn consumer thread bằng Thread.sleep() rất lâu.

### 5.1 pollTimeoutWhilePaused

Một số phiên bản Spring Kafka hỗ trợ thuộc tính pollTimeoutWhilePaused để điều chỉnh timeout poll trong trạng thái paused.

~~~java
factory.getContainerProperties()
       .setPollTimeoutWhilePaused(Duration.ofMillis(100));
~~~

Tài liệu Spring Kafka hiện đại cho biết giá trị mặc định thường là **100 ms**. Timeout nên lớn hơn 0 để tránh tight loop tiêu thụ CPU khi consumer paused.

| Cấu hình | Điều khiển |
|---|---|
| pauseImmediate | Ranh giới áp dụng pause khi record listener đang xử lý poll |
| pollTimeoutWhilePaused | Timeout của poll khi container đang paused |
| max.poll.records | Số record tối đa một consumer nhận về trong một poll |
| max.poll.interval.ms | Giới hạn thời gian giữa các poll trước nguy cơ mất assignment |

Giảm poll timeout không làm listener hiện tại kết thúc nhanh hơn. pauseImmediate cũng không làm một HTTP call đang treo tự hết timeout.

### 5.2 Consumer group membership

Pause khác stop vì consumer có thể tiếp tục poll mà không nhận data records từ các partitions paused, giúp duy trì group membership. Tuy nhiên, nếu record hiện tại xử lý quá lâu khiến poll không thể tiếp tục, consumer vẫn có thể rebalance.

Không tuyên bố rằng pause bảo đảm 100% không có rebalance trong mọi lỗi hạ tầng.

## 6. Records còn lại được giữ trong memory

Khi pauseImmediate=true, records còn lại từ poll trước được giữ trong bộ nhớ container. Đây là cách Spring Kafka tiếp tục giao dữ liệu sau resume mà không cần application tự re-publish records.

Ví dụ một consumer poll 200 records, đã xử lý 61 records rồi pause. Phần còn lại có thể đang được giữ ở bộ nhớ cho đến resume.

### 6.1 Tác động tới memory budget

Giả sử concurrency=4, max.poll.records=500. Mỗi child có thể giữ một phần records riêng. Tổng số records đang giữ phụ thuộc:

- Số child consumers.
- Số records trả về từ các poll.
- Số records đã xử lý trước pause.
- Kích thước keys, values, headers và object graph.
- Runtime allocation, GC và deserializer.

Không dùng max.poll.records như giới hạn bytes. Một poll có 100 payload lớn có thể cần bộ nhớ nhiều hơn một poll có 500 payload nhỏ.

### 6.2 Giảm max.poll.records

~~~yaml
spring:
  kafka:
    consumer:
      properties:
        max.poll.records: 100
~~~

Giảm số records mỗi poll có thể giảm số records buffered khi pause. Nhưng nó cũng có thể làm throughput thay đổi. Cần đo workload thực tế; không đặt max.poll.records cực nhỏ chỉ để đạt một pause latency nhất định.

### 6.3 Buffer memory không bền vững

Nếu pod chết trong lúc D/E đang retained, process memory mất. Consumer mới sẽ đọc lại từ committed offset theo Kafka log và retention.

Một số records xử lý thành công trước đó cũng có thể bị redelivery nếu offset chưa commit kịp. Vì vậy listener và downstream side effects vẫn cần idempotency.

## 7. Offset commit và acknowledgment

PauseImmediate không tự mark những records được poll là thành công. Nó không phải một cơ chế offset commit.

### 7.1 AckMode.RECORD

Với record listener và AckMode.RECORD, container thường commit offset sau record được xử lý thành công theo commit policy tương ứng.

~~~text
A processed
B processed
C processed
PAUSED
D retained, not processed
E retained, not processed
~~~

D/E chưa được coi là business success chỉ vì chúng có trong buffer. Nếu chưa được xử lý thì offset không nên được commit vượt qua chúng bởi logic application.

### 7.2 AckMode.BATCH

Record listener cũng có thể dùng AckMode.BATCH. Khi pause cắt giữa poll, commit timing của records đã xử lý cần được đánh giá theo phiên bản Spring Kafka và container semantics.

Không mặc định rằng pause luôn commit offset ngay sau record C. Nếu commit chưa hoàn tất, A/B/C có thể được giao lại sau restart.

### 7.3 Manual acknowledgment

Với AckMode.MANUAL hoặc MANUAL_IMMEDIATE, chỉ acknowledge sau khi side effect thực sự hoàn tất:

~~~java
@KafkaListener(
    topics = "orders",
    containerFactory = "manualOrdersFactory"
)
public void handle(
        ConsumerRecord<String, OrderEvent> record,
        Acknowledgment acknowledgment) {

    service.apply(record.value());
    acknowledgment.acknowledge();
}
~~~

Factory phải cấu hình AckMode phù hợp. Không đặt acknowledge trong finally: một lỗi nghiệp vụ không được tự động chuyển thành record thành công.

### 7.4 asyncAcks là cơ chế riêng

Spring Kafka có asyncAcks cho manual acknowledgments đến không đúng thứ tự theo các phiên bản hỗ trợ; container có thể pause khi cần chờ acknowledgments còn thiếu.

asyncAcks giải quyết **offset acknowledgment sequencing**, còn pauseImmediate quyết định **ranh giới giao records mới sau yêu cầu pause**. Nếu dùng cùng nhau, phải phân biệt nguyên nhân pause và tránh resume không đúng lúc.

## 8. Concurrency và nhiều child consumers

ConcurrentMessageListenerContainer parent tạo nhiều KafkaMessageListenerContainer child. Mỗi child quản lý KafkaConsumer và consumer thread riêng.

~~~mermaid
flowchart TD
    P["ConcurrentMessageListenerContainer"]
    P --> A["Child 0 / consumer 0"]
    P --> B["Child 1 / consumer 1"]
    P --> C["Child 2 / consumer 2"]
    A --> LA["Record listener"]
    B --> LB["Record listener"]
    C --> LC["Record listener"]
~~~

Nếu parent nhận pause request, các children áp dụng theo ranh giới xử lý của chính mình. Với pauseImmediate=true, mỗi child chờ record hiện tại kết thúc.

Ví dụ:

- Child 0 còn 20 ms trong record đang xử lý.
- Child 1 còn 500 ms.
- Child 2 còn 3 giây.

Parent có thể chỉ được coi là paused đầy đủ sau khi các child consumers tương ứng đã áp dụng pause. Không giả định cả ba dừng đúng cùng một thời điểm.

### 8.1 Tính cả deployment

Ba pods với concurrency=4 có tối đa 12 consumer members đang tham gia group. Mỗi member có poll buffer riêng. Khi thiết kế memory/backpressure, phải tính tổng instance count, concurrency, max.poll.records và kích thước records.

### 8.2 Pause không sửa phân phối tải không đều

Một partition có thể chứa nhiều records hơn partition khác. Pause parent sẽ ảnh hưởng toàn bộ children tương ứng, kể cả child xử lý các partition khỏe. Nếu cần điều tiết riêng một partition hoặc tenant, có thể cân nhắc partition-level pause APIs ở phiên bản Spring Kafka hỗ trợ, nhưng cần kiểm tra semantics riêng; không tự giả định pauseImmediate áp dụng cho mọi partition-control flow.

## 9. Điều tiết tự động bằng hysteresis

Một backpressure policy nên có **high watermark** để pause và **low watermark** để resume, thay vì một ngưỡng duy nhất gây dao động.

Ví dụ:

~~~text
downstream pending >= 800 : pause
downstream pending <= 300 : resume
300 < pending < 800     : giữ trạng thái hiện tại
~~~

Controller minh họa:

~~~java
public interface DownstreamLoad {
    long pendingTasks();
}
~~~

~~~java
@Component
public class OrdersBackpressureController {

    private final KafkaListenerEndpointRegistry registry;
    private final DownstreamLoad load;

    public OrdersBackpressureController(
            KafkaListenerEndpointRegistry registry,
            DownstreamLoad load) {
        this.registry = registry;
        this.load = load;
    }

    @Scheduled(fixedDelay = 2_000)
    public void regulate() {
        MessageListenerContainer container =
            registry.getListenerContainer("orders-projection");

        if (container == null || !container.isRunning()) {
            return;
        }

        long pending = load.pendingTasks();

        if (pending >= 800 && !container.isPauseRequested()) {
            container.pause();
        }
        else if (pending <= 300 && container.isPauseRequested()) {
            container.resume();
        }
    }
}
~~~

Để @Scheduled hoạt động cần bật scheduling trong Spring configuration, ví dụ @EnableScheduling. Số 800/300 chỉ minh họa và phải được hiệu chỉnh theo queue capacity/latency của downstream.

### 9.1 Chọn metric phù hợp

Nếu listener gọi database đồng bộ, pendingTasks trong executor có thể không phản ánh tải vì không có executor. Có thể sử dụng:

- Connection pool waiters.
- Database query p95/p99 latency.
- HTTP 429/503 rate.
- Circuit breaker trạng thái open/half-open.
- Số in-flight requests hoặc queue depth.
- CPU throttling, heap pressure.
- Backlog của worker pool hữu hạn.

Consumer lag tăng **không tự chứng minh cần pause**. Pause có thể làm lag tăng thêm; mục tiêu là bảo vệ downstream.

### 9.2 Không để auto-controller resume pause thủ công

Nếu operator pause để bảo trì rồi auto-controller thấy pendingTasks=0, lời gọi resume tự động có thể trái chủ đích.

Trong production, cần quản lý các lý do pause: MAINTENANCE, DOWNSTREAM_OVERLOAD, MANUAL_OPERATOR. Chỉ resume khi mọi lý do pause đã được giải quyết. Ví dụ code đơn giản phía trên giả định chỉ có một chủ sở hữu chính sách.

## 10. Pause không sửa queue async vô hạn

Anti-pattern:

~~~java
@KafkaListener(topics = "orders")
public void handle(OrderEvent event) {
    executor.submit(() -> service.apply(event));
}
~~~

Listener return ngay trong khi task còn chạy. Container có thể tiếp tục poll và commit offset trước khi task thực sự hoàn tất, tùy AckMode. Nếu pod chết, task chưa hoàn tất có thể mất dù offset đã tiến.

pauseImmediate chỉ giúp dừng **các listener invocations mới**, không tự hủy queue hoặc bảo đảm side effect hoàn tất.

Nếu dùng async processing, phải thiết kế:

- Bounded executor queue.
- Backpressure trên queue occupancy.
- Acknowledgment gắn với completion thực.
- Idempotency và per-key ordering.
- Graceful shutdown và task recovery.

Không coi pause là thay thế cho một durable job queue nếu business yêu cầu xử lý bền vững qua crash.

## 11. Observability: pause requested và pause effective

Spring Kafka cung cấp **ConsumerPausedEvent** và **ConsumerResumedEvent** khi container/consumer thay đổi trạng thái tương ứng.

~~~java
@Component
public class KafkaPauseEvents {

    @EventListener
    public void onPaused(ConsumerPausedEvent event) {
        log.info("Paused partitions={}", event.getPartitions());
    }

    @EventListener
    public void onResumed(ConsumerResumedEvent event) {
        log.info("Resumed partitions={}", event.getPartitions());
    }
}
~~~

Các event có thể liên quan child container và partition assignment. Để troubleshoot, nên gắn listener ID, client ID và topic-partition vào log nếu có thể.

### 11.1 Metrics gợi ý

| Metric | Mục đích |
|---|---|
| pause_requested_total | Số yêu cầu pause |
| resume_requested_total | Số yêu cầu resume |
| pause_request_to_effective_ms | Độ trễ áp dụng pause |
| pause_duration_seconds | Thời gian paused |
| listener_processing_duration | p95/p99 record latency |
| consumer_lag | Backlog Kafka |
| committed_offset_progression | Consumer có tiến sau resume không |
| rebalance_count | Có rebalance bất thường không |
| downstream_pool_waiters | Áp lực kết nối |
| downstream_error_rate | Dependency đã phục hồi chưa |

Đây là các tên gợi ý cho instrumentation, không phải tất cả tự tồn tại trong Micrometer mặc định.

### 11.2 Alert

Nên cảnh báo khi:

- Pause duration quá dài.
- Consumer lag vượt SLA hoặc retention budget.
- isPauseRequested=true lâu nhưng isConsumerPaused=false.
- Sau resume, offset vẫn không tiến và có records chờ.
- Downstream vẫn lỗi nhưng controller resume liên tục.
- Có những retry consumers khác tiếp tục gây quá tải trong khi main listener paused.

## 12. PauseImmediate kết hợp với error handler

Một record đang xử lý có thể ném exception đúng lúc pause request đến. Điều đó không làm record trở thành thành công.

**DefaultErrorHandler** xử lý retry/recovery theo policy và container phối hợp ack/offset. PauseImmediate chỉ kiểm soát việc dừng giao thêm records khi pause được yêu cầu.

Các điểm cần nhớ:

- Không nuốt exception rồi acknowledge chỉ để container pause.
- Retry/backoff có thể dùng cơ chế pause riêng; đừng resume khi backoff vẫn còn hiệu lực.
- asyncAcks có thể giữ consumer paused do acknowledgment thiếu.
- @RetryableTopic thường tạo retry listener containers riêng; pause main listener không tự pause tất cả retry consumers.
- Với transactional listener, exception có thể làm Kafka transaction abort và kích hoạt AfterRollbackProcessor; không suy luận offset từ riêng pause state.

### 12.1 Phân biệt pauseImmediate và stopImmediate

| Thuộc tính | Trigger | Ý nghĩa |
|---|---|---|
| pauseImmediate | container.pause() | Dừng giao records sau record hiện tại, giữ phần còn lại |
| stopImmediate | container.stop() | Dừng lifecycle sau record hiện tại thay vì hết poll, theo API/version |
| pollTimeoutWhilePaused | Container paused | Poll timeout sử dụng lúc paused |

Không dùng stopImmediate thay cho pauseImmediate chỉ vì tên gần giống. Stop làm thay đổi lifecycle và có thể gây rebalance.

## 13. Khi pause phản ứng chậm

Nếu pause() được gọi lúc 10:00:00 nhưng consumerPaused chỉ true lúc 10:00:25:

1. Kiểm tra pauseImmediate runtime đang true hay false.
2. Xác nhận record listener chứ không phải batch listener.
3. Đo latency của record hiện tại.
4. Xem max.poll.records và số records đã nhận từ poll trước.
5. Kiểm tra child consumers trong concurrent container.
6. Quan sát ConsumerPausedEvent theo child.
7. Kiểm tra thread starvation, CPU throttling hoặc GC pause.
8. Kiểm tra error handler, Kafka transaction hoặc downstream calls bị block.
9. Kiểm tra max.poll.interval.ms và rebalance events.
10. Đo lại request-to-pause latency sau điều chỉnh.

Nếu pauseImmediate=false và poll trước còn nhiều records, việc chờ hết poll có thể là hành vi đúng theo cấu hình, không phải lỗi Kafka.

Nếu pauseImmediate=true mà record hiện tại treo lâu, cần giải quyết timeout/dependency. Setting này không interrupt method.

## 14. Khi resume nhưng listener chưa chạy tiếp

Nguyên nhân có thể:

- Resume mới là request; consumer thread chưa áp dụng.
- Không còn data records đang chờ.
- Consumer chưa có assignment.
- Container đã stop hoặc ứng dụng đang shutting down.
- Có lý do pause khác.
- Error handler/backoff đang chờ retry.
- Broker không khả dụng hoặc consumer đang rebalance.
- Metrics/logging bị trễ.

Đừng gọi resume liên tục như một vòng loop nóng. Hãy kiểm tra ConsumerResumedEvent, isConsumerPaused(), assignment, consumer lag và offset progression.

Với policy tự động, dùng low watermark và một healthy window thay vì resume ngay khi lỗi giảm một thoáng.

## 15. Integration test cho PauseImmediate

Unit test gọi listener method trực tiếp không kiểm chứng consumer.poll, paused state hay retained records. Nên dùng Kafka broker thật qua Testcontainers hoặc staging.

### 15.1 Test so sánh false và true

1. Tạo topic một partition.
2. Gửi nhiều records để một poll có thể nhận A, B, C, D, E.
3. Listener sử dụng CountDownLatch để giữ record C đang chạy.
4. Gọi pause() trong lúc C chưa hoàn tất.
5. Với pauseImmediate=false, quan sát container có thể xử lý records còn lại trước pause.
6. Với pauseImmediate=true, release C rồi chờ isConsumerPaused().
7. Xác nhận D/E chưa được listener gọi trong lúc paused.
8. Gọi resume().
9. Xác nhận D/E tiếp tục được xử lý.

Cần bảo đảm **nhiều records thực sự thuộc một poll**; nếu mỗi poll chỉ trả một record thì hai modes có thể trông giống nhau.

### 15.2 Test không interrupt current record

- Giữ C trong listener bằng latch.
- Gửi pause request từ thread khác.
- Xác nhận C vẫn đang chạy trước khi release.
- Sau C kết thúc, kiểm tra pause effective.
- Không dùng assert thời gian 1 ms dễ flaky; dùng event/state và timeout hữu hạn.

### 15.3 Test crash trong lúc retained records

- Poll A-E, pause sau C.
- D/E chưa được xử lý.
- Dừng process/container trước resume.
- Khởi động lại consumer cùng group.
- Xác nhận records chưa commit có thể được giao lại.
- Xác nhận idempotency nếu records trước đó cũng redeliver.

### 15.4 Test concurrency và backpressure

- Chạy concurrency=3 với topic có ít nhất 3 partitions.
- Gửi pause ở parent khi child records có latency khác nhau.
- Quan sát child pause không đồng thời nhưng parent cuối cùng paused.
- Thử high/low watermark và kiểm tra controller không oscillate.
- Resume và xác nhận offset progression.
- Làm một record lỗi để kiểm tra error handler không bị pause bỏ qua.

## 16. Runbook khi downstream quá tải

1. Xác định Kafka listeners gọi dependency đang nghẽn.
2. Đo downstream pool wait, error rate, p95 latency và queue depth.
3. Kiểm tra concurrency, partitions, max.poll.records và memory budget.
4. Xác nhận listener factory có pauseImmediate=true nếu muốn pause sau current record.
5. Gửi pause qua MessageListenerContainer, không qua consumer API ở thread khác.
6. Đợi isConsumerPaused hoặc ConsumerPausedEvent để xác nhận pause thực.
7. Theo dõi in-flight work, ack/commit và error handler.
8. Theo dõi consumer lag, Kafka retention và khả năng catch up.
9. Khi downstream ổn định, resume theo low watermark và healthy window.
10. Xác nhận listener tiến triển, offset commit và error rate bình thường.
11. Nếu quá tải tái diễn, tăng capacity hoặc giảm upstream rate thay vì pause mãi.

Backpressure bảo vệ dependency trong lúc xảy ra sự cố hoặc spike, nhưng không giải quyết được bài toán dài hạn nếu tốc độ producer lớn hơn throughput tiêu thụ.

## 17. Các hiểu nhầm cần tránh

**“pauseImmediate=true ngắt ngay record đang chạy.”** Sai. Nó đợi record hiện tại xử lý xong.

**“Chỉ bật pauseImmediate là container tự pause.”** Sai. Phải có pause request.

**“container.pause() return nghĩa là đã pause thực.”** Sai. Xem isPauseRequested và isConsumerPaused.

**“Default đã dừng sau current record.”** Sai. Default false: thường đợi xử lý hết records từ poll trước.

**“Records retained trong memory là durable queue.”** Sai. Process restart làm buffer mất; Kafka log và committed offset phục vụ redelivery.

**“Pause tự commit records đã poll.”** Sai. Commit theo AckMode, transaction và error handling.

**“Pause chắc chắn tránh mọi rebalance.”** Không. Listener chặn poll quá lâu vẫn có thể mất assignment.

**“Batch listener được cắt ngay giữa List.”** Không. Thuộc tính được mô tả cho record listener.

**“Pause làm producer ngừng ghi Kafka.”** Sai. Consumer lag vẫn có thể tăng.

**“Pause và stopImmediate là một.”** Sai. Pause/resume khác stop lifecycle.

**“Tăng concurrency sẽ sửa database overload.”** Không nhất thiết; có thể làm nghẽn nặng hơn.

## 18. Checklist cấu hình và vận hành

**Container**

- [ ] Spring Kafka version hỗ trợ pauseImmediate.
- [ ] Listener dùng record mode khi cần dừng sau current record.
- [ ] setPauseImmediate(true) được đặt trên đúng factory.
- [ ] Có code chủ động pause/resume và ownership chính sách.
- [ ] Có ngưỡng high/low watermark, tránh oscillation.
- [ ] pollTimeoutWhilePaused được cấu hình phù hợp nếu cần.
- [ ] max.poll.records và concurrency phù hợp memory/capacity.

**Reliability**

- [ ] AckMode và error handler rõ ràng.
- [ ] Retained records chưa xử lý không bị coi là đã ack.
- [ ] Listener idempotent khi redelivery sau crash.
- [ ] Async tasks không được ack trước completion.
- [ ] Current record có timeout hữu hạn.
- [ ] Các retry-topic consumers cũng được tính vào downstream load.

**Observability**

- [ ] Theo dõi pause requested và consumer paused riêng.
- [ ] Có ConsumerPausedEvent/ConsumerResumedEvent hoặc metric tương đương.
- [ ] Theo dõi request-to-pause latency và pause duration.
- [ ] Theo dõi committed offsets, lag, rebalance và memory.
- [ ] Có alert khi paused quá lâu hoặc resume không tiến triển.

**Verification**

- [ ] Đã test một poll chứa nhiều records.
- [ ] Đã so sánh pauseImmediate false và true.
- [ ] Đã test resume và records retained.
- [ ] Đã test crash/restart khi paused.
- [ ] Đã test concurrency>1 và các child pause khác thời điểm.
- [ ] Đã test record failure, retry và backpressure thresholds.

## 19. Tài liệu chính thức

- Spring Kafka: Pausing and Resuming Listener Containers — https://docs.spring.io/spring-kafka/reference/kafka/pause-resume.html
- Spring Kafka: Listener Container Properties — https://docs.spring.io/spring-kafka/reference/kafka/container-props.html

## 20. Kết luận

**pauseImmediate** thay đổi ranh giới pause của **record listener** trong Spring Kafka. Với false (default), container thường hoàn tất các records đã nhận từ poll trước; với true, container pause sau **record hiện tại**, giữ records còn lại trong memory để giao sau resume.

Đây là một công cụ quan trọng để backpressure phản ứng nhanh hơn với downstream overload, nhưng không interrupt listener đang chạy, không tự commit offsets, không bảo đảm memory bền vững và không thay thế retry/idempotency. Một thiết kế đáng tin cậy phải sử dụng container API đúng thread, quan sát pause requested khác paused thực, tính đến concurrency và poll buffers, đồng thời kiểm thử đầy đủ pause, resume, crash và recovery.

