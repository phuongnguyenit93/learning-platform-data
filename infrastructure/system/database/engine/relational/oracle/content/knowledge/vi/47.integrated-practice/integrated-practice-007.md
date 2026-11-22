# Kết nối Java/Spring Boot, quản lý giao dịch và ánh xạ kiểu dữ liệu

## 1. Bức tranh tổng thể

Ứng dụng Java kết nối Oracle Database thường đi qua các lớp sau:

```text
REST Controller / Message Consumer
              |
              v
       Service Layer
       @Transactional
              |
       +------+------+
       |             |
       v             v
 Spring Data JPA   JdbcTemplate
       |             |
       v             v
 Hibernate ORM   Spring JDBC
       |             |
       +------+------+
              |
              v
         DataSource
       (HikariCP/UCP)
              |
              v
       Oracle JDBC Driver
              |
              v
        Oracle Database
```

Mỗi thành phần có một trách nhiệm riêng:

- **Oracle JDBC driver** thực hiện giao tiếp JDBC với Oracle, gửi SQL, bind parameter và chuyển kết quả về Java.
- **DataSource/connection pool** quản lý physical connection để ứng dụng tái sử dụng, giới hạn số kết nối và kiểm soát thời gian chờ.
- **Hibernate/JPA** ánh xạ entity, sinh SQL và quản lý persistence context.
- **Spring transaction manager** điều phối ranh giới transaction cho JPA/JDBC.
- **Service layer** xác định một thao tác nghiệp vụ gồm những thay đổi dữ liệu nào và khi nào commit/rollback.

Khi chỉ làm việc với một Oracle Database, một local transaction trên JDBC connection thường là đủ. JTA/XA chỉ cần khi một nghiệp vụ phải commit/rollback đồng bộ trên nhiều resource manager độc lập, chẳng hạn Oracle và một JMS broker có hỗ trợ XA.

## 2. Chuẩn bị Oracle Database và thông tin kết nối

### 2.1. Tạo user và schema cho ứng dụng

Ứng dụng nên dùng database account riêng, có quyền tối thiểu trên các object cần thiết. Không dùng `SYS`, `SYSTEM` hoặc tài khoản DBA làm runtime account.

Ví dụ DBA tạo tablespace/user:

```sql
CREATE TABLESPACE app_data
  DATAFILE '/u02/oradata/DB/app_data01.dbf'
  SIZE 1G
  AUTOEXTEND ON NEXT 256M MAXSIZE 10G;

CREATE USER app_user IDENTIFIED BY "replace-with-secret"
  DEFAULT TABLESPACE app_data
  TEMPORARY TABLESPACE temp
  QUOTA 2G ON app_data;

GRANT CREATE SESSION TO app_user;
```

Đường dẫn và dung lượng chỉ là ví dụ cho filesystem; môi trường ASM/OMF sẽ có cách khai báo khác. Trong production, quản lý password qua secret manager hoặc cơ chế credential của nền tảng, không ghi password thật trong script được commit.

Nếu schema được tạo bởi Flyway/Liquibase, tài khoản migration có thể cần quyền DDL rộng hơn runtime account. Nên tách tài khoản migration/deployment khỏi tài khoản ứng dụng chỉ đọc/ghi dữ liệu.

### 2.2. Service name và SID trong JDBC URL

Oracle Thin driver kết nối qua TCP mà không cần cài Oracle Client. URL thông dụng dùng service name:

```text
jdbc:oracle:thin:@//db-host.example.com:1521/app_service
```

Trong đó:

- `db-host.example.com`: hostname hoặc địa chỉ máy chủ.
- `1521`: listener port, có thể khác theo môi trường.
- `app_service`: service được listener đăng ký, thường ánh xạ tới database/PDB/service workload.

Một dạng URL legacy dùng SID:

```text
jdbc:oracle:thin:@db-host.example.com:1521:ORCL
```

Không thay service name bằng SID theo cảm tính. Trong môi trường multitenant, ứng dụng thường kết nối qua service của PDB. DBA cung cấp service name và cấu hình failover/load balancing phù hợp.

### 2.3. Kiểm tra kết nối từ SQL*Plus

Trước khi điều tra Spring Boot, xác nhận database service hoạt động bằng công cụ Oracle nếu có:

```bash
sqlplus app_user@//db-host.example.com:1521/app_service
```

Sau khi đăng nhập:

```sql
SELECT sys_context('USERENV', 'DB_NAME') AS db_name,
       sys_context('USERENV', 'SERVICE_NAME') AS service_name,
       sys_context('USERENV', 'CON_NAME') AS container_name
FROM dual;
```

Nếu kết nối bằng SQL*Plus cũng thất bại, kiểm tra DNS/network, listener, service registration, firewall, wallet/TLS và credential trước khi thay đổi code Java.

## 3. Oracle JDBC driver trong Maven và Gradle

### 3.1. Maven dependency

Ví dụ dùng `ojdbc11`:

```xml
<dependency>
    <groupId>com.oracle.database.jdbc</groupId>
    <artifactId>ojdbc11</artifactId>
    <version>${oracle.jdbc.version}</version>
    <scope>runtime</scope>
</dependency>
```

Khai báo property ở `properties` hoặc quản lý version bằng BOM của dự án:

```xml
<properties>
    <oracle.jdbc.version>use-a-supported-version</oracle.jdbc.version>
</properties>
```

`use-a-supported-version` là placeholder, phải thay bằng version cụ thể đã được kiểm tra trong ma trận Oracle JDBC. Không để placeholder này trong build production.

### 3.2. Gradle dependency

```kotlin
dependencies {
    runtimeOnly("com.oracle.database.jdbc:ojdbc11:$oracleJdbcVersion")
}
```

Nếu project dùng Spring Boot dependency management, kiểm tra version driver được resolve cuối cùng. Tránh đưa nhiều bản `ojdbc` vào runtime classpath vì có thể gây xung đột class loading.

### 3.3. Chọn driver theo Java và Oracle release

Không chọn driver chỉ theo số version Oracle Database. Hãy kiểm tra:

- JDK đang chạy ứng dụng.
- Oracle Database release/RU.
- Spring Boot/Hibernate version.
- Application server nếu ứng dụng triển khai trên server.
- Tính năng cần dùng: JDBC, LOB, JSON, TLS, XA, UCP hoặc wallet.

`ojdbc8` và `ojdbc11` nhắm tới các thế hệ Java khác nhau; bản driver cụ thể còn có ma trận hỗ trợ Oracle Database riêng. Driver version không cần có số trùng với database release, nhưng phải nằm trong phạm vi Oracle hỗ trợ.

Driver Thin thường tự đăng ký với `DriverManager`; Spring Boot có thể suy ra driver từ JDBC URL. Khai báo `driver-class-name: oracle.jdbc.OracleDriver` giúp cấu hình rõ ràng nhưng không phải lúc nào cũng bắt buộc.

## 4. Cấu hình Spring Boot DataSource

### 4.1. application.yml cơ bản

```yaml
spring:
  datasource:
    url: jdbc:oracle:thin:@//db-host.example.com:1521/app_service
    username: ${DB_USERNAME}
    password: ${DB_PASSWORD}
    driver-class-name: oracle.jdbc.OracleDriver
    hikari:
      pool-name: app-oracle-pool
      maximum-pool-size: 20
      minimum-idle: 5
      connection-timeout: 30000
      validation-timeout: 5000
      idle-timeout: 600000
      max-lifetime: 1800000
      auto-commit: true

  jpa:
    open-in-view: false
    hibernate:
      ddl-auto: validate
```

Các giá trị pool trong ví dụ chỉ là điểm khởi đầu để minh họa, không phải khuyến nghị chung. Chọn `maximum-pool-size` theo tổng số replica, số service, workload database và capacity của Oracle. Mật khẩu được lấy từ environment/secret store; không commit credential vào repository.

### 4.2. Ý nghĩa các thuộc tính HikariCP

| Thuộc tính | Ý nghĩa |
|---|---|
| `maximum-pool-size` | Số physical connection tối đa của pool |
| `minimum-idle` | Số connection nhàn rỗi tối thiểu pool cố duy trì |
| `connection-timeout` | Thời gian chờ mượn connection trước khi pool báo lỗi, milliseconds |
| `validation-timeout` | Thời gian tối đa kiểm tra connection còn hợp lệ |
| `idle-timeout` | Thời gian connection idle có thể bị loại bỏ khi pool lớn hơn minimum idle |
| `max-lifetime` | Tuổi thọ tối đa của physical connection trước khi pool thay mới |
| `auto-commit` | Trạng thái auto-commit mặc định khi connection ở ngoài transaction do pool quản lý |

Không đặt timeout quá thấp khiến request thất bại khi database chỉ chậm tạm thời; cũng không đặt quá cao khiến request giữ thread và tài nguyên quá lâu. `max-lifetime` nên thấp hơn timeout đóng connection của network/load balancer/database nếu có giới hạn như vậy.

### 4.3. Tính tổng connection trên toàn hệ thống

`maximum-pool-size` áp dụng cho từng pool của từng instance ứng dụng. Nếu có nhiều replica:

\[
Total\ possible\ connections = \sum_{i=1}^{n}(replicas_i \times maxPool_i)
\]

Ví dụ 4 replica, mỗi replica có pool tối đa 20 connection, thì một service có thể tạo tối đa 80 physical connections. Cộng thêm các service khác, batch job, reporting, monitoring và DBA session trước khi so sánh với `PROCESSES`/`SESSIONS` của Oracle.

Pool lớn không tự làm database nhanh hơn. Quá nhiều concurrent SQL có thể làm tăng CPU, I/O, lock contention và latency. Hãy đo throughput và thời gian giữ connection để chọn pool size.

### 4.4. HikariCP hay Oracle UCP?

HikariCP là connection pool phổ biến, nhẹ và tích hợp sẵn trong nhiều ứng dụng Spring Boot. Oracle Universal Connection Pool (UCP) cung cấp các tính năng tích hợp Oracle như một số cơ chế runtime/load balancing, Fast Connection Failover hoặc DRCP tùy cấu hình và phiên bản.

Chọn pool dựa trên yêu cầu thực tế. Dù dùng HikariCP hay UCP, ứng dụng vẫn cần cấu hình đúng Oracle JDBC driver, timeout, connection validation, pool size và transaction manager.

## 5. Cấu hình JPA/Hibernate

### 5.1. Để Hibernate tự nhận diện Oracle

Với Hibernate 6/7, nếu JDBC metadata hoạt động bình thường, thường không cần đặt dialect thủ công. Ví dụ:

```yaml
spring:
  jpa:
    open-in-view: false
    hibernate:
      ddl-auto: validate
    properties:
      hibernate:
        format_sql: true
```

Với Hibernate 5.x hiện đại, Oracle 12c/18c/19c thường dùng `org.hibernate.dialect.Oracle12cDialect`. Hibernate 6/7 dùng `org.hibernate.dialect.OracleDialect`. Kiểm tra class trong đúng artifact và ưu tiên auto-detection nếu không có lý do cần cấu hình rõ.

### 5.2. Dùng schema migration thay cho tự động sửa schema

Trong production, nên dùng Flyway hoặc Liquibase để quản lý DDL có version. Hibernate thường được cấu hình:

```yaml
spring:
  jpa:
    hibernate:
      ddl-auto: validate
```

Các giá trị thường gặp:

| Giá trị | Hành vi |
|---|---|
| `none` | Không tự quản lý schema |
| `validate` | So sánh mapping với schema hiện có, không tạo/sửa schema |
| `update` | Cố gắng điều chỉnh schema theo mapping; không phù hợp làm migration production có kiểm soát |
| `create` | Tạo schema khi khởi tạo, có thể phá dữ liệu hiện có |
| `create-drop` | Tạo schema lúc khởi động và drop khi đóng context |

Không dùng `create`, `create-drop` hoặc `update` trên production chỉ để xử lý lỗi mapping. DDL Oracle có implicit commit và có thể cần lock; migration phải được kiểm thử và chạy theo kế hoạch riêng.

### 5.3. Không bật Open Session in View tùy tiện

`spring.jpa.open-in-view` mặc định có thể được bật trong một số cấu hình Spring Boot. Với API/service, cân nhắc tắt để tránh truy vấn lazy ngoài transaction ở tầng serialization. Hãy fetch dữ liệu cần thiết trong service/repository bằng fetch join, entity graph hoặc DTO projection.

## 6. Quản lý transaction với Spring

### 6.1. Transaction boundary ở service layer

Một nghiệp vụ thường gồm nhiều thao tác database. Đặt transaction ở service method bao trùm toàn bộ thay đổi cần atomic:

```java
@Service
public class OrderService {
    private final OrderRepository orderRepository;
    private final InventoryRepository inventoryRepository;

    public OrderService(
            OrderRepository orderRepository,
            InventoryRepository inventoryRepository) {
        this.orderRepository = orderRepository;
        this.inventoryRepository = inventoryRepository;
    }

    @Transactional
    public Long createOrder(CreateOrderCommand command) {
        inventoryRepository.reserve(
                command.productId(), command.quantity());

        Order order = new Order(
                command.customerId(),
                command.productId(),
                command.quantity());

        return orderRepository.save(order).getId();
    }
}
```

Nếu `reserve` thất bại bằng exception phù hợp, transaction có thể rollback toàn bộ thay đổi của method. Không commit thủ công trong repository khi Spring đang quản lý transaction.

### 6.2. Cách @Transactional hoạt động

Spring thường thực thi `@Transactional` thông qua proxy/interceptor:

1. Caller gọi method qua Spring proxy.
2. Transaction manager bắt đầu transaction hoặc tham gia transaction hiện có.
3. Repository/JPA/JDBC sử dụng connection gắn với transaction.
4. Nếu method hoàn tất bình thường, transaction manager commit.
5. Nếu exception thuộc rollback rule, transaction manager rollback.

Vì dùng proxy, self-invocation thường không kích hoạt transaction advice:

```java
public void outer() {
    inner(); // gọi nội bộ cùng object, có thể bypass proxy
}

@Transactional
public void inner() {
    // Không mặc định có transaction mới chỉ vì method có annotation.
}
```

Đặt transaction boundary ở method được gọi qua Spring bean proxy, hoặc tái cấu trúc service để lời gọi đi qua bean khác. Không dựa vào `@Transactional` trên private method như một cách tạo transaction độc lập.

### 6.3. Quy tắc rollback mặc định

Spring mặc định rollback khi method ném `RuntimeException` hoặc `Error`; checked exception không tự động rollback trong cấu hình mặc định truyền thống.

Nếu checked exception cũng phải rollback:

```java
@Transactional(rollbackFor = Exception.class)
public void importOrders() throws Exception {
    // Multiple database writes
}
```

Không bắt exception rồi bỏ qua nếu muốn rollback:

```java
@Transactional
public void process() {
    try {
        repository.save(...);
    } catch (DataAccessException ex) {
        log.error("Database operation failed", ex);
        throw ex; // truyền lỗi để transaction manager rollback
    }
}
```

Nếu bắt lỗi và không ném lại, Spring có thể coi method đã thành công và commit các thay đổi còn lại. Nếu muốn xử lý lỗi và vẫn commit phần khác, phải thiết kế transaction boundary/compensation rõ ràng.

### 6.4. Propagation

Các propagation mode thường gặp:

| Propagation | Hành vi |
|---|---|
| `REQUIRED` | Tham gia transaction hiện tại; nếu chưa có thì tạo mới |
| `REQUIRES_NEW` | Tạm suspend transaction hiện tại và tạo transaction độc lập |
| `SUPPORTS` | Tham gia nếu có transaction; nếu không thì chạy không transaction |
| `MANDATORY` | Yêu cầu caller đã có transaction |
| `NOT_SUPPORTED` | Suspend transaction hiện tại trong thời gian chạy method |
| `NEVER` | Báo lỗi nếu đang có transaction |
| `NESTED` | Dùng nested transaction/savepoint nếu transaction manager và resource hỗ trợ |

`REQUIRES_NEW` có thể cần thêm connection trong khi transaction bên ngoài vẫn giữ connection/lock. Dùng quá nhiều có thể làm cạn pool hoặc tạo deadlock chờ connection. `NESTED` phụ thuộc transaction manager và JDBC savepoint; không giả định mọi JPA transaction manager hỗ trợ đầy đủ.

### 6.5. Isolation level của Oracle

Oracle mặc định dùng `READ COMMITTED`. Mỗi statement đọc dữ liệu đã commit tại thời điểm statement bắt đầu bằng cơ chế multiversion read consistency; Oracle không cho dirty read theo cách thông thường.

Spring có thể yêu cầu isolation:

```java
@Transactional(isolation = Isolation.READ_COMMITTED)
public void readOrders() {
    // Oracle default isolation
}
```

Hoặc:

```java
@Transactional(isolation = Isolation.SERIALIZABLE)
public void calculateAndUpdate() {
    // Must be tested for serialization conflicts
}
```

Oracle hỗ trợ `READ COMMITTED` và `SERIALIZABLE` theo semantics của Oracle; không hỗ trợ `READ UNCOMMITTED` như một isolation mode thực sự. `SERIALIZABLE` có thể phát sinh `ORA-08177` khi có thay đổi cạnh tranh. Chỉ nâng isolation khi yêu cầu nghiệp vụ cần và đã kiểm thử concurrency.

### 6.6. readOnly và timeout

```java
@Transactional(readOnly = true, timeout = 10)
public List<OrderSummary> findRecentOrders() {
    return orderRepository.findRecentSummaries();
}
```

`readOnly=true` là hint cho transaction manager/provider và có thể cho phép tối ưu flush; nó không tự bảo đảm database từ chối mọi DML. `timeout` tính theo giây trong annotation Spring, nhưng việc áp dụng cụ thể còn phụ thuộc transaction manager/driver/provider.

Phân biệt transaction timeout với query timeout, lock timeout, network timeout và connection acquisition timeout. Chúng bảo vệ các giai đoạn khác nhau và không thay thế nhau.

## 7. Dùng JPA và JDBC trong cùng transaction

### 7.1. Ưu tiên JdbcTemplate khi cần SQL trực tiếp

Nếu ứng dụng dùng JPA và cần một truy vấn JDBC đặc thù Oracle, `JdbcTemplate` có thể tham gia transaction Spring hiện tại khi dùng cùng DataSource/transaction manager phù hợp:

```java
@Service
public class ReconciliationService {
    private final OrderRepository orderRepository;
    private final JdbcTemplate jdbcTemplate;

    @Transactional
    public void reconcile(Long orderId) {
        Order order = orderRepository.findById(orderId).orElseThrow();

        jdbcTemplate.update(
                "UPDATE order_audit SET status = ? WHERE order_id = ?",
                order.getStatus(), orderId);
    }
}
```

Điều kiện quan trọng là JPA và JdbcTemplate phải dùng cùng DataSource và được cấu hình transaction manager có thể phối hợp connection đó. Spring Boot thường tự cấu hình `JpaTransactionManager` cho một EntityManagerFactory/DataSource; xác nhận cấu hình nếu ứng dụng có nhiều datasource.

### 7.2. Không tự lấy connection ngoài transaction-bound context

Nếu tự gọi `dataSource.getConnection()` trong code đang chạy transaction JPA, không nên mặc định connection trả về là cùng physical connection đang được transaction quản lý. Dùng `JdbcTemplate` hoặc `DataSourceUtils.getConnection(dataSource)` để lấy connection gắn với transaction theo cơ chế Spring.

Không tự gọi `commit()`/`rollback()` trên connection do Spring quản lý. Cũng không đóng connection transaction-bound bằng tay; để Spring/JdbcTemplate quản lý vòng đời. Nếu dùng raw JDBC ngoài transaction, phải tự quản lý `try-with-resources`, commit/rollback và cleanup.

### 7.3. Nhiều DataSource

Nếu ứng dụng có hai Oracle database hoặc Oracle và một database khác, hai local transaction manager riêng không tự tạo atomic transaction chung. Cần cân nhắc:

- JTA/XA với XA-capable datasource và transaction manager chung.
- Transactional outbox/Saga nếu không cần hoặc không thể dùng XA.
- Quy trình reconciliation/idempotency nếu nghiệp vụ chấp nhận eventual consistency.

Không dùng `@Transactional` đơn lẻ để giả định nhiều DataSource sẽ commit cùng nhau.

## 8. Ánh xạ kiểu dữ liệu Oracle sang Java/JPA

### 8.1. NUMBER và BigDecimal

Oracle `NUMBER(p,s)` thường phù hợp với `BigDecimal` khi cần giữ chính xác decimal:

```sql
amount NUMBER(18, 2) NOT NULL
```

Entity:

```java
@Column(name = "AMOUNT", precision = 18, scale = 2, nullable = false)
private BigDecimal amount;
```

Không dùng `double`/`float` cho tiền tệ hoặc dữ liệu cần decimal chính xác vì binary floating point có thể làm tròn khác mong đợi.

Ánh xạ thường gặp:

| Oracle | Java/JDBC thường dùng | Lưu ý |
|---|---|---|
| `NUMBER(p,0)` có miền giá trị nhỏ | `Integer` | Kiểm tra giới hạn p và range |
| `NUMBER(19,0)` | `Long` hoặc `BigDecimal` | `NUMBER` có thể chứa giá trị vượt `Long`; xác nhận miền dữ liệu |
| `NUMBER(p,s)` | `BigDecimal` | Khai báo precision/scale phù hợp |
| `BINARY_FLOAT` | `Float` | Dùng cho floating point, không phải tiền tệ |
| `BINARY_DOUBLE` | `Double` | Dùng khi chấp nhận floating point |

Không suy ra kiểu Java chỉ từ tên `NUMBER`. Oracle `NUMBER` có thể có precision/scale không giới hạn như cột khai báo cụ thể; kiểm tra schema và giá trị thực tế.

### 8.2. VARCHAR2, NVARCHAR2 và CHAR

```sql
customer_code VARCHAR2(50 CHAR),
display_name  NVARCHAR2(200),
country_code  CHAR(2)
```

Thông thường ánh xạ sang `String`:

```java
@Column(name = "CUSTOMER_CODE", length = 50)
private String customerCode;

@Column(name = "DISPLAY_NAME", length = 200)
private String displayName;

@Column(name = "COUNTRY_CODE", length = 2)
private String countryCode;
```

`VARCHAR2` có thể khai báo giới hạn theo BYTE hoặc CHAR semantics; cần xem `NLS_LENGTH_SEMANTICS` và DDL thực tế. `NVARCHAR2` dùng national character set. `CHAR` là kiểu fixed-length và có thể được đệm khoảng trắng; kiểm tra so sánh và trim khi ánh xạ.

Không giả định `@Column(length=...)` luôn mô tả đầy đủ byte/character semantics của Oracle. Migration DDL nên là nguồn sự thật cho độ dài và charset.

### 8.3. DATE không chỉ lưu ngày

Oracle `DATE` lưu năm, tháng, ngày, giờ, phút và giây; không lưu fractional seconds hoặc timezone. Nó không giống hoàn toàn `java.sql.Date` theo nghĩa chỉ có ngày.

Lựa chọn Java phụ thuộc semantics:

- `LocalDate` nếu ứng dụng chủ ý chỉ lưu ngày và luôn chuẩn hóa phần thời gian.
- `LocalDateTime` nếu cần cả ngày và giờ tới giây.

Ví dụ:

```java
@Column(name = "ORDER_DATE", nullable = false)
private LocalDateTime orderDate;
```

Nếu cột Oracle DATE được dùng như ngày thuần, thống nhất quy tắc đặt thời gian về đầu ngày và kiểm thử round-trip. Không để ứng dụng này dùng `LocalDate`, ứng dụng khác dùng `LocalDateTime` rồi diễn giải cùng một cột theo hai cách khác nhau.

### 8.4. TIMESTAMP và timezone

| Oracle type | Java type thường phù hợp | Đặc điểm |
|---|---|---|
| `TIMESTAMP(n)` | `LocalDateTime` | Có fractional seconds, không có timezone |
| `TIMESTAMP WITH TIME ZONE` | `OffsetDateTime` hoặc kiểu phù hợp provider | Mang thông tin timezone/offset theo semantics Oracle/JDBC |
| `TIMESTAMP WITH LOCAL TIME ZONE` | Thường dùng `OffsetDateTime`/`LocalDateTime` theo thiết kế và provider | Chuẩn hóa theo database timezone và hiển thị theo session timezone |

Ví dụ:

```java
@Column(name = "CREATED_AT", nullable = false)
private LocalDateTime createdAt;

@Column(name = "EVENT_TIME")
private OffsetDateTime eventTime;
```

`TIMESTAMP WITH LOCAL TIME ZONE` không giữ nguyên timezone gốc theo cách giống `TIMESTAMP WITH TIME ZONE`; giá trị được chuẩn hóa theo database timezone và hiển thị theo session timezone. Hãy chọn kiểu Java và cấu hình session timezone dựa trên yêu cầu nghiệp vụ, không chỉ theo tên cột.

Với hệ thống cần ghi thời điểm toàn cầu, thống nhất lưu UTC hoặc một quy ước timezone rõ ràng, kiểm thử qua các JVM có timezone khác nhau và qua session/database timezone khác nhau.

### 8.5. CLOB, NCLOB và BLOB

Oracle LOB dùng để lưu nội dung lớn:

- `CLOB`: ký tự theo database character set.
- `NCLOB`: ký tự theo national character set.
- `BLOB`: dữ liệu nhị phân.

JPA có thể ánh xạ bằng `@Lob`:

```java
@Lob
@Column(name = "DESCRIPTION")
private String description;

@Lob
@Column(name = "DOCUMENT_CONTENT")
private byte[] documentContent;
```

`String`/`byte[]` tiện lợi cho nội dung nhỏ hoặc vừa nhưng có thể materialize toàn bộ dữ liệu vào heap. Với LOB lớn, cân nhắc JDBC `Clob`/`Blob`, stream hoặc API provider phù hợp để đọc/ghi theo luồng. Đóng stream/LOB locator đúng cách và giữ connection trong thời gian cần thiết.

Không dùng `@Lob` trên một field nhỏ chỉ vì muốn có kiểu dữ liệu lớn; mapping phải khớp DDL và cách ứng dụng sử dụng.

### 8.6. RAW và UUID

Oracle `RAW(n)` thường ánh xạ sang `byte[]`. Nếu lưu UUID, có thể dùng `RAW(16)` với converter hoặc kiểu mapping Hibernate được hỗ trợ:

```java
@Converter(autoApply = false)
public class UuidRawConverter
        implements AttributeConverter<UUID, byte[]> {

    @Override
    public byte[] convertToDatabaseColumn(UUID value) {
        if (value == null) return null;
        ByteBuffer buffer = ByteBuffer.allocate(16);
        buffer.putLong(value.getMostSignificantBits());
        buffer.putLong(value.getLeastSignificantBits());
        return buffer.array();
    }

    @Override
    public UUID convertToEntityAttribute(byte[] value) {
        if (value == null) return null;
        if (value.length != 16) {
            throw new IllegalArgumentException("Expected 16-byte UUID");
        }
        ByteBuffer buffer = ByteBuffer.wrap(value);
        return new UUID(buffer.getLong(), buffer.getLong());
    }
}
```

Converter này định nghĩa byte order theo thứ tự hai `long` của `UUID`; mọi service ghi/đọc cột phải dùng cùng quy ước. Nếu dùng `VARCHAR2(36)` để lưu UUID dạng text, dễ debug hơn nhưng chiếm nhiều byte hơn `RAW(16)`. Chọn một chuẩn duy nhất và không đổi encoding giữa các hệ thống.

### 8.7. Boolean trong Oracle

Oracle Database trước 23c/23ai không có SQL `BOOLEAN` dùng trong bảng theo cách phổ biến như PostgreSQL. Các schema thường biểu diễn boolean bằng:

- `NUMBER(1)` với `0/1`.
- `CHAR(1)` hoặc `VARCHAR2(1)` với `Y/N`, `T/F`.

Ví dụ converter:

```java
@Converter
public class BooleanYnConverter
        implements AttributeConverter<Boolean, String> {

    @Override
    public String convertToDatabaseColumn(Boolean value) {
        if (value == null) return null;
        return value ? "Y" : "N";
    }

    @Override
    public Boolean convertToEntityAttribute(String value) {
        if (value == null) return null;
        return switch (value) {
            case "Y" -> true;
            case "N" -> false;
            default -> throw new IllegalArgumentException(
                    "Unexpected boolean value: " + value);
        };
    }
}
```

Đặt converter trên field:

```java
@Convert(converter = BooleanYnConverter.class)
@Column(name = "ACTIVE_FLAG", length = 1)
private Boolean active;
```

Oracle Database 23c/23ai có SQL Boolean type; việc dùng trực tiếp còn phụ thuộc JDBC driver, Hibernate version và migration/schema compatibility. Không dùng SQL Boolean type trong môi trường 19c.

### 8.8. Enum

Với enum nghiệp vụ, thường ưu tiên lưu tên bằng `EnumType.STRING`:

```java
@Enumerated(EnumType.STRING)
@Column(name = "ORDER_STATUS", length = 30)
private OrderStatus status;
```

`EnumType.ORDINAL` lưu số thứ tự. Nếu đổi thứ tự hoặc chèn phần tử trong enum Java, dữ liệu cũ có thể bị diễn giải thành trạng thái khác. `STRING` dễ đọc hơn nhưng đổi tên enum cũng cần migration dữ liệu.

## 9. Ánh xạ khóa chính và sequence Oracle

### 9.1. Tạo sequence

```sql
CREATE SEQUENCE order_seq
  START WITH 1
  INCREMENT BY 50
  CACHE 100
  NOCYCLE;
```

`CACHE` có thể cải thiện hiệu năng sinh sequence; sequence không bảo đảm giá trị liên tục. Khi database restart hoặc cache mất, có thể xuất hiện gap. Không dùng sequence làm bộ đếm hóa đơn liên tục nếu nghiệp vụ đòi hỏi không có khoảng trống.

### 9.2. Entity dùng GenerationType.SEQUENCE

```java
@Entity
@Table(name = "ORDERS")
public class Order {
    @Id
    @GeneratedValue(
        strategy = GenerationType.SEQUENCE,
        generator = "order_seq_generator")
    @SequenceGenerator(
        name = "order_seq_generator",
        sequenceName = "ORDER_SEQ",
        allocationSize = 50)
    @Column(name = "ORDER_ID")
    private Long id;

    // Other fields
}
```

`allocationSize` và `INCREMENT BY` của sequence phải phù hợp với optimizer mà Hibernate sử dụng. Với pooled optimizer, Hibernate có thể cấp phát một dải ID trong một lần lấy sequence. Nếu sequence increment không khớp, có thể gây ID nhảy lớn, lỗi validation hoặc xung đột ID tùy cấu hình. Kiểm tra DDL, Hibernate version và log generator.

### 9.3. Identity column

Oracle 12c trở lên hỗ trợ identity column:

```sql
CREATE TABLE audit_event (
    event_id NUMBER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    event_type VARCHAR2(50) NOT NULL,
    created_at TIMESTAMP(6) DEFAULT SYSTIMESTAMP NOT NULL
);
```

Entity có thể dùng `GenerationType.IDENTITY` nếu database, Hibernate và JDBC driver hỗ trợ đúng generated-key behavior. Identity có thể ảnh hưởng khả năng JDBC batching khi insert; với workload insert lớn, sequence-based generation thường cho phép Hibernate tối ưu batching linh hoạt hơn.

## 10. Một entity Oracle hoàn chỉnh

DDL:

```sql
CREATE TABLE customers (
    customer_id   NUMBER(19) PRIMARY KEY,
    customer_code VARCHAR2(40 CHAR) NOT NULL,
    display_name  VARCHAR2(200 CHAR) NOT NULL,
    credit_limit  NUMBER(16, 2) DEFAULT 0 NOT NULL,
    active_flag   CHAR(1) DEFAULT 'Y' NOT NULL,
    created_at    TIMESTAMP(6) DEFAULT SYSTIMESTAMP NOT NULL,
    version_no    NUMBER(19) DEFAULT 0 NOT NULL,
    CONSTRAINT customers_code_uk UNIQUE (customer_code),
    CONSTRAINT customers_active_ck CHECK (active_flag IN ('Y', 'N'))
);

CREATE SEQUENCE customer_seq START WITH 1 INCREMENT BY 1 CACHE 100;
```

Entity:

```java
@Entity
@Table(name = "CUSTOMERS")
public class Customer {
    @Id
    @GeneratedValue(strategy = GenerationType.SEQUENCE,
                    generator = "customer_seq_gen")
    @SequenceGenerator(name = "customer_seq_gen",
                       sequenceName = "CUSTOMER_SEQ",
                       allocationSize = 1)
    @Column(name = "CUSTOMER_ID")
    private Long id;

    @Column(name = "CUSTOMER_CODE", nullable = false, length = 40)
    private String customerCode;

    @Column(name = "DISPLAY_NAME", nullable = false, length = 200)
    private String displayName;

    @Column(name = "CREDIT_LIMIT", precision = 16, scale = 2, nullable = false)
    private BigDecimal creditLimit;

    @Convert(converter = BooleanYnConverter.class)
    @Column(name = "ACTIVE_FLAG", length = 1, nullable = false)
    private Boolean active;

    @Column(name = "CREATED_AT", nullable = false)
    private LocalDateTime createdAt;

    @Version
    @Column(name = "VERSION_NO", nullable = false)
    private Long version;

    protected Customer() {}

    public Customer(String customerCode, String displayName,
                    BigDecimal creditLimit) {
        this.customerCode = customerCode;
        this.displayName = displayName;
        this.creditLimit = creditLimit;
        this.active = true;
        this.createdAt = LocalDateTime.now();
    }

    // Getters and domain methods omitted for brevity.
}
```

Ví dụ dùng `allocationSize=1` để khớp sequence `INCREMENT BY 1` và tránh bàn sâu vào pooled optimizer. Với hệ thống throughput cao, có thể chọn allocation size lớn hơn nhưng phải đồng bộ DDL và Hibernate optimizer.

## 11. Repository và service end-to-end

### 11.1. Spring Data repository

```java
public interface CustomerRepository extends JpaRepository<Customer, Long> {
    Optional<Customer> findByCustomerCode(String customerCode);

    boolean existsByCustomerCode(String customerCode);
}
```

Spring Data tạo implementation dựa trên entity mapping. Tên property trong method query là tên field Java, không nhất thiết giống tên cột Oracle.

### 11.2. DTO command và service transaction

```java
public record CreateCustomerCommand(
        String customerCode,
        String displayName,
        BigDecimal creditLimit) {}

@Service
public class CustomerService {
    private final CustomerRepository repository;

    public CustomerService(CustomerRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public Long create(CreateCustomerCommand command) {
        if (repository.existsByCustomerCode(command.customerCode())) {
            throw new IllegalArgumentException("Customer code already exists");
        }

        Customer customer = new Customer(
                command.customerCode(),
                command.displayName(),
                command.creditLimit());

        return repository.save(customer).getId();
    }

    @Transactional(readOnly = true)
    public Customer findByCode(String code) {
        return repository.findByCustomerCode(code).orElseThrow();
    }
}
```

Kiểm tra `existsByCustomerCode` cải thiện thông báo nghiệp vụ nhưng không thay thế unique constraint. Hai request đồng thời vẫn có thể cùng vượt qua bước kiểm tra; unique constraint ở Oracle là bảo vệ cuối cùng. Xử lý `DataIntegrityViolationException`/constraint violation để trả lỗi phù hợp.

### 11.3. Đừng gọi external API khi đang giữ transaction dài

Nếu method `@Transactional` gọi HTTP service, gửi email hoặc chờ message broker lâu, connection và lock database có thể bị giữ suốt thời gian chờ. Tách external call khỏi transaction hoặc dùng outbox/event-driven flow. Một transaction database nên ngắn và chỉ bao gồm các thay đổi cần atomic.

## 12. Kiểm thử kết nối, mapping và transaction

### 12.1. Kiểm tra DataSource

Một smoke test có thể lấy connection và xem metadata:

```java
try (Connection connection = dataSource.getConnection()) {
    DatabaseMetaData metadata = connection.getMetaData();
    assertTrue(metadata.getDatabaseProductName().contains("Oracle"));
    assertTrue(connection.isValid(5));
}
```

Không chạy kiểm tra kiểu này bằng cách mở một connection mới cho mỗi request production. Dùng health indicator của Spring Boot/Actuator hoặc cơ chế monitoring phù hợp.

### 12.2. Kiểm thử round-trip kiểu dữ liệu

Tạo test insert rồi đọc lại các trường:

- `BigDecimal` có scale/precision đúng.
- `LocalDate`/`LocalDateTime` không bị lệch ngày hoặc mất giờ ngoài dự kiến.
- `OffsetDateTime`/timezone được giữ theo semantics đã chọn.
- Unicode/NVARCHAR2 được lưu và đọc đúng.
- LOB lớn được stream đầy đủ.
- UUID/RAW(16) có byte order nhất quán.
- Boolean converter xử lý null và giá trị không hợp lệ.
- Enum string tương thích dữ liệu đã có.

Test phải chạy trên Oracle release/driver gần production; H2 hoặc database giả lập có thể không tái hiện semantics Oracle DATE, NUMBER, sequence, LOB, locking và SQL dialect.

### 12.3. Kiểm thử rollback

Một test service có thể buộc phát sinh exception sau lần ghi đầu:

```java
@Transactional
public void createThenFail() {
    repository.save(new Customer(...));
    throw new IllegalStateException("force rollback for test");
}
```

Sau khi method thất bại, dùng transaction/connection mới kiểm tra dòng không tồn tại. Không đọc lại bằng cùng persistence context đã bị rollback rồi kết luận trạng thái database.

### 12.4. Kiểm thử concurrency

Mở hai connection/transaction độc lập và kiểm tra:

- Unique constraint khi hai request insert cùng business key.
- Optimistic locking với `@Version`.
- Pessimistic locking với `SELECT FOR UPDATE`.
- Lock timeout và deadlock.
- Isolation `READ COMMITTED`/`SERIALIZABLE` nếu ứng dụng dùng.

Mỗi thread cần transaction/persistence context riêng; `EntityManager` không thread-safe. Dùng barrier/latch để kiểm soát thứ tự thay vì sleep cố định.

## 13. Chẩn đoán lỗi thường gặp

| Lỗi/triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| `ORA-12154` | Không phân giải được connect identifier/TNS alias | JDBC URL, TNS config, service name và naming resolution |
| `ORA-12514` | Listener không biết service được yêu cầu | Service name, listener registration, PDB service |
| `ORA-12541` | Không có listener tại host/port | Listener process, port, firewall, DNS |
| `ORA-01017` | Username/password không hợp lệ | Secret, account, case-sensitive password, đúng PDB/service |
| `ORA-28000` | Account bị khóa | DBA kiểm tra account status và policy |
| Pool acquisition timeout | Không mượn được connection trong thời gian cấu hình | Active/idle/pending pool, leak, query/transaction dài, DB capacity |
| `ORA-00020`/`ORA-00018` | Chạm giới hạn process/session | `V$RESOURCE_LIMIT`, session theo user/service và tổng pool replicas |
| `ORA-00904` | Invalid identifier | Schema migration, column name, naming strategy, quoted identifier |
| `ORA-01400` | Insert NULL vào cột NOT NULL | Mapping/default/insert statement và DDL |
| `ORA-12899` | Giá trị vượt độ dài cột | Byte/CHAR semantics, length annotation, dữ liệu Unicode |
| `ORA-01438` | Giá trị vượt precision của NUMBER | `BigDecimal`, precision/scale và DDL |
| `ORA-00001` | Vi phạm unique/primary key | Business key, sequence/identity và concurrency |
| `ORA-00060` | Deadlock | Transaction order, lock graph, transaction duration |
| `ORA-08177` | Không serialize được transaction | Isolation SERIALIZABLE và retry transaction mới |

Khi điều tra, lấy root cause JDBC/Oracle error code. Spring có thể translate exception sang `DataAccessException`; không chỉ nhìn tên exception ở tầng REST.

### 13.1. Kiểm tra session từ Oracle

```sql
SELECT sid,
       serial#,
       username,
       status,
       machine,
       program,
       module,
       action,
       service_name,
       sql_id,
       event
FROM v$session
WHERE username = 'APP_USER'
ORDER BY logon_time;
```

Để gắn session với request, ứng dụng có thể dùng `DBMS_APPLICATION_INFO.SET_MODULE` và `DBMS_SESSION.SET_IDENTIFIER` qua connection đang sử dụng. Nếu dùng pool, reset các giá trị session-specific trước khi trả connection để request sau không thừa hưởng metadata hoặc trạng thái cũ.

### 13.2. Kiểm tra transaction còn mở

```sql
SELECT s.sid,
       s.serial#,
       s.username,
       t.start_time,
       t.used_ublk,
       t.used_urec
FROM v$transaction t
JOIN v$session s
  ON s.taddr = t.addr
WHERE s.username = 'APP_USER'
ORDER BY t.start_time;
```

Transaction tồn tại lâu có thể do code quên commit/rollback, transaction boundary bao trùm external call hoặc request giữ connection. Xác định owner và tác động trước khi terminate session.

## 14. Bảo mật và vận hành production

### 14.1. Credential và TLS

- Lấy username/password từ secret store hoặc secret injection của nền tảng.
- Dùng account runtime có quyền tối thiểu.
- Dùng TLS/TCPS hoặc Oracle Native Network Encryption theo yêu cầu bảo mật.
- Không log JDBC URL nếu URL chứa credential hoặc token.
- Xoay credential theo quy trình và kiểm tra pool có thể tái kết nối sau rotation.

### 14.2. Không bật SQL/bind logging rộng trong production

`org.hibernate.SQL=DEBUG` có thể hữu ích ở môi trường dev/test. Bind parameter TRACE có thể ghi dữ liệu khách hàng, token hoặc thông tin nhạy cảm. Chỉ bật ngắn hạn, giới hạn phạm vi và bảo vệ log.

### 14.3. Theo dõi pool và database

Theo dõi:

- Pool active, idle, pending threads và acquisition timeout.
- Connection creation/close rate và leak detection.
- Transaction duration, rollback rate và query latency.
- Oracle session/process utilization và wait events.
- SQL_ID, module/action, top SQL và lock contention.
- Error rate theo ORA code và service/PDB.

Đừng chỉ tăng pool khi thấy pending borrowers. Nếu database đã bão hòa CPU hoặc lock, pool lớn hơn có thể làm tình hình xấu hơn.

### 14.4. Session state và connection pool

Connection pool tái sử dụng physical session. Tránh để request thay đổi `CURRENT_SCHEMA`, NLS settings, timezone, application context hoặc package state mà không reset. Nếu cần session state, khởi tạo và cleanup rõ ràng, kể cả khi exception. Một session bị rò rỉ state có thể làm request kế tiếp chạy sai schema hoặc nhìn nhầm tenant.

## 15. Quy trình triển khai thực tế

1. DBA cung cấp host, port, service name/PDB, account runtime và yêu cầu TLS/wallet.
2. Kiểm tra kết nối từ công cụ Oracle; xác nhận đúng database, service và container.
3. Chọn Oracle JDBC driver theo JDK, database release và ma trận hỗ trợ; khóa version trong build.
4. Cấu hình DataSource/connection pool bằng secret, timeout và pool size có capacity budget.
5. Xác định Spring Boot/Hibernate version; để Hibernate auto-detect Oracle dialect khi phù hợp.
6. Tạo schema bằng Flyway/Liquibase; dùng `ddl-auto: validate` ở production.
7. Thiết kế entity mapping khớp Oracle DDL: NUMBER, VARCHAR2, DATE/TIMESTAMP, LOB, RAW, Boolean và sequence.
8. Đặt transaction boundary ở service method; quy định rollback, propagation, isolation và timeout.
9. Dùng `JdbcTemplate`/`DataSourceUtils` nếu cần JDBC trong transaction JPA; không tự commit connection do Spring quản lý.
10. Kiểm thử round-trip kiểu dữ liệu, rollback, concurrency, lock, generated ID và lỗi unique trên Oracle thật hoặc môi trường tương thích.
11. Theo dõi pool, transaction, SQL và Oracle session trong staging dưới tải gần production.
12. Triển khai với runbook, dashboard, cảnh báo và phương án rollback ứng dụng/schema.

## 16. Checklist trước khi đưa lên production

| Hạng mục | Câu hỏi cần xác nhận |
|---|---|
| Connection | URL dùng đúng service/PDB? Listener và network/TLS hoạt động? |
| Driver | `ojdbc` tương thích JDK, Oracle release và application server? |
| Credential | Secret được quản lý ngoài source code? Runtime user có quyền tối thiểu? |
| Pool | Tổng max connections của mọi replica nằm trong DB capacity? Timeout phù hợp? |
| Hibernate | Dialect tương thích major version? Metadata detection hoạt động? |
| Schema | Flyway/Liquibase quản lý DDL? `ddl-auto` không phá schema? |
| Mapping | NUMBER precision/scale, DATE/TIMESTAMP/timezone, LOB, RAW, Boolean và enum được test? |
| Identifier | Sequence/identity và allocation size khớp DDL? |
| Transaction | Ranh giới service rõ? Rollback rule và propagation đúng? |
| Isolation/locking | Đã test lost update, lock timeout, deadlock và serialization conflict? |
| JDBC/JPA mix | Cùng DataSource/transaction manager? Không tự commit/close transaction-bound connection? |
| Observability | Có pool metrics, SQL_ID, module/action, ORA code và transaction duration? |
| Recovery | Có backup/schema migration rollback và runbook vận hành? |

## 17. Nguyên tắc cần ghi nhớ

- JDBC driver, DataSource pool, Hibernate và transaction manager là các lớp khác nhau; lỗi cần được định vị đúng tầng.
- Dùng JDBC Thin URL với service name/PDB do DBA cung cấp; kiểm tra kết nối độc lập trước khi debug ORM.
- Chọn `ojdbc` theo JDK, Oracle release và ma trận hỗ trợ; không chọn version theo số Oracle Database một cách máy móc.
- Dùng connection pool có giới hạn; tổng kết nối phải tính trên mọi replica/service và workload nền.
- Spring `@Transactional` nên đặt ở service boundary; self-invocation có thể bypass proxy và checked exception không mặc định rollback.
- Oracle mặc định `READ COMMITTED`; `SERIALIZABLE` có thể gặp `ORA-08177` và cần retry bằng transaction mới.
- Khi trộn JPA và JDBC, dùng cùng DataSource/transaction manager; ưu tiên `JdbcTemplate` hoặc `DataSourceUtils` để tham gia transaction hiện tại.
- `NUMBER(p,s)` thường ánh xạ `BigDecimal`; Oracle `DATE` có cả giờ tới giây; phân biệt `TIMESTAMP` và các kiểu có timezone.
- LOB lớn nên được stream; UUID/RAW, Boolean và Enum cần quy ước mapping ổn định.
- Sequence `allocationSize` phải phù hợp với DDL; sequence không bảo đảm giá trị liên tục.
- Dùng Flyway/Liquibase và `ddl-auto: validate`; không để Hibernate tự sửa schema production thiếu kiểm soát.
- Kiểm thử round-trip, rollback, concurrency và pool behavior trên Oracle release/driver gần production.

## Tài liệu Oracle, Spring và Java tham khảo

- [Oracle JDBC Developer's Guide](https://docs.oracle.com/en/database/oracle/oracle-database/19/jjdbc/)
- [Oracle Database 19c SQL Language Reference — Data Types](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/Data-Types.html)
- [Oracle Database 19c SQL Language Reference — CREATE TABLE](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/CREATE-TABLE.html)
- [Oracle Database 19c SQL Language Reference — CREATE SEQUENCE](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/CREATE-SEQUENCE.html)
- [Spring Boot Reference — SQL Databases and DataSource](https://docs.spring.io/spring-boot/reference/data/sql.html)
- [Spring Framework Reference — Declarative Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative.html)
- [Spring Data JPA Reference](https://docs.spring.io/spring-data/jpa/reference/)
- [Hibernate ORM User Guide — Basic Types](https://docs.hibernate.org/orm/6.6/userguide/html_single/Hibernate_User_Guide.html#basic)
- [Hibernate ORM User Guide — Identifiers](https://docs.hibernate.org/orm/6.6/userguide/html_single/Hibernate_User_Guide.html#identifiers)
- [Java SE API — JDBC](https://docs.oracle.com/en/java/javase/21/docs/api/java.sql/java/sql/package-summary.html)
