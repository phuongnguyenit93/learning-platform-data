# Cấu hình dialect, múi giờ, pool và timeout theo môi trường

## 1. Vì sao cấu hình database phải theo môi trường?

Spring Data JPA chạy trên Hibernate/JPA provider, JDBC driver và database server. Một request chỉ truy cập database thành công khi các lớp này thống nhất về vendor, kiểu dữ liệu, múi giờ, kết nối và giới hạn thời gian.

Các môi trường local, test, staging và production thường khác nhau ở:

- JDBC URL, hostname, port, database/schema.
- Database vendor và phiên bản engine.
- Tài khoản, quyền, secret và TLS.
- Múi giờ của JVM, JDBC connection và database session.
- Kích thước connection pool và số instance ứng dụng.
- Timeout kết nối, chờ connection, câu SQL, lock và transaction.
- Cấu hình migration, schema validation và giới hạn tài nguyên.

Nếu cấu hình những giá trị này trực tiếp trong source code, ứng dụng khó triển khai ở nhiều môi trường và dễ phát sinh lỗi như sai dialect, lệch thời gian, cạn connection pool hoặc request treo quá lâu.

Nguyên tắc triển khai là giữ logic JPA thống nhất, đưa cấu hình môi trường vào external configuration/profile/secret, chọn database engine đúng với production và kiểm chứng các giá trị thực tế khi ứng dụng khởi động.

## 2. Các lớp cấu hình cần phân biệt

| Thành phần | Trách nhiệm | Ví dụ |
|---|---|---|
| JDBC driver | Giao tiếp với database | PostgreSQL JDBC, MySQL Connector/J |
| JDBC URL | Chỉ ra database và tùy chọn kết nối | \`jdbc:postgresql://db:5432/app\` |
| Dialect | Chuyển query Hibernate thành SQL phù hợp | PostgreSQLDialect, MySQLDialect |
| JVM timezone | Múi giờ mặc định của process Java | UTC |
| Hibernate JDBC timezone | Timezone dùng khi bind/đọc một số giá trị JDBC | \`hibernate.jdbc.time_zone=UTC\` |
| Database session timezone | Múi giờ của session giữ connection | \`SHOW TimeZone\`, \`@@session.time_zone\` |
| Connection pool | Tái sử dụng và giới hạn JDBC connection | HikariCP |
| Connection timeout | Giới hạn thời gian chờ/mở kết nối | Hikari acquisition, driver connect |
| Query timeout | Giới hạn thời gian thực thi SQL | JPA/JDBC/database |
| Transaction timeout | Giới hạn thời gian transaction | \`@Transactional(timeout = 5)\` |

Một cấu hình không thay thế cho cấu hình khác. Ví dụ, đặt Hibernate JDBC timezone thành UTC không tự đổi timezone của PostgreSQL session. Hikari connectionTimeout cũng không phải query timeout.

## 3. JDBC URL và driver

### 3.1. PostgreSQL

```properties
spring.datasource.url=jdbc:postgresql://db.internal:5432/customer_db
spring.datasource.username=customer_app
spring.datasource.password=${DB_PASSWORD}
```

Driver là \`org.postgresql:postgresql\`. Spring Boot thường suy ra driver từ JDBC URL khi driver có trên classpath; không cần khai báo \`spring.datasource.driver-class-name\` nếu không có lý do đặc biệt.

### 3.2. MySQL

```properties
spring.datasource.url=jdbc:mysql://db.internal:3306/customer_db
spring.datasource.username=customer_app
spring.datasource.password=${DB_PASSWORD}
```

Driver là MySQL Connector/J, artifact hiện hành thường là \`com.mysql:mysql-connector-j\`. Cũng nên để Spring Boot suy ra driver từ URL.

### 3.3. Đưa URL và credential ra khỏi source code

Local có thể dùng container hoặc database trên máy phát triển; CI dùng Testcontainers; staging và production dùng endpoint managed database. Đưa URL vào profile hoặc biến môi trường, không sửa code rồi build artifact riêng cho từng môi trường.

Không commit password, token hoặc private key vào Git. Dùng secret store của nền tảng triển khai, CI secret hoặc biến môi trường được bảo vệ. Không in toàn bộ JDBC URL có chứa credential vào log.

Production thường cần TLS, CA certificate và xác minh hostname theo chính sách hạ tầng. Cấu hình TLS phụ thuộc driver và certificate; không sao chép một cờ SSL từ vendor này sang vendor khác.

Kiểm tra từ đúng host/container chạy ứng dụng:
- DNS có phân giải hostname database không?
- Firewall/route có cho phép kết nối tới port không?
- TLS certificate còn hạn và hostname có khớp không?
- User có quyền kết nối database/schema không?
- Proxy/load balancer có idle timeout hoặc connection lifetime giới hạn không?

Kết nối thành công từ laptop không chứng minh pod production có cùng network path.

## 4. Dialect của Hibernate

### 4.1. Dialect dùng để làm gì?

Dialect mô tả các khác biệt SQL theo database, chẳng hạn cú pháp phân trang, kiểu dữ liệu, generated value, sequence/identity, function SQL, locking và DDL. Hibernate dùng dialect để sinh SQL phù hợp với database mà JDBC connection đang truy cập.

### 4.2. Hibernate hiện đại thường tự nhận diện dialect

Với Hibernate 6 trở lên, Hibernate đọc JDBC metadata để xác định vendor/version rồi chọn dialect phù hợp. Ứng dụng Spring Boot thông thường không cần khai báo dialect thủ công.

```yaml
spring:
  datasource:
    url: jdbc:postgresql://localhost:5432/customer_db
    username: customer_app
    password: ${DB_PASSWORD}
  jpa:
    hibernate:
      ddl-auto: validate
```

Nếu URL kết nối PostgreSQL, Hibernate chọn dialect PostgreSQL. Nếu URL trỏ tới MySQL, dialect tương ứng được nhận diện từ metadata.

Không đặt PostgreSQL dialect cố định trong artifact rồi triển khai artifact đó tới MySQL. Dialect sai có thể làm Hibernate sinh SQL không tương thích hoặc ánh xạ kiểu dữ liệu không đúng.

### 4.3. Khi nào cần khai báo dialect?

Chỉ override khi có lý do cụ thể:
- Dùng custom dialect do ứng dụng/thư viện cung cấp.
- Hibernate không thể đọc JDBC metadata trong quá trình bootstrap.
- Môi trường đặc biệt cần khởi tạo metadata khi chưa mở connection.
- Có workaround đã xác định cho provider/database version.

Spring Boot hỗ trợ:

```yaml
spring:
  jpa:
    database-platform: com.example.persistence.CustomPostgreSQLDialect
```

Hoặc thuộc tính Hibernate:

```properties
spring.jpa.properties.hibernate.dialect=com.example.persistence.CustomPostgreSQLDialect
```

Chỉ chọn một cách khai báo rõ ràng. \`spring.jpa.database-platform\` là thuộc tính Spring Boot; \`hibernate.dialect\` là thuộc tính Hibernate được chuyển qua \`spring.jpa.properties.*\`.

Với Hibernate 6+, không dùng class dialect cũ chỉ vì thấy trong hướng dẫn Hibernate 5. Một số dialect theo version cũ đã được hợp nhất hoặc deprecated. Hãy dùng dialect phù hợp với major version Hibernate đang chạy.

### 4.4. Không nhầm dialect với driver

| Cấu hình | Ví dụ | Mục đích |
|---|---|---|
| JDBC URL | \`jdbc:postgresql://...\` | Chọn endpoint/database |
| JDBC driver | PostgreSQL JDBC | Mở kết nối theo protocol |
| Hibernate dialect | PostgreSQLDialect | Sinh SQL theo database |
| JPA provider | Hibernate | Thực thi mapping/persistence |

Đổi dialect không biến PostgreSQL driver thành MySQL driver. Muốn đổi vendor phải đổi URL, driver, schema/migration và kiểm thử tương thích.

## 5. Múi giờ: dữ liệu biểu diễn điều gì?

Trước khi cấu hình timezone, xác định cột thời gian biểu diễn ngày lịch, giờ địa phương hay một thời điểm tuyệt đối trên timeline.

| Java type | Ý nghĩa | Dùng khi |
|---|---|---|
| \`LocalDate\` | Ngày lịch, không có giờ/timezone | Ngày sinh, ngày hóa đơn |
| \`LocalTime\` | Giờ trong ngày, không có ngày/timezone | Giờ mở cửa |
| \`LocalDateTime\` | Ngày giờ tường, không offset/zone | Giờ hẹn địa phương khi zone xác định riêng |
| \`Instant\` | Một thời điểm tuyệt đối | Event timestamp, createdAt |
| \`OffsetDateTime\` | Ngày giờ cùng UTC offset | Thời điểm kèm offset đã biết |
| \`ZonedDateTime\` | Ngày giờ cùng ZoneId/quy tắc vùng | Lịch theo vùng như Asia/Ho_Chi_Minh |

Không gắn UTC vào \`LocalDateTime\` rồi coi nó là Instant nếu nghiệp vụ không nói vậy. Một giờ hẹn lúc 09:00 tại Hà Nội là local wall-clock time; một event đã xảy ra nên được mô hình hóa bằng Instant hoặc kiểu tương đương.

Nếu cần tái hiện lịch tương lai theo vùng, lưu ZoneId IANA như \`Asia/Ho_Chi_Minh\` hoặc \`Europe/Berlin\` theo nghiệp vụ. Offset cố định \`+07:00\` không chứa quy tắc daylight saving của một vùng.

## 6. Đồng bộ timezone giữa JVM, Hibernate và database

### 6.1. Quy ước UTC cho instant

Với các trường biểu diễn thời điểm tuyệt đối, quy ước phổ biến là:
- Lưu/trao đổi instant theo UTC.
- Chuyển sang timezone người dùng ở tầng trình bày.
- Không dựa vào timezone mặc định của host.
- Kiểm thử round-trip qua JDBC và database thật.

Có thể đặt JVM timezone trong môi trường chạy:

```bash
java -Duser.timezone=UTC -jar app.jar
```

Đây là lựa chọn cấp process. Không thay đổi \`TimeZone.setDefault()\` trong lúc ứng dụng đang chạy vì nó ảnh hưởng toàn bộ code dùng timezone mặc định.

### 6.2. Hibernate JDBC timezone

Hibernate cung cấp thuộc tính:

```yaml
spring:
  jpa:
    properties:
      hibernate:
        jdbc:
          time_zone: UTC
```

Hoặc:

```properties
spring.jpa.properties.hibernate.jdbc.time_zone=UTC
```

Thuộc tính này giúp Hibernate dùng timezone tham chiếu khi gọi một số API JDBC có hỗ trợ Calendar, đặc biệt khi bind/read các kiểu timestamp/time. Nó không tự đặt timezone của database server hoặc session.

Đặt JVM UTC và Hibernate JDBC timezone UTC giúp giảm phụ thuộc vào timezone mặc định của host. Vẫn phải kiểm tra kiểu cột và session timezone của database.

### 6.3. Hibernate lưu trữ OffsetDateTime/ZonedDateTime

Hibernate có các chiến lược lưu trữ timezone-aware type như \`NORMALIZE\`, \`NATIVE\`, \`COLUMN\` và \`AUTO\` tùy version/provider.

- \`NORMALIZE\`: chuẩn hóa thời điểm, không giữ nguyên zone/offset ban đầu trong cột timestamp.
- \`NATIVE\`: dùng kiểu timestamp with time zone của database nếu dialect hỗ trợ.
- \`COLUMN\`: lưu phần timezone bổ sung trong cột riêng.
- \`AUTO\`: provider chọn chiến lược dựa trên khả năng database.

Với Hibernate hỗ trợ thuộc tính này, có thể cấu hình rõ:

```yaml
spring:
  jpa:
    properties:
      hibernate:
        timezone:
          default_storage: NORMALIZE
```

Đừng giả định \`OffsetDateTime\` luôn giữ lại offset ban đầu sau khi lưu và đọc. Nếu cần giữ ZoneId như \`Asia/Ho_Chi_Minh\`, lưu ZoneId trong thuộc tính/cột riêng; timestamp UTC chỉ lưu thời điểm, không lưu tên vùng.

## 7. Khác biệt timezone giữa PostgreSQL và MySQL

### 7.1. PostgreSQL

PostgreSQL có hai kiểu thường gặp:

- \`timestamp without time zone\`: ngày giờ tường, không giữ timezone. Nếu truyền literal có timezone vào kiểu này, phần timezone có thể bị bỏ qua.
- \`timestamp with time zone\` (\`timestamptz\`): PostgreSQL chuyển input về UTC để lưu; khi đọc/hiển thị, giá trị được chuyển sang timezone của session. PostgreSQL không lưu lại tên zone hoặc offset ban đầu.

Kiểm tra session timezone:

```sql
SHOW TimeZone;
SELECT CURRENT_TIMESTAMP;
```

Có thể đặt mặc định timezone cho role:

```sql
ALTER ROLE customer_app SET TimeZone TO 'UTC';
```

Cần tạo connection mới để session nhận default mới. \`SET LOCAL\` chỉ có hiệu lực trong transaction hiện tại; \`SET\` ở session ảnh hưởng connection đó cho tới khi đổi lại hoặc connection đóng. Với pool, không tùy tiện chạy \`SET\` rồi trả connection về pool mà không reset session state.

### 7.2. MySQL

MySQL phân biệt:
- \`TIMESTAMP\`: server chuyển giá trị từ session timezone sang UTC khi lưu và từ UTC về session timezone khi đọc.
- \`DATETIME\`: lưu ngày giờ tường, không tự chuyển đổi timezone như TIMESTAMP.

Kiểm tra timezone:

```sql
SELECT
    @@global.time_zone,
    @@session.time_zone,
    NOW(),
    UTC_TIMESTAMP();
```

MySQL Connector/J từ 8.0.23 có các thuộc tính liên quan instant:
- \`connectionTimeZone\`: timezone dùng khi driver cần chuyển đổi.
- \`forceConnectionTimeZoneToSession\`: yêu cầu driver đặt session timezone theo connectionTimeZone.
- \`preserveInstants\`: yêu cầu driver cố gắng giữ nguyên instant khi lưu/đọc các kiểu tương ứng.

Ví dụ URL khi hệ thống thống nhất session UTC:

```properties
spring.datasource.url=jdbc:mysql://db.internal:3306/customer_db?connectionTimeZone=UTC&forceConnectionTimeZoneToSession=true&preserveInstants=true
```

Cấu hình này làm thay đổi timezone session; các hàm \`NOW()\`, \`CURTIME()\` và \`CURDATE()\` chịu ảnh hưởng. Chỉ áp dụng khi semantics của ứng dụng muốn session UTC và đã kiểm tra driver/server version. Không dùng URL này như một chuỗi thần chú cho mọi schema.

### 7.3. Chọn cột phù hợp

| Nghiệp vụ | Java type thường phù hợp | Database type cần cân nhắc |
|---|---|---|
| Ngày sinh | \`LocalDate\` | DATE |
| Giờ mở cửa | \`LocalTime\` | TIME |
| Lịch hẹn theo giờ địa phương | \`LocalDateTime\` + ZoneId riêng | timestamp without time zone / DATETIME |
| Thời điểm tạo đơn | \`Instant\` | PostgreSQL timestamptz; MySQL TIMESTAMP hoặc quy ước UTC với DATETIME |
| Lịch định kỳ theo vùng | LocalDateTime + IANA ZoneId | Cột local datetime và zone ID |

Không chọn cột chỉ dựa vào tên Java type. Kiểm tra Hibernate mapping, JDBC driver và semantics của database cụ thể.

## 8. Daylight saving time và precision timestamp

Một số vùng thay đổi offset theo mùa. Khi đồng hồ tiến lên, một khoảng local time có thể không tồn tại; khi đồng hồ lùi lại, một khoảng local time có thể xuất hiện hai lần.

Vì vậy:
- Dùng \`ZoneId\` với tên vùng IANA khi nghiệp vụ cần quy tắc vùng.
- Lưu Instant cho event đã xảy ra.
- Lưu ZoneId nếu cần tái hiện lịch theo vùng.
- Không tự cộng/trừ số giờ cố định để đổi timezone.
- Kiểm thử thời điểm trước/sau chuyển DST nếu ứng dụng phục vụ vùng có DST.

Ngoài timezone, database có giới hạn precision. Java có thể giữ nanoseconds trong \`Instant\`, trong khi database/driver có thể lưu microseconds hoặc precision khác. Nếu so sánh chính xác, chuẩn hóa precision hoặc so sánh theo độ chính xác schema hỗ trợ.

Một test round-trip nên kiểm tra:
1. Giá trị Java trước khi persist.
2. Giá trị sau flush.
3. Giá trị đọc lại trong persistence context mới.
4. Kết quả khi JVM/session timezone khác nhau theo cấu hình hỗ trợ.
5. Hành vi ở ranh giới ngày và DST.

## 9. Connection pool và HikariCP

### 9.1. Vì sao cần pool?

Tạo JDBC connection mới có chi phí network, authentication và thiết lập session. HikariCP giữ một tập connection để nhiều request mượn/trả lại.

Luồng cơ bản:
1. Spring transaction/data access lấy connection từ pool.
2. Hibernate/JDBC thực thi SQL.
3. Transaction commit/rollback.
4. Connection được trả về pool.
5. Request khác tái sử dụng connection.

Pool không làm query chậm trở thành query nhanh. Nó giảm chi phí mở kết nối và giới hạn số session đồng thời tới database.

### 9.2. Các thuộc tính Hikari thường dùng

| Thuộc tính | Ý nghĩa |
|---|---|
| \`maximum-pool-size\` | Tổng connection tối đa, gồm idle và in-use |
| \`minimum-idle\` | Số connection idle tối thiểu muốn duy trì |
| \`connection-timeout\` | Thời gian chờ lấy connection từ pool |
| \`idle-timeout\` | Thời gian connection idle có thể bị loại bỏ khi pool co giãn |
| \`max-lifetime\` | Tuổi thọ tối đa trước khi retire |
| \`keepalive-time\` | Chu kỳ giữ sống/kiểm tra connection idle |
| \`validation-timeout\` | Giới hạn thời gian kiểm tra connection |
| \`leak-detection-threshold\` | Ngưỡng cảnh báo connection bị giữ quá lâu |

Các giá trị thời gian trong Spring Boot YAML có thể dùng \`ms\`, \`s\`, \`m\`. Hikari nội bộ cấu hình thời gian theo milliseconds.

### 9.3. Ví dụ cấu hình pool

```yaml
spring:
  datasource:
    hikari:
      pool-name: CustomerPool
      maximum-pool-size: 12
      minimum-idle: 2
      connection-timeout: 3s
      validation-timeout: 1s
      idle-timeout: 10m
      max-lifetime: 25m
```

Đây chỉ là cấu hình minh họa. Không sao chép số 12, 2 hoặc 3 giây vào production nếu chưa đo tải và giới hạn database.

Hikari có default riêng cho nhiều thuộc tính. Ví dụ connectionTimeout thường là 30 giây, maxLifetime thường là 30 phút và maximumPoolSize mặc định thường là 10; kiểm tra version HikariCP thực tế thay vì phụ thuộc vào trí nhớ hoặc giá trị mặc định cũ.

### 9.4. Chọn maximumPoolSize

Tổng connection ứng dụng có thể mở gần bằng:

\`số instance ứng dụng × maximumPoolSize mỗi instance\`

Ví dụ 5 pod, mỗi pod pool tối đa 12 connection, có thể tạo tới 60 connection từ service này, chưa kể worker, migration, admin tool và các service khác.

Khi chọn pool size, cần biết:
- Giới hạn \`max_connections\` của database.
- Số replica/pod có thể scale tối đa.
- Connection dành cho ứng dụng khác, monitoring và DBA.
- Khả năng xử lý đồng thời của CPU/I/O database.
- Thời gian query và transaction.
- Số thread có thể đồng thời cần connection.

Pool quá nhỏ làm request chờ connection. Pool quá lớn làm database chịu quá nhiều session, tăng context switching, lock contention và memory usage. Tăng pool không phải cách mặc định để sửa latency.

### 9.5. minimumIdle và idleTimeout

Nếu \`minimum-idle\` nhỏ hơn \`maximum-pool-size\`, pool có thể co giãn và \`idle-timeout\` có thể loại bỏ connection idle vượt mức tối thiểu.

Nếu muốn pool cố định, có thể bỏ cấu hình minimumIdle để Hikari dùng maximumPoolSize làm kích thước pool mục tiêu theo hành vi mặc định. Khi pool hoạt động cố định, idleTimeout không có tác dụng co pool như trường hợp elastic.

### 9.6. maxLifetime và keepalive

Đặt \`max-lifetime\` thấp hơn giới hạn tuổi thọ connection của database proxy/load balancer/firewall nếu hạ tầng có giới hạn đó. Hikari retire connection trước khi tầng bên ngoài chủ động đóng nó.

\`keepalive-time\` chỉ tác động tới connection idle và phải nhỏ hơn maxLifetime theo quy tắc Hikari. Chỉ bật khi có bằng chứng network đóng idle connection; keepalive quá thường xuyên tạo thêm traffic.

### 9.7. Leak detection

\`leak-detection-threshold\` giúp phát hiện connection được mượn quá lâu. Cảnh báo không luôn có nghĩa code làm rò connection: transaction hợp lệ hoặc query chậm cũng có thể giữ connection lâu.

Bật tạm thời khi điều tra, đọc stack trace và xác định call site. Đừng dùng ngưỡng quá thấp trong production vì có thể tạo cảnh báo nhiễu.

## 10. Timeout: mỗi tầng có một mục đích

Timeout cần được thiết kế theo chuỗi request. Một request có thể chờ connection, mở socket, chạy SQL, chờ lock và chờ downstream. Một timeout ở một tầng không tự động giới hạn tất cả các tầng khác.

| Timeout | Giới hạn điều gì? | Nơi cấu hình |
|---|---|---|
| Pool acquisition | Chờ connection rảnh trong Hikari | \`spring.datasource.hikari.connection-timeout\` |
| Driver connect/login | Mở kết nối mạng và đăng nhập database | JDBC driver property |
| Socket read | Chờ dữ liệu đọc từ socket | JDBC driver property |
| Query/statement | Thời gian thực thi một SQL | JPA/JDBC/provider/database |
| Lock wait | Thời gian chờ lock | Database |
| Transaction | Thời gian transaction theo transaction manager | \`@Transactional(timeout=...)\` |
| HTTP/request deadline | Tổng thời gian request được phép chạy | Web server/gateway/client |

Không đặt tất cả bằng cùng một số và cho rằng ứng dụng sẽ có deadline nhất quán. Hãy thiết kế thứ tự timeout theo ngân sách request và hành vi rollback/retry.

## 11. Pool acquisition timeout

Hikari \`connection-timeout\` là thời gian thread chờ một connection rảnh khi pool đã hết connection. Nó không phải timeout mở TCP connection tới database và cũng không phải timeout query.

```yaml
spring:
  datasource:
    hikari:
      maximum-pool-size: 12
      connection-timeout: 3s
```

Nếu 12 connection đều đang được giữ và không có connection nào trả về trong thời gian chờ, Hikari ném lỗi lấy connection. Cần điều tra:
- Transaction giữ connection quá lâu.
- Query chậm hoặc lock wait.
- Connection không được trả về pool.
- Pool nhỏ hơn concurrency thực tế.
- N+1 làm request giữ connection qua nhiều lần query.
- Database đang quá tải.

Không tăng connection-timeout vô hạn để che tình trạng pool cạn; điều đó chỉ làm request xếp hàng lâu hơn.

## 12. Driver connect timeout và socket timeout

Driver timeout là cấu hình riêng theo vendor/version.

### 12.1. PostgreSQL JDBC

pgJDBC có \`connectTimeout\` và \`socketTimeout\`; đơn vị là giây. \`connectTimeout\` giới hạn thời gian mở socket kết nối, còn \`socketTimeout\` giới hạn thời gian chờ đọc dữ liệu từ socket.

```properties
spring.datasource.url=jdbc:postgresql://db.internal:5432/customer_db?connectTimeout=5&socketTimeout=30
```

\`socketTimeout\` là giới hạn tầng socket. Khi hết hạn, driver có thể đóng connection; nó không giống query timeout có semantics hủy statement/transaction được kiểm soát. Dùng giá trị dựa trên SLA và kiểm tra khả năng phục hồi connection.

### 12.2. MySQL Connector/J

MySQL Connector/J có \`connectTimeout\` và \`socketTimeout\`; các giá trị networking này tính bằng milliseconds theo tài liệu Connector/J.

```properties
spring.datasource.url=jdbc:mysql://db.internal:3306/customer_db?connectTimeout=5000&socketTimeout=30000
```

Không sao chép đơn vị của PostgreSQL URL sang MySQL. Với driver khác, hãy đọc tài liệu chính thức của đúng version.

### 12.3. Đừng nhầm driver timeout với Hikari timeout

| Trường hợp | Cấu hình cần xem |
|---|---|
| Pool không còn connection rảnh | Hikari connectionTimeout |
| Mạng không mở được kết nối tới DB | Driver connectTimeout/loginTimeout |
| Socket không nhận được dữ liệu | Driver socketTimeout |
| SQL chạy quá lâu | Statement/query timeout |
| SQL chờ row/table lock | Database lock timeout |
| Transaction giữ connection lâu | Transaction boundary và transaction timeout |

## 13. Query timeout trong JPA và Spring Data JPA

### 13.1. Jakarta Persistence query timeout hint

Jakarta Persistence định nghĩa hint \`jakarta.persistence.query.timeout\`. Đơn vị là milliseconds.

```java
public interface OrderRepository
        extends JpaRepository<Order, Long> {

    @Query("select o from Order o where o.status = :status")
    @QueryHints(
        value = @QueryHint(
            name = "jakarta.persistence.query.timeout",
            value = "3000"
        )
    )
    List<Order> findByStatusWithTimeout(
        @Param("status") OrderStatus status
    );
}
```

Import:

```java
import jakarta.persistence.QueryHint;
import org.springframework.data.jpa.repository.QueryHints;
```

Đây là query hint; provider/driver/database có thể khác nhau về mức độ hỗ trợ. Không giả định hint luôn hủy SQL ngay tại đúng 3 giây. Hãy kiểm thử trên database production-like và quan sát exception thực tế.

### 13.2. Query timeout với EntityManager

```java
TypedQuery<Order> query = entityManager.createQuery(
    "select o from Order o where o.status = :status",
    Order.class
);

query.setParameter("status", OrderStatus.PENDING);
query.setHint("jakarta.persistence.query.timeout", 3000);

List<Order> result = query.getResultList();
```

Giá trị là milliseconds. Đây là hint cấp query, không đặt timeout cho toàn bộ request.

### 13.3. Spring JDBC template khác JPA query

Spring Boot có thuộc tính \`spring.jdbc.template.query-timeout\` cho JdbcTemplate. Thuộc tính này không phải cấu hình chung cho mọi query Hibernate/JPA. Khi ứng dụng dùng cả JdbcTemplate và Spring Data JPA, cần đặt timeout cho từng data access path.

## 14. Transaction timeout và lock timeout

### 14.1. Spring @Transactional timeout

```java
@Service
public class OrderService {

    @Transactional(timeout = 5)
    public void processOrder(Long orderId) {
        // Load, validate và cập nhật dữ liệu trong transaction.
    }
}
```

Giá trị timeout của Spring \`@Transactional\` tính bằng giây. Khả năng áp dụng phụ thuộc transaction manager và resource integration. Nó không bảo đảm mọi driver hủy một SQL đang chạy đúng thời điểm; vẫn cần query/statement timeout và database-side limit khi use case yêu cầu.

Không giữ transaction mở trong khi gọi HTTP service chậm, chờ người dùng hoặc thực hiện công việc không liên quan database. Transaction dài giữ connection và lock lâu hơn.

### 14.2. PostgreSQL statement_timeout và lock_timeout

PostgreSQL có các timeout riêng:
- \`statement_timeout\`: giới hạn thời gian một statement chạy.
- \`lock_timeout\`: giới hạn thời gian chờ lock.
- \`idle_in_transaction_session_timeout\`: kết thúc session idle trong transaction quá lâu.

```sql
BEGIN;
SET LOCAL statement_timeout = '5s';
SET LOCAL lock_timeout = '1s';

-- Các câu SQL của transaction

COMMIT;
```

\`lock_timeout\` chỉ giới hạn thời gian chờ lock; nếu \`statement_timeout\` nhỏ hơn, statement timeout có thể xảy ra trước. \`SET LOCAL\` chỉ áp dụng trong transaction hiện tại.

Tránh đặt \`statement_timeout\` quá thấp ở cấp toàn server nếu có nhiều workload khác nhau. Có thể cấu hình theo role/database hoặc transaction. Với pool, hiểu rõ scope của SET và reset session state.

### 14.3. MySQL execution và lock timeout

MySQL có các giới hạn khác:
- \`max_execution_time\` (milliseconds) có thể giới hạn SELECT.
- Optimizer hint \`MAX_EXECUTION_TIME(N)\` có thể áp dụng cho một SELECT.
- \`innodb_lock_wait_timeout\` giới hạn thời gian chờ InnoDB row lock, tính bằng giây.

Kiểm tra session:

```sql
SELECT
    @@session.max_execution_time,
    @@session.innodb_lock_wait_timeout;
```

Không coi \`innodb_lock_wait_timeout\` là query timeout tổng quát. Nó chỉ xử lý thời gian chờ lock của InnoDB. Cú pháp và phạm vi thay đổi theo MySQL version; xác minh trước khi dùng production.

## 15. Ngân sách timeout theo request

Giả sử endpoint có deadline 8 giây. Một thiết kế minh họa có thể dành:
- Tối đa 0.5 giây chờ pool connection.
- Tối đa 1 giây để mở kết nối mới khi cần.
- Tối đa 4 giây cho query/lock theo chính sách database.
- Phần còn lại cho business logic, serialization và response.

Các con số chỉ minh họa. Driver connect timeout không nhất thiết xảy ra trên mỗi request nếu pool đã có connection.

Nguyên tắc:
1. Timeout tầng dưới không nên khiến request vượt deadline tầng trên.
2. Query timeout nên đủ thấp để giải phóng tài nguyên khi query bất thường.
3. Lock timeout thường ngắn hơn statement timeout nếu cần fail nhanh khi tranh chấp.
4. Transaction không nên kéo dài chỉ vì client đang chờ response.
5. Retry chỉ áp dụng khi lỗi có thể retry và operation an toàn/idempotent.
6. Khi timeout, xác định statement đã rollback hay transaction đã bị đánh dấu rollback-only.

Timeout không thay thế cancellation end-to-end. Nếu client disconnect, SQL có thể vẫn tiếp tục nếu driver/provider/database không nhận và thực thi cancellation.

## 16. Cấu hình theo môi trường bằng Spring Profiles

### 16.1. Cấu hình chung

File \`application.yml\` chứa các thuộc tính chung:

```yaml
spring:
  jpa:
    hibernate:
      ddl-auto: validate
    properties:
      hibernate:
        jdbc:
          time_zone: UTC

  datasource:
    hikari:
      pool-name: CustomerPool
      validation-timeout: 1s
      max-lifetime: 25m
```

Cấu hình URL, username, password và pool size được đưa vào profile/secret phù hợp. Với schema được quản lý bởi Flyway/Liquibase, \`ddl-auto: validate\` giúp kiểm tra mapping thay vì để Hibernate tự tạo schema production.

### 16.2. Local profile

File \`application-local.yml\`:

```yaml
spring:
  datasource:
    url: jdbc:postgresql://localhost:5432/customer_local
    username: local_app
    password: ${LOCAL_DB_PASSWORD}
    hikari:
      maximum-pool-size: 4
      minimum-idle: 1
      connection-timeout: 5s
      idle-timeout: 5m
```

Local có thể dùng container hoặc database riêng. Không nhất thiết mô phỏng số connection production trên laptop.

### 16.3. Production profile

File \`application-prod.yml\`:

```yaml
spring:
  datasource:
    url: ${DB_URL}
    username: ${DB_USERNAME}
    password: ${DB_PASSWORD}
    hikari:
      maximum-pool-size: ${DB_POOL_MAX}
      minimum-idle: ${DB_POOL_MIN}
      connection-timeout: 2s
      idle-timeout: 10m
      max-lifetime: 25m
      validation-timeout: 1s
```

Các giá trị DB_URL, DB_USERNAME, DB_PASSWORD, DB_POOL_MAX và DB_POOL_MIN được cấp từ môi trường triển khai hoặc secret manager. Nếu thiếu biến bắt buộc, ứng dụng nên fail fast với thông báo cấu hình rõ ràng thay vì âm thầm dùng database mặc định.

Kích hoạt profile:

```bash
java -jar app.jar --spring.profiles.active=prod
```

Hoặc qua biến môi trường:

```bash
SPRING_PROFILES_ACTIVE=prod
```

Không đặt password thật trong file profile được commit. Có thể dùng Kubernetes Secret, Vault, cloud secret manager hoặc cơ chế bảo mật của nền tảng.

### 16.4. Externalized configuration và thứ tự ưu tiên

Spring Boot có thể nhận cấu hình từ:
- application.yml và application-{profile}.yml.
- Biến môi trường.
- Java system properties.
- Command-line arguments.
- Config server hoặc config import.
- Secret/config store của nền tảng.

Giá trị cuối cùng phụ thuộc property source precedence. Khi nghi ngờ ứng dụng dùng sai URL/pool size, kiểm tra active profile và property source thực tế qua diagnostics được bảo vệ; không log credential.

### 16.5. Không phân nhánh code theo môi trường

Tránh viết điều kiện \`if (isProduction)\` để chọn dialect hoặc pool trong code. Cấu hình database nên đi qua Spring Environment/ConfigurationProperties. Logic nghiệp vụ không nên phụ thuộc tên profile.

Nếu database vendor thật sự khác nhau giữa các triển khai, cấu hình driver/dialect/schema tương ứng ở configuration boundary và chạy integration test cho từng vendor.

## 17. Cấu hình có kiểu bằng @ConfigurationProperties

Khi cần nhiều tham số liên quan, có thể gom chúng thành cấu hình có kiểu để validate:

```java
@ConfigurationProperties(prefix = "app.database")
@Validated
public record DatabaseRuntimeProperties(
    @Min(1) int expectedInstances,
    @Min(1) int poolMax,
    @NotBlank String referenceTimeZone
) {
}
```

Đăng ký properties:

```java
@Configuration
@EnableConfigurationProperties(DatabaseRuntimeProperties.class)
public class DatabaseConfiguration {
}
```

Ví dụ YAML:

```yaml
app:
  database:
    expected-instances: 4
    pool-max: 10
    reference-time-zone: UTC
```

Đây là cấu hình riêng của ứng dụng, không tự thay thế \`spring.datasource.hikari.*\` hoặc \`spring.jpa.properties.hibernate.*\`. Có thể dùng để kiểm tra consistency, ví dụ tổng pool theo số instance không vượt ngân sách connection được cấp.

## 18. Nhiều DataSource hoặc nhiều database vendor

Nếu ứng dụng có nhiều database, mỗi DataSource cần cấu hình riêng:
- JDBC URL và driver phù hợp.
- Connection pool riêng.
- EntityManagerFactory riêng.
- TransactionManager riêng.
- Entity/repository package scan tương ứng.
- Dialect phù hợp với database của persistence unit.

Không dùng một Hikari pool chung cho hai database khác vendor. Không gắn cùng một EntityManagerFactory vào hai DataSource khác nhau.

```text
SalesDataSource   -> SalesEntityManagerFactory   -> SalesTransactionManager
BillingDataSource -> BillingEntityManagerFactory -> BillingTransactionManager
```

Repository phải được gắn đúng EntityManagerFactory/transaction manager. Nếu một transaction cần cập nhật hai database, transaction local của từng DataSource không tự tạo distributed atomic transaction; cần thiết kế saga/outbox hoặc JTA phù hợp.

## 19. Quan sát pool, query và timeout

Nên theo dõi:
- Active, idle, pending và maximum connections của Hikari.
- Thời gian chờ lấy connection p50/p95/p99.
- Số lần connection acquisition timeout.
- Query duration và số query chậm.
- Transaction duration và rollback.
- Lock wait, deadlock và số session database.
- Connection creation/close rate.
- Số request đang chờ và thời gian response.

Spring Boot Actuator/Micrometer có thể xuất Hikari metrics khi datasource/pool được instrument. Tên metric thường bắt đầu bằng \`hikaricp.connections\`; tên tag/metric cụ thể phụ thuộc version và registry.

| Quan sát | Khả năng cần điều tra |
|---|---|
| Active luôn bằng max, pending tăng | Pool cạn hoặc transaction/query giữ connection lâu |
| Idle nhiều nhưng request vẫn chậm | Bottleneck ở query, network hoặc application |
| Connection timeout tăng đột biến | Database/network không đáp ứng hoặc pool capacity thiếu |
| Query latency cao nhưng pool chưa đầy | SQL/index/lock/database workload |
| Connection bị đóng định kỳ | maxLifetime không phù hợp proxy/server timeout |
| Timeout chỉ ở một profile | URL, network, pool hoặc server setting khác môi trường |

Metrics không thay thế database slow query log và execution plan. Kết hợp số liệu ứng dụng lẫn database để tìm bottleneck.

## 20. Kiểm thử cấu hình database theo môi trường

### 20.1. Test với đúng database vendor

Dùng Testcontainers hoặc database service tương ứng để kiểm tra PostgreSQL/MySQL thật. Không dùng H2 làm bằng chứng cho dialect, native SQL hoặc kiểu dữ liệu vendor-specific.

Test cần xác minh:
- ApplicationContext khởi động với JDBC URL/profile đúng.
- Hibernate chọn dialect phù hợp.
- Migration chạy được.
- Repository query và native SQL thực thi.
- Timezone round-trip giữ đúng instant/local time theo semantics.
- Precision timestamp phù hợp.
- Pool lấy/trả connection đúng.
- Query timeout/lock timeout có hiệu lực theo provider/driver/database.
- Transaction rollback và isolation đúng mong đợi.

### 20.2. Test timezone có chủ đích

Tạo test với:
- Instant ở UTC.
- OffsetDateTime có offset khác UTC.
- LocalDateTime không có timezone.
- Thời điểm sát ranh giới ngày.
- Giá trị có fractional seconds.
- Vùng có DST nếu ứng dụng hỗ trợ.
- Session timezone đã biết.

Sau khi persist, flush, clear và đọc lại trong transaction mới. So sánh theo semantics mong muốn, không so sánh chuỗi hiển thị nếu database chuyển timestamp theo session timezone.

### 20.3. Test pool và timeout riêng

Để kiểm tra pool timeout, tạo concurrency có kiểm soát và giữ connection trong test transaction lâu hơn acquisition timeout. Không chạy test này song song với các test khác dùng cùng pool vì có thể gây flaky.

Để kiểm tra query timeout, dùng query có thời gian thực thi xác định trên database mục tiêu hoặc lock có kiểm soát. Kiểm tra exception và trạng thái transaction sau timeout. Đừng dựa vào \`Thread.sleep()\` rồi kết luận database query đã bị hủy.

## 21. Troubleshooting

| Triệu chứng | Nguyên nhân thường gặp | Hướng xử lý |
|---|---|---|
| Hibernate không xác định được dialect | Không lấy được JDBC metadata, thiếu driver hoặc DB chưa sẵn sàng | Kiểm tra URL, driver, network và startup readiness |
| SQL chỉ lỗi trên production | Dialect/native SQL hoặc database version khác | Xác nhận vendor/version và chạy test trên engine thật |
| Timestamp lệch vài giờ | JVM, Hibernate, JDBC session hoặc DB timezone không thống nhất | Kiểm tra cả bốn lớp và kiểu cột |
| LocalDateTime bị đổi giờ | Dùng kiểu local như instant hoặc mapping/column semantics không khớp | Xác định domain semantics rồi chọn Java/SQL type |
| MySQL NOW() khác mong đợi | Session timezone bị driver/config thay đổi | Kiểm tra \`@@session.time_zone\` và Connector/J options |
| Connection timeout từ Hikari | Pool hết connection hoặc connection bị giữ lâu | Kiểm tra active/pending, transaction duration và query |
| Connect timeout | DNS, route, firewall, TLS hoặc database không accept connection | Kiểm tra driver connect setting và network |
| Socket timeout | Database/network không trả dữ liệu trong thời gian cấu hình | Xem slow query, DB load và driver socket setting |
| QueryTimeoutException | SQL hoặc lock vượt giới hạn | Xem query hint, DB statement/lock timeout và execution plan |
| Lock wait timeout | Transaction khác giữ lock | Kiểm tra lock graph, transaction duration và thứ tự cập nhật |
| Pool bị đóng connection định kỳ | maxLifetime lớn hơn giới hạn proxy/server hoặc network idle timeout | Điều chỉnh lifetime/keepalive theo hạ tầng |
| Chỉ lỗi khi scale nhiều pod | Tổng pool vượt ngân sách connection DB | Tính tổng pool trên toàn bộ replica và các client khác |

## 22. Các lỗi cấu hình phổ biến

1. **Hard-code dialect:** khai báo PostgreSQL dialect rồi dùng URL MySQL ở môi trường khác.
2. **Dùng timezone JVM làm chuẩn duy nhất:** không kiểm tra session timezone hoặc semantics của cột.
3. **Lưu lịch địa phương như instant:** chuyển giờ hẹn local thành UTC mà không biết ZoneId.
4. **Tăng pool để sửa query chậm:** database nhận thêm concurrency nhưng SQL vẫn chậm.
5. **Đặt pool bằng số thread:** mọi thread không nhất thiết cần connection đồng thời; database có giới hạn riêng.
6. **Dùng connectionTimeout như queryTimeout:** request có thể vẫn chạy SQL lâu sau khi đã lấy connection.
7. **Dùng socketTimeout quá thấp:** driver đóng connection trong query bình thường hoặc lúc database tạm chậm.
8. **Đặt timeout database toàn cục thiếu phân tích:** workload khác nhau có SLA khác nhau.
9. **Đổi session timezone mà không reset pool:** connection trả về pool có thể giữ session state ngoài dự kiến.
10. **Bật leak detection quá thấp:** log cảnh báo connection hợp lệ đang chạy query dài.
11. **Không test migration trên engine production:** schema có thể chỉ hoạt động với H2.
12. **Commit credential trong YAML:** làm lộ thông tin truy cập database.

## 23. Checklist trước khi triển khai

### Dialect và driver
- [ ] JDBC URL trỏ đúng vendor, host, port và database.
- [ ] JDBC driver đúng version có trong runtime classpath.
- [ ] Hibernate tự nhận diện dialect từ metadata nếu không có lý do override.
- [ ] Nếu override dialect, class phù hợp Hibernate major version và database thực tế.
- [ ] Migration/schema validation chạy trên database mục tiêu.

### Timezone
- [ ] Đã phân biệt ngày lịch, giờ địa phương và instant.
- [ ] Java type phù hợp semantics dữ liệu.
- [ ] JVM/Hibernate JDBC timezone có quy ước rõ.
- [ ] Database session timezone được kiểm tra.
- [ ] Đã hiểu timestamptz/timestamp của PostgreSQL và TIMESTAMP/DATETIME của MySQL.
- [ ] ZoneId được lưu riêng nếu cần tái hiện lịch theo vùng.
- [ ] Có test round-trip, precision và DST nếu liên quan.

### Pool
- [ ] maximumPoolSize phù hợp ngân sách connection toàn hệ thống.
- [ ] Đã tính số replica tối đa và các client database khác.
- [ ] connectionTimeout không che giấu pool exhaustion.
- [ ] maxLifetime phù hợp proxy/server timeout.
- [ ] idleTimeout/keepalive được cấu hình theo chế độ pool.
- [ ] Có metrics active/idle/pending và acquisition latency.
- [ ] Leak detection chỉ bật với ngưỡng có chủ đích.

### Timeout
- [ ] Pool acquisition timeout được phân biệt với driver connect timeout.
- [ ] Socket timeout được phân biệt với SQL timeout.
- [ ] Query/statement timeout được kiểm tra trên provider và driver thật.
- [ ] Lock timeout và statement timeout có mục đích riêng.
- [ ] Transaction timeout phù hợp transaction manager.
- [ ] Timeout các tầng phù hợp request deadline và retry policy.

### Environment
- [ ] Local/test/staging/prod có cấu hình URL và pool riêng.
- [ ] Secret không nằm trong Git hoặc log.
- [ ] Active profile và property source được xác nhận khi triển khai.
- [ ] CI có integration test trên đúng database vendor/version.
- [ ] Nhiều DataSource có EntityManagerFactory và TransactionManager riêng.

## 24. Tài liệu tham khảo chính thức

- [Spring Boot — Common Application Properties](https://docs.spring.io/spring-boot/appendix/application-properties/): datasource, HikariCP, JPA database platform và cấu hình pool.
- [Hibernate ORM User Guide — Time zone handling](https://docs.jboss.org/hibernate/orm/current/userguide/html_single/Hibernate_User_Guide.html): \`hibernate.jdbc.time_zone\` và chiến lược lưu timezone-aware values.
- [Hibernate ORM — Dialect configuration](https://github.com/hibernate/hibernate-orm/blob/main/documentation/src/main/asciidoc/introduction/Configuration.adoc): tự nhận diện dialect từ JDBC metadata và trường hợp cần override.
- [HikariCP — Configuration](https://github.com/brettwooldridge/HikariCP/wiki/Configuration): connectionTimeout, idleTimeout, maxLifetime, pool size và validation.
- [PostgreSQL — Date/Time Types](https://www.postgresql.org/docs/current/datatype-datetime.html): timestamp with/without time zone.
- [PostgreSQL — Client Connection Defaults](https://www.postgresql.org/docs/current/runtime-config-client.html): statement_timeout, lock_timeout và idle transaction timeout.
- [MySQL Connector/J — Datetime types processing](https://dev.mysql.com/doc/connector-j/en/connector-j-connp-props-datetime-types-processing.html): connectionTimeZone, preserveInstants và forceConnectionTimeZoneToSession.
- [MySQL — Date and Time Functions](https://dev.mysql.com/doc/refman/8.4/en/date-and-time-functions.html): session timezone và các hàm thời gian.
- [Jakarta Persistence — Query API](https://jakartaee.github.io/persistence/latest-nightly/api/jakarta.persistence/jakarta/persistence/Query.html): query timeout hint tính bằng milliseconds.

## 25. Kết luận

Cấu hình database theo môi trường cần giữ nhất quán giữa JDBC URL, driver, Hibernate dialect, timezone, connection pool và timeout. Hibernate hiện đại thường tự nhận diện dialect qua JDBC metadata; chỉ override khi có yêu cầu kỹ thuật rõ ràng. Đổi dialect không thay thế driver hoặc database vendor.

Với thời gian, hãy phân biệt LocalDateTime dùng cho giờ địa phương và Instant dùng cho thời điểm tuyệt đối. UTC là quy ước hữu ích cho instant, nhưng phải đồng bộ JVM, Hibernate JDBC binding và database session. PostgreSQL timestamptz không giữ lại tên timezone ban đầu; MySQL TIMESTAMP chuyển đổi theo session timezone trong khi DATETIME giữ giá trị wall-clock. Nếu cần lưu ZoneId, hãy lưu riêng.

HikariCP giới hạn và tái sử dụng connection. Chọn pool size theo ngân sách toàn hệ thống và số replica; theo dõi active, idle, pending và thời gian chờ. Timeout phải được chia theo tầng: chờ pool, mở kết nối, đọc socket, thực thi query, chờ lock, transaction và HTTP request. Một giá trị không thay thế tất cả các giới hạn còn lại.

Cuối cùng, đưa URL/credential/pool/timezone/timeout vào external configuration, quản lý secret an toàn, chạy migration và integration test trên đúng database vendor/version. Quan sát metrics cùng log database để điều chỉnh theo tải thực tế thay vì sao chép một cấu hình cố định cho mọi môi trường.