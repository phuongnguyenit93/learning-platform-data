# Chạy kiểm thử tương thích, chuyển lưu lượng và xác định điểm rollback

> **Chương:** Di chuyển broker  
> **Phạm vi:** Lập kế hoạch và thực hiện cutover giữa hai môi trường ActiveMQ, đặc biệt khi chuyển từ ActiveMQ Classic sang Artemis hoặc ngược lại. Bài tập trung vào **kiểm thử tương thích theo contract**, rehearsal, chuyển lưu lượng có kiểm soát, quan sát sau cutover và xác định thời điểm rollback còn an toàn. Dữ liệu store của hai broker không phải định dạng có thể hoán đổi trực tiếp.

## 1. Migration thành công là giữ nguyên contract nghiệp vụ

Đổi broker không chỉ là thay hostname trong cấu hình client. Hệ thống cần giữ các hành vi mà producer, consumer và nghiệp vụ đang dựa vào:

- Message đến đúng logical destination và đúng nhóm consumer.
- Body, headers và application properties được giữ đúng kiểu/giá trị.
- Selector tiếp tục chọn đúng tập message.
- Queue/topic, durable subscription và routing có cùng ý nghĩa nghiệp vụ.
- Transaction, acknowledgment, redelivery và DLQ không làm mất hoặc nhân đôi side effect.
- Ordering theo business key được giữ trong giới hạn contract đã cam kết.
- Security, TLS, authorization, retry và reconnect hoạt động trong môi trường mới.
- Backlog, message hết hạn, scheduled delivery và poison message được xử lý có chủ đích.

Một migration có thể “kết nối thành công” nhưng vẫn sai nghiệp vụ: selector lọc mất message do property type đổi; topic subscriber mất message khi offline; consumer mới ACK trước khi DB commit; hoặc message bị chuyển sang DLQ do redelivery policy khác.

**Tiêu chí hoàn tất không phải broker mới mở cổng.** Tiêu chí là các contract được kiểm chứng trên broker đích, lưu lượng đã chuyển, backlog được đối soát và đội vận hành có một điểm quyết định rollback dựa trên dữ liệu.

~~~mermaid
flowchart LR
    A["Inventory + baseline"] --> B["Compatibility test"]
    B --> C["Migration rehearsal"]
    C --> D["Cutover gate"]
    D --> E["Canary / traffic switch"]
    E --> F{"Metrics + business checks pass?"}
    F -->|"Có"| G["Stabilize + close rollback window"]
    F -->|"Không, còn safe point"| R["Freeze target + rollback"]
    F -->|"Không, đã phát sinh state mới"| X["Reconcile / forward recovery"]
~~~

## 2. Xác định phạm vi và nguồn dữ liệu trước khi thử

Trước khi viết test, lập inventory theo **logical workload**, không chỉ theo tên broker:

| Nhóm | Cần thu thập |
|---|---|
| Producer | Ứng dụng, phiên bản client, protocol, destination, delivery mode, transaction, send timeout |
| Consumer | Ứng dụng, concurrency, prefetch/consumer window, ACK mode, selector, retry behavior |
| Destination | Queue/topic, address/queue binding, routing type, durable subscription, DLQ, expiry |
| Message contract | Body format/schema, property names/types, correlation ID, group ID, priority, timestamp, TTL |
| Reliability | Persistent/non-persistent, transaction, redelivery count/delay, duplicate handling, idempotency |
| Security | TLS trust/key material, authentication mechanism, roles/permissions, certificate rotation |
| Operations | Monitoring, alert thresholds, backup/restore, capacity, disk, restart and failover procedure |
| Topology | Broker URL, cluster/bridge/federation, DNS, load balancer, firewall and network path |

Tạo một **destination map** từ nguồn sang đích. Ví dụ:

| Logical workload | Source | Target | Contract |
|---|---|---|---|
| `billing.commands` | Classic Queue `billing.commands` | Artemis address + ANYCAST queue `billing.commands` | Competing consumers, transacted receive |
| `billing.events` | Classic Topic `billing.events` | Artemis MULTICAST address + subscriptions | Fan-out; subscriber offline cần durable |
| `billing.retry` | Classic retry destination/policy | Artemis retry address hoặc redelivery policy | Delay và attempt limit được chuẩn hóa |
| DLQ | `ActiveMQ.DLQ` hoặc individual DLQ | Artemis `DLQ` / per-address DLQ | Operator browse, classify, redrive |

Đây là mapping minh họa, không phải cấu hình tự động. Artemis address/queue và Classic physical destination có mô hình khác nhau. Với mỗi logical destination, ghi rõ ai tạo, loại routing, quyền gửi/nhận và nơi message hết hạn/DLQ.

### 2.1. Phân loại dữ liệu theo khả năng chuyển

- **Message pending:** chưa được consumer ACK; cần drain, bridge hoặc export/replay theo quy trình được kiểm chứng.
- **In-flight delivery:** đã dispatch nhưng chưa ACK; cần dừng consumer có trật tự hoặc rollback transaction để broker trả về pending.
- **Scheduled/delayed message:** cần kiểm tra cách broker đích biểu diễn lịch và thời điểm delivery.
- **Expired message:** không được vô tình hồi sinh khi replay; giữ expiration/deadline nghiệp vụ.
- **DLQ/poison message:** phải giữ dấu vết lỗi và quyết định có replay hay không.
- **Durable topic subscription backlog:** mỗi subscription có state riêng; phải chuyển và đối soát theo subscriber identity.
- **Temporary destination:** thường gắn với connection/session và không thể xem như queue durable có thể chuyển nguyên trạng.
- **Transactions đang mở:** phải hoàn tất hoặc rollback trước cutover; transaction state không được sao chép bằng cách đổi endpoint.

Không lấy một con số messageCount tổng làm inventory. Cần phân biệt pending, delivering, scheduled, expired, DLQ và backlog theo từng durable subscription.

## 3. Đặt compatibility contract và test matrix

### 3.1. Phân biệt chuẩn JMS với extension của provider

JMS định nghĩa các API/semantics portable như Queue/Topic, message headers, properties, selectors, delivery mode, acknowledgment và transaction session. Nhưng broker còn có extension riêng:

- ActiveMQ Classic có OpenWire, destination policy, virtual topics, individual DLQ strategy, advisory messages, network of brokers và các property/command riêng.
- Artemis có Core protocol, address/routing type, paging, address settings, broker plugins, federation/cluster và management attributes riêng.
- AMQP/OpenWire/Core không tự động có cùng behavior chỉ vì đều chở JMS message.
- Client failover URI, reconnect, redelivery policy và JNDI factory naming có cú pháp provider-specific.

Lập hai cột trong test report: **JMS contract portable** và **provider-specific behavior**. Nếu ứng dụng phụ thuộc extension, cần adapter/migration decision rõ ràng, không giả định broker đích có cùng tên cấu hình.

### 3.2. Test matrix tối thiểu

| Nhóm | Kịch bản | Assertion |
|---|---|---|
| Connect/security | TLS, credentials, authorization | Producer/consumer chỉ dùng quyền đã cấp; certificate đúng |
| Destination | Queue, topic, routing type, FQQN/physical name | Message đến đúng logical consumer group |
| Payload | Text/Bytes/Map/Object message, schema version | Body và encoding đọc đúng |
| Properties | String, numeric, boolean, correlation ID, reply-to | Tên, kiểu và giá trị không đổi ngoài mapping đã duyệt |
| Selector | IS NULL, IN, comparison, mixed types | Cùng tập message được chọn |
| Transactions | Send commit/rollback, receive commit/rollback | Message visibility và redelivery đúng contract |
| Acknowledgment | AUTO, CLIENT, transacted | Không ACK sớm hoặc ACK sai phạm vi |
| Retry/DLQ | N lần fail, delay, poison message | Attempt limit, DLQ route, metadata và operator flow |
| Ordering | Một consumer, nhiều consumer, message group | Ordering theo key đúng yêu cầu |
| Expiry/schedule | TTL, scheduled delivery, expiry queue | Deadline và thời điểm giao đúng |
| Durability | Persistent queue, durable subscription, restart | Backlog phục hồi theo failure model |
| Scale/failover | Consumer reconnect, broker restart, cluster route | Không mất hoặc nhân đôi business effect |
| Performance | Throughput, p95/p99, backlog drain | Đạt SLO với tải đại diện |

Mỗi test case cần có `testRunId`, business ID, broker/client version, destination, thời gian bắt đầu/kết thúc và kết quả ACK. Không dùng JMSMessageID làm business key vì ID thường được tạo lại khi replay.

### 3.3. So sánh kết quả theo contract, không so nội bộ provider

Ví dụ Classic và Artemis có thể biểu diễn delivery count hoặc DLQ metadata bằng provider-specific property khác nhau. Test không nên bắt hai broker có cùng tên attribute nội bộ. Thay vào đó, chuẩn hóa kết quả:

~~~text
logicalMessageId
destination
bodyHash
applicationProperties
correlationId
deliveryAttempt
redelivered
acknowledged
expired
deadLettered
businessEffectCount
~~~

Adapter test đọc provider metadata rồi ánh xạ sang record chuẩn của test harness. Chỉ so sánh những trường mà ứng dụng thực sự dựa vào. Các trường nội bộ khác được ghi riêng để điều tra.

## 4. Xây dựng bộ kiểm thử tương thích dùng chung

Một cách thực tế là định nghĩa test contract độc lập với factory cụ thể, sau đó chạy cùng scenario trên hai ConnectionFactory được cấu hình riêng. API package javax.jms hay jakarta.jms phải theo client library; không cố ép một class compile với hai namespace cùng lúc.

Ví dụ helper dưới đây dùng **Jakarta JMS** và có thể dùng với client Artemis Jakarta. Nếu nguồn Classic đang dùng javax.jms, tạo source set/adapter tương ứng hoặc nâng client Classic sang Jakarta-compatible version sau khi kiểm tra support matrix.

### 4.1. Gửi, nhận bằng selector và xác minh property

~~~java
import jakarta.jms.ConnectionFactory;
import jakarta.jms.JMSConsumer;
import jakarta.jms.JMSContext;
import jakarta.jms.Message;
import jakarta.jms.Queue;
import jakarta.jms.TextMessage;

import java.util.UUID;

public final class MessagingContractProbe {
    public static void verifySelectorAndPayload(ConnectionFactory factory)
            throws Exception {
        String testId = UUID.randomUUID().toString();
        String queueName = "migration.contract";
        String selector = "migrationTestId = '" + testId
                + "' AND schemaVersion = 2";

        try (JMSContext producer = factory.createContext(
                JMSContext.SESSION_TRANSACTED)) {
            Queue queue = producer.createQueue(queueName);
            TextMessage message =
                    producer.createTextMessage("{\"orderId\":\"O-42\"}");
            message.setStringProperty("migrationTestId", testId);
            message.setIntProperty("schemaVersion", 2);
            message.setStringProperty("eventType", "OrderCreated");

            producer.createProducer().send(queue, message);
            producer.commit();
        }

        try (JMSContext consumerContext = factory.createContext(
                JMSContext.SESSION_TRANSACTED)) {
            Queue queue = consumerContext.createQueue(queueName);
            JMSConsumer consumer =
                    consumerContext.createConsumer(queue, selector);
            consumerContext.start();

            Message received = consumer.receive(5_000L);
            if (received == null) {
                throw new AssertionError(
                        "No matching message for " + testId);
            }
            if (!(received instanceof TextMessage text)) {
                throw new AssertionError("Expected TextMessage");
            }
            if (!testId.equals(
                    received.getStringProperty("migrationTestId"))) {
                throw new AssertionError("Wrong migration test ID");
            }
            if (received.getIntProperty("schemaVersion") != 2) {
                throw new AssertionError("Property type/value changed");
            }
            if (!"{\"orderId\":\"O-42\"}".equals(text.getText())) {
                throw new AssertionError("Body changed");
            }

            consumerContext.commit();
            consumer.close();
        }
    }
}
~~~

Đây là **probe contract**, không phải test đầy đủ cho mọi behavior. Destination `migration.contract` phải được provision/auto-create có kiểm soát ở cả hai broker. Trong test song song, dùng destination namespace riêng hoặc marker selector như ví dụ; cleanup message/queue theo fixture. Nếu source/target dùng API namespace khác nhau, adapter của từng client phải expose cùng contract method.

### 4.2. Test rollback và redelivery

Cùng một scenario cần:

1. Gửi message với business ID duy nhất và commit.
2. Consumer transacted nhận message nhưng rollback.
3. Consumer mới nhận lại cùng business ID.
4. Xác minh redelivery flag/attempt metadata theo provider.
5. Commit message cuối cùng.
6. Lặp lại với lỗi vượt retry limit để xác minh DLQ.

Không bắt buộc hai broker có cùng delivery-count header; contract cần bảo đảm retry budget và poison handling có thể vận hành. Nếu ứng dụng đọc trực tiếp provider-specific header, test phải chứng minh mapping tương thích hoặc refactor qua adapter.

### 4.3. Test topic subscription offline

Đối với event fan-out:

- Tạo durable subscription với client ID và subscription name cố định.
- Đóng subscriber nhưng giữ subscription.
- Publish persistent event.
- Reconnect với cùng identity.
- Xác minh subscriber nhận event đã publish trong thời gian offline.
- Xóa subscription trong teardown.

Test riêng non-durable subscription để chứng minh event không được lưu cho subscriber offline. Không suy ra topic durability từ test queue.

## 5. Chuẩn bị rehearsal: môi trường đích phải giống production

Rehearsal là lần chạy migration trên bản sao cấu hình/dữ liệu có tính đại diện. Môi trường đích phải pin:

- Broker image/version/digest.
- Client artifact/version và protocol.
- TLS/authentication/authorization.
- Destination definitions, routing, selectors, address settings và DLQ.
- Persistence mode, journal/disk class và paging limits.
- Heap, memory, file descriptor, CPU, IOPS và network limits.
- Monitoring/alerts, backup/restore và operational access.

Dùng data copy hoặc message corpus được tạo lại từ fixture. **Không mount trực tiếp source broker store vào target broker** để thử: Classic KahaDB và Artemis journal không phải format tương thích; kể cả cùng broker family cũng cần quy trình upgrade/restore theo version.

### 5.1. Rehearsal với message corpus

Tạo corpus có phân tầng:

- Message thường, body nhỏ, property chuẩn.
- Message lớn và binary payload.
- Message có selector properties thiếu/NULL và nhiều kiểu.
- Priority, TTL, scheduled delivery.
- Message có correlation ID, reply-to, group ID.
- Message persistent/non-persistent.
- Poison message và message đã redeliver.
- Backlog queue và durable topic subscription.

Gắn `migrationBatchId`/businessId ổn định, lưu manifest gồm số lượng, body hash và expected destination. Khi chạy target, so sánh số lượng nhận, hash, property, thứ tự theo từng business key và trạng thái cuối cùng (ACK/DLQ/expired).

### 5.2. Đo baseline trước khi đổi

Trong cửa sổ tải đại diện, ghi:

| Chỉ số | Source baseline | Target rehearsal |
|---|---|---|
| Send success/error rate | Đo theo workload | So cùng corpus/tải |
| Receive/ACK throughput | Đo theo consumer group | So cùng concurrency |
| p95/p99 send-to-ack latency | Theo destination | So cùng SLO |
| Pending/oldest message age | Theo queue/subscription | Backlog drain |
| Redelivery/DLQ/expired | Theo logical workload | Không tăng bất thường |
| CPU/heap/direct memory | Theo node | Capacity headroom |
| Journal/paging disk I/O | Theo node | Disk latency/capacity |
| Reconnect/auth failures | Theo client | Phải trong ngưỡng |

So sánh cùng loại tải, cùng payload và cùng consumer concurrency. Không so một source đang idle với target đang replay backlog.

## 6. Chọn phương pháp chuyển lưu lượng

Không có một chiến lược duy nhất phù hợp mọi workload. Chọn theo khả năng dừng producer, cách chuyển backlog và yêu cầu ordering.

| Phương pháp | Khi phù hợp | Rủi ro chính |
|---|---|---|
| Stop-and-drain | Có maintenance window, queue có thể xử lý hết | Downtime phụ thuộc drain time |
| Freeze + export/replay | Cần chuyển backlog có đối soát | Cần công cụ giữ metadata/idempotency, có thể đổi order |
| Broker bridge/federation/network connector | Hai broker có interop được hỗ trợ và test kỹ | Mapping headers/ACK/transaction/loop, bridge lag |
| Partition/tenant canary | Workload có thể tách độc lập theo key/tenant | Cần single-owner cho từng partition |
| Dual-publish/dual-write | Chỉ khi downstream idempotent và có reconciliation | Duplicate, ordering race, partial commit |

### 6.1. Stop-and-drain là lựa chọn dễ kiểm soát

Quy trình tổng quát:

1. Ngừng nhận producer mới hoặc chuyển producer sang maintenance mode.
2. Đợi producer transaction đang mở commit/rollback.
3. Ngừng tạo consumer mới; cho consumer hiện hữu hoàn tất message đang xử lý.
4. Theo dõi delivering/in-flight về 0 hoặc xác định rõ delivery nào sẽ rollback.
5. Đợi source pending backlog về 0 nếu contract yêu cầu drain hoàn toàn.
6. Đối soát DLQ, expiry và durable subscriptions riêng.
7. Chuyển producer/consumer endpoint sang target.
8. Mở consumer trước hoặc theo thứ tự đã rehearsal; sau đó mở producer.
9. Gửi canary marker và xác nhận business effect/ACK.
10. Mở dần traffic còn lại.

Nếu backlog không thể drain trong maintenance window, phải chọn export/replay hoặc bridge có semantics đã được test. Không tuyên bố cutover zero-loss chỉ vì source queue count giảm.

### 6.2. Bridge/forwarding không phải bản sao store

Broker bridge có thể forward message qua protocol được hỗ trợ; nó không sao chép nguyên trạng mọi transaction, queue metadata, subscription state hoặc provider extension. Trước khi dùng, test:

- ACK nguồn xảy ra khi nào so với ACK đích?
- Broker đích nhận persistent delivery đúng không?
- Headers/properties, expiration, priority và group metadata được map thế nào?
- Bridge reconnect có thể resend message đã forward nhưng chưa ACK không?
- Có vòng lặp forwarding hoặc gửi ngược lại source không?
- Thứ tự per key có được giữ khi nhiều bridge/consumer chạy song song?
- DLQ/poison behavior ở source và target ai chịu trách nhiệm?

Giữ source message cho tới khi đích xác nhận theo contract của bridge; vẫn cần idempotency vì crash giữa hai broker có thể tạo duplicate.

### 6.3. Dual-publish phải có thiết kế idempotency

Gửi cùng event tới hai broker không tạo một transaction nguyên tử giữa hai hệ thống độc lập. Có thể xảy ra:

- Source nhận, target timeout.
- Target nhận, producer mất phản hồi.
- Cả hai nhận nhưng chỉ một bên ACK.
- Consumer cũ và mới cùng tạo side effect.
- Hai luồng hoàn tất khác thứ tự.

Nếu bắt buộc dual-publish, dùng transactional outbox với stable event ID, delivery state cho từng target, retry có giới hạn và consumer inbox/idempotency. Không dùng JMSMessageID làm event ID ổn định qua publish/replay.

## 7. Cutover gate: điều kiện trước khi đổi endpoint

Không bắt đầu cutover chỉ vì rehearsal “chạy được”. Chốt gate bằng checklist có người chịu trách nhiệm:

- [ ] Compatibility test pass cho tất cả critical destinations.
- [ ] Source và target version/client/protocol/config đã được ghi lại.
- [ ] Security/TLS/authorization đã test bằng user production-equivalent.
- [ ] Backup source có restore rehearsal thành công.
- [ ] Target persistence/volume/monitoring/alerts đã sẵn sàng.
- [ ] Destination map đã provision; queue/topic/routing/DLQ được xác minh.
- [ ] Producer/consumer config có thể đổi endpoint nhanh và đã thử rollback config.
- [ ] Backlog, delivering, scheduled, DLQ, expired và durable subscription đã inventory.
- [ ] Kế hoạch freeze/drain/export/replay có thời gian và owner cụ thể.
- [ ] Business IDs, duplicate detection và reconciliation dashboard đã hoạt động.
- [ ] Rollback trigger, decision owner và thời hạn rollback window đã được thống nhất.
- [ ] Không còn test client hoặc consumer probe đang đọc destination production.

**No-go** nếu thiếu bằng chứng về message inventory, target persistence, security hoặc khả năng khôi phục source. Trì hoãn cutover rẻ hơn xử lý mất/nhân đôi business transaction sau đó.
## 8. Thực hiện cutover theo một luồng ghi duy nhất

### 8.1. Trước giờ cutover

- Chốt change window, người ra quyết định và kênh liên lạc incident.
- Tắt auto-scaling/redeploy ngoài kế hoạch có thể làm consumer tự bật lại ở source.
- Xác nhận backup source, target health, secret/certificate và endpoint config đã sẵn sàng.
- Kiểm tra mọi producer/consumer instance đã nhận đúng config version.
- Ghi baseline queue counts, delivering count, oldest age, DLQ, expired, consumer count và business outbox/inbox watermark.
- Chuẩn bị cách **fence** source: dừng producer/consumer hoặc thu hồi quyền gửi/nhận sau khi drain; không chỉ đổi DNS trong khi client cũ vẫn kết nối.

### 8.2. Freeze, drain và đổi endpoint

Một lịch trình stop-and-drain mẫu:

| Pha | Hành động | Điều kiện qua pha |
|---|---|---|
| T-30 phút | Kiểm tra backup, config hash, destination map, alerts | Các owner xác nhận READY |
| T-10 phút | Ngừng producer nhận request mới; outbox tiếp tục giữ event | Không có producer mới phát vào source |
| T-8 phút | Chờ send transaction đang mở commit/rollback | Không còn producer transaction outcome unknown |
| T-5 phút | Ngừng nhận công việc mới ở consumer source; chờ xử lý in-flight | Delivering count về 0 hoặc đã rollback có kiểm soát |
| T-0 | Đối soát pending/DLQ/scheduled/expiry; drain/export theo runbook | Source inventory khớp manifest |
| T+ | Đổi connection factory/endpoint sang target; mở consumer đích | Target consumer registered và ready |
| T+5 | Mở producer theo canary; gửi marker batch | Target ACK và business effect đúng |
| T+10 | Tăng dần traffic nếu các gate đạt | Không có trigger rollback |
| T+N | Mở toàn bộ traffic; tiếp tục quan sát | Hết stabilization window |

Các mốc thời gian là ví dụ; rehearsal phải xác định thời lượng thực tế theo backlog và SLA.

**Single-writer rule:** tại một thời điểm, mỗi logical partition/tenant/destination chỉ có một bên được phép nhận writes từ producer nghiệp vụ. Nếu source và target cùng nhận cùng event, phải có dual-publish/outbox và idempotency được thiết kế riêng. Không để client failover URI trỏ lẫn hai broker độc lập rồi coi đó là load balancing.

### 8.3. Thứ tự mở consumer và producer

Với queue workload, thông thường:

1. Target broker đã có destination, security, persistence và consumer.
2. Consumer target kết nối nhưng chưa xử lý traffic ngoài canary.
3. Chuyển producer của partition canary sang target.
4. Xác nhận send, receive, DB effect và ACK.
5. Chuyển từng partition tiếp theo.
6. Chỉ mở source consumer trở lại nếu rollback đã được quyết định và target traffic đã bị fence.

Với topic, cần tạo durable subscriptions trên target **trước** khi publish các event cần subscriber nhận. Mở producer trước khi durable subscription sẵn sàng có thể tạo một khoảng trống không thể khôi phục cho subscriber offline.

### 8.4. Canary theo tenant hoặc partition

Chọn một lát cắt độc lập, ví dụ tenant `tenant-042` hoặc partition `accountHash mod N`. Giữ tất cả message của cùng business key đi cùng một broker trong suốt canary để không phá ordering.

Tăng traffic theo bước, ví dụ 1% → 5% → 25% → 50% → 100%, chỉ khi:

- Không có send/receive/auth error tăng bất thường.
- p95/p99 latency không vượt ngưỡng đã duyệt.
- Oldest message age và backlog drain nằm trong SLO.
- DLQ/redelivery/expired không tăng ngoài mức giải thích được.
- Không có duplicate business ID hoặc ordering violation.
- Consumer count, delivering count và ACK throughput phù hợp với số worker dự kiến.

Phần trăm chỉ là ví dụ. Nếu workload không partition được an toàn, dùng stop-and-drain thay vì canary ngẫu nhiên theo từng message.

## 9. Quan sát sau cutover: metrics phải gắn với business ID

### 9.1. Dashboard tối thiểu

| Lớp | Chỉ số | Dấu hiệu cần điều tra |
|---|---|---|
| Client | Connect/reconnect failures, auth failures | Client vẫn trỏ source hoặc credentials không hợp lệ |
| Producer | Send error, timeout, commit failure, p95/p99 | Broker chậm, transaction outcome unknown |
| Queue | Pending, delivering, oldest message age | Backlog không giảm hoặc message bị giữ in-flight |
| Consumer | Receive/ACK rate, handler error, processing latency | Consumer không xử lý hoặc ACK sớm |
| Reliability | Redelivery, delivery attempt, DLQ, expired | Policy khác source hoặc poison message tăng |
| Business | Unique IDs, duplicate effects, missing IDs, per-key sequence | Message đã tới nhưng business result sai |
| Runtime | Heap, direct memory, CPU, disk latency, journal/paging | Target thiếu capacity hoặc storage chậm |
| Topology | Cluster/bridge lag, connection state, route count | Forwarding không ổn định hoặc topology sai |

Đừng dùng enqueue/dequeue của mỗi broker để đối chiếu xuyên migration nếu định nghĩa metric provider khác nhau. Dùng manifest business ID và trạng thái ứng dụng để xác nhận message nào được gửi, nhận, commit và hoàn tất.

### 9.2. Ngưỡng cảnh báo phải lấy từ baseline

Ví dụ ngưỡng **minh họa**, cần thay bằng SLO và độ biến động của hệ thống:

- Send/receive error rate lớn hơn 0,5% trong 5 phút hoặc tăng rõ so với source baseline.
- p95 send-to-ACK lớn hơn 2 lần baseline trong 10 phút.
- Oldest message age vượt SLO của destination.
- DLQ/expired tăng đột ngột hoặc xuất hiện business event critical.
- Duplicate business effect lớn hơn 0.
- Per-key ordering violation lớn hơn 0 nếu ordering là contract bắt buộc.
- Target disk/heap vượt ngưỡng capacity đã đặt; journal write latency kéo dài.
- Bridge lag không giảm hoặc source pending không được drain theo tiến độ.

Không dùng các con số này như default của ActiveMQ. Chốt threshold trước change window để người trực không tranh luận cách đo khi incident xảy ra.

### 9.3. Canary marker và reconciliation

Mỗi canary batch có manifest:

~~~text
migrationId: MIG-2026-11-17-A
partition: tenant-042
expectedMessages: 500
businessIds: [evt-0001 ... evt-0500]
expectedDestination: billing.commands
bodyHashAlgorithm: SHA-256
~~~

Đối chiếu:

- Tất cả ID trong manifest có trạng thái terminal mong đợi?
- Không có ID ngoài manifest bị consumer canary lấy?
- Body hash và critical properties có khớp?
- Có ID nào vừa được xử lý ở source lẫn target?
- Có business effect nào thiếu hoặc lặp trong DB?
- DLQ/expiry có ID nào cần operator review?

Với throughput cao, không log toàn bộ payload; dùng ID/hash/metadata có kiểm soát và lưu kết quả đối soát ở nơi có retention/audit phù hợp.

## 10. Xác định rollback point trước khi traffic chuyển

Rollback phải được định nghĩa **trước** cutover. Endpoint có thể đổi lại nhanh, nhưng message và business side effects đã tạo ở target không tự quay về source.

### 10.1. Ba trạng thái rollback

| Trạng thái | Điều đã xảy ra | Hành động phù hợp |
|---|---|---|
| **R0 — Trước target write** | Producer vẫn chỉ ghi source; target chưa nhận business message | Đổi config về source, kiểm tra client reconnect; rollback đơn giản nhất |
| **R1 — Target đã nhận, chưa xử lý business** | Target có pending messages nhưng chưa có consumer commit side effect | Freeze target, inventory và export/replay về source theo manifest; sau đó đổi endpoint |
| **R2 — Target đã xử lý business** | Consumer target đã commit DB/API side effect hoặc phát event downstream | Không chỉ flip endpoint. Reconcile business IDs, fence consumer, dedupe/compensate hoặc forward-recover |

**Rollback point đơn giản kết thúc khi target bắt đầu tạo side effect nghiệp vụ không thể đảo nguyên tử.** Nếu target đã nhận message nhưng chưa xử lý, vẫn có thể quay lại bằng quy trình export/replay có đối soát; không được bỏ lại message trong target rồi bật source consumer và tuyên bố hoàn tất.

### 10.2. Ranh giới quyết định rollback

Đặt checkpoint rõ ràng:

- **Checkpoint A — trước producer switch:** source là owner duy nhất; có thể rollback config.
- **Checkpoint B — target nhận canary nhưng chưa business commit:** có thể freeze, chuyển pending message về source và rollback nếu công cụ replay đã rehearsal.
- **Checkpoint C — target consumer đã commit business effect:** cần reconciliation; quyết định có rollback hay forward recovery dựa trên DB/outbox/inbox state, không dựa riêng broker queue depth.
- **Checkpoint D — mở toàn bộ traffic và hết stabilization window:** đóng rollback window; mọi thay đổi sau đó đi theo incident/DR plan.

Định nghĩa ai ký qua checkpoint, số liệu nào phải chụp và thời điểm nào source bị fence. Giữ source process chạy nhưng cấm nhận writes/consumes có thể hữu ích cho điều tra; không để source và target cùng xử lý một partition.

### 10.3. Quy tắc không thể bỏ qua

- Một partition chỉ có một broker owner tại một thời điểm.
- Freeze producer trước khi chuyển message pending.
- Chờ hoặc rollback in-flight transaction trước khi export.
- Giữ stable business ID khi replay.
- Không phát lại expired message nếu deadline nghiệp vụ đã qua.
- Không dùng broker queue count làm bằng chứng business transaction đã commit.
- Giữ source data và backup trong toàn bộ rollback window.
## 11. Runbook rollback theo trạng thái

### 11.1. Rollback ở R0: target chưa nhận message

1. Dừng producer rollout/canary.
2. Đưa endpoint/config về source version đã lưu.
3. Restart/reconnect client theo cơ chế thực tế; xác minh không còn connection tới target.
4. Mở source consumer và producer.
5. Gửi canary marker mới; xác minh business effect và ACK.
6. Giữ target để điều tra; không xóa volume hoặc log.

### 11.2. Rollback ở R1: target có pending nhưng chưa xử lý

1. **Fence target:** dừng producer và consumer target; chờ in-flight về 0 hoặc rollback session chưa commit.
2. Chụp inventory target: pending, delivering, scheduled, expired, DLQ và durable subscriptions.
3. Xuất/replay pending theo công cụ đã rehearsal, giữ stable business ID, body, critical properties, expiration và ordering key.
4. Gửi vào source trong khi source consumers vẫn dừng.
5. Đối chiếu manifest source sau replay; xác nhận không mất/nhân đôi ID.
6. Đổi endpoint về source, mở consumer, sau đó mới mở producer.
7. Theo dõi duplicate/idempotency và oldest message age.

Không copy file journal/KahaDB từ target sang source. Chuyển message bằng bridge/export/import/replay được hỗ trợ, hoặc khôi phục snapshot đúng broker family/version nếu kịch bản đó đã được thiết kế.

### 11.3. Rollback ở R2: target đã tạo business effects

1. Dừng producer mới và fence consumer target để không phát sinh thêm side effect.
2. Chụp target pending/delivering/DLQ và business outbox/inbox/processed ledger.
3. Đối soát từng stable business ID: chưa nhận, đang xử lý, DB commit, downstream event đã phát, đã ACK.
4. Chọn một hướng:
   - **Forward recovery:** sửa lỗi target và tiếp tục xử lý ở target; thường ít rủi ro hơn khi target đã ghi state.
   - **Compensating action:** hoàn tác nghiệp vụ bằng giao dịch bù có audit nếu business cho phép.
   - **Controlled reverse migration:** replay các ID chưa hoàn tất về source, dedupe ID đã xử lý và giữ ordering theo key.
5. Chỉ mở source consumers sau khi có owner duy nhất cho từng partition và reconciliation pass.
6. Kiểm tra downstream consumers không tiếp tục xử lý bản sao cũ.

Không dùng thao tác purge để làm queue count về 0. Không xóa target data vì có thể cần đối soát hoặc khôi phục.

## 12. Các điều kiện bắt buộc để rollback có thể thực hiện

- Stable business ID tồn tại trước khi publish và không đổi khi retry/replay.
- Consumer inbox/idempotency key ngăn side effect trùng.
- Transactional outbox hoặc delivery ledger cho producer cần phát lại.
- Có thể inventory pending, in-flight, scheduled, DLQ và durable subscription backlog.
- Có đường chuyển message được hỗ trợ, đã test preservation của body/properties/expiration.
- Có cơ chế fence source/target để không có hai consumer group cùng sở hữu partition.
- Có manifest gửi/nhận/ACK/DB commit để reconcile.
- Source store và backup vẫn được giữ nguyên trong rollback window.
- Có decision owner và giới hạn thời gian cho mỗi trạng thái R0/R1/R2.

Nếu thiếu stable business ID hoặc không thể phân biệt message đã tạo business effect, rollback sau R2 có thể gây duplicate hoặc mất giao dịch. Khi đó nên giữ hệ thống ở trạng thái freeze và thực hiện reconciliation có kiểm soát trước khi bật lại traffic.

## 13. Ví dụ cấu hình endpoint có version để rollback

Đừng sửa tay từng pod trong change window. Đưa endpoint vào config version hóa, triển khai đồng nhất và lưu bản trước/sau:

~~~yaml
# application-messaging.yaml — ví dụ cấu hình do ứng dụng đọc
messaging:
  broker:
    url: tcp://artemis-target.internal:61616
    client-id: billing-worker
    connect-timeout: 5000
    reconnect:
      enabled: true
  destinations:
    commands: billing.commands
    events: billing.events
~~~

Source config trước migration có thể trỏ tới Classic endpoint. Đổi endpoint không tự đổi semantics destination hoặc client library; artifact client và destination adapter phải được triển khai phù hợp. Nếu cần quay lại Classic javax.jms, đó có thể là một release ứng dụng khác, không chỉ đổi URL.

Một release record nên giữ:

~~~text
migrationId: MIG-2026-11-17-A
sourceBroker: classic-prod-a
sourceConfigVersion: billing-messaging-v41
targetBroker: artemis-prod-a
targetConfigVersion: billing-messaging-v42
clientArtifact: artemis-jakarta-client:<approved-version>
trafficOwner: tenant-042
rollbackState: R1
decisionOwner: on-call-messaging-lead
~~~

Các giá trị là ví dụ. Không ghi password, token, private key hoặc connection string chứa credential vào release record.

## 14. Rehearsal rollback: phải thử cả đường quay lại

Một migration rehearsal chỉ thử forward cutover là chưa đủ. Chạy ít nhất các kịch bản:

1. **R0:** target chưa nhận message; đổi endpoint về source và xác minh client reconnect.
2. **R1:** target có pending message; freeze, export/replay, đối chiếu business ID rồi quay về source.
3. **R2:** target đã commit một phần business effect; thử reconciliation/inbox dedupe và chứng minh không phát sinh side effect lần hai.
4. **Bridge failure:** mất kết nối giữa forward và ACK; kiểm tra duplicate/retry.
5. **Client stale config:** một số instance chưa nhận config mới; xác minh fencing chặn source/target split ownership.
6. **Topic offline:** durable subscriber backlog ở source/target; kiểm tra subscriber identity và không bỏ sót event.
7. **Expiry/DLQ:** message gần hết TTL hoặc poison message; replay không được làm message hết hạn sống lại ngoài ý muốn.
8. **Ordering:** cùng business key qua canary/replay; xác minh sequence theo contract.

Ghi thời gian thực hiện từng bước, số ID được chuyển, số duplicate được phát hiện, điểm cần operator can thiệp và RTO đạt được. Nếu rollback không hoàn thành trong RTO, phải thay chiến lược hoặc giảm phạm vi cutover.

## 15. Decision log và báo cáo sau cutover

Mỗi checkpoint ghi:

~~~text
migrationId:
timestamp:
sourceConfigVersion:
targetConfigVersion:
trafficPercent:
sourcePending / sourceDelivering:
targetPending / targetDelivering:
sourceDLQ / targetDLQ:
oldestMessageAge:
sendErrorRate:
receiveAckRate:
p95 / p99 latency:
duplicateBusinessIds:
missingBusinessIds:
orderingViolations:
decision: CONTINUE | HOLD | ROLLBACK | FORWARD_RECOVERY
decisionOwner:
evidenceLink:
~~~

Sau stabilization window:

- Xác nhận source không còn producer/consumer cũ và không còn backlog chưa phân loại.
- Giữ source data/backup theo retention và audit policy; không xóa ngay sau cutover.
- Chốt target SLO, alert, capacity và backup/restore runbook.
- Cập nhật service discovery, credential rotation và access policy.
- Ghi các extension Classic còn phụ thuộc hoặc Artemis-specific behavior đã chấp nhận.
- Đóng rollback window bằng quyết định có audit; sau mốc này dùng DR/incident process.

## 16. Lỗi migration thường gặp

| Lỗi | Hậu quả | Cách phòng tránh |
|---|---|---|
| Chỉ test connect/send | Mất selector, transaction, DLQ hoặc durable subscription semantics | Contract matrix trên cả hai broker |
| Copy KahaDB sang Artemis journal | Store không tương thích, broker không đọc được | Export/replay hoặc bridge đã kiểm chứng |
| Cùng một queue nhận writes từ hai broker | Duplicate và ordering race | Single-writer theo partition |
| Dùng JMSMessageID làm migration key | ID thay đổi khi replay | Stable business ID/outbox |
| Bật target consumer trước khi target subscription sẵn sàng | Event có thể mất với subscriber offline | Provision durable subscription trước producer |
| Chỉ nhìn queue count | Không phát hiện in-flight, DLQ, expired hoặc business duplicate | Manifest ID + delivery/ACK + DB reconciliation |
| Flip endpoint sau khi target đã commit side effect | Source có thể xử lý lại cùng business event | R2 reconciliation/forward recovery |
| Không giữ source backup | Không thể khôi phục trạng thái trước cutover | Backup và restore rehearsal |
| Bridge không test crash window | Forward thành công nhưng source ACK chưa rõ, tạo duplicate | Test bridge reconnect và idempotency |
| DNS switch nhưng client connection cũ còn sống | Hai broker cùng nhận traffic | Explicit client rollout/fencing, kiểm tra connection inventory |

## 17. Checklist chốt migration

- [ ] Destination map và message contract đã được review?
- [ ] Client/protocol/provider-specific extension đã có compatibility decision?
- [ ] Test corpus bao phủ headers, properties, selectors, transactions, DLQ, TTL, ordering và durable subscriptions?
- [ ] Rehearsal chạy với version/config/capacity gần production?
- [ ] Baseline SLO và rollback thresholds được chốt trước change window?
- [ ] Source backup đã restore thử?
- [ ] Pending, in-flight, scheduled, expired, DLQ và durable subscription backlog đã inventory?
- [ ] Single-writer/fencing theo partition đã được kiểm tra?
- [ ] Canary xác nhận cả broker ACK lẫn business effect?
- [ ] Stable business ID, inbox/outbox và reconciliation hoạt động?
- [ ] R0/R1/R2 rollback đã rehearsal, bao gồm replay và R2 compensation/forward recovery?
- [ ] Decision owner, checkpoint, rollback window và RTO được ghi lại?
- [ ] Source data được giữ tới khi migration được chấp nhận chính thức?

## 18. Kết luận

Chuyển lưu lượng giữa ActiveMQ Classic và Artemis cần được điều khiển bằng **contract test, rehearsal, inventory và business reconciliation**. JMS API giúp giữ một phần semantics portable, nhưng protocol, address/routing, durable subscription, redelivery, DLQ và management behavior vẫn có khác biệt provider. Không copy store giữa hai broker family; hãy drain, bridge hoặc export/replay bằng phương thức đã kiểm chứng.

Điểm rollback quan trọng nhất là thời điểm target bắt đầu commit business side effect. Trước đó, có thể freeze target, chuyển pending messages về source và đổi endpoint theo manifest. Sau đó, chỉ flip URL là không đủ: phải reconcile stable business IDs, dedupe, compensate hoặc forward-recover. Mỗi partition cần một owner duy nhất, mỗi message cần ID nghiệp vụ ổn định, và mỗi quyết định cutover phải có metrics cùng bằng chứng.

Một migration chỉ nên được coi là ổn định khi target xử lý đúng contract dưới tải thực tế, backlog và side effect được đối soát, source đã được fence, backup/restore sẵn sàng và rollback window được đóng bằng quyết định có audit.
