# Thiết kế active–passive và active–active nhiều khu vực

Khi một ứng dụng phục vụ người dùng ở nhiều quốc gia hoặc cần tiếp tục hoạt động khi một khu vực cloud gặp sự cố, kiến trúc một region có thể không đáp ứng mục tiêu độ trễ và phục hồi. Triển khai ở nhiều region mở ra khả năng phân phối traffic gần người dùng, duy trì dịch vụ khi một region mất khả năng phục vụ và đáp ứng yêu cầu đặt dữ liệu theo địa lý. Tuy nhiên, nhiều region cũng làm tăng độ phức tạp của định tuyến, replication, consistency, identity, bảo mật, vận hành và chi phí.

Hai mô hình phổ biến là **active–passive** và **active–active**. Trong active–passive, một region chính xử lý workload, region còn lại được duy trì để tiếp quản khi cần. Trong active–active, nhiều region cùng phục vụ traffic bình thường. Không có mô hình nào luôn tốt hơn: lựa chọn phụ thuộc RTO/RPO, latency, tính chất dữ liệu, khả năng xử lý xung đột, giới hạn nghiệp vụ và năng lực vận hành.

Bài học thuộc chương **Kiến trúc toàn cầu** của lộ trình **Cloud Architecture**. Lộ trình hướng dẫn thiết kế ứng dụng cloud từ yêu cầu nghiệp vụ tới mạng, compute, dữ liệu và mô hình triển khai, cân bằng độ tin cậy, bảo mật, khả năng mở rộng, chi phí và vận hành. Bài này tập trung vào việc lựa chọn topology nhiều region, định nghĩa quyền ghi, định tuyến người dùng, phục hồi và kiểm chứng bằng diễn tập.

Sau bài học, bạn có thể:

- Phân biệt active–passive, active–active và các biến thể hybrid.
- Chọn mô hình theo RTO, RPO, latency, data residency và business continuity.
- Thiết kế global traffic management, health routing và regional failover.
- Chọn replication đồng bộ/bất đồng bộ và xác định consistency boundary.
- Thiết kế single-writer, home-region, partitioned ownership hoặc multi-writer có conflict policy.
- Xử lý split-brain, stale replica, failover và failback.
- Tách control plane khỏi data plane và tránh dependency toàn cục không cần thiết.
- Lập kế hoạch capacity, security, observability, cost và DR testing cho nhiều region.

## 1. Vì sao triển khai nhiều region?

Một region thường gồm nhiều availability zone nhưng vẫn có thể chịu sự cố ảnh hưởng toàn khu vực, như lỗi control plane, network, dịch vụ dùng chung hoặc sự cố địa lý. Multi-region có thể giảm phụ thuộc vào một region và cải thiện trải nghiệm cho người dùng ở các vị trí xa.

Các mục tiêu thường gặp:

- **Business continuity:** tiếp tục phục vụ khi region chính bị sự cố.
- **Lower user latency:** đưa compute và dữ liệu gần nhóm người dùng.
- **Data residency:** giữ dữ liệu hoặc xử lý trong khu vực được phép.
- **Resilience:** giảm blast radius của lỗi ở một region.
- **Capacity distribution:** phân chia workload theo địa lý hoặc tenant.
- **Maintenance flexibility:** nâng cấp một region trong khi region khác tiếp tục phục vụ, nếu kiến trúc hỗ trợ.

Multi-region không tự bảo đảm các mục tiêu này. Nếu cả hai region dùng chung một identity provider, DNS control plane, KMS dependency hoặc database writer đặt tại một nơi, sự cố của dependency chung vẫn có thể làm toàn hệ thống gián đoạn.

## 2. Active–passive là gì?

Trong mô hình active–passive, một region là primary/active và xử lý phần lớn hoặc toàn bộ write traffic bình thường. Region passive được chuẩn bị để tiếp quản khi primary không còn khả năng phục vụ.

Region passive có thể ở các trạng thái:

- **Warm standby:** compute và các dependency cốt lõi đã chạy ở mức capacity thấp; cần scale trước khi nhận full traffic.
- **Pilot light:** chỉ các thành phần dữ liệu/identity hoặc thành phần tối thiểu chạy thường xuyên; phần lớn compute được provision khi disaster xảy ra.
- **Cold standby:** tài nguyên được tạo sau khi sự cố xảy ra; thời gian phục hồi dài hơn.
- **Hot standby:** hạ tầng và dữ liệu luôn sẵn sàng gần mức production; có thể chuyển traffic nhanh hơn nhưng tốn chi phí hơn.

### 2.1. Topology active–passive

~~~mermaid
flowchart TB
    U["Global users"] --> G["Global traffic manager"]
    G --> A["Region A: Active"]
    G -. "Standby target" .-> B["Region B: Passive"]
    subgraph RA["Primary region"]
        A --> APP_A["Application fleet"]
        APP_A --> DB_A[("Primary database")]
    end
    subgraph RB["Recovery region"]
        B --> APP_B["Warm standby application"]
        APP_B --> DB_B[("Replicated database")]
    end
    DB_A -. "Async replication" .-> DB_B
~~~

Trong thời gian bình thường, Region A nhận write. Region B nhận replication và có thể chạy read-only health check hoặc workload giới hạn. Khi failover, hệ thống phải xác định authority, promote data store ở B, fence writer A và chuyển traffic theo một quy trình có kiểm soát.

### 2.2. Ưu điểm và giới hạn

Ưu điểm là write ownership đơn giản hơn, ít conflict và dễ giữ invariant dữ liệu. Chi phí compute ở passive region có thể thấp hơn nếu dùng pilot light/warm standby.

Giới hạn là người dùng ở vùng xa vẫn phải gọi về active region trong điều kiện bình thường; failover có thể mất dữ liệu đã commit nhưng chưa replicate nếu replication bất đồng bộ; capacity passive có thể không đủ; và failback cần kế hoạch riêng.

## 3. Active–active là gì?

Trong active–active, hai hoặc nhiều region cùng nhận traffic bình thường. Traffic có thể được định tuyến theo vị trí người dùng, latency, tenant ownership hoặc thuật toán cân bằng tải.

Active–active không nhất thiết có nghĩa mọi dữ liệu đều được ghi tự do ở mọi region. Có thể có active–active ở tầng stateless/API nhưng single-writer ở tầng data; hoặc partitioned write ownership theo tenant/aggregate. Phải mô tả chính xác lớp nào active–active.

~~~mermaid
flowchart TB
    U["Global users"] --> G["Global traffic manager"]
    G --> A["Region A: Active"]
    G --> B["Region B: Active"]
    subgraph RA["Region A"]
        A --> APP_A["Application fleet A"]
        APP_A --> DB_A[("Regional data A")]
    end
    subgraph RB["Region B"]
        B --> APP_B["Application fleet B"]
        APP_B --> DB_B[("Regional data B")]
    end
    DB_A <-->|"Replication / conflict policy"| DB_B
~~~

### 3.1. Ưu điểm và giới hạn

Active–active có thể giảm latency cho người dùng ở nhiều khu vực, sử dụng capacity của nhiều region trong điều kiện bình thường và giảm nhu cầu scale-up một passive region sau disaster.

Đổi lại, routing, data ownership và consistency phức tạp hơn. Nếu nhiều nơi ghi cùng một entity, cần protocol giải quyết concurrent update. Nếu không, hệ thống có nguy cơ lost update, duplicate booking, double spend hoặc split-brain.

## 4. Phân biệt mô hình ở từng lớp

Một sai lầm thường gặp là gọi toàn bộ hệ thống active–active chỉ vì có application instances tại hai region. Cần mô tả topology ở từng lớp.

| Lớp | Active–passive | Active–active |
| --- | --- | --- |
| Global DNS/traffic | Route tới primary, standby khi cần | Route đồng thời nhiều region |
| Web/API compute | Primary nhận traffic; passive scale khi failover | Nhiều region xử lý request |
| Database write | Một primary | Multi-writer hoặc partitioned/single-writer theo ownership |
| Database read | Replica/standby read nếu an toàn | Regional read replica hoặc local data |
| Queue/worker | Primary xử lý; passive standby | Nhiều region consumer/producer theo partition |
| Cache | Primary hoặc warm cache passive | Cache local mỗi region, cần invalidation strategy |
| Identity | Có recovery path | Federated/local verification hoặc dependency global có HA |
| Control plane | Có thể quản trị từ primary | Quản lý nhiều region, cần tránh dependency runtime |
| Observability | Có thể tập trung | Regional collection và aggregation đa vùng |

Một hệ thống có thể chọn active–active compute, active–passive database writer và local read replicas. Đây thường là hybrid hợp lý nếu latency đọc quan trọng nhưng write consistency cần đơn giản.

## 5. Chọn theo RTO và RPO

**RTO (Recovery Time Objective)** là thời gian mục tiêu để phục hồi dịch vụ. **RPO (Recovery Point Objective)** là mức mất dữ liệu tối đa được chấp nhận, thường đo bằng khoảng thời gian dữ liệu có thể bị mất.

Active–passive có thể đạt RTO thấp với hot/warm standby và automated failover, nhưng RPO phụ thuộc replication mode và log durability. Active–active có thể duy trì traffic ở region khác khi một vùng lỗi, song RPO không tự bằng 0: asynchronous replication vẫn có lag và concurrent write vẫn có thể conflict.

| Nhu cầu | Mô hình có thể phù hợp | Điều cần xác minh |
| --- | --- | --- |
| RTO dài, chi phí DR thấp | Pilot light/cold standby | Thời gian provision và restore có nằm trong RTO? |
| RTO trung bình, RPO thấp | Warm standby + replication thường xuyên | Lag và promotion procedure |
| RTO rất thấp, một writer | Hot standby + automated failover có fencing | Writer authority, capacity và route propagation |
| Latency thấp cho nhiều vùng | Active–active compute/read | Data ownership và regional dependency |
| Ghi cục bộ ở nhiều vùng | Active–active data | Conflict semantics, ordering và business invariant |
| Data residency theo tenant | Home-region/partitioned ownership | Replication và support access có tuân thủ? |

Mục tiêu cần gắn với hành trình nghiệp vụ. Payment ledger, booking, search index và notification có thể có RPO/RTO khác nhau. Không nên đưa một con số RPO/RTO chung cho toàn bộ platform nếu các dataset có đặc tính khác nhau.

## 6. Global traffic management

Global traffic manager quyết định client được đưa tới region nào. Các phương pháp thường gặp:

- **Geo routing:** route theo vị trí địa lý hoặc policy data residency.
- **Latency-based routing:** chọn endpoint có latency đo được thấp.
- **Weighted routing:** phân bổ tỷ lệ traffic cố định hoặc tăng dần.
- **Failover routing:** ưu tiên primary, chuyển sang standby khi health policy thất bại.
- **Anycast/global edge:** đưa client tới điểm vào gần nhất, sau đó route nội bộ.
- **Tenant/home-region routing:** tenant luôn được đưa tới region sở hữu dữ liệu.

### 6.1. Health check cần phản ánh khả năng phục vụ

Health check chỉ kiểm tra process còn sống là chưa đủ. Một region có thể trả HTTP 200 nhưng database writer, queue hoặc identity dependency đã không khả dụng. Ngược lại, health check phụ thuộc mọi optional service có thể loại bỏ một region dù chức năng chính vẫn hoạt động.

Nên phân biệt:

- **Liveness:** process có cần restart không?
- **Readiness:** instance có thể nhận request này không?
- **Regional service health:** region có đáp ứng critical path và capacity không?
- **Dependency health:** các dependency bắt buộc có còn hoạt động?
- **Synthetic business check:** một hành trình nghiệp vụ mẫu có hoạt động không?

Tránh health check gây failover vòng lặp: traffic chuyển vùng làm tải tăng, health check vùng mới fail, traffic lại chuyển ngược. Dùng hysteresis, cooldown, threshold và manual override phù hợp.

## 7. DNS, TTL và connection behavior

DNS failover không tức thời đối với mọi client. Resolver, browser, operating system, proxy và connection pool có thể cache địa chỉ; connection đang mở có thể tiếp tục tới endpoint cũ.

Cần hiểu:

- DNS TTL và negative caching.
- Resolver/client có tuân TTL không.
- Load balancer/global accelerator có health propagation time nào.
- HTTP keep-alive, HTTP/2 connection và gRPC channel có được drain/reconnect không.
- Mobile client có thể offline lâu rồi reconnect.
- Callback/webhook có thể quay về endpoint cũ.
- Certificate/SAN có phù hợp hostname sau failover không.

Không dựa vào DNS TTL thấp như cơ chế fencing. DNS chỉ hướng traffic; nó không thu hồi quyền ghi của writer cũ hoặc session đã kết nối.

## 8. Data replication: synchronous và asynchronous

Replication chuyển dữ liệu từ một region/node sang region khác. Hai kiểu chính có trade-off khác nhau.

### 8.1. Synchronous replication

Write chỉ được xác nhận sau khi các replica cần thiết đã xác nhận durable theo semantics hệ thống. Điều này có thể giảm RPO nhưng thêm network latency và phụ thuộc vào kết nối liên vùng.

Nếu link liên vùng chậm hoặc mất, write có thể bị block/giảm availability tùy protocol. Cần hiểu quorum, acknowledgment level và failure behavior thực tế.

### 8.2. Asynchronous replication

Primary xác nhận write trước khi replica ở region khác nhận đủ dữ liệu. Điều này giảm latency ghi trong primary region và tăng khả năng tiếp tục ghi khi link chậm, nhưng có replication lag và có thể mất một phần dữ liệu khi primary bị mất đột ngột.

### 8.3. So sánh

| Tiêu chí | Synchronous | Asynchronous |
| --- | --- | --- |
| Write latency | Thường cao hơn do round trip | Thường thấp hơn tại primary |
| Data loss khi failover | Có thể thấp hơn theo commit/quorum guarantees | Có thể mất log chưa replicate |
| Phụ thuộc network liên vùng | Cao | Thấp hơn cho write path |
| Availability khi partition | Có thể dừng write nếu không đạt quorum | Primary có thể tiếp tục tùy kiến trúc |
| Complexity | Quorum/commit semantics | Lag monitoring và recovery point |
| Use case | Dữ liệu cần durability nghiêm ngặt trong phạm vi hỗ trợ | DR, read replica, analytics hoặc use case chấp nhận lag |

Không có cam kết “zero data loss” chỉ từ nhãn synchronous. Cần kiểm tra database/provider, failure model, quorum và xác nhận client nhận commit ở thời điểm nào.

## 9. Quyền ghi dữ liệu: single-writer, home-region và multi-writer

Đây là quyết định quan trọng nhất trong active–active.

- **Single-writer:** một writer authoritative cho toàn bộ dataset hoặc cluster.
- **Home-region per tenant/aggregate:** mỗi tenant hoặc aggregate có một region sở hữu write.
- **Partitioned ownership:** dữ liệu chia shard/partition; mỗi partition có owner rõ ràng.
- **Multi-writer:** nhiều region có thể ghi cùng dữ liệu, với protocol/semantics giải quyết conflict.
- **Read-local/write-home:** đọc ở region gần, ghi chuyển về region sở hữu dữ liệu.

Với booking, inventory và ledger, single-writer/home-region thường dễ giữ invariant hơn. Với profile/preferences hoặc dữ liệu có phép hợp nhất commutative, multi-writer có thể phù hợp hơn nếu conflict semantics đã được chứng minh.

### 9.1. Home-region routing

Tenant directory có thể ánh xạ tenant tới home region. Request được route tới region đó để thực hiện write; các region khác phục vụ read theo policy. Khi chuyển home region, cần migration dữ liệu, writer fencing và cập nhật routing có version.

Directory là dependency quan trọng. Cần cache signed/versioned mapping, có HA và quy trình khi không thể tra cứu. Cache stale không được phép khiến hai region cùng tin mình là home writer.

## 10. Consistency và conflict resolution

Khi hai region cùng nhận cập nhật, cần xác định semantics:

- **Strong consistency:** thao tác nhìn thấy thứ tự nhất quán theo guarantee của hệ thống, thường cần coordination và có thể tăng latency/giảm availability khi partition.
- **Eventual consistency:** replica hội tụ sau khi thông tin được truyền, nhưng trong thời gian đó có thể đọc thấy dữ liệu cũ.
- **Causal consistency:** giữ thứ tự nhân quả trong phạm vi được xác định.
- **Read-your-writes:** client thấy update của chính mình sau khi ghi theo session/context.
- **Monotonic reads:** client không quay về version cũ hơn trong session.

Conflict policy có thể gồm optimistic concurrency, version check, domain-specific resolution, CRDT cho cấu trúc phù hợp hoặc manual reconciliation. Last-write-wins không nên được áp dụng mù quáng cho trạng thái tài chính, booking hoặc inventory.

## 11. Tránh split-brain và fencing

Split-brain xảy ra khi hai node/region cùng tin rằng mình có quyền ghi authoritative cho cùng một dữ liệu. DNS failover hoặc health timeout không đủ để ngăn tình huống này.

Các kiểm soát:

- Quorum/consensus hoặc coordinator có authority rõ.
- Leader epoch/generation tăng đơn điệu.
- Lease có semantics và clock assumption được hiểu rõ.
- Fencing token được kiểm tra tại resource ghi.
- Database writer endpoint/role chỉ cho một authority.
- Revoke session/credential/network path của writer cũ.
- Không promote standby trước khi xác minh writer cũ đã được fence.

~~~mermaid
sequenceDiagram
    participant C as Coordinator
    participant A as Region A writer
    participant B as Region B candidate
    participant D as Protected database

    C->>A: Grant epoch 17
    A->>D: Write with epoch 17
    D-->>A: Accepted
    Note over A,B: Network partition
    C->>B: Grant epoch 18 after authority decision
    B->>D: Register epoch 18
    D-->>B: Accepted
    A->>D: Delayed write with epoch 17
    D-->>A: Reject stale epoch
~~~

Nếu storage/database không hỗ trợ fencing token trực tiếp, phải dùng cơ chế promotion/revoke/network/credential ở lớp khác và chứng minh nó thực sự chặn writer cũ. Không mở write khi authority còn mơ hồ.

## 12. Stateless compute và regional data

Active–active compute thường dễ triển khai hơn active–active data nếu ứng dụng stateless hoặc giữ state ngoài process. Mỗi region có thể chạy cùng application version, được route traffic độc lập.

Cần bảo đảm:

- Image/config/version giống hoặc tương thích.
- Session không phụ thuộc memory cục bộ; dùng token hoặc shared/session store theo policy.
- Regional endpoint và secret/certificate hoạt động.
- Feature flag/config có consistency phù hợp.
- Background job không chạy trùng ngoài ý muốn.
- Scheduled task có leader/lease hoặc partition ownership.
- Rate limit/quota có policy global hoặc regional rõ.
- Dependencies đủ capacity trong failover.

Stateless không có nghĩa không có state; state được chuyển sang database, cache, queue, object storage hoặc external service. Những nơi đó cần topology và recovery riêng.

## 13. Cache và session nhiều region

Cache local giảm latency nhưng có thể stale hoặc không đồng bộ. Cần xác định loại dữ liệu nào chấp nhận eventual consistency và cơ chế invalidation.

Các mẫu:

- Local cache theo region với TTL.
- Distributed cache global hoặc regional replication.
- Cache-aside với source of truth tập trung.
- Versioned cache key hoặc invalidation event.
- Session token stateless có signature/expiry.
- Session store theo home region.

Không dùng local cache stale để ra quyết định nhạy cảm như quyền truy cập, payment authorization hoặc inventory reservation nếu semantics không cho phép. TTL là giới hạn stale theo thời gian nhưng không bảo đảm invalidation tức thì.

## 14. Queue, event và background processing đa region

Queue có thể đặt tại mỗi region hoặc dùng broker đa vùng. Cần xác định message ownership, ordering, duplicate và failover semantics.

Một số lựa chọn:

- Regional queue với producer/consumer local; replicate event sang region khác.
- Global broker có partition/replication topology rõ.
- Home-region queue theo tenant.
- Outbox/event log authoritative ở một region.
- Cross-region forwarding với idempotent consumer.

Không để hai region cùng xử lý một scheduled job hoặc message partition nếu không có ownership/lease/idempotency. Khi failover, cần kiểm tra offset/checkpoint và message đã được ack nhưng chưa replicate.

## 15. Control plane và data plane

Control plane quản lý provisioning, configuration, routing policy, deployment và policy. Data plane xử lý request nghiệp vụ. Một thiết kế bền vững không nên phụ thuộc vào control plane toàn cục cho mọi request runtime.

Ví dụ nếu global control plane tạm thời không truy cập được, các region vẫn có thể tiếp tục phục vụ với cấu hình đã xác thực và cached policy trong giới hạn an toàn. Tuy nhiên, thay đổi nhạy cảm như revoke quyền hoặc chuyển writer cần được phối hợp đúng.

Cần định nghĩa:

- Chức năng nào phải hoạt động khi control plane mất?
- Config nào được dùng last-known-good và trong bao lâu?
- Routing policy version được phân phối thế nào?
- Ai có quyền chuyển writer hoặc đổi home region?
- Làm sao tránh hai control plane độc lập cấp authority xung đột?
- Recovery metadata và audit được lưu ở đâu?

## 16. Security và identity đa vùng

Multi-region mở rộng security boundary: identity, secrets, KMS, certificate, network và operator access cần hoạt động ở các region mà không làm credential lan rộng không cần thiết.

Nguyên tắc:

- Workload identity riêng theo region/environment.
- Least privilege theo service và resource.
- Secret replication có policy và scope rõ.
- Key policy/replica key tuân yêu cầu data residency.
- TLS certificate SAN và trust chain phù hợp endpoint global/regional.
- mTLS identity giữa service và region.
- Audit log được tập hợp nhưng có thể giữ bản sao local theo policy.
- Operator break-glass có thời hạn và audit.
- Network segmentation và egress control theo region.
- Kiểm soát cross-region data transfer và support access.

Không replicate toàn bộ secrets sang mọi region nếu workload không cần. Việc failover phải có một đường cấp credential hợp lệ, nhưng không mở quyền truy cập rộng hơn cần thiết.

## 17. Data residency và sovereignty

Một tenant có thể yêu cầu dữ liệu lưu trong một quốc gia/khu vực. Điều này ảnh hưởng primary storage, replica, backup, logs, analytics, key material, support access và processing.

Cần xác định chính xác dữ liệu nào chịu yêu cầu: content, metadata, backup, telemetry, support artifact hay derived data. Không giả định chỉ database primary ở region địa phương là đủ nếu log hoặc backup được gửi toàn cầu.

Các mô hình:

- Home-region per tenant, không replicate dữ liệu nhạy cảm ra ngoài vùng.
- Cross-region replication trong một geography được chấp thuận.
- Replicate metadata/aggregate đã giảm định danh.
- DR trong cùng vùng pháp lý nhưng khác zone.
- Dùng regional key boundary hoặc customer-managed key phù hợp.

Data residency có thể xung đột với mục tiêu DR nếu không có region phục hồi hợp lệ. Cần xác định trước vùng DR được phép và thời gian phục hồi có thể đạt.

## 18. Capacity planning và failover readiness

Active–passive cần passive region có đủ capacity để nhận tải khi failover. Active–active cần mỗi region có headroom để tiếp nhận traffic chuyển từ region khác.

Ví dụ hai region chia đều 50/50. Nếu một region mất, region còn lại phải xử lý gần gấp đôi tải bình thường hoặc hệ thống phải chủ động giảm chức năng/traffic. Không thể mặc định autoscaling sẽ thêm capacity ngay lập tức; quota, warm-up, image pull, connection limits và database capacity có thể là bottleneck.

Cần test:

- Normal traffic distribution.
- Peak/burst.
- N-1 region failure.
- Dependency degradation trong một region.
- Scale-up time và quota availability.
- Database/queue throughput khi dồn tải.
- Cache cold start và connection surge.
- Cost khi duy trì warm/hot standby.

### 18.1. Headroom cho active–active

Nếu muốn mỗi region tự chịu toàn bộ tải khi region khác mất, mỗi vùng cần đủ capacity N-1. Nếu chấp nhận degraded mode, có thể thiết kế một số chức năng bị shed/queue. Điều quan trọng là degradation phải được công bố trong SLO và kiểm thử.

## 19. Failover và failback

Failover là chuyển dịch vụ/authority sang region thay thế. Failback là chuyển lại region ban đầu hoặc sang topology bình thường mới sau khắc phục.

Một failover an toàn:

1. Phát hiện và đánh giá phạm vi sự cố.
2. Quyết định failover theo policy và business impact.
3. Fence writer cũ hoặc xác minh không còn quyền ghi.
4. Kiểm tra replica freshness và recovery point.
5. Promote data store/cell mới với epoch/version mới.
6. Cập nhật routing và tenant/home-region mapping.
7. Mở traffic theo cohort/health gate.
8. Xác minh business invariants, queue và payment reconciliation.
9. Theo dõi latency, errors, replication và backlog.
10. Ghi nhận RPO/RTO thực tế và quyết định failback.

Failback không nên được kích hoạt chỉ vì region cũ đã healthy. Cần re-seed/reconcile dữ liệu, xác định writer authority và chuyển đổi có kiểm soát. DNS switch không phải failback data.

## 20. Observability đa vùng

Cần phân biệt sự cố local và global. Telemetry nên có dimension region, zone, cell, service, tenant tier và operation.

Signals hữu ích:

- Availability/error rate theo region.
- Latency p50/p95/p99 theo user geography.
- Global routing decision và health status.
- Replication lag/position và writer epoch.
- Cross-region bytes/latency/cost.
- Queue age/offset lag.
- Capacity headroom và autoscaling time.
- Failover/failback state và duration.
- RPO/RTO achieved.
- Data reconciliation mismatch.
- Certificate/KMS/identity error theo region.

Đồng hồ giữa region phải đồng bộ đủ để correlation và log analysis đáng tin; tuy nhiên không dựa duy nhất vào timestamp để xác định thứ tự commit. Dùng log sequence, version hoặc causal metadata theo semantics dữ liệu.

## 21. Cost và complexity

Multi-region thường làm tăng chi phí và gánh nặng vận hành:

- Compute và database ở region thứ hai.
- Data replication và cross-region egress.
- Storage/backup duplication.
- Global networking, traffic management và security services.
- Observability ingestion/retention.
- KMS/secret/certificate operations.
- On-call, testing, runbook và kỹ năng vận hành.

Active–passive pilot light tiết kiệm compute nhưng có thể tăng RTO. Hot standby tốn hơn nhưng giảm thời gian provision. Active–active tận dụng capacity cho traffic bình thường nhưng có thể đắt vì replication và data conflict management.

So sánh chi phí toàn vòng đời với business impact của downtime/data loss, không chỉ nhìn hóa đơn compute.

## 22. Các lỗi thiết kế thường gặp

| Lỗi | Hậu quả | Cách phòng tránh |
| --- | --- | --- |
| Gọi hệ thống active–active vì có hai app region | Data tier vẫn là single-region bottleneck | Mô tả topology theo từng lớp |
| DNS failover nhưng không fence writer | Split-brain và ghi xung đột | Authority model, epoch và fencing |
| Async replica lag không được giám sát | RPO vượt mục tiêu khi promote | Alert lag và candidate threshold |
| Passive region chưa đủ capacity | Failover thành công nhưng service quá tải | N-1 capacity test và warm-up |
| Active–active write không có conflict policy | Lost update/double booking | Single-writer/ownership hoặc domain conflict resolution |
| Dùng LWW cho dữ liệu tài chính | Mất giao dịch hợp lệ | Domain-specific consistency |
| Global dependency không có HA | Một dependency gây outage toàn vùng | Tách/cache/replicate runtime dependencies |
| Health check quá nhạy | Flapping và failover loop | Hysteresis, cooldown và business check |
| Chỉ đổi DNS mà quên session/connection | Client tiếp tục gọi region cũ | Drain, reconnect, TTL và client behavior |
| Replicate mọi dữ liệu không xét residency | Vi phạm policy/hợp đồng | Data classification và regional placement |
| Key/secret không sẵn ở DR | Application không thể đọc dữ liệu | DR identity/KMS test |
| Failback vội vàng | Lỗi lần hai hoặc split-brain | Reconcile, re-seed, writer transfer |
| Không diễn tập region loss | RTO chỉ tồn tại trên giấy | Game day và full failover drill |
| Không tính egress/ops cost | Mô hình multi-region vượt ngân sách | Cost model và review theo workload |

## 23. Quy trình thiết kế kiến trúc nhiều region

1. **Xác định mục tiêu:** latency, availability, RTO/RPO, data residency và business continuity.
2. **Phân loại workload/data:** stateless/stateful, read/write ratio, consistency và khả năng rebuild.
3. **Chọn topology:** active–passive, active–active hoặc hybrid theo từng lớp.
4. **Định nghĩa write authority:** single writer, home region, partition owner hoặc multi-writer protocol.
5. **Thiết kế replication:** sync/async, lag limit, retention và conflict handling.
6. **Thiết kế global routing:** geo/latency/weighted/failover/tenant routing và health semantics.
7. **Bảo vệ split-brain:** quorum, epoch, fencing và writer transition.
8. **Thiết kế runtime dependencies:** identity, KMS, secrets, queue, cache và control plane.
9. **Bảo đảm capacity:** N-1, warm-up, quota, burst và degraded mode.
10. **Bảo vệ dữ liệu:** residency, encryption, backup, audit và cross-region access.
11. **Thiết lập observability/cost:** metric theo region, replication, egress và failover.
12. **Diễn tập:** region outage, network partition, stale replica, failover, failback và reconciliation.
13. **Review định kỳ:** RPO/RTO thực tế, topology drift, cost và provider lifecycle.

## 24. Ví dụ: nền tảng SaaS đặt thuê thiết bị

Một nền tảng phục vụ khách hàng tại Đông Nam Á và châu Âu. Các tenant doanh nghiệp có booking, inventory, payment và reporting. Một số tenant yêu cầu dữ liệu ở home region; payment và booking cần consistency cao; reporting chấp nhận eventual consistency.

### 24.1. Phân chia workload

| Workload | Mô hình có thể chọn | Lý do |
| --- | --- | --- |
| Web/API stateless | Active–active | Có thể route gần user và scale theo region |
| Booking write | Home-region per tenant | Giữ một writer cho invariant booking |
| Inventory allocation | Single authority theo asset/partition | Tránh double reservation |
| Payment ledger | Single-writer/quorum-backed primary theo policy | Giữ thứ tự và reconciliation rõ |
| Search/reporting | Regional read model, async replication | Chấp nhận freshness lag |
| Notification | Regional workers, durable queue và idempotency | Có thể xử lý retry và backlog |
| Static assets | CDN/global edge | Phục vụ gần user, giảm tải origin |

### 24.2. Topology khái niệm

~~~mermaid
flowchart TB
    U["Users across geographies"] --> G["Global traffic management"]
    G --> RA["Region A: Active"]
    G --> RB["Region B: Active"]
    RA --> DIR["Tenant home-region directory"]
    RB --> DIR
    DIR --> BA["Booking service / home writer A"]
    DIR --> BB["Booking service / home writer B"]
    BA --> DBA[("Region A primary data")]
    BB --> DBB[("Region B primary data")]
    DBA -. "Approved replication" .-> DBB
    DBB -. "Approved replication" .-> DBA
    RA --> READ_A["Regional read models"]
    RB --> READ_B["Regional read models"]
~~~

Đây là topology minh họa cho ownership theo tenant. Không nên diễn giải hai mũi tên replication là hai database được phép ghi cùng một tenant. Mỗi tenant chỉ có một home writer tại một thời điểm; khi chuyển home region cần fencing và migration protocol.

### 24.3. Kịch bản Region A outage

1. Global health policy xác nhận Region A không thể phục vụ.
2. Với tenant home-region A, control workflow quyết định DR theo RPO/RTO.
3. Fence writer A bằng database promotion/epoch hoặc cơ chế tương đương.
4. Kiểm tra Region B có log/replica đạt recovery point được chấp nhận.
5. Promote writer mới, cập nhật tenant mapping với version mới.
6. Route tenant A tới Region B; giữ tenant khác tại home region riêng nếu topology cho phép.
7. Xác minh booking/inventory/payment invariants và reconciliation.
8. Theo dõi backlog/latency và capacity.
9. Khi A phục hồi, re-seed hoặc reconcile thành replica trước; chỉ failback sau review.

## 25. Đánh giá theo Well-Architected

| Góc nhìn | Câu hỏi thiết kế |
| --- | --- |
| **Độ tin cậy** | RTO/RPO được đo? Region còn lại đủ capacity? Failover/failback có fencing, validation và rehearsal? |
| **Bảo mật** | Identity, secret, KMS, log và data residency được scope theo region/tenant? Operator access có audit? |
| **Hiệu quả hiệu năng** | Routing giảm latency? Replication/coordination có ảnh hưởng write path? Cross-region calls có được tối ưu? |
| **Tối ưu chi phí** | Warm/hot standby, replication, egress và observability cost có tương xứng với business impact? |
| **Khả năng vận hành** | Có global dashboard, runbook, routing policy owner, replication lag alert và game day? |

### Checklist nghiệm thu

- [ ] Mục tiêu latency, RTO, RPO, residency và business continuity được xác định theo workload.
- [ ] Topology được mô tả riêng cho compute, data, queue, cache, identity và control plane.
- [ ] Active–passive có warm-up/capacity plan và recovery dependency đầy đủ.
- [ ] Active–active có write ownership và conflict policy rõ; không mặc định mọi region cùng ghi.
- [ ] Replication mode, lag threshold và commit semantics đã được kiểm chứng.
- [ ] Global routing có geo/latency/health policy, hysteresis và manual override.
- [ ] DNS TTL, client connection, session và webhook behavior được xem xét.
- [ ] Writer transition có quorum/epoch/fencing hoặc cơ chế authority tương đương.
- [ ] Tenant/home-region mapping có version, HA và không thể cấp hai writer.
- [ ] Queue/job có ownership, idempotency, ordering và replay policy.
- [ ] Cache/session có freshness và invalidation semantics.
- [ ] Identity/KMS/secret/certificate hoạt động ở DR region theo least privilege.
- [ ] Data residency bao gồm backup, logs, telemetry, derived data và support access.
- [ ] Capacity N-1, quota, warm-up và degraded mode đã được load test.
- [ ] Dashboard đo region health, latency, replication lag, writer epoch, RPO/RTO và cost.
- [ ] Failover, failback, network partition và stale replica đã được diễn tập.

## 26. Bài tập áp dụng

Một nền tảng SaaS có 2.000 tenant, người dùng tập trung tại Đông Nam Á và châu Âu. Region A hiện phục vụ toàn bộ write traffic. Region B giữ asynchronous replica, RPO mục tiêu 60 giây và RTO 15 phút. Đội sản phẩm muốn chuyển sang active–active để giảm latency; tuy nhiên, booking và inventory phải ngăn double booking, payment ledger cần thứ tự giao dịch rõ, còn search/reporting chấp nhận dữ liệu trễ vài phút.

Hãy thiết kế:

1. Phần nào nên active–active và phần nào vẫn single-writer/home-region?
2. Chia tenant theo home region dựa trên residency, latency và capacity ra sao?
3. Cần những thành phần nào trong global routing và tenant directory?
4. Replication đồng bộ/bất đồng bộ phù hợp cho booking, ledger, search và reporting thế nào?
5. Làm sao xử lý tenant chuyển home region mà không có hai writer?
6. Quorum, epoch, fencing và session revocation được phối hợp ra sao khi network partition?
7. Nếu Region A mất đột ngột với replica lag 45 giây, làm sao đánh giá RPO 60 giây trước promotion?
8. Capacity Region B có thể phục vụ traffic chuyển tới trong 15 phút không? Đã tính cold cache, quota và connection surge chưa?
9. Khi A phục hồi, re-seed/failback và reconciliation thế nào?
10. Metric và game day nào chứng minh latency, RPO/RTO, consistency và cost?

Một phương án có cơ sở có thể triển khai active–active cho stateless API và regional read models, giữ home-region writer cho booking/inventory/payment, dùng async replication cho dữ liệu có thể chấp nhận lag, và áp dụng policy mạnh hơn cho ledger. Tenant directory phải có authority/fencing; khi failover, chỉ promotion sau khi writer cũ bị fence và candidate đáp ứng RPO. Reporting/search có thể rebuild hoặc cập nhật trễ; dữ liệu tài chính không được giải quyết conflict bằng timestamp đơn thuần.

**Điểm cốt lõi:** active–passive ưu tiên một writer và quy trình tiếp quản có kiểm soát; active–active phân phối traffic thường xuyên nhưng đòi hỏi thiết kế ownership và consistency chặt chẽ hơn. Chọn topology theo từng lớp, đo RTO/RPO/latency, bảo vệ writer authority, chuẩn bị capacity và diễn tập failover/failback. Multi-region chỉ mang lại độ tin cậy khi dữ liệu, identity, routing, dependency và quy trình vận hành đều có thể chịu sự cố trong phạm vi đã cam kết.
