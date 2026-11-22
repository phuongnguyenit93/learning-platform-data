# Phân chia workload theo phụ thuộc, dữ liệu và độ trễ

## 1. Vì sao phải phân chia workload trước khi chọn cloud?

Một hệ thống doanh nghiệp thường có nhiều loại workload: ứng dụng giao dịch, hệ thống legacy tại data center, phân tích dữ liệu, API đối tác, batch job, thiết bị IoT và dịch vụ cần độ trễ thấp. Các workload này không có cùng yêu cầu về dữ liệu, kết nối, compliance, latency, availability hoặc cách vận hành. Đưa tất cả lên cùng một cloud hoặc trải đều qua nhiều provider mà không phân tích dependency có thể làm tăng chi phí, độ trễ và rủi ro.

**Workload placement** là quyết định workload chạy ở đâu và dữ liệu của nó được lưu ở đâu: on-premises, private cloud, public cloud, nhiều region, edge hoặc nhiều cloud provider. Quyết định này cần dựa trên mối quan hệ giữa workload với hệ thống phụ thuộc, vị trí dữ liệu, yêu cầu latency, ràng buộc pháp lý và khả năng vận hành.

Trong module **CLOUD_ARCHITECTURE**, kiến trúc cloud được thiết kế từ yêu cầu nghiệp vụ tới mạng, compute, dữ liệu và mô hình triển khai; đồng thời cân bằng độ tin cậy, bảo mật, khả năng mở rộng, chi phí và vận hành theo Well-Architected. Hybrid và multi-cloud là phương án kiến trúc để đáp ứng các ràng buộc thực tế, không phải mục tiêu tự thân.

Sau bài này, bạn có thể:

- Lập dependency map và phân loại workload trước khi quyết định placement.
- Đánh giá data gravity, data locality, latency và network path.
- Chọn thành phần giữ tại on-premises/private cloud và thành phần đưa lên public cloud.
- Phân biệt hybrid cloud, multi-cloud và multi-region.
- Chọn mô hình placement theo transaction, analytics, batch, edge và integration workload.
- Thiết kế data replication, ownership, consistency và migration boundary.
- Đánh giá kết nối, identity, security, observability, resilience và cost liên vùng.
- Xây dựng workload placement matrix và kiểm chứng bằng đo lường.

## 2. Bắt đầu từ workload và ràng buộc nghiệp vụ

### 2.1. Workload là đơn vị phân tích

Không nên quyết định “di chuyển hệ thống ERP lên cloud” như thể ERP là một khối duy nhất. Hãy phân rã thành workload hoặc capability có thể xác định:

- API/frontend.
- Transaction processing.
- Batch và scheduled jobs.
- Database và object storage.
- Search/indexing.
- Integration adapter với hệ thống cũ.
- Analytics/warehouse.
- Identity, audit và security services.
- Control plane/management tooling.

Một ứng dụng có thể gồm các workload đặt ở nhiều môi trường. Nhưng càng chia nhỏ placement, số boundary và network dependency càng tăng. Cần tìm ranh giới hợp lý theo data ownership, failure domain và khả năng deploy độc lập.

### 2.2. Hồ sơ workload

Mỗi workload nên có profile:

| Thuộc tính | Câu hỏi |
|---|---|
| Business capability | Workload phục vụ hành trình nào? Criticality ra sao? |
| Owner | Nhóm nào chịu trách nhiệm code và vận hành? |
| Dependencies | Cần gọi service, database, queue, identity hoặc partner nào? |
| Data | Dữ liệu nào đọc/ghi? Ai là source of truth? |
| Latency | p95/p99 và timeout budget là bao nhiêu? |
| Throughput | RPS, concurrent users, batch volume, data growth? |
| Availability | SLO, RTO, RPO và degraded mode? |
| Security | Classification, identity, network boundary, key và audit? |
| Compliance | Residency, retention, transfer và access constraints? |
| Lifecycle | Release cadence, scaling pattern, maintenance window? |
| Cost | Compute, storage, egress, license, support và operations? |

Không chọn placement trước khi biết workload cần truy cập dữ liệu và dependency nào. Một service stateless có thể dễ di chuyển hơn database hoặc hệ thống dùng giao thức legacy gắn với mạng nội bộ.

## 3. Dependency mapping: workload không chạy độc lập

### 3.1. Phân loại dependency

| Loại dependency | Ví dụ | Ảnh hưởng tới placement |
|---|---|---|
| Synchronous API | Booking gọi Inventory | Mỗi network round trip có thể tăng latency |
| Database transaction | ERP ghi order và inventory | Transaction boundary và consistency giới hạn cách tách |
| Event/message | Order event tới notification worker | Có thể bất đồng bộ, nhưng cần delivery/replay semantics |
| Shared identity | SSO, directory, token issuer | Auth path cần reachable và có failure strategy |
| File/data transfer | ETL đọc object storage hoặc NAS | Data volume và egress có thể chi phối cost |
| Legacy protocol | Mainframe, SMB, proprietary TCP | Có thể cần adapter, gateway hoặc network extension |
| External provider | Payment, tax, SMS | Placement phụ thuộc endpoint, quota và contract |
| Operational dependency | KMS, DNS, monitoring, secrets | Workload không hoạt động nếu control/service plane không tới được |

### 3.2. Dependency graph

Ví dụ hệ thống BookingCloud:

~~~mermaid
flowchart TB
    WEB["Web / mobile API"] --> BOOK["Booking service"]
    BOOK --> INV["Inventory service"]
    BOOK --> PAY["Payment provider"]
    BOOK --> DB[("Booking database")]
    INV --> LEGACY["On-prem inventory ERP"]
    BOOK --> BUS[("Event broker")]
    BUS --> NOTIFY["Notification worker"]
    BUS --> ANALYTICS["Analytics pipeline"]
    ANALYTICS --> LAKE[("Cloud data lake")]
    WEB --> IDP["Corporate / cloud identity"]
~~~

Nếu Booking service đặt trên public cloud nhưng Inventory ERP còn ở on-premises, request đặt booking có thể phải đi qua kết nối hybrid. Nếu đường này có latency cao hoặc không ổn định, transaction synchronous có thể bị ảnh hưởng. Một lựa chọn khác là đưa adapter hoặc inventory capability gần ERP, rồi cung cấp API/event tới cloud.

### 3.3. Phân biệt hard và soft dependency

- **Hard dependency:** workload không thể hoàn thành operation nếu dependency không truy cập được, ví dụ authorize payment trong một quy trình cần thanh toán đồng bộ.
- **Soft dependency:** có thể trì hoãn hoặc degrade, ví dụ gửi email xác nhận qua queue sau khi booking đã commit.
- **Optional dependency:** chỉ phục vụ tính năng phụ, ví dụ recommendation.

Định nghĩa này giúp quyết định dependency nào cần kết nối tốc độ cao, dependency nào có thể chuyển thành event-driven và dependency nào không nên nằm trên critical path.

### 3.4. Critical path

Vẽ đường đi quan trọng cho mỗi user journey. Với booking:

1. Authenticate caller.
2. Kiểm tra availability.
3. Hold inventory.
4. Lưu booking.
5. Authorize payment nếu quy trình yêu cầu.
6. Publish event.
7. Gửi notification bất đồng bộ.

Các bước cần consistency hoặc response tức thời thường thuộc critical path. Notification/reporting có thể chạy bất đồng bộ để giảm số lần gọi xuyên cloud/on-premises.

## 4. Data gravity và data ownership

### 4.1. Data gravity

Dataset lớn, có nhiều consumer hoặc thay đổi liên tục thường kéo compute và service về gần nơi lưu trữ. Di chuyển compute nhỏ tới data store có thể rẻ và ít rủi ro hơn chuyển hàng terabyte dữ liệu qua network.

Đánh giá:

- Tổng dung lượng và tốc độ tăng dữ liệu.
- Read/write rate và số query.
- Số workload phụ thuộc.
- Network egress và replication cost.
- Data residency, encryption và key management.
- Backup/restore và lifecycle.
- Thời gian chuyển đổi source of truth.

### 4.2. Source of truth

Mỗi domain dữ liệu cần có nơi authoritative rõ ràng. Ví dụ:

- ERP on-premises là source of truth cho inventory legacy.
- Booking database trên cloud là source of truth cho booking lifecycle.
- Data lake là nơi phân tích, không thay thế transactional database.
- Search index là derived view, có thể rebuild từ authoritative source.

Nếu hai môi trường đều ghi cùng một record mà không có ownership hoặc conflict resolution, hệ thống có nguy cơ split-brain và data inconsistency.

### 4.3. Data placement matrix

| Data class | Vị trí authoritative | Replica/consumer | Consistency phù hợp |
|---|---|---|---|
| Booking transaction | Cloud region chính | DR replica | Strong/transactional theo domain |
| Legacy inventory | On-prem ERP | Cloud API/cache | Cần freshness bound; hold qua owner service |
| Catalog public | Cloud object store | CDN/edge cache | Eventual/cacheable |
| Analytics events | Broker/data lake | Warehouse | Eventual, replayable |
| Identity directory | Identity platform được chọn | Workload token/cache | Theo token/revocation policy |
| Audit records | Security-controlled store | SIEM/archive | Durable, tamper-resistant |

### 4.4. Tránh sao chép mọi dữ liệu

Replica giúp giảm latency hoặc tăng availability, nhưng tăng data movement, key/secret distribution, deletion complexity và compliance surface. Chỉ replicate phần consumer thực sự cần; chọn schema/field tối thiểu; xác định TTL và purge semantics.

Với dữ liệu cá nhân, xóa ở source có thể cần propagate tới cache, search index, lake, backup và provider khác theo retention policy. Placement design cần xử lý lifecycle chứ không chỉ migration lần đầu.

## 5. Latency và network path

### 5.1. End-to-end latency

Thời gian request chịu ảnh hưởng bởi:

\[
T_{\text{total}} =
T_{\text{client}} +
T_{\text{network}} +
T_{\text{queue}} +
T_{\text{compute}} +
T_{\text{data}} +
T_{\text{external}}
\]

Khi hai workload nằm khác môi trường, mỗi synchronous call thường thêm DNS/routing, firewall/proxy, TLS và network round trip. Nếu critical path có nhiều call tuần tự, phần overhead có thể cộng dồn.

### 5.2. Ví dụ nhiều hop

Giả sử request đi:

Client → Cloud API → On-prem adapter → ERP database → Cloud API → Payment provider.

Nếu mỗi round trip hybrid mất 35 ms và quy trình có 4 round trip tuần tự, network overhead đã khoảng 140 ms chưa tính xử lý. Thực tế cần đo từ các vùng mạng và giờ tải khác nhau; không dùng con số minh họa làm cam kết.

### 5.3. Giảm số round trip

- Gom request/batch query nếu business semantics cho phép.
- Chuyển notification/reporting sang event-driven.
- Đặt adapter gần hệ thống legacy.
- Cache dữ liệu đọc nhiều với freshness contract rõ.
- Giữ service và database authoritative cùng placement.
- Tránh call chain sâu qua nhiều cloud/provider.
- Dùng connection pooling, HTTP keep-alive và gRPC/HTTP2 khi phù hợp.

Không biến mọi synchronous call thành async chỉ để giảm latency. Nếu người dùng cần kết quả commit ngay hoặc resource ownership cần kiểm tra online, eventual response có thể không phù hợp.

## 6. Hybrid cloud, multi-cloud và multi-region

| Mô hình | Ý nghĩa | Lý do lựa chọn điển hình |
|---|---|---|
| Hybrid cloud | Kết hợp on-premises/private cloud với public cloud | Legacy, residency, low-latency plant/branch, gradual migration |
| Multi-cloud | Dùng từ hai cloud provider trở lên cho workload hoặc capability | Provider-specific capability, acquisition, risk diversification, contract |
| Multi-region | Chạy cùng provider ở nhiều region | Latency theo geography, disaster recovery, regional resilience |
| Hybrid + multi-cloud | On-prem/private kết hợp nhiều public provider | Nhiều ràng buộc cùng lúc, thường có operational complexity cao |

Multi-region không tự động là multi-cloud; hai region của cùng provider vẫn là một cloud provider. Hybrid cũng không nhất thiết phải có hai provider public cloud.

### 6.1. Vì sao chọn hybrid?

- Hệ thống legacy có giao thức/phần cứng khó di chuyển.
- Dữ liệu hoặc xử lý phải ở một địa điểm cụ thể.
- Workload cần kết nối trực tiếp tới thiết bị, nhà máy hoặc chi nhánh.
- Di chuyển theo từng giai đoạn để giảm cutover risk.
- Một phần hệ thống có license hoặc dependency chỉ hỗ trợ môi trường nhất định.

### 6.2. Vì sao chọn multi-cloud?

- Capability đặc thù của provider phù hợp workload.
- Tổ chức có acquisition hoặc contract tạo ra nhiều cloud.
- Cần giảm phụ thuộc vào một provider cho một capability quan trọng.
- Workload có yêu cầu deployment/market khác nhau.
- Có chiến lược portability có giá trị được kiểm chứng.

Không chọn multi-cloud chỉ vì giả định nó tự động tăng resilience. Nếu ứng dụng, data và operator chưa được thiết kế để failover giữa provider, có nhiều cloud account có thể tăng rủi ro thay vì giảm.

## 7. Placement patterns theo loại workload

### 7.1. Keep, move, split, replace

| Pattern | Mô tả | Khi phù hợp |
|---|---|---|
| Keep | Giữ workload tại vị trí hiện tại | Chi phí di chuyển cao, dependency chặt hoặc chưa có lý do đổi |
| Move | Di chuyển cả workload và dữ liệu | Có thể chuyển boundary trọn vẹn, ít cross-environment calls |
| Split | Tách capability thành workload độc lập | Có domain boundary và data contract rõ |
| Replace | Thay component cũ bằng managed service/API mới | Có thể cải thiện vận hành và chấp nhận migration |
| Replicate | Tạo read model/cache/copy gần consumer | Read-heavy, freshness và lifecycle được xác định |
| Edge | Xử lý gần nguồn hoặc user | Latency/volume cần local processing và logic đủ nhỏ |

### 7.2. Transactional workload

Transaction cần atomicity, isolation và consistency thường nên giữ service với authoritative data store gần nhau. Nếu một transaction cần ghi qua hai môi trường, phải thiết kế distributed transaction, saga hoặc ownership boundary rõ; không dựa vào việc network “thường nhanh”.

### 7.3. Analytics và batch

Analytics có thể chạy nơi data lake/warehouse đặt, giảm di chuyển lượng dữ liệu lớn. Batch có thể được lên lịch ngoài giờ hoặc gần data source để giảm network load. Cần kiểm tra residency, export policy, throughput và data freshness.

### 7.4. Legacy integration

Giữ hệ thống legacy tại chỗ nhưng đặt integration adapter trong cùng network zone là lựa chọn thường gặp. Adapter chuyển protocol, validate identity, map schema và publish event/API ra cloud. Adapter phải có HA, retry, idempotency, monitoring và queue/buffer khi link gián đoạn.

### 7.5. SaaS/third-party

Đôi khi workload không cần đặt ở cloud của doanh nghiệp mà được dùng như SaaS. Cần đánh giá data location, identity federation, export, API quota, audit, service continuity, egress, contract và exit strategy.

## 8. Thiết kế kết nối hybrid và multi-cloud

### 8.1. Connectivity options

| Kết nối | Mô tả | Đánh đổi |
|---|---|---|
| Site-to-site VPN | Tunnel mã hóa qua Internet | Dễ triển khai hơn, latency/jitter và throughput phụ thuộc đường Internet |
| Dedicated private circuit | Kết nối riêng tới provider | Throughput/latency ổn định hơn tùy tuyến, chi phí và lead time cao |
| Transit hub/gateway | Kết nối nhiều VPC/VNet/on-prem | Quản lý route tập trung, cần tránh route leak và shared blast radius |
| Private endpoint | Truy cập managed service qua private path | Giảm public exposure, cần DNS/route/resource policy |
| Public API over TLS | Kết nối qua Internet tới endpoint được công bố | Dễ kết nối nhưng cần secure egress, certificate, auth và rate limit |
| Service mesh federation | Kết nối service identity/policy giữa cluster/environment | Có thể tăng consistency L7, nhưng thêm control plane và complexity |

### 8.2. Network segmentation

Không kết nối toàn bộ mạng on-prem và cloud như một mạng phẳng. Tạo boundary theo environment, data tier và trust domain; route chỉ tới CIDR/service cần thiết; dùng firewall, security group, DNS policy và egress control.

### 8.3. Identity xuyên môi trường

- Dùng federation/workload identity thay credential tĩnh dùng chung.
- Xác minh issuer, audience, subject và trust domain.
- Dùng mTLS cho service connection cần xác thực hai chiều.
- Role riêng cho từng environment/provider.
- Short-lived credential và rotation.
- Audit cross-cloud role assumption và privileged access.

Private connectivity không đồng nghĩa caller được phép truy cập. Network reachability, service authentication và application authorization là ba lớp khác nhau.

### 8.4. DNS và service discovery

Định nghĩa private DNS zone, resolver forwarding và naming convention. Tránh cùng một hostname phân giải sang endpoint khác nhau không có contract rõ. Failover DNS có thể bị cache; cần phối hợp TTL, connection pool, health check và retry.

### 8.5. Observability xuyên môi trường

Chuẩn hóa service name, trace context, correlation ID, timestamp và resource attributes để trace đi qua cloud/on-prem/provider. Không đưa secret, customer payload hay định danh nhạy cảm vào telemetry chỉ để tiện debug.

## 9. Consistency và integration pattern

### 9.1. Synchronous API

Phù hợp khi caller cần kết quả ngay và dependency có latency/availability phù hợp. Phải có timeout, deadline, retry có budget, circuit breaker và idempotency theo operation.

### 9.2. Event-driven integration

Phù hợp khi consumer có thể xử lý sau, link có thể gián đoạn hoặc cần buffer. Cần event schema/version, delivery semantics, idempotent consumer, replay, DLQ và ordering theo domain.

### 9.3. Store-and-forward

Adapter ở on-prem có thể lưu message bền vững cục bộ rồi chuyển khi link cloud trở lại. Cần giới hạn disk, retention, encryption, deduplication và backpressure. Nếu buffer đầy, phải có policy ưu tiên hoặc từ chối rõ.

### 9.4. Data synchronization

Replication/CDC cần xác định:

- Source of truth.
- Ordering và transaction boundary.
- Schema evolution.
- Duplicate/replay behavior.
- Conflict resolution.
- Lag SLA và alert.
- Delete/tombstone propagation.
- Recovery từ full snapshot và incremental log.

Không dùng last-write-wins cho mọi domain. Inventory/booking có invariant nghiệp vụ cần conflict policy cụ thể.

## 10. Resilience: khi một môi trường không thể truy cập

### 10.1. Failure scenario

- VPN/private circuit bị đứt.
- Provider region/service outage.
- DNS forwarding hoặc identity federation lỗi.
- Firewall/route update sai.
- Certificate hết hạn.
- Replication lag tăng.
- API provider throttling hoặc quota exceeded.
- Control plane một môi trường không triển khai được resource.

### 10.2. Degraded mode

Định nghĩa thao tác nào tiếp tục được khi dependency mất:

| Capability | Khi link hybrid mất | Hành vi khả dĩ |
|---|---|---|
| Đọc catalog cacheable | Có thể tiếp tục | Dùng cache trong freshness bound |
| Tạo booking cần inventory authoritative | Có thể không an toàn | Từ chối/pending, không xác nhận availability giả |
| Notification | Có thể trì hoãn | Lưu queue và retry bounded |
| Analytics ingestion | Có thể buffer | Store-and-forward và xử lý sau |
| Payment authorization | Theo provider path | Unknown outcome cần reconcile, không charge lại mù |
| Admin operation | Có thể chặn | Fail closed và dùng break-glass được audit |

### 10.3. RTO/RPO và failover

RTO là thời gian mục tiêu để khôi phục dịch vụ; RPO là mức mất dữ liệu tối đa chấp nhận được. Với hybrid/multi-cloud, cần tính thêm thời gian DNS, credential, network route, quota, image/secret availability, data replication và operator action.

Một bản sao dữ liệu ở provider khác không đủ chứng minh DR. Phải chạy restore/failover test với workload và dependency thật.

## 11. Security và governance xuyên cloud

### 11.1. Control consistency

Chuẩn hóa baseline:

- Identity federation, MFA, privileged access và short-lived credential.
- Encryption in transit/at rest và key ownership.
- Network segmentation, private endpoint và egress controls.
- Logging/audit với retention và access policy.
- Vulnerability/image scanning và patch policy.
- Backup, restore, data classification và deletion.
- Policy as code và exception expiry.

Provider-specific control cần được map về cùng yêu cầu bảo mật, không giả định cùng tên dịch vụ có semantics giống nhau.

### 11.2. Data residency và cross-border transfer

Xác định data class nào được lưu, xử lý, replicate, backup hoặc support từ mỗi geography. Cross-cloud transfer, telemetry export và backup replication cũng có thể là data movement cần review.

Đối với nghĩa vụ pháp lý cụ thể, cần security/legal/privacy owner xác nhận theo loại dữ liệu, thị trường, hợp đồng và mục đích xử lý; kiến trúc không tự suy ra compliance từ region selection.

### 11.3. Shared responsibility

Mỗi provider có ranh giới trách nhiệm khác nhau giữa provider và customer. Managed service giảm việc vận hành phần cứng, nhưng customer vẫn thường chịu trách nhiệm identity, data access, configuration, secret, logging và workload security. Lập control ownership matrix cho mỗi platform/service.

## 12. Chi phí thật của hybrid và multi-cloud

### 12.1. Chi phí thường bị bỏ sót

- Egress và inter-region/inter-cloud data transfer.
- Dedicated connectivity, VPN gateway, transit hub và firewall.
- Replication, CDC, backup và duplicate storage.
- Observability ingestion/export giữa hệ thống.
- License portability, support plan và marketplace charge.
- Network/security appliance và certificate lifecycle.
- Cross-cloud identity, DNS và secrets integration.
- Kỹ năng vận hành nhiều control plane và on-call coverage.
- Migration, testing, compliance và exit/egress khi chuyển provider.

### 12.2. Total cost of ownership

Không so sánh chỉ giá VM hoặc database. TCO nên gồm compute, storage, network, managed services, software license, support, operations, security, compliance, migration và DR.

Có thể đo:

\[
\text{Cost per business transaction} =
\frac{\text{Total hybrid/multi-cloud cost}}
{\text{Successful business transactions}}
\]

Phân bổ shared cost theo quy tắc nhất quán. So sánh cùng workload, SLO, retention, security và availability assumptions.

### 12.3. Data transfer amplification

Một payload nhỏ có thể dẫn tới nhiều lần query, log/trace export, retry, CDC và replica update. Đo bytes thực tế theo source/destination/workload. Cache hoặc batch có thể giảm transfer nhưng cần freshness và consistency policy.

## 13. Operating model cho nhiều môi trường

### 13.1. Platform ownership

Xác định team chịu trách nhiệm:

- Landing zone/account/subscription và network hub.
- Identity federation và secret/key management.
- Connectivity, DNS và firewall.
- IaC module, pipeline và policy.
- Observability, incident response và cost allocation.
- Data governance, backup và recovery.

### 13.2. Golden path

Tạo mẫu triển khai đã được kiểm soát cho workload mới: network pattern, identity, logging, metrics, trace, deployment, quota, backup và tag. Team sản phẩm chọn từ các pattern được hỗ trợ thay vì tự thiết kế mọi provider integration.

### 13.3. Incident command xuyên môi trường

Runbook phải cho biết ai có thể:

- Kiểm tra provider status và support case.
- Route traffic hoặc disable integration.
- Revoke credential/certificate.
- Failover data/compute.
- Replay event và reconcile.
- Thông báo business/customer.

Cross-cloud incident có thể liên quan nhiều support organization và timezone; cần correlation ID, evidence bundle và escalation contact đã chuẩn bị trước.

## 14. Migration và thay đổi placement

### 14.1. Migration pattern

| Pattern | Mô tả | Rủi ro chính |
|---|---|---|
| Rehost | Chuyển gần như nguyên trạng | Giữ nguyên technical debt và network dependency |
| Replatform | Thay một phần runtime/managed service | Compatibility và behavior change |
| Refactor | Tách workload theo domain/API/event | Data ownership và distributed complexity |
| Repurchase | Chuyển sang SaaS | Integration, data export/exit và contract |
| Retain | Giữ workload tại chỗ | Tiếp tục vận hành legacy |
| Retire | Loại bỏ workload không còn cần | Hidden dependency và owner không rõ |

### 14.2. Migration waves

Nhóm workload theo dependency và data boundary. Chuyển các thành phần ít phụ thuộc trước, sau đó adapter/integration và workload có critical transaction. Không chia wave chỉ theo phòng ban nếu các hệ thống cùng chia sẻ database hoặc transaction.

### 14.3. Cutover và rollback

- Đồng bộ dữ liệu trước cutover.
- Định nghĩa freeze/write ownership.
- Dùng DNS/routing hoặc feature flag theo kế hoạch.
- So sánh record count, checksum và business invariant.
- Theo dõi error, latency và replication lag.
- Có rollback window và điều kiện kích hoạt rõ.
- Tránh hai nơi cùng nhận write trong thời gian chưa có conflict policy.

### 14.4. Strangler pattern

Có thể đặt façade/API gateway trước legacy system rồi chuyển từng capability sang workload mới. Façade định tuyến theo domain/operation; dữ liệu và event được chuyển dần. Cần tránh proxy trở thành bottleneck hoặc nơi chứa toàn bộ business logic mới.

## 15. Placement decision matrix

Chấm điểm từng workload theo tiêu chí, đồng thời đặt hard constraint trước scoring:

| Tiêu chí | Câu hỏi | Ví dụ trọng số |
|---|---|---:|
| Dependency locality | Có bao nhiêu critical dependency ở cùng môi trường? | 20% |
| Data locality/gravity | Data size, write ownership và transfer cost? | 20% |
| Latency | Critical path có đáp ứng p95/p99? | 20% |
| Compliance/security | Residency, identity và control có đáp ứng? | Hard gate |
| Reliability | Failure mode, RTO/RPO và provider dependency? | 15% |
| Cost | Compute, egress, operations và support? | 15% |
| Operability | Team có skill, tooling và on-call? | 10% |

Trọng số chỉ là ví dụ. Nếu residency hoặc security là hard requirement thì không bù được bằng điểm cost/performance cao. Những phương án không đạt hard gate cần bị loại trước khi so sánh tổng điểm.

### 15.1. Ví dụ placement cho BookingCloud

| Workload | Placement đề xuất | Lý do |
|---|---|---|
| Public API/frontend | Public cloud region gần user | Scale, ingress và managed compute |
| Booking service | Cùng region với authoritative booking DB | Transaction latency/consistency |
| Legacy inventory ERP | On-premises/private environment | Data ownership và dependency cũ |
| Inventory adapter | Gần ERP, expose secured API/event | Tránh nhiều round trip qua link hybrid |
| Notification worker | Cloud region | Có thể xử lý async, scale độc lập |
| Analytics pipeline | Cloud gần data lake/warehouse | Compute gần dữ liệu lớn |
| Audit store | Vị trí được security/data policy duyệt | Retention, integrity và residency |
| DR workload | Region khác theo RTO/RPO | Failure-domain separation |

Đây là một phương án tham khảo. Placement thực tế cần đo link hybrid, database latency, data residency, provider quota và cost.

## 16. Đánh giá theo Well-Architected

| Góc nhìn | Câu hỏi review | Bằng chứng cần có |
|---|---|---|
| **Operational Excellence** | Ai sở hữu từng môi trường, network, identity và incident handoff? | Dependency map, golden path, runbook, service catalog |
| **Security** | Identity, encryption, egress, data residency và audit có nhất quán? | Trust model, access review, data-flow map, policy tests |
| **Reliability** | Link/provider/region mất thì operation nào tiếp tục, failover ra sao? | RTO/RPO, store-and-forward, restore/failover exercise |
| **Performance Efficiency** | Critical path có nhiều cross-environment hop? Compute có gần data? | p95/p99, trace, replication lag, data transfer |
| **Cost Optimization** | Egress, duplicate data và operational overhead có đáng giá? | TCO, cost per transaction, network bill, utilization |
| **Sustainability** | Có copy, compute hoặc network traffic dư thừa? | Data lifecycle, idle resource, transfer efficiency |

Không có một placement tối ưu cho tất cả workload. Ranh giới đúng thường theo capability và ownership: giữ transaction cùng authoritative data; đặt batch/analytics gần dữ liệu; dùng event cho dependency có thể trì hoãn; và chỉ thêm provider/region khi lợi ích được đo và vận hành được.

## 17. Bài thực hành: phân chia workload cho BookingCloud

BookingCloud có một ERP inventory chạy tại data center, API booking chạy trên public cloud, analytics ở data warehouse, payment provider ở bên ngoài và người dùng ở nhiều thị trường. Một số request booking bị chậm khi ERP bận; dữ liệu catalog được đọc nhiều; team muốn đưa thêm workload sang provider thứ hai.

Hãy thực hiện:

**Bài 1 — Workload inventory:** phân rã capability thành API, booking, inventory, payment, notification, analytics, identity và audit; ghi owner cùng SLO.

**Bài 2 — Dependency map:** phân loại hard/soft dependency, synchronous/event-driven và xác định critical path.

**Bài 3 — Data ownership:** xác định source of truth cho booking, inventory, catalog và analytics; nêu dữ liệu được replicate.

**Bài 4 — Placement matrix:** so sánh on-prem, private cloud, provider A, provider B và edge theo dependency, data, latency, residency, reliability, cost và operability.

**Bài 5 — Integration:** thiết kế adapter gần ERP, private connectivity, identity federation, mTLS, DNS và event buffer.

**Bài 6 — Consistency:** xử lý inventory hold, replica lag, duplicate event và response timeout.

**Bài 7 — Resilience:** mô tả degraded mode khi link hybrid/provider mất; tính RTO/RPO và failover behavior.

**Bài 8 — Cost:** tính egress, replication, duplicate storage, connectivity, observability và support cost.

**Bài 9 — Migration:** lập wave, cutover, validation, rollback và ownership sau chuyển đổi.

### Khung tự kiểm tra

| Quyết định | Cần chứng minh |
|---|---|
| Giữ ERP on-prem | Có lý do data/dependency/latency hoặc migration risk cụ thể |
| Đặt adapter gần ERP | Giảm round trip và có buffer khi link mất |
| Booking service gần database | Transaction path đáp ứng latency/consistency |
| Replicate catalog | Có freshness, invalidation và ownership |
| Dùng event cho notification | Consumer idempotent, retry/DLQ và replay an toàn |
| Thêm provider thứ hai | Capability và exit/resilience benefit lớn hơn complexity/TCO |
| Failover hybrid | Có credential, quota, route, data và runbook thực sự hoạt động |

## 18. Checklist trước khi chốt workload placement

- [ ] Mỗi workload có owner, business criticality, SLO và profile.
- [ ] Dependency graph phân biệt hard/soft và synchronous/asynchronous.
- [ ] Critical path và số network round trip được đo.
- [ ] Source of truth và data ownership được xác định.
- [ ] Data gravity, replication, freshness, conflict và deletion được thiết kế.
- [ ] Region/provider/on-prem placement đáp ứng latency và residency.
- [ ] Network connectivity, routing, DNS, segmentation và egress có owner.
- [ ] Workload identity, mTLS, secret và authorization được thiết kế xuyên môi trường.
- [ ] RTO/RPO, degraded mode, failover và restore đã được test.
- [ ] Quota/capacity và provider API limits đủ cho steady/peak/failover.
- [ ] Egress, replication, connectivity, license, support và operation cost nằm trong TCO.
- [ ] Observability correlation xuyên cloud/on-prem được kiểm chứng.
- [ ] Migration wave, cutover, rollback và reconciliation có kế hoạch.
- [ ] Có incident runbook, support contact và ownership rõ ràng.

Phân chia workload theo dependency, dữ liệu và độ trễ giúp chọn nơi chạy phù hợp với bản chất của từng capability. Giữ transaction gần authoritative data, đưa compute tới dataset lớn khi hợp lý, chuyển dependency không critical sang event và chỉ mở rộng sang nhiều cloud khi lợi ích được chứng minh. Một kiến trúc hybrid/multi-cloud tốt phải vận hành được khi network, provider hoặc một môi trường gặp sự cố, đồng thời giữ consistency, security, residency, performance và tổng chi phí trong giới hạn đã cam kết.
