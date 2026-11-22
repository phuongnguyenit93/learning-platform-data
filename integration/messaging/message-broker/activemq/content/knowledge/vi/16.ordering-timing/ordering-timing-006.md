# Message priority và nguy cơ thông điệp ưu tiên thấp bị chờ lâu

> **Chương:** Thứ tự và thời gian  
> **Phạm vi:** Mức ưu tiên message của JMS (0–9), cách ActiveMQ Classic và Artemis sử dụng priority khi dispatch, nguy cơ *starvation* của message ưu tiên thấp, vai trò của prefetch/in-flight và các cách bảo đảm tiến độ. Ví dụ Java chính sử dụng Classic 5.x với `javax.jms`; đối chiếu Artemis nêu rõ khác biệt cấu hình.

## 1. Bài toán: HIGH cần nhanh, LOW không được chờ mãi

Queue `payments.jobs` nhận hai loại công việc:

- **HIGH (priority 9):** xác thực giao dịch cần phản hồi trong vài giây.
- **LOW (priority 1):** đối soát định kỳ, không quá khẩn nhưng **phải xong trong 15 phút**.

Một nhóm worker có công suất hữu hạn. Khi ít HIGH, xử lý HIGH trước LOW giúp giảm độ trễ lệnh khẩn. Khi HIGH xuất hiện liên tục nhanh hơn tốc độ xử lý, LOW có thể chờ rất lâu dù broker vẫn hoạt động, không mất message và throughput tổng nhìn rất tốt.

**Message priority là tín hiệu điều phối thứ tự xử lý, không phải cơ chế tự bảo đảm tiến độ tối thiểu cho mọi mức ưu tiên.**

Mục tiêu bài học:

1. Đặt và đọc `JMSPriority` chính xác, phân biệt priority với property tự tạo.
2. Dự đoán lúc nào ưu tiên có thể khiến một message vượt lên trước message khác.
3. Giải thích vì sao prefetch, in-flight, transaction, nhiều consumer và retry làm thứ tự quan sát không tuyệt đối.
4. Phân tích starvation bằng tốc độ đến, công suất xử lý và thời gian chờ.
5. Bật xử lý prioritized messages của ActiveMQ Classic, đối chiếu Artemis.
6. Viết Java/JMS để kiểm chứng và chọn giải pháp bảo đảm SLA cho LOW.

## 2. Hợp đồng JMS: priority 0–9, không phải sắp xếp tuyệt đối

JMS quy định **10 mức priority** từ **0 (thấp nhất)** đến **9 (cao nhất)**; **4** là mức mặc định. Các mức 0–4 thuộc nhóm thông thường, 5–9 là nhóm ưu tiên cao (*expedited*).

Một `MessageProducer` có thể đặt mức mặc định cho các lần gửi sau:

~~~java
producer.setPriority(9);
producer.send(message);
~~~

Hoặc đặt riêng cho một lần gửi:

~~~java
producer.send(
    message,
    DeliveryMode.PERSISTENT,
    9,
    0L); // TTL=0: producer không đặt expiration
~~~

Đối với JMS 1.1, overload là `send(Message, int deliveryMode, int priority, long timeToLive)`.

**Những điều phải phân biệt:**

- `producer.setPriority(9)` và tham số priority trong `send` điều khiển **JMS priority**.
- `message.setIntProperty("priority", 9)` chỉ tạo **application property** tên `priority`; không mặc nhiên đổi cách broker xếp message.
- `JMSPriority` là **header chuẩn** do provider gán theo giá trị của lần gửi. Consumer đọc `message.getJMSPriority()`.
- `DeliveryMode.PERSISTENT` liên quan khả năng lưu bền; không phải độ khẩn.
- TTL quyết định thời hạn hiệu lực; không tạo quota xử lý hay quyền ưu tiên.
- Provider cố gắng ưu tiên delivery của message priority cao hơn, nhưng JMS **không cam kết strict priority hoặc thứ tự tổng thể tuyệt đối** trong mọi topology/trường hợp.

### 2.1. Một message LOW đến trước HIGH

~~~text
T0 Producer gửi L1 priority=1
T1 Producer gửi L2 priority=1
T2 Producer gửi H1 priority=9
T3 Producer gửi H2 priority=9

Nếu không có consumer trước T3:
    cả bốn message có thể nằm trong backlog và được xét priority

Nếu L1 đã dispatch trước T2:
    H1 không có quyền ngắt L1 đang được xử lý
~~~

Một queue hỗ trợ priority có thể giao `H1,H2,L1,L2` khi chúng đều còn đợi trong backlog. Nhưng nếu LOW đã được dispatch/preferred tới client trước khi HIGH đến, `L1` có thể hoàn tất trước `H1`.

**Vì vậy hãy thử priority bằng backlog đã có trước khi mở consumer**, không chỉ chạy producer và consumer đồng thời rồi so log.

### 2.2. Gửi, dispatch và hoàn thành là ba thứ tự khác nhau

| Mốc | Ngữ cảnh | Nguồn gây khác biệt |
|---|---|---|
| Producer gọi `send()` | Thứ tự ở ứng dụng | Nhiều producer, nhiều thread |
| Broker enqueue/dispatch | Chọn message cho consumer | Priority, transaction, scheduler, cursor, prefetch, selector |
| Consumer xử lý xong/commit | Business completion order | Nhiều worker, thời gian xử lý, retry, rollback |

Nếu nghiệp vụ yêu cầu `OrderCreated → OrderPaid` theo cùng `orderId`, chỉ đặt priority cao cho `OrderPaid` có thể làm sự kiện sau đến trước. Priority không phải giải pháp cho ordering theo khóa nghiệp vụ.

## 3. Cơ chế starvation: HIGH tiêu thụ hết khả năng phục vụ

Xét mô hình queue có scheduler gần **strict priority, không ngắt một job đang chạy**. Gọi:

- `μ`: công suất tổng của consumer, message/giây.
- `λH`: tốc độ đến của HIGH, message/giây.
- `λL`: tốc độ đến của LOW, message/giây.

Trong mô hình lý tưởng:

- Nếu `λH < μ`, công suất còn lại cho LOW xấp xỉ `μ − λH`.
- Nếu `λH ≥ μ` liên tục, HIGH có thể chiếm hết năng lực, LOW **không được bảo đảm tiến độ**.
- Nếu `λH + λL > μ`, backlog chung tăng dù có hay không có priority.

Ví dụ:

| Đại lượng | Giá trị minh họa |
|---|---:|
| Công suất worker `μ` | 100 msg/s |
| HIGH đến `λH` | 105 msg/s |
| LOW đến `λL` | 5 msg/s |
| Hậu quả trong strict priority | HIGH đã bão hòa; LOW có thể chờ mãi khi tải giữ nguyên |

**Đây là mô hình phân tích, không phải lời khẳng định mọi bản ActiveMQ Classic/Artemis đều dùng strict priority và chắc chắn bỏ đói LOW.** Broker có cách dispatch, cursor, buffering và đồng bộ riêng; kết luận vận hành phải dựa trên đo thực tế.

### 3.1. LOW có thể chờ rất lâu dù HIGH chưa vượt công suất

Nếu HIGH còn backlog `B_H` và HIGH mới đến với `λH < μ`, thời gian làm cạn backlog HIGH theo mô hình xấp xỉ:

\[
T_{\mathrm{drain,H}} \approx \frac{B_H}{\mu-\lambda_H}.
\]

Giả sử `B_H=600`, `μ=100 msg/s`, `λH=90 msg/s`:

\[
T_{\mathrm{drain,H}} \approx \frac{600}{100-90}=60\ \text{giây}.
\]

LOW có thể phải đợi **khoảng một phút chỉ vì HIGH backlog**, chưa tính LOW khác, network, retry và thời gian xử lý bản thân. Khi `λH` tiến gần `μ`, mẫu số nhỏ và thời gian chờ tăng nhanh.

Công thức là *queueing approximation*, không phải SLA JMS; nó giả định tải, tốc độ ổn định và HIGH luôn được phục vụ trước LOW.

### 3.2. Starvation khác backlog, lag và expiration

- **Backlog:** nhiều message chờ vì tốc độ đến vượt công suất, kể cả queue FIFO.
- **Starvation:** LOW ít được xét vì scheduler liên tục ưu tiên HIGH; chờ lâu bất cân đối dù hệ thống vẫn xử lý message.
- **Lag:** độ trễ xử lý/tuổi message; phải đo theo từng lớp priority.
- **Expiration:** message hết TTL khi còn chờ; nó bị loại/đưa expiry không phải là LOW đã được phục vụ thành công.

**Throughput cao của queue không chứng minh mọi nhóm có latency được chấp nhận.**

## 4. Prefetch và in-flight: HIGH không thể lấy lại LOW đã dispatch

Ở ActiveMQ Classic, queue consumer có thể được **prefetch** nhiều message; Artemis cũng có buffering/flow control và message đang dispatch.

~~~mermaid
flowchart LR
    P["Producer LOW/HIGH"] --> B["Queue backlog: broker xét priority"]
    B -->|Dispatch / prefetch| C["Buffer của consumer"]
    C --> R["receive() / onMessage()"]
    R --> A["Business work + ACK/commit"]
~~~

Ví dụ:

1. Consumer A đã nhận trước 50 LOW vào buffer.
2. Producer mới gửi 100 HIGH.
3. Những LOW đã dispatch không tự bị thu hồi để thay bằng HIGH.
4. Consumer B có thể được cấp HIGH và hoàn tất trước A; thứ tự kết quả càng khó suy từ thứ tự enqueue.

**Prefetch thấp hơn** thường giúp broker xét lại backlog thường xuyên, nhưng có thể tăng round trip và giảm throughput; nó **không tạo quota** cho LOW. Ngược lại, prefetch cao có thể khiến message LOW đã dispatch vẫn được xử lý trước HIGH đến sau (*priority inversion*).

Các biến ảnh hưởng khác:

| Yếu tố | Tác động có thể có |
|---|---|
| Nhiều producer | Thứ tự enqueue giữa các JVM không tuyệt đối |
| JMS transacted send | Message chưa commit chưa sẵn sàng như message đã commit |
| Nhiều consumer | Thứ tự **hoàn thành** phụ thuộc thời gian công việc |
| ACK và redelivery | Rollback/crash có thể khiến message cũ được phát lại |
| Selector | Không phải consumer nào cũng đủ điều kiện nhận |
| Scheduled message và TTL | Có message chưa đến thời điểm deliver hoặc đã hết hạn |
| Paging/cursor/persistence | Cách lấy dữ liệu từ backlog có thể ảnh hưởng thứ tự hiệu dụng |
| Message grouping | Giữ thứ tự theo nhóm có thể hạn chế phân phối và ưu tiên |

## 5. Cấu hình ActiveMQ Classic: `prioritizedMessages`

ActiveMQ Classic có tùy chọn `prioritizedMessages` trong **destination policy**. Để kiểm chứng JMS priority, cấu hình queue thử nghiệm thay vì giả định mỗi queue đều sắp xếp theo priority.

Fragment bên trong `<broker>` của `conf/activemq.xml`:

~~~xml
<destinationPolicy>
  <policyMap>
    <policyEntries>
      <policyEntry queue="priority.lab"
                   prioritizedMessages="true"
                   producerFlowControl="true"
                   memoryLimit="64mb"/>
    </policyEntries>
  </policyMap>
</destinationPolicy>
~~~

Giải thích:

- `queue="priority.lab"` áp dụng riêng cho queue được thử; topic có cùng tên không tự nhận policy này.
- `prioritizedMessages="true"` bật xử lý prioritized message theo khả năng của Classic.
- `producerFlowControl` và `memoryLimit` kiểm soát tài nguyên; **không tạo công bằng giữa HIGH/LOW**.

Đây là **đoạn cấu hình**, không thay thế file XML đầy đủ. Cần kiểm tra broker instance thực sự nạp policy và phiên bản hỗ trợ giá trị này; thay đổi policy có thể cần restart hoặc quy trình reload tương ứng.

Nếu muốn khớp nhiều queue Classic, có thể dùng `queue="priority.>"`. Đây là wildcard **Classic**, không phải `#` của Artemis. Trong lab nên dùng exact match để tránh vô ý thay behavior của queue khác.

### 5.1. Những điều policy không bảo đảm

`prioritizedMessages="true"` **không**:

- Ngắt LOW đang được consumer xử lý để chạy HIGH.
- Thu hồi an toàn mọi message LOW đã prefetch.
- Tự tăng priority theo thời gian message chờ.
- Dành sẵn công suất tối thiểu cho LOW.
- Tăng năng lực CPU/IO của consumer.
- Biến `JMSPriority` thành bộ bảo đảm FIFO hoặc thứ tự hoàn thành toàn cục.

Thử nghiệm phải đo **priority trên consumer**, thứ tự nhận và tuổi message; không chỉ nhìn XML.

## 6. Artemis: cùng JMSPriority, khác mô hình cấu hình

Artemis dùng mô hình **address → routing type → queue**. Nó hỗ trợ độ ưu tiên JMS 0–9 và có logic dispatch queue tương ứng, nhưng không dùng `policyEntry prioritizedMessages` của Classic.

Ví dụ khai báo anycast queue trong phần `<addresses>` của `etc/broker.xml`:

~~~xml
<addresses>
  <address name="priority.lab">
    <anycast>
      <queue name="priority.lab" durable="true"/>
    </anycast>
  </address>
</addresses>
~~~

Đây là fragment, cần ghép vào `<core>` hợp lệ theo version. Producer dùng Artemis Jakarta JMS client tương thích với broker/JDK và truyền priority 1/9 cho JMS queue `priority.lab`.

Phân biệt **ba khái niệm** trong Artemis:

| Khái niệm | Điều nó kiểm soát |
|---|---|
| **Message priority** `JMSPriority` | Độ ưu tiên khi xét một **message** |
| **Consumer priority** (nếu được hỗ trợ/cấu hình) | Độ ưu tiên trong lựa chọn **consumer** nhận message |
| **Anycast/multicast routing** | Message đi vào **queue nào** |

Address settings như paging, expiry, DLQ hoặc flow control giúp vận hành broker, nhưng không tự là một weighted-fair scheduler dành quota theo mức priority.

**Không copy `prioritizedMessages="true"` từ Classic sang Artemis.** Đồng thời không suy rằng hai broker nhất thiết có cùng thứ tự dispatch khi prefetch, paging, HA và protocol khác nhau.

## 7. Java JMS 1.1: gửi LOW/HIGH và quan sát thứ tự nhận

Lab dùng **ActiveMQ Classic 5.x**, Maven artifact `org.apache.activemq:activemq-client` tương thích `javax.jms` và broker lắng nghe `tcp://localhost:61616`.

Điều kiện:

- Queue `priority.lab` có cấu hình ở mục 5.
- Tài khoản lab `app/lab-secret` có quyền send/consume; không hard-code credential thật trên production.
- Queue đã rỗng hoặc môi trường thử cô lập, không trộn message từ run khác.
- Dùng Java 8+ và đúng classpath từ dự án.

### 7.1. Producer: priority là tham số của từng send

File `PriorityPublisher.java`:

~~~java
import javax.jms.Connection;
import javax.jms.DeliveryMode;
import javax.jms.MessageProducer;
import javax.jms.Queue;
import javax.jms.Session;
import javax.jms.TextMessage;
import org.apache.activemq.ActiveMQConnectionFactory;

public final class PriorityPublisher {
    public static void main(String[] args) throws Exception {
        if (args.length < 3 || args.length > 4) {
            throw new IllegalArgumentException(
                "Usage: PriorityPublisher <runId> <priority 0..9> <count> [pauseMs]");
        }
        String runId = args[0];
        int priority = Integer.parseInt(args[1]);
        int count = Integer.parseInt(args[2]);
        long pauseMs = args.length == 4 ? Long.parseLong(args[3]) : 0L;
        if (priority < 0 || priority > 9 || count <= 0 || pauseMs < 0) {
            throw new IllegalArgumentException("Invalid arguments");
        }

        ActiveMQConnectionFactory factory =
                new ActiveMQConnectionFactory("tcp://localhost:61616");
        Connection connection =
                factory.createConnection("app", "lab-secret");
        try {
            Session session = connection.createSession(
                    true, Session.SESSION_TRANSACTED);
            try {
                Queue queue = session.createQueue("priority.lab");
                MessageProducer producer = session.createProducer(queue);
                try {
                    for (int i = 1; i <= count; i++) {
                        String eventId = runId + "-p" + priority + "-" + i;
                        TextMessage message =
                                session.createTextMessage(eventId);
                        message.setStringProperty("eventId", eventId);
                        message.setStringProperty("runId", runId);
                        message.setLongProperty(
                                "appSentAtMs", System.currentTimeMillis());

                        // JMS provider gán header JMSPriority cho lần send.
                        producer.send(
                                message, DeliveryMode.PERSISTENT,
                                priority, 0L);

                        if (i % 20 == 0) {
                            session.commit();
                        }
                        if (pauseMs > 0) {
                            Thread.sleep(pauseMs);
                        }
                    }
                    session.commit();
                    System.out.println("CONFIRMED run=" + runId
                            + " priority=" + priority
                            + " count=" + count);
                } catch (Exception error) {
                    try {
                        session.rollback();
                    } catch (Exception rollbackError) {
                        error.addSuppressed(rollbackError);
                    }
                    throw error;
                } finally {
                    producer.close();
                }
            } finally {
                session.close();
            }
        } finally {
            connection.close();
        }
    }
}
~~~

Ở transacted session, `commit()` mới hoàn thành nhóm send. Nếu `commit()` timeout hoặc mất response, producer không thể chắc message không được broker ghi nhận; đó là bài toán riêng cần event ID và chống duplicate.

Ví dụ tạo backlog **khi chưa có consumer**:

~~~text
java PriorityPublisher R001 1 30
java PriorityPublisher R001 9 30
~~~

Hai lệnh gửi 30 LOW trước rồi 30 HIGH sau. Khi consumer bắt đầu, nếu queue đang ưu tiên message chưa dispatch, có thể thấy HIGH được nhận trước một số LOW dù đến sau.

### 7.2. Consumer: in header priority và tuổi message

File `PriorityConsumer.java`:

~~~java
import javax.jms.Connection;
import javax.jms.Message;
import javax.jms.MessageConsumer;
import javax.jms.Queue;
import javax.jms.Session;
import org.apache.activemq.ActiveMQConnectionFactory;

public final class PriorityConsumer {
    public static void main(String[] args) throws Exception {
        if (args.length != 2) {
            throw new IllegalArgumentException(
                    "Usage: PriorityConsumer <maxMessages> <workMs>");
        }
        int maxMessages = Integer.parseInt(args[0]);
        long workMs = Long.parseLong(args[1]);
        if (maxMessages <= 0 || workMs < 0) {
            throw new IllegalArgumentException("Invalid arguments");
        }

        ActiveMQConnectionFactory factory =
                new ActiveMQConnectionFactory("tcp://localhost:61616");
        // Chỉ dùng để giảm prefetch trong lab với Classic client.
        factory.getPrefetchPolicy().setQueuePrefetch(1);

        Connection connection =
                factory.createConnection("app", "lab-secret");
        try {
            Session session = connection.createSession(
                    true, Session.SESSION_TRANSACTED);
            try {
                Queue queue = session.createQueue("priority.lab");
                MessageConsumer consumer = session.createConsumer(queue);
                try {
                    connection.start();
                    for (int i = 1; i <= maxMessages; i++) {
                        Message message = consumer.receive(8_000L);
                        if (message == null) {
                            System.out.println("No message in timeout");
                            break;
                        }

                        String eventId =
                                message.getStringProperty("eventId");
                        long appSentAt =
                                message.getLongProperty("appSentAtMs");
                        long approximateAge =
                                System.currentTimeMillis() - appSentAt;

                        System.out.printf(
                                "seq=%d event=%s priority=%d "
                              + "ageApproxMs=%d redelivered=%s%n",
                                i, eventId, message.getJMSPriority(),
                                approximateAge,
                                message.getJMSRedelivered());

                        Thread.sleep(workMs); // Mô phỏng worker chậm.
                        session.commit();     // Hoàn tất receive JMS.
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
    }
}
~~~

Chạy sau hai lượt publisher:

~~~text
java PriorityConsumer 60 100
~~~

**Quan sát và giới hạn kết luận:**

1. `getJMSPriority()` phải tương ứng priority 1 hoặc 9 đã gửi.
2. Nếu HIGH xuất hiện trước LOW được enqueue trước, đó là dấu hiệu reordering theo priority.
3. Không thấy HIGH đầu tiên **không chứng minh** broker bỏ qua priority; kiểm tra queue policy đang hiệu lực, cursor, phiên bản, thứ tự commit và prefetch.
4. `ageApproxMs` dựa trên **đồng hồ máy producer**, không phải metric enqueue time của broker; trên hai host có lệch giờ, số đo có thể sai.
5. Consumer commit mỗi message để thử nghiệm dễ hiểu; ở production có DB phải phối hợp business transaction và idempotency.

### 7.3. Thử LOW bị chờ lâu dưới tải HIGH

Trên queue lab mới hoặc đã được dọn:

1. Chạy consumer chậm, ví dụ `100–200 ms/message`.
2. Cho producer HIGH gửi nhiều message, tốc độ **lớn hơn công suất consumer**:
   ~~~text
   java PriorityPublisher LOAD01 9 1000 20
   ~~~
3. Khi HIGH vẫn đang vào queue, gửi một nhóm LOW ở terminal khác:
   ~~~text
   java PriorityPublisher LOAD01 1 10
   ~~~
4. Ghi thời điểm từng LOW được enqueue/nhận, priority, tuổi message, backlog và in-flight.
5. Đợi producer HIGH dừng, tiếp tục drain để quan sát LOW có thể cuối cùng được xử lý.

Thí nghiệm là **tải hữu hạn**, chỉ thực hiện trong môi trường lab. LOW có thể vẫn được dispatch sớm nếu consumer còn chỗ hoặc scheduler không strict; không khẳng định nó chắc chắn phải chờ hết 1.000 HIGH.

Muốn đối chứng, lặp lại trên queue Classic **không bật `prioritizedMessages`**, giữ nguyên số message, prefetch, worker delay và topology.

## 8. Cách xử lý starvation khi LOW có deadline

### 8.1. Giảm prefetch: cải thiện phản ứng, không tạo fairness

Trong Classic:

~~~java
factory.getPrefetchPolicy().setQueuePrefetch(1);
~~~

Prefetch thấp có thể giảm lượng LOW bị cấp trước khi HIGH đến, nhưng cũng tăng round-trip/overhead. **LOW vẫn không được bảo đảm phần công suất nào** nếu HIGH chiếm hết nguồn lực.

### 8.2. Tách queue và dành worker riêng cho LOW

Khi LOW phải hoàn tất đúng SLA, phương án dễ kiểm chứng là:

~~~mermaid
flowchart LR
    P["Producer"] -->|HIGH| H["payments.high"]
    P -->|LOW| L["payments.low"]
    H --> WH["HIGH worker pool"]
    L --> WL["LOW pool: reserved capacity"]
~~~

Ví dụ dành 8 worker cho HIGH, 2 worker tối thiểu cho LOW. LOW không bị HIGH chiếm toàn bộ tài nguyên. Vẫn cần đo `λL < μL`, và giám sát công suất thực tế thay vì chỉ đếm số worker.

Có thể thiết kế worker linh hoạt hỗ trợ queue bên kia khi rảnh, nhưng **phần dung lượng tối thiểu của LOW phải được bảo vệ** nếu muốn tuyên bố SLA.

### 8.3. Weighted fair scheduling ở ứng dụng

Một ý tưởng chia lượt:

~~~text
Trong mỗi chu kỳ:
  Xử lý tối đa 3 message HIGH, nếu có
  Sau đó dành cơ hội xử lý 1 message LOW, nếu có
  Lặp lại
~~~

Tỷ lệ 3:1 có thể bảo vệ tiến độ LOW khi cả hai queue có backlog. Nhưng đây là **logic scheduler tùy biến**, không phải semantics tự có của JMS priority hoặc một dòng cấu hình Classic/Artemis.

Triển khai thật phải quản lý **hai consumer/queue**, session/ACK, timeout, prefetch, tải đồng thời và idempotency. Không lấy pseudo-code này làm chương trình JMS chạy được.

### 8.4. Aging: tăng mức ưu tiên theo tuổi chờ

Chiến lược aging lý thuyết:

~~~text
LOW vừa đến: priority hiệu dụng 1
Chờ > 5 phút: priority hiệu dụng 4
Chờ > 10 phút: priority hiệu dụng 8
~~~

**JMS không cung cấp cam kết portable rằng broker tự nâng `JMSPriority` theo tuổi message.** Nếu muốn aging, phải dùng tính năng scheduler/plugin được phiên bản hỗ trợ hoặc triển khai riêng.

Việc dequeue rồi re-publish để đổi priority có nguy cơ trùng message, thay JMSMessageID, reset TTL và ảnh hưởng ordering. Nếu bắt buộc làm, cần giữ business `eventId` và quy tắc transaction/expiry rõ ràng; ưu tiên thiết kế tách queue khi SLA cứng.

### 8.5. Capacity, rate limit và deadline

- **Giới hạn tốc độ HIGH** hoặc dùng backpressure khi nguồn chấp nhận được.
- **Tăng công suất xử lý** khi tổng `λH+λL` vượt năng lực.
- **Không tự nâng tất cả message lên priority 9**: khi mọi message cùng priority, việc phân lớp trở nên vô nghĩa.
- **Giữ deadline nghiệp vụ riêng** với JMS TTL; message LOW bị expire không phải là hoàn thành đúng hạn.
- **Quan sát redelivery/poison message** chiếm worker; retry có thể làm starvation trầm trọng hơn.
- **Dùng idempotency** khi tăng consumer concurrency hoặc chuyển message giữa queue.

## 9. Đo starvation bằng metric theo priority

Một queue có throughput cao vẫn có thể làm LOW quá hạn. Cần đo **từng lớp** thay vì chỉ queue depth tổng.

| Metric đề xuất | Ý nghĩa |
|---|---|
| `enqueue_total{priority}` | Mức tải đầu vào theo priority |
| `completed_total{priority}` | Message đã hoàn tất theo priority |
| `oldest_pending_age_seconds{priority}` | LOW cũ nhất đã chờ bao lâu |
| `queue_wait_seconds{priority}` p50/p95/p99 | Tail latency riêng từng priority |
| `inflight_messages` | Message đã dispatch nhưng chưa hoàn tất |
| `consumer_busy_ratio` | Worker bão hòa hay còn năng lực |
| `expired_total{priority}` | Message hết hạn thay vì hoàn thành |
| `redelivery_total{priority}` | Retry có đang chiếm công suất không |

Tên metric ở bảng là **đề xuất chuẩn hóa cho observability**, không phải tên JMX/MBean chuẩn tồn tại giống hệt trên mọi Classic/Artemis. Một số số liệu phải instrument ở producer/consumer, hoặc truy vấn management theo phiên bản.

Ví dụ SLO nghiệp vụ **minh họa**:

~~~text
HIGH: p95 thời gian chờ < 2 giây
LOW:  99% hoàn tất < 15 phút
      oldest pending age < 10 phút để còn thời gian khắc phục
~~~

Nếu HIGH đạt SLO nhưng LOW chờ 30 phút, việc queue vẫn dequeue liên tục không đủ chứng minh hệ thống đúng. Metric thời gian chờ phải dùng đồng hồ đáng tin; `System.currentTimeMillis()` từ nhiều host có thể lệch.

## 10. Các lỗi thiết kế thường gặp

| Lầm tưởng | Vì sao không đúng |
|---|---|
| “Priority 9 luôn xử lý trước priority 1.” | LOW có thể đã dispatch hoặc đang xử lý |
| “Chỉ cần thêm property `priority=9`.” | Không thay thế JMSPriority/header do provider gán |
| “Classic không cần cấu hình queue vẫn chắc chắn ưu tiên.” | Cần kiểm tra và bật `prioritizedMessages` phù hợp |
| “Có thể chép `prioritizedMessages` sang Artemis.” | Hai broker có schema khác nhau |
| “Prefetch=1 giải quyết starvation.” | Chỉ giảm buffer, không dành quota cho LOW |
| “Đẩy LOW từ priority 1 lên 9 sẽ tăng công suất.” | Không tăng CPU/IO và làm mất phân biệt giữa luồng |
| “Priority là FIFO toàn cục.” | Priority reordering và nhiều consumer không bảo đảm global FIFO |
| “LOW không thấy trong log nghĩa là message đã mất.” | Có thể pending, prefetch/in-flight, expired hoặc bị filter |
| “TTL ngắn giúp LOW hoàn thành sớm.” | Expiration bỏ message, không hoàn tất công việc |
| “Consumer priority và message priority giống nhau.” | Một bên chọn consumer, một bên ưu tiên message |
| “ACK thành công đồng nghĩa mọi message cùng priority xử lý đúng thứ tự.” | ACK là mốc messaging, không chứng minh business completion order |

## 11. Bài thực hành có đáp án

### A — HIGH được gửi sau LOW

Queue đã bật xử lý priority; trước khi consumer mở, producer commit `L1(p1), L2(p1), H1(p9), H2(p9)`.

**Giải thích:** Broker có thể dispatch HIGH trước LOW khi cả bốn còn trong backlog, ví dụ `H1,H2,L1,L2`. Không được coi đây là thứ tự bắt buộc trong mọi môi trường JMS vì prefetch, cursor, transaction và provider semantics.

### B — Vì sao HIGH phải đợi LOW?

Consumer đã prefetch 50 LOW rồi mới có H1(p9).

**Giải thích:** Message đã dispatch không tự bị thu hồi để H1 chen vào client buffer. Giảm prefetch, tách queue hoặc dành consumer riêng có thể cải thiện độ trễ HIGH.

### C — HIGH vượt công suất

Worker xử lý 80 msg/s, HIGH tới 85 msg/s và LOW tới 3 msg/s liên tục.

**Giải thích:** Trong mô hình strict priority, HIGH đã bão hòa; LOW không còn công suất dư được bảo đảm. Nâng LOW từ p1 lên p4 không xử lý được vì HIGH vẫn p9. Cần reserve capacity, rate limit hoặc mở rộng công suất.

### D — Tính thời gian chờ gần đúng

Có 400 HIGH pending; công suất 50 msg/s, HIGH mới tới 45 msg/s.

**Đáp án:** Tốc độ làm cạn backlog HIGH là `50−45=5 msg/s`, nên cần xấp xỉ `400/5=80 giây` trước khi backlog HIGH hiện tại hết. Đây là mô hình, chưa tính biến động và LOW khác.

### E — Thiết kế đáp ứng LOW deadline 15 phút

HIGH cần phản hồi trong vài giây, LOW vẫn phải hoàn tất trong 15 phút ở tải HIGH kéo dài.

**Giải pháp:** Tách `payments.high` và `payments.low`, dành pool LOW có năng lực tối thiểu và theo dõi oldest pending age. Một queue với p9/p1 tự nó không bảo đảm SLA LOW.

### F — Test không thấy reorder

LOW được gửi và consumer đã nhận trước khi HIGH xuất hiện một giây sau.

**Giải thích:** Đây không phải bằng chứng broker bỏ qua priority. Muốn thử cách xếp priority, hãy tạo **backlog chưa dispatch** gồm cả HIGH/LOW rồi mới mở consumer, giữ nguyên cấu hình và quan sát.

## 12. Checklist thiết kế và vận hành

- [ ] Chỉ dùng vài lớp priority có ý nghĩa nghiệp vụ, tránh ai cũng gửi priority 9.
- [ ] JMS producer đặt priority qua `setPriority` hoặc tham số `send`, không nhầm property tự tạo.
- [ ] Queue Classic đã bật `prioritizedMessages` ở đúng instance và đúng destination; Artemis dùng cấu hình riêng.
- [ ] Thử cả backlog trước khi consumer chạy và tải HIGH liên tục.
- [ ] Đã hiểu prefetch/in-flight, nhiều consumer, transaction, retry và order inversion.
- [ ] Có metric tuổi message theo HIGH/LOW và SLO p95/p99 cho từng lớp.
- [ ] Đã ước lượng `λH`, `λL`, `μ` trong giờ cao điểm.
- [ ] LOW có deadline thì có phần công suất được reserve hoặc fair scheduler có thể kiểm chứng.
- [ ] Không dùng TTL/expiry để che giấu việc LOW không được xử lý.
- [ ] Có idempotency khi tăng concurrency, requeue hoặc thay destination.
- [ ] Có rollback plan khi bật priority khiến nghiệp vụ thay đổi thứ tự xử lý.
- [ ] Đã kiểm tra ordering riêng cho các message phụ thuộc nhau cùng business key.

## 13. Kết luận

**Message priority** trong JMS cho phép provider ưu tiên message quan trọng trong phạm vi mức **0–9**, với mặc định thường là **4**. ActiveMQ Classic có chính sách `prioritizedMessages` dành cho queue; Artemis hỗ trợ priority với mô hình address/queue và cấu hình khác. Nhưng **priority không đồng nghĩa với sắp xếp tuyệt đối hay công bằng**.

Khi HIGH liên tục tiêu thụ gần hết năng lực xử lý, LOW có thể chờ rất lâu. Prefetch và in-flight làm thứ tự thực tế càng khác mô hình lý tưởng. Muốn đáp ứng deadline của LOW, phải **đo tuổi backlog theo priority và bảo vệ phần công suất của LOW** bằng tách queue, rate limit, tăng capacity hoặc fair scheduling. Priority xác định **message nào được ưu tiên xét trước**; năng lực và fairness mới quyết định **mọi nhóm có tiến độ đúng yêu cầu hay không**.
