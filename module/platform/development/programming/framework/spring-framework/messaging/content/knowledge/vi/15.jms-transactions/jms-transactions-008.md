# Rollback, redelivery và ngoại lệ thoát khỏi listener trong Spring JMS

## 1. Vì sao exception của listener ảnh hưởng tới việc giao lại message?

Một JMS listener thường nhận message từ broker, thực hiện nghiệp vụ rồi kết thúc lần xử lý. Broker cần biết message đã được xử lý thành công hay chưa để quyết định có thể loại message khỏi destination hay phải giao lại.

Trong Spring JMS, kết quả này phụ thuộc vào acknowledgement mode hoặc transaction của JMS Session. Khi listener hoàn tất bình thường, message có thể được acknowledge hoặc transaction được commit. Khi listener ném exception và exception thoát khỏi method, container có thể rollback transaction để broker giao lại message.

Ba khái niệm cần tách biệt:

- **Rollback:** hủy kết quả của transaction hiện tại. Với local JMS transaction, việc nhận message được rollback để message có thể được giao lại.
- **Redelivery:** broker giao lại một message đã từng được giao nhưng chưa được xác nhận hoàn tất.
- **Exception propagation:** exception từ method listener đi ra ngoài method để listener adapter/container nhận biết lần xử lý thất bại.

Chỉ ném exception không tự động bảo đảm redelivery trong mọi acknowledgement mode. Cần cấu hình listener container và broker phù hợp.

Sau bài học, bạn cần có thể:

- Giải thích transaction và acknowledgement của listener.
- Cấu hình sessionTransacted để rollback khi listener lỗi.
- Hiểu khác biệt giữa AUTO_ACKNOWLEDGE, CLIENT_ACKNOWLEDGE và transacted Session.
- Để exception thoát khỏi listener đúng cách.
- Phân biệt ErrorHandler với cơ chế rollback và broker redelivery.
- Cấu hình giới hạn redelivery, delay và dead-letter queue.
- Thiết kế idempotency để chịu được message trùng.
- Kiểm thử rollback, redelivery, poison message và transaction boundary.

## 2. Vòng đời một lần xử lý message

Với listener chạy trong local JMS transaction, một lần xử lý thường có trình tự:

~~~text
Broker giao message
        |
        v
JMS Session bắt đầu transaction
        |
        v
Spring gọi listener method
        |
        +----------------------------+
        |                            |
   Method thành công             Method ném exception
        |                            |
        v                            v
     COMMIT                       ROLLBACK
        |                            |
        v                            v
Broker ghi nhận                 Broker có thể giao lại
message đã xử lý                message theo redelivery policy
~~~

Khi listener xử lý thành công, container commit session transaction. Broker ghi nhận việc nhận message đã hoàn tất.

Khi listener ném exception, container rollback transaction. Message nhận trong transaction chưa được commit sẽ không được xác nhận thành công. Broker có thể giao lại message theo chính sách redelivery của provider.

Nếu method bắt exception rồi chỉ ghi log và kết thúc bình thường, container nhìn thấy một lần xử lý thành công. Transaction có thể được commit và message không được giao lại. Vì vậy, quyết định catch hay rethrow exception là một phần của hợp đồng xử lý message.

## 3. Cấu hình sessionTransacted trong Spring JMS

### 3.1 Dùng DefaultJmsListenerContainerFactory

Với listener khai báo bằng `@JmsListener`, có thể bật local JMS transaction trên factory:

~~~java
import jakarta.jms.ConnectionFactory;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.annotation.EnableJms;
import org.springframework.jms.config.DefaultJmsListenerContainerFactory;

@Configuration
@EnableJms
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

Factory này tạo listener container dùng transacted JMS Session. Mỗi lần listener xử lý message nằm trong transaction nhận message. Nếu listener hoàn tất bình thường, container commit; nếu listener thất bại, container rollback.

Listener:

~~~java
import org.springframework.jms.annotation.JmsListener;
import org.springframework.stereotype.Component;

@Component
public class OrderListener {

    private final OrderService orderService;

    public OrderListener(OrderService orderService) {
        this.orderService = orderService;
    }

    @JmsListener(destination = "orders.queue")
    public void handle(OrderCreated event) {
        orderService.process(event);
    }
}
~~~

`OrderCreated` và `OrderService` là kiểu thuộc ứng dụng. Nếu `process` ném unchecked exception, exception đi ra khỏi listener method để container xử lý. Với session transaction đã bật, container rollback lần nhận message.

Nếu ứng dụng có nhiều nhóm listener với yêu cầu transaction khác nhau, hãy khai báo factory riêng và chọn bằng thuộc tính `containerFactory` của `@JmsListener`.

### 3.2 Cấu hình container thủ công

Nếu tạo `DefaultMessageListenerContainer` trực tiếp, bật cùng thuộc tính:

~~~java
DefaultMessageListenerContainer container =
        new DefaultMessageListenerContainer();

container.setConnectionFactory(connectionFactory);
container.setDestination(ordersQueue);
container.setMessageListener(orderListener);
container.setSessionTransacted(true);
~~~

Đây là đoạn cấu hình trong bean do Spring quản lý. `connectionFactory`, `ordersQueue` và `orderListener` cần được cung cấp từ application context.

### 3.3 Vì sao nên dùng transacted Session?

Tài liệu Spring khuyến nghị dùng `sessionTransacted=true` hoặc transaction manager bên ngoài khi cần độ tin cậy. Với local JMS transaction, việc acknowledge message được gắn với commit của session. Exception từ listener khiến container rollback và broker có cơ hội redeliver.

Đây là lựa chọn rõ ràng cho queue consumer hoặc durable topic subscriber cần tránh mất message do lỗi xử lý. Tuy vậy, transaction JMS cục bộ chỉ bao phủ tài nguyên JMS thuộc session đó; nó không tự bao gồm database hoặc dịch vụ HTTP.

## 4. Acknowledgement mode và khả năng redelivery

Không nên giả định mọi acknowledgement mode có cùng hành vi khi listener ném exception. Với `DefaultMessageListenerContainer`, các mode có ý nghĩa như sau:

| Chế độ | Hành vi khi listener thành công | Hành vi khi listener ném exception |
|---|---|---|
| `AUTO_ACKNOWLEDGE` | Container/provider tự acknowledge | Với DefaultMessageListenerContainer, acknowledge diễn ra trước khi gọi listener; không redeliver do exception của listener |
| `DUPS_OK_ACKNOWLEDGE` | Acknowledge lười theo cơ chế provider/container | Không bảo đảm redelivery khi listener ném exception; vẫn có thể có duplicate trong một số tình huống |
| `CLIENT_ACKNOWLEDGE` | Spring acknowledge sau khi listener chạy thành công | Có thể redeliver khi listener lỗi, nhưng là cơ chế best-effort |
| `sessionTransacted=true` | Commit transaction sau khi listener thành công | Rollback khi listener lỗi; hỗ trợ redelivery nhất quán hơn |

`AUTO_ACKNOWLEDGE` là mặc định phổ biến của listener container. Với `DefaultMessageListenerContainer`, Spring acknowledge message trước khi listener execution bắt đầu. Nếu method sau đó ném exception, broker đã được báo rằng message đã được acknowledge; không thể dựa vào exception đó để yêu cầu redelivery.

`CLIENT_ACKNOWLEDGE` có thể cho phép Spring chỉ acknowledge sau khi listener hoàn tất thành công. Tuy nhiên, acknowledgement trong JMS có thể áp dụng cho các message đã được consumer nhận trên cùng session, và hành vi redelivery phụ thuộc provider. Khi cần bảo đảm rõ ràng, ưu tiên transacted Session.

`sessionTransacted=true` là cách trực tiếp để gắn kết việc nhận message với kết quả listener. Hãy cấu hình trên factory/container thay vì chỉ trông chờ exception tự động được broker nhìn thấy.

## 5. Để exception thoát khỏi listener

### 5.1 Rethrow khi xử lý thất bại

Ví dụ một service phát hiện lỗi tạm thời:

~~~java
@JmsListener(destination = "payments.queue")
public void handle(PaymentRequested event) {
    paymentService.process(event);
}
~~~

Nếu `paymentService.process` ném `RuntimeException`, listener method kết thúc bất thường. Với session transaction, container rollback và message có thể được giao lại.

Có thể ném exception rõ nghĩa khi phát hiện điều kiện không thể tiếp tục:

~~~java
@JmsListener(destination = "inventory.queue")
public void reserve(ReserveInventory command) {
    boolean reserved = inventoryService.reserve(command);

    if (!reserved) {
        throw new IllegalStateException(
                "Inventory reservation could not be completed");
    }
}
~~~

Ví dụ minh họa việc để lỗi thoát khỏi method. `ReserveInventory` và `InventoryService` là kiểu ứng dụng; trong production nên dùng exception domain cụ thể để phân biệt lỗi tạm thời và lỗi vĩnh viễn.

### 5.2 Catch rồi rethrow

Có thể bắt exception để bổ sung ngữ cảnh rồi ném lại:

~~~java
@JmsListener(destination = "orders.queue")
public void handle(OrderCreated event) {
    try {
        orderService.process(event);
    }
    catch (RuntimeException ex) {
        log.error("Could not process order event {}", event.eventId(), ex);
        throw ex;
    }
}
~~~

Việc rethrow giữ nguyên tín hiệu thất bại cho listener container. Transaction có thể rollback theo cấu hình.

Nếu cần đổi loại exception, hãy giữ nguyên nguyên nhân gốc:

~~~java
catch (ExternalServiceException ex) {
    throw new TemporaryOrderProcessingException(
            "Order processing must be retried", ex);
}
~~~

Đừng làm mất stack trace hoặc correlation ID khi bọc exception. Thông tin này cần thiết để tìm nguyên nhân qua log và trace.

### 5.3 Catch và swallow exception

Đoạn sau thay đổi semantics của lần xử lý:

~~~java
@JmsListener(destination = "orders.queue")
public void handle(OrderCreated event) {
    try {
        orderService.process(event);
    }
    catch (RuntimeException ex) {
        log.error("Processing failed", ex);
        // Method kết thúc bình thường.
    }
}
~~~

Vì exception không thoát khỏi listener, container có thể xem lần gọi là thành công. Với session transaction, message có thể được commit và không redeliver.

Chỉ catch rồi không ném lại khi ứng dụng đã xử lý lỗi theo một kết quả được chấp nhận, ví dụ đã ghi nhận message vào một error store bền vững trong một transaction phù hợp. Việc ghi log đơn thuần không phải xử lý lỗi bền vững.

## 6. Spring xử lý exception của listener như thế nào?

Listener container là lớp trung gian giữa broker và method nghiệp vụ. Nó quản lý việc nhận message, transaction, acknowledgement, tài nguyên JMS và xử lý exception.

Mặc định, Spring không chuyển exception từ listener method ngược lên JMS provider như thể callback provider tự thất bại. Container xử lý acknowledgement/transaction của nó và thường ghi log exception ở mức WARN. Có thể cấu hình `ErrorHandler` để nhận lỗi listener và thực hiện logging, metrics hoặc cảnh báo.

Ví dụ đăng ký ErrorHandler trên factory:

~~~java
factory.setErrorHandler(error ->
        logger.error("JMS listener execution failed", error));
~~~

`logger` trong ví dụ là logger của lớp cấu hình.

Cần phân biệt:

- **Exception thoát khỏi listener:** báo cho container biết lần xử lý method thất bại; transaction mode quyết định commit hay rollback.
- **ErrorHandler:** điểm nhận lỗi do listener execution phát sinh để quan sát hoặc xử lý theo chính sách ứng dụng.
- **JMS ExceptionListener:** callback của JMS connection cho các lỗi connection-level mà provider báo.
- **Broker redelivery policy:** quyết định lịch giao lại, số lần thử và dead-letter sau khi transaction bị rollback hoặc message không được acknowledge.

ErrorHandler không thay thế transaction. Nếu muốn rollback, hãy để exception thoát khỏi listener và cấu hình transaction phù hợp. Không bắt exception trong listener rồi kỳ vọng ErrorHandler tự khôi phục một transaction đã được commit.

## 7. Redelivery do broker quản lý

### 7.1 Khi nào broker giao lại?

Sau khi transaction bị rollback hoặc message không được acknowledge theo cơ chế phù hợp, broker có thể đưa message trở lại trạng thái có thể giao. Lần nhận tiếp theo là redelivery.

Các yếu tố ảnh hưởng:

- Acknowledgement hoặc transaction outcome.
- Message có persistent delivery mode hay không.
- Broker redelivery policy.
- Delivery count và giới hạn số lần giao.
- Redelivery delay hoặc backoff.
- Message expiration/TTL.
- Consumer selector và destination topology.
- Broker restart, persistence và cấu hình lưu trữ.

Spring bật transaction ở listener container; broker quyết định chính sách giao lại cụ thể. Các tên cấu hình và hành vi khác nhau giữa ActiveMQ Classic, ActiveMQ Artemis, IBM MQ và provider khác.

### 7.2 Nhận biết message redelivered

JMS cung cấp header `JMSRedelivered` để cho biết message có thể đã được giao trước đó nhưng chưa được xác nhận thành công.

Ví dụ nhận JMS Message trực tiếp:

~~~java
import jakarta.jms.JMSException;
import jakarta.jms.Message;

@JmsListener(destination = "orders.queue")
public void inspect(Message message) throws JMSException {
    boolean redelivered = message.getJMSRedelivered();

    if (redelivered) {
        log.warn("Receiving a redelivered message: {}",
                message.getJMSMessageID());
    }

    processMessage(message);
}
~~~

Một số provider còn cung cấp delivery count property như `JMSXDeliveryCount`. Hãy kiểm tra provider và phiên bản JMS đang dùng để biết cách đọc, giá trị ban đầu và cách tăng bộ đếm.

`JMSRedelivered` chỉ là tín hiệu phục vụ quan sát. Không dùng nó làm khóa chống trùng duy nhất. Message có thể bị giao lại sau crash ở một thời điểm không thể dự đoán, và ứng dụng cần dựa vào event ID hoặc business key ổn định để deduplicate.

### 7.3 Redelivery delay và số lần thử

Broker thường cho phép cấu hình:

- Số lần giao tối đa.
- Khoảng chờ trước lần giao lại.
- Exponential delay hoặc multiplier.
- Maximum redelivery delay.
- Xử lý khi vượt quá số lần thử.

Nếu listener luôn thất bại và broker giao lại ngay lập tức, một message lỗi có thể tạo vòng lặp nhanh, tiêu thụ CPU, thread và log. Redelivery delay giúp giảm áp lực và cho hệ thống phụ thuộc có thời gian phục hồi.

Không nhầm redelivery delay của message với `recoveryInterval` của listener container. Recovery interval điều khiển việc Spring thử tạo lại connection/consumer sau lỗi hạ tầng. Redelivery policy điều khiển thời điểm broker giao lại một message chưa được xác nhận.

## 8. Poison message và dead-letter queue

### 8.1 Poison message là gì?

Poison message là message liên tục gây lỗi khi xử lý. Nguyên nhân có thể là:

- Payload sai schema hoặc thiếu dữ liệu bắt buộc.
- Giá trị nghiệp vụ không hợp lệ.
- Message chứa kiểu dữ liệu consumer không thể deserialize.
- Một bug khiến cùng một nhánh code luôn ném exception.
- Dữ liệu tham chiếu đã bị xóa hoặc không còn tồn tại.

Retry vô hạn không sửa được lỗi vĩnh viễn. Message đó có thể chiếm consumer và làm chậm các message hợp lệ.

### 8.2 Dead-letter queue

Dead-letter queue (DLQ) là destination để broker chuyển message sau khi vượt quá redelivery limit hoặc theo điều kiện dead-letter policy.

Một quy trình thường gặp:

1. Consumer nhận message.
2. Listener ném exception và transaction rollback.
3. Broker giao lại theo redelivery policy.
4. Delivery count tăng.
5. Sau số lần thử tối đa, broker chuyển message sang DLQ hoặc xử lý theo policy đã cấu hình.
6. Đội vận hành kiểm tra nguyên nhân và quyết định sửa dữ liệu, sửa code hoặc replay message.

DLQ và số lần thử tối đa không được cấu hình giống nhau ở mọi provider. Cần cấu hình broker, cấp quyền truy cập DLQ và có quy trình theo dõi backlog.

### 8.3 Retry lỗi tạm thời và lỗi vĩnh viễn

Có thể phân loại lỗi theo bản chất:

- **Lỗi tạm thời:** dịch vụ ngoài timeout, database tạm mất kết nối, rate limit. Có thể retry với delay và giới hạn.
- **Lỗi vĩnh viễn:** schema sai, dữ liệu không hợp lệ, destination mapping sai. Retry không giới hạn thường không có ích; cần đưa vào error flow hoặc DLQ.
- **Lỗi chưa rõ:** cần giữ nguyên message, ghi đủ metadata và giới hạn số lần thử trong khi điều tra.

Không tự sleep trong listener để chờ retry. Sleep giữ consumer thread và có thể làm giảm throughput. Dùng broker redelivery policy hoặc cơ chế retry có chủ đích.

## 9. Transaction JMS và database không tự động nguyên tử

`sessionTransacted=true` tạo local transaction cho JMS Session. Nó bao phủ việc nhận message và các thao tác JMS cùng session, ví dụ gửi response qua một listener API có sử dụng session đó.

Nó không tự động bao gồm database transaction, HTTP call hoặc thao tác trên hệ thống ngoài.

Ví dụ:

1. Listener nhận event.
2. Service ghi thay đổi vào database và database commit.
3. Một bước sau đó ném exception.
4. JMS session rollback.
5. Broker giao lại message.
6. Database có thể nhận cùng event lần nữa.

Kết quả là duplicate processing có thể xảy ra dù JMS transaction hoạt động đúng. Vì vậy, listener nên có idempotency.

Các lựa chọn thường dùng:

- **Inbox/deduplication table:** lưu event ID đã xử lý với unique constraint trong cùng database transaction với cập nhật nghiệp vụ.
- **Idempotent service:** cùng một event được gọi nhiều lần vẫn tạo ra cùng kết quả cuối.
- **Outbox pattern:** ghi thay đổi nghiệp vụ và sự kiện cần phát trong cùng database transaction, sau đó publisher phát outbox.
- **JTA/XA:** phối hợp nhiều tài nguyên XA trong một transaction khi provider, database và transaction manager hỗ trợ; cấu hình phức tạp và có chi phí vận hành.

Không tuyên bố exactly-once chỉ vì bật transacted Session. Hãy thiết kế để duplicate message không gây tác dụng phụ ngoài ý muốn.

## 10. Phân biệt local JMS transaction và transaction manager bên ngoài

### 10.1 Local JMS transaction

Dùng `sessionTransacted=true` khi muốn transaction chỉ bao phủ JMS Session. Đây thường là lựa chọn hiệu quả và dễ triển khai cho consumer.

~~~java
factory.setSessionTransacted(true);
~~~

Khi listener thành công, session commit. Khi listener ném exception, session rollback. Việc giao lại message sau rollback tuân theo provider redelivery policy.

### 10.2 JmsTransactionManager

`JmsTransactionManager` quản lý local transaction cho một ConnectionFactory. Nó có thể phối hợp các thao tác JMS trong phạm vi transaction được Spring quản lý, nhưng bản thân nó không biến database transaction thành cùng một transaction nguyên tử.

Nếu cần cùng transaction JMS được chia sẻ giữa các bean hoặc template, hãy cấu hình transaction manager và ConnectionFactory đúng cách, đồng thời xác minh tài nguyên có được bind vào transaction hiện tại.

### 10.3 JTA/XA

Khi cần transaction phối hợp JMS và database, có thể dùng JTA với XA-capable ConnectionFactory và XA resource của database. Listener container cần tham gia transaction manager bên ngoài.

Điều kiện:

- JMS provider cung cấp XA resource phù hợp.
- Database driver/resource hỗ trợ XA.
- Transaction coordinator được cấu hình đúng.
- Timeout, recovery log và crash recovery được vận hành.
- Các hệ thống downstream tham gia transaction theo đúng chuẩn.

XA có thể cung cấp atomic commit giữa các resource được enlist, nhưng tăng độ phức tạp và yêu cầu vận hành. Với nhiều hệ thống, outbox/inbox và idempotency có thể dễ kiểm soát hơn.

## 11. Error handling và logging

Một listener production cần ghi đủ thông tin để điều tra mà không làm lộ payload nhạy cảm.

Nên ghi nhận:

- Destination và listener ID.
- JMSMessageID và JMSCorrelationID nếu có.
- Business event ID hoặc idempotency key.
- JMSRedelivered và delivery count nếu provider hỗ trợ.
- Loại exception và root cause.
- Thời gian xử lý.
- Số lần retry hoặc trạng thái DLQ.
- Trạng thái transaction ở mức có thể quan sát.

Tránh log toàn bộ body nếu message chứa dữ liệu cá nhân, token, thông tin thanh toán hoặc bí mật. Có thể log event type, business ID đã che dữ liệu và correlation ID.

ErrorHandler nên gửi lỗi tới logging, metrics hoặc alerting. Nếu dùng error flow để chuyển message sang hệ thống lưu lỗi, phải xác định rõ message gốc có được commit hay rollback và nơi lưu lỗi có bền vững không. Một thao tác chỉ ghi log không đủ để thay thế DLQ.

## 12. Kiểm thử rollback và redelivery

Các hành vi quan trọng cần integration test với JMS provider/broker mục tiêu:

1. Listener thành công với sessionTransacted: message được commit và không còn được giao lại.
2. Listener ném exception: transaction rollback và broker giao lại message.
3. Listener catch rồi swallow exception: xác minh lần xử lý được coi là thành công theo transaction flow.
4. AUTO_ACKNOWLEDGE trên DefaultMessageListenerContainer: xác minh exception không tự tạo redelivery.
5. CLIENT_ACKNOWLEDGE: kiểm tra hành vi cụ thể của provider/container.
6. Redelivery delay: message không được giao lại trước khoảng chờ đã cấu hình.
7. Max delivery attempts: message vượt giới hạn được xử lý theo DLQ policy.
8. Listener nhận message có JMSRedelivered được đặt phù hợp.
9. Database đã commit nhưng JMS rollback: deduplication ngăn tác dụng phụ lặp.
10. Broker restart trong lúc xử lý: xác minh acknowledgement và redelivery sau recovery.
11. ErrorHandler nhận exception theo cấu hình mà transaction outcome vẫn đúng.
12. Poison message không chặn vô hạn các message hợp lệ khác.

Test nên dùng latch/future hoặc polling assertion có timeout thay vì sleep cố định. Test unit cho service không chứng minh broker redelivery; cần integration test với provider thực tế hoặc Testcontainers phù hợp.

## 13. Các lỗi thường gặp

- **Cho rằng exception luôn tạo redelivery:** acknowledgement mode có thể đã acknowledge message trước khi listener chạy.
- **Dùng AUTO_ACKNOWLEDGE cho xử lý cần độ tin cậy:** DefaultMessageListenerContainer acknowledge trước listener execution.
- **Bắt rồi nuốt exception:** container có thể commit transaction vì method kết thúc bình thường.
- **Chỉ ghi log rồi tiếp tục:** log không rollback message và không lưu message bền vững.
- **Nhầm ErrorHandler với rollback:** transaction/acknowledgement do container quản lý; ErrorHandler chủ yếu nhận lỗi để quan sát/xử lý.
- **Retry vô hạn poison message:** một message lỗi có thể tạo vòng lặp và làm nghẽn consumer.
- **Không cấu hình DLQ:** message vượt giới hạn có thể bị xử lý theo policy mặc định không phù hợp.
- **Nhầm recoveryInterval với redelivery delay:** một bên khôi phục listener resources, bên kia trì hoãn giao lại message.
- **Cho rằng local JMS transaction bao gồm database:** hai resource có thể commit/rollback độc lập.
- **Không idempotent:** rollback và redelivery có thể làm nghiệp vụ chạy lặp.
- **Tin JMSRedelivered như khóa deduplication:** đây chỉ là cờ trạng thái, không thay thế event ID ổn định.
- **Dùng XA mà không vận hành recovery log:** transaction phân tán cần quy trình xử lý trạng thái in-doubt.
- **Không kiểm thử trên broker thật:** giới hạn redelivery, delay và DLQ phụ thuộc provider.

## 14. Checklist triển khai

Trước khi đưa listener vào production, hãy xác nhận:

- Listener container đang dùng là DefaultMessageListenerContainer hay implementation khác?
- Acknowledgement mode hiện tại là gì?
- Có bật `sessionTransacted=true` hoặc transaction manager phù hợp không?
- Listener có để exception thoát ra khi xử lý thất bại không?
- Có catch exception rồi vô tình commit message không?
- ErrorHandler có ghi nhận exception và root cause không?
- Broker redelivery policy có delay và max attempts hợp lý không?
- DLQ đã được cấu hình, giám sát và có quy trình replay chưa?
- Có phân biệt lỗi tạm thời với lỗi vĩnh viễn không?
- Listener có idempotent và dùng event ID ổn định không?
- Database và JMS có cần XA hoặc outbox/inbox không?
- Metric có theo dõi redelivery, delivery count, rollback và DLQ backlog không?
- Integration test đã xác minh rollback, redelivery, poison message và broker restart chưa?

## 15. Tài liệu tham khảo

- [Spring Framework 6.2 — Receiving a Message](https://docs.spring.io/spring-framework/reference/6.2/integration/jms/receiving.html)
- [Spring Framework 6.2 — Using Spring JMS](https://docs.spring.io/spring-framework/reference/6.2/integration/jms/using.html)
- [AbstractMessageListenerContainer — Spring Framework 6.2 Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jms/listener/AbstractMessageListenerContainer.html)
- [DefaultMessageListenerContainer — Spring Framework 6.2 Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jms/listener/DefaultMessageListenerContainer.html)