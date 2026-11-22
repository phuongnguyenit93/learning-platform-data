# Connection pooling và giới hạn kết nối ứng dụng

> **Chương:** Cloud SQL và AlloyDB  
> **Mô-đun:** CLOUD_PROVIDERS_GCP

Một API Java quản lý đơn hàng chạy trên **Cloud Run**, dữ liệu ở **Cloud SQL for PostgreSQL** hoặc **AlloyDB for PostgreSQL**. Trong giờ bình thường, vài container có thể xử lý mọi request. Khi có chương trình khuyến mại, Cloud Run tăng hàng chục instances, mỗi instance mở một nhóm kết nối PostgreSQL. Database bắt đầu báo `too many connections` dù CPU chưa dùng hết. Vấn đề thường nằm ở **tổng số kết nối được tạo bởi ứng dụng và cách tái sử dụng chúng**, không nhất thiết ở năng lực xử lý truy vấn.

Bài thuộc chương **Cloud SQL và AlloyDB** của mô-đun **CLOUD_PROVIDERS_GCP**: sau khi học tổ chức project, IAM, VPC, Compute Engine, GKE, Cloud Run, lưu trữ và cơ sở dữ liệu, bạn cần biết cách triển khai ứng dụng an toàn, tự động hóa phát hành, theo dõi độ tin cậy và chi phí. Bài dùng **PostgreSQL** làm ví dụ xuyên suốt. MySQL/SQL Server có driver, mô hình connection và managed-pooling khác; không áp nguyên các câu lệnh PostgreSQL cho chúng.

**Kết quả học tập:**

1. Phân biệt **kết nối client**, **server connection**, **pool trong ứng dụng**, **pooler phía database** và **Cloud SQL Auth Proxy**.
2. Đọc `max_connections`, tính **connection budget** theo số Cloud Run instances/GKE Pods và các nguồn dùng chung database.
3. Cấu hình **HikariCP** cho Java với giới hạn pool, timeout, vòng đời kết nối và đóng tài nguyên đúng cách.
4. Chọn Managed Connection Pooling phù hợp với **Cloud SQL for PostgreSQL Enterprise Plus** hoặc **AlloyDB**, hiểu yêu cầu và cổng kết nối.
5. Phân biệt **transaction pooling** và **session pooling**; nhận biết tính năng PostgreSQL không tương thích.
6. Quan sát active/idle/waiting clients, nguyên nhân bão hòa, failover, connection leaks và chi phí.
7. Hoàn thành bài lab kiểm thử tải/rollback cấu hình mà không tác động vào cơ sở dữ liệu production.

## 1. Vì sao nhiều kết nối chưa chắc nhanh hơn?

PostgreSQL thường sử dụng một **backend process** cho mỗi server connection. Mỗi connection tiêu thụ bộ nhớ, tài nguyên quản lý và thời gian xác thực/thiết lập TLS. Khi ứng dụng liên tục mở/đóng connection, phần overhead có thể chiếm đáng kể thời gian request. Khi mở quá nhiều connection, database có thể bị tranh chấp CPU/memory hoặc từ chối sessions mới.

**Connection pool** giữ một tập connection đã được thiết lập để các requests mượn rồi trả về, thay vì mở connection mới cho mỗi truy vấn.

~~~mermaid
flowchart LR
  REQ["HTTP requests"] --> API["Cloud Run instance\nJava orders-api"]
  API --> H["HikariCP\nMax pool = 5"]
  H -->|"Borrow / return"| DB["Cloud SQL / AlloyDB\nPostgreSQL server"]
  API2["Cloud Run instance khác"] --> H2["HikariCP\nMax pool = 5"]
  H2 --> DB
  DB --> M["DB max_connections\nGiới hạn tổng"]
~~~

### 1.1. Những con số không tương đương

| Khái niệm | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **HTTP concurrency** | Requests cùng lúc một instance có thể nhận | Cloud Run concurrency = 40 |
| **Pool size** | Số database connections **tối đa trong một pool** | Hikari maximumPoolSize = 5 |
| **Active connections** | Connections đang được ứng dụng mượn và sử dụng | 3/5 |
| **Idle connections** | Connections chưa được mượn nhưng pool giữ để tái sử dụng | 2/5 |
| **Pending/waiting borrowers** | Threads/requests chờ pool cấp connection | 8 threads đang đợi |
| **Server connections** | PostgreSQL backend sessions đang tồn tại | 130 connections trên primary |
| **`max_connections`** | Giới hạn cấu hình PostgreSQL, không phải số connections rảnh cho riêng một app | 300 (minh họa) |

Một ứng dụng nhận 40 concurrent HTTP requests **không cần mặc định 40 database connections**: có request xử lý JSON/cache mà không truy vấn DB; một connection có thể phục vụ nhiều truy vấn **tuần tự**. Ngược lại, một request giữ transaction quá lâu có thể chiếm connection trong nhiều giây và tạo hàng chờ.

### 1.2. Lifecycle của một pool

~~~text
Request → pool.getConnection()
    ├── Có idle connection? → mượn ngay
    ├── Chưa đủ maxPoolSize? → tạo connection mới
    └── Pool đầy? → chờ đến connectionTimeout
                         └── Hết hạn → SQLException/timeout

Sử dụng query/transaction
    ↓
connection.close()  # Trong JDBC pool: TRẢ VỀ POOL, thường không đóng socket
    ↓
Connection sẵn sàng được mượn lại
~~~

**Không tạo pool mới cho mỗi HTTP request.** Tạo pool theo vòng đời process/container (thường singleton qua DI/Spring Boot), dùng `try-with-resources` cho `Connection`, `PreparedStatement` và `ResultSet`. Pool không tự khắc phục SQL query chậm, transaction giữ lock lâu hoặc hết DB memory.

## 2. Ba lớp giới hạn phải tính riêng

~~~mermaid
flowchart TD
    RUN["Cloud Run/GKE\nN instances × P pool size"] --> A["Tổng client connections khả dĩ"]
    A --> R{"Có managed pooler?"}
    R -- "Không" --> DB["DB server sessions\nmax_connections"]
    R -- "Có" --> MP["Pooler client connections\nmax_client_connections"]
    MP --> S["Pooler server connections\npool_mode + max_pool_size"]
    S --> DB
    O["Other apps, replicas,\nadmin, maintenance"] --> DB
~~~

### 2.1. Budget cho database không dùng server-side pooler

Ước lượng mức trần từ một ứng dụng:

\[
C_{\text{app,max}} \approx \sum_{r=1}^{R} N_r \times P_r + C_{\text{jobs}} + C_{\text{other-processes}}
\]

Trong đó:

- `R`: số revisions/deployments còn sống đồng thời (bao gồm canary/rollback window).
- `N_r`: số instances hoặc Pods tối đa của revision `r`.
- `P_r`: giới hạn connections của **mỗi process/pool**.
- `C_jobs`: kết nối do background workers, migration jobs, batch, connection pools khác tạo.
- Tổng này là **ngưỡng kịch bản**, không phải số luôn đạt hoặc cam kết autoscaler sẽ không vượt giới hạn trong mọi tình huống.

Phần dành cho ứng dụng phải nhỏ hơn ngân sách database:

\[
B_{\text{app}} = C_{\text{DB usable}} - C_{\text{other services}} - C_{\text{headroom}}
\]

**Không lấy toàn bộ `max_connections` làm ngân sách cho service.** Cần dự phòng kết nối quản trị, replication, maintenance, các ứng dụng khác và tình huống failover/scale-out. Khi thay `max_connections`, xét bộ nhớ và giới hạn cấu hình engine/tier; tăng số lên cao không tự tạo CPU/RAM.

### 2.2. Ví dụ tính ngược

Giả sử `max_connections=400`; sau đánh giá hoạt động và dự phòng, đội DBA chỉ cấp **240 kết nối** cho orders-api. Chọn:

| Thành phần | Giá trị giả định |
| --- | ---: |
| Cloud Run revision mới tối đa | 16 instances |
| Revision cũ có thể còn phục vụ trong rollout | 8 instances |
| Tổng instances đưa vào thiết kế | 24 |
| HikariCP maximumPoolSize | 8 |
| Nhu cầu tối đa theo cấu hình | 24 × 8 = **192** |
| Headroom trong budget ứng dụng | 240 − 192 = **48** |

Tăng pool từ 8 lên 15 mà không đổi số instances tạo trần **360**, vượt ngân sách 240. Nếu muốn cho nhiều requests chạy đồng thời, nên đo **thời gian DB connection bị giữ** rồi cân nhắc concurrency, instance limit, query efficiency hoặc server-side pooling.

**Luật khởi đầu:** Thiết kế theo peak instances **của tất cả revisions/Jobs/consumers**, không chỉ số instances nhìn thấy lúc bình thường.

### 2.3. Tương quan RPS và nhu cầu active connections

Ước lượng theo Little's Law ở trạng thái ổn định:

\[
C_{\text{active,average}} \approx \text{DB transactions/s} \times \text{average connection hold time (s)}
\]

Nếu 200 transactions/s và mỗi transaction giữ connection trung bình 40 ms, mức sử dụng đồng thời trung bình khoảng **8 connections** (200 × 0,04). Đây **không phải** pool size bắt buộc: peak bursts, p95/p99 query time, locks, transaction queuing và cache miss có thể đẩy nhu cầu cao hơn. Tính cùng dashboard/đo tải thực tế, rồi chọn budget có margin.

## 3. Giới hạn Cloud SQL PostgreSQL và Cloud Run

### 3.1. PostgreSQL `max_connections`

Lệnh SQL **chỉ đọc** với một user được phép kết nối:

~~~sql
SHOW max_connections;

SELECT name, setting, unit, source
FROM pg_settings
WHERE name IN ('max_connections', 'superuser_reserved_connections',
               'reserved_connections');

SELECT current_setting('max_connections')::int AS configured_limit,
       count(*) AS visible_sessions
FROM pg_stat_activity;
~~~

`reserved_connections` có thể không có ở các phiên bản PostgreSQL cũ; nếu query `pg_settings` không hiển thị nó, không coi đó là lỗi. `pg_stat_activity` có thể ẩn thông tin chi tiết của sessions khác theo quyền, dù đếm sessions vẫn hữu ích. So sánh với Metrics Explorer/Database Insights.

Cloud SQL tự chọn giá trị mặc định theo machine configuration và bộ nhớ của edition/instance. Với PostgreSQL, có thể điều chỉnh flag `max_connections` **trong giới hạn supported settings và DB memory**; thay flag có thể cần restart. Không sao chép giá trị của máy 32 GiB RAM sang instance nhỏ.

### 3.2. Phạm vi giới hạn Cloud Run 100 connections/instance

Tài liệu Cloud SQL nói rõ: **Cloud Run built-in Cloud SQL connection** có giới hạn **100 connections tới mỗi Cloud SQL database trên mỗi container instance**. Giới hạn này **không áp dụng giống hệt** cho:

- Cloud SQL **Language Connectors**.
- Cloud SQL Auth Proxy **sidecar**.
- Kết nối **TCP trực tiếp tới instance IP**.

Nhưng mọi phương thức vẫn tiêu thụ **các connections của database** và chịu `max_connections`. Con số 100 **không phải cấu hình mặc định của HikariCP** và không phải giới hạn toàn bộ deployment. Ví dụ 30 instances dùng built-in integration với 20 connections/instance có thể cần tới khoảng 600 database connections, nếu không có server-side pooling.

### 3.3. App Engine, GKE và workers

| Nơi chạy | Nguồn tạo nhiều connections | Cần tính |
| --- | --- | --- |
| Cloud Run services | Autoscaling và nhiều revisions cùng nhận traffic | Instances × pools, concurrency, max instances |
| Cloud Run jobs | Parallel tasks / retry job executions | Tasks × pools + app services |
| GKE | ReplicaSet/HPA, nhiều JVMs trong mỗi Pod, rolling deploy | Replicas (bao gồm surge) × pools |
| Compute Engine | Số VMs/processes và sidecar workers | Instances × processes × pools |
| App Engine Standard | Autoscaling và quota platform | Connections/instance + service scaling |

Cùng một database có thể được **nhiều loại workloads** sử dụng. Dashboard theo từng service giúp nhận diện nguồn connections tăng đột biến.

## 4. Pool trong ứng dụng: Java HikariCP

Ví dụ giả sử bạn có JDBC driver PostgreSQL, HikariCP và endpoint database đã được cấu hình **đúng network/TLS/IAM**. Với Cloud SQL hoặc AlloyDB, đường kết nối có thể qua **Auth Proxy, connector hoặc private IP**; các lựa chọn đó **không đồng nghĩa** với pool.

### 4.1. Tạo datasource dùng lại

~~~java
import com.zaxxer.hikari.HikariConfig;
import com.zaxxer.hikari.HikariDataSource;

public final class DataSourceFactory {
    private DataSourceFactory() {}

    public static HikariDataSource create() {
        var cfg = new HikariConfig();

        // URL được cấp qua cấu hình an toàn:
        // jdbc:postgresql://DB_HOST:DB_PORT/orders
        // Cần TLS/trust + DNS/hostname phù hợp với phương thức kết nối.
        cfg.setJdbcUrl(System.getenv("DB_JDBC_URL"));
        cfg.setUsername(System.getenv("DB_USER"));
        cfg.setPassword(System.getenv("DB_PASSWORD"));

        cfg.setPoolName("orders-pool");
        cfg.setMaximumPoolSize(5);
        cfg.setMinimumIdle(0);
        cfg.setConnectionTimeout(10_000);  // Chờ mượn connection <= 10 s
        cfg.setValidationTimeout(5_000);
        cfg.setIdleTimeout(600_000);       // Chỉ có tác dụng nếu còn idle dư
        cfg.setMaxLifetime(1_800_000);     // Giữ thấp hơn timeout backend phù hợp

        return new HikariDataSource(cfg);
    }
}
~~~

**Đây là cấu hình mẫu**, không phải một chuỗi JDBC production đã hoàn thiện. Ứng dụng phải đặt `DB_JDBC_URL` theo kết nối thật, xác minh TLS/server identity hoặc dùng Auth Proxy/Language Connector được hỗ trợ, và lấy `DB_PASSWORD` từ Secret Manager/credential provider. Không đặt password trong source code hoặc logs.

**Giải thích thông số:**

| HikariCP | Ý nghĩa | Lưu ý |
| --- | --- | --- |
| `maximumPoolSize` | Số connections tối đa mỗi pool | Ước lượng DB budget trước |
| `minimumIdle` | Số idle tối thiểu duy trì | `0` có thể phù hợp serverless; phải thử load |
| `connectionTimeout` | Thời gian thread đợi **borrow từ pool** | Khác TCP connect timeout và SQL query timeout |
| `validationTimeout` | Thời gian kiểm tra connection còn hợp lệ | Không được lớn hơn connectionTimeout |
| `idleTimeout` | Thời gian connection dư có thể idle trước khi bị dọn | Không đảm bảo dọn chính xác từng mili giây |
| `maxLifetime` | Vòng đời tối đa một connection; bị retire khi thích hợp | Đặt ngắn hơn server/proxy lifetime để tránh stale |
| `leakDetectionThreshold` | Báo connection bị giữ quá lâu | Dùng để điều tra, không tự đóng leak |

**Không chỉ dựa vào `maxLifetime` để giới hạn query runtime.** Thiết lập statement/query timeout riêng, theo workload và PostgreSQL `statement_timeout`/`lock_timeout` khi thích hợp.

### 4.2. Borrow, trả về pool và đóng đúng lúc

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import javax.sql.DataSource;

public class OrderHealthQuery {
    private final DataSource dataSource; // Một singleton pool dùng chung

    public OrderHealthQuery(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public boolean ping() throws SQLException {
        try (Connection connection = dataSource.getConnection();
             PreparedStatement sql = connection.prepareStatement("SELECT 1");
             ResultSet rs = sql.executeQuery()) {
            return rs.next() && rs.getInt(1) == 1;
        }
    }
}
~~~

Với `try-with-resources`, HikariCP nhận lại connection khi `close()` được gọi. Trong Spring Boot, cấu hình pool thường do framework tạo và quản lý **một lần cho application context**, tránh tạo lại datasource ở mỗi request. Đóng HikariDataSource khi process shutdown, không đóng toàn pool ở cuối từng request.

### 4.3. Phân biệt timeout khi điều tra

~~~text
HTTP request deadline
  ├── Pool borrow: Hikari connectionTimeout
  ├── Establish new JDBC/TCP/Cloud SQL Connector connection timeout
  ├── Execute SQL: statement_timeout / query timeout
  ├── Acquire database lock: lock_timeout
  └── Commit/response network timeout
~~~

HikariCP `connectionTimeout=10s` chỉ giới hạn thời gian **chờ connection khả dụng trong pool**. Một truy vấn trên connection đã mượn vẫn có thể chạy lâu hơn nếu không có SQL timeout. Chọn deadline theo SLO để tổng thời gian chờ/retries không vượt thời gian request của Cloud Run/API Gateway.

## 5. Điều chỉnh cho Cloud Run và GKE

### 5.1. Cloud Run autoscaling

Khi request tăng, Cloud Run có thể thêm instances. Mỗi JVM instance thường có pool riêng: **pool 5 × 30 instances = 150 connections** ở mức trần. Trong rollout, revision cũ và mới có thể chạy đồng thời, nên tính cả hai.

- `--concurrency` kiểm soát số HTTP requests có thể vào **một container instance**, **không** trực tiếp giới hạn DB sessions.
- `--max-instances` giới hạn scale-out theo cấu hình tương ứng; xem hiệu lực ở **service vs revision level** của cấu hình đang chạy.
- `--min-instances` giữ warm capacity nhưng cũng có thể giữ idle database connections.
- Pool minIdle thấp giảm lượng idle sessions; pool quá nhỏ tạo backlog khi traffic thực sự cần DB.
- Nếu database đã bão hòa, tăng max instances hoặc max pool size có thể làm tình hình tệ hơn.

Các lệnh chỉ đọc:

~~~bash
gcloud run services describe orders-api \
  --region=asia-southeast1 \
  --project=LAB_PROJECT_ID

gcloud sql instances describe orders-db \
  --project=LAB_PROJECT_ID
~~~

Ví dụ thay đổi thử nghiệm khi được duyệt:

~~~bash
# TẠO REVISION / ĐỔI autoscaling; không chạy trên production tùy tiện
gcloud run services update orders-api \
  --region=asia-southeast1 \
  --project=LAB_PROJECT_ID \
  --concurrency=20 \
  --max-instances=12
~~~

**Bẫy serverless:** Với request-based billing, CPU của Cloud Run có thể bị hạn chế khi instance idle; background threads của pool không được chạy đều. Khi request mới đến, idle connection đã bị DB/proxy đóng có thể gây lỗi lần đầu. Dùng validation/reconnect, `minimumIdle` phù hợp, lazy connector refresh khi dùng Cloud SQL Java Connector; chỉ cân nhắc **instance-based billing** nếu workload cần bảo trì background pool liên tục, vì có tác động chi phí.

### 5.2. GKE rolling update và HPA

Giả sử Deployment có `replicas=10`, `maxSurge=3`, HikariCP `maximumPoolSize=10`. Trong rollout có thể xuất hiện **13 Pods**, tương ứng **130** DB sessions từ workload này dù baseline là 100. HPA còn có thể tăng replica count trong cùng cửa sổ.

Khi lập budget, tính:

~~~text
Max DB connections ≈
  (replicas chính + Pods surge) × JVMs/Pod × pools/JVM
  + job/consumer connections
  + các ứng dụng khác
~~~

Giảm `maxSurge` có thể giảm peak connections nhưng cũng làm rollout chậm hơn; chọn theo availability/SLO. Với GKE, kiểm tra connection pool metrics theo Pod và deployment, đừng chỉ xem `kubectl get pods`.

## 6. Cloud SQL Auth Proxy không phải connection pool

**Cloud SQL Auth Proxy** cung cấp IAM-backed authorized encrypted connectivity tới Cloud SQL instance; **không tự gộp nhiều PostgreSQL sessions thành ít server connections**. Nếu mở 100 JDBC connections qua Auth Proxy thông thường, database vẫn có thể cần khoảng 100 sessions. Có thể **kết hợp** Auth Proxy với HikariCP hoặc Managed Connection Pooling được hỗ trợ.

| Công cụ | Chức năng chính | Có tự multiplex nhiều DB clients? |
| --- | --- | --- |
| Cloud SQL Auth Proxy | Xác thực/kênh mã hóa và quản lý kết nối | **Không**, nếu chỉ dùng Proxy |
| Cloud SQL Java Connector | Xác thực IAM, TLS và address selection | **Không** phải pool mặc định |
| HikariCP | Tái sử dụng connections **bên trong JVM** | Giới hạn clients mỗi JVM, không chia sẻ giữa instances |
| PgBouncer tự quản lý | Pooler server-side, thường transaction/session | **Có**, tùy pool mode |
| Cloud SQL PostgreSQL **Managed Connection Pooling** | Managed poolers dùng nhiều server sessions chung | **Có**, với điều kiện hỗ trợ |
| AlloyDB **Managed Connection Pooling** | Managed poolers của AlloyDB instance | **Có**, với điều kiện hỗ trợ |

**Mạng, IAM và DB authentication là các lớp riêng:** PostgreSQL direct TCP tới private IP có yêu cầu networking/TLS/auth; Auth Proxy/Language Connector có thêm IAM permissions (như `roles/cloudsql.client` cho Cloud SQL); nhưng PostgreSQL `CONNECT`, schema/table privileges và credential/ IAM DB auth vẫn phải được thiết lập. `roles/cloudsql.client` không tự cấp `SELECT/INSERT` trên bảng.

## 7. Cloud SQL for PostgreSQL Managed Connection Pooling

**Cloud SQL Managed Connection Pooling (MCP)** là pooler server-side do Google quản lý. Khác pool trong JVM, nhiều client connections có thể **dùng chung một số lượng server connections giới hạn** theo user/database pair và chế độ transaction/session. Tính năng này dành cho **Cloud SQL for PostgreSQL Enterprise Plus**, **không** phải mặc định trên mọi Cloud SQL instance.

### 7.1. Những điều kiện bắt buộc

Theo tài liệu hiện hành, trước khi bật MCP phải kiểm tra:

- **Edition:** Cloud SQL **Enterprise Plus** cho PostgreSQL.
- **Network architecture:** instance dùng **new Cloud SQL network architecture** và kết nối qua private services access, public IP hoặc Private Service Connect theo điều kiện hỗ trợ.
- **Maintenance version:** ít nhất `POSTGRES_$version.R20250727.00_14` (thay `$version` bằng major version thực); không chỉ nhìn số PostgreSQL major.
- **Client connectivity:** MCP được hỗ trợ với **direct connection** hoặc **Cloud SQL Auth Proxy** (Proxy v**2.15.2+**). Không mặc nhiên coi mọi Language Connector có thể sử dụng MCP như một đường tương đương.
- **Quyền quản trị:** người cập nhật instance phải có quyền Cloud SQL phù hợp; app user chỉ cần quyền connection/database theo phương thức chọn.
- **Thay đổi instance đang chạy:** bật MCP trên instance hiện có **gây database restart**; cần maintenance window, HA/failover plan và test reconnect.

**Không bật MCP bằng một lệnh patch trực tiếp trên production vì nghĩ đây là tính năng “zero downtime”.** Đặc biệt phải xem lại network architecture và maintenance version.

### 7.2. Cổng kết nối và cách chọn

| Trường hợp | Cổng | Ý nghĩa |
| --- | --- | --- |
| Direct PostgreSQL | TCP `5432` | Kết nối trực tiếp database server, **không qua MCP** |
| Direct Managed Connection Pooling | TCP `6432` | Kết nối tới MCP pooler qua đường mạng hỗ trợ |
| Cloud SQL Auth Proxy tới MCP | Đích phía Cloud SQL dùng TCP `3307` | Auth Proxy chọn endpoint MCP theo cấu hình Proxy; **port local** cho app có thể khác |
| Cloud SQL Auth Proxy thường | Đích Proxy của Cloud SQL cũng sử dụng `3307` | Không mặc nhiên được MCP nếu chưa bật/chọn endpoint |

**Không sửa JDBC URL từ 5432 sang 3307 khi app đang nói chuyện với local Auth Proxy.** `3307` ở đây là **cổng dịch vụ phía Cloud SQL mà Proxy sử dụng**. Để đi MCP qua Auth Proxy, dùng cờ/phiên bản hỗ trợ theo tài liệu và kết nối app tới **local listener** được cấu hình.

### 7.3. Số poolers và pool size là hai tầng

Cloud SQL tính số **connection poolers** xấp xỉ **1 pooler cho mỗi 4 vCPU**, tối thiểu một. Mỗi pooler quản lý **một pool riêng cho từng cặp database và user**.

Ví dụ instance 8 vCPU có 2 poolers. Nếu cấu hình `max_pool_size=50` thì **một cặp user/database** có thể được cấp tới 50 server connections **trên mỗi pooler**, tổng mức lý thuyết tới **100** cho cặp đó, **không phải 50 cho toàn instance**. Nếu có nhiều database users, tổng server sessions có thể lớn hơn nữa. Cuối cùng, PostgreSQL `max_connections` vẫn là trần bảo vệ.

Thông số mặc định quan trọng:

| Cấu hình MCP | Mặc định trong tài liệu | Phạm vi |
| --- | ---: | --- |
| `pool_mode` | `transaction` | Mức giữ server connection |
| `max_pool_size` | 50 | **Mỗi user/database/pooler** |
| `min_pool_size` | 0 | Mỗi pool |
| `max_client_connections` | 5.000 | **Mỗi pooler** |
| `query_wait_timeout` | 120 s | Thời gian client đợi server connection |
| `max_prepared_statements` | 0 | Hỗ trợ protocol named prepared statements khi cấu hình |

**5.000 client connections không đồng nghĩa database có thể chạy 5.000 transactions đồng thời.** Khi server pool đầy, clients **chờ**; latency tăng và có thể timeout. Pooler giúp giảm overhead kết nối, không biến database thành tài nguyên vô hạn.

### 7.4. Kiểm tra và bật bằng gcloud

~~~bash
# CHỈ ĐỌC: thay instance/project thật trước khi chạy
gcloud sql instances describe orders-db \
  --project=LAB_PROJECT_ID \
  --format="yaml(name,region,databaseVersion,settings.edition,settings.tier,settings.connectionPoolConfig)"

# CHỈ ĐỌC: xem MCP đang bật không
gcloud sql instances describe orders-db \
  --project=LAB_PROJECT_ID \
  --format="value(settings.connectionPoolConfig.connectionPoolingEnabled)"
~~~

Khi mọi prerequisites đã được xác minh trong **project lab**, người quản trị có thể bật:

~~~bash
# THAY ĐỔI INSTANCE và CÓ DATABASE RESTART:
# chỉ dùng với Cloud SQL PostgreSQL Enterprise Plus đủ điều kiện.
gcloud sql instances patch orders-db \
  --project=LAB_PROJECT_ID \
  --enable-connection-pooling
~~~

Ví dụ đổi cài đặt **sau khi đã bật**:

~~~bash
# THAY ĐỔI cấu hình pool, phải kiểm tra tải và bảo trì
gcloud sql instances patch orders-db \
  --project=LAB_PROJECT_ID \
  --connection-pool-flags=pool_mode=transaction,max_pool_size=30
~~~

Các flags được truyền **theo phiên bản gcloud được hỗ trợ** (hướng dẫn yêu cầu gcloud 515.0.0+). Không chạy với giá trị pool tùy ý trên production trước khi xem số poolers, database users, `max_connections` và tác động tới phiên kết nối.

## 8. AlloyDB Managed Connection Pooling

**AlloyDB for PostgreSQL** cũng có **Managed Connection Pooling**, dùng chung ý tưởng multiplex client connections sang một pool server connections; hỗ trợ **primary** và **read pool instances**. Tính năng **tắt theo mặc định** và có cấu hình độc lập trên từng AlloyDB instance.

### 8.1. Bật và kiểm tra

~~~bash
# CHỈ ĐỌC
gcloud alloydb instances describe primary-instance \
  --project=LAB_PROJECT_ID \
  --region=asia-southeast1 \
  --cluster=orders-cluster \
  --format="value(connectionPoolConfig.enabled)"
~~~

~~~bash
# CÓ THAY ĐỔI instance: chỉ thực hiện trong lab được phép
gcloud alloydb instances update primary-instance \
  --project=LAB_PROJECT_ID \
  --region=asia-southeast1 \
  --cluster=orders-cluster \
  --enable-connection-pooling
~~~

**Cần chuẩn bị change window:** Với AlloyDB instances tạo **trước tháng 11/2024**, bật MCP có thể cần cập nhật network một lần, gây gián đoạn VPC connection ngắn (tài liệu nêu thường dưới 15 giây); không hứa áp dụng chung cho mọi instance hoặc rằng mọi in-flight transaction sẽ sống sót.

### 8.2. Kết nối tới pooler trên cổng 6432

- Direct PostgreSQL trên AlloyDB thường là **5432**.
- MCP sử dụng **TCP 6432** trên private/PSC endpoint được hỗ trợ.
- Managed pooler **không hỗ trợ public IP connections**.
- Có thể dùng **AlloyDB Auth Proxy hoặc AlloyDB Language Connectors** theo tài liệu hỗ trợ; Auth Proxy pooler có nhóm kết nối riêng với direct pooler.
- DB credentials/IAM DB auth và SSL/mTLS phải cấu hình theo đúng loại kết nối. Không coi có private IP tức là mọi chứng chỉ đã được xác minh.

Ví dụ **chỉ để minh họa đường kết nối**, không nhúng mật khẩu vào command line:

~~~bash
# Chạy từ máy trong VPC có network/TLS/auth phù hợp.
# DB_HOST là DNS/private IP hợp lệ, có thể cần sslmode/cert theo policy.
psql "host=DB_HOST port=6432 dbname=orders user=orders_app sslmode=require"
~~~

**Không sử dụng literal `DB_HOST` làm địa chỉ thật**. Với AlloyDB direct connections, lựa chọn TLS/verification và khả năng certificate validation khác với kết nối qua Auth Proxy/Language Connector; xác thực đúng theo kiến trúc đã chọn.

### 8.3. Tùy chỉnh transaction/session mode

~~~bash
# CÓ THAY ĐỔI pooler config trong lab; kiểm tra phiên bản và IAM
gcloud alloydb instances update primary-instance \
  --project=LAB_PROJECT_ID \
  --region=asia-southeast1 \
  --cluster=orders-cluster \
  --connection-pooling-pool-mode=transaction \
  --connection-pooling-max-pool-size=30 \
  --connection-pooling-max-client-connections=1000
~~~

`max_pool_size` là giới hạn server connections theo cặp user/database ở phạm vi pooler; `max_client_connections` giới hạn số clients, **không** phải database `max_connections`. Cần đo `waiting clients` và query wait time sau thay đổi, không tự tối ưu bằng cách tăng vô hạn.

### 8.4. AlloyDB stats console và metrics

AlloyDB cung cấp pooler metrics:

| Metrics Explorer | Ý nghĩa |
| --- | --- |
| `/database/conn_pool/client_connections` | Client connections theo active/waiting |
| `/database/conn_pool/server_connections` | Server connections theo active/idle |
| `/database/conn_pool/client_connections_avg_wait_time` | Thời gian client đợi server connection |
| `/database/conn_pool/num_pools` | Số pools theo database |

Khi được cấp quyền riêng, người vận hành có thể kết nối **stats console** qua private endpoint và chạy các lệnh PgBouncer-compatible `SHOW POOLS;`, `SHOW CLIENTS;`, `SHOW STATS;`. Tên database stats có dạng `alloydb_mcp_stats_1` cho pooler thông thường; phải allowlist stats users trước. **Không cấp quyền xem thông tin kết nối và credentials rộng** để chỉ phục vụ một ứng dụng bình thường.

## 9. Transaction pooling so với session pooling

Đây là quyết định **tương thích ứng dụng**, không chỉ lựa chọn hiệu năng.

~~~mermaid
flowchart LR
  A["Client A\nPooler"] --> P["Transaction pool"]
  B["Client B\nPooler"] --> P
  P -->|"Tx A: server #1\nCOMMIT → trả server"| S1["PostgreSQL server #1"]
  P -->|"Tx B: dùng lại server #1"| S1
  P2["Session pool"] -->|"Client C giữ server #2\nsuốt phiên"| S2["PostgreSQL server #2"]
~~~

| Tiêu chí | **Transaction mode** | **Session mode** |
| --- | --- | --- |
| Thời gian giữ backend connection | Trong **một transaction**; trả về pool sau commit/rollback | Trong **toàn session** đến khi client disconnect |
| Hiệu quả chia sẻ | Cao với transactions ngắn | Thấp hơn khi clients giữ session lâu |
| Session state | **Không thể giả định giữ được** qua nhiều transactions | Giữ session state trên server connection được cấp |
| Phù hợp | REST APIs stateless, giao dịch ngắn | Ứng dụng phụ thuộc session state/protocol features |
| Khi pool hết server connections | Clients chờ/timeout | Clients khác chờ đến khi session nhả connection |

### 9.1. Các tính năng dễ không tương thích transaction mode

Theo hạn chế của Cloud SQL và AlloyDB MCP transaction mode, cần kiểm tra:

- `SET/RESET` với trạng thái session kéo dài qua transactions.
- `LISTEN/NOTIFY` phía listener giữ session dài hạn.
- Session-level advisory locks (`pg_advisory_lock`).
- Temporary tables có `ON COMMIT PRESERVE ROWS` hoặc kiểu session-scoped.
- `WITH HOLD` cursors.
- SQL-level `PREPARE/DEALLOCATE` và prepared statements phụ thuộc session.
- **Protocol-level named prepared statements** ở mặc định; một số cấu hình có `max_prepared_statements` khác 0 để hỗ trợ nhưng phải test driver/pooler.

**Ví dụ lỗi:** Một Hibernate/PostgreSQL JDBC driver dùng server-side prepared statement cache giữa các transactions. Nếu server connection bị đổi sau mỗi transaction, named prepared statement có thể không tồn tại trên server mới hoặc xảy ra xung đột tên. Kiểm thử driver `prepareThreshold` và khả năng MCP `max_prepared_statements`; đừng vội tắt toàn bộ prepared statements khi chưa đo hiệu năng và đọc tài liệu phiên bản.

**Chọn session mode** nếu ứng dụng bắt buộc giữ session state, nhưng hiểu rằng khi đó số client sessions thường gần số server connections; server-side multiplexing kém hiệu quả hơn. Nếu app cần `LISTEN` hoặc migration tool, có thể dùng **đường direct 5432 riêng** cho component đó, còn API giao dịch ngắn qua transaction pooler 6432.

### 9.2. Pooler và HikariCP có thể dùng chung không?

**Có.** HikariCP giới hạn mỗi JVM mở bao nhiêu client connections tới pooler; pooler quản lý nhiều client sessions tới một tập server connections. Tuy nhiên **hai tầng hàng chờ** có thể tăng tail latency:

1. Request chờ mượn HikariCP connection.
2. Client connection đã tới MCP nhưng chờ server connection rảnh.

Vì vậy cần theo dõi **Hikari pending/wait time** và **MCP waiting/query wait time**, không chỉ xem tổng connections. Với workload giao dịch ngắn, có thể giảm pool size trong JVM, dùng transaction pooling và scale ứng dụng trong giới hạn backend. Luôn kiểm tra tương thích SQL trước.

## 10. Lựa chọn giải pháp pooling theo hệ thống

| Tình huống | Gợi ý | Cần tránh |
| --- | --- | --- |
| Cloud SQL PostgreSQL Enterprise (không phải Plus) | HikariCP/driver pool; cân nhắc PgBouncer tự vận hành khi cần | Giả định đã có Google-managed MCP |
| Cloud SQL PostgreSQL Enterprise Plus đủ điều kiện | HikariCP + **Cloud SQL MCP** khi benefit rõ | Bật MCP mà không dự tính restart/transaction compatibility |
| AlloyDB read/write với spike clients | HikariCP + **AlloyDB MCP** | Kết nối 6432 từ public IP không hỗ trợ |
| Ứng dụng dựa session state dài | HikariCP hoặc **session mode**/direct 5432 | Transaction mode chưa được thử |
| Java GKE hàng trăm Pods | Sizing pooled connections × replicas/surge; MCP nếu hỗ trợ | Chỉ tăng database max_connections |
| Cloud Run nhiều instances, traffic dao động | Giới hạn pool/instance, max instances, idle validation, cân nhắc MCP | Tạo connection/pool mới mỗi HTTP request |
| PostgreSQL admin/migrations/replication | Connection **direct** theo policy | Dùng transaction pooler cho `REPLICATION`, DDL/migration có session state |
| Cloud SQL MySQL/SQL Server | Đọc mô hình riêng của engine | Sao chép cơ chế PostgreSQL process/multiplexing |

**Phân biệt Cloud SQL MySQL Managed Connection Pooling:** trên MySQL cơ chế mới là **thread pooling**, vẫn có client session riêng và vẫn tính vào `max_connections`; không được suy từ bài PostgreSQL rằng MySQL tự giảm số server sessions như một PgBouncer.

## 11. Quan sát kết nối và tìm điểm nghẽn

### 11.1. SQL an toàn cho Cloud SQL PostgreSQL/AlloyDB

Chạy bằng DB user **có quyền xem thống kê phù hợp**, tránh xuất toàn bộ query text của người dùng vào ticket/log:

~~~sql
-- Giới hạn cấu hình:
SHOW max_connections;

-- Số session theo trạng thái và người dùng (aggregate):
SELECT datname, usename, COALESCE(state, 'unknown') AS state,
       count(*) AS sessions
FROM pg_stat_activity
GROUP BY datname, usename, state
ORDER BY sessions DESC;

-- Số connections và số sessions đang hoạt động:
SELECT
    count(*) AS all_sessions,
    count(*) FILTER (WHERE state = 'active') AS active_sessions,
    count(*) FILTER (WHERE state = 'idle') AS idle_sessions,
    count(*) FILTER (WHERE state = 'idle in transaction') AS idle_in_transaction
FROM pg_stat_activity;
~~~

**Đếm server sessions không bằng đếm MCP clients.** Với transaction pooler, hàng trăm hoặc hàng nghìn client connections có thể đứng trước ít backend connections. Cần xem **pooler metrics** thay vì chỉ `pg_stat_activity` để biết số clients chờ. `idle in transaction` cao có thể báo code giữ transaction/lock quá lâu.

### 11.2. Metrics cần so theo cùng thời gian

| Tầng | Tín hiệu | Ý nghĩa |
| --- | --- | --- |
| Cloud Run/GKE | Instance/Pod count, concurrent HTTP, restart, p95 | Ứng dụng scale ra sao |
| HikariCP | `active`, `idle`, `pending`, `total`, borrow time | Chờ trong JVM |
| Cloud SQL/AlloyDB | Server connections, CPU, memory, active transactions | Database saturation |
| MCP | Client waiting, active/idle server connections, wait time | Bị nghẽn tại pooler? |
| Query | Lock wait, slow query/p95, query execution time | Pool chỉ bị giữ lâu vì SQL chậm? |
| Network | Connection errors, TLS failures, latency | Không phải lúc nào cũng do pool |
| Product | DB failover/restart, maintenance, max connections errors | Phân biệt transient với cấu hình sai |

**Câu hỏi bắt đầu:** Tăng 5xx là vì **không lấy được connection từ HikariCP**, hay đã lấy được nhưng **MCP chờ server**, hay đang **thực thi SQL chậm**? Ba nguyên nhân có cách sửa khác nhau.

### 11.3. Alert gợi ý

- Hikari `pending > 0` kéo dài, borrow p95 cao gần `connectionTimeout`.
- Database connections tăng gần budget được duyệt, hoặc xuất hiện `too many connections`.
- MCP waiting clients/query wait time tăng trong khi server pool đang bão hòa.
- `idle in transaction` tăng hoặc transactions quá dài.
- DB CPU, lock wait, IOPS tăng mà app pool vẫn rảnh: cần tối ưu SQL, không tăng connections.
- Cloud Run instances/revision overlap làm tổng pool capacity vượt dự báo.
- Lỗi reconnect sau failover, maintenance hoặc Secret Manager/password rotation.

Metrics nguồn có tên và khả năng phân loại khác nhau theo phiên bản; dùng Metrics Explorer và instrumentation (Micrometer/JMX, Cloud Monitoring) để xác minh thay vì hard-code một metric không tồn tại.

## 12. Runbook khi connection pool bão hòa

~~~mermaid
flowchart TD
  FAIL["HTTP 5xx / DB timeout"] --> GET{"Mượn connection từ HikariCP được?"}
  GET -- "Không" --> H["Pending, leak, pool size,\ntransaction hold time"]
  GET -- "Có" --> MCP{"Có managed pooler không?"}
  MCP -- "Có" --> WAIT{"Pooler waiting tăng?"}
  WAIT -- "Có" --> P["Kiểm tra max_pool_size,\nquery wait, server saturation"]
  WAIT -- "Không" --> SQL["SQL/lock/network/DB failover"]
  MCP -- "Không" --> LIMIT{"Gần max_connections?"}
  LIMIT -- "Có" --> S["Budget apps × instances,\nidle sessions, other consumers"]
  LIMIT -- "Không" --> SQL
  H --> LOAD["Đối chiếu metrics, logs và load test"]
  P --> LOAD
  S --> LOAD
  SQL --> LOAD
~~~

### 12.1. Thứ tự xử lý, không “tăng số cho đến khi hết lỗi”

1. **Xác nhận phạm vi:** Cloud SQL hay AlloyDB; primary hay read pool; endpoint **5432/6432**, direct/Auth Proxy hay Language Connector; project và region nào.
2. **Phân loại timeout:** Hikari borrow timeout, TCP connect timeout, pooler query wait timeout hay SQL `statement_timeout`.
3. **Đếm nguồn:** Cloud Run revisions, Cloud Run jobs, GKE replicas, migration/cron và các services khác.
4. **Kiểm tra DB:** `max_connections`, active/idle sessions, CPU/memory, long transactions, locks và slow queries.
5. **Kiểm tra pooler nếu có:** clients waiting, server connections active/idle, `pool_mode`, `max_pool_size`, limits theo từng user/database.
6. **Ưu tiên giảm thời gian giữ connection:** đóng JDBC resources, tối ưu truy vấn, giữ transaction ngắn, tránh gọi dịch vụ HTTP bên ngoài khi đang mở transaction.
7. **Áp dụng backpressure:** giới hạn max instances/Pod replicas, queue concurrency, bounded wait và 429/503 theo hợp đồng thay vì tạo vô hạn DB sessions.
8. **Chỉ khi có bằng chứng mới tăng pool/capacity:** bảo đảm DB CPU/RAM/IOPS và `max_connections` còn headroom.
9. **Canary thay đổi:** cập nhật một revision/môi trường thử, theo dõi p95, error budget, connection count; rollback khi xấu đi.

### 12.2. Retry và failover

Trong HA failover hoặc maintenance, những connections hiện có có thể bị cắt. App nên phát hiện connection lỗi, loại connection đó khỏi pool, thiết lập lại và **retry có giới hạn** với exponential backoff + jitter. Nếu lỗi xảy ra **giữa một transaction**, transaction có thể đã commit hoặc chưa; chỉ retry từ đầu khi operation có **idempotency key**/kiểm tra trạng thái để tránh ghi hai lần.

**Không tăng Hikari minimumIdle lên giá trị lớn trên hàng trăm instances** với kỳ vọng HA tốt hơn. Hàng trăm idle sessions có thể làm primary cạn tài nguyên ngay khi bắt đầu hồi phục.

### 12.3. Quản trị thay đổi có rủi ro

| Thay đổi | Tác động cần chuẩn bị |
| --- | --- |
| Tăng `maximumPoolSize` của ứng dụng | Mỗi instance có thể mở thêm sessions; tổng tăng theo autoscaling |
| Tăng Cloud Run max instances | Nhiều JVM pools hơn, DB connections tăng |
| Tăng PostgreSQL `max_connections` | Cần RAM, kiểm tra restart và giới hạn Cloud SQL/AlloyDB |
| Bật Cloud SQL MCP trên existing instance | **Có restart** và thay đường app kết nối tới pooler |
| Bật AlloyDB MCP trên instance cũ | Có thể có one-time network update, gián đoạn VPC |
| Chuyển session → transaction pooling | Có thể phá session state, prepared statements, advisory locks |
| Tắt AlloyDB MCP | **Ngắt các client connections đang dùng pooler** |
| Chuyển endpoint 5432 → 6432 | Cần kiểm tra firewall/TLS/driver, số liệu và rollback |

Mỗi thay đổi phải có **change owner, thời gian quan sát, test dưới tải, rollback plan và thông báo**. Không điều chỉnh những thông số này trực tiếp trên production để thực hiện bài tập.

## 13. Ma trận lỗi thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Hướng xử lý |
| --- | --- | --- |
| `FATAL: sorry, too many clients already` | DB gần `max_connections`, thiếu slot dành cho user | Kiểm tra sessions, các clients khác và budget |
| `FATAL: remaining connection slots are reserved` | Slot được dành cho role/admin | Không dùng admin account cho app; giảm connections |
| Hikari `Connection is not available, request timed out` | Pool đầy hoặc tạo connection mới chậm | Hikari active/pending, long queries, timeouts |
| PostgreSQL `idle in transaction` nhiều | Code giữ transaction mà không commit/rollback | Đo thời gian transaction và fix vòng đời |
| MCP `waiting clients` tăng | Pool server connections bão hòa, query lâu | Tối ưu SQL, đo wait và cân nhắc max pool |
| MCP transaction mode lỗi prepared statement | Driver/session feature không tương thích | Test `max_prepared_statements` hoặc session/direct |
| `SET` thay đổi không bền qua request | Transaction pooling không giữ session state | Sửa app, dùng `SET LOCAL` trong transaction khi thích hợp |
| Đổi sang `:6432` bị connection refused | MCP chưa bật, sai network/port/firewall | Xem instance MCP status và routing |
| Cloud SQL MCP không bật được | Không Enterprise Plus/new network/maintenance | Kiểm tra prerequisites trước mọi patch |
| AlloyDB MCP không dùng public IP | Tính năng không hỗ trợ public endpoint | Dùng private/PSC và auth theo tài liệu |
| Cloud Run vừa idle xong có stale connection | CPU throttling, server timeout, pool maintenance bị hoãn | Validation/reconnect, lazy refresh, cân nhắc billing mode |
| 100 connections/instance bị chặn | Built-in Cloud Run–Cloud SQL integration limit | Hạn chế pool; kiểm tra phương thức kết nối |
| `permission denied` trước khi tới DB | IAM/connector/auth proxy rights | Xem runtime SA, resource scope, Admin API |
| `password authentication failed` | Sai user/secret/database auth | Kiểm tra credential/rotation, không cấp Owner |
| Server `too many connections` sau rollout | Hai revisions/Pods surge cùng chạy | Tính pool capacity trong rollout, giảm surge/scale |
| CPU/IOPS DB 100% nhưng pool còn rảnh | SQL query/lock, index hoặc I/O bottleneck | Query Insights, plan/index và transaction time |
| Retry làm lỗi nhiều hơn | Retry storm, không có jitter hoặc backpressure | Bounded exponential backoff và circuit breaker |
| Dùng read pool để ghi bị lỗi | Kết nối nhầm endpoint replica/read-only | Tách write/read datasource theo use case |

**Phân biệt rõ:** Lỗi auth/network không biến mất khi tăng pool size. Nếu có vài request lỗi vì pooler/server chưa sẵn sàng sau failover, retry phải có giới hạn và không được làm transaction ghi lặp.

## 14. Case study: đặt hàng Java trên Cloud Run, đổi Cloud SQL sang AlloyDB

### 14.1. Bài toán

Một nhóm vận hành API bán hàng:

- Spring Boot Java trên Cloud Run, có canary revisions.
- PostgreSQL primary; mỗi request có 1–3 queries nhỏ, phần lớn ngắn.
- Traffic đột biến theo chiến dịch, số instances tăng mạnh.
- Team không muốn downtime vì connection exhaustion; có thể đang dùng Cloud SQL Enterprise Plus hoặc xem xét AlloyDB.

**Phân tích:** Vấn đề cần kiểm tra đầu tiên là **instances × Hikari pool size** và **thời gian giữ connection**, không phải ngay lập tức “chuyển sang AlloyDB thì sẽ hết lỗi”.

### 14.2. Một cấu hình ban đầu có thể kiểm thử

| Tham số | Mốc kiểm thử | Giải thích |
| --- | ---: | --- |
| DB budget cho orders-api | 240 sessions | Phần còn lại dành cho hệ thống và services khác |
| Max Cloud Run instances cả hai revisions | 24 | Tính theo rollout |
| Hikari max pool/instance | 8 | Trần 192 connections, còn headroom |
| Hikari minIdle | 0 | Tránh giữ nhiều sessions idle khi scale-out |
| Borrow timeout | 10 s | Phải thấp hơn deadline request có budget khác |
| Query/transaction timeouts | Theo SLO | Không để giữ connection quá lâu |
| DB CPU/memory headroom | Theo load test | Không suy chỉ từ số sessions |

**Thử A:** Chạy với 24 instances × pool 8 và đo throughput/latency. Nếu Hikari pending cao nhưng DB còn CPU/IOPS rảnh, kiểm tra held connections và điều chỉnh pool hợp lý. Nếu DB CPU đang bão hòa thì **tăng connections chỉ làm tranh chấp hơn**.

**Thử B:** Với Cloud SQL PostgreSQL Enterprise Plus đủ prerequisites hoặc AlloyDB, bật managed pooling trong môi trường thử rồi chuyển một canary đi **cổng 6432**/proxy option phù hợp. So sánh MCP waiting, server connections, Hikari pending, application p95 và hiệu năng của các SQL features đã liệt kê.

**Thử C:** Kiểm tra ứng dụng dùng `SET search_path` hoặc JDBC prepared statements có hoạt động đúng qua **transaction mode** hay không. Nếu không, cân nhắc session mode/direct với workload cần session state.

**Quyết định:** Chỉ bật MCP production khi số liệu chứng minh lợi ích và **đã đánh giá restart/transaction behavior/rollback**. Không ép tất cả workloads qua pooler chỉ vì một nhóm API có nhiều kết nối ngắn.

## 15. Bài lab thực hành có hướng dẫn

**Mục tiêu:** Tính budget, cấu hình pool và chẩn đoán bão hòa trên **project/instance lab riêng**. Nếu không có quyền truy cập Cloud SQL/AlloyDB hoặc ngân sách không cho phép, hoàn thành phần tính toán và mô phỏng, **không cần tạo managed database có phí**.

### Phần A — Kiểm tra chỉ đọc

~~~bash
# Chỉ đọc; sử dụng đúng project lab
gcloud config get-value project

gcloud sql instances describe orders-db \
  --project=LAB_PROJECT_ID \
  --format="yaml(name,databaseVersion,settings.edition,settings.tier,settings.connectionPoolConfig)"

gcloud alloydb instances describe primary-instance \
  --cluster=orders-cluster \
  --region=asia-southeast1 \
  --project=LAB_PROJECT_ID \
  --format="yaml(name,instanceType,connectionPoolConfig)"
~~~

Hai lệnh cuối đại diện **hai lựa chọn database**: không bắt buộc cả hai tài nguyên đều tồn tại trong lab. Nếu một bên chưa được tạo, ghi “NOT PRESENT”, không tạo production-sized instance để kiểm chứng.

Nếu có một endpoint PostgreSQL thật với DB user được phép, chạy các SQL **chỉ đọc** ở mục 3 và 11. Không dump password, connection URI có credential hoặc toàn bộ SQL text nhạy cảm ra báo cáo.

### Phần B — Tính bằng bảng

Giả sử:

- Cloud SQL max_connections = 320 (giả định).
- Kết nối dành cho admin, reporting, migrations và dự phòng = 120.
- Có 20 Cloud Run instances đồng thời và 4 GKE Pods cùng ghi database.
- Mỗi JVM khởi tạo **một** Hikari pool, các workloads dùng một cặp user/database.

**Yêu cầu:** Tính ngân sách còn lại **200**; nếu Hikari max pool 10 thì trần 24 × 10 = **240** (không đạt). Đề xuất pool size 6 hoặc 8, rồi so với application p95 và database saturation trong load test. Với 8, 24 × 8 = **192**, headroom chỉ 8; cần margin rộng hơn nếu instances/jobs có thể tăng. Có thể chọn 6 → **144** để dự phòng, sau đó đo thời gian mượn pool.

### Phần C — Kiểm thử theo từng tầng

1. Đặt Hikari max pool 5, minIdle 0, connectionTimeout 10 s; ghi nhận baseline.
2. Thử tải tăng dần với **endpoint read-only trên DB test**; không tạo truy vấn tấn công hoặc ghi dữ liệu lớn.
3. Thu metrics active/idle/pending, DB sessions, CPU, p95 và request failures.
4. Khi thấy pending borrowers, xác định query/transaction giữ connection bao lâu trước khi tăng pool.
5. Với MCP sandbox đã chuẩn bị, chạy test qua **5432 direct** rồi **6432 pooler** (hoặc Auth Proxy mode được hỗ trợ); ghi khác biệt clients/server sessions/wait.
6. Kiểm tra một SQL feature có session state bằng dữ liệu lab để so transaction/session mode; không đổi mọi app sang transaction mode trước khi test driver.
7. Mô phỏng rollout bằng tính toán số instances của hai revisions thay vì thực sự ép scale production.
8. Đề xuất cấu hình cuối dựa vào **số liệu và an toàn**, không chọn pool size theo một công thức duy nhất.

### Phần D — Bằng chứng nộp bài

| Bằng chứng | Kết quả cần thể hiện |
| --- | --- |
| Database type/edition/region | Cloud SQL Enterprise/Enterprise Plus hoặc AlloyDB |
| `max_connections` và reserved budget | Giá trị cấu hình/quan sát |
| Số instances, Pods, Jobs | Mức peak và rollout |
| HikariCP config | Maximum/minIdle, timeouts, vòng đời |
| Metrics | Active/idle/pending/borrow time và DB server sessions |
| MCP khi có | Pool mode, 5432/6432, client waiting/server connections |
| Compatibility | Driver, prepared statement, session state |
| Error/failover | Loại lỗi, bounded retry và recovery time |
| Tuning decision | Chỉ rõ bottleneck và tác động tới p95/5xx |
| Rollback plan | Trả lại endpoint/config cũ, không xóa DB |

## 16. Câu hỏi ôn tập và đáp án

1. **HikariCP pool 5 trên 20 Cloud Run instances tạo tối đa bao nhiêu clients?** Khoảng **100** database connections từ ứng dụng đó nếu mỗi instance có một pool; chưa tính revisions/jobs khác.
2. **HTTP concurrency 80 nghĩa là phải có 80 DB connections/instance?** Không. Connection nhu cầu phụ thuộc DB hold time và mức dùng DB của request.
3. **`max_connections` là toàn bộ ngân sách dành cho app?** Không; phải dự phòng và tính workload khác.
4. **Cloud SQL Auth Proxy tự pooling không?** Không; nó tạo secure connectivity, có thể kết hợp client/managed pooling.
5. **Cloud Run built-in Cloud SQL 100 connections/instance có áp cho mọi Language Connector?** Không.
6. **Cloud SQL PostgreSQL nào có Google-managed MCP?** **Enterprise Plus** đủ network/maintenance prerequisites.
7. **Bật Cloud SQL MCP trên instance hiện hữu có restart không?** Có; phải lập maintenance/change plan.
8. **Port direct PostgreSQL và managed pooler?** Thông thường **5432** và **6432**.
9. **MCP max_pool_size=50 có là tối đa 50 sessions trên cả instance?** Không; giới hạn theo user/database **trên mỗi pooler**.
10. **AlloyDB MCP mặc định bật?** Không, cần bật và cấu hình.
11. **AlloyDB MCP hỗ trợ kết nối public IP?** Không.
12. **Transaction mode trả server connection khi nào?** Sau khi transaction kết thúc; session mode giữ đến client disconnect.
13. **Ứng dụng dùng LISTEN lâu dài nên chọn transaction mode?** Không; cần session/direct theo tính năng.
14. **`Connection is not available` ở Hikari luôn do `max_connections`?** Không; có thể pool đầy vì query/transaction chậm.
15. **Tăng Cloud Run max instances có thể làm DB lỗi hơn?** Có, vì nhân số pool.
16. **Tại sao không retry giao dịch ghi mù quáng sau timeout?** Có thể transaction đã commit; cần idempotency/reconciliation.
17. **Pooler có biến query chậm thành nhanh không?** Không; nó tối ưu kết nối, SQL/IO/locks vẫn phải xử lý.
18. **Khi có pooling cả hai tầng, cần metric gì?** Hikari pending/borrow và MCP waiting/server connections bên cạnh DB/query metrics.

## 17. Checklist production và tài liệu chính thức

- [ ] Xác định PostgreSQL Cloud SQL edition hoặc AlloyDB instance; kiểm tra region/network/maintenance/version.
- [ ] Đo `max_connections` và dự trù phần cho admin, các services khác, migrations và headroom.
- [ ] Tính **instances/Pods/jobs/revisions × pools** cho peak và rollout.
- [ ] Java dùng singleton HikariCP, `try-with-resources` và không giữ transaction khi gọi HTTP ngoài.
- [ ] `maximumPoolSize`/`minimumIdle`, timeout và maxLifetime đã thử với p95 workload.
- [ ] Cloud Run request-based CPU throttling và stale connections đã có chiến lược xử lý.
- [ ] Phân biệt Auth Proxy/Language Connector với pooling và yêu cầu IAM/TLS/network.
- [ ] Nếu Cloud SQL MCP: Enterprise Plus, network mới, maintenance version và restart window được xác nhận.
- [ ] Nếu AlloyDB MCP: endpoint/port 6432 private, auth và pooler stats được kiểm tra.
- [ ] Pool mode transaction/session đã kiểm tra prepared statements, SET, LISTEN, temp tables, locks.
- [ ] MCP client vs server connection limits đã tính theo user/database/pooler, không chỉ per instance.
- [ ] Có đo pending borrowers, waiting clients, query wait/locks, CPU/memory/IOPS.
- [ ] Bounded retry, idempotent writes, failover/secret rotation runbook đã kiểm chứng.
- [ ] Có canary, load test, rollback plan và người phê duyệt các thay đổi có restart.
- [ ] Theo dõi Billing: database tier/edition, Cloud Run/GKE scaling, logs/monitoring và network.
- [ ] Không đưa DB password, IAM tokens, full SQL text nhạy cảm vào logs/tài liệu.

**Nguồn Google Cloud chính thức:**

- [Cloud SQL PostgreSQL: Manage database connections](https://docs.cloud.google.com/sql/docs/postgres/manage-connections) — pool, timeouts, retry/backoff.
- [Cloud SQL PostgreSQL: Managed Connection Pooling overview](https://docs.cloud.google.com/sql/docs/postgres/managed-connection-pooling) — requirements, poolers, modes, ports.
- [Cloud SQL PostgreSQL: Configure MCP](https://docs.cloud.google.com/sql/docs/postgres/configure-mcp) — enable, flags, restart và quan sát.
- [Cloud SQL PostgreSQL: Quotas and limits](https://docs.cloud.google.com/sql/docs/postgres/quotas) — max connections và Cloud Run built-in limit.
- [Cloud SQL PostgreSQL: Connect from Cloud Run](https://docs.cloud.google.com/sql/docs/postgres/connect-run) — CPU throttling, connection management.
- [Cloud SQL PostgreSQL: Cloud SQL Auth Proxy](https://docs.cloud.google.com/sql/docs/postgres/sql-proxy) — kênh mã hóa/IAM, không tự pooling.
- [AlloyDB: Connection overview](https://docs.cloud.google.com/alloydb/docs/connection-overview) — client pools, server-side MCP, tuning.
- [AlloyDB: Configure managed connection pooling](https://docs.cloud.google.com/alloydb/docs/configure-managed-connection-pooling) — port 6432, flags, transaction/session, metrics.
- [AlloyDB: Choose connectivity](https://docs.cloud.google.com/alloydb/docs/choose-alloydb-connectivity) — direct/Auth Proxy/connectors và TLS.
- [Cloud Run: Concurrency](https://docs.cloud.google.com/run/docs/about-concurrency) — request concurrency và autoscaling.
- [Cloud SQL MySQL: Managed Connection Pooling](https://docs.cloud.google.com/sql/docs/mysql/managed-connection-pooling) — thread pool khác PostgreSQL.
- [Cloud SQL pricing](https://cloud.google.com/sql/pricing) và [AlloyDB pricing](https://cloud.google.com/alloydb/pricing) — edition, compute, storage và chi phí.

**Kết luận:** **Đủ connections để phục vụ tải, nhưng không nhiều đến mức làm cạn database.** Pool ở ứng dụng giới hạn connections theo process, managed pooler chia sẻ backend sessions khi được hỗ trợ, còn PostgreSQL `max_connections` và CPU/memory/IO vẫn quyết định giới hạn thực tế. Hãy **tính budget ở quy mô toàn hệ thống, đo active/waiting/latency, kiểm chứng transaction/session compatibility và rollout có khả năng rollback**.
