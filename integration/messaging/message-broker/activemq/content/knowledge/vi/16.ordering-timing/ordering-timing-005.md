# Exclusive consumer hoặc exclusive queue cho luồng cần tuần tự

> **Chương:** Thứ tự và thời gian  
> **Module:** `INTEGRATION_MESSAGING_MESSAGE_BROKER_ACTIVEMQ` — Apache ActiveMQ Classic, Artemis và Java/JMS.  
> **Trọng tâm:** Chọn **một consumer đang được cấp message tại một thời điểm** để hạn chế xử lý đảo thứ tự, cho phép các consumer khác kết nối dự phòng. Phân biệt cơ chế này với bảo đảm thứ tự nghiệp vụ từ đầu đến cuối.

## 1. Bài toán: nhiều replica nhưng một luồng lệnh cần xử lý tuần tự

Một hệ thống kho phát các lệnh cho cùng một sổ tồn:

~~~text
seq=101  ReserveStock(ORD-01, SKU-A, 2)
seq=102  ReleaseStock(ORD-01, SKU-A, 2)
seq=103  ReserveStock(ORD-02, SKU-A, 1)
~~~

Giả sử cả ba lệnh được phát **theo thứ tự đó** vào cùng một queue. Nếu hai consumer cạnh tranh lấy message, worker A có thể nhận `101` còn worker B nhận `102`. Worker B gọi DB nhanh hơn, vì vậy **102 hoàn tất trước 101** mặc dù broker đã phân phối message theo thứ tự dự kiến. Chỉ dùng queue không tự tạo một điểm tuần tự hóa **ở thời điểm commit nghiệp vụ**.

Với nhu cầu **một worker thực thi luồng lệnh**, nhưng vẫn muốn có standby khi worker chính chết, có hai cơ chế gần nhau:

- **ActiveMQ Classic: exclusive consumer.** Một consumer đăng ký với tùy chọn độc quyền; broker ưu tiên phân phối message của queue cho một exclusive consumer đang hoạt động. Consumer khác có thể kết nối để dự phòng.
- **ActiveMQ Artemis: exclusive queue.** Tính chất `exclusive` thuộc **queue do broker cấu hình**; broker chỉ chọn một consumer được phát message từ queue đó tại một thời điểm, dù nhiều consumer đang kết nối.

**Mục tiêu học tập:** phân biệt hai cơ chế theo broker, cấu hình được một queue exclusive, chạy hai Java/JMS worker, đo xem worker nào nhận message, thử failover khi consumer active dừng và giải thích tại sao exclusive vẫn **không đồng nghĩa bảo đảm exactly-once hay strict global order**.

### Một minh họa trực quan

~~~mermaid
flowchart TB
    P[Producer gửi seq 1, 2, 3...] --> Q[(Exclusive queue: ordered.jobs)]
    Q -->|Delivery tới một consumer active| A[Worker A: ACTIVE]
    Q -.->|Đã kết nối, chưa được cấp message| B[Worker B: STANDBY]
    A -.->|Disconnect / close| F[Broker chọn consumer còn lại]
    F --> B
~~~

Hai trạng thái ACTIVE/STANDBY ở sơ đồ là **vai trò phân phối message** trong một queue, không phải một cơ chế leader election tổng quát của ứng dụng. Worker standby có thể vẫn hoạt động HTTP, nhận lệnh quản trị hoặc chạy công việc không thuộc queue này. Exclusive queue cũng **không khóa bảng DB** hay bảo vệ một hệ thống ngoài broker khỏi ghi song song.

## 2. Tính độc quyền thực sự bảo đảm điều gì?

### 2.1. Bốn loại “thứ tự” phải tách riêng

| Loại thứ tự | Ví dụ | Exclusive queue/consumer tác động thế nào? |
|---|---|---|
| **Send order** | Producer P gửi message 1 trước message 2 | Không kiểm soát thứ tự producer phát; nhiều producer có thể xen kẽ |
| **Enqueue/routing order** | Broker đưa 1 rồi 2 vào cùng queue | Không đổi thứ tự đã vào queue; priority/scheduled delivery vẫn ảnh hưởng điều kiện phát |
| **Delivery order** | Broker đưa 1 rồi 2 đến consumer | Hạn chế **phân phối đồng thời sang nhiều consumer** của cùng queue |
| **Business commit order** | Transaction DB cho 1 commit trước transaction của 2 | Chỉ có thể suy ra nếu consumer **xử lý tuần tự và ACK/commit sau khi hoàn tất**; không tự bảo đảm trước crash/redelivery |

Trong tình huống đơn giản — **một producer, cùng priority, không scheduling, một queue, một consumer active, một message xử lý xong mới nhận message tiếp** — exclusive hỗ trợ một đường xử lý tuần tự dễ dự đoán.

Nhưng không có một câu bảo đảm tuyệt đối rằng tất cả message luôn được hoàn tất đúng thứ tự trong mọi tình huống: khi connection mất, một message đang in-flight có thể quay lại sau khi những message khác đã được phát; retry/redelivery delay, failover, message expiration và điều kiện xử lý nghiệp vụ có thể tạo thứ tự hoàn tất khác.

### 2.2. Một consumer được phân phối không có nghĩa chỉ một message in-flight

Broker có thể **buffer/prefetch** nhiều message ở client active. Do vậy exclusive có thể đồng thời tồn tại:

~~~text
Broker queue
  ├─ seq=11 (đang xử lý trong callback)
  ├─ seq=12 (đã dispatch/prefetch đến active client)
  └─ seq=13 (đang chờ hoặc đã dispatch)
~~~

Nếu code worker tự đẩy message vào thread pool rồi trả về ngay, seq 12 có thể hoàn tất trước seq 11 **trong cùng một exclusive consumer**. Muốn tuyến tính hóa ở cấp business:

1. Giữ **một luồng xử lý nghiệp vụ tuần tự** cho queue.
2. Chỉ `ACK/commit` message sau khi side effect của message đó hoàn tất.
3. Tránh dispatch message qua executor song song không có cơ chế sắp thứ tự.
4. Xác minh các trường hợp redelivery/failover bằng **sequence number ở nghiệp vụ**, không chỉ nhìn số consumer active.

**Đừng dùng tính độc quyền để thay thế transaction và idempotency.** Broker có thể giao lại một message chưa ACK, ngay cả khi DB đã commit.

## 3. ActiveMQ Classic: exclusive consumer ở phía client

### 3.1. Cách khai báo

Trong **ActiveMQ Classic**, tính độc quyền thường được kích hoạt trên destination của **consumer** bằng tùy chọn `consumer.exclusive=true`. Ví dụ với client Classic dùng API `javax.jms`:

~~~java
import javax.jms.Connection;
import javax.jms.MessageConsumer;
import javax.jms.Queue;
import javax.jms.Session;
import org.apache.activemq.ActiveMQConnectionFactory;

// Đoạn minh họa trong một phương thức throws JMSException.
ActiveMQConnectionFactory factory =
    new ActiveMQConnectionFactory("tcp://127.0.0.1:61616");

Connection connection = factory.createConnection("labuser", "lab-password");
Session session = connection.createSession(
    true, Session.SESSION_TRANSACTED);

// Đích broker là "ordered.jobs"; query option dành cho ActiveMQ Classic consumer.
Queue destination =
    session.createQueue("ordered.jobs?consumer.exclusive=true");

MessageConsumer consumer = session.createConsumer(destination);
connection.start();

// receive/commit/rollback theo logic nghiệp vụ.
// Sau cùng đóng consumer, session, connection theo thứ tự phù hợp.
~~~

`consumer.exclusive=true` là **destination option riêng của ActiveMQ Classic**, không phải tham số chung của JMS 1.1/Jakarta Messaging. Đừng copy chuỗi `?consumer.exclusive=true` này sang một JMS destination Artemis rồi giả định Artemis sẽ tự cấu hình queue exclusive.

**Điểm cần nhớ:**

- Exclusive nằm ở **đăng ký consumer**. Khi có một exclusive consumer phù hợp, broker phân phối message cho nó; các consumer cùng queue khác có thể chờ.
- Nếu active consumer ngắt kết nối, broker có thể chọn consumer còn kết nối để tiếp tục xử lý.
- Không phải tất cả consumer tự động nhận được ưu tiên như nhau; consumer priority/prefetch và tùy chọn client có thể ảnh hưởng lựa chọn thực tế.
- Chỉ nhìn từ code publisher không biết hàng đợi đang có exclusive consumer hay không, bởi publisher vẫn gửi vào queue logic `ordered.jobs` như bình thường.

Với ActiveMQ Classic nhánh dùng `jakarta.jms`, import và artifact client có thể khác. Đừng trộn `javax.jms.*` của Classic 5.x với `jakarta.jms.*` của Artemis ví dụ ở phần 5.

### 3.2. Điều kiện kiểm chứng

Chạy consumer C1 với `consumer.exclusive=true` và consumer C2 có cấu hình tương đương, cả hai cùng nhận `ordered.jobs`. Phát N message khi hai connection vẫn đang mở. Trong thời gian **một exclusive consumer active không bị đóng**, bạn kỳ vọng **chỉ một consumer được phát message**; khi nó rời đi, worker còn lại có thể nhận các message sau đó hoặc message chưa được xác nhận.

Thứ tự lựa chọn consumer active cụ thể không nên được hardcode theo “process chạy đầu luôn thắng” trong mọi phiên bản, trừ khi bạn đã kiểm chứng chính sách lựa chọn thực tế.

## 4. ActiveMQ Artemis: exclusive queue nằm ở broker

### 4.1. Cấu hình queue exclusive đúng chỗ

Với Artemis instance đã được tạo, mở:

~~~text
<ARTEMIS_INSTANCE>/etc/broker.xml
~~~

Bên trong section `<addresses>` **đang tồn tại**, khai báo một anycast address và queue riêng:

~~~xml
<address name="ordered.jobs">
    <anycast>
        <queue name="ordered.jobs" exclusive="true">
            <durable>true</durable>
        </queue>
    </anycast>
</address>
~~~

**Đây là một mảnh cấu hình, không phải toàn bộ `broker.xml`.** Không tạo thêm section `<addresses>` trùng hoặc queue trùng tên; giữ nguyên acceptor, namespace và các policy do instance sinh ra. Trong lab, khởi động lại broker sau chỉnh sửa và xác minh thuộc tính **exclusive=true** của queue trong console/JMX/management trước khi kết luận bài thử hoạt động.

- `<anycast>` là routing type phù hợp cho queue xử lý một đơn vị công việc mỗi lần giao.
- `exclusive="true"` là thuộc tính của **queue**, không nằm trong URL producer/consumer.
- `<durable>true</durable>` giữ queue khi broker restart theo cấu hình. Message muốn có độ bền qua restart vẫn cần persistence và producer gửi persistent delivery.
- Nếu muốn các consumer cạnh tranh nhưng không giới hạn một active, đổi thuộc tính queue; không đơn thuần đổi `MessageConsumer` ở phía Java.

Một số phiên bản Artemis cũng có chính sách **default exclusive queue** trong `address-settings` để quyết định giá trị mặc định cho queue tạo sau đó. Ví dụ dưới chỉ là **tùy chọn**, dùng khi đã đối chiếu schema và phiên bản đang chạy:

~~~xml
<address-setting match="ordered.#">
    <default-exclusive-queue>true</default-exclusive-queue>
</address-setting>
~~~

Trong bài lab, khai báo `exclusive="true"` **trực tiếp ở queue** để tránh phụ thuộc default của một queue auto-created. Mặc định chỉ áp dụng khi tạo queue, không phải lệnh sửa ngược mọi queue đã tồn tại.

### 4.2. Exclusive khác `max-consumers="1"`

Artemis có thuộc tính giới hạn số consumer kết nối queue, ví dụ:

~~~xml
<!-- Chỉ là ví dụ đối chiếu, KHÔNG thêm lên queue lab đang exclusive. -->
<queue name="single-consumer-only" max-consumers="1"/>
~~~

Đừng nhầm hai mục tiêu:

| Cấu hình | Có thể có nhiều consumer kết nối cùng queue? | Lợi ích | Điểm hạn chế |
|---|---|---|---|
| `exclusive="true"` | **Có**, nhưng chỉ một consumer được chọn để phát message tại một thời điểm | Standby đã kết nối, broker chuyển phát khi active rời đi | Throughput bị giới hạn bởi một consumer; vẫn cần xử lý duplicate/failover |
| `max-consumers="1"` | **Không**, consumer thứ hai có thể bị từ chối vì vượt giới hạn | Chặn nhiều consumer cùng subscribe | Không có standby cùng queue đã đăng ký sẵn; phải reconnect khi slot trống |
| Queue mặc định, hai consumer | Có | Chia tải song song | Hoàn tất nghiệp vụ có thể đảo thứ tự giữa hai consumer |

**Exclusive là tính chất phân phối**, còn `max-consumers` là **hạn mức kết nối/đăng ký consumer**. Dùng cả hai cùng lúc có thể làm mất lợi ích standby của exclusive queue.

### 4.3. Tại sao không thay bằng `JMSXGroupID` ngay?

Nếu một queue chứa message cho **nhiều tài khoản độc lập**, ta có thể chỉ cần tuần tự *trong từng tài khoản*, không cần khóa toàn bộ queue vào một worker. Khi đó message grouping, ví dụ đặt `JMSXGroupID=accountId`, có thể cho phép các nhóm khác nhau được xử lý song song mà vẫn giữ affinity của từng group đến consumer theo cơ chế provider.

So sánh:

| Cơ chế | Độ rộng của vùng tuần tự | Khi nào nên chọn? |
|---|---|---|
| Exclusive queue | **Toàn bộ một queue** | Luồng lệnh thực sự có một tổng thứ tự cần bảo vệ |
| Message grouping | **Theo group key** trong queue | Nhiều đối tượng độc lập: `accountId`, `orderId`, `aggregateId` |
| Partition/shard thành nhiều queue | Mỗi partition độc lập | Tải lớn và có thể chia miền thứ tự bằng khóa định tuyến |

Message grouping cũng có giới hạn theo client/broker/version, failover và rebalancing. Không cần lồng cả grouping vào cấu hình queue exclusive để làm bài này; nếu việc xử lý mọi message bằng một worker là nút thắt, hãy đánh giá lại yêu cầu thực tế trước khi chọn.

## 5. Java/JMS lab: hai worker kết nối, chỉ một worker nhận

### 5.1. Chuẩn bị

Cần:

- Một Artemis instance local với acceptor Core/JMS ở `tcp://127.0.0.1:61616`.
- Queue `ordered.jobs` đã được khai báo **exclusive=true** như mục 4, đang rỗng khi bắt đầu.
- Tài khoản user/password có quyền `send` và `consume` trên address đó.
- Java 17, một dự án dùng Jakarta Messaging với Artemis Jakarta client tương thích broker.

Ví dụ dependency Maven:

~~~xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
    <artemis.version>2.33.0</artemis.version>
</properties>
<dependencies>
    <dependency>
        <groupId>org.apache.activemq</groupId>
        <artifactId>artemis-jakarta-client</artifactId>
        <version>${artemis.version}</version>
    </dependency>
</dependencies>
~~~

Chọn phiên bản Artemis client tương thích với broker/JDK thực tế. Không cần hardcode credentials; cấp hai biến môi trường `ARTEMIS_USER` và `ARTEMIS_PASSWORD` khi chạy. Giá trị `2.33.0` chỉ phục vụ ví dụ cấu hình cụ thể, không phải khẳng định mọi hệ thống phải dùng bản này.

### 5.2. Mã nguồn hoàn chỉnh

Lớp sau có ba chế độ:

- `send <count>`: một producer gửi tuần tự `seq=1..count`; commit riêng từng message để dễ đối chiếu.
- `work <workerName>`: consumer xử lý một message, in sequence và delivery count, **commit**, rồi nhận message tiếp theo.
- `hold <workerName>`: consumer nhận message đầu tiên nhưng **chưa commit**, chờ để operator chủ động dừng cưỡng bức và quan sát redelivery sang standby.

~~~java
import jakarta.jms.DeliveryMode;
import jakarta.jms.JMSConsumer;
import jakarta.jms.JMSContext;
import jakarta.jms.Message;
import jakarta.jms.Queue;
import jakarta.jms.TextMessage;
import org.apache.activemq.artemis.jms.client.ActiveMQConnectionFactory;

import java.util.UUID;

public final class ExclusiveOrderingLab {
    private static final String URL = "tcp://127.0.0.1:61616";
    private static final String QUEUE = "ordered.jobs";

    public static void main(String[] args) throws Exception {
        if (!validArgs(args)) {
            System.out.println("Dùng: ExclusiveOrderingLab send <1..100>");
            System.out.println("      ExclusiveOrderingLab work <workerName>");
            System.out.println("      ExclusiveOrderingLab hold <workerName>");
            return;
        }

        String user = requiredEnv("ARTEMIS_USER");
        String password = requiredEnv("ARTEMIS_PASSWORD");
        ActiveMQConnectionFactory factory =
            new ActiveMQConnectionFactory(URL);

        // Mỗi process/worker có JMSContext (connection + session) riêng.
        try (JMSContext ctx = factory.createContext(
                user, password, JMSContext.SESSION_TRANSACTED)) {

            Queue queue = ctx.createQueue(QUEUE);

            if ("send".equals(args[0])) {
                sendSequence(ctx, queue, Integer.parseInt(args[1]));
            } else {
                consume(ctx, queue, args[1], "hold".equals(args[0]));
            }
        }
    }

    private static void sendSequence(
            JMSContext ctx, Queue queue, int count) throws Exception {
        String runId = UUID.randomUUID().toString();

        var producer = ctx.createProducer()
            .setDeliveryMode(DeliveryMode.PERSISTENT);

        for (int seq = 1; seq <= count; seq++) {
            String eventId = runId + ":" + seq;
            TextMessage message = ctx.createTextMessage(
                "{\"eventId\":\"" + eventId
                + "\",\"seq\":" + seq + "}");

            message.setStringProperty("eventId", eventId);
            message.setStringProperty("runId", runId);
            message.setIntProperty("seq", seq);

            try {
                producer.send(queue, message);
                ctx.commit();
                System.out.printf(
                    "SEND run=%s seq=%d JMSMessageID=%s%n",
                    runId, seq, message.getJMSMessageID());
            } catch (Exception failure) {
                ctx.rollback();
                throw failure;
            }
        }
    }

    private static void consume(
            JMSContext ctx, Queue queue, String name, boolean hold)
            throws Exception {

        JMSConsumer consumer = ctx.createConsumer(queue);
        int idlePolls = 0;

        try {
            while (idlePolls < 30) {
                Message message = consumer.receive(1000);
                if (message == null) {
                    idlePolls++;
                    continue;
                }

                idlePolls = 0;

                try {
                    if (!(message instanceof TextMessage text)) {
                        throw new IllegalArgumentException(
                            "Lab chỉ hỗ trợ TextMessage");
                    }

                    String eventId =
                        text.getStringProperty("eventId");
                    int seq = text.getIntProperty("seq");
                    int deliveryCount =
                        message.propertyExists("JMSXDeliveryCount")
                            ? message.getIntProperty("JMSXDeliveryCount")
                            : -1;

                    System.out.printf(
                        "[%s] RECEIVE seq=%d id=%s "
                        + "redelivered=%s deliveryCount=%d%n",
                        name, seq, eventId,
                        message.getJMSRedelivered(),
                        deliveryCount
                    );

                    if (hold) {
                        System.out.println(
                            "[" + name + "] HOLD uncommitted, "
                            + "đang chờ để kiểm thử failover");
                        Thread.sleep(120_000);
                        // Nếu không bị dừng cưỡng bức, trả lại message.
                        ctx.rollback();
                        return;
                    }

                    // Chỉ giả lập side effect tuần tự.
                    // Production cần transaction DB, version check,
                    // idempotency key theo eventId.
                    Thread.sleep(250);
                    ctx.commit();

                    System.out.printf(
                        "[%s] COMMITTED seq=%d id=%s%n",
                        name, seq, eventId);
                } catch (Exception failure) {
                    try {
                        ctx.rollback();
                    } catch (Exception rollbackError) {
                        failure.addSuppressed(rollbackError);
                    }
                    throw failure;
                }
            }
        } finally {
            consumer.close();
        }
        System.out.println("[" + name + "] Hết khoảng quan sát.");
    }

    private static boolean validArgs(String[] args) {
        if (args.length != 2) return false;

        if ("send".equals(args[0])) {
            try {
                int count = Integer.parseInt(args[1]);
                return count >= 1 && count <= 100;
            } catch (NumberFormatException failure) {
                return false;
            }
        }
        return ("work".equals(args[0]) || "hold".equals(args[0]))
            && !args[1].isBlank();
    }

    private static String requiredEnv(String key) {
        String value = System.getenv(key);
        if (value == null || value.isBlank()) {
            throw new IllegalStateException("Thiếu biến " + key);
        }
        return value;
    }
}
~~~

**Những chi tiết khiến lab kiểm chứng đúng ý:**

1. Mỗi worker là **một process hoặc một context độc lập**. Không chia sẻ cùng `JMSContext` giữa hai thread.
2. Producer gửi từ **một session**, tuần tự tăng `seq` và gọi `commit()` sau mỗi send. Vì vậy dữ liệu vào queue có điểm tham chiếu rõ ràng. Không chạy producer khác xen vào trong lượt này.
3. Cả hai worker tạo consumer trên **cùng queue `ordered.jobs`**; ứng dụng **không** gắn tùy chọn exclusive ở JMS destination. Tính độc quyền đến từ broker config.
4. Mã `work` xử lý và commit **trên cùng thread**, không dispatch job sang thread pool. Tại mỗi thời điểm code chỉ có một message đang chạy nghiệp vụ.
5. Mã `hold` cố tình để message uncommitted. Dùng để quan sát standby được chọn sau khi active chết, **không dùng trong production**.
6. Dòng `JMSXDeliveryCount=-1` nghĩa là provider không cung cấp thuộc tính đó ở ví dụ hoặc không đọc được; không lấy nó làm định danh nghiệp vụ.

### 5.3. Nếu muốn giảm prefetch trong bài thử

Artemis Core client có cấu hình `consumerWindowSize` (consumer credit/window). Trong bài thử thứ tự và redelivery, bạn có thể đánh giá cấu hình window nhỏ hoặc bằng 0 **theo đúng client/version đang dùng** để giảm số message được buffer trước trong client.

**Không suy rằng đặt window=0 là đủ để bảo đảm commit order tuyệt đối.** Khi có rollback, delayed redelivery, failover hoặc application side effect bên ngoài, cần kiểm soát thứ tự ở tầng nghiệp vụ. Thay đổi window còn có thể làm giảm throughput; so sánh thực nghiệm trước khi áp dụng.

## 6. Thực hành A: cùng kết nối, một active và một standby

### Cách tiến hành

1. Xác nhận queue `ordered.jobs` **rỗng** và attribute `exclusive=true` trong broker.
2. Chạy `ExclusiveOrderingLab work A` ở terminal A.
3. Chạy `ExclusiveOrderingLab work B` ở terminal B **trước khi hết thời gian chờ 30 giây**.
4. Tại terminal C, chạy `ExclusiveOrderingLab send 12`.
5. Quan sát log A/B và count queue trong console.

Kết quả mong đợi khi cả hai consumer vẫn kết nối liên tục:

- **Một** worker nhận và commit các message trong đợt phát, ví dụ worker A nhận seq 1 đến 12. Worker còn lại kết nối nhưng không nhận message trong khoảng quan sát đó.
- Nếu broker chọn B thay A thì kết quả **vẫn hợp lệ**. Không coi “A phải là leader vì chạy đầu” là điều kiện cứng.
- Log của worker được chọn có thể có thứ tự `RECEIVE 1, COMMITTED 1, RECEIVE 2, COMMITTED 2...` vì code xử lý/commit tuần tự. Đây là kết quả của **dữ liệu thử + một worker đang xử lý tuần tự + không có lỗi**, không phải bảo đảm vô điều kiện của mọi ứng dụng dùng exclusive.
- Queue giảm về 0 sau khi 12 message được commit; `JMSRedelivered` thường là false cho những lần giao đầu.

| Điều quan sát | Queue bình thường với hai worker | Exclusive queue với hai worker |
|---|---|---|
| Ai nhận các message trong một đợt? | Có thể cả A và B, cạnh tranh chia việc | Một consumer được chọn tại một thời điểm |
| Thứ tự hoàn tất giữa A/B | Có thể đảo | Không có cạnh tranh hoàn tất giữa hai consumer cùng queue khi active ổn định |
| Khi active rời đi | Consumer còn lại có thể nhận message mới | Standby được broker chọn để nhận tiếp |
| Tổng throughput | Có thể tận dụng cả hai | Bị giới hạn bởi consumer được chọn |

Khi chạy lab không dùng một consumer thứ ba, queue browser có side effect hay một service thực tế cũng đang consume `ordered.jobs`. Nếu có, kết quả không còn phản ánh phép thử hai worker.

## 7. Thực hành B: failover khi active đang giữ message chưa commit

Thí nghiệm này minh họa ranh giới quan trọng nhất của tính độc quyền: **failover có thể dẫn đến redelivery**.

### Chuẩn bị và thao tác

1. Dọn queue lab (chỉ khi không chứa dữ liệu cần giữ), khởi động broker và xác nhận `exclusive=true`.
2. Chạy `ExclusiveOrderingLab hold A`. Worker A nhận message đầu tiên nhưng chưa commit.
3. Chạy `ExclusiveOrderingLab work B`. Worker B kết nối dự phòng.
4. Chạy `ExclusiveOrderingLab send 1`; đợi log `[A] HOLD uncommitted` để xác nhận A đã nhận message.
5. **Trong môi trường lab riêng**, dừng cưỡng bức process A trước khi hết 120 giây chờ. Ví dụ Linux/macOS có thể dùng `kill -9 <PID>` **chỉ đối với PID của A**; trên Windows có thể dùng công cụ dừng cưỡng bức process tương ứng. Không sử dụng thao tác này trên broker hay tiến trình production.
6. Quan sát B: sau khi broker phát hiện A disconnect, B có thể nhận lại message chưa commit. Ghi `eventId`, `JMSRedelivered`, `JMSXDeliveryCount` và log commit của B.
7. Xác nhận queue về 0 sau khi B commit; nếu không, kiểm tra connection timeout, redelivery delay, broker policy, trạng thái in-flight và còn consumer khác hay không.

Log minh họa **có thể** trông như sau:

~~~text
[A] RECEIVE seq=1 id=<run-id>:1 redelivered=false deliveryCount=1
[A] HOLD uncommitted, đang chờ để kiểm thử failover

# Process A bị dừng cưỡng bức; broker phát hiện disconnect.

[B] RECEIVE seq=1 id=<run-id>:1 redelivered=true deliveryCount=2
[B] COMMITTED seq=1 id=<run-id>:1
~~~

**Không cố định deliveryCount=2 hoặc thời gian takeover** làm tiêu chí bắt buộc ở mọi provider/version; hãy đối chiếu bộ đếm thực tế. Điều kiện chính cần xác minh là **message chưa commit không bị xem là đã hoàn tất** và consumer dự phòng có thể tiếp tục sau khi active mất kết nối.

### Tại sao phép thử không chứng minh strict FIFO trong mọi trường hợp?

Khi queue có seq 1, 2, 3... và seq 1 đang in-flight, nếu có retry/redelivery delay, failover hoặc những message được buffer sẵn, có thể phát sinh thứ tự quan sát khác với thứ tự phát. **Exclusive giới hạn nơi delivery diễn ra; nó không tự tạo một giao dịch nguyên tử bao gồm DB của consumer A và broker JMS.**

Để đánh giá nghiêm túc, lặp lại phép thử với `send 10`, kill active sau khi thấy một seq cụ thể chưa commit, ghi lại **receive order và commit order** ở standby. Đây là bài thử failure mode, không phải cam kết broker chắc chắn reorder. Dùng eventId/sequence để tìm điểm mất, trùng hoặc đảo, thay vì dựa vào tên worker.

### Một rủi ro khác: active chưa chết hẳn

Nếu một JVM bị treo lâu, mất kết nối đến broker và broker chọn standby, ứng dụng cũ có thể **vẫn đang thực thi side effect bên ngoài JMS** trong khi standby nhận lại message. Vì vậy exclusive queue **không phải distributed lock/fencing token** cho DB, API kho hay hệ thống thanh toán. Nếu side effect phải độc quyền tuyệt đối, cần thêm khóa/lease có fencing hoặc điều kiện cập nhật trạng thái trong hệ thống đích.

## 8. Bảo vệ thứ tự nghiệp vụ với sequence và idempotency

Khi yêu cầu là **“seq n+1 chỉ được áp dụng sau seq n”**, không đủ chỉ bật exclusive. Hãy để message mang:

~~~json
{
  "eventId": "order-42:103",
  "aggregateId": "order-42",
  "sequence": 103,
  "operation": "ReserveStock"
}
~~~

DB nên lưu `last_applied_sequence` **theo aggregate** và xử lý trong transaction:

~~~sql
BEGIN;

-- Phải khóa record trạng thái của aggregate trong transaction,
-- hoặc dùng cơ chế version/CAS tương đương.
SELECT last_applied_sequence
FROM aggregate_state
WHERE aggregate_id = 'order-42'
FOR UPDATE;

-- Pseudocode trong ứng dụng:
-- Nếu sequence == last_applied_sequence + 1: áp dụng side effect.
-- Nếu sequence <= last_applied_sequence: duplicate/stale, không làm lại.
-- Nếu sequence > last_applied_sequence + 1: thiếu event trước;
--     hoãn xử lý/rollback/quarantine có kiểm soát, KHÔNG nhảy cóc.

UPDATE aggregate_state
SET last_applied_sequence = 103
WHERE aggregate_id = 'order-42';

INSERT INTO processed_messages(consumer_name, event_id)
VALUES ('stock-worker', 'order-42:103');

COMMIT;
~~~

Đây là **phác thảo transaction**: nhánh kiểm tra sequence cần được thực hiện trong code nghiệp vụ **trước** hai câu lệnh ghi và phải dùng điều kiện/khóa phù hợp. Bảng `processed_messages` cần unique constraint trên `(consumer_name, event_id)`. Trong môi trường thực tế, `aggregate_state` cần khởi tạo sequence trước đó nhất quán với producer, và side effect nghiệp vụ cũng phải nằm trong cùng DB transaction nếu muốn bảo vệ theo sequence.

Sau DB commit thành công, consumer mới `JMSContext.commit()`. Nếu JMS commit thất bại, redelivery sẽ gặp cùng eventId hoặc sequence cũ, nhận diện duplicate, **không làm lại side effect**, rồi ACK/commit JMS. Nếu phát hiện gap seq 105 khi chưa có 104, việc rollback ngay vô hạn có thể tạo poison loop; cần timeout, retry budget, lưu riêng event out-of-order và alert khi gap không thể tự khôi phục.

Đối với side effect qua HTTP/API không hỗ trợ transaction DB, dùng idempotency key/fencing ở downstream hoặc outbox riêng. Exclusive queue tự nó không biến nhiều hệ thống thành một giao dịch thống nhất.

## 9. Khi nào không nên bật exclusive?

Exclusive phù hợp khi **toàn bộ một queue** thực sự phụ thuộc vào một thứ tự xử lý và throughput một worker có thể đáp ứng tải.

Ngược lại, không nên bật chỉ vì “muốn an toàn” nếu:

- Hệ thống có nhiều tài khoản/đơn hàng **độc lập**, có thể xử lý song song theo key.
- Thời gian xử lý mỗi message rất dài, một message độc có thể chặn mọi việc của queue.
- Tốc độ producer vượt tốc độ một worker, làm backlog tăng liên tục.
- Đầu ra chỉ cần idempotency, không yêu cầu xử lý theo thứ tự toàn cục.
- Muốn active/active để tận dụng nhiều CPU mà không có điểm thứ tự tổng.

Ví dụ producer phát 500 message/giây, một worker xử lý 300 message/giây. Exclusive queue chỉ có một worker active nên backlog tăng khoảng **200 message/giây** trong giai đoạn đó. Ba consumer standby cũng không làm throughput lên 900 message/giây. Nếu lưu lượng duy trì 60 giây, backlog phát sinh thêm xấp xỉ **12.000 message**, chưa kể kích thước message và traffic từ hệ thống khác.

Khi gặp nút thắt này, cân nhắc thiết kế **partition theo aggregateId** hoặc message grouping, mỗi phần độc lập giữ thứ tự riêng, thay vì hy sinh toàn bộ throughput cho một queue exclusive. Quyết định cần dựa trên yêu cầu business thật sự: **global FIFO** thường tốn kém hơn **per-key ordering**.

## 10. Chẩn đoán sai cấu hình và các failure mode

| Triệu chứng | Nguyên nhân cần kiểm tra | Hướng kiểm tra |
|---|---|---|
| Hai worker đều liên tục nhận message cùng lúc | Queue Artemis chưa bật exclusive, đang kết nối hai queue khác nhau, hoặc config chưa nạp | Xem queue thực tế trong broker management: address, name, routing, exclusive |
| Worker B không thể đăng ký consumer | Queue đang đặt `max-consumers=1`, hoặc lỗi quyền truy cập | Phân biệt giới hạn consumer với exclusive; kiểm tra role |
| C1 của Classic vẫn chia tải với C2 | `consumer.exclusive=true` không nằm trên destination consumer thực sự hoặc bị client khác/version ảnh hưởng | Xem queue option, client library và broker Classic đang dùng |
| Thứ tự business commit bị đảo dù exclusive | Code xử lý song song trong một callback, redelivery, producer đa luồng, priority/scheduling | Ghi send/enqueue/receive/commit sequence và eventId |
| Standby không tiếp quản ngay | Broker chưa phát hiện disconnect, đang có in-flight/rollback/redelivery delay | Kiểm tra heartbeat/TTL, connection state, retry config |
| Cùng eventId được xử lý hai lần sau failover | DB commit trước JMS ACK, active cũ vẫn làm việc hoặc redelivery | Unique constraint, fencing và idempotency |
| Một message độc chặn toàn queue | Exclusive chỉ có một active worker và retry giữ hàng chờ | DLQ/rollback/backoff, phân loại poison message |
| Queue lớn dần dù thêm nhiều consumer | Standby không tăng năng lực xử lý | Tối ưu active worker hoặc partition theo key |
| Sự kiện số 11 được commit trước 10 | Reorder do failover/prefetch/scheduled/redelivery hoặc producer không serialize send | Enforce sequence/version tại consumer DB |
| Dùng cấu hình Classic trên Artemis không hiệu lực | `consumer.exclusive=true` không phải cú pháp cấu hình exclusive queue Artemis | Cấu hình `exclusive="true"` tại broker queue |

### Quan sát tối thiểu

Để chứng minh exclusive đang làm việc, lưu các chỉ số:

- Tên **queue/address**, routing type, thuộc tính exclusive và số consumer đã kết nối.
- Worker đang nhận message, thời gian active, thời gian chuyển sang standby khi failover.
- Các bộ đếm message ready, delivering, acknowledged, redelivered, DLQ.
- Với mỗi nghiệp vụ: `eventId`, `aggregateId`, `sequence`, `workerId` và thời điểm **DB commit/JMS commit**.
- Tốc độ enqueue/dequeue, queue age và số lượng gap/duplicate khi consumer kiểm tra version.

Không ghi full payload nhạy cảm hoặc password ra log chỉ để kiểm chứng thứ tự.

## 11. Bài tập tự đánh giá

1. Hai worker cùng tiêu thụ một Artemis queue. Thêm `max-consumers=1` có tương đương bật `exclusive=true` không? Giải thích khác biệt khi worker chính chết.
2. Một queue exclusive nhận seq 1, 2, 3 từ một producer. Worker active dispatch từng message sang ba thread xử lý DB. Vì sao vẫn có thể commit 3 trước 1?
3. Cơ chế kích hoạt exclusive của Classic nằm ở producer, consumer hay cấu hình queue Artemis? Viết ví dụ cụ thể cho cả hai broker.
4. Trong phép thử `hold A`, khi A bị kill trước commit, B có thể nhận lại message nào? Có được phép suy rằng side effect DB của A chắc chắn chưa chạy không?
5. Nếu cần tuần tự hóa theo `accountId` nhưng các account độc lập, bạn chọn exclusive toàn queue, message grouping hay partition? Tại sao?
6. Vì sao `JMSRedelivered=true` hoặc `JMSXDeliveryCount>1` chưa đủ để tránh tính tiền hai lần khi consumer failover?
7. Một queue exclusive có backlog tăng 200 message/giây. Tại sao thêm 5 standby consumer không giải quyết throughput?
8. Trong DB đã có `last_applied_sequence=103`. Consumer nhận seq 102, 104 và 106 thì nên xử lý từng trường hợp như thế nào?
9. Nếu producer P1 và P2 gửi cùng queue đồng thời, exclusive có bảo đảm thứ tự nghiệp vụ theo thời gian phát sinh trên hai máy không? Cần thiết kế gì bổ sung?
10. Tại sao exclusive queue không được dùng như một distributed lock cho API kho không hỗ trợ fencing?

**Định hướng trả lời:** (1) không, max-consumers từ chối standby đã kết nối; (2) độc quyền delivery không đóng băng ba thread; (3) Classic ở consumer destination option, Artemis ở queue; (4) message chưa ACK đủ điều kiện redelivery, DB có thể đã được cập nhật; (5) grouping/partition theo key; (6) cần idempotency ở hệ thống đích; (7) chỉ một active; (8) 102 duplicate/stale, 104 tiếp theo, 106 gap; (9) không, phải có sequence/logical ordering contract; (10) active cũ có thể vẫn thực thi side effect sau khi mất quyền nhận message.

## 12. Ghi nhớ

**ActiveMQ Classic exclusive consumer** lựa chọn một consumer ưu tiên nhận message bằng cấu hình phía **client**. **ActiveMQ Artemis exclusive queue** đặt thuộc tính độc quyền ở **queue phía broker**, cho phép một consumer active và nhiều standby kết nối; đừng nhầm với `max-consumers=1`.

Cả hai giúp tránh việc các consumer khác nhau đồng thời hoàn tất message từ cùng queue trong điều kiện ổn định, nhưng **không tự bảo đảm strict FIFO dưới mọi lỗi, không giải quyết nhiều producer và không cấp exactly-once nghiệp vụ**. Muốn thực sự cần tuần tự, phải kết hợp *một worker xử lý tuần tự → ACK/commit đúng ranh giới → sequence/version + idempotency ở hệ thống đích → thử failover/redelivery*.

**Tài liệu để đối chiếu phiên bản:** [ActiveMQ Classic — Exclusive Consumer](https://activemq.apache.org/components/classic/documentation/exclusive-consumer) và [ActiveMQ Artemis — Exclusive Queues](https://artemis.apache.org/components/artemis/documentation/latest/exclusive-queues.html). Khi triển khai, kiểm tra đúng broker/client/version và cấu hình management thực tế trước khi dựa vào các thuộc tính riêng của provider.
