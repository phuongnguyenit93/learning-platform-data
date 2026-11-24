# Thử lại vô hạn, DLQ không có dữ liệu hoặc phát lại tạo vòng lặp

Trong Spring Cloud Stream, một message lỗi có thể được **retry tại ứng dụng**, **redeliver từ broker**, **chuyển vào dead-letter queue/topic (DLQ/DLT)** hoặc **phát lại từ DLQ về luồng chính**. Ba triệu chứng — cùng một message được xử lý mãi không dừng, DLQ vẫn rỗng dù log đầy lỗi, và replay khiến message chạy vòng tròn — thường có nguyên nhân khác nhau. Nếu chỉ tăng `maxAttempts`, restart consumer hoặc xóa message, ta có thể làm mất chứng cứ, gây retry storm và làm hỏng dữ liệu nghiệp vụ.

Bài thuộc chương **Chẩn đoán sự cố** của module `SPRING_CLOUD_STREAM`: ứng dụng sự kiện viết bằng `Supplier`/`Function`/`Consumer`, sử dụng binding với Kafka, RabbitMQ hoặc Pulsar. Nội dung tập trung vào cách truy tìm **lớp chịu trách nhiệm retry/ack**, điều kiện để DLQ thật sự nhận dữ liệu, kiểm soát replay có giới hạn, phân biệt cơ chế Kafka Binder với Kafka Streams Binder, rồi kiểm chứng khắc phục bằng kiểm thử lỗi thực tế.

> **Nguyên tắc đầu tiên:** Không xóa topic/queue, reset offset, purge DLQ hoặc phát lại hàng loạt trước khi ghi nhận message ID, consumer group/subscription, partition/offset, retry policy và tác động đã ghi vào database. Những thao tác đó có thể làm mất dữ liệu hoặc nhân đôi giao dịch. Luôn thử trên staging và có phương án rollback cho production.

## 1. Sơ đồ tổng quát một message lỗi

```text
                Destination chính
                   (topic/queue)
                        |
                        v
              Binder / Consumer
                        |
                        v
               Function handler
                        |
             +----------+-----------+
             |                      |
          Thành công               Thất bại
             |                      |
          Ack/commit                v
                             Retry tại chỗ?
                               /       \
                           Có           Không/hết lần
                           |                 |
                       Backoff                v
                           |            Error/recovery policy
                           +-- xử lý lại      /       |       \
                                       Requeue    DLQ     Fail/stop/drop
                                         |         |
                                         v         v
                                  Luồng chính   Replay worker
                                         ^         |
                                         +---------+
```

Không phải mọi binder đều đi qua đúng các hộp trong sơ đồ. Kafka dùng offset và listener container, RabbitMQ dùng ack/nack/requeue và DLX, còn Pulsar dùng subscription ack/negative ack/ack timeout/retry letter topic. Một ứng dụng reactive có thể retry bên trong Reactor thay vì cơ chế retry của binder. Cần xác định **hành vi thực tế**, không chỉ nhìn một property tên `maxAttempts`.

## 2. Phân biệt retry, redelivery, DLQ và replay

| Cơ chế | Người chủ động | Dấu hiệu trong log/metric | Điểm cần thận trọng |
|---|---|---|---|
| Retry trong handler/binder | Framework hoặc code ứng dụng | Một message được thử lại nhiều lần trong một lần nhận | Giới hạn số lần, backoff, timeout và side effect |
| Redelivery từ broker | Broker/container/consumer client | Cùng message ID/offset xuất hiện sau nack, disconnect hoặc restart | Bộ đếm retry ứng dụng có thể bị reset khi nhận lại |
| DLQ/DLT | Binder, error handler hoặc broker DLX | Message lỗi được đưa tới destination dành riêng | Không nhất thiết tự bật, có thể thiếu quyền hoặc routing |
| Retry topic/delay queue | Hạ tầng retry do ứng dụng/broker thiết kế | Message tạm rời luồng chính, trở lại sau độ trễ | Phân biệt retry topic với DLQ cuối cùng |
| Replay thủ công/tự động | Worker vận hành hoặc ứng dụng chuyên biệt | Message từ DLQ/parking lot được xuất bản lại | Dễ lặp vô hạn nếu nguyên nhân chưa sửa |
| Parking lot | Topic/queue cách ly lâu dài | Event không tiếp tục quay về luồng chính | Cần quy trình triage, TTL/retention và audit |

**Retry count không phải lúc nào cũng là một bộ đếm toàn hệ thống.** Ví dụ ứng dụng cố xử lý ba lần, nack về broker, broker redeliver, rồi lại cố ba lần; người vận hành thấy hàng trăm lần dù cấu hình mỗi vòng chỉ là ba. Nếu replay từ DLQ về nguồn lại kích hoạt chu kỳ ba lần mới, tổng số lần cũng tăng không giới hạn.

## 3. Nhận diện retry vô hạn từ triệu chứng

Các dấu hiệu phổ biến:

- Cùng `eventId`/payload/partition-offset hoặc broker message ID xuất hiện liên tục trong log lỗi.
- CPU tăng, số request tới database/API ngoài tăng, nhưng throughput **thành công** không tăng.
- RabbitMQ `redelivered`/nack/requeue tăng nhanh; queue depth dao động gần một mức hoặc không giảm.
- Kafka consumer lag đứng yên ở một offset, container liên tục seek/retry; cũng có trường hợp consumer commit tiếp nhưng replay riêng vẫn lặp.
- Pulsar subscription backlog/redelivery tăng; cùng message được phát lại sau negative acknowledgment hoặc ack timeout.
- DLQ trống nhưng error rate cao; hoặc DLQ vừa có message lại bị worker replay tự động đẩy về nguồn.

Một log lỗi giống nhau **chưa đủ** để kết luận cùng message bị retry: nhiều event có payload giống nhau cũng có thể lỗi cùng kiểu. Phải gắn thông tin nhận dạng ổn định để phân biệt.

Ví dụ log chẩn đoán (không log toàn bộ payload nhạy cảm):

```text
2026-11-24T10:00:00Z ERROR binding=processOrder-in-0
 destination=orders.events group=order-projection
 eventId=evt-1082 key=order-42 sourcePartition=2 sourceOffset=711
 cause=InvalidOrderStateException attempt=1

2026-11-24T10:00:02Z ERROR ... eventId=evt-1082
 sourcePartition=2 sourceOffset=711 attempt=2

2026-11-24T10:00:10Z ERROR ... eventId=evt-1082
 sourcePartition=2 sourceOffset=711 attempt=1
```

Ở lần thứ ba, `attempt` quay về 1 có thể cho thấy **một vòng nhận message mới**, không phải chắc chắn một `RetryTemplate` tiếp tục vô hạn. Đối chiếu consumer restart/rebalance, nack/requeue, manual replay và message headers để biết vòng nào đã đưa message trở lại.

## 4. Quy trình triage nhanh trước khi sửa cấu hình

Thực hiện theo trình tự để không che nguyên nhân:

1. **Xác định message bị lỗi:** `eventId`, business key, timestamp, topic/queue, partition/offset hoặc Pulsar message ID.
2. **Xác định binding:** tên function bean, `<function>-in-0`, `destination`, `group`/subscription và binder thực tế.
3. **Xác định loại lỗi:** deserialize/schema, validate, lỗi nghiệp vụ vĩnh viễn, timeout, authentication/authorization, hay database/broker tạm thời.
4. **Xác định nơi retry:** code (`while`, `retryWhen`), retry binder, Kafka listener error handler, Rabbit nack/requeue, Pulsar negative ack, hay replay worker.
5. **Xác định chính sách sau hết lần:** bỏ qua, dừng container, nack/requeue, DLQ, hoặc parking lot.
6. **Xác minh DLQ thực tế:** tên, broker/vhost/namespace, quyền publish, partition, DLX/routing, subscription/consumer và retention.
7. **Xác minh replay:** nguồn và đích có thực sự khác nhau? Có attempt cap bền vững và trạng thái xử lý được lưu không?
8. **Chỉ sửa một lớp mỗi lần**, phát một poison message được đánh dấu riêng để kiểm thử, theo dõi trạng thái cuối.

Không dùng `maxAttempts: 1` như một câu trả lời chung cho mọi binder: cấu hình này có thể chỉ tắt retry tại lớp binder, còn retry/redelivery tại container hoặc broker vẫn hoạt động.

## 5. Phân loại lỗi để chọn chính sách phục hồi

| Loại lỗi | Ví dụ | Hướng xử lý ưu tiên |
|---|---|---|
| Tạm thời | HTTP 503, DB failover, timeout ngắn | Retry có giới hạn, exponential backoff, jitter, cảnh báo |
| Dữ liệu vĩnh viễn | JSON sai schema, enum không hợp lệ, trường bắt buộc thiếu | Quarantine/DLQ, sửa dữ liệu hoặc schema, không retry nóng |
| Vi phạm quy tắc nghiệp vụ | Sự kiện version cũ, trạng thái không hợp lệ | Phân loại duplicate/stale/gap, không nhất thiết đưa tất cả vào DLQ |
| Lỗi cấu hình | Sai credentials, serializer, topic, ACL | Sửa cấu hình; tăng số Pod hoặc retry không khắc phục |
| Lỗi phụ thuộc kéo dài | Database không sẵn sàng nhiều phút | Circuit breaker, dừng/giảm consumer, backoff theo thời gian, giữ message an toàn |
| Lỗi triển khai | Hợp đồng schema thay đổi không tương thích | Rollback/canary hoặc fix converter, rồi replay có kiểm soát |

Với lỗi vĩnh viễn, mỗi lần thử lại chỉ tăng CPU/network và log volume; với lỗi tạm thời, đưa thẳng vào DLQ sau một lần thử có thể gây áp lực vận hành không cần thiết. Chọn chính sách dựa trên tính chất lỗi và **giới hạn thời gian hồi phục** của dịch vụ.

## 6. Ví dụ function và binding dùng để chẩn đoán

Một consumer imperative cho phép binder quan sát exception được ném ra:

```java
import java.util.function.Consumer;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

record OrderEvent(String eventId, String orderId, String status) {}

@Configuration(proxyBeanMethods = false)
class OrderStreamConfiguration {

    @Bean
    Consumer<OrderEvent> processOrder(OrderService orderService) {
        return orderService::apply;
    }
}
```

`OrderService` do ứng dụng cung cấp và `apply` phải ném exception khi việc xử lý bắt buộc thất bại. Với một function đơn giản, binding tên `processOrder-in-0`:

```yaml
spring:
  cloud:
    function:
      definition: processOrder
    stream:
      bindings:
        processOrder-in-0:
          destination: orders.events
          group: order-projection
          content-type: application/json
          consumer:
            maxAttempts: 3
            backOffInitialInterval: 1000
            backOffMultiplier: 2.0
            backOffMaxInterval: 10000
```

Đây là các **thuộc tính retry chung** cho binding. Chúng không tự tạo DLQ; cũng không chứng minh Kafka listener container, RabbitMQ broker hay Pulsar consumer đã ngừng redelivery. Số lần thử còn phụ thuộc loại binder, model imperative/reactive, custom error handler và cấu hình container.

## 7. Phân biệt "handler ném lỗi" và "handler nuốt lỗi"

Mẫu thường làm DLQ luôn rỗng dù log dày đặc:

```java
@Bean
Consumer<OrderEvent> unsafeConsumer(OrderService service) {
    return event -> {
        try {
            service.apply(event);
        }
        catch (RuntimeException ex) {
            log.error("Failed eventId={}", event.eventId(), ex);
            // Không ném lại -> binder có thể coi message thành công.
        }
    };
}
```

Hàm đã **trả về bình thường**, nên cơ chế retry/DLQ vốn chờ một exception có thể không bao giờ được kích hoạt. Nếu code tự bắt lỗi, cần quyết định tường minh: lưu quarantine bền vững trước khi coi message đã xử lý, hoặc ném lại exception cho framework xử lý.

Mẫu để binder nhận biết lỗi:

```java
@Bean
Consumer<OrderEvent> propagatingConsumer(OrderService service) {
    return event -> {
        // Khi thất bại, exception được truyền ra ngoài.
        service.apply(event);
    };
}
```

Đừng thay `catch` thành `throw` ngay trong production khi chưa xác minh binder recovery policy: có thể biến một lỗi vốn được bỏ qua thành retry vô hạn. Hãy kiểm tra endpoint DLQ và chính sách hữu hạn trước.

## 8. Reactive function có cơ chế retry khác

Với các function kiểu `Function<Flux<T>, Flux<R>>`, Spring Cloud Stream không coi từng phần tử là một imperative message handler để áp dụng chung retry template/DLQ như ở trên. Các toán tử Reactor (`retry`, `retryWhen`, `onErrorResume`, `onErrorContinue`) và cách binder tích hợp reactive pipeline quyết định hành vi.

Mẫu dễ tạo retry không giới hạn:

```java
@Bean
Function<Flux<OrderEvent>, Flux<OrderEvent>> riskyPipeline() {
    return input -> input
        .map(this::enrich)
        .retry(); // Có thể resubscribe vô hạn khi lỗi tiếp diễn.
}
```

Một cấu hình giới hạn hơn (đây là ví dụ về Reactor, **không tự kích hoạt broker DLQ**):

```java
@Bean
Function<Flux<OrderEvent>, Flux<OrderEvent>> boundedPipeline() {
    return input -> input
        .map(this::enrich)
        .retryWhen(Retry.backoff(3, Duration.ofSeconds(1))
            .maxBackoff(Duration.ofSeconds(10)));
}
```

Trong ví dụ, `enrich`, `Flux` và `Retry` cần được định nghĩa/import từ Reactor trong ứng dụng. `retryWhen` có thể resubscribe cả upstream sequence, không nhất thiết chỉ thử lại một record lỗi; nó có nguy cơ phát lại các phần tử đã tạo side effect. Với nhu cầu per-message bounded retry, cần thiết kế ở ranh giới message và có idempotency, không dùng toán tử retry toàn stream một cách vô thức.

## 9. Cây quyết định khi thấy retry không dứt

```text
Lặp cùng message ID/offset?
  |
  +-- Không: nhiều message độc lập lỗi giống nhau
  |           -> xem schema, input quality, consumer capacity
  |
  +-- Có:
       |
       +-- Cùng lần nhận? attempt tăng liên tục
       |      -> code retry, binder retry hoặc listener error handler
       |
       +-- Qua nhiều lần nhận? attempt về 1/rebalance
       |      -> broker requeue, nack/redelivery, offset seek, crash
       |
       +-- Source chính đã kết thúc retry nhưng message xuất hiện lại?
              -> replay worker, TTL retry queue/DLX hoặc retry topic
```

Ghi nhận một mẫu có ID ổn định xuyên các lần thử. Nếu không thể gắn `eventId` ở payload, dùng Kafka topic/partition/offset, Rabbit message ID (nếu producer cung cấp) hoặc Pulsar message ID cùng metadata gốc. Message ID ở bản **được republish** có thể thay đổi, nên giữ cả `originalEventId`/`originalDestination` để theo dấu xuyên DLQ/replay.

## 10. Kafka Binder: DLQ không bật mặc định

Với Kafka message-channel binder, DLQ là tính năng phải bật rõ ràng. Điều kiện chính:

1. Input binding có **consumer group tường minh**.
2. Extended consumer property `enableDlq` được bật cho **đúng binding name**.
3. Retry/hệ thống xử lý lỗi đi qua cơ chế mà Kafka Binder DLQ quản lý.
4. DLT topic có partition/routing phù hợp và ứng dụng có quyền ghi.

Ví dụ:

```yaml
spring:
  cloud:
    function:
      definition: processOrder
    stream:
      bindings:
        processOrder-in-0:
          destination: orders.events
          group: order-projection
          consumer:
            maxAttempts: 3
            backOffInitialInterval: 500
            backOffMultiplier: 2.0
            backOffMaxInterval: 3000
      kafka:
        bindings:
          processOrder-in-0:
            consumer:
              enableDlq: true
              dlqName: orders.events.dlt
```

Khi input xử lý thất bại và các lần retry do binder quản lý đã hết, record được gửi tới `orders.events.dlt` theo cấu hình. **Không** đặt `enableDlq` dưới `spring.cloud.stream.bindings...consumer` vì nó là property **mở rộng của Kafka Binder**. Nếu dùng alias `spring.cloud.stream.function.bindings`, tên trong nhánh extended binder phải khớp với binding sau ánh xạ.

DLQ thường được đặt tên mặc định dạng `error.<destination>.<group>` nếu không có `dlqName`; đặt tên cụ thể giúp tránh nhìn nhầm topic. Không giả định Kafka tự tạo topic theo policy broker: kiểm tra provisioning và quyền thực tế.

## 11. Kafka Binder: `maxAttempts: 1` không phải lúc nào cũng hết retry

Trong Spring Cloud Stream Kafka Binder hiện đại, khi **DLQ không bật**, cấu hình retry chung của binder không nhất thiết điều khiển retry tại listener container. Tài liệu Kafka Binder 5.x nêu rằng mặc định lúc này fallback sang retry của Spring Kafka container (chẳng hạn 10 retries theo cấu hình mặc định được tài liệu mô tả). Vì vậy đặt:

```yaml
spring:
  cloud:
    stream:
      bindings:
        processOrder-in-0:
          consumer:
            maxAttempts: 1
```

có thể **không** tắt các lần container retry. Muốn thay chính sách, phải xem error handler thực tế của listener container và release Spring Cloud Stream/Spring Kafka đang sử dụng. Ví dụ tài liệu dùng `ListenerContainerCustomizer` để cài một `DefaultErrorHandler` có `FixedBackOff(0L, 0L)` cho nhánh không có DLQ; đây là **cách cấu hình retry container**, không phải cách thiết lập DLQ mặc định.

Một container khác có thể được ứng dụng tùy chỉnh với backoff không giới hạn, hoặc code gọi `seek` thủ công khiến cùng offset được đọc lại. Hãy kiểm tra bean `ListenerContainerCustomizer`, `ListenerContainerWithDlqAndRetryCustomizer`, `CommonErrorHandler`, `DefaultErrorHandler` và những code thao tác `Acknowledgment`/seek. Không sửa hàng loạt listener container nếu chỉ một binding cần chính sách khác.

## 12. Kafka: DLQ rỗng vì lỗi xảy ra trước handler

Không phải mọi lỗi đều chạy qua `Consumer<OrderEvent>` ở tầng business. Ví dụ lỗi deserialization gốc xảy ra trước khi message converter tạo object:

```text
Broker record bytes
       |
KafkaDeserializer / native serde
       |        \-- lỗi trước khi handler chạy
       v
Spring Cloud Stream conversion
       |
       v
Consumer<OrderEvent>
```

Nếu lỗi xảy ra ở **Kafka Deserializer** trước khi framework dựng được record bình thường, application handler không được gọi và retry/DLQ dành cho handler có thể không bắt lỗi đó. Kafka client có thể tiếp tục báo lỗi cùng offset; tùy cấu hình, container không khôi phục được record để xuất bản vào DLQ. Cần xem liệu binder đang dùng message conversion hay native encoding và liệu `ErrorHandlingDeserializer`/error handler tương ứng đã được cấu hình trong release đó chưa.

Test phải có trường hợp byte payload sai schema, không chỉ method `service.apply()` ném `RuntimeException`. Không reset offset để "bỏ qua" khi chưa lưu được bản ghi lỗi hoặc có phê duyệt nghiệp vụ rõ ràng.

## 13. Kafka: partition, serializer, quyền và producer DLT

Khi Kafka Binder gửi record sang dead-letter topic, mặc định nhiều phiên bản giữ **partition gốc** để chọn partition trên DLT. Vì vậy DLT cần số partition thích hợp hoặc custom DLQ partition function; nếu DLT có ít partition hơn, publish có thể thất bại.

Ví dụ nếu nguồn có 8 partition và DLT chỉ có 1 partition, không nên mặc định rằng broker sẽ điều phối sang partition hợp lệ. Có thể cấu hình `dlqPartitions: 1` theo hỗ trợ binder hoặc một `DlqPartitionFunction` để đưa record tới partition 0; cú pháp và điều kiện tùy release.

Kiểm tra thêm:

- DLT topic có tồn tại/được auto-provision đúng không?
- Broker principal có quyền `WRITE` vào DLT không?
- DLT producer dùng serializer tương thích với payload gốc và headers lỗi không?
- Có `DlqDestinationResolver` tự chọn topic khác `dlqName` không?
- DLT nằm ở cluster Kafka khác và producer của binder có được cấu hình đúng không?
- Nếu dùng `destinationIsPattern`, phiên bản binder có cho phép DLQ hay không?

Một lỗi gửi DLT có thể dẫn đến container tiếp tục retry hoặc dừng, không nhất thiết làm queue đích có dữ liệu. Cần xem **lỗi của DLQ publisher** chứ không chỉ lỗi business ban đầu.

## 14. Kafka Streams Binder khác Kafka message-channel Binder

**Kafka Streams Binder** dùng topology `KStream`/`KTable`/state store; không áp dụng máy móc `spring.cloud.stream.kafka.bindings...consumer.enableDlq` của Kafka message-channel binder cho mọi lỗi topology. Với lỗi **deserialization**, Kafka Streams Binder có property riêng:

```yaml
spring:
  cloud:
    stream:
      kafka:
        streams:
          binder:
            deserializationExceptionHandler: sendToDlq
```

Có thể chọn `logAndFail`/`logAndContinue` theo hỗ trợ phiên bản. Một số release hỗ trợ cấu hình handler ở input binding cấp thấp hơn. Lựa chọn `sendToDlq` trong ví dụ này áp dụng **đường deserialization lỗi**, không chứng minh mọi exception trong processor, join, aggregate hoặc output serializer đều đi vào DLT.

Đối với lỗi **processing/production** của Kafka Streams, cần kiểm tra exception handler mà Kafka Streams bản tương ứng hỗ trợ, chính sách thread replacement/restart và các customizer trên Streams builder/container. Nếu topology ngừng xử lý sau lỗi, nhìn DLT rỗng có thể là hành vi đúng vì chưa có handler tương ứng. Các DLT record từ Kafka Streams cũng có quy tắc partition/destination khác nhau; kiểm tra số partition DLT và cấu hình `DlqPartitionFunction` nếu cần.

## 15. RabbitMQ: requeue có thể tạo vòng vô hạn

RabbitMQ sử dụng `ack` cho message đã xử lý, `nack`/reject cho message thất bại. Nếu reject với `requeue=true`, broker đưa message trở lại queue để giao lại. Khi nguyên nhân là dữ liệu sai vĩnh viễn, chu kỳ này không tự kết thúc:

```text
Queue -> Consumer
  ^         |
  |         v
  |     Handler lỗi
  |         |
  +-- nack(requeue=true)
```

Trong RabbitMQ Binder, thuộc tính mở rộng `requeueRejected` chi phối việc đưa delivery bị reject trở lại queue trong điều kiện binder/container tương ứng. Cấu hình kết hợp `requeueRejected: true` và không republish lỗi vào DLQ có thể khiến **redelivery liên tục**. Không khắc phục bằng cách tăng số consumer: mỗi consumer mới chỉ nhận lại poison message nhanh hơn.

Để xử lý hữu hạn, thường cần retry tại application/binder với số lần rõ ràng và **sau đó reject không requeue vào dead-letter exchange** hoặc republish có kiểm soát vào DLQ.

## 16. RabbitMQ: cấu hình DLQ có chủ đích

Ví dụ với `processOrder-in-0`, destination `orders.events` và group `order-projection`:

```yaml
spring:
  cloud:
    function:
      definition: processOrder
    stream:
      bindings:
        processOrder-in-0:
          destination: orders.events
          group: order-projection
          consumer:
            maxAttempts: 3
            backOffInitialInterval: 1000
            backOffMultiplier: 2.0
            backOffMaxInterval: 5000
      rabbit:
        bindings:
          processOrder-in-0:
            consumer:
              autoBindDlq: true
              republishToDlq: true
              requeueRejected: false
```

`autoBindDlq` cho binder khai báo DLQ/DLX/routing khi điều kiện provisioning được đáp ứng. `republishToDlq` khiến binder dùng cơ chế republish để kèm metadata lỗi; `requeueRejected: false` tránh đưa một message đã thất bại trở lại queue chính theo đường reject tương ứng. Phiên bản mới có thể đặt mặc định `republishToDlq` khác tài liệu lịch sử — khai báo tường minh sẽ tránh mơ hồ.

Nếu queue/exchange đã được đội hạ tầng provision, không mặc định bật `autoBindDlq` sẽ sửa an toàn topology tồn tại. Queue arguments có thể gây `PRECONDITION_FAILED` khi không khớp; phải so với trạng thái broker thực tế và có kế hoạch migration khi đổi DLX argument.

## 17. RabbitMQ: vì sao `autoBindDlq` vẫn có thể không thấy message?

Đặt `autoBindDlq: true` chỉ giúp khai báo tài nguyên khi provisioning thành công. Message chưa chắc đến DLQ nếu:

1. **Handler nuốt lỗi** và trả về bình thường — listener ack message.
2. **Requeue vô hạn** — message không bao giờ đi vào đường dead-letter.
3. **Sai tên queue:** binder dùng queue dựa trên destination/group/prefix/partition; người vận hành xem nhầm `.dlq` của topic khác.
4. **DLX/routing key không khớp:** message bị dead-letter nhưng không có queue nào bind để nhận, có thể mất khỏi luồng chờ.
5. **`republishToDlq` gặp lỗi:** publish bị từ chối, credential thiếu quyền, connection/channel lỗi hoặc metadata/header quá lớn.
6. **Queue TTL/expiry hoặc max-length:** message vào DLQ nhưng bị expire/drop nhanh hơn thời gian quan sát.
7. **DLQ có consumer đang đọc:** metric `messages_ready=0` nhưng message đã được chuyển tiếp/ack ở nơi khác.
8. **Exception đặc biệt được binder/container bỏ qua DLQ:** ví dụ `ImmediateAcknowledgeAmqpException` có thể xác nhận ngay mà không dead-letter.
9. **DLQ được tạo ở vhost hoặc broker khác:** ứng dụng và giao diện vận hành không cùng môi trường.

Với Rabbit, xem cả `messages_ready` và `messages_unacknowledged`, số consumer trên DLQ, policy DLX/routing, các header `x-death` hoặc exception headers nếu có. `x-death` không phải bộ đếm nghiệp vụ đáng tin duy nhất cho mọi đường **republish**: thao tác republish tạo một publish mới, có thể khác với native broker dead-lettering.

## 18. Native dead-lettering khác với binder republish

Hai đường đi thường gặp:

```text
A. Broker DLX:
main queue -> reject(requeue=false) -> DLX -> DLQ

B. Binder republish:
main queue -> handler lỗi -> binder publish tới DLQ
                                -> ack/recover message gốc theo cơ chế binder
```

Với native DLX, broker dựa vào dead-letter exchange và routing key; với republish, ứng dụng gửi một message mới với metadata lỗi và cần bảo đảm producer ghi thành công. Việc ghi thành công DLQ và xác nhận bản gốc **có thể có cửa sổ lỗi** nếu không được bảo đảm bởi transaction/confirm phù hợp. Chính sách `transacted`, publisher confirms và khả năng recover khi publish DLQ thất bại cần được kiểm chứng bằng integration test, không suy ra từ `republishToDlq=true` là giao nhận exactly-once.

Nếu bật DLQ mà message vẫn ở main queue, tìm xem binder đang **reject + requeue** hay **republish**. Đừng đổi cả hai cơ chế cùng lúc khi chưa biết cơ chế thực tế được dùng.

## 19. RabbitMQ: tránh vòng TTL từ DLQ trở về queue chính

Một mẫu retry có delay dùng queue retry với TTL và dead-letter exchange trỏ lại nguồn:

```text
main queue --error--> retry queue
                     TTL 30s
                       |
                       v
                   DLX về main
                       |
                       +--> consumer fail lại
                                 |
                                 +--> retry queue ...
```

Vòng này **có thể là thiết kế chủ ý** cho retry trì hoãn, nhưng phải có số lượt hữu hạn. Nếu queue retry luôn dead-letter về main và không có counter/parking lot, một poison message sẽ chạy mãi. Việc set `x-message-ttl` chỉ làm **chậm** vòng lặp, không giới hạn số vòng.

RabbitMQ quorum queues có tùy chọn **delivery limit** và một số broker version có cơ chế phát hiện dead-letter cycle trong điều kiện nhất định, nhưng không nên phụ thuộc vào chúng để thay thế retry policy. Chúng có semantics riêng và không bao phủ mọi vòng publish lại ở cấp ứng dụng.

Thiết kế tốt: sau `N` vòng (đếm bền vững bằng application metadata hoặc chính sách broker thích hợp), message chuyển **parking-lot queue** không tự routing về main; chỉ replay thủ công hoặc qua job được phê duyệt.

## 20. Pulsar: negative acknowledgment và ack timeout

Pulsar consumer có thể redeliver message theo nhiều cơ chế:

- `negativeAcknowledge` khi xử lý thất bại.
- Acknowledgment timeout (`ackTimeout`) nếu đã nhận nhưng chưa ack đúng hạn.
- Consumer bị disconnect/crash và broker giao lại unacknowledged messages.
- Retry letter topic với `enableRetry(true)`/`reconsumeLater`, nếu ứng dụng dùng cơ chế đó.

Đặc biệt, **negative acknowledgment không có cùng bảo đảm giới hạn retry** như retry-letter topic. Tài liệu Pulsar cảnh báo redelivery counter của negative ack có thể chỉ ở trong bộ nhớ và được reset sau broker restart, topic unload, dispatcher reconfiguration hoặc consumer disconnect. Vì vậy `DeadLetterPolicy.maxRedeliverCount` có thể **không bao giờ đạt ngưỡng** trong một số tình huống; DLQ vẫn rỗng dù message được phát lại rất nhiều lần.

Với yêu cầu retry count ổn định xuyên restart, Pulsar khuyến nghị sử dụng **`enableRetry(true)` và `reconsumeLater`** để ghi số lần retry trong message properties trên retry topic. Tuy nhiên đây là chức năng của Pulsar client; cách expose lên Spring Cloud Stream Pulsar Binder phụ thuộc phiên bản Spring Pulsar/binder và phải kiểm tra cụ thể.

## 21. Pulsar: minh họa retry letter topic và dead letter policy

Ví dụ **Pulsar Java client thuần**, không phải đoạn mã tự động được bật bởi Spring Cloud Stream Binder:

```java
Consumer<byte[]> consumer = pulsarClient.newConsumer(Schema.BYTES)
    .topic("persistent://acme/orders/orders.events")
    .subscriptionName("order-projection")
    .subscriptionType(SubscriptionType.Shared)
    .enableRetry(true)
    .deadLetterPolicy(DeadLetterPolicy.builder()
        .maxRedeliverCount(5)
        .retryLetterTopic("persistent://acme/orders/orders.retry")
        .deadLetterTopic("persistent://acme/orders/orders.dlq")
        .build())
    .subscribe();

Message<byte[]> message = consumer.receive();
try {
    orderProcessor.process(message.getData());
    consumer.acknowledge(message);
}
catch (RuntimeException exception) {
    consumer.reconsumeLater(message, 30, TimeUnit.SECONDS);
}
```

Ở ví dụ này `pulsarClient` và `orderProcessor` do chương trình khởi tạo, và code bắt `RuntimeException` chỉ là minh họa. Việc `reconsumeLater` tạo retry message có thể thất bại do producer/ACL/network, nên production cần xử lý lỗi của đường retry và kiểm thử recovery. Đừng vừa `negativeAcknowledge` vừa `reconsumeLater` cho cùng lần thất bại rồi mặc định rằng chỉ có một bản retry. API `DeadLetterPolicy` và subscription type được hỗ trợ phụ thuộc phiên bản Pulsar client.

**Không copy ví dụ client thuần vào một Spring Cloud Stream function mà không tìm hiểu ack/error handling của binder.** Nếu binder tự động ack sau khi function trả về, side effect `reconsumeLater` thủ công có thể gây bất đồng bộ giữa hai cơ chế. Khi dùng binder, hãy xác minh đường consumer builder customization, xử lý exception và subscription type trong bản Spring for Apache Pulsar đang sử dụng.

## 22. Pulsar: vì sao DLQ trống dù backlog tăng?

Các nguyên nhân cần kiểm tra:

| Nhóm | Ví dụ | Phương pháp xác minh |
|---|---|---|
| Không có dead-letter policy | Chỉ dùng `negativeAcknowledge`, không cấu hình DLT | Kiểm tra consumer builder/binder config |
| Sai subscription type | `Exclusive` nhưng mong semantics retry/DLQ của `Shared` | Xem subscription metadata và docs phiên bản |
| Không dùng retry-letter topic | `enableRetry` chưa bật, counter nack reset | Kiểm tra retry topic/properties `RECONSUMETIMES` |
| Sai topic/subscription | Xem topic DLQ được đặt tên cho subscription khác | Kiểm tra tên đầy đủ/namespace |
| Retry count không tích lũy | Consumer reconnect/unload reset counter | Theo dõi redelivery trước/sau restart |
| Ack quá sớm | Function return bình thường trước khi công việc hoàn tất | Xác minh thời điểm ack/commit và side effect |
| ACL của DLQ producer thiếu | Client không tạo/publish vào DLT | Xem log quyền và producer errors |
| Auto-creation bị chặn | Topic DLQ/retry không tồn tại | Provision topic và subscription theo policy |
| Consumer khác đang đọc DLQ | DLQ subscription backlog thấp dù message đã từng tới | Xem stats mọi subscription/producer |

Tập trung vào **subscription backlog**, không chỉ topic stats tổng quát. Một topic có nhiều subscription với backlog khác nhau; nhìn sai subscription có thể dẫn tới chẩn đoán sai. Pulsar retry topic và DLT là topic thông thường có retention, permission, partition và namespace policy riêng.

## 23. Tổng hợp dấu hiệu DLQ rỗng theo ba binder

| Dấu hiệu quan sát | Kafka Binder | RabbitMQ Binder | Pulsar |
|---|---|---|---|
| Handler không ném exception | Có thể coi record thành công | Container có thể ack | Subscription có thể ack |
| Cấu hình DLQ không bật | `enableDlq` mặc định false | `autoBindDlq`/DLX cần kiểm tra | Cần dead-letter policy/đường retry phù hợp |
| Thiếu group/subscription đúng | DLQ yêu cầu group tường minh | Queue name phụ thuộc group/destination | Subscription name điều khiển backlog/DLT |
| Retry liên tục | Container seek/recoverer | Nack/requeue | Negative ack, ack timeout hoặc retry topic |
| Lỗi trước business handler | Kafka deserializer/converter | Converter/adapter/broker delivery | Schema decode/consumer receive path |
| Destination lỗi | DLT name/partition/producer | DLX/routing/vhost/queue | Topic full name/namespace/subscription |
| Thiếu quyền | Producer DLT WRITE | Publish vào DLX/DLQ | Admin/topic producer ACL |
| DLQ có dữ liệu nhưng trông rỗng | Consumer khác commit DLT | DLQ consumer đang ack | Subscription khác đã ack |

Đối chiếu từng binder để chọn phép kiểm chứng. Không so sánh `Kafka lag=0`, `Rabbit queue depth=0` và `Pulsar backlog=0` rồi kết luận tương đương: các con số đo trạng thái khác nhau.

## 24. Vòng lặp replay: nguyên nhân phổ biến thứ ba

Giả sử consumer chính xử lý một event sai schema, sau ba lần thử gửi nó vào DLQ. Một replay worker luôn đọc DLQ rồi xuất bản lại nguồn, không giới hạn số lần:

```text
orders.events
    |
    v
Consumer lỗi vĩnh viễn
    |
    +--> orders.events.dlq
                |
                v
         Replay worker (tự động)
                |
                +--> orders.events
                          |
                          +--> Consumer lỗi như cũ ...
```

Mỗi chu kỳ có thể tạo **record mới** trong broker, với offset hoặc message ID mới, nên nhìn theo broker identity có thể tưởng là nhiều event khác nhau. Cần theo dõi `originalEventId`, `originalDestination`, `replayAttempt` và mối quan hệ parent-child giữa các lần publish. Nếu replay code luôn xóa/reset header đếm lần, giới hạn retry không còn ý nghĩa.

Vòng lặp không chỉ có ở Kafka. RabbitMQ có thể dùng DLQ TTL + DLX quay về main; Pulsar retry-letter topic có thể bị code hoặc workflow ngoài thiết kế publish lại topic chính không giới hạn. Luôn kiểm tra **cả đường hồi lưu** của message, không chỉ chính sách retry trong consumer.

## 25. Chính sách replay đúng: một lần xử lý phải có điểm kết thúc

Một kiến trúc replay an toàn thường có **parking lot** và **quyết định của operator hoặc hệ thống kiểm soát**:

```text
main topic/queue
     |
     v
main consumer --(lỗi sau N attempts)--> DLQ
                                         |
                                         v
                                Triage + phân loại lỗi
                                         |
                         +---------------+--------------+
                         |                              |
                     Có thể sửa                    Không thể sửa
                         |                              |
                         v                              v
                  Bounded replay                   Parking lot
                         |
                         v
                Back to main (khi đủ điều kiện)
                         |
                   lỗi lại?
                     /   \
                   Có     Không
                   |        |
             tăng durable  kết thúc, lưu audit
             replayAttempt
                   |
             >= limit? -> Parking lot
```

Điều kiện để replay:

1. Đã xác định nguyên nhân của lần thất bại trước và có bằng chứng lỗi **có thể phục hồi**.
2. Có chính sách số lần replay tối đa trên **event gốc**, không chỉ trên từng message được publish lại.
3. Có delay/throttle và giới hạn concurrency để tránh gây lại sự cố downstream.
4. Có idempotency theo `eventId` và kiểm tra version/thứ tự nghiệp vụ khi cần.
5. Có đích parking lot tách biệt, không auto-route trở lại main.
6. Có audit ai/khi nào/vì sao replay, phiên bản schema/code nào xử lý.
7. Chỉ đánh dấu DLQ record đã được xử lý sau khi kết quả chuyển tiếp hoặc lưu parking lot **bền vững** theo policy.

**Không dùng "thấy DLQ có message là replay ngay" làm quy tắc mặc định.** DLQ là nơi giữ message để phân tích và kiểm soát rủi ro, không phải hàng đợi retry nóng thứ hai.

## 26. Replay counter phải sống qua lần publish và restart

Một header đơn thuần có thể bị mất khi qua serializer, message converter, proxy hoặc hệ thống trung gian. Vì vậy nếu business quan trọng, số lần replay nên được lưu **bền vững** theo `originalEventId` ở database/ledger quản trị hoặc trong envelope có schema được kiểm soát; việc đọc header chỉ là cách tối ưu cho quan sát.

Envelope ví dụ:

```json
{
  "originalEventId": "evt-1082",
  "originalDestination": "orders.events",
  "aggregateId": "order-42",
  "aggregateVersion": 7,
  "replayId": "replay-20261124-001",
  "replayAttempt": 2,
  "firstFailedAt": "2026-11-24T10:00:00Z",
  "lastFailureCode": "VALIDATION_ERROR",
  "payload": {
    "eventId": "evt-1082",
    "orderId": "order-42",
    "status": "PAID"
  }
}
```

`originalEventId` **không thay đổi** giữa các vòng. `replayId` phân biệt hành động của replay worker, còn `replayAttempt` tăng trong cùng một chính sách. Không tin tuyệt đối số `replayAttempt` do một publisher không đáng tin cậy gửi vào; nếu dùng nó quyết định số lần, server phải xác thực/ghi bền vững bản ghi trạng thái tương ứng.

Không nên lấy chỉ `x-death` (RabbitMQ), Kafka offset hoặc Pulsar message ID làm khóa replay toàn cục vì chúng có thể đổi khi message được republish. Cần một business/event identity ổn định xuyên các queue/topic.

## 27. Quy tắc quyết định replay (pseudocode)

Mô hình quản trị có thể như sau:

```text
for each DLQ record:
    originalId = extractOriginalEventId(record)

    lock ledger[originalId] transactionally
    if ledger.state == COMPLETED:
        mark DLQ record as handled, skip duplicate

    if failureReason is permanent and not repaired:
        ledger.state = PARKED
        retain record in parking lot with audit
    else if ledger.replayAttempts >= MAX_REPLAY_ATTEMPTS:
        ledger.state = PARKED
        retain record in parking lot with audit
    else:
        ledger.replayAttempts += 1
        ledger.state = REPLAY_REQUESTED
        persist outbox message to main destination
        commit ledger + outbox transaction

    separate outbox publisher sends with delivery confirmation
    on confirmed publish, mark outbox delivered
    mark DLQ input handled according to the durable workflow
```

Mã giả cố ý tách **transaction database** và **publish broker** để không tuyên bố `StreamBridge.send()` tạo exactly-once transaction xuyên database và Kafka/RabbitMQ/Pulsar. Trong triển khai thực tế, dùng transactional outbox, idempotent publisher hoặc cơ chế giao dịch tương thích để chịu được crash giữa các bước. Việc ack DLQ trước khi đã ghi ledger/outbox có thể làm mất công việc replay; ack sau khi publish nhưng trước khi ghi ledger có thể tạo duplicate. Cần kiểm thử cả hai cửa sổ lỗi.

Trong một hệ thống không yêu cầu giao dịch chặt, có thể chấp nhận at-least-once replay nhưng **phải** có idempotency và audit; đó là lựa chọn có chủ đích, không phải bảo đảm exactly-once.

## 28. Vì sao chỉ dùng `x-retries` header không đủ?

Ví dụ điều kiện kiểm tra header trong replay worker:

```java
int attempts = message.getHeaders().getOrDefault("x-retries", 0) instanceof Integer n
    ? n : 0;

if (attempts >= 3) {
    // Ghi parking lot; không gửi về main.
}
else {
    // Tăng attempts rồi gửi về main.
}
```

Ví dụ trên chỉ là minh họa ý tưởng. Nó **không đầy đủ** cho production, bởi các vấn đề:

- Kafka/AMQP/Pulsar có cơ chế encoding header khác nhau; numeric header có thể được đọc thành `byte[]` hoặc `String`.
- Một conversion/republish path có thể bỏ header không được mapper cho phép.
- Nếu code mới dựng message từ payload và quên copy headers, bộ đếm trở về 0.
- Một job replay chạy song song có thể đọc cùng event và cả hai đều quyết định gửi.
- Sau restart, trạng thái chỉ có trong memory bị mất.

Do đó bộ đếm tại header nên là **tín hiệu bổ sung**, còn ràng buộc cuối cùng thuộc về ledger bền vững/unique constraint. Trong các ví dụ thực hành có thể dùng header đơn giản để học luồng, nhưng không coi đó là thiết kế đủ an toàn cho sự kiện tài chính hoặc nghiệp vụ quan trọng.

## 29. Phát lại có thể phá thứ tự sự kiện cùng khóa

Giả sử event `OrderPaid(v11)` lỗi và bị đưa DLQ, còn `OrderShipped(v12)` tiếp tục đi qua luồng chính. Sau một giờ, operator replay v11. Nếu code chỉ cập nhật status theo event nhận được cuối, trạng thái có thể quay từ `SHIPPED` về `PAID`.

```text
Thời gian | Sự kiện          | Projection
--------- | ---------------- | ----------------
t1        | v10 CREATED      | CREATED
t2        | v11 PAID lỗi     | CREATED
t3        | v12 SHIPPED      | SHIPPED
t4        | replay v11 PAID  | PAID (sai nếu ghi đè)
```

Cần kiểm tra `aggregateVersion`, `eventId`, điều kiện chuyển trạng thái và dữ liệu đã áp dụng. Nếu sự kiện có thứ tự phụ thuộc nhau, có thể **chặn key** khi có ordering gap, lưu event sau vào buffer/quarantine bền vững và replay theo thứ tự. Nếu nghiệp vụ chấp nhận áp dụng event cuối mà bỏ qua intermediate event, phải ghi rõ hợp đồng đó và audit lý do.

DLQ không tự bảo đảm ordering. Việc phát lại message về topic chính có thể còn làm record mới đi vào partition khác nếu thay đổi key serializer hoặc số partition. Giữ record key/routing key ổn định và kiểm thử toàn pipeline sau replay.

## 30. Xác minh đường DLQ trước khi replay

Các bước kiểm tra cho một event mẫu:

1. Tạo một event ID riêng trong staging và khiến handler **ném lỗi có chủ đích**.
2. Quan sát số lần xử lý và backoff tại application/container.
3. Xác nhận message cuối cùng **rời** luồng retry và xuất hiện ở đúng DLT/queue/topic.
4. Xác minh DLQ record giữ được payload gốc hoặc payload đủ để phục hồi; metadata `originalEventId`, destination, error reason và timestamp phải tra được.
5. Tạm dừng replay worker; xem số lượng DLQ không tự quay về nguồn.
6. Sửa điều kiện gây lỗi hoặc dùng handler test luôn thành công; replay **một** event và xác minh nó được xử lý đúng.
7. Lặp với điều kiện lỗi vĩnh viễn để bảo đảm attempt cap đưa event tới parking lot.
8. Thử crash tại các điểm trước/sau publish và ack để chứng minh không mất message và idempotency xử lý duplicate.

Không bắt đầu bằng việc replay toàn bộ DLQ nếu chưa chứng minh đường replay cho **một message** kết thúc hữu hạn. Với production, đặt giới hạn số event/giây và chỉ replay một dải ID/offset đã phê duyệt.

## 31. Lệnh chẩn đoán Kafka an toàn

Các lệnh dưới đây chỉ **đọc metadata/trạng thái** và cần kết nối tới đúng cluster:

```bash
# Group + lag + assignment:
kafka-consumer-groups.sh \
  --bootstrap-server kafka-bootstrap:9092 \
  --group order-projection \
  --describe

# Kiểm tra topic nguồn và DLT:
kafka-topics.sh \
  --bootstrap-server kafka-bootstrap:9092 \
  --describe --topic orders.events

kafka-topics.sh \
  --bootstrap-server kafka-bootstrap:9092 \
  --describe --topic orders.events.dlt
```

Nếu cluster cần SASL/TLS, thêm file client properties theo quy trình bảo mật và tuyệt đối không in credential vào log/shell history. Để quan sát bản ghi DLT, có thể dùng một consumer **read-only** trong môi trường an toàn, với group riêng; việc tiêu thụ bằng group khác không xóa record Kafka gốc nhưng có thể tạo offset mới cho group đó. Đừng dùng group production để kiểm tra thủ công rồi vô tình thay đổi offset của replay worker.

**Không chạy `--reset-offsets --execute`**, xóa topic hoặc thay đổi retention như thao tác đầu tiên. Reset offset tác động đến cơ chế replay và có thể làm hàng triệu sự kiện được xử lý lại hoặc bỏ qua.

## 32. Lệnh chẩn đoán RabbitMQ an toàn

Kiểm tra queue, ready/unacked và consumer:

```bash
rabbitmqctl list_queues name messages_ready messages_unacknowledged consumers
```

Với nhiều vhost, chỉ định đúng vhost theo syntax của phiên bản CLI. RabbitMQ Management HTTP API cũng cho phép xem queue attributes (`arguments` bao gồm `x-dead-letter-exchange`, `x-dead-letter-routing-key`) và bindings trong đúng vhost.

Checklist:

- Queue của `orders.events` + group có tồn tại không?
- DLQ có tồn tại trong **cùng vhost** không?
- Queue chính có dead-letter exchange/routing key đúng không?
- Exchange đó có binding tới DLQ không?
- DLQ có consumer đang đọc và ack rất nhanh không?
- Có TTL/max-length/quorum delivery limit trên queue chính hoặc retry/DLQ không?
- Binder đang `requeueRejected=true` hay republish vào DLT?

**Không dùng `rabbitmqctl purge_queue`** để giải quyết retry loop khi chưa có quyết định xử lý dữ liệu. Purge sẽ xóa các message đang chờ và có thể ảnh hưởng các consumer khác.

## 33. Lệnh chẩn đoán Pulsar an toàn

Kiểm tra subscriptions và stats theo topic đầy đủ:

```bash
pulsar-admin topics subscriptions \
  persistent://acme/orders/orders.events

pulsar-admin topics stats \
  persistent://acme/orders/orders.events

pulsar-admin topics stats \
  persistent://acme/orders/orders.dlq
```

Kiểm tra chính xác tên subscription `order-projection`, backlog/redelivery, consumer connection, producers trên retry/DLQ topic và namespace permissions. Nếu dùng partitioned topic, xem thêm metadata/statistics cho từng partition theo lệnh hỗ trợ của bản Pulsar; đừng nhầm non-partitioned topic với partitioned topic.

Để khẳng định counter retry được giữ bền vững, theo dõi message properties trên retry topic (`RECONSUMETIMES`, `ORIGIN_MESSAGE_ID`, `REAL_TOPIC`) khi ứng dụng sử dụng retry-letter mechanism. Với negative ack, broker restart/unload có thể đặt lại bộ đếm trong memory, nên không dùng số redelivery nhất thời làm bằng chứng đã đạt retry limit.

Không reset subscription cursor hoặc skip messages bằng Admin CLI khi chưa có kế hoạch lưu/khôi phục thông tin nguồn. Cursor reset có thể phát lại một đoạn lớn của topic hoặc bỏ qua message đang cần điều tra.

## 34. Dấu hiệu "DLQ luôn bằng 0" có thể do quan sát sai

Trước khi kết luận DLQ không hoạt động, cần kiểm tra **ba điểm quan sát độc lập**:

1. **Producer của DLQ đã publish thành công hay chưa?** Xem logger của recoverer, broker permission/producer failure và metric publish error.
2. **DLQ destination có thực sự tồn tại và có dữ liệu ở broker không?** Xem topic/queue stats, đúng vhost/namespace/cluster.
3. **DLQ consumer đã đọc và ack nhanh tới mức backlog trở về 0 chưa?** Đọc producer rate, consumer rate, offset/cursor hoặc audit của DLQ processor.

Ví dụ Kafka DLQ topic tồn tại và có log end offset tăng, nhưng consumer group `dlq-replay` cũng commit nhanh. Consumer lag của replay group bằng 0 không có nghĩa không có record nào được ghi vào DLQ. Tương tự RabbitMQ `messages_ready=0` có thể vì DLQ processor đang giữ `unacknowledged` hoặc đã ack; Pulsar subscription backlog thấp có thể vì cursor đã tiến trong khi topic vẫn có dữ liệu tùy retention.

Muốn xác minh, tạo một test record có `eventId` rõ, tạm ngắt consumer replay nếu được phép trong staging, rồi theo dõi **producer publish acknowledgement** và broker stats. Không dùng số liệu backlog duy nhất để chứng minh toàn bộ pipeline lỗi.

## 35. Custom error handler có thể chiếm quyền xử lý lỗi

Spring Cloud Stream cho phép khai báo function xử lý `ErrorMessage` riêng thông qua `error-handler-definition`. Theo tài liệu các dòng hiện đại, **custom error handler và binder-provided error handling/DLQ có thể loại trừ nhau** để không cùng xử lý một lỗi. Vì vậy cấu hình có `enableDlq: true` nhưng binding lại gắn custom handler có thể khiến DLQ không nhận message theo kỳ vọng.

Ví dụ cấu hình cần kiểm tra:

```yaml
spring:
  cloud:
    stream:
      bindings:
        processOrder-in-0:
          destination: orders.events
          group: order-projection
          error-handler-definition: orderErrorHandler
```

Đừng tự giả định function `orderErrorHandler` vừa ghi log vừa kích hoạt recoverer DLQ của binder. Phải đọc logic của handler và semantics của bản Spring Cloud Stream đang dùng. Nếu cần cả thông báo lỗi lẫn DLQ, hãy thiết kế một recovery path thống nhất (hoặc observer tách rời) và kiểm thử kết quả cuối, không bật hai handler cạnh tranh nhau.

## 36. Retry count và DLQ count: chọn metric không gây nhầm

| Metric đề xuất | Ý nghĩa | Cách dùng |
|---|---|---|
| `message_processing_failures_total` | Tổng số xử lý thất bại | Phân loại exception và binding |
| `retry_attempts_total` | Số lần thử lại ở tầng ứng dụng | Không đồng nghĩa redelivery count broker |
| `broker_redeliveries_total` | Số lần broker giao lại message | Cảnh báo vòng requeue/nack/ack timeout |
| `dlq_published_total` | Số lần recoverer phát DLQ thành công | Đối chiếu producer acknowledgement |
| `dlq_publish_failures_total` | Lỗi khi ghi DLQ | Cảnh báo sớm nguy cơ message bị kẹt/mất |
| `dlq_backlog` | Số message đang chờ xử lý trong DLQ | Dùng cùng rate để đánh giá trend |
| `replay_requested_total` | Số lệnh replay được tạo | Audit ý định vận hành |
| `replay_succeeded_total` | Event replay đã được xử lý thành công | Không nhầm với chỉ số publish đã gọi |
| `replay_exhausted_total` | Event vượt trần replay | Buộc chuyển parking lot |
| `parking_lot_backlog` | Event đã cách ly, chờ triage | Theo dõi công việc tồn lâu |
| `ordering_gap_total` | Message tới sau version bị thiếu | Phát hiện tác động của DLQ/replay lên ordering |

Metric ở đây là **đề xuất đặt tên cho ứng dụng**, không phải cam kết Spring Cloud Stream tự cung cấp đủ các tên trên. Nên dùng Micrometer/Actuator và metric broker thực tế, gắn tags có cardinality thấp (binder, binding, error class, outcome) thay vì đưa mọi `eventId` vào metric labels. ID cụ thể nên nằm trong log/tracing có kiểm soát.

Một warning hợp lý: **cùng một event được redeliver quá X lần trong Y phút**, `dlq_publish_failures_total` tăng, hoặc `replay_exhausted_total` tăng đột biến. Chỉ cảnh báo theo độ sâu DLQ có thể bỏ sót trường hợp DLQ trống vì đang retry vô hạn.

## 37. Đọc log đúng mức để không làm sự cố nặng thêm

Khi lỗi xảy ra liên tục, việc bật DEBUG/TRACE toàn bộ Spring Kafka, Rabbit, Pulsar và framework có thể làm đĩa đầy hoặc giảm throughput. Quy trình an toàn:

- Lọc log theo một `eventId`/partition-offset/subscription message ID.
- Bật logger chi tiết ở **phạm vi hẹp và thời gian ngắn** nếu cần.
- Ghi exception type và root cause, giữ stacktrace cho số lượng mẫu có giới hạn.
- Phân biệt `business failure`, `DLQ publish failure`, `consumer disconnect`, `serialization failure` và `replay publish failure`.
- Không log token, SASL password, Pulsar JWT, raw PII hoặc toàn bộ payload nhạy cảm.
- Ghi version ứng dụng, binding name, binder type, destination và group/subscription.

Một dấu hiệu cần chú ý: lỗi lặp với chu kỳ đều chính xác 30 giây có thể từ retry queue TTL hoặc negative-ack delay, trong khi lỗi sát nhau vài mili-giây có thể từ requeue nóng hoặc retry loop trong code. Đây chỉ là **gợi ý suy luận**, không thay thế kiểm tra configuration/log broker.

## 38. Bài thực hành: ba lỗi khác nhau trên cùng sự kiện

Giả sử `OrderEvent(eventId="evt-1082", orderId="order-42", status="PAID")` bị lỗi do `InvalidOrderStateException`. Chuẩn bị topic/queue thử nghiệm `orders.events`, group/subscription `order-projection` và DLQ `orders.events.dlq` trong staging.

**Tình huống A — Retry vô hạn.** Bật đường redelivery lặp lại phù hợp broker (ví dụ Rabbit requeue) và phát một event có lỗi cố định. Quan sát attempt logs, broker redelivery và CPU. Sau đó chuyển sang retry hữu hạn + DLQ, xác minh message dừng lặp và tới DLQ sau số lần hợp lệ.

**Tình huống B — DLQ trống.** Cố ý bắt exception trong handler nhưng không ném lại. Quan sát message được coi thành công và DLQ không nhận gì. Sau đó sửa handler để truyền lỗi ra, bật đúng DLQ binding, kiểm tra DLQ topic/queue và producer permission. Với Kafka, thử thêm một payload lỗi native deserializer để hiểu vì sao handler không được gọi.

**Tình huống C — Replay loop.** Tạo replay worker tự đưa DLT record trở lại main trong một environment cô lập; quan sát vòng lặp tăng số message. Bổ sung `originalEventId`, durable ledger với `MAX_REPLAY_ATTEMPTS=2`, parking lot và điều kiện lỗi được sửa. Kiểm tra cuối cùng chỉ có tối đa hai lượt replay **trên event gốc** theo policy, sau đó dừng dù worker restart.

Trong cả ba tình huống, lưu trước/sau: số lần handler được gọi, broker publish/ack count, DLQ backlog, database side effect và số event đã kết thúc tại parking lot.

## 39. Ma trận integration test cần có

| Test | Thiết lập | Kết quả kỳ vọng |
|---|---|---|
| Lỗi tạm thời | Handler fail hai lần rồi thành công | Số retry nằm trong limit, không DLQ sai |
| Poison message | Handler luôn ném lỗi vĩnh viễn | Hết retry, dừng vòng lặp và vào DLQ/parking lot |
| Exception bị nuốt | Handler catch rồi return | Test chứng minh không kích hoạt binder DLQ; có cảnh báo/code fix |
| Kafka DLQ disabled | `enableDlq=false` | Xác định container recovery thay vì giả định DLT |
| Kafka group missing | Không đặt group | Không kỳ vọng Kafka Binder DLQ hoạt động như khi có group |
| Kafka malformed bytes | Native deserializer ném lỗi | Lỗi được xử lý theo deserialization path riêng |
| Kafka DLT partition mismatch | DLT ít partition hơn nguồn | Cảnh báo lỗi producer; không mất dữ liệu im lặng |
| Kafka Streams Serde | Đầu vào không decode được | Kiểm tra `sendToDlq` cho deserialization-only path |
| Rabbit requeue | Reject + requeue | Quan sát vòng lặp trước/sau thay đổi config |
| Rabbit DLX routing sai | DLX không có binding hợp lệ | DLQ không nhận; test phát hiện topology sai |
| Rabbit DLQ consumer đang chạy | Consumer DLQ ack liên tục | Backlog có thể thấp dù DLT publisher hoạt động |
| Rabbit TTL loop | Retry queue DLX trở lại main | Retry cap/parking lot thực sự chặn vòng |
| Pulsar negative ack | Restart broker/consumer giữa retry | Bộ đếm nack có thể reset, không khẳng định DLT sẽ nhận |
| Pulsar retry-letter | `enableRetry(true)`, `reconsumeLater` | Retry count bền vững theo message property, DLT nhận khi hết limit |
| Replay worker restart | Restart trước/sau publish | Ledger vẫn giữ attempt count; idempotency an toàn |
| Replay publish failure | Broker từ chối publish về nguồn | Không ack DLQ như đã chuyển tiếp thành công |
| Event cũ replay | Version cũ hơn database projection | Không ghi đè trạng thái mới |
| Lưu lượng lớn | Phát nhiều poison message | Có rate limit, không DLQ/replay storm |

Test Binder trong JVM giúp kiểm tra function và một phần error routing, nhưng không chứng minh Kafka container seek/rebalance, Rabbit DLX/nack hoặc Pulsar retry counter. Các trường hợp này cần broker thật/Testcontainers hoặc môi trường integration tương thích. Không chạy phá hủy dữ liệu production chỉ để thử một kịch bản lỗi.

## 40. Decision table: từ triệu chứng đến bước tiếp theo

| Triệu chứng thực tế | Khả năng cao | Bước kiểm tra đầu tiên |
|---|---|---|
| `maxAttempts=1` nhưng Kafka vẫn retry | Listener container vẫn có error handler retry | Xem `CommonErrorHandler` và tài liệu binder release |
| Kafka retry xong nhưng DLT rỗng | `enableDlq=false`, group thiếu, sai binding hoặc publish DLT lỗi | Kiểm tra extended property, group, destination, quyền |
| Kafka Streams topology chết, DLT rỗng | Exception không phải Serde hoặc handler đang `logAndFail` | Xác minh lỗi xảy ra ở deserialization hay processing |
| Rabbit mỗi giây xử lý lại cùng event | `requeueRejected=true`, nack/requeue hoặc TTL loop | Xem queue arguments, consumer ack/nack và DLX |
| Rabbit DLQ được khai báo nhưng luôn 0 | Sai routing/vhost, republish fail hoặc có DLQ consumer | Xem exchange binding + ready/unacked/consumer |
| Pulsar negative-ack nhiều lần, không thấy DLT | Counter redelivery reset hoặc policy thiếu | Xem subscription type, retry letter và reconnect |
| DLQ tăng rồi giảm rất nhanh | Replay worker tự động hoặc DLQ consumer ack | Tạm dừng có kiểm soát trong staging, xem audit/offset |
| Cùng business event quay lại mãi nhưng offset mới | Publish lại từ replay thay vì retry tại chỗ | Trace `originalEventId` và replay worker |
| Đã sửa code nhưng event vẫn lỗi | Dữ liệu vĩnh viễn sai, schema chưa sửa hoặc replay quá sớm | Kiểm tra root cause trên một record mẫu |
| Replay làm trạng thái DB lùi về version cũ | Thiếu idempotency/version gate | Kiểm tra ledger/version và transaction |
| DLQ publish thỉnh thoảng thất bại | ACL, broker outage, header quá lớn, serializer | Xem recoverer producer errors và metrics |
| Message lỗi bị mất mà không ở DLQ | Handler catch, ack sớm, drop/error handler custom | Truy vết từ receive đến ack và recovery |

Nếu vẫn không xác định được nguồn vòng lặp, ưu tiên **cô lập một message** trong môi trường kiểm thử; dùng trace ID và kiểm tra thời điểm ack/publish ở từng lớp. Không thay đồng thời serializer, retry policy, consumer concurrency và queue topology, vì không còn biết thay đổi nào tạo ra kết quả.

## 41. Runbook khi sự cố đang diễn ra

**Trong 5–10 phút đầu**, tập trung giảm tác động thay vì thay đổi dữ liệu:

1. Xác minh broker/cluster và môi trường đúng, ghi version deployment và cấu hình hiệu lực.
2. Chọn một poison `eventId`, trace nó từ input qua retry tới DLQ/replay.
3. Kiểm tra queue/topic có đang tăng theo cấp số nhân hay không; đo error/retry rate và tốc độ xử lý thành công.
4. Nếu replay worker là nguồn loop, **tạm dừng riêng replay worker** theo quy trình vận hành và xác nhận DLQ/parking lot vẫn giữ dữ liệu.
5. Nếu consumer đang làm sập downstream, cân nhắc giảm concurrency/pause consumer ở scope thích hợp sau khi đánh giá tác động backlog và SLA.
6. Sao lưu metadata và bằng chứng lỗi; tránh purge/offset reset.

**Trong giai đoạn khắc phục**, xác định root cause, sửa đúng cấu hình binder hoặc dữ liệu, kiểm thử một record mẫu, rồi mới triển khai canary. Nếu vấn đề là lỗi schema vĩnh viễn, tăng backoff có thể giảm áp lực nhưng không thay thế sửa schema hoặc quarantine. Nếu là lỗi môi trường (DB down), có thể đặt consumer tạm chờ với backoff hữu hạn nhằm tránh retry storm.

**Sau khi ổn định**, chạy replay theo batch giới hạn; theo dõi thành công, lỗi và ordering gap. Không kết thúc incident khi queue chính giảm về 0 nhưng DLQ/parking lot chưa có kế hoạch xử lý.

## 42. Vận hành replay có kiểm soát

Một quy trình replay production có thể gồm các bước:

1. Tạo ticket/approval gắn với `source`, `DLQ`, dải event ID, số lượng và lý do.
2. Xác minh source code/schema/ACL đã sửa đúng nguyên nhân ban đầu.
3. Chụp số lượng DLQ trước replay, thống kê theo loại lỗi và tuổi sự kiện.
4. Chọn canary 1–10 events, gửi có rate limit và quan sát xử lý end-to-end.
5. Ghi ledger theo `originalEventId` để tránh hai operator hoặc worker phát lại cùng event.
6. Mở rộng batch dần trong giới hạn throughput downstream; kiểm tra database state/version.
7. Với event không thể phục hồi, chuyển parking lot và gắn lý do xử lý cuối.
8. Kết thúc bằng báo cáo `requested`, `published`, `consumed_successfully`, `parked`, `duplicate_skipped` và outstanding count.

Không xóa lịch sử lỗi chỉ vì một event đã được replay thành công. Giữ audit tối thiểu cần thiết theo chính sách retention/privacy; payload nhạy cảm nên được mã hóa hoặc tham chiếu bằng ID thay vì lưu tràn lan trong log.

## 43. Bảo vệ thứ tự, idempotency và giao nhận

Một consumer có thể nhận cùng message nhiều lần theo at-least-once. Giải pháp nền tảng:

- Gắn `eventId` ổn định và unique constraint/deduplication ledger ở storage.
- Kiểm tra `aggregateVersion` hoặc business sequence trước khi áp dụng update.
- Trong cùng transaction, ghi trạng thái mới và dấu event đã xử lý.
- Ack/commit chỉ sau khi side effect bắt buộc hoàn tất bền vững.
- Khi replay event cũ, quyết định bỏ qua/khôi phục ordering gap thay vì ghi đè mù.
- Phân biệt `message processed` và `message successfully published to DLQ/replay topic`.

Ví dụ giao nhận at-least-once an toàn hơn:

```text
Receive event
  -> begin DB transaction
  -> if eventId already applied: skip duplicate
  -> else validate version and apply state change
  -> store eventId in processed-events table
  -> commit DB transaction
  -> acknowledge/commit broker message
```

Nếu crash xảy ra **sau DB commit nhưng trước broker ack**, event có thể được giao lại. Nhờ unique constraint và version check, consumer không nhân đôi side effect. Nếu lỗi ở bước publish DLQ/replay, cần một workflow bảo đảm at-least-once khác hoặc outbox; không tuyên bố một transaction database tự đồng bộ với broker.

## 44. Checklist xử lý trước khi tuyên bố đã sửa lỗi

- [ ] Đã xác định binder và model: imperative, reactive hay Kafka Streams.
- [ ] Đã xác định input binding, destination và group/subscription thực tế.
- [ ] Có event ID ổn định để nối các lần retry/redelivery/replay.
- [ ] Đã xác định chính xác lớp retry: code, binder, container hay broker.
- [ ] Có retry cap/backoff phù hợp với phân loại exception.
- [ ] Với Kafka, đã kiểm tra `enableDlq`, group và lỗi DLT producer/partition.
- [ ] Với Kafka Streams, đã phân biệt Serde lỗi với processing exception.
- [ ] Với RabbitMQ, đã kiểm tra `requeueRejected`, `autoBindDlq`, DLX/routing/vhost.
- [ ] Với Pulsar, đã hiểu negative ack/ack timeout và persistent retry-letter counter.
- [ ] Đã xác minh record lỗi thực sự tới đúng DLQ, không chỉ log "đã chuyển".
- [ ] Đã kiểm tra DLQ có consumer nào đang làm backlog trở về 0 không.
- [ ] Replay chỉ chạy sau khi lỗi có thể sửa và có trần số lần bền vững.
- [ ] Có parking lot không tự quay về topic/queue chính.
- [ ] Có idempotency và version/order handling cho replay sự kiện cũ.
- [ ] Đã kiểm thử crash giữa publish, DB commit và ack/offset commit.
- [ ] Không còn retry/replay storm khi phát một poison record trong staging.
- [ ] Có dashboard/alert cho replay attempts, DLQ publish failure và DLQ backlog.
- [ ] Không dùng purge/reset offset như bước sửa lỗi mặc định.

## 45. Câu hỏi tự kiểm tra

1. Retry trong `RetryTemplate` khác gì redelivery do broker tạo ra sau nack/disconnect?
2. Vì sao `maxAttempts: 3` không đủ để kết luận một RabbitMQ message chỉ được xử lý ba lần tổng cộng?
3. Trên Kafka Binder, điều kiện group và `enableDlq` cần được khai báo ở các namespace cấu hình nào?
4. Vì sao `maxAttempts: 1` có thể không tắt retry của Kafka listener container trong một số bản mới?
5. Nếu handler catch exception rồi return, DLQ có tự nhận dữ liệu không?
6. RabbitMQ `requeueRejected: true` có thể tạo loại vòng lặp nào?
7. Khác biệt giữa Rabbit broker DLX và `republishToDlq` của binder là gì?
8. Vì sao Pulsar negative ack có thể không đạt `maxRedeliverCount` sau consumer reconnect?
9. Muốn có retry limit bền vững với Pulsar, retry-letter topic khác negative ack ở điểm nào?
10. `sendToDlq` trong Kafka Streams Binder chủ yếu xử lý loại lỗi gì?
11. Vì sao `x-retries` ở header không luôn đủ để ngăn replay loop?
12. Cần xử lý gì khi replay event version 11 sau khi version 12 đã cập nhật DB?
13. Nếu DLQ backlog = 0, cần ba điểm quan sát nào trước khi kết luận DLQ không hoạt động?
14. Tại sao parking lot cần tách khỏi đường tự động hồi lưu tới main destination?
15. Nếu lỗi publish replay xảy ra ngay sau khi DB ledger commit, cần cơ chế nào để tránh mất yêu cầu replay?

## Kết luận

Ba hiện tượng **retry vô hạn**, **DLQ rỗng** và **replay thành vòng lặp** chỉ có thể được giải quyết bền vững sau khi phân biệt đúng ranh giới giữa **exception của function**, **retry binder/container**, **redelivery của broker** và **workflow replay**. Kafka Binder cần kiểm tra `enableDlq`, group, DLT producer, partition và listener error handler; Kafka Streams Binder có đường xử lý deserialization riêng. RabbitMQ cần kiểm soát requeue/nack, DLX/routing và republish; Pulsar cần phân biệt negative ack với retry letter topic có bộ đếm bền vững. Trong mọi trường hợp, hãy dùng retry hữu hạn, backoff phù hợp, DLQ/parking lot rõ ràng, replay ledger theo event ID, idempotency, kiểm soát thứ tự và integration test fault injection. **DLQ không phải cơ chế tự sửa lỗi và replay không nên tự động diễn ra mãi.**

## Tài liệu tham khảo

- Spring Cloud Stream — General Error Handling: https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/overview-error-handling.html
- Spring Cloud Stream — Kafka Binder DLT Processing: https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-binder/dlq.html
- Spring Cloud Stream — Kafka Binder Configuration Options: https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-binder/config-options.html
- Spring Cloud Stream — Kafka Streams Binder Error Handling: https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-streams-binder/error-handling.html
- Spring Cloud Stream — RabbitMQ Consumer Properties: https://docs.spring.io/spring-cloud-stream/reference/rabbit/rabbit_overview/rabbitmq-consumer-properties.html
- Spring Cloud Stream — RabbitMQ Binder Overview: https://docs.spring.io/spring-cloud-stream/reference/rabbit/rabbit_overview/rabbitmq-overview.html
- Spring Cloud Stream — Pulsar Binder: https://docs.spring.io/spring-cloud-stream/reference/pulsar/pulsar_binder.html
- Apache Pulsar — Message Redelivery, Retry Letter Topics and Dead Letter Policies: https://pulsar.apache.org/docs/4.0.x/concepts-messaging/
- Spring Kafka — Handling Exceptions: https://docs.spring.io/spring-kafka/reference/kafka/annotation-error-handling.html
- RabbitMQ — Dead Letter Exchanges: https://www.rabbitmq.com/docs/dlx
