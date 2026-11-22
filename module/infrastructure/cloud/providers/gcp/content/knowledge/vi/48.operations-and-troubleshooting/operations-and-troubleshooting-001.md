# Kiểm tra production readiness cho workload GCP

Một ứng dụng Java có thể vượt qua unit test, được triển khai thành công lên Cloud Run hoặc GKE và trả HTTP 200 trong môi trường staging nhưng vẫn chưa sẵn sàng phục vụ người dùng thật. Ví dụ, API không có cảnh báo khi tỷ lệ lỗi tăng, Cloud SQL chưa từng được kiểm tra phục hồi, service account có quyền quá rộng, container không xử lý SIGTERM, quota không đủ cho giờ cao điểm và không ai biết ai có quyền quyết định rollback.

**Production readiness review (PRR)** là quá trình đánh giá có bằng chứng liệu workload đã đáp ứng các yêu cầu về **chức năng, bảo mật, độ tin cậy, khả năng vận hành, hiệu năng, quy trình phát hành và chi phí** trước khi nhận traffic production hay chưa. PRR không chỉ làm một lần trước ngày ra mắt; các thay đổi lớn về kiến trúc, lưu lượng, dữ liệu và quy trình cũng có thể cần đánh giá lại.

Bài học thuộc chương **Vận hành và xử lý sự cố** trong module **CLOUD_PROVIDERS_GCP**. Module khám phá Google Cloud từ tổ chức project, IAM và VPC đến Compute Engine, GKE, Cloud Run, dịch vụ lưu trữ và cơ sở dữ liệu. Qua các tình huống triển khai, người học biết lựa chọn dịch vụ, bảo vệ tài nguyên, tự động hóa phát hành và theo dõi độ tin cậy cùng chi phí. Bài này nối các kiến thức đó thành một quy trình kiểm tra trước khi một workload được đưa vào production.

## Mục tiêu học tập

Sau bài học, người học có thể:

- Giải thích phạm vi và đầu ra của production readiness review.
- Xây ma trận tiêu chí **GO / CONDITIONAL GO / NO-GO** theo mức độ rủi ro.
- Thu thập bằng chứng cấu hình, kết quả kiểm thử và chủ sở hữu.
- Đánh giá workload Cloud Run, GKE, Compute Engine, Cloud SQL và các dịch vụ tích hợp.
- Kiểm tra SLI/SLO, error budget, alerting, logging, tracing và incident response.
- Xác minh IAM, networking, secrets, encryption, supply-chain và chính sách dữ liệu.
- Kiểm tra capacity, quota, autoscaling, backup/restore và disaster recovery.
- Chuẩn bị quy trình canary, rollback, on-call, runbook và cost guardrails.
- Thực hiện một cuộc PRR mẫu cho API Java/Spring Boot trên Google Cloud.
- Viết biên bản, phân công remediation và đưa ra quyết định có thể kiểm toán.

## 1. Production readiness thực sự là gì?

**Production readiness** không phải một nhãn được gán cho resource sau khi deploy. Nó là trạng thái chứng minh hệ thống và đội vận hành **có thể phục vụ, phát hiện lỗi, ứng phó, phục hồi và kiểm soát thay đổi** trong điều kiện thực tế.

Google Cloud Well-Architected Framework nhấn mạnh các trụ cột operational excellence, reliability, security, performance và cost optimization. Trong thực tế, PRR cần liên kết mục tiêu nghiệp vụ với bằng chứng kỹ thuật.

| Trục kiểm tra | Câu hỏi trọng tâm | Bằng chứng điển hình |
|---|---|---|
| Nghiệp vụ và ownership | Ai chịu trách nhiệm, dịch vụ phục vụ ai? | Service catalog, RACI, business sign-off |
| Độ tin cậy | SLO, failure domains, HA/DR đã đủ chưa? | SLO, sơ đồ, test failover |
| Khả năng quan sát | Sự cố có được phát hiện nhanh và điều tra được không? | Dashboard, alert test, logs/traces |
| Bảo mật | Chỉ đúng danh tính được truy cập đúng dữ liệu? | IAM review, network test, secret scan |
| Dữ liệu | Có thể phục hồi và bảo toàn tính nhất quán? | Backup policy, restore test, reconciliation |
| Hiệu năng | Hệ thống chịu được tải và tăng trưởng dự báo? | Load test, p95/p99, quota baseline |
| Phát hành | Deploy an toàn và rollback thực hiện được? | CI/CD, artifact digest, canary drill |
| Vận hành | Có on-call, runbook, escalation và incident drill? | Rota, runbook, diễn tập |
| Chi phí | Ai theo dõi và giới hạn chi tiêu? | Budget alerts, billing tags, forecast |

### Đối tượng cần tham gia

- **Application owner:** chấp nhận kết quả nghiệp vụ.
- **Technical lead:** kiến trúc, dependency, tính tương thích.
- **SRE/on-call:** SLO, cảnh báo, incident và recovery.
- **Cloud platform/network:** project, VPC, quota, cluster, kết nối.
- **Security/compliance:** IAM, dữ liệu, chính sách và ngoại lệ.
- **DBA/data owner:** backup, integrity, quyền database.
- **Release manager:** canary, rollback, change window.
- **FinOps:** chi phí, ngân sách và người chịu trách nhiệm.

PRR cần đủ đại diện theo rủi ro, không phải cuộc họp mà mọi ý kiến đều có thể thay thế bằng một checkbox chung.

## 2. Định nghĩa cấp độ rủi ro và cổng GO/NO-GO

Một checklist không có quy tắc xử lý thất bại sẽ tạo cảm giác an toàn giả. Trước khi review, thống nhất severity và quyền phê duyệt.

### Mức phân loại mẫu

| Mức | Ví dụ | Quyết định mặc định |
|---|---|---|
| P0 / Blocker | Không có phương án phục hồi dữ liệu quan trọng; lộ secret; không có owner trực xử lý sự cố | **NO-GO** |
| P1 / Critical | Canary không thể rollback; thiếu cảnh báo lỗi khách hàng; quota không đủ cho peak đã biết | **NO-GO**, trừ ngoại lệ chính thức được lãnh đạo rủi ro phê duyệt |
| P2 / High | Dashboard latency chưa có breakdown theo route; rehearsal DR chưa bao phủ mọi edge case | **CONDITIONAL GO** nếu rủi ro và kế hoạch giảm thiểu được chấp thuận |
| P3 / Improvement | Tài liệu phụ chưa hoàn chỉnh, tối ưu tài nguyên chưa ưu tiên | Có thể **GO** với backlog và deadline |

Đây là **ma trận ví dụ**, không phải tiêu chuẩn bắt buộc của Google Cloud. Hệ thống xử lý thanh toán hoặc dữ liệu nhạy cảm có thể cần ngưỡng chặt hơn; workload ít quan trọng có thể được chấp nhận với mức kiểm soát khác.

### Quy tắc quyết định

- **GO:** tất cả yêu cầu bắt buộc đạt; rủi ro còn lại nằm trong ngưỡng đã phê duyệt.
- **CONDITIONAL GO:** không có blocker; các ngoại lệ có owner, deadline, biện pháp tạm và người chấp nhận rủi ro.
- **NO-GO:** còn blocker, thiếu dữ liệu quan trọng hoặc không xác minh được điều kiện an toàn cốt lõi.

Không viết “PASS” khi chưa có bằng chứng. Dùng các trạng thái: `PASS`, `FAIL`, `NOT TESTED`, `NOT APPLICABLE` và `WAIVED WITH APPROVAL`. Một hạng mục `NOT TESTED` không tương đương `PASS`.

## 3. Bài toán tham chiếu: API Java trên Google Cloud

Giả sử một dịch vụ xử lý đơn hàng có kiến trúc:

~~~mermaid
flowchart LR
  U[Web / Mobile] --> LB[HTTPS Load Balancer / entrypoint]
  LB --> API[Orders API Spring Boot / Cloud Run hoặc GKE]
  API --> DB[(Cloud SQL PostgreSQL)]
  API --> PUB[Pub/Sub topic]
  PUB --> W[Order worker]
  W --> OBJ[(Cloud Storage)]
  API --> SEC[Secret Manager]
  API --> OBS[Logging / Monitoring / Trace]
  W --> OBS
  CICD[CI/CD + Artifact Registry] --> API
  CICD --> W
~~~

Sơ đồ mang tính khái quát. Một service Cloud Run có thể được công bố trực tiếp với authentication và ingress phù hợp; việc thêm load balancer phụ thuộc yêu cầu miền, WAF, TLS, traffic routing và network boundary. Nếu API chạy trên GKE, cần bổ sung cluster/node/pod readiness và policy riêng.

### SLO và dữ liệu mẫu

| Mục tiêu | Giá trị minh họa | Người xác nhận |
|---|---|---|
| Availability SLO | 99,9% request hợp lệ thành công, rolling 30 ngày | Product + SRE |
| Latency SLO | 99% request hợp lệ dưới 400 ms | Product + backend |
| RTO | 1 giờ khi gặp sự cố nghiêm trọng | Business owner |
| RPO | 15 phút cho dữ liệu đơn hàng theo kịch bản DR | Business owner + DBA |
| Peak load | 700 requests/giây, có burst | Performance owner |
| Traffic tăng trưởng | 30% trong sáu tháng | Product/FinOps |

Tất cả số trên là **giả định để thực hành**. RTO/RPO/SLO phải dựa vào nhu cầu thật; chúng không tự được bảo đảm vì Cloud SQL hoặc Cloud Run có SLA riêng.

## 4. Giai đoạn chuẩn bị: inventory và boundary

Trước PRR, có một nguồn sự thật thống nhất về workload:

- Project/folder/organization và billing account.
- Environment: production/staging/DR.
- Regions, zones, VPC, subnets, load balancers và DNS.
- Compute: Cloud Run service, GKE deployments hoặc Compute Engine instances.
- Data: Cloud SQL, Firestore/Spanner, Cloud Storage, BigQuery, caches.
- Integration: Pub/Sub, Cloud Tasks, external APIs, hybrid connectivity.
- Service account, identity providers và secrets.
- Artifact registry, image digests, CI/CD pipeline và IaC repository.
- Ownership, on-call, compliance, service criticality và release window.

### Dependency graph

~~~mermaid
flowchart TD
  A[Orders API] --> B[Cloud SQL]
  A --> C[Payment provider]
  A --> D[Pub/Sub]
  D --> E[Worker]
  E --> F[Cloud Storage]
  A --> G[Secret Manager]
  A --> H[Identity provider]
  B --> I[Backups / PITR]
  A --> J[Monitoring / Alerts]
  E --> J
~~~

Đánh dấu **required**, **degraded mode** và **optional**. Nếu Payment provider không hoạt động, API có thể từ chối tạo đơn hoặc xếp hàng chờ; phản ứng đó phải được product owner chấp nhận. Không thử nghiệm resilience bằng cách làm hỏng hệ thống production không có kế hoạch.

### Sản phẩm đầu ra tối thiểu

| Artifact | Nội dung | Owner |
|---|---|---|
| Service catalog | ID, criticality, team và escalation | Application owner |
| Architecture | Diagrams, data flows, failure domains | Architect |
| Dependency register | API, DB, queue, identity, external | Tech lead |
| Security review | IAM, secrets, network, data classification | Security |
| SLO spec | SLI, goal, error budget, data source | Product + SRE |
| Runbook | Diagnose, mitigate, rollback, escalate | On-call |
| DR plan | RPO/RTO, backup/restore/failover | DBA + SRE |
| Test report | Load, resilience, security, functional | QA/Performance |
| Release plan | Canary, metrics gates, rollback | Release manager |
| Cost model | Budget, SKU, owner, forecast | FinOps |

## 5. Landing zone, organization và project governance

Một workload có thể chạy kỹ thuật tốt nhưng sai governance nếu được đặt trong project không có billing owner, không có policy, hoặc ai cũng có Owner.

### Kiểm tra organization/project

- Project ID được quản lý theo quy ước và thuộc đúng folder.
- Billing account được gắn và có người nhận thông báo chi phí.
- API được bật theo nhu cầu, không bật tùy tiện.
- Organization policies đã được kiểm tra về external IP, service account keys, allowed locations và resource restrictions.
- Labels/tags phục vụ ownership, environment, cost center và policy.
- Quota/limits và quota increase plan phù hợp peak.
- Cloud Audit Logs, log routing/retention và quyền truy cập audit phù hợp.
- IaC/state được bảo vệ và quy trình thay đổi được ghi nhận.

### Phân tách môi trường

Production và non-production cần tách bằng project, quyền, dữ liệu và secrets theo yêu cầu bảo mật. Không cho thử nghiệm staging dùng chung database production chỉ vì “tiện kiểm chứng”. Nếu dùng Shared VPC, xác định host project/service project, trách nhiệm network và IAM rõ ràng.

### Bằng chứng

Ghi lại project/folder ID, policy constraints quan trọng, người phê duyệt ngoại lệ và ngày kiểm tra. Không copy toàn bộ IAM policy có danh tính cá nhân vào tài liệu công khai.

## 6. IAM và danh tính workload

**Least privilege** là nguyên tắc: service chỉ nhận những quyền cần để thực hiện công việc; deployer, runtime và người trực không nên dùng chung một danh tính có quyền rộng.

| Danh tính | Quyền gợi ý theo vai trò | Điều không nên làm |
|---|---|---|
| Runtime Orders API | Đọc đúng secret, kết nối dịch vụ cần thiết | Project Editor/Owner |
| Runtime Worker | Subscribe/publish topic cụ thể, ghi bucket được phân quyền | Storage Admin trên toàn tổ chức |
| CI/CD deployer | Deploy service và actAs đúng runtime service account | Dùng user account cá nhân trong pipeline |
| SRE on-call | View logs/metrics, quyền mitigations giới hạn | Service account key dùng chung |
| Security auditor | Đọc policies và audit logs theo phạm vi | Quyền quản trị thay đổi nếu không cần |
| DBA | Quản lý instance/database theo trách nhiệm | Quyền rộng tới mọi project |

### Checklist danh tính

1. Service account riêng cho workload, không dùng default service account có quyền lịch sử rộng.
2. IAM bindings ở scope hẹp nhất có thể: resource hoặc project phù hợp.
3. Phân biệt quyền **deploy** với quyền **invoke** và quyền **runtime**.
4. Dùng Workload Identity Federation cho GKE/external CI khi phù hợp.
5. Tránh service account JSON keys dài hạn; không đưa key vào image hoặc repository.
6. Xác định đường cấp và thu hồi quyền khẩn cấp (break-glass) có audit.
7. Định kỳ kiểm tra quyền không sử dụng và principal không còn hoạt động.
8. IAM Conditions hoặc policy boundaries khi phù hợp.

**Network access không thay cho authorization.** API nằm trong VPC vẫn cần xác thực caller; kết nối được Cloud SQL bằng TCP không có nghĩa database login có quyền đọc mọi bảng.

## 7. Network, ingress, egress và TLS

### Những câu hỏi bắt buộc

- API cần public Internet hay chỉ internal VPC/hybrid?
- Có domain, TLS certificate, DNS ownership và renewal monitoring?
- Dùng external/internal load balancer, Cloud Armor, IAP hoặc Private Service Connect theo yêu cầu nào?
- Firewall rules có nguyên tắc least privilege và chiều egress không?
- Cloud NAT, Direct VPC egress/connector, proxy và Cloud SQL private IP có đường đi đúng?
- Có overlapping CIDR, route đến on-prem hoặc vendor IP allowlist?
- Có kiểm thử IPv4/IPv6 khi sản phẩm và client dùng?
- Google APIs cần Private Google Access hay endpoint được hỗ trợ nào?
- Các ingress/egress paths có log, metrics và owner?

### Bài thử kết nối phân biệt lớp lỗi

| Lớp | Cách kiểm tra | Tín hiệu hỏng |
|---|---|---|
| DNS | Resolve FQDN từ đúng nguồn | NXDOMAIN, trả IP sai, TTL cũ |
| Routing | Connectivity Tests, route table, flow logs | Unreachable hoặc asymmetric path |
| Firewall | Rule evaluation và deny logs | TCP timeout hoặc reset |
| TLS | Certificate chain, hostname, expiry, protocol | Handshake error |
| Identity | OIDC/mTLS/API auth, IAM | 401/403 |
| Application | Health/business endpoint | 5xx, timeout, sai dữ liệu |

Không dùng `curl -k` làm kết quả kiểm chứng TLS; nó bỏ qua certificate validation. Không mở rộng firewall tới `0.0.0.0/0` chỉ để PRR qua một test.

### Readiness của kết nối Cloud SQL

- Chọn private IP/connector/proxy theo kiến trúc.
- Kết nối từ đúng runtime service account và subnet.
- Kiểm tra DB user/role, TLS, connection pool và query timeout.
- Đánh giá pool size nhân với số instance tối đa của Cloud Run/GKE, không chỉ pool size trên một instance.
- Thử restart/failover theo kịch bản và xác định hành vi retry.

## 8. Chọn compute và kiểm tra failure behavior

### Cloud Run

Cloud Run tự quản lý hạ tầng serverless, nhưng ứng dụng phải cấu hình đúng:

| Kiểm tra | Ý nghĩa |
|---|---|
| CPU/memory | Đủ cho startup, GC, request peak |
| Concurrency | Số request/instance mà Java server xử lý ổn định |
| Min instances | Giảm cold starts nếu latency yêu cầu; có chi phí |
| Max instances | Giới hạn autoscaling/cost nhưng có thể làm giảm capacity |
| Timeout | Phù hợp SLO, dependency, client retry |
| Startup/liveness probes | Ứng dụng khởi động và phục hồi đúng |
| SIGTERM/shutdown | Hoàn thành request, release resources khi có thể |
| Ingress/auth | Không mở public nếu không có nhu cầu |
| Traffic splitting | Cho phép canary và rollback revision |
| Runtime identity | Service account đúng, không dùng key |

Tài liệu Cloud Run ghi rằng min instances được giữ sẵn để giảm cold start nhưng có thể bị khởi động lại và không đảm bảo không bao giờ giảm dưới mục tiêu trong mọi sự cố. Không coi cấu hình min instances là thay thế multi-region DR hoặc load test.

**Concurrency cần benchmark.** Ứng dụng Java có thread pool, connection pool và memory limit riêng; tăng concurrency có thể giảm chi phí hoặc gây OOM/p95 xấu. Không copy một giá trị cố định cho tất cả service.

### GKE Standard hoặc Autopilot

Kiểm tra:

- Cluster mode/version/release channel và kế hoạch upgrade.
- Node pools hoặc Autopilot compute classes/requests, regional/zone placement.
- Deployment replicas và readiness/liveness/startup probes.
- PodDisruptionBudget (PDB) cho workload nhiều replica cần chịu voluntary disruption.
- Requests/limits, Horizontal Pod Autoscaler hoặc cách scale phù hợp.
- Pod scheduling, topology spread và anti-affinity khi cần HA.
- Graceful termination, terminationGracePeriodSeconds và preStop nếu phù hợp.
- Persistent volumes/stateful sets, backup và DR.
- NetworkPolicy, workload identity, secrets và image policies.
- DaemonSet/sidecar/logging overhead, quota và capacity.
- GKE upgrade, maintenance windows và lịch bảo trì.

PDB chủ yếu kiểm soát **voluntary disruptions** như eviction trong maintenance, không bảo vệ tuyệt đối trước node failure hoặc lỗi region. Readiness probe giúp hệ thống biết Pod có thể nhận traffic; liveness probe không nên kiểm tra mọi external dependency theo cách làm tất cả Pod restart khi một database bị lỗi.

### Compute Engine

Kiểm tra:

- Managed Instance Groups khi cần autoscaling và self-healing.
- Health checks và khả năng restart/recreate.
- Shielded VM, OS patching và image baseline.
- VM service account, metadata, firewall, disk encryption.
- Persistent disk snapshots/backup, app state và graceful shutdown.
- Multi-zone design nếu SLO yêu cầu.
- Instance templates bất biến, rolling updates và rollback.

Máy ảo chạy ổn định trong staging không chứng minh đủ capacity khi một zone chết hoặc khi deploy đồng loạt.

## 9. Java/Spring Boot: startup, readiness, liveness và shutdown

Một API Java cần phân biệt **process còn sống** với **dịch vụ sẵn sàng nhận traffic**. Ví dụ Spring Boot dùng Actuator health probes.

### Cấu hình Actuator mẫu

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,prometheus
  endpoint:
    health:
      probes:
        enabled: true
      show-details: never
      add-additional-paths: true
server:
  shutdown: graceful
spring:
  lifecycle:
    timeout-per-shutdown-phase: 25s
~~~

Cấu hình này chỉ minh họa các property Spring Boot ở phiên bản hỗ trợ. Cần dependency `spring-boot-starter-actuator`; Prometheus endpoint cần registry tương ứng và bảo vệ khỏi public exposure khi cần. Việc đặt `exposure.include` rộng có thể khiến endpoint bị phơi nếu network/auth không bảo vệ. Điều chỉnh theo framework version và deployment target.

Các endpoint thường dùng:

- `/actuator/health/liveness`
- `/actuator/health/readiness`

Với `add-additional-paths`, Spring Boot có thể cung cấp `/livez` và `/readyz` trên main server port theo phiên bản/cấu hình. **Kiểm tra endpoint thật** trước khi đưa vào load balancer hoặc Kubernetes probes.

### Readiness probe trên GKE

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: orders-api
spec:
  replicas: 3
  selector:
    matchLabels:
      app: orders-api
  template:
    metadata:
      labels:
        app: orders-api
    spec:
      terminationGracePeriodSeconds: 30
      containers:
        - name: api
          image: REGION-docker.pkg.dev/PROJECT/REPO/orders-api@sha256:IMAGE_DIGEST
          ports:
            - containerPort: 8080
          startupProbe:
            httpGet:
              path: /actuator/health/liveness
              port: 8080
            periodSeconds: 5
            failureThreshold: 24
          readinessProbe:
            httpGet:
              path: /actuator/health/readiness
              port: 8080
            periodSeconds: 5
            failureThreshold: 3
          livenessProbe:
            httpGet:
              path: /actuator/health/liveness
              port: 8080
            periodSeconds: 10
            failureThreshold: 3
          resources:
            requests:
              cpu: "500m"
              memory: "512Mi"
            limits:
              memory: "1Gi"
~~~

Đây là **fragment thực hành cần chỉnh sửa** theo image, CPU/memory, health semantics và version của ứng dụng. Trong Kubernetes, `terminationGracePeriodSeconds` là thuộc tính của **Pod spec**; ví dụ đặt nó tại `spec.template.spec` (cùng cấp với `containers`), không nằm trong container. Tránh dùng manifest mẫu trực tiếp cho production nếu chưa qua schema validation.

Một liveness probe gọi dependency ngoài có thể tạo restart storm khi mạng hoặc database lỗi. Thiết kế liveness chủ yếu phản ánh trạng thái tiến trình, còn readiness phản ánh khả năng phục vụ; khi cần quyết định dependency ảnh hưởng readiness, phải tránh loại toàn bộ replica chỉ vì một sự cố chung.

### Graceful shutdown

- Dừng nhận request mới.
- Hoàn thành các request/transaction đang chạy trong giới hạn.
- Flush logging/metrics/traces khi phù hợp.
- Đóng JDBC pool/HTTP client an toàn.
- Worker trả ack cho message **sau khi** hoàn thành xử lý được xác nhận.
- Tôn trọng timeout/termination window của runtime.

Thử shutdown trong staging bằng rolling restart hoặc scale-down có kiểm soát; kiểm tra retry/idempotency và duplicate message thay vì chỉ quan sát container đã dừng.

## 10. Dữ liệu: HA, backup, PITR và restore không phải một thứ

### Cloud SQL

| Khả năng | Mục đích | Không thay thế |
|---|---|---|
| High availability | Phục hồi từ một số lỗi zone/instance | Backup/restore hoặc DR region |
| Automated backups | Tạo điểm khôi phục theo lịch/chính sách | Continuous replication |
| Point-in-time recovery (PITR) | Phục hồi tới thời điểm trong khoảng lưu giữ | Cơ chế phòng mọi lỗi bảo mật |
| Read replica | Scale reads, tùy thiết kế có thể dùng DR | Backup, primary HA hoặc zero-lag guarantee |
| Cross-region replica/backup | Hỗ trợ kịch bản DR theo khả năng sản phẩm | Runbook failover/failback đã kiểm thử |

Cloud SQL HA giúp ứng phó với sự cố được hỗ trợ nhưng không tự cung cấp DR cho mọi lỗi vùng hoặc ransomware. Với PostgreSQL, xác minh backups, PITR, retention và quyền khôi phục, đồng thời **thực hành restore** sang instance thử nghiệm.

### Checklist dữ liệu

1. RPO/RTO được business owner phê duyệt.
2. Dung lượng dữ liệu, tốc độ tăng và transaction volume đã đo.
3. Backup policy/PITR được bật khi cần, với retention phù hợp.
4. Backup và khóa mã hóa có khả năng dùng được khi recovery.
5. Thử restore từ bản sao thực và kiểm tra dữ liệu sau restore.
6. DB roles, schema migration, extensions, sequence và connection string được kiểm tra.
7. Có kế hoạch khi database bị xóa nhầm, corruption hoặc khóa KMS mất quyền.
8. Data migration/cutover có kiểm chứng consistency, tránh dual-write không có chiến lược.
9. Các dịch vụ khác như Cloud Storage, Firestore, Spanner, Bigtable có chính sách backup/versioning phù hợp riêng.
10. Không coi replication là backup, vì sai/xóa dữ liệu có thể được replicate sang bản khác.

### Pub/Sub, Cloud Tasks và xử lý async

- Subscriber có ack/nack, retry và dead-letter policy.
- Consumer idempotent vì có thể nhận message lặp.
- Đo queue depth, oldest unacked age, processing latency.
- Payload schema được version hóa và backward compatible.
- Xác định ordering requirements và giới hạn subscription.
- Có recovery khi worker không chạy hoặc downstream hỏng.
- Không ack trước khi xử lý thành công rồi kỳ vọng Pub/Sub tự đảm bảo nghiệp vụ.

## 11. SLI, SLO, error budget và cảnh báo

Một dashboard CPU không trực tiếp trả lời người dùng có nhận được dịch vụ tốt hay không.

### Định nghĩa SLI

Ví dụ Orders API:

~~~text
Availability SLI = successful eligible requests / total eligible requests

Latency SLI = requests below agreed latency threshold
              / total eligible requests
~~~

**Eligibility** phải được định nghĩa rõ: có tính 4xx do client không, có loại health probes không, timeout được ghi nhận thế nào. Với SLO theo request, error budget là phần request không tốt được phép trong compliance period.

Nếu SLO availability là 99,9%, phần lỗi cho phép theo tỷ lệ là 0,1%. Không tự suy rằng 0,1% tương đương một số phút downtime cố định khi traffic biến động.

### Một dashboard production tối thiểu

| Dashboard/widget | Phục vụ câu hỏi |
|---|---|
| Request rate, errors, latency | Hệ thống đang phục vụ bao nhiêu người và chất lượng ra sao? |
| SLO compliance/error budget | Dịch vụ còn trong mục tiêu không? |
| Per-route p95/p99 | Endpoint nào suy giảm? |
| CPU/memory/instance count | Có đang nghẽn hoặc scale bất thường? |
| DB connections/CPU/replication/locks | Dependency data có vấn đề gì? |
| Pub/Sub backlog/retries/dead-letter | Async pipeline có đang tích tụ? |
| External dependency errors | Lỗi do nội bộ hay vendor? |
| Deployment/incident markers | Sự cố bắt đầu sau thay đổi nào? |

### Alerting

Nên có:

- Alert **customer-impacting**: error rate, SLO burn rate, latency, availability.
- Alert **capacity**: quota/saturation, DB storage, connection pool, queue backlog.
- Alert **integrity**: backup thất bại, job data pipeline kẹt, số dữ liệu lệch.
- Alert **security**: credential misuse, bất thường audit theo chính sách.
- Alert **operational**: không có telemetry hoặc mất heartbeat ở các dịch vụ quan trọng.

Mỗi alert có severity, owner, notification channel và runbook. Thử kênh cảnh báo trước launch; một policy tồn tại nhưng gửi tới mailbox không ai đọc là **FAIL**.

### Synthetic monitoring

Uptime checks có thể kiểm chứng endpoint công khai hoặc private theo khả năng sản phẩm, nhưng không thay thế transaction-level probe. Với API yêu cầu auth, thiết kế synthetic test account có scope hẹp, không dùng token production trong cấu hình công khai.

## 12. Logging, tracing, audit và dữ liệu nhạy cảm

Ứng dụng Java nên ghi structured logs để lọc theo service, event, route, status và trace context.

~~~json
{
  "severity": "ERROR",
  "service": "orders-api",
  "event": "order.create.failed",
  "route": "/v1/orders",
  "error_type": "DATABASE_TIMEOUT",
  "duration_ms": 870,
  "correlation_id": "synthetic-test-abc"
}
~~~

Ví dụ cố ý không chứa email, mã đơn hàng, bearer token hay payload khách hàng.

### Trace context

- Gắn trace ID và span ID từ context hiện hành.
- Propagate W3C `traceparent` qua HTTP/gRPC khi framework hỗ trợ.
- Nếu logs gửi qua stdout Cloud Run, các field đặc biệt `logging.googleapis.com/trace` và `logging.googleapis.com/spanId` phải có format phù hợp để Cloud Logging liên kết.
- Trace chỉ hiển thị đầy đủ khi span được tạo, sampled/export và ingest; log có trace ID không đảm bảo trace tồn tại.
- Theo dõi OTel Collector/exporter errors, sampling và phí ingest.

### Retention và bảo mật

- Log buckets ở location/retention phù hợp.
- IAM/log views giới hạn người xem dữ liệu.
- Audit logs không bị vô hiệu hóa ngoài chính sách.
- Exclusions tránh làm mất log điều tra sự cố.
- Có quy trình phản ứng khi secret hoặc PII lọt vào log.
- Không đưa request ID, user ID hoặc raw URL làm metric labels cardinality cao.

## 13. CI/CD, IaC và supply-chain readiness

### Pipeline phát hành mẫu

~~~mermaid
flowchart LR
  A[Commit / PR] --> B[Static checks + unit tests]
  B --> C[Dependency + image scan]
  C --> D[Build immutable artifact]
  D --> E[Sign / attest / publish artifact]
  E --> F[Deploy staging]
  F --> G[Integration + load + security tests]
  G --> H[Change approval]
  H --> I[Production canary]
  I --> J{SLO/error gate}
  J -->|Pass| K[Rollout tăng dần]
  J -->|Fail| L[Rollback]
~~~

Không bắt buộc mọi tổ chức dùng chính công cụ trong sơ đồ, nhưng **bằng chứng build từ source đáng tin cậy, kiểm thử và khả năng rollback** cần rõ ràng.

### Checklist

- Artifact/image được tham chiếu bằng digest hoặc immutable version, không chỉ `latest`.
- CI có tests, SCA/dependency scan và secret scanning.
- Build account, deploy account và runtime account có phạm vi riêng.
- IaC (Terraform/GitOps) có review và kiểm tra drift.
- Secrets được cấp qua Secret Manager hoặc cơ chế quản lý bí mật phù hợp; không commit vào Git.
- Database migrations tương thích version khi canary chạy song song hai revision.
- Deployment scripts an toàn khi chạy lại/idempotent.
- Có plan rollback image/config và xử lý dữ liệu sau schema migration.
- Tất cả thay đổi production có audit trail và owner phê duyệt.

### Rolling update không đủ

Nếu release mới đổi schema database theo cách bản cũ không đọc được, rollback image có thể vẫn thất bại. Dùng **expand–migrate–contract** hoặc chiến lược migration tương thích hai version để canary/rollback an toàn. Xác định điểm không thể rollback sau khi dữ liệu đã được ghi theo schema mới.

## 14. Performance, capacity và quota

### Load testing phải đại diện thực tế

Ghi rõ:

- Lượng requests/giây, phân bố endpoint, payload size.
- Tỷ lệ read/write và kích thước data.
- Concurrency và connection pool behavior.
- Peak/burst, ramp-up, soak test và cooldown.
- Dependencies production-like hoặc stub có giới hạn rõ.
- Latency p50/p95/p99, CPU, memory, GC pauses, DB locks, error rate.
- Dữ liệu đầu vào và vùng mạng tạo traffic.
- SLO và điều kiện dừng test.

Không dùng kết quả test chỉ vào `/health` để kết luận API chịu được 700 requests/giây.

### Capacity trước ngày mở traffic

| Lớp | Kiểm tra |
|---|---|
| Cloud Run | Min/max instances, concurrency, CPU, memory, quotas |
| GKE | Node/pod resources, autoscaling, image pull, topology |
| Compute Engine | Instance group capacity, quota, regional availability |
| Cloud SQL | CPU, RAM, connections, storage, IOPS, read replicas |
| Pub/Sub | Throughput/quota, backlog, subscriber capacity |
| Cloud Storage | Request rate, object layout, transfer costs |
| Network | Load balancer quotas, Cloud NAT ports, egress, DNS |
| Monitoring | Metric cardinality, log ingest quotas, alert delivery |

Nếu workload có 200 instances và mỗi instance tạo pool 20 kết nối DB, ngưỡng lý thuyết có thể lên tới **4.000 kết nối** chưa tính admin/worker/replica. Đây là tính toán illustrative, không phải dự đoán kết nối thực tế; xác định cap và proxy/pooling theo giới hạn DB.

### Kiểm thử suy giảm

- Một dependency trả 5xx/timeout.
- Database read replica bị chậm.
- Pub/Sub consumer xử lý chậm.
- Một instance/pod được restart trong lúc có traffic.
- DNS hoặc external API chậm.
- Quota/autoscaling chạm giới hạn.

Các thí nghiệm failure phải thực hiện trong sandbox/staging và có rollback; không gây gián đoạn production để thu bằng chứng PRR khi chưa được phê duyệt.

## 15. Backup, disaster recovery và business continuity

**High availability** giải quyết một số lỗi hạ tầng; **backup/PITR** giúp phục hồi dữ liệu; **disaster recovery** giải quyết các sự cố quy mô lớn theo RTO/RPO. Ba nhóm không thay thế nhau.

### Kịch bản phải xem

1. Deploy sai làm tăng 5xx.
2. Zone mất khả dụng.
3. Region bị ảnh hưởng nghiêm trọng.
4. Database bị xóa/corruption.
5. Secret Manager access hoặc CMEK key bị vô hiệu hóa.
6. Ransomware/credential compromise.
7. External payment provider mất dịch vụ.
8. Mất quyền truy cập logging/monitoring hoặc network.
9. IaC thay đổi nhầm firewall/IAM.
10. Người trực chính không thể phản hồi incident.

### Recovery evidence

- Có bản backup gần đây trong thời hạn retention.
- Có bản kiểm thử restore **đã hoàn thành**, không chỉ “backup succeeded”.
- Thời gian restore thực đo được phù hợp RTO hoặc có biện pháp thay thế.
- Data loss trong thử nghiệm được đối chiếu với RPO.
- Identity/IAM/KMS/secret và network dependencies cũng được phục hồi.
- Có tài liệu failover/failback và communication plan.
- DR drill được lên lịch lại định kỳ.

### Không tự động suy từ SLA

SLA của Cloud SQL, GKE hay Cloud Run có phạm vi/điều kiện riêng. SLO end-to-end còn phụ thuộc app code, database, identity, DNS, network và các bên thứ ba. PRR đánh giá **toàn đường giao dịch**, không nhân hoặc cộng các con số SLA một cách tùy tiện.

## 16. Bảo mật production: defense in depth

### Các kiểm soát thường cần

- Threat modeling cho luồng dữ liệu và trust boundaries.
- IAM least privilege; review quyền quá rộng và service account keys.
- TLS/mTLS khi cần, kiểm tra certificate expiry và private CA.
- Network segmentation, firewall, ingress/egress restrictions.
- Cloud Armor hoặc WAF theo threat model của dịch vụ public.
- Secret Manager, rotation và bảo vệ database credentials.
- Encryption at rest, CMEK khi tổ chức yêu cầu; runbook key rotation/recovery.
- Vulnerability scanning, patch policy, base image và dependency updates.
- Artifact provenance/signing/attestations và image admission policy nếu áp dụng.
- Cloud Audit Logs, threat detection và incident escalation.
- Data classification, residency, retention, DLP và backup isolation.
- Negative tests: user không có quyền thực sự nhận 403; service không thể đọc bucket ngoài scope.

### Câu hỏi kiểm tra thật

- Nếu service account bị lộ token, principal đó có thể xóa backup hay KMS key không?
- Nếu một container bị chiếm, network egress có cho phép gửi dữ liệu tới mọi Internet host không?
- Nếu CI token hết hạn, pipeline có fail closed và cảnh báo không?
- Nếu certificate hết hạn, ai được page trước khi khách hàng bị ảnh hưởng?
- Nếu key CMEK bị disable, có runbook khôi phục an toàn không?

Không cần trả lời “có” cho mọi công cụ Google Cloud; cần chứng minh **rủi ro đã được xử lý** với kiểm soát thích hợp.

## 17. FinOps và quota readiness

Một workload có thể bị outage vì vượt quota hoặc vì billing bị vô hiệu hóa. Ngược lại, một autoscaler không giới hạn theo workload có thể gây chi phí bất thường.

### Những mục cần xem

- Budget và alerts theo project/environment/cost center.
- Billing export để phân tích SKU và unit cost.
- Owner nhận thông báo và có quyền xử lý.
- Quota headroom cho peak và failover.
- Cost of HA, warm standby, min instances, logs và DR.
- Labels/tags và cách phân bổ shared costs.
- Storage lifecycle/retention, data transfer egress.
- Thay đổi SKU khi scale/region deployment.
- Quy tắc dọn test resources, old revisions, unattached disks hoặc idle IPs.

**Budget alerts không tự động chặn chi tiêu**. Nếu cần hard guardrails, thiết kế quotas/limits và policy có xét tác động reliability; không tự đặt max instances quá thấp làm hệ thống từ chối traffic giờ cao điểm.

### Unit economics

Ví dụ:

~~~text
Cost per 1,000 successful requests
  = eligible monthly operating cost
    / successful requests in month
    × 1,000
~~~

Tính cả các khoản phân bổ hợp lý: compute, database, networking, logging và storage, không chỉ Cloud Run CPU. Khi request rate tăng, so sánh cost/transaction và p95 latency cùng lúc.

## 18. On-call, incident response và runbooks

### Bắt buộc có người chịu trách nhiệm

Một service production cần:

- Primary và secondary on-call hoặc escalation phù hợp.
- Pager/notification channel được thử.
- Severity definitions (SEV1/SEV2...) và incident commander.
- Runbook triage, mitigation, rollback, escalation.
- SLO/status dashboard và link tới Logs Explorer/Trace Explorer.
- Quản lý change freeze, incident bridge và stakeholder communication.
- Retrospective/postmortem không đổ lỗi cá nhân và backlog cải tiến.

### Runbook mẫu: tỷ lệ lỗi Orders API tăng

~~~text
Trigger: Availability SLO fast-burn alert / HTTP 5xx tăng
Owner: orders-oncall
First 5 minutes:
  1. Acknowledge alert; xem dashboard lỗi theo route/revision.
  2. Kiểm tra deployment gần nhất và Cloud SQL/PubSub health.
  3. Xác định customer impact, mở incident nếu đạt severity.
Mitigation:
  4. Nếu lỗi do revision mới, rollback traffic theo runbook.
  5. Nếu DB quá tải, giảm pressure bằng rate limiting/queue.
  6. Nếu third-party hỏng, bật degraded mode đã phê duyệt.
Verification:
  7. Tỷ lệ lỗi, p95 latency và backlog phục hồi.
  8. Đối soát các giao dịch thất bại hoặc retry.
Communication:
  9. Thông báo định kỳ và ghi timeline/owner.
After incident:
  10. Review root causes, test gaps và follow-up actions.
~~~

Không viết lệnh rollback hoặc sửa dữ liệu production trong runbook như một “one-click” không kiểm soát. Xác định người được quyền thao tác, điều kiện an toàn và hậu quả.

## 19. Các bằng chứng kiểm tra bằng gcloud (read-only)

Dưới đây là bộ lệnh **chỉ xem cấu hình** cho một workload mẫu. Thay `PROJECT_ID`, `REGION`, `SERVICE` và các tên khác. Các lệnh là starting point; không thay thế toàn bộ PRR.

### Xác nhận project và API

~~~bash
gcloud config get-value project
gcloud projects describe PROJECT_ID
gcloud services list --enabled --project=PROJECT_ID
~~~

### Cloud Run

~~~bash
gcloud run services describe SERVICE \
  --region=REGION \
  --project=PROJECT_ID \
  --format=yaml

gcloud run revisions list \
  --service=SERVICE \
  --region=REGION \
  --project=PROJECT_ID
~~~

Xem ingress, runtime identity, min/max instances, concurrency, resource limits, traffic split và revision configuration. Cần kiểm tra effective config vì CLI flags có thể thay đổi giữa các phiên bản.

### GKE

~~~bash
gcloud container clusters list --project=PROJECT_ID
gcloud container clusters describe CLUSTER \
  --location=LOCATION --project=PROJECT_ID
kubectl get deployments,pods,pdb -A
kubectl get hpa -A
kubectl describe deployment orders-api -n orders
~~~

Lệnh `kubectl` cần kubeconfig/cluster context đúng. Xác nhận context trước khi chạy; các lệnh trên là read-only nhưng có thể hiển thị thông tin nội bộ và cần quyền phù hợp.

### Cloud SQL

~~~bash
gcloud sql instances list --project=PROJECT_ID
gcloud sql instances describe SQL_INSTANCE --project=PROJECT_ID
gcloud sql backups list --instance=SQL_INSTANCE --project=PROJECT_ID
~~~

Kết quả hiện có backup **không** đồng nghĩa đã restore thành công. Cần evidence từ một restore drill độc lập.

### IAM và network

~~~bash
gcloud projects get-iam-policy PROJECT_ID --format=json
gcloud compute networks list --project=PROJECT_ID
gcloud compute firewall-rules list --project=PROJECT_ID
~~~

Không copy output chứa principal, emails hoặc network topology vào tài liệu ngoài phạm vi được phép. Một IAM policy ở project không cho biết mọi permission hiệu lực từ tổ chức/folder, IAM Conditions và resource-specific bindings; security review phải xét effective access.

### Alerting và budgets

Cloud Monitoring/Cloud Billing Console có thể dùng để kiểm tra dashboard, SLO, notification channels, uptime checks và budget alerts. Nếu dùng API/CLI, đối chiếu resource names/region và quyền thật; đừng coi một lệnh list trả về bản ghi là bằng chứng alert đã gửi thành công.

## 20. Thực hành PRR cho Orders API Java

### Bước 1: Khởi động review

Tạo service catalog record: mục tiêu, criticality, owners, region, dependencies, ngày launch và ticket PRR. Chọn scope: API, Cloud SQL, Pub/Sub, Cloud Storage và identity/monitoring.

### Bước 2: Xác minh entry criteria

- Kiến trúc và data flows đã phê duyệt.
- Unit/integration tests đạt.
- Security threat model có owner.
- SLO và RTO/RPO có xác nhận.
- Staging gần tương đương production ở các yếu tố ảnh hưởng hiệu năng.
- Có quyền đọc cấu hình và bằng chứng mà không làm thay đổi production.

### Bước 3: Thu cấu hình

Dùng lệnh phần 19 và Console để xem runtime identity, ingress, concurrency, quotas, DB HA/backup/PITR, logging và alerting. Mọi chứng cứ phải ghi **thời điểm, project, service, version và owner**.

### Bước 4: Thực hiện test matrix

| Test | Điều kiện PASS | Evidence |
|---|---|---|
| Functional happy path | Tạo/đọc đơn thành công | Test report |
| Unauthorized caller | Bị từ chối đúng cách | 401/403 và audit log |
| Synthetic endpoint | Phát hiện được lỗi mô phỏng | Uptime check result |
| 5xx alert | Notification đến đúng on-call | Alert test |
| Load peak | p95, 5xx, saturation trong giới hạn | Load test |
| Deployment canary | Có thể tăng traffic và rollback | Pipeline records |
| Kill one Pod/instance | Không gián đoạn quá SLO | Disruption test |
| DB restore | Khôi phục được dữ liệu mẫu với RTO/RPO | Restore log/reconciliation |
| Pub/Sub duplicate | Consumer xử lý idempotent | Integration test |
| Dependency timeout | Retry/circuit breaker không gây storm | Fault injection logs |
| Secret access | Đúng service account được phép | IAM/security test |
| Budget alert | Có người nhận và biết xử lý | Billing alert validation |

### Bước 5: Review rủi ro và remediation

Ví dụ giả định:

| Finding | Severity | Owner | Deadline | Trạng thái |
|---|---|---|---|---|
| Chưa từng restore backup Cloud SQL | P0 | DBA | Trước launch | FAIL |
| Canary rollback chưa test sau DB schema change | P1 | Backend | Trước launch | FAIL |
| Dashboard không hiển thị latency theo route | P2 | SRE | +7 ngày nếu được waiver | OPEN |
| Old staging artifacts chưa dọn | P3 | Platform | +14 ngày | OPEN |

Trong ví dụ này **quyết định là NO-GO** cho tới khi hai blocker đầu được giải quyết. Không tự đổi thành GO vì “chắc sẽ chạy được”.

### Bước 6: Tái kiểm tra và phê duyệt

Sau remediation, test lại đúng failure mode. Ghi evidence mới, artifact digest, config revision và danh tính người phê duyệt. Quyết định chỉ áp dụng cho release/scope cụ thể; thay đổi lớn sau đó cần review lại.

## 21. Mẫu biên bản PRR có thể tái sử dụng

~~~yaml
review_id: "PRR-orders-api-2026-11"
service:
  id: "orders-api"
  environment: "production"
  project: "PROJECT_ID"
  region: "REGION"
  release: "IMAGE_DIGEST"
owners:
  application: "orders-team"
  oncall: "sre-team"
  security: "security-team"
  data: "dba-team"
objectives:
  availability_slo: "99.9% eligible requests / 30d"
  latency_slo: "99% eligible requests <= 400ms / 30d"
  rto: "60 minutes"
  rpo: "15 minutes"
evidence:
  architecture: "approved-diagram-link"
  load_test: "test-report-link"
  security: "security-review-link"
  restore: "restore-test-link"
  alerts: "pager-test-link"
  rollback: "canary-rollback-log-link"
findings:
  - id: "PRR-001"
    category: "data-recovery"
    severity: "P0"
    status: "FAIL"
    owner: "dba-team"
    action: "Restore rehearsal and data reconciliation"
decision:
  outcome: "NO-GO"
  reason: "P0 restore evidence missing"
  approved_by: []
  reviewed_at: "2026-11-19"
next_review: "after-PRR-001-resolved"
~~~

Đây là **mẫu biên bản**, không phải cấu hình API Google Cloud. Các link là placeholder và các giá trị SLO/RTO/RPO là dữ liệu ví dụ, phải thay bằng số được phê duyệt. Tài liệu evidence có thể nhạy cảm; lưu trong kho có phân quyền.

## 22. Kịch bản canary và rollback ngày go-live

~~~mermaid
flowchart TD
  A[Freeze config / backup snapshot evidence] --> B[Đẩy revision mới không nhận traffic]
  B --> C[Smoke test + security/auth]
  C --> D{PASS?}
  D -->|Không| X[NO-GO / rollback]
  D -->|Có| E[Chuyển 5% traffic]
  E --> F[Quan sát SLO, logs, DB, Pub/Sub]
  F --> G{Gate đạt?}
  G -->|Không| X
  G -->|Có| H[25% -> 50% -> 100% theo approval]
  H --> I[Enhanced monitoring / on-call]
  I --> J{Ổn định trong thời gian đã định?}
  J -->|Không| X
  J -->|Có| K[Go-live accepted + handover]
~~~

Các tỷ lệ 5%/25%/50% chỉ minh họa. Với traffic thấp, tỷ lệ 5% có thể không tạo đủ request để kết luận. Cần kết hợp test chức năng, cửa sổ quan sát, số mẫu, feature flags và rủi ro state/data migration.

### Timeline vận hành mẫu

| Giai đoạn | Hành động | Owner |
|---|---|---|
| Trước T-1 ngày | Kiểm tra backup/restore evidence, IAM, quota, alert channels | DBA + SRE |
| Trước T-2 giờ | Freeze thay đổi ngoài phạm vi, xác nhận incident bridge | Release |
| T0 | Deploy revision với traffic an toàn | DevOps |
| T+15 phút | Kiểm tra synthetic, SLO, DB và log | SRE |
| T+30 phút | Tăng traffic nếu gate đạt | Release + App |
| T+60 phút | Kiểm tra backlog, data integrity và cost anomalies | App + DBA |
| Sau launch | Handover, ghi finding và theo dõi tăng cường | On-call |

Đặt thời gian theo hệ thống thật; không coi timeline trên là SLA go-live.

### Go-live gate

Một gate có thể gồm:

- Error rate không tăng quá mức do SLO đặt.
- p95 latency không suy giảm ngoài ngưỡng chấp nhận.
- Không phát sinh security/audit anomaly mới.
- Database CPU/connections/locks còn headroom.
- Async backlog không tăng liên tục.
- Synthetic transaction thành công.
- Có khả năng rollback image **và** xử lý schema/data.
- On-call thực tế đã nhận bàn giao.

## 23. Sự cố PRR thường gặp

| Triệu chứng | Nguyên nhân phổ biến | Hướng xử lý |
|---|---|---|
| Cloud Run trả 503 dưới tải | Concurrency, max instances, startup hoặc dependency | Load test, tuning, quota |
| API khỏe nhưng transaction thất bại | Health endpoint không đo dependency nghiệp vụ | Synthetic transaction, tracing |
| GKE rollout khiến 100% Pod unavailable | PDB/probes/replicas/scheduling chưa phù hợp | Workload disruption readiness |
| Liveness gây restart storm | Probe phụ thuộc DB bên ngoài | Thiết kế liveness đúng process |
| DB restore quá lâu | Chưa diễn tập, dữ liệu lớn, thiếu quota | Restore test và RTO review |
| Secret bị lộ trong log | Logger ghi headers/body, thiếu masking | Redact, revoke/rotate, incident |
| Canary rollback không sửa được lỗi | Schema migration backward-incompatible | Expand-contract / data recovery |
| Budget vượt nhanh | Min instances/egress/log volume cao | Billing export, budget/cost owner |
| SLO dashboard trống | Sai metric filter hoặc chưa ingest | Test telemetry pipeline |
| Pager không đến đúng nhóm | Channel/rotation/escalation sai | Test notification |
| Cloud SQL hết connections | Pool × instance count quá lớn | Pool cap, connection management |
| DNS/TLS lỗi ở production | Cert/hostname/network khác staging | Preflight FQDN/TLS và canary |
| Worker xử lý message trùng | Không idempotent, ack/retry sai | Idempotency keys và retry policy |
| Không thể failover region | Chỉ có backup, thiếu config/IAM/network DR | Diễn tập end-to-end DR |
| Không có người quyết định rollback | RACI/runbook thiếu | PRR owner và escalation chain |

## 24. Checklist hoàn chỉnh trước production

### Nghiệp vụ và ownership

- [ ] Service catalog, owner và escalation đã xác nhận.
- [ ] Critical user journeys và phụ thuộc đã được liệt kê.
- [ ] SLO, RTO, RPO và compliance obligations được phê duyệt.
- [ ] Có xác nhận GO/NO-GO và exception owner.

### Landing zone và bảo mật

- [ ] Project/folder/billing/policies đúng môi trường.
- [ ] IAM least privilege cho deploy, runtime, ops.
- [ ] Secrets không nằm trong source/image/log.
- [ ] TLS, ingress, egress, IAM auth và DB privileges đã test.
- [ ] Data classification, residency, retention và backup encryption đúng yêu cầu.
- [ ] Audit/security monitoring và incident owner sẵn sàng.

### Compute và dữ liệu

- [ ] Cloud Run/GKE/GCE startup, probes, shutdown và autoscaling đúng.
- [ ] Quota, capacity, region/zone và maintenance được review.
- [ ] DB HA, backups/PITR, connection pool và schema compatibility đạt.
- [ ] Có restore drill thực tế và kết quả đối soát dữ liệu.
- [ ] Messaging retries, dead-letter, idempotency được thử.

### Observability và vận hành

- [ ] Dashboard SLI/SLO, errors, latency, saturation đầy đủ.
- [ ] Alerting policies, notification channels và on-call đã test.
- [ ] Structured logs/traces có thể liên kết request–dependency.
- [ ] Có runbook sự cố và diễn tập rollback/failover.
- [ ] Có owners, escalation, status communication và postmortem process.

### Release, hiệu năng và chi phí

- [ ] Build artifact immutable, scan và provenance phù hợp.
- [ ] CI/CD tests và IaC review/drift control đạt.
- [ ] Load/soak/failure tests đáp ứng SLO theo peak dự báo.
- [ ] Canary/rollout/rollback có gate và người phê duyệt.
- [ ] Cost baseline, budget alert, quota headroom và cost owner rõ.
- [ ] Các blocker được giải quyết; waiver có người chấp nhận rủi ro.

## Câu hỏi ôn tập

1. Một service có HTTP 200 ở `/health` nhưng Cloud SQL không có backup restore test: tại sao chưa production-ready?
2. SLO và SLA khác nhau thế nào, vì sao PRR cần error budget?
3. Liveness probe phụ thuộc database có thể gây ra tác hại nào?
4. Tại sao min instances của Cloud Run không thay thế HA/DR?
5. Với 100 Cloud Run instances và pool 30 connections/instance, nhóm cần kiểm tra giới hạn gì?
6. Bằng chứng nào cho biết một alerting policy thực sự chuyển thông báo tới on-call?
7. Vì sao rollback image không giải quyết được mọi rủi ro sau DB schema migration?
8. Backup, PITR, HA và cross-region DR khác nhau ra sao?
9. Đâu là sự khác nhau giữa `FAIL`, `NOT TESTED` và `WAIVED WITH APPROVAL`?
10. Có cần chạy load test với traffic đại diện cho nghiệp vụ thay vì chỉ endpoint health không?
11. Budget alert có phải hard cap tự động ngừng chi tiêu không?
12. Khi nào một PRR được CONDITIONAL GO thay vì GO hoặc NO-GO?

## Kết luận

Production readiness trên Google Cloud là khả năng **chứng minh workload có thể phục vụ, phát hiện vấn đề, khắc phục, phục hồi và phát hành an toàn**, không chỉ là cấu hình tài nguyên đạt yêu cầu. Một PRR đáng tin cậy kết nối application owner, DBA, Security, SRE, Platform và FinOps quanh SLO, RTO/RPO, risk register và các bằng chứng kiểm chứng.

Với workload Java/Spring Boot trên Cloud Run hoặc GKE, cần đặc biệt chú ý startup, concurrency, readiness/liveness, graceful shutdown, JDBC connection pool, data backup/restore, messaging idempotency và khả năng rollback khi nhiều revision/schema cùng tồn tại. Well-Architected Framework cung cấp nguyên tắc; quyết định **GO/NO-GO** phải dựa vào tình huống, mức rủi ro và bằng chứng thực tế của dịch vụ.

Khi các tiêu chí được chuẩn hóa, có người chịu trách nhiệm, có test và được tái đánh giá sau thay đổi lớn, PRR trở thành một hoạt động vận hành liên tục giúp giảm incident và tăng khả năng phát hành an toàn.

## Tài liệu tham khảo

- [Well-Architected Framework: Operational excellence](https://cloud.google.com/architecture/framework/operational-excellence)
- [Ensure operational readiness and performance using CloudOps](https://cloud.google.com/architecture/framework/operational-excellence/operational-readiness-and-performance-using-cloudops)
- [Well-Architected Framework: Reliability](https://cloud.google.com/architecture/framework/reliability)
- [Well-Architected Framework: Security, privacy and compliance](https://cloud.google.com/architecture/framework/security)
- [Well-Architected Framework: Cost optimization](https://cloud.google.com/architecture/framework/cost-optimization)
- [Cloud Run: General development tips](https://cloud.google.com/run/docs/tips/general)
- [Cloud Run: Configure concurrency](https://cloud.google.com/run/docs/configuring/concurrency)
- [Cloud Run: Configure minimum instances](https://cloud.google.com/run/docs/configuring/min-instances)
- [GKE: Ensure workloads are disruption-ready](https://cloud.google.com/kubernetes-engine/docs/how-to/workload-disruption-readiness)
- [GKE: Manage cluster lifecycle changes](https://cloud.google.com/kubernetes-engine/docs/concepts/managing-clusters)
- [Cloud SQL PostgreSQL: High availability](https://cloud.google.com/sql/docs/postgres/high-availability)
- [Cloud SQL: Configure backups](https://cloud.google.com/sql/docs/postgres/backup-recovery/backups)
- [Cloud Monitoring: Concepts in service monitoring](https://cloud.google.com/stackdriver/docs/solutions/slo-monitoring)
- [Cloud Monitoring: Alerting overview](https://cloud.google.com/monitoring/alerts)
- [Cloud Logging: Structured logging](https://cloud.google.com/logging/docs/structured-logging)
- [Cloud Build: Build provenance](https://cloud.google.com/build/docs/securing-builds/view-build-provenance)
- [Artifact Registry: Vulnerability scanning](https://cloud.google.com/artifact-analysis/docs/on-demand-scanning)
- [Secret Manager: Best practices](https://cloud.google.com/secret-manager/docs/best-practices)
- [Cloud Billing: Budgets and budget alerts](https://cloud.google.com/billing/docs/how-to/budgets)
- [Google SRE Workbook](https://sre.google/workbook/table-of-contents/)

