# Xử lý đơn hàng đúng thứ tự theo khóa với nhiều instance

Một hệ thống đơn hàng thường nhận nhiều sự kiện cho cùng một đơn: tạo đơn, xác nhận thanh toán, giữ hàng, đóng gói, giao hàng và hủy đơn. Các sự kiện của một đơn phải được áp dụng theo đúng thứ tự nghiệp vụ. Trong khi đó, hệ thống cần nhiều instance consumer để tăng throughput và tiếp tục hoạt động khi một instance dừng.

Thách thức là **song song giữa các đơn hàng nhưng tuần tự bên trong từng đơn hàng**. Nếu hai instance cùng xử lý những sự kiện của một `orderId`, sự kiện cập nhật trạng thái mới có thể hoàn tất trước sự kiện cũ. Chỉ tăng số consumer hoặc dùng một consumer group không tự bảo đảm thứ tự nghiệp vụ.

Bài thực hành này xây dựng luồng Spring Cloud Stream với Kafka làm ví dụ chính: producer gắn `orderId` làm record key, Kafka phân phối các key vào partition, nhiều instance cùng consumer group xử lý các partition khác nhau, còn database kiểm tra `eventId` và `sequence` để chống trùng và phát hiện sự kiện đến sai thứ tự. Phần cuối đối chiếu cách triển khai với RabbitMQ và Pulsar.

## 1. Mục tiêu và tiêu chí hoàn thành

Sau bài thực hành, hệ thống cần đáp ứng:

- Sự kiện của cùng một `orderId` đi vào cùng một partition Kafka.
- Các partition khác nhau được xử lý song song bởi nhiều consumer instance.
- Trong một partition, handler xử lý tuần tự và không chạy side effect bất đồng bộ làm đảo thứ tự.
- Mỗi đơn có sequence tăng dần; consumer phát hiện thiếu, trùng hoặc sai thứ tự.
- Restart, rebalance và redelivery không làm mất sự kiện; duplicate không tạo side effect nghiệp vụ lần thứ hai.
- Retry/DLQ không âm thầm cho phép sự kiện sau của cùng đơn vượt qua một sự kiện trước chưa được xử lý.
- Có kiểm thử chứng minh thứ tự với nhiều instance, nhiều partition và tình huống lỗi.

### 1.1. Phạm vi bảo đảm

Trong Kafka, thứ tự được bảo đảm trong phạm vi một partition. Nếu tất cả event của cùng đơn được ghi vào cùng partition, consumer có thể xử lý chúng theo thứ tự broker lưu. Kafka không tạo thứ tự toàn cục giữa các partition.

Thứ tự này là thứ tự append vào partition, không tự động là thứ tự thời gian tạo event trong nhiều producer độc lập. Nếu hai service cùng phát event cho một đơn, hệ thống phải có nguồn cấp sequence/serialization có thẩm quyền để quyết định event nào đến trước.

~~~mermaid
flowchart LR
    A[Order A events] --> K1[Partition 0]
    B[Order B events] --> K1
    C[Order C events] --> K2[Partition 1]
    D[Order D events] --> K3[Partition 2]
    K1 --> W1[Consumer instance 1]
    K2 --> W2[Consumer instance 2]
    K3 --> W3[Consumer instance 3]
    W1 --> DB[(Order state)]
    W2 --> DB
    W3 --> DB
~~~

Trong hình, các đơn A và B có thể cùng partition nên được xử lý tuần tự trong partition đó. Đơn C và D nằm ở partition khác nên có thể xử lý đồng thời. Không có cam kết thứ tự giữa A và C vì chúng thuộc hai partition khác nhau.

## 2. Mô hình dữ liệu và quy tắc thứ tự

Mỗi event cần ít nhất bốn trường:

| Trường | Mục đích |
|---|---|
| `eventId` | ID duy nhất để nhận diện và chống xử lý trùng. |
| `orderId` | Khóa nghiệp vụ; dùng làm Kafka record key. |
| `sequence` | Số thứ tự tăng dần trong phạm vi một đơn hàng. |
| `eventType` | Loại thay đổi nghiệp vụ như `ORDER_CREATED`, `PAYMENT_CONFIRMED`. |

Ví dụ Java record:

~~~java
package com.acme.orders;

import java.time.Instant;
import java.util.UUID;

public record OrderEvent(
    UUID eventId,
    String orderId,
    long sequence,
    String eventType,
    Instant occurredAt,
    long amountInMinorUnit
) {}
~~~

Một đơn hàng có chuỗi event:

| orderId | sequence | eventType |
|---|---:|---|
| `ORD-1001` | 1 | `ORDER_CREATED` |
| `ORD-1001` | 2 | `PAYMENT_CONFIRMED` |
| `ORD-1001` | 3 | `STOCK_RESERVED` |
| `ORD-1001` | 4 | `ORDER_PACKED` |
| `ORD-1001` | 5 | `ORDER_SHIPPED` |

Đơn `ORD-2002` có sequence riêng bắt đầu từ 1. Không so sánh sequence của hai đơn khác nhau.

Quy tắc consumer:

1. Nếu `eventId` đã xử lý, bỏ qua như duplicate.
2. Nếu sequence bằng `lastSequence + 1`, áp dụng event và cập nhật trạng thái.
3. Nếu sequence lớn hơn `lastSequence + 1`, phát hiện gap: một hoặc nhiều event trước đang thiếu.
4. Nếu sequence nhỏ hơn hoặc bằng `lastSequence` nhưng eventId khác, phát hiện stale/conflicting event; cần kiểm tra dữ liệu và chính sách replay.

Sequence là kiểm tra nghiệp vụ bổ sung. Kafka key bảo đảm cùng key vào cùng partition, nhưng sequence giúp phát hiện lỗi từ upstream, replay sai thứ tự hoặc thay đổi partitioning.

## 3. Chọn orderId làm partition key

Kafka phân phối record vào partition dựa trên key và partitioner. Với partitioner mặc định, cùng một key thường được ánh xạ ổn định vào cùng partition khi số partition không đổi. Vì vậy, mọi event có `orderId=ORD-1001` sẽ được ghi vào cùng partition nếu producer luôn gửi đúng key.

Không dùng `eventId` làm key cho luồng cần thứ tự theo đơn. Event ID thay đổi ở mỗi message nên các event của một đơn có thể đi vào nhiều partition khác nhau.

### 3.1. Cấu hình producer key trong Kafka binder

Khai báo output binding và dùng header `orderId` làm Kafka message key:

~~~yaml
spring:
  cloud:
    stream:
      output-bindings: orders-out-0
      bindings:
        orders-out-0:
          destination: orders.events
      kafka:
        bindings:
          orders-out-0:
            producer:
              message-key-expression: headers['orderId']
              configuration:
                enable.idempotence: true
                acks: all
                max.in.flight.requests.per.connection: 5
~~~

`message-key-expression` là biểu thức của Kafka binder để lấy key từ message. Ví dụ này yêu cầu producer đặt header `orderId` trước khi gửi. `enable.idempotence`, `acks` và `max.in.flight.requests.per.connection` là cấu hình Kafka producer; chúng giúp tăng độ tin cậy của retry phía producer và giữ thứ tự batch trong giới hạn được Kafka hỗ trợ.

Publisher gửi `Message` qua `StreamBridge`:

~~~java
package com.acme.orders;

import org.springframework.cloud.stream.function.StreamBridge;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.stereotype.Component;

@Component
public class OrderEventPublisher {

    private final StreamBridge streamBridge;

    public OrderEventPublisher(StreamBridge streamBridge) {
        this.streamBridge = streamBridge;
    }

    public boolean publish(OrderEvent event) {
        Message<OrderEvent> message = MessageBuilder
            .withPayload(event)
            .setHeader("orderId", event.orderId())
            .build();

        return streamBridge.send("orders-out-0", message);
    }
}
~~~

Giá trị trả về của `send` cho biết message đã được chấp nhận ở tầng message channel của framework. Nó không tự chứng minh broker đã lưu bền vững hoặc consumer đã xử lý xong.

### 3.2. Producer phải phát event theo sequence

Partition key chỉ chọn partition; nó không sắp xếp hai producer độc lập theo thời điểm nghiệp vụ. Ví dụ:

- Producer A tạo event sequence 2 nhưng bị chậm network.
- Producer B gửi event sequence 3 và đến Kafka trước.
- Kafka append sequence 3 trước sequence 2 dù cùng key.

Consumer sẽ nhìn thấy thứ tự append, không thể tự suy ra sequence 2 phải đến trước chỉ từ timestamp.

Để tránh trường hợp này, nguồn phát event cần:

- Cấp sequence trong transaction cập nhật aggregate đơn hàng.
- Ghi event vào transactional outbox cùng transaction với trạng thái đơn.
- Dispatcher chỉ publish các outbox record theo thứ tự sequence của cùng `orderId`.
- Có thể chạy nhiều dispatcher song song theo shard/key, nhưng cùng một key phải được một luồng dispatcher tuần tự hóa.
- Đánh dấu outbox record đã publish sau khi gửi thành công; nếu crash sau publish trước khi đánh dấu, event có thể được gửi lại nên consumer vẫn cần idempotency.

Không dựa vào `occurredAt` để sắp xếp tuyệt đối: đồng hồ giữa instance có thể lệch, timestamp có thể trùng và thời điểm ghi nhận không nhất thiết là thứ tự commit nghiệp vụ.

## 4. Thiết kế topic và số partition

Trong bài thực hành, tạo topic `orders.events` với 12 partition. Đây là ví dụ để minh họa nhiều consumer; môi trường thực tế cần chọn partition count theo throughput, kích thước cluster, số key hoạt động và khả năng vận hành.

Với ba application instance, mỗi instance có concurrency 4:

\[
3\ \text{instances} \times 4\ \text{consumer threads} = 12
\]

Tổng số consumer thread bằng số partition nên có thể sử dụng đủ 12 partition trong một group, nếu tất cả thread hoạt động và broker phân phối assignment bình thường.

Nếu tổng consumer thread lớn hơn partition count, một số consumer sẽ không được gán partition và ở trạng thái idle. Nếu nhỏ hơn partition count, một consumer có thể xử lý nhiều partition.

### 4.1. Không tăng partition count tùy tiện

Với partitioner dựa trên hash(key) và modulo số partition, thay đổi số partition có thể làm một key được ánh xạ sang partition khác. Khi đó:

- Event cũ của `ORD-1001` vẫn nằm ở partition cũ.
- Event mới của cùng đơn có thể được ghi vào partition mới.
- Hai partition có thể được consumer xử lý song song.
- Không còn một thứ tự duy nhất giữa lịch sử cũ và event mới của đơn đó.

Nếu cần tăng partition, hãy lập kế hoạch migration: dừng hoặc rào producer, chuyển dữ liệu theo key, dùng topic phiên bản mới hoặc cơ chế routing ổn định có version. Không coi tăng partition là thay đổi chỉ ảnh hưởng throughput.

## 5. Cấu hình nhiều consumer instance cùng group

Consumer cần cùng `group` để Kafka phân phối partition giữa các instance. Nếu mỗi instance dùng group riêng, mỗi instance sẽ nhận toàn bộ luồng và có thể tạo side effect trùng.

~~~yaml
spring:
  cloud:
    function:
      definition: processOrders
    stream:
      bindings:
        processOrders-in-0:
          destination: orders.events
          group: orders-processor
          consumer:
            concurrency: 4
            max-attempts: 3
      kafka:
        bindings:
          processOrders-in-0:
            consumer:
              configuration:
                max.poll.records: 1
                max.poll.interval.ms: 300000
~~~

`concurrency: 4` yêu cầu mỗi application instance tạo bốn consumer thread cho binding. Với ba instance, tổng cộng có tối đa 12 member trong group. Kafka tự phân phối partition giữa các member.

`max.poll.records: 1` được dùng ở bài tập để làm rõ thứ tự từng record và đơn giản hóa quan sát. Đây không phải giá trị tối ưu throughput cho mọi hệ thống; khi chuyển sang batch, phải kiểm tra thời gian xử lý và semantics của batch error handling.

Không cần đặt `instanceCount`/`instanceIndex` để Kafka consumer group tự chia partition. Các thuộc tính instance đó thuộc cơ chế partitioned producer/consumer của Spring Cloud Stream và không thay thế consumer group assignment của Kafka.

### 5.1. Một partition chỉ có một consumer trong group tại một thời điểm

Trong cùng consumer group, một partition được gán cho tối đa một consumer member tại một thời điểm. Do đó, nhiều instance có thể xử lý nhiều partition đồng thời nhưng không xử lý song song cùng một partition trong cùng group.

Điều này tạo nền tảng cho thứ tự theo key:

1. Producer đặt `orderId` làm key.
2. Kafka ghi mọi event cùng key vào cùng partition.
3. Một consumer member sở hữu partition đó.
4. Consumer xử lý record theo thứ tự poll/listener.
5. Khi rebalance, partition có thể chuyển sang member khác; offset/commit quyết định vị trí tiếp tục.

Không chạy thêm `@Async`, `parallelStream()` hoặc executor không kiểm soát bên trong handler nếu side effect phải giữ thứ tự. Nếu listener nhận record 1 rồi gửi xử lý async, record 2 có thể hoàn tất trước record 1 dù Kafka đã giao đúng thứ tự.

## 6. Consumer function xử lý tuần tự

Function imperative nhận từng event:

~~~java
package com.acme.orders;

import java.util.function.Consumer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class OrderFunctions {

    @Bean
    Consumer<OrderEvent> processOrders(OrderService orderService) {
        return orderService::applyInOrder;
    }
}
~~~

Function này gọi service đồng bộ. Khi một consumer thread đang xử lý event hiện tại, nó chưa hoàn tất invocation trước thì không nên tự chuyển side effect sang background thread rồi trả về thành công.

Nếu dùng reactive function, cần giữ thứ tự bằng toán tử tuần tự như `concatMap` trong từng luồng partition. `flatMap` với concurrency có thể cho phép nhiều event chạy đồng thời và hoàn tất không theo thứ tự nguồn. Việc giữ thứ tự khi emit output cũng chưa đủ nếu side effect bên trong các inner publisher đã chạy song song.

## 7. Sequence guard và idempotency ở database

Kafka at-least-once có thể giao lại record khi consumer crash sau khi thực hiện business logic nhưng trước khi offset được commit. Vì vậy, service cần chống duplicate ở tầng nghiệp vụ.

Một mô hình bảng đơn giản:

| Bảng | Khóa | Dữ liệu chính |
|---|---|---|
| `orders` | `order_id` | trạng thái đơn, `last_sequence`, version |
| `processed_events` | `event_id` | thời điểm xử lý, `order_id`, sequence |

Database cần unique constraint trên `processed_events.event_id`. Việc ghi processed event và cập nhật order state phải nằm trong cùng transaction DB.

~~~java
@Service
public class OrderService {

    private final ProcessedEventRepository processedEvents;
    private final OrderRepository orders;

    public OrderService(
            ProcessedEventRepository processedEvents,
            OrderRepository orders) {
        this.processedEvents = processedEvents;
        this.orders = orders;
    }

    @Transactional
    public void applyInOrder(OrderEvent event) {
        boolean firstDelivery = processedEvents.insertIfAbsent(
            event.eventId(), event.orderId(), event.sequence()
        );

        if (!firstDelivery) {
            return; // Event ID đã được áp dụng trước đó.
        }

        OrderState state = orders.findForUpdate(event.orderId())
            .orElseGet(() -> {
                if (event.sequence() != 1 ||
                        !"ORDER_CREATED".equals(event.eventType())) {
                    throw new IllegalStateException(
                        "First event for an order must be ORDER_CREATED"
                    );
                }
                return OrderState.newOrder(event.orderId());
            });

        long expected = state.lastSequence() + 1;
        if (event.sequence() != expected) {
            throw new SequenceGapException(
                event.orderId(), expected, event.sequence()
            );
        }

        state.apply(event);
        state.setLastSequence(event.sequence());
        orders.save(state);
    }
}
~~~

`insertIfAbsent` cần được triển khai bằng unique constraint/upsert nguyên tử, không phải thao tác SELECT rồi INSERT thiếu khóa. Nếu sequence guard ném exception, transaction DB rollback cả processed-event insert, vì vậy event có thể được thử lại sau khi xử lý gap.

Nếu event có sequence nhỏ hơn expected nhưng eventId mới, không tự động coi là duplicate hợp lệ. Đây có thể là event cũ được replay, event bị cấp sequence sai hoặc producer phát trùng logic. Hãy đưa vào luồng điều tra/quarantine theo contract.

### 7.1. Vì sao cần cả key và sequence?

| Cơ chế | Bảo vệ điều gì? | Không giải quyết được |
|---|---|---|
| Kafka key = `orderId` | Cùng đơn vào cùng partition. | Hai producer độc lập phát sai thứ tự trước khi append. |
| Partition ordering | Record trong một partition được đọc theo append order. | Thứ tự giữa partition hoặc side effect chạy async. |
| `eventId` unique | Chống áp dụng lại cùng event. | Phát hiện thiếu event sequence. |
| `sequence` theo order | Phát hiện gap hoặc event stale. | Tự khôi phục event bị thiếu. |
| DB transaction/lock | Bảo vệ cập nhật trạng thái đồng thời. | Atomic commit với Kafka nếu không dùng thiết kế giao dịch phù hợp. |

## 8. Xử lý sequence gap mà không phá thứ tự

Giả sử trạng thái đơn có `lastSequence=2`, nhưng consumer nhận event sequence 4. Event sequence 3 đang thiếu hoặc chưa đến.

Không nên áp dụng event 4 rồi chờ event 3 đến sau. Điều đó làm trạng thái nghiệp vụ đi ngược thứ tự. Cũng không nên gửi event 4 vào DLQ, commit offset rồi để event 5 tiếp tục cập nhật cùng đơn nếu yêu cầu là strict ordering.

Có ba chiến lược:

1. **Block partition:** dừng xử lý partition tại record lỗi cho đến khi khôi phục được event bị thiếu. Đây là lựa chọn đơn giản, bảo toàn thứ tự nhưng các key khác cùng partition cũng bị chặn.
2. **Per-key parking/sequencer:** lưu event đến sau vào kho pending theo `orderId`, giữ sequence gap và chỉ áp dụng khi event còn thiếu đã được bổ sung. Cần thiết kế transaction và khả năng phục hồi của kho pending.
3. **Quarantine + replay có kiểm soát:** chuyển record lỗi vào nơi cách ly, giữ checkpoint/offset chưa vượt qua ranh giới an toàn, sửa nguyên nhân rồi replay theo đúng sequence. Không chỉ publish lại một record vào cuối topic nếu các event sau đã được áp dụng.

Trong bài tập, chọn chiến lược block partition cho sequence gap để hành vi dễ kiểm chứng. Với production có nhiều key trên một partition, cần đánh giá tác động head-of-line blocking và cân nhắc per-key parking nếu yêu cầu sẵn sàng cao.

## 9. Retry và DLQ phải giữ invariant theo key

Retry có thể giữ partition đứng tại record lỗi, nhưng thời gian backoff kéo dài làm giảm throughput của partition. DLQ thường giúp consumer tiếp tục với record tiếp theo sau khi record lỗi được recover; điều đó có thể phá thứ tự nghiệp vụ của một key nếu event sau vẫn được xử lý.

Ví dụ:

| Offset | orderId | sequence | Kết quả |
|---:|---|---:|---|
| 100 | `ORD-1001` | 1 | Thành công |
| 101 | `ORD-1001` | 2 | Lỗi, chuyển DLQ và commit |
| 102 | `ORD-1001` | 3 | Thành công |

Trạng thái đơn đã áp dụng sequence 3 trong khi sequence 2 chưa được xử lý. Kafka vẫn giữ thứ tự offset, nhưng quy trình DLQ đã cho phép bỏ qua event trong luồng nghiệp vụ.

Với strict order:

- Phân biệt lỗi tạm thời có thể retry với lỗi poison cần can thiệp.
- Không commit vượt qua gap nếu partition phải giữ nguyên thứ tự.
- Nếu dùng DLQ, lưu original topic, partition, offset, key, sequence, eventId và exception metadata.
- Replay theo đúng key/sequence; không replay sau event mới hơn đã được áp dụng.
- Có cảnh báo khi một partition bị pause hoặc một order bị pending quá lâu.
- Dùng idempotency để replay không lặp side effect đã commit.

Ví dụ cấu hình retry hữu hạn cho record mode:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        processOrders-in-0:
          consumer:
            max-attempts: 3
~~~

Đây chỉ là giới hạn số lần thử ở tầng Spring Cloud Stream. Cần cấu hình error handler/DLQ của Kafka binder phù hợp và kiểm tra chính xác offset recovery. Nếu strict order yêu cầu block partition, không bật recovery tự động kiểu gửi DLQ rồi tiếp tục mà chưa có sequencer hoặc cơ chế giữ event sau.

## 10. Rebalance, restart và nhiều instance

Kafka có thể rebalance khi một instance khởi động hoặc dừng, consumer mất heartbeat hoặc không gọi poll đúng hạn, số partition thay đổi hoặc consumer group thay đổi membership.

Khi rebalance, partition có thể chuyển từ instance A sang instance B. Đây là hành vi bình thường. Để giữ thứ tự:

1. Dùng cùng group name trong mọi instance.
2. Không để consumer xử lý vượt `max.poll.interval.ms`.
3. Dùng graceful shutdown để hoàn tất/commit công việc đang xử lý khi có thể.
4. Không commit offset trước khi business transaction cần thiết đã hoàn tất.
5. Chấp nhận at-least-once redelivery khi crash và bảo vệ bằng idempotency.
6. Giữ key và partitioning strategy ổn định trong suốt rollout.

Một partition chỉ được gán cho một group member tại một thời điểm, nhưng trong thời gian rebalance có thể có khoảng dừng. Không thiết kế ứng dụng phụ thuộc vào cùng một instance luôn sở hữu một `orderId`.

### 10.1. Chạy ba instance trong môi trường thử nghiệm

Khởi chạy ba process với cùng cấu hình:

| Instance | Consumer concurrency | Group |
|---|---:|---|
| `orders-1` | 4 | `orders-processor` |
| `orders-2` | 4 | `orders-processor` |
| `orders-3` | 4 | `orders-processor` |

Topic có 12 partition. Tổng 12 consumer thread có thể nhận đủ partition. Kiểm tra log assignment để xác minh phân phối thực tế; không giả định mỗi instance luôn nhận đúng bốn partition vì assignment strategy và membership có thể phân bố khác.

## 11. Kiểm thử end-to-end

Test phải dùng broker Kafka thật hoặc môi trường tích hợp tương đương. Test Binder kiểm tra function/binding wiring nhưng không chứng minh partition assignment, consumer group, producer key, rebalance hay committed offset của broker.

### 11.1. Dữ liệu kiểm thử

Phát đồng thời:

- `ORD-A`: sequence 1 đến 100.
- `ORD-B`: sequence 1 đến 100.
- `ORD-C`: sequence 1 đến 100.
- Nhiều event của mỗi đơn được gửi nhanh để tạo tải.

Mỗi event có `eventId` duy nhất. Ghi nhận input fixture và expected sequence theo từng orderId.

### 11.2. Kiểm tra cùng key vào cùng partition

Dùng Kafka consumer kiểm tra metadata của record hoặc quan sát partition trong test harness:

1. Publish 100 event cho `ORD-A`.
2. Ghi lại partition của từng record.
3. Assert chỉ có một partition xuất hiện cho key `ORD-A`.
4. Lặp lại với `ORD-B` và `ORD-C`.
5. Assert sequence tăng dần theo offset trong partition của từng order.

Không assert rằng các order khác nhau phải luôn ở partition khác nhau. Hash collision là bình thường; điều cần thiết là cùng một order không bị phân tán.

### 11.3. Kiểm tra nhiều instance xử lý song song

Khởi động ba instance cùng group và bật log gồm:

- `orderId`.
- `sequence`.
- Kafka partition/offset.
- Consumer client/instance ID.
- Thời điểm bắt đầu và kết thúc xử lý.

Kết quả mong đợi:

- Các partition khác nhau có thể được xử lý đồng thời.
- Mỗi order có sequence được áp dụng theo 1, 2, 3…100.
- Không có hai instance cùng xử lý song song cùng partition trong cùng group.
- Một order có thể chuyển sang instance khác sau rebalance, nhưng sequence vẫn tiếp tục đúng.

### 11.4. Kiểm tra duplicate và idempotency

Gửi lại cùng eventId hai lần, kể cả khi producer nhận timeout không biết broker đã nhận hay chưa. Assert:

- Bảng `processed_events` chỉ có một record cho eventId.
- Trạng thái đơn chỉ tăng sequence một lần.
- Side effect nghiệp vụ không lặp.
- Metric duplicate tăng nếu ứng dụng có instrument riêng.

### 11.5. Kiểm tra sequence gap

Tạo một đơn có `lastSequence=2`, sau đó publish event sequence 4 mà không có sequence 3.

Assert:

- Service phát hiện expected=3, actual=4.
- Trạng thái đơn không nhảy sang sequence 4.
- Event không bị đánh dấu processed thành công.
- Partition/key được giữ hoặc event được parking theo đúng chiến lược đã chọn.
- Có log/metric/alert chứa orderId, sequence và partition/offset để điều tra.

Sau đó bổ sung/replay sequence 3 và 4 theo đúng thứ tự; assert trạng thái đạt sequence 4.

### 11.6. Kiểm tra rebalance giữa lúc có backlog

1. Publish một lượng event đủ lớn để tạo backlog.
2. Dừng một instance theo cách graceful.
3. Xác nhận partition được chuyển sang instance còn lại.
4. Tiếp tục publish event mới cho cùng các order.
5. Đối soát sequence và event ID trong DB.
6. Khởi động lại instance đã dừng và xác minh nó tham gia group mà không reset offset.

Lặp lại bằng cách kill process đột ngột khi handler đang xử lý. Một số event có thể được giao lại; kết quả nghiệp vụ vẫn phải đúng nhờ transaction DB và idempotency.

### 11.7. Ma trận kiểm thử

| Ca kiểm thử | Tình huống | Kết quả mong đợi |
|---|---|---|
| KEY-01 | 100 event cùng orderId | Tất cả cùng partition. |
| KEY-02 | Hai orderId khác nhau | Có thể xử lý song song trên partition khác nhau. |
| SEQ-01 | Sequence liên tục 1..N | Trạng thái tăng đúng thứ tự. |
| SEQ-02 | Thiếu sequence giữa luồng | Phát hiện gap, không áp dụng event sau. |
| DUP-01 | Gửi cùng eventId hai lần | Side effect chỉ một lần. |
| PROD-01 | Producer retry khi network chập chờn | Không đảo thứ tự trong giới hạn idempotent producer; duplicate vẫn được consumer bảo vệ. |
| CON-01 | Ba instance cùng group | Partition được chia giữa các member. |
| CON-02 | Một instance dừng | Rebalance, không mất event. |
| CON-03 | Một instance crash giữa xử lý | Redelivery được xử lý idempotent. |
| DLQ-01 | Poison event của một order | Không để event sau cùng order vượt qua gap. |
| PART-01 | Thay partition count | Test chứng minh remapping và yêu cầu migration. |
| LOAD-01 | Nhiều order cùng lúc | Throughput tăng mà sequence từng order vẫn đúng. |

## 12. Kiểm tra hot key và phân bố tải

Partitioning theo `orderId` giữ thứ tự nhưng có thể tạo hot partition nếu một order hoặc một nhóm key chiếm phần lớn traffic.

Ví dụ 90% message thuộc một order lớn. Order đó luôn vào một partition; 11 partition còn lại ít tải. Thêm consumer instance không giúp xử lý song song cùng order nếu strict ordering là yêu cầu.

Cần cân nhắc:

- Tối ưu xử lý cho key nóng.
- Giảm kích thước payload và chi phí DB/API.
- Tách nghiệp vụ thành các bước độc lập nhưng giữ sequence tại aggregate boundary.
- Tăng partition chỉ khi routing/migration vẫn giữ được thứ tự lịch sử.
- Đo skew theo partition và key group, không chỉ tổng throughput.

Không chia một `orderId` thành nhiều key chỉ để cân bằng tải nếu các event vẫn phụ thuộc thứ tự toàn đơn. Điều đó đổi yêu cầu nghiệp vụ thành mô hình đồng bộ phức tạp hơn.

## 13. Nếu dùng RabbitMQ

RabbitMQ queue thường giữ thứ tự enqueue, nhưng nhiều consumer, prefetch, redelivery và xử lý bất đồng bộ có thể làm thứ tự hoàn tất side effect khác thứ tự nhận.

### 13.1. Một consumer duy nhất cho queue

- Dùng một active consumer, concurrency 1.
- Đặt prefetch 1 nếu cần chỉ có một delivery chưa ACK tại một thời điểm.
- Xử lý đồng bộ và ACK sau khi DB transaction hoàn tất.
- Có thể dùng Single Active Consumer để có consumer standby khi active consumer mất.

Cách này đơn giản cho strict queue ordering nhưng giới hạn throughput của queue.

### 13.2. Chia theo key thành nhiều queue

Để xử lý nhiều đơn song song, route cùng `orderId` vào cùng queue/partition queue. Các queue khác nhau có thể được consumer song song. Routing phải ổn định theo key và số shard không được thay đổi tùy tiện nếu lịch sử còn đang được xử lý.

Với Rabbit binder, có thể dùng partitioned producer/consumer của Spring Cloud Stream nếu topology và binder configuration phù hợp. Phải xác minh queue/partition mapping thực tế và bảo đảm một partition queue chỉ có một consumer xử lý tuần tự nếu cần strict order.

Prefetch lớn hơn 1 có thể cải thiện throughput nhưng nhiều delivery chưa ACK cùng lúc làm tăng khả năng hoàn tất không theo thứ tự nếu ứng dụng xử lý song song. Retry/requeue cũng có thể đưa message cũ quay lại sau message mới. Vì vậy, không suy ra strict ordering chỉ từ việc queue là FIFO.

## 14. Nếu dùng Apache Pulsar

Pulsar có nhiều subscription type với semantics khác nhau:

| Subscription type | Đặc điểm | Phù hợp với yêu cầu |
|---|---|---|
| `Exclusive` | Một consumer hoạt động trên subscription. | Thứ tự đơn giản, throughput giới hạn. |
| `Failover` | Một consumer active, consumer khác standby. | Giữ mô hình tuần tự và có failover. |
| `Shared` | Nhiều consumer nhận message từ subscription. | Throughput cao; không bảo đảm thứ tự toàn cục hoặc theo key một cách mặc định. |
| `Key_Shared` | Message cùng key được phân phối tới cùng consumer theo cơ chế key-shared. | Xử lý song song theo key, giữ thứ tự trong phạm vi key khi producer/batching được cấu hình tương thích. |

Với nhiều instance và thứ tự theo `orderId`, `Key_Shared` là lựa chọn cần xem xét. Producer phải đặt message key là `orderId`. Khi bật batching, cần dùng key-based batching tương thích với Key_Shared; batch chứa nhiều key và được dispatch như một đơn vị có thể làm giảm tính chất phân phối theo key.

Consumer xử lý message cùng key phải tuần tự. Nếu một consumer nhận các key khác nhau, nó có thể xử lý song song giữa các key bằng cơ chế có kiểm soát, nhưng không chạy song song hai event của cùng key.

Không dùng `Shared` rồi giả định các message cùng order luôn hoàn tất theo thứ tự. Cũng cần kiểm tra ACK timeout, redelivery và dead-letter policy vì message bị giao lại có thể ảnh hưởng chuỗi xử lý.

## 15. Quan sát và vận hành

Log có cấu trúc nên ghi các trường:

- `eventId`, `orderId`, `sequence`, `eventType`.
- `topic`, `partition`, `offset` (Kafka) hoặc queue/subscription/message ID của broker tương ứng.
- Consumer group, instance ID và thời điểm bắt đầu/kết thúc.
- Kết quả `APPLIED`, `DUPLICATE`, `GAP`, `STALE`, `RETRY` hoặc `DLQ`.

Metrics nên dùng tag có cardinality hữu hạn:

| Metric | Tag phù hợp |
|---|---|
| `orders.events.processed` | binder, binding, outcome |
| `orders.events.sequence_gap` | binding, error_category |
| `orders.events.duplicate` | binding |
| `orders.consumer.lag` | topic, partition có giới hạn, group |
| `orders.partition.processing.time` | binding, outcome |

Không dùng `orderId`, `eventId`, `correlationId` làm metric label vì số giá trị có thể tăng theo từng đơn/event. Đưa các ID này vào log/trace để truy vết cụ thể.

Các cảnh báo quan trọng:

- Consumer lag tăng liên tục.
- Partition không có consumer assignment hoặc assignment thay đổi bất thường.
- Sequence gap xuất hiện.
- Redelivery/retry tăng đột biến.
- DLQ có message mới.
- Một partition có throughput hoặc lag khác biệt lớn so với các partition còn lại.
- Một order/key bị pending quá lâu.

## 16. Các lỗi thiết kế thường gặp

1. Dùng `eventId` làm Kafka key nên các event cùng order đi vào nhiều partition.
2. Dùng `orderId` làm key nhưng có nhiều producer gửi đồng thời mà không cấp sequence/serialize nguồn phát.
3. Cho rằng Kafka bảo đảm thứ tự giữa các partition.
4. Tăng partition count mà không xét key remapping.
5. Mỗi instance dùng một consumer group riêng khiến tất cả instance nhận cùng dữ liệu.
6. Tăng concurrency rồi dùng `@Async`/`parallelStream()` khiến side effect hoàn tất sai thứ tự.
7. Dùng retry topic hoặc DLQ rồi commit offset, để event sau của cùng order vượt qua event lỗi.
8. Chỉ dựa vào event timestamp để sắp xếp, bỏ qua sequence nghiệp vụ.
9. Không có unique constraint cho eventId nên duplicate vẫn cập nhật DB hai lần.
10. Commit offset trước khi business transaction hoàn tất.
11. Dùng Pulsar `Shared` khi cần Key_Shared ordering.
12. Dùng Rabbit prefetch cao và xử lý song song nhưng vẫn kỳ vọng FIFO completion.
13. Đưa orderId vào metric tag làm cardinality tăng theo số đơn.
14. Không kiểm thử rebalance, crash và replay.

## 17. Quy trình thực hiện bài lab

1. Tạo topic `orders.events` với 12 partition và xác nhận topic đã sẵn sàng.
2. Tạo producer output binding, đặt `orderId` vào header và cấu hình `message-key-expression`.
3. Cấu hình producer idempotence và reliability phù hợp.
4. Tạo function `processOrders` nhận từng `OrderEvent`.
5. Cấu hình consumer group cố định `orders-processor`, concurrency 4.
6. Khởi động ba instance; xác nhận tổng 12 consumer thread và partition assignment.
7. Phát 100 event liên tục cho mỗi orderId, kiểm tra tất cả cùng partition và sequence tăng.
8. Lưu eventId và lastSequence trong DB transaction để chống duplicate và phát hiện gap.
9. Gửi duplicate, đảo sequence và poison event; xác minh không phá trạng thái đơn.
10. Dừng/crash một instance khi có backlog; kiểm tra rebalance và redelivery.
11. Đo lag, throughput, processing latency và partition skew.
12. Thử thay partition count trên topic thử nghiệm riêng để quan sát key remapping; không thay topic của luồng đang chạy.
13. Ghi lại cấu hình, kết quả, event IDs và checkpoint để có thể tái lập.

### Checklist nghiệm thu

- [ ] `orderId` được dùng làm Kafka record key ở mọi producer path.
- [ ] Nguồn phát cấp sequence tăng dần và publish theo thứ tự cho từng order.
- [ ] Outbox/dispatcher không publish event sau trước event trước của cùng order.
- [ ] Topic partition count được quản lý và có kế hoạch migration.
- [ ] Mọi consumer instance dùng cùng group.
- [ ] Consumer concurrency không vượt quá khả năng partition và downstream.
- [ ] Handler xử lý đồng bộ theo partition hoặc có sequencer per-key.
- [ ] DB transaction cập nhật state và processed-event record cùng nhau.
- [ ] Sequence gap không bị bỏ qua âm thầm.
- [ ] Retry/DLQ không làm event sau cùng key vượt qua event chưa xử lý.
- [ ] Rebalance, graceful restart và crash đã được kiểm thử.
- [ ] Duplicate không tạo side effect lần thứ hai.
- [ ] Metrics không dùng orderId/eventId làm label.
- [ ] Có dashboard cho lag, partition skew, gap, duplicate và DLQ.

## Tài liệu tham khảo

- [Spring Cloud Stream – Kafka Binder](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-binder/index.html)
- [Spring Cloud Stream – Kafka Binder Configuration Options](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-binder/config-options.html)
- [Spring Kafka – Message Listener Containers and Offset Management](https://docs.spring.io/spring-kafka/reference/kafka/receiving-messages/message-listener-container.html)
- [Apache Kafka – Producer Configuration](https://kafka.apache.org/documentation/#producerconfigs)
- [Apache Kafka – Consumer Configuration](https://kafka.apache.org/documentation/#consumerconfigs)
- [RabbitMQ – Consumer Prefetch](https://www.rabbitmq.com/docs/consumer-prefetch)
- [RabbitMQ – Single Active Consumer](https://www.rabbitmq.com/docs/consumers#single-active-consumer)
- [Spring Cloud Stream – Rabbit Binder](https://docs.spring.io/spring-cloud-stream-binder-rabbit/docs/current/reference/html/)
- [Apache Pulsar – Messaging Concepts and Subscriptions](https://pulsar.apache.org/docs/concepts-messaging/)
- [Apache Pulsar – Key_Shared Subscription](https://pulsar.apache.org/docs/concepts-messaging/#key_shared)
- [Spring for Apache Pulsar – Message Consumption](https://docs.spring.io/spring-pulsar/reference/reference/pulsar/message-consumption.html)
