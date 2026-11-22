# Quản lý Session khi nhiều luồng cùng gửi hoặc nhận

Trong JMS, Session là ngữ cảnh làm việc để tạo message, gửi message, nhận message và quản lý giao dịch. Một Connection có thể tạo nhiều Session, nhưng một Session được định nghĩa là ngữ cảnh single-threaded: các thao tác trên cùng Session không được thực hiện đồng thời từ nhiều thread. Session cũng tuần tự hóa việc gọi MessageListener gắn với nó.

Điều này rất quan trọng khi ứng dụng cần tăng throughput bằng nhiều luồng. Không nên tạo một Session rồi chia sẻ cho tất cả producer hoặc consumer chạy song song. Hãy tổ chức mỗi luồng xử lý đồng thời với Session và các resource JMS riêng của nó, hoặc giao việc quản lý Session cho Spring JMS listener container và JmsTemplate.

Bài này tập trung vào vòng đời Session, cách gửi/nhận đồng thời, quản lý transaction và acknowledgement, thứ tự message, cấu hình concurrency trong Spring và những lỗi thường gặp khi chia sẻ Session.

## 1. Connection, Session, Producer và Consumer

Một ứng dụng JMS thường có các thành phần sau:

- **ConnectionFactory:** tạo kết nối đến JMS provider, ví dụ ActiveMQ Artemis, IBM MQ hoặc một broker JMS khác.
- **Connection:** kết nối vật lý hoặc logic đến provider. Một Connection có thể tạo nhiều Session.
- **Session:** ngữ cảnh single-threaded dùng để tạo message, producer, consumer và quản lý acknowledgement hoặc transaction.
- **MessageProducer:** gửi message đến destination như Queue hoặc Topic.
- **MessageConsumer:** nhận message từ destination bằng receive hoặc MessageListener.
- **Destination:** nơi gửi/nhận, thường là Queue hoặc Topic.

Quan hệ điển hình:

~~~mermaid
flowchart TD
    F["ConnectionFactory"] --> C["Connection"]
    C --> S1["Session 1"]
    C --> S2["Session 2"]
    C --> S3["Session 3"]
    S1 --> P1["Producer / Consumer"]
    S2 --> P2["Producer / Consumer"]
    S3 --> P3["Producer / Consumer"]
~~~

Connection có thể phục vụ nhiều Session. Mỗi Session quản lý các producer, consumer và trạng thái giao dịch của chính nó. Nhiều Session trên cùng Connection cho phép ứng dụng có nhiều luồng gửi/nhận độc lập mà không phải mở một Connection vật lý cho từng message.

Không nên nhầm Connection với Session. Việc provider cho phép nhiều Session trên một Connection không có nghĩa một Session có thể được nhiều thread sử dụng đồng thời.

## 2. Vì sao Session không được chia sẻ đồng thời?

JMS mô tả Session là một ngữ cảnh single-threaded cho việc gửi và nhận message. Session quản lý trạng thái có thứ tự như:

- MessageProducer và MessageConsumer được tạo từ Session.
- Trạng thái transaction của Session nếu dùng transacted session.
- Acknowledgement của các message nhận trong Session.
- Việc dispatch tuần tự các callback MessageListener trên Session đó.

Nếu hai thread cùng sử dụng một Session tại cùng thời điểm, các thao tác có thể xen kẽ và gây ra hành vi không mong muốn. Ví dụ, một thread commit transaction trong khi thread khác đang gửi message; một thread đóng consumer trong khi thread khác đang receive; hoặc hai thread dùng cùng producer và session state không theo thứ tự ứng dụng mong đợi.

Cần tuân theo các nguyên tắc:

1. Không dùng đồng thời một Session từ nhiều thread.
2. Không chia sẻ MessageProducer hoặc MessageConsumer của Session giữa các thread như thể chúng là thread-safe.
3. Dùng nhiều Session để có nhiều luồng xử lý song song.
4. Đóng producer, consumer và Session theo vòng đời quản lý của ứng dụng hoặc container.
5. Nếu cần pooling/caching, dùng cơ chế được JMS provider hoặc Spring hỗ trợ thay vì tự giữ một Session toàn cục.

Một Session có thể được dùng tuần tự theo cách mà API/provider cho phép, nhưng thiết kế an toàn và dễ kiểm soát nhất là gắn Session với một luồng xử lý hoặc một consumer worker tại một thời điểm.

## 3. Mô hình một Session cho mỗi worker

Giả sử ứng dụng có ba worker gửi message song song. Có thể dùng một Connection chung và ba Session riêng:

~~~java
Connection connection = connectionFactory.createConnection();

Session session1 =
        connection.createSession(false, Session.AUTO_ACKNOWLEDGE);
Session session2 =
        connection.createSession(false, Session.AUTO_ACKNOWLEDGE);
Session session3 =
        connection.createSession(false, Session.AUTO_ACKNOWLEDGE);
~~~

Mỗi worker dùng Session của mình:

~~~text
Worker 1 -> Session 1 -> Producer 1
Worker 2 -> Session 2 -> Producer 2
Worker 3 -> Session 3 -> Producer 3
~~~

Khi nhận message bất đồng bộ, mỗi consumer cũng nên có Session riêng. JMS provider và listener container thường quản lý quan hệ này. Một Session không trở thành nhiều consumer thread chỉ vì có thể tạo nhiều MessageConsumer từ nó; listener callbacks trên cùng Session được tuần tự hóa.

Nếu cần xử lý nhiều message đồng thời, tăng số consumer/session. Cần cân bằng concurrency với năng lực broker, database, downstream service và giới hạn connection/session của provider.

## 4. Gửi đồng thời: dùng JmsTemplate hoặc Session riêng

### 4.1. Chia sẻ JmsTemplate giữa các thread

Trong ứng dụng Spring, JmsTemplate được thiết kế để dùng lại sau khi cấu hình. Nhiều thread có thể gọi các phương thức send/convertAndSend trên cùng một JmsTemplate. Template lấy hoặc tham gia Session phù hợp thông qua ConnectionFactory và cơ chế transaction hiện hành; nó quản lý việc sử dụng tài nguyên trong phạm vi lời gọi.

Ví dụ:

~~~java
@Service
public class OrderPublisher {

    private final JmsTemplate jmsTemplate;

    public OrderPublisher(JmsTemplate jmsTemplate) {
        this.jmsTemplate = jmsTemplate;
    }

    public void publish(OrderCreated event) {
        jmsTemplate.convertAndSend("orders.queue", event);
    }
}
~~~

Service publisher có thể là singleton và được nhiều thread gọi. Điều cần tránh là tự tạo một Session ở field của service rồi dùng nó trong mọi lời gọi. JmsTemplate quản lý Session theo cơ chế Spring JMS; không cần giữ Session trong singleton.

Nên cấu hình template và ConnectionFactory trước khi ứng dụng bắt đầu xử lý tải. Không thay đổi cấu hình dùng chung khi các thread đang gửi message.

### 4.2. Khi dùng JMS API trực tiếp

Nếu không dùng JmsTemplate, mỗi worker nên lấy Session riêng từ Connection. Ví dụ minh họa:

~~~java
Session session = connection.createSession(
        false,
        Session.AUTO_ACKNOWLEDGE
);

MessageProducer producer = session.createProducer(queue);

try {
    TextMessage message = session.createTextMessage("Order ORD-42");
    producer.send(message);
}
finally {
    producer.close();
    session.close();
}
~~~

Đoạn mã cần các import và resource JMS tương ứng. Trong ứng dụng thực tế, việc tạo/đóng Connection và Session nên nằm trong một lifecycle manager, pool hoặc container phù hợp; không nên tạo Connection vật lý mới cho mỗi message nếu không có lý do.

Nếu một worker gửi nhiều message, có thể giữ Session và producer trong suốt vòng đời worker rồi đóng khi worker dừng. Không chia sẻ chúng đồng thời với worker khác.

### 4.3. CachingConnectionFactory

Spring JMS cung cấp CachingConnectionFactory để tái sử dụng Connection và cache Session, MessageProducer hoặc consumer theo cấu hình. Khi ứng dụng đóng Session proxy, tài nguyên có thể được trả về cache thay vì đóng Session vật lý ngay lập tức.

Cache giúp giảm chi phí tạo tài nguyên, nhưng không làm Session trở thành thread-safe. Một Session đang được một thread mượn không được một thread khác dùng đồng thời. Khi trả về cache, Session có thể được tái sử dụng cho một lần mượn khác theo cơ chế quản lý của factory.

Cần cấu hình session cache size dựa trên concurrency thực tế. Nếu số worker vượt quá số Session cache, factory có thể phải tạo thêm Session; cache size không nên bị hiểu nhầm là giới hạn số thread được phép gửi.

## 5. Nhận đồng thời bằng listener container của Spring

Với consumer bất đồng bộ, nên để Spring quản lý Connection, Session và MessageConsumer thông qua listener container. Một container có thể tạo nhiều consumer; mỗi consumer có Session riêng để nhận message và gọi listener.

Ví dụ cấu hình:

~~~java
@Configuration
@EnableJms
public class JmsConfiguration {

    @Bean
    public DefaultJmsListenerContainerFactory jmsListenerContainerFactory(
            ConnectionFactory connectionFactory) {

        DefaultJmsListenerContainerFactory factory =
                new DefaultJmsListenerContainerFactory();

        factory.setConnectionFactory(connectionFactory);
        factory.setConcurrency("3-8");
        factory.setSessionTransacted(true);

        return factory;
    }
}
~~~

Listener:

~~~java
@Component
public class OrderListener {

    @JmsListener(
            destination = "orders.queue",
            concurrency = "3-8"
    )
    public void receive(OrderCreated event) {
        processOrder(event);
    }

    private void processOrder(OrderCreated event) {
        // Xử lý nghiệp vụ.
    }
}
~~~

Tùy cách cấu hình, concurrency được đặt trên factory hoặc annotation. Không cần đặt cả hai nếu không có lý do; annotation có thể ghi đè thiết lập của factory cho listener đó.

Với concurrency 3-8, container có thể duy trì tối thiểu ba consumer và tăng lên tối đa tám consumer theo khả năng điều phối của container. Mỗi consumer có Session riêng. Các listener invocation có thể chạy đồng thời trên nhiều thread.

Một lưu ý quan trọng: bean OrderListener thường là singleton. Phương thức receive có thể được gọi đồng thời trên cùng instance. Vì vậy, không lưu trạng thái mutable theo từng message trong field thông thường; dùng biến local, object bất biến hoặc cấu trúc thread-safe nếu thật sự cần chia sẻ trạng thái.

## 6. Session, transaction và acknowledgement

Session không chỉ quản lý resource mà còn là phạm vi transaction và acknowledgement của JMS. Việc tăng số Session có nghĩa ứng dụng cũng tăng số đơn vị xử lý độc lập.

### 6.1. Non-transacted Session

Ví dụ:

~~~java
Session session = connection.createSession(
        false,
        Session.AUTO_ACKNOWLEDGE
);
~~~

Tham số đầu tiên false nghĩa là Session không dùng transaction JMS. Tham số thứ hai xác định acknowledgement mode.

Các mode phổ biến:

- **AUTO_ACKNOWLEDGE:** provider tự xác nhận message theo quy tắc của chế độ này. Với receive đồng bộ, acknowledgement diễn ra khi receive trả về thành công; với listener, sau khi callback hoàn tất bình thường.
- **CLIENT_ACKNOWLEDGE:** ứng dụng gọi acknowledge trên message. Việc acknowledge có phạm vi theo Session: xác nhận một message có thể xác nhận tất cả message đã được Session đó tiêu thụ trước đó.
- **DUPS_OK_ACKNOWLEDGE:** provider có thể trì hoãn acknowledgement để tăng hiệu năng; consumer cần chấp nhận khả năng nhận trùng.
- **SESSION_TRANSACTED:** chỉ dùng khi tạo Session transacted; acknowledgement mode thông thường không còn được dùng theo cách tương tự.

Vì CLIENT_ACKNOWLEDGE có phạm vi Session, không nên chia sẻ một Session cho nhiều consumer thread rồi kỳ vọng mỗi thread xác nhận độc lập message của mình.

### 6.2. Transacted Session

Có thể tạo Session giao dịch:

~~~java
Session session = connection.createSession(
        true,
        Session.SESSION_TRANSACTED
);

MessageProducer producer = session.createProducer(queue);

try {
    producer.send(session.createTextMessage("Order ORD-42"));
    session.commit();
}
catch (JMSException ex) {
    session.rollback();
    throw ex;
}
finally {
    producer.close();
    session.close();
}
~~~

Một transaction JMS gắn với một Session. commit xác nhận các thao tác gửi và nhận thuộc transaction đó; rollback hủy các message đã gửi trong transaction và làm các message đã nhận được giao lại theo semantics của provider.

Nếu nhiều worker dùng các Session riêng, mỗi worker có transaction riêng. Commit của Session 1 không commit công việc đang thực hiện trong Session 2. Đây là ranh giới quan trọng khi thiết kế batch hoặc xử lý song song.

### 6.3. Transaction của JMS và database

Transaction JMS không tự động trở thành transaction chung với database. Nếu listener cập nhật database rồi acknowledgement message, process có thể gặp lỗi giữa hai thao tác và tạo trạng thái lệch nhau.

Có thể dùng JTA/XA khi cả database và JMS provider hỗ trợ XA và hệ thống được cấu hình transaction coordinator phù hợp. Cách này có chi phí vận hành và hiệu năng cao hơn.

Một lựa chọn khác là Transactional Outbox: ghi dữ liệu nghiệp vụ và bản ghi outbox trong cùng database transaction, sau đó relay gửi message tới JMS destination. Consumer vẫn cần idempotency vì relay hoặc broker có thể tạo delivery lặp trong một số tình huống.

## 7. Ordering khi có nhiều Session và consumer

Một Session tuần tự hóa listener callback của nó, nhưng khi có nhiều Session/consumer, các message có thể được xử lý song song. Vì vậy, thứ tự bắt đầu và hoàn tất xử lý trên toàn hệ thống có thể khác thứ tự gửi.

Ví dụ, message A được consumer 1 nhận trước message B ở consumer 2, nhưng consumer 2 xử lý nhanh hơn nên B hoàn tất trước A. Nếu nghiệp vụ yêu cầu thứ tự theo đơn hàng hoặc khách hàng, cần thiết kế rõ phạm vi ordering.

Các cách thường dùng:

- Chỉ dùng một consumer khi cần thứ tự xử lý toàn queue và throughput cho phép.
- Phân nhóm công việc theo khóa nghiệp vụ để các message cùng nhóm đi qua cùng consumer nếu provider hỗ trợ.
- Dùng sequence number hoặc version để consumer phát hiện message đến sai thứ tự.
- Thiết kế handler idempotent và có thể xử lý event đến trễ.
- Tránh tăng concurrency trước khi xác định ordering nào thực sự cần bảo toàn.

Một số JMS provider hỗ trợ message grouping, thường qua thuộc tính JMSXGroupID. Nếu sử dụng, cần đọc tài liệu provider để biết cách phân phối group và hành vi failover. Không nên giả định mọi provider có cùng cách triển khai.

Với nhiều producer Session, thứ tự giữa các producer cũng không tự tạo thành một thứ tự toàn cục. Nếu cần ordering theo một aggregate, hãy serialize việc phát event của aggregate đó hoặc dùng cơ chế partition/group phù hợp.

## 8. Quản lý vòng đời và giới hạn tài nguyên

Mỗi Session thường tạo thêm producer/consumer và có thể tạo thêm tài nguyên phía broker. Tăng concurrency quá cao có thể làm cạn giới hạn connection, session, consumer hoặc thread.

Một số nguyên tắc:

- Tái sử dụng Connection thông qua ConnectionFactory, pool hoặc caching factory phù hợp.
- Không tạo Connection vật lý cho mỗi message.
- Đóng Session, producer và consumer khi vòng đời worker/container kết thúc.
- Không đóng shared Connection trong khi các worker khác còn sử dụng.
- Giới hạn concurrency theo năng lực broker, database và dịch vụ downstream.
- Theo dõi số Session đang hoạt động, số consumer, backlog, thời gian xử lý và tỷ lệ lỗi.
- Dùng shutdown graceful để dừng nhận message, hoàn tất hoặc rollback công việc đang xử lý rồi đóng resource.
- Không giữ Session trong static field hoặc singleton service để nhiều thread gọi chung.

ConnectionFactory có thể là singleton; JmsTemplate và listener container cũng thường được quản lý như bean dùng chung. Session là resource có phạm vi sử dụng hẹp hơn và cần được quản lý theo thread/consumer hoặc transaction.

## 9. Các lỗi thường gặp khi nhiều luồng cùng gửi hoặc nhận

### 9.1. Dùng chung một Session cho nhiều thread

Triệu chứng có thể là lỗi provider, transaction bị trộn, message không theo thứ tự ứng dụng mong đợi hoặc lỗi khó tái hiện dưới tải.

Cách xử lý: tạo Session riêng cho mỗi worker/consumer đồng thời hoặc dùng JmsTemplate/listener container quản lý Session.

### 9.2. Nghĩ rằng JmsTemplate là Session

JmsTemplate là abstraction tiện ích cấp cao, không phải Session. Có thể chia sẻ một template đã cấu hình giữa các thread; không nên lấy Session từ callback rồi lưu vào field để dùng về sau.

### 9.3. Tăng thread nhưng không tăng Session/consumer

Một Session không tự thực hiện nhiều listener callback song song. Muốn tăng khả năng nhận đồng thời, cấu hình listener container với nhiều consumer để container tạo Session riêng cho từng consumer.

### 9.4. Chia sẻ MessageProducer hoặc MessageConsumer

Producer/consumer được tạo từ Session và phụ thuộc vòng đời Session. Không chia sẻ chúng đồng thời giữa các thread. Hãy để mỗi worker dùng resource của Session riêng.

### 9.5. Dùng CLIENT_ACKNOWLEDGE như acknowledgement theo từng thread

Acknowledgement có phạm vi Session, không phải một acknowledgement độc lập cho từng thread dùng chung Session. Dùng Session riêng cho mỗi consumer giúp phạm vi ack dễ hiểu và kiểm soát hơn.

### 9.6. Concurrency làm thay đổi thứ tự xử lý

Nhiều consumer có thể hoàn tất message theo thứ tự khác nhau. Nếu nghiệp vụ cần ordering, hãy chọn mức concurrency và chiến lược grouping/sequence phù hợp.

### 9.7. Session hoặc consumer bị đóng khi vẫn đang sử dụng

Việc đóng resource dùng chung có thể làm các thao tác đang chạy thất bại. Container nên quản lý lifecycle; với JMS API trực tiếp, worker sở hữu resource phải chịu trách nhiệm đóng nó sau khi dừng công việc.

### 9.8. Retry làm phát sinh tác dụng phụ trùng

Một message có thể được giao lại sau rollback, mất kết nối hoặc lỗi acknowledgement. Dùng message ID hoặc khóa nghiệp vụ để bảo đảm handler idempotent; không dựa vào giả định một message chỉ được xử lý đúng một lần.

## 10. Ví dụ Java 17: mỗi worker sử dụng Session riêng

Ví dụ sau dùng JDK thuần để mô phỏng nguyên tắc một Session riêng cho mỗi tác vụ chạy đồng thời. DemoSession là class minh họa do chương trình tự định nghĩa, không phải javax.jms.Session hay jakarta.jms.Session.

Tạo file **JmsSessionConcurrencyDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.Callable;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class JmsSessionConcurrencyDemo {

    record OrderMessage(String id, String payload) {}

    record DemoSession(String sessionId) {
        String send(OrderMessage message) {
            return sessionId + " sent " + message.id();
        }
    }

    public static void main(String[] args) throws Exception {
        ExecutorService workers = Executors.newFixedThreadPool(3);

        try {
            List<Callable<String>> tasks = new ArrayList<>();

            for (int i = 1; i <= 3; i++) {
                int workerNumber = i;

                tasks.add(() -> {
                    DemoSession session =
                            new DemoSession("session-" + workerNumber);

                    OrderMessage message = new OrderMessage(
                            "msg-" + workerNumber,
                            "OrderCreated"
                    );

                    return session.send(message);
                });
            }

            List<Future<String>> results = workers.invokeAll(tasks);

            // invokeAll giữ thứ tự Future theo thứ tự task đầu vào.
            for (Future<String> result : results) {
                System.out.println(result.get());
            }
        }
        finally {
            workers.shutdown();
        }
    }
}
~~~

Biên dịch và chạy bằng Java 17 trở lên:

~~~bash
javac JmsSessionConcurrencyDemo.java
java JmsSessionConcurrencyDemo
~~~

Kết quả:

~~~text
session-1 sent msg-1
session-2 sent msg-2
session-3 sent msg-3
~~~

Ví dụ tạo một DemoSession bên trong từng task. Ba task có thể chạy đồng thời nhưng không chia sẻ cùng một Session object. Đây chỉ là mô hình minh họa ownership; nó không kết nối tới JMS broker và không kiểm thử semantics của một JMS provider.

## 11. Cách kiểm thử concurrency và transaction

Khi triển khai thực tế, nên kiểm tra trên JMS provider mà ứng dụng sử dụng:

- **Session isolation:** xác nhận mỗi consumer/worker có Session riêng và không có Session được gọi đồng thời.
- **Concurrent sending:** gửi từ nhiều worker và xác nhận số message, payload và message ID chính xác.
- **Concurrent receiving:** tăng concurrency và xác nhận các message được phân phối, xử lý đúng một lần theo mức bảo đảm của cấu hình.
- **Transaction rollback:** làm handler ném exception trong transacted Session, xác nhận rollback và redelivery theo provider.
- **Acknowledgement:** kiểm tra AUTO_ACKNOWLEDGE, CLIENT_ACKNOWLEDGE hoặc transacted mode theo đúng phạm vi Session.
- **Ordering:** gửi chuỗi message có sequence number và quan sát thứ tự nhận/hoàn tất khi tăng consumer.
- **Shutdown:** dừng container khi đang xử lý để xác nhận resource được đóng và message chưa commit được phục hồi theo cấu hình.
- **Load test:** tăng concurrency từng bước, theo dõi số Session, thread, consumer, throughput, latency và backlog.

Không chỉ kiểm tra rằng chương trình không ném exception. Cần xác nhận không mất message, không tạo tác dụng phụ trùng, transaction rollback đúng và giới hạn tài nguyên được giữ trong mức vận hành cho phép.

## 12. Quy trình lựa chọn concurrency

Trước khi tăng số luồng, hãy trả lời:

1. Mỗi worker có Session riêng chưa?
2. Producer có đang dùng JmsTemplate hoặc resource được quản lý đúng vòng đời không?
3. Consumer có được listener container tạo với concurrency phù hợp không?
4. Listener bean có an toàn khi nhiều invocation chạy đồng thời không?
5. Transaction và acknowledgement có phạm vi rõ theo từng Session không?
6. Ordering cần bảo toàn ở mức toàn queue, destination hay theo khóa nghiệp vụ?
7. Broker và downstream service có đủ năng lực cho số consumer dự kiến không?
8. Retry, redelivery và idempotency đã được thiết kế chưa?

JMS Session là đơn vị quản lý trạng thái gửi/nhận, acknowledgement và transaction. Khi nhiều thread cùng hoạt động, hãy dùng nhiều Session độc lập hoặc để Spring quản lý Session qua JmsTemplate và listener container. Tăng concurrency bằng cách tăng số consumer/session giúp xử lý song song có kiểm soát; chia sẻ một Session đồng thời chỉ làm phát sinh race condition, transaction lẫn nhau và lỗi khó chẩn đoán.