# Kết nối JDBC, connection pool và retry trong ứng dụng Java

Trong module **CLOUD_PROVIDERS_AZURE**, chúng ta khám phá hệ sinh thái Microsoft Azure từ subscription, resource group và Microsoft Entra ID đến mạng ảo, dịch vụ tính toán, lưu trữ và dữ liệu. Mục tiêu là biết triển khai, giám sát, bảo vệ và kiểm soát chi phí kiến trúc ứng dụng trên Azure. Tại chương **Cơ sở dữ liệu quan hệ**, bài học này đi sâu vào ba thành phần nền tảng khi Java kết nối với **Azure SQL Database**, **Azure Database for PostgreSQL** hoặc **Azure Database for MySQL**: **JDBC**, **connection pool** và **retry** có kiểm soát.

Hãy tưởng tượng một hệ thống Java Spring Boot triển khai thành 8 replicas trên AKS. Mỗi request cần tra cứu đơn hàng rồi cập nhật trạng thái. Khi một cơ sở dữ liệu Azure thực hiện failover, các kết nối hiện tại có thể mất hiệu lực; đồng thời mỗi replica có connection pool và sẽ cố kết nối lại. Nếu ứng dụng tạo kết nối cho từng request, retry vô hạn hoặc cấu hình pool quá lớn, sự cố ban đầu có thể biến thành bão kết nối, hết connection limit, timeout kéo dài và thậm chí ghi dữ liệu lặp.

Sau bài học, bạn có thể:

- Giải thích **JDBC driver**, `DataSource`, `Connection`, `PreparedStatement`, transaction và `SQLException`.
- Xây dựng JDBC URL phù hợp cho Azure SQL, Azure PostgreSQL, Azure MySQL; bắt buộc kiểm tra TLS, DNS và mạng.
- Dùng **HikariCP** hoặc Spring Boot connection pool và biết phân biệt **pool timeout**, **query timeout**, **socket timeout**.
- Ước lượng tổng số connections khi scale nhiều replicas, tránh pool exhaustion/leak và overload database.
- Phân biệt authentication bằng **Microsoft Entra ID/managed identity** với SQL username/password; thiết kế token refresh đúng cho pool.
- Nhận diện lỗi kết nối tạm thời, serialization/deadlock, throttling và lỗi không nên retry.
- Retry **đúng phạm vi giao dịch**, có exponential backoff + jitter, giới hạn thời gian, idempotency và kiểm soát kết quả commit không chắc chắn.
- Theo dõi pool metrics, DB metrics, tracing, alerts và thiết kế test failover/chaos.

## 1. Vì sao kết nối cơ sở dữ liệu là bài toán vận hành?

Ứng dụng dùng Azure managed relational database vẫn có các thành phần mạng và runtime:

```text
Mobile/Web client
       |
       v
API Gateway / Ingress
       |
       v
Java API (8 replicas)
       |
       +-- Replica 1: HikariCP [0..10 connections]
       +-- Replica 2: HikariCP [0..10 connections]
       +-- ...
       +-- Replica 8: HikariCP [0..10 connections]
       |
       v
VNet / Private DNS / TLS / Azure Firewall theo thiết kế
       |
       v
Azure SQL Database hoặc Azure Database for PostgreSQL/MySQL
       |
       +-- Max connections / compute / IOPS / locks
       +-- Failover / maintenance / scaling events
```

Mỗi connection có **chi phí trên cả Java process và database server**: socket, trạng thái session, bộ nhớ, khả năng tranh chấp tài nguyên. Connection pool giúp tái sử dụng những connections đang hoạt động nhưng không làm backend có capacity vô hạn.

### 1.1. Ba loại sự cố cần phân biệt

| Sự cố | Ví dụ | Hướng xử lý |
|---|---|---|
| **Không tạo được connection** | Sai mật khẩu, DNS lỗi, firewall/private endpoint, connection limit | Xác định auth/network/capacity; retry **chỉ khi tạm thời** |
| **Có connection nhưng query lỗi** | Deadlock, lock timeout, sai SQL, unique constraint | Phân loại SQLState/vendor code; có thể retry **cả transaction** khi an toàn |
| **Commit không rõ thành công hay thất bại** | DB đã commit nhưng TCP bị cắt trước khi client nhận ACK | Không blind retry; dùng idempotency key/đối chiếu trạng thái |

**Retry không sửa được mật khẩu sai, query syntax sai hay quyền database không đủ.** Những lỗi cấu hình phải được phát hiện rõ và báo cáo, thay vì liên tục mở kết nối mới.

### 1.2. “Managed” không có nghĩa connection không thể đứt

Azure quản lý nhiều hoạt động như cập nhật hệ điều hành, vá lỗi hạ tầng, backup và một số cơ chế HA/failover theo dịch vụ/tier. Tuy vậy, network connection là tài nguyên có trạng thái và có thể bị reset khi failover, maintenance, autoscale hoặc sự cố mạng.

Ứng dụng cần thiết kế để **recover**: bỏ connection hỏng, tạo connection mới, retry được những thao tác an toàn và báo hiệu nhanh khi không còn khả năng phục vụ request.

## 2. JDBC và vòng đời một thao tác SQL

**Java Database Connectivity (JDBC)** là API Java chuẩn để truy cập database qua JDBC driver phù hợp. Một ứng dụng có thể dùng JDBC trực tiếp, Spring JDBC, JPA/Hibernate hoặc framework ORM khác; bên dưới thường vẫn sử dụng driver, connections và transactions.

```text
Service method
      |
      v
DataSource (thường là pool)
      |
      v
JDBC Connection
      |
      +-- PreparedStatement / ResultSet
      |
      +-- Transaction: auto-commit hoặc begin/commit/rollback
      |
      v
JDBC driver <---- TLS socket ----> Azure relational database
```

### 2.1. Những interface quan trọng

| Thành phần | Vai trò | Lưu ý |
|---|---|---|
| `Driver` | Thực thi wire protocol với SQL Server/PostgreSQL/MySQL | Mỗi loại database dùng driver phù hợp |
| `DataSource` | Cung cấp `Connection`, có thể do pool triển khai | Ứng dụng nên inject/reuse một DataSource |
| `Connection` | Session/transaction và trạng thái kết nối | **Không** dùng chung một Connection giữa nhiều threads |
| `PreparedStatement` | Thực thi SQL parameterized | Chống SQL injection khi dùng placeholders đúng |
| `ResultSet` | Dữ liệu kết quả truy vấn | Đóng tài nguyên đúng vòng đời |
| `SQLException` | Thông tin SQLState, vendor error code, cause | Không mọi SQLException đều transient |
| `commit` / `rollback` | Kết thúc transaction | Hiểu phạm vi unit of work và lỗi khi commit |

**`Connection.close()` với connection pool thường là trả connection về pool**, không phải phá TCP socket ngay lập tức. Nếu code quên close, pool cạn dù database còn rảnh.

### 2.2. Ví dụ JDBC dùng PreparedStatement

Ví dụ sau **chỉ đọc** bản ghi, không chứa hardcoded credentials; `DataSource` được cấu hình riêng:

```java
import javax.sql.DataSource;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.Optional;

public final class OrderReader {
    private final DataSource dataSource;

    public OrderReader(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public Optional<String> findStatus(String orderId) throws SQLException {
        String sql = "SELECT status FROM orders WHERE order_id = ?";
        try (Connection conn = dataSource.getConnection();
             PreparedStatement ps = conn.prepareStatement(sql)) {
            ps.setString(1, orderId);
            ps.setQueryTimeout(5); // ví dụ: giây, tùy driver hỗ trợ
            try (ResultSet rs = ps.executeQuery()) {
                return rs.next()
                        ? Optional.ofNullable(rs.getString("status"))
                        : Optional.empty();
            }
        }
    }
}
```

`try-with-resources` đóng `ResultSet`/`PreparedStatement` rồi trả `Connection` về pool ngay cả khi có exception. Chỉ đóng tài nguyên **do mình sở hữu**: nếu framework `@Transactional` đang quản lý Connection thì tránh tự can thiệp transaction/close sai cách ngoài phạm vi framework.

### 2.3. PreparedStatement không tự giải quyết mọi vấn đề

Parameterized SQL giúp dữ liệu đầu vào không bị coi là cú pháp SQL trong các vị trí bindable. Nhưng những phần như **tên bảng/tên cột/order direction** thường không thể bind bằng `?`; nếu phải chọn động, hãy dùng whitelist an toàn. Dữ liệu `orderId` vẫn cần validation về độ dài/kiểu và object-level authorization.

## 3. Chọn JDBC driver và URL theo dịch vụ Azure

**Không có một JDBC driver dùng chung** cho cả SQL Server, PostgreSQL và MySQL. Mỗi driver dùng giao thức, cú pháp connection URL, cơ chế auth và SQLState/vendor codes riêng.

| Azure database | JDBC driver thường dùng | Prefix URL |
|---|---|---|
| **Azure SQL Database** (SQL Server engine) | Microsoft JDBC Driver for SQL Server, `com.microsoft.sqlserver:mssql-jdbc` | `jdbc:sqlserver://` |
| **Azure Database for PostgreSQL – Flexible Server** | PostgreSQL JDBC Driver, `org.postgresql:postgresql` | `jdbc:postgresql://` |
| **Azure Database for MySQL – Flexible Server** | MySQL Connector/J, `com.mysql:mysql-connector-j` | `jdbc:mysql://` |

Các phiên bản driver nên được **pin theo bản ổn định được kiểm thử với JDK/engine** của dự án. Không dùng driver JDBC không được hỗ trợ cho phiên bản Java đang chạy, không tải JAR ngẫu nhiên từ nguồn không tin cậy.

### 3.1. JDBC URL cho Azure SQL

Ví dụ **minh họa**:

```text
jdbc:sqlserver://orders-sql.database.windows.net:1433;databaseName=ordersdb;encrypt=true;trustServerCertificate=false;loginTimeout=30;
```

Giải thích:

- `orders-sql.database.windows.net` là hostname máy chủ Azure SQL giả lập.
- `1433` là cổng thường dùng cho SQL Server/TDS.
- `databaseName=ordersdb` chọn database.
- `encrypt=true` bật mã hóa.
- `trustServerCertificate=false` yêu cầu xác minh server certificate thay vì bỏ qua kiểm tra.
- `loginTimeout=30` ảnh hưởng thời gian login theo driver; **không thay** thời hạn toàn HTTP request.

Trong production, kiểm tra certificate hostname validation và trust store của JDK/container. Không đặt `trustServerCertificate=true` để “sửa” lỗi trust chain; phải sửa CA trust, hostname, route hoặc cấu hình TLS.

### 3.2. JDBC URL cho Azure PostgreSQL Flexible Server

```text
jdbc:postgresql://orders-pg.postgres.database.azure.com:5432/ordersdb?sslmode=verify-full
```

`verify-full` yêu cầu TLS và hostname verification theo cơ chế PostgreSQL JDBC driver. Container/JVM phải tin cậy CA chain của server. Nếu driver báo lỗi certificate, kiểm tra CA/trust store và DNS đúng hostname, **không chuyển sang `sslmode=disable`** trong production.

Port `5432` là mặc định PostgreSQL; không đồng nghĩa server phải public. Với private access/private DNS, tên hostname cần phân giải tới IP riêng theo topology Azure đã triển khai.

### 3.3. JDBC URL cho Azure MySQL Flexible Server

```text
jdbc:mysql://orders-mysql.mysql.database.azure.com:3306/ordersdb?sslMode=VERIFY_IDENTITY
```

`sslMode=VERIFY_IDENTITY` yêu cầu kiểm tra TLS và danh tính hostname trong các phiên bản MySQL Connector/J hỗ trợ. `3306` là cổng thông thường. Khi đổi driver/JDK, xác minh lại các tên tham số TLS và trust store thay vì copy option từ PostgreSQL sang MySQL.

### 3.4. URL và identity được cấu hình riêng

Một JDBC URL có thể được lưu trong configuration không bí mật, nhưng **username/password, access token hoặc private key không được viết trong Git**. Cần tách:

```text
DB_JDBC_URL   -> URL tới database, gồm các tùy chọn TLS
DB_USERNAME   -> tài khoản DB theo mô hình đã chọn
DB_PASSWORD   -> secret từ nguồn quản lý bí mật (khi dùng password auth)
```

Trong Azure, có thể dùng Microsoft Entra authentication/managed identity theo dịch vụ/driver hỗ trợ. Khi dùng identity-based auth, cách lấy và refresh token cho JDBC pool cần thiết kế riêng; sẽ được trình bày ở phần sau.

## 4. Mạng, Private Endpoint, DNS và TLS trước khi debug JDBC

Một lỗi `Connection refused`, timeout hoặc TLS handshake thường bắt đầu từ **đường mạng/certificate**, không phải do thiếu `SELECT` permission trong SQL.

```text
AKS / Azure App Service / VM / Container Apps
                  |
                  | outbound route từ runtime
                  v
               VNet
                  |
          DNS resolver / Private DNS
                  |
          Firewall / NSG / UDR / NAT
                  |
                  v
        Azure database endpoint
                  |
                  v
            TLS + DB login
```

Để kiểm tra có thứ tự:

1. Runtime phân giải đúng **FQDN** hay không? Private DNS link/resolver có phù hợp?
2. Cổng cần dùng (Azure SQL 1433, PostgreSQL 5432, MySQL 3306 theo thiết kế) có reachable?
3. Azure DB networking/firewall đang public hay private? Mạng nguồn có được phép?
4. Proxy/route/NSG/firewall có chặn kết nối không?
5. TLS handshake có tin cậy certificate và khớp hostname không?
6. Sau khi mạng/TLS hoạt động mới chẩn đoán **database authentication và authorization**.

**Đừng bật public access của database cho toàn Internet, tắt TLS hoặc dùng admin account để khắc phục timeout chưa xác định.** Một kết nối thành công từ laptop không chứng minh pod trong AKS có cùng DNS/route/identity.

## 5. Connection pool là gì?

Mỗi lần mở kết nối database có chi phí **DNS, TCP/TLS handshake, authentication, tạo session** và tài nguyên server. Nếu mỗi request Java tạo connection mới và đóng kết nối vật lý ngay, ứng dụng có thể gặp latency và connection churn cao. **Connection pool** quản lý tập connections để tái sử dụng, hạn chế số kết nối đồng thời và cung cấp cơ chế kiểm tra/loại connection hỏng.

```text
Thread A ----\
Thread B -----+--> HikariCP DataSource
Thread C ----/         |
                       +-- Idle connection #1
                       +-- Busy connection #2
                       +-- Busy connection #3
                       +-- ... tới maximumPoolSize
                       |
                       +-- Khi mọi connection đều bận:
                           request chờ tối đa connectionTimeout
```

Khi code gọi `getConnection()`, pool cho mượn một connection có sẵn hoặc tạo mới nếu chưa đạt giới hạn. Khi code `close()`, connection trở về pool. Nếu hết connections và thời gian chờ đạt giới hạn, pool ném exception. Đây là dấu hiệu **pool acquisition failure**, không nhất thiết là database đã chết.

### 5.1. Một connection không phải một thread

Không dùng chung cùng một `java.sql.Connection` giữa các luồng xử lý đồng thời. Connection có transaction state và session properties; chia sẻ sai cách dễ gây commit chéo, race conditions hoặc leak dữ liệu. Pool bảo đảm cho mượn một connection đến một borrower tại một thời điểm khi dùng đúng API.

### 5.2. Pool không thay database capacity

Tăng `maximumPoolSize` không tạo CPU/IOPS của database. Khi database đã bão hòa, thêm sessions có thể làm **query latency tăng**, locks tranh chấp hơn và throughput giảm.

Lựa chọn pool size nên dựa trên:

- Số lượng truy vấn đồng thời **thật sự cần** trên mỗi replica.
- Thời gian giữ connection trung bình/p95.
- Connection limit và compute tier của Azure database.
- Số replicas tối đa của Java, background jobs, BI/admin/maintenance clients.
- Sự cạnh tranh locks, SQL query plans, DB CPU, memory và I/O.

Pool size **không nên lấy bằng số HTTP threads** theo mặc định. HTTP request đôi khi làm nhiều công việc không cần connection; kết nối chỉ nên được giữ đúng trong khoảng thao tác SQL cần thiết.

## 6. Cấu hình HikariCP trong Java

**HikariCP** là một JDBC connection pool phổ biến, được Spring Boot sử dụng mặc định trong nhiều cấu hình JDBC/JPA phù hợp. Ví dụ tiếp theo chọn **Azure Database for PostgreSQL Flexible Server** để minh họa; cách thiết lập pool có thể dùng tương tự với Azure SQL/MySQL sau khi đổi driver, URL và các tham số xác thực.

### 6.1. Dependencies Maven

```xml
<dependencies>
  <dependency>
    <groupId>com.zaxxer</groupId>
    <artifactId>HikariCP</artifactId>
    <version>REPLACE_WITH_TESTED_HIKARI_VERSION</version>
  </dependency>
  <dependency>
    <groupId>org.postgresql</groupId>
    <artifactId>postgresql</artifactId>
    <version>REPLACE_WITH_TESTED_PGJDBC_VERSION</version>
  </dependency>
</dependencies>
```

Các `REPLACE_WITH...` là **placeholder phiên bản**, phải thay bằng bản đã được kiểm thử với JDK và database engine trước khi build. Với Spring Boot, dùng BOM/dependency management đồng bộ thay vì tự ép nhiều phiên bản xung đột.

### 6.2. Tạo một DataSource chia sẻ

```java
import com.zaxxer.hikari.HikariConfig;
import com.zaxxer.hikari.HikariDataSource;

public final class DatabasePools {
    private DatabasePools() {}

    public static HikariDataSource create() {
        HikariConfig config = new HikariConfig();

        config.setPoolName("orders-write-pool");
        config.setJdbcUrl(require("DB_JDBC_URL"));
        config.setUsername(require("DB_USERNAME"));
        config.setPassword(require("DB_PASSWORD"));

        config.setMaximumPoolSize(10);
        config.setMinimumIdle(2);
        config.setConnectionTimeout(3_000);       // ms: chờ pool cho mượn
        config.setValidationTimeout(1_000);       // ms: kiểm tra connection
        config.setIdleTimeout(300_000);           // ms: idle quá lâu
        config.setMaxLifetime(1_500_000);         // ms: 25 phút
        config.setKeepaliveTime(120_000);         // ms: 2 phút
        config.setLeakDetectionThreshold(20_000); // ms: chẩn đoán, cân nhắc tắt

        return new HikariDataSource(config);
    }

    private static String require(String envName) {
        String value = System.getenv(envName);
        if (value == null || value.isBlank()) {
            throw new IllegalStateException("Missing " + envName);
        }
        return value;
    }
}
```

**Chú ý:** `setPassword` minh họa **password authentication** cho lab, không có nghĩa đây luôn là phương án ưu tiên production. Lấy password từ secret store hoặc chuyển sang Entra/managed identity khi dịch vụ/driver hỗ trợ; không đưa giá trị secret vào log, image, Git hay config map công khai. Cách tích hợp token authentication với pool được trình bày ở phần sau.

Đối với `HikariDataSource` được tạo một lần ở application startup, framework cần **đóng pool khi shutdown**; không tạo/đóng pool ở mỗi HTTP request. Với Java CLI/demo, dùng:

```java
try (HikariDataSource ds = DatabasePools.create()) {
    OrderReader reader = new OrderReader(ds);
    System.out.println(reader.findStatus("ORD-1042"));
}
```

Mỗi request chỉ mượn và trả một `Connection` từ `ds`. Việc khởi tạo pool có thể mở connections ngay hoặc khi cần, tùy config và trạng thái DB.

### 6.3. Ý nghĩa tham số HikariCP

| HikariCP property | Ý nghĩa | Hậu quả nếu sai |
|---|---|---|
| `maximumPoolSize` | Số connection vật lý tối đa của pool | Quá lớn gây bão sessions; quá nhỏ dẫn đến wait |
| `minimumIdle` | Số connections idle mong muốn | Đặt cao tăng footprint, nhất là nhiều replicas |
| `connectionTimeout` | Tối đa chờ mượn connection từ pool | Quá dài khiến HTTP threads xếp hàng; quá ngắn báo lỗi khi spike |
| `validationTimeout` | Ngưỡng kiểm tra connection có hoạt động | Quá dài làm chậm acquisition; cần tương thích connectionTimeout |
| `idleTimeout` | Thời gian idle trước khi pool có thể thu hồi bớt connections trên minIdle | Không hiệu quả như kỳ vọng khi pool cố định |
| `maxLifetime` | Vòng đời tối đa của connection trong pool | Nên nhỏ hơn giới hạn vòng đời kết nối do mạng/DB áp dụng nếu biết |
| `keepaliveTime` | Kiểm tra kết nối idle định kỳ theo điều kiện Hikari | Không phải keepalive cho mọi query/bất kỳ lỗi |
| `leakDetectionThreshold` | Ngưỡng cảnh báo connection bị giữ quá lâu | Có thể tạo false positive cho transaction dài |
| `initializationFailTimeout` | Hành vi fail-fast khi tạo/kiểm tra connection lúc khởi tạo | Cân nhắc với dependency availability và lifecycle app |

Các mốc 10 connections, 3 giây, 25 phút trong ví dụ chỉ là **giá trị lab để minh họa**, không phải cấu hình tối ưu cho mọi cơ sở dữ liệu Azure. `maxLifetime` không tạo một timeout tuyệt đối làm ngắt query đang dùng giữa chừng theo cách đơn giản; Hikari chủ yếu retire connection khi nó trở về trạng thái có thể thu hồi.

### 6.4. HikariCP không phải database connection proxy

Pool thường nằm **trong JVM** của từng app instance. Nếu có 12 pods, sẽ có **12 pools riêng** chứ không tự dùng chung một pool toàn cluster. Những giải pháp như PgBouncer (PostgreSQL) hoặc các connection proxies khác có thể được xem xét riêng, nhưng có ràng buộc session/transaction mode, prepared statements và authentication phải kiểm chứng. Không xem proxy là giải pháp miễn phí cho truy vấn thiếu index hoặc transaction giữ lock quá lâu.

## 7. Tính tổng connections khi autoscale

Một lỗi thiết kế phổ biến: cấu hình `maximumPoolSize=30` vì “mỗi JVM chịu được 30 threads” mà quên số replicas.

Ước lượng trên:

\[
Connections_{potential}=Replicas_{max}\times PoolsPerReplica\times MaximumPoolSize
\]

Ví dụ:

```text
Max AKS replicas = 20
Số write pool mỗi pod = 1
Max pool size = 10

Tối đa từ Java API ≈ 20 × 1 × 10 = 200 connections
```

Nếu DB tier chỉ cho khoảng 120 connections hiệu dụng và còn 20 connections dự phòng cho quản trị, ETL, migration, health checks cùng jobs khác, 200 là cấu hình gây rủi ro. Không nhất thiết mọi connection luôn được mở, nhưng **khi scale và tải tăng đồng thời** đúng lúc DB có ít capacity nhất, mức cực đại này có thể bị chạm.

### 7.1. Một công thức dự toán có dự phòng

Với ví dụ giả định:

```text
Giới hạn hiệu dụng của DB        = 120
Reserve hệ thống/operations      = 20
Các clients khác                 = 20
Max replicas Java                = 20

Ngân sách pool mỗi replica = floor((120 - 20 - 20) / 20) = 4
```

Đây là **bài toán capacity planning sơ bộ**, không phải đảm bảo performance ở 4 connections. Thông số hiệu dụng còn chịu ảnh hưởng của service tier, session overhead, DB parallelism, replication và connection types. Phải **load test** để chọn pool size theo throughput và latency thật.

### 7.2. Ba nguồn làm vượt dự toán

- **Rolling deployment:** pods cũ và mới cùng chạy một lúc, tổng connections có thể vượt `replicas` mục tiêu; tính đến `maxSurge` hoặc cơ chế scale tương tự.
- **Nhiều DataSources:** read pool, write pool, migration/admin pool hoặc multi-tenant pools nhân tổng số connections.
- **Background workers:** scheduled jobs, outbox relay, ETL, BI tools hoặc serverless functions có thể tăng connections đồng thời.

Với scale-out nhanh, kiểm soát **startup burst**, minIdle và max replica. Không tạo 100 connections idle từ mỗi pod khi DB chỉ cần vài query đồng thời.

### 7.3. Tại sao ít connections đôi khi nhanh hơn?

Nếu một query tốn 50 ms CPU/IO và database chỉ có capacity xử lý hiệu quả một số requests đồng thời, quá nhiều clients đẩy vào DB gây contention; một hàng đợi bounded trước database đôi khi cho latency p95 tốt hơn. Đây là lý do cần đo:

```text
request latency
pool acquisition wait
DB query duration
DB CPU/IO
lock wait / deadlocks
active connections
error / timeout rates
```

Tăng pool size chỉ có ý nghĩa khi **pool chính là nút thắt thực sự** và DB có capacity tiếp nhận. Nếu DB CPU đã 95% hoặc lock waits tăng, nên tối ưu SQL/index/transactions trước.

## 8. Các loại timeout không được nhầm lẫn

Một request có thể trải qua nhiều thời gian chờ khác nhau:

```text
HTTP request deadline (ví dụ 5s)
    |
    +-- Pool acquisition (connectionTimeout, ví dụ 1s)
    |
    +-- TCP connect + TLS/login (driver timeouts)
    |
    +-- SQL execution (statement/query timeout)
    |
    +-- ResultSet streaming / socket read
    |
    +-- COMMIT / ROLLBACK
```

### 8.1. Phân biệt ý nghĩa

| Timeout | Kiểm soát | Ví dụ hậu quả |
|---|---|---|
| **HTTP deadline** | Tổng thời gian caller chờ API | Caller ngắt kết nối, server có thể vẫn đang chạy nếu không cancel |
| **Hikari `connectionTimeout`** | Thời gian chờ pool cho mượn connection | Pool exhausted khi nhiều threads dùng hết |
| **Connect timeout** | Thiết lập TCP connection tới database | DNS/route/firewall hoặc server không reachable |
| **Login timeout** | Quá trình xác thực DB theo driver | Entra token/password/DB login chậm hoặc lỗi |
| **JDBC query/statement timeout** | Thời gian thực thi query theo driver | Query bị hủy theo semantics driver/server |
| **Socket/network timeout** | Hoạt động đọc/ghi mạng ở driver | Có thể xảy ra giữa query hoặc COMMIT |
| **Transaction timeout** | Giới hạn unit of work theo framework | Tránh giữ connection/locks quá lâu |

**Không suy ra rằng query timeout luôn rollback toàn bộ transaction.** Tùy database và driver, connection/transaction có thể ở trạng thái cần rollback hoặc không còn sử dụng được. Với PostgreSQL, một lỗi statement trong transaction có thể khiến transaction bị đánh dấu failed cho đến rollback; với SQL Server, ảnh hưởng phụ thuộc lỗi và transaction settings. Luôn xử lý rollback và phân loại exception rõ.

### 8.2. Chọn deadline có hệ thống

Ví dụ một API có deadline 5 giây:

```text
HTTP deadline          5.0s
Pool acquisition       0.8s
SQL statement          2.0s
Ứng dụng/parsing       0.3s
Margin retry/network   còn lại
```

Đây chỉ là **ngân sách minh họa**, không phải tổng các timeout độc lập được phép tiêu hết ở mọi lần retry. Retry ba lần mỗi lần query timeout 2 giây sẽ vượt deadline 5 giây nếu không kiểm soát deadline toàn yêu cầu. Cần truyền/duy trì **time budget** xuyên các lớp.

### 8.3. Query bị client timeout không đồng nghĩa work chưa commit

Khi xảy ra lỗi socket sau khi gửi `COMMIT`, server có thể đã commit nhưng response không quay lại client. **Không khẳng định transaction rollback chỉ vì client nhận timeout.** Với thao tác ghi/thu tiền/đặt hàng, cần idempotency key và cách xác minh kết quả cuối thay vì lặp lại mù quáng.

## 9. Spring Boot và cấu hình pool bằng application.yml

Spring Boot có thể tự cấu hình một `DataSource` dựa trên JDBC driver và pool implementation đang có. Với ứng dụng Spring Boot sử dụng HikariCP, có thể cấu hình như sau:

```yaml
spring:
  datasource:
    url: "${DB_JDBC_URL}"
    username: "${DB_USERNAME}"
    password: "${DB_PASSWORD}"
    hikari:
      pool-name: orders-write-pool
      maximum-pool-size: 10
      minimum-idle: 2
      connection-timeout: 3000
      validation-timeout: 1000
      idle-timeout: 300000
      max-lifetime: 1500000
      keepalive-time: 120000

management:
  endpoints:
    web:
      exposure:
        include: "health,info,prometheus"
```

Đoạn `${...}` trong template được hiểu là **Spring property placeholders**; ứng dụng đọc environment variables thực tế khi khởi động. Không đưa password thật vào `application.yml` được commit. Khi cấu hình môi trường production, secrets phải đến từ nguồn có quyền truy cập hẹp; việc đặt secret trong environment variable vẫn đòi hỏi kiểm soát quyền đọc cấu hình, pod inspection và dumps.

### 9.1. Một DataSource cấp ứng dụng

```java
import javax.sql.DataSource;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public final class OrdersRepository {
    private final JdbcTemplate jdbc;

    public OrdersRepository(DataSource dataSource) {
        this.jdbc = new JdbcTemplate(dataSource);
    }

    public int updateStatus(String orderId, String newStatus) {
        return jdbc.update(
                "UPDATE orders SET status = ? WHERE order_id = ?",
                newStatus, orderId);
    }
}
```

Spring tự quản lý `DataSource` và connections theo context và transaction manager. Không tạo `new HikariDataSource` bên trong mỗi lần gọi `updateStatus`. `JdbcTemplate` đơn giản hóa đóng tài nguyên JDBC; vẫn phải thiết kế giao dịch và retry đúng ranh giới.

### 9.2. `@Transactional` chỉ bảo vệ một database transaction

```java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderApplicationService {
    private final OrdersRepository orders;

    public OrderApplicationService(OrdersRepository orders) {
        this.orders = orders;
    }

    @Transactional
    public void markPaid(String orderId) {
        int updated = orders.updateStatus(orderId, "PAID");
        if (updated != 1) {
            throw new IllegalArgumentException("Order not found");
        }
    }
}
```

Ví dụ minh họa transaction boundary trong Spring khi transaction manager được cấu hình đúng. `@Transactional` **không tự đảm bảo atomicity** giữa SQL Database và các dịch vụ ngoài như Service Bus, payment provider hoặc REST API.

Một lỗi phổ biến là gọi method `@Transactional` qua **self-invocation trong cùng object** rồi tưởng proxy luôn áp dụng transaction. Cần hiểu transaction management của framework, propagation, isolation và method visibility theo version.

### 9.3. Không mở transaction rồi gọi HTTP chậm

```text
BEGIN DB transaction
  SELECT order FOR UPDATE
  HTTP call Payment API (chờ 30 giây)
  UPDATE order
COMMIT
```

Đây là anti-pattern: connection và có thể cả row locks bị giữ trong lúc chờ mạng. Nên tách workflow thành các bước ngắn, dùng trạng thái bền vững, outbox/saga hoặc idempotent external API calls. **Transaction càng ngắn, cơ hội pool bị cạn và lock contention càng thấp**.

## 10. Authentication: password hay Microsoft Entra managed identity?

Azure relational database có thể hỗ trợ các cách xác thực khác nhau theo dịch vụ/tier/configuration:

| Phương án | Ưu điểm | Lưu ý |
|---|---|---|
| **DB username/password** | Tương thích rộng với JDBC driver | Cần secret store, rotation, least privilege và không hard-code |
| **Microsoft Entra ID authentication** | Quản lý principal và quyền qua Entra theo dịch vụ hỗ trợ | Cần cấu hình DB principal/role và driver/token |
| **Managed identity / AKS Workload Identity** | Workload không phải giữ client secret lâu dài | Entra access token có hạn, driver/pool phải hỗ trợ refresh đúng |
| **Integrated workload credentials** | Dùng cơ chế Azure Identity/driver cấp token theo môi trường | Phụ thuộc JDK, JDBC driver version và cloud/tenant |

**Một managed identity có Azure RBAC Contributor trên tài nguyên database không tự có quyền SELECT trong database.** Phải cấu hình database-level authentication principal và GRANT/roles phù hợp theo cơ chế của Azure SQL, PostgreSQL hoặc MySQL. RBAC quản lý Azure resource và SQL data-plane permissions là hai phạm vi riêng.

### 10.1. Azure SQL JDBC và Entra authentication

Microsoft JDBC Driver for SQL Server có các chế độ Entra authentication được hỗ trợ theo phiên bản, ví dụ `ActiveDirectoryManagedIdentity`, `ActiveDirectoryDefault` hoặc token-based auth qua API phù hợp. Ví dụ **connection string khái niệm** dùng identity của runtime:

```text
jdbc:sqlserver://orders-sql.database.windows.net:1433;databaseName=ordersdb;encrypt=true;trustServerCertificate=false;authentication=ActiveDirectoryManagedIdentity;
```

Chế độ/thuộc tính cụ thể của **user-assigned identity**, dependency của driver và cách chọn client ID khác nhau theo phiên bản. Không giả định mọi phiên bản `mssql-jdbc` đều nhận cùng cú pháp `user`/`msiClientId` hoặc tự kích hoạt federation của AKS. **Xác nhận đúng driver version và môi trường**, cấp DB principal cho identity và thử kết nối trước khi áp dụng vào Hikari pool.

### 10.2. PostgreSQL/MySQL với Entra access token

Các cơ chế Microsoft Entra authentication trên PostgreSQL/MySQL có thể sử dụng **access token làm credential đăng nhập** theo tính năng đang được bật. Một token có **expiration**; nếu tạo HikariCP với password cố định bằng một access token nhận lúc startup, các **connections mới** sau khi token hết hạn có thể thất bại trong khi sessions cũ vẫn tồn tại.

Thiết kế an toàn cần:

1. Xác định dịch vụ/driver và cách xác thực Entra được hỗ trợ.
2. Cấp principal/quyền database thích hợp cho managed identity.
3. Lấy token có audience/scope phù hợp với **đúng Azure database service**.
4. Tích hợp **token refresh trên mỗi lần mở physical connection** hoặc cơ chế plugin/callback được driver/pool hỗ trợ.
5. Không lưu access token trong log, JVM dumps, config file hay dùng một token bất biến làm password suốt nhiều giờ.
6. Load test tình huống token hết hạn, failover, pool recycle và nhiều replicas khởi động đồng thời.

Đừng copy một ví dụ `dataSource.setPassword(token)` chạy lúc startup rồi kết luận nó production-ready; hãy kiểm chứng cơ chế renew khi pool tạo connection mới.

### 10.3. Một checklist quyền database

- Entra admin và các tùy chọn authentication đã được cấu hình theo dịch vụ Azure.
- Managed identity/service principal thực sự có DB user/role tương ứng.
- Tài khoản chỉ có `SELECT/INSERT/UPDATE` ở bảng/schema cần thiết; hạn chế quyền `ALTER`/`DROP` trong runtime.
- User migration/schema admin tách khỏi runtime application.
- Network/DNS/TLS và Entra token endpoint đều reachable khi workload cần token.
- Đã thử secret/token rotation, principal change và failover.

### 10.4. Tách quyền migration và runtime

Chạy Flyway/Liquibase migrations thường cần `CREATE/ALTER`; ứng dụng chỉ đọc/ghi đơn hàng không cần quyền đó. Nếu cả hai dùng chung credential admin, một SQL injection hoặc lỗi code có thể làm thay đổi schema.

Nên dùng **migration identity** riêng được vận hành qua CI/CD có approval, còn runtime DataSource dùng principal quyền hẹp, nhất là production.

## 11. Phân loại lỗi JDBC trước khi retry

`SQLException` có nhiều thông tin:

- `getSQLState()`: mã trạng thái SQL theo lớp lỗi.
- `getErrorCode()`: mã lỗi riêng do database/driver cung cấp.
- `getNextException()`, `getCause()`: chuỗi lỗi có thể chỉ ra nguyên nhân gốc.
- Các subtype như `SQLTransientException`, `SQLNonTransientException`, `SQLRecoverableException` khi driver dùng chúng.

**Không thể quyết định “mọi SQLException đều retry được”.** Cùng một triệu chứng timeout có thể là lỗi khi mở connection trước transaction, lỗi trong khi update, hay lỗi sau khi lệnh COMMIT được gửi – và mức an toàn khi retry khác nhau.

### 11.1. SQLState là gợi ý, không phải chính sách đầy đủ

| SQLState / mã | Thường mang ý nghĩa | Retry như thế nào? |
|---|---|---|
| Lớp **`08`** | Connection exception | Có thể retry *kết nối mới*; nếu đã gửi ghi/commit thì phải đánh giá tính không chắc chắn |
| **`40001`** | Serialization failure/transaction rollback trong một số engines | Retry **cả transaction** mới sau rollback, có giới hạn |
| **`40P01`** (PostgreSQL) | Deadlock detected | Retry cả transaction đã rollback, với backoff |
| **1205** (SQL Server vendor error) | Deadlock victim | Retry transaction mới sau khi xác nhận DB đã hủy transaction |
| **1213** (MySQL vendor error) | Deadlock | Retry transaction mới khi driver/engine báo rollback phù hợp |
| **40501** (Azure SQL vendor error) | Một dạng throttling/busy theo ngữ cảnh | Retry có backoff ở phạm vi an toàn, theo hướng dẫn dịch vụ |
| **40613 / 40197** (Azure SQL vendor errors) | DB tạm thời không sẵn sàng/lỗi xử lý theo tình huống | Có thể retry kết nối/thao tác idempotent, nhưng kiểm tra giai đoạn transaction |
| **23505** (PostgreSQL) | Unique constraint violation | Thường lỗi nghiệp vụ/duplicate; không retry liên tục |
| **28xxx** | Invalid authorization/authentication ở một số engines | Sửa credential/DB principal/role; không blind retry |
| **42xxx** | Syntax/object/authorization-related SQL errors tùy engine | Thường sửa schema/query/quyền, không retry đơn thuần |

Các mã ở bảng là **ví dụ thường gặp, không phải danh sách chuẩn hóa cho mọi driver**. MySQL, PostgreSQL và SQL Server có cách ánh xạ lỗi riêng. Cần kiểm tra tài liệu driver/engine và logs thực tế trước khi áp whitelist retry production.

### 11.2. Những lỗi nên fail fast

- Username/password sai, Entra principal chưa có quyền database.
- DNS hostname không tồn tại do sai cấu hình ổn định.
- Connection string sai driver/port/DB name.
- TLS hostname/certificate verification bị lỗi.
- Bảng/cột không tồn tại hoặc query sai cú pháp.
- Unique constraint/foreign key/check constraint bị vi phạm bởi dữ liệu không hợp lệ.
- Tenant không đủ quyền hoặc query truy cập dữ liệu ngoài phạm vi.

Retry mù những lỗi này làm tăng latency và lấp log mà **không tăng xác suất thành công**. Hãy trả lỗi phù hợp, đặt alert và sửa cấu hình/schema/dữ liệu.

### 11.3. Những lỗi có thể transient

- Service Azure chuyển đổi primary/failover hoặc bảo trì, connections cũ bị reset.
- Mạng bị gián đoạn trong thời gian ngắn.
- Database đang quá tải/throttling, cần giảm tốc và backoff.
- Transaction bị deadlock victim hoặc serialization failure.
- Một connection idle bị firewall/NAT/database đóng, pool cần tạo replacement.

Ngay cả với lỗi transient, retry phải giới hạn theo **số lần, thời gian, mục tiêu idempotency và capacity**. Không phải cứ transient là có thể retry toàn bộ business workflow.

### 11.4. Hai chiều cần xác định

Trước khi retry, luôn đặt hai câu hỏi:

1. **Lỗi xảy ra ở bước nào?** Trước khi mở connection, trước khi có bất kỳ write, trong transaction đã rollback hay sau khi COMMIT được gửi?
2. **Thao tác có thể thực hiện lại an toàn không?** Chỉ đọc, insert theo unique request ID, cập nhật idempotent, hay đã tạo side effect bên ngoài?

Ví dụ `UPDATE accounts SET balance = balance - 100 WHERE account_id = ?` **không idempotent** nếu chạy lại sau một commit không rõ kết quả. Ngược lại, `UPDATE orders SET status='PAID' WHERE id=?` có thể idempotent về trạng thái, nhưng vẫn phải xét triggers, timestamps, audit records và side effects phát sinh.

## 12. Retry policy: backoff, jitter và time budget

Một retry policy tốt có **whitelist lỗi**, **max attempts**, **backoff tăng dần**, **jitter**, **request deadline** và **logs/metrics có giới hạn**.

### 12.1. Exponential backoff có jitter

Ví dụ minh họa:

```text
Attempt 1: thực hiện ngay
Attempt 2: chờ ~100–250 ms
Attempt 3: chờ ~250–600 ms
Attempt 4: chờ ~600–1200 ms
Hết số lần hoặc hết deadline: trả lỗi để caller xử lý
```

Thời gian thực tế phụ thuộc SLO và thời gian failover/throttling, không phải dãy số chuẩn cho Azure. Với hàng trăm replicas, **jitter** giúp tránh mọi instances retry đồng thời khi database vừa phục hồi.

Một phép tính khái niệm:

\[
delay_n=\min(delay_{max},delay_{base}\times 2^{n-1}) + randomJitter
\]

Nếu nhiều tầng cùng retry (HTTP gateway, service, JDBC driver và transaction handler), tổng số lần thử có thể **nhân lên**. Ví dụ ba tầng mỗi tầng tối đa ba lần có thể tạo tới 27 attempts phía dưới. Đặt trách nhiệm retry rõ để tránh **retry storm**.

### 12.2. Retry có ngân sách thời gian

Nếu HTTP endpoint có deadline 5 giây, không thể cho transaction retry 10 lần mỗi lần statement timeout 3 giây. Một chiến lược:

- Giới hạn **2–4 lần** cho lỗi được phép, nhưng không dùng con số này như quy tắc cứng.
- Dừng khi remaining deadline không đủ để thử có ý nghĩa.
- Tôn trọng tín hiệu cancellation/interruption; không nuốt `InterruptedException`.
- Có thể đặt circuit breaker để chặn requests mới khi DB outage kéo dài.
- Không giữ `Connection` trong lúc sleep giữa retries.

### 12.3. Retry tại tầng nào?

| Tầng | Retry hợp lý | Không nên làm |
|---|---|---|
| **HikariCP/driver** | Quản lý kết nối hỏng và hành vi tái kết nối được hỗ trợ | Giả định pool tự replay SQL transaction |
| **Repository/read query** | SELECT ngắn, deterministic, không có side effect | Lặp query vô hạn, đẩy tải vào DB đang throttled |
| **Transaction service** | Retry **toàn bộ transaction đã rollback** khi deadlock/serialization failure | Retry mỗi statement giữa transaction hỏng |
| **HTTP/API boundary** | Retry request nếu contract hỗ trợ idempotency | Lặp POST thanh toán mà không có idempotency key |
| **Background worker** | Retry job với event ID ổn định và dữ liệu bền vững | Complete message trước DB commit hoặc làm side effects trùng |

## 13. Java: retry transaction đã rollback, không retry COMMIT mù

Đây là ví dụ **Java thuần** thiết kế bảo thủ: chỉ tự retry transaction SQL được xác định là deadlock/serialization-aborted, sau khi rollback thành công. Ví dụ cố tình **không tự retry** khi có lỗi ở `commit()` vì kết quả commit có thể đã thành công nhưng client không nhận được ACK.

### 13.1. Mẫu executor cho transaction trong database

```java
import javax.sql.DataSource;
import java.sql.Connection;
import java.sql.SQLException;
import java.util.concurrent.ThreadLocalRandom;

public final class TransactionRetry {
    private static final int MAX_ATTEMPTS = 4;
    private final DataSource dataSource;

    @FunctionalInterface
    public interface Work<T> {
        T execute(Connection connection) throws SQLException;
    }

    public TransactionRetry(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public <T> T run(Work<T> work) throws SQLException, InterruptedException {
        for (int attempt = 1; attempt <= MAX_ATTEMPTS; attempt++) {
            try (Connection conn = dataSource.getConnection()) {
                conn.setAutoCommit(false);
                boolean commitStarted = false;

                try {
                    T result = work.execute(conn);
                    commitStarted = true;
                    conn.commit();
                    return result;
                } catch (SQLException ex) {
                    if (commitStarted) {
                        // COMMIT được gọi nhưng phản hồi lỗi:
                        // Không biết server đã commit hay chưa.
                        throw new SQLException(
                                "Commit outcome unknown; reconcile by request ID",
                                ex);
                    }

                    // Không retry nếu không thể rollback an toàn.
                    try {
                        conn.rollback();
                    } catch (SQLException rollbackFailure) {
                        ex.addSuppressed(rollbackFailure);
                        throw ex;
                    }

                    if (!retryableAbortedTransaction(ex)
                            || attempt == MAX_ATTEMPTS) {
                        throw ex;
                    }
                } catch (RuntimeException businessError) {
                    try {
                        conn.rollback();
                    } catch (SQLException rollbackFailure) {
                        businessError.addSuppressed(rollbackFailure);
                    }
                    throw businessError;
                }
            }

            // Sau khi Connection đã được trả pool.
            long baseMs = Math.min(800L, 100L << (attempt - 1));
            long jitterMs = ThreadLocalRandom.current().nextLong(20, 150);
            Thread.sleep(baseMs + jitterMs);
        }
        throw new IllegalStateException("Unreachable");
    }

    private static boolean retryableAbortedTransaction(SQLException ex) {
        String state = ex.getSQLState();
        int vendorCode = ex.getErrorCode();
        return "40001".equals(state)
                || "40P01".equals(state)  // PostgreSQL deadlock
                || vendorCode == 1205     // SQL Server deadlock victim
                || vendorCode == 1213;    // MySQL deadlock
    }
}
```

**Phạm vi ví dụ:** chỉ dành cho code thao tác **một database transaction**, không gọi payment API, gửi message, email hoặc ghi file ở ngoài transaction. Muốn xử lý `SQLException` khi **`getConnection()`** thất bại, có thể thêm một retry **riêng cho acquisition** với classifier lỗi và deadline phù hợp; ví dụ cố ý để lỗi đó thoát ra, tránh vô tình retry một thao tác có trạng thái không chắc chắn.

**Điểm thận trọng:** sau khi `commit()` thành công, ngay cả lỗi khi đóng/trả connection cũng không có nghĩa transaction thất bại. Đối với business command cần at-most-once effect, caller không được blind retry chỉ vì thấy exception sát lúc hoàn tất; phải kiểm tra request ID trong database.

### 13.2. Sử dụng executor với PreparedStatement

```java
TransactionRetry retry = new TransactionRetry(dataSource);

String orderId = "ORD-1042";
retry.run(conn -> {
    try (var ps = conn.prepareStatement(
            "UPDATE orders SET status = ? WHERE order_id = ?")) {
        ps.setString(1, "PAID");
        ps.setString(2, orderId);
        int changed = ps.executeUpdate();
        if (changed != 1) {
            throw new SQLException("Unexpected order row count");
        }
    }
    return null;
});
```

Đây là **đoạn code nằm trong method** có `dataSource`. Để production-ready còn cần deadline, metrics, exception mapping theo driver, kiểm tra business invariants, idempotency key và logging an toàn. Ví dụ cố ý không bao gồm retry cho connection errors sau writes; cần xử lý khác tùy giai đoạn.

### 13.3. Vì sao không retry từng câu lệnh riêng lẻ?

Giả sử một transaction có ba bước:

```sql
UPDATE accounts SET balance = balance - 100 WHERE id = 1;
UPDATE accounts SET balance = balance + 100 WHERE id = 2;
INSERT INTO transfers(transfer_id, status) VALUES (?, 'COMPLETED');
```

Nếu statement thứ hai gặp deadlock và transaction bị rollback, **retry statement thứ hai** mà không replay cả transaction có thể làm kết quả sai; nếu statement đầu đã bị rollback mà code không biết, lần retry không còn tương ứng nghiệp vụ ban đầu.

Với transaction aborted do serialization/deadlock, retry **toàn bộ unit of work trong transaction mới**, kèm cùng logical transfer ID và kiểm tra invariant. Không tự retry một phần rồi tiếp tục dùng connection đang ở failed transaction state.

## 14. “Commit outcome unknown”: trường hợp nguy hiểm nhất

Tình huống:

```text
Java                             Azure database
 |                                   |
 | BEGIN                             |
 | INSERT orders(order_id='ORD-42')  |
 |---------------------------------->|
 | COMMIT                            |
 |---------------------------------->|
 |                       COMMIT thành công
 |             X Network reset trước COMMIT ACK
 |<----------------------- (mất phản hồi)
 |
 | SQLException: connection lost
 | KẾT QUẢ COMMIT? KHÔNG CHẮC
```

Nếu Java retry bằng một `order_id` khác và gọi lại payment, có thể tạo **hai đơn hàng hoặc hai lần thu tiền**. Lỗi connection sau COMMIT không có nghĩa server rollback.

### 14.1. Idempotency key ở lớp nghiệp vụ

API tạo đơn có thể yêu cầu một **idempotency key** do client/gateway/service xác định ổn định theo logical request:

```http
POST /orders HTTP/1.1
Idempotency-Key: req-20261120-1042
Content-Type: application/json

{"productId":"SKU-17","quantity":1}
```

Trong database, một bảng lưu request ID và kết quả giao dịch:

```sql
CREATE TABLE order_requests (
    request_id VARCHAR(120) PRIMARY KEY,
    order_id VARCHAR(120) NOT NULL,
    result_status VARCHAR(30) NOT NULL
);
```

Khi retry, hệ thống truy vấn `request_id` trước hoặc dựa vào **unique constraint** để không tạo đơn thứ hai. Nếu yêu cầu có cùng key nhưng payload khác, cần xác định lỗi conflict và từ chối thay vì cho phép key tái sử dụng tùy ý.

### 14.2. Unique constraint là cơ chế bảo vệ cuối

Một pre-check kiểu:

```text
SELECT request_id -> không thấy
INSERT order -> thành công
```

không chống được hai requests song song cùng kiểm tra rồi cùng insert. Cần **unique constraint** và transaction isolation phù hợp. Nếu bị unique violation, ứng dụng nên truy xuất kết quả gốc và trả về theo contract nếu xác nhận cùng logical request, không retry insert vô tận.

### 14.3. Không gộp DB commit và Service Bus send bằng niềm tin

Nếu Java lưu đơn hàng vào SQL rồi gửi `OrderCreated` đến Azure Service Bus, hai thao tác không tự tạo một transaction nguyên tử. Với yêu cầu không mất event sau DB commit, sử dụng **transactional outbox**:

```text
DB transaction:
  INSERT orders
  INSERT outbox_events(event_id, payload)
  COMMIT

Outbox relay:
  đọc outbox chưa gửi
  publish event với event_id ổn định
  đánh dấu đã gửi sau broker acknowledgment

Consumer:
  inbox/idempotent processing để chịu message gửi lặp
```

Outbox tránh mất sự kiện đã commit nhưng có thể publish lặp khi relay crash sau broker ACK trước khi đánh dấu đã gửi. Vì vậy **consumer vẫn phải idempotent**.

### 14.4. Kết nối với payment provider

Đối với thu tiền, chuyển tiền hoặc tạo resource ở service ngoài, DB transaction chỉ bảo vệ dữ liệu của chính database. Cần **idempotency key được downstream hỗ trợ**, tra cứu trạng thái giao dịch và saga/compensation nếu cần. Không dùng retry JDBC như một lời hứa exactly-once của toàn workflow.

## 15. Transaction isolation và xử lý concurrency

JDBC cho phép thiết lập transaction isolation level nhưng **semantics thực tế phụ thuộc database engine** và có thể tương tác với các tùy chọn như optimistic concurrency, snapshot isolation hoặc server defaults.

| Isolation concept | Mục tiêu | Rủi ro/đổi chác |
|---|---|---|
| **READ COMMITTED** | Tránh đọc dữ liệu chưa commit, theo định nghĩa từng engine | Không tự bảo đảm không có non-repeatable reads/phantoms |
| **REPEATABLE READ** | Ổn định hơn giữa các reads trong transaction | Có thể tăng contention hoặc phát sinh serialization conflicts theo engine |
| **SERIALIZABLE** | Mạnh hơn về hành vi tương đương serial transactions | Có thể tăng blocking/serialization failures, cần retry đúng |
| **Snapshot/MVCC variants** | Hỗ trợ nhất quán reads theo cơ chế của database | Có trade-offs và conflict handling riêng |

Không chọn `SERIALIZABLE` cho mọi request chỉ vì “an toàn nhất”. Cần cân nhắc business invariants, performance, khả năng retry và cách Azure SQL/PostgreSQL/MySQL thực thi mức cô lập.

### 15.1. Optimistic concurrency bằng version

Một cách tránh ghi đè thay đổi của request khác:

```sql
UPDATE orders
SET status = ?, version = version + 1
WHERE order_id = ? AND version = ?;
```

Java kiểm tra affected rows. Nếu bằng 0, dữ liệu đã thay đổi hoặc record không tồn tại; đó có thể là **conflict nghiệp vụ**, không phải lỗi connection transient. Không retry mù cho tới khi câu UPDATE thắng: phải đọc lại trạng thái và áp business rule.

### 15.2. Giữ lock ngắn

Anti-pattern:

```text
BEGIN
  SELECT ... FOR UPDATE
  HTTP call external service (30 seconds)
  UPDATE ...
COMMIT
```

Giữ row lock và JDBC connection trong lúc chờ HTTP làm tăng thời gian pool bị chiếm và nguy cơ deadlock. Với workflow nhiều bước, dùng trạng thái bền vững và async messaging thay vì một transaction kéo dài qua nhiều hệ thống.

### 15.3. Đừng phụ thuộc vào một session state bị rò rỉ

Connections từ Hikari được tái sử dụng. Nếu code thay đổi `autoCommit`, isolation, schema, timezone hoặc các session settings khác bằng raw SQL mà không reset đúng cách, request tiếp theo có thể nhận state không mong đợi. Một số connection properties được pool theo dõi và reset, nhưng không thể dựa vào pool để tự phục hồi mọi **server-side session setting** của từng database.

Ưu tiên dùng framework transaction manager, cấu hình connection init phù hợp và đảm bảo connection state nhất quán trước khi trả về pool. Nếu dùng PostgreSQL advisory locks, temp tables hoặc session variables, cần thiết kế cleanup rõ ràng.

## 16. Connection leaks và cách chẩn đoán pool exhaustion

Một **connection leak** xảy ra khi code mượn connection mà không trả lại pool sau khi công việc kết thúc. Khi pool có 10 connections và tất cả bị giữ, request thứ 11 sẽ chờ đến `connectionTimeout` rồi thất bại.

### 16.1. Ví dụ sai

```java
public String loadStatusBad(DataSource ds, String orderId)
        throws SQLException {
    Connection conn = ds.getConnection();  // Không close.
    PreparedStatement ps =
            conn.prepareStatement(
                    "SELECT status FROM orders WHERE order_id = ?");
    ps.setString(1, orderId);
    ResultSet rs = ps.executeQuery();
    return rs.next() ? rs.getString(1) : null;
}
```

Ở đây không có `finally` hoặc `try-with-resources`; mọi request thành công cũng có thể làm connection bị giữ lại cho tới khi process kết thúc hoặc garbage collection/driver cleanup không đáng tin cậy. **Không trông cậy vào GC để trả connection.**

### 16.2. Ví dụ đúng

```java
public String loadStatusGood(DataSource ds, String orderId)
        throws SQLException {
    try (Connection conn = ds.getConnection();
         PreparedStatement ps = conn.prepareStatement(
                 "SELECT status FROM orders WHERE order_id = ?")) {
        ps.setString(1, orderId);
        try (ResultSet rs = ps.executeQuery()) {
            return rs.next() ? rs.getString(1) : null;
        }
    }
}
```

### 16.3. Leak warning không luôn là leak thật

Hikari `leakDetectionThreshold` có thể cảnh báo khi connection bị giữ quá lâu. Một query thực sự mất 25 giây với threshold 20 giây có thể phát sinh warning dù cuối cùng connection vẫn được trả. Khi đó cần tìm **slow query/long transaction** thay vì mặc định quy lỗi cho quên close.

Phân tích cùng các tín hiệu:

- `active connections` tăng lâu và không giảm sau khi traffic ngừng.
- `idle connections` gần 0, `pending threads` tăng, acquisition timeout xảy ra.
- Thread dump/stack traces cho thấy thread đang chờ SQL, gọi HTTP hay quên close.
- DB-side sessions/transactions ở trạng thái active/idle-in-transaction.
- Slow query logs và query execution plans.

### 16.4. Rò rỉ từ framework boundary

Trong Spring/JPA:

- Một transaction mở ở controller rồi trả streaming response có thể giữ connection lâu.
- Một lazy-loading query bị gọi ngoài phạm vi transaction có thể gây lỗi/lấy thêm connection không mong muốn.
- Một method `@Async` không tự mang transaction context của thread khác theo cách đơn giản.
- Background job tạo `EntityManager`/`Session` thủ công mà không đóng đúng có thể giữ tài nguyên.

Đo thời gian **hold connection**, không chỉ số request đồng thời. Đánh giá transaction boundaries và các code paths lỗi/cancellation.

## 17. Sự cố failover và connection pool cần phục hồi thế nào?

Giả sử Azure SQL hoặc Azure Database for PostgreSQL gặp failover. Một số TCP connections tới primary cũ có thể bị đóng; pool vẫn giữ các objects đại diện cho những connections này cho tới khi phát hiện không hợp lệ.

```text
T0: primary hoạt động -> Java pool có 8 connections
T1: failover/maintenance -> một số connections mất hiệu lực
T2: request nhận connection cũ -> SQLException/connection reset
T3: pool loại connection hỏng, thử tạo connection mới
T4: DNS/route/primary mới sẵn sàng, authentication thành công
T5: queries tiếp tục, nhưng một số requests phải retry an toàn
```

### 17.1. Nguyên tắc thiết kế

- Sử dụng **hostname service chính thức** của Azure database, không hard-code IP primary hiện tại.
- Kiểm tra các cơ chế DNS TTL/cache của JVM và môi trường mạng nếu failover dựa vào thay đổi DNS.
- Cấu hình Hikari connection validation, maxLifetime/keepalive phù hợp; không cố sử dụng connection đã bị đánh dấu broken.
- Cho phép timeout và retry có giới hạn khi failover ngắn, nhưng đừng giữ hàng nghìn HTTP requests chờ không hạn định.
- Cập nhật alerts từ DB failover/connectivity/compute metrics, phân biệt sự cố DB với pool capacity.
- Sau recovery, xác minh **business outcomes** của những transactions bị gián đoạn.

**Không giảm `maxLifetime` xuống vài giây** để buộc mọi request liên tục mở socket mới; điều đó làm tăng authentication/TLS cost và có thể tạo connection storm trong lúc DB chưa sẵn sàng.

### 17.2. Read replica và read/write split

Khi kiến trúc dùng read replica (theo dịch vụ/tier hỗ trợ), có thể có **read DataSource** và **write DataSource** riêng. Điều này không miễn phí:

- Read replica có thể **lag** sau primary; yêu cầu read-your-writes phải có chiến lược.
- Mỗi DataSource có pool riêng, nhân tổng số connections.
- Transaction cập nhật phải đi tới writer; không tự route read trong một write transaction sang replica mà làm mất consistency.
- Khi replica lỗi, ứng dụng phải có hành vi degrade/fallback được kiểm soát.

Không xem replica là cách giải quyết deadlock trên writer hoặc query ghi thiếu index.

### 17.3. Khởi động khi database đang outage

Ứng dụng có thể quyết định:

- **Fail-fast startup** khi DB là dependency bắt buộc và không thể phục vụ bất kỳ request nào.
- **Start but not ready** khi runtime cần hoạt động để retry/recover, nhưng `readiness` phải phản ánh tính sẵn sàng của API nghiệp vụ.
- Background workers có thể tiếp tục chạy một số phần không cần DB hoặc chờ reconnect theo policy.

Không lạm dụng Kubernetes **liveness probe** để restart toàn bộ pod chỉ vì DB tạm thời unavailable: điều này có thể gây restart storm và connection storm. Liveness đo process còn khỏe; readiness phản ánh khả năng phục vụ theo contract.

## 18. Monitoring: nhìn đồng thời Java pool và Azure database

Khi API trả 503 do không mượn được connection, cần biết đó là **pool undersized**, **connection leak**, **slow query/locks** hay **database/network outage**.

### 18.1. HikariCP metrics

Trong môi trường Spring Boot + Micrometer/Actuator hoặc công cụ metrics phù hợp, nên theo dõi:

| Metric khái niệm | Ý nghĩa | Dấu hiệu bất thường |
|---|---|---|
| **Active connections** | Connections đang cho mượn | Gần max quá lâu |
| **Idle connections** | Connections sẵn để cho mượn | Liên tục bằng 0 khi tải không lớn |
| **Pending acquisition** | Threads đang chờ connection | Tăng liên tục, request latency tăng |
| **Total connections** | Active + idle | Tăng/giảm bất thường khi scale/failover |
| **Acquire time** | Thời gian mượn connection | p95/p99 tăng khi pool căng |
| **Connection creation time** | Mở physical connection mới | Tăng khi network/login chậm |
| **Timeout count** | Không lấy được connection kịp thời | Pool, DB hoặc code giữ connection lâu |

Tên metrics thực tế có thể là `hikaricp.connections.active` hoặc dạng Prometheus được ánh xạ sang underscore theo framework/registry. **Không hard-code tên metric trước khi xem endpoint/registry thực tế**.

### 18.2. Metrics Azure database

Quan sát đúng dịch vụ/tier:

- CPU, memory và storage pressure; I/O throughput/latency theo metrics hỗ trợ.
- Số **active connections/sessions** và giới hạn.
- Failed connections, failed logins, connection throttling.
- Deadlocks, lock waits, query duration và expensive SQL.
- Failover/maintenance events hoặc trạng thái service.
- Network errors và private endpoint/DNS events trong logs có sẵn.

Các tên metrics khác nhau giữa Azure SQL Database, PostgreSQL Flexible Server và MySQL Flexible Server. Không giả định một biểu đồ SQL Server DMV có sẵn trên PostgreSQL hoặc ngược lại.

### 18.3. Một dashboard tối thiểu

```text
AKS API replicas                  12
Hikari maximumPoolSize            8
Estimated app connection ceiling 96
Hikari active (aggregate)        74
Hikari pending threads            9
DB active sessions               110
DB CPU                           87%
HTTP p95 latency                 2.4 s
DB query p95 latency             1.8 s
Connection acquire timeout/min   24
```

Các số là giả định minh họa. Nếu `Hikari active` và `pending` đều cao, nhưng DB CPU 87% và SQL latency tăng, việc tăng pool từ 8 lên 20 có thể làm DB quá tải hơn. Nên xác định **nút thắt** bằng tracing, slow query và SQL execution plan trước.

### 18.4. Distributed tracing có ích gì?

Một trace HTTP request có thể chia thành:

```text
HTTP POST /orders  1800ms
  |
  +-- Auth/JWT check   30ms
  +-- Pool acquire     650ms
  +-- SQL INSERT       920ms
  +-- Business logic    50ms
  +-- HTTP response    150ms
```

Nếu chỉ nhìn SQL execution 920ms, bỏ qua pool acquire 650ms sẽ làm chẩn đoán sai một phần lớn latency. Instrument JDBC/client spans và HTTP spans bằng OpenTelemetry/Application Insights hoặc giải pháp tương thích; **không đưa SQL parameters nhạy cảm hoặc credentials vào trace**.

### 18.5. Alert có runbook

Một số cảnh báo hữu ích:

- Hikari pending connections cao liên tục + timeout count tăng.
- DB connections gần giới hạn khi replicas/scale tăng.
- Login/authentication failures tăng sau credential rotation.
- Query p95 tăng hoặc deadlock/serialization failures tăng.
- DB CPU/IO saturation, storage capacity hoặc failover events.
- Pool acquisition p95 vượt một phần đáng kể HTTP request budget.
- Requests thất bại nhiều nhưng retry success rate giảm – dấu hiệu retry không còn hữu ích.

Alert nên gắn với **owner, evaluation window, severity, action group và runbook**. Không tạo cảnh báo “connection active > 0” vì đó là hoạt động bình thường.

## 19. Bảo mật kết nối và dữ liệu

### 19.1. Secrets và rotation

Nếu dùng password authentication:

1. Lưu password trong Azure Key Vault hoặc secret store tương đương có quyền tối thiểu.
2. Truy cập secret bằng managed identity của workload khi được hỗ trợ.
3. Có quy trình rotation dùng account/credential khác hoặc dual credential khi hệ thống hỗ trợ.
4. Đảm bảo app/pool mở connections mới bằng credential hiện tại; **các physical connections đang sống có thể không bị buộc xác thực lại ngay**.
5. Không log JDBC URL nếu URL có username/password hoặc access token được nhúng; mask các thông tin nhạy cảm.

Một password được cập nhật trong Key Vault **không có nghĩa** mọi JVM tự nhận giá trị mới. Nếu app đọc secret lúc startup, phải thiết kế refresh/restart theo quy trình an toàn.

### 19.2. Principle of least privilege ở database

- Tài khoản runtime chỉ có quyền ở schema/tables cần thiết.
- Tách read-only workloads khi phù hợp.
- Dùng parameterized SQL và kiểm tra tenant/ownership.
- Tách database migration admin khỏi runtime.
- Kiểm tra row-level security nếu engine/schema hỗ trợ, nhưng không coi nó thay toàn bộ app authorization.
- Hạn chế query có thể đọc bảng hệ thống hoặc thông tin quản trị ngoài nhu cầu.

### 19.3. Mạng private và encryption in transit

Chọn Private Endpoint/VNet integration/private access theo Azure database và network topology được hỗ trợ. Nếu database public access được bật vì tích hợp bên ngoài, phải dùng firewall, source restrictions, TLS và threat model tương ứng; không để `0.0.0.0/0` như phương án mặc định.

**TLS trong JDBC cần hostname verification**, không chỉ “socket đã mã hóa”. Dùng CA trust chain của Azure tương ứng và luân chuyển chứng chỉ một cách có kiểm soát. Không in certificate private key, access token hoặc connection string có secret vào log.

### 19.4. Tài khoản và dữ liệu trong logs

Nên log `operation`, SQLState, vendor code, retry attempt, query fingerprint, pool name, DB resource ID/region và correlation ID ở mức cần thiết. Không log:

- Full SQL chứa giá trị nhạy cảm đã được interpolate.
- Username/password/access tokens hoặc SAS keys.
- Full connection string có secrets.
- PII, payment data hoặc toàn bộ kết quả query.
- Stack traces ở public HTTP response.

Điều tra cần xác định **mã lỗi**, **giai đoạn**, **thời điểm** và **phạm vi ảnh hưởng**, không cần làm lộ dữ liệu khách hàng.

## 20. Troubleshooting: tìm đúng nguyên nhân thay vì tăng pool

### 20.1. Bảng triệu chứng – nguyên nhân – xử lý

| Dấu hiệu | Nguyên nhân có thể | Việc cần kiểm tra |
|---|---|---|
| `Connection is not available, request timed out` từ Hikari | Pool hết connections hoặc connections bị giữ lâu | Active/idle/pending, long transactions, slow SQL, leaks |
| `Connection refused` | Sai hostname/port, service không reachable, firewall | DNS, route, port, Azure DB networking |
| `Connection timed out` khi connect | Network/DNS/private endpoint hoặc DB không phản hồi | VNet, NSG, firewall, private DNS, failover events |
| `SSLHandshakeException` / certificate validation error | Sai CA trust, hostname hoặc TLS config | Driver/JDK trust store, FQDN và certificate chain |
| Login failed / SQLState `28...` | Sai credential/token, DB user/role chưa đúng | Entra principal, DB auth, credential rotation |
| Lỗi ngay sau khi rotate password | App/pool vẫn dùng password cũ để tạo physical connection | Secret refresh/restart, rotation order và logs an toàn |
| SQLState lớp `08` trong lúc chạy query | Network reset, failover, broken connection | Operation phase, pool eviction, idempotency |
| `40001` hoặc deadlock vendor code | Serialization/deadlock | Retry nguyên transaction mới, tối ưu lock order/query |
| `23505` sau retry | Unique constraint/duplicate logical request | Dùng request ID để xác minh kết quả cũ |
| Azure SQL `40501` | Database busy/throttled theo tình huống | Compute/capacity, retry-after/backoff nếu hỗ trợ |
| Nhiều JDBC queries chậm | Thiếu index, DB CPU/IO/locks, plan regression | Query plans, waits, DB metrics trước khi tăng pool |
| Chỉ một vài pods bị lỗi | DNS/identity/secret/pool config khác, node egress | So sánh runtime config, pod/node và role |
| Sau scale-out toàn app gặp timeout | Tổng số pools vượt DB session/capacity | Max replicas × max pool size, rollout surge |
| API timeout nhưng DB vẫn đang ghi | Caller deadline/cancellation không hủy transaction kịp | Timeout layering, idempotency, connection lifecycle |
| Java OOM/CPU spike | Nhiều threads chờ, quá nhiều ResultSets, buffer lớn | Heap/thread dumps, pool metrics, fetchSize và query patterns |

Không coi bảng là chẩn đoán chắc chắn. Một thông báo `Connection timeout` có thể đến từ **pool acquisition** hoặc **network connect**; tên exception, stack trace, metric và điểm phát sinh cần được đối chiếu.

### 20.2. Quy trình điều tra 10 bước

1. **Xác định phạm vi:** một endpoint, một replica hay toàn cluster? Bắt đầu lúc nào?
2. **Phân loại exception:** `SQLException` SQLState/vendor code, Hikari timeout hay TLS/transport exception?
3. **Xác định operation phase:** lấy connection, thực thi SQL, transaction commit hay close?
4. **Xem pool:** active, idle, pending, acquisition latency, leak warnings, physical connection creations.
5. **Xem DB:** sessions, CPU/IO, deadlocks/locks, slow queries, failover/maintenance.
6. **Xem network:** DNS, port, private endpoint/firewall, TLS certificate, egress từ đúng pod/VM.
7. **Xem authentication:** SQL credentials, Entra identity, token refresh và DB principal grants.
8. **Đối chiếu thay đổi:** rollout, pool size, replica count, DB scaling, password rotation, migration.
9. **Khắc phục tối thiểu:** sửa leak/query/credential/route hoặc giảm concurrency, retry có giới hạn.
10. **Xác minh và ghi nhận:** test request hợp lệ, lỗi từ chối, latency/pool recovery, business consistency.

Không thực hiện đồng thời các thay đổi lớn như “tăng pool, tăng replicas, bỏ TLS và mở firewall”; điều đó vừa nguy hiểm vừa khiến không biết tác động của từng bước.

### 20.3. Khi pool pending tăng mà database không quá tải

Có thể là pool size hơi nhỏ, hoặc một vài transactions giữ connection lâu. Trình tự:

- Xem `active` có đạt `maximumPoolSize` không.
- Xem slow SQL và transaction duration, tránh nhầm HTTP waiting với thời gian sử dụng DB.
- Kiểm tra code leak/đọc ResultSet streaming chưa đóng.
- Nếu DB vẫn còn năng lực và throughput tăng khi thêm connections trong load test, cân nhắc tăng pool **có giới hạn**.
- Kiểm tra tổng replicas sau khi thay pool size; cần giữ ngân sách DB.

### 20.4. Khi DB connections cao nhưng CPU thấp

Nhiều sessions có thể đang idle, chờ lock, chờ network hoặc giữ transaction không làm nhiều CPU. Kiểm tra **session states và waits** thay vì giả định CPU thấp nghĩa là DB chưa bão hòa.

Với PostgreSQL, `idle in transaction` đặc biệt đáng chú ý vì một session có thể giữ locks/snapshot dù không chạy query. Với SQL Server, kiểm tra các sessions/requests và waits bằng những views/tools được phép. Với MySQL, xem sessions/processlist/performance schema nếu quyền và tính năng cho phép. Không cần cấp admin privileges cho runtime chỉ để truy vấn performance data.

## 21. Spring Retry, Resilience4j và ranh giới transaction

Ứng dụng Spring thường sử dụng Spring Retry, Resilience4j hoặc một thư viện resilience. Những công cụ này có giá trị nhưng có thể **làm sai khi đặt decorator sai lớp**.

### 21.1. Retry phải tạo transaction mới

Một trường hợp cần tránh:

```text
@Transactional mở transaction
      |
      v
@Retryable lặp một câu SQL trong transaction cũ đã aborted
      |
      v
Các lần thử tiếp theo thất bại hoặc tạo trạng thái không mong muốn
```

Đối với serialization failure/deadlock đã rollback, **mỗi retry phải chạy trong một transaction mới**. Có thể thiết kế một **retrying orchestration service** gọi một transaction service khác qua Spring proxy, hoặc dùng `TransactionTemplate` theo từng attempt. Cần kiểm tra proxy ordering, transaction propagation và self-invocation thực tế.

```text
HTTP/API layer
    |
    v
Retrying orchestration boundary
    |
    +-- Attempt 1 -> new DB transaction -> rollback on 40001
    |
    +-- backoff (không giữ connection)
    |
    +-- Attempt 2 -> new DB transaction -> commit
    |
    v
Return response
```

**Không** đặt `Thread.sleep` bên trong một `@Transactional` đang giữ DB connection/locks. Nếu transaction service gọi side effects ngoài DB, không tự retry toàn bộ bằng decorator.

### 21.2. Retry ở đúng phạm vi nghiệp vụ

| Thao tác | Có thể retry? | Điều kiện |
|---|---|---|
| `SELECT` chỉ đọc ngắn | Thường có thể | Query deterministic, không giữ state bên ngoài, deadline còn |
| `UPDATE ... SET status='PAID'` | Có thể khi idempotent thật | Xét trigger, audit, side effects và request ID |
| `INSERT` với unique idempotency key | Có thể reconcile/replay | Xác minh row đã ghi nếu commit outcome unknown |
| Trừ tiền bằng phép cộng/trừ trực tiếp | Không blind retry | Cần ledger/transaction ID và unique constraint |
| Gọi payment API trong DB transaction | Không tự retry cả workflow | Cần provider idempotency và saga |
| Publish Service Bus sau DB commit | Không đảm bảo atomicity | Dùng outbox |

### 21.3. Circuit breaker khi database outage

Nếu DB không reachable nhiều phút, retry mỗi incoming HTTP request sẽ gây tải lên connection pool và mạng. Circuit breaker giúp **fail fast có điều kiện** khi tỷ lệ lỗi vượt ngưỡng, rồi thử phục hồi có kiểm soát.

Điều cần lưu ý:

- Chỉ áp circuit breaker vào dependency call có phân loại failure rõ.
- Không che lỗi lập trình hoặc business validation thành “database unavailable”.
- Không mở circuit quá lâu làm app không thử phục hồi.
- Quan sát state OPEN/HALF_OPEN/CLOSED và tỷ lệ thành công sau failover.
- Tách read-only endpoints/health endpoints theo mức phụ thuộc DB thật.

Circuit breaker cũng không thay thế idempotency. Một HTTP caller có thể retry lại request sau khi nhận 503; backend vẫn phải xác minh kết quả cũ bằng request key nếu write đã xảy ra.

## 22. JDBC và reactive programming

JDBC là API **blocking** theo mô hình phổ biến. Nếu ứng dụng Java dùng Spring WebFlux/Project Reactor hoặc reactive pipeline, gọi JDBC trực tiếp trên event-loop thread có thể gây latency rộng vì thread bị chiếm khi chờ I/O.

Các lựa chọn:

- Dùng **Spring MVC/virtual threads hoặc thread pool có giới hạn** với JDBC phù hợp kiến trúc, vẫn giữ tổng concurrency và pool capacity được kiểm soát.
- Nếu dùng reactive framework nhưng vẫn phải gọi JDBC, chuyển blocking work sang một scheduler dành cho blocking I/O với giới hạn và backpressure.
- Xem xét **R2DBC** nếu driver/engine/tính năng đáp ứng và đội ngũ thực sự cần reactive database access; R2DBC **không phải JDBC**, có driver/pool/config khác.

**Virtual threads không làm database xử lý nhiều queries hơn.** Chúng có thể giảm chi phí quản lý threads chờ nhưng tăng số requests chờ kết nối nếu không có semaphore/bounded concurrency. Khi số virtual threads rất lớn, Hikari pool vẫn là điểm kiểm soát truy cập DB.

### 22.1. N+1 queries và connection hold time

Một HTTP request tải 100 đơn, mỗi đơn lại truy vấn 5 bản ghi riêng có thể tạo hàng trăm SQL round-trips:

```text
SELECT orders ...          -> 1 query
for each order:
  SELECT items ...         -> 100 queries
```

Đây là **N+1 query problem** thường gặp trong ORM. Tăng pool size không giải quyết tận gốc; cần sửa fetching/query batching, index và data access pattern. Đo số queries trên request và DB time bằng tracing trước khi tune pool.

### 22.2. Cursor, fetchSize và stream dữ liệu lớn

Nếu query trả hàng triệu rows, tải toàn bộ vào memory có thể gây OOM hoặc giữ connection quá lâu. JDBC có các cơ chế `fetchSize`/streaming khác nhau theo driver/engine và transaction settings. Với PostgreSQL, cursor-based fetching có yêu cầu về autocommit và fetch size; với MySQL/SQL Server, cơ chế streaming khác.

Không copy một giá trị `setFetchSize(500)` rồi đảm bảo memory luôn thấp; cần kiểm tra driver/transaction behavior và giải phóng ResultSet/Connection đúng vòng đời.

## 23. Kiểm thử lỗi và phục hồi trước production

Không thể đánh giá retry chỉ bằng việc chạy một query thành công. Cần các bài test có **positive, negative và failure injection** trong môi trường được phép.

### 23.1. Unit tests

Không cần Azure:

- Hàm phân loại SQLState/vendor error chỉ retry các mã đã allowlist.
- Backoff tăng dần, giới hạn attempts và deadline; interruption được propagate.
- Connection được trả pool trong nhánh success/SQLException/RuntimeException.
- Serialization/deadlock retry **toàn transaction**.
- Lỗi query syntax/unique violation được trả ngay hoặc chuyển thành business conflict.
- Lỗi khi commit trả trạng thái **unknown** và yêu cầu reconcile.
- Không log database password/access token.

Khi mock JDBC `Connection` và `SQLException`, phải test cả `rollback()` thất bại để tránh code tưởng rollback thành công và retry.

### 23.2. Integration tests

Trong cơ sở dữ liệu test phù hợp:

| Bài test | Cách mô phỏng | Kết quả kỳ vọng |
|---|---|---|
| Connection success | TLS + valid DB credential | Query đọc hoạt động, connection trả pool |
| Wrong password/DB role | Credential không hợp lệ | Fail-fast, không retry storm |
| Network unavailable | Chặn kết nối trong test environment | Timeout có giới hạn, metrics/alert rõ |
| Pool exhausted | Giữ đủ connections trong test có kiểm soát | Request sau chờ tới timeout, không treo vô hạn |
| Deadlock/serialization failure | Hai transactions cạnh tranh locks | Rollback + retry transaction mới có giới hạn |
| Duplicate request | Gửi hai lần cùng idempotency key | Một logical DB effect |
| Commit ACK lost | Cắt connection ngay sau server commit trong test | Không tạo bản ghi/nghiệp vụ trùng khi caller retry |
| Failover | Thử failover được dịch vụ/lab hỗ trợ | Pool loại stale connections và tự phục hồi |
| Secret rotation | Đổi password/token theo quy trình | Connections mới dùng credential còn hiệu lực |
| Token expiration | Test refresh identity-based JDBC | Connection mới vẫn login đúng sau token expiry |
| Autoscale burst | Tăng replicas đồng thời | Không vượt ngân sách connections/DB capacity |

**Không thực hiện failover hoặc chặn network trên database production không có phê duyệt.** Các bài thử có thể ảnh hưởng clients khác và gây mất khả năng phục vụ.

### 23.3. Tập trung vào bài test commit không rõ kết quả

Một test quan trọng:

1. Client gửi request `Idempotency-Key=req-1042`.
2. Database commit đơn hàng và request record.
3. Giả lập mất ACK trước khi client biết kết quả.
4. Client retry **cùng key**.
5. API truy xuất kết quả cũ hoặc phát hiện unique conflict và trả đúng response.
6. Không thêm đơn khác, không phát event lặp gây side effect trùng.

Nếu không thể tái tạo chính xác mất ACK trong lab, ít nhất viết integration test cho **hai requests cạnh tranh** và **sau commit retry**; ghi rõ giới hạn của test thay vì tuyên bố exactly-once đã được chứng minh.

### 23.4. Load test pool size

Chạy tải tăng dần:

```text
Concurrent users: 10 -> 50 -> 100 -> 200
Pool max:          4 -> 8 -> 12 (các cấu hình thử riêng)
Replicas:          2 -> 4 -> 8 (các cấu hình thử riêng)
```

Đo throughput, p50/p95/p99 request latency, pool acquire p95, active/pending connections, DB CPU/IO, locks, deadlocks và error rate. Chọn cấu hình **ổn định tại tải mục tiêu** chứ không chọn giá trị cực đại với latency tail lớn.

### 23.5. Thử scale-down

Khi KEDA/HPA/Container Apps scale-in, một process có thể bị dừng trong lúc transaction đang mở. Kiểm tra graceful shutdown, connection close, rollback của công việc chưa hoàn tất và retry từ caller/worker khác. Không để ứng dụng tự complete message đã nhận từ Service Bus **trước khi DB commit**.

## 24. Chi phí và vận hành pool trên Azure

Connection pool không phải một dịch vụ Azure có hóa đơn riêng, nhưng cấu hình pool tác động tới **compute tier của database**, khả năng scale app và hiệu năng, nên có ảnh hưởng chi phí gián tiếp.

| Thành phần | Chi phí/rủi ro | Hướng tối ưu |
|---|---|---|
| Azure SQL/PostgreSQL/MySQL compute | CPU/RAM/IO theo tier/vCore hoặc mô hình service | Tối ưu queries/index/transactions trước khi tăng tier |
| Database connections | Memory/session overhead và contention | Giới hạn pool, quản lý replicas, close đúng |
| App compute | Threads, heap, waiting time, autoscaling | Bounded concurrency, backpressure |
| Network | Private endpoints, NAT/Firewall, egress | Kiểm tra topology và DNS |
| Logging/monitoring | Tracing/log ingestion, retention, alert evaluations | Metric sampling, log hygiene |
| Retry storm | Nhiều SQL attempts, DB CPU/locks, log volume | Whitelist lỗi, backoff/jitter, circuit breaker |
| Database HA/replicas | Tier/replica/storage thêm | Chọn theo RTO/RPO và read workload thực tế |

**Đừng giảm `connectionTimeout` hoặc pool size chỉ để có bảng chi phí đẹp** nếu SLO không đáp ứng. Cũng đừng chi thêm database compute để che N+1 queries, full-table scans hay transaction locks kéo dài.

### 24.1. Một bài toán chi phí gián tiếp

Giả sử:

```text
10 API replicas × pool max 20 = 200 connections potential
DB limit/capacity thực tế chỉ phù hợp ~100 sessions
Retry cùng lúc khi failover = 10 replicas × nhiều requests
```

App có thể tạo connection storm, quá tải database, tăng lỗi, kéo theo autoscaler tăng replicas và làm vòng lặp trầm trọng hơn. Một pool nhỏ hơn, bounded concurrency và retry được phân loại có thể giảm cả **lỗi lẫn chi phí** mà không cần đổi DB tier.

### 24.2. Ghi nhận baseline

Nên có bảng baseline theo môi trường:

```text
DB service / tier / region
Connection limit và reserve
JDK, JDBC driver, HikariCP version
maximumPoolSize × max replicas
Pool acquire p50/p95
SQL p50/p95
Error rate / SQLState distribution
Deadlocks / retry rate
DB CPU/IO/session count
RTO/RPO target và failover test record
```

Mỗi lần đổi scale hoặc DB tier, cập nhật baseline và re-run load test phù hợp.

## 25. Tình huống kiến trúc: Orders API trên AKS và Azure PostgreSQL

### 25.1. Yêu cầu

Hệ thống quản lý đơn hàng có:

```text
AKS (production)
  |
  +-- orders-api: 6 replicas, HikariCP per JVM
  +-- orders-worker: 4 replicas, HikariCP per JVM
  +-- outbox-relay: 2 replicas, HikariCP per JVM
  |
  v
Azure Database for PostgreSQL Flexible Server
  |
  +-- orders
  +-- order_requests (unique request_id)
  +-- outbox_events
  +-- processed_messages
```

API ghi đơn, worker xử lý trạng thái, relay publish event sang Service Bus. Đội nền tảng muốn có:

- TLS xác minh hostname, private network.
- Principal riêng cho runtime/migrations, secrets không hard-code.
- Pool tránh vượt database connection budget.
- Retry deadlock/serialization có giới hạn.
- Không tạo đơn hai lần khi COMMIT ACK mất.
- Giám sát pool acquisition và database load.

### 25.2. Dự toán connections

Giả sử đề xuất:

| Workload | Max replicas | Max pool size | Potential connections |
|---|---:|---:|---:|
| `orders-api` | 10 | 8 | 80 |
| `orders-worker` | 6 | 4 | 24 |
| `outbox-relay` | 3 | 3 | 9 |
| **Tổng từ ba workloads** | | | **113** |

Nếu database chỉ có **100 connections hiệu dụng** và cần reserve cho monitoring/migrations, cấu hình này **không đạt**. Cần giảm pool/replica ceilings, tách workload, đổi tier hoặc tối ưu throughput; không chỉ “mỗi pod có dưới 10 connections nên chắc ổn”.

Một phương án thử nghiệm ban đầu:

```text
orders-api:      10 replicas × pool 4 = 40
orders-worker:    6 replicas × pool 3 = 18
outbox-relay:     3 replicas × pool 2 =  6
                                      ---
                                      64 connections
```

Phần còn lại làm reserve cho migrations, admin, monitoring, deployments surge và các clients khác. **Đây không phải khuyến nghị pool size cuối cùng** – phải đo load test và capacity thực tế của tier đang dùng.

### 25.3. Trình tự xử lý một đơn hàng

1. Client gửi `POST /orders` với idempotency key ổn định.
2. API mượn connection từ Hikari; mở transaction ngắn.
3. API ghi `orders`, `order_requests` và `outbox_events` trong cùng transaction.
4. Nếu transaction bị deadlock/serialization failure và rollback thành công, retry **cả transaction** theo policy.
5. Nếu lỗi xảy ra sau khi gửi COMMIT, trả trạng thái cần reconcile; lần gọi lại với cùng request ID không tạo đơn mới.
6. Outbox relay publish event với event ID cố định.
7. Worker nhận event, dùng inbox/idempotency để cập nhật trạng thái và commit DB trước khi xác nhận Service Bus message.

### 25.4. Khi PostgreSQL failover

Ví dụ sự cố:

```text
09:00:00  DB primary mất kết nối; pool có 5 stale connections
09:00:02  Một số requests báo SQLState 08...
09:00:05  Pool loại connections hỏng; DNS/DB chưa hoàn toàn ổn
09:00:15  DB có thể nhận kết nối mới; API phục hồi dần
09:00:20  Outbox relay tiếp tục gửi events còn pending
```

Đây là **timeline giả lập**, không phải SLA failover Azure. Những transactions chưa biết kết quả cần được tra cứu bằng request ID. Log/metric phải phân biệt acquisition failure, login, deadlock và commit uncertainty.

### 25.5. Kết quả mong muốn

- Không có duplicate orders hoặc double payment.
- Pool active/pending giảm trở lại sau DB recovery.
- Backlog outbox có thể drain và giữ idempotency.
- Dashboard đủ data để biết lỗi bắt đầu từ failover, không phải SQL syntax.
- Không cần tắt TLS hoặc mở public database để phục hồi.

## 26. Bài tập thực hành

### Bài tập A – Cấu hình HikariCP

Bạn có Spring Boot API trên App Service và Azure SQL Database. Số replicas tối đa là 8; database có giới hạn hiệu dụng 100 connections và các clients khác cần 28 sessions.

**Nhiệm vụ:**

1. Tính pool size tối đa lý thuyết khi chỉ xét số replicas và reserve.
2. Viết một cấu hình `spring.datasource.hikari` có `maximum-pool-size`, `connection-timeout`, `max-lifetime` hợp lý để thử nghiệm.
3. Nêu lý do không nên cấu hình `maximumPoolSize=50` cho mỗi replica.
4. Liệt kê ba metric phải theo dõi khi load test.

**Hướng giải:** ngân sách còn lại `100 - 28 = 72`; chia 8 replicas được **9 connections/replica** theo mô hình đơn giản. Đây chỉ là ceiling lý thuyết, cần thêm surge reserve/DB overhead nên thử số thấp hơn và đo active/pending, query duration, DB CPU/locks trước khi quyết định.

### Bài tập B – Sửa connection leak

Một repository gọi `dataSource.getConnection()` rồi trả sớm khi không tìm thấy row, không đóng connection. Sau vài nghìn requests, toàn bộ pool busy.

**Nhiệm vụ:** thay code bằng `try-with-resources` và kiểm tra ResultSet/PreparedStatement/Connection được đóng ở mọi nhánh, kể cả exception. Mô tả cách Hikari leak detection và pool metrics giúp phát hiện.

**Hướng giải:** xem `loadStatusGood` ở phần 16. Kết thúc scope là trả connection về pool; nếu vẫn active cao, kiểm tra transaction dài và query chậm.

### Bài tập C – Deadlock/serialization retry

Hai requests cập nhật hai account theo thứ tự ngược nhau, một transaction nhận `40001` hoặc vendor deadlock code.

**Nhiệm vụ:**

1. Xác định giao dịch nào được DB rollback.
2. Thực hiện retry bằng **transaction mới**, không lặp riêng câu UPDATE lỗi.
3. Đặt max attempts, jitter, deadline.
4. Thêm stable transfer ID, unique constraint và kiểm tra business invariant tổng tiền.

**Hướng giải:** transaction bị abort sẽ được tạo lại hoàn chỉnh khi retry; nếu vượt ngưỡng, trả lỗi phù hợp và ghi metric. Không gọi payment service bên trong transaction retry nếu side effect không idempotent.

### Bài tập D – COMMIT không có ACK

Đơn `ORD-42` được INSERT, server commit thành công nhưng response mất, client retry POST.

**Nhiệm vụ:** thiết kế bảng request idempotency, unique constraint và logic trả về kết quả đã được ghi. Giải thích vì sao retry với một random order ID mới có thể tạo đơn trùng.

**Hướng giải:** cùng logical request phải dùng cùng `Idempotency-Key`; tra cứu kết quả cũ hoặc xử lý unique conflict theo schema. Không suy từ `SQLException` ở commit rằng transaction chắc chắn rollback.

### Bài tập E – Managed identity hết hạn token

Một ứng dụng Java kết nối Azure PostgreSQL bằng Entra token, khởi tạo HikariDataSource với password là token lúc startup. Sau khoảng thời gian token hết hạn, connections mới không đăng nhập được.

**Nhiệm vụ:** chỉ ra lỗi thiết kế và đề xuất giải pháp có **refresh token khi mở physical connection** theo driver/plugin/connection factory phù hợp. Kiểm tra role của DB principal và JWT audience; không log token.

**Hướng giải:** pooled connections không tự làm mới token được lưu trong password string. Dùng cơ chế token acquisition/refresh được driver và database hỗ trợ; test pool recycle và failover sau token expiration.

### Bài tập F – DB CPU cao sau autoscale

AKS scale từ 4 lên 16 pods. Mỗi pod giữ pool max 20, tổng connection ceiling tăng từ 80 lên 320. CPU DB lên 95%, query p95 tăng, retries xuất hiện.

**Nhiệm vụ:** đề xuất thay đổi pool/replica ceilings, bounded concurrency, slow SQL/index optimization và một load test để xác nhận. Giải thích vì sao tăng pool có thể làm tệ hơn.

**Hướng giải:** giới hạn tổng connections theo budget, quan sát query plans/locks/CPU, đặt retry backoff, tránh thổi phồng tải bằng nhiều workers. Pool size phải là kết quả của capacity test, không chỉ là hệ số nhân theo số pods.

### Bài tập G – Local chạy, AKS production lỗi TLS

Developer kết nối được từ laptop nhưng trên AKS nhận `SSLHandshakeException`.

**Nhiệm vụ:** kiểm tra FQDN, private DNS, CA trust store của container/JDK, certificate hostname và driver TLS mode. Nêu những thao tác không nên làm.

**Hướng giải:** xác minh đường mạng/cert chain từ chính pod; không đặt `trustServerCertificate=true` hoặc `sslmode=disable` chỉ để đi qua lỗi, không mở public network hoặc bỏ hostname verification.

### Bài tập H – Viết runbook

Đội SRE nhận alert `Hikari pending > 0` kéo dài và connection acquire p95 tăng. Soạn runbook gồm:

- Xác định số replicas và maximumPoolSize thực tế.
- Kiểm tra active/idle/pending, leak warnings và DB sessions/CPU/locks.
- Phân loại exception SQLState/vendor code và operation phase.
- Đối chiếu deployment/config/DB failover/credential rotation.
- Chọn hành động giảm tải, sửa leak/slow query hoặc điều chỉnh pool có kiểm soát.
- Xác minh hệ thống phục hồi và không sinh side effects trùng khi requests retry.

## 27. Câu hỏi tự kiểm tra

**1. JDBC là gì?** API Java chuẩn để truy cập database qua driver tương ứng; `DataSource` cung cấp các `Connection`.

**2. `Connection.close()` trong Hikari thường làm gì?** Trả connection về pool để tái sử dụng, không nhất thiết đóng TCP socket ngay.

**3. Vì sao không giữ một Connection singleton cho nhiều HTTP threads?** Connection có session/transaction state và không an toàn khi nhiều threads dùng đồng thời theo cách đó.

**4. Connection pool giúp tăng DB CPU capacity không?** Không. Nó tối ưu tái sử dụng và bounded concurrency, không làm database mạnh hơn.

**5. Nếu 20 pods, mỗi pod max pool 10, tối đa có thể bao nhiêu connections?** Khoảng 200 connections từ các pools đó, chưa kể những clients khác và giai đoạn rollout.

**6. Hikari `connectionTimeout` đo gì?** Thời gian tối đa chờ mượn connection từ pool, không phải thời gian SQL query.

**7. `PreparedStatement` giúp chống lỗi nào?** Giảm nguy cơ SQL injection ở các vị trí bindable, nhưng vẫn phải validate dữ liệu và object authorization.

**8. `trustServerCertificate=true` có nên dùng để sửa TLS lỗi ở production?** Không. Phải sửa certificate trust/hostname/network đúng cách.

**9. SQLState `40001` thường gợi ý gì?** Serialization/transaction rollback theo engine; có thể retry **cả transaction mới** khi đã rollback an toàn.

**10. Mọi `SQLException` đều retry được?** Không. Authentication, syntax, permission, constraints và commit outcome unknown cần cách xử lý khác.

**11. Tại sao không `Thread.sleep` khi transaction vẫn đang mở?** Nó giữ connection/locks lâu và gây pool exhaustion/lock contention.

**12. Lỗi connection trong lúc COMMIT có nghĩa DB rollback?** Không. Kết quả commit có thể không chắc chắn; cần idempotency key và reconcile.

**13. Unique constraint có tác dụng gì trong idempotency?** Ngăn hai transactions đồng thời tạo cùng logical request record; pre-check một mình có race condition.

**14. Transactional outbox giải quyết vấn đề gì?** Ghi business row và event durable cùng transaction, tránh mất event sau DB commit trước publish broker.

**15. Managed identity có quyền Azure RBAC Contributor trên DB resource tự được SELECT?** Không. Cần DB principal và data permissions đúng engine.

**16. Tại sao token Entra dùng làm password JDBC ở startup có thể lỗi về sau?** Token có hạn; physical connections mở sau khi hết hạn cần token mới.

**17. Khi Hikari active cao, có nên tăng pool ngay?** Không. Đầu tiên kiểm tra leaks, long transactions, slow SQL, DB capacity và tổng replicas.

**18. Tại sao `@Retryable` đặt bên trong `@Transactional` có thể sai?** Có thể retry trong transaction đã aborted; mỗi retry cần transaction mới theo thiết kế.

**19. Virtual threads có giải quyết DB connection limit?** Không. Chúng không tăng số connections/capacity của database.

**20. Vì sao read replica có thể làm người dùng không thấy cập nhật vừa ghi?** Replica có thể lag; cần thiết kế read-your-writes/consistency.

## 28. Checklist triển khai production

- [ ] Đã xác định đúng Azure SQL/PostgreSQL/MySQL engine và driver JDBC tương thích JDK.
- [ ] JDBC URL dùng FQDN chính thức, đúng database/port và TLS hostname verification.
- [ ] Network private/public, DNS, route, firewall và private endpoint được kiểm tra từ runtime thực tế.
- [ ] Không có DB password, access token hoặc connection string có secret trong Git/image/log.
- [ ] Nếu dùng Entra/managed identity, DB principal/permissions và token refresh của pool đã được xác minh.
- [ ] Runtime identity có quyền dữ liệu tối thiểu; migration/admin identity tách riêng.
- [ ] Mỗi application instance có DataSource/pool tái sử dụng, không tạo pool theo request.
- [ ] JDBC Connections, PreparedStatements và ResultSets được đóng đúng mọi nhánh.
- [ ] Đã cấu hình `maximumPoolSize`, `minimumIdle`, `connectionTimeout`, `validationTimeout`, `maxLifetime` phù hợp.
- [ ] Tổng `max replicas × pools × max size` và rollout surge có ngân sách DB reserve.
- [ ] Đã đo pool active/idle/pending, acquisition latency, creation time và timeout count.
- [ ] Đã đo DB CPU/IO/connections/locks/deadlocks và slow SQL/query plans.
- [ ] Retry chỉ áp dụng cho lỗi được phân loại transient/aborted, có max attempts, jitter, deadline.
- [ ] Mỗi retry transaction diễn ra trong transaction mới, không sleep trong transaction.
- [ ] Đã phân biệt acquisition failure, query failure, deadlock và commit outcome unknown.
- [ ] Ghi đơn/thanh toán hoặc workflow side effect có idempotency key/unique constraint phù hợp.
- [ ] Có transactional outbox khi DB commit phải phát message tin cậy.
- [ ] Không chạy HTTP/API bên ngoài trong transaction DB kéo dài nếu có phương án tách workflow.
- [ ] App readiness/liveness và graceful shutdown được thiết kế cho DB outages và scale-in.
- [ ] Đã thử wrong credentials, TLS/DNS failure, pool exhaustion, failover, deadlock và token rotation.
- [ ] Đã thử duplicate/concurrent requests và missing COMMIT ACK trong lab khi khả thi.
- [ ] Có alerts/runbook, không log dữ liệu nhạy cảm, và có bảng baseline capacity.
- [ ] Đã đánh giá chi phí DB tier, replicas, network, monitoring và retry load.

## 29. Kết luận

**JDBC** cho phép Java tương tác với các cơ sở dữ liệu quan hệ trên Azure qua driver/connection phù hợp; **HikariCP connection pool** giúp tái sử dụng connections và giới hạn concurrency; **retry** giúp ứng dụng phục hồi khi gặp các lỗi có tính chất tạm thời như deadlock, serialization failure hoặc kết nối bị gián đoạn. Nhưng cả ba chỉ hoạt động an toàn khi đi kèm **TLS, authentication đúng, transaction boundary rõ, pool capacity planning, timeout có ngân sách và quan sát toàn hệ thống**.

Nguyên tắc quan trọng nhất là **không retry một thao tác ghi chỉ vì thấy SQLException**. Phải biết lỗi ở giai đoạn nào, transaction đã rollback hay chưa, và COMMIT có kết quả chắc chắn hay không. Với những nghiệp vụ quan trọng, **idempotency key, unique constraint, transactional outbox và đối soát kết quả** giúp tránh side effects trùng. Khi ứng dụng Java xử lý đúng vòng đời Connection, giới hạn tổng số sessions trên mọi replicas và kiểm thử failover/recovery, hệ thống mới có thể tận dụng khả năng quản lý của Azure database mà vẫn giữ hiệu năng, tính nhất quán và độ tin cậy trong production.
