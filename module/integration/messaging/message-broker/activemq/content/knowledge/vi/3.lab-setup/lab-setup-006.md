# Kiểm tra kết nối bằng CLI, console và cặp producer–consumer tối thiểu

> **Chương:** Môi trường thực hành  
> **Học phần:** `INTEGRATION_MESSAGING_MESSAGE_BROKER_ACTIVEMQ` — thực hành Apache ActiveMQ Classic và Artemis trong giao tiếp bất đồng bộ với queue, topic, routing và JMS; hướng tới acknowledgment, transaction, redelivery, DLQ, bảo mật và vận hành broker đáng tin cậy.

## 1. Mục tiêu và phạm vi

Bài này hướng dẫn một phép thử hoàn chỉnh trên **ActiveMQ Artemis**: chạy broker trên Docker, xác minh đường quản trị qua **web console**, gửi/nhận qua **CLI**, rồi biên dịch và chạy **hai chương trình Java/JMS** độc lập. Cuối bài có hướng dẫn đối chiếu khi môi trường đang dùng **ActiveMQ Classic**, vì hai dòng sản phẩm không chia sẻ mọi CLI và dependency Java.

Hoàn thành bài, bạn cần tự trả lời được: broker có thực sự nghe cổng messaging không; user có quyền gửi/nhận không; queue đã có hoặc được tự tạo chưa; message đang chờ, đang được giao hay đã ack; và khi kết nối/consumer gặp lỗi thì chẩn đoán từ đâu.

| Thành phần | Cổng hoặc đích | Mục đích |
|---|---|---|
| Messaging TCP | `localhost:61616` | Kết nối từ Artemis CLI và Java JMS |
| Web management | `http://localhost:8161/console` | Đăng nhập và xem trạng thái broker |
| Queue thử CLI | `lab.cli.ping` | Gửi 3, nhận 3 message do CLI tạo |
| Queue thử Java | `lab.java.ping` | Gửi/nhận một `TextMessage` kèm `eventId` |
| Tài khoản lab | `lab / labpass123` | Xác thực cục bộ trong ví dụ |

Chọn **hai queue khác nhau** nhằm tránh consumer CLI lấy message Java hoặc ngược lại. Đây là *work queue* dạng cạnh tranh: nhiều consumer trên cùng queue thường chia nhau nhận việc; muốn phát mỗi sự kiện cho nhiều nhóm cần mô hình topic/subscription hoặc multicast.

~~~mermaid
flowchart LR
    CLI["CLI producer"] -->|"TCP 61616"| B[["Artemis broker"]]
    J["Java JMS producer"] -->|"TCP 61616"| B
    B --> Q1[("lab.cli.ping")]
    B --> Q2[("lab.java.ping")]
    Q1 --> C1["CLI consumer"]
    Q2 --> C2["Java JMS consumer"]
    WEB["Browser console"] <-->|"HTTP 8161"| B
~~~

**Điều kiện hoàn thành:** CLI gửi/nhận đủ số lượng, console hiển thị queue và thay đổi số message chờ, Java consumer in đúng body và event ID của Java producer, và có thể phân biệt lỗi kết nối với lỗi phân quyền.

## 2. Chuẩn bị môi trường

Cần **Docker Engine/Docker Desktop**, **JDK 17+**, **Apache Maven** và trình duyệt. Kiểm tra công cụ trên terminal:

~~~powershell
docker version
java -version
mvn -version
~~~

Bài minh họa với image **`apache/activemq-artemis:2.40.0`** và Maven client **`artemis-jakarta-client:2.40.0`**, cố định phiên bản để dễ tái hiện. Đây là **phiên bản ví dụ**, không hàm ý bản mới nhất. Nếu dùng release khác, kiểm tra lại image tag, Java API, giao thức được bật và cú pháp CLI theo phiên bản đó. Java ở đây dùng **`jakarta.jms`**, không dùng namespace `javax.jms` của các ứng dụng JMS đời cũ.

Trên máy chủ, cần hai cổng **61616** và **8161** còn trống. Chỉ publish ra **127.0.0.1** để không mở cổng lab ra toàn mạng.

## 3. Khởi động ActiveMQ Artemis bằng Docker

Chạy một lần:

~~~powershell
docker run -d --name amq-lab -p 127.0.0.1:61616:61616 -p 127.0.0.1:8161:8161 -e ARTEMIS_USER=lab -e ARTEMIS_PASSWORD=labpass123 apache/activemq-artemis:2.40.0
~~~

Ý nghĩa:
- `-d`: broker chạy tách khỏi terminal.
- `--name amq-lab`: tên ổn định để dùng với `docker exec/logs/start/stop`.
- Hai lệnh `-p`: map từ cổng host về cổng container, chỉ tại địa chỉ loopback host.
- `ARTEMIS_USER` và `ARTEMIS_PASSWORD`: tài khoản do image hỗ trợ cho bài lab, **không dùng làm mật khẩu production**.

Đọc trạng thái, port mapping và log:

~~~powershell
docker ps --filter name=amq-lab
docker port amq-lab
docker logs --tail 80 amq-lab
~~~

Kỳ vọng container ở trạng thái `Up`, cổng xuất hiện trong kết quả mapping và log không báo lỗi khởi động hay bind port. Chuỗi log thành công thay đổi theo phiên bản, do đó đừng phụ thuộc một câu chữ cố định.

**Các trường hợp gặp ngay từ bước này:**

- Nếu Docker báo tên `amq-lab` đã tồn tại, kiểm tra `docker ps -a --filter name=amq-lab`. Nếu đúng container lab đã dừng, có thể `docker start amq-lab`. Đừng xóa một container chưa kiểm tra vì nó có thể chứa dữ liệu.
- Nếu `61616` hoặc `8161` bị chiếm, đổi **cổng phía host**: ví dụ `-p 127.0.0.1:61626:61616` và `-p 127.0.0.1:8162:8161`. Khi đó Java dùng `tcp://localhost:61626`, browser dùng `http://localhost:8162/console`. CLI chạy *bên trong* container vẫn dùng cổng 61616.
- `localhost` trong Java chạy trên host và `localhost` trong `docker exec` thuộc hai không gian mạng riêng; cả hai đều đúng trong ví dụ vì một bên dùng port mapping, bên kia gọi broker ngay trong container.

Nếu container chưa sẵn sàng, xem log trước khi thử gửi message.

## 4. Dùng web console để kiểm tra quản trị

Mở **`http://localhost:8161/console`** và đăng nhập `lab` / `labpass123`.

Trên Artemis console (giao diện thường dựa trên Hawtio), tìm trang **addresses/queues** hoặc màn hình tương đương theo phiên bản. Quan sát:

- Broker đang kết nối và các address hiện có.
- Queue name, message count/queue depth, consumer count.
- Các thao tác duyệt message (**Browse**) và chỉ số enqueue/dequeue, nếu UI cung cấp.

Ban đầu không thấy `lab.cli.ping` hoặc `lab.java.ping` **là bình thường**: trong cấu hình tự tạo queue, chúng chỉ xuất hiện khi có thao tác tạo/gửi/nhận tới đích.

Việc console hoạt động mới chứng minh **đường HTTP quản trị** trên 8161 dùng được. Nó **chưa chứng minh** Java kết nối được TCP 61616 hoặc tài khoản có quyền gửi/consume message. Vì vậy tiếp tục thử riêng bằng CLI.

## 5. CLI: gửi ba message rồi nhận đủ ba

Artemis broker instance có công cụ CLI với các subcommand `producer`, `consumer`. Image trong bài thường đặt nó ở `/var/lib/artemis-instance/bin/artemis`. Trước khi chạy, xem trợ giúp **của bản đang sử dụng**:

~~~powershell
docker exec amq-lab /var/lib/artemis-instance/bin/artemis producer --help
docker exec amq-lab /var/lib/artemis-instance/bin/artemis consumer --help
~~~

Nếu bản image của bạn sử dụng đường dẫn instance khác, tìm đúng `ARTEMIS_INSTANCE` và executable `bin/artemis`; tùy chọn CLI có thể thay đổi theo release. Các lệnh bên dưới dùng option thông dụng của Artemis 2.x.

### 5.1. Producer CLI

~~~powershell
docker exec amq-lab /var/lib/artemis-instance/bin/artemis producer --url tcp://localhost:61616 --user lab --password labpass123 --destination queue://lab.cli.ping --message-count 3
~~~

Giải thích các option:

| Option | Ý nghĩa |
|---|---|
| `--url tcp://localhost:61616` | Broker endpoint theo góc nhìn từ *bên trong container* |
| `--user`, `--password` | Tài khoản xác thực |
| `--destination queue://lab.cli.ping` | Đích kiểu queue, không phải topic |
| `--message-count 3` | Gửi ba message do CLI tự tạo cho mục đích kiểm thử |

**Dừng ở đây để kiểm tra console.** Refresh trang queues, tìm `lab.cli.ping`. Nếu broker cho phép tự tạo queue và không có consumer khác, bạn sẽ thấy khoảng **3 message chờ**. Nội dung payload mà CLI tự phát sinh có thể khác giữa các phiên bản; bài không phụ thuộc việc các message chứa chuỗi cụ thể nào.

### 5.2. Consumer CLI

~~~powershell
docker exec amq-lab /var/lib/artemis-instance/bin/artemis consumer --url tcp://localhost:61616 --user lab --password labpass123 --destination queue://lab.cli.ping --message-count 3
~~~

Đợi lệnh nhận hoàn thành và đọc thống kê số message đã nhận. Trở lại console, refresh queue:

1. Message count/queue depth sẽ giảm về **0** sau khi ba message được nhận và xác nhận, nếu không có hoạt động song song khác.
2. Bộ đếm tổng số message đã thêm có thể **vẫn là 3**, vì nó đếm lịch sử enqueue, không phải số đang chờ.
3. Consumer count có thể quay về **0** vì CLI thoát sau khi hoàn thành.

**Tránh hiểu nhầm:** một message đã ack và bị gỡ khỏi queue không xuất hiện lại chỉ vì chạy consumer thêm lần nữa. Nếu muốn nhận lại một message, phải gửi message mới hoặc có một tình huống redelivery hợp lệ.

CLI thành công chứng minh broker nhận kết nối, xác thực cho phép thao tác và queue định tuyến được message. Nó **không đủ để cam kết xử lý nghiệp vụ exactly-once**.

## 6. Java/JMS: producer và consumer độc lập

Tạo dự án Maven riêng để kiểm tra client Java thực sự hoạt động. Cấu trúc:

~~~text
activemq-jms-lab/
├── pom.xml
└── src/main/java/lab/
    ├── Producer.java
    └── Consumer.java
~~~

### 6.1. `pom.xml`

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>lab</groupId>
    <artifactId>activemq-jms-lab</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.apache.activemq</groupId>
            <artifactId>artemis-jakarta-client</artifactId>
            <version>2.40.0</version>
        </dependency>
        <dependency>
            <groupId>jakarta.jms</groupId>
            <artifactId>jakarta.jms-api</artifactId>
            <version>3.1.0</version>
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

**Chú ý sự tương thích:** `artemis-jakarta-client` cho mã import `jakarta.jms`. Không đổi sang `javax.jms` nếu chưa đổi API và provider client phù hợp. JMS là API ở phía Java, còn giao thức trên socket được Artemis client triển khai.

### 6.2. `src/main/java/lab/Producer.java`

~~~java
package lab;

import jakarta.jms.ConnectionFactory;
import jakarta.jms.DeliveryMode;
import jakarta.jms.JMSContext;
import jakarta.jms.Queue;
import jakarta.jms.TextMessage;
import org.apache.activemq.artemis.jms.client.ActiveMQConnectionFactory;

import java.util.UUID;

public final class Producer {
    private static final String URL = "tcp://localhost:61616";
    private static final String USER = "lab";
    private static final String PASSWORD = "labpass123";
    private static final String QUEUE_NAME = "lab.java.ping";

    public static void main(String[] args) throws Exception {
        String body = args.length > 0 ? args[0]
                : "Xin chao Artemis, " + System.currentTimeMillis();
        String eventId = UUID.randomUUID().toString();

        ConnectionFactory factory = new ActiveMQConnectionFactory(URL);
        try (JMSContext context = factory.createContext(USER, PASSWORD)) {
            Queue queue = context.createQueue(QUEUE_NAME);

            TextMessage message = context.createTextMessage(body);
            message.setStringProperty("eventId", eventId);

            context.createProducer()
                    .setDeliveryMode(DeliveryMode.PERSISTENT)
                    .send(queue, message);

            System.out.println("SENT queue=" + QUEUE_NAME);
            System.out.println("messageId=" + message.getJMSMessageID());
            System.out.println("eventId=" + eventId);
            System.out.println("body=" + body);
        }
    }
}
~~~

Ý nghĩa các chi tiết:
- `ConnectionFactory` cung cấp kết nối; `JMSContext` quản lý connection/session theo API Jakarta JMS và được đóng bằng `try-with-resources`.
- `context.createQueue("lab.java.ping")` tạo *đối tượng destination phía client*; queue vật lý phải tồn tại hoặc broker được phép tự tạo. Lệnh này **không một mình bảo đảm** queue đã được cấp phát trên server.
- `DeliveryMode.PERSISTENT` yêu cầu lưu bền message theo JMS. Khả năng chịu lỗi thực tế còn phụ thuộc cấu hình journal, storage và HA.
- `eventId` là ID nghiệp vụ tự sinh để tham chiếu khi nói về idempotency; `JMSMessageID` là ID do provider gán. Không đồng nhất hai trường.

### 6.3. `src/main/java/lab/Consumer.java`

~~~java
package lab;

import jakarta.jms.ConnectionFactory;
import jakarta.jms.JMSConsumer;
import jakarta.jms.JMSContext;
import jakarta.jms.Message;
import jakarta.jms.Queue;
import jakarta.jms.TextMessage;
import org.apache.activemq.artemis.jms.client.ActiveMQConnectionFactory;

public final class Consumer {
    private static final String URL = "tcp://localhost:61616";
    private static final String USER = "lab";
    private static final String PASSWORD = "labpass123";
    private static final String QUEUE_NAME = "lab.java.ping";

    public static void main(String[] args) throws Exception {
        ConnectionFactory factory = new ActiveMQConnectionFactory(URL);

        try (JMSContext context = factory.createContext(
                USER, PASSWORD, JMSContext.AUTO_ACKNOWLEDGE)) {
            Queue queue = context.createQueue(QUEUE_NAME);
            JMSConsumer consumer = context.createConsumer(queue);

            // Giới hạn thời gian chờ để thử queue rỗng không bị treo.
            Message message = consumer.receive(5000);
            if (message == null) {
                System.out.println("TIMEOUT: queue khong co message trong 5 giay");
                return;
            }

            if (!(message instanceof TextMessage textMessage)) {
                throw new IllegalStateException(
                        "Message khong phai TextMessage");
            }

            System.out.println("RECEIVED queue=" + QUEUE_NAME);
            System.out.println("messageId=" + textMessage.getJMSMessageID());
            System.out.println("eventId="
                    + textMessage.getStringProperty("eventId"));
            System.out.println("body=" + textMessage.getText());
        }
    }
}
~~~

**Vì sao chọn `AUTO_ACKNOWLEDGE`?** Đây là chế độ tối thiểu để minh họa nhận thông điệp mà không phải tự viết transaction. Theo JMS, thao tác `receive()` đồng bộ được auto-ack khi nhận thành công theo hợp đồng của provider. Điều đó **không có nghĩa** mọi xử lý nghiệp vụ sau khi `receive()` đều đã thành công. Phần 9 giải thích sự khác biệt này.

### 6.4. Chạy và quan sát

Trong thư mục `activemq-jms-lab`, chạy:

~~~powershell
mvn -q -DskipTests package
mvn -q exec:java "-Dexec.mainClass=lab.Producer"
~~~

Producer phải in ra message ID, event ID và body. **Chưa chạy consumer vội.** Quay lại console, tìm `lab.java.ping`: nếu không có ứng dụng nào khác cùng queue, số message chờ dự kiến là **1**.

Tiếp theo:

~~~powershell
mvn -q exec:java "-Dexec.mainClass=lab.Consumer"
~~~

Đầu ra kỳ vọng (giá trị thực thay đổi):

~~~text
RECEIVED queue=lab.java.ping
messageId=ID:...
eventId=...
body=Xin chao Artemis, ...
~~~

So sánh `messageId`, `eventId` và `body` giữa producer và consumer: đó phải là **cùng một message**. Sau khi nhận/ack, console sẽ thấy queue hết message chờ nếu không có lưu lượng khác.

Chạy consumer thêm một lần **mà không gửi message mới**:

~~~powershell
mvn -q exec:java "-Dexec.mainClass=lab.Consumer"
~~~

Đầu ra kỳ vọng sau khoảng 5 giây:

~~~text
TIMEOUT: queue khong co message trong 5 giay
~~~

Lệnh timeout này cũng là bằng chứng consumer không tự tạo message mới và không vô hạn chờ queue trống. Nếu đổi thứ tự, chạy consumer trước rồi producer trong khoảng 5 giây, consumer có thể nhận ngay; đây là hành vi bất đồng bộ bình thường.

## 7. Diễn giải queue, address và chỉ số đúng cách

Trong Artemis, **address** là đích định tuyến; **queue** là nơi message được lưu/đưa đến consumer. Một JMS queue thường tương ứng address cùng tên được định tuyến **ANYCAST**, nhưng các thành phần này không phải cùng một khái niệm.

~~~text
Java producer -> address "lab.java.ping" -> [ANYCAST] -> queue "lab.java.ping"
                                                             |
                                                       Java consumer
~~~

**ANYCAST** thích hợp chia việc giữa consumer trong cùng queue. **MULTICAST** có thể gửi đến nhiều queue/subscription theo cấu hình. Kiểm thử một queue trong bài không chứng minh tính chất của topic/durable subscription.

| Chỉ số giao diện | Thường diễn giải là | Điều không nên kết luận |
|---|---|---|
| Queue depth / message count | Message hiện đang chờ/chưa hoàn tất theo cách broker tính | Không phải tổng message từng gửi |
| Messages added / enqueued | Tổng đếm message thêm vào queue | Có thể tiếp tục tăng khi depth đã về 0 |
| Messages acknowledged | Message đã ack theo broker | Không chứng minh database của consumer đã commit |
| Consumer count | Consumer còn đăng ký với queue | Bằng 0 sau khi chương trình Java thoát là bình thường |
| Delivering / in-flight | Message đã được giao nhưng chưa hoàn tất ack (nếu UI có) | Không nhất thiết nằm trong bộ đếm “ready” |

Các giá trị có thể cập nhật bất đồng bộ. Hãy refresh giao diện và đảm bảo không có producer/consumer thứ ba chạy song song trước khi quy kết chênh lệch là lỗi.

## 8. Queue chưa được tạo: cấu hình Artemis cần biết

Với môi trường lab mặc định, Artemis thường bật **auto-create address/queue**; song hệ thống thật có thể tắt để quản lý chặt tên đích và quyền.

Nếu queue `lab.java.ping` không được tạo, có thể cấu hình tĩnh trong phần `<addresses>` của **`broker.xml` thuộc broker instance**:

~~~xml
<!-- Chỉ thêm <address> vào <addresses> đã có trong broker.xml. -->
<address name="lab.java.ping">
    <anycast>
        <queue name="lab.java.ping"/>
    </anycast>
</address>
~~~

Đoạn này là **mảnh cấu hình**, không phải tệp broker hoàn chỉnh. Không tạo trùng một address/queue đã có; nếu muốn queue `lab.cli.ping` cũng khai báo tĩnh thì thêm cấu hình riêng đúng tên.

Trong một broker dành cho lab, có thể cho phép tự tạo tại address setting phù hợp:

~~~xml
<!-- Chèn vào <address-settings> hiện hữu, hợp nhất với rule cùng match nếu có. -->
<address-setting match="lab.#">
    <auto-create-addresses>true</auto-create-addresses>
    <auto-create-queues>true</auto-create-queues>
</address-setting>
~~~

Rule `lab.#` áp dụng cho tên như `lab.cli.ping` và `lab.java.ping` theo wildcard Artemis. **Quyền bảo mật** vẫn có thể ngăn user tạo queue/address; đừng giải quyết bằng cách tắt xác thực. Nếu cấu hình đang có một rule cùng match, hãy hợp nhất lựa chọn thay vì thêm bản trùng mâu thuẫn. Việc reload/restart cấu hình phụ thuộc loại setting và phiên bản.

Bạn **không cần sửa broker.xml để hoàn thành bài** nếu image mặc định đã tự tạo queue và account có quyền gửi/nhận.

## 9. Thử lỗi có chủ đích và hiểu acknowledgment

Để phân biệt các dạng lỗi, thay đổi **một yếu tố mỗi lần** rồi hoàn nguyên:

1. Thử Java kết nối sai cổng (`tcp://localhost:61626` khi cổng này không được map) → kỳ vọng lỗi kết nối/timeout.
2. Thử mật khẩu sai → TCP có thể kết nối nhưng broker từ chối xác thực.
3. Thử queue sai tên → producer và consumer có thể cùng kết nối broker nhưng không nhìn thấy cùng một message.
4. Chạy consumer hai lần sau một lần gửi → lần hai timeout, vì message đã được nhận/ack.
5. Nếu có thể, dùng console kiểm tra quyền user và lỗi ở broker log khi access bị từ chối.

### 9.1. Restart broker để quan sát persistence

Gửi **một** message bằng Java producer và **chưa nhận**. Dừng rồi chạy lại **cùng container**:

~~~powershell
docker stop amq-lab
docker start amq-lab
docker logs --tail 60 amq-lab
~~~

Khi broker hoạt động trở lại, chạy Java consumer. Với message persistent và store hoạt động bình thường, bạn kỳ vọng vẫn nhận được cùng message.

Phép thử này kiểm chứng **stop/start cùng container**. Nó không chứng minh phục hồi sau mất đĩa, mất host, failover hay xóa container; `docker rm` và tạo container khác có thể mất journal nếu không dùng volume bền vững. Production cần storage/backup/replication và kiểm thử RPO/RTO riêng.

### 9.2. JMS transaction khác auto-ack thế nào?

Một consumer làm việc với database không nên giả định auto-ack nghĩa là “đã xử lý nghiệp vụ”. Ví dụ đoạn xử lý **transacted JMS session**:

~~~java
// Chỉ minh họa logic; processBusiness là hàm do ứng dụng tự triển khai.
try (JMSContext tx = factory.createContext(
        USER, PASSWORD, JMSContext.SESSION_TRANSACTED)) {
    JMSConsumer consumer =
            tx.createConsumer(tx.createQueue("lab.java.ping"));
    Message message = consumer.receive(5000);

    if (message != null) {
        try {
            String body = message.getBody(String.class);
            processBusiness(body); // Xử lý nghiệp vụ thành công rồi mới commit
            tx.commit();
        } catch (Exception e) {
            tx.rollback();        // Cho phép redelivery theo broker policy
            throw e;
        }
    }
}
~~~

**Transaction JMS không đồng nhất với transaction database.** Nếu database commit rồi consumer chết trước JMS commit, broker có thể giao lại cùng message. Cách thiết kế an toàn là consumer **idempotent** theo `eventId` (ví dụ unique constraint và lưu dấu processed event trong cùng DB transaction); khi cần gửi message từ giao dịch DB, cân nhắc transactional outbox.

Cấu hình Artemis có thể quy định delay và giới hạn redelivery, định tuyến message lỗi sang **dead-letter address (DLQ)**. Ví dụ trích đoạn đặt trong address-setting đã có, sau khi bảo đảm address/queue DLQ được khai báo và quyền phù hợp:

~~~xml
<address-setting match="lab.#">
    <dead-letter-address>DLQ</dead-letter-address>
    <redelivery-delay>1000</redelivery-delay>
    <max-delivery-attempts>3</max-delivery-attempts>
</address-setting>
~~~

Không thêm đồng thời hai `address-setting` trùng `match` mà bỏ mặc các giá trị mâu thuẫn. Tùy phiên bản, broker và chính sách, retry/redelivery/DLQ có mặc định và hành vi khác nhau; cần kiểm tra cấu hình thực đang áp dụng. Đoạn XML chỉ giúp hiểu liên hệ giữa **rollback → giao lại → xử lý message lỗi**, không phải cấu hình bắt buộc của lab kết nối.

## 10. Nếu bạn đang chạy ActiveMQ Classic

Artemis và Classic đều hỗ trợ các bài toán queue/topic và tích hợp JMS, nhưng **không thể thay thế CLI hoặc dependency bằng cách đổi tên broker**:

| Chủ đề | ActiveMQ Artemis trong lab | ActiveMQ Classic |
|---|---|---|
| CLI | `artemis producer/consumer` trên instance | Không mặc nhiên có cùng subcommand; xem script và bộ công cụ của Classic đang dùng |
| Web console thường gặp | `/console` trên cổng 8161 | `/admin` trên cổng 8161 nếu web console Classic bật |
| Messaging port thường gặp | 61616 nếu acceptor đang nghe | 61616 cho OpenWire nếu connector được bật |
| Mã Java minh họa | `artemis-jakarta-client`, `jakarta.jms` | Classic 5.x thường dùng `activemq-client`, `javax.jms`; phải xác minh phiên bản cụ thể |
| Routing và cấu hình | Address/queue, ANYCAST/MULTICAST, Artemis `broker.xml` | Destination/policy và cơ chế cấu hình riêng của Classic |

Với Classic đã cài đặt, script `bin/activemq console` thường khởi động broker ở foreground trong các bản phân phối có hỗ trợ. Kiểm tra `http://localhost:8161/admin`, port OpenWire thực tế và user/password theo bản đang chạy. Không áp dụng trực tiếp lệnh `artemis producer` cho Classic.

Để thấy sự khác nhau về Java API, ví dụ tối thiểu với **ActiveMQ Classic 5.x và `javax.jms`** (cần dependency `org.apache.activemq:activemq-client` cùng hệ tương thích và broker đang chạy):

~~~java
import javax.jms.Connection;
import javax.jms.ConnectionFactory;
import javax.jms.Destination;
import javax.jms.MessageProducer;
import javax.jms.Session;
import org.apache.activemq.ActiveMQConnectionFactory;

ConnectionFactory factory =
        new ActiveMQConnectionFactory("tcp://localhost:61616");

Connection connection = factory.createConnection();
try {
    Session session =
            connection.createSession(false, Session.AUTO_ACKNOWLEDGE);
    Destination destination = session.createQueue("lab.classic.ping");
    MessageProducer producer = session.createProducer(destination);
    producer.send(session.createTextMessage("Ping Classic"));
    session.close();
} finally {
    connection.close();
}
~~~

Đây là đoạn so sánh API, **không nằm trong project Jakarta Maven của Artemis ở mục 6**. Ngoài namespace, cần kiểm tra wire protocol, version client, quyền truy cập và cách đóng resource. Không suy rằng mọi client JMS dùng chung được cho cả hai sản phẩm chỉ vì đều gửi tới 61616.

## 11. Troubleshooting theo từng lớp

| Triệu chứng | Cần kiểm tra | Hành động |
|---|---|---|
| Docker báo tên container đã tồn tại | Trạng thái container hiện hữu | `docker ps -a --filter name=amq-lab`; start đúng container nếu cần |
| Lỗi bind 61616/8161 | Cổng host bị chiếm | Đổi cổng host, cập nhật URL Java và browser |
| Console mở được, Java lỗi kết nối | HTTP 8161 và messaging 61616 là hai đường riêng | `docker port amq-lab`, log broker, URL client |
| Đăng nhập bị từ chối | Credential sai | Kiểm tra account và môi trường image |
| Đăng nhập được nhưng gửi bị từ chối | Thiếu quyền send/create trên destination | Kiểm tra role, security-setting, queue/address |
| Queue không xuất hiện | Auto-create tắt hoặc sai destination/routing | Khai báo đích ANYCAST, kiểm tra quyền |
| `ClassNotFoundException`, `NoClassDefFoundError` | Thiếu client/API hoặc trộn `javax` và `jakarta` | Kiểm tra Maven dependencies và Java import |
| Producer gửi thành công, consumer timeout | Khác URL/queue, queue đã bị consumer khác lấy, TTL hết | So sánh tên đích, log và chỉ số console |
| Sau khi nhận, message không còn | Ack thành công | Hành vi bình thường của queue |
| Message xuất hiện lại sau lỗi | Consumer chưa ack/JMS rollback | Kiểm tra redelivery policy, xử lý trùng, DLQ |
| Restart bằng container mới làm mất data | Journal chưa lưu ở volume | Kiểm tra store, volume và kế hoạch phục hồi |

Thứ tự cô lập lỗi hữu ích là **process/container → cổng → authentication → authorization → address/queue/routing → producer → consumer → acknowledgment**. Tránh thay cùng lúc nhiều tầng cấu hình.

## 12. Checklist nghiệm thu và tự kiểm tra

- [ ] Broker chạy, port 61616 và 8161 map đúng.
- [ ] Mở console được và xác thực thành công.
- [ ] CLI gửi **3 message** vào `lab.cli.ping`; console thấy queue có message.
- [ ] CLI consumer nhận đủ **3 message**; message count sau ack giảm về 0.
- [ ] Java Maven build thành công với Jakarta JMS.
- [ ] Producer gửi **1 TextMessage persistent** cùng `eventId`.
- [ ] Consumer in đúng body, event ID và message ID đã gửi.
- [ ] Consumer timeout có kiểm soát khi queue trống.
- [ ] Giải thích được vì sao console OK vẫn không bảo đảm JMS TCP OK.
- [ ] Giải thích được vì sao auto-ack chưa bảo đảm công việc database hoàn tất.

**Câu hỏi 1.** Vì sao consumer chạy lần hai không nhận lại message đã xử lý?  
Vì message đã được ack, queue không hoạt động như log lịch sử cho phép replay tùy ý. Khi không có redelivery hoặc message mới, consumer sẽ timeout.

**Câu hỏi 2.** Vì sao một queue có hai consumer không bảo đảm mỗi consumer đều nhận đủ ba message?  
Vì đó là nhóm consumer cạnh tranh lấy việc; không phải hai subscription độc lập. Muốn gửi một bản cho từng nhóm cần topic/subscription hoặc routing multicast.

**Câu hỏi 3.** Vì sao gửi persistent rồi restart thành công vẫn chưa thể kết luận broker bảo đảm không mất dữ liệu?  
Vì còn phụ thuộc filesystem, flush/journal, replication, volume, failover, backup và loại sự cố. Test stop/start một container chỉ kiểm tra một failure mode.

**Câu hỏi 4.** Nếu nghiệp vụ đã ghi DB nhưng chưa JMS ack mà consumer chết, cần làm gì khi message giao lại?  
Kiểm tra và ngăn xử lý trùng bằng khóa idempotency như `eventId`, commit tác dụng nghiệp vụ một lần rồi ack/commit JMS.

**Kết quả bài học:** bạn đã kiểm thử đường đi `producer → Artemis queue → consumer` bằng CLI và Java, đồng thời quan sát queue trên console. Đây là nền để thực hành topic/routing, JMS transaction, redelivery, DLQ và giám sát hoạt động broker trong các bài tiếp theo.
