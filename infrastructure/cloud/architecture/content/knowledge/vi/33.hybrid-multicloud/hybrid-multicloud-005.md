# Đồng bộ dữ liệu và vận hành khi kết nối bị gián đoạn

## 1. Vì sao đồng bộ dữ liệu là thách thức của hybrid và multi-cloud?

Kiến trúc hybrid kết hợp hạ tầng tại chỗ với cloud; kiến trúc multi-cloud phân bổ workload hoặc dữ liệu trên nhiều cloud provider hay region. Các môi trường kết nối qua VPN, private link, dedicated circuit hoặc internet. Kết nối có thể chậm, mất gói, gián đoạn theo vùng, bị giới hạn băng thông hoặc bị cắt hoàn toàn.

Khi kết nối ổn định, hệ thống đồng bộ database, object, event, file và identity theo lịch hoặc theo luồng liên tục. Khi link bị gián đoạn, một phía có thể vẫn tiếp nhận giao dịch trong khi phía còn lại không nhận được thay đổi. Hai bên có thể phát sinh dữ liệu khác nhau; message có thể bị giữ lại, giao lặp hoặc đến sai thứ tự; replication lag tăng; ứng dụng có thể không biết giao dịch trước đó đã được commit ở remote hay chưa.

Thiết kế tốt phải trả lời: dữ liệu nào cần đồng bộ; hệ thống nào là source of truth; workload nào tiếp tục hoạt động khi link mất; có thể chấp nhận mất hoặc chậm dữ liệu bao lâu; nếu hai nơi cùng ghi thì giải quyết xung đột thế nào; khi kết nối lại thì replay theo thứ tự nào và tránh side effect lặp ra sao.

Trong module CLOUD_ARCHITECTURE, các quyết định này liên kết network, database, storage, event architecture, identity, disaster recovery và operations. Mục tiêu là cân bằng độ tin cậy, bảo mật, khả năng mở rộng, hiệu năng, chi phí và khả năng vận hành trong điều kiện phân tán.

Ví dụ xuyên suốt: nền tảng đặt chỗ có control plane trên cloud và hệ thống tại khách sạn. Site khách sạn cần tiếp tục check-in và cập nhật trạng thái phòng khi đường truyền cloud mất. Cloud vẫn phục vụ tìm kiếm toàn hệ thống, nhưng dữ liệu của site có thể cũ. Khi kết nối lại, hai phía phải hợp nhất thay đổi mà không tạo booking trùng hoặc ghi đè trạng thái sai.

## 2. Phân loại dữ liệu trước khi chọn cơ chế đồng bộ

Không nên dùng một giải pháp replication cho mọi loại dữ liệu. Mỗi loại có đặc điểm khác nhau về quyền ghi, consistency, kích thước, độ nhạy cảm và khả năng tái tạo.

| Loại dữ liệu | Đặc tính | Câu hỏi thiết kế |
| --- | --- | --- |
| Transactional records | Booking, payment, inventory, ledger | Nguồn ghi có thẩm quyền ở đâu? Có cần tránh double booking? |
| Reference/master data | Property, room type, product catalog, policy | Ai được cập nhật? Replica có thể stale bao lâu? |
| Operational events | Check-in, cancellation, status change | Ordering, duplicate và replay xử lý thế nào? |
| Read models/projections | Search index, dashboard, materialized view | Có thể rebuild từ source/event log không? |
| Files/objects | Ảnh, hóa đơn, export, document | Versioning, checksum, delete marker và metadata ra sao? |
| Configuration/secrets | Runtime config, certificate, key reference | Ai phân phối? Có cần đồng bộ secret thật không? |
| Telemetry | Metrics, logs, traces | Có thể buffer và gửi sau? Retention/egress được kiểm soát không? |

### 2.1. Xác định ownership và write authority

Với mỗi aggregate hoặc loại dữ liệu, ghi rõ owner system; nơi được phép ghi; các replica/read-only consumer; field có thể được sửa ở edge/local site; quy tắc chuyển ownership khi failover; điều kiện và quyền phê duyệt khi thay đổi authority.

Một nguyên tắc an toàn là tránh để nhiều nơi cùng ghi dữ liệu quan trọng nếu chưa có thuật toán giải quyết conflict được chứng minh. Có thể phân vùng ownership theo tenant, property, region hoặc aggregate để mỗi đối tượng chỉ có một writer tại một thời điểm.

## 3. Các mức consistency và lựa chọn theo nghiệp vụ

| Mô hình | Đặc điểm | Ví dụ phù hợp |
| --- | --- | --- |
| Strong/linearizable consistency | Reader quan sát thay đổi theo thứ tự toàn cục được bảo đảm | Ledger hoặc thao tác cần thứ tự nghiêm ngặt |
| Read-your-writes | Người ghi nhìn thấy thay đổi của chính mình | Nhân viên vừa đổi trạng thái phòng |
| Monotonic reads | Reader không quay lại trạng thái cũ hơn đã thấy | Màn hình vận hành |
| Eventual consistency | Khi không có cập nhật mới và đồng bộ tiếp tục, replica dần hội tụ | Search index, analytics projection |
| Bounded staleness | Replica có thể cũ nhưng nằm trong giới hạn xác định | Catalog/dashboard chấp nhận trễ vài phút |

Không có một mức consistency phù hợp cho toàn ứng dụng. Có thể dùng consistency mạnh cho thao tác giữ phòng tại authoritative service, read-your-writes cho UI ở site, và eventual consistency cho search/analytics.

Strong consistency giữa các site thường cần round-trip hoặc quorum/coordinator qua network. Khi link có latency cao hoặc bị partition, write có thể chậm hoặc không thể commit nếu hệ thống phải bảo đảm thứ tự nhất quán. Nếu nghiệp vụ buộc tiếp tục hoạt động khi partition, cần xác định dữ liệu nào cho phép local authority, phần nào chuyển sang pending state và phần nào phải từ chối.

## 4. Các chiến lược đồng bộ dữ liệu

| Chiến lược | Cách hoạt động | Điểm mạnh | Hạn chế |
| --- | --- | --- | --- |
| Synchronous replication | Giao dịch chờ xác nhận từ replica theo cơ chế hệ thống | RPO có thể rất thấp trong failure model xác định | Nhạy với latency/link outage |
| Asynchronous replication | Primary commit rồi gửi thay đổi sau | Giảm latency commit, chịu link chập chờn tốt hơn | Replica lag; failover có thể mất write chưa replicate |
| Periodic batch sync | Đồng bộ theo lịch hoặc batch | Đơn giản, kiểm soát cửa sổ và tải | Dữ liệu stale giữa các lần chạy |
| Change Data Capture (CDC) | Đọc transaction log/change stream rồi truyền thay đổi | Gần thời gian thực, giữ thứ tự trong phạm vi nguồn/partition | Cần quản lý offset, schema, retention và replay |
| Event-driven sync | Domain event được publish và consumer áp dụng | Tách producer/consumer, mở rộng theo event | Cần schema evolution, idempotency, ordering |
| File/object replication | Copy object/version giữa vùng lưu trữ | Hợp với file lớn và binary | Conflict/delete/metadata có semantics riêng |
| Store-and-forward | Ghi local durable queue/store rồi gửi khi link hoạt động | Tiếp tục nhận việc offline | Backlog, disk capacity và reconciliation phức tạp |

### 4.1. Synchronous replication

Trong đồng bộ đồng bộ, primary có thể chỉ trả thành công sau khi replica xác nhận theo quorum hoặc durability mechanism của database. Điều này giảm cửa sổ mất dữ liệu trong một số failure scenario nhưng tăng độ nhạy với network. Cần hiểu “đã xác nhận” nghĩa là replica đã nhận log, ghi bền vững hay đã commit transaction; semantics khác nhau theo database và topology.

### 4.2. Asynchronous replication

Primary trả kết quả trước, replication chạy phía sau. Ứng dụng ít phụ thuộc latency liên vùng hơn nhưng cần đo lag và xác định RPO. Nếu primary mất trước khi log được gửi/áp dụng, transaction đã ack có thể chưa có trên replica. Theo dõi lag theo thời gian/byte/log sequence, commit timestamp so với apply timestamp, backlog, lỗi xác thực/network/schema và khả năng catch-up.

### 4.3. Batch sync

Batch phù hợp khi dữ liệu có thể trễ và thay đổi có thể gom nhóm. Job cần checkpoint, watermark, checksum, retry và xử lý record update/delete. Một batch chạy lại phải idempotent. Batch mỗi giờ không có nghĩa dữ liệu chỉ cũ tối đa một giờ: thời gian chạy, retry, backlog và outage đều cộng vào độ trễ thực tế.

## 5. Kiến trúc store-and-forward khi mất kết nối

Store-and-forward cho phép site tiếp tục ghi công việc vào local durable storage/queue; đồng bộ tới cloud khi link trở lại.

~~~mermaid
flowchart LR
    APP["Local application"] --> DB["Local durable DB"]
    DB --> OUTBOX["Outbox / local event log"]
    OUTBOX --> Q["Forwarder queue"]
    Q --> LINK["VPN / private link / internet"]
    LINK --> CLOUD["Cloud ingestion API"]
    CLOUD --> CENTRAL["Central event store / DB"]
    CLOUD -.->|"ack / checkpoint"| Q
~~~

Local write phải bền vững trước khi báo thành công nếu nghiệp vụ yêu cầu. Outbox nên được ghi cùng transaction với dữ liệu nghiệp vụ để tránh commit record nhưng mất event. Forwarder gửi theo batch có giới hạn và backpressure. Mỗi message cần ID duy nhất, source, aggregate key, version, occurredAt và schema version. Cloud trả ack/checkpoint rõ để local chỉ đánh dấu delivered sau khi xác nhận hợp lệ. Retry có exponential backoff và jitter; poison message không được retry vô hạn. Queue local cần quota, disk threshold, retention và cảnh báo.

### 5.1. Transactional outbox

Nếu application commit booking vào database rồi mới gọi broker, process có thể chết giữa hai bước. Database đã có booking nhưng event không được phát. Transactional outbox ghi event vào bảng outbox trong cùng transaction; publisher đọc và gửi sau. Outbox giải quyết atomicity giữa business state và event intent trong một database transaction. Nó không tự bảo đảm broker chỉ nhận một lần; publisher có thể gửi lại khi ack bị mất, vì vậy consumer vẫn phải idempotent.

## 6. Change Data Capture và đồng bộ từ database hiện hữu

CDC đọc thay đổi từ transaction log hoặc change stream thay vì polling toàn bộ bảng. Dữ liệu thay đổi được gửi tới stream/target để xây replica, search index hoặc data warehouse.

Một pipeline CDC cần source database và log retention đủ cho consumer catch-up; connector đọc log theo vị trí/offset; schema registry hoặc contract; broker buffer khi target hoặc network tạm lỗi; consumer áp thay đổi idempotently và quản lý offset; reconciliation so sánh source/target.

### 6.1. Snapshot và incremental changes

Bootstrap thường cần snapshot dữ liệu hiện tại, sau đó áp phần log phát sinh từ một watermark tương ứng. Nếu snapshot và log boundary không khớp, có thể bỏ sót hoặc áp trùng thay đổi. Ghi nhận snapshot timestamp/consistent point, log position/offset bắt đầu, checkpoint consumer, schema version và cách xử lý delete/tombstone; kiểm thử resume khi connector restart.

### 6.2. Schema evolution

Source thêm/đổi field có thể khiến connector hoặc consumer lỗi. Dùng quy tắc backward/forward compatibility, version hóa schema và triển khai consumer có khả năng xử lý giai đoạn chuyển tiếp. Không xóa field khỏi source trước khi mọi consumer đã chuyển.

## 7. Conflict resolution khi nhiều phía cùng thay đổi

Conflict xảy ra khi hai replica sửa cùng một logical object trước khi đồng bộ. Ví dụ tại khách sạn, nhân viên A đánh dấu phòng đã dọn; cloud đồng thời nhận cập nhật từ housekeeping integration. Hoặc hai site sửa cùng booking lúc WAN bị mất.

| Chiến lược | Quy tắc | Phù hợp | Rủi ro |
| --- | --- | --- | --- |
| Single-writer ownership | Mỗi aggregate chỉ có một writer có thẩm quyền | Booking/payment/inventory quan trọng | Cần xử lý khi owner offline |
| Last-write-wins | Chọn phiên bản có timestamp mới hơn | Preference ít quan trọng | Clock skew có thể chọn sai; mất cập nhật |
| Version/CAS | Chỉ ghi nếu version hiện tại khớp | Tránh ghi đè concurrent update | Conflict phải được xử lý |
| Field-level merge | Merge field độc lập | Profile/metadata có field ownership rõ | Không an toàn khi field có invariant liên quan |
| CRDT | Cấu trúc có phép merge bảo đảm hội tụ | Một số counter/set phù hợp | Không áp dụng tự nhiên cho mọi domain |
| Manual/business resolution | Đưa conflict vào hàng chờ | Payment/booking có tác động tài chính | Cần nhân sự và SLA |

Last-write-wins không đơn giản là lấy timestamp lớn nhất. Đồng hồ hai site có thể lệch; timestamp client không đáng tin; thời gian phát sinh và thời gian nhận khác nhau. Nếu sử dụng, cần nguồn thời gian, tie-breaker ổn định và đánh giá nguy cơ mất update. Với dữ liệu quan trọng, version hoặc explicit ownership thường dễ giải thích hơn.

Version/ETag/aggregate version giúp phát hiện hai thay đổi dựa trên cùng một phiên bản cũ. Khi version không khớp, server trả conflict để caller đọc lại, merge hoặc yêu cầu quyết định nghiệp vụ. Version vector hoặc causal metadata có thể thể hiện quan hệ nhân quả nhưng tăng độ phức tạp.

Ví dụ booking B đang CONFIRMED, version 10. Site offline nhận yêu cầu hủy; cloud nhận payment capture đồng thời. Không thể chỉ chọn timestamp mới hơn mà bỏ qua invariant: có được hủy khi payment đã capture, có cần refund/void, inventory đã giải phóng chưa, khách đã nhận xác nhận chưa? State machine và command validation phải là nguồn quy tắc.

## 8. Idempotency, duplicate delivery và ordering

Khi link mất sau khi receiver đã xử lý nhưng trước khi sender nhận ack, sender không biết message đã commit hay chưa. Retry có thể gửi lại message. Vì vậy nên giả định at-least-once delivery trừ khi nền tảng chứng minh semantics khác.

- Gắn event/message ID ổn định qua các lần retry.
- Consumer lưu inbox/dedup key cùng business state trong transaction phù hợp.
- Side effect ngoài dùng idempotency key nếu provider hỗ trợ.
- Aggregate version ngăn event cũ ghi đè trạng thái mới.
- Partition theo aggregate khi cần ordering trong phạm vi đó.
- Poison message vào dead-letter/quarantine kèm alert và công cụ replay.
- Replay theo batch có rate limit để không quá tải khi reconnect.

Không tuyên bố exactly-once chỉ vì broker có tính năng này. Phải xét transaction từ producer, broker, consumer tới database và external side effect.

## 9. Vận hành khi network partition

Partition không chỉ là link down hoàn toàn. Có thể một chiều hoạt động, chiều còn lại bị chặn; latency tăng và request timeout; packet loss; DNS/control plane không truy cập được; VPN tunnel flap; băng thông bị chiếm bởi bulk sync hoặc retry storm.

### 9.1. Chọn degraded mode theo capability

| Capability | Khi mất kết nối | Điều kiện bảo vệ |
| --- | --- | --- |
| Search | Phục vụ cache/index local có nhãn freshness hoặc từ chối filter cần dữ liệu mới | Không trình bày stale như real-time |
| Check-in | Cho phép local trong quota/ownership đã xác định | Durable local log, idempotency, reconciliation |
| Booking mới | Queue pending hoặc chỉ cho phép trong inventory được phân quyền | Tránh oversell/double booking |
| Payment | Hiển thị pending/unknown hoặc dùng provider fallback được duyệt | Không coi timeout là failed rồi thu tiền lại |
| Notification | Queue local và gửi lại sau | Dedup, expiry, provider rate limit |
| Analytics | Hoãn đồng bộ/báo cáo | Theo dõi freshness |
| Identity | Dùng token/cache credential còn hiệu lực | Không mở quyền khi không thể xác minh |

Degraded mode phải được thiết kế trước. Không phải mọi nghiệp vụ đều nên tiếp tục ghi local; đôi khi fail-closed là lựa chọn an toàn.

### 9.2. Timeout, retry và circuit breaker

Timeout phải phù hợp latency budget. Retry chỉ cho lỗi tạm thời và thao tác idempotent/được bảo vệ. Exponential backoff và jitter giảm retry đồng loạt. Circuit breaker tạm ngừng gọi dependency lỗi để bảo vệ thread/connection. Queue có giới hạn và backpressure khi receiver chậm. Fallback phải giữ invariant và công bố mức stale/degraded phù hợp.

Retry ngay lập tức khi link down có thể làm bão hòa WAN và dịch vụ khi kết nối vừa hồi phục. Phân biệt retry traffic với new traffic.

## 10. Reconnect và catch-up sau khi kết nối trở lại

Kết nối được phục hồi không có nghĩa dữ liệu lập tức nhất quán. Có thể còn queue backlog, replication lag, schema mismatch hoặc credential hết hạn.

~~~mermaid
flowchart TD
    A["Link restored"] --> B["Authenticate and validate channel"]
    B --> C["Measure lag, backlog and capacity"]
    C --> D["Resume from durable checkpoint"]
    D --> E["Replay with rate limit and idempotency"]
    E --> F["Detect duplicates and conflicts"]
    F --> G["Reconcile source and target"]
    G --> H{"Integrity and lag acceptable?"}
    H -->|No| C
    H -->|Yes| I["Restore normal traffic"]
~~~

Trình tự reconnect: xác thực tunnel/certificate/identity/route; kiểm tra schema compatibility; đo lag, queue depth, oldest message age và disk; xác định write authority; resume từ checkpoint durable; drain backlog có rate limit; xử lý duplicate/out-of-order/conflict; reconcile bằng count/checksum/version/business invariant; xác nhận SLO/freshness trước khi tắt degraded mode; lưu số liệu outage.

Nếu backlog tích lũy 5 triệu event, gửi đồng loạt có thể làm ingestion, database và downstream consumer bão hòa. Tốc độ drain phải xét capacity receiver, traffic mới, thứ tự ưu tiên, rate limit provider, retention log và egress quota. Cần dành capacity cho live traffic và backlog; nếu receiver không xử lý nhanh hơn tốc độ tạo backlog, phải tăng capacity hoặc giảm workload phát sinh event.

## 11. RPO, RTO và freshness trong đồng bộ hybrid

RPO là mức mất dữ liệu theo thời gian mà nghiệp vụ chấp nhận trong kịch bản phục hồi. Replication lag là độ trễ quan sát được của cơ chế đồng bộ. Hai khái niệm liên quan nhưng không giống nhau.

Ví dụ: RPO mục tiêu 5 phút; lag bình thường 20 giây; link down 40 phút; local log được giữ bền vững; sau khi link hồi phục, backlog cần 25 phút để drain. Nếu local log không mất và replay đầy đủ, dữ liệu không nhất thiết mất, nhưng central view stale 40 phút. Nếu local site hỏng trước khi log được bảo vệ ở nơi khác, dữ liệu có thể mất.

| Chỉ số | Ý nghĩa |
| --- | --- |
| Replication lag | Thời gian/độ dài log chưa được áp dụng ở đích |
| Data freshness | Tuổi của dữ liệu mới nhất consumer đang nhìn thấy |
| RPO | Mức dữ liệu có thể mất được business chấp nhận khi recovery |

Freshness có thể kém dù không mất dữ liệu; RPO có thể đạt dù read model tạm thời stale. Dashboard phải hiển thị riêng cả ba.

## 12. Bảo mật đồng bộ giữa các môi trường

Đồng bộ dữ liệu mở ra đường truyền và quyền truy cập mới. Dùng VPN/private connectivity hoặc TLS phù hợp; xác thực hai phía khi cần; workload identity/certificate có vòng đời và rotation; least privilege theo source, target, topic, table và operation; mã hóa at rest và in transit; phân loại dữ liệu và mask/tokenize trước khi đưa sang môi trường quyền hạn thấp hơn; audit thao tác sync/replay/checkpoint; chống replay trái phép; kiểm soát delete propagation; bảo vệ dead-letter queue vì có thể chứa dữ liệu nhạy cảm.

Không sao chép secret dài hạn tới mọi site chỉ để ứng dụng hoạt động offline. Ưu tiên identity cục bộ riêng, credential ngắn hạn hoặc cơ chế cache có expiration. Nếu cần offline credential, phải có threat model, giới hạn quyền, thời hạn, rotation và quy trình revoke.

## 13. Đồng bộ object và file

Object replication có semantics khác database replication. Object versioning giúp nhận biết phiên bản; metadata/tag có thể cần replicate riêng; delete có thể tạo delete marker hoặc xóa vĩnh viễn tùy cấu hình; multipart upload dang dở cần xử lý; checksum kiểm tra integrity; file lớn có thể cần multipart/resume hoặc bulk transfer.

Nếu hai phía sửa cùng object key khi offline, cần version ID hoặc ownership policy để tránh overwrite. Không dùng last modified time làm nguồn sự thật duy nhất nếu clock giữa site không đồng bộ.

## 14. Đồng bộ cấu hình và identity

| Thành phần | Khuyến nghị thiết kế |
| --- | --- |
| Application configuration | Có source of truth, version, staged rollout và rollback |
| Network policy | Phê duyệt tập trung; local enforcement theo phiên bản đã ký |
| Identity/role mapping | Federation hoặc trust relationship rõ, audit thay đổi |
| Secrets | Secret manager theo môi trường; hạn chế copy giữa domain |
| Certificates | Inventory, expiry alert, renewal và trust overlap |
| Software/image artifacts | Registry tin cậy, immutable digest, kiểm tra chữ ký/provenance |

Khi mất control plane, site có thể cần tiếp tục bằng policy/config đã ký và còn hiệu lực. Không chuyển sang allow-all vì không lấy được policy mới.

## 15. Network design cho đồng bộ liên vùng/liên cloud

Network là dependency nền cho replication, CDC và store-and-forward. Cần kết nối có redundancy theo RTO; sizing băng thông theo baseline sync cộng backlog catch-up; QoS/traffic shaping phân biệt live transaction với bulk replication; DNS/endpoint discovery có chiến lược khi provider/region lỗi; kiểm tra MTU, NAT, firewall state và idle timeout; private connectivity, encryption và segmentation giữ trust boundary; giám sát tunnel, packet loss, latency, throughput và route changes.

### 15.1. Capacity cho catch-up

Giả sử local tạo trung bình 2 MB/s log, link down 30 phút:

~~~text
backlog = 2 MB/s * 30 * 60 s
        = 3,600 MB
~~~

Nếu sau reconnect có 10 MB/s capacity cho replication trong khi live traffic tiếp tục tạo 2 MB/s, net drain rate là 8 MB/s:

~~~text
catch_up_time = 3,600 MB / 8 MB/s
              = 450 s
              = 7.5 minutes
~~~

Đây là ước tính đơn giản bỏ qua protocol overhead, compression, retry, burst và processing bottleneck. Nó cho thấy capacity phải lớn hơn tốc độ phát sinh dữ liệu để backlog giảm.

## 16. Observability và runbook cho đồng bộ

Không thể chỉ giám sát trạng thái tunnel màu xanh. Link có thể up nhưng replication không tiến triển, consumer lỗi schema hoặc queue liên tục retry.

| Nhóm | Metric |
| --- | --- |
| Network | Tunnel uptime, latency, packet loss, throughput, reconnect count |
| Replication | Lag seconds/bytes, log position, apply rate, failure count |
| Queue | Depth, oldest age, enqueue/dequeue rate, retry, dead-letter |
| Data integrity | Checksum mismatch, record count delta, conflict/duplicate count |
| Freshness | Age of newest event/data visible at target |
| Capacity | Disk spool usage, network quota, connector CPU/memory |
| Security | Auth failure, certificate expiry, policy change, replay rejection |
| Business | Pending booking/payment, duplicate operation, reconciliation backlog |

Metric nên dimension theo source/site/target/stream với cardinality được kiểm soát; không gắn raw customer ID vào time-series label.

Alert nên kích hoạt khi lag vượt ngưỡng đủ lâu; queue gần đầy hoặc disk spool gần hết; oldest message age vượt SLA; replication không tiến triển dù tunnel up; conflict/duplicate tăng; certificate sắp hết hạn; catch-up rate thấp hơn tốc độ tạo backlog.

Runbook nêu owner, tác động, cách dừng sync an toàn, kiểm tra write authority, resume checkpoint, quarantine poison message, đối soát và tiêu chí đóng sự cố.

## 17. Failure scenarios và cách phục hồi

| Sự cố | Hậu quả | Biện pháp |
| --- | --- | --- |
| WAN/VPN down | Không đồng bộ; local queue tăng | Store-and-forward, quota, alert, degraded mode |
| Link flap | Retry nhiều, duplicate, session reset | Backoff/jitter, circuit breaker, checkpoint |
| Target database down | Backlog tăng dù network up | Bounded buffer, capacity plan, resume |
| Schema incompatibility | Consumer từ chối event | Versioned schema, compatibility test, quarantine |
| Disk spool full | Local không thể nhận thêm dữ liệu | Threshold alert, backpressure, admission policy |
| Clock skew | Ordering/last-write-wins sai | NTP, logical version, tránh timestamp đơn |
| Split-brain | Hai site cùng ghi authoritative data | Fencing, ownership lease/quorum hoặc manual failover |
| Credential expired | Sync bị từ chối | Refresh/rotation, certificate alert |
| Poison message | Consumer retry vô hạn | DLQ/quarantine, sửa payload và replay có kiểm soát |
| Accidental delete/ransomware | Lỗi lan sang replica | Immutable backup, delete protection, restore clean point |

## 18. Bài thực hành: giữ hoạt động tại site khi cloud link bị mất

**Bối cảnh giả định:** nền tảng đặt chỗ chạy control plane trên cloud; mỗi khách sạn có local edge service quản lý check-in, trạng thái phòng và event. VPN tới cloud có thể mất tối đa 45 phút. Site cần tiếp tục check-in, tra cứu reservation đã cache và ghi local status event. Booking mới vượt quota local phải chuyển sang pending hoặc từ chối theo policy.

### Nhiệm vụ

1. Phân loại booking, payment, room status, property catalog, search projection, notification và telemetry theo owner/consistency/RPO.
2. Thiết kế network path/failure-domain: VPN redundancy, DNS, identity, bandwidth và traffic priority.
3. Chọn dữ liệu dùng synchronous replication, asynchronous replication, CDC, batch hoặc store-and-forward; giải thích lý do.
4. Thiết kế local durable database và transactional outbox với event ID, aggregate version và checkpoint.
5. Viết degraded mode cho check-in, booking mới, payment timeout và notification.
6. Thiết kế conflict resolution cho room status và booking; xác định writer authority và business rule.
7. Mô phỏng mất link 45 phút, reconnect; tính backlog và thời gian catch-up.
8. Thiết kế retry/backoff, deduplication, ordering, DLQ và replay.
9. Xác định RPO, replication lag và data freshness cho từng capability.
10. Xây dashboard/alert cho tunnel, lag, backlog, spool disk, conflict và business reconciliation.
11. Kiểm thử credential expiry, schema mismatch, split-brain, target outage và disk full.
12. Viết ADR nêu trade-off availability, consistency, security, cost và operational complexity.

### Mẫu quyết định đồng bộ

| Dataset | Source of truth | Sync method | Offline behavior | Conflict policy |
| --- | --- | --- | --- | --- |
| Booking/payment | Central booking/payment service | Async event + durable ledger/reconciliation | Pending hoặc hạn chế thao tác rủi ro | Single writer/business workflow |
| Room status | Local site trong phạm vi ủy quyền | Outbox/store-and-forward | Tiếp tục update local | Version/CAS và rule nghiệp vụ |
| Property catalog | Central master | CDC/batch | Read-only cached snapshot | Central wins, refresh version |
| Search projection | Rebuildable projection | Event/CDC | Dùng index stale có cảnh báo | Rebuild từ source |
| Notification | Event source/outbox | Queue/replay | Queue local | Idempotency key |
| Telemetry | Site-local buffer | Batch/stream | Buffer bounded | Loss policy theo loại signal |

### Tiêu chí hoàn thành

- Mỗi dataset có owner, write authority, consistency và RPO rõ.
- Không dùng multi-writer cho dữ liệu quan trọng nếu thiếu conflict semantics.
- Outbox/store-and-forward bền vững và có checkpoint.
- Retry, duplicate, ordering và replay được xử lý.
- Degraded mode nêu rõ chức năng tiếp tục, pending hoặc fail-closed.
- Reconnect có backpressure, catch-up capacity và reconciliation.
- Metric tách replication lag, freshness và RPO.
- Identity, encryption, key, audit và retention được bảo vệ khi offline.
- Runbook xử lý link down, split-brain, queue full và credential expiry.

## 19. Checklist Well-Architected cho đồng bộ hybrid/multi-cloud

- [ ] Đã phân loại dataset và xác định source of truth/owner cho từng loại.
- [ ] Consistency level phù hợp invariant nghiệp vụ và failure scenario.
- [ ] Đã xác định synchronous, asynchronous, CDC, event, batch hay store-and-forward theo data type.
- [ ] Replication semantics, lag, commit acknowledgment và failure behavior được hiểu rõ.
- [ ] Backup độc lập replication, có immutable protection và restore test.
- [ ] Local offline writes có durable storage/outbox và quota/backpressure.
- [ ] Message có ID, schema version, aggregate key/version và checkpoint.
- [ ] Consumer idempotent; duplicate, ordering, retry, poison message và replay có policy.
- [ ] Conflict resolution dựa trên domain semantics; tránh timestamp-only khi clock không tin cậy.
- [ ] Write authority/fencing ngăn split-brain và double writer.
- [ ] Degraded mode xác định rõ capability tiếp tục, hạn chế, pending hoặc fail-closed.
- [ ] Reconnect có catch-up capacity, rate limit, jitter và reconciliation.
- [ ] RPO, replication lag và data freshness được đo riêng.
- [ ] Network có redundancy, segmentation, encryption, bandwidth và traffic priority.
- [ ] Identity/credential/certificate có vòng đời, rotation và offline policy rõ.
- [ ] PII/secret được bảo vệ trong stream, queue, log, trace và dead-letter.
- [ ] Có dashboard/alert về link, lag, backlog, disk, conflict và integrity.
- [ ] Runbook có owner, recovery order, checkpoint, rollback và tiêu chí kết thúc.
- [ ] ADR ghi rõ đánh đổi reliability, consistency, security, performance, cost và operations.

**Điểm cốt lõi:** đồng bộ dữ liệu không chỉ là sao chép bản ghi qua network. Kiến trúc phải xác định nguồn có thẩm quyền, mức consistency, cách tiếp nhận thay đổi khi offline, cách xử lý duplicate/conflict và cách catch-up khi reconnect. Khi durable queue, outbox/CDC, checkpoint, idempotency, write authority và observability được thiết kế cùng nhau, hybrid/multi-cloud có thể duy trì nghiệp vụ trong giới hạn đã định và hội tụ dữ liệu có kiểm soát sau gián đoạn.
