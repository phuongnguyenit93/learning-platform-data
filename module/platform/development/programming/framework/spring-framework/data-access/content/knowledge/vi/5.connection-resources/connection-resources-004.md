# Vì sao gọi trực tiếp DataSource.getConnection() có thể bỏ qua kết nối gắn giao dịch

## 1. Vấn đề cần hiểu

Một phương thức service được đánh dấu `@Transactional` không có nghĩa **mọi Connection được tạo trong phương thức đó** tự động tham gia cùng transaction. Với Spring JDBC, transaction manager gắn một Connection vào ngữ cảnh giao dịch của luồng thực thi hiện hành. Những thành phần biết cơ chế này — ví dụ `JdbcTemplate` hoặc `DataSourceUtils.getConnection(dataSource)` — dùng lại Connection đã gắn. Ngược lại, lời gọi trực tiếp `dataSource.getConnection()` trên **DataSource gốc không có transaction-aware proxy** có thể xin một Connection khác từ pool, khiến câu SQL trên Connection đó nằm ngoài transaction đang được Spring quản lý.

Ví dụ: trong `@Transactional`, `JdbcTemplate` ghi bản ghi A; lập trình viên mở Connection bằng `HikariDataSource.getConnection()` và ghi bản ghi B; sau đó service ném ngoại lệ. Spring rollback bản ghi A, nhưng bản ghi B có thể vẫn tồn tại nếu Connection lấy trực tiếp bật `autoCommit=true`. Lỗi này làm một thao tác tưởng là atomic bị tách thành hai transaction độc lập.

**Mục tiêu:** nhận diện đúng nguyên nhân, hiểu cách Spring chọn và giữ Connection, phân biệt phương thức an toàn với lời gọi có thể bypass, quan sát bằng chương trình chạy được và biết cách sửa mà vẫn quản lý tài nguyên đúng.

> Phạm vi quan trọng: Kết luận “gọi trực tiếp sẽ bypass” đúng với DataSource gốc thông thường như `HikariDataSource` dùng trong ví dụ. **Không đúng tuyệt đối với mọi implementation của DataSource**: nếu người gọi nhận `TransactionAwareDataSourceProxy`, chính proxy đó làm `getConnection()` nhận được một Connection có hành vi nhận biết transaction của Spring. Cách khuyên dùng cho mã ứng dụng Spring JDBC vẫn là `JdbcTemplate` hoặc `DataSourceUtils`.

## 2. Hai lớp khái niệm: transaction logic và Connection thực tế

**Transaction logic** là ranh giới nghiệp vụ mà Spring đánh dấu khi một lời gọi đi qua interceptor của `@Transactional`. **Connection thực tế** là tài nguyên JDBC được một `DataSource` cung cấp để thực hiện câu SQL. Mọi câu SQL muốn cùng commit/rollback phải thực sự tham gia đúng tài nguyên của transaction.

Khi sử dụng transaction manager JDBC (`DataSourceTransactionManager` hoặc `JdbcTransactionManager`), luồng điển hình là:

1. Caller gọi phương thức service thông qua Spring proxy, interceptor bắt đầu transaction.
2. Transaction manager lấy Connection từ DataSource phù hợp, cấu hình transaction (ví dụ chuyển `autoCommit=false` khi cần), rồi gắn một `ConnectionHolder` vào ngữ cảnh tài nguyên của luồng.
3. `JdbcTemplate` gọi `DataSourceUtils.getConnection(dataSource)`. Utility này kiểm tra Connection đã gắn với cùng DataSource, rồi dùng lại Connection đó.
4. Các SQL thực thi thông qua Connection được quản lý; khi service hoàn tất, transaction manager commit hoặc rollback.
5. Spring hủy gắn kết tài nguyên, khôi phục trạng thái JDBC cần thiết và trả Connection về pool.

Spring lưu tài nguyên giao dịch trong `TransactionSynchronizationManager`, thường dựa vào ThreadLocal ở mô hình transaction JDBC đồng bộ. Đây là lý do một transaction thường gắn với luồng thực thi hiện tại; tự tạo thread mới hoặc chuyển sang `@Async` không mặc nhiên mang theo transaction JDBC cũ.

Hình dung:

~~~text
Thread xử lý yêu cầu
│
├── Spring @Transactional proxy
│    └── Transaction manager
│         └── ConnectionHolder gắn với DataSource chính
│              └── Connection #A (transaction Spring)
│
├── JdbcTemplate
│    └── DataSourceUtils.getConnection(DataSource chính)
│         └── tìm ConnectionHolder → Connection #A
│
└── DataSource chính.getConnection() [nếu gọi thẳng pool]
     └── pool cấp Connection #B (độc lập với Connection #A)
~~~

Vì cả `Connection #A` và `Connection #B` có thể kết nối cùng database, chúng có thể nhìn thấy dữ liệu **khác nhau** theo isolation level. Chúng cũng có thể commit/rollback **độc lập**.

## 3. Tại sao lời gọi trực tiếp bỏ qua tài nguyên được Spring gắn?

DataSource JDBC chuẩn định nghĩa `getConnection()` là cách **xin** một Connection. Nó không quy định phải truy vấn ThreadLocal của Spring hay tìm ConnectionHolder hiện hành. Ví dụ, một `HikariDataSource` lấy kết nối từ pool; nếu Connection #A đang được transaction manager giữ, một lần gọi mới có thể nhận Connection #B.

Trong cùng transaction logic:

~~~java
@Transactional
public void saveTwoEvents() throws SQLException {
    jdbcTemplate.update(
            "INSERT INTO events(id, description) VALUES (?, ?)",
            1, "through Spring");

    try (Connection raw = dataSource.getConnection()) {
        try (PreparedStatement ps = raw.prepareStatement(
                "INSERT INTO events(id, description) VALUES (?, ?)")) {
            ps.setInt(1, 2);
            ps.setString(2, "direct connection");
            ps.executeUpdate();
        }
    }

    throw new IllegalStateException("Force rollback");
}
~~~

Đây là **mã minh họa đặt trong một service đã khai báo các trường `JdbcTemplate jdbcTemplate` và `DataSource dataSource`**, không phải lớp Java độc lập. Vấn đề nằm tại `dataSource.getConnection()`: nếu dataSource là pool gốc, câu INSERT thứ hai có thể chạy trên Connection riêng, không nằm trong transaction của INSERT thứ nhất. Trong trường hợp mặc định `autoCommit=true` trên Connection mới, INSERT thứ hai đã commit trước khi Spring rollback transaction thứ nhất.

Điểm dễ nhầm: transaction manager **cũng gọi `DataSource.getConnection()` khi bắt đầu transaction**, nhưng sau đó **nó gắn Connection được cấp** để `DataSourceUtils` và các template dùng lại. Việc ứng dụng trực tiếp gọi `getConnection()` thêm một lần không tự đọc lại binding đó.

### Điều `@Transactional` bảo đảm — và điều nó không làm

`@Transactional` hoạt động thông qua interceptor/transaction manager trong cấu hình Spring thường gặp, giúp quản lý **tài nguyên đã đăng ký tham gia** transaction. Nó không tự chỉnh mọi đối tượng `Connection` mà ứng dụng tự mở; không tự biến JDBC SQL qua Connection độc lập thành cùng commit/rollback. Kiểm tra mỗi `TransactionSynchronizationManager.isActualTransactionActive()` là **chưa đủ** để kết luận câu SQL trên Connection bạn đang dùng có tham gia transaction hay không.

Nếu Connection trực tiếp có `autoCommit=false`, vấn đề vẫn tồn tại: đó có thể là một transaction JDBC riêng cần `commit()`/`rollback()` riêng. Trạng thái autoCommit không phải bằng chứng về membership của Spring transaction.

## 4. Phân biệt ba cách lấy kết nối

| Cách gọi | Tham gia connection gắn transaction? | Cách dùng |
| --- | --- | --- |
| `jdbcTemplate.query(...)`, `jdbcTemplate.update(...)` | Có, nếu dùng đúng DataSource/transaction manager của Spring | Ưu tiên cho mã truy cập JDBC; Spring lo lấy/trả tài nguyên và chuyển đổi exception. |
| `DataSourceUtils.getConnection(dataSource)` | Có, khi đúng DataSource được transaction manager gắn và có transaction đồng bộ thích hợp | Khi phải làm JDBC thủ công; luôn dùng `DataSourceUtils.releaseConnection(...)` trong finally. |
| `dataSource.getConnection()` trên pool gốc | Có thể tạo Connection **khác** và bypass | Không dùng để trộn với JDBC của `@Transactional` khi muốn một transaction. |
| `getConnection()` trên `TransactionAwareDataSourceProxy` | Proxy hỗ trợ tham gia transaction Spring | Dành cho mã cũ/thư viện chỉ biết DataSource; hiểu chính xác cấu hình proxy và transaction manager. |

**Điều kiện thiết yếu:** DataSource trong `JdbcTemplate`, `DataSourceUtils` và transaction manager phải tương ứng đúng tài nguyên. Dùng hai pool/datasource khác nhau, dù cùng URL database, không có nghĩa hai bên chia sẻ một transaction. Các hệ thống nhiều database cần chọn transaction manager rõ ràng; transaction JDBC cục bộ không tự phối hợp commit/rollback toàn bộ những database độc lập.

## 5. Ví dụ chạy được: một INSERT rollback, một INSERT vẫn còn

Ứng dụng Spring Boot sau được thiết kế để **cố ý tái hiện lỗi**. Nó dùng Java 21, Spring JDBC, HikariCP mặc định của starter và database H2 trong bộ nhớ. Cấu hình pool có ít nhất hai Connection, isolation mặc định `READ_COMMITTED`, và Connection trực tiếp bật autoCommit. Chương trình không tạo HTTP endpoint.

### 5.1. Tạo cấu trúc dự án

~~~text
spring-tx-connection-demo/
├── settings.gradle
├── build.gradle
└── src/main/
    ├── java/example/tx/
    │   ├── TxConnectionApplication.java
    │   └── TxProbeService.java
    └── resources/
        ├── application.properties
        └── schema.sql
~~~

Tệp `settings.gradle`:

~~~groovy
rootProject.name = 'spring-tx-connection-demo'
~~~

Tệp `build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    runtimeOnly 'com.h2database:h2'
}
~~~

Tệp `src/main/resources/application.properties`:

~~~properties
spring.main.web-application-type=none
spring.main.banner-mode=off
spring.datasource.url=jdbc:h2:mem:tx_connection_demo;DB_CLOSE_DELAY=-1
spring.datasource.driver-class-name=org.h2.Driver
spring.datasource.username=sa
spring.datasource.password=
spring.datasource.hikari.maximum-pool-size=4
spring.datasource.hikari.auto-commit=true
spring.sql.init.mode=always
logging.level.root=ERROR
~~~

Tệp `src/main/resources/schema.sql`:

~~~sql
CREATE TABLE journal (
    id INT PRIMARY KEY,
    description VARCHAR(100) NOT NULL
);
~~~

H2 sẽ khởi tạo bảng mới ở mỗi tiến trình chạy. Trong một Spring JDBC transaction, transaction manager có thể đổi trạng thái Connection đang quản lý thành `autoCommit=false`; cấu hình `auto-commit=true` ở pool mô tả trạng thái mặc định của **Connection mới được mượn trực tiếp** trong ví dụ.

### 5.2. Service chứa thao tác cố ý bypass

Tệp `src/main/java/example/tx/TxProbeService.java`:

~~~java
package example.tx;

import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Statement;

import javax.sql.DataSource;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class TxProbeService {
    private final JdbcTemplate jdbc;
    private final DataSource dataSource;

    public TxProbeService(JdbcTemplate jdbc, DataSource dataSource) {
        this.jdbc = jdbc;
        this.dataSource = dataSource;
    }

    @Transactional(rollbackFor = SQLException.class)
    public void demonstrate() throws SQLException {
        jdbc.update(
                "INSERT INTO journal(id, description) VALUES (?, ?)",
                1, "spring-managed");

        int inSpringTransaction = jdbc.queryForObject(
                "SELECT COUNT(*) FROM journal WHERE id = 1",
                Integer.class);
        System.out.println("Spring JDBC nhìn thấy id=1: "
                + inSpringTransaction);

        // Chú ý: DataSource ở đây là pool gốc, không phải
        // TransactionAwareDataSourceProxy.
        try (Connection raw = dataSource.getConnection()) {
            System.out.println("Connection trực tiếp autoCommit: "
                    + raw.getAutoCommit());

            try (Statement statement = raw.createStatement();
                 ResultSet rs = statement.executeQuery(
                         "SELECT COUNT(*) FROM journal WHERE id = 1")) {
                rs.next();
                System.out.println("Connection trực tiếp thấy id=1: "
                        + rs.getInt(1));
            }

            try (PreparedStatement insert = raw.prepareStatement(
                    "INSERT INTO journal(id, description) VALUES (?, ?)")) {
                insert.setInt(1, 2);
                insert.setString(2, "direct-and-committed");
                insert.executeUpdate();
            }
        }

        throw new IllegalStateException("Chủ động rollback");
    }
}
~~~

Vì service dùng `@Transactional(rollbackFor = SQLException.class)`, cả unchecked exception được ném ở cuối lẫn `SQLException` có thể phát sinh khi thao tác JDBC trực tiếp sẽ kích hoạt rollback **đối với transaction Spring quản lý**. Việc khai báo `rollbackFor` cho checked SQLException giúp tránh nhầm lẫn với quy tắc mặc định chỉ rollback cho RuntimeException/Error.

Dẫu vậy, rollback trên Connection của Spring không thể undo một INSERT đã commit bởi Connection khác. Trong chương trình này, `JdbcTemplate` dùng Connection #A, `dataSource.getConnection()` trả Connection #B.

### 5.3. Runner bắt ngoại lệ rồi kiểm tra database

Tệp `src/main/java/example/tx/TxConnectionApplication.java`:

~~~java
package example.tx;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.JdbcTemplate;

@SpringBootApplication
public class TxConnectionApplication {
    public static void main(String[] args) {
        SpringApplication.run(TxConnectionApplication.class, args);
    }

    @Bean
    CommandLineRunner verify(TxProbeService service, JdbcTemplate jdbc) {
        return args -> {
            try {
                service.demonstrate();
            } catch (IllegalStateException expected) {
                System.out.println("Spring đã rollback transaction");
            }

            int remainingSpring = jdbc.queryForObject(
                    "SELECT COUNT(*) FROM journal WHERE id = 1",
                    Integer.class);
            int remainingDirect = jdbc.queryForObject(
                    "SELECT COUNT(*) FROM journal WHERE id = 2",
                    Integer.class);

            System.out.println("Sau rollback, id=1: " + remainingSpring);
            System.out.println("Sau rollback, id=2: " + remainingDirect);
        };
    }
}
~~~

Dùng JDK 21 với Gradle hỗ trợ Java 21 (chẳng hạn Gradle 8.5), chạy tại thư mục dự án:

~~~bash
gradle bootRun
~~~

Các dòng do chương trình in ra trong trường hợp H2/pool được cấu hình như trên:

~~~text
Spring JDBC nhìn thấy id=1: 1
Connection trực tiếp autoCommit: true
Connection trực tiếp thấy id=1: 0
Spring đã rollback transaction
Sau rollback, id=1: 0
Sau rollback, id=2: 1
~~~

**Giải thích từng dòng:**

- `Spring JDBC nhìn thấy id=1: 1`: truy vấn qua `JdbcTemplate` dùng Connection #A; chính transaction đó đã INSERT id=1, nên thấy thay đổi chưa commit của mình.
- `Connection trực tiếp autoCommit: true`: Connection #B có chế độ mặc định của Hikari pool trong ví dụ.
- `Connection trực tiếp thấy id=1: 0`: Connection #B không thấy INSERT chưa commit của #A dưới `READ_COMMITTED`.
- Sau khi #B INSERT id=2, cơ chế autoCommit commit câu INSERT đó.
- Service ném unchecked exception; Spring rollback Connection #A. Bản ghi id=1 biến mất, nhưng id=2 vẫn tồn tại vì đã commit độc lập.

Đây là một **demo cố ý vi phạm yêu cầu nghiệp vụ** để quan sát lỗi. Không dùng cách mở Connection trực tiếp như trên cho thao tác vốn phải atomic. Giá trị nhìn thấy có thể thay đổi khi dùng isolation, pool, driver hay một transaction-aware wrapper khác. Kết luận đáng tin cậy là **hai đường truy cập có khả năng dùng hai Connection/transaction khác nhau**, và điều đó phá vỡ giả định một lần rollback sẽ hoàn tác tất cả.

## 6. Cách sửa ưu tiên: dùng JdbcTemplate cho toàn bộ công việc

Trong thực tế, service chỉ nên gọi repository hoặc JdbcTemplate dùng đúng DataSource. Ví dụ sửa phần phương thức ở trên (đoạn này dùng các trường và bean trong cùng dự án):

~~~java
@Transactional
public void demonstrateCorrectly() {
    jdbc.update(
            "INSERT INTO journal(id, description) VALUES (?, ?)",
            11, "first");
    jdbc.update(
            "INSERT INTO journal(id, description) VALUES (?, ?)",
            12, "second");

    throw new IllegalStateException("Rollback cả hai INSERT");
}
~~~

Nếu caller gọi `demonstrateCorrectly()` qua Spring proxy và database đang ở trạng thái phù hợp, cả hai INSERT đều nằm trong Connection gắn transaction. Khi RuntimeException thoát ra, cả id=11 và id=12 đều được rollback.

`JdbcTemplate` còn lo `PreparedStatement`, `ResultSet`, cleanup và chuyển `SQLException` thành hệ thống `DataAccessException` của Spring. Vì vậy tránh thao tác JDBC thủ công khi không có nhu cầu đặc biệt.

**Đặt transaction ở service** là cách dễ bảo đảm tính nguyên tử của một nghiệp vụ gồm nhiều repository call. Chỉ một `@Transactional` ở service nhưng lại có repository tự mở raw Connection sẽ không cứu được việc bypass.

## 7. Khi thực sự cần Connection: DataSourceUtils

Nếu cần JDBC API không được template bao phủ trực tiếp, hãy sử dụng `DataSourceUtils.getConnection(dataSource)` và `DataSourceUtils.releaseConnection(connection, dataSource)`. Hai lời gọi này phối hợp với tài nguyên transaction Spring gắn vào luồng. Bên trong transaction đang hoạt động, `releaseConnection` không đóng sớm Connection thuộc transaction manager; Spring giữ nó đến lúc transaction hoàn tất. Ngoài transaction, utility sẽ trả Connection khi không còn cần.

Ví dụ một phương thức có thể đặt trong Spring service/repository có trường `DataSource dataSource` và được gọi qua bean proxy:

~~~java
@Transactional(readOnly = true)
public int countUsingBoundConnection() {
    Connection connection = DataSourceUtils.getConnection(dataSource);
    try (PreparedStatement statement = connection.prepareStatement(
            "SELECT COUNT(*) FROM journal");
         ResultSet rs = statement.executeQuery()) {

        if (!rs.next()) {
            throw new IllegalStateException("COUNT trả về rỗng");
        }
        return rs.getInt(1);
    } catch (SQLException ex) {
        throw new IllegalStateException("Không truy vấn được journal", ex);
    } finally {
        DataSourceUtils.releaseConnection(connection, dataSource);
    }
}
~~~

Những import cần có cho đoạn method minh họa: `java.sql.Connection`, `java.sql.PreparedStatement`, `java.sql.ResultSet`, `java.sql.SQLException`, `org.springframework.jdbc.datasource.DataSourceUtils`, `org.springframework.transaction.annotation.Transactional`; class giữ `javax.sql.DataSource`.

Lưu ý quan trọng:

1. **Không** bọc Connection lấy từ `DataSourceUtils.getConnection` trong `try (Connection connection = ...)` rồi đóng trực tiếp. Hãy đóng Statement/ResultSet bằng try-with-resources, nhưng release Connection bằng `DataSourceUtils.releaseConnection` trong finally để Spring tự quyết định có được đóng thực tế hay chưa.
2. Không tự gọi `commit()`, `rollback()`, `setAutoCommit(...)` hoặc thay isolation trên Connection do transaction manager kiểm soát khi mục tiêu là để Spring quyết định transaction.
3. `getConnection()` và `releaseConnection()` phải nhận **cùng DataSource phù hợp với transaction manager**; không trộn một wrapper không tương thích hoặc hai pool.
4. `DataSourceUtils` giải quyết việc lấy/trả Connection gắn transaction. Nó không miễn trừ việc quản lý Statement, ResultSet hoặc các tài nguyên database khác.
5. Nếu một `SQLException` xảy ra trong callback thủ công, nên chuyển sang `DataAccessException` bằng cơ chế Spring thích hợp khi cần API nhất quán; trong đoạn ngắn phía trên ta bọc thành `IllegalStateException` để làm rõ vòng đời, còn Spring JDBC thường có dịch lỗi tinh tế hơn.

Trong đa số trường hợp, một `JdbcTemplate.execute(ConnectionCallback<T>)` còn gọn hơn việc tự get/release:

~~~java
public int countWithJdbcTemplateCallback() {
    return jdbc.execute(connection -> {
        try (PreparedStatement statement = connection.prepareStatement(
                "SELECT COUNT(*) FROM journal");
             ResultSet rs = statement.executeQuery()) {
            rs.next();
            return rs.getInt(1);
        }
    });
}
~~~

Đoạn method này giả định `jdbc` là trường `JdbcTemplate`; nó có thể dùng trong service transaction hoặc ngoài transaction. `JdbcTemplate` cung cấp Connection hợp lệ cho callback, đồng thời quản lý việc lấy/trả và translate `SQLException`. Không giữ Connection lấy trong callback để sử dụng sau khi callback trả về.

## 8. Ngoại lệ quan trọng: TransactionAwareDataSourceProxy

Spring cung cấp `TransactionAwareDataSourceProxy` để thích ứng code cũ/thư viện bên ngoài vốn chỉ biết gọi `DataSource.getConnection()`. Proxy bọc một DataSource mục tiêu; khi caller gọi `getConnection()` trên **proxy**, nó cung cấp một Connection wrapper có khả năng tham gia transaction Spring của DataSource mục tiêu (nếu có) và nhận biết cách close thích hợp.

~~~java
DataSource transactionAware =
        new TransactionAwareDataSourceProxy(targetDataSource);

try (Connection connection = transactionAware.getConnection();
     PreparedStatement statement = connection.prepareStatement(
             "SELECT COUNT(*) FROM journal");
     ResultSet rs = statement.executeQuery()) {
    rs.next();
    System.out.println(rs.getInt(1));
}
~~~

Đây là **đoạn minh họa cần khai báo `targetDataSource` và import JDBC + `TransactionAwareDataSourceProxy`**, không phải file Java độc lập. Để hoạt động đúng, transaction manager quản lý **DataSource mục tiêu** tương ứng. Không tạo một proxy mới tùy tiện trong mỗi method rồi giả định nó giải quyết mọi cấu hình nhiều DataSource.

`TransactionAwareDataSourceProxy` chủ yếu dành cho việc tích hợp code không biết Spring transaction. Đối với code do mình kiểm soát, hãy ưu tiên `JdbcTemplate` hoặc `DataSourceUtils` để việc tham gia transaction và sở hữu tài nguyên rõ ràng. Khi dùng nhiều lớp proxy (`LazyConnectionDataSourceProxy`, routing datasource, transaction-aware proxy), xác định đúng target, thứ tự wrapper và DataSource thực mà transaction manager quản lý. Một wrapper có thể làm câu trả lời cho câu hỏi “`getConnection()` này có bypass không?” thay đổi.

## 9. Đừng nhầm với những trường hợp có Connection khác một cách chủ ý

### 9.1. Propagation.REQUIRES_NEW

Một transaction mới với `Propagation.REQUIRES_NEW` có thể cần Connection độc lập, nhưng **Spring vẫn quản lý transaction mới đó**. Transaction cũ được tạm treo, transaction mới bắt đầu/commit/rollback theo quy tắc của Spring, rồi transaction cũ tiếp tục. Đây là khác biệt căn bản với việc lấy raw Connection bằng pool mà không có ranh giới transaction rõ ràng.

Việc dùng REQUIRES_NEW cần cân nhắc pool size: khi nhiều luồng giữ Connection của transaction ngoài rồi đồng loạt xin Connection cho transaction mới, pool nhỏ có thể cạn và chờ đến timeout. Chỉ chọn propagation này vì yêu cầu nghiệp vụ, không dùng để che việc bypass.

### 9.2. Nhiều transaction manager hoặc nhiều DataSource

Với ứng dụng có `ordersDataSource` và `auditDataSource`, `@Transactional` chọn một transaction manager có thể chỉ kiểm soát một DataSource. `JdbcTemplate` trỏ sang DataSource khác sẽ không tự tham gia transaction đầu. Có thể cần transaction manager riêng và chiến lược nhất quán dữ liệu phù hợp.

Ngay cả hai DataSource cùng kết nối một database cũng không bảo đảm chúng dùng cùng Connection. Khi kiểm tra, xem bean `DataSource` được gắn vào transaction manager, bean mà `JdbcTemplate` nhận và các proxy wrapper trung gian.

### 9.3. Self-invocation và chuyển luồng

Trong cấu hình Spring proxy thông thường, gọi một phương thức `@Transactional` **trực tiếp từ phương thức khác của cùng object** (self-invocation) thường không đi qua proxy; có thể transaction chưa từng bắt đầu. Kết quả `TransactionSynchronizationManager.isActualTransactionActive()` lúc đó có thể là false. Tương tự, Spring transaction đồng bộ theo ThreadLocal không được tự động truyền qua `new Thread(...)` hay `@Async`; phải thiết kế ranh giới transaction riêng cho công việc bất đồng bộ.

Phần này chỉ nói về transaction đồng bộ của Spring JDBC. Spring reactive/R2DBC có mô hình context và resource management khác; không áp dụng máy móc quy tắc ThreadLocal/JDBC Connection lên Reactive Streams.

## 10. Cách chẩn đoán một nghi vấn bypass

Nếu một thao tác SQL “không rollback dù service có `@Transactional`”, hãy điều tra theo thứ tự:

1. **Xác nhận transaction thực sự active** tại điểm gọi repository: `TransactionSynchronizationManager.isActualTransactionActive()` hỗ trợ chẩn đoán, nhưng chưa đủ để chứng minh Connection đang dùng tham gia transaction.
2. **Tìm mọi `getConnection()` trực tiếp** và ghi rõ đối tượng đó là pool gốc, `TransactionAwareDataSourceProxy` hay wrapper khác. Kiểm tra đối tượng DataSource mà JdbcTemplate và transaction manager đang dùng.
3. **Kiểm tra cách lấy và release Connection**: `JdbcTemplate`/`DataSourceUtils` hay `DataSource.getConnection()`; có `close()`, `commit()` hoặc `setAutoCommit()` thủ công không?
4. **Chứng minh bằng dữ liệu sau rollback** trong test tích hợp với database cụ thể: viết bản ghi A qua Spring template và B qua đường nghi vấn, cố ý ném unchecked exception, rồi đọc lại cả hai từ một kết nối mới.
5. **Kiểm tra môi trường**: pool có đủ Connection để thử, isolation level, autoCommit, proxy, transaction manager và các transaction lồng nhau. Nếu pool size = 1 trong lúc transaction đang giữ Connection #A, gọi `getConnection()` trực tiếp có thể bị chờ/timeout thay vì cấp #B.
6. **Kiểm tra thread boundary**: thao tác chạy đồng bộ trong transaction hay đã chuyển sang thread/task khác?

Có thể dùng `DataSourceUtils.isConnectionTransactional(connection, dataSource)` để kiểm tra một Connection **có được nhận diện là gắn với transaction theo DataSource và ngữ cảnh hiện tại không** trong những tình huống chẩn đoán phù hợp. Kết quả chỉ đáng tin khi bạn truyền đúng DataSource và kiểm tra ở đúng luồng/điểm thời gian; đừng dùng một phép so sánh `connection == otherConnection` để kết luận vì pool và proxy có thể trả wrapper khác nhau quanh cùng tài nguyên.

### Test tình huống tối thiểu

| Kịch bản | Dấu hiệu | Bài học |
| --- | --- | --- |
| Cả hai INSERT dùng cùng JdbcTemplate và transaction manager | RuntimeException khiến cả hai rollback | Spring quản lý cùng connection/resource. |
| INSERT A qua JdbcTemplate, INSERT B qua pool gốc `getConnection()` autoCommit | A rollback; B còn lại | B bypass transaction Spring. |
| Query qua JDBC template trong transaction thấy dữ liệu chưa commit; raw Connection READ_COMMITTED chưa thấy | Hai query nhìn thấy khác nhau | Hai Connection/transaction độc lập. |
| Raw Connection dùng TransactionAwareDataSourceProxy đúng target | Có thể tham gia transaction hiện tại | Phải phân biệt proxy với pool gốc. |
| Pool còn một Connection đang bị transaction giữ | Lần gọi trực tiếp thứ hai có thể chờ hoặc timeout | Bypass còn có thể gây áp lực/treo pool. |
| Service tự gọi `@Transactional` cùng lớp | Transaction có thể không active | Xác minh proxy trước khi phân tích Connection. |
| Có nhiều DataSource và chọn sai manager | Một số SQL ngoài ranh giới kỳ vọng | Bảo đảm cấu hình cùng tài nguyên. |

## 11. Những lỗi tư duy cần tránh

- **“Có annotation thì mọi SQL nằm trong transaction.”** Annotation xác định điểm bắt đầu/kết thúc transaction Spring; JDBC call phải dùng Connection được enlist/gắn đúng cách.
- **“Hai Connection có cùng JDBC URL thì là một transaction.”** URL chỉ địa chỉ database; transaction JDBC gắn với Connection/session cụ thể.
- **“Connection được đóng sẽ tự rollback theo transaction bên ngoài.”** Đóng raw Connection về pool không khiến câu SQL đã autoCommit bị rollback bởi transaction Spring khác.
- **“Dùng `try-with-resources` quanh mọi Connection đều đúng.”** Đúng với raw Connection do code tự sở hữu; với Connection từ `DataSourceUtils`, phải dùng releaseConnection để không đóng tài nguyên còn được Spring quản lý.
- **“`isActualTransactionActive()` true chứng minh Connection hiện tại cùng transaction.”** Đây là trạng thái ngữ cảnh của luồng, không phải bằng chứng membership của một Connection bất kỳ.
- **“Đổi sang REQUIRES_NEW để tất cả cùng rollback.”** REQUIRES_NEW là transaction độc lập được Spring quản lý; nó thường có commit/rollback độc lập với transaction bên ngoài và không đáp ứng yêu cầu atomic chung.
- **“Một lỗi đã được catch nhưng transaction vẫn chắc chắn rollback.”** Spring thường quyết định rollback khi exception vượt khỏi ranh giới interceptor theo rollback rules; nếu bắt và nuốt lỗi, cần chủ động xử lý rollback hoặc để exception thích hợp thoát ra.
- **“Proxy được cấu hình ở đâu cũng tương đương.”** DataSource pool, transaction-aware proxy, lazy proxy và routing proxy có ngữ nghĩa khác nhau. Cấu hình sai target có thể khiến Spring không nhận ra Connection đã được gắn.

## 12. Câu hỏi tự kiểm tra

1. Khi transaction đã giữ Connection #A, vì sao một lần `HikariDataSource.getConnection()` trong cùng phương thức có thể trả #B?
2. `JdbcTemplate` dùng cơ chế nào để tìm Connection được transaction manager gắn theo luồng?
3. Với bản ghi A vừa INSERT trong transaction chưa commit, vì sao SELECT trên Connection #B ở isolation READ_COMMITTED có thể chưa thấy A?
4. Tại sao `DataSourceUtils.releaseConnection` khác với gọi `Connection.close()` trực tiếp?
5. Khi nào `TransactionAwareDataSourceProxy` làm cho `getConnection()` có hành vi khác pool gốc?
6. Vì sao `@Transactional` và hai DataSource trỏ cùng database vẫn có thể cho hai transaction độc lập?
7. Muốn chứng minh một DAO thật sự nằm trong cùng transaction, cần kiểm tra những gì ngoài cờ `isActualTransactionActive()`?
8. Nếu vừa thêm `@Async` vào một tác vụ database, cần kiểm tra lại giả định nào về ngữ cảnh transaction?

**Ghi nhớ:** Trong Spring JDBC, transaction manager quản lý **Connection được gắn với tài nguyên/luồng transaction**. `JdbcTemplate` và `DataSourceUtils` được xây dựng để sử dụng Connection đó. Gọi `getConnection()` trực tiếp trên DataSource pool gốc có thể lấy một Connection khác, dẫn đến commit/rollback độc lập. Muốn bảo đảm tính nhất quán, hãy giữ các thao tác SQL của cùng nghiệp vụ trên đúng hạ tầng transaction Spring và kiểm tra cấu hình DataSource/proxy thực tế.

### Tài liệu tham khảo

- Spring Framework — JDBC và quản lý Connection: https://docs.spring.io/spring-framework/reference/data-access/jdbc/connections.html
- Spring Framework — Transaction Management: https://docs.spring.io/spring-framework/reference/data-access/transaction.html
- Spring Javadoc — DataSourceUtils: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jdbc/datasource/DataSourceUtils.html
- Spring Javadoc — TransactionAwareDataSourceProxy: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jdbc/datasource/TransactionAwareDataSourceProxy.html
- Spring Javadoc — DataSourceTransactionManager: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jdbc/datasource/DataSourceTransactionManager.html
