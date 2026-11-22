# Selector, cú pháp biểu thức và ảnh hưởng đến phân phối thông điệp

## 1. Selector tác động vào bước nào của consumer?

**JMS message selector** là điều kiện lọc được cung cấp khi tạo **MessageConsumer/JMSConsumer**. Provider sử dụng biểu thức để chọn message có **JMS headers** hoặc **message properties** phù hợp; selector chuẩn không phân tích JSON, XML hay Java object nằm trong body. Với ActiveMQ Classic và Artemis, sự khác biệt giữa **lọc delivery tới consumer** và **lọc lúc broker route message vào queue** quyết định message không khớp có còn nằm chờ hay không.

Ví dụ queue **orders.in** chứa sáu thông điệp:

| Message | region | amount (JMS numeric property) | eventType |
| --- | --- | ---: | --- |
| M1 | VN | 800 | OrderPaid |
| M2 | VN | 100 | OrderPaid |
| M3 | SG | 700 | OrderPaid |
| M4 | SG | 400 | OrderCancelled |
| M5 | TH | 600 | OrderPaid |
| M6 | VN | *thiếu property* | OrderPaid |

Selector:

~~~sql
region = 'VN' AND amount >= 500
~~~

chỉ khớp **M1**. M2 không đạt ngưỡng; M3/M4/M5 khác vùng; M6 thiếu amount nên điều kiện amount trả **UNKNOWN**. Khi một queue consumer không nhận M2–M6, các message đó **không tự bị ACK, xóa hoặc gửi DLQ**. Chúng có thể tiếp tục chờ consumer phù hợp.

~~~mermaid
flowchart TB
    Q[("Queue orders.in<br/>M1 M2 M3 M4 M5 M6")]
    Q --> A["Consumer A selector<br/>region='VN' AND amount>=500"]
    Q --> B["Consumer B selector<br/>region='SG'"]
    A --> M1["Nhận M1"]
    B --> M34["Nhận M3, M4"]
    Q --> R[("M2 M5 M6 còn chờ")]
    R --> C["Consumer phù hợp khác<br/>nhận phần dư"]
~~~

Bài thuộc chương **Consumer** của module **INTEGRATION_MESSAGING_MESSAGE_BROKER_ACTIVEMQ**. Phạm vi là cách viết biểu thức đúng, cách JMS đánh giá TRUE/FALSE/UNKNOWN và tác động lên queue/topic, kèm thử nghiệm cụ thể bằng Java/JMS.

## 2. Khai báo selector đúng API và đúng thời điểm

Với **Jakarta Messaging/JMSContext**:

~~~java
Queue queue = context.createQueue("orders.in");
JMSConsumer consumer = context.createConsumer(
        queue,
        "eventType = 'OrderPaid' AND region = 'VN' AND amount >= 500");
~~~

Với API **javax.jms** của Classic 5.x hoặc API Connection/Session tương ứng:

~~~java
Session session = connection.createSession(
        true, Session.SESSION_TRANSACTED);
Queue queue = session.createQueue("orders.in");
MessageConsumer consumer = session.createConsumer(
        queue,
        "eventType = 'OrderPaid' AND region = 'VN' AND amount >= 500");
~~~

**Selector được chọn lúc tạo consumer**; các lời gọi **receive()** sau đó dùng điều kiện ấy. JMS không cung cấp cách portable để sửa trực tiếp selector của consumer đang mở. Muốn đổi, đóng consumer hiện tại và tạo consumer mới, tính đến message đang in-flight và transaction/ACK chưa hoàn tất.

Một số provider có thể triển khai selector tại broker để giảm dữ liệu truyền tới client. Nhưng hiệu quả tối ưu này **không đổi ý nghĩa JMS**: message trên **queue** không khớp selector không bị coi là đã xử lý.

### Phải đặt JMS properties, không chỉ JSON

Giả sử producer gửi:

~~~java
TextMessage message = context.createTextMessage(
        "{\"eventType\":\"OrderPaid\",\"region\":\"VN\",\"amount\":800}");
~~~

Selector chuẩn **không truy cập trường bên trong TextMessage**. Producer cần gắn các property độc lập:

~~~java
message.setStringProperty("eventType", "OrderPaid");
message.setStringProperty("region", "VN");
message.setIntProperty("amount", 800);
message.setBooleanProperty("urgent", true);
~~~

Các property này phải là **hợp đồng giữa producer và consumer**, gồm tên, kiểu, đơn vị và quy tắc khi thiếu giá trị. Không giả định broker tự sao chép các field JSON thành properties.

## 3. Cú pháp SQL-92 subset của JMS selector

Ngôn ngữ selector lấy cảm hứng từ **SQL-92 conditional expressions**, không phải SQL truy vấn database đầy đủ. Không sử dụng **SELECT**, **JOIN**, subquery, stored procedure, JSON path hoặc hàm SQL tùy ý.

| Nhóm điều kiện | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| Bằng, khác | **region = 'VN'**; **status <> 'CANCELLED'** | So sánh giá trị |
| So sánh số | **amount > 500**, **amount <= 1000** | Numeric comparison |
| AND/OR/NOT | **urgent = TRUE AND region = 'VN'** | Logic Boolean ba giá trị |
| IN | **region IN ('VN', 'SG')** | Thuộc danh sách literal |
| BETWEEN | **amount BETWEEN 100 AND 1000** | Khoảng có bao gồm hai đầu |
| LIKE | **orderCode LIKE 'ORD-%'** | Mẫu chuỗi |
| IS NULL | **amount IS NULL** | Thiếu/chưa xác định |
| IS NOT NULL | **amount IS NOT NULL** | Có giá trị |

Các dạng phủ định như **NOT IN**, **NOT BETWEEN**, **NOT LIKE** cũng có thể được sử dụng. Viết ngoặc khi điều kiện kết hợp nhiều toán tử để tránh diễn giải sai.

**Chuỗi phải đặt trong dấu nháy đơn**, ví dụ **'VN'**, còn **TRUE/FALSE** là literal boolean và **500** là numeric literal. Nếu chuỗi chứa dấu nháy đơn, biểu diễn bằng cách nhân đôi:

~~~sql
customerName = 'O''Brien'
~~~

Không dùng **!=**, **ILIKE**, **REGEXP**, **JSON_VALUE**, **CAST** hoặc **COALESCE** như thể đó là cú pháp JMS selector portable. Provider có thể có extension riêng, nhưng cần ghi rõ phạm vi phiên bản và kiểm tra tính tương thích khi dùng.

### LIKE và ký tự đặc biệt

- **%** khớp không hoặc nhiều ký tự.
- **_** khớp đúng một ký tự.
- **ESCAPE** khai báo một ký tự thoát để so khớp literal wildcard.

~~~sql
orderCode LIKE 'ORD-%'
orderCode LIKE 'A_'
orderCode LIKE 'INV!_%' ESCAPE '!'
~~~

Biểu thức cuối khớp các mã bắt đầu bằng **INV_** với dấu gạch dưới thật, ví dụ **INV_1001**. Nếu thiếu ESCAPE, dấu **_** là wildcard. Giá trị chuỗi thường phân biệt chữ hoa/chữ thường; chuẩn hóa eventType, region và tên code ở producer.

### Tên property và giá trị

Dùng những identifier hợp lệ và ổn định như **eventType**, **region**, **amount**, **tenantId**. Tránh tên chứa dấu gạch nối, khoảng trắng, dấu chấm hoặc trùng từ khóa selector. Không đặt tên application property trong vùng tên hệ thống như **JMSX...**.

Các toán tử so sánh và LIKE thao tác trên giá trị của property, **không tính toán trực tiếp nội dung payload**. Một selector dài ghép nhiều biểu thức có thể khó kiểm thử; khi điều kiện nghiệp vụ phức tạp, producer nên xác định property phân loại rõ ràng, ví dụ **riskBand='HIGH'**.

## 4. TRUE, FALSE, UNKNOWN: vì sao message thiếu property không khớp?

JMS selector sử dụng logic ba giá trị **TRUE**, **FALSE**, **UNKNOWN**. Message **chỉ khớp khi toàn bộ biểu thức trả TRUE**. Một property không tồn tại thường dẫn đến UNKNOWN khi so sánh thông thường.

M6 có **region='VN'**, nhưng không có **amount**:

~~~sql
region = 'VN' AND amount >= 500
~~~

Điều kiện đầu trả TRUE; điều kiện thứ hai UNKNOWN; **TRUE AND UNKNOWN = UNKNOWN**, nên M6 không được consumer chọn.

| A | B | A AND B | A OR B |
| --- | --- | --- | --- |
| TRUE | UNKNOWN | UNKNOWN | TRUE |
| FALSE | UNKNOWN | FALSE | UNKNOWN |
| UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN |
| TRUE | FALSE | FALSE | TRUE |

**NOT UNKNOWN vẫn UNKNOWN**. Bởi vậy:

~~~sql
NOT (region = 'VN')
~~~

không lấy những message thiếu **region**. Muốn lấy cả message không có region, phải biểu diễn rõ:

~~~sql
region <> 'VN' OR region IS NULL
~~~

**Đừng so sánh NULL bằng = NULL hoặc <> NULL**; hai phép so sánh này không trả TRUE cho trường hợp thiếu. Dùng:

~~~sql
amount IS NULL
amount IS NOT NULL
amount IS NOT NULL AND amount >= 500
~~~

### Ưu tiên AND/OR và dấu ngoặc

Thứ tự ưu tiên logic: **NOT > AND > OR**. Hai biểu thức sau có ý nghĩa khác nhau:

~~~sql
region = 'VN' OR region = 'SG' AND amount >= 500
~~~

~~~sql
(region = 'VN' OR region = 'SG') AND amount >= 500
~~~

Câu đầu cho qua **mọi message VN** kể cả amount nhỏ. Câu sau chỉ cho qua VN/SG có amount đủ lớn. Với selector kết hợp tenant, eventType, SLA hoặc mức ưu tiên, **luôn dùng ngoặc** để làm rõ ý định.

## 5. JMS property type và header được phép lọc

Nếu producer gọi:

~~~java
message.setIntProperty("amount", 800);
~~~

thì **amount >= 500** có ngữ nghĩa so sánh số. Nếu producer lại gọi:

~~~java
message.setStringProperty("amount", "800");
~~~

thì property mang kiểu **String**. Không dựa vào chuyển đổi ngầm giữa String "800" và numeric 800 trong biểu thức: tùy provider, việc so sánh có thể không match. Hợp đồng property nên chốt kiểu dữ liệu, đơn vị và quy tắc null.

Các kiểu properties phổ biến là **boolean, byte, short, int, long, float, double, String**. Tránh dùng float/double cho số tiền nghiệp vụ cần chính xác; dùng đơn vị nguyên nhỏ nhất và kiểu long nếu giới hạn phù hợp.

JMS selector có thể tham chiếu một số **JMS header fields**, ví dụ:

~~~sql
JMSPriority >= 7
JMSDeliveryMode = 'PERSISTENT'
JMSRedelivered = TRUE
JMSType = 'OrderPaid'
JMSCorrelationID = 'workflow-821'
~~~

Ở selector, **JMSDeliveryMode** dùng tên chuỗi **'PERSISTENT'** hoặc **'NON_PERSISTENT'**; trong Java, **getJMSDeliveryMode()** lại trả về giá trị int theo hằng số DeliveryMode. **JMSPriority** là numeric, **JMSRedelivered** là boolean.

Các trường như **JMSMessageID**, **JMSTimestamp**, **JMSExpiration** cũng thuộc metadata JMS; việc dùng chúng phải xét thời điểm provider gán và ngữ nghĩa thực tế. **JMSXDeliveryCount** là JMSX property có thể được provider cung cấp để quan sát giao lại; không nên dùng selector **JMSXDeliveryCount >= 3** để thay cơ chế retry/DLQ của broker vì giá trị và thời điểm đánh giá có thể thay đổi trong quá trình giao.

## 6. Queue: lọc consumer, không tạo bản sao message

Với queue, mỗi message được giao cho **một consumer đủ điều kiện tại một thời điểm**, kể cả khi có nhiều consumer cùng đọc queue đó. Nếu hai selector **cùng khớp** một message, broker chọn một consumer theo chính sách dispatch; không có hai bản sao độc lập.

Ví dụ queue **orders.in** có ba consumer:

| Consumer | Selector | Đủ điều kiện |
| --- | --- | --- |
| A | **region = 'VN' AND amount >= 500** | M1 |
| B | **region = 'SG'** | M3, M4 |
| C | Không selector | M1–M6 |

Nếu C hoạt động đồng thời với A và B, C **có thể lấy M1/M3/M4 trước**. Selector cụ thể hơn không mang quyền ưu tiên so với selector catch-all. Để kiểm chứng message còn lại trong queue, cần cho A/B xử lý rồi đóng, **sau đó** mới mở C.

Khi queue chỉ có consumer nhận **region='VN'** nhưng message mới toàn **region='TH'**, message có thể tích lũy backlog. Broker không tự ACK, hủy hoặc chuyển DLQ chỉ vì chúng **không khớp selector**. Hãy quan sát queue depth và oldest-message age; nếu luồng được phân tách ổn định, cân nhắc nhiều queue với routing phù hợp thay vì đặt một selector quá hẹp trên queue tổng.

**Selector không bảo đảm FIFO toàn cục.** Prefetch, nhiều consumer, priority, rollback, redelivery và độ trễ nghiệp vụ làm thứ tự hoàn thành khác thứ tự gửi. Nếu cần xử lý tuần tự theo orderId, phải dùng cơ chế grouping/ordering hoặc kiểm tra version nghiệp vụ thích hợp.

## 7. Topic: selector thuộc về subscription, không phải message chung

Trên JMS Topic **orders.events**, các subscription độc lập có thể dùng selector khác nhau:

- Billing VN: **eventType = 'OrderPaid' AND region = 'VN'**.
- Audit: không selector.
- Fraud: **amount >= 10000**.

Một OrderPaid VN amount=12000 có thể được phân phối cho **cả ba subscription**. Một OrderPaid SG amount=12000 có thể vào Audit và Fraud, không vào Billing VN. Mỗi subscription có trạng thái nhận/ACK riêng.

~~~mermaid
flowchart LR
    P["Producer"] --> T(("Topic orders.events"))
    T --> B["Billing VN<br/>eventType='OrderPaid' AND region='VN'"]
    T --> A["Audit<br/>không selector"]
    T --> F["Fraud<br/>amount>=10000"]
~~~

Tạo subscription không bền bằng Jakarta Messaging:

~~~java
Topic topic = context.createTopic("orders.events");
JMSConsumer billing = context.createConsumer(
        topic,
        "eventType = 'OrderPaid' AND region = 'VN'");
~~~

Với **non-durable subscription**, message publish khi subscription không hoạt động không được tự lưu để phát bù sau reconnect. Với **durable subscription**, broker có thể lưu những message phù hợp từ thời điểm subscription đã tồn tại, tùy TTL, storage và policy.

Nếu thay selector của một **durable subscription**, định nghĩa subscription có thể bị thay đổi hoặc tạo lại, ảnh hưởng backlog hiện tại theo quy tắc JMS/provider. Hãy kiểm thử và có kế hoạch migration trước khi đổi ở production. Với **shared subscription**, nhiều consumer chia nhau message **của cùng subscription**, không phải mỗi consumer nhận một bản sao độc lập.

## 8. Artemis: queue filter lúc route khác consumer selector lúc dispatch

Artemis cho phép khai báo **queue filter** trong broker.xml. Nó quyết định message **được enqueue vào queue từ đầu** hay không, khác consumer selector chỉ xác định message đủ điều kiện nhận tại consumer.

~~~xml
<!-- Đoạn nằm trong phần addresses của broker.xml hiện có. -->
<address name="orders.events">
    <multicast>
        <queue name="billing.vn" durable="true">
            <filter string="eventType = 'OrderPaid' AND region = 'VN'"/>
        </queue>
        <queue name="audit.all" durable="true"/>
    </multicast>
</address>
~~~

Nếu producer publish **OrderPaid region=SG**, queue **billing.vn** không nhận một bản phân phối nào; queue **audit.all** vẫn nhận. Consumer dùng selector rộng hơn sau đó cũng **không thể lấy hồi tố message chưa từng vào billing.vn**.

Nếu consumer đọc **billing.vn** rồi thêm selector **amount >= 500**, message phải đáp ứng **cả queue filter lúc route và consumer selector lúc delivery**.

Với Artemis JMS client, có thể chọn queue cụ thể bằng **FQQN**:

~~~java
Queue billingQueue =
        context.createQueue("orders.events::billing.vn");
JMSConsumer consumer =
        context.createConsumer(billingQueue, "amount >= 500");
~~~

**FQQN = address::queue**. Khi dùng JMS Topic hoặc giao thức ngoài JMS, cần xác định routing type (MULTICAST/ANYCAST) và binding tương ứng; tránh vô tình tạo queue khác qua auto-create.

### Escape XML cho filter

Nếu XML attribute chứa dấu **<** hoặc **&**, viết bằng entity:

~~~xml
<filter string="amount &lt; 500 AND region = 'VN'"/>
~~~

Nội dung filter thực sau parse là **amount < 500 AND region = 'VN'**. Queue filter và JMS selector dùng cú pháp biểu thức tương tự ở các phép so sánh thường gặp, nhưng extension riêng của Artemis không bảo đảm tương thích với ActiveMQ Classic.

## 9. Lab Jakarta JMS: hai selector và message vẫn nằm chờ

Thí nghiệm gửi sáu message vào **một queue ANYCAST**. Consumer A với **region='VN' AND amount>=500** nhận M1, B với **region='SG'** nhận M3/M4. Sau khi A và B đóng, consumer C với selector chỉ giới hạn **runId** nhận **M2/M5/M6**. Đây là phép kiểm chứng rằng không match selector không đồng nghĩa message bị xóa.

### 9.1. Điều kiện trước khi chạy

Cần JDK 17+, Maven, broker ActiveMQ Artemis và credential có quyền **send/consume**. Đặt **BROKER_URL** theo cổng host; ví dụ **tcp://127.0.0.1:61617** nếu Artemis chạy cùng Classic theo Docker Compose.

Demo tạo queue riêng có tên ngẫu nhiên; nếu broker cấm auto-create ANYCAST queue, hãy tạo queue test trước và sửa queueName. Dùng project Maven với dependency **artemis-jakarta-client** phù hợp broker. POM ví dụ:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>lab.messaging</groupId>
    <artifactId>artemis-selector-lab</artifactId>
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

### 9.2. Code hoàn chỉnh

Tạo **src/main/java/SelectorQueueLab.java**:

~~~java
import jakarta.jms.DeliveryMode;
import jakarta.jms.JMSConsumer;
import jakarta.jms.JMSContext;
import jakarta.jms.JMSProducer;
import jakarta.jms.Message;
import jakarta.jms.Queue;
import jakarta.jms.TextMessage;
import org.apache.activemq.artemis.jms.client.ActiveMQConnectionFactory;

import java.util.HashSet;
import java.util.Objects;
import java.util.Set;
import java.util.UUID;

public final class SelectorQueueLab {
    public static void main(String[] args) throws Exception {
        String url = System.getenv().getOrDefault(
                "BROKER_URL", "tcp://127.0.0.1:61616");
        String user = Objects.requireNonNull(
                System.getenv("BROKER_USER"), "Missing BROKER_USER");
        String password = Objects.requireNonNull(
                System.getenv("BROKER_PASSWORD"), "Missing BROKER_PASSWORD");

        String runId = UUID.randomUUID().toString();
        String queueName = "lab.selectors." + runId.replace("-", "");
        ActiveMQConnectionFactory factory =
                new ActiveMQConnectionFactory(url);

        try (JMSContext sender = factory.createContext(
                    user, password, JMSContext.SESSION_TRANSACTED);
             JMSContext vn = factory.createContext(
                    user, password, JMSContext.SESSION_TRANSACTED);
             JMSContext sg = factory.createContext(
                    user, password, JMSContext.SESSION_TRANSACTED);
             JMSContext rest = factory.createContext(
                    user, password, JMSContext.SESSION_TRANSACTED)) {

            Queue queue = sender.createQueue(queueName);
            JMSProducer producer = sender.createProducer()
                    .setDeliveryMode(DeliveryMode.PERSISTENT);

            send(sender, producer, queue, runId, "M1", "VN", 800);
            send(sender, producer, queue, runId, "M2", "VN", 100);
            send(sender, producer, queue, runId, "M3", "SG", 700);
            send(sender, producer, queue, runId, "M4", "SG", 400);
            send(sender, producer, queue, runId, "M5", "TH", 600);
            send(sender, producer, queue, runId, "M6", "VN", null);
            sender.commit();

            String scope = "runId = '" + runId + "'";
            JMSConsumer vnConsumer = vn.createConsumer(
                    queue, scope + " AND region = 'VN' AND amount >= 500");
            JMSConsumer sgConsumer = sg.createConsumer(
                    queue, scope + " AND region = 'SG'");

            expect(vn, vnConsumer, Set.of("M1"), "VN-large");
            expect(sg, sgConsumer, Set.of("M3", "M4"), "SG-all");

            vnConsumer.close();
            sgConsumer.close();

            // Catch-all được tạo sau khi hai consumer chuyên biệt đóng.
            JMSConsumer remaining = rest.createConsumer(queue, scope);
            expect(rest, remaining, Set.of("M2", "M5", "M6"), "remaining");
            remaining.close();

            System.out.println("PASS: 3 matched, 3 remained in queue");
        }
    }

    private static void send(
            JMSContext sender, JMSProducer producer,
            Queue queue, String runId, String id,
            String region, Integer amount) throws Exception {
        TextMessage msg = sender.createTextMessage("payload-" + id);
        msg.setStringProperty("runId", runId);
        msg.setStringProperty("eventId", id);
        msg.setStringProperty("region", region);
        if (amount != null) {
            msg.setIntProperty("amount", amount);
        }
        producer.send(queue, msg);
        System.out.printf("SEND %s region=%s amount=%s%n",
                id, region, amount);
    }

    private static void expect(
            JMSContext tx, JMSConsumer consumer,
            Set<String> expectedIds, String name) throws Exception {
        Set<String> actual = new HashSet<>();

        for (int i = 0; i < expectedIds.size(); i++) {
            Message msg = consumer.receive(10000L);
            if (msg == null) {
                tx.rollback();
                throw new IllegalStateException(name + " receive timed out");
            }
            String id = msg.getStringProperty("eventId");
            if (!expectedIds.contains(id) || !actual.add(id)) {
                tx.rollback();
                throw new IllegalStateException(
                        name + " unexpected or repeated message: " + id);
            }
            tx.commit();
            System.out.println(name + " RECEIVED " + id);
        }

        Message extra = consumer.receive(500L);
        if (extra != null) {
            tx.rollback();
            throw new IllegalStateException(name + " got extra message");
        }
    }
}
~~~

Trong demo, **M6 thiếu property amount**, được xử lý theo UNKNOWN ở biểu thức so sánh. Các context khác nhau có transaction JMS riêng; commit của VN không ACK message đang chờ SG hoặc catch-all.

### 9.3. Chạy và kết quả mong đợi

Trong PowerShell tại thư mục Maven demo:

~~~powershell
$env:BROKER_URL = "tcp://127.0.0.1:61617"
$env:BROKER_USER = "artemis_app"
$env:BROKER_PASSWORD = "<your-artemis-password>"

mvn -q compile exec:java "-Dexec.mainClass=SelectorQueueLab"
~~~

Thay password placeholder bằng credential thật, và đổi URL nếu Artemis được publish tại cổng khác. Docker Compose **.env** không tự động trở thành environment variables của lệnh Maven trên host.

Đầu ra điển hình:

~~~text
SEND M1 region=VN amount=800
SEND M2 region=VN amount=100
SEND M3 region=SG amount=700
SEND M4 region=SG amount=400
SEND M5 region=TH amount=600
SEND M6 region=VN amount=null
VN-large RECEIVED M1
SG-all RECEIVED M3
SG-all RECEIVED M4
remaining RECEIVED M2
remaining RECEIVED M5
remaining RECEIVED M6
PASS: 3 matched, 3 remained in queue
~~~

Chương trình so sánh **tập eventId**, không khẳng định thứ tự tuyệt đối; thứ tự nhận M3/M4 và các message còn lại có thể phụ thuộc broker. **Consumer catch-all** chỉ được mở sau khi hai consumer đầu đã hoàn tất, để tránh tranh quyền với chúng.

Đây là bài lab **selector và transaction JMS**, không có database side effect. Trong sản phẩm thật, commit nghiệp vụ bền vững và idempotency phải xảy ra trước khi commit JMS. Queue thử nghiệm có tên ngẫu nhiên nên cần quản lý/xóa các queue lab không còn sử dụng; không xóa nhầm destination sản xuất.

## 10. Classic javax.jms: cùng quy tắc selector

Với **ActiveMQ Classic 5.x**, dùng **org.apache.activemq:activemq-client** và package **javax.jms**. Đoạn code trong phương thức có **user/password** đã cung cấp:

~~~java
import javax.jms.Connection;
import javax.jms.Message;
import javax.jms.MessageConsumer;
import javax.jms.Queue;
import javax.jms.Session;
import org.apache.activemq.ActiveMQConnectionFactory;

ActiveMQConnectionFactory factory =
        new ActiveMQConnectionFactory("tcp://127.0.0.1:61616");
Connection connection = factory.createConnection(user, password);
try {
    Session session = connection.createSession(
            true, Session.SESSION_TRANSACTED);
    try {
        Queue queue = session.createQueue("orders.in");
        MessageConsumer consumer = session.createConsumer(
                queue,
                "region = 'VN' AND amount >= 500");
        try {
            connection.start();
            Message message = consumer.receive(5000L);
            if (message != null) {
                System.out.println(
                        message.getStringProperty("eventId"));
                // Xử lý dữ liệu thành công rồi mới xác nhận JMS.
                session.commit();
            }
        } finally {
            consumer.close();
        }
    } finally {
        session.close();
    }
} finally {
    connection.close();
}
~~~

JMS selector giữ ngữ nghĩa ngôn ngữ chuẩn ở Classic và Artemis; khả năng tối ưu ở broker, prefetch, expiry hoặc redelivery policy có thể khác theo sản phẩm và phiên bản. Đừng trộn các import **javax.jms** của Classic với **jakarta.jms** của Artemis client trong cùng source/demo.

## 11. ACK, rollback và retry không do selector quyết định

| Sự kiện | Hệ quả |
| --- | --- |
| Message không match selector | Có thể vẫn chờ trong queue, chưa được consumer ACK |
| Consumer nhận message phù hợp và commit JMS | Message được xác nhận trên queue/subscription đó |
| Consumer rollback message đã nhận | Broker có thể redeliver theo policy |
| Message quá TTL khi chờ | Broker có thể expire; selector không ngăn expiration |
| Message hỏng bị retry nhiều lần | DLQ do redelivery/dead-letter policy, không do selector |
| Producer gửi hai JMS messages trùng eventId | Cả hai có thể match selector; cần idempotency |

Không nên dùng selector **JMSRedelivered = FALSE** để ngăn xử lý trùng: một message chưa xử lý xong được broker phát lại có thể không được consumer nào nhận, tạo backlog. Hãy để broker quản lý retry/DLQ và dùng **eventId** ổn định để deduplicate khi ghi nghiệp vụ.

Consumer không được dựa hoàn toàn vào **amount/tenantId** trên message properties để quyết định quyền thực thi side effect. Header và properties là dữ liệu đầu vào; business handler vẫn cần xác thực payload và trạng thái nghiệp vụ.

## 12. Hiệu năng, backlog và bảo mật

Consumer selector phù hợp khi các message chung queue được nhiều worker xử lý theo điều kiện khác nhau, nhưng phải bảo đảm có consumer bao phủ dữ liệu cần xử lý. Khi queue chứa nhiều message không match, **queue depth/oldest-message age có thể tăng** dù consumer đang online.

Những chỉ số cần kiểm tra:

| Tín hiệu | Vì sao hữu ích |
| --- | --- |
| Pending/queue depth | Phát hiện message không match hoặc không được xử lý |
| In-flight/delivering | Phân biệt message đã dispatch với message đang chờ |
| Consumer count/selector | Đối soát nhóm đang online và điều kiện hiện hành |
| Oldest-message age | Nhận diện nhóm bị bỏ quên lâu |
| Expiry/DLQ count | Phân biệt lỗi/timeout với không match |
| Phân bố property | Phát hiện sai tên, sai kiểu, thiếu vùng hoặc eventType |
| Tốc độ xử lý theo consumer | Phát hiện bất cân bằng do selector/độ trễ nghiệp vụ |

Một biểu thức dài kết hợp nhiều điều kiện, đặc biệt LIKE với wildcard đầu, có thể tốn chi phí đánh giá. Khi số lượng nhóm ổn định và backlog cần tách biệt, dùng **nhiều queue / routing filter** thích hợp hơn. Nếu cần mỗi nhóm nhận một bản phân phối độc lập, dùng **topic/multicast** với subscription queue riêng.

**Selector không phải cơ chế phân quyền.** Nếu một account được phép consume toàn bộ queue nhưng UI chỉ mở consumer **tenantId='A'**, account đó vẫn có thể tạo consumer không lọc nếu broker không hạn chế. Hãy dùng **authentication, authorization, quyền destination, tách queue/topic** cho tenant isolation; dùng selector để lọc trong phạm vi đã được cấp quyền.

## 13. Cách chẩn đoán selector không nhận message

| Triệu chứng | Nguyên nhân có khả năng | Cách kiểm chứng |
| --- | --- | --- |
| Có message trong queue nhưng receive timeout | Property không match, thiếu/sai kiểu, hoặc selector sai | Browse headers/properties và đánh giá từng điều kiện |
| **amount >= 500** không chọn String **"800"** | Type mismatch | Dùng numeric setter trong producer |
| **region <> 'VN'** không chọn message thiếu region | UNKNOWN, không phải TRUE | Dùng **OR region IS NULL** nếu có chủ đích |
| Consumer A/B nhận message “không đúng nhóm” | Selector chồng lấp hoặc một consumer catch-all | Xem tập điều kiện, các consumer đang online |
| Topic consumer mới không thấy event cũ | Subscription được tạo sau lúc publish | Kiểm tra durable/non-durable và lifecycle |
| Consumer selector rộng hơn vẫn không lấy message | Queue filter đã không enqueue message | Phân biệt thời điểm route và delivery |
| Hàng chờ tăng nhưng consumer vẫn hoạt động | Không consumer nào match nhóm backlog | Kiểm tra phân bố metadata và selector |
| Không nhận message redelivered | Selector đã loại **JMSRedelivered = TRUE** | Kiểm tra retry, delivery count và selector |
| broker.xml không parse filter | Dấu **<** hoặc **&** chưa escape | Đổi sang **&lt;**, **&amp;** trong XML |

Quy trình điều tra: xác nhận **broker/destination** → lấy selector nguyên văn → quan sát **JMS properties và kiểu** của một eventId → tính TRUE/FALSE/UNKNOWN → kiểm tra consumer cạnh tranh → phân biệt pending/in-flight/ACK/expiry/DLQ → kiểm tra topic subscription hoặc Artemis queue filter.

Không suy rằng consumer selector đã được áp dụng chỉ vì nhìn thấy điều kiện trong code; broker/client có thể đang chạy bản cấu hình cũ, consumer được tạo với selector khác hoặc đang đọc queue khác.

## 14. Bài tập củng cố và tiêu chí nghiệm thu

**Thực hành A — NULL và type.** Gửi lần lượt amount numeric **500**, numeric **499**, thiếu amount và amount String **"800"**. Dự đoán kết quả của **amount >= 500** rồi đối chiếu. Dùng thêm **amount IS NULL** để chọn trường hợp thiếu.

**Thực hành B — Dấu ngoặc.** Gửi VN amount 100, SG amount 100 và SG amount 800. So sánh kết quả:

~~~sql
region = 'VN' OR region = 'SG' AND amount >= 500
~~~

với:

~~~sql
(region = 'VN' OR region = 'SG') AND amount >= 500
~~~

Dùng hai queue thử nghiệm riêng để message của hai consumer không tranh nhau.

**Thực hành C — LIKE và ESCAPE.** Gửi mã **INV_01**, **INV001**, **INV_A**, **INV-01**. Tạo selector **orderCode LIKE 'INV!_%' ESCAPE '!'**. Giải thích vì sao chỉ các mã có dấu gạch dưới thật ngay sau INV mới match.

**Thực hành D — Queue filter.** Trên Artemis, tạo hai queue MULTICAST: một filter **region='VN'**, một không filter. Publish message VN và SG. Chứng minh tạo consumer selector rộng hơn sau đó không thể lấy các message mà queue filter không nhận từ lúc route.

**Thực hành E — Selector chồng lấp.** Trên một queue, mở A selector **amount>=500** và B selector **region='VN'**. Publish VN amount 800. Kiểm tra message được giao cho một consumer theo dispatch, không tự tạo hai bản sao. Dùng hai subscription queue nếu cả hai nhóm cần nhận độc lập.

| Tiêu chí nghiệm thu | Cần chứng minh |
| --- | --- |
| Viết đúng cú pháp | Toán tử, quote, IN/BETWEEN/LIKE và dấu ngoặc |
| Hiểu ba giá trị | UNKNOWN không match; kiểm tra NULL bằng IS NULL |
| Đúng kiểu dữ liệu | String và numeric property không bị giả định tương đương |
| Hiểu queue | Message không match vẫn có thể chờ consumer khác |
| Hiểu topic | Selector thuộc từng subscription, không ảnh hưởng độc lập của subscriber khác |
| Hiểu Artemis | Queue filter áp dụng lúc route, consumer selector lúc delivery |
| Biết vận hành | Quan sát backlog, in-flight, expiry/DLQ và loại consumer |
| Bảo mật phù hợp | Selector không thay cho authorization |

**JMS selector giúp consumer chọn message qua metadata**, với cú pháp SQL-92 subset và logic ba giá trị. Để hệ thống ActiveMQ Classic/Artemis đáng tin cậy, phải phân biệt **consumer filtering**, **queue filtering lúc routing** và **quyết định ACK/retry sau xử lý**, đồng thời bảo đảm message không được chọn vẫn có một đường xử lý hợp lệ.
