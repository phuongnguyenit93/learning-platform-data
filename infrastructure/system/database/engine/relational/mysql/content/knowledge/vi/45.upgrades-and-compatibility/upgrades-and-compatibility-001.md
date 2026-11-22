# Lập ma trận tương thích server, Connector/J, công cụ và ứng dụng

Một hệ thống MySQL không chỉ có máy chủ cơ sở dữ liệu. Ứng dụng Java kết nối qua Connector/J, framework ORM tạo SQL, connection pool quản lý phiên, công cụ migration thay đổi schema, còn hệ thống backup, giám sát và proxy tham gia vận hành. Khi nâng cấp một thành phần, các thành phần còn lại vẫn phải tương thích với phiên bản mới và với nhau.

Ma trận tương thích là tài liệu ghi lại các phiên bản đang dùng, phiên bản dự kiến, điều kiện hỗ trợ, kết quả kiểm thử và bằng chứng cho từng thành phần. Ma trận giúp trả lời ba câu hỏi: tổ hợp nào được nhà cung cấp hỗ trợ, tổ hợp nào đã được đội dự án kiểm thử và tổ hợp nào được phép triển khai production. Ba trạng thái này cần được phân biệt rõ; một driver có thể kết nối được trong thử nghiệm nhưng chưa chắc nằm trong tổ hợp được hỗ trợ chính thức.

Bài học này nằm trong phạm vi làm chủ MySQL từ thiết kế bảng, kiểu dữ liệu và SQL đến tối ưu truy vấn, phân quyền, backup và vận hành. Trọng tâm là xây dựng ma trận có thể dùng trong đánh giá nâng cấp và kiểm soát thay đổi.

## 1. Các lớp cần có trong ma trận

Một ma trận đầy đủ cần bao phủ các thành phần có ảnh hưởng đến kết nối, câu lệnh SQL, dữ liệu và quy trình vận hành:

| Lớp | Thành phần cần ghi nhận | Ví dụ thông tin phiên bản |
|---|---|---|
| Database server | MySQL Community/Enterprise, phiên bản, patch level, edition | Phiên bản hiện tại và phiên bản đích |
| Java runtime | JDK/JRE, vendor, phiên bản, TLS provider | Java runtime chạy ứng dụng |
| JDBC driver | MySQL Connector/J, artifact và phiên bản | com.mysql:mysql-connector-j |
| Framework ứng dụng | Spring Boot, Spring Framework, Hibernate/JPA, MyBatis | Phiên bản framework và dialect |
| Connection pool | HikariCP, Apache DBCP hoặc pool khác | Phiên bản, cấu hình timeout và validation |
| Migration/schema | Flyway, Liquibase, công cụ nội bộ | Phiên bản parser, plugin và migration scripts |
| Proxy/routing | MySQL Router, proxy hoặc service discovery | Phiên bản và chế độ routing |
| Vận hành | MySQL Shell, client, backup, restore, monitoring, CDC | Phiên bản công cụ và định dạng dữ liệu |
| Hạ tầng | Hệ điều hành, kiến trúc CPU, container image, TLS, network | Phiên bản hệ điều hành và image |

Không bỏ qua các thư viện phụ thuộc. Ví dụ, ứng dụng có thể khai báo Connector/J tương thích với server nhưng phiên bản Spring Boot đang dùng lại khóa một phiên bản driver khác; hoặc driver hoạt động với JDK nhưng connection pool cũ có vấn đề khi đóng connection. Ma trận cần phản ánh dependency thực tế được đóng gói và chạy, không chỉ phiên bản khai báo trực tiếp.

## 2. Phân biệt hỗ trợ, tương thích và đã kiểm thử

Các trạng thái nên được định nghĩa nhất quán:

| Trạng thái | Ý nghĩa | Cách sử dụng |
|---|---|---|
| Supported | Nhà cung cấp công bố hỗ trợ tổ hợp hoặc phiên bản đó | Điều kiện đầu vào để xem xét production |
| Compatible | Giao thức hoặc API có khả năng hoạt động cùng nhau theo tài liệu | Chưa đủ để kết luận phù hợp workload cụ thể |
| Tested | Đội dự án đã chạy bộ kiểm thử trên đúng tổ hợp phiên bản | Có bằng chứng test, log và kết quả |
| Approved | Tổ chức đã chấp thuận tổ hợp cho môi trường xác định | Được phép triển khai theo quy trình thay đổi |
| Blocked | Có lỗi, thiếu hỗ trợ hoặc rủi ro chưa được xử lý | Không đưa vào production |
| Unknown | Chưa có đủ tài liệu hoặc kết quả kiểm thử | Cần bổ sung bằng chứng trước khi phê duyệt |

Một tổ hợp có thể được nhà cung cấp hỗ trợ nhưng vẫn chưa được ứng dụng kiểm thử. Ngược lại, một tổ hợp có thể chạy được trong môi trường thử nghiệm nhưng nằm ngoài phạm vi hỗ trợ của nhà cung cấp. Không gộp các trạng thái này thành một cột "OK".

Mỗi dòng ma trận nên có tối thiểu:

- Thành phần và vai trò.
- Phiên bản hiện tại, phiên bản mục tiêu và phiên bản thực tế trong môi trường test.
- Phiên bản tối thiểu/tối đa được tài liệu hỗ trợ nếu có.
- Điều kiện tương thích như JDK, hệ điều hành, TLS, authentication plugin hoặc server feature.
- Trạng thái hỗ trợ, kết quả kiểm thử và quyết định triển khai.
- Liên kết release notes, compatibility matrix hoặc tài liệu chính thức.
- Ngày xác minh, người xác minh, test run và vấn đề còn mở.

## 3. Mẫu ma trận tương thích

Mẫu dưới đây là cấu trúc để điền theo môi trường thật. Các ô "Chưa xác minh" không phải kết luận tương thích; phải thay bằng phiên bản cụ thể và bằng chứng từ nhà cung cấp cùng kết quả kiểm thử.

| Thành phần | Hiện tại | Mục tiêu | Điều kiện phải xác minh | Kết quả |
|---|---|---|---|---|
| MySQL Server | server-current | server-target | Đường nâng cấp, tính năng bị loại bỏ, cấu hình mặc định và định dạng dữ liệu | Chưa xác minh |
| Connector/J | connector-current | connector-target | Server được hỗ trợ, JDK tối thiểu, authentication, TLS và thay đổi connection properties | Chưa xác minh |
| JDK | jdk-current | jdk-target | Connector/J, framework, TLS provider, chứng chỉ và runtime container | Chưa xác minh |
| Spring Boot/Framework | framework-current | framework-target | Phiên bản Java, dependency management, auto-configuration và driver được quản lý | Chưa xác minh |
| Hibernate/JPA | orm-current | orm-target | Dialect, SQL sinh ra, kiểu dữ liệu, schema validation và transaction behavior | Chưa xác minh |
| Connection pool | pool-current | pool-target | JDBC API, timeout, validation, failover và leak detection | Chưa xác minh |
| Flyway/Liquibase | migration-current | migration-target | Server support, parser, transactional DDL và lịch sử migration | Chưa xác minh |
| MySQL Shell/Router | tools-current | tools-target | Phiên bản server, metadata, topology và thao tác quản trị | Chưa xác minh |
| Backup/restore | backup-current | backup-target | Khả năng đọc định dạng, physical/logical compatibility và restore test | Chưa xác minh |
| Monitoring/CDC | monitor-current | monitor-target | Performance Schema, status variables, binlog format và authentication | Chưa xác minh |

Có thể duy trì hai ma trận: ma trận theo môi trường (development, staging, production) và ma trận theo tổ hợp phần mềm. Nếu production có nhiều cụm với phiên bản khác nhau, phải ghi rõ từng cụm; không ghi một phiên bản chung khi thực tế còn node chạy patch level khác.

## 4. Xác minh MySQL Server và đường nâng cấp

### 4.1. Ghi nhận baseline

Trên mỗi instance, lấy thông tin server đang chạy:

~~~sql
SELECT
  VERSION() AS mysql_version,
  @@version_comment AS distribution,
  @@version_compile_os AS compile_os,
  @@version_compile_machine AS compile_machine;

SHOW VARIABLES
WHERE Variable_name IN (
  'sql_mode',
  'character_set_server',
  'collation_server',
  'lower_case_table_names',
  'default_authentication_plugin',
  'require_secure_transport'
);
~~~

Danh sách biến thay đổi theo phiên bản; một số biến có thể không còn tồn tại hoặc có tên khác. Khi truy vấn nhiều biến trong một câu, cần điều chỉnh theo server thực tế thay vì xem lỗi "unknown variable" là lỗi của ứng dụng.

Ghi nhận thêm cấu hình từ tệp cấu hình, tham số khởi động, plugin, component, storage engine, replication/Group Replication và các tính năng đang được ứng dụng sử dụng. Kết quả VERSION() không đủ để mô tả toàn bộ môi trường vì các node có thể khác cấu hình, plugin hoặc patch level.

### 4.2. Kiểm tra đường nâng cấp được hỗ trợ

Không phải mọi phiên bản nguồn đều có thể nâng trực tiếp lên mọi phiên bản đích. Trước khi lập lịch, tra tài liệu nâng cấp của đúng dòng MySQL và xác minh:

1. Phiên bản nguồn có được hỗ trợ làm điểm bắt đầu cho phiên bản đích không.
2. Có yêu cầu nâng lên một phiên bản trung gian hay không.
3. Hệ điều hành, kiến trúc, package repository và định dạng dữ liệu có được hỗ trợ không.
4. Có thay đổi về cấu hình mặc định, system table, data dictionary hoặc plugin cần xử lý không.
5. Có yêu cầu nâng cấp MySQL Shell, Router, backup agent hoặc các công cụ cùng thời điểm không.
6. Có giới hạn tương thích khi các node trong topology chạy phiên bản khác nhau trong giai đoạn rolling upgrade không.

Đọc release notes của cả phiên bản nguồn, phiên bản trung gian nếu có và phiên bản đích. Chú ý mục incompatibilities, removed/deprecated features, changed defaults, upgrade procedure và known issues. Không suy ra đường nâng cấp chỉ từ số phiên bản lớn hơn.

### 4.3. Chạy Upgrade Checker và kiểm tra thủ công

MySQL Shell có Upgrade Checker Utility để kiểm tra một số vấn đề có thể cản trở nâng cấp. Có thể chạy từ MySQL Shell sau khi kết nối đến instance nguồn:

~~~javascript
util.checkForServerUpgrade();
~~~

Đối chiếu cú pháp và các tùy chọn của tiện ích với phiên bản MySQL Shell đang cài. Kết quả checker là đầu vào quan trọng nhưng không thay thế kiểm thử ứng dụng. Công cụ không thể biết mọi truy vấn động, mọi dữ liệu thực tế hoặc hành vi của các thư viện bên ngoài.

Các điểm cần rà soát thêm:

- Cấu hình và biến hệ thống bị deprecated hoặc bị loại bỏ.
- Tên cột, bảng, alias hoặc từ khóa có thể trở thành reserved keyword.
- Kiểu dữ liệu, giá trị mặc định, phép ép kiểu và hành vi ngày giờ.
- SQL mode và các thay đổi về kiểm tra dữ liệu.
- Authentication plugin, tài khoản và chính sách mật khẩu.
- Charset/collation, so sánh chuỗi và thứ tự sắp xếp.
- Plugin, component, UDF và storage engine bên ngoài.
- Replication filter, binlog format, GTID và topology HA.

## 5. MySQL Server và Connector/J

Connector/J là JDBC driver cho Java. Driver chịu trách nhiệm chuyển lời gọi JDBC thành giao thức MySQL, xử lý xác thực, TLS, kiểu dữ liệu và các thuộc tính kết nối. Server và driver có vòng đời phát hành riêng, vì vậy cần kiểm tra compatibility matrix và release notes của Connector/J thay vì ghép số phiên bản theo cảm tính.

### 5.1. Những điều cần xác minh

| Hạng mục | Câu hỏi kiểm tra |
|---|---|
| Server support | Phiên bản Connector/J có hỗ trợ phiên bản MySQL Server mục tiêu không? |
| Java support | Driver yêu cầu JDK/JRE tối thiểu nào và có hỗ trợ runtime đang dùng không? |
| JDBC API | Phiên bản JDBC và các API mà ứng dụng sử dụng có phù hợp không? |
| Authentication | Driver hỗ trợ plugin xác thực đang bật trên server không? |
| TLS | Driver và JDK hỗ trợ protocol/cipher; có xác minh hostname và CA không? |
| Data types | Mapping cho JSON, temporal, decimal, bit, enum, spatial và unsigned có thay đổi không? |
| Connection properties | Thuộc tính cũ còn được hỗ trợ, đổi tên hoặc thay default không? |
| Behavior | Prepared statement, batching, generated keys, metadata và transaction có thay đổi không? |

Connector/J hiện đại sử dụng driver class:

~~~java
com.mysql.cj.jdbc.Driver
~~~

Các framework JDBC hiện đại thường tự phát hiện driver thông qua JDBC service provider khi dependency có trên classpath. Nếu cấu hình driver class tường minh, phải dùng tên phù hợp với phiên bản Connector/J đã chọn. Không giữ class name cũ chỉ vì cấu hình lịch sử vẫn chạy trong một môi trường.

Dependency Maven có dạng:

~~~xml
<dependency>
  <groupId>com.mysql</groupId>
  <artifactId>mysql-connector-j</artifactId>
  <version>DRIVER_VERSION_APPROVED_FOR_THIS_PROJECT</version>
</dependency>
~~~

Giá trị phiên bản phải được thay bằng phiên bản đã xác minh và khóa trong dependency management. Không dùng phiên bản động hoặc để môi trường tự tải bản mới nhất ngoài quy trình quản lý dependency.

### 5.2. Authentication và TLS

MySQL Server có thể sử dụng plugin xác thực khác nhau theo phiên bản và cấu hình. Kiểm tra plugin của từng tài khoản:

~~~sql
SELECT
  user,
  host,
  plugin
FROM mysql.user
ORDER BY user, host;
~~~

Truy vấn này cần quyền đọc phù hợp; không xuất hoặc chia sẻ password hash. Xác nhận Connector/J, JDK và cấu hình server cùng hỗ trợ plugin đang dùng. Khi nâng cấp, kiểm tra cả tài khoản ứng dụng, tài khoản migration, monitoring, backup và replication.

Khi kết nối qua mạng, cấu hình TLS với CA đáng tin cậy và xác minh danh tính máy chủ. Với Connector/J hỗ trợ thuộc tính sslMode, cấu hình có xác minh hostname có thể được khai báo trong JDBC URL:

~~~properties
spring.datasource.url=jdbc:mysql://mysql.internal.example:3306/appdb?sslMode=VERIFY_IDENTITY
~~~

Tên máy chủ trong URL phải khớp với Subject Alternative Name của chứng chỉ. Cấu hình trust store, CA và client certificate nếu chính sách yêu cầu. Không hạ chế độ xác minh chứng chỉ chỉ để bỏ qua lỗi hostname hoặc CA; sửa DNS, chứng chỉ hoặc trust chain theo đúng môi trường.

### 5.3. Kiểm tra connection properties

Connector/J có nhiều thuộc tính ảnh hưởng đến hành vi, ví dụ:

- connectTimeout và socketTimeout.
- sslMode và cấu hình trust store.
- connectionTimeZone và cách xử lý thời gian.
- useServerPrepStmts và cachePrepStmts.
- rewriteBatchedStatements.
- allowPublicKeyRetrieval.
- characterEncoding và thuộc tính liên quan đến session.

Không sao chép toàn bộ JDBC URL cũ sang driver mới mà không kiểm tra. Một thuộc tính có thể bị deprecated, đổi tên, thay default hoặc không còn tác dụng. Đặc biệt, không bật allowPublicKeyRetrieval tùy tiện để xử lý xác thực; ưu tiên TLS đã xác minh và cấu hình xác thực theo tài liệu của server/driver.

## 6. Java runtime, framework và connection pool

### 6.1. Java runtime

Kiểm tra JDK chạy thực tế trong môi trường production, không chỉ JDK trên máy phát triển:

~~~bash
java -version
~~~

Đối chiếu yêu cầu Java của Connector/J, Spring Boot, Hibernate, Flyway/Liquibase, connection pool và thư viện nội bộ. Kiểm tra vendor JDK, TLS provider, trust store, container base image và tham số JVM. Nếu nâng JDK cùng lúc với server và driver, lỗi phát sinh sẽ khó quy về một nguyên nhân; nên chia thay đổi thành các bước có thể kiểm thử độc lập khi có thể.

### 6.2. Framework và ORM

Spring Boot có thể quản lý phiên bản Connector/J thông qua dependency management. Hãy kiểm tra dependency tree để biết artifact thực tế:

~~~bash
mvn dependency:tree
~~~

Với Gradle, dùng lệnh dependency report tương ứng cho configuration của ứng dụng. Không chỉ nhìn pom.xml hoặc build.gradle: dependency transitive, BOM, plugin và dependency override có thể khiến runtime nạp phiên bản khác dự kiến.

Với Hibernate/JPA, kiểm tra:

- Dialect được chọn và khả năng nhận diện server version.
- SQL sinh ra cho pagination, locking, JSON, sequence/identity và generated key.
- Mapping java.time, BigDecimal, boolean, enum và unsigned numeric.
- Schema validation và schema generation.
- Transaction isolation, flush mode, batching và optimistic/pessimistic locking.

Không sửa dialect để che lỗi SQL trước khi xác định thay đổi đến từ server, driver hay framework. Chạy integration test trên đúng phiên bản target để phát hiện khác biệt.

### 6.3. Connection pool

Connection pool giữ các phiên JDBC sống lâu hơn một request. Khi nâng cấp, kiểm tra pool có tương thích JDBC driver mới và có xử lý đúng lỗi kết nối, server restart, failover và timeout không.

Các tham số cần ghi trong ma trận:

| Tham số | Ý nghĩa cần đánh giá |
|---|---|
| maximumPoolSize | Giới hạn connection đồng thời và tổng tải lên MySQL |
| connectionTimeout | Thời gian chờ lấy connection từ pool |
| validation/keepalive | Cách phát hiện connection đã chết hoặc bị ngắt |
| maxLifetime | Tuổi thọ connection so với timeout của server/proxy |
| idleTimeout | Thời gian giữ connection nhàn rỗi |
| leakDetectionThreshold | Phát hiện connection bị giữ quá lâu trong môi trường phù hợp |

Ví dụ cấu hình HikariCP:

~~~yaml
spring:
  datasource:
    url: jdbc:mysql://mysql.internal.example:3306/appdb?sslMode=VERIFY_IDENTITY
    username: app_user
    hikari:
      maximum-pool-size: 20
      connection-timeout: 30000
      max-lifetime: 1500000
      validation-timeout: 5000
~~~

Các con số trên chỉ là ví dụ, không phải cấu hình tối ưu chung. Hãy tính pool size theo số instance ứng dụng, số connection tối đa của MySQL, tải thực tế và các dịch vụ dùng chung database. Một pool quá lớn có thể làm server quá tải; pool quá nhỏ có thể tạo hàng đợi ở ứng dụng.

## 7. Công cụ migration, backup, router và monitoring

### 7.1. Công cụ thay đổi schema

Flyway và Liquibase cần được kiểm tra theo phiên bản server và Java runtime. Xác minh parser có hiểu cú pháp mới, cách xử lý DDL, lock metadata, checksum migration và khả năng resume khi migration thất bại.

MySQL DDL có nhiều thao tác gây implicit commit hoặc không thể rollback như một transaction InnoDB thông thường. Không giả định migration script có thể hoàn tác chỉ bằng ROLLBACK. Mỗi thay đổi schema quan trọng cần có kế hoạch expand/contract, backup hoặc phương án sửa tiếp theo.

### 7.2. Công cụ backup và restore

Kiểm tra công cụ backup có hỗ trợ phiên bản MySQL nguồn/đích, định dạng physical backup và cách ghi nhận GTID/binlog coordinates hay không. Một bản backup tạo thành công chưa chứng minh có thể restore vào phiên bản đích.

Thực hiện restore test trên môi trường cô lập, kiểm tra:

- Backup có giải mã và đọc được không.
- Phiên bản đích có hỗ trợ định dạng backup không.
- System tables, data dictionary và plugin có tương thích không.
- GTID, binary log và tọa độ khôi phục có được bảo toàn đúng không.
- Thời gian restore có đáp ứng RTO không.

### 7.3. MySQL Shell và MySQL Router

Với InnoDB Cluster hoặc Group Replication, kiểm tra phiên bản MySQL Shell và MySQL Router theo compatibility matrix tương ứng. Xác minh metadata cluster, discovery, routing role, failover và kết nối lại sau khi primary đổi vai trò.

Một router có thể vẫn mở cổng nhưng định tuyến sai role hoặc giữ connection cũ. Kiểm thử cả kết nối mới, kết nối đang tồn tại, chuyển primary và trường hợp một node rời nhóm.

### 7.4. Monitoring và CDC

Dashboard có thể phụ thuộc Performance Schema, status variables, system tables hoặc câu truy vấn nội bộ thay đổi theo phiên bản. Rà soát exporter, agent, alert rule và dashboard. Với CDC, xác minh binlog format, row image, GTID, retention và cách connector xử lý DDL hoặc server restart.

## 8. Kiểm tra thay đổi hành vi SQL và dữ liệu

Khả năng kết nối thành công không chứng minh ứng dụng tương thích. Server mới có thể thay đổi hành vi SQL, mặc định hoặc cách kiểm tra dữ liệu.

### 8.1. SQL mode và cú pháp

So sánh @@sql_mode giữa môi trường hiện tại và target. Kiểm tra ứng dụng có dựa vào việc chấp nhận dữ liệu không hợp lệ, implicit conversion, giá trị ngày giờ đặc biệt hoặc GROUP BY không chuẩn hay không.

Rà soát câu SQL có:

- Tên bảng/cột/alias có thể trùng reserved keyword.
- Hàm hoặc cú pháp đã deprecated hay thay đổi.
- GROUP BY, ORDER BY, LIMIT, window function và CTE.
- Locking clause như FOR UPDATE hoặc SKIP LOCKED.
- JSON, generated column, functional index và expression.
- DDL, partition, check constraint và foreign key.

### 8.2. Charset và collation

Charset/collation ảnh hưởng việc lưu trữ, so sánh, unique key và thứ tự sắp xếp. Khi đổi collation, hai chuỗi trước đây phân biệt có thể được xem là bằng nhau hoặc ngược lại. Điều này có thể làm phát sinh duplicate key khi tạo unique index hoặc thay đổi kết quả tìm kiếm.

Kiểm tra charset ở server, database, table, column và connection session. Chạy thử với dữ liệu có dấu, emoji, ký tự ngoài BMP, ký tự kết hợp và chuỗi có khác biệt hoa/thường hoặc dấu.

### 8.3. Kiểu dữ liệu và thời gian

Kiểm tra mapping giữa MySQL và Java:

| MySQL | Java/JDBC thường gặp | Rủi ro cần thử |
|---|---|---|
| DECIMAL | BigDecimal | Độ chính xác, scale và rounding |
| BIGINT | Long | Giá trị biên và tràn kiểu |
| TINYINT(1) | Boolean hoặc số | Mapping phụ thuộc driver/framework |
| DATETIME | LocalDateTime | Không mang timezone |
| TIMESTAMP | Instant/OffsetDateTime hoặc kiểu khác | Chuyển đổi theo session/server timezone |
| JSON | String hoặc mapping JSON của framework | Serialization, null và kiểu dữ liệu |
| BIT | Boolean/byte array | Mapping và cách đọc ResultSet |
| ENUM | String hoặc enum ứng dụng | Giá trị mới và thứ tự enum |

Đặc biệt kiểm tra timezone của JVM, server, session và dữ liệu. Một thay đổi cấu hình timezone có thể làm lệch thời điểm hiển thị hoặc lưu trữ dù câu truy vấn vẫn chạy.

## 9. Quy trình xây dựng và duyệt ma trận

Một quy trình có thể lặp lại:

1. **Inventory:** thu thập phiên bản server, JDK, driver, framework, pool, migration tool, backup, router và monitoring từ môi trường thực tế.
2. **Chọn target:** xác định phiên bản dự kiến và đường nâng cấp được nhà cung cấp hỗ trợ.
3. **Tra cứu support:** đọc compatibility matrix và release notes của từng thành phần, lưu liên kết và ngày xác minh.
4. **Phân tích dependency:** kiểm tra BOM, dependency tree, container image, plugin và các thư viện transitive.
5. **Ghi điều kiện:** ghi rõ JDK tối thiểu, TLS, authentication, SQL mode, dialect, cấu hình và yêu cầu vận hành.
6. **Lập test matrix:** xác định các tổ hợp phiên bản cần chạy; ưu tiên tổ hợp production mục tiêu và các tổ hợp chuyển tiếp nếu rollout theo giai đoạn.
7. **Kiểm thử:** chạy unit, integration, migration, performance, failover, backup/restore và security test.
8. **Xử lý sai lệch:** phân loại lỗi theo server, driver, framework, schema, dữ liệu, cấu hình hoặc network; ghi workaround và chủ sở hữu.
9. **Phê duyệt:** chỉ đánh dấu Approved khi mọi kiểm tra bắt buộc đạt và có phương án rollback.
10. **Khóa phiên bản:** cập nhật BOM, lockfile, container image và cấu hình triển khai để mọi môi trường dùng đúng tổ hợp đã duyệt.

## 10. Bộ kiểm thử cho tổ hợp mới

Ma trận chỉ có giá trị khi gắn với kiểm thử cụ thể. Có thể tổ chức theo các lớp sau:

| Nhóm test | Nội dung | Điều kiện đạt |
|---|---|---|
| Kết nối | DNS, TCP, TLS, xác minh chứng chỉ, xác thực và reconnect | Kết nối đúng server, không hạ bảo mật |
| JDBC | Prepared statement, batch, generated keys, metadata, ResultSet | Hành vi đúng với API ứng dụng dùng |
| SQL | Truy vấn đọc/ghi, join, pagination, locking, JSON và DDL | Kết quả và lỗi đúng kỳ vọng |
| Transaction | Commit, rollback, isolation, deadlock và retry | Không mất giao dịch, retry có kiểm soát |
| ORM | Mapping, lazy loading, flush, schema validation và dialect | Không phát sinh SQL sai hoặc thay đổi dữ liệu |
| Pool | Timeout, connection stale, server restart, failover | Pool phục hồi theo SLO |
| Migration | Chạy từ schema cũ đến schema mới, resume và checksum | Migration xác định, có thể vận hành lại |
| Backup/restore | Restore từ backup và PITR nếu có | Dữ liệu phục hồi đạt RPO/RTO |
| Performance | Throughput, latency p95/p99, CPU, I/O và connection count | Nằm trong ngưỡng đã thống nhất |
| Security | Authentication, TLS, grants, secret rotation | Không có quyền dư hoặc kết nối không xác minh |

Chạy kiểm thử với dữ liệu đại diện, gồm cả giá trị biên, NULL, chuỗi Unicode, số thập phân, ngày giờ và các bản ghi có quan hệ khóa ngoại. Test trên database rỗng không đủ để phát hiện lỗi do dữ liệu production tích lũy qua nhiều năm.

## 11. Ví dụ ma trận test cho một đợt nâng cấp

Giả sử nhóm dự án dự kiến nâng MySQL Server và đồng thời thay Connector/J, JDK và framework. Hãy tách thay đổi để có thể quy lỗi:

| Lượt | Server | JDK/Connector/J | Framework | Mục đích |
|---|---|---|---|---|
| A | Phiên bản hiện tại | Bộ hiện tại | Hiện tại | Baseline và đo hiệu năng |
| B | Phiên bản đích | Bộ hiện tại nếu được hỗ trợ | Hiện tại | Cô lập tác động server |
| C | Phiên bản đích | Connector/J mục tiêu | Hiện tại | Kiểm tra driver và JDBC |
| D | Phiên bản đích | JDK mục tiêu + driver mục tiêu | Hiện tại | Kiểm tra runtime và TLS |
| E | Phiên bản đích | Bộ mục tiêu | Framework mục tiêu | Kiểm tra toàn bộ tổ hợp production |

Đây là trình tự kiểm thử minh họa. Nếu nhà cung cấp không hỗ trợ tổ hợp trung gian ở lượt B hoặc C, không triển khai tổ hợp đó trên production; chỉ dùng môi trường thử nghiệm nếu có thể và phù hợp với điều kiện hỗ trợ. Khi phải nâng cấp đồng thời vì ràng buộc kỹ thuật, hãy tăng cường test tích hợp và giữ bằng chứng rõ cho từng thay đổi.

Mỗi lượt cần ghi:

- Commit ứng dụng và artifact được kiểm thử.
- Container image hoặc JDK build.
- Phiên bản MySQL chính xác trên từng node.
- Connector/J và dependency tree thực tế.
- Cấu hình server, SQL mode, charset, collation và TLS.
- Bộ dữ liệu, script migration và test suite.
- Kết quả test, log lỗi, latency và tài nguyên.

## 12. Quản lý rủi ro và quyết định production

Không nên phê duyệt chỉ dựa vào việc mọi dependency đều có phiên bản mới nhất. Phiên bản mới có thể thay đổi API, default, authentication, SQL generation hoặc yêu cầu Java. Hãy chọn tổ hợp được hỗ trợ, đã kiểm thử và phù hợp với chu kỳ bảo trì của tổ chức.

Các điều kiện nên chặn triển khai:

- Server target nằm ngoài đường nâng cấp được hỗ trợ.
- Connector/J không hỗ trợ server hoặc JDK mục tiêu.
- Framework/ORM chưa hỗ trợ runtime hoặc driver đã chọn.
- TLS hoặc authentication không đáp ứng chính sách bảo mật.
- Migration tool không thể đọc/ghi schema target theo cách đã kiểm thử.
- Backup không restore được trên môi trường tương thích.
- Có lỗi dữ liệu, transaction, deadlock hoặc hiệu năng vượt ngưỡng.
- Chưa có phương án rollback và người chịu trách nhiệm quyết định.

Khi ma trận được duyệt, lưu phiên bản cùng ngày xác minh và bằng chứng. Cập nhật lại ma trận khi có bản vá server, đổi JDK, thay framework, cập nhật driver, đổi CA/chứng chỉ hoặc thêm công cụ vận hành.

## 13. Tình huống thực hành

Một ứng dụng Java đang chạy MySQL Server, Connector/J, Spring Boot, Hibernate và HikariCP theo các phiên bản đã ổn định nhiều năm. Nhóm vận hành muốn nâng server lên một dòng mới và đồng thời cập nhật JDK để đáp ứng chính sách bảo mật.

Hãy xây dựng kế hoạch:

1. Thu thập phiên bản thật từ server, runtime, dependency tree, container image và cấu hình pool.
2. Tra tài liệu hỗ trợ của server target, Connector/J, JDK, Spring Boot, Hibernate và HikariCP.
3. Ghi các ràng buộc về authentication plugin, TLS, timezone, SQL mode, charset và dialect.
4. Kiểm tra migration tool, backup/restore, monitoring và MySQL Router nếu hệ thống dùng chúng.
5. Tạo các lượt test tách biệt để xác định lỗi do server, driver, runtime hay framework.
6. Chạy integration test với dữ liệu đại diện, đặc biệt các kiểu dữ liệu thời gian, decimal, JSON và Unicode.
7. Chạy performance test, failover test và restore test.
8. Đánh dấu Approved chỉ khi tổ hợp đầy đủ đạt tiêu chí và đã có phương án quay lui.

Kết quả cần là một ma trận có thể được người khác đọc và tái lập, không phải một danh sách phiên bản rời rạc. Mỗi kết luận tương thích phải chỉ ra tài liệu hỗ trợ hoặc test run chứng minh.

## 14. Câu hỏi tự kiểm tra

1. Vì sao "driver kết nối được" chưa đủ chứng minh tổ hợp server và Connector/J được hỗ trợ?
2. Ma trận cần ghi những thành phần nào ngoài MySQL Server và JDBC driver?
3. Vì sao phải kiểm tra dependency tree thay vì chỉ đọc file build?
4. Authentication plugin và TLS có thể gây lỗi gì sau khi nâng cấp?
5. SQL mode, collation và timezone có thể làm thay đổi hành vi ứng dụng ra sao?
6. Vì sao cần kiểm tra backup/restore và migration tool cùng với server target?
7. Một tổ hợp cần những bằng chứng nào để chuyển từ Tested sang Approved?
8. Khi nâng server, JDK, Connector/J và framework cùng lúc, làm thế nào để khoanh vùng lỗi?

Ma trận tương thích là một phần của quản lý thay đổi MySQL. Khi phiên bản, điều kiện hỗ trợ, dependency thực tế, kết quả kiểm thử và quyết định production được ghi cùng nhau, đội dự án có thể nâng cấp có kiểm soát và phát hiện sớm rủi ro giữa database, Java driver, framework và công cụ vận hành.
