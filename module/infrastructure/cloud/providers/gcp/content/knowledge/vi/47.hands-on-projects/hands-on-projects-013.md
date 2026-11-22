# Dự án diễn tập failover và khôi phục dữ liệu GCP

Một hệ thống thương mại điện tử có thể chạy ổn định trong nhiều tháng nhưng ngừng nhận đơn hàng khi database mất kết nối, một zone bị lỗi hoặc một thao tác triển khai làm hỏng dữ liệu. Để chứng minh khả năng phục hồi, nhóm vận hành cần nhiều hơn một checkbox “đã bật backup”: phải biết **khi nào chuyển sang vùng dự phòng, cách không tạo hai điểm ghi độc lập, bản sao có thể mất bao nhiêu dữ liệu và làm thế nào kiểm tra dịch vụ thật sự hoạt động trở lại**.

Dự án này hướng dẫn xây dựng một ứng dụng thử nghiệm **Java 21 + Spring Boot trên Cloud Run**, lưu đơn hàng giả trong **Cloud SQL for PostgreSQL**; triển khai instance chính ở region A và read replica bất đồng bộ ở region B. Người học lần lượt thực hành **failover trong region bằng Cloud SQL HA**, **chuyển sang region khác bằng cách promote replica**, **phục hồi dữ liệu bằng Point-in-Time Recovery (PITR)** và **khôi phục object nhờ Cloud Storage soft delete**. Tất cả bài diễn tập đều yêu cầu ghi nhận mốc thời gian, RPO/RTO và bằng chứng.

Đây là bài thuộc chương **Dự án thực hành GCP** của module **CLOUD_PROVIDERS_GCP**. Module khám phá Google Cloud từ tổ chức project, IAM, VPC đến Compute Engine, GKE, Cloud Run, dịch vụ lưu trữ và cơ sở dữ liệu; qua các tình huống triển khai, người học biết lựa chọn dịch vụ, bảo vệ tài nguyên, tự động hóa phát hành và theo dõi độ tin cậy cùng chi phí. Bài này tổng hợp kiến thức đó thành một DR drill có phương án cutover, xác minh, dọn tài nguyên và báo cáo.

> **An toàn:** Đây là thiết kế **staging/lab**. Việc promote read replica, chuyển database writer, thay traffic, xóa dữ liệu hoặc tạo PITR clone có thể gián đoạn dịch vụ và tốn chi phí. Không chạy lệnh có tác động trên production, không diễn tập bằng cách gây outage thực tế cho một region và không thực hiện xóa dữ liệu ngoài tài nguyên giả lập được sở hữu. Quy trình thực tế phải có Incident Commander, Security, DBA và người phê duyệt thay đổi.

## Mục tiêu và sản phẩm cần nộp

Sau dự án, bạn phải giải thích và chứng minh được:

- Sự khác nhau giữa **HA trong một region**, **DR sang region khác**, **backup/restore** và **PITR khôi phục thao tác ghi sai**.
- Vì sao Cloud SQL cross-region read replica **không tự động failover** theo mô hình cơ bản và vì sao sao chép bất đồng bộ có thể mất dữ liệu.
- Cách dựng Cloud Run cùng image ở hai region, đặt guard để chỉ có một writer và chuyển cấu hình kết nối sau promotion.
- Cách kiểm chứng replica lag, bảo toàn dữ liệu giả, chạy smoke test và quyết định mở traffic.
- Cách mô phỏng mất dữ liệu để khôi phục bằng PITR hoặc Cloud Storage soft delete.
- Cách xác định RTO/RPO theo timestamp thật, không suy ra từ việc lệnh trả về thành công.
- Cách viết runbook, ghi log, chi phí, hoàn nguyên và xử lý phần dữ liệu chưa đồng bộ.

**Bộ nộp bài:** sơ đồ kiến trúc, bảng giả định, cấu hình source/image, bản ghi các bước diễn tập, bảng before/after dữ liệu, RPO/RTO thực đo, checklist bảo mật và kế hoạch failback/cleanup. Không nộp password, token hoặc thông tin khách hàng.

## 1. Mô hình giả định và yêu cầu phi chức năng

Ứng dụng demo tên `dr-orders` lưu ba trường: `id` dạng UUID, `amount` nguyên dương và `created_at`. Client có thể tạo và tra cứu đơn hàng. Mỗi đơn dùng ID do client gửi để chống ghi trùng khi retry. Trong lab không có thanh toán hay dữ liệu khách hàng thật.

| Yêu cầu | Mục tiêu giả định | Cách kiểm chứng |
|---|---|---|
| Business journey | POST đơn → đọc lại bằng GET | So sánh ID/amount trước và sau drill |
| Normal availability | Mục tiêu 99,9% mỗi tháng | Thiết lập SLI, không nhầm với SLA của GCP |
| DR RTO | Không quá 45 phút | Thời điểm bắt đầu sự cố mô phỏng đến khi POST/GET thành công |
| DR RPO | Không quá 5 phút | Mốc write cuối trên primary so với write đã có trên standby |
| Data recovery | Khôi phục trước thao tác làm hỏng dữ liệu | PITR clone và đối soát row |
| Isolation | Staging project riêng, dữ liệu giả | IAM, billing và inventory |
| Write safety | Tại một thời điểm chỉ một database được ứng dụng ghi | Guard và traffic/DB fencing |
| Security | Secret Manager, runtime SA, IAM invoker | Kiểm tra quyền và Cloud Audit Logs |
| Cost | Có dự toán, budget alert và kế hoạch dọn | Báo cáo Billing theo SKU |

Các giá trị RTO/RPO là **mục tiêu của bài thực hành**, không phải lời hứa Cloud SQL replication hay Cloud Run tự bảo đảm. Đặc biệt, replication bất đồng bộ không cam kết RPO=0 khi vùng primary bất ngờ mất liên lạc.

### 1.1. Phạm vi kiểm thử

Dự án có bốn bài diễn tập tách biệt:

1. **Zonal HA:** kích hoạt test failover một Cloud SQL HA instance trong cùng region; application connection name thường không đổi.
2. **Regional DR:** ngăn write vào A, đánh giá lag, **promote** read replica B, cập nhật Cloud Run B để ghi vào B, chuyển client.
3. **Logical recovery:** trên một primary còn có PITR window, mô phỏng sửa sai một row rồi tạo PITR clone vào **instance mới**.
4. **Object recovery:** trên bucket lab, xóa một object giả, tìm generation soft-deleted rồi restore.

Không nhất thiết chạy bốn bài trong một buổi hoặc trên cùng một instance; **PITR nên thực hiện trước bài promote hoặc trên một primary khác đã có backup/PITR sẵn**, tránh nhầm rằng instance vừa promote lập tức có đủ lịch sử PITR.

## 2. Kiến trúc lab: active/standby, một writer

| Thành phần | Region A | Region B |
|---|---|---|
| Cloud Run | `dr-orders` revision active | `dr-orders` revision standby, cùng image |
| Cloud SQL | `dr-pg-primary`, PostgreSQL HA | `dr-pg-replica`, cross-region read replica |
| Ứng dụng | `APP_WRITES_ENABLED=true` | `APP_WRITES_ENABLED=false` |
| Connection | A → primary A | B → primary A lúc đầu; đổi sang B sau promotion |
| Client | Gọi URL của Cloud Run A | Chỉ chuyển sang B sau khi đạt release gates |
| Backup/restore | Automated backup + PITR | Replica không thay thế backup/PITR |
| Monitoring | Metrics và logs của A | Metrics và logs của B |

~~~mermaid
flowchart TD
    C["Client / điều phối traffic"] -->|"Bình thường"| RA["Cloud Run A: writer"]
    C -.->|"Chỉ sau DR cutover"| RB["Cloud Run B: standby"]
    RA -->|"JDBC + Cloud SQL Connector"| DBA[("Cloud SQL A: primary HA")]
    RB -.->|"Lúc đầu trỏ A, write guard OFF"| DBA
    DBA -->|"Asynchronous replication"| DBB[("Cloud SQL B: read replica")]
    RB -->|"Sau promotion: đổi connection + bật write"| DBB
    DBA --> BK["Backups + PITR logs"]
    RA --> OBS["Cloud Logging / Monitoring"]
    RB --> OBS
    DBB --> OBS
    BK -.->|"Restore vào instance riêng"| REC[("PITR recovery instance")]
~~~

**Điểm kiểm soát quan trọng:** hai Cloud Run services tồn tại ở hai region **không có nghĩa database đã hỗ trợ multi-region automatic failover**. Không chuyển client sang B khi B vẫn trỏ primary A đang unavailable. Trước khi B bắt đầu ghi, phải có **fencing** đối với A: đóng/giảm luồng request tới writer cũ, xác nhận các request cũ đã drain và kiểm soát khả năng A nhận write khi quay lại.

Một công tắc môi trường `APP_WRITES_ENABLED=false` giúp **diễn tập trong trạng thái A còn hoạt động**; đây chưa phải fencing mạnh cho một region outage thật, vì khi A mất liên lạc ta có thể không đổi được cấu hình A. Production cần kết hợp traffic routing/fencing, quyền và thủ tục khôi phục primary cũ để không sinh **split brain**. Không có chủ trương ghi đồng thời vào cả hai primary độc lập.

### 2.1. Phương án định tuyến traffic

Để giữ lab dễ kiểm tra, dùng **manual URL cutover**: client test gọi URL A trước sự cố và URL B sau khi DR đã đạt điều kiện. Đây là mô phỏng chuyển hướng, không phải global failover tự động.

Trong production có thể dùng global external Application Load Balancer kết hợp regional serverless NEGs và Cloud Run service health hoặc cơ chế failover thích hợp. **Chỉ triển khai Cloud Run hai region sau một load balancer chưa tự bảo đảm tự chuyển traffic khi region gặp lỗi**. Nếu dùng manual failover, thao tác thay đổi backend/URL map và kiểm tra kết quả phải nằm trong runbook được duyệt.

## 3. Chuẩn bị và các lớp chi phí

### 3.1. Điều kiện đầu vào

- Google Cloud project **chuyên dùng cho lab**, đã bật billing; không sử dụng production.
- Người vận hành có quyền bootstrap về Cloud SQL, Cloud Run, Artifact Registry, Secret Manager, IAM và Cloud Storage.
- Có gcloud CLI, Java 21, Maven, Git và quyền xem Cloud Monitoring/Logging.
- Đã chọn hai region có hỗ trợ Cloud SQL PostgreSQL, Cloud Run và các machine types cần dùng.
- Có budget alert và dự toán chi phí; một Cloud SQL HA + cross-region replica thường **đắt hơn nhiều** một lab Cloud Run thuần túy.
- Có người được chỉ định approve promotion, PITR clone, thay đổi writer và xóa resource sau lab.

Ví dụ đặt biến trong Cloud Shell/Linux:

~~~bash
export PROJECT_ID="YOUR-DR-LAB-PROJECT"
export REGION_A="asia-southeast1"
export REGION_B="asia-southeast2"
export PRIMARY="dr-pg-primary"
export REPLICA="dr-pg-replica"
export DB_NAME="orders"
export SERVICE="dr-orders"
export REPO="dr-lab"
export IMAGE="${REGION_A}-docker.pkg.dev/${PROJECT_ID}/${REPO}/dr-orders:v1"

gcloud config set project "${PROJECT_ID}"
gcloud config get-value project
gcloud auth list
~~~

Các region chỉ là ví dụ. Kiểm tra chính sách residency, quotas, VPC, latency và pricing trước khi tạo dữ liệu. Nếu tài khoản chỉ có quyền đọc, thực hiện phần **tabletop** thay vì bỏ qua kiểm soát để xin Editor/Owner.

### 3.2. Bật API

~~~bash
gcloud services enable \
  run.googleapis.com \
  sqladmin.googleapis.com \
  cloudbuild.googleapis.com \
  artifactregistry.googleapis.com \
  secretmanager.googleapis.com \
  storage.googleapis.com \
  monitoring.googleapis.com \
  logging.googleapis.com \
  --project="${PROJECT_ID}"
~~~

Các dịch vụ có thể cần thiết lập bổ sung tùy cách đóng gói ứng dụng và tổ chức. Việc bật API/trao IAM nên do quản trị viên hoặc pipeline IaC có quyền đã phê duyệt thực hiện.

### 3.3. Danh sách chi phí cần dự toán

| Nguồn phí | Vì sao phát sinh ngay cả khi ít request? | Cách kiểm soát |
|---|---|---|
| Cloud SQL HA A | Compute, HA standby, storage, backups | Giới hạn thời gian lab, size phù hợp |
| Cloud SQL replica B | Instance luôn phục vụ replication, storage | Không để replica lab tồn tại vô thời hạn |
| Cloud Run A/B | Request, CPU/memory, min instances nếu có | Min instances=0 ở bài học khi chấp nhận cold start |
| Cross-region replication | Network transfer tùy pricing và dữ liệu | Dữ liệu test nhỏ, quan sát egress |
| Cloud Storage | Object, soft-delete retention, operations | Bucket lab, TTL, dọn có chủ đích |
| Cloud Build/Artifact Registry | Build-minutes và image storage | Build một lần, reuse image digest |
| Logging/Monitoring | Volume/retention của log và metric | Log có cấu trúc, tránh spam |
| PITR clone | **Instance mới** và storage riêng | Xóa sau khi đối soát, bảo vệ bằng approval |

Cloud Billing **budget alert không phải spending cap**. Có thể giảm chi phí bằng chế độ **tabletop chỉ đọc**, không tạo Cloud SQL replica thật. Phần hands-on dùng tài nguyên thật chỉ thực hiện khi ngân sách và quyền đã sẵn sàng.

## 4. Quy trình quyết định trước mỗi thao tác

Mỗi hành động liên quan đến dữ liệu hoặc route cần có một dòng nhật ký:

| Trường | Ví dụ |
|---|---|
| Drill ID | `DRILL-2026-11-LAB` |
| Change owner | SRE on-call |
| Data owner | Nhóm Orders |
| Security reviewer | Security engineer |
| Test start time | UTC timestamp |
| Baseline | Image digest, instance IDs, row IDs, LSN/lag |
| RPO/RTO goals | 5 phút / 45 phút |
| Action gate | Điều kiện đạt, người phê duyệt |
| Recovery target | Region B hoặc PITR instance mới |
| Fencing | Writer cũ đã dừng và không còn traffic |
| Rollback plan | Quay về trạng thái an toàn đã định nghĩa |

**Không đồng nhất “gcloud hoàn thành” với “dịch vụ phục hồi”.** Cutover thành công phải kiểm tra write/read end-to-end, độ đúng dữ liệu, IAM, network, latency, logging và khả năng backup tiếp tục hoạt động.

## 5. Tạo Cloud SQL PostgreSQL và bảo vệ dữ liệu

### 5.1. Primary A với HA và PITR

Ví dụ dưới đây dùng PostgreSQL 16 Enterprise, hai vCPU, HA trong region. **Lệnh này tạo tài nguyên có phí**; phải kiểm tra hợp lệ của machine type/region/edition và quota:

~~~bash
# CHỈ LAB CÓ BILLING/BUDGET VÀ APPROVAL.
gcloud sql instances create "${PRIMARY}" \
  --project="${PROJECT_ID}" \
  --region="${REGION_A}" \
  --database-version=POSTGRES_16 \
  --edition=ENTERPRISE \
  --cpu=2 \
  --memory=7680MB \
  --storage-type=SSD \
  --storage-size=20 \
  --availability-type=REGIONAL \
  --backup-start-time=03:00 \
  --enable-point-in-time-recovery \
  --retained-backups-count=7 \
  --deletion-protection
~~~

Những điểm cần xác nhận sau khi tạo:

~~~bash
gcloud sql instances describe "${PRIMARY}" \
  --project="${PROJECT_ID}" \
  --format="yaml(name,region,databaseVersion,settings.availabilityType,settings.backupConfiguration,connectionName)"

gcloud sql operations list \
  --instance="${PRIMARY}" \
  --project="${PROJECT_ID}"
~~~

- `REGIONAL` cho HA giữa hai **zone trong một region**, không phải DR giữa hai region.
- `--enable-point-in-time-recovery` cần bật rõ cho nhiều phương án tạo instance qua gcloud; không giả định luôn bật.
- PITR phải có backup/log history còn trong window và một recovery point hợp lệ.
- `--deletion-protection` là lớp ngăn xóa instance ngoài ý muốn; nó **không thay thế backup**.
- Mô hình private IP/PSC, Cloud KMS CMEK, firewall hoặc org policies có thể yêu cầu flags và thiết kế khác. Mẫu này dùng Cloud SQL Connector và instance connection name, không mô tả toàn bộ mạng production.

### 5.2. Tạo database và user theo quyền tối thiểu

~~~bash
gcloud sql databases create "${DB_NAME}" \
  --instance="${PRIMARY}" \
  --project="${PROJECT_ID}"
~~~

Trong **Cloud SQL Console → primary → Users**, tạo user `dr_app` với mật khẩu ngẫu nhiên mạnh, gắn database role phù hợp. Tránh đưa password vào tham số `--password=...` trên terminal dùng chung vì có thể lộ trong shell history/process arguments.

Ở **Cloud SQL Studio** hoặc phiên `psql` xác thực do DBA quản lý, chạy DDL trong database `orders`:

~~~sql
CREATE TABLE IF NOT EXISTS dr_orders (
  id UUID PRIMARY KEY,
  amount INTEGER NOT NULL CHECK (amount > 0),
  created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Trong production, role DDL và DML nên tách.
-- Chỉ cấp quyền cần thiết cho user ứng dụng.
GRANT SELECT, INSERT, UPDATE ON TABLE dr_orders TO dr_app;
~~~

Quyền database là lớp **PostgreSQL** riêng với IAM `roles/cloudsql.client` dùng kết nối Cloud SQL. Trong lab, tùy cách tạo user, hệ thống có thể gán role rộng hơn cần thiết; cần review và thu hẹp trước khi coi đây là production baseline. Không cho Cloud Run tự chạy DDL khi khởi động; điều đó giúp standby không vô tình ghi vào primary.

### 5.3. Secret Manager và service account

Đưa mật khẩu vào Secret Manager bằng quy trình được bảo vệ, qua Console hoặc CLI không hiển thị secret vào logs. Trong ví dụ, secret ID là `dr-db-password`. Nếu tạo từ Console, chọn replication phù hợp với data residency; nếu tạo bằng CLI thì không lưu plaintext vào repository.

~~~bash
gcloud iam service-accounts create dr-runtime \
  --project="${PROJECT_ID}" \
  --display-name="DR lab Cloud Run runtime"

export RUNTIME_SA="dr-runtime@${PROJECT_ID}.iam.gserviceaccount.com"

gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
  --member="serviceAccount:${RUNTIME_SA}" \
  --role="roles/cloudsql.client"

gcloud secrets add-iam-policy-binding dr-db-password \
  --project="${PROJECT_ID}" \
  --member="serviceAccount:${RUNTIME_SA}" \
  --role="roles/secretmanager.secretAccessor"
~~~

Lệnh trên yêu cầu secret đã tồn tại. Sử dụng **user-managed runtime SA** thay vì cấp quyền cho default Compute Engine service account. Danh tính deployer cần riêng quyền deploy và quyền actAs runtime SA; tránh dùng Owner hoặc JSON key tĩnh.

## 6. Tạo read replica ở region B

Cloud SQL read replica ở region khác là một **bản sao bất đồng bộ**. Nó chỉ đọc cho đến khi được promote. Replica không tự động trở thành primary khi region A down trong mô hình cơ bản.

~~~bash
# CHỈ LAB: tạo cross-region replica tốn chi phí liên tục.
gcloud sql instances create "${REPLICA}" \
  --master-instance-name="${PRIMARY}" \
  --project="${PROJECT_ID}" \
  --region="${REGION_B}" \
  --availability-type=ZONAL
~~~

`ZONAL` cho replica ở lab nhằm giảm cấu hình so với HA B, không phải khuyến nghị DR production. Với hệ thống quan trọng, xem xét **HA ở region dự phòng**, right-sizing đủ tải, capacity/quota, private connectivity và chính sách backup của primary mới sau promotion.

Xác minh:

~~~bash
gcloud sql instances describe "${REPLICA}" \
  --project="${PROJECT_ID}" \
  --format="yaml(name,region,state,masterInstanceName,replicaConfiguration,connectionName)"

gcloud sql instances list \
  --project="${PROJECT_ID}"
~~~

Để đánh giá sức khỏe replication, xem Cloud SQL → replica → Monitoring với **Replication state** và **Lag Bytes** cùng metrics liên quan. Đừng chỉ nhìn instance status `RUNNABLE` để khẳng định mọi write đã replay xong. Thời điểm đầu replica vừa tạo cần đợi đồng bộ cơ sở dữ liệu ban đầu hoàn tất.

### 6.1. Đặc điểm quyền và kết nối

Replica có connection name **khác** primary vì khác region/instance. Ứng dụng B lúc đầu **trỏ primary A và vô hiệu hóa ghi**, vì vậy B chỉ là container standby. Sau promotion, việc cấu hình lại Cloud Run B và chấp thuận route là các thao tác DR riêng.

Nếu ứng dụng B trước promotion kết nối trực tiếp read replica B, các lệnh `INSERT/UPDATE` sẽ bị PostgreSQL từ chối vì read-only. Một readiness check có thao tác ghi cũng sẽ fail. Trong bài thực hành này, chúng ta chủ ý không dùng replica B làm writer trước promotion.

## 7. Tạo ứng dụng Java/Spring Boot nhỏ để quan sát dữ liệu

Ứng dụng demo có ba endpoint:

| Endpoint | Vai trò | Bảo đảm |
|---|---|---|
| `GET /ready` | Kiểm tra kết nối DB bằng query `SELECT 1` | Khác với kiểm tra rằng toàn hệ thống không mất dữ liệu |
| `POST /orders` | Ghi một đơn hàng có idempotency key | Bị từ chối khi `APP_WRITES_ENABLED=false` |
| `GET /orders/{id}` | Đọc lại đơn hàng theo UUID | Dùng để đối soát trước/sau promotion |
| `GET /whoami` | Xem label region và chế độ writer | Không phải nguồn chân lý của cloud routing |

Tạo cây thư mục ví dụ ở project học viên (không cần tạo trong kho tài liệu knowledge):

~~~text
dr-orders/
├── pom.xml
├── Dockerfile
└── src/main/
    ├── java/lab/dr/
    │   └── DrOrdersApplication.java
    └── resources/
        └── application.yml
~~~

### 7.1. Maven pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.5.7</version>
    <relativePath/>
  </parent>
  <groupId>lab.dr</groupId>
  <artifactId>dr-orders</artifactId>
  <version>0.0.1</version>
  <properties>
    <java.version>21</java.version>
  </properties>
  <dependencies>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-jdbc</artifactId>
    </dependency>
    <dependency>
      <groupId>org.postgresql</groupId>
      <artifactId>postgresql</artifactId>
    </dependency>
    <dependency>
      <groupId>com.google.cloud.sql</groupId>
      <artifactId>postgres-socket-factory</artifactId>
      <version>1.30.0</version>
    </dependency>
  </dependencies>
  <build>
    <plugins>
      <plugin>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-maven-plugin</artifactId>
      </plugin>
    </plugins>
  </build>
</project>
~~~

Ví dụ dùng một phiên bản Spring Boot 3.5.x và Cloud SQL JDBC Socket Factory đã công bố; khi làm thật, kiểm tra tương thích JVM/dependency, quét lỗ hổng và pin bản cập nhật bảo mật thích hợp.

### 7.2. Spring Boot application.yml

~~~yaml
server:
  port: ${PORT:8080}
spring:
  datasource:
    url: "jdbc:postgresql:///orders?cloudSqlInstance=${DB_INSTANCE_CONNECTION_NAME}&socketFactory=com.google.cloud.sql.postgres.SocketFactory"
    username: "${DB_USER:dr_app}"
    password: "${DB_PASSWORD}"
    hikari:
      maximum-pool-size: 4
      connection-timeout: 5000
      minimum-idle: 0
  sql:
    init:
      mode: never
~~~

Cloud SQL JDBC Socket Factory giúp ứng dụng xác thực với Cloud SQL bằng ADC của service account và khởi tạo kết nối an toàn; **nó không thay thế database username/password hoặc IAM của PostgreSQL** trong ví dụ này. Không đưa secret vào code, Docker image hoặc log.

Công thức ước tính kết nối tối đa cần xem xét:

~~~text
Số kết nối ứng dụng đến DB có thể lên tới:
  max_instances_Cloud_Run × maximumPoolSize_mỗi_instance
  + kết nối admin / background workers / công cụ khác
~~~

Dùng `--max-instances=5` và pool 4 chỉ là giới hạn thiết kế **tối đa xấp xỉ 20 connection từ pool nếu mỗi instance đạt kích thước pool**; không bảo đảm tuyệt đối không tăng ngoài dự kiến do biến động scaling/revision và clients khác. Khi region B được bật làm writer, phải kiểm tra giới hạn DB ở B.

### 7.3. Java controller và write guard

~~~java
package lab.dr;

import java.util.List;
import java.util.Map;
import java.util.UUID;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.ResponseEntity;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.web.bind.annotation.*;

@SpringBootApplication
public class DrOrdersApplication {
    public static void main(String[] args) {
        SpringApplication.run(DrOrdersApplication.class, args);
    }
}

@RestController
class OrdersController {
    private final JdbcTemplate jdbc;

    @Value("${APP_WRITES_ENABLED:false}")
    private boolean writesEnabled;

    @Value("${REGION_LABEL:unknown}")
    private String region;

    OrdersController(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    record OrderRequest(String id, int amount) {}

    @GetMapping("/whoami")
    Map<String, Object> whoami() {
        return Map.of("region", region,
                      "writesEnabled", writesEnabled);
    }

    @GetMapping("/ready")
    Map<String, Object> ready() {
        Integer one = jdbc.queryForObject("SELECT 1", Integer.class);
        return Map.of("db", one == 1 ? "reachable" : "unexpected",
                      "region", region);
    }

    @PostMapping("/orders")
    ResponseEntity<Map<String, Object>> create(
            @RequestBody OrderRequest order) {
        if (!writesEnabled) {
            return ResponseEntity.status(503)
                .body(Map.of("error", "standby_writer_disabled"));
        }

        if (order == null || order.id() == null || order.amount() <= 0) {
            return ResponseEntity.badRequest()
                .body(Map.of("error", "invalid_order"));
        }

        final UUID id;
        try {
            id = UUID.fromString(order.id());
        } catch (IllegalArgumentException e) {
            return ResponseEntity.badRequest()
                .body(Map.of("error", "invalid_uuid"));
        }

        int inserted = jdbc.update(
            "INSERT INTO dr_orders(id, amount) VALUES (?, ?) "
                + "ON CONFLICT (id) DO NOTHING",
            id, order.amount());

        // Replay cùng id không ghi thêm một bản ghi.
        return ResponseEntity.status(inserted == 1 ? 201 : 200)
            .body(Map.of("id", id.toString(),
                         "created", inserted == 1,
                         "region", region));
    }

    @GetMapping("/orders/{id}")
    ResponseEntity<?> get(@PathVariable String id) {
        final UUID uuid;
        try {
            uuid = UUID.fromString(id);
        } catch (IllegalArgumentException e) {
            return ResponseEntity.badRequest()
                .body(Map.of("error", "invalid_uuid"));
        }

        List<Map<String, Object>> rows = jdbc.queryForList(
            "SELECT id::text AS id, amount, created_at "
                + "FROM dr_orders WHERE id = ?",
            uuid);

        return rows.isEmpty()
            ? ResponseEntity.notFound().build()
            : ResponseEntity.ok(rows.get(0));
    }
}
~~~

**Giới hạn của demo:**

- Check `APP_WRITES_ENABLED` chỉ nằm trong application revision, không phải distributed lease hay fencing token. Trong sự cố thật cần đảm bảo mọi writer cũ bị vô hiệu hóa và không tự ghi lại khi region A hồi phục.
- Câu lệnh `ON CONFLICT DO NOTHING` ngăn insert hai lần theo ID, nhưng client gửi cùng ID với nội dung khác cần được phát hiện ở ứng dụng production. Bài này chỉ tập trung vào khả năng phục hồi.
- Endpoint `GET /ready` chỉ chứng minh truy vấn cơ bản thành công; để đánh giá cutover phải kiểm chứng cả một POST và GET của cùng record, permissions và business invariants.
- Demo không có thanh toán, Pub/Sub, cache hay schema migration phức tạp. Hệ thống thực cần runbook riêng cho các dependency đó.
- Với workload nhiều traffic, cần authentication/authorization của khách hàng ở cấp ứng dụng và idempotency key có retention phù hợp; Cloud Run IAM chỉ bảo vệ người gọi trong lab.

### 7.4. Dockerfile và build image một lần

~~~dockerfile
FROM maven:3.9-eclipse-temurin-21 AS build
WORKDIR /src
COPY pom.xml .
COPY src ./src
RUN mvn -B -ntp -DskipTests package

FROM eclipse-temurin:21-jre
WORKDIR /app
COPY --from=build /src/target/dr-orders-0.0.1.jar /app/app.jar
EXPOSE 8080
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
~~~

Tạo Artifact Registry:

~~~bash
gcloud artifacts repositories create "${REPO}" \
  --location="${REGION_A}" \
  --repository-format=docker \
  --project="${PROJECT_ID}"

# Chỉ thực hiện trong thư mục dr-orders của project lab.
gcloud builds submit \
  --project="${PROJECT_ID}" \
  --tag="${IMAGE}" .
~~~

Image được build một lần, sau đó deploy **cùng một image digest** sang A và B nếu cơ chế Artifact Registry/repository location và permissions cho phép pull cross-region. Sau build, lấy digest thực tế từ Artifact Registry hoặc build result; trong production nên pin bằng `@sha256:...` để loại rủi ro tag bị ghi đè. Việc dùng tag `v1` trong lab chỉ để đơn giản hóa minh họa.

## 8. Deploy Cloud Run A và B có giới hạn quyền

### 8.1. Cloud Run A làm writer

~~~bash
export CONN_A="${PROJECT_ID}:${REGION_A}:${PRIMARY}"

gcloud run deploy "${SERVICE}" \
  --project="${PROJECT_ID}" \
  --region="${REGION_A}" \
  --image="${IMAGE}" \
  --service-account="${RUNTIME_SA}" \
  --add-cloudsql-instances="${CONN_A}" \
  --set-env-vars="DB_INSTANCE_CONNECTION_NAME=${CONN_A},DB_USER=dr_app,APP_WRITES_ENABLED=true,REGION_LABEL=${REGION_A}" \
  --set-secrets="DB_PASSWORD=dr-db-password:latest" \
  --max-instances=5 \
  --min-instances=0 \
  --memory=512Mi \
  --no-allow-unauthenticated
~~~

Mọi kết nối database đi qua Cloud SQL Connector dùng runtime SA; secret chỉ truyền ở runtime. Người gọi dịch vụ phải có `roles/run.invoker` phù hợp để gọi endpoint bằng ID token.

### 8.2. Cloud Run B ở chế độ standby

~~~bash
gcloud run deploy "${SERVICE}" \
  --project="${PROJECT_ID}" \
  --region="${REGION_B}" \
  --image="${IMAGE}" \
  --service-account="${RUNTIME_SA}" \
  --add-cloudsql-instances="${CONN_A}" \
  --set-env-vars="DB_INSTANCE_CONNECTION_NAME=${CONN_A},DB_USER=dr_app,APP_WRITES_ENABLED=false,REGION_LABEL=${REGION_B}" \
  --set-secrets="DB_PASSWORD=dr-db-password:latest" \
  --max-instances=5 \
  --min-instances=0 \
  --memory=512Mi \
  --no-allow-unauthenticated
~~~

Ban đầu **B trỏ cùng database primary A**, nhưng guard tắt ghi. Điều này giúp so sánh readiness ở hai vùng khi primary khỏe. Khi primary A mất, B cũng mất khả năng DB read/write **cho đến khi promote replica và cập nhật connection name**; B không phải standby database tự hoàn chỉnh trước lúc đó.

Nếu muốn warm container luôn sống trong B, cấu hình `min-instances` lớn hơn 0 và đánh giá chi phí. Bản lab dùng 0 để giảm phí khi không có request; cold start có thể kéo dài RTO thực đo.

### 8.3. Lấy URL và kiểm tra danh tính

~~~bash
export URL_A="$(gcloud run services describe "${SERVICE}" \
  --project="${PROJECT_ID}" --region="${REGION_A}" \
  --format='value(status.url)')"

export URL_B="$(gcloud run services describe "${SERVICE}" \
  --project="${PROJECT_ID}" --region="${REGION_B}" \
  --format='value(status.url)')"

printf "A=%s\nB=%s\n" "${URL_A}" "${URL_B}"
~~~

Tài khoản đang thử nghiệm phải được cấp quyền invoker cho **cả** dịch vụ A và B:

~~~bash
# Quản trị viên lab áp dụng cho người kiểm thử được phê duyệt.
gcloud run services add-iam-policy-binding "${SERVICE}" \
  --project="${PROJECT_ID}" \
  --region="${REGION_A}" \
  --member="user:APPROVED_OPERATOR_EMAIL" \
  --role="roles/run.invoker"
~~~

Lặp lại binding cho B theo scope người thử nghiệm; không thay thành `--allow-unauthenticated` chỉ để bỏ qua lỗi 403.

Smoke test:

~~~bash
export TOKEN="$(gcloud auth print-identity-token)"

curl -fsS -H "Authorization: Bearer ${TOKEN}" "${URL_A}/ready"
curl -fsS -H "Authorization: Bearer ${TOKEN}" "${URL_B}/ready"

curl -fsS -H "Authorization: Bearer ${TOKEN}" "${URL_A}/whoami"
curl -fsS -H "Authorization: Bearer ${TOKEN}" "${URL_B}/whoami"
~~~

Kỳ vọng: A báo `writesEnabled=true`, B báo `false`, cả hai có thể đọc primary A khi database khỏe. Token nên tạo lại khi hết hạn; không ghi token vào ticket/log dùng chung. Nếu `/ready` lỗi, kiểm tra Cloud SQL connection name, runtime SA, `roles/cloudsql.client`, quyền truy cập secret, DB user/password và network/IP mode.

## 9. Ghi baseline và dữ liệu giả trước khi diễn tập

Dùng UUID riêng cho mỗi drill, ghi rõ từ đâu tới đâu:

~~~bash
export ORDER_ID="11111111-1111-4111-8111-111111111111"

curl -fsS -X POST "${URL_A}/orders" \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  --data "{\"id\":\"${ORDER_ID}\",\"amount\":120}"

curl -fsS "${URL_A}/orders/${ORDER_ID}" \
  -H "Authorization: Bearer ${TOKEN}"
~~~

Trong một script shell ở lab, giữ mốc thời gian:

~~~bash
date -u +"%Y-%m-%dT%H:%M:%SZ"

gcloud sql instances describe "${PRIMARY}" \
  --project="${PROJECT_ID}" \
  --format="yaml(state,region,connectionName,settings.availabilityType)"

gcloud sql instances describe "${REPLICA}" \
  --project="${PROJECT_ID}" \
  --format="yaml(state,region,masterInstanceName,connectionName)"
~~~

Lưu lại ID, amount, `created_at`, timestamp UTC, image digest, revision Cloud Run, metrics replication, thời gian truy vấn và ảnh chụp dashboards. Đừng chỉ lưu stdout lệnh `gcloud` rồi kết luận tất cả dữ liệu đã đồng bộ.

### 9.1. Kiểm tra replica đã replay

Qua Cloud SQL Studio/psql được cấp quyền ở **replica B**, dùng query chỉ đọc:

~~~sql
SELECT pg_is_in_recovery() AS is_standby;

SELECT
  pg_last_wal_receive_lsn() AS received_lsn,
  pg_last_wal_replay_lsn() AS replayed_lsn,
  pg_last_xact_replay_timestamp() AS last_replayed_commit;
~~~

Khi còn là replica, `pg_is_in_recovery()` thường trả `true`. Kết quả LSN và timestamp cần diễn giải cùng **Replication state** và **Lag Bytes**; không suy ra “đã bắt kịp hoàn toàn” chỉ từ một timestamp, đặc biệt khi database nhàn rỗi lâu. Người quản trị cần xác minh các writes/mốc nghiệp vụ đã được replay trên B trước promotion có kế hoạch.

## 10. Diễn tập số 1: Cloud SQL HA failover trong một region

**Mục tiêu:** quan sát ứng dụng A xử lý mất kết nối ngắn và hồi phục khi Cloud SQL HA chuyển sang standby zone trong cùng region. Không chuyển client sang region B ở bài này.

### Gate 1 — Trước khi failover

- [ ] Instance primary A là `REGIONAL`, cả primary/standby zone khỏe.
- [ ] Không có operation dài hoặc backup/maintenance đang chặn test.
- [ ] Có backup/PITR và dữ liệu baseline.
- [ ] Cloud Run A đang healthy, người kiểm thử ghi thời điểm UTC.
- [ ] Có người approve thao tác, chỉ chạy trên project lab.

Lệnh thử HA, sau approval:

~~~bash
# DRILL TRÊN LAB: có thể gây mất kết nối tạm thời.
gcloud sql instances failover "${PRIMARY}" \
  --project="${PROJECT_ID}"
~~~

Cloud SQL HA trong cùng region có thể failover tự động khi xảy ra lỗi zone, và Google Cloud hỗ trợ thao tác test failover qua CLI. Trong quá trình test, connection của ứng dụng có thể bị đóng; JDBC/Hikari cần tái tạo connection, request lỗi cần retry/idempotency ở phía client. **Đây không phải regional DR** và không tác động promotion của B.

### Gate 2 — Sau failover

- Quan sát Cloud SQL operation state, kết quả Cloud Run GET/POST và 5xx.
- Xác minh database connection name của A **không cần đổi** trong mô hình HA này.
- Ghi downtime thực tế, lỗi application và thời gian phục hồi.
- Kiểm tra record baseline không mất, tạo record mới bằng ID khác.
- Ghi nguyên nhân retry, kiểm tra client không tạo hai đơn do timeout.

Nếu test thất bại hoặc instance vẫn trong operation, **không chạy failover liên tục**; điều tra Cloud SQL logs/Monitoring trước.

## 11. Diễn tập số 2: DR chuyển sang region B

**Mục tiêu:** thử quy trình failover thủ công có kiểm soát. Ta **không tắt một Google Cloud region**. Thay vào đó, giả định region A không còn phục vụ client, chủ động dừng writes A và sử dụng replica B.

### Pha A — Chốt trạng thái và fencing

1. Đảm bảo B replica đang khỏe và có latest data hợp lệ.
2. Dừng test writer/producer của A. Đợi request đang chạy hoàn tất và không cho job nền tiếp tục ghi.
3. Đổi Cloud Run A sang mode không ghi **trong khi A còn truy cập được**, rồi xác minh POST bị từ chối.
4. Đối chiếu marker/LSN đã replay ở B; nếu còn lag, chờ trong giới hạn lab hoặc ghi nhận risk.
5. Ghi mốc `T0` bắt đầu đếm RTO và người phê duyệt promotion.

Lệnh tắt ghi A (không gây outage region thật):

~~~bash
gcloud run services update "${SERVICE}" \
  --project="${PROJECT_ID}" \
  --region="${REGION_A}" \
  --update-env-vars="APP_WRITES_ENABLED=false"
~~~

Sau khi revision mới Ready và traffic cũ đã drain, gọi:

~~~bash
export TOKEN="$(gcloud auth print-identity-token)"

curl -sS -o /dev/null -w "HTTP %{http_code}\n" \
  -X POST "${URL_A}/orders" \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  --data '{"id":"22222222-2222-4222-8222-222222222222","amount":50}'
~~~

Kỳ vọng `503` do write guard. Nếu vẫn trả `201`, **STOP**: A chưa được fence; không promote B. Cần lưu ý Cloud Run revision/traffic routing và các producer khác; guard ở app không đủ để bảo đảm trong sự cố mất liên lạc. Với failover thật phải có **runbook fencing mạnh hơn**, xác nhận mọi nguồn ghi và tránh hai primary độc lập.

### Pha B — Đánh giá lag và promote B

Xác minh Cloud SQL replication state và lag trên B. Với planned drill, ưu tiên đợi replica **đã replay mọi write được chấp nhận trên A**. Chọn một marker cuối cùng và đọc trực tiếp từ B để làm bằng chứng. Nếu không khớp, chưa nên promote theo đường planned-zero-data-loss.

Sau khi DBA và Incident Commander phê duyệt, thực hiện thao tác **có tính chất thay đổi topology**:

~~~bash
# LAB DR ONLY, không chạy khi A vẫn đang nhận write!
gcloud sql instances promote-replica "${REPLICA}" \
  --project="${PROJECT_ID}"
~~~

Promotion biến B thành một instance **standalone writable**. Đây là hành động thủ công, không phải zonal HA. Với Cloud SQL Enterprise Plus có mô hình **advanced DR** riêng gồm designated DR replica và `replica failover/switchover`; không đánh đồng mô hình đó với promotion cổ điển trong bài này.

Kiểm tra:

~~~bash
gcloud sql instances describe "${REPLICA}" \
  --project="${PROJECT_ID}" \
  --format="yaml(name,state,region,masterInstanceName,connectionName)"
~~~

Ở PostgreSQL của B, query sau promotion:

~~~sql
SELECT pg_is_in_recovery() AS is_standby;
~~~

Kỳ vọng `false`. Điều này chỉ xác nhận database B không còn ở chế độ recovery; cần thêm smoke test write/read và xác minh data integrity.

**Quan trọng:** sau promotion, A và B có thể trở thành **hai cơ sở dữ liệu writable độc lập**. Nếu A được phép ghi tiếp khi khôi phục kết nối, dữ liệu có thể phân kỳ. Không hướng client hoặc job nền trở lại A một cách tự động. Giữ A fenced, đưa ra quyết định rõ về data reconciliation, re-replication và failback.

### Pha C — Cập nhật Cloud Run B vào primary mới

Lấy connection name B:

~~~bash
export CONN_B="${PROJECT_ID}:${REGION_B}:${REPLICA}"
~~~

Cập nhật cả **instance attachment** và biến môi trường; chỉ bật write B sau khi có bằng chứng B đã promote:

~~~bash
gcloud run services update "${SERVICE}" \
  --project="${PROJECT_ID}" \
  --region="${REGION_B}" \
  --set-cloudsql-instances="${CONN_B}" \
  --update-env-vars="DB_INSTANCE_CONNECTION_NAME=${CONN_B},APP_WRITES_ENABLED=true"
~~~

Kiểm tra trạng thái và đợi revision Ready:

~~~bash
gcloud run services describe "${SERVICE}" \
  --project="${PROJECT_ID}" \
  --region="${REGION_B}" \
  --format="yaml(status.url,status.conditions,metadata.name)"
~~~

### Pha D — Smoke test và manual cutover

~~~bash
export TOKEN="$(gcloud auth print-identity-token)"
export DR_ORDER_ID="33333333-3333-4333-8333-333333333333"

curl -fsS -H "Authorization: Bearer ${TOKEN}" "${URL_B}/ready"
curl -fsS -H "Authorization: Bearer ${TOKEN}" "${URL_B}/whoami"

curl -fsS -X POST "${URL_B}/orders" \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  --data "{\"id\":\"${DR_ORDER_ID}\",\"amount\":230}"

curl -fsS -H "Authorization: Bearer ${TOKEN}" \
  "${URL_B}/orders/${DR_ORDER_ID}"

curl -fsS -H "Authorization: Bearer ${TOKEN}" \
  "${URL_B}/orders/${ORDER_ID}"
~~~

Điều kiện pass:

- B chỉ nhận write sau khi DBA chấp thuận promotion.
- POST mới thành công và GET trả cùng ID/amount.
- Record baseline trước DR vẫn có ở B, hoặc mọi thiếu hụt được **đo và ghi rõ**.
- Ứng dụng B chạy đúng image, identity, secret, DB instance và có logs/alerts.
- A tiếp tục bị fence và không có ứng dụng producer khác ghi vào A.
- Incident Commander chấp thuận chuyển **client test** sang URL B.

Việc gọi trực tiếp URL B trong bài này là **manual cutover client-side**. Với production, thay URL qua load balancer/DNS/traffic switch có kế hoạch, xét TTL, connection draining, cache và khả năng client retry. Không dùng `--allow-unauthenticated` để “sửa” 403 khi failover.

## 12. Đo RTO/RPO của diễn tập regional DR

### 12.1. Nhật ký timestamp mẫu

| Mốc UTC (giả định) | Sự kiện |
|---|---|
| 08:59:40 | Marker order cuối được primary A xác nhận |
| 08:59:41 | Marker đó đã được kiểm chứng trên replica B |
| 09:00:00 | T0: bắt đầu drill, ngừng nhận write trên A |
| 09:04:00 | Đã đánh giá lag, phê duyệt promote |
| 09:11:00 | B đã promote và kiểm tra instance state |
| 09:14:00 | Cloud Run B revision Ready |
| 09:17:00 | POST/GET thành công qua URL B, T-restore |

Nếu lấy RTO từ 09:00 đến 09:17 thì **RTO đo được = 17 phút** trong ví dụ. Việc marker cuối đã replay không bảo đảm **mọi** write khác đã replay nếu không đối soát thích hợp; trong planned drill nên quiesce writes, kiểm chứng replication status/lag và dữ liệu trước khi promote. Nếu chứng minh không mất write, **RPO quan sát = 0 cho dữ liệu kiểm thử đã xác nhận**; không vì vậy cam kết RPO=0 cho sự cố mất region đột ngột.

~~~text
Actual RTO = first verified healthy business transaction
             - incident/drill start time

Observed RPO = latest committed data accepted by old primary
               that is absent on promoted primary,
               expressed as time window or lost transaction set
~~~

Trong bảng báo cáo, ghi cả **phút** và **số records mất/được giữ**. Không lấy replication lag metric làm RPO đo được một cách máy móc: lag có thể có độ trễ quan sát và kết quả ngoài database còn phụ thuộc Pub/Sub/cache/objects.

### 12.2. Mẫu báo cáo

~~~yaml
drill_id: DRILL-EXAMPLE-01
environment: staging
scenario: cross_region_manual_promotion
start_time_utc: "2026-11-19T09:00:00Z"
restore_time_utc: "2026-11-19T09:17:00Z"
rto_target_minutes: 45
rto_observed_minutes: 17
rpo_target_minutes: 5
data_validation:
  last_committed_id: "11111111-1111-4111-8111-111111111111"
  present_on_recovery: true
  suspected_missing_records: 0
  confirmation_scope: "test marker only"
write_fencing:
  old_writer_blocked: true
  outstanding_producers_reviewed: true
security_approval: "pending evidence link"
cutover_approval: "pending evidence link"
~~~

Chỉ dùng các số liệu mẫu để hiểu cách ghi. Báo cáo thực phải ghi UTC timestamps và evidence links đã kiểm chứng; không ghi “pass” cho bước chưa thực hiện.

## 13. Diễn tập số 3: PITR khôi phục dữ liệu sau thao tác sai

Failover và data recovery là hai việc khác nhau:

- **Failover** xử lý database/region không khả dụng, chọn primary khác.
- **PITR** tạo một instance mới phản ánh dữ liệu tại thời điểm trước thao tác ghi sai; nó **không tự khôi phục dữ liệu đã mất vào instance hiện tại**.

Thực hiện phần này trên primary còn hoạt động, **đã có backup và PITR window phù hợp**. Dùng một instance có PITR được bật trước khi tạo dữ liệu. Không mặc định có thể chạy ngay sau khi B mới được promote.

### Pha A — Tạo dữ liệu giả và gây sai có kiểm soát

1. Tạo hai đơn hàng giả khác ID qua API lab.
2. Ghi lại JSON của cả hai và mốc thời gian UTC.
3. Trong Cloud SQL Studio/psql của database lab, xác nhận row và snapshot logic trước thao tác.
4. Chọn một thời điểm `T_SAFE` có thể phục hồi trong PITR window.
5. Thực hiện một thao tác sửa sai có kiểm soát **chỉ với row lab**, ví dụ thay amount từ 120 sang 999.
6. Không thử `DROP DATABASE` hoặc xóa instance để chứng minh PITR.

~~~sql
-- Chỉ database lab, dùng ID đã tạo riêng cho drill.
SELECT id, amount, created_at
FROM dr_orders
WHERE id = '11111111-1111-4111-8111-111111111111';

-- Bài tập mô phỏng lỗi, phải được Data owner cho phép:
UPDATE dr_orders
SET amount = 999
WHERE id = '11111111-1111-4111-8111-111111111111';
~~~

Nếu đang chạy lab sau regional promotion, chọn **primary hiện hành** (có thể là B) và **xác minh PITR window của chính primary đó**; không reuse timestamp/instance name của primary A một cách mù quáng.

### Pha B — Kiểm tra PITR window

~~~bash
# Đổi SOURCE thành primary có PITR hợp lệ; trong lab độc lập có thể là A.
export SOURCE="${PRIMARY}"
export PITR_TARGET="dr-pitr-verify"

gcloud sql instances describe "${SOURCE}" \
  --project="${PROJECT_ID}" \
  --format="yaml(name,settings.backupConfiguration)"

gcloud sql instances get-latest-recovery-time "${SOURCE}" \
  --project="${PROJECT_ID}"
~~~

Ghi `earliestRecoveryTime` và `latestRecoveryTime` nếu được trả về, rồi chọn `T_SAFE` **trong cửa sổ đó và trước lúc dữ liệu bị sửa**. Sử dụng UTC RFC3339, không dùng đồng hồ local chưa chuyển múi giờ. Khi dữ liệu mới tạo mà PITR chưa có recovery point phù hợp, hãy dừng bài tập, không tự đoán timestamp.

### Pha C — Clone sang instance mới

~~~bash
# T_SAFE là timestamp UTC hợp lệ, ví dụ 2026-11-19T08:50:00Z.
export T_SAFE="YYYY-MM-DDTHH:MM:SSZ"

# CHỈ LAB / sau approval; tạo instance mới có chi phí.
gcloud sql instances clone "${SOURCE}" "${PITR_TARGET}" \
  --project="${PROJECT_ID}" \
  --point-in-time="${T_SAFE}"
~~~

**Không restore đè production** để tiết kiệm một instance. PITR clone tạo instance mới, có connection name/IP riêng. Với standard backups, lệnh `instances clone --point-in-time` là luồng thông dụng. Với **Enhanced backups** trong Backup and DR vault, cách thao tác PITR có thể dùng `gcloud sql instances point-in-time-restore` và data source khác; kiểm tra loại backup/edition trước khi chọn lệnh.

### Pha D — Xác minh và chọn phương án sửa dữ liệu

Truy vấn trên **PITR_TARGET** bằng Cloud SQL Studio/psql với quyền thích hợp:

~~~sql
SELECT id, amount, created_at
FROM dr_orders
WHERE id = '11111111-1111-4111-8111-111111111111';
~~~

Kỳ vọng bản sao tại `T_SAFE` còn amount ban đầu. Không chỉ nhìn thấy instance RUNNABLE là đạt. Đối soát các record khác, schema migration, sequence/transaction và tính nhất quán với sự kiện bên ngoài.

Với ứng dụng thật, có hai phương án chính:

- **Extract và sửa chọn lọc:** lấy row đúng từ PITR clone, kiểm tra giao dịch, cập nhật có điều kiện vào primary hiện tại, bảo đảm không ghi đè các thay đổi hợp lệ sau `T_SAFE`.
- **Full cutover sang PITR clone:** chỉ khi có thẩm quyền chấp nhận mất toàn bộ writes từ `T_SAFE` tới hiện tại và đã rà soát tất cả consumer/dependency; thay connection, route và account policy.

Bài lab dừng ở **xác minh bản PITR clone**, không tự động ghi đè primary. Phần dữ liệu tham chiếu ở ngoài PostgreSQL như Pub/Sub, Cloud Storage hoặc payment gateway không quay ngược thời gian cùng một lệnh PITR.

## 14. Diễn tập số 4: khôi phục Cloud Storage object

Cloud Storage là nơi thường lưu hóa đơn, biên bản và object do ứng dụng tạo. Với bucket đã bật **soft delete**, object bị xóa có thể khôi phục trong thời gian retention. Không nhầm soft delete, Object Versioning và bucket retention policy.

### Pha A — Tạo bucket và dữ liệu giả

~~~bash
export BUCKET="${PROJECT_ID}-dr-object-lab"

# Chỉ LAB, bucket name phải duy nhất trên toàn cầu.
gcloud storage buckets create "gs://${BUCKET}" \
  --project="${PROJECT_ID}" \
  --location="${REGION_A}" \
  --uniform-bucket-level-access \
  --soft-delete-duration=7d

printf '%s\n' '{"order":"lab-only","total":120}' \
  | gcloud storage cp - "gs://${BUCKET}/receipts/sample.json"
~~~

Xác minh object và thông tin generation trước khi xóa:

~~~bash
gcloud storage ls -L "gs://${BUCKET}/receipts/sample.json"
gcloud storage cat "gs://${BUCKET}/receipts/sample.json"
~~~

### Pha B — Xóa object thử nghiệm và tìm bản soft-deleted

Chỉ sau khi đã xác nhận đúng tên bucket/path:

~~~bash
# XÓA CHÍNH OBJECT LAB, không bao giờ dùng wildcard production.
gcloud storage rm "gs://${BUCKET}/receipts/sample.json"

gcloud storage ls "gs://${BUCKET}/receipts/sample.json" --soft-deleted
~~~

Lệnh liệt kê cho thấy generation của object đã bị xóa. Ghi lại generation và thời điểm delete.

### Pha C — Restore generation có kiểm soát

~~~bash
gcloud storage restore \
  "gs://${BUCKET}/receipts/sample.json#GENERATION_NUMBER"

gcloud storage cat "gs://${BUCKET}/receipts/sample.json"
gcloud storage ls -L "gs://${BUCKET}/receipts/sample.json"
~~~

Điều kiện pass: JSON nội dung giả lập đúng, metadata/checksum phù hợp, object có thể đọc với quyền được duyệt. Nếu một live object đã trùng tên, **không tự thêm `--allow-overwrite`**; trước tiên bảo vệ bản hiện tại và chọn phương án kiểm chứng an toàn.

Soft delete chỉ bảo vệ trong retention window. Nếu xóa cả bucket, cần khôi phục bucket trước; với CLI/API, khôi phục bucket không tự khôi phục toàn bộ objects. Với Cloud Storage được mã hóa bằng CMEK, khả năng đọc backup còn phụ thuộc key version và service agent đúng quyền.

## 15. Quy trình failback sau khi region A hồi phục

**Failback không phải đảo ngược lệnh promote.** Với Cloud SQL cross-region replica cổ điển, khi B đã promote, B là primary độc lập, còn instance A cũ không tự trở thành replica đồng bộ của B.

Một runbook có trách nhiệm cần:

1. **Giữ A fenced** trong lúc B đang là writer. Không chấp nhận client quay về A chỉ vì endpoint cũ sống lại.
2. Kiểm tra dữ liệu trên B, transaction và các event/outbox. Xác định sự khác biệt giữa A cũ và B mới.
3. Thiết lập một **read replica mới của B ở A** hoặc giải pháp đồng bộ dữ liệu được hỗ trợ; không dùng instance A cũ đang chứa data phân kỳ làm replica bằng cách đổi tên.
4. Chờ replay bắt kịp và kiểm tra dữ liệu/metrics.
5. Tổ chức một đợt **planned switchover/failback** khi có maintenance window, dừng writes B và chọn đường trở về A an toàn.
6. Sau failback, kiểm tra writer duy nhất, ảnh hưởng đến client, replica/backup/HA topology và runbook tương lai.
7. Chỉ xóa instance cũ sau khi Data owner phê duyệt và backup retention đã được kiểm tra.

Với **Cloud SQL Enterprise Plus advanced DR**, designated DR replica và các thao tác replica failover/switchover có semantics khác và có thể đơn giản hóa failback. Không trộn lệnh hoặc runbook của hai mô hình.

### 15.1. Vì sao phải kiểm soát split brain?

Nếu A tiếp tục nhận 100 đơn trong khi B nhận 50 đơn khác sau promotion, hai database đã diverge. Chuyển DNS về A không thể tự gộp đơn từ B. Cơ chế khôi phục có thể cần transaction reconciliation, event replay, conflict resolution và định danh idempotent; đó là quyết định nghiệp vụ, không đơn thuần thao tác hạ tầng.

Một “fencing” mạnh có thể gồm: chặn đường ingress tới writer cũ, thu hồi quyền ghi tại các producers còn sống, điều phối connection cutover, đảm bảo old primary không quay lại phục vụ writes mà chưa được tái đồng bộ. Trong lúc region A không liên lạc được, khả năng fencing phải được thiết kế từ **trước sự cố**, không phụ thuộc duy nhất vào một lệnh chỉ chạy được khi A còn khỏe.

## 16. Kiểm thử end-to-end sau khôi phục

| Nhóm | Test | Bằng chứng đạt |
|---|---|---|
| Database | GET marker trước failover | Đúng ID/amount, không mất record ngoài RPO chấp thuận |
| Database | POST marker mới sau failover | 201/200 theo quy tắc idempotency, đọc lại cùng ID |
| Writer isolation | POST tới old writer A | Bị chặn; không còn producer cũ |
| App | Cloud Run B revision và health | Ready, log và metric đúng region |
| Identity | Runtime SA, secret, DB user | Không có 403/permission escalation |
| Replication | Đúng topology sau promote | B primary, không còn phụ thuộc A cũ |
| Recovery | PITR clone | Thấy dữ liệu ở timestamp đúng |
| Cloud Storage | Soft delete generation restore | Hash/nội dung khớp |
| Observability | Logs, dashboards, alert | Có đủ timestamp, 5xx/latency |
| Business | Không double-charge/duplicate event | Review bởi Data owner, nếu workload thật |

Các test này phải gắn với mốc UTC và người phê duyệt. “Health 200” không đủ vì có thể ứng dụng đọc được DB nhưng ghi nhầm instance hoặc dữ liệu trùng.

## 17. Logs, metrics và alert cần thu thập

### 17.1. Những chỉ số cần đo

- Cloud Run: request count, 5xx, latency p95/p99, active revisions và instance count ở từng region.
- Cloud SQL primary/replica: replication state, lag bytes, CPU, memory, connections, transaction rate và operations.
- Backup/PITR: backup success, PITR window, restore operation duration.
- Cloud Storage: soft-delete configuration, object generation, restore result.
- IAM: ai deploy, ai promote, ai thay secret hoặc đổi database permissions.
- Business: số đơn hàng test đã ghi nhận, duplicate IDs, row reconciliation.
- Billing: runtime instance-hours, database HA/replica, network egress, storage, log và PITR clone.

### 17.2. Mẫu log cho ứng dụng

~~~text
event=dr_write_guard_enabled region=asia-southeast1
event=replication_validation_started source=dr-pg-primary target=dr-pg-replica
event=promotion_approved change_id=DRILL-EXAMPLE-01
event=promotion_completed primary=dr-pg-replica
event=cloud_run_revision_ready region=asia-southeast2
event=dr_smoke_passed region=asia-southeast2 order_id=...
event=client_cutover_approved region=asia-southeast2
~~~

Những dòng trên là **mẫu sự kiện cần ghi**, không phải log mà Google Cloud tự phát sinh đúng nguyên văn. Dùng correlation ID/change ID, tránh ghi password, token hoặc dữ liệu nhạy cảm trong logs.

### 17.3. Khi nào cần alert?

| Tình huống | Alert/action |
|---|---|
| Replica lag tăng hoặc replication stopped | Điều tra trước khi DR, đánh giá RPO |
| Cloud SQL primary unavailable | Kích hoạt incident triage, phân biệt zonal và regional |
| Cloud Run 5xx tăng | Kiểm tra app/DB/log trước khi chuyển traffic |
| DB connections gần giới hạn | Giảm concurrency, kiểm tra max instances/pool |
| PITR/backup thất bại | Chặn kế hoạch DR nếu mất cửa sổ phục hồi bắt buộc |
| Chi phí replica/clone vượt dự toán | Dừng mở rộng lab và xử lý resource sau approval |
| Old writer còn nhận POST sau cutover | **Sev cao: nguy cơ split brain**, cô lập và điều tra |

## 18. Các lỗi hay gặp trong lab

| Triệu chứng | Nguyên nhân khả dĩ | Xử lý an toàn |
|---|---|---|
| Cloud Run A lỗi 403 khi gọi | User không có Run Invoker | Cấp role đúng service, không mở public |
| Ứng dụng lỗi kết nối Cloud SQL | Runtime SA thiếu Cloud SQL Client, sai connection name, secret hoặc network | So config, IAM, Secret Manager và logs |
| Replica còn read-only sau promote | Operation chưa hoàn tất hoặc app đang trỏ instance cũ | Xem instance state, `pg_is_in_recovery()`, connection config |
| Replica lag cao | I/O/capacity/network hoặc transaction dài | Giảm write test, chờ hoặc ghi RPO risk |
| A vẫn ghi sau chuyển B | Fencing thiếu, traffic còn route về A | Dừng cutover, cô lập nguồn ghi, điều tra data divergence |
| PITR báo timestamp invalid | Sai timezone hoặc ngoài recovery window | Lấy earliest/latest recovery time, UTC RFC3339 |
| PITR clone không có row như mong đợi | Chọn sai T_SAFE hoặc chưa có WAL phù hợp | Kiểm tra audit timeline và backup history |
| Soft-deleted object không liệt kê được | Bucket không bật soft delete hoặc hết retention | Xem policy/generation và quyền; không hứa phục hồi |
| Đã restore GCS nhưng object khác nội dung | Chọn nhầm generation hoặc overwrite | So hash, metadata và chọn đúng version |
| Cloud SQL failover treo | Instance operation khác, standby zone unhealthy | Kiểm tra operations, không spam failover |
| Client ghi trùng sau timeout | Retry không có idempotency | Dùng client-generated ID, unique key, reconciliation |
| Chi phí tăng khi lab xong | Hai Cloud SQL instances + PITR clone/backup còn tồn tại | Inventory, delete có approval và chính sách giữ backup |

## 19. Security và giới hạn của diễn tập

- **Không dùng dữ liệu production:** seed synthetic IDs, không copy PII/secret.
- **Tách identity:** deployer, runtime, DBA, incident commander và auditor.
- **IAM tối thiểu:** runtime chỉ cần Cloud SQL client và Secret Manager accessor cho đúng secret; quyền tạo/delete/promote instance chỉ cấp người vận hành có thẩm quyền.
- **Giữ audit evidence:** lưu change ID, Cloud Audit Logs, Cloud SQL operations và bản log kiểm thử ở nơi kiểm soát.
- **CMEK:** nếu dùng customer-managed encryption keys, backup và replica vẫn phụ thuộc key material, key version, location, service agent và IAM; backup không thể đọc khi key cần thiết bị phá hủy.
- **Không làm outage thật:** nếu muốn diễn tập region-down, mô phỏng bằng client routing và writer guard trong staging; không tắt network hay tài nguyên chung.
- **Không lẫn lộn continuity với confidentiality:** DR phục hồi dịch vụ, còn xử lý ransomware/credential compromise cần security containment, điều tra và restore sạch riêng.
- **IAM invoker:** Cloud Run IAM hạn chế người thử nghiệm; endpoints application production cần identity/authorization nghiệp vụ riêng.
- **Single-writer:** công tắc app là guard trong lab; production cần fencing và quy trình failback được thiết kế kỹ.

## 20. Dọn tài nguyên sau lab

Không xóa tài nguyên cho đến khi:

1. Tất cả logs, RTO/RPO, screenshots và bằng chứng cần thiết đã lưu.
2. Không có client/tester còn dùng URL/DB.
3. Data owner xác nhận chỉ có dữ liệu giả, không cần giữ để tái kiểm chứng.
4. Người có quyền phê duyệt đã xem danh sách tài nguyên cần xóa.
5. Đã ghi nhận backup retention, CMEK, Secret Manager và chi phí còn lại.

Kiểm tra inventory chỉ đọc:

~~~bash
gcloud run services list --project="${PROJECT_ID}"
gcloud sql instances list --project="${PROJECT_ID}"
gcloud artifacts repositories list --project="${PROJECT_ID}"
gcloud storage buckets list --project="${PROJECT_ID}"
gcloud secrets list --project="${PROJECT_ID}"
~~~

Lệnh phá hạ tầng **chỉ là gợi ý kiểm soát**, không chạy tự động:

~~~bash
# CẨN TRỌNG: xóa service lab trong từng region sau approval.
# gcloud run services delete dr-orders --region=asia-southeast1 --project=PROJECT_ID
# gcloud run services delete dr-orders --region=asia-southeast2 --project=PROJECT_ID

# CẨN TRỌNG: PITR clone và promoted replica là DB instances tính phí.
# Xem deletion protection và retained/final backups trước khi xóa.
# gcloud sql instances delete dr-pitr-verify --project=PROJECT_ID
# gcloud sql instances delete dr-pg-replica --project=PROJECT_ID
# gcloud sql instances delete dr-pg-primary --project=PROJECT_ID
~~~

Nếu `--deletion-protection` bật, cần quy trình riêng để đổi protection trước khi xóa; không thêm `--no-deletion-protection` tự động vào script cleanup. Storage soft-deleted objects, backup retention, Artifact Registry image, secret versions và các logs có thể vẫn lưu theo chính sách hoặc phát sinh phí sau khi xóa compute; kiểm tra Billing trong các ngày tiếp theo.

## 21. Ma trận đánh giá và rubric nộp bài

| Tiêu chí | Điểm tối đa | Bằng chứng |
|---|---:|---|
| Kiến trúc và SLO/RTO/RPO | 15 | Diagram và bảng yêu cầu |
| Cloud SQL HA và cross-region topology | 15 | Screenshots/describe/metrics |
| Write fencing, single-writer và promotion gates | 15 | Runbook và POST bị chặn ở old writer |
| Smoke test và data reconciliation | 15 | ID/amount trước và sau, error rate |
| PITR + GCS restore | 15 | Timestamp, clone và object generation |
| IAM, secret, audit | 10 | Security checklist, roles |
| Cost/cleanup | 5 | Dự toán và inventory sau lab |
| Báo cáo diễn tập và phản tư | 10 | T0, T-restore, RTO/RPO, cải tiến |
| **Tổng** | **100** | |

Một bài không được đánh giá “đạt production readiness” nếu còn nguy cơ split brain, thiếu dữ liệu khôi phục hoặc không có bằng chứng backup/PITR hoạt động, dù tổng điểm cao.

### Những điều học viên phải giải thích

- Failover HA trong region giữ instance connection name như thế nào, và ứng dụng phải xử lý connection reset ra sao?
- Vì sao cross-region replica promotion có thể mất dữ liệu và cần quiesce/replay validation?
- Tại sao chuyển Cloud Run traffic trước khi promote database sẽ thất bại?
- Nếu region A hồi phục sau khi B đã nhận writes, vì sao không tự động chuyển về A?
- PITR khác việc restore lại bản backup gần nhất và khác failover ra sao?
- Vì sao soft delete cần kiểm tra generation và retention?
- RTO/RPO quan sát là số liệu đo, không phải thuộc tính cố định của một dịch vụ cloud?

## 22. Checklist cuối cùng

- [ ] Project lab, budget alert và quota được kiểm tra; không sử dụng production.
- [ ] Runtime SA, Secret Manager và IAM invoker được cấu hình tối thiểu.
- [ ] Cloud SQL A HA + PITR/backup được bật và kiểm tra.
- [ ] Replica B đúng region, healthy và có bằng chứng replay.
- [ ] Cloud Run A và B dùng cùng image, config riêng và standby write guard.
- [ ] Có ít nhất một record marker đã kiểm tra trên source và standby.
- [ ] HA failover trong region có log thao tác, connection recovery và 5xx.
- [ ] Regional promotion chỉ chạy sau fencing, replay validation và approval.
- [ ] Cloud Run B trỏ đúng connection name B sau promotion.
- [ ] POST/GET sau DR thành công, baseline records đối soát.
- [ ] Old writer A bị chặn; không sinh primary split brain.
- [ ] PITR clone dùng timestamp UTC hợp lệ và được kiểm tra dữ liệu.
- [ ] Cloud Storage object đã restore đúng generation, checksum/nội dung phù hợp.
- [ ] Báo cáo có RTO/RPO thực đo, thời điểm, records thiếu và owner.
- [ ] Có kế hoạch failback/rebuild replica, không dùng lại A cũ bừa bãi.
- [ ] Logs/metrics và chứng cứ được lưu, dữ liệu lab được dọn có phê duyệt.

## Kết luận

Dự án cho thấy **failover không đồng nghĩa với phục hồi dữ liệu**. Cloud SQL HA xử lý một số lỗi ở cấp zone trong region; cross-region replica hỗ trợ DR nhưng cần promotion, kiểm tra lag và fencing để không tạo hai nguồn ghi độc lập; PITR khôi phục sai lệch dữ liệu ở một thời điểm bằng instance mới; Cloud Storage soft delete phục hồi object trong retention. Thành công chỉ được công nhận khi người vận hành chứng minh được **dữ liệu đúng, business transaction chạy, RTO/RPO đã đo, quyền bảo mật vẫn phù hợp và không còn writer cũ có thể gây phân kỳ**.

## Tài liệu tham khảo

- [Cloud SQL for PostgreSQL — About disaster recovery](https://docs.cloud.google.com/sql/docs/postgres/intro-to-cloud-sql-disaster-recovery)
- [Cloud SQL for PostgreSQL — Promote cross-region replicas](https://docs.cloud.google.com/sql/docs/postgres/replication/cross-region-replicas)
- [Cloud SQL for PostgreSQL — Create read replicas](https://docs.cloud.google.com/sql/docs/postgres/replication/create-replica)
- [Cloud SQL for PostgreSQL — Manage replicas and promotion](https://docs.cloud.google.com/sql/docs/postgres/replication/manage-replicas)
- [Cloud SQL for PostgreSQL — High availability](https://docs.cloud.google.com/sql/docs/postgres/high-availability)
- [Cloud SQL for PostgreSQL — Configure HA and test failover](https://docs.cloud.google.com/sql/docs/postgres/configure-ha)
- [Cloud SQL for PostgreSQL — Configure PITR](https://docs.cloud.google.com/sql/docs/postgres/backup-recovery/configure-pitr)
- [Cloud SQL for PostgreSQL — Perform PITR](https://docs.cloud.google.com/sql/docs/postgres/backup-recovery/pitr)
- [Cloud SQL for PostgreSQL — Restore overview](https://docs.cloud.google.com/sql/docs/postgres/backup-recovery/restore)
- [Cloud SQL for PostgreSQL — Connect from Cloud Run](https://docs.cloud.google.com/sql/docs/postgres/connect-run)
- [Cloud Run — Serve traffic from multiple regions](https://docs.cloud.google.com/run/docs/multiple-regions)
- [Cloud Run — Configure Cloud SQL connections](https://docs.cloud.google.com/run/docs/configuring/services/cloud-sql)
- [Cloud Storage — Use soft-deleted objects](https://docs.cloud.google.com/storage/docs/use-soft-deleted-objects)
- [Cloud Storage — Configure soft delete](https://docs.cloud.google.com/storage/docs/use-soft-delete)
- [Cloud Storage — Restore soft-deleted objects](https://docs.cloud.google.com/sdk/gcloud/reference/storage/restore)
- [Cloud Billing — Create budgets and alerts](https://docs.cloud.google.com/billing/docs/how-to/budgets)
- [Google Cloud — Architecture Framework: Reliability](https://docs.cloud.google.com/architecture/framework/reliability)

