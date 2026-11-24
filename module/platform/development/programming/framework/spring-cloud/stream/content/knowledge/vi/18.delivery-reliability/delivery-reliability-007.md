# Xử lý sự kiện đến muộn, sai thứ tự và thiếu sự kiện

## Mục tiêu

Trong hệ thống xử lý sự kiện, thời điểm một sự kiện xảy ra, thời điểm producer gửi nó và thời điểm consumer nhận nó có thể khác nhau đáng kể. Một message có thể đến sau những message được tạo ra sau nó, đến sau khi một cửa sổ tổng hợp đã kết thúc, hoặc không xuất hiện ở consumer dù nghiệp vụ nguồn đã phát sinh. Những tình huống này thường được gọi là **sự kiện đến muộn**, **sự kiện sai thứ tự** và **sự kiện bị thiếu**.

Spring Cloud Stream cung cấp binding và binder để kết nối ứng dụng với Kafka, RabbitMQ hoặc Pulsar. Các abstraction này giúp tổ chức luồng xử lý, nhưng không tự bảo đảm thứ tự toàn cục, tự phát hiện mọi sự kiện bị mất hoặc tự sửa trạng thái nghiệp vụ khi message đến trễ. Ứng dụng cần xác định thứ tự có ý nghĩa ở phạm vi nào, nhận diện sự kiện bằng định danh ổn định và có quy trình phục hồi khi phát hiện khoảng trống.

Sau bài học, bạn có thể:

- Phân biệt event time, processing time và thời điểm broker nhận message.
- Nhận diện nguyên nhân khiến message đến muộn hoặc sai thứ tự.
- Thiết kế ordering theo aggregate/key thay vì giả định thứ tự toàn cục.
- Phát hiện gap bằng sequence number, event ID và đối soát dữ liệu.
- Chọn chính sách chấp nhận, trì hoãn, sửa lại hoặc cách ly sự kiện đến muộn.
- Dùng watermark và grace period khi xử lý cửa sổ thời gian với Kafka Streams.
- Kiểm thử và giám sát độ trễ, sự kiện trùng, sai thứ tự và thiếu sự kiện.

## 1. Ba vấn đề khác nhau

Các khái niệm thường bị gộp chung nhưng cần được phân biệt:

| Tình huống | Ý nghĩa | Ví dụ |
|---|---|---|
| Sự kiện đến muộn (late event) | Message được xử lý sau thời điểm nghiệp vụ hoặc sau mốc thời gian mà luồng xử lý mong đợi | Giao dịch xảy ra lúc 10:00 nhưng consumer nhận lúc 10:08 |
| Sự kiện sai thứ tự (out-of-order) | Consumer nhận các sự kiện theo thứ tự khác với thứ tự nghiệp vụ cần bảo toàn | Nhận `OrderShipped` trước `OrderPaid` |
| Sự kiện bị thiếu (missing event) | Một sự kiện được kỳ vọng nhưng chưa quan sát thấy hoặc không còn được tìm thấy trong luồng | Aggregate có sequence 10 rồi 12 nhưng chưa thấy 11 |

Một sự kiện có thể vừa đến muộn vừa sai thứ tự. Một sequence bị khuyết có thể chỉ là message đến chậm, nhưng cũng có thể là message bị mất, bị loại bỏ hoặc chưa từng được producer gửi thành công. Không thể kết luận message bị mất chỉ vì nó chưa xuất hiện trong vài giây; cần một SLA hoặc timeout phát hiện gap đã được định nghĩa.

### Event time, processing time và broker time

- **Event time / occurredAt:** thời điểm sự kiện xảy ra trong nghiệp vụ, do producer ghi nhận.
- **Processing time:** thời điểm consumer thực sự xử lý message.
- **Ingestion/record time:** thời điểm broker nhận hoặc ghi message, tùy broker và cấu hình timestamp.

Ví dụ: một thiết bị ghi nhận nhiệt độ lúc 10:00 khi đang mất mạng. Nó gửi dữ liệu lúc 10:07 và consumer xử lý lúc 10:07:01. Event time là 10:00; ingestion time gần 10:07; processing time là 10:07:01.

Nếu dùng processing time để tính báo cáo theo giờ nghiệp vụ, dữ liệu có thể bị đưa vào sai cửa sổ. Nếu dùng event time, hệ thống cần một chính sách cho message đến sau khi cửa sổ đã được xem là hoàn tất.

## 2. Vì sao message đến muộn hoặc sai thứ tự?

Các nguyên nhân thường gặp gồm:

- Nhiều producer phát sự kiện cho cùng một aggregate mà không có cơ chế tuần tự hóa.
- Producer retry sau khi không rõ broker đã nhận message hay chưa; lần gửi lại có thể đến sau một message mới hơn.
- Consumer xử lý song song, khiến thao tác hoàn tất theo thứ tự khác với thứ tự nhận.
- Retry hoặc redelivery làm một message cũ quay lại sau khi message mới hơn đã được xử lý.
- Rebalance, restart hoặc failover khiến consumer đọc lại dữ liệu chưa commit.
- Nhiều partition hoặc queue không có thứ tự chung.
- Mạng chập chờn, thiết bị offline hoặc batch upload tạo độ trễ lớn.
- Đồng hồ máy phát không đồng bộ hoặc producer ghi timestamp sai.
- Retention, cấu hình subscription hoặc lỗi producer khiến một message không còn được lưu/nhận như mong đợi.

Cần phân biệt thứ tự broker giao message với thứ tự nghiệp vụ. Broker có thể giao đúng thứ tự đã ghi trong một partition, nhưng hai producer vẫn có thể ghi sự kiện theo thứ tự nghiệp vụ sai. Ngược lại, broker có thể nhận đúng thứ tự nhưng consumer chạy xử lý bất đồng bộ khiến side effect hoàn tất không theo thứ tự đó.

## 3. Phạm vi bảo đảm thứ tự của từng broker

Spring Cloud Stream thống nhất cách khai báo function và binding, nhưng semantics ordering phụ thuộc broker và binder.

| Broker | Phạm vi thứ tự thường có | Nguyên nhân làm thứ tự quan sát thay đổi |
|---|---|---|
| Kafka | Trong một partition của topic | Nhiều partition không có thứ tự toàn cục; consumer xử lý song song; retry/replay và nhiều producer |
| RabbitMQ | Trong một queue theo thứ tự enqueue trong điều kiện thông thường | Nhiều consumer, prefetch, requeue, priority, redelivery và xử lý bất đồng bộ |
| Pulsar | Theo topic/partition và cơ chế key/subscription được chọn | Shared subscription, nhiều producer, redelivery và xử lý song song |

### Kafka

Kafka đảm bảo thứ tự record trong một partition. Nếu các sự kiện của cùng `orderId` được gửi với cùng record key và partition mapping ổn định, chúng có thể được ghi vào cùng partition. Consumer group đọc partition đó theo thứ tự log.

Tuy nhiên, Kafka không đảm bảo thứ tự giữa các partition. Nếu hai sự kiện cùng aggregate bị gửi đến hai partition khác nhau, consumer không có một thứ tự toàn cục để dựa vào. Cấu hình nhiều consumer hoặc xử lý bất đồng bộ trong ứng dụng cũng có thể làm side effect hoàn tất khác thứ tự record.

### RabbitMQ

RabbitMQ queue có thứ tự giao nhận theo topology và điều kiện vận hành, nhưng không nên xem FIFO là cam kết thứ tự nghiệp vụ tuyệt đối. Nhiều consumer cùng đọc queue có thể hoàn tất xử lý khác thứ tự. Message bị nack/requeue hoặc redelivery có thể xuất hiện lại ở vị trí khác. Priority queue cũng thay đổi thứ tự giao.

Nếu thứ tự theo aggregate quan trọng, cần thiết kế routing/queue và consumer concurrency phù hợp, đồng thời kiểm tra hành vi requeue. Một queue duy nhất với một consumer có thể đơn giản hóa thứ tự nhưng giới hạn throughput.

### Pulsar

Pulsar có topic thường hoặc partitioned topic, message key và nhiều subscription type. Subscription Shared tối ưu phân phối cho nhiều consumer nhưng không cung cấp thứ tự xử lý tổng thể. Key_Shared có thể phân phối message cùng key đến cùng consumer theo semantics của broker, giúp giữ locality theo key; cần kiểm tra cấu hình key-based batching và ordering theo phiên bản Pulsar. Failover và Exclusive có mô hình consumer active khác Shared.

Chọn subscription type theo yêu cầu ordering và throughput. Không suy ra rằng cùng một `group` trong Spring Cloud Stream sẽ có semantics giống nhau trên Kafka, RabbitMQ và Pulsar.

## 4. Thiết kế event envelope có thể phát hiện thứ tự

Để phát hiện sai thứ tự hoặc gap, message cần mang đủ thông tin. Một event envelope có thể gồm:

```java
public record OrderEvent(
        String eventId,
        String aggregateId,
        long sequence,
        String eventType,
        Instant occurredAt,
        Instant producedAt,
        int schemaVersion,
        OrderPayload payload
) {}
```

Ý nghĩa:

- `eventId`: định danh duy nhất, ổn định qua retry và replay.
- `aggregateId`: định danh thực thể cần bảo toàn thứ tự, ví dụ order ID.
- `sequence`: số thứ tự tăng đơn điệu trong phạm vi aggregate.
- `eventType`: loại sự kiện.
- `occurredAt`: thời điểm nghiệp vụ xảy ra.
- `producedAt`: thời điểm producer tạo/phát message.
- `schemaVersion`: phiên bản hợp đồng.
- `payload`: dữ liệu nghiệp vụ.

Sequence nên được cấp bởi nguồn có quyền quyết định thứ tự của aggregate. Nếu nhiều producer độc lập tự tăng sequence mà không phối hợp, chúng có thể tạo ra sequence trùng hoặc xung đột. Có thể cấp sequence trong cùng transaction cập nhật aggregate và ghi outbox để trạng thái nghiệp vụ và event order nhất quán.

Không dùng timestamp làm sequence duy nhất. Hai sự kiện có thể có cùng timestamp, đồng hồ có thể lệch và timestamp có thể bị ghi sai. Sequence hoặc version tăng đơn điệu thường phù hợp hơn để phát hiện gap trong một aggregate.

### Ví dụ producer ghi outbox cùng transaction

Một transaction nghiệp vụ có thể cập nhật aggregate, tăng version và ghi outbox:

```java
@Transactional
public void markOrderPaid(String orderId) {
    Order order = orderRepository.findForUpdate(orderId);
    order.markPaid();

    long sequence = order.nextEventSequence();
    orderRepository.save(order);

    outboxRepository.append(new OrderEvent(
            eventIdGenerator.next(),
            orderId,
            sequence,
            "order.paid",
            clock.instant(),
            clock.instant(),
            1,
            OrderPayload.from(order)
    ));
}
```

Ví dụ minh họa ranh giới transaction; cách cấp sequence phải phù hợp mô hình aggregate và schema database của ứng dụng. Outbox relay có thể phát lại cùng event khi gặp sự cố, vì vậy event ID phải được giữ nguyên qua các lần gửi.

## 5. Định tuyến theo key để giữ thứ tự trong phạm vi cần thiết

Nếu cần thứ tự theo aggregate, hãy chọn khóa partition phù hợp thay vì cố tạo thứ tự toàn cục cho toàn bộ topic.

Với Kafka binder, producer binding có thể dùng `partitionKeyExpression`:

```yaml
spring:
  cloud:
    function:
      definition: orderEvents
    stream:
      bindings:
        orderEvents-out-0:
          destination: orders.events
          content-type: application/json
          producer:
            partition-key-expression: payload.aggregateId
            partition-count: 12
```

Các event có cùng `aggregateId` được định tuyến theo cùng key trong cùng partition topology. Consumer group đọc mỗi partition theo thứ tự record. `partition-count` cần khớp với topic đã provision và cấu hình binder; thay đổi số partition có thể làm mapping của key thay đổi.

Đối với RabbitMQ, routing key và queue topology có thể được thiết kế để cùng aggregate đi qua một luồng xử lý phù hợp. Cần hạn chế concurrency nếu yêu cầu thứ tự nghiêm ngặt; requeue/redelivery vẫn có thể ảnh hưởng thứ tự quan sát.

Đối với Pulsar, message key và Key_Shared subscription có thể giúp các message cùng key được xử lý bởi cùng consumer trong subscription. Kiểm tra key-based batching và subscription configuration để xác nhận ordering mong muốn.

### Key không tự bảo đảm side effect hoàn tất theo thứ tự

Ngay cả khi record cùng key đi vào một partition, code consumer có thể gọi `flatMap` để xử lý nhiều event đồng thời. Event sequence 12 có thể cập nhật database trước sequence 11. Nếu cần tuần tự hóa side effect, dùng xử lý tuần tự theo partition/key hoặc kiểm tra sequence trong transaction.

Với Reactor, `concatMap` tuần tự hóa publisher con:

```java
@Bean
Function<Flux<OrderEvent>, Mono<Void>> applyOrderEvents(
        OrderEventService service) {
    return events -> events
            .concatMap(service::apply)
            .then();
}
```

`flatMap` có thể tăng concurrency nhưng không bảo đảm thứ tự hoàn tất. Chọn operator dựa trên yêu cầu nghiệp vụ và binder reactive đang sử dụng.

## 6. Xử lý sự kiện sai thứ tự bằng sequence number

Consumer có thể theo dõi sequence cuối cùng đã áp dụng cho từng aggregate.

Giả sử aggregate `order-42` đã áp dụng sequence 10:

- Nhận sequence 11: đúng thứ tự, có thể áp dụng.
- Nhận sequence 10: sự kiện cũ hoặc trùng; cần kiểm tra event ID/trạng thái đã xử lý.
- Nhận sequence 12: thiếu sequence 11; không nên áp dụng mù quáng nếu sequence 11 có ảnh hưởng đến kết quả.
- Nhận sequence 11 sau khi đã áp dụng sequence 12: có thể là late event; cần xác định chính sách sửa trạng thái hoặc bỏ qua.

Một quyết định cơ bản:

```text
incoming.sequence == lastSequence + 1  -> apply
incoming.sequence <= lastSequence      -> duplicate/stale; deduplicate or reconcile
incoming.sequence > lastSequence + 1   -> gap; buffer and recover missing sequence
```

Đây là quy tắc theo aggregate. Một luồng khác có thể cho phép bỏ qua sequence nếu các sự kiện độc lập; đừng áp dụng kiểm tra gap cứng cho mọi loại event.

### Inbox và pending-event store

Một consumer có thể dùng hai vùng lưu trữ:

- **Inbox/processed event store:** ghi nhận event ID đã nhận để chống xử lý lặp.
- **Pending event store:** giữ sự kiện đến trước khi sequence trước đó được xử lý.

Mô hình dữ liệu minh họa:

```sql
CREATE TABLE processed_event (
    event_id VARCHAR(120) PRIMARY KEY,
    aggregate_id VARCHAR(120) NOT NULL,
    sequence_no BIGINT NOT NULL,
    received_at TIMESTAMP NOT NULL
);

CREATE TABLE pending_order_event (
    aggregate_id VARCHAR(120) NOT NULL,
    sequence_no BIGINT NOT NULL,
    event_id VARCHAR(120) NOT NULL UNIQUE,
    payload JSON NOT NULL,
    received_at TIMESTAMP NOT NULL,
    PRIMARY KEY (aggregate_id, sequence_no)
);
```

Khi nhận sequence 12 trong khi sequence hiện tại là 10, consumer có thể lưu sequence 12 vào pending store trong transaction rồi hoàn tất việc nhận message. Một tiến trình phục hồi sẽ tìm sequence 11 từ nguồn sự thật hoặc chờ nó đến. Khi sequence 11 được áp dụng, tiến trình có thể tiếp tục áp dụng sequence 12.

Nếu message được lưu bền vững vào pending store, broker có thể được xác nhận vì trách nhiệm phục hồi đã được chuyển sang kho nội bộ. Nếu chưa có nơi lưu bền vững, không nên ACCEPT message rồi chỉ giữ trong RAM; process restart sẽ làm mất sự kiện đã xác nhận.

### Cập nhật transaction và chống race condition

Việc đọc sequence cuối cùng rồi cập nhật phải được bảo vệ bằng transaction, khóa phù hợp hoặc optimistic locking. Nếu hai consumer cùng xử lý event cho một aggregate, cả hai không được đồng thời áp dụng sequence trên cùng một trạng thái cũ.

Có thể dùng điều kiện cập nhật version:

```sql
UPDATE orders
SET status = :new_status,
    version = :incoming_sequence
WHERE order_id = :order_id
  AND version = :incoming_sequence - 1;
```

Nếu số hàng cập nhật là 0, trạng thái hiện tại đã thay đổi hoặc sequence không liền kề. Ứng dụng cần đọc lại và phân loại duplicate, stale event hoặc gap. Không coi mọi lần update 0 hàng là lỗi giống nhau.

## 7. Xử lý sự kiện đến muộn theo event time

Một message có sequence hợp lệ vẫn có thể đến muộn theo thời gian nghiệp vụ. Ví dụ, sự kiện giao dịch lúc 10:00 chỉ đến lúc 10:12. Cách xử lý phụ thuộc nghiệp vụ:

- **Chấp nhận và cập nhật lại:** nếu báo cáo có thể được hiệu chỉnh, cập nhật aggregate/window đã tính.
- **Tạo correction event:** giữ kết quả cũ và phát một sự kiện điều chỉnh có audit trail.
- **Đưa vào late-event stream:** cách ly để xử lý riêng nếu cửa sổ chính đã đóng.
- **Từ chối theo SLA:** nếu nghiệp vụ không chấp nhận dữ liệu sau một hạn chót, ghi nhận lý do và cho phép đối soát.
- **Chờ lâu hơn trước khi chốt:** tăng thời gian chờ/watermark nếu độ trễ là đặc tính bình thường của nguồn.

Không nên tự động bỏ mọi event có timestamp cũ hơn thời điểm hiện tại. Một event đến muộn có thể chứa thông tin quan trọng và là nguồn sự thật hợp lệ.

### Event time và clock skew

Timestamp do producer tạo có thể sai vì đồng hồ thiết bị lệch, timezone không rõ hoặc timestamp bị ghi tại thời điểm gửi thay vì thời điểm xảy ra. Trước khi áp dụng chính sách late event, hãy xác định:

- Ai là nguồn tin cậy tạo `occurredAt`.
- Timestamp có timezone/UTC hay không.
- Độ lệch đồng hồ tối đa được chấp nhận.
- Có cần giữ cả `occurredAt` và `producedAt` để chẩn đoán không.
- Sự kiện có sequence/version để xác minh thứ tự độc lập với timestamp không.

## 8. Watermark và grace period trong Kafka Streams

Khi xử lý cửa sổ theo event time, hệ thống cần một mốc để quyết định khi nào có thể xem một cửa sổ gần như hoàn tất. **Watermark** biểu diễn tiến độ event time mà hệ thống tin rằng phần lớn sự kiện trước mốc đó đã đến. Watermark không chứng minh tuyệt đối rằng sẽ không còn event cũ hơn.

Kafka Streams sử dụng timestamp của record và grace period của window để quyết định một record đến muộn còn được phép cập nhật kết quả cửa sổ hay không. Có thể cấu hình cửa sổ với grace period bằng DSL:

```java
KStream<String, PaymentEvent> payments = ...;

KTable<Windowed<String>, Long> countByAccount = payments
        .groupByKey()
        .windowedBy(
                TimeWindows.ofSizeAndGrace(
                        Duration.ofMinutes(5),
                        Duration.ofMinutes(2)
                )
        )
        .count();
```

Ví dụ: cửa sổ dài 5 phút và grace 2 phút cho phép record đến muộn trong khoảng grace theo semantics event-time của Kafka Streams. Record đến sau khi cửa sổ đã đóng theo stream-time/grace policy sẽ không cập nhật kết quả cửa sổ đó. Chính sách timestamp extractor quyết định timestamp record mà Kafka Streams sử dụng.

Cần phân biệt:

- Kích thước window xác định khoảng event time được gom nhóm.
- Grace period xác định khoảng chấp nhận record đến muộn sau thời điểm kết thúc window theo stream-time.
- Stream-time được tiến triển bởi timestamp record mà topology quan sát; nó không đơn giản là đồng hồ wall-clock.
- Record đến sau grace có thể bị bỏ qua đối với phép tính window; Kafka Streams không tự động gửi nó vào DLQ nếu ứng dụng chưa thiết kế đường xử lý riêng.

Nếu late event cần được điều tra hoặc áp dụng thành correction, hãy thiết kế processor/branch hoặc luồng phụ phù hợp để lưu và quan sát nó. Kiểm tra API Kafka Streams và Kafka Streams binder của đúng phiên bản vì cách cấu hình timestamp extractor, window và error handling có thể khác.

## 9. Phát hiện sự kiện bị thiếu

Một message chưa xuất hiện có thể chỉ đang bị trễ. Để phát hiện missing event, cần một tín hiệu kỳ vọng có thể kiểm chứng.

### Sequence gap

Nếu mỗi aggregate có sequence tăng liên tục, nhận sequence 15 sau sequence 13 cho thấy đang thiếu sequence 14. Consumer có thể:

1. Ghi nhận gap với aggregate ID và sequence bị thiếu.
2. Đặt thời hạn chờ dựa trên SLA.
3. Tìm event bị thiếu trong broker/source of truth hoặc yêu cầu producer replay.
4. Giữ event đến sau trong pending store nếu thứ tự cần thiết.
5. Phát cảnh báo khi gap vượt thời hạn.
6. Tiếp tục xử lý sau khi gap được khôi phục hoặc có quyết định nghiệp vụ.

### Reconciliation với nguồn sự thật

Nếu producer không cung cấp sequence, consumer khó chứng minh một sự kiện cụ thể đã bị mất. Có thể đối soát định kỳ với nguồn dữ liệu chuẩn:

- So sánh số lượng đơn hàng đã phát với số lượng sự kiện consumer ghi nhận.
- So sánh trạng thái aggregate giữa database nguồn và read model.
- Kiểm tra outbox record chưa được publish.
- Đối chiếu batch ID hoặc high-watermark giữa các hệ thống.
- Kiểm tra event ID trong kho lưu trữ/replay log.

Consumer lag chỉ cho biết consumer đang chậm so với log/queue; nó không chứng minh một event nghiệp vụ bị mất. Tương tự, số lượng message bằng nhau không chứng minh cùng một tập event đã được xử lý; nên đối chiếu theo event ID hoặc sequence.

### Heartbeat và expected events

Một số nguồn phát heartbeat hoặc watermark định kỳ. Nếu heartbeat không đến đúng hạn, hệ thống có thể phát hiện nguồn im lặng hoặc luồng bị gián đoạn. Đây là phát hiện bất thường ở cấp luồng, không nhất thiết xác định message cụ thể nào bị thiếu. Kết hợp heartbeat với sequence và reconciliation để có bằng chứng đầy đủ hơn.

## 10. Phục hồi message thiếu hoặc đến muộn

Khi phát hiện gap, không nên tự tạo một event nghiệp vụ giả chỉ để lấp số sequence. Cần khôi phục từ nguồn đáng tin cậy:

1. Tìm event theo event ID hoặc aggregate sequence trong outbox, event store hoặc log nguồn.
2. Xác minh event chưa được áp dụng ở consumer.
3. Replay giữ nguyên event ID, aggregate ID và sequence gốc.
4. Đảm bảo consumer deduplicate theo event ID.
5. Xử lý lại các pending event sau khi gap được lấp.
6. Đối soát trạng thái cuối cùng của aggregate.
7. Ghi audit trail về replay và kết quả.

Nếu không thể lấy lại event gốc, nghiệp vụ có thể cần snapshot/rebuild read model hoặc phát một correction event được định nghĩa rõ. Không giả vờ rằng correction là event gốc; giữ quan hệ causation và lịch sử thay đổi.

### Replay và offset

Với Kafka, có thể replay bằng cách đọc lại offset hoặc phát lại event từ event store/outbox sang topic replay. Việc reset offset của consumer group ảnh hưởng toàn bộ partition/group và cần quy trình vận hành cẩn thận. Không reset offset production chỉ để thử một message mà chưa đánh giá tác động đến tất cả record tiếp theo.

Với RabbitMQ, replay có thể được thực hiện từ DLQ hoặc kho lưu trữ bằng cách publish lại message vào exchange/queue phù hợp. Với Pulsar, có thể dùng subscription cursor, seek hoặc phát lại từ topic lưu trữ theo khả năng client/binder. Các thao tác cụ thể cần kiểm tra quyền và semantics của broker.

## 11. Thiết kế consumer chịu được late, duplicate và out-of-order

Một consumer bền vững thường phối hợp các cơ chế sau:

- **Idempotency:** event ID ổn định và inbox/unique constraint để cùng message không tạo side effect lặp.
- **Sequence validation:** kiểm tra version/sequence theo aggregate khi thứ tự là yêu cầu nghiệp vụ.
- **Pending gap store:** lưu bền vững message đến trước khi sequence trước đó có mặt.
- **Late-event policy:** xác định event cũ được chấp nhận, sửa kết quả, cách ly hay từ chối.
- **Reconciliation:** đối soát định kỳ với nguồn sự thật để tìm missing event.
- **Outbox ở producer:** ghi thay đổi nghiệp vụ và event trong cùng transaction để giảm nguy cơ phát thiếu.
- **Retry/DLQ:** phân biệt lỗi tạm thời, poison message và gap cần chờ/recover.
- **Bounded state:** giới hạn số pending event, thời gian chờ và dung lượng reorder buffer.

Không phải mọi luồng cần tất cả cơ chế. Ví dụ telemetry có thể chấp nhận mất mẫu và tổng hợp theo event time; thanh toán hoặc trạng thái đơn hàng thường cần event ID, sequence, idempotency và reconciliation chặt chẽ hơn.

## 12. Ví dụ chiến lược xử lý theo aggregate

Một service có thể áp dụng chính sách:

```java
@Transactional
public void accept(OrderEvent event) {
    if (inboxRepository.exists(event.eventId())) {
        return; // Duplicate đã được xử lý.
    }

    long current = orderRepository.currentSequence(event.aggregateId());
    long expected = current + 1;

    if (event.sequence() > expected) {
        pendingRepository.storeIfAbsent(event);
        inboxRepository.markPending(event.eventId());
        return; // Đã lưu bền vững để phục hồi gap.
    }

    if (event.sequence() < expected) {
        inboxRepository.markStale(event.eventId());
        return; // Event cũ; cần policy đối soát nếu chưa biết đã áp dụng chưa.
    }

    applyAndAdvance(event);
    drainNextPendingEvents(event.aggregateId());
}
```

Đây là pseudocode minh họa. Triển khai thực tế cần bảo vệ cập nhật sequence bằng transaction/lock hoặc optimistic concurrency, và phân biệt event cũ đã áp dụng với event chưa từng được ghi nhận. Nếu sequence nhỏ hơn expected nhưng event ID chưa có trong inbox, không được tự động bỏ qua mà không xác minh; có thể là event hợp lệ đến muộn nhưng aggregate đã được cập nhật bằng snapshot hoặc một luồng khác.

Nếu event được lưu vào pending store, việc ghi inbox/pending phải cùng transaction để không tạo trạng thái đã nhận nhưng không còn payload. Khi gap được lấp, worker phục hồi đọc pending theo sequence, áp dụng tuần tự và đánh dấu trạng thái. Giới hạn pending age và số lượng để một aggregate lỗi không làm đầy database.

## 13. Quan sát và cảnh báo trong production

Nên theo dõi các metric:

| Metric | Ý nghĩa | Khi cần cảnh báo |
|---|---|---|
| Event-time lag | Khoảng cách giữa thời điểm hiện tại/processing time và event time | Tăng đột biến hoặc vượt SLA |
| Late-event count/rate | Số lượng/tỷ lệ event đến sau mốc mong đợi | Vượt ngưỡng nghiệp vụ |
| Out-of-order count | Số event có sequence lớn hơn expected hoặc thứ tự không phù hợp | Tăng theo aggregate/partition |
| Missing-sequence gap | Số gap chưa được lấp | Gap tồn tại quá timeout |
| Pending-event age/depth | Tuổi và số lượng event đang chờ gap | Tăng liên tục hoặc vượt dung lượng |
| Duplicate/stale rate | Event ID đã thấy hoặc sequence cũ | Tăng bất thường sau retry/replay |
| Reconciliation mismatch | Chênh lệch giữa source of truth và consumer state | Có mismatch chưa giải quyết |
| Consumer lag | Tiến độ consumer so với broker | Vượt SLA xử lý, nhưng không đồng nghĩa missing event |

Log nên có event ID, aggregate ID, sequence, occurredAt, producedAt, destination, partition/offset hoặc message ID nếu có. Tránh log toàn bộ payload chứa dữ liệu nhạy cảm.

Khi cảnh báo, cung cấp đủ thông tin để truy vết: aggregate nào, sequence nào đang thiếu, event gần nhất đã áp dụng, event-time lag và nơi tìm lại event gốc. Một cảnh báo chung "consumer chậm" không đủ để quyết định replay hoặc sửa dữ liệu.

## 14. Kiểm thử late, out-of-order và missing events

Kiểm thử cần tạo ra thứ tự cụ thể, không phụ thuộc timing ngẫu nhiên.

### Unit test cho sequence và idempotency

Tạo chuỗi sự kiện có sequence 10, 12, 11 và xác minh:

- 10 được áp dụng.
- 12 được lưu pending vì thiếu 11.
- 11 được áp dụng rồi 12 được drain theo thứ tự.
- Gửi lại event ID của 11 không tạo side effect lặp.
- Sequence cũ không được áp dụng lại ngoài policy.
- Gap không được lấp trong thời hạn thì phát cảnh báo hoặc yêu cầu reconciliation.

### Test event time và window

Với Kafka Streams, kiểm tra:

- Timestamp extractor lấy đúng event time.
- Event nằm trong cửa sổ được tính đúng.
- Event đến trong grace period có thể cập nhật kết quả theo semantics window.
- Event đến sau grace được xử lý theo chính sách late-event đã thiết kế.
- Thay đổi watermark/stream-time không làm test phụ thuộc đồng hồ wall-clock.

### Integration test với binder/broker

- Kafka: gửi record cùng key, kiểm tra partition và thứ tự; restart/rebalance và quan sát duplicate/replay; kiểm tra offset và window grace.
- RabbitMQ: kiểm tra nhiều consumer, prefetch, nack/requeue và thứ tự redelivery trên queue.
- Pulsar: kiểm tra Key_Shared/Shared subscription, key ordering và redelivery theo policy.
- Kiểm tra producer outbox không bỏ sót event khi database commit hoặc broker publish thất bại.
- Kiểm tra reconciliation và replay giữ nguyên event ID/sequence.

Test Binder hữu ích cho wiring và function logic nhưng không thay thế broker integration test về partition, queue ordering, subscription type, redelivery và cursor.

## 15. Quy trình xử lý một gap trong production

Khi hệ thống phát hiện aggregate có sequence 20 nhưng chưa có 19:

1. Ghi gap record gồm aggregate ID, expected sequence, observed sequence và thời điểm phát hiện.
2. Kiểm tra message 19 có đang chờ trong broker, retry queue, DLQ hoặc pending store không.
3. Tra cứu outbox/event store của producer để xác định event 19 đã được tạo và publish chưa.
4. Nếu có event gốc, replay giữ nguyên event ID và sequence vào luồng recovery được kiểm soát.
5. Nếu không có event gốc, đối soát trạng thái aggregate với nguồn sự thật và quyết định snapshot/correction theo nghiệp vụ.
6. Khi sequence 19 được xử lý, drain pending event 20 và các event tiếp theo theo thứ tự.
7. Đóng gap record, ghi audit trail và kiểm tra trạng thái cuối cùng.
8. Nếu gap không thể khôi phục, chuyển cho owner nghiệp vụ xử lý thay vì tự tạo dữ liệu giả.

Không replay toàn bộ topic hoặc reset toàn consumer group chỉ vì một aggregate có gap. Khoanh vùng theo event ID/aggregate/partition và chọn phương pháp recovery ít ảnh hưởng nhất.

## Kết luận

Sự kiện đến muộn liên quan đến event time và thời điểm xử lý; sự kiện sai thứ tự liên quan đến thứ tự nhận so với thứ tự nghiệp vụ; sự kiện bị thiếu cần được phát hiện bằng sequence, tín hiệu kỳ vọng hoặc đối soát với nguồn sự thật. Kafka giữ thứ tự trong partition, RabbitMQ phụ thuộc queue và cách consumer xử lý, còn Pulsar phụ thuộc partition, key và subscription type.

Trong Spring Cloud Stream, hãy chọn key theo aggregate cần giữ thứ tự, dùng event ID để idempotency và sequence để phát hiện gap. Với xử lý theo cửa sổ, xác định timestamp, watermark và grace period; với nghiệp vụ cần phục hồi, lưu pending event, dùng outbox và reconciliation. Kiểm thử các chuỗi đến trễ/sai thứ tự có chủ đích và xác minh behavior trên đúng binder/broker trước khi cam kết SLA.

