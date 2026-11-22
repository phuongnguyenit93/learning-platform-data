# Core protocol và lựa chọn Core client của Artemis

> **Chương:** Giao thức kết nối  
> **Học phần:** `INTEGRATION_MESSAGING_MESSAGE_BROKER_ACTIVEMQ` — Apache ActiveMQ Classic và Artemis, queue/topic/routing, JMS, producer/consumer Java, acknowledgment, transaction, redelivery, DLQ, bảo mật và vận hành broker.  
> **Trọng tâm:** Giao thức **Core của ActiveMQ Artemis**, API Java Core và những tiêu chí để chọn Core client thay vì JMS hoặc client AMQP. Ví dụ sử dụng **Artemis 2.40.0** làm mốc minh họa; cần kiểm tra tính tương thích nếu triển khai phiên bản khác.

## 1. Bài toán lựa chọn: “Core” là gì trong một kết nối Artemis?

Hãy xét dịch vụ Java chuyên xử lý lệnh tạo vận đơn. Broker Artemis đã có address `shipping.commands` và queue `shipping.commands`; dịch vụ gửi message persistent, một worker nhận, xử lý và chỉ xác nhận sau khi commit dữ liệu nghiệp vụ. Nhóm phát triển muốn điều khiển trực tiếp việc gửi, nhận, buffer, acknowledgment và khôi phục kết nối.

Có ba khái niệm thường bị đánh đồng:

- **Core protocol**: giao thức nhị phân riêng của **ActiveMQ Artemis** giữa client phù hợp và broker; mang các thao tác như tạo session, gửi message, nhận message, acknowledge và quản lý tài nguyên.
- **Core client API**: tập interface/class Java thuộc `org.apache.activemq.artemis.api.core.*` để lập trình trực tiếp các khái niệm Core như `ServerLocator`, `ClientSession`, `ClientProducer`, `ClientConsumer` và `ClientMessage`.
- **JMS (Java/Jakarta Message Service)**: API chuẩn ở tầng ứng dụng Java. Một **Artemis JMS client** có thể dùng Core protocol ở phía dưới, trong khi một JMS provider khác, chẳng hạn Qpid JMS, dùng **AMQP 1.0**. Từ “JMS” không xác định giao thức wire.

Còn **Netty/TCP** là tầng vận chuyển kết nối. Chuỗi `tcp://host:61616` cho biết transport/endpoint, **không tự chứng minh** broker đang nhận gói Core, AMQP hay OpenWire.

~~~mermaid
flowchart TD
    A["Java application"] --> B{"Chọn API/client"}
    B --> C["Artemis Core API\nartemis-core-client"]
    B --> D["Artemis JMS API\nartemis-jakarta-client hoặc artemis-jms-client"]
    B --> E["AMQP 1.0 client\nví dụ Qpid JMS"]
    C --> F["Artemis Core wire protocol"]
    D --> F
    E --> G["AMQP 1.0 wire protocol"]
    F --> H["Netty TCP/TLS hoặc InVM (nếu đồng JVM)"]
    G --> I["TCP/TLS"]
    H --> J[["Artemis acceptor có CORE"]]
    I --> K[["Artemis acceptor có AMQP"]]
~~~

**Ý nghĩa thiết kế:** dùng Core client khi thực sự cần mô hình và tính năng riêng của Artemis, đồng thời kiểm soát được việc phụ thuộc vào client/broker Artemis. Nếu chỉ cần queue/topic theo API phổ biến, việc chọn JMS thường giảm mức phụ thuộc vào Core API. Nếu cần nhiều ngôn ngữ, broker khác nhau hoặc hợp đồng giao thức chuẩn, cân nhắc AMQP 1.0.

## 2. Giao thức, API và transport: phân định bằng ví dụ

| Câu hỏi | Core client | Artemis JMS client | AMQP 1.0 client |
|---|---|---|---|
| Ứng dụng Java lập trình theo interface nào? | `ClientSession`, `ClientProducer`, `ClientConsumer`, `ClientMessage` | `jakarta.jms` hoặc `javax.jms` theo bản client | API riêng hoặc JMS của một AMQP provider |
| Thư viện đại diện | `org.apache.activemq:artemis-core-client` | `artemis-jakarta-client` / `artemis-jms-client` phù hợp API | Ví dụ Qpid JMS hoặc AMQP client khác |
| Wire protocol thường dùng | **Artemis Core** | **Artemis Core** đối với Artemis JMS native client | **AMQP 1.0** |
| Đích khi gửi | **Address** | JMS `Queue` / `Topic` được provider ánh xạ vào address/queue | Node/address theo mô hình AMQP và cấu hình broker |
| Đích khi tiêu thụ | **Queue** được tạo/gắn vào address | JMS consumer của queue/topic hoặc subscription | Receiver/link tới node được khai báo |
| Điều khiển riêng của Artemis | Trực tiếp và chi tiết | Qua JMS abstraction và các tùy chọn provider | Phụ thuộc các khả năng AMQP/provider |
| Tính di động mã nguồn | Gắn chặt Artemis Core API | JMS có tính di động cao hơn ở tầng API; extension vẫn có thể phụ thuộc provider | Giao thức chuẩn hơn cho các hệ có hỗ trợ AMQP 1.0 |
| Thích hợp khi | Dịch vụ Java gắn với Artemis, cần hành vi/điều khiển Core | Ứng dụng Java muốn lập trình JMS | Tích hợp đa ngôn ngữ, liên thông hệ sinh thái AMQP |

**ActiveMQ Classic không nói Core protocol của Artemis.** Classic truyền thống dùng **OpenWire** với client Classic, dù Artemis có thể có acceptor hỗ trợ OpenWire để phục vụ một số client. Một cổng TCP dùng số `61616` không làm hai giao thức giống nhau. AMQP 1.0 cũng **khác AMQP 0-9-1** thường gặp ở RabbitMQ.

### 2.1. Core protocol hỗ trợ những thao tác nào?

Ở góc nhìn Core client, một cuộc trao đổi điển hình:

1. `ServerLocator` biết các endpoint/transport cấu hình để tìm broker.
2. `ClientSessionFactory` tạo session factory kết nối đến broker phù hợp.
3. `ClientSession` đại diện một phiên làm việc, có cấu hình xác thực, auto-commit và acknowledgment.
4. `ClientProducer` gửi `ClientMessage` đến **address**; broker route đến queue theo cấu hình.
5. `ClientConsumer` đăng ký nhận từ **queue**; session phải được `start()` để bắt đầu delivery.
6. Khi xử lý xong, ứng dụng `acknowledge()` và nếu dùng transaction thì `commit()`; nếu lỗi có thể `rollback()`.

Đây là **ngữ nghĩa API Core**. Không nên dựa vào tên method để đoán chính xác từng packet trên wire hoặc timing gửi packet: Core client có thể gộp/batch acknowledgment và sử dụng cơ chế flow control theo configuration.

### 2.2. Transport và phạm vi triển khai

Core client thường kết nối đến broker từ xa qua **Netty TCP** (có thể bật TLS). Khi client và broker ở cùng JVM, Artemis còn có **InVM transport** trong những mô hình nhúng/phù hợp. InVM là transport nội bộ quá trình, **không** phải một cổng TCP có thể truy cập qua mạng; code ví dụ trong bài dùng Netty để phù hợp dịch vụ tách tiến trình.

Phải tách rõ:

- **Acceptor** nằm ở broker, **lắng nghe kết nối vào**, ví dụ `0.0.0.0:61617` với `protocols=CORE`.
- **TransportConfiguration/connector phía client** cung cấp địa chỉ broker và Netty connector factory để tạo **kết nối đi ra**.
- `<connector>` trong `broker.xml` thường là một **định nghĩa endpoint kết nối đi** phục vụ broker/cluster/bridge; khai báo nó không tự mở port lắng nghe.
- **Firewall, container port mapping, TLS và xác thực** vẫn phải phù hợp mới tạo được kết nối sử dụng Core.

## 3. Khi nào thực sự nên chọn Core client?

### 3.1. Tiêu chí chọn

**Core client là ứng viên tốt** nếu thỏa phần lớn điều kiện sau:

- Dịch vụ viết bằng Java và **broker là Artemis** được kiểm soát trong dài hạn; không có yêu cầu đổi provider JMS.
- Muốn thao tác trực tiếp `address`, `queue`, `routing type`, `ClientSession`, `ClientMessage` và các cấu hình flow control/acknowledgment riêng của Artemis.
- Đội ngũ hiểu lifecycle của Core session, callback/consumer, transaction, retry và cấu hình broker; sẵn sàng kiểm thử khi nâng phiên bản.
- Cần cấu hình/quan sát trực tiếp một số chi tiết Core hơn là ánh xạ chúng sang JMS destination và provider properties.
- Có thể chuẩn hóa một version client/broker, thiết lập quyền, TLS, HA và vận hành tương ứng.

**Ưu tiên JMS** khi yêu cầu ứng dụng chỉ gồm `send`, `receive`, selector, acknowledgment/transaction theo contract JMS thông dụng; framework đã tích hợp Spring JMS/Jakarta Messaging hoặc khả năng thay provider quan trọng. Artemis JMS native vẫn có thể dùng **Core protocol dưới lớp JMS**, nên không phải “JMS = giao thức khác”.

**Ưu tiên AMQP 1.0** khi cần client đa ngôn ngữ/khác vendor giao tiếp qua một wire protocol được chuẩn hóa. Cần xác minh mapping address/queue, settlement/ack, outcome, transaction và các extension trong cụm công nghệ thật; “cùng AMQP” không có nghĩa hành vi tự động giống nhau.

### 3.2. Một quyết định thực tế

| Yêu cầu dự án | Nên thử trước | Lý do |
|---|---|---|
| Worker Java chỉ gửi/nhận queue, đã dùng Jakarta JMS/Spring JMS | Artemis JMS client | API quen thuộc, framework hỗ trợ, vẫn đi được qua Core wire |
| Worker Java tự quản lý Core `ClientSession`, ack batching, consumer credit và QueueConfiguration | Artemis Core client | Điều khiển trực tiếp bằng mô hình native của Artemis |
| Microservice Node.js/Python và Java giao tiếp chung qua giao thức chuẩn | AMQP 1.0 client | API theo ngôn ngữ, wire protocol chung khi broker hỗ trợ |
| Ứng dụng hiện tại dùng `org.apache.activemq.ActiveMQConnectionFactory` của Classic 5.x | Đánh giá tương thích OpenWire/đường chuyển đổi | Không thay client Classic bằng Core client chỉ bằng cách sửa URL |
| Dự án muốn khả năng thay đổi broker mà ít chỉnh business code | JMS hoặc giao thức chuẩn, hạn chế extension | Giảm khóa chặt theo Artemis Core API |
| Đọc lại lịch sử sự kiện theo offset nhiều ngày và consumer group độc lập | Xem hệ event log phù hợp | Queue Core tiêu thụ/ack không tự trở thành event log replay |

**Không chọn Core chỉ vì “Core chắc chắn nhanh nhất”.** Benchmark phải cố định độ bền message, xác nhận gửi, batch/credit, kích thước payload, số producer/consumer, cấu hình broker và chỉ số đuôi phân phối độ trễ. Chênh lệch trong một benchmark không bảo đảm kết quả của hệ thống thật.

## 4. Cấu hình broker để chỉ nhận Core trên một acceptor

Ví dụ sử dụng ActiveMQ Artemis **2.40.0** với broker instance đã được tạo và khởi động được. Trong `broker.xml`, dưới phần tử `<acceptors>` **đã có**, có thể thêm một acceptor riêng cho lab:

~~~xml
<!-- Trích đoạn bên trong <acceptors> hiện hữu. -->
<acceptor name="core-lab">tcp://0.0.0.0:61617?protocols=CORE</acceptor>
~~~

Phân tích:

- `tcp://0.0.0.0:61617`: broker bind vào mọi network interface của môi trường broker trên port **61617**.
- `protocols=CORE`: trên **acceptor này** chỉ nhận Core protocol (theo danh sách protocol của broker).
- `core-lab` là tên acceptor để phân biệt trong cấu hình/log, không phải tên queue.
- Không có yêu cầu mọi Core connection phải đi qua 61617. Nhiều bản Artemis sử dụng acceptor **đa giao thức** trên **61616** (có thể cho Core, AMQP, OpenWire, MQTT hoặc STOMP tùy cấu hình). Protocol phụ thuộc cấu hình acceptor, **không** phụ thuộc số port.

Đây là **mảnh XML**, không phải toàn bộ `broker.xml`. Chỉ thêm vào khối `<acceptors>` đang tồn tại, kiểm tra không trùng tên/cổng với acceptor khác, và khởi động lại broker khi loại thay đổi yêu cầu. Nếu bạn chạy broker trong Docker, map port từ container ra host tương ứng, chẳng hạn **host 127.0.0.1:61617 → container 61617**; không nhầm `localhost` bên trong container với host.

Nếu chỉ thực hành trên một máy, nên giới hạn bằng firewall hoặc bind loopback thích hợp với topology. Ví dụ dùng `0.0.0.0` giúp thấy rõ yêu cầu network giữa các container/VM, **không** phải khuyến nghị công khai cổng broker ra Internet.

### 4.1. Tạo queue bền vững, chọn rõ ANYCAST

Trong Artemis, producer Core gửi tới **address**, còn consumer Core nhận từ **queue**. Mọi thứ sẽ khó kiểm chứng nếu dựa hoàn toàn vào auto-create mà không biết queue nào được tạo.

Ví dụ thêm **một address** bên trong `<addresses>` đã có:

~~~xml
<address name="lab.core.jobs">
    <anycast>
        <queue name="lab.core.jobs"/>
    </anycast>
</address>
~~~

Với bài lab:

- **Address:** `lab.core.jobs`, nhận message Core từ producer.
- **Queue:** `lab.core.jobs`, chứa message cho consumer.
- **Routing:** **ANYCAST**, phù hợp work queue: khi có nhiều worker trên cùng queue, message sẽ được phân phối tới consumer theo dispatch của broker, không phát một bản cho mỗi worker.
- Queue được cấu hình trên broker trước, nên ví dụ Java không cần gọi `createQueue()` và không cần quyền **create durable queue** chỉ để phát/nhận.

Nếu muốn nhiều nhóm độc lập cùng nhận mỗi sự kiện, thiết kế các queue/subscription và **MULTICAST**; không gán nhầm rằng Core protocol tự quyết định routing. **Routing là cấu hình address/queue của Artemis**, không phải đặc tính “Core vs AMQP”.

### 4.2. Quyền trên address và queue

Cấu hình security phải cho **producer quyền send**, **consumer quyền consume**, và nếu tự tạo queue thì có quyền create tương ứng. Một đoạn cấu hình authorization minh họa, đặt vào `<security-settings>` hiện hữu và hợp nhất với rule trùng phạm vi:

~~~xml
<security-setting match="lab.core.#">
    <permission type="send" roles="lab-producer"/>
    <permission type="consume" roles="lab-consumer"/>
</security-setting>
~~~

Tên role chỉ là ví dụ; phải tồn tại trong cấu hình người dùng/role thật của broker. Để chạy demo cùng một credential cho gửi và nhận, tài khoản lab phải có **cả hai** role phù hợp. Trên môi trường thật, dùng user riêng cho từng nhiệm vụ là an toàn hơn. Nếu broker có security setting tổng quát hoặc quyền quản trị khác, kiểm tra cách rule cụ thể này được áp dụng trước khi chỉnh.

**Không bật/tắt quyền chỉ vì lỗi kết nối TCP**. Lỗi TCP, authentication và authorization là ba lớp cần chẩn đoán riêng.

## 5. Java Core API: từ TransportConfiguration đến message

Đây là ví dụ **native Core client**, không import JMS. Mẫu dùng Netty connector đến acceptor `CORE` tại `127.0.0.1:61617`.

### 5.1. Project Maven

Cấu trúc dự án:

~~~text
artemis-core-lab/
├── pom.xml
└── src/
    └── main/java/lab/CoreClientDemo.java
~~~

Nội dung `pom.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>lab</groupId>
    <artifactId>artemis-core-lab</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.apache.activemq</groupId>
            <artifactId>artemis-core-client</artifactId>
            <version>2.40.0</version>
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

**Dependency đúng là `artemis-core-client`.** Không sử dụng `artemis-jakarta-client` làm thay thế khi muốn lập trình trực tiếp bằng `ClientSession`. Không import `javax.jms` hoặc `jakarta.jms` trong lớp ví dụ này.

### 5.2. Producer/consumer dùng chung phần tạo session

Tạo `src/main/java/lab/CoreClientDemo.java`:

~~~java
package lab;

import java.util.HashMap;
import java.util.Map;
import java.util.UUID;

import org.apache.activemq.artemis.api.core.TransportConfiguration;
import org.apache.activemq.artemis.api.core.client.ActiveMQClient;
import org.apache.activemq.artemis.api.core.client.ClientConsumer;
import org.apache.activemq.artemis.api.core.client.ClientMessage;
import org.apache.activemq.artemis.api.core.client.ClientProducer;
import org.apache.activemq.artemis.api.core.client.ClientSession;
import org.apache.activemq.artemis.api.core.client.ClientSessionFactory;
import org.apache.activemq.artemis.api.core.client.ServerLocator;
import org.apache.activemq.artemis.core.remoting.impl.netty.NettyConnectorFactory;
import org.apache.activemq.artemis.core.remoting.impl.netty.TransportConstants;

public final class CoreClientDemo {

    // Cấu hình trên broker.xml: address và queue trùng tên trong lab.
    private static final String ADDRESS = "lab.core.jobs";
    private static final String QUEUE = "lab.core.jobs";

    private CoreClientDemo() {}

    public static void main(String[] args) throws Exception {
        if (args.length == 0
                || (!"send".equals(args[0]) && !"receive".equals(args[0]))) {
            throw new IllegalArgumentException(
                    "Cách dùng: send [noi-dung] hoặc receive");
        }

        String user = requiredEnv("CORE_USER");
        String password = requiredEnv("CORE_PASSWORD");
        String host = System.getenv().getOrDefault(
                "CORE_HOST", "127.0.0.1");
        int port = Integer.parseInt(System.getenv().getOrDefault(
                "CORE_PORT", "61617"));

        Map<String, Object> connectorParams = new HashMap<>();
        connectorParams.put(TransportConstants.HOST_PROP_NAME, host);
        connectorParams.put(TransportConstants.PORT_PROP_NAME, port);

        // NettyConnectorFactory tạo transport phía client.
        TransportConfiguration connector = new TransportConfiguration(
                NettyConnectorFactory.class.getName(), connectorParams);

        // Không dùng HA trong lab một broker. Không suy ra HA chỉ từ retry.
        try (ServerLocator locator =
                     ActiveMQClient.createServerLocatorWithoutHA(connector)) {

            // Giá trị minh họa, cần cân chỉnh theo SLA thật.
            locator.setInitialConnectAttempts(2);
            locator.setReconnectAttempts(3);
            locator.setRetryInterval(1000);

            try (ClientSessionFactory factory = locator.createSessionFactory();
                 ClientSession session = factory.createSession(
                         user, password,
                         false,  // xa: không dùng XA
                         true,   // autoCommitSends
                         false,  // autoCommitAcks: ACK cần commit
                         false,  // preAcknowledge: tắt
                         0)) {  // ackBatchSize: 0, không gom ACK

                if ("send".equals(args[0])) {
                    String payload = args.length >= 2
                            ? args[1]
                            : "ship-" + UUID.randomUUID();
                    sendOne(session, payload);
                } else {
                    receiveOne(session);
                }
            }
        }
    }

    private static String requiredEnv(String key) {
        String value = System.getenv(key);
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(
                    "Chưa đặt biến môi trường: " + key);
        }
        return value;
    }

    private static void sendOne(ClientSession session, String body)
            throws Exception {
        ClientProducer producer = session.createProducer(ADDRESS);
        try {
            // true: durable message; cần broker/store cấu hình phù hợp.
            ClientMessage message = session.createMessage(true);
            message.getBodyBuffer().writeString(body);

            producer.send(message);
            System.out.println("SENT address=" + ADDRESS);
            System.out.println("body=" + body);
        } finally {
            producer.close();
        }
    }

    private static void receiveOne(ClientSession session) throws Exception {
        ClientConsumer consumer = session.createConsumer(QUEUE);
        try {
            // Core session cần start() để broker bắt đầu delivery.
            session.start();

            ClientMessage message = consumer.receive(5000);
            if (message == null) {
                System.out.println("TIMEOUT: không có message trong 5 giây");
                return;
            }

            String body = message.getBodyBuffer().readString();
            System.out.println("RECEIVED queue=" + QUEUE);
            System.out.println("body=" + body);

            // Chỉ ACK sau khi xử lý đã thành công.
            message.acknowledge();
            session.commit(); // Commit ACK vì autoCommitAcks=false.
            System.out.println("ACK_COMMITTED");
        } finally {
            consumer.close();
        }
    }
}
~~~

### 5.3. Chạy và quan sát

Trong phiên PowerShell dành cho lab, dùng user/password đã được cấu hình ở broker:

~~~powershell
$env:CORE_USER = "lab"
$env:CORE_PASSWORD = "mat-khau-cua-lab"
$env:CORE_HOST = "127.0.0.1"
$env:CORE_PORT = "61617"
~~~

Ở ví dụ, tài khoản phải có quyền `send` và `consume` trên address/queue của lab. Không lưu mật khẩu này vào Git hoặc log ứng dụng. Với Bash, thay cú pháp đặt biến môi trường tương ứng.

Biên dịch và gửi một message:

~~~powershell
mvn -q -DskipTests package
mvn -q exec:java "-Dexec.mainClass=lab.CoreClientDemo" "-Dexec.args=send hello-core"
~~~

Kỳ vọng:

~~~text
SENT address=lab.core.jobs
body=hello-core
~~~

Nếu có web console/management API, kiểm tra queue `lab.core.jobs` đang có **một message chờ** trước khi chạy consumer. Sau đó:

~~~powershell
mvn -q exec:java "-Dexec.mainClass=lab.CoreClientDemo" "-Dexec.args=receive"
~~~

Kỳ vọng:

~~~text
RECEIVED queue=lab.core.jobs
body=hello-core
ACK_COMMITTED
~~~

Chạy `receive` lần hai khi không có producer khác: sau khoảng 5 giây, in `TIMEOUT`. Như vậy bạn đã xác minh cả **gửi vào address**, **routing ANYCAST đến queue**, **nhận bằng Core client**, và **acknowledgment được commit**.

Nếu broker chỉ mở acceptor đa giao thức ở `61616`, có thể đổi `CORE_PORT=61616` **nếu acceptor đó thực sự cho phép CORE**. Đừng suy ra từ cổng số hoặc trang web console rằng Core đã được bật.

## 6. Giải thích sâu các đối tượng Core và lỗi cấu hình hay gặp

### 6.1. `ServerLocator` khác `ClientSessionFactory`

`ServerLocator` chứa thông tin để tìm một hoặc nhiều broker endpoint và một số chính sách kết nối/retry. Từ locator, ứng dụng tạo `ClientSessionFactory` — điểm tạo các session. Một factory có thể phục vụ nhiều session; mỗi session chứa trạng thái của gửi, nhận, transaction và acknowledgment.

- Không tạo mới locator/factory **cho mỗi message** trong ứng dụng production: việc thiết lập connection và cleanup liên tục gây chi phí không cần thiết.
- Không dùng **cùng một `ClientSession` đồng thời từ nhiều luồng** nếu không có hợp đồng hỗ trợ rõ ràng; mô hình Core session nhìn chung được dùng theo luồng hoặc quản lý tuần tự. Mỗi worker có thể giữ session riêng.
- Thời điểm khởi tạo kết nối có thể là `locator.createSessionFactory()` / `factory.createSession()`, tùy transport và client. Nếu chương trình báo lỗi tại đây, chưa phải lỗi consume.
- Đóng các resource theo thứ tự phù hợp. `try-with-resources` trong ví dụ đóng session, factory rồi locator ngay cả khi exception xảy ra.

### 6.2. Producer gửi **address**, consumer nhận **queue**

Đây là khác biệt quan trọng nhất khi lập trình Core trực tiếp.

~~~text
ClientProducer.send(address = lab.core.jobs)
                  |
                  v
           [Artemis address]
                  |
        routing type = ANYCAST
                  |
                  v
         [Queue lab.core.jobs]
                  |
                  v
ClientConsumer.createConsumer(queue = lab.core.jobs)
~~~

Một address có thể có nhiều queue; routing quyết định message nào đi vào queue nào. Vì ví dụ chọn tên address và queue giống nhau, dễ bỏ qua khác biệt này. Trong sản xuất chúng có thể có tên **khác nhau** — producer vẫn gửi address, consumer vẫn đăng ký queue.

Nếu **address có thật nhưng không route tới queue phù hợp**, send có thể thành công theo cấu hình trong khi consumer không có message để nhận. Phải xem address routing, queue binding, auto-create policy, filter, expiry và cách xử lý message không route được; không tự kết luận client lỗi.

### 6.3. Durable message khác durable queue

- `session.createMessage(true)` tạo **durable message** ở tầng Core API.
- Queue trên broker phải có cấu hình **durable** và storage/persistence phù hợp; message durability không tự bù cho một queue tạm thời hoặc một cấu hình broker không lưu bền.
- Xác nhận gửi thành công không thay thế **replication, backup, journal verification và kiểm thử sự cố**.
- `acknowledge()` không đồng nghĩa “business transaction thành công”; nó đánh dấu tiến trình nhận tại broker/session. Vì ví dụ cấu hình `autoCommitAcks=false`, cần `session.commit()` để commit ACK.

Bài thực hành xác nhận đường kết nối và thao tác đơn giản, chưa hứa dữ liệu có thể sống sót qua mọi loại lỗi host/disk.

## 7. ACK, transaction và tình huống connection bị đứt

### 7.1. Đọc đúng các cờ `createSession`

Trong lời gọi:

~~~java
ClientSession session = factory.createSession(
    user, password,
    false, // xa
    true,  // autoCommitSends
    false, // autoCommitAcks
    false, // preAcknowledge
    0      // ackBatchSize
);
~~~

| Tham số | Vai trò trong lab | Khi thay đổi có hậu quả gì? |
|---|---|---|
| `xa=false` | Session không tham gia XA | XA chỉ cần cho mô hình phối hợp transaction hỗ trợ tương ứng; phức tạp hơn |
| `autoCommitSends=true` | Gửi message không chờ một lệnh session commit của ứng dụng | Nếu `false`, các send thuộc transaction và cần `commit()`; `rollback()` loại bỏ send chưa commit |
| `autoCommitAcks=false` | ACK sau khi xử lý phải được commit | Nếu `true`, ACK có thể được commit tự động theo cơ chế Core |
| `preAcknowledge=false` | Không ack trước khi ứng dụng nhận | Bật pre-ack có thể làm message mất khả năng redelivery nếu consumer chết trước khi xử lý |
| `ackBatchSize=0` | Không gom ACK theo kích thước buffer trong ví dụ | Batching có thể cải thiện throughput nhưng tăng phức tạp khi quan sát thời điểm ack |

**Core `preAcknowledge` cần đặc biệt thận trọng.** Nó dành cho những trường hợp chấp nhận rủi ro mất xử lý để giảm overhead. Không bật trong worker giao dịch quan trọng chỉ vì muốn tăng thông lượng.

### 7.2. Producer không biết chắc kết quả sau timeout

Giả sử producer gửi durable message, broker nhận và ghi vào store, nhưng đường mạng đứt **trước khi client nhận được phản hồi**. Producer có thể thấy exception/timeout dù broker đã có message.

~~~text
Producer                Broker
   |   send(M)             |
   |---------------------->|
   |                       | persisted M
   |     acknowledgment    |
   X<----------------------|  (mạng lỗi)
   |
   | retry(M)  --->  có thể tạo bản M thứ hai
~~~

Vì vậy **retry gửi không mặc nhiên là exactly-once**. Dùng `eventId` ổn định do ứng dụng tạo (khác biệt với ID do provider tự cấp), transactional outbox khi kết hợp database và consumer idempotent. Phải xác định rõ “send thành công” nghĩa là client nhận confirmation, broker lưu local hay replication đã đảm bảo theo RPO cụ thể.

### 7.3. Consumer đã làm xong nhưng chưa commit ACK

Nếu worker ghi DB xong rồi chết trước `session.commit()`, broker có thể redeliver message. Một consumer thực tế cần:

1. Đọc `eventId` hoặc khóa nghiệp vụ ổn định.
2. Trong DB transaction, kiểm tra khóa đã xử lý chưa và ghi nghiệp vụ cùng dấu dedup.
3. Chỉ sau khi DB commit thành công mới `acknowledge()` và `session.commit()`.
4. Nếu lỗi, `rollback()` session khi còn kết nối hoặc để broker thực hiện redelivery theo policy sau khi session mất.

**Core transaction và DB transaction là hai transaction riêng biệt.** Sử dụng XA chỉ khi thực sự đáp ứng được các điều kiện resource manager và vận hành; với đa số worker, mô hình idempotent + outbox và xử lý at-least-once rõ ràng dễ kiểm soát hơn.

### 7.4. Redelivery và DLQ nằm ở đâu?

Core protocol mang các thao tác ACK/rollback; **chính sách redelivery, delivery attempts và dead-letter address** được xác định bởi Artemis broker configuration. Ví dụ một rule cho address lab:

~~~xml
<!-- Đặt vào <address-settings> có sẵn, hợp nhất với rule match trùng. -->
<address-setting match="lab.core.#">
    <dead-letter-address>DLQ</dead-letter-address>
    <max-delivery-attempts>5</max-delivery-attempts>
    <redelivery-delay>1000</redelivery-delay>
</address-setting>
~~~

Đoạn cấu hình minh họa: sau số lần giao thất bại, message có thể đi đến DLQ **nếu DLQ được cấu hình/tạo và cho phép routing phù hợp**. Đừng tạo nhiều `<address-setting>` cùng match với cấu hình mâu thuẫn. Không gán việc bật DLQ cho “chọn Core client”: JMS client dùng Core wire cũng chịu ảnh hưởng chính sách broker tương tự.

## 8. Connection lifecycle, flow control và failover

### 8.1. Retry không đồng nghĩa HA

Trong lab ta dùng:

~~~java
ServerLocator locator =
    ActiveMQClient.createServerLocatorWithoutHA(connector);
locator.setInitialConnectAttempts(2);
locator.setReconnectAttempts(3);
locator.setRetryInterval(1000);
~~~

- **Initial connection attempts** điều chỉnh nỗ lực kết nối ban đầu khi broker chưa sẵn sàng.
- **Reconnect attempts** điều chỉnh nỗ lực tái kết nối sau sự cố theo chính sách locator/client.
- **Retry interval** điều chỉnh khoảng đợi giữa các lần thử.

Những giá trị trên **không** tạo ra cluster hoặc broker dự phòng. HA yêu cầu cấu hình cluster/topology, replication/shared store hoặc cơ chế failover phù hợp. Khi dùng locator HA, client cần khám phá/tạo connection theo topology đã cấu hình, kiểm chứng phản ứng với lỗi thật thay vì chỉ thấy `createServerLocatorWithHA(...)` tồn tại.

Sau reconnect, vẫn cần xử lý **trạng thái không chắc chắn của send/ack**. Consumer có thể nhận lại, hoặc một send có thể đã được broker nhận trước khi lỗi mạng. Khả năng tự kết nối lại không thay thế idempotency.

### 8.2. Consumer credit / window và hiệu năng

Artemis Core client có các tham số liên quan flow control, ví dụ **consumer window size** và **producer window/confirmation window** ở những ngữ cảnh khác nhau. Chúng tác động đến lượng dữ liệu prefetch, credits và cách client/broker cân bằng tốc độ.

Ví dụ:

~~~java
// Tùy chọn hiệu năng để khảo sát trong phép thử tải,
// phải đặt trước khi tạo session factory/session.
locator.setConsumerWindowSize(1024 * 1024);
~~~

Điểm cần suy xét:

- Window lớn có thể tăng throughput khi network latency cao nhưng làm nhiều message nằm ở bộ đệm client, có thể giảm tính công bằng khi nhiều consumer cùng queue và tăng dùng RAM.
- Window nhỏ giảm lượng message prefetch nhưng có thể tăng trao đổi credit và giảm tốc độ tiêu thụ.
- Payload lớn cần xem thêm giới hạn message size, paging/large-message handling của broker và memory/disk.
- Không dùng mỗi `consumerWindowSize` làm biện pháp sửa backlog: cần đo enqueue rate, dequeue rate, queue depth, message age, GC và worker processing time.

Các giá trị tối ưu tùy phiên bản, latency, số consumer và kích thước message. Phải benchmark với độ bền và chế độ ACK giống production.

### 8.3. `ServerLocator` và thread safety

Đừng chia sẻ một `ClientSession` cho nhiều worker thread đồng thời rồi cho rằng mọi thao tác send, receive, commit sẽ độc lập. Session có trạng thái transaction/acknowledgment, do đó truy cập song song có thể tạo race condition hoặc trộn công việc.

Một pattern an toàn: **mỗi luồng consumer có session/consumer riêng**, dùng `ClientSessionFactory` được quản lý trong lifecycle ứng dụng; các session được đóng khi shutdown. Với producer throughput cao, thiết kế pooling/concurrency theo tài liệu client phiên bản đang dùng và thử tải. Tránh tạo/đóng session cho mỗi message nếu chi phí setup ảnh hưởng SLA.

## 9. TLS và bảo mật khi dùng Core qua mạng

Đây là giao thức mạng thực sự, vì vậy cần bảo vệ **transport, identity, authorization**.

- **TLS:** mã hóa đường truyền và xác thực broker bằng trust store/certificate validation. Nếu cấu hình mTLS, client còn phải cung cấp chứng chỉ client và broker phải kiểm tra chứng chỉ đó.
- **Broker credentials:** Core client cung cấp user/password khi tạo session. Không hardcode credential vào source, XML công khai, commit hoặc log.
- **Authorization:** giới hạn user theo address/queue và thao tác như send, consume, browse, create queue/addresses. Đừng cho consumer quyền tạo/xóa destination nếu không cần.
- **Network:** chỉ cho các host/container cần thiết truy cập Core acceptor. Nếu dùng Docker/Kubernetes, phối hợp listener bind, port mapping/service và network policy.
- **Operation:** đo authentication failures, số connection/session, tốc độ enqueue/dequeue, queue depth, memory/disk, failover và redelivery/DLQ.

### 9.1. Ví dụ cấu hình acceptor Core qua TLS

Ví dụ **trích đoạn khái niệm** trong `<acceptors>` của `broker.xml`:

~~~xml
<!-- Broker cần keystore thật và password lấy qua cơ chế secret phù hợp. -->
<acceptor name="core-tls">
    tcp://0.0.0.0:61618?protocols=CORE;sslEnabled=true;keyStorePath=/secrets/broker.p12;keyStorePassword=CHANGE_ME
</acceptor>
~~~

Các property URI trên là cấu hình server-side cho Netty acceptor; hãy kiểm tra version, keystore type và cách cấp secret trước khi áp dụng. **Không ghi password thật vào repository**. Việc bật `sslEnabled` chỉ ở broker chưa đủ: Core client cũng phải bật SSL trên connector và cấu hình trust store/certificate verification phù hợp.

Minh họa hướng bổ sung connector params phía client (không phải chương trình độc lập):

~~~java
connectorParams.put(TransportConstants.SSL_ENABLED_PROP_NAME, true);
connectorParams.put(TransportConstants.TRUSTSTORE_PATH_PROP_NAME,
                    "/path/to/client-truststore.p12");
connectorParams.put(TransportConstants.TRUSTSTORE_PASSWORD_PROP_NAME,
                    System.getenv("CORE_TRUSTSTORE_PASSWORD"));
~~~

Không sử dụng `trustAll=true` hoặc vô hiệu hóa hostname validation như một cấu hình production. Nếu cần mTLS, thêm keystore phía client theo đúng transport constants và broker's client-auth policy. Cần lưu ý `tcp://` vẫn có thể là URI transport của một **socket TLS** khi thuộc tính SSL được bật; chữ `tcp` tự nó không có nghĩa kênh chưa mã hóa.

## 10. Phân tích các lỗi Core connection thường gặp

| Biểu hiện | Kiểm tra tại broker | Kiểm tra tại client / hướng sửa |
|---|---|---|
| `Connection refused` | Port 61617 có acceptor thực sự bind không? Docker đã publish port chưa? | Host/port đúng không? Firewall/DNS/network namespace |
| TCP mở nhưng handshake thất bại | Acceptor có `protocols=CORE` không, hay chỉ AMQP/OpenWire? | Dùng **artemis-core-client** tới Core acceptor, đừng dùng client Classic/OpenWire để gửi Core |
| Xác thực thất bại | User/role và authentication configuration | `createSession(user,password,...)` có credential đúng chưa |
| Kết nối được, send bị từ chối | Quyền `send` của address | Kiểm tra security-setting theo tên **address** |
| Consumer bị từ chối | Quyền `consume` của queue / address và chính sách security | Kiểm tra role account, queue name đúng chưa |
| Send không lỗi, consumer không nhận | Address đã được bind đến queue ANYCAST chưa, queue có filter không? | Producer gửi **address**, consumer nhận **queue**; đừng nhầm hai tên |
| `receive(5000)` luôn timeout | Queue rỗng, consumer chưa `session.start()`, hoặc không route tới queue | Đối chiếu queue depth, session.start và queue đúng |
| Bị lỗi thiếu class `ClientSession` | Client artifact/version phù hợp không? | Thêm `artemis-core-client`, kiểm tra Maven dependency tree |
| Bị lỗi TLS certificate/handshake | Keystore server, TLS version/client-auth configuration | Trust store, hostname, certificate chain và thiết lập SSL phía client |
| Message xuất hiện lại sau lỗi worker | Ack chưa commit hoặc session bị rollback/đứt | Idempotency, transaction, redelivery policy và DLQ |
| Kết nối lại nhưng ứng dụng vẫn lỗi nghiệp vụ | Broker topology/HA, thông điệp chưa xác nhận đang ở trạng thái gì? | Kiểm tra lại trạng thái send/ack, tránh retry gây duplicate |
| Throughput thấp dù CPU còn dư | Paging, storage sync, flow control, message size, backlog | Đo consumerWindowSize, độ trễ network, ack/commit và worker processing |

### 10.1. Quy trình khoanh vùng cụ thể

1. **Transport:** broker có acceptor nghe port Core chưa? Host/port của Netty connector có map đúng mạng không?
2. **Protocol:** acceptor có `CORE` trong danh sách `protocols` chưa? Client có thực sự là Artemis Core client không?
3. **TLS:** broker và client có cùng chính sách mã hóa, trust chain và hostname validation không?
4. **Authentication:** session tạo được bằng user/password được cấp không?
5. **Authorization:** tài khoản có đủ quyền gửi address và nhận queue, nhưng không quá rộng?
6. **Routing:** address được gắn với queue thích hợp và routing ANYCAST/MULTICAST đúng?
7. **Delivery:** session đã `start()`, queue có message chờ/delivering, filter/expiry có tác động không?
8. **ACK/transaction:** message đã ack và commit theo đúng kế hoạch; có timeout hoặc redelivery không?
9. **Recovery:** sau broker restart/failover, những send/ack nào chưa xác nhận, dữ liệu có thể trùng/mất ở điểm nào?

Đừng đổi cùng lúc transport protocol, TLS, credentials và routing. Mỗi lần sửa nên xác minh lại đúng lớp đang lỗi bằng log broker và trạng thái message.

## 11. Bài thực hành suy luận cho người thiết kế hệ thống

### Tình huống A — Dịch vụ Core và JMS cùng gửi vào một queue

Một producer Java dùng `ClientProducer` của Core để gửi đến address `lab.core.jobs`; worker khác sử dụng Artemis **JMS native client** gửi/nhận JMS queue tương ứng. Có thể cùng hoạt động không?

**Có thể**, nếu cả hai client/broker tương thích, mapping JMS destination và Core address/queue phù hợp, quyền truy cập đúng và payload/property có cách giải mã thống nhất. JMS là API; với Artemis JMS native client, wire protocol có thể vẫn là Core. Tuy nhiên **định dạng body và properties** cần được thống nhất: một Core `writeString` không tự bảo đảm client JMS có thể gọi `getBody(String.class)` như với `TextMessage`; phải đặt rõ message type/encoding hoặc dùng hợp đồng trao đổi tương thích.

### Tình huống B — Core producer gửi thành công nhưng queue rỗng

Broker có address `events` với **MULTICAST** và không có queue phù hợp. Core producer gửi đến `events`, nhưng consumer `events.orders` chờ mãi.

**Lời giải:** cần xác minh queue binding và routing type. Producer gửi address, broker route theo queue được bind; không thể giả định cứ có address thì sẽ có queue theo tên bất kỳ.

### Tình huống C — Worker xử lý DB xong, connection chết trước ACK commit

Sau failover, worker nhận lại message. Đây có phải bug Core protocol?

**Không.** Đây là trường hợp at-least-once/redelivery và trạng thái commit không chắc chắn. Xử lý bằng `eventId` ổn định, transaction DB và idempotency; chỉ ACK khi đã hoàn tất. Nếu gửi message từ DB transaction, cân nhắc transactional outbox.

### Tình huống D — Nhóm chọn Core vì benchmark có số TPS lớn

Khi kiểm thử thật, quy mô tăng lên nhiều consumer và queue, có hiện tượng consumer nhanh giành sẵn nhiều message, một số worker ít việc.

**Lời giải:** đo consumer credits/window/prefetch, worker processing time, mức công bằng dispatch và topology, thay vì kết luận do protocol. Giảm window có thể cải thiện phân phối nhưng giảm throughput; cần benchmark trên SLA thật.

### Tình huống E — Dịch vụ Java có thể phải chuyển từ Artemis sang broker khác

Core client đã gắn sâu vào lớp nghiệp vụ, gọi thẳng `ClientSession` ở nhiều nơi. Việc đổi broker sẽ ảnh hưởng lớn đến code.

**Lời giải:** nếu tính di động quan trọng, cân nhắc JMS abstraction hoặc một hợp đồng giao thức chuẩn, đặt interface ứng dụng quanh việc gửi/nhận và giữ phần client-specific trong adapter. Chọn Core khi giá trị từ khả năng điều khiển trực tiếp của Artemis lớn hơn chi phí phụ thuộc.

## 12. Checklist lựa chọn và triển khai Core client

- [ ] Xác nhận nhu cầu thực sự cần **Core Java API**, không chỉ muốn “kết nối Artemis”.
- [ ] Chọn đúng artifact `artemis-core-client`, khớp Java/runtime và kiểm tra version client–broker.
- [ ] Có acceptor chứa `CORE`; hiểu số port không đại diện cho protocol.
- [ ] Client dùng Netty connector/TransportConfiguration đến đúng host/port hoặc InVM đúng topology.
- [ ] Quy định rõ **address để send** và **queue để consume**, routing type và queue durability.
- [ ] Cấp đúng role send/consume; chỉ bật auto-create nếu thực sự cần.
- [ ] Dùng TLS/trust store, quản lý secret và network ACL theo môi trường.
- [ ] Định nghĩa session lifecycle, thread ownership, acknowledgment và transaction.
- [ ] Có chiến lược idempotency, redelivery, DLQ và khôi phục khi timeout không rõ trạng thái.
- [ ] Kiểm thử reconnect/failover với HA broker được cấu hình thật nếu đó là yêu cầu.
- [ ] Đo flow control, consumer window, throughput, message age, queue depth và failure metrics.
- [ ] Nếu cần interoperable/multi-provider, đã so sánh cùng các lựa chọn JMS/AMQP.

**Kết luận:** Core protocol là giao thức nhị phân **của Artemis**; Core client là **một lựa chọn API Java** trực tiếp để thao tác với address, queue, session, producer/consumer, acknowledgment và kết nối. Chọn Core khi kiểm soát được phụ thuộc vào Artemis và cần các khả năng native của nó. Chọn Artemis JMS client khi JMS đủ đáp ứng và muốn giữ hợp đồng API JMS; chọn AMQP 1.0 khi ưu tiên tương tác đa ngôn ngữ bằng wire protocol chuẩn. Dù dùng Core, JMS hay AMQP, **độ bền, bảo mật, routing, retry và tính đúng đắn nghiệp vụ** vẫn phải được thiết kế và kiểm thử riêng.
