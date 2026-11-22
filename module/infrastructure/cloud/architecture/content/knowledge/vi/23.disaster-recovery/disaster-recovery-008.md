# Failback sau sự cố và khôi phục trạng thái vận hành bình thường

Khi một region chính gặp sự cố, hệ thống có thể chuyển sang region dự phòng để tiếp tục phục vụ. Nhưng việc region ban đầu hoạt động trở lại không có nghĩa hệ thống nên lập tức chuyển traffic về đó. Trong thời gian failover, region dự phòng có thể đã nhận giao dịch mới, thay đổi dữ liệu, phát event, gửi thông báo và trở thành nơi duy nhất có trạng thái mới nhất. Nếu chỉ đổi DNS hoặc bật lại database cũ, hệ thống có thể mất giao dịch, ghi hai nơi, gửi message trùng hoặc tạo ra hai nguồn dữ liệu không còn đồng nhất.

**Failback** là quy trình có kiểm soát để đưa workload, quyền ghi, dữ liệu và traffic từ môi trường DR hiện đang phục vụ trở về topology vận hành mục tiêu. Mục tiêu không chỉ là quay về region ban đầu, mà là khôi phục một trạng thái ổn định, nhất quán, có thể vận hành và đã được kiểm chứng.

Bài học này thuộc chương **Phục hồi thảm họa** của module **CLOUD_ARCHITECTURE**. Chủ đề liên kết độ tin cậy, dữ liệu, network, compute, identity, bảo mật và vận hành. Một kế hoạch failback cần định nghĩa điều kiện bắt đầu, thứ tự đồng bộ dữ liệu, quyền writer, kiểm tra drift, chuyển traffic, đối soát giao dịch, phương án dừng/rollback và bằng chứng đóng sự cố.

## 1. Failover và failback là hai quy trình khác nhau

**Failover** chuyển dịch vụ khỏi môi trường đang lỗi sang một môi trường có khả năng phục vụ. **Failback** chuyển workload và quyền vận hành từ môi trường DR về topology mục tiêu sau khi sự cố được xử lý.

Ví dụ Booking Platform có Region A là region vận hành bình thường và Region B là warm standby. Khi A mất kết nối, đội vận hành fence writer A, promote database B và chuyển traffic sang B. Trong vài giờ hoặc vài ngày tiếp theo, B nhận các booking, payment status, cancellation và event mới. Khi A phục hồi, A thường đã tụt hậu so với dữ liệu hiện tại ở B.

~~~mermaid
flowchart LR
    A["Trước sự cố<br/>A = Primary"] --> F["Failover<br/>A lỗi"]
    F --> B["DR operation<br/>B = Active writer"]
    B --> R["Region A phục hồi"]
    R --> S["Assess / repair / reverse sync"]
    S --> C["Controlled failback"]
    C --> N["Normal topology restored"]
~~~

Sự khác biệt về hướng dữ liệu:

| Giai đoạn | Nơi giữ dữ liệu authoritative | Hướng đồng bộ |
|---|---|---|
| Trước sự cố | Region A | A → B |
| Sau failover | Region B | B → A hoặc chờ đồng bộ |
| Trong failback preparation | Region B vẫn là writer | B → A |
| Tại thời điểm switchover | Chuyển quyền ghi có kiểm soát | Hoàn tất B → A rồi đổi owner |
| Sau failback | Region A trở thành writer mới | A → B |

Điểm cốt yếu: **không đảo chiều replication hoặc đổi writer chỉ vì region A đã online**. Phải xác định nơi đang chứa dữ liệu đúng nhất và giữ nó authoritative cho tới khi chuyển quyền ghi an toàn.

## 2. Điều kiện để bắt đầu failback

Failback là một thay đổi production có rủi ro. Cần xác định readiness trước khi thực hiện.

### 2.1. Region gốc đã phục hồi ổn định

Không chỉ dựa vào việc VM hoặc database báo healthy. Cần xác minh:
- Nguyên nhân sự cố đã được hiểu và xử lý.
- Compute, storage, network và database không còn ở trạng thái degradation.
- Các AZ và dependency cần thiết hoạt động.
- Capacity đủ để tiếp nhận tải dự kiến.
- Không còn dấu hiệu packet loss, latency bất thường, throttling hoặc lỗi control plane.
- Monitoring và alerting từ bên ngoài region hoạt động.
- Các lần kiểm tra liên tiếp cho thấy trạng thái ổn định trong một khoảng thời gian được quy định.

Không chọn thời gian ổn định tùy ý. Mức quan sát cần dựa vào loại lỗi, lịch sử sự cố và khả năng tái phát. Một network flap kéo dài vài phút cần cách đánh giá khác với corruption hoặc security compromise.

### 2.2. Nguyên nhân gốc đã được khắc phục

Nếu failover xảy ra do lỗi schema migration, credential, policy hoặc bug ứng dụng thì failback không tự giải quyết những vấn đề đó. Cần:
- Root cause analysis đã có kết luận đủ tin cậy.
- Bản sửa được kiểm thử.
- Policy, secret và certificate cần thiết được khôi phục.
- Artifact và cấu hình phù hợp đã được triển khai.
- Có bằng chứng lỗi không tái diễn trong môi trường kiểm thử hoặc canary.

Nếu nguyên nhân chưa rõ, failback có thể đưa traffic trở lại đúng failure mode cũ. Trường hợp này nên tiếp tục chạy trên region B và điều tra thêm, trừ khi có lý do nghiệp vụ bắt buộc phải chuyển.

### 2.3. Capacity và dependency sẵn sàng

Region A cần đủ tài nguyên để nhận tải production, còn Region B cần đủ tài nguyên để tiếp tục nhận traffic trong trường hợp failback thất bại.

Kiểm tra:
- Compute quota, instance/GPU quota, IP và subnet capacity.
- Database/storage throughput và connection limit.
- Cache warm-up và queue consumer capacity.
- Identity, KMS/HSM, secret manager, DNS, certificate và registry.
- Network path tới các dịch vụ nội bộ, đối tác và SaaS.
- Autoscaling, deployment pipeline và quyền break-glass.
- Backup/replication và phương án phục hồi nếu switchover bị gián đoạn.

Không scale toàn bộ capacity A xuống trước khi A hoàn tất kiểm chứng và B vẫn có thể tiếp tục phục vụ.

## 3. Giữ một nguồn ghi authoritative

Sau failover, region B thường đã trở thành writer. Trước và trong failback preparation, nên giữ B là nguồn dữ liệu có thẩm quyền.

Các quy tắc:
1. Xác nhận rõ region/database nào đang giữ quyền ghi.
2. Chặn writer cũ hoặc resource đã mất quyền ghi.
3. Không cho ứng dụng ở A tự động ghi khi database chỉ vừa khởi động lại.
4. Thiết lập replication chiều B → A theo cơ chế được hỗ trợ.
5. Theo dõi lag và lỗi apply trong suốt quá trình.
6. Chỉ đổi writer sau khi hoàn tất điều kiện switchover.
7. Dùng fencing/epoch/lease phù hợp để ngăn writer cũ tiếp tục ghi.

### 3.1. Split-brain khi cả hai region cùng ghi

Nếu A và B đều nhận write, có thể tạo ra:
- Hai booking cùng giữ một tài nguyên.
- Payment state khác nhau giữa hai region.
- Hai event có nội dung mâu thuẫn.
- Counter hoặc inventory bị cập nhật sai.
- Dữ liệu bị ghi đè khi replication hội tụ.

Không thể giải quyết mọi xung đột bằng cách lấy timestamp lớn hơn. Clock có thể lệch, update có semantics khác nhau và một giao dịch có thể phụ thuộc vào thứ tự nghiệp vụ.

### 3.2. Fencing và quyền writer

Một cơ chế fencing có thể sử dụng epoch/term tăng đơn điệu. Khi B được promote, nó mang epoch mới; database hoặc tầng ghi phải từ chối thao tác của writer cũ có epoch thấp hơn.

Fencing token chỉ hiệu quả nếu mọi đường ghi đều kiểm tra token hoặc quyền tương đương. Chỉ sửa DNS, cập nhật load balancer hoặc tắt một pod không đủ nếu client, batch job hay worker cũ vẫn có thể ghi trực tiếp.

## 4. Reverse replication: đồng bộ từ DR về region gốc

Sau failover, dữ liệu mới được tạo ở B. Failback cần đưa những thay đổi đó về A trước khi A trở thành writer.

~~~mermaid
flowchart TB
    B["Region B<br/>Current authoritative writer"] --> LOG["Transaction log / change stream"]
    LOG --> XFER["Reverse replication B → A"]
    XFER --> A["Region A<br/>Recovering replica"]
    A --> VERIFY["Validate lag / consistency / checksums"]
    VERIFY --> READY["Candidate for writer"]
~~~

Cơ chế reverse replication tùy loại dữ liệu:
- **Database:** transaction log, streaming replication, change data capture hoặc native cross-region replication.
- **Object storage:** object version replication, inventory/diff và copy object thay đổi.
- **Event stream:** replicate partition/event theo offset, giữ event ID và ordering semantics.
- **File/block storage:** snapshot, volume replication hoặc block-level synchronization.
- **Search index/cache:** thường có thể rebuild từ source of truth thay vì replicate trực tiếp.

Không phải mọi dịch vụ hỗ trợ đảo chiều replication an toàn. Một số cơ chế chỉ hỗ trợ một hướng hoặc yêu cầu tạo lại relationship. Cần xác minh thao tác provider/API, điều kiện version/engine, quyền và các giới hạn trước khi chạy.

### 4.1. Không nhầm replication lag với dữ liệu đã đồng nhất

Replication lag bằng 0 tại một thời điểm là tín hiệu tốt nhưng chưa tự chứng minh mọi hệ thống đã đồng nhất. Cần kiểm tra:
- Replication stream có bị pause hoặc lỗi apply không?
- Tất cả partition/table/object prefix cần thiết có được bao phủ không?
- Có transaction đang mở hoặc chưa commit không?
- Có dữ liệu bị filter/exclude khỏi replication không?
- Sequence/offset có liên tục không?
- Secondary index, materialized view và search index đã catch up chưa?
- Metadata, ownership, tags, ACL và encryption key reference có đầy đủ không?

Với object storage, một số thao tác replication bất đồng bộ có thể không bảo đảm thứ tự giữa các object. Nếu file metadata trong DB trỏ đến object chưa replicate, ứng dụng có thể hiển thị record nhưng không tải được file. Cần kiểm tra quan hệ dữ liệu chứ không chỉ đếm object.

### 4.2. Dữ liệu không thể replicate trực tiếp

Một số trạng thái phải được tái tạo hoặc đối soát ở tầng ứng dụng:
- Cache có thể xóa và warm-up lại từ database.
- Search index có thể rebuild từ bảng nguồn hoặc event log.
- Session tạm có thể hết hạn hoặc phải đăng nhập lại.
- Queue ephemeral có thể cần replay từ outbox/event store.
- Scheduled job cần xác định owner mới để không chạy hai lần.
- File tạm/incomplete upload cần kiểm tra và cleanup theo upload session.

Lập danh sách từng data store và phân loại: replicate, restore, rebuild, reconcile hoặc discard theo policy.

## 5. Đối soát dữ liệu và giao dịch phát sinh trong DR

Trong thời gian B phục vụ, có thể đã xảy ra những giao dịch ở gần thời điểm replication lag hoặc thời điểm A mất kết nối. Trước failback phải hiểu chính xác những gì đã được commit.

### 5.1. Reconciliation

Đối soát không chỉ là so sánh row count. Cần kiểm tra invariant nghiệp vụ:
- Mọi booking đã CONFIRMED có tài nguyên và khoảng thời gian hợp lệ.
- Mọi payment đã captured có transaction/reference tương ứng.
- Một cancellation không bị ghi đè bởi trạng thái cũ.
- Event quan trọng không bị mất hoặc xử lý hai lần.
- Inventory/availability tổng hợp khớp với các giao dịch nguồn.
- Object metadata có object thực và object đó đọc được.
- Sequence/offset của stream không có khoảng trống không giải thích được.

Có thể dùng:
- Row count và checksum theo partition.
- Transaction ID/LSN/GTID/commit sequence theo engine.
- Event ID và idempotency key.
- Reconciliation query từ source of truth.
- Tổng giá trị, số lượng và trạng thái theo business aggregate.
- Object inventory và metadata comparison.

### 5.2. Giao dịch chưa rõ kết quả

Một request có thể đã được xử lý ở B nhưng client không nhận response. Client retry ở một region khác có thể gửi lại cùng một yêu cầu. Khi đối soát cần phân biệt:
- Chưa từng commit.
- Đã commit nhưng response bị mất.
- Đã thực hiện side effect nhưng trạng thái chưa ghi nhận.
- Đã ghi nhận ở database nhưng event chưa phát.
- Event đã phát nhưng consumer chưa xử lý.

Idempotency key và transaction reference giúp xác định một thao tác đã xảy ra hay chưa. Không tự tạo giao dịch mới khi chưa tra cứu trạng thái trước đó.

### 5.3. Event/outbox và consumer

Với kiến trúc event-driven, cần đối soát:
- Outbox event đã được publish hay chưa.
- Event ID có được giữ nguyên khi replay không.
- Consumer đã xử lý side effect chưa.
- Offset/ack state của broker có nhất quán với database không.
- DLQ có message phát sinh trong thời gian DR không.
- Replay có thể tạo duplicate notification/payment command không.

Failback là thời điểm dễ tạo duplicate nếu hai region cùng chạy scheduler, outbox publisher hoặc consumer. Cần ownership rõ ràng cho từng partition/workload.

## 6. Đồng bộ ứng dụng, cấu hình và schema

Dữ liệu không phải thứ duy nhất có thể lệch giữa hai region. Trong thời gian DR, region B có thể đã được cập nhật nóng hoặc chạy một image khác region A.

Kiểm tra parity của:
- Container image digest và package version.
- Application config, feature flags và environment variables.
- Database schema/migration version.
- API/event schema và compatibility.
- Model artifact/feature version nếu có ML.
- Secret version, certificate, trust bundle và expiry.
- IAM role/policy, workload identity và network policy.
- Autoscaling parameters, quotas và runtime settings.
- Scheduled jobs, worker concurrency và retry policy.

Không triển khai mù quáng bản cũ của A lên dữ liệu mới ở B hoặc ngược lại. Schema phải tương thích với version ứng dụng sẽ chạy sau failback. Dùng expand-contract nếu cần đồng bộ schema mà hai region/consumer đang chạy các phiên bản khác nhau.

### 6.1. Immutable artifacts và configuration drift

Nên so sánh bằng:
- Image digest thay vì tag mutable.
- Artifact checksum/signature.
- Version của IaC và deployment manifest.
- Config revision hoặc hash có kiểm soát.
- Secret reference/version, không xuất secret value.
- Database migration history.
- Policy snapshot hoặc policy-as-code evaluation.

Drift cần được phân loại thành bắt buộc, chấp nhận tạm thời hoặc cần sửa trước failback. Đừng xóa thay đổi nóng ở B khi chưa hiểu chúng đã ảnh hưởng tới dữ liệu hay user flow như thế nào.

## 7. Chuẩn bị traffic và health check

Sau khi dữ liệu đã đồng bộ, cần xác nhận A có thể phục vụ trước khi nhận traffic thật.

### Kiểm tra readiness ở cấp region

- API health và synthetic user journey.
- Database read/write path theo quyền được phép.
- Feature flag, cache và object access.
- Authentication, authorization và token renewal.
- Kết nối payment/email/partner theo sandbox hoặc kiểm tra an toàn.
- Queue publish/consume với event kiểm thử có thể deduplicate.
- TLS/certificate, DNS, private endpoint và network route.
- p95/p99 latency và error rate.
- Capacity khi nhận phần traffic dự kiến.

Không dùng test ghi thật vào dữ liệu khách hàng nếu chưa có cleanup/approval. Có thể sử dụng synthetic tenant hoặc test object được đánh dấu rõ.

### Traffic không nên chuyển cùng lúc

Traffic manager có thể hỗ trợ weighted routing. Khi A đã sẵn sàng:
1. Giữ B là primary writer.
2. Chuyển một lượng nhỏ traffic đọc hoặc cohort nội bộ tới A nếu data/consistency cho phép.
3. Quan sát latency, error, auth, cache và dữ liệu trả về.
4. Nếu ổn, tăng tỷ lệ theo các bước đã định.
5. Chuyển quyền ghi theo một switchover có kiểm soát.
6. Sau khi A trở thành writer, chuyển tiếp traffic theo kế hoạch.
7. Giữ B sẵn sàng để rollback/DR trong khoảng quan sát.

Nếu hệ thống single-writer, **không cho cả A và B ghi song song chỉ để canary traffic**. Có thể canary read-only hoặc dùng shadow request, nhưng write ownership vẫn phải duy nhất.

## 8. Switchover: chuyển quyền ghi tại thời điểm failback

Switchover là bước nhạy cảm nhất. Phải có kế hoạch rõ ràng, người điều hành, điều kiện dừng và trạng thái xác nhận.

Một trình tự tham khảo cho hệ thống single-writer:

~~~mermaid
sequenceDiagram
    participant OPS as Operations
    participant APP as Applications
    participant B as Region B writer
    participant A as Region A candidate
    OPS->>APP: Enable maintenance/admission control
    APP->>B: Stop accepting new writes
    B->>B: Drain in-flight transactions
    B->>A: Final replication catch-up
    A-->>OPS: Lag zero / consistency checks pass
    OPS->>B: Fence writer B
    OPS->>A: Promote A with new epoch
    OPS->>APP: Route write traffic to A
    APP->>A: Controlled write verification
    OPS->>APP: Restore normal traffic
~~~

Chi tiết cần xem theo từng engine/service:
- Dừng hoặc hạn chế write mới trong một cửa sổ ngắn.
- Drain request/transaction đang chạy.
- Dừng scheduler hoặc publisher có thể tạo side effect.
- Ghi nhận replication position cuối cùng ở B.
- Chờ A apply tới điểm đó.
- Chạy consistency checks cuối.
- Fence B và xác nhận không còn đường ghi.
- Promote A theo cơ chế database/broker hỗ trợ.
- Cấp epoch/lease mới nếu kiến trúc dùng fencing.
- Cập nhật service discovery/connection string/traffic routing.
- Mở write traffic dần.
- Xác minh một giao dịch kiểm thử và đọc lại từ nguồn chuẩn.

Trong một số database, promote standby và reverse replication có ràng buộc thứ tự khác nhau. Luôn dùng quy trình được hỗ trợ bởi database/provider; sơ đồ trên mô tả logic tổng thể, không phải câu lệnh áp dụng cho mọi engine.

### 8.1. Maintenance window và admission control

Nếu downtime ngắn được chấp nhận, có thể bật maintenance window, từ chối hoặc xếp hàng các write mới, trong khi vẫn phục vụ read-only. Nếu không thể dừng ghi, phải có một protocol chuyển ownership mạnh hơn và hỗ trợ cutover không downtime.

Thông báo cho người dùng và đối tác nếu cần. Những request bị từ chối trong maintenance cần retry behavior an toàn, idempotency key và thông điệp rõ ràng.

## 9. Rollback khi failback có vấn đề

Failback cũng có thể thất bại. Cần định nghĩa rollback trước khi bắt đầu, không chờ tới khi lỗi xảy ra mới quyết định.

Các trigger dừng:
- Replication lag không giảm hoặc xuất hiện lỗi apply.
- Consistency check thất bại.
- Không fence được writer cũ.
- A không đạt health, SLO hoặc capacity.
- Identity/KMS/network không hoạt động ổn định.
- Error rate hoặc latency vượt ngưỡng sau chuyển traffic.
- Data mismatch hoặc duplicate side effect xuất hiện.
- Không rõ region nào đang authoritative.

### 9.1. Trước và sau khi A nhận write

**Trước khi A nhận write:** có thể hủy switchover, giữ B làm writer và điều tra. Đây thường là rollback đơn giản hơn.

**Sau khi A đã nhận write:** A đã trở thành source of truth mới. Không được chỉ chuyển traffic về B và bật ghi mà không đồng bộ các write mới từ A sang B hoặc xác minh B vẫn có dữ liệu đầy đủ. Khi đó cần:
1. Fence writer hiện tại theo một quy trình mới.
2. Xác định các transaction đã commit tại A.
3. Đồng bộ hoặc đối soát dữ liệu A → B.
4. Đảm bảo không ghi ở cả hai nơi.
5. Chỉ promote B khi đã đáp ứng consistency và recovery criteria.
6. Ghi lại incident và quyết định.

Sau khi đã có write mới, “rollback về B” thực chất có thể là một **failover mới**, không phải đảo ngược một config.

### 9.2. Giữ B như recovery path

Trong một khoảng thời gian sau failback, giữ B sẵn sàng và replication A → B được thiết lập lại. Không xóa dữ liệu B hoặc thu hồi toàn bộ capacity ngay lập tức. Thời gian giữ standby phụ thuộc chính sách DR và mức độ tự tin vào hệ thống vừa chuyển.

## 10. Failback theo từng loại dữ liệu

Không phải mọi data store đều dùng chung một chiến lược:

| Thành phần | Phương án failback | Kiểm tra quan trọng |
|---|---|---|
| Relational database | Reverse replication, catch-up, fence và promote | Transaction position, schema, constraint, lag |
| NoSQL database | Replication reversal hoặc export/import theo provider | Conflict, consistency, partition ownership |
| Object storage | Replicate version/object mới về region gốc | Version ID, metadata, lifecycle, checksum |
| Event broker | Mirror/replay theo partition và offset | Event ID, ordering, duplicate, consumer offset |
| Cache | Có thể invalidate và warm từ source | Cache key/version, cold-start load |
| Search index | Rebuild từ source hoặc replicate index | Index version, document count, freshness |
| File share/block volume | Snapshot/replication và mount kiểm tra | Crash/application consistency, permissions |
| Session store | Replicate hoặc yêu cầu session refresh/re-auth | TTL, token validity, user impact |
| Analytics warehouse | Catch-up/backfill partition | Late data, deduplication, watermark |
| Scheduled jobs | Chuyển ownership theo lease/leader | Không chạy trùng job hoặc bỏ sót lịch |

Một số dữ liệu có thể tái tạo rẻ hơn replicate. Chẳng hạn cache/search index có thể được rebuild, trong khi ledger payment cần bảo toàn transaction và đối soát chặt.

## 11. Shared dependencies khi failback

Một region có thể đã hoạt động trong DR nhờ cấu hình dự phòng, nhưng khi quay về A các dependency vẫn cần được kiểm tra. Đặc biệt:
- Identity issuer và workload federation.
- KMS/HSM key access, key rotation và decrypt permission.
- Secret manager, config store và certificate authority.
- DNS/traffic management và resolver cache.
- Container/image registry, package repository và model artifact.
- CI/CD, IaC state và deployment authority.
- Network hub, firewall, NAT, egress và private endpoint.
- Monitoring, alerting, tracing và incident communication.
- External provider quota, webhook callback và allowlist IP.
- Backup, replication coordinator và control plane.

Region A có thể healthy ở mức compute nhưng vẫn không sẵn sàng nếu certificate hết hạn, secret chưa đồng bộ, registry bị chặn hoặc workload identity đã thay đổi trong thời gian DR.

### Checklist dependency trước failback

| Dependency | Kiểm tra bắt buộc | Bằng chứng |
|---|---|---|
| Identity | Principal/role/token hoạt động từ cả hai region | Authentication test |
| KMS | Runtime và operator đọc/giải mã đúng dữ liệu | Decrypt test/audit |
| Secrets | Phiên bản secret/certificate hợp lệ và nhất quán | Secret version check |
| DNS | Record, TTL, health policy và endpoint đúng | External DNS probe |
| Registry | Artifact đã promote có thể pull | Image digest verification |
| Network | Private route, firewall và egress hoạt động | Connectivity test |
| CI/CD/IaC | Có pipeline failback được phê duyệt | Deployment rehearsal |
| Observability | Alert độc lập và dashboard cả hai region | Synthetic monitor |
| External API | Quota, allowlist và callback endpoint sẵn sàng | Contract/smoke test |

## 12. Bảo mật và kiểm soát thay đổi trong failback

Failback thường yêu cầu quyền cao: promote database, đổi routing, cấp key, sửa policy và tắt writer. Đây là thời điểm dễ mắc lỗi thao tác hoặc bị lợi dụng quyền.

Nguyên tắc:
- Phân tách người phê duyệt và người thực thi cho thao tác rủi ro cao.
- Sử dụng break-glass có kiểm soát, thời hạn và audit.
- Least privilege theo từng bước; không dùng credential admin vĩnh viễn.
- Ghi nhận ai đổi writer, policy, DNS, secret và traffic.
- Không gửi secret hoặc signed URL vào log/ticket.
- Bảo vệ backup, replication channel và dữ liệu tạm.
- Xác minh encryption key và data residency trước khi sao chép.
- Kiểm tra security finding phát sinh trong DR trước khi đưa A trở lại production.
- Sau khi hoàn tất, thu hồi quyền khẩn cấp và credential tạm.
- Kiểm tra cấu hình region A không bị hạ thấp security posture để dễ khôi phục.

Nếu sự cố ban đầu có thể là security compromise, không được tự động đưa region A trở lại chỉ vì hạ tầng hoạt động. Cần xác minh containment, persistence, identity trust và integrity trước khi cho phép nó nhận dữ liệu production.

## 13. Observability và tiêu chí thành công

Failback cần được đo như một quy trình, không chỉ là một lần chuyển DNS.

### 13.1. Chỉ số theo dõi

- Replication lag/position và lỗi apply.
- Số transaction chờ, in-flight write và thời gian drain.
- Data reconciliation mismatch.
- Database connection, lock, CPU, IOPS và storage latency.
- API p50/p95/p99, error rate và success rate.
- Queue depth, oldest message age, duplicate và DLQ arrival.
- Cache warm-up, hit ratio và stale response.
- Authentication, authorization, KMS decrypt và secret retrieval failure.
- Traffic weight theo region và user cohort.
- Cost/network egress/replication throughput trong quá trình catch-up.

### 13.2. Timeline và audit

Mỗi lần failback cần ghi:
- Incident ID và change ID.
- Người chỉ huy, approver và operator.
- Region hiện tại và writer hiện tại.
- Thời điểm bắt đầu, từng checkpoint, cutover và kết thúc.
- Replication position trước/sau.
- Mốc fence/promote và quyền writer.
- Traffic routing changes.
- Kết quả smoke test và reconciliation.
- Lỗi, rollback hoặc deviation.
- RTO/RPO thực tế của incident ban đầu và thời gian failback.
- Action items sau sự cố.

Không dùng một dashboard có metric aggregate toàn hệ thống để kết luận. Phải phân biệt region A/B, phiên bản ứng dụng, database writer và workload.

## 14. Runbook failback tham khảo

~~~text
PHASE 0 — AUTHORIZATION AND READINESS
  - Confirm incident cause is resolved.
  - Confirm target region and failback window.
  - Name incident commander, data owner and operators.
  - Confirm rollback and stop criteria.
  - Verify quota, identity, KMS, secrets, network and artifacts.

PHASE 1 — RECOVER TARGET REGION
  - Restore infrastructure and service dependencies.
  - Deploy approved application/runtime versions.
  - Verify schema/config/security parity.
  - Keep target region out of production write traffic.
  - Run health and synthetic checks.

PHASE 2 — REVERSE DATA SYNCHRONIZATION
  - Keep current DR region as sole writer.
  - Configure reverse replication.
  - Verify coverage, lag, errors and data integrity.
  - Rebuild cache/search/index as required.
  - Reconcile transactions, events and objects.

PHASE 3 — CUTOVER PREPARATION
  - Confirm target capacity and dependency readiness.
  - Notify stakeholders and enable maintenance/admission control if needed.
  - Stop new writes and drain in-flight work.
  - Record final replication position.
  - Wait for target to catch up and pass final checks.

PHASE 4 — WRITER SWITCH
  - Fence old writer.
  - Promote target with new ownership/epoch.
  - Validate one authoritative writer.
  - Switch routing gradually.
  - Run controlled business transaction and read-back.

PHASE 5 — STABILIZATION
  - Monitor latency, errors, queue, data and dependency health.
  - Keep former DR region ready and replicate from new writer.
  - Stop or reverse traffic shift if a criterion fails.
  - Reconcile post-cutover transactions.

PHASE 6 — CLOSE
  - Confirm SLO and business journeys.
  - Record actual RTO/RPO and failback timeline.
  - Revoke temporary access and clean up safely.
  - Update diagrams, runbooks and action items.
~~~

Các lệnh cụ thể phải theo database engine, cloud provider và routing service. Runbook cần có lệnh đã được review, output mong đợi, người thực hiện, điều kiện rollback và bước xác minh sau từng thao tác; không nên viết một đoạn lệnh chung rồi giả định chạy được trên mọi nền tảng.

## 15. Diễn tập failback và kiểm thử phục hồi

DR plan thường tập trung vào failover nhưng bỏ quên failback. Cần diễn tập cả hai hướng.

| Bài kiểm thử | Mục đích | Kết quả mong đợi |
|---|---|---|
| Reverse replication setup | Kiểm tra khả năng đổi chiều | Relationship được thiết lập, không ghi hai nơi |
| Replication catch-up | Đo thời gian đồng bộ dữ liệu tích lũy | Lag giảm theo dự kiến, không mất partition |
| Writer fencing | Xác minh writer cũ bị từ chối | Chỉ một writer có quyền ghi |
| Transaction reconciliation | Kiểm tra dữ liệu phát sinh trong DR | Invariant nghiệp vụ được thỏa mãn |
| Object/event recovery | Kiểm tra file, event và offset | Không mất/duplicate ngoài policy |
| Application/config parity | Phát hiện drift giữa region | Artifact, schema, secret reference và policy phù hợp |
| Traffic canary | Kiểm tra target trước khi full cutback | SLO đạt ở cohort thử nghiệm |
| Failback abort | Kiểm tra dừng giữa quy trình | DR region tiếp tục authoritative |
| Post-cutover rollback | Kiểm tra khi target đã nhận write | Có quy trình failover mới và data catch-up |
| Full game day | Diễn tập end-to-end | Đo timeline, RTO/RPO và action items |

### 15.1. Tiêu chí không nên bỏ qua

- Có thể xác định writer duy nhất tại mọi thời điểm.
- Có thể đo replication position và data mismatch.
- Có thể dừng trước cutover mà không ảnh hưởng source of truth.
- Có thể phục hồi nếu target gặp lỗi sau khi đã nhận write.
- Có thể tái lập dữ liệu cần thiết từ backup/replica/event log.
- Quy trình khẩn cấp vẫn hoạt động khi một shared dependency bị mất.
- Người vận hành biết khi nào tiếp tục, khi nào dừng và ai có quyền quyết định.

## 16. Đánh đổi theo Well-Architected

| Khía cạnh | Lợi ích của failback có kiểm soát | Rủi ro cần quản lý | Bằng chứng |
|---|---|---|---|
| **Độ tin cậy** | Khôi phục topology mục tiêu, capacity và recovery posture | Chuyển quá sớm, split-brain, mất write hoặc failback loop | Rehearsal, fencing test, reconciliation |
| **Bảo mật** | Khôi phục policy và quyền bình thường, thu hồi quyền khẩn cấp | Credential drift, key access sai, region từng bị compromise | IAM audit, key/decrypt test, incident review |
| **Hiệu quả hiệu năng** | Đưa workload về region có latency/capacity phù hợp | Cold cache, warm-up, replication load và traffic spike | p95/p99, cache hit, DB/replication metrics |
| **Tối ưu chi phí** | Có thể giải phóng capacity DR dư thừa sau ổn định | Replication hai chiều, standby và data transfer | Cost timeline, storage/egress usage |
| **Vận hành xuất sắc** | Runbook, ownership, timeline và trạng thái rõ | Thao tác thủ công, undocumented drift, phụ thuộc một chuyên gia | Game day, change log, runbook review |
| **Bền vững** | Loại bỏ tài nguyên tạm và replication không cần thiết | Giữ bản sao dư thừa hoặc xóa nhầm dữ liệu phục hồi | Lifecycle review, inventory, cleanup audit |

Một số đánh đổi:
- Maintenance window giúp cutover đơn giản hơn nhưng tạo gián đoạn chủ động.
- Zero-downtime switchover giảm gián đoạn nhưng đòi hỏi writer coordination và consistency mạnh hơn.
- Reverse replication giảm lượng dữ liệu cần copy lại nhưng phụ thuộc khả năng hỗ trợ của service.
- Backup/restore có thể đơn giản về hướng dữ liệu nhưng kéo dài RTO.
- Giữ DR region nóng lâu hơn tăng chi phí nhưng duy trì phương án phục hồi nhanh.
- Canary traffic phát hiện vấn đề sớm nhưng cần đảm bảo không phá single-writer ownership.

## 17. ADR minh họa — Failback Booking Platform từ Region B về Region A

> **Bối cảnh:** Region A gặp outage và đã failover sang B. Trong 36 giờ, B xử lý booking, cancellation và payment status. A đã phục hồi, nhưng replica database cũ hơn B và ứng dụng A có image/config khác.
>
> **Phương án A:** Chuyển DNS về A ngay khi health check xanh. Thực hiện nhanh nhưng có thể phục vụ bằng dữ liệu cũ, thiếu object/event và tạo split-brain nếu writer B vẫn hoạt động.
>
> **Phương án B:** Giữ B là writer, phục hồi A thành replica, đồng bộ B → A, đối soát giao dịch, fence B tại cutover và promote A.
>
> **Quyết định minh họa:** Chọn B. B tiếp tục authoritative trong quá trình preparation. Chỉ cutover khi replication position bắt kịp, data checks pass, dependency parity đạt và capacity A được xác nhận.
>
> **Cutover:** Dừng write trong cửa sổ ngắn, drain request, hoàn tất final sync, fence B, promote A và chuyển traffic theo cohort.
>
> **Rollback:** Trước khi A nhận write, có thể hủy và giữ B. Sau khi A nhận write, mọi quay lại B phải được xem là failover mới với reverse sync A → B.
>
> **Kiểm chứng:** Booking/payment reconciliation, event deduplication, object checksum, auth/KMS, p95/p99, queue backlog, canary và failback abort drill.
>
> **Điều kiện đóng:** A đạt SLO ổn định, replication A → B được thiết lập lại, B đủ khả năng DR, quyền khẩn cấp được thu hồi và timeline/action items đã ghi.

## 18. Bài tập thực hành: failback sau 24 giờ vận hành tại DR

Một nền tảng đặt chỗ sử dụng Region A làm primary và Region B làm warm standby. A gặp lỗi hạ tầng, đội vận hành failover thành công sang B. Sau 24 giờ, B đã tiếp nhận:
- 18.000 booking mới và cập nhật booking.
- 2.500 cancellation.
- 7.000 payment status events.
- 40.000 notification events, trong đó một số message đã vào DLQ.
- 600 GB object uploads.
- Một lần cập nhật cấu hình và một phiên bản container hotfix.

A đã online trở lại. Database A vẫn chạy nhưng replication relationship cũ không hoạt động. DNS health check báo A healthy. Nhóm muốn failback ngay trong ngày.

**Yêu cầu:**
1. Xác định điều kiện readiness cần kiểm tra trước khi bắt đầu.
2. Xây dựng inventory dữ liệu phải replicate, rebuild, replay hoặc reconcile.
3. Xác định B tiếp tục là writer trong giai đoạn nào.
4. Đề xuất reverse replication và cách đo catch-up.
5. Thiết kế reconciliation cho booking, cancellation và payment.
6. Xử lý notification/DLQ để tránh gửi trùng.
7. Xác minh 600 GB object uploads và metadata.
8. Đồng bộ container hotfix, config, schema, identity và secrets.
9. Thiết kế cutover, fencing và traffic migration.
10. Mô tả rollback trước và sau khi A nhận write.

### Hướng giải quyết

- DNS health check chỉ chứng minh một phần khả năng phục vụ; kiểm tra nguyên nhân outage, database, network, identity, KMS, secret, registry, capacity và synthetic business flow.
- Giữ B là authoritative writer cho tới khi reverse sync và đối soát hoàn tất.
- Dữ liệu giao dịch cần replication/change stream theo semantics database và transaction position. Cache có thể rebuild; search index rebuild hoặc catch-up; event phải giữ event ID, offset và ordering.
- Đối soát booking/cancellation/payment theo business invariant và transaction reference, không chỉ row count.
- Với notification, kiểm tra event ID, provider delivery status và DLQ; consumer phải idempotent trước replay.
- Với object, so sánh inventory, version, checksum, metadata, ACL và encryption key reference; chỉ đánh dấu file COMPLETE khi object thật đọc được.
- So sánh image digest, config revision, DB schema, secret version, IAM policy và feature flags; chỉ deploy artifact đã phê duyệt.
- Cutover bằng maintenance/admission control nếu cần, drain write, ghi final replication point, chờ A catch up, fence B, promote A, chuyển traffic canary rồi mở hoàn toàn.
- Trước khi A nhận write, có thể hủy cutover và tiếp tục B. Sau khi A nhận write, nếu quay lại B phải đồng bộ A → B và thực hiện failover mới, không chỉ đổi DNS.

### Câu hỏi tự kiểm tra

1. Vì sao failback không thể được thực hiện chỉ bằng cách đổi DNS về region cũ?
2. Sau failover, tại sao region DR thường là nơi giữ dữ liệu authoritative?
3. Reverse replication khác gì restore backup?
4. Replication lag bằng 0 có đủ để chứng minh dữ liệu đã nhất quán không?
5. Split-brain có thể xảy ra thế nào trong lúc switchover?
6. Fencing token bảo vệ hệ thống khỏi writer cũ ra sao?
7. Vì sao phải đối soát nghiệp vụ ngoài việc so sánh row count?
8. Những dữ liệu nào có thể rebuild thay vì replicate?
9. Vì sao cần kiểm tra image/config/schema drift trước failback?
10. Rollback trước cutover khác gì rollback sau khi region đích đã nhận write?
11. Những shared dependencies nào có thể khiến region cũ healthy nhưng vẫn không sẵn sàng?
12. Bằng chứng nào cần có để tuyên bố hệ thống đã trở lại trạng thái vận hành bình thường?

Failback an toàn là một quy trình **chuyển quyền sở hữu dữ liệu và traffic có kiểm soát**. Hãy giữ region DR authoritative trong lúc phục hồi, đồng bộ ngược và đối soát dữ liệu, kiểm tra dependency/config parity, sau đó mới fence writer hiện tại, promote region mục tiêu và chuyển traffic theo từng bước. Chỉ kết thúc khi SLO, consistency, security, observability và khả năng DR trở lại đã được kiểm chứng.
