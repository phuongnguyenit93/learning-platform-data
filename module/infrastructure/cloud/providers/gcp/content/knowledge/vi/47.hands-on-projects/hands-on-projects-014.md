# Dự án tổng hợp từ thiết kế kiến trúc đến bàn giao vận hành

Một dự án Google Cloud không kết thúc ở thời điểm ứng dụng trả về HTTP 200. Hệ thống chỉ thực sự sẵn sàng khi có **yêu cầu được chấp thuận, kiến trúc có lý do lựa chọn, tài nguyên được kiểm soát bằng mã, dữ liệu được bảo vệ, kiểm thử có bằng chứng, quy trình phát hành và rollback, giám sát, runbook và người nhận bàn giao vận hành**.

Bài thực hành tổng hợp này thuộc chương **Dự án thực hành GCP** của module **CLOUD_PROVIDERS_GCP**. Module trang bị kiến thức từ tổ chức project, IAM và VPC đến Compute Engine, GKE, Cloud Run, dịch vụ lưu trữ và cơ sở dữ liệu; qua các tình huống triển khai, người học biết lựa chọn dịch vụ, bảo vệ tài nguyên, tự động hóa phát hành và theo dõi độ tin cậy cùng chi phí. Bài này tập hợp những kỹ năng đó thành một capstone có thể đánh giá theo đầu ra, không chỉ theo danh sách dịch vụ đã bật.

**Đề bài:** Thiết kế, triển khai thử nghiệm, đưa vào vận hành và bàn giao một ứng dụng quản lý đơn hàng nhiều tầng tên **ShopFlow Orders**. Mục tiêu là giữ luồng đặt hàng an toàn và ổn định trên Google Cloud, có khả năng phục hồi dữ liệu, theo dõi chi phí và quy trình xử lý sự cố rõ ràng.

**Quy ước an toàn:** Mọi project ID, tài khoản, IP, tên database, số liệu tải và ngân sách trong bài đều là ví dụ. Các lệnh gcloud/Terraform chỉ chạy trên project sandbox hoặc staging đã được phép, vì nhiều lệnh sẽ tạo tài nguyên có tính phí. Không deploy, xóa hoặc cutover production nếu chưa qua phê duyệt thay đổi.

Sau bài học, bạn có thể:

- Chuyển nhu cầu nghiệp vụ thành SLO, RTO/RPO, tiêu chí nghiệm thu và ma trận truy vết yêu cầu.
- Lập kiến trúc ba tầng Google Cloud với network, identity, data flow và ranh giới tin cậy.
- Lựa chọn Cloud Run, Cloud SQL, Cloud Storage, Pub/Sub, Artifact Registry, Cloud Build và Secret Manager trên cơ sở trade-off.
- Tổ chức project, IAM, VPC, IaC/Terraform và quản lý môi trường staging/production.
- Xây dựng quy trình test, build, scan, deploy, release, canary và rollback.
- Vận hành với Cloud Monitoring/Logging, alerting, backup, PITR, DR và FinOps.
- Chuẩn bị bộ hồ sơ bàn giao, runbook có thể thực thi, RACI và điều kiện Go/No-Go.

## 1. Đầu ra bắt buộc của capstone

Đừng chấm dự án chỉ bằng ảnh chụp Console. Một nhóm hoàn thành bài phải tạo bộ bằng chứng sau:

| Mã | Deliverable | Tiêu chí chấp nhận |
|---|---|---|
| D01 | Project charter và scope | Có business owner, hệ thống hiện tại, giới hạn và giả định |
| D02 | Yêu cầu chức năng/phi chức năng | Có ID, ưu tiên, chỉ tiêu định lượng và chủ sở hữu |
| D03 | Architecture Decision Records (ADR) | Nêu ít nhất hai phương án và lý do chọn/không chọn |
| D04 | Sơ đồ kiến trúc, data flow, trust boundaries | Thể hiện ingress/egress, dịch vụ, dữ liệu và identities |
| D05 | Landing zone và resource register | Project, region, VPC/CIDR, IAM, labels, API, owner |
| D06 | Infrastructure as Code | Terraform plan, state/backend, review và drift policy |
| D07 | Code, image và CI/CD | Test results, image digest, scan, provenance nếu áp dụng |
| D08 | Data protection và security plan | Secrets, backups, PITR, quyền và threat model |
| D09 | Test evidence | Unit/integration/load/security/DR, lỗi và biện pháp |
| D10 | Release/cutover và rollback plan | Go/No-Go, traffic change, data safety và approval |
| D11 | SLO dashboard, alerts và cost report | Có baseline, threshold, notification và budget |
| D12 | Operational handover pack | Runbook, on-call, RACI, inventory, sign-off |

**D01–D12 là tên hồ sơ đầu ra của bài thực hành**, không phải các file đã được tự động tạo. Người học có thể lưu chúng trong hệ thống tài liệu, repository hoặc issue tracker được tổ chức phê duyệt. Mỗi hồ sơ nên có version, người phê duyệt và liên kết với commit/release.

### Các mốc kiểm soát

~~~mermaid
flowchart LR
    A["G0: Scope/BIA"] --> B["G1: ADR + design review"]
    B --> C["G2: IaC + security readiness"]
    C --> D["G3: Staging tests"]
    D --> E["G4: Production Go/No-Go"]
    E --> F["G5: Hypercare + handover"]
~~~

Không được bỏ qua G3/G4 chỉ vì CI build thành công. Trạng thái production-ready dựa trên **bằng chứng tích hợp và khả năng vận hành**, không chỉ tình trạng compilation.

## 2. Bối cảnh nghiệp vụ và phạm vi

ShopFlow có ba nhóm người dùng:

- Người mua đặt hàng và xem trạng thái.
- Nhân viên vận hành xử lý đơn bị lỗi.
- Nhân viên tài chính cần xuất hóa đơn và đối soát.

Luồng nghiệp vụ chủ yếu:

1. Người mua đăng nhập bằng cơ chế identity của ứng dụng.
2. Gửi yêu cầu POST /api/orders, kèm một idempotency key.
3. Backend kiểm tra dữ liệu, ghi đơn hàng cùng transaction vào PostgreSQL.
4. Backend ghi một **outbox event** cùng transaction đó.
5. Worker chuyển outbox event sang Pub/Sub; consumer xử lý tác vụ hậu kiểm/gửi thông báo.
6. Hóa đơn PDF được tạo và lưu trong Cloud Storage; metadata lưu trong database.
7. Người mua đọc được trạng thái mới và nhân viên có thể điều tra lỗi qua trace ID.

### 2.1. In scope

- Frontend web container trên Cloud Run.
- Backend Java/Spring Boot trên Cloud Run.
- Cloud SQL for PostgreSQL qua private networking.
- Secret Manager cho database password hoặc thiết lập IAM database auth đã được đánh giá.
- Cloud Storage cho invoice objects.
- Pub/Sub cho business events và xử lý bất đồng bộ.
- Artifact Registry, Cloud Build và quy trình promote image.
- IAM, VPC, Terraform, Monitoring, Logging, budget/alerts.
- Staging test, một lần release được kiểm soát và bàn giao vận hành.

### 2.2. Out of scope

- Thu thập trực tiếp thông tin thẻ thanh toán và đạt chứng nhận PCI DSS.
- Triển khai active-active đa region với zero RPO.
- Viết lại toàn bộ ứng dụng thành microservices hoặc thay đổi lớn schema cùng cutover.
- Vận hành production dữ liệu cá nhân thật trong môi trường lab.
- Bảo đảm mọi hệ thống khách hàng có đúng SLO từ những con số minh họa.

Để giảm rủi ro, hệ thống thanh toán giả lập hoặc bên thứ ba chỉ dùng sandbox endpoint; không dùng dữ liệu thẻ thật.

## 3. Đưa yêu cầu thành mục tiêu có thể nghiệm thu

Giả định sản phẩm có các yêu cầu sau (chủ sở hữu nghiệp vụ phải xác nhận trước khi thực hiện ngoài lab):

| ID | Yêu cầu | Mục tiêu minh họa | Cách đo |
|---|---|---|---|
| F01 | Tạo đơn hàng | POST tạo một order duy nhất với cùng idempotency key | Functional/API test |
| F02 | Xem đơn | GET chỉ trả đơn mà user có quyền xem | Authz integration test |
| F03 | Phát sự kiện | Event order.created được publish/retry không gây side effect trùng | Outbox/consumer test |
| F04 | Lưu hóa đơn | Object và DB metadata liên kết đúng | E2E storage test |
| N01 | API latency | P95 dưới 500 ms ở mức tải giả định | Load test và traces |
| N02 | Availability | SLO 99,9% trên chu kỳ 30 ngày | SLI good/total requests |
| N03 | Data durability | Đơn đã xác nhận không bị mất âm thầm | Transaction/outbox/recovery tests |
| N04 | RPO | Không quá 15 phút theo kịch bản đã duyệt | Recovery point/drill |
| N05 | RTO | Không quá 2 giờ theo kịch bản đã duyệt | Business restore drill |
| N06 | Bảo mật | Least privilege, no public DB, secret không nằm trong repo/image | IAM/security review |
| N07 | Audit | Có trace ID, release ID và audit trail cho thay đổi quan trọng | Log/trace inspection |
| N08 | Chi phí | Trong ngân sách được duyệt và có cảnh báo | Billing budget report |

### 3.1. SLO và error budget

Với Availability SLO = 99,9% trong 30 ngày:

\[
30 \times 24 \times 60 \times (1-0{,}999)=43{,}2\ \text{phút}
\]

43,2 phút là **minh họa error budget tương đương thời gian** nếu đo availability liên tục; trong thực tế có thể dùng request-based SLI với good/valid requests, nên không nhất thiết quy đổi trực tiếp mọi failure thành số phút.

Ví dụ định nghĩa SLI:

~~~text
SLI_availability = good_requests / eligible_requests

good_requests:
  HTTP response thành công theo contract nghiệp vụ,
  không tính 4xx do client nhập sai như server outage

eligible_requests:
  HTTP request hợp lệ trong phạm vi sản phẩm đã thỏa thuận
~~~

Phải thống nhất rõ cách loại trừ lỗi client, synthetic probes, bot traffic, maintenance và timeout. Không tự chọn lại định nghĩa SLI sau khi đã có outage.

### 3.2. RPO và RTO

- **RPO 15 phút:** bản phục hồi không được cũ hơn 15 phút so với thời điểm sự cố đối với data có scope tương ứng.
- **RTO 2 giờ:** nghiệp vụ tạo/xem đơn có thể hoạt động lại trong hai giờ, bao gồm phát hiện, quyết định, restore, xác minh và chuyển traffic.
- RTO/RPO phải được đo qua restore drill, không tự suy ra từ cờ "backups enabled".

Nếu F01 yêu cầu không mất bất kỳ đơn hàng đã được thông báo thành công nào, RPO 15 phút chỉ là **ngưỡng hạ tầng**; còn phải thiết kế reconciliation/replay nghiệp vụ để xử lý giao dịch bị mất sau restore.

## 4. Lựa chọn kiến trúc và ghi ADR

Các phương án cần đánh giá trước khi chọn dịch vụ:

| Tiêu chí | Compute Engine VM | GKE | Cloud Run |
|---|---|---|---|
| App stateless/container | Chạy được | Phù hợp | Rất phù hợp |
| Kiểm soát OS/network | Cao | Trung bình/cao | Hạn chế theo runtime |
| Autoscaling | Cần MIG hoặc thiết kế riêng | HPA/cluster | Quản lý theo service |
| Vận hành hạ tầng | Cao | Trung bình/cao | Thấp hơn |
| Workload stateful/phụ thuộc kernel | Linh hoạt | Có ràng buộc | Không phải lựa chọn đầu tiên |
| Tích hợp CI/CD | Có | Có | Có |
| Kỹ năng cần có | VM/OS | Kubernetes/SRE | Containers/serverless/IAM |

**ADR-001:** Chọn Cloud Run cho frontend và Orders API do cả hai stateless, traffic theo giờ biến động và nhóm muốn giảm vận hành node. Cloud SQL đảm nhận relational transaction; Cloud Storage lưu binary objects; Pub/Sub tách các xử lý hậu giao dịch.

**Đánh đổi được chấp nhận:** cold start, giới hạn concurrency/timeout, egress setup và database connection pressure khi scale. Không dùng Cloud Run nếu workload cần local persistent file system, kernel privilege hoặc protocol không phù hợp mà chưa thiết kế lại.

### 4.1. Mẫu ADR ngắn

~~~markdown
# ADR-001: Chạy Orders API trên Cloud Run

Status: Accepted (chỉ sau design review)
Context:
- Java Spring Boot stateless, lưu dữ liệu trong PostgreSQL.
- Cần autoscaling, giảm vận hành VM.
Decision:
- Cloud Run backend, Cloud SQL PostgreSQL và Direct VPC egress.
Alternatives:
- Compute Engine MIG: linh hoạt hơn nhưng vận hành OS.
- GKE: phù hợp khi có nhu cầu Kubernetes rộng hơn.
Consequences:
- Phải tính DB connection budget và SLO cold-start.
- Phải tách state và background jobs khỏi HTTP request.
Review date:
- Khi tăng trưởng/tính chất workload thay đổi.
~~~

ADR là **bản ghi quyết định**, không phải tuyên bố rằng Cloud Run luôn tốt hơn GKE.

## 5. Kiến trúc tham chiếu ba tầng

~~~mermaid
flowchart TD
    USER["Người dùng / browser"]
    EDGE["HTTPS / custom domain<br/>Optional external Application LB"]
    WEB["Cloud Run: shopflow-web<br/>Public presentation + app auth"]
    API["Cloud Run: shopflow-api<br/>IAM-protected backend"]
    VPC["Custom VPC subnet<br/>Direct VPC egress"]
    DB["Cloud SQL PostgreSQL<br/>Private IP + backups/PITR"]
    SEC["Secret Manager"]
    GCS["Cloud Storage: invoices"]
    PUB["Pub/Sub: order-events"]
    WORKER["Worker / Cloud Run<br/>Event consumer"]
    BUILD["Cloud Build + Artifact Registry"]
    OBS["Logging, Monitoring, Tracing"]
    USER --> EDGE --> WEB
    WEB -->|"HTTPS + ID token"| API
    API --> VPC --> DB
    API --> SEC
    API --> GCS
    API -->|"Transactional outbox publisher"| PUB
    PUB --> WORKER
    BUILD --> WEB
    BUILD --> API
    API --> OBS
    WEB --> OBS
    WORKER --> OBS
~~~

Load balancer, Cloud Armor và Cloud CDN có thể được thêm vào production nếu cần WAF, domain, edge cache và policy tập trung. Trong lab có thể dùng trực tiếp URL Cloud Run của frontend để giảm chi phí/độ phức tạp.

### 5.1. Data flow và trust boundary

| Luồng | Giao thức | Danh tính/quyền | Điểm kiểm soát |
|---|---|---|---|
| Browser → Web | HTTPS | App-level user identity/session | TLS, CSRF/XSS, session validation |
| Web → API | HTTPS | Web runtime SA + roles/run.invoker | Google-signed ID token và app authorization |
| API → Cloud SQL | PostgreSQL qua connector | API runtime SA + DB user | Cloud SQL Client, VPC route, DB GRANT |
| API → Cloud Storage | HTTPS API | API runtime SA | Object creator/reader theo bucket |
| API → Secret Manager | HTTPS API | API runtime SA | secretAccessor đúng secret/version |
| Outbox publisher → Pub/Sub | HTTPS API | Publisher SA | pubsub.publisher trên topic |
| Pub/Sub → consumer | Push HTTPS hoặc pull | Subscriber/push identity | Consumer IAM, idempotency, retry |
| Operator → control plane | Google Cloud API | Nhân sự qua IAM/WIF/MFA | Audit Logs, change approval |

Cloud Run **service** dùng Direct VPC egress để gọi VPC resources; nó không tự có private ingress kiểu VM. Backend dùng HTTPS service URL và bắt buộc IAM invoker. Nếu muốn giới hạn ingress chặt hơn, phải thiết kế đường gọi hợp lệ cho service-to-service, không bật internal-only mà không thử đường vào.

### 5.2. Đặt dữ liệu và kiểm soát egress

- Đặt Cloud Run, Cloud SQL, bucket và Artifact Registry cùng region khi phù hợp để giảm latency/cross-region cost.
- Chọn region theo data residency và service availability của tổ chức; ví dụ lab dùng asia-southeast1, không coi đó là lựa chọn bắt buộc.
- Cloud SQL private IP yêu cầu VPC connectivity và đường đến Google APIs cho Cloud SQL Connector.
- Cloud Storage/PubSub/Secret Manager dùng HTTPS Google APIs; egress và quyền cần đánh giá riêng.
- Không truyền raw customer credentials hoặc service account key tới browser.
- Đặt expiry/retention/lifecycle cho object để tránh chi phí tích tụ.

## 6. Landing zone và phân tách môi trường

Không để staging và production dùng chung secret, service account hoặc database.

~~~text
organization / folder theo chính sách doanh nghiệp
  platform-shared (nếu tổ chức có network chung)
  shopflow-staging
    shopflow-vpc, subnet, Cloud SQL staging, buckets, services
  shopflow-production
    production network/Cloud SQL, buckets, services
  security-logging (nếu có dự án logging trung tâm)
~~~

Trong mô hình nhỏ, mỗi môi trường là một project độc lập. Trong doanh nghiệp, Shared VPC, folder policies và billing boundaries có thể theo landing zone chuẩn.

### 6.1. Resource naming và labels

| Loại | Ví dụ staging | Label/owner |
|---|---|---|
| Project | shopflow-staging-001 | env=staging, team=commerce |
| VPC | shopflow-vpc | owner=platform |
| Subnet | shopflow-run-subnet | region=asia-southeast1 |
| Cloud Run frontend | shopflow-web | app=shopflow, tier=web |
| Cloud Run backend | shopflow-api | app=shopflow, tier=api |
| Cloud SQL | shopflow-db | data_class=confidential |
| Bucket | shopflow-invoices-staging-UNIQUE | retention=business-approved |
| Pub/Sub topic | shopflow-order-events | owner=commerce |
| Artifact Registry | shopflow-images | team=platform |
| Service accounts | shopflow-web-sa, shopflow-api-sa | purpose=runtime |

Tên bucket phải **duy nhất toàn cầu**; không tự giả định mẫu tên trên còn trống. Tất cả tags/labels áp dụng trong giới hạn ký tự/cú pháp của từng dịch vụ.

### 6.2. API và quota

Ví dụ lệnh chạy **chỉ trong staging đã được cấp quyền**:

~~~bash
PROJECT_ID="shopflow-staging-001"
REGION="asia-southeast1"

gcloud config set project "$PROJECT_ID"

gcloud services enable \
  run.googleapis.com \
  compute.googleapis.com \
  sqladmin.googleapis.com \
  servicenetworking.googleapis.com \
  artifactregistry.googleapis.com \
  cloudbuild.googleapis.com \
  secretmanager.googleapis.com \
  pubsub.googleapis.com \
  storage.googleapis.com \
  monitoring.googleapis.com \
  logging.googleapis.com \
  --project="$PROJECT_ID"
~~~

Quyền bật API không phải quyền triển khai mọi dịch vụ. Trước provisioning, kiểm tra organization policies, region availability, quota, billing account và APIs phụ thuộc. Trong production, bật API qua IaC và review.

## 7. Identity, IAM và bảo vệ secret

Tạo ít nhất hai runtime service accounts riêng biệt và một build/deploy identity theo policy tổ chức:

~~~bash
gcloud iam service-accounts create shopflow-web-sa \
  --display-name="ShopFlow web runtime" \
  --project="$PROJECT_ID"

gcloud iam service-accounts create shopflow-api-sa \
  --display-name="ShopFlow API runtime" \
  --project="$PROJECT_ID"
~~~

### 7.1. IAM matrix

| Principal | Quyền tối thiểu mẫu | Scope |
|---|---|---|
| Web runtime SA | roles/run.invoker | Trên Cloud Run shopflow-api |
| API runtime SA | roles/cloudsql.client | Project chứa Cloud SQL instance |
| API runtime SA | roles/secretmanager.secretAccessor | Secret DB password riêng |
| API runtime SA | roles/storage.objectCreator | Bucket invoices nếu chỉ ghi mới |
| Outbox publisher SA hoặc API SA | roles/pubsub.publisher | Topic order-events |
| Consumer runtime SA | Subscriber hoặc service permissions phù hợp | Subscription và tài nguyên đích |
| CI build SA | Quyền build, read source, push image | Project/repository cần thiết |
| CD deploy SA | Cloud Run deploy + iam.serviceAccountUser | Service và runtime SA được duyệt |
| Operator | Viewer/Monitoring và incident breakglass có kiểm soát | Project/service scope |

Dùng resource-level bindings khi dịch vụ hỗ trợ; không cấp Owner/Editor cho app SA. Developer không cần có Secret Manager accessor trên mọi secret hoặc quyền ghi production chỉ để chạy unit tests.

### 7.2. Ba lớp xác thực không được nhập làm một

1. **Người dùng cuối:** xác thực và phân quyền xem/tạo đơn theo user hoặc tenant.
2. **Service-to-service:** web SA được quyền gọi backend Cloud Run bằng ID token với audience URL backend.
3. **Database:** Cloud SQL Connector xác thực IAM ở mức kết nối, nhưng PostgreSQL user/GRANT vẫn quyết định quyền đọc/ghi.

Đừng cho rằng roles/run.invoker trên backend thay thế quyền của người dùng cuối. Mỗi yêu cầu tạo/xem đơn cần kiểm tra owner/tenant trong business layer.

### 7.3. Secret lifecycle

- Không ghi password vào Terraform variable mặc định, Git, Dockerfile hoặc image layer.
- Tạo secret bằng quy trình riêng được bảo vệ, lưu và rotation theo chính sách.
- Gắn secret version cụ thể khi cần kiểm soát rollback; dùng latest phải hiểu rằng cấu hình version/rotation cần được kiểm thử.
- Hạn chế principals có secretAccessor.
- Rotation phải kiểm tra active DB connections và thời gian rollout.
- Bật audit log phù hợp, không log giá trị secret.

## 8. Thiết kế mạng và private data path

~~~mermaid
flowchart LR
    WEB["Cloud Run web"] -->|"HTTPS ID token"| API["Cloud Run API"]
    API -->|"Direct VPC egress"| SUB["Subnet 10.80.8.0/24"]
    SUB --> PSA["Private Services Access"]
    PSA --> SQL["Cloud SQL private IP"]
    API --> GOOGLE["Google APIs 443<br/>Cloud SQL Admin / PubSub / Storage"]
~~~

### 8.1. VPC và subnet

Ví dụ CLI nếu đang dựng môi trường staging **mới**, chưa có Shared VPC:

~~~bash
gcloud compute networks create shopflow-vpc \
  --subnet-mode=custom \
  --project="$PROJECT_ID"

gcloud compute networks subnets create shopflow-run-subnet \
  --network=shopflow-vpc \
  --region="$REGION" \
  --range=10.80.8.0/24 \
  --enable-private-ip-google-access \
  --project="$PROJECT_ID"
~~~

Với Cloud Run services, Direct VPC egress yêu cầu subnet đủ lớn, tối thiểu /26. /24 trong ví dụ là để có headroom khi scale và rollout revisions. CIDR 10.80.8.0/24 phải được so với các dải trên mạng tổ chức để tránh overlap.

### 8.2. Private Services Access cho Cloud SQL

Cloud SQL private IP qua Private Services Access cần reserved range và service networking connection. Ví dụ **chỉ áp dụng khi network chưa có private services connection**:

~~~bash
gcloud compute addresses create google-managed-services-shopflow \
  --global \
  --purpose=VPC_PEERING \
  --prefix-length=16 \
  --network="projects/$PROJECT_ID/global/networks/shopflow-vpc" \
  --project="$PROJECT_ID"

gcloud services vpc-peerings connect \
  --service=servicenetworking.googleapis.com \
  --ranges=google-managed-services-shopflow \
  --network=shopflow-vpc \
  --project="$PROJECT_ID"
~~~

Không tạo allocation trùng, sửa peering hoặc xóa range đang dùng chung. Với production Shared VPC, dự án host/network team thường chịu trách nhiệm. Cloud SQL instance phải được tạo với private IP trên network đúng; không tự bật public IP chỉ vì kết nối staging lỗi.

### 8.3. Backend kết nối SQL

Ví dụ Spring Boot qua Cloud SQL Java Connector và PostgreSQL JDBC socket factory; cần dependency pgJDBC và postgres-socket-factory tương thích:

~~~properties
server.port=8080
spring.datasource.url=jdbc:postgresql:///orders?cloudSqlInstance=PROJECT_ID:asia-southeast1:shopflow-db&socketFactory=com.google.cloud.sql.postgres.SocketFactory&ipTypes=PRIVATE&cloudSqlRefreshStrategy=lazy&sslmode=disable
spring.datasource.username=shopflow_app
spring.datasource.hikari.maximum-pool-size=5
spring.datasource.hikari.minimum-idle=0
spring.datasource.hikari.connection-timeout=10000
~~~

Trong ứng dụng thật, **không hard-code instance connection name**, mà nạp từ cấu hình/biến môi trường đã được kiểm duyệt. Password lấy từ SPRING_DATASOURCE_PASSWORD do Secret Manager cấp; không viết vào file properties.

Cờ sslmode=disable ở lớp **pgJDBC khi dùng Cloud SQL Java Connector** không có nghĩa kết nối tới Cloud SQL là plaintext: TLS do connector quản lý. Không dùng cấu hình đó cho kết nối JDBC trực tiếp qua IP khi chưa thiết lập TLS đúng.

### 8.4. Connection budget

Nếu API có max 10 Cloud Run instances và mỗi instance Hikari pool tối đa 5 connections:

\[
C_{\text{tối đa dự kiến}} \approx 10 \times 5 = 50\ \text{connections}
\]

Đó là 50 connections cho backend, chưa tính migrations, admin tools, reporting và workloads khác. Đặt giới hạn pool theo năng lực Cloud SQL, theo dõi active/pending connections, latency và query lock. Tăng concurrency của Cloud Run không tự tăng capacity database.

## 9. Data model, giao dịch và idempotency

### 9.1. Minimal schema

~~~sql
CREATE TABLE orders (
  id BIGSERIAL PRIMARY KEY,
  customer_id UUID NOT NULL,
  idempotency_key VARCHAR(128) NOT NULL,
  status VARCHAR(32) NOT NULL,
  total_amount_minor BIGINT NOT NULL,
  currency CHAR(3) NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (customer_id, idempotency_key)
);

CREATE TABLE order_outbox (
  event_id UUID PRIMARY KEY,
  order_id BIGINT NOT NULL REFERENCES orders(id),
  event_type VARCHAR(128) NOT NULL,
  payload JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  published_at TIMESTAMPTZ
);
~~~

Không lưu tiền bằng floating point cho nghiệp vụ cần chính xác; ví dụ dùng minor units theo currency và quy tắc tính tiền được phê duyệt. Migration tool (Flyway/Liquibase) phải quản lý schema version; tránh áp dụng DDL tự động mỗi lúc app startup nếu không kiểm soát.

### 9.2. Transactional outbox

~~~mermaid
sequenceDiagram
    participant U as Người dùng
    participant API as Orders API
    participant DB as Cloud SQL
    participant PUB as Outbox publisher
    participant PS as Pub/Sub
    U->>API: POST order + idempotency key
    API->>DB: Transaction: INSERT order + outbox event
    DB-->>API: COMMIT
    API-->>U: 201 order_id
    PUB->>DB: Poll unsent outbox
    PUB->>PS: Publish event_id + payload
    PS-->>PUB: Ack
    PUB->>DB: Mark published_at
~~~

Việc ghi order và outbox **trong cùng DB transaction** tránh trạng thái "order đã commit nhưng sự kiện chưa có record để retry". Tuy nhiên nếu publisher gửi Pub/Sub thành công rồi lỗi trước khi cập nhật published_at, event có thể gửi lại. Consumer vẫn phải idempotent theo event_id.

**Không hứa exactly-once end-to-end** chỉ vì chọn Pub/Sub. Kết quả nghiệp vụ một lần cần được tạo bằng deduplication atomic trong consumer và/hoặc idempotency key.

### 9.3. API contract

| API | Input | Expected status | Test bắt buộc |
|---|---|---|---|
| POST /api/orders | JSON items + Idempotency-Key header | 201 hoặc response đơn đã tạo | Duplicate key, transaction atomic |
| GET /api/orders/{id} | Order ID | 200 hoặc 404/403 theo policy | Tenant isolation |
| GET /healthz | Không yêu cầu dữ liệu nghiệp vụ | 200 khi app alive | Liveness |
| GET /readyz | DB connection/readiness theo policy | 200/503 | Readiness |
| GET /api/orders | Pagination, filters | 200 | Authz, query performance |

Mẫu request:

~~~http
POST /api/orders HTTP/1.1
Content-Type: application/json
Idempotency-Key: order-request-7d9a

{
  "items": [
    {"sku": "book-01", "quantity": 2}
  ],
  "currency": "VND"
}
~~~

Mẫu response:

~~~json
{
  "id": 14572,
  "status": "CREATED",
  "currency": "VND",
  "totalAmountMinor": 240000,
  "traceId": "c84f-example"
}
~~~

Dữ liệu ví dụ là giả định. Hệ thống thật phải kiểm tra giá ở server và không tin amount do client gửi. Tránh cho health endpoint thực hiện truy vấn nặng làm database thêm tải khi instance mở rộng.

## 10. Cấu trúc repository và ownership

~~~text
shopflow/
  README.md
  docs/
    charter.md
    requirements.md
    architecture.md
    adr/
      001-cloud-run.md
      002-database.md
    security-threat-model.md
    runbooks/
      api-5xx.md
      db-restore.md
      release-rollback.md
    handover/
      resource-register.md
      raci.md
      acceptance.md
  services/
    shopflow-web/
      Dockerfile
      src/
      tests/
    shopflow-api/
      Dockerfile
      pom.xml
      src/main/
      src/test/
  infrastructure/
    modules/
      network/
      sql/
      cloud-run/
      observability/
    envs/
      staging/
      production/
  pipelines/
    cloudbuild-api.yaml
  tests/
    api-contract/
    load/
    dr/
~~~

Đây là **cấu trúc đề xuất để người học tạo trong repository của mình**, không phải danh sách file được worker này phép ghi. Nội dung secrets, kubeconfigs, Terraform state, private keys và build credentials không đưa lên repository.

### 10.1. Branching và thay đổi

- Pull request bắt buộc code review và status checks.
- Infrastructure change qua terraform plan được lưu làm bằng chứng và phê duyệt.
- Database schema migration review riêng, có hướng backward-compatible.
- Production deployment dùng image digest đã qua staging; không build lại từ cùng branch rồi coi artifact giống hệt.
- CODEOWNERS hoặc reviewer rules cho các phần bảo mật/IAM/network/DR.
- Không tự chỉnh production bằng Console nếu không ghi change record và reconcile drift.

## 11. IaC: từ kiến trúc thành tài nguyên lặp lại

Terraform được dùng để định nghĩa VPC, subnet, IAM, Cloud SQL, Cloud Run, Monitoring và các resource phù hợp. Một nhóm nên quản lý **backend state tập trung và khóa đồng thời**.

### 11.1. Bootstrap remote state

Trước khi terraform init, platform team tạo GCS bucket state riêng với quyền hạn chế, public access prevention, versioning và quy trình phục hồi. Terraform backend không thể tự tạo bucket mà nó cần để lưu chính state.

Ví dụ backend:

~~~hcl
terraform {
  required_providers {
    google = {
      source = "hashicorp/google"
    }
  }
  backend "gcs" {
    bucket = "ORG-APPROVED-TF-STATE-BUCKET"
    prefix = "shopflow/staging"
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}
~~~

**Lưu ý:** phiên bản provider phải được chọn và pin qua .terraform.lock.hcl sau khi kiểm thử; ví dụ bỏ version vì đây là skeleton, không phải Terraform module production hoàn chỉnh.

### 11.2. Network module nhỏ

~~~hcl
variable "project_id" { type = string }
variable "region" { type = string }

resource "google_compute_network" "shopflow" {
  name                    = "shopflow-vpc"
  auto_create_subnetworks = false
}

resource "google_compute_subnetwork" "run" {
  name                     = "shopflow-run-subnet"
  region                   = var.region
  network                  = google_compute_network.shopflow.id
  ip_cidr_range            = "10.80.8.0/24"
  private_ip_google_access = true
}
~~~

Chưa thể dùng module nhỏ này để có Cloud SQL private IP: còn cần service networking reserved range/connection và DB instance. Các quyền IAM và services APIs cũng cần quản lý. Không đặt database password trực tiếp trong Terraform state nếu có thể tránh; dùng Secret Manager qua quy trình an toàn.

### 11.3. Quy trình thay đổi hạ tầng

~~~bash
terraform fmt -check
terraform validate
terraform plan -out=staging.tfplan
# Người có thẩm quyền review plan, chi phí và thay đổi IAM/network.
terraform apply staging.tfplan
~~~

Lệnh apply **có tác động thực** và có thể phát sinh chi phí. File plan/state có thể chứa dữ liệu nhạy cảm; bảo quản trong vùng truy cập hạn chế, không gửi vào chat/ticket công khai.

Một production pipeline tốt không chạy terraform destroy tự động. Với Cloud SQL, sử dụng deletion protection, backup retention và quy trình thay đổi có phê duyệt. Đừng coi mọi khác biệt giữa state và hạ tầng là lỗi cần apply ngay khi đang có migration hoặc incident.

## 12. Artifact, build và CI

Chỉ deploy image đã được kiểm thử và có thể truy vết. Quy trình CI:

~~~mermaid
flowchart LR
    PR["Pull request"] --> T["Unit/integration + SAST"]
    T --> B["Build container"]
    B --> SCAN["Dependency/container scan"]
    SCAN --> REG["Artifact Registry: digest"]
    REG --> ST["Staging deploy + tests"]
    ST --> APPROVE["Approval / promotion"]
    APPROVE --> PROD["Production release"]
~~~

### 12.1. Ví dụ Cloud Build cho Orders API

Ví dụ này giả định source và Dockerfile nằm trong services/shopflow-api, Maven build tạo JAR trước khi Docker build. Các substitution phải được cấu hình trong Cloud Build trigger/job.

~~~yaml
substitutions:
  _REGION: asia-southeast1
  _REPO: shopflow-images

steps:
  - name: 'maven:3.9-eclipse-temurin-17'
    dir: 'services/shopflow-api'
    entrypoint: 'mvn'
    args: ['-B', '-ntp', 'verify']

  - name: 'gcr.io/cloud-builders/docker'
    args:
      - 'build'
      - '-t'
      - '$_REGION-docker.pkg.dev/$PROJECT_ID/$_REPO/shopflow-api:$BUILD_ID'
      - 'services/shopflow-api'

  - name: 'gcr.io/cloud-builders/docker'
    args:
      - 'push'
      - '$_REGION-docker.pkg.dev/$PROJECT_ID/$_REPO/shopflow-api:$BUILD_ID'

images:
  - '$_REGION-docker.pkg.dev/$PROJECT_ID/$_REPO/shopflow-api:$BUILD_ID'
~~~

Đây là **ví dụ build pipeline**, chưa tự triển khai production. Cần cấu hình build service account, repository quyền push, API, trigger, scan policy và lưu artifact digest. Bộ kiểm thử thật phải có unit tests, integration tests, migrations/DB compatibility tests và security checks theo scope.

### 12.2. Image provenance và release manifest

Release record tối thiểu:

~~~yaml
release_id: shopflow-2026-11-example
git_commit: REPLACE_WITH_COMMIT_SHA
image_digest: sha256:REPLACE_WITH_VERIFIED_DIGEST
pipeline_run: REPLACE_WITH_CLOUD_BUILD_ID
environment: staging
tested_at: REPLACE_WITH_TIMESTAMP
approved_by: REPLACE_WITH_APPROVER
terraform_plan_ref: REPLACE_WITH_REVIEWED_PLAN_REFERENCE
db_migration_version: V12
~~~

Hồ sơ này phải được **điền bằng kết quả thật** từ CI/test, không bằng giá trị mô phỏng. Khi promote staging → production, dùng cùng digest và database migrations tương thích thay vì tự rebuild image từ branch. Cân nhắc SBOM, vulnerability scan và build provenance/attestation theo supply-chain policy tổ chức.

## 13. Triển khai staging theo thứ tự phụ thuộc

Không thực hiện hàng loạt lệnh mà bỏ qua kết quả ở từng bước. Thiết kế **gates**, để khi xuất hiện lỗi chỉ cần dừng ở một tầng.

| Bước | Thao tác | Điều kiện PASS |
|---|---|---|
| S1 | Project, APIs, billing, organization policy | Có owner, quota và quyền hợp lệ |
| S2 | VPC/subnet, private service networking | CIDR/route review PASS |
| S3 | Runtime SA, secrets, bucket, topic, repository | IAM matrix và security review PASS |
| S4 | Cloud SQL, database role, migrations, backup/PITR | Instance private, recovery config đạt yêu cầu |
| S5 | Build/test/scan frontend và API | Pipeline PASS, image digest được lưu |
| S6 | Deploy backend Cloud Run | Ready, SQL connection hoạt động, IAM bảo vệ |
| S7 | Cấp invoker và deploy frontend | Web gọi được API bằng service identity |
| S8 | Outbox publisher và Pub/Sub consumer nếu dùng | Retry/dedupe/DLQ test PASS |
| S9 | E2E, load, security và recovery tests | Không còn critical defect |
| S10 | Dashboard, alerts, SLO và runbook | Ops owner xác nhận |
| S11 | Go/No-Go production | Approval hợp lệ |

### 13.1. Cloud SQL staging

Trong Console hoặc Terraform module được review:

1. Chọn PostgreSQL version phù hợp runtime/driver đã kiểm thử.
2. Chọn region gần Cloud Run để giảm latency và rủi ro cross-region.
3. Tạo instance có **private IP** với đúng VPC và Private Services Access.
4. Tạo database orders, DB user runtime không có quyền superuser.
5. Bật backups và kiểm tra **PITR thực sự được bật** theo edition/cách tạo instance; không tin mọi trường hợp đều bật mặc định.
6. Cấu hình storage, maintenance, deletion protection, HA theo yêu cầu và budget.
7. Chạy migration schema bằng danh tính DDL riêng, không dùng runtime application user.
8. Kiểm tra connection và quyền từ **Cloud Run staging**; test trên laptop không thay thế việc này.

### 13.2. Triển khai backend với image đã kiểm thử

Các biến dưới đây phải được thay bằng giá trị từ release manifest đã được duyệt:

~~~bash
PROJECT_ID="shopflow-staging-001"
REGION="asia-southeast1"
API_SA="shopflow-api-sa@$PROJECT_ID.iam.gserviceaccount.com"
API_IMAGE="asia-southeast1-docker.pkg.dev/$PROJECT_ID/shopflow-images/shopflow-api:REVIEWED_BUILD_ID"
SQL_CONN="$PROJECT_ID:$REGION:shopflow-db"

gcloud run deploy shopflow-api \
  --project="$PROJECT_ID" \
  --region="$REGION" \
  --image="$API_IMAGE" \
  --service-account="$API_SA" \
  --no-allow-unauthenticated \
  --ingress=all \
  --network=shopflow-vpc \
  --subnet=shopflow-run-subnet \
  --vpc-egress=private-ranges-only \
  --set-env-vars="INSTANCE_CONNECTION_NAME=$SQL_CONN,SPRING_PROFILES_ACTIVE=staging,SPRING_DATASOURCE_USERNAME=shopflow_app" \
  --set-secrets="SPRING_DATASOURCE_PASSWORD=shopflow-db-password:5" \
  --max-instances=10
~~~

**Tiền điều kiện:** image và secret version 5 đã tồn tại; SA có roles/cloudsql.client, quyền đọc secret được chỉ định; VPC/subnet/Cloud SQL private IP được tạo đúng; app thực sự nạp INSTANCE_CONNECTION_NAME để tạo JDBC URL. Mẫu lệnh này không tự bảo đảm mọi quyền và cấu hình đã sẵn sàng.

Cờ --ingress=all cho phép nhận HTTP connection đến service URL, nhưng --no-allow-unauthenticated vẫn yêu cầu IAM invoker. Nếu chính sách tổ chức yêu cầu ingress chặt hơn, thiết kế lại đường truy cập frontend→backend và kiểm thử; không đổi tùy tiện sang internal-only.

### 13.3. Frontend xác thực với backend

Sau khi backend tồn tại:

~~~bash
WEB_SA="shopflow-web-sa@$PROJECT_ID.iam.gserviceaccount.com"

gcloud run services add-iam-policy-binding shopflow-api \
  --project="$PROJECT_ID" \
  --region="$REGION" \
  --member="serviceAccount:$WEB_SA" \
  --role="roles/run.invoker"
~~~

Ví dụ Node.js trên **web server** (không chạy trong browser):

~~~javascript
const {GoogleAuth} = require("google-auth-library");
const auth = new GoogleAuth();
const apiOrigin = process.env.API_ORIGIN;

async function getOrder(orderId) {
  const client = await auth.getIdTokenClient(apiOrigin);
  const response = await client.request({
    url: apiOrigin + "/api/orders/" + encodeURIComponent(orderId),
    method: "GET"
  });
  return response.data;
}
~~~

Audience của ID token là **Cloud Run service URL hoặc custom audience đã cấu hình**, không lấy bừa custom domain làm audience. Backend vẫn phải xác thực/ủy quyền người dùng cuối theo ứng dụng; IAM invoker chỉ xác minh danh tính service caller.

### 13.4. Deploy frontend

~~~bash
API_URL=$(gcloud run services describe shopflow-api \
  --project="$PROJECT_ID" \
  --region="$REGION" \
  --format="value(status.url)")

WEB_IMAGE="asia-southeast1-docker.pkg.dev/$PROJECT_ID/shopflow-images/shopflow-web:REVIEWED_BUILD_ID"

gcloud run deploy shopflow-web \
  --project="$PROJECT_ID" \
  --region="$REGION" \
  --image="$WEB_IMAGE" \
  --service-account="$WEB_SA" \
  --allow-unauthenticated \
  --set-env-vars="API_ORIGIN=$API_URL" \
  --max-instances=10
~~~

--allow-unauthenticated chỉ dùng nếu frontend thực sự là website public được phép công bố. Với app nội bộ, sử dụng identity/edge ingress policy phù hợp và kiểm thử đường truy cập đã xác thực.

## 14. Outbox, Pub/Sub và consumer được vận hành thế nào?

Luồng outbox → Pub/Sub → consumer có nhiều điểm có thể thất bại dù một request tạo đơn đã COMMIT.

| Thành phần | Quyền và control | Tình huống test |
|---|---|---|
| Outbox publisher | Pub/Sub publisher trên topic | Publish xong nhưng chưa mark DB |
| Pub/Sub topic/subscription | Retention, retry policy, DLQ | Backlog, poison message, redelivery |
| Push subscription | Push service identity và quyền gọi Cloud Run consumer | Sai audience, 401/403 |
| Pull consumer | pubsub.subscriber trên subscription | Ack deadline hết, reconnect |
| Worker application | Atomic event deduplication | Gửi invoice/email trùng |
| Dead-letter flow | Alert, operator, quyền publish/consume | Không xử lý event lỗi vô hạn |

Với Pub/Sub push tới Cloud Run, cấu hình push authentication bằng service account được ủy quyền; push SA cần roles/run.invoker ở worker, và Pub/Sub service agent phải có quyền tạo OIDC token phù hợp. Không mở worker unauthenticated để xử lý lỗi 403.

### 14.1. Idempotency của consumer

~~~sql
CREATE TABLE processed_events (
  event_id UUID PRIMARY KEY,
  processed_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
~~~

Một transaction xử lý:

1. Ghi event_id bằng INSERT có uniqueness guard (đã tồn tại thì return).
2. Thực hiện side effect DB trong cùng transaction nếu có thể.
3. Commit rồi mới ACK.
4. Với side effect bên ngoài như email, cần một idempotency key/ledger hoặc outbox tiếp theo vì email có thể đã được gửi nhưng process chưa lưu trạng thái.

Pub/Sub có thể redeliver. **Không tuyên bố exactly-once toàn pipeline** chỉ vì có Pub/Sub, outbox hoặc một lần ACK thành công.

## 15. Ma trận kiểm thử trước production

| Tầng | Trường hợp | Môi trường | Evidence |
|---|---|---|---|
| Unit | Validation, pricing, state transition, idempotency | JVM/local | JUnit report |
| Component | Repository, outbox, transaction rollback | DB test container/fakes | Integration report |
| API contract | Response schema, 401/403/409, pagination | Staging | API tests |
| Cloud integration | Cloud SQL/Secret Manager/Bucket/PubSub permissions | Staging | Logs + resource states |
| Security | Secret scan, SAST, dependency scan, user authz | CI/staging | Findings/approvals |
| Load | Baseline và peak traffic | Staging có quota | P95, 5xx, DB pool |
| Failure | DB timeout, PubSub backlog, expired secret | Staging cô lập | Recovery/retry results |
| Backup/DR | PITR, restore và dữ liệu đúng | Recovery staging | RPO/RTO timestamps |
| E2E | Login → đặt đơn → xem đơn/invoice/event | Staging | Business sign-off |

### 15.1. Các case bắt buộc

- Hai POST cùng idempotency key xảy ra đồng thời chỉ tạo một order.
- Runtime SA không đọc được secret ngoài scope.
- Anonymous request vào API backend bị từ chối.
- User A không được đọc đơn của user B, kể cả khi gọi qua frontend SA hợp lệ.
- Outbox publish failure có thể replay sau restart.
- Pub/Sub redelivery không tạo side effect trùng.
- Database migration không phá khả năng chạy của revision cũ trong canary.
- Database connection timeout có xử lý giới hạn, không retry vô hạn.
- Sau restore, bản ghi orders và invoice metadata liên kết đúng với Cloud Storage.

### 15.2. HTTP smoke test

Chỉ khi frontend có endpoint healthz:

~~~bash
WEB_URL=$(gcloud run services describe shopflow-web \
  --project="$PROJECT_ID" \
  --region="$REGION" \
  --format="value(status.url)")

curl -i "$WEB_URL/healthz"
~~~

Không tự mở quyền public cho backend hoặc đưa ID token vào query string. Test trực tiếp backend cần principal có run.invoker và Google-signed ID token audience đúng.

### 15.3. Load test và connection budget

| Mức tải | API P95 | 5xx | Active DB connections | Kết luận |
|---|---:|---:|---:|---|
| 20 requests/s | Đo thật | Đo thật | Đo thật | Pass/fail |
| 100 requests/s | Đo thật | Đo thật | Đo thật | Pass/fail |
| 200 requests/s | Đo thật | Đo thật | Đo thật | Pass/fail |
| Burst 5 phút | Đo thật | Đo thật | Đo thật | Pass/fail |

Các ô này cố tình để "Đo thật": không tạo bằng chứng giả khi chưa chạy test. Thử với request mix thực tế, không chỉ gọi /healthz. Chỉ load test môi trường được phê duyệt.

## 16. Threat model và kiểm thử bảo mật

| Mối đe dọa | Ranh giới | Control | Evidence |
|---|---|---|---|
| Anonymous gọi backend | Cloud Run IAM | no-allow-unauthenticated + invoker | Negative test |
| Broken object authorization | Backend/data | Tenant ownership checks | Cross-user access test |
| SQL injection | Java→PostgreSQL | Prepared statements/binding | SAST + test |
| Secrets trong code/log | CI/runtime | Secret Manager, scanning, redaction | Scan results |
| Pub/Sub event giả/trùng | Topic/worker | Publisher IAM, schema, dedupe | Replay test |
| Invoice đọc trái phép | Bucket/application | Object IAM, signed access theo policy | IAM negative test |
| Xóa nhầm DB | Database | Deletion protection, PITR, role separation | Restore drill |
| Compromised CI | Deployment | Workload Identity Federation, approval, provenance | IAM/audit review |
| Supply-chain dependency | Container | Dependency scan, SBOM, artifact digest | CI evidence |

Cloud encryption at rest không tự chứng minh ứng dụng đáp ứng mọi compliance controls. Nếu cần CMEK, phải thiết kế vòng đời và recovery của Cloud KMS keys trước khi bật, vì key unavailable có thể khiến bản backup không dùng được.

## 17. Dashboard, SLI và alerting

| Tín hiệu | Nguồn | Người cần phản ứng |
|---|---|---|
| Good/eligible requests và 5xx | Cloud Run/Monitoring | App on-call |
| P50/P95/P99 theo endpoint | Tracing/APM | App/SRE |
| Order success, duplicate prevented | Custom application metrics | Commerce/App |
| CPU, disk, connections, slow query | Cloud SQL Monitoring | DBA |
| Outbox age / oldest unacked message | App/PubSub | Event worker owner |
| Invoice write failure | Storage metrics/app logs | App |
| Secret/IAM denied | Audit Logs | Security/App |
| Cloud Run revision rollout | Deploy logs/revision metrics | Platform |
| Budget anomaly | Cloud Billing | FinOps |

Ví dụ application structured log:

~~~json
{
  "severity": "INFO",
  "service": "shopflow-api",
  "environment": "staging",
  "release": "image-digest-placeholder",
  "traceId": "example-trace",
  "event": "order_created",
  "orderId": 14572,
  "durationMs": 87,
  "outcome": "success"
}
~~~

Không log password, access token, thông tin thẻ hoặc raw invoice data. Đặt dữ liệu PII và log retention theo chính sách.

### 17.1. Alert gắn với hành động

| Alert | Ví dụ trigger | Runbook |
|---|---|---|
| Error budget fast burn | Vi phạm SLO nhanh theo policy | api-5xx |
| Cloud SQL connection exhaustion | Pending/acquire timeout tăng | db-connection |
| Backup failure | Không có recovery point hợp lệ mới | db-restore |
| PubSub oldest unacked age tăng | Quá data freshness SLO | event-backlog |
| Secret access denied tăng | Sau release/rotation | iam-secret |
| Budget forecast vượt ngưỡng | Anomaly thực tế | cost-review |

Mọi alert cần owner, notification route và bài test giả lập. Alert không có runbook thường tạo nhiễu hơn là tăng độ tin cậy.

## 18. Backup, PITR và DR có bằng chứng

Phân loại dữ liệu:

| Data | Source of truth | Bảo vệ |
|---|---|---|
| Orders, outbox | Cloud SQL | Backups, PITR, restore |
| Invoice binary | Cloud Storage | Soft delete/versioning/retention phù hợp |
| PubSub events | Topic/subscription | Retention/DLQ/replay, outbox |
| IaC state | GCS backend | Versioning, IAM, access recovery |
| Images | Artifact Registry | Digest, retention, rebuild plan |
| Secrets/keys | Secret Manager/Cloud KMS | Backup/access recovery theo policy |
| Docs/runbook | Repo/document store | Versioning và truy cập ngoài failure domain |

**Cloud SQL PITR tạo instance mới**, không trực tiếp sửa instance đang vận hành. Vì thế RTO bao gồm tạo instance, data validation, cập nhật connection/secrets/network, redeploy nếu cần, kiểm tra business flow và chuyển traffic.

### 18.1. Recovery drill

Giả lập lỗi logic lúc 10:00, điểm dữ liệu sạch có thể phục hồi tại 09:55:

1. Chốt UTC incident timestamp và người ra quyết định DR.
2. Khóa writes nếu dữ liệu đang bị hỏng lan rộng.
3. Tạo PITR **instance mới** trong recovery environment.
4. Đối chiếu schema, số order và business checksum.
5. Kết nối ứng dụng test read-only tới database mới.
6. Thử authenticated GET và hành vi nghiệp vụ phù hợp.
7. Ghi kết quả reconciliation và xác nhận dữ liệu outbox/event.
8. Đo actual RPO/RTO, chụp evidence và ghi action items.

\[
RPO_{\text{quan sát}}=10{:}00-09{:}55=5\ \text{phút}
\]

Nếu người dùng phục hồi luồng đặt hàng lúc 11:25 thì RTO đo được = 85 phút. Không dừng đồng hồ tại thời điểm database instance báo Ready.

### 18.2. Zone HA khác region DR

Cloud SQL regional HA có thể giảm downtime khi zone gặp sự cố nhưng **không tự bảo vệ mất cả region**. Nếu N04/N05 áp dụng cho region outage, cần riêng secondary region, data replication/backup, IAM/keys/network/quota và failover drills.

Một tabletop chưa chứng minh RTO thực tế. Nếu chưa diễn tập cross-region thật, ghi rõ **unverified risk** và chủ sở hữu.

## 19. Runbook API 5xx

### Trigger

- Error budget burn hoặc 5xx rate đạt threshold P1/P2.
- User issue đã được xác minh.
- Synthetic checkout fail quá mức chấp nhận.

### Trình tự

1. Mở incident record, ghi UTC bắt đầu, severity, incident commander.
2. Xem Cloud Run revisions vừa deploy, latency, 5xx, SQL connections, PubSub backlog.
3. Kiểm tra IAM denied, Secret Manager access và network egress.
4. Nếu lỗi trùng thời điểm release, xem có thể rollback revision mà không phá schema không.
5. Nếu DB outage, kích hoạt runbook DB thay vì retry storm.
6. Thử business flow tạo/xem order và xác nhận event/invoice.
7. Chỉ giảm severity khi SLI và giao dịch thật phục hồi.
8. Ghi timeline, impact, data reconciliation và postmortem.

Lệnh kiểm tra read-only:

~~~bash
gcloud run services describe shopflow-api \
  --project="$PROJECT_ID" \
  --region="$REGION" \
  --format="yaml(status.url,status.traffic,status.conditions)"

gcloud run revisions list \
  --project="$PROJECT_ID" \
  --region="$REGION" \
  --service=shopflow-api
~~~

Lệnh rollback **có tác động** và chỉ thực hiện sau approval:

~~~bash
gcloud run services update-traffic shopflow-api \
  --project="$PROJECT_ID" \
  --region="$REGION" \
  --to-revisions=KNOWN_GOOD_REVISION=100
~~~

Rollback application revision **không tự rollback schema hoặc dữ liệu**. Nếu đã áp dụng migration không backward-compatible, phải có fix-forward/data recovery plan riêng.

## 20. Phát hành, canary và rollback

~~~mermaid
flowchart LR
    OLD["Revision cũ"]
    NEW["Revision mới"]
    SERVICE["Cloud Run service traffic"]
    CLIENT["Client requests"]
    OLD -->|"95% minh họa"| SERVICE
    NEW -->|"5% minh họa"| SERVICE
    SERVICE --> CLIENT
~~~

Khi canary, so sánh error rate, P95, DB contention, event schema compatibility và tỷ lệ tạo đơn thành công giữa hai revisions. Tăng tỷ lệ chỉ theo policy khi đủ evidence; trả về revision cũ khi metric vượt ngưỡng.

### 20.1. Expand–migrate–contract

Với thay đổi database:

- **Expand:** thêm column/index mà phiên bản cũ vẫn hoạt động.
- **Migrate:** chuyển dữ liệu và deploy code đọc schema mới, không phá old revision.
- **Contract:** chỉ xóa field cũ khi không còn client/revision cần dùng.
- Sao lưu và ghi schema version trước mỗi bước.
- Test rollback từ canary sang code cũ trên database đã expand.

Nếu thay thế hệ thống on-prem có dữ liệu, thêm công việc chuyển dữ liệu (ví dụ DMS đối với PostgreSQL), initial load/CDC, write freeze, đối chiếu và cutover. **Không để source và target cùng nhận writes** nếu không có kiến trúc multi-writer được thiết kế riêng.

## 21. Go/No-Go trước production

| Gate | Go khi | No-Go khi |
|---|---|---|
| Business | Scope/SLO/RPO/RTO đã duyệt | Thiếu owner/acceptance |
| Architecture | ADR/network/data flow có review | Trust boundary không rõ |
| Security | IAM/secret/threat tests PASS | Critical finding |
| Data | Backup/PITR/permission/migrations PASS | Chưa thử restore |
| Functional | Order, authz, outbox và consumer PASS | Lỗi nghiệp vụ quan trọng |
| Performance | P95/5xx/connection budget đạt | Không chịu peak test |
| Operations | Dashboard, alerts, on-call và runbook PASS | Không ai nhận incident |
| FinOps | Budget/quotas/cost owners được duyệt | Vượt ngân sách không có phương án |
| Deployment | Immutable digest và rollback đã thử | Không biết revision tốt |

Mẫu Go/No-Go record:

~~~text
Release: ShopFlow 1.0
Environment: production
Business owner: [approver]
Platform owner: [approver]
DB owner: [approver]
Security: [approver]
Approved image digest: [digest]
Terraform plan: [reference]
Schema migration version: [version]
Go/No-Go timestamp (UTC): [time]
Decision: GO / NO-GO
~~~

Không tự điền GO khi chưa có phê duyệt. Bằng chứng gồm dashboard, test report, IAM diff, DR drill và change ticket.

## 22. Runbook cutover và hypercare

Nếu đây là hệ thống mới không có dữ liệu cũ, cutover chủ yếu là mở traffic. Nếu thay ứng dụng cũ có dữ liệu, cutover còn phải xác định **database primary**, writes và các giao dịch chưa hoàn tất.

### 22.1. Timeline minh họa

| Mốc | Công việc | Owner | Evidence |
|---|---|---|---|
| T-1 ngày | Chốt image digest, Terraform plan, backup, DNS/SSL | Release lead | Approval |
| T-30 phút | Staging health, alerts, dashboard, channel thông báo | SRE | G0–G8 PASS |
| T-10 phút | Dừng source writers/batch nếu chuyển data | Database lead | Không còn writer khác |
| T0 | Promote/cutover database theo runbook nếu cần | Database lead | CDC lag/data validation |
| T+ | Canary frontend/API traffic | Platform | Revision metrics |
| T+ | Smoke test order, tenant auth, outbox, invoice | QA/Business | Business evidence |
| T+ | Theo dõi P95, 5xx, connections, queue và cost | On-call | Dashboard |
| T+N ngày | Kết thúc hypercare, bàn giao và chỉ sau đó decommission | Business/Platform | Sign-off |

Không dùng DNS TTL thấp như một bảo đảm mọi client chuyển ngay lập tức: cache và keep-alive có thể kéo dài. Nếu target đã nhận giao dịch mới, rollback về source cũ mà không đồng bộ ngược sẽ mất dữ liệu. Khi đó ưu tiên fix-forward hoặc reconciliation có phê duyệt.

### 22.2. Hypercare

Trong khoảng 24–72 giờ hoặc theo chính sách được duyệt:

- Theo dõi error rate, P95/P99, số đơn tạo thành công, DB lock/connection và Pub/Sub backlog.
- So sánh baseline với trước migration và theo từng Cloud Run revision.
- Kiểm tra Cloud SQL backup/PITR, object storage và alert notifications.
- Kiểm tra budget/anomaly để phát hiện rollout tạo resource không mong muốn.
- Tổng hợp issue có severity, owner, deadline, khắc phục tạm và root cause.
- Không xóa source/recovery resources khi chưa hết retention và business sign-off.

## 23. FinOps: dự toán, theo dõi và tối ưu chi phí

Một capstone nên có budget approval **trước khi tạo tài nguyên**, không chỉ tổng hợp sau khi nhận hóa đơn.

| Thành phần | Cost drivers | Điểm kiểm soát |
|---|---|---|
| Cloud Run | CPU, memory, requests, min instances, concurrency | Tối ưu sizing/timeout và cache |
| Cloud SQL | Compute tier, HA, storage, backups, PITR logs | Right-size theo P95 và query load |
| Cloud Storage | Stored bytes, operations, retrieval và egress | Lifecycle và retention hợp lệ |
| Pub/Sub | Published/delivered bytes, subscription retention | Payload và retry control |
| Artifact Registry | Storage/transfer | Image retention theo release policy |
| Cloud Build | Build minutes, build pools | Caching và pipeline design |
| Network | Egress, LB/NAT nếu có, region transfer | Co-locate dịch vụ và kiểm tra flow |
| Observability | Log ingestion, custom metrics, trace volume | Sampling, retention, cardinality |
| DR | Backup storage, recovery replicas/drills | Chính sách theo RPO/RTO |

~~~text
Ước tính tháng =
  Cloud Run compute/requests
+ Cloud SQL compute/storage/backup
+ Cloud Storage + Pub/Sub + Artifact Registry
+ Network/LB/NAT
+ CI + Logging/Monitoring + DR
+ các khoản thuế/chiết khấu theo hợp đồng
~~~

Không đưa một số USD giả định vào bảng rồi xem đó là giá hiện tại. Sử dụng Google Cloud Pricing Calculator cho region/tier/requests thật và đối chiếu Cloud Billing Reports theo SKU sau khi chạy staging.

### 23.1. Budget alert không tự chặn chi phí

Thiết lập budget và cảnh báo ví dụ tại 50%, 80%, 100% dự toán; đồng thời phát hiện anomaly khi chi phí bất thường. Budget alert thường chỉ gửi tín hiệu; nếu cần shutdown tự động thì phải thiết kế automation riêng, tránh gây mất dữ liệu hoặc outage production.

### 23.2. Giá trị của labels và ownership

Gắn nhất quán environment, application, team, cost-center và business owner trên các tài nguyên có hỗ trợ. Với shared infrastructure, chọn allocation rule/chargeback được chấp thuận thay vì phân bổ tùy ý toàn bộ phí cho một service.

## 24. Operational handover pack

Nhóm phát triển bàn giao cho SRE/Platform/DBA bằng **hồ sơ có version và liên kết tới bằng chứng thật**:

| Hồ sơ | Nội dung tối thiểu | Người nhận |
|---|---|---|
| H01 – Service catalog | Tên dịch vụ, project, region, URL, owner, tags | SRE |
| H02 – Architecture | Diagram, trust boundary, ADR, flow IDs | SRE/Security |
| H03 – Resource register | IDs, quota, network, IAM, secret references | Platform |
| H04 – Code/deployment | Repo, release manifest, digest, pipeline triggers | DevOps |
| H05 – Data | Schema, migrations, roles, backup retention, PITR | DBA |
| H06 – Observability | Dashboard, SLO, alert rules, escalation | On-call |
| H07 – Runbooks | 5xx, DB outage, Pub/Sub backlog, rollback, restore | Incident commander |
| H08 – Security | Threat model, IAM review, rotation, audit controls | Security |
| H09 – FinOps | Budget, spend baseline, SKU report, optimization backlog | FinOps |
| H10 – Open risks | Known limitations, exception, owner, due date | Business/Platform |
| H11 – DR evidence | Actual RPO/RTO, restore test, remediation | DBA/SRE |
| H12 – Acceptance | Handover training, approvers, support model | Operations lead |

Một link repository chưa đủ. Người nhận phải **truy cập được dashboards, có quyền thực thi runbook đúng scope, biết gọi ai và đã thử ít nhất một tình huống sự cố**.

### 24.1. Bản ghi bàn giao minh họa

~~~yaml
service: shopflow-orders
environment: production
business_owner: commerce-lead
technical_owner: shopflow-team
operations_owner: sre-team
release_digest: REPLACE_WITH_REAL_DIGEST
region: asia-southeast1
rpo_target_minutes: 15
rto_target_minutes: 120
slo_availability: 0.999
dashboards:
  - REPLACE_WITH_REAL_MONITORING_URL
runbooks:
  - api-5xx
  - db-restore
  - event-backlog
last_drill:
  date: null
  actual_rpo_minutes: null
  actual_rto_minutes: null
acceptance:
  security: pending
  data: pending
  operations: pending
  business: pending
~~~

Để null/pending đến khi có kết quả thật. Không tự gán actual RPO/RTO bằng target đã đặt.

## 25. RACI: phân chia trách nhiệm sau ngày bàn giao

RACI gồm Responsible (thực hiện), Accountable (chịu trách nhiệm), Consulted (tham vấn), Informed (nhận thông báo).

| Công việc | Product | App | Platform/SRE | DBA | Security |
|---|---|---|---|---|---|
| Xác định SLO/impact | A | C | R | C | I |
| Release/rollback code | I | A/R | R | C | C |
| Cloud Run/VPC/CI platform | I | C | A/R | I | C |
| Database/schema/backup | I | R | C | A/R | C |
| IAM/secret policy | I | R | R | C | A |
| Incident command | I | R | A/R | R | C |
| Data reconciliation | A | R | C | R | I |
| DR drill | C | R | A/R | R | C |
| Cost review | A | R | R | C | I |

Mẫu này cần được sửa theo tổ chức. Tránh nhiệm vụ không có A hoặc nhiều A mâu thuẫn nhau, nhất là quyền promote DB, emergency rollback và failback.

## 26. Operational Readiness Review (ORR)

Trước khi tiếp nhận dịch vụ, ops team kiểm tra:

| Trục | Câu hỏi | Evidence |
|---|---|---|
| Reproducibility | Có thể dựng lại revision từ image digest được không? | CI/CD replay hoặc deployment record |
| IAM | Các runtime SAs có quyền tối thiểu? | IAM diff + negative test |
| Database | Restore từ PITR có chạy và dữ liệu nhất quán? | Drill report |
| Dependencies | SQL/Secret/PubSub lỗi thì app phản ứng ra sao? | Failure injection test |
| Monitoring | Alert P1 có tới đúng on-call và actionable? | Notification test |
| Rollback | Old revision còn chạy được với schema hiện tại? | Rehearsal |
| Capacity | DB pool có đủ cho autoscaling không? | Load test |
| Cost | Có ai xử lý spend anomalies? | Budget/FinOps plan |
| Documentation | Runbooks đúng với release hiện tại? | Owner review |
| Ownership | Ai phê duyệt failover/decommission? | RACI và escalation |

Một hệ thống có 100% unit tests nhưng chưa restore database lần nào, không có người nhận alert hoặc không biết image digest dùng để rollback vẫn **chưa đạt ORR**.

## 27. Ma trận truy vết yêu cầu – kiểm thử – bằng chứng

| Requirement | Triển khai/kiểm soát | Test ID | Evidence |
|---|---|---|---|
| F01: idempotent order | Unique key + DB transaction | T-API-01 | DB state + test output |
| F03: event publishing | Transactional outbox + Pub/Sub | T-EVT-02 | Duplicate replay |
| N01: P95 API | Cloud Run sizing + Cloud SQL indexing | T-PERF-01 | Trace + load report |
| N02: 99,9% availability | Monitoring SLI/alerts | T-SLO-01 | Dashboard |
| N03: data durability | DB backup/outbox + reconciliation | T-DATA-01 | Consistency report |
| N04: RPO | PITR/backup | T-DR-01 | Recovered timestamp |
| N05: RTO | Restore runbook | T-DR-02 | Incident-like timeline |
| N06: security | IAM matrix/Secret Manager | T-SEC-01 | Permission/scan |
| N08: FinOps | Budget/labels/Billing Reports | T-COST-01 | SKU-level cost baseline |

Khi yêu cầu critical chưa có evidence, phải ghi rõ trạng thái **NOT VERIFIED** hoặc **BLOCKED**, không chuyển ngầm thành PASS.

## 28. Lịch thực hành theo các phiên

| Phiên | Hoạt động | Deliverable |
|---|---|---|
| 1 | Stakeholder workshop, BIA, scope | D01–D02 |
| 2 | ADR/diagram/threat model/cost estimate | D03–D04 |
| 3 | Project/IAM/VPC/Terraform plan | D05–D06 |
| 4 | Cloud SQL/Storage/PubSub và images | D07–D08 |
| 5 | CI, staging deploy, API contract test | D07–D09 |
| 6 | Load/security/failure/restore tests | D08–D09 |
| 7 | Release rehearsal, rollback, Go/No-Go | D10 |
| 8 | SLO dashboards, budget, ORR, handover | D11–D12 |

Đây là **trình tự đào tạo**, không phải lời hứa hoàn thành production trong tám ngày. Quy mô, quota, approvals, migration data và policy có thể kéo dài từng phiên.

## 29. Rubric chấm điểm dự án

| Nhóm | Điểm | Tiêu chí tốt |
|---|---:|---|
| Requirements/traceability | 10 | SLO/RPO/RTO rõ, testable, có owner |
| ADR/architecture/data flow | 15 | Có alternatives, trust boundaries và trade-off |
| IaC/environment separation | 15 | State, plan review, IAM/VPC an toàn |
| App/data correctness | 15 | Idempotency, outbox, data consistency |
| CI/CD/supply chain | 10 | Digest, scan, release approvals |
| Security | 10 | IAM/secret/threat tests có evidence |
| SRE/observability/FinOps | 10 | Alerts/runbooks/budgets actionable |
| DR và handover | 15 | Restore drill, RACI, sign-off |
| **Tổng** | **100** | |

**Điều kiện chặn độc lập với điểm số:** backend public ngoài chủ ý, leak secret, user đọc dữ liệu tenant khác, không có backup/restore evidence, production migration không có rollback/failback an toàn hoặc không có operational owner.

## 30. Checklist nghiệm thu cuối cùng

- [ ] Scope, owners và yêu cầu F/N được phê duyệt.
- [ ] SLO/RTO/RPO, ADR, diagram và traceability đầy đủ.
- [ ] Staging/production tách project, identity, secrets, database và state.
- [ ] Cloud Run backend không cho anonymous invocation.
- [ ] Web→API dùng ID token audience đúng; user-level authorization riêng.
- [ ] Cloud SQL private IP, VPC route/peering và DB least privilege hoạt động.
- [ ] DB pool budget tương thích Cloud Run max instances.
- [ ] API dùng transactional outbox; consumer idempotent.
- [ ] Bucket invoice có IAM, lifecycle và retention theo policy.
- [ ] Terraform plan reviewed, backend state có IAM/versioning.
- [ ] CI có unit/integration/scan; image digest được ghi.
- [ ] Staging performance/security/failure tests PASS.
- [ ] Production canary, rollback và Go/No-Go có approval.
- [ ] SLO dashboards, alerts, log retention và on-call được kiểm thử.
- [ ] PITR/restore drill có actual RPO/RTO và data reconciliation.
- [ ] Budget, cost baseline, labels và cost owner tồn tại.
- [ ] Handover pack, RACI, ORR và operations sign-off hoàn thành.
- [ ] Open risks có owner, deadline hoặc ghi BLOCKER phù hợp.

## 31. Câu hỏi tự kiểm tra

**1. Vì sao phải viết ADR khi đã lựa chọn Cloud Run?**

Vì ADR giải thích bối cảnh, lựa chọn thay thế, đánh đổi và điều kiện cần xem lại. Dịch vụ được chọn phải phù hợp workload, không chỉ do quen công nghệ.

**2. roles/run.invoker của web SA có cho phép xem mọi đơn hàng không?**

Không. IAM xác thực service caller. API vẫn phải xác minh quyền end-user hoặc tenant trên từng order.

**3. Vì sao transactional outbox tốt hơn gọi Pub/Sub ngay sau khi COMMIT đơn hàng?**

Outbox cho phép retry sau khi DB đã ghi thành công mà publish thất bại. Nó không xóa bỏ khả năng event bị gửi trùng; consumer vẫn cần dedupe.

**4. Cloud SQL PITR có nghĩa RTO bằng thời gian nhấn nút Restore không?**

Không. PITR tạo instance mới; phải kiểm tra dữ liệu, quyền, route, cấu hình kết nối, health và business flow trước khi người dùng sử dụng trở lại.

**5. Tại sao cần tính Cloud Run instances × DB pool size?**

Vì mỗi instance có pool riêng; tổng kết nối có thể vượt Cloud SQL capacity khi autoscaling, gây timeout dù Cloud Run CPU còn thấp.

**6. Khi nào rollback revision không đủ?**

Khi database schema/dữ liệu đã thay đổi không tương thích với code cũ, hoặc target DB đã nhận writes sau migration. Khi đó cần forward fix, data reconciliation hoặc recovery plan riêng.

**7. Vì sao build thành công vẫn chưa được nhận bàn giao vận hành?**

Vì thiếu restore drill, on-call alerts, runbook, ngân sách, owner và test evidence có thể khiến incident thực tế không thể giải quyết.

**8. Có thể decommission hệ thống nguồn ngay sau cutover không?**

Không. Chỉ sau hypercare, business sign-off, backup/retention và xác nhận không còn dependencies hoặc dữ liệu cần reconciliation.

## 32. Tài liệu tham khảo

- [Google Cloud Architecture Framework](https://cloud.google.com/architecture/framework)
- [Cloud Run overview](https://cloud.google.com/run/docs/overview/what-is-cloud-run)
- [Cloud Run Direct VPC egress](https://cloud.google.com/run/docs/configuring/vpc-direct-vpc)
- [Cloud Run service-to-service authentication](https://cloud.google.com/run/docs/authenticating/service-to-service)
- [Cloud Run rollouts, rollbacks and traffic migration](https://cloud.google.com/run/docs/rollouts-rollbacks-traffic-migration)
- [Cloud SQL: connect from Cloud Run](https://cloud.google.com/sql/docs/postgres/connect-run)
- [Cloud SQL: private IP](https://cloud.google.com/sql/docs/postgres/configure-private-ip)
- [Cloud SQL: PITR](https://cloud.google.com/sql/docs/postgres/backup-recovery/pitr)
- [Cloud SQL: backup and recovery](https://cloud.google.com/sql/docs/postgres/backup-recovery/backups)
- [Secret Manager documentation](https://cloud.google.com/secret-manager/docs/overview)
- [Cloud Storage soft delete](https://cloud.google.com/storage/docs/soft-delete)
- [Pub/Sub: subscriber guide](https://cloud.google.com/pubsub/docs/subscriber)
- [Cloud Build: deploy to Cloud Run](https://cloud.google.com/build/docs/deploying-builds/deploy-cloud-run)
- [Cloud Deploy overview](https://cloud.google.com/deploy/docs/overview)
- [Artifact Registry](https://cloud.google.com/artifact-registry/docs/overview)
- [Terraform on Google Cloud](https://cloud.google.com/docs/terraform)
- [Google Cloud SLO monitoring](https://cloud.google.com/stackdriver/docs/solutions/slo-monitoring)
- [Cloud Billing Reports](https://cloud.google.com/billing/docs/how-to/reports)
- [Cloud Billing budgets and alerts](https://cloud.google.com/billing/docs/how-to/manage-budgets)



