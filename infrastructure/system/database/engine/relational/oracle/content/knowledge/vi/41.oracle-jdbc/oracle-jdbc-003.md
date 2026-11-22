# URL kết nối bằng service name, Easy Connect và connect descriptor trong Oracle JDBC

Trong Java, Oracle JDBC dùng một JDBC URL để xác định database endpoint mà ứng dụng cần kết nối. Với Oracle Database, endpoint thường được biểu diễn bằng hostname, listener port và **service name**. Có thể khai báo thông tin đó trực tiếp bằng Easy Connect hoặc mô tả chi tiết hơn bằng connect descriptor.

Ba dạng cần phân biệt:

- **Easy Connect:** URL ngắn, phù hợp khi chỉ cần host, port và service name.
- **Connect descriptor:** URL chứa cấu trúc Oracle Net DESCRIPTION, cho phép khai báo nhiều address, timeout, failover, load balancing và server type.
- **TNS alias:** URL tham chiếu một tên trong tnsnames.ora; driver cần biết thư mục chứa file cấu hình.

Với ứng dụng Java mới, Oracle JDBC Thin thường là lựa chọn mặc định vì driver thuần Java và không cần Oracle Client trên máy chạy ứng dụng. URL phổ biến nhất là:

~~~text
jdbc:oracle:thin:@//dbhost.example.com:1521/appsvc.example.com
~~~

Phần quan trọng là appsvc.example.com phải là service name đã được listener/database đăng ký. Service name khác với SID và khác với tên JDBC driver.

Bài học lấy Oracle Database 19c và Oracle JDBC Thin làm trọng tâm. Nội dung giải thích cấu trúc URL, cách chọn service name, Easy Connect, Easy Connect Plus, connect descriptor, RAC/SCAN, TNS alias, Java connection code, connection pool, bảo mật thông tin xác thực, timeout và xử lý lỗi kết nối.

## 1. Các thành phần của Oracle JDBC URL

### 1.1. Cấu trúc tổng quát

Với Oracle JDBC Thin, dạng URL thông dụng:

~~~text
jdbc:oracle:thin:@//host:port/service_name
~~~

Các phần có ý nghĩa:

| Thành phần | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| jdbc | jdbc | JDBC URL scheme |
| oracle | oracle | Nhà cung cấp driver |
| thin | thin | Oracle JDBC Thin driver |
| @ | @ | Bắt đầu phần Oracle Net connect identifier |
| // | // | Dạng Easy Connect |
| host | db01.example.com | Hostname hoặc IP của listener |
| port | 1521 | Listener TCP port |
| service_name | appsvc.example.com | Service database mà listener sẽ định tuyến |

Ví dụ:

~~~text
jdbc:oracle:thin:@//db01.example.com:1521/salespdb.example.com
~~~

URL trên yêu cầu JDBC Thin kết nối tới listener trên db01.example.com cổng 1521 và yêu cầu service salespdb.example.com.

### 1.2. JDBC URL không phải database username/password

URL xác định endpoint. Tên user và password nên được truyền riêng:

~~~java
String url =
    "jdbc:oracle:thin:@//db01.example.com:1521/appsvc.example.com";

try (Connection connection =
         DriverManager.getConnection(url, username, password)) {
    // Thực hiện công việc với connection.
}
~~~

Không đặt password trực tiếp trong URL hoặc source code. Credentials nên lấy từ secret manager, environment được bảo vệ hoặc cơ chế cấp phát secret của nền tảng.

### 1.3. Driver Thin và OCI

Hai loại Oracle JDBC driver thường gặp:

| Driver | URL prefix | Yêu cầu phía máy ứng dụng |
| --- | --- | --- |
| Thin | jdbc:oracle:thin:@ | Driver Java; không cần Oracle Client native |
| OCI | jdbc:oracle:oci:@ | Oracle Client/OCI native libraries phù hợp |

Thin phù hợp với phần lớn ứng dụng server Java vì dễ đóng gói và triển khai. OCI có thể được dùng khi hệ thống phụ thuộc tính năng hoặc cấu hình native cụ thể, nhưng phải quản lý client library, architecture, PATH/LD_LIBRARY_PATH và version compatibility.

Các ví dụ trong bài dùng Thin. Không đổi thin thành oci chỉ để thử một URL; OCI cần runtime native tương ứng.

## 2. Service name, SID và database name

### 2.1. Service name là gì?

Service name là tên dịch vụ mà Oracle Net listener dùng để định tuyến kết nối tới database service. Một database có thể cung cấp nhiều service để phân tách workload, ứng dụng, PDB hoặc mục tiêu quản trị.

Service name có thể đại diện cho:
- Một PDB service trong multitenant database.
- Một service ứng dụng trong single-instance database.
- Một service được quản lý bởi Oracle Clusterware trong RAC.
- Một service có thuộc tính workload management, failover hoặc edition-based routing.

Ứng dụng thường nên kết nối qua service name để database quản lý nơi nhận session.

### 2.2. SID là gì?

SID (System Identifier) nhận diện một Oracle instance. Trong mô hình instance đơn giản, SID thường gắn với instance cụ thể.

Trong RAC, mỗi instance có SID riêng, trong khi một database service có thể được cung cấp bởi nhiều instance. Kết nối bằng service giúp ứng dụng không phải gắn cứng vào một instance.

### 2.3. So sánh service name và SID

| Tiêu chí | Service name | SID |
| --- | --- | --- |
| Đại diện | Dịch vụ database | Oracle instance |
| Phù hợp PDB | Có, qua PDB service | Không phải lựa chọn phù hợp |
| RAC | Có thể được cung cấp bởi nhiều instance | Thường gắn với một instance |
| Quản lý workload | Có service attributes, preferred/available instances | Ít linh hoạt hơn |
| Khuyến nghị ứng dụng mới | Ưu tiên | Chỉ dùng khi hệ thống yêu cầu cụ thể |

Không lấy giá trị ORACLE_SID ở máy chủ rồi tự động điền vào phần service name. Hai giá trị có thể khác nhau.

### 2.4. Ví dụ sai thường gặp

Giả sử instance SID là ORCL, nhưng service ứng dụng là salespdb.example.com. URL:

~~~text
jdbc:oracle:thin:@//dbhost:1521/ORCL
~~~

sẽ yêu cầu listener tìm service tên ORCL. Nếu ORCL chỉ là SID và không có service tương ứng, listener có thể trả ORA-12514.

URL theo service thực tế:

~~~text
jdbc:oracle:thin:@//dbhost:1521/salespdb.example.com
~~~

### 2.5. Tìm service name trong database

DBA có thể xem service đã được đăng ký:

~~~sql
SELECT name,
       network_name,
       pdb
FROM   v$services
ORDER  BY name;
~~~

Tên cột hiển thị có thể khác theo release/view và quyền. Trong môi trường multitenant, PDB cho biết service gắn với PDB nào nếu thông tin được cung cấp.

Có thể xem service qua:

~~~sql
SELECT name,
       network_name
FROM   dba_services
ORDER  BY name;
~~~

DBA_SERVICES có phạm vi và quyền truy cập riêng. Nếu tài khoản ứng dụng không đọc được view, hãy yêu cầu DBA cung cấp service name chính thức.

### 2.6. Xác minh service tại listener

Trên máy database/listener, DBA có thể chạy:

~~~bash
lsnrctl status
lsnrctl services
~~~

LSNRCTL SERVICES hiển thị các service listener đang biết và handler tương ứng. Nếu service chưa đăng ký, kiểm tra listener, LOCAL_LISTENER/REMOTE_LISTENER, service management và trạng thái PDB/database.

Không dùng SID hoặc DB_NAME thay cho service name chỉ vì chúng xuất hiện trong output quản trị.

## 3. Easy Connect cơ bản

### 3.1. Dạng URL

Easy Connect cho Oracle JDBC Thin thường dùng:

~~~text
jdbc:oracle:thin:@//host:port/service_name
~~~

Ví dụ:

~~~text
jdbc:oracle:thin:@//localhost:1521/orclpdb1
~~~

Nếu listener dùng port mặc định, một số cách viết có thể bỏ port theo cú pháp Oracle Net tương ứng; trong cấu hình ứng dụng, nên ghi rõ port để tránh phụ thuộc mặc định.

### 3.2. Khi nào nên dùng Easy Connect?

Easy Connect phù hợp khi:
- Ứng dụng chỉ cần một host/listener endpoint.
- Không cần khai báo nhiều address.
- Không cần cấu hình connect descriptor phức tạp.
- Muốn URL dễ đọc trong application.properties, YAML hoặc environment.
- Không muốn phân phối tnsnames.ora tới ứng dụng.

Ví dụ cấu hình Spring Boot:

~~~properties
spring.datasource.url=jdbc:oracle:thin:@//db01.example.com:1521/appsvc.example.com
spring.datasource.username=app_user
spring.datasource.password=ENV_DB_PASSWORD
spring.datasource.driver-class-name=oracle.jdbc.OracleDriver
~~~

Trong cấu hình thực tế, cú pháp biến môi trường phụ thuộc framework/deployment platform. Đảm bảo password được inject từ secret store và không xuất hiện trong log.

### 3.3. Easy Connect không cần tnsnames.ora

URL chứa host, port và service name trực tiếp, do đó không cần alias trong tnsnames.ora.

Đây là ưu điểm cho container hoặc ứng dụng triển khai tự động: chỉ cần cung cấp endpoint qua configuration. Tuy nhiên, nếu có nhiều host, policy failover, wallet hoặc nhiều tham số Oracle Net, connect descriptor hoặc Easy Connect Plus có thể phù hợp hơn.

### 3.4. Port và hostname

- Host có thể là DNS name hoặc IP address.
- Port phải là listener port đang lắng nghe.
- Port 1521 thường gặp nhưng không phải mặc định bắt buộc.
- Hostname phải phân giải được từ máy ứng dụng, không chỉ từ database host.
- Nếu dùng container/Kubernetes, kiểm tra DNS/network policy từ chính pod/container chạy Java.

Dùng hostname/service endpoint chính thức thay vì IP tạm thời để tránh thay đổi khi chuyển node hoặc storage/network.

## 4. Easy Connect Plus

### 4.1. Mục đích

Easy Connect Plus mở rộng Easy Connect với khả năng khai báo nhiều host/port và các tham số kết nối trong URL. Điều này hữu ích khi ứng dụng cần:
- Nhiều listener address.
- Connect-time failover.
- Load balancing ở tầng địa chỉ.
- Timeout và retry.
- Một số tùy chọn TLS/wallet theo driver và Oracle Net version.

Easy Connect Plus được hỗ trợ trong các phiên bản Oracle Net/JDBC phù hợp; kiểm tra ma trận tương thích của JDBC driver đang dùng thay vì giả định mọi driver cũ đều hiểu cú pháp mở rộng.

### 4.2. Ví dụ nhiều host

~~~text
jdbc:oracle:thin:@//dbhost1.example.com:1521,dbhost2.example.com:1521/appsvc.example.com
~~~

URL chứa hai listener address và cùng một service name. Khả năng dùng nhiều address, failover và load balancing phụ thuộc cú pháp được hỗ trợ và cấu hình service/listener.

### 4.3. Thêm tham số timeout/retry

Ví dụ minh họa Easy Connect Plus:

~~~text
jdbc:oracle:thin:@//dbhost1.example.com:1521,dbhost2.example.com:1521/appsvc.example.com?connect_timeout=10&retry_count=3&retry_delay=2
~~~

Các tham số query string cần đúng tên và cách diễn giải mà Oracle JDBC/Oracle Net version hỗ trợ. Đơn vị, thứ tự retry và phạm vi áp dụng cần được xác nhận trong tài liệu driver. Không copy nguyên cấu hình này vào production mà chưa đo thời gian connect và failover thực tế.

### 4.4. Easy Connect Plus hay connect descriptor?

Easy Connect Plus phù hợp khi URL vẫn có cấu trúc đơn giản và các tham số được hỗ trợ trong dạng URL ngắn. Connect descriptor phù hợp hơn khi cần kiểm soát chi tiết ADDRESS_LIST, CONNECT_DATA, SOURCE_ROUTE, server type hoặc các cấu trúc Oracle Net phức tạp.

Nếu URL có nhiều dấu ngoặc và policy failover phức tạp, descriptor thường dễ đọc và quản lý hơn khi đặt trong cấu hình riêng.

## 5. Connect descriptor

### 5.1. Cấu trúc DESCRIPTION

Connect descriptor mô tả đầy đủ cách Oracle Net thiết lập kết nối:

~~~text
jdbc:oracle:thin:@(DESCRIPTION=
  (ADDRESS=
    (PROTOCOL=TCP)
    (HOST=db01.example.com)
    (PORT=1521)
  )
  (CONNECT_DATA=
    (SERVICE_NAME=appsvc.example.com)
    (SERVER=DEDICATED)
  )
)
~~~

Các phần chính:

- DESCRIPTION: một mô tả kết nối.
- ADDRESS: một endpoint mạng.
- PROTOCOL: TCP hoặc TCPS tùy listener.
- HOST: hostname/IP của listener.
- PORT: listener port.
- CONNECT_DATA: thông tin dịch vụ database.
- SERVICE_NAME: service cần kết nối.
- SERVER: loại server process mong muốn, ví dụ DEDICATED.

### 5.2. URL Java dạng một dòng

Connect descriptor thường được lưu dưới dạng một chuỗi. Ví dụ:

~~~java
String url =
    "jdbc:oracle:thin:@(DESCRIPTION=" +
    "(ADDRESS=(PROTOCOL=TCP)(HOST=db01.example.com)(PORT=1521))" +
    "(CONNECT_DATA=(SERVICE_NAME=appsvc.example.com)(SERVER=DEDICATED))" +
    ")";

try (Connection connection =
         DriverManager.getConnection(url, username, password)) {
    // Connection đã được mở.
}
~~~

Việc ghép chuỗi ở đây chỉ để thể hiện một URL tĩnh. Nếu host/service đến từ configuration, validate nguồn cấu hình và không ghép dữ liệu không tin cậy vào descriptor.

### 5.3. ADDRESS và ADDRESS_LIST

Một DESCRIPTION có thể chứa một ADDRESS hoặc ADDRESS_LIST gồm nhiều endpoint:

~~~text
jdbc:oracle:thin:@(DESCRIPTION=
  (ADDRESS_LIST=
    (LOAD_BALANCE=ON)
    (FAILOVER=ON)
    (ADDRESS=(PROTOCOL=TCP)(HOST=dbhost1.example.com)(PORT=1521))
    (ADDRESS=(PROTOCOL=TCP)(HOST=dbhost2.example.com)(PORT=1521))
  )
  (CONNECT_DATA=
    (SERVICE_NAME=appsvc.example.com)
  )
)
~~~

LOAD_BALANCE điều khiển cách Oracle Net chọn giữa các address trong danh sách theo cấu hình hỗ trợ. FAILOVER cho phép thử address khác khi một endpoint không thể thiết lập kết nối.

Các tùy chọn này chủ yếu xử lý lựa chọn/thiết lập kết nối tới endpoint. Chúng không tự replay transaction đã chạy trên một connection bị mất.

### 5.4. DESCRIPTION_LIST

Có thể dùng DESCRIPTION_LIST để mô tả nhiều DESCRIPTION, ví dụ khi cần nhóm các site/endpoint khác nhau. Đây là cấu trúc Oracle Net nâng cao. Chỉ dùng khi hiểu rõ thứ tự thử, failover, load balancing và cách driver xử lý từng description.

Đối với đa số ứng dụng, một DESCRIPTION với ADDRESS_LIST là đủ. Tránh tạo descriptor phức tạp hơn mức cần thiết vì khó chẩn đoán khi DNS, listener hoặc service thay đổi.

### 5.5. CONNECT_DATA và SERVICE_NAME

Ví dụ:

~~~text
(CONNECT_DATA=
  (SERVICE_NAME=salespdb.example.com)
  (SERVER=DEDICATED)
)
~~~

SERVICE_NAME xác định dịch vụ database. SERVER=DEDICATED yêu cầu dedicated server connection khi cấu hình/listener hỗ trợ. Nếu bỏ SERVER, Oracle Net sử dụng mặc định và chính sách của listener/database.

Không đưa cả SERVICE_NAME và SID vào CONNECT_DATA một cách tùy tiện. Chọn đúng định danh theo mô hình kết nối.

### 5.6. SID descriptor kiểu cũ

Một số ứng dụng cũ dùng SID:

~~~text
jdbc:oracle:thin:@(DESCRIPTION=
  (ADDRESS=(PROTOCOL=TCP)(HOST=legacy-db.example.com)(PORT=1521))
  (CONNECT_DATA=(SID=ORCL))
)
~~~

Hoặc URL dạng legacy:

~~~text
jdbc:oracle:thin:@legacy-db.example.com:1521:ORCL
~~~

Cú pháp SID vẫn có thể cần cho hệ thống legacy, nhưng không nên thay thế service name trong ứng dụng mới, đặc biệt khi kết nối PDB hoặc RAC.

## 6. Connect descriptor với timeout và retry

### 6.1. CONNECT_TIMEOUT

CONNECT_TIMEOUT giới hạn thời gian Oracle Net chờ hoàn thành quá trình thiết lập kết nối theo phạm vi của descriptor/driver. Ví dụ:

~~~text
jdbc:oracle:thin:@(DESCRIPTION=
  (CONNECT_TIMEOUT=10)
  (TRANSPORT_CONNECT_TIMEOUT=3)
  (ADDRESS=(PROTOCOL=TCP)(HOST=db01.example.com)(PORT=1521))
  (CONNECT_DATA=(SERVICE_NAME=appsvc.example.com))
)
~~~

CONNECT_TIMEOUT và TRANSPORT_CONNECT_TIMEOUT có phạm vi khác nhau. Transport timeout giới hạn việc thiết lập transport tới address; connect timeout bao quát giai đoạn kết nối Oracle Net theo quy tắc của descriptor.

Không đặt timeout quá thấp khiến kết nối hợp lệ bị từ chối khi hệ thống có tải cao hoặc network latency tăng.

### 6.2. RETRY_COUNT và RETRY_DELAY

Ví dụ:

~~~text
jdbc:oracle:thin:@(DESCRIPTION=
  (CONNECT_TIMEOUT=10)
  (RETRY_COUNT=3)
  (RETRY_DELAY=2)
  (ADDRESS_LIST=
    (FAILOVER=ON)
    (ADDRESS=(PROTOCOL=TCP)(HOST=dbhost1.example.com)(PORT=1521))
    (ADDRESS=(PROTOCOL=TCP)(HOST=dbhost2.example.com)(PORT=1521))
  )
  (CONNECT_DATA=(SERVICE_NAME=appsvc.example.com))
)
~~~

RETRY_COUNT và RETRY_DELAY điều khiển việc thử lại theo quy tắc Oracle Net. Thời gian tổng có thể dài hơn một timeout đơn lẻ do có nhiều address và lần retry. Tính thời gian worst-case trước khi cấu hình connection pool.

### 6.3. Connect timeout khác query timeout

| Loại timeout | Điều khiển | Cách cấu hình thường gặp |
| --- | --- | --- |
| Connect timeout | Thời gian mở connection tới listener/database | Oracle Net descriptor/Easy Connect Plus hoặc driver properties |
| Network/read timeout | Thời gian chờ dữ liệu mạng trong một lần đọc | Oracle JDBC network properties hoặc Connection.setNetworkTimeout tùy driver/JDBC |
| Statement query timeout | Thời gian cho phép một SQL statement chạy | Statement.setQueryTimeout |
| Pool acquisition timeout | Thời gian chờ lấy connection từ pool | Cấu hình connection pool |
| Transaction timeout | Giới hạn thời gian transaction ở tầng framework/container | Transaction manager |

Không dùng connect timeout để kiểm soát thời gian chạy SELECT. Một query có thể kết nối thành công trong 100 ms nhưng chạy 20 phút.

### 6.4. Retry không đồng nghĩa retry transaction

Nếu connection rớt sau khi server đã nhận một DML/COMMIT, ứng dụng có thể không biết transaction đã commit hay chưa. Tự động gửi lại transaction có thể tạo thao tác trùng.

Ứng dụng cần:
- Thiết kế operation idempotent khi có thể.
- Dùng business key/request ID để chống trùng.
- Phân biệt lỗi trước khi gửi request và lỗi sau khi gửi.
- Xử lý trạng thái commit không xác định theo quy trình.
- Dùng Application Continuity/Transaction Guard khi kiến trúc và license/configuration hỗ trợ.

Connect-time failover chỉ giúp thiết lập connection tới endpoint khác; nó không tự bảo đảm tính exactly-once cho transaction.

## 7. Kết nối Oracle RAC bằng service name

### 7.1. Dùng SCAN listener

Với RAC, ứng dụng thường kết nối qua SCAN name và service name thay vì gắn cứng vào node VIP riêng:

~~~text
jdbc:oracle:thin:@//rac-scan.example.com:1521/orders_rw.example.com
~~~

SCAN giúp client dùng một endpoint ổn định khi node trong cluster thay đổi. Listener/Clusterware định tuyến session tới instance cung cấp service theo cấu hình service.

### 7.2. RAC connect descriptor

~~~text
jdbc:oracle:thin:@(DESCRIPTION=
  (ADDRESS=(PROTOCOL=TCP)(HOST=rac-scan.example.com)(PORT=1521))
  (CONNECT_DATA=
    (SERVICE_NAME=orders_rw.example.com)
    (SERVER=DEDICATED)
  )
)
~~~

Nếu SCAN trả nhiều IP, Oracle Net có thể sử dụng các address theo cơ chế DNS/SCAN. Không hardcode một IP SCAN duy nhất nếu môi trường yêu cầu phân giải nhiều địa chỉ.

### 7.3. Load balancing

Có hai khái niệm thường bị nhầm:
- **Client-side load balancing:** Oracle Net chọn một address trong danh sách.
- **Runtime connection load balancing:** service/ONS/connection pool có thể phân phối session dựa trên workload và service metrics khi cấu hình hỗ trợ.

LOAD_BALANCE=ON trong ADDRESS_LIST không tự thay thế cấu hình service/RAC runtime load balancing. DBA cần cấu hình service và listener theo workload.

### 7.4. Connect-time failover

Khi address đầu tiên không thể kết nối, Oracle Net có thể thử address tiếp theo nếu descriptor bật failover và các điều kiện phù hợp.

Failover khi connect khác với:
- Phục hồi một session đang chạy.
- Replay câu SQL đã gửi.
- Khôi phục transaction đang mở.
- Đảm bảo ứng dụng không nhận kết quả không xác định sau mất mạng.

Ứng dụng cần xử lý lỗi kết nối và transaction state ở tầng JDBC/framework.

### 7.5. Dùng service cho PDB

Trong CDB, ứng dụng nên kết nối tới service được tạo/quản lý cho PDB đích. Ví dụ:

~~~text
jdbc:oracle:thin:@//pdb-host.example.com:1521/hrpdb.example.com
~~~

Sau khi kết nối, xác minh:

~~~sql
SELECT sys_context('USERENV', 'CON_NAME') AS con_name,
       sys_context('USERENV', 'SERVICE_NAME') AS service_name
FROM   dual;
~~~

Nếu service trỏ nhầm PDB, câu SQL có thể chạy thành công nhưng truy cập sai schema/data. Vì vậy validation phải kiểm tra container và service name, không chỉ kiểm tra Connection.isValid.

## 8. TNS alias và tnsnames.ora

### 8.1. Khi nào dùng alias?

TNS alias giúp tách network configuration khỏi application URL. Ứng dụng chỉ lưu tên kết nối; DBA có thể thay host, port hoặc descriptor trong tnsnames.ora mà không phải sửa mọi URL trong ứng dụng.

Ví dụ URL:

~~~text
jdbc:oracle:thin:@APPDB
~~~

Trong tnsnames.ora:

~~~text
APPDB =
  (DESCRIPTION =
    (ADDRESS =
      (PROTOCOL = TCP)
      (HOST = db01.example.com)
      (PORT = 1521)
    )
    (CONNECT_DATA =
      (SERVICE_NAME = appsvc.example.com)
    )
  )
~~~

### 8.2. Chỉ định thư mục tnsnames.ora cho JDBC Thin

Oracle JDBC Thin cần biết vị trí file cấu hình. Có thể đặt system property:

~~~bash
java -Doracle.net.tns_admin=/opt/oracle/network/admin -jar application.jar
~~~

Hoặc cấu hình property trong ứng dụng:

~~~java
Properties properties = new Properties();
properties.setProperty(
    "oracle.net.tns_admin",
    "/opt/oracle/network/admin"
);
~~~

Tên property và khả năng cấu hình phụ thuộc JDBC driver version. Xác nhận theo tài liệu driver đang dùng.

### 8.3. Alias không có nghĩa phải cài Oracle Client

JDBC Thin có thể đọc tnsnames.ora khi được cấu hình thư mục. Không cần Oracle Client chỉ để dùng một TNS alias trong Thin driver.

OCI driver thì cần native Oracle Client libraries.

### 8.4. Quản lý nhiều môi trường

Có thể cung cấp tnsnames.ora riêng cho dev/test/prod. Tuy nhiên, cần tránh:
- Cùng alias nhưng trỏ khác service ngoài ý muốn.
- Container thiếu file cấu hình.
- Mount secret/config sai quyền.
- Alias cũ sau migration.
- File cấu hình không đồng bộ giữa các instance ứng dụng.

Ghi rõ endpoint thật trong deployment inventory và kiểm tra bằng kết nối runtime.

## 9. Viết Java code dùng JDBC URL

### 9.1. Kết nối tối thiểu bằng DriverManager

~~~java
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.ResultSet;
import java.sql.Statement;

public class OracleConnectionExample {
    public static void main(String[] args) throws Exception {
        String url =
            "jdbc:oracle:thin:@//db01.example.com:1521/appsvc.example.com";

        String username = System.getenv("DB_USER");
        String password = System.getenv("DB_PASSWORD");

        try (Connection connection =
                 DriverManager.getConnection(url, username, password);
             Statement statement = connection.createStatement();
             ResultSet resultSet = statement.executeQuery(
                 "SELECT sys_context('USERENV', 'SERVICE_NAME') FROM dual"
             )) {

            if (resultSet.next()) {
                System.out.println("Connected service: " + resultSet.getString(1));
            }
        }
    }
}
~~~

JDBC 4 tự đăng ký driver thông qua service provider khi driver JAR có trên classpath. Các ứng dụng cũ đôi khi dùng Class.forName("oracle.jdbc.OracleDriver"); phần lớn ứng dụng hiện đại không cần gọi thủ công.

### 9.2. Dùng connect descriptor trong Java

~~~java
String url =
    "jdbc:oracle:thin:@(DESCRIPTION=" +
    "(ADDRESS=(PROTOCOL=TCP)(HOST=db01.example.com)(PORT=1521))" +
    "(CONNECT_DATA=(SERVICE_NAME=appsvc.example.com)(SERVER=DEDICATED))" +
    ")";

try (Connection connection =
         DriverManager.getConnection(url, username, password)) {
    // Connection đã được mở.
}
~~~

Nên đặt URL trong configuration thay vì hardcode trong source. Nếu descriptor dài, dùng file cấu hình riêng hoặc Java text block theo phiên bản JDK.

### 9.3. Dùng OracleDataSource

~~~java
import java.sql.Connection;
import oracle.jdbc.pool.OracleDataSource;

OracleDataSource dataSource = new OracleDataSource();
dataSource.setURL(
    "jdbc:oracle:thin:@//db01.example.com:1521/appsvc.example.com"
);
dataSource.setUser(username);
dataSource.setPassword(password);

try (Connection connection = dataSource.getConnection()) {
    // Thực hiện SQL.
}
~~~

DataSource là abstraction chuẩn JDBC và phù hợp để tích hợp với application server hoặc connection pool. Với ứng dụng web, nên dùng pool được quản lý thay vì tạo TCP/database connection mới cho từng request.

### 9.4. Spring Boot

~~~properties
spring.datasource.url=jdbc:oracle:thin:@//db01.example.com:1521/appsvc.example.com
spring.datasource.username=app_user
spring.datasource.password=ENV_DB_PASSWORD
spring.datasource.driver-class-name=oracle.jdbc.OracleDriver

spring.datasource.hikari.maximum-pool-size=20
spring.datasource.hikari.minimum-idle=2
spring.datasource.hikari.connection-timeout=30000
~~~

Đây là cấu hình minh họa. Chọn pool size theo số connection database cho phép, workload, số replica ứng dụng và giới hạn session/process. Không nhân maximum-pool-size một cách máy móc khi tăng số pod.

### 9.5. Dependency driver

Với Maven, ứng dụng thường thêm Oracle JDBC artifact tương ứng JDK:

~~~xml
<dependency>
    <groupId>com.oracle.database.jdbc</groupId>
    <artifactId>ojdbc11</artifactId>
    <version>YOUR_APPROVED_VERSION</version>
</dependency>
~~~

Tên artifact và version phải khớp JDK, Oracle JDBC release, repository và chính sách dependency của tổ chức. Với JDK khác, có artifact phù hợp khác như ojdbc8. Kiểm tra Oracle JDBC compatibility matrix; không dùng một JAR tùy tiện chỉ vì compile thành công.

## 10. Connection pool và cấu hình URL

### 10.1. Vì sao nên dùng pool?

Mở connection mới gồm DNS, TCP handshake, listener negotiation, authentication và tạo session. Lặp lại cho từng request gây overhead lớn.

Connection pool:
- Tạo một số connection trước hoặc theo nhu cầu.
- Cho request mượn/trả connection.
- Giới hạn concurrency tới database.
- Có thể kiểm tra connection và loại connection hỏng.
- Quản lý timeout chờ pool.

Pool không tự sửa URL sai hoặc service không tồn tại. Khi endpoint đổi, cần cập nhật config và xử lý connection cũ theo quy trình.

### 10.2. Các tham số pool cần phân biệt

| Tham số | Ý nghĩa |
| --- | --- |
| Maximum pool size | Số connection tối đa trong pool |
| Minimum idle | Số connection idle mục tiêu |
| Connection timeout | Thời gian request chờ lấy connection từ pool |
| Validation timeout | Thời gian kiểm tra connection |
| Idle timeout | Thời gian giữ connection idle trước khi loại theo policy |
| Max lifetime | Tuổi tối đa connection trước khi recycle |
| Keepalive | Kiểm tra/duy trì connection theo pool nếu hỗ trợ |

Connection timeout của pool không giống CONNECT_TIMEOUT trong descriptor. Một request có thể đợi pool 30 giây, sau đó việc mở connection mới lại có timeout riêng.

### 10.3. Pool size và database capacity

Nếu có 10 application replicas và mỗi replica pool tối đa 30 connection, tổng lý thuyết có thể lên tới 300 session. Cần tính:
- Số replica tối đa khi autoscale.
- Batch/worker connection riêng.
- DBA/monitoring sessions.
- Database processes/sessions limit.
- Workload đồng thời thực tế.
- RAC service capacity.

Pool quá lớn có thể làm database tăng contention, CPU, memory và parse. Pool nhỏ quá có thể làm request chờ dù database còn khả năng xử lý. Đo p95/p99 pool wait và DB load để chọn.

### 10.4. Connection validation

Pool có thể kiểm tra connection bằng JDBC isValid hoặc validation query theo cấu hình. Không nên ping database quá thường xuyên vì validation cũng tiêu tốn round trip.

Sau network interruption hoặc failover, connection pool phải loại connection không còn usable và tạo lại theo policy. Kiểm tra hành vi của pool khi listener/service chuyển node.

## 11. Bảo mật connection string và transport

### 11.1. Không nhúng credentials vào URL

Tránh các kiểu URL có username/password hoặc đặt secret trực tiếp trong source, parfile, log và command history.

Nên:
- Lưu username/password trong secret manager.
- Inject vào runtime qua cơ chế bảo mật.
- Giới hạn quyền đọc environment/config.
- Không log full connection properties.
- Rotate secret theo quy trình.

### 11.2. Dùng TCPS khi cần TLS

Connect descriptor có thể dùng TCPS:

~~~text
jdbc:oracle:thin:@(DESCRIPTION=
  (ADDRESS=(PROTOCOL=TCPS)(HOST=db-secure.example.com)(PORT=2484))
  (CONNECT_DATA=(SERVICE_NAME=appsvc.example.com))
)
~~~

Listener phải được cấu hình TCPS và certificate/trust chain phù hợp. Driver cần trust material và các thuộc tính TLS/wallet tương ứng. Chỉ đổi TCP thành TCPS trong URL không đủ nếu listener và client chưa cấu hình TLS.

### 11.3. Tách bảo vệ đường truyền và bảo vệ dữ liệu lưu trữ

- TCPS bảo vệ kênh truyền.
- TDE bảo vệ datafile/tablespace/column theo cấu hình.
- Secret manager bảo vệ credentials.
- Network policy/firewall giới hạn endpoint.
- Database privilege giới hạn dữ liệu user có thể đọc.

Một URL an toàn không thay thế least privilege hoặc mã hóa dữ liệu at rest.

### 11.4. Không bật TLS verification yếu

Không tắt certificate validation hoặc hostname verification để “sửa nhanh” lỗi handshake. Kiểm tra:
- Certificate còn hạn.
- SAN/hostname khớp endpoint.
- Trust chain có đủ CA.
- Wallet/truststore đúng file.
- Đồng hồ host chính xác.
- TLS protocol/cipher tương thích driver và server.

## 12. Timeout, retry và độ ổn định kết nối

### 12.1. Connect timeout

Đặt giới hạn hợp lý cho việc mở connection để request không chờ vô hạn khi listener hoặc network mất phản hồi. Giá trị cần xét:
- DNS resolution.
- TCP connect.
- TLS handshake nếu dùng TCPS.
- Listener handoff.
- Authentication.
- Retry qua nhiều address.

### 12.2. Read/network timeout

Read timeout giới hạn thời gian driver chờ dữ liệu mạng. Nếu đặt quá thấp, query hợp lệ nhưng trả dữ liệu chậm có thể bị ngắt. Nếu đặt quá cao, thread có thể bị giữ lâu khi network gặp sự cố.

### 12.3. Statement timeout

JDBC có thể đặt timeout cho statement:

~~~java
try (PreparedStatement statement =
         connection.prepareStatement(
             "SELECT order_id FROM orders WHERE order_id = ?")) {

    statement.setLong(1, 9001L);
    statement.setQueryTimeout(30);

    try (ResultSet resultSet = statement.executeQuery()) {
        while (resultSet.next()) {
            System.out.println(resultSet.getLong(1));
        }
    }
}
~~~

setQueryTimeout giới hạn thời gian statement theo JDBC semantics. Nó không thay thế network timeout hoặc transaction timeout.

### 12.4. Retry chỉ cho thao tác an toàn

Retry kết nối có thể phù hợp trước khi request được gửi. Retry DML sau lỗi mạng cần biết transaction đã commit hay chưa. Thiết kế:
- Idempotency key.
- Unique business request ID.
- Transaction boundary rõ ràng.
- Error classification.
- Retry budget và exponential backoff.
- Logging đủ để đối chiếu.

Không retry vô hạn hoặc retry mọi SQLException như nhau.

## 13. Kiểm tra kết nối và xác nhận đúng database

### 13.1. Smoke test bằng SQL

Sau khi kết nối, chạy:

~~~sql
SELECT
    sys_context('USERENV', 'DB_NAME') AS db_name,
    sys_context('USERENV', 'SERVICE_NAME') AS service_name,
    sys_context('USERENV', 'CON_NAME') AS con_name,
    sys_context('USERENV', 'SESSION_USER') AS session_user
FROM dual;
~~~

Kết quả giúp xác nhận database, service, container và database user mà ứng dụng thực sự sử dụng.

### 13.2. Kiểm tra instance

~~~sql
SELECT instance_name,
       host_name,
       version,
       status
FROM   v$instance;
~~~

View V$INSTANCE cần quyền phù hợp. Trong RAC, kiểm tra thêm instance đang nhận session và service placement.

### 13.3. Kiểm tra PDB

~~~sql
SELECT name,
       open_mode
FROM   v$pdbs
ORDER  BY name;
~~~

PDB phải ở trạng thái cho phép kết nối và service phải được start/registered. Nếu service name trỏ tới PDB đóng hoặc không được đăng ký, listener có thể từ chối kết nối.

### 13.4. Kiểm tra từ client host

Từ đúng máy/pod chạy Java:
- Resolve DNS của host.
- Kiểm tra TCP port tới listener.
- Kiểm tra firewall/network policy.
- Xác nhận TCPS handshake nếu dùng TLS.
- Chạy một chương trình JDBC tối thiểu.
- Kiểm tra service name từ session sau khi kết nối.

tnsping hữu ích cho Oracle Net naming/endpoint trong môi trường có Oracle tools, nhưng không thay thế việc mở JDBC connection thật. JDBC Thin có thể hoạt động mà không cài Oracle Client.

## 14. Lỗi kết nối thường gặp

| Lỗi | Ý nghĩa thường gặp | Hướng kiểm tra |
| --- | --- | --- |
| ORA-12154 | Không phân giải được connect identifier | Alias, tnsnames.ora, TNS_ADMIN, tên alias |
| ORA-12514 | Listener không biết service được yêu cầu | SERVICE_NAME, listener registration, PDB/service state |
| ORA-12505 | Listener không biết SID được yêu cầu | SID/descriptor, listener services; có thể đang dùng nhầm SID thay service |
| ORA-12541 | Không có listener tại endpoint | Host, port, listener process, firewall |
| ORA-12543 | Không tới được destination host | DNS, route, network policy |
| ORA-12516/ORA-12520 | Listener không tìm được handler phù hợp | Session/process capacity, service handler, server mode |
| ORA-01017 | Username/password không hợp lệ | Credentials, case/quoted username, secret version |
| ORA-28000 | Account bị khóa | DBA kiểm tra account status và policy |
| ORA-28001 | Password hết hạn | Password rotation/expiry workflow |
| ORA-17002 | JDBC I/O error | Network, listener, socket reset, timeout, TLS |
| ORA-29024 | Certificate validation failure | Trust chain, certificate, hostname, wallet |
| ORA-12537 | Connection closed | Listener/network/server shutdown hoặc policy |

### 14.1. ORA-12154

Nếu dùng Easy Connect trực tiếp, kiểm tra URL có đúng dạng host/port/service không. Nếu dùng alias, kiểm tra:
- TNS_ADMIN.
- File tnsnames.ora.
- Alias spelling.
- File có mount vào container không.
- Driver Thin có đọc đúng thư mục không.

### 14.2. ORA-12514

Listener nhận được kết nối nhưng không biết service name được yêu cầu. Kiểm tra:
- SERVICE_NAME có đúng không.
- PDB đã mở chưa.
- Service đã start chưa.
- Listener đã nhận đăng ký service chưa.
- Host/port có trỏ tới đúng listener không.

### 14.3. ORA-12505

Lỗi thường gặp khi dùng SID nhưng listener không có SID đó. Nếu database cung cấp service name, đổi sang Easy Connect service form hoặc CONNECT_DATA SERVICE_NAME sau khi xác minh với DBA.

### 14.4. ORA-12541

Không có listener tại host/port. Kiểm tra DNS, port, firewall và trạng thái listener. Không đổi service name để sửa lỗi khi TCP endpoint chưa có listener.

### 14.5. ORA-17002

Đây là lỗi I/O JDBC tổng quát, cần xem nested cause và stack trace. Có thể liên quan connection reset, socket timeout, firewall idle timeout, listener shutdown hoặc TLS/network issue. Không chỉ dựa vào mã ORA-17002.

### 14.6. Lỗi authentication

Khi nhận ORA-01017/ORA-28000/ORA-28001:
- Xác minh user và database service.
- Kiểm tra secret đang được inject.
- Kiểm tra account status và password expiry.
- Xác nhận ứng dụng không trỏ nhầm môi trường.
- Không ghi password vào log để debug.

## 15. Quy trình chọn dạng URL

### 15.1. Dùng Easy Connect khi

- Có một host/listener endpoint.
- Có service name rõ ràng.
- Không cần nhiều address hoặc Oracle Net options.
- Muốn config đơn giản, dễ đưa vào container/environment.

Ví dụ:

~~~text
jdbc:oracle:thin:@//db01.example.com:1521/appsvc.example.com
~~~

### 15.2. Dùng connect descriptor khi

- Cần nhiều listener address.
- Cần LOAD_BALANCE/FAILOVER rõ ràng.
- Cần timeout/retry policy chi tiết.
- Cần SERVER=DEDICATED/SHARED.
- Cần TCPS hoặc cấu trúc Oracle Net nâng cao.
- Muốn kiểm soát đầy đủ DESCRIPTION/ADDRESS/CONNECT_DATA.

### 15.3. Dùng TNS alias khi

- DBA quản lý tập trung connect descriptor.
- Nhiều ứng dụng dùng cùng naming configuration.
- Có quy trình phân phối tnsnames.ora đáng tin cậy.
- Muốn đổi endpoint mà không sửa application URL.

### 15.4. Bảng quyết định

| Nhu cầu | Lựa chọn phù hợp |
| --- | --- |
| Một host + port + service | Easy Connect |
| Nhiều host trong cùng service | Easy Connect Plus hoặc descriptor |
| RAC dùng SCAN và service | Easy Connect tới SCAN hoặc descriptor |
| Timeout/retry/address policy chi tiết | Connect descriptor |
| Tên kết nối do DBA quản lý | TNS alias |
| Legacy kết nối một instance bằng SID | SID URL/descriptor nếu được yêu cầu |
| TLS với listener TCPS | Descriptor hoặc Easy Connect Plus theo cấu hình driver |
| Ứng dụng container cần config ngắn | Easy Connect qua environment/config |

## 16. Các ví dụ cấu hình hoàn chỉnh

### 16.1. Java ứng dụng local development

~~~text
jdbc:oracle:thin:@//localhost:1521/freepdb1
~~~

Dùng khi Oracle Database local/container đã mở service freepdb1 và port được publish ra localhost. Tên service phụ thuộc image/database cấu hình; xác nhận bằng listener hoặc DBA.

### 16.2. Spring Boot kết nối PDB

~~~properties
spring.datasource.url=jdbc:oracle:thin:@//oracle-db.internal:1521/hrpdb.internal
spring.datasource.username=hr_app
spring.datasource.password=ENV_HR_DB_PASSWORD
~~~

Kiểm tra CON_NAME sau khi kết nối để chắc chắn session vào đúng PDB.

### 16.3. RAC với SCAN

~~~text
jdbc:oracle:thin:@//rac-scan.example.com:1521/orders_rw.example.com
~~~

Dùng service được Clusterware quản lý. Kiểm tra preferred/available instances và service policy với DBA.

### 16.4. Hai listener address với descriptor

~~~text
jdbc:oracle:thin:@(DESCRIPTION=
  (CONNECT_TIMEOUT=10)
  (RETRY_COUNT=2)
  (RETRY_DELAY=2)
  (ADDRESS_LIST=
    (LOAD_BALANCE=ON)
    (FAILOVER=ON)
    (ADDRESS=(PROTOCOL=TCP)(HOST=db1.example.com)(PORT=1521))
    (ADDRESS=(PROTOCOL=TCP)(HOST=db2.example.com)(PORT=1521))
  )
  (CONNECT_DATA=(SERVICE_NAME=appsvc.example.com))
)
~~~

Đo thời gian kết nối khi một host down và khi cả hai host đều khỏe. Kết quả phụ thuộc DNS, listener và driver.

### 16.5. TNS alias

~~~text
jdbc:oracle:thin:@PROD_APP
~~~

Với TNS_ADMIN trỏ tới thư mục chứa tnsnames.ora. Kiểm tra file được phân phối nhất quán trên mọi application instance.

### 16.6. TCPS descriptor

~~~text
jdbc:oracle:thin:@(DESCRIPTION=
  (ADDRESS=(PROTOCOL=TCPS)(HOST=db-secure.example.com)(PORT=2484))
  (CONNECT_DATA=(SERVICE_NAME=secure_app.example.com))
)
~~~

Cần cấu hình TLS ở listener và trust material ở client theo tài liệu Oracle JDBC Security. Không chỉ đổi protocol mà bỏ qua certificate validation.

## 17. Những hiểu nhầm thường gặp

**“SID và service name là một.”** Không. SID nhận diện instance; service name định tuyến tới dịch vụ database.

**“Easy Connect cần tnsnames.ora.”** Không. Easy Connect URL chứa endpoint trực tiếp.

**“Dùng Thin driver phải cài Oracle Client.”** Không. Thin là driver thuần Java.

**“Port luôn là 1521.”** Không. 1521 phổ biến nhưng listener có thể dùng port khác.

**“URL kết nối thành công nghĩa là vào đúng PDB.”** Không. Xác nhận CON_NAME và SERVICE_NAME sau khi mở session.

**“SCAN là SID của RAC.”** Không. SCAN là tên endpoint cluster; ứng dụng kết nối qua service name.

**“LOAD_BALANCE=ON tự phân phối mọi query giữa node.”** Không. Nó liên quan lựa chọn address; runtime service load balancing có cơ chế riêng.

**“FAILOVER=ON tự replay transaction.”** Không. Connect-time failover không tự bảo đảm replay transaction đang chạy.

**“Connect timeout là query timeout.”** Không. Connect timeout áp dụng giai đoạn mở connection; statement timeout áp dụng SQL statement.

**“TNS alias chỉ dùng được với OCI.”** Không. JDBC Thin có thể dùng alias nếu cấu hình vị trí tnsnames.ora phù hợp.

**“Có thể để password trong URL để dễ deploy.”** Không nên. Credentials phải được quản lý bằng secret mechanism và không xuất hiện trong log.

**“TCPS chỉ cần thay TCP thành TCPS.”** Không. Listener, certificate, trust chain và driver phải được cấu hình tương thích.

## 18. Bài thực hành

Thực hành bằng database test và account có quyền tối thiểu. Không thử endpoint hoặc credentials production nếu chưa được cấp phép.

### Bài 1 — Easy Connect cơ bản

Kết nối bằng URL host/port/service. Chạy truy vấn lấy SERVICE_NAME, CON_NAME và SESSION_USER.

### Bài 2 — Phân biệt service và SID

Lấy SID và service name từ DBA. Thử URL theo service name; so sánh với URL SID trong môi trường test. Giải thích lỗi nếu listener không đăng ký SID.

### Bài 3 — Tìm service

Truy vấn V$SERVICES hoặc DBA_SERVICES và đối chiếu với LSNRCTL SERVICES. Ghi lại service dành cho ứng dụng.

### Bài 4 — Connect descriptor đơn

Chuyển URL Easy Connect thành DESCRIPTION/ADDRESS/CONNECT_DATA. Xác nhận cùng service và database.

### Bài 5 — Nhiều address

Tạo descriptor có hai listener address trong môi trường test. Tắt một endpoint theo kế hoạch test và quan sát connect-time failover.

### Bài 6 — Timeout/retry

Thử các giá trị CONNECT_TIMEOUT, RETRY_COUNT và RETRY_DELAY. Ghi thời gian kết nối khi host không phản hồi. Khôi phục cấu hình sau thử nghiệm.

### Bài 7 — RAC SCAN

Kết nối qua SCAN và service name. Xem instance_name/host_name để biết session được định tuyến tới node nào.

### Bài 8 — PDB service

Kết nối tới PDB service và kiểm tra CON_NAME. Thử service của PDB khác trong môi trường test để thấy routing khác nhau.

### Bài 9 — TNS alias với Thin

Tạo alias trong tnsnames.ora, đặt oracle.net.tns_admin và kết nối bằng jdbc:oracle:thin:@ALIAS.

### Bài 10 — Connection pool

Cấu hình HikariCP với URL Easy Connect. Đo thời gian chờ pool, số connection và database session khi tăng tải.

### Bài 11 — TCPS

Dùng listener test có TCPS và certificate hợp lệ. Kết nối bằng descriptor TCPS và xác nhận hostname/trust chain.

### Bài 12 — Lỗi service

Dùng service name sai trong môi trường test. Nhận diện ORA-12514 và phân biệt với ORA-12541 khi listener không chạy.

### Bài 13 — Lỗi alias

Dùng TNS alias không tồn tại hoặc TNS_ADMIN sai. Nhận diện ORA-12154 và kiểm tra file cấu hình.

### Bài 14 — Thiết kế URL production

Viết cấu hình cho một ứng dụng có RAC/PDB service, timeout, pool, secret injection và TLS. Ghi rõ lý do chọn Easy Connect hay descriptor và cách xác minh endpoint sau khi kết nối.

## 19. Tài liệu Oracle tham khảo

- [Oracle Database JDBC Developer's Guide 19c — Connecting to the Database](https://docs.oracle.com/en/database/oracle/oracle-database/19/jjdbc/data-sources-and-URLs.html): JDBC URL, DataSource và các dạng kết nối.
- [Oracle Database JDBC Developer's Guide 19c — JDBC Thin Driver](https://docs.oracle.com/en/database/oracle/oracle-database/19/jjdbc/introducing-JDBC.html): kiến trúc và sử dụng Oracle JDBC Thin.
- [Oracle Database Net Services Reference 19c — Local Naming Parameters](https://docs.oracle.com/en/database/oracle/oracle-database/19/netrf/local-naming-parameters.html): DESCRIPTION, ADDRESS, CONNECT_DATA và Oracle Net connect descriptor.
- [Oracle Database Net Services Administrator's Guide 19c — Easy Connect Naming Method](https://docs.oracle.com/en/database/oracle/oracle-database/19/netag/easy-connect-naming-method.html): cú pháp Easy Connect.
- [Oracle Database Net Services Administrator's Guide 19c — Easy Connect Plus](https://docs.oracle.com/en/database/oracle/oracle-database/19/netag/easy-connect-plus.html): nhiều host, port và tham số kết nối.
- [Oracle Database Net Services Administrator's Guide 19c — Configuring and Administering Oracle Net Listener](https://docs.oracle.com/en/database/oracle/oracle-database/19/netag/configuring-and-administering-oracle-net-listener.html): listener, service registration và LSNRCTL.
- [Oracle Database JDBC Developer's Guide 19c — Using TNS Names with JDBC Thin](https://docs.oracle.com/en/database/oracle/oracle-database/19/jjdbc/data-sources-and-URLs.html): alias và cấu hình thư mục network admin.
- [Oracle Database JDBC Developer's Guide 19c — Data Sources and Connection Properties](https://docs.oracle.com/en/database/oracle/oracle-database/19/jjdbc/data-sources-and-URLs.html): OracleDataSource, connection properties và URL.
- [Oracle Real Application Clusters Administration and Deployment Guide 19c](https://docs.oracle.com/en/database/oracle/oracle-database/19/racad/): SCAN, service, client connection và workload management.

Oracle JDBC Thin thường kết nối trực tiếp bằng Easy Connect URL có host, port và service name. Khi cần nhiều address, timeout, failover, load balancing hoặc TCPS, connect descriptor cho phép khai báo cấu trúc Oracle Net chi tiết hơn; TNS alias phù hợp khi DBA quản lý tập trung cấu hình. **Luôn xác minh service name và container thực tế sau khi kết nối, quản lý credentials ngoài URL, và hiểu rằng failover kết nối không tự động bảo đảm transaction được replay.**
