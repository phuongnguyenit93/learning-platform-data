# Thứ tự khi có nhiều consumer, giao lại hoặc ưu tiên khác nhau

Trong JMS, thứ tự gửi message không đồng nghĩa với thứ tự xử lý hoàn tất ở consumer. Khi một queue có nhiều consumer, khi message bị rollback và giao lại, hoặc khi producer gửi các mức ưu tiên khác nhau, thứ tự quan sát được có thể thay đổi.

Muốn thiết kế luồng đáng tin cậy, cần phân biệt ba khái niệm:

- **Thứ tự nhận (delivery/receipt order):** consumer nhận message theo thứ tự nào.
- **Thứ tự xử lý (processing order):** listener bắt đầu xử lý message theo thứ tự nào.
- **Thứ tự hoàn tất (completion order):** nghiệp vụ xử lý xong theo thứ tự nào.

Jakarta Messaging quy định một số ràng buộc thứ tự, nhưng không bảo đảm một thứ tự toàn cục cho mọi producer, consumer và tình huống lỗi. Spring JMS cũng cảnh báo rằng tăng số consumer làm mất các bảo đảm thứ tự. Nếu nghiệp vụ cần xử lý tuần tự theo đơn hàng, tài khoản hoặc aggregate, phải chọn concurrency, transaction, message grouping và kiểm tra sequence phù hợp.

## 1. Những bảo đảm thứ tự cơ bản của Jakarta Messaging

JMS định nghĩa thứ tự theo từng Session và Destination, không phải một hàng đợi thứ tự toàn cục cho mọi ứng dụng.

### Thứ tự gửi trong cùng Session

Theo Jakarta Messaging 3.1, các message mà **một Session gửi tới cùng một Destination** phải được nhận theo thứ tự gửi, với một số ngoại lệ được đặc tả.

Ví dụ cùng Session gửi:

~~~text
Session S1 -> orders.queue:
    M1
    M2
    M3
~~~

Khi các điều kiện thứ tự được giữ, consumer nhận M1 trước M2 rồi M3. Đây là ràng buộc thứ tự một phần: nó không xác định thứ tự giữa các Destination khác nhau hoặc giữa message được gửi từ nhiều Session.

### Nhiều Session hoặc nhiều producer

Nếu hai Session cùng gửi tới một queue:

~~~text
Session S1 -> orders.queue: A1, A2
Session S2 -> orders.queue: B1, B2
~~~

JMS không quy định một thứ tự tổng hợp như A1, B1, A2, B2. Thứ tự phụ thuộc thời điểm gửi, provider, broker và việc các message đến Destination. Mỗi Session có thứ tự riêng theo các quy tắc JMS; ứng dụng không được giả định rằng các Session khác nhau tạo thành một chuỗi FIFO chung.

Nếu thứ tự nghiệp vụ phụ thuộc vào một producer duy nhất, hãy dùng cùng một Session cho các lần gửi liên quan hoặc thêm sequence number ở cấp ứng dụng để consumer kiểm tra.

### Các ngoại lệ ảnh hưởng thứ tự gửi

Ngay cả khi dùng cùng Session và Destination, các yếu tố sau có thể làm thứ tự quan sát được khác với thứ tự gọi send:

1. Message có priority cao hơn có thể vượt lên trước message priority thấp hơn đã gửi trước đó.
2. Message có delivery time muộn hơn chỉ được phép xuất hiện sau khi đến thời điểm giao; message khác có thể được giao trước trong lúc chờ.
3. Nếu trộn PERSISTENT và NON_PERSISTENT, thứ tự chỉ được bảo đảm trong từng delivery mode. Một message NON_PERSISTENT gửi sau có thể đến trước message PERSISTENT gửi trước.
4. Provider failure có thể làm mất message NON_PERSISTENT.
5. Thứ tự gửi trong một transaction tới cùng Destination có ý nghĩa; thứ tự gửi qua nhiều Destination trong cùng transaction không được xác định.

Vì vậy, khi cần FIFO, cần kiểm soát cả Session, Destination, priority, delivery mode và delivery delay.

## 2. Nhiều consumer trên cùng queue

Một queue có thể có nhiều consumer. Mỗi message trong queue được giao cho một consumer; Jakarta Messaging không quy định chính xác broker phải phân phối message giữa các consumer như thế nào.

Ví dụ:

~~~text
orders.queue
    |
    +---- Consumer A
    |
    +---- Consumer B
    |
    +---- Consumer C
~~~

Broker có thể phân phối message giữa các consumer để tăng throughput. Một consumer có thể nhận M1 rồi M3; consumer khác nhận M2 rồi M4. Mỗi consumer có thứ tự nhận riêng theo các quy tắc JMS, nhưng không có thứ tự hoàn tất toàn cục giữa A, B và C.

Ví dụ:

| Message | Consumer | Thời gian xử lý | Thứ tự hoàn tất |
|---|---|---:|---:|
| M1 | A | 900 ms | 2 |
| M2 | B | 100 ms | 1 |
| M3 | A | 200 ms | 3 |

Mặc dù M1 được giao trước M2, B có thể xử lý M2 xong trước A hoàn tất M1. Nếu hai message cập nhật cùng một đơn hàng, thứ tự hoàn tất có thể làm trạng thái nghiệp vụ sai.

### Thứ tự nhận khác thứ tự hoàn tất

Một Session chỉ được sử dụng tuần tự theo quy tắc threading của JMS. Session cũng tuần tự hóa việc gọi các listener bất đồng bộ gắn với Session đó. Muốn xử lý đồng thời, ứng dụng tạo nhiều Session; listener trên các Session khác nhau có thể chạy song song.

Spring **DefaultMessageListenerContainer** dùng các Session và MessageConsumer riêng cho các listener worker. Khi tăng concurrency, nhiều method listener có thể xử lý cùng lúc. Spring ghi rõ rằng khi đăng ký nhiều consumer, các bảo đảm thứ tự bị mất.

### Spring JMS: cấu hình concurrency

Với **DefaultJmsListenerContainerFactory**, có thể đặt concurrency:

~~~java
@Configuration
@EnableJms
public class JmsConfiguration {

    @Bean
    public DefaultJmsListenerContainerFactory orderedQueueFactory(
            ConnectionFactory connectionFactory
    ) {
        DefaultJmsListenerContainerFactory factory =
                new DefaultJmsListenerContainerFactory();

        factory.setConnectionFactory(connectionFactory);

        // Một consumer/session cho queue cần xử lý tuần tự.
        factory.setConcurrency("1");

        // Listener exception làm rollback local JMS transaction.
        factory.setSessionTransacted(true);

        return factory;
    }
}
~~~

Listener sử dụng factory đó:

~~~java
@Component
public class OrderListener {

    @JmsListener(
            destination = "orders.queue",
            containerFactory = "orderedQueueFactory"
    )
    public void handle(String event) {
        orderService.apply(event);
    }
}
~~~

Có thể đặt concurrency trực tiếp trên **@JmsListener**:

~~~java
@JmsListener(
        destination = "orders.queue",
        concurrency = "1",
        containerFactory = "orderedQueueFactory"
)
public void handle(String event) {
    orderService.apply(event);
}
~~~

**concurrency = "1"** giữ một consumer cho endpoint. Cấu hình **"3-10"** cho phép từ ba đến mười consumer tùy container; cách này tăng khả năng xử lý song song nhưng không còn bảo đảm thứ tự xử lý toàn cục trên queue.

**Lưu ý:** **sessionTransacted=true** tạo local JMS transaction cho Session. Nó không tự đưa thao tác database vào cùng transaction. Nếu listener cập nhật database và cần atomicity giữa database với việc acknowledge message, cần thiết kế JTA/XA hoặc transactional outbox phù hợp.

## 3. Nhiều consumer nhưng vẫn cần thứ tự theo từng nghiệp vụ

Không phải lúc nào ứng dụng cũng cần một thứ tự duy nhất cho toàn queue. Thường chỉ cần các message thuộc cùng một aggregate được xử lý tuần tự, còn các aggregate khác có thể chạy song song.

Ví dụ:

- Các thay đổi của **order-1001** phải theo sequence 1, 2, 3.
- Các thay đổi của **order-2002** cũng phải theo sequence 1, 2, 3.
- Hai đơn hàng khác nhau có thể xử lý đồng thời.

Đây là trường hợp phù hợp với **message grouping** nếu broker hỗ trợ.

### JMSXGroupID và JMSXGroupSeq

Jakarta Messaging định nghĩa hai property chuẩn:

- **JMSXGroupID**: String xác định message thuộc group nào.
- **JMSXGroupSeq**: số thứ tự của message trong group; giá trị đầu tiên là 1, tiếp theo là 2, v.v.

Các property này là một phần của Jakarta Messaging và provider phải hỗ trợ. Tuy nhiên, cách broker gán group cho consumer, giữ group khi consumer lỗi và bảo toàn thứ tự xử lý cần được kiểm tra theo tài liệu provider.

Ví dụ producer gửi các bước của một đơn hàng:

~~~java
public void publishOrderStep(
        String orderId,
        int sequence,
        String payload
) {
    jmsTemplate.execute("orders.queue", (session, producer) -> {
        TextMessage message = session.createTextMessage(payload);

        message.setStringProperty("JMSXGroupID", orderId);
        message.setIntProperty("JMSXGroupSeq", sequence);

        producer.send(
                message,
                DeliveryMode.PERSISTENT,
                4,
                0L
        );

        return null;
    });
}
~~~

Ở đây:

- **orderId** là group ID, ví dụ **order-1001**.
- **sequence** là số thứ tự nghiệp vụ trong group.
- Tất cả message của cùng một đơn hàng dùng cùng JMSXGroupID.
- Priority được giữ cố định ở mức 4 để tránh priority làm thay đổi thứ tự.
- Delivery mode được giữ PERSISTENT và không đặt delivery delay trong ví dụ.

### Message group hoạt động ra sao?

Các broker như ActiveMQ Artemis và ActiveMQ Classic hỗ trợ message grouping: message cùng JMSXGroupID được ghim vào một consumer trong khi group còn được gán cho consumer đó; group khác có thể được phân phối sang consumer khác.

~~~text
orders.queue
    |
    +---- group order-1001 ----> Consumer A
    |          seq 1
    |          seq 2
    |          seq 3
    |
    +---- group order-2002 ----> Consumer B
               seq 1
               seq 2
               seq 3
~~~

Cách này cho phép song song giữa các group, đồng thời giữ một luồng xử lý cho từng group theo cơ chế broker hỗ trợ.

Không nên suy ra rằng chỉ cần đặt JMSXGroupID thì mọi broker sẽ có cùng hành vi pinning và failover. Hãy xác minh tài liệu provider, cấu hình group, chính sách prefetch, consumer failover và xử lý redelivery.

### Group ID nên đại diện cho aggregate nào?

Chọn một khóa mà các thao tác cần tuần tự cùng chia sẻ:

| Nghiệp vụ | Group ID gợi ý |
|---|---|
| Các thay đổi của một đơn hàng | orderId |
| Các giao dịch trên một tài khoản | accountId |
| Các sự kiện của một thiết bị | deviceId |
| Các thay đổi của một hồ sơ | customerId |

Không dùng một group ID duy nhất cho toàn bộ queue nếu muốn tận dụng nhiều consumer; làm vậy sẽ dồn mọi message vào cùng một group và gần như triệt tiêu concurrency.

Cũng không tạo group ID ngẫu nhiên cho từng message nếu mục tiêu là giữ thứ tự theo aggregate. Các message liên quan phải dùng cùng một khóa ổn định.

## 4. Sequence number ở cấp ứng dụng

JMSXGroupSeq giúp mô tả thứ tự trong group, nhưng ứng dụng nên có sequence number nghiệp vụ riêng nếu việc đúng thứ tự là yêu cầu quan trọng.

Ví dụ payload:

~~~json
{
  "eventId": "evt-901",
  "aggregateId": "order-1001",
  "sequence": 12,
  "eventType": "OrderPaid"
}
~~~

Consumer lưu sequence cuối cùng đã áp dụng cho aggregate. Khi nhận event:

- **sequence == lastSequence + 1**: có thể xử lý tiếp.
- **sequence <= lastSequence**: event đã xử lý hoặc đã cũ; kiểm tra eventId để phân biệt duplicate.
- **sequence > lastSequence + 1**: đang thiếu event trước đó; tạm hoãn, lưu buffer hoặc yêu cầu reconciliation.

Ví dụ logic:

~~~java
public void apply(OrderEvent event) {
    long lastSequence = repository.lastAppliedSequence(event.aggregateId());

    if (event.sequence() <= lastSequence) {
        // Duplicate hoặc event cũ: không áp dụng lại side effect.
        return;
    }

    if (event.sequence() != lastSequence + 1) {
        throw new OutOfOrderEventException(
                "Expected " + (lastSequence + 1)
                        + " but received " + event.sequence()
        );
    }

    repository.applyAndAdvanceSequence(event);
}
~~~

**applyAndAdvanceSequence** nên cập nhật dữ liệu nghiệp vụ và sequence trong cùng database transaction. Nếu nhiều consumer có thể cùng xử lý một aggregate, cần khóa hàng, optimistic locking hoặc một cơ chế serialization tương đương để tránh hai thread cùng đọc một lastSequence rồi cùng ghi.

Sequence number không tự sắp xếp message trong broker. Nó giúp phát hiện message đến sai thứ tự và ngăn consumer âm thầm áp dụng sai trạng thái.

## 5. Redelivery: khi message được giao lại

Redelivery xảy ra khi consumer đã nhận message nhưng message chưa được xác nhận thành công, hoặc transaction bị rollback/recover. Broker có thể giao lại message để xử lý tiếp.

Một số nguyên nhân thường gặp:

- Listener ném exception trong transaction.
- Session transacted bị rollback.
- Ứng dụng gọi **Session.recover()** trong chế độ acknowledgment phù hợp.
- Process hoặc kết nối bị lỗi trước khi acknowledgement được hoàn tất.
- Transaction timeout hoặc broker phát hiện consumer mất kết nối.

### Redelivery có thể ảnh hưởng thứ tự

Giả sử queue có:

~~~text
M1 -> M2 -> M3
~~~

Consumer nhận M1 nhưng xử lý lỗi. Sau rollback, M1 được giao lại. Trong thời gian đó, có thể có message priority cao hơn, message vừa đến delivery time hoặc message khác được giao cho consumer khác.

Jakarta Messaging quy định **Session.recover()** khởi động lại luồng từ message chưa được acknowledge đầu tiên. Tuy nhiên, các message được giao sau recover có thể khác với chuỗi ban đầu do message hết hạn, message priority cao hơn đến hoặc message delayed delivery vừa đủ điều kiện được giao.

Vì vậy, không nên giả định rằng sau redelivery, toàn bộ message sẽ xuất hiện lại trong cùng một chuỗi thứ tự như trước lỗi.

### JMSRedelivered và JMSXDeliveryCount

Consumer có thể kiểm tra hai metadata này:

- **JMSRedelivered**: boolean cho biết provider đang giao lại message.
- **JMSXDeliveryCount**: số lần provider đã giao message. Lần nhận đầu có giá trị 1; giá trị 2 trở lên cho biết message đã được redeliver.

Ví dụ:

~~~java
@JmsListener(destination = "orders.queue")
public void inspect(Message message) throws JMSException {
    boolean redelivered = message.getJMSRedelivered();
    int deliveryCount = message.getIntProperty("JMSXDeliveryCount");

    log.info(
            "messageId={}, redelivered={}, deliveryCount={}",
            message.getJMSMessageID(),
            redelivered,
            deliveryCount
    );
}
~~~

**JMSXDeliveryCount** hữu ích để quan sát số lần giao và phát hiện poison message, nhưng provider không bắt buộc bảo đảm giá trị luôn chính xác tuyệt đối sau mọi sự cố vì không nhất thiết phải persist bộ đếm này. Không dùng delivery count làm định danh duy nhất của nghiệp vụ.

### Redelivery và acknowledgment mode

| Chế độ | Hành vi liên quan đến xác nhận |
|---|---|
| **AUTO_ACKNOWLEDGE** | Provider tự acknowledge sau khi receive trả về thành công hoặc listener xử lý thành công theo semantics JMS. |
| **CLIENT_ACKNOWLEDGE** | Gọi acknowledge() trên một message sẽ acknowledge tất cả message đã được giao trong Session đó. recover() có thể yêu cầu giao lại các message chưa xác nhận. |
| **Transacted Session** | commit() xác nhận các message đã nhận và gửi các message đầu ra; rollback() phục hồi message đầu vào và hủy message đầu ra trong transaction. |

Trong Spring **DefaultMessageListenerContainer**, chế độ **AUTO_ACKNOWLEDGE** mặc định có thể acknowledge trước khi listener chạy; exception từ listener không tạo redelivery trong cấu hình mặc định đó. Khi cần retry dựa trên lỗi listener, nên cấu hình **sessionTransacted=true** hoặc một external transaction manager phù hợp.

Ví dụ factory local JMS transaction:

~~~java
@Bean
public DefaultJmsListenerContainerFactory reliableFactory(
        ConnectionFactory connectionFactory
) {
    DefaultJmsListenerContainerFactory factory =
            new DefaultJmsListenerContainerFactory();

    factory.setConnectionFactory(connectionFactory);
    factory.setConcurrency("1");
    factory.setSessionTransacted(true);

    return factory;
}
~~~

Khi listener ném exception, Spring container có thể rollback Session transaction. Provider sau đó quyết định redelivery theo chính sách cấu hình. Nếu dùng JTA transaction, cấu hình transaction manager bên ngoài thay vì tự commit/rollback Session.

## 6. Poison message, retry và Dead Letter Queue

Một message lỗi lặp lại có thể trở thành **poison message**. Ví dụ, JSON sai schema hoặc một giá trị nghiệp vụ luôn khiến listener ném exception. Nếu cứ rollback vô hạn, message có thể được giao đi giao lại và tiêu tốn tài nguyên.

Một chính sách thường dùng:

~~~text
Receive
   |
   v
Process
   |
   +---- success ----> Commit / acknowledge
   |
   +---- transient error
   |          |
   |          v
   |      Retry with backoff
   |          |
   |          +---- retry limit reached
   |                       |
   |                       v
   |                 Dead Letter Queue
   |
   +---- permanent error
              |
              v
        Quarantine / DLQ
~~~

Các yếu tố cần cấu hình:

- Số lần redelivery tối đa.
- Khoảng chờ giữa các lần retry hoặc exponential backoff.
- Queue đích cho message hết số lần retry.
- Cách giữ original destination, exception cause và correlation ID.
- Cách cảnh báo và replay sau khi sửa lỗi.
- Chính sách xử lý message đến sai thứ tự khi một event trong group bị đưa vào DLQ.

Giới hạn redelivery, delay, dead-letter address và cách giữ thứ tự khi chuyển DLQ là tính năng phụ thuộc provider. Jakarta Messaging không định nghĩa một cấu hình DLQ thống nhất cho mọi broker.

Nếu bỏ qua một message trong chuỗi nghiệp vụ, các message sau có thể không còn hợp lệ. Ví dụ event sequence 12 thất bại và bị chuyển DLQ, event sequence 13 không nên tự động cập nhật trạng thái nếu ứng dụng yêu cầu đủ sequence. Consumer cần giữ trạng thái thiếu event, tạm dừng aggregate đó hoặc thực hiện reconciliation.

## 7. Priority: message có mức ưu tiên khác nhau

JMS định nghĩa header **JMSPriority** với mười mức:

| Priority | Ý nghĩa |
|---:|---|
| 0 | Thấp nhất |
| 1–4 | Các mức bình thường |
| 5–9 | Các mức ưu tiên cao (expedited) |

Giá trị mặc định thường là 4. Jakarta Messaging không yêu cầu provider thực hiện strict priority ordering; provider nên cố gắng giao message expedited (5–9) trước message normal (0–4).

Điều này có nghĩa message priority cao có thể vượt qua message priority thấp đã được gửi trước đó. Priority là một gợi ý scheduling của provider, không phải công cụ để đảm bảo thứ tự nghiệp vụ.

### Đặt priority khi gửi

Với Jakarta Messaging, có thể đặt priority qua overload **MessageProducer.send(...)**:

~~~java
producer.send(
        message,
        DeliveryMode.PERSISTENT,
        8,
        60_000L
);
~~~

Ở đây:

- **PERSISTENT**: delivery mode.
- **8**: priority cao.
- **60_000L**: time-to-live 60 giây.

Không đặt JMSPriority bằng setter trên Message. Provider gán header này dựa trên tham số send hoặc cấu hình producer.

Với Spring **JmsTemplate**, có thể dùng ProducerCallback để đặt QoS riêng cho từng message:

~~~java
jmsTemplate.execute("alerts.queue", (session, producer) -> {
    TextMessage message = session.createTextMessage("Critical alert");
    producer.send(
            message,
            DeliveryMode.PERSISTENT,
            9,
            30_000L
    );
    return null;
});
~~~

Nếu chỉ cần một mức priority chung, JmsTemplate cũng có thể cấu hình delivery mode, priority và TTL; cần bật explicit QoS để template truyền các giá trị đã cấu hình.

### Priority ảnh hưởng FIFO thế nào?

Giả sử producer gửi cùng một queue:

~~~text
M1 priority=4
M2 priority=4
M3 priority=9
M4 priority=4
~~~

Provider có thể giao M3 trước M1/M2/M4 vì M3 thuộc nhóm expedited. Do đó, nếu M1–M4 là các bước cập nhật cùng một đơn hàng và phải theo sequence, không nên thay đổi priority giữa các bước.

Một số hệ thống có thể dùng priority để phân loại SLA, nhưng nếu message cần thứ tự nghiệp vụ thì nên:

- Giữ priority đồng nhất trong cùng một aggregate/group.
- Dùng queue riêng cho luồng critical và normal nếu hai luồng có SLA khác nhau.
- Không dựa vào priority để thay thế sequence number.
- Kiểm tra hành vi thực tế của broker khi có backlog, nhiều consumer và message đang in-flight.

Priority cao kéo dài có thể khiến message priority thấp chờ lâu. Nếu cần fairness hoặc tránh starvation, phải thiết kế queue và chính sách scheduling phù hợp với broker.

## 8. Delivery delay, expiration và delivery mode cũng ảnh hưởng thứ tự

Ngoài priority, ba thuộc tính khác cần được xét cùng lúc.

### Delivery delay

JMS 2.0 trở lên cho phép producer chỉ định delivery delay. Message chưa được phép giao trước thời điểm delivery time.

Nếu M1 được gửi trước nhưng có delay 30 giây, còn M2 gửi sau không có delay, M2 có thể được giao trước M1. Khi dùng delay, thứ tự gửi không còn đồng nghĩa với thứ tự nhận.

### Time-to-live và expiration

Message có thể hết hạn trước khi consumer nhận được. Nếu sequence 10 hết hạn nhưng sequence 11 vẫn được giao, consumer thấy một khoảng trống sequence. Ứng dụng cần phát hiện và xử lý tình trạng thiếu event thay vì mặc định sequence 11 là hợp lệ.

### Persistent và non-persistent

Persistent delivery yêu cầu provider lưu message theo semantics persistent. Non-persistent có thể bị mất khi provider gặp sự cố.

Nếu trộn hai delivery mode trên cùng Destination, JMS chỉ bảo đảm thứ tự trong từng delivery mode. Một message NON_PERSISTENT gửi sau có thể được giao trước message PERSISTENT gửi trước. Nếu thứ tự nghiêm ngặt quan trọng, giữ delivery mode nhất quán.

## 9. Thiết kế theo yêu cầu thứ tự

| Yêu cầu | Thiết kế nên cân nhắc |
|---|---|
| FIFO cho toàn queue | Một producer Session theo thứ tự, một consumer/session, cùng priority, delivery mode và delivery delay. |
| Thứ tự cho từng đơn hàng nhưng nhiều đơn xử lý song song | Message grouping theo orderId, broker hỗ trợ group pinning và sequence number nghiệp vụ. |
| Throughput cao, thứ tự không quan trọng | Nhiều consumer/concurrency, xử lý idempotent. |
| Ưu tiên cảnh báo quan trọng | Priority hoặc queue riêng; không trộn với chuỗi event cần FIFO nghiêm ngặt. |
| Retry message lỗi | Transacted listener, redelivery policy có giới hạn, backoff và DLQ. |
| Không được bỏ sót sequence | Sequence number nghiệp vụ, lưu trạng thái cuối đã xử lý và cơ chế replay/reconciliation. |
| Nhiều producer gửi cùng aggregate | Partition theo aggregate hoặc serialize việc publish; không dựa vào thứ tự giữa các Session. |

### Một queue hay nhiều queue?

Nếu message thuộc các luồng nghiệp vụ độc lập, tách queue có thể giúp giảm ảnh hưởng giữa chúng. Ví dụ:

- **orders.critical**: cảnh báo hoặc lệnh khẩn cấp.
- **orders.normal**: sự kiện thông thường.
- **orders.retry**: message đang chờ retry nếu broker/provider hỗ trợ chính sách này.

Tách queue giúp mỗi luồng có consumer và QoS riêng, nhưng làm tăng số destination và cần quản lý thứ tự giữa các queue nếu chúng có quan hệ nghiệp vụ. Không chia queue theo priority nếu các message trong hai queue vẫn phải được xử lý theo cùng một sequence.

## 10. Ví dụ tổng hợp: xử lý theo từng orderId

Giả sử một queue xử lý event đơn hàng với nhiều consumer. Mỗi orderId là một group. Broker hỗ trợ JMS message grouping và gán cùng group cho cùng consumer. Consumer dùng transacted Session để rollback khi lỗi, đồng thời kiểm tra sequence nghiệp vụ.

### Producer

~~~java
public void publishOrderStep(
        String orderId,
        int sequence,
        String payload
) {
    jmsTemplate.execute("orders.queue", (session, producer) -> {
        TextMessage message = session.createTextMessage(payload);
        message.setStringProperty("JMSXGroupID", orderId);
        message.setIntProperty("JMSXGroupSeq", sequence);
        message.setStringProperty("eventId", UUID.randomUUID().toString());

        // Giữ priority/delivery mode giống nhau trong một group.
        producer.send(
                message,
                DeliveryMode.PERSISTENT,
                4,
                0L
        );

        return null;
    });
}
~~~

### Listener

~~~java
@Component
public class OrderEventListener {

    private final OrderService orderService;

    public OrderEventListener(OrderService orderService) {
        this.orderService = orderService;
    }

    @JmsListener(
            destination = "orders.queue",
            containerFactory = "groupedOrderFactory"
    )
    public void receive(TextMessage message) throws JMSException {
        String groupId = message.getStringProperty("JMSXGroupID");
        String eventId = message.getStringProperty("eventId");
        boolean redelivered = message.getJMSRedelivered();
        int deliveryCount = message.getIntProperty("JMSXDeliveryCount");

        orderService.applyInSequence(
                groupId,
                eventId,
                message.getText(),
                redelivered,
                deliveryCount
        );
    }
}
~~~

### Listener container

~~~java
@Bean
public DefaultJmsListenerContainerFactory groupedOrderFactory(
        ConnectionFactory connectionFactory
) {
    DefaultJmsListenerContainerFactory factory =
            new DefaultJmsListenerContainerFactory();

    factory.setConnectionFactory(connectionFactory);

    // Cho phép nhiều group xử lý song song.
    factory.setConcurrency("4-12");

    // Listener exception làm rollback message transaction.
    factory.setSessionTransacted(true);

    return factory;
}
~~~

Trong ví dụ, broker có thể phân phối các group khác nhau cho nhiều consumer, còn các event trong một group được xử lý theo semantics grouping của provider. **orderService.applyInSequence(...)** phải thực hiện kiểm tra sequence và cập nhật dữ liệu một cách nguyên tử trong database.

Đây là mã tích hợp Spring JMS cần ConnectionFactory, broker, queue và một JSON converter phù hợp nếu payload là JSON. Không có stdout cố định vì thứ tự và kết quả phụ thuộc message thực tế, consumer và provider. Nếu broker không hỗ trợ grouping semantics mong muốn, không dùng cấu hình concurrency này như một bảo đảm FIFO; hãy partition queue hoặc serialize xử lý theo aggregate.

## 11. Idempotency: redelivery không được tạo side effect lặp

Một message có thể được giao lại sau khi consumer đã thực hiện một phần công việc nhưng chưa acknowledge hoặc commit. Nếu consumer không idempotent, cùng một nghiệp vụ có thể chạy hai lần.

Không nên dùng **JMSMessageID** hoặc **JMSXDeliveryCount** làm khóa nghiệp vụ duy nhất:

- **JMSMessageID** định danh một message do provider gán.
- **JMSXDeliveryCount** chỉ phản ánh số lần giao, không định danh event.
- **eventId** hoặc business key ổn định do producer tạo mới phù hợp để deduplicate.

Một mẫu phổ biến là lưu eventId vào bảng inbox có unique constraint trong cùng transaction database với cập nhật nghiệp vụ. Nếu eventId đã tồn tại, consumer nhận diện duplicate và không áp dụng side effect lần nữa.

Khi JMS và database dùng hai transaction riêng, cần thiết kế rõ ranh giới commit/acknowledge. Nếu yêu cầu atomicity giữa database và việc consume JMS, cân nhắc JTA/XA; nếu không dùng XA, cần một chiến lược outbox/inbox, retry và reconciliation phù hợp.

## 12. Những lỗi thường gặp

1. **“Một queue luôn giao message theo FIFO toàn cục.”** Không đúng. Thứ tự được đặc tả theo Session/Destination và có ngoại lệ priority, delivery time, delivery mode.
2. **“Tăng concurrentConsumers chỉ tăng tốc mà không đổi thứ tự.”** Không đúng. Spring cảnh báo nhiều consumer làm mất bảo đảm thứ tự.
3. **“Mỗi consumer nhận mọi message.”** Không đúng với queue cạnh tranh; mỗi message chỉ được giao cho một consumer.
4. **“Thứ tự nhận chính là thứ tự hoàn tất.”** Không đúng khi nhiều consumer xử lý song song hoặc thời gian xử lý khác nhau.
5. **“Nhiều producer gửi cùng queue sẽ có một thứ tự tổng hợp.”** Không đúng. JMS không định nghĩa thứ tự nhận giữa các message được gửi từ nhiều Session.
6. **“Rollback chỉ gửi lại đúng message đó rồi mọi thứ tiếp tục cùng thứ tự.”** Không đúng. Recovery có thể thay đổi chuỗi nhận do message mới, priority, delay và expiration.
7. **“AUTO_ACKNOWLEDGE luôn redeliver khi listener ném exception trong Spring DMLC.”** Không đúng với cấu hình mặc định của DefaultMessageListenerContainer; acknowledgment có thể diễn ra trước listener execution. Dùng transacted session hoặc external transaction manager khi cần reliability.
8. **“JMSXDeliveryCount là số lần chính xác trong mọi tình huống.”** Không đúng. Giá trị có thể không chính xác tuyệt đối sau provider failure.
9. **“Chỉ cần JMSXGroupID là mọi broker bảo đảm group FIFO giống nhau.”** Không đúng. Property chuẩn có mặt trong JMS; cách pin group và failover cần kiểm tra theo provider.
10. **“Priority 9 luôn được xử lý trước priority 4 trong mọi tình huống.”** Không đúng. JMS không yêu cầu strict priority ordering; provider chỉ cần cố gắng ưu tiên expedited message.
11. **“Priority có thể dùng để đánh số sequence.”** Không đúng. Priority là scheduling hint; dùng sequence number nghiệp vụ để xác định thứ tự.
12. **“DLQ tự động giữ đúng thứ tự nghiệp vụ.”** Không nên giả định. Việc chuyển DLQ, retry và replay phụ thuộc broker; ứng dụng phải phát hiện sequence bị thiếu.
13. **“Một message bị redeliver chắc chắn chưa từng chạy nghiệp vụ.”** Không đúng. Consumer có thể đã thực hiện side effect trước khi lỗi hoặc mất acknowledgement; cần idempotency.
14. **“Session có thể dùng chung cho nhiều thread để tăng throughput.”** Không đúng. JMS Session được thiết kế cho sử dụng tuần tự; muốn concurrency, dùng nhiều Session/consumer.

## 13. Ghi nhớ

- JMS bảo đảm thứ tự gửi từ cùng Session tới cùng Destination trong phạm vi các ngoại lệ được đặc tả.
- Thứ tự giữa nhiều Session, nhiều producer hoặc nhiều Destination không được xác định toàn cục.
- Một queue có thể có nhiều consumer; phân phối message giữa chúng do provider quyết định.
- Spring **DefaultMessageListenerContainer** mất bảo đảm thứ tự khi đăng ký nhiều consumer.
- Một Session tuần tự hóa listener execution; nhiều Session cho phép xử lý song song.
- **JMSXGroupID** và **JMSXGroupSeq** dùng để mô tả group và sequence; cần kiểm tra semantics grouping của broker.
- Rollback/recover có thể làm message được giao lại; **JMSRedelivered** và **JMSXDeliveryCount** giúp quan sát redelivery.
- Spring DMLC cần **sessionTransacted=true** hoặc external transaction manager nếu muốn listener exception dẫn đến rollback/redelivery.
- Priority 0–9 có thể làm message ưu tiên cao vượt lên trước; JMS không yêu cầu strict priority ordering.
- Delivery delay, expiration và delivery mode cũng ảnh hưởng chuỗi nhận.
- Dùng sequence number, idempotency, bounded retry và DLQ/reconciliation để bảo vệ thứ tự nghiệp vụ.

Khi chọn concurrency, hãy bắt đầu từ yêu cầu thứ tự của nghiệp vụ: FIFO toàn queue cần một luồng nhận tuần tự; thứ tự theo từng aggregate có thể dùng message grouping và sequence; nếu thứ tự không quan trọng thì mới mở rộng nhiều consumer tự do. Đừng để priority, redelivery hoặc retry vô tình thay đổi trạng thái nghiệp vụ mà consumer không phát hiện.

## Tài liệu tham khảo

- [Jakarta Messaging 3.1 — Queue semantics và message order](https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html)
- [Spring Framework 6.2 — DefaultMessageListenerContainer API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jms/listener/DefaultMessageListenerContainer.html)
- [Spring Framework 6.2 — JmsListener API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jms/annotation/JmsListener.html)
- [Spring Framework 6.2 — Annotation-driven Listener Endpoints](https://docs.spring.io/spring-framework/reference/6.2/integration/jms/annotated.html)
- [ActiveMQ Artemis — Message Grouping](https://artemis.apache.org/components/artemis/documentation/latest/message-grouping.html)
- [ActiveMQ Classic — Message Groups](https://activemq.apache.org/components/classic/documentation/message-groups)
