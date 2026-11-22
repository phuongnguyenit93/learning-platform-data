# Private IP, Private Service Connect và kết nối Cloud SQL

Một API Java chạy trên Cloud Run cần truy cập Cloud SQL for PostgreSQL nhưng không muốn mở database ra Internet. Có hai lựa chọn kết nối riêng tư dễ bị nhầm: **Private IP qua Private Services Access (PSA)** và **Private Service Connect (PSC)**. Cả hai đều dùng địa chỉ nội bộ nhưng khác cách tổ chức mạng, chia sẻ dịch vụ giữa các VPC và vận hành DNS. Chọn sai có thể khiến ứng dụng báo `connection timeout`, phát sinh rủi ro phân quyền hoặc buộc thay đổi hạ tầng khi mở rộng sang nhiều project.

Bài thuộc chương **Cloud SQL và AlloyDB** của học phần **CLOUD_PROVIDERS_GCP**. Nội dung kết nối kiến thức project/IAM/VPC với Compute Engine, GKE, Cloud Run, Cloud SQL, bảo mật, tự động hóa triển khai và theo dõi độ tin cậy/chi phí. Trọng tâm là **cách thiết kế, cấu hình và chẩn đoán đường mạng đến Cloud SQL**, không phải quản trị SQL schema chuyên sâu.

Sau bài học, bạn có thể:

- Phân biệt **public IP**, **private IP qua PSA** và **PSC endpoint**.
- Thiết lập dải IP dành cho PSA, kết nối Service Networking và tạo Cloud SQL instance không có public IP.
- Cấu hình một Cloud SQL instance bật PSC, tạo endpoint trong consumer VPC và kiểm tra trạng thái `ACCEPTED`.
- Sử dụng private DNS để ứng dụng kết nối PSC từ nhiều VPC, phân biệt DNS name và instance connection name.
- Kết nối Java qua Cloud SQL Java Connector với `ipTypes=PRIVATE` hoặc `ipTypes=PSC`, dùng ADC/IAM và giới hạn JDBC pool.
- Xác định đường mạng đúng cho Compute Engine, GKE và Cloud Run; phân biệt **network connectivity**, **IAM** và **database authentication**.
- Tìm nguyên nhân lỗi `NETWORK_NOT_PEERED`, DNS lookup, `403`, timeout, `too many connections` và xử lý chuyển đổi có kiểm soát.

> **Phạm vi thực hành:** các lệnh tạo VPC, address range, Cloud SQL instance, PSC endpoint và DNS có thể phát sinh chi phí hoặc ảnh hưởng hệ thống đang chạy. Tên project, IP, instance, service account là ví dụ; chỉ thao tác trên môi trường lab được phép. Không xóa dải PSA, peering hoặc endpoint còn ứng dụng sử dụng.

## 1. Bức tranh tổng quan: ba cách kết nối

| Đường truy cập | Địa chỉ phía ứng dụng | Phù hợp | Điều kiện chính |
|---|---|---|---|
| **Public IP** | Cloud SQL public IP/hostname | Client hợp lệ không cùng VPC, tình huống được phép qua Internet | Firewall/authorized networks hoặc Cloud SQL Auth Proxy/Connector; TLS/auth |
| **Private IP qua PSA** | Private IP của Cloud SQL cấp từ dải dành cho dịch vụ | Workload cùng VPC hoặc có route được hỗ trợ tới VPC đã cấu hình | Dải IP `VPC_PEERING`, Service Networking connection, route, DB auth |
| **Private Service Connect** | **PSC endpoint internal IP** thuộc consumer subnet, hoặc DNS trỏ tới IP đó | Nhiều nhóm/project/VPC cùng truy cập một Cloud SQL instance | Cloud SQL bật PSC, service attachment, endpoint `ACCEPTED`, DNS/IAM/DB auth |

**Private IP ≠ Private Service Connect.** Cloud SQL private IP truyền thống thường dựa trên **Private Services Access**; PSC sử dụng **service attachment** do Cloud SQL xuất bản và **forwarding rule/endpoint** do consumer VPC sở hữu. Một Cloud SQL instance mới hoặc đã được nâng cấp có thể hỗ trợ **cả PSA và PSC** theo tính năng/điều kiện áp dụng; không phải hai chế độ luôn loại trừ nhau.

### Minh họa mạng

~~~mermaid
flowchart TD
  subgraph APP["Project ứng dụng / VPC consumer"]
    A["Cloud Run (Direct VPC egress) / GKE / VM"]
    E["PSC endpoint: 10.20.0.10"]
  end
  subgraph NET["Private Services Access"]
    P["Service Networking VPC peering"]
  end
  subgraph SQL["Project database / Cloud SQL"]
    S["Cloud SQL PostgreSQL"]
    T["Service attachment (PSC)"]
  end
  A -->|"Private IP qua PSA"| P
  P --> S
  A -->|"PSC private endpoint"| E
  E --> T
  T --> S
~~~

Mạng riêng tư giúp hạn chế bề mặt truy cập, nhưng **không tự mã hóa mọi kết nối SQL** và **không thay thế password hoặc IAM database authentication**. Khi kết nối thẳng bằng JDBC TCP, cấu hình TLS và verify server identity theo yêu cầu; dùng **Cloud SQL Auth Proxy** hoặc **Cloud SQL Language Connectors** khi muốn lớp xác thực/kết nối được hỗ trợ tự quản lý mã hóa.

## 2. Private Services Access (PSA) hoạt động ra sao?

PSA dành một dải địa chỉ IP **không chồng lấn** trong VPC của bạn cho các dịch vụ Google được quản lý. **Service Networking** thiết lập một kết nối peering tới mạng service producer; Cloud SQL nhận private IP từ dải này.

~~~text
VM/GKE/Cloud Run egress trong VPC app-vpc
       │
       │ route đến dải địa chỉ PSA
       ▼
Private Services Access (Service Networking peering)
       │
       ▼
Cloud SQL instance private IP (không cần public IP)
~~~

**Các điểm thiết kế:**

- IP range dành cho PSA cần được quy hoạch dài hạn: không trùng subnet ứng dụng, on-premises hoặc dải dùng cho các dịch vụ khác.
- Peering kết nối **VPC của ứng dụng với mạng dịch vụ Google**; nó **không tạo mạng chuyển tiếp (transitive routing)** giữa mọi VPC đang peering với nhau. Một workload ở VPC B không tự tới Cloud SQL PSA trong VPC A chỉ vì hai VPC có peering riêng.
- Với Cloud Run/Functions/App Engine Standard, muốn đến private IP thường cần **Direct VPC egress hoặc Serverless VPC Access connector** tới VPC đúng. VM/GKE trong cùng VPC có thể dùng đường private theo routing/firewall.
- Khi dùng **Shared VPC**, dải IP và cấu hình network thuộc **host project**; instance có thể ở service project. Cần kiểm tra project nào chịu trách nhiệm Service Networking và các role cross-project.

## 3. Lab A — Cloud SQL PostgreSQL dùng PSA private IP

Mục tiêu lab: dùng một VPC riêng `orders-vpc`, cấp dải PSA, tạo Cloud SQL PostgreSQL **không public IP**, sau đó kết nối từ workload có đường mạng tới VPC. Các lệnh giả định bạn có quyền quản lý network, Service Networking và Cloud SQL.

### Bước 1 — Chuẩn bị API và VPC

~~~bash
PROJECT_ID="orders-lab-project"
REGION="asia-southeast1"
VPC="orders-vpc"
SUBNET="orders-subnet"
INSTANCE="orders-pg-private"
PSA_RANGE="google-managed-services-$VPC"

gcloud config set project "$PROJECT_ID"
gcloud services enable \
  compute.googleapis.com \
  servicenetworking.googleapis.com \
  sqladmin.googleapis.com

# Trong project lab mới, chỉ tạo các resource nếu chưa tồn tại.
gcloud compute networks create "$VPC" \
  --subnet-mode=custom

gcloud compute networks subnets create "$SUBNET" \
  --network="$VPC" \
  --region="$REGION" \
  --range=10.20.0.0/24
~~~

Ở project có network hiện hữu, **không tạo VPC trùng tên**; thay bằng VPC đã được phê duyệt. Một VPC khác chỉ cần cấu hình peering/ranges nếu chưa có. CIDR `10.20.0.0/24` là **subnet ứng dụng**, không phải dải PSA.

### Bước 2 — Cấp dải PSA không chồng lấn

~~~bash
# Google Cloud sẽ chọn một dải /16 chưa được dùng trong VPC.
gcloud compute addresses create "$PSA_RANGE" \
  --global \
  --purpose=VPC_PEERING \
  --prefix-length=16 \
  --network="projects/$PROJECT_ID/global/networks/$VPC"

gcloud compute addresses describe "$PSA_RANGE" \
  --global
~~~

Với hệ thống doanh nghiệp, quy hoạch CIDR cụ thể (ví dụ `10.70.0.0/16`) rồi thêm `--addresses=10.70.0.0` sau khi rà soát toàn bộ network. **Không lấy subnet đang cấp cho VM làm PSA range.** Số lượng địa chỉ cần dành tùy số service/region/database và network architecture.

### Bước 3 — Thiết lập Service Networking private connection

~~~bash
gcloud services vpc-peerings connect \
  --service=servicenetworking.googleapis.com \
  --ranges="$PSA_RANGE" \
  --network="$VPC" \
  --project="$PROJECT_ID"

gcloud services vpc-peerings list \
  --network="$VPC" \
  --project="$PROJECT_ID"
~~~

Nếu lệnh trả **operation ID**, cần chờ operation hoàn tất; không vội tạo instance khi peering chưa sẵn sàng. Mạng đã có connection thì **không tạo connection trùng**; khi dải cũ cạn có thể bổ sung range qua quy trình `vpc-peerings update` và đánh giá ảnh hưởng.

### Bước 4 — Tạo Cloud SQL không có public IP

~~~bash
gcloud sql instances create "$INSTANCE" \
  --project="$PROJECT_ID" \
  --database-version=POSTGRES_16 \
  --region="$REGION" \
  --tier=db-custom-2-7680 \
  --availability-type=ZONAL \
  --network="projects/$PROJECT_ID/global/networks/$VPC" \
  --allocated-ip-range="$PSA_RANGE" \
  --no-assign-ip

gcloud sql instances describe "$INSTANCE" \
  --project="$PROJECT_ID" \
  --format="yaml(connectionName,ipAddresses,settings.ipConfiguration)"
~~~

Ví dụ `ZONAL` nhằm giới hạn chi phí lab và **không có failover đa zone**; production thường cần đánh giá `REGIONAL` HA, backups/PITR, automated backups, maintenance window và replica/failover. Cloud SQL instance là resource tính phí dù không có workload; kiểm soát chi phí trước khi tạo.

**Đọc kết quả:** `ipAddresses` sẽ có private address khi instance sẵn sàng; public IP không được cấp với `--no-assign-ip`. Chuỗi `PROJECT:REGION:INSTANCE` là **instance connection name**, dùng cho Auth Proxy/Connector; **không phải** địa chỉ DNS/IP để client `psql` tự phân giải.

### Bước 5 — Kiểm tra connectivity từ một client hợp lệ

Từ một **VM/GKE Pod trong cùng VPC** đã cài PostgreSQL client:

~~~bash
# Lấy PRIVATE_IP từ kết quả describe đã xác minh.
PRIVATE_IP="10.x.y.z"    # thay bằng địa chỉ thật
DB_USER="orders_reader"  # user DB được tạo và cấp quyền trước
DB_NAME="orders"

# Chỉ kiểm tra đường TCP; chưa chứng minh quyền truy cập DB.
nc -vz "$PRIVATE_IP" 5432

# Direct connection: yêu cầu TLS đúng theo chính sách/CA của instance.
# Mẫu này giả định đã cấu hình certificate verification:
psql "host=$PRIVATE_IP port=5432 dbname=$DB_NAME user=$DB_USER sslmode=verify-full sslrootcert=/path/to/server-ca.pem"
~~~

`sslmode=verify-full` cần tên máy chủ trong chứng chỉ khớp với hostname được dùng; **nếu kết nối bằng IP mà chứng chỉ không có IP SAN phù hợp, kiểm tra TLS sẽ thất bại**. Trong production, dùng endpoint hostname hợp lệ/CA bundle hoặc chuyển sang Cloud SQL Auth Proxy/Language Connector cho đường kết nối bảo mật dễ quản hơn. Không sửa mặc định thành `sslmode=disable` để né lỗi.

### Kết nối an toàn với Cloud SQL Auth Proxy

Khi client có **ADC** và quyền `roles/cloudsql.client`, Cloud SQL Auth Proxy v2 có thể tự quản lý xác thực và TLS đến instance. Trên VM/GKE Pod có đường đến **private IP**:

~~~bash
INSTANCE_CONNECTION_NAME="$PROJECT_ID:$REGION:$INSTANCE"

# Chạy Auth Proxy ở terminal riêng, phiên bản v2.
./cloud-sql-proxy --private-ip --port 5432 "$INSTANCE_CONNECTION_NAME"

# Trong terminal khác trên CÙNG máy/process namespace:
psql "host=127.0.0.1 port=5432 dbname=orders user=orders_reader"
~~~

Proxy tự bảo vệ kết nối từ nó tới Cloud SQL; **đường từ ứng dụng tới proxy local** là local TCP. Proxy không tự tạo route VPC, không cấp database username/password và không phải database connection pool. Nếu dùng Cloud SQL Auth Proxy trong cùng Pod GKE như sidecar, `localhost` là loopback chung của Pod; nếu chạy trên một VM khác, không tự mở proxy port ra Internet.

## 4. Private Service Connect (PSC) là gì?

PSC cho phép ứng dụng trong **consumer VPC** truy cập Cloud SQL qua **một endpoint có internal IP thuộc subnet consumer**, thay vì cần mỗi VPC kết nối peering trực tiếp tới mạng dịch vụ qua PSA.

Các thành phần:

| Thành phần | Chủ sở hữu | Vai trò |
|---|---|---|
| **Cloud SQL PSC-enabled instance** | Database project | Xuất bản dịch vụ được quản lý |
| **Service attachment** | Cloud SQL/producer | URI đích của endpoint |
| **Allowed PSC projects** | Cấu hình Cloud SQL instance | Danh sách project được phép tạo endpoints tới instance |
| **PSC endpoint/forwarding rule** | Consumer project/VPC | Nhận IP từ consumer subnet, chuyển traffic tới service attachment |
| **Private DNS** | Consumer VPC/Cloud DNS | Đưa hostname được connector/proxy dùng tới endpoint IP |

~~~mermaid
flowchart LR
  subgraph DB["Database project: data-prod"]
    SQL["Cloud SQL PostgreSQL"]
    SA["Cloud SQL service attachment"]
    SQL --- SA
  end
  subgraph A["Consumer VPC A: orders-prod"]
    APP1["Java Cloud Run / GKE"]
    EP1["Endpoint IP: 10.10.0.20"]
    APP1 --> EP1
  end
  subgraph B["Consumer VPC B: reports-prod"]
    APP2["Report service"]
    EP2["Endpoint IP: 10.30.0.20"]
    APP2 --> EP2
  end
  EP1 --> SA
  EP2 --> SA
~~~

**Lợi ích chính:** mỗi VPC có endpoint/DNS riêng trong dải IP do nhóm đó quản lý; các project/organization/teams khác nhau có thể truy cập **cùng Cloud SQL instance** khi được cho phép. PSC giảm sự phụ thuộc vào VPC peering đa bên, nhưng **không có nghĩa mọi VPC trong organization được mặc định truy cập**: phải có allowed project, endpoint và mạng/DNS/DB auth đúng.

**Tính năng hiện hành:** Cloud SQL cho phép tạo instance bật **PSC thuần** hoặc **kết hợp PSA + PSC** theo cấu hình được hỗ trợ. Khi bật PSC trên instance PSA đã có, thao tác thay đổi có thể **gây downtime**; không thực hiện giữa giờ cao điểm mà không kiểm tra tài liệu phiên bản và maintenance plan. Tính năng **PSC outbound connectivity** (chiều Cloud SQL truy cập ngược vào consumer network qua network attachment) là bài toán khác, không cần cho luồng app → database ở đây.

## 5. Lab B — Tạo Cloud SQL PSC và endpoint consumer

Giả định có **database project** và **consumer project**. Mục tiêu: PSC-enabled PostgreSQL ở `data-lab` được phép tạo endpoint trong `app-lab`. Đường từ app đến database dùng PSC IP, không cấp public IP.

### Bước 1 — Tạo instance PSC

~~~bash
DB_PROJECT="data-lab-project"
APP_PROJECT="app-lab-project"
REGION="asia-southeast1"
DB_INSTANCE="orders-pg-psc"

# Database/platform team, chạy ở database project.
gcloud services enable sqladmin.googleapis.com \
  --project="$DB_PROJECT"

gcloud sql instances create "$DB_INSTANCE" \
  --project="$DB_PROJECT" \
  --region="$REGION" \
  --database-version=POSTGRES_16 \
  --tier=db-custom-2-7680 \
  --availability-type=ZONAL \
  --no-assign-ip \
  --enable-private-service-connect \
  --allowed-psc-projects="$APP_PROJECT"

gcloud sql instances describe "$DB_INSTANCE" \
  --project="$DB_PROJECT" \
  --format="yaml(connectionName,pscServiceAttachmentLink,settings.ipConfiguration)"
~~~

`--allowed-psc-projects` là danh sách **project IDs hoặc numbers** được phép tạo endpoint tới Cloud SQL service attachment. Đây **không phải** một danh sách database users hoặc service account có quyền login. Với instance đã tồn tại, kiểm tra hỗ trợ bật PSC/PSA kết hợp, thời gian downtime và quyền trước khi `gcloud sql instances patch`.

### Bước 2 — Lấy service attachment từ Cloud SQL

~~~bash
SERVICE_ATTACHMENT="$(gcloud sql instances describe "$DB_INSTANCE" \
  --project="$DB_PROJECT" \
  --format='value(pscServiceAttachmentLink)')"

echo "$SERVICE_ATTACHMENT"
~~~

URI có dạng `projects/PRODUCER_PROJECT/regions/REGION/serviceAttachments/NAME`. **Không tự xây URI từ instance name hoặc đoán producer project**; dùng giá trị thật do Cloud SQL trả về.

### Bước 3 — Chuẩn bị VPC/subnet ở consumer project

~~~bash
APP_VPC="orders-consumer-vpc"
APP_SUBNET="orders-consumer-subnet"
PSC_ADDRESS="orders-sql-psc-ip"
PSC_ENDPOINT="orders-sql-psc-endpoint"

gcloud services enable compute.googleapis.com \
  --project="$APP_PROJECT"

# Chỉ tạo khi VPC/subnet chưa có; CIDR phải được quy hoạch.
gcloud compute networks create "$APP_VPC" \
  --project="$APP_PROJECT" --subnet-mode=custom
gcloud compute networks subnets create "$APP_SUBNET" \
  --project="$APP_PROJECT" \
  --network="$APP_VPC" \
  --region="$REGION" \
  --range=10.30.0.0/24

# Dành một internal IP từ primary subnet range cho PSC endpoint.
gcloud compute addresses create "$PSC_ADDRESS" \
  --project="$APP_PROJECT" \
  --region="$REGION" \
  --subnet="$APP_SUBNET"
~~~

Subnet của PSC endpoint cần ở **region tương ứng với service attachment**. Nếu dùng **Shared VPC**, network/subnet có thể nằm ở **host project**, còn endpoint nằm ở host/service project theo hỗ trợ và IAM; dùng đúng **full resource URI** và quyền network của host project, không thay tên project một cách tùy tiện.

### Bước 4 — Tạo forwarding rule tới service attachment

~~~bash
gcloud compute forwarding-rules create "$PSC_ENDPOINT" \
  --project="$APP_PROJECT" \
  --region="$REGION" \
  --network="projects/$APP_PROJECT/global/networks/$APP_VPC" \
  --address="$PSC_ADDRESS" \
  --target-service-attachment="$SERVICE_ATTACHMENT"

gcloud compute forwarding-rules describe "$PSC_ENDPOINT" \
  --project="$APP_PROJECT" \
  --region="$REGION" \
  --format="yaml(IPAddress,pscConnectionStatus,target,network)"
~~~

Kỳ vọng `pscConnectionStatus: ACCEPTED` và `IPAddress` là IP thuộc consumer subnet. Nếu status `PENDING` hoặc `REJECTED`, **đừng thử sửa Java/DB password ngay**: trước hết kiểm tra allowed project, service attachment URI, endpoint region, resource quota và service networking policy.

Mặc định **không** thêm `--allow-psc-global-access` khi workload chỉ trong cùng region. Tùy chọn này mở khả năng đến endpoint từ các region khác; chỉ bật nếu có yêu cầu và đánh giá latency, egress/firewall, security policy.

### Bước 5 — Kiểm tra kết nối TCP từ client trong VPC

~~~bash
# Chạy từ Compute Engine VM/GKE Pod có route đến APP_VPC.
PSC_IP="10.30.0.10"   # THAY bằng IPAddress từ describe
nc -vz "$PSC_IP" 5432
~~~

`nc` thành công chỉ chứng minh có kết nối TCP tới PostgreSQL port, **chưa xác thực database**. Khi kết nối trực tiếp bằng `psql`/JDBC, cần database account hợp lệ và TLS/verify certificate phù hợp; hoặc dùng Cloud SQL Auth Proxy/Language Connector ở bước sau.

## 6. DNS cho PSC: vì sao nên dùng hostname?

Mỗi consumer VPC có thể tạo PSC endpoint với IP **khác nhau** nhưng cùng đích Cloud SQL. Đó là lý do **DNS được khuyến nghị**: app trong VPC A và B dùng tên database theo hợp đồng, còn private DNS resolve về endpoint IP của VPC đó.

~~~text
orders-db.<domain-do-google-cap> → 10.30.0.10  (trong APP_VPC)
orders-db.<domain-do-google-cap> → 10.50.0.10  (trong REPORT_VPC)
~~~

Với Cloud SQL PSC, một số phiên bản cung cấp **DNS automation**, có thể tự tạo các record qua service connection policies khi cấu hình auto-connections; cấu hình thủ công là phương án khác. Hãy đọc **DNS name được Cloud SQL trả về cho instance**, không tự sáng tác hostname. Các phiên bản Cloud SQL có thể có **per-instance DNS name** và **global write endpoint DNS** (ví dụ cho advanced DR thuộc edition hỗ trợ), có ý nghĩa khác nhau.

### Khi dùng Auth Proxy hoặc Java Connector

- **Cloud SQL Auth Proxy v2.5+** hỗ trợ PSC và yêu cầu **DNS name** có thể resolve từ nơi chạy proxy.
- **Cloud SQL Java Connector v1.13+** hỗ trợ `ipTypes=PSC`, dựa trên DNS record/đường tới endpoint.
- Java/JDBC kết nối trực tiếp TCP có thể dùng endpoint IP hoặc hostname đã resolve; khi direct phải tự quản SSL/TLS và DB credentials.
- **Instance connection name** dạng `project:region:instance` là định danh cho Cloud SQL API/connector, không thay một DNS A record trỏ tới endpoint.

Quy trình:

1. Lấy hostname PSC do Cloud SQL trả về (hoặc dùng chức năng DNS automation được hỗ trợ).
2. Tạo **Cloud DNS private zone/record** cho consumer VPC, record tới IP endpoint (khi cấu hình thủ công); kiểm tra chính xác DNS suffix mà tài liệu/instance cung cấp.
3. Từ VM/GKE/Cloud Run có VPC DNS visibility, chạy `nslookup HOSTNAME` hoặc `dig HOSTNAME`, xác nhận IP đúng consumer endpoint.
4. Kiểm tra endpoint `ACCEPTED`, `nc -vz HOSTNAME 5432` và sau đó mới kiểm tra connector/DB auth.
5. Nếu có nhiều VPC, tạo/cấp private zone visibility phù hợp từng VPC; không quảng bá record nội bộ ra public DNS khi không cần.

**DNS chỉ cho biết đích để kết nối, không tự cấp IAM hay DB user.** Một tên trỏ đúng endpoint vẫn có thể bị timeout do firewall, thiếu network route, hoặc bị `FATAL: password authentication failed` vì database credentials sai.

## 7. Java: Cloud SQL Connector qua PSA hoặc PSC

Với Java, **Cloud SQL Java Connector** là thư viện quản lý phần xác thực IAM và mã hóa kết nối tới Cloud SQL. Nó **không tự tạo network connectivity**; ứng dụng vẫn phải truy cập được private IP hoặc PSC endpoint thông qua VPC. Sử dụng **Application Default Credentials (ADC)** trong Cloud Run/GKE/VM và IAM `roles/cloudsql.client` khi sử dụng Connector/Proxy.

### Cấu hình phụ thuộc

Với PostgreSQL và HikariCP, dự án Maven/Gradle cần:

- PostgreSQL JDBC driver `org.postgresql:postgresql`.
- Cloud SQL Java Connector cho PostgreSQL `com.google.cloud.sql:postgres-socket-factory`.
- HikariCP `com.zaxxer:HikariCP`.
- Google Cloud auth/Secret Manager client nếu cần lấy DB password bằng ADC.

Chọn phiên bản tương thích qua dependency management/BOM và kiểm tra hướng dẫn Connector chính thức. Mã dưới đây là một class hỗ trợ tái sử dụng trong ứng dụng Java đã có build setup.

### Pool kết nối Java — chọn IP type có chủ đích

~~~java
import com.zaxxer.hikari.HikariConfig;
import com.zaxxer.hikari.HikariDataSource;

public final class CloudSqlDataSource {
    private CloudSqlDataSource() {}

    public static HikariDataSource create(
            String connectionName,
            String database,
            String dbUser,
            String dbPassword,
            String ipType) {

        if (!ipType.equals("PRIVATE") && !ipType.equals("PSC")) {
            throw new IllegalArgumentException("Expected PRIVATE or PSC");
        }

        HikariConfig cfg = new HikariConfig();
        cfg.setJdbcUrl("jdbc:postgresql:///" + database);
        cfg.setUsername(dbUser);
        cfg.setPassword(dbPassword); // Đọc từ Secret Manager, không hardcode.
        cfg.addDataSourceProperty(
            "socketFactory", "com.google.cloud.sql.postgres.SocketFactory");
        cfg.addDataSourceProperty("cloudSqlInstance", connectionName);
        cfg.addDataSourceProperty("ipTypes", ipType);
        cfg.addDataSourceProperty("cloudSqlRefreshStrategy", "lazy");

        cfg.setMaximumPoolSize(5);
        cfg.setMinimumIdle(0);
        cfg.setConnectionTimeout(10_000);
        cfg.setIdleTimeout(60_000);
        return new HikariDataSource(cfg);
    }
}
~~~

Ví dụ khởi tạo:

~~~java
String instance = System.getenv("INSTANCE_CONNECTION_NAME");
String database = System.getenv("DB_NAME");
String dbUser = System.getenv("DB_USER");
String dbPassword = loadFromSecretManager(); // Hàm do ứng dụng tự triển khai.

// PSA private IP:
var psaPool = CloudSqlDataSource.create(
    instance, database, dbUser, dbPassword, "PRIVATE");

// Hoặc PSC endpoint + private DNS đã sẵn sàng:
var pscPool = CloudSqlDataSource.create(
    instance, database, dbUser, dbPassword, "PSC");
~~~

Đây là **hai phương án thay thế**, không khởi tạo cả hai pool cho cùng workload nếu không có lý do. `loadFromSecretManager()` là ký hiệu cho một hàm ứng dụng thực tế; không phải phương thức Java có sẵn. Khởi tạo pool **một lần cho mỗi app instance**, đóng bằng `close()` khi shutdown; không tạo pool mới cho mỗi request.

| `ipTypes` | Đường mạng Connector chọn | Phụ thuộc |
|---|---|---|
| `PRIVATE` | Private IP Cloud SQL qua PSA | Network/peering/routing, IP private tồn tại |
| `PSC` | PSC endpoint trong consumer VPC | PSC enabled, endpoint ACCEPTED, DNS resolvable |
| `PUBLIC` | Public IP của Cloud SQL | Public IP và policy truy cập; không phù hợp bài lab private |

**Không bỏ trống `ipTypes` khi muốn chắc chắn đi private**: Connector có hành vi mặc định và thứ tự ưu tiên IP types theo phiên bản; khai báo `PRIVATE` hoặc `PSC` rõ ràng để kiểm tra đường mạng và tránh chọn public IP ngoài ý muốn. Đối với PSC, dùng Cloud SQL Java Connector phiên bản có hỗ trợ PSC và cấu hình DNS mà Connector yêu cầu.

### IAM và xác thực database là hai bước khác nhau

- **IAM Cloud SQL Client**: cho Connector/Proxy có quyền lấy instance metadata/certificates và thiết lập đường kết nối được hỗ trợ.
- **Database account**: PostgreSQL username/password và quyền `GRANT SELECT/INSERT/...` trong database. Không được tạo tự động chỉ nhờ `roles/cloudsql.client`.
- **IAM database authentication** (nếu chọn): cần bật tính năng ở Cloud SQL, tạo DB user IAM phù hợp, cấp role như Cloud SQL Instance User và dùng Connector/Auth Proxy có cấu hình IAM DB auth; đây là một **phương án khác** với password truyền thống.

Khi client **kết nối trực tiếp** bằng `psql`/JDBC TCP tới private IP/PSC IP, không bắt buộc IAM Cloud SQL Client nếu chỉ dùng database credentials và network được phép; tuy nhiên TLS/authentication và chính sách tổ chức vẫn bắt buộc. Đừng cấp role Admin chỉ để mở cổng SQL.

## 8. Nguồn kết nối: VM, GKE và Cloud Run

| Nguồn workload | PSA private IP | PSC | Điều phải kiểm tra |
|---|---|---|---|
| **Compute Engine VM** | VM ở VPC có PSA và route phù hợp | VM có route tới endpoint IP trong consumer VPC | Firewall, network tags, DNS, DB auth |
| **GKE** | Nodes/Pods có egress tới PSA VPC | Pod có egress tới consumer PSC endpoint | GKE VPC-native, NetworkPolicy, service account/ADC |
| **Cloud Run** | Direct VPC egress hoặc Serverless VPC Access tới VPC PSA | Direct VPC egress/connector tới VPC chứa endpoint PSC | Subnet cùng region theo ràng buộc, IAM, DNS, egress setting |
| **App Engine Standard/Functions** | VPC egress phù hợp tới PSA VPC | VPC egress phù hợp tới consumer endpoint | Network/product support và IAM |
| **On-premises** | VPN/Interconnect tới VPC PSA, các routes được quảng bá đúng | VPN/Interconnect/route hợp lệ tới consumer endpoint | DNS forwarding, firewall, latency, TLS |

**Không thể chỉ “có Cloud SQL Client IAM” rồi kết nối từ laptop vào private IP.** Máy phải có đường mạng tới VPC (VPN/Interconnect, máy bastion được bảo vệ, môi trường dev nội bộ). Proxy chạy trên laptop **không tạo đường xuyên VPC**, dù nó tự lấy token thành công.

### Cloud Run Direct VPC egress mẫu

Khi triển khai một **Cloud Run service** từ container image đã được build/push, chọn network và subnet có thể tới PSA hoặc PSC endpoint:

~~~bash
RUN_PROJECT="app-lab-project"
REGION="asia-southeast1"
NETWORK="orders-consumer-vpc"
SUBNET="orders-consumer-subnet"
RUN_SA="orders-runtime@$RUN_PROJECT.iam.gserviceaccount.com"
IMAGE="$REGION-docker.pkg.dev/$RUN_PROJECT/apps/orders-api:v1"

gcloud run deploy orders-api \
  --project="$RUN_PROJECT" \
  --image="$IMAGE" \
  --region="$REGION" \
  --service-account="$RUN_SA" \
  --network="$NETWORK" \
  --subnet="$SUBNET" \
  --vpc-egress=private-ranges-only \
  --no-allow-unauthenticated
~~~

Giả định VPC/subnet ở **cùng project** với Cloud Run service; Shared VPC cần cấp permissions của host project và cấu hình theo hướng dẫn. `private-ranges-only` định tuyến IP nội bộ qua VPC; `all-traffic` định tuyến toàn bộ egress qua VPC và có thể cần Cloud NAT để tới Internet. **Cấu hình VPC không tự tạo PSC endpoint hay kết nối PSA** — phải chuẩn bị trước.

### GKE và lỗi NetworkPolicy

Một Pod GKE có `roles/cloudsql.client` qua Workload Identity Federation nhưng bị `NetworkPolicy` default-deny egress sẽ không tới PSC endpoint hoặc dải PSA nếu policy chưa cho phép. Cần cho phép đúng **database IP và TCP 5432** (PostgreSQL) hoặc **TCP 3306** (MySQL), cùng DNS và đường đến Google APIs cần cho Connector. Nếu dùng Cloud SQL Auth Proxy/Connector, kiểm tra đường Google Cloud Admin API, metadata server và IAM token exchange riêng.

Ví dụ NetworkPolicy chỉ mở egress tới **một PSC endpoint IP** cho các Pods có label `app=orders-api`:

~~~yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: allow-orders-db-psc
  namespace: orders
spec:
  podSelector:
    matchLabels:
      app: orders-api
  policyTypes:
    - Egress
  egress:
    - to:
        - ipBlock:
            cidr: 10.30.0.10/32
      ports:
        - protocol: TCP
          port: 5432
~~~

Đây **không phải policy egress hoàn chỉnh**: trong namespace default-deny, ứng dụng còn cần DNS, metadata/ADC, Cloud SQL Admin API, Secret Manager... Không áp trực tiếp CIDR mẫu vào môi trường chưa biết IP thật.

## 9. Bảo mật, độ tin cậy và vận hành

### Các lớp bảo vệ

| Lớp | Kiểm soát | Ví dụ |
|---|---|---|
| **VPC/IP** | PSA private path hoặc PSC endpoint, firewall/network policy | Chỉ nhóm ứng dụng được tới database port |
| **IAM** | Runtime SA tối thiểu, Cloud SQL Client khi dùng Connector | Không cấp `roles/editor` cho toàn app |
| **Database** | DB user, password/ IAM DB auth, schema grants, row-level access | App reader không có `DROP TABLE` |
| **Transport** | Cloud SQL Connector/Auth Proxy hoặc TLS xác minh CA/certificate | Không tắt certificate validation để né lỗi |
| **Secrets** | Secret Manager và rotation | Không lưu DB password trong Docker image |
| **Application** | Prepared statements, multi-tenant authorization, idempotency | Một tenant không đọc được đơn tenant khác |

**PSC không phải IAM authorization của PostgreSQL.** Allowed projects chỉ xác định ai có thể tạo PSC endpoint tới instance. Khi endpoint được chấp nhận, vẫn phải quản ai có đường mạng tới IP đó và ai có DB credentials.

### High availability và migration

Tách hai khái niệm:

- **Kết nối mạng riêng**: PSA/PSC là con đường app → instance; không tự tăng HA, backup, PITR hoặc replication.
- **Sẵn sàng database**: instance `REGIONAL`, HA/failover, replicas, backups, monitoring, connection retry và recovery kế hoạch.

Khi chuyển từ PSA sang PSC hoặc bật cả hai:

1. Kiểm kê nơi kết nối (VM, GKE, Cloud Run), DB clients, DNS, VPC, IAM và dependency.
2. Xác minh Cloud SQL edition, engine/version và khả năng hỗ trợ **PSA + PSC**; đánh giá downtime của thao tác patch.
3. Tạo endpoint mới trong consumer VPC; chờ `ACCEPTED` và xác minh private DNS.
4. Test kết nối canary bằng Connector `ipTypes=PSC`, xác nhận query và transaction thực, đo P95 latency.
5. Chuyển dần clients; giữ PSA trong giai đoạn rollback nếu instance hỗ trợ và quy trình cho phép.
6. Chỉ bỏ dải/routing PSA cũ khi không còn workload nào dùng, tránh làm ngắt các dịch vụ Google khác chia sẻ PSA peering.

**Không chỉnh private network trên instance production hoặc xóa peering khi chưa có maintenance window.** Một số thay đổi network của Cloud SQL có thể cần restart và có thời gian gián đoạn.

### Pool, timeout và tránh bùng nổ kết nối

Giả sử có **20 Cloud Run instances** và mỗi instance mở JDBC pool tối đa 10 connections. Database có thể phải phục vụ **200 connections** chỉ từ một service, chưa tính read replicas, BI jobs và migrations.

~~~text
Maximum possible connections (nominal)
  = Max app instances × Max JDBC connections / instance
  = 20 × 10 = 200
~~~

Đặt `maximumPoolSize` nhỏ theo SLO và giới hạn Cloud SQL, có connection timeout và idle timeout; giảm kết nối idle trong serverless. Với PostgreSQL workloads lớn, xem xét managed connection pooling hoặc PgBouncer khi sản phẩm/edition và thiết kế hỗ trợ; **pooling không thay việc sửa truy vấn chậm**.

### Chi phí cần tính đủ

Cloud SQL instance/CPU/RAM/storage/backups vẫn bị tính phí dù private. PSA cần quản lý IP range và network; PSC có chi phí **endpoint/traffic hoặc các thành phần liên quan theo biểu phí Private Service Connect**, cộng egress/cross-region, Cloud DNS, NAT/VPC connector nếu dùng, logging và monitoring. Multi-region/HA và replicas ảnh hưởng mạnh tới tổng chi phí.

**Không kết luận PSC luôn đắt hơn hoặc rẻ hơn PSA chỉ từ một đơn giá IP.** So sánh tổng chi phí IP/routing operations, endpoint ở mỗi VPC, network traffic, security boundaries, HA, vận hành và migration.

## 10. Runbook: chẩn đoán kết nối thất bại

Luôn điều tra theo thứ tự: **instance → network → DNS → TCP → IAM Connector → database authentication → ứng dụng**. Lỗi cùng có dạng `connection failed` nhưng nguyên nhân rất khác.

| Triệu chứng | Nguyên nhân có thể | Bước ưu tiên |
|---|---|---|
| `SERVICE_NETWORKING_NOT_ENABLED` | Service Networking API chưa bật | Bật `servicenetworking.googleapis.com` ở đúng project; Shared VPC kiểm tra host/service project |
| `NETWORK_NOT_PEERED` khi tạo private IP | PSA private connection chưa hoàn tất | `gcloud services vpc-peerings list`, operation status và allocated range |
| PSA IP range exhausted/overlap | Dải PSA trùng CIDR hoặc thiếu địa chỉ | Quy hoạch range mới; không sửa range đang dùng tùy tiện |
| PSC `REJECTED` | Consumer project không nằm trong allowed list hoặc endpoint cấu hình sai | Instance PSC settings, service attachment và endpoint status |
| PSC `PENDING` kéo dài | Hạ tầng chưa provision xong, policy hoặc quota | `forwarding-rules describe`, Cloud SQL operation, IAM của network team |
| PSC DNS `NXDOMAIN` | Chưa tạo private zone/record hoặc VPC không được bind | DNS zone visibility, hostname thực của Cloud SQL, DNS automation |
| `Connection timed out` | Không có route, firewall/NetworkPolicy chặn, Cloud Run chưa dùng VPC egress | Test `nc` từ **đúng runtime network** tới IP:5432 |
| `Connection refused` | Sai IP/port, endpoint chưa active, DB service chưa sẵn sàng | Kiểm tra IP endpoint/instance health và loại engine |
| Connector trả `403` | Runtime SA thiếu Cloud SQL Client hoặc dùng sai project/API | IAM bindings, ADC, Cloud SQL Admin API |
| `FATAL: password authentication failed` | Sai DB username/password hoặc secret cũ | DB users, Secret Manager version, không tăng IAM bừa bãi |
| `no pg_hba.conf entry`/TLS failure | Cấu hình auth/SSL sai, không phù hợp client/CA | Database engine logs, TLS mode, Connector/Proxy |
| `too many connections` | Pool × instances vượt capacity | Active connections, Hikari pool, Cloud Run max instances |
| Lúc nhanh lúc timeout | DNS stale, failover, pool giữ socket chết, kết nối cross-region | DNS TTL, reconnect/backoff, P95 latency, HA events |
| Cloud Run deployment mới lỗi, bản cũ hoạt động | Revision mới chọn sai network/subnet hoặc runtime SA | So sánh VPC config và identity giữa revisions |

### Lệnh chẩn đoán chỉ đọc

~~~bash
DB_PROJECT="data-lab-project"
DB_INSTANCE="orders-pg-psc"
APP_PROJECT="app-lab-project"
REGION="asia-southeast1"
PSC_ENDPOINT="orders-sql-psc-endpoint"

# Cloud SQL: engine, trạng thái, IP, PSC attachment và settings.
gcloud sql instances describe "$DB_INSTANCE" \
  --project="$DB_PROJECT" \
  --format="yaml(state,region,connectionName,ipAddresses,pscServiceAttachmentLink,settings.ipConfiguration)"

# Consumer PSC endpoint: IP và connection status.
gcloud compute forwarding-rules describe "$PSC_ENDPOINT" \
  --project="$APP_PROJECT" \
  --region="$REGION" \
  --format="yaml(IPAddress,pscConnectionStatus,target)"

# PSA: thực hiện nếu database đi qua private services access.
gcloud services vpc-peerings list \
  --network=orders-vpc \
  --project=orders-lab-project

# Cloud Run: mạng/SA và revision mới nhất.
gcloud run services describe orders-api \
  --project="$APP_PROJECT" \
  --region="$REGION"
~~~

Trong **VM/Pod chạy ứng dụng**, không phải Cloud Shell không có đường tới VPC:

~~~bash
# Dùng hostname PSC do Cloud SQL cung cấp cho consumer network.
nslookup "ACTUAL_CLOUD_SQL_PSC_DNS_NAME"
nc -vz "ACTUAL_CLOUD_SQL_PSC_DNS_NAME" 5432

# Nếu DNS chưa có nhưng endpoint đã ACCEPTED:
nc -vz "ACTUAL_PSC_ENDPOINT_INTERNAL_IP" 5432
~~~

**Cách đọc kết quả:**

1. Không resolve hostname: lỗi **DNS visibility/record**, chưa liên quan database password.
2. Resolve đúng IP nhưng TCP timeout: lỗi **VPC route/firewall/egress/endpoint**.
3. TCP thông, Connector lấy token thất bại: lỗi **ADC/IAM/Cloud SQL Admin API**.
4. Connector đi tới DB nhưng `password authentication failed`: lỗi **database identity/grants**, không phải `roles/cloudsql.client`.
5. Có kết nối nhưng query chậm: xem **DB performance, indexes, pool, locks và network latency**.

Khi nghi ngờ firewall, kiểm tra **đúng network tags và chiều egress** của workload. Không mở tạm `0.0.0.0/0` ở VPC hoặc Cloud SQL authorized networks để “test nhanh”; điều này làm khó truy vết và tăng rủi ro.

### Logs, metrics và audit

| Nguồn | Tín hiệu cần theo dõi |
|---|---|
| Cloud SQL | Instance health, active connections, CPU, memory, storage, failover, query latency |
| VPC Flow Logs / Firewall Rules Logging | Traffic đến PSC IP hoặc dải PSA bị chặn/khác route |
| PSC forwarding rule metrics/status | `pscConnectionStatus`, data processing, endpoint health |
| Cloud DNS | Resolution success/latency và private zone binding |
| Cloud Run / GKE | Connection errors, cold start, Hikari pool exhaustion, 5xx |
| Cloud Audit Logs | Thay đổi Cloud SQL settings, PSC allowed projects, IAM, VPC resources |
| Billing | Cloud SQL compute/storage/backup, PSC traffic/endpoints, networking, DNS, logging |

Chỉ bật các loại logs cần thiết theo chính sách retention: DB logs hoặc client debug có thể chứa query/PII. Không in database password, IAM token hay toàn connection string có secret vào log.

## 11. PSA hay PSC? Ra quyết định theo topology

| Tình huống | Phương án ưu tiên xem xét | Lý do |
|---|---|---|
| Một Java API và database ở **cùng VPC**, ít thay đổi network | **PSA private IP** | Ít endpoints/DNS per-VPC hơn nếu peering đã cấu hình |
| Nhiều project/VPC của các team độc lập truy cập **cùng instance** | **PSC** | Mỗi consumer có endpoint riêng, tránh phụ thuộc peering đa VPC |
| Chuyển dần từ ứng dụng cũ PSA sang topology đa VPC | **PSA + PSC** khi instance hỗ trợ | Hai đường cùng tồn tại trong giai đoạn migration |
| Workload chỉ từ mạng on-premises có VPN/Interconnect | **Đánh giá cả hai** | Route propagation/DNS/firewall mới quyết định |
| Instance yêu cầu DR/cross-region read/write | **PSC + DNS/write endpoint** khi edition hỗ trợ | Tên logic có thể giảm phụ thuộc IP cụ thể, vẫn cần DR design |
| Ứng dụng Java chỉ cần Cloud SQL với private network | **Connector + PSA hoặc PSC** | Connector làm auth/TLS, network method chọn theo topology |

**Không có lựa chọn mặc định phù hợp mọi doanh nghiệp.** Với một VPC và instance đã dùng PSA ổn định, không cần bắt buộc chuyển PSC. Với nhiều VPC/project cùng truy cập, PSC có thể tạo ranh giới vận hành tốt hơn, nhưng tăng số endpoint/DNS/IAM/quota cần quản trị.

### Tình huống doanh nghiệp

Một công ty có:

~~~text
Project data-prod:
   Cloud SQL PostgreSQL orders-db (HA, backups)

Project shop-prod:
   Cloud Run orders-api
   VPC orders-vpc

Project reports-prod:
   GKE analytics cluster
   VPC reports-vpc
~~~

Nếu chỉ dùng PSA từ `orders-vpc`, GKE trong `reports-vpc` **không tự có đường** tới Cloud SQL chỉ vì các VPC cùng organization. Với PSC, database team cho phép hai consumer projects, hai team tạo endpoints trong VPC của mình, cấu hình DNS và test connect. Runtime SAs được cấp `roles/cloudsql.client` khi dùng Connector, nhưng database phải có **users/grants riêng** cho API read/write và analytics read-only.

Với ứng dụng báo cáo, ưu tiên **read replica** hoặc workload đã được giới hạn để không làm giảm SLO của primary. Nếu dùng nhiều PSC endpoints, **đó không đồng nghĩa load balancing/HA tự động của database**; endpoints tới cùng primary vẫn phụ thuộc primary đó.

## 12. Lưu ý riêng về AlloyDB

Chương có cả **Cloud SQL và AlloyDB for PostgreSQL**, nhưng **không dùng lệnh Cloud SQL để tạo AlloyDB cluster**. AlloyDB cũng cung cấp các phương án mạng riêng, trong đó có **PSC cho AlloyDB**, nhưng tài nguyên và tools khác:

- **AlloyDB cluster/instance** được quản lý bằng `gcloud alloydb ...` và API riêng; Cloud SQL dùng `gcloud sql instances ...`.
- Với AlloyDB PSC, endpoint vẫn gắn service attachment và consumer VPC, nhưng DNS name là trường **`pscDnsName`** của AlloyDB instance, phải tạo record private DNS trỏ tới endpoint IP khi dùng **AlloyDB Auth Proxy/Language Connector**.
- **Cloud SQL Auth Proxy/Java Connector** và **AlloyDB Auth Proxy/Language Connector** là **hai bộ công cụ khác nhau**; không dùng lẫn chỉ vì cả hai hỗ trợ PostgreSQL.
- Mô hình network, HA, read pools, DR, connection pooling và pricing của AlloyDB cần đánh giá riêng. Không lấy hạn mức, tham số CLI hay chi phí Cloud SQL áp sang AlloyDB.

Đối với bài tập Cloud SQL trong tài liệu này, mọi lệnh `gcloud sql`, `ipTypes=PSC` và `CloudSqlDataSource` là cho **Cloud SQL PostgreSQL**, không phải ví dụ AlloyDB.

## 13. Checklist triển khai production

- [ ] Đã xác định đúng Cloud SQL engine/edition, instance, project/region, yêu cầu HA/backup và SLO.
- [ ] Đã chọn PSA, PSC hoặc kết hợp dựa trên **topology VPC** và ranh giới team/project.
- [ ] PSA dùng IP range không chồng lấn, Service Networking connection đã hoàn tất và có kế hoạch capacity.
- [ ] PSC đã bật trên instance, allowed projects đúng và endpoint trả `ACCEPTED`.
- [ ] PSC private DNS resolve đúng IP trong **từng consumer VPC**; Connector/Proxy tương thích.
- [ ] Cloud Run/GKE/VM có đường egress tới đúng IP; NetworkPolicy/firewall không chặn DB/API.
- [ ] Runtime SA dùng ADC, IAM ít quyền; phân biệt Cloud SQL Client với DB user/grants.
- [ ] Sử dụng Connector/Proxy hoặc TLS được xác minh cho direct TCP; không đưa password vào image/Git.
- [ ] JDBC pool × số instances không vượt database capacity; timeout/reconnect/failover được kiểm thử.
- [ ] Có canary migration, rollout/rollback, DR, audit logs, monitoring và billing alerts.
- [ ] Không xóa private connection/PSC endpoint hoặc Cloud SQL instance khi còn consumer.

## 14. Bài tập vận dụng

**Bài 1 — So sánh kiến trúc.** Vẽ hai đường VM → Cloud SQL bằng PSA và VM → PSC endpoint → Cloud SQL. Chỉ ra network project, địa chỉ IP phía client và thành phần phụ thuộc DNS ở mỗi phương án.

**Bài 2 — Thiết lập PSA.** Từ một VPC lab đã có, liệt kê các lệnh để bật Service Networking, reserve `VPC_PEERING` range, tạo private connection và Cloud SQL PostgreSQL không public IP. Giải thích vì sao subnet VM `10.20.0.0/24` không được dùng làm dải PSA.

**Bài 3 — PSC cross-project.** Database project A cho phép project B và C. Thiết kế mỗi VPC một endpoint, lựa chọn IP/subnet, xác minh `pscConnectionStatus` và mô tả private DNS records cần có nếu endpoint IP khác nhau.

**Bài 4 — Java Connector.** Viết phương thức Java tạo HikariCP với `ipTypes=PRIVATE`, sau đó chuyển sang `PSC`. Nêu **ít nhất ba điều kiện** ngoài thay property `ipTypes` để Java thật sự kết nối được qua PSC.

**Bài 5 — Cloud Run.** Một service có runtime SA Cloud SQL Client nhưng kết nối `10.30.0.10:5432` bị timeout. Chỉ ra cấu hình Direct VPC egress, subnet, endpoint `ACCEPTED`, firewall và DNS cần kiểm tra trước khi tăng IAM.

**Bài 6 — Phân biệt lỗi.** Với các tình huống `NETWORK_NOT_PEERED`, `PSC REJECTED`, `NXDOMAIN`, `403 Cloud SQL Admin API` và `FATAL password authentication failed`, phân loại lần lượt là lỗi **PSA**, **PSC admission**, **DNS**, **IAM Connector** hay **database auth**.

**Bài 7 — Connection capacity.** Một Java service có 30 Cloud Run instances, mỗi instance tạo pool tối đa 8 connections. Tính số connections tối đa danh nghĩa, giải thích rủi ro khi Cloud SQL chỉ còn 150 slots trống và đề xuất cách điều chỉnh pool/scale.

**Bài 8 — Thiết kế migration.** Một nhóm đang dùng PSA, thêm ba ứng dụng từ VPC khác. Lập kế hoạch bật PSA + PSC đồng thời, test canary, chuyển DNS/Connector, theo dõi SLO và rollback nếu PSC gặp lỗi. Vì sao không được xóa PSA ngay khi một endpoint PSC đã `ACCEPTED`?

**Bài 9 — AlloyDB.** Một đồng nghiệp dùng Cloud SQL Auth Proxy với `gcloud alloydb` và hỏi vì sao không hoạt động. Giải thích khác biệt giữa Cloud SQL và AlloyDB PSC, `pscDnsName`, AlloyDB Auth Proxy/Connectors và tài liệu cần tham khảo.

## Tài liệu tham khảo chính thức

- [Cloud SQL — Private IP connection overview](https://cloud.google.com/sql/docs/postgres/private-ip) — kiến trúc và điều kiện kết nối qua private IP.
- [Configure private services access (PSA)](https://cloud.google.com/sql/docs/postgres/configure-private-services-access) — allocate IP range, Service Networking và peering.
- [Connect to Cloud SQL using private IP](https://cloud.google.com/sql/docs/postgres/connect-instance-private-ip) — VPC client, Auth Proxy và kiểm thử.
- [Cloud SQL Private Service Connect overview](https://cloud.google.com/sql/docs/postgres/about-private-service-connect) — endpoints, service attachments và DNS.
- [Configure Private Service Connect](https://cloud.google.com/sql/docs/postgres/configure-private-service-connect) — instance PSC, allowed projects, forwarding rules và trạng thái.
- [Configure DNS for PSC](https://cloud.google.com/sql/docs/postgres/configure-dns) — DNS automation và private zones.
- [Configure both PSA and PSC](https://cloud.google.com/sql/docs/postgres/configure-private-services-access-and-private-service-connect) — migration và giới hạn.
- [Cloud SQL Auth Proxy](https://cloud.google.com/sql/docs/postgres/connect-auth-proxy) — bảo mật kết nối, `--private-ip` và PSC.
- [Cloud SQL Java Connector JDBC](https://github.com/GoogleCloudPlatform/cloud-sql-jdbc-socket-factory/blob/main/docs/jdbc.md) — `ipTypes=PRIVATE/PSC`, ADC và pool.
- [Connect Cloud Run to Cloud SQL](https://cloud.google.com/sql/docs/postgres/connect-run) — serverless private IP và DB authentication.
- [Cloud Run Direct VPC egress](https://cloud.google.com/run/docs/configuring/vpc-direct-vpc) — route tới consumer VPC.
- [AlloyDB — Private Service Connect overview](https://cloud.google.com/alloydb/docs/about-private-service-connect) — cluster/instance model và `pscDnsName`.
- [AlloyDB — Configure Private Service Connect](https://cloud.google.com/alloydb/docs/configure-private-service-connect) — endpoints và private DNS.
- [Cloud SQL pricing](https://cloud.google.com/sql/pricing) và [Private Service Connect pricing](https://cloud.google.com/vpc/network-pricing#private-service-connect) — dự toán database và network.
