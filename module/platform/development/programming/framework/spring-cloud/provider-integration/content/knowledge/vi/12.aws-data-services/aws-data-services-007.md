# Kết nối RDS qua JDBC và quản lý pool kết nối

## 1. Bối cảnh và mục tiêu

Trong module **Spring Cloud Provider Integration**, ứng dụng Spring Boot kết nối dịch vụ managed của AWS, Azure và Google Cloud bằng Spring Cloud hoặc SDK tương ứng. Với dữ liệu quan hệ trên AWS, **Amazon Relational Database Service (Amazon RDS)** quản lý phần lớn công việc vận hành database engine như PostgreSQL và MySQL; ứng dụng Java vẫn giao tiếp qua **JDBC** như khi kết nối một máy chủ quan hệ thông thường.

Kết nối thành công không chỉ phụ thuộc JDBC URL. Ứng dụng còn phải cấu hình mạng VPC/security group, TLS, danh tính và secret, vòng đời kết nối, transaction và **connection pool**. Pool quá nhỏ có thể khiến request chờ; pool quá lớn có thể làm cạn `max_connections` của database, nhất là khi hệ thống có nhiều pod/instance. AWS có thể dùng **RDS Proxy** để quản lý và multiplex backend connections, nhưng proxy cũng cần được thiết kế cùng pool phía ứng dụng.

Ví dụ xuyên suốt là dịch vụ đặt chỗ:

- Bảng `reservation` lưu lượt đặt và trạng thái.
- Bảng `property_inventory` giữ số chỗ còn lại.
- Khi đặt chỗ, ứng dụng cập nhật tồn kho và chèn reservation trong cùng transaction SQL.
- Spring Boot dùng `JdbcTemplate`, `DataSource` do HikariCP quản lý, kết nối đến RDS PostgreSQL qua endpoint trong VPC.

Sau bài học, bạn có thể:

1. Chọn đúng RDS endpoint, port, database name, JDBC driver và cấu hình mạng.
2. Cấu hình `spring-boot-starter-jdbc`, `JdbcTemplate` và HikariCP trong Spring Boot.
3. Tính tổng số connection có thể mở từ nhiều instance ứng dụng và chọn pool size có căn cứ.
4. Phân biệt `connectionTimeout`, `maxLifetime`, `idleTimeout`, query timeout và thời gian mở TCP connection.
5. Bảo vệ kết nối bằng TLS, Secrets Manager hoặc IAM database authentication; hiểu vòng đời credential trong pool.
6. Dùng RDS Proxy, xử lý failover và connection reset, theo dõi metric và kiểm thử tích hợp.

> **Phạm vi:** RDS là dịch vụ AWS quản lý database quan hệ; JDBC/HikariCP là thành phần phía ứng dụng Java. Spring Cloud AWS có thể tích hợp với các dịch vụ AWS như Secrets Manager và Parameter Store, nhưng kết nối JDBC tới RDS chủ yếu dùng driver của database, Spring Boot JDBC và cấu hình DataSource. Không cần một "RDS JDBC starter" riêng để dùng JDBC.

## 2. Kiến trúc kết nối từ Spring Boot tới RDS

### 2.1. Luồng kết nối

~~~mermaid
flowchart LR
    A["Spring Boot Service"] --> B["JdbcTemplate / JDBC"]
    B --> C["HikariCP DataSource<br/>pool phía ứng dụng"]
    C --> D["RDS Proxy (tùy chọn)"]
    D --> E["Amazon RDS PostgreSQL/MySQL"]
    C -. "kết nối trực tiếp nếu không có Proxy" .-> E
    F["Secrets Manager / IAM DB Auth"] --> C
    G["VPC + Route + Security Group + TLS"] --- C
    G --- D
    G --- E
~~~

Mỗi tầng giải quyết một trách nhiệm:

- **JDBC driver** chuyển lời gọi JDBC thành giao thức tương ứng với PostgreSQL/MySQL.
- **HikariCP** giữ và tái sử dụng kết nối vật lý, tránh tạo TCP/database session cho từng request.
- **RDS Proxy** (nếu có) nhận các kết nối client và quản lý/multiplex kết nối đến database khi workload cho phép.
- **RDS** lưu dữ liệu và thực thi SQL/transaction.
- **IAM, Secrets Manager và TLS** kiểm soát danh tính, credential và bảo vệ dữ liệu trên đường truyền.
- **VPC/security group** quyết định workload có thể đi đến endpoint/port của RDS hay không.

HikariCP và RDS Proxy nằm ở hai phía của đường kết nối. HikariCP quản lý pool trong từng JVM; RDS Proxy quản lý kết nối phía dịch vụ database. Khi dùng cả hai, vẫn phải tính tổng số kết nối client, kích thước pool, thời gian transaction và giới hạn backend.

### 2.2. Chọn endpoint phù hợp

RDS cung cấp DNS endpoint và port theo database engine. PostgreSQL thường dùng port `5432`, MySQL thường dùng `3306`. JDBC URL có dạng:

~~~text
jdbc:postgresql://<rds-endpoint>:5432/<database-name>
jdbc:mysql://<rds-endpoint>:3306/<database-name>
~~~

Không ghi cứng địa chỉ IP đã resolve từ endpoint. DNS endpoint giúp ứng dụng tiếp tục kết nối đúng tài nguyên sau một số thay đổi hạ tầng hoặc failover; IP của instance có thể thay đổi.

Phân biệt các loại endpoint:

| Endpoint | Công dụng | Điều cần lưu ý |
| --- | --- | --- |
| RDS DB instance endpoint | Kết nối tới một DB instance | Dùng endpoint của instance/primary phù hợp với topology |
| Read replica endpoint | Đọc từ replica cụ thể | Có replication lag; không mặc định phù hợp read-after-write |
| Aurora cluster writer endpoint | Kết nối tới writer hiện tại | Dùng cho ghi và transaction cần writer |
| Aurora reader endpoint | Phân phối kết nối đọc đến reader | Không thay thế writer endpoint; có thể đọc dữ liệu trễ |
| RDS Proxy endpoint | Kết nối tới proxy | Ứng dụng vẫn dùng JDBC driver/SQL theo engine; proxy xử lý kết nối backend |

RDS Multi-AZ DB instance và read replica là hai khái niệm khác nhau: standby Multi-AZ phục vụ availability/failover, không mặc nhiên là endpoint đọc để scale. Với Aurora, writer/reader endpoints thuộc mô hình cluster. Chọn đúng endpoint theo loại RDS/Aurora đã triển khai.

## 3. Chuẩn bị dependency JDBC trong Spring Boot

### 3.1. Maven cho PostgreSQL

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-jdbc</artifactId>
    </dependency>

    <dependency>
        <groupId>org.postgresql</groupId>
        <artifactId>postgresql</artifactId>
        <scope>runtime</scope>
    </dependency>
</dependencies>
~~~

Spring Boot quản lý version tương thích qua dependency management/BOM của dự án. Nếu dùng MySQL, thay driver bằng `com.mysql:mysql-connector-j` ở scope runtime. Không kéo đồng thời hai driver nếu ứng dụng chỉ dùng một engine.

`spring-boot-starter-jdbc` đưa vào Spring JDBC và HikariCP theo cấu hình mặc định của Spring Boot. Khi có một JDBC driver và cấu hình `spring.datasource.*`, Boot có thể tự tạo `DataSource`, sau đó `JdbcTemplate` được auto-configure để dùng DataSource đó.

Để chạy integration test trong mục 12, dự án thường cần thêm `spring-boot-starter-test`, `org.testcontainers:postgresql` và `org.testcontainers:junit-jupiter` ở scope test. Quản lý version Testcontainers đồng bộ bằng BOM hoặc dependency management của dự án.

### 3.2. Cấu hình DataSource qua environment

Ví dụ PostgreSQL RDS:

~~~yaml
# application.yml
spring:
  datasource:
    url: jdbc:postgresql://${DB_HOST}:${DB_PORT:5432}/${DB_NAME}
    username: ${DB_USERNAME}
    password: ${DB_PASSWORD}
    hikari:
      pool-name: ReservationPool
      maximum-pool-size: 12
      minimum-idle: 2
      connection-timeout: 3000
      validation-timeout: 1000
      idle-timeout: 600000
      max-lifetime: 1500000
      keepalive-time: 120000
~~~

Các giá trị pool trên **chỉ là điểm khởi đầu để học**, không phải sizing production áp dụng cho mọi RDS instance. Cần thay bằng giá trị đo được theo số replica, `max_connections`, thời gian query và SLO.

Không lưu mật khẩu thật trong file cấu hình được commit vào Git. `DB_HOST`, `DB_NAME`, `DB_USERNAME`, `DB_PASSWORD` nên được cung cấp bởi cấu hình triển khai/secret injection; ở mục 8 sẽ xem cách dùng Secrets Manager và IAM database authentication.

### 3.3. Bật TLS và xác minh server certificate

Kết nối production nên mã hóa TLS và xác minh certificate của server. Với PostgreSQL JDBC, có thể cấu hình URL dạng:

~~~yaml
spring:
  datasource:
    url: jdbc:postgresql://${DB_HOST}:5432/${DB_NAME}?sslmode=verify-full&sslrootcert=/etc/ssl/certs/global-bundle.pem
~~~

Đường dẫn CA bundle là ví dụ; đưa CA bundle được AWS công bố vào image/runtime theo quy trình cập nhật certificate. `verify-full` vừa kiểm tra chuỗi tin cậy vừa kiểm tra hostname khớp certificate. Tránh `sslmode=disable` ở production và tránh chế độ chỉ mã hóa nhưng không xác minh danh tính server khi yêu cầu bảo mật cần xác minh đầy đủ.

Với MySQL Connector/J, tham số thường dùng là `sslMode=VERIFY_IDENTITY`; xác nhận cấu hình trust store/CA theo version driver và engine. Cú pháp PostgreSQL và MySQL không giống nhau, không sao chép nguyên URL của driver này sang driver kia.

## 4. Mạng AWS: VPC, subnet và security group

### 4.1. Đường mạng phải thông trước khi debug JDBC

Một kết nối RDS private thường cần:

1. RDS nằm trong DB subnet group thuộc các subnet/VPC đã chọn.
2. EC2/ECS/EKS hoặc workload Spring Boot có route tới subnet của RDS, thường trong cùng VPC hoặc qua kết nối mạng đã cấu hình.
3. Security group của RDS cho phép **inbound** TCP từ security group của ứng dụng trên port database, ví dụ `5432`.
4. Security group của ứng dụng cho phép egress phù hợp; network ACL/route table/DNS không chặn luồng.
5. Ứng dụng resolve được DNS endpoint và kết nối tới đúng hostname/port.
6. TLS trust chain và hostname verification hợp lệ.

Không mở database port tới `0.0.0.0/0` chỉ để sửa lỗi kết nối. Nên dùng private subnets và tham chiếu **security group nguồn của workload** trong rule inbound của RDS. `Publicly accessible` chỉ bật khi có yêu cầu kiến trúc rõ ràng và biện pháp kiểm soát mạng phù hợp.

### 4.2. Phân biệt lỗi mạng và lỗi xác thực

| Triệu chứng | Nhóm nguyên nhân | Kiểm tra |
| --- | --- | --- |
| DNS lookup thất bại | Endpoint sai, DNS/VPC resolver hoặc cấu hình hostname | Resolve endpoint từ đúng container/pod/EC2 |
| Connection timeout | Route, SG, NACL, port, endpoint hoặc RDS chưa sẵn sàng | Kiểm tra TCP từ workload trong cùng network context |
| Connection refused | Sai port, listener/instance chưa sẵn sàng hoặc proxy endpoint không đúng | Engine, port, trạng thái DB/proxy |
| TLS handshake/certificate error | CA bundle, hostname, TLS version hoặc driver | CA bundle, `sslmode`, server certificate, driver version |
| Authentication failed | Username/password, secret rotation hoặc IAM DB auth | DB user, credential hiện tại, IAM auth config |
| Permission denied khi chạy SQL | DB user thiếu quyền schema/table/sequence | Grant trong database; IAM permission không tự cấp SQL privilege |
| Hikari pool timeout | Pool hết connection, connection bị giữ lâu hoặc DB không cấp thêm | Hikari active/idle/pending, query/transaction duration |

Kiểm tra từ **đúng workload** vì laptop developer có thể vào RDS qua VPN/bastion trong khi pod production không có route hoặc SG phù hợp. Không đưa password lên command line/log để kiểm tra.

## 5. HikariCP: pool kết nối phía ứng dụng

### 5.1. Vì sao cần connection pool?

Tạo một kết nối JDBC mới cho mỗi HTTP request có chi phí TCP handshake, TLS handshake, xác thực và thiết lập session. HikariCP duy trì một nhóm kết nối và cho các request mượn/trả lại:

~~~mermaid
sequenceDiagram
    participant R1 as HTTP Request A
    participant R2 as HTTP Request B
    participant H as HikariCP
    participant DB as RDS PostgreSQL
    R1->>H: borrow connection
    H->>DB: dùng connection đã có
    R2->>H: borrow connection khác / chờ
    H-->>R1: trả connection
    R2->>H: nhận connection vừa rảnh
    H-->>R2: trả connection
~~~

`DataSource` là abstraction JDBC; HikariCP triển khai pool cho DataSource. `JdbcTemplate` lấy connection từ DataSource, thực thi SQL, đóng logical connection khi xong; HikariCP đưa connection vật lý trở lại pool thay vì đóng socket ngay.

Pool có giới hạn: nếu tất cả connection đang được giữ bởi query/transaction, request mới phải chờ đến `connectionTimeout`. Nếu chờ quá lâu, Hikari ném lỗi lấy connection; tăng pool chỉ hợp lý khi database còn capacity và workload cần nhiều concurrent DB operations.

### 5.2. Ý nghĩa các thông số chính

| HikariCP property | Đơn vị | Tác dụng | Sai lầm thường gặp |
| --- | --- | --- | --- |
| `maximum-pool-size` | số connection | Tổng số connection tối đa trong pool, gồm idle và in-use | Tăng lớn mà không tính tổng replica và giới hạn DB |
| `minimum-idle` | số connection | Mức idle pool cố duy trì | Đặt bằng max trong mọi môi trường làm giữ nhiều connection nhàn rỗi |
| `connection-timeout` | ms | Thời gian caller chờ lấy connection từ pool | Nhầm với query timeout hoặc timeout mở socket |
| `validation-timeout` | ms | Thời gian tối đa kiểm tra connection hợp lệ | Đặt lớn hơn/equal connectionTimeout |
| `idle-timeout` | ms | Thu hồi connection idle khi pool có thể co lại | Không có tác dụng co pool nếu `minimumIdle` bằng `maximumPoolSize` |
| `max-lifetime` | ms | Tuổi thọ tối đa của connection trong pool | Đặt dài hơn giới hạn connection phía database/proxy/network |
| `keepalive-time` | ms | Kiểm tra/giữ sống connection idle theo chu kỳ | Đặt quá ngắn gây traffic không cần thiết; phải nhỏ hơn maxLifetime |
| `leak-detection-threshold` | ms | Log cảnh báo connection bị giữ lâu bất thường | Tưởng rằng Hikari tự giải phóng connection bị leak |

Một số nguyên tắc:

- `connectionTimeout` là thời gian chờ **một connection có sẵn**, không phải thời gian SQL được phép chạy.
- `maxLifetime` nên thấp hơn giới hạn tuổi thọ/idle connection của tầng hạ tầng liên quan để pool chủ động thay connection trước khi server/network đóng. Hikari không cưỡng bức đóng connection đang được ứng dụng mượn; connection được loại bỏ khi trả lại.
- `idleTimeout` chỉ có ý nghĩa khi pool có thể co dưới `maximumPoolSize`, thường khi `minimumIdle` thấp hơn max.
- `keepaliveTime` áp dụng với connection idle, không thay thế query timeout hay TCP keepalive của hệ điều hành.
- Với JDBC4 driver có `Connection.isValid()`, thường không cần cấu hình `connectionTestQuery` thủ công.
- `leakDetectionThreshold` là công cụ chẩn đoán, không phải cơ chế thu hồi connection đang bị giữ.

### 5.3. Không nhầm các loại timeout

| Timeout | Tầng | Ý nghĩa |
| --- | --- | --- |
| Hikari `connectionTimeout` | Pool | Chờ lấy connection từ pool |
| JDBC driver `connectTimeout` | Driver/network | Chờ mở kết nối TCP/DB session |
| JDBC `socketTimeout` / network timeout | Driver/network | Giới hạn thời gian chờ dữ liệu trên socket; khi hết có thể làm hỏng connection |
| JDBC `Statement.setQueryTimeout()` / Spring query timeout | SQL execution | Giới hạn thời gian thực thi statement theo API/driver |
| Spring transaction timeout | Transaction | Giới hạn thời gian transaction theo cấu hình Spring/transaction manager |
| HTTP request timeout | API | Giới hạn tổng thời gian request từ góc nhìn caller |

Không nên đặt mọi timeout cùng một giá trị. Thiết kế theo thứ tự hợp lý: deadline HTTP đủ bao phủ các bước nghiệp vụ, thời gian chờ pool nhỏ hơn deadline còn lại, query/transaction có timeout phù hợp, còn driver connect/socket timeout ngăn chờ mạng vô hạn. Timeout của một lớp không tự hủy mọi công việc ở lớp khác.

## 6. Chọn pool size từ tổng tải, không đoán theo một JVM

### 6.1. Tính tổng connection tiềm năng

Mỗi instance Spring Boot có **pool riêng**. Nếu chạy nhiều pod/replica, tổng connection có thể tăng tuyến tính:

~~~text
Tổng connection tối đa từ ứng dụng
  = số replica × maximumPoolSize
    + pool của worker/background
    + connection từ migration/admin/monitoring
~~~

Ví dụ:

| Thành phần | Số instance | Max pool mỗi instance | Connection tối đa |
| --- | ---: | ---: | ---: |
| API Spring Boot | 4 | 12 | 48 |
| Worker | 2 | 4 | 8 |
| Migration/admin/monitoring (dự phòng) | — | — | 10 |
| **Tổng ước tính** | | | **66** |

Nếu engine chỉ còn khả năng phục vụ 60 connection cho workload ứng dụng sau khi trừ reserved/system connections, cấu hình này không an toàn. Phải giảm pool, tăng capacity phù hợp, đưa proxy vào kiến trúc hoặc thay đổi concurrency. Không dùng `max_connections` như toàn bộ ngân sách vì DB còn cần connection cho quản trị, monitoring và failover.

### 6.2. Pool lớn không đồng nghĩa throughput cao

Một DB instance có giới hạn CPU, memory, I/O, lock và khả năng chạy query đồng thời. Tăng pool từ 12 lên 100 có thể:

- Tăng số session và memory DB tiêu thụ.
- Làm nhiều query tranh CPU/I/O/lock cùng lúc.
- Tăng queue, context switching và tail latency.
- Làm một đợt tải ngắn tạo ra lượng kết nối khó kiểm soát.

Pool size nên được chọn bằng benchmark với workload thực, quan sát thời gian query, số connection active/idle/pending và DB CPU/memory/IOPS. Một pool nhỏ nhưng query ngắn, index tốt có thể xử lý nhiều request hơn pool lớn với transaction dài.

### 6.3. Connection phải được trả sớm

Các nguyên nhân phổ biến khiến pool cạn:

- Quên đóng `Connection`, `Statement` hoặc `ResultSet` khi không dùng Spring abstraction.
- Mở transaction rồi gọi API HTTP/S3/SQS hoặc chờ người dùng, giữ connection trong lúc không chạy SQL.
- Query chậm, thiếu index hoặc lock chờ lâu.
- Stream/ResultSet được tiêu thụ chậm ở tầng web khiến connection bị giữ.
- Dùng `@Async` hoặc thread mới nhưng mang transaction/context không đúng cách.
- Một code path bị exception nhưng không đóng tài nguyên đúng.

`JdbcTemplate` và `@Transactional` giúp quản lý lifecycle, nhưng transaction phải ngắn. Không truyền JDBC `Connection` ra khỏi repository để giữ qua nhiều tầng hoặc lưu vào field dùng chung.

## 7. RDS Proxy và ứng dụng có nhiều replica

### 7.1. Proxy giải quyết điều gì?

Amazon RDS Proxy nằm giữa ứng dụng và RDS/Aurora. Proxy duy trì các kết nối backend đến database và có thể **multiplex** nhiều client sessions lên một số backend connections khi session state cho phép. Nó giúp giảm áp lực mở/đóng kết nối, hỗ trợ khả năng phục hồi trong một số tình huống failover và quản lý backend connection lifecycle.

RDS Proxy hữu ích khi:

- Ứng dụng serverless hoặc workload scale nhanh tạo nhiều kết nối đồng thời.
- Nhiều replica có pool client riêng và database có giới hạn connection.
- Muốn tập trung một số cấu hình xác thực/secret và cải thiện khả năng phục hồi kết nối.

Proxy không phải phép màu:

- Ứng dụng vẫn cần pool client hợp lý; không nên đặt Hikari max vô hạn.
- Không loại bỏ giới hạn CPU, I/O, lock hay query chậm của database.
- Transaction đang chạy thường giữ backend connection trong thời gian transaction.
- Một số session state hoặc tính năng giữ trạng thái có thể làm **connection pinning**, giảm khả năng multiplex. Đối chiếu tài liệu RDS Proxy cho engine/driver cụ thể.
- Proxy có chi phí riêng và giới hạn client/backend connection cần theo dõi.

### 7.2. Kết nối HikariCP qua RDS Proxy

Ứng dụng thay host trong JDBC URL bằng **RDS Proxy endpoint**; driver và database name vẫn theo engine:

~~~yaml
spring:
  datasource:
    url: jdbc:postgresql://${RDS_PROXY_ENDPOINT}:5432/${DB_NAME}?sslmode=verify-full&sslrootcert=/etc/ssl/certs/global-bundle.pem
    username: ${DB_USERNAME}
    password: ${DB_PASSWORD}
    hikari:
      pool-name: ReservationViaProxy
      maximum-pool-size: 8
      minimum-idle: 1
      connection-timeout: 3000
      validation-timeout: 1000
      max-lifetime: 1500000
~~~

Các con số là ví dụ; sizing dựa trên số replica và metric của proxy/database. Dù có proxy, `maximum-pool-size` vẫn giới hạn số connection từ **mỗi JVM** tới proxy. Proxy quản lý kết nối backend, không tự thay thế HikariCP trong ứng dụng.

### 7.3. Session pinning và transaction

RDS Proxy có thể cần giữ một client session gắn với backend connection khi phát hiện session state hoặc thao tác khiến việc multiplex không an toàn. Các transaction dài, thay đổi session state, temporary objects hoặc một số tính năng theo engine có thể ảnh hưởng khả năng tái sử dụng backend. Tác động chính xác phụ thuộc engine, driver và tính năng; kiểm tra tài liệu proxy và metric thay vì suy luận rằng mọi câu SQL đều multiplex.

Giữ transaction ngắn, tránh gọi hệ thống ngoài khi đang giữ transaction và hạn chế session state không cần thiết. Theo dõi `DatabaseConnections`, `ClientConnections`, `DatabaseConnectionsBorrowLatency` và các metric proxy được công bố cho engine tương ứng.

## 8. Danh tính, password rotation và IAM database authentication

### 8.1. Secrets Manager cho database credentials

Một database user/password có thể được lưu trong **AWS Secrets Manager**, sau đó runtime đưa secret vào ứng dụng qua secret injection hoặc integration phù hợp. Một số cách triển khai:

- ECS task definition tham chiếu secret để đưa giá trị vào container environment.
- Kubernetes External Secrets/CSI hoặc cơ chế đồng bộ secret đã được tổ chức phê duyệt.
- AWSpring integration với Secrets Manager/Parameter Store theo đúng phiên bản và property hỗ trợ.
- Ứng dụng dùng AWS SDK lấy secret qua IAM role, có cache/refresh và kiểm soát vòng đời.

Không ghi secret vào Git, Docker image, log hoặc exception message. Chỉ cấp role quyền đọc secret cần thiết; tách secret theo môi trường và database user theo least privilege.

**Rotation có ảnh hưởng tới pool:** HikariCP không tự biết password trong Secrets Manager vừa đổi. Những connection đã xác thực có thể tiếp tục hoạt động, nhưng connection mới phải dùng credential mới. Nếu ứng dụng tiếp tục cung cấp password cũ, pool có thể cạn dần khi cần mở connection thay thế. Cần một cơ chế refresh credential và thay/evict connection an toàn, hoặc dùng RDS Proxy với mô hình quản lý secret phù hợp.

### 8.2. IAM database authentication

Một số engine/phiên bản RDS và Aurora hỗ trợ IAM database authentication. Thay vì lưu password DB dài hạn cho client, ứng dụng tạo **authentication token** bằng AWS SDK và dùng token làm password khi thiết lập kết nối JDBC. Token có thời hạn ngắn (**15 phút**), được ký theo Region/hostname/port/database user và phải dùng kết nối TLS.

IAM DB authentication cần cấu hình ở cả hai phía:

1. Bật tính năng IAM database authentication cho DB/cluster nếu engine hỗ trợ.
2. Tạo DB user và cấp quyền database cần thiết; ví dụ PostgreSQL cần cấu hình role hỗ trợ IAM auth theo tài liệu engine.
3. Cấp IAM permission `rds-db:connect` trên đúng DB resource ID và DB username ARN.
4. Ứng dụng có credentials AWS qua role/provider chain để ký token.
5. JDBC connection dùng token khi mở physical connection và xác minh TLS theo hướng dẫn AWS.

Ví dụ khái niệm tạo token bằng AWS SDK v2:

Dependency AWS SDK v2 tương ứng (quản lý version bằng AWS SDK BOM):

~~~xml
<dependency>
    <groupId>software.amazon.awssdk</groupId>
    <artifactId>rds</artifactId>
</dependency>
~~~

~~~java
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.rds.RdsUtilities;
import software.amazon.awssdk.services.rds.model.GenerateAuthenticationTokenRequest;

RdsUtilities utilities = RdsUtilities.builder()
        .region(Region.AP_SOUTHEAST_1)
        .build();

String token = utilities.generateAuthenticationToken(
        GenerateAuthenticationTokenRequest.builder()
                .hostname(rdsEndpoint)
                .port(5432)
                .username(databaseUser)
                .build());
~~~

Đoạn code minh họa API tạo token; cần thêm AWS SDK v2 RDS utilities dependency tương ứng và lấy endpoint/user từ cấu hình an toàn. Token chỉ dùng cho **quá trình xác thực khi mở connection**; connection đã xác thực không bị ngắt chỉ vì token hết hạn. Tuy nhiên, connection mới do Hikari mở sau đó phải được cấp token mới.

Vì HikariCP thông thường nhận một password tĩnh từ cấu hình, không nên đưa token IAM vừa tạo một lần vào `spring.datasource.password` rồi để pool chạy mãi. Cần một DataSource/credential provider tạo token mới cho mỗi lần physical connection được mở, hoặc dùng RDS Proxy với mô hình IAM/Secrets Manager được cấu hình phù hợp. Kiểm tra hướng dẫn engine và driver trước khi triển khai.

### 8.3. Phân biệt IAM permission và SQL privilege

IAM `rds-db:connect` cho phép danh tính AWS **đăng nhập** bằng IAM database authentication vào DB user tương ứng. Nó không tự cấp quyền `SELECT`, `INSERT`, `UPDATE`, `DELETE` trên schema/table. Quyền SQL vẫn phải được cấp trong PostgreSQL/MySQL bằng cơ chế của engine. Ngược lại, password DB hợp lệ không giúp workload vượt qua security group/VPC hay TLS verification.

## 9. Transaction JDBC trong Spring Boot

### 9.1. `JdbcTemplate` và `@Transactional`

`JdbcTemplate` dùng DataSource để mượn connection; Spring transaction manager quản lý connection trong phạm vi transaction. Ví dụ repository:

~~~java
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class ReservationJdbcRepository {
    private final JdbcTemplate jdbc;

    public ReservationJdbcRepository(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public int reserveInventory(
            String tenantId, String propertyId, int quantity) {
        return jdbc.update("""
                UPDATE property_inventory
                   SET available = available - ?
                 WHERE tenant_id = ?
                   AND property_id = ?
                   AND available >= ?
                """,
                quantity, tenantId, propertyId, quantity);
    }

    public int insertReservation(
            String tenantId, String reservationId,
            String propertyId, int quantity) {
        return jdbc.update("""
                INSERT INTO reservation
                    (tenant_id, reservation_id, property_id, guest_count, state)
                VALUES (?, ?, ?, ?, 'CONFIRMED')
                """,
                tenantId, reservationId, propertyId, quantity);
    }

    public int countByReservationId(String tenantId, String reservationId) {
        return jdbc.queryForObject("""
                SELECT COUNT(*)
                  FROM reservation
                 WHERE tenant_id = ? AND reservation_id = ?
                """,
                Integer.class, tenantId, reservationId);
    }

    public int availableForProperty(String tenantId, String propertyId) {
        return jdbc.queryForObject("""
                SELECT available
                  FROM property_inventory
                 WHERE tenant_id = ? AND property_id = ?
                """,
                Integer.class, tenantId, propertyId);
    }
}
~~~

Ví dụ service:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class ReservationService {
    private final ReservationJdbcRepository repository;

    public ReservationService(ReservationJdbcRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public void book(
            String tenantId, String reservationId,
            String propertyId, int guestCount) {
        int changed = repository.reserveInventory(
                tenantId, propertyId, guestCount);

        if (changed != 1) {
            throw new IllegalStateException(
                    "Không đủ chỗ hoặc không tìm thấy inventory");
        }

        repository.insertReservation(
                tenantId, reservationId, propertyId, guestCount);
    }
}
~~~

Nếu insert thất bại (ví dụ unique constraint của reservation ID), runtime exception trong ví dụ làm Spring rollback transaction theo mặc định. Cả hai SQL statements phải chạy qua **cùng DataSource/transaction manager** và cùng database để cùng transaction. Dùng parameter placeholder `?` để truyền giá trị, không nối chuỗi người dùng vào SQL.

Đây là transaction relational database thực sự, khác transaction DynamoDB. Nếu service còn gọi S3, SQS hoặc HTTP API trong phương thức này, các hệ thống ngoài không tự rollback cùng transaction JDBC. Cần outbox/saga/compensation hoặc một workflow rõ ràng.

### 9.2. Không giữ connection khi gọi hệ thống ngoài

Không nên:

~~~text
@Transactional
  UPDATE inventory
  gọi HTTP tới payment provider (chờ 3 giây)
  INSERT reservation
commit
~~~

Trong thời gian chờ payment, connection và transaction DB bị giữ, có thể khóa row lâu và làm Hikari pool cạn. Tốt hơn là thiết kế transaction ngắn để ghi trạng thái/intent, gọi hệ thống ngoài sau khi commit qua workflow/outbox, rồi cập nhật trạng thái theo kết quả và idempotency.

`@Transactional` mặc định thường rollback với unchecked exception; nếu cần rollback cho checked exception, khai báo `rollbackFor` theo yêu cầu. Cũng cần hiểu self-invocation/proxy semantics của Spring: gọi một method transactional khác trong cùng object có thể không đi qua proxy như mong đợi.

## 10. Read replica, failover và vòng đời connection

### 10.1. Read/write routing

Với RDS read replicas hoặc Aurora reader endpoint, workload có thể tách đọc/ghi:

- **Write:** writer/primary endpoint.
- **Read-only có thể chấp nhận lag:** reader endpoint/replica.
- **Read-after-write hoặc transaction nghiệp vụ:** đọc writer trong cùng transaction hoặc theo guarantee phù hợp.

`@Transactional(readOnly = true)` không tự động chuyển JDBC connection sang read replica. Nếu muốn routing, cần cấu hình DataSource/transaction routing rõ ràng, đảm bảo transaction bắt đầu sau khi chọn đúng datasource và không gửi write vào replica.

Replication lag khiến đọc trên replica có thể chưa thấy dữ liệu vừa ghi trên writer. Không dùng replica để kiểm tra tức thời trạng thái tồn kho hoặc quyền sở hữu vừa thay đổi nếu nghiệp vụ đòi hỏi dữ liệu mới nhất.

### 10.2. RDS failover và connection cũ

Khi RDS failover hoặc DB restart/maintenance:

- TCP connections hiện hữu có thể bị đóng hoặc trở nên stale.
- Query/transaction đang chạy có thể thất bại; transaction chưa commit cần được xử lý lại theo logic idempotent.
- DNS endpoint có thể trỏ tới tài nguyên mới, nhưng JVM/driver/network cache và pool có thể vẫn giữ connection cũ một thời gian.
- Hikari sẽ loại bỏ connection lỗi khi được phát hiện; `maxLifetime`, validation và retry ở tầng ứng dụng giúp pool tái tạo kết nối.
- RDS Proxy có thể cải thiện khả năng phục hồi kết nối, nhưng không bảo đảm transaction đang chạy không thất bại.

Không cache IP endpoint lâu dài và không giả định một lần failover luôn trong suốt với mọi request. AWS Advanced JDBC Wrapper/driver hỗ trợ failover có thể là lựa chọn cho một số engine/topology; đánh giá tương thích, tính năng và version trước khi dùng.

### 10.3. Retry transaction JDBC phải an toàn

Nếu mất kết nối trong lúc commit, client có thể không biết transaction đã commit hay chưa. Retry toàn bộ nghiệp vụ với một reservation ID mới có thể tạo booking trùng hoặc trừ tồn kho hai lần. Dùng unique constraint/idempotency key, đọc đối soát theo business key và chỉ retry transaction khi biết cách xác định kết quả. Không tự retry mọi `SQLException` giống nhau; phân biệt deadlock, serialization failure, connection reset, constraint violation và lỗi dữ liệu.

## 11. Theo dõi pool và RDS

### 11.1. Metric HikariCP

Spring Boot Actuator/Micrometer có thể công bố metric Hikari tùy dependency và cấu hình:

| Metric (tên có thể khác theo registry) | Ý nghĩa | Dấu hiệu cần điều tra |
| --- | --- | --- |
| `hikaricp.connections.active` | Connection đang được mượn | Gần max trong thời gian dài |
| `hikaricp.connections.idle` | Connection đang rảnh | Luôn bằng 0 cùng pending cao |
| `hikaricp.connections.pending` | Số caller đang chờ connection | Tăng liên tục hoặc vượt ngưỡng |
| `hikaricp.connections.max` | Pool capacity | So sánh với số replica và DB budget |
| `hikaricp.connections.acquire` / acquisition time | Thời gian lấy connection | p95/p99 tăng bất thường |
| `hikaricp.connections.timeout` | Số lần chờ pool quá hạn | Cần tìm query chậm, leak hoặc pool thiếu |

Tên metric cụ thể phụ thuộc Spring Boot, Micrometer và registry. Không log URL/password/secret trong dashboard. Có thể bật Actuator health/readiness để kiểm tra DataSource, nhưng tránh biến liveness probe thành truy vấn database quá thường xuyên gây tải phụ.

### 11.2. Metric Amazon RDS và RDS Proxy

Theo dõi các metric CloudWatch liên quan:

- `DatabaseConnections`, `CPUUtilization`, `FreeableMemory`, `FreeStorageSpace`, read/write latency và IOPS.
- Deadlocks/locks, query performance, slow query log/Performance Insights hoặc công cụ quan sát tương ứng engine/phiên bản.
- RDS Proxy: client connections, database connections, borrow latency, số connection bị từ chối và metric pinning/target health nếu được công bố.
- Sự kiện RDS maintenance, failover, reboot và trạng thái DB/Proxy.

Một pool timeout không tự động có nghĩa DB thiếu connection. Có thể query đang giữ connection lâu, lock contention, transaction chờ external API hoặc network bị gián đoạn. Đối chiếu metric Hikari và RDS theo cùng mốc thời gian.

## 12. Kiểm thử kết nối và pool

### 12.1. Test với PostgreSQL Testcontainers

Một integration test với PostgreSQL container xác minh JDBC driver, schema, transaction và repository SQL:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

@SpringBootTest
@Testcontainers
class ReservationJdbcIT {
    @Container
    static PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16-alpine")
                    .withDatabaseName("reservationdb")
                    .withUsername("test")
                    .withPassword("test");

    @DynamicPropertySource
    static void datasourceProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", postgres::getJdbcUrl);
        registry.add("spring.datasource.username", postgres::getUsername);
        registry.add("spring.datasource.password", postgres::getPassword);
    }

    @Autowired ReservationService service;
    @Autowired ReservationJdbcRepository repository;

    @Test
    void bookingUpdatesInventoryAndCreatesReservation() {
        // Fixture schema/data phải được tạo bằng migration hoặc SQL test;
        // seed inventory tenant-it/house-it với available = 3.
        service.book("tenant-it", "res-it-1", "house-it", 1);

        assertEquals(1, repository.countByReservationId("tenant-it", "res-it-1"));
        assertEquals(2, repository.availableForProperty("tenant-it", "house-it"));
    }
}
~~~

Ví dụ yêu cầu có schema/fixture được tạo bằng Flyway/Liquibase hoặc SQL test; fixture phải seed inventory với `available = 3` trước khi gọi service. Đây là cấu trúc test để minh họa, không phải class đã chạy trong dự án. Với test transaction, nên kiểm tra **cả reservation lẫn inventory**, và thêm case insert thất bại để xác minh inventory rollback.

### 12.2. Kiểm thử Hikari pool

Các tình huống nên kiểm tra:

1. Pool được tạo đúng max/min và không vượt DB connection budget khi scale replica.
2. Query chậm/transaction giữ connection làm `pending` tăng; timeout được trả trong giới hạn API.
3. Exception trong transaction rollback và connection được trả lại pool.
4. DB restart/failover khiến connection lỗi; pool tạo connection mới sau khi endpoint sẵn sàng.
5. Password được rotation: connection mới dùng credential hiện tại, connection cũ được retire có kiểm soát.
6. TLS hostname/CA verification thất bại khi cấu hình sai, thay vì silently fallback sang plaintext.
7. Read replica trả dữ liệu trễ được xử lý theo contract, không dùng cho read-after-write bắt buộc.

### 12.3. Giới hạn của local container test

PostgreSQL Testcontainers kiểm tra logic JDBC/PostgreSQL, nhưng **không mô phỏng đầy đủ** RDS IAM authentication, Secrets Manager rotation, VPC security group, RDS Proxy multiplexing, Multi-AZ failover hay CloudWatch. Các tính năng AWS-specific cần integration test trên **RDS staging** với quota và ngân sách có kiểm soát.

## 13. Lỗi thường gặp và cách chẩn đoán

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| `Connection timed out` | VPC route, security group, NACL, port, DNS | Kiểm tra từ đúng pod/EC2, RDS SG inbound và endpoint |
| `password authentication failed` | Secret cũ, username/database sai, rotation chưa cập nhật | Kiểm tra secret version/current user và cơ chế refresh |
| `PKIX path building failed` / SSL error | CA bundle hoặc trust store không đúng | Cập nhật RDS CA bundle, bật hostname verification |
| `Connection is not available, request timed out` | Hikari pool cạn hoặc connection không trả về | Xem active/idle/pending, transaction/query duration, leak |
| `too many connections` | Tổng pool các replica vượt budget DB hoặc có client khác | Tính lại tổng pool, cân nhắc RDS Proxy, giảm replica/pool |
| Query chậm nhưng pool còn connection | SQL/index/lock/I/O bottleneck | Phân tích query plan, lock, Performance Insights và metric RDS |
| Sau failover request lỗi | TCP connection cũ bị đóng, transaction đang chạy thất bại | Để pool thay connection, xử lý retry idempotent, kiểm tra DNS |
| Proxy borrow latency tăng | Thiếu backend connection, session pinning hoặc DB quá tải | Theo dõi metric proxy, rút ngắn transaction, kiểm tra session state |
| App start thành công nhưng query lỗi | JDBC URL/driver/DB/schema/SQL privilege chưa đúng | Kiểm tra connection thật và quyền SQL user |

## 14. Bài tập tự luyện

1. Cấu hình Spring Boot kết nối RDS PostgreSQL bằng JDBC URL, environment variables và TLS `verify-full`; xác nhận kết nối từ workload trong VPC.
2. Chạy bốn replica, mỗi replica có Hikari `maximum-pool-size=20`. Tính số connection tiềm năng và đề xuất pool phù hợp với `max_connections` thực của DB, có dự phòng cho migration/admin.
3. Tạo endpoint đặt chỗ dùng `@Transactional`: cập nhật inventory với điều kiện `available >= quantity`, sau đó insert reservation; thử unique constraint fail và xác minh rollback.
4. Giảm `maximum-pool-size`, tạo tải đồng thời và quan sát `pending`, acquisition latency, timeout. Thay đổi query duration để thấy tác động đến pool.
5. Chuyển JDBC URL từ RDS endpoint sang RDS Proxy endpoint; so sánh `ClientConnections`, `DatabaseConnections` và borrow latency.
6. Thực hiện rotation password trong Secrets Manager ở môi trường thử nghiệm; kiểm tra ứng dụng mở được connection mới và pool retire connection cũ.
7. Tìm hiểu IAM DB authentication cho PostgreSQL hoặc MySQL: bật tính năng, cấu hình DB user, policy `rds-db:connect`, token 15 phút và cơ chế cung cấp token cho connection mới.
8. Mô phỏng failover/restart trên RDS staging, ghi nhận connection lỗi, transaction thất bại và cách retry theo reservation ID ổn định.
9. So sánh pool JDBC của RDS với cách quản lý connection tới Azure Database for PostgreSQL/MySQL và Google Cloud SQL; chỉ ra phần Spring `DataSource` có thể dùng chung và phần endpoint/auth/proxy phụ thuộc provider.

**Tiêu chí hoàn thành:** người học giải thích được đường đi JDBC từ Spring Boot tới RDS, cấu hình được HikariCP có căn cứ, tính được tổng connection theo replica, bảo vệ credential/TLS, xử lý failover và chứng minh transaction không cập nhật dở bằng integration test.

## Tài liệu tham khảo

- [Amazon RDS — Connecting to a DB instance](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/CHAP_CommonTasks.Connect.html): endpoint, port, network và client connection.
- [Amazon RDS — Security with VPC](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/Overview.RDSSecurityGroups.html): security group và network access.
- [Amazon RDS — SSL/TLS connections](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/UsingWithRDS.SSL.html): CA bundle và TLS theo database engine.
- [Amazon RDS Proxy](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/rds-proxy.html): connection pooling, multiplexing, authentication và failover.
- [Amazon RDS — IAM database authentication](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/UsingWithRDS.IAMDBAuth.html): IAM token, DB user và policy.
- [Amazon RDS — Managing credentials with Secrets Manager](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/rds-secrets-manager.html): lưu trữ và rotation database credentials.
- [Amazon RDS — Working with parameter groups](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/USER_WorkingWithParamGroups.html): cấu hình engine như `max_connections`.
- [Spring Boot — SQL Databases](https://docs.spring.io/spring-boot/reference/data/sql.html): DataSource, JDBC, pool và auto-configuration.
- [HikariCP — Configuration](https://github.com/brettwooldridge/HikariCP#configuration-knobs-baby): ý nghĩa các pool properties.
- [AWS SDK for Java 2.x — Generate an IAM authentication token](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/examples-rds.html): tạo token IAM bằng SDK.
