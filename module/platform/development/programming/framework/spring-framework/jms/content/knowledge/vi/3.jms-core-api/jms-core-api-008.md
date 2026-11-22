# Connection.start(), stop() và close() trong JMS API gốc

## 1. Vì sao cần quản lý vòng đời Connection?

Trong Jakarta Messaging (trước đây là Java Message Service, JMS), **Connection** biểu diễn kết nối logic của ứng dụng tới một JMS provider/message broker. Ứng dụng thường lấy một ConnectionFactory đã cấu hình để tạo Connection, rồi tạo Session, MessageProducer và MessageConsumer.

Bài học tập trung vào ba thao tác điều khiển vòng đời của **classic JMS API**:

- **start()**: bắt đầu hoặc tiếp tục giao thông điệp **đến consumer** thuộc Connection.
- **stop()**: tạm dừng việc giao thông điệp **đến tất cả consumer** thuộc Connection, nhưng vẫn giữ Connection và tài nguyên của nó để có thể chạy lại.
- **close()**: đóng Connection và các đối tượng con, kết thúc vòng đời; muốn làm việc tiếp phải tạo Connection mới.

Hiểu đúng ba thao tác giúp tránh ba lỗi rất phổ biến: tạo consumer rồi quên gọi start(), tưởng stop() sẽ ngăn producer gửi message, hoặc dùng close() như một cách tạm dừng có thể khởi động lại.

### 1.1. Vị trí của Connection trong JMS API

~~~text
ConnectionFactory
    └── Connection                         (vòng đời: start / stop / close)
          ├── Session A                    (ngữ cảnh xử lý tuần tự)
          │     ├── MessageProducer
          │     └── MessageConsumer A
          └── Session B
                ├── MessageProducer
                └── MessageConsumer B
~~~

Connection thường là tài nguyên tương đối nặng vì liên quan xác thực, kết nối mạng và trạng thái provider; một Connection có thể phục vụ nhiều Session. **Connection hỗ trợ sử dụng đồng thời**, còn **Session phải tuân thủ mô hình sử dụng tuần tự**; không dùng chung một Session một cách tùy tiện giữa nhiều thread.

API gốc là bộ ba Connection + Session + MessageProducer/MessageConsumer, với những chữ ký quan trọng:

~~~java
Connection connection = connectionFactory.createConnection();
Session session = connection.createSession(
        false, Session.AUTO_ACKNOWLEDGE);
connection.start();
connection.stop();
connection.close();
~~~

Đây là **đoạn minh họa**, chưa phải chương trình chạy độc lập: biến connectionFactory phải được tạo hoặc lấy từ JNDI/provider. Ví dụ độc lập, có dependency và lệnh chạy, nằm ở mục 5.

**Tên package:** JMS 1.x/Java EE cũ dùng javax.jms.*; Spring Framework 6, Spring Boot 3 và Jakarta Messaging 3.x dùng jakarta.jms.*. Ba thao tác start/stop/close giữ ý nghĩa nền tảng tương ứng, nhưng không trộn hai namespace trong cùng một chương trình.

## 2. Mô hình trạng thái và ảnh hưởng thực sự

Connection **vừa được tạo ở trạng thái stopped**. Kết nối có thể đã được thiết lập tới provider, nhưng broker chưa được phép giao message cho consumer của Connection đó. start() và stop() thay đổi trạng thái nhận; close() chấm dứt tài nguyên.

~~~mermaid
stateDiagram-v2
    [*] --> Stopped: createConnection()
    Stopped --> Started: start()
    Started --> Stopped: stop()
    Started --> Closed: close()
    Stopped --> Closed: close()
    Closed --> [*]
~~~

| Trạng thái | Consumer nhận message mới? | Producer gửi message? | Có thể quay về nhận message? |
| --- | --- | --- | --- |
| Mới tạo / stopped | Không; receive(timeout) có thể hết thời gian và trả null | Có | Có, gọi start() |
| Started | Có, theo quy tắc queue/topic và session | Có | Đang nhận |
| Stopped sau khi stop() | Tạm ngưng giao đến mọi consumer thuộc connection | Có | Có, gọi start() |
| Closed | Không; session/consumer cũ không còn dùng được | Không; producer cũ không còn dùng được | Không trên connection đã đóng |

**start() không phải là “mở socket”; stop() không phải là “ngắt socket”.** Cả hai điều khiển **message delivery** tới phía nhận của Connection. Một producer vẫn được phép gửi message khi Connection chưa start hoặc đã stop. Trạng thái stopped cũng không đồng nghĩa broker xóa message trong queue hay xóa subscription.

Các lời gọi lặp có quy tắc xác định:

- start() trên Connection đã started: được bỏ qua.
- stop() trên Connection đã stopped: được bỏ qua.
- close() trên Connection đã closed: không được báo lỗi chỉ vì đã đóng.
- start() hoặc stop() sau khi Connection đã closed: thao tác sử dụng tài nguyên đã đóng, không hợp lệ (IllegalStateException theo API).

Đừng dùng cơ chế bỏ qua lời gọi lặp để che lỗi quản lý vòng đời. Cần xác định rõ thành phần nào sở hữu Connection và có trách nhiệm đóng nó.

## 3. Connection.start(): bắt đầu giao thông điệp đến consumer

### 3.1. Thứ tự chuẩn để setup

Với classic API, trình tự thường là:

1. Lấy ConnectionFactory và tạo Connection; trạng thái lúc này là stopped.
2. Tạo Session với chế độ transaction/acknowledgement phù hợp.
3. Tạo Destination, MessageConsumer và MessageProducer khi cần.
4. Nếu dùng callback, đăng ký MessageListener bằng setMessageListener(...).
5. **Sau khi cấu hình xong**, gọi connection.start() một lần để cho phép nhận.

~~~java
Connection connection = factory.createConnection();
try {
    Session session = connection.createSession(
            false, Session.AUTO_ACKNOWLEDGE);
    MessageConsumer consumer = session.createConsumer(destination);

    // Đăng ký listener hoặc chuẩn bị luồng receive trước khi start.
    connection.start();

    Message received = consumer.receive(5_000);
    // Xử lý received nếu khác null.
} finally {
    connection.close();
}
~~~

Đây là minh họa về thứ tự: factory và destination cần được cấp trước khi chạy. Nếu gọi start() quá sớm rồi mới đăng ký listener, message có thể được giao ngay trong lúc ứng dụng còn đang cấu hình các đối tượng khác.

### 3.2. Hai hình thức nhận message

**Nhận đồng bộ:** MessageConsumer.receive(), receive(timeout) hoặc receiveNoWait() chạy ở thread gọi. Khi Connection còn stopped, receive có thể chờ; với receive(timeout), bộ đếm thời gian **vẫn chạy** nên lệnh có thể trả null do hết hạn ngay cả khi queue đang có message. Trong Jakarta Messaging, receive(0) nghĩa là chờ không giới hạn thời gian; một số ứng dụng vô tình dùng 0 với ý định "không chờ" rồi bị kẹt.

**Nhận bất đồng bộ:** setMessageListener(...) đăng ký callback onMessage(Message). Provider không được giao message vào callback trước khi Connection được start(). Sau khi start(), listener có thể được gọi trên thread do provider/container điều phối. Không suy ra một thread chung cho mọi Session; quy tắc tuần tự áp dụng trong phạm vi Session.

### 3.3. Producer không cần start() để gửi

Một ứng dụng chỉ gửi thông điệp có thể tạo Connection, Session và MessageProducer rồi gọi send(...) **mà không start()**. Lời gọi start() quan trọng cho **phía nhận**. Ví dụ trong một Connection đang stopped:

~~~java
producer.send(session.createTextMessage("queued while stopped"));
// Gửi message hợp lệ dù connection chưa start.
~~~

Message được broker nhận/lưu theo chính sách destination, delivery mode, transaction, TTL và cấu hình provider; "send được" không tự hứa chắc về độ bền trong mọi cách triển khai.

## 4. Connection.stop(): tạm dừng message delivery

### 4.1. Chính xác điều gì bị dừng?

connection.stop() tạm dừng **tất cả consumer** thuộc Connection đó, kể cả consumer trên các Session khác nhau cùng Connection. Khi stopped:

- Không giao message mới tới MessageListener.onMessage(...) của connection đó.
- Các lệnh receive() đang đợi không được trả về một message mới do connection tiếp tục delivery; receive(timeout) vẫn có thể hết hạn và trả null.
- Không ngăn MessageProducer.send(...); không đóng Session hay MessageConsumer.
- Không tự xóa message trong broker, không phải cơ chế xóa queue hoặc hủy subscription.
- Không tự động commit/rollback transaction đang mở hay tự xác nhận message đang chờ acknowledgement.

Ví dụ thời gian:

~~~text
T0: createConnection()       -> STOPPED
T1: producer.send("A")       -> gửi thành công dù STOPPED
T2: consumer.receive(200)    -> null vì vẫn STOPPED
T3: connection.start()       -> STARTED
T4: consumer.receive(5000)   -> nhận "A"
T5: connection.stop()        -> STOPPED
T6: producer.send("B")       -> vẫn gửi được
T7: consumer.receive(200)    -> null vì STOPPED
T8: connection.start()       -> STARTED
T9: consumer.receive(5000)   -> nhận "B"
~~~

Đây là kịch bản có một producer và một consumer trên temporary queue của ví dụ mục 5. Khi có nhiều consumer, selector, expiration, retry hoặc message priority, không thể suy luận thứ tự nhận một cách đơn giản như vậy.

### 4.2. stop() có thể chặn thread gọi

Theo đặc tả, stop() **chỉ được trả về sau khi delivery đã thực sự tạm dừng**. Nếu có MessageListener đang chạy, lệnh phải chờ các listener đó hoàn thành. Trong khoảng chờ, listener còn đang chạy vẫn phải được dùng đầy đủ các dịch vụ của Connection để hoàn tất công việc.

Hệ quả:

- Gọi stop() từ thread quản trị/vòng đời khi muốn tạm dừng consumer.
- **Không mặc định stop() là non-blocking**; nếu xử lý listener chậm hoặc kẹt, stop() cũng có thể bị chậm.
- Khi stop() trả về bình thường, không còn listener thuộc Connection đó đang được callback; việc xử lý đã nhận phải được quản lý bởi ứng dụng/transaction tương ứng.
- Không gọi stop() trên chính Connection từ bên trong onMessage() rồi trông đợi hành vi nhất quán giữa các provider. Jakarta Messaging cho phép hai cách xử lý trường hợp này: ném jakarta.jms.IllegalStateException **hoặc** hoàn tất stop theo quy tắc đặc tả. Vì vậy đây là cách gọi **không portable**.

**stop() không phải là một “global consumer pause”.** Nếu instance khác dùng Connection riêng, instance đó vẫn có thể nhận message. Stop cũng không bảo đảm metrics như queue depth thay đổi tức thời theo kỳ vọng: provider có thể có buffer/prefetch và cơ chế acknowledgement riêng.

### 4.3. Khi nào nên stop()?

Một số tình huống hợp lý: tạm ngừng nhận thêm công việc để bảo trì một consumer thủ công; hoàn tất cấu hình trước khi kích hoạt callback; chủ động kiểm soát luồng tiêu thụ trong chương trình JMS tự quản lý.

Nếu cần graceful shutdown toàn ứng dụng, thường phải kết hợp: dừng tiếp nhận mới, chờ/giới hạn thời gian hoàn tất tác vụ đang chạy, xử lý transaction/acknowledgement và sau đó close. stop() đơn lẻ không thay thế quy trình này.

## 5. Ví dụ chạy được với Java 17, Jakarta JMS và Apache ActiveMQ Artemis

Ví dụ này minh họa trực tiếp ba phương thức trong **classic API**, không phụ thuộc Spring container. Dùng Artemis broker cục bộ và temporary queue do Session tạo ra, nhờ đó mỗi lượt chạy có queue riêng và dễ quan sát.

### 5.1. Chuẩn bị broker

Cần Java 17+, Maven 3.9+, Docker và cổng 61616 còn trống. Chạy broker thử nghiệm bằng image chính thức:

~~~bash
docker run --detach --rm --name jms-lifecycle-broker -p 61616:61616 -p 8161:8161 apache/artemis:latest-alpine
~~~

Chờ broker sẵn sàng trên cổng 61616; image mặc định dùng username/password artemis/artemis. Tài khoản này chỉ dành cho demo, không dùng trong production. Dùng docker logs jms-lifecycle-broker để quan sát khởi động nếu kết nối chưa được.

Cấu trúc project:

~~~text
jms-connection-lifecycle/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── example/
                └── jms/
                    └── ConnectionLifecycleDemo.java
~~~

### 5.2. Maven pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>jms-connection-lifecycle</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>jakarta.jms</groupId>
            <artifactId>jakarta.jms-api</artifactId>
            <version>3.1.0</version>
        </dependency>
        <dependency>
            <groupId>org.apache.activemq</groupId>
            <artifactId>artemis-jakarta-client</artifactId>
            <version>2.37.0</version>
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
                <version>3.5.0</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Các phiên bản được ghim để bài có đầu vào tái lập. jakarta.jms-api cung cấp interface; artemis-jakarta-client cung cấp implementation cho provider Artemis. Thay library/provider có thể thay cách cấu hình factory, nhưng hành vi ba phương thức phải tuân thủ đặc tả JMS.

### 5.3. Java class hoàn chỉnh

Đặt đúng file src/main/java/example/jms/ConnectionLifecycleDemo.java:

~~~java
package example.jms;

import jakarta.jms.Connection;
import jakarta.jms.ConnectionFactory;
import jakarta.jms.JMSException;
import jakarta.jms.Message;
import jakarta.jms.MessageConsumer;
import jakarta.jms.MessageProducer;
import jakarta.jms.Session;
import jakarta.jms.TemporaryQueue;
import jakarta.jms.TextMessage;
import org.apache.activemq.artemis.jms.client.ActiveMQConnectionFactory;

public final class ConnectionLifecycleDemo {
    private ConnectionLifecycleDemo() {}

    public static void main(String[] args) throws JMSException {
        ConnectionFactory factory =
                new ActiveMQConnectionFactory("tcp://localhost:61616");
        Connection connection = factory.createConnection("artemis", "artemis");

        try {
            Session session = connection.createSession(
                    false, Session.AUTO_ACKNOWLEDGE);
            TemporaryQueue queue = session.createTemporaryQueue();
            MessageProducer producer = session.createProducer(queue);
            MessageConsumer consumer = session.createConsumer(queue);

            // Connection mới: đang ở STOPPED. Producer vẫn gửi được.
            producer.send(session.createTextMessage("A"));
            System.out.println("Sent A before start");

            Message beforeStart = consumer.receive(200);
            System.out.println("Before start: " + describe(beforeStart));

            // Bật delivery cho consumer của connection này.
            connection.start();
            Message first = consumer.receive(5_000);
            System.out.println("After start: " + describe(first));

            // Tạm dừng delivery, không hủy producer/consumer.
            connection.stop();
            producer.send(session.createTextMessage("B"));
            System.out.println("Sent B while stopped");

            Message whileStopped = consumer.receive(200);
            System.out.println("While stopped: " + describe(whileStopped));

            // Bật lại trên cùng Connection/Session/Consumer.
            connection.start();
            Message second = consumer.receive(5_000);
            System.out.println("After restart: " + describe(second));
        } finally {
            // close() đóng cả các session/producer/consumer thuộc connection.
            connection.close();
            System.out.println("Connection closed");
        }
    }

    private static String describe(Message message) throws JMSException {
        if (message == null) {
            return "null";
        }
        if (message instanceof TextMessage text) {
            return text.getText();
        }
        return message.getClass().getSimpleName();
    }
}
~~~

Ở đây chỉ một thread sử dụng Session và MessageConsumer; producer gửi message trước khi gọi receive nên không có tranh chấp thread. TemporaryQueue được tạo riêng theo Connection và tự hết vòng đời khi Connection đóng. Không cần cấu hình một queue cố định cho ví dụ.

**Giải thích sát code:**

1. createConnection(...) trả Connection ở trạng thái stopped; createSession(...) và createConsumer(...) không tự start trong classic API.
2. send("A") thành công khi stopped vì start/stop chỉ ảnh hưởng consumer delivery.
3. receive(200) không nhận message; sau 200 ms có thể trả null. Trong demo khi broker hoạt động bình thường, giá trị là null.
4. start() cho phép receive(5000) lấy A.
5. stop() tạm dừng; gửi B vẫn hợp lệ; receive(200) không nhận B.
6. start() lần nữa cho phép nhận B trên consumer cũ.
7. finally luôn gọi close(), cả khi phần xử lý ném JMSException; các tài nguyên con do Connection quản lý được đóng cùng Connection.

Nếu hệ thống quá chậm khiến receive(5000) trả null, cần kiểm tra broker, transport, quyền truy cập và log. Ví dụ không giả định rằng mọi network đều trả kết quả trong đúng 5 giây.

### 5.4. Chạy project

Tại thư mục chứa pom.xml:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=example.jms.ConnectionLifecycleDemo
~~~

Kết quả ứng dụng dự kiến với broker hoạt động và một consumer của temporary queue:

~~~text
Sent A before start
Before start: null
After start: A
Sent B while stopped
While stopped: null
After restart: B
Connection closed
~~~

Các log do Artemis/client phát ra có thể xuất hiện thêm tùy cấu hình logging; nội dung trên là những dòng System.out.println của ứng dụng, đúng thứ tự khi nhận đủ A và B. Nếu cần dừng container demo, chạy docker stop jms-lifecycle-broker.

### 5.5. Minh họa try-with-resources

Vì Connection extends AutoCloseable, nếu chỉ cần đảm bảo close() được gọi thì có thể viết:

~~~java
try (Connection connection = factory.createConnection()) {
    Session session = connection.createSession(
            false, Session.AUTO_ACKNOWLEDGE);
    // Cấu hình consumer, gọi start()/stop() khi cần.
} // Tự động connection.close() kể cả khi có exception.
~~~

Đây là snippet bổ sung: factory được tạo ở ngoài, không phải chương trình chạy độc lập. Chương trình hoàn chỉnh phía trên dùng finally để thể hiện tường minh close().

## 6. close(): kết thúc vòng đời và tác động lên message đang xử lý

### 6.1. Các tác động bắt buộc

Khi connection.close() được gọi:

1. Provider kết thúc các lệnh nhận đang chờ trên consumer của Connection. Với receive() đang chờ, việc kết thúc có thể trả **một message hoặc null** tùy thời điểm; không được suy luận “null luôn nghĩa là Connection đã close”.
2. Nếu listener đang xử lý message, provider phải cho listener đó hoàn thành theo quy định đóng có trật tự; vì vậy close() cũng **có thể chặn thread gọi** đến khi xử lý đang chạy kết thúc.
3. Connection đóng các Session, MessageProducer, MessageConsumer, QueueBrowser liên quan, đồng thời giải phóng tài nguyên provider.
4. Sau khi đóng, các thao tác sử dụng lại Connection, Session, producer hoặc consumer cũ là không hợp lệ. Gọi close() lần nữa được bỏ qua.

Ví dụ sai:

~~~java
connection.close();
connection.start(); // Sai: Connection đã CLOSED, không thể restart.
~~~

Ví dụ đúng nếu cần kết nối mới:

~~~java
connection.close();
Connection next = factory.createConnection();
try {
    // Tạo Session, consumer mới và gọi next.start() khi nhận.
} finally {
    next.close();
}
~~~

**close() không phải cách “chờ broker xử lý hết mọi message”.** Nó chấm dứt các hoạt động của những consumer thuộc chính Connection đó; message còn lại trong queue hoặc durable subscription tiếp tục tuân theo policy lưu trữ/acknowledgement của provider.

### 6.2. Điều gì xảy ra với transaction và acknowledgement?

| Session mode | close() liên quan đến dữ liệu chưa hoàn tất |
| --- | --- |
| SESSION_TRANSACTED | Giao dịch JMS còn mở khi đóng Connection phải rollback. Các lượt gửi/nhận chưa commit tuân theo rollback của provider. |
| CLIENT_ACKNOWLEDGE | Đóng Connection **không ép acknowledge** các message client chưa xác nhận. Không được gọi message.acknowledge() trên message nhận từ Session đã đóng. |
| AUTO_ACKNOWLEDGE | Ack gắn với hoàn tất nhận/xử lý theo quy tắc API. Không nên suy luận close() sẽ bảo đảm hoàn thành mọi tác vụ hay mọi side effect; phải hiểu thời điểm listener hoàn tất. |

Cần phân biệt close() với session.commit(), session.rollback() và message.acknowledge(). start()/stop() là điều khiển delivery, **không phải công cụ commit hay ack**. Với queue hoặc durable subscription, message chưa được xác nhận có thể được giao lại khi consumer hợp lệ mới hoạt động; bảo đảm chính xác còn phụ thuộc delivery mode, TTL, broker và việc client có tuân thủ protocol hay không.

Nếu ứng dụng ghi DB/HTTP side effect rồi crash trước JMS commit/ack, provider có thể redeliver. Dùng business idempotency key để xử lý trùng; ba phương thức lifecycle không tạo ra exactly-once end-to-end.

### 6.3. Tránh close() từ chính onMessage()

Cũng như stop(), khi một MessageListener gọi close() trên Connection mà chính nó đang sử dụng, chuẩn cho phép provider **ném IllegalStateException hoặc thực hiện close** theo quy định. Kết quả không portable; đây không phải pattern shutdown an toàn.

Để dừng consumer theo tín hiệu nghiệp vụ, nên chuyển quyết định tới thành phần quản lý vòng đời trên thread điều phối; không đóng Connection trong callback đang chạy. Nếu dùng Spring container, dùng lifecycle của container ở mục 8.

## 7. Phân biệt các thao tác thường bị nhầm

| Thao tác | Phạm vi | Tạm dừng / kết thúc | Producer có gửi được bằng Connection cũ? |
| --- | --- | --- | --- |
| Connection.start() | Tất cả consumer thuộc Connection | Cho phép/tiếp tục nhận | Có |
| Connection.stop() | Tất cả consumer thuộc Connection | Tạm dừng delivery | Có |
| Connection.close() | Connection và tài nguyên con | Kết thúc | Không |
| MessageConsumer.close() | Một consumer | Kết thúc consumer đó | Producer khác có thể tiếp tục nếu Connection vẫn mở |
| Session.close() | Một Session và tài nguyên con | Kết thúc Session | Các Session khác có thể tiếp tục nếu Connection vẫn mở |
| Session.commit() | Transaction của một transacted Session | Chốt transaction, không chuyển trạng thái Connection | Có |
| Session.rollback() | Transaction của một transacted Session | Hủy transaction, có thể kích hoạt redelivery | Có |

Một Session không nên được sử dụng đồng thời từ nhiều thread tùy ý. Việc một Connection hỗ trợ nhiều Session không có nghĩa mọi thao tác sử dụng chung Session là thread-safe. Đặc biệt khi gắn MessageListener cho Session, thread provider đang điều phối callback quản lý chuỗi delivery của Session đó.

### Hai timeline so sánh stop() và close()

~~~text
PAUSE:
producer send -> queue giữ message -> stop() -> không giao consumer
                                        |
                                        +-> start() -> consumer lại nhận

SHUTDOWN:
producer send -> consumer đang xử lý -> close() đợi xử lý đang diễn ra
                                        |
                                        +-> session/consumer/connection đóng
                                        +-> muốn làm lại: createConnection()
~~~

Nếu yêu cầu là "ngừng nhận thêm job nhưng cho những job đã nhận chạy nốt", stop() có thể là một mảnh ghép của quy trình drain ở phía application; nhớ rằng nó tác động trên **toàn Connection** và có thể đợi listener. Đừng quên chính sách timeout và cách xử lý công việc chưa acknowledge.

## 8. Liên hệ với Spring Framework JMS

### 8.1. Khi dùng Spring, ai sở hữu Connection?

Ở ứng dụng Spring thông thường, JmsTemplate và listener container tạo/quản lý Connection/Session thông qua ConnectionFactory. Vì vậy code nghiệp vụ gọi jmsTemplate.convertAndSend(...) hay dùng @JmsListener **thường không cần tự gọi Connection.start/stop/close**. Việc tự đóng Connection được framework quản lý có thể gây lỗi cho listener/producer khác cùng sử dụng tài nguyên đó.

Ví dụ listener do Spring quản lý:

~~~java
@Component
class OrderListener {
    @JmsListener(id = "ordersListener", destination = "orders")
    public void handle(String body) {
        // Xử lý message theo transaction/ack configuration của container.
    }
}
~~~

Đoạn trên là snippet trong một ứng dụng Spring có dependency JMS và @EnableJms/cấu hình tương đương; không phải class độc lập biên dịch chỉ bằng javac. Spring thiết lập container, tạo consumer và quản lý start/stop cùng lifecycle application.

### 8.2. Muốn tạm dừng một listener Spring?

Điều khiển **listener container** qua JmsListenerEndpointRegistry hoặc lifecycle infrastructure của Spring, ví dụ:

~~~java
MessageListenerContainer container =
        registry.getListenerContainer("ordersListener");
if (container != null) {
    container.stop();   // Dừng container có id tương ứng.
    // ...
    container.start();  // Tiếp tục container khi được phép.
}
~~~

Đây là snippet: registry phải được inject và listener có id ordersListener. Sự khác biệt là stop/start theo **một listener container** và chính sách quản lý của nó; không nên mặc định một lời gọi trực tiếp Connection.stop() là cách chính xác để điều khiển một endpoint Spring. Các container có thể quản lý shared connection hoặc nhiều connection/session, nên hãy chọn điểm điều khiển ở tầng framework.

Một vài lưu ý vận hành: container có thể start tự động với application; cần cấu hình autoStartup khi yêu cầu manual start; đảm bảo shutdown không cắt ngang transaction hoặc timeout ngoài ý muốn; tài nguyên được Spring thu hồi khi đóng ApplicationContext theo lifecycle của container.

### 8.3. Classic Connection so với JMSContext

Jakarta Messaging có **simplified API** với JMSContext gom vai trò Connection và Session. Khác biệt đặc biệt quan trọng: mặc định JMSContext **tự start khi tạo consumer đầu tiên**, còn classic Connection mới tạo vẫn stopped cho tới khi gọi start() rõ ràng.

Nếu muốn chờ setup xong mới nhận trong simplified API:

~~~java
try (JMSContext context = factory.createContext()) {
    context.setAutoStart(false);
    JMSConsumer consumer = context.createConsumer(destination);
    // Hoàn thành setup...
    context.start();
    // ...
    context.stop();
}
~~~

Đây là snippet; factory và destination phải có trước, và JMSContext thuộc simplified API nên hành vi exception/lifecycle có khác biệt (ví dụ IllegalStateRuntimeException), không được bê nguyên giả định về start mặc định của classic Connection sang đây.

## 9. Lỗi thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân nên kiểm tra | Cách khắc phục |
| --- | --- | --- |
| Queue có message nhưng consumer không nhận | Quên connection.start() trong classic API; connection đã stop | Kiểm tra lifecycle và gọi start() sau khi tạo consumer. |
| Đã gọi stop() nhưng broker vẫn có message mới | stop() không chặn producer | Dừng phía producer theo chính sách riêng nếu thật sự cần ngừng gửi. |
| stop() lâu không trả về | Listener đang chạy; stop() phải đợi callback hoàn thành | Kiểm tra thời gian xử lý, thread dump, transaction và timeout. |
| Sau stop(), receive(timeout) trả null | Timer vẫn chạy dù delivery tạm dừng | Phân biệt timeout với queue rỗng; gọi start() khi cần nhận. |
| Sau close(), start()/send()/receive() lỗi | Tài nguyên đã bị đóng | Tạo Connection và các đối tượng con mới. |
| Ứng dụng thoát nhưng broker còn message | Chưa ack/commit hoặc broker duy trì queue/durable subscription | Kiểm tra transaction, ack, delivery mode và retention. |
| Một listener dừng làm listener khác cũng dừng | Các consumer thuộc cùng Connection; stop ảnh hưởng toàn connection | Tách ownership/connection hoặc điều khiển riêng qua container Spring. |
| Callback cố gọi stop/close chính Connection | Hành vi phụ thuộc provider, có thể IllegalStateException | Di chuyển thao tác shutdown sang lifecycle manager bên ngoài listener. |

### Checklist khi điều tra

1. Xác định chương trình đang dùng **classic Connection**, JMSContext hay **Spring-managed listener**.
2. Xác định ai tạo và ai sở hữu Connection; ai được phép start/stop/close.
3. Ghi log trạng thái ứng dụng quanh những lời gọi lifecycle và exception, tránh giả định JMS Connection cung cấp một hàm isStarted chuẩn để đọc trực tiếp.
4. Kiểm tra destination, selector, message expiration, quyền, transaction và acknowledgement; không xem start/stop là lời giải cho mọi sự cố "không nhận message".
5. Khi pause/shutdown, theo dõi callback còn chạy, số message inflight, việc redelivery và thời gian chờ.
6. Nếu thử nghiệm trong broker/provider khác, xác nhận những giả định về connection pooling, prefetch và listener container có đúng với triển khai đó.

## 10. Câu hỏi tự kiểm tra

**1. Connection vừa tạo có tự giao message đến consumer chưa?** Chưa. Classic Connection mặc định stopped; phải gọi start() để cho phép delivery.

**2. stop() có ngăn một producer của cùng Connection gửi vào queue không?** Không. Nó chỉ điều khiển incoming delivery đến consumer của Connection.

**3. Có thể dùng start() sau stop() trên cùng Connection không?** Có, miễn Connection chưa close.

**4. Có thể dùng start() sau close() trên cùng Connection không?** Không; phải tạo Connection mới.

**5. stop() trả về khi listener đang chạy hay sau khi đã xử lý xong callback đang chạy?** Theo chuẩn, nó phải chờ các listener đang chạy hoàn tất rồi mới trả về, để đảm bảo message delivery đã tạm dừng.

**6. close() có tự commit transacted Session không?** Không. Giao dịch JMS còn mở phải rollback khi Connection đóng.

**7. close() có tự acknowledge message của CLIENT_ACKNOWLEDGE Session không?** Không. Ứng dụng phải quản lý acknowledge và xử lý redelivery theo đúng chế độ.

**8. Nếu dùng @JmsListener trong Spring Boot, nên gọi Connection.stop() trực tiếp không?** Thông thường không; điều khiển lifecycle của listener container do Spring quản lý.

**9. Đâu là khác biệt về start mặc định giữa Connection và JMSContext?** Classic Connection cần start tường minh; JMSContext mặc định auto-start khi tạo consumer, trừ khi setAutoStart(false).

**10. Vì sao stop() có thể làm cả nhiều consumer ngừng nhận?** Vì phạm vi của stop() là toàn Connection, có thể bao gồm nhiều Session và consumer.

### Bài tập mở rộng

- Chạy chương trình ở mục 5 rồi bỏ connection.start() thứ nhất. Giải thích vì sao receive(5000) không thể nhận A dù producer đã gửi.
- Đổi sang hai Session cùng một Connection, mỗi Session tạo một consumer trên các temporary queue riêng; xác minh stop() ảnh hưởng cả hai.
- Đăng ký MessageListener có tác vụ dài trên một Session, từ một thread quản lý khác gọi stop() và đo thời gian nó chờ callback; không gọi stop() trong chính onMessage().
- Thay AUTO_ACKNOWLEDGE bằng SESSION_TRANSACTED; thử commit/rollback trong Session và quan sát redelivery độc lập với start/stop.

## 11. Nguồn chuẩn

- [Jakarta Messaging 3.1 Specification, §6.1.4–6.1.8](https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html): trạng thái Connection, start, stop, close, chờ listener và rollback/ack khi close.
- [Jakarta Messaging 3.1 API: Connection](https://jakarta.ee/specifications/messaging/3.1/apidocs/jakarta.messaging/jakarta/jms/connection): chữ ký và hợp đồng từng phương thức.
- [Apache ActiveMQ Artemis: Docker](https://artemis.apache.org/components/artemis/documentation/latest/docker.html): image chính thức, cổng và tài khoản demo.
- [Spring Framework: JMS reference](https://docs.spring.io/spring-framework/reference/integration/jms.html): JmsTemplate, listener container và quản lý tài nguyên trong Spring.
