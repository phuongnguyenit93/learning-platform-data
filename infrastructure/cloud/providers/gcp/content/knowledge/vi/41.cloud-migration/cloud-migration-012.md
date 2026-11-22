# Thực hành di chuyển ứng dụng ba tầng lên Google Cloud

Di chuyển một ứng dụng ba tầng không chỉ là sao chép máy chủ. Nhóm triển khai phải chuyển **đường nhận traffic**, **dịch vụ xử lý nghiệp vụ** và **cơ sở dữ liệu** sang môi trường mới, giữ kết nối và quyền truy cập đúng, đồng thời bảo đảm không mất đơn hàng hoặc tạo dữ liệu trùng trong thời điểm cutover. Bài thực hành này mô phỏng một ứng dụng quản lý đơn hàng đang chạy tại trung tâm dữ liệu riêng và đưa nó lên Google Cloud qua các bước có thể kiểm tra, dừng hoặc quay lui.

Trong module **CLOUD_PROVIDERS_GCP**, người học đã tiếp cận tổ chức project, IAM, VPC, Compute Engine, GKE, Cloud Run, lưu trữ và cơ sở dữ liệu. Bài này kết nối các kiến thức đó thành dự án thực tế: chọn dịch vụ đích, bảo vệ tài nguyên, tự động hóa phát hành, theo dõi độ tin cậy và kiểm soát chi phí sau di chuyển.

**Mục tiêu**: chuyển hệ thống ba tầng từ NGINX + Spring Boot + PostgreSQL tại on-premises sang Cloud Run frontend + Cloud Run backend + Cloud SQL for PostgreSQL; có staging test, đường kết nối bảo mật, đồng bộ dữ liệu liên tục và runbook cutover/rollback.

Sau bài học, bạn có thể:

- Lập inventory ứng dụng, dependency graph, RTO/RPO và tiêu chí chấp nhận.
- Chọn rehost hay replatform cho từng tầng và giải thích trade-off.
- Chuẩn bị landing zone, IAM, VPC, connectivity và secret.
- Triển khai frontend/backend lên Cloud Run và kết nối backend đến Cloud SQL qua private IP.
- Dùng Database Migration Service (DMS) cho PostgreSQL với initial load và change data capture (CDC).
- Kiểm tra nhất quán dữ liệu, hiệu năng, bảo mật và độ tin cậy trước cutover.
- Thực hiện cutover với write freeze, theo dõi replication lag và chuyển traffic có kiểm soát.
- Thiết kế rollback đúng khi có hoặc không có dữ liệu mới đã ghi ở hệ thống đích.

**Lưu ý phạm vi**: đây là tài liệu lab, không tự động tạo tài nguyên thật. Các tên project, image, IP, thời hạn và ngưỡng đo là giả định minh họa. Chỉ thực hiện thao tác tạo, sửa, promote hoặc chuyển traffic trên môi trường đã được phê duyệt.

## 1. Kịch bản nguồn: ứng dụng ba tầng

Giả sử hệ thống **Orders** đang chạy trong một phòng máy riêng, với giao diện đặt hàng, API Java Spring Boot và PostgreSQL tự quản lý.

| Tầng | Hạ tầng nguồn | Nhiệm vụ | Phụ thuộc |
|---|---|---|---|
| Presentation | Hai VM NGINX | Trả HTML, reverse proxy đến API | DNS, TLS, API, session |
| Application | Hai VM Java 17/Spring Boot | Xử lý đơn hàng, kiểm tra tồn kho | PostgreSQL, email, object storage |
| Data | PostgreSQL 14 trên VM | Lưu đơn hàng, khách hàng, trạng thái | Disk, backups, WAL, extension |
| Phụ trợ | SMTP/API email, nơi lưu hóa đơn | Gửi thông báo, lưu tệp | Outbound network, credentials |

~~~mermaid
flowchart LR
    USER["Người dùng"] --> DNS["DNS / TLS"]
    DNS --> WEB["NGINX web VMs"]
    WEB --> API["Spring Boot app VMs"]
    API --> PG["PostgreSQL VM"]
    API --> OUT["Email / file storage"]
~~~

### 1.1. Giả định

- App đã có Dockerfile hoặc có thể đóng gói thành container mà không sửa logic lớn.
- Frontend có thể chạy trong một web container; request API được proxy từ phía server.
- Database source là PostgreSQL phiên bản DMS hỗ trợ.
- Nhóm có cửa sổ bảo trì và cách đưa ứng dụng vào chế độ read-only.
- Các tích hợp thanh toán/ERP và IP allowlist sẽ được kiểm tra lại ở cloud.
- Không thay đổi schema nghiệp vụ lớn cùng lúc migration.

### 1.2. Inventory và baseline

| Thuộc tính | Dữ liệu mẫu cần ghi lại |
|---|---|
| Domain production | orders.example.com |
| Người dùng đồng thời | Baseline trong giờ bình thường và giờ cao điểm |
| Request/phút | P50/P95 và peak trong 24 giờ |
| Database size | Bảng, index, WAL, tốc độ tăng mỗi ngày |
| Transactions/giây | Đọc, ghi và truy vấn chậm |
| P95 latency | Theo endpoint từ APM/log |
| RTO mục tiêu | Ví dụ không quá 60 phút trong cutover |
| RPO mục tiêu | Không chấp nhận mất giao dịch đã xác nhận |
| Phụ thuộc ngoài | SMTP, SSO, đối tác thanh toán, object storage |
| Phiên bản | JDK, Spring Boot, PostgreSQL, extension |
| Data compliance | Region, retention, backup, audit và key management |

**RTO** là thời gian gián đoạn tối đa chấp nhận; **RPO** là mức mất dữ liệu tối đa chấp nhận. Đây là mục tiêu nghiệp vụ phải được duyệt, không phải cam kết mặc định của Cloud Run hoặc DMS. RPO gần 0 tại cutover yêu cầu khóa mọi writer nguồn, đợi CDC theo kịp và đối chiếu dữ liệu.

## 2. Khảo sát dependency trước migration

~~~mermaid
flowchart TD
    BROWSER["Browser"] --> WEB["Presentation"]
    WEB --> AUTH["SSO / Identity provider"]
    WEB --> APP["Orders API"]
    APP --> PG["PostgreSQL"]
    APP --> STOCK["Inventory service"]
    APP --> EMAIL["SMTP / Mail API"]
    APP --> FILE["Invoice storage"]
    APP --> AUDIT["Audit / logs"]
~~~

Cần ghi lại latency, giao thức, port, thông tin xác thực, owner và phương án xử lý lỗi trên từng cạnh.

Các câu hỏi quan trọng:

1. Frontend lưu session trong RAM, local disk hay shared store?
2. App có cron, background thread, local file upload hoặc in-memory cache không?
3. PostgreSQL có extension, trigger, stored function, role hoặc sequence đặc thù không?
4. Có batch job, báo cáo hoặc integration ngoài app ghi trực tiếp vào database không?
5. IP, hostname, TLS certificate và SMTP endpoint có hard-code không?
6. Có transaction dài hoặc query khóa bảng trong giờ cao điểm không?
7. Có yêu cầu data residency, PITR, retention và kiểm toán không?
8. Hệ thống nào là source of truth tại từng thời điểm cutover?
9. Có dependency về OS daemon, TCP protocol hoặc file system khiến Cloud Run không phù hợp?
10. DNS TTL và quyền sửa DNS hiện do ai quản lý?

Nếu app phụ thuộc mạnh vào OS daemon hoặc lưu local state, hãy rehost lên Compute Engine trước hoặc bóc tách thành phần. Không chọn Cloud Run chỉ vì có autoscaling nếu ứng dụng chưa phù hợp kiến trúc stateless.

## 3. Chọn chiến lược theo tầng

| Chiến lược | Web/App | Data | Ưu điểm | Đánh đổi |
|---|---|---|---|---|
| Rehost | Compute Engine | Compute Engine hoặc Cloud SQL | Ít sửa code, phù hợp ứng dụng legacy | Cần vận hành VM, patching, backup OS |
| Replatform | Cloud Run hoặc GKE | Cloud SQL | Giảm vận hành máy chủ, autoscaling | Phải container hóa, tách state và cấu hình network/IAM |
| Refactor | Microservices/event-driven | Cloud SQL/Spanner/khác | Linh hoạt dài hạn | Phạm vi, rủi ro và thời gian lớn |

**Bài lab chọn replatform có kiểm soát**: giữ logic Spring Boot và schema PostgreSQL, đóng gói frontend/backend thành container, chuyển dữ liệu sang Cloud SQL bằng DMS. Không refactor business behavior trong cùng release.

Nếu ứng dụng chưa container hóa được, có thể chọn **Migrate to Virtual Machines** theo chu trình onboard → replicate → target details → test-clone → cutover → finalize. Test-clone phải tách biệt môi trường nguồn để tránh side effect, còn cutover VM cần dừng nguồn để final sync. Không thực hiện hai phương án di chuyển cùng lúc với một workload.

## 4. Kiến trúc đích trên Google Cloud

~~~mermaid
flowchart TD
    USER["Browser / mobile"]
    DNS["DNS"]
    LB["HTTPS Load Balancer + Cloud Armor<br/>tùy chọn production"]
    FRONT["Cloud Run: orders-web<br/>Presentation"]
    API["Cloud Run: orders-api<br/>Business logic + IAM"]
    VPC["Custom VPC / subnet<br/>Direct VPC egress"]
    SQL["Cloud SQL for PostgreSQL<br/>Private IP"]
    SM["Secret Manager"]
    OBS["Cloud Logging / Monitoring"]
    ART["Cloud Build / Artifact Registry"]

    USER --> DNS --> LB --> FRONT
    FRONT -->|"HTTPS + ID token"| API
    API --> VPC --> SQL
    API --> SM
    API --> OBS
    FRONT --> OBS
    ART --> FRONT
    ART --> API
~~~

- **Tầng web**: Cloud Run orders-web phục vụ HTML hoặc SSR, proxy lời gọi API qua server-side HTTPS. External HTTPS Load Balancer với serverless NEG là bước tùy chọn cho custom domain, TLS, Cloud Armor và routing.
- **Tầng application**: Cloud Run orders-api chạy Spring Boot. Service từ chối unauthenticated invocation; chỉ frontend service account có roles/run.invoker.
- **Tầng data**: Cloud SQL PostgreSQL private IP. Backend dùng Direct VPC egress và Cloud SQL Java Connector (hoặc một cơ chế driver/TLS phù hợp) để kết nối.

Trong lab, có thể thử trực tiếp bằng URL của Cloud Run thay cho Load Balancer. Với production, chọn ingress/auth, WAF, TLS và domain theo chính sách công ty.

**Cloud Run Direct VPC egress chỉ dành cho traffic đi ra** từ service tới VPC, không biến service thành VM có private IP để gọi vào theo TCP. Frontend gọi backend qua HTTPS, sử dụng Google-signed ID token phù hợp audience.

### Thành phần bắt buộc và tùy chọn

| Dịch vụ | Lab | Mục đích |
|---|---|---|
| Project + billing | Bắt buộc | Phạm vi và tính phí |
| VPC + subnet | Bắt buộc | Private IP path |
| Cloud Run frontend/backend | Bắt buộc | Web và application |
| Cloud SQL for PostgreSQL | Bắt buộc | Data tier |
| Artifact Registry | Bắt buộc | Container image |
| Secret Manager | Khuyến nghị | Quản lý credential |
| Cloud Logging/Monitoring | Bắt buộc | Điều tra, cảnh báo |
| DMS | Bắt buộc cho CDC | Chuyển dữ liệu với downtime thấp |
| Cloud VPN/Interconnect | Tùy source | Kết nối hybrid |
| External HTTPS Load Balancer | Tùy thiết kế | Domain, certificate, WAF |
| Terraform | Khuyến nghị | IaC và review hạ tầng |

## 5. Chuẩn bị landing zone và phân tách môi trường

Ví dụ cấu trúc project:

~~~text
orders-migration-sandbox
orders-migration-staging
orders-production
~~~

Mỗi môi trường nên có state, secret, IAM, budget và network được quản lý riêng. Với tổ chức lớn, dùng landing zone chuẩn, Shared VPC và organization policies thay vì tạo VPC tùy ý ở từng project.

| Tài nguyên | Tên ví dụ |
|---|---|
| Region | asia-southeast1 |
| VPC | orders-vpc |
| Subnet | orders-run-subnet |
| Database instance | orders-db |
| Web service | orders-web |
| API service | orders-api |
| Artifact Registry repository | orders |
| Runtime service accounts | orders-web-sa, orders-api-sa |
| DMS job | orders-postgres-migration |

### 5.1. API cần bật

~~~bash
PROJECT_ID="orders-migration-staging"
REGION="asia-southeast1"

gcloud config set project "$PROJECT_ID"

gcloud services enable \
  compute.googleapis.com \
  run.googleapis.com \
  artifactregistry.googleapis.com \
  cloudbuild.googleapis.com \
  sqladmin.googleapis.com \
  servicenetworking.googleapis.com \
  secretmanager.googleapis.com \
  logging.googleapis.com \
  monitoring.googleapis.com \
  datamigration.googleapis.com \
  --project="$PROJECT_ID"
~~~

Đây là danh sách tối thiểu cho kiến trúc minh họa; DNS, Load Balancing, VPN hoặc CI/CD có thể cần API bổ sung.

### 5.2. IAM runtime

~~~bash
gcloud iam service-accounts create orders-web-sa \
  --display-name="Orders web runtime"

gcloud iam service-accounts create orders-api-sa \
  --display-name="Orders API runtime"
~~~

Cấp quyền tối thiểu:

| Principal | Role phù hợp | Vì sao |
|---|---|---|
| orders-web-sa | roles/run.invoker trên orders-api | Gọi backend đã xác thực |
| orders-api-sa | roles/cloudsql.client | Kết nối Cloud SQL qua Java Connector |
| orders-api-sa | roles/secretmanager.secretAccessor trên secret cụ thể | Đọc password nếu dùng built-in DB user |
| Build/deploy identity | Artifact Registry writer + quyền build/deploy + Service Account User theo phạm vi | Phát hành image và Cloud Run revision |
| DMS migration identity | DMS permissions và source DB replication user | Chuyển database, tách với runtime app |

Nếu dùng IAM database authentication, cần roles/cloudsql.instanceUser và IAM database user/SQL GRANT tương ứng. Không cấp Owner/Editor chỉ để application kết nối database.

## 6. Thiết kế VPC và kết nối private IP

### 6.1. Tạo VPC custom và subnet

~~~bash
gcloud compute networks create orders-vpc \
  --subnet-mode=custom

gcloud compute networks subnets create orders-run-subnet \
  --network=orders-vpc \
  --region="$REGION" \
  --range=10.60.10.0/24 \
  --enable-private-ip-google-access
~~~

Direct VPC egress yêu cầu subnet đủ lớn, tối thiểu /26 theo hướng dẫn Cloud Run. Trong lab dùng /24 để có dư địa cho autoscaling và các revision cũ/mới cùng tồn tại. CIDR không được trùng với mạng on-prem, các subnet khác hoặc dải Private Services Access.

### 6.2. Chuẩn bị Private Services Access cho Cloud SQL

Với Cloud SQL private IP qua Private Services Access, tạo dải riêng dành cho dịch vụ và kết nối service networking. Ví dụ **chỉ thực hiện nếu VPC chưa được cấu hình**:

~~~bash
gcloud compute addresses create google-managed-services-orders-vpc \
  --global \
  --purpose=VPC_PEERING \
  --prefix-length=16 \
  --network="projects/$PROJECT_ID/global/networks/orders-vpc"

gcloud services vpc-peerings connect \
  --service=servicenetworking.googleapis.com \
  --ranges=google-managed-services-orders-vpc \
  --network=orders-vpc \
  --project="$PROJECT_ID"
~~~

Không xóa hoặc thay đổi peering dùng chung tùy tiện: Cloud SQL và dịch vụ khác có thể đang phụ thuộc. Trong production, phần này thường do network team quản lý bằng IaC.

Bài lab chọn DMS tạo **Cloud SQL destination mới**. Sau khi chuẩn bị private service connectivity, chọn network/region trong DMS wizard. Đừng tạo thêm một instance cùng tên bằng gcloud sql instances create nếu DMS sẽ tạo destination.

### 6.3. Hybrid connectivity

| Phương án | Khi nào dùng | Lưu ý |
|---|---|---|
| Cloud VPN | Thử nghiệm hoặc hybrid traffic vừa phải | IPsec, route, HA |
| Dedicated/Partner Interconnect | Thông lượng lớn, yêu cầu mạng doanh nghiệp | Cần circuit, BGP và dự phòng |
| DMS connectivity method | Tùy engine và môi trường nguồn | Có thể dùng private connectivity, allowlist hoặc reverse SSH |

Chọn chính xác method mà DMS hỗ trợ cho source. Không mở TCP 5432 toàn Internet để giải quyết nhanh lỗi migration. Kiểm tra firewall, route, DNS và chứng thực theo từng phương pháp.

## 7. Chuẩn bị ứng dụng chạy trên Cloud Run

Cloud Run phù hợp với service stateless. Cần loại bỏ phụ thuộc vào trạng thái máy chủ:

| Hiện trạng | Thay đổi |
|---|---|
| HTTP session trong RAM/local NGINX | Stateless token hoặc shared store |
| Upload file lên disk | Cloud Storage hoặc storage phù hợp |
| Cron/background jobs trên VM | Cloud Scheduler, Cloud Tasks hoặc Cloud Run Jobs |
| DB host/IP hard-coded | Biến môi trường và Secret Manager |
| TLS cert nằm trong container | TLS tại Cloud Run/load balancer |
| Log file local | Structured logs ra stdout/stderr |
| HTTP response trả trước khi xử lý xong background | Bàn giao tác vụ vào queue bền vững |
| Outbound API giới hạn IP | Kiểm tra VPC egress/NAT/static IP nếu cần |

**Không refactor hệ thống lên microservices trong cùng lần cutover.** Đóng gói app hiện có, giữ hành vi, chạy regression tests rồi tối ưu sau.

### 7.1. Dockerfile mẫu cho backend

~~~dockerfile
FROM eclipse-temurin:17-jre
WORKDIR /app
COPY target/orders-api.jar app.jar

ENV PORT=8080
EXPOSE 8080

ENTRYPOINT ["java", "-jar", "/app/app.jar"]
~~~

App Spring Boot phải listen trên 0.0.0.0 và port do Cloud Run cung cấp. Ví dụ có thể đặt các giá trị qua Spring config hoặc biến môi trường:

~~~properties
server.port=${PORT:8080}
management.endpoints.web.exposure.include=health,info
spring.datasource.hikari.maximum-pool-size=5
spring.datasource.hikari.connection-timeout=10000
~~~

Đoạn trên chỉ là ví dụ các tham số; trong bản production, server.port nên lấy từ biến môi trường PORT hoặc dùng cấu hình Spring Boot tương ứng. Không lưu password trong image hoặc Dockerfile.

## 8. Triển khai backend lên Cloud Run

Ví dụ URI image (image đã được build/push trước):

~~~text
asia-southeast1-docker.pkg.dev/PROJECT_ID/orders/orders-api:v1
asia-southeast1-docker.pkg.dev/PROJECT_ID/orders/orders-web:v1
~~~

### 8.1. Kết nối database

Giả sử Cloud SQL destination có:

~~~text
INSTANCE_CONNECTION_NAME=PROJECT_ID:asia-southeast1:orders-db
DB_NAME=orders
DB_USER=orders_runtime
~~~

Đối với Spring Boot JDBC với Cloud SQL Java Connector:

~~~properties
spring.datasource.url=jdbc:postgresql:///orders?cloudSqlInstance=${INSTANCE_CONNECTION_NAME}&socketFactory=com.google.cloud.sql.postgres.SocketFactory&ipTypes=PRIVATE&cloudSqlRefreshStrategy=lazy&sslmode=disable
spring.datasource.username=${DB_USER}
spring.datasource.password=${DB_PASSWORD}
~~~

Application lấy password từ DB_PASSWORD được cấp qua Secret Manager, không hard-code vào cấu hình. Socket factory yêu cầu pgJDBC và dependency Cloud SQL PostgreSQL Socket Factory phù hợp. Với **đường connector**, TLS được quản lý bởi connector nên ví dụ dùng sslmode=disable ở lớp pgJDBC; không dùng như vậy khi kết nối PostgreSQL trực tiếp qua IP nếu chưa có TLS thay thế.

Nếu chưa promote DMS destination, không chạy API test có INSERT/UPDATE vào database đang CDC. Sử dụng database staging độc lập hoặc test read-only đã được kiểm soát.

### 8.2. Lệnh triển khai ví dụ

~~~bash
API_SA="orders-api-sa@$PROJECT_ID.iam.gserviceaccount.com"
API_IMAGE="asia-southeast1-docker.pkg.dev/$PROJECT_ID/orders/orders-api:v1"

gcloud run deploy orders-api \
  --image="$API_IMAGE" \
  --region="$REGION" \
  --service-account="$API_SA" \
  --no-allow-unauthenticated \
  --ingress=all \
  --network=orders-vpc \
  --subnet=orders-run-subnet \
  --vpc-egress=private-ranges-only \
  --set-env-vars="INSTANCE_CONNECTION_NAME=$PROJECT_ID:$REGION:orders-db,DB_NAME=orders,DB_USER=orders_runtime" \
  --set-secrets="DB_PASSWORD=orders-db-password:latest" \
  --max-instances=5
~~~

Các tiền điều kiện cần có: secret đã tạo và cấp secretAccessor cho API SA; Cloud SQL target đã tồn tại; app image đã push; runtime identity có Cloud SQL Client; network/subnet đúng region. Lệnh dùng --ingress=all nhưng **không bật unauthenticated invocation**; IAM vẫn chặn caller không được cấp run.invoker. Nếu môi trường yêu cầu network ingress chặt hơn, phải thiết kế route nội bộ phù hợp thay vì sao chép trực tiếp ví dụ.

### 8.3. Connection pool budget

Mỗi Cloud Run instance có pool riêng. Với 5 max instances và Hikari maximumPoolSize=5, có thể cần đến khoảng 25 physical connections, chưa tính migration tool, console và workload khác.

\[
\text{Connection budget} \approx \text{Max Cloud Run instances} \times \text{Pool size}
\]

Không tăng pool vô hạn khi gặp timeout. Xem Cloud SQL active connections, slow query, CPU, locks và pool acquire wait.

## 9. Triển khai frontend và IAM service-to-service

Frontend là Cloud Run web service public, gọi backend bằng Google-signed ID token. Trình duyệt không được nhận service account ID token.

### 9.1. Cấp quyền gọi backend

~~~bash
WEB_SA="orders-web-sa@$PROJECT_ID.iam.gserviceaccount.com"

gcloud run services add-iam-policy-binding orders-api \
  --region="$REGION" \
  --member="serviceAccount:$WEB_SA" \
  --role="roles/run.invoker"
~~~

### 9.2. Tạo ID token trong frontend server

Ví dụ Node.js web server có dependency google-auth-library:

~~~javascript
const {GoogleAuth} = require("google-auth-library");
const auth = new GoogleAuth();
const backendUrl = process.env.BACKEND_URL;

async function fetchOrders() {
  const client = await auth.getIdTokenClient(backendUrl);
  const response = await client.request({
    url: backendUrl + "/api/orders",
    method: "GET"
  });
  return response.data;
}
~~~

getIdTokenClient tạo client lấy token với audience dành cho Cloud Run backend. Browser chỉ nhận dữ liệu qua frontend; user authentication và authorization ở tầng ứng dụng vẫn phải được thực hiện theo nghiệp vụ.

### 9.3. Deploy web

~~~bash
API_URL=$(gcloud run services describe orders-api \
  --region="$REGION" \
  --format="value(status.url)")

WEB_IMAGE="asia-southeast1-docker.pkg.dev/$PROJECT_ID/orders/orders-web:v1"

gcloud run deploy orders-web \
  --image="$WEB_IMAGE" \
  --region="$REGION" \
  --service-account="$WEB_SA" \
  --allow-unauthenticated \
  --set-env-vars="BACKEND_URL=$API_URL" \
  --max-instances=5
~~~

--allow-unauthenticated chỉ phù hợp khi website là public. Nếu service chỉ phục vụ nhân viên, giữ xác thực/IAP hoặc mô hình ingress theo chính sách. Với production có thể đặt frontend sau HTTPS Load Balancer với serverless NEG và Cloud Armor.

## 10. Chuyển PostgreSQL bằng Database Migration Service

DMS continuous migration gồm **initial load** dữ liệu hiện có và **change data capture** để đồng bộ thay đổi mới trong khi source vẫn tiếp nhận ghi. Nhờ vậy downtime tại cutover có thể giảm, nhưng vẫn phải dừng writes source ở bước cuối.

~~~mermaid
flowchart LR
    SRC["On-prem PostgreSQL<br/>Primary / writes"] --> SNAP["Initial load"]
    SRC --> WAL["Logical replication / WAL"]
    SNAP --> DMS["DMS migration job"]
    WAL --> DMS
    DMS --> DST["Cloud SQL PostgreSQL<br/>Destination / no app writes"]
    DST --> PROMOTE["Write freeze → lag gần 0 → promote"]
    PROMOTE --> API["Cloud Run Orders API"]
~~~

### 10.1. Kiểm tra source

Trước khi chạy job, đảm bảo source được hỗ trợ, backup đã thử restore, replication user có quyền cần thiết, cấu hình pg_hba.conf và firewall phù hợp, đủ WAL và connection capacity, đã kiểm tra schema/extension.

Các truy vấn kiểm tra:

~~~sql
SHOW server_version;
SHOW wal_level;
SHOW max_replication_slots;
SHOW max_wal_senders;
SHOW max_worker_processes;

SELECT extname, extversion
FROM pg_extension
ORDER BY extname;
~~~

Với **standard continuous migration** của PostgreSQL self-managed, DMS yêu cầu cấu hình logical replication/pglogical, migration user và replication slots/WAL senders phù hợp. Thay đổi WAL settings có thể cần restart PostgreSQL; không làm vậy trên production nếu chưa có maintenance approval.

### 10.2. Kiểm tra schema

| Hạng mục | Rủi ro | Cách xử lý |
|---|---|---|
| Bảng thiếu primary key | UPDATE/DELETE có thể không được replicate theo standard pglogical mode | Thêm PK hoặc chọn migration mode hỗ trợ REPLICA IDENTITY |
| Extension | Cloud SQL không hỗ trợ mọi extension | Đối chiếu danh sách và test |
| Schema DDL | DDL thông thường không tự replicate trong standard flow | Freeze schema hoặc dùng phương pháp hỗ trợ |
| Sequence | Giá trị sau migration có thể cần hiệu chỉnh | Kiểm tra MAX(id), last_value, ownership |
| Role/GRANT | Permission khác ở destination | Kiểm kê, tạo lại và test |
| Timezone/collation | Kết quả so sánh/sắp xếp khác | Test contract/query |
| Long transaction/WAL | CDC lag và WAL giữ quá lâu | Giám sát replication slot, lag, disk |
| Large objects | Khả năng hỗ trợ phụ thuộc method | Test theo DMS known limitations |

DMS còn có quick-start mode dùng pgnative và một số hành vi khác so với standard pglogical. **Không trộn điều kiện giữa hai mode**; bài này minh họa standard continuous migration.

### 10.3. Tạo job qua Console

1. Mở **Database Migration Service → Migration jobs**.
2. Chọn source PostgreSQL và destination Cloud SQL for PostgreSQL.
3. Chọn migration type **Continuous**.
4. Tạo source connection profile và migration user.
5. Chọn **new Cloud SQL destination instance**, region, VPC và private IP.
6. Thiết lập connectivity từ migration service/destination tới source.
7. Nhấn **Test job** và sửa mọi lỗi trước khi start.
8. Chạy migration job; theo dõi initial load, CDC lag, source WAL và destination.

DMS là dịch vụ theo region; connection profiles, migration job và destination phải được thiết lập đúng location. Khi DMS tạo destination, tránh thao tác DDL/DML lên dữ liệu đang migrate vì có thể gây conflict.

Truy vấn trạng thái job:

~~~bash
gcloud database-migration migration-jobs list \
  --region="$REGION" \
  --project="$PROJECT_ID"

gcloud database-migration migration-jobs describe orders-postgres-migration \
  --region="$REGION" \
  --project="$PROJECT_ID"
~~~

Không bắt đầu cutover nếu initial load chưa hoàn tất hoặc CDC lag đang tăng.

### 10.4. Bảo vệ database destination

Trong standard continuous migration:

- Destination có thể writable về kỹ thuật nhưng **không được để app hoặc batch ghi vào các bảng đang replicate**.
- Chỉ dùng đọc có kiểm soát hoặc database staging độc lập trong vòng test.
- Automated backup/PITR có thể bị tạm dừng khi migration tới new destination; sau promotion phải bật và kiểm tra lại.
- Chưa tạo read replica cho destination đến khi promote thành công.
- DMS có thể điều chỉnh Cloud SQL settings; nếu dùng Terraform, reconcile configuration drift **sau** migration, không apply đè giữa CDC.

## 11. Kiểm thử dữ liệu và hành vi ứng dụng

### 11.1. So sánh dữ liệu

Ví dụ truy vấn:

~~~sql
SELECT COUNT(*) AS orders_count,
       MIN(created_at) AS earliest_order,
       MAX(created_at) AS latest_order
FROM public.orders;

SELECT status, COUNT(*) AS total
FROM public.orders
GROUP BY status
ORDER BY status;

SELECT COUNT(*) AS customers_count
FROM public.customers;
~~~

Đếm row ở hai thời điểm khác nhau khi source vẫn ghi **không chứng minh nhất quán**. Chỉ so sánh trên snapshot nhất quán hoặc sau write freeze và CDC lag gần 0. Nên đối chiếu checksum theo batch/primary key, tổng đơn hàng theo ngày, trạng thái nghiệp vụ và dữ liệu đặc thù.

### 11.2. Bộ kiểm thử ứng dụng

| Nhóm | Bài kiểm tra | Tiêu chí |
|---|---|---|
| API | GET /health, GET /api/orders | 2xx và schema đúng |
| Auth | User thiếu role | 401/403, không lộ dữ liệu |
| Business | Tạo, cập nhật, hủy đơn | Transaction/audit đúng |
| Idempotency | Gửi trùng request key | Không tạo hai đơn |
| Data | Count, totals, status, sample IDs | Đúng theo snapshot |
| Performance | Load giờ cao điểm | P95/P99 đáp ứng SLO |
| Reliability | DB failover ở staging | Retry giới hạn, không mất giao dịch |
| Security | IAM, Secret Manager, egress, TLS | PASS |
| Observability | Log, metric, trace | Truy được root cause |

Trước promote, chỉ làm writes test ở **DB staging độc lập**, không dùng DMS destination đang CDC.

### 11.3. Kết nối phụ trợ

Nếu app dùng payment gateway hoặc email, sử dụng sandbox endpoint và dữ liệu giả lập. Kiểm tra allowlist IP, SMTP egress, DNS, timeout và credentials sau khi chuyển workload. Không gửi email thật hoặc thực hiện thanh toán thật trong migration rehearsal.

## 12. Dashboard, baseline và cảnh báo

Tạo dashboard trước cutover:

| Tín hiệu | Nguồn | Ý nghĩa |
|---|---|---|
| HTTP requests/4xx/5xx | Cloud Run/Load Balancer | Lưu lượng và lỗi |
| P50/P95/P99 latency | Monitoring / traces | SLO |
| Cloud Run instance count | Cloud Run | Autoscaling và cold start |
| DB CPU, memory, connections | Cloud SQL | Capacity |
| Slow query/lock waits | Cloud SQL Query Insights | Bottleneck |
| DMS replication lag | Database Migration Service | Source → target delay |
| PostgreSQL source WAL/disk | On-prem metrics | Nguy cơ đầy disk |
| Secret/permission errors | Cloud Audit Logs/app logs | IAM regressions |
| Budget alerts | Cloud Billing | Chi phí migration |

Gắn environment, version, image digest và release ID vào log để đối chiếu nguồn/đích. Không ghi password, token hoặc dữ liệu khách hàng trong log.

## 13. Diễn tập cutover và tiêu chí Go/No-Go

Một runbook cutover cần người chịu trách nhiệm, thao tác, công cụ, bằng chứng xác minh và điều kiện dừng. Diễn tập staging với dataset đại diện trước.

### 13.1. DNS và load balancer

Giảm DNS TTL **từ trước** cửa sổ bảo trì theo chính sách. TTL thấp không bảo đảm mọi cache/client chuyển tức thì; keep-alive và proxy có thể giữ kết nối cũ. Nếu dùng global HTTPS Load Balancer, cấu hình serverless NEG, certificate, URL map và Cloud Armor trước, thử với hostname staging.

### 13.2. Vai trò

| Vai trò | Trách nhiệm |
|---|---|
| Migration lead | Quyết định Go/No-Go |
| Database lead | Source freeze, CDC lag, DMS promote |
| App lead | Cloud Run revisions, smoke tests |
| Network/DNS lead | LB/DNS/TLS và connectivity |
| Security lead | IAM, secrets, audit, WAF |
| Business owner | Xác nhận luồng đơn hàng và dữ liệu |

### 13.3. Tiêu chí Go

- DMS initial load hoàn tất, CDC ổn định.
- Replication lag dưới ngưỡng và có xu hướng giảm.
- Backup/source recovery point đã xác minh restore.
- Image digest và test kết quả đã được duyệt.
- IAM, private SQL connection, secret, metrics/alerts PASS.
- Người dùng đã được thông báo maintenance window.
- Runbook rollback theo giai đoạn đã được phê duyệt.

Không Go khi WAL tăng không kiểm soát, DMS error chưa xử lý hoặc không có cách xử lý writes mới ở destination.

## 14. Runbook cutover thực tế

| Mốc | Hành động | Bằng chứng |
|---|---|---|
| T-30 phút | Check DMS, DB, image, DNS, secrets, dashboard | Go/No-Go |
| T-10 phút | Tắt batch, scheduler, integration writers | Logs và job state |
| T0 | Source app vào maintenance/read-only; khóa mọi writes source | Không còn write transactions |
| T+ | Chờ transaction cũ kết thúc và CDC lag gần 0 | DMS metrics, SQL checks |
| T+ | **Promote** DMS migration job | Job và Cloud SQL state thành công |
| T+ | Kiểm tra users, GRANT, sequence, schema, backup/PITR | SQL + Cloud SQL settings |
| T+ | Bật Cloud Run production revision, xác minh SQL connection | Health và logs |
| T+ | Chuyển frontend/LB/DNS theo kế hoạch | Request logs |
| T+ | Smoke test GET, authenticated POST, idempotency | Business sign-off |
| T+ | Giám sát P95/5xx/DB connection trong hypercare | Dashboard |
| T+N ngày | Decommission nguồn sau approval/retention | Handover |

**Tại T0 phải chặn mọi writer**, không chỉ đổi trang web sang maintenance. Queue consumer, cron, ETL, admin tool và integration đối tác có thể vẫn ghi trực tiếp PostgreSQL.

### 14.1. DMS promotion

Trong Console, chọn job ở pha CDC, kiểm tra lag và sử dụng **Promote**. Promotion tách destination khỏi source và đưa Cloud SQL thành primary độc lập.

DMS có thể cho promote khi lag còn khác 0, nhưng cách đó làm tăng nguy cơ mất thay đổi. Bài lab đặt No-Go nếu lag chưa theo kịp, trừ khi business owner phê duyệt RPO khác rõ ràng.

Sau promote:

- Test read/write và DB permissions trên Cloud SQL.
- Kiểm tra schema, sequence, extension, migration version.
- Bật lại hoặc xác nhận backup/PITR và retention.
- Reconcile Terraform drift nếu DMS tạm đổi Cloud SQL settings.
- Xác nhận có recovery point mới.

### 14.2. Chuyển traffic

Traffic split giữa các Cloud Run revisions chỉ an toàn khi chúng dùng cùng một primary database hợp lệ và tương thích schema. **Không duy trì hai primary nhận writes song song**.

Với migration database, nên chuyển writer một lần sau promotion, còn frontend có thể mở cho nhóm canary rồi tăng dần. Nếu DNS cache giữ traffic cũ, source app phải tiếp tục read-only hoặc hiển thị maintenance để không phát sinh writes vào source đã cũ.

## 15. Rollback trước và sau writes ở target

Rollback không chỉ là chuyển DNS. Sau promote, DMS replication từ source sang target đã kết thúc. Nếu Cloud SQL nhận đơn hàng mới, PostgreSQL source cũ **không có các giao dịch đó**.

### Trường hợp A: target chưa nhận writes

1. Giữ maintenance hoặc chặn traffic.
2. Xác nhận source vẫn có thể nhận writes và không bị ứng dụng khác sửa dữ liệu.
3. Chuyển connection/frontend/LB về source theo runbook.
4. Mở lại source writes khi đã xác định primary duy nhất.
5. Ghi nhận thời điểm và nguyên nhân rollback.

### Trường hợp B: target đã nhận writes

**Không đổi DNS thẳng về source cũ.** Các phương án cần thiết kế trước:

- Dừng writes ở target; export/reconcile giao dịch mới theo business key và transaction ID.
- Dùng reverse sync tương thích đã được thiết kế và thử nghiệm riêng (phức tạp).
- Ưu tiên **fix-forward** nếu Cloud SQL đã là source of truth: sửa revision/configuration hoặc phục hồi dịch vụ trên target.

Quyết định phải do database lead và business owner phê duyệt, duy trì RPO yêu cầu dù RTO có thể kéo dài.

| Sự cố | Hành động ưu tiên | Rủi ro |
|---|---|---|
| Frontend lỗi, DB bình thường | Rollback Cloud Run web revision | Thấp |
| API code lỗi, schema còn tương thích | Rollback API revision | Thấp/vừa |
| Schema không tương thích | Dừng writes, evaluate fix-forward | Cao |
| Cloud SQL IAM/network lỗi, chưa có writes | Sửa config hoặc rollback source | Có thể thấp |
| Cloud SQL đã nhận writes mới | Reconcile/reverse sync hoặc fix-forward | Cao nếu đổi DNS đơn thuần |
| CDC lag chưa về gần 0 trước cutover | Không Go | Tránh mất dữ liệu |

## 16. Nghiệm thu và hypercare

### Gate kỹ thuật

- Frontend/backend chạy ở project/region mong đợi.
- HTTPS, IAM, authorization và ingress đúng thiết kế.
- Cloud SQL là **primary duy nhất**, kết nối private hoạt động.
- Dữ liệu đối chiếu theo SQL và business aggregates.
- Database users, GRANT, sequence, extension hợp lệ.
- P95/5xx nằm trong SLO; không có tăng trưởng connection bất thường.
- Audit logs, metrics, traces và alerts có tín hiệu.
- Backups, PITR và restore procedure của Cloud SQL được xác minh.
- Runbook DR và ownership được cập nhật.

### Gate nghiệp vụ

1. Đăng nhập với user hợp lệ.
2. Tạo đơn hàng mới.
3. Xem đơn từ session thứ hai.
4. Cập nhật/hủy theo role.
5. Kiểm tra hóa đơn, tồn kho, notification và payment sandbox.
6. Kiểm tra báo cáo tổng hợp khớp giao dịch mới.
7. Xác nhận không có đơn trùng do retry/cutover.

Trong 24–72 giờ hypercare (thời lượng do tổ chức quyết định), giám sát P95 latency, 5xx, DB CPU/connections, slow queries, scaling, cost và feedback người dùng. Chỉ decommission source sau business sign-off, backup/retention và không còn dependency.

## 17. Bảo mật và chi phí migration

### 17.1. Bảo mật

- IAM quyền tối thiểu, tách service account web, API, deploy và migration.
- Service-to-service dùng ID token/roles.run.invoker; không truyền token cho browser.
- Cloud SQL private IP, database user riêng và Secret Manager.
- Bảo vệ ingress/egress; dùng Cloud Armor nếu website public cần WAF.
- Audit log các thay đổi IAM, database, promotion, deployment và breakglass.
- Áp dụng data residency, retention, TLS/mã hóa theo quy định.

### 17.2. Chi phí

| Dịch vụ | Yếu tố tính phí |
|---|---|
| Cloud Run | CPU/memory, request, min instances, concurrency |
| Cloud SQL | Machine, HA, storage, backups, network |
| Artifact Registry | Storage, transfer |
| Load Balancing/Cloud Armor | Policy, rule, traffic |
| DMS | Migration service, destination database, connectivity |
| Cloud VPN/Interconnect | Tunnel/gateway/circuit |
| Cloud Logging/Monitoring | Ingestion, retention, metrics |
| Data transfer | Egress, hybrid, cross-region traffic |

Tạo budget alerts trước migration. Chi phí tăng tạm thời khi nguồn/đích chạy song song, initial load, performance test và hypercare. Không hạ cấu hình Cloud SQL quá mức trước cutover chỉ để giảm giá.

## 18. Lỗi thường gặp trong thực hành

| Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| DMS Test job lỗi | Sai user, pg_hba.conf, route, port, TLS | Kiểm tra connection profile và replication privileges |
| CDC lag tăng | WAL lớn, transaction dài, network nghẽn | Xem source WAL, slots, lag, bandwidth |
| Destination thiếu UPDATE/DELETE | Bảng thiếu primary key trong standard mode | Bổ sung PK hoặc đổi replication strategy hỗ trợ |
| DMS replication conflict | App/batch ghi vào destination | Dừng writer target, phân tích và phục hồi job |
| Extension khác biệt | Không tương thích Cloud SQL | Đối chiếu allowed extensions |
| Cloud Run API 403 | Thiếu invoker role/ID token sai audience | Kiểm tra web SA và backend IAM |
| API không đến Cloud SQL | Sai VPC, peering, egress hoặc quyền | Kiểm tra network/roles và connector |
| API trả 500 | Thiếu secret, DB user/GRANT, schema mismatch | Xem logs, SQL errors |
| DB hết connections | Pool mỗi Cloud Run instance quá lớn | Tính instance × pool, tune queries/capacity |
| Custom domain lỗi | DNS/LB/TLS/NEG sai | Kiểm tra TTL, certificate, backend mapping |
| Traffic vẫn vào source | DNS cache/keep-alive | Giữ source read-only, theo dõi logs |
| Rollback sau khi target đã ghi | Thiếu reverse sync | Dừng writes, fix-forward hoặc reconciliation |

## 19. Checklist bàn giao

- [ ] Inventory, dependency graph, owners đầy đủ.
- [ ] Baseline CPU/memory/requests/DB/P95 và RTO/RPO được duyệt.
- [ ] Backup source đã test restore.
- [ ] Chọn rehost/replatform phù hợp tương thích workload.
- [ ] Project, VPC, CIDR, VPN/Interconnect nếu cần đã sẵn sàng.
- [ ] Cloud SQL private IP, source connection và DMS connectivity PASS.
- [ ] IAM service account tách theo chức năng.
- [ ] Images đã build, test, scan, ghi digest.
- [ ] Web service gọi API bằng ID token; backend chặn unauthenticated.
- [ ] Secret Manager/DB user/GRANT hợp lệ.
- [ ] Initial load xong, CDC lag theo dõi ổn định.
- [ ] Không ghi vào DMS destination khi CDC.
- [ ] Unit/integration/E2E/load test PASS trên staging.
- [ ] Data counts/checksums/roles/sequences đã đối chiếu.
- [ ] DNS/TLS/LB và maintenance mode đã thử.
- [ ] Cutover runbook có Go/No-Go và owner.
- [ ] Mọi writer nguồn bị freeze trước promotion.
- [ ] CDC lag gần 0 trước promotion.
- [ ] Cloud SQL backup/PITR được kiểm tra sau promote.
- [ ] Production smoke tests và business sign-off PASS.
- [ ] Hypercare monitoring, incident runbook, budget alert hoạt động.
- [ ] Source chỉ decommission sau retention và approval.

## 20. Câu hỏi tự kiểm tra

**1. Vì sao không chỉ chuyển hai web VM lên cloud rồi giữ PostgreSQL ở on-prem mãi?**

Latency app–DB qua VPN có thể tăng, hybrid connectivity thêm điểm lỗi và cutover chưa hoàn tất. Đây chỉ là lựa chọn có chủ đích nếu đã đo được hiệu năng và rủi ro.

**2. Rehost khác replatform thế nào?**

Rehost chuyển VM sang Compute Engine với ít đổi code; replatform dùng Cloud Run/Cloud SQL, giảm vận hành OS nhưng yêu cầu container hóa, tách state, IAM và VPC connectivity.

**3. DMS continuous migration mang lại điều gì?**

Initial load rồi CDC giúp target theo kịp writes trong khi source hoạt động, giảm lượng dữ liệu cần chuyển ở cutover. Tuy nhiên vẫn cần write freeze, lag về gần 0 và promote.

**4. Vì sao không ghi vào Cloud SQL destination lúc CDC?**

Source vẫn là primary. Writes tại destination có thể xung đột với DMS, gây lỗi replication hoặc dữ liệu lệch.

**5. Frontend có được đưa service account ID token vào JavaScript gửi browser?**

Không. Frontend server gọi backend bằng ID token riêng và roles/run.invoker. Browser chỉ nhận response và dữ liệu theo quyền user.

**6. Muốn RPO gần 0, điều kiện nào quan trọng nhất?**

Dừng mọi writer nguồn, đợi CDC theo kịp, xác minh tính nhất quán rồi mới promote. Bật DMS đơn thuần không bảo đảm RPO bằng 0.

**7. Vì sao rollback DNS có thể gây mất đơn hàng sau promotion?**

Source cũ thiếu dữ liệu target đã ghi sau cutover. Cần reconcile, reverse sync được thử nghiệm hoặc fix-forward.

## 21. Tài liệu tham khảo

- [Google Cloud Migration Center](https://cloud.google.com/migration-center/docs/migration-center-overview)
- [Migrate to Virtual Machines overview](https://cloud.google.com/migrate/virtual-machines/docs/5.0/discover/overview)
- [Migrate individual VMs: lifecycle, test-clone, cutover](https://cloud.google.com/migrate/virtual-machines/docs/5.0/migrate/migrating-vms)
- [Database Migration Service for PostgreSQL overview](https://cloud.google.com/database-migration/docs/postgres/overview)
- [DMS PostgreSQL: Configure source](https://cloud.google.com/database-migration/docs/postgres/configure-source-database)
- [DMS PostgreSQL: Create migration job](https://cloud.google.com/database-migration/docs/postgres/create-migration-job)
- [DMS PostgreSQL: Known limitations](https://cloud.google.com/database-migration/docs/postgres/known-limitations)
- [DMS PostgreSQL: Promote migration](https://cloud.google.com/database-migration/docs/postgres/promote-migration)
- [Cloud SQL: Configure private services access](https://cloud.google.com/sql/docs/postgres/configure-private-services-access)
- [Cloud SQL: Connect from Cloud Run](https://cloud.google.com/sql/docs/postgres/connect-run)
- [Cloud Run: Direct VPC egress](https://cloud.google.com/run/docs/configuring/vpc-direct-vpc)
- [Cloud Run: Service-to-service authentication](https://cloud.google.com/run/docs/authenticating/service-to-service)
- [External Application Load Balancer](https://cloud.google.com/load-balancing/docs/https)
- [Cloud VPN overview](https://cloud.google.com/network-connectivity/docs/vpn/concepts/overview)

