# DataSourceUtils và kết nối tham gia giao dịch hiện tại

> **Chủ đề:** Spring Framework – Data Access  
> **Nhóm kiến thức:** Kết nối và tài nguyên

## 1. Tại sao cần `DataSourceUtils`?

Giả sử một phương thức nghiệp vụ thực hiện hai thao tác trên cùng cơ sở dữ liệu: tạo đơn hàng và ghi audit. Cả hai phải commit hoặc rollback cùng nhau. Trong Spring, `@Transactional` hoặc `TransactionTemplate` có thể đặt ranh giới giao dịch, nhưng mã JDBC tự viết vẫn phải **lấy đúng `Connection` đang tham gia giao dịch**. Nếu DAO tự lấy một kết nối mới từ pool, thao tác đó có thể tự commit và không rollback theo transaction của service.

`org.springframework.jdbc.datasource.DataSourceUtils` là tiện ích của Spring JDBC để lấy và giải phóng JDBC connection **có nhận thức về transaction context**. Cặp API cơ bản:

~~~java
Connection connection = DataSourceUtils.getConnection(dataSource);
try {
    // Thực thi JDBC bằng connection.
} finally {
    DataSourceUtils.releaseConnection(connection, dataSource);
}
~~~

Đây là mẫu nằm trong phương thức có sẵn `dataSource`; phải đóng `PreparedStatement`, `ResultSet` do mình tạo. Ví dụ Maven chạy được có ở mục 7.

**Ý tưởng quan trọng:** nếu Spring đã gắn một connection vào giao dịch hiện tại, `getConnection` tìm ra connection đó. Nếu connection vẫn thuộc giao dịch, `releaseConnection` không đóng nó quá sớm. Không có giao dịch hay synchronization quản lý, cùng API vẫn lấy và giải phóng connection bình thường.

`DataSourceUtils` giúp **tham gia** vào giao dịch đã được quản lý; nó **không tự bắt đầu, commit hoặc rollback** một giao dịch nghiệp vụ.

## 2. Bốn thành phần và ranh giới trách nhiệm

| Thành phần | Phụ trách | Không tự làm |
| --- | --- | --- |
| `DataSource` | Cấp JDBC `Connection`; thường kết nối đến pool | Bảo đảm mọi `getConnection()` đều tự tham gia transaction Spring |
| `DataSourceUtils` | Tra cứu/giải phóng connection có nhận thức về resource binding | Mở/commit/rollback transaction nghiệp vụ |
| `PlatformTransactionManager`, chẳng hạn `DataSourceTransactionManager` | Bắt đầu/tham gia transaction JDBC, thiết lập trạng thái và commit/rollback/cleanup | Tự sửa mã JDBC lấy nhầm kết nối khác |
| `TransactionSynchronizationManager` | Giữ resource/synchronization liên quan đến luồng thực thi imperative | API để DAO tùy tiện tự tạo giao dịch hoặc tự bind resource |

Ví dụ một `DataSourceTransactionManager` quản lý `DataSource` dùng chung với DAO:

~~~text
@Service / @Transactional hoặc TransactionTemplate
                │
                ▼
       DataSourceTransactionManager
        begin / commit / rollback
                │
                ▼
     TransactionSynchronizationManager
       └─ resource key: DataSource
          value: ConnectionHolder
                ▲
                │ tìm kết nối đang được bind
                │
        DataSourceUtils.getConnection(dataSource)
                ▲
                │
            JDBC DAO
                │
                ▼
       PreparedStatement / ResultSet
~~~

Ở transaction JDBC địa phương, manager thường lấy connection từ `DataSource`, chuẩn bị auto-commit/isolation/read-only theo cấu hình thích hợp, rồi gắn tài nguyên với luồng. Lần gọi `DataSourceUtils.getConnection` bằng đúng `DataSource` có thể nhận lại connection đó.

Cần phân biệt **resource management** (lấy/trả kết nối) với **transaction management** (chọn phạm vi nguyên tử và commit/rollback). Cùng một lời gọi DAO có thể cần cả hai; không nhiệm vụ nào tự thay thế nhiệm vụ còn lại.

## 3. Cơ chế `getConnection(DataSource)`

Định nghĩa API:

~~~java
Connection con = DataSourceUtils.getConnection(dataSource);
~~~

Tại mức khái niệm, Spring thực hiện:

1. Kiểm tra tài nguyên `ConnectionHolder` đã gắn với `DataSource` trong `TransactionSynchronizationManager` ở luồng hiện tại chưa.
2. Nếu có connection phù hợp, sử dụng connection đó.
3. Nếu chưa có, lấy một connection từ `DataSource`. Khi transaction synchronization đang hoạt động, Spring có thể bind và đăng ký cleanup để những lời gọi kế tiếp trong cùng context tham gia phù hợp.
4. Nếu không có transaction synchronization cần quản lý, kết nối được lấy như cách JDBC thông thường; mã gọi phải giải phóng sau khi dùng.

Spring hỗ trợ đồng bộ tài nguyên với `DataSourceTransactionManager` và một số cấu hình JTA/JPA. Vì vậy không được suy luận rằng chỉ khi một phương thức có annotation `@Transactional` thì `DataSourceUtils` mới hoạt động; API kiểm tra **ngữ cảnh thực thi**, không quét source code để tìm annotation.

### 3.1. Khi có Spring-managed JDBC transaction

Với một `DataSourceTransactionManager` thực sự bắt đầu transaction trên cùng `DataSource`:

~~~java
Connection a = DataSourceUtils.getConnection(dataSource);
Connection b = DataSourceUtils.getConnection(dataSource);
try {
    // Trong cấu hình JDBC transaction thông thường, a và b
    // đều là connection mà Spring đã bind.
} finally {
    DataSourceUtils.releaseConnection(b, dataSource);
    DataSourceUtils.releaseConnection(a, dataSource);
}
~~~

Đoạn minh họa này **chỉ khẳng định cùng connection khi thỏa điều kiện về transaction và nguồn dữ liệu**. Ngoài transaction, hai lần gọi có thể được cấp hai connection khác nhau. Trong hệ thống có wrapper/proxy, không nên dùng so sánh object identity giữa mọi loại connection handle để thay cho việc kiểm chứng commit/rollback.

### 3.2. Khi không có transaction

Gọi `DataSourceUtils.getConnection` vẫn hợp lệ. API không tự gọi `begin` và không tự chuyển các câu SQL riêng thành một đơn vị nguyên tử. Tùy cách driver/connection cấu hình, JDBC có thể auto-commit mỗi statement.

Ví dụ: gọi `jdbcTemplate.update(...)` hai lần ngoài transaction có thể tạo hai thay đổi đã commit riêng. Việc cả hai lần đều lấy/trả connection hợp lệ **không bảo đảm** rollback cùng nhau nếu lỗi xuất hiện giữa hai lần.

### 3.3. Phân biệt actual transaction và synchronization

`TransactionSynchronizationManager` có trạng thái liên quan đến cả **transaction thực sự đang hoạt động** và **transaction synchronization**. `DataSourceUtils` có thể liên kết kết nối khi synchronization hoạt động, kể cả trường hợp tài nguyên JDBC chỉ được enlist/lấy trễ trong một ngữ cảnh JTA hoặc JPA phù hợp. Do đó:

- `TransactionSynchronizationManager.isSynchronizationActive()` không đồng nghĩa mọi nơi đều có một local JDBC transaction đã mở.
- `DataSourceUtils.isConnectionTransactional(con, dataSource)` quan sát xem connection được nhận diện là tài nguyên được bind bởi Spring đối với luồng và nguồn dữ liệu này.
- Không tự gọi `TransactionSynchronizationManager.bindResource(...)` hoặc `unbindResource(...)` trong DAO thông thường để “ép” tham gia transaction; đây là phần hạ tầng phải được điều phối đúng lifecycle.

## 4. API quan trọng nên biết

### 4.1. `getConnection` và `doGetConnection`

~~~java
Connection c = DataSourceUtils.getConnection(dataSource);
~~~

`getConnection` xử lý lỗi lấy connection theo kiểu unchecked, ví dụ `CannotGetJdbcConnectionException` (một loại `DataAccessException`). Biến thể `doGetConnection(dataSource)` thực hiện tra cứu tương tự nhưng có thể ném `SQLException` gốc theo hợp đồng checked exception.

**Giới hạn exception translation:** việc `getConnection` chuyển lỗi **lấy kết nối** không có nghĩa câu SQL thủ công ném `SQLException` cũng được tự chuyển hết. `JdbcTemplate` cung cấp exception translation cho hoạt động JDBC ở tầng cao hơn.

### 4.2. `releaseConnection` và `doReleaseConnection`

~~~java
DataSourceUtils.releaseConnection(c, dataSource);
~~~

Nếu connection là tài nguyên Spring đang bind với transaction/synchronization, lệnh này **không đóng nó**. Việc đóng/trả về pool được quản lý vào lúc thích hợp sau transaction.

Nếu connection không đang được quản lý bởi thread-bound resource, Spring giải phóng nó theo quy tắc `DataSource`. Với pool, `Connection.close()` thường trả kết nối logic về pool; với `DriverManagerDataSource` demo, connection thường bị đóng vật lý. Biến thể `doReleaseConnection` cho phép truyền tiếp `SQLException` trong một số tình huống sử dụng thấp tầng.

Đừng diễn giải “release” là “commit”, “rollback” hay “luôn đóng socket”. Đây là ba khái niệm khác nhau.

### 4.3. `isConnectionTransactional`

~~~java
boolean transactional =
        DataSourceUtils.isConnectionTransactional(c, dataSource);
~~~

`true` nghĩa Spring nhận diện connection gắn với tài nguyên transaction trong **luồng hiện tại** đối với `DataSource` được cung cấp. `false` không có nghĩa database không thể chạy SQL, cũng không tự chứng minh auto-commit đang bật; nó chỉ nói rằng Spring không nhận diện resource binding tương ứng.

Đây là tín hiệu debug, không phải API để DAO quyết định tự `commit()` khi thấy `false`. Ranh giới transaction thuộc service/transaction manager.

### 4.4. `applyTransactionTimeout`

Với `PreparedStatement` thủ công, Spring cho phép áp dụng timeout còn lại của transaction (nếu có):

~~~java
DataSourceUtils.applyTransactionTimeout(preparedStatement, dataSource);
~~~

API này thiết lập query timeout trên JDBC statement khi ngữ cảnh có timeout thích hợp. `JdbcTemplate` đã hỗ trợ timeout theo cấu hình Spring; không cần gọi lặp trong DAO dùng `JdbcTemplate`. Timeout phụ thuộc driver/database và không bảo đảm có thể cưỡng bức chấm dứt mọi loại thao tác ngoài database.

## 5. Vì sao `DataSource.getConnection()` trực tiếp có thể bỏ qua transaction?

Xét service đã được Spring mở transaction trên `appDataSource`, nhưng một DAO thực thi:

~~~java
try (Connection connection = appDataSource.getConnection()) {
    // Thực hiện INSERT qua JDBC thuần.
}
~~~

Nếu `appDataSource` là pool hoặc `DataSource` thông thường, `getConnection()` trực tiếp có thể cấp **một connection khác** với connection Spring đã bind. Nếu connection mới có auto-commit, INSERT có thể commit ngay. Sau đó service rollback thì chỉ những thao tác đã tham gia connection/transaction Spring mới được rollback đúng.

Mã thay thế để tích hợp Spring:

~~~java
Connection connection = DataSourceUtils.getConnection(appDataSource);
try {
    try (PreparedStatement ps = connection.prepareStatement(
            "INSERT INTO audit_log(id, description) VALUES (?, ?)")) {
        ps.setLong(1, 101L);
        ps.setString(2, "created");
        DataSourceUtils.applyTransactionTimeout(ps, appDataSource);
        ps.executeUpdate();
    }
} catch (SQLException ex) {
    throw new IllegalStateException("Cannot write audit log", ex);
} finally {
    DataSourceUtils.releaseConnection(connection, appDataSource);
}
~~~

Đây là đoạn **minh họa trong một phương thức** có `appDataSource` và bảng `audit_log` đã tồn tại. Trong một transaction được quản lý đúng cách, mã này tham gia connection đang bind. Ngoài transaction, nó vẫn lấy connection và giải phóng đúng.

### 5.1. Không dùng `try-with-resources` để đóng connection đã bind

Tránh:

~~~java
// Sai cách trong Spring-managed transaction:
try (Connection c = DataSourceUtils.getConnection(dataSource)) {
    // ...
}
~~~

Java sẽ tự gọi `c.close()` khi kết thúc block, bỏ qua quy tắc của `DataSourceUtils.releaseConnection`. Điều đó có thể đóng connection mà transaction vẫn cần dùng hoặc đang chuẩn bị commit/rollback.

**Cách đúng:** dùng `try-with-resources` cho `PreparedStatement` và `ResultSet` do code sở hữu; dùng `try/finally` và `DataSourceUtils.releaseConnection` cho `Connection`. Không trực tiếp gọi `connection.commit()`, `rollback()` hoặc thay đổi `setAutoCommit(...)` trên connection Spring đang quản lý.

### 5.2. Release trong DAO không kết thúc transaction

~~~text
Service mở transaction
    ├── DAO A: getConnection → INSERT A → releaseConnection
    │         (Connection vẫn được giữ nếu đang bound)
    ├── DAO B: getConnection → INSERT B → releaseConnection
    │         (vẫn tham gia cùng transaction)
    └── Service kết thúc:
             transaction manager commit hoặc rollback
             cleanup, unbind, trả connection về DataSource/pool
~~~

Điểm thường bị hiểu lầm: **kết thúc scope truy cập tài nguyên** không đồng nghĩa **kết thúc giao dịch nghiệp vụ**. Dù `releaseConnection` được gọi trước, transaction manager vẫn kiểm soát connection đang bind cho đến thời điểm phù hợp.

## 6. Phương án ưu tiên: `JdbcTemplate`

Nếu mục tiêu là thực thi SQL bình thường, `JdbcTemplate` thường tốt hơn việc tự quản lý JDBC connection:

~~~java
int rows = jdbcTemplate.update(
        "UPDATE orders SET status = ? WHERE id = ?",
        "DONE", orderId);
~~~

`JdbcTemplate` nội bộ áp dụng cách lấy/trả connection tương thích với `DataSourceUtils`; nó cũng quản lý statement/result set và chuyển lỗi JDBC sang `DataAccessException`. DAO tập trung vào SQL, tham số và kết quả; transaction manager lo giao dịch.

Chỉ nên dùng `DataSourceUtils` trực tiếp khi viết adapter JDBC thấp tầng, tích hợp thư viện đòi hỏi raw `Connection` hoặc sử dụng chức năng driver chưa được abstraction đang dùng bao phủ. Tránh trộn `JdbcTemplate` với raw connection handling mà không hiểu nguồn dữ liệu và transaction đang quản lý.

Ví dụ một service dùng cả DAO JDBC thủ công và `JdbcTemplate` vẫn có thể commit/rollback cùng nhau **nếu hai bên dùng đúng một `DataSource` và cùng transaction**.

## 7. Demo Java 17+: kết nối được bind, commit và rollback

Ví dụ dùng Spring Framework JDBC **6.1.14**, H2 **2.2.224**, Maven và Java **17+**. `DriverManagerDataSource` không có connection pool nên phù hợp cho minh họa, không phải lựa chọn mặc định cho production. `TransactionTemplate` giúp đặt transaction tường minh mà không phải cấu hình Spring AOP proxy.

Mục tiêu quan sát:

- `isConnectionTransactional` là `false` ngoài transaction.
- Trong transaction, hai lần `getConnection` sử dụng cùng connection đang bind.
- JDBC thủ công và `JdbcTemplate` cùng commit.
- Lệnh INSERT bị ném lỗi sau đó sẽ rollback, dù code đã gọi `releaseConnection`.

### 7.1. Cấu trúc dự án

~~~text
datasource-utils-demo/
├── pom.xml
└── src/main/java/demo/
    └── DataSourceUtilsDemo.java
~~~

### 7.2. `pom.xml`

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>datasource-utils-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-jdbc</artifactId>
            <version>6.1.14</version>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <version>2.2.224</version>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.3.0</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 7.3. `src/main/java/demo/DataSourceUtilsDemo.java`

~~~java
package demo;

import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.jdbc.datasource.DataSourceUtils;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.transaction.support.TransactionTemplate;

public class DataSourceUtilsDemo {

    public static void main(String[] args) {
        DriverManagerDataSource dataSource = new DriverManagerDataSource(
                "jdbc:h2:mem:dsutils_demo;DB_CLOSE_DELAY=-1", "sa", "");
        dataSource.setDriverClassName("org.h2.Driver");

        JdbcTemplate jdbc = new JdbcTemplate(dataSource);
        jdbc.execute("CREATE TABLE event_log (" +
                "id INT PRIMARY KEY, message VARCHAR(100) NOT NULL)");

        // Ngoài giao dịch Spring: kết nối không được bind bởi transaction.
        Connection outside = DataSourceUtils.getConnection(dataSource);
        try {
            System.out.println("Outside Spring transaction: " +
                    DataSourceUtils.isConnectionTransactional(outside, dataSource));
        } finally {
            DataSourceUtils.releaseConnection(outside, dataSource);
        }

        TransactionTemplate tx = new TransactionTemplate(
                new DataSourceTransactionManager(dataSource));

        tx.executeWithoutResult(status -> {
            Connection first = DataSourceUtils.getConnection(dataSource);
            Connection second = DataSourceUtils.getConnection(dataSource);
            try {
                System.out.println("Same transaction connection: " +
                        (first == second));
                System.out.println("Connection is transactional: " +
                        DataSourceUtils.isConnectionTransactional(first, dataSource));

                try (PreparedStatement statement = first.prepareStatement(
                        "INSERT INTO event_log(id, message) VALUES (?, ?)")) {
                    statement.setInt(1, 1);
                    statement.setString(2, "manual JDBC");
                    DataSourceUtils.applyTransactionTimeout(statement, dataSource);
                    statement.executeUpdate();
                }

                // JdbcTemplate tham gia cùng transaction nhờ cùng DataSource.
                jdbc.update("INSERT INTO event_log(id, message) VALUES (?, ?)",
                        2, "JdbcTemplate");
            } catch (SQLException ex) {
                throw new IllegalStateException("JDBC failure", ex);
            } finally {
                DataSourceUtils.releaseConnection(second, dataSource);
                DataSourceUtils.releaseConnection(first, dataSource);
            }
        });

        System.out.println("Rows after commit: " +
                jdbc.queryForObject("SELECT COUNT(*) FROM event_log", Integer.class));

        try {
            tx.executeWithoutResult(status -> {
                Connection c = DataSourceUtils.getConnection(dataSource);
                try (PreparedStatement statement = c.prepareStatement(
                        "INSERT INTO event_log(id, message) VALUES (?, ?)")) {
                    statement.setInt(1, 3);
                    statement.setString(2, "must rollback");
                    statement.executeUpdate();
                } catch (SQLException ex) {
                    throw new IllegalStateException("JDBC failure", ex);
                } finally {
                    DataSourceUtils.releaseConnection(c, dataSource);
                }
                throw new IllegalStateException("forced rollback");
            });
        } catch (IllegalStateException expected) {
            System.out.println("Caught: " + expected.getMessage());
        }

        System.out.println("Rows after rollback: " +
                jdbc.queryForObject("SELECT COUNT(*) FROM event_log", Integer.class));
    }
}
~~~

Chạy trong thư mục `datasource-utils-demo`:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.DataSourceUtilsDemo
~~~

**Các dòng do ứng dụng in ra** (không tính log của Maven):

~~~text
Outside Spring transaction: false
Same transaction connection: true
Connection is transactional: true
Rows after commit: 2
Caught: forced rollback
Rows after rollback: 2
~~~

### 7.4. Diễn giải từng bước

**Ngoài transaction.** `getConnection` lấy connection từ `DriverManagerDataSource`. Vì luồng chưa có resource binding do Spring transaction, `isConnectionTransactional` là `false`. `releaseConnection` đóng kết nối. Tham số H2 `DB_CLOSE_DELAY=-1` giữ database in-memory tồn tại giữa những connection khác nhau trong cùng tiến trình.

**Trong transaction thứ nhất.** `TransactionTemplate` gọi `DataSourceTransactionManager` bắt đầu giao dịch. Manager lấy connection, cấu hình theo transaction và bind resource. `first`, `second` cùng tham chiếu connection được bind trong demo. JDBC thủ công chèn hàng 1; `JdbcTemplate` chèn hàng 2 qua cùng `DataSource`. `releaseConnection` được gọi trong callback nhưng không đóng connection đang được transaction manager quản lý. Callback kết thúc bình thường nên manager commit. Đếm bảng trả 2.

**Trong transaction thứ hai.** Lệnh INSERT hàng 3 thành công ở cấp SQL nhưng callback ném `IllegalStateException`, một runtime exception. `TransactionTemplate` rollback và chuyển exception ra ngoài. Khối `catch` in `forced rollback`. Đếm bảng vẫn 2, chứng minh hàng 3 không commit.

**Điều ví dụ không chứng minh:** mọi triển khai `DataSource`/proxy luôn trả cùng Java object khi so sánh `==`; mọi database đều có cùng isolation hoặc timeout; hai database khác nhau sẽ tự rollback cùng nhau. Hãy kiểm tra transaction boundary và dữ liệu sau commit/rollback trong môi trường thực tế.

## 8. Dùng với `@Transactional` trong ứng dụng Spring

Một kiến trúc thường gặp:

~~~java
@Service
public class CheckoutService {
    private final OrderDao orders;
    private final AuditDao audits;

    public CheckoutService(OrderDao orders, AuditDao audits) {
        this.orders = orders;
        this.audits = audits;
    }

    @Transactional
    public void checkout(long orderId) {
        orders.markCompleted(orderId);
        audits.recordCompleted(orderId);
    }
}
~~~

Đây là ví dụ kiến trúc, **không phải class runnable độc lập**: cần hai DAO bean, transaction manager và hạ tầng xử lý `@Transactional`. Khi lời gọi đi qua Spring proxy/interceptor hợp lệ, Spring tạo hoặc tham gia transaction. DAO dùng `JdbcTemplate` hoặc `DataSourceUtils` trên cùng `DataSource` sẽ tham gia connection phù hợp.

Một vài tình huống cần hiểu:

- **Self-invocation:** một phương thức gọi `this.checkout(...)` trong cùng bean có thể bỏ qua proxy nên `@Transactional` không có hiệu lực mong muốn.
- **Rollback:** mặc định `RuntimeException` và `Error` khiến transaction theo `@Transactional` rollback; checked exception có thể cần `rollbackFor`. Bắt và nuốt ngoại lệ có thể khiến manager commit nếu không có dấu rollback-only.
- **Propagation:** `REQUIRED` tham gia transaction hiện có hoặc tạo mới; `REQUIRES_NEW` là transaction độc lập và có thể cần connection riêng. “Cùng request” không đồng nghĩa “cùng transaction”.
- **Transaction dài:** giữ kết nối và lock lâu; tránh gọi mạng hoặc đợi tác vụ bên ngoài trong transaction khi không cần.

Dù cho có `@Transactional`, DAO vẫn có thể vô tình dùng sai `DataSource` hoặc lấy connection trực tiếp từ pool. Vì vậy cần xác minh **transaction đã được kích hoạt** và **kết nối thực sự tham gia**.

## 9. `TransactionAwareDataSourceProxy` và `LazyConnectionDataSourceProxy`

### 9.1. Proxy transaction-aware cho mã JDBC không biết Spring

Nếu tích hợp mã cũ chỉ gọi:

~~~java
try (Connection c = dataSource.getConnection()) {
    // JDBC thuần.
}
~~~

mà không thể thay thành `DataSourceUtils`, Spring cung cấp `TransactionAwareDataSourceProxy` bao quanh một target `DataSource`. Connection handle do proxy trả về điều phối `getConnection` và `close` theo quy tắc Spring để tham gia transaction phù hợp.

Điều đó giải thích vì sao câu “`dataSource.getConnection` luôn bỏ qua transaction” là **sai** nếu biến `dataSource` thực tế tham chiếu `TransactionAwareDataSourceProxy`. Với một pool/`DataSource` chuẩn không có proxy, lời gọi trực tiếp có thể lấy kết nối ngoài transaction.

Khi tổ hợp nhiều proxy DataSource, cần cấu hình thứ tự đúng; `TransactionAwareDataSourceProxy` thường là lớp ngoài cùng của chuỗi proxy dành cho consumer legacy. Đối với mã mới, ưu tiên `JdbcTemplate` hoặc `DataSourceUtils` để dễ đọc và ít phụ thuộc wrapper.

### 9.2. Proxy lấy connection lười

`LazyConnectionDataSourceProxy` có thể trì hoãn việc lấy JDBC connection vật lý cho đến khi cần thực thi statement. Điều này hữu ích cho giao dịch “rỗng” không thực sự truy cập cơ sở dữ liệu. Vì có proxy, việc kiểm chứng connection bằng object identity/driver connection id có thể không phản ánh chính xác lịch sử cấp connection vật lý; kiểm tra bằng API Spring và kết quả transaction vẫn đáng tin hơn.

Việc dùng proxy lười không làm thay đổi nguyên tắc: DAO cần đúng nguồn dữ liệu và transaction manager, connection vẫn phải được quản lý đúng lifecycle.

## 10. Cùng luồng chưa chắc cùng `DataSource` hoặc cùng transaction

`TransactionSynchronizationManager` theo dõi tài nguyên theo key gắn với nguồn dữ liệu. Nếu transaction manager đang quản lý `appDataSource` nhưng DAO gọi:

~~~java
Connection c = DataSourceUtils.getConnection(reportingDataSource);
~~~

thì connection từ `reportingDataSource` không tự động thuộc transaction của `appDataSource`. Tương tự, tự tạo một `DriverManagerDataSource` mới với cùng JDBC URL bên trong DAO không có nghĩa Spring coi nó là cùng bean đã bind.

**Cách tổ chức dễ kiểm soát:**

- Inject `DataSource` và `JdbcTemplate` từ cùng cấu hình nguồn vào các DAO liên quan.
- Để transaction manager quản lý đúng `DataSource` mà các DAO sử dụng.
- Nếu có nhiều nguồn dữ liệu, xác định manager nào được chọn ở từng `@Transactional` và cần tính nhất quán trên nguồn nào.
- Không xem một local `DataSourceTransactionManager` như cơ chế transaction phân tán tự động trên nhiều database.

### JPA và JTA

`DataSourceUtils` có hỗ trợ transaction synchronization trong một số ngữ cảnh dùng `JpaTransactionManager` hoặc `JtaTransactionManager`. Tuy nhiên việc JDBC thực sự chia sẻ transaction JPA/JTA phụ thuộc vào cách khai báo cùng `DataSource`, provider, tài nguyên được enlist và transaction coordinator. Không được giả định mọi `EntityManager` và mọi JDBC `Connection` tự thuộc một transaction chỉ vì cùng phương thức service.

Trong JPA, `EntityManager`/persistence context có vòng đời riêng; không xem nó như `Connection` thô. Với reactive R2DBC, cần sử dụng `ConnectionFactory`, transaction manager và context tương ứng; `DataSourceUtils` là tiện ích cho JDBC imperative.

## 11. Kết nối tham gia transaction thường gắn với thread

Transaction imperative của Spring thường dùng `ThreadLocal` trong `TransactionSynchronizationManager` để quản lý tài nguyên của luồng hiện tại. Hậu quả thực hành:

- Không lưu `Connection` vào field của singleton DAO hoặc cache để dùng trong request khác.
- Không truyền connection đang bind sang thread khác rồi giả định nó tiếp tục thuộc transaction cũ.
- `@Async`, `CompletableFuture.supplyAsync` hoặc một executor riêng không tự mang theo JDBC transaction imperative của luồng gọi; nếu tác vụ async cần transaction, hãy thiết kế transaction riêng ở tác vụ ấy.
- Trong mã chạy bằng virtual threads, mỗi luồng vẫn có ngữ cảnh riêng; không tự động có một transaction chung khi chia công việc sang nhiều thread.
- Luôn trả connection trong đúng scope qua `finally`; tránh giữ nó qua lời gọi API mạng hoặc bước nghiệp vụ kéo dài.

**Đừng kết luận** một kết nối được Spring bind sẽ phù hợp để dùng đa luồng. Nhiều JDBC `Connection` không bảo đảm thread-safety cho việc dùng đồng thời.

## 12. Bảng chẩn đoán lỗi

| Triệu chứng | Nguyên nhân có thể xảy ra | Hướng kiểm tra |
| --- | --- | --- |
| Service rollback nhưng một INSERT vẫn tồn tại | DAO dùng raw `dataSource.getConnection` từ pool thông thường hoặc nguồn khác | Kiểm tra cách lấy connection, cùng DataSource, transaction manager |
| `isConnectionTransactional` trả `false` trong DAO | Không có transaction/synchronization tương ứng; khác DataSource hoặc khác thread | Xác minh transaction thực sự được kích hoạt, key/tài nguyên đúng |
| `Connection is closed` trước commit | DAO đã `close()` connection đang bind hoặc bọc nó bằng `try-with-resources` | Đổi thành `DataSourceUtils.releaseConnection`; đóng riêng statement/result set |
| Cạn connection pool | Không release ngoài transaction, transaction kéo dài hoặc code giữ connection | `finally` release, kiểm tra active/idle/waiting và transaction duration |
| DAO JDBC không thấy rollback cùng JPA | JDBC không được enlist theo cấu hình JPA/JTA hoặc dùng sai nguồn | Kiểm tra JpaTransactionManager, DataSource và hạ tầng provider |
| Lỗi câu SQL vẫn là checked `SQLException` | Mã JDBC thuần không sử dụng cơ chế dịch lỗi truy vấn | Ưu tiên `JdbcTemplate` hoặc xử lý/translate rõ ràng |
| Timeout của transaction không áp dụng lên statement thủ công | Không áp dụng query timeout cho statement do DAO tự tạo | `applyTransactionTimeout` hoặc dùng JdbcTemplate |
| Transaction bên ngoài không bao phủ async job | Transaction imperative thread-bound | Tạo transaction riêng tại thread thực thi async |
| `releaseConnection` không đóng ngay connection | Connection còn thuộc transaction; đây có thể là hành vi đúng | Xác minh transaction kết thúc và cleanup, không ép đóng sớm |

**Thứ tự chẩn đoán hiệu quả:** (1) transaction boundary có thật không, (2) transaction manager nào, (3) cùng bean `DataSource` không, (4) DAO lấy connection bằng API nào, (5) connection được release thế nào, (6) kiểm chứng dữ liệu sau commit/rollback. Khi có lỗi dữ liệu, không chỉ kiểm tra việc annotation `@Transactional` có tồn tại trên source.

## 13. Những sai lầm cần tránh

**Sai lầm 1: “`DataSourceUtils` sẽ tự tạo transaction.”** Không. Nó lấy/trả connection đúng ngữ cảnh; service hoặc `TransactionTemplate` vẫn phải mở transaction thích hợp.

**Sai lầm 2: “Lúc nào cũng có thể gọi `Connection.close()`.”** Không. Connection đang được Spring bind phải được trả qua `releaseConnection` để transaction manager tiếp tục quản lý.

**Sai lầm 3: “`releaseConnection` sẽ commit.”** Không. Nó quản lý tài nguyên, còn commit/rollback thuộc transaction manager.

**Sai lầm 4: “Hai DAO dùng chung JDBC URL tức là chung transaction.”** Không. Cần đối chiếu `DataSource`, transaction manager, resource binding và khả năng tham gia giao dịch của tài nguyên.

**Sai lầm 5: “`JdbcTemplate` cần gọi `DataSourceUtils` thủ công trước mỗi query.”** Không. `JdbcTemplate` đã tích hợp cơ chế này.

**Sai lầm 6: “Có transaction rồi nên không cần đóng statement/result set.”** Không. Đóng statement/result set đúng thời điểm độc lập với connection đang được giữ cho transaction.

**Sai lầm 7: “Exception do JDBC thủ công luôn là `DataAccessException`.”** Không. `DataSourceUtils` dịch lỗi cấp connection; `JdbcTemplate` xử lý translation cho những thao tác SQL mà nó quản lý.

**Sai lầm 8: “`@Transactional` tự động lan qua mọi thread.”** Không trong mô hình imperative thông thường. Thiết kế riêng cho công việc bất đồng bộ.

## 14. Câu hỏi tự kiểm tra

**1. Gọi `DataSourceUtils.getConnection` khi không có Spring transaction thì có lỗi không?**  
Không. API vẫn lấy connection được; mã gọi phải release nó và không tự được bảo đảm rollback nhiều statement.

**2. Trong transaction JDBC của `DataSourceTransactionManager`, vì sao hai DAO dùng `DataSourceUtils` có thể dùng cùng connection?**  
Vì manager bind connection holder vào ngữ cảnh hiện tại theo `DataSource`; `DataSourceUtils` tra cứu tài nguyên đã bind ấy.

**3. Vì sao không viết `try (Connection c = DataSourceUtils.getConnection(ds))`?**  
Vì Java gọi `c.close()` trực tiếp khi thoát block, có thể đóng connection Spring còn cần. Dùng `try/finally` + `releaseConnection`.

**4. `releaseConnection` được gọi trước khi service kết thúc thì transaction có bị commit không?**  
Không. Với connection đang bind, Spring giữ nó đến khi transaction manager commit/rollback và cleanup.

**5. Mã dùng `JdbcTemplate` cần thay đổi gì để tham gia transaction?**  
Bảo đảm các thao tác dùng đúng `DataSource` và transaction manager, và transaction boundary thật sự được kích hoạt. `JdbcTemplate` tự dùng cơ chế lấy connection của Spring.

**6. `isConnectionTransactional` là `true` có bảo đảm mọi câu SQL của hệ thống rollback cùng nhau?**  
Không. Nó chỉ phản ánh binding của connection cụ thể theo context/source hiện tại; các câu SQL ở connection hay nguồn khác có thể thuộc transaction khác.

**7. Khi nào `TransactionAwareDataSourceProxy` hữu ích?**  
Khi mã JDBC legacy chỉ biết `DataSource.getConnection` và `Connection.close` cần tham gia transaction Spring mà khó sửa mã nguồn. Với mã mới, ưu tiên abstraction phù hợp.

**8. Bài kiểm thử nào chứng minh việc tham gia transaction?**  
Ghi hai thay đổi qua hai đường truy cập JDBC khác nhau dưới một transaction, cố ý ném runtime exception, rồi đọc database kiểm tra cả hai thay đổi đều bị rollback.

## 15. Tài liệu tham khảo chính thức

- [Spring Framework: Controlling Database Connections](https://docs.spring.io/spring-framework/reference/data-access/jdbc/connections.html) – `DataSourceUtils`, proxy transaction-aware, transaction manager và `JdbcTemplate`.
- [Spring Framework: Synchronizing Resources with Transactions](https://docs.spring.io/spring-framework/reference/data-access/transaction/tx-resource-synchronization.html) – cơ chế liên kết tài nguyên với giao dịch.
- [DataSourceUtils Javadoc (Spring 6.1.14)](https://docs.spring.io/spring-framework/docs/6.1.14/javadoc-api/org/springframework/jdbc/datasource/DataSourceUtils.html) – hợp đồng của `getConnection`, `releaseConnection`, `isConnectionTransactional` và timeout.
- [Spring Framework: Programmatic Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/programmatic.html) – cách sử dụng `TransactionTemplate`.

**Ghi nhớ:** `DataSourceUtils` giúp JDBC code sử dụng kết nối phù hợp với transaction mà Spring đang quản lý và giải phóng kết nối đúng thời điểm. Một transaction thành công vẫn cần ranh giới nghiệp vụ, đúng transaction manager, cùng `DataSource` và chính sách commit/rollback phù hợp.
