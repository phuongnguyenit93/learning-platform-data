# SessionCallback và ProducerCallback cho thao tác tùy chỉnh với JmsTemplate

## 1. Tại sao cần callback khi đã có JmsTemplate?

Trong Spring Framework JMS, JmsTemplate cung cấp các phương thức thuận tiện như convertAndSend(...), send(...), receive(...), receiveAndConvert(...) và sendAndReceive(...). Với một thông điệp cần gửi, các phương thức này thường đã đủ: Spring tạo/lấy JMS Connection và Session, chuyển đổi body, tạo producer/consumer, gọi JMS API rồi dọn tài nguyên.

Nhưng có tình huống cần **nhiều thao tác trên cùng JMS Session** hoặc cần tùy chỉnh trực tiếp MessageProducer:

- Gửi hai message vào hai Queue khác nhau bằng cùng Session, có thể nằm trong một JMS transaction được quản lý đúng cách.
- Tạo nhiều TextMessage/MapMessage với headers và properties riêng, rồi gửi liên tiếp qua một MessageProducer.
- Đặt delivery mode, priority và time-to-live khác nhau cho từng lần gửi, thay vì áp một cấu hình chung.
- Tạo QueueBrowser hoặc MessageConsumer với selector phục vụ một thao tác JMS chuyên biệt.
- Trích xuất metadata của message ngay trong ngữ cảnh Session, trước khi JmsTemplate giải phóng tài nguyên.

Hai callback được Spring thiết kế cho nhu cầu này:

1. **SessionCallback<T>**: cấp trực tiếp jakarta.jms.Session, cho phép thao tác ở mức Session.
2. **ProducerCallback<T>**: cấp cả jakarta.jms.Session và jakarta.jms.MessageProducer, thuận tiện khi thao tác xoay quanh việc gửi nhiều message.

Cả hai được thực thi qua **JmsTemplate.execute(...)**. Phần callback chạy **đồng bộ trên luồng gọi**; nó không tự tạo background worker và cũng không tự bảo đảm các lệnh trong callback là một transaction nguyên tử.

## 2. Nằm ở đâu trong kiến trúc Spring JMS?

~~~mermaid
flowchart TD
    A["Application Service"] --> B{"JMS operation"}
    B -->|Gửi đơn giản| C["convertAndSend / send"]
    B -->|Nhận đơn giản| D["receive / receiveAndConvert"]
    B -->|Nhiều bước, cần Session| E["execute(SessionCallback)"]
    B -->|Tùy chỉnh MessageProducer| F["execute(ProducerCallback)"]
    C --> G["JmsTemplate"]
    D --> G
    E --> G
    F --> G
    G --> H["ConnectionFactory / Session"]
    H --> I["JMS Provider / Broker"]
~~~

JmsTemplate đóng vai trò **template method**: nó thiết lập bối cảnh tài nguyên, gọi phần code tùy chỉnh và dọn tài nguyên khi trả về hoặc gặp lỗi.

Với callback, ứng dụng cần hiểu ranh giới ownership:

| Tài nguyên | Thành phần thường sở hữu | Trách nhiệm trong callback |
| --- | --- | --- |
| Connection | JmsTemplate/ConnectionFactory/transaction manager | Không tự close hoặc giữ lại sau khi callback kết thúc. |
| Session truyền vào | JmsTemplate hoặc Spring transaction manager | Sử dụng tuần tự trong callback; không tự close, không chuyển sang thread khác. |
| MessageProducer truyền vào ProducerCallback | JmsTemplate | Không tự close; JmsTemplate đóng khi callback kết thúc. |
| MessageProducer tự tạo trong SessionCallback | Code ứng dụng | Phải đóng qua try-with-resources hoặc finally. |
| MessageConsumer/QueueBrowser tự tạo | Code ứng dụng | Đóng tài nguyên đã tạo, kể cả khi callback lỗi. |
| Message/giá trị trả về | Code ứng dụng | Trả kết quả độc lập như String, DTO, số đếm; tránh trả về handle JMS cần Session đang sống. |

Khi Session do Spring transaction manager gắn với thread, “dọn tài nguyên” có thể là trả về/bỏ liên kết đúng vòng đời transaction thay vì đóng vật lý ngay. Callback **không sở hữu** Connection hoặc Session để tự ý đóng.

## 3. Chữ ký API cần biết

### 3.1. SessionCallback<T>

Trong package **org.springframework.jms.core**:

~~~java
@FunctionalInterface
public interface SessionCallback<T> {
    T doInJms(jakarta.jms.Session session)
            throws jakarta.jms.JMSException;
}
~~~

Đây là chữ ký rút gọn để giải thích; interface thực tế đã có sẵn trong spring-jms. T là kiểu kết quả do callback trả về; có thể là String, Integer, record nghiệp vụ, hoặc Void/null nếu chỉ cần side effect.

Hai overload hữu ích của JmsTemplate:

~~~java
<T> T execute(SessionCallback<T> action);

<T> T execute(SessionCallback<T> action, boolean startConnection);
~~~

Lời gọi execute(action) mặc định **không start JMS Connection chỉ để thực thi callback**. Nó phù hợp cho gửi message hoặc thao tác Session không cần incoming delivery. Nếu callback tự tạo MessageConsumer và gọi receive(...), thường phải dùng execute(action, true), hoặc sử dụng trực tiếp receive()/receiveSelected() của JmsTemplate (cách được khuyến khích trong trường hợp nhận thông thường).

### 3.2. ProducerCallback<T>

Trong cùng package:

~~~java
@FunctionalInterface
public interface ProducerCallback<T> {
    T doInJms(
            jakarta.jms.Session session,
            jakarta.jms.MessageProducer producer)
            throws jakarta.jms.JMSException;
}
~~~

Các overload tương ứng trên JmsTemplate:

~~~java
<T> T execute(ProducerCallback<T> action);

<T> T execute(
        jakarta.jms.Destination destination,
        ProducerCallback<T> action);

<T> T execute(
        String destinationName,
        ProducerCallback<T> action);
~~~

Đây là chữ ký API minh họa, chưa phải một file Java có thể chạy độc lập.

- Truyền **String destinationName**: JmsTemplate sử dụng DestinationResolver để chuyển thành Destination rồi tạo producer gắn với đích đó.
- Truyền **Destination object**: dùng trực tiếp Destination được cung cấp.
- Không truyền destination: dùng default destination nếu đã cấu hình; nếu không có default, JmsTemplate có thể tạo producer không gắn đích (anonymous producer), và trong callback phải gửi bằng overload có tham số Destination.
- Tại callback, producer đã được tạo trong đúng Session; Spring đóng producer sau khi callback kết thúc.

Không nhầm ProducerCallback với MessageCreator: ProducerCallback **tự gửi message**, trong khi MessageCreator chủ yếu **tạo Message**, còn JmsTemplate.send(...) thực hiện gửi.

### 3.3. Lambda giúp code gọn

~~~java
Integer count = jmsTemplate.execute(
        (SessionCallback<Integer>) session -> {
            // Làm việc với session.
            return 2;
        });

Integer sent = jmsTemplate.execute(
        "orders.requests",
        (session, producer) -> {
            // Làm việc với session và producer.
            return 2;
        });
~~~

Đây là snippet, biến jmsTemplate đã được inject trong ứng dụng Spring. Việc ép kiểu SessionCallback<Integer> ở ví dụ giúp người học thấy rõ overload được chọn, dù lambda một tham số thường đã đủ để Java suy luận.

## 4. Đường thực thi và quản lý tài nguyên

### 4.1. SessionCallback

~~~mermaid
sequenceDiagram
    autonumber
    participant App as Application
    participant J as JmsTemplate
    participant CF as ConnectionFactory
    participant S as JMS Session
    App->>J: execute(SessionCallback)
    J->>CF: Lấy/tạo Connection và Session phù hợp
    J->>S: doInJms(session)
    S-->>J: Kết quả T hoặc JMSException
    J->>J: Dọn Session/Connection theo ownership
    J-->>App: T hoặc Spring JmsException
~~~

JmsTemplate đảm bảo luồng xử lý lỗi và tài nguyên trong phạm vi nó quản lý. Nếu callback ném **jakarta.jms.JMSException**, JmsTemplate chuyển thành **org.springframework.jms.JmsException** (unchecked) phù hợp trước khi đưa ra call site. Runtime exception của ứng dụng cũng không được biến thành thành công; tài nguyên vẫn được dọn trong nhánh finally.

### 4.2. ProducerCallback

~~~mermaid
sequenceDiagram
    autonumber
    participant App as Application
    participant J as JmsTemplate
    participant S as JMS Session
    participant P as MessageProducer
    App->>J: execute(name, ProducerCallback)
    J->>S: resolve Destination
    J->>S: createProducer(destination)
    S-->>J: producer
    J->>App: doInJms(session, producer)
    App->>P: send(message 1)
    App->>P: send(message 2)
    App-->>J: return count
    J->>P: close()
    J->>J: Dọn Session/Connection
    J-->>App: count
~~~

JmsTemplate giải phóng producer ngay cả khi callback ném exception. Vì thế không trả producer ra ngoài, không đưa producer vào thread pool, không đóng Session được framework cấp và không kỳ vọng producer tồn tại sau execute(...).

## 5. SessionCallback: thao tác tùy chỉnh ở mức Session

### 5.1. Gửi nhiều message tới hai queue

Một SessionCallback có thể tạo nhiều Destination và producer, sau đó gửi liên tiếp:

~~~java
Integer sent = jmsTemplate.execute(
        (SessionCallback<Integer>) session -> {
            Queue orders = session.createQueue("orders.requests");
            Queue audit = session.createQueue("audit.events");

            try (MessageProducer orderProducer =
                         session.createProducer(orders);
                 MessageProducer auditProducer =
                         session.createProducer(audit)) {

                TextMessage order =
                        session.createTextMessage("ORDER-42");
                order.setStringProperty("BusinessId", "order-42");
                orderProducer.send(order);

                TextMessage event =
                        session.createTextMessage("AUDIT-42");
                event.setStringProperty("BusinessId", "order-42");
                auditProducer.send(event);
            }
            return 2;
        });
~~~

**Snippet này cần jmsTemplate và import jakarta.jms.Queue, MessageProducer, TextMessage cùng SessionCallback của Spring**, nên không phải file chạy độc lập. Chương trình hoàn chỉnh được cung cấp ở mục 9.

Điều đang xảy ra:

1. Template cung cấp một Session; không cần tự gọi ConnectionFactory.createConnection().
2. Callback tạo đối tượng Queue và hai producer trong **cùng Session**.
3. Mỗi message được tạo bởi session.createTextMessage(...), gắn property để truy vết nghiệp vụ.
4. Hai producer tự tạo được đóng bằng try-with-resources.
5. Callback trả Integer=2, tức có hai lời gọi send hoàn tất bình thường trong callback.

**Quan trọng:** chỉ vì hai lần send dùng cùng Session không có nghĩa chúng tự động commit cùng nhau. Tính nguyên tử phụ thuộc Session có transacted không và transaction được commit/rollback ra sao. Với Session không transacted, có thể xảy ra lần gửi thứ nhất thành công rồi lần thứ hai lỗi. Mục 8 trình bày transaction.

### 5.2. Dùng SessionCallback để tạo message đặc biệt

SessionCallback cho phép truy cập các JMS API trực tiếp như createBytesMessage(), createMapMessage(), createObjectMessage(), createTemporaryQueue(), createConsumer(...), createBrowser(...).

Ví dụ thao tác MapMessage:

~~~java
jmsTemplate.execute((SessionCallback<Void>) session -> {
    Queue queue = session.createQueue("inventory.updates");

    try (MessageProducer producer = session.createProducer(queue)) {
        MapMessage message = session.createMapMessage();
        message.setString("sku", "SKU-42");
        message.setInt("quantity", 5);
        message.setStringProperty("SourceSystem", "warehouse");
        producer.send(message);
    }
    return null;
});
~~~

Đây là snippet: cần import jakarta.jms.MapMessage, Queue, MessageProducer. MapMessage là định dạng message của JMS; khác với Map của Java được MessageConverter chuyển đổi và cũng khác message properties. Bài này dùng nó để minh họa quyền truy cập Session ở callback, không đi sâu vào các loại JMS Message.

### 5.3. Khi nào SessionCallback hợp lý hơn method thường?

SessionCallback có ích khi một thao tác cần **nhiều JMS calls chia sẻ Session**, cần tạo destination/consumer/producer tùy chỉnh hoặc cần điều khiển một số API thấp hơn. Nếu chỉ gửi một String:

~~~java
jmsTemplate.convertAndSend("orders.requests", "ORDER-42");
~~~

phương thức tiện ích dễ đọc hơn và ít rủi ro quản lý tài nguyên. Không biến mọi lần gửi đơn giản thành callback cho “mạnh” hơn; mức quyền API lớn hơn cũng tăng trách nhiệm.

## 6. ProducerCallback: thao tác phức tạp với MessageProducer

### 6.1. Tái sử dụng một producer qua nhiều lần gửi

ProducerCallback cung cấp sẵn producer, vì vậy code không cần tạo/đóng nó:

~~~java
Integer sent = jmsTemplate.execute(
        "orders.outbound",
        (session, producer) -> {
            TextMessage first =
                    session.createTextMessage("ORDER-101");
            first.setStringProperty("BatchId", "B-7");

            TextMessage second =
                    session.createTextMessage("ORDER-102");
            second.setStringProperty("BatchId", "B-7");

            producer.send(first);
            producer.send(second);
            return 2;
        });
~~~

Đây là snippet bên trong Spring bean. Nếu broker nhận cả hai send và Session không transacted, ứng dụng nhận số 2. Nhưng giá trị 2 là **số thao tác send thực hiện trong callback**, không chứng minh nghiệp vụ downstream đã xử lý thành công hoặc message được lưu vĩnh viễn.

**Không gọi producer.close()** trong callback. Spring đóng producer trong finally khi execute() kết thúc.

### 6.2. Đặt QoS theo từng message

JMS MessageProducer có overload cho delivery mode, priority và time-to-live:

~~~java
producer.send(
        message,
        DeliveryMode.PERSISTENT, // Chế độ delivery có độ bền theo hợp đồng JMS.
        7,                       // Priority 0..9.
        60_000L);                // TTL 60 giây.
~~~

Đây là snippet; producer và message phải tồn tại. Khi cần mỗi message có QoS khác nhau:

~~~java
jmsTemplate.execute(
        "reports.jobs",
        (session, producer) -> {
            TextMessage urgent =
                    session.createTextMessage("URGENT-1");
            urgent.setStringProperty("JobClass", "urgent");
            producer.send(
                    urgent,
                    DeliveryMode.PERSISTENT,
                    8,
                    120_000L);

            TextMessage routine =
                    session.createTextMessage("NORMAL-2");
            routine.setStringProperty("JobClass", "routine");
            producer.send(
                    routine,
                    DeliveryMode.NON_PERSISTENT,
                    4,
                    30_000L);

            return null;
        });
~~~

Cần import jakarta.jms.DeliveryMode và TextMessage. Cả hai message cùng dùng một MessageProducer nhưng mỗi send có QoS khác nhau.

**Chú ý:** khi tự gọi producer.send(...) trong ProducerCallback, code đang điều khiển send trực tiếp. Các đường đi nội bộ JmsTemplate.send(...) có logic riêng cho explicit QoS, delivery delay và commit cục bộ. Đừng giả định cấu hình template sẽ tự gắn lại mọi QoS hoặc gọi commit thay cho lệnh send tùy chỉnh của callback. Nếu cần một policy QoS chung, cân nhắc dùng JmsTemplate.send/convertAndSend với cấu hình tương ứng, hoặc chỉ định QoS ngay trong lời gọi producer.send như trên.

### 6.3. Producer gắn destination và anonymous producer

Nếu gọi:

~~~java
jmsTemplate.execute("orders.queue", (session, producer) -> {
    producer.send(session.createTextMessage("A"));
    return null;
});
~~~

Spring đã resolve "orders.queue" rồi tạo producer gắn với Destination đó. Ngược lại, nếu dùng producer không gắn đích, JMS cho phép gửi bằng overload có tham số Destination:

~~~java
jmsTemplate.execute((ProducerCallback<Void>) (session, producer) -> {
    Queue first = session.createQueue("queue.first");
    Queue second = session.createQueue("queue.second");

    producer.send(first, session.createTextMessage("A"));
    producer.send(second, session.createTextMessage("B"));
    return null;
});
~~~

Snippet thứ hai dựa trên tình huống JmsTemplate.execute(ProducerCallback) không có default destination hoặc đã tạo anonymous producer. Nếu template có default destination, producer sẽ gắn đích ấy và không thể tùy tiện dùng overload gửi tới destination khác trong mọi provider. Với mục tiêu một producer gửi nhiều destination, **cấu hình rõ ràng producer không gắn destination** hoặc dùng SessionCallback tự tạo session.createProducer(null); đừng trông chờ trạng thái default destination không được kiểm soát.

## 7. Nhận message trong SessionCallback: startConnection và timeout

### 7.1. Tại sao execute(action) mặc định không đủ?

Classic JMS Connection mới tạo **chưa start incoming delivery**. Producer gửi message có thể hoạt động mà không cần start, nhưng consumer.receive(...) cần Connection đã start để được giao message.

JmsTemplate có overload:

~~~java
<T> T execute(SessionCallback<T> action, boolean startConnection);
~~~

Khi callback tự tạo MessageConsumer, dùng startConnection=true để JmsTemplate bật receiving theo vòng đời tài nguyên mà nó quản lý.

~~~java
String received = jmsTemplate.execute(
        (SessionCallback<String>) session -> {
            Queue queue = session.createQueue("reports.replies");

            try (MessageConsumer consumer =
                         session.createConsumer(
                                 queue,
                                 "Region = 'VN'")) {

                Message message = consumer.receive(3_000L);
                if (message == null) {
                    return null;
                }
                if (message instanceof TextMessage text) {
                    return text.getText();
                }
                throw new JMSException("Expected TextMessage");
            }
        },
        true);
~~~

Đây là snippet nhận có selector; import jakarta.jms.MessageConsumer, Queue, Message, TextMessage, JMSException. Timeout là 3 giây. Không có message matching thì result là null; không được coi null là lỗi JMS mặc định.

**Vì sao phải trả String thay vì MessageConsumer?** Consumer do callback tự tạo đã được đóng trước khi callback trả về. Trả handle đó để dùng sau sẽ dẫn đến lỗi. Tương tự, không trả Session cho caller rồi tiếp tục dùng sau execute(...).

### 7.2. Đường ưu tiên cho nhận đơn giản

Nếu chỉ cần một message hoặc một selector thông thường, JmsTemplate đã có:

~~~java
Object payload =
        jmsTemplate.receiveAndConvert("reports.replies");

Message message =
        jmsTemplate.receiveSelected(
                "reports.replies",
                "Region = 'VN'");
~~~

Các method này tự quản lý startConnection và consumer phù hợp. Thiết lập receiveTimeout có giới hạn là quan trọng để không chặn thread vô hạn; một số cấu hình JMS dùng timeout 0 mang nghĩa chờ không giới hạn.

### 7.3. Không đưa Session sang thread khác

Session của JMS tuân theo mô hình sử dụng tuần tự; JmsTemplate chỉ cấp Session hợp lệ **trong khoảng callback**. Không làm như sau:

~~~java
// Sai về lifecycle và khả năng thread-safety:
jmsTemplate.execute((SessionCallback<Void>) session -> {
    executor.submit(() -> {
        // Dùng session sau khi callback đã return là sai.
    });
    return null;
});
~~~

Đây là anti-pattern, không phải code cần chạy. Nếu cần xử lý bất đồng bộ, có thể gửi một job sang hàng đợi và để @JmsListener/container riêng xử lý. Mỗi tác vụ tự quản lý ngữ cảnh tài nguyên phù hợp, không mượn Session đã hết hạn.

## 8. Transaction, acknowledgement, lỗi và giới hạn atomicity

### 8.1. Một callback không tự tạo transaction

So sánh:

| Trường hợp | Hệ quả |
| --- | --- |
| Session không transacted (mặc định trong JmsTemplate cấu hình cơ bản) | Hai lần send có thể thành công/thất bại riêng; callback không tự gom thành một commit nguyên tử. |
| Session transacted do ứng dụng tự quản lý | Cần commit/rollback rõ ràng nếu không có transaction manager điều phối. |
| Session gắn với JmsTransactionManager | Spring quản lý commit/rollback khi boundary của transaction kết thúc; callback dùng cùng Session được bind với thread. |
| Tham gia JTA/XA đúng cấu hình | Có thể bao gồm tài nguyên JMS trong transaction phân tán; yêu cầu provider và transaction manager hỗ trợ XA. |
| Có DB transaction riêng cùng thời điểm | Không mặc định nguyên tử với JMS; cần kiến trúc nhất quán phù hợp (outbox, idempotency hoặc XA/JTA nếu thật sự cần). |

Điều quan trọng với SessionCallback và ProducerCallback là **trách nhiệm commit**. Trong JmsTemplate, các convenience method send/receive có logic commit/ack riêng cho session transacted cục bộ; **callback execute tùy chỉnh không thể mặc định thay thế những bước đó**. Nếu bật sessionTransacted nhưng không dùng Spring transaction manager, phải hiểu rõ ai commit/rollback, nếu không việc đóng Session với transaction chưa commit có thể khiến các message chưa được ghi nhận.

Không tự gọi session.commit() hoặc session.rollback() trên một Session đang tham gia Spring-managed transaction. Điều đó phá ranh giới commit/rollback do transaction manager sở hữu.

### 8.2. Ví dụ dùng transaction manager cho nhiều send

Khi cả hai message cùng nằm trên **một JMS ConnectionFactory**, có thể cấu hình JmsTransactionManager và dùng TransactionTemplate để bảo vệ một nhóm thao tác JMS:

~~~java
import jakarta.jms.ConnectionFactory;
import org.springframework.jms.connection.JmsTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;

// Snippet bên trong ứng dụng đã có connectionFactory và jmsTemplate.
JmsTransactionManager txManager =
        new JmsTransactionManager(connectionFactory);
TransactionTemplate tx = new TransactionTemplate(txManager);

tx.executeWithoutResult(status -> {
    jmsTemplate.execute(
            (SessionCallback<Void>) session -> {
                Queue a = session.createQueue("orders.outbound");
                Queue b = session.createQueue("audit.outbound");

                try (MessageProducer pa = session.createProducer(a);
                     MessageProducer pb = session.createProducer(b)) {
                    pa.send(session.createTextMessage("ORDER-42"));
                    pb.send(session.createTextMessage("AUDIT-42"));
                }
                return null;
            });
});
~~~

Đây là **snippet**, không phải project độc lập. Để đúng về transaction, JmsTemplate phải dùng **cùng ConnectionFactory instance** mà transaction manager bind, và môi trường phải cho phép Session transacted. Với transaction thành công, manager commit sau callback; khi lỗi phù hợp thoát khỏi transaction, manager rollback. Nếu một transaction quản lý chỉ JMS, nó không đồng thời commit/rollback JDBC database trên một tài nguyên DB khác.

**Không tạo JmsTransactionManager mới trong mỗi request** như minh họa local variable ở trên. Khi triển khai thật, khai báo một bean transaction manager được quản lý trong cấu hình và inject vào nơi cần dùng.

### 8.3. Runtime exception và JMSException

Callback có thể ném checked jakarta.jms.JMSException. JmsTemplate chuyển checked exception này thành nhánh Spring JmsException unchecked. Điều này cho phép code caller xử lý ở boundary dịch vụ mà không buộc mọi method khai báo throws JMSException.

~~~java
try {
    Integer count =
            jmsTemplate.execute(
                    (SessionCallback<Integer>) session -> {
                        // Các lời gọi JMS API có thể ném JMSException.
                        return 1;
                    });
} catch (org.springframework.jms.JmsException ex) {
    // Ghi nhận lỗi vận chuyển/JMS provider; phân loại retry.
}
~~~

Đây là snippet. Spring JmsException không đồng nghĩa mọi lỗi trong callback là lỗi kết nối: callback cũng có thể tự ném RuntimeException nghiệp vụ. Không catch chung rồi trả về "success" nếu message chưa được gửi đúng cách.

### 8.4. Atomicity, redelivery và idempotency

Giả sử callback gửi message "charge card" và "send receipt":

- Không có JMS transaction: send thứ nhất có thể hoàn tất, send thứ hai lỗi.
- Có một JMS transaction cục bộ: hai send tới tài nguyên JMS tương thích có thể commit cùng nhau trong cùng transaction; nhưng side effect trên database hoặc dịch vụ thanh toán vẫn nằm ngoài phạm vi đó.
- Có lỗi sau commit nhưng trước khi phía gửi quan sát được thành công: retry có thể tạo message trùng.
- Consumer nhận lại message khi ack/commit gặp sự cố: vẫn cần idempotency key để tránh lặp nghiệp vụ.

Không coi callback là phép bảo đảm **exactly-once end-to-end**. Với ứng dụng phức tạp, thiết kế transactional outbox, inbox/deduplication hoặc JTA/XA khi phù hợp.

## 9. Dự án chạy được: Java 17 + Spring Boot 3.3 + Artemis

Ứng dụng dưới đây chạy hai kiểu callback, rồi lấy chính các message đã gửi ra để chứng minh chúng đến đúng queue. Ví dụ cố tình dùng **JMS Session không transacted** để đường chạy đơn giản, sau đó sẽ giải thích cách thêm transaction. Mỗi lần chạy trên broker/queue sạch cho stdout xác định.

### 9.1. Chuẩn bị môi trường

Yêu cầu JDK 17+, Maven, Docker và cổng TCP 61616 không bị ứng dụng khác chiếm. Chạy Apache ActiveMQ Artemis thử nghiệm:

~~~bash
docker run --detach --rm --name jms-callback-broker \
  -p 61616:61616 -p 8161:8161 \
  apache/artemis:latest-alpine
~~~

Chờ broker sẵn sàng rồi mới chạy ứng dụng. Mật khẩu và user mặc định artemis/artemis chỉ để học; hệ thống thực cần tài khoản riêng và cấu hình bảo mật. Nếu broker tắt auto-create queue, hãy khai báo bốn queue demo.callback.orders, demo.callback.audit, demo.callback.batch và cấp quyền trước.

Cấu trúc project:

~~~text
jms-callback-demo/
├── pom.xml
└── src/main/
    ├── java/example/jmscallback/CallbackDemoApplication.java
    └── resources/application.properties
~~~

### 9.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>
    <groupId>example</groupId>
    <artifactId>jms-callback-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-artemis</artifactId>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Spring Boot 3.x/Spring Framework 6.x dùng **jakarta.jms.***. Tránh trộn javax.jms.* của thế hệ cũ vào dự án này.

### 9.3. application.properties

~~~properties
spring.main.web-application-type=none
spring.artemis.mode=native
spring.artemis.broker-url=tcp://localhost:61616
spring.artemis.user=artemis
spring.artemis.password=artemis

spring.jms.template.receive-timeout=5s
~~~

receive-timeout giới hạn thời gian cho các lời gọi JmsTemplate.receiveAndConvert, tránh treo chương trình nếu message không đến. Mẫu dùng queue, không cấu hình pubSubDomain=true.

### 9.4. CallbackDemoApplication.java

~~~java
package example.jmscallback;

import jakarta.jms.DeliveryMode;
import jakarta.jms.MessageProducer;
import jakarta.jms.Queue;
import jakarta.jms.TextMessage;
import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.jms.core.SessionCallback;

@SpringBootApplication
public class CallbackDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(CallbackDemoApplication.class, args);
    }

    @Bean
    CommandLineRunner run(JmsTemplate jmsTemplate) {
        return args -> {
            Integer sessionCount = jmsTemplate.execute(
                    (SessionCallback<Integer>) session -> {
                        Queue orders = session.createQueue(
                                "demo.callback.orders");
                        Queue audit = session.createQueue(
                                "demo.callback.audit");

                        // Producer do callback tự tạo: callback phải đóng.
                        try (MessageProducer orderProducer =
                                     session.createProducer(orders);
                             MessageProducer auditProducer =
                                     session.createProducer(audit)) {

                            TextMessage order =
                                    session.createTextMessage("ORDER-42");
                            order.setStringProperty(
                                    "BusinessId", "order-42");
                            orderProducer.send(order);

                            TextMessage event =
                                    session.createTextMessage("AUDIT-42");
                            event.setStringProperty(
                                    "BusinessId", "order-42");
                            auditProducer.send(event);
                        }
                        return 2;
                    });
            System.out.println("SessionCallback sent: " + sessionCount);

            // Producer do JmsTemplate tạo, Spring sẽ đóng.
            Integer producerCount = jmsTemplate.execute(
                    "demo.callback.batch",
                    (session, producer) -> {
                        TextMessage first =
                                session.createTextMessage("BATCH-1");
                        first.setStringProperty("BatchId", "batch-7");
                        producer.send(
                                first, DeliveryMode.PERSISTENT,
                                5, 60_000L);

                        TextMessage second =
                                session.createTextMessage("BATCH-2");
                        second.setStringProperty("BatchId", "batch-7");
                        producer.send(
                                second, DeliveryMode.PERSISTENT,
                                5, 60_000L);
                        return 2;
                    });
            System.out.println("ProducerCallback sent: " + producerCount);

            Object order =
                    jmsTemplate.receiveAndConvert("demo.callback.orders");
            Object audit =
                    jmsTemplate.receiveAndConvert("demo.callback.audit");
            Object firstBatch =
                    jmsTemplate.receiveAndConvert("demo.callback.batch");
            Object secondBatch =
                    jmsTemplate.receiveAndConvert("demo.callback.batch");

            System.out.println("order: " + order);
            System.out.println("audit: " + audit);
            System.out.println("batch first: " + firstBatch);
            System.out.println("batch second: " + secondBatch);
        };
    }
}
~~~

**Tại sao đoạn này là ví dụ đầy đủ?** File Java có main(), application.properties cấu hình Artemis, pom.xml chứa Spring Boot starter. Không cần biến giả định như session hoặc producer ở ngoài callback. Để chạy, các queue phải được broker cho phép; chúng được phân giải qua JMS Session/Provider. Spring Boot tự cung cấp JmsTemplate/ConnectionFactory khi starter và broker được cấu hình phù hợp.

**Dòng nào là SessionCallback?** Callback thứ nhất nhận một Session, tạo Queue, hai producer, hai TextMessage rồi gửi vào hai queue. Mỗi producer tự tạo được đóng tự động trong try-with-resources.

**Dòng nào là ProducerCallback?** Callback thứ hai nhận Session và producer đã gắn với "demo.callback.batch"; code tái sử dụng producer để gửi hai TextMessage và đặt QoS cho mỗi send. Không đóng producer vì JmsTemplate sở hữu nó.

**Dữ liệu trả về:** mỗi callback trả Integer=2. Điều đó mô tả số send trong callback, không phải JMS queue depth lâu dài hay số job xử lý thành công.

### 9.5. Chạy

Đứng trong thư mục có pom.xml:

~~~bash
mvn spring-boot:run
~~~

Khi broker hoạt động, queue sạch, không có consumer cạnh tranh, và cả bốn message đều được nhận trong timeout, output do những lệnh System.out.println trong ứng dụng tạo ra là:

~~~text
SessionCallback sent: 2
ProducerCallback sent: 2
order: ORDER-42
audit: AUDIT-42
batch first: BATCH-1
batch second: BATCH-2
~~~

Spring Boot/Artemis có thể in thêm log. Trên queue có backlog từ lần chạy trước, kết quả nhận có thể khác, vì vậy dùng broker/queue dành riêng cho demo. Nếu broker không sẵn sàng, quyền bị từ chối hoặc receive timeout, code có thể ném lỗi hoặc in null thay vì output thành công.

Dừng broker demo khi xong:

~~~bash
docker stop jms-callback-broker
~~~

### 9.6. Quan sát điều gì trong demo?

1. **JmsTemplate quản lý Session**: code không mở/đóng Connection thủ công.
2. **SessionCallback có thể thao tác qua nhiều destination** trong cùng Session.
3. **ProducerCallback tái sử dụng MessageProducer** và không cần tự quản lý lifecycle của producer.
4. **QoS trực tiếp** đi vào overload producer.send(message, deliveryMode, priority, ttl).
5. **JmsTemplate.receiveAndConvert** là đường phù hợp để nhận message đơn giản; callback nhận không cần thiết ở đây.
6. **Message đã gửi là riêng biệt**: hai message trên batch queue có cùng BatchId nhưng body khác nhau.
7. **Không có transaction chung** bao gồm bốn message. Muốn nhóm send thành đơn vị atomic, xem mục transaction, không dựa vào việc code cùng ở một CommandLineRunner.

## 10. Những trường hợp tùy chỉnh nâng cao

### 10.1. Đọc metadata hoặc chọn Message đặc biệt

Nếu cần trích một header/metadata từ Message nhận trực tiếp, SessionCallback cho phép tự tạo consumer, receive và trả DTO đơn giản:

~~~java
record ReceivedInfo(String messageId, String payload) {}

ReceivedInfo info = jmsTemplate.execute(
        (SessionCallback<ReceivedInfo>) session -> {
            Queue q = session.createQueue("orders.replies");
            try (MessageConsumer consumer =
                         session.createConsumer(q)) {
                Message msg = consumer.receive(2_000);
                if (msg == null) return null;

                return new ReceivedInfo(
                        msg.getJMSMessageID(),
                        msg.getBody(String.class));
            }
        },
        true);
~~~

Đây là snippet Java 17 trong một lớp có import phù hợp, không có main() độc lập. Nó trả record **không phụ thuộc Session**, khác việc trả MessageConsumer. Với lệnh nhận thông thường, hãy cân nhắc receiveSelected(...)/receiveAndConvert(...) để hưởng policy timeout/ack/commit của JmsTemplate.

### 10.2. Gửi thông điệp tùy biến theo content

ProducerCallback cho phép tạo đúng loại JMS Message cần dùng:

~~~java
jmsTemplate.execute(
        "inventory.queue",
        (session, producer) -> {
            MapMessage update = session.createMapMessage();
            update.setString("sku", "SKU-17");
            update.setInt("delta", 5);
            update.setJMSType("inventory.adjusted.v1");
            update.setStringProperty("Region", "VN");
            producer.send(update);
            return null;
        });
~~~

Snippet này cần import MapMessage. Nhớ phân biệt **MapMessage fields** nằm trong body với **message properties** như Region nằm ở metadata và có thể được JMS selector dùng.

### 10.3. Tạo temporary queue trong SessionCallback

~~~java
jmsTemplate.execute(
        (SessionCallback<Void>) session -> {
            TemporaryQueue replyQueue =
                    session.createTemporaryQueue();
            try {
                // Dùng replyQueue trong cùng một request-reply workflow.
                // Không trả queue handle ra ngoài để giữ mãi.
            } finally {
                replyQueue.delete();
            }
            return null;
        });
~~~

Đây là snippet minh họa lifecycle, không chứa đầy đủ luồng request-reply. Temporary destination tồn tại phụ thuộc Connection; nếu chỉ cần request-reply thông thường, JmsTemplate.sendAndReceive(...) đã cung cấp API chuyên biệt và quản lý temporary reply destination giúp ứng dụng.

## 11. So sánh với MessageCreator và MessagePostProcessor

| API | Callback nhận gì? | Ai gọi send()? | Phù hợp |
| --- | --- | --- | --- |
| convertAndSend(destination, Object) | Caller cung cấp object; JmsTemplate dùng converter | JmsTemplate | Một message đơn giản. |
| MessageCreator | Session để tạo Message | JmsTemplate | Một message cần type/body/header tùy chỉnh. |
| MessagePostProcessor | Message sau khi converter tạo xong | JmsTemplate | Thêm property/header, chỉnh metadata trước send. |
| SessionCallback<T> | Session | Callback nếu muốn gửi | Nhiều API calls trên cùng Session; tạo producer/consumer/browser. |
| ProducerCallback<T> | Session và MessageProducer | Callback | Nhiều send và QoS tùy chỉnh qua một producer. |
| @JmsListener | Message hoặc payload khi broker giao | Không phải API chủ yếu để gửi | Nhận bất đồng bộ, xử lý ở listener container. |

Hai trường hợp không cần callback mức thấp:

~~~java
// Chỉ gửi một String:
jmsTemplate.convertAndSend("orders.requests", "ORDER-42");

// Một message cần gắn header và property:
jmsTemplate.convertAndSend(
        "orders.requests", "ORDER-42",
        message -> {
            message.setJMSType("order.created.v1");
            message.setStringProperty("Source", "api");
            return message;
        });
~~~

Khi JmsTemplate.convertAndSend có thể xử lý yêu cầu, dùng method này để code dễ đọc và áp dụng nhất quán converter, transaction/ack/QoS do template quản lý. Chỉ chuyển lên execute(...) khi cần API mà các convenience methods không diễn tả thuận tiện.

## 12. Checklist an toàn khi triển khai

### 12.1. Ownership và cleanup

- Session và Connection do JmsTemplate cấp **không được đóng thủ công** trong callback.
- Producer truyền vào ProducerCallback **không được đóng thủ công**; JmsTemplate chịu trách nhiệm.
- Producer, consumer, QueueBrowser tự tạo trong SessionCallback cần được đóng rõ ràng, kể cả khi có exception.
- Không giữ Session hoặc producer sau khi execute() return; đừng dùng chúng qua async callback/thread khác.
- Không dùng chung Session đồng thời giữa nhiều thread, kể cả khi ConnectionFactory có connection pool.

### 12.2. Transaction và lỗi

- Phân biệt Session không transacted với Spring-managed JMS transaction.
- Đặt transaction boundary tại service/TransactionTemplate, dùng đúng ConnectionFactory instance cho manager và JmsTemplate.
- Khi chưa có transaction, nhiều send trong một callback **không nguyên tử**.
- Nếu callback tự thao tác trên một Session transacted cục bộ, phải có chiến lược commit/rollback chính xác; tránh đóng Session khi transaction còn mở.
- Không tự session.commit()/rollback() khi Session thuộc transaction manager của Spring.
- Không giả định commit JMS gộp cả JDBC, HTTP call hay hệ thống thứ ba.
- Kiểm tra idempotency, retry và DLQ nếu có khả năng gửi/giao lại message.

### 12.3. QoS, timeout và throughput

- QoS của producer.send tùy chỉnh được chỉ định rõ theo từng lần gửi nếu cần: delivery mode, priority, time-to-live.
- Priority không phải cam kết thứ tự cứng trong mọi broker/cấu hình; TTL có thể làm message hết hạn trước khi consumer nhận.
- Callback không nên chạy các tác vụ CPU/network lâu không liên quan JMS khi vẫn giữ tài nguyên Session/Connection.
- Khi nhận thủ công, đặt timeout hữu hạn và bật Connection với execute(action, true).
- Với xử lý liên tục, dùng @JmsListener và listener container thay vì vòng lặp receive vô hạn trong một SessionCallback chạy đồng bộ.
- Đo thời gian send/receive, lỗi và số message; tránh in hoặc log payload nhạy cảm.

## 13. Sự cố thường gặp

| Triệu chứng | Nguyên nhân khả dĩ | Hướng xử lý |
| --- | --- | --- |
| Callback chỉ gửi được message đầu | Message thứ hai lỗi, Session không transacted | Ghi nhận partial sends; dùng JMS transaction nếu cần nguyên tử. |
| ProducerCallback ném IllegalStateException sau execute | Giữ MessageProducer rồi dùng sau khi Spring đóng | Chỉ dùng producer trong callback. |
| SessionCallback.receive(timeout) luôn trả null | Gọi execute(action) thay vì execute(action, true), Connection chưa start | Dùng execute(action, true) hoặc JmsTemplate.receive. |
| Receive chặn vô thời hạn | Dùng receive() hoặc receive(0) không có thời hạn | Đặt timeout dương hữu hạn. |
| Bật sessionTransacted rồi không thấy message | Không có transaction commit cho send tùy chỉnh | Dùng JmsTransactionManager/TransactionTemplate hoặc quản lý commit cục bộ rõ ràng. |
| @Transactional không làm rollback DB và JMS chung | Đang dùng một transaction manager cục bộ riêng | Thiết kế outbox/idempotency hoặc XA/JTA nếu thật sự cần atomicity đa tài nguyên. |
| TTL/priority khác kỳ vọng | Custom send đi qua direct producer.send nhưng code không chỉ định QoS | Dùng overload send có QoS, kiểm tra provider config. |
| Lỗi JMSException không được bắt | JmsTemplate chuyển thành Spring JmsException runtime | Xử lý ở service boundary, chính sách retry/idempotency. |
| Callback làm nghẽn thread | Chạy logic lâu trong callback, giữ Session/Connection | Tách công việc dài và chỉ giữ JMS callback ngắn. |
| Exception khi đóng resource | Không cleanup producer/consumer tự tạo | Dùng try-with-resources/finally, bảo toàn exception gốc. |
| Gửi đúng tên mà không consumer nhận | Queue/topic domain, selector, broker ACL hoặc listener sai | Kiểm tra DestinationResolver, broker và listener config. |
| Cast Session/Message sai | Nhầm jakarta.jms.* với javax.jms.* | Dùng Jakarta JMS nhất quán trong Spring Boot 3.x. |

## 14. Tự kiểm tra kiến thức

**1. SessionCallback nhận những tham số nào?** Một jakarta.jms.Session; tự tạo những resource con cần dùng và phải quản lý resource tự tạo.

**2. ProducerCallback nhận những tham số nào?** Session và MessageProducer do JmsTemplate cấp; callback gửi message qua producer đó.

**3. Ai đóng producer trong ProducerCallback?** JmsTemplate. Callback không được giữ hoặc đóng producer dùng chung.

**4. Nếu tự tạo MessageProducer trong SessionCallback thì sao?** Code ứng dụng phải đóng trong try-with-resources/finally.

**5. execute(SessionCallback) mặc định có start Connection để receive không?** Không. Nếu cần tự receive bằng consumer, gọi execute(action, true) hoặc dùng receive methods của JmsTemplate.

**6. Callback trả về gì?** Giá trị T tùy ứng dụng, có thể null. Nên trả kết quả Java độc lập với tài nguyên JMS đã được dọn.

**7. Hai producer.send trong cùng callback có tự trở thành một transaction không?** Không. Cần Session transacted và commit/rollback đúng ranh giới.

**8. Có nên gọi session.commit() khi JmsTransactionManager đang quản lý Session không?** Không; Spring transaction manager chịu trách nhiệm.

**9. Khi nào dùng MessagePostProcessor thay ProducerCallback?** Khi chỉ cần chỉnh một Message sau converter rồi gửi qua JmsTemplate, không cần thao tác nhiều lần với producer.

**10. Có nên dùng callback để chạy vòng lặp consumer lâu dài?** Thường không; @JmsListener/container được thiết kế cho xử lý bất đồng bộ và quản lý lifecycle tốt hơn.

### Bài tập mở rộng

1. Chạy dự án mục 9, thêm message thứ ba vào ProducerCallback và giải thích số đếm returned có ý nghĩa gì.
2. Thử sửa QoS giữa các lần gửi; quan sát JMSPriority/JMSExpiration trên message đã nhận bằng API/console thích hợp.
3. Thêm một MessageProducer khác trong SessionCallback để gửi tới queue mới; kiểm tra cleanup khi cố ý ném exception.
4. Thử một lỗi gửi thứ hai khi Session không transacted; đối chiếu queue depth với số send đã hoàn tất.
5. Dùng JmsTransactionManager và TransactionTemplate cho hai send ở cùng một Session; cố ý ném RuntimeException trước khi transaction kết thúc và kiểm chứng rollback.
6. Tạo consumer có selector trong SessionCallback, so sánh execute(action, false) với execute(action, true); bảo đảm timeout hữu hạn.
7. Refactor một ProducerCallback chỉ gửi một String thành convertAndSend và so sánh code, lỗi và khả năng mở rộng.
8. Viết integration test với Artemis thực để xác minh producer resource được giải phóng sau callback exception.

## 15. Tài liệu chính thức

- Spring Framework 6.2 — Using Spring JMS: https://docs.spring.io/spring-framework/reference/6.2/integration/jms/using.html
- Spring Framework 6.2 — Sending a Message, SessionCallback và ProducerCallback: https://docs.spring.io/spring-framework/reference/6.2/integration/jms/sending.html
- Spring Framework 6.2 — JmsTemplate API: https://docs.spring.io/spring-framework/docs/6.2.x-SNAPSHOT/javadoc-api/org/springframework/jms/core/JmsTemplate.html
- Spring Framework 6.1 — SessionCallback API: https://docs.spring.io/spring-framework/docs/6.1.10/javadoc-api/org/springframework/jms/core/SessionCallback.html
- Spring Framework 6.1 — ProducerCallback API: https://docs.spring.io/spring-framework/docs/6.1.10/javadoc-api/org/springframework/jms/core/ProducerCallback.html
- Jakarta Messaging 3.1 Specification: https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html
- Apache ActiveMQ Artemis Docker: https://artemis.apache.org/components/artemis/documentation/latest/docker.html
