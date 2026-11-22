# ConnectionFactory, Connection, Session và trách nhiệm của từng đối tượng

## 1. Ba đối tượng, ba phạm vi trách nhiệm

Trong **Lập trình JMS** với **Apache ActiveMQ Classic** hoặc **ActiveMQ Artemis**, ba đối tượng **ConnectionFactory**, **Connection** và **Session** xác định cách client sở hữu tài nguyên, nhận thông điệp, xác nhận xử lý và phục hồi khi có lỗi. Phần lớn lỗi triển khai không xuất phát từ cú pháp **send()** hay **receive()**, mà từ việc đặt thao tác vào sai phạm vi: gọi **start()** sai lúc, chia sẻ một Session giữa nhiều thread, hoặc tưởng **Connection.close()** có thể thay cho **Session.commit()**.

~~~mermaid
flowchart TD
    CF["ConnectionFactory<br/>Địa chỉ broker, tham số client, cách tạo kết nối"] -->|"createConnection()"| C["Connection<br/>Kết nối logic, xác thực, start/stop/close"]
    C -->|"createSession()"| S1["Session A<br/>Producer + transaction A"]
    C -->|"createSession()"| S2["Session B<br/>Consumer + transaction B"]
    S1 --> P["MessageProducer"]
    S2 --> R["MessageConsumer"]
    P --> Q[("Broker / destination")]
    Q --> R
~~~

| Đối tượng | Câu hỏi nó trả lời | Nó trực tiếp sở hữu/điều khiển | Điều nó **không** cam kết |
| --- | --- | --- | --- |
| **ConnectionFactory** | “Kết nối tới broker bằng cách nào?” | Cấu hình client và thao tác tạo **Connection** | Không phải kết nối đang chạy; không nhận/ACK message |
| **Connection** | “Client đã có kênh tới broker chưa, khi nào bắt đầu nhận?” | Kết nối logic với provider, các Session, **start/stop/close**, listener lỗi bất đồng bộ | Không tự commit transaction của mọi Session |
| **Session** | “Các thao tác JMS của luồng này được nhóm, xác nhận và rollback ra sao?” | Tạo producer/consumer/message/destination; thứ tự xử lý trong session; **ACK/commit/rollback/recover** tùy mode | Không là transaction của database bên ngoài; không an toàn để nhiều thread dùng đồng thời |
| **MessageProducer** | “Gửi message đến destination nào, với delivery options nào?” | **send()**, delivery mode, priority, TTL | Không tự đảm bảo consumer đã hoàn thành nghiệp vụ |
| **MessageConsumer** | “Nhận message nào và theo selector nào?” | **receive()**, **MessageListener**, **close()** | Không quyết định mode transaction/ack riêng ngoài Session |

Trong cấu trúc trên, **một Connection có thể tạo nhiều Session** và **một Session có thể tạo nhiều producer/consumer**. Điểm then chốt: **Session là phạm vi tuần tự hóa và transaction/ack**, còn **Connection là phạm vi kết nối và điều khiển bắt đầu nhận**.

Phạm vi bài tập trung ở **JMS client API**. Artemis còn cung cấp Core API, AMQP và các giao thức khác, nhưng chúng không biến quy tắc **Session của JMS** thành transaction database hay thay đổi ý nghĩa của **ConnectionFactory**.

## 2. ConnectionFactory: mô tả cách tạo kết nối, chưa phải một kết nối

**ConnectionFactory** là điểm bắt đầu của JMS. Nó có thể chứa thông tin về:

- URL broker, ví dụ **tcp://127.0.0.1:61616** trên môi trường thử nghiệm.
- Tham số provider-specific như timeout, TLS, failover/reconnect, cân bằng kết nối.
- Cách xác thực và tùy chọn của client.
- Cơ chế lấy cấu hình từ DI/JNDI hoặc container quản lý, nếu ứng dụng sử dụng application server/framework.

Tạo factory **không đồng nghĩa đã mở phiên JMS**. Tùy implementation, factory có thể chỉ là object cấu hình; việc cấp tài nguyên kết nối và xác thực thường diễn ra khi gọi **createConnection()** hoặc **createContext()**. Không nên dùng việc khởi tạo factory thành công làm health check của broker.

### Ví dụ khởi tạo theo provider

**ActiveMQ Classic**, với client API **javax.jms** tương thích với broker/classpath:

~~~java
import javax.jms.Connection;
import javax.jms.ConnectionFactory;
import org.apache.activemq.ActiveMQConnectionFactory;

ConnectionFactory factory =
        new ActiveMQConnectionFactory("tcp://127.0.0.1:61616");

// Từ đây mới yêu cầu provider tạo Connection và xác thực.
Connection connection = factory.createConnection(user, password);
~~~

**ActiveMQ Artemis**, với **Jakarta Messaging**:

~~~java
import jakarta.jms.Connection;
import jakarta.jms.ConnectionFactory;
import org.apache.activemq.artemis.jms.client.ActiveMQConnectionFactory;

ConnectionFactory factory =
        new ActiveMQConnectionFactory("tcp://127.0.0.1:61617");

Connection connection = factory.createConnection(user, password);
~~~

Hai ví dụ này nằm trong **hai dự án/classpath riêng**; import **javax.jms.Connection** và **jakarta.jms.Connection** không thể hoán đổi chỉ bằng cách đổi package. Factory concrete khác nhau, nhưng cách tổ chức **factory → connection → session** giống về mặt ý nghĩa.

Một project production có thể lấy **ConnectionFactory** từ Spring/container thay vì trực tiếp **new ActiveMQConnectionFactory(...)**. Khi đó, hãy ưu tiên nơi quản lý cấu hình và vòng đời mà framework cung cấp; không tạo factory/connections tự phát ở mỗi request.

### Có tạo một factory cho mỗi message không?

Không nên. Factory thường được tạo theo cấu hình ứng dụng và có thể được dùng lại **theo hợp đồng/thread-safety của provider hoặc framework**. Với các object cấu hình mutable, tránh vừa chia sẻ vừa thay URL/credentials/options khi nhiều thread đang tạo connection. Factory là nơi cấu hình phương thức kết nối; **Session** mới là đối tượng gắn trực tiếp với một luồng xử lý JMS cụ thể.

### Những kiểm tra đúng sau khi tạo factory

| Quan sát | Chứng minh điều gì? | Chưa chứng minh điều gì? |
| --- | --- | --- |
| Tạo object factory thành công | Code tìm thấy class provider và tạo được object | Broker đang online |
| **createConnection()** thành công | Provider chấp nhận tạo kết nối tại thời điểm đó | Consumer đã nhận message; transaction đã commit |
| **createSession()** thành công | Client tạo được phạm vi thao tác JMS | Queue/topic có message hoặc consumer đã được cấp quyền mọi destination |
| Gửi/nhận + commit thành công | Đường đi JMS đã được kiểm chứng ở mức tương ứng | Side effect ở database ngoài JMS chính xác tuyệt đối |

Cấp quyền **connect** cũng khác với quyền **send/consume** trên destination. Một user có thể xác thực được nhưng không được phép gửi hoặc nhận queue cụ thể; lỗi này xuất hiện ở bước sử dụng Session/destination, không nhất thiết ở lúc tạo Connection.

## 3. Connection: phạm vi kết nối, start/stop và đóng tài nguyên

**Connection** biểu diễn một kết nối logic của client tới JMS provider. Nó là cha của các Session được tạo từ nó và cung cấp các thao tác có phạm vi rộng:

- **createSession(...)**: tạo phạm vi gửi/nhận.
- **start()**: cho phép **delivery đến các consumer** do những Session của Connection quản lý.
- **stop()**: tạm ngừng delivery đến consumer trên Connection theo hợp đồng JMS.
- **setExceptionListener(...)**: đăng ký callback nhận thông báo về một số lỗi bất đồng bộ của Connection.
- **close()**: đóng Connection và các tài nguyên JMS con liên quan.

Đặc tính dễ nhầm: **Connection mới được tạo ở trạng thái stopped** đối với delivery đến consumer. Ứng dụng có thể tạo Session, producer, consumer và gửi message trước khi gọi **start()**, nhưng các consumer thuộc Connection đó chưa được phép nhận message theo đường nhận bình thường. JMS 2.0 **JMSContext** có hành vi auto-start mặc định riêng; xem mục 8.

### Timeline chuẩn của client JMS classic API

~~~mermaid
sequenceDiagram
    autonumber
    participant App as Java application
    participant CF as ConnectionFactory
    participant C as Connection
    participant S as Session
    participant B as Broker

    App->>CF: createConnection(user, password)
    CF-->>App: Connection C (delivery chưa start)
    App->>C: createSession(transacted, mode)
    C-->>App: Session S
    App->>S: createConsumer(queue)
    App->>C: start()
    App->>S: receive(timeout)
    S->>B: Nhận message từ destination
    B-->>S: Message
    S-->>App: Message
    App->>S: commit() / acknowledge()
    App->>C: close()
~~~

**Connection.start() không commit message.** Nó chỉ cho phép delivery. Nếu consumer nhận một message trong Session transacted nhưng chưa **commit()**, việc Connection đã start không làm broker tự coi message hoàn tất.

### Sự khác nhau giữa stop và close

| Thao tác | Mục đích | Tác động |
| --- | --- | --- |
| **start()** | Mở cho consumer nhận message | Áp dụng đến delivery của các Session thuộc Connection |
| **stop()** | Tạm dừng delivery | Kết nối vẫn tồn tại; không biến message đã xử lý thành ACK |
| **close()** | Kết thúc sử dụng Connection | Đóng Session và các tài nguyên JMS con; các transaction chưa hoàn tất không được coi đã commit |

Đừng dùng **stop()** như cơ chế bảo đảm một workflow được checkpoint an toàn. Message đã dispatch/in-flight và các callback đang chạy vẫn cần được xử lý theo quy tắc Session. Nếu đóng Connection khi còn transaction chưa commit, kết quả nhận có thể là **redelivery** sau khi consumer khác kết nối lại, tùy policy broker.

**close() không thay thế commit().** Mô hình đúng là xử lý dữ liệu, commit transaction theo yêu cầu, rồi mới đóng tài nguyên khi phạm vi sử dụng kết thúc.

### ExceptionListener giải quyết được gì?

~~~java
connection.setExceptionListener(exception ->
        System.err.println("JMS connection problem: "
                + exception.getMessage()));
~~~

Callback này giúp quan sát lỗi **bất đồng bộ**, ví dụ Connection gặp sự cố mà lời gọi hiện tại không trực tiếp ném exception. Nó **không thay thế** việc catch **JMSException** từ **send()/receive()/commit()**. Trong callback, tránh thao tác blocking hoặc tự ý dùng lại Session đang hỏng; đặt logic phục hồi ở thành phần điều phối lifecycle và tuân thủ tính năng failover của client.

Nếu ứng dụng bật tự động reconnect, phải xác định rõ provider xử lý **Session/consumer/subscription** thế nào sau failover. “Connection reconnect thành công” không tự chứng minh những side effect chưa commit đã được bảo toàn exactly-once.

## 4. Session: ranh giới gửi/nhận, ACK và transaction

**Session** được tạo từ Connection. Nó có ba vai trò kỹ thuật quan trọng:

1. **Factory cho các object JMS thuộc phạm vi xử lý:** message, producer, consumer, queue/topic handle.
2. **Ngữ cảnh tuần tự hóa việc xử lý message:** các operation và callback liên quan trong một Session tuân theo mô hình **single-threaded** của JMS.
3. **Phạm vi acknowledgment hoặc transaction:** quyết định khi nào message đã receive được xác nhận, khi nào send nằm trong transaction được commit, và tác dụng của rollback/recover.

### Ví dụ tạo Session không và có transaction

~~~java
// Non-transacted: provider tự ACK theo AUTO_ACKNOWLEDGE.
Session auto = connection.createSession(
        false, Session.AUTO_ACKNOWLEDGE);

// Non-transacted: ứng dụng chủ động acknowledge().
Session manual = connection.createSession(
        false, Session.CLIENT_ACKNOWLEDGE);

// Transacted: commit()/rollback() quyết định ACK/send trong session.
Session tx = connection.createSession(
        true, Session.SESSION_TRANSACTED);
~~~

Với API **Connection.createSession(boolean transacted, int acknowledgeMode)**, khi **transacted = true**, JMS transaction quyết định trạng thái; **acknowledgeMode không được dùng để thay thế commit/rollback**. Dùng **Session.SESSION_TRANSACTED** giúp code thể hiện ý định rõ ràng.

### Session không an toàn để dùng đồng thời từ nhiều thread

Quy tắc thực dụng:

- Một thread xử lý **một Session** tại một thời điểm.
- Không cho nhiều worker gọi **receive()**, **send()**, **commit()** đồng thời trên cùng Session.
- Khi cần nhiều consumer xử lý song song, tạo nhiều Session hoặc để framework JMS listener container cấp phát Session theo concurrency.
- Không dùng Session đang được gọi trong **MessageListener** từ một thread khác để commit/rollback cùng lúc.
- Khi một Connection có nhiều Session, **Connection.start()** mở delivery cho tất cả, nhưng **Session A.commit() chỉ commit transaction của A**.

Một producer có thể được tạo từ Session A, consumer từ Session B của cùng Connection; hai Session có transaction độc lập. Việc dùng chung Connection **không biến chúng thành một transaction**.

### Hành vi khi Session nhận nhiều message

Ví dụ một Session **CLIENT_ACKNOWLEDGE** đã nhận M1, M2, M3 nhưng chưa ACK. Gọi **M3.acknowledge()** theo hợp đồng JMS xác nhận **các message đã được tiêu thụ trong cùng Session**, không chỉ riêng M3.

Đây là lý do cần hiểu **Session là đơn vị ACK** trước khi dùng API trông như nằm trên object Message.

## 5. Phân biệt các acknowledgment mode trong Session

| Mode khi Session không transacted | Ai xác nhận? | Bẫy thường gặp |
| --- | --- | --- |
| **AUTO_ACKNOWLEDGE** | JMS provider ACK theo quy tắc khi **receive()** trả thành công hoặc listener xử lý xong bình thường | Ứng dụng chưa kịp commit DB nhưng message đã được ACK |
| **CLIENT_ACKNOWLEDGE** | Ứng dụng gọi **message.acknowledge()** | ACK có phạm vi các message đã tiêu thụ trong **cùng Session** |
| **DUPS_OK_ACKNOWLEDGE** | Provider có thể ACK trễ và gom lô | Có thể làm tăng xác suất message bị giao lại |
| **SESSION_TRANSACTED** | **session.commit()** xác nhận receive và hoàn tất send trong JMS transaction | Gọi acknowledge() không thay thế commit(); DB ngoài JMS vẫn độc lập |

**Session.recover()** dành cho **Session không transacted** để dừng/khởi động lại delivery của các message chưa được ACK theo cơ chế provider. Với **Session transacted**, dùng **rollback()** thay vì recover(). Không viết code gọi cả hai như hai thao tác retry tương đương trên cùng transaction.

### Tình huống lỗi minh họa

Giả sử consumer nhận **OrderPaid** trong Session transacted:

1. Consumer nhận M1.
2. Ghi database thành công, DB commit.
3. Kết nối broker đứt trước **session.commit()**.
4. Broker có thể phát lại M1 vì chưa xác nhận thành công transaction JMS.

Như vậy **ACK/commit JMS** xác định tiến độ trên broker, **không đồng nghĩa** transaction nghiệp vụ ở DB. Để không trừ tiền/cập nhật tồn kho hai lần, consumer dùng **eventId** ổn định, khóa duy nhất hoặc bảng processed_events cùng transaction DB và chỉ commit JMS sau khi transaction DB hoàn tất.

Nếu một Session cùng lúc nhận message và gửi message khác trong JMS transaction, **commit()** áp dụng cho các receive/send của Session đó trong cùng phạm vi JMS. Đây là một cách chuyển tiếp JMS-to-JMS khi phù hợp, nhưng không tự động bảo vệ side effect HTTP/JDBC ngoài Session.

## 6. Bài lab Java ActiveMQ Classic: thấy rõ ba đối tượng và start()

Ví dụ này dùng **ActiveMQ Classic** qua **javax.jms**, chủ động quản lý Connection và **hai Session transacted**. Ta gửi message trước khi **start()** Connection, thử receive khi Connection chưa start, rồi mở delivery và nhận; sau đó commit riêng Session tiêu thụ.

**Điều kiện chạy:**

- Broker Classic có OpenWire endpoint **tcp://127.0.0.1:61616** (hoặc sửa **BROKER_URL**).
- Tài khoản **BROKER_USER**, **BROKER_PASSWORD** có quyền gửi/tiêu thụ queue **lab.jms.objects**.
- JDK 17+, Maven. Mẫu dùng một phiên bản Classic client thuộc dòng **javax.jms**; trong hệ thống thật phải đối chiếu tương thích client/broker.
- Queue có thể được broker tự tạo nếu policy cho phép; nếu cấm auto-create, quản trị viên tạo trước queue cùng quyền phù hợp.

Tạo Maven project chỉ chứa ví dụ Classic. Nội dung **pom.xml**:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>lab.jms</groupId>
    <artifactId>classic-object-lifecycle</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.apache.activemq</groupId>
            <artifactId>activemq-client</artifactId>
            <version>5.18.3</version>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.3.0</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Tạo **src/main/java/ClassicObjectsLab.java**:

~~~java
import java.util.Objects;
import java.util.UUID;

import javax.jms.Connection;
import javax.jms.ConnectionFactory;
import javax.jms.DeliveryMode;
import javax.jms.Message;
import javax.jms.MessageConsumer;
import javax.jms.MessageProducer;
import javax.jms.Queue;
import javax.jms.Session;
import javax.jms.TextMessage;

import org.apache.activemq.ActiveMQConnectionFactory;

public final class ClassicObjectsLab {
    public static void main(String[] args) throws Exception {
        String url = System.getenv().getOrDefault(
                "BROKER_URL", "tcp://127.0.0.1:61616");
        String user = Objects.requireNonNull(
                System.getenv("BROKER_USER"), "Missing BROKER_USER");
        String password = Objects.requireNonNull(
                System.getenv("BROKER_PASSWORD"), "Missing BROKER_PASSWORD");
        String eventId = UUID.randomUUID().toString();

        // 1. Factory mô tả cách tạo kết nối.
        ConnectionFactory factory = new ActiveMQConnectionFactory(url);

        // 2. Connection mới được tạo, delivery chưa start().
        Connection connection = factory.createConnection(user, password);
        try {
            connection.setExceptionListener(error ->
                    System.err.println("Async JMS error: "
                            + error.getMessage()));

            // 3. Hai Session: transaction gửi khác transaction nhận.
            Session sender = connection.createSession(
                    true, Session.SESSION_TRANSACTED);
            Session receiver = connection.createSession(
                    true, Session.SESSION_TRANSACTED);
            try {
                Queue queue = sender.createQueue("lab.jms.objects");
                MessageProducer producer = sender.createProducer(queue);
                MessageConsumer consumer = receiver.createConsumer(queue);
                try {
                    producer.setDeliveryMode(DeliveryMode.PERSISTENT);

                    TextMessage outgoing =
                            sender.createTextMessage("OrderPaid:ORD-1001");
                    outgoing.setStringProperty("eventId", eventId);

                    producer.send(outgoing);
                    sender.commit();
                    System.out.println("SENT and sender.commit(): "
                            + eventId);

                    // Connection còn stopped: không được deliver tới consumer.
                    Message early = consumer.receive(600);
                    if (early != null) {
                        throw new IllegalStateException(
                                "Unexpected delivery before start()");
                    }
                    System.out.println("BEFORE start(): no message delivered");

                    connection.start(); // Mở delivery cho mọi Session của C.
                    Message incoming = consumer.receive(5000);
                    if (!(incoming instanceof TextMessage)) {
                        receiver.rollback();
                        throw new IllegalStateException("Expected TextMessage");
                    }

                    String receivedId =
                            incoming.getStringProperty("eventId");
                    if (!eventId.equals(receivedId)) {
                        receiver.rollback();
                        throw new IllegalStateException(
                                "Unexpected eventId " + receivedId);
                    }

                    System.out.println("RECEIVED: "
                            + ((TextMessage) incoming).getText());
                    receiver.commit(); // ACK transaction của receiver.
                    System.out.println("ACK via receiver.commit()");
                } finally {
                    consumer.close();
                    producer.close();
                }
            } finally {
                receiver.close();
                sender.close();
            }
        } finally {
            connection.close();
        }
    }
}
~~~

**Ghi chú về độ bền:** đoạn code cố ý dùng **hai Session cùng một Connection**, mỗi Session là một JMS transaction riêng. **sender.commit()** có thể đưa message vào broker ngay cả khi Connection chưa **start()**; **start()** điều khiển delivery cho consumer chứ không phải việc producer có thể gửi. **receiver.commit()** xác nhận message đã nhận, không làm lại transaction đã commit của sender.

Trong lab sạch, không có consumer khác cạnh tranh trên queue này và không có message tồn từ lần thử trước, output mong đợi:

~~~text
SENT and sender.commit(): <eventId>
BEFORE start(): no message delivered
RECEIVED: OrderPaid:ORD-1001
ACK via receiver.commit()
~~~

Khi có consumer khác đang đọc queue hoặc queue chứa backlog cũ, bài thử có thể thất bại dù Connection/Session đúng. Sử dụng queue riêng cho lab hoặc làm sạch **có chủ đích trong môi trường thử nghiệm**, không purge queue production. Bài minh họa không ghi DB thật; vì vậy đây là kiểm chứng JMS lifecycle, chưa phải mẫu idempotent order processing hoàn chỉnh.

Trên PowerShell:

~~~powershell
$env:BROKER_URL = "tcp://127.0.0.1:61616"
$env:BROKER_USER = "classic_app"
$env:BROKER_PASSWORD = "<your-classic-password>"

mvn -q compile exec:java "-Dexec.mainClass=ClassicObjectsLab"
~~~

Giá trị password trong ngoặc nhọn chỉ là chỗ điền và phải thay bằng secret thật. Nếu Classic broker dùng tài khoản khác, đặt đúng username và URL. Chạy Java trong thư mục Maven chứa hai tệp ví dụ; Docker Compose **.env** không tự động được nạp vào terminal chạy Maven.

### Vì sao tách sender và receiver thành hai Session?

Nếu chỉ dùng **một Session transacted** cho cả **producer.send()** và **consumer.receive()**, việc gửi message chưa **commit** có thể khiến receive không thấy message mới ngay, bởi message được gửi vẫn nằm trong transaction chưa hoàn tất. Tách hai Session và commit sender trước là cách kiểm chứng rõ ràng.

Sau đó, khi một Session khác đã ACK, Session kia không cần commit thêm để “xác nhận chung”. **Connection** không phải transaction coordinator của mọi Session con.

## 7. Cùng kiến trúc bằng Artemis và Jakarta Messaging

Với Artemis client hỗ trợ **jakarta.jms**, có thể viết lại chương trình bằng chính API ba object:

~~~java
import jakarta.jms.Connection;
import jakarta.jms.ConnectionFactory;
import jakarta.jms.Queue;
import jakarta.jms.Session;
import org.apache.activemq.artemis.jms.client.ActiveMQConnectionFactory;

// Mẫu trong một phương thức throws Exception.
ConnectionFactory factory =
        new ActiveMQConnectionFactory("tcp://127.0.0.1:61617");
try (Connection connection = factory.createConnection(user, password)) {
    try (Session session = connection.createSession(
            true, Session.SESSION_TRANSACTED)) {
        Queue queue = session.createQueue("lab.jms.objects");
        // Tạo producer/consumer, xử lý và session.commit()/rollback().
        connection.start();
    }
}
~~~

Đây là **đoạn minh họa cú pháp**, cần bổ sung logic producer/consumer nếu chạy thành chương trình hoàn chỉnh. Đổi factory/provider không làm thay đổi bản chất **Connection.start()** và **Session.commit()**. Không thể gộp hai ví dụ Classic javax và Artemis jakarta trong cùng source file như thể cùng một API binary.

Để dùng cách lập trình hiện đại hơn, **Jakarta Messaging/JMS 2.0 API** cung cấp **JMSContext**, kết hợp chức năng của Connection và Session trong một object gần gũi với try-with-resources. Nội dung tiếp theo cho thấy mapping này cụ thể.

## 8. JMSContext: lớp API tiện dụng có làm biến mất Connection và Session không?

**JMSContext** không xóa bỏ trách nhiệm kết nối và transaction; nó **gộp thao tác quản lý** để code ít boilerplate. Có thể hiểu:

| Legacy API | JMSContext API | Ranh giới vẫn phải hiểu |
| --- | --- | --- |
| **factory.createConnection(user, password)** | **factory.createContext(user, password, mode)** | Cấp client connection/session context |
| **connection.createSession(...)** | Mode được chọn khi tạo **JMSContext** | Session mode quyết định ACK hoặc transaction |
| **connection.start()** | **context.start()**, thường được auto-start khi tạo consumer | Vẫn có thời điểm delivery bắt đầu |
| **session.createProducer(queue)** | **context.createProducer()** tạo **JMSProducer** | Producer dùng context để gửi |
| **session.createConsumer(queue)** | **context.createConsumer(queue)** | Consumer nhận trong context |
| **session.commit()/rollback()** | **context.commit()/rollback()** | Vẫn chỉ là JMS transaction của context |
| **connection/session.close()** | **context.close()** hoặc try-with-resources | Vẫn phải giải phóng tài nguyên và hoàn tất transaction |

**Điểm khác quan trọng:** với **JMSContext**, mặc định các lời gọi tạo consumer có thể làm context tự động **start** connection (**autoStart = true**). Do đó, để kiểm chứng “nhận trước start() trả null” theo cách tường minh, gọi **context.setAutoStart(false)** trước khi tạo consumer.

### Ví dụ chạy độc lập với Artemis

Maven **pom.xml** cho dự án Artemis riêng:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>lab.jms</groupId>
    <artifactId>artemis-context-lifecycle</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.apache.activemq</groupId>
            <artifactId>artemis-jakarta-client</artifactId>
            <version>2.42.0</version>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.3.0</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Tạo **src/main/java/ArtemisContextLab.java**:

~~~java
import java.util.Objects;
import java.util.UUID;

import jakarta.jms.DeliveryMode;
import jakarta.jms.JMSConsumer;
import jakarta.jms.JMSContext;
import jakarta.jms.Message;
import jakarta.jms.Queue;
import jakarta.jms.TextMessage;

import org.apache.activemq.artemis.jms.client.ActiveMQConnectionFactory;

public final class ArtemisContextLab {
    public static void main(String[] args) throws Exception {
        String url = System.getenv().getOrDefault(
                "BROKER_URL", "tcp://127.0.0.1:61617");
        String user = Objects.requireNonNull(
                System.getenv("BROKER_USER"), "Missing BROKER_USER");
        String password = Objects.requireNonNull(
                System.getenv("BROKER_PASSWORD"), "Missing BROKER_PASSWORD");
        String eventId = UUID.randomUUID().toString();

        ActiveMQConnectionFactory factory =
                new ActiveMQConnectionFactory(url);

        // Mỗi JMSContext có phạm vi transaction riêng.
        try (JMSContext sender = factory.createContext(
                     user, password, JMSContext.SESSION_TRANSACTED);
             JMSContext receiver = factory.createContext(
                     user, password, JMSContext.SESSION_TRANSACTED)) {

            receiver.setAutoStart(false); // Phải làm trước createConsumer().
            Queue queue = sender.createQueue("lab.jms.context");
            JMSConsumer consumer = receiver.createConsumer(queue);

            TextMessage outgoing = sender.createTextMessage(
                    "OrderPaid:ORD-2002");
            outgoing.setStringProperty("eventId", eventId);
            sender.createProducer()
                    .setDeliveryMode(DeliveryMode.PERSISTENT)
                    .send(queue, outgoing);
            sender.commit();
            System.out.println("SENT " + eventId);

            Message before = consumer.receive(600);
            if (before != null) {
                receiver.rollback();
                throw new IllegalStateException(
                        "Unexpected delivery before receiver.start()");
            }
            System.out.println("Before receiver.start(): empty");

            receiver.start();
            Message incoming = consumer.receive(5000);
            if (!(incoming instanceof TextMessage)) {
                receiver.rollback();
                throw new IllegalStateException("Expected TextMessage");
            }
            String actual = incoming.getStringProperty("eventId");
            if (!eventId.equals(actual)) {
                receiver.rollback();
                throw new IllegalStateException(
                        "Unexpected eventId: " + actual);
            }

            System.out.println("RECEIVED: "
                    + ((TextMessage) incoming).getText());
            receiver.commit();
            System.out.println("RECEIVER COMMITTED");
        }
    }
}
~~~

Chạy bằng PowerShell trên host:

~~~powershell
$env:BROKER_URL = "tcp://127.0.0.1:61617"
$env:BROKER_USER = "artemis_app"
$env:BROKER_PASSWORD = "<your-artemis-password>"

mvn -q compile exec:java "-Dexec.mainClass=ArtemisContextLab"
~~~

Trong lab có broker Artemis publish trên **61616** thay vì **61617**, sửa **BROKER_URL** cho phù hợp. Nên có một queue test sạch và không có consumer cạnh tranh. Với cài đặt bảo mật chặt, queue **lab.jms.context** phải được tạo/bind đúng routing **ANYCAST** trước hoặc user có quyền tự tạo queue.

Kết quả kỳ vọng:

~~~text
SENT <eventId>
Before receiver.start(): empty
RECEIVED: OrderPaid:ORD-2002
RECEIVER COMMITTED
~~~

Đoạn này cho thấy **JMSContext vẫn cần session mode, start và commit**, nhưng code không cần gọi rõ **Connection.createSession()**. Các method như **context.createProducer().send(...)** không làm transaction gửi tự commit khi context đang ở **SESSION_TRANSACTED**.

### Khi nào chọn API nào?

- Ứng dụng Java mới với thư viện **Jakarta Messaging** phù hợp: ưu tiên **JMSContext** nếu đơn giản hóa vòng đời là lợi ích rõ ràng.
- Ứng dụng lâu năm hoặc framework/SDK đang dùng **javax.jms.Connection/Session**: giữ API tương thích và nâng cấp theo kế hoạch.
- Nếu cần kiểm soát rõ nhiều Session, client ID, nhiều consumer với cấu trúc tài nguyên phức tạp: có thể dùng classic API ngay cả khi provider hỗ trợ JMSContext.

Không xem **JMSContext** là một object tự do chia sẻ cho mọi request/thread. Nó vẫn thể hiện ngữ cảnh sử dụng session, có trạng thái transaction và phải được đóng đúng lifecycle.

## 9. Quan hệ “một Connection, nhiều Session” và giới hạn đồng thời

Một mẫu triển khai phổ biến là **một Connection phục vụ nhiều Session do từng worker quản lý**. Tùy client library, provider và cơ chế pooling, ứng dụng có thể dùng số lượng Connection khác nhau. Quy tắc không đổi: **không chia sẻ Session đồng thời**.

Ví dụ kiến trúc:

~~~mermaid
flowchart TB
    CF["Configured ConnectionFactory"] --> C["Managed Connection"]
    C --> S1["Session worker-1"]
    C --> S2["Session worker-2"]
    C --> S3["Session worker-3"]
    S1 --> R1["Consumer-1 / transaction-1"]
    S2 --> R2["Consumer-2 / transaction-2"]
    S3 --> R3["Consumer-3 / transaction-3"]
    R1 --> Q[("orders.in")]
    R2 --> Q
    R3 --> Q
~~~

Với queue **orders.in**, ba consumer thường chia nhau thông điệp; nếu broker dispatch message M1 cho worker-1 và M2 cho worker-2, **worker-2.commit()** không xác nhận M1 đang nằm ở worker-1. Mỗi transaction/ACK gắn với Session tương ứng.

### Những mẫu sử dụng cần tránh

**Sai: một Session dùng bởi nhiều thread**

~~~java
// Ví dụ SAI: cùng Session được hai tác vụ xử lý đồng thời.
ExecutorService workers = Executors.newFixedThreadPool(2);
workers.submit(() -> useSessionForOrder(session, "ORD-1"));
workers.submit(() -> useSessionForOrder(session, "ORD-2"));
~~~

Hai lời gọi cùng dùng **session** có thể chen nhau ở receive/send/commit; không có cách suy ra commit thuộc request nào bằng Java synchronization tự phát. Tạo Session riêng cho từng worker hoặc để listener container quản lý.

**Sai: mở kết nối cho từng message**

~~~text
for each message:
    new ConnectionFactory
    createConnection
    createSession
    send
    close
~~~

Cách này thường gây tốn chi phí handshake/auth, khó quản lý socket và tăng tải broker. Với ứng dụng có lưu lượng ổn định, dùng connection/session lifecycle phù hợp và pool/client manager được provider/framework hỗ trợ. Riêng chương trình CLI demo gửi một message rồi thoát thì việc tạo/đóng một connection mỗi lần là hợp lý.

**Sai: tưởng transaction A của Session gửi là transaction B của Session nhận**

~~~text
Connection C
├─ Session A: producer.send(M1); A.commit()    -> gửi xong ở A
└─ Session B: consumer.receive(M1); B.rollback() -> B có thể nhận lại
~~~

Hai Session cùng thuộc Connection nhưng có transaction riêng. Mức cô lập ở đây là theo Session, không theo Connection.

### JMS Listener và trách nhiệm của Session

Khi sử dụng **setMessageListener(...)**, provider gọi callback theo mô hình delivery của Session. Tránh sử dụng cùng Session từ thread ngoài để tác động đồng thời đến callback. Nếu listener bắt đầu xử lý nền rồi trả về ngay trong **AUTO_ACKNOWLEDGE**, provider có thể xác nhận message trước khi công việc nền thành công. Với dữ liệu cần bền vững, dùng transaction/ack rõ ràng và hoàn tất side effect trước khi báo xong.

## 10. Đóng tài nguyên: thứ tự và lỗi thường gặp

Trong ứng dụng CLI thuần JMS, thứ tự cleanup an toàn thường là:

1. Ngừng nhận việc mới và đợi hoặc hủy có chủ đích những thao tác đang chạy.
2. **commit()** transaction đã xử lý thành công hoặc **rollback()** transaction thất bại.
3. Đóng consumer/producer nếu ứng dụng quản lý trực tiếp.
4. Đóng **Session**.
5. Đóng **Connection**.

Đóng Connection cũng có thể đóng các resource con theo hợp đồng provider, nhưng việc **đóng rõ và quản lý transaction có chủ đích** giúp tránh che mất lỗi nghiệp vụ. Với try-with-resources (nếu API type hỗ trợ **AutoCloseable**) hoặc **JMSContext**, quản lý tài nguyên trở nên dễ theo dõi hơn.

### Lỗi đóng khi transaction chưa commit

Giả sử consumer đã nhận M1 trong Session transacted, nhưng chương trình return sớm:

~~~java
Session session = connection.createSession(
        true, Session.SESSION_TRANSACTED);
MessageConsumer consumer = session.createConsumer(queue);
Message message = consumer.receive(5000);
// Thiếu xử lý và session.commit().
session.close();
~~~

Kết quả: broker **không nên được coi là đã ACK** M1; với queue và policy phù hợp, M1 có thể được giao lại cho consumer khác. Không xem **close()** là “auto commit” các receive chưa được xử lý.

### Framework quản lý vòng đời khác code thuần

Nếu dùng Spring JMS listener container hoặc application server-managed ConnectionFactory, framework có thể cấp Connection/Session, transaction và auto-close ở cuối callback. Không tự ý gọi **close()** trên Connection mà framework đang chia sẻ hoặc giữ Session ngoài thời hạn callback, vì có thể cắt ngang các consumer khác. Xác định **ai sở hữu object**: code của bạn, container hay pool. Quy tắc phạm vi JMS vẫn giữ nguyên dù object lifecycle được tự động quản lý.

## 11. Những thí nghiệm phân biệt vai trò các object

| Thí nghiệm | Thay đổi duy nhất | Điều cần quan sát |
| --- | --- | --- |
| Factory không kết nối | Tạo factory khi broker chưa chạy, chưa gọi createConnection | Tạo factory có thể thành công; chứng minh việc kết nối chưa được kiểm chứng |
| Connection chưa start | Gửi + commit qua Session producer; consumer receive có timeout trước start | Không có delivery cho consumer trên Connection stopped |
| Bắt đầu delivery | Gọi **connection.start()** sau khi tạo consumer | Consumer có thể nhận message đang chờ |
| Hai Session | Sender commit, receiver rollback | Message đã gửi vẫn ở broker; receive chưa ACK có thể redeliver |
| Client ACK | Nhận hai message cùng Session rồi ACK message thứ hai | Nhận diện ACK bao trùm message đã tiêu thụ trong Session |
| Một Session chia thread | Thử mô phỏng đồng thời trên môi trường cách ly | Phát hiện API usage không hợp lệ/khó bảo toàn transaction; không dùng làm giải pháp production |
| Connection.close khi chưa commit | Nhận trong Session transacted rồi close | Message chưa hoàn tất có thể xuất hiện lại |
| JMSContext autoStart | So sánh **setAutoStart(false)** và mặc định | Nhận ra khác biệt điều khiển start so với classic Connection API |
| Sai user/destination | Dùng user không có quyền send/consume | Xác thực kết nối có thể thành công nhưng hoạt động trên destination bị từ chối |
| Mất broker sau receive | Đứt kết nối trước session.commit() | Có thể redelivery; cần eventId và idempotency tại DB |

Một phép thử về Session concurrency cần được thực hiện thận trọng vì vi phạm hợp đồng thread-safety có thể gây hành vi phụ thuộc provider; kết quả “chạy được một lần” không hợp thức hóa việc chia sẻ Session đồng thời.

### Minh họa kiểm tra delivery chưa start

Câu hỏi: **“Producer có gửi được khi Connection chưa start không?”**

Trong classic JMS API, có thể tạo producer, **send()**, **commit()**, rồi mới **start()** Connection. Lúc Connection chưa start, lời gọi **consumer.receive(timeout)** sẽ không trả về message để xử lý chỉ vì send đã thành công. Khi gọi **start()**, delivery mới được phép bắt đầu.

Hàm **start()** không làm broker route lại message hoặc thay đổi độ bền queue. Nó điều khiển trạng thái delivery đến consumer thuộc Connection. Message đã commit nằm ở destination phù hợp và có thể chờ consumer.

### Minh họa kiểm tra transaction session độc lập

Câu hỏi: **“Nếu Connection C có Session A và B, gọi A.commit() có ACK message ở B không?”**

Không. JMS transaction được xác định theo Session. Trường hợp **B.receive(M2)** rồi **A.commit()** không có nghĩa M2 được ACK. B phải tự **commit()** hoặc **rollback()**. Đây là lý do thiết kế worker concurrency không được sử dụng một cờ “Connection committed” để theo dõi tất cả message.

## 12. Các điểm khác nhau giữa Classic, Artemis và API đời mới

| Khía cạnh | ActiveMQ Classic theo ví dụ | Artemis theo ví dụ | Nguyên tắc chung |
| --- | --- | --- | --- |
| Provider factory | **org.apache.activemq.ActiveMQConnectionFactory** | **org.apache.activemq.artemis.jms.client.ActiveMQConnectionFactory** | Tạo client connection theo cấu hình |
| Namespace ví dụ | **javax.jms** với Classic 5.x | **jakarta.jms** với Artemis Jakarta client | Đừng trộn binary API một cách tùy tiện |
| Kết nối | **factory.createConnection()** | **createConnection()** hoặc **createContext()** | Kết nối và xác thực có chi phí/lifecycle |
| Session | **connection.createSession(...)** | Tương tự, hoặc ẩn trong **JMSContext** | ACK/transaction thuộc phạm vi session |
| Bắt đầu nhận | **connection.start()** | **connection.start()**; JMSContext thường auto-start | Trạng thái delivery khác với gửi và commit |
| Định tuyến mặc định | Queue/Topic theo Classic | Queue/Topic có thể ánh xạ tới ANYCAST/MULTICAST | Consumer phải dùng đúng destination |
| Failover/HA | Cấu hình và khả năng tùy release/client | Cấu hình và khả năng tùy release/client | Reconnect không tự tạo exactly-once business result |

Không dùng ví dụ này để suy diễn rằng **mọi Classic client đều là javax.jms** hoặc **mọi Artemis client đều là jakarta.jms**. Hệ sinh thái có nhiều phiên bản và artifact tương thích các API thế hệ khác nhau. Chọn **broker release → JMS client artifact → package imports → JDK** theo một bộ nhất quán.

### Mapping cho người đọc sử dụng Spring JMS

Nếu dùng **JmsTemplate** hoặc listener container, ba object gốc vẫn tồn tại nhưng framework quản lý:

~~~text
Configured ConnectionFactory
          |
          v
Spring JmsTemplate / Listener Container
          |
          v
Borrow/create Connection -> Session -> Producer/Consumer
          |
          v
ACK/commit/rollback according to container transaction config
~~~

Vấn đề cần xác minh khi cấu hình framework là **sessionTransacted**, acknowledge mode, listener error handling, concurrency, transaction manager và connection/session caching. Đừng suy rằng **@JmsListener** mặc định đã tự tạo transaction chung với database hoặc bảo đảm xử lý exactly-once.

## 13. Những lỗi thường gặp và cách khoanh vùng

| Triệu chứng | Khả năng liên quan | Bước chẩn đoán |
| --- | --- | --- |
| Khởi tạo factory thành công nhưng **createConnection()** thất bại | URL sai, broker chưa chạy, TLS hoặc credential không đúng | Kiểm tra endpoint, logs broker và loại connector |
| Producer gửi được nhưng **receive()** luôn timeout | Quên **connection.start()**, sai queue/selector hoặc chưa commit send | Đối chiếu start state, Session mode và destination |
| Message xuất hiện lại sau restart | Consumer nhận nhưng Session transacted chưa commit | Kiểm tra ranh giới **commit()/rollback()** và trạng thái DB |
| ACK một message nhưng nhiều message trong batch biến mất | **CLIENT_ACKNOWLEDGE** xác nhận các receive cùng Session | Kiểm tra số message đã consume trên Session đó |
| Nhiều thread đôi khi commit nhầm/nhận lạ | Session bị sử dụng đồng thời | Tách Session theo worker và xác minh lifecycle |
| Ứng dụng có nhiều consumer bị dừng đồng loạt | Gọi **connection.stop()/close()** trên Connection dùng chung | Xác định owner của Connection và ảnh hưởng đến mọi Session |
| Tạo consumer xong nhận được ngay dù không gọi start | **JMSContext autoStart** | Kiểm tra **setAutoStart(false)** |
| Broker restart khiến xử lý lặp | ACK/transaction chưa xác nhận thành công trước sự cố | Dùng eventId/idempotency ở nghiệp vụ |
| Client Classic/Artemis không compile | Trộn **javax.jms** và **jakarta.jms** hoặc artifact không phù hợp | Xác minh Maven dependency, package và release |
| Xóa/pool connection nhưng còn listener treo | Lifecycle do framework quản lý hoặc callback chưa kết thúc | Đối chiếu ownership và shutdown sequence |
| Tạo Connection quá nhiều, broker nhiều socket | Khởi tạo Connection/Session mỗi message | Dùng managed lifecycle và điều chỉnh pool/concurrency có đo đạc |

### Ba câu hỏi để review code JMS

1. **Factory được tạo và cấu hình ở đâu?** Nó có được dùng lại đúng cách, có secret/TLS/failover phù hợp, và code có phân biệt cấu hình với kết nối thật không?
2. **Ai sở hữu Connection và gọi start/close?** Mọi Session/consumer gắn vào Connection đó đều chịu tác động của start/stop/close; có listener nào bị đóng ngoài ý muốn không?
3. **Session có thuộc đúng một luồng xử lý và được commit/rollback đúng thời điểm?** Side effect đã bền vững trước JMS ACK chưa, và có chặn xử lý trùng sau redelivery không?

## 14. Ghi nhớ ranh giới trách nhiệm

**ConnectionFactory** quyết định **cách tạo kết nối**; **Connection** quyết định **vòng đời và lúc cho phép delivery**; **Session** quyết định **ngữ cảnh thao tác, thứ tự, ACK và transaction**. Việc một Connection có nhiều Session không khiến các Session dùng chung transaction, và việc Connection được start không khiến message tự động hoàn tất nghiệp vụ. Với JMSContext, các trách nhiệm đó vẫn tồn tại dù API đã rút gọn.

Khi viết producer/consumer Java cho **ActiveMQ Classic** hay **Artemis**, hãy kiểm tra lifecycle theo thứ tự: **factory → connection/context → session mode → producer/consumer → start nếu cần → send/receive → commit/ack hoặc rollback → close**. Nhờ đặt đúng ranh giới trách nhiệm, ta dễ phát hiện lỗi thiếu start, commit sai Session, dùng chung Session giữa thread và xử lý trùng khi broker phát lại thông điệp.
