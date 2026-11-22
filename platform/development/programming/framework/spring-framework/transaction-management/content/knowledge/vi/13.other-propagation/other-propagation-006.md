# SUPPORTS và đồng bộ hóa tài nguyên khi không có giao dịch vật lý

## 1. Bài toán và thông điệp quan trọng

Trong Spring Framework, `Propagation.SUPPORTS` có một cách diễn đạt ngắn:

> Nếu đang có transaction phù hợp thì tham gia transaction ấy; nếu không có thì thực thi không có transaction vật lý.

Tuy nhiên, câu trên **chưa mô tả hết** hành vi của Spring. Với các transaction manager hỗ trợ *transaction synchronization*, một lời gọi `@Transactional(propagation = Propagation.SUPPORTS)` **có thể kích hoạt phạm vi đồng bộ hóa tài nguyên** ngay cả khi **không có transaction vật lý** ở database.

Vì vậy, hoàn toàn có thể đồng thời quan sát:

```text
TransactionSynchronizationManager.isSynchronizationActive() = true
TransactionSynchronizationManager.isActualTransactionActive() = false
```

Hai giá trị này **không mâu thuẫn**. Chúng trả lời hai câu hỏi khác nhau:

- **Synchronization active?** Spring có đang quản lý một phạm vi để các tài nguyên/callback đồng bộ được đăng ký, tái sử dụng và dọn dẹp theo scope?
- **Actual transaction active?** Có transaction vật lý hiện hữu mà Spring coi là đang hoạt động hay không?

Hệ quả quan trọng nhất: **cùng dùng lại một JDBC Connection không đồng nghĩa những câu SQL đang nằm trong một database transaction có thể rollback chung**. Với cấu hình H2/Hikari auto-commit thông thường, hai câu INSERT trong một scope SUPPORTS không có transaction vật lý có thể được commit **riêng ngay lúc thực thi**, và exception cuối method không tự hoàn tác chúng.

### Sau bài học, bạn sẽ làm được gì?

1. Phân biệt `SUPPORTS` với `REQUIRED`, `NOT_SUPPORTED` và `MANDATORY` theo tình trạng transaction bên ngoài.
2. Phân biệt **logical synchronization scope**, **resource binding/reuse** và **physical transaction**.
3. Hiểu vai trò của `AbstractPlatformTransactionManager.SYNCHRONIZATION_ALWAYS`, `SYNCHRONIZATION_ON_ACTUAL_TRANSACTION` và `SYNCHRONIZATION_NEVER`.
4. Giải thích `DataSourceUtils`, `JdbcTemplate` và `TransactionSynchronizationManager` phối hợp để chia sẻ connection trong một thread như thế nào.
5. Chạy được demo **Java 17+, Spring Boot, Spring JDBC và H2** cho thấy `SUPPORTS` không có transaction vật lý vẫn có synchronization và vẫn dùng chung connection, nhưng không rollback dữ liệu đã auto-commit.
6. So sánh với trường hợp inner `SUPPORTS` tham gia transaction `REQUIRED` bên ngoài: transaction vật lý có thật và các INSERT rollback cùng nhau.
7. Thiết kế test và giám sát tránh nhầm `isSynchronizationActive()`, `isCurrentTransactionReadOnly()` hoặc việc thấy lại dữ liệu với bằng chứng commit/rollback.

Bài thuộc mục **Propagation khác** của module **Spring Framework — transaction management**, tập trung trực tiếp vào đề bài **“SUPPORTS và đồng bộ hóa tài nguyên khi không có giao dịch vật lý”**.

## 2. SUPPORTS không phải là REQUIRED “nhẹ hơn” theo nghĩa rollback

Giả sử một service có:

```java
@Transactional(propagation = Propagation.SUPPORTS)
public void doWork() {
    // Data access...
}
```

Nếu service được Spring proxy intercept, behavior của `SUPPORTS` phụ thuộc tình trạng bên ngoài:

| Bối cảnh trước khi gọi | SUPPORTS thực hiện | Transaction vật lý? | Điều cần nhớ |
| --- | --- | --- | --- |
| Đã có transaction T thuộc manager thích hợp | **Tham gia T** | Có, dùng T đã có | INSERT/UPDATE thuộc T có thể cùng commit/rollback |
| Không có transaction T, synchronization mode là `ALWAYS` | Chạy không có T, nhưng có thể mở synchronization scope | **Không** | Tài nguyên có thể chia sẻ trong scope; không có rollback vật lý cho SQL auto-commit |
| Không có T, synchronization mode là `ON_ACTUAL_TRANSACTION` | Chạy không có T và không mở synchronization scope mới | **Không** | Không hứa thread-bound resource sharing nhờ scope SUPPORTS |
| Không có T, synchronization mode là `NEVER` | Không mở synchronization scope bởi manager đó | **Không** | Không nên mặc định `DataSourceUtils` sẽ bind connection |
| Gọi method trực tiếp qua `this.method()` trong proxy mode | Annotation tại method không được interceptor áp dụng riêng | Tùy outer đã có T hay chưa | Không kết luận gì chỉ từ annotation |

Với `REQUIRED`, nếu chưa có transaction, Spring **phải mở một transaction vật lý mới** theo khả năng manager. Với `SUPPORTS`, nếu chưa có transaction, nó **không yêu cầu transaction vật lý**. Đây là khác biệt cốt lõi về bảo đảm atomicity.

Điều bất ngờ là cấu hình synchronization có thể khiến `SUPPORTS` **không giống một lời gọi Java thuần ngoài transaction** về cách *scope tài nguyên*. Nó có thể giữ lại cùng connection/session để dùng lại và đăng ký callback, dù các câu SQL không nằm dưới một `BEGIN...COMMIT/ROLLBACK` chung.

### 2.1. SUPPORTS “tham gia T” khi nào?

Ví dụ:

```java
@Service
public class ReportService {
    @Transactional(propagation = Propagation.SUPPORTS)
    public void calculate() {
        // JDBC/JPA queries...
    }
}

@Service
public class OrderService {
    private final ReportService reports;

    public OrderService(ReportService reports) {
        this.reports = reports;
    }

    @Transactional
    public void placeOrder() {
        // Ghi đơn hàng.
        reports.calculate(); // SUPPORTS tham gia T do placeOrder mở.
    }
}
```

Hai class là **minh họa kiến trúc**, chưa có implementation phần DB. Nếu cả hai method được gọi qua proxy và dùng đúng transaction manager/tài nguyên, `calculate()` thực hiện trong transaction T hiện có. `SUPPORTS` **không tạo transaction độc lập** và không tự commit khi `calculate()` return.

Nếu caller gọi `reportService.calculate()` trực tiếp từ một runner không có transaction, behavior lại khác: **không có physical transaction** cho riêng method đó, dù synchronization có thể vẫn active.

## 3. Ba lớp cần phân biệt: metadata, synchronization, physical transaction

Để không nhầm lẫn, hãy chia thành ba khái niệm:

### 3.1. Metadata của transaction

`@Transactional(propagation = SUPPORTS)` là lời khai báo. `TransactionInterceptor` đọc metadata để hỏi `PlatformTransactionManager` cách xử lý.

Annotation **không** tự chuyển JDBC connection sang `autoCommit=false`, không tự bind resource và không tự tạo proxy. Spring bean phải được quản lý và invocation phải đi qua advice tương ứng (hoặc cơ chế weaving phù hợp).

### 3.2. Transaction synchronization

Spring có cơ chế quản lý synchronization cho thread-bound imperative transactions. `TransactionSynchronizationManager` có thể giữ:

- Các resource gắn với key, ví dụ một `ConnectionHolder` gắn với `DataSource`.
- Danh sách `TransactionSynchronization` callback đã đăng ký.
- Thông tin phạm vi transaction, như tên, read-only hint hoặc isolation metadata.
- Cờ synchronization active và cờ actual transaction active.

**Synchronization scope là cơ chế phối hợp/lifecycle**, không phải database transaction theo định nghĩa ACID. Manager có thể mở synchronization cho một “empty transaction” của `SUPPORTS` không có backend transaction.

### 3.3. Physical transaction

Physical transaction thật quản lý atomicity trên database connection (hoặc entity manager/transaction coordinator tương ứng). Với `DataSourceTransactionManager`, một transaction JDBC mới thường chuyển connection sang chế độ `autoCommit=false`, bind resource cho thread, và sau cùng gọi commit/rollback.

Khi không có physical transaction và connection đang `autoCommit=true`, từng câu SQL thường được commit theo semantics auto-commit của driver/DB. Một exception cuối method **không thể khiến Spring rollback những câu SQL đã được database commit trước đó**.

### 3.4. Bảng nhận biết bằng API

| API/quan sát | Cho biết điều gì? | Không chứng minh điều gì? |
| --- | --- | --- |
| `TransactionSynchronizationManager.isSynchronizationActive()` | Có synchronization scope hiện tại | Không chứng minh DB transaction đang active |
| `TransactionSynchronizationManager.isActualTransactionActive()` | Spring đánh dấu có actual transaction | Không bảo đảm mọi resource ngoài đều tham gia |
| `TransactionSynchronizationManager.hasResource(dataSource)` | Đã bind resource cho key `DataSource` | Không chứng minh resource đã tắt auto-commit |
| `TransactionAspectSupport.currentTransactionStatus().isNewTransaction()` | Invocation của advice có mở transaction mới | Không phải DB transaction ID, không dùng ngoài advice |
| `Connection.getAutoCommit()` | Chế độ auto-commit trên connection được lấy ra | Không nói về commit của connection khác |
| `SELECT COUNT(*)` sau khi boundary kết thúc | Trạng thái dữ liệu đã quan sát ở DB | Cần bảo đảm query đúng DB/schema và không có concurrency gây nhiễu |

Ví dụ “`sync=true`, `actual=false`, `bound=true`, `autoCommit=true`” cho thấy một **synchronization scope đang tái sử dụng connection ngoài physical transaction**, không phải một rollback-able transaction.

## 4. Vì sao SUPPORTS có thể chia sẻ JDBC Connection khi không có T?

Spring JDBC thường đi qua `DataSourceUtils.getConnection(DataSource)` để lấy connection. `JdbcTemplate` cũng sử dụng cơ chế kết nối phù hợp với transaction infrastructure.

Khi synchronization đang active và code xin một connection:

1. `DataSourceUtils` kiểm tra `TransactionSynchronizationManager` xem có `ConnectionHolder` đã bind theo `DataSource` chưa.
2. Nếu chưa có, nó lấy connection từ pool/driver.
3. Nếu có synchronization scope thích hợp, nó có thể **đăng ký synchronization để dọn dẹp** và bind holder vào thread.
4. Các thao tác JDBC tiếp theo qua cùng `DataSource`/`DataSourceUtils` trong scope có thể nhận **chính connection đã bind**.
5. Khi scope kết thúc, Spring chạy phần cleanup/đóng hoặc trả connection về pool theo lifecycle tương ứng.

Khi có physical transaction T, connection chung này thường được manager thiết lập `autoCommit=false`, và manager commit/rollback T.

Khi **không có T**, connection vẫn có thể được giữ và dùng lại vì synchronization, nhưng nó vẫn có thể giữ `autoCommit=true`. **Đồng nhất connection ≠ đồng nhất commit boundary**.

Sơ đồ:

```text
SUPPORTS, không có T, manager SYNCHRONIZATION_ALWAYS

Service A qua proxy
    |
    +-- Spring mở synchronization scope (không BEGIN T)
    |
    +-- DataSourceUtils.getConnection(ds)
    |      +-- lấy Connection C từ pool
    |      +-- bind C vào thread, đăng ký cleanup
    |
    +-- JdbcTemplate INSERT id=1 qua C  [autoCommit=true]
    |      +-- DB commit câu SQL này
    |
    +-- Service B SUPPORTS qua proxy
    |      +-- DataSourceUtils.getConnection(ds) -> vẫn C
    |      +-- JdbcTemplate INSERT id=2 qua C  [autoCommit=true]
    |      +-- DB commit câu SQL thứ hai
    |
    +-- Service A throw RuntimeException
    |
    +-- Spring cleanup synchronization scope
    |      [KHÔNG có physical transaction để rollback]
    |
Caller catch exception
    |
    +-- SELECT COUNT(id=1 or 2) -> cả hai record vẫn tồn tại
```

**Cảnh báo:** sơ đồ là behavior của **demo H2/Hikari với auto-commit=true**. Với một DataSource đặc biệt hoặc connection được cấu hình auto-commit khác, hành vi có thể khác và cần test riêng; đừng suy luận mù quáng từ tên propagation.

### 4.1. Vì sao giữ cùng Connection lại có ích?

Resource synchronization hữu ích cho tính nhất quán về *lifecycle*, chẳng hạn:

- Nhiều lớp truy cập dữ liệu trong cùng một lời gọi có thể dùng cùng connection/session.
- Giảm việc xin/trả resource lặp lại trong một scope khi framework quản lý phù hợp.
- Đảm bảo cleanup của resource theo boundary được tổ chức.
- Các thư viện có thể gắn synchronization callback phục vụ vòng đời resource.

Tuy nhiên, nếu không có physical transaction, **không hứa ACID atomicity**. Cùng connection có thể giúp nhất quán trạng thái session, nhưng có thể dẫn tới connection bị giữ lâu hơn, đặc biệt khi method truy vấn kéo dài.

### 4.2. DataSourceUtils không đồng nghĩa trực tiếp gọi dataSource.getConnection()

Trong Spring JDBC, `DataSourceUtils.getConnection(ds)` và `DataSourceUtils.releaseConnection(conn, ds)` là cách công khai tương thích với thread-bound resources. Trong phạm vi synchronization, `releaseConnection` có thể **không đóng ngay** một connection đang được bind: framework giữ nó để tái dùng và cleanup lúc kết thúc scope.

Nếu dùng trực tiếp `dataSource.getConnection()`, tự đóng hoặc tự điều chỉnh auto-commit không đúng chỗ, bạn có thể bỏ qua cơ chế Spring hoặc làm hỏng resource lifecycle. Với code business thông thường, hãy dùng `JdbcTemplate`, repository hoặc transaction-aware abstraction thay vì tự quản lý connection; demo dưới đây cầm connection để **quan sát một cách có kiểm soát**.

### 4.3. Resource binding diễn ra trên thread imperative

`TransactionSynchronizationManager` dùng context gắn với thread cho mô hình imperative. Nếu nhảy sang `@Async`, tự tạo thread hoặc executor khác, context của thread ban đầu **không tự chuyển sang**. Reactive Spring dùng cơ chế khác dựa trên Reactor context; không áp dụng phép so sánh `ThreadLocal` của demo JDBC trực tiếp cho R2DBC.

## 5. Ba chế độ synchronization của transaction manager

`AbstractPlatformTransactionManager` định nghĩa những mức kích hoạt transaction synchronization sau:

| Chế độ | Không có physical transaction khi SUPPORTS | Có actual transaction |
| --- | --- | --- |
| `SYNCHRONIZATION_ALWAYS` | **Có thể kích hoạt synchronization scope**, dù là “empty” transaction | Kích hoạt synchronization |
| `SYNCHRONIZATION_ON_ACTUAL_TRANSACTION` | Không kích hoạt synchronization mới chỉ vì SUPPORTS | Kích hoạt synchronization khi có T |
| `SYNCHRONIZATION_NEVER` | Không kích hoạt | Manager không kích hoạt synchronization kể cả khi có T |

Theo mặc định của `AbstractPlatformTransactionManager`, synchronization mode là **ALWAYS**. Tuy nhiên, framework có nhiều loại transaction manager, nên phải đọc cấu hình thực tế thay vì giả sử mọi môi trường giống nhau.

Ví dụ Java configuration:

```java
DataSourceTransactionManager manager =
    new DataSourceTransactionManager(dataSource);

manager.setTransactionSynchronization(
    AbstractPlatformTransactionManager.SYNCHRONIZATION_ALWAYS);
```

Đây là **mảnh cấu hình**, cần import/bean và `DataSource`; trong demo ở dưới có một bean hoàn chỉnh dùng chính cấu hình này.

### 5.1. ALWAYS: synchronization dù không có T

Với `SUPPORTS` và không có actual transaction:

```text
isActualTransactionActive() = false
isSynchronizationActive()   = true
```

Sau khi `DataSourceUtils.getConnection` lấy connection, manager/utility có thể bind holder vào synchronization scope; `JdbcTemplate` của những lớp cùng thread có thể dùng lại connection ấy.

Một `TransactionSynchronization` callback được gọi theo lifecycle **không nên được hiểu là bằng chứng đã có physical DB commit**. Với “empty” synchronization scope, không có `doCommit` vật lý để tác động lên các câu SQL đã auto-commit. Vì vậy, không dùng cờ sync hay callback đơn lẻ làm bảo đảm nghiệp vụ “sau commit”.

### 5.2. ON_ACTUAL_TRANSACTION: chỉ synchronization khi có T

Với cấu hình:

```java
manager.setTransactionSynchronization(
    AbstractPlatformTransactionManager.SYNCHRONIZATION_ON_ACTUAL_TRANSACTION);
```

nếu một `SUPPORTS` method không có physical transaction bên ngoài, nó không tạo synchronization scope mới:

```text
isActualTransactionActive() = false
isSynchronizationActive()   = false
```

Khi không có synchronization, một `DataSourceUtils.getConnection()` thường không bind một connection cho toàn scope theo kiểu ALWAYS. Không nên dự đoán hai lời gọi JDBC khác nhau sẽ có cùng Java connection object. Nhưng **bản thân không có synchronization cũng không tự bật transaction**: SQL với auto-commit=true vẫn có thể commit riêng, giống như trong demo SUPPORTS phía dưới.

Chế độ `ON_ACTUAL_TRANSACTION` đặc biệt đáng cân nhắc nếu kiến trúc **lồng một lời gọi REQUIRED/REQUIRES_NEW bên trong SUPPORTS** và gặp xung đột synchronization. Javadoc của Spring cảnh báo cần thận trọng khi lồng các propagation đó vào một SUPPORTS scope không có physical transaction; hãy test tính tương thích của manager/tài nguyên. Đây là lựa chọn cấu hình **ở cấp transaction manager**, không phải một thuộc tính trực tiếp của `@Transactional`.

### 5.3. NEVER: không kích hoạt synchronization

`SYNCHRONIZATION_NEVER` tắt việc manager kích hoạt synchronization ngay cả khi có actual transaction. Đây là cấu hình đặc biệt dành cho nhu cầu tích hợp cụ thể; nó **không đồng nghĩa tắt transaction vật lý**. Đừng bật chỉ để thay đổi một chỉ báo `syncActive` mà không hiểu hạ tầng JDBC/ORM và resource handling.

### 5.4. Một môi trường có nhiều manager

Spring cảnh báo không có nghĩa cho nhiều transaction manager **đồng thời cùng sở hữu thread-bound synchronization**. Nếu sử dụng JDBC manager, JPA manager, JMS manager hoặc JTA manager trong cùng call chain, hãy xác định ai quản lý synchronization, tài nguyên nào được bind và manager nào được annotation chọn. Một manager bật `SYNCHRONIZATION_ALWAYS` **không biến nhiều cơ sở dữ liệu thành một distributed transaction**.

## 6. Dự án thực hành đầy đủ: hai INSERT, cùng connection, hai kết quả rollback khác nhau

Ta tạo một chương trình Java 17+ dùng **Spring Boot 3.3.13, Spring JDBC, Spring AOP và H2 in-memory**. Có hai tình huống có thể so sánh trực tiếp:

- **Trường hợp S — SUPPORTS không có physical transaction:** method ngoài và method trong đều SUPPORTS; synchronization active, cùng JDBC connection, auto-commit=true; cả hai INSERT còn trong DB dù method ngoài ném `IllegalStateException`.
- **Trường hợp R — REQUIRED ngoài, SUPPORTS trong:** outer mở physical transaction; inner SUPPORTS tham gia T, dùng cùng connection đã chuyển auto-commit=false; outer ném `IllegalStateException`; cả hai INSERT bị rollback.

Thí nghiệm giữ nguyên công việc của inner (một câu INSERT) nhưng thay đổi **bối cảnh transaction của outer**, để isolating variable là “physical transaction đã có hay chưa”.

### 6.1. Các file của dự án

```text
supports-sync-demo/
├── settings.gradle
├── build.gradle
└── src/main/
    ├── java/learning/supports/
    │   ├── SupportsApplication.java
    │   ├── SupportsFacade.java
    │   └── SupportsWorker.java
    └── resources/
        ├── application.properties
        └── schema.sql
```

Không cần controller HTTP; `CommandLineRunner` chạy hai thí nghiệm tuần tự khi ứng dụng khởi động.

**`settings.gradle`**

```groovy
rootProject.name = 'supports-sync-demo'
```

**`build.gradle`**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'learning'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.encoding = 'UTF-8'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    implementation 'org.springframework.boot:spring-boot-starter-aop'
    runtimeOnly 'com.h2database:h2'
}
```

Gradle 8.x tương thích, JDK 17 trở lên. Các dependency bổ sung Spring transaction infrastructure, JDBC, AOP và database embedded; không dùng `javac` thuần khi thiếu classpath Spring/H2.

**`src/main/resources/application.properties`**

```properties
spring.datasource.url=jdbc:h2:mem:supports_demo;DB_CLOSE_DELAY=-1
spring.datasource.driver-class-name=org.h2.Driver
spring.datasource.username=sa
spring.datasource.password=
spring.datasource.hikari.auto-commit=true
spring.sql.init.mode=always
spring.main.web-application-type=none
spring.main.banner-mode=off
```

Dòng `spring.datasource.hikari.auto-commit=true` làm điều kiện thí nghiệm **tường minh**. Hikari/DataSource cấp connection auto-commit cho thao tác **không có physical transaction**; `DataSourceTransactionManager` sẽ quản lý việc tắt auto-commit khi mở physical transaction mới. Không xem cấu hình auto-commit này là đề xuất cho mọi hệ thống; nó chỉ giúp minh họa khác biệt.

**`src/main/resources/schema.sql`**

```sql
CREATE TABLE demo_event (
    id INT PRIMARY KEY,
    description VARCHAR(80) NOT NULL
);
```

Mỗi trường hợp dùng id khác nhau (1,2 và 3,4). Nếu bảng khởi đầu trống, `COUNT(*)` sau scope sẽ thể hiện commit/rollback rõ. H2 in-memory tạo database mới cho mỗi lần khởi động JVM thông thường, miễn không có tiến trình cũ giữ database đó.

### 6.2. SupportsWorker: inner SUPPORTS nhận được connection đã bind

**`src/main/java/learning/supports/SupportsWorker.java`**

```java
package learning.supports;

import java.sql.Connection;
import java.sql.SQLException;
import javax.sql.DataSource;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceUtils;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionSynchronizationManager;

@Service
public class SupportsWorker {
    private final DataSource dataSource;
    private final JdbcTemplate jdbc;

    public SupportsWorker(DataSource dataSource, JdbcTemplate jdbc) {
        this.dataSource = dataSource;
        this.jdbc = jdbc;
    }

    @Transactional(propagation = Propagation.SUPPORTS)
    public void write(int id, Connection parentConnection)
            throws SQLException {
        Connection connection = DataSourceUtils.getConnection(dataSource);
        try {
            boolean physical =
                TransactionSynchronizationManager
                    .isActualTransactionActive();
            boolean sync =
                TransactionSynchronizationManager
                    .isSynchronizationActive();
            boolean bound =
                TransactionSynchronizationManager.hasResource(dataSource);
            boolean sameConnection = connection == parentConnection;

            System.out.println(
                "worker physical=" + physical +
                " sync=" + sync +
                " bound=" + bound +
                " sameConnection=" + sameConnection +
                " autoCommit=" + connection.getAutoCommit());

            jdbc.update(
                "INSERT INTO demo_event(id, description) VALUES (?, ?)",
                id, "written-by-worker"
            );
        } finally {
            DataSourceUtils.releaseConnection(connection, dataSource);
        }
    }
}
```

Lưu ý cách đặt mã:

- `SupportsWorker` là bean do Spring quản lý; method `write` public, không final và mang `SUPPORTS`.
- Lời gọi ở outer sử dụng **bean khác** được inject, nên đi qua proxy và transaction interceptor riêng.
- `DataSourceUtils.getConnection` lấy connection phù hợp thread-bound context. So sánh `connection == parentConnection` là test **đúng môi trường demo** vì cả hai lớp dùng **cùng một object DataSource** và cùng thread.
- `hasResource(dataSource)` cho biết đã có holder được bind cho key DataSource sau khi gọi `getConnection`.
- `releaseConnection` được gọi trong `finally`; nếu connection thuộc scope Spring đang quản lý, nó được dọn dẹp đúng vòng đời chứ không bị business code đóng sai cách.
- `JdbcTemplate` dùng cách kết nối tương thích với Spring, nên câu INSERT có thể đi qua connection đã bind.

**Chúng ta không dùng `Connection.close()` trực tiếp** trong inner và không tự đặt auto-commit; làm vậy có thể phá resource management của transaction manager. Việc cầm JDBC connection ở đây chỉ nhằm quan sát trong bài học, không phải cách viết mặc định cho business service.

### 6.3. SupportsFacade: thay bối cảnh ngoài, không đổi inner

**`src/main/java/learning/supports/SupportsFacade.java`**

```java
package learning.supports;

import java.sql.Connection;
import java.sql.SQLException;
import javax.sql.DataSource;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceUtils;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionSynchronizationManager;

@Service
public class SupportsFacade {
    private final DataSource dataSource;
    private final JdbcTemplate jdbc;
    private final SupportsWorker worker;

    public SupportsFacade(
            DataSource dataSource, JdbcTemplate jdbc,
            SupportsWorker worker) {
        this.dataSource = dataSource;
        this.jdbc = jdbc;
        this.worker = worker;
    }

    @Transactional(propagation = Propagation.SUPPORTS)
    public void noPhysicalTransaction() throws SQLException {
        Connection connection = DataSourceUtils.getConnection(dataSource);
        try {
            printStatus("support", connection);

            jdbc.update(
                "INSERT INTO demo_event(id, description) VALUES (?, ?)",
                1, "support-outer"
            );
            worker.write(2, connection);

            throw new IllegalStateException("no-physical");
        } finally {
            DataSourceUtils.releaseConnection(connection, dataSource);
        }
    }

    @Transactional(propagation = Propagation.REQUIRED)
    public void physicalTransaction() throws SQLException {
        Connection connection = DataSourceUtils.getConnection(dataSource);
        try {
            printStatus("required", connection);

            jdbc.update(
                "INSERT INTO demo_event(id, description) VALUES (?, ?)",
                3, "required-outer"
            );
            worker.write(4, connection);

            throw new IllegalStateException("physical-failure");
        } finally {
            DataSourceUtils.releaseConnection(connection, dataSource);
        }
    }

    private static void printStatus(
            String label, Connection connection) throws SQLException {
        boolean physical =
            TransactionSynchronizationManager
                .isActualTransactionActive();
        boolean sync =
            TransactionSynchronizationManager
                .isSynchronizationActive();
        boolean bound =
            TransactionSynchronizationManager
                .hasResource(DataSourceForLogHolder.key());
    }
}
```

Phần `printStatus` ở cuối sẽ được thay bằng triển khai hoàn chỉnh ngay dưới đây, để không dùng biến/hàm không tồn tại. Bản Java **hoàn chỉnh sử dụng một implementation duy nhất**:

```java
package learning.supports;

import java.sql.Connection;
import java.sql.SQLException;
import javax.sql.DataSource;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceUtils;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionSynchronizationManager;

@Service
public class SupportsFacade {
    private final DataSource dataSource;
    private final JdbcTemplate jdbc;
    private final SupportsWorker worker;

    public SupportsFacade(
            DataSource dataSource, JdbcTemplate jdbc,
            SupportsWorker worker) {
        this.dataSource = dataSource;
        this.jdbc = jdbc;
        this.worker = worker;
    }

    @Transactional(propagation = Propagation.SUPPORTS)
    public void noPhysicalTransaction() throws SQLException {
        Connection connection = DataSourceUtils.getConnection(dataSource);
        try {
            printStatus("support", connection);

            jdbc.update(
                "INSERT INTO demo_event(id, description) VALUES (?, ?)",
                1, "support-outer"
            );
            worker.write(2, connection);

            throw new IllegalStateException("no-physical");
        } finally {
            DataSourceUtils.releaseConnection(connection, dataSource);
        }
    }

    @Transactional(propagation = Propagation.REQUIRED)
    public void physicalTransaction() throws SQLException {
        Connection connection = DataSourceUtils.getConnection(dataSource);
        try {
            printStatus("required", connection);

            jdbc.update(
                "INSERT INTO demo_event(id, description) VALUES (?, ?)",
                3, "required-outer"
            );
            worker.write(4, connection);

            throw new IllegalStateException("physical-failure");
        } finally {
            DataSourceUtils.releaseConnection(connection, dataSource);
        }
    }

    private void printStatus(
            String label, Connection connection) throws SQLException {
        boolean physical =
            TransactionSynchronizationManager
                .isActualTransactionActive();
        boolean sync =
            TransactionSynchronizationManager
                .isSynchronizationActive();
        boolean bound =
            TransactionSynchronizationManager.hasResource(dataSource);

        System.out.println(
            label + " physical=" + physical +
            " sync=" + sync +
            " bound=" + bound +
            " autoCommit=" + connection.getAutoCommit());
    }
}
```

**Chỉ tạo file `SupportsFacade.java` từ block Java thứ hai**, block đầu là bước giải thích cấu trúc đã được hoàn thiện. Không đặt cả hai vào cùng file. Nhờ có `printStatus` là instance method, nó truy cập được field `dataSource` để kiểm tra đúng resource key.

Hai method khác nhau chỉ ở propagation của outer. Trong cả hai, inner luôn là `@Transactional(SUPPORTS)` và cùng ghi một câu INSERT. Điều này cho phép **kiểm chứng đúng nguyên nhân của khác biệt về rollback**: có hay không có physical transaction được outer mở.

### 6.4. SupportsApplication: bật transaction advice và chạy SQL readback

**`src/main/java/learning/supports/SupportsApplication.java`**

```java
package learning.supports;

import javax.sql.DataSource;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.annotation.EnableTransactionManagement;
import org.springframework.transaction.support.AbstractPlatformTransactionManager;

@SpringBootApplication
@EnableTransactionManagement(proxyTargetClass = true)
public class SupportsApplication {
    public static void main(String[] args) {
        SpringApplication.run(SupportsApplication.class, args);
    }

    @Bean
    PlatformTransactionManager transactionManager(DataSource dataSource) {
        DataSourceTransactionManager manager =
            new DataSourceTransactionManager(dataSource);

        manager.setTransactionSynchronization(
            AbstractPlatformTransactionManager.SYNCHRONIZATION_ALWAYS);

        return manager;
    }

    @Bean
    CommandLineRunner demo(SupportsFacade facade, JdbcTemplate jdbc) {
        return args -> {
            try {
                facade.noPhysicalTransaction();
            } catch (IllegalStateException ex) {
                System.out.println("support caught=" + ex.getMessage());
            }
            System.out.println("support rows=" + count(jdbc, 1, 2));

            try {
                facade.physicalTransaction();
            } catch (IllegalStateException ex) {
                System.out.println("required caught=" + ex.getMessage());
            }
            System.out.println("required rows=" + count(jdbc, 3, 4));
        };
    }

    private static int count(JdbcTemplate jdbc, int firstId, int lastId) {
        Integer result = jdbc.queryForObject(
            "SELECT COUNT(*) FROM demo_event WHERE id BETWEEN ? AND ?",
            Integer.class,
            firstId,
            lastId
        );
        return result;
    }
}
```

**Giải thích cấu hình:**

- `@SpringBootApplication` quét `SupportsFacade` và `SupportsWorker` cùng package; Spring tạo các bean thay vì business code dùng `new`.
- `@EnableTransactionManagement(proxyTargetClass = true)` giúp chúng ta có proxy class-based phù hợp cho các class không triển khai interface.
- `transactionManager` là **một bean** `DataSourceTransactionManager` gắn đúng `DataSource` dùng bởi `JdbcTemplate`.
- `setTransactionSynchronization(SYNCHRONIZATION_ALWAYS)` khiến thí nghiệm SUPPORTS không có backend transaction vẫn có synchronization scope, không cần dựa vào cấu hình mặc định ẩn.
- `CommandLineRunner` **không** mang annotation `@Transactional` nên hai phép thử chạy độc lập. Count chỉ được thực hiện sau khi method facade đã trả về hoặc exception đã đi qua proxy.
- `count(jdbc,1,2)` và `count(jdbc,3,4)` kiểm tra những id khác nhau, tránh đọc nhầm dữ liệu của ca trước.

Mã Java trong ba file cùng package, tên class/public class khớp tên file. `SQLException` của facade có thể truyền từ các method ra runner; method `CommandLineRunner.run` khai báo `throws Exception` nên lambda trong `@Bean` compile được. Ở điều kiện demo bình thường, không có SQLException nên chỉ `IllegalStateException` chủ động được bắt.

### 6.5. Chạy dự án

Tại thư mục `supports-sync-demo`, với JDK 17+ và Gradle 8.x tương thích:

```bash
gradle bootRun
```

Nếu đã tạo Gradle Wrapper tương thích, dùng `./gradlew bootRun` trên Linux/macOS hoặc `gradlew.bat bootRun` trên Windows. Dependencies Spring/H2 phải được tải vào Gradle cache (cần mạng lần đầu); không dùng `javac SupportsApplication.java` thuần vì thiếu thư viện.

Khi chạy, bỏ qua những log từ Gradle, Hikari và Spring Boot. Các dòng do chương trình in theo thứ tự là:

```text
support physical=false sync=true bound=true autoCommit=true
worker physical=false sync=true bound=true sameConnection=true autoCommit=true
support caught=no-physical
support rows=2
required physical=true sync=true bound=true autoCommit=false
worker physical=true sync=true bound=true sameConnection=true autoCommit=false
required caught=physical-failure
required rows=0
```

Bảng diễn giải chính:

| Phép đo | SUPPORTS không có T | REQUIRED ngoài + SUPPORTS trong |
| --- | --- | --- |
| `isActualTransactionActive()` | `false` | `true` |
| `isSynchronizationActive()` | `true` | `true` |
| `hasResource(dataSource)` sau `getConnection` | `true` | `true` |
| `worker` nhận đúng object connection của outer | `true` | `true` |
| `Connection.getAutoCommit()` | `true` | `false` |
| Hai INSERT rồi RuntimeException thoát qua facade proxy | Không có T để rollback; SQL đã auto-commit | Transaction vật lý rollback hai INSERT |
| SQL count sau method kết thúc | `2` | `0` |

**Kết quả quan trọng nhất không phải `sameConnection=true`; mà là cùng `sameConnection=true` nhưng `rows=2` trong một ca và `rows=0` ở ca khác.** Nó chứng minh việc bind/share connection cho synchronization **không** tự tạo physical transaction hoặc atomic rollback guarantee.

## 7. Đi sâu từng bước của thí nghiệm SUPPORTS

### 7.1. SUPPORTS không có physical transaction

Khi runner gọi `facade.noPhysicalTransaction()`:

1. Không có transaction từ caller; `SUPPORTS` **không mở JDBC transaction mới**.
2. Với `SYNCHRONIZATION_ALWAYS`, interceptor/manager khởi tạo synchronization scope. Quan sát `physical=false, sync=true`.
3. `DataSourceUtils.getConnection(dataSource)` lấy H2 connection auto-commit=true và bind vào thread. `hasResource(dataSource)` trở thành true.
4. `JdbcTemplate` INSERT id=1 qua connection đang bind. H2 commit câu lệnh đó theo auto-commit.
5. `worker.write(2,connection)` đi qua proxy với SUPPORTS; không có physical transaction, nhưng kế thừa synchronization scope, lấy lại cùng connection và INSERT id=2. Câu lệnh thứ hai cũng auto-commit.
6. Facade ném `IllegalStateException`. Transaction interceptor nhận lỗi runtime nhưng **không có physical transaction để rollback**. Nó cleanup synchronization/resource.
7. Runner bắt exception, đọc DB: cả id=1 và id=2 **vẫn tồn tại**, `support rows=2`.

Vậy exception runtime trong một method mang `@Transactional(SUPPORTS)` **không có nghĩa dữ liệu rollback**. Rollback rule chỉ có khả năng hoàn tác transaction vật lý thực sự đang quản lý; nếu mọi INSERT đã auto-commit thì việc báo lỗi cuối method quá muộn để hủy chúng.

### 7.2. REQUIRED ngoài, SUPPORTS trong

Sau đó runner gọi `facade.physicalTransaction()`:

1. Không có transaction từ caller, nên `REQUIRED` tạo physical transaction T; `DataSourceTransactionManager` dùng connection có `autoCommit=false`.
2. Facade INSERT id=3 **chưa commit**.
3. `worker.write(4,connection)` qua proxy, `SUPPORTS` thấy T đã có và **tham gia T**. Worker nhận cùng connection, INSERT id=4 cũng thuộc T.
4. Facade ném `IllegalStateException` thoát qua proxy ngoài. Spring đánh giá rollback rule mặc định cho RuntimeException và yêu cầu rollback T.
5. Cả hai INSERT trong T bị rollback.
6. Runner đọc sau transaction: `required rows=0`.

Ở trường hợp này, **inner SUPPORTS đang thực sự nằm trong physical transaction**, nhưng vì **outer đã tạo nó**, không phải vì SUPPORTS tự khởi động T.

### 7.3. Tại sao không nhìn count khi còn trong scope?

Nếu gọi `SELECT COUNT(*)` trong facade trước khi ném exception, JDBC transaction T có thể đọc thấy id=3, id=4 do chính mình vừa ghi (*read-your-writes*). Điều đó **không chứng minh commit**. Sau rollback, DB không còn hai record.

Ngược lại, trong case SUPPORTS không T, SQL auto-commit khiến record đã có thể bền vững trước exception. Đặt readback ở runner **sau khi facade proxy kết thúc** mới giúp hai trường hợp có bằng chứng so sánh tin cậy.

### 7.4. Sao không chỉ dựa vào Throwable?

Cả hai facade đều ném cùng loại `IllegalStateException`, đều được caller catch và đều dùng Spring transaction advice. Chỉ dựa vào exception class, ta **không** phân biệt được kết quả database.

Chính physical transaction boundary (có hoặc không) quyết định exception có thể khiến Spring rollback các SQL hay không. Kết quả `2 vs 0` là quan sát dữ liệu thực của demo trong điều kiện đã thiết kế.

## 8. Thử thay SYNCHRONIZATION_ALWAYS bằng ON_ACTUAL_TRANSACTION

Để khám phá vai trò synchronization, tạo một bản sao dự án demo riêng hoặc sửa **duy nhất cấu hình manager**:

```java
manager.setTransactionSynchronization(
    AbstractPlatformTransactionManager.SYNCHRONIZATION_ON_ACTUAL_TRANSACTION);
```

Đây là thay đổi **trong project demo**, không áp dụng tùy tiện vào production. Với một SUPPORTS method không có physical transaction:

- `isActualTransactionActive()` vẫn `false`.
- `isSynchronizationActive()` sẽ `false`, vì manager không tạo synchronization scope cho “empty” transaction.
- `DataSourceUtils` không tự giữ một shared connection dựa trên synchronization scope của SUPPORTS; việc `sameConnection` có thể không còn true và còn phụ thuộc pool/driver/cách resource được lấy.
- `autoCommit=true` vẫn có thể giữ nguyên theo cấu hình Hikari của demo; các INSERT không được một T vật lý bao quanh.
- Exception cuối method vẫn không tự undo hai INSERT đã auto-commit; `support rows` vẫn có thể là 2 theo precondition demo.
- Trong case `REQUIRED`, transaction vật lý được tạo nên synchronization vẫn active, worker SUPPORTS vẫn tham gia T và rollback chung.

**Không ghi một output `sameConnection=false` bắt buộc cho cấu hình thay thế.** Chúng ta không thể bảo đảm identity connection được cấp bởi một pool cụ thể trong mọi cách gọi. Ý nghĩa của phép thay đổi là xem **synchronization scope có được tạo hay không**, không phải yêu cầu pool trả object khác nhau.

Nếu ứng dụng có nhiều lớp transaction hoặc lồng `REQUIRED` trong `SUPPORTS`, Spring Javadoc khuyến nghị cân nhắc chế độ synchronization chỉ khi có actual transaction để tránh một số xung đột tại runtime. Cần kiểm thử trường hợp cụ thể trên manager đang sử dụng.

## 9. SUPPORTS có thể “không transaction” nhưng vẫn có synchronization callback

Khi synchronization active, code framework có thể đăng ký `TransactionSynchronization` cho lifecycle resource hoặc callback. Tuy nhiên, với `SUPPORTS` không có backend transaction:

- Không được suy luận từ việc callback được đăng ký rằng đã có lệnh DB `BEGIN`.
- Không được suy luận từ tên một callback “afterCommit” rằng manager vừa commit một physical transaction. Lifecycle của synchronization scope và transaction vật lý phải được phân biệt.
- Không dựa vào callback để phát một event **chỉ khi record thật sự commit** nếu đang chạy dưới “empty” synchronization scope mà chưa xác định semantics của manager.
- Nếu nghiệp vụ cần sự kiện sau commit DB, nên xác định có actual transaction, sử dụng callback đúng ngữ cảnh hoặc thiết kế outbox/transactional event phù hợp.

Đăng ký callback cho resource cleanup là khả năng hạ tầng, không phải bảo đảm ACID. Khi author thư viện chung, điều kiện `isSynchronizationActive()` không đủ để quyết định liệu các thay đổi DB có thể rollback được hay chưa; phải cân nhắc `isActualTransactionActive()` và manager/resource đang dùng.

## 10. readOnly, timeout và isolation trong SUPPORTS

### 10.1. readOnly không thay thế transaction vật lý

Ví dụ:

```java
@Transactional(
    propagation = Propagation.SUPPORTS,
    readOnly = true
)
public List<OrderView> findOrders() {
    return repository.findOrders();
}
```

Đây là mảnh minh họa, thiếu repository và type domain. Với một physical transaction **đã có**, SUPPORTS tham gia và thường dùng characteristics của outer transaction; read-only khai báo inner không tự đổi trạng thái DB transaction đã mở (manager có thể validate mismatch theo cấu hình).

Nếu **không có physical transaction**, Spring có thể ghi nhận **read-only metadata trong synchronization scope**, nhưng điều đó không chứng minh JDBC connection đã được đưa vào một DB transaction chỉ đọc. Thông thường, read-only là hint/optimization hoặc enforcement phụ thuộc driver, manager và DB. Không dùng một boolean trên `TransactionSynchronizationManager` như rào bảo mật cấm INSERT.

### 10.2. Timeout/isolation có tác dụng khi manager mở T

`isolation` và `timeout` của `@Transactional` thường có ý nghĩa cho **transaction vật lý mới**, đặc biệt với `REQUIRED` hoặc `REQUIRES_NEW`. SUPPORTS không tạo T khi chưa có, nên không thể tùy tiện mong một timeout transaction hoặc isolation level được DB áp dụng.

Nếu SUPPORTS tham gia outer T, isolation/timeout đã được xác lập bởi transaction vật lý của outer thường vẫn có hiệu lực; inner không tự chuyển isolation của connection đang được manager quản lý. Với `validateExistingTransaction=true`, một manager có thể phát hiện mismatch isolation/read-only và từ chối tham gia thay vì bỏ qua ngầm.

### 10.3. Không nên dùng SUPPORTS chỉ để “đỡ lock”

Một SELECT không có physical transaction vẫn chịu hành vi isolation/auto-commit riêng của DB; không phải mọi truy vấn đều miễn lock hoặc không chịu concurrency anomaly. Một synchronization scope có thể còn giữ connection đến cuối method, gây áp lực pool dù không có T dài. Đo thời gian query, connection lifetime và tính nhất quán của dữ liệu theo DB cụ thể.

Nếu use case cần snapshot nhiều truy vấn phải nhất quán, `REQUIRED` read-only với isolation phù hợp có thể là lựa chọn tốt hơn SUPPORTS. Nếu chỉ cần một truy vấn độc lập, SUPPORTS hoặc không annotation có thể đủ tùy hạ tầng và quy ước codebase.

## 11. SUPPORTS so với REQUIRED, NOT_SUPPORTED, MANDATORY và NEVER

| Propagation | Khi outer đã có T | Khi outer không có T | Điểm phân biệt |
| --- | --- | --- | --- |
| `SUPPORTS` | Tham gia T | Không tạo physical T; có thể tạo synchronization scope | Linh hoạt theo caller, atomicity phụ thuộc caller |
| `REQUIRED` | Tham gia T | Tạo physical T mới | Bảo đảm có transaction trong lời gọi được intercept |
| `REQUIRES_NEW` | Suspend outer và tạo T2 mới | Tạo physical T mới | Có thể commit/rollback độc lập |
| `NOT_SUPPORTED` | Suspend T và chạy không có physical T | Chạy không có physical T | Chủ động **tránh** tham gia transaction outer |
| `MANDATORY` | Tham gia T | Báo lỗi nếu thiếu T | Ép caller cung cấp transaction |
| `NEVER` | Báo lỗi nếu có T | Chạy không có physical T | Chủ động từ chối transaction |

**Đừng đánh đồng SUPPORTS và NOT_SUPPORTED.** Khi outer có T, SUPPORTS **tham gia T**, còn NOT_SUPPORTED **suspend T**. Không phải “đều không mở transaction mới nên giống nhau”.

**Đừng đánh đồng SUPPORTS và MANDATORY.** SUPPORTS vẫn chạy khi chưa có physical T; MANDATORY chủ động báo lỗi để bảo vệ precondition của use case.

**Đừng đánh đồng SUPPORTS và “không viết annotation”.** Trong mode `SYNCHRONIZATION_ALWAYS`, SUPPORTS có thể mở một synchronization scope ngay cả khi không có DB transaction. Một method Java hoàn toàn không được transaction advice intercept thường không tự tạo scope tương tự, trừ khi caller/hạ tầng khác đã mở nó.

## 12. Lồng propagation: nơi SUPPORTS dễ gây hiểu nhầm

### 12.1. Outer REQUIRED gọi inner SUPPORTS

Đây là mô hình **an toàn để hiểu nhất**: outer đã tạo T, inner tham gia T; nếu outer rollback thì các SQL của inner thuộc cùng T cũng rollback. Trường hợp R trong demo xác nhận bằng dữ liệu.

Không có yêu cầu SUPPORTS phải dùng JDBC; với JPA cũng có thể tham gia một transaction phù hợp qua manager, nhưng resource/session behavior cần kiểm tra manager/ORM tương ứng.

### 12.2. Outer SUPPORTS không T gọi inner REQUIRED

Ví dụ kiến trúc:

```java
@Transactional(propagation = Propagation.SUPPORTS)
public void orchestrate() {
    readSomeData();
    writeService.writeTransactionally(); // REQUIRED bean khác
}
```

Đây là mã minh họa. Khi outer không có T nhưng đã kích hoạt synchronization, việc inner REQUIRED cố mở physical transaction có thể dẫn đến **tương tác phức tạp với resource đã được bind**; Javadoc của Spring cảnh báo cần dùng SUPPORTS cẩn thận khi lồng REQUIRED hoặc REQUIRES_NEW và gợi ý mode synchronization chỉ khi có actual transaction khi cần thiết.

Không mô tả case này bằng câu đơn giản “REQUIRED chắc chắn tạo T và mọi thứ đều ổn” khi resource đã tồn tại từ scope SUPPORTS. Tốt hơn là **đặt transaction boundary trực tiếp ở use case write**, tách phần đọc và phần ghi rõ ràng, hoặc cấu hình/test synchronization mode phù hợp với manager đang dùng.

### 12.3. Outer SUPPORTS không T gọi inner REQUIRES_NEW

Một inner REQUIRES_NEW có thể mở physical T riêng, nhưng nếu outer đang có “empty” synchronization scope giữ connection, việc suspend/resume synchronization và connection lifecycle cần được manager thực thi đúng. Có thể tăng nhu cầu pool connection. Nếu inner commit rồi outer tiếp tục các câu SQL không transaction, **không có atomicity chung** giữa chúng.

### 12.4. Self-invocation không tạo advice riêng

`@Transactional` trong proxy mode là metadata chỉ được áp dụng khi lời gọi đi qua Spring proxy. Nếu trong cùng bean dùng `this.innerSupports()`, inner method **không có transaction advisor invocation riêng**, dù nó có thể tiếp tục dùng transaction/synchronization của outer đang active.

Để kiểm chứng two-scope semantics, hãy dùng **hai bean Spring khác nhau** như `SupportsFacade` và `SupportsWorker`. Đừng dùng `new SupportsWorker(...)` rồi cho rằng annotation sẽ mở synchronization scope.

## 13. Khi nào SUPPORTS có giá trị trong thiết kế thật?

### 13.1. Service đọc được gọi ở cả hai bối cảnh

Một query service có thể được gọi từ một use case đã có transaction và từ một endpoint độc lập:

```text
HTTP endpoint -> ReportService.findSummary() [SUPPORTS, không T]
Order workflow [REQUIRED T] -> ReportService.findSummary() [SUPPORTS, tham gia T]
```

Khi caller có T, report service đọc trong cùng transaction, có thể thấy những cập nhật chưa commit của caller. Khi caller không có T, report không tự mở physical transaction mới. Đây có thể là lựa chọn có chủ đích cho các query đơn giản.

Nhưng nếu hai môi trường cần mức nhất quán rất khác nhau, việc dùng cùng một contract SUPPORTS có thể gây khó dự đoán. Hãy ghi rõ precondition hoặc tách API truy vấn độc lập với query phục vụ transaction nghiệp vụ.

### 13.2. Resource sharing trong một request/service scope

Một số ứng dụng muốn nhiều thao tác JDBC/Hibernate trong một phạm vi dùng lại resource mà không ép mọi truy vấn thành một transaction vật lý. Với `SYNCHRONIZATION_ALWAYS`, SUPPORTS có thể hỗ trợ resource lifecycle đó.

Đổi lại, resource có thể được giữ đến cuối scope, tạo ảnh hưởng tới pool và latency. Nên đo tài nguyên thực tế; không xem resource sharing là lợi ích miễn phí.

### 13.3. Phân biệt khả năng tiếp tục và tính atomic

SUPPORTS có thể giúp một phương thức “dùng transaction nếu caller có”. Nó không nói rằng mọi thao tác bên trong được phép thất bại một phần. Nếu nghiệp vụ **không chấp nhận partial write**, không nên để một method ghi nhiều bước chạy dưới SUPPORTS mà không có outer transaction.

Đặc biệt, đừng dùng SUPPORTS cho một lệnh tạo đơn ghi nhiều bảng với giả định “có `@Transactional` nên rollback”. Nếu các bước cần cùng commit, dùng `REQUIRED` ở boundary đúng và test rollback từ caller thực.

## 14. Những lỗi phổ biến và cách chẩn đoán

### Lỗi 1 — Thấy syncActive=true rồi khẳng định đang có DB transaction

Sai: `isSynchronizationActive()` đo synchronization scope; với SUPPORTS không T, nó vẫn có thể true. Phải kiểm tra `isActualTransactionActive()` và connection/manager thực.

### Lỗi 2 — Thấy cùng JDBC Connection rồi tin hai INSERT sẽ rollback cùng nhau

Sai: khi connection auto-commit=true, từng INSERT có thể commit riêng. Test `SUPPORTS` của demo cho cùng connection nhưng `rows=2` sau RuntimeException.

### Lỗi 3 — Chỉ assert exception mà không kiểm tra DB

Một `IllegalStateException` được ném cả ở trường hợp SUPPORTS và REQUIRED, nhưng dữ liệu còn lại khác hẳn. Đọc SQL **sau khi method đã kết thúc** mới đánh giá đúng.

### Lỗi 4 — Đặt @Transactional(SUPPORTS) lên method ghi nhiều bước cần atomic

Nếu caller không có T, SUPPORTS không tự tạo T. Nên đặt `REQUIRED` trên use case boundary, hoặc xác định phương thức bắt buộc được gọi trong T bằng `MANDATORY`.

### Lỗi 5 — Dùng raw dataSource.getConnection hoặc close sai cách

Có thể tạo connection ngoài thread-bound resource và phá cơ chế đồng bộ; nên dùng `JdbcTemplate`/`DataSourceUtils` hoặc infrastructure data access phù hợp, release resource đúng cách.

### Lỗi 6 — Dùng readOnly=true làm tín hiệu chắc chắn DB đang ở transaction read-only

Read-only metadata trong synchronization scope không bảo đảm physical transaction tồn tại. Kiểm tra manager/driver/DB và quyền dữ liệu thật.

### Lỗi 7 — Tự mở thread trong SUPPORTS

Thread mới không tự kế thừa transaction synchronization của thread hiện tại trong imperative Spring. Kết quả `syncActive` và resource reuse có thể đổi.

### Lỗi 8 — Đổi synchronization mode mà không test library phụ thuộc resource binding

`SYNCHRONIZATION_ON_ACTUAL_TRANSACTION` làm SUPPORTS không T không tạo synchronization scope. Một số library dựa vào holder/callback có thể ứng xử khác. Test theo luồng end-to-end.

### Lỗi 9 — Tưởng SUPPORTS và NOT_SUPPORTED tương đương

Khi có outer transaction, SUPPORTS tham gia còn NOT_SUPPORTED suspend. Điều này ảnh hưởng SQL visibility, rollback và resource handling.

### Lỗi 10 — Chỉ test trong method test cũng @Transactional

Transaction của test có thể đã active, khiến mọi SUPPORTS tưởng như “luôn có T” và che tình huống rủi ro **không có physical transaction** trong production. Hãy kiểm chứng cả đường gọi không có outer T.

## 15. Cách kiểm thử đúng, không bị kết quả giả

Một test tốt cho SUPPORTS phải tách hai câu hỏi:

**Câu hỏi 1: Synchronization/resource sharing có diễn ra không?**

- Gọi một method `@Transactional(SUPPORTS)` không có transaction ngoài.
- In `isSynchronizationActive()` và `isActualTransactionActive()`.
- Lấy connection bằng `DataSourceUtils` ở facade, truyền tham chiếu vào worker, so sánh với connection worker lấy từ cùng DataSource.
- So sánh `getAutoCommit()` để biết điều kiện DB của thí nghiệm.
- Đổi manager mode từ ALWAYS sang ON_ACTUAL_TRANSACTION và quan sát sự khác biệt về synchronization.

**Câu hỏi 2: Các thay đổi SQL có rollback được không?**

- Trong cùng method, INSERT record ở hai lớp khác nhau rồi ném RuntimeException **sau khi INSERT**.
- Bắt exception **ở caller ngoài proxy**.
- Đọc lại DB sau khi scope đã kết thúc; với SUPPORTS không T và auto-commit=true, các record còn tồn tại.
- Đổi outer thành REQUIRED, giữ nguyên worker SUPPORTS; sau exception, các record thuộc T bị rollback.
- Không chỉ dùng `assertThrows` hay log; cần assert DB state.

### 15.1. Bẫy Spring TestContext

Nếu method test mang `@Transactional`, Spring TestContext có thể mở transaction và rollback cuối test. Khi đó SUPPORTS **tham gia transaction của test**, và phép thử không còn đại diện đường gọi production không có T.

Để test case “không có physical transaction”, hãy dùng test method **không có @Transactional**, gọi Spring bean qua proxy rồi kiểm chứng dữ liệu sau khi method ném exception. Nếu cần test nhiều scope, dùng `TestTransaction` cẩn thận để bắt đầu/kết thúc các transaction phù hợp.

### 15.2. Test cùng database nhưng khác resource key?

`TransactionSynchronizationManager.hasResource(dataSource)` lấy resource key là object `DataSource` cụ thể. Nếu code A dùng một proxy wrapper DataSource khác hoặc các bean được cấu hình không trùng key theo cách framework nhận diện, việc bind/reuse có thể không như mong đợi. Demo cố định cả ba class dùng một `DataSource` injection.

### 15.3. Test cả concurrent/long-running scope

Synchronization scope giữ connection có thể kéo dài dù không có transaction vật lý. Nếu một method SUPPORTS gọi API mạng rồi tiếp tục query, connection của nó có thể bị giữ trong lúc chờ. Với nhiều request đồng thời, cần giám sát Hikari active/idle/waiting, giới hạn thời gian và ranh giới data access để tránh pool starvation.

## 16. Logging và quan sát trong hệ thống đang chạy

Có thể bật log tạm để kiểm tra Spring transaction interceptor và JDBC manager:

```properties
logging.level.org.springframework.transaction.interceptor=TRACE
logging.level.org.springframework.jdbc.datasource.DataSourceTransactionManager=DEBUG
logging.level.org.springframework.jdbc.datasource.DataSourceUtils=DEBUG
```

Đây là **mảnh cấu hình debug tùy chọn**. Không cần thêm các dòng này vào `application.properties` của demo để đối chiếu `System.out` ở trên.

Khi đọc log, phân biệt:

- “Creating new transaction” trên manager khi outer REQUIRED thực sự bắt đầu physical T.
- “Participating in existing transaction” khi SUPPORTS được gọi trong T hiện hữu.
- Một SUPPORTS scope không có T có thể chỉ kích hoạt synchronization, không tương đương lệnh DB BEGIN.
- Resource binding/cleanup là lifecycle; không chứng minh commit.
- Nếu có lỗi trên DB, hãy xác minh kết quả SQL sau method — đặc biệt với lỗi commit/network khiến outcome chưa xác định.

Đừng bật log SQL chứa dữ liệu nhạy cảm trong production chỉ vì muốn biết propagation. Dùng trace được giới hạn và hạ mức log sau khi xác minh xong.

## 17. Checklist trước khi chọn SUPPORTS

Hãy trả lời:

1. Method này chỉ **đọc** hay có thể ghi nhiều bước cần atomicity?
2. Khi được gọi từ endpoint độc lập, **có physical transaction hiện hữu không**?
3. Có bắt buộc tham gia transaction nếu caller có không? Nếu cần transaction trong mọi trường hợp, `REQUIRED` có thể phù hợp hơn.
4. Transaction manager đang dùng bật synchronization mode nào: ALWAYS, ON_ACTUAL_TRANSACTION hay NEVER?
5. Các data access có dùng cùng `DataSource`/`EntityManagerFactory` và infrastructure quản lý resource không?
6. Service có cần chia sẻ connection/session trong một scope không có T không? Resource sẽ bị giữ bao lâu?
7. Có assumption nào rằng exception runtime sẽ rollback các bước ghi đã auto-commit không?
8. Có call chain lồng REQUIRED hoặc REQUIRES_NEW bên trong SUPPORTS không? Đã kiểm thử resource synchronization conflict chưa?
9. Có sử dụng `@Async`, thread khác hoặc tài nguyên ngoài DB mà transaction context không tự truyền sang không?
10. Test có **đọc trạng thái DB sau boundary**, cả với và không với outer transaction, thay vì chỉ kiểm tra exception?

**Nguyên tắc:** `SUPPORTS` là chính sách *“tham gia nếu có”*, không phải *“luôn có transaction nhưng nhẹ hơn”*. Synchronization giúp quản lý resource scope; transaction vật lý mới đem lại rollback/commit atomic của các thao tác DB thuộc scope ấy.

## 18. Câu hỏi tự kiểm tra

**Câu 1.** `@Transactional(SUPPORTS)` được gọi khi không có outer T, nhưng `isSynchronizationActive()==true`. Có chứng minh physical transaction đã bắt đầu không?

**Trả lời:** Không. Với `SYNCHRONIZATION_ALWAYS`, Spring có thể mở synchronization cho một “empty” SUPPORTS scope, trong khi `isActualTransactionActive()==false`.

**Câu 2.** Hai service SUPPORTS dùng cùng JDBC Connection. Nếu cuối method ném `IllegalStateException`, có chắc cả hai INSERT rollback?

**Trả lời:** Không. Nếu không có physical T và connection auto-commit=true, từng INSERT có thể đã commit riêng. Connection identity không bằng transaction atomicity.

**Câu 3.** Inner SUPPORTS được outer REQUIRED gọi qua Spring proxy, cùng DataSource. Inner có physical transaction không?

**Trả lời:** Nó **tham gia transaction vật lý mà outer đã mở**, không tạo T riêng. Outer rollback có thể hủy các SQL inner thuộc T.

**Câu 4.** Đổi transaction manager từ ALWAYS sang ON_ACTUAL_TRANSACTION, SUPPORTS không có T sẽ có syncActive như thế nào?

**Trả lời:** Spring không mở synchronization scope mới chỉ vì SUPPORTS, nên thường `syncActive=false` trong lời gọi độc lập. Actual transaction vẫn false.

**Câu 5.** `hasResource(dataSource)==true` cho biết điều gì?

**Trả lời:** Spring đã bind một resource vào current thread với DataSource key. Nó **không** chứng minh JDBC connection đang `autoCommit=false` hay DB đang có transaction vật lý.

**Câu 6.** SUPPORTS và NOT_SUPPORTED có giống nhau khi outer REQUIRED đã mở T không?

**Trả lời:** Không. SUPPORTS tham gia T; NOT_SUPPORTED chủ động suspend T và chạy không có physical transaction.

**Câu 7.** Khi nào nên ưu tiên REQUIRED thay SUPPORTS?

**Trả lời:** Khi use case cần bảo đảm một physical transaction cho nhiều bước ghi cùng commit/rollback, kể cả khi caller ban đầu không có transaction.

**Câu 8.** Vì sao không nên chỉ test SUPPORTS trong method test có `@Transactional`?

**Trả lời:** Vì test đã cung cấp outer transaction. SUPPORTS sẽ tham gia T của test, che trường hợp production gọi độc lập không có T.

**Câu 9.** Nếu một thư viện đăng ký synchronization callback trong SUPPORTS không T, có thể xem callback đó là proof of DB commit không?

**Trả lời:** Không. Có thể chỉ là lifecycle synchronization scope; cần kiểm tra actual transaction và DB commit thực tế.

## 19. Tài liệu tham khảo Spring chính thức

- `Propagation.SUPPORTS` Javadoc (gồm lưu ý synchronization scope): https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/transaction/annotation/Propagation.html
- `AbstractPlatformTransactionManager` Javadoc (SYNCHRONIZATION_ALWAYS, ON_ACTUAL_TRANSACTION, NEVER): https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/transaction/support/AbstractPlatformTransactionManager.html
- `TransactionSynchronizationManager` Javadoc: https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/transaction/support/TransactionSynchronizationManager.html
- `DataSourceUtils` Javadoc: https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/jdbc/datasource/DataSourceUtils.html
- Spring Framework — Declarative Transaction Implementation: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-decl-explained.html
- Spring Framework — Transaction Propagation: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html

**Kết luận:** `SUPPORTS` không mở transaction vật lý khi chưa có, nhưng **có thể** mở synchronization scope, bind và tái dùng JDBC Connection. Quan sát `sync=true, physical=false, sameConnection=true, autoCommit=true` và dữ liệu INSERT **vẫn còn sau exception** chính là minh chứng cho sự khác biệt giữa **đồng bộ hóa tài nguyên** và **transaction vật lý có rollback**. Khi outer `REQUIRED` mở T, cùng inner `SUPPORTS` lại tham gia T và các SQL có thể rollback chung; vì vậy transaction boundary phải được thiết kế theo yêu cầu nghiệp vụ, không chỉ dựa vào annotation hay synchronization flag.