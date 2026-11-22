# Phân biệt tính bền vững, khả năng sẵn sàng và khả năng phục hồi

> **Chương:** Độ tin cậy  
> **Phạm vi:** Apache ActiveMQ Classic và ActiveMQ Artemis trong giao tiếp bất đồng bộ bằng JMS. Bài này tập trung phân biệt **durability**, **availability** và **recoverability**, đo được bằng kịch bản lỗi, RPO/RTO, persistence, HA, backup/restore và kiểm chứng Java. Ba mục tiêu bổ sung cho nhau, không phải ba tên gọi của cùng một cơ chế.

## 1. Ba câu hỏi khác nhau về một thông điệp

Order Service gửi lệnh `InvoiceRequested(eventId=E-1001)` vào JMS queue `billing.commands`. Producer dùng message `PERSISTENT`, transaction JMS và nhận phản hồi commit thành công. Ngay sau đó máy chứa broker gặp sự cố.

Có ba câu hỏi độc lập:

1. **Tính bền vững (*durability*):** Message đã được xác nhận có còn tồn tại sau lỗi/restart thuộc phạm vi bảo đảm không?
2. **Khả năng sẵn sàng (*availability*):** Khi một node hỏng, producer/consumer có tiếp tục gửi, nhận trong thời gian chấp nhận được không?
3. **Khả năng phục hồi (*recoverability*):** Nếu process, volume hoặc cả cụm hỏng, có thể phục hồi trạng thái và dịch vụ bằng quy trình nào, mất bao lâu và tối đa mất bao nhiêu dữ liệu?

| Thuộc tính | Thứ cần bảo vệ | Câu hỏi kiểm chứng | Công cụ chính |
|---|---|---|---|
| **Durability** | Message/transaction được broker chấp nhận và vẫn còn trách nhiệm giao | “Sau broker crash, message pending còn không?” | JMS `PERSISTENT`, journal/KahaDB, commit, đồng bộ storage, replication phù hợp |
| **Availability** | Khả năng gửi/nhận của ứng dụng trong thời gian chạy | “Node lỗi, client tiếp tục hoạt động sau bao lâu?” | Primary/backup HA, failover, reconnect, capacity, health check |
| **Recoverability** | Đưa dịch vụ **và dữ liệu** về trạng thái nhất quán sau lỗi lớn | “Volume bị mất thì khôi phục từ đâu, RPO/RTO thực tế bao nhiêu?” | Backup nhất quán, restore, replay, DR rehearsal, runbook |

Hệ thống có thể **bền nhưng không sẵn sàng**, **sẵn sàng cao mà vẫn mất dữ liệu**, hoặc **có backup nhưng không thể phục hồi trong thời gian yêu cầu**.

~~~mermaid
flowchart LR
    P["Java Producer"] -->|send/commit| B["Broker active"]
    B --> S[("Persistent Store")]
    B -. "HA failover" .-> BK["Broker backup"]
    S -. "Backup / restore" .-> DR["Bản sao phục hồi"]
    B -->|deliver / ACK| C["Java Consumer"]
    C --> DB[("Business DB")]
~~~

**Điểm phân biệt đầu-cuối:** JMS consumer ACK không có nghĩa hóa đơn đã được commit trong database; JMS local transaction không tự làm nguyên tử giao dịch giữa broker và database bên ngoài.

## 2. Durability: bền đối với dữ liệu gì và lỗi nào?

Để kỳ vọng một message vẫn có thể nhận sau broker restart, cần xác định **trạng thái message**, **ràng buộc lưu trữ** và **loại sự cố**.

### 2.1. Ranh giới của message được xác nhận

Một luồng gửi thường có các mốc:

~~~text
Producer tạo M1
  -> setDeliveryMode(PERSISTENT)
  -> send(M1) trong transacted Session
  -> session.commit() thành công
  -> Broker chịu trách nhiệm giao message
  -> Crash, restart trên đúng persistent store
  -> M1 còn pending nếu chưa ACK/expire/purge
~~~

Ở session transacted, `send()` trả về chưa đủ để khẳng định transaction gửi đã hoàn tất. **`commit()` là ranh giới**. Nếu phản hồi commit mất giữa đường, producer không biết kết quả đã commit hay chưa: đó là *ambiguous outcome*, cần retry cùng `eventId` và consumer idempotent.

Nếu message bị ACK bởi consumer, hết TTL, bị purge hoặc xóa queue/durable subscription, việc nó không còn pending **không phải bằng chứng lỗi durability**.

### 2.2. PERSISTENT không phải “không thể mất trong mọi hoàn cảnh”

JMS `DeliveryMode.PERSISTENT` yêu cầu provider xử lý message với semantics lưu bền. Nó không khiến ổ đĩa trở nên bất hoại.

| Sự cố | Persistent store có thể bảo vệ? | Giới hạn cần xác minh |
|---|---|---|
| Broker process crash, volume còn nguyên | Đây là mục tiêu cốt lõi | Journal hợp lệ; commit hoàn tất; message còn pending |
| Restart sạch | Thông thường còn message persistent | Không xóa store; không expire/ACK trước đó |
| Mất điện, disk vẫn nguyên | Có thể | Journal sync, OS cache, controller, filesystem, phần cứng |
| Volume bị xóa/hỏng vật lý | Không nếu chỉ có một bản | Cần replica, backup hoặc replay ngoài volume đó |
| Mất cả site | Không nếu dữ liệu chỉ ở site đó | Cần DR theo fault domain độc lập |
| Consumer đã ACK M1 | M1 không còn nghĩa vụ giao bình thường | ACK không phải sao lưu dữ liệu lịch sử |
| Producer gửi NON_PERSISTENT | Không được đòi cùng bảo đảm | Một lần restart sạch còn thấy message không tạo ra hợp đồng bền |

**Durability luôn gắn với *failure model*.** “Còn sau restart process” không đồng nghĩa “còn khi cả disk, node, vùng dữ liệu bị phá hủy”.

### 2.3. Persistent message khác durable topic subscription

- `PERSISTENT`: delivery mode **của message**.
- **Durable subscription**: danh tính đăng ký nhận **của subscriber** vẫn tồn tại khi consumer offline.

Một sự kiện persistent trên topic phát **trước khi subscriber đăng ký** không tự được phát lại cho subscriber mới. Một durable subscription đã tạo trước vẫn chịu TTL, chính sách expiry, quyền xóa, storage và HA.

Cần kiểm tra cả **message đã commit** lẫn **destination/subscription đang thực sự giữ backlog**, không chỉ nhìn producer bật `PERSISTENT`.

## 3. Availability: dữ liệu còn nhưng dịch vụ có thể ngừng

Một broker đơn có persistent KahaDB: crash lúc 10:01, admin restart lúc 10:12 bằng cùng volume, client reconnect lúc 10:13. Message vẫn còn nhưng từ 10:01 đến 10:13 producer/consumer có thể không phục vụ được.

~~~text
Durability:    PASS  (M1 vẫn còn sau restart)
Availability: OUTAGE (client ngừng gửi/nhận trong khoảng sự cố)
Recoverability: kiểm chứng được restart process, chưa kiểm chứng mất volume
~~~

**“Port 61616 mở” không phải tiêu chí availability đầy đủ.** Broker có thể nhận TCP nhưng producer bị flow control, store đầy, quyền ACL từ chối, queue/address sai, hoặc consumer lag vượt deadline. Đo availability bằng khả năng **send/receive/commit hoàn tất** theo SLO nghiệp vụ.

### 3.1. HA giảm gián đoạn; không bảo đảm không mất message

Trong topology primary/backup, một lần failover gồm:

1. Phát hiện primary lỗi.
2. Kiểm tra backup đủ điều kiện active và quyền sở hữu storage/replica.
3. Đảm bảo **không có hai primary** chấp nhận ghi cùng lúc.
4. Backup phục vụ queue/destination với state phù hợp.
5. Client JMS reconnect hoặc failover.
6. Consumer khôi phục session và xử lý message chưa ACK.
7. Kiểm tra producer commit nào đã được xác nhận hay còn *unknown*.

HA tốt cần cả cơ chế **fencing/quorum** chống split brain và cách client tìm lại endpoint. Hai broker cùng chạy mà có hai store độc lập **không mặc nhiên** bảo đảm một message gửi vào broker A đã bền ở broker B.

### 3.2. RTO availability phải đo tới ứng dụng

Nếu backup khởi động lúc `T+5s` nhưng JMS client hoàn thành send lần đầu lúc `T+45s`, metric “failover time” hữu ích cho ứng dụng là **45 giây**, không chỉ 5 giây. Với luồng Billing, phải quan sát cả consumer resume và thời gian drain backlog.

Chỉ đo process startup sẽ bỏ qua timeout transport, reconnect, xác thực/TLS, tạo consumer và giao dịch bị rollback.

## 4. Recoverability: khôi phục được khi HA không còn giúp

Recoverability xử lý các tình huống như **volume bị xóa, corruption, mất site, cấu hình bị phá hỏng hoặc xóa queue nhầm**. Những lỗi này có thể làm cả primary lẫn backup không còn trạng thái hợp lệ.

Một kế hoạch thực sự có thể phục hồi gồm:

- Bản backup **nhất quán** của dữ liệu và cấu hình cần thiết.
- Bản sao ở fault domain phù hợp, không chỉ trên cùng volume đang cần bảo vệ.
- Quy trình restore tương thích broker version, journal/store format, quyền/secret.
- Cách đối soát message pending, durable subscription, DLQ/expiry và transaction không rõ kết quả.
- Replay từ transactional outbox hoặc event log khi bản backup thiếu message.
- Idempotent consumer để không thực hiện lại nghiệp vụ sau restore/replay.
- Thử restore định kỳ với thời gian và kết quả thực tế.

### 4.1. RPO và RTO khác nhau

**RPO (Recovery Point Objective):** mức mất dữ liệu tối đa được chấp nhận. Có thể tính theo khoảng thời gian giữa dữ liệu mới nhất có thể phục hồi và thời điểm lỗi, hoặc kiểm kê message/transaction mất.

**RTO (Recovery Time Objective):** thời gian tối đa cho phép để dịch vụ phục hồi chức năng ở mức đã định.

Ví dụ một disaster xảy ra 12:00, backup nhất quán cuối lúc 11:55, hệ thống phục vụ trở lại 12:20:

~~~text
11:55             12:00                     12:20
  |-----------------|-------------------------|
backup            disaster                   restored
  ^                  ^                          ^
  |                  |                          |
tập dữ liệu tới     RPO có thể tới             RTO khoảng
11:55 được giữ      5 phút, nếu không replay  20 phút
~~~

Các số trên chỉ minh họa. Replay từ outbox có thể khôi phục một phần sự kiện sau 11:55, nhưng cần kiểm tra event đã được consumer xử lý trước sự cố để tránh side effect trùng.

**Mục tiêu RPO=0 cho mọi message đã xác nhận** cần bằng chứng về đồng bộ commit/replication, storage và fault model, không tự có vì cấu hình được đặt tên “HA”.

### 4.2. Một bảng phân loại thiết kế

| Thiết kế | Điểm mạnh | Vùng chưa được giải quyết |
|---|---|---|
| Một broker + persistent store | Có thể sống qua restart process | Outage tới khi restart; mất volume có thể mất dữ liệu |
| Broker đơn + backup định kỳ | Có thể restore khi disk hỏng | RPO phụ thuộc lịch backup, RTO phụ thuộc tốc độ restore |
| HA + shared store | Backup có thể tiếp quản state chung | Shared store là một fault domain, cần locking/fencing |
| HA + replicated store | Dữ liệu được sao chép theo chính sách HA | Phải kiểm tra sync, quorum và message đã ACK ở thời điểm lỗi |
| HA + backup độc lập + DR rehearsal | Có cả failover lẫn đường phục hồi thảm họa | Vẫn phải đo RPO/RTO và xử lý duplicate/replay |
| Outbox + inbox/idempotency | Tăng khả năng phục hồi sự kiện **nghiệp vụ** | Không thay thế capacity, HA hay backup broker |

## 5. Ma trận lỗi: tính chất nào được kiểm chứng?

Giả định các message đang xét đã commit ở producer và chưa ACK/expire, trừ trường hợp ghi rõ khác.

| Sự cố | Durability | Availability | Recovery |
|---|---|---|---|
| Consumer offline 10 phút, queue còn | Message persistent có thể tiếp tục chờ | Broker có thể vẫn online; nghiệp vụ xử lý chậm | Restart consumer, drain backlog |
| Broker restart sạch với cùng disk | Có thể PASS | Gián đoạn khi restart | Khởi động và kiểm kê queue |
| Process crash, disk nguyên | Journal có thể replay | Broker đơn ngừng phục vụ | Restart hoặc HA takeover |
| Volume bị phá hỏng | Store đơn không bảo vệ dữ liệu | Primary ngừng phục vụ | Replica/backup/replay |
| Primary mất, backup HA hoạt động | Tùy state sync | Có thể tiếp tục sau failover | Đối soát transaction *unknown* |
| Network partition thiếu fencing | Rủi ro phân kỳ/split brain | Có thể “up” sai lầm | Chặn ghi trùng, đối soát hai phía |
| Producer timeout giữa commit | Kết quả không xác định | Client gián đoạn | Retry cùng eventId và deduplication |
| Consumer DB commit rồi crash trước ACK | Message có thể còn để redeliver | Consumer reconnect được | Inbox chống side effect trùng |
| Message hết TTL | Có thể bị loại hợp lệ | Broker vẫn phục vụ | Xem expiry policy; replay chỉ khi nghiệp vụ cho phép |
| Xóa nhầm durable subscription | Pending messages có thể mất | Broker khác vẫn hoạt động | Restore hoặc replay nếu có dữ liệu |

Không được xem message biến mất do ACK, TTL, purge là cùng loại lỗi với mất volume. Nêu đúng **nguyên nhân và phạm vi bảo đảm** mới đo durability có ý nghĩa.

## 6. Classic: persistent KahaDB và giới hạn HA

ActiveMQ Classic thường sử dụng KahaDB. Trong `conf/activemq.xml`, broker có thể khai báo:

~~~xml
<!-- Thuộc tính trên phần tử <broker> của Classic:
     persistent="true"
     deleteAllMessagesOnStartup="false" -->

<!-- Thành phần nằm bên trong <broker> -->
<persistenceAdapter>
  <kahaDB directory="data/kahadb"/>
</persistenceAdapter>
~~~

Đây là **fragment**, không phải toàn bộ XML chạy độc lập. `data/kahadb` phải đặt trên volume bền; khi container bị xóa/recreate, không được mất data directory. Đừng bật startup option xóa toàn bộ backlog khi đang thử durability.

Ba điểm cùng cần:

1. Broker được cấu hình persistence và persistent store đúng.
2. Producer dùng `DeliveryMode.PERSISTENT`.
3. Nếu send thuộc transacted session, `session.commit()` được xác nhận.

### 6.1. Đừng nhầm network of brokers với HA state replication

Classic có network connectors để chuyển tiếp message giữa broker; **network of brokers không tự bảo đảm** broker B có đầy đủ trạng thái queue đã commit ở A. Những mô hình active/standby Classic khác có thể dùng shared persistence/locking theo version và hạ tầng.

Khi review HA Classic, yêu cầu chứng minh:

- Chỉ một broker được active với một shared store tại một thời điểm.
- Volume và file lock/fencing xử lý đúng khi host/network lỗi.
- Client kết nối lại được với địa chỉ mới.
- Message đã commit trước lỗi còn tồn tại trên broker sau failover.
- Transaction đang in-flight/commit response mất được xử lý theo mô hình unknown outcome.

**Không sao chép `ha-policy` của Artemis vào `activemq.xml` Classic**. Hai broker có schema và cơ chế HA khác nhau.

### 6.2. Backup KahaDB

Không coi việc copy thư mục KahaDB **đang được ghi liên tục** như một backup nhất quán nếu không có quy trình snapshot/backup được hỗ trợ. Cần biết trạng thái journal/index, quiesce hoặc cơ chế snapshot an toàn, và thử restore trên **một instance riêng**. Backup “thành công” chưa chứng minh dữ liệu mở lại được.

## 7. Artemis: journal, paging và lựa chọn HA

ActiveMQ Artemis dùng journal và các thư mục dữ liệu tương ứng. Ví dụ **một số phần tử trong `<core>`** của `etc/broker.xml`:

~~~xml
<persistence-enabled>true</persistence-enabled>
<journal-type>NIO</journal-type>

<bindings-directory>data/bindings</bindings-directory>
<journal-directory>data/journal</journal-directory>
<paging-directory>data/paging</paging-directory>
<large-messages-directory>data/large-messages</large-messages-directory>

<journal-sync-transactional>true</journal-sync-transactional>
<journal-sync-non-transactional>true</journal-sync-non-transactional>
~~~

Đây là fragment minh họa, phải ghép theo **schema và thứ tự phần tử** của bản Artemis đang chạy.

- `persistence-enabled` và journal quyết định đường lưu trữ bền của broker.
- `journal-sync-*` liên quan đồng bộ journal ở các loại transaction tương ứng; kết quả còn phụ thuộc OS, disk/controller và phiên bản.
- Journal, bindings, paging và large messages có quan hệ tới trạng thái broker; khi backup phải hiểu **tập dữ liệu cần giữ nhất quán**, không chỉ copy mỗi journal.
- `NON_PERSISTENT` không tự trở thành persistent chỉ vì bật `persistence-enabled`.

### 7.1. Replication và shared-store là hai lựa chọn có điểm lỗi riêng

**Replication:** broker primary sao chép state cho backup theo HA policy. Phải hỏi backup đã đồng bộ đến đâu, có quorum/fencing không, điều kiện promote là gì, xác nhận commit nào được bảo vệ trước khi primary mất. **Không khẳng định RPO=0 chỉ vì có backup đang online.**

**Shared store:** primary và backup dùng state storage chung, chỉ một active được sở hữu store. Giảm nhu cầu sao chép message giữa hai nơi nhưng **volume chung là single fault domain**: hỏng volume có thể khiến cả hai broker mất khả năng hoạt động.

Tên role/element trong `<ha-policy>` thay đổi theo đời Artemis (tài liệu mới có primary/backup, tài liệu cũ có master/slave). Đừng lấy đoạn XML HA rời rạc của một version làm bằng chứng production đã có quorum, cluster connection và failover an toàn.

### 7.2. Client reconnect không giải quyết transaction outcome không rõ

~~~text
Producer -> send() + commit()
Broker   -> đã commit và lưu message
Network  -> phản hồi commit thất lạc
Client   -> reconnect sang backup
Producer -> không thể biết chắc lần trước đã commit hay chưa
~~~

Khi retry mà dùng một event ID mới, consumer có thể tạo hóa đơn trùng. Giữ `eventId` ổn định ở outbox và dùng inbox/idempotency tại consumer. Artemis có duplicate detection qua `_AMQ_DUPL_ID` như lớp giảm duplicate nếu cache còn ID, **không thay thế** business deduplication.

## 8. Java JMS: kiểm chứng durability sau restart

Ví dụ sử dụng **Classic 5.x + `javax.jms`** và `org.apache.activemq:activemq-client` phiên bản phù hợp. Broker lab tại `tcp://localhost:61616` và queue `lab.reliability.pending`; tài khoản `app/lab-secret` là giá trị minh họa, cần quyền send/consume. Nếu chuyển sang Artemis Jakarta JMS, thay client/import và chuẩn bị address/queue phù hợp.

### 8.1. Producer PERSISTENT có transaction

~~~java
import javax.jms.Connection;
import javax.jms.DeliveryMode;
import javax.jms.MessageProducer;
import javax.jms.Queue;
import javax.jms.Session;
import javax.jms.TextMessage;
import org.apache.activemq.ActiveMQConnectionFactory;

public final class ReliabilityProducer {
    public static void main(String[] args) throws Exception {
        if (args.length != 1 || args[0].trim().isEmpty()) {
            throw new IllegalArgumentException("Usage: ReliabilityProducer <eventId>");
        }
        String eventId = args[0];
        ActiveMQConnectionFactory factory =
                new ActiveMQConnectionFactory("tcp://localhost:61616");
        Connection connection =
                factory.createConnection("app", "lab-secret");
        try {
            Session session = connection.createSession(
                    true, Session.SESSION_TRANSACTED);
            try {
                Queue queue = session.createQueue("lab.reliability.pending");
                MessageProducer producer = session.createProducer(queue);
                try {
                    producer.setDeliveryMode(DeliveryMode.PERSISTENT);
                    TextMessage message = session.createTextMessage(
                            "eventId=" + eventId);
                    message.setStringProperty("eventId", eventId);
                    message.setJMSType("durability.probe.v1");

                    try {
                        producer.send(message);
                        session.commit();
                        System.out.println("COMMIT_CONFIRMED " + eventId
                                + " jmsId=" + message.getJMSMessageID());
                    } catch (Exception failure) {
                        // Nếu commit response mất, outcome có thể unknown.
                        try {
                            session.rollback();
                        } catch (Exception rollbackFailure) {
                            failure.addSuppressed(rollbackFailure);
                        }
                        throw failure;
                    }
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

**Ranh giới:** `COMMIT_CONFIRMED` mới chứng minh caller đã quan sát được kết quả commit thành công theo JMS. Nếu `commit()` ném lỗi, gọi rollback phía client **không chứng minh** broker chưa commit. `Connection.start()` không cần thiết cho producer-only.

### 8.2. Consumer transacted để kiểm tra backlog sau restart

~~~java
import javax.jms.Connection;
import javax.jms.Message;
import javax.jms.MessageConsumer;
import javax.jms.Queue;
import javax.jms.Session;
import org.apache.activemq.ActiveMQConnectionFactory;

public final class ReliabilityConsumer {
    public static void main(String[] args) throws Exception {
        ActiveMQConnectionFactory factory =
                new ActiveMQConnectionFactory("tcp://localhost:61616");
        Connection connection =
                factory.createConnection("app", "lab-secret");
        try {
            Session session = connection.createSession(
                    true, Session.SESSION_TRANSACTED);
            try {
                Queue queue = session.createQueue("lab.reliability.pending");
                MessageConsumer consumer = session.createConsumer(queue);
                try {
                    connection.start();
                    Message message = consumer.receive(10_000L);
                    if (message == null) {
                        System.out.println("NO_MESSAGE_WITHIN_TIMEOUT");
                        return;
                    }
                    String eventId = message.getStringProperty("eventId");
                    System.out.println("RECEIVED eventId=" + eventId
                            + " id=" + message.getJMSMessageID()
                            + " redelivered=" + message.getJMSRedelivered());

                    if (eventId == null || eventId.isEmpty()) {
                        session.rollback();
                        throw new IllegalStateException("Missing eventId");
                    }
                    // Lab chỉ xác minh message; không có database nghiệp vụ.
                    session.commit();
                    System.out.println("CONSUME_COMMITTED " + eventId);
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

Trong session transacted, `session.commit()` xác nhận consume trong **JMS transaction**. Nếu consumer còn ghi database, nó cần transaction DB và idempotency riêng: JMS transaction local không tự gom SQL transaction.

### 8.3. Thực hiện ba phép thử khác nhau

**A. Durability — process restart**

1. Dùng broker lab có persistence, đúng persistent volume, queue rỗng.
2. Chạy `ReliabilityProducer E-RESTART-001`; ghi dòng `COMMIT_CONFIRMED`.
3. **Không khởi động consumer** trước khi dừng broker.
4. Restart broker dùng lại **cùng store**, không bật tùy chọn xóa dữ liệu.
5. Chạy `ReliabilityConsumer`, so event ID nhận được với ID đã gửi.

Kết quả là bằng chứng cho durability **qua kịch bản restart được thử**, chưa phải bằng chứng sống qua mất disk/site.

**B. Availability — broker offline**

1. Gọi thử send/receive khi broker đang tắt.
2. Đo lúc bắt đầu lỗi, lúc broker phục vụ lại và thời điểm API JMS hoàn tất thành công lần đầu.
3. Dù thử A PASS, vẫn có thể ghi nhận outage dài: đó là rủi ro availability.

**C. Recoverability — restore từ backup trong lab cô lập**

1. Tạo bản backup nhất quán bằng cơ chế được phiên bản broker hỗ trợ, ghi mốc thời gian và tập event ID.
2. Gửi thêm message sau backup và ghi trạng thái commit.
3. Mô phỏng volume mất trên **bản sao môi trường lab**, tuyệt đối không xóa volume dùng chung/production.
4. Restore rồi kiểm tra queue/subscriptions, message pending, lỗi journal, event ID cần replay.
5. Đo RPO/RTO thực tế và thử consume an toàn sau restore.

Thử `NON_PERSISTENT` riêng để đối chứng. Nếu nó có mặt sau một lần restart sạch, đó **không phải** bảo đảm tương đương PERSISTENT.

## 9. End-to-end reliability: nơi broker không thể cứu ứng dụng

Có hai khoảng trống quan trọng hơn bản thân việc broker restart thành công.

### 9.1. Database nguồn commit nhưng producer chưa kịp gửi

~~~text
Order DB COMMIT
-> process Order Service chết trước JMS send
-> broker không có event để giữ hay replay
~~~

Broker có HA hoàn hảo cũng không biết event chưa từng gửi. Dùng **transactional outbox** để commit **đơn hàng + row outbox** trong cùng DB transaction, rồi dispatcher publish với event ID ổn định và retry khi outcome mơ hồ.

### 9.2. Consumer DB commit nhưng JMS ACK chưa tới broker

~~~text
Billing DB COMMIT invoice
-> consumer chết trước JMS ACK / session.commit()
-> message có thể redeliver sau failover/restart
-> nguy cơ tạo hóa đơn lần hai
~~~

Dùng **idempotent inbox/unique event ID**. Ghi inbox và business side effect trong cùng DB transaction; sau DB commit mới ACK/commit JMS. Nếu ACK mất, consumer nhận lại thấy inbox row và bỏ qua side effect trùng.

| Điểm commit | Trạng thái được bảo đảm | Trường hợp response mất |
|---|---|---|
| Commit Order DB + outbox | Ý định publish được giữ trong DB nguồn | Cần đối soát DB transaction |
| Commit JMS send | Broker nhận trách nhiệm message theo provider | Có thể unknown; retry cùng eventId |
| Commit Billing DB rồi ACK JMS | Business state và trạng thái messaging riêng nhau | Có thể redelivery; inbox chống trùng |

Không một JMS local transaction nào tự bao phủ cả hai DB và broker. XA là bài toán hạ tầng khác có chi phí và failure model riêng; outbox/inbox thường phù hợp hơn khi hệ thống không dùng transaction phân tán.

## 10. SLO riêng cho durability, availability và recovery

Đừng dùng một chỉ số “broker uptime” cho cả ba thuộc tính.

| Chỉ số | Cách đo đúng | Sai lầm cần tránh |
|---|---|---|
| Durability test | Message **đã commit và còn pending** có thể nhận sau lỗi đã định nghĩa | Đếm message đã ACK/expire như mất dữ liệu |
| Availability SLI | Tỷ lệ send/receive đáp ứng deadline và điều kiện nghiệp vụ | Chỉ kiểm tra TCP port |
| Failover time | Từ lúc primary lỗi đến **first successful client transaction** trên node đang active | Chỉ lấy lúc backup process start |
| RPO | Message/transaction đã xác nhận nhưng không thể phục hồi theo failure model | Dùng riêng timestamp backup mà không kiểm tra dữ liệu thực |
| RTO | Từ khi outage bắt đầu tới khi gửi/nhận và nghiệp vụ hoạt động lại | Bỏ qua reconnect, reprocessing, backlog |
| Recovery correctness | Đối soát event ID, pending, DLQ, durable subscription, side effect | Chỉ kiểm tra broker đã khởi động |
| Drain time | Thời gian xử lý backlog sau failover/restore | Tuyên bố phục hồi trong khi queue lag tăng |

Một hệ thống Billing có thể đặt các mục tiêu **minh họa**:

- Process crash đơn: mọi message persistent đã commit và còn pending phục hồi từ store hợp lệ.
- Failover node: first successful publish/consume trong 2 phút.
- Mất cả volume: RPO tối đa 5 phút cho dữ liệu không thể replay; RTO 30 phút.
- Không tạo hai invoice cho cùng event ID, kể cả khi replay/HA redelivery.

Các mục tiêu này cần **thử nghiệm**; chúng không phải cam kết mặc định của Classic hoặc Artemis.

## 11. Runbook phục hồi đáng tin cậy

1. **Phân loại lỗi:** process, host, storage, network partition, site loss, cấu hình hay quyền.
2. **Ngăn split brain:** xác định primary hiện tại; kiểm tra fencing/quorum trước khi promote hoặc khởi động lại.
3. **Giữ bằng chứng:** log, journal, snapshot, trạng thái replication, event ID và timestamp; không xóa data store tùy tiện.
4. **Khôi phục dịch vụ:** failover hoặc restart với store cũ nếu còn nguyên; xác minh client JMS reconnect, TLS/auth.
5. **Nếu volume mất:** restore từ bản backup nhất quán vào môi trường phù hợp, không copy ngẫu nhiên các file đang được broker mở.
6. **Đối soát:** so message pending/ACK/expiry/DLQ, durable subscriptions, transaction không rõ kết quả.
7. **Replay:** chỉ replay từ outbox/nguồn với event ID không đổi; giới hạn tốc độ, bảo đảm inbox/idempotency.
8. **Đo thực tế:** thời gian first successful send/consume, queue drain, số message mất sau restore, side effect trùng.
9. **Kiểm tra hậu phục hồi:** capacity, disk, journal, backup scheduling và khả năng tiếp tục failover.
10. **Đúc kết:** cập nhật runbook, SLO và kiểm thử định kỳ theo failure model.

**Backup phải được thử restore định kỳ.** Thông báo “backup success” không chứng minh bản sao nhất quán, tương thích phiên bản hay mở được queue thực tế.

## 12. Bài tập tình huống và đáp án

### A — KahaDB còn, broker chết 8 phút

Một queue có message PERSISTENT đã commit. Broker process chết, sau 8 phút restart với đúng store; message vẫn còn.

**Đáp án:** Có bằng chứng **durability qua process restart**. Availability gián đoạn 8 phút. Recoverability khi mất volume chưa được kiểm chứng.

### B — Có hai broker nhưng hai store độc lập

Producer gửi vào A và nhận commit thành công; B đang chạy nhưng không chứa state của A. A và volume A bị mất.

**Đáp án:** B đang online không chứng minh message A còn. Có thể có endpoint còn sẵn sàng nhưng **durability của message được A xác nhận đã thất bại** nếu không có replication/backup/replay.

### C — Snapshot thành công nhưng chưa restore

Nhóm tạo backup mỗi 15 phút, chưa từng khởi động một broker từ bản backup.

**Đáp án:** Chưa có bằng chứng recoverability. Cần restore drill, kiểm tra journal/queue, RPO và RTO cùng client.

### D — HA chuyển đổi trong 15 giây nhưng Billing tạo trùng invoice

Primary chết sau DB commit của Billing nhưng trước JMS ACK; backup redeliver message, Billing tạo invoice thứ hai.

**Đáp án:** HA có thể đã đạt availability, nhưng **end-to-end correctness thất bại**. Inbox/unique event ID giúp không tạo side effect trùng.

### E — NON_PERSISTENT sống qua restart sạch

Dev thấy message NON_PERSISTENT vẫn còn và kết luận nó bền tương đương PERSISTENT.

**Đáp án:** Không đúng. Một quan sát không thay đổi delivery contract; phải thử failure model và bảo đảm được yêu cầu của hệ thống.

### F — Yêu cầu RPO=0 nhưng chấp nhận downtime 24 giờ

**Đáp án:** RPO là dữ liệu có thể mất; RTO là thời gian phục hồi. RPO=0 không tự bảo đảm availability, nên hai mục tiêu phải được xác định và kiểm chứng riêng.

## 13. Checklist quyết định kiến trúc

- [ ] Đã định nghĩa durability cho message/transaction được **confirm**, loại queue/subscription và tập lỗi cụ thể?
- [ ] Producer dùng `PERSISTENT`, transaction và commit đúng; consumer không ACK sớm hơn DB commit cần thiết?
- [ ] Store/journal/bindings/paging/large-message data ở volume bền, có bảo vệ storage phù hợp?
- [ ] Đã thử restart sạch, process crash và một tình huống mất volume trong lab riêng biệt?
- [ ] HA có active ownership, quorum/fencing và client reconnect, không xuất hiện split brain?
- [ ] Đo failover bằng **API JMS thực sự thành công**, không chỉ trạng thái broker process?
- [ ] Backup nhất quán, lưu khác fault domain và đã restore thành công trên instance khác?
- [ ] RPO và RTO của node failure/site disaster có đo độc lập?
- [ ] Đã kiểm kê TTL, expiry, purge, DLQ và durable subscription lifecycle để phân biệt mất dữ liệu với xóa hợp lệ?
- [ ] Producer có eventId ổn định/outbox, consumer có inbox/idempotency khi commit/ACK outcome mơ hồ?
- [ ] Có metric queue lag, store/disk pressure, replication health, restore success, duplicate side effect?
- [ ] Runbook quy định rõ người thực hiện cutover, restore, đối soát, replay và diễn tập định kỳ?

## 14. Kết luận

**Durability** trả lời liệu message đã commit còn được giữ qua *loại lỗi đã xác định*. **Availability** trả lời dịch vụ có thể phục vụ các yêu cầu send/receive và gián đoạn bao lâu. **Recoverability** trả lời liệu có thể khôi phục dữ liệu, trạng thái và hoạt động trong **RPO/RTO** mong muốn khi HA thông thường không đủ.

Bật persistence của ActiveMQ Classic hoặc Artemis **không tự tạo HA**; có backup broker **không tự tạo DR**; có file backup **không chứng minh restore được**; và cả ba cũng **không tự bảo đảm xử lý nghiệp vụ đúng một lần**. Kiến trúc đáng tin cậy phải kiểm chứng riêng persistence, failover và restore/replay, rồi nối chúng bằng event ID ổn định, outbox/inbox và theo dõi từ producer đến consumer.
