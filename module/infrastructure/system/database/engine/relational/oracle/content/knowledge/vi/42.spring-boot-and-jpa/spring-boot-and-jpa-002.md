# HikariCP, Oracle UCP và ranh giới quản lý kết nối

Trong ứng dụng Spring Boot dùng JPA với Oracle Database, kết nối JDBC là tài nguyên hữu hạn. Mỗi lần tạo kết nối vật lý có thể phải thực hiện network handshake, xác thực, thiết lập session và khởi tạo trạng thái Oracle. Nếu ứng dụng tạo rồi đóng kết nối cho từng câu SQL, chi phí này tăng nhanh và database phải xử lý nhiều lần đăng nhập/đăng xuất.

Connection pool giữ một nhóm kết nối JDBC đã được tạo sẵn. Khi một request cần truy cập database, ứng dụng mượn một connection từ pool, dùng nó trong phạm vi công việc, sau đó trả lại pool. HikariCP và Oracle Universal Connection Pool (UCP) đều cung cấp cơ chế này, nhưng có phạm vi tích hợp khác nhau:

- **HikariCP** là connection pool JDBC gọn, nhanh và phổ biến trong Spring Boot. Nó phù hợp với ứng dụng cần quản lý vòng đời connection theo chuẩn JDBC.
- **Oracle UCP** là pool của Oracle, có tích hợp sâu hơn với hệ sinh thái Oracle, bao gồm các khả năng như Fast Connection Failover (FCF), FAN, Runtime Load Balancing (RLB), connection labeling và một số tính năng HA tùy cấu hình/version.

Điều cần hiểu rõ là pool chỉ quản lý việc cấp phát và thu hồi connection. Spring transaction manager quản lý transaction; JPA EntityManager quản lý persistence context; Hibernate quản lý việc thực thi SQL và ánh xạ object. Các lớp này phối hợp với nhau nhưng không phải một thành phần.

## 1. Vì sao cần connection pool?

Giả sử một ứng dụng có 100 request mỗi giây và mỗi request cần truy vấn Oracle nhiều lần. Nếu mỗi truy vấn tự tạo một TCP/JDBC connection mới, hệ thống sẽ liên tục trả chi phí:

1. Phân giải hostname và thiết lập network connection.
2. Bắt tay Oracle Net.
3. Xác thực user.
4. Tạo database session và thiết lập session state.
5. Thực thi SQL.
6. Đóng connection và giải phóng session.

Pool giữ connection đã được xác thực để tái sử dụng:

~~~text
HTTP request
    |
    v
Spring service / repository
    |
    v
JPA / Hibernate / JDBC
    |
    | borrow connection
    v
Connection pool
    |
    +---- JDBC connection 1 ---- Oracle session
    +---- JDBC connection 2 ---- Oracle session
    +---- JDBC connection 3 ---- Oracle session
    +---- ...
    |
    | return connection
    v
Connection pool
~~~

Pool giúp:

- Giảm số lần tạo kết nối vật lý.
- Giới hạn số session mà một instance ứng dụng có thể mở.
- Tái sử dụng connection sau khi công việc kết thúc.
- Phát hiện hoặc loại bỏ một số connection không còn hợp lệ.
- Điều tiết request khi tất cả connection đang được sử dụng.
- Tập trung cấu hình timeout và kích thước pool.

Pool không làm truy vấn SQL tự nhanh hơn, không thay thế index/query tuning, không tự sửa lỗi transaction và cũng không làm database có thêm năng lực xử lý. Nếu pool quá lớn, ứng dụng có thể tạo quá nhiều session và làm Oracle quá tải.

## 2. Phân biệt DataSource, Connection, EntityManager và Transaction

Các khái niệm sau thường bị gộp chung khi cấu hình Spring Boot:

| Thành phần | Trách nhiệm |
|---|---|
| DataSource | Cung cấp JDBC connection; trong ứng dụng có pool, nó thường là facade quản lý pool |
| Connection | Đại diện một phiên JDBC đang được mượn từ DataSource |
| HikariCP hoặc UCP | Quản lý tập connection vật lý và việc mượn/trả connection |
| EntityManagerFactory | Tạo các JPA EntityManager |
| EntityManager | Quản lý persistence context, entity state và thao tác JPA |
| Hibernate Session | Persistence context/implementation tương ứng của Hibernate |
| Spring transaction manager | Bắt đầu, commit, rollback và đồng bộ tài nguyên transaction |
| Oracle database session | Session phía database tương ứng với kết nối vật lý đã xác thực |

Một ứng dụng Spring Boot thường có một DataSource được dùng chung cho JPA, JdbcTemplate và các thành phần JDBC khác. Nếu chúng cùng sử dụng DataSource và transaction manager phù hợp, các thao tác có thể tham gia cùng transaction.

### Ranh giới tài nguyên

- Pool quản lý **connection vật lý** và thời gian connection được mượn.
- Transaction manager quản lý **ranh giới commit/rollback**.
- EntityManager quản lý **persistence context** và trạng thái entity.
- Repository/service xác định **ranh giới nghiệp vụ**.

Không gọi Connection.close() để commit transaction. Không gọi EntityManager.close() trên EntityManager do Spring inject và quản lý. Không giữ connection trong biến static hoặc chia sẻ nó giữa nhiều thread.

## 3. HikariCP là gì?

HikariCP là JDBC connection pool tập trung vào hiệu năng, kích thước nhỏ và hành vi tương đối đơn giản. Spring Boot thường chọn HikariCP làm implementation mặc định nếu thư viện này có trên classpath.

Các đặc điểm thường dùng:

- maximumPoolSize: số connection tối đa trong pool.
- minimumIdle: số connection idle mục tiêu tối thiểu.
- connectionTimeout: thời gian tối đa chờ mượn connection.
- idleTimeout: thời gian connection idle có thể được loại bỏ khi pool có nhiều hơn minimumIdle.
- maxLifetime: tuổi thọ tối đa của connection trong pool.
- keepaliveTime: chu kỳ kiểm tra/giữ kết nối idle, nếu bật.
- validationTimeout: timeout cho thao tác kiểm tra connection.
- leakDetectionThreshold: ngưỡng ghi log khi connection bị giữ quá lâu.

HikariCP dùng chuẩn JDBC và phù hợp với nhiều database. Nó không phải Oracle-specific HA pool; các tích hợp chuyên biệt như FAN/FCF và Runtime Load Balancing của Oracle UCP không tự xuất hiện chỉ vì URL kết nối trỏ đến Oracle.

## 4. Cấu hình HikariCP trong Spring Boot

Khi dùng spring-boot-starter-data-jpa hoặc spring-boot-starter-jdbc, HikariCP thường được đưa vào classpath theo dependency management của Spring Boot.

Ví dụ Maven dependency:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-data-jpa</artifactId>
</dependency>

<dependency>
    <groupId>com.oracle.database.jdbc</groupId>
    <artifactId>ojdbc11</artifactId>
</dependency>
~~~

Phiên bản JDBC driver nên được quản lý qua BOM hoặc dependency management phù hợp với JDK và Oracle Database đang dùng. Không lấy ngẫu nhiên một version driver mới nhất mà chưa kiểm tra compatibility.

### application.yml

~~~yaml
spring:
  datasource:
    url: jdbc:oracle:thin:@//dbhost.example.com:1521/APP_SERVICE
    username: app_runtime
    password: ${DB_PASSWORD}
    driver-class-name: oracle.jdbc.OracleDriver
    hikari:
      pool-name: app-oracle-pool
      maximum-pool-size: 20
      minimum-idle: 5
      connection-timeout: 30000
      validation-timeout: 5000
      idle-timeout: 600000
      max-lifetime: 1740000
      keepalive-time: 120000
      leak-detection-threshold: 60000
~~~

Các giá trị trên chỉ là ví dụ ban đầu, không phải cấu hình chuẩn cho mọi ứng dụng. Đặc biệt:

- maximum-pool-size phải được tính theo tổng số instance ứng dụng và khả năng database.
- minimum-idle có thể đặt thấp hơn maximum để pool co giãn, hoặc để mặc định bằng maximum nếu muốn pool cố định.
- connection-timeout là thời gian chờ connection từ pool, không phải timeout của câu SQL.
- max-lifetime cần ngắn hơn giới hạn tuổi thọ connection của database, firewall, load balancer hoặc network.
- auto-commit phải phù hợp với transaction management của ứng dụng; khi dùng Spring/JPA, cấu hình transaction manager rõ ràng.
- leak-detection-threshold chỉ phát hiện và ghi log connection bị giữ lâu; nó không tự giải quyết nguyên nhân hoặc bảo đảm đóng connection.

### Ép chọn HikariCP

Nếu classpath có nhiều pool implementation và muốn chọn tường minh:

~~~yaml
spring:
  datasource:
    type: com.zaxxer.hikari.HikariDataSource
~~~

Trong ứng dụng Spring Boot tiêu chuẩn, thường không cần khai báo DataSource bean thủ công nếu chỉ dùng một datasource và cấu hình theo prefix chuẩn.

## 5. Oracle JDBC URL và service name

Với Oracle, ứng dụng thường kết nối bằng service name:

~~~yaml
spring:
  datasource:
    url: jdbc:oracle:thin:@//dbhost.example.com:1521/orders.example.com
~~~

Đây là Easy Connect URL. Có thể dùng connect descriptor phức tạp hơn khi cần nhiều address, timeout hoặc cấu hình failover:

~~~text
jdbc:oracle:thin:@(DESCRIPTION=
  (ADDRESS=(PROTOCOL=TCP)(HOST=dbhost.example.com)(PORT=1521))
  (CONNECT_DATA=(SERVICE_NAME=orders.example.com))
)
~~~

Trong RAC, nên kết nối bằng service được quản lý cho workload thay vì hard-code SID của một instance. Service giúp database định tuyến session đến instance phù hợp theo cấu hình cluster.

Không nhầm service name với SID:

- SID nhận diện một instance.
- Service name nhận diện dịch vụ logic/workload.
- PDB thường có application service riêng để client vào đúng container.

## 6. Oracle UCP là gì?

Oracle Universal Connection Pool (UCP) là connection pool của Oracle cho JDBC. UCP có thể dùng với Oracle JDBC driver và cung cấp nhiều khả năng tích hợp Oracle-specific hơn pool JDBC tổng quát.

Các khả năng thường được quan tâm:

- Fast Connection Failover (FCF) với sự kiện FAN.
- Runtime Load Balancing (RLB) trong môi trường hỗ trợ.
- Connection labeling để phân loại connection theo trạng thái/session context.
- Connection harvesting để quản lý connection khi pool thiếu tài nguyên.
- Connection validation và timeout.
- Một số khả năng HA, replay hoặc integration khác tùy driver, database, service và version.

UCP đặc biệt đáng xem xét khi ứng dụng chạy trên Oracle RAC hoặc cần tích hợp với Oracle HA stack. Việc bật UCP không tự động bật mọi tính năng HA; cần cấu hình service, ONS, driver, database và môi trường cluster tương ứng.

## 7. Dependency UCP cho Spring Boot

Ví dụ Maven dependencies:

~~~xml
<dependency>
    <groupId>com.oracle.database.jdbc</groupId>
    <artifactId>ojdbc11</artifactId>
</dependency>

<dependency>
    <groupId>com.oracle.database.jdbc</groupId>
    <artifactId>ucp</artifactId>
</dependency>

<dependency>
    <groupId>com.oracle.database.ha</groupId>
    <artifactId>ons</artifactId>
</dependency>
~~~

ojdbc11 là ví dụ driver cho môi trường Java tương ứng. Chọn artifact và version theo JDK, Oracle Database, Spring Boot và hướng dẫn Oracle JDBC/UCP hiện hành. ONS dependency thường cần khi sử dụng FAN/FCF với cấu hình ONS tương ứng; không phải mọi ứng dụng UCP đều phải cấu hình FCF.

Nếu dùng dependency management của Oracle JDBC BOM hoặc BOM nội bộ, hãy để BOM quản lý các version tương thích thay vì tự trộn version driver, UCP và ONS.

## 8. Cấu hình UCP thành DataSource trong Spring

UCP cung cấp PoolDataSource và factory để tạo pool. Một cách rõ ràng là khai báo bean riêng:

~~~java
import oracle.ucp.jdbc.PoolDataSource;
import oracle.ucp.jdbc.PoolDataSourceFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Primary;
import org.springframework.core.env.Environment;

import java.sql.SQLException;

@Configuration
public class OracleUcpConfiguration {

    @Bean
    @Primary
    public PoolDataSource dataSource(Environment env) throws SQLException {
        PoolDataSource pool = PoolDataSourceFactory.getPoolDataSource();

        pool.setConnectionFactoryClassName(
            "oracle.jdbc.pool.OracleDataSource"
        );
        pool.setURL(env.getRequiredProperty("app.datasource.url"));
        pool.setUser(env.getRequiredProperty("app.datasource.username"));
        pool.setPassword(env.getRequiredProperty("app.datasource.password"));

        pool.setConnectionPoolName("app-oracle-ucp");
        pool.setInitialPoolSize(3);
        pool.setMinPoolSize(3);
        pool.setMaxPoolSize(20);
        pool.setConnectionWaitTimeout(30);
        pool.setValidateConnectionOnBorrow(true);

        return pool;
    }
}
~~~

Đây là ví dụ cấu hình khởi đầu. Các phương thức và property phải khớp version UCP đang dùng. Không hard-code password; đọc secret từ environment/secret manager hoặc cấu hình bảo mật của nền tảng.

Ví dụ application.yml:

~~~yaml
app:
  datasource:
    url: jdbc:oracle:thin:@//dbhost.example.com:1521/APP_SERVICE
    username: app_runtime
    password: ${DB_PASSWORD}
~~~

Khi tự tạo DataSource bean, cần bảo đảm Spring Boot không tạo thêm một pool khác ngoài ý muốn. Nếu ứng dụng có nhiều DataSource, đánh dấu @Primary cho datasource mặc định hoặc dùng @Qualifier rõ ràng ở các bean JPA/JdbcTemplate tương ứng.

### Cấu hình bằng properties

Spring Boot và các version khác nhau có thể hỗ trợ binding UCP theo prefix riêng hoặc thông qua DataSourceBuilder/bean được cấu hình. Nếu dùng auto-configuration chuyên biệt của Boot, kiểm tra tài liệu đúng phiên bản về property prefix và class UCP. Không sao chép prefix từ một version Boot khác mà chưa xác minh.

## 9. Cấu hình FCF, FAN và ONS với UCP

Trong Oracle RAC, node hoặc instance có thể bị lỗi, service có thể chuyển sang instance khác. Nếu pool không nhận biết sự kiện HA, một số connection trong pool có thể trỏ đến instance đã chết và chỉ phát hiện lỗi khi ứng dụng dùng chúng.

Các khái niệm:

- **FAN (Fast Application Notification):** sự kiện thông báo trạng thái service/instance/node tới client hoặc middle tier.
- **ONS (Oracle Notification Service):** hạ tầng truyền thông báo FAN.
- **FCF (Fast Connection Failover):** UCP sử dụng sự kiện FAN để loại bỏ connection không còn hợp lệ và phản ứng nhanh hơn với thay đổi cluster.
- **RLB (Runtime Load Balancing):** sử dụng thông tin service/load để phân phối connection phù hợp với workload trong môi trường hỗ trợ.

Ví dụ cấu hình UCP:

~~~java
pool.setFastConnectionFailoverEnabled(true);
pool.setONSConfiguration(
    "nodes=racnode1.example.com:6200,racnode2.example.com:6200"
);
~~~

Địa chỉ/port ONS phải lấy từ cấu hình Grid Infrastructure thực tế. Không đoán port hoặc tự mở firewall theo ví dụ. Trong một số cấu hình, client có thể dùng remote ONS configuration hoặc cơ chế discovery khác theo phiên bản.

Để FCF hoạt động đúng:

1. Database chạy trong cấu hình Oracle HA được hỗ trợ, ví dụ RAC.
2. Service được cấu hình phù hợp cho workload.
3. FAN event được phát và ONS có thể truy cập.
4. UCP bật FCF và được cấu hình ONS đúng.
5. Oracle JDBC driver/UCP version tương thích.
6. Ứng dụng xử lý transaction bị gián đoạn theo cách an toàn.

FCF giúp pool nhận biết connection không còn hợp lệ; nó không thể làm một transaction đã bị ngắt tự động hoàn tất theo ý nghiệp vụ. Ứng dụng vẫn cần retry có kiểm soát và idempotency khi operation có thể đã commit ở phía server nhưng response bị mất.

## 10. HikariCP và UCP: khác nhau ở đâu?

| Tiêu chí | HikariCP | Oracle UCP |
|---|---|---|
| Phạm vi | Pool JDBC tổng quát | Pool JDBC của Oracle |
| Spring Boot | Được auto-config phổ biến, cấu hình đơn giản | Có thể cấu hình qua auto-config phù hợp hoặc khai báo bean |
| Oracle RAC/FAN/FCF | Không có tích hợp UCP-native tương đương | Hỗ trợ FCF/FAN theo cấu hình và version |
| Runtime Load Balancing | Không có tích hợp Oracle RLB native | Có thể tích hợp RLB trong môi trường hỗ trợ |
| Connection labeling | Không phải chức năng cốt lõi tương đương UCP | Có hỗ trợ |
| Connection harvesting | Không phải cơ chế đặc trưng của Hikari | Có hỗ trợ với cấu hình phù hợp |
| Độ đơn giản | Thường đơn giản, ít cấu hình | Có thêm cấu hình Oracle-specific |
| Phù hợp | Ứng dụng JDBC/JPA thông thường, một endpoint hoặc HA xử lý ở lớp khác | Ứng dụng cần tận dụng Oracle RAC/ONS/FAN và UCP features |

HikariCP có thể chạy tốt với Oracle JDBC driver. UCP không tự động nhanh hơn trong mọi workload. Lựa chọn dựa trên nhu cầu HA, topology, cách vận hành, yêu cầu driver và khả năng giám sát.

### Khi nào chọn HikariCP?

HikariCP thường là lựa chọn phù hợp khi:

- Ứng dụng Spring Boot chỉ cần JDBC pooling tiêu chuẩn.
- Không cần UCP-specific FAN/FCF/RLB.
- HA được xử lý bằng service/network/driver/retry ở lớp khác.
- Muốn cấu hình đơn giản và hành vi pool dễ quan sát.
- Không có yêu cầu dùng connection labeling hoặc tính năng riêng của UCP.

### Khi nào cân nhắc UCP?

UCP đáng xem xét khi:

- Ứng dụng chạy với Oracle RAC và cần phản ứng theo FAN.
- Cần FCF để loại bỏ connection đến instance/service đã lỗi.
- Cần RLB theo service metrics.
- Cần connection labeling hoặc connection harvesting.
- Kiến trúc đã chuẩn hóa Oracle UCP và đội vận hành có khả năng theo dõi.

Không chọn UCP chỉ vì database là Oracle. Với database standalone và workload thông thường, HikariCP có thể đáp ứng tốt.

## 11. Pool size: tính theo toàn bộ hệ thống

maximumPoolSize là giới hạn connection tối đa của một pool trong một process ứng dụng. Nếu triển khai nhiều replica, tổng connection tiềm năng là tổng của tất cả pool.

Ví dụ:

| Thành phần | Số lượng | Max pool mỗi instance | Tổng tối đa |
|---|---:|---:|---:|
| API deployment | 4 | 20 | 80 |
| Batch worker | 2 | 8 | 16 |
| Admin/reporting | 1 | 5 | 5 |
| **Tổng** | | | **101** |

Oracle còn phải phục vụ các session khác: DBA, monitoring, scheduler, replication, background service và các ứng dụng khác. Vì vậy, không được tính pool size của một service riêng lẻ mà bỏ qua toàn bộ database.

### Công thức ngân sách connection

\[
\text{Tổng connection tối đa}
= \sum(\text{số instance ứng dụng} \times \text{max pool})
\]

Sau đó so sánh với:

- Khả năng PROCESSES/SESSIONS và giới hạn thực tế của database.
- Tải CPU, I/O và số transaction đồng thời.
- Các ứng dụng khác dùng cùng database.
- Dự phòng cho rolling deployment, autoscaling và failover.
- Các session không qua pool.

Nếu Kubernetes autoscaler có thể tăng từ 4 lên 12 pod, ngân sách phải dùng số pod tối đa có thể chạy, không chỉ replica bình thường.

### Không phải càng nhiều connection càng nhanh

Mỗi Oracle session tiêu tốn tài nguyên. Tăng pool size có thể:

- Tăng số session đồng thời.
- Tăng tranh chấp CPU, buffer cache, latch hoặc lock.
- Tăng số transaction cùng chạy.
- Làm database quá tải và kéo dài thời gian truy vấn.
- Khiến hệ thống chậm hơn dù ứng dụng có nhiều connection hơn.

Pool size nên bắt đầu nhỏ, đo thời gian chờ pool, active/idle count, DB CPU, I/O và query latency rồi điều chỉnh.

### Một pool hay nhiều pool?

Mỗi DataSource thường sở hữu một pool riêng. Nếu ứng dụng tạo một DataSource cho JPA, một DataSource cho JdbcTemplate và một DataSource khác cho batch nhưng cùng kết nối Oracle, tổng số connection là tổng của tất cả pool.

Nếu không cần tách transaction hoặc workload, dùng chung DataSource giúp kiểm soát ngân sách dễ hơn. Nếu cần tách workload, hãy tính tổng pool và giới hạn riêng cho từng loại.

## 12. HikariCP timeout và vòng đời connection

Các timeout có ý nghĩa khác nhau:

| Property | Ý nghĩa |
|---|---|
| connectionTimeout | Thời gian tối đa ứng dụng chờ mượn connection từ pool |
| validationTimeout | Thời gian tối đa cho kiểm tra connection |
| idleTimeout | Thời gian connection idle có thể bị loại bỏ khi pool có connection dư |
| maxLifetime | Tuổi thọ tối đa connection trong pool |
| keepaliveTime | Chu kỳ kiểm tra connection idle để tránh bị network thiết bị loại bỏ |
| Query timeout | Giới hạn thời gian thực thi câu SQL/statement |
| Transaction timeout | Giới hạn thời gian transaction theo cấu hình transaction manager |

Không nhầm connectionTimeout với query timeout. Nếu pool đã cấp connection và SQL chạy 5 phút, connectionTimeout không dừng câu SQL đó.

### maxLifetime

Đặt maxLifetime thấp hơn giới hạn connection lifetime do firewall, load balancer, database profile hoặc network infrastructure áp dụng. HikariCP sẽ loại bỏ connection theo vòng đời pool khi có thể, tránh để thiết bị trung gian cắt kết nối bất ngờ.

Không đặt maxLifetime quá thấp vì pool sẽ tạo/đóng connection liên tục, làm tăng login storm và overhead. Không đặt cao hơn giới hạn hạ tầng nếu connection bị cắt giữa lúc đang dùng.

### keepaliveTime

Keepalive giúp kiểm tra connection idle để giảm nguy cơ bị thiết bị mạng loại bỏ vì không hoạt động. Nó không bảo vệ một connection đang chạy query lâu và không thay thế timeout của network hoặc JDBC driver.

### Leak detection

Ví dụ:

~~~yaml
spring:
  datasource:
    hikari:
      leak-detection-threshold: 60000
~~~

Nếu connection được mượn lâu hơn ngưỡng, HikariCP ghi log stack trace lúc mượn để giúp điều tra. Khi connection được trả lại, log có thể ghi nhận leak đã được thu hồi. Đây là công cụ phát hiện nghi vấn, không phải bằng chứng mọi trường hợp đều là leak; một transaction hợp lệ nhưng chạy lâu cũng có thể vượt ngưỡng.

## 13. Timeout và validation của UCP

UCP có các thuộc tính tương tự nhưng tên và semantics khác HikariCP. Một số property thường dùng:

- initialPoolSize.
- minPoolSize.
- maxPoolSize.
- connectionWaitTimeout.
- inactiveConnectionTimeout.
- abandonedConnectionTimeout.
- validateConnectionOnBorrow.
- sqlForValidateConnection.
- fastConnectionFailoverEnabled.
- ONSConfiguration.

Ví dụ:

~~~java
pool.setInitialPoolSize(3);
pool.setMinPoolSize(3);
pool.setMaxPoolSize(20);
pool.setConnectionWaitTimeout(30);
pool.setValidateConnectionOnBorrow(true);
~~~

Các giá trị thời gian UCP có thể dùng đơn vị giây trong API tương ứng, trong khi nhiều property Hikari dùng millisecond. Đọc Javadoc của version đang dùng trước khi chuyển cấu hình giữa hai pool.

### Abandoned connection timeout

UCP có cơ chế phát hiện connection bị giữ quá lâu. Một số cấu hình có thể thu hồi connection được coi là abandoned. Cần thận trọng vì một transaction hoặc thao tác hợp lệ nhưng lâu có thể bị nhận diện sai nếu timeout đặt quá thấp.

Trước khi bật cơ chế reclaim:

- Đo thời gian transaction dài nhất.
- Xác định cách UCP nhận biết connection abandoned.
- Kiểm tra log và cảnh báo.
- Thử trong môi trường staging.
- Không dùng timeout để che lỗi code không đóng connection.

### Connection validation

Validation on borrow có thể giảm nguy cơ trả về connection chết cho ứng dụng nhưng thêm chi phí kiểm tra khi mượn. Cần cân bằng với FAN/FCF và driver validation. Dùng Connection.isValid() hoặc SQL validation theo khuyến nghị của pool/driver; tránh query validation quá nặng.

## 14. Ranh giới transaction với Spring JPA

Trong Spring, @Transactional thường xác định ranh giới transaction tại service layer:

~~~java
@Service
public class OrderService {

    private final OrderRepository orderRepository;
    private final JdbcTemplate jdbcTemplate;

    public OrderService(
            OrderRepository orderRepository,
            JdbcTemplate jdbcTemplate) {
        this.orderRepository = orderRepository;
        this.jdbcTemplate = jdbcTemplate;
    }

    @Transactional
    public void confirmOrder(Long orderId) {
        Order order = orderRepository.findById(orderId)
            .orElseThrow();

        order.confirm();

        jdbcTemplate.update(
            "insert into order_audit(order_id, event_type) values (?, ?)",
            orderId,
            "CONFIRMED"
        );
    }
}
~~~

Khi JPA và JdbcTemplate dùng cùng DataSource và transaction manager được cấu hình phù hợp, thay đổi entity và câu JDBC có thể nằm trong cùng transaction. Nếu một thao tác ném exception làm transaction rollback theo quy tắc Spring, cả hai phần được rollback cùng nhau.

Nếu mỗi thành phần dùng DataSource khác nhau hoặc transaction manager khác nhau, không mặc định chúng tham gia cùng transaction. Cần cấu hình transaction coordination rõ ràng hoặc thiết kế outbox/message pattern.

### Connection được mượn lúc nào?

JPA có thể trì hoãn việc lấy connection cho đến khi cần thực thi SQL. Thời điểm acquire/release phụ thuộc Hibernate connection handling mode, transaction manager, OSIV và thao tác thực tế.

Không nên suy luận rằng chỉ cần tạo EntityManager là đã giữ một connection vật lý. Ngược lại, cũng không nên giả định connection luôn được trả ngay sau mỗi repository method nếu transaction vẫn đang mở.

Trong một transaction thông thường:

1. Spring bắt đầu transaction.
2. EntityManager/persistence context được gắn với transaction.
3. Khi cần SQL, Hibernate lấy JDBC connection qua DataSource.
4. SQL chạy trên connection trong transaction.
5. Spring commit hoặc rollback.
6. Connection được trả về pool theo cơ chế quản lý tài nguyên.

## 15. EntityManager và connection pool không phải một

EntityManager không phải connection JDBC. Một EntityManager có thể thực hiện nhiều thao tác và Hibernate quản lý việc lấy/trả connection bên dưới.

Ví dụ:

~~~java
@PersistenceContext
private EntityManager entityManager;
~~~

Đây là EntityManager proxy do Spring quản lý theo context. Không tự gọi entityManager.close() trong service khi inject theo cách này.

Đối với JDBC thủ công:

~~~java
try (Connection connection = dataSource.getConnection();
     PreparedStatement statement =
         connection.prepareStatement("select 1 from dual");
     ResultSet resultSet = statement.executeQuery()) {

    if (resultSet.next()) {
        // Use the result.
    }
}
~~~

Với pooled DataSource, connection.close() thường trả connection về pool thay vì đóng physical connection ngay lập tức. try-with-resources vẫn cần thiết để đảm bảo connection được trả lại khi code kết thúc hoặc có exception.

Nếu connection được Spring transaction manager quản lý, hãy để Spring điều phối việc release. Tránh tự đóng connection được lấy qua cơ chế transaction-aware.

## 16. @Transactional và thời gian giữ connection

Transaction dài thường giữ connection lâu hơn, làm pool nhanh bão hòa. Ví dụ không tốt:

~~~java
@Transactional
public void processLargeFile() {
    List<Row> rows = readFileFromRemoteStorage();
    callExternalPaymentApi(rows);
    updateDatabase(rows);
}
~~~

Nếu method đã lấy connection sớm và giữ transaction trong lúc đọc file hoặc gọi API chậm, connection bị giữ dù database không làm việc. Nhiều request cùng lúc có thể làm pool cạn.

Tách công việc:

~~~java
public void processLargeFile() {
    List<Row> rows = readFileFromRemoteStorage();
    paymentClient.validate(rows);
    orderWriter.persist(rows);
}

@Transactional
public void persist(List<Row> rows) {
    // Keep only database work inside this transaction.
}
~~~

Trong ví dụ thực tế, orderWriter nên là bean khác để lời gọi đi qua Spring proxy; gọi method @Transactional nội bộ cùng object có thể không kích hoạt proxy transaction theo cấu hình proxy-based mặc định.

### Gọi API ngoài trong transaction

Không giữ transaction Oracle mở trong lúc chờ HTTP API nếu không có yêu cầu consistency đặc biệt. Một API ngoài có thể timeout hoặc chậm, làm connection và lock bị giữ lâu.

Nếu cần đảm bảo cập nhật database và phát sự kiện:

- Dùng transactional outbox.
- Commit dữ liệu nghiệp vụ và outbox record trong cùng transaction.
- Worker riêng đọc outbox và gửi message/API.
- Consumer xử lý idempotent.

## 17. Open Session in View và pool

Spring Boot có thể bật Open EntityManager in View (OSIV) cho web application tùy cấu hình. OSIV giữ persistence context mở trong suốt request để lazy association có thể được truy cập ở tầng web/view.

OSIV không có nghĩa chắc chắn một JDBC connection vật lý bị giữ từ đầu đến cuối request; việc acquire/release phụ thuộc Hibernate connection handling. Tuy nhiên, truy vấn lazy ở tầng serialization/view có thể tạo SQL ngoài service transaction, kéo dài thời gian sử dụng tài nguyên và làm khó kiểm soát N+1.

Với REST API, thường nên cân nhắc:

~~~yaml
spring:
  jpa:
    open-in-view: false
~~~

Khi tắt OSIV:

- Load dữ liệu cần thiết trong service transaction.
- Dùng fetch join/entity graph hoặc projection phù hợp.
- Chuyển entity thành DTO trước khi rời transaction.
- Không để JSON serializer tự kích hoạt lazy loading.

Đây là quyết định kiến trúc; kiểm tra ứng dụng trước khi tắt nếu code hiện đang phụ thuộc lazy loading ngoài service.

## 18. Pool exhaustion và dấu hiệu nhận biết

Pool exhaustion xảy ra khi tất cả connection đều đang được mượn và request mới phải chờ. Nếu chờ quá connectionTimeout, HikariCP thường ném lỗi timeout lấy connection. UCP có thể báo lỗi chờ connection theo timeout đã cấu hình.

Nguyên nhân thường gặp:

- Pool quá nhỏ so với concurrency thực tế.
- Transaction kéo dài.
- Connection leak hoặc không close JDBC resource.
- Query chậm hoặc lock wait.
- Gọi remote API trong transaction.
- Database chậm hoặc mất kết nối.
- Pool size tăng quá nhanh giữa nhiều replica.
- Có nhiều DataSource/pool hơn dự kiến.

Không tăng max pool ngay khi thấy timeout. Trước hết xem active/idle/pending, thời gian query, transaction duration, database session và số lượng pod.

### Dấu hiệu từ HikariCP

Log có thể cho biết:

- Connection timeout.
- Pool active/idle/total.
- Thread đang chờ connection.
- Leak detection warning.
- Connection bị evict hoặc validation thất bại.

Một pool thường xuyên có active bằng maximum và pending lớn là dấu hiệu bão hòa. Nếu active thấp nhưng request vẫn chậm, nguyên nhân có thể nằm ở database, network hoặc application thread.

### Dấu hiệu từ Oracle

Kiểm tra session:

~~~sql
SELECT username,
       service_name,
       machine,
       program,
       status,
       COUNT(*) AS session_count
  FROM v$session
 WHERE username IS NOT NULL
 GROUP BY username,
          service_name,
          machine,
          program,
          status
 ORDER BY session_count DESC;
~~~

Kiểm tra session theo service/module:

~~~sql
SELECT service_name,
       module,
       action,
       status,
       COUNT(*) AS session_count
  FROM v$session
 WHERE username = 'APP_RUNTIME'
 GROUP BY service_name, module, action, status
 ORDER BY session_count DESC;
~~~

Các view V$ thường cần quyền đọc phù hợp. Trên production, dùng tài khoản monitoring có quyền tối thiểu hoặc view đã được DBA công bố.

## 19. Giám sát pool từ Spring Boot

Spring Boot Actuator có thể cung cấp metrics cho DataSource và HikariCP khi dependency/configuration phù hợp. Với Micrometer, các metric thường có prefix hikaricp và tag theo pool name, chẳng hạn:

- Active connections.
- Idle connections.
- Pending threads.
- Maximum connections.
- Minimum connections.
- Connection usage/acquire time.

Tên metric và cách expose phụ thuộc version Spring Boot/Micrometer. Kiểm tra /actuator/metrics hoặc hệ thống Prometheus scrape thay vì giả định tên metric giống mọi version.

Ví dụ bật endpoint quản trị ở phạm vi được kiểm soát:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics,prometheus
~~~

Không expose endpoint metrics hoặc env/config ra Internet. Bảo vệ Actuator bằng authentication, network policy và allowlist.

### Những gì nên theo dõi

| Metric | Ý nghĩa |
|---|---|
| Active | Connection đang được ứng dụng sử dụng |
| Idle | Connection sẵn sàng được mượn |
| Pending | Thread đang chờ connection |
| Max | Giới hạn pool |
| Acquire time | Thời gian lấy connection |
| Usage time | Thời gian giữ connection |
| Timeout count | Số lần không lấy được connection đúng hạn |

Kết hợp metric pool với database CPU, session count, wait events, SQL latency và HTTP request latency. Chỉ nhìn một metric không đủ xác định bottleneck.

## 20. UCP monitoring và quản lý pool

UCP cung cấp API/management interface và thống kê pool để quan sát:

- Số connection total/available/borrowed.
- Pool size và giới hạn.
- Connection wait.
- Connection validation.
- Connection labeling.
- FCF events và trạng thái HA theo cấu hình.

Có thể lấy pool statistics qua API UCP tương ứng version. Ví dụ khái niệm:

~~~java
int total = pool.getStatistics().getTotalConnectionsCount();
int available = pool.getStatistics().getAvailableConnectionsCount();
int borrowed = pool.getStatistics().getBorrowedConnectionsCount();
~~~

Tên method có thể thay đổi theo UCP release; đối chiếu Javadoc của version đang dùng. Không ghi credential hoặc connection string có secret vào metrics/log.

Nếu dùng FCF, cần quan sát:

- FAN/ONS connectivity.
- Service/instance event.
- Connection bị invalidated/aborted.
- Thời gian pool ổn định sau failover.
- Transaction retry và lỗi ứng dụng.

## 21. Connection labeling và session state

Oracle UCP hỗ trợ connection labeling để phân loại connection theo thuộc tính session. Điều này hữu ích khi các request cần session state khác nhau, ví dụ NLS settings hoặc một số thuộc tính nghiệp vụ.

Pool có thể chọn connection có label phù hợp hoặc gọi callback để cấu hình lại connection khi cần. Tuy nhiên, session state có thể tồn tại sau khi connection được trả về pool.

Nếu ứng dụng thay đổi:

- NLS_DATE_FORMAT.
- CURRENT_SCHEMA.
- CLIENT_IDENTIFIER.
- Module/action.
- Application context.
- Một số session parameter.

cần bảo đảm state được reset hoặc được quản lý qua labeling/callback. Nếu không, request tiếp theo có thể nhận connection mang state từ request trước.

Với HikariCP, không có cơ chế connection labeling UCP tương đương. Ứng dụng cần quản lý session state một cách cẩn thận và reset trong finally/connection lifecycle phù hợp.

Không dùng ALTER SESSION tùy tiện rồi trả connection về pool mà không reset. Nếu cần set module/action, dùng cơ chế set/reset rõ ràng để monitoring không gán nhầm workload.

## 22. Read-only transaction và connection state

@Transactional(readOnly = true) là hint cho transaction manager/provider. Nó không phải cơ chế authorization và không tự bảo đảm mọi câu SQL chỉ đọc. Có thể giúp Hibernate tối ưu flush behavior hoặc truyền read-only hint tùy cấu hình.

Ví dụ:

~~~java
@Transactional(readOnly = true)
public OrderDto findOrder(Long id) {
    return repository.findById(id)
        .map(OrderDto::from)
        .orElseThrow();
}
~~~

Nếu ứng dụng dùng nhiều datasource hoặc read/write service khác nhau, cần cấu hình routing và transaction manager rõ ràng. Không tự chuyển transaction sang read replica chỉ vì annotation readOnly=true nếu chưa có routing policy và consistency plan.

Connection pool có thể tái sử dụng connection sau transaction; session-level state như schema, NLS, isolation hoặc role phải được khôi phục theo thiết kế. Tránh để request thay đổi session state mà không reset.

## 23. Async, scheduler và thread boundary

Spring transaction thường gắn với thread thực thi. Khi method có @Async gọi một tác vụ khác, thread mới không tự kế thừa transaction hoặc JDBC connection của thread ban đầu.

Ví dụ:

~~~java
@Async
public CompletableFuture<Void> processAsync(Long orderId) {
    workerService.process(orderId);
    return CompletableFuture.completedFuture(null);
}

@Transactional
public void process(Long orderId) {
    // This worker thread starts its own transaction.
}
~~~

Transaction của worker cần được bắt đầu ở bean/service được gọi trên thread mới. Không truyền Connection, EntityManager hoặc Hibernate Session từ thread cũ sang thread mới.

Scheduler và batch worker cũng dùng pool connection. Nếu chạy nhiều job song song, phải tính concurrency của scheduler cùng API pool và các pool khác.

## 24. Retry và lỗi kết nối

Khi network hoặc RAC failover xảy ra, connection có thể bị invalid. Pool có thể loại bỏ connection hỏng và cấp connection mới, nhưng transaction đang chạy có thể đã rollback, commit hoặc ở trạng thái không rõ đối với client.

Không retry mù quáng các thao tác ghi:

~~~java
@Retryable
public void chargeCardAndUpdateOrder(...) {
    // A retry may repeat a non-idempotent operation.
}
~~~

Trước khi retry:

- Xác định lỗi xảy ra trước hay sau khi server nhận request.
- Xác định transaction có thể đã commit hay chưa.
- Dùng idempotency key cho thao tác nghiệp vụ có side effect.
- Chỉ retry lỗi transient được xác định rõ.
- Đặt giới hạn số lần và backoff.
- Không retry vô hạn khi database đang outage.

UCP/FCF cải thiện nhận biết connection lỗi trong Oracle HA; nó không thay thế retry policy ở tầng nghiệp vụ.

## 25. Session initialization và connection reset

Ứng dụng có thể cần đặt module/action để Oracle nhận diện workload:

~~~java
try (Connection connection = dataSource.getConnection()) {
    try (CallableStatement statement = connection.prepareCall(
            "begin dbms_application_info.set_module(?, ?); end;")) {
        statement.setString(1, "orders-api");
        statement.setString(2, "confirm-order");
        statement.execute();
    }

    // Execute work using this connection.
}
~~~

Đây là minh họa. Khi connection trả lại pool, module/action có thể vẫn tồn tại trong session nếu không reset. Có thể đặt/reset trong một wrapper/interceptor hoặc dùng cơ chế phù hợp của pool.

DBMS_APPLICATION_INFO giúp DBA theo dõi module/action trong V$SESSION, nhưng không thay thế authorization. Không ghi dữ liệu nhạy cảm hoặc thông tin cá nhân vào module/action.

## 26. Multi-tenancy và nhiều DataSource

Một ứng dụng có thể kết nối nhiều PDB hoặc database:

- OLTP database.
- Reporting database.
- Legacy database.
- Tenant database riêng.

Mỗi DataSource thường có pool riêng. Nếu có 3 DataSource với max pool 20 và 5 pod, tổng số connection tối đa có thể đạt:

\[
3 \times 20 \times 5 = 300
\]

Tạo nhiều pool làm tăng tổng session và độ phức tạp transaction. Nếu cần transaction xuyên hai database, Spring @Transactional với một transaction manager đơn lẻ không tự biến hai DataSource thành một distributed transaction. Cần cấu hình JTA/XA hoặc thiết kế saga/outbox theo yêu cầu consistency.

Không chia sẻ một DataSource bean cho hai database URL khác nhau. Mỗi DataSource phải có pool, credential, health check và transaction configuration phù hợp.

## 27. HikariCP và UCP trong môi trường RAC

Trong RAC, service có thể chạy trên nhiều instance. Client nên dùng service name được quản lý bởi Clusterware. UCP có thể tích hợp FAN/FCF và RLB khi được cấu hình đúng.

HikariCP có thể kết nối đến service RAC bằng JDBC URL bình thường, nhưng pool không có cùng tích hợp UCP-native để xử lý FAN event. Khi failover, HikariCP có thể phát hiện connection hỏng qua validation hoặc lỗi khi ứng dụng sử dụng connection; hành vi và thời gian phục hồi phụ thuộc driver, URL, network timeout và ứng dụng.

### Những yếu tố ảnh hưởng HA

- Service placement và service role.
- SCAN listener/VIP.
- ONS/FAN configuration.
- Oracle JDBC driver version.
- Pool implementation.
- Connection validation.
- TCP connect/read timeout.
- Transaction retry và idempotency.
- Health check của ứng dụng.

Không chỉ bật FCF rồi coi HA đã hoàn tất. Cần diễn tập node failure, service relocation, network partition và database restart trong môi trường thử nghiệm.

## 28. Cấu hình mẫu lựa chọn HikariCP hoặc UCP

### HikariCP đơn giản

~~~yaml
spring:
  datasource:
    url: jdbc:oracle:thin:@//dbhost.example.com:1521/APP_SERVICE
    username: app_runtime
    password: $DB_PASSWORD
    hikari:
      pool-name: orders-hikari
      maximum-pool-size: 16
      minimum-idle: 4
      connection-timeout: 30000
      validation-timeout: 5000
      max-lifetime: 1740000
~~~

### UCP cho Oracle HA

~~~java
PoolDataSource pool = PoolDataSourceFactory.getPoolDataSource();
pool.setConnectionFactoryClassName("oracle.jdbc.pool.OracleDataSource");
pool.setURL("jdbc:oracle:thin:@//rac-scan.example.com:1521/ORDERS_RW");
pool.setUser("app_runtime");
pool.setPassword(secretProvider.getSecret("oracle/app-runtime"));
pool.setInitialPoolSize(4);
pool.setMinPoolSize(4);
pool.setMaxPoolSize(16);
pool.setConnectionWaitTimeout(30);
pool.setValidateConnectionOnBorrow(true);
pool.setFastConnectionFailoverEnabled(true);
pool.setONSConfiguration(onsConfiguration);
~~~

Hai cấu hình này là điểm bắt đầu để so sánh, không phải benchmark. Đo pool wait, connection creation, failover recovery, SQL latency, database load và tổng session trong topology thật.

## 29. Checklist thiết kế pool cho production

- [ ] Xác định số replica/pod tối đa, không chỉ số replica bình thường.
- [ ] Tính tổng connection tối đa từ mọi DataSource và ứng dụng.
- [ ] Chọn HikariCP hay UCP theo nhu cầu thực tế.
- [ ] Dùng Oracle service name và PDB đúng.
- [ ] Quản lý password qua secret manager.
- [ ] Đặt connection timeout khác với query/transaction timeout.
- [ ] Đặt maxLifetime phù hợp network/database.
- [ ] Cấu hình validation/keepalive theo pool và driver.
- [ ] Giới hạn transaction duration và tránh gọi API ngoài trong transaction dài.
- [ ] Dùng cùng DataSource/transaction manager khi cần cùng transaction.
- [ ] Không chia sẻ EntityManager/Connection giữa thread.
- [ ] Đo active, idle, pending, acquire time và usage time.
- [ ] Theo dõi session count, SQL latency và database wait.
- [ ] Nếu dùng UCP FCF, xác nhận FAN/ONS/service/driver tương thích.
- [ ] Diễn tập RAC failover hoặc network failure.
- [ ] Kiểm tra retry/idempotency và trạng thái transaction sau lỗi.

## 30. Những lỗi thường gặp

**Pool quá lớn:** mỗi pod tạo nhiều session, tổng số vượt ngân sách Oracle. Tính theo số replica tối đa và mọi DataSource.

**Tăng pool để chữa query chậm:** nhiều connection hơn có thể làm database quá tải. Xem SQL, lock, I/O và DB CPU trước.

**Nhầm connection timeout với query timeout:** timeout chờ pool không dừng SQL đang chạy. Cấu hình statement/query timeout riêng.

**Giữ transaction trong lúc gọi HTTP:** connection và lock có thể bị giữ lâu. Đưa thao tác ngoài database ra khỏi transaction hoặc dùng outbox.

**Không đóng JDBC resource:** connection bị giữ và pool cạn. Dùng try-with-resources khi tự quản lý JDBC.

**Tự đóng EntityManager của Spring:** có thể phá vỡ lifecycle và transaction. Để Spring quản lý EntityManager inject bằng @PersistenceContext.

**Dùng Hikari nhưng kỳ vọng UCP FCF:** Hikari không tự tích hợp FAN/FCF theo cơ chế UCP. Chọn UCP nếu cần Oracle-specific integration.

**Bật UCP FCF nhưng không có ONS/service phù hợp:** pool không nhận được sự kiện HA như mong đợi. Kiểm tra ONS, FAN, service và driver.

**Đặt abandoned timeout quá thấp:** connection đang chạy transaction hợp lệ có thể bị thu hồi. Đo workload và thử nghiệm trước.

**Dùng @Transactional(readOnly=true) như quyền chỉ đọc:** annotation là hint, không phải security boundary.

**Truyền connection sang @Async:** JDBC connection và EntityManager không thread-safe theo cách này; worker cần transaction và connection riêng.

**Retry thao tác ghi không idempotent:** có thể tạo duplicate khi response mất sau commit. Dùng idempotency key và retry policy.

## 31. Kết luận

HikariCP và Oracle UCP đều quản lý JDBC connection pool, nhưng phục vụ nhu cầu khác nhau. HikariCP phù hợp với ứng dụng Spring Boot/JPA cần pooling JDBC đơn giản. UCP đáng xem xét khi cần tích hợp Oracle-specific như FAN, FCF, RLB, connection labeling hoặc harvesting trong môi trường được hỗ trợ.

Pool quản lý connection vật lý và việc mượn/trả connection; Spring transaction manager quản lý commit/rollback; JPA EntityManager quản lý persistence context. Giữ transaction ngắn, không gọi hệ thống ngoài trong transaction dài, không chia sẻ connection hoặc EntityManager giữa thread và luôn trả JDBC resource về pool.

Pool size phải được tính theo tổng số pod/replica, DataSource và ứng dụng cùng dùng database. Theo dõi active/idle/pending, acquire time, usage time, Oracle session và query latency trước khi tăng pool. Nếu dùng UCP với RAC, xác nhận FAN/ONS/service/driver và diễn tập failover. Không có pool nào thay thế thiết kế transaction, retry, idempotency và capacity planning.
