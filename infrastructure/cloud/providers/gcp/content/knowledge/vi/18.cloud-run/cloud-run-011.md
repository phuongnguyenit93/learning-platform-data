# Kết nối Cloud Run với Cloud SQL và dịch vụ riêng

> **Chương:** Cloud Run  
> **Mô-đun:** CLOUD_PROVIDERS_GCP

Một API Java chạy trên **Cloud Run** cần lưu đơn hàng vào **Cloud SQL for PostgreSQL**, đọc cache nội bộ và gọi một dịch vụ xử lý thanh toán chỉ dành cho nội bộ. Để triển khai an toàn, phải giải quyết **ba câu hỏi riêng biệt**: gói tin đi đường nào, danh tính nào được phép kết nối và ứng dụng quản lý kết nối ra sao khi Cloud Run tự mở rộng.

Trong mô-đun **CLOUD_PROVIDERS_GCP**, người học đi từ project, IAM và VPC đến Compute Engine, GKE, Cloud Run, lưu trữ, cơ sở dữ liệu, tự động hóa phát hành và theo dõi độ tin cậy/chi phí. Bài này tập trung vào **Cloud Run services**, minh họa với **PostgreSQL**; các nguyên tắc mạng cũng hữu ích cho Cloud Run jobs, MySQL, SQL Server và các dịch vụ private khác, nhưng cổng/driver/quyền cần điều chỉnh theo sản phẩm.

**Kết quả học tập:**

1. Phân biệt **ingress**, **egress**, **VPC routing**, **IAM** và **database authentication**.
2. Chọn **Direct VPC egress** hoặc **Serverless VPC Access connector** và các chế độ `private-ranges-only`/`all-traffic`.
3. Kết nối Cloud Run đến Cloud SQL qua **public IP + Cloud SQL connector/proxy** hoặc **private IP + VPC** mà không trộn lẫn các phương thức.
4. Sử dụng **Cloud SQL Java Connector**, Secret Manager và runtime service account theo quyền tối thiểu.
5. Truy cập VM, dịch vụ nội bộ hoặc Cloud Run service khác một cách có xác thực.
6. Điều chỉnh connection pool theo Cloud Run autoscaling để tránh làm cạn số kết nối Cloud SQL.
7. Kiểm tra DNS, route, firewall, IAM, logs, lỗi timeout và khôi phục an toàn.

## 1. Kiến trúc tham chiếu và các lớp kiểm soát

~~~mermaid
flowchart TB
    CLIENT["Client đã xác thực"] --> INGRESS["Cloud Run ingress + Invoker IAM"]
    INGRESS --> API["Cloud Run: orders-api\nJava, runtime service account"]
    API --> EGRESS["Direct VPC egress\nprivate-ranges-only"]
    subgraph VPC["Ứng dụng trong VPC"]
      EGRESS --> SQL["Cloud SQL PostgreSQL\nPrivate IP :5432"]
      EGRESS --> CACHE["Cache / VM / internal LB\nPrivate IP"]
    end
    API --> SECRET["Secret Manager\nDB credentials"]
    API --> IAM["Cloud SQL Admin API + IAM\n(khi dùng Java Connector)"]
    API --> TASK["Cloud Run private service\nqua luồng nội bộ + ID token"]
    TASK --> INV["roles/run.invoker"]
    API --> OBS["Cloud Logging / Monitoring"]
~~~

**Đường vào và đường ra độc lập:**

- **Ingress** quyết định **nguồn nào được gọi HTTP endpoint của Cloud Run**; `--ingress=internal` không tự cấp đường ra đến Cloud SQL.
- **Egress** quyết định **lưu lượng Cloud Run phát ra** đi qua VPC thế nào; `--network/--subnet` không tự biến URL Cloud Run thành internal-only.
- **VPC/firewall/route/DNS** quyết định có đường mạng tới private IP/endpoint không.
- **IAM** kiểm soát quyền sử dụng Google APIs, chẳng hạn Cloud SQL Connector hoặc gọi một Cloud Run service yêu cầu xác thực.
- **DB user/password hoặc IAM database authentication** kiểm soát truy cập **bên trong PostgreSQL**, không tự được cấp bởi `roles/cloudsql.client`.

**Bài học then chốt:** Một lỗi `403` có thể là thiếu IAM; một lỗi `connection timed out` thường liên quan network; còn `password authentication failed` là xác thực PostgreSQL. Đừng sửa tất cả bằng cách mở firewall hoặc cấp Project Owner.

## 2. Ma trận chọn phương thức kết nối

| Đích đến | Đường kết nối thông dụng | Xác thực bắt buộc |
| --- | --- | --- |
| Cloud SQL **public IP** | Cloud SQL Java Connector hoặc Cloud Run tích hợp Auth Proxy/Unix socket | IAM `cloudsql.client` cho connector/proxy **và** quyền DB |
| Cloud SQL **private IP** | Direct VPC egress/connector → TCP đến private IP, hoặc **Java Connector chọn PRIVATE** | Network + DB auth; Java Connector cần IAM/API |
| Cloud SQL qua **Private Service Connect (PSC)** | Endpoint/địa chỉ private và DNS/routing theo cấu hình PSC | Network + DB auth; connector nếu dùng còn cần IAM/API |
| Compute Engine VM / GKE internal Load Balancer | Direct VPC egress/connector → internal IP/port | Firewall ingress/egress, TLS và app auth |
| Memorystore/Redis-compatible cache | VPC egress → internal endpoint | Quyền/network và AUTH/TLS theo phiên bản sản phẩm |
| **Cloud Run service riêng** | Đường truy cập được Cloud Run coi là internal + **Google-signed ID token** | Caller có `roles/run.invoker` trên callee |
| Google APIs như Secret Manager | Google API endpoint và runtime service identity | IAM đối với secret/resource; thường không cần kết nối TCP trực tiếp đến DB |

**Lưu ý:** Cloud SQL **private IP** không phải là Private Google Access (PGA). Private IP của Cloud SQL thường dựa vào **Private Services Access (PSA)** hoặc **PSC** tùy cách tạo instance. PGA là một cơ chế truy cập các **Google APIs được hỗ trợ** từ nguồn không có external IP. Hai cơ chế giải quyết các đích đến khác nhau.

### 2.1. Public IP + connector/proxy vẫn có mã hóa và IAM

Public IP trên Cloud SQL **không đồng nghĩa** ứng dụng phải mở kết nối PostgreSQL công khai không được bảo vệ. Với **Cloud SQL Language Connector/Cloud SQL Auth Proxy**, kênh được thiết lập có **IAM authorization và encryption**; trong production vẫn cân nhắc giảm public exposure và chọn private connectivity theo chính sách.

Nếu dùng **Cloud Run built-in Cloud SQL connection** qua `--add-cloudsql-instances`, Cloud Run có thể cung cấp Unix socket tại `/cloudsql/PROJECT:REGION:INSTANCE`. Nhưng **Java không hỗ trợ Unix-domain socket theo cách thuần JDBC thông thường**; với Java, **Cloud SQL Java Connector (JDBC Socket Factory)** thường là lựa chọn tự nhiên hơn.

### 2.2. Private IP có hai lựa chọn triển khai riêng

**A. Kết nối TCP trực tiếp:** `Cloud Run → VPC → private IP:5432`, ứng dụng tự xử lý **TLS/certificate validation** nếu chính sách yêu cầu, và dùng PostgreSQL credentials. **Không cần** `--add-cloudsql-instances` hay Cloud SQL Client IAM chỉ để mở TCP đến database; nếu dùng IAM DB auth thì có yêu cầu bổ sung.

**B. Cloud SQL Java Connector với `ipTypes=PRIVATE`:** ứng dụng dùng JDBC Socket Factory; connector thiết lập kênh được mã hóa và xác thực kết nối bằng IAM, **nhưng vẫn cần VPC route tới private IP**. Phải có Cloud SQL Admin API, `roles/cloudsql.client` và DB auth (hoặc IAM DB auth khi được cấu hình). Chỉ bật VPC egress không thay thế quyền connector.

**Không coi** Java Connector là một đường VPN: nó không tạo tuyến private IP nếu Cloud Run chưa có VPC connectivity.

## 3. Direct VPC egress và Serverless VPC Access

Cloud Run có hai cách gửi traffic **outbound** tới VPC:

| Tiêu chí | **Direct VPC egress** | **Serverless VPC Access connector** |
| --- | --- | --- |
| Kiến trúc | Cloud Run kết nối trực tiếp với VPC/subnet, **không cần connector VMs** | Connector regional làm trung gian tới VPC |
| Khuyến nghị hiện hành | **Ưu tiên cho thiết kế mới**, nếu sản phẩm/vùng hỗ trợ | Tương thích kiến trúc cũ hoặc yêu cầu riêng |
| Cấu hình chính | `--network`, `--subnet`, `--vpc-egress` | `--vpc-connector`, `--vpc-egress` |
| Mở rộng/chi phí | Không trả phí vận hành connector VM; vẫn tính traffic và tài nguyên liên quan | Connector có capacity, autoscaling và chi phí riêng |
| Firewall | Có thể dùng **network tags** trên Cloud Run revision để quản lý egress | Có rules/service agent cho connector, cần theo hướng dẫn |
| Đường ingress tới Cloud Run service | **Không tạo ingress internal trực tiếp** | **Không tạo ingress internal trực tiếp** |

Cloud Run **services/jobs** sử dụng Direct VPC cho **egress**, không phải inbound TCP listener trong VPC như một VM. Khi muốn client trong VPC gọi Cloud Run, phải thiết kế **ingress/ILB/PSC/endpoint routing** riêng.

### 3.1. Hai chế độ routing outbound

| Egress mode | Hành vi | Tình huống |
| --- | --- | --- |
| `private-ranges-only` | Chỉ chuyển lưu lượng đến **dải địa chỉ nội bộ** theo quy tắc của sản phẩm qua VPC | Cloud SQL private IP, VM/private LB |
| `all-traffic` | Chuyển **tất cả outbound** qua VPC | Cần firewall, proxy/NAT, egress inspection hoặc route đặc biệt |

Nếu dùng `all-traffic` và ứng dụng cần gọi Internet, hãy thiết kế **Public Cloud NAT/proxy** và firewall/route phù hợp; chỉ bật egress mode không tạo NAT. Khi dùng **PSC endpoint, địa chỉ không thuộc phạm vi private thông thường hoặc DNS đặc biệt**, hãy kiểm chứng chính xác địa chỉ đích và routing để không chọn sai `private-ranges-only`.

### 3.2. Các điều kiện Direct VPC egress cần kiểm tra

1. **Region của subnet phải trùng region Cloud Run service**.
2. VPC/subnet tồn tại và Cloud Run identity/service agent có quyền sử dụng (đặc biệt **Shared VPC**).
3. Subnet có **đủ địa chỉ IP** cho scale-out; Cloud Run có thể sử dụng IP trong quá trình khởi tạo/giải phóng.
4. Firewall **egress nguồn Cloud Run** và **ingress đích** cho phép TCP/port cần thiết; nếu có hierarchical policies, kiểm tra cả cấp tổ chức.
5. Cloud SQL private connectivity (PSA/PSC) đã được thiết lập và đích thực sự có private IP/endpoint.
6. Đường về, peering, Cloud VPN/Interconnect, DNS, egress restriction và địa chỉ endpoint phù hợp.
7. Nếu ứng dụng chỉ cần database ở private IP, **không nên bật all-traffic theo phản xạ**.

Trong Shared VPC, các service identities, host/service projects và **quyền Compute Network User** phải được cấu hình theo tài liệu. Đừng tự sửa quyền toàn host project để giải quyết một lỗi permission.

### 3.3. Lệnh kiểm tra và cấu hình mẫu

~~~bash
# Đọc cấu hình, không thay đổi
gcloud run services describe orders-api \
  --region=asia-southeast1 \
  --project=LAB_PROJECT_ID

gcloud compute networks subnets describe run-egress-subnet \
  --region=asia-southeast1 \
  --project=LAB_PROJECT_ID

gcloud sql instances describe orders-db \
  --project=LAB_PROJECT_ID
~~~

Giả sử service `orders-api` **đã có image hợp lệ và quyền triển khai**, thao tác dưới đây cập nhật revision để đi qua VPC:

~~~bash
# THAY ĐỔI service, chỉ chạy trong lab được phê duyệt
gcloud run services update orders-api \
  --network=app-vpc \
  --subnet=run-egress-subnet \
  --vpc-egress=private-ranges-only \
  --region=asia-southeast1 \
  --project=LAB_PROJECT_ID
~~~

Nếu dùng connector đã tồn tại:

~~~bash
# PHƯƠNG ÁN THAY THẾ; không bật chồng hai kiểu kết nối
gcloud run services update orders-api \
  --vpc-connector=orders-vpc-connector \
  --vpc-egress=private-ranges-only \
  --region=asia-southeast1 \
  --project=LAB_PROJECT_ID
~~~

**Không áp dụng cả hai lệnh liên tiếp chỉ để “tăng bảo mật”**: cần chọn một kiểu egress per revision, kiểm tra cấu hình kết quả và tác động đến traffic. Với VPC subnet ở project host, dùng cấu hình Shared VPC và resource names đúng theo hướng dẫn.

## 4. Quyền truy cập và tài nguyên chuẩn bị

### 4.1. Giá trị lab nhất quán

| Tài nguyên | Giá trị minh họa |
| --- | --- |
| Project (Cloud Run + SQL trong cùng project lab) | `LAB_PROJECT_ID` |
| Region | `asia-southeast1` |
| Cloud Run service | `orders-api` |
| Runtime service account | `orders-runtime@LAB_PROJECT_ID.iam.gserviceaccount.com` |
| VPC / subnet | `app-vpc` / `run-egress-subnet` |
| Cloud SQL instance | `orders-db` (PostgreSQL) |
| Instance connection name | `LAB_PROJECT_ID:asia-southeast1:orders-db` |
| Private IP của Cloud SQL | `10.80.0.5` (**chỉ minh họa**) |
| Database / user | `orders` / `orders_app` |
| Secret Manager | `orders-db-password` |
| Dịch vụ nội bộ khác | `payments-internal` |
| Cloud Run image | `IMAGE_URI_BY_DIGEST` (image ứng dụng thật) |

**Không dùng** các IP/name ví dụ làm giá trị thật trên production. Private IP cần lấy từ metadata instance và DNS/PSC tùy cấu hình. Tài nguyên thử nghiệm cần nằm trong project được cấp quyền, có budget và không đang phục vụ workload thật.

### 4.2. IAM theo từng vai trò

| Danh tính | Quyền tương ứng | Lưu ý |
| --- | --- | --- |
| Người triển khai Cloud Run | Quyền quản lý Cloud Run + `iam.serviceAccounts.actAs` trên runtime SA | Không phải runtime SA |
| **Runtime service account** | `roles/cloudsql.client` nếu dùng Cloud SQL Connector/Proxy | Có thể cấp ở đúng project chứa Cloud SQL |
| Runtime SA đọc secret | `roles/secretmanager.secretAccessor` trên **đúng secret** | Tách secret của dev/prod |
| Cloud Run gọi Cloud Run private | `roles/run.invoker` trên **callee service** | Cần ID token hợp lệ |
| Runtime SA gọi Google APIs khác | Role đúng trên resource mục tiêu | Không cấp Editor theo mặc định |
| VPC/Shared VPC administrator | Quyền cấu hình subnet, peering, PSC và egress | Không gộp vào app runtime SA |

Nếu Cloud Run và Cloud SQL ở **hai projects**, kiểm tra **Cloud SQL Admin API ở cả projects** khi dùng connector/proxy và grant `cloudsql.client` cho danh tính gọi trên project Cloud SQL. Đường mạng private qua Shared VPC/PSC phải được thiết kế độc lập.

**Cloud SQL Client IAM không phải PostgreSQL role.** Ngoài IAM, database phải có `orders_app` được cấp `CONNECT`, schema/table privileges cần thiết và mật khẩu hoặc IAM database auth đã thiết lập đúng. Tránh dùng `postgres` superuser trong ứng dụng.

### 4.3. Bí mật và cấu hình không nhạy cảm

Dùng **Secret Manager** cho DB password, certificates hoặc dữ liệu bí mật; dùng environment variables thông thường cho database name, instance connection name hoặc application options không nhạy cảm.

~~~bash
# Đọc metadata, không in giá trị secret
gcloud secrets describe orders-db-password \
  --project=LAB_PROJECT_ID

gcloud sql instances describe orders-db \
  --format="yaml(name,region,connectionName,ipAddresses,settings.ipConfiguration)" \
  --project=LAB_PROJECT_ID
~~~

Cloud Run có thể tham chiếu secret qua environment variable hoặc volume. Với **env var**, giá trị được resolve khi instance khởi động; rotation không tự cập nhật các container đang chạy. Với **volume**, phiên bản `latest` có thể được đọc lại theo cách khác; thiết kế rotation và retry theo tài liệu. Trong production, cân nhắc pin **version số** để rollout có thể lặp lại và audit.

Không lưu mật khẩu DB trong Dockerfile, image layer, source Git, CI logs, Cloud Run YAML công khai hoặc URL query parameters.

## 5. Kết nối Cloud SQL PostgreSQL bằng Java Connector

Với ứng dụng Java trên Cloud Run cần Cloud SQL **private IP**, một lựa chọn tiện là **Cloud SQL JDBC Socket Factory** (Cloud SQL Java Connector): connector thực hiện IAM authorization và thiết lập kết nối được mã hóa; ta yêu cầu `PRIVATE` để chọn địa chỉ private IP. VPC networking **vẫn phải sẵn sàng**.

### 5.1. Dependency và cấu hình JDBC

Ứng dụng Java cần PostgreSQL JDBC driver, HikariCP (hoặc một pool tương đương) và thư viện **Cloud SQL PostgreSQL Socket Factory** tương thích. Không cố định số version thư viện ở đây: chọn version đã được kiểm thử theo JDK/framework và theo [Cloud SQL Java Connector](https://github.com/GoogleCloudPlatform/cloud-sql-jdbc-socket-factory).

Ví dụ phương thức tạo datasource:

~~~java
import com.zaxxer.hikari.HikariConfig;
import com.zaxxer.hikari.HikariDataSource;

public final class OrderDataSource {
    private OrderDataSource() {}

    public static HikariDataSource create() {
        String dbName = System.getenv("DB_NAME");
        String dbUser = System.getenv("DB_USER");
        String dbPass = System.getenv("DB_PASS"); // Được inject từ Secret Manager
        String instance = System.getenv("INSTANCE_CONNECTION_NAME");

        HikariConfig cfg = new HikariConfig();
        cfg.setJdbcUrl("jdbc:postgresql:///" + dbName);
        cfg.setUsername(dbUser);
        cfg.setPassword(dbPass);

        cfg.addDataSourceProperty(
            "socketFactory", "com.google.cloud.sql.postgres.SocketFactory");
        cfg.addDataSourceProperty("cloudSqlInstance", instance);
        cfg.addDataSourceProperty("ipTypes", "PRIVATE");
        cfg.addDataSourceProperty("cloudSqlRefreshStrategy", "lazy");

        cfg.setMaximumPoolSize(5);
        cfg.setMinimumIdle(0);
        cfg.setConnectionTimeout(10_000);
        cfg.setMaxLifetime(1_800_000);

        return new HikariDataSource(cfg);
    }
}
~~~

**Cách đọc code:**

- `cloudSqlInstance` nhận định danh `PROJECT:REGION:INSTANCE`, **không** phải hostname/IP.
- `ipTypes=PRIVATE` buộc connector chọn private IP; thiếu Direct VPC egress/connector hoặc private IP sẽ gây lỗi.
- `cloudSqlRefreshStrategy=lazy` phù hợp serverless khi CPU có thể không chạy liên tục giữa requests; tránh phụ thuộc background refresh theo lịch khi CPU bị hạn chế.
- `DB_PASS` là PostgreSQL credential; **Cloud SQL Client IAM** của runtime service account vẫn là điều kiện riêng khi dùng connector.
- `maximumPoolSize=5` chỉ là giá trị lab; phải tính với **số instances Cloud Run đồng thời**, DB limit và transaction time.

Đây là **đoạn code datasource**, không phải ứng dụng HTTP hoàn chỉnh; cần wiring vào Spring Boot/Quarkus, dependencies đúng, retry policy và xử lý exceptions. Không tạo datasource/pool mới **cho mỗi request**; thường tạo một pool dùng lại trong vòng đời container.

### 5.2. Ví dụ kiểm tra DB không thay đổi dữ liệu

Sau khi datasource được tạo, ứng dụng có thể định nghĩa endpoint **chỉ dùng nội bộ** kiểm tra:

~~~java
try (var connection = dataSource.getConnection();
     var statement = connection.prepareStatement("SELECT 1");
     var results = statement.executeQuery()) {
    if (results.next()) {
        return "db-ok";
    }
}
~~~

Không trả thông tin chi tiết của SQL exception, username, hostname nội bộ hoặc stack trace cho client công khai. Health/liveness của Cloud Run **không nên luôn phụ thuộc DB** nếu một sự cố database sẽ khiến mọi container bị restart/trừ điểm và tăng tải lúc phục hồi. Dùng DB readiness/telemetry riêng khi cần.

### 5.3. Tại sao chọn connector thay vì TCP trực tiếp?

| Tiêu chí | Java Connector + private IP | TCP trực tiếp tới private IP |
| --- | --- | --- |
| Định danh đích | Instance connection name | Private IP hoặc private DNS |
| Xác thực kết nối tới Cloud SQL | IAM + Cloud SQL Admin API | VPC reachability, DB auth; IAM Cloud SQL không tự tham gia |
| Mã hóa tới Cloud SQL | Connector cung cấp TLS | Phải tự cấu hình TLS/CA và kiểm chứng theo yêu cầu |
| Đường mạng | **VPC private connectivity vẫn bắt buộc** | VPC private connectivity bắt buộc |
| Độ phức tạp app | Thêm thư viện và IAM/API | Driver thông thường, TLS/certificate management |
| Khi thích hợp | Ưu tiên khi muốn IAM-backed encrypted connection | Hệ thống chuẩn hóa TLS/DB host hoặc có yêu cầu connector khác |

Nếu chọn **TCP trực tiếp** trong production, không dùng ví dụ `jdbc:postgresql://10.80.0.5:5432/orders` với SSL mặc định rồi mặc định “private IP tự mã hóa”. Phải thực thi TLS policy của Cloud SQL instance, xác minh server identity và cấp chứng chỉ/cấu hình JDBC thích hợp.

## 6. Gắn Cloud Run revision với VPC, identity và secret

Giả sử image Java đã được build/push lên Artifact Registry, được kiểm tra health và có reference **theo digest**. Không dùng image mẫu `hello` để kỳ vọng test DB thành công.

### 6.1. Deploy service riêng với Direct VPC egress

~~~bash
# THAY ĐỔI hạ tầng và tạo revision: chỉ project lab có phê duyệt
gcloud run deploy orders-api \
  --image=IMAGE_URI_BY_DIGEST \
  --region=asia-southeast1 \
  --project=LAB_PROJECT_ID \
  --service-account=orders-runtime@LAB_PROJECT_ID.iam.gserviceaccount.com \
  --network=app-vpc \
  --subnet=run-egress-subnet \
  --vpc-egress=private-ranges-only \
  --ingress=internal \
  --no-allow-unauthenticated \
  --max-instances=10 \
  --concurrency=20
~~~

**Giải thích ingress:** `--ingress=internal` khiến Cloud Run chỉ chấp nhận các nguồn **được Cloud Run phân loại là internal**, **không có nghĩa** developer ở laptop có thể gọi URL trực tiếp. Lệnh vẫn yêu cầu Invoker IAM để gọi. Để test từ bên ngoài, dùng môi trường test phù hợp hoặc proxy/đường nội bộ được cho phép; không mở `--allow-unauthenticated` để xử lý 403.

### 6.2. Cấp quyền runtime (do quản trị viên thực hiện)

Ví dụ sau **chỉ minh họa** IAM bindings. Phải thay project/SA thật và xác nhận phạm vi trước khi chạy:

~~~bash
# Quyền Cloud SQL Connector/Proxy; project chứa Cloud SQL
gcloud projects add-iam-policy-binding LAB_PROJECT_ID \
  --member="serviceAccount:orders-runtime@LAB_PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/cloudsql.client"

# Quyền đọc duy nhất secret password
gcloud secrets add-iam-policy-binding orders-db-password \
  --member="serviceAccount:orders-runtime@LAB_PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/secretmanager.secretAccessor" \
  --project=LAB_PROJECT_ID
~~~

Ở production, policy tổ chức có thể yêu cầu IAM cấp theo project/resource khác hoặc roles tùy chỉnh. Đừng dùng service account mặc định có quyền Editor hay lưu JSON key trong container.

### 6.3. Cấu hình DB variables và Secret Manager

~~~bash
# THAY ĐỔI revision; phải tạo DB user, secret và instance trước
gcloud run services update orders-api \
  --region=asia-southeast1 \
  --project=LAB_PROJECT_ID \
  --set-env-vars="DB_NAME=orders,DB_USER=orders_app,INSTANCE_CONNECTION_NAME=LAB_PROJECT_ID:asia-southeast1:orders-db" \
  --update-secrets="DB_PASS=orders-db-password:7"
~~~

`:7` là **version secret minh họa**, phải thay bằng version đã tạo và được phê duyệt. Secret cần được tạo ngoài luồng bằng công cụ quản lý bí mật, không lưu password trong Markdown hoặc shell history.

**Không cần `--add-cloudsql-instances` trong ví dụ Java Connector** vì connector được khởi tạo từ JDBC. Ngược lại, nếu ứng dụng Python/Go dùng **Cloud Run built-in Auth Proxy qua Unix socket** với Cloud SQL public IP, cần cấu hình Cloud SQL connection để socket xuất hiện tại `/cloudsql/INSTANCE_CONNECTION_NAME` và cấp quyền Cloud SQL Client. Hai cách này **không phải các cờ bắt buộc cộng dồn**.

### 6.4. Kiểm tra revision sau deploy

~~~bash
gcloud run services describe orders-api \
  --region=asia-southeast1 \
  --project=LAB_PROJECT_ID

gcloud run revisions list \
  --service=orders-api \
  --region=asia-southeast1 \
  --project=LAB_PROJECT_ID

gcloud run services logs read orders-api \
  --region=asia-southeast1 \
  --project=LAB_PROJECT_ID \
  --limit=50
~~~

Xác nhận network/subnet/egress, runtime service account, secret references, revision rollout và logs. Không ghi giá trị secret ra logs. **Một revision Ready không đủ chứng minh kết nối DB đã thành công** nếu code kết nối chỉ khi có request; cần smoke test từ caller được phép và kiểm tra truy vấn `SELECT 1`.

## 7. Phương án thay thế: built-in Cloud SQL connection qua public IP

Cloud Run hỗ trợ tích hợp Cloud SQL Auth Proxy cho các ngôn ngữ có thể dùng **Unix sockets**. Ví dụ riêng với PostgreSQL:

~~~bash
# Thay đổi Cloud Run revision: cấp Cloud SQL connection config
gcloud run services update orders-api \
  --region=asia-southeast1 \
  --project=LAB_PROJECT_ID \
  --add-cloudsql-instances=LAB_PROJECT_ID:asia-southeast1:orders-db
~~~

Đường socket:

~~~text
/cloudsql/LAB_PROJECT_ID:asia-southeast1:orders-db/.s.PGSQL.5432
~~~

Một số PostgreSQL libraries tự nối hậu tố `.s.PGSQL.5432`; một số yêu cầu chỉ định đầy đủ. Giới hạn độ dài Unix socket path trên Linux cần được xét. **Java nên ưu tiên Cloud SQL Java Connector**, không mặc định driver JDBC có thể mở Unix socket như Python/Go.

**Các lưu ý:**

- Dùng public IP path với built-in Cloud SQL connection vẫn cần **IAM `roles/cloudsql.client`**, Cloud SQL Admin API và DB auth.
- Với Cloud Run **first generation execution environment**, có hạn chế Cloud SQL server CA mode (chỉ per-instance CA) theo tài liệu do embedded Auth Proxy cũ; nên kiểm tra execution environment và CA khi dùng public-proxy path.
- **Tích hợp Cloud SQL không tự biến instance thành chỉ có private IP**. Phải kiểm tra cấu hình public/private IP riêng.
- Private SQL qua Direct VPC egress với **Java Connector `ipTypes=PRIVATE`** là phương án chính trong bài, không trộn lẫn lệnh trên vào cùng luồng chỉ để “chắc chắn”.

## 8. Kết nối đến dịch vụ VPC riêng khác

Không phải dịch vụ riêng nào cũng là Cloud SQL. Một Cloud Run app có thể gọi:

| Đích nội bộ | Ví dụ | Điều kiện cần |
| --- | --- | --- |
| Compute Engine VM | `10.70.1.10:8080` | VPC route, firewall ingress tới VM, app auth |
| GKE internal Load Balancer | `10.70.2.20:8443` | ILB/backend health, VPC reachability, TLS |
| Memorystore | Private IP/endpoint của Redis/Valkey | Product-specific authorized network, AUTH/TLS khi có |
| Cloud SQL private IP | `10.80.0.5:5432` | PSA/PSC, DB auth và connector/TLS tùy phương thức |
| Private Google API endpoint | PSC endpoint hoặc `private.googleapis.com` | DNS, routes và IAM của Google API |
| Cloud Run service ingress internal | URL Cloud Run hoặc internal LB/PSC | **Đường được Cloud Run coi là internal + ID token/Invoker IAM** |

### 8.1. VM/private load balancer

Với một dịch vụ HTTP chạy trên VM chỉ có internal IP, ứng dụng có thể gọi:

~~~text
http://10.70.1.10:8080/internal/status
~~~

**Điều kiện:** VM phải lắng nghe trên internal interface (không chỉ `127.0.0.1`), firewall phải cho đúng source Cloud Run đến port, VPC route/tuyến về phù hợp và ứng dụng tự xác thực request. **Internal IP không thay thế mTLS hoặc xác thực ứng dụng**.

Trong cấu hình Direct VPC egress, có thể đặt network tag cho revision:

~~~bash
# Chỉ ví dụ thay đổi revision trong lab
gcloud run services update orders-api \
  --network=app-vpc \
  --subnet=run-egress-subnet \
  --network-tags=orders-egress \
  --vpc-egress=private-ranges-only \
  --region=asia-southeast1 \
  --project=LAB_PROJECT_ID
~~~

Sử dụng tag này trong firewall egress phù hợp thay vì mở outbound mọi port. Ingress firewall của **VM đích** vẫn cần thiết, theo nguồn thực và chính sách hiện hành.

### 8.2. Private Google Access / PSC không phải NAT

- **Private Google Access** cho truy cập Google APIs/services hỗ trợ từ địa chỉ nội bộ; subnet, DNS, routing và IAM phải phù hợp.
- **Private Service Connect** cung cấp private endpoint cho Google APIs hoặc các managed services được hỗ trợ, tùy loại PSC; cần cấu hình endpoint/DNS/acceptance đúng.
- **Public Cloud NAT** xử lý outbound đến Internet theo route/firewall; **không mở inbound** cho VM/private Cloud SQL.
- **Cloud SQL private IP qua PSA** kết nối đến managed producer network; không nhầm với một request đến `sqladmin.googleapis.com`.

Nếu PSC endpoint dùng địa chỉ không thuộc private ranges mặc định, điều chỉnh egress mode/routes theo hướng dẫn thực tế và kiểm tra địa chỉ đích mà application DNS resolve.

## 9. Gọi Cloud Run service nội bộ: đường mạng và ID token

Giả sử `orders-api` cần gọi `payments-internal` qua HTTPS. Dịch vụ nhận được cấu hình `ingress=internal` và **yêu cầu xác thực**. Có hai điều kiện **đều phải đúng**:

1. **Network ingress:** request từ nguồn được Cloud Run coi là **internal**, qua một đường VPC/endpoint được hỗ trợ.
2. **Invoker IAM:** runtime service account của `orders-api` được cấp `roles/run.invoker` trên service `payments-internal`, gửi Google-signed **ID token** có audience hợp lệ.

Cấp `roles/run.invoker` **không tự vượt** ingress restriction; thiết lập `ingress=internal` cũng **không tự cho phép** mọi caller bỏ qua xác thực.

### 9.1. Tại sao cùng project vẫn có thể bị chặn?

Nếu Cloud Run caller chỉ cấu hình `private-ranges-only`, việc gọi URL `https://...run.app` có thể **không đi qua VPC** vì URL được resolve tới địa chỉ không thuộc private ranges. Callee `ingress=internal` có thể từ chối dù hai services ở cùng project.

Các thiết kế được Cloud Run hỗ trợ gồm:

- Caller dùng **Direct VPC egress hoặc connector ở chế độ `all-traffic`**, subnet có **Private Google Access**, và đường đến `run.app` qua VPC được Google nhận là internal.
- Sử dụng **Private Service Connect** hoặc **internal Application Load Balancer** trước callee, gọi qua private endpoint/IP.
- Cấu hình **private.googleapis.com/restricted.googleapis.com** cho `run.app` qua DNS và PGA theo hướng dẫn, kiểm tra tuyến thực.

**Không dùng `--ingress=all` để “sửa” lỗi khi yêu cầu của doanh nghiệp là private-only.** Xác định nguồn, URL resolution, route, ingress và IAM riêng.

### 9.2. Ví dụ cấp quyền gọi dịch vụ

~~~bash
# IAM CHO SERVICE NHẬN, do người có quyền quản trị thực hiện
gcloud run services add-iam-policy-binding payments-internal \
  --region=asia-southeast1 \
  --project=LAB_PROJECT_ID \
  --member="serviceAccount:orders-runtime@LAB_PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/run.invoker"
~~~

Trong `orders-api`, sử dụng **Google Auth Library** lấy Google-signed **ID token** từ runtime identity qua Application Default Credentials/metadata server; không tải service account JSON key.

~~~text
callee_service_url = "https://payments-internal-<hash>-as.a.run.app"
audience = callee_service_url  # Hoặc custom audience được cấu hình
id_token = GoogleAuthLibrary.fetch_id_token(audience)

GET <callee_service_url>/internal/quote
Authorization: Bearer <id_token>
~~~

Đây là **pseudocode**, không phải mã có thể chạy nguyên văn. Với Cloud Run authentication mặc định, `aud` phải là **service URL của callee**, kể cả khi gọi một traffic tag URL; custom domain không phải `aud` mặc định. Nếu đi qua internal LB/PSC và dùng host khác, vẫn phải xử lý audience đúng theo cấu hình được hỗ trợ.

**Không đưa ID token vào logs**. ID token khác OAuth **access token** dùng để gọi Google APIs. Nếu request trả 401, xem token, chữ ký, expiry, audience; nếu 403, xem `run.invoker`, ingress policy và quyền resource.

### 9.3. Phân biệt ingress/egress cho hai Cloud Run services

~~~mermaid
flowchart LR
  A["orders-api\nCaller"] -->|"Direct VPC egress / connector"| VPC["VPC + PGA hoặc PSC/ILB"]
  VPC -->|"HTTPS + ID token"| B["payments-internal\nIngress internal + IAM"]
  DB["Cloud SQL private IP"] -. "TCP:5432 qua VPC" .-> A
~~~

Một Cloud Run service có thể cùng lúc:

- Nhận requests từ nội bộ qua ingress + IAM.
- Gửi requests tới PostgreSQL private IP qua VPC.
- Gửi HTTPS tới một Cloud Run service khác bằng ID token và đường được coi là internal.

Ba luồng có **điều kiện** khác nhau, không được gộp vào một khái niệm “Cloud Run private”.

## 10. Connection pool, autoscaling và độ tin cậy database

Cloud Run tự mở rộng bằng cách tạo nhiều container instances; **mỗi instance có thể có connection pool riêng**. Nếu thiết kế pool cho một máy chủ cố định, Cloud SQL có nguy cơ cạn `max_connections` khi traffic tăng đột biến.

### 10.1. Tính connection budget

Công thức ước lượng:

~~~text
DB connections tối đa từ một revision ≈
  số Cloud Run container instances đồng thời × maximumPoolSize mỗi instance
~~~

Ví dụ:

| Tham số | Giá trị minh họa |
| --- | ---: |
| DB connection budget dành cho orders-api | 120 |
| Cloud Run max instances (giới hạn cấu hình) | 10 |
| Hikari maximumPoolSize | 5 |
| Số connections ở trạng thái bão hòa dự kiến | 10 × 5 = 50 |
| Dự phòng cho revision cũ/mới cùng phục vụ | Phải tính riêng |
| Dự phòng cho migrations, admin và services khác | Phải tính riêng |

Không coi con số 50 là tuyệt đối: trong **rollout**, các revisions cũ và mới có thể cùng chạy; scaling hoặc platform events có thể làm số instances thực tế dao động, và mỗi workload khác cũng dùng DB. Khi thay config max instances, kiểm tra mức áp dụng **service-level/revision-level** của Cloud Run phiên bản đang dùng.

Với **built-in Cloud SQL connection** của Cloud Run, tài liệu Cloud SQL nêu giới hạn **100 connections tới một database trên mỗi Cloud Run instance**; giới hạn này **không áp dụng giống hệt** cho Java Language Connector, Cloud SQL Auth Proxy sidecar hay direct TCP. Dù vậy, **giới hạn của database** vẫn tồn tại cho mọi phương thức. <https://docs.cloud.google.com/sql/docs/postgres/quotas>

### 10.2. Thiết lập ứng dụng

- **Pool dùng lại giữa requests** thay vì mở connection mới trên mỗi request.
- `maximumPoolSize` theo DB budget; `minimumIdle=0` có thể phù hợp workload co giãn.
- Timeout kết nối và query **ngắn, có giới hạn**, tránh để request bị treo lâu hơn request timeout.
- Backoff + jitter cho lỗi kết nối **tạm thời**; không retry vô hạn khi password/IAM sai.
- Transaction ngắn, không giữ connection trong lúc đợi một HTTP request bên ngoài.
- Có readiness/metrics riêng cho DB connectivity; liveness không buộc phải fail mỗi khi DB lỗi thoáng qua.
- Nếu cần nhiều kết nối và traffic cao, cân nhắc database connection pooling/managed connection pooling được hỗ trợ, nhưng phải kiểm tra cách tương thích với SQL engine và connector.

**CPU throttling:** với request-based billing, background tasks duy trì pool có thể không chạy liên tục lúc idle. Cloud SQL docs khuyến nghị Java Connector `cloudSqlRefreshStrategy=lazy` cho serverless. Nếu workload cần background pool maintenance liên tục, đánh giá instance-based billing và chi phí.

### 10.3. HA failover và xử lý lỗi

Khi Cloud SQL HA failover, các sessions hiện tại có thể bị đóng; ứng dụng phải:

1. Nhận biết connection đã hỏng, loại khỏi pool.
2. Tạo kết nối mới tới endpoint/danh tính database hiện hành.
3. Retry **idempotent operation** có backoff; không lặp giao dịch ghi tiền hoặc đơn hàng một cách mù quáng.
4. Theo dõi 5xx/latency và kết nối database.
5. Kiểm tra các migrations tương thích khi rollback revision.

**Không biến mỗi lỗi `connection refused` thành yêu cầu restart mọi Cloud Run instances**. Sự cố VPC/DB/Secret Manager có thể là lỗi dùng chung; restart đồng loạt thường làm phục hồi khó hơn.

## 11. Bảo mật và vận hành production

### 11.1. Kiểm soát từ ngoài vào

| Cấu hình | Ý nghĩa |
| --- | --- |
| `ingress=internal` | Chỉ các nguồn được Cloud Run coi là nội bộ |
| `ingress=internal-and-cloud-load-balancing` | Cho phép đường qua external Application Load Balancer có kiểm soát; không cho truy cập trực tiếp Internet tới `run.app` theo mặc định |
| `ingress=all` | Cho phép mọi nguồn mạng gọi endpoint; **IAM vẫn độc lập** |
| `--no-allow-unauthenticated` | Yêu cầu xác thực Invoker; không thay cấu hình ingress |
| Disabled default URL khi phù hợp | Giảm một đường truy cập; phải xét tích hợp/trigger liên quan |

Một service dùng DB private IP **vẫn có thể có HTTP endpoint public** nếu ingress không bị hạn chế. Đừng nhầm “DB private” với “API private”.

### 11.2. Kiểm soát từ Cloud Run ra

- Dùng **Direct VPC egress**, subnet và network tags đúng nguồn; cho egress tối thiểu.
- Kiểm tra VPC firewall/hierarchical policies; Cloud SQL private network có cấu hình provider/PSC riêng, **không phải VM firewall thuần túy**.
- Nếu chọn `all-traffic`, thiết kế NAT/proxy, DNS và route thay vì kỳ vọng Internet tự hoạt động.
- Với nguồn Google APIs (Secret Manager, Cloud SQL Admin API), xem đường truy cập được hỗ trợ và IAM, **không mở TCP/5432 đến IP của Google API**.
- Không log passwords, connection strings có credentials hoặc ID tokens.
- Hạn chế quyền của runtime service account; không trộn build/deploy identity với runtime identity.
- Sử dụng TLS/mTLS hoặc connector bảo đảm mã hóa thích hợp; private IP **không mặc định xác thực máy chủ DB**.

### 11.3. Kế hoạch thay đổi và rollback

Khi đổi VPC egress, subnet, service account hoặc cách Cloud SQL connect, Cloud Run tạo **revision** mới. Hãy rollout canary với traffic thấp khi phù hợp, giữ revision trước để rollback, quan sát connection error, latency và DB capacity. Sau rollback revision, **IAM, secrets và database schema không tự quay về trạng thái cũ**.

**Chi phí cần dự trù:** Cloud Run CPU/memory/requests, Cloud SQL instance HA/storage/backups, Connector hoặc Direct VPC data transfer, Cloud NAT nếu dùng, Secret Manager, Cloud Logging/Monitoring và data transfer liên vùng. Đặt Cloud Run/Cloud SQL **cùng region** thường giảm latency và một phần chi phí/rủi ro; vẫn cần đánh giá data residency và DR.

## 12. Quan sát và xử lý sự cố có hệ thống

### 12.1. Bộ lệnh kiểm tra chỉ đọc

~~~bash
# Kiểm tra networking, ingress, runtime identity và revision
gcloud run services describe orders-api \
  --region=asia-southeast1 \
  --project=LAB_PROJECT_ID

# Kiểm tra private/public IP, instance connection name
gcloud sql instances describe orders-db \
  --project=LAB_PROJECT_ID

# Kiểm tra subnet source của Cloud Run
gcloud compute networks subnets describe run-egress-subnet \
  --region=asia-southeast1 \
  --project=LAB_PROJECT_ID

# Kiểm tra logs (không in secrets)
gcloud run services logs read orders-api \
  --region=asia-southeast1 \
  --project=LAB_PROJECT_ID \
  --limit=100
~~~

Ngoài CLI, xem **Cloud Run request/container logs, Cloud SQL Insights/connection metrics, Cloud Monitoring, VPC Flow Logs, Firewall Rules Logging** khi được bật. VPC Flow Logs có sampling/aggregation; không thay thế kiểm thử ứng dụng thật.

### 12.2. Bảng chẩn đoán

| Triệu chứng | Tầng có khả năng lỗi | Bước kiểm tra |
| --- | --- | --- |
| Cloud Run revision không Ready | Image không nghe cổng `PORT`, startup/crash hoặc env sai | Container logs, container contract, health |
| `connection timed out` tới private IP:5432 | VPC egress, subnet/region, firewall, PSC/PSA, DNS | Route và private IP thật; test từ đúng nguồn |
| `connection refused` | Không có listener, IP/port sai, DB đang failover | Cloud SQL state, port và logs |
| Java Connector báo 403 | `roles/cloudsql.client`, Cloud SQL Admin API, service identity | IAM ở project chứa SQL, Admin API ở projects liên quan |
| `password authentication failed` | Sai PostgreSQL username/password, DB role hoặc secret version | DB auth, Secret Manager reference, rotation |
| `permission denied for relation` | Thiếu PostgreSQL table/schema privilege | DB GRANT, migration, không tăng Google Cloud IAM |
| `No route to host` hoặc DNS NXDOMAIN | Route/peering/DNS/PSC endpoint chưa đúng | DNS record, VPC peering, subnet, firewall |
| Public IP SQL bị tắt và app ngừng hoạt động | Connector/proxy đang chọn PUBLIC, chưa cấu hình PRIVATE | `ipTypes=PRIVATE`, VPC routing, private IP |
| Cloud Run private callee trả 401 | ID token thiếu/sai audience/hết hạn | Credential library, `aud`, bearer header |
| Callee trả 403 | `run.invoker`, ingress internal không nhận route, org policy | Network classification + IAM |
| DB `too many connections` | Cloud Run scale × pool size vượt DB budget | Instance counts, pool configs, rollout overlap |
| Pool có stale connections sau idle | DB đóng connection, background refresh bị hạn chế CPU | Connection validation, lazy refresh, billing mode |
| PSC endpoint truy cập thất bại | DNS/consumer endpoint/service attachment/acceptance hoặc route | PSC configuration và allowed consumer |
| Cấu hình `all-traffic` gây mất Internet | Không có Cloud NAT/proxy hoặc egress policy chặn | Default route, NAT, firewall, DNS |
| Service A gọi internal Service B bị chặn | Request tới `run.app` không đi qua VPC được nhận là internal | VPC all-traffic+PGA, PSC/ILB hoặc DNS phù hợp |
| Secret update không có tác dụng trên instance đang chạy | Env secret resolved lúc startup | Deploy revision mới/rotation plan |

### 12.3. Quy trình tìm nguyên nhân

~~~mermaid
flowchart TD
    ERR["Lỗi gọi Cloud SQL / private service"] --> DEST{"Đích là loại nào?"}
    DEST -->|"Cloud SQL private IP"| ROUTE["Kiểm tra VPC, IP/PSA/PSC, DNS, port 5432"]
    DEST -->|"Cloud Run private"| IN["Kiểm tra ingress internal + đường route VPC"]
    DEST -->|"VM/cache/private LB"| NET["Kiểm tra listener, firewall, DNS và route"]
    ROUTE --> AUTH{"TCP tới đích thành công?"}
    AUTH -->|"Không"| RNET["Sửa network; chưa đổi DB password/IAM"]
    AUTH -->|"Có"| DB["Kiểm tra Connector IAM, TLS, DB auth và SQL grants"]
    IN --> ID["Kiểm tra ID token audience và run.invoker"]
    NET --> APP["Kiểm tra app auth/TLS/health"]
    DB --> MET["Kiểm tra pool, timeout, autoscaling và logs"]
    ID --> MET
    APP --> MET
    RNET --> MET
~~~

**Phân biệt ba lớp khi đọc log:** *network reachability → authentication → application/SQL permission*. Tránh “cho all egress + Editor + public database IP” vì có thể giấu lỗi gốc và mở thêm rủi ro.

## 13. Bài lab có hướng dẫn

**Mục tiêu:** Kết nối một Cloud Run Java service đã có image hợp lệ tới Cloud SQL PostgreSQL private IP, bảo vệ secret và định lượng connection budget. Không cần thực sự thay đổi production; lab có thể làm bằng mô hình và câu trả lời nếu không có sandbox.

### 13.1. Preflight

1. Xác minh project/region, `orders-db` **đã có private IP**, cấu hình PSA/PSC và database `orders`/user `orders_app`.
2. Xác minh VPC/subnet cùng region với Cloud Run, đủ IP, đường đến private Cloud SQL hoạt động.
3. Tạo hoặc xác minh runtime service account có Cloud SQL Client IAM (cho Java Connector) và Secret Manager Secret Accessor trên đúng secret.
4. Đảm bảo image Java chạy trên Cloud Run, đọc env/secret, dùng JDBC Socket Factory `ipTypes=PRIVATE`; **không** chỉ dùng container echo/hello.
5. Có quota, billing, logs, backup database, kế hoạch rollback và thời gian lab được phép.

### 13.2. Triển khai và thử kết nối

1. Deploy với Direct VPC egress `private-ranges-only`, ingress internal và yêu cầu xác thực.
2. Gắn variables không nhạy cảm, tham chiếu DB password từ Secret Manager.
3. Xem Cloud Run revision logs. Dùng một **caller được phép trong VPC** kiểm thử endpoint DB `SELECT 1` và ứng dụng trả HTTP 200 khi DB hoạt động.
4. Cố tình đổi **cấu hình DNS đích trong môi trường test riêng** (không chỉnh subnet production) để phân biệt lỗi timeout/DNS với lỗi auth.
5. Thử user thiếu DB privilege trên bảng test (không dùng superuser), xem PostgreSQL error khác IAM 403 như thế nào.
6. Khôi phục cấu hình lab; xác minh latency, SQL connections, logs và không rò secret.

**Không dùng lệnh tắt Cloud SQL, xóa bảng hoặc làm đứt private network production** để thử fault injection.

### 13.3. Bài test Cloud Run → Cloud Run nội bộ

1. Tạo `payments-internal` trên project lab, cấu hình `ingress=internal` và require authentication.
2. Cấp `roles/run.invoker` trên callee cho đúng runtime service account của caller.
3. Thiết kế đường từ caller qua **VPC all-traffic + PGA**, hoặc **PSC/internal LB** được hỗ trợ.
4. Gửi Google-signed **ID token** có `aud` là callee URL; xác nhận request thành công.
5. Bỏ Invoker IAM của **một caller test** và chứng minh 403 (không thay quyền production).
6. Giữ ingress internal; không mở anonymous invocation chỉ để vượt lỗi.

### 13.4. Bằng chứng cần nộp

| Mục | Bằng chứng |
| --- | --- |
| Direct VPC egress | Cloud Run revision networking có VPC/subnet/egress |
| SQL private connectivity | Cloud SQL private IP + route/PSA/PSC được xác nhận |
| IAM/runtime identity | Runtime SA có quyền cần thiết, không phải Editor |
| DB authentication | User riêng chỉ có quyền tối thiểu |
| Secret | Service tham chiếu Secret Manager version, không plaintext |
| Test query | Kết quả an toàn của `SELECT 1`, không ghi mật khẩu |
| Pool budget | Max instances × maximumPoolSize và DB headroom |
| Private service | ID token/Invoker IAM và đường mạng được phép |
| Observability | Logs/metrics latency, DB connections, lỗi thất bại thử nghiệm |
| Rollback | Revision trước còn khả dụng; cấu hình/data được đối chiếu |

## 14. Case study: Orders API trong doanh nghiệp

Một doanh nghiệp chạy API đặt hàng theo kiến trúc:

- **Cloud Run orders-api** nhận request có xác thực, kiểm soát ingress.
- **Cloud SQL PostgreSQL** lưu đơn hàng, private IP, HA và backup.
- **Redis-compatible cache** trên private endpoint.
- **Cloud Run payments-internal** chỉ nhận requests từ nguồn internal và service account được phép.
- **Cloud Logging/Monitoring** giám sát response latency, SQL errors và saturation.

**Thiết kế được chọn:** Direct VPC egress trên `orders-api` để gọi Cloud SQL và cache; Java Connector PRIVATE; DB password trong Secret Manager; pool 5 kết nối/container với max instances được giới hạn theo DB budget. Gọi payments qua đường mạng được Cloud Run coi là internal và ID token, không dùng anonymous HTTP.

**Sự cố giả định:** Black Friday, request tăng 8 lần. Autoscaling tạo nhiều Cloud Run instances; DB báo `too many connections`. Tăng CPU của Cloud Run **không giải quyết** DB connection budget. Đội vận hành nên kiểm tra DB connections, giảm pool hoặc cấu hình max instances/concurrency hợp lý, tối ưu query và dùng cache/queue khi cần. Trong quá trình rollout, tính cả **instances cũ lẫn mới** để tránh tăng kết nối đột biến.

**Đánh giá thành công:** API đạt SLO, không có SQL auth errors bất thường, private endpoints không mở công khai, IAM tối thiểu và có đủ khả năng phục hồi/rollback.

## 15. Câu hỏi ôn tập và đáp án ngắn

1. **Cloud Run service có `ingress=internal` thì tự kết nối được Cloud SQL private IP?** Không, ingress và egress độc lập.
2. **Direct VPC egress khác connector?** Direct không cần connector VM; cả hai cung cấp outbound vào VPC.
3. **`private-ranges-only` khác `all-traffic`?** Chỉ tuyến tới private/internal ranges so với tất cả outbound qua VPC.
4. **Cloud SQL Java Connector có tự tạo tuyến VPC không?** Không; phải có network reachability.
5. **Khi dùng Java Connector chọn private IP bằng gì?** `ipTypes=PRIVATE`, cùng các quyền/API phù hợp.
6. **`roles/cloudsql.client` có thay PostgreSQL password/DB role không?** Không.
7. **Với TCP trực tiếp tới private IP, kết nối mặc định đã bảo đảm TLS?** Không; phải cấu hình và kiểm chứng theo chính sách.
8. **Vì sao Java không dùng Unix socket Cloud Run giống Python?** JDBC thường không có hỗ trợ Unix sockets native, nên ưu tiên Java Connector.
9. **Cloud Run gọi service internal cùng project, chỉ có run.invoker thì đủ?** Không; request phải đi đường được Cloud Run coi là internal.
10. **ID token khác access token?** ID token xác thực caller tới Cloud Run; access token dùng cho Google APIs.
11. **Audience token tới Cloud Run là gì?** Service URL hoặc custom audience được cấu hình; không mặc định là custom domain.
12. **10 instances × pool 5 tạo tối đa bao nhiêu connections một revision?** Xấp xỉ 50, chưa tính revisions khác và kết nối DB còn lại.
13. **Built-in Cloud SQL connection có giới hạn 100 connections/Cloud Run instance có áp cho mọi phương thức không?** Không; tài liệu nêu ngoại lệ cho language connectors, sidecar proxy và direct IP.
14. **Bị 403 nên mở firewall 0.0.0.0/0?** Không; kiểm tra IAM/Invoker/SQL connector permissions trước.
15. **Rollback Cloud Run revision có rollback secrets/schema database không?** Không; cần kế hoạch riêng.

## 16. Checklist production và nguồn đọc thêm

- [ ] Xác định Cloud Run là **caller hay callee**; ingress/egress cấu hình độc lập.
- [ ] Chọn rõ Cloud SQL **public/proxy** hoặc **private IP qua VPC/PSC**; không trộn các cơ chế.
- [ ] Cloud Run và subnet đúng region, đủ IP, route/firewall/DNS kiểm chứng từ đúng nguồn.
- [ ] Runtime SA có IAM tối thiểu; Cloud SQL Client khi dùng connector/proxy; Invoker trên callee khi gọi service.
- [ ] DB user/role, TLS, secrets và Secret Manager rotation được quản lý riêng.
- [ ] Java Connector chọn `ipTypes=PRIVATE` và refresh strategy phù hợp serverless.
- [ ] Connection pool/Cloud Run max instances/concurrency được tính theo DB budget, kể cả rollout.
- [ ] Cloud SQL HA/backup, idempotency, retry/backoff và test failover được lên kế hoạch.
- [ ] Ingress private không bị mở thành public chỉ để test; có phương pháp smoke test từ nguồn cho phép.
- [ ] Logs/metrics/alerts có HTTP errors, SQL connections, VPC failures, secret/Invoker denies.
- [ ] Có change approval, canary, rollback revision và migration compatibility.
- [ ] Theo dõi Cloud Run/Cloud SQL/NAT/egress/connector/Logging chi phí.

**Tài liệu Google Cloud chính thức:**

- [Cloud SQL PostgreSQL: Connect from Cloud Run](https://docs.cloud.google.com/sql/docs/postgres/connect-run) — public IP, private IP, Java connector, Unix socket, IAM và pooling.
- [Cloud SQL Java Connector](https://github.com/GoogleCloudPlatform/cloud-sql-jdbc-socket-factory) — JDBC Socket Factory, `ipTypes` và lazy refresh.
- [Direct VPC egress](https://docs.cloud.google.com/run/docs/configuring/vpc-direct-vpc) — cấu hình mạng/subnet/egress.
- [VPC connector](https://docs.cloud.google.com/run/docs/configuring/vpc-connectors) — alternative connector mode.
- [Compare Direct VPC egress and connectors](https://docs.cloud.google.com/run/docs/configuring/connecting-vpc) — ưu/nhược và tính phí.
- [Cloud Run private networking](https://docs.cloud.google.com/run/docs/securing/private-networking) — nội bộ qua VPC, ILB, PSC và PGA.
- [Cloud Run ingress](https://docs.cloud.google.com/run/docs/securing/ingress) — internal, load balancing và all.
- [Cloud Run service-to-service authentication](https://docs.cloud.google.com/run/docs/authenticating/service-to-service) — Invoker IAM, ID token, audience.
- [Cloud Run Secret Manager integration](https://docs.cloud.google.com/run/docs/configuring/services/secrets) — environment variables, secret volumes, versions.
- [Cloud SQL PostgreSQL: Connection management](https://docs.cloud.google.com/sql/docs/postgres/manage-connections) — pooling, retries, timeouts.
- [Cloud SQL PostgreSQL: Quotas](https://docs.cloud.google.com/sql/docs/postgres/quotas) — giới hạn kết nối và built-in proxy.
- [Cloud SQL private IP](https://docs.cloud.google.com/sql/docs/postgres/configure-private-ip) — PSA, địa chỉ và network prerequisites.
- [Cloud SQL Private Service Connect](https://docs.cloud.google.com/sql/docs/postgres/about-private-service-connect) — endpoint private và yêu cầu DNS.
- [Cloud Run pricing](https://cloud.google.com/run/pricing), [Cloud SQL pricing](https://cloud.google.com/sql/pricing) — dự toán chi phí.

**Ghi nhớ:** Cloud Run kết nối thành công với dịch vụ riêng chỉ khi **mạng đúng đường, danh tính đúng quyền, ứng dụng dùng đúng giao thức/xác thực**, và số kết nối còn nằm trong khả năng phục vụ của backend. **VPC egress, Cloud SQL Client IAM và PostgreSQL permissions là ba lớp khác nhau**; kiểm chứng từng lớp trước khi mở rộng traffic.
