# Diễn tập broker bị dừng đột ngột rồi kiểm chứng phục hồi và failover

> **Chương:** Bài tập tổng hợp  
> **Phạm vi:** Apache ActiveMQ Classic và Artemis; Java/JMS, persistent messages, transaction, broker restart recovery và HA failover. Bài thực hành dùng môi trường sandbox có data directory riêng. Các thao tác dừng cưỡng bức chỉ thực hiện trên broker thử nghiệm.

Mục tiêu của bài diễn tập là chứng minh hệ thống giữ được message đã commit khi broker bị dừng đột ngột, khôi phục được trạng thái từ persistent store, và chuyển workload sang node dự phòng khi topology HA được cấu hình đúng. Cần phân biệt hai tình huống:

- **Crash recovery:** cùng một broker/node khởi động lại và đọc lại journal/store của chính nó.
- **HA failover:** node đang phục vụ mất khả năng hoạt động; một node dự phòng được kích hoạt và client chuyển kết nối sang node đó.

Restart recovery không chứng minh failover. Hai tiến trình broker cùng tồn tại cũng không chứng minh HA. Kết quả phải được xác nhận bằng **event IDs, transaction outcomes, queue state, broker role, client reconnect và business effects**.

## 1. Kết quả cần đạt

Sau bài diễn tập, người học phải có bằng chứng cho các kết luận sau:

1. Message **persistent** đã được producer commit được khôi phục sau khi broker process bị kill đột ngột và restart với đúng data directory.
2. Message đang nằm trong một JMS transaction chưa commit không được coi là đã hoàn tất; sau mất kết nối, transaction được rollback hoặc kết quả gửi phải được phân loại là chưa rõ.
3. Consumer đã receive nhưng chưa commit/ACK có thể nhận lại message sau crash; consumer phải xử lý redelivery an toàn.
4. Trong HA pair được cấu hình và đồng bộ đúng, backup có thể tiếp quản khi live node chết; client reconnect theo cơ chế của provider.
5. Không mất message đã được xác nhận bền vững trong phạm vi failure model của lab; không kết luận exactly-once chỉ từ số lượng queue.
6. Duplicate delivery và kết quả commit không rõ được phát hiện bằng eventId/inbox, không xử lý trùng side effect.
7. Sau failover, node cũ khởi động lại theo đúng vai trò/topology, không tạo hai live owners cùng sử dụng một store hoặc cùng phục vụ một workload ngoài thiết kế.

### 1.1. Phân biệt các mốc

| Mốc | Bằng chứng | Điều chưa thể kết luận |
|---|---|---|
| Producer gọi send | Ứng dụng đã gọi API | Broker đã nhận hoặc lưu bền vững |
| Producer transaction commit trả về thành công | JMS provider xác nhận transaction gửi hoàn tất theo contract | Consumer đã nhận hoặc business effect đã commit |
| Broker restart recovery hoàn tất | Broker mở được store/journal và phục vụ | Một broker khác có thể takeover |
| Backup được HA protocol xác nhận sẵn sàng | Replica/standby đã bắt kịp theo trạng thái broker | Mọi message chưa xác nhận đều đã được bảo vệ |
| Client reconnect thành công | Client có session/connection mới hoặc được provider phục hồi | Message trước outage không bị duplicate |
| Consumer commit receive | Broker có thể hoàn tất delivery theo transaction | DB/API side effect nằm ngoài transaction đã commit |
| Business outcome được đối soát | Domain record có trạng thái terminal theo eventId | Mọi message trong mọi queue đều đúng |

## 2. Crash recovery khác HA failover

~~~mermaid
flowchart TD
    subgraph Recovery["Crash recovery: một node"]
      A["Broker A live"] --> K["Process bị kill"]
      K --> S["A restart với cùng persistent store"]
      S --> R["Journal/store recovery"]
      R --> A2["A phục vụ lại"]
    end
    subgraph Failover["HA failover: hai node"]
      L["Live A"] -->|Replication hoặc shared store| B["Backup B"]
      L --> X["A mất đột ngột"]
      X --> P["B được promote/activate"]
      P --> C["Client reconnect/failover"]
    end
~~~

**Crash recovery** trả lời: “Broker A có thể phục hồi dữ liệu của nó sau khi process chết không?”  
**HA failover** trả lời: “Khi A không còn phục vụ, B có thể tiếp quản dữ liệu/dịch vụ và client có thể tiếp tục không?”

Một **network of brokers** chỉ forward message theo topology/demand; nó không mặc nhiên là HA replication. Hai brokers với hai KahaDB riêng và cùng tên queue không phải một cặp active/standby. Không được thử failover bằng cách cho hai broker mở chung một thư mục store nếu cơ chế HA của sản phẩm không hỗ trợ đúng mô hình đó.

### 2.1. Các failure model phải ghi rõ

| Failure | Crash recovery | HA failover |
|---|---|---|
| JVM bị kill, disk còn nguyên | Restart cùng node/store | Backup có thể takeover nếu HA đã đồng bộ |
| Host mất, volume vẫn truy cập được | Khởi động lại host/node | Shared-store backup có thể lấy lock và activate |
| Disk/store hỏng hoàn toàn | Không thể tự phục hồi từ cùng store | Replicated backup có thể giúp nếu bản sao còn nhất quán và đủ mới |
| Network partition giữa live và backup | Node có thể vẫn sống nhưng mất liên lạc | Cần quorum/lock/HA protocol để tránh split brain |
| Client mất kết nối ngắn | Reconnect/retry tùy client | Failover URI/topology có thể chuyển sang backup |
| Consumer chết sau DB commit, trước JMS ACK | Broker redelivery | Failover có thể redeliver; inbox/idempotency vẫn cần |

**Không tuyên bố RPO = 0** chỉ vì backup đã khởi động. Phải biết message nào được producer commit, backup đã nhận replication/lock state nào, và protocol có xác nhận đồng bộ trước khi trả kết quả hay không.

## 3. Thiết kế môi trường sandbox

Tạo một lab độc lập với hai tầng:

- **Track A — single broker:** một Classic hoặc Artemis broker, persistent storage riêng; diễn tập kill/restart để kiểm tra crash recovery.
- **Track B — HA pair:** một cặp Classic shared-store master/slave hoặc Artemis shared-store primary/backup; diễn tập live-node failure và client failover. Artemis replication là biến thể nâng cao khi đã có coordination/quorum hoặc lock manager phù hợp.

Không dùng production data, credentials hoặc shared storage đang phục vụ workload thật.

### 3.1. Sơ đồ các thành phần

~~~mermaid
flowchart LR
    P["Producer test"] --> CF["Failover-aware JMS client"]
    CF --> A["Live broker A<br/>persistent store"]
    A <-->|HA replication<br/>hoặc shared-store lock| B["Backup broker B<br/>standby"]
    A --> Q["Durable queue<br/>LAB.RECOVERY"]
    B -. "Tiếp quản khi A fail" .-> Q
    Q --> C["Transacted consumer"]
    C --> DB["Test outcome ledger"]
~~~

Sơ đồ logic trên có hai dạng HA khác nhau:

- **Artemis shared-store:** primary và backup dùng chung các data directories; backup lấy lock và load store khi primary mất.
- **Artemis replication:** live broker sao chép journal/state sang backup qua replication channel; backup chỉ được activate theo cơ chế coordination/quorum/lock manager đã cấu hình.
- **Classic shared-store master/slave:** master và slave dùng chung persistent store được hỗ trợ; chỉ node giữ được lock hợp lệ trở thành master. Đây không phải hai bản sao KahaDB độc lập.

### 3.2. Chuẩn bị và cô lập

- Java runtime và client library phù hợp với broker version.
- Một queue test tên **LAB.RECOVERY** được provision sẵn.
- Persistent store nằm trên volume/data directory riêng của lab.
- HA pair có node IDs, connector/listener ports và credentials riêng.
- Một client có thể reconnect theo đúng provider HA transport.
- Một file log hoặc database test ghi eventId, JMSMessageID, thời điểm send/receive/commit và broker endpoint.
- Đồng hồ các máy được đồng bộ; ghi thời điểm theo UTC để đối chiếu broker/client logs.
- Đặt giới hạn message count/size và dung lượng disk; dừng producer khi vượt ngưỡng lab.

**Không dùng queue production để kiểm tra.** Consumer test sẽ ACK message khi commit; browse bằng consumer có thể làm thay đổi trạng thái queue. Dùng management browse/QueueBrowser read-only khi cần xem mà không consume.

### 3.3. Bộ event test có thể đối soát

Mỗi message mang ID duy nhất, ví dụ:

~~~text
recovery-run = run-2026-11-17-A
eventId = run-2026-11-17-A-000001
eventId = run-2026-11-17-A-000002
...
eventId = run-2026-11-17-A-001000
~~~

Không chỉ đếm 1.000 message. Sau mỗi kịch bản, so sánh **tập eventId đã commit ở producer** với tập eventId được consumer commit; phân loại missing, duplicate, pending, expired và DLQ. Dùng cùng eventId khi retry cùng một thao tác logic.

## 4. Chuẩn bị broker và persistent queue

### 4.1. ActiveMQ Classic

Với Classic, xác nhận broker bật persistence và dùng KahaDB hoặc persistence adapter được hỗ trợ. Ví dụ fragment trong activemq.xml:

~~~xml
<broker xmlns="http://activemq.apache.org/schema/core"
        brokerName="recovery-classic"
        persistent="true">

    <persistenceAdapter>
        <kahaDB directory="data/kahadb"/>
    </persistenceAdapter>

    <transportConnectors>
        <transportConnector name="openwire"
                            uri="tcp://0.0.0.0:61616"/>
    </transportConnectors>
</broker>
~~~

Đây là fragment minh họa cấu hình broker; giữ các plugin, policy, system usage và connector khác đang cần trong lab. Không cho hai broker process độc lập cùng mở một KahaDB directory. Với shared-store master/slave, hai node phải được cấu hình theo cơ chế lock/HA của Classic và cùng truy cập **một shared store được hỗ trợ**.

### 4.2. ActiveMQ Artemis

Artemis lưu journal/paging data theo thư mục cấu hình của từng broker. Đảm bảo data directory của live và backup đúng với HA policy, và queue test có routing/queue definition phù hợp. Một queue anycast có thể được khai báo trong broker.xml:

~~~xml
<addresses>
    <address name="LAB.RECOVERY">
        <anycast>
            <queue name="LAB.RECOVERY"/>
        </anycast>
    </address>
</addresses>
~~~

Đây là fragment addresses đặt bên trong phần tử cấu hình core của broker.xml. Với queue test, bảo đảm message được gửi tới đúng address và queue. **PERSISTENT delivery mode** ở producer và durable queue/address là hai điều kiện khác nhau: queue phải tồn tại theo cấu hình, message phải được gửi persistent để broker lưu theo policy.

### 4.3. Không nhầm persistent message với mọi loại message

| Loại | Kỳ vọng sau broker restart |
|---|---|
| Persistent message đã commit vào durable queue | Được khôi phục theo persistence store và broker guarantee |
| Non-persistent message | Không được dựa vào để phục hồi sau crash |
| Message trong transaction gửi chưa commit | Chưa phải message đã được chấp nhận hoàn tất; transaction có thể rollback |
| Message đã ACK/commit consume | Không mong message xuất hiện lại như pending |
| Message trong non-durable topic subscription | Không có bảo đảm giữ khi subscriber offline |
| Message trong durable subscription | Phụ thuộc durable subscription, persistence và subscription state |

**Không dùng queue depth một mình để xác nhận**: queue có thể rỗng vì message đã được consumer ACK, hết hạn, chuyển DLQ hoặc được route sang destination khác.

## 5. Ứng dụng Java/JMS tạo và kiểm tra message

Ví dụ sau dùng Jakarta JMS API, phù hợp với Artemis client Jakarta và các client Classic có hỗ trợ Jakarta. Nếu triển khai Classic client thế hệ javax.jms, thay namespace/import và dependency đồng bộ; không trộn javax.jms với jakarta.jms trong cùng ứng dụng.

### 5.1. Producer transacted, persistent

~~~java
package com.example.recovery;

import jakarta.jms.Connection;
import jakarta.jms.ConnectionFactory;
import jakarta.jms.DeliveryMode;
import jakarta.jms.MessageProducer;
import jakarta.jms.Queue;
import jakarta.jms.Session;
import jakarta.jms.TextMessage;

public final class RecoveryProducer {
    private RecoveryProducer() {}

    public static void sendBatch(
            ConnectionFactory factory,
            String runId,
            int count) throws Exception {

        try (Connection connection = factory.createConnection()) {
            Session session = connection.createSession(
                true, Session.SESSION_TRANSACTED);

            try {
                Queue queue = session.createQueue("LAB.RECOVERY");
                MessageProducer producer = session.createProducer(queue);
                try {
                    producer.setDeliveryMode(DeliveryMode.PERSISTENT);

                    for (int i = 1; i <= count; i++) {
                        String eventId = "%s-%06d".formatted(runId, i);
                        TextMessage message = session.createTextMessage(
                            "{\"runId\":\"" + runId
                            + "\",\"sequence\":" + i + "}");

                        message.setStringProperty("eventId", eventId);
                        message.setStringProperty("runId", runId);

                        producer.send(message);
                        System.out.printf(
                            "SENT eventId=%s jmsMessageId=%s%n",
                            eventId, message.getJMSMessageID());
                    }

                    // Chỉ sau commit mới ghi nhận batch là committed.
                    session.commit();
                    System.out.printf(
                        "PRODUCER_COMMIT runId=%s count=%d%n",
                        runId, count);
                } catch (Exception failure) {
                    session.rollback();
                    throw failure;
                } finally {
                    producer.close();
                }
            } finally {
                session.close();
            }
        }
    }
}
~~~

**Ghi chú:** chương trình tạo một transaction cho cả batch. Nếu gửi 1.000 message rồi commit, batch là đơn vị commit. Với batch lớn, cân nhắc commit theo nhóm nhỏ và ghi manifest các eventId đã commit; nếu một batch bị timeout ở commit, kết quả có thể không rõ với producer và cần đối soát/retry cùng eventId.

Trong ví dụ, JMSMessageID được log để hỗ trợ điều tra; **eventId** mới là khóa logic để so sánh qua retry/replay. Không tạo eventId mới khi chỉ đang retry một batch chưa rõ kết quả.

### 5.2. Consumer transacted, log redelivery

~~~java
package com.example.recovery;

import jakarta.jms.Connection;
import jakarta.jms.ConnectionFactory;
import jakarta.jms.JMSException;
import jakarta.jms.Message;
import jakarta.jms.MessageConsumer;
import jakarta.jms.Queue;
import jakarta.jms.Session;
import jakarta.jms.TextMessage;

public final class RecoveryConsumer {
    private RecoveryConsumer() {}

    public static void consumeOne(
            ConnectionFactory factory,
            boolean failBeforeCommit) throws Exception {

        try (Connection connection = factory.createConnection()) {
            Session session = connection.createSession(
                true, Session.SESSION_TRANSACTED);
            try {
                Queue queue = session.createQueue("LAB.RECOVERY");
                MessageConsumer consumer = session.createConsumer(queue);
                try {
                    connection.start();
                    Message message = consumer.receive(10_000L);

                    if (message == null) {
                        System.out.println("NO_MESSAGE");
                        session.rollback();
                        return;
                    }

                    String eventId = message.propertyExists("eventId")
                        ? message.getStringProperty("eventId")
                        : "MISSING_EVENT_ID";

                    int deliveryCount = readDeliveryCount(message);

                    System.out.printf(
                        "RECEIVED eventId=%s messageId=%s " +
                        "redelivered=%s deliveryCount=%d%n",
                        eventId,
                        message.getJMSMessageID(),
                        message.getJMSRedelivered(),
                        deliveryCount
                    );

                    if (failBeforeCommit) {
                        // Chỉ dùng trong lab để mô phỏng xử lý chưa commit.
                        session.rollback();
                        System.out.println("ROLLED_BACK_BEFORE_COMMIT");
                        return;
                    }

                    if (message instanceof TextMessage text) {
                        System.out.println("BODY=" + text.getText());
                    }

                    // Lab này chưa gọi DB; commit xác nhận receive.
                    session.commit();
                    System.out.println("CONSUMER_COMMIT eventId=" + eventId);
                } finally {
                    consumer.close();
                }
            } finally {
                session.close();
            }
        }
    }

    private static int readDeliveryCount(Message message)
            throws JMSException {
        if (message.propertyExists("JMSXDeliveryCount")) {
            return message.getIntProperty("JMSXDeliveryCount");
        }
        return -1; // Provider không expose JMSXDeliveryCount.
    }
}
~~~

Ví dụ rollback chủ động thay cho crash consumer; khi cần kiểm tra process death thật, dừng consumer process ngay sau log RECEIVED nhưng trước session.commit(). Giá trị deliveryCount = -1 nghĩa là provider không expose JMSXDeliveryCount; dùng JMSRedelivered và log broker để quan sát redelivery, không suy ra số lần chính xác. Khi kết nối đóng bất thường, broker sẽ giải quyết transaction chưa commit theo semantics của provider. Delivery count/header có thể khác nhau giữa Classic và Artemis; so sánh bằng eventId và log thực tế.

### 5.3. Factory kết nối phải do provider cấu hình

Hai provider có cách tạo factory và HA client khác nhau. Đặt ConnectionFactory trong cấu hình ứng dụng theo profile; không dùng một URI failover của Classic cho Artemis.

- **Classic:** client OpenWire dùng ActiveMQConnectionFactory; HA shared-store có thể dùng Failover Transport URI liệt kê endpoint master/slave.
- **Artemis:** dùng ActiveMQConnectionFactory của Artemis JMS client; HA client phải bật hỗ trợ HA và nhận topology/backup connector theo cấu hình broker. Static failover URI và HA discovery cần được chọn theo phiên bản/cấu trúc mạng.

Các phần sau dùng tên biến connectionFactory để giữ code JMS trung lập. Bài lab cần xác nhận factory đang kết nối đúng broker, không chỉ xác nhận constructor không ném exception.


## 6. Track A — broker đơn lẻ bị kill rồi restart

Kịch bản này xác minh **journal recovery trên cùng một node**. Không cần HA pair; phải giữ nguyên persistent store qua lần restart.

### 6.1. Gửi và xác nhận batch trước khi crash

1. Start broker sandbox và chờ listener mở, store recovery hoàn tất.
2. Xác nhận queue LAB.RECOVERY tồn tại và queue depth bằng 0.
3. Chạy RecoveryProducer gửi 1.000 message với runId duy nhất.
4. Chờ log PRODUCER_COMMIT; lưu manifest 1.000 eventId đã commit.
5. Dùng management browse hoặc queue metrics xác nhận 1.000 message pending.
6. Chưa start consumer; nếu consumer đã nhận/ACK, không còn đủ bằng chứng để test khôi phục backlog.

| Trường | Giá trị mẫu |
|---|---:|
| Broker identity | recovery-a |
| Queue | LAB.RECOVERY |
| Producer committed events | 1.000 |
| Queue pending | 1.000 |
| Consumer committed | 0 |
| Persistent store free space | Ghi số đo thực |
| Thời điểm commit cuối | UTC timestamp |

### 6.2. Dừng broker process đột ngột

Chỉ dùng trong sandbox, sau khi chắc chắn đúng PID/container:

~~~bash
# Linux: xác định đúng PID của broker lab trước khi chạy
kill -KILL <broker-pid>
~~~

~~~powershell
# Windows PowerShell: xác định đúng PID của tiến trình broker lab
Stop-Process -Id <broker-pid> -Force
~~~

~~~bash
# Docker: chỉ áp dụng khi broker lab chạy trong container riêng
docker kill --signal=KILL <broker-container>
~~~

Không dùng lệnh trên môi trường production. Không xóa journal, lock file, paging directory hoặc data directory sau crash. Không chạy một broker process thứ hai với cùng store trong khi process cũ chưa chắc đã dừng hoàn toàn.

Ghi nhận thời điểm process chết, client disconnect, broker log cuối cùng và tình trạng volume. **SIGKILL không cho broker chạy shutdown hook**; đây là chủ ý của bài test để buộc broker phục hồi từ persistent store.

### 6.3. Restart cùng node và cùng store

1. Start lại đúng broker instance với đúng broker configuration.
2. Kiểm tra process mở đúng persistent data directory đã dùng trước crash.
3. Theo dõi log recovery/journal replay và lỗi store lock, corrupt record hoặc I/O.
4. Chờ transport connector mở và broker báo trạng thái phục vụ.
5. Kiểm tra queue LAB.RECOVERY bằng management metrics/browse.
6. Đối chiếu pending message count với manifest producer.

**PASS:** tất cả eventId đã commit trước crash vẫn có thể được browse/consume; không có lỗi journal recovery và broker sử dụng đúng data directory.

**FAIL:** queue rỗng bất thường, broker tạo data directory mới, journal không mở được, hoặc eventId bị thiếu. Trước khi sửa, dừng broker và bảo toàn bản sao store/log phục vụ điều tra.

### 6.4. Consumer nhận message rồi broker chết trước commit

Kịch bản này kiểm tra transaction receive đang mở:

1. Gửi một message test riêng có eventId crash-inflight-001.
2. Chạy RecoveryConsumer và đặt breakpoint/pause **sau log RECEIVED nhưng trước session.commit()**.
3. Xác nhận message đã được dispatch/in-flight; chưa có log CONSUMER_COMMIT.
4. Kill broker process bằng SIGKILL trong lúc consumer còn giữ session transaction.
5. Restart broker với cùng persistent store.
6. Khởi động lại consumer và nhận message có cùng eventId.
7. Commit receive và xác nhận chỉ có một terminal outcome trong ledger.

Để tạo pause dễ tái hiện, đặt breakpoint ngay trước lệnh commit trong IDE hoặc thêm một latch/sleep chỉ trong test build. Không thêm sleep vô hạn vào listener production.

Message có thể được redeliver vì transaction receive chưa commit. Header JMSRedelivered/JMSXDeliveryCount giúp quan sát nhưng không phải bằng chứng duy nhất; eventId và transaction log mới là khóa đối soát.

### 6.5. Producer send nhưng chưa commit khi broker crash

1. Dùng một session transacted mới.
2. Gửi batch nhỏ với eventId thuộc run riêng.
3. Tạm dừng producer sau send nhưng trước session.commit().
4. Kill broker trong khi transaction vẫn mở; dừng producer process trong lab để nó không reconnect rồi tiếp tục session cũ.
5. Khởi động lại broker và tạo producer session mới.
6. Kiểm tra các eventId thuộc batch chưa commit không được tính là accepted/committed.
7. Nếu producer không biết commit trước crash có hoàn tất hay không, phân loại kết quả là **UNKNOWN** và đối soát theo eventId trước khi retry.

Không đưa một batch chưa commit vào manifest committed. Một timeout ngay tại lệnh commit cũng không cho phép producer kết luận chắc chắn transaction thất bại; retry cùng eventId và consumer idempotency bảo vệ cửa sổ kết quả không rõ.


## 7. Track B1 — ActiveMQ Classic shared-file-system master/slave

Classic có mô hình **Shared File System Master Slave**: nhiều broker process dùng chung một persistent store trên shared filesystem; process lấy được exclusive lock trở thành master và mở transport connectors. Các slave chờ lock. Khi master chết và lock được giải phóng, một slave lấy lock rồi trở thành master.

Đây là **shared storage**, không phải replication giữa hai KahaDB local độc lập. Hệ thống lưu trữ phải hỗ trợ exclusive file locks đúng cách; không chọn một NFS mount bất kỳ rồi mặc định lock semantics an toàn.

### 7.1. Hai node dùng chung KahaDB store

Ví dụ persistence fragment trong cấu hình của cả hai node:

~~~xml
<persistenceAdapter>
    <kahaDB directory="/shared/activemq/recovery-ha/kahadb"/>
</persistenceAdapter>
~~~

- Node A và node B cùng trỏ đến **một shared path** trên storage hỗ trợ lock.
- Mỗi node có transport connector phù hợp với hostname/port mà client có thể truy cập, ví dụ A:61616 và B:61617.
- Cấu hình broker/persistence phải tương thích; chỉ master giữ lock và phục vụ client.
- Nếu dùng scheduler, audit hoặc data directory ngoài KahaDB, cấu hình các dữ liệu cần thiết theo hướng dẫn HA của Classic.
- Không để hai process cùng lúc ghi store; không copy KahaDB đang hoạt động để dựng standby.

Với shared filesystem, kiểm tra lock behavior khi client/server/storage mất đột ngột. Một số filesystem/NFS version có thể giữ stale lock lâu hoặc không đáp ứng semantics cần thiết; failover sẽ không hoạt động nếu slave không lấy được lock. Thử nghiệm với đúng loại volume sẽ dùng trong production.

### 7.2. Client failover URI của Classic

Dùng ActiveMQ Classic Failover Transport để client thử master trước, sau đó slave:

~~~text
failover:(tcp://classic-a:61616,tcp://classic-b:61617)?randomize=false&initialReconnectDelay=1000&maxReconnectAttempts=-1
~~~

- **randomize=false:** giữ thứ tự URI, thử primary trước.
- **initialReconnectDelay=1000:** bắt đầu reconnect sau 1 giây; cần tune theo SLO và startup time.
- **maxReconnectAttempts=-1:** tiếp tục reconnect không giới hạn sau khi đã kết nối thành công; cần timeout/alert ở tầng ứng dụng để request không treo vô hạn.

Không dùng Failover Transport để thay HA store. URI chỉ giúp client tìm broker đang active; shared lock/master-slave mới quyết định node nào được quyền mở service.

### 7.3. Diễn tập failover Classic

1. Start node A và B cùng shared store; chờ A giữ lock, B ở trạng thái slave/waiting.
2. Kết nối producer/consumer qua failover URI, không hardcode chỉ một node.
3. Gửi một batch persistent, transacted; chờ producer commit trả về.
4. Xác minh A là master, queue pending đúng số lượng và B đang standby.
5. Kill process A.
6. Quan sát B lấy exclusive lock, load store và mở transport connector.
7. Quan sát client failover reconnect sang B; ghi thời gian từ A chết đến lần send/receive thành công đầu tiên.
8. Đối chiếu eventId đã commit, message pending, redelivery và business outcomes.
9. Khởi động lại A; xác nhận A tham gia lại với vai trò slave, không giành quyền ghi khi B vẫn giữ lock.
10. Thực hiện failback theo quy trình được hỗ trợ; không kill node đang active tùy tiện để ép đổi vai trò.

**PASS:** chỉ một master active tại một thời điểm; B phục vụ sau khi A chết; client reconnect; persistent messages đã commit được giữ và không có business effect trùng.

### 7.4. Những giới hạn phải ghi vào biên bản

- Shared filesystem là dependency HA trọng yếu; lock không đáng tin thì không có failover an toàn.
- Một network of brokers/store-and-forward không thay master/slave.
- Shared store bảo vệ broker process/host failure khi volume còn nguyên; nó không bảo vệ trước việc volume bị xóa/hỏng.
- Nếu client không dùng failover transport, broker có thể đã phục hồi nhưng ứng dụng vẫn không tự kết nối lại.
- Client send đang in-flight khi failover có thể có kết quả không rõ; retry cần eventId ổn định và idempotency.


## 8. Track B2 — ActiveMQ Artemis shared-store HA pair

Artemis hỗ trợ HA bằng **shared store** hoặc **replication**. Bài lab này chọn shared store để diễn tập primary/backup rõ ràng: hai node dùng chung toàn bộ data directories; backup lấy journal lock sau khi primary thất bại rồi load store và nhận kết nối.

Shared store bao gồm **journal, paging, large messages và bindings journal**, không chỉ một thư mục journal. Hai broker phải cấu hình cùng shared locations. Storage phải bảo đảm locking và I/O semantics phù hợp; không cho hai broker active ghi cùng data directories.

### 8.1. HA policy trên primary và backup

Fragment trong broker.xml của primary:

~~~xml
<ha-policy>
    <shared-store>
        <primary/>
    </shared-store>
</ha-policy>
~~~

Fragment trong broker.xml của backup:

~~~xml
<ha-policy>
    <shared-store>
        <backup>
            <allow-failback>true</allow-failback>
        </backup>
    </shared-store>
</ha-policy>
~~~

Các node cần cluster configuration và connectors/acceptors đúng để nhận biết topology. Ví dụ minh họa hai connector và cluster connection:

~~~xml
<connectors>
    <connector name="node-0">tcp://artemis-a:61616</connector>
    <connector name="node-1">tcp://artemis-b:61617</connector>
</connectors>

<cluster-connections>
    <cluster-connection name="ha-cluster">
        <connector-ref>node-0</connector-ref>
        <static-connectors>
            <connector-ref>node-1</connector-ref>
        </static-connectors>
    </cluster-connection>
</cluster-connections>
~~~

Trên backup, connector-ref phải đại diện endpoint của backup; static connector phải trỏ tới peer tương ứng. Cấu hình acceptor, connector name, cluster connection, credentials và shared directories phải nhất quán với topology thực tế. Đây là các fragment, không phải broker.xml độc lập hoàn chỉnh.

### 8.2. Artemis client URL có HA topology

Artemis Core client có thể nhận topology primary/backup từ cluster. URL minh họa với hai named connectors:

~~~text
(tcp://artemis-a:61616?name=node-0,tcp://artemis-b:61617?name=node-1)?ha=true&reconnectAttempts=-1
~~~

Tên trong URL phải khớp connector names được broker announce qua cluster connection. Với JMS client, cấu hình Artemis JMS ConnectionFactory bằng URL HA này theo version client đang dùng. Không thay bằng Classic Failover Transport URI.

### 8.3. Diễn tập failover Artemis

1. Start primary và backup với cùng shared storage, cấu hình HA policy đúng.
2. Xác nhận primary active; backup passive và không nhận application traffic.
3. Đợi backup hoàn tất startup/cluster discovery; xác nhận trạng thái standby.
4. Kết nối producer/consumer bằng Artemis HA URL.
5. Gửi batch persistent và commit; ghi eventId/producer transaction.
6. Kill primary process trong lúc queue còn pending.
7. Chờ backup lấy lock, load shared store và chuyển sang active.
8. Quan sát JMS client reconnect, session/consumer phục hồi và transaction in-flight được xử lý theo semantics Artemis.
9. Đối soát pending, redelivery, DLQ, eventId và business outcome.
10. Khởi động lại primary cũ; xác nhận nó không mở cùng store khi backup đang active.
11. Kiểm tra failback theo allow-failback policy; ghi nhận lần chuyển vai trò thứ hai và thời gian gián đoạn.

**PASS:** backup chỉ active sau khi primary mất lock/được xác định fail; client reconnect được; persistent messages đã lưu được khôi phục; không có hai node cùng active trên shared store.

### 8.4. Artemis replication không giống shared store

Với **replication**, primary và backup dùng **data directories riêng** và đồng bộ dữ liệu qua mạng. Backup phải hoàn tất initial synchronization trước khi đủ điều kiện thay primary. Cấu hình replication cơ bản chỉ định primary/backup và group-name phù hợp, nhưng **không nên giả định backup tự promote chỉ vì mất kết nối**.

Trong Artemis hiện hành, replication failover cần cơ chế phối hợp phù hợp như **quorum voting hoặc pluggable lock manager** để xử lý quyền active và split brain. Nếu dùng quorum voting, cấu hình check-for-active-server/failback đúng; nếu dùng lock manager, cấu hình coordination service theo hướng dẫn của version. Diễn tập replication là bài nâng cao riêng: phải test mất primary, network partition, quorum/lock manager outage, failback và trạng thái journal mới nhất.

Không trộn shared-store fragment với replication fragment. Không đặt hai replication brokers dùng chung journal directory. Nếu lab chỉ có hai node và chưa có coordination/quorum đã được thiết kế, hãy thực hành shared-store HA trước; không bật replication đơn giản rồi tuyên bố failover an toàn.


## 9. Client failover và transaction đang mở

Broker backup có thể active nhưng client vẫn thất bại nếu factory không biết topology, DNS/ports sai, reconnect budget quá ngắn hoặc ứng dụng không xử lý transaction rollback sau failover.

### 9.1. Classic Failover Transport

Classic client sử dụng Failover Transport để thử các endpoint trong danh sách. Ví dụ đã dùng ở mục 7.2 ưu tiên node A trước node B. Client tự reconnect khi transport bị đứt, nhưng không có nghĩa mọi operation đang in-flight đã hoàn tất.

Khi failover xảy ra trong lúc send/commit:

- Producer có thể nhận exception hoặc timeout dù broker đã xử lý commit trước khi connection đứt.
- Consumer có thể nhận lại message chưa ACK/commit.
- Session transaction có thể phải rollback và được ứng dụng thực hiện lại.
- Nếu ứng dụng retry bằng eventId mới, cùng một nghiệp vụ có thể tạo hai message logic khác nhau.

Với Classic, bật các tùy chọn client như message tracking chỉ khi đã hiểu semantics, memory footprint và giới hạn của phiên bản. Bài lab phải có **application-level eventId/idempotency** để xử lý kết quả không rõ; không xem reconnect thành bằng chứng operation trước đã thành công hoặc thất bại.

### 9.2. Artemis HA client

Artemis Core/JMS client có thể nhận topology primary/backup và reconnect sang backup khi failover. Broker tạo lại session/consumer state cần thiết, nhưng không tái tạo toàn bộ trạng thái server của mọi operation in-flight. Message send/ack chưa được ghi bền vững có thể không có ở backup.

Với transacted session, nếu failover xảy ra sau khi session đã gửi/ack message trong transaction hiện tại, client có thể bị đánh dấu rollback-only; lệnh commit sau đó có thể ném TransactionRolledBackException. Ứng dụng phải xử lý rollback/retry theo API và version đang dùng.

**Đặc biệt:** nếu failover xảy ra ngay trong lệnh commit, client có thể không biết commit đã được xử lý trước khi node chết hay chưa. Đây là kết quả UNKNOWN. Dùng eventId ổn định, transaction retry và duplicate detection/inbox ở tầng ứng dụng để bảo vệ side effect.

### 9.3. Ghi nhận connection failure

Có thể gắn JMS ExceptionListener để log mất kết nối/failover. Đây là ví dụ quan sát, không thay logic retry:

~~~java
import jakarta.jms.Connection;
import jakarta.jms.JMSException;

connection.setExceptionListener((JMSException error) -> {
    System.err.printf(
        "JMS_CONNECTION_EXCEPTION errorCode=%s message=%s%n",
        error.getErrorCode(),
        error.getMessage()
    );
});
~~~

Đặt listener ngay sau khi tạo connection và trước khi start workload. Với provider-specific failover, kiểm tra error code/exception details để phân biệt reconnect thành công với trạng thái disconnected. Không log credentials hoặc payload nhạy cảm.

### 9.4. Retry transaction an toàn

Khi commit trả về lỗi trong cửa sổ failover:

1. Đánh dấu transaction attempt là UNKNOWN/ROLLBACK_REQUIRED theo exception semantics.
2. Không tạo eventId mới cho cùng một thao tác logic.
3. Tạo session/transaction mới theo hướng dẫn của provider nếu session cũ không còn dùng được.
4. Retry cùng batch/event IDs với producer idempotency hoặc broker duplicate detection phù hợp.
5. Consumer dùng inbox/unique constraint để không lặp business effect.
6. Đối soát producer accepted IDs, broker state và consumer terminal outcomes.

Không tự động retry mọi exception vô hạn. Phân loại lỗi transient, auth/configuration và permanent; áp dụng backoff và giới hạn thời gian theo SLO.

## 10. Đo RTO, RPO và kết quả message

Một diễn tập chỉ có giá trị khi có timeline và tập IDs để đối chiếu. Đừng chỉ ghi “broker lên lại sau vài giây”.

### 10.1. Các timestamp cần ghi

| Mốc | Timestamp | Nguồn |
|---|---|---|
| Producer commit cuối trước sự cố | T0 | Producer log/manifest |
| Broker process chết | T1 | Process supervisor/container runtime |
| Client phát hiện disconnect | T2 | JMS ExceptionListener/client log |
| Backup bắt đầu active | T3 | Broker HA log/management |
| Client reconnect thành công | T4 | Client log |
| Send/receive đầu tiên sau failover | T5 | Producer/consumer log |
| Queue backlog về baseline | T6 | Broker metrics |
| Business outcomes đối soát xong | T7 | Database/domain ledger |

Các phép đo:

~~~text
Failure detection time = T3 - T1
Client reconnect time   = T4 - T2
Service interruption    = T5 - T1
Backlog drain time      = T6 - T5
Business recovery time  = T7 - T1
~~~

Đây là số đo của lần chạy lab, không phải guarantee của broker. Chạy nhiều lần dưới tải và với cùng topology để có phân bố p50/p95/p99.

### 10.2. Định nghĩa RPO trong bài lab

Từ manifest các eventId mà producer đã ghi nhận commit thành công trước T1:

~~~text
committed_before_failure = tập eventId producer commit trước crash
recovered_after_failover = tập eventId browse/consume được sau recovery
missing = committed_before_failure - recovered_after_failover
~~~

**RPO message loss count = số eventId missing** trong tập đã được xác nhận commit, sau khi loại trừ expiry, DLQ, routing khác và consumer đã ACK trước đó.

Nếu có message commit response không rõ, tách chúng thành nhóm UNKNOWN; không đưa vào nhóm confirmed committed. Với HA replication, kết quả còn phụ thuộc replication/coordination policy và thời điểm backup sync. Với shared store, volume và lock correctness là điều kiện cốt lõi.

### 10.3. Đếm duplicate và business effect

~~~text
delivery_attempts(eventId) = số lần consumer nhận eventId
business_commits(eventId)  = số lần domain effect được commit
~~~

Kỳ vọng cho một command idempotent:

- delivery_attempts có thể lớn hơn 1 sau rollback/failover.
- business_commits phải bằng 1 cho eventId đã xử lý thành công.
- eventId chưa được xử lý có thể còn pending, hoặc ở DLQ/expired theo policy.
- Không dùng riêng JMSMessageID để đối chiếu producer retry vì mỗi send attempt có thể tạo message ID khác.

Nếu test chỉ có JMS consumer commit mà không có database ledger, ghi rõ kết quả chỉ xác nhận broker receive transaction, chưa chứng minh external side effect.

## 11. Ma trận diễn tập và tiêu chí PASS/FAIL

Chạy mỗi kịch bản ít nhất ba lần trong sandbox; giữa các lần dùng runId/eventId khác nhau và reset queue theo quy trình có kiểm soát.

| Kịch bản | Tác động | Kết quả mong đợi | Điều kiện FAIL |
|---|---|---|---|
| Restart graceful | Stop broker bình thường rồi start lại | Store mở lại, queue state nhất quán | Persistent committed IDs bị mất |
| SIGKILL single broker | Kill process, restart cùng store | Journal recovery, message đã commit còn | Store mới được tạo hoặc committed IDs thiếu |
| Crash khi consumer in-flight | Kill broker sau receive, trước JMS commit | Message được redeliver | Message biến mất dù chưa commit/ACK |
| Crash khi producer transaction mở | Kill broker trước commit | Transaction chưa commit không được tính accepted | Producer đánh dấu batch chưa commit là committed |
| Classic shared-store failover | Kill master A | Slave B lấy lock, client reconnect | Hai master cùng active hoặc B không lấy lock |
| Artemis shared-store failover | Kill primary A | Backup B activate, client reconnect | Backup không active hoặc store không load |
| Client reconnect timeout | Rút network ngắn | Client retry trong budget cấu hình | Client bỏ cuộc trước khi backup sẵn sàng |
| Failback | Khởi động lại node cũ | Node cũ tham gia đúng role, không split brain | Node cũ ghi cùng store khi node mới còn active |
| Redelivery/duplicate | Crash trong transaction | Duplicate được nhận diện theo eventId | Business side effect chạy hai lần |
| Storage pressure | Giảm dung lượng sandbox có kiểm soát | Broker báo pressure, không làm hỏng store | Xóa store/lock thủ công hoặc corruption |

### 11.1. PASS về phục hồi

- Broker restart từ đúng data directory và hoàn tất journal/store recovery.
- Queue/address và message metadata cần thiết còn nguyên.
- Event IDs đã commit được tìm thấy hoặc có trạng thái giải thích được (đã ACK, DLQ, expiry).
- Không có corruption hoặc hai process cùng ghi store.
- Broker mở listener và management endpoint theo đúng vai trò.

### 11.2. PASS về failover

- Backup chuyển từ passive/standby sang active theo HA policy.
- Chỉ một node có quyền phục vụ và sở hữu store theo thiết kế.
- Client tự reconnect hoặc ứng dụng thực hiện reconnect theo contract.
- Producer/consumer tiếp tục trong thời gian gián đoạn được đo.
- Không mất message đã xác nhận bền vững trong failure model được kiểm thử.
- Duplicate deliveries không tạo duplicate business effects.

### 11.3. FAIL dù broker đã báo started

Bài lab vẫn FAIL nếu broker start thành công nhưng:

- Dùng nhầm data directory trống.
- Queue test tồn tại nhưng committed eventIds trước crash không còn.
- Client chỉ kết nối được node cũ, không failover sang backup.
- Backup active nhưng producer/consumer không thể reconnect.
- In-flight transaction bị xử lý sai hoặc business side effect trùng.
- Primary cũ restart và tạo hai node active trên cùng shared store.
- Chỉ số DLQ/expiry tăng nhưng không được giải thích.
 

## 12. Tạo ConnectionFactory đúng cho từng provider

Code producer/consumer ở mục 5 nhận JMS ConnectionFactory qua tham số. Ứng dụng cần tạo factory theo provider và client API namespace đang triển khai.

### 12.1. ActiveMQ Classic

~~~java
import jakarta.jms.ConnectionFactory;
import org.apache.activemq.ActiveMQConnectionFactory;

String brokerUrl =
    "failover:(tcp://classic-a:61616,tcp://classic-b:61617)"
    + "?randomize=false&initialReconnectDelay=1000"
    + "&maxReconnectAttempts=-1";

ConnectionFactory connectionFactory =
    new ActiveMQConnectionFactory(brokerUrl);
~~~

Đoạn import jakarta.jms chỉ dùng với Classic client release hỗ trợ Jakarta. Nếu dùng Classic client javax.jms, đổi import ConnectionFactory sang javax.jms và dùng dependency tương ứng. URI failover phải trỏ đến các node thuộc cùng HA logical broker; không liệt kê hai brokers độc lập với KahaDB riêng rồi kỳ vọng message state được chia sẻ.

### 12.2. ActiveMQ Artemis

~~~java
import jakarta.jms.ConnectionFactory;
import org.apache.activemq.artemis.jms.client.ActiveMQConnectionFactory;

String brokerUrl =
    "(tcp://artemis-a:61616?name=node-0,"
    + "tcp://artemis-b:61617?name=node-1)"
    + "?ha=true&reconnectAttempts=-1";

ConnectionFactory connectionFactory =
    new ActiveMQConnectionFactory(brokerUrl);
~~~

Tên connector trong URL phải khớp connector topology được broker announce. Artifact JMS client phải tương thích namespace Jakarta/Java version của ứng dụng. Nếu dùng Artemis client phiên bản khác, kiểm tra constructor, failover options và connector topology theo tài liệu đúng release.

Artemis hiện cung cấp client riêng cho JMS 2.0 (namespace javax.jms) và Jakarta Messaging 3.x (namespace jakarta.jms), ví dụ artifact artemis-jms-client và artemis-jakarta-client. Chọn đúng một artifact/API family; không đưa cả hai namespace vào cùng module chỉ để thử một URL.

**Không dùng cùng URL cho Classic và Artemis.** Classic dùng Failover Transport scheme; Artemis dùng HA topology/client connector configuration. Hai provider có transaction/failover exception semantics riêng.

## 13. Runbook khi diễn tập không đạt

### 13.1. Broker restart nhưng queue trống

1. Dừng broker; xác nhận không có process khác đang mở store.
2. Đối chiếu đường dẫn data directory trong cấu hình trước và sau crash.
3. Kiểm tra quyền filesystem, volume mount, journal files và startup logs.
4. Kiểm tra queue có bị consumer ACK, expiry, DLQ routing hoặc purge trước crash không.
5. So sánh eventId manifest với producer commit log; phân loại batch UNKNOWN riêng.
6. Không tạo store mới hoặc xóa journal để ép broker start trước khi bảo toàn dữ liệu.
7. Nếu store corruption, giữ bản sao read-only và chuyển sang quy trình restore/incident phù hợp.

### 13.2. Backup không activate

- Xác nhận đúng HA policy và broker role; process sống không có nghĩa backup đã sẵn sàng.
- Với Classic shared filesystem, kiểm tra exclusive lock, stale lock, filesystem semantics và quyền truy cập shared volume.
- Với Artemis shared store, kiểm tra primary đã nhả lock, backup dùng đúng toàn bộ shared directories và cluster connection đã nhận biết peer.
- Với Artemis replication, kiểm tra backup đã initial-sync và coordination/quorum/lock manager được cấu hình; backup replication không tự promote chỉ vì không còn thấy primary.
- Kiểm tra network partition, firewall, DNS, connector names, cluster credentials và port.
- Không start thêm một node với store đang bị active broker giữ.

### 13.3. Backup active nhưng client không reconnect

1. Kiểm tra client URI/factory có chứa endpoint backup/topology đúng.
2. Kiểm tra DNS/ports/TLS truststore và broker connector được announce.
3. Kiểm tra reconnectAttempts/startup retry budget và thời gian timeout ứng dụng.
4. Xem JMS ExceptionListener, transport logs và exception code.
5. Xác nhận client namespace/dependency tương thích broker.
6. Chạy một producer/consumer test mới qua cùng factory sau khi kết nối lại.

### 13.4. Message được giao lại hoặc duplicate sau failover

- Dùng eventId để gom delivery attempts.
- Xác định producer commit response có UNKNOWN không.
- Xác định consumer đã DB commit trước khi JMS ACK hay chưa.
- Kiểm tra inbox/unique constraint và downstream idempotency key.
- Không purge message hoặc reset delivery counter để làm dashboard về 0.
- Replay cùng eventId nếu vẫn là cùng nghiệp vụ; dùng eventId mới chỉ cho một command/event mới.

### 13.5. Failback không đúng vai trò

Đợi active backup ổn định và xác nhận client traffic đã phục hồi trước khi khởi động node cũ. Đọc log role/lock/synchronization. Với Artemis replication, node primary cũ phải đồng bộ lại journal và thực hiện failback theo policy; không cho nó active độc lập trên dữ liệu cũ. Với Classic shared store, node cũ chỉ được trở lại sau khi lock được giải phóng đúng quy trình. Không ép failback bằng cách kill node đang phục vụ.

## 14. Các bài diễn tập mở rộng

### Lab C — Failover khi producer đang gửi liên tục

1. Chạy producer gửi batch nhỏ liên tục, mỗi eventId ổn định.
2. Ghi nhận batch commit trước khi failover và batch có kết quả UNKNOWN.
3. Kill live broker trong lúc producer đang chạy.
4. Quan sát client exception/reconnect và thời gian send đầu tiên thành công.
5. Đối soát missing/duplicate eventIds; retry các event UNKNOWN bằng cùng IDs.
6. Xác minh consumer inbox hoặc ledger chỉ ghi một business effect cho mỗi eventId.

**Đạt:** phân biệt throughput interruption, commit uncertainty và message loss thực sự.

### Lab D — Failover khi consumer đang có in-flight message

1. Start transacted consumer với concurrency nhỏ để dễ quan sát.
2. Dừng ở breakpoint sau receive nhưng trước commit.
3. Kill live broker.
4. Chờ backup active và client reconnect.
5. Xác minh message được redeliver hoặc transaction rollback theo provider semantics.
6. Commit lần nhận lại và đối chiếu eventId/business effect.

**Đạt:** không mất message chưa ACK và không tạo side effect trùng.

### Lab E — Network partition giữa live và backup

Chỉ thực hiện trong sandbox có khả năng khôi phục network:

1. Bắt đầu từ HA pair healthy, backup đã sẵn sàng.
2. Chặn network replication/cluster/lock traffic theo cách có kiểm soát.
3. Quan sát role, health và broker logs ở cả hai node.
4. Không gửi thêm traffic nghiệp vụ nếu topology chưa chứng minh được fencing/quorum.
5. Khôi phục network và xác minh chỉ một node active.
6. Đối soát eventId trước khi tiếp tục producer.

**Đạt:** giải thích được split brain risk và vai trò của shared lock/quorum/lock manager. Không cố tình partition filesystem production.

### Lab F — Failback và khôi phục node cũ

1. Sau khi backup đã tiếp quản và client hoạt động, giữ workload test ở mức thấp.
2. Start node cũ với cùng config và store/topology đúng.
3. Quan sát node cũ join làm passive/backup hoặc bắt đầu synchronization.
4. Chờ failback policy thực hiện chuyển vai trò nếu được cấu hình.
5. Ghi thời gian failback và số lần client reconnect.
6. Xác nhận node active duy nhất, queue state và eventId ledger nhất quán.

**Đạt:** khôi phục topology HA hoàn chỉnh, không chỉ đưa một broker process lên lại.

## 15. Checklist trước khi kết thúc diễn tập

- [ ] Chỉ chạy kill/restart/failover trên sandbox và xác định đúng PID/container.
- [ ] Ghi rõ broker product/version, HA policy, client version và persistence adapter.
- [ ] Queue test được provision sẵn; producer gửi persistent messages và commit trước khi crash.
- [ ] Manifest eventId phân biệt committed, unknown, pending, consumed, expired và DLQ.
- [ ] Single-node restart dùng lại đúng persistent store.
- [ ] Consumer in-flight test dừng trước commit và xác minh redelivery.
- [ ] Classic shared-store master/slave dùng shared filesystem có exclusive lock được hỗ trợ.
- [ ] Artemis shared-store primary/backup dùng chung journal, paging, large messages và bindings directories.
- [ ] Artemis replication có coordination/quorum/lock manager; không giả định backup tự promote.
- [ ] Client factory dùng đúng provider failover URI/topology, credentials và TLS.
- [ ] Đo T1–T7, RTO, missing committed IDs, duplicate deliveries và business outcomes.
- [ ] Có test producer commit UNKNOWN, consumer transaction rollback và downstream idempotency.
- [ ] Chỉ một node active/owner của store tại mọi thời điểm.
- [ ] Node cũ restart/failback theo HA policy, không giành quyền ghi ngoài thiết kế.
- [ ] Có runbook cho store recovery, backup activation, client reconnect, duplicate và failback.
- [ ] Không xóa DLQ/journal/lock hoặc reset counters trước khi bảo toàn bằng chứng.

**Kết luận:** Diễn tập broker bị dừng đột ngột phải kiểm tra hai năng lực độc lập: **crash recovery** phục hồi store của cùng node và **HA failover** chuyển dịch vụ sang backup đã được chuẩn bị đúng. ActiveMQ Classic shared-file-system master/slave dựa vào shared filesystem lock; Artemis shared-store dùng primary/backup cùng data directories, còn replication cần đồng bộ và cơ chế phối hợp activation. Persistent send phải được commit, client phải reconnect đúng topology, transaction in-flight có thể rollback hoặc có kết quả UNKNOWN, và consumer phải idempotent theo eventId. Chỉ coi diễn tập PASS khi có manifest, timeline, queue/broker evidence và business outcomes đối soát được.

## Tài liệu kỹ thuật tham khảo

- [ActiveMQ Classic — Shared File System Master Slave](https://activemq.apache.org/components/classic/documentation/shared-file-system-master-slave)
- [ActiveMQ Classic — Failover Transport Reference](https://activemq.apache.org/components/classic/documentation/failover-transport-reference)
- [ActiveMQ Artemis — High Availability and Failover](https://artemis.apache.org/components/artemis/documentation/latest/ha.html)
