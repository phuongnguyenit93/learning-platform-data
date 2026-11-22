# Đóng nhóm, phân phối lại nhóm và giới hạn khi một nhóm quá tải

> **Chương:** Thứ tự và thời gian  
> **Học phần:** `INTEGRATION_MESSAGING_MESSAGE_BROKER_ACTIVEMQ` — Apache ActiveMQ Classic và Artemis trong giao tiếp bất đồng bộ với queue/topic, routing, Java/JMS, acknowledgment, transaction, redelivery, DLQ, bảo mật và vận hành broker đáng tin cậy.  
> **Trọng tâm:** Đóng **JMS message group**, gán lại quyền sở hữu khi nhóm kết thúc hoặc consumer thay đổi, và xử lý **hot group** khi một khóa nhóm chiếm phần lớn lưu lượng. Ví dụ Java dùng ActiveMQ Artemis 2.40.0 với `jakarta.jms`; khác biệt của ActiveMQ Classic được nêu riêng.

## 1. Bài toán: có bốn consumer nhưng một nhóm vẫn tắc

Queue `lab.order.groups` nhận message cập nhật đơn hàng. Mỗi message được gắn `JMSXGroupID = orderId` nhằm giữ các thay đổi của **cùng đơn hàng** trên cùng một consumer trong lúc nhóm đang được sở hữu. Có bốn worker, nhưng một order hoặc tenant có lưu lượng rất cao tạo ra phần lớn message.

~~~text
ANYCAST queue lab.order.groups
│
├── order-hot: H1,H2,H3,H4,H5,H6,... -> Consumer W1 (giữ group)
├── order-021: A1,A2,A3           -> Consumer W2
├── order-022: B1,B2              -> Consumer W3
└── order-023: C1,C2              -> Consumer W4

W1 bận liên tục, W2..W4 có thể nhàn rỗi.
Thêm W5 không tự biến H1..H6 thành công việc song song.
~~~

Vì thông điệp của **một group** cần được xử lý theo một chuỗi logic, message grouping tạo **affinity** giữa nhóm và consumer. Đây chính là lý do cơ chế này hữu ích cho tính đúng đắn nhưng có thể gây nghẽn.

Ba khái niệm khác nhau:

1. **Đóng nhóm:** phát message đặc biệt `JMSXGroupSeq=-1` để báo ranh giới kết thúc một chuỗi logic và cho phép broker giải phóng group association.
2. **Phân phối lại nhóm:** broker có thể chọn consumer khác khi group không còn bị giữ, khi consumer mất hoặc khi có cơ chế rebalance phù hợp.
3. **Giải quyết quá tải nhóm:** thay group key, giảm thời gian xử lý hoặc giới hạn lưu lượng khi invariant nghiệp vụ cho phép; **close hoặc rebalance không tự tăng số consumer đồng thời xử lý một group**.

Bài này đi sâu ba vấn đề đó thay vì lặp phần tổng quan queue/topic.

## 2. Group ownership thực sự hoạt động thế nào?

JMS producer đặt ít nhất thuộc tính `JMSXGroupID`:

~~~java
TextMessage message = session.createTextMessage("order updated");
message.setStringProperty("JMSXGroupID", "order-1029");
message.setIntProperty("JMSXGroupSeq", 7);
producer.send(message);
~~~

| Trường | Vai trò | Giới hạn |
|---|---|---|
| `JMSXGroupID` | Khóa chuỗi cho group; broker dùng để duy trì affinity của các message cùng group trên một queue | Không phải khóa idempotency; không là mutex toàn bộ hệ thống |
| `JMSXGroupSeq > 0` | Chỉ số do producer cung cấp cho chuỗi logic | Không ép broker sắp xếp lại các message producer đã gửi sai thứ tự |
| `JMSXGroupSeq = -1` | Marker đóng group | Không xóa queue, không hủy dữ liệu, không tự chuyển hết backlog sang worker khác |
| `JMSXGroupFirstForConsumer` | Dấu hiệu first-for-consumer do một số provider/cấu hình cung cấp | Không được mặc định tồn tại hoặc mang nghĩa “seq=1” |
| `eventId`, `aggregateVersion` | Trường nghiệp vụ để dedup, kiểm tra thứ tự cập nhật DB | Không thay thế cơ chế group ownership của broker |

Điểm hay bị bỏ sót là **chuẩn hóa group ID**. `tenant-1` và `Tenant-1` là các chuỗi khác nhau; vô tình tạo hai group có thể cho cùng aggregate được xử lý song song. Nếu nhiều producer cùng phát tới một aggregate, tất cả phải dùng **cùng quy tắc sinh key**.

### 2.1. Bản đồ sở hữu group

~~~mermaid
stateDiagram-v2
    [*] --> Free: Chưa có consumer sở hữu group
    Free --> W1: Broker gán khi dispatch
    W1 --> W1: Các message tiếp theo cùng JMSXGroupID
    W1 --> Free: Đóng nhóm / consumer rời / rebalance
    Free --> W2: Có thể chọn consumer khác
    Free --> W1: Cũng có thể chọn lại consumer cũ
    W2 --> Free: Đóng / rời / rebalance
~~~

- Broker cố gắng giữ các delivery của cùng group về **một owner tại một thời điểm** theo group policy.
- Ownership có thể thay đổi khi một điều kiện giải phóng xảy ra.
- **Không bảo đảm** rằng group sau khi đóng sẽ đến consumer khác.
- Consumer mới tham gia **không mặc nhiên** làm broker tái phân bố tất cả group đang hoạt động.
- Hành vi cần xem cùng backlog, in-flight delivery, ACK, routing và policy của phiên bản broker.

Một `JMSXGroupID` trên **hai queue khác nhau** không tạo ra một owner chung xuyên queue. Với topic/multicast, các subscription có các queue tiêu thụ riêng. Nếu có nhiều broker/cluster, cấu hình grouping giữa các node phải được xem xét riêng, không suy rằng chuỗi property giống nhau tự động tạo khóa toàn cluster.

### 2.2. Grouping không là bộ sắp xếp lại theo số

Ví dụ producer P1 gửi `seq=3`, producer P2 gửi `seq=2`, rồi P1 gửi `seq=1` từ các connection khác nhau. Broker **không mặc nhiên giữ message 3 và 2 chờ 1** như một reorder buffer. `JMSXGroupSeq` không thay thế thứ tự enqueue thực tế và một versioning protocol của ứng dụng.

Nếu cần thứ tự **business commit** theo aggregate, thiết kế nguồn `aggregateVersion` tin cậy (ví dụ version DB/outbox), bảo đảm gửi theo chuỗi phù hợp, và consumer có version guard. Group affinity chỉ là **một mắt xích**.

## 3. Đóng một nhóm bằng message có `JMSXGroupSeq=-1`

Producer gửi một message với **cùng `JMSXGroupID`** và số thứ tự **-1**. Message này vẫn được delivery tới consumer như một message bình thường; consumer cần xử lý và ACK/commit theo hợp đồng đã chọn.

~~~text
                  Broker queue                   Consumer đang giữ G
send(G,seq=1)  ------------------------------->  xử lý G1 -> ACK
send(G,seq=2)  ------------------------------->  xử lý G2 -> ACK
send(G,seq=3)  ------------------------------->  xử lý G3 -> ACK
send(G,seq=-1) ------------------------------->  nhận CLOSE -> ACK/commit
                                                        |
                                             group đủ điều kiện giải phóng
                                                        |
send(G,epoch2) ------> broker chọn owner mới hoặc cũ --> nhận tiếp
~~~

**Marker -1 không phải thao tác quản trị xóa dữ liệu.** Nó có ý nghĩa đối với **group assignment**. Message đóng cần đi qua routing và delivery bình thường; nếu producer send/commit marker xong, **chưa thể kết luận** consumer đã ACK marker.

### 3.1. Khi nào có thể coi đợt cũ đã đóng an toàn?

Nếu yêu cầu nghiệp vụ là “không xử lý event của epoch mới trước khi epoch cũ hoàn tất”, thì ứng dụng phải tổ chức **hàng rào xử lý**:

1. Producer (hoặc bộ điều phối các producer) xác nhận không còn message cũ đang được phát cho group.
2. Gửi marker `JMSXGroupSeq=-1` **sau** các event thuộc epoch cũ theo thứ tự gửi đã được bảo đảm.
3. Consumer xử lý message trước đó, nhận marker và chỉ ACK/commit marker khi điều kiện kết thúc epoch đã thực sự thỏa mãn.
4. Một **tín hiệu hoàn tất đáng tin cậy của ứng dụng** (ví dụ status DB/completion event) cho phép producer bắt đầu epoch mới khi invariant yêu cầu rào chắn nghiêm ngặt.

Điều kiện thứ tư đặc biệt quan trọng nếu nhiều producer hoặc nhiều dịch vụ cùng phát group. **JMS producer commit marker không phải ACK nghiệp vụ từ consumer.**

Khi consumer rollback message marker, message có thể redeliver; không tuyên bố chắc nhóm đã đóng theo dự định chỉ vì có log “close sent”. Chi tiết thời điểm release ownership cần kiểm tra theo phiên bản/broker và trạng thái ACK.

### 3.2. Đóng nhóm không nhất thiết chuyển nó sang worker khác

Giả sử W1 đang sở hữu `order-42` và W2 đang rảnh. Sau marker -1 được xử lý, broker được phép tạo association tiếp theo. Tùy dispatch, consumer availability và group map, nó có thể **lại gán cho W1**.

Vì thế phép thử chỉ được kết luận:

- Đã nhận và commit **close marker**.
- Event sau marker được xử lý theo association tiếp theo của group.
- Nếu group chuyển sang W2 thì đó là **kết quả có thể xảy ra**, không phải điều kiện bắt buộc để test PASS.

Nếu muốn thử một phép **reassignment** dễ nhìn, có thể cho worker giữ group đóng connection sau khi xử lý xong, rồi gửi event mới và quan sát worker còn sống. Nhưng cần ghi rõ **consumer leave** cũng là một nguyên nhân giải phóng association; khi đó không được gán mọi kết quả riêng cho close marker.

## 4. Đóng, rebalance và failover là các sự kiện khác nhau

| Sự kiện | Phạm vi | Lưu ý kiểm chứng |
|---|---|---|
| `JMSXGroupSeq=-1` | Chủ động kết thúc một **group** | Đợi xử lý/ACK marker; không đồng nghĩa xóa queue |
| Consumer `close()` | Consumer rời queue; những group do nó giữ có thể gán lại | Kiểm tra message chưa ACK, reconnect và timing |
| Connection mất/process crash | Broker phát hiện worker không còn, có thể redeliver | Idempotency bắt buộc khi DB đã commit trước ACK |
| Consumer mới được thêm | Thay đổi số consumer có sẵn | Nhóm cũ có thể tiếp tục dính owner nếu không có rebalance |
| Group rebalance | Broker điều chỉnh association giữa các group | Không tách một group thành nhiều owner xử lý song song |
| Broker restart/HA failover | Thay đổi topology/ownership | Có thể thay đổi assignment, cần kiểm thử replay và thứ tự nghiệp vụ |

### 4.1. Classic và Artemis khác nhau ở lớp cấu hình

**ActiveMQ Classic 5.x** dùng `JMSXGroupID`, hỗ trợ marker `JMSXGroupSeq=-1`, và có các chiến lược group map như bucket/hash và cache. Khi nhiều group được ánh xạ vào cùng bucket, chúng có thể cùng gắn vào một consumer, làm mất cơ hội song song giữa các group vốn độc lập. Provider có thể đặt `JMSXGroupFirstForConsumer` để ứng dụng biết khi message đầu của group được giao cho consumer.

**ActiveMQ Artemis** có `group-buckets`, `group-rebalance`, `group-rebalance-pause-dispatch`, `group-first-key` ở address settings trên các bản hỗ trợ. Các lựa chọn đó điều khiển ánh xạ và phân phối lại **các group**, nhưng không làm giảm yêu cầu tuần tự của **một group**.

Artemis Core API thuần có biểu diễn group ID native riêng (ví dụ header `_AMQ_GROUP_ID`). Ví dụ Java trong bài dùng **JMS**, nên cấu hình `JMSXGroupID` và `JMSXGroupSeq` ở JMS message.

Không copy XML `broker.xml` Artemis sang `activemq.xml` của Classic, hoặc chọn client Classic chỉ vì cả hai broker có cổng 61616. Muốn so sánh hành vi, giữ nguyên mục tiêu thí nghiệm và chọn **broker/client/config đúng phiên bản**.

## 5. Cấu hình Artemis để quan sát vòng đời group

Với Artemis có queue ANYCAST riêng cho lab, trích đoạn dưới được thêm **bên trong `<addresses>` đang tồn tại** của `broker.xml`:

~~~xml
<address name="lab.order.groups">
    <anycast>
        <queue name="lab.order.groups"/>
    </anycast>
</address>
~~~

Nếu queue đã tồn tại hoặc môi trường thử có auto-create, không tạo trùng address/queue. Dữ liệu lab cần chạy trên queue tách khỏi production.

### 5.1. Address settings cho rebalance/bucket

Trích đoạn **bên trong `<address-settings>`** của Artemis:

~~~xml
<address-setting match="lab.order.groups">
    <group-buckets>128</group-buckets>
    <group-rebalance>true</group-rebalance>
    <group-rebalance-pause-dispatch>true</group-rebalance-pause-dispatch>
    <group-first-key>JMSXGroupFirstForConsumer</group-first-key>
</address-setting>
~~~

Nếu đã có `<address-setting match="lab.order.groups">`, hãy **hợp nhất thuộc tính** cùng rule thay vì thêm cấu hình trùng/mâu thuẫn. Đây là ví dụ cho một phiên bản Artemis có hỗ trợ các phần tử trên; cần xác minh lại với broker đang chạy trước khi áp dụng và restart/reload theo quy trình cấu hình.

| Thuộc tính | Mục đích | Đánh đổi |
|---|---|---|
| `group-buckets` | Giới hạn số bucket để broker quản lý mapping group | Bucket collision có thể khiến nhiều group cùng consumer; giá trị 128 chỉ dùng cho lab |
| `group-rebalance` | Cho phép rebalance association theo thay đổi tập consumer được cơ chế hỗ trợ | Group ownership có thể chuyển và tạo thêm chi phí điều phối |
| `group-rebalance-pause-dispatch` | Phối hợp pause dispatch khi rebalance theo cách broker hỗ trợ để xử lý các delivery liên quan | Có thể tăng độ trễ khi membership thay đổi |
| `group-first-key` | Tên property broker gắn để nhận biết message đầu của group tới một consumer | Chỉ là tín hiệu assignment, không đồng nghĩa `seq=1` hay đã xử lý lịch sử |

**Lưu ý:** explicit close có thể sử dụng **mà không cần bật group rebalance**. Rebalance phục vụ phân phối lại các group khi tập consumer thay đổi, không thay thế ranh giới logic do producer tạo ra.

Không suy rằng tăng `group-buckets` sẽ tự sửa hot group: collision của **nhiều group** và một group quá nóng là **hai nguyên nhân khác nhau**.

## 6. Lab Java: hai consumer cạnh tranh và marker đóng nhóm

Ví dụ dùng **JDK 17**, **Artemis 2.40.0**, Jakarta JMS 3.1. Giả định broker Artemis đã chạy tại `tcp://127.0.0.1:61616` với acceptor phù hợp client native, user có quyền send/consume queue `lab.order.groups`.

### 6.1. Maven

Cấu trúc:

~~~text
group-lifecycle-lab/
├── pom.xml
└── src/main/java/lab/GroupLifecycleLab.java
~~~

`pom.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>lab</groupId>
  <artifactId>group-lifecycle-lab</artifactId>
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

### 6.2. Producer và worker có thể chạy trong các terminal riêng

Tạo `src/main/java/lab/GroupLifecycleLab.java`:

~~~java
package lab;

import java.util.concurrent.TimeUnit;

import jakarta.jms.ConnectionFactory;
import jakarta.jms.DeliveryMode;
import jakarta.jms.JMSConsumer;
import jakarta.jms.JMSContext;
import jakarta.jms.Message;
import jakarta.jms.Queue;
import jakarta.jms.TextMessage;
import org.apache.activemq.artemis.jms.client.ActiveMQConnectionFactory;

public final class GroupLifecycleLab {
    private static final String QUEUE_NAME = "lab.order.groups";
    private static final String HOT = "order-hot";
    private static final String COLD = "order-cold";

    private GroupLifecycleLab() {}

    public static void main(String[] args) throws Exception {
        if (args.length == 0) {
            throw new IllegalArgumentException(
                "Modes: worker <name> | seed | close | next | stress");
        }

        String url = System.getenv().getOrDefault(
            "BROKER_URL", "tcp://127.0.0.1:61616");
        String user = requiredEnv("BROKER_USER");
        String password = requiredEnv("BROKER_PASSWORD");
        ConnectionFactory factory = new ActiveMQConnectionFactory(url);

        if ("worker".equals(args[0])) {
            if (args.length != 2) {
                throw new IllegalArgumentException("worker cần tên");
            }
            runWorker(factory, user, password, args[1]);
            return;
        }

        try (JMSContext ctx = factory.createContext(
                user, password, JMSContext.SESSION_TRANSACTED)) {
            Queue queue = ctx.createQueue(QUEUE_NAME);
            switch (args[0]) {
                case "seed" -> {
                    for (int i = 1; i <= 5; i++) {
                        publish(ctx, queue, HOT, "e1", i,
                                "hot-" + i);
                        if (i <= 3) {
                            publish(ctx, queue, COLD, "e1", i,
                                    "cold-" + i);
                        }
                    }
                }
                case "close" -> publish(ctx, queue,
                        HOT, "e1", -1, "END_EPOCH_1");
                case "next" -> {
                    for (int i = 1; i <= 3; i++) {
                        publish(ctx, queue, HOT, "e2", i,
                                "new-" + i);
                    }
                }
                case "stress" -> {
                    for (int i = 1; i <= 60; i++) {
                        publish(ctx, queue, HOT, "stress", i,
                                "hot-stress-" + i);
                        if (i % 3 == 0) {
                            String otherGroup = "order-cold-" + (i / 3);
                            publish(ctx, queue, otherGroup, "stress", 1,
                                    "cold-stress-" + (i / 3));
                        }
                    }
                }
                default -> throw new IllegalArgumentException(
                        "Mode không hợp lệ: " + args[0]);
            }
        }
    }

    private static void publish(
            JMSContext ctx, Queue queue,
            String group, String epoch, int seq, String body)
            throws Exception {
        TextMessage m = ctx.createTextMessage(body);
        m.setStringProperty("JMSXGroupID", group);
        m.setIntProperty("JMSXGroupSeq", seq);
        m.setStringProperty("eventId", group + ":" + epoch + ":" + seq);

        ctx.createProducer()
            .setDeliveryMode(DeliveryMode.PERSISTENT)
            .send(queue, m);
        ctx.commit(); // Chốt giao dịch JMS phía producer.

        System.out.println("PUBLISHED group=" + group
                + " seq=" + seq + " epoch=" + epoch);
    }

    private static void runWorker(ConnectionFactory factory,
            String user, String password, String name) throws Exception {

        // Mỗi process dùng một transacted Session/Consumer.
        try (JMSContext ctx = factory.createContext(
                user, password, JMSContext.SESSION_TRANSACTED)) {
            JMSConsumer consumer = ctx.createConsumer(
                    ctx.createQueue(QUEUE_NAME));
            long deadline = System.nanoTime()
                    + TimeUnit.SECONDS.toNanos(120);

            System.out.println("WORKER_START " + name);
            while (System.nanoTime() < deadline) {
                Message m = consumer.receive(1000);
                if (m == null) {
                    continue;
                }
                try {
                    String group = m.getStringProperty("JMSXGroupID");
                    int seq = m.getIntProperty("JMSXGroupSeq");
                    String eventId = m.getStringProperty("eventId");
                    String body = m.getBody(String.class);

                    boolean first = m.propertyExists(
                            "JMSXGroupFirstForConsumer")
                            && m.getBooleanProperty(
                                    "JMSXGroupFirstForConsumer");

                    System.out.println("RECEIVED worker=" + name
                            + " group=" + group
                            + " seq=" + seq
                            + " firstForConsumer=" + first
                            + " eventId=" + eventId
                            + " body=" + body);

                    if (HOT.equals(group) && seq != -1) {
                        Thread.sleep(300); // Mô phỏng hot group.
                    }

                    // Production: DB transaction + idempotency trước ACK.
                    ctx.commit(); // ACK của delivery qua JMS transaction.
                    System.out.println((seq == -1
                            ? "CLOSE_MARKER_COMMITTED"
                            : "MESSAGE_COMMITTED")
                            + " worker=" + name
                            + " group=" + group
                            + " seq=" + seq);
                } catch (Exception e) {
                    System.err.println("WORKER_FAILED " + e.getMessage());
                    ctx.rollback();
                    throw e; // Không lặp poison message vô hạn trong lab.
                }
            }
            System.out.println("WORKER_STOP " + name);
        }
    }

    private static String requiredEnv(String name) {
        String value = System.getenv(name);
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException("Thiếu " + name);
        }
        return value;
    }
}
~~~

**Các quyết định quan trọng:**

- `publish` dùng **`JMSXGroupID`**, `JMSXGroupSeq` và `ctx.commit()`; producer commit **không** nói consumer đã ACK.
- Mỗi worker có **Session riêng**; vì vậy hai worker có thể nhận các group khác nhau. Các callback/worker không chia sẻ một JMS Session.
- Consumer ACK qua `ctx.commit()` **sau** xử lý mô phỏng; việc log thành công không phải DB transaction thực. Production cần business commit và dedup theo `eventId` trước JMS commit.
- `CLOSE_MARKER_COMMITTED` được in khi consumer đã commit marker. Nó là điểm quan sát thích hợp để điều phối bài lab thành các pha; với production nên có completion/status protocol thực.
- `firstForConsumer` có thể thiếu nếu broker không gắn property; `false` không có nghĩa chắc chắn group không được gán lại.
- `eventId` chỉ minh họa từ group/epoch/seq. Không dùng `JMSXGroupSeq` làm khóa idempotency toàn hệ thống.

### 6.3. Chạy hai worker để quan sát affinity

Đặt biến môi trường của broker lab (PowerShell):

~~~powershell
$env:BROKER_URL = "tcp://127.0.0.1:61616"
$env:BROKER_USER = "lab"
$env:BROKER_PASSWORD = "mat-khau-broker-lab"
mvn -q -DskipTests package
~~~

Mở hai terminal worker, cùng thư mục Maven, cùng bộ biến môi trường:

~~~powershell
# Terminal W1
mvn -q exec:java "-Dexec.mainClass=lab.GroupLifecycleLab" "-Dexec.args=worker W1"
~~~

~~~powershell
# Terminal W2
mvn -q exec:java "-Dexec.mainClass=lab.GroupLifecycleLab" "-Dexec.args=worker W2"
~~~

Mỗi worker chạy khoảng **120 giây**. Ở terminal thứ ba, gửi dữ liệu ban đầu:

~~~powershell
mvn -q exec:java "-Dexec.mainClass=lab.GroupLifecycleLab" "-Dexec.args=seed"
~~~

Kết quả ví dụ **không bắt buộc assignment y hệt**:

~~~text
RECEIVED worker=W1 group=order-hot seq=1 ...
MESSAGE_COMMITTED worker=W1 group=order-hot seq=1
RECEIVED worker=W1 group=order-hot seq=2 ...
MESSAGE_COMMITTED worker=W1 group=order-hot seq=2
RECEIVED worker=W2 group=order-cold seq=1 ...
MESSAGE_COMMITTED worker=W2 group=order-cold seq=1
~~~

Có thể cả `order-hot` và `order-cold` cùng được broker gán về một worker; đó không phải lỗi test. Đối chiếu owner/chuỗi xử lý theo **từng group**.

Đợi log đã commit cả **5 message hot và 3 message cold**. Gửi close marker:

~~~powershell
mvn -q exec:java "-Dexec.mainClass=lab.GroupLifecycleLab" "-Dexec.args=close"
~~~

Đợi worker in:

~~~text
RECEIVED ... group=order-hot seq=-1 ... END_EPOCH_1
CLOSE_MARKER_COMMITTED worker=... group=order-hot seq=-1
~~~

Sau khi marker được xử lý, gửi epoch tiếp theo:

~~~powershell
mvn -q exec:java "-Dexec.mainClass=lab.GroupLifecycleLab" "-Dexec.args=next"
~~~

Quan sát worker sở hữu `order-hot` ở epoch mới. **W1 vẫn có thể tiếp tục nhận**; phép thử không yêu cầu đổi sang W2. Nếu cần minh họa điều kiện reassignment rõ hơn, hãy cho worker đang giữ group rời đi một cách có kiểm soát và quan sát worker còn lại, nhưng đó là kịch bản **consumer leave** cùng với close.

### 6.4. Thử một hot group

Trong môi trường queue thử riêng đã được xử lý hết message cũ, chạy:

~~~powershell
mvn -q exec:java "-Dexec.mainClass=lab.GroupLifecycleLab" "-Dexec.args=stress"
~~~

Producer phát **60 message** vào đúng một group `order-hot` và **20 message** cho 20 group lạnh khác nhau. Worker mô phỏng mỗi message hot tốn **300 ms**, nên 60 message hot cần xấp xỉ **18 giây xử lý tuần tự**, chưa kể overhead.

Tăng số worker từ 2 lên 4 có thể giúp các group lạnh được phân phối nhanh hơn nhưng **không khiến hai consumer xử lý đồng thời một group nóng**. Nếu queue đang tồn từ một lần chạy trước, hoặc các consumer khác đang hoạt động, hãy đối chiếu message ID/event ID trước khi suy ra bottleneck.

## 7. Công thức giải thích tại sao hot group không scale tuyến tính

Ký hiệu:

- \(\lambda\): tốc độ message vào queue, tính theo message/giây.
- \(p\): tỷ lệ message của một group nóng `G`.
- \(\lambda_G=p\lambda\): tốc độ đến của group nóng.
- \(s_G\): thời gian xử lý trung bình cho một message trong group.
- \(\mu_G\approx 1/s_G\): tốc độ phục vụ lý tưởng của **một luồng xử lý tuần tự** cho group.

Điều kiện không tích backlog lâu dài của group (trong mô hình đơn giản) là:

\[
\lambda_G<\mu_G.
\]

**Ví dụ:** queue nhận **120 msg/s**; một tenant đóng góp **60%**, tức \(\lambda_G=72\) msg/s. Worker cần **100 ms** cho một message của tenant, tức \(\mu_G\approx 10\) msg/s. Dòng đến của group vượt khả năng xử lý khoảng **62 msg/s**, và backlog riêng nhóm tiếp tục tăng. Thêm nhiều consumer **không đổi** bất đẳng thức này nếu vẫn phải giữ một group tuần tự.

Vì vậy cần hỏi **nhu cầu giữ thứ tự đặt ở mức nào**, thay vì chỉ tăng số consumer theo tổng message rate.

### 7.1. Một group thật sự nóng khác collision do bucket

| Hiện tượng | Bản chất | Biện pháp |
|---|---|---|
| **Hot group thật** | Một `JMSXGroupID` chiếm phần lớn message | Giảm thời gian xử lý, rate limit, chia key nếu invariant cho phép |
| **Bucket collision** | Nhiều group độc lập hash vào cùng bucket và bị gắn chung consumer | Tuning group map/buckets và kiểm tra phân bố thực tế |
| **Worker chậm** | DB/API/GC/lock kéo dài trên owner hiện hành | Profile/timeout/downstream capacity |
| **Prefetch quá rộng** | Client giữ nhiều delivery và làm phân phối thiếu công bằng | Cân chỉnh prefetch/consumer window, đo latency |
| **Producer sai thứ tự** | Nhiều producer cùng aggregate không có nguồn sequence đáng tin | Aggregate version, serialize send hoặc kiểm tra state ở DB |

Không thể kết luận collision chỉ từ “hai group nằm trên cùng worker”: broker hoàn toàn có thể chọn cùng worker **ngay cả khi không collision**. Cần đo nhiều group/buckets và so sánh policy.

### 7.2. Tại sao đóng nhóm liên tục không giải quyết throughput?

Chia một chuỗi 100 message cần thứ tự nghiêm ngặt thành 10 epoch, gửi marker -1 sau mỗi epoch. Nếu epoch mới **chỉ bắt đầu sau epoch trước xử lý xong**, 100 message vẫn nối tiếp nhau theo thời gian. Việc đổi worker giữa epoch không biến chúng thành 100 công việc song song.

Nếu cho các epoch **chồng lấn** để nhanh hơn, bạn đã **nới invariant thứ tự nghiệp vụ**. Điều này có thể đúng nếu tác vụ độc lập/commutative, nhưng cần version guard và kiểm chứng riêng, không phải tính năng miễn phí của marker -1.

## 8. Chiến lược xử lý group quá tải

### 8.1. Chọn key hẹp nhất còn bảo vệ đúng nghiệp vụ

Nếu yêu cầu là **các update của cùng order theo thứ tự**, nhưng `JMSXGroupID=tenantId`, một tenant lớn sẽ vô tình serialize **tất cả order** của họ.

Có thể đổi sang `JMSXGroupID=orderId`:

~~~text
Trước:
tenant-1 -> [order A, B, C, D ...] -> Một consumer

Sau:
order-A -> [A1,A2,A3] -> Consumer X
order-B -> [B1,B2]    -> Consumer Y
order-C -> [C1,C2]    -> Consumer Z
~~~

Chỉ làm điều này nếu các order độc lập. Nếu bài toán là **số dư tài khoản** và cần thứ tự trên toàn account, không được tùy tiện đổi `accountId` thành `transactionId` chỉ để tăng throughput.

### 8.2. Chia luồng công việc, nhưng giữ invariant rõ ràng

Một số tác vụ có thể chia key theo loại subtask, ví dụ `orderId:notification` và `orderId:invoice`, **nếu** hai luồng thật sự có thể chạy độc lập. Nếu chúng cùng cập nhật một state, cần cơ chế version/cas/optimistic locking.

Dùng **random suffix** trên cùng aggregate chỉ để chia tải là nguy hiểm: nó phá vỡ affinity và làm các thao tác phụ thuộc nhau được xử lý đồng thời.

### 8.3. Giảm service time

Nếu bắt buộc giữ đúng một group:

- Tối ưu query/index/transaction DB, tránh giữ transaction khi gọi API chậm.
- Đặt timeout và giới hạn concurrency tới downstream, dùng connection pool có capacity hợp lý.
- Tách side effect có thể thực hiện sau ra pipeline khác **nếu handoff bền vững**; không ACK message gốc khi chỉ mới đẩy task vào hàng đợi RAM.
- Tận dụng thao tác gộp/batch nghiệp vụ **khi vẫn bảo đảm đúng thứ tự và tính nguyên tử**.
- Dùng idempotency và aggregate version để xử lý lại khi có redelivery.

Nếu external API giới hạn tốc độ, thêm worker thường chỉ tạo thêm lỗi 429; khi ấy cần rate limiting/backpressure chứ không phải nhiều connection hơn.

### 8.4. Tách lane cho nhóm nóng

Có thể chuyển group nóng sang queue/lane riêng để không kéo chậm các nhóm khác. Nhưng quá trình migration phải có **barrier/drain**: tránh một thời điểm cùng aggregate đang được xử lý trên queue cũ và queue mới. Message grouping chỉ giữ affinity **bên trong queue**, không tự tạo thứ tự giữa hai queue.

## 9. Sự cố làm rõ giới hạn của ordering

### 9.1. Consumer chết sau DB commit, trước JMS ACK

~~~text
G: m1 -> m2 -> m3 ...
Consumer A nhận m1, ghi DB thành công.
A chết trước JMS ACK/commit.
Broker phát hiện A mất; m1 có thể được redeliver.
Group được gán lại; consumer B có thể xử lý lại m1.
~~~

Đây là **at-least-once delivery**, không phải bug message grouping. Consumer B phải dedup bằng `eventId`, kiểm tra `aggregateVersion` rồi chỉ tạo tác dụng nghiệp vụ nếu chưa làm. `JMSXGroupSeq` **không đủ** làm khóa dedup: seq có thể lặp lại ở epoch mới hoặc producer không bảo đảm uniqueness.

### 9.2. ACK sớm phá hỏng ranh giới đóng

Giả sử A đã nhận `m3`, nhưng đưa việc xử lý `m3` sang thread pool, rồi ACK ngay. A nhận tiếp marker -1, ACK marker, broker giải phóng group. Consumer B bắt đầu epoch mới trong khi thread pool của A còn đang ghi DB cho `m3`.

Đây là lỗi ứng dụng **ACK trước khi business commit**, chứ không phải group mechanism bảo đảm sai. Giải pháp: chỉ ACK sau xử lý thật sự hoàn tất; khi dùng DB và JMS transaction riêng, vẫn cần idempotency.

### 9.3. Poison message và DLQ không bảo vệ hoàn chỉnh thứ tự nghiệp vụ

Nếu `m5` liên tục rollback và bị đưa DLQ sau max attempts, broker có thể tiếp tục dispatch `m6` theo policy. Nhưng trạng thái nghiệp vụ **đã thiếu bước m5**; chuyển vào DLQ không làm application invariant trở lại đúng.

Cần quy định rõ: message nào có thể skip, message nào phải khóa group, DLQ re-drive cần kiểm tra version ra sao và khi nào cho phép gửi close marker. Không suy rằng broker tự từ chối `JMSXGroupSeq=6` vì `seq=5` đã vào DLQ.

### 9.4. Producer đồng thời và thứ tự DB commit

Một producer session gửi `seq=1,2,3` liên tiếp là điều kiện đơn giản để quan sát. Nhưng hai producer cùng group, một bản tin bị retry hoặc một outbox relay gửi chậm có thể làm **enqueue order** khác thứ tự nghiệp vụ. Group affinity không tự sắp xếp lại theo `JMSXGroupSeq`.

Thiết kế nguồn `aggregateVersion` đáng tin cậy và kiểm tra ở consumer, hoặc serialize publication theo aggregate. Không mặc định dùng “group đã đúng” để bỏ qua version guard.

## 10. Kiểm chứng vận hành: nhìn gì trên broker và trong log?

Một dòng log có giá trị:

~~~text
timestamp, brokerId, queue, workerId,
groupId, eventId, aggregateVersion, groupSeq,
JMSMessageID, JMSRedelivered, JMSXDeliveryCount,
receivedAt, businessCommittedAt, jmsCommittedAt
~~~

Đừng đưa `groupId` nguyên trạng vào metric label nếu có cardinality cao hoặc ID khách hàng nhạy cảm. Có thể dùng bucket/cohort, hash có kiểm soát trong log và sampling.

| Chỉ số | Câu hỏi |
|---|---|
| Queue depth, oldest-message age | Backlog có đang phá SLA? |
| Enqueue/dequeue rate | Tải toàn queue và năng lực xử lý tổng thể? |
| Delivering/in-flight | Message đã dispatch nhưng chưa ACK có nhiều không? |
| Consumer count | Có worker còn đăng ký nhận không? |
| Processing duration phân nhóm | Một group/key cohort có kéo dài bất thường không? |
| Redelivery/DLQ count | Có poison/retry đang làm nghẽn luồng không? |
| Group association/group-map statistics nếu có | Có nhiều group dính một owner hoặc collision không? |
| Rebalance count/first-group marker nếu có | Ownership có thay đổi liên tục sau deploy không? |

### 10.1. Ma trận kiểm thử

| Test | Thao tác | Bằng chứng hợp lý |
|---|---|---|
| Affinity | Hai worker, nhiều message cùng group | Ổn định một owner trong điều kiện không lỗi |
| Đóng group | Gửi `seq=-1`, đợi consumer ACK | Marker được xử lý; group đủ điều kiện association tiếp theo |
| Sau close | Gửi epoch mới cùng group ID | Message mới được nhận; owner **có thể giống hoặc khác** |
| Worker rời | Đóng worker đang giữ group khi có backlog | Broker gán lại; unacked delivery có thể redeliver |
| Thêm consumer | Bổ sung worker khi nhóm cũ đang hoạt động | Xem policy có rebalance hay không, không giả định |
| Hot key | 60 hot / 20 cold, tăng số worker | Hot vẫn tuần tự, cold có cơ hội scale |
| Bucket collision | So sánh grouping với số buckets khác trong broker lab | Đo nhiều group/assignment, tránh kết luận từ một lần |
| Failure/rollback | Mô phỏng consumer lỗi giữa group | Idempotency, DLQ và aggregate version bảo vệ nghiệp vụ |

Không test bằng cách purge một queue production chưa được ủy quyền. Dùng queue riêng, seed có định danh rõ, và đọc trạng thái sau từng pha. Khi kết quả khác nhau giữa Classic/Artemis hay bản broker, kiểm tra **phiên bản, config và in-flight state** thay vì dựa vào log số lượng cố định.

## 11. Những nhận định sai cần loại bỏ

| Nhận định | Phản biện |
|---|---|
| “Tăng worker sẽ chia đều một group nóng.” | Group affinity chủ ý giữ cùng group tại một owner trong giai đoạn ổn định |
| “Đóng group đồng nghĩa xóa message cuối.” | Marker -1 vẫn là message cần xử lý/ACK |
| “Sau close, broker bắt buộc chọn consumer khác.” | Có thể chọn lại consumer cũ |
| “`JMSXGroupSeq` là số broker dùng để tự sắp xếp message.” | Producer khai báo sequence; business order cần được đảm bảo riêng |
| “Bật rebalance đủ để xử lý hot key.” | Rebalance giữa các group, không nhân bản một group thành N lane |
| “First-for-consumer tức là message đầu tiên của epoch.” | Nó mô tả assignment/dispatch, không phải bằng chứng producer sequence |
| “Group ID giống nhau bảo đảm thứ tự trên mọi queue và broker.” | Association có scope theo queue/topology, không phải global lock |
| “ACK JMS nghĩa là DB nghiệp vụ thành công.” | Chỉ đúng nếu ứng dụng đã commit DB đúng thứ tự và xử lý lỗi |
| “Marker -1 có thể gửi bất cứ lúc nào.” | Nếu còn producer khác hoặc business effect cũ in-flight, close sớm có thể phá ordering |

## 12. Bài tập suy luận

**Câu hỏi 1 — Đã gửi close marker và ngay lập tức gửi epoch mới. Có chắc consumer cũ đã xử lý xong?**  
Không. Producer commit chỉ là mốc gửi thành công; nếu nghiệp vụ cần hàng rào, phải chờ bằng chứng marker/chuỗi cũ **đã xử lý và ACK**, hoặc có protocol hoàn tất riêng.

**Câu hỏi 2 — Close marker đã ACK nhưng epoch mới vẫn do W1 nhận, dù W2 rảnh. Broker lỗi?**  
Không. Đóng làm group đủ điều kiện gán lại, không áp đặt consumer phải khác.

**Câu hỏi 3 — Một tenant chiếm 90% queue và group ID đang là `tenantId`. 16 worker thay cho 4 worker có giúp không?**  
Không giải quyết giới hạn tuần tự của tenant đó. Cần xem invariant có cho phép dùng `orderId` hoặc lane độc lập hơn không; nếu không, giảm service time và rate limit.

**Câu hỏi 4 — Worker đã DB commit, crash trước JMS ACK; sau reassignment, message được giao lại. Cách đúng?**  
Dedup theo event ID, kiểm tra aggregate version; lần giao lại không tạo side effect lần hai nhưng được ACK sau khi xác nhận trạng thái nghiệp vụ.

**Câu hỏi 5 — Vì sao tăng số bucket có thể giúp nhiều nhóm nhưng không giúp một hot group?**  
Bucket collision có thể ép **các group độc lập** cùng consumer; giảm collision giúp cân phân bố nhiều group. Một hot group vẫn cần xử lý tuần tự, không phụ thuộc bucket count.

**Câu hỏi 6 — Khi nào nên dùng `JMSXGroupSeq=-1`?**  
Khi tồn tại một **ranh giới kết thúc chuỗi logic** mà producer có thể bảo đảm và consumer có thể xác nhận, không phải cứ sau N message để “tăng tốc” một group vẫn cần ordering.

## 13. Checklist triển khai

- [ ] Group ID được chuẩn hóa và chọn theo invariant, tránh serialize quá rộng.
- [ ] Producer cùng aggregate có nguồn thứ tự/version và phối hợp việc gửi marker kết thúc.
- [ ] Marker close đúng group ID, `JMSXGroupSeq=-1`, và được ACK/commit như một message thực.
- [ ] Epoch mới chỉ bắt đầu sau ranh giới an toàn nếu business effect không được chồng lấn.
- [ ] Phân biệt **close group**, **rebalance**, **consumer leave** và **broker failover**.
- [ ] Không hứa owner sau close sẽ khác owner trước đó.
- [ ] Chính sách group map/buckets được đo với cardinality và skew thực tế.
- [ ] Không ACK sớm; có idempotency + aggregate version guard khi redelivery.
- [ ] DLQ/re-drive có quy định rõ tác động lên thứ tự nghiệp vụ.
- [ ] Không dùng chung cấu hình XML Artemis và Classic.
- [ ] Có metric backlog, processing latency, distribution/group ownership và consumer health.
- [ ] Đã thử ít nhất một hot group, consumer crash và group close/next.

## 14. Kết luận kỹ thuật

**`JMSXGroupSeq=-1` đóng một chuỗi message group để broker có thể giải phóng association; nó không xóa queue, không làm mất yêu cầu ACK và không bảo đảm consumer kế tiếp phải khác.** Rebalance giúp điều chỉnh mapping **giữa nhiều group** khi điều kiện broker thay đổi, nhưng không tạo năng lực xử lý song song trong **một group** vẫn phải bảo toàn thứ tự.

Nếu nhóm quá tải, cần giải đúng **giới hạn tuần tự**: chọn group key nhỏ nhất vẫn giữ invariant, giảm thời gian xử lý, điều tiết nguồn vào hoặc tách tác vụ thành các luồng độc lập khi nghiệp vụ cho phép. Dù dùng ActiveMQ Classic hay Artemis, vẫn phải kết hợp **ACK sau business commit, idempotency, version check, redelivery/DLQ có kiểm soát và giám sát theo group** để đảm bảo thứ tự có ý nghĩa ở tầng nghiệp vụ.
