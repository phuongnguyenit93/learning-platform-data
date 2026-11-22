# Tiêu chí chọn container theo giao dịch và khả năng mở rộng

> Mục tiêu: chọn đúng JMS listener container theo yêu cầu transaction, độ tin cậy, throughput và khả năng mở rộng; hiểu khác biệt giữa `SimpleMessageListenerContainer` và `DefaultMessageListenerContainer`; cấu hình concurrency, acknowledgement, recovery và kiểm thử hành vi khi listener lỗi.

## 1. Listener container giải quyết việc gì?

Một JMS listener container là thành phần trung gian giữa JMS provider và listener của ứng dụng. Container tạo và quản lý `Connection`, `Session`, `MessageConsumer`, thread nhận message, transaction, acknowledgement và vòng đời listener. Nhờ đó, code nghiệp vụ chỉ cần xử lý payload khi được gọi.

Trong Spring, hai implementation tiêu chuẩn thường được cân nhắc là:

- `SimpleMessageListenerContainer` (SMLC).
- `DefaultMessageListenerContainer` (DMLC).

Cả hai đều nhận message bất đồng bộ và gọi listener. Khác biệt chính nằm ở cách nhận message, transaction được hỗ trợ, khả năng tự điều chỉnh số consumer và cách phục hồi khi broker gặp sự cố.

## 2. SimpleMessageListenerContainer

`SimpleMessageListenerContainer` tạo một số lượng session và consumer cố định khi container khởi động. Nó đăng ký listener bằng API JMS chuẩn `MessageConsumer.setMessageListener()` và để JMS provider gọi callback `onMessage()` khi có message.

Đặc điểm:

- Số consumer được xác định khi khởi động; container không tự tăng/giảm theo tải.
- Dựa vào cơ chế callback bất đồng bộ của JMS provider.
- Hỗ trợ transaction JMS cục bộ thông qua `sessionTransacted=true`.
- Không tham gia transaction được quản lý bên ngoài như JTA.
- Có yêu cầu tương thích với môi trường Jakarta EE hạn chế tài nguyên JMS; cần kiểm tra provider/container trước khi chọn.

SMLC phù hợp khi tải ổn định, số consumer cố định, ứng dụng chạy trong môi trường JMS standalone phù hợp và không cần transaction manager bên ngoài. Nó có cấu hình đơn giản, nhưng ứng dụng phải tự xác định concurrency phù hợp từ đầu.

### Ví dụ cấu hình SMLC

```java
import jakarta.jms.ConnectionFactory;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.listener.SimpleMessageListenerContainer;

@Configuration
class SimpleJmsConfiguration {

    @Bean
    SimpleMessageListenerContainer simpleOrdersContainer(
            ConnectionFactory connectionFactory,
            OrderMessageListener listener) {
        var container = new SimpleMessageListenerContainer();
        container.setConnectionFactory(connectionFactory);
        container.setDestinationName("orders.incoming");
        container.setMessageListener(listener);
        container.setConcurrentConsumers(2);
        container.setSessionTransacted(true);
        return container;
    }
}
```

Ví dụ tạo hai consumer cố định và dùng transaction JMS cục bộ cho mỗi lần xử lý. `OrderMessageListener` là listener do ứng dụng cung cấp. Nếu listener ném exception trong transaction, session được rollback và broker có thể giao lại message theo chính sách của provider.

SMLC cũng hỗ trợ `CLIENT_ACKNOWLEDGE`, nhưng chế độ này chỉ xác nhận message và không gom các thao tác JMS khác trong cùng session vào transaction. Khi cần gửi reply hoặc phối hợp nhiều thao tác JMS, transacted session thường rõ ràng hơn.

## 3. DefaultMessageListenerContainer

`DefaultMessageListenerContainer` là lựa chọn phổ biến cho phần lớn ứng dụng Spring JMS. Container dùng vòng lặp `MessageConsumer.receive()` trên các task do Spring quản lý, thay vì giao toàn bộ việc gọi listener cho callback thread của provider.

Đặc điểm:

- Hỗ trợ số consumer tối thiểu và tối đa, có thể tăng theo tải rồi giảm về mức cơ sở.
- Hỗ trợ transaction JMS cục bộ bằng `sessionTransacted=true`.
- Có thể tham gia transaction được quản lý bên ngoài, thường là JTA với XA-capable `ConnectionFactory`.
- Có cơ chế recovery khi broker tạm thời không khả dụng.
- Cho phép cấu hình cache level, receive timeout, executor, recovery interval hoặc `BackOff`.

DMLC phù hợp khi cần mở rộng consumer theo tải, cần tham gia JTA/XA hoặc muốn container tự phục hồi sau khi broker gián đoạn. Nó có nhiều tùy chọn hơn, nên concurrency, cache và transaction cần được cấu hình có chủ đích.

## 4. So sánh hai container

| Tiêu chí | `SimpleMessageListenerContainer` | `DefaultMessageListenerContainer` |
|---|---|---|
| Cách nhận | Provider gọi `MessageListener` | Container polling bằng `MessageConsumer.receive()` |
| Consumer | Cố định từ lúc khởi động | Cố định hoặc tăng/giảm theo giới hạn cấu hình |
| Transaction JMS cục bộ | Có, qua `sessionTransacted` | Có, qua `sessionTransacted` |
| Transaction bên ngoài/JTA | Không hỗ trợ | Có hỗ trợ |
| Recovery broker | Phụ thuộc provider và vòng đời container | Có cơ chế recovery tích hợp, có thể cấu hình backoff |
| Cấu hình vận hành | Đơn giản hơn | Nhiều tùy chọn hơn |
| Trường hợp phù hợp | Tải ổn định, concurrency cố định | Tải biến động, cần scaling hoặc transaction bên ngoài |

Nếu chưa có lý do đặc biệt để dùng SMLC, DMLC thường là lựa chọn thực tế cho ứng dụng production vì khả năng transaction và recovery phong phú hơn. Tuy vậy, container không thể thay thế thiết kế idempotency, dead-letter và giới hạn tài nguyên của ứng dụng.

## 5. Chọn container theo yêu cầu transaction

Trước khi chọn container, cần xác định transaction phải bảo vệ những thao tác nào: chỉ nhận message, nhận và gửi reply, hay cả message cùng cập nhật database.

### 5.1. Không dùng transaction

Nếu listener chỉ thực hiện công việc có thể lặp lại và chấp nhận rủi ro giao nhận theo mặc định, có thể dùng acknowledgement mode mặc định. Tuy nhiên, `AUTO_ACKNOWLEDGE` không bảo đảm redelivery khi listener thất bại. Spring cảnh báo message có thể bị mất nếu listener ném exception hoặc container dừng trong lúc xử lý.

Với DMLC, acknowledgement mặc định có thể được thực hiện trước khi listener chạy; exception từ listener vì vậy không làm message tự động rollback. Không dùng việc ném exception như cơ chế retry nếu container chưa được cấu hình transaction.

### 5.2. Transaction JMS cục bộ

Đặt `sessionTransacted=true` trên listener container để mỗi lần gọi listener chạy trong một JMS transaction cục bộ:

1. Container nhận message trong session transacted.
2. Listener thực hiện xử lý và các thao tác JMS thuộc session đó.
3. Nếu listener hoàn tất bình thường, transaction được commit.
4. Nếu listener ném exception, transaction rollback; broker có thể redeliver message.

Đây thường là lựa chọn phù hợp khi cần giao nhận đáng tin cậy giữa broker và listener. Nếu dùng `SessionAwareMessageListener` để gửi reply bằng chính session nhận message, thao tác gửi reply có thể nằm trong cùng JMS transaction.

Ví dụ DMLC với local JMS transaction:

```java
import jakarta.jms.ConnectionFactory;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.config.DefaultJmsListenerContainerFactory;

@Configuration
class JmsListenerConfiguration {

    @Bean
    DefaultJmsListenerContainerFactory ordersListenerFactory(
            ConnectionFactory connectionFactory) {
        var factory = new DefaultJmsListenerContainerFactory();
        factory.setConnectionFactory(connectionFactory);
        factory.setSessionTransacted(true);
        factory.setConcurrency("2-8");
        factory.setRecoveryInterval(5_000L);
        return factory;
    }
}
```

`DefaultJmsListenerContainerFactory` tạo DMLC cho các endpoint dùng factory này. Cấu hình đặt tối thiểu hai consumer, cho phép tăng tối đa tám consumer, dùng transaction JMS cục bộ và thử recovery theo khoảng thời gian năm giây.

Gắn factory vào listener:

```java
import org.springframework.jms.annotation.JmsListener;
import org.springframework.stereotype.Component;

@Component
class OrderListener {
    private final OrderService orderService;

    OrderListener(OrderService orderService) {
        this.orderService = orderService;
    }

    @JmsListener(
            destination = "orders.incoming",
            containerFactory = "ordersListenerFactory"
    )
    public void receive(OrderCreated event) {
        orderService.process(event);
    }
}
```

Ứng dụng cần bật listener annotation bằng `@EnableJms` nếu hạ tầng chưa được Spring Boot tự cấu hình. `OrderCreated` là DTO message và `OrderService` chứa logic nghiệp vụ. Nếu xử lý thất bại, exception cần được truyền ra ngoài listener để container biết transaction phải rollback.

### 5.3. Transaction với database

Một JMS transaction cục bộ chỉ quản lý thao tác JMS trong session. Nó không tự động bao gồm transaction JDBC/JPA. Ví dụ listener ghi database thành công nhưng broker gặp lỗi trước khi commit/acknowledge, message có thể được giao lại và database có thể nhận cùng tác động lần nữa.

Có hai hướng phổ biến:

- **JMS local transaction + idempotency/inbox:** transaction JMS quản lý nhận message; database ghi nhận kết quả và message ID/business key theo cách chống duplicate. Cách này thường dễ vận hành và ít tốn chi phí hơn XA.
- **JTA/XA transaction:** gộp nhận JMS và cập nhật database trong một transaction phân tán nếu cả JMS provider và database đều hỗ trợ XA và được đăng ký đúng với transaction coordinator.

Không giả định `@Transactional` trên phương thức listener tự động gộp database transaction vào transaction JMS của container. Cần xác định transaction manager nào đang được container sử dụng và resource nào tham gia transaction đó.

### 5.4. Transaction phân tán JTA/XA

Khi yêu cầu nghiệp vụ cần commit hoặc rollback nguyên tử giữa JMS và database, DMLC có thể tham gia transaction bên ngoài thông qua `JtaTransactionManager`. JMS `ConnectionFactory` phải hỗ trợ XA; database cũng cần resource XA nếu thao tác database phải tham gia cùng transaction.

Ví dụ cấu hình factory tham gia JTA:

```java
import jakarta.jms.ConnectionFactory;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.config.DefaultJmsListenerContainerFactory;
import org.springframework.transaction.jta.JtaTransactionManager;

@Configuration
class XaJmsListenerConfiguration {

    @Bean
    DefaultJmsListenerContainerFactory xaOrdersListenerFactory(
            ConnectionFactory xaConnectionFactory,
            JtaTransactionManager transactionManager) {
        var factory = new DefaultJmsListenerContainerFactory();
        factory.setConnectionFactory(xaConnectionFactory);
        factory.setTransactionManager(transactionManager);
        factory.setConcurrency("2-8");
        return factory;
    }
}
```

Đây là cấu hình phía Spring. Để XA thực sự hoạt động, `xaConnectionFactory` phải là factory XA do provider cung cấp và được cấu hình trong transaction coordinator; datasource cũng phải là XA nếu database cần tham gia. Chỉ đặt `JtaTransactionManager` trong Spring mà dùng connection factory thường sẽ không tạo ra transaction phân tán.

XA tăng độ phức tạp, chi phí log transaction và yêu cầu vận hành recovery coordinator. Nếu hệ thống chấp nhận duplicate có kiểm soát, local transaction kết hợp inbox/outbox và idempotency thường là phương án nhẹ hơn.

## 6. Chọn container theo khả năng mở rộng

Concurrency là số listener consumer có thể xử lý message đồng thời. Với DMLC, `concurrentConsumers` là mức cơ sở và `maxConcurrentConsumers` là giới hạn trên. Có thể khai báo bằng chuỗi như `2-8`: container duy trì ít nhất hai consumer và có thể tăng lên tám khi tải tăng.

Tăng consumer thường giúp queue xử lý nhiều message song song, nhưng không đảm bảo throughput tăng tuyến tính. Mỗi consumer có thể cần session, transaction, thread và kết nối đến database hoặc service downstream. Nếu tăng concurrency vượt khả năng của các tài nguyên đó, latency và lỗi timeout có thể tăng.

### Chọn concurrency

Cần cân nhắc:

- Thời gian xử lý trung bình và độ biến động của handler.
- CPU, heap và số thread có thể cấp cho listener.
- Kích thước connection pool của database và giới hạn đồng thời của downstream API.
- Khả năng xử lý song song của broker và destination.
- Thời gian transaction; transaction càng dài càng giữ tài nguyên lâu.
- Số lượng message tồn đọng, tốc độ publish và độ trễ xử lý mục tiêu.

Bắt đầu với concurrency nhỏ, đo throughput/latency và tăng dần. Đặt giới hạn tối đa dựa trên năng lực database và downstream; đừng chỉ dựa vào số core CPU.

### Queue và Topic có hành vi concurrency khác nhau

**Queue:** nhiều consumer thường cạnh tranh nhận message; mỗi message được giao cho một consumer trong nhóm theo chính sách broker. Tăng consumer có thể tăng throughput, nhưng thứ tự hoàn tất xử lý không còn được bảo đảm. Một message xử lý lâu có thể hoàn tất sau message đến sau.

**Topic:** mỗi subscription thông thường nhận bản sao của publication. Tăng nhiều consumer độc lập trên cùng topic có thể khiến mỗi consumer nhận cùng message, tạo xử lý lặp trong ứng dụng. Chỉ tăng concurrency cho topic khi provider hỗ trợ shared subscription và cấu hình Spring/JMS tương ứng đã được kiểm chứng.

Nếu nghiệp vụ yêu cầu thứ tự nghiêm ngặt, thường cần một consumer tuần tự hoặc partition theo khóa nghiệp vụ để các message liên quan đi qua cùng một luồng xử lý. Nếu chỉ cần thứ tự theo từng aggregate, có thể phân vùng theo `orderId` thay vì khóa toàn bộ queue.

## 7. Recovery, cache và giới hạn tài nguyên

DMLC có cơ chế thử kết nối lại khi broker tạm thời không khả dụng. Mặc định, recovery được thử lại theo khoảng thời gian cố định; có thể cấu hình `recoveryInterval` hoặc `BackOff` để giãn thời gian thử lại. Khi broker phục hồi, container tạo lại các tài nguyên nhận message theo lifecycle của nó.

Container cũng quản lý cache connection/session/consumer. Khi không cache, container có thể phải tạo connection/session thường xuyên; khi dùng external transaction manager, việc lấy resource mới có thể cần thiết để resource tham gia đúng JTA transaction. Chỉ thay đổi cache level sau khi hiểu provider, transaction manager và yêu cầu lifecycle.

Không tăng concurrency vô hạn. Hãy đặt giới hạn và theo dõi số consumer thực tế, thread pool, session, queue depth, tuổi message cũ nhất và tỷ lệ rollback.

## 8. Acknowledgement, redelivery và dead-letter

Với cả SMLC và DMLC, `AUTO_ACKNOWLEDGE` mặc định không cung cấp bảo đảm đáng tin cậy cho redelivery khi listener thất bại. Khi cần xử lý message tin cậy, Spring khuyến nghị dùng transacted session hoặc transaction manager bên ngoài phù hợp.

Khi listener ném exception trong local JMS transaction, container rollback. Broker có thể redeliver message; số lần giao lại và chính sách chuyển dead-letter phụ thuộc provider. Một message độc hại hoặc sai schema có thể gây vòng lặp retry và làm queue nghẽn.

Nên có chính sách:

1. Retry có giới hạn cho lỗi tạm thời như database/network timeout.
2. Delay hoặc backoff giữa các lần retry nếu broker/provider hỗ trợ.
3. Dead-letter queue hoặc quarantine sau số lần thất bại đã định.
4. Ghi nhận message ID, correlation ID, destination, exception và delivery count.
5. Quy trình điều tra và phát lại message sau khi sửa nguyên nhân.

Listener phải idempotent vì duplicate có thể xuất hiện sau rollback, redelivery hoặc sự cố trong lúc commit. Với cập nhật database, có thể dùng inbox table/unique key để ghi nhận message đã xử lý cùng transaction nghiệp vụ.

## 9. Ví dụ lựa chọn theo tình huống

| Tình huống | Lựa chọn gợi ý | Lý do |
|---|---|---|
| Queue ít message, tải ổn định, cần cấu hình đơn giản | SMLC + local transaction | Consumer cố định, không cần dynamic scaling/JTA |
| Queue có tải thay đổi theo giờ | DMLC với `concurrency="2-12"` | Tăng/giảm consumer theo tải trong giới hạn |
| Listener cần transaction JMS và gửi reply cùng session | SMLC hoặc DMLC với `sessionTransacted=true` | Các thao tác JMS trong session cùng local transaction |
| Listener cập nhật DB và cần atomic commit với JMS | DMLC + JTA/XA | Hỗ trợ transaction manager bên ngoài khi mọi resource XA được cấu hình đúng |
| Topic có nhiều subscriber độc lập | Một consumer cho mỗi subscription thông thường | Tránh tạo nhiều subscription nhận cùng publication ngoài ý muốn |
| Queue cần thứ tự xử lý nghiêm ngặt | Một consumer hoặc partition/serialize theo khóa | Tránh nhiều consumer hoàn tất sai thứ tự |
| Broker có thể restart và cần tự phục hồi | DMLC | Có recovery/backoff tích hợp |

## 10. Lỗi thường gặp khi chọn container

- **Chọn SMLC rồi kỳ vọng tự scale:** SMLC tạo số consumer cố định lúc khởi động.
- **Dùng SMLC khi cần JTA:** container này không tham gia transaction được quản lý bên ngoài.
- **Dùng DMLC nhưng giữ AUTO_ACKNOWLEDGE:** listener ném exception không đủ để bảo đảm message được redeliver.
- **Bật nhiều consumer cho topic thông thường:** có thể khiến nhiều consumer nhận cùng publication.
- **Tăng concurrency vượt database pool:** listener chờ connection, transaction kéo dài và queue backlog tăng.
- **Dùng XA chỉ để tránh viết idempotency:** XA làm tăng độ phức tạp và chi phí vận hành; cần cân nhắc với outbox/inbox.
- **Cho rằng local JMS transaction bao gồm database:** hai resource có thể commit độc lập.
- **Cho rằng rollback luôn retry vô hạn an toàn:** poison message có thể lặp lại và làm nghẽn queue.
- **Không kiểm tra ordering khi scale:** thứ tự gửi không đảm bảo thứ tự hoàn tất xử lý giữa nhiều consumer.
- **Không đo recovery và cache:** container có thể tạo quá nhiều resource hoặc khôi phục chậm khi broker trở lại.

## 11. Kiểm thử và vận hành

Trước khi triển khai production, nên kiểm tra các tình huống sau:

- Listener thành công: message được commit/acknowledge đúng một lần theo cấu hình.
- Listener ném exception: local transaction rollback và broker redeliver theo chính sách.
- Database lỗi tạm thời: retry không tạo side effect trùng.
- Broker restart hoặc mất mạng: DMLC phục hồi và consumer hoạt động trở lại.
- Tải tăng đột biến: concurrency tăng nhưng không làm cạn database pool hoặc thread pool.
- Tải giảm: số consumer trở về mức cơ sở nếu dynamic scaling được bật.
- Nhiều consumer trên queue: kiểm tra thứ tự, duplicate và phân phối tải.
- Topic subscription: xác nhận mỗi subscriber nhận đúng số bản tin mong đợi.
- Poison message: retry có giới hạn rồi chuyển DLQ/quarantine.
- Shutdown: container dừng có trật tự và message chưa commit được xử lý lại an toàn.

Theo dõi ít nhất queue depth, tuổi message cũ nhất, publish/consume rate, listener duration, số consumer hoạt động, transaction rollback, redelivery, DLQ depth, reconnect count và trạng thái connection pool.

## 12. Quy trình ra quyết định

1. Xác định destination là queue hay topic và yêu cầu ordering.
2. Xác định transaction cần bảo vệ: JMS riêng, JMS cùng reply, hay JMS cùng database.
3. Nếu cần JTA/XA hoặc dynamic scaling, chọn DMLC.
4. Nếu tải cố định và chỉ cần local JMS transaction trong môi trường phù hợp, cân nhắc SMLC.
5. Với yêu cầu giao nhận tin cậy, bật `sessionTransacted=true` hoặc cấu hình transaction manager phù hợp; không dựa vào AUTO_ACKNOWLEDGE.
6. Đặt concurrency min/max theo năng lực broker, database và downstream.
7. Thiết kế retry, redelivery, DLQ và idempotency.
8. Kiểm thử lỗi listener, broker restart, duplicate, ordering và tải cực đại.
9. Theo dõi metrics và điều chỉnh dựa trên dữ liệu production.

## 13. Kết luận

`SimpleMessageListenerContainer` phù hợp với luồng nhận có concurrency cố định và transaction JMS cục bộ. `DefaultMessageListenerContainer` phù hợp với phần lớn ứng dụng cần dynamic scaling, recovery hoặc tham gia transaction được quản lý bên ngoài như JTA/XA.

Với cả hai container, hãy dùng transacted session khi cần redelivery đáng tin cậy. Chọn concurrency theo giới hạn thật của broker, database và downstream; cân nhắc khác biệt queue/topic và thứ tự xử lý. Nếu transaction bao gồm database, quyết định rõ giữa local JMS transaction kết hợp idempotency/inbox-outbox và JTA/XA, rồi kiểm thử rollback, redelivery, recovery và tải đồng thời.

## Tài liệu tham khảo

- [Spring Framework Reference — Using Spring JMS](https://docs.spring.io/spring-framework/reference/integration/jms/using.html)
- [Spring Framework Reference — Receiving a Message](https://docs.spring.io/spring-framework/reference/integration/jms/receiving.html)
- [Spring Framework Reference — Annotation-driven Listener Endpoints](https://docs.spring.io/spring-framework/reference/integration/jms/annotated.html)