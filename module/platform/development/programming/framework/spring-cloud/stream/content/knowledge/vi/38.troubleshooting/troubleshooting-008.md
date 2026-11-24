# Thông điệp lặp lại, sai thứ tự hoặc dồn vào một partition

## Mục tiêu

Trong hệ thống xử lý sự kiện bằng **Spring Cloud Stream**, cùng một sự kiện có thể được nhận nhiều lần, sự kiện cập nhật mới có thể được xử lý trước sự kiện cũ, hoặc phần lớn tải có thể đổ vào một Kafka partition trong khi các consumer khác gần như rảnh. Ba triệu chứng này thường liên quan đến **delivery semantics, khóa phân vùng, concurrency và thời điểm ACK/commit**, nhưng không có cùng nguyên nhân hay cách sửa.

Một ứng dụng có `Supplier` phát sự kiện, `Function` biến đổi dữ liệu và `Consumer` cập nhật database có thể gặp tất cả ba sự cố. Kafka, RabbitMQ và Pulsar đều hỗ trợ giao nhận và retry, song khái niệm partition, consumer group, queue và subscription có những bảo đảm khác nhau. Khi chẩn đoán, phải tìm được điểm xảy ra lặp, đảo thứ tự hoặc nghẽn; không thể chữa mọi trường hợp bằng tăng `concurrency`, đổi `group` hoặc xóa backlog.

Bài học thuộc chương **Chẩn đoán sự cố** của module **SPRING_CLOUD_STREAM**. Nội dung hướng dẫn cách xác minh dấu hiệu, chọn khóa ổn định, giữ xử lý idempotent, đánh giá ordering theo key, nhận diện hot partition, và kiểm thử retry/redelivery trước khi điều chỉnh cấu hình triển khai.

Sau bài học, bạn có thể:

- Phân biệt duplicate record, redelivery và duplicate side effect nghiệp vụ.
- Đọc timeline của producer, broker, consumer và ACK/offset để tìm điểm phát sinh duplicate.
- Giải thích giới hạn ordering của Kafka theo partition, RabbitMQ theo queue và Pulsar theo subscription type.
- Sử dụng event ID, aggregate ID, sequence/version để phát hiện và kiểm soát sự kiện lặp hoặc cũ.
- Áp dụng mẫu inbox/idempotent consumer với database transaction.
- Kiểm tra key/partition assignment và xác định hot key hoặc hot partition từ metrics.
- Điều chỉnh `concurrency`, prefetch, consumer group và partitioning mà không phá yêu cầu ordering.
- Phân biệt Kafka Streams repartition, state store và event-time late arrival.
- Thực hiện broker integration test cho redelivery, out-of-order và partition skew.
- Lập runbook, chọn biện pháp giảm tải và rollback an toàn.

## 1. Ba triệu chứng dễ bị nhầm

| Triệu chứng | Quan sát | Có nhất thiết là broker lỗi? | Câu hỏi đầu tiên |
|---|---|---|---|
| **Message lặp** | Cùng event ID xuất hiện ở handler hai lần | Không | Producer gửi trùng hay broker giao lại? |
| **Sai thứ tự** | Version 12 được xử lý trước version 11 | Không | Thứ tự trong cùng partition hay thứ tự hoàn tất handler? |
| **Dồn một partition** | Partition 3 có lưu lượng/lag cao, partition khác thấp | Không | Key distribution có lệch hoặc một key quá nóng? |

Ví dụ luồng sự kiện theo đơn hàng:

~~~text
Producer (theo nghiệp vụ):
  O-21 / version=1 / CREATED
  O-21 / version=2 / PAID
  O-21 / version=3 / SHIPPED

Consumer quan sát:
  O-21 / version=1 / CREATED
  O-21 / version=2 / PAID
  O-21 / version=2 / PAID      <-- duplicate
  O-21 / version=3 / SHIPPED
~~~

Một biến thể khác:

~~~text
Consumer log ghi thời điểm hoàn tất:
  O-21 / version=3 / SHIPPED
  O-21 / version=2 / PAID     <-- processing completion out of order
~~~

Điều này chưa chứng minh broker đã lưu record ngược thứ tự. Có thể version 2 được nhận trước nhưng xử lý chậm; version 3 hoàn tất trước do ứng dụng chạy tác vụ bất đồng bộ.

Dồn partition lại là vấn đề phân phối tải, ví dụ phần lớn order events có cùng key `customerId="VIP"` nên chúng luôn được định tuyến vào một partition.

**Không bắt đầu bằng cách đặt lại offset hoặc tăng số partition.** Trước hết, ghi lại event identity, key, partition, offset, thời điểm và kết quả xử lý.

## 2. Mô hình quan sát: event identity, delivery và side effect

Một event cần được phân biệt với lần giao nhận (delivery attempt).

- **Event identity:** `eventId` được tạo tại nguồn nghiệp vụ, ổn định qua retry/replay.
- **Aggregate identity:** `orderId` hoặc `accountId` để nhóm sự kiện cần thứ tự.
- **Sequence/version:** số tăng đơn điệu theo aggregate để biết cập nhật nào mới hơn.
- **Delivery metadata:** topic, partition, offset của Kafka; message ID và delivery/redelivery information của broker tương ứng.
- **Processing attempt:** số lần handler thực sự chạy.
- **Side effect:** cập nhật database, gọi API hoặc phát output.

Một bản ghi log có cấu trúc:

~~~json
{
  "eventId": "evt-702",
  "aggregateId": "order-21",
  "aggregateVersion": 12,
  "binding": "processOrders-in-0",
  "group": "order-projection",
  "broker": "kafka",
  "topic": "orders.events",
  "partition": 3,
  "offset": 481920,
  "attempt": 2,
  "outcome": "ALREADY_PROCESSED"
}
~~~

`eventId`, `aggregateId` và `aggregateVersion` là fields hoặc headers do ứng dụng định nghĩa; Kafka không tự cung cấp business identity. Các thông tin `partition`, `offset` và delivery headers có tên cụ thể tùy binder/version. Trong Spring Kafka, các hằng `KafkaHeaders.RECEIVED_TOPIC`, `KafkaHeaders.RECEIVED_PARTITION` và `KafkaHeaders.OFFSET` thường hỗ trợ quan sát dữ liệu nhận; hãy xác minh header mapping ở release đang dùng.

### Vì sao chỉ nhìn payload giống nhau là chưa đủ?

Hai đơn hàng có nội dung bằng nhau có thể là hai event hợp lệ. Ngược lại, cùng `eventId` nhưng khác body là lỗi contract hoặc nguồn phát không nhất quán. Không deduplicate bằng hash toàn bộ payload nếu event ID là định danh được bảo đảm bởi producer.

| Dữ kiện | Giải thích có thể |
|---|---|
| Cùng event ID, cùng topic/partition/offset | Khả năng cao là redelivery hoặc handler được gọi lại cho cùng broker record |
| Cùng event ID, offset khác nhau | Producer đã publish hai record hoặc replay/forward tạo record mới |
| Khác event ID, cùng aggregate/version | Producer tạo lại business event bằng ID khác; cần xét aggregate-version contract |
| Offset tăng đúng nhưng DB log đảo thứ tự | Concurrency, asynchronous processing hoặc side effect completion |
| Partition lag tăng bất thường | Hot partition hoặc consumer của partition xử lý chậm |

Một offset chỉ định vị record trong **một Kafka partition**. Nó không phải số thứ tự toàn topic hoặc toàn hệ thống.

## 3. Message lặp: vì sao broker có thể giao lại?

Spring Cloud Stream không mặc định cho phép suy luận rằng mỗi business event chỉ chạy handler đúng một lần. Mô hình **at-least-once** thường dẫn đến khả năng duplicate khi có sự cố giữa xử lý và acknowledgment.

Timeline phổ biến:

~~~mermaid
sequenceDiagram
    participant K as Kafka / broker
    participant C as Consumer
    participant D as Database
    K->>C: Deliver event evt-702
    C->>D: UPDATE thành công
    D-->>C: Commit OK
    Note over C,K: Process chết trước khi ACK/offset commit
    K->>C: Redeliver evt-702
    C->>D: UPDATE lần nữa nếu không idempotent
~~~

Các nguyên nhân thường gặp:

1. Handler hoàn tất side effect nhưng process chết trước ACK/commit.
2. ACK hoặc offset commit thất bại/không kịp hoàn tất.
3. Consumer rebalance hoặc mất connection, partition/queue được giao lại.
4. Handler ném exception khiến binder/container retry hoặc broker redeliver.
5. Producer retry sau khi không chắc broker đã nhận thành công.
6. Outbox publisher gửi lại event sau lỗi ở bước đánh dấu đã phát.
7. Replay từ DLT, reset offset hoặc dùng consumer group/applicationId mới.
8. Một event đi qua nhiều function/binding và được publish hai lần do routing sai.
9. Autoscaling/rolling deployment hoặc health restart làm tăng các cửa sổ in-flight chưa được xác nhận.

Không thể kết luận nguyên nhân chỉ từ việc handler log hai lần. Hãy so sánh `eventId`, Kafka topic/partition/offset hoặc broker message ID, và dấu mốc commit của dữ liệu nghiệp vụ.

### Duplicate delivery khác duplicate side effect

Duplicate delivery không nhất thiết phải làm tăng số lần ghi nghiệp vụ. Một consumer idempotent có thể nhận lại event nhưng trả kết quả `ALREADY_PROCESSED`, giữ database không đổi. Mục tiêu không phải che mọi duplicate khỏi log, mà **biến xử lý lặp thành an toàn**.

## 4. Xử lý idempotent bằng inbox cùng DB transaction

Một mẫu phổ biến là lưu khóa `(consumer_name, event_id)` trong bảng inbox có unique constraint. Consumer chỉ chạy side effect nếu event ID chưa được xử lý cho logical consumer đó.

Ví dụ PostgreSQL:

~~~sql
CREATE TABLE processed_events (
    consumer_name VARCHAR(100) NOT NULL,
    event_id VARCHAR(120) NOT NULL,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (consumer_name, event_id)
);
~~~

Trong Spring service:

~~~java
@Service
public class OrderProjectionService {
    private final JdbcTemplate jdbc;

    public OrderProjectionService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public void apply(OrderPaid event) {
        int inserted = jdbc.update("""
            INSERT INTO processed_events (consumer_name, event_id)
            VALUES (?, ?)
            ON CONFLICT DO NOTHING
            """,
            "order-projection",
            event.eventId()
        );

        if (inserted == 0) {
            return; // Đã commit sự kiện này trước đó
        }

        int updated = jdbc.update("""
            UPDATE order_projection
               SET paid_amount_minor = paid_amount_minor + ?
             WHERE order_id = ?
            """,
            event.amountMinor(),
            event.orderId()
        );
        if (updated != 1) {
            throw new IllegalStateException(
                    "Expected one order projection for " + event.orderId()
            );
        }
    }
}
~~~

Function binding:

~~~java
@Bean
Consumer<OrderPaid> projectPaidOrders(OrderProjectionService service) {
    return service::apply;
}
~~~

**Điều kiện cốt lõi:** insert inbox và cập nhật dữ liệu nghiệp vụ phải nằm trong **cùng database transaction**. Ví dụ kiểm tra số dòng được cập nhật để không đánh dấu event đã xử lý khi projection đích chưa tồn tại. Nếu update thất bại hoặc điều kiện này sai, transaction rollback cả dòng inbox; lần redelivery có thể thử lại. Nếu commit thành công nhưng ACK tới broker thất bại, lần nhận sau sẽ gặp unique constraint và không chạy side effect lần nữa.

Ví dụ dùng `ON CONFLICT DO NOTHING` của PostgreSQL, không phải cú pháp SQL phổ quát cho mọi database. Với hệ quản trị khác, chọn cơ chế insert-if-absent và unique constraint tương đương.

### Những giới hạn cần biết

- Một event ID cần ổn định và không bị tái sử dụng cho một sự kiện khác.
- Tên consumer phải phản ánh logical subscriber; các projection độc lập không dùng chung khóa idempotency nếu chúng đều cần xử lý event.
- Side effect ra ngoài database (email/HTTP/thanh toán) **không** tự trở thành atomic với inbox transaction; cần outbox, idempotency key ở phía đích hoặc saga/compensation.
- Cần retention cho inbox dài hơn khoảng thời gian event có thể được replay, nếu không bản ghi đã xóa có thể được xử lý lại.
- Nếu event có nhiều loại side effect, phải thiết kế idempotency theo semantics từng operation.
- Khi cập nhật số dư, tồn kho hoặc tổng tiền, duplicate side effect có thể gây lỗi nghiêm trọng; luôn test DB commit → process crash → redelivery.

## 5. Producer lặp: không phải mọi duplicate đều do consumer

Nếu **cùng event ID nhưng Kafka offset khác nhau**, nguyên nhân có thể nằm ở producer hoặc một bước forward trong pipeline.

Các trường hợp:

- Producer không nhận được ACK đúng hạn, gửi lại message ở cấp ứng dụng.
- Một job outbox poll cùng record hai lần do thiếu locking/lease hoặc chưa đánh dấu published.
- Một request HTTP được retry mà logic tạo event không có idempotency key.
- Hai service cùng publish event cho một business transition.
- Khởi chạy lại Supplier phát lại dữ liệu cũ vì cursor/state không bền vững.
- Consumer đọc DLT rồi gửi về topic gốc tạo record mới với cùng ID.

### Kafka producer idempotence và giới hạn

Kafka hỗ trợ idempotent producer (ví dụ `enable.idempotence=true` với các cấu hình tương thích). Nó giúp broker loại trừ một số bản sao do **producer client retry cùng record trong phiên** theo sequence number. Điều này **không** deduplicate hai lần gọi publish logic riêng biệt, hai producer khác nhau, hay side effect ở database.

Kafka transactions và `read_committed` có thể giúp bảo đảm read-process-write trong phạm vi Kafka topics theo cấu hình transaction; không tự tạo transaction phân tán atomic giữa Kafka và database/HTTP. Với external side effects, dùng inbox/outbox và idempotency.

### Phân biệt bằng record identity

Đối với Kafka:

| Cùng event ID | Topic/partition/offset | Khả năng |
|---|---|---|
| Giống hệt | Cùng bộ ba | Một record broker được giao nhiều lần |
| Giống hệt | Offset khác | Producer hoặc topology ghi nhiều record |
| Giống hệt | Topic khác | Forward/retry/DLT/replay; kiểm tra routing |
| Giống nhưng ID khác | Bất kỳ | Business event được sinh lặp; kiểm tra nguồn |

Với RabbitMQ và Pulsar, dùng message ID/delivery metadata theo khả năng của binder; đừng giả định broker-native ID không bao giờ thay đổi khi message được republish vào retry/DLT.

## 6. Sai thứ tự có nhiều nghĩa

Cần tách bốn loại thứ tự:

1. **Thứ tự event nghiệp vụ:** thứ tự các thay đổi thật sự diễn ra, ví dụ version 1 → 2 → 3.
2. **Thứ tự publish/append:** thứ tự record được broker nhận trong một partition hoặc queue.
3. **Thứ tự delivery:** thứ tự consumer nhận được record.
4. **Thứ tự hoàn tất side effect:** thứ tự transaction DB hoặc HTTP request thực sự hoàn thành.

Ví dụ hai record được consumer nhận theo thứ tự 11 rồi 12, nhưng handler xử lý bất đồng bộ:

~~~text
10:00:00.000  receive version=11
10:00:00.001  receive version=12
10:00:00.030  complete version=12
10:00:00.150  complete version=11
~~~

Đây là lỗi **completion order**, không nhất thiết lỗi ordering của Kafka. Nếu business projection dùng last-write-wins dựa trên thời điểm commit, bản cập nhật cũ có thể ghi đè bản mới.

Cũng cần phân biệt:

- **Out-of-order event:** version nghiệp vụ đi ngược.
- **Late event:** event có event-time cũ đến sau; có thể hợp lệ trong stream processing.
- **Duplicate event:** cùng identity được xử lý lại.
- **Gap:** thiếu một sequence/version trong dòng sự kiện.

Một hệ thống có thể gặp đồng thời cả bốn tình huống.

## 7. Kafka bảo đảm thứ tự trong phạm vi partition

Kafka lưu record theo thứ tự offset tăng dần **trong một partition**. Consumer đọc partition đó theo offset, nhưng Kafka không bảo đảm total order giữa các partition.

~~~text
orders.events partition 0:  offset 80, 81, 82, 83
orders.events partition 1:  offset 41, 42, 43
orders.events partition 2:  offset 77, 78
~~~

Không có ý nghĩa so sánh rằng offset 83 của partition 0 "xảy ra sau" offset 78 của partition 2.

### Điều kiện để ordering theo aggregate có ích

Để giữ thứ tự các event của cùng `orderId` qua Kafka:

1. Producer sử dụng cùng key canonical cho mọi event của order đó.
2. Các event cùng key được partitioner điều hướng vào cùng partition theo chiến lược ổn định.
3. Các producer phát các event cùng aggregate theo trật tự đã được phối hợp; không dựa vào thời gian máy trên nhiều producer.
4. Consumer giữ cách xử lý tuần tự hoặc kiểm soát version khi dùng asynchronous work.
5. Không có nhánh replay/forward phá vỡ quy tắc key/order.
6. Việc đổi partition count, partitioner, key serializer hoặc hash strategy được đánh giá trước khi triển khai.

**Cùng key không tạo ordering nghiệp vụ nếu nhiều producer cạnh tranh phát cùng aggregate mà không có source sequencing.** Broker chỉ biết thứ tự nó nhận record, không biết transition nào xảy ra trước theo domain.

### Producer retry có thể gây đảo thứ tự như thế nào?

Với một số cấu hình không idempotent và nhiều request in-flight, nếu batch A gửi thất bại rồi được retry sau batch B, thứ tự append có thể khác thứ tự gọi send. Idempotent producer với cấu hình tương thích giúp duy trì ordering khi retry trong phạm vi producer protocol, nhưng không thay thế sequencing ở nguồn nghiệp vụ.

Khi điều tra, ghi lại producer config (`enable.idempotence`, `acks`, `retries`, `max.in.flight.requests.per.connection`), producer IDs nếu quan sát được, key, partition và offset. Không cố sửa trật tự bằng cách tăng concurrency.

## 8. Sai thứ tự do async processing và consumer concurrency

Trong Spring Cloud Stream, `consumer.concurrency` có thể tạo nhiều consumer threads. Với Kafka regular binder, cùng một partition của một consumer group thường được gán cho một consumer member tại một thời điểm, nhưng ứng dụng vẫn có thể tạo async processing.

Ví dụ nguy hiểm:

~~~java
@Bean
Consumer<OrderEvent> processOrders(Executor executor, OrderService service) {
    return event -> executor.execute(() -> service.apply(event));
}
~~~

Function trả về ngay sau khi queue được task, không đợi `service.apply` hoàn thành. Từ góc nhìn binder, handler có thể xem như đã hoàn tất và commit/ACK message trước khi business work thực sự kết thúc. Các task cũng có thể được thực thi ngược thứ tự.

Một hướng an toàn hơn khi cần tuần tự cho từng partition hoặc key là xử lý đồng bộ trong handler:

~~~java
@Bean
Consumer<OrderEvent> processOrders(OrderService service) {
    return service::apply;
}
~~~

Nếu cần concurrency cao:

- Giữ **serialized execution theo aggregate key** bằng worker partitioning/striped executor và kiểm soát ack sau completion.
- Dùng version/sequence check trước khi cập nhật trạng thái.
- Không submit vào queue vô hạn; giữ backpressure.
- Nếu tách xử lý khỏi consumer, ghi công việc vào **durable queue** trước khi ACK.
- Kiểm thử crash sau submit nhưng trước completion.
- Không kỳ vọng tăng `concurrency` sẽ làm một Kafka partition đơn lẻ được nhiều consumer xử lý song song theo ordering chuẩn.

### Một bản cập nhật cũ ghi đè bản mới

Giả sử consumer nhận version 8 rồi 9, nhưng version 9 hoàn thành trước. Nếu SQL dùng `UPDATE ... SET status=?` không kiểm soát version, version 8 có thể ghi đè version 9. Khi state là "mới nhất", có thể dùng version guard.

## 9. Bảo vệ state bằng aggregate version

Đặt `aggregateVersion` hoặc `sequence` do nguồn nghiệp vụ phát sinh:

~~~java
public record OrderEvent(
        String eventId,
        String orderId,
        long aggregateVersion,
        String status,
        Instant occurredAt
) {}
~~~

Ví dụ PostgreSQL chỉ áp dụng update nếu event mới hơn state hiện tại:

~~~sql
UPDATE order_projection
   SET status = :status,
       aggregate_version = :incoming_version
 WHERE order_id = :order_id
   AND aggregate_version < :incoming_version;
~~~

Ý nghĩa:

- Đã có version 9 → event version 8 hoặc 9 không ghi đè.
- Đã có version 7 → event version 9 có thể được áp dụng.
- Số version bắt buộc do nguồn phát tạo đơn điệu và có contract rõ ràng.

**Lưu ý:** điều kiện `current_version < incoming_version` phù hợp với projection "latest state wins" khi mỗi event mang **trạng thái đầy đủ** hoặc mọi phiên bản trung gian không cần thiết. Nó **không an toàn** cho event delta như "trừ 10", "cộng 5" hoặc chuyển trạng thái phải đi qua từng bước. Với delta/transition, cần:

- Kiểm tra `incoming_version == current_version + 1`.
- Giữ bản tin đến sớm trong buffer/store hữu hạn hoặc đưa về durable retry.
- Tìm event bị thiếu và có cơ chế reconciliation.
- Xử lý gap quá thời hạn theo chính sách nghiệp vụ, không đợi vô hạn trong heap.
- Dùng lock/optimistic concurrency hoặc cập nhật có điều kiện trong database transaction.

Đừng lấy timestamp của JVM consumer làm sequence chính. Clock skew và đường truyền khác nhau khiến occurredAt có thể không đồng nghĩa thứ tự nhân quả. Version từ aggregate owner thường mạnh hơn timestamp để diễn giải causal order.

## 10. Event time, late arrival và Kafka Streams

Với Kafka Streams, record có timestamp phục vụ windowing. Một event được tạo lúc 09:59 có thể đến sau record lúc 10:01 do network/retry. Đây là **late arrival**, không nhất thiết Kafka đã phá thứ tự offset.

Ví dụ aggregate theo time window:

~~~java
KTable<Windowed<String>, Long> counts = events
    .groupByKey(Grouped.with(Serdes.String(), orderEventSerde))
    .windowedBy(TimeWindows.ofSizeAndGrace(
            Duration.ofMinutes(5),
            Duration.ofMinutes(2)))
    .count();
~~~

Ví dụ tạo cửa sổ 5 phút và cho phép grace 2 phút đối với record đến muộn theo stream-time semantics. Event quá thời gian đóng cửa sổ có thể bị bỏ, tùy topology/operator. Window grace xử lý late event-time, **không** tự sửa duplicate business events hoặc thứ tự causal của aggregate.

Khi dùng Kafka Streams:

- Định nghĩa rõ timestamp extractor và múi giờ/đơn vị thời gian.
- Xem stream-time, grace và retention khi record đến muộn.
- Kiểm tra Serde cho key/value khi repartition hoặc materialize.
- Tránh dùng `groupBy` với key quá nóng làm một task/state store nghẽn.
- Kiểm tra changelog/state restoration và processing guarantee nếu topology có trạng thái.
- Dùng event ID/version hoặc dedup state store nếu nghiệp vụ không được tính lặp.

## 11. Dồn vào một Kafka partition là gì?

**Partition skew** xảy ra khi tải không được phân bố tương đối đồng đều giữa các partition hoặc task. Một partition có thể có:

- Tốc độ record vào cao hơn các partition khác.
- Nhiều bytes hơn dù số record tương đương.
- Phần lớn message cần xử lý nặng hơn.
- Một aggregate/key chiếm phần lớn traffic.
- Lag tăng liên tục trong khi những partition còn lại gần bằng 0.

Ví dụ:

| Partition | Input msg/s | Consumer msg/s | Lag tăng? |
|---|---:|---:|---|
| 0 | 120 | 130 | Không |
| 1 | 110 | 125 | Không |
| 2 | 900 | 250 | Có |
| 3 | 130 | 140 | Không |

Partition 2 có 900 msg/s nhưng xử lý được 250 msg/s, nên lag có thể tăng khoảng 650 msg/s. Thêm replica không tự tạo thêm consumer processing cho **cùng một partition** trong cùng group.

### Hot partition không luôn là hot key

- **Hot key:** một key như `customerId=VIP` chiếm phần lớn record và được hash vào một partition.
- **Skew do ít key:** chỉ có vài giá trị như `country=VN/US` hoặc `status=NEW/PAID` cho nhiều partition.
- **Skew do null/constant key:** producer gắn cùng một key cho mọi message hoặc định tuyến cố định.
- **Skew do heavy record:** ít message nhưng mỗi message xử lý chậm hoặc có payload lớn.
- **Skew do consumer:** một partition có message lỗi hoặc truy vấn DB chậm, khiến lag cao dù input distribution đều.
- **Skew do assignment:** một consumer được gán nhiều partition nặng; partition assignment và task placement mất cân đối.

Phải phân biệt **input rate per partition**, **processing rate per partition** và **lag per partition**. Chỉ nhìn lag không đủ để kết luận partitioner sai.

## 12. Kiểm tra hot partition bằng Kafka CLI và metrics

Kiểm tra consumer group và lag từng partition:

~~~bash
bin/kafka-consumer-groups.sh \
  --bootstrap-server kafka-1:9092 \
  --group order-projection \
  --describe
~~~

Ví dụ output minh họa:

~~~text
TOPIC          PARTITION  CURRENT-OFFSET  LOG-END-OFFSET  LAG
orders.events  0          50000           50010           10
orders.events  1          52000           52008           8
orders.events  2          19000           90000           71000
orders.events  3          49000           49005           5
~~~

Từ ví dụ, partition 2 có backlog lớn hơn. Nhưng cần đo lượng record/bytes được ghi mới theo partition và processing latency để biết đó là key skew hay consumer bị chậm.

Xem số partition và metadata của topic:

~~~bash
bin/kafka-topics.sh \
  --bootstrap-server kafka-1:9092 \
  --describe --topic orders.events
~~~

Cần kiểm tra thêm:

1. Có bao nhiêu consumer member active trong group?
2. Partition 2 đang gán cho consumer/pod nào?
3. Event keys phổ biến trong partition 2 là gì?
4. Có một key chiếm phần lớn traffic không?
5. Message size/processing duration p95, p99 có bất thường không?
6. Có retry/poison event lặp lại trong partition 2 không?
7. Sau rebalance, lag có chuyển theo partition hay theo pod?
8. Broker/controller có vấn đề I/O/network riêng với partition leader không?

Đừng đưa key nhạy cảm vào metric label. Nếu cần xác định hot keys, dùng cardinality-limited top-K sampling hoặc hash đã được phê duyệt, tránh lưu trữ PII trong monitoring.

## 13. Chọn partition key theo đơn vị cần ordering

Một partition key tốt phải phản ánh **đơn vị nghiệp vụ cần xử lý theo thứ tự** và đủ phân tán để tránh hot partition.

Ví dụ:

| Nghiệp vụ | Key đề xuất | Vì sao |
|---|---|---|
| Trạng thái từng đơn hàng | `orderId` | Các event cùng order đi cùng partition |
| Số dư tài khoản | `accountId` | Tuần tự theo account khi cần |
| Inventory theo SKU và kho | `warehouseId:sku` | Trạng thái cho từng stock record |
| Clickstream theo session | `sessionId` | Giữ order trong session |
| Trạng thái toàn khách hàng | `customerId` | Cần ordering theo customer, nhưng có nguy cơ hot customer |
| Thống kê toàn quốc gia | `country` | **Không phù hợp để phân tải** nếu chỉ có vài key |

Nếu chọn `eventId` làm partition key, distribution thường tốt nhưng event của cùng order có thể rơi vào nhiều partition, làm mất cơ sở cho per-order ordering. Nếu chọn `customerId`, nhiều đơn hàng của một khách hàng quá nóng có thể dồn vào một partition.

Chọn key là một **trade-off** giữa ordering và phân tải. Không có key đáp ứng đồng thời mọi mục tiêu; cần xác định phạm vi ordering cần thiết thật sự.

### Canonical key representation

Khóa String từ hai producer khác ngôn ngữ phải có cùng cách chuẩn hóa và serialize:

- Unicode normalization, chữ hoa/chữ thường.
- Khoảng trắng, tiền tố, mã tenant.
- Cách biểu diễn UUID hoặc số.
- Charset và byte serialization.
- Partitioner/hash strategy và số partition.

Cùng một giá trị nghiệp vụ nhưng bytes key khác nhau có thể hash ra partition khác. Đổi serializer hoặc partitioner trong một rolling deployment có thể phá phân phối theo key dù dữ liệu nhìn bằng mắt giống nhau.

## 14. Cấu hình partition key trong Spring Cloud Stream

Với producer binding sử dụng partitioning của Spring Cloud Stream, có thể khai báo partition key expression:

~~~yaml
spring:
  cloud:
    function:
      definition: publishOrders
    stream:
      bindings:
        publishOrders-out-0:
          destination: orders.events
          producer:
            partition-key-expression: payload.orderId
            partition-count: 12
~~~

Ví dụ này áp dụng khi payload tại thời điểm tính expression có property `orderId`. Với Java record, expression/property access và mapper phụ thuộc cách function/binder biểu diễn payload; cần integration test để chắc chắn key được xác định trước conversion đúng như mong đợi.

Các điểm cần phân biệt:

- `partition-key-expression` quyết định key dùng trong **cơ chế partitioning của Spring Cloud Stream** theo cấu hình hiệu lực.
- `partition-count` mô tả số partition được dùng cho thuật toán partitioning/provisioning; phải đối chiếu với partition count thực tế trên broker.
- Khai báo partition key expression hoặc key extractor phù hợp là cách bật đường partitioning ở producer binding theo cơ chế framework; không giả định có một property boolean `partitioned` dùng chung cho mọi producer binder/version.
- Kafka native producer còn có `ProducerRecord.key`, key serializer và partitioner. Không giả định một binding property và native Kafka partitioner là cùng một API trong mọi binder version.
- Đối với RabbitMQ/Pulsar, key/routing/subscription semantics khác Kafka; không tự sao chép YAML Kafka thành quy tắc ordering của Rabbit hoặc Pulsar.

### Khi dùng StreamBridge

`StreamBridge` gửi tới output binding được chỉ định, có thể cùng key expression/partitioning configuration của binding đó. Nếu gửi Spring `Message<?>`, có thể đặt Kafka key header theo contract Kafka binder phù hợp; hãy kiểm tra tên header và serializer trong Spring Kafka version đang dùng. Không tạo partition key từ UUID ngẫu nhiên khi nghiệp vụ yêu cầu ordering theo `orderId`.

Kiểm tra producer thực tế bằng client độc lập: gửi một chuỗi event cùng `orderId` rồi đọc topic, xác minh chúng vào cùng partition và xuất hiện theo offset tăng dần trong khoảng cấu hình ổn định.

## 15. Tăng số partition có chữa được hot partition không?

Không nhất thiết.

- Nếu một key tạo ra 80% lưu lượng, tăng từ 8 lên 32 partition vẫn có thể dồn 80% record vào **một partition**.
- Nếu nhiều key phân bố tương đối đồng đều nhưng có quá ít partition để chạy đủ consumer, tăng partition có thể cải thiện parallelism.
- Nếu bottleneck là database hoặc một handler chậm, thêm partition không tăng năng lực xử lý thực.
- Nếu consumer lag do poison message lặp, tăng partition không giải quyết lỗi dữ liệu.

**Cảnh báo ordering khi tăng partition count:** thuật toán hash-modulo có thể định tuyến cùng key vào partition khác khi số partition thay đổi. Record cũ của key vẫn nằm ở partition cũ, record mới có thể vào partition mới. Trong giai đoạn chuyển tiếp, hai partition được đọc độc lập nên **per-key order xuyên ranh giới thay đổi có thể bị phá**.

Khi cần ordering nghiêm ngặt, nên:

1. Đánh giá liệu partition count có được coi là một phần của wire/routing contract không.
2. Nếu tăng partition, thiết kế coordinated drain/cutover hoặc topic version mới.
3. Tái phân vùng dữ liệu có kiểm soát khi cần.
4. Dùng aggregate version để phòng trường hợp record cũ/new đi sai thứ tự.
5. Kiểm thử old/new producer chạy đồng thời và stateful consumers.
6. Có rollback/reconciliation; không đơn giản giảm số partition trở lại vì Kafka không hỗ trợ thu hẹp partition như một thao tác thông thường.

## 16. Biện pháp giảm hot partition đúng nguyên nhân

| Nguyên nhân | Biện pháp phù hợp | Rủi ro/điều kiện |
|---|---|---|
| Một key quá nóng | Tách aggregate nếu nghiệp vụ cho phép; salt/shard key rồi tổng hợp lại | Mất ordering toàn key; cần re-aggregation |
| Key có cardinality thấp | Chọn key chi tiết hơn | Phải giữ đúng business ordering contract |
| Partition count nhỏ, key phân bố đều | Tăng partition cùng migration plan | Key→partition mapping thay đổi |
| Consumer của partition chậm | Profile handler/DB/external dependency | Không phải lỗi partitioner |
| Một consumer gánh nhiều partition nặng | Scale/migration task assignment | Tổng capacity vẫn cần đủ |
| Poison event/retry storm | Sửa handler, bounded retry, DLT | Chống duplicate side effect |
| Event size bất thường | Giới hạn payload, tối ưu serializer | Schema/backward compatibility |
| Kafka Streams stateful hotspot | Đổi key aggregation hoặc hai tầng aggregate nếu phép toán associative | State-store/changelog migration |
| Giới hạn CPU/heap | Tối ưu batch, GC, memory, I/O | Không phá ACK/order |

### Salt key chỉ phù hợp với toán tử có thể kết hợp

Với phép đếm hoặc tính tổng, có thể xử lý hai tầng:

~~~text
Hot key = region-VN
  -> region-VN:shard-0 -> partial count
  -> region-VN:shard-1 -> partial count
  -> region-VN:shard-2 -> partial count
  -> combine partial results -> region-VN total
~~~

Tách key làm tăng parallelism, nhưng **mất ordering tuyệt đối** của các event trong key gốc. Không sử dụng salting cho cập nhật số dư tài khoản hoặc các bước nghiệp vụ phải tuần tự, trừ khi đã thiết kế concurrency control tương ứng.

Đối với một aggregate đơn lẻ thật sự cần xử lý lần lượt, điểm nghẽn có thể là ràng buộc nghiệp vụ. Giải pháp là tối ưu chi phí xử lý từng event, giảm lượng công việc đồng bộ hoặc thay đổi mô hình nghiệp vụ, không đơn thuần tăng consumer.

## 17. Consumer group và concurrency không phá giới hạn partition

Regular Kafka binder có thể cấu hình consumer concurrency:

~~~yaml
spring:
  cloud:
    function:
      definition: processOrders
    stream:
      bindings:
        processOrders-in-0:
          destination: orders.events
          group: order-projection
          consumer:
            concurrency: 4
~~~

Ví dụ topic có 6 partition:

| Deployment | Consumer members trong group | Consumer nhận partition hoạt động tối đa |
|---|---:|---:|
| 1 replica × concurrency 2 | 2 | 2 |
| 2 replica × concurrency 3 | 6 | 6 |
| 3 replica × concurrency 4 | 12 | 6 |

Trong cùng group, một Kafka partition được gán cho một consumer tại một thời điểm; consumer vượt quá số partition có thể idle. Nhiều input topic và assignment policy có thể khiến số partition assignment cụ thể khác cách đếm đơn giản này.

Tăng replicas từ 2 lên 4 khi mọi partition đã có consumer không tự tăng parallelism của **một partition nóng**. Trước khi scale:

- Kiểm tra số partition.
- Đo tải theo partition và theo pod.
- Kiểm tra downstream connection pool.
- Xem số consumer thực sự có partition assignment.
- Kiểm tra rebalance duration và processing lag.
- Xác minh ACK/commit semantics không đổi khi tăng concurrency.

Không đổi `group` chỉ để thấy lag giảm; group mới có offset riêng và có thể replay hoặc bỏ lịch sử tùy cấu hình.

## 18. Kafka Streams: repartition và task skew

Trong Kafka Streams binder, key và phân vùng có vai trò đặc biệt với `KStream`, `KTable`, aggregation và join.

Ví dụ thay key bằng `orderId`:

~~~java
@Bean
Function<KStream<String, OrderEvent>, KStream<String, OrderEvent>>
normalizeOrderKey() {
    return input -> input.selectKey(
            (oldKey, event) -> event.orderId()
    );
}
~~~

`selectKey` thay key logical của record trong topology. Kafka Streams có thể đánh dấu stream cần repartition khi toán tử phía sau phụ thuộc key; việc chỉ gọi `selectKey` không nhất thiết lập tức tạo repartition topic. Khi group/join/aggregate, cần xét `Grouped.with(...)`, key/value Serde, số partition và task assignment.

Hot key có thể làm một task và local state store chịu phần lớn chi phí xử lý. Khi chẩn đoán, quan sát:

- Record rate/latency theo task hoặc thread.
- Changelog/repartition topic sizes.
- State store size/restore duration.
- Aggregation/join key distribution.
- RocksDB/cache/GC và disk I/O.
- Rebalance và task migration.
- ApplicationId và state schema trước khi thay topology.

Đổi key, store name, Serde hoặc repartition strategy có thể yêu cầu rebuild state. Không dùng application reset hoặc xóa changelog ở production để thử "cân lại tải" khi chưa có kế hoạch replay, migration và downstream idempotency.

## 19. RabbitMQ: lặp và sai thứ tự có semantics riêng

RabbitMQ không phân phối record theo Kafka partition; message được route qua exchange/binding đến queue, rồi queue chuyển delivery cho consumer.

Một số nguyên nhân duplicate:

- Consumer ACK chưa tới broker trước khi connection đóng.
- Consumer ném lỗi rồi nack/requeue.
- Publisher không chắc broker nhận publish và gửi lại.
- Message được republish sang retry/DLQ rồi replay.
- Handler side effect thành công trước khi delivery được ACK.

RabbitMQ có thể cung cấp FIFO-like delivery từ queue theo một số điều kiện, nhưng **thứ tự hoàn tất xử lý không được bảo đảm với nhiều consumer**, prefetch, priority hoặc redelivery/requeue.

Ví dụ một queue có hai consumer:

~~~text
Queue head: M1, M2, M3
Consumer A receives M1 -> xử lý 500ms
Consumer B receives M2 -> xử lý 20ms, ACK
Consumer B receives M3 -> xử lý 30ms, ACK
Consumer A ACK M1
Completion order: M2, M3, M1
~~~

Nếu cần tuần tự chặt chẽ toàn queue, cân nhắc một active consumer, prefetch nhỏ và xử lý đồng bộ; điều này giới hạn throughput. RabbitMQ có mô hình single active consumer ở broker và các cách shard queue theo routing key nếu chỉ cần ordering theo business key. Xác minh loại queue, tính năng và phiên bản binder/broker trước khi triển khai.

### Cấu hình prefetch và concurrency

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        processOrders-in-0:
          destination: orders.exchange
          group: order-projection
          consumer:
            concurrency: 2
      rabbit:
        bindings:
          processOrders-in-0:
            consumer:
              prefetch: 5
              requeueRejected: false
~~~

Đây là ví dụ minh họa bounded in-flight. `prefetch` giới hạn số delivery chưa ACK theo semantics của RabbitMQ/Spring AMQP; `concurrency` tăng số consumer. `requeueRejected: false` không tự tạo DLT: cần DLX/DLQ được broker/binder cấu hình đúng. Nếu nghiệp vụ cần ordering, nhiều consumer có thể làm completion order khác delivery order.

Không đặt `requeueRejected=true` cho poison message mà không có backoff/hạn mức; redelivery storm có thể làm một queue có vẻ "bị kẹt" và message lặp liên tục.

## 20. Pulsar: Shared, Key_Shared và redelivery

Pulsar dùng subscription để xác định cách phân phối message tới consumer:

| Subscription type | Tính chất tổng quát | Tác động ordering |
|---|---|---|
| Exclusive | Một consumer hoạt động trên subscription | Dễ suy luận order hơn, nhưng vẫn cần xét async/retry |
| Failover | Một consumer active, consumer dự phòng | Redelivery khi failover và ranh giới lifecycle |
| Shared | Message được phân phối giữa consumer | Không bảo đảm thứ tự hoàn tất theo key |
| Key_Shared | Message cùng key được phối hợp phân phối theo key | Hữu ích khi cần xử lý theo key; vẫn cần test retry/batching/consumer concurrency |

Với Pulsar `Key_Shared`, cùng key thường được giao cho consumer phù hợp theo chính sách key distribution; ordering theo key dựa vào cấu hình, batching và điều kiện hoạt động. Nếu producer batching không phù hợp (gộp keys khác nhau vào một batch), phân phối Key_Shared có thể không đúng kỳ vọng; cân nhắc key-based batching hoặc tắt batching theo tài liệu client version.

Negative acknowledgment/redelivery và retry/DLT có thể tác động đến thứ tự quan sát. Tài liệu Pulsar lưu ý redelivery khi nack có thể dẫn tới out-of-order trong một số subscription semantics. Không kết luận "Key_Shared nghĩa là side effect luôn hoàn tất theo thứ tự" nếu handler submit async tasks hoặc có retry.

Nếu message lặp:

1. Kiểm tra message ID, key và redelivery count.
2. Kiểm tra ACK timeout, negative ack delay, retry topic và DLT policy.
3. Kiểm tra subscription type và receiver queue.
4. Kiểm tra consumer restart, broker unload hoặc rebalance.
5. Thử lại bằng integration test trên đúng Pulsar broker/client/binder version.

Không sao chép cấu hình Kafka `enableDlq` hay Kafka `partitionKeyExpression` rồi giả định nó có hiệu lực giống hệt trên Pulsar binder.

## 21. Phân biệt lặp vì broker và lặp vì retry của framework

Spring Cloud Stream có retry/error handling cấp function handler trong nhiều binder. Ví dụ:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        processOrders-in-0:
          consumer:
            max-attempts: 3
            back-off-initial-interval: 1000
            back-off-max-interval: 10000
~~~

Trong đường imperative framework retry được hỗ trợ, `max-attempts: 3` thường gồm lần xử lý đầu. Đó không đồng nghĩa với ba lần broker redelivery. Một record có thể gọi handler nhiều lần trước khi broker nhận ACK/nack. Ngoài ra, native deserialization, Kafka Streams và reactive function có error handling riêng.

Để chẩn đoán, ghi riêng:

- Số broker delivery/redelivery attempts.
- Số handler invocations per event ID.
- Số request tới DB/API per event ID.
- Số output record được publish.
- Số DLT record.
- Kết quả commit/ACK cuối cùng.

Đặt một retry budget tổng có giới hạn. Retry ở framework, client HTTP, broker và DLT replay có thể khuếch đại tải vào hot partition.

## 22. Error handling không tự bảo đảm thứ tự hoặc dedup

Khi một event thất bại:

- Retry đồng bộ có thể chặn partition/queue, giữ thứ tự nhưng làm tăng lag.
- Skip/continue có thể giữ throughput nhưng tạo gap nghiệp vụ.
- Đưa vào DLT tách poison message khỏi main flow, nhưng replay sau này có thể đến **muộn hoặc sai thứ tự causal**.
- Đẩy failed event sang retry topic giải phóng main consumer nhưng có thể cho event mới vượt qua event cũ.

Ví dụ:

~~~text
Main topic:
  order-21/version=10   -> failed -> retry topic
  order-21/version=11   -> processed successfully
Retry topic later:
  order-21/version=10   -> processed after 11
~~~

Nếu handler dùng version guard đúng contract, event 10 có thể bị đánh dấu stale. Nhưng nếu version 10 là delta bắt buộc, cần gap detection/replay chứ không được bỏ qua.

Hãy xác định rõ **chính sách giữa correctness và liveness**:

| Chính sách | Ưu điểm | Nhược điểm |
|---|---|---|
| Block/retry tại chỗ | Dễ giữ per-partition order | Một poison event chặn cả partition |
| DLT rồi tiếp tục | Partition tiến được | Aggregate có thể thiếu phiên bản |
| Retry topic bất đồng bộ | Tránh giữ worker | Có thể đảo thứ tự nghiệp vụ |
| Version guard/latest-wins | Chặn stale overwrite | Không phù hợp cho delta/gap bắt buộc |
| Ordered inbox/buffer theo key | Bảo vệ causal order | Tăng state, timeout và logic vận hành |

Không có một đáp án chung: event snapshot và event delta có yêu cầu khác nhau.

## 23. Metric và dữ kiện cần thu thập

Chẩn đoán tốt cần dữ kiện ở ba tầng.

### Broker

- Kafka: input bytes/records theo partition, log end offset, group committed offset, lag, assignment, rebalance.
- RabbitMQ: ready/unacked, consumer count, prefetch, redelivery, reject, DLX/DLQ.
- Pulsar: backlog, unacked, redelivery, subscription type, consumer assignment, retry/DLT.
- Broker/network: lỗi kết nối, throttling, disk I/O và leader movement.

### Application

- Invocation count theo event ID hoặc sample bounded-cardinality.
- Tỷ lệ `ALREADY_PROCESSED` theo logical consumer.
- Handler processing time và DB/HTTP latency p95/p99.
- Active workers, executor queue depth, rejected tasks.
- Offset/ACK failures, retry/backoff, DLT ingress.
- Processing time so với occurredAt và aggregateVersion.
- State-store restore/repartition metrics với Kafka Streams.

### Contract

- Producer key bytes/format, null-key ratio, số key distinct.
- Top-K key frequency với chính sách bảo vệ dữ liệu.
- Event ID uniqueness và aggregate version gaps.
- Topic/queue/subscription routing.
- Producer và consumer version khi lỗi xuất hiện.
- Đợt tăng partition hoặc đổi serializer gần nhất.

Không dùng raw `eventId` hoặc `orderId` làm Prometheus metric label vì cardinality có thể vô hạn. Có thể ghi ID trong log có sampling/bảo vệ, còn metric dùng binding/topic/partition/error-class có giới hạn hợp lý.

## 24. Runbook A — Message lặp lại

Làm theo thứ tự:

1. Xác định `eventId` và side effect có thực sự bị lặp hay chỉ handler log lặp.
2. So sánh broker record identity: Kafka topic/partition/offset, Rabbit delivery metadata hoặc Pulsar message ID.
3. Nếu cùng record được giao lại, tìm restart, rebalance, ACK timeout, exception hoặc commit failure.
4. Nếu là record khác, điều tra producer retry cấp ứng dụng, outbox, dual-publish, DLT replay.
5. Đo framework handler attempts tách khỏi broker redelivery attempts.
6. Kiểm tra inbox/unique constraint và ranh giới DB transaction.
7. Kiểm tra có ACK trước khi side effect hoàn tất không.
8. Nếu duplicate side effect đã xảy ra, cần reconciliation/compensation theo nghiệp vụ.
9. Sau khi sửa, test crash ngay sau DB commit nhưng trước ACK.
10. Ghi nhận metric duplicate delivery rate và duplicate side-effect rate riêng.

**Không xóa consumer group offset hoặc DLT để "xóa duplicate".** Làm vậy có thể khiến replay nhiều hơn và mất dấu vết điều tra.

## 25. Runbook B — Sai thứ tự

1. Xác định sự kiện có cùng aggregate key hay không.
2. Kiểm tra event `aggregateVersion`/sequence và occurredAt, không dựa mỗi timestamp log.
3. Với Kafka, kiểm tra topic/partition/offset của các event.
4. Nếu cùng partition và offset đúng, điều tra async processing, thread pool, retry, DB commit order.
5. Nếu khác partition, kiểm tra producer key, partitioner, serializer và thay đổi partition count.
6. Nếu producer khác nhau phát cùng aggregate, xác định nguồn sequencing/owner.
7. Nếu event đến muộn qua retry/DLT, kiểm tra business policy cho late/gap.
8. Chọn snapshot latest-wins hoặc ordered delta processing theo semantics.
9. Thử xử lý phiên bản `N+1` trước `N` trong integration test.
10. Xác minh output/state không regress khi record cũ replay.

**Không coi Kafka offset là event version.** Offset có phạm vi một partition; version nghiệp vụ phải được quản lý ở tầng aggregate.

## 26. Runbook C — Dồn tải vào một partition

1. Xác minh lag và input rate từng partition qua CLI/metrics.
2. Xác định có hot key, null key, constant key hoặc ít key khác nhau không.
3. Kiểm tra partition assignment và consumer/pod đang xử lý partition nóng.
4. So sánh processing latency của hot partition với partition khác.
5. Xác minh lỗi retry/poison message có đang chặn partition không.
6. Kiểm tra bottleneck DB, CPU, heap, producer throttling, state store.
7. Nếu key distribution tốt nhưng partition ít, đánh giá tăng partition có kế hoạch.
8. Nếu một key quá nóng, cân nhắc tối ưu per-key processing hoặc shard/reaggregate chỉ khi nghiệp vụ cho phép.
9. Nếu đổi partitioner/key/partition count, lập migration preserving order.
10. Theo dõi lại lag, throughput, duplicate và event-order violations sau rollout.

**Không tăng consumer concurrency vô hạn:** một partition vẫn chỉ có một active consumer member trong group thông thường. Số thread tăng có thể làm tốn CPU/connection mà không cải thiện hot partition.

## 27. Kiểm thử tái hiện ba lỗi

Test Binder có ích để kiểm tra function logic và validation nhưng không tái hiện đầy đủ broker offsets, partition assignment, ACK/redelivery hoặc nack/requeue. Các lỗi này cần broker integration test bằng Testcontainers hoặc một môi trường Kafka/RabbitMQ/Pulsar thật phù hợp với production.

### Test duplicate và idempotency

~~~text
Given:
  eventId = evt-702
  DB projection chưa có eventId này

When:
  publish event
  consumer commit DB nhưng bị kill trước ACK
  broker redeliver cùng event

Then:
  handler có thể chạy lại
  business side effect chỉ commit một lần
  inbox có đúng một bản ghi (consumer_name, event_id)
  consumer tiến lên sau lần xử lý thành công
~~~

Kiểm thử producer duplicate riêng: publish **hai broker records** với cùng event ID nhưng offsets/message IDs khác, xác minh DB vẫn chỉ cập nhật một lần.

### Test out-of-order và gap

~~~text
Given:
  Order order-21 đã xử lý version 9

When:
  version 11 đến trước version 10

Then (snapshot latest-wins):
  version 11 có thể trở thành state hiện tại
  version 10 đến sau không ghi đè

Then (ordered delta):
  version 11 được giữ/retry trong durable buffer
  version 10 được áp dụng trước
  version 11 được áp dụng sau
  gap timeout có alert/reconciliation
~~~

Chạy thêm test: cùng key, nhiều producer; async task có latency khác nhau; DLT replay; restart giữa hai event; tăng partition count.

### Test hot partition

~~~text
Scenario A: 95% messages có cùng key
  Expected: một partition/task chịu phần lớn tải
  Assertion: thêm consumer không tự chia một key thành nhiều partition

Scenario B: 10.000 key phân bố đều
  Expected: gần đều theo key hash, có sai lệch ngẫu nhiên
  Assertion: concurrency tăng tới giới hạn partition hữu ích

Scenario C: phân bố key đều nhưng partition 2 có DB timeout
  Expected: lag partition 2 tăng dù producer distribution cân bằng
  Assertion: root cause thuộc consumer/dependency, không phải key
~~~

Khi benchmark, ghi per-partition throughput/bytes/lag, CPU, heap, GC, DB pool, retries và p99 processing latency. Hãy dùng một tập event fixture có phân phối key tương tự production.

## 28. Cấu hình và cách sửa không nên áp dụng mù quáng

| Cách sửa vội | Vì sao nguy hiểm | Thay thế |
|---|---|---|
| Đổi `group` để xử lý duplicate | Group mới có offsets riêng, có thể replay nhiều hơn | Giữ group, sửa ACK/idempotency |
| Đặt key ngẫu nhiên để phân tải | Phá ordering theo aggregate | Chọn key nghiệp vụ, shard chỉ khi được phép |
| Tăng partition count tức thì | Key có thể chuyển partition, phá per-key order trong cutover | Migration/rollout có kiểm soát |
| Tăng concurrency trên một hot partition | Không làm một partition có nhiều consumer active trong cùng group | Tìm hot key và tối ưu task |
| Tăng retry vô hạn | Poison event và dependency chậm tạo storm | Backoff, budget, DLQ và reconciliation |
| Dùng `logAndContinue` cho mọi lỗi | Có thể bỏ record quan trọng | Phân loại lỗi và xác định gap policy |
| Trả bình thường sau khi catch mọi exception | Có thể ACK dù side effect thất bại | Đưa lỗi vào error handler đúng tầng |
| Submit task rồi ACK ngay | Task nằm trong heap có thể mất khi process chết | Chờ completion hoặc durable handoff |
| Đếm event theo Kafka offset toàn topic | Offset không có total order liên partition | Dùng aggregate sequence/version |
| Xóa DLT để không còn lỗi | Mất dữ liệu cần điều tra/replay | Quản lý DLT và sửa nguyên nhân |
| Thấy lag rồi tăng prefetch | Chuyển backlog vào heap, không tăng service rate | Tìm bottleneck thực |
| Coi exactly-once Kafka là DB exactly-once | Kafka transactions không bao phủ side effect DB | Inbox/outbox và idempotent operation |

## 29. Checklist triển khai production

### Hợp đồng event

- [ ] Có `eventId` ổn định qua retry và replay.
- [ ] Có `aggregateId` cho đơn vị cần ordering.
- [ ] Có `aggregateVersion` hoặc sequence nếu business yêu cầu causal order.
- [ ] Key serializer/partitioner và partition count được quản lý như contract.
- [ ] Quy định rõ event snapshot, delta hay transition.
- [ ] Xác định duplicate/gap/late-event policy.

### Giao nhận và lỗi

- [ ] Chỉ ACK/commit sau khi công việc cần bảo đảm hoàn tất.
- [ ] Đã test crash sau DB commit trước ACK.
- [ ] Có unique constraint/inbox hoặc cơ chế idempotent tương đương.
- [ ] Có retry budget, backoff, DLT và quy trình replay.
- [ ] Không nuốt exception làm ACK sai.
- [ ] Có cơ chế xử lý side effect ngoài DB nếu được retry.

### Ordering và phân tải

- [ ] Đã kiểm tra per-partition input rate, bytes, lag và assignment.
- [ ] Đã đo hot-key ratio và null-key ratio.
- [ ] Concurrency được giới hạn bởi partition/subscription và downstream capacity.
- [ ] Async processing không phá ACK hoặc ordering.
- [ ] Đổi partition count/key/serializer có migration plan.
- [ ] Với Kafka Streams, đã kiểm tra repartition, Serde và state store.
- [ ] Với RabbitMQ/Pulsar, đã kiểm tra queue/subscription ordering và redelivery.

### Kiểm thử/vận hành

- [ ] Có broker integration test cho duplicate, out-of-order, hot partition.
- [ ] Test DLT replay và broker/consumer restart.
- [ ] Theo dõi metrics riêng: duplicate deliveries, duplicate side effects, ordering violations, hot partition lag.
- [ ] Dashboard không gắn event ID/cardinality cao làm label.
- [ ] Runbook có owner, điều kiện rollback và quy trình reconciliation.

## Kết luận

**Message lặp** chủ yếu là vấn đề delivery/retry và ACK/commit boundary; **sai thứ tự** là vấn đề causal version, key/partition, asynchronous processing và replay; **hot partition** là vấn đề phân phối key, tải xử lý và giới hạn parallelism. Ba triệu chứng có thể xuất hiện cùng lúc nhưng phải chẩn đoán bằng dữ liệu ở đúng tầng.

Trong Kafka, thứ tự được bảo đảm theo **offset trong từng partition**, không theo toàn topic hoặc toàn business event. Trong RabbitMQ, nhiều consumer/prefetch/requeue có thể làm thứ tự hoàn tất khác thứ tự delivery. Trong Pulsar, subscription type (đặc biệt Shared/Key_Shared), batching và redelivery quyết định cách phân phối và tính chất ordering. Trong Kafka Streams, `groupBy`, repartition và state store còn tạo thêm các điểm cần xem xét.

Đừng tìm một cấu hình magic bảo đảm "không lặp, không đảo thứ tự, mọi partition đều cân". Hãy thiết kế event ID và aggregate version, xử lý idempotent bằng transaction/inbox, dùng partition key theo phạm vi cần ordering, giữ ACK sau completion, phân biệt hot key với slow consumer, rồi kiểm thử replay/redelivery và cutover trên broker thật. Đó là nền tảng để hệ thống Spring Cloud Stream xử lý sự kiện đúng khi tăng tải, retry và triển khai nhiều instance.

## Tài liệu tham khảo

- [Spring Cloud Stream — Consumer Groups](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/consumer-groups.html) và [Partitioning](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/overview-partitioning.html): group, concurrency, producer partitioning và ràng buộc theo binder.
- [Spring Cloud Stream — Kafka Binder Configuration](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-binder/config-options.html): Kafka consumer/producer configuration và các tùy chọn error/DLT.
- [Apache Kafka — Consumer Groups](https://kafka.apache.org/documentation/#consumerconfigs) và [Producer Configs](https://kafka.apache.org/documentation/#producerconfigs): partition assignment, poll, idempotence và ordering trong Kafka client.
- [Apache Kafka — Semantics](https://kafka.apache.org/documentation/#semantics): at-least-once, at-most-once, idempotent producer và transaction scope.
- [Spring Cloud Stream — Kafka Streams Binder](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-streams-binder/configuration-options.html): Kafka Streams topology, Serde và runtime properties.
- [RabbitMQ — Consumer Acknowledgements and Publisher Confirms](https://www.rabbitmq.com/docs/confirms), [Consumer Prefetch](https://www.rabbitmq.com/docs/consumer-prefetch) và [Queues](https://www.rabbitmq.com/docs/queues): redelivery, prefetch, requeue và ordering limitations.
- [Apache Pulsar — Messaging Concepts](https://pulsar.apache.org/docs/concepts-messaging/) và [Key_Shared Subscriptions](https://pulsar.apache.org/docs/concepts-messaging/#key_shared): subscription semantics và ordering theo key.

Các ví dụ có tính hướng dẫn và có thể cần điều chỉnh theo Spring Cloud Stream, Kafka/RabbitMQ/Pulsar binder, broker và client version. Khi chạy production, ưu tiên reference guide của đúng release, kiểm tra dữ liệu thực và viết integration test cho bảo đảm mà nghiệp vụ yêu cầu.

