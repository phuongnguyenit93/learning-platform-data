# OracleDataSource, thuộc tính kết nối và quản lý bí mật

## 1. OracleDataSource trong kiến trúc JDBC

JDBC cung cấp giao diện chuẩn javax.sql.DataSource để ứng dụng lấy kết nối tới database. Oracle triển khai giao diện này bằng lớp **oracle.jdbc.pool.OracleDataSource**.

OracleDataSource gom cấu hình kết nối vào một đối tượng:

- Database URL hoặc các thành phần host, port, service name.
- Driver type.
- Database username.
- Password hoặc cơ chế xác thực thay thế.
- Các connection properties của Oracle JDBC.
- Login timeout và log writer.

Ứng dụng gọi getConnection() để tạo một JDBC Connection. DataSource cũng có thể được bind vào JNDI để application server hoặc framework cung cấp cho ứng dụng bằng tên logic.

Điều cần phân biệt ngay:

- **OracleDataSource** là một DataSource tạo kết nối vật lý; bản thân nó không phải connection pool tổng quát.
- **Universal Connection Pool (UCP)** cung cấp pool-enabled DataSource để mượn/trả connection và quản lý pool lifecycle.
- **JNDI** là cơ chế đặt tên/lookup một DataSource đã được cấu hình, thường do application server hoặc container quản lý.

Trong ứng dụng nhỏ hoặc tác vụ ngắn, OracleDataSource có thể đủ. Với web application hoặc service xử lý nhiều request, nên dùng UCP hoặc connection pool do application server quản lý để tái sử dụng connection, giới hạn số session và xử lý connection lỗi.

## 2. Các lớp và interface quan trọng

| Lớp/interface | Vai trò |
| --- | --- |
| javax.sql.DataSource | JDBC standard interface để lấy Connection |
| oracle.jdbc.pool.OracleDataSource | Oracle implementation của DataSource |
| oracle.jdbc.OracleConnection | JDBC Connection mở rộng các tính năng Oracle |
| oracle.ucp.jdbc.PoolDataSource | UCP DataSource dùng để mượn connection từ pool |
| oracle.ucp.jdbc.PoolDataSourceFactory | Factory tạo PoolDataSource |
| oracle.jdbc.xa.client.OracleXADataSource | Oracle XA connection factory |
| javax.naming.Context | JNDI naming context |

Import thông thường:

~~~java
import java.sql.Connection;
import java.sql.SQLException;
import oracle.jdbc.pool.OracleDataSource;
~~~

Oracle JDBC driver JAR phải có trong runtime classpath/module path. Nếu dùng UCP, cần thêm UCP JAR tương thích với Oracle JDBC driver và JDK đang chạy.

### 2.1. OracleDataSource không thay thế JDBC Connection

DataSource là factory. Mỗi lần gọi getConnection() nhận một Connection để thực thi SQL:

~~~java
OracleDataSource dataSource = new OracleDataSource();
dataSource.setURL("jdbc:oracle:thin:@//dbhost.example.com:1521/appsvc");
dataSource.setUser("APP_RUNTIME");
dataSource.setPassword(passwordFromSecretStore);

try (Connection connection = dataSource.getConnection()) {
    // Thực hiện JDBC work.
}
~~~

Trong ví dụ, passwordFromSecretStore là giá trị được lấy từ một nguồn bí mật tại runtime. Không ghi password thật vào source code hoặc commit file cấu hình chứa password.

### 2.2. Vì sao DataSource được khuyến nghị?

DataSource:

- Tách cấu hình kết nối khỏi logic truy vấn.
- Có thể được cấu hình bằng JavaBeans setter.
- Có thể được bind/lookup qua JNDI.
- Hỗ trợ cấu hình pool thông qua một pool-enabled DataSource.
- Giảm phụ thuộc trực tiếp vào DriverManager trong code nghiệp vụ.

DriverManager vẫn tồn tại và vẫn có thể dùng, nhưng DataSource thuận tiện hơn cho ứng dụng enterprise, dependency injection và container-managed resource.

## 3. Tạo OracleDataSource và mở kết nối

### 3.1. Cấu hình bằng URL và setter

Ví dụ JDBC Thin:

~~~java
import java.sql.Connection;
import java.sql.SQLException;
import oracle.jdbc.pool.OracleDataSource;

public final class OracleConnectionFactory {
    private OracleConnectionFactory() {
    }

    public static Connection open(
            String username,
            String password) throws SQLException {

        OracleDataSource dataSource = new OracleDataSource();
        dataSource.setURL(
            "jdbc:oracle:thin:@//dbhost.example.com:1521/appsvc"
        );
        dataSource.setUser(username);
        dataSource.setPassword(password);

        return dataSource.getConnection();
    }
}
~~~

Trong ứng dụng thật, không nên tạo một OracleDataSource mới cho từng request. Hãy cấu hình DataSource một lần khi khởi động ứng dụng, sau đó chia sẻ DataSource hoặc để container quản lý.

### 3.2. Cấu hình bằng các thuộc tính host/port/service

OracleDataSource có các setter:

~~~java
OracleDataSource dataSource = new OracleDataSource();
dataSource.setDriverType("thin");
dataSource.setServerName("dbhost.example.com");
dataSource.setPortNumber(1521);
dataSource.setServiceName("appsvc.example.com");
dataSource.setUser("APP_RUNTIME");
dataSource.setPassword(passwordFromSecretStore);

try (Connection connection = dataSource.getConnection()) {
    // JDBC work.
}
~~~

Đây là cách dùng các property rời rạc. Nếu đã đặt URL, Oracle JDBC bỏ qua các property serverName, portNumber, networkProtocol, databaseName, driverType và tnsEntry theo quy tắc precedence của DataSource. Không cấu hình URL và một bộ property rời rạc mâu thuẫn rồi chờ driver tự kết hợp chúng.

### 3.3. Cấu hình bằng Properties

OracleDataSource hỗ trợ setConnectionProperties(Properties) để truyền các connection property của Oracle JDBC:

~~~java
import java.sql.Connection;
import java.util.Properties;
import oracle.jdbc.pool.OracleDataSource;

Properties properties = new Properties();
properties.setProperty("user", "APP_RUNTIME");
properties.setProperty("password", passwordFromSecretStore);
properties.setProperty("oracle.net.CONNECT_TIMEOUT", "5");
properties.setProperty("oracle.net.OUTBOUND_CONNECT_TIMEOUT", "10");
properties.setProperty("oracle.jdbc.ReadTimeout", "30000");

OracleDataSource dataSource = new OracleDataSource();
dataSource.setURL("jdbc:oracle:thin:@//dbhost.example.com:1521/appsvc");
dataSource.setConnectionProperties(properties);

try (Connection connection = dataSource.getConnection()) {
    // JDBC work.
}
~~~

Tên property, đơn vị và khả năng hỗ trợ phụ thuộc driver type và phiên bản. Không sao chép property của JDBC Thin sang OCI hoặc driver version khác nếu chưa kiểm tra Oracle JDBC API Reference.

### 3.4. Dùng getConnection(username, password)

DataSource cung cấp overload:

~~~java
Connection connection = dataSource.getConnection(
    runtimeUsername,
    runtimePassword
);
~~~

Username/password truyền vào getConnection được ưu tiên hơn các property username/password đã đặt trên DataSource. Cách này hữu ích khi cùng một DataSource factory cần mở kết nối bằng credential khác nhau, nhưng phải cân nhắc connection pooling và credential isolation.

Không đưa nhiều người dùng cuối vào cùng pool nếu pool không được thiết kế để tách identity, quyền và session state theo từng credential.

## 4. OracleDataSource properties

### 4.1. Standard properties

Các property phổ biến theo Oracle JDBC 19c:

| Property | Kiểu | Ý nghĩa |
| --- | --- | --- |
| databaseName | String | Tên database theo mô hình property rời rạc |
| dataSourceName | String | Tên underlying data source |
| description | String | Mô tả DataSource |
| networkProtocol | String | Network protocol; chủ yếu áp dụng cho OCI |
| password | String | Password của user kết nối |
| portNumber | int | Listener port |
| serverName | String | Host/server |
| user | String | Database username |
| loginTimeout | int | Thời gian tối đa chờ tạo kết nối, tính bằng giây |
| logWriter | PrintWriter | Nơi ghi log của DataSource |

Vì lý do bảo mật, OracleDataSource không cung cấp getPassword(). Không nên tìm cách đọc lại password từ object sau khi đã cấu hình.

### 4.2. Oracle extension properties

Một số property mở rộng thường gặp:

| Property | Ý nghĩa |
| --- | --- |
| driverType | thin, oci hoặc kprb |
| url | JDBC URL |
| serviceName | Oracle database service name |
| tnsEntry | TNS alias trong tnsnames.ora |
| connectionProperties | Các property cho connection |
| connectionCachingEnabled | Cấu hình implicit connection cache cũ |
| connectionCacheName | Tên implicit cache cũ |
| fastConnectionFailoverEnabled | Fast Connection Failover cho cơ chế cache/pool tương ứng |
| ONSConfiguration | Cấu hình ONS/FAN notification |
| maxStatements | Statement cache property trong cơ chế tương ứng |

Một số thuộc tính liên quan implicit connection cache cũ không nên được chọn làm nền tảng cho thiết kế pool mới. Với ứng dụng cần pooling, đánh giá UCP hoặc pool do application server quản lý.

### 4.3. setConnectionProperties và setConnectionCacheProperties

Hai method có mục đích khác nhau:

- setConnectionProperties: cấu hình thuộc tính cho connection được tạo bởi factory.
- setConnectionCacheProperties: cấu hình cache cũ của OracleDataSource trong những mô hình legacy tương ứng.

Không đưa pool sizing như minPoolSize/maxPoolSize vào connectionProperties của OracleDataSource. Pool sizing là trách nhiệm của UCP/application server.

## 5. JDBC URL: service name, SID và TNS alias

### 5.1. Easy Connect với SERVICE_NAME

Định dạng phổ biến:

~~~text
jdbc:oracle:thin:@//host:port/service_name
~~~

Ví dụ:

~~~text
jdbc:oracle:thin:@//dbhost.example.com:1521/sales.example.com
~~~

Đây là dạng phù hợp với service-based connection, PDB service và nhiều kiến trúc RAC.

### 5.2. TNS alias

~~~text
jdbc:oracle:thin:@APPDB
~~~

Trong tnsnames.ora:

~~~text
APPDB =
  (DESCRIPTION =
    (ADDRESS =
      (PROTOCOL = TCP)
      (HOST = dbhost.example.com)
      (PORT = 1521)
    )
    (CONNECT_DATA =
      (SERVICE_NAME = appsvc.example.com)
    )
  )
~~~

Để driver tìm đúng tnsnames.ora, có thể cấu hình Oracle Net admin directory:

~~~java
Properties properties = new Properties();
properties.setProperty(
    "oracle.net.tns_admin",
    "/opt/app/oracle/network/admin"
);

OracleDataSource dataSource = new OracleDataSource();
dataSource.setURL("jdbc:oracle:thin:@APPDB");
dataSource.setConnectionProperties(properties);
~~~

Đường dẫn phải tồn tại trên host/container chạy ứng dụng. Không mặc định rằng Oracle JDBC sẽ đọc đúng thư mục TNS chỉ vì máy DBA có ORACLE_HOME.

### 5.3. Full connect descriptor

Khi cần nhiều address, retry hoặc các tùy chọn Oracle Net:

~~~text
jdbc:oracle:thin:@
(DESCRIPTION =
  (CONNECT_TIMEOUT = 10)
  (TRANSPORT_CONNECT_TIMEOUT = 5)
  (RETRY_COUNT = 3)
  (ADDRESS_LIST =
    (ADDRESS =
      (PROTOCOL = TCP)
      (HOST = dbnode1.example.com)
      (PORT = 1521)
    )
    (ADDRESS =
      (PROTOCOL = TCP)
      (HOST = dbnode2.example.com)
      (PORT = 1521)
    )
  )
  (CONNECT_DATA =
    (SERVICE_NAME = appsvc.example.com)
  )
)
~~~

Connect descriptor cho phép khai báo nhiều endpoint và timeout/retry ở tầng Oracle Net. Cần bảo đảm các address thực sự phục vụ cùng service hoặc được cấu hình cho load balancing/failover phù hợp.

### 5.4. SID syntax cũ

Một số kết nối legacy dùng:

~~~text
jdbc:oracle:thin:@host:1521:ORCL
~~~

Phần cuối ở dạng SID, không phải service name. Với RAC, PDB hoặc ứng dụng cần định tuyến theo service, nên dùng SERVICE_NAME thay vì gắn cứng SID/instance.

### 5.5. Service name và SID không giống nhau

| Khái niệm | Ý nghĩa |
| --- | --- |
| SID | Định danh instance Oracle |
| SERVICE_NAME | Dịch vụ database mà client yêu cầu |
| TNS alias | Tên logic trỏ tới connect descriptor |
| Host/port | Endpoint mạng của listener |

Trong môi trường RAC, service có thể chạy trên nhiều instance và được relocate. Nếu ứng dụng gắn cứng SID, khả năng tận dụng service management, load balancing và failover sẽ giảm.

### 5.6. URL không nên chứa credential

Không viết:

~~~text
jdbc:oracle:thin:APP_RUNTIME/password@//dbhost:1521/appsvc
~~~

URL có thể xuất hiện trong log, exception, metrics, process list, configuration dump hoặc công cụ giám sát. Đặt URL chỉ chứa endpoint/service; truyền credential qua secret provider, wallet hoặc cơ chế xác thực phù hợp.

## 6. Driver type: Thin, OCI và KPRB

| Driver type | Đặc điểm | Khi dùng |
| --- | --- | --- |
| Thin | Java driver thuần, kết nối trực tiếp qua Oracle Net | Lựa chọn phổ biến cho ứng dụng Java |
| OCI | Dùng Oracle Client/native OCI libraries | Khi cần tính năng hoặc môi trường phụ thuộc OCI |
| KPRB | Internal server-side driver, dùng kết nối nội bộ | Java chạy bên trong Oracle Database JVM |

Với ứng dụng Java chạy ngoài database, JDBC Thin thường đơn giản nhất vì không yêu cầu Oracle Client cài trên host ứng dụng.

OCI yêu cầu native library và cấu hình Oracle Client phù hợp. Nếu chọn OCI, kiểm tra ORACLE_HOME, PATH/LD_LIBRARY_PATH, bitness, native library version và Oracle Net configuration.

KPRB là internal driver; các connection properties thông thường có thể bị bỏ qua. Không dùng KPRB như lựa chọn thay thế Thin cho ứng dụng chạy trên máy application server.

## 7. Thứ tự ưu tiên và xung đột thuộc tính

Đây là nguyên nhân phổ biến khiến ứng dụng kết nối nhầm user hoặc nhầm database.

### 7.1. User/password trong URL

Nếu URL chứa username/password, giá trị đó có thể được ưu tiên hơn user/password cấu hình riêng trên DataSource.

Không đưa credential vào URL để tránh tình trạng cấu hình rời rạc bị bỏ qua và tránh lộ secret.

### 7.2. getConnection(username, password)

Credential truyền vào overload getConnection(username, password) được ưu tiên hơn các property username/password đã đặt trên DataSource.

### 7.3. URL overrides các property rời rạc

Khi property url được đặt, các property tnsEntry, driverType, portNumber, networkProtocol, serverName và databaseName bị bỏ qua theo quy tắc Oracle JDBC.

Khi tnsEntry được đặt và URL không được đặt, các property databaseName, serverName, portNumber và networkProtocol bị bỏ qua.

### 7.4. KPRB

Nếu driverType là kprb, các property setting khác bị bỏ qua vì driver dùng implicit internal connection.

### 7.5. Quy tắc cấu hình dễ kiểm soát

Chọn một kiểu cấu hình rõ ràng:

1. Một URL đầy đủ, không chứa credential.
2. Một nguồn credential riêng.
3. Một nhóm connection properties có chủ đích.
4. Không khai báo hai giá trị khác nhau cho cùng một thông tin endpoint.

Sau khi cấu hình, xác minh session:

~~~sql
SELECT USER AS database_user,
       SYS_CONTEXT('USERENV', 'SERVICE_NAME') AS service_name,
       SYS_CONTEXT('USERENV', 'INSTANCE_NAME') AS instance_name,
       SYS_CONTEXT('USERENV', 'CON_NAME') AS container_name
FROM dual;
~~~

## 8. Các connection property quan trọng

Không phải property nào cũng cần cấu hình. Chỉ thêm khi có yêu cầu đo được và đã xác nhận với Oracle JDBC version đang dùng.

### 8.1. Timeout khi tạo kết nối

| Thuộc tính | Đơn vị | Phạm vi |
| --- | --- | --- |
| DataSource loginTimeout | Giây | Thời gian tối đa DataSource chờ mở connection |
| oracle.net.CONNECT_TIMEOUT | Giây | Thời gian kết nối socket tới listener |
| oracle.net.OUTBOUND_CONNECT_TIMEOUT | Giây | Thời gian thiết lập session/network negotiation với service |
| UCP connectionWaitTimeout | Giây | Thời gian chờ một connection được trả về pool |

CONNECT_TIMEOUT thành công chỉ có nghĩa listener nhận kết nối socket; chưa chứng minh database service đã sẵn sàng hoặc authentication đã hoàn tất.

OUTBOUND_CONNECT_TIMEOUT bao phủ quá trình kết nối và thương lượng session theo Oracle Net, không bao gồm mọi giai đoạn authentication.

UCP connectionWaitTimeout là thời gian chờ mượn connection khi pool đã đạt max size và không có connection rảnh. Nó khác timeout kết nối tới listener.

### 8.2. Read timeout

Thin driver hỗ trợ:

~~~java
properties.setProperty("oracle.jdbc.ReadTimeout", "30000");
~~~

Giá trị tính bằng milliseconds. Read timeout giới hạn thời gian đọc từ socket. Nó không phải statement execution timeout theo nghĩa database sẽ luôn dừng SQL đúng thời điểm.

Oracle JDBC ghi nhận rằng ReadTimeout và Connection.setNetworkTimeout có thể có tương tác với cấu hình Dead Connection Detection cũ. Kiểm tra DCD/Oracle Net và thử nghiệm trên đúng môi trường.

### 8.3. Statement query timeout

JDBC cung cấp:

~~~java
try (var statement = connection.createStatement()) {
    statement.setQueryTimeout(30);
    statement.executeQuery("SELECT 1 FROM dual");
}
~~~

setQueryTimeout là thời gian statement; driver thường dùng cơ chế cancel để yêu cầu server dừng. Nếu network hoặc database server bị treo, cancel không nhất thiết giải phóng thread đúng ngay tại mốc timeout.

Không đánh đồng:

- Login timeout.
- Socket connect timeout.
- Session negotiation timeout.
- Socket read timeout.
- Statement query timeout.
- Pool borrow timeout.
- HTTP request timeout của ứng dụng.

Các timeout phải được phối hợp theo một ngân sách thời gian thống nhất.

### 8.4. Ví dụ cấu hình timeout

~~~java
Properties properties = new Properties();
properties.setProperty("oracle.net.CONNECT_TIMEOUT", "5");
properties.setProperty("oracle.net.OUTBOUND_CONNECT_TIMEOUT", "10");
properties.setProperty("oracle.jdbc.ReadTimeout", "30000");

OracleDataSource dataSource = new OracleDataSource();
dataSource.setURL("jdbc:oracle:thin:@//dbhost.example.com:1521/appsvc");
dataSource.setLoginTimeout(15);
dataSource.setConnectionProperties(properties);
~~~

Các con số chỉ minh họa. Nếu connect descriptor có CONNECT_TIMEOUT hoặc TRANSPORT_CONNECT_TIMEOUT, giá trị trong URL/descriptor có thể ưu tiên hơn property tương ứng.

### 8.5. TNS_ADMIN

Property:

~~~java
properties.setProperty(
    "oracle.net.tns_admin",
    "/opt/app/oracle/network/admin"
);
~~~

Chỉ tới thư mục chứa tnsnames.ora, sqlnet.ora và các file Oracle Net cần thiết. Không đặt path này vào repository nếu mỗi môi trường có cấu trúc filesystem khác nhau; đưa qua cấu hình deployment.

### 8.6. Row prefetch và batch

Oracle JDBC có các extension property như defaultRowPrefetch và defaultBatchValue. Chúng có thể ảnh hưởng lượng dữ liệu driver lấy trước hoặc batch behavior.

~~~java
properties.setProperty("defaultRowPrefetch", "100");
~~~

Không tăng prefetch theo cảm tính. ResultSet lớn, LOB/streaming, mạng WAN và heap size có thể khiến giá trị quá cao làm tăng memory pressure. Đo round trip, heap, response size và latency trước khi đổi.

### 8.7. Network compression

Oracle JDBC Thin từ 12.2 hỗ trợ network data compression:

~~~java
properties.setProperty("oracle.net.networkCompression", "on");
properties.setProperty("oracle.net.networkCompressionThreshold", "1024");
~~~

Compression có thể hữu ích trên WAN khi truyền nhiều payload, nhưng có chi phí CPU và không áp dụng cho streamed data theo tài liệu Oracle. Benchmark trước khi bật cho mọi workload.

## 9. Quản lý bí mật kết nối

Password database là secret có giá trị cao. Nếu lộ password của application account, kẻ tấn công có thể truy cập dữ liệu hoặc thực hiện thao tác trong phạm vi privilege của account đó.

Nguyên tắc:

- Không hardcode password trong Java source.
- Không commit password vào Git.
- Không nhúng password trong JDBC URL.
- Không ghi password, token hoặc wallet password vào log.
- Không in Properties object chứa credential ra console.
- Không lưu secret trong file .properties không mã hóa trên filesystem dùng chung.
- Dùng account riêng cho từng ứng dụng hoặc service.
- Cấp quyền tối thiểu cho runtime account.
- Có quy trình rotation, revoke và xử lý incident khi secret lộ.

### 9.1. Nguồn secret nên dùng

Ưu tiên theo kiến trúc:

1. Oracle Secure External Password Store (client-side wallet).
2. Secret manager của cloud hoặc platform deployment.
3. Secret store do application server/container quản lý.
4. Credential provider do tổ chức quản lý, có kiểm soát ACL và rotation.

Environment variable có thể dùng để inject cấu hình trong một số môi trường, nhưng cần hiểu rằng nó vẫn có thể bị lộ qua process inspection, crash dump, diagnostics hoặc cấu hình deployment. Không coi environment variable là một vault tự động an toàn.

### 9.2. Không ghi password vào file cấu hình thường

Không nên:

~~~properties
db.url=jdbc:oracle:thin:@//dbhost:1521/appsvc
db.user=APP_RUNTIME
db.password=VerySecretPassword
~~~

File có thể bị đọc bởi người dùng hệ điều hành, backup agent, CI logs hoặc được commit nhầm.

Nên tách endpoint và username khỏi password:

~~~properties
db.url=jdbc:oracle:thin:@//dbhost:1521/appsvc
db.user=APP_RUNTIME
db.secretRef=prod/oracle/app-runtime
~~~

Ứng dụng đọc secretRef từ secret provider khi khởi động hoặc theo cơ chế rotation của nền tảng.

### 9.3. Truyền password qua biến runtime

~~~java
String username = configuration.get("db.user");
String password = secretProvider.read("prod/oracle/app-runtime");

OracleDataSource dataSource = new OracleDataSource();
dataSource.setURL(configuration.get("db.url"));
dataSource.setUser(username);
dataSource.setPassword(password);
~~~

Ví dụ secretProvider là abstraction của ứng dụng. Không log password và hạn chế thời gian tồn tại của bản copy trong memory khi có thể. Java String không thể được zero hóa trực tiếp; nếu cần kiểm soát buffer tốt hơn, dùng API secret provider hỗ trợ char[]/credential object và xử lý theo lifecycle.

## 10. Oracle Wallet và Secure External Password Store

### 10.1. Hai mục đích của wallet

Oracle wallet có thể chứa:

- Credential username/password cho Secure External Password Store.
- Certificate và private key cho TLS/mTLS.

Credential store và PKI store là hai mục đích khác nhau, dù có thể cùng nằm trong một wallet container tùy cấu hình. Phải phân biệt wallet dùng để đăng nhập database bằng password với wallet dùng để xác thực certificate.

### 10.2. Vì sao dùng Secure External Password Store?

Secure External Password Store lưu credential ở client-side Oracle wallet. JDBC driver có thể lấy username/password từ wallet thay vì yêu cầu ứng dụng nhúng credential trong source code, batch job hoặc script.

Lợi ích:

- Không phải lưu password trong Java source.
- Có thể thay đổi credential trong wallet mà không sửa code ứng dụng.
- Hỗ trợ quản lý credential tập trung cho các batch/application client.
- Wallet file có thể được giới hạn quyền đọc cho owner.

Wallet vẫn là secret. Nếu auto-login wallet bị đánh cắp và attacker có thể sử dụng nó trong đúng môi trường, credential có thể bị lạm dụng. Bảo vệ file, thư mục, backup và quyền OS.

### 10.3. Tạo wallet

Ví dụ trên host client:

~~~text
mkstore -wrl /opt/app/oracle/wallet -create
~~~

mkstore sẽ hỏi password wallet. Không truyền password wallet thành tham số dòng lệnh có thể bị lưu trong shell history/process list.

### 10.4. Tạo credential cho database service

~~~text
mkstore -wrl /opt/app/oracle/wallet
  -createCredential APPDB APP_RUNTIME
~~~

Lệnh sẽ hỏi database password. APPDB phải là connect identifier/TNS alias/service string khớp với tên được dùng lúc kết nối.

Liệt kê credential:

~~~text
mkstore -wrl /opt/app/oracle/wallet -listCredential
~~~

Danh sách hiển thị alias và username, không hiển thị password.

### 10.5. Cấu hình wallet cho JDBC

Oracle JDBC 19c hỗ trợ connection property:

~~~text
oracle.net.wallet_location
~~~

Ví dụ:

~~~java
Properties properties = new Properties();
properties.setProperty(
    "oracle.net.wallet_location",
    "(SOURCE=(METHOD=FILE)(METHOD_DATA=(DIRECTORY=/opt/app/oracle/wallet)))"
);

OracleDataSource dataSource = new OracleDataSource();
dataSource.setURL("jdbc:oracle:thin:@APPDB");
dataSource.setConnectionProperties(properties);

try (Connection connection = dataSource.getConnection()) {
    // Driver retrieves the credential from the wallet.
}
~~~

Trong ví dụ, không đặt user/password trong URL hoặc Properties. Oracle JDBC tìm credential trong Properties trước, sau đó URL, rồi mới tới wallet. Vì vậy, nếu vẫn khai báo password trực tiếp thì wallet có thể không được dùng.

Có thể chỉ định wallet location theo dạng file URI hoặc Oracle Net descriptor. Kiểm tra cú pháp với đúng JDBC driver.

### 10.6. PKCS12 và auto-login wallet

Wallet auto-login thường có file cwallet.sso. Wallet PKCS12 có thể cần wallet password qua property oracle.net.wallet_password nếu không bật auto-login.

Không lưu wallet password trong source code. Nếu dùng auto-login wallet, kiểm soát chặt file cwallet.sso và quyền truy cập thư mục.

### 10.7. Rotation credential trong wallet

Quy trình khái quát:

1. DBA thay password database theo kế hoạch.
2. Cập nhật credential tương ứng trong wallet bằng mkstore.
3. Xác nhận ứng dụng có thể mở connection mới.
4. Drain/refresh pool để loại bỏ connection cần được thay thế.
5. Xác nhận lỗi authentication không xuất hiện trong log.
6. Thu hồi/loại bỏ credential cũ theo chính sách.

Credential đã được pool dùng khi tạo physical connection có thể vẫn tồn tại trong pool. Thay password trong wallet không tự động biến các connection hiện hữu thành connection mới.

## 11. TLS và TCPS

### 11.1. TCP và TCPS

- TCP là transport thông thường, có thể kết hợp Oracle Native Network Encryption/Integrity.
- TCPS là Oracle Net protocol dùng TLS để bảo vệ kênh mạng và xác thực server/client theo cấu hình.

Ví dụ connect descriptor:

~~~text
jdbc:oracle:thin:@
(DESCRIPTION =
  (ADDRESS =
    (PROTOCOL = TCPS)
    (HOST = db.example.com)
    (PORT = 2484)
  )
  (CONNECT_DATA =
    (SERVICE_NAME = appsvc.example.com)
  )
  (SECURITY =
    (TLS_SERVER_DN_MATCH = TRUE)
  )
)
~~~

Port 2484 chỉ là ví dụ; dùng listener TCPS port thực tế.

### 11.2. Server DN matching

DN matching giúp client xác minh certificate thuộc đúng server dự kiến. Nếu chỉ kiểm tra certificate chain mà không kiểm tra danh tính server, client có thể tin nhầm một endpoint có certificate hợp lệ nhưng không phải database mong muốn.

Oracle khuyến nghị bật TLS_SERVER_DN_MATCH và cấu hình host/DN khớp certificate. Với full DN matching, dùng TLS_SERVER_CERT_DN theo tài liệu Oracle. Từ Oracle Database 19c Release 2 trở lên, hành vi partial DN matching đã được siết chặt; không giả định SERVICE_NAME luôn được dùng thay cho hostname.

### 11.3. One-way TLS và mutual TLS

| Kiểu | Mô tả |
| --- | --- |
| One-way TLS | Client xác thực certificate của server |
| Mutual TLS (mTLS) | Client và server xác thực certificate của nhau |

One-way TLS thường chỉ cần trust server certificate. mTLS cần client certificate/private key và server phải được cấu hình yêu cầu hoặc cho phép client authentication.

### 11.4. Wallet cho TLS

Oracle JDBC Thin dùng JSSE và có thể dùng Oracle wallet làm truststore/keystore theo cấu hình. Với TCPS, wallet có thể chứa CA certificate và client certificate nếu dùng mTLS.

Không tắt certificate validation chỉ để kết nối thành công. Nếu TLS handshake lỗi:

1. Kiểm tra certificate chain.
2. Kiểm tra hostname/DN.
3. Kiểm tra expiry và thời gian hệ thống.
4. Kiểm tra wallet location/permission.
5. Kiểm tra listener đang dùng TCPS đúng port.
6. Kiểm tra client/server TLS version và cipher policy.

## 12. Connection pooling bằng UCP

### 12.1. Vì sao cần pool?

Tạo database connection mới có chi phí network handshake, authentication, session initialization và resource allocation. Với ứng dụng web, tạo connection mới cho từng request có thể làm tăng latency và session churn.

Pool giữ một số physical connection và cho request mượn connection handle. Khi ứng dụng close handle, connection thường được trả lại pool để request khác sử dụng.

Oracle Universal Connection Pool cung cấp pool-enabled DataSource:

- oracle.ucp.jdbc.PoolDataSource.
- oracle.ucp.jdbc.PoolDataSourceFactory.

UCP dùng OracleDataSource làm connection factory để tạo physical connection.

### 12.2. Ví dụ cấu hình UCP

~~~java
import java.sql.Connection;
import java.sql.SQLException;
import oracle.ucp.jdbc.PoolDataSource;
import oracle.ucp.jdbc.PoolDataSourceFactory;

public final class UcpFactory {
    private UcpFactory() {
    }

    public static PoolDataSource create(
            String username,
            String password) throws SQLException {

        PoolDataSource pool =
            PoolDataSourceFactory.getPoolDataSource();

        pool.setConnectionFactoryClassName(
            "oracle.jdbc.pool.OracleDataSource"
        );
        pool.setURL(
            "jdbc:oracle:thin:@//dbhost.example.com:1521/appsvc"
        );
        pool.setUser(username);
        pool.setPassword(password);

        pool.setConnectionPoolName("APP_POOL");
        pool.setInitialPoolSize(2);
        pool.setMinPoolSize(2);
        pool.setMaxPoolSize(20);
        pool.setConnectionWaitTimeout(10);

        return pool;
    }
}
~~~

Các giá trị min/max chỉ là ví dụ. Tính tổng connection tối đa của tất cả application replica, batch worker và service trước khi đặt maxPoolSize.

### 12.3. Mượn và trả connection

~~~java
try (Connection connection = pool.getConnection()) {
    // Execute SQL and finish the transaction.
}
~~~

Với UCP, close connection handle trả connection về pool. Không giữ connection trong static field hoặc chia sẻ cùng một Connection cho nhiều thread đồng thời.

### 12.4. Pool properties thường dùng

| Property | Ý nghĩa |
| --- | --- |
| initialPoolSize | Số connection khởi tạo |
| minPoolSize | Số connection tối thiểu |
| maxPoolSize | Số connection tối đa |
| connectionWaitTimeout | Thời gian chờ connection được trả về pool |
| inactiveConnectionTimeout | Thời gian connection rảnh có thể ở trong pool trước khi bị đóng |
| abandonedConnectionTimeout | Thời gian connection bị mượn nhưng không hoạt động trước khi bị xem là abandoned |
| validateConnectionOnBorrow | Kiểm tra connection khi mượn |
| SQLForValidateConnection | SQL dùng để validate khi bật validate on borrow |
| timeToLiveConnectionTimeout | Tuổi tối đa connection được giữ trong trạng thái borrowed |
| maxConnectionReuseTime | Thời gian tối đa connection được tái sử dụng theo cấu hình |

Không bật mọi timeout cùng lúc mà không hiểu tương tác. Abandoned connection timeout quá thấp có thể thu hồi connection của request hợp lệ đang chạy lâu.

### 12.5. Validate connection

Ví dụ:

~~~java
pool.setValidateConnectionOnBorrow(true);
pool.setSQLForValidateConnection("SELECT 1 FROM DUAL");
~~~

Validation giúp phát hiện stale connection trước khi giao cho request. Tuy nhiên, validate mỗi lần borrow có chi phí round trip. UCP có các cơ chế validation và stale connection handling; chọn cấu hình theo network/firewall/HA requirements.

### 12.6. Pool sizing

Giả sử:

- 4 application replicas.
- Mỗi replica có maxPoolSize = 30.
- Có 2 batch worker, mỗi worker tối đa 5 connection.

Tổng tiềm năng:

~~~text
4 × 30 + 2 × 5 = 130 connections
~~~

Database phải đủ process/session/resource cho tổng tải từ tất cả client, không chỉ một instance ứng dụng. Cân nhắc service, RAC instance distribution, background session, DBA sessions và các ứng dụng khác.

### 12.7. Không dùng implicit cache legacy cho pool mới

OracleDataSource có các property cache legacy. Với thiết kế mới, nên dùng UCP hoặc application server pool có lifecycle/metrics/validation rõ ràng thay vì tự xây pool hoặc dựa vào cache API cũ.

## 13. JNDI và application server

### 13.1. JNDI logical name

JNDI cho phép ứng dụng lookup DataSource bằng tên logic:

~~~java
import javax.naming.Context;
import javax.naming.InitialContext;
import javax.sql.DataSource;
import java.sql.Connection;

Context context = new InitialContext();
DataSource dataSource =
    (DataSource) context.lookup("java:comp/env/jdbc/AppDB");

try (Connection connection = dataSource.getConnection()) {
    // JDBC work.
}
~~~

Tên JNDI được khai báo trong application server/container. Ứng dụng không cần hardcode host, port, password và pool sizing trong code.

### 13.2. Container-managed DataSource

Trong môi trường enterprise:

1. DBA/platform admin tạo database service và account.
2. Application server cấu hình JDBC DataSource/UCP pool.
3. Credential được lưu trong credential store/encrypted configuration.
4. Ứng dụng inject hoặc lookup DataSource bằng JNDI.
5. Container quản lý pool lifecycle, monitoring và connection validation.

Đây thường là mô hình dễ vận hành hơn việc mỗi web request tự tạo OracleDataSource.

### 13.3. JNDI không tự mã hóa password

Việc bind DataSource vào JNDI không tự động làm password an toàn. Nếu application server serialize hoặc lưu DataSource configuration vào file, cần dùng credential store/encryption mechanism của server và phân quyền đọc file.

Không đưa password vào deployment descriptor hoặc file XML dạng plaintext nếu nền tảng có secret/credential store.

## 14. Credential rotation và lifecycle

### 14.1. Password rotation

Khi database password thay đổi:

1. Xác định ứng dụng và pool dùng account đó.
2. Chuẩn bị credential mới trong secret manager/wallet.
3. Thực hiện đổi password theo quy trình database.
4. Cập nhật secret reference/credential store.
5. Refresh hoặc drain pool để connection mới dùng credential mới.
6. Kiểm tra tạo connection mới và authentication.
7. Theo dõi ORA-01017 hoặc lỗi login liên quan.

Nếu đổi password trên database trước khi cập nhật secret, connection mới có thể thất bại trong khoảng thời gian chuyển đổi. Thiết kế rotation có cửa sổ chuyển tiếp nếu hệ thống hỗ trợ.

### 14.2. Connection cũ và connection mới

Password chỉ được dùng khi authentication tạo session mới. Connection đã xác thực có thể vẫn hoạt động sau khi password thay đổi, tùy trạng thái session và policy. Vì vậy, đổi secret không đồng nghĩa mọi physical connection trong pool đã được thay mới.

### 14.3. Tách account theo ứng dụng

Không dùng chung một schema owner hoặc SYS cho nhiều ứng dụng. Tạo runtime account riêng, cấp đúng quyền cần thiết và có thể khóa/rotate credential của một ứng dụng mà không làm ảnh hưởng mọi client khác.

### 14.4. Không dùng SYS trong application runtime

SYS/SYSDBA là quyền quản trị đặc biệt. Không cấu hình SYS password trong OracleDataSource của ứng dụng nghiệp vụ. Nếu cần administrative operation, dùng account quản trị riêng, quy trình đặc quyền và audit.

## 15. Network, service và HA

### 15.1. Kết nối bằng service

Service là điểm định tuyến logic cho workload. Service có thể được cấu hình với:

- Preferred/available instances.
- Load balancing.
- Failover.
- FAN/ONS notification.
- Draining cho planned maintenance.
- Application Continuity/TAC nếu được cấu hình.

Ứng dụng nên dùng service name ổn định thay vì SID của một instance cụ thể.

### 15.2. FAN và UCP

UCP có thể nhận FAN event để phản ứng khi service/instance thay đổi. Với RAC/HA, cấu hình ONS/FAN và Fast Connection Failover phù hợp với database/service topology.

Không chỉ bật fastConnectionFailoverEnabled mà bỏ qua ONS, service configuration và pool support.

### 15.3. Retry connection không phải retry transaction

Retry tạo connection mới có thể hợp lý khi listener hoặc network tạm thời lỗi. Retry một transaction sau khi mất response COMMIT là vấn đề khác: client có thể không biết transaction đã commit chưa.

Không viết vòng lặp retry mù cho mọi SQLException. Phân loại lỗi, transaction outcome, idempotency và Application Continuity/Transaction Guard nếu hệ thống hỗ trợ.

## 16. Bảo vệ dữ liệu và quyền của application account

### 16.1. Least privilege

Runtime account chỉ nên có:

- CREATE SESSION.
- Object privileges cần thiết.
- EXECUTE trên package/API nghiệp vụ.
- Quyền sequence hoặc type cần thiết nếu ứng dụng dùng.

Không cấp DBA, SELECT ANY TABLE hoặc quyền DDL rộng cho account runtime chỉ để tránh lỗi insufficient privileges.

### 16.2. Dùng package API thay vì cấp DML rộng

Nếu ứng dụng cần gọi một nhóm thao tác nghiệp vụ, có thể cấp EXECUTE trên package và hạn chế direct UPDATE/DELETE trên các bảng nhạy cảm. Cần thiết kế definer-rights/invoker-rights phù hợp và cấp direct grant cho stored code khi Oracle yêu cầu.

### 16.3. Database auditing

Gắn MODULE, ACTION và CLIENT_IDENTIFIER để truy vết workload:

~~~java
try (var statement = connection.createStatement()) {
    statement.execute(
        "BEGIN DBMS_APPLICATION_INFO.SET_MODULE(" +
        "'orders-api', 'create-order'); END;"
    );
}
~~~

CLIENT_IDENTIFIER có thể được thiết lập bằng DBMS_SESSION.SET_IDENTIFIER để liên kết database session với request/user logic. Không ghi password, access token hoặc dữ liệu nhạy cảm vào MODULE/ACTION/CLIENT_IDENTIFIER.

## 17. Xử lý SQLException và chẩn đoán kết nối

### 17.1. SQLException

~~~java
try (Connection connection = dataSource.getConnection()) {
    // Work.
} catch (SQLException exception) {
    int errorCode = exception.getErrorCode();
    String sqlState = exception.getSQLState();

    logger.error(
        "Oracle JDBC connection failed. errorCode={}, sqlState={}",
        errorCode,
        sqlState
    );
    throw exception;
}
~~~

Không log password, URL có embedded credential, wallet password hoặc Properties chứa secret. Có thể log service alias, correlation ID, error code và SQLState đã được kiểm soát.

### 17.2. Một số lỗi thường gặp

| Lỗi | Nguyên nhân có thể | Hướng kiểm tra |
| --- | --- | --- |
| ORA-01017 | Username/password không hợp lệ | Secret source, username casing, wallet alias và password rotation |
| ORA-28000 | Account bị khóa | DBA kiểm tra account status và chính sách login |
| ORA-28001 | Password hết hạn | Quy trình password rotation/expiry |
| ORA-12154 | Không resolve được TNS alias | TNS_ADMIN, tnsnames.ora, alias spelling |
| ORA-12514 | Listener không biết service yêu cầu | SERVICE_NAME, service registration, listener status |
| ORA-12541 | Không có listener tại endpoint | Host/port, listener và network |
| ORA-12545 | Host/address không resolve hoặc không tồn tại | DNS, connect descriptor và network route |
| ORA-29024 | Certificate validation failure | Trust chain, wallet, certificate expiry và DN match |
| ORA-17002 | I/O/network adapter error | Firewall, socket timeout, listener, database availability |
| ORA-01031 | Thiếu privilege | Direct grants/role và quyền account |
| SQLRecoverableException | Connection có thể bị mất hoặc không dùng được | Loại bỏ connection lỗi, xử lý transaction outcome, lấy connection mới |

Mã lỗi không đủ để kết luận nguyên nhân. Đọc SQLException chain, Oracle error code, alert log, listener log và client trace khi cần.

### 17.3. Test service sau khi connect

~~~sql
SELECT USER,
       SYS_CONTEXT('USERENV', 'SERVICE_NAME') AS service_name,
       SYS_CONTEXT('USERENV', 'INSTANCE_NAME') AS instance_name,
       SYS_CONTEXT('USERENV', 'CON_NAME') AS con_name
FROM dual;
~~~

Query này giúp phát hiện ứng dụng kết nối nhầm service, PDB hoặc instance.

## 18. Ví dụ cấu hình theo các tình huống

### 18.1. Ứng dụng nhỏ, không dùng pool

~~~java
OracleDataSource dataSource = new OracleDataSource();
dataSource.setURL("jdbc:oracle:thin:@//dbhost:1521/appsvc");
dataSource.setUser(runtimeUser);
dataSource.setPassword(runtimePassword);
dataSource.setLoginTimeout(15);

try (Connection connection = dataSource.getConnection()) {
    // Run one short task.
}
~~~

Phù hợp cho command-line job hoặc tác vụ ít connection, nếu lifecycle được kiểm soát.

### 18.2. Ứng dụng production dùng UCP

~~~java
PoolDataSource pool = PoolDataSourceFactory.getPoolDataSource();
pool.setConnectionFactoryClassName(
    "oracle.jdbc.pool.OracleDataSource"
);
pool.setURL("jdbc:oracle:thin:@//dbhost:1521/appsvc");
pool.setUser(runtimeUser);
pool.setPassword(runtimePassword);
pool.setMinPoolSize(4);
pool.setInitialPoolSize(4);
pool.setMaxPoolSize(24);
pool.setConnectionWaitTimeout(10);
pool.setValidateConnectionOnBorrow(true);
pool.setSQLForValidateConnection("SELECT 1 FROM DUAL");
~~~

Kích thước pool cần được tính cùng số replica, batch, background worker và giới hạn session/process database.

### 18.3. TNS alias và wallet

~~~java
Properties properties = new Properties();
properties.setProperty(
    "oracle.net.tns_admin",
    "/opt/app/oracle/network/admin"
);
properties.setProperty(
    "oracle.net.wallet_location",
    "(SOURCE=(METHOD=FILE)(METHOD_DATA=(DIRECTORY=/opt/app/oracle/wallet)))"
);

OracleDataSource dataSource = new OracleDataSource();
dataSource.setURL("jdbc:oracle:thin:@APPDB");
dataSource.setConnectionProperties(properties);

try (Connection connection = dataSource.getConnection()) {
    // Credentials are obtained from the external password store.
}
~~~

Credential entry trong wallet phải dùng đúng connect identifier APPDB. Không khai báo user/password trong URL hoặc Properties nếu muốn driver lấy chúng từ wallet.

### 18.4. TCPS và DN matching

~~~java
OracleDataSource dataSource = new OracleDataSource();
dataSource.setURL(
    "jdbc:oracle:thin:@(DESCRIPTION=" +
    "(ADDRESS=(PROTOCOL=TCPS)(HOST=db.example.com)(PORT=2484))" +
    "(CONNECT_DATA=(SERVICE_NAME=appsvc.example.com))" +
    "(SECURITY=(TLS_SERVER_DN_MATCH=TRUE)))"
);
dataSource.setUser(runtimeUser);
dataSource.setPassword(runtimePassword);
~~~

Wallet/truststore và server certificate phải được cấu hình đồng bộ. Nếu dùng mTLS, cần client certificate/private key theo server policy.

## 19. Các anti-pattern cần tránh

| Anti-pattern | Rủi ro | Cách làm tốt hơn |
| --- | --- | --- |
| Password hardcode trong source | Lộ qua Git, source archive hoặc code review | Secret manager hoặc Oracle wallet |
| Password trong JDBC URL | Lộ qua log, process args hoặc diagnostics | URL chỉ chứa endpoint/service |
| Tạo DataSource cho từng request | Tăng chi phí kết nối và session churn | DataSource singleton/container-managed |
| Dùng OracleDataSource như pool | Không có pool lifecycle tổng quát | Dùng UCP/application server pool |
| Gắn cứng SID trong RAC | Khó relocate/load balance service | Dùng SERVICE_NAME |
| Đặt URL và host/port property mâu thuẫn | Một số property bị bỏ qua | Chọn một cách cấu hình rõ ràng |
| Dùng SYS cho application runtime | Quyền quá rộng | Runtime account riêng, least privilege |
| Log toàn bộ Properties | Có thể lộ password/token/wallet path | Log field đã allowlist |
| Chia sẻ một Connection giữa nhiều thread | Race condition và session state lẫn nhau | Mỗi đơn vị công việc mượn connection riêng |
| Không close Connection | Leak pool slot hoặc server session | try-with-resources |
| Không phối hợp timeout | Request treo lâu hoặc timeout quá sớm | Timeout budget thống nhất |
| Bật validation mọi lần mà không đo | Thêm round trip khi borrow | Chọn validation theo network/pool behavior |
| Đổi secret nhưng không refresh pool | Connection mới vẫn dùng credential cũ | Drain/recycle pool có kiểm soát |
| Retry mù sau lỗi COMMIT | Transaction có thể chạy hai lần | Transaction Guard/idempotency |
| Tắt TLS/DN validation để hết lỗi | Có thể kết nối nhầm server | Sửa certificate, trust chain và hostname |

## 20. Checklist triển khai OracleDataSource

1. **Driver đúng chưa?** Chọn Thin/OCI/KPRB theo nơi chạy và yêu cầu.
2. **URL dùng service name chưa?** Ưu tiên service cho RAC/PDB/workload routing.
3. **TNS_ADMIN đúng chưa?** Xác nhận file alias có thể đọc từ runtime host/container.
4. **Không có credential trong URL chưa?** Tách endpoint khỏi secret.
5. **Precedence rõ chưa?** Không để URL và discrete properties mâu thuẫn.
6. **Connection properties có cần thiết không?** Chỉ bật các property có lý do.
7. **Timeout phân biệt rõ chưa?** Login, connect, outbound, read, statement và pool wait.
8. **Secret source phù hợp chưa?** Wallet, secret manager hoặc container credential store.
9. **Wallet permission đã hạn chế chưa?** Chỉ runtime identity được đọc.
10. **TLS/DN matching đã bật chưa?** Kiểm tra server identity và certificate chain.
11. **Có dùng pool không?** Production service thường cần UCP hoặc container pool.
12. **Pool size đã tính tổng chưa?** Cộng tất cả replicas và worker.
13. **Validation/stale connection policy đã phù hợp chưa?** Xem firewall và HA.
14. **Credential rotation có quy trình không?** Cập nhật secret và refresh pool.
15. **Runtime account có least privilege không?** Không dùng SYS/DBA.
16. **Connection được close đúng cách không?** Dùng try-with-resources.
17. **Log có thể lộ secret không?** Không dump URL/Properties/credential.
18. **Service/PDB đúng chưa?** Xác nhận bằng SYS_CONTEXT.
19. **Có kiểm thử lỗi mạng/TLS/authentication không?** Không chỉ test kết nối thành công.
20. **Đã theo dõi pool và database sessions chưa?** Borrow wait, active/available, failures, session count.

## 21. Câu hỏi tự kiểm tra

**Câu 1.** OracleDataSource là gì?

**Câu 2.** OracleDataSource nằm trong package nào?

**Câu 3.** DataSource khác Connection ở điểm nào?

**Câu 4.** OracleDataSource có phải connection pool không?

**Câu 5.** UCP dùng OracleDataSource như thế nào?

**Câu 6.** SERVICE_NAME khác SID như thế nào?

**Câu 7.** Khi URL đã được đặt, những property host/port rời rạc nào bị bỏ qua?

**Câu 8.** getConnection(username, password) có precedence ra sao?

**Câu 9.** Vì sao không nên nhúng password trong JDBC URL?

**Câu 10.** setConnectionProperties dùng để làm gì?

**Câu 11.** loginTimeout khác oracle.net.CONNECT_TIMEOUT thế nào?

**Câu 12.** oracle.jdbc.ReadTimeout tính bằng đơn vị nào?

**Câu 13.** Vì sao ReadTimeout không tương đương Statement.setQueryTimeout?

**Câu 14.** TNS_ADMIN dùng để làm gì?

**Câu 15.** Secure External Password Store giải quyết vấn đề gì?

**Câu 16.** Vì sao wallet auto-login vẫn cần bảo vệ file?

**Câu 17.** Oracle wallet có thể dùng cho cả password credential và TLS như thế nào?

**Câu 18.** Vì sao cần TLS_SERVER_DN_MATCH?

**Câu 19.** UCP connectionWaitTimeout khác connect timeout thế nào?

**Câu 20.** Vì sao đổi password trong secret store chưa chắc thay thế ngay mọi connection trong pool?

<details>
<summary>Gợi ý đáp án</summary>

1. Oracle implementation của JDBC DataSource để cấu hình và tạo database connection.
2. oracle.jdbc.pool.
3. DataSource là factory; Connection là session JDBC dùng thực thi SQL.
4. Không. Nó tạo physical connection; UCP hoặc application server pool quản lý reuse.
5. UCP dùng OracleDataSource làm connection factory để tạo physical connection.
6. SID định danh instance; SERVICE_NAME định danh database service.
7. tnsEntry, driverType, portNumber, networkProtocol, serverName và databaseName.
8. Credential truyền vào getConnection được ưu tiên hơn property trên DataSource.
9. URL có thể xuất hiện trong log, process list, diagnostics hoặc config dump.
10. Truyền Oracle JDBC connection properties.
11. loginTimeout là DataSource wait time; CONNECT_TIMEOUT là thời gian kết nối socket tới listener.
12. Milliseconds.
13. ReadTimeout giới hạn socket read; query timeout yêu cầu hủy statement và có thể chịu ảnh hưởng network/cancel.
14. Chỉ thư mục Oracle Net chứa tnsnames.ora/sqlnet.ora và file liên quan.
15. Lưu username/password trong client wallet thay vì nhúng trong source/script.
16. Ai đọc được wallet có thể sử dụng credential; cần ACL và filesystem protection.
17. Password store lấy username/password; PKI wallet chứa trust/certificate/private key cho TLS/mTLS.
18. Xác minh server certificate thuộc đúng endpoint mong muốn.
19. connectionWaitTimeout chờ connection rảnh trong pool; connect timeout kết nối tới listener/service.
20. Physical connection đã xác thực có thể vẫn nằm trong pool; cần drain/refresh để tạo connection mới.

</details>

## 22. Tài liệu Oracle chính thức

1. [Oracle Database 19c JDBC Developer's Guide — Data Sources and URLs](https://docs.oracle.com/en/database/oracle/oracle-database/19/jjdbc/data-sources-and-URLs.html): OracleDataSource, standard/extended properties, JNDI, URL và precedence.
2. [Oracle Database 19c JDBC Java API Reference — OracleConnection](https://docs.oracle.com/en/database/oracle/oracle-database/19/jajdb/oracle/jdbc/OracleConnection.html): các connection property, wallet, timeout và Oracle JDBC extensions.
3. [Oracle Database 19c JDBC Developer's Guide — JDBC Client-Side Security Features](https://docs.oracle.com/en/database/oracle/oracle-database/19/jjdbc/client-side-security.html): wallet, authentication, network encryption, TLS và Secure External Password Store.
4. [Oracle Database 19c Security Guide — Managing the Secure External Password Store](https://docs.oracle.com/en/database/oracle/oracle-database/19/dbseg/managing-secure-external-password-store-password-credentials.html): tạo wallet, quản lý credential bằng mkstore và cấu hình client.
5. [Oracle Database 19c Universal Connection Pool Developer's Guide — Borrowing Connections](https://docs.oracle.com/en/database/oracle/oracle-database/19/jjucp/borrowing-ucp-connections.html): PoolDataSource, connection factory và connection properties.
6. [Oracle Database 19c Universal Connection Pool Developer's Guide — Setting UCP Properties](https://docs.oracle.com/en/database/oracle/oracle-database/19/jjucp/setting-ucp-properties.html): min/max pool size và cấu hình pool.
7. [Oracle Database 19c JDBC Troubleshooting](https://docs.oracle.com/en/database/oracle/oracle-database/19/jjdbc/JDBC-troubleshooting.html): read timeout, firewall, network failure và resource cleanup.
8. [Oracle Database 19c Security Guide — About Configuring TLS](https://docs.oracle.com/en/database/oracle/oracle-database/19/dbseg/about-configuring-tls-oracle-database.html): TCPS, wallet, TLS client authentication và DN matching.
9. [Oracle Database 19c Security Guide — TLS Features](https://docs.oracle.com/en/database/oracle/oracle-database/19/dbseg/tls-and-oracle-database.html): one-way TLS, mTLS và certificate validation.

**Nguyên tắc cần nhớ:** OracleDataSource là factory tạo JDBC Connection; UCP hoặc application server pool mới quản lý việc mượn/trả và tái sử dụng connection. Dùng SERVICE_NAME, kiểm soát rõ URL/property precedence, phân biệt các loại timeout và xác minh session sau khi kết nối. Password phải đến từ wallet, secret manager hoặc credential store được bảo vệ; không nhúng vào source, URL hay log. Trong production, kết hợp least privilege, TLS/DN matching, pool sizing, credential rotation và monitoring để quản lý vòng đời kết nối an toàn.
