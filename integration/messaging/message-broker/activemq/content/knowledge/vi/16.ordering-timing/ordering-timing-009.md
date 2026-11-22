# Scheduled delivery của Artemis và khác biệt với JMS delivery delay

## 1. Một mốc hẹn và một khoảng trì hoãn không giống nhau

Giả sử dịch vụ Reservation phát một thông điệp nhắc lịch ngay khi người dùng xác nhận đặt chỗ. Có hai yêu cầu khác nhau:

- **Nhắc lúc 09:00 ngày mai**: nghiệp vụ biết một **thời điểm tuyệt đối**.
- **Kiểm tra lại sau 30 giây**: nghiệp vụ chỉ biết một **khoảng trì hoãn tương đối** tính từ lúc gửi.

**Apache ActiveMQ Artemis scheduled delivery** hỗ trợ mốc tuyệt đối qua property riêng của broker **_AMQ_SCHED_DELIVERY**, chứa timestamp Unix epoch theo **mili giây**. **JMS delivery delay** (JMS 2.0/Jakarta Messaging) là API chuẩn **JMSProducer.setDeliveryDelay(long)** hoặc **MessageProducer.setDeliveryDelay(long)**, nhận **số mili giây cần trì hoãn**. Provider gán header **JMSDeliveryTime** thể hiện thời điểm sớm nhất message được phép giao.

~~~mermaid
sequenceDiagram
    autonumber
    participant P as Producer
    participant B as Artemis broker
    participant Q as Queue
    participant C as Consumer
    P->>B: send(message có lịch)
    P->>B: commit() nếu Session transacted
    B->>Q: Giữ scheduled reference
    Note over B,Q: Chưa đủ điều kiện dispatch
    B->>Q: Tới thời điểm scheduled
    Q-->>C: Delivery khi có consumer phù hợp
    C-->>B: ACK / commit sau xử lý
~~~

Scheduler chỉ kiểm soát **thời điểm đủ điều kiện phân phối sớm nhất**, không bảo đảm consumer nhận đúng mili giây, càng không bảo đảm giao dịch nghiệp vụ hoàn tất đúng thời điểm đó.

~~~text
t_send → t_commit → t_due → t_dispatch → t_business_commit → t_jms_ack
~~~

Bài thuộc chương **Thứ tự và thời gian** của module **INTEGRATION_MESSAGING_MESSAGE_BROKER_ACTIVEMQ**, tập trung vào so sánh hai API đặt lịch, vòng đời tại Artemis, ảnh hưởng của TTL/transaction/ordering và cách kiểm chứng bằng Java/JMS.

## 2. Bảng so sánh nguồn thời gian và tính portable

| Tiêu chí | Artemis scheduled delivery | JMS delivery delay |
| --- | --- | --- |
| Đầu vào | **Timestamp tuyệt đối**, epoch milliseconds | **Duration tương đối**, milliseconds |
| Cách đặt | **message.setLongProperty("_AMQ_SCHED_DELIVERY", epochMs)** | **producer.setDeliveryDelay(delayMs)** |
| Ví dụ | Giao từ **2027-01-02T09:00:00Z** | Giao từ khoảng **5 giây sau send** |
| Phạm vi | Extension của **Artemis** | API **JMS 2.0/Jakarta Messaging** chuẩn khi provider hỗ trợ |
| Metadata | Property lập lịch Artemis và trạng thái scheduled ở broker | Header chuẩn **JMSDeliveryTime** |
| Mặc định | Không có scheduling property thì không đặt lịch native | Delivery delay mặc định **0** |
| Phù hợp | Lịch hẹn có mốc thời gian, nhắc lịch cụ thể | Trì hoãn theo thời lượng, chờ N giây |
| Broker khác | Không tự tương thích | Cần JMS client/provider hỗ trợ delivery delay |

Tại cùng một thời điểm gửi, hai cách có thể mang cùng thời điểm due:

~~~text
Send lúc 10:00:00.000
Artemis property = epochMillis(10:00:20.000)
JMS setDeliveryDelay(20_000L)
→ Cả hai có mốc eligible khoảng 10:00:20.000
~~~

Tuy nhiên, nếu producer chạy trễ ba phút, “**giao vào 09:00**” và “**giao sau ba phút**” không còn tương đương.

**Tránh đặt đồng thời _AMQ_SCHED_DELIVERY và setDeliveryDelay trên cùng message.** Trong từng provider, hai cách có thể được ánh xạ vào chung cơ chế scheduler, nhưng không có quy tắc portable xác định cái nào thắng khi hai mốc xung đột. Chọn một nguồn sự thật và kiểm chứng trên phiên bản broker/client đang sử dụng.

## 3. Scheduled delivery native của Artemis dùng mốc tuyệt đối

Trong Artemis Core, field lập lịch tương ứng với **Message.HDR_SCHEDULED_DELIVERY_TIME**. Qua Artemis JMS client, có thể truyền mốc đến broker bằng property **_AMQ_SCHED_DELIVERY**:

~~~java
import java.time.Instant;
import jakarta.jms.TextMessage;

// context và queue đã được tạo bằng Artemis JMS client.
long dueAt = Instant.parse("2027-01-02T09:00:00Z").toEpochMilli();

TextMessage message =
        context.createTextMessage("ReservationReminder");
message.setStringProperty("eventId", "reservation-R100-reminder");
message.setLongProperty("_AMQ_SCHED_DELIVERY", dueAt);

context.createProducer().send(queue, message);
~~~

**Năm điều cần đúng:**

1. Giá trị **long** là **epoch milliseconds**, không phải số giây trì hoãn. Đặt **5000L** không có nghĩa hoãn năm giây; đó là timestamp thuộc quá khứ xa.
2. Đừng lấy **Instant.getEpochSecond()** rồi gán thẳng vào property: phải dùng **toEpochMilli()**.
3. Nếu nhập thời gian địa phương, chuyển bằng zone ID rõ ràng trước khi lấy Instant; không phụ thuộc timezone mặc định của JVM.
4. Đồng hồ broker/host cần được đồng bộ. Clock skew có thể làm broker coi due time đã đến hoặc còn xa.
5. Đặt property **trước send**. Sửa message object sau khi đã gửi không cập nhật message đã nằm trong broker.

Ví dụ đổi lịch **09:00 tại Việt Nam** thành timestamp chuẩn:

~~~java
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.time.ZonedDateTime;

LocalDateTime local = LocalDateTime.of(2027, 1, 2, 9, 0);
ZonedDateTime zoned =
        local.atZone(ZoneId.of("Asia/Ho_Chi_Minh"));
long scheduledAtEpochMs = zoned.toInstant().toEpochMilli();
~~~

Với vùng có daylight saving time, một local time có thể mơ hồ hoặc không tồn tại; cần policy nghiệp vụ cho tình huống đó. Dữ liệu lưu để đối soát nên chứa cả **zone nghiệp vụ**, **mốc Instant** và **scheduleVersion**.

### Điều gì xảy ra nếu lịch đã ở quá khứ?

Một timestamp native ở quá khứ thường khiến message **đủ điều kiện giao ngay sau khi đã được broker chấp nhận/commit và route**, không khiến broker “truy xuất lịch sử”. Nếu tính sai đơn vị epoch, message có thể đến gần như tức thì. Vì vậy nên log mốc native ở cả dạng số và **Instant.ofEpochMilli(value)** trước khi gửi.

### Scheduled reference và sự tồn tại của queue

Sau khi message được broker nhận/commit, Artemis quản lý bản phân phối phù hợp với **queue/subscription**. Khi chưa đến hạn, message có thể được quản lý dưới dạng **scheduled reference**, chưa sẵn sàng dispatch. Queue durable và message persistent, cùng storage/journal hợp lệ, là những điều kiện quan trọng nếu muốn message còn qua broker restart.

Một queue phải **được tạo hoặc được auto-create theo policy** để có nơi lưu message. Với topic/multicast, queue/subscription phù hợp tại thời điểm route mới có bản phân phối; scheduling không tự tạo durable subscription cho một consumer sẽ xuất hiện trong tương lai.

## 4. JMS delivery delay: tương đối và do JMS provider tính

Jakarta Messaging cung cấp **JMSProducer.setDeliveryDelay(milliseconds)**:

~~~java
import jakarta.jms.JMSProducer;

JMSProducer producer = context.createProducer()
        .setDeliveryDelay(5_000L); // Hoãn 5 giây kể từ send.
producer.send(queue, message);
~~~

API producer truyền thống trong client hỗ trợ JMS 2.0 cũng có:

~~~java
MessageProducer producer = session.createProducer(queue);
producer.setDeliveryDelay(5_000L);
producer.send(message);
~~~

JMS provider sẽ tính mốc eligible và ghi **JMSDeliveryTime**. Consumer Jakarta Messaging có thể quan sát:

~~~java
long deliveryTime = received.getJMSDeliveryTime();
System.out.println(
        java.time.Instant.ofEpochMilli(deliveryTime));
~~~

**Không nên tự gọi message.setJMSDeliveryTime(...) rồi xem đó là yêu cầu chuẩn để lên lịch**. Header được quản lý bởi provider; cách portable là cấu hình delay trên producer.

| Timestamp/header | Trả lời câu hỏi |
| --- | --- |
| **JMSTimestamp** | Provider ghi nhận mốc gửi nào? |
| **JMSDeliveryTime** | Khi nào message sớm nhất được phép giao theo JMS? |
| **JMSExpiration** | Từ mốc nào message hết hạn theo TTL/policy? |
| **_AMQ_SCHED_DELIVERY** | Native scheduler của Artemis được yêu cầu mốc nào? |
| Thời gian **receive()** trả về | Ứng dụng thực sự quan sát delivery lúc nào? |
| Thời gian DB commit | Nghiệp vụ thực sự hoàn tất lúc nào? |

**Delivery delay mặc định là 0**. Khi tái sử dụng một JMSProducer mutable, cần quản lý rõ delay từng loại message; **setDeliveryDelay** không retroactively thay lịch của các message đã gửi. Với JMSContext, session/transaction vẫn là tài nguyên có lifecycle; không chia sẻ context dùng đồng thời từ nhiều thread.

### Thận trọng với mốc native và JMSDeliveryTime

Artemis có thể thực hiện JMS delivery delay dựa trên cơ chế scheduling nội bộ. Nhưng khi ứng dụng **đặt trực tiếp property _AMQ_SCHED_DELIVERY**, đừng mặc định header **JMSDeliveryTime** sẽ được sửa thành cùng giá trị trong mọi phiên bản/client. Khi kiểm chứng native scheduling, hãy quan sát **native property, mốc producer tính và dữ liệu scheduled trong broker**; với API JMS delay, đối chiếu **JMSDeliveryTime**.


## 5. Transaction, TTL và hai đồng hồ thời gian

Một **Session transacted** có thể gửi delayed message rồi commit sau. **Trước commit**, broker không được dispatch message thuộc transaction chưa hoàn tất, ngay cả khi due time đã đi qua.

~~~mermaid
sequenceDiagram
    participant P as Producer
    participant B as Broker
    participant C as Consumer
    P->>B: send M1, scheduledAt = 10:00:10
    Note over P,B: Transaction JMS chưa commit
    P->>B: commit lúc 10:00:12
    B-->>C: M1 có thể dispatch sau commit
~~~

Nếu một scheduled message đến hạn trong lúc producer chưa commit, nó chỉ có thể được giao sau khi transaction được commit; nếu rollback thì không có bản gửi đã commit. Nếu **commit() ném lỗi mạng**, outcome có thể **UNKNOWN**: broker đã commit lịch hay chưa. Dùng eventId ổn định, outbox và idempotency khi retry thay vì suy exception luôn là rollback.

### Time-to-live và expiration là điều kiện độc lập

**Scheduled delivery/JMS delivery delay** nói **sớm nhất khi nào được giao**. **Time-to-live (TTL)/JMSExpiration** nói **khi nào message hết hạn**. Một message persistent có thể hết hạn trước khi được tiêu thụ.

~~~text
send                  due                     expiration
 |---------------------|--------------------------|
 chưa đủ điều kiện      có thể giao               không còn hợp lệ
~~~

Ví dụ có nguy cơ không bao giờ được nhận:

~~~java
context.createProducer()
       .setDeliveryDelay(60_000L)
       .setTimeToLive(5_000L)
       .send(queue, message);
~~~

Đừng giả định TTL ngắn hơn delay sẽ vẫn cho message còn hợp lệ sau 60 giây. Cách provider tính các header phải được kiểm chứng bằng **getJMSDeliveryTime()**, **getJMSExpiration()** và policy expiry thực tế. Đối với lab chỉ muốn kiểm tra scheduling, dùng **TTL=0** để loại yếu tố này trước; sau đó thử expiration riêng.

Một scheduled reminder cũng có thể **hết giá trị nghiệp vụ** vì reservation đã hủy hoặc dời giờ. Consumer phải kiểm tra **reservationId/scheduleVersion** và trạng thái hiện tại, bỏ qua version cũ một cách idempotent; broker không tự biết dữ liệu nghiệp vụ đã thay đổi.

## 6. Scheduled delivery không bảo toàn thứ tự gửi

Xét hai message trong cùng queue:

~~~text
10:00:00  Gửi M1, scheduledAt=10:00:15
10:00:01  Gửi M2, không delay
10:00:02  Consumer có thể nhận M2
10:00:15+ Consumer có thể nhận M1
~~~

**Thứ tự gửi M1 trước M2 không bắt buộc là thứ tự nhận**. M1 chưa đủ điều kiện dispatch trong lúc M2 đã sẵn sàng.

| Nhận định sai | Cách hiểu đúng |
| --- | --- |
| Một queue luôn FIFO dù message có lịch | Message chưa đến hạn có thể bị message sẵn sàng vượt qua |
| Due time là thời điểm handler hoàn thành | Due time là thời điểm earliest-eligible |
| Priority cao buộc message chưa đến hạn giao ngay | Priority không bỏ qua lịch |
| Cùng scheduledAt thì mọi consumer xử lý cùng thứ tự | Concurrency, prefetch, redelivery và transaction có thể đổi thứ tự hoàn thành |
| Delay đảm bảo version sau không vượt version trước | Cần thêm sequence, state check hoặc grouping phù hợp |

Nếu thứ tự theo **orderId** bắt buộc, cần mô hình state machine và version/sequence validation ở consumer; đừng dùng lịch gửi làm cơ chế kiểm soát duy nhất.

### Queue, topic và subscriber offline

Với **queue durable** đã tồn tại khi broker route message, message persistent scheduled có thể tiếp tục nằm chờ khi consumer offline, tùy TTL và policy. Với **Topic/MULTICAST**, mỗi subscription có queue/binding riêng. Một **non-durable subscriber tham gia sau publish** không được tự cấp backlog lịch sử chỉ vì message chưa đến hạn; scheduler không tạo durable subscription.

## 7. Cấu hình Artemis và phân biệt redelivery delay

Scheduled delivery là tính năng broker Artemis, không yêu cầu cài một dịch vụ cron riêng để sử dụng timestamp native. Nhưng queue, security và journal phải hợp lệ.

Ví dụ hai queue **ANYCAST durable**, ghép vào phần **addresses** hiện hữu của broker.xml:

~~~xml
<address name="lab.delivery.jms">
    <anycast>
        <queue name="lab.delivery.jms" durable="true"/>
    </anycast>
</address>
<address name="lab.delivery.native">
    <anycast>
        <queue name="lab.delivery.native" durable="true"/>
    </anycast>
</address>
~~~

Đây không phải tệp broker.xml hoàn chỉnh. Nếu broker lab cho auto-create queues, có thể dùng queue tạo động; nếu muốn phép thử ổn định, khai báo trước như trên và tránh duplicate bindings.

Một **address-setting** tùy chọn trong phần address-settings hiện có:

~~~xml
<address-setting match="lab.delivery.#">
    <expiry-address>ExpiryQueue</expiry-address>
    <redelivery-delay>2000</redelivery-delay>
    <max-delivery-attempts>5</max-delivery-attempts>
</address-setting>
~~~

Muốn dùng **ExpiryQueue**, phải có address/queue và routing phù hợp. Đặc biệt, **redelivery-delay** trì hoãn lần giao **sau thất bại/rollback**, khác thời gian giao **đầu tiên** do producer đặt.

| Cơ chế | Ai đặt | Đối tượng được hoãn |
| --- | --- | --- |
| Artemis scheduled delivery | Producer đặt epoch timestamp | Lần dispatch đầu |
| JMS delivery delay | Producer đặt duration | Lần dispatch đầu |
| Redelivery delay | Broker/client retry policy sau rollback | Lần giao lại |
| Producer resend sau timeout | Ứng dụng producer | Lần send mới, có thể là JMS message mới |

Broker redelivery có thể mang cùng **JMSMessageID**, **JMSRedelivered=true** và delivery count tăng. Producer retry có thể sinh JMSMessageID mới dù eventId nghiệp vụ trùng. Cần idempotency độc lập với việc đặt lịch.


## 8. Lab Java/JMS: so sánh bằng hai queue độc lập

Thí nghiệm chạy **Jakarta Messaging trên Artemis**:

- **lab.delivery.jms**: trì hoãn **4 giây** bằng **setDeliveryDelay(4_000L)**.
- **lab.delivery.native**: đặt lịch tại **System.currentTimeMillis() + 7_000L** bằng **_AMQ_SCHED_DELIVERY**.

Cả hai được gửi với **PERSISTENT**, **TTL=0** và **SESSION_TRANSACTED**. Hai queue độc lập ngăn việc prefetch/ordering trong cùng một queue làm nhiễu việc quan sát từng cách scheduling. Dùng message property **labRun** để phân biệt các lượt thực hành.

### Điều kiện và POM

Cần JDK 17+, Maven, Artemis broker và quyền send/consume hai queue ở mục 7. Nếu broker tắt auto-create và không có các queue này, phải cấu hình queue trước. POM minh họa:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>lab.messaging</groupId>
  <artifactId>artemis-scheduling-lab</artifactId>
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

Client artifact là phiên bản tham chiếu; khi triển khai cần đối chiếu compatibility đúng bản broker và JDK. Không trộn **javax.jms** của Classic 5.x với **jakarta.jms** của Artemis Jakarta client trong một chương trình.

### Source ScheduledDeliveryLab.java

Tạo file **src/main/java/ScheduledDeliveryLab.java** trong Maven project thực hành:

~~~java
import jakarta.jms.DeliveryMode;
import jakarta.jms.JMSConsumer;
import jakarta.jms.JMSContext;
import jakarta.jms.Message;
import jakarta.jms.Queue;
import jakarta.jms.TextMessage;
import org.apache.activemq.artemis.jms.client.ActiveMQConnectionFactory;

import java.time.Instant;
import java.util.Objects;
import java.util.UUID;

public final class ScheduledDeliveryLab {
    private static final String SCHEDULE = "_AMQ_SCHED_DELIVERY";

    public static void main(String[] args) throws Exception {
        String url = System.getenv().getOrDefault(
                "BROKER_URL", "tcp://127.0.0.1:61616");
        String user = Objects.requireNonNull(
                System.getenv("BROKER_USER"), "Missing BROKER_USER");
        String password = Objects.requireNonNull(
                System.getenv("BROKER_PASSWORD"), "Missing BROKER_PASSWORD");

        String runId = UUID.randomUUID().toString();
        String selector = "labRun = '" + runId + "'";
        ActiveMQConnectionFactory factory =
                new ActiveMQConnectionFactory(url);

        try (JMSContext sender = factory.createContext(
                     user, password, JMSContext.SESSION_TRANSACTED);
             JMSContext relativeReader = factory.createContext(
                     user, password, JMSContext.SESSION_TRANSACTED);
             JMSContext absoluteReader = factory.createContext(
                     user, password, JMSContext.SESSION_TRANSACTED)) {

            Queue relativeQueue = sender.createQueue("lab.delivery.jms");
            Queue absoluteQueue = sender.createQueue("lab.delivery.native");

            long startedNano = System.nanoTime();

            TextMessage relative = sender.createTextMessage(
                    "JMS delivery delay: 4 seconds");
            relative.setStringProperty("labRun", runId);
            relative.setStringProperty("eventId", runId + "-relative");

            sender.createProducer()
                    .setDeliveryMode(DeliveryMode.PERSISTENT)
                    .setDeliveryDelay(4_000L)
                    .setTimeToLive(0L)
                    .send(relativeQueue, relative);

            long nativeDueEpochMs =
                    System.currentTimeMillis() + 7_000L;
            TextMessage absolute = sender.createTextMessage(
                    "Artemis native scheduled delivery: absolute due time");
            absolute.setStringProperty("labRun", runId);
            absolute.setStringProperty("eventId", runId + "-absolute");
            absolute.setLongProperty(SCHEDULE, nativeDueEpochMs);

            sender.createProducer()
                    .setDeliveryMode(DeliveryMode.PERSISTENT)
                    .setDeliveryDelay(0L)
                    .setTimeToLive(0L)
                    .send(absoluteQueue, absolute);

            // Broker không được dispatch message trước commit JMS.
            sender.commit();

            System.out.println("runId=" + runId
                    + ", native due="
                    + Instant.ofEpochMilli(nativeDueEpochMs));

            JMSConsumer relativeConsumer = relativeReader.createConsumer(
                    relativeReader.createQueue("lab.delivery.jms"),
                    selector);
            JMSConsumer absoluteConsumer = absoluteReader.createConsumer(
                    absoluteReader.createQueue("lab.delivery.native"),
                    selector);

            expectNotReady(relativeConsumer, "JMS delay");
            expectNotReady(absoluteConsumer, "Artemis native");

            Message first = relativeConsumer.receive(15_000L);
            requireMessage(first, "JMS delay");
            printDelivery("JMS delay", first, startedNano);
            relativeReader.commit();

            Message second = absoluteConsumer.receive(15_000L);
            requireMessage(second, "Artemis native");
            printDelivery("Artemis native", second, startedNano);
            absoluteReader.commit();

            System.out.println("PASS: two messages delivered");
        }
    }

    private static void expectNotReady(
            JMSConsumer consumer, String label) {
        Message early = consumer.receive(500L);
        if (early != null) {
            throw new IllegalStateException(
                    label + " delivered unexpectedly early;"
                    + " inspect clocks, queue, and timing");
        }
        System.out.println(label + ": no early delivery");
    }

    private static void requireMessage(
            Message message, String label) {
        if (message == null) {
            throw new IllegalStateException(
                    label + " timed out; inspect scheduled count,"
                    + " queue routing, expiration, and consumer state");
        }
    }

    private static void printDelivery(
            String label, Message message, long startedNano)
            throws Exception {
        long elapsedMs =
                (System.nanoTime() - startedNano) / 1_000_000L;

        System.out.printf(
                "%s received at +%d ms, id=%s,"
                + " JMSTimestamp=%d, JMSDeliveryTime=%d,"
                + " JMSExpiration=%d%n",
                label, elapsedMs,
                message.getJMSMessageID(),
                message.getJMSTimestamp(),
                message.getJMSDeliveryTime(),
                message.getJMSExpiration());

        if (message.propertyExists(SCHEDULE)) {
            System.out.println("native scheduled property="
                    + message.getLongProperty(SCHEDULE));
        }
    }
}
~~~

**Lý giải ranh giới của code:**

- Sender dùng **SESSION_TRANSACTED** và gọi **commit()** sau hai send; nếu chưa commit thì lịch gửi chưa có kết quả hoàn tất.
- Hai consumer dùng context/session riêng; gọi **commit()** sau khi đã nhận và kiểm chứng message, không nhầm ACK giữa queue.
- **JMSContext** thông thường có auto-start khi tạo consumer; khác với Connection theo API cổ điển cần gọi start() tường minh.
- **labRun** là selector cô lập lượt test. Nó **không xóa** message của lượt trước; khi không dùng nữa cần dọn backlog của queue lab một cách an toàn.
- **getJMSDeliveryTime()** có ý nghĩa chuẩn với JMS delivery delay. Với property native, không dựa vào việc header này được đồng bộ tự động theo mọi phiên bản.
- Phép thử nhận sớm bằng receive(500L) chỉ có giá trị khi sender commit và consumer khởi tạo **trước hạn 4/7 giây**. Trên máy quá chậm, cần xem timestamp/log thay vì suy broker hoạt động sai.
- Chương trình không thực hiện side effect DB, vì trọng tâm là **delivery eligibility**, không phải một workflow transaction nghiệp vụ hoàn chỉnh.


## 9. Chạy lab và đọc kết quả

Trong terminal PowerShell tại thư mục Maven đã tạo:

~~~powershell
$env:BROKER_URL = "tcp://127.0.0.1:61617"
$env:BROKER_USER = "artemis_app"
$env:BROKER_PASSWORD = "<your-artemis-password>"

mvn -q compile exec:java "-Dexec.mainClass=ScheduledDeliveryLab"
~~~

Nếu Artemis publish trên host port **61616**, chỉnh URL tương ứng. Khi Java chạy trong container trên cùng Docker network, dùng service DNS và cổng nội bộ; không mặc định localhost của container là broker. Thay mật khẩu placeholder bằng secret thật. Docker Compose .env không tự động nạp vào PowerShell chạy Maven.

Kết quả kỳ vọng về **ngữ nghĩa**, không phải mili giây tuyệt đối:

~~~text
runId=..., native due=...
JMS delay: no early delivery
Artemis native: no early delivery
JMS delay received at +4xxx ms, JMSDeliveryTime=...
Artemis native received at +7xxx ms, JMSDeliveryTime=...
PASS: two messages delivered
~~~

Nếu thời gian nhận lớn hơn kỳ vọng, kiểm tra broker load, transaction commit, scheduled count, consumer readiness, network và lệch đồng hồ. Không dùng một lần chạy để tuyên bố scheduler đảm bảo real-time. Nếu quá trình gửi và tạo consumer mất nhiều giây, phép thử **expectNotReady()** có thể mất ý nghĩa; dùng trace timestamp và thử lại trên broker lab ít tải.

### Tại sao hai queue?

Nếu dùng cùng queue, prefetch, message priority, dispatch và ACK có thể làm khó việc quy kết thời gian nhận cho từng phương pháp scheduling. Hai queue độc lập giúp đối chiếu **JMSDeliveryTime**, **native due timestamp** và thời điểm receive rõ hơn.

## 10. ActiveMQ Classic sử dụng scheduler extension khác

ActiveMQ Classic 5.x và Artemis **không dùng chung mọi property scheduling**. Với Classic, broker scheduler cần được bật theo release/cấu hình phù hợp, thường với **schedulerSupport="true"** trong broker XML. Classic có các property như **AMQ_SCHEDULED_DELAY**, **AMQ_SCHEDULED_PERIOD**, **AMQ_SCHEDULED_REPEAT** và **AMQ_SCHEDULED_CRON**.

Ví dụ Classic JMS client (namespace **javax.jms**):

~~~java
import org.apache.activemq.ScheduledMessage;

// producer và message thuộc ActiveMQ Classic JMS client.
message.setLongProperty(
        ScheduledMessage.AMQ_SCHEDULED_DELAY, 5_000L);
producer.send(message);
~~~

**AMQ_SCHEDULED_DELAY** ở Classic là **duration tương đối**, không phải timestamp tuyệt đối như **_AMQ_SCHED_DELIVERY** ở Artemis. Các tùy chọn repeat/cron của Classic không mặc nhiên có cùng API/semantics ở Artemis.

| Cách viết | Kiểu thời gian | Phạm vi |
| --- | --- | --- |
| **setDeliveryDelay(5_000L)** | Duration 5 giây | JMS 2.0/Jakarta Messaging |
| **_AMQ_SCHED_DELIVERY = epochMs** | Timestamp tuyệt đối | Artemis extension |
| **AMQ_SCHEDULED_DELAY = 5_000L** | Duration 5 giây | Classic scheduler extension |
| **_AMQ_SCHED_DELIVERY = 5_000L** | Timestamp đã ở quá khứ | Sai nếu định hoãn 5 giây ở Artemis |
| **setTimeToLive(5_000L)** | TTL 5 giây | Expiration, không phải scheduling |
| **redelivery-delay = 5000** | Chờ trước retry sau lỗi | Broker retry, không phải lịch giao lần đầu |

Chỉ sử dụng **setDeliveryDelay** nếu client JMS và provider thực sự hỗ trợ API JMS 2.0/Jakarta Messaging. Một thư viện chỉ triển khai JMS 1.1 có thể không có phương thức này; đừng xem lỗi compile là lỗi scheduler của broker.

## 11. Quan sát scheduled references và xử lý sự cố

Artemis có khả năng báo **scheduled message count** theo queue qua các công cụ quản trị. Tùy phiên bản, scheduled/ready/delivering có thể được trình bày khác nhau. Vì vậy phải quan sát cả **scheduled count**, **message count/ready**, **delivering/in-flight**, consumer count, expiry và DLQ.

| Triệu chứng | Nguyên nhân có thể | Kiểm tra |
| --- | --- | --- |
| Message được giao ngay | Epoch seconds thay vì ms, due time trong quá khứ, delay bằng 0 | Chuyển epoch thành Instant, kiểm tra headers và client |
| Message bị hoãn nhiều giờ | Nhầm UTC/local timezone hoặc clock lệch | ZoneId, NTP, thời gian broker |
| Đến hạn nhưng không có receive | Không consumer, sai queue, selector/permission, backlog | Queue binding, consumer count, scheduled vs ready |
| Message biến mất khi đang scheduled | TTL hết hạn, queue auto-delete hoặc policy khác | JMSExpiration, expiry metrics/queue |
| Restart broker rồi không còn message | Mode/queue/storage không đủ bền hoặc đã expire | PERSISTENT, queue durable, journal và volume |
| Message xuất hiện lần hai | Rollback/ACK lỗi hoặc producer resend | JMSRedelivered, JMSXDeliveryCount, eventId |
| Giao sau due time lâu | Broker bận, consumer bị nghẽn, flow control/paging | Broker load, ready count, latency |
| Scheduled count giảm nhưng nghiệp vụ chưa chạy | Message đã trở nên ready hoặc đã dispatch | In-flight, DB commit, JMS ACK |

Nên log ít nhất:

~~~text
eventId=reminder-R100-v2
destination=lab.delivery.native
scheduledAtEpochMs=...
jmsDeliveryTimeEpochMs=...
jmsExpirationEpochMs=...
producerCommitOutcome=CONFIRMED
observedAt=...
businessAppliedAt=...
jmsAckOutcome=...
~~~

**Queue depth = 0** hoặc scheduled count giảm **không chứng minh** nghiệp vụ đã hoàn tất. Đối soát bằng eventId và kết quả side effect trong hệ thống nghiệp vụ.

### Hủy hoặc dời lịch

JMS không có API portable **cancelScheduledMessage(eventId)**. Artemis có các thao tác quản trị scheduled messages tùy phiên bản/quyền operator, nhưng việc hủy có thể đua với quá trình dispatch sát due time. Với reminder, thiết kế **scheduleVersion** trong DB:

1. Tạo eventId/scheduleVersion cho lịch hiện hành.
2. Khi thay đổi lịch, tăng version ở nguồn sự thật và phát reminder mới.
3. Khi consumer nhận reminder cũ, kiểm tra version và trạng thái reservation.
4. Nếu không còn hợp lệ, không tạo side effect, ACK có chủ đích.
5. Nếu message được redeliver hoặc producer gửi lại, deduplicate bằng eventId.

Broker kiểm soát **khi nào được giao**; DB nghiệp vụ quyết định **có còn được thực hiện hay không**.

## 12. Thực hành kiểm chứng điều kiện biên

**A — Epoch seconds so với milliseconds.** Dùng cùng một mốc tương lai từ **Instant.getEpochSecond()** và **Instant.toEpochMilli()**. Dự đoán kết quả khi gán nhầm seconds vào **_AMQ_SCHED_DELIVERY**; chỉ thử trên queue lab.

**B — Gửi trước nhưng nhận sau.** Gửi M1 với native due +10 giây, rồi M2 không delay vào một queue. Ghi thứ tự nhận và lý giải vì sao M2 có thể vượt M1.

**C — Chưa commit thì chưa dispatch.** Gửi scheduled message +3 giây trong Session transacted, chờ 5 giây rồi mới commit. Kiểm tra không nhận trước commit; lặp với rollback để kiểm tra không có bản gửi đã commit.

**D — Delay và expiration.** Thay đổi timeToLive cho message có setDeliveryDelay, in **JMSDeliveryTime** và **JMSExpiration**. Quan sát queue nguồn và expiry address khi được cấu hình.

**E — Consumer offline.** Gửi persistent scheduled message tới queue durable, tắt consumer tới sau due rồi mở lại. So sánh với một JMS Topic non-durable subscription được tạo sau lúc publish.

**F — Redelivery khác first-delivery delay.** Gửi message ngay, consumer receive rồi rollback, đo delay giao lại. So với một message mới có JMS delivery delay; quan sát JMSRedelivered và JMSXDeliveryCount khi provider hỗ trợ.

## 13. Checklist nghiệm thu

| Câu hỏi | Câu trả lời phải có |
| --- | --- |
| Artemis native property là gì? | **_AMQ_SCHED_DELIVERY**, timestamp epoch milliseconds |
| JMS delivery delay nhận gì? | **setDeliveryDelay** nhận duration milliseconds |
| JMSDeliveryTime có nghĩa gì? | Thời điểm sớm nhất cho phép delivery theo JMS |
| Due time có phải lúc xử lý xong? | Không, còn dispatch, consumer, DB và ACK |
| Transaction chưa commit thì sao? | Chưa được dispatch như message đã commit |
| TTL có thể làm mất message chờ không? | Có thể expire trước khi được giao; kiểm tra header/policy |
| Queue còn đảm bảo thứ tự gửi tuyệt đối không? | Không, delayed message có thể bị vượt |
| Consumer offline ảnh hưởng gì? | Phụ thuộc lifecycle queue/subscription, persistence và TTL |
| Classic và Artemis có dùng chung extension? | Không, property và broker config khác |
| Khi lịch bị hủy hoặc thay đổi? | Kiểm tra scheduleVersion/trạng thái và xử lý idempotent |

**Kết luận:** **Scheduled delivery của Artemis** dùng thời điểm tuyệt đối **_AMQ_SCHED_DELIVERY**, còn **JMS delivery delay** dùng **setDeliveryDelay** với khoảng chờ tương đối và **JMSDeliveryTime** do provider quản lý. Cả hai chỉ quyết định **lúc message đủ điều kiện được giao**, không thay transaction, TTL, thứ tự nghiệp vụ hoặc bảo đảm thời điểm consumer xử lý hoàn tất. Thiết kế đáng tin cậy cần thêm queue/subscription phù hợp, persistence, eventId, scheduleVersion, và quan sát đủ các mốc thời gian.
