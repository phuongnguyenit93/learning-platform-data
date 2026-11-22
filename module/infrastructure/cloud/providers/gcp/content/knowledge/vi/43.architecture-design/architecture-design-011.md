# Thiết kế đa region và kiểm soát tính nhất quán

Một ứng dụng chạy tại hai region vẫn có thể trả HTTP 200 khi một region mất kết nối, nhưng chưa chắc giao dịch an toàn. Nếu hai bản triển khai cùng chấp nhận cập nhật số dư trong hai cơ sở dữ liệu chưa đồng bộ, người dùng có thể thấy giá trị cũ hoặc bị thanh toán trùng. Ngược lại, nếu mọi thao tác ghi phải chờ xác nhận từ nhiều region, độ trễ có thể tăng và một phía bị cô lập có thể phải tạm ngừng ghi. **Thiết kế đa region là bài toán đồng thời về khả dụng, độ trễ, nhất quán, bền vững dữ liệu và khả năng vận hành.**

Trong chương **Thiết kế kiến trúc GCP** của module **CLOUD_PROVIDERS_GCP**, bài học nối các kiến thức về tổ chức project, IAM, VPC, Compute Engine, GKE, Cloud Run, lưu trữ và cơ sở dữ liệu thành một quyết định kiến trúc có thể kiểm chứng. Mục tiêu là biết **ai được phép ghi**, **bản đọc nào là hợp lệ**, **điều gì xảy ra khi mất một region hoặc bị network partition** và **cách chứng minh failover đáp ứng SLO/RTO/RPO**. Những quyết định này cũng tác động đến bảo mật, tự động hóa triển khai, observability và chi phí.

## Mục tiêu học tập

Sau bài này, bạn có thể phân biệt chịu lỗi zone/region; lựa chọn active-passive, active-active với một writer hoặc nhiều writer, hay geo-partitioning; giải thích strong consistency, read-your-writes và eventual consistency; so sánh cơ chế dữ liệu của Spanner, Cloud SQL, Firestore, Bigtable và Cloud Storage; thiết kế fencing, idempotency, failover/failback và kiểm thử theo bất biến nghiệp vụ.

## 1. Region là failure domain, không chỉ là vị trí chạy compute

Một Google Cloud region có nhiều zone. Chạy workload trên nhiều zone giúp giảm phụ thuộc vào một zone, nhưng không tự bảo vệ trước lỗi toàn region. Muốn chịu lỗi region, **tất cả thành phần quan trọng trong đường xử lý giao dịch** phải có cơ chế hoạt động từ một region khác: compute, lưu trữ, database, mạng, IAM, secrets, traffic routing và các dịch vụ tích hợp.

| Phạm vi | Ví dụ | Khả năng bảo vệ | Giới hạn |
|---|---|---|---|
| Zonal | VM, zonal Persistent Disk | Cần replica hay restore nơi khác | Một zone mất có thể làm thành phần dừng |
| Regional/multi-zone | Regional MIG, regional GKE cluster, Cloud SQL HA | Chịu một số lỗi zone theo cấu hình | Mất toàn region vẫn gây gián đoạn |
| Multi-region | Hai Cloud Run services/GKE clusters; Spanner multi-region; Cloud Storage dual-region | Có thể tiếp tục sau lỗi region theo mô hình | Không tự bảo vệ khỏi lỗi code, IAM hay thao tác xóa dữ liệu |
| Global frontend | Global external Application Load Balancer | Một endpoint định tuyến đến backend nhiều region | Không tự làm backend hoặc database trở thành đa region |

**Đánh giá end-to-end:** Nếu frontend có hai region nhưng database chỉ có một primary ở region A, region B có thể tiếp tục trả health check mà không ghi được đơn hàng. Nếu dùng cùng một secret, certificate hoặc IdP chỉ khả dụng tại A, sự cố A cũng có thể vô hiệu hóa B.

Các kịch bản phải kiểm thử gồm lỗi một zone, mất cả region, **network partition** (hai region còn chạy nhưng liên lạc gián đoạn), và **logical/common-mode failure** như rollout sai, schema migration hỏng, IAM bị thu hồi hoặc dữ liệu bị xóa đồng thời. Replication không thay thế backup, kiểm soát thay đổi, quyền tối thiểu hay kế hoạch khôi phục dữ liệu logic.

## 2. SLO, RTO, RPO, latency và consistency contract

Trước khi chọn một dịch vụ managed, thống nhất mục tiêu theo luồng nghiệp vụ, không chỉ theo hạ tầng:

| Yêu cầu | Câu hỏi thiết kế | Ví dụ minh họa, không phải SLA Google Cloud |
|---|---|---|
| SLO availability | Bao nhiêu request hợp lệ được phục vụ trong cửa sổ đo? | 99,95% checkout thành công mỗi tháng |
| RTO | Sau lỗi region, bao lâu mới khôi phục được chức năng thiết yếu? | 15 phút |
| RPO | Có thể mất tối đa bao nhiêu dữ liệu **đã được xác nhận ghi**? | 5 phút; một số giao dịch yêu cầu không mất dữ liệu |
| Consistency | Sau commit, ai phải thấy trạng thái mới và khi nào? | Thanh toán không được nhìn thấy số dư cũ |
| Latency | p95/p99 cho đọc/ghi tại vị trí người dùng? | Checkout p99 dưới 800 ms |
| Data residency | Dữ liệu được phép lưu và xử lý ở những khu vực nào? | PII chỉ tại khu vực được phê duyệt |
| Capacity | Region còn lại có thể nhận hết tải khi failover? | Đủ quota, DB connections và autoscaling |

**RPO không đồng nghĩa độ trễ replica và khác read staleness.** Một replica bình thường có thể trễ rất ít nhưng vẫn mất các transaction chưa nhận được khi primary biến mất. Ngược lại, một datastore ghi bền bằng quorum có thể cho phép đọc tại timestamp cũ để giảm latency theo yêu cầu của client.

Lập consistency contract theo dữ liệu:

- **Thanh toán, số dư và kho:** bắt buộc giữ bất biến nghiệp vụ, tránh debit hoặc trừ tồn kho hai lần.
- **Đơn hàng:** trạng thái sau commit phải đọc được đúng theo semantics của API; mọi retry phải idempotent.
- **Giỏ hàng/cài đặt cá nhân:** có thể hỗ trợ merge hoặc read-your-writes theo phiên, nếu business chấp nhận.
- **Catalog và báo cáo:** có thể dùng stale reads hoặc eventual consistency với mức trễ đã công bố.
- **Event và analytics:** có thể xử lý bất đồng bộ và phát lại; không được giả định producer và consumer commit nguyên tử.

## 3. Các mức nhất quán cần phân biệt

| Mức/thuộc tính | Ý nghĩa | Tình huống sử dụng |
|---|---|---|
| Strong consistency/linearizability | Đọc sau một ghi đã hoàn tất quan sát trạng thái phù hợp với một thứ tự duy nhất | Trạng thái giao dịch vừa commit |
| External consistency | Giao dịch có thứ tự serializable đồng thời tôn trọng thứ tự commit quan sát theo thời gian thực | Spanner read-write transactions |
| Read-your-writes | Client không đọc phiên bản cũ hơn chính ghi gần nhất của nó | Người dùng cập nhật hồ sơ rồi xem lại |
| Monotonic reads | Client đã thấy phiên bản mới thì không lùi về bản cũ | Chuyển route từ region A sang B |
| Bounded staleness | Chấp nhận đọc snapshot cũ theo giới hạn thời gian/timestamp | Dashboard cho phép trễ 15 giây |
| Eventual consistency | Nếu ngừng cập nhật, các bản sao cuối cùng sẽ hội tụ | Multi-cluster Bigtable theo mặc định |
| Durability | Bảo vệ dữ liệu khỏi mất mát | Có thể bền vững dù chưa truy cập được tại region khác |

**Strong consistency ở một database không tự bảo đảm transaction giữa nhiều hệ thống.** Ví dụ commit đơn hàng trong DB rồi publish Pub/Sub là hai bước riêng; nếu tiến trình crash giữa chúng, phải có transactional outbox, CDC hoặc workflow đáng tin cậy để tránh mất event.

### Khi bị network partition: chọn khả dụng hay quyền ghi an toàn?

Với replication **đồng bộ theo quorum**, một phía không có đủ số phiếu có thể phải từ chối ghi để giữ consistency. Với replication **bất đồng bộ nhiều writer**, hai phía có thể tiếp tục ghi độc lập nhưng cần giải quyết conflict, stale reads và quy trình hội tụ sau đó. Thiết kế phải ghi rõ lựa chọn trong từng thao tác, thay vì tuyên bố chung rằng hệ thống vừa luôn nhất quán vừa luôn ghi được ở mọi phía khi mạng chia cắt.

## 4. Bốn mẫu topology đa region

### 4.1 Active-passive

Region A là nơi phục vụ chính; region B giữ standby ở mức cold/warm/hot. Dữ liệu được backup hoặc replicate sang B. Khi A lỗi, runbook kích hoạt compute, chuyển quyền ghi và endpoint, rồi xác minh giao dịch.

**Điểm mạnh:** chỉ một writer, tương đối dễ vận hành. **Đánh đổi:** RTO phụ thuộc thời gian phát hiện/khởi động/routing; RPO tùy replication. Standby không đủ capacity làm failover thành công về kỹ thuật nhưng hệ thống vẫn quá tải.

### 4.2 Active-active frontend, single-writer database

API stateless chạy ở A và B. Cả hai phục vụ request nhưng chỉ một primary/leader có quyền commit write, hoặc một dịch vụ database có bộ điều phối leader. Frontend ở B có thể phải gọi data leader ở A qua mạng.

**Điểm mạnh:** tăng khả dụng tầng frontend, tránh hai database độc lập cùng ghi. **Đánh đổi:** thêm round trip cho write xuyên region và phải có quy trình chuyển quyền ghi khi A mất.

### 4.3 Active-active application và dữ liệu đa region

Hai region nhận request ghi, nhưng dữ liệu phải được quản lý bởi **một hệ thống có semantics transaction/consensus phù hợp** hoặc bởi cơ chế giải quyết conflict được thiết kế riêng. Spanner multi-region là một lựa chọn cho các transaction nhất quán bằng quorum; điều đó không tương đương việc hai Cloud SQL primaries độc lập tự động trở thành một database multi-writer.

**Điểm mạnh:** phục vụ người dùng nhiều địa lý và có khả năng sẵn sàng cao. **Đánh đổi:** latency ghi khi phối hợp liên region, chi phí replica, vận hành và khả năng tương thích ứng dụng.

### 4.4 Geo-partitioned ownership

Mỗi tenant/shard có một owner region. User ở A ghi dữ liệu thuộc A, user ở B ghi dữ liệu thuộc B; có thể sao chép các tập dữ liệu được phép sang nơi khác. Khi chuyển owner lúc failover, phải dùng **fencing token/epoch hoặc transaction có điều kiện** để không có hai region cùng sở hữu quyền ghi một shard.

Mẫu này có thể giảm write latency và hỗ trợ data residency, nhưng yêu cầu định tuyến theo khóa dữ liệu, logic di chuyển quyền sở hữu và xử lý truy cập liên vùng.

~~~mermaid
flowchart TB
  USER[Người dùng toàn cầu] --> LB[Global Application Load Balancer]
  LB --> A[Region A: ứng dụng]
  LB --> B[Region B: ứng dụng]
  A --> DATA[Hệ dữ liệu với consistency contract rõ ràng]
  B --> DATA
  DATA --> RA[Replica / quorum Region A]
  DATA --> RB[Replica / quorum Region B]
  DATA --> W[Witness nếu topology yêu cầu]
  A --> OBS[Giám sát / tracing / audit]
  B --> OBS
~~~

Đây là **sơ đồ logic**, không phải cấu hình cụ thể của mọi dịch vụ. Spanner, Cloud SQL, Bigtable và Firestore có topology và quyền ghi rất khác nhau. Mỗi phương án cần một sơ đồ hạ tầng riêng khi triển khai thật.

## 5. Routing: một global endpoint không đủ để failover

Với **Cloud Run**, một service được triển khai theo region. Muốn chạy ở hai region, deploy cùng phiên bản ứng dụng ở hai nơi và cấu hình global external Application Load Balancer với serverless NEG phù hợp. Với **GKE**, cần nhiều regional clusters/backends và policy định tuyến thích hợp; một regional GKE cluster không tự thành multi-region.

~~~bash
# Hai deployment khu vực; chưa bao gồm việc tạo load balancer
gcloud run deploy orders-api \
  --project=PROJECT_ID \
  --region=REGION_A \
  --image=IMAGE_URL_BY_DIGEST

gcloud run deploy orders-api \
  --project=PROJECT_ID \
  --region=REGION_B \
  --image=IMAGE_URL_BY_DIGEST
~~~

Đường dẫn image theo digest cần là URL hợp lệ từ Artifact Registry; các ký hiệu viết hoa là placeholder. Hai lệnh trên **không** tự tạo routing, IAM invoker, certificate, global load balancer, DNS hay DR policy. Cần triển khai các thành phần đó riêng, đồng thời đồng bộ cấu hình/secret/schema giữa hai region theo kiểm soát thay đổi.

### Health check ứng dụng và Cloud Run service health

Một serverless NEG bổ sung không đủ để bảo đảm mọi lỗi HTTP 5xx làm traffic tự chuyển. Cloud Run có **service health** phối hợp với global load balancer để tự động failover/failback khi region được xác định unhealthy; tính năng này phải được cấu hình với readiness probes, và có những điều kiện như **tối thiểu một service-level hoặc revision-level minimum instance mỗi region** để tính health. Nếu không sử dụng, cần manual failover hoặc cơ chế được hỗ trợ khác và phải diễn tập.

Với GKE, readiness và backend health quyết định nơi nhận traffic; liveness quyết định thời điểm restart process/pod. Không biến lỗi dependency tạm thời thành hành vi tất cả Pod đồng loạt unhealthy nếu vẫn có thể degrade service có kiểm soát. Kết hợp timeout, retry với jitter, circuit breaker và bulkhead.

### DNS, session và capacity

DNS TTL không phải cam kết client đổi tuyến sau đúng TTL: resolver, browser, SDK và connection pool có thể cache khác nhau. Session nên stateless hoặc đặt trong shared store có consistency phù hợp; sticky session không bảo vệ khỏi mất region.

Nếu cả hai region đang xử lý 50% tải, sau sự cố một region, nơi còn lại phải đáp ứng gần **100% tải hợp lệ**. Kiểm tra quota, min/max instances, cold start, số kết nối DB, throughput của dependency, budget CPU, traffic egress và khả năng scale-up. Đừng dựa vào capacity trung bình khi tính DR.

## 6. So sánh lựa chọn dữ liệu đa region trên GCP

Không chọn database chỉ vì có nhãn “replicated”. Hãy hỏi **ghi được từ đâu, điều kiện commit là gì, read có thấy write vừa xác nhận không, khi mất region có cần promotion không và liệu hai nơi có thể ghi mâu thuẫn không**.

| Dịch vụ/cấu hình | Sao chép và consistency chính | Ứng xử khi lỗi region | Quyết định quan trọng |
|---|---|---|---|
| **Spanner multi-region** | Quorum qua các region; external consistency cho transaction; hỗ trợ strong hoặc stale reads | Có khả năng tự động leader failover theo topology | Write latency, leader location, edition, chi phí và data residency |
| **Firestore multi-region** | Dữ liệu được sao chép qua tập region xác định; database hỗ trợ đọc/ghi khi mất một region | Khả năng tiếp tục phục vụ theo topology managed | Location được chọn từ các cấu hình hỗ trợ; thêm latency/chi phí so với regional |
| **Cloud SQL HA + cross-region replica** | HA đồng bộ trong region; read replica liên region **bất đồng bộ** | Thường cần promote/failover replica và đổi write endpoint; RPO có thể khác 0 | Mô hình single primary, replication lag, DR runbook |
| **Bigtable multi-cluster** | Replication giữa cluster **eventual** theo mặc định | Có thể route đến cluster khác; có nguy cơ stale reads sau failover | App profile/routing, conflict resolution, consistency contract |
| **Cloud Storage dual-/multi-region** | Metadata/object operations có strong consistency; dữ liệu được sao chép liên region bất đồng bộ | Có thể tiếp tục phục vụ bản object đã replicate; bản mới chưa replicate có thể không sẵn | Default/turbo replication, object RPO, data placement, backup |

Một cấu hình **regional** vẫn có thể đủ cho đa số workload nếu business chấp nhận RTO theo giờ và DR bằng backup/restore. Ngược lại, tính nhất quán mạnh trên datastore không tự tạo tính sẵn sàng của API, secret, network hay identity provider ở region thứ hai.

## 7. Spanner: quorum, leader, transaction và stale reads

Spanner regional configuration duy trì các read-write replica tại nhiều zone của một region. **Spanner multi-region** phân phối các replica voting/read-write qua nhiều region, thường có witness region theo instance configuration, và yêu cầu edition hỗ trợ như **Enterprise Plus**. Danh sách cấu hình và vị trí cụ thể được Google Cloud công bố; không thể tự ghép bất kỳ hai region nào rồi coi là một Spanner multi-region configuration.

Trong multi-region, phần lớn topology có một **leader region**; client có thể đặt tại nhiều region nhưng write transaction sẽ được điều phối với leader và phải đạt quorum theo thiết kế replication. **External consistency** giúp các transaction đã commit giữ thứ tự phù hợp với quan sát thời gian thực. Khi leader region lỗi, cơ chế được quản lý có thể chuyển leader nếu còn quorum hợp lệ. Điều này khác với việc hai application instances tự tranh quyền ghi vào hai database tách rời.

### Mẫu transaction và đọc

- **Read-write transaction:** dùng cho dữ liệu cần bất biến toàn cục, ví dụ đặt hàng và trừ tồn kho; phải xử lý transaction abort/retry theo thư viện client.
- **Strong read:** nhìn thấy tác động của những transaction đã commit trước khi thao tác đọc bắt đầu theo bảo đảm của Spanner.
- **Stale read tại timestamp:** chấp nhận snapshot cũ để giảm latency đối với dashboard, feed hoặc phân tích; không dùng để quyết định thanh toán khi cần trạng thái mới nhất.
- **Read-only region:** có thể phục vụ những loại read phù hợp, nhưng không phải là một cơ chế DR độc lập nếu write quorum của instance mất.
- **Read lease region:** trong một số cấu hình giúp giảm strong-read latency ở non-leader region nhưng có trade-off về write latency; cần benchmark trước khi bật.

~~~mermaid
sequenceDiagram
  participant C as Client tại Region B
  participant L as Spanner leader Region A
  participant Q as Voting replicas
  C->>L: Read-write transaction
  L->>Q: Replication / quorum
  Q-->>L: Đủ xác nhận
  L-->>C: Commit thành công
  Note over C,Q: Chỉ minh họa logic; số replica và quorum tùy instance configuration
~~~

**Độ trễ của write phụ thuộc vào địa lý:** leader và voting replicas càng xa nhau, network round trip có thể tăng. Hãy đặt phần lớn write workload gần leader region khi phù hợp, đo latency của transaction thực, cân nhắc read-only/stale reads cho người dùng ở xa và kiểm tra compliance trước khi chọn vị trí replica.

Không tuyên bố “Spanner multi-region = RTO 0 cho toàn bộ ứng dụng”: quorum database có thể vẫn hoạt động trong khi global frontend, authorization, cache hoặc phụ thuộc SaaS mất sẵn sàng. RPO của các transaction đã commit trong datastore cũng không có nghĩa event được publish sau đó hoặc file upload khác đã bền vững.

## 8. Cloud SQL: HA trong region khác DR liên region

Cloud SQL high availability (regional availability) bảo vệ trước lỗi một zone bằng primary và standby ở zone khác. **Cross-region read replica là bản sao bất đồng bộ**, không phải standby được quản lý giống mô hình HA cùng region. Khi mất region chứa primary, replica liên vùng có thể chưa nhận hết transaction đã commit.

### Mô hình DR tiêu chuẩn

~~~mermaid
flowchart LR
  APP_A[Application Region A] --> PRIMARY[Cloud SQL HA primary Region A]
  PRIMARY -. asynchronous replication .-> REPLICA[Read replica Region B]
  APP_B[Application Region B] -. sau DR .-> REPLICA
  REPLICA --> PROMOTE[Promote / replica failover theo edition]
  PROMOTE --> NEW[Write primary mới ở Region B]
~~~

Khi region A không phục vụ được:

1. Incident commander xác nhận sự cố và ngưỡng kích hoạt DR.
2. Đọc **replication state/lag** gần thời điểm lỗi và đánh giá dữ liệu có thể chưa được sao chép.
3. **Fencing** old primary nếu có thể; tránh để hai endpoint tiếp tục được client ghi độc lập sau khi mạng phục hồi.
4. Promote cross-region replica theo quy trình DR, hoặc dùng chức năng replica failover đã cấu hình.
5. Chuyển database write endpoint, làm mới connection pools và xác minh transaction/business invariants.
6. Bật lại HA cho primary mới và tái lập cross-region replica ở hướng ngược lại để khôi phục năng lực DR.

**Thao tác promote thường là quyết định có chủ đích**, không giống zonal HA tự động. Cloud SQL **Enterprise Plus** có **advanced disaster recovery** hỗ trợ designated DR replica, replica failover và planned switchover. Planned switchover có thể thực hiện không mất dữ liệu theo điều kiện dịch vụ; **replica failover trong thảm họa vẫn có thể mất dữ liệu do replication lag**. Không dùng khả năng switchover không mất dữ liệu để cam kết RPO 0 cho unplanned region outage.

Trong mô hình active-active frontend/single-writer Cloud SQL, hãy giữ đúng **một write primary** ở mọi thời điểm. Nếu B chỉ là cross-region read replica, có thể đọc report tại B nhưng phải hiểu stale reads; write từ A/B vẫn phải đến primary. Một nhóm tự bật ghi vào hai independent primaries sẽ phải tự giải quyết transaction conflict và không còn semantics Cloud SQL replication một primary.

### Recovery và failback

Không tự chuyển traffic về region A ngay khi A vừa hồi phục. Region B có thể đã trở thành source of truth với những commit mới. Failback phải đồng bộ ngược, xác minh checkpoint, thiết lập lại replication, chuyển quyền ghi theo kế hoạch và chỉ hủy tài nguyên cũ sau khi đảm bảo không còn client kết nối.

## 9. Firestore multi-region và Bigtable multi-cluster: khác nhau căn bản

**Firestore multi-region** là một database location do dịch vụ cung cấp, phân phối replica theo cấu hình hỗ trợ (thường có hai read-write regions và một witness). Database được thiết kế để vẫn phục vụ reads/writes khi mất một region theo topology. Firestore không tương đương việc tự tạo hai regional databases rồi liên kết chúng bằng một script đồng bộ. Location được chọn khi tạo database; cần kiểm tra danh sách region được hỗ trợ, latency và ràng buộc residency trước khi cấp phát vì không thể tùy ý đổi location sau đó.

Firestore dùng giao dịch trong hệ storage và có các bảo đảm nhất quán ở cấp database. Dù vậy, client vẫn cần retry khi transaction contention xảy ra, xử lý idempotency và kiểm tra các giới hạn document/query/indexing của workload. Không dùng một write transaction phân tán ngoài Firestore để giả định việc publish message đã atomic.

**Bigtable replicated instance** cho phép nhiều cluster ở những zone/region khác nhau. Mặc định, thay đổi được replicate **bất đồng bộ** và các cluster hội tụ theo **eventual consistency**. App profile quyết định routing, có thể multi-cluster (tự chuyển sang cluster khác khi một cluster không khả dụng) hoặc single-cluster (tập trung reads/writes vào một cluster để có semantics nhất quán mạnh hơn theo điều kiện sử dụng).

Điểm cần chú ý khi dùng Bigtable:

- Khi application đọc từ cluster khác ngay sau write, có thể nhận giá trị cũ.
- Một số app-profile routing có thể đạt read-your-writes trong những điều kiện nhất định, nhưng failover có thể phá vỡ kỳ vọng đó.
- Nếu hai cluster ghi cùng cell key/timestamp, dịch vụ dùng quy tắc conflict resolution của riêng nó; cách hợp nhất kiểu last-write-wins không phù hợp cho mọi giao dịch tài chính.
- Phải phân biệt single-row transactions ở single-cluster routing với multi-cluster routing; không áp các đảm bảo transaction của một cluster lên toàn bộ topology replicated.

Nếu yêu cầu dữ liệu khách hàng liên tục đọc phiên bản mới nhất trên nhiều region, không nên chọn multi-cluster Bigtable theo mặc định rồi tự tuyên bố là strongly consistent. Ngược lại, nếu đó là time-series analytics hoặc catalog có thể chấp nhận staleness và cần throughput cao, eventual consistency có thể là một lựa chọn hợp lý.

## 10. Cloud Storage: strong metadata consistency nhưng replication liên region bất đồng bộ

Cloud Storage regional bucket lưu dư thừa qua zone trong cùng region. Dual-region hoặc multi-region bucket lưu bản sao ở nhiều vùng địa lý và được thiết kế để tự phục vụ từ nơi còn khả dụng khi một region mất, **đối với dữ liệu đã hoàn tất replication**.

Không mâu thuẫn khi nói Cloud Storage có strong consistency nhưng vẫn có RPO liên region: **object metadata và kết quả thao tác ghi được quản lý nhất quán**, trong khi **bytes của object mới được sao chép liên region bất đồng bộ**. Khi region nhận object mất trước khi replication hoàn tất, object đó có thể tạm thời không truy cập được cho đến khi region phục hồi; trong tình huống phá hủy vật lý hiếm gặp còn có rủi ro mất dữ liệu.

| Chế độ | Mục tiêu replication đối với object mới | Lưu ý |
|---|---|---|
| Dual-/multi-region mặc định | Thiết kế đạt 99,9% trong một giờ và 100% trong 12 giờ | Đây là mục tiêu của dịch vụ; không phải mọi object sẽ sẵn tại region B ngay sau write |
| Dual-region với turbo replication | Thiết kế sao chép 100% object mới trong mục tiêu RPO 15 phút | Chỉ áp dụng cho dual-region có tính năng hỗ trợ và có chi phí bổ sung |
| Hai bucket riêng dùng cross-bucket replication | Sao chép phụ thuộc cấu hình/cơ chế replication | Không mặc nhiên có cùng RPO hay strong transaction semantics như một dual-region bucket |

Sơ đồ dữ liệu cần ghi riêng đường **transactional state** (Spanner/Cloud SQL), đường **object storage** (Cloud Storage) và đường **event delivery** (Pub/Sub). Một đơn hàng có record bền vững không có nghĩa file hóa đơn hoặc sự kiện gửi email đã được sao chép đến region dự phòng.

Lưu trữ đa region vẫn cần object versioning, retention/backup và bảo vệ quyền xóa. Replication thường mang cả những thay đổi hợp lệ hoặc sai sót logic; nó không thể thay thế điểm khôi phục độc lập.

## 11. Event và messaging: cùng một nghiệp vụ có thể chạy nhiều lần

Trong kiến trúc đa region, ứng dụng thường dùng **Pub/Sub** để tách luồng request đồng bộ khỏi xử lý email, hóa đơn hoặc analytics. Tuy nhiên, chuyển region, timeout, retry hoặc consumer restart có thể làm một message được xử lý nhiều lần. **Message delivery không đồng nghĩa exactly-once business effect**.

Các điều cần ghi trong contract:

- **Producer:** khi nào coi event đã được phát hành? Có lưu ID duy nhất của event và ID giao dịch nguồn không?
- **Consumer:** nếu nhận hai message cùng event ID, kết quả nghiệp vụ có bị lặp không?
- **Ordering:** có cần thứ tự theo một đơn hàng/tenant? Có chấp nhận việc xử lý khác thứ tự khi retry/failover không?
- **Retry/DLQ:** khi downstream lỗi, retry trong bao lâu, dead-letter queue ở đâu và ai được phép replay?
- **Regional location:** nơi dữ liệu message được lưu/xử lý có đáp ứng residency và DR requirement không?
- **Backlog:** region còn lại có đủ consumer capacity để xử lý cả backlog và traffic mới không?

Pub/Sub cho phép cấu hình **message storage policy** để giới hạn những region được phép lưu/xử lý payload. Global endpoint không có nghĩa mọi message luôn được lưu ở tất cả region; thêm region vào policy cũng không tự tạo kiến trúc DR hoàn chỉnh nếu publisher/consumer chỉ tồn tại ở một region. Khi bật chính sách enforce-in-transit, client nằm ngoài region được phép có thể cần endpoint regional/locational phù hợp. Hãy kiểm tra latency, egress, ordering requirements và availability trade-off.

### Transactional outbox khi DB và Pub/Sub là hai hệ thống độc lập

Phần lớn ứng dụng không thể thực hiện một transaction nguyên tử duy nhất qua database và Pub/Sub. Có hai trường hợp lỗi:

1. **DB commit thành công nhưng publish event thất bại:** hệ thống đã nhận đơn nhưng worker không biết.
2. **Publish event thành công nhưng DB transaction rollback:** downstream xử lý một đơn hàng không tồn tại.

Mẫu **transactional outbox** ghi thay đổi nghiệp vụ và một bản ghi sự kiện vào **cùng database transaction**. Sau khi commit, một publisher/CDC worker lấy outbox và gửi Pub/Sub; nếu gửi xong nhưng chưa kịp đánh dấu đã gửi, message có thể được phát lại. Consumer phải idempotent.

~~~mermaid
sequenceDiagram
  participant API as orders-api Region A/B
  participant DB as Database nhất quán
  participant PUB as Outbox publisher
  participant MQ as Pub/Sub
  participant CON as Consumer
  API->>DB: Transaction: cập nhật order + INSERT outbox
  DB-->>API: Commit
  PUB->>DB: Đọc outbox chưa gửi
  PUB->>MQ: Publish event_id
  MQ-->>PUB: Acknowledge
  MQ->>CON: Deliver event_id
  CON->>CON: Dedupe theo event_id
  CON-->>MQ: Ack khi hoàn thành
~~~

Outbox giảm nguy cơ mất event, nhưng không tự ngăn email hoặc thanh toán được gửi hai lần. Consumer cần lưu **processed-event ID** trong cùng transaction với tác động lên cơ sở dữ liệu của nó, hoặc sử dụng idempotency key của hệ thống bên ngoài.

## 12. Ngăn split brain bằng write ownership và fencing

**Split brain** xảy ra khi hai phía đều tin rằng mình có quyền ghi vào cùng tập dữ liệu. Tình huống nguy hiểm là region A mất liên lạc với hệ thống quản lý nhưng vẫn nhận request, trong khi region B đã được promote thành primary mới. Khi mạng phục hồi, hai chuỗi ghi có thể không có thứ tự hợp lệ để hợp nhất.

Các biện pháp:

1. **Single writer theo quyền ghi thật:** không chỉ “config cho rằng B là primary”, mà quyền cấp phép ghi và endpoint phải phản ánh điều đó.
2. **Quorum/consensus:** hệ quản trị dữ liệu chỉ chấp nhận ghi ở nơi còn đủ điều kiện commit.
3. **Fencing token/monotonic epoch:** mỗi lần chuyển chủ được cấp một epoch lớn hơn; nơi xử lý write phải từ chối token cũ.
4. **Lease có kiểm soát:** lease hết hạn không đủ nếu một worker đã treo rồi tiếp tục ghi; cần fencing tại tài nguyên đích, tránh chỉ dựa vào đồng hồ cục bộ.
5. **Thủ tục promote rõ ràng:** xác minh primary cũ không còn được phép ghi, hoặc chấp nhận cơ chế quorum của datastore có quản lý.
6. **Failback có đối soát:** không tái bật old primary như writer chỉ vì region ban đầu hoạt động trở lại.

### Minh họa optimistic concurrency và fencing

Một transaction ở **datastore thống nhất có consistency thích hợp** có thể yêu cầu phiên bản bản ghi khớp kỳ vọng:

~~~sql
-- Ví dụ logic trong một database hỗ trợ transaction; không phải giao thức
-- chuyển chủ giữa hai databases độc lập.
UPDATE inventory
SET available = available - 1,
    version = version + 1
WHERE sku = :sku
  AND available > 0
  AND version = :expected_version;
~~~

Nếu số row cập nhật bằng 0, caller phải kiểm tra số lượng tồn và version rồi retry/abandon theo nghiệp vụ. Với fencing, có thể yêu cầu thêm một epoch hợp lệ được xác nhận từ nguồn thẩm quyền duy nhất. **Quan trọng:** UPDATE có điều kiện ở mỗi database độc lập không loại bỏ split brain giữa chúng; phải có chung cơ chế bảo đảm quyền ghi, hoặc tránh multi-writer.

### Khi vùng cũ phục hồi

Old primary có thể còn transaction đã nhận nhưng chưa sao chép. Không được hợp nhất hai lịch sử ghi bằng cách lấy “bản có timestamp mới hơn” nếu dữ liệu là số dư, thanh toán hay tồn kho. Cần xác định source of truth, so khớp transaction IDs/checkpoints, bù trừ giao dịch nếu có thể và có owner chấp thuận kế hoạch reconciliation.

## 13. Thiết kế idempotency, version và hợp nhất xung đột

Một request có thể được server xử lý xong nhưng phản hồi bị mất do failover. Client retry ở region B không thể biết lần ở A đã commit hay chưa. Cách phòng ngừa là **idempotency key** do client hoặc gateway cung cấp, ổn định qua các lần retry của cùng một thao tác.

### Mẫu PostgreSQL đơn giản cho idempotency

~~~sql
CREATE TABLE request_dedup (
  idempotency_key TEXT PRIMARY KEY,
  request_hash TEXT NOT NULL,
  status TEXT NOT NULL,
  response_payload JSONB,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE outbox_events (
  event_id UUID PRIMARY KEY,
  aggregate_id TEXT NOT NULL,
  event_type TEXT NOT NULL,
  payload JSONB NOT NULL,
  published_at TIMESTAMPTZ
);
~~~

Trong một Spring Boot service xử lý lệnh đặt hàng, thiết kế transaction:

1. Nhận idempotency key và hash payload; kiểm tra key trùng nhưng payload khác để trả lỗi, không dùng lại kết quả sai.
2. Dành quyền xử lý key bằng ràng buộc unique/transaction phù hợp. Nếu request đang được xử lý ở nơi khác, chờ có giới hạn hoặc trả trạng thái cho phép retry.
3. Kiểm tra tồn kho và ghi order **trong cùng transaction** với trạng thái idempotency và outbox event.
4. Commit; trả lại cùng response đã lưu nếu client gửi lại cùng key.
5. Worker phát outbox event; consumer dùng event ID hoặc business transaction ID để khử trùng.

Tất cả những bước bảo vệ atomicity trong database phải dùng **cùng một transaction thật sự**, không phải một chuỗi API calls với kỳ vọng “sẽ chạy tuần tự”. Với Spanner, thay đổi cú pháp/schema và dùng transaction API phù hợp; không sao chép SQL PostgreSQL trên sang Spanner mà không điều chỉnh.

### Các chiến lược conflict resolution

| Chiến lược | Phù hợp với | Không nên dùng cho |
|---|---|---|
| Single writer / serialize theo khóa | Tiền, tồn kho, trạng thái order | Workload cần ghi độc lập mọi nơi nhưng không thiết kế routing |
| Compare-and-swap/optimistic version | Cập nhật hồ sơ, aggregate trong một datastore nhất quán | Hai database độc lập không có cơ chế đồng bộ version chung |
| Merge field-by-field | Giỏ hàng, cài đặt có rule rõ ràng | Ghi trùng một field có ý nghĩa giao dịch tài chính |
| CRDT hoặc operation commutative | Counter, set hoặc collaboration với semantics phù hợp | Mọi nghiệp vụ không thể đảo ngược hoặc không giao hoán |
| Last-write-wins | Dữ liệu độ rủi ro thấp chấp nhận mất cập nhật | Thanh toán, ledger, audit hay giữ quyền truy cập |
| Saga + compensating action | Giao dịch nhiều dịch vụ không có distributed transaction | Bảo đảm rollback vật lý hoàn toàn mọi tác động bên ngoài |

**Clock timestamps không tự quyết định thứ tự đúng** khi các region khác nhau. Dùng sequence/transaction version hoặc ID lệnh theo nghiệp vụ; nêu rõ policy khi event đến trễ, out-of-order hoặc lặp lại. Đối với distributed saga, compensation phải được thiết kế có kiểm soát: một email đã gửi không thể “rollback”, một khoản tiền đã chuyển có thể cần một giao dịch hoàn tiền độc lập.

## 14. Tình huống thiết kế: ứng dụng đặt hàng Java/Spring Boot

Giả sử doanh nghiệp có khách hàng ở hai khu vực; yêu cầu frontend tiếp tục nhận traffic khi mất một region, giao dịch thanh toán không bị nhân đôi, ảnh hóa đơn được lưu trong vùng địa lý hợp lệ và event xử lý có thể phát lại.

**Phương án tham khảo:** hai Cloud Run services (hoặc hai GKE regional clusters) chạy cùng image digest, global external Application Load Balancer cùng service-health/failover policy; dữ liệu giao dịch đặt hàng trong Spanner multi-region configuration **có hỗ trợ ở khu vực được chọn**; object trong Cloud Storage dual-region tương thích địa lý; Pub/Sub làm event bus với transactional outbox và idempotent consumers.

~~~mermaid
flowchart TB
  USER[Clients] --> GLB[Global external ALB]
  GLB --> API_A[Cloud Run Region A]
  GLB --> API_B[Cloud Run Region B]
  API_A --> SP[Spanner multi-region: orders / ledger]
  API_B --> SP
  SP --> OUT[Outbox table / publisher]
  OUT --> PUB[Pub/Sub]
  PUB --> WORKER_A[Consumer Region A]
  PUB --> WORKER_B[Consumer Region B]
  API_A --> OBJ[Cloud Storage dual-region: invoice object]
  API_B --> OBJ
  API_A --> OBS[Cloud Monitoring / Logging / Tracing]
  API_B --> OBS
~~~

Hai consumer ở A/B phải được cấu hình theo **cùng subscription hoặc các subscription có mục đích rõ ràng**; nếu mỗi bên có subscription độc lập thì mỗi message có thể được gửi đến cả hai bên và ứng dụng phải biết đó là hành vi mong muốn. Sơ đồ mang tính khái niệm; không giả định Pub/Sub tự nhân bản message như một quorum database và không giả định bất kỳ cặp region nào đều được Spanner/Cloud Storage hỗ trợ.

### Consistency contract theo thành phần

| Luồng | Contract | Cơ chế |
|---|---|---|
| Tạo đơn và trừ tồn kho | Không có hai đơn cùng tiêu thụ một đơn vị tồn hợp lệ; read sau commit đúng | Spanner transaction và unique business key |
| Thanh toán | Retry không tạo charge thứ hai | Idempotency key được payment provider chấp nhận hoặc ledger kiểm soát |
| Event order-created | Không mất event sau DB commit; có thể gửi/nhận lặp | Transactional outbox và consumer dedupe |
| Giỏ hàng | Có thể chấp nhận trạng thái hơi cũ theo phiên | App/session policy, merge/version rule |
| Hóa đơn PDF | Không dùng object ở region dự phòng trước khi replication xong nếu cần RPO nghiêm ngặt | Dual-region storage, replication monitoring và business retry |
| Báo cáo | Cho phép đọc cũ theo độ trễ tối đa được duyệt | Stale read/analytics pipeline |

Nếu doanh nghiệp bắt buộc **RPO 0 cho file hóa đơn đã xác nhận với khách hàng**, không đủ để chỉ chọn turbo replication mục tiêu 15 phút. Cần sửa quy trình xác nhận (chỉ hoàn thành sau khi đạt điều kiện bền vững mong muốn), lưu bản sao bằng cơ chế có xác nhận riêng hoặc xác định nguồn dữ liệu có thể tái tạo hóa đơn một cách đáng tin cậy từ transaction database.

### Quy trình request quan trọng

1. Gateway xác thực request và chuyển đến ứng dụng khỏe theo routing policy.
2. Ứng dụng xác thực idempotency key; chỉ một transaction thay đổi tồn kho/order.
3. Cùng transaction lưu outbox event và response/idempotency state.
4. API trả thành công sau commit hợp lệ; nếu client mất kết nối, retry vẫn nhận cùng kết quả nghiệp vụ.
5. Publisher chuyển outbox sang Pub/Sub, consumer idempotent xử lý.
6. Service tạo hóa đơn theo luồng riêng, theo dõi replicated object và thông báo trạng thái phù hợp.

Tách **transactional consistency** khỏi **độ sẵn sàng của trải nghiệm**: ứng dụng có thể tạm thời không gửi email hoặc cập nhật dashboard nhưng vẫn không được vi phạm bất biến thanh toán.

## 15. Failover và failback: không chỉ chuyển traffic

Một kiến trúc đa region cần **hai quy trình khác nhau**:

- **Failover:** phục hồi ở region còn khỏe mà vẫn tuân thủ write ownership, data correctness và RTO/RPO.
- **Failback:** khi region ban đầu phục hồi, đồng bộ dữ liệu theo chiều cần thiết, chuyển quyền sở hữu và traffic về an toàn. Không được tự động failback chỉ vì health check vừa chuyển xanh.

### Runbook failover theo thứ tự

1. **Phát hiện và xác minh:** so sánh synthetic checks từ nhiều địa điểm, lỗi người dùng, backend health, status database và cloud status. Loại trừ lỗi cấu hình, rollout hoặc vấn đề mạng cục bộ.
2. **Tuyên bố DR:** incident commander quyết định kích hoạt theo ngưỡng đã định; ghi timestamp và người phê duyệt.
3. **Kiểm tra consistency:** database có quorum tự phục hồi hay cần promotion? Nếu single-primary, xác nhận replication lag và RPO có thể mất.
4. **Fencing:** bảo đảm writer cũ không còn hợp lệ theo hệ thống thẩm quyền; không để cả A và B commit cùng một nhóm dữ liệu.
5. **Kích hoạt capacity:** scale workload tại region B, kiểm tra quota, secret, IAM, KMS, network routes, external allowlists và database connections.
6. **Chuyển traffic:** global LB/service health, routing policy hoặc DNS theo thiết kế; cập nhật write endpoints khi thật sự chuyển database primary.
7. **Xác minh:** gọi smoke tests có idempotency, đọc/ghi nghiệp vụ, kiểm tra event backlog, object access, SLO và data invariants.
8. **Ổn định:** quan sát đủ cửa sổ vận hành và duy trì region B làm primary/owner theo chính sách, không chuyển ngược ngay.
9. **Lập kế hoạch failback:** khôi phục replication theo chiều ngược, kiểm tra mọi giao dịch, chuyển chủ có kiểm soát, diễn tập rollback failback.

Trong **Spanner multi-region**, hệ thống có cơ chế leader failover dựa trên quorum khi phù hợp; ứng dụng không nên tự xây thao tác promote thủ công kiểu Cloud SQL cho một dịch vụ có replication quản lý. Trong **Cloud SQL DR**, việc promote/replica failover và sửa kết nối là phần của runbook; advanced DR có những thao tác riêng. Runbook cần chia nhánh theo datastore chứ không dùng một lệnh “promote database” chung cho mọi công nghệ.

### Điểm quyết định go/no-go

Nên đặt tiêu chí cụ thể: mất region kéo dài bao lâu thì kích hoạt? Khi replication lag vượt RPO, có dừng ghi để chờ đồng bộ hay phải chấp nhận phục hồi từ một điểm khôi phục cũ hơn? Ai có quyền phê duyệt nguy cơ mất giao dịch? Khi không thể xác nhận primary cũ đã bị fence, hệ thống nên chuyển sang read-only/degraded mode hay tạm ngừng ghi? Những quyết định này phải được chốt **trước** sự cố cùng business owner.

### Tránh sai lầm “tự động failover = dữ liệu chắc chắn đúng”

Tự động hóa định tuyến có thể hoàn thành trước khi database, cache và consumer đồng bộ trạng thái. Nếu frontend đã sang B nhưng database chỉ đọc được dữ liệu cũ, trả HTTP 200 cho yêu cầu thanh toán có thể là thất bại nghiêm trọng hơn từ chối tạm thời. Hãy điều khiển readiness và feature flags theo **capability**: có thể cho phép xem catalog nhưng tạm chặn checkout cho đến khi consistency gate đạt điều kiện.

## 16. Giám sát SLO và tính nhất quán

Dashboard phải ghép tín hiệu ở **application, datastore, messaging và traffic routing**, có breakdown theo region/version:

| Tín hiệu | Cách sử dụng |
|---|---|
| Request success/error, p95/p99 latency theo region | Nhận biết lỗi user-facing và backend không đều giữa các vùng |
| Global LB backend health, traffic share, service health | Phát hiện routing sai, mất backend hoặc failover không diễn ra |
| DB write/read latency, transaction abort/retry | Phát hiện tác động của quorum/leader change và network RTT |
| Cloud SQL replication state/lag | Ước lượng dữ liệu nguy cơ mất trước khi promote replica |
| Spanner transaction latency, lock contention, leader region | Xác minh lựa chọn topology và thay đổi commit latency |
| Bigtable replication lag và lỗi theo cluster | Quan sát mức hội tụ, nguy cơ stale reads khi chuyển cluster |
| Cloud Storage replication/RPO metrics | Biết object nào đang chưa đạt mục tiêu redundancy liên region |
| Pub/Sub backlog, oldest unacked message, retry/DLQ | Phát hiện consumer ở một region không theo kịp và nguy cơ xử lý trùng |
| Idempotency conflict, event dedupe và fencing rejection | Phát hiện việc retry có an toàn hay có hai writer cạnh tranh |
| IAM/secret/KMS failures, DNS và egress latency | Phát hiện dependency ngoài database gây gián đoạn |

**Chỉ số tính nhất quán cần chủ động đo**, không đợi người dùng báo mất dữ liệu. Ví dụ chạy synthetic transaction theo tenant test, ghi một unique ID, đọc lại từ cả hai region theo consistency contract, rồi ghi nhận thời gian tới khi stale-read view hội tụ (nếu contract cho phép stale). Dữ liệu test phải được làm sạch và tách khỏi transaction người dùng.

Đo **RTO thực tế** từ thời điểm sự cố bắt đầu (hoặc phát hiện, nhưng phải ghi rõ cách tính) đến khi giao dịch thiết yếu đạt SLO trở lại. Đo **RPO thực tế** bằng các checkpoint/transaction IDs đã được xác nhận trước lỗi và những ID có ở hệ mới sau failover. Không dùng “replica healthy” làm bằng chứng rằng không mất write.

### Observability cho Java/Spring Boot

Ứng dụng nên log có cấu trúc với region, release, request ID, idempotency key **đã được làm sạch**, transaction ID và kết quả retry/rollback. Trace cần theo W3C context qua HTTP, gRPC và event headers khi phù hợp. Đặt alert trên error budget và invariant violations, không chỉ CPU hoặc số Pod đang chạy. Không log payload có PII, credential, token, số thẻ hay toàn bộ event tài chính.

## 17. Game day: kiểm thử khi network và dữ liệu không như dự kiến

Mỗi kịch bản phải có người phê duyệt, phạm vi sandbox/staging, phương án rollback, mức tải và chỉ số nghiệm thu. Không gây sự cố trên production chỉ để kiểm thử nếu chưa có change approval và điều kiện an toàn.

| Kịch bản | Điều cần chứng minh | Dấu hiệu thất bại |
|---|---|---|
| Một region backend unhealthy | Global LB/service health chuyển request tới nơi còn khỏe | Request tiếp tục đến backend lỗi; region B quá tải |
| Mất write-primary region Cloud SQL | Runbook promote/replica failover trong RTO đã duyệt | Quên fence, write endpoint không cập nhật, lag vượt RPO mà không được nhận diện |
| Spanner leader region không sẵn | Quorum/leader failover và transaction retry hoạt động | Application retry storm, lỗi nghiệp vụ hoặc latency vượt ngưỡng dài |
| Bigtable chuyển cluster | Application chấp nhận/đánh dấu stale data đúng contract | Đọc giá trị cũ như mới nhất và ra quyết định thanh toán |
| Object mới chưa replicate | Ứng dụng xử lý object tạm thời không khả dụng an toàn | Trả lỗi vĩnh viễn hoặc coi file chưa sao chép là đã bảo vệ toàn vùng |
| Pub/Sub consumer failover | Không mất xử lý nghiệp vụ, replay và dedupe đúng | Email/charge trùng, DLQ không được xử lý |
| A và B mất kết nối nhưng còn sống | Chỉ writer hợp lệ được commit; client lỗi ở mức chấp nhận | Split brain, hai ledger độc lập không thể reconcile |
| Sai IAM hoặc secret rollout ở cả hai region | Có break-glass/rollback và blast radius giới hạn | Common-mode outage dù compute nhiều vùng |
| Failback sau phục hồi | Dữ liệu đồng nhất, old region không ghi trùng | Mất giao dịch phát sinh ở DR region |

### Quy trình diễn tập đo lường

1. Ghi lại baseline 30–60 phút hoặc khoảng tải phù hợp: throughput, latency, lag, error rate và capacity.
2. Tiêm lỗi có kiểm soát vào **một thành phần** (không trộn nhiều kịch bản khi chưa hiểu kết quả).
3. Đo MTTD, thời gian ra quyết định, thời gian routing, database recovery và thời gian giao dịch thành công trở lại.
4. Đối chiếu số lượng giao dịch đã được xác nhận với dữ liệu sau lỗi; phát hiện ID thiếu/trùng, không chỉ row count.
5. Đo consistency contract: strong/read-your-writes/allowed staleness, ordering và compensation.
6. Khôi phục và thử failback; xác nhận không còn client sử dụng old endpoint.
7. Tạo action items: sửa runbook, tăng quota, cải thiện monitoring, giảm vòng retry hoặc thay đổi thiết kế.

Kết quả game day nên được lưu như evidence cho SRE/architecture review. Nếu chưa đạt RPO, đừng chỉ tăng retry: cần xem lại phương pháp đồng bộ dữ liệu hoặc điều chỉnh mục tiêu với business owner.

## 18. Bảo mật, residency, chi phí và vận hành

**Đa region làm tăng bề mặt quản trị.** Mỗi region phải có IAM bindings, runtime service identity, KMS/secret access, network egress policy, registry/image access, telemetry và quota. Cần kiểm tra mã hóa khi truyền giữa region, TLS, audit logs, data locality và khả năng cung cấp khóa khi một region lỗi. Với dữ liệu bị giới hạn địa lý, chọn database/bucket region pair được phê duyệt; không giả định “multi-region” mặc định đáp ứng residency.

Các khoản chi phí và trade-off phải tính:

- **Compute dự phòng:** active-active giữ replica chạy thường xuyên; warm/hot standby tốn capacity nhưng giảm RTO.
- **Database replication/quorum:** chi phí replica/storage và latency giao dịch qua WAN; Enterprise Plus hoặc phiên bản dịch vụ cao hơn có thể cần thiết cho topology.
- **Network transfer/egress:** write từ B đến leader A, object cross-region, app gọi DB on-prem hoặc third party.
- **Storage và backup:** object versioning, dual-region/turbo replication, snapshot và bản sao độc lập.
- **Quan sát và kiểm thử:** synthetic probes, log/trace ingestion, DR game days, private connectivity.
- **Rủi ro nghiệp vụ:** chi phí downtime và chi phí sai giao dịch có thể lớn hơn giá hạ tầng.

Không nhân availability của hai region như thể mọi sự cố là độc lập. Một lỗi image, rollout, policy hoặc secret có thể ảnh hưởng cả hai; SLO end-to-end và thử nghiệm common-mode mới cho thấy hiệu quả của redundancy.

### Ma trận chọn phương án ban đầu

| Nhu cầu chính | Hướng cân nhắc | Điều phải xác minh trước quyết định |
|---|---|---|
| RTO vài giờ, chi phí giới hạn | Active-passive với DR backup/cross-region replica | Restore time, RPO và quota đủ |
| Frontend cần chịu lỗi region, DB có một writer | Active-active compute + Cloud SQL DR hoặc DB single leader | Write RTT, promotion, fencing và app reconnect |
| Giao dịch toàn cục phải nhất quán | Spanner multi-region | Edition, topology hỗ trợ, quorum/leader latency và cost |
| Document DB managed với yêu cầu chịu region outage | Firestore multi-region location | Location cố định, query/transaction semantics, latency và quota |
| Time series có thể chấp nhận stale data | Bigtable replicated clusters | App profile, conflict, replication lag và read semantics |
| Object data phục vụ nhiều vùng | Cloud Storage dual/multi-region | Replication RPO, turbo availability, residency và backup |
| Dữ liệu theo tenant cần giữ ở khu vực | Geo-partition với explicit ownership | Cross-tenant access, fencing và quy trình chuyển chủ |

## 19. Bài tập thiết kế

**Bối cảnh:** một hệ thống thương mại điện tử có API Spring Boot, PostgreSQL, RabbitMQ, object ảnh hóa đơn và dịch vụ thanh toán bên ngoài. Người dùng ở hai khu vực; business yêu cầu checkout không trừ tiền hai lần, cho phép catalog chậm một chút, RTO giao dịch 20 phút và RPO dữ liệu đơn hàng phải được xác định rõ.

1. Vẽ failure domains: region, zone, DB writer, identity provider, external payment, event bus, object storage và DNS.
2. So sánh **active-passive Cloud SQL cross-region replica** với **active-active API + Spanner multi-region**. Nêu RTO, RPO, write latency, cost, thay đổi schema/code và điều kiện hỗ trợ region cho mỗi phương án.
3. Viết consistency contract cho thanh toán, order, giỏ hàng, catalog và hóa đơn.
4. Thiết kế idempotency key, transaction outbox và consumer dedupe. Mô tả chuyện gì xảy ra nếu API commit rồi mất kết nối trước khi gửi HTTP response.
5. Nếu chọn Cloud SQL, viết runbook promote, fencing, endpoint switch và failback. Nếu chọn Spanner, mô tả quorum/leader behavior và transaction retry.
6. Thiết kế global load balancing và kiểm tra health-based failover. Xác định cần minimum instances, timeout và capacity của region B.
7. Đề xuất dashboard cảnh báo replication lag, transaction latency, object replication RPO, event backlog và invariant violation.
8. Lập ba game days: mất region, network partition và trùng message. Xác định go/no-go và cách đo RPO thay vì chỉ xem Pod healthy.
9. Dự toán các nhóm chi phí cross-region replication, egress, standby và monitoring; xác nhận data residency.

**Đầu ra:** một sơ đồ kiến trúc, bảng lựa chọn datastore, consistency contract, runbook failover/failback, bảng test và các rủi ro còn mở. Không cần tạo tài nguyên production; có thể chạy POC trong sandbox đã được cấp phép.

## 20. Checklist trước khi phê duyệt kiến trúc đa region

- [ ] SLO, RTO, RPO và consistency contract đã được business/data owner phê duyệt.
- [ ] Mọi failure domain và dependency quan trọng đã có bản đồ.
- [ ] Mỗi dữ liệu có source of truth, write owner, read policy và conflict policy.
- [ ] Đã phân biệt replication sync/quorum với async, và biết khi nào cần promotion.
- [ ] Có fencing để ngăn old primary ghi sau khi failover; không có split brain chưa được kiểm soát.
- [ ] Client sử dụng idempotency key và consumer có deduplication khi cần.
- [ ] Outbox hoặc workflow đáng tin cậy nối transaction database với event publication.
- [ ] Traffic routing đã được thử khi backend/application unhealthy, không chỉ khi VM tắt.
- [ ] Region dự phòng đủ capacity, quota, IAM, KMS, networking, secrets và database connections.
- [ ] Database, storage và messaging đều có RPO/consistency riêng, không đánh đồng.
- [ ] Có cơ chế bảo vệ object/transaction trước xóa nhầm hoặc rollout hỏng; backup được thử restore.
- [ ] Data residency, privacy và cross-region transfer đã được review.
- [ ] Monitoring theo region đo SLO, latency, replication lag, stale reads và invariant violations.
- [ ] Runbook failover có người quyết định, điều kiện stop/go và kịch bản read-only khi cần.
- [ ] Failback có kế hoạch đồng bộ ngược và kiểm tra không còn dual writer.
- [ ] Game day đã đo RTO/RPO thực tế và chi phí dự phòng nằm trong ngân sách.

## 21. Kết luận

Thiết kế đa region không kết thúc ở việc triển khai ứng dụng vào hai nơi. Đội kiến trúc phải chọn mô hình quyền ghi, nêu rõ mức nhất quán cho từng dữ liệu, hiểu cách sản phẩm Google Cloud replicate/failover và xác nhận trade-off latency, availability, RTO/RPO. Spanner, Firestore, Cloud SQL, Bigtable và Cloud Storage có semantics khác nhau; lựa chọn đúng phụ thuộc vào bất biến nghiệp vụ và khả năng chấp nhận stale data hay mất dữ liệu. Khi kết hợp transaction an toàn, idempotency, fencing, routing được thử nghiệm, quan sát liên vùng và runbook failback, hệ thống mới có khả năng phục hồi **và giữ tính đúng đắn của nghiệp vụ** trong sự cố region.

## Tài liệu tham khảo

- [Google Cloud Architecture Center — Architecting disaster recovery for cloud infrastructure outages](https://docs.cloud.google.com/architecture/disaster-recovery)
- [Google Cloud Well-Architected Framework — Reliability](https://docs.cloud.google.com/architecture/framework/reliability)
- [Cloud Run — Serve traffic from multiple regions](https://docs.cloud.google.com/run/docs/multiple-regions)
- [Cloud Run — Automate cross-region failover with service health](https://docs.cloud.google.com/run/docs/configuring/configure-service-health)
- [Spanner — Regional, dual-region, and multi-region configurations](https://docs.cloud.google.com/spanner/docs/instance-configurations)
- [Spanner — Reads outside transactions, strong and stale reads](https://docs.cloud.google.com/spanner/docs/reads)
- [Spanner — Leader-aware routing](https://docs.cloud.google.com/spanner/docs/leader-aware-routing)
- [Spanner — Replica region types and voting quorum](https://docs.cloud.google.com/spanner/docs/region-types)
- [Cloud SQL for PostgreSQL — About disaster recovery](https://docs.cloud.google.com/sql/docs/postgres/intro-to-cloud-sql-disaster-recovery)
- [Cloud SQL for PostgreSQL — Promote cross-region replicas](https://docs.cloud.google.com/sql/docs/postgres/replication/cross-region-replicas)
- [Cloud SQL — Advanced disaster recovery](https://docs.cloud.google.com/sql/docs/postgres/use-advanced-disaster-recovery)
- [Firestore in Native mode — Database locations](https://docs.cloud.google.com/firestore/native/docs/locations)
- [Firestore in Native mode — Understand reads and writes at scale](https://docs.cloud.google.com/firestore/native/docs/understand-reads-writes-scale)
- [Bigtable — Replication overview](https://docs.cloud.google.com/bigtable/docs/replication-overview)
- [Bigtable — Examples of replication configurations](https://docs.cloud.google.com/bigtable/docs/replication-settings)
- [Cloud Storage — Data availability and durability](https://docs.cloud.google.com/storage/docs/availability-durability)
- [Pub/Sub — Message storage policies](https://docs.cloud.google.com/pubsub/docs/resource-location-restriction)
