# JDBC Thin, OCI driver và tiêu chí lựa chọn

Oracle JDBC cung cấp giao diện Java Database Connectivity để ứng dụng Java kết nối và làm việc với Oracle Database. Ứng dụng dùng cùng các API chuẩn như Connection, PreparedStatement, CallableStatement và ResultSet; phần khác nhau nằm ở cách driver giao tiếp với Oracle Net và các thư viện native.

Hai driver phổ biến là:

- **JDBC Thin:** driver thuần Java, kết nối trực tiếp tới database qua Oracle Net bằng TCP/IP hoặc TCPS. Ứng dụng chỉ cần JDBC driver JAR tương thích với JDK.
- **JDBC OCI:** driver dùng Oracle Call Interface (OCI) thông qua thư viện native của Oracle Client. Máy chạy ứng dụng phải có Oracle Client/Instant Client và native library phù hợp.

Với đa số ứng dụng Java mới, JDBC Thin là lựa chọn mặc định vì triển khai đơn giản, đa nền tảng và phù hợp với container/cloud. OCI phù hợp khi hệ thống có yêu cầu cụ thể về OCI/native client, cần dùng cấu hình Oracle Client hiện hữu hoặc một khả năng mà phiên bản Thin đang dùng không đáp ứng.

Không nên chọn driver chỉ vì suy nghĩ OCI luôn nhanh hơn Thin. Hiệu năng phụ thuộc workload, round trip, fetch size, statement cache, connection pool, network latency, database plan và cấu hình client. Hãy benchmark trên môi trường đại diện trước khi quyết định.

## 1. JDBC driver nằm ở đâu trong kiến trúc?

JDBC là API chuẩn của Java. Oracle JDBC driver hiện thực API đó để chuyển các lời gọi Java thành giao thức Oracle Net.

~~~text
Java application
      |
      v
JDBC API
      |
      v
Oracle JDBC driver
      |
      +---------------------------+
      |                           |
      v                           v
   JDBC Thin                    JDBC OCI
   Java networking              OCI native libraries
      |                           |
      +-------------+-------------+
                    |
                    v
              Oracle Net
                    |
                    v
             Oracle Database
~~~

Ứng dụng vẫn dùng các interface JDBC chuẩn. Phần code xử lý SQL, transaction, ResultSet và exception có thể giống nhau giữa Thin và OCI nếu ứng dụng không phụ thuộc extension riêng của driver.

### 1.1 Driver không phải connection pool

Driver chịu trách nhiệm tạo kết nối vật lý và giao tiếp với database. Connection pool quản lý vòng đời các kết nối để ứng dụng tái sử dụng chúng.

Ví dụ các thành phần:

- Oracle JDBC Thin hoặc OCI: driver.
- Oracle UCP, HikariCP hoặc pool của application server: connection pool.
- Oracle Database service: endpoint database.

Chọn Thin hay OCI không tự quyết định có dùng pool hay không. Ứng dụng production thường cần pool để tránh tạo kết nối mới cho từng request.

### 1.2 Driver không phải Oracle Client đầy đủ

JDBC Thin không yêu cầu cài Oracle Client trên máy ứng dụng. JDBC OCI cần thư viện native OCI từ Oracle Client hoặc Instant Client tương thích.

Không nhầm JDBC driver JAR với SQL*Plus, RMAN hoặc bộ Oracle Client. Đây là các thành phần có mục đích và dependency khác nhau.

## 2. JDBC Thin driver

JDBC Thin là driver thuần Java. Nó thực hiện Oracle Net protocol trong Java và kết nối trực tiếp tới listener/service của Oracle Database.

Đặc điểm:

- Không cần cài Oracle Client native trên host.
- Dùng cùng một loại JAR trên Windows, Linux và các hệ điều hành được JDK hỗ trợ.
- Phù hợp ứng dụng standalone, application server, container và cloud.
- Có thể kết nối bằng host/port/service name, connect descriptor hoặc TNS alias theo cấu hình.
- Hỗ trợ các tính năng Oracle JDBC phổ biến như bind variables, batch, LOB, REF CURSOR, callable statement và transaction.
- Có thể cấu hình TLS/TCPS, wallet và các tính năng bảo mật được phiên bản hỗ trợ.

### 2.1 Ưu điểm

**Triển khai đơn giản:** chỉ cần đưa đúng JDBC JAR vào classpath hoặc dependency graph. Không cần cài native Oracle Client ở mọi máy chạy ứng dụng.

**Đa nền tảng:** cùng một artifact Java có thể được triển khai trên các môi trường JDK tương thích.

**Phù hợp container:** image ứng dụng không phải chứa Oracle Client native chỉ để mở JDBC connection.

**Dễ quản lý dependency:** driver có thể được quản lý qua Maven/Gradle, repository nội bộ và quy trình build.

**Phù hợp cloud:** kết nối TCP/TCPS tới database service thường dễ cấu hình hơn việc đóng gói native client.

### 2.2 Hạn chế và điều cần kiểm tra

- Phải chọn driver JAR tương thích với JDK và Oracle Database release.
- Các tính năng đặc thù cần kiểm tra support matrix của Thin driver.
- TNS alias, wallet, TLS và các tùy chọn Oracle Net cần cấu hình đúng.
- Nếu hệ thống đang dựa vào OCI-specific capability, cần xác nhận có thể chuyển sang Thin hay không.

Thin không có nghĩa là chỉ hỗ trợ một chuỗi URL đơn giản. Driver có thể dùng connect descriptor, TNS configuration, TCPS và các tính năng nâng cao theo release.

## 3. JDBC OCI driver

JDBC OCI sử dụng Oracle Call Interface (OCI) thông qua thư viện native được cài từ Oracle Client hoặc Instant Client.

Đặc điểm:

- Cần Oracle Client/Instant Client có OCI library phù hợp.
- JVM phải nạp được native library của đúng kiến trúc.
- Cấu hình Oracle Net phía client như TNS_ADMIN, tnsnames.ora, sqlnet.ora và wallet có thể được dùng theo cơ chế OCI.
- Triển khai phụ thuộc hệ điều hành, kiến trúc CPU, bitness và phiên bản Oracle Client.

### 3.1 Ưu điểm

- Tích hợp với Oracle Client/OCI đã có trong môi trường.
- Có thể phù hợp với hệ thống phụ thuộc vào khả năng native hoặc cơ chế xác thực/cấu hình client đặc thù.
- Có thể tái sử dụng các Oracle Net configuration đã được quản trị tập trung.
- Là lựa chọn khi một yêu cầu cụ thể được Oracle hỗ trợ qua OCI nhưng không được đáp ứng bằng Thin trong release đang dùng.

### 3.2 Chi phí triển khai

- Phải cài và cập nhật Oracle Client/Instant Client.
- Cần đảm bảo native library có trong PATH, LD_LIBRARY_PATH hoặc cơ chế tìm kiếm thư viện tương ứng.
- JVM và OCI library phải cùng kiến trúc, ví dụ đều 64-bit.
- Container image phải chứa native dependency đúng hệ điều hành/base image.
- Nâng cấp driver và client phải được kiểm thử cùng nhau.
- Lỗi load native library khó xử lý hơn lỗi dependency Java thông thường.

### 3.3 OCI không mặc nhiên nhanh hơn

OCI sử dụng native code, nhưng điều đó không đảm bảo ứng dụng sẽ nhanh hơn Thin trong mọi workload. Nếu thời gian chủ yếu nằm ở database execution, network round trip, lock, I/O hoặc cách ứng dụng fetch dữ liệu, đổi driver có thể không cải thiện đáng kể.

Chỉ chọn OCI vì hiệu năng khi benchmark cho thấy lợi ích ổn định, đo được và đáng để đổi lấy độ phức tạp triển khai.

## 4. So sánh JDBC Thin và JDBC OCI

| Tiêu chí | JDBC Thin | JDBC OCI |
|---|---|---|
| Kiểu driver | Thuần Java | Java kết hợp native OCI |
| Oracle Client trên host | Không cần | Cần OCI library từ Oracle Client/Instant Client |
| Native library | Không | Có |
| Phụ thuộc OS/bitness | Chủ yếu phụ thuộc JDK | Phụ thuộc JDK, OS, kiến trúc và Client |
| Đóng gói container | Đơn giản | Phải đóng gói native client tương thích |
| Kết nối TCP/TCPS | Có, theo feature support | Có |
| TNS alias/connect descriptor | Có thể cấu hình | Có thể dùng Oracle Net configuration |
| Quản trị client | Chủ yếu quản lý JAR | Quản lý JAR và Oracle Client |
| Vận hành cloud | Thường thuận tiện | Phụ thuộc khả năng cài native client |
| OCI-specific integration | Không dùng OCI native API | Có |
| Hiệu năng | Thường đáp ứng tốt workload JDBC | Không mặc nhiên nhanh hơn; cần benchmark |
| Nâng cấp | Quản lý driver artifact | Phối hợp driver và native client |
| Lựa chọn mặc định | Phù hợp đa số ứng dụng Java mới | Chỉ khi có yêu cầu cụ thể |

## 5. Chọn JDBC driver theo nhu cầu

### 5.1 Chọn Thin khi

- Phát triển ứng dụng Java mới.
- Chạy trên Kubernetes, Docker hoặc cloud runtime.
- Cần deploy cùng artifact trên nhiều hệ điều hành.
- Muốn giảm số thành phần phải cài ở application host.
- Kết nối bằng TCP/TCPS và Oracle service name đáp ứng yêu cầu.
- Không có phụ thuộc vào OCI-specific feature.

### 5.2 Cân nhắc OCI khi

- Ứng dụng hiện hữu phụ thuộc vào OCI/native Oracle Client.
- Có yêu cầu xác thực hoặc Oracle Net integration đặc thù đã được xác nhận cần OCI.
- Chính sách vận hành yêu cầu dùng Oracle Client được quản trị sẵn.
- Một tính năng cần thiết được hỗ trợ qua OCI trong phiên bản đang triển khai.
- Benchmark có kiểm soát chứng minh OCI cải thiện workload đủ lớn để bù chi phí native deployment.

### 5.3 Không chọn chỉ dựa vào

- Driver nào có tên nghe “native” hơn.
- Một benchmark tổng quát trên máy khác.
- Kinh nghiệm từ Oracle Database version rất cũ.
- Việc máy DBA đã cài Oracle Client.
- Giả định Thin không hỗ trợ TLS, wallet hoặc TNS.

## 6. Chọn phiên bản JDBC driver

Oracle phát hành JDBC driver theo các JAR/artifact tương ứng với mức Java mà driver hỗ trợ. Tên artifact phổ biến gồm các dòng như ojdbc8 và ojdbc11; tên và ma trận hỗ trợ có thể thay đổi theo release.

Khi chọn driver, kiểm tra đồng thời:

1. JDK version của ứng dụng.
2. Oracle JDBC driver version.
3. Oracle Database version và Release Update.
4. Application server/framework.
5. Hệ điều hành và kiến trúc nếu dùng OCI.
6. Các tính năng cần dùng: TLS, wallet, FAN/FCF, UCP, sharding, AQ, LOB, JSON hoặc các API đặc thù.

Không suy luận rằng JAR mới nhất luôn phù hợp với mọi JDK hoặc database cũ. Cần tra Oracle JDBC Developer's Guide và JDBC driver certification/support matrix cho đúng release.

### 6.1 Maven dependency

Ví dụ dependency Maven cho dòng driver tương thích JDK 11:

~~~xml
<dependency>
    <groupId>com.oracle.database.jdbc</groupId>
    <artifactId>ojdbc11</artifactId>
    <version>ORACLE_JDBC_VERSION</version>
</dependency>
~~~

ORACLE_JDBC_VERSION là placeholder do dự án thay bằng phiên bản đã được kiểm tra trong repository và ma trận tương thích.

### 6.2 Gradle dependency

Ví dụ:

~~~kotlin
dependencies {
    runtimeOnly("com.oracle.database.jdbc:ojdbc11:ORACLE_JDBC_VERSION")
}
~~~

Có thể dùng implementation thay cho runtimeOnly nếu code compile-time trực tiếp tham chiếu class Oracle-specific. Với ứng dụng chỉ dùng java.sql, runtimeOnly thường đủ cho driver.

### 6.3 Quản lý phiên bản qua property

~~~kotlin
val oracleJdbcVersion = providers.gradleProperty("oracleJdbcVersion")
    .orElse("SET_A_VALIDATED_VERSION")
    .get()

dependencies {
    runtimeOnly("com.oracle.database.jdbc:ojdbc11:$oracleJdbcVersion")
}
~~~

Không để placeholder chưa thay thế trong build production. Pin version rõ ràng, cập nhật qua dependency review và kiểm thử.

### 6.4 Không trộn JAR từ nhiều release

Một số tính năng cần thêm JAR phụ trợ như UCP, ONS, Oracle PKI hoặc thư viện bảo mật. Dùng bộ artifact có version tương thích với nhau. Không copy ngẫu nhiên ojdbc từ một release và oraclepki/osdt từ release khác vào cùng classpath.

## 7. JDBC Thin connection URL

Thin URL có prefix:

~~~text
jdbc:oracle:thin:@
~~~

### 7.1 Service name với Easy Connect

Mẫu thông dụng:

~~~text
jdbc:oracle:thin:@//dbhost.example.com:1521/sales.example.com
~~~

Trong đó:

- dbhost.example.com: hostname hoặc địa chỉ máy chủ.
- 1521: listener port ví dụ.
- sales.example.com: service name.

Nên dùng service name cho ứng dụng thay vì phụ thuộc SID của một instance. Service giúp database/RAC quản lý workload và role phù hợp.

### 7.2 SID dạng cũ

URL dạng SID:

~~~text
jdbc:oracle:thin:@dbhost.example.com:1521:ORCL
~~~

Đây là dạng legacy vẫn gặp trong hệ thống cũ. Với triển khai mới, ưu tiên service name và xác nhận cấu hình listener.

### 7.3 Connect descriptor

~~~text
jdbc:oracle:thin:@(DESCRIPTION=
  (ADDRESS=(PROTOCOL=TCP)(HOST=dbhost.example.com)(PORT=1521))
  (CONNECT_DATA=(SERVICE_NAME=sales.example.com))
)
~~~

Connect descriptor cho phép khai báo nhiều địa chỉ, retry, load balancing và các thuộc tính Oracle Net khác theo nhu cầu.

### 7.4 TNS alias

Có thể dùng alias trong tnsnames.ora:

~~~text
SALESDB =
  (DESCRIPTION =
    (ADDRESS = (PROTOCOL = TCP)
               (HOST = dbhost.example.com)
               (PORT = 1521))
    (CONNECT_DATA =
      (SERVICE_NAME = sales.example.com)
    )
  )
~~~

Thin URL:

~~~text
jdbc:oracle:thin:@SALESDB
~~~

Đặt thuộc tính TNS_ADMIN để driver tìm tnsnames.ora:

~~~text
-Doracle.net.tns_admin=/opt/app/oracle/network/admin
~~~

Đường dẫn là ví dụ. Có thể cấu hình qua connection properties theo hướng dẫn của driver.

### 7.5 TCPS

Thin driver hỗ trợ kết nối TCPS/TLS theo cấu hình và phiên bản tương ứng. Ví dụ connect descriptor:

~~~text
jdbc:oracle:thin:@(DESCRIPTION=
  (ADDRESS=(PROTOCOL=TCPS)(HOST=db.example.com)(PORT=2484))
  (CONNECT_DATA=(SERVICE_NAME=sales.example.com))
)
~~~

Để kết nối thành công, database listener, certificate, trust configuration và hostname verification phải được cấu hình đúng. Chỉ đổi PROTOCOL=TCP thành TCPS là chưa đủ.

## 8. JDBC OCI connection URL

OCI URL có prefix:

~~~text
jdbc:oracle:oci:@
~~~

### 8.1 Dùng TNS alias

~~~text
jdbc:oracle:oci:@SALESDB
~~~

OCI thường dùng Oracle Net configuration từ Oracle Client, bao gồm tnsnames.ora và sqlnet.ora theo cấu hình client.

### 8.2 Dùng connect descriptor

~~~text
jdbc:oracle:oci:@(DESCRIPTION=
  (ADDRESS=(PROTOCOL=TCP)(HOST=dbhost.example.com)(PORT=1521))
  (CONNECT_DATA=(SERVICE_NAME=sales.example.com))
)
~~~

Xác nhận cú pháp URL và khả năng descriptor với OCI driver version đang dùng. Trong môi trường enterprise, TNS alias thường dễ quản lý hơn vì DBA có thể cập nhật endpoint trong Oracle Net config.

### 8.3 Không dùng Thin prefix cho OCI

Các URL sau chọn hai driver khác nhau:

~~~text
jdbc:oracle:thin:@//dbhost:1521/service
jdbc:oracle:oci:@SALESDB
~~~

Đảm bảo dependency/classpath chứa driver cần thiết và URL prefix khớp với driver đã triển khai.

## 9. Kết nối JDBC bằng Java

Ứng dụng dùng API chuẩn java.sql:

~~~java
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.PreparedStatement;
import java.sql.ResultSet;

public class OracleJdbcExample {
    public static void main(String[] args) throws Exception {
        String url =
            "jdbc:oracle:thin:@//dbhost.example.com:1521/sales.example.com";

        String username = System.getenv("DB_USERNAME");
        String password = System.getenv("DB_PASSWORD");

        try (Connection connection =
                 DriverManager.getConnection(url, username, password);
             PreparedStatement statement =
                 connection.prepareStatement(
                     "SELECT employee_id, employee_name " +
                     "FROM employees WHERE department_id = ?")) {

            statement.setInt(1, 10);

            try (ResultSet resultSet = statement.executeQuery()) {
                while (resultSet.next()) {
                    System.out.println(
                        resultSet.getLong("employee_id") + " " +
                        resultSet.getString("employee_name"));
                }
            }
        }
    }
}
~~~

Đoạn code dùng Thin URL. Để thử OCI, đổi URL thành OCI URL hợp lệ và cung cấp native Oracle Client phù hợp; phần xử lý JDBC vẫn giữ nguyên.

### 9.1 Driver auto-registration

Với JDBC 4 trở lên, driver thường tự đăng ký thông qua service provider mechanism khi JAR nằm trên classpath/module path.

Trong code mới thường không cần:

~~~java
Class.forName("oracle.jdbc.OracleDriver");
~~~

Nếu dùng môi trường cũ hoặc classloader đặc biệt, có thể cần cấu hình explicit driver class theo framework. Tên class hiện đại là oracle.jdbc.OracleDriver; tránh dùng tên legacy oracle.jdbc.driver.OracleDriver trong code mới.

### 9.2 Không ghép username/password vào URL

Tránh:

~~~text
jdbc:oracle:thin:username/password@//host:1521/service
~~~

URL và command line có thể bị ghi vào log, process listing hoặc monitoring. Truyền credential qua Properties/secret manager và không hard-code password.

## 10. Kết nối bằng Properties

Có thể truyền thuộc tính kết nối riêng:

~~~java
import java.sql.Connection;
import java.sql.DriverManager;
import java.util.Properties;

String url =
    "jdbc:oracle:thin:@//dbhost.example.com:1521/sales.example.com";

Properties properties = new Properties();
properties.setProperty("user", System.getenv("DB_USERNAME"));
properties.setProperty("password", System.getenv("DB_PASSWORD"));
properties.setProperty("oracle.net.CONNECT_TIMEOUT", "5000");
properties.setProperty("oracle.jdbc.ReadTimeout", "30000");

try (Connection connection =
         DriverManager.getConnection(url, properties)) {
    // Execute database work.
}
~~~

Timeout property và đơn vị cần được xác nhận theo driver version. Kết nối production nên có timeout phù hợp để ứng dụng không treo vô hạn khi network/database gặp sự cố.

## 11. Thin, OCI và Oracle Net configuration

Oracle Net là tầng giao tiếp giữa client và database listener. Cả Thin và OCI đều có thể dùng Oracle Net connect descriptor, nhưng cách nạp cấu hình khác nhau.

### 11.1 Thin

Thin có thể dùng:

- Easy Connect.
- Full connect descriptor.
- TNS alias với TNS_ADMIN.
- TCPS/TLS và wallet theo cấu hình hỗ trợ.

Không cần Oracle Client chỉ để đọc tnsnames.ora; Thin driver có thể đọc cấu hình TNS theo thuộc tính được hỗ trợ.

### 11.2 OCI

OCI dùng Oracle Client native libraries và Oracle Net configuration từ client installation. Các file thường gặp:

- tnsnames.ora.
- sqlnet.ora.
- ldap.ora nếu dùng LDAP naming.
- Wallet files nếu dùng TLS/wallet hoặc external authentication theo cấu hình.

Vị trí cấu hình có thể được xác định qua TNS_ADMIN, ORACLE_HOME hoặc cơ chế Oracle Client tương ứng. Ưu tiên cấu hình rõ ràng thay vì phụ thuộc môi trường shell không được kiểm soát.

### 11.3 Service name và SID

Service name đại diện dịch vụ database mà client kết nối. SID thường định danh instance. Trong RAC, PDB hoặc môi trường có nhiều instance, service name thường phù hợp hơn vì cho phép database quản lý phân phối session và role.

Hãy lấy service name từ DBA/Cloud console hoặc cấu hình listener chính thức, không tự đoán theo database name.

## 12. Thin và OCI trong RAC/HA

Ứng dụng kết nối RAC nên dùng service được quản trị cho workload, thay vì hard-code một node/instance.

Các cơ chế có thể tham gia:

- Service registration và listener.
- Load balancing.
- Connection failover.
- Fast Application Notification (FAN).
- Fast Connection Failover (FCF).
- Runtime Load Balancing.
- Oracle Universal Connection Pool (UCP).

Hỗ trợ và cách cấu hình FAN/FCF phụ thuộc driver version, pool, ONS, database release và topology. Không chỉ đổi URL là có failover hoàn chỉnh.

### 12.1 UCP

Oracle Universal Connection Pool là pool của Oracle có tích hợp với các tính năng Oracle Database. UCP có thể làm việc với Oracle JDBC driver; lựa chọn Thin/OCI vẫn là quyết định driver riêng.

Khi dùng UCP, kiểm tra:

- UCP version tương thích với JDBC driver.
- ONS configuration nếu dùng FAN.
- Service được cấu hình cho load balancing.
- Connection validation và timeout.
- Pool sizing.
- FCF behavior khi node/service down.

### 12.2 HikariCP hoặc pool khác

Pool bên thứ ba có thể quản lý JDBC connection cho Thin hoặc OCI. Các tính năng Oracle-specific như FAN/FCF có thể cần integration riêng hoặc UCP. Không giả định mọi pool hỗ trợ đầy đủ Oracle HA chỉ vì dùng cùng JDBC API.

## 13. Connection pooling và vòng đời connection

Không tạo connection mới cho mỗi câu SQL trong ứng dụng production có tải đáng kể. Việc mở connection bao gồm network handshake, authentication, session initialization và resource allocation.

Mô hình khuyến nghị:

~~~text
HTTP request
     |
     v
Application service
     |
     v
Connection pool
     |
     +--> JDBC connection 1
     +--> JDBC connection 2
     +--> JDBC connection N
                 |
                 v
           Oracle Database
~~~

Ứng dụng mượn connection từ pool, thực hiện transaction rồi trả lại pool. Đóng Connection trong code khi dùng pool thường trả connection về pool, không nhất thiết đóng physical session.

### 13.1 Không giữ connection quá lâu

- Không giữ connection trong lúc chờ gọi HTTP service khác.
- Không giữ transaction mở khi xử lý logic không liên quan database.
- Commit/rollback rõ ràng.
- Đóng ResultSet và Statement bằng try-with-resources.
- Trả connection về pool ngay khi hoàn tất đơn vị công việc.

### 13.2 Pool size

Pool quá nhỏ có thể gây chờ connection; pool quá lớn có thể làm database quá tải session, process, memory và CPU.

Chọn max pool size theo:

- Số instance ứng dụng.
- Số replica/container.
- Database session/process limit.
- Thời gian giữ connection.
- Throughput và concurrency thực tế.
- Các workload khác dùng chung database.

Tổng số connection tối đa thường là số replica nhân max pool size, cộng các client khác. Phải tính tổng trên toàn hệ thống.

### 13.3 Connection validation

Pool nên có cách kiểm tra connection trước khi cấp lại nếu môi trường có idle timeout, firewall timeout hoặc failover. Validation query và timeout phải được cấu hình hợp lý để tránh tạo thêm tải.

## 14. Bảo mật kết nối: TLS, wallet và credential

Thin và OCI có thể hỗ trợ các cơ chế bảo mật khác nhau theo phiên bản và cấu hình. Hãy xác nhận support matrix thay vì cho rằng chỉ OCI mới có TLS hoặc wallet.

### 14.1 TCPS/TLS

TCPS bảo vệ dữ liệu trên đường truyền bằng TLS. Cần:

- Listener hỗ trợ TCPS.
- Certificate chain hợp lệ.
- Truststore/wallet phù hợp.
- Hostname verification.
- TLS protocol/cipher theo policy.
- Rotation certificate có kế hoạch.

Không tắt certificate validation để “sửa nhanh” lỗi handshake trong production.

### 14.2 Oracle Wallet

Wallet có thể lưu certificate/credential theo cơ chế Oracle. Thin driver có thể dùng wallet theo cấu hình tương thích; OCI có thể dùng wallet thông qua Oracle Client/Oracle Net.

Đường dẫn wallet, mật khẩu và certificate phải được quản lý như secret:

- Không commit vào Git.
- Không đưa secret vào Docker image chung.
- Mount từ secret manager/secure volume.
- Giới hạn quyền đọc file.
- Có rotation và backup.

### 14.3 External authentication

Một số mô hình Kerberos, TLS certificate authentication, OS authentication hoặc external identity có yêu cầu riêng theo driver, Oracle Client, OS và database configuration. Nếu external authentication là lý do chọn OCI, hãy kiểm tra chính xác feature matrix của phiên bản thay vì dựa vào tên gọi.

### 14.4 Credential management

Ưu tiên:

- Secret manager của nền tảng.
- Oracle Wallet/secure external password store nếu phù hợp.
- Environment injection từ secret service.
- Credential rotation và least privilege.

Không lưu password trong source code, URL, log, exception message hoặc file parfile chia sẻ.

## 15. OCI deployment: native library và bitness

Đây là phần khác biệt vận hành lớn nhất giữa Thin và OCI.

Để dùng OCI:

1. Cài Oracle Client hoặc Instant Client phù hợp.
2. Cài đúng OCI native library.
3. Đảm bảo driver JAR và client tương thích.
4. Đảm bảo JVM và native library cùng kiến trúc.
5. Cấu hình đường dẫn thư viện.
6. Cấu hình Oracle Net.
7. Kiểm thử trên đúng host/container runtime.

### 15.1 Windows

Windows cần tìm được OCI DLL qua PATH hoặc cơ chế loader tương ứng. JVM 64-bit cần Oracle Client 64-bit. Một Oracle Client 32-bit không thể được nạp vào JVM 64-bit.

### 15.2 Linux

Linux thường cần cấu hình LD_LIBRARY_PATH hoặc linker configuration để tìm OCI shared libraries. Cần kiểm tra dependencies hệ điều hành của Instant Client và base image.

### 15.3 Container

Nếu dùng OCI trong container:

- Cài native client trong image hoặc mount theo quy trình đã duyệt.
- Dùng đúng base image và glibc/runtime compatibility.
- Đảm bảo library path.
- Không copy thư viện từ host khác kiến trúc.
- Quét lỗ hổng và cập nhật client image.
- Kiểm tra license/redistribution terms của Oracle Client artifact.

Thin thường giảm đáng kể công việc này vì chỉ cần Java driver JAR.

## 16. Lỗi thường gặp khi dùng Thin

### No suitable driver

Nguyên nhân có thể:

- Thiếu ojdbc JAR.
- JAR không nằm trong runtime classpath.
- URL prefix sai.
- Dependency bị exclude hoặc không được đóng gói.

Kiểm tra dependency tree và URL.

### ClassNotFoundException: oracle.jdbc.OracleDriver

Driver JAR chưa có trong classpath/module path hoặc classloader không nhìn thấy driver.

Với JDBC 4, driver thường auto-register; không cần gọi Class.forName nếu JAR được nạp đúng.

### ORA-12514

Listener không nhận diện service name được yêu cầu.

Kiểm tra:

- Service name chính xác.
- Listener service registration.
- PDB đã mở và service đang active.
- URL không nhầm SID với service.

### ORA-12154

Không phân giải được connect identifier/TNS alias.

Kiểm tra:

- Alias trong tnsnames.ora.
- TNS_ADMIN.
- File có được đọc từ process runtime không.
- Syntax descriptor.

### ORA-01017

Username/password không hợp lệ hoặc authentication configuration không phù hợp. Kiểm tra credential, case, account status và password rotation.

### ORA-28040

Authentication protocol không tương thích giữa client/driver và database policy. Nâng driver/client lên phiên bản được hỗ trợ; không hạ chính sách authentication trên production như một cách khắc phục mặc định.

### SSLHandshakeException

Kiểm tra certificate chain, truststore/wallet, hostname, thời hạn certificate, TLS protocol và cipher. Không vô hiệu hóa certificate validation.

## 17. Lỗi thường gặp khi dùng OCI

### UnsatisfiedLinkError

JVM không nạp được native OCI library hoặc dependency của library.

Kiểm tra:

- Oracle Client/Instant Client đã cài chưa.
- PATH/LD_LIBRARY_PATH.
- Bitness của JVM và Client.
- Native library dependencies.
- Library version.
- Container base image.

### OCI initialization error

Có thể do OCI library không tương thích, client installation thiếu thành phần hoặc Oracle Net config sai. Đọc đầy đủ stack trace và kiểm tra client installation.

### TNS alias không phân giải

Kiểm tra TNS_ADMIN, tnsnames.ora, sqlnet.ora và Oracle Client đang được process sử dụng. Đừng chỉ kiểm tra biến môi trường ở terminal khác; service/application server có thể chạy với environment riêng.

### Client version mismatch

Driver JAR, Oracle Client và database cần nằm trong tổ hợp được hỗ trợ. Đối chiếu Oracle JDBC compatibility matrix và OCI client interoperability documentation.

## 18. Theo dõi driver và database session

Khi điều tra kết nối, nên ghi:

- JDBC driver name/version.
- JDK version.
- Connection URL đã loại bỏ secret.
- Database service.
- Application module/action.
- Client identifier.
- Pool name và connection timeout.
- Oracle session ID nếu cần.

Có thể đặt module/action từ Java:

~~~java
try (var statement = connection.prepareCall(
        "begin dbms_application_info.set_module(?, ?); end;")) {
    statement.setString(1, "ORDER_SERVICE");
    statement.setString(2, "CREATE_ORDER");
    statement.execute();
}
~~~

Hoặc dùng API Oracle JDBC/DBMS_APPLICATION_INFO theo convention của ứng dụng. Khi connection được trả về pool, cần reset module/action/client identifier để request sau không thừa hưởng context cũ.

Không ghi password, token hoặc dữ liệu nhạy cảm vào module/action/client identifier.

## 19. JDBC statement và transaction best practices

Driver choice không thay thế việc sử dụng JDBC đúng cách.

### 19.1 Dùng PreparedStatement

~~~java
String sql =
    "SELECT employee_id, salary " +
    "FROM employees WHERE employee_id = ?";

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setLong(1, employeeId);

    try (ResultSet rs = ps.executeQuery()) {
        if (rs.next()) {
            BigDecimal salary = rs.getBigDecimal("salary");
        }
    }
}
~~~

PreparedStatement giúp bind dữ liệu, giảm nguy cơ SQL injection và hỗ trợ statement reuse.

### 19.2 Quản lý transaction

~~~java
connection.setAutoCommit(false);

try {
    // Execute related DML statements.
    connection.commit();
} catch (Exception e) {
    connection.rollback();
    throw e;
}
~~~

Trong code production, cần bảo đảm rollback khi lỗi và trả connection về pool ở trạng thái sạch. Pool có thể reset một số thuộc tính, nhưng không nên dựa vào hành vi reset không được xác nhận.

### 19.3 Batch DML

~~~java
String sql = "INSERT INTO order_items(order_id, item_id) VALUES (?, ?)";

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    for (OrderItem item : items) {
        ps.setLong(1, item.orderId());
        ps.setLong(2, item.itemId());
        ps.addBatch();
    }
    ps.executeBatch();
}
~~~

Batch giảm network round trips khi xử lý nhiều row. Batch size cần đo theo workload, memory và giới hạn transaction.

### 19.4 Fetch size

Với query trả nhiều hàng, fetch size có thể giảm số round trips:

~~~java
statement.setFetchSize(500);
~~~

Giá trị tối ưu phụ thuộc row width, network latency, memory và cách ứng dụng tiêu thụ ResultSet. Không đặt quá lớn cho mọi query.

## 20. Statement cache và hiệu năng

Oracle JDBC có các cơ chế statement caching. Connection pool cũng có thể quản lý prepared statement cache tùy driver/pool.

Lợi ích:

- Giảm parse overhead.
- Tái sử dụng statement/cursor.
- Giảm chi phí tạo PreparedStatement lặp lại.

Kiểm tra:

- Driver version.
- Implicit/explicit statement cache configuration.
- Pool statement cache.
- SQL text stability.
- Bind variables.

Không bật nhiều lớp cache cùng lúc mà không hiểu cách phối hợp và giới hạn cursor. Theo dõi open cursors, parse calls và database cursor sharing.

## 21. Driver, UCP và các thư viện phụ trợ

Một số ứng dụng dùng thêm:

- Oracle UCP: connection pool.
- ONS: Oracle Notification Service cho notification/FAN trong các cấu hình phù hợp.
- Oracle PKI/Wallet libraries: hỗ trợ một số cấu hình certificate/wallet.
- Oracle XML/JSON/LOB-related libraries theo API và release.

Không phải ứng dụng nào cũng cần mọi JAR phụ trợ. Chỉ thêm dependency khi tính năng thực sự yêu cầu và dùng phiên bản tương thích với ojdbc.

### 21.1 Dependency hygiene

- Pin version.
- Tránh duplicate ojdbc JAR trong application server và WAR/EAR.
- Kiểm tra classloader precedence.
- Dùng dependency lock/verification nếu build hỗ trợ.
- Quét CVE và cập nhật patch.
- Kiểm thử startup, connection, transaction và failover sau nâng cấp.

### 21.2 Driver do application server cung cấp

Nếu application server quản lý datasource, driver có thể được cài ở server module thay vì đóng gói trong ứng dụng. Không đồng thời cài nhiều phiên bản ojdbc không chủ ý trong server và ứng dụng.

## 22. Thin/OCI trong môi trường cloud và container

### 22.1 JDBC Thin

Thường phù hợp nhất:

- Image Java nhỏ.
- Không cần native dependency.
- Dễ build đa nền tảng.
- Dễ nâng cấp JAR qua pipeline.
- Kết nối Oracle Database service qua TCP/TCPS.

### 22.2 JDBC OCI

Chỉ nên dùng khi có lý do:

- Native OCI feature bắt buộc.
- Chính sách client configuration hiện hữu.
- Runtime có thể cài Oracle Client đúng cách.
- Image có thể quản lý patch và CVE của native client.

### 22.3 Kubernetes secrets

Dù dùng Thin hay OCI, credential và wallet nên được mount/inject từ secret manager. Không bake password hoặc private key vào image.

### 22.4 Network policy

Thin không có nghĩa kết nối đi qua HTTP. JDBC Thin thường dùng Oracle Net qua TCP/TCPS. Network policy, firewall và egress rules phải cho phép đúng host/port/service.

## 23. Driver compatibility và nâng cấp

Trước khi nâng JDBC driver:

1. Xác định JDK version.
2. Xác định Oracle Database versions đang kết nối.
3. Đối chiếu Oracle JDBC support matrix.
4. Kiểm tra application server/framework.
5. Kiểm tra API/behavior changes.
6. Kiểm tra TLS, wallet và authentication.
7. Kiểm tra UCP/ONS/PKI companion JAR.
8. Chạy integration test và performance test.
9. Canary rollout.
10. Có rollback artifact.

### 23.1 Backward compatibility không phải vô hạn

JDBC driver mới thường hỗ trợ nhiều database release, nhưng không phải mọi tổ hợp đều được chứng nhận hoặc hỗ trợ. Driver cũ có thể không hỗ trợ JDK mới hoặc tính năng database mới.

Không chọn version chỉ dựa trên việc build thành công. Phải test runtime và đối chiếu ma trận hỗ trợ chính thức.

### 23.2 Nâng Oracle Client khi dùng OCI

Với OCI, cần kiểm tra thêm:

- Oracle Client version.
- JDBC OCI driver JAR version.
- Native library dependencies.
- TNS_ADMIN/sqlnet configuration.
- 32/64-bit alignment.
- Compatibility với OS/base image.

Nâng JAR mà bỏ quên native client có thể gây lỗi load hoặc hành vi không được hỗ trợ.

## 24. Kiểm thử lựa chọn driver

Nếu đang cân nhắc chuyển từ OCI sang Thin hoặc ngược lại, tạo test matrix:

| Nhóm kiểm thử | Nội dung |
|---|---|
| Connectivity | Service name, listener, DNS, timeout |
| Authentication | Password, wallet, external auth nếu dùng |
| Security | TLS/TCPS, certificate validation |
| SQL | SELECT, DML, PL/SQL, REF CURSOR |
| Data types | NUMBER, DATE/TIMESTAMP, LOB, JSON theo ứng dụng |
| Transactions | Commit, rollback, isolation |
| Performance | Throughput, latency, fetch/batch |
| Pooling | Borrow/return, validation, leak detection |
| HA | RAC service failover, FAN/FCF nếu dùng |
| Deployment | Container, OS, native library nếu OCI |
| Recovery | Restart database, network interruption |
| Observability | JDBC metrics, SQL_ID, module/action |

### 24.1 Benchmark công bằng

- Dùng cùng database service.
- Dùng cùng JDK và application build.
- Dùng cùng SQL, bind values và dataset.
- Cùng pool size và fetch size.
- Warm-up JVM và statement cache.
- Đo p50/p95/p99 latency.
- Đo throughput, CPU, network và database wait.
- Chạy đủ lâu để tránh kết luận từ một lần đo.

### 24.2 Đo cả vận hành

Ngoài tốc độ, đo:

- Thời gian build/deploy.
- Kích thước container.
- Số dependency.
- Quy trình patch.
- Số lỗi startup.
- Thời gian xử lý incident.

Thin thường thắng về độ đơn giản triển khai, nhưng quyết định cuối phải theo yêu cầu thật.

## 25. Decision matrix

| Câu hỏi | Nếu Có | Hướng lựa chọn |
|---|---|---|
| Ứng dụng Java mới, không có OCI-specific requirement? | Có | JDBC Thin |
| Chạy container/Kubernetes/cloud? | Có | Ưu tiên Thin |
| Muốn không cài Oracle Client trên host? | Có | Thin |
| Có yêu cầu native OCI/client integration đã xác nhận? | Có | Cân nhắc OCI |
| Dựa vào Oracle Net client config đặc thù? | Có | So sánh Thin TNS support và OCI; chỉ chọn OCI nếu cần |
| Cần external authentication đặc thù? | Có | Kiểm tra support matrix; chọn driver đáp ứng |
| OCI benchmark nhanh hơn rõ rệt? | Có | Đánh giá lợi ích với chi phí native deployment |
| Không có người quản lý Oracle Client trên mọi host? | Có | Thin |
| Application server đã quản trị OCI client chuẩn? | Có | OCI có thể phù hợp |
| Chưa biết yêu cầu native cụ thể? | Có | Bắt đầu với Thin và xác minh tính năng |

Quy tắc thực tế: bắt đầu với Thin; chuyển sang OCI khi có yêu cầu kỹ thuật cụ thể hoặc số liệu benchmark đủ thuyết phục.

## 26. Ví dụ cấu hình Spring Boot

### 26.1 Thin driver

Maven dependency:

~~~xml
<dependency>
    <groupId>com.oracle.database.jdbc</groupId>
    <artifactId>ojdbc11</artifactId>
    <version>ORACLE_JDBC_VERSION</version>
</dependency>
~~~

application.yml:

~~~yaml
spring:
  datasource:
    url: jdbc:oracle:thin:@//dbhost.example.com:1521/sales.example.com
    username: DB_USERNAME_FROM_SECRET
    password: DB_PASSWORD_FROM_SECRET
    driver-class-name: oracle.jdbc.OracleDriver
    hikari:
      maximum-pool-size: 20
      connection-timeout: 30000
      validation-timeout: 5000
~~~

Đây là cấu hình minh họa. Pool size và timeout phải được tính theo số replica và giới hạn database. Không lưu credential thật trong file cấu hình được commit.

### 26.2 OCI driver

URL có thể dùng:

~~~yaml
spring:
  datasource:
    url: jdbc:oracle:oci:@SALESDB
    username: DB_USERNAME_FROM_SECRET
    password: DB_PASSWORD_FROM_SECRET
    driver-class-name: oracle.jdbc.OracleDriver
~~~

Ngoài JAR, runtime phải có Oracle Client/Instant Client native library và Oracle Net configuration. Nếu dùng Spring Boot executable JAR trong container, phải xác nhận library path trong chính container, không chỉ trên máy build.

## 27. Ví dụ kiểm tra driver runtime

Có thể in metadata driver:

~~~java
try (Connection connection = dataSource.getConnection()) {
    var metadata = connection.getMetaData();

    System.out.println("Driver: " + metadata.getDriverName());
    System.out.println("Driver version: " +
                       metadata.getDriverVersion());
    System.out.println("Database: " +
                       metadata.getDatabaseProductVersion());
}
~~~

Ghi nhận driver name/version trong diagnostics giúp phân biệt môi trường dùng Thin hay OCI và phát hiện lệch version giữa các instance ứng dụng.

Không ghi URL đầy đủ nếu URL có credential hoặc thông tin hạ tầng nhạy cảm.

## 28. Troubleshooting theo lớp

Khi kết nối lỗi, chia thành các lớp:

1. Dependency: JAR có trong runtime không?
2. Driver: URL prefix và driver class có đúng?
3. Name resolution: hostname/TNS alias có phân giải?
4. Network: firewall, route, listener port?
5. Service: service name có đăng ký?
6. Authentication: user/password/wallet?
7. TLS: certificate/trust/hostname?
8. Database: account status, session limit, resource?
9. Pool: timeout, stale connection, exhausted pool?
10. Native client: OCI library/bitness/path nếu dùng OCI?

Không thay đổi database authentication policy hoặc tắt TLS validation trước khi xác định lỗi nằm ở lớp nào.

## 29. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Cách làm đúng |
|---|---|---|
| Nghĩ OCI luôn nhanh hơn Thin | Tăng độ phức tạp mà không có lợi ích | Benchmark cùng workload |
| Dùng OCI nhưng không cài native client | UnsatisfiedLinkError | Cài Client/Instant Client đúng kiến trúc |
| JVM 64-bit dùng client 32-bit | Không load được native library | Đồng bộ bitness |
| Dùng SID URL cho service name | ORA-12505/12514 hoặc kết nối sai | Dùng đúng SERVICE_NAME |
| Thin không đọc TNS alias | Cấu hình sai driver | Cấu hình TNS_ADMIN và alias |
| Trộn nhiều ojdbc JAR | Classloader conflict | Chỉ giữ một driver version có chủ ý |
| Trộn ojdbc và UCP/ONS khác version | Lỗi runtime hoặc feature | Dùng bộ artifact tương thích |
| Hard-code password trong URL | Lộ secret qua log/process | Dùng Properties/secret manager |
| Tạo connection mỗi request | Tốn handshake và session | Dùng connection pool |
| Pool quá lớn | Database cạn session/resource | Tính tổng connection toàn hệ thống |
| Không đặt timeout | Request treo lâu khi network lỗi | Cấu hình connect/read/pool timeout |
| Coi TCPS chỉ cần đổi URL | TLS handshake thất bại | Cấu hình listener, cert và trust |
| Tắt certificate validation | Mất bảo vệ MITM | Sửa trust/hostname đúng |
| Coi JDBC Thin là HTTP | Network policy sai | Mở đúng TCP/TCPS Oracle Net |
| Chỉ test local | Production thiếu native config hoặc secret | Test trong image/runtime thật |
| Nâng driver không test database cũ | Lỗi tương thích | Đối chiếu support matrix và integration test |

## 30. Bài thực hành tự kiểm tra

Thực hiện với database lab và credential được cấp.

### Bài 1 — Kết nối bằng Thin

Thêm JDBC dependency phù hợp JDK, tạo URL service name và chạy SELECT 1 FROM dual.

### Bài 2 — Dùng PreparedStatement

Truy vấn một bảng theo bind variable, đọc ResultSet và đóng resource bằng try-with-resources.

### Bài 3 — So sánh URL

Thử Easy Connect, TNS alias và connect descriptor. Ghi nhận cấu hình cần thiết cho từng kiểu.

### Bài 4 — TNS_ADMIN

Đặt TNS_ADMIN và kết nối bằng alias với Thin driver. Xác nhận process đọc đúng tnsnames.ora.

### Bài 5 — TCPS

Trong môi trường lab có certificate, cấu hình TCPS và kiểm tra certificate/hostname validation.

### Bài 6 — OCI runtime

Trên host được phép, cài Instant Client đúng bitness, cấu hình native library path và thử OCI URL.

### Bài 7 — Pool

Dùng HikariCP hoặc UCP, đo thời gian borrow/return và theo dõi tổng session trên database.

### Bài 8 — Timeout

Thử connect timeout và read timeout trong lab. Ghi loại exception và thời gian phản hồi.

### Bài 9 — Driver metadata

In getDriverName/getDriverVersion và database product version. Lưu thông tin vào diagnostics.

### Bài 10 — Benchmark

So sánh Thin/OCI trên cùng workload nếu môi trường hỗ trợ. Đo p95 latency, throughput, CPU và network.

### Bài 11 — Failover

Trong môi trường RAC/HA được phép, kiểm tra service failover và pool behavior. Không mô phỏng node failure trên production.

### Bài 12 — Compatibility review

Lập bảng JDK, JDBC driver, database release, UCP/ONS và Oracle Client version. Đối chiếu tài liệu support matrix trước khi nâng cấp.

## 31. Checklist lựa chọn và triển khai

**Yêu cầu**

- Ứng dụng có OCI-specific requirement không?
- Có cần Oracle Client native integration không?
- Runtime là VM, application server, container hay cloud?
- Có yêu cầu TNS alias, wallet, TCPS hoặc external authentication?

**Tương thích**

- JDK version đã xác định?
- JDBC JAR phù hợp JDK?
- Oracle Database release được hỗ trợ?
- Application server/framework tương thích?
- OCI Client/bitness đúng nếu dùng OCI?
- Companion JAR cùng bộ version?

**Kết nối**

- URL dùng đúng service name?
- TNS_ADMIN/descriptor chính xác?
- Timeout được cấu hình?
- Credential lấy từ secret manager?
- TLS certificate được validate?

**Vận hành**

- Có connection pool?
- Pool size tính trên toàn bộ replica?
- Có validation và leak detection?
- Có metrics driver/pool?
- Có module/action/client identifier?
- Có quy trình nâng cấp/rollback?

**Kiểm chứng**

- Integration test thành công?
- Performance test công bằng?
- Restart/network interruption được kiểm tra?
- RAC/HA behavior đã được kiểm chứng nếu cần?
- Container/runtime production đã được thử?

## 32. Ghi nhớ

| Khái niệm | Điều cần nhớ |
|---|---|
| JDBC | API chuẩn Java để truy cập database |
| JDBC Thin | Driver thuần Java, không cần Oracle Client |
| JDBC OCI | Driver dùng OCI native library từ Oracle Client |
| ojdbc JAR | Artifact JDBC driver |
| oracle.jdbc.OracleDriver | Driver class hiện đại |
| Thin URL | jdbc:oracle:thin:@... |
| OCI URL | jdbc:oracle:oci:@... |
| Service name | Endpoint dịch vụ database, thường ưu tiên hơn SID |
| TNS_ADMIN | Vị trí Oracle Net configuration |
| TCPS | Oracle Net qua TLS |
| Oracle Client/Instant Client | Thành phần native cần cho OCI |
| Bitness | JVM và native library phải tương thích kiến trúc |
| UCP | Oracle connection pool |
| FAN/FCF | Notification và failover cho HA theo cấu hình hỗ trợ |
| Connection pool | Tái sử dụng physical connections |
| PreparedStatement | Bind dữ liệu, hỗ trợ an toàn và reuse |
| Fetch size | Điều chỉnh lượng row lấy mỗi lượt |
| Statement cache | Tái sử dụng statement/cursor |
| Support matrix | Xác nhận tổ hợp JDK/driver/database/client |

JDBC Thin là lựa chọn mặc định hợp lý cho phần lớn ứng dụng Java hiện đại: dễ đóng gói, đa nền tảng và không cần native Oracle Client. JDBC OCI dành cho trường hợp có yêu cầu OCI/native integration cụ thể hoặc benchmark chứng minh lợi ích đủ lớn. Cả hai dùng chung JDBC API ở phần lớn code ứng dụng, nhưng khác rõ ở URL, dependency và vận hành. Hãy chọn driver theo JDK/database compatibility, security, HA, container strategy và khả năng quản trị client; dùng connection pool, quản lý secret đúng cách và kiểm thử trong runtime production trước khi triển khai.
