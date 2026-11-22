# Đối chiếu dữ liệu persistent và phần đang xử lý sau chuyển đổi broker

> **Chương:** Sẵn sàng cao  
> **Phạm vi:** ActiveMQ Classic và Apache Artemis khi một broker ngừng hoạt động, broker dự phòng nhận vai trò active và JMS client kết nối lại. Bài tập trung vào **đối chiếu những message đã ghi bền vững, message đang được phân phối nhưng chưa xác nhận, và transaction đang chờ kết quả**. Ví dụ Java dùng Java 17, `jakarta.jms`, Classic 6.x hoặc Artemis 2.57.x. Không coi việc kết nối lại thành công là bằng chứng không mất/trùng dữ liệu.

## 1. Vì sao so sánh hai con số QueueSize là chưa đủ?

Một consumer nhận `OrderPaid` từ queue `ha.reconcile.lab`, ghi cập nhật tồn kho rồi broker primary ngừng đúng lúc consumer chuẩn bị `commit()`. Sau khi backup active, queue có thể xuất hiện lại message đó, hoặc không còn message nếu commit đã áp dụng trước khi primary mất kết nối. Nếu chỉ nhìn queue depth giảm/tăng, ta **không thể kết luận đã xử lý thiếu hay xử lý trùng**.

```text
                  Trước failover                          Sau failover

Publisher           Primary                            Active backup
   │                   │                                     │
   ├── persistent SEND─▶│  journal/store record              │
   │◀── send/commit ACK─┤                                     │
   │                   │ ── shared-store hoặc replication ──▶│
   │                   │                                     │
Consumer             │                                     │
   │◀── delivery ──────┤                                     │
   ├── xử lý cục bộ     │                                     │
   ├── ACK/commit ── X  │              failover               │
   │                   X                                     │
   └── reconnect ───────────────────────────────────────────▶│
                                         dữ liệu persistent được recover;
                                         session/in-flight được xây lại
```

Muốn đánh giá đúng phải **theo dõi từng sự kiện bằng ID nghiệp vụ bất biến** và phân biệt:

1. **Tồn tại vật lý:** message/ACK/transaction đã được ghi đủ vào persistence store hay bản sao HA theo mức bảo đảm của topology?
2. **Tình trạng JMS:** message còn pending, scheduled, paged, đã dispatch nhưng chưa ACK, đã ACK/commit, hay đã chuyển DLQ/expiry?
3. **Kết quả nghiệp vụ:** consumer có thực sự hoàn tất tác dụng bên ngoài broker không; có thể đã làm xong DB nhưng broker chưa nhận được ACK.

Kết luận cần đạt là **không mất sự kiện đã được xác nhận là durable, không sinh tác dụng nghiệp vụ trùng ngoài chủ đích, và nhận diện được phần chưa xác định**. Đây là bài toán đối soát dữ liệu, không chỉ đo thời gian downtime.

## 2. Ranh giới bảo đảm của từng topology HA

### 2.1. Artemis: shared-store và replication

| Thành phần | Shared-store primary/backup | Replication primary/backup |
|---|---|---|
| Nguồn dữ liệu | Hai broker dùng **cùng** thư mục dữ liệu trên shared filesystem | Mỗi broker dùng **data directory riêng**, đồng bộ qua mạng |
| Dữ liệu cần có | Journal message, bindings, paging, large-message files trên shared store | Durable data đã được primary **đồng bộ thành công** sang backup |
| Khi backup có thể active | Sau khi lấy được quyền/lock của shared store | Sau khi HA pairing và **initial synchronization hoàn tất**, rồi kích hoạt theo quorum/lock policy |
| Rủi ro trọng yếu | Exclusive lock/fencing, filesystem consistency, volume mất kết nối | Lag/chưa sync, quorum/split brain, chọn nhầm bản dữ liệu cũ khi failback |
| Có sao chép session đang sống? | **Không** | **Không** |

Theo hướng dẫn Artemis, **chỉ message data đã ghi vào storage** mới có cơ sở sống sót qua failover; các send/ACK đang bay và chưa ghi vào storage không được tự động giữ nguyên chỉ vì client có `ha=true`. Với replication, backup **chưa đồng bộ xong** không phải một bản sao đã sẵn sàng để so sánh 1:1. Trước khi fault injection, phải ghi nhận **backup đã paired và synchronized**, không chỉ process “running”.

Fragment Artemis `broker.xml` để nhận biết loại HA, **không phải cấu hình HA đầy đủ** (cluster connection, connector, volume, quorum/fencing phải được thiết kế riêng):

```xml
<!-- Primary trong topology SHARED-STORE: nằm trong <core> hiện có. -->
<ha-policy>
    <shared-store>
        <primary/>
    </shared-store>
</ha-policy>
```

```xml
<!-- Backup tương ứng, trên broker instance KHÁC. -->
<ha-policy>
    <shared-store>
        <backup/>
    </shared-store>
</ha-policy>
```

Với **replication** thay vì shared-store, topology dùng `<ha-policy><replication><primary>...` và `<backup>...` với nhóm/coordination phù hợp. Không áp dụng cấu hình shared-store lên hai data directory độc lập rồi kỳ vọng message tự được replicate. Khi primary cũ quay lại, **không** ép nó active trên journal/bản sao cũ trước khi có quy trình failback/sync hợp lệ.

### 2.2. Classic: shared KahaDB/JDBC, không nhầm network of brokers với HA store

Ở Classic, các mô hình master/slave thường dùng **shared filesystem/KahaDB** hoặc **shared JDBC database** với exclusive lock. Backup lấy lock khi primary ngừng và mở connector cho client; dữ liệu đến từ **cùng persistence store**. Network connector nối hai broker active **không tự tạo một bản sao đầy đủ của mọi queue và mọi in-flight transaction**.

Ví dụ Classic shared-store, đoạn trích trong `conf/activemq.xml` của broker có HA được vận hành đúng:

```xml
<persistenceAdapter>
    <kahaDB directory="/shared/activemq/kahadb"/>
</persistenceAdapter>
```

Cả primary và standby trỏ tới thư mục shared store đúng chuẩn **chỉ khi filesystem hỗ trợ exclusive locking ổn định**; không cho hai broker active đồng thời viết cùng KahaDB. Với JDBC master/slave, phải xác minh đúng database/lock, không so sánh journal KahaDB của hai node nếu chúng không dùng chung dữ liệu.

**Classic Failover Transport** giúp client tự đổi endpoint, **không thay một cơ chế HA storage**:

```java
import org.apache.activemq.ActiveMQConnectionFactory;

ActiveMQConnectionFactory factory = new ActiveMQConnectionFactory(
    "failover:(tcp://classic-primary:61616,tcp://classic-backup:61616)" +
    "?randomize=false&timeout=5000");
```

Theo tài liệu Classic, failover transport theo dõi/replay transaction trong giới hạn giao thức. Nếu commit diễn ra đúng cửa sổ đứt mạng, client có thể nhận `TransactionRolledBackException`, nhưng **không được chỉ dựa vào một dòng log "reconnect success" để khẳng định từng ACK hay side effect bên ngoài đã chạy đúng một lần**.

## 3. Phân loại trạng thái tại thời điểm cắt broker

| Cửa sổ lỗi | Điều đã biết trước failover | Điều có thể thấy sau failover | Cách đối soát |
|---|---|---|---|
| **A. Chưa gửi** | Producer chưa gọi `send` | Không có message từ lần đó | Kiểm tra outbox/nguồn sự kiện |
| **B. Đã gửi và được xác nhận durable** | Broker xác nhận `send` hoặc `commit` theo chế độ lưu bền đã chọn | Message chưa ACK có cơ sở được recover | Tra `eventId` ở queue, DLQ, expiry hoặc ledger xử lý |
| **C. Send đang chờ phản hồi** | Socket đứt trong `send`/`commit` | Broker có thể đã nhận/lưu, hoặc chưa | Ghi `IN_DOUBT`; không kết luận “chưa gửi” |
| **D. Đã dispatch, chưa ACK/commit** | Consumer đang giữ message trong Session | Có thể **redelivery** từ storage sau session mất | Gắn `eventId`, đọc `JMSXDeliveryCount`/broker metrics |
| **E. ACK/commit đang bay** | Client chưa có xác nhận transaction | Message có thể còn hoặc đã được loại khỏi queue | Xem log commit, queue và **business ledger** |
| **F. Consumer đã đổi DB nhưng chưa commit JMS** | Side effect bên ngoài JMS có thể đã xong | Message có thể redelivery | Consumer phải idempotent theo `(consumerGroup,eventId)` |
| **G. Nonpersistent/unflushed** | Chưa có cam kết storage bền vững | Có thể mất | Không đưa vào tập “được bảo đảm sống sót” |
| **H. XA đã prepare** | Transaction thuộc transaction manager phân tán | Có thể cần recovery/heuristic handling | Dùng XA/JTA recovery, **không** replay tay tùy tiện |

**Điểm cốt lõi:** `PERSISTENT` + queue durable + store hoạt động và xác nhận gửi/commit có ý nghĩa khác với `NON_PERSISTENT` hoặc asynchronous send chưa nhận broker confirmation. Một `receive()` thành công **không có nghĩa message đã được ACK bền vững**. Với consumer transacted, điểm quyết định là `commit()`.

### Một timeline điển hình

```text
T0  Producer: send persistent eventId=pay-714, commit() returns OK
T1  Consumer: receive pay-714, chưa commit/ACK
T2  Consumer: cập nhật hệ thống bên ngoài, kết quả đã thành công
T3  Primary chết trước khi consumer commit JMS
T4  Backup active; consumer mới có thể nhận lại pay-714
T5  Idempotency ledger phát hiện pay-714 đã xử lý, không lặp side effect
T6  Consumer commit/ACK để kết thúc xử lý message redelivered
```

Tại T4, **message xuất hiện lại là hành vi recovery đúng**, không tự động là duplicate từ producer. Duplicate về mặt **giao message** có thể được chấp nhận; điều phải ngăn là duplicate **tác dụng nghiệp vụ** ở T5.

## 4. Vì sao count sau failover có thể khác mà không mất dữ liệu?

Đối với một queue có nhiều consumer, một phần message ở trạng thái **in-delivery**. Sau failover, các session cũ bị mất và broker có thể đưa chúng về pending hoặc scheduled-for-redelivery; do đó:

- `deliveringCount` / `InFlightCount` có thể giảm về 0 khi session bị hủy.
- Số message pending có thể tăng tương ứng, dù **tổng dữ liệu chưa ACK không đổi**.
- Một số message bị ACK/commit thành công trước lỗi sẽ biến mất khỏi source queue như bình thường.
- DLQ, expiry, scheduled message, paging, selectors và message group làm thay đổi hình thức quan sát.
- Các bộ đếm lịch sử enqueue/dequeue có thể reset khi broker restart; chúng **không phải sổ cái persistent**.

### Đọc metrics đúng tên

| Mục quan sát | Classic (JMX queue destination) | Artemis (QueueControl/metrics) |
|---|---|---|
| Số message chưa được ACK / ở queue | `QueueSize` | `messageCount` |
| Đã dispatch nhưng chưa ACK | `InFlightCount` | `deliveringCount` |
| Tổng đã thêm vào queue từ khi đếm | `EnqueueCount` | `messagesAdded` |
| Đã ACK thành công trong kỳ thống kê | `DequeueCount` | `messagesAcknowledged` |
| Quá hạn / bị loại theo policy | `ExpiredCount` + DLQ | `messagesExpired`, `messagesKilled` + expiry/DLQ queues |
| Message scheduled/redelivery | Broker scheduler/JMX tương ứng | `scheduledCount`/`scheduledMessageCount` tùy API/metrics |

**Đừng cộng trừ mù quáng.** Classic `QueueSize` bao gồm message chưa ACK trong store; Artemis `messageCount` bao gồm scheduled, paged **và in-delivery messages**. Vì vậy biểu thức `messageCount + deliveringCount` ở Artemis **đếm kép** các message đang giao. Các counter như `EnqueueCount` thường tính từ khi broker tạo/reset metric, không phải snapshot transaction nhất quán giữa hai node.

Một ví dụ dễ hiểu (queue **không có consumer khác**, không DLQ/expiry trong khoảng đo):

| Mốc | Tổng chưa ACK | Đang in-flight | Phần còn pending (minh họa) |
|---|---:|---:|---:|
| Trước failover | 100 | 12 | 88 |
| Sau failover, các session cũ bị hủy | 100 | 0 | 100 |
| Sau 5 transaction xử lý thành công | 95 | 0 | 95 |

Không nên tuyên bố “backup có thêm 12 message trùng” chỉ vì số pending tăng từ 88 lên 100. Đó có thể chỉ là 12 message **quay lại từ in-flight**.

## 5. Đối soát bằng event ID: ba nguồn bằng chứng

Để xác minh tập message đã được xác nhận và công việc chưa hoàn tất, phải có **event ID độc lập với JMS provider**. `JMSMessageID` hữu ích cho tracing, nhưng có thể đổi khi một sự kiện được producer tạo/gửi lại; nên lấy `eventId` từ nguồn nghiệp vụ, lưu bền vững và giữ nguyên qua retry.

| Nguồn bằng chứng | Dữ liệu cần có | Điều **không** chứng minh |
|---|---|---|
| **Producer outbox/ledger** | `eventId`, `batchId`, thời gian tạo, `sendStatus=CONFIRMED/IN_DOUBT`, thời điểm publish | Một `CONFIRMED` không chứng minh consumer đã xử lý |
| **Broker queue/management** | Queue/address, message count, in-flight, scheduled, DLQ/expiry, metadata `eventId` | Một browse không phải snapshot toàn cục và có thể bỏ sót in-flight |
| **Consumer business ledger** | `(consumerGroup,eventId)` unique, thời điểm commit side effect, kết quả | Không tự nói message còn pending ở broker hay chưa |

Đối soát theo **mỗi eventId**, không đối soát đơn thuần bằng lượng message:

```text
eventId       Producer ledger        Broker/queue state         Business ledger        Quyết định
------------------------------------------------------------------------------------------------
pay-711       CONFIRMED              pending                   chưa có                tiếp tục consume
pay-712       CONFIRMED              redelivered/in-flight     COMMITTED              ACK lại, không xử lý trùng
pay-713       IN_DOUBT               pending                   chưa có                không resend mù
pay-714       CONFIRMED              không ở source            COMMITTED              đối soát hoàn tất
pay-715       CONFIRMED              không ở source            chưa có                điều tra DLQ/expiry/route
```

**`IN_DOUBT` là trạng thái nhận thức của client**, không phải một queue vật lý đặc biệt. Message có thể đang thực sự ở broker hoặc không. Khi không thể chứng minh kết quả gửi, retry phải dùng **cùng eventId** và có cơ chế chống trùng; với Artemis có thể dùng duplicate detection `_AMQ_DUPL_ID` (giới hạn bởi cache theo address), và consumer vẫn phải idempotent.

### Nguyên tắc “cân đối” sau khi hệ thống yên tĩnh

Chỉ sau khi **dừng producer, không còn session in-flight cũ và tạm ngừng consumer** ở môi trường lab, mới có thể xây tập trạng thái tương đối ổn định:

```text
Tập event ID từ outbox confirmed/under-investigation
     |
     +--> đã xử lý thành công (consumer ledger)
     +--> còn chờ ở queue nguồn
     +--> đã chuyển DLQ hoặc expiry có chủ đích
     +--> đang scheduled/redistributed/paged hoặc in-flight mới
     +--> chưa đối chiếu được  ==> INVESTIGATE
```

Các nhánh **không mặc nhiên là một phép chia tập hoàn hảo**: một event có thể hiện diện ở queue và ledger nếu side effect đã commit nhưng ACK JMS chưa commit; một event cũng có thể tồn tại hai message vật lý nếu producer retry. Khi đếm, cần phân biệt **số eventId duy nhất** và **số lần xuất hiện** của cùng eventId.

### Ví dụ đối chiếu DB không thay cho kiểm tra broker

Giả sử `outbox_events` lưu mọi sự kiện gốc và `processed_events` có unique key `(consumer_group,event_id)`:

```sql
-- PostgreSQL: liệt kê sự kiện nguồn chưa có bằng chứng consumer thành công.
SELECT o.event_id, o.send_status, o.created_at
FROM outbox_events AS o
LEFT JOIN processed_events AS p
  ON p.event_id = o.event_id
 AND p.consumer_group = 'billing'
WHERE o.batch_id = :batch_id
  AND p.event_id IS NULL
ORDER BY o.created_at, o.event_id;
```

Kết quả là **danh sách cần đối chiếu với broker/DLQ**, không phải danh sách chắc chắn bị mất. Khi side effect ở một hệ thống khác DB hiện tại, phải dùng idempotency key/log xác nhận của chính hệ thống đích.

## 6. Runbook đối soát an toàn trước và sau failover

### W0 — Xác nhận chính xác loại HA và storage

1. Ghi broker product/version, `brokerName`/node ID, loại HA, active/passive hiện tại, datasource hoặc volume mount, journal/bindings/paging/large messages, time UTC.
2. **Artemis replication:** chỉ bắt đầu phép thử mất primary sau khi backup đã **synchronized**. Xem log pairing/activation/quorum; nếu chưa đồng bộ, dừng và phân loại `NOT_READY`.
3. **Artemis shared store / Classic shared KahaDB:** kiểm tra chỉ có **một owner** của store/lock, cả hai cấu hình đúng storage path; không manually start hai active.
4. Ghi client URI/failover policy và cấu hình persistent/durable/sync. **Không** coi cluster với hai broker active là standby HA nếu không có data protection tương ứng.

### W1 — Lập mốc trước sự cố (T0)

Trên **queue lab**, seed một batch message `PERSISTENT`, commit thành công rồi ghi manifest `eventId`. Chụp:

- danh sách event ID đã gửi xác nhận và số lượng unique;
- queue size, delivering/in-flight, scheduled, DLQ/expiry count và số consumer;
- log lần startup/synchronization của cả hai node;
- consumer ledger đã commit và số message đang xử lý nhưng chưa commit.

**Không** bật công cụ browse xóa/ack khi thu thập mốc. Nếu dùng QueueBrowser/JMX, giới hạn phạm vi batch/selector; có thể tạm dừng các consumer khác để giảm race.

### W2 — Thực hiện chuyển đổi broker có kiểm soát

Trong môi trường staging được phê duyệt, để một consumer nhận **một message** trong transacted Session rồi **chưa commit**. Sau đó gây mất primary theo kịch bản HA đã định (force failover theo management hoặc fault injection dành riêng cho lab).

Ghi:

- thời điểm primary mất active, backup active và client kết nối lại;
- exception từ `send`/`commit`, đặc biệt `TransactionRolledBackException` hoặc lỗi mất phản hồi;
- eventId đang in-flight; không gộp nó với message chưa từng gửi;
- những lỗi replication/quorum/lock, nếu có.

Không thử `kill -9` hoặc can thiệp storage trên broker sản xuất. Với Artemis, shutdown graceful **không mặc định** kích hoạt backup ở mọi cấu hình shared-store (`failover-on-shutdown` có thể là `false`), nên chọn cách kích hoạt đúng với kịch bản kiểm thử.

### W3 — Sau failover: quan sát không phá dữ liệu

1. Xác nhận **chỉ một active broker** và backup thực sự đã kích hoạt bằng HA, không phải một broker độc lập có queue trùng tên.
2. Trước khi cho nhiều consumer xử lý tiếp, ghi metrics trên **broker active mới** và dùng QueueBrowser/management để tìm eventId của batch.
3. Đối chiếu message persistent đã `COMMIT_CONFIRMED` với nguồn outbox; xác định các ID có thể đã ACK, vào DLQ/expiry, hoặc cần điều tra.
4. Đối chiếu event đang in-flight trước chuyển đổi: có thể giờ pending, được redeliver hoặc đã ACK trước sự cố. `JMSXDeliveryCount` là tín hiệu hỗ trợ, **không phải bằng chứng chính xác tuyệt đối** qua mọi crash/topology.
5. Chỉ sau khi có kết quả sơ bộ mới bật lại consumers/producer theo quy trình, giữ nguyên eventId và idempotency.

### W4 — Kết luận bằng kết quả nghiệp vụ

Đối với mỗi eventId trong manifest, lưu kết quả theo mẫu:

```text
runId:
broker product/version, HA mode, oldActive/newActive, storage identity:
backup synchronized before fault?:
eventId, JMSMessageID (nếu có):
producerStatus: CONFIRMED | IN_DOUBT:
before: sourceQueue / delivering / DLQ / consumerLedger:
after:  sourceQueue / delivering / DLQ / consumerLedger:
observed redeliveryCount:
business effect count (unique eventId):
decision: OK_PENDING | OK_PROCESSED | QUARANTINED | IN_DOUBT | INVESTIGATE:
evidence timestamps and broker logs:
```

**Pass không có nghĩa số message ở queue bằng số trước failover**: có thể message đã được xử lý/ACK hợp lệ. Pass nghĩa là **mọi sự kiện thuộc tập kỳ vọng đều có lời giải thích và bằng chứng**, không có side effect trùng không được ngăn chặn, và không còn ID đã xác nhận mà không truy ra trạng thái hợp lệ.

## 7. Lab Java/JMS: seed, giữ một message in-flight, browse và ACK sau failover

Bài tập dùng **queue riêng, không có dữ liệu production**: `ha.reconcile.lab`. Đặt `PERSISTENT` và queue durable. Lấy `BROKER_URL`, `BROKER_USER`, `BROKER_PASSWORD` qua biến môi trường; không đưa password vào source hoặc command line. Lab trước tiên dùng Artemis Core; cách thay provider cho Classic ở mục 7.4.

### 7.1. Provision queue dành riêng cho lab

Trong Artemis `broker.xml`, thêm **một fragment** bên trong `<addresses>` hiện có trên cấu hình broker đã được HA quản lý:

```xml
<address name="ha.reconcile.lab">
    <anycast>
        <queue name="ha.reconcile.lab"/>
    </anycast>
</address>
```

Đây là queue ANYCAST mặc định durable trong cấu hình tường minh. Nếu dùng Classic, có thể thêm vào `<destinations>` hiện hữu:

```xml
<queue physicalName="ha.reconcile.lab"/>
```

Không deploy cấu hình broker mới mà bỏ các phần tử security, HA, persistence đang hoạt động. Chỉ thử khi đã có primary/backup trên **cùng topology HA**, backup sẵn sàng và queue tồn tại trước khi seed.

### 7.2. Maven dependency và quy tắc chạy

Cho Artemis 2.57.x / Java 17:

```xml
<dependency>
    <groupId>org.apache.artemis</groupId>
    <artifactId>artemis-jakarta-client</artifactId>
    <version>2.57.0</version>
</dependency>
```

Tạo `HaReconcileLab.java`:

```java
import jakarta.jms.ConnectionFactory;
import jakarta.jms.DeliveryMode;
import jakarta.jms.JMSContext;
import jakarta.jms.JMSProducer;
import jakarta.jms.JMSRuntimeException;
import jakarta.jms.Message;
import jakarta.jms.Queue;
import jakarta.jms.QueueBrowser;
import jakarta.jms.TextMessage;
import jakarta.jms.TransactionRolledBackRuntimeException;
import org.apache.activemq.artemis.jms.client.ActiveMQConnectionFactory;

import java.util.ArrayList;
import java.util.Collections;
import java.util.Enumeration;
import java.util.List;

public final class HaReconcileLab {
    private static final String QUEUE = "ha.reconcile.lab";

    static String env(String key) {
        String value = System.getenv(key);
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException("Missing environment: " + key);
        }
        return value;
    }

    static String eventId(String batch, int index) {
        if (!batch.matches("[A-Za-z0-9_-]{1,64}") || index < 1) {
            throw new IllegalArgumentException("Invalid batch/index");
        }
        return batch + "-" + index;
    }

    static void seed(ConnectionFactory cf, String user, String password,
                     String batch, int count) throws Exception {
        if (count < 1 || count > 100) {
            throw new IllegalArgumentException("Lab limit: 1..100");
        }
        try (JMSContext tx = cf.createContext(
                user, password, JMSContext.SESSION_TRANSACTED)) {
            Queue queue = tx.createQueue(QUEUE);
            JMSProducer producer = tx.createProducer()
                .setDeliveryMode(DeliveryMode.PERSISTENT);
            for (int i = 1; i <= count; i++) {
                String id = eventId(batch, i);
                TextMessage m = tx.createTextMessage("DATA-" + id);
                m.setStringProperty("batchId", batch);
                m.setStringProperty("eventId", id);
                producer.send(queue, m);
            }
            // Chỉ khi commit trả OK mới đánh dấu batch đã xác nhận.
            tx.commit();
            System.out.println("SEED_COMMIT_CONFIRMED batch=" + batch
                + " count=" + count);
        }
    }

    static void browse(ConnectionFactory cf, String user, String password,
                       String batch) throws Exception {
        eventId(batch, 1); // validate input dùng trong JMS selector
        try (JMSContext ctx = cf.createContext(user, password)) {
            Queue queue = ctx.createQueue(QUEUE);
            QueueBrowser browser = ctx.createBrowser(
                queue, "batchId = '" + batch + "'");
            try {
                List<String> ids = new ArrayList<>();
                Enumeration<?> entries = browser.getEnumeration();
                while (entries.hasMoreElements()) {
                    Message m = (Message) entries.nextElement();
                    ids.add(m.getStringProperty("eventId"));
                }
                Collections.sort(ids);
                System.out.println("BROWSE_VISIBLE batch=" + batch
                    + " ids=" + ids);
            } finally {
                browser.close();
            }
        }
    }

    static void receive(ConnectionFactory cf, String user, String password,
                        String batch, int index, boolean hold)
                        throws Exception {
        String id = eventId(batch, index);
        try (JMSContext tx = cf.createContext(
                user, password, JMSContext.SESSION_TRANSACTED)) {
            Queue queue = tx.createQueue(QUEUE);
            String selector = "eventId = '" + id + "'";
            Message m = tx.createConsumer(queue, selector).receive(15_000L);
            if (m == null) {
                throw new IllegalStateException("No message for " + id);
            }
            int deliveries = m.propertyExists("JMSXDeliveryCount")
                ? m.getIntProperty("JMSXDeliveryCount") : -1;
            System.out.printf("RECEIVED_UNCOMMITTED id=%s jmsId=%s count=%d%n",
                id, m.getJMSMessageID(), deliveries);

            if (hold) {
                System.out.println(
                    "HOLD: failover primary in LAB, then press ENTER");
                System.in.read(); // chủ động giữ tx chưa commit
            }
            try {
                tx.commit();
                System.out.println("CONSUME_COMMIT_CONFIRMED id=" + id);
            } catch (TransactionRolledBackRuntimeException rolledBack) {
                System.out.println("TX_ROLLED_BACK_CONFIRMED id=" + id);
                throw rolledBack;
            } catch (JMSRuntimeException uncertain) {
                System.out.println("TX_COMMIT_IN_DOUBT id=" + id);
                throw uncertain;
            }
        }
    }

    public static void main(String[] args) throws Exception {
        if (args.length < 2) {
            throw new IllegalArgumentException(
                "Use seed|browse|hold|consume <batch> [countOrIndex]");
        }
        String url = env("BROKER_URL");
        String user = env("BROKER_USER");
        String password = env("BROKER_PASSWORD");
        String batch = args[1];

        ActiveMQConnectionFactory cf = new ActiveMQConnectionFactory(url);
        try {
            switch (args[0]) {
                case "seed" -> {
                    if (args.length != 3) throw new IllegalArgumentException();
                    seed(cf, user, password, batch, Integer.parseInt(args[2]));
                }
                case "browse" -> {
                    if (args.length != 2) throw new IllegalArgumentException();
                    browse(cf, user, password, batch);
                }
                case "hold", "consume" -> {
                    if (args.length != 3) throw new IllegalArgumentException();
                    receive(cf, user, password, batch,
                        Integer.parseInt(args[2]), args[0].equals("hold"));
                }
                default -> throw new IllegalArgumentException("Unknown command");
            }
        } finally {
            cf.close();
        }
    }
}
```

**Mã này cố ý giới hạn tác dụng:** `seed` chỉ gửi tối đa 100 message lab trong một JMS transaction; `browse` dùng `QueueBrowser`, **không tiêu thụ**; `hold` để một message in-flight chưa commit; `consume` commit một message sau khi nhận. Không có DB side effect thật, không chứng minh business exactly-once. Mỗi lần chạy dùng batch mới, ví dụ `ha_case01`, không dùng lại batch của lần gửi trước.

### 7.3. Chạy trên Artemis HA

Một URI **Core JMS** ví dụ cho ứng dụng đã kết nối được vào primary/backup và nhận topology từ broker:

```text
tcp://artemis-primary:61616?ha=true&reconnectAttempts=30&retryInterval=500&initialConnectAttempts=10
```

Đặt URI này trong `BROKER_URL` ở môi trường lab, với DNS/host/port và quảng bá connector đúng topology. `ha=true` **không tự tạo backup**, cũng không chứng minh backup đang đồng bộ. Các thông số chỉ điều khiển hành vi client tìm và thử kết nối lại.

Quy trình:

1. Đảm bảo primary active, backup synchronized; không có consumer nào khác trên `ha.reconcile.lab`.
2. Chạy `HaReconcileLab seed ha_case01 10`. Chỉ coi batch confirmed nếu thấy `SEED_COMMIT_CONFIRMED`.
3. Chạy `HaReconcileLab browse ha_case01`, lưu danh sách `ha_case01-1 ... ha_case01-10`; chụp `messageCount`, `deliveringCount`.
4. Mở terminal khác, chạy `HaReconcileLab hold ha_case01 3`. Nó nhận message thứ ba, **chưa commit**, rồi chờ Enter.
5. Từ một terminal khác, **chuyển primary/backup theo kịch bản HA lab đã được phê duyệt**; chờ backup active và bảo đảm primary cũ không đồng thời active.
6. Trong terminal `hold`, nhấn Enter, ghi xem commit **đã được xác nhận rollback**, **không xác định**, hay success; không giả định mọi lỗi đều rollback.
7. Sau khi client/session cũ kết thúc, chạy lại `browse ha_case01` và kiểm tra `ha_case01-3`. Nếu message được redeliver, chạy `consume ha_case01 3` để ACK, rồi browse lại.
8. Đối chiếu batch 10 ID ban đầu với phần còn pending và các ID đã xử lý; chỉ dùng queue lab riêng để kiểm tra. Nếu failover chưa thực sự hoàn tất hoặc còn consumer khác, kết quả browse có thể bị ảnh hưởng.

**Một ví dụ output dự kiến** (không phải kết quả đã chạy):

```text
SEED_COMMIT_CONFIRMED batch=ha_case01 count=10
BROWSE_VISIBLE batch=ha_case01 ids=[ha_case01-1, ..., ha_case01-10]
RECEIVED_UNCOMMITTED id=ha_case01-3 jmsId=ID:... count=1
HOLD: failover primary in LAB, then press ENTER
TX_ROLLED_BACK_CONFIRMED id=ha_case01-3
BROWSE_VISIBLE batch=ha_case01 ids=[ha_case01-1, ..., ha_case01-10]
```

Nếu commit thực sự thành công trước khi failover áp dụng, message `ha_case01-3` có thể **không còn trong queue**; phải có bằng chứng commit/ledger tương ứng. Nếu failover/rollback đã xảy ra nhưng redelivery được hẹn giờ, message có thể chưa hiện ngay. `QueueBrowser` **không phải snapshot tuyệt đối**; cần kết hợp metrics và bảo đảm không có consumer khác đang giữ message.

### 7.4. Chạy cùng logic với Classic

Đoạn mã wiring dùng với Classic:

```java
import org.apache.activemq.ActiveMQConnectionFactory;

ConnectionFactory cf = new ActiveMQConnectionFactory(
    "failover:(tcp://classic-primary:61616,tcp://classic-backup:61616)"
    + "?randomize=false&timeout=5000");
HaReconcileLab.seed(cf, user, password, "classic_case01", 10);
HaReconcileLab.browse(cf, user, password, "classic_case01");
```

Đây là **đoạn wiring dùng chung các method static**, chạy trong một ứng dụng Classic riêng và thay dependency/import Artemis bằng `org.apache.activemq:activemq-client` (Classic 6.x). `HaReconcileLab.main` trong ví dụ gốc tạo Artemis factory; nếu viết command-line runner cho Classic phải thay phần khởi tạo factory đó bằng Classic factory. Không dùng đồng thời hai provider cùng tên class trong một chương trình mà không phân biệt package.

## 8. Kịch bản fault injection và tiêu chí PASS

| Kịch bản | Điểm gây lỗi | Quan sát bắt buộc |
|---|---|---|
| F0 — baseline | Không gây lỗi | Batch confirmed, đủ eventId ở queue, consumer commit giảm outstanding đúng số |
| F1 — message in-flight | Consumer giữ transaction sau receive, primary mất | Message chưa commit có thể redeliver, không bị ghi nhận xử lý hai lần |
| F2 — producer commit chưa rõ | Cắt kết nối khi gửi/commit | Lỗi `IN_DOUBT`; tra eventId trước khi retry, giữ ID không đổi |
| F3 — consumer đã làm side effect ngoài JMS | Giữ side effect DB thành công nhưng ACK chưa commit | Redelivery **không** lặp side effect nhờ unique key/idempotency |
| F4 — replication chưa sync | Backup chưa hoàn tất copy dữ liệu | **Không chạy test dữ liệu**; đánh dấu `NOT_READY`, không tuyên bố HA pass |
| F5 — failback | Primary cũ khởi động lại sau backup active | Không split brain, không làm active bản journal cũ; sync/fencing hoàn chỉnh |
| F6 — message ở DLQ/expiry | Message đã chuyển theo policy trong lúc failover | Có bằng chứng ở destination mới, không bị gắn nhãn mất dữ liệu |

**Thực nghiệm F2 khó tạo chính xác** vì cần mất phản hồi sau khi broker đã xử lý commit. Dùng network proxy/fault injection của môi trường lab; một lệnh dừng process ngẫu nhiên không bảo đảm tạo đúng cửa sổ. Phải chấp nhận cả hai kết quả vật lý (`đã commit` hoặc `chưa commit`) khi exception không đưa ra chứng cứ đủ mạnh.

### Các dấu hiệu khiến kết quả không đạt

- Một broker khác đang active trên data store riêng mà ứng dụng nhầm là backup của primary.
- Backup replication chưa synchronized nhưng đã được xem như bản sao cuối cùng.
- Event đã `COMMIT_CONFIRMED` và chưa có business processing, DLQ/expiry/route hợp lệ nhưng **không tìm thấy** trong tập dữ liệu đã đối soát; cần điều tra storage/HA.
- Cùng `(consumerGroup,eventId)` gây **hai** side effect thực dù consumer redelivery hợp lệ.
- Operator xóa queue, `purge`, `removeMessages` hoặc replay hàng loạt khi chưa có manifest và bằng chứng, làm thay đổi hiện trường sự cố.

## 9. Recovery khi phát hiện thiếu/trùng/in-doubt

| Kết quả đối soát | Hành động tiếp theo | Không được làm |
|---|---|---|
| Event confirmed, vẫn pending | Cho consumer xử lý theo policy | Resend với eventId mới |
| Event đã xử lý trong ledger nhưng còn queue | Consumer idempotent nhận/ACK lại | Thực hiện side effect lần nữa |
| Event ở DLQ/expiry | Xác minh chính sách và quyết định replay có phê duyệt | Purge DLQ hoặc replay mọi message vô điều kiện |
| Producer `IN_DOUBT`, chưa thấy message | Đối chiếu outbox và xác định retry **cùng eventId** có dedup/idempotency | Kết luận “broker chắc chắn chưa nhận” từ timeout |
| Chỉ có số liệu queue khác | Tách in-flight, scheduled, paged và historical counters | Kết luận mất dữ liệu từ một cặp QueueSize |
| Hai node cùng active hoặc dữ liệu replication lệch | **Tạm dừng ghi**, xử lý fencing/quorum và xác định bản authoritative | Cưỡng bức cả hai node ghi tiếp hoặc hợp nhất journal thủ công |
| XA prepared transaction | Giao transaction manager khôi phục prepare/commit/rollback | Tự xóa record transaction hay resend message tùy ý |

Đối với Artemis, có thể dùng duplicate detection theo `_AMQ_DUPL_ID` với producer retry có cùng ID, nhưng cache này **có giới hạn** và không thay idempotency của consumer. Với Classic, chiến lược producer retry/failover phải được kiểm thử với version cụ thể. Nếu cần đảm bảo cập nhật DB và publish JMS không mất dữ liệu khi một tiến trình chết giữa hai bước, áp dụng outbox từ transaction DB và relay idempotent; local JMS transaction không bao phủ resource DB.

## 10. Checklist nghiệm thu sau chuyển đổi broker

- [ ] Xác định đúng **broker active cũ/mới**, topology HA, cùng store (shared) hay backup đã synchronized (replication).
- [ ] Không có split brain, hai node không ghi hai bản dữ liệu độc lập; failback có fencing/sync hợp lệ.
- [ ] Định nghĩa rõ `PERSISTENT`, queue durable, journal/store sync và thời điểm producer được coi là `CONFIRMED`.
- [ ] Có manifest `eventId` trước test, không chỉ đo tổng queue depth.
- [ ] Sau failover ghi cả pending, delivering/in-flight, scheduled, DLQ/expiry và business ledger; hiểu counter reset khi restart.
- [ ] Message đang receive nhưng chưa commit được đánh giá theo redelivery; không coi redelivery là producer phát trùng.
- [ ] Commit chưa xác định được giữ `IN_DOUBT`, retry bằng ID ổn định và cơ chế chống trùng.
- [ ] Consumer có unique `(consumerGroup,eventId)` / idempotency cho side effect; ACK được đặt sau khi xử lý đáng tin cậy.
- [ ] Đã chạy kiểm chứng baseline và ít nhất một case in-flight failover trên **broker lab riêng**, không làm biến đổi queue production.
- [ ] Mỗi event confirmed có trạng thái và bằng chứng rõ ràng, các trường hợp chưa rõ được lưu `INVESTIGATE` chứ không ẩn bằng việc purge/replay.

**Kết luận:** Sau chuyển đổi broker, dữ liệu persistent không biến mất chỉ vì in-flight session thay đổi, nhưng **session/ACK/commit đang bay không được sao chép như một state machine hoàn hảo**. Đối soát chính xác cần **eventId bền vững, đúng bằng chứng storage/HA, tách pending–in-flight–processed, nhận biết commit in-doubt và idempotency nghiệp vụ**. Queue depth chỉ là tín hiệu vận hành, không thể thay một sổ cái sự kiện.

## Tài liệu chính thức

1. [Apache Artemis 2.57.0 — High Availability and Failover](https://artemis.apache.org/components/artemis/documentation/latest/ha.html): shared-store, replication synchronization, transaction state và in-flight operations.
2. [Apache Artemis 2.57.0 — Core Client Failover](https://artemis.apache.org/components/artemis/documentation/latest/client-failover.html): `ha`, reconnect, reattachment và `confirmationWindowSize`.
3. [Apache Artemis 2.57.0 — Management](https://artemis.apache.org/components/artemis/documentation/latest/management.html): `QueueControl`/`ActiveMQServerControl`, `listMessages`, `countMessages`, prepared transactions.
4. [Apache Artemis 2.57.0 — Metrics](https://artemis.apache.org/components/artemis/documentation/latest/metrics.html): `message.count`, `delivering.message.count`, `messages.acknowledged` và scheduled metrics.
5. [ActiveMQ Classic — Shared File System Master Slave](https://activemq.apache.org/components/classic/documentation/shared-file-system-master-slave): exclusive lock trên KahaDB/shared directory và client failover.
6. [ActiveMQ Classic — JDBC Master Slave](https://activemq.apache.org/components/classic/documentation/jdbc-master-slave): shared JDBC store/lock và broker activation.
7. [ActiveMQ Classic — Failover Transport Reference](https://activemq.apache.org/components/classic/documentation/failover-transport-reference): transaction replay, `TransactionRolledBackException`, timeout và tình huống commit in-doubt.
8. [ActiveMQ Classic — How Do I Find the Size of a Queue?](https://activemq.apache.org/components/classic/documentation/how-do-i-find-the-size-of-a-queue): `QueueSize`, `InFlightCount`, `EnqueueCount`, `DequeueCount` và QueueBrowser.
