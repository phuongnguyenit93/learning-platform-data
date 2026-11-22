# Subscription không bền vững và hành vi khi consumer ngoại tuyến

## 1. Quy tắc cốt lõi: non-durable subscriber chỉ nhận khi subscription còn hoạt động

Trong mô hình **publish/subscribe** của JMS, một **non-durable subscription** (subscription không bền vững) trên **topic** dành cho luồng thông điệp mà ứng dụng chỉ cần nhận khi đang tham gia. Broker không có nghĩa vụ giữ các thông điệp đã xuất bản trong khoảng thời gian subscription đó **không tồn tại** để phát lại cho lần kết nối sau.

Giả sử hệ thống cập nhật vị trí xe theo thời gian thực:

- 10:00:00 — ứng dụng giám sát A mở non-durable subscription vào topic **fleet.positions**.
- 10:00:01 — producer gửi vị trí **P1**; A có thể nhận P1.
- 10:00:02 — A đóng consumer và ngắt kết nối; subscription của A kết thúc.
- 10:00:03 — producer gửi **P2**, nhưng A không còn subscription hoạt động.
- 10:00:04 — A kết nối lại và tạo một **non-durable subscription mới**.
- 10:00:05 — producer gửi **P3**; A có thể nhận P3.

**A không được phát bù P2 chỉ vì đã từng subscribe cùng tên topic.** Đây là hành vi cần nhớ trong phần **Queue và Topic** của module ActiveMQ Classic/Artemis. Tên topic giống nhau qua các lần kết nối không biến non-durable subscription thành subscription có lịch sử.

> **Phạm vi quan trọng:** Quy tắc nói về **subscriber cụ thể**. Nếu B vẫn đang subscribe topic khi P2 được gửi, B vẫn có thể nhận P2. Message không nhất thiết “biến mất khỏi toàn bộ broker”; nó chỉ không được lưu để trả cho A sau khi A đăng ký lại.

~~~mermaid
sequenceDiagram
    autonumber
    participant P as Producer
    participant T as Topic broker
    participant A as Subscriber A
    participant B as Subscriber B

    A->>T: Subscribe non-durable
    B->>T: Subscribe non-durable
    P->>T: Publish P1
    T-->>A: P1
    T-->>B: P1
    A->>T: Close consumer / disconnect
    P->>T: Publish P2
    T-->>B: P2
    Note over A,T: A không có subscription để nhận P2
    A->>T: Subscribe lại (subscription mới)
    P->>T: Publish P3
    T-->>A: P3
    T-->>B: P3
~~~

**Producer gửi thành công không chứng minh mọi consumer từng quan tâm đã nhận message.** Thành công ở phía producer xác nhận thao tác gửi theo hợp đồng JMS/broker; nó không cam kết có subscriber hoạt động hoặc mỗi subscriber đã xử lý nghiệp vụ.

## 2. “Ngoại tuyến” cần được định nghĩa chính xác

Không phải mọi trường hợp ứng dụng **chưa xử lý** message đều đồng nghĩa với non-durable subscription đã kết thúc.

| Trạng thái của ứng dụng A | Subscription còn tồn tại? | Điều gì có thể xảy ra với message mới? |
| --- | --- | --- |
| A chưa từng tạo consumer trên topic | Không | Không có bản sao dành riêng cho A để nhận về sau |
| A tạo consumer và đang nhận bình thường | Có | Message phù hợp có thể được dispatch/đệm cho A |
| A vẫn giữ kết nối và consumer nhưng xử lý chậm | Thường còn | Message có thể chờ trong buffer/queue của subscription, chịu giới hạn tài nguyên và chính sách broker |
| A gọi **consumer.close()**, hoặc đóng session/context/connection | Non-durable subscription tương ứng kết thúc khi broker xử lý việc đóng | Message phát sau thời điểm đó không được giữ cho A |
| Mạng đứt đột ngột nhưng broker chưa phát hiện | Trạng thái chuyển tiếp, chưa chắc chắn | Một số message có thể đang in-flight hoặc được route trước khi broker thu hồi subscription; không được dựa vào chúng để replay |
| A kết nối lại và gọi **createConsumer(topic)** | Một subscription mới | Nhận các message đủ điều kiện kể từ khi subscription mới được thiết lập, không tự nhận lịch sử của subscription cũ |
| Broker restart làm kết nối non-durable cũ mất hiệu lực | Không còn subscription cũ | Client reconnect phải subscribe lại; không có bảo đảm bù message cho khoảng offline |

Các thời điểm **đóng TCP ở client**, **broker phát hiện connection chết**, **consumer được đăng ký ở broker** và **ứng dụng bắt đầu gọi receive()** có thể lệch nhau. Vì thế không nên viết quy tắc đơn giản kiểu “process vừa mất mạng đúng 1 ms thì chắc chắn message P2 bị xóa ngay”. Điều được bảo đảm ở cấp mô hình là: **non-durable subscription không cung cấp cơ chế lưu các message phát trong khoảng subscription không hoạt động để phát bù sau khi tạo lại**.

### Sự khác nhau giữa “chưa xử lý” và “không có subscription”

Khi A đang subscribe nhưng callback xử lý bị nghẽn, broker có thể đang giữ message trong vùng đệm hoặc queue liên kết với subscription. Việc còn subscription hoạt động cho phép message được phân phối và có thể redeliver theo quy tắc acknowledgment. Ngược lại, khi A đóng non-durable consumer, **quyền nhận message của subscription đó kết thúc**; một message mới phát lúc này không nằm trong backlog dành cho A.

Đây cũng là lý do không thể kết luận “topic làm mất message” chỉ từ việc một consumer nhận ít event hơn producer gửi: phải quan sát **thời gian subscription hoạt động**, bộ lọc selector, TTL, kết nối, ack và tình trạng broker.

## 3. Hành vi theo thời điểm publish và số lượng subscriber

Xét topic **orders.events** với hai non-durable subscriber A và B độc lập.

| Thời điểm | A | B | Message publish | Kết quả mong đợi |
| --- | --- | --- | --- | --- |
| t0 | Chưa subscribe | Chưa subscribe | M0 | Không có bản sao lưu cho A/B |
| t1 | Online | Online | M1 | A và B mỗi bên có thể nhận một bản phân phối |
| t2 | Offline, subscription đã kết thúc | Online | M2 | B vẫn nhận; A không được phát bù M2 |
| t3 | Subscribe lại | Online | M3 | A và B nhận được M3 |
| t4 | Offline | Offline | M4 | Không có non-durable subscriber nào để phân phối |
| t5 | A subscribe lại | Offline | Không publish | A không tự nhận M4 |

Trong JMS topic thông thường, hai subscription độc lập là **hai đối tượng nhận**: M1 được phân phối cho cả A lẫn B, không theo kiểu mỗi message chỉ có một người thắng. Một topic cũng có thể có **durable subscriptions** bên cạnh những non-durable subscription; message M2 có thể được giữ cho durable subscriber đã đăng ký trước, dù A bỏ lỡ.

### PERSISTENT không làm non-durable subscription trở nên durable

Đặt producer gửi bằng **DeliveryMode.PERSISTENT** không có nghĩa broker sẽ lưu message cho mọi người có thể subscribe trong tương lai. Delivery mode quy định độ bền của các bản phân phối mà broker **có trách nhiệm giữ** theo kiểu destination và subscription hiện có. Khi không có non-durable subscription của A lúc gửi, không hình thành cam kết lưu một bản sao cho A.

Tương tự, tăng **message TTL**, tăng kích thước journal hoặc bật persistence không tạo ra “lịch sử topic” dành cho non-durable consumer mới. Nếu muốn A bắt kịp message phát lúc ngoại tuyến, cần một thiết kế giữ backlog như **durable subscription** hoặc event store/replay phù hợp.

### Subscription selector ảnh hưởng đến những gì được nhận

Một consumer được tạo với selector, ví dụ **eventType = 'OrderPlaced'**, chỉ được phát các message đáp ứng selector. Message **OrderCancelled** không đến consumer đó ngay cả khi subscription đang hoạt động. Khi điều tra khoảng trống dữ liệu, cần phân biệt **offline**, **selector loại bỏ message**, **TTL hết hạn** và **message đã được dispatch nhưng chưa được xử lý**.

## 4. ActiveMQ Classic và Artemis thực hiện non-durable topic ra sao?

Hai sản phẩm đều có API JMS cho **Topic** và **MessageConsumer**, nhưng cách biểu diễn routing bên trong không hoàn toàn giống nhau.

| Vấn đề | ActiveMQ Classic | ActiveMQ Artemis |
| --- | --- | --- |
| Khái niệm phía Java | **Topic** và non-durable **MessageConsumer** | **Topic** và non-durable **JMSConsumer/MessageConsumer** |
| Đường phân phối | Broker phát message đến subscription/consumer đang hoạt động | Topic JMS thường ánh xạ tới **MULTICAST address** và các **subscription queues** liên kết |
| Khi đăng ký | Consumer trở thành điểm nhận topic | Broker/client tạo liên kết subscription, thường có queue không bền dành cho subscriber |
| Khi đóng subscription | Broker thôi phân phối và không giữ backlog mới cho consumer đó | Subscription queue không bền được giải phóng/xóa theo lifecycle và chính sách tương ứng |
| Khi mở consumer mới | Không tự khôi phục message bỏ lỡ | Một subscription/queue không bền mới được thiết lập; không tự phát lại backlog cũ |
| Cấu hình cần kiểm tra | Chính sách topic, prefetch, advisory, plugin hoặc **retroactive consumer** nếu được bật | Routing type **MULTICAST**, auto-create/auto-delete, quyền tạo queue không bền và policy address |

Trong Artemis, cần phân biệt **address còn tồn tại** với **queue của subscription còn tồn tại**. Address topic có thể tồn tại nhiều năm; điều đó không có nghĩa mọi client đã ngắt kết nối đều có queue bền vững ở phía dưới. Ngay cả khi queue không bền còn hiển thị ngắn hạn do chính sách xóa trễ, **không được dựa vào nó** để bảo đảm lịch sử cho lần subscribe mới.

### Cấu hình routing Artemis minh họa

Nếu broker Artemis không cho tự tạo address, administrator có thể khai báo **MULTICAST address** trong phần **addresses** của **broker.xml**:

~~~xml
<address name="lab.events.nonDurable">
    <multicast/>
</address>
~~~

Đây là **đoạn bên trong cấu hình addresses hiện có**, không phải file broker.xml độc lập. **Không tạo một queue cố định duy nhất** dưới address rồi coi nó là non-durable subscription của mọi client: một queue cố định có thể biến các consumer thành nhóm tranh nhau message hoặc vô tình giữ backlog với lifecycle khác JMS topic.

Nếu broker dùng phân quyền theo role, một chính sách minh họa trong **security-settings** có thể cấp cho ứng dụng quyền publish và tạo/tiêu thụ subscription queue không bền:

~~~xml
<security-setting match="lab.events.nonDurable">
    <permission type="send" roles="topic_publisher"/>
    <permission type="consume" roles="topic_subscriber"/>
    <permission type="createNonDurableQueue" roles="topic_subscriber"/>
    <permission type="deleteNonDurableQueue" roles="topic_subscriber"/>
</security-setting>
~~~

Các **role** phải thực sự được gắn với người dùng ở cấu hình security của instance. Phải ghép các đoạn XML vào đúng phần tử hiện có, xét thêm các security-setting có thể đang áp dụng và kiểm tra cấu hình trên release triển khai. Nếu bạn chỉ thử broker local theo cấu hình auto-create mặc định, không nhất thiết phải sửa broker.xml.

**ActiveMQ Classic** có các cơ chế mở rộng như **retroactive consumer** và recovery policy cho phép subscriber mới nhận một số thông điệp trước đó trong những cấu hình đặc biệt. Đây **không phải hành vi JMS non-durable mặc định**. Khi quan sát message cũ xuất hiện sau reconnect, cần kiểm tra đã bật tính năng này, plugin hoặc retained/replay riêng chưa; không dùng kết quả một broker cấu hình đặc biệt làm kỳ vọng chung cho toàn bộ ActiveMQ.

## 5. Thí nghiệm Java/JMS: hai subscriber, một bên ngoại tuyến

Thí nghiệm sau trên **ActiveMQ Artemis** dùng **Jakarta Messaging (jakarta.jms)**. Một producer gửi bốn message **M1–M4**:

- M1: A và B đang online, **cả hai nhận**.
- M2: A đã đóng consumer, B vẫn online, **chỉ B nhận**.
- A subscribe lại: gọi **receive** trước khi gửi tiếp để xác nhận **không nhận bù M2**.
- M3: A và B online, **cả hai nhận**.
- M4: cả A và B đã đóng consumer; một subscriber mới tạo sau đó **không được nhận bù M4**.

Để tránh nhận nhầm message của lần chạy khác trên cùng topic, mẫu đặt property **labRun** là UUID cho mọi message và sử dụng JMS selector tương ứng. Mẫu dùng **PERSISTENT** cố ý, nhằm chứng minh rằng delivery mode này vẫn không làm phát sinh backlog cho non-durable consumer ngoại tuyến.

### Chuẩn bị

Cần JDK 17+, Maven và broker Artemis đang sẵn sàng. Trong ví dụ:

- **BROKER_URL** là URL đến cổng JMS của Artemis, mặc định **tcp://127.0.0.1:61616** nếu chạy một broker đơn lẻ.
- Nếu chạy lab song song Classic và Artemis với Artemis được publish lên cổng host **61617**, đặt **BROKER_URL=tcp://127.0.0.1:61617**.
- **BROKER_USER**, **BROKER_PASSWORD** là credential thực tế của Artemis; user phải có quyền **send**, **consume** và tạo non-durable subscription queue khi broker hạn chế quyền.
- Topic tên **lab.events.nonDurable**; nếu broker tắt tự tạo address, cấu hình MULTICAST như mục 4.

Ví dụ Maven **pom.xml** tối thiểu (phiên bản chỉ để tái hiện mã mẫu; trong dự án cần đối chiếu compatibility của broker/client ở release sử dụng):

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>lab.messaging</groupId>
    <artifactId>topic-nondurable-lab</artifactId>
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

Tạo **src/main/java/NonDurableTopicLab.java**:

~~~java
import jakarta.jms.DeliveryMode;
import jakarta.jms.JMSConsumer;
import jakarta.jms.JMSContext;
import jakarta.jms.JMSException;
import jakarta.jms.Message;
import jakarta.jms.TextMessage;
import jakarta.jms.Topic;
import org.apache.activemq.artemis.jms.client.ActiveMQConnectionFactory;

import java.util.Objects;
import java.util.UUID;

public final class NonDurableTopicLab {

    public static void main(String[] args) throws Exception {
        String brokerUrl = System.getenv().getOrDefault(
                "BROKER_URL", "tcp://127.0.0.1:61616");
        String user = Objects.requireNonNull(
                System.getenv("BROKER_USER"), "Missing BROKER_USER");
        String password = Objects.requireNonNull(
                System.getenv("BROKER_PASSWORD"), "Missing BROKER_PASSWORD");

        String runId = UUID.randomUUID().toString();
        // UUID chỉ có chữ số, chữ và dấu gạch nối: an toàn trong literal selector này.
        String selector = "labRun = '" + runId + "'";

        ActiveMQConnectionFactory factory =
                new ActiveMQConnectionFactory(brokerUrl);

        try (JMSContext publisher = factory.createContext(
                user, password, JMSContext.AUTO_ACKNOWLEDGE)) {
            Topic topic = publisher.createTopic("lab.events.nonDurable");

            // B online xuyên suốt M1, M2 và M3.
            try (JMSContext subscriberB = factory.createContext(
                    user, password, JMSContext.AUTO_ACKNOWLEDGE)) {
                JMSConsumer b = subscriberB.createConsumer(topic, selector);

                // A online khi M1 xuất hiện.
                try (JMSContext subscriberA1 = factory.createContext(
                        user, password, JMSContext.AUTO_ACKNOWLEDGE)) {
                    JMSConsumer a1 =
                            subscriberA1.createConsumer(topic, selector);

                    publish(publisher, topic, runId, "M1");
                    expect(a1, "M1", "A");
                    expect(b, "M1", "B");
                } // Đóng A1: non-durable subscription của A kết thúc.

                // A offline. B vẫn có subscription đang hoạt động.
                publish(publisher, topic, runId, "M2");
                expect(b, "M2", "B");

                // Tạo lại consumer A => subscription mới.
                try (JMSContext subscriberA2 = factory.createContext(
                        user, password, JMSContext.AUTO_ACKNOWLEDGE)) {
                    JMSConsumer a2 =
                            subscriberA2.createConsumer(topic, selector);
                    expectNone(a2, "M2", "A reconnect");

                    publish(publisher, topic, runId, "M3");
                    expect(a2, "M3", "A reconnect");
                    expect(b, "M3", "B");
                }
            } // Lúc này A và B đều offline.

            // Không có subscription nào thuộc lượt chạy này đang hoạt động.
            publish(publisher, topic, runId, "M4");

            try (JMSContext subscriberA3 = factory.createContext(
                    user, password, JMSContext.AUTO_ACKNOWLEDGE)) {
                JMSConsumer a3 =
                        subscriberA3.createConsumer(topic, selector);
                expectNone(a3, "M4", "A after both offline");
            }
        }

        System.out.println("PASS: non-durable subscription không phát bù"
                + " message trong khoảng offline");
    }

    private static void publish(
            JMSContext publisher, Topic topic, String runId, String payload)
            throws JMSException {
        TextMessage message = publisher.createTextMessage(payload);
        message.setStringProperty("labRun", runId);
        publisher.createProducer()
                .setDeliveryMode(DeliveryMode.PERSISTENT)
                .send(topic, message);
        System.out.println("PUBLISH " + payload);
    }

    private static void expect(
            JMSConsumer consumer, String expected, String subscriber)
            throws JMSException {
        Message message = consumer.receive(5000);
        if (!(message instanceof TextMessage)) {
            throw new IllegalStateException(
                    subscriber + " did not receive " + expected);
        }
        String actual = ((TextMessage) message).getText();
        if (!expected.equals(actual)) {
            throw new IllegalStateException(
                    subscriber + " expected " + expected + " but got " + actual);
        }
        System.out.println(subscriber + " RECEIVED " + actual);
    }

    private static void expectNone(
            JMSConsumer consumer, String missed, String subscriber) {
        Message unexpected = consumer.receive(1500);
        if (unexpected != null) {
            throw new IllegalStateException(
                    subscriber + " unexpectedly received a message"
                    + " after reconnect; expected to miss " + missed);
        }
        System.out.println(subscriber + " MISSED " + missed + " (expected)");
    }
}
~~~

Cách chạy trên **PowerShell**, với password do bạn đã đặt trên broker:

~~~powershell
$env:BROKER_URL = "tcp://127.0.0.1:61617"
$env:BROKER_USER = "artemis_app"
$env:BROKER_PASSWORD = "<your-artemis-password>"

mvn -q compile exec:java "-Dexec.mainClass=NonDurableTopicLab"
~~~

Nếu Artemis chạy trên cổng host 61616 thì sửa **BROKER_URL** tương ứng. Trong PowerShell, đừng sao chép literal **<your-artemis-password>** làm mật khẩu thật. Khi chạy Maven với lệnh trên, terminal Java dùng chính environment variables của terminal đó; Docker Compose **.env** không tự động nạp chúng vào tiến trình Maven.

### Đọc kết quả

Đầu ra hợp lệ (thứ tự các dòng **PUBLISH/RECEIVED** theo luồng chương trình):

~~~text
PUBLISH M1
A RECEIVED M1
B RECEIVED M1
PUBLISH M2
B RECEIVED M2
A reconnect MISSED M2 (expected)
PUBLISH M3
A reconnect RECEIVED M3
B RECEIVED M3
PUBLISH M4
A after both offline MISSED M4 (expected)
PASS: non-durable subscription không phát bù message trong khoảng offline
~~~

Nếu **A reconnect** nhận M2, đừng lập tức kết luận tiêu chuẩn JMS tự lưu cho non-durable subscriber. Hãy kiểm tra có sử dụng nhầm **durable subscription**, plugin **retroactive/recovery**, subscription queue được cấu hình bền vững, selector/endpoint sai hoặc còn phiên subscriber cũ chưa thực sự đóng hay không. Nếu A không nhận được M1/M3 dù đang online, xem quyền tạo subscription queue, routing **MULTICAST**, selector, trạng thái connection và broker logs.

Bài thử dùng **AUTO_ACKNOWLEDGE** và **receive() đồng bộ**, vì trọng tâm là **subscription hiện diện tại thời điểm publish**. Nó không giả lập transaction database hay đảm bảo end-to-end exactly-once.

## 6. Áp dụng cùng hành vi với ActiveMQ Classic

ActiveMQ Classic hỗ trợ cùng mô hình JMS non-durable topic, nhưng client API/package có thể khác Artemis. Với dòng client Classic sử dụng **javax.jms**, cách tạo consumer non-durable là **Session.createConsumer(topic)** hoặc **Session.createConsumer(topic, selector)**, không cần đăng ký **clientID + durable subscription name**.

Ví dụ rút gọn phía Classic:

~~~java
import javax.jms.Connection;
import javax.jms.DeliveryMode;
import javax.jms.MessageConsumer;
import javax.jms.MessageProducer;
import javax.jms.Session;
import javax.jms.TextMessage;
import javax.jms.Topic;
import org.apache.activemq.ActiveMQConnectionFactory;

// Đặt đoạn này trong phương thức throws Exception.
// user/password/url lấy từ cấu hình ứng dụng, không hardcode.
ActiveMQConnectionFactory factory =
        new ActiveMQConnectionFactory("tcp://127.0.0.1:61616");
Connection publisherConnection = factory.createConnection(user, password);
Connection subscriberConnection = factory.createConnection(user, password);

try {
    Session publisherSession = publisherConnection.createSession(
            false, Session.AUTO_ACKNOWLEDGE);
    Session subscriberSession = subscriberConnection.createSession(
            false, Session.AUTO_ACKNOWLEDGE);

    Topic topic = publisherSession.createTopic("lab.events.nonDurable");
    MessageProducer producer = publisherSession.createProducer(topic);
    producer.setDeliveryMode(DeliveryMode.PERSISTENT);

    MessageConsumer subscriber = subscriberSession.createConsumer(topic);
    subscriberConnection.start();
    publisherConnection.start();

    producer.send(publisherSession.createTextMessage("ONLINE"));
    TextMessage online = (TextMessage) subscriber.receive(5000);
    if (online == null) {
        throw new IllegalStateException("Expected ONLINE");
    }
    System.out.println("Received: " + online.getText());

    subscriber.close(); // Kết thúc non-durable subscription hiện tại.
    producer.send(publisherSession.createTextMessage("OFFLINE"));

    MessageConsumer freshSubscriber = subscriberSession.createConsumer(topic);
    if (freshSubscriber.receive(1500) != null) {
        throw new IllegalStateException("Unexpected offline replay");
    }
    producer.send(publisherSession.createTextMessage("AFTER_RECONNECT"));
    TextMessage after = (TextMessage) freshSubscriber.receive(5000);
    if (after == null) {
        throw new IllegalStateException("Expected AFTER_RECONNECT");
    }
    System.out.println("Received: " + after.getText());

    freshSubscriber.close();
    producer.close();
    subscriberSession.close();
    publisherSession.close();
} finally {
    subscriberConnection.close();
    publisherConnection.close();
}
~~~

Sử dụng dependency **org.apache.activemq:activemq-client** tương thích với dòng Classic đang chạy. Đây là **đoạn logic mẫu** đặt trong phương thức Java có biến **user/password** và xử lý exception thích hợp; ví dụ Artemis ở mục 5 là chương trình chạy độc lập đầy đủ. Không trộn package **javax.jms** của ví dụ Classic với **jakarta.jms** của Artemis vào cùng file Java. Một số dòng/release Classic có biến thể client và mức hỗ trợ JMS API khác nhau; cần chọn dependency theo release thực tế.

Điểm giống nhau không nằm ở tên lớp factory mà ở hành vi: **createConsumer** tạo non-durable subscription đang hoạt động; **close** kết thúc nó; **createConsumer** một lần nữa không đòi broker trả lại message publish ở khoảng trống.

## 7. Điều gì xảy ra với message đã được dispatch nhưng chưa ACK?

Không nên trộn hai câu hỏi:

1. **Broker có subscription đang hoạt động để định tuyến message lúc publish không?**
2. **Message đã được định tuyến đó được ACK/commit thành công chưa?**

Câu đầu quyết định liệu message có khả năng được giao đến A theo subscription hiện tại. Câu sau quyết định việc broker có thể redeliver một message đã giao **khi subscription và phiên xử lý còn phù hợp**.

Ví dụ, A tạo non-durable consumer và nhận P1 bằng **SESSION_TRANSACTED**:

~~~java
try (JMSContext context = factory.createContext(
        user, password, JMSContext.SESSION_TRANSACTED)) {
    Topic topic = context.createTopic("lab.events.nonDurable");
    JMSConsumer consumer = context.createConsumer(topic);

    Message message = consumer.receive(5000);
    if (message != null) {
        try {
            handleBusinessLogic(message); // Hàm của ứng dụng
            context.commit();             // ACK các receive trong transaction JMS
        } catch (Exception error) {
            context.rollback();           // Có thể được redeliver theo policy
            throw error;
        }
    }
}
~~~

Đoạn này minh họa **thứ tự xử lý/commit**, giả sử **factory**, **user**, **password** và **handleBusinessLogic** đã được cung cấp. Nếu rollback khi consumer/session vẫn đang hoạt động, message có thể được giao lại theo policy. Nhưng nếu client hoặc broker làm kết thúc **toàn bộ non-durable subscription**, ứng dụng không được giả định message chưa ACK sẽ tồn tại để cấp lại sau khi tạo subscription khác. Đây là một ranh giới độ tin cậy quan trọng: non-durable phù hợp với dữ liệu có thể bỏ qua, không phù hợp với nghiệp vụ buộc xử lý đủ mọi event.

### Các trường hợp thường bị nhầm

- **AUTO_ACKNOWLEDGE:** nếu listener xử lý xong và trả bình thường hoặc lời gọi receive đồng bộ hoàn tất theo quy tắc JMS, provider có thể coi message đã được ACK; đừng đẩy side effect sang thread nền rồi trả callback quá sớm.
- **CLIENT_ACKNOWLEDGE:** ứng dụng gọi **acknowledge()**; trong JMS, lời gọi này có thể ACK toàn bộ message đã tiêu thụ trong cùng session. Nó **không** làm subscriber thành durable.
- **SESSION_TRANSACTED:** **commit()** xác nhận các receive trong transaction; **rollback()** cho phép redelivery khi còn subscription phù hợp. JMS transaction không tự bao trùm database riêng.
- **JMSRedelivered/JMSXDeliveryCount:** giúp xem delivery lặp khi provider hỗ trợ nhưng không phải bằng chứng broker sẽ giữ thông điệp qua lúc non-durable subscription đã chấm dứt.
- **DLQ:** một message được giao rồi thất bại nhiều lần có thể chịu redelivery/DLQ policy; message bị bỏ lỡ vì **không có non-durable subscription tại lúc publish** thường không thể “lấy lại từ DLQ” chỉ bằng việc reconnect.

## 8. Một subscriber offline khác với tất cả subscriber offline

Nếu hai consumer A và B subscribe cùng topic bằng **hai non-durable subscriptions độc lập**, mỗi consumer có một đường nhận của riêng mình. B vẫn online có thể nhận message M2 khi A offline. Sau khi A quay lại, A không được hưởng backlog của B.

~~~mermaid
flowchart TD
    P[Producer publish M2] --> T[Topic]
    T --> SA{Subscription A đang hoạt động?}
    T --> SB{Subscription B đang hoạt động?}
    SA -- Không --> MISS[A bỏ lỡ M2]
    SB -- Có --> DELIVER[B nhận M2]
    MISS --> NEW[A subscribe lại]
    NEW --> FUTURE[A chỉ nhận message mới phù hợp]
~~~

### Shared non-durable subscription là trường hợp khác

JMS có khái niệm **shared non-durable subscription**: nhiều consumer cùng chia sẻ **một subscription logic** thay vì mỗi consumer có bản phân phối riêng. Khi đó:

- Nếu A đóng nhưng **B vẫn đang tiêu thụ cùng shared subscription**, subscription vẫn còn hoạt động; message có thể tiếp tục được phân phối qua B.
- Nếu **consumer cuối cùng** của shared non-durable subscription đóng và subscription kết thúc, message phát sau đó không được tích lũy để phát bù lần kết nối mới.
- Các consumer chia sẻ một subscription thường **chia công việc** trong subscription đó; không phải mọi consumer đều nhận một bản sao của mỗi message.

Trên Classic và Artemis, **khả năng hỗ trợ và API shared subscription phụ thuộc phiên bản JMS/client và broker**. Khi học hành vi offline, phải xác định bạn đang dùng **mỗi client một subscription riêng** hay **nhiều client chia sẻ một subscription**, nếu không phép đo số lượng message nhận sẽ gây hiểu nhầm.

## 9. Khi nào phải chuyển sang durable subscription hoặc thiết kế khác?

**Non-durable** phù hợp khi giá trị của thông điệp giảm nhanh và ứng dụng có thể hoạt động đúng dù bỏ lỡ một số bản cập nhật, ví dụ màn hình thống kê trực tiếp, trạng thái online, thay đổi vị trí gửi liên tục. Khi reconnect, ứng dụng có thể gọi API lấy **snapshot mới nhất** rồi tiếp tục nhận live events.

Nếu mọi event phải được xử lý, lựa chọn sẽ khác:

| Nhu cầu | Non-durable topic | Lựa chọn phù hợp hơn |
| --- | --- | --- |
| Chỉ cần cập nhật trực tiếp, bỏ lỡ trong lúc offline được | Phù hợp | Giữ non-durable + nạp snapshot lúc reconnect |
| Mỗi dịch vụ cần nhận đầy đủ event kể cả khi ngừng bảo trì | Không phù hợp | **Durable topic subscription** có định danh ổn định |
| Một công việc chỉ giao cho một worker trong nhóm | Không phải mô hình thích hợp | **Queue** với competing consumers |
| Cần phát lại từ ngày/offset tùy ý hoặc tái dựng state | Không đáp ứng | Event log/event store có retention và replay |
| Cần mỗi dịch vụ xử lý đủ và không lặp side effect | Không đủ | Durable subscription/queue + idempotency tại database |
| Chỉ cần trạng thái hiện tại sau khi reconnect | Có thể dùng | Snapshot từ nguồn sự thật + non-durable live updates |

Một **durable subscription** được đăng ký đúng theo JMS có thể giữ những message publish lúc subscriber tạm ngừng kết nối, phụ thuộc TTL, storage, quota, broker policy và điều kiện subscription tồn tại. Nhưng **durable** vẫn không đồng nghĩa exactly-once business processing: consumer phải xử lý redelivery, transaction và idempotency.

Ví dụ so sánh ngắn với **Jakarta JMS**: khi cần durable, ứng dụng tạo **durable consumer** có tên subscription ổn định (và client identity phù hợp với quy tắc JMS/provider), chứ không chỉ gọi lại **createConsumer(topic)**:

~~~java
JMSContext context = factory.createContext(
        user, password, JMSContext.AUTO_ACKNOWLEDGE);
context.setClientID("inventory-service-01"); // Trước khi tạo consumer/start
Topic topic = context.createTopic("orders.events");
JMSConsumer consumer =
        context.createDurableConsumer(topic, "inventory-orders-v1");
~~~

Đây là **đoạn minh họa API**, chưa phải mã đầy đủ cho vòng đời durable subscription. Cần quản lý ổn định **clientID**, **subscriptionName**, quyền tạo durable queue và lifecycle unsubscribe theo đúng broker; với durable subscription không chia sẻ, không cho nhiều client đồng thời dùng cùng định danh theo cách xung đột. Non-durable thì không lưu lại một định danh như vậy chỉ bằng việc dùng chung tên topic.

### Thiết kế “snapshot + live” tránh khoảng trống khi khởi động

Nếu ứng dụng cần **trạng thái hiện tại** rồi theo dõi live updates, hãy định nghĩa rõ race giữa lúc lấy snapshot và lúc subscribe:

1. Đăng ký live subscription.
2. Lấy snapshot có **version/timestamp** từ nguồn dữ liệu chuẩn.
3. Áp dụng các event có version mới hơn snapshot theo cơ chế buffer/reconcile.
4. Nếu phát hiện thiếu version hoặc mất kết nối, lấy snapshot lại.

Đơn thuần **lấy snapshot trước rồi mới subscribe** có thể bỏ lỡ một cập nhật xảy ra giữa hai thao tác. Ngược lại, subscribe rồi lấy snapshot nhưng không có version/reconcile có thể áp dụng event cũ đè lên snapshot mới. Với dữ liệu quan trọng yêu cầu mọi thay đổi, durable subscription hoặc log có offset vẫn là thiết kế dễ kiểm chứng hơn.

## 10. Chẩn đoán hiện tượng “producer gửi 100 message, consumer nhận 73”

Một log kiểu **producer sent=100** và **subscriber received=73** chưa đủ để suy ra ActiveMQ lỗi. Kiểm tra theo trình tự:

1. **Khoảng online thực tế:** thời điểm consumer/connection được broker đăng ký, thời điểm đóng, restart và khoảng mất mạng.
2. **Loại subscription:** non-durable, durable, shared non-durable hay queue; kiểm tra cả số consumer cùng nhận.
3. **Destination và selector:** cùng topic/address/routing type không, selector loại bỏ bao nhiêu message, publisher có gửi sai topic không?
4. **Cách ACK và lỗi callback:** message đang in-flight, rollback/recovery, listener ném exception hoặc đóng context quá sớm?
5. **TTL/expiration:** message có hết hạn trước khi được dispatch/nhận không?
6. **Policy đặc biệt:** Artemis auto-create/auto-delete, Classic retroactive/recovery, quota, paging/prefetch, broker restart.
7. **Chứng cứ theo từng eventId:** producer log eventId, timestamp, JMS destination; subscriber log eventId khi nhận và sau khi xử lý hoàn tất.

| Triệu chứng | Diễn giải có khả năng | Hướng kiểm tra |
| --- | --- | --- |
| Consumer khởi động sau producer và không nhận message cũ | Đúng hành vi non-durable | Gửi event mới sau khi consumer đã subscribe |
| B nhận M2, A offline không nhận; A reconnect vẫn thiếu M2 | Đúng hành vi subscription độc lập | Xác nhận A đã đóng subscription trước M2 |
| A vẫn ở trạng thái “online” nhưng không gọi receive() | Có thể là nghẽn xử lý hoặc prefetch, chưa chắc offline | Xem connection, subscription queue, in-flight và exception |
| Sau reconnect xuất hiện message cũ | Có thể đang dùng durable, shared subscription còn consumer, retroactive/recovery hoặc phiên cũ chưa kết thúc | Kiểm tra subscription type và config |
| Producer dùng PERSISTENT mà subscriber vẫn mất event | PERSISTENT không tạo offline backlog cho non-durable | Đối chiếu timeline publish/subscribe |
| Queue size broker bằng 0 nhưng ứng dụng thiếu sự kiện | Không có backlog dành cho non-durable offline | Đối soát eventId với event store/outbox, không suy từ queue size |
| Chỉ một số loại event mất | Selector, routing hoặc schema filter | So sánh properties, selector và topic thực tế |

**Quan sát broker:** ActiveMQ Artemis có thể thể hiện MULTICAST address và các subscription queues; ActiveMQ Classic có thống kê topic/consumer. Các metric quan trọng là **active consumer/subscription count**, **enqueue/dispatch**, **in-flight**, **redelivery**, **expiry** và trạng thái kết nối. Mỗi release expose tên metric khác nhau. Đặc biệt, **queue depth = 0** ở một non-durable subscription đã bị hủy không nói lên rằng mọi message trước đó đã được consumer xử lý.

### Giới hạn của DLQ khi subscriber không tồn tại

DLQ thường phục vụ message **đã có đường phân phối nhưng liên tục không xử lý được** (tùy policy), chứ không phải kho lưu mặc định của mọi event publish vào topic khi không ai subscribe. Nếu không có durable subscription hoặc một consumer/archive service nhận event, thường không có bản sao dành cho A để tìm trong DLQ. Muốn replay cần **nguồn lịch sử độc lập** hoặc đăng ký bền vững từ trước thời điểm event phát sinh.

## 11. Bài thực hành mở rộng và câu hỏi kiểm chứng

### Thực hành A — Đảo thứ tự khởi động

Chạy publisher trước khi tạo consumer, publish **BEFORE_SUBSCRIBE**, rồi tạo non-durable consumer. Kiểm tra receive timeout. Publish tiếp **AFTER_SUBSCRIBE** khi consumer đã mở; xác minh chỉ nhận event sau. Lặp lại với **DeliveryMode.PERSISTENT** và **NON_PERSISTENT** để giải thích vì sao delivery mode không tạo offline backlog trong cả hai trường hợp.

### Thực hành B — Bảo đảm “chỉ một A offline”

Giữ B online, đóng A, phát 10 event và đếm số event B nhận. Mở lại A rồi phát 3 event mới; xác minh A chỉ nhận 3 event sau khi subscribe lại. Tránh dùng hai consumer **shared** trong bài này, vì mục tiêu là so sánh **hai subscriptions độc lập**.

### Thực hành C — Phân biệt offline với xử lý chậm

Giữ consumer kết nối và subscription hoạt động, làm callback xử lý chậm có kiểm soát. Quan sát số message đang chờ/in-flight (nếu broker expose). Sau đó đóng subscription hoàn toàn và publish các event mới. Giải thích vì sao hai trạng thái có hậu quả khác nhau. Không chạy test vô hạn khiến broker đầy memory/disk.

### Thực hành D — Chọn đúng cơ chế cho nghiệp vụ

Một hệ thống có ba consumer: dashboard nhiệt độ (mất bản đo cũ được), dịch vụ xuất hóa đơn (không được bỏ lỡ), và bộ tổng hợp báo cáo ngày (cần replay quá khứ). Hãy chọn riêng cho từng consumer giữa **non-durable topic**, **durable topic subscription**, **queue** hoặc **event log**; giải thích retention, khôi phục khi offline và xử lý trùng.

### Các kết luận cần tự chứng minh

- **Một non-durable subscription không giữ các message được xuất bản khi subscription đó không hoạt động.**
- **Hai non-durable subscriptions độc lập cùng online có thể nhận cùng một event topic; một subscriber offline không ngăn subscriber kia nhận.**
- **PERSISTENT, TTL dài hoặc một topic address tồn tại sẵn không tự cấp lịch sử cho subscriber mới.**
- **ACK, rollback và redelivery là vấn đề của message đã có subscription để giao; chúng không thay thế durable subscription.**
- **Nếu bỏ lỡ event là không chấp nhận được, cần thiết kế giữ backlog hoặc replay được và xử lý side effect idempotent.**

Bài học trọng tâm là xác định **subscription có tồn tại tại thời điểm publish hay không**. Từ ranh giới đó, bạn có thể dự đoán chính xác hành vi khi consumer ngắt kết nối, lựa chọn giữa non-durable và durable, và tránh coi một lần gửi JMS thành công là bảo đảm mọi subscriber đã nhận đầy đủ.
