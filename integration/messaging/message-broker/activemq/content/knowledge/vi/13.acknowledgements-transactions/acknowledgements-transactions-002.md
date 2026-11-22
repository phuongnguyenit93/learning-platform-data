# CLIENT_ACKNOWLEDGE và phạm vi xác nhận trong cùng Session

> **Chương:** Xác nhận và giao dịch  
> **Học phần:** `INTEGRATION_MESSAGING_MESSAGE_BROKER_ACTIVEMQ` — ActiveMQ Classic và Artemis, queue/topic, định tuyến, producer/consumer Java, acknowledgment, transaction, redelivery, DLQ, bảo mật và vận hành broker tin cậy.  
> **Trọng tâm:** Ngữ nghĩa **`Session.CLIENT_ACKNOWLEDGE` theo JMS**, đặc biệt khi một `Session` có nhiều `MessageConsumer`. Ví dụ dùng **Apache ActiveMQ Artemis 2.40.0**, **Jakarta Messaging 3.1**, Java 17; nguyên tắc phạm vi xác nhận là của JMS và cũng áp dụng cho client JMS tương thích của ActiveMQ Classic.

## 1. Vấn đề thực tế: vì sao ACK message B lại có thể xác nhận cả message A?

Giả sử một dịch vụ Java dùng **một JMS Session** và tạo hai consumer:

- `consumerA` nhận yêu cầu kiểm tra thanh toán từ queue `lab.ack.payment`.
- `consumerB` nhận yêu cầu tạo vận đơn từ queue `lab.ack.shipping`.

Ứng dụng nhận message **A** nhưng chưa xử lý xong, sau đó nhận message **B** và gọi `messageB.acknowledge()`, nghĩ rằng chỉ B được xác nhận. Trong chế độ **`CLIENT_ACKNOWLEDGE`**, cách nghĩ đó sai.

**Quy tắc JMS:** Khi một client gọi `Message.acknowledge()` trên message đã tiêu thụ bằng Session có chế độ `CLIENT_ACKNOWLEDGE`, JMS xác nhận **toàn bộ message đã tiêu thụ trong cùng Session** mà chưa được xác nhận; thao tác không giới hạn ở message đã gọi phương thức, không giới hạn ở consumer đã nhận message ấy và không giới hạn ở một queue cụ thể.

~~~text
                             JMS Connection
                                    |
                             Session S  (CLIENT_ACKNOWLEDGE)
                              /                    \
                  Consumer A                        Consumer B
             queue lab.ack.payment              queue lab.ack.shipping
                     |                                |
               receive(A1)                      receive(B1)
               A1 chưa xử lý                       xử lý B1
                     |                                |
                     +---------- B1.acknowledge() ----+
                                    |
                          Session S xác nhận A1 và B1
~~~

Điểm nguy hiểm: nếu **A1 chưa hoàn tất nghiệp vụ**, sau khi B1 ACK thành công, broker có thể loại A1 khỏi trạng thái chờ xử lý. Process chết lúc này thì A1 **không còn được redeliver chỉ vì phần xử lý A1 chưa xong**. Đây là lỗi mất công việc do **phạm vi ACK sai**, không phải lỗi queue routing.

### Mục tiêu sau bài

Bạn có thể giải thích và thử nghiệm chính xác:

1. Phạm vi xác nhận theo **Session**, không theo `MessageConsumer`, queue hay một connection.
2. Một ACK xác nhận các message đã **được giao cho ứng dụng và tiêu thụ trong Session**, phân biệt với message mới chỉ nằm trong broker/client prefetch.
3. Hành vi của `Session.recover()` đối với message chưa ACK và sự khác nhau giữa recover, close và transaction rollback.
4. Cách tách Session hoặc dùng `SESSION_TRANSACTED` để xác định ranh giới nghiệp vụ an toàn.
5. Các điểm lỗi có thể dẫn đến xử lý trùng, mất message hoặc số liệu quan sát gây hiểu nhầm.

## 2. Phạm vi ACK: Session là ranh giới quan trọng

### 2.1. Một Session có thể chứa nhiều Consumer

Sơ đồ sau thể hiện bốn message được giao vào hai Session độc lập trong **cùng một Connection**:

~~~mermaid
flowchart TB
    CONN["JMS Connection C"]
    CONN --> S1["Session S1: CLIENT_ACKNOWLEDGE"]
    CONN --> S2["Session S2: CLIENT_ACKNOWLEDGE"]
    S1 --> CA["Consumer A"]
    S1 --> CB["Consumer B"]
    S2 --> CC["Consumer C"]
    CA --> A1["A1 consumed, unacked"]
    CB --> B1["B1 consumed, unacked"]
    CC --> C1["C1 consumed, unacked"]
    B1 --> ACK["B1.acknowledge()"]
    ACK --> X["ACK A1 và B1 (Session S1)"]
    ACK -. "không ACK" .-> C1
~~~

| Hoạt động | Message nào thuộc phạm vi xác nhận? |
|---|---|
| `A1.acknowledge()` trong `S1` | Các message đã tiêu thụ, chưa xác nhận trong **S1**, gồm cả từ consumer B của S1 |
| `B1.acknowledge()` trong `S1` | Cùng phạm vi **S1**, không riêng B1 |
| `C1.acknowledge()` trong `S2` | Các message đã tiêu thụ trong **S2**, không ảnh hưởng S1 |
| Hai Session nằm chung Connection | **Không** hợp nhất phạm vi ACK của hai Session |
| Hai consumer khác queue nhưng chung Session | **Không** tạo phạm vi ACK độc lập |
| Producer gửi vào queue cùng tên với consumer | Không thay đổi phạm vi ACK của consumer Session |

**Connection không phải ranh giới xác nhận cho `CLIENT_ACKNOWLEDGE`.** Một Connection có thể tạo nhiều Session; từng Session có trạng thái tiêu thụ, xác nhận và luồng thực thi riêng.

### 2.2. Một ví dụ theo thời gian

Giả sử S1 đã có hai consumer, lần lượt nhận:

~~~text
t0: Consumer A (S1) receive A1     -> unacked = {A1}
t1: Consumer B (S1) receive B1     -> unacked = {A1, B1}
t2: Consumer A (S1) receive A2     -> unacked = {A1, B1, A2}
t3: A1.acknowledge()              -> ACK {A1, B1, A2}
t4: Consumer B (S1) receive B2     -> unacked = {B2}
t5: B2.acknowledge()              -> ACK {B2}
~~~

Tại t3, bạn gọi `acknowledge()` trên **A1**, một message đã nhận sớm nhất. Tuy vậy điều kiện quan trọng là **Session đã tiêu thụ những message nào vào thời điểm xác nhận**, chứ không phải “mọi message có thứ tự trước A1”.

Trong một Session có callback `MessageListener`, các callback được provider **tuần tự hóa theo Session**; Session vẫn có thể chứa nhiều consumer khác nhau. Đừng suy ra rằng có hai listener ở hai consumer thuộc cùng một Session thì ACK được độc lập.

### 2.3. “Đã tiêu thụ” khác “đã prefetched”

Một broker như ActiveMQ có thể gửi sẵn nhiều message đến buffer phía client (prefetch/consumer window). **Không vì thấy broker đang báo delivering/in-flight mà mặc định toàn bộ đã nằm trong phạm vi `Message.acknowledge()` ở cấp ứng dụng.**

Ngữ nghĩa JMS cần phân biệt:

- **Queued tại broker:** chưa được ứng dụng nhận.
- **Prefetched/đang nằm trong buffer của provider:** có thể đang in-flight từ góc nhìn broker, nhưng ứng dụng chưa nhất thiết nhận bằng `receive()` hay `onMessage()`.
- **Delivered/consumed bởi Session ở cấp JMS:** được tính vào phạm vi client acknowledgment theo contract JMS.

Cách provider quản lý hàng đợi prefetch, batch ACK và bộ đếm delivering là **chi tiết triển khai**. Vì thế khi kiểm thử phạm vi ACK, hãy dùng **message ID + nội dung đã `receive()`** và kiểm chứng redelivery thực tế, thay vì suy từ một chỉ số console đơn lẻ.

## 3. So sánh phạm vi `CLIENT_ACKNOWLEDGE` với các chế độ gần kề

| Chế độ | Hành vi xác nhận | Phạm vi cần hiểu |
|---|---|---|
| `Session.AUTO_ACKNOWLEDGE` | Provider tự ACK message khi thao tác nhận/callback đáp ứng ngữ nghĩa thành công của JMS | Không có lời gọi ACK thủ công từ ứng dụng |
| `Session.CLIENT_ACKNOWLEDGE` | Ứng dụng gọi `Message.acknowledge()` | **Tất cả message đã tiêu thụ chưa ACK của cùng Session** |
| `Session.DUPS_OK_ACKNOWLEDGE` | Provider được phép trì hoãn việc ACK, đổi hiệu năng lấy khả năng redelivery trùng | Ứng dụng không kiểm soát ACK theo từng message |
| `Session.SESSION_TRANSACTED` | `Session.commit()` chốt thao tác nhận/ACK và send thuộc JMS transaction; `rollback()` hủy transaction hiện tại | **Transaction của Session**, không phải ACK độc lập của từng Message |

Với transacted Session, tham số acknowledge mode truyền vào `createSession(true, ...)` không quyết định ACK; **commit/rollback** mới là ranh giới. Đừng viết code có transaction nhưng tin rằng `message.acknowledge()` tạo một commit riêng.

### Vì sao JMS thiết kế như vậy?

Một Session cung cấp ngữ cảnh tiêu thụ tuần tự và có thể nhận nhiều message; API `CLIENT_ACKNOWLEDGE` cho phép ứng dụng **xác nhận một nhóm message đã tiêu thụ**, giảm số thao tác ACK. Nhưng batch theo Session trở thành lỗi khi một Session gánh các **đơn vị nghiệp vụ độc lập** mà không được xử lý/commit cùng lúc.

Đây không phải lỗi riêng ActiveMQ Classic hay Artemis: đó là ngữ nghĩa **JMS tiêu chuẩn**.

## 4. Thực hành: chứng minh ACK một message có tác dụng lên hai queue

Mục đích lab là so sánh **cùng Session** với **hai Session độc lập**, không cần thiết lập lại kiến thức cơ bản về broker. Dùng ActiveMQ Artemis 2.40.0 với endpoint JMS native `tcp://127.0.0.1:61616` và tài khoản có quyền `send`/`consume` trên hai queue.

### 4.1. Cấu hình đích ở broker Artemis

Trong `broker.xml`, nếu chưa có queue, có thể chèn hai address dưới phần tử **`<addresses>` hiện hữu**:

~~~xml
<address name="lab.ack.payment">
    <anycast>
        <queue name="lab.ack.payment"/>
    </anycast>
</address>

<address name="lab.ack.shipping">
    <anycast>
        <queue name="lab.ack.shipping"/>
    </anycast>
</address>
~~~

Hai queue độc lập, mỗi queue có routing **ANYCAST**. Các đoạn XML là **mảnh cấu hình**, không phải file `broker.xml` hoàn chỉnh. Nếu đã tồn tại, không tạo lại; nếu broker cho phép auto-create, có thể chạy lab mà không cần sửa `broker.xml`. Chạy thử trong môi trường riêng, không để consumer production cạnh tranh lấy message từ các queue này.

### 4.2. Maven và namespace

Dự án:

~~~text
client-ack-scope-lab/
├── pom.xml
└── src/main/java/lab/ClientAckScopeLab.java
~~~

`pom.xml` với Java 17 và Artemis client tương thích **`jakarta.jms`**:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>lab</groupId>
    <artifactId>client-ack-scope-lab</artifactId>
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

Một lưu ý: với ActiveMQ Classic 5.x, thông thường dùng `org.apache.activemq:activemq-client` và `javax.jms`. **Không** dùng import `javax.jms` với Artemis Jakarta client ở ví dụ này. Dù dùng provider nào, ACK phạm vi Session vẫn là quy tắc JMS.

### 4.3. Java thực hành ba tình huống

Tạo file `src/main/java/lab/ClientAckScopeLab.java`. Chương trình hỗ trợ bốn chế độ:

- `seed`: gửi một message persistent tới mỗi queue bằng một producer transaction.
- `shared`: tạo hai consumer **cùng Session**, nhận A và B, chỉ ACK message B.
- `isolated`: tạo hai consumer ở **hai Session** trong cùng Connection; ACK A, đóng Session B khi chưa ACK, sau đó mở Session mới nhận lại B.
- `probe`: kiểm tra queue có message hay không; nếu thấy message, **không ACK** và đóng session để tránh xóa dữ liệu thử nghiệm.

~~~java
package lab;

import jakarta.jms.Connection;
import jakarta.jms.DeliveryMode;
import jakarta.jms.JMSException;
import jakarta.jms.Message;
import jakarta.jms.MessageConsumer;
import jakarta.jms.MessageProducer;
import jakarta.jms.Queue;
import jakarta.jms.Session;
import jakarta.jms.TextMessage;
import org.apache.activemq.artemis.jms.client.ActiveMQConnectionFactory;

import java.util.UUID;

public final class ClientAckScopeLab {

    private static final String PAYMENT = "lab.ack.payment";
    private static final String SHIPPING = "lab.ack.shipping";

    private ClientAckScopeLab() {}

    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            throw new IllegalArgumentException(
                    "Chọn một mode: seed | shared | isolated | probe");
        }

        String url = System.getenv().getOrDefault(
                "BROKER_URL", "tcp://127.0.0.1:61616");
        String user = requiredEnv("BROKER_USER");
        String password = requiredEnv("BROKER_PASSWORD");

        ActiveMQConnectionFactory factory = new ActiveMQConnectionFactory(url);
        Connection connection = factory.createConnection(user, password);
        try {
            switch (args[0]) {
                case "seed" -> seed(connection);
                case "shared" -> sharedSession(connection);
                case "isolated" -> isolatedSessions(connection);
                case "probe" -> probe(connection);
                default -> throw new IllegalArgumentException(
                        "Mode không hợp lệ: " + args[0]);
            }
        } finally {
            connection.close();
        }
    }

    private static String requiredEnv(String key) {
        String value = System.getenv(key);
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException("Thiếu " + key);
        }
        return value;
    }

    private static void seed(Connection connection) throws JMSException {
        // Producer Session là giao dịch độc lập, không phải
        // một trong các Session CLIENT_ACKNOWLEDGE của consumer.
        Session session = connection.createSession(
                true, Session.SESSION_TRANSACTED);
        try {
            Queue payment = session.createQueue(PAYMENT);
            Queue shipping = session.createQueue(SHIPPING);
            MessageProducer producer = session.createProducer(null);
            try {
                producer.setDeliveryMode(DeliveryMode.PERSISTENT);
                String runId = UUID.randomUUID().toString().substring(0, 8);

                producer.send(payment,
                        session.createTextMessage("PAYMENT-" + runId));
                producer.send(shipping,
                        session.createTextMessage("SHIPPING-" + runId));

                session.commit();
                System.out.println("SEEDED: A và B trong hai queue");
            } finally {
                producer.close();
            }
        } finally {
            session.close();
        }
    }

    private static void sharedSession(Connection connection)
            throws JMSException {
        // CẢ HAI consumer sử dụng CHUNG một Session.
        Session session = connection.createSession(
                false, Session.CLIENT_ACKNOWLEDGE);
        try {
            MessageConsumer a =
                    session.createConsumer(session.createQueue(PAYMENT));
            MessageConsumer b =
                    session.createConsumer(session.createQueue(SHIPPING));

            connection.start();

            Message messageA = require(a.receive(5000), "PAYMENT");
            Message messageB = require(b.receive(5000), "SHIPPING");

            show("A received, not yet acked", messageA);
            show("B received, not yet acked", messageB);

            // QUAN TRỌNG:
            // B.acknowledge() xác nhận A và B vì cùng Session.
            messageB.acknowledge();

            System.out.println(
                    "ACK_B_CALLED: tất cả message đã tiêu thụ "
                    + "trong Session chung được ACK.");
        } finally {
            session.close();
        }
    }

    private static void isolatedSessions(Connection connection)
            throws JMSException {
        // Hai Session trong CÙNG Connection, mỗi Session tự ACK.
        Session sessionA = connection.createSession(
                false, Session.CLIENT_ACKNOWLEDGE);
        Session sessionB = connection.createSession(
                false, Session.CLIENT_ACKNOWLEDGE);
        try {
            MessageConsumer a =
                    sessionA.createConsumer(sessionA.createQueue(PAYMENT));
            MessageConsumer b =
                    sessionB.createConsumer(sessionB.createQueue(SHIPPING));

            connection.start();

            Message messageA = require(a.receive(5000), "PAYMENT");
            Message messageB = require(b.receive(5000), "SHIPPING");
            show("Session A got", messageA);
            show("Session B got", messageB);

            messageA.acknowledge(); // Chỉ Session A được xác nhận.
            System.out.println("ACK_A: Session B vẫn chưa ACK");

            // Đóng Session B khi B chưa được ACK.
            // B sẽ đủ điều kiện redelivery theo broker/client policy.
            sessionB.close();
            sessionB = null;

            Session retrySession = connection.createSession(
                    false, Session.CLIENT_ACKNOWLEDGE);
            try {
                MessageConsumer retry = retrySession.createConsumer(
                        retrySession.createQueue(SHIPPING));
                Message redelivered = require(retry.receive(10000),
                        "SHIPPING redelivery");
                show("Session mới nhận lại B", redelivered);
                redelivered.acknowledge();
                System.out.println("ACK_B_ON_NEW_SESSION");
            } finally {
                retrySession.close();
            }
        } finally {
            if (sessionB != null) {
                sessionB.close();
            }
            sessionA.close();
        }
    }

    private static void probe(Connection connection) throws JMSException {
        // Không ACK: chỉ quan sát; nếu queue còn message, nó sẽ
        // đủ điều kiện giao lại sau khi Session đóng.
        Session session = connection.createSession(
                false, Session.CLIENT_ACKNOWLEDGE);
        try {
            MessageConsumer a = session.createConsumer(
                    session.createQueue(PAYMENT));
            MessageConsumer b = session.createConsumer(
                    session.createQueue(SHIPPING));

            connection.start();
            Message messageA = a.receive(1500);
            Message messageB = b.receive(1500);

            System.out.println("PROBE_PAYMENT="
                    + (messageA == null ? "EMPTY" : "HAS_MESSAGE"));
            System.out.println("PROBE_SHIPPING="
                    + (messageB == null ? "EMPTY" : "HAS_MESSAGE"));
        } finally {
            session.close();
        }
    }

    private static Message require(Message message, String label) {
        if (message == null) {
            throw new IllegalStateException(
                    "Không thấy " + label
                    + " trong thời gian chờ; kiểm tra queue và dữ liệu seed");
        }
        return message;
    }

    private static void show(String label, Message message)
            throws JMSException {
        String body = message instanceof TextMessage text
                ? text.getText() : "<not TextMessage>";
        String count = message.propertyExists("JMSXDeliveryCount")
                ? String.valueOf(message.getIntProperty("JMSXDeliveryCount"))
                : "not-provided";

        System.out.println(label
                + " id=" + message.getJMSMessageID()
                + " body=" + body
                + " redelivered=" + message.getJMSRedelivered()
                + " deliveryCount=" + count);
    }
}
~~~

**Giải thích phạm vi trong mã:**

- `seed()` dùng producer Session **transacted** để gửi hai message thử. Nó không tham gia ACK của các Session consumer.
- `sharedSession()` gọi **duy nhất `messageB.acknowledge()`**. Sau đó, mọi message đã được ứng dụng tiêu thụ từ Session chung, gồm A và B, đều thuộc phạm vi ACK.
- `isolatedSessions()` ACK A bằng Session A; B ở Session B vẫn unacked. Đóng Session B cho phép broker đưa B trở lại trạng thái đủ điều kiện redelivery. Một Session mới nhận B rồi ACK độc lập.
- `probe()` dùng `receive()` để quan sát nhưng **không ACK** nếu thấy message, và đóng Session ngay. Chỉ chạy trên queue thử nghiệm vì thao tác quan sát bằng receive có thể ảnh hưởng thứ tự và số lần giao lại; nếu cần quan sát không làm tiêu thụ, dùng broker management browse.
- `JMSXDeliveryCount` không phải khóa idempotency; giá trị thuộc JMS provider hỗ trợ và chính sách giao lại. Cờ `JMSRedelivered` giúp quan sát việc giao lại nhưng không thay thế business event ID.

### 4.4. Chạy hai kịch bản độc lập

Trong PowerShell, đặt biến môi trường phù hợp broker lab:

~~~powershell
$env:BROKER_URL = "tcp://127.0.0.1:61616"
$env:BROKER_USER = "lab"
$env:BROKER_PASSWORD = "mat-khau-cua-broker-lab"
mvn -q -DskipTests package
~~~

**Kịch bản A — hai queue chung Session:**

~~~powershell
mvn -q exec:java "-Dexec.mainClass=lab.ClientAckScopeLab" "-Dexec.args=seed"
mvn -q exec:java "-Dexec.mainClass=lab.ClientAckScopeLab" "-Dexec.args=shared"
mvn -q exec:java "-Dexec.mainClass=lab.ClientAckScopeLab" "-Dexec.args=probe"
~~~

Quan sát dự kiến:

~~~text
A received, not yet acked id=... body=PAYMENT-... redelivered=false deliveryCount=1
B received, not yet acked id=... body=SHIPPING-... redelivered=false deliveryCount=1
ACK_B_CALLED: tất cả message đã tiêu thụ trong Session chung được ACK.

PROBE_PAYMENT=EMPTY
PROBE_SHIPPING=EMPTY
~~~

**Kịch bản B — hai Session khác nhau trong cùng Connection:**

~~~powershell
mvn -q exec:java "-Dexec.mainClass=lab.ClientAckScopeLab" "-Dexec.args=seed"
mvn -q exec:java "-Dexec.mainClass=lab.ClientAckScopeLab" "-Dexec.args=isolated"
mvn -q exec:java "-Dexec.mainClass=lab.ClientAckScopeLab" "-Dexec.args=probe"
~~~

Quan sát dự kiến:

~~~text
Session A got id=... body=PAYMENT-... redelivered=false deliveryCount=1
Session B got id=... body=SHIPPING-... redelivered=false deliveryCount=1
ACK_A: Session B vẫn chưa ACK
Session mới nhận lại B id=... body=SHIPPING-... redelivered=true deliveryCount=2
ACK_B_ON_NEW_SESSION

PROBE_PAYMENT=EMPTY
PROBE_SHIPPING=EMPTY
~~~

Số lần giao và cờ redelivery trong log có thể khác nếu queue đã chứa message hoặc policy client/broker khác. Trọng tâm là **B không được ACK khi ta chỉ ACK A ở Session độc lập**, vì vậy B có thể được giao lại sau khi Session B đóng.

**Điều kiện để kết quả dễ đối chiếu:** trước từng `seed`, kiểm tra hai queue lab **đang rỗng** và không có consumer khác. `seed` tạo message mới, không tự dọn message cũ. Không thực hiện lab trên queue nghiệp vụ thật và không dùng thao tác purge nếu chưa xác nhận có thể xóa dữ liệu.

## 5. `Session.recover()`: giao lại message chưa ACK trong Session

`CLIENT_ACKNOWLEDGE` không có `rollback()` như giao dịch JMS; đó là **non-transacted Session**. JMS cung cấp `Session.recover()` để dừng rồi khởi động lại message delivery trong Session và giao lại các message đã tiêu thụ mà **chưa được xác nhận**.

Ví dụ rút gọn với một consumer đồng bộ:

~~~java
Session session = connection.createSession(
        false, Session.CLIENT_ACKNOWLEDGE);
try {
    MessageConsumer consumer = session.createConsumer(
            session.createQueue("lab.ack.payment"));
    connection.start();

    Message first = consumer.receive(5000);
    if (first != null) {
        System.out.println("Lần 1: " + first.getJMSMessageID());

        // Chưa gọi first.acknowledge().
        session.recover();

        Message redelivered = consumer.receive(5000);
        if (redelivered != null) {
            System.out.println("Lần 2: "
                    + redelivered.getJMSMessageID());
            System.out.println("JMSRedelivered="
                    + redelivered.getJMSRedelivered());

            // Chỉ ACK sau khi xử lý thành công.
            redelivered.acknowledge();
        }
    }
} finally {
    session.close();
}
~~~

**Phân biệt các thao tác:**

| Thao tác | Ý nghĩa |
|---|---|
| `message.acknowledge()` trên Session CLIENT_ACK | Xác nhận toàn bộ message đã tiêu thụ chưa ACK trong Session |
| `session.recover()` trên non-transacted Session | Khởi động lại delivery đối với message đã tiêu thụ nhưng chưa ACK trong Session |
| `session.close()` / mất Connection khi còn unacked | Message chưa ACK có thể được trả lại để broker giao lại theo chính sách |
| `session.rollback()` | Chỉ dùng khi Session **transacted**; hủy giao dịch và cho phép redelivery |
| `session.commit()` | Chỉ dùng khi Session **transacted**, xác nhận message đã tiêu thụ thuộc transaction và chốt send trong transaction |

Khi có **nhiều consumer chung Session**, `recover()` cũng có **phạm vi Session**, không chỉ một consumer. Nếu đã ACK A và B bằng `messageB.acknowledge()`, gọi recover sau đó không thể “hoàn tác” ACK đã hoàn tất để lấy lại A.

**Không sử dụng `Session.recover()` từ nhiều thread đồng thời hoặc trộn `receive()` với `MessageListener` trên cùng consumer.** Nếu consumer bất đồng bộ báo lỗi, hãy thiết kế cơ chế xử lý recovery phù hợp lifecycle/luồng sở hữu Session, hoặc chuyển sang transacted Session với rollback rõ ràng. Đừng xem recover như khả năng retry an toàn đúng một message theo lựa chọn.

### 5.1. Mối quan hệ với redelivery policy và DLQ

Lệnh recover có thể dẫn đến redelivery; broker hoặc client có thể áp dụng delay, số lần thử, chiến lược DLQ theo **cơ chế và phiên bản cụ thể**. Một số đường đi có thể làm số delivery count tăng và cờ redelivered được bật. Không nên viết logic phụ thuộc tuyệt đối vào giá trị `JMSXDeliveryCount == 2` ở mọi broker.

Với **Artemis**, chính sách `redelivery-delay`, `max-delivery-attempts` và `dead-letter-address` nằm trong cấu hình address settings. Với **ActiveMQ Classic**, redelivery policy và dead-letter strategy có cơ chế riêng; copy XML Artemis sang Classic sẽ không có tác dụng đúng.

## 6. Lỗi nghiệp vụ khi nhiều message dùng chung Session

### 6.1. Sai lầm: ACK “message cuối đã xong” khi message đầu còn lỗi

~~~java
Message payment = paymentConsumer.receive(5000);
Message shipping = shippingConsumer.receive(5000);

try {
    processShipping(shipping);  // Thành công
    shipping.acknowledge();     // Cũng ACK payment nếu cùng Session
} catch (Exception error) {
    log(error);
}

// processPayment(payment) chưa được gọi hoặc đã thất bại.
~~~

Nếu A và B là hai việc độc lập, đoạn trên **không an toàn**. Lệnh ACK không kiểm tra liệu `processPayment(payment)` đã thành công. Đó là trách nhiệm của ứng dụng.

### 6.2. Thiết kế đúng theo yêu cầu nghiệp vụ

**Lựa chọn A — mỗi luồng nghiệp vụ một Session**

Nếu payment và shipping độc lập, tạo **Session riêng** cho từng consumer. ACK của payment chỉ ảnh hưởng các message đã tiêu thụ trong Session payment; ACK của shipping chỉ ảnh hưởng Session shipping.

Không nhất thiết phải tạo hai TCP Connection: cả hai Session có thể nằm trong **cùng Connection** nhưng có ranh giới ACK riêng. Trong ứng dụng chạy lâu, quản lý session/consumer lifecycle và thread-safety rõ ràng.

**Lựa chọn B — cố ý ACK theo batch trong một Session**

Nếu một Session nhận **nhiều message thuộc cùng đơn vị xử lý**, có thể ACK ở cuối sau khi **tất cả** công việc trong batch được xác nhận thành công. Cần hiểu rủi ro:

- Nếu ứng dụng crash trước ACK, **cả batch chưa xác nhận** có thể được giao lại.
- Nếu một message thất bại trong khi những message khác đã tạo side effect, cần idempotency để tránh lặp.
- `CLIENT_ACKNOWLEDGE` không có rollback transaction để chốt đồng thời side effect và ACK.

Ví dụ một đơn vị xử lý gồm A1, A2, A3 trong cùng Session: xử lý và commit nghiệp vụ của tất cả, rồi gọi `A3.acknowledge()`. Điều này là ACK theo **Session/batch**, không phải ACK riêng A3.

**Lựa chọn C — `SESSION_TRANSACTED` khi cần rollback có chủ đích**

Với work queue có tác vụ xử lý nhiều bước và cần rollback nếu một bước thất bại, transacted Session thường diễn đạt logic rõ hơn:

~~~java
Session session = connection.createSession(
        true, Session.SESSION_TRANSACTED);
MessageConsumer consumer = session.createConsumer(
        session.createQueue("shipping.create"));
connection.start();

try {
    Message message = consumer.receive(5000);
    if (message != null) {
        businessHandler(message); // Chỉ khi thành công
        session.commit();         // ACK qua JMS transaction
    }
} catch (Exception failure) {
    session.rollback();
    throw failure;
} finally {
    session.close();
}
~~~

Transaction JMS **không bao gồm** transaction database tự động. Nếu DB commit rồi process chết trước JMS commit, message có thể được giao lại. Cần thiết kế consumer idempotent theo `eventId`, outbox khi cần phối hợp producer DB với publish JMS, và đối soát side effect ngoài hệ thống.

### 6.3. Cần ACK riêng từng message thì sao?

**Chuẩn JMS `CLIENT_ACKNOWLEDGE` không cung cấp per-message ACK độc lập trong cùng Session.**

Một số provider hỗ trợ extension, ví dụ **`ActiveMQSession.INDIVIDUAL_ACKNOWLEDGE`** ở ActiveMQ Classic; Artemis Core API cũng có cách điều khiển acknowledgement ở tầng native. Tuy nhiên những cơ chế này **không nằm trong ngữ nghĩa portable của `CLIENT_ACKNOWLEDGE`** và có điều kiện riêng về Session, batching và broker. Không coi việc đổi một hằng số là phương án thay thế thiết kế transaction/idempotency.

Nếu cần giới hạn tác động của ACK theo từng công việc mà vẫn dùng JMS chuẩn, cách dễ chứng minh nhất là **Session độc lập theo luồng xử lý**, sau đó điều chỉnh số Session/consumer theo tải và tài nguyên.

## 7. Đặc biệt với `MessageListener`: phạm vi ACK vẫn không đổi

Nhận bất đồng bộ không thay đổi quy tắc scope.

~~~java
Session session = connection.createSession(
        false, Session.CLIENT_ACKNOWLEDGE);

MessageConsumer consumerA = session.createConsumer(
        session.createQueue("lab.ack.payment"));
MessageConsumer consumerB = session.createConsumer(
        session.createQueue("lab.ack.shipping"));

consumerA.setMessageListener(message -> {
    // Không thể giả định ACK ở callback A độc lập với callback B.
});

consumerB.setMessageListener(message -> {
    // ACK này bao phủ message đã tiêu thụ trong Session chung.
    try {
        handleShipping(message);
        message.acknowledge();
    } catch (Exception error) {
        reportFailure(error);
    }
});

connection.start();
~~~

Đây là **đoạn minh họa ý nghĩa**, không phải chương trình Java độc lập: `handleShipping` và `reportFailure` là hàm do ứng dụng triển khai.

Theo JMS, callback listener trong **cùng Session** được tuần tự hóa. Nhưng một Session có thể chứa nhiều consumer, và ACK ở callback sau vẫn có thể xác nhận message đã tiêu thụ trước đó qua consumer khác, nếu chưa ACK.

**Đừng cố sửa bằng cách đưa `message.acknowledge()` sang thread pool.** JMS Session không được dùng đồng thời tùy tiện từ nhiều luồng; đưa tác vụ nghiệp vụ vào executor rồi ACK trước khi executor xử lý xong còn tạo rủi ro mất công việc. Muốn concurrency, tạo nhiều Session/consumer do lifecycle manager/framework quản lý.

## 8. Tình huống lỗi, mất việc và nhận lại message

### 8.1. ACK sớm làm mất khả năng tự redeliver

~~~text
t0: S1 nhận payment A; business A chưa commit
t1: S1 nhận shipping B; business B commit
t2: B.acknowledge() thành công -> A cũng ACK
t3: JVM crash
t4: Broker không redeliver A chỉ vì business A chưa hoàn tất
~~~

Ở đây vấn đề **không phải broker bỏ qua transaction**, mà là ứng dụng đã ACK A ngoài ý muốn theo scope Session. Để tránh, tách Session và chỉ ACK khi business commit.

### 8.2. ACK muộn tạo khả năng delivery trùng

~~~text
t0: S1 nhận payment A
t1: Business DB commit A
t2: JVM crash trước message.acknowledge()
t3: Broker có thể giao lại A
t4: Consumer phải kiểm tra eventId để không tạo lại tác dụng nghiệp vụ
~~~

Cách xử lý phổ biến: trong cùng transaction DB, ghi `processed_events(event_id)` và thay đổi nghiệp vụ, bảo đảm unique constraint; lần nhận lại nhận ra event đã xử lý rồi ACK mà không lặp tác dụng.

### 8.3. Mất phản hồi tại lúc ACK

Nếu mạng lỗi đúng lúc gọi `acknowledge()`, client có thể không biết chắc broker đã nhận ACK. **ACK gọi xong hoặc thất bại ở phía client không nên trở thành bằng chứng nghiệp vụ đã commit hay chưa.** Nghiệp vụ phải có nguồn sự thật riêng, còn consumer cần chịu được duplicate delivery.

### 8.4. ACK cả một nhóm nhưng sau đó gọi recover

Sau khi ACK thành công, `Session.recover()` không có tác dụng hoàn tác xác nhận. Vì thế không có chiến lược:

~~~text
ACK B (vô tình ACK A) -> phát hiện A lỗi -> recover A
~~~

Đây không phải transaction rollback. Nếu bạn cần xác nhận nhóm message theo mô hình tất cả thành công hoặc tất cả nhận lại, hãy thiết kế transacted Session hoặc tách unit of work và idempotency phù hợp.

## 9. Quan sát và kiểm chứng tại broker

Dùng **web console/JMX** của ActiveMQ Classic hoặc Artemis để đối chiếu:

| Chỉ số | Dùng để đánh giá | Không được suy ra |
|---|---|---|
| Queue message count | Số message đang chờ/chưa hoàn tất theo cách broker đếm | Bao nhiêu message đã xử lý nghiệp vụ thành công |
| Delivering/in-flight count | Message đã được dispatch/chưa hoàn tất ACK | Tất cả đều đã đến phương thức `receive()` của ứng dụng |
| Acknowledged/dequeued count | Broker đã xác nhận/gỡ message theo chỉ số cụ thể | DB transaction đã commit |
| Consumer count | Có bao nhiêu consumer đang đăng ký | Mỗi consumer đều khỏe và xử lý đúng |
| Redelivery count hoặc `JMSXDeliveryCount` | Có hiện tượng nhận lại message | Nguyên nhân chính xác và số tác dụng nghiệp vụ |
| DLQ queue depth | Số message đã đi vào đường xử lý lỗi theo policy | Producer gửi thất bại |

Thực nghiệm có giá trị nhất là kết hợp **message ID, session identity, log ACK và trạng thái queue**. Khi demo cùng Session, nhìn hai queue đều rỗng sau chỉ một `acknowledge()` giúp xác nhận phạm vi. Khi demo hai Session, B được giao lại sau khi chỉ ACK A là bằng chứng đối chiếu.

Không dùng hai queue có consumer bên ngoài khi đo, vì message có thể bị client khác lấy/ACK khiến kết quả sai lệch. Không xóa/purge một queue chưa xác minh quyền sở hữu dữ liệu.

## 10. Câu hỏi kiểm tra tư duy

**1. Một Connection có hai Session `S1` và `S2`. ACK message của S1 có xác nhận message đã tiêu thụ ở S2 không?**

Không. Scope của `CLIENT_ACKNOWLEDGE` là **Session**, không phải Connection. Hai Session có trạng thái ACK độc lập dù dùng chung Connection TCP/JMS.

**2. Hai consumer của hai queue khác nhau dùng cùng Session. Consumer B gọi `acknowledge()`; message từ consumer A đã nhận có được ACK không?**

Có, nếu message A đã được Session đó tiêu thụ và chưa ACK. Không có quy tắc ACK theo queue trong `CLIENT_ACKNOWLEDGE`.

**3. Nếu gọi `acknowledge()` trên message A1, các message A2/B1 được cùng Session nhận sau A1 nhưng trước lúc ACK có thuộc scope không?**

Có. Scope xét **toàn bộ message đã tiêu thụ chưa xác nhận trong Session tại thời điểm gọi ACK**, không chỉ những message đứng trước A1 trong một thứ tự nhận giả định.

**4. Có thể gọi `Session.recover()` để lấy lại message đã ACK thành công không?**

Không. Recover dành cho những delivery **chưa được xác nhận** trong non-transacted Session; ACK đã thành công không bị hoàn tác.

**5. Đổi sang `SESSION_TRANSACTED` có khiến DB và JMS cùng commit một lần không?**

Không. JMS transaction chỉ điều khiển các thao tác JMS trong Session; DB transaction vẫn độc lập nếu không có cơ chế phối hợp phù hợp. Cần idempotency và xác định thứ tự commit.

**6. Có thể kiểm tra phạm vi ACK chỉ bằng log “consumer B processed” không?**

Không. Cần biết consumer B dùng **Session nào**, message nào đã tiêu thụ trong Session đó, đã ACK khi nào, và kiểm tra kết quả trên broker hoặc qua redelivery test.

## 11. Checklist thiết kế `CLIENT_ACKNOWLEDGE`

- [ ] Mỗi consumer được gắn với Session nào? Có consumer khác cùng Session không?
- [ ] Một lần `acknowledge()` có thể bao phủ message chưa xử lý nào?
- [ ] Nếu dùng batch ACK, tất cả message trong phạm vi đã được xử lý/commit nghiệp vụ chưa?
- [ ] Nếu một message thất bại, cách recover hoặc chuyển sang transacted Session đã rõ chưa?
- [ ] Session có bị truy cập từ nhiều thread hoặc handler/worker pool không?
- [ ] Khi DB commit xong nhưng ACK chưa xong, đã có `eventId`/idempotency chưa?
- [ ] Broker redelivery, DLQ, queue depth và log nhận được theo dõi chưa?
- [ ] Nếu cần ACK từng công việc độc lập, đã tách Session hay chọn extension có chủ đích chưa?
- [ ] Bài test đã kiểm chứng **hai consumer cùng Session** và **hai consumer khác Session** chưa?
- [ ] Các chỉ số broker có được đối chiếu với kết quả nghiệp vụ, không đánh đồng ACK với xử lý thành công không?

## 12. Kết luận kỹ thuật

**`CLIENT_ACKNOWLEDGE` là xác nhận theo phạm vi Session.** Một lời gọi `Message.acknowledge()` trên bất kỳ message đã tiêu thụ trong Session sẽ xác nhận các message đã tiêu thụ chưa ACK **thuộc cùng Session**, kể cả message đến từ consumer khác hoặc queue khác. Nó không ảnh hưởng Session riêng biệt, dù hai Session dùng cùng Connection.

Nếu các công việc độc lập, hãy **tách Session** để tránh ACK ngoài ý muốn; nếu cần transaction rollback rõ ràng, dùng **`SESSION_TRANSACTED`** với commit/rollback phù hợp. Dù lựa chọn nào, độ tin cậy nghiệp vụ vẫn cần xử lý trùng, giám sát redelivery và đặt ACK sau khi thay đổi nghiệp vụ đã được commit.
