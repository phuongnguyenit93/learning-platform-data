# Pool kết nối, private IP và IAM database authentication khi hỗ trợ

## Mục tiêu học tập

Trong module **SPRING_CLOUD_PROVIDER_INTEGRATION**, Spring Boot tích hợp dịch vụ managed của AWS, Azure và Google Cloud để truy cập storage, messaging, dữ liệu và quản lý danh tính/quyền. Trên Google Cloud, **Cloud SQL** cung cấp cơ sở dữ liệu quan hệ managed. Một ứng dụng Spring Boot có thể kết nối thành công bằng JDBC nhưng vẫn gặp sự cố khi tải tăng, khi nhiều replica cùng mở pool, khi workload chuyển sang private network hoặc khi dùng IAM database authentication.

Bài học tập trung vào ba vấn đề vận hành:

1. **Connection pool:** cấu hình HikariCP và tính tổng connection từ mọi replica, worker, migration job và công cụ quản trị.
2. **Private IP:** đưa workload vào đúng VPC path và cấu hình Cloud SQL Connector để sử dụng private address.
3. **IAM database authentication:** phân biệt quyền kết nối Cloud SQL với quyền đăng nhập database và quyền SQL; chỉ bật khi engine/phiên bản hỗ trợ.

Sau bài này, bạn có thể ước lượng connection budget cho Cloud SQL, điều chỉnh pool theo autoscaling, thiết kế private networking cho Cloud Run/GKE, cấu hình IAM DB auth cho PostgreSQL/MySQL khi phù hợp và kiểm thử khả năng phục hồi.

> **Phạm vi:** Ví dụ chính sử dụng Cloud SQL PostgreSQL, Spring Boot, HikariCP và Cloud SQL Java Connector. Một số tùy chọn tương tự áp dụng cho MySQL; tính năng IAM database authentication và cách định danh database user phụ thuộc engine/phiên bản. Không suy rằng mọi Cloud SQL engine đều hỗ trợ cùng một cơ chế.

## 1. Ba lớp cần kiểm soát khi kết nối Cloud SQL

Kết nối thành công cần đồng thời đáp ứng ba lớp:

| Lớp | Câu hỏi cần trả lời | Ví dụ |
| --- | --- | --- |
| Network | Workload có route tới địa chỉ Cloud SQL đã chọn không? | VPC, Private IP, firewall, egress |
| Cloud IAM | Workload có được phép kết nối instance không? | ADC, `roles/cloudsql.client` |
| Database authorization | Danh tính nào đăng nhập và được chạy câu SQL nào? | DB user, IAM DB auth, SQL grants |

HikariCP là lớp thứ tư ở phía ứng dụng: nó quản lý vòng đời và số lượng JDBC connection. HikariCP không cấp quyền IAM, không tạo route mạng và không thay thế database user.

~~~mermaid
flowchart TD
    APP["Spring Boot replicas"] --> POOL["HikariCP pools"]
    POOL --> JDBC["JDBC driver + Cloud SQL Connector"]
    NET["VPC route / Private IP"] --> JDBC
    IAM["ADC + Cloud SQL IAM"] --> JDBC
    JDBC --> DB["Cloud SQL instance"]
    DB --> AUTH["DB user / IAM DB authentication"]
    AUTH --> SQL["SQL roles and grants"]
~~~

Nếu ứng dụng báo timeout, cần điều tra network và pool. Nếu báo `PERMISSION_DENIED` ở connector, cần kiểm IAM. Nếu kết nối được nhưng câu `SELECT` bị từ chối, cần kiểm database grants. Không xử lý cả ba loại lỗi bằng cách tăng pool size hoặc cấp Owner cho service account.

## 2. Connection pool hoạt động như thế nào?

### 2.1. Vì sao cần pool?

Thiết lập một database connection có chi phí: mở socket, xác thực, thiết lập TLS, tạo session và khởi tạo trạng thái JDBC. Nếu mỗi HTTP request tạo rồi đóng một connection mới, hệ thống tốn thời gian và có thể tạo đợt kết nối dồn dập khi traffic tăng.

**Connection pool** giữ một nhóm JDBC connections để các request mượn dùng rồi trả lại. Spring Boot mặc định dùng HikariCP trong cấu hình JDBC/JPA thông thường.

~~~mermaid
flowchart LR
    R1["HTTP request A"] --> POOL["HikariCP"]
    R2["HTTP request B"] --> POOL
    R3["HTTP request C"] --> POOL
    POOL --> C1["JDBC connection 1"]
    POOL --> C2["JDBC connection 2"]
    POOL --> C3["JDBC connection 3"]
    C1 --> DB["Cloud SQL"]
    C2 --> DB
    C3 --> DB
~~~

Khi một request gọi repository/JdbcTemplate, Spring lấy connection từ pool. Sau khi transaction kết thúc và connection được đóng ở tầng JDBC, HikariCP nhận lại connection để tái sử dụng; `close()` trên connection mượn từ pool thường trả connection về pool thay vì đóng socket vật lý ngay lập tức.

### 2.2. Cloud SQL Connector không phải pool

Cloud SQL Java Connector xử lý xác thực và đường kết nối được bảo vệ đến instance. Nó không tự giới hạn số JDBC sessions mà ứng dụng tạo. HikariCP đảm nhiệm việc đó.

| Thành phần | Trách nhiệm |
| --- | --- |
| Cloud SQL Java Connector / Socket Factory | Xác thực instance, thiết lập TLS và tạo kết nối |
| PostgreSQL/MySQL JDBC driver | Thực hiện giao thức database, statement và transaction |
| HikariCP | Giới hạn, cấp phát, tái sử dụng và thu hồi JDBC connections |
| Spring transaction manager | Quản lý transaction boundary |
| Cloud SQL | Giới hạn tài nguyên và số database connections theo cấu hình/engine |

Nếu tạo nhiều `DataSource` hoặc nhiều pool trong cùng một process, mỗi pool có ngân sách riêng. Tránh vô tình tạo pool mới theo từng service hoặc mỗi request.

## 3. Tính connection budget trên toàn hệ thống

### 3.1. Pool size phải nhân với số replica

Giả sử cấu hình:

- 5 replica Spring Boot.
- Mỗi replica có `maximum-pool-size = 8`.
- 2 background worker có pool riêng, mỗi pool tối đa 3 connection.
- 1 migration job có thể mở 2 connection.
- 3 connection dành cho quản trị/monitoring.

Tổng connection tối đa ước lượng:

~~~text
API replicas       = 5 × 8 = 40
Background workers = 2 × 3 =  6
Migration job      =          2
Admin/monitoring   =          3
--------------------------------
Tổng dự kiến       =         51 connections
~~~

Cloud SQL nhìn thấy tổng kết nối từ tất cả workload, không chỉ một HikariCP instance. Một pool 8 connection có vẻ nhỏ, nhưng 20 replica có thể tạo tới 160 connection cho API.

### 3.2. Công thức connection budget

Có thể lập ngân sách theo công thức:

\[
C_{total} =
N_{api}P_{api}
+ N_{worker}P_{worker}
+ C_{jobs}
+ C_{admin}
\]

Trong đó:

- `N_api`: số replica API tối đa có thể chạy đồng thời.
- `P_api`: maximum pool size của mỗi API replica.
- `N_worker`: số worker replica tối đa.
- `P_worker`: pool size của mỗi worker.
- `C_jobs`: connection tối đa từ migration, batch và scheduled jobs.
- `C_admin`: headroom cho vận hành, monitoring và kết nối khẩn cấp.

Đặt `C_total` thấp hơn giới hạn connection thực tế của instance. Phần chênh lệch là headroom để chịu burst, failover, rolling deployment hoặc thao tác quản trị. Không có một tỷ lệ headroom phù hợp cho mọi instance; chọn theo tải, giới hạn database và yêu cầu vận hành.

### 3.3. Autoscaling có thể làm pool vượt giới hạn

Cloud Run hoặc GKE có thể tăng replica khi request tăng. Nếu pool size cố định theo từng replica, tổng connection tăng theo số replica.

Ví dụ Cloud Run:

~~~text
max instances = 20
maximum-pool-size per instance = 10

Potential API connections = 20 × 10 = 200
~~~

Nếu Cloud SQL chỉ còn ngân sách 100 connection cho API, cấu hình này có thể làm database từ chối connection khi autoscaling đạt đỉnh.

Giải pháp phối hợp:

1. Chọn `max instances` hoặc replica ceiling phù hợp.
2. Giới hạn pool mỗi replica theo connection budget.
3. Đặt concurrency của ứng dụng hợp lý; không cần một connection cho mọi request đang chờ nếu request không truy cập DB đồng thời.
4. Dùng queue cho batch/background workload có thể điều tiết.
5. Theo dõi số connection thực tế và thời gian chờ pool.
6. Dành connection cho migration và quản trị thay vì dùng hết ngân sách cho API.

### 3.4. Pool size không bằng HTTP concurrency

Một request có thể thực hiện nhiều công việc không dùng database: gọi HTTP service, đọc cache hoặc xử lý dữ liệu trong bộ nhớ. Vì vậy không nhất thiết cấu hình pool bằng concurrency HTTP.

Ngược lại, nếu request giữ transaction trong khi gọi một dịch vụ bên ngoài, connection có thể bị giữ lâu và làm pool cạn. Giữ transaction ngắn, không gọi network chậm bên trong transaction nếu không cần thiết.

## 4. Cấu hình HikariCP trong Spring Boot

### 4.1. Cấu hình khởi đầu

~~~yaml
spring:
  datasource:
    hikari:
      pool-name: orders-cloud-sql-pool
      maximum-pool-size: 6
      minimum-idle: 1
      connection-timeout: 30000
      validation-timeout: 5000
      idle-timeout: 600000
      max-lifetime: 1800000
      leak-detection-threshold: 0
~~~

Các giá trị là ví dụ ban đầu. Cần điều chỉnh theo Cloud SQL instance, replica count, thời gian query và giới hạn connection. `leak-detection-threshold: 0` tắt cảnh báo leak; chỉ bật tạm thời khi điều tra, với ngưỡng phù hợp thời gian xử lý bình thường.

### 4.2. Ý nghĩa các tham số quan trọng

| Tham số | Tác dụng | Cách cân nhắc |
| --- | --- | --- |
| `maximum-pool-size` | Số connection tối đa trong một pool | Tính theo tổng replica và DB budget |
| `minimum-idle` | Số connection nhàn rỗi pool cố gắng duy trì | Đặt thấp khi workload co giãn/scale-to-zero |
| `connection-timeout` | Thời gian chờ mượn connection | Đủ để chờ ngắn, nhưng không che giấu pool saturation |
| `validation-timeout` | Giới hạn thời gian kiểm tra connection | Nhỏ hơn connection timeout |
| `idle-timeout` | Thời gian loại connection nhàn rỗi khi pool có thể co lại | Chỉ có ý nghĩa khi min idle thấp hơn max |
| `max-lifetime` | Tuổi tối đa connection trước khi pool thay thế | Phối hợp với timeout của database/network |
| `leak-detection-threshold` | Log connection bị giữ lâu hơn ngưỡng | Dùng chẩn đoán; không tự sửa leak |

HikariCP thường có default `maximumPoolSize` là 10 nếu không cấu hình. Không dựa vào default này để tính capacity production.

### 4.3. Chọn minimum idle cho workload co giãn

Nếu `minimum-idle` bằng `maximum-pool-size`, pool có xu hướng giữ số connection gần cố định. Điều đó phù hợp một số workload ổn định nhưng có thể giữ nhiều connection nhàn rỗi khi traffic thấp.

Với Cloud Run hoặc worker có thể scale về 0, đặt `minimum-idle` thấp (thậm chí 0 nếu phù hợp) giúp giảm connection nhàn rỗi. Đổi lại, khi có request mới, pool cần tạo connection và request đầu có thể chậm hơn. Đo cold-start và latency trước khi quyết định.

### 4.4. maxLifetime và Cloud SQL Connector

HikariCP có thể loại connection cũ sau `max-lifetime` để tránh giữ session quá lâu. Chọn giá trị thấp hơn timeout do database/network áp dụng nếu có. Không đặt quá thấp khiến pool liên tục đóng/mở connection và tăng chi phí handshake.

Cloud SQL Java Connector quản lý thông tin xác thực/TLS của connector theo cơ chế riêng. Việc refresh metadata/certificate của connector không có nghĩa mọi JDBC session đang mở phải bị đóng ngay. Pool vẫn cần lifecycle policy cho session và phải xử lý connection bị ngắt do maintenance/failover.

### 4.5. Theo dõi pool saturation

Các chỉ số Hikari cần quan sát:

- Active connections: số connection đang được mượn.
- Idle connections: số connection đang chờ được dùng.
- Pending threads: số thread đang chờ connection.
- Total connections: tổng connection pool đang giữ.
- Connection acquire time: thời gian chờ mượn connection.

Dấu hiệu pool saturation:

- Active liên tục bằng maximum pool size.
- Pending threads tăng.
- Thời gian chờ connection tăng.
- Request latency tăng dù query latency không đổi.

Nếu query chậm hoặc transaction giữ connection lâu, tăng pool có thể chỉ chuyển áp lực từ HikariCP sang Cloud SQL. Kiểm tra slow query, lock, transaction duration và thời gian gọi dịch vụ ngoài trước khi tăng pool.

## 5. Transaction và vòng đời connection

### 5.1. Giữ transaction ngắn

~~~java
@Service
public class OrderService {
    private final JdbcTemplate jdbc;

    public OrderService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public void markPaid(String orderId) {
        jdbc.update(
                "update orders set status = ? where id = ?",
                "PAID", orderId);
        jdbc.update(
                "insert into order_audit(order_id, action) values (?, ?)",
                orderId, "PAYMENT_CONFIRMED");
    }
}
~~~

Trong ví dụ, hai câu SQL nằm trong một transaction. Sau commit/rollback, connection được trả về pool.

Tránh pattern:

~~~java
@Transactional
public void processOrder(String orderId) {
    jdbc.update("update orders set status = 'PROCESSING' where id = ?", orderId);
    callSlowExternalApi(); // Giữ transaction/connection trong khi chờ network.
    jdbc.update("update orders set status = 'DONE' where id = ?", orderId);
}
~~~

Nếu API ngoài mất 20 giây, transaction và connection có thể bị giữ trong 20 giây. Hãy chia thành các bước có trạng thái rõ ràng, commit trước khi gọi dịch vụ ngoài khi nghiệp vụ cho phép, rồi cập nhật kết quả bằng transaction khác.

### 5.2. Đóng connection đúng cách

Khi dùng JDBC thuần, luôn đóng `Connection`, `Statement` và `ResultSet` bằng try-with-resources. Khi dùng JdbcTemplate/JPA, Spring quản lý việc mượn/trả connection theo transaction boundary; không tự đóng connection được inject hoặc đang do transaction manager quản lý.

### 5.3. Leak và starvation

Connection leak xảy ra khi code mượn connection nhưng không trả lại. Pool dần cạn và các request khác chờ đến `connection-timeout`.

Khi gặp lỗi:

1. Xem thread dump và stack trace từ leak detection nếu bật.
2. Tìm nhánh code không đóng resource hoặc transaction kéo dài.
3. Kiểm tra exception path có bỏ qua cleanup không.
4. Đo thời gian transaction và các cuộc gọi ngoài.
5. Sửa lifecycle trước khi tăng pool.

## 6. Cloud SQL connection limit và các mô hình pooling bổ sung

### 6.1. Connection limit phụ thuộc engine và cấu hình instance

Cloud SQL không có một con số connection tối đa áp dụng cho mọi instance. Giới hạn phụ thuộc database engine, memory/tier, flags và cấu hình instance. PostgreSQL và MySQL cũng có cách quản lý session khác nhau.

Không dùng một giá trị cố định từ ví dụ để kết luận instance của bạn chịu được bao nhiêu connection. Kiểm tra cấu hình/metric của instance đang chạy và để lại capacity cho tác vụ vận hành.

### 6.2. Khi nào cần proxy hoặc pooler?

HikariCP quản lý pool ở từng process ứng dụng. Nếu có rất nhiều replica ngắn hạn, việc mỗi replica mở một pool nhỏ vẫn có thể tạo nhiều database sessions.

Có thể cân nhắc một lớp pooling/proxy bổ sung nếu engine, phiên bản và kiến trúc hỗ trợ, ví dụ pooler PostgreSQL hoặc dịch vụ proxy phù hợp. Trước khi triển khai cần đánh giá:

- Chế độ session pooling hay transaction pooling.
- Tương thích prepared statements, session variables, temporary tables và advisory locks.
- Hành vi transaction và connection pinning.
- Cách xác thực IAM/password qua proxy.
- Giới hạn và khả năng quan sát của pooler.
- Độ trễ và điểm lỗi bổ sung.

Transaction pooling có thể thay đổi giả định về session affinity. Ứng dụng dựa vào session state phải được kiểm thử trước khi bật. Không thêm proxy chỉ vì thấy số connection cao; trước hết hãy tính budget và tối ưu pool ở ứng dụng.

## 7. Private IP: kiến trúc mạng và đường đi

### 7.1. Private IP là địa chỉ, không phải quyền truy cập

Cloud SQL Private IP đặt instance trong phạm vi địa chỉ riêng có thể truy cập từ mạng được kết nối. Java Connector có thể được cấu hình chọn private IP, nhưng **connector không tự tạo route VPC** và không thay thế firewall/network configuration.

~~~mermaid
flowchart LR
    subgraph VPC["Google Cloud VPC"]
      APP["Cloud Run / GKE / Compute workload"]
      SQL["Cloud SQL Private IP"]
      APP -->|"Private network route"| SQL
    end
    IAM["ADC + IAM permissions"] --> APP
    APP --> CONN["Cloud SQL Java Connector"]
    CONN --> SQL
~~~

Để kết nối được, workload cần đồng thời:

1. Instance có Private IP hoặc private connectivity endpoint đã được cấu hình.
2. Workload có network path đến VPC/endpoint đó.
3. Firewall/egress policy cho phép luồng kết nối cần thiết.
4. Java Connector chọn IP type phù hợp.
5. ADC principal có quyền kết nối Cloud SQL.

### 7.2. Private Service Access và Private Service Connect

Hai mô hình này không nên dùng lẫn tên:

- **Private Service Access (PSA):** kết nối private services thông qua VPC peering với một dải địa chỉ được phân bổ cho service producer; đây là mô hình phổ biến khi cấp Private IP cho Cloud SQL.
- **Private Service Connect (PSC):** cung cấp endpoint riêng để consumer truy cập service thông qua một endpoint được cấu hình; cách triển khai, DNS và kết nối khác PSA.

Chọn mô hình theo kiến trúc Cloud SQL instance và hướng dẫn networking của tổ chức. Không giả định bật PSC tự động tạo Private Service Access hoặc ngược lại.

### 7.3. Cloud Run

Cloud Run cần cấu hình kết nối mạng phù hợp trước khi dùng Cloud SQL Private IP. Các mô hình có thể gồm:

- **Direct VPC egress** khi cấu hình triển khai và Region hỗ trợ.
- **Serverless VPC Access connector** trong kiến trúc sử dụng connector mạng serverless.

Sau khi có đường mạng, cấu hình Cloud SQL Java Connector chọn `PRIVATE`. Chỉ sửa JDBC URL mà chưa cấu hình egress/VPC thì request vẫn timeout.

Cần tính cả egress firewall và giới hạn kết nối khi Cloud Run scale out. Đặt `max instances`, request concurrency và Hikari pool cùng một connection budget.

### 7.4. GKE và Compute Engine

Với GKE, kiểm tra cluster/node/pod network và VPC route đến Cloud SQL. Workload Identity Federation for GKE cung cấp danh tính workload; nó không tự tạo network route.

Với Compute Engine, VM cần nằm trong VPC có route tới instance và gắn service account phù hợp. Firewall/egress policy phải cho phép luồng cần thiết.

### 7.5. Chọn IP type trong JDBC Socket Factory

Với PostgreSQL:

~~~properties
spring.datasource.url=jdbc:postgresql:///${DB_NAME}?cloudSqlInstance=${INSTANCE_CONNECTION_NAME}&socketFactory=com.google.cloud.sql.postgres.SocketFactory&ipTypes=PRIVATE
~~~

`ipTypes=PRIVATE` yêu cầu connector chọn private address. `DB_NAME` và `INSTANCE_CONNECTION_NAME` là placeholder được Spring resolve từ biến môi trường/property. Nếu instance không có Private IP hoặc workload không route tới địa chỉ đó, kết nối sẽ thất bại. Khi cần Public IP, chọn IP type phù hợp theo tài liệu connector và policy mạng.

Không dùng `PUBLIC,PRIVATE` như cách che lỗi private route nếu yêu cầu bảo mật là chỉ đi qua mạng riêng. Chọn rõ đường kết nối mà workload được phép sử dụng.

## 8. IAM database authentication khi engine hỗ trợ

### 8.1. Ba quyền/danh tính độc lập

IAM database authentication có thể gây nhầm lẫn vì Google Cloud IAM và database authorization cùng tham gia:

| Thành phần | Vai trò |
| --- | --- |
| Workload IAM principal | Service account hoặc principal chạy ứng dụng |
| `roles/cloudsql.client` | Quyền kết nối instance qua connector/proxy |
| `roles/cloudsql.instanceUser` | Quyền IAM login vào database khi dùng IAM DB auth |
| IAM database user | User được tạo/ánh xạ trong Cloud SQL |
| SQL roles/grants | Quyền truy cập database, schema, table, sequence và câu lệnh |

Một service account có `roles/cloudsql.client` có thể thiết lập kết nối tới instance nhưng chưa chắc đăng nhập được bằng IAM DB authentication. Khi dùng IAM DB auth, workload cần quyền login tương ứng và một IAM database user hợp lệ.

Sau khi đăng nhập, quyền SELECT/INSERT/UPDATE/DELETE vẫn do database roles/grants quyết định. IAM role không tự cấp quyền trên bảng.

### 8.2. Engine và phiên bản phải hỗ trợ

IAM database authentication không được hỗ trợ đồng nhất trên mọi database engine, edition và phiên bản. Ví dụ thực hành trong bài tập tập trung vào PostgreSQL và MySQL với connector tương ứng. Trước khi bật trên instance thực tế, xác minh:

- Engine và phiên bản Cloud SQL có hỗ trợ IAM DB auth không.
- Instance đã bật cờ/tùy chọn IAM database authentication cần thiết chưa.
- Loại IAM database user phù hợp (user hay service account) đã được tạo chưa.
- Cloud SQL Java Connector/Socket Factory và JDBC driver đang dùng có hỗ trợ `enableIamAuth` không.
- Workload principal có `cloudsql.instances.login` thông qua IAM role phù hợp không.

Không áp dụng cú pháp hoặc giả định của PostgreSQL cho MySQL/SQL Server. Đặc biệt, không giả định SQL Server có cùng cơ chế IAM DB authentication chỉ vì nó cũng là Cloud SQL.

### 8.3. Password-based và IAM DB authentication

| Tiêu chí | Password-based DB auth | IAM database authentication |
| --- | --- | --- |
| Danh tính kết nối instance | ADC/IAM qua connector | ADC/IAM qua connector |
| Database login | Username + password database | IAM principal/user và token IAM |
| Quản lý secret | Cần bảo vệ, rotation password | Giảm password tĩnh cho login |
| Quyền IAM | Cloud SQL Client | Cloud SQL Client + quyền IAM login |
| Quyền SQL | Database grants | Database grants |
| Phù hợp | Ứng dụng hiện hữu, engine/config hỗ trợ | Workload có IAM identity và engine hỗ trợ |

IAM DB auth không có nghĩa ứng dụng không còn cần secret ở mọi nơi; các secret khác như API key, encryption key và credential của dịch vụ phụ thuộc vẫn phải quản lý.

### 8.4. Tạo database IAM user

Tạo IAM database user là thao tác quản trị Cloud SQL, tách khỏi việc tạo service account. Tên user được chuẩn hóa theo engine và loại principal. Với service account, định dạng tên database có thể khác email hiển thị đầy đủ; hãy dùng đúng quy tắc của Cloud SQL cho engine và kiểm tra user sau khi tạo.

Sau đó cấp quyền SQL cần thiết bằng câu lệnh database. Ví dụ PostgreSQL, sau khi IAM user tồn tại và đã đăng nhập được:

~~~sql
GRANT CONNECT ON DATABASE orders TO orders_app_iam;
GRANT USAGE ON SCHEMA public TO orders_app_iam;
GRANT SELECT, INSERT, UPDATE
ON ALL TABLES IN SCHEMA public TO orders_app_iam;
GRANT USAGE, SELECT
ON ALL SEQUENCES IN SCHEMA public TO orders_app_iam;
~~~

Tên role `orders_app_iam` chỉ là ví dụ minh họa; thay bằng tên database user thực tế được Cloud SQL tạo. Nếu bảng/sequence mới được tạo sau đó, cần default privileges hoặc migration grant tương ứng.

## 9. Cấu hình IAM DB authentication trong Spring Boot

### 9.1. PostgreSQL Socket Factory

Với Cloud SQL PostgreSQL Socket Factory, ví dụ JDBC URL khi bật IAM DB auth:

~~~properties
spring.datasource.url=jdbc:postgresql:///${DB_NAME}?cloudSqlInstance=${INSTANCE_CONNECTION_NAME}&socketFactory=com.google.cloud.sql.postgres.SocketFactory&enableIamAuth=true&ipTypes=PRIVATE
spring.datasource.username=${IAM_DB_USER}
~~~

`enableIamAuth=true` yêu cầu connector dùng IAM database authentication theo khả năng của engine/connector. Username phải là tên IAM database user đã được tạo trong Cloud SQL theo quy tắc PostgreSQL; không tự đoán hoặc tự cắt email khi chưa kiểm tra định dạng của user.

Trong mô hình này, không đưa password database tĩnh vào datasource như password-based auth. Connector lấy token theo ADC để xác thực database connection. Khi Hikari cần mở connection mới, connector xử lý việc lấy thông tin xác thực theo cơ chế của thư viện.

### 9.2. MySQL Socket Factory

MySQL dùng driver và Socket Factory khác PostgreSQL. Cấu hình có thể dùng `enableIamAuth=true` nếu phiên bản Cloud SQL MySQL và connector đang dùng hỗ trợ:

~~~properties
spring.datasource.url=jdbc:mysql:///${DB_NAME}?cloudSqlInstance=${INSTANCE_CONNECTION_NAME}&socketFactory=com.google.cloud.sql.mysql.SocketFactory&enableIamAuth=true&ipTypes=PRIVATE
spring.datasource.username=${IAM_DB_USER}
spring.datasource.driver-class-name=com.mysql.cj.jdbc.Driver
~~~

Xác minh tên IAM database user theo loại principal và engine. Không copy user naming rule của PostgreSQL sang MySQL.

### 9.3. Password-based vẫn cần Secret Manager

Nếu chưa dùng IAM DB auth, password database nên được lấy từ secret manager hoặc secret injection của môi trường triển khai:

~~~yaml
spring:
  datasource:
    username: ${DB_USER}
    password: ${DB_PASS}
~~~

Không commit password thật vào `application.yml`, Docker image, log hoặc file `.env` dùng chung. Phân tách user runtime và user migration; rotation secret cần được phối hợp với việc tạo connection mới trong pool.

### 9.4. IAM token và connection pool

IAM database authentication sử dụng token trong quá trình xác thực database connection. HikariCP giữ session database đã được mở; không lấy token mới cho từng câu SQL. Khi pool tạo connection mới, connector phải lấy thông tin xác thực còn hiệu lực theo cơ chế tự động của nó.

Điều này dẫn đến một số điểm vận hành:

- Workload ADC phải còn khả dụng khi tạo connection mới.
- IAM role/user cần tồn tại trong suốt vòng đời workload.
- Nếu quyền IAM bị thu hồi, các kết nối database đã mở có thể không bị ngắt ngay lập tức; không coi thu hồi IAM là cơ chế kill session tức thời.
- Khi rotation hoặc thay đổi principal, cần có kế hoạch thay thế connection/pool có kiểm soát.
- Không cache token IAM thủ công trong biến môi trường hoặc cấu hình lâu dài.

## 10. Kết hợp HikariCP, Private IP và IAM DB auth

Một cấu hình khái niệm cho PostgreSQL:

~~~yaml
spring:
  datasource:
    url: jdbc:postgresql:///${DB_NAME}?cloudSqlInstance=${INSTANCE_CONNECTION_NAME}&socketFactory=com.google.cloud.sql.postgres.SocketFactory&enableIamAuth=true&ipTypes=PRIVATE
    username: ${IAM_DB_USER}
    driver-class-name: org.postgresql.Driver
    hikari:
      pool-name: orders-private-cloud-sql
      maximum-pool-size: 6
      minimum-idle: 1
      connection-timeout: 30000
      validation-timeout: 5000
      idle-timeout: 600000
      max-lifetime: 1800000
~~~

Cấu hình này chỉ hoạt động nếu tất cả điều kiện sau đúng:

1. PostgreSQL instance hỗ trợ và đã bật IAM database authentication.
2. Instance có Private IP.
3. Workload có VPC route tới private address.
4. ADC trỏ tới đúng service account/principal.
5. Principal có Cloud SQL Client và quyền IAM DB login cần thiết.
6. IAM database user đã được tạo đúng định dạng.
7. Database user có SQL grants cho nghiệp vụ.
8. Dependency Socket Factory, JDBC driver và property tương thích.
9. Pool size nằm trong connection budget của instance.

Khi chẩn đoán, kiểm tra từng điều kiện theo lớp. Nếu TCP/private route không hoạt động, sửa IAM DB user sẽ không giúp. Nếu connector xác thực được nhưng database từ chối login, tăng Hikari maximum pool size cũng không giải quyết.

## 11. Rotation, failover và phục hồi pool

### 11.1. Connection cũ có thể bị ngắt

Cloud SQL maintenance, failover, network disruption hoặc database restart có thể làm session hiện tại bị đóng. HikariCP phải loại connection lỗi và tạo connection mới.

Ứng dụng cần:

- Đặt connection timeout hợp lý.
- Phân loại transient connection exception.
- Cho pool tạo lại connection sau khi database sẵn sàng.
- Retry transaction ở ranh giới nghiệp vụ với idempotency.
- Không retry mọi câu SQL một cách mù quáng.

### 11.2. Không nhầm connection retry với transaction retry

Nếu connection bị ngắt trước khi câu lệnh chạy, có thể retry sau khi pool tạo connection mới. Nếu bị ngắt trong lúc commit, client có thể không biết transaction đã commit hay chưa.

Với thao tác ghi quan trọng:

1. Dùng idempotency key hoặc unique constraint.
2. Ghi trạng thái nghiệp vụ trong transaction.
3. Sau lỗi không rõ kết quả, truy vấn trạng thái theo idempotency key.
4. Chỉ thực hiện lại khi xác định thao tác chưa hoàn tất.
5. Ghi nhận số lần retry và nguyên nhân.

### 11.3. Thay đổi IAM hoặc secret

Khi thay service account, IAM role hoặc password database:

- Cập nhật workload identity/secret ở môi trường triển khai.
- Đảm bảo connection mới có thể được tạo với thông tin mới.
- Theo dõi connection failures trong lúc rollout.
- Thực hiện rolling restart hoặc pool refresh có kiểm soát nếu cần.
- Thu hồi credential cũ sau khi xác minh workload mới hoạt động.

Không thu hồi password/role cũ trước khi biết replica nào còn dùng connection/credential cũ.

## 12. Giám sát Cloud SQL và HikariCP

### 12.1. Chỉ số ở tầng ứng dụng

| Metric | Ý nghĩa | Dấu hiệu cần điều tra |
| --- | --- | --- |
| Hikari active | Connection đang được mượn | Luôn bằng maximum pool size |
| Hikari idle | Connection sẵn sàng | Luôn bằng 0 trong khi request chờ |
| Hikari pending | Thread chờ connection | Tăng kéo dài |
| Hikari acquire time | Thời gian lấy connection | P95/P99 tăng |
| Transaction duration | Thời gian transaction mở | Dài bất thường |
| SQL latency | Thời gian query | Tăng cùng lock/CPU |
| Connection creation failures | Lỗi mở session mới | IAM, network, DB limit hoặc failover |

### 12.2. Chỉ số ở Cloud SQL

Theo dõi:

- Database connection count và giới hạn engine.
- CPU, memory, storage utilization/latency.
- Query latency, slow query và lock.
- Restart/failover/maintenance events.
- Network throughput và lỗi kết nối.
- Các lỗi authentication/permission.

Kết hợp metric ứng dụng với metric Cloud SQL theo cùng khoảng thời gian để phân biệt pool exhaustion, query saturation, network failure và database capacity.

### 12.3. Cảnh báo có ích

- Hikari pending threads khác 0 kéo dài.
- Active connection liên tục chạm maximum.
- Cloud SQL connection count tiến gần giới hạn.
- Tỷ lệ lỗi tạo connection tăng.
- Query latency hoặc transaction duration tăng bất thường.
- Private IP connection timeout tăng sau thay đổi VPC/egress.
- IAM authentication failures xuất hiện sau rollout/rotation.

Không chỉ cảnh báo theo tổng connection; nên theo dõi cả tuổi request đang chờ và mức sử dụng database.

## 13. Kiểm thử tích hợp và tải

### 13.1. Kiểm thử theo từng lớp

| Bài kiểm tra | Điều cần xác minh | Cách cô lập lỗi |
| --- | --- | --- |
| ADC/IAM | Principal thực tế và quyền Cloud SQL | Kiểm tra role binding, không thay đổi pool |
| Private networking | Workload route tới private IP | Test từ đúng runtime/VPC, không chỉ máy local |
| Database authentication | Password hoặc IAM DB auth | Test user login độc lập |
| SQL authorization | Grants/schema/table | Chạy câu query với đúng DB user |
| Hikari pool | Pool size, acquire time, leak | Tải đồng thời và quan sát metrics |
| Failover/restart | Pool loại connection hỏng và tạo lại | Thử trong sandbox, có idempotency |
| Autoscaling | Tổng connection khi replica đạt max | Tăng replica có kiểm soát và đo DB sessions |

### 13.2. Kịch bản integration test

1. Tạo Cloud SQL PostgreSQL sandbox và database riêng.
2. Bật Private IP và cấu hình VPC path cho workload test.
3. Cấp Cloud SQL Client cho service account.
4. Tạo database user password-based; xác minh kết nối private.
5. Nếu engine/instance hỗ trợ, bật IAM DB authentication, tạo IAM user và cấp quyền login.
6. Cấu hình Socket Factory với `ipTypes=PRIVATE` và `enableIamAuth=true`.
7. Chạy query đọc, ghi và transaction rollback/commit.
8. Tạo tải đồng thời cao hơn pool size để quan sát pending threads và acquire timeout.
9. Tăng replica test theo giới hạn đã định, xác nhận tổng connections không vượt budget.
10. Ngắt/khởi động lại database trong sandbox theo quy trình được phép; xác minh pool phục hồi.
11. Thu hồi IAM login role trong môi trường test và quan sát tác động với connection mới so với session đã mở.
12. Kiểm tra log không chứa password, token, key JSON hoặc connection string có secret.

### 13.3. Kiểm tra tổng connection bằng phép tính

Giả sử:

- Cloud Run max instances: 12.
- API pool: 5 connection mỗi instance.
- Worker tối đa 3 replica, mỗi replica 2 connection.
- Migration job tối đa 2 connection.
- Admin/monitoring cần 5 connection.

~~~text
API       = 12 × 5 = 60
Workers   =  3 × 2 =  6
Migration =             2
Admin     =             5
--------------------------
Tổng      =            73
~~~

So sánh 73 với connection capacity thực tế của Cloud SQL và headroom cần thiết. Nếu ngân sách còn 60, phải giảm pool, replica ceiling hoặc tách tải; không chờ đến khi production nhận lỗi `too many connections`.

## 14. Lỗi thường gặp và cách xử lý

| Triệu chứng | Lớp có khả năng lỗi | Hướng kiểm tra |
| --- | --- | --- |
| `Connection timed out` với Private IP | Network | VPC route, Cloud Run egress, firewall, IP type |
| `PERMISSION_DENIED` khi connector khởi tạo | Cloud IAM | ADC principal, Cloud SQL Client role, API |
| IAM login bị từ chối | IAM DB auth | Instance flag, `cloudsql.instances.login`, IAM DB user, engine support |
| Password authentication failed | Database authentication | DB username/password, secret version, DB user status |
| `too many connections` | Connection budget | Tổng replica × pool, workers, jobs, admin |
| Hikari `Connection is not available` | Pool saturation hoặc DB unreachable | Pending, active, acquire time, query latency, connector errors |
| Connection cũ hỏng sau failover | Pool lifecycle | Pool eviction, connection validation và retry |
| SQL permission denied | Database authorization | Schema/table grants, sequence privileges |
| Connection creation tăng đột biến khi scale out | Autoscaling | Replica ceiling, min idle, pool max và cold-start |
| Chạy local được nhưng Cloud Run lỗi private IP | Network identity khác nhau | VPC egress và service account của runtime |

Không sửa lỗi bằng cách tắt TLS, mở quyền Owner, chuyển private workload sang public ngoài chủ đích hoặc tăng pool vô hạn. Xác định đúng lớp lỗi trước khi thay cấu hình.

## 15. So sánh với AWS và Azure

Các nền tảng khác cũng có connection pool và private networking, nhưng cách cấp identity và kết nối managed database khác nhau:

| Khía cạnh | Google Cloud SQL | AWS RDS/Aurora | Azure Database |
| --- | --- | --- | --- |
| Java pool | HikariCP | HikariCP | HikariCP |
| Kết nối được quản lý | Cloud SQL Java Connector/Auth Proxy | TLS/CA, RDS Proxy tùy kiến trúc | TLS, proxy/service tương ứng |
| Workload identity | ADC/service account | IAM role | Managed identity/service principal |
| Private networking | VPC, Private IP, PSA/PSC | VPC/subnet/security group | VNet/private endpoint |
| DB IAM auth | Chỉ ở engine/phiên bản hỗ trợ | Tùy engine và IAM DB auth support | Tùy engine/dịch vụ và Entra support |
| Pool ở nhiều replica | Tổng Hikari pools trên workload | Tổng pools, có thể kết hợp RDS Proxy | Tổng pools, có thể kết hợp giải pháp pooling phù hợp |

Spring Data/JdbcTemplate, transaction abstraction và phần lớn logic repository có thể dùng chung khi engine SQL tương thích. Cấu hình identity, network, proxy, secret và database IAM authentication phải theo provider.

## 16. Bài tập thực hành

### Bài A — Tính connection budget

Một dịch vụ có 10 API replicas, mỗi replica pool tối đa 6; 4 worker replicas, mỗi replica pool 2; migration job cần 2 connection và admin cần 4 connection. Tính tổng connection tối đa. Sau đó giảm API pool xuống 4 và so sánh headroom.

### Bài B — Kiểm thử autoscaling

Triển khai Spring Boot lên Cloud Run với max instances được kiểm soát. Tăng tải trong sandbox, quan sát Hikari active/pending và Cloud SQL connection count. Xác định điểm mà pool/replica làm database gần giới hạn.

### Bài C — Private IP

Cấu hình Cloud SQL Private IP, VPC egress cho workload và `ipTypes=PRIVATE`. Chạy ứng dụng từ đúng runtime. Sau đó cố ý bỏ VPC route trong môi trường test để phân biệt timeout mạng với lỗi IAM.

### Bài D — IAM database authentication

Trên engine/phiên bản hỗ trợ, bật IAM DB auth, tạo IAM database user, cấp Cloud SQL Client và Instance User cho principal phù hợp. Kết nối bằng `enableIamAuth=true`, chạy query và kiểm tra SQL grants. Thu hồi quyền login trong sandbox và quan sát kết nối mới.

### Bài E — Pool recovery

Trong môi trường test, restart/failover Cloud SQL theo quy trình được phép. Quan sát connection bị loại, connection mới được tạo và retry nghiệp vụ. Dùng idempotency key để chứng minh không tạo bản ghi trùng.

### Bài F — Điều tra pool leak

Tạo một nhánh code test cố tình giữ connection lâu hơn bình thường. Bật leak detection tạm thời, đọc stack trace, sửa lifecycle và so sánh pending threads trước/sau.

### Câu hỏi tự kiểm tra

1. Vì sao `maximum-pool-size = 8` không có nghĩa toàn ứng dụng chỉ dùng 8 connection?
2. Làm thế nào tính tổng connection từ API replicas, worker và migration job?
3. Vì sao Cloud Run autoscaling có thể làm Cloud SQL hết connection dù từng pool nhỏ?
4. `minimum-idle` ảnh hưởng thế nào tới workload scale-to-zero?
5. `connection-timeout` khác `max-lifetime` ở điểm nào?
6. Vì sao tăng pool size có thể làm database quá tải hơn?
7. Cloud SQL Java Connector có tự quản lý HikariCP không?
8. `ipTypes=PRIVATE` có tự tạo VPC route không?
9. Private Service Access và Private Service Connect khác nhau thế nào?
10. Vì sao workload cần cả network path và Cloud SQL IAM role?
11. `roles/cloudsql.client` có cấp quyền SELECT bảng không?
12. IAM database authentication khác password-based DB auth ở bước nào?
13. Vì sao cần kiểm tra engine/phiên bản trước khi bật IAM DB authentication?
14. Điều gì xảy ra với session database đã mở khi IAM role bị thu hồi?
15. Vì sao retry transaction sau lỗi commit cần idempotency?
16. Khi nào nên cân nhắc proxy/pooler ngoài HikariCP?
17. Những metric nào giúp phân biệt Hikari pool exhaustion với Cloud SQL query saturation?

**Kết quả mong đợi:** người học thiết kế được connection budget cho toàn bộ Spring Boot workload, cấu hình HikariCP theo autoscaling và giới hạn Cloud SQL, thiết lập private network path đúng cách, sử dụng IAM database authentication khi engine hỗ trợ, đồng thời kiểm thử và giám sát khả năng phục hồi của pool.

