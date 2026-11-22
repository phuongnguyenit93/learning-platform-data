# AUTO_ACKNOWLEDGE, CLIENT_ACKNOWLEDGE và DUPS_OK_ACKNOWLEDGE

## 1. Acknowledgement giải quyết vấn đề gì?

Trong Jakarta Messaging (JMS), consumer cần thông báo cho provider biết message đã được nhận và xử lý tới đâu. Acknowledgement (ack) là tín hiệu ở phía nhận để provider quyết định có thể loại message khỏi trạng thái chờ giao hay cần giữ lại để giao lại.

Ba acknowledgement mode chuẩn của một `Session` không giao dịch là:

- `Session.AUTO_ACKNOWLEDGE`: provider tự acknowledge theo quy tắc của mode.
- `Session.CLIENT_ACKNOWLEDGE`: ứng dụng chủ động gọi `Message.acknowledge()`.
- `Session.DUPS_OK_ACKNOWLEDGE`: provider acknowledge lười để giảm overhead; consumer phải chấp nhận khả năng nhận duplicate.

Ngoài ba mode trên, `Session.SESSION_TRANSACTED` biểu thị một Session có local transaction. Đây là cơ chế commit/rollback riêng, không phải acknowledgement mode thứ tư tương đương ba mode không giao dịch.

Ack mode được cấu hình ở cấp `Session`, ảnh hưởng các message consumer của Session đó. Nó không phải thuộc tính của từng message và không quyết định producer gửi message persistent hay non-persistent.

## 2. Phân biệt acknowledgement, transaction và delivery mode

Ba khái niệm thường bị nhầm:

| Khái niệm | Câu hỏi được trả lời | Ví dụ |
| --- | --- | --- |
| Acknowledgement mode | Khi nào provider xem message đã được consumer xác nhận? | AUTO, CLIENT, DUPS_OK |
| Session transaction | Nhóm nhận và gửi message nào được commit hoặc rollback cùng nhau? | `SESSION_TRANSACTED`, `commit()`, `rollback()` |
| Delivery mode | Broker cần lưu message đã gửi bền vững hay có thể mất khi provider lỗi? | `PERSISTENT`, `NON_PERSISTENT` |

`PERSISTENT` không có nghĩa consumer đã xử lý xong. `AUTO_ACKNOWLEDGE` không có nghĩa message được lưu bền vững. `CLIENT_ACKNOWLEDGE` không tạo transaction giữa JMS và database. Muốn hiểu độ tin cậy của một luồng, phải xem cả producer delivery mode, consumer acknowledgement/transaction, broker policy và transaction nghiệp vụ.

## 3. Ba acknowledgement mode chuẩn

### 3.1. AUTO_ACKNOWLEDGE

Provider tự acknowledge khi:

- Consumer nhận đồng bộ: lời gọi `receive()` trả về message thành công.
- Consumer nhận bất đồng bộ: `MessageListener.onMessage(...)` kết thúc thành công.

Với nhận đồng bộ, ack xảy ra khi `receive()` trả về. Nếu ứng dụng lấy message xong rồi mới cập nhật database và database lỗi, provider đã được phép xem message là đã nhận; message không tự quay lại chỉ vì code xử lý phía sau thất bại.

Với listener bất đồng bộ thuần theo Jakarta Messaging, provider acknowledge sau khi `onMessage` trả về thành công. Nếu listener ném `RuntimeException`, Jakarta Messaging quy định hành vi redelivery cho AUTO/DUPS_OK; số lần provider thử lại trước khi từ bỏ phụ thuộc provider.

Đừng áp dụng máy móc quy tắc listener thuần này cho Spring listener container. Spring bắt và xử lý exception của listener bên trong container, nên provider không nhìn thấy callback thất bại theo cùng cách. Thời điểm ack của `DefaultMessageListenerContainer` và `SimpleMessageListenerContainer` cũng khác nhau; phần 8 giải thích cụ thể.

AUTO phù hợp khi xử lý đơn giản, mất message trong một số failure window được chấp nhận hoặc ứng dụng có cơ chế phục hồi khác. Với nghiệp vụ cần redelivery khi listener thất bại, không nên chỉ dựa vào AUTO.

### 3.2. CLIENT_ACKNOWLEDGE

Ứng dụng gọi `message.acknowledge()` sau khi hoàn thành công việc:

~~~java
Message message = consumer.receive(5_000);
if (message != null) {
    processBusinessData(message);
    message.acknowledge();
}
~~~

Nếu xử lý thất bại trước khi acknowledge, message vẫn chưa được xác nhận. Ứng dụng có thể gọi `session.recover()` để dừng luồng nhận hiện tại và bắt đầu giao lại từ message đầu tiên chưa được acknowledge.

**Điểm rất quan trọng:** trong JMS chuẩn, `Message.acknowledge()` acknowledge tất cả message đã được giao bởi cùng Session, kể cả message được giao trước message đang gọi `acknowledge()`. Nó không phải individual ack cho riêng một message.

Ví dụ, nếu cùng một Session đã nhận M1, M2 và M3, gọi `M2.acknowledge()` có thể acknowledge cả M1, M2 và M3 đã được giao bởi Session đó. Vì vậy không nên xử lý song song nhiều message trên cùng Session rồi acknowledge tùy ý theo thứ tự hoàn tất.

`CLIENT_ACKNOWLEDGE` phù hợp khi ứng dụng cần quyết định thời điểm xác nhận và có thể kiểm soát thứ tự xử lý trong Session. Nó không gom thao tác gửi response hoặc cập nhật database vào cùng một transaction nguyên tử. Nếu cần nhận message và gửi reply như một đơn vị JMS, hãy dùng transacted Session.

### 3.3. DUPS_OK_ACKNOWLEDGE

Provider acknowledge message theo cách lười, có thể gom nhiều lần acknowledge để giảm công việc quản lý trạng thái giao nhận. Khi provider hoặc kết nối gặp lỗi, một số message đã được xử lý có thể được giao lại.

Mode này đổi chi phí acknowledgement thấp hơn lấy khả năng duplicate cao hơn. Chỉ dùng khi consumer chịu được xử lý lặp, ví dụ cập nhật một projection có tính idempotent hoặc xử lý dữ liệu mà duplicate không làm thay đổi kết quả.

DUPS_OK không phải chế độ “không bao giờ mất message”. Nó vẫn có failure window và semantics phụ thuộc provider. Nếu duplicate có thể gây thu tiền hai lần, tạo đơn trùng hoặc phát side effect không thể đảo ngược, hãy chọn transaction/idempotency rõ ràng.

## 4. CLIENT_ACKNOWLEDGE: acknowledge tích lũy và recover

### 4.1. Acknowledge theo phạm vi Session

JMS chuẩn không định nghĩa individual acknowledgement cho một message độc lập trong một Session. Khi gọi `acknowledge()` trên một message, provider acknowledge toàn bộ message đã được giao bởi Session đó.

Điều này có hai hệ quả:

1. Giữ việc nhận và xử lý message theo thứ tự trong từng Session.
2. Nếu cần concurrency, tạo nhiều Session/consumer độc lập thay vì chia sẻ một Session cho nhiều thread.

Jakarta Messaging yêu cầu Session được sử dụng tuần tự bởi một luồng logic tại một thời điểm. Mỗi Session có input stream và phạm vi acknowledgement riêng.

### 4.2. session.recover()

`Session.recover()` dừng luồng nhận hiện tại và khởi động lại từ message đầu tiên chưa được acknowledge. Provider đánh dấu message được giao lại bằng `JMSRedelivered=true` và tăng `JMSXDeliveryCount` theo quy định của Jakarta Messaging.

Ví dụ:

~~~java
Message message = consumer.receive(5_000);
if (message != null) {
    try {
        processBusinessData(message);
        message.acknowledge();
    } catch (RuntimeException ex) {
        session.recover();
        throw ex;
    }
}
~~~

Đây là ví dụ minh họa cho consumer đồng bộ, không phải mẫu retry hoàn chỉnh. Nếu lỗi là dữ liệu không hợp lệ và không thể xử lý, gọi recover vô hạn có thể tạo vòng lặp poison message. Cần giới hạn retry và chuyển message lỗi sang dead-letter queue (DLQ) theo khả năng của broker.

`recover()` chỉ áp dụng cho Session không giao dịch. Với Session transacted, dùng `rollback()` để hoàn tác transaction.

## 5. SESSION_TRANSACTED: commit và rollback

Khi tạo Session giao dịch, acknowledgement được quản lý tự động bởi transaction:

- `commit()` xác nhận các message đã nhận trong transaction và phát các message đã gửi trong transaction.
- `rollback()` hủy các message đã gửi trong transaction và phục hồi các message đã nhận để provider có thể giao lại.

Một transaction JMS gom input và output của cùng Session thành một đơn vị công việc. Ví dụ consumer nhận `OrderPlaced`, xử lý rồi gửi `ReserveInventory` bằng producer tạo từ cùng Session. Nếu commit thành công, việc nhận và gửi được commit cùng nhau. Nếu rollback, message đầu vào được phục hồi và message đầu ra bị hủy.

~~~java
try (Connection connection = connectionFactory.createConnection();
     Session session = connection.createSession(Session.SESSION_TRANSACTED)) {

    MessageConsumer consumer = session.createConsumer(ordersQueue);
    MessageProducer producer = session.createProducer(inventoryQueue);
    connection.start();

    Message incoming = consumer.receive(5_000);
    if (incoming != null) {
        try {
            processOrder(incoming);
            producer.send(session.createTextMessage("ReserveInventory"));
            session.commit();
        } catch (RuntimeException ex) {
            session.rollback();
            throw ex;
        }
    }
}
~~~

Đoạn code minh họa cần một `ConnectionFactory`, `ordersQueue` và `inventoryQueue` do JMS provider cung cấp. Trong ứng dụng thực tế, cần xử lý `JMSException`, cấu hình timeout và đóng tài nguyên theo vòng đời ứng dụng.

Khi Session đã transacted, tham số acknowledgement mode truyền cùng `createSession(transacted, acknowledgeMode)` bị bỏ qua. Hãy dùng `createSession(Session.SESSION_TRANSACTED)` để thể hiện rõ ý định.

Transaction chỉ bao phủ các thao tác JMS trong cùng Session. Nếu `processOrder` cập nhật database bằng JDBC, database không tự nằm trong transaction JMS. Nếu database commit nhưng JMS rollback, message có thể được giao lại và code có thể chạy lần nữa. Hãy dùng idempotency, inbox/outbox hoặc XA nếu cần phối hợp nhiều resource.

## 6. So sánh nhanh các mode

| Mode | Ai xác nhận? | Khi nào xác nhận? | Redelivery khi lỗi xử lý | Duplicate |
| --- | --- | --- | --- | --- |
| `AUTO_ACKNOWLEDGE` | Provider | Sau `receive()` thành công hoặc listener trả về thành công theo JMS API; container Spring có semantics riêng | Phụ thuộc receive/listener và container | Có thể có ở failure window cuối cùng |
| `CLIENT_ACKNOWLEDGE` | Ứng dụng hoặc container Spring | Khi gọi `acknowledge()`; Spring container thường ack sau listener thành công | Có thể yêu cầu `recover()`; Spring container cung cấp best-effort redelivery khi listener lỗi | Có thể có khi redelivery |
| `DUPS_OK_ACKNOWLEDGE` | Provider | Lười, có thể gom acknowledge | Provider/JMS API và container quyết định; Spring container không redeliver khi user exception theo mode này | Có thể có và là đặc tính cần chấp nhận |
| `SESSION_TRANSACTED` | Transaction manager/Session | Khi `commit()`; `rollback()` phục hồi input và hủy output | Có khi rollback; provider áp dụng redelivery policy | Vẫn có ở một số failure window giữa business commit và JMS commit |

Không có một mode nào tự bảo đảm exactly-once cho toàn bộ nghiệp vụ qua database, broker và các service bên ngoài.

## 7. Tạo Session với từng mode trong Jakarta Messaging

Với API classic, các hằng số nằm trong `jakarta.jms.Session`:

~~~java
Session auto = connection.createSession(Session.AUTO_ACKNOWLEDGE);
Session client = connection.createSession(Session.CLIENT_ACKNOWLEDGE);
Session duplicates = connection.createSession(Session.DUPS_OK_ACKNOWLEDGE);
Session transaction = connection.createSession(Session.SESSION_TRANSACTED);
~~~

Hoặc dùng overload hai tham số:

~~~java
Session auto = connection.createSession(false, Session.AUTO_ACKNOWLEDGE);
Session client = connection.createSession(false, Session.CLIENT_ACKNOWLEDGE);
Session duplicates = connection.createSession(false, Session.DUPS_OK_ACKNOWLEDGE);
Session transaction = connection.createSession(true, Session.AUTO_ACKNOWLEDGE);
~~~

Ở dòng cuối, `transacted=true` có nghĩa Session giao dịch; `AUTO_ACKNOWLEDGE` bị bỏ qua. Các Session trong ví dụ là những lựa chọn thay thế để minh họa; không cần tạo cả bốn Session cho cùng một consumer.

Với API đơn giản `JMSContext`, các mode tương ứng là `JMSContext.AUTO_ACKNOWLEDGE`, `CLIENT_ACKNOWLEDGE`, `DUPS_OK_ACKNOWLEDGE` và `SESSION_TRANSACTED`. Quy tắc và giới hạn của Session cũng áp dụng cho JMSContext.

Trong Jakarta EE web/EJB container, container có thể quản lý transaction và Session. Một số cách tạo local transacted hoặc client-ack Session không portable hoặc bị bỏ qua khi có JTA transaction đang hoạt động. Hãy tuân theo mô hình transaction do application server quản lý.

## 8. Acknowledgement trong Spring JMS listener container

Spring listener container nhận message, gọi listener, xử lý exception và thực hiện acknowledgement. Vì container kiểm soát callback, hành vi quan sát được có thể khác JMS client tự đăng ký `MessageListener` trực tiếp.

### 8.1. AUTO_ACKNOWLEDGE: DMLC và SMLC khác nhau

`DefaultMessageListenerContainer` (DMLC) acknowledge trước khi gọi listener. Nếu listener lỗi hoặc process bị gián đoạn trong lúc xử lý, message không được redeliver theo AUTO mode.

`SimpleMessageListenerContainer` (SMLC) acknowledge sau khi listener invocation kết thúc. Tuy nhiên Spring container không mặc định truyền exception listener lên provider; vì thế exception do listener ném ra không tạo redelivery trong AUTO mode. JVM chết giữa lúc listener đang chạy vẫn có thể dẫn tới redelivery.

Vì vậy, khi cần redelivery nhất quán, không nên chỉ dựa vào AUTO dù dùng SMLC hay DMLC.

### 8.2. CLIENT_ACKNOWLEDGE trong Spring container

Spring container tự acknowledge sau khi listener xử lý thành công. Nếu listener ném exception, container có thể để message được redeliver theo best-effort semantics. Đây không phải local JMS transaction: thao tác khác trên Session, chẳng hạn gửi response, không được commit/rollback cùng message nhận như transacted Session.

### 8.3. DUPS_OK_ACKNOWLEDGE trong Spring container

Spring container acknowledge lười trong hoặc ngay sau listener execution. Exception do user listener ném không tạo redelivery theo semantics của container; process interruption có thể tạo redelivery. Mode này vẫn yêu cầu consumer chịu được duplicate.

### 8.4. Ưu tiên sessionTransacted=true khi cần rollback

Để bật local JMS transaction cho mỗi listener invocation:

~~~java
DefaultJmsListenerContainerFactory factory =
        new DefaultJmsListenerContainerFactory();
factory.setConnectionFactory(connectionFactory);
factory.setSessionTransacted(true);
~~~

Với `@JmsListener`, method có thể là:

~~~java
@JmsListener(destination = "orders.queue")
public void handle(OrderPlaced event) {
    orderService.process(event);
}
~~~

Nếu `orderService.process(...)` ném exception ra khỏi listener, container rollback JMS Session; provider có thể giao lại message theo redelivery policy. Nếu code bắt exception rồi return bình thường, container có thể commit; chỉ ghi log không làm transaction rollback.

Trong Spring, `sessionTransacted=true` là khuyến nghị phổ biến khi cần redelivery đáng tin cậy. DMLC hỗ trợ tham gia transaction bên ngoài khi cấu hình JTA/XA phù hợp; SMLC không hỗ trợ externally managed transaction. Nếu dùng SMLC với `TaskExecutor`, acknowledgement có thể diễn ra trước khi listener chạy; không dùng cấu hình executor đó khi đang dựa vào transaction hoặc client acknowledgement để rollback.

## 9. Synchronous receive và acknowledgement timing

Với raw JMS `AUTO_ACKNOWLEDGE`, message được acknowledge khi `receive()` trả về thành công. Nếu ứng dụng xử lý payload sau dòng `receive()`, phần xử lý đó nằm ngoài thời điểm ack:

~~~java
Message message = consumer.receive(5_000);
if (message != null) {
    updateDatabase(message); // lỗi tại đây không tự làm message redeliver trong AUTO
}
~~~

Với `CLIENT_ACKNOWLEDGE`, gọi `message.acknowledge()` sau khi database update thành công. Nếu lỗi trước ack, dùng `session.recover()` hoặc đóng Session theo recovery semantics phù hợp để message chưa ack được giao lại.

Với transacted Session, đặt cả `receive`, xử lý và `commit()` trong cùng transaction. Nếu xử lý lỗi, rollback. Khi dùng Spring `JmsTemplate.receive()` đơn lẻ, template có thể hoàn tất thao tác nhận trước khi method trả về; xử lý nghiệp vụ diễn ra sau đó không tự thuộc cùng một transaction chỉ vì đã cấu hình template.

## 10. Redelivery, duplicate và dead-letter queue

Redelivery là một phần của failure handling. Provider có thể giao lại message khi Session recover/rollback, connection mất hoặc acknowledgement chưa hoàn tất.

JMS cung cấp metadata hữu ích:

- `JMSRedelivered`: boolean cho biết provider đánh dấu message có thể đã được giao trước đó.
- `JMSXDeliveryCount`: số lần giao theo provider/Jakarta Messaging.

Đây là thông tin quan sát, không phải khóa idempotency. Không chỉ dựa vào `JMSRedelivered` để bỏ qua message: một message lần đầu có thể đã tạo side effect trước khi process chết và sau đó được giao lại. Dùng `eventId` ổn định của ứng dụng, lưu kết quả xử lý hoặc inbox record có unique constraint.

Broker thường cho phép cấu hình số lần redelivery, delay/backoff, dead-letter address/queue và chính sách xử lý poison message. Những tên cấu hình và default này phụ thuộc provider; JMS API không chuẩn hóa một DLQ policy chung.

Thiết kế consumer nên:

1. Kiểm tra hoặc ghi `eventId` trong cùng transaction database với thay đổi nghiệp vụ.
2. Chỉ xác nhận message sau khi công việc bắt buộc đã hoàn tất.
3. Phân loại lỗi tạm thời và lỗi không thể xử lý.
4. Giới hạn số lần retry; chuyển poison message tới DLQ để điều tra.
5. Có quy trình replay sau khi sửa dữ liệu hoặc code.
6. Theo dõi redelivery count, DLQ depth và tuổi message.

## 11. Local JMS transaction, database transaction và XA

### 11.1. Local JMS transaction

Transacted Session bảo đảm các thao tác gửi/nhận trong Session cùng commit hoặc rollback. Đây thường là lựa chọn hiệu quả khi nghiệp vụ chính nằm trong JMS hoặc khi consumer chỉ cần gửi reply qua cùng Session.

Spring `JmsTransactionManager` quản lý local transaction cho một `ConnectionFactory`, bind cặp Connection/Session vào thread. `JmsTemplate` có thể tham gia resource đã bind. Listener container cũng có thể mở transaction riêng cho từng lần gọi listener bằng `sessionTransacted=true`.

### 11.2. Database không tự nằm trong JMS transaction

Nếu listener vừa cập nhật database vừa consume message, local JMS transaction và JDBC transaction là hai transaction độc lập. Có thể xảy ra:

- Database commit, sau đó JMS commit thất bại: broker giao lại message; nghiệp vụ có thể chạy lần nữa.
- JMS commit thành công nhưng database rollback: message đã bị xác nhận trong khi dữ liệu nghiệp vụ không được lưu, nếu hai transaction không phối hợp.

Để xử lý, dùng idempotent consumer/inbox, transactional outbox hoặc transaction coordinator XA khi thực sự cần atomic commit giữa resource và provider hỗ trợ XA.

### 11.3. XA/JTA

XA/JTA cho phép transaction coordinator phối hợp nhiều resource manager, chẳng hạn database và JMS provider có XA-aware ConnectionFactory. Với Spring JMS, DMLC có thể tham gia external transaction qua `JtaTransactionManager` và XA resource phù hợp. SMLC không hỗ trợ external transaction.

XA tăng chi phí vận hành, cấu hình và thời gian xử lý. Không nên chọn XA chỉ để tránh viết idempotency nếu outbox/inbox đáp ứng yêu cầu. Dù dùng XA, cần hiểu failure recovery và heuristic outcome của transaction coordinator.

## 12. Chọn mode theo yêu cầu

| Yêu cầu | Lựa chọn gợi ý | Lý do |
| --- | --- | --- |
| Consumer đơn giản, mất message trong failure window chấp nhận được | AUTO_ACKNOWLEDGE | Ít thao tác và chi phí thấp |
| Giảm overhead acknowledgement, consumer chịu được duplicate | DUPS_OK_ACKNOWLEDGE | Provider có thể acknowledge theo lô/lười |
| Ứng dụng tự quyết định thời điểm ack sau xử lý | CLIENT_ACKNOWLEDGE | Có thể acknowledge sau nghiệp vụ; cần nhớ ack tích lũy theo Session |
| Cần rollback message khi listener lỗi và có thể gửi response cùng transaction | SESSION_TRANSACTED / `sessionTransacted=true` | Commit/rollback bao gồm JMS input và output của cùng Session |
| Cần phối hợp database và JMS trong một atomic transaction | JTA/XA với DMLC và XA resources, hoặc thiết kế outbox/inbox | Phối hợp nhiều resource theo yêu cầu reliability |

Đối với xử lý nghiệp vụ quan trọng, điểm bắt đầu thường là `sessionTransacted=true`, consumer idempotent, redelivery có giới hạn và DLQ. Sau đó đo hiệu năng và điều chỉnh theo tải thực tế.

## 13. Ví dụ cấu hình Spring JMS với transaction

Ví dụ cấu hình `DefaultJmsListenerContainerFactory` dùng local JMS transaction:

~~~java
package com.example.messaging;

import jakarta.jms.ConnectionFactory;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.config.DefaultJmsListenerContainerFactory;

@Configuration
public class JmsListenerConfiguration {
    @Bean
    public DefaultJmsListenerContainerFactory jmsListenerContainerFactory(
            ConnectionFactory connectionFactory) {
        DefaultJmsListenerContainerFactory factory =
                new DefaultJmsListenerContainerFactory();
        factory.setConnectionFactory(connectionFactory);
        factory.setSessionTransacted(true);
        factory.setConcurrency("2-6");
        return factory;
    }
}
~~~

Listener:

~~~java
package com.example.messaging;

import org.springframework.jms.annotation.JmsListener;
import org.springframework.stereotype.Component;

@Component
public class OrderListener {
    private final OrderService orderService;

    public OrderListener(OrderService orderService) {
        this.orderService = orderService;
    }

    @JmsListener(destination = "orders.queue")
    public void handle(OrderPlaced event) {
        orderService.process(event);
    }
}
~~~

Ví dụ cần một JMS provider, bean `ConnectionFactory`, destination `orders.queue` và converter phù hợp với payload `OrderPlaced`. Nếu `orderService.process` ném exception, listener container rollback local JMS transaction. Nếu method return bình thường, container commit. Broker quyết định số lần redelivery và DLQ theo cấu hình provider.

Đây là cấu hình tích hợp Spring, không phải chương trình độc lập có stdout xác định; cần môi trường JMS thật để quan sát ack/rollback. Hãy kiểm thử bằng cách cố ý ném exception trước commit, xác nhận `JMSRedelivered`/delivery count tăng và sau số lần retry đã cấu hình message đi vào DLQ.

## 14. Lỗi thường gặp

- **Nhầm `AUTO_ACKNOWLEDGE` với xử lý nghiệp vụ thành công:** với synchronous receive, ack xảy ra khi `receive()` trả về; phần code sau đó có thể lỗi mà message không được redeliver.
- **Giả định raw JMS listener và Spring listener container có cùng timing:** DMLC và SMLC xử lý AUTO ack khác nhau; Spring container không mặc định truyền listener exception lên provider.
- **Dùng `CLIENT_ACKNOWLEDGE` rồi nghĩ chỉ ack một message:** `Message.acknowledge()` xác nhận tất cả message đã giao bởi Session.
- **Xử lý song song nhiều message trên cùng Session:** Session được thiết kế để dùng tuần tự; ack có thể xác nhận cả message khác.
- **Quên gọi `acknowledge()`:** message chưa được xác nhận và có thể được giao lại khi Session recover/đóng.
- **Dùng `recover()` trên transacted Session:** dùng `rollback()` cho transaction; `recover()` dành cho non-transacted Session.
- **Dùng DUPS_OK cho side effect không idempotent:** duplicate có thể gây tác động nghiệp vụ lặp.
- **Bắt exception rồi return bình thường trong listener transacted:** container có thể commit vì listener kết thúc thành công.
- **Cho rằng CLIENT_ACK gửi reply nguyên tử cùng receive:** client ack không tạo transaction bao gồm các Session operation khác.
- **Cho rằng JMS transaction bao gồm JDBC:** local JMS transaction chỉ quản lý resource JMS của Session.
- **Cho rằng rollback bảo đảm retry vô hạn:** broker có thể giới hạn redelivery và chuyển message vào DLQ.
- **Dùng `JMSRedelivered` làm khóa dedup:** dùng application event ID ổn định và lưu inbox/dedup record.
- **Nhầm acknowledgement với persistent delivery:** ack là trạng thái consumer; persistence là chính sách lưu message ở broker.

## 15. Checklist thiết kế và vận hành

1. Consumer nhận đồng bộ hay bất đồng bộ? Ack xảy ra chính xác ở thời điểm nào?
2. Session có transacted không? Nếu không, đang dùng AUTO, CLIENT hay DUPS_OK?
3. Với CLIENT_ACK, có hiểu acknowledgement áp dụng cho toàn bộ message đã giao bởi Session không?
4. Listener exception có truyền ra ngoài để rollback không, hay bị bắt và bỏ qua?
5. Spring đang dùng DMLC hay SMLC? AUTO ack timing có phù hợp không?
6. Có dùng TaskExecutor trong SMLC khiến acknowledgement xảy ra trước listener không?
7. Có cần gửi response trong cùng JMS transaction với message nhận không?
8. Database và JMS có cùng transaction coordinator hay cần outbox/inbox/XA?
9. Consumer có idempotent và có event ID ổn định không?
10. Redelivery count, retry delay và DLQ được cấu hình ở broker chưa?
11. Có cảnh báo cho poison message, backlog và DLQ depth không?
12. Có kiểm thử crash trước/sau ack, commit, database commit và broker recovery không?

## 16. Ghi nhớ

`AUTO_ACKNOWLEDGE` tự xác nhận khi synchronous `receive()` trả về hoặc listener JMS thuần kết thúc thành công; với Spring listener container, DMLC và SMLC có timing khác nhau và exception listener không mặc định được truyền lên provider. `CLIENT_ACKNOWLEDGE` cho phép xác nhận sau xử lý nhưng `Message.acknowledge()` áp dụng cho tất cả message đã giao bởi Session; `recover()` đưa các message chưa ack trở lại luồng nhận. `DUPS_OK_ACKNOWLEDGE` giảm overhead bằng acknowledgement lười và chấp nhận duplicate. `SESSION_TRANSACTED` dùng commit/rollback để xác nhận input và phát output cùng một transaction JMS; trong Spring listener, `sessionTransacted=true` là lựa chọn thường dùng khi cần redelivery đáng tin cậy. Database vẫn là resource riêng trừ khi có XA/JTA; hãy làm consumer idempotent, giới hạn retry và cấu hình DLQ.

### Tài liệu tham khảo

- [Jakarta Messaging 3.1 Specification — Sessions, Transactions and Message Acknowledgement](https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html#sessions)
- [Jakarta Messaging 3.1 — Message Acknowledgement](https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html#message-acknowledgment)
- [Spring Framework 6.2 — Using Spring JMS](https://docs.spring.io/spring-framework/reference/6.2/integration/jms/using.html)
- [Spring Framework 6.2 — Receiving a Message and Processing Messages Within Transactions](https://docs.spring.io/spring-framework/reference/6.2/integration/jms/receiving.html)
- [Spring Framework 6.2.8 — AbstractMessageListenerContainer Javadoc](https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/jms/listener/AbstractMessageListenerContainer.html)