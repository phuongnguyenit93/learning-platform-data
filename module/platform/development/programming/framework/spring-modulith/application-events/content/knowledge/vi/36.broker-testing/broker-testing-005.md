# Kiểm thử acknowledgement

*Xác nhận broker chỉ giải phóng message hoặc tiến offset sau khi consumer xử lý theo đúng chính sách*

Khi application event được externalize từ Spring Modulith sang RabbitMQ hoặc Kafka, producer gửi message và consumer nhận message ở hai tiến trình độc lập. Consumer cần thông báo cho broker rằng message đã được xử lý đến mức nào. Với RabbitMQ, cơ chế này là acknowledgement (ACK), negative acknowledgement (NACK) hoặc reject. Với Kafka, consumer ghi nhận tiến độ bằng cách commit offset của partition. Kiểm thử acknowledgement xác nhận message không bị xác nhận quá sớm, lỗi có thể được giao lại và tiến độ chỉ tiến lên theo đúng hợp đồng.

ACK là ranh giới quan trọng giữa việc nhận message và việc hoàn tất side effect. Nếu ACK trước khi dữ liệu nghiệp vụ được commit, ứng dụng có thể mất message khi tiến trình dừng. Nếu xử lý thành công nhưng ACK bị mất, broker có thể giao lại message. Vì vậy, consumer vẫn cần idempotency ngay cả khi acknowledgement được cấu hình đúng.

## 1. Phân biệt các loại acknowledgement

Không có một cơ chế ACK chung cho mọi broker. Trước khi viết test, cần xác định chính xác đang kiểm tra xác nhận ở phía producer, consumer hay tiến độ đọc:

| Cơ chế | Phía | Ý nghĩa |
|---|---|---|
| Publisher confirm (RabbitMQ) | Producer | Broker xác nhận đã xử lý publish theo giao thức confirm |
| Publisher return (RabbitMQ) | Producer | Thông báo message `mandatory` không được route đến queue nào |
| Consumer ACK (RabbitMQ) | Consumer | Consumer xác nhận một hoặc nhiều delivery đã xử lý |
| Consumer NACK/reject (RabbitMQ) | Consumer | Consumer từ chối delivery; có thể requeue hoặc dead-letter tùy cờ và cấu hình |
| Offset commit (Kafka) | Consumer | Ghi nhận vị trí tiếp theo cần đọc cho một partition và consumer group |

Publisher confirm không chứng minh consumer đã xử lý message. Consumer ACK không chứng minh side effect ở một dịch vụ bên ngoài đã hoàn tất nếu handler xác nhận quá sớm. Kafka offset commit cũng không phải ACK cho từng record theo giao thức RabbitMQ; nó ghi nhận tiến độ đọc của consumer group.

## 2. Xác định hợp đồng acknowledgement của consumer

Trước khi kiểm thử, viết rõ điều kiện nào cho phép consumer xác nhận message:

- Dữ liệu nghiệp vụ đã được ghi bền vững chưa?
- Transaction database đã commit trước ACK chưa?
- Lỗi tạm thời có được retry hoặc requeue không?
- Lỗi vĩnh viễn có được chuyển đến dead-letter destination không?
- Một batch có được xác nhận toàn bộ khi chỉ một record thành công không?
- Khi tiến trình dừng giữa xử lý và ACK, message sẽ được giao lại như thế nào?
- Nếu ACK đã gửi nhưng phản hồi bị mất, consumer có chịu được duplicate không?

Với listener cập nhật read model trong cùng database, một quy tắc an toàn phổ biến là commit transaction cập nhật projection trước khi xác nhận delivery. Với side effect bên ngoài, cần idempotency key hoặc trạng thái đối soát vì ACK không thể tạo transaction nguyên tử với API từ xa.

## 3. RabbitMQ: ACK, NACK và reject

RabbitMQ giao message đến consumer với delivery tag gắn với channel. Consumer có thể:

- `basicAck`: xác nhận message đã xử lý.
- `basicNack`: từ chối một hoặc nhiều delivery; có thể chọn requeue.
- `basicReject`: từ chối một delivery; có thể chọn requeue.

Nếu `requeue=false`, message bị từ chối có thể được dead-letter nếu queue có cấu hình dead-letter exchange; nếu không có DLX, message có thể bị loại bỏ. Nếu `requeue=true`, message được đưa lại queue và có thể được giao lại ngay. Requeue liên tục khi dependency vẫn lỗi có thể tạo vòng lặp nóng.

`deliveryTag` chỉ có ý nghĩa trong channel đã nhận message và phải được ACK/NACK trên chính channel đó. Cờ `multiple=true` áp dụng xác nhận hoặc từ chối cho các delivery chưa xác nhận đến delivery tag được chỉ định; dùng sai có thể xác nhận nhầm message đang xử lý song song.

## 4. Kiểm thử ACK tự động trong Spring AMQP

Spring AMQP có các chế độ acknowledgement của listener container:

| Chế độ | Hành vi khái quát | Điều cần kiểm thử |
|---|---|---|
| `NONE` | Broker tự xác nhận khi giao message theo chế độ auto-ack của giao thức | Message không còn được giữ để redelivery nếu consumer chết sau khi nhận |
| `AUTO` | Container ACK khi listener hoàn tất thành công; exception được xử lý theo error handler/retry configuration | Thành công thì ACK; lỗi đi theo retry/reject policy |
| `MANUAL` | Listener tự quyết định ACK/NACK/reject | ACK chỉ sau side effect; nhánh lỗi có quyết định rõ ràng |

`AUTO` là chế độ thường dùng khi listener trả về bình thường sau xử lý thành công và ném exception khi cần container xử lý lỗi. Cần kiểm tra cấu hình retry, requeue và dead-letter đi kèm; chỉ nhìn tên `AUTO` không đủ để biết message lỗi sẽ đi đâu.

Với `MANUAL`, listener hoặc thành phần xử lý phải gửi ACK/NACK rõ ràng. Nếu listener quên ACK, delivery có thể ở trạng thái unacknowledged và được giao lại khi channel đóng. Nếu ACK trước khi transaction commit, dữ liệu có thể mất tính nhất quán.

## 5. Ví dụ listener manual acknowledgement

Ví dụ dưới đây minh họa việc chỉ ACK sau khi service nghiệp vụ trả về thành công:

```java
import com.rabbitmq.client.Channel;
import org.springframework.amqp.core.Message;
import org.springframework.amqp.rabbit.listener.api.ChannelAwareMessageListener;
import org.springframework.stereotype.Component;

@Component
class PaymentMessageListener implements ChannelAwareMessageListener {

    private final PaymentHandler handler;

    PaymentMessageListener(PaymentHandler handler) {
        this.handler = handler;
    }

    @Override
    public void onMessage(Message message, Channel channel) throws Exception {
        long deliveryTag = message.getMessageProperties().getDeliveryTag();
        PaymentCaptured event = decode(message.getBody());

        try {
            handler.handle(event);
            channel.basicAck(deliveryTag, false);
        } catch (RetryablePaymentException ex) {
            channel.basicNack(deliveryTag, false, true);
        } catch (InvalidPaymentMessageException ex) {
            channel.basicReject(deliveryTag, false);
        }
    }
}
```

`decode` là hàm giải mã theo converter/hợp đồng của ứng dụng. Ví dụ minh họa phân nhánh lỗi; trong production cần cấu hình DLX cho message reject, tránh requeue tức thì không giới hạn và xử lý trường hợp chính thao tác ACK/NACK thất bại. Nếu `handler.handle` dùng transaction, phải bảo đảm transaction đã commit trước khi phương thức trả về và listener gửi ACK.

Không giữ channel hoặc delivery tag để ACK từ một thread tùy ý sau khi channel đã đóng. Nếu xử lý bất đồng bộ, cần dùng cơ chế container hỗ trợ asynchronous listener và acknowledgement tương ứng với phiên bản Spring AMQP; không tự chuyển delivery tag qua thread mà không kiểm soát vòng đời channel.

## 6. Kiểm thử RabbitMQ ACK khi xử lý thành công

Một integration test có thể khởi chạy RabbitMQ bằng Testcontainers, khai báo queue và gửi một message. Sau khi listener xử lý thành công, kiểm tra message không còn trong queue và side effect đã được ghi nhận.

```java
@Testcontainers
@SpringBootTest
class RabbitAcknowledgementTest {

    @Container
    static final RabbitMQContainer rabbit =
        new RabbitMQContainer("rabbitmq:3.13-management-alpine");

    @Autowired RabbitTemplate rabbitTemplate;
    @Autowired PaymentReadModelRepository readModels;

    @Test
    void acknowledgesMessageAfterSuccessfulProcessing() {
        UUID paymentId = UUID.randomUUID();
        rabbitTemplate.convertAndSend(
            "payments.events", "payments.captured",
            new PaymentCaptured(UUID.randomUUID(), paymentId, 2500)
        );

        await().atMost(Duration.ofSeconds(5)).untilAsserted(() ->
            assertThat(readModels.existsByPaymentId(paymentId)).isTrue()
        );

        assertThat(rabbitTemplate.receive("payments.capture", 200)).isNull();
    }
}
```

Queue, exchange, binding, DTO và cấu hình container là fixture của ứng dụng. Test dùng polling có timeout để chờ side effect; sau đó xác nhận message đã được ACK và không còn sẵn sàng trong queue. Không dùng `receive()` làm bằng chứng duy nhất: message có thể đã được consumer nhận nhưng vẫn unacknowledged. Khi cần kiểm tra chính xác trạng thái broker, kết hợp queue depth/management API hoặc test consumer chuyên dụng.

## 7. Kiểm thử NACK, requeue và dead-letter

Tạo các kịch bản riêng cho từng chính sách lỗi:

1. Listener gặp lỗi tạm thời và NACK với `requeue=true`; message có thể được giao lại.
2. Listener gặp lỗi dữ liệu vĩnh viễn và reject với `requeue=false`; message được route đến DLX nếu queue cấu hình DLX.
3. Retry có giới hạn; sau số lần thử quy định, message đi vào dead-letter queue.
4. Consumer bị dừng trước ACK; message unacknowledged được requeue khi channel/connection đóng.
5. Dependency phục hồi; message retry được xử lý và ACK thành công.

Không chỉ assert rằng message “xuất hiện lại” mà không kiểm tra số lần giao. Một cấu hình requeue tức thì có thể làm listener lặp vô hạn và khiến test treo. Dùng retry có backoff hoặc giới hạn số lần, đồng thời theo dõi redelivery metadata và dead-letter count.

## 8. Kiểm thử cửa sổ lỗi giữa commit và ACK

Đây là tình huống quan trọng nhất để kiểm chứng idempotency:

1. Consumer nhận message.
2. Handler cập nhật database và transaction commit.
3. Tiến trình dừng hoặc channel đóng trước khi ACK được broker ghi nhận.
4. RabbitMQ giao lại message.
5. Consumer nhận duplicate và phải không lặp side effect.

Test nên mô phỏng việc handler đã commit nhưng ACK không xảy ra, sau đó khởi động hoặc cho consumer nhận lại message. Xác nhận database chỉ có một kết quả nghiệp vụ, inbox chỉ ghi một event ID và lần giao lại được ACK sau khi handler nhận diện duplicate.

Không thể tạo transaction nguyên tử giữa database ứng dụng và ACK RabbitMQ chỉ bằng cách đặt `@Transactional` trên listener. Nếu dùng transaction synchronization hoặc channel transaction, cần hiểu rõ phạm vi và thứ tự commit; vẫn cần idempotency để bảo vệ các tình huống mất kết nối và kết quả không rõ ràng.

## 9. Publisher confirm khác consumer ACK

Khi test producer RabbitMQ, publisher confirm xác nhận broker đã xử lý publish theo giao thức confirm. Nếu producer dùng `mandatory`, publisher return giúp phát hiện message không route được đến queue. Hai tín hiệu này không chứng minh consumer đã xử lý message.

Một bộ test producer có thể kiểm tra:

- Broker confirm publish thành công.
- Broker trả lỗi hoặc confirm bị timeout.
- Message `mandatory` không có binding tạo publisher return.
- Message có binding đến đúng queue.
- Ứng dụng xử lý trường hợp confirm không rõ ràng mà không phát sinh side effect trùng ở consumer.

Khi Spring Modulith externalization adapter gửi event, cần xác định adapter hoàn tất publication theo thời điểm nào: sau khi gọi API publish, sau publisher confirm hay theo semantics riêng của integration. Event Publication Registry ghi nhận trạng thái của publication theo cơ chế adapter; không mặc định trạng thái `completed` có nghĩa consumer bên ngoài đã hoàn tất xử lý nghiệp vụ.

## 10. Kafka: offset commit là acknowledgement tiến độ

Kafka không dùng per-message consumer ACK giống RabbitMQ. Consumer đọc record từ partition và commit offset thể hiện vị trí tiếp theo cần đọc. Nếu consumer commit offset trước khi dữ liệu nghiệp vụ bền vững, record có thể bị bỏ qua sau restart. Nếu dữ liệu đã commit nhưng offset chưa được commit, record có thể được đọc lại.

Với Spring Kafka, `AckMode` quyết định thời điểm container commit offset:

| AckMode | Hành vi khái quát |
|---|---|
| `RECORD` | Commit sau khi listener xử lý từng record thành công |
| `BATCH` | Commit sau khi tất cả record trong batch poll được xử lý thành công |
| `TIME` / `COUNT` / `COUNT_TIME` | Commit theo điều kiện thời gian, số record hoặc kết hợp |
| `MANUAL` | Listener gọi `Acknowledgment.acknowledge()`; container commit theo semantics của mode |
| `MANUAL_IMMEDIATE` | Yêu cầu commit ngay khi acknowledge trên consumer thread; hành vi cần được xác nhận theo cấu hình/version |

Tên và chi tiết hỗ trợ có thể khác theo phiên bản Spring Kafka. Kiểm tra tài liệu phiên bản dự án và cấu hình `enable.auto.commit`, error handler, transaction và concurrency trước khi viết assertion.

## 11. Kiểm thử Kafka offset và redelivery

Với Kafka, test nên xác nhận offset chỉ tiến sau khi xử lý thành công theo AckMode đã chọn. Có thể dùng Kafka Testcontainer hoặc môi trường broker tương thích, tạo topic riêng và consumer group riêng cho từng test.

Các tình huống:

- Listener xử lý thành công; offset của partition tiến đến vị trí kế tiếp.
- Listener ném exception; offset không tiến vượt qua record chưa xử lý nếu chính sách retry yêu cầu xử lý lại.
- Consumer dừng sau DB commit nhưng trước offset commit; record được đọc lại và consumer idempotent.
- Batch có một record lỗi; offset không vượt qua record chưa hoàn tất theo semantics của container/error handler.
- Rebalance xảy ra khi consumer đang xử lý; partition được giao lại và record chưa commit được xử lý an toàn.
- Consumer group khác đọc cùng topic độc lập; offset của group này không ảnh hưởng group kia.

Đọc offset đã commit bằng `AdminClient` hoặc API phù hợp và so sánh với vị trí mong đợi. Nhớ rằng offset commit thường là offset tiếp theo cần đọc, không phải số thứ tự record vừa xử lý. Test phải xét partition cụ thể, không lấy một offset đơn lẻ đại diện cho toàn topic.

## 12. Kiểm thử manual acknowledgement trong Spring Kafka

Với `MANUAL` hoặc `MANUAL_IMMEDIATE`, listener nhận `Acknowledgment` và quyết định khi nào xác nhận:

```java
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.kafka.support.Acknowledgment;
import org.springframework.stereotype.Component;

@Component
class PaymentKafkaListener {

    private final PaymentHandler handler;

    PaymentKafkaListener(PaymentHandler handler) {
        this.handler = handler;
    }

    @KafkaListener(
        topics = "payments.events",
        groupId = "payment-projection"
    )
    void on(PaymentCaptured event, Acknowledgment acknowledgment) {
        handler.handle(event);
        acknowledgment.acknowledge();
    }
}
```

Container factory cần được cấu hình AckMode tương ứng và auto commit phải được kiểm soát theo hướng dẫn Spring Kafka. Nếu `handler.handle` ném exception, listener không gọi acknowledge; error handler quyết định retry, seek hoặc dead-letter theo cấu hình. Nếu handler trả về trước khi transaction database commit, offset có thể được commit quá sớm; bảo đảm transaction hoàn tất trước khi acknowledge.

Với `MANUAL`, không giả định lệnh acknowledge luôn commit ngay tại dòng gọi; nó được xử lý theo semantics của container. Nếu cần kiểm tra commit tức thời, xem xét `MANUAL_IMMEDIATE` và thực thi trên consumer thread theo tài liệu phiên bản đang dùng.

## 13. Kiểm thử batch và thứ tự acknowledgement

Khi một poll trả nhiều record, commit offset của partition có thể xác nhận tiến độ qua một dải record. Nếu record ở offset 12 lỗi nhưng consumer đã xử lý offset 13 và commit 14, lần khởi động lại có thể bỏ qua record 12. Vì vậy, chỉ commit offset liên tục đã xử lý thành công trong từng partition.

Với RabbitMQ, `basicAck(deliveryTag, multiple=true)` cũng có thể xác nhận tất cả delivery chưa ACK đến tag đó. Nếu consumer xử lý song song và message có thời gian hoàn tất khác nhau, xác nhận nhiều delivery dựa trên tag lớn nhất có thể ACK nhầm message nhỏ hơn vẫn đang chạy. Chỉ dùng multiple ACK khi thứ tự hoàn tất được kiểm soát.

Test batch nên cố ý làm một record/message ở giữa thất bại, xác nhận các record trước/sau không làm tiến checkpoint vượt qua vị trí lỗi và sau retry dữ liệu không bị mất hoặc lặp side effect.

## 14. Kết hợp acknowledgement với transaction và idempotency

ACK/offset commit và transaction database là hai cơ chế độc lập trong nhiều cấu hình phổ biến. Có thể xảy ra hai cửa sổ lỗi:

- **Database commit trước, ACK thất bại:** message được giao lại; handler phải phát hiện duplicate.
- **ACK/offset commit trước, database rollback:** broker nghĩ message đã xong nhưng dữ liệu nghiệp vụ chưa được ghi; có nguy cơ mất xử lý.

Quy tắc phổ biến là chỉ xác nhận sau khi side effect trong database đã commit. Kết hợp inbox table có unique constraint `(consumer_name, event_id)` và cập nhật read model trong cùng transaction. Nếu message được giao lại, inbox ngăn side effect lặp; handler có thể xác nhận duplicate an toàn.

Với side effect bên ngoài, truyền idempotency key ổn định đến API đích hoặc dùng outbox/process manager và đối soát. Không tuyên bố exactly-once end-to-end chỉ vì broker có ACK hoặc Kafka có offset commit.

## 15. Kiểm thử với Testcontainers và dữ liệu cô lập

Broker test cần dùng destination và consumer group riêng để tránh message tồn từ test khác. Testcontainers giúp kiểm tra broker thật trong pipeline:

- RabbitMQ: kiểm tra queue, exchange, binding, delivery tag, ACK/NACK, requeue, DLX, publisher confirm và return.
- Kafka: kiểm tra topic, partition, consumer group, offset commit, rebalance và redelivery.
- Consumer: dùng database test có transaction và unique constraint tương tự môi trường chạy.
- Cleanup: drain hoặc xóa destination do test sở hữu; không purge queue/topic dùng chung khi test chạy song song.

Dùng polling với timeout hữu hạn để chờ side effect hoặc offset commit. Không dùng `Thread.sleep` cố định làm bằng chứng ACK đã hoàn tất. Khi test cần kiểm tra message chưa bị ACK, quan sát trạng thái unacknowledged/queue hoặc offset commit; một lần `receive()` trả về `null` chưa đủ chứng minh không có delivery đang được consumer giữ.

## 16. Những điểm cần nhớ

- RabbitMQ consumer ACK/NACK và Kafka offset commit là hai semantics khác nhau.
- Publisher confirm không phải consumer ACK; publisher return chỉ báo message không route được khi dùng mandatory.
- Với RabbitMQ, kiểm thử `AUTO` và `MANUAL`, ACK/NACK/reject, requeue, redelivery và DLX.
- Với Kafka, kiểm thử AckMode, offset theo partition, batch, retry và rebalance.
- Chỉ xác nhận sau khi side effect cần bảo vệ đã bền vững; xử lý duplicate bằng idempotency.
- Kiểm thử cửa sổ lỗi giữa database commit và ACK/offset commit.
- Event Publication Registry theo dõi publication phía Spring Modulith; không mặc định nó chứng minh consumer ngoài đã hoàn tất nghiệp vụ.
- Dùng broker thật/Testcontainers, destination cô lập và assertion có timeout để tránh test sai hoặc chập chờn.

Khi acknowledgement được kiểm thử theo đúng semantics của từng broker, transaction được hoàn tất trước khi xác nhận và consumer chịu được redelivery, ứng dụng có thể phục hồi sau lỗi mà không âm thầm bỏ message hoặc nhân đôi side effect. Kết hợp kiểm thử ACK với Event Publication Registry, retry và idempotency giúp externalization trong Spring Modulith đáng tin cậy hơn.
