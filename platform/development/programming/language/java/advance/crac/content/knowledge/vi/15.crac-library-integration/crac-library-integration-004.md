# Thông điệp đang xử lý, offset, xác nhận và nguy cơ xử lý lặp

Trong ứng dụng Java sử dụng message broker, một thông điệp có nhiều trạng thái khác nhau: broker đã giao message cho consumer, ứng dụng đang xử lý, nghiệp vụ đã được ghi bền vững, và broker đã nhận xác nhận (acknowledgement) hoặc offset commit. Những trạng thái này thường nằm ở nhiều nơi: một phần trong heap của JVM, một phần trong database, và một phần tại broker.

CRaC (Coordinated Restore at Checkpoint) lưu trạng thái tiến trình tại một thời điểm. Nó không tạo một giao dịch nguyên tử bao trùm process image, database và broker. Nếu checkpoint xảy ra khi message đang được xử lý, trạng thái trong heap có thể không còn đồng bộ với trạng thái giao nhận mà broker đang quản lý. Khi restore, message có thể được giao lại, offset có thể đã tiến lên, hoặc delivery lease/channel cũ không còn hợp lệ. Đây là nguồn gốc của nguy cơ mất message hoặc xử lý lặp.

Thiết kế an toàn cần phối hợp ba việc: dừng nhận message mới và drain công việc đang chạy trước checkpoint; chỉ ack/commit sau khi kết quả nghiệp vụ đã được ghi bền vững; và làm cho consumer có thể xử lý lại cùng một message mà không tạo side effect trùng lặp.

## 1. Một message đi qua những trạng thái nào?

Một luồng xử lý message điển hình gồm các bước:

```text
Broker giữ message
       |
       v
Broker giao message cho consumer
       |
       v
Consumer bắt đầu xử lý
       |
       v
Thực hiện nghiệp vụ / ghi database
       |
       v
Kết quả nghiệp vụ được commit bền vững
       |
       v
Consumer gửi ACK hoặc commit offset
       |
       v
Broker ghi nhận message đã được xử lý
```

Điểm cần phân biệt là **xử lý xong trong bộ nhớ** không đồng nghĩa với **nghiệp vụ đã commit**, và **gửi ack** không đồng nghĩa với broker chắc chắn đã lưu ack nếu kết quả chưa được xác nhận theo protocol.

| Trạng thái | Nơi thường lưu | Có được CRaC checkpoint bảo vệ không? |
| --- | --- | --- |
| Message đang nằm trong queue/topic | Broker storage | Không; broker quản lý độc lập. |
| Message đã được giao nhưng chưa ack | Broker delivery state và có thể có object trong heap | Không được bảo đảm nhất quán giữa hai phía. |
| Payload/processing state trong listener | Heap, thread stack, executor task | Có thể xuất hiện trong process image, nhưng không chứng minh broker vẫn giữ cùng delivery/session. |
| Business change đã commit | Database transaction log/storage | Được database bảo vệ theo durability policy, không phải bởi ảnh CRaC. |
| Ack/offset đã commit | Broker metadata hoặc consumer group state | Được broker quản lý độc lập; không rollback cùng process image. |
| Retry counter hoặc attempt state | Broker, database hoặc heap tùy thiết kế | Nếu chỉ nằm trong heap, nó có thể cũ hoặc mất đồng bộ sau restore. |

Vì các trạng thái nằm ở nhiều hệ thống, không có một thời điểm checkpoint nào tự động biến toàn bộ quá trình thành exactly-once.

## 2. Vì sao checkpoint giữa lúc xử lý message nguy hiểm?

Giả sử consumer nhận message `M42`. Handler đã cập nhật database nhưng chưa commit offset hoặc ack. Tiến trình được checkpoint rồi tạm dừng. Trong thời gian đó, broker có thể phát hiện consumer không còn poll/heartbeat hoặc delivery lease hết hạn và giao lại message cho consumer khác.

```text
Consumer A                  Database                 Broker
----------                  --------                 ------
Receive M42  ---------------------------------------> Deliver M42
Update business row ------->
                            COMMIT
       |                                             Ack chưa nhận
       | checkpoint                                  |
       X                                             v
                                         Consumer A mất lease/session
                                                     |
                                                     v
                                         Deliver M42 cho Consumer B
```

Consumer B xử lý lại message dù database đã được cập nhật bởi A. Nếu handler không idempotent, side effect có thể xảy ra hai lần.

Tình huống ngược lại còn nguy hiểm hơn: consumer ack message hoặc commit offset trước khi database transaction hoàn tất. Nếu process bị dừng trước khi dữ liệu được commit, broker có thể coi message đã xong và không giao lại, trong khi nghiệp vụ chưa được lưu bền vững. Đây là cửa sổ mất message.

Nguyên tắc phổ biến là **hoàn tất và commit side effect bền vững trước, sau đó mới xác nhận message**. Điều này thường tạo semantics at-least-once: message có thể được giao lại nếu process chết sau database commit nhưng trước ack. Idempotency xử lý cửa sổ duplicate đó.

## 3. Offset, acknowledgement và delivery tag khác nhau

Các broker không dùng cùng một khái niệm xác nhận.

| Hệ thống | Định danh/tiến độ | Xác nhận | Điều cần chú ý khi restore |
| --- | --- | --- | --- |
| Apache Kafka | Offset theo từng partition; consumer group lưu offset tiếp theo cần đọc | Commit offset | Broker lưu committed offset; consumer assignment và client state cũ cần được tạo lại/rejoin. |
| RabbitMQ | Delivery tag theo channel cho từng delivery | `basicAck`, `basicNack` hoặc `basicReject` | Delivery tag gắn với channel; channel cũ không thể được coi là còn hợp lệ sau khi reconnect. |
| JMS | Message delivery và session acknowledgement/transaction | Acknowledge hoặc `Session.commit()` tùy mode | Session/connection có lifecycle riêng; cần tạo lại session và để provider giao lại message chưa được xác nhận. |
| Amazon SQS | Message receipt handle và visibility timeout | `DeleteMessage` | Receipt handle gắn với lần nhận; visibility hết hạn có thể khiến message được giao lại. |

Không nên gọi tất cả các cơ chế này là “offset”. Offset là tiến độ đọc theo partition của Kafka; RabbitMQ dùng delivery tag; SQS dùng receipt handle; JMS dùng acknowledgement/transaction của session.

## 4. Kafka: offset commit và cửa sổ xử lý lặp

Trong Kafka, offset thuộc từng partition. Khi consumer commit offset `N`, ý nghĩa thông thường là consumer đã xử lý các record trước `N` và lần đọc tiếp theo bắt đầu từ offset `N`. Vì vậy, offset commit thường là **next offset**, không phải offset cuối cùng đã xử lý.

Ví dụ partition có các record 100, 101 và 102:

```text
Record đã xử lý:       100   101
Offset cần commit:                   102
Lần đọc tiếp theo:                   bắt đầu từ 102
```

Nếu consumer xử lý song song, không được commit offset cao hơn khi vẫn còn một record thấp hơn chưa hoàn tất. Giả sử record 100 còn đang xử lý nhưng 101 và 102 đã xong. Commit offset 103 có thể khiến consumer group bỏ qua record 100 sau khi restart. Chỉ commit tới offset liên tục cao nhất mà mọi record trước nó đã hoàn tất.

### Auto commit và manual commit

Với `enable.auto.commit=true`, consumer có thể commit tiến độ theo lịch dựa trên các record đã poll, trong khi ứng dụng vẫn đang xử lý bất đồng bộ. Điều này có thể làm offset tiến lên trước khi business processing hoàn tất.

Với handler cần kiểm soát thứ tự side effect, thường nên tắt auto commit và commit thủ công sau khi xử lý bền vững:

```properties
enable.auto.commit=false
```

Ví dụ xử lý tuần tự đơn giản:

```java
import org.apache.kafka.clients.consumer.Consumer;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.apache.kafka.clients.consumer.ConsumerRecords;
import org.apache.kafka.clients.consumer.OffsetAndMetadata;
import org.apache.kafka.common.TopicPartition;

import java.time.Duration;
import java.util.Map;

ConsumerRecords<String, String> records = consumer.poll(Duration.ofMillis(500));

for (ConsumerRecord<String, String> record : records) {
    processAndCommitBusinessTransaction(record);

    TopicPartition partition = new TopicPartition(record.topic(), record.partition());
    long nextOffset = record.offset() + 1;
    consumer.commitSync(Map.of(partition, new OffsetAndMetadata(nextOffset)));
}
```

Ví dụ trên minh họa thứ tự xử lý tuần tự; nó chưa phải mẫu tối ưu cho mọi consumer và cần xử lý batch, nhiều partition, retry, rebalance và timeout trong ứng dụng thật. Nếu một poll trả nhiều record cùng partition, commit sau mỗi record có thể tốn chi phí; có thể commit batch offset liên tục cao nhất đã xử lý xong.

### Xử lý song song cần commit theo contiguous offset

Giả sử partition có ba record:

```text
Offset 200: đang xử lý
Offset 201: hoàn tất
Offset 202: hoàn tất
```

Committed offset an toàn vẫn là 200 (next offset của record trước 200, tùy committed position ban đầu) cho đến khi 200 hoàn tất. Không thể commit 203 chỉ vì 201 và 202 xong. Khi 200 hoàn tất, consumer có thể tiến committed offset lên 203.

Hãy giữ completion tracker theo partition và commit offset liên tục, đồng thời bảo đảm chỉ consumer thread gọi KafkaConsumer API vì `KafkaConsumer` không thread-safe. Worker thread nên báo kết quả về consumer thread thay vì gọi `commitSync()` trực tiếp.

## 5. RabbitMQ: ack gắn với channel và delivery tag

RabbitMQ giao message trên một channel và gán delivery tag cho lần giao đó. Consumer gửi `basicAck` để xác nhận đã xử lý. Nếu channel/connection đóng trước khi broker nhận ack, message chưa được xác nhận có thể được đưa lại vào queue và giao cho consumer khác.

Một điểm quan trọng là delivery tag chỉ có ý nghĩa trong channel đã giao message. Sau khi CRaC restore và tạo channel mới, không được dùng delivery tag cũ từ heap để ack một delivery mới. Nếu channel cũ đã đóng, broker có thể từ chối ack với lỗi unknown delivery tag hoặc channel-level exception.

Với xử lý đồng thời, tùy chọn `multiple=true` của `basicAck` xác nhận tất cả delivery tag chưa ack đến tag được chỉ định. Chỉ dùng khi mọi message trước tag đó đã hoàn tất. Nếu message hoàn tất out-of-order, ack nhiều có thể xác nhận nhầm message còn đang xử lý. Khi không duy trì thứ tự hoàn tất, dùng ack từng message hoặc completion tracker bảo đảm chỉ ack dải liên tục.

Ví dụ khái niệm:

```java
void onMessage(Message message, Channel channel, long deliveryTag) throws Exception {
    processAndCommitBusinessTransaction(message);
    channel.basicAck(deliveryTag, false);
}
```

Ack chỉ được gửi sau khi transaction nghiệp vụ commit thành công. Nếu process dừng sau commit nhưng trước `basicAck`, RabbitMQ có thể giao lại message; handler phải idempotent. Nếu ack trước commit và database transaction thất bại, message có thể bị mất khỏi queue dù nghiệp vụ chưa hoàn tất.

## 6. JMS và SQS cũng có cửa sổ duplicate

Với JMS, semantics phụ thuộc acknowledgement mode và session transaction. Trong transacted session, ứng dụng thường xử lý message rồi gọi `Session.commit()` để xác nhận cả phần công việc của session theo semantics provider. Nếu session rollback hoặc connection bị đóng trước commit, message có thể được giao lại. Với `AUTO_ACKNOWLEDGE` và listener container, thời điểm ack phụ thuộc cách container gọi listener và xác nhận kết quả; hãy đọc cấu hình cụ thể thay vì suy luận từ việc method handler đã return.

Với SQS, message được giao kèm receipt handle và có visibility timeout. Nếu handler chưa gọi `DeleteMessage` trước khi visibility timeout hết, message có thể xuất hiện lại cho consumer khác. Nếu thời gian checkpoint/restore dài hơn visibility timeout, một message vẫn có thể được giao lại trong khi ảnh process cũ còn giữ trạng thái xử lý. Sau restore, receipt handle cũ cũng có thể không còn hợp lệ cho lần delivery hiện tại.

Với cả JMS và SQS, quy tắc chung vẫn là: không coi trạng thái listener object trong heap là nguồn sự thật về trạng thái message ở broker; xác nhận theo protocol hiện hành và thiết kế handler chịu được redelivery.

## 7. Vì sao cần quiesce và drain consumer trước checkpoint?

Quiesce là ngừng nhận công việc mới; drain là chờ công việc đã nhận hoàn tất. Đây là bước quan trọng để checkpoint không cắt ngang ranh giới giữa business commit và broker acknowledgement.

Một quy trình điển hình:

1. Đưa ứng dụng sang trạng thái `REFUSING_TRAFFIC` hoặc chế độ bảo trì nếu consumer có thể tạo side effect ảnh hưởng hệ thống.
2. Dừng listener container hoặc pause consumer để không nhận delivery mới.
3. Tiếp tục xử lý các message đã nhận và chờ handler đang chạy hoàn tất trong deadline.
4. Với message hoàn tất, commit database transaction rồi ack/commit offset theo đúng protocol.
5. Với message chưa hoàn tất khi hết hạn, hủy công việc an toàn và để message chưa ack/commit để broker giao lại.
6. Đóng consumer connection/session/channel/client theo API của thư viện.
7. Tạo CRaC checkpoint khi không còn delivery/session cũ cần tiếp tục.

Đối với Kafka, `pause()` ngăn poll trả thêm record từ partition đã pause nhưng ứng dụng thường vẫn cần gọi `poll()` để duy trì group membership trong lúc drain. Khi chuẩn bị checkpoint, có thể dừng listener/container theo API framework rồi close consumer; không để một `KafkaConsumer` bị treo qua checkpoint với kỳ vọng assignment và heartbeat vẫn hợp lệ.

Đối với RabbitMQ, dừng consumer và drain handler trước khi đóng channel. Với SQS, dừng nhận message mới và hoàn tất hoặc để visibility timeout/visibility policy xử lý message chưa hoàn tất; không lưu receipt handle cũ để dùng sau restore.

## 8. Consumer group, rebalance và trạng thái assignment

Kafka consumer group quản lý partition assignment và liveness của member. Khi consumer không poll/heartbeat trong thời gian đủ dài, broker có thể loại member khỏi group và rebalance partition cho consumer khác. Trong thời gian checkpoint, tiến trình không hoạt động; vì vậy, không nên giả định assignment trước checkpoint vẫn thuộc về process sau restore.

Sau restore:

- Tạo Kafka consumer mới hoặc để listener container tạo lại theo lifecycle framework.
- Subscribe topic/group như cấu hình hiện hành.
- Chờ broker cấp assignment mới.
- Đọc committed offset của group và tiếp tục từ vị trí broker xác nhận.
- Không sử dụng assignment, generation hoặc in-memory poll state cũ như quyền sở hữu partition hiện tại.

Các giá trị như `max.poll.interval.ms`, `session.timeout.ms` và heartbeat settings ảnh hưởng thời điểm group loại consumer. Tăng timeout chỉ để “chịu được checkpoint” không giải quyết được tính nhất quán của message đang xử lý; thời gian checkpoint có thể dài không dự đoán được. Nên đóng/quản lý consumer có chủ đích và khởi tạo lại sau restore.

## 9. Đặt thứ tự business commit và broker ack đúng

Khi database và broker không tham gia cùng một distributed transaction, có hai thứ tự cơ bản:

| Thứ tự | Cửa sổ lỗi | Kết quả có thể xảy ra |
| --- | --- | --- |
| Ack/commit offset trước, rồi commit database | Process dừng sau ack nhưng trước DB commit | Broker nghĩ message đã xong; thay đổi nghiệp vụ có thể bị mất. |
| Commit database trước, rồi ack/commit offset | Process dừng sau DB commit nhưng trước ack | Broker giao lại message; nghiệp vụ có thể chạy lần nữa. |

Thứ tự thứ hai thường được chọn vì duplicate có thể xử lý bằng idempotency, trong khi mất message sau ack sớm khó khôi phục hơn. Với thao tác không thể lặp an toàn, cần một transaction boundary hoặc cơ chế deduplication bền vững.

```text
Consumer nhận message
       |
       v
BEGIN database transaction
       |
       v
Ghi business data + inbox/dedup record
       |
       v
COMMIT database transaction
       |
       v
ACK / commit broker offset
```

Nếu process bị dừng sau database commit nhưng trước ack, message sẽ được giao lại. Inbox record cho biết message id đã được xử lý và consumer có thể ack mà không lặp side effect.

## 10. Idempotent consumer và inbox pattern

Idempotent consumer là handler có thể nhận cùng một message nhiều lần nhưng chỉ tạo ra một hiệu quả nghiệp vụ tương đương một lần xử lý.

Một cách phổ biến là lưu `message_id` vào bảng inbox với unique constraint cùng transaction với business update:

```sql
CREATE TABLE processed_message (
    message_id VARCHAR(200) PRIMARY KEY,
    processed_at TIMESTAMP NOT NULL
);
```

Pseudo-code:

```java
@Transactional
public void handle(Message message) {
    boolean firstDelivery = inboxRepository.insertIfAbsent(message.id());

    if (!firstDelivery) {
        return; // Message đã được xử lý trong transaction trước.
    }

    applyBusinessChange(message);
}
```

`insertIfAbsent` phải dựa vào unique constraint hoặc thao tác nguyên tử của database, không phải chuỗi `SELECT` rồi `INSERT` thiếu khóa đồng bộ. Nếu hai consumer nhận cùng message đồng thời, database phải bảo đảm chỉ một transaction thắng việc insert idempotency key.

Ack message sau khi method transaction đã commit thành công. Nếu insert inbox và business update cùng transaction, một lần xử lý thất bại sẽ rollback cả hai; broker có thể giao lại và lần sau thử lại. Nếu transaction commit xong nhưng ack thất bại, lần giao lại thấy inbox record và không lặp business update.

Inbox record cần retention đủ dài so với thời gian broker có thể redeliver, retry và replay. Nếu xóa record quá sớm, một message cũ được replay có thể thực hiện side effect lần nữa.

## 11. Idempotency key, version và thứ tự message

Không phải message nào cũng có ID duy nhất đáng tin cậy. Nếu producer không cung cấp message id ổn định, hãy tạo event id trước khi publish và giữ nguyên id qua retry. Không tạo id mới cho mỗi lần gửi lại cùng một nghiệp vụ.

Với dữ liệu có version, có thể bảo vệ bằng điều kiện cập nhật:

```sql
UPDATE account_projection
SET balance = :new_balance,
    version = :incoming_version
WHERE account_id = :account_id
  AND version < :incoming_version;
```

Điều kiện version ngăn một message cũ ghi đè projection đã cập nhật bằng event mới hơn. Cần chọn quy tắc phù hợp với semantics của event; không phải mọi event đều có thể bỏ qua chỉ vì version nhỏ hơn.

Idempotency cũng không tự bảo đảm thứ tự. Nếu message cùng key/aggregate phải xử lý tuần tự, cần partitioning theo key, FIFO group hoặc cơ chế sequence/version ở database. Khi xử lý song song, chỉ ack/commit tới message liên tục đã hoàn tất và giữ đúng thứ tự nghiệp vụ cần thiết.

## 12. Exactly-once: giới hạn và điều kiện

“Exactly-once” thường chỉ có ý nghĩa trong một phạm vi được xác định rõ. Kafka có thể hỗ trợ transaction để ghi output record và commit input offsets trong cùng Kafka transaction đối với luồng consume-transform-produce được cấu hình phù hợp. Điều này không tự mở rộng thành transaction nguyên tử với database, email, HTTP API hoặc hệ thống bên ngoài.

| Trường hợp | Cơ chế thường dùng | Giới hạn |
| --- | --- | --- |
| Kafka consume → transform → Kafka produce | Kafka producer transaction, gửi offsets vào cùng transaction, consumer đọc `read_committed` | Phạm vi transaction là Kafka; cần cấu hình và xử lý fencing/transactional id đúng. |
| Broker → database | DB inbox/dedup record + business update trong một transaction, sau đó ack broker | Broker có thể redeliver; handler phải idempotent. |
| Database → broker | Transactional outbox + publisher retry | Message có thể publish nhiều lần; consumer cần idempotency. |
| Broker → HTTP/payment API | Idempotency key được API đích hỗ trợ hoặc workflow bền vững | Nếu API đích không hỗ trợ dedup, không thể tự bảo đảm exactly-once chỉ ở consumer. |

CRaC không thêm một distributed transaction vào các hệ thống này. Nó chỉ khôi phục process. Khi process image được restore, trạng thái broker/database có thể đã tiến xa hơn trạng thái object trong heap.

## 13. Không giữ delivery/session cũ qua restore

Các đối tượng client thường có trạng thái gắn với kết nối và phiên broker:

- Kafka consumer giữ network connection, group membership, generation, assignment, position và buffer record.
- RabbitMQ channel giữ delivery tag và channel sequence state.
- JMS session giữ acknowledgement/transaction state.
- SQS receipt handle đại diện cho một lần nhận cụ thể và có thể hết hiệu lực.

Các trạng thái đó do broker hoặc protocol quản lý. Khi checkpoint, hãy đóng/giải phóng client theo hướng dẫn của thư viện và tạo client/session/channel mới sau restore. Không tái sử dụng delivery tag, receipt handle hoặc session cũ như thể broker chưa thay đổi.

Nếu thư viện có CRaC integration chính thức, dùng lifecycle mà thư viện hỗ trợ. Nếu tự viết Resource, cần xác nhận cách đóng và tạo lại client an toàn, không gọi đồng thời callback của thư viện và callback custom làm cùng một việc hai lần.

## 14. Ví dụ Resource điều phối consumer qua CRaC

Ví dụ dưới đây dùng abstraction `MessageConsumerLifecycle` để thể hiện thứ tự. Nó không phụ thuộc một broker cụ thể:

```java
import org.crac.Context;
import org.crac.Resource;

public final class MessageConsumerCracResource implements Resource {
    private final MessageConsumerLifecycle consumer;
    private final ReadinessController readiness;

    public MessageConsumerCracResource(
            MessageConsumerLifecycle consumer,
            ReadinessController readiness) {
        this.consumer = consumer;
        this.readiness = readiness;
    }

    @Override
    public void beforeCheckpoint(Context<? extends Resource> context)
            throws Exception {
        readiness.refuseTraffic();
        consumer.stopReceivingNewMessages();

        if (!consumer.awaitInFlightToFinish()) {
            throw new IllegalStateException(
                    "Message handlers did not drain before checkpoint");
        }

        consumer.commitCompletedProgress();
        consumer.closeBrokerResources();
    }

    @Override
    public void afterRestore(Context<? extends Resource> context)
            throws Exception {
        consumer.createFreshBrokerResources();
        consumer.joinOrSubscribe();
        consumer.validateReady();
        readiness.acceptTraffic();
    }
}
```

Các method trên là abstraction của ứng dụng và phải có timeout/deadline hữu hạn. `commitCompletedProgress()` chỉ commit message đã hoàn tất và đã có kết quả nghiệp vụ bền vững. Message còn đang xử lý khi hết deadline phải được hủy an toàn và để broker giao lại; không đánh dấu hoàn tất chỉ để checkpoint tiếp tục.

Trong Kafka, `createFreshBrokerResources()` tạo consumer mới, `joinOrSubscribe()` subscribe và chờ assignment. Trong RabbitMQ, nó tạo connection/channel/consumer mới. Với JMS, tạo connection/session mới. Với SQS, tạo client mới và nhận message bằng receipt handle mới.

Nếu checkpoint bị abort sau khi `stopReceivingNewMessages()` đã chạy, process ban đầu cần rollback/resume consumer theo lifecycle coordinator. Không dựa vào `afterRestore` để khởi động lại consumer trong trường hợp checkpoint thất bại. Nếu không thể resume an toàn, giữ readiness ở trạng thái từ chối traffic và để orchestration xử lý instance.

## 15. Ví dụ Kafka consumer có kiểm soát offset

Ví dụ sau minh họa cấu hình tắt auto commit và chỉ commit sau khi business transaction thành công:

```java
Properties properties = new Properties();
properties.put(ConsumerConfig.ENABLE_AUTO_COMMIT_CONFIG, "false");
properties.put(ConsumerConfig.GROUP_ID_CONFIG, "orders-worker");

KafkaConsumer<String, OrderEvent> consumer = new KafkaConsumer<>(properties);
consumer.subscribe(List.of("orders"));

while (running) {
    ConsumerRecords<String, OrderEvent> records =
            consumer.poll(Duration.ofMillis(500));

    for (ConsumerRecord<String, OrderEvent> record : records) {
        processInDatabaseTransaction(record.value());

        TopicPartition partition =
                new TopicPartition(record.topic(), record.partition());
        OffsetAndMetadata next =
                new OffsetAndMetadata(record.offset() + 1);

        consumer.commitSync(Map.of(partition, next));
    }
}
```

Đây là consumer xử lý tuần tự minh họa. Trong ứng dụng thật, cần bổ sung shutdown flag, xử lý exception, timeout commit, close consumer trong `finally`, rebalance listener và quản lý nhiều record trên mỗi partition. Nếu dùng framework như Spring Kafka, để listener container quản lý consumer thread và offset policy; CRaC Resource nên dừng container bằng API lifecycle được hỗ trợ thay vì tự gọi consumer methods từ thread khác.

Không dùng `commitAsync()` rồi coi việc gọi method là bằng chứng offset đã được broker lưu. Nếu checkpoint cần chờ commit hoàn tất, hãy dùng cơ chế đồng bộ hoặc callback/flush có xác nhận và deadline rõ ràng. Cũng không commit offset của record chưa hoàn tất chỉ vì muốn giảm redelivery.

## 16. Retry, dead-letter queue và attempt count

Checkpoint có thể làm một message chưa ack được giao lại. Lần giao lại không nhất thiết là lỗi producer; đó có thể là hành vi bình thường của at-least-once delivery.

Retry state nên được lưu ở nơi có thể khôi phục nhất quán:

- Broker delivery count/redelivery flag nếu broker cung cấp và semantics đủ dùng.
- Retry topic/queue với metadata attempt và next retry time.
- Database record quản lý workflow/retry state.
- Dead-letter queue (DLQ) cho message vượt quá chính sách retry.

Không chỉ giữ attempt counter trong biến local của consumer. Sau restore, counter trong heap có thể cũ hơn số lần broker đã giao message hoặc có thể không phản ánh retry từ consumer khác.

Retry phải có giới hạn, backoff và phân loại lỗi. Lỗi tạm thời như network timeout có thể retry; lỗi payload/schema không hợp lệ thường nên chuyển DLQ hoặc quarantine sau số lần thử xác định. Tránh retry đồng bộ vô hạn trong listener vì nó giữ message in-flight và có thể làm checkpoint drain không bao giờ hoàn tất.

## 17. Observability cho message processing và checkpoint

Để điều tra duplicate hoặc mất message, cần liên kết log/metric giữa process, broker và database bằng message id/correlation id.

Nên ghi nhận:

- Message id, topic/queue, partition và offset hoặc delivery tag/receipt metadata phù hợp.
- Consumer group, consumer instance id và assignment generation nếu broker cung cấp.
- Thời điểm receive, processing start/end, database commit và ack/offset commit.
- Checkpoint attempt id, thời điểm bắt đầu quiesce, số handler đang chạy và thời gian drain.
- Số message hoàn tất, chưa hoàn tất, bị cancel và được broker redeliver.
- Offset committed theo partition hoặc acknowledgement result theo broker.
- Số duplicate bị inbox/idempotency guard chặn.
- Retry count, DLQ count, rebalance và visibility timeout event.
- Readiness state trong lúc dừng consumer và sau restore.

Không ghi payload nhạy cảm hoặc credential vào log. Với metric, tránh dùng message id làm label vì cardinality có thể tăng không giới hạn; dùng counter/histogram tổng hợp và đưa message id vào structured log hoặc trace.

## 18. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể gặp | Hướng xử lý |
| --- | --- | --- |
| Message được xử lý hai lần sau restore | DB commit xong nhưng ack/offset chưa commit; broker redelivery | Dùng inbox/idempotency record cùng transaction nghiệp vụ. |
| Message bị mất sau checkpoint | Ack/offset commit trước khi business transaction commit | Đổi thứ tự: commit side effect bền vững trước rồi mới ack. |
| Kafka bỏ qua record chưa xử lý | Commit offset cao hơn contiguous completed offset khi xử lý song song | Track completion theo partition và chỉ commit offset liên tục đã hoàn tất. |
| Kafka consumer bị rebalance sau restore | Consumer ngừng poll/heartbeat trong thời gian checkpoint | Tạo consumer mới và rejoin group; không dùng assignment cũ. |
| RabbitMQ báo unknown delivery tag | Ack bằng tag của channel cũ hoặc channel đã đóng | Tạo channel mới và để broker redeliver delivery chưa ack. |
| SQS giao lại message khi handler vẫn chạy | Visibility timeout hết trước khi delete | Drain trước checkpoint hoặc quản lý visibility extension có giới hạn; handler vẫn phải idempotent. |
| Message được ack dù handler lỗi | Auto ack hoặc container ack policy không phù hợp | Chọn manual/transactional acknowledgement và xác nhận semantics framework. |
| Consumer drain không kết thúc | Handler block, retry vô hạn hoặc dependency không có timeout | Deadline tổng, timeout I/O và cancellation có kiểm soát. |
| Message cũ ghi đè trạng thái mới | Event xử lý out-of-order hoặc replay | Dùng version/sequence và quy tắc ordering theo aggregate. |
| Duplicate tạo thanh toán/gửi email hai lần | Side effect ngoài DB không có idempotency | Idempotency key ở hệ thống đích hoặc workflow/outbox bền vững. |

## 19. Kiểm thử redelivery và checkpoint–restore

Một kiểm thử tích hợp nên chủ động tạo checkpoint ở các ranh giới khác nhau:

1. **Trước khi handler bắt đầu:** nhận message hoặc chuẩn bị delivery rồi checkpoint; xác nhận sau restore broker giao message hợp lệ.
2. **Trong khi handler đang chạy:** giữ handler bằng latch, yêu cầu checkpoint và xác nhận quiesce/drain đợi hoặc hủy theo deadline.
3. **Sau business commit, trước ack:** mô phỏng dừng process; xác nhận message được giao lại nhưng inbox/idempotency chặn side effect lần hai.
4. **Sau ack/offset commit:** xác nhận message không được xử lý lại, trong khi business state đã bền vững.
5. **Lỗi trước business commit:** xác nhận message không bị ack và có thể retry.
6. **Kafka xử lý song song:** hoàn tất offset sau trước offset trước và xác nhận committed offset không vượt qua gap.
7. **Broker session thay đổi:** đóng channel/session/consumer trước checkpoint và xác nhận restore tạo kết nối/assignment mới.
8. **Visibility/session timeout:** để checkpoint lâu hơn timeout phù hợp và xác nhận redelivery được xử lý idempotently.
9. **Checkpoint bị abort:** xác nhận consumer được resume an toàn hoặc instance vẫn `NOT_READY`; không để listener dừng vĩnh viễn.
10. **DLQ/retry:** xác nhận delivery count và retry policy không bị reset sai bởi state trong heap.

Kiểm thử phải xác nhận kết quả ở cả ba nơi: database business state, broker offset/ack state và log/trace của ứng dụng. Chỉ thấy handler được gọi một lần trong log process không đủ chứng minh không có duplicate ở cấp nghiệp vụ.

## 20. Checklist triển khai

- [ ] Phân biệt offset, delivery tag, receipt handle và acknowledgement mode theo broker.
- [ ] Xác định rõ message nào đang được giao, đang xử lý, đã commit nghiệp vụ và đã ack.
- [ ] Tắt auto commit nếu cần tự kiểm soát thời điểm commit offset.
- [ ] Với Kafka song song, chỉ commit contiguous completed offset cho từng partition.
- [ ] Không ack/commit trước khi side effect bền vững hoàn tất.
- [ ] Dùng inbox/deduplication hoặc idempotency key cho consumer có side effect.
- [ ] Dừng nhận message mới và drain handler trước checkpoint.
- [ ] Message chưa hoàn tất khi hết deadline được hủy an toàn và để broker redeliver.
- [ ] Đóng consumer/channel/session trước checkpoint theo API thư viện.
- [ ] Sau restore, tạo client/session mới và rejoin/re-subscribe broker.
- [ ] Không tái sử dụng delivery tag, receipt handle hoặc assignment cũ.
- [ ] Dùng outbox/inbox khi phối hợp database và message broker.
- [ ] Retry có giới hạn, backoff và DLQ; không giữ attempt state chỉ trong heap.
- [ ] Readiness từ chối traffic cho tới khi consumer và dependency sẵn sàng.
- [ ] Có log/metric cho processing, DB commit, ack/offset commit, redelivery và duplicate.
- [ ] Kiểm thử checkpoint tại các cửa sổ trước/sau commit và ack.

## 21. Kết luận

Thông điệp đang xử lý, offset và acknowledgement thuộc các hệ thống có vòng đời khác nhau. CRaC khôi phục trạng thái process, nhưng broker vẫn quản lý delivery, committed offset, channel/session và visibility timeout theo trạng thái của chính nó. Checkpoint giữa lúc xử lý có thể khiến message được giao lại; nếu database đã commit nhưng broker chưa ack, handler sẽ gặp duplicate. Nếu ack trước khi database commit, message có thể bị mất.

Hãy dừng nhận message mới, drain handler và hoàn tất transaction trước checkpoint; commit offset/ack chỉ sau khi side effect đã bền vững; đóng client/session cũ và tạo lại sau restore. Dùng inbox/idempotency để xử lý redelivery, outbox cho sự kiện phát từ database, và tuân thủ contiguous offset khi xử lý Kafka song song. Khi các ranh giới này được quản lý rõ ràng, CRaC có thể rút ngắn thời gian phục hồi process mà không làm suy yếu semantics giao nhận message.
