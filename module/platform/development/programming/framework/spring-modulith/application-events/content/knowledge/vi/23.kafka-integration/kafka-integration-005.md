# Offset và acknowledgement

Trong Kafka, consumer đọc message theo partition và theo dõi tiến độ bằng **offset**. Acknowledgement trong ứng dụng thường có nghĩa là xác nhận một record đã được xử lý để consumer có thể commit offset tương ứng. Hiểu đúng quan hệ giữa xử lý nghiệp vụ, acknowledgement và offset commit giúp tránh hai lỗi nghiêm trọng: xác nhận quá sớm làm mất tác động nghiệp vụ, hoặc xác nhận quá muộn khiến message được giao lại và tạo duplicate.

Với Spring Modulith, application event giúp các module trong cùng ứng dụng giao tiếp qua hợp đồng sự kiện; Event Publication Registry theo dõi publication đến listener theo cơ chế của framework. Khi event được externalize qua Kafka adapter, Kafka có thêm cơ chế consumer group và offset riêng. Trạng thái publication của Spring Modulith, xác nhận gửi của producer và offset commit của Kafka là các mốc khác nhau, cần được quan sát theo từng chặng.

## 1. Offset là vị trí đọc trong partition

Kafka lưu message trong các partition của một topic. Mỗi record trong một partition có một offset tăng dần. Offset xác định vị trí của record trong partition đó; nó không phải ID toàn cục của event và không tự chứng minh nghiệp vụ đã xử lý thành công.

Consumer group có một offset đã commit cho mỗi partition mà group sở hữu. Offset đã commit thường biểu thị **vị trí record tiếp theo cần đọc**. Vì vậy, nếu record có offset `42` đã được xử lý và xác nhận, consumer commit offset `43`.

Ví dụ, một topic có hai partition:

| Partition | Record đã đọc | Offset đã commit | Vị trí đọc tiếp theo |
| --- | --- | --- | --- |
| `orders-0` | 40, 41, 42 | 43 | 43 |
| `orders-1` | 17, 18 | 19 | 19 |

Offset là tiến độ của consumer group trên từng partition. Hai consumer group độc lập có thể đọc cùng một topic với offset khác nhau. Khi một group khởi động lại hoặc nhận partition sau rebalance, Kafka sử dụng offset đã commit của group để xác định điểm tiếp tục đọc.

Kafka không xóa từng record khi consumer acknowledgement. Record vẫn được giữ theo retention policy của topic; offset commit chỉ cập nhật tiến độ đọc của consumer group. Vì vậy, consumer group khác vẫn có thể đọc cùng dữ liệu và group hiện tại có thể reset offset nếu chính sách vận hành cho phép.

## 2. Phân biệt producer acknowledgement và consumer acknowledgement

Từ publisher đến consumer có ít nhất hai loại xác nhận:

| Xác nhận | Thành phần phát ra | Ý nghĩa |
| --- | --- | --- |
| Producer acknowledgement (`acks`) | Kafka broker phản hồi producer | Broker đã nhận và xác nhận ghi record theo cấu hình producer/broker. |
| Consumer acknowledgement/offset commit | Consumer hoặc listener container | Tiến độ xử lý của consumer group đã được ghi nhận để tiếp tục đọc. |

Producer `acks` không chứng minh consumer đã xử lý message. Ngược lại, consumer commit offset không chứng minh producer đã ghi message với durability như nghiệp vụ yêu cầu. Cần xác định rõ mỗi bên xác nhận điều gì.

Với producer, `acks=all` yêu cầu broker chờ các replica đang nằm trong tập in-sync replicas xác nhận theo cấu hình cluster; `min.insync.replicas` và replication factor ảnh hưởng mức chịu lỗi. `acks=0` không chờ broker xác nhận, còn `acks=1` chờ leader xác nhận. Các lựa chọn này ảnh hưởng durability và latency, không phải consumer delivery guarantee.

Với consumer, commit offset là thao tác cập nhật tiến độ group. Nếu consumer commit offset trước khi ghi database, process có thể dừng sau commit offset nhưng trước commit nghiệp vụ; record sẽ không được đọc lại từ vị trí cũ và tác động nghiệp vụ có thể bị mất. Nếu consumer commit database trước rồi dừng trước offset commit, record có thể được đọc lại và tạo duplicate. Do đó consumer at-least-once thường chọn xử lý nghiệp vụ trước, commit offset sau, đồng thời bảo vệ duplicate bằng idempotency.

## 3. Consumer group và phân phối partition

Trong một consumer group, mỗi partition tại một thời điểm chỉ được gán cho một consumer member. Nhiều partition có thể được xử lý song song bởi nhiều member. Nếu số member lớn hơn số partition, một số member sẽ không nhận partition.

Khi member tham gia hoặc rời group, Kafka có thể thực hiện rebalance để phân phối lại partition. Rebalance có thể xảy ra khi deploy, scale, consumer mất heartbeat hoặc xử lý quá lâu. Trong lúc rebalance, partition có thể được thu hồi và giao cho member khác.

Một tình huống phổ biến:

1. Consumer A đọc record offset `42`.
2. A ghi dữ liệu nghiệp vụ vào database và transaction commit.
3. A dừng trước khi commit offset `43`.
4. Sau rebalance, consumer B nhận partition và đọc lại offset `42`.
5. B xử lý lại record đó.

Đây là redelivery hợp lệ trong at-least-once. Consumer cần idempotent để lần đọc lại không tạo thêm reservation, invoice hoặc tác động nghiệp vụ khác.

Thời gian xử lý record phải phù hợp với cấu hình poll/heartbeat và giới hạn thời gian xử lý của consumer. Nếu listener giữ record quá lâu, group có thể coi member không còn hoạt động và rebalance. Với tác vụ dài, cân nhắc tách công việc, điều chỉnh giới hạn poll hợp lý hoặc chuyển sang mô hình worker có kiểm soát; không tăng timeout một cách mù quáng.

## 4. Commit offset tự động và commit do ứng dụng/container quản lý

Kafka consumer có cơ chế auto commit offset. Nếu bật `enable.auto.commit`, client có thể commit offset theo chu kỳ mà không đợi ứng dụng xác nhận từng record đã hoàn tất. Điều này dễ gây mất tác động nghiệp vụ nếu quá trình xử lý kéo dài hoặc thất bại sau khi offset đã commit.

Với Spring Kafka, thông thường nên để listener container quản lý commit và cấu hình rõ `enable.auto.commit=false`. Container phối hợp việc gọi listener với acknowledgement mode để quyết định khi nào commit offset. Cần kiểm tra cấu hình thực tế của `ConcurrentKafkaListenerContainerFactory`, consumer properties và transaction manager; không dựa vào giá trị mặc định của một phiên bản khác.

Các acknowledgement mode thường gặp trong Spring Kafka gồm:

| Ack mode | Cách hoạt động khái quát | Lưu ý |
| --- | --- | --- |
| `RECORD` | Commit offset sau khi từng record được listener xử lý xong. | Phù hợp khi muốn xác nhận theo record; vẫn cần xem transaction và lỗi listener. |
| `BATCH` | Commit offset sau khi tất cả record trong một poll batch được xử lý. | Một lỗi có thể ảnh hưởng tiến độ của batch; container xử lý theo cấu hình error handler. |
| `TIME` / `COUNT` / `COUNT_TIME` | Commit khi đạt điều kiện thời gian hoặc số record. | Có thể tăng throughput nhưng làm thay đổi khoảng thời gian record chưa được commit. |
| `MANUAL` | Listener gọi `Acknowledgment.acknowledge()`; container quản lý commit theo mode. | Phải gọi acknowledgement sau khi xử lý bền vững thành công. |
| `MANUAL_IMMEDIATE` | Yêu cầu commit ngay khi acknowledgement được gọi trên consumer thread. | Cần hiểu rõ thread và transaction/commit configuration. |

Tên mode và chi tiết hành vi có thể thay đổi theo phiên bản Spring Kafka. Chọn mode theo yêu cầu xử lý, rồi xác minh bằng integration test với đúng phiên bản và cấu hình đang dùng.

## 5. Acknowledgement sau khi transaction nghiệp vụ commit

Với at-least-once, nguyên tắc là chỉ xác nhận record sau khi tác động nghiệp vụ đã được lưu bền vững. Ví dụ dưới đây dùng manual acknowledgement và tách service transaction thành một bean riêng:

```java
@Component
public class OrderConfirmedKafkaListener {

    private final InventoryMessageHandler handler;

    public OrderConfirmedKafkaListener(InventoryMessageHandler handler) {
        this.handler = handler;
    }

    @KafkaListener(topics = "orders", groupId = "inventory")
    public void onMessage(
            ConsumerRecord<String, OrderConfirmed> record,
            Acknowledgment acknowledgment) {

        handler.process(record.value());

        // process() trả về sau khi transaction database của bean handler commit.
        acknowledgment.acknowledge();
    }
}
```

```java
@Service
public class InventoryMessageHandler {

    private final InboxRepository inbox;
    private final InventoryService inventory;

    public InventoryMessageHandler(
            InboxRepository inbox,
            InventoryService inventory) {
        this.inbox = inbox;
        this.inventory = inventory;
    }

    @Transactional
    public void process(OrderConfirmed event) {
        if (!inbox.insertIfAbsent("inventory", event.eventId())) {
            return;
        }

        inventory.reserveFor(event.orderId());
    }
}
```

Ví dụ giả định listener container được cấu hình `AckMode.MANUAL` hoặc mode manual phù hợp, `enable.auto.commit=false`, và `insertIfAbsent` được bảo vệ bằng unique constraint. Do `InventoryMessageHandler` là bean Spring riêng, transaction proxy commit khi lời gọi `process` trả về cho listener. Sau đó listener mới gọi acknowledgement.

Trong `MANUAL`, lời gọi `acknowledge()` báo cho container rằng record đã được xử lý; thời điểm commit broker thực tế vẫn tuân theo cách container quản lý acknowledgement và commit. `MANUAL_IMMEDIATE` có semantics khác về thời điểm commit. Không nên diễn giải lời gọi `acknowledge()` như một xác nhận đồng bộ rằng broker đã lưu offset nếu cấu hình commit không bảo đảm điều đó.

Nếu `process` ném exception, listener không gọi acknowledgement. Error handler/container quyết định retry, seek, recover hoặc chuyển record sang dead-letter theo cấu hình. Nếu database đã commit nhưng offset chưa commit, record có thể được giao lại; inbox giúp loại duplicate.

## 6. Inbox và idempotency để xử lý redelivery

Offset commit và transaction database thường thuộc hai hệ thống quản lý khác nhau. Không có transaction nguyên tử mặc định bao trùm cả database nghiệp vụ và Kafka offset. Inbox pattern giúp consumer đạt hiệu quả xử lý một lần trong phạm vi transaction database.

Một bảng inbox có thể dùng khóa chính ghép theo consumer và message ID:

```sql
CREATE TABLE consumed_message (
    consumer_name VARCHAR(150) NOT NULL,
    message_id    VARCHAR(200) NOT NULL,
    processed_at  TIMESTAMP WITH TIME ZONE NOT NULL,
    PRIMARY KEY (consumer_name, message_id)
);
```

`insertIfAbsent` cần thực hiện thao tác insert nguyên tử, chẳng hạn `INSERT ... ON CONFLICT DO NOTHING` ở database hỗ trợ cú pháp đó. Nếu insert không tạo hàng mới, consumer đã xử lý message trước đó và có thể kết thúc mà không lặp side effect.

Việc ghi inbox và cập nhật nghiệp vụ phải nằm trong cùng transaction:

- Nếu nghiệp vụ lỗi, transaction rollback cả inbox và thay đổi nghiệp vụ; lần giao lại có thể thử lại.
- Nếu transaction commit, inbox và tác động nghiệp vụ cùng tồn tại.
- Nếu process dừng trước offset commit, Kafka có thể giao lại; unique key phát hiện message đã xử lý.

Inbox không tự bảo vệ lời gọi ra hệ thống ngoài transaction. Nếu handler gọi payment gateway hoặc gửi email, hãy dùng idempotency key mà hệ thống đích hỗ trợ, hoặc ghi outbox để tạo một chặng giao tiếp có thể retry độc lập.

## 7. Kafka transaction và giới hạn exactly-once

Kafka hỗ trợ transaction để kết hợp việc ghi nhiều record vào Kafka và commit offset của các record đã đọc trong cùng một Kafka transaction. Cách này hữu ích cho luồng consume-transform-produce: output record và tiến độ input có thể được commit cùng nhau, tránh output bị ghi nhận khi input offset chưa được xác nhận tương ứng.

Spring Kafka hỗ trợ transaction manager và transactional listener container để phối hợp producer transaction với việc xử lý record. Khi bật Kafka transaction, cần cấu hình transactional producer, transaction ID prefix phù hợp với từng application instance, consumer isolation phù hợp và error handling tương ứng. Cấu hình chính xác phụ thuộc phiên bản Spring Kafka và topology triển khai.

Kafka exactly-once semantics áp dụng trong phạm vi các thao tác Kafka được tham gia transaction. Nó không tự mở rộng sang một database quan hệ, HTTP API, email provider hoặc payment gateway. Nếu consumer cập nhật database rồi commit Kafka offset trong một transaction riêng, vẫn tồn tại khoảng trống giữa hai commit.

Với luồng cần cập nhật database và Kafka cùng nhau, cân nhắc:

1. **Inbox + xử lý database + commit offset sau đó:** đạt hiệu quả idempotent trong database, chấp nhận redelivery.
2. **Database outbox:** ghi thay đổi nghiệp vụ và message cần phát trong cùng transaction; relay publish message sau commit.
3. **Kafka transaction cho luồng Kafka-to-Kafka:** dùng transaction để ghi output và xác nhận offset input trong cùng Kafka transaction.

Chọn phương án theo ranh giới dữ liệu và yêu cầu nghiệp vụ. Không tuyên bố exactly-once end-to-end nếu còn side effect ngoài transaction chưa được bảo vệ.

## 8. Offset khi xử lý song song và theo batch

Offset được commit theo partition, vì vậy xử lý song song trong cùng partition cần được kiểm soát cẩn thận. Giả sử consumer đã đọc offset `10`, `11`, `12` và xử lý chúng trên các worker độc lập. Nếu `12` hoàn tất trước nhưng `10` chưa xong, commit offset `13` có thể khiến Kafka tiếp tục từ `13` sau sự cố và bỏ qua record `10` chưa hoàn tất.

Để tránh commit vượt qua record chưa xử lý, hãy:

- Giữ thứ tự xử lý trong một partition khi dùng commit offset theo tiến độ liên tục.
- Nếu xử lý song song, theo dõi các offset đã hoàn tất và chỉ commit đến vị trí liên tục cao nhất đã xử lý xong.
- Dùng concurrency theo partition hoặc key sao cho thứ tự nghiệp vụ được bảo toàn.
- Kiểm tra hành vi batch ack và error handler khi một record trong batch thất bại.

Với Spring Kafka, listener container và acknowledgement mode có cơ chế quản lý offset cho record/batch. Khi dùng asynchronous listener return types hoặc xử lý bất đồng bộ tùy biến, cần theo đúng hướng dẫn của phiên bản Spring Kafka vì quy tắc commit và thread ownership có thể khác listener đồng bộ.

## 9. Rebalance, retry và dead-letter

Khi partition được thu hồi do rebalance, consumer cũ có thể chưa commit offset cho record vừa xử lý. Consumer mới sẽ tiếp tục từ offset đã commit và có thể đọc lại record. Xử lý trùng do rebalance là một phần bình thường của at-least-once.

Khi listener lỗi, Spring Kafka có thể phối hợp với error handler để retry, seek hoặc recover record. Một số cấu hình dùng `DefaultErrorHandler` và `DeadLetterPublishingRecoverer` để thử lại rồi gửi record lỗi sang dead-letter topic. Cần xác định rõ số lần retry, backoff, loại exception được retry và thời điểm offset được xác nhận sau khi recover.

Dead-letter topic (DLT) là nơi lưu record không thể xử lý theo chính sách hiện tại. Cần giữ metadata đủ để truy vết topic, partition, offset gốc, exception và thời điểm lỗi; giới hạn quyền truy cập và retention; đồng thời định nghĩa quy trình sửa nguyên nhân và replay. Replay nên giữ event/message ID gốc nếu vẫn là cùng sự kiện, để inbox có thể phát hiện duplicate. Nếu nghiệp vụ quyết định tạo một hành động mới, phát event mới và liên kết `causation_id`.

Không retry vô hạn một poison message. Retry nên có backoff và giới hạn, đồng thời không nhân số lần thử ngoài ý muốn khi cả listener container, client HTTP và dịch vụ downstream đều có retry riêng.

## 10. Tích hợp Kafka với Spring Modulith

Spring Modulith giúp module nguồn phát application event và theo dõi publication nội bộ. Khi cần đưa event ra Kafka, ứng dụng có thể dùng cơ chế externalization và Kafka integration tương ứng với phiên bản Spring Modulith. Ví dụ event được đánh dấu externalize:

```java
@Externalized("orders")
public record OrderConfirmed(
        UUID eventId,
        UUID orderId,
        Instant occurredAt
) {}
```

Giá trị `orders` được dùng như routing value theo cấu hình externalization; adapter Kafka quyết định cách chuyển thành destination và message. Cần cấu hình dependency/integration module, serializer, KafkaTemplate hoặc adapter tương ứng theo phiên bản đang sử dụng. Không giả định annotation tự tạo topic hoặc consumer group.

Ở phía nhận, `@KafkaListener` thuộc Spring Kafka xử lý record từ topic và consumer group. Đây là chặng Kafka consumer, với offset và acknowledgement do Kafka client/Spring Kafka container quản lý. Event Publication Registry theo dõi publication trong mô hình Spring Modulith; offset Kafka theo dõi tiến độ đọc của consumer group. Hai cơ chế không thay thế nhau.

Nếu ứng dụng vừa có listener nội bộ `@ApplicationModuleListener` vừa externalize cùng event, hãy quan sát riêng trạng thái publication nội bộ và chặng gửi Kafka. Broker xác nhận publish không có nghĩa consumer group đã xử lý; consumer group commit offset cũng không có nghĩa mọi listener nội bộ đã hoàn tất.

## 11. Kiểm thử offset và acknowledgement

Kiểm thử cần xác nhận vị trí commit offset và trạng thái nghiệp vụ khi lỗi xảy ra ở từng ranh giới:

1. Khi listener xử lý thành công và transaction database commit, acknowledgement được gửi theo ack mode đã chọn.
2. Khi listener ném exception trước commit, offset không được xác nhận sớm và record có thể được retry theo chính sách.
3. Khi database commit nhưng consumer dừng trước offset commit, record được giao lại nhưng inbox ngăn side effect trùng.
4. Khi offset commit trước database commit trong một cấu hình không phù hợp, kiểm thử thể hiện nguy cơ mất tác động nghiệp vụ.
5. Khi consumer group rebalance, record chưa được commit có thể được đọc lại và xử lý idempotent.
6. Khi một record trong batch lỗi, offset commit không vượt qua record chưa xử lý.
7. Khi hết retry, record được recover vào DLT với metadata nguồn đầy đủ.
8. Với Kafka transaction, output record và offset input được commit/abort theo cùng transaction.
9. Với Spring Modulith externalization, kiểm tra riêng event được chuyển đến Kafka adapter và trạng thái publication theo integration đang dùng.

`@EmbeddedKafka` hoặc Testcontainers có thể hỗ trợ integration test với broker. Nên kiểm tra offset group thực tế sau khi listener xử lý, sau lỗi và sau rebalance; chỉ xác nhận method listener được gọi là chưa đủ. Dùng đúng phiên bản Kafka broker/client và Spring Kafka của ứng dụng để kiểm tra semantics.

## 12. Quan sát offset và acknowledgement

Các chỉ số vận hành hữu ích gồm:

- consumer lag theo group và partition;
- offset đã đọc, offset đã commit và tuổi record chưa được xác nhận;
- số record đang xử lý, retry, redelivery và DLT;
- thời gian xử lý record và thời gian commit offset;
- số lần rebalance, partition bị thu hồi và lỗi heartbeat/poll;
- tỷ lệ duplicate bị inbox loại bỏ;
- lỗi commit, lỗi serialization và lỗi khi publish DLT.

Log nên chứa topic, partition, offset, consumer group, message ID, event type, aggregate ID và correlation/trace ID. Không dùng offset hoặc message ID làm metric label có cardinality cao; chúng phù hợp hơn cho log và trace. Khi điều tra một message, đối chiếu cùng lúc offset group, trạng thái inbox và transaction nghiệp vụ.

## 13. Checklist triển khai

- [ ] Phân biệt producer `acks` với consumer acknowledgement và offset commit.
- [ ] Xác định consumer group và partition chịu trách nhiệm cho mỗi record.
- [ ] Cấu hình rõ `enable.auto.commit` và acknowledgement mode của listener container.
- [ ] Chỉ acknowledge/commit sau khi tác động nghiệp vụ đã commit bền vững.
- [ ] Dùng inbox/idempotency để xử lý redelivery và rebalance.
- [ ] Không commit offset vượt qua record chưa xử lý trong cùng partition.
- [ ] Chọn Kafka transaction khi cần phối hợp input offset và output Kafka record.
- [ ] Dùng outbox/inbox hoặc idempotency cho ranh giới database và hệ thống ngoài Kafka.
- [ ] Có retry giới hạn, backoff, DLT và quy trình replay.
- [ ] Phân biệt Event Publication Registry của Spring Modulith với offset của Kafka consumer group.
- [ ] Kiểm thử với broker thực tế/embedded broker và quan sát offset sau các tình huống lỗi.

Offset và acknowledgement xác định consumer group sẽ tiếp tục đọc từ đâu sau khi xử lý hoặc gặp sự cố. Khi acknowledgement chỉ được gửi sau commit nghiệp vụ, duplicate được bảo vệ bằng inbox/idempotency và việc xử lý song song tôn trọng thứ tự offset trong từng partition, Kafka có thể cung cấp delivery at-least-once đáng tin cậy. Trong kiến trúc Spring Modulith, cần giữ rõ ranh giới giữa publication nội bộ, externalization qua adapter và tiến độ consumer group để mỗi chặng có cơ chế xác nhận và phục hồi phù hợp.
