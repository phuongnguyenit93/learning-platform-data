# Artemis message redistribution khi consumer thay đổi vị trí

> **Chương:** Kết nối nhiều broker  
> **Phạm vi:** Cơ chế **message redistribution** trong cụm Apache ActiveMQ Artemis khi một queue trên node cũ còn backlog nhưng consumer phù hợp đã chuyển sang node khác. Bài đi sâu vào `redistribution-delay`, cluster `message-load-balancing`, cấu hình 2 broker, kiểm chứng bằng Java/Jakarta JMS và kiểm soát redelivery/idempotency. **Không đồng nhất redistribution với broker HA replication, JMS client failover hoặc routing ban đầu của một message mới.**

## 1. Bài toán: backlog ở B, worker đã sang A

Một cụm Artemis hai node lưu job cho dịch vụ xử lý nền:

- **Broker B**, listener Core/JMS cổng `61617`, đang giữ các message persistent tại queue `lab.redistribute`.
- **Broker A**, cổng `61616`, có queue cùng tên và routing type nhưng ban đầu không có backlog.
- Worker trước đây nhận việc ở B đã đóng; worker mới chỉ kết nối tới A.

~~~mermaid
flowchart LR
    P["Producer gửi vào B"] --> QB["B: queue lab.redistribute\nJ1...J20 pending"]
    OLD["Consumer B đã đóng"] -. "consumerCount B = 0" .-> QB
    QB -->|"Cluster redistribution"| QA["A: queue lab.redistribute"]
    QA --> NEW["Consumer A đang nhận"]
~~~

Nếu không có cơ chế chuyển phù hợp, queue B có thể tiếp tục giữ backlog trong khi consumer A rảnh. **Message redistribution** cho phép broker đang giữ message chuyển **backlog chưa được xử lý hoàn tất** sang broker khác có queue/consumer tương ứng.

Đây **không phải** cơ chế tự di chuyển một process Java từ B sang A. Client tự ngắt/kết nối sang A; cluster nhìn thấy **remote consumer demand** và broker B chuyển các message đang chờ nếu điều kiện redistribution được đáp ứng.

### 1.1. Phạm vi bảo đảm thực tế

Redistribution không có nghĩa “mọi message sẽ lập tức chạy theo consumer”:

- Cluster connection phải nhận diện remote queue/consumer đúng.
- Queue nguồn không còn consumer cục bộ phù hợp theo quy tắc của broker.
- `redistribution-delay` phải cho phép chuyển; giá trị `-1` có thể vô hiệu hóa.
- Message đã dispatch/in-flight ở consumer B không tự bị thu hồi trước khi connection/session xử lý xong hoặc rollback.
- Selector, grouping, filter, routing type, message-load-balancing mode và topology có thể ảnh hưởng.
- Message mới gửi khi A đã có consumer có thể **được route trực tiếp tới A**, không hề trải qua redistribution.

**Kết quả cần chứng minh**: một `jobId` đã được enqueue ở B **trước khi A có consumer**, sau đó được consumer A xử lý thành công khi B không có local consumer.

## 2. Phân biệt redistribution với routing, failover và replication

| Cơ chế | Điều kiện kích hoạt | Thứ thay đổi | Ý nghĩa |
|---|---|---|---|
| **Initial message routing** | Producer gửi message mới | Chọn queue local hoặc remote theo load-balancing mode | Không đòi backlog đã tồn tại |
| **Redistribution** | Queue nguồn có backlog, thiếu local demand; remote node có consumer thích hợp | Chuyển **message đã lưu trong queue** sang queue remote | Tránh tồn đọng do consumer đổi node |
| **Client reconnect/failover** | Kết nối JMS/transport mất hoặc client được restart | Đổi **nơi client kết nối** | Không tự di chuyển mọi backlog cũ |
| **HA replication/shared-store failover** | Broker primary lỗi, backup takeover | Chuyển quyền hoạt động trên state/storage theo HA policy | Bảo vệ availability/durability trước lỗi broker |
| **Scale-down** | Node dừng theo quy trình broker | Chuyển state/message theo cơ chế scale-down | Không phải cùng trigger với redistribution |

Bài toán ở đây là **cả A và B vẫn chạy**, mỗi broker có storage riêng. Chỉ có vị trí consumer thay đổi. Nếu B chết và không thể truy cập journal/storage, redistribution **không thể thay thế HA/backup** để khôi phục body không còn sẵn có.

### 2.1. Vì sao routing ON_DEMAND không đủ cho message cũ?

Một timeline có thể kiểm chứng:

~~~text
T0  A và B có queue lab.redistribute, chưa có consumer.
T1  Producer kết nối trực tiếp B và commit J1...J20.
    -> Queue B giữ backlog: không có remote consumer demand.
T2  Worker B nhận/commit J1 và J2, rồi đóng.
    -> Queue B còn J3...J20; consumerCount(B) = 0.
T3  Worker A kết nối vào queue lab.redistribute tại A.
    -> B biết A có remote consumer demand.
T4  Sau khi đủ điều kiện delay và routing, backlog được redistribute.
T5  Worker A commit J3...J20.
~~~

Nếu cho A chạy **trước T1**, message mới có thể được **initially forwarded** từ B sang A theo `ON_DEMAND`. Thấy A nhận message khi đó **không** chứng minh redistribution.

## 3. Các điều kiện phải có trên source và destination

| Điều kiện | Vì sao quan trọng? | Cách kiểm chứng |
|---|---|---|
| A và B chung cluster topology | B phải biết remote binding ở A | Cluster links, topology/log không lỗi |
| Cluster connection bao phủ address | Nếu address bị filter khỏi cluster, không có đường chuyển | Kiểm tra prefix/filter cluster connection |
| Queue cùng logic/routing phù hợp | Remote queue cần nhận message theo routing thích hợp | Cả hai có anycast queue `lab.redistribute` |
| B có backlog đã commit | Không có pending message thì không có gì để chuyển | `messageCount(B)>0` trước khi A có consumer |
| B không còn local consumer | Redistribution không nhằm cướp việc khỏi consumer B đang hoạt động | `consumerCount(B)=0` |
| A có consumer phù hợp | Có nơi cần message đang chờ | `consumerCount(A)>0` |
| Address setting của B bật redistribution | `-1` nghĩa là disabled | Effective `redistribution-delay` trên B |
| Cluster load-balancing mode tương thích | Mode `OFF` có thể ngăn forwarding/redistribution | Lab dùng `ON_DEMAND` |
| B/A trao đổi cluster messages được | Cluster authentication hoặc connector lỗi làm không có remote demand | Log/JMX cluster, thử cluster reachability |
| Không bị cấu hình đặc biệt chặn | Selector, JMSXGroupID, exclusive/last-value/non-destructive có semantics riêng | Bắt đầu với queue thường, không selector |

**Điểm dễ sai:** `redistribution-delay` nằm trong **address-settings**, vì vậy cần match **tên address**, không phải tên consumer, broker hoặc JMS connection. Với `lab.redistribute`, chọn exact match để giới hạn tác động của lab.

### 3.1. Redistribute không có nghĩa preempt message đang chạy

Message có thể đã:

- Được dispatch/prefetch tới client B nhưng chưa được app xử lý.
- Được app B nhận nhưng chưa `acknowledge()` hoặc `session.commit()`.
- Hoàn tất thay đổi database nhưng broker chưa nhận JMS ACK.

Nếu B đóng/mất kết nối, Artemis xử lý những delivery chưa ACK theo rollback/redelivery; message lại trở thành pending nếu còn hợp lệ. **Sau đó** nó có thể đủ điều kiện chuyển sang A.

~~~mermaid
stateDiagram-v2
    [*] --> PendingB: send/commit vào B
    PendingB --> InflightB: dispatch B
    InflightB --> Completed: ACK/commit B
    InflightB --> PendingB: rollback/lost connection
    PendingB --> Waiting: no local consumer, remote A demand
    Waiting --> PendingA: redistribution
    PendingA --> InflightA: dispatch A
    InflightA --> Completed: ACK/commit A
    InflightA --> PendingA: rollback/reconnect
~~~

Sơ đồ là **mô hình khái niệm**, không phải các state name/transaction internals của Artemis. Đừng dựa vào sơ đồ để suy rằng database của consumer được commit nguyên tử cùng JMS transaction.

### 3.2. Một consumer “treo” vẫn có thể giữ local demand

Nếu `consumerCount(B)>0` nhưng worker B bị treo vì SQL lock hoặc đang xử lý một job rất lâu, Artemis vẫn có thể coi B là nơi có demand. Bật `redistribution-delay=0` không giải quyết một **consumer chưa thực sự đóng**.

Kiểm tra consumer count, delivering count, prefetch/credits, thời gian processing và khả năng broker đã phát hiện disconnect; tránh giả định “app đã được scale down” đồng nghĩa local queue consumer đã biến mất.

## 4. message-load-balancing quyết định cách cluster chuyển message

Trong Artemis, `cluster-connection` có `message-load-balancing`. Giá trị ảnh hưởng cách message được route giữa các queue trên nhiều node, nên phải phân biệt nó với `redistribution-delay`.

| Mode | Hành vi cốt lõi | Liên quan tới bài toán consumer move |
|---|---|---|
| `ON_DEMAND` | Chuyển **message mới** tới node khác khi có consumer demand phù hợp | Lựa chọn lab: minh họa cả initial routing theo demand và redistribution backlog cũ |
| `STRICT` | Cân bằng việc forward giữa node/queue matching theo chính sách cluster, kể cả khi demand không giống ON_DEMAND | Không tự đồng nghĩa mọi worker sẽ nhận nhanh; backlog có thể tồn tại ở node không còn consumer |
| `OFF` | Tắt forward message theo cơ chế cluster load balancing thông thường | Không dùng để kỳ vọng chuyển backlog tự động qua cluster |
| `OFF_WITH_REDISTRIBUTION` | Giữ cơ chế ban đầu gần `OFF` nhưng cho phép **redistribution** khi consumer remote xuất hiện | Hữu ích nếu muốn giữ message mới ở node nhận nhưng giải phóng backlog bị mắc kẹt; kiểm tra **phiên bản Artemis hỗ trợ** |

**ON_DEMAND ≠ redistribution.** Có thể thấy message mới đi B→A do ON_DEMAND ngay khi send, trong khi các message đã enqueue B từ trước vẫn cần redistribution để chuyển đi.

**OFF_WITH_REDISTRIBUTION ≠ ON_DEMAND.** Dùng khi muốn giới hạn forwarding lúc nhận message mới nhưng vẫn cho phép một queue thiếu local consumers chuyển backlog sang nơi có demand. Kiểm tra release notes và runtime version trước khi dùng tên mode này trên hệ thống cũ.

Một cluster connection có thể chứa:

~~~xml
<message-load-balancing>ON_DEMAND</message-load-balancing>
~~~

Muốn đổi sang `OFF_WITH_REDISTRIBUTION`, làm trên **mọi cluster connection liên quan** với version hỗ trợ, restart/reload theo quy trình, rồi test cả message **mới** và message **đã nằm trong queue**. Không chỉ sửa một node nếu các node còn lại có chính sách khác.

## 5. redistribution-delay: bao lâu sau khi local consumer biến mất?

Artemis cung cấp thuộc tính `redistribution-delay` trong `<address-setting>`, đơn vị **mili giây**.

~~~xml
<!-- Fragment trong <address-settings> của Artemis broker.xml -->
<address-setting match="lab.redistribute">
  <redistribution-delay>3000</redistribution-delay>
</address-setting>
~~~

Các cấu hình thường dùng:

| Giá trị | Ý nghĩa | Đánh đổi |
|---|---|---|
| `-1` | Không cho tự động redistribution theo policy này | Backlog có thể nằm ở node cũ cho đến khi local consumer quay lại |
| `0` | Cho phép redistribution ngay khi có đủ điều kiện | Độ trễ thấp nhưng dễ chuyển qua lại khi consumer ngắt/kết nối liên tục |
| `3000` | Delay 3 giây theo cơ chế Artemis | Tránh chuyển vội trong một đợt reconnect ngắn |
| `30000` | Delay 30 giây | Giảm nguy cơ thrashing, nhưng job ở node khác chờ lâu hơn |

**Đây không phải TTL, redelivery-delay hay scheduled-delivery-delay.** `redistribution-delay` điều khiển thời điểm broker có thể xét chuyển backlog **khi queue không có local consumers**. Redelivery delay điều khiển retry sau rollback; hai timer có thể tương tác nhưng không thay thế nhau.

Với nhiều bản Artemis, giá trị mặc định của redistribution-delay là **`-1` (disabled)**; phải kiểm tra effective address settings theo version/deployment. Không kết luận từ việc thấy hai broker đã connect rằng redistribution tự động đã bật.

### 5.1. Đừng đặt SLA chính xác bằng mỗi delay

Nếu đặt `redistribution-delay=3000`, đừng hứa “message được consumer A nhận đúng 3 giây sau khi A connect”. Thời gian thực tế còn phụ thuộc:

- Mốc queue B trở thành không có consumer; timer có thể bắt đầu **trước** lúc A xuất hiện.
- Cluster propagation để B thấy binding/consumer demand của A.
- Khả năng message đủ điều kiện chuyển và tác động của transaction/selector/group.
- Kích thước backlog, tốc độ cluster bridge, page store, disk và network.
- Consumer A có credits và thực sự xử lý/commit được hay không.

**Thử nghiệm chính xác** cần log timestamp các mốc `consumerCount(B)=0`, `consumerCount(A)>0`, lần nhận job cũ đầu tiên và job cuối cùng hoàn tất.

### 5.2. Match theo address, không lấy FQQN làm policy

Một queue lab có thể được mô tả:

~~~text
Address: lab.redistribute
Queue:   lab.redistribute
FQQN:    lab.redistribute::lab.redistribute
~~~

Policy `match="lab.redistribute"` nhắm tên **address**. Không dùng `lab.redistribute::lab.redistribute` như một pattern mặc định cho address settings. Nếu dùng wildcard `match="#"`, hiệu ứng có thể ảnh hưởng nhiều address khác; lab nên sử dụng **exact match**.

Trong production, cấu hình match có thể nhận kế thừa từ pattern rộng, nên cần đọc **effective policy** thay vì chỉ nhìn một dòng XML.

## 6. Cấu hình hai Artemis broker để kiểm chứng thực tế

Hai instance Artemis chạy trên **cùng máy lab**, mỗi broker có **data directory riêng**. Cổng phía client/Core:

| Broker | Netty/Core acceptor | Connector dùng để node khác tìm tới |
|---|---|---|
| A | `127.0.0.1:61616` | `node-a` |
| B | `127.0.0.1:61617` | `node-b` |

Ví dụ dưới đây chỉ là các **fragment của `<core>` trong `etc/broker.xml`**. Nếu file của bạn đã có phần `<connectors>`/`<acceptors>`/`<cluster-connections>`, **gộp phần tử con vào section hiện có**, không tạo hai section trùng. Thứ tự và các phần tử khác phải theo schema của đúng Artemis version.

### 6.1. Broker A — local connector A, remote connector B

~~~xml
<!-- BROKER A: ghép vào các section tương ứng của <core> -->
<connectors>
  <connector name="node-a">tcp://127.0.0.1:61616</connector>
  <connector name="node-b">tcp://127.0.0.1:61617</connector>
</connectors>

<acceptors>
  <acceptor name="core">tcp://0.0.0.0:61616?protocols=CORE</acceptor>
</acceptors>

<cluster-connections>
  <cluster-connection name="lab-cluster">
    <connector-ref>node-a</connector-ref>
    <retry-interval>500</retry-interval>
    <message-load-balancing>ON_DEMAND</message-load-balancing>
    <max-hops>1</max-hops>
    <static-connectors>
      <connector-ref>node-b</connector-ref>
    </static-connectors>
  </cluster-connection>
</cluster-connections>
~~~

`connector-ref=node-a` là connector **của node A**, dùng làm địa chỉ node được công bố trong cluster. Trong `static-connectors`, A trỏ tới **B**.

### 6.2. Broker B — local connector B, remote connector A

~~~xml
<!-- BROKER B: ghép vào các section tương ứng của <core> -->
<connectors>
  <connector name="node-a">tcp://127.0.0.1:61616</connector>
  <connector name="node-b">tcp://127.0.0.1:61617</connector>
</connectors>

<acceptors>
  <acceptor name="core">tcp://0.0.0.0:61617?protocols=CORE</acceptor>
</acceptors>

<cluster-connections>
  <cluster-connection name="lab-cluster">
    <connector-ref>node-b</connector-ref>
    <retry-interval>500</retry-interval>
    <message-load-balancing>ON_DEMAND</message-load-balancing>
    <max-hops>1</max-hops>
    <static-connectors>
      <connector-ref>node-a</connector-ref>
    </static-connectors>
  </cluster-connection>
</cluster-connections>
~~~

`connector-ref=node-b` là connector **của B**; B dùng `static-connectors` để kết nối A. Trong hai-node lab, `max-hops=1` là lựa chọn đơn giản cho forwarding một bước.

**Các điều kiện còn phải hoàn thành ngoài fragment:**

- Mỗi broker có **persistent journal/bindings/paging/large-message directories riêng**; hai active nodes không được cùng ghi một journal.
- Hai broker phải có cluster credentials/security/role tương thích theo version; không đưa password thật vào Git.
- Broker A/B cần **node identity riêng** được lưu trong từng data directory.
- Nếu broker.xml hiện có `<address>` filter của `cluster-connection`, phải đảm bảo nó **bao phủ address `lab.redistribute`**. Mẫu trên không thêm filter để tránh chặn bài lab.
- Chạy hai broker cùng host còn phải tách các cổng khác (web console, management, extra acceptors), không chỉ hai cổng Core trên.
- `127.0.0.1` chỉ đúng khi broker A và B cùng máy/namespace mạng. Nếu chạy qua Docker/Kubernetes, dùng hostname/DNS thực sự có thể truy cập **từ broker kia**, không dùng localhost giữa hai container.
- Nếu broker dùng TLS trên cluster connector, phải cấu hình CA, SAN, user/role cluster và certificate tương ứng; ví dụ này chỉ tập trung cơ chế redistribution nên dùng Core TCP trong lab cô lập.

### 6.3. Queue và delay giống nhau trên cả hai node

Mỗi broker cần một anycast queue có cùng tên để tạo backlog tương ứng:

~~~xml
<!-- Trong <addresses> của cả A và B -->
<address name="lab.redistribute">
  <anycast>
    <queue name="lab.redistribute" durable="true"/>
  </anycast>
</address>
~~~

Và address setting:

~~~xml
<!-- Trong <address-settings> của cả A và B -->
<address-setting match="lab.redistribute">
  <redistribution-delay>3000</redistribution-delay>
</address-setting>
~~~

**Vì sao ở cả A và B?** Trong bài lab B là nguồn cần chuyển sang A. Trong production, consumer có thể đổi vị trí ngược lại; đặt policy cả hai giúp A cũng có thể redistribute khi nó trở thành node có backlog nhưng không còn consumer.

Khi một cluster có nhiều anycast queues trên cùng address, hãy phân biệt **route giữa nhiều queues** với **redistribute backlog đã nằm trong một queue**. Bài này cố ý dùng một queue cùng tên trên mỗi node, không tạo queue theo tên worker.

## 7. Chứng minh cluster link hoạt động trước khi gửi batch

Hai broker cùng chạy **chưa đủ**. Làm precheck bằng web console/JMX/management API tương ứng Artemis version:

1. Cluster topology từ A và B cho thấy **hai nodes**, connection không liên tục retry authentication/transport.
2. Trên cả A/B có address `lab.redistribute` với anycast queue bền `lab.redistribute`.
3. Đảm bảo application user có quyền gửi/nhận; cluster user đủ quyền nội bộ để trao đổi bindings/forwarding.
4. Trước khi test, không có consumer và backlog tại A/B của batch cũ.
5. Ban đầu gửi tới B khi chưa có consumer A; **queue B** phải tăng messageCount.
6. Khi worker B đóng, **consumerCount(B)=0**; chờ in-flight do worker cũ được giải quyết.
7. Khi worker A vào, **consumerCount(A)>0**; sau đó log của A xuất hiện eventId từ backlog gửi ở bước 5.

Các tên chỉ số quản lý thay đổi theo Artemis version. Những khái niệm cần quan sát gồm **message count/pending**, **delivering count**, **consumer count**, **messages added/acknowledged**, và trạng thái cluster connection.

Lưu ý: queue A có thể không giữ message lâu đủ để console thấy pending tăng, vì consumer A nhận/commit ngay. **Log batchId, jobId và số ACK** ở Java đáng tin hơn một ảnh chụp queue depth. Không kết luận redistribution chỉ vì tổng `messagesAdded` tăng: còn phải chứng minh message được **enqueue B trước khi A có demand**.
## 8. Java Jakarta JMS: tạo batch trên B, nhận một phần ở B và phần còn lại ở A

Lab dùng **Java 17+**, Artemis broker/client có phiên bản tương thích và artifact Maven `org.apache.activemq:artemis-jakarta-client`. Các lớp JMS thuộc `jakarta.jms`, **không** dùng `javax.jms` của ActiveMQ Classic 5.x.

Ví dụ Maven dependency khi project chưa có BOM quản lý Artemis:

~~~xml
<properties>
  <!-- Version minh họa có thực; thay bằng version đã kiểm thử
       tương thích với broker/JDK trong hệ thống của bạn. -->
  <artemis.version>2.37.0</artemis.version>
</properties>
<dependencies>
  <dependency>
    <groupId>org.apache.activemq</groupId>
    <artifactId>artemis-jakarta-client</artifactId>
    <version>${artemis.version}</version>
  </dependency>
</dependencies>
~~~

Đây là **fragment Maven**, không phải `pom.xml` đầy đủ. Không hiểu version ví dụ là bản mới nhất; production nên quản lý version bằng BOM/lockfile và integration test cùng broker version đang chạy.

Hai chương trình nhận port ở đối số để **ép chọn endpoint A hay B cho kết nối đầu tiên**. Để lặp lại lab, cần kiểm tra connection thực sự được cấp consumer ở node mong muốn trong broker console; nếu bạn có custom client topology/load balancing hoặc failover URL, nó có thể chọn node khác.

### 8.1. Producer: gửi persistent batch vào B, commit trước khi có consumer A

File `ClusterBatchSender.java`:

~~~java
import jakarta.jms.DeliveryMode;
import jakarta.jms.JMSContext;
import jakarta.jms.JMSProducer;
import jakarta.jms.Queue;

import org.apache.activemq.artemis.jms.client.ActiveMQConnectionFactory;

public final class ClusterBatchSender {
    private static final String QUEUE = "lab.redistribute";

    private static String requiredEnv(String name) {
        String value = System.getenv(name);
        if (value == null || value.isEmpty()) {
            throw new IllegalStateException("Missing env " + name);
        }
        return value;
    }

    public static void main(String[] args) {
        if (args.length != 3) {
            throw new IllegalArgumentException(
                "Usage: ClusterBatchSender <port> <batchId> <count>");
        }

        int port = Integer.parseInt(args[0]);
        String batchId = args[1];
        int count = Integer.parseInt(args[2]);
        if (port < 1 || port > 65535 || count < 1
                || !batchId.matches("[A-Za-z0-9_-]{1,50}")) {
            throw new IllegalArgumentException("Invalid arguments");
        }

        String url = "tcp://127.0.0.1:" + port;
        ActiveMQConnectionFactory factory =
                new ActiveMQConnectionFactory(url);

        try (JMSContext context = factory.createContext(
                requiredEnv("JMS_USER"),
                requiredEnv("JMS_PASSWORD"),
                JMSContext.SESSION_TRANSACTED)) {

            Queue queue = context.createQueue(QUEUE);
            JMSProducer producer = context.createProducer()
                    .setDeliveryMode(DeliveryMode.PERSISTENT)
                    .setTimeToLive(0L);

            try {
                for (int i = 1; i <= count; i++) {
                    String jobId = batchId + "-" + i;
                    producer.setProperty("batchId", batchId)
                            .setProperty("jobId", jobId)
                            .setProperty("sequence", i);

                    // Body nhỏ để tránh paging/large-message tác động lab.
                    producer.send(queue, "JOB:" + jobId);
                }

                context.commit();
                System.out.println("COMMIT_CONFIRMED brokerPort="
                        + port + " batch=" + batchId + " count=" + count);
            } catch (RuntimeException error) {
                // Nếu mất phản hồi commit, outcome có thể UNKNOWN.
                // Rollback ở client không chứng minh broker chưa commit.
                try {
                    context.rollback();
                } catch (RuntimeException rollbackError) {
                    error.addSuppressed(rollbackError);
                }
                throw error;
            }
        }
    }
}
~~~

**Lý do sử dụng transaction:**

- `SESSION_TRANSACTED` gom batch thành transaction gửi JMS.
- Dòng `COMMIT_CONFIRMED` chỉ in sau `context.commit()` thành công.
- `DeliveryMode.PERSISTENT` và queue durable kiểm tra việc giữ backlog sau restart trong failure model phù hợp; bài này **không tự kiểm chứng HA durability**.
- `jobId` và `batchId` ổn định giúp đối soát mỗi job **bất kể message có bị forward/redeliver**.
- Password được lấy từ environment trong lab, **không** in log hay đưa vào CLI args. Production nên dùng nguồn secret có rotation và quản lý vòng đời process.
- Nếu producer mất phản hồi commit, một lần gửi lại có thể tạo hai message chứa cùng `jobId`; phải dựa trên idempotency, không chỉ JMSMessageID.

### 8.2. Consumer: ghi node, jobId và commit từng message

File `ClusterBatchReceiver.java`:

~~~java
import jakarta.jms.JMSConsumer;
import jakarta.jms.JMSContext;
import jakarta.jms.Message;
import jakarta.jms.Queue;
import jakarta.jms.TextMessage;

import org.apache.activemq.artemis.jms.client.ActiveMQConnectionFactory;

public final class ClusterBatchReceiver {
    private static final String QUEUE = "lab.redistribute";

    private static String requiredEnv(String name) {
        String value = System.getenv(name);
        if (value == null || value.isEmpty()) {
            throw new IllegalStateException("Missing env " + name);
        }
        return value;
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 3) {
            throw new IllegalArgumentException(
                "Usage: ClusterBatchReceiver <port> <batchId> <maxCount>");
        }

        int port = Integer.parseInt(args[0]);
        String expectedBatch = args[1];
        int maxCount = Integer.parseInt(args[2]);
        if (port < 1 || port > 65535 || maxCount < 1
                || !expectedBatch.matches("[A-Za-z0-9_-]{1,50}")) {
            throw new IllegalArgumentException("Invalid arguments");
        }

        ActiveMQConnectionFactory factory =
                new ActiveMQConnectionFactory("tcp://127.0.0.1:" + port);

        try (JMSContext context = factory.createContext(
                requiredEnv("JMS_USER"),
                requiredEnv("JMS_PASSWORD"),
                JMSContext.SESSION_TRANSACTED)) {

            Queue queue = context.createQueue(QUEUE);
            JMSConsumer consumer = context.createConsumer(queue);
            context.start();

            int committed = 0;
            while (committed < maxCount) {
                Message message = consumer.receive(30_000L);
                if (message == null) {
                    System.out.println("RECEIVE_TIMEOUT port=" + port
                            + " committed=" + committed);
                    break;
                }

                try {
                    String batchId =
                            message.getStringProperty("batchId");
                    String jobId =
                            message.getStringProperty("jobId");
                    int sequence =
                            message.getIntProperty("sequence");

                    if (!expectedBatch.equals(batchId)
                            || jobId == null
                            || !(message instanceof TextMessage)) {
                        // Bài lab yêu cầu queue sạch, không có batch khác.
                        context.rollback();
                        throw new IllegalStateException(
                                "Unexpected message on lab queue");
                    }

                    String body = ((TextMessage) message).getText();
                    System.out.printf(
                            "RECEIVED port=%d batch=%s job=%s "
                            + "seq=%d redelivered=%s jmsId=%s body=%s%n",
                            port, batchId, jobId, sequence,
                            message.getJMSRedelivered(),
                            message.getJMSMessageID(), body);

                    // Demo chỉ log. Production: commit DB+inbox trước JMS.
                    context.commit();
                    committed++;
                    System.out.println("ACK_COMMITTED port="
                            + port + " jobId=" + jobId);
                } catch (Exception processingFailure) {
                    try {
                        context.rollback();
                    } catch (RuntimeException rollbackFailure) {
                        processingFailure.addSuppressed(rollbackFailure);
                    }
                    throw processingFailure;
                }
            }

            System.out.println("DONE port=" + port
                    + " committed=" + committed);
        }
    }
}
~~~

**Điểm cần đọc kỹ:**

1. Mỗi process có `JMSContext`/consumer riêng; cùng tên **JMS Queue** không có nghĩa consumer A nhận bản sao cùng job mà B đã commit.
2. Consumer commit ngay từng message sau khi log. Trong ứng dụng có SQL/service call, **không** xem log là side effect bền; cần inbox/idempotency và ACK sau xử lý.
3. `JMSRedelivered` giúp quan sát delivery lại nhưng **không phải header chứng minh message đã trải qua cluster redistribution**; phải dùng timeline và broker queue metrics.
4. Mã ném lỗi nếu gặp batch không mong đợi; thử trên **queue riêng, sạch** để không rollback vĩnh viễn một job của batch khác.
5. Ngắt B bằng cách process kết thúc sau `maxCount=2` sẽ đóng consumer; dùng `consumerCount(B)=0` để xác nhận B thực sự không còn local demand.
6. `JMSContext` quản lý một session transacted; các method liên quan được dùng tuần tự trong process, không chia cùng context cho các worker thread song song.

## 9. Quy trình lab: chứng minh backlog J3...J20 chuyển B→A

Đặt biến môi trường `JMS_USER` và `JMS_PASSWORD` bằng thông tin của user lab được cấp đúng quyền. Sau khi build Maven và tạo classpath đúng, các dòng sau là **lệnh mẫu với `CLASSPATH` đã được chuẩn bị**:

~~~bash
# 1. Cả A và B đang chạy, queue hai node sạch.
# Không chạy consumer A ở thời điểm publish.
java -cp "$CLASSPATH" ClusterBatchSender 61617 RUN001 20

# 2. Chỉ cho B xử lý hai message rồi đóng hẳn consumer.
java -cp "$CLASSPATH" ClusterBatchReceiver 61617 RUN001 2

# 3. Xác nhận broker B không còn consumer. Sau đó mở A.
java -cp "$CLASSPATH" ClusterBatchReceiver 61616 RUN001 18
~~~

Trong PowerShell hoặc Windows CMD, cú pháp classpath/env khác shell Bash ở trên; dùng IDE/Maven Exec nếu đang ở Windows. Không đưa password vào command-line args.

### 9.1. Những mốc bắt buộc ghi lại

| Mốc | B | A | Điều cần ghi |
|---|---|---|---|
| Trước publish | Queue rỗng, consumer 0 | Queue rỗng, consumer 0 | Broker instance/cluster link đều healthy |
| Sau `RUN001 20` | 20 message pending, nếu không có consumer/initial routing khác | Chưa có message nhận | Có bằng chứng batch **đang ở B** |
| Sau receiver B nhận 2 | 18 message còn trách nhiệm giao; consumer trở về 0 | Chưa có consumer | Log `ACK_COMMITTED` J1/J2 ở B |
| Mở receiver A | B thấy remote demand qua cluster | consumerCount(A)=1 | Mốc A bắt đầu chờ |
| Sau redistribution | Pending ở B giảm khi chuyển/ACK | A nhận J3...J20 | Log 18 job ID đã gửi trước đó |
| Sau hoàn tất | Không còn pending của RUN001 | Đã ACK đủ 18 | Tổng 20 jobId duy nhất đã xử lý |

**Số queue count ở một thời điểm là snapshot, có thể đổi nhanh khi consumer nhận.** Nếu chưa từng chụp được B có backlog trước khi A mở, thí nghiệm **chưa phân biệt** được initial forwarding với redistribution.

Đừng mặc định message luôn được phân phối/hoàn thành theo sequence tăng. Vì cluster, prefetch, chuyển hướng và transaction, chỉ nên dùng sequence để **đối soát đủ tập**, không để kết luận FIFO tuyệt đối.

### 9.2. Kiểm chứng với một lần bật/tắt redistribution

Chạy hai lần độc lập trên queue sạch (hoặc dùng batch/instance lab riêng):

- **Lần 1:** `redistribution-delay=-1` trên B. Nếu không còn consumer B, A có thể không nhận backlog J3...J20 từ B qua redistribution. Kiểm tra broker vẫn có cluster link và queue B vẫn giữ pending.
- **Lần 2:** `redistribution-delay=3000` trên B (và tương tự A). Cùng quy trình producer/consumer, A nhận dần phần backlog từ B khi đủ điều kiện.

Việc đổi `broker.xml` cần reload/restart theo cách version hỗ trợ; sau đó xác minh **effective policy** đã thực sự được áp dụng. **Không đổi config trong lúc batch RUN001 vẫn chưa xử lý** nếu muốn có thí nghiệm độc lập, dễ diễn giải.

### 9.3. Thử ngược A→B

Sau khi hoàn tất batch đầu, đảo vai:

1. Producer đưa batch mới tới A **khi B chưa có consumer**.
2. Cho consumer A xử lý vài job và đóng.
3. Mở consumer B, đối soát job ID trước đó được nhận tại B.

Phép thử hai chiều xác minh địa chỉ connectors, cluster credentials, address-settings và cấu hình queue ở **cả hai node**, tránh tình trạng chỉ một phía forward được.
## 10. Các tình huống khó: consumerCount, selector, prefetch và group

Một cluster đã connected, policy `redistribution-delay=3000` đúng mà A vẫn chưa nhận backlog **không nhất thiết** là Artemis lỗi. Hãy phân tách từng giả thuyết.

### 10.1. B vẫn có local consumer

Một worker có thể bị **kẹt ở ứng dụng** nhưng JMS connection vẫn sống. Management còn `consumerCount(B)=1`. Khi đó điều kiện queue không có local consumers để trigger redistribution có thể chưa đạt.

Cách xử lý: xác minh instance/process, session/consumer lifecycle, graceful shutdown và broker connection failure detection. Đừng mặc định tăng/giảm `redistribution-delay` sẽ thu hồi message từ một consumer cũ vẫn connected.

### 10.2. Message đã in-flight ở B

Prefetch/consumer-window có thể làm B có các message **delivering**, chưa ACK, kể cả worker chưa gọi `receive()` cho từng message. Sau khi client đóng, message chưa ACK cần trở lại trạng thái được broker quản lý theo semantics rollback/reconnect, rồi mới có thể chuyển tiếp.

Vì vậy cần quan sát đồng thời:

~~~text
B.messageCount
B.deliveringCount
B.consumerCount
A.consumerCount
application-logs: jobId, ACK_COMMITTED, connection close
~~~

Đừng chỉ nhìn `messageCount(B)`; một phần backlog có thể đang **in-flight**, không phải đã biến mất.

### 10.3. Selector, filter và routing không tương thích

Ví dụ A có consumer dùng selector:

~~~java
// Chỉ các message có property "kind=pdf" thỏa selector.
JMSConsumer consumer =
        context.createConsumer(queue, "kind = 'pdf'");
~~~

Trong khi message cũ ở B không có property `kind`, hoặc `kind='csv'`. A **không phải consumer đủ điều kiện** cho những message đó; không nên kết luận cluster có demand phù hợp chỉ từ `consumerCount(A)>0`.

Tương tự, kiểm tra queue filter, anycast/multicast routing type, tên queue và FQQN thực tế. Một subscription trên **topic khác** không làm demand của queue này xuất hiện.

**Bài lab gốc cố ý không dùng selector.** Nếu muốn test selector, thêm property vào producer tương ứng và ghi lại kết quả lọc.

### 10.4. JMSXGroupID và thứ tự theo business key

Khi một ứng dụng đặt:

~~~java
message.setStringProperty("JMSXGroupID", accountId);
~~~

Artemis có cơ chế message grouping, và hành vi khi consumer rời node có thể phụ thuộc group ownership/group handler, cluster topology và version. Cần test:

- Message cùng group có còn được xử lý đúng ranh giới business ordering sau chuyển không?
- Nếu một message chưa ACK bị redeliver, consumer mới có xử lý trùng side effect không?
- Có hot group giữ backlog trên một consumer/node?
- Thay đổi hoặc reset group owner trong failover có làm thứ tự hoàn thành khác kỳ vọng không?

**Không dùng redistribution làm bảo đảm FIFO toàn cụm**. Nó giải quyết khả năng tìm nơi tiêu thụ backlog, không tự giải quyết tất cả ordering theo `orderId`.

### 10.5. Consumer ở A ngừng ngay sau khi B bắt đầu chuyển

Nếu A vừa có consumer thì lại mất kết nối, B có thể chưa chuyển xong backlog; các message đã được chuyển sang A cũng có thể lại thành backlog thiếu consumer. Khi `redistribution-delay=0` trên cả hai node, workload dễ bị chuyển qua lại nếu consumers dao động.

Đây là **thrashing**: tăng cluster traffic và journal/disk work, trong khi business completion không tăng. Một delay dương nhỏ và chiến lược ổn định vị trí worker thường hợp lý hơn thay vì đặt luôn 0.

## 11. Redistribution không tự loại bỏ redelivery và duplicate

### 11.1. Crash sau database commit trước JMS commit

Một job `RUN001-7` ở B đã được consumer B nhận:

~~~text
B sends job RUN001-7 to Worker-B
Worker-B COMMIT database invoice/report result
Worker-B crashes before JMS ACK/commit
B returns unacknowledged delivery to pending state
Consumer-B no longer exists
A has remote consumer -> B redistributes job to A
Worker-A receives RUN001-7
~~~

Nếu Worker-A thực hiện lại side effect mà không có kiểm tra, cùng job có thể tạo **hai hóa đơn/báo cáo**. Redistrib không phải cơ chế exactly-once end-to-end.

Cách bảo vệ:

1. Producer tạo và giữ một **business `jobId` cố định** qua mọi retry.
2. Consumer ghi **idempotency inbox** với unique key `(consumerName, jobId)`.
3. Ghi business side effect và inbox trong **cùng database transaction** nếu cùng một DB.
4. Sau DB commit mới commit JMS session/ACK.
5. Khi redelivery tới A, consumer thấy inbox row đã tồn tại → bỏ qua side effect nhưng vẫn ACK/commit JMS.

Ví dụ PostgreSQL:

~~~sql
CREATE TABLE processed_jobs (
    consumer_name TEXT NOT NULL,
    job_id TEXT NOT NULL,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (consumer_name, job_id)
);

BEGIN;
INSERT INTO processed_jobs (consumer_name, job_id)
VALUES ('billing-workers', 'RUN001-7')
ON CONFLICT DO NOTHING
RETURNING job_id;

-- Trong code ứng dụng: chỉ thực hiện business mutation nếu
-- INSERT trên thực sự trả về một row mới.
-- INSERT INTO invoices (...);

COMMIT;
~~~

**Đừng chạy thay đổi nghiệp vụ vô điều kiện** sau `ON CONFLICT DO NOTHING`. Ranh giới điều kiện phải được code/SQL kiểm soát.

Nếu side effect là API bên ngoài database (email/payment/object storage), cần idempotency key ở provider hoặc một workflow state machine. Một inbox cục bộ không tự bảo đảm giao dịch nguyên tử với external API.

### 11.2. Producer commit unknown và cluster redistribution

Nếu producer gửi batch vào B nhưng mất response `commit()`, client không biết B đã commit chưa. Retry cùng batch có thể tạo **hai JMS messages cho cùng jobId**, rồi cả hai có thể được route/redistribute trong cluster.

Dùng **transactional outbox** giữ jobId/payload, và consumer idempotency; không lấy `JMSMessageID` làm business key, vì lần gửi lại thường tạo JMS ID mới.

### 11.3. JMSRedelivered không chỉ ra “đã redistribute”

`JMSRedelivered=true` cho biết provider coi đây là message được giao lại, không phải một trace bất biến của “B đã chuyển message sang A”. Một message có thể được chuyển mà không có `JMSRedelivered=true`, hoặc bị redeliver **trên cùng broker B** mà không có redistribution.

Để chứng minh đường đi, kết hợp:

- Log producer xác nhận batch được enqueue tại B khi A không có consumer.
- Queue B có backlog tại thời điểm đó.
- Queue B mất local demand, A có remote demand.
- Cluster connection đã established.
- Log consumer A nhận đúng `jobId` từ batch cũ.
- Message pending/delivering/ACK được đối soát ở cả hai nodes.

## 12. Tuning: chọn delay dựa trên biến động consumer, không theo cảm tính

Hai lực kéo ngược chiều:

- **Delay quá thấp:** consumer vừa reconnect đã khiến message chuyển qua cluster, tăng traffic và có thể thrash khi autoscaling/rebalancing dao động.
- **Delay quá cao:** consumer đã chuyển sang A nhưng backlog ở B vẫn đợi lâu, làm tăng `oldestPendingAge` và vi phạm deadline job.

Cách quyết định có kiểm chứng:

1. Thu thập thời gian reconnect bình thường của consumer B (ví dụ phân phối p95/p99 của downtime do deploy).
2. Thu thập SLA thời gian chờ tối đa của backlog và khả năng xử lý sau chuyển.
3. Chọn delay đủ tránh những disconnect **rất ngắn** nhưng không làm hỏng SLO.
4. Thử scale-down/scale-up, rolling restart worker và network blip trong lab.
5. Đo **thời gian từ B consumerCount=0 tới lúc A nhận job cũ đầu tiên**, và thời gian **drain hết backlog**.
6. Quan sát số lần message qua cluster bridge, network/disk utilization và redelivery/duplicate.
7. Nếu thay đổi `redistribution-delay`, reload/restart theo phương thức version hỗ trợ và kiểm tra effective setting.

Ví dụ mục tiêu minh họa:

| Đặc tính workload | Hướng chọn delay |
|---|---|
| Worker B thường reconnect trong 1–2 giây | Một delay dương như 3–5 giây có thể tránh chuyển vội |
| Worker chuyển zone thật sự trong nhiều phút | Không cần chờ quá lâu trước khi cho A xử lý |
| Message đặc biệt nhạy latency | Test delay thấp và giữ worker topology ổn định hơn |
| Workload streaming/backlog lớn | Đo traffic cluster, batch transfer và áp lực disk trước khi giảm delay |
| Việc phải xử lý đúng thứ tự theo business key | Cân nhắc grouping/partition, không dùng delay làm ordering guarantee |

Các số là ví dụ thảo luận, **không phải giá trị mặc định hoặc SLA của Artemis**.

### 12.1. Redistribution không làm tăng công suất hệ thống

Nếu B có 20.000 job đang chờ, worker A chỉ xử lý 10 job/s, chuyển backlog sang A **không** khiến nó hoàn tất tức thì. Nếu producer tiếp tục tạo 30 job/s, backlog vẫn tăng.

Phân biệt:

- **Queue redistribution latency:** message cũ mất bao lâu để được chuyển sang nơi có consumer.
- **Processing latency:** consumer cần bao lâu để hoàn tất business action.
- **Backlog drain time:** mất bao lâu để xử lý hết batch tích tụ.

Giám sát cả ba; tăng tốc message forwarding không thay thế scale consumer/database.

## 13. Ma trận chẩn đoán khi không thấy redistribution

| Quan sát | Nguyên nhân có thể | Kiểm chứng/hành động |
|---|---|---|
| B có 18 pending, A có consumer, **cluster link down** | Connector host/port, auth, TLS, network | Sửa cluster link, đừng chỉ giảm delay |
| Link healthy, B local consumerCount > 0 | Worker cũ chưa đóng hoặc connection zombie | Đóng/drain consumer B, quan sát in-flight |
| Link healthy, B consumer=0, A consumer=0 | Consumer A chưa start, kết nối sang node khác | Kiểm tra endpoint/connection và quản lý consumers |
| Link healthy, A consumerCount > 0 nhưng selector sai | Remote demand không phù hợp message | Test không selector rồi thêm filter có chủ đích |
| B có pending nhưng address filter cluster không khớp | Cluster connection không forward address đó | Kiểm tra `<address>` prefix và bindings |
| B policy vẫn `redistribution-delay=-1` | Chưa bật redistribution hoặc config không reload | Sửa exact address setting, restart/reload đúng version |
| Cluster dùng `OFF` | Forwarding/redistribution không như kỳ vọng | Dùng ON_DEMAND hoặc mode tương thích được version hỗ trợ |
| Queue A/B khác routing type hoặc tên queue | Không có remote matching binding | Provision một anycast queue tương ứng ở hai node |
| B message đang delivering/in-flight | B client prefetch hoặc transaction chưa resolve | Chờ/đóng B consumer hợp lệ; đo delivering count |
| A nhận vài job rồi dừng | Worker exception, DB bottleneck, ACK/rollback | Log lỗi, queue delivering, retry/DLQ |
| A nhận nhưng job ID khác kỳ vọng | Queue không sạch, batch cũ hoặc producer mới route trực tiếp | Dùng batchId độc nhất; tách thời điểm producer/consumer |
| Message nhanh chóng di chuyển A↔B | Consumer dao động, delay quá thấp | Giảm churn, dùng delay dương và quan sát topology |
| Queue B về 0 nhưng A không log | Expiry/purge/DLQ, selector, message đã consume ở đâu khác | Audit ACK/expiry/DLQ và toàn bộ consumers |
| Failover một broker rồi backlog mất | HA/persistence failure, không phải riêng redistribution | Điều tra journal/replication/backup theo failure model |

**Luôn đối soát message bằng business `jobId`**, thay vì so sánh một chỉ số queue count trước và sau rồi kết luận đã đủ message.

## 14. Fault injection để phân biệt đúng các cơ chế

### Thử A — ON_DEMAND chỉ route message mới

1. Mở consumer A từ đầu.
2. Gửi batch mới tới B.
3. Quan sát nhiều message có thể xuất hiện ở A ngay.
4. Xác nhận B **chưa từng giữ batch đó như pending backlog trước khi A mở**.

**Kết luận:** đây có thể là **initial forwarding**, không đủ chứng minh redistribution.

### Thử B — B có backlog trước khi consumer A xuất hiện

1. Gửi batch khi cả hai node không có consumer.
2. Chụp queue count ở B.
3. Cho B consume 2 job rồi đóng.
4. A subscribe; theo dõi phần backlog cũ đi B→A.

**Kết luận:** đã cô lập đường chuyển backlog, phù hợp mục tiêu của bài.

### Thử C — redistribution-delay=-1

1. Dùng batch mới và queue sạch.
2. Tắt redistribution trên address của B, xác minh policy đã áp dụng.
3. Lặp lại B giữ backlog rồi A xuất hiện.
4. Kiểm tra B giữ pending thay vì A nhận theo redistribution.

**Kết luận:** cluster link tồn tại không đồng nghĩa redistribution đã bật.

### Thử D — B còn local consumer, A rảnh

1. Để worker B còn kết nối nhưng mô phỏng xử lý chậm.
2. Mở worker A.
3. Đo consumerCount/deliveringCount B và queue lag.
4. Đóng B đúng cách rồi so hành vi.

**Kết luận:** phải hiểu chính xác trạng thái consumer tại nguồn.

### Thử E — kill worker B sau DB commit trước JMS commit

1. Lưu `jobId` và business side effect vào một transaction DB.
2. Kill B worker trước JMS commit.
3. Mở A; quan sát redelivery/redistribution theo policy.
4. Xác minh inbox không cho tạo side effect trùng.

**Kết luận:** chuyển message không bảo đảm exactly-once business processing.

### Thử F — cluster link gián đoạn

1. Khi có backlog ở B, chặn đường cluster A↔B **chỉ trong lab cô lập**.
2. A có consumer nhưng B không thể forward.
3. Khôi phục link, quan sát topology và backlog drain.
4. Đảm bảo không có split brain/HA khác bị ảnh hưởng.

**Kết luận:** redistribution cần một cluster connection khỏe; nó không phải bộ lưu và chuyển dữ liệu khi peer vĩnh viễn mất.

## 15. Bài tập suy luận kèm đáp án

### A. Message ở B, A có consumer; tại sao chưa chuyển?

B còn `consumerCount=1` và `deliveringCount=50`, dù đội vận hành nghĩ worker B đã được scale xuống 0.

**Đáp án:** local consumer có thể vẫn tồn tại hoặc giữ in-flight; điều kiện redistrib chưa đạt. Kiểm tra connection/session và graceful shutdown, không giảm delay mù.

### B. Vì sao không dùng chỉ log A nhận message?

Producer gửi J1..J20 **sau khi A đã mở consumer** và dùng `ON_DEMAND`.

**Đáp án:** message có thể được initial route trực tiếp tới A. Muốn chứng minh redistribution, phải quan sát J1..J20 đã pending **ở B trước khi A subscribe**.

### C. Khi muốn giữ message local lúc gửi, nhưng cho phép chuyển backlog khi worker dời node?

**Đáp án:** Xem xét mode `OFF_WITH_REDISTRIBUTION` nếu Artemis version hỗ trợ; cấu hình delay và thử hành vi. `ON_DEMAND` cho phép forwarding message mới theo remote consumer demand, không đáp ứng hoàn toàn yêu cầu “chỉ chuyển backlog cũ”.

### D. B messageCount giảm nhưng A messageCount luôn 0; đã mất message?

**Đáp án:** Chưa đủ bằng chứng. Consumer A có thể nhận/ACK nhanh khiến backlog A không tích tụ. Đối chiếu `jobId` ở log A, messages acknowledged, delivering count và DLQ/expiry.

### E. Message đã được B worker commit database nhưng chưa ACK khi process chết, chuyển tới A rồi có thể bị xử lý lại?

**Đáp án:** Có. Redistrib và redelivery không gom transaction JMS với database. Cần unique jobId/inbox và ACK sau business commit.

### F. Delay 3.000ms có bắt buộc job đến A sau đúng 3 giây kể từ khi A kết nối?

**Đáp án:** Không. Timer gắn với trạng thái không còn local consumer và còn chịu thời gian cluster topology propagation, in-flight, chuyển dữ liệu, consumer credits và tải.

### G. Cluster gồm hai broker có storage độc lập, B hỏng disk hoàn toàn; redistribution có phục hồi message từ B không?

**Đáp án:** Không. Redistrib cần B hoặc state message vẫn truy cập được. Mất disk là bài toán HA replication/shared store/backup/DR, không phải thay đổi vị trí consumer.

## 16. Checklist production trước khi bật redistribution

- [ ] Đã xác định rõ mục tiêu **chuyển backlog cũ**, không nhầm với routing message mới hoặc HA failover?
- [ ] Cả hai node có cluster topology/connector và security khỏe?
- [ ] Cluster connection bao phủ address cần chuyển, `max-hops`/routing hợp lý?
- [ ] Queue trên các node có tên, routing type và filter tương thích, được provision chủ động?
- [ ] Effective `redistribution-delay` trên node giữ backlog đã được kiểm tra, không chỉ nhìn XML?
- [ ] Mode `message-load-balancing` đúng nhu cầu và được version đang chạy hỗ trợ?
- [ ] Đã đối chiếu `consumerCount` và `deliveringCount` tại node nguồn trước khi mong chờ redistribution?
- [ ] Đã thử queue không selector/group trước; sau đó mới thử grouping/filter dùng thật?
- [ ] Có log `jobId`/`batchId` xác nhận message đã pending ở nguồn trước khi consumer đích mở?
- [ ] Đã đo thời gian tới first redistributed delivery và backlog drain time, không chỉ ping cluster port?
- [ ] Đã thử consumer churn, broker restart, cluster link down và chiều A→B?
- [ ] Có idempotency/inbox, xử lý JMS unknown commit/redelivery và DLQ?
- [ ] Có monitoring queue age, pending/delivering, cluster link status, retry, disk/network usage?
- [ ] Delay được chọn theo thời gian reconnect và SLO; không mặc định 0 ở mọi queue?
- [ ] Có rollback plan nếu cluster traffic/latency tăng sau khi bật redistribution?

## 17. Kết luận

Trong ActiveMQ Artemis cluster, **message redistribution** giải quyết tình huống **message đã nằm ở queue của broker B nhưng consumer phù hợp đã chuyển sang broker A**. B có thể chuyển backlog còn pending qua cluster khi nó không còn local consumer, A có remote consumer demand và policy cho phép. Đây là cơ chế **di chuyển message đang chờ**, không phải tự động chuyển JVM consumer, không phải HA replication và cũng không phải initial routing của message mới.

Hai tham số cần đọc cùng nhau là **`message-load-balancing`** trên cluster connection và **`redistribution-delay`** trên address settings. `ON_DEMAND` là lựa chọn phù hợp để học cơ chế, còn `OFF_WITH_REDISTRIBUTION` đáng xem xét khi muốn giảm forwarding message mới nhưng vẫn chuyển backlog stranded (nếu version hỗ trợ). Delay âm tắt, zero cho phép sớm, delay dương giúp giảm chuyển qua lại khi consumers dao động.

Cuối cùng, phải **chứng minh bằng timeline và jobId**: backlog có ở B trước khi A có consumer, B không còn local consumer, A nhận đúng job cũ và commit chúng. Khi worker có side effect, bảo vệ tính đúng đắn bằng **jobId ổn định, inbox/idempotency, transaction/ACK rõ ràng và quan sát redelivery/DLQ**. Chỉ như vậy redistribution mới nâng tính liên tục xử lý công việc mà không biến thay đổi vị trí consumer thành xử lý trùng hoặc mất kiểm soát backlog.
