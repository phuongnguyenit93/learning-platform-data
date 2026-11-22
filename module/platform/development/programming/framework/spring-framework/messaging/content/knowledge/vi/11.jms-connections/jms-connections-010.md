# Đóng tài nguyên, đặt lại kết nối và xử lý broker mất kết nối

> Mục tiêu: quản lý đúng vòng đời Connection, Session, Producer và Consumer của JMS; đóng tài nguyên an toàn khi kết thúc; nhận biết lỗi kết nối broker; khôi phục luồng gửi/nhận có backoff; và xử lý đúng các trường hợp message có thể đã được gửi hoặc xác nhận trước khi kết nối bị đứt.

## 1. Vì sao vòng đời tài nguyên JMS quan trọng?

Một ứng dụng JMS làm việc qua nhiều lớp tài nguyên: `ConnectionFactory` tạo `Connection`; connection tạo `Session`; session tạo `MessageProducer` và `MessageConsumer`. Các tài nguyên này thường giữ socket, session state, consumer registration và trạng thái giao dịch với broker.

Nếu không đóng tài nguyên đúng lúc, ứng dụng có thể rò rỉ connection, session, consumer hoặc thread; broker có thể tiếp tục giữ subscription; connection pool bị cạn; và quá trình deploy/shutdown trở nên chậm hoặc không ổn định. Ngược lại, đóng một tài nguyên còn được thành phần khác sử dụng có thể làm gián đoạn message đang xử lý.

Cần xác định rõ **ai sở hữu tài nguyên và ai chịu trách nhiệm đóng nó**:

| Tài nguyên | Vai trò | Chủ sở hữu thường gặp |
|---|---|---|
| `ConnectionFactory` | Tạo connection đến provider | Application context hoặc cấu hình hạ tầng |
| `Connection` | Kết nối client với provider | Component tạo connection hoặc Spring connection factory/container |
| `Session` | Ngữ cảnh tạo message và transaction | Thread/consumer hoặc listener container quản lý |
| `MessageProducer` | Gửi đến destination | Session hoặc component gửi |
| `MessageConsumer` | Nhận từ destination | Session hoặc listener container |

Trong mã JMS thuần, component tạo tài nguyên thường phải đóng tài nguyên đó. Trong Spring JMS, `JmsTemplate` và listener container quản lý các tài nguyên mà chúng tạo; không tự ý đóng connection/session do Spring đang quản lý.

## 2. Thứ tự đóng tài nguyên

Khi ứng dụng tự tạo tài nguyên bằng JMS API, nên đóng theo thứ tự ngược với lúc tạo:

1. Ngừng nhận thêm message hoặc dừng producer gửi công việc mới.
2. Đóng `MessageConsumer` và `MessageProducer`.
3. Đóng `Session`.
4. Đóng `Connection`.

Đóng connection cũng sẽ đóng các session và đối tượng con thuộc connection đó theo hợp đồng JMS. Tuy nhiên, đóng từng tài nguyên con trước giúp thể hiện rõ quyền sở hữu, tránh giữ consumer/producer lâu hơn cần thiết và giúp xử lý lỗi đóng tài nguyên có kiểm soát.

`Connection.stop()` chỉ tạm dừng phân phối message đến consumer; nó không giải phóng connection. `close()` mới kết thúc connection và giải phóng các tài nguyên con. Nếu muốn tiếp tục sử dụng sau một khoảng tạm dừng, có thể dùng `stop()` rồi `start()` theo đúng lifecycle; không dùng `stop()` thay cho `close()` khi shutdown.

### Ví dụ quản lý tài nguyên thủ công

```java
import jakarta.jms.Connection;
import jakarta.jms.ConnectionFactory;
import jakarta.jms.JMSException;
import jakarta.jms.MessageConsumer;
import jakarta.jms.Queue;
import jakarta.jms.Session;

void receiveOne(ConnectionFactory connectionFactory) throws JMSException {
    Connection connection = connectionFactory.createConnection();
    try {
        Session session = connection.createSession(
                false, Session.AUTO_ACKNOWLEDGE);
        try {
            Queue queue = session.createQueue("orders.incoming");
            MessageConsumer consumer = session.createConsumer(queue);
            try {
                connection.start();
                consumer.receive(2_000);
            } finally {
                consumer.close();
            }
        } finally {
            // Đóng session ngay cả khi receive hoặc consumer.close thất bại.
            // Mã production nên giữ lại exception gốc nếu close cũng lỗi.
            session.close();
        }
    } finally {
        connection.close();
    }
}
```

Đây là ví dụ minh họa thứ tự đóng tài nguyên. Mã production nên dùng helper hoặc try-with-resources nếu phiên bản JMS API đang dùng hỗ trợ `AutoCloseable`, đồng thời bảo đảm exception phát sinh trong lúc đóng không che mất exception chính. Ví dụ chỉ nhận một message rồi kết thúc; consumer chạy lâu dài nên được quản lý bởi listener container thay vì tạo/đóng connection cho từng lần nhận.

Không chia sẻ một `Session`, `MessageProducer` hoặc `MessageConsumer` cho nhiều thread đồng thời. Nếu cần xử lý song song, tạo nhiều session/consumer thông qua container hoặc cơ chế pool phù hợp.

## 3. Shutdown có trật tự

Khi ứng dụng dừng, mục tiêu là ngừng nhận công việc mới, cho công việc đang chạy hoàn tất trong khoảng thời gian cho phép, sau đó giải phóng tài nguyên.

Một trình tự shutdown thường dùng:

1. Đánh dấu ứng dụng không nhận thêm công việc mới.
2. Dừng listener container hoặc gọi `Connection.stop()` để tạm ngừng dispatch message mới.
3. Chờ các handler đang chạy hoàn tất trong thời gian graceful shutdown đã định.
4. Commit hoặc rollback transaction đang mở theo kết quả xử lý.
5. Đóng consumer/producer, session và connection do ứng dụng sở hữu.
6. Đóng executor, scheduler và các thành phần phụ thuộc sau khi không còn task sử dụng chúng.

Nếu process bị kill đột ngột hoặc thời gian shutdown hết hạn, broker có thể giao lại message chưa được xác nhận. Vì vậy, shutdown có trật tự giúp giảm gián đoạn nhưng không thay thế idempotency và redelivery handling.

Trong Spring, listener container có lifecycle do application context quản lý. Hãy để Spring start/stop container theo lifecycle; không gọi `close()` lên connection hoặc session mà container đang sở hữu. Có thể cấu hình thời gian chờ shutdown và concurrency theo yêu cầu triển khai.

## 4. Nhận biết broker mất kết nối

Broker có thể mất kết nối do restart, network partition, DNS hoặc TLS issue, credential hết hạn, giới hạn connection, failover, timeout hoặc sự cố hạ tầng. Lỗi có thể xuất hiện ở nhiều thời điểm:

- Khi tạo connection hoặc session.
- Khi gửi message bằng `send()`.
- Khi consumer đang chờ `receive()`.
- Trong callback `MessageListener` hoặc lúc acknowledge/commit.
- Khi connection đang idle nhưng provider phát hiện socket đã chết.

JMS thường biểu diễn lỗi bằng `JMSException`. Exception có thể cung cấp `getErrorCode()` và `getLinkedException()`; provider còn có thể gắn nguyên nhân gốc theo cách riêng. Hãy giữ cause chain và thông tin provider để điều tra.

### ExceptionListener

JMS `Connection` hỗ trợ đăng ký `ExceptionListener`. Provider gọi listener khi phát hiện một lỗi nghiêm trọng liên quan đến connection:

```java
connection.setExceptionListener(exception -> {
    Throwable linked = exception.getLinkedException();
    System.err.println("JMS connection problem: " + exception.getMessage());
    if (linked != null) {
        linked.printStackTrace(System.err);
    }
});
```

Đoạn mã chỉ minh họa callback. Trong ứng dụng thực tế, nên ghi log có cấu trúc và phát tín hiệu cho cơ chế recovery. Không nên thực hiện reconnect blocking hoặc chạy một quy trình phục hồi dài ngay trên thread callback của provider; callback nên nhanh và an toàn khi có nhiều lỗi gần nhau.

`ExceptionListener` không phải bộ bắt mọi lỗi nghiệp vụ. Một lỗi khi parse payload hoặc exception trong service có thể không phải lỗi connection và cần đi qua error handling của listener/container. Ngoài ra, không phải mọi provider đều phát hiện network failure ngay lập tức; heartbeat và timeout phụ thuộc cấu hình provider.

## 5. Điều gì không chắc chắn khi kết nối bị đứt?

Một điểm khó trong messaging là client có thể mất kết nối đúng lúc gửi hoặc xác nhận message. Khi đó client đôi khi không biết broker đã thực hiện thao tác hay chưa.

| Thời điểm mất kết nối | Điều client biết | Rủi ro cần xử lý |
|---|---|---|
| Trước khi broker nhận send | Có thể send chưa đến broker | Có thể cần gửi lại |
| Broker đã nhận nhưng phản hồi send bị mất | Client không biết send đã thành công chưa | Gửi lại có thể tạo duplicate |
| Consumer đã xử lý nhưng acknowledgement chưa đến broker | Broker có thể xem message chưa được xác nhận | Message có thể được redeliver |
| Broker đã xác nhận nhưng consumer chưa ghi nhận kết quả cục bộ | Client không có bằng chứng hoàn tất ở phía ứng dụng | Cần đối soát hoặc idempotency |

Không được giả định timeout hoặc exception đồng nghĩa message chắc chắn chưa được gửi. Khi kết quả không rõ ràng, retry phải dựa trên message ID/business key ổn định và consumer phải xử lý duplicate an toàn.

## 6. Khôi phục kết nối trong ứng dụng JMS thuần

Nếu ứng dụng tự quản lý connection lâu dài, recovery cần tạo lại toàn bộ nhóm tài nguyên gắn với connection lỗi. Một session, producer hoặc consumer thuộc connection đã hỏng không nên được tái sử dụng như thể chúng vẫn hợp lệ.

Quy trình phục hồi tổng quát:

1. Đánh dấu kết nối hiện tại không còn khả dụng và ngừng gửi/nhận mới trên nhóm tài nguyên đó.
2. Ghi nhận lỗi, destination, thời điểm, số lần thử và các message đang xử lý.
3. Đóng các consumer, producer, session và connection cũ nếu provider còn cho phép; bỏ tham chiếu đến chúng nếu không thể đóng.
4. Chờ theo backoff có giới hạn và jitter để tránh nhiều instance reconnect đồng loạt.
5. Tạo connection mới từ `ConnectionFactory`.
6. Tạo session, producer/consumer và listener mới; đăng ký lại `ExceptionListener` nếu cần.
7. Gọi `Connection.start()` khi consumer đã sẵn sàng nhận message.
8. Đánh dấu kết nối healthy và tiếp tục xử lý; tiếp tục giám sát redelivery và duplicate.

Backoff thường tăng dần, ví dụ 1 giây, 2 giây, 4 giây, 8 giây rồi giữ ở một mức tối đa. Có thể thêm jitter ngẫu nhiên để nhiều instance không cùng reconnect vào một thời điểm. Giới hạn số lần thử hoặc chuyển sang trạng thái degraded/alert theo yêu cầu vận hành.

Không tạo connection mới trong một vòng lặp nóng khi broker đang down. Cách đó có thể gây bão kết nối, tăng tải broker và làm quá trình phục hồi chậm hơn.

### Pseudocode cho recovery loop

```text
while application is running:
    try:
        create connection
        create session and producer/consumer
        start connection when receiving
        process messages
    catch connection failure:
        mark resources unavailable
        close/discard failed resources
        wait using bounded exponential backoff + jitter
        continue
    finally:
        close resources owned by this loop
```

Đây là pseudocode mô tả chiến lược, không phải mã Java có thể chạy trực tiếp. Trong ứng dụng Spring, nên ưu tiên recovery đã được cung cấp bởi listener container hoặc connection factory thay vì tự viết vòng lặp quản lý thread và session.

## 7. Spring CachingConnectionFactory và resetConnection()

Spring JMS có `CachingConnectionFactory`, một wrapper trên `ConnectionFactory` có thể chia sẻ connection và cache session, producer, cùng consumer nếu bật tùy chọn tương ứng. Nó giúp giảm chi phí tạo tài nguyên lặp lại, nhưng cần cấu hình theo mô hình ứng dụng.

Một số điểm cần hiểu:

- `setSessionCacheSize(...)` đặt số session tối đa được cache theo từng connection.
- Producer caching có thể giảm việc tạo producer liên tục.
- Consumer caching cần cân nhắc kỹ; không phải mọi mô hình listener container đều phù hợp với việc cache consumer bên ngoài.
- `resetConnection()` buộc connection dùng chung và các tài nguyên cache liên quan được reset để lần sử dụng tiếp theo tạo tài nguyên mới.
- Cơ chế tự reconnect khi provider phát exception phụ thuộc `ExceptionListener`, cấu hình `reconnectOnException` và khả năng của provider.

Ví dụ cấu hình wrapper:

```java
import jakarta.jms.ConnectionFactory;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.connection.CachingConnectionFactory;

@Configuration
class JmsConnectionConfiguration {
    @Bean
    CachingConnectionFactory cachingConnectionFactory(
            ConnectionFactory targetConnectionFactory) {
        CachingConnectionFactory factory =
                new CachingConnectionFactory(targetConnectionFactory);
        factory.setSessionCacheSize(10);
        factory.setCacheProducers(true);
        factory.setCacheConsumers(false);
        factory.setReconnectOnException(true);
        return factory;
    }
}
```

Ví dụ trên minh họa một chiến lược cache phổ biến, không phải cấu hình tối ưu cho mọi provider. Không bọc thêm `CachingConnectionFactory` nếu application đã dùng một connection pool hoặc wrapper có caching khác mà chưa hiểu cách chúng phối hợp. Cache size cần được đo theo concurrency và số session thực tế.

Khi cần buộc reset sau sự cố được phát hiện bởi tầng giám sát, có thể gọi `resetConnection()` trên wrapper do ứng dụng sở hữu. Không gọi reset tùy tiện trong lúc các thread khác vẫn đang dùng connection; cần phối hợp với lifecycle của producer/consumer.

## 8. Spring listener container tự phục hồi

Với consumer chạy nền, `DefaultMessageListenerContainer` quản lý connection, session, consumer và listener thread. Container có cơ chế recovery khi broker hoặc connection gặp sự cố; nó có thể thử thiết lập lại tài nguyên theo recovery interval hoặc `BackOff` được cấu hình.

Ví dụ cấu hình factory:

```java
import jakarta.jms.ConnectionFactory;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.annotation.EnableJms;
import org.springframework.jms.config.DefaultJmsListenerContainerFactory;

@Configuration
@EnableJms
class JmsListenerConfiguration {
    @Bean
    DefaultJmsListenerContainerFactory jmsListenerContainerFactory(
            ConnectionFactory connectionFactory) {
        var factory = new DefaultJmsListenerContainerFactory();
        factory.setConnectionFactory(connectionFactory);
        factory.setConcurrency("2-8");
        factory.setSessionTransacted(true);
        factory.setRecoveryInterval(5_000L);
        return factory;
    }
}
```

Trong ví dụ, container dùng từ 2 đến 8 consumer, session có transaction cục bộ và thử recovery theo khoảng thời gian 5 giây. Có thể cấu hình `BackOff` để dùng lịch retry tăng dần. Giá trị thực tế cần phù hợp với broker, thời gian outage dự kiến và tải của ứng dụng.

Listener có thể dùng factory này:

```java
import org.springframework.jms.annotation.JmsListener;
import org.springframework.stereotype.Component;

@Component
class OrderListener {
    @JmsListener(
            destination = "orders.incoming",
            containerFactory = "jmsListenerContainerFactory"
    )
    public void receive(String json) {
        processOrder(json);
    }
}
```

Khi listener ném exception trong session transacted, container rollback session theo cấu hình và provider có thể giao lại message. Recovery của container xử lý connection/listener infrastructure; nó không sửa payload sai, không bảo đảm business operation idempotent và không thay thế dead-letter policy.

## 9. JmsTemplate và lỗi gửi message

`JmsTemplate` quản lý việc lấy và giải phóng connection/session/producer cho từng thao tác gửi hoặc receive đồng bộ. Nếu dùng `CachingConnectionFactory` hoặc pool, tài nguyên có thể được tái sử dụng bên dưới.

```java
import org.springframework.jms.core.JmsTemplate;
import org.springframework.stereotype.Service;

@Service
class OrderPublisher {
    private final JmsTemplate jmsTemplate;

    OrderPublisher(JmsTemplate jmsTemplate) {
        this.jmsTemplate = jmsTemplate;
    }

    void publish(String json) {
        jmsTemplate.convertAndSend("orders.incoming", json);
    }
}
```

Nếu broker không khả dụng, thao tác gửi có thể ném `JmsException` (Spring bọc lỗi JMS ở dạng runtime exception). Caller cần phân biệt lỗi tạm thời với lỗi cấu hình hoặc dữ liệu, áp dụng retry có giới hạn khi an toàn và ghi nhận trạng thái khi kết quả send không rõ ràng.

Không nên tạo `JmsTemplate` mới hoặc connection mới cho mỗi lần retry. Hãy tái sử dụng bean đã cấu hình, để connection factory quản lý tài nguyên và để retry policy quyết định thời điểm thử lại.

## 10. Retry, redelivery và idempotency

Khi broker mất kết nối, message chưa được xác nhận có thể được giao lại sau khi consumer kết nối trở lại. Khi producer không nhận được phản hồi gửi, producer có thể phải thử lại dù broker đã nhận message trước đó. Vì vậy, hệ thống cần giả định duplicate có thể xảy ra.

Các biện pháp quan trọng:

- Dùng message ID hoặc business key ổn định để nhận diện message.
- Thiết kế handler idempotent: xử lý cùng một command/event nhiều lần không tạo side effect lặp.
- Ghi nhận trạng thái đã xử lý và cập nhật nghiệp vụ trong cùng transaction phù hợp.
- Phân biệt retry lỗi kết nối tạm thời với lỗi schema, validation hoặc business rejection không thể tự phục hồi.
- Dùng backoff, giới hạn số lần retry và dead-letter queue/quarantine cho message không xử lý được.
- Theo dõi redelivery flag, delivery count hoặc metadata tương đương do provider cung cấp.

Không retry vô hạn trong listener thread. Nếu message bị lỗi vĩnh viễn, retry chỉ làm queue bị nghẽn và tiêu tốn tài nguyên. Hãy chuyển message sang DLQ sau ngưỡng đã định và cung cấp quy trình điều tra/phát lại.

## 11. Transaction khi broker mất kết nối

Nếu session dùng transaction cục bộ, `commit()` xác nhận các thao tác JMS trong transaction và `rollback()` hủy các thao tác chưa commit theo semantics của provider. Nếu kết nối bị đứt đúng lúc commit, client có thể không biết broker đã commit hay chưa. Đây là một trường hợp kết quả không rõ ràng, cần deduplication hoặc đối soát.

Transaction JMS không tự động bao trùm transaction database. Nếu listener ghi database rồi connection mất trước acknowledgement, broker có thể giao lại message và database có thể nhận cùng tác động lần nữa. Có thể dùng inbox/deduplication table, unique business key hoặc XA/JTA khi toàn bộ resource hỗ trợ và chi phí phù hợp.

Không bắt exception rồi trả về bình thường nếu xử lý chưa hoàn tất; container có thể xem listener thành công và acknowledge message. Hãy để exception và transaction semantics thể hiện đúng kết quả xử lý.

## 12. Giám sát sức khỏe kết nối và broker

Nên theo dõi cả trạng thái kết nối và tình trạng backlog:

- Connection/session hiện hoạt và số lần reconnect.
- Thời gian từ lúc phát hiện lỗi đến khi consumer hoạt động lại.
- Số message gửi thất bại, receive timeout và listener exception.
- Queue depth, tuổi của message cũ nhất và tốc độ publish/consume.
- Redelivery count, rollback, retry và DLQ depth.
- Số consumer hoạt động so với concurrency cấu hình.
- CPU, thread pool, heap và thời gian chờ connection/session.

Log nên có destination, message ID, correlation ID, provider error code và nguyên nhân gốc. Không ghi password, token hoặc toàn bộ payload nhạy cảm. Cảnh báo nên dựa trên thời gian outage, số lần reconnect và backlog tăng, tránh phát cảnh báo riêng cho từng retry bình thường.

## 13. Lỗi thường gặp

- **Không đóng consumer/session/connection tự tạo:** gây rò rỉ tài nguyên và subscription còn tồn tại.
- **Đóng connection dùng chung do Spring quản lý:** làm gián đoạn các thành phần khác; chỉ đóng tài nguyên mà component sở hữu.
- **Đóng parent trước child mà không có kế hoạch:** khó xác định lỗi đóng và lifecycle; nên đóng consumer/producer, session rồi connection.
- **Gọi `stop()` rồi cho rằng đã giải phóng connection:** `stop()` chỉ tạm dừng dispatch; `close()` mới giải phóng tài nguyên.
- **Tạo connection mới trong mỗi lần gửi:** tăng overhead và có thể làm cạn broker connection limit.
- **Tái sử dụng Session hoặc Consumer sau khi connection hỏng:** tài nguyên con có thể đã invalid; cần tạo lại nhóm tài nguyên.
- **Reconnect liên tục không backoff:** tạo bão kết nối khi broker đang phục hồi.
- **Giả định send timeout nghĩa là broker chưa nhận message:** kết quả có thể không rõ ràng; gửi lại có thể tạo duplicate.
- **Không xử lý redelivery:** listener có thể thực hiện side effect nhiều lần sau rollback hoặc mất acknowledgement.
- **Dùng retry để xử lý payload sai:** lỗi dữ liệu vĩnh viễn cần reject, sửa hoặc DLQ thay vì retry vô hạn.
- **Tự quản lý recovery song song với listener container:** hai cơ chế có thể tranh quyền tạo/đóng session và consumer.
- **Không có graceful shutdown:** message đang xử lý có thể bị ngắt giữa transaction hoặc phải redeliver.

## 14. Quy trình triển khai và kiểm thử

1. Xác định tài nguyên do ứng dụng tự tạo và tài nguyên do Spring/container sở hữu.
2. Viết lifecycle rõ ràng: start, stop, close; đóng tài nguyên theo thứ tự consumer/producer → session → connection.
3. Với mã JMS thuần, kiểm thử cả đường thành công và lỗi khi tạo, gửi, nhận hoặc đóng tài nguyên.
4. Cấu hình `ExceptionListener` nếu ứng dụng tự quản lý connection và cần tín hiệu lỗi từ provider.
5. Với Spring listener, cấu hình concurrency, transaction và recovery/backoff trong listener container.
6. Chọn caching hoặc pooling phù hợp; tránh cache/pool chồng chéo mà không hiểu ownership.
7. Mô phỏng broker restart, network interruption, send timeout, listener exception và lỗi trong lúc commit/acknowledge.
8. Xác nhận connection/session/consumer được tạo lại và message chưa xác nhận được xử lý theo chính sách redelivery.
9. Kiểm thử duplicate để chứng minh handler idempotent và side effect không bị lặp.
10. Kiểm tra graceful shutdown, metrics, log và DLQ trong môi trường tích hợp.

## 15. Kết luận

Trong JMS thuần, component sở hữu tài nguyên phải đóng consumer/producer, session và connection theo thứ tự phù hợp; connection có thể tạm dừng bằng `stop()` và kết thúc bằng `close()`. Khi broker mất kết nối, session và các đối tượng con có thể không còn dùng được, nên recovery phải tạo lại nhóm tài nguyên với backoff và theo dõi trạng thái.

Trong Spring JMS, ưu tiên để `JmsTemplate`, `CachingConnectionFactory` và listener container quản lý lifecycle/recovery theo cấu hình. Dù framework có thể tự kết nối lại, kết quả gửi hoặc acknowledge ở thời điểm mất mạng vẫn có thể không rõ ràng và message có thể được giao lại. Consumer idempotent, retry có giới hạn, dead-letter và graceful shutdown là các phần bắt buộc để hệ thống phục hồi an toàn.