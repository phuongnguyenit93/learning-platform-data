# Advisory message và theo dõi thay đổi trên broker

> **Chương:** Định tuyến Classic  
> **Phạm vi:** Apache ActiveMQ **Classic 5.x** trong học phần `INTEGRATION_MESSAGING_MESSAGE_BROKER_ACTIVEMQ` — giao tiếp bất đồng bộ bằng queue/topic, JMS, định tuyến, acknowledgment, transaction, redelivery, DLQ, bảo mật và giám sát broker. Bài này tập trung vào **advisory message** của Classic; tên topic, kiểu payload và XML dưới đây không được áp dụng nguyên xi cho ActiveMQ Artemis.

## 1. Vấn đề: biết lúc nào topology và hành vi broker thay đổi

Một dịch vụ Java gửi yêu cầu vào queue `orders.created`; một nhóm worker nhận và xử lý. Khi triển khai phiên bản worker mới, hệ thống giám sát muốn trả lời:

- Có bao nhiêu consumer thực sự kết nối tới queue này? Consumer nào vừa đến hoặc vừa rời đi?
- Producer nào vừa kết nối hoặc ngắt? Broker có vừa được tạo một destination mới?
- Có dấu hiệu slow consumer, producer bị chặn vì tài nguyên, hoặc message hết hạn không?
- Thông tin biến động tức thời này khác gì các con số được đọc qua JMX?

ActiveMQ Classic có cơ chế **advisory message**: broker **phát thông điệp quản trị** lên những topic đặc biệt khi các sự kiện thích hợp xảy ra. Ứng dụng giám sát có thể tạo JMS consumer để nhận các thông điệp này giống cách đăng ký topic JMS thông thường.

Ví dụ một consumer bắt đầu nhận trên queue `orders.created`:

~~~text
Order worker --createConsumer("orders.created")--> ActiveMQ Classic
                                                   |
                                                   | broker phát thông điệp advisory
                                                   v
                          ActiveMQ.Advisory.Consumer.Queue.orders.created
                                                   |
                                                   v
                                        Monitoring JMS subscriber
                                                   |
                                                   v
                               Log thay đổi / cập nhật view / phát cảnh báo
~~~

**Điểm phân biệt căn bản:** advisory là **thông báo về hoạt động và trạng thái broker**; nó không phải đơn hàng, không phải nghiệp vụ của queue `orders.created`, cũng không phải bản ghi audit bền vững mặc định. Consumer của advisory topic **không** lấy message nghiệp vụ ra khỏi `orders.created`.

### Kết quả mong đợi sau bài

Bạn có thể:

1. Xác định đúng advisory topic cho một loại sự kiện của **Classic**, phân biệt advisory liên quan connection, destination, consumer, producer và tình trạng message/consumer.
2. Viết một JMS listener Java đọc payload đặc thù `ConsumerInfo`, `RemoveInfo`, `ProducerInfo`, `DestinationInfo` và `ConnectionInfo` khi có.
3. Tạo một consumer/producer thử nghiệm và quan sát các advisory tương ứng; hiểu vì sao một số sự kiện có thể chưa xuất hiện.
4. Bật/tắt và cấu hình **chọn lọc** advisory trong `activemq.xml` theo broker/destination policy.
5. Kết hợp advisory với **JMX/metrics/log** để vận hành đáng tin cậy mà không nhầm sự kiện tức thời với nguồn sự thật lâu dài.

## 2. Cơ chế advisory của ActiveMQ Classic

Trong Classic, broker có thể phát advisory lên các **topic thuộc namespace `ActiveMQ.Advisory.`**. Người nghe sử dụng JMS `Topic`, mặc dù đối tượng được quan sát có thể là một **queue**.

Luồng khi worker kết nối:

1. Java worker tạo connection/session, sau đó `createConsumer(queue)`.
2. Broker đăng ký consumer và phát advisory về việc consumer xuất hiện, nếu tính năng tương ứng được bật.
3. Advisory được gửi đến topic chuyên biệt, ví dụ `ActiveMQ.Advisory.Consumer.Queue.orders.created`.
4. JMS subscriber nhận message và đọc phần **broker command/data structure**, thay vì giả định message là `TextMessage` hay JSON.
5. Khi consumer được đóng hoặc kết nối rơi, broker có thể phát advisory mang thông tin **remove**.

Loại message mà listener nhận thường là `org.apache.activemq.command.ActiveMQMessage`; thông tin sự kiện nằm trong `getDataStructure()`, chẳng hạn:

- `ConsumerInfo`: có consumer mới được thêm.
- `ProducerInfo`: có producer mới được thêm.
- `ConnectionInfo`: có connection mới được thêm.
- `DestinationInfo`: destination được thêm/xóa.
- `RemoveInfo`: broker thông báo một đối tượng tương ứng đã bị xóa/đóng; cần xem **topic** đã đăng ký và **object ID** để biết loại đối tượng.

Đây là **API/kiểu command của ActiveMQ Classic**, không phải payload được JMS chuẩn hóa. Một JMS provider khác hoặc một nhánh Artemis không bắt buộc sinh các lớp này.

### 2.1. Topic hệ thống và destination nghiệp vụ

| Vai trò | Ví dụ | Điểm cần nhớ |
|---|---|---|
| Queue nghiệp vụ | `orders.created` | Worker nhận message công việc từ queue |
| Advisory về consumer của queue | `ActiveMQ.Advisory.Consumer.Queue.orders.created` | Subscriber theo dõi consumer được thêm/bớt của queue |
| Advisory về producer của queue | `ActiveMQ.Advisory.Producer.Queue.orders.created` | Subscriber theo dõi producer được thêm/bớt |
| Advisory về connection | `ActiveMQ.Advisory.Connection` | Thông báo kết nối được tạo/loại bỏ, không riêng queue nào |
| Advisory destination dạng queue | `ActiveMQ.Advisory.Queue` | Thông báo tạo/xóa queue |
| Advisory destination dạng topic | `ActiveMQ.Advisory.Topic` | Thông báo tạo/xóa topic |

Một queue mang tên `orders.created` và topic advisory kết thúc bằng `orders.created` là **hai đích khác nhau**. Nếu subscribe nhầm `orders.created` như một topic nghiệp vụ, bạn sẽ không nhận được sự kiện thêm/bớt consumer của queue.

### 2.2. Các nhóm advisory thường gặp

| Loại biến động | Topic Classic thường gặp / cách chọn | Điều có thể suy ra |
|---|---|---|
| Connection được tạo/xóa | `ActiveMQ.Advisory.Connection` | Có thay đổi kết nối tại broker |
| Consumer được thêm/xóa | `ActiveMQ.Advisory.Consumer.Queue.<queue>` hoặc `.Topic.<topic>` | Consumer của destination thay đổi |
| Producer được thêm/xóa | `ActiveMQ.Advisory.Producer.Queue.<queue>` hoặc `.Topic.<topic>` | Producer của destination thay đổi |
| Queue/topic tạo/xóa | `ActiveMQ.Advisory.Queue`, `ActiveMQ.Advisory.Topic` | Danh sách destination thay đổi |
| Temporary destination | `ActiveMQ.Advisory.TempQueue`, `ActiveMQ.Advisory.TempTopic` | Temporary queue/topic được tạo hoặc xóa |
| Slow consumer | `AdvisorySupport.getSlowConsumerAdvisoryTopic(destination)` | Broker phát hiện trường hợp thỏa điều kiện phát advisory theo policy/strategy |
| Fast producer | `AdvisorySupport.getFastProducerAdvisoryTopic(destination)` | Producer bị xem là gây áp lực theo tiêu chí broker |
| Message delivered/consumed | Các topic do `AdvisorySupport.getMessageDeliveredAdvisoryTopic(...)`, `getMessageConsumedAdvisoryTopic(...)` trả về | Sự kiện mức message, có thể rất nhiều |
| Message expired / discarded / không có consumer | Các phương thức `AdvisorySupport` tương ứng, tùy loại policy | Sự kiện cụ thể khi broker kích hoạt chính sách |

`<queue>` và `<topic>` là **chỗ điền tên destination**, không phải ký tự cần gõ vào JMS topic. Ví dụ tên queue là `orders.created` thì advisory consumer là `ActiveMQ.Advisory.Consumer.Queue.orders.created`.

Với các advisory về tình trạng đặc biệt, **nên dùng lớp `org.apache.activemq.advisory.AdvisorySupport` của client Classic** để tạo đúng topic. Tránh ghép chuỗi thủ công cho mọi loại vì tiền tố/tên advisory không phải API JMS chuẩn; cần kiểm tra broker/client cùng dòng phiên bản.

### 2.3. Wildcard của Classic

Classic hỗ trợ wildcard trong tên destination topic theo quy tắc riêng:

- `*` phù hợp **một** thành phần tên phân cách bởi dấu chấm.
- `>` phù hợp **một hoặc nhiều** thành phần ở phần còn lại của tên, được dùng ở cuối đường dẫn theo ngữ nghĩa wildcard của Classic.

Ví dụ subscriber có thể theo dõi consumer của các queue bắt đầu bằng `orders.` qua:

~~~text
ActiveMQ.Advisory.Consumer.Queue.orders.>
~~~

Nhưng khi bài toán chỉ quan tâm `orders.created`, **đăng ký topic chính xác** sẽ tiết kiệm traffic và tránh rò rỉ thông tin về destination khác.

**Wildcard là tính năng định tuyến của ActiveMQ Classic, không phải quy tắc JMS chuẩn.** Không mặc định port cách viết này sang Artemis hay một broker khác.

## 3. Advisory có thể nói gì và không thể nói gì?

Một sự kiện `ConsumerInfo` cho biết broker đã ghi nhận một consumer. Điều này **không chứng minh** consumer đó đang xử lý đúng nghiệp vụ, kết nối tới database khỏe mạnh, hoặc đã ack message.

Tương tự:

- `ProducerInfo` thể hiện producer hiện diện, **không** đo số message được gửi thành công.
- `DestinationInfo` thể hiện queue/topic được tạo hoặc xóa, **không** cho biết queue đang tồn bao nhiêu đơn hàng.
- `RemoveInfo` cho biết broker loại một ID, **không** nhất thiết chứng minh nguyên nhân là deploy bình thường, timeout, crash hay mất mạng.
- Advisory slow consumer thể hiện broker đã phát hiện theo tiêu chí của nó, **không** phải số liệu đầy đủ về độ trễ ứng dụng.
- Message advisory về delivery/consumption phản ánh mốc xử lý tại broker/JMS, **không** đồng nghĩa giao dịch database hoặc HTTP bên ngoài đã commit.

### 3.1. Event stream và state snapshot khác nhau

Advisory là chuỗi thông báo thay đổi. Một số advisory có thể gửi thông tin về đối tượng đã tồn tại khi một subscriber mới kết nối, nhưng **đừng coi chuỗi advisory là snapshot nguyên tử, đầy đủ và bền vững**.

Tình huống: monitor mất kết nối 30 giây, hai worker xuất hiện rồi biến mất trong khoảng đó. Khi reconnect, monitor có thể không thấy đủ hai lần thay đổi để tái dựng chính xác lịch sử. Ngay cả khi có thông báo về trạng thái hiện tại, **lịch sử đã bỏ lỡ không mặc nhiên được phát lại** như Kafka log.

Giải pháp đáng tin cậy:

1. Dùng **JMX** (hoặc cơ chế quản trị/metrics tương ứng) để lấy trạng thái hiện tại: queue, consumer count, producer count, queue size.
2. Dùng **advisory** để biết thay đổi gần thời gian thực và kích hoạt refresh dữ liệu.
3. **Đối soát định kỳ** toàn bộ snapshot; không chỉ cộng/trừ số lượng dựa trên từng advisory nhận được.
4. Sau reconnect/failover, coi trạng thái cache là **chưa xác minh** cho đến khi đồng bộ lại với broker.

Một thiết kế hợp lý là advisory trigger việc làm mới snapshot, còn số liệu snapshot quyết định cảnh báo:

~~~mermaid
flowchart LR
    A["ActiveMQ Classic broker"] -->|"Advisory topic"| E["Event listener"]
    E -->|"Báo có biến động"| R["Refresh coordinator"]
    A -->|"JMX/current metrics"| R
    R --> S[("Current topology snapshot")]
    S --> D["Dashboard / alert"]
    T["Periodic reconciliation"] --> R
~~~

Đừng dùng advisory như **audit log bắt buộc giữ trong nhiều tháng**. Nhu cầu audit cần một cơ chế ghi bền vững riêng (cơ sở dữ liệu, log có chính sách retention, hoặc event store phù hợp).

## 4. Cấu hình ActiveMQ Classic: bật advisory và chọn mức chi tiết

### 4.1. Bật cơ chế advisory trên broker

Trong **`conf/activemq.xml` của ActiveMQ Classic**, phần `broker` có thuộc tính `advisorySupport`. Nhiều bản cài Classic bật advisory theo mặc định, nhưng bạn phải kiểm tra file và phiên bản đang chạy.

Ví dụ phần tử broker (trích đoạn, **không phải tệp `activemq.xml` đầy đủ**):

~~~xml
<broker xmlns="http://activemq.apache.org/schema/core"
        brokerName="classic-lab"
        advisorySupport="true">

    <!-- Các transportConnector, persistenceAdapter, plugins... đã có -->

</broker>
~~~

Nếu `advisorySupport="false"`, đừng kỳ vọng nhận các advisory đã mô tả dù TCP/JMS messaging vẫn hoạt động. Ngược lại, **bật advisory không khiến mọi loại thông báo mức message tự phát sinh**: nhiều loại phải được bật chọn lọc ở destination policy.

Không thay thế cả phần tử `<broker>` hiện hữu bằng đoạn ví dụ; khi thực hành hãy thêm/điều chỉnh đúng thuộc tính trên cấu hình đang có. Thay cấu hình broker có thể cần restart theo quy trình của bản triển khai.

### 4.2. Bật một số advisory theo destination policy

Với các queue `orders.`, bạn có thể cấu hình thêm trong `<destinationPolicy>` hiện hữu:

~~~xml
<destinationPolicy>
    <policyMap>
        <policyEntries>
            <policyEntry queue="orders.>"
                         advisoryForSlowConsumers="true"
                         advisoryWhenFull="true"
                         advisoryForConsumed="false"
                         advisoryForDelivery="false"/>
        </policyEntries>
    </policyMap>
</destinationPolicy>
~~~

Ý nghĩa:

- `queue="orders.>"`: policy áp dụng các queue phù hợp tên, chẳng hạn `orders.created`.
- `advisoryForSlowConsumers="true"`: cho phép phát thông báo slow consumer khi broker xác định được tình trạng theo cơ chế/strategy thích hợp.
- `advisoryWhenFull="true"`: phát advisory khi đích gặp điều kiện đầy tài nguyên theo chính sách broker.
- Hai cờ `advisoryForConsumed` và `advisoryForDelivery` đặt `false` để không phát mỗi lần consume/deliver trong ví dụ giám sát topology. Nếu bật trên queue lưu lượng lớn, số lượng advisory có thể tăng theo từng message.

**Quan trọng:** đoạn trên là mẫu cấu hình chọn lọc. Nếu broker đã có `<destinationPolicy>`, `<policyMap>` hay `<policyEntry>` phù hợp, hãy **hợp nhất thuộc tính** vào mục hiện có, giữ nguyên các chính sách khác (memory, pending, dead letter, redelivery, dispatch...). Không tạo hai policy trùng phạm vi và ngầm cho rằng cả hai sẽ cùng áp dụng.

Một số advisory như **slow consumer** chỉ xuất hiện nếu broker đã phát hiện điều kiện tương ứng; đơn thuần đặt cờ không làm phát sinh sự kiện tức thì. Cách phát hiện và chính sách cụ thể cần đối chiếu với phiên bản Classic thực tế.

### 4.3. Ảnh hưởng đến hiệu năng

Advisory có chi phí thực:

- Mỗi lần thay đổi producer/consumer/connection có thể tạo thêm message quản trị.
- Với advisory mức message (`MessageDelivered`, `MessageConsumed`), tải quan sát có thể gần với **số message nghiệp vụ** nếu được bật rộng.
- Subscriber giám sát chậm hoặc log quá nhiều có thể tự trở thành nguồn tải và che khuất tín hiệu quan trọng.
- Broker có thể phải xử lý thêm topic, wildcard subscriber và serialization của command.

Vì vậy nên **ưu tiên advisory về topology**, chỉ bật advisory mức message trong kiểm thử có mục tiêu, rồi dùng metric tổng hợp để đánh giá throughput/latency thường xuyên.

## 5. Thực hành Java: nhận advisory và giải mã sự kiện

Bài thực hành dùng **ActiveMQ Classic 5.18.3** và JMS namespace **`javax.jms`**. Đây là một phiên bản ví dụ cố định, không phải tuyên bố bản mới nhất. Mã không dùng `jakarta.jms` và không dùng `artemis-jakarta-client`, vì đang làm việc với **Classic 5.x**.

Bạn cần một broker Classic đang chạy, có TCP transport connector tương thích tại `tcp://127.0.0.1:61616`. Tài khoản và role phải đủ quyền kết nối, subscribe advisory topic, tạo consumer/producer tới queue `orders.created`. Dùng broker lab; không mở các advisory nhạy cảm công khai.

### 5.1. Dự án Maven độc lập

~~~text
classic-advisory-lab/
├── pom.xml
└── src/main/java/lab/
    └── ClassicAdvisoryLab.java
~~~

`pom.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>lab</groupId>
    <artifactId>classic-advisory-lab</artifactId>
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
                <version>3.5.0</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

`activemq-client` cung cấp ActiveMQ client và các lớp command/advisory Classic cần dùng, cùng các dependency chuyển tiếp theo artifact. Nếu dự án thực đã có JMS API dependency thì phải kiểm tra dependency tree để tránh trộn không tương thích giữa `javax.jms` và `jakarta.jms`.

### 5.2. Một chương trình, ba chế độ: monitor / consumer / producer

Mục đích của ba chế độ:

- **`monitor`:** subscribe các topic advisory, in ra loại sự kiện và ID liên quan.
- **`consumer`:** mở một consumer trên queue `orders.created`, giữ kết nối đến khi bấm Enter, rồi đóng.
- **`producer`:** mở một producer gắn với cùng queue, giữ đến khi bấm Enter, rồi đóng. Chế độ này chỉ tạo/đóng producer, **không gửi message nghiệp vụ**, để cô lập advisory lifecycle.

Tạo file `src/main/java/lab/ClassicAdvisoryLab.java`:

~~~java
package lab;

import java.io.IOException;
import java.time.Instant;
import javax.jms.Connection;
import javax.jms.JMSException;
import javax.jms.Message;
import javax.jms.MessageConsumer;
import javax.jms.MessageListener;
import javax.jms.MessageProducer;
import javax.jms.Queue;
import javax.jms.Session;
import javax.jms.Topic;

import org.apache.activemq.ActiveMQConnectionFactory;
import org.apache.activemq.advisory.AdvisorySupport;
import org.apache.activemq.command.ActiveMQMessage;
import org.apache.activemq.command.ActiveMQQueue;
import org.apache.activemq.command.ConnectionInfo;
import org.apache.activemq.command.ConsumerInfo;
import org.apache.activemq.command.DataStructure;
import org.apache.activemq.command.DestinationInfo;
import org.apache.activemq.command.ProducerInfo;
import org.apache.activemq.command.RemoveInfo;

public final class ClassicAdvisoryLab {

    private static final String DESTINATION = "orders.created";

    private ClassicAdvisoryLab() {}

    public static void main(String[] args) throws Exception {
        String mode = args.length == 0 ? "monitor" : args[0];
        String url = System.getenv().getOrDefault(
                "ACTIVEMQ_URL", "tcp://127.0.0.1:61616");

        ActiveMQConnectionFactory factory =
                new ActiveMQConnectionFactory(url);

        // Không ghi user/password cố định vào mã.
        // Nếu broker lab không dùng authentication, bỏ trống cả hai biến.
        String user = System.getenv("ACTIVEMQ_USER");
        String password = System.getenv("ACTIVEMQ_PASSWORD");
        if ((user == null) != (password == null)) {
            throw new IllegalArgumentException(
                    "Cần đặt cả ACTIVEMQ_USER và ACTIVEMQ_PASSWORD");
        }

        Connection connection = user == null
                ? factory.createConnection()
                : factory.createConnection(user, password);

        try {
            Session session =
                    connection.createSession(false, Session.AUTO_ACKNOWLEDGE);

            switch (mode) {
                case "monitor":
                    monitor(session);
                    connection.start();
                    waitForEnter("Đang nghe advisory. Bấm Enter để dừng.");
                    break;
                case "consumer":
                    runConsumer(session, connection);
                    break;
                case "producer":
                    runProducer(session, connection);
                    break;
                default:
                    throw new IllegalArgumentException(
                            "Mode phải là monitor, consumer hoặc producer");
            }

            session.close();
        } finally {
            // javax.jms.Connection của Classic phải được đóng an toàn.
            connection.close();
        }
    }

    private static void monitor(Session session) throws JMSException {
        ActiveMQQueue queue = new ActiveMQQueue(DESTINATION);

        // Dùng AdvisorySupport để xác định chính xác topic advisory.
        Topic consumerTopic = AdvisorySupport.getConsumerAdvisoryTopic(queue);
        Topic producerTopic = AdvisorySupport.getProducerAdvisoryTopic(queue);

        // Hai topic cấp broker, độc lập với queue orders.created.
        Topic connectionTopic =
                session.createTopic("ActiveMQ.Advisory.Connection");
        Topic queueDestinationTopic =
                session.createTopic("ActiveMQ.Advisory.Queue");

        Topic[] topics = {
                consumerTopic, producerTopic,
                connectionTopic, queueDestinationTopic
        };

        MessageListener listener = ClassicAdvisoryLab::printAdvisory;
        for (Topic topic : topics) {
            MessageConsumer subscription = session.createConsumer(topic);
            subscription.setMessageListener(listener);
            System.out.println("WATCH " + topic.getTopicName());
        }
    }

    private static void printAdvisory(Message message) {
        try {
            String topic = String.valueOf(message.getJMSDestination());

            if (!(message instanceof ActiveMQMessage amqMessage)) {
                System.out.println(Instant.now()
                        + " topic=" + topic
                        + " unexpected JMS type="
                        + message.getClass().getName());
                return;
            }

            DataStructure data = amqMessage.getDataStructure();
            String description;

            if (data instanceof ConsumerInfo info) {
                description = "CONSUMER_ADDED id=" + info.getConsumerId()
                        + " dest=" + info.getDestination();
            } else if (data instanceof ProducerInfo info) {
                description = "PRODUCER_ADDED id=" + info.getProducerId()
                        + " dest=" + info.getDestination();
            } else if (data instanceof ConnectionInfo info) {
                description = "CONNECTION_ADDED id="
                        + info.getConnectionId();
            } else if (data instanceof DestinationInfo info) {
                description = "DESTINATION_CHANGE dest="
                        + info.getDestination()
                        + " op=" + info.getOperationType();
            } else if (data instanceof RemoveInfo info) {
                description = "REMOVED objectId=" + info.getObjectId();
            } else if (data == null) {
                description = "ADVISORY_WITHOUT_COMMAND";
            } else {
                description = "OTHER_COMMAND type="
                        + data.getClass().getSimpleName();
            }

            System.out.println(Instant.now()
                    + " topic=" + topic + " " + description);
        } catch (JMSException ex) {
            System.err.println("Không đọc được advisory: " + ex.getMessage());
        }
    }

    private static void runConsumer(Session session, Connection connection)
            throws JMSException, IOException {
        Queue queue = session.createQueue(DESTINATION);
        MessageConsumer consumer = session.createConsumer(queue);

        connection.start();
        waitForEnter("Consumer đã mở trên " + DESTINATION
                + ". Bấm Enter để đóng.");
        consumer.close();
    }

    private static void runProducer(Session session, Connection connection)
            throws JMSException, IOException {
        Queue queue = session.createQueue(DESTINATION);
        MessageProducer producer = session.createProducer(queue);

        connection.start();
        waitForEnter("Producer đã mở trên " + DESTINATION
                + ". Bấm Enter để đóng.");
        producer.close();
    }

    private static void waitForEnter(String prompt) throws IOException {
        System.out.println(prompt);
        System.in.read();
    }
}
~~~

**Những điểm quan trọng trong mã:**

1. `AdvisorySupport.getConsumerAdvisoryTopic(queue)` và `getProducerAdvisoryTopic(queue)` giúp tránh viết nhầm tên của các topic advisory theo queue.
2. Connection advisory và destination advisory là topic **cấp broker**; chúng có thể mang sự kiện không chỉ riêng `orders.created`. Trong production, cần giới hạn phạm vi và không log dữ liệu nhạy cảm.
3. `ActiveMQMessage.getDataStructure()` cho phép phân loại command. **`RemoveInfo` cần đọc trong bối cảnh topic**, vì `objectId` có thể đại diện consumer, producer hoặc connection. Đừng đọc một RemoveInfo rồi mặc định “một consumer vừa biến mất”.
4. `DestinationInfo.getOperationType()` là giá trị lệnh nội bộ; để phân biệt add/remove, giải mã theo API/constant cùng phiên bản Classic. Đoạn in số nguyên để tránh đoán sai một giá trị tùy phiên bản.
5. Listener chạy trên luồng callback JMS; nếu xử lý nặng, hãy chuyển thông tin tối thiểu vào bộ đệm giám sát hoặc queue nội bộ, không làm chậm vòng callback bằng thao tác database hay HTTP dài.
6. `AUTO_ACKNOWLEDGE` chỉ xác nhận việc nhận advisory ở cấp JMS. Nó không đem lại lưu trữ audit; không dùng cơ chế này để kết luận một thay đổi đã được ghi bền trong hệ thống giám sát.
7. Chương trình giữ kết nối đến khi bấm Enter để bạn **quan sát thời điểm add và remove**. Nếu chạy trong terminal không tương tác khiến stdin đóng ngay, các mode có thể kết thúc sớm; hãy chạy ở terminal có stdin thực.

### 5.3. Cấu hình kết nối khi broker có xác thực

Các biến môi trường ví dụ trên **PowerShell**, dùng đúng account đã cấp trên broker lab:

~~~powershell
$env:ACTIVEMQ_URL = "tcp://127.0.0.1:61616"
$env:ACTIVEMQ_USER = "monitor-lab"
$env:ACTIVEMQ_PASSWORD = "<mat-khau-lab>"
~~~

Các giá trị trong ngoặc chỉ là placeholder. Nếu broker không cần authentication, có thể không đặt cả `ACTIVEMQ_USER` và `ACTIVEMQ_PASSWORD`. Không commit mật khẩu vào source code, không in credential vào log. Trong sản xuất dùng secret manager, TLS và role riêng theo nhiệm vụ; script lab đặt biến trong session terminal chỉ nhằm đơn giản hóa minh họa.

**Nhớ:** cùng một broker có thể cho quyền connect nhưng cấm `read` một advisory topic hoặc cấm `admin`/create trên destination nghiệp vụ. Quyền đọc advisory khác với quyền đọc message ở queue `orders.created`.

### 5.4. Biên dịch và chạy theo trình tự

Từ thư mục chứa `pom.xml`:

~~~powershell
mvn -q -DskipTests package
~~~

Mở **ba terminal** tại cùng thư mục dự án. Đảm bảo các terminal có cùng cấu hình biến môi trường khi cần.

**Terminal A:** chạy monitor trước, giữ nguyên:

~~~powershell
mvn -q exec:java "-Dexec.mainClass=lab.ClassicAdvisoryLab" "-Dexec.args=monitor"
~~~

Kỳ vọng monitor in tên bốn topic `WATCH ...`, ví dụ:

~~~text
WATCH ActiveMQ.Advisory.Consumer.Queue.orders.created
WATCH ActiveMQ.Advisory.Producer.Queue.orders.created
WATCH ActiveMQ.Advisory.Connection
WATCH ActiveMQ.Advisory.Queue
Đang nghe advisory. Bấm Enter để dừng.
~~~

**Terminal B:** tạo consumer trên queue:

~~~powershell
mvn -q exec:java "-Dexec.mainClass=lab.ClassicAdvisoryLab" "-Dexec.args=consumer"
~~~

Kỳ vọng terminal A có một sự kiện `CONSUMER_ADDED` với destination `orders.created`. Tùy thời điểm, A có thể nhận thêm `CONNECTION_ADDED` và `DESTINATION_CHANGE` nếu queue mới được tạo. Bấm Enter ở terminal B để đóng consumer: A có thể nhận `REMOVED objectId=...` trên advisory consumer, cùng thay đổi connection.

**Terminal C:** tạo producer trên cùng queue:

~~~powershell
mvn -q exec:java "-Dexec.mainClass=lab.ClassicAdvisoryLab" "-Dexec.args=producer"
~~~

Kỳ vọng terminal A nhận `PRODUCER_ADDED` trên topic producer của `orders.created`. Bấm Enter ở C; quan sát `REMOVED` liên quan producer.

Cuối cùng bấm Enter ở A để đóng listener.

### 5.5. Vì sao thứ tự và số lượng sự kiện có thể khác?

Nếu queue đã tồn tại, việc mở consumer/producer **không** tạo thêm một `DestinationInfo` add mới. Nếu monitor vừa subscribe và broker phát thông tin hiện trạng theo cơ chế advisory, có thể xuất hiện một số sự kiện cho đối tượng đã có **trước khi chạy**. Thời gian dispatch, kết nối, cấu hình và client cũng ảnh hưởng thứ tự quan sát.

**Đừng kiểm thử bằng số sự kiện cố định trên toàn bộ bốn topic.** Hãy kiểm tra quan hệ có ý nghĩa: B mở consumer mới → quan sát ConsumerInfo đúng queue/ID; B đóng → RemoveInfo tương ứng, nếu monitor kết nối liên tục và broker phát sự kiện. Tương tự với producer.

Chỉ để kiểm tra trạng thái hiện tại sau thao tác, đối chiếu thêm **consumer count/producer count** qua JMX hoặc giao diện quản trị broker.

## 6. Cách suy luận đúng từ dữ liệu advisory

### 6.1. Đếm consumer mà không đếm nhầm

Một triển khai ngây thơ thường làm:

~~~text
on ConsumerInfo: consumerCount += 1
on RemoveInfo:   consumerCount -= 1
~~~

Cách này dễ sai vì:
- Khi bắt đầu subscribe có thể nhận thông báo trạng thái hiện có.
- Monitor mất kết nối có thể bỏ lỡ add/remove.
- Một số thông điệp remove không cùng loại đối tượng nếu subscriber theo dõi nhiều topic.
- Trong broker network/failover, các ID và sự kiện cần được phân biệt theo broker và vòng đời connection.
- Thứ tự nhận trên nhiều topic không phải thứ tự giao dịch toàn hệ thống.

Thay bằng một **tập ID được quan sát**, hoặc tốt hơn là dùng advisory chỉ làm tín hiệu làm mới số liệu broker:

~~~text
consumerIdsByQueue["orders.created"] = set()

on ConsumerInfo event from consumer advisory:
    add (brokerIdentity, consumerId) to set
on RemoveInfo event from consumer advisory:
    remove matching (brokerIdentity, objectId)
on reconnect:
    mark local set as stale
    refresh JMX snapshot and reconcile
~~~

Tập này vẫn chỉ là **cache quan sát**, không được xem là nguồn sự thật sau khi mất message. Khi cần đếm chính xác tại một thời điểm, dùng MBean/management API tương ứng và ghi rõ thời điểm snapshot.

### 6.2. Xử lý remove đúng loại

Nếu subscribe đồng thời `ActiveMQ.Advisory.Connection` và `ActiveMQ.Advisory.Consumer.Queue.orders.created`, `RemoveInfo` có thể xuất hiện trên cả hai. Hãy lưu metadata:

| Topic nhận được | `RemoveInfo.objectId` thường liên quan | Cách xử lý |
|---|---|---|
| Consumer advisory | Consumer ID | Xóa consumer ID của destination tương ứng |
| Producer advisory | Producer ID | Xóa producer ID tương ứng |
| Connection advisory | Connection ID | Đánh dấu connection biến mất; kiểm tra các entity liên quan |
| Destination advisory | Có thể mang `DestinationInfo` với loại thao tác remove | Đối chiếu tên destination và làm mới snapshot |

Không suy ra “worker lỗi” chỉ từ `RemoveInfo`; worker có thể được dừng có chủ đích trong một rolling deployment. Muốn phân biệt crash và rolling update cần tương quan thêm **deployment event, process health, application log** và metrics.

### 6.3. Xử lý message lạ và tương thích phiên bản

Advisory không mặc nhiên là `TextMessage`. Mã nên:

- Kiểm tra `instanceof ActiveMQMessage` trước khi giải mã.
- Kiểm tra `getDataStructure()` có null hoặc loại command không dự kiến.
- Ghi log **loại, topic, ID**; không dump toàn bộ object nếu có thông tin nhận dạng hoặc dữ liệu nhạy cảm.
- Giữ phần parser chịu được event mới/không biết; không throw làm listener chết trên một advisory không liên quan.
- Test với **đúng bản broker và client** được sử dụng. Không coi contract command nội bộ là schema nghiệp vụ ổn định giữa mọi phiên bản.

## 7. Theo dõi slow consumer, queue full và message-level advisory

Advisory về cấu trúc (connection/consumer/producer/destination) thường có lưu lượng thấp hơn advisory theo từng message. Khi muốn giám sát hiệu năng, cần phân biệt:

| Loại tín hiệu | Câu hỏi nó giúp giải đáp | Điều kiện và giới hạn |
|---|---|---|
| Slow consumer advisory | Broker thấy consumer chậm theo cơ chế hiện có? | Phụ thuộc policy/strategy phát hiện; không phải mọi chậm trễ DB đều kích hoạt |
| Full advisory | Broker gặp ngưỡng tài nguyên/flow control cho destination? | Cần cấu hình và đối chiếu resource usage, producer blocking |
| Message delivered | Broker đã giao message cho consumer? | Không đồng nghĩa business transaction thành công |
| Message consumed | Broker đã ghi nhận message được tiêu thụ? | Không thay thế số liệu xử lý thành công của ứng dụng |
| Message expired | Message hết TTL theo broker? | Cần kiểm tra TTL, dead-letter/expiry handling và yêu cầu nghiệp vụ |
| Discarded / no consumer | Có trường hợp broker loại thông điệp hoặc không có consumer tại thời điểm gửi? | Tùy loại destination, policy và điều kiện kích hoạt |

**Ví dụ:** một queue có `consumerCount=1` nhưng số message chờ tăng liên tục, độ tuổi message lâu nhất tăng và queue full advisory xuất hiện. Kết luận hợp lý là **năng lực tiêu thụ không theo kịp hoặc có tắc nghẽn**, chứ không kết luận “consumer chết”. Cần thêm queue depth, enqueue/dequeue rate, thread dump, thời gian xử lý và log ứng dụng.

### 7.1. Có nên bật advisory mỗi lần delivered/consumed?

Chỉ nên bật nếu mục tiêu quan sát cụ thể cần đến chúng, trong một phạm vi kiểm soát. Ví dụ queue nhận 5.000 message/s và bật hai loại advisory theo mỗi message có thể tạo thêm tải đáng kể lên broker và subscriber. Không được giả định mỗi message nghiệp vụ tương ứng chính xác hai sự kiện advisory trong mọi đường đi (retry, rollback, expiration và cấu hình có thể thay đổi điều này).

Để đo throughput thường xuyên, ưu tiên **JMX counters**, metrics exporter và sampling, cùng request correlation trong log ứng dụng. Advisory phù hợp để **phát hiện biến động** hơn là làm pipeline phân tích message-level lưu lượng cao.

### 7.2. Nhận biết vấn đề redelivery/DLQ mà advisory không giải quyết

Redelivery và DLQ nằm trong phạm vi vận hành cùng message broker, nhưng một advisory consumer add/remove **không** cho biết:

- Message đã được rollback bao nhiêu lần.
- Nghiệp vụ đã xử lý thành công hay chưa.
- Chính sách redelivery đã đưa message vào DLQ đúng lúc hay chưa.

Các vấn đề này cần theo dõi thêm `JMSXDeliveryCount` khi được provider cung cấp, queue DLQ, redelivery policy, application retry metric, trạng thái transaction và log theo correlation ID. Không dùng advisory thay thế chương trình xử lý lỗi nghiệp vụ.

## 8. Bảo mật advisory và quyền truy cập

Advisory có thể lộ **tên queue/topic nội bộ, connection ID, consumer/producer ID, cấu trúc topology và tín hiệu lỗi**. Tùy event/client, command còn có metadata không nên chia sẻ rộng. Vì vậy subscriber giám sát cần **nguyên tắc quyền tối thiểu**.

Trong Classic, có thể áp dụng `authorizationPlugin` và các `authorizationEntry` để quản lý quyền `read` trên các advisory topic. Ví dụ một mục nằm **bên trong `<authorizationEntries>` đã được cấu hình**:

~~~xml
<!-- Chỉ là một entry minh họa, không phải cấu hình security hoàn chỉnh. -->
<authorizationEntry
    topic="ActiveMQ.Advisory.Consumer.Queue.orders.created"
    read="observers,admins"
    write="admins"
    admin="admins"/>
~~~

Cần thiết kế toàn bộ policy phù hợp hệ thống: các client/framework có thể cần quyền đọc một số advisory cho cơ chế theo dõi động; nếu chặn nhầm sẽ phát sinh lỗi khó chẩn đoán. Nhiều loại subscription sử dụng wildcard cần quyền tương thích với wildcard. Broker-generated advisory không phải thao tác publish từ ứng dụng thông thường, nên kiểm tra cách broker kiểm soát permission khi áp dụng policy.

Các nguyên tắc thực tế:

1. Chỉ cho tài khoản monitor **đọc những advisory thực sự cần thiết**; không cấp quyền quản trị đầy đủ để dễ chạy demo.
2. Dùng **TLS** khi message/credential đi qua mạng; không để OpenWire port công khai ra Internet.
3. Không log toàn bộ `ConnectionInfo` hay command object; giới hạn tập trường theo nhu cầu và che thông tin nhạy cảm.
4. Tách mật khẩu ứng dụng và mật khẩu quan sát, xoay vòng credential, giám sát lỗi authentication/authorization.
5. Nếu đẩy advisory sang hệ thống khác, áp dụng retention và phân quyền ở đích; dữ liệu topology cũng cần quản trị truy cập.

## 9. Kiểm thử và chẩn đoán

### 9.1. Kịch bản kiểm thử tối thiểu

| Bước | Thao tác | Kết quả cần quan sát |
|---|---|---|
| 1 | Start broker Classic có `advisorySupport=true` | Không lỗi cấu hình/transport; broker nhận JMS |
| 2 | Chạy mode `monitor` | Đăng ký được bốn topic, không lỗi permission |
| 3 | Chạy mode `consumer` | Monitor thấy `ConsumerInfo` của `orders.created` |
| 4 | Đóng consumer bằng Enter | Monitor nhận thông báo remove tương ứng nếu còn connected |
| 5 | Chạy mode `producer` | Monitor thấy `ProducerInfo` của cùng queue |
| 6 | Đóng producer | Monitor nhận remove producer theo điều kiện quan sát |
| 7 | Tắt monitor, thay đổi consumer, bật monitor | Nhận diện khoảng trống quan sát, đối soát JMX; không giả định có đầy đủ lịch sử |
| 8 | Xem JMX/console hiện trạng | Snapshot consumer count phù hợp kết quả thao tác hiện tại |

### 9.2. Các lỗi thường gặp

| Triệu chứng | Khả năng cao | Cách khoanh vùng |
|---|---|---|
| Java không kết nối được | Broker chưa nghe port, sai hostname, firewall hoặc TLS mismatch | Kiểm tra transport connector/port/log và client URL |
| Kết nối được nhưng không subscribe được advisory | ACL thiếu `read` trên advisory topic | Kiểm tra role và authorization entries |
| Monitor chạy nhưng không thấy consumer event | Sai topic (queue vs topic), sai destination, broker tắt advisory, hoặc sự kiện xảy ra trước khi subscribe | Log tên topic từ `AdvisorySupport`, bật monitor trước và thử lại |
| Monitor thấy connection event nhưng không thấy consumer event | Connection đã mở, nhưng consumer chưa tạo đúng queue, thiếu quyền, hoặc đang nghe sai advisory topic | Xem log Java, queue name và quyền subscribe |
| `ClassNotFoundException` / `NoClassDefFoundError` | Thiếu `activemq-client` hoặc trộn `javax.jms` với `jakarta.jms` | Kiểm tra `mvn dependency:tree` và import |
| `RemoveInfo` không khớp kiểu đang đếm | Áp cùng logic cho consumer, producer và connection | Dùng topic nguồn và loại ID để phân biệt |
| Dashboard đếm consumer âm hoặc lệch JMX | Missed/replayed advisory, reconnect hoặc snapshot không nguyên tử | Đánh dấu cache stale và đối soát trạng thái hiện tại |
| Bật delivery/consumed advisory khiến broker nặng | Mỗi message thêm sự kiện giám sát | Tắt bớt mức message, chỉ bật theo phạm vi có mục tiêu, dùng JMX |
| Sau restart mất lịch sử biến động | Advisory không phải event log bền vững | Dùng audit pipeline riêng nếu cần lưu sự kiện |

### 9.3. Ba phép thử lỗi nên làm trong môi trường lab

**Thử nghiệm A — Missed event:** khi monitor đang dừng, mở/đóng một consumer rồi mở monitor. Hệ giám sát không thể chắc chắn tái tạo toàn bộ trình tự sự kiện đã diễn ra trong thời gian offline. Hãy buộc hệ thống refresh current state từ JMX.

**Thử nghiệm B — Đóng connection bất thường:** thay vì bấm Enter, kết thúc hẳn tiến trình `consumer`. Broker có thể chỉ phát remove sau khi phát hiện connection đã mất (phụ thuộc network/transport inactivity timeout). Đừng xem chậm vài giây là chắc chắn không có sự kiện.

**Thử nghiệm C — Sai quyền:** dùng tài khoản có `connect` nhưng không có quyền `read` advisory topic. Kỳ vọng listener bị từ chối dù các tác vụ JMS khác có thể vẫn chạy. Sửa ACL theo nguyên tắc tối thiểu, không tắt authentication toàn broker.

## 10. Thiết kế giám sát production: advisory bổ trợ JMX và ứng dụng

Một kiến trúc giám sát bền vững tách rõ nguồn dữ liệu:

| Nguồn | Phù hợp | Không nên giao trách nhiệm |
|---|---|---|
| **Advisory topic** | Thông báo tức thời về connection, producer, consumer, destination và một số tình trạng đặc biệt | Lưu lịch sử đầy đủ, snapshot luôn đúng, chứng thực giao dịch nghiệp vụ |
| **JMX / broker metrics** | Queue depth, consumer count, enqueue/dequeue rate, memory/store usage, trạng thái broker | Thay thế toàn bộ timeline sự kiện nếu chỉ lấy theo chu kỳ |
| **Application metrics/log/traces** | Độ trễ xử lý, retry, lỗi DB/HTTP, correlation ID, thành công nghiệp vụ | Suy ra tất cả tình trạng nội bộ broker nếu không có dữ liệu broker |
| **Audit/event store riêng** | Lưu dài hạn, đối soát trách nhiệm, replay theo thời gian | Thay thế các health signal thời gian thực nếu ingest chậm |

### 10.1. Quy tắc cảnh báo thực tế

Ví dụ yêu cầu: **cảnh báo khi queue `orders.created` không có consumer liên tục năm phút và số message chờ đang tăng**.

Cách triển khai:

1. Listener nhận advisory consumer add/remove của queue và yêu cầu làm mới snapshot sớm.
2. Hệ giám sát định kỳ lấy **ConsumerCount**, **QueueSize**, **EnqueueCount/DequeueCount** từ MBean của đúng broker/destination.
3. Xác định điều kiện `ConsumerCount == 0` cùng queue backlog tăng trong cửa sổ thời gian, có xử lý dữ liệu thiếu và broker restart.
4. Chỉ cảnh báo sau khi điều kiện kéo dài đủ thời gian và đã đối soát, tránh báo nhầm khi rolling deployment.
5. Nếu cần phân biệt lỗi consumer với thay đổi theo kế hoạch, tương quan deployment event và health check ứng dụng.

Việc dùng advisory làm trigger giúp phản ứng sớm, còn số liệu JMX cung cấp trạng thái hiện tại cho điều kiện cảnh báo.

### 10.2. Những câu hỏi phải trả lời trước khi bật toàn broker

- Broker có **bao nhiêu destination, connection, producer và consumer**? Mỗi phút chúng biến động bao nhiêu lần?
- Subscriber advisory đặt ở đâu và có giữ được kết nối khi failover không?
- Có cần **lịch sử chính xác** hay chỉ trạng thái đang hoạt động? Nếu cần lịch sử, lưu bền bằng pipeline riêng.
- Có quyền nào cho phép đọc advisory nhưng phải tránh lộ thông tin topology? Quyền có tương thích các client/framework hiện hữu không?
- Mức sampling, retention và cảnh báo nào phù hợp, ai chịu trách nhiệm vận hành nếu subscriber chết?
- Nếu chạy nhiều Classic broker qua network connector, nguồn dữ liệu được gắn **broker identity** như thế nào để tránh trộn ID và double count?

## 11. Bài tập tự kiểm tra

**Tình huống 1:** bạn subscribe `ActiveMQ.Advisory.Consumer.Queue.orders.created` và nhận `RemoveInfo`. Có thể kết luận message vừa bị xóa khỏi queue không?

Không. `RemoveInfo` trong ngữ cảnh này nói về **consumer bị loại bỏ**, không phải dữ liệu nghiệp vụ bị tiêu thụ. Muốn biết message được ack/đưa DLQ, xem metrics và cơ chế xử lý message tương ứng.

**Tình huống 2:** monitor vừa khởi động, nhận `ConsumerInfo`, nhưng bạn chưa thấy worker mới nào deploy. Có chắc broker phát trùng không?

Không. Broker có thể gửi thông tin về consumer hiện hữu cho subscriber mới, hoặc consumer thực sự đã kết nối trước khi bạn bắt đầu quan sát. Đối soát trạng thái bằng JMX và kiểm tra ID/timestamp thay vì chỉ nhìn số lượng event.

**Tình huống 3:** tại sao không bật `advisoryForDelivery=true` cho toàn bộ 10.000 queue để làm metrics mặc định?

Vì số advisory có thể tăng theo message delivery, tạo lưu lượng/CPU bổ sung đáng kể, và delivery tại broker không đại diện cho **thành công nghiệp vụ**. Dùng metrics tổng hợp trước, chỉ bật chi tiết khi có câu hỏi điều tra cụ thể.

**Tình huống 4:** một worker chết sau khi commit DB nhưng trước JMS ack. Có dựa vào advisory để biết và sửa trùng đơn hàng được không?

Không. Advisory về connection/consumer không chứa ràng buộc exactly-once của giao dịch DB. Cần **idempotency**, khóa xử lý theo event ID, redelivery policy, DLQ và kiểm soát transaction. Advisory có thể báo worker rời broker, nhưng không khôi phục tác dụng nghiệp vụ.

**Tình huống 5:** bạn port nguyên listener trên sang Artemis. Tại sao có thể lỗi hoặc không nhận đúng message?

Vì `AdvisorySupport`, các topic `ActiveMQ.Advisory.*` và `ConsumerInfo/RemoveInfo` là **cơ chế cụ thể của ActiveMQ Classic**, không phải chuẩn JMS. Artemis có mô hình address/queue/routing và cơ chế quản trị/notification riêng; cần thiết kế lại adapter quan sát cho broker đó.

## 12. Tổng kết theo đúng phạm vi advisory

**Advisory message** giúp theo dõi biến động của broker ActiveMQ Classic qua **JMS topic đặc biệt**: connection, producer, consumer, queue/topic và một số điều kiện vận hành. Listener phải hiểu **destination advisory**, kiểu payload **broker command**, vòng đời add/remove và chi phí phát sự kiện.

Khi vận hành đáng tin cậy, hãy xem advisory là **tín hiệu thay đổi** để làm mới giám sát, **JMX** là nguồn snapshot hiện trạng, và **log/metrics nghiệp vụ** là nơi chứng minh công việc thành công hay thất bại. Giới hạn quyền đọc advisory, tránh log thông tin nhạy cảm, không bật advisory mức message đại trà, và luôn đối soát sau reconnect/failover.
