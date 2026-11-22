# Lựa chọn rehost, replatform và refactor theo dịch vụ GCP

Di chuyển một ứng dụng lên Google Cloud không đồng nghĩa chỉ sao chép máy chủ sang một máy ảo khác. Một hệ thống còn phụ thuộc vào hệ điều hành, runtime, database, network, danh tính, giấy phép, quy trình triển khai và yêu cầu kinh doanh. Có workload cần được đưa lên cloud nhanh với rất ít thay đổi; có workload nên chuyển sang database được quản lý; cũng có hệ thống chỉ thực sự khai thác được lợi ích cloud khi được thiết kế lại theo các thành phần có khả năng mở rộng và phục hồi độc lập.

Trong chương **Di chuyển lên Google Cloud** của module **CLOUD_PROVIDERS_GCP**, bài này xây dựng một phương pháp chọn giữa **rehost** (lift and shift), **replatform** (lift and optimize) và **refactor** (move and improve/modernize). Các lựa chọn được ánh xạ tới Compute Engine, Google Cloud VMware Engine, Cloud SQL, AlloyDB for PostgreSQL, Cloud Run, Google Kubernetes Engine (GKE), Pub/Sub và các dịch vụ dữ liệu khác. Quyết định không dựa trên mức độ “cloud-native” trừu tượng, mà dựa trên mục tiêu, giới hạn, mức thay đổi chấp nhận được và khả năng kiểm chứng sau di chuyển.

## 1. Mục tiêu học tập

Sau bài học, người học có thể:

- Phân biệt rehost, replatform và refactor; nhận diện khi nào nên retain, retire, repurchase, relocate hoặc rebuild.
- Khảo sát workload, đo mức độ phụ thuộc và xác định business driver, SLO, RTO, RPO, yêu cầu tuân thủ.
- Chọn sản phẩm GCP đích theo đặc tính ứng dụng, database, trạng thái dữ liệu, khả năng mở rộng và năng lực đội ngũ.
- Lựa chọn Migrate to Virtual Machines, Database Migration Service hoặc phương án hiện đại hóa ứng dụng phù hợp.
- Ước lượng thời gian, chi phí, rủi ro, nợ kỹ thuật và chi phí vận hành dài hạn cho từng phương án.
- Thiết kế migration wave, pilot, rehearsal, cutover, rollback và validation.
- Tránh lỗi về dual writes, đồng bộ dữ liệu, quyền truy cập, mạng riêng, phiên bản runtime và chứng nhận phần mềm.
- Xây decision record có giả định, phương án bị loại, tiêu chí nghiệm thu và công việc tối ưu sau migration.

## 2. Ba chiến lược cốt lõi

### 2.1. Rehost: lift and shift

**Rehost** chuyển workload từ môi trường nguồn sang một môi trường chạy trên GCP với rất ít hoặc không sửa mã nguồn/kiến trúc. Ví dụ, một máy ảo ứng dụng Java trên VMware được chuyển sang **Compute Engine** với cấu hình OS, runtime và mô hình service tương tự.

Đặc trưng:

- Mức thay đổi nhỏ; dễ áp dụng khi không có source code hoặc vendor không cho phép sửa.
- Thời gian migration thường ngắn hơn so với viết lại chức năng.
- Giữ các giả định về VM, state, process và deployment; có thể tiếp tục dùng công cụ vận hành sẵn có.
- Chỉ tạo lợi ích cloud một phần: việc cài patch OS, quản lý middleware, HA và backup vẫn có thể do nhóm tự chịu trách nhiệm.
- Chi phí VM, license, storage và vận hành có thể cao nếu chuyển nguyên sizing từ on-premises mà không đo lại.

Không nên gọi rehost là “không rủi ro”. Cấu hình IP, DNS, latency đến database, OS driver, firewall, giấy phép phần mềm và cấu trúc đĩa có thể khiến bản sao VM không hoạt động như môi trường nguồn.

### 2.2. Replatform: lift and optimize

**Replatform** giữ phần lớn logic nghiệp vụ nhưng thay một hoặc vài tầng nền tảng để giảm công vận hành hoặc tăng khả năng mở rộng. Ví dụ:

- PostgreSQL tự vận hành trên VM sang **Cloud SQL for PostgreSQL**.
- MySQL trên VM sang **Cloud SQL for MySQL**.
- Ứng dụng HTTP stateless được container hóa, chuyển từ VM sang **Cloud Run** mà không đổi lớn domain model.
- Application server trên VM chuyển sang **GKE** hoặc App Engine khi có nhu cầu quản lý container/runtime tương ứng.

Replatform thường phải thay cấu hình connection string, secret, service account, health check, persistent storage, startup, backup hoặc driver. Chọn cách này khi lợi ích managed service cao và ứng dụng có thể thích nghi với giới hạn dịch vụ mà không cần tái thiết kế sâu.

Rủi ro đặc trưng: compatibility của database extension, version, JDBC driver, network, connection pooling, filesystem tạm, runtime lifecycle và một số tính năng OS không còn được phép truy cập.

### 2.3. Refactor: move and improve

**Refactor** thay đáng kể cấu trúc mã nguồn, thành phần triển khai hoặc cách phối hợp nghiệp vụ để tận dụng các cơ chế cloud-native. Ví dụ:

- Tách một monolith Java thành các bounded context, service riêng trên Cloud Run/GKE.
- Thay xử lý đồng bộ kéo dài bằng **Pub/Sub** và worker có retry/idempotency.
- Chuyển file local thành Cloud Storage, session local thành giải pháp state/session phù hợp.
- Áp dụng CI/CD, progressive delivery, autoscaling, resilience, observability và security by design.
- Chuyển quy trình batch thành Cloud Run Jobs/Workflows/Dataflow khi có tính phù hợp.

Lợi ích có thể gồm độc lập scale, phát hành nhanh hơn, giảm coupling và tăng khả năng chống lỗi. Đổi lại, chi phí phát triển, test tích hợp, quản trị API/event schema, phân tán dữ liệu và độ phức tạp vận hành cao hơn. Refactor toàn bộ trong một wave chỉ vì “microservices hiện đại hơn” là quyết định có rủi ro.

### 2.4. Các chiến lược khác và khác biệt cách gọi

Các framework migration không nhất thiết dùng cùng một bộ chữ “R”. Google Cloud Architecture Center mô tả nhiều kiểu như rehost, replatform, refactor, re-architect, rebuild, repurchase; tài liệu lập kế hoạch thường bổ sung retain và retire. Một số tài liệu tách riêng **relocate**.

| Chiến lược | Ý nghĩa ngắn gọn | Ví dụ |
|---|---|---|
| Rehost | Chuyển môi trường chạy với ít thay đổi | VMware/AWS/Azure VM sang Compute Engine |
| Replatform | Chuyển tầng platform có tối ưu nhẹ | PostgreSQL trên VM sang Cloud SQL |
| Refactor | Thay cấu trúc code/kiến trúc để cải thiện | Monolith sang các module/service độc lập |
| Re-architect | Thiết kế lại kiến trúc tổng thể | Đồng bộ điểm-điểm thành event-driven |
| Rebuild | Xây lại chức năng/ứng dụng | Thay hệ thống cũ bằng code mới |
| Repurchase | Thay sản phẩm bằng SaaS/giải pháp mua khác | Thay tự vận hành phần mềm bằng SaaS |
| Retain | Chưa di chuyển trong đợt này | Giữ hệ thống có ràng buộc pháp lý hoặc vendor |
| Retire | Ngừng sử dụng | Tắt batch hoặc hệ thống không còn người dùng |
| Relocate | Chuyển platform/hạ tầng với thay đổi nhỏ, đôi khi giữ stack VMware | VMware vào Google Cloud VMware Engine |

**Không cưỡng ép tất cả workload vào ba lựa chọn.** Retire có thể tiết kiệm nhiều hơn so với rehost một ứng dụng không còn giá trị. Repurchase có thể tối ưu hơn refactor nếu chức năng được một SaaS đáp ứng đầy đủ.

## 3. Đánh giá trước khi chọn chiến lược

Quyết định migration phải bắt đầu từ dữ liệu khảo sát, không phải từ danh sách dịch vụ yêu thích.

### 3.1. Inventory và dependency mapping

Mỗi ứng dụng cần tối thiểu:

| Trường | Câu hỏi cần trả lời |
|---|---|
| Owner và business criticality | Ai phê duyệt thay đổi, hậu quả nếu ngừng hoạt động? |
| Runtime/OS | Windows/Linux, phiên bản, kiến trúc CPU, agent, license? |
| Compute | CPU p50/p95/peak, RAM working set, IOPS, throughput, GPU? |
| Storage | Disk local, network share, object, retention, backup? |
| Data | Engine, phiên bản, schema, size, tốc độ thay đổi, CDC khả dụng? |
| Dependencies | DNS, LDAP/AD, mail, API, payment, ERP, shared database? |
| Network | Ingress/egress, private routes, NAT, ports, fixed IP, mTLS? |
| Security | IAM, encryption, key ownership, data residency, audit? |
| SLO | Availability, latency p95/p99, throughput, peak season? |
| Recovery | RTO, RPO, backup, restore test, DR region? |
| Delivery | Có source/build pipeline không? Test coverage và release cadence? |
| Commercial | License, support contract, vendor certification, EOL? |
| Economics | TCO hiện tại, chi phí nhân sự, hạn hợp đồng data center? |

**Dependency graph** phải chỉ rõ hướng kết nối và lưu lượng, không chỉ liệt kê máy nào cùng subnet. Ví dụ API A phụ thuộc Database B với 20 ms p99 và phụ thuộc LDAP C mỗi request: di chuyển A trước nhưng giữ B/C ở on-premises có thể tăng latency lớn hoặc làm lỗi xác thực.

~~~mermaid
flowchart LR
    Users[Người dùng] --> W[Web/API VM]
    W --> DB[(PostgreSQL nguồn)]
    W --> AD[Directory/LDAP]
    W --> File[File share]
    Batch[Batch VM] --> DB
    Batch --> Partner[API đối tác]
~~~

Đánh dấu dependency bằng mức độ: **hard dependency** trong request path, **soft dependency** có thể retry/queue, và **batch dependency** theo lịch. Nhóm thành migration wave có thể giữ giao dịch quan trọng gần nhau.

### 3.2. Baseline cần đo trước khi di chuyển

- Lưu lượng theo giờ/ngày/tuần, spike và mùa cao điểm.
- HTTP/API latency p50/p95/p99, error rate, timeout, retry.
- CPU/RAM/GC, số kết nối database, IOPS, disk latency và dung lượng.
- Network flows giữa các hệ thống, bandwidth, peak throughput.
- Backup/restore time, RPO và failover procedures.
- Thời gian deploy và tần suất sự cố.
- Chi phí vận hành, license, monitoring, backup, data transfer.

Giữ baseline tối thiểu qua một chu kỳ sử dụng đại diện; một ảnh chụp CPU trung bình trong ngày thường không đủ để sizing VM hoặc database.

### 3.3. Công cụ khám phá và đánh giá

**Migration Center** giúp thu thập và đánh giá inventory/phụ thuộc, hỗ trợ hoạch định chi phí và chọn migration path theo phạm vi được hỗ trợ. Kết quả assessment là dữ liệu đầu vào, không thay thế xác minh ứng dụng, bảo mật, license và thử nghiệm cutover.

Đối với VMware hoặc VM từ cloud khác, rà soát thêm danh sách operating system, disk, encryption và cấu hình được **Migrate to Virtual Machines** hỗ trợ. Với database, kiểm tra bảng hỗ trợ phiên bản nguồn/đích của **Database Migration Service (DMS)** và tính năng SQL/extension thực tế.

## 4. Tiêu chí chọn rehost, replatform hay refactor

### 4.1. Ma trận so sánh

| Tiêu chí | Rehost | Replatform | Refactor |
|---|---|---|---|
| Mức sửa code | Không hoặc rất ít | Ít đến vừa | Vừa đến lớn |
| Thời gian triển khai ban đầu | Thường ngắn | Trung bình | Thường dài |
| Rủi ro thay đổi business logic | Thấp hơn | Trung bình | Cao hơn |
| Nợ kỹ thuật được xử lý | Ít | Một phần | Có thể xử lý đáng kể |
| Mức dùng managed services | Hạn chế | Vừa đến cao | Cao nếu thiết kế phù hợp |
| Công quản lý OS/runtime | Giữ lại | Có thể giảm | Có thể giảm nhiều |
| Tính độc lập scale | Tương tự nguồn | Tốt hơn với platform phù hợp | Tốt nếu tách đúng workload |
| Phức tạp testing | Tập trung môi trường/config | Thêm compatibility test | Contract, integration, event, resilience |
| TCO dài hạn | Có thể còn cao | Có cơ hội giảm | Có cơ hội tối ưu nhưng phải tính chi phí phát triển |
| Khả năng rollback | Phụ thuộc cutover | Phụ thuộc dữ liệu đã ghi ở đích | Khó hơn nếu thay đổi API/data semantics |

“Thấp hơn/cao hơn” là xu hướng, không phải cam kết. Một rehost Oracle/Windows rất lớn có thể phức tạp hơn refactor một service stateless nhỏ.

### 4.2. Quy tắc ra quyết định

**Ưu tiên rehost** khi:

- Deadline thoát data center gần, không còn thời gian thay code.
- Ứng dụng vendor/black-box, không có source hoặc license chỉ chứng nhận trên VM.
- Ứng dụng ổn định, chức năng ít thay đổi, đủ khả năng vận hành OS/DB.
- Cần giảm rủi ro dịch chuyển trước rồi mới tối ưu theo wave tiếp theo.

**Ưu tiên replatform** khi:

- Core business logic dùng được mà không viết lại.
- Managed database/runtime đích hỗ trợ đầy đủ tính năng và extension quan trọng.
- Hạ tầng và vận hành hiện tại đang tạo nhiều toil.
- Có thể kiểm thử đường truy cập dữ liệu, session, filesystem, network và startup.
- Tổ chức muốn có lợi ích cloud sớm nhưng kiểm soát phạm vi thay đổi.

**Ưu tiên refactor** khi:

- Phạm vi thay đổi có giá trị kinh doanh rõ: release cadence, scale, reliability hoặc tính năng mới.
- Monolith/batch đồng bộ đang làm nghẽn một phần hệ thống.
- Source code, test automation và product ownership sẵn sàng.
- Có khả năng chạy song song old/new paths và quản trị migration dữ liệu.
- Chấp nhận chi phí thiết kế, test phân tán, SRE/observability và schema evolution.

**Ưu tiên retain/retire/repurchase** khi compliance/vendor/hardware không cho di chuyển, sản phẩm đã hết giá trị hoặc SaaS giải quyết nhu cầu tốt hơn.

### 4.3. Không nên đưa ra quyết định bằng điểm số duy nhất

Có thể chấm các phương án theo thời gian, rủi ro cutover, chi phí 3 năm, effort engineering, SLO, security và mức giảm toil. Nhưng các yêu cầu như **data residency**, license không hợp lệ hoặc RPO không đáp ứng là **điều kiện loại**, không thể dùng điểm chi phí cao để bù.

Một bảng trọng số có thể hỗ trợ hội thảo ra quyết định, song phải lưu giả định, nguồn dữ liệu, ngày đánh giá và các rủi ro chưa được giải quyết.

## 5. Ánh xạ workload sang sản phẩm GCP

| Workload nguồn | Rehost | Replatform | Refactor |
|---|---|---|---|
| VMware VM chạy Java monolith | Compute Engine hoặc giữ VMware stack trên Google Cloud VMware Engine theo nhu cầu | Container hóa ít thay đổi lên Cloud Run/GKE, database riêng lên Cloud SQL | Tách domain modules/services, event-driven, per-service deploy |
| PostgreSQL/MySQL trên VM | VM DB trên Compute Engine (ngắn hạn, vẫn tự quản lý DB) | Cloud SQL hoặc AlloyDB cho PostgreSQL khi tương thích | Thiết kế lại mô hình dữ liệu/read model, tách transaction boundaries |
| Web API stateless .NET/Java/Node | VM trên Compute Engine | Cloud Run/App Engine/GKE | Cloud-native services, workflow/events và caching |
| Batch job theo cron | VM có scheduler | Cloud Run Jobs, Cloud Scheduler/Workflows phù hợp | Event-driven fan-out qua Pub/Sub/Dataflow |
| File server và ứng dụng ghi file | VM có disk hoặc network file system phù hợp | Cloud Storage/Filestore kết hợp app adapter | Tách metadata, object events, asynchronous processing |
| Data warehouse/ETL tự vận hành | VM/cluster trên GCE | BigQuery/Dataflow theo compatibility | Mô hình pipeline incremental/streaming và governance mới |
| Vendor app yêu cầu VMware | Compute Engine nếu OS/license được hỗ trợ; hoặc VMware Engine | Chỉ khi vendor chứng nhận managed platform | Thường cân nhắc thay sản phẩm (repurchase) hơn là tự sửa |

Bảng trên là **hướng đánh giá**, không phải bảng cam kết tương thích. Kiểm tra khu vực, hạn mức, license, tính năng managed service và lựa chọn connectivity cho từng ứng dụng.

## 6. Rehost chi tiết: Migrate to Virtual Machines và Compute Engine

### 6.1. Migrate to Virtual Machines làm được gì?

**Migrate to Virtual Machines** hỗ trợ chuyển VM/disk từ các nguồn được Google công bố như **on-premises VMware vSphere, AWS, Azure và Google Cloud VMware Engine** sang Compute Engine hoặc Persistent Disk. Đây là công cụ cho VM-level migration: không phải trình chuyển đổi tự động monolith thành Cloud Run hay database thành Cloud SQL.

Một migration thường có host project quản lý quy trình và một hoặc nhiều target projects nhận VM. Kiểm tra quyền, billing, API, destination region, OS và nguồn hỗ trợ trước khi bắt đầu.

### 6.2. Vòng đời VM migration

~~~mermaid
flowchart LR
    A[Discovery + inventory] --> B[Configure source/target]
    B --> C[Initial replication]
    C --> D[Test clone + validation]
    D --> E{Pass gates?}
    E -- No --> F[Fix compatibility/config]
    F --> D
    E -- Yes --> G[Final sync + cutover]
    G --> H[Production validation]
    H --> I[Finalize + decommission source]
~~~

- **Replication:** sao chép dữ liệu disk từ nguồn sang Google Cloud, có thể tiếp tục trong khi VM nguồn đang hoạt động.
- **Test clone:** tạo VM kiểm thử từ dữ liệu đã replicate để xác minh OS boot, ứng dụng, network, disk, license; không cho clone vô tình kết nối và ghi vào production dependency.
- **Cutover:** chuyển workload thực tế sang VM đích theo lịch, kiểm soát trạng thái dữ liệu/traffic và điểm rollback.
- **Finalize:** chỉ hoàn tất và thu hồi máy nguồn sau khi tiêu chí nghiệm thu, backup, giám sát và quy trình phê duyệt đạt.

VM disk replication không tự đảm bảo **application-consistent cutover** cho database có write volume cao. Đối với database cần tính nhất quán transaction và RPO chặt, đánh giá logical/physical DB replication, backup + restore, DMS hoặc cơ chế engine-specific thay vì chỉ snapshot/disk clone.

### 6.3. Thiết kế landing zone đích

Trước khi migrate VM, provision:

- Organization/folder/project và billing phù hợp.
- IAM của migration operator, VM runtime identity và break-glass access.
- VPC/subnet, private DNS, Cloud VPN/Interconnect nếu còn dependency on-premises.
- Firewall egress/ingress tối thiểu, không mở toàn Internet chỉ để VM boot.
- Image/OS/boot driver, disk type/size, region/zone và quota.
- Backup/DR, OS patching, logging/monitoring agents, alerting.
- Sizing dựa trên baseline, không bê nguyên số vCPU/RAM nếu chưa đo.

Với VM Windows hoặc phần mềm vendor, xác minh license, activation, OS support, kernel/driver, cấu hình domain join và bản quyền agent trước test clone.

### 6.4. Dùng Google Cloud VMware Engine khi nào?

Google Cloud VMware Engine cung cấp môi trường VMware managed chạy trên hạ tầng Google Cloud cho nhu cầu tiếp tục dùng VMware stack/vSphere. Việc **relocate** VMware workloads vào VMware Engine có thể giảm thay đổi guest OS và công cụ quản trị so với đổi thẳng sang Compute Engine, nhưng còn chi phí, license, capacity và yêu cầu network riêng.

Nếu mục tiêu dài hạn là bỏ VMware dependency, có thể lập kế hoạch hai bước: chuyển hoặc relocate trước, sau đó migrate từng VM từ VMware Engine sang Compute Engine/managed services khi phù hợp. Không gọi VMware Engine là “serverless replatform”.

## 7. Replatform ứng dụng: Compute Engine sang Cloud Run, GKE và App Engine

### 7.1. Cloud Run cho stateless HTTP service

Cloud Run thích hợp ứng dụng HTTP/container không cần quyền cấp OS và có thể xử lý vòng đời instance không cố định. Một ứng dụng Java/Spring Boot có thể giữ phần lớn business logic, nhưng thường phải thay:

- Cổng HTTP bind theo biến môi trường `PORT`; lắng nghe trên `0.0.0.0`.
- Không lưu dữ liệu bền vững trên filesystem tạm của container.
- Session và cache cần được externalize nếu lưu local trước đây.
- Secret dùng Secret Manager/workload identity, không nhúng file credentials.
- Logging sang stdout/stderr có cấu trúc, tracing/metrics phù hợp.
- Connection pool và max instances cần sizing để không làm nghẽn database.
- Startup/shutdown/health probes phù hợp timeout và autoscaling.

Ví dụ cấu hình Spring Boot:

~~~yaml
server:
  address: 0.0.0.0
  port: 8080

spring:
  datasource:
    hikari:
      maximum-pool-size: 10

management:
  endpoint:
    health:
      probes:
        enabled: true
~~~

Nếu service chọn cổng khác 8080, cấu hình Spring phải đọc đúng biến `PORT` do Cloud Run cung cấp. YAML trên là ví dụ đơn giản, không tự giải quyết Cloud SQL connectivity, identity, secret hoặc readiness cho mọi ứng dụng.

### 7.2. GKE khi cần Kubernetes capabilities

GKE phù hợp nếu cần sidecar, service mesh, custom scheduling, policy, operator hoặc nhiều workload phối hợp. Khi replatform từ VM sang container chạy GKE, phải xử lý:

- Container image, non-root user, CPU/memory requests và limits.
- Readiness/liveness/startup probes và graceful shutdown.
- Pod/service identity bằng Workload Identity Federation for GKE.
- Horizontal Pod Autoscaler, node capacity và quota.
- PersistentVolume/StorageClass cho stateful workload nếu có.
- Kubernetes manifests, Helm/GitOps, bảo mật image và rollback.

GKE Autopilot giảm trách nhiệm quản lý node so với Standard; lựa chọn vẫn tùy mức kiểm soát cần có và chi phí/tải. **Không chọn GKE chỉ vì “container”**: nếu ứng dụng HTTP đơn giản, Cloud Run thường có ít vận hành nền tảng hơn.

### 7.3. App Engine có còn phù hợp?

App Engine standard/flexible có thể phù hợp với ứng dụng đã dùng mô hình deployment của App Engine hoặc runtime được hỗ trợ. Với dự án mới, so sánh lifecycle, version/runtime support, khả năng chỉnh OS, networking và chi phí với Cloud Run và GKE. Không áp đặt App Engine như đích mặc định cho mọi app Java.

### 7.4. Containerization không mặc định là refactor

Đưa ứng dụng monolith vào container, chuyển cấu hình sang environment/secret và triển khai trên Cloud Run/GKE nhưng **giữ nguyên domain logic** thường được xếp replatform. Chỉ khi thay đổi đáng kể cấu trúc, trách nhiệm service, giao thức tương tác hoặc dữ liệu thì mới gọi refactor/re-architect.

## 8. Replatform dữ liệu: Cloud SQL, AlloyDB và DMS

### 8.1. Chọn database đích

| Nguồn | Đích cần đánh giá | Ghi chú |
|---|---|---|
| MySQL được hỗ trợ | Cloud SQL for MySQL | Kiểm tra version, charset/collation, engine features |
| PostgreSQL được hỗ trợ | Cloud SQL for PostgreSQL | Kiểm tra extension, logical replication, role/permission |
| PostgreSQL workload cần hiệu năng hoặc HA chuyên biệt | AlloyDB for PostgreSQL | Đánh giá compatibility, SLA, sizing, cost |
| SQL Server được hỗ trợ | Cloud SQL for SQL Server | Kiểm tra edition, SQL Agent, CLR, licensing, HA |
| Oracle hoặc SQL Server muốn chuyển sang PostgreSQL | Cloud SQL/AlloyDB for PostgreSQL trong kịch bản DMS hỗ trợ | Là chuyển đổi khác engine; cần schema/code conversion và test kỹ |

Danh sách phiên bản/nguồn/đích của **Database Migration Service** thay đổi theo engine và loại migration. Hãy xem trang **Supported source and destination databases** trước khi lập kế hoạch; không coi mọi nguồn Oracle, MariaDB hoặc SQL Server đều có đường đi giống nhau. DMS for MySQL không hỗ trợ MariaDB như một nguồn MySQL tương đương.

### 8.2. Database Migration Service (DMS)

DMS hỗ trợ các migration đồng nhất (ví dụ PostgreSQL sang Cloud SQL PostgreSQL) và một số migration khác engine (ví dụ nguồn Oracle/SQL Server sang PostgreSQL theo kịch bản được công bố). Tùy engine/migration scenario, có thể thực hiện snapshot ban đầu và **continuous replication/CDC** để giảm downtime.

Một luồng tổng quát:

~~~mermaid
flowchart LR
    S[(Source database)] -->|Initial copy| D[(Cloud SQL / AlloyDB)]
    S -->|Continuous change replication| D
    AppOld[App nguồn] --> S
    D --> Check[Data validation + lag checks]
    Check --> Gate{Ready to cut over?}
    Gate -- Yes --> Freeze[Quiesce writes / controlled cutover]
    Freeze --> AppNew[App đích]
    AppNew --> D
~~~

Điểm bắt buộc kiểm tra:

- Source và destination version/feature support.
- Kết nối private/public theo yêu cầu, firewall và replication access.
- Quyền database, replication slot/log retention, disk/IO và tác động lên source.
- Dung lượng, tốc độ thay đổi dữ liệu, tốc độ apply và độ trễ replication.
- Schema, indexes, sequences, triggers, stored procedures, users, collations và extension.
- Tính toàn vẹn dữ liệu cùng kiểm thử chức năng ứng dụng ở đích.

Không giả định continuous replication tương đương cutover **zero downtime**: vẫn cần điểm dừng hoặc điều phối ghi, kiểm tra replication lag về ngưỡng chấp nhận và chuyển connection/traffic an toàn.

### 8.3. Giới hạn thay đổi engine

Migrating Oracle sang PostgreSQL có thể yêu cầu sửa SQL dialect, stored procedures, sequence behavior, transaction semantics và data types. Đây thường là **replatform có conversion sâu** hoặc gần với **refactor dữ liệu** tùy mức thay đổi. Không được coi đây là “chỉ đổi connection string”.

Nếu ứng dụng phụ thuộc extension không có trên managed database, có thể cần giữ database tự quản lý tạm thời hoặc thay thiết kế. Không chọn managed database chỉ vì giảm công quản trị mà bỏ qua incompatibility có thể ngăn ứng dụng hoạt động.

## 9. Refactor từng bước: strangler pattern và event-driven

### 9.1. Vì sao tránh big-bang rewrite?

Viết lại toàn bộ monolith trước khi di chuyển có thể kéo dài dự án, làm mất những quy tắc nghiệp vụ không được tài liệu hóa, và khó xác định lỗi ở tầng migration hay ở code mới. **Strangler pattern** cho phép tách một phần chức năng theo giá trị/độ rủi ro, chuyển traffic dần qua router/API facade và giữ phần còn lại ở hệ thống cũ.

~~~mermaid
flowchart LR
    User[Client] --> Router[API facade / routing layer]
    Router -->|Legacy endpoints| Legacy[Monolith on VM]
    Router -->|New bounded context| New[Cloud Run / GKE service]
    Legacy --> DB[(Legacy DB)]
    New --> NewDB[(Owned datastore)]
    Legacy -.Integration events / outbox.-> Pub[Pub/Sub]
    Pub --> New
~~~

Ở giai đoạn đầu, service mới có thể dùng API của monolith để đọc/ghi theo hợp đồng, rồi chuyển quyền sở hữu dữ liệu từng bounded context khi đã giải quyết consistency.

### 9.2. Chọn slice đầu tiên

Ưu tiên chức năng:

- Có domain boundary rõ, ít transaction xuyên module.
- Có owner/SME sẵn sàng xác nhận business rules.
- Có thể kiểm thử end-to-end và chạy song song.
- Có giá trị rõ như giảm bottleneck, cải thiện release cadence hoặc trải nghiệm người dùng.
- Có khả năng rollback routing về legacy path.

Tránh mở đầu bằng chức năng thanh toán/cấp quyền lõi nếu test coverage, audit và dữ liệu chưa sẵn sàng.

### 9.3. Pub/Sub, Cloud Tasks và Workflows

- **Pub/Sub:** nhiều consumer, fan-out event và tích hợp bất đồng bộ; delivery có thể trùng, cần idempotent consumer.
- **Cloud Tasks:** điều phối công việc HTTP có retry, rate control và queue semantics; thích hợp một tác vụ nền hướng tới handler.
- **Workflows:** điều phối nhiều bước gọi API/Google Cloud services, thực thi có trạng thái và kiểm soát nhánh lỗi.
- **Eventarc:** route sự kiện được hỗ trợ từ nguồn Google Cloud tới service/handler.

Không chuyển mọi lời gọi đồng bộ sang event chỉ để “modernize”. Nếu business process cần phản hồi ngay và transaction rõ, API sync vẫn phù hợp. Nếu tách thành saga, phải thiết kế compensating action, timeout, poison message, audit và idempotency.

### 9.4. Tách dữ liệu khỏi monolith

Một vấn đề khó là quyền sở hữu dữ liệu. Nếu cả monolith và service mới cùng ghi một bảng, các ràng buộc nghiệp vụ có thể bị phá vỡ khi code mới và cũ khác nhau.

Lộ trình an toàn:

1. Xác định system of record cho từng entity.
2. Tạo API/event contract; phân biệt command và fact nghiệp vụ.
3. Một side chịu trách nhiệm ghi chính; side còn lại đọc qua API/projection.
4. Dùng transactional outbox/CDC khi cần phát thay đổi đáng tin cậy.
5. Kiểm thử duplicate, out-of-order, replay và consistency lag.
6. Chỉ thay đổi ownership sau khi có reconciliation và đường rollback.

**Dual write** hai database không cùng transaction phải được xử lý bằng pattern đáng tin cậy; không coi “ghi database A xong publish B” là atomic.

## 10. Hạ tầng nền: IAM, VPC, kết nối và bảo mật

### 10.1. Identity và quyền

- Tách service account của migration operator, replication tool, workload runtime và CI/CD.
- Áp IAM least privilege ở project/resource, tránh role Owner/Editor cho mọi runtime.
- Với Cloud Run/GKE/Compute Engine, ưu tiên service identity/workload identity thay JSON key lâu hạn.
- Secret từ Secret Manager, key encryption từ Cloud KMS khi yêu cầu, ghi audit logs cần thiết.
- Xác nhận quyền database ở lớp engine riêng với quyền IAM truy cập dịch vụ.

### 10.2. Network hybrid

Trong khi migration chưa hoàn tất, GCP và on-premises thường cần kết nối hybrid qua Cloud VPN hoặc Cloud Interconnect theo yêu cầu bandwidth/latency, VPC routing và bảo mật.

Các điểm phải kiểm tra:

- IP CIDR tránh overlap; đường đi return traffic rõ ràng.
- Firewall source/destination, protocol/port và private DNS.
- Nút nghẽn ở NAT, proxy, VPN throughput, egress cost.
- Endpoint TLS/certificate và hostname verification sau thay IP.
- Zone/region, VPC peering/Private Service Connect khi phù hợp.
- Bảo vệ dữ liệu khi replication, không mở inbound port rộng.

Nếu một app chuyển sang GCP nhưng database vẫn on-premises, request có thể gọi nhiều lần qua WAN. Đo p95/p99 network RTT và số round-trip trên request path, thay vì chỉ tính khoảng cách địa lý.

### 10.3. Compliance, residency và license

Data residency, retention và encryption có thể loại trừ một region hoặc migration path. Phần mềm thương mại thường có license tied to cores, hypervisor, cloud provider hoặc OS edition. Chỉ migrate khi xác nhận điều khoản và chứng nhận support từ vendor, đặc biệt với hệ thống database/ERP và agent legacy.

Không chuyển dữ liệu nhạy cảm vào project thử nghiệm mà chưa có data classification và guardrail. Tạo test fixtures tổng hợp hoặc de-identified theo chính sách.

## 11. TCO, FinOps và yêu cầu vận hành

### 11.1. Tính chi phí theo vòng đời

**Không dùng chỉ giá VM/giờ để so sánh.** Tổng chi phí của mỗi lựa chọn gồm:

\[
TCO_{3y} =
C_{\text{migration}}+
C_{\text{compute}}+
C_{\text{storage}}+
C_{\text{network}}+
C_{\text{license}}+
C_{\text{operations}}+
C_{\text{risk}} .
\]

Trong đó C_risk là ước lượng có giả định về downtime, data loss hoặc effort xử lý sự cố, không phải giá cloud invoice.

Các nhóm chi phí cần lập mô hình:

| Khoản mục | Rehost | Replatform | Refactor |
|---|---|---|---|
| Engineering migration | Ít thay đổi code | Điều chỉnh platform và test | Thiết kế lại, test và chuyển dữ liệu |
| Compute/runtime | VM 24/7 hoặc MIG | Managed runtime/container | Nhiều service độc lập, autoscale |
| Database | Self-managed VM | Managed DB | Có thể nhiều datastore/replica |
| Network/data transfer | Hybrid, egress, NAT | Vẫn cần hybrid thời gian đầu | Service-to-service traffic và events |
| Operations | OS, patch, backup, runbooks | Giảm một phần toil | Toil khác: event, distributed tracing, schema |
| License | Có thể giữ nguyên license legacy | Kiểm tra managed compatibility | Có thể thay hoặc bỏ license |
| Parallel run | VM nguồn và đích chạy đồng thời | Database replication + app đích | Legacy và modernized chạy dài hơn |

Trong giai đoạn migration, **double run** (hai môi trường hoạt động đồng thời) thường tạo chi phí tạm thời. Phải budget cho log retention, backup, transfer, support và rollback window.

### 11.2. Sizing và cam kết chi phí

Rehost thường chuyển tỷ lệ sizing có tính thừa dự phòng từ on-premises. Sau khi ổn định, đo lại CPU/RAM, IOPS, network, autoscaling rồi rightsizing. Không mua cam kết sử dụng dài hạn cho workload chưa biết kích thước tối ưu hoặc có khả năng sớm chuyển sang Cloud Run/managed service.

Replatform và refactor có thể giảm idle compute nhưng phát sinh cost mới như Cloud SQL HA/replicas, Pub/Sub, Cloud NAT, Artifact Registry, Cloud Logging và BigQuery. Dự báo theo lưu lượng thực và kiểm tra budget alert; alert không phải hard cap.

### 11.3. Khía cạnh carbon và tính bền vững

Tắt tài nguyên rảnh, chọn máy/region hiệu quả và dùng autoscaling có thể giảm mức sử dụng. Tuy nhiên, đừng tuyên bố footprint giảm cùng tỷ lệ với chi phí. Để đánh giá phát thải, dùng Carbon Footprint theo phạm vi hỗ trợ và kết hợp đơn vị nghiệp vụ, latency, reliability và cost.

## 12. Thiết kế migration waves

Không nên di chuyển các VM riêng lẻ theo thứ tự tùy ý. Wave cần gom nhóm theo dependency và mức độ quan trọng.

### 12.1. Một phương án wave

| Wave | Workload | Mục tiêu | Chiến lược mẫu |
|---|---|---|---|
| 0 - Foundation | Landing zone, IAM, VPC, backup, monitoring | Sẵn hạ tầng & guardrail | Chưa di chuyển workload |
| 1 - Pilot | Ứng dụng ít quan trọng, dependency đơn giản | Kiểm chứng tool/process | Rehost |
| 2 - Core rehost | VM legacy có RTO/RPO rõ | Thoát data center theo hạn | Rehost |
| 3 - Managed data | Database tương thích | Giảm toil/backup/patch | Replatform |
| 4 - App modernization | API stateless, batch độc lập | Autoscale/CI/CD | Replatform hoặc refactor |
| 5 - Domain refactor | Monolith module có owner | Độc lập deploy, tăng reliability | Refactor |

Thứ tự phải được điều chỉnh theo dependency. Nếu database cần được đồng bộ trước app, có thể thực hiện tiền chuyển dữ liệu và cutover chung trong một wave. Không ép “database wave 3” sau “app wave 2” khi kết nối WAN sẽ làm lỗi nghiệp vụ.

### 12.2. Wave có thể mixed strategy

Một hệ thống đặt hàng có thể chọn **rehost web VM** trong 2 tháng để thoát data center, **replatform PostgreSQL lên Cloud SQL** trong 3 tháng tiếp theo, và **refactor module gửi email qua Pub/Sub/Cloud Run** sau khi ổn định. Việc dùng chiến lược khác nhau theo component là bình thường; cần thống nhất kiến trúc mục tiêu cuối và tránh kéo dài tình trạng hybrid quá lâu.

## 13. Cutover, RTO/RPO và rollback

### 13.1. Chuẩn bị runbook cutover

Mỗi runbook cần:

- Scope ứng dụng/VM/database, owner và ngày cutover.
- Change window, người duyệt go/no-go và kênh incident.
- Freeze policy, source of truth và số lượng writes trong thời gian chuyển.
- Cách đo replication lag/CDC, xác minh last applied position.
- Cách chuyển DNS/traffic/router/connection strings.
- Smoke test và business transaction quan trọng.
- Tiêu chí rollback, điểm không thể rollback và người có thẩm quyền.
- Backup/restore test, RTO/RPO kỳ vọng và cách xử lý dữ liệu đã phát sinh trên đích.

### 13.2. Dữ liệu là điểm khó rollback

Rollback hạ tầng web service thường dễ hơn rollback **database đã nhận writes mới**. Sau cutover, nếu người dùng đã ghi vào database đích, chuyển traffic về source mà không đồng bộ ngược có thể làm mất giao dịch hoặc tạo split-brain.

Phương án:

1. Trước cutover: chạy nguồn là primary, đích là replica/read-only và xác minh.
2. Tại cutover: quiesce writes/đưa ứng dụng vào maintenance theo RPO đã duyệt.
3. Chờ replication catch-up và kiểm tra checkpoint.
4. Thay endpoint/secret/router để chỉ có một writer hợp lệ.
5. Mở traffic theo canary hoặc wave, giám sát validation.
6. Sau cutover: không “rollback DNS” tùy tiện khi có writes mới; dùng forward-fix, reverse replication được thiết kế trước hoặc data reconciliation.

Đối với hệ thống không có dual-write reconciliation, chọn rõ **rollback window** và **point of no return**. RPO gần zero đòi hỏi chiến lược DB replication/transaction phù hợp, không được chỉ hứa bằng VM snapshot.

### 13.3. DNS và traffic

Giảm DNS TTL trước cutover chỉ hỗ trợ rút thời gian cache ở các resolver tôn trọng TTL, không tạo chuyển đổi tức thời toàn mạng. Với ứng dụng nhiều endpoint, cần test health probes, session stickiness, connection draining, client retry và cached IP. Đối với microservices, có thể dùng load balancer/ingress để chia traffic canary và rollback revision nếu dữ liệu cho phép.

## 14. Validation: đừng chỉ kiểm tra “VM boot được”

Một migration thành công phải đáp ứng **functional equivalence**, security posture, SLO và khả năng vận hành.

### 14.1. Kiểm tra theo lớp

| Lớp | Bằng chứng cần có |
|---|---|
| Infrastructure | VM/container ready, disk, IP, DNS, quota |
| Identity | IAM/service account, secret, directory, RBAC |
| Network | Routes/firewall, TLS, private connection, latency |
| Data | Row counts, checksums/sampling, sequence/constraints, CDC lag |
| Function | Business workflows, integration/contract tests |
| Performance | p50/p95/p99, error rate, throughput, CPU/RAM/IOPS |
| Reliability | HA/failover, backup restore, RTO/RPO drills |
| Security | Audit logging, vulnerability scans, encryption, policy |
| Operations | Dashboards, alerts, SRE runbook, incident access |
| Economics | Daily cost run-rate, dual-run cost, budget owner |

Row count bằng nhau **không đủ** chứng minh dữ liệu đúng; có thể thiếu rows và thêm rows khác. Dùng hash theo partition, checksum/canonical comparison, business reconciliation và xác minh transaction semantics, đặc biệt với DB conversion.

### 14.2. Success criteria từ trước migration

Ví dụ cho API đặt hàng:

- 100% critical business acceptance tests pass.
- p99 latency không vượt baseline/SLO được duyệt trong giờ peak.
- Error rate trong error budget cho phép.
- Database không có mất giao dịch theo RPO cam kết; replication validated.
- Backup restore đã diễn tập, không chỉ backup job báo success.
- IAM không rộng hơn target policy, vulnerability critical được xử lý.
- Có rollback/forward-fix decision và owner trực sự cố.

Không được tự phát minh threshold cho ứng dụng chưa có baseline. Phải lấy từ product SLO, compliance và yêu cầu thương mại cụ thể.

## 15. Ví dụ thực tế 1: ERP vendor không có source code

**Nguồn:** ứng dụng ERP chạy trên VMware Windows VMs, vendor cung cấp MSI và hướng dẫn backup; license phụ thuộc OS/hypervisor. Khách hàng cần rời data center trước ngày hết hợp đồng.

**Đánh giá:**

- Không có quyền chỉnh code, refactor là không khả thi trong ngắn hạn.
- Kiểm tra vendor support trên Compute Engine/Google Cloud VMware Engine.
- Kiểm tra Windows license, máy chủ domain, SQL Server edition, network ports.
- Nếu Migrate to VMs hỗ trợ OS/source, pilot test clone và performance test.
- Nếu phải giữ stack VMware, cân nhắc VMware Engine và tính tổng chi phí dài hạn.

**Chiến lược sơ bộ:** rehost/relocate có kiểm soát, rồi rightsizing và đánh giá replatform khi vendor cho phép. Không cố chuyển ERP vendor sang Cloud Run chỉ để có cấu trúc “serverless”.

**Acceptance:** đăng nhập/SSO, kỳ báo cáo kế toán, in ấn, import/export, tích hợp đối tác, backup/restore và license compliance đều đạt.

## 16. Ví dụ thực tế 2: Java REST API và PostgreSQL trên hai VM

**Nguồn:** Spring Boot API trên Linux VM, PostgreSQL tự quản lý trên VM khác, load thay đổi theo giờ. Team có source code và integration tests, nhưng mất nhiều thời gian patch OS/DB.

**Phương án A - rehost:** chuyển hai VM lên Compute Engine bằng Migrate to VMs. Ưu: nhanh, ít sửa code. Nhược: vẫn quản lý database/OS, idle cost.

**Phương án B - replatform:** migrate PostgreSQL bằng DMS sang Cloud SQL for PostgreSQL; container hóa API và triển khai Cloud Run. Cần:

- Kiểm tra PostgreSQL extension/version/roles, replication permissions.
- Chọn Cloud SQL instance, HA/backups/PITR và private connectivity.
- Chuyển file cấu hình/credential sang environment/Secret Manager.
- Thay local session nếu có, kiểm tra Cloud Run request timeout/port.
- Tối ưu HikariCP pool theo max instances, dùng Cloud SQL connector/đường kết nối phù hợp.
- Test peak traffic, cutover lag và rollback data policy.

**Phương án C - refactor:** thêm Pub/Sub và worker riêng cho tạo PDF/email, tách một bounded context có nhu cầu scale độc lập. Mức thay đổi này chỉ nên làm khi đã xác định bottleneck/giá trị và có test idempotency.

**Lựa chọn mẫu:** B nếu DMS và Cloud Run tương thích; C làm một phần sau khi hệ thống replatform ổn định. Không cần gộp DB migration, containerization và event architecture rewrite trong một lần cutover nếu điều đó làm rủi ro vượt khả năng kiểm soát.

### 16.1. Ví dụ cấu hình Cloud Run cho API

~~~bash
gcloud run deploy orders-api \
  --image="REGION-docker.pkg.dev/PROJECT_ID/apps/orders-api:VERSION" \
  --region="REGION" \
  --service-account="orders-api-runtime@PROJECT_ID.iam.gserviceaccount.com" \
  --memory="1Gi" \
  --cpu="1" \
  --concurrency="40" \
  --max-instances="20"
~~~

Đây chỉ là **mẫu minh họa**. Trước khi chạy thật phải thay placeholder, kiểm tra image, permission, ingress/IAM, Cloud SQL connectivity, secret, region và quota. Đừng gán `--allow-unauthenticated` nếu API cần xác thực. Concurrency, CPU/memory và max instances phải đo bằng tải thật; không dùng các giá trị mẫu làm production default.

### 16.2. Sizing connection pool

Nếu max instances của Cloud Run là 20 và mỗi instance mở tối đa 10 kết nối DB, riêng API có thể tạo khoảng 200 kết nối, chưa tính các service khác. Phải sizing tổng pool so với Cloud SQL max connections và peak behavior. Tránh để autoscaling Cloud Run vô tình tạo cạn database connections.

## 17. Ví dụ thực tế 3: monolith báo cáo và batch xử lý file

**Nguồn:** một Java monolith chạy cron nightly để đọc file CSV hàng chục GB, cập nhật PostgreSQL và tạo báo cáo. Batch thường kéo dài khiến web API thiếu CPU.

**Rehost:** chuyển VM, giữ cron như cũ, phù hợp nếu deadline gấp.

**Replatform:** tách cron thành Cloud Run Job, file nguồn sang Cloud Storage, database sang Cloud SQL; vẫn giữ phần lớn Java transformation logic.

**Refactor:** khi dung lượng và yêu cầu analytics đủ lớn, thiết kế pipeline Pub/Sub/Dataflow và BigQuery cho phần tổng hợp; API nghiệp vụ chỉ truy vấn read model đã xuất bản. Tách retry/idempotency, checkpoint, schema validation và late data. Không giả định BigQuery có thể thay OLTP transaction trong mọi trường hợp.

**Quyết định:** đo data volume, completion deadline, job parallelism, I/O/egress, transformation effort và consistency. Nếu batch chỉ vài phút một đêm, Cloud Run Job có thể đủ; Dataflow chỉ hợp lý khi dữ liệu và phép tính biện minh cho vận hành bổ sung.

## 18. Thực hành lập migration decision record

Một bản ghi quyết định kiến trúc (ADR) giúp tránh thay đổi chiến lược vì ý kiến cá nhân hoặc thông tin thiếu nguồn.

### 18.1. Mẫu YAML phân loại workload

~~~yaml
workload:
  id: order-api
  owner: team-commerce
  criticality: high
  source:
    compute: linux-vm
    database: postgresql-self-managed
    dependencies:
      - identity-provider
      - payment-gateway
  requirements:
    availability_slo: "defined-by-product-team"
    p99_latency_slo: "defined-by-product-team"
    rto: "approved-target"
    rpo: "approved-target"
    data_residency: "approved-regions"
  options:
    rehost:
      target: compute-engine
      risk: operating-system-and-database-toil
    replatform:
      target: cloud-run-and-cloud-sql
      risk: database-compatibility-and-cutover
    refactor:
      target: cloud-run-services-and-pubsub
      risk: distributed-consistency-and-delivery
  selected: replatform
  assumptions:
    - supported-postgresql-version
    - app-is-stateless-or-session-can-be-externalized
  gates:
    - dms-compatibility-verified
    - private-connectivity-tested
    - load-tests-pass
    - replication-lag-within-rpo
    - rollback-runbook-approved
~~~

Các giá trị `defined-by-product-team`/`approved-target` cần được thay bằng SLO/RTO/RPO thực tế trước khi phê duyệt migration. File trên là **mẫu tài liệu**, không phải cấu hình Terraform hoặc lệnh có thể tự động triển khai.

### 18.2. Quy trình workshop 90 phút

1. **15 phút - Outcome:** thống nhất business driver, deadline, RTO/RPO, compliance, cost target.
2. **20 phút - Inventory:** xem dependency graph, runtime/DB, traffic và bottleneck.
3. **20 phút - Options:** điền rehost, replatform, refactor và retain/retire/repurchase nếu thích hợp.
4. **15 phút - Risks:** loại phương án không đáp ứng hard constraints; ghi các giả định chưa kiểm chứng.
5. **10 phút - Validation:** xác định PoC, test và tiêu chí go/no-go.
6. **10 phút - Decision:** chọn hướng, owner, wave, chi phí và ngày tái đánh giá.

Nếu sau workshop còn thiếu thông tin quan trọng như license support hoặc RPO thực tế, ghi **DECISION_PENDING** và chủ sở hữu việc kiểm chứng. Không tự gắn nhãn approved khi chưa có bằng chứng.

## 19. Các anti-pattern cần tránh

1. **Chọn mục tiêu theo trend:** ép mọi ứng dụng vào GKE/microservices dù Cloud Run hoặc VM là đủ.
2. **Đồng nhất replatform với không sửa code:** runtime managed thường đòi cấu hình, secret, filesystem, networking và health check.
3. **Coi DB disk replication đủ bảo đảm transaction:** high-write database cần kế hoạch engine-specific.
4. **Migrate tất cả một lúc:** thiếu pilot, wave và rollback path.
5. **Không khảo sát dependency:** DNS/LDAP/database hoặc API đối tác vẫn on-prem khiến latency tăng.
6. **Overprovision VM:** bê nguyên sizing theo máy vật lý cũ mà không đo usage.
7. **Đổi database engine không test dialect/extension:** lỗi business logic chỉ xuất hiện sau cutover.
8. **Chạy old và new writers đồng thời không kiểm soát:** split-brain, dữ liệu divergent, RPO không đáp ứng.
9. **Bỏ qua giấy phép vendor:** migration thành công kỹ thuật nhưng không hợp pháp/không được hỗ trợ.
10. **Không có post-migration optimization:** rehost xong rồi quên patching, DR, FinOps, rightsizing.
11. **Coi “can deploy” là “production ready”:** chưa có SLO, HA, backup restore test và alert.
12. **Đóng source quá sớm:** hủy rollback option trước khi ổn định, chưa reconcile dữ liệu.
13. **Dùng service account quyền Editor chung:** tăng blast radius và khó audit.
14. **Không ghi chi phí double-run:** chi phí migration tăng ngoài ngân sách.
15. **Chọn refactor lớn không có test coverage:** khó cô lập lỗi migration so với lỗi viết lại.

## 20. Checklist trước khi chốt chiến lược

### Khảo sát và thiết kế

- [ ] Workload owner, business criticality, deadline và phạm vi rõ ràng.
- [ ] Inventory đủ VM/OS/runtime/database/storage/identity/network.
- [ ] Có dependency graph và phân loại hard/soft/batch dependencies.
- [ ] Đã đo baseline traffic, p99, CPU/RAM/IOPS, database lag và chi phí.
- [ ] Đã kiểm tra license/vendor support và data residency.
- [ ] Có các lựa chọn rehost/replatform/refactor và xem xét retain/retire/repurchase.
- [ ] Đã ghi hard constraints, risks, assumptions và kiến trúc mục tiêu.

### Khả năng tương thích GCP

- [ ] Source/OS/disk/region được công cụ Migrate to Virtual Machines hỗ trợ nếu dùng.
- [ ] Database source/destination/version/extension được DMS hoặc kế hoạch khác hỗ trợ.
- [ ] Compute Engine/Cloud Run/GKE phù hợp workload và nhu cầu OS control.
- [ ] Landing zone, billing, IAM, VPC, private DNS, VPN/Interconnect đã sẵn sàng.
- [ ] Project và resource identity tách staging/prod; secret, KMS, firewall đúng policy.
- [ ] Quota, machine availability, managed service region và chi phí được kiểm tra.

### Migration và cutover

- [ ] Wave và pilot đã có owner, lịch và playbook.
- [ ] Có dữ liệu và test môi trường thật hoặc gần production.
- [ ] Đã diễn tập test clone, database migration, network và cutover.
- [ ] Có validation về dữ liệu, business workflow, p99 và error rate.
- [ ] Có điểm go/no-go, rollback plan, điểm không thể quay lại và RTO/RPO rõ.
- [ ] Cơ chế bảo đảm một nguồn ghi tại thời điểm cutover đã xác định.
- [ ] Có alert/log/trace/backup/restore và incident response sau cutover.
- [ ] Có kế hoạch decommission source và đối soát chi phí sau ổn định.

## 21. Tài liệu tham khảo chính thức

- [Google Cloud Architecture Center - Migrate to Google Cloud: Get started](https://cloud.google.com/architecture/migration-to-gcp-getting-started)
- [Migration and modernization overview](https://cloud.google.com/docs/migration/overview/migrate-modernize-overview)
- [Migration Center documentation](https://cloud.google.com/migration-center/docs)
- [Migrate to Virtual Machines documentation](https://cloud.google.com/migrate/virtual-machines/docs/5.0)
- [Migrate to Virtual Machines - Architecture](https://cloud.google.com/migrate/virtual-machines/docs/5.0/discover/architecture)
- [Migrate to Virtual Machines - VM migration lifecycle](https://cloud.google.com/migrate/virtual-machines/docs/5.0/discover/lifecycle)
- [Migrate to Virtual Machines - Supported operating systems](https://cloud.google.com/migrate/virtual-machines/docs/5.0/discover/supported-os-versions)
- [Google Cloud VMware Engine documentation](https://cloud.google.com/vmware-engine/docs)
- [Database Migration Service - Supported source and destination databases](https://cloud.google.com/database-migration/docs/supported-databases)
- [Database Migration Service documentation](https://cloud.google.com/database-migration/docs)
- [Cloud SQL documentation](https://cloud.google.com/sql/docs)
- [AlloyDB documentation](https://cloud.google.com/alloydb/docs)
- [Cloud Run documentation](https://cloud.google.com/run/docs)
- [Google Kubernetes Engine documentation](https://cloud.google.com/kubernetes-engine/docs)
- [Cloud VPN documentation](https://cloud.google.com/network-connectivity/docs/vpn)
- [Cloud Interconnect documentation](https://cloud.google.com/network-connectivity/docs/interconnect)
- [Cloud Architecture Framework - Reliability](https://cloud.google.com/architecture/framework/reliability)
- [Cloud Architecture Framework - Cost optimization](https://cloud.google.com/architecture/framework/cost-optimization)

## 22. Tổng kết

**Rehost** phù hợp khi cần dịch chuyển với phạm vi thay đổi thấp, giới hạn về mã nguồn hoặc deadline gấp; **replatform** phù hợp khi core business logic còn tốt nhưng cần giảm vận hành nhờ database/runtime managed; **refactor** phù hợp khi nhu cầu scale, reliability hoặc phát hành đòi thay đổi kiến trúc và tổ chức có đủ năng lực kiểm thử, vận hành hệ phân tán.

Mỗi workload có thể đi qua nhiều chiến lược theo thời gian. Một quyết định chất lượng phải được gắn với **inventory và dependency rõ ràng, ràng buộc cứng được xác nhận, TCO và SLO đo được, migration wave có test/rehearsal, cutover dữ liệu an toàn và kế hoạch rollback có giới hạn cụ thể**. Google Cloud cung cấp dịch vụ và công cụ để thực hiện các phương án này; trách nhiệm chọn đường đi phù hợp và chứng minh kết quả vẫn thuộc về nhóm kiến trúc, sản phẩm và vận hành.
