# LazyConnectionDataSourceProxy và thời điểm lấy kết nối vật lý

Trong Spring Framework, ứng dụng có thể bắt đầu một giao dịch qua @Transactional mà **chưa cần chạy SQL**. Nếu mỗi giao dịch đều mượn JDBC Connection thật ngay lập tức, những nhánh chỉ kiểm tra cache, trả dữ liệu đã có hoặc thoát sớm vẫn có thể chiếm kết nối trong pool. **LazyConnectionDataSourceProxy** cho phép trì hoãn việc mượn Connection từ DataSource đích đến khi mã thực sự cần tạo JDBC Statement.

Bài thuộc nhóm **Kết nối và tài nguyên** của module **Spring Framework - data-access**. Trọng tâm là phân biệt Connection logic với Connection thật, hiểu chính xác **mốc lấy connection vật lý**, cách Spring transaction và JdbcTemplate phối hợp với proxy, cấu hình qua các phiên bản Spring Boot, đo kiểm thực tế và tránh những cách hiểu sai.

## 1. Phân biệt Connection logic và Connection vật lý

**Logical Connection / connection handle** là đối tượng java.sql.Connection mà LazyConnectionDataSourceProxy.getConnection() trả về. Đối tượng này là một proxy: nó ghi nhận một số trạng thái, nhận lời gọi JDBC và chỉ tìm tới connection bên dưới khi cần.

**Target/physical Connection** là Connection do DataSource đích cấp, thường là một connection đã được HikariCP quản lý. Nói “mượn connection vật lý từ pool” **không nhất thiết có nghĩa tạo một TCP socket mới**: HikariCP có thể cấp lại một connection đã mở và đang rảnh.

~~~text
Spring service / JdbcTemplate / transaction manager
                        |
                        v
             LazyConnectionDataSourceProxy
                        |
               getConnection()
                        |
                        v
              Logical Connection
                        |
            Có tạo JDBC Statement?
                  /          \
                Chưa          Có
                 |             |
                 v             v
         Chưa cần mượn    targetDataSource.getConnection()
          connection thật           |
                                   v
                              HikariCP pool
                                   |
                                   v
                               Database
~~~

Với HikariCP, số **Active** phản ánh kết nối đang được mượn; **Idle** là kết nối đang rảnh trong pool, còn **Pending** là lời gọi đang đợi mượn. Một logical Connection chưa truy cập target **không tự động làm Active tăng**. Khi proxy phải mượn target connection, pool vẫn áp dụng maximumPoolSize, connectionTimeout và các giới hạn riêng.

**Không nhầm lazy proxy với pool:** LazyConnectionDataSourceProxy chỉ điều phối thời điểm gọi DataSource đích; nó không tạo, tái sử dụng, giới hạn hay health-check connection vật lý thay HikariCP.

## 2. Mốc quan trọng: tạo Statement trước khi thực thi SQL

Theo Javadoc của Spring, LazyConnectionDataSourceProxy trì hoãn việc lấy JDBC Connection thật **đến lần tạo JDBC Statement đầu tiên**. Các thao tác thường kích hoạt gồm:

- Connection.createStatement()
- Connection.prepareStatement(sql)
- Connection.prepareCall(sql)

Điểm quan trọng là **tạo Statement**, không cần đợi executeQuery(), executeUpdate() hoặc execute(). Một ứng dụng có thể mượn connection thật rồi không chạy SQL vì đã tạo PreparedStatement nhưng bỏ qua execute.

| Hành động | DataSource là HikariCP trực tiếp | DataSource là LazyConnectionDataSourceProxy |
| --- | --- | --- |
| dataSource.getConnection() | Mượn từ pool ngay | Trả logical handle, thường chưa mượn |
| connection.setAutoCommit(false) | Thiết lập trên connection đã mượn | Có thể được ghi nhận, áp dụng khi lấy target |
| connection.setReadOnly(true) | Thiết lập trên connection đã mượn | Có thể được ghi nhận và áp dụng sau |
| connection.setTransactionIsolation(...) | Thiết lập trên connection đã mượn | Có thể được ghi nhận và áp dụng sau |
| connection.prepareStatement(sql) | Dùng connection đang có | **Mượn target connection nếu chưa mượn** |
| statement.executeQuery() | Thực thi trên connection hiện có | Thực thi trên connection đã lấy lúc tạo statement |
| connection.close() khi chưa tạo Statement | Trả connection đang mượn | Đóng logical handle, có thể chưa mượn target lần nào |
| commit()/rollback() khi chưa tạo Statement | Gọi trên connection thật | Proxy có thể bỏ qua vì không có transaction JDBC thực tế |

Đây là quy tắc điển hình trong Spring JDBC; còn việc đọc metadata, unwrap connection vendor hoặc các API chuyên biệt có thể buộc truy cập target sớm. Không giả định **mọi** phương thức của java.sql.Connection đều được trì hoãn như setReadOnly.

### 2.1. Ví dụ về mốc prepareStatement

~~~java
// Đoạn này nằm trong ứng dụng đã khai báo lazyDataSource.
try (Connection connection = lazyDataSource.getConnection()) {
    connection.setReadOnly(true);

    // Có thể mượn JDBC Connection thật NGAY Ở ĐÂY.
    try (PreparedStatement statement =
            connection.prepareStatement("SELECT 1")) {
        // Chưa execute, nhưng target DataSource có thể đã được gọi.
        try (ResultSet result = statement.executeQuery()) {
            if (result.next()) {
                System.out.println(result.getInt(1));
            }
        }
    }
}
~~~

Đoạn Java chỉ minh họa các API; biến lazyDataSource phải được cấu hình trước, và driver/database hỗ trợ SELECT 1. Câu lệnh in 1 trên H2/PostgreSQL thông thường. Phép đo quan trọng nhất không phải output SQL mà là thời điểm target.getConnection() được gọi.

### 2.2. Vì sao getConnection() không đồng nghĩa mượn vật lý?

Một logical Connection có thể tồn tại mà chưa có target Connection; proxy giữ các thuộc tính giao dịch như auto-commit, isolation và read-only rồi áp dụng chúng khi target được tạo/lấy. Nếu handle được đóng trước khi tạo Statement thì có thể chưa cần tài nguyên database.

**Ngoại lệ rất quan trọng về lần truy cập đầu:** từ Spring Framework **6.1.2**, LazyConnectionDataSourceProxy có thể lấy một connection ở lần truy cập đầu tiên để xác định các thuộc tính mặc định auto-commit và transaction isolation. Có thể gọi checkDefaultConnectionProperties() trước để dịch công việc này sang giai đoạn khởi tạo. Vì thế phát biểu “getConnection() không bao giờ gọi pool” là sai; hãy phân biệt **lượt khởi tạo đặc tính mặc định** với lượt mượn để thực thi SQL.

## 3. Dòng thời gian khi dùng @Transactional

Một phương thức được Spring transaction interceptor xử lý có thể trải qua hai nhánh khác nhau:

~~~text
00. Interceptor bắt đầu @Transactional
01. Transaction manager nhận logical Connection từ lazy DataSource
02. Ghi nhận setAutoCommit(false), isolation và readOnly khi cần
03. Mã nghiệp vụ kiểm tra điều kiện hoặc dữ liệu đã có

NHÁNH A: không truy cập JDBC
04A. Không tạo Statement
05A. Spring kết thúc transaction logic
06A. Có thể không mượn connection thật từ pool

NHÁNH B: truy cập JDBC
04B. JdbcTemplate tạo PreparedStatement đầu tiên
05B. Lazy proxy gọi target DataSource -> mượn pool connection
06B. Áp dụng thuộc tính giao dịch rồi chuẩn bị và chạy SQL
07B. Kết thúc transaction: commit/rollback, giải phóng connection
~~~

Ba mốc cần tách biệt:

1. **Bắt đầu transaction Spring:** interceptor/transaction manager xử lý metadata giao dịch.
2. **Nhận logical Connection:** đối tượng proxy có thể được gắn với transaction mà chưa chiếm kết nối pool.
3. **Lần tạo Statement:** connection thật thường được lấy; SQL có thể chỉ chạy sau đó.

Khi đã thực thi JDBC bên trong transaction, connection thường được giữ đến **cuối transaction**, ngay cả khi JdbcTemplate đã xong truy vấn. Lazy proxy chủ yếu giảm **thời gian từ lúc bắt đầu transaction đến SQL đầu tiên**; nó không tự trả connection giữa các câu SQL trong một transaction đang mở.

### 3.1. Ví dụ service có và không truy cập database

~~~java
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class AvailabilityService {
    private final JdbcTemplate jdbc;

    public AvailabilityService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional(readOnly = true)
    public int check(boolean queryDatabase) {
        if (!queryDatabase) {
            // Không tạo bất cứ JDBC Statement nào ở nhánh này.
            return 0;
        }

        Integer value = jdbc.queryForObject(
            "SELECT 1", Integer.class
        );
        return value == null ? 0 : value;
    }
}
~~~

Đây là class của ứng dụng Spring đã có JdbcTemplate, DataSource, transaction manager và driver, không phải Java main độc lập. Với Spring JDBC được wiring nhất quán cùng lazy DataSource:

- check(false): Spring có thể xử lý transaction rỗng mà không mượn target connection, nếu không có thao tác khởi tạo hay can thiệp khác.
- check(true): JdbcTemplate phải tạo Statement để chạy SELECT 1, nên proxy mượn connection thật; kết quả với H2/PostgreSQL là 1.

@Transactional chỉ có tác dụng khi đi qua **Spring proxy**; tự gọi check() từ một phương thức khác trong cùng instance thường không đi qua interceptor theo proxy mode thông thường. Khi không có transaction thật, thời điểm trả connection khác với lúc trong transaction: JdbcTemplate thường giải phóng resource sau từng thao tác.

### 3.2. JdbcTransactionManager và DataSourceTransactionManager

Spring JDBC hỗ trợ **DataSourceTransactionManager** và **JdbcTransactionManager**. Cả hai quản lý transaction cho một JDBC DataSource; JdbcTransactionManager còn có khả năng translate một số lỗi JDBC khi commit/rollback thành các loại DataAccessException phù hợp.

Để transaction và DAO dùng **cùng connection được đồng bộ**, transaction manager và JdbcTemplate phải tham chiếu tới **cùng lazy DataSource bean**. Nếu một bên dùng proxy còn một bên dùng raw pool trực tiếp mà không kiểm tra resource identity, các lời gọi JDBC có thể không tham gia transaction như mong đợi.

DataSourceUtils.getConnection(dataSource) là cách Spring đồng bộ và tái sử dụng connection gắn với transaction. JdbcTemplate đã sử dụng cơ chế này; code mới thường nên dùng JdbcTemplate thay vì tự lấy/đóng connection thủ công trong @Transactional.

### 3.3. Read-only không phải công cụ phân quyền

@Transactional(readOnly = true) là metadata của Spring. Tùy transaction manager, JDBC driver và DBMS, nó có thể chỉ là một **hint**. Nếu cấu hình DataSourceTransactionManager.setEnforceReadOnly(true), manager có thể thực thi lệnh SQL như SET TRANSACTION READ ONLY vào đầu transaction. Việc tạo Statement này **buộc proxy mượn target connection sớm**, kể cả nghiệp vụ sau đó không đọc dữ liệu.

Không coi việc “bị lấy connection sớm” trong trường hợp trên là lỗi của lazy proxy: chính cấu hình transaction manager yêu cầu chạy SQL ngay từ đầu. Muốn bảo vệ dữ liệu thật sự cần phân quyền DB, transaction enforcement và chính sách ghi phù hợp.

## 4. Cơ chế ghi nhận thuộc tính trước khi lấy target

LazyConnectionDataSourceProxy là lớp:

~~~java
org.springframework.jdbc.datasource.LazyConnectionDataSourceProxy
~~~

Lớp kế thừa DelegatingDataSource và cung cấp Connection proxy. Trước khi lấy connection thật, proxy có thể giữ auto-commit, transaction isolation và read-only để áp dụng sau. Commit/rollback không có Statement nào đã tạo có thể được bỏ qua: không có transaction JDBC thực sự cần commit/rollback tại target.

Để trả giá trị chính xác từ connection.getAutoCommit() và connection.getTransactionIsolation() khi chưa có target, proxy cần biết **giá trị mặc định** của driver/pool. Spring cung cấp:

~~~java
lazy.checkDefaultConnectionProperties();
~~~

Lời gọi này chủ động mượn target connection để kiểm tra các mặc định khi có thể; phù hợp khi muốn khởi tạo chúng trước lúc đo transaction rỗng. Một lựa chọn khác khi **đã xác nhận giá trị thật** của target:

~~~java
lazy.setDefaultAutoCommit(true);
lazy.setDefaultTransactionIsolation(
    Connection.TRANSACTION_READ_COMMITTED
);
~~~

Không đặt các giá trị trên theo suy đoán để “bảo đảm lazy”: thiết lập sai khác với target có thể khiến ngữ nghĩa giao dịch hoặc giá trị đọc lại không đúng. Một lượt getConnection đầu tiên để xác lập defaults không phủ nhận lợi ích trì hoãn của những lượt sau.

Không ép kiểu logical Connection thành connection vendor hoặc Hikari ProxyConnection. Nếu buộc phải dùng driver-specific API qua unwrap hoặc ConnectionProxy.getTargetConnection(), thao tác đó có thể khiến target được lấy ngay và tác động đến phép đo.

## 5. Cấu hình trong Spring Boot: lưu ý theo phiên bản

### 5.1. Spring Boot 3.x / wiring tường minh

Các phiên bản Boot 3.x không có thuộc tính auto-config lazy JDBC mới của Boot 4.1. Có thể cấu hình Bean theo cách tường minh, ví dụ ứng dụng dùng **Spring Boot 3.3+, Spring JDBC, HikariCP, PostgreSQL và Java 17+**.

Tệp application.yml:

~~~yaml
spring:
  datasource:
    url: jdbc:postgresql://localhost:5432/demo
    username: demo
    hikari:
      pool-name: main-pool
      maximum-pool-size: 10
      connection-timeout: 3000
~~~

Cung cấp password bằng biến môi trường **SPRING_DATASOURCE_PASSWORD** hoặc cơ chế secret phù hợp; không đưa mật khẩu thật vào bài học. Dependency Gradle trong dự án dùng Spring Boot dependency management/BOM:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    runtimeOnly 'org.postgresql:postgresql'
}
~~~

Tệp LazyJdbcConfig.java:

~~~java
import com.zaxxer.hikari.HikariDataSource;
import javax.sql.DataSource;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.autoconfigure.jdbc.DataSourceProperties;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Primary;
import org.springframework.jdbc.datasource.LazyConnectionDataSourceProxy;
import org.springframework.jdbc.support.JdbcTransactionManager;

@Configuration(proxyBeanMethods = false)
public class LazyJdbcConfig {

    @Bean("physicalDataSource")
    @ConfigurationProperties("spring.datasource.hikari")
    HikariDataSource physicalDataSource(
            DataSourceProperties properties) {
        return properties.initializeDataSourceBuilder()
                .type(HikariDataSource.class)
                .build();
    }

    @Bean("dataSource")
    @Primary
    DataSource dataSource(
            @Qualifier("physicalDataSource") HikariDataSource physical) {
        return new LazyConnectionDataSourceProxy(physical);
    }

    @Bean
    JdbcTransactionManager transactionManager(
            @Qualifier("dataSource") DataSource dataSource) {
        return new JdbcTransactionManager(dataSource);
    }
}
~~~

Đây là **cấu hình bên trong dự án Spring Boot** đã có JDBC starter, driver và DataSourceProperties được Boot đăng ký; không phải tệp Java độc lập chạy bằng javac. Các vai trò:

- physicalDataSource: HikariDataSource thật, quản lý pooled connections.
- dataSource: LazyConnectionDataSourceProxy, được @Primary để DAO/JdbcTemplate ưu tiên.
- transactionManager: dùng cùng bean proxy như DAO; giao dịch rỗng có thể không mượn pool connection.

Nếu dự án có nhiều DataSource, nhiều transaction manager hoặc JPA, cần dùng qualifier và cấu hình cụ thể để bảo đảm đúng bean. Không mặc định ví dụ một JDBC resource phù hợp với hệ nhiều database hay transaction phân tán.

### 5.2. Spring Boot 4.1+ có thuộc tính connection-fetch

Spring Boot **4.1** giới thiệu khả năng bọc pooled DataSource auto-configured thành lazy proxy bằng thuộc tính:

~~~properties
spring.datasource.connection-fetch=lazy
~~~

Cú pháp YAML tương đương:

~~~yaml
spring:
  datasource:
    connection-fetch: lazy
~~~

Ở phiên bản có hỗ trợ, Spring Boot tự tạo wrapper theo cơ chế auto-configuration. **Không** sao chép thuộc tính này sang Boot 3.3/3.5 và mặc định nó có tác dụng; phải đối chiếu tài liệu của phiên bản đang chạy. Nếu đã bật auto-wrap ở Boot 4.1+, cần tránh tự bọc thêm một lazy proxy trùng lặp.

Bean DataSource bên ngoài có thể là proxy, nên ép kiểu trực tiếp thành HikariDataSource sẽ sai. Dùng cơ chế unwrap/lookup target đúng cách nếu cần đọc cấu hình và metric của pool vật lý.

## 6. Thứ tự các DataSource proxy và transaction participation

Ngoài LazyConnectionDataSourceProxy, Spring có **TransactionAwareDataSourceProxy**. Chức năng của chúng khác nhau:

| Thành phần | Vai trò |
| --- | --- |
| HikariDataSource | Quản lý kết nối thực và giới hạn pool |
| LazyConnectionDataSourceProxy | Trì hoãn mượn connection thực đến lúc cần Statement |
| TransactionAwareDataSourceProxy | Giúp mã JDBC thuần dùng DataSource/getConnection() tham gia Spring-managed transaction |
| DataSourceUtils/JdbcTemplate | Lấy/trả connection tương thích với Spring transaction synchronization |
| JdbcTransactionManager | Mở, commit, rollback, giải phóng JDBC transaction |

Khi cần **cả LazyConnectionDataSourceProxy lẫn TransactionAwareDataSourceProxy**, tài liệu Spring yêu cầu TransactionAwareDataSourceProxy nằm **ngoài cùng**:

~~~text
Mã JDBC cũ
    |
    v
TransactionAwareDataSourceProxy
    |
    v
LazyConnectionDataSourceProxy
    |
    v
HikariDataSource -> Database

JdbcTemplate -> DataSourceUtils -> LazyConnectionDataSourceProxy -> pool
TransactionManager -------------> LazyConnectionDataSourceProxy -> pool
~~~

Với code mới, ưu tiên JdbcTemplate hoặc DataSourceUtils; hiếm khi phải thêm TransactionAwareDataSourceProxy. Transaction manager nên dùng DataSource phù hợp để đồng bộ transaction (trong ví dụ là lazy proxy), không tự chọn lớp TransactionAwareDataSourceProxy ngoài cùng làm managed resource khi chưa hiểu cơ chế unwrap và binding.

Spring đồng bộ tài nguyên dựa trên DataSource identity/key. Nếu tạo nhiều proxy riêng biệt bao quanh cùng Hikari pool và cho DAO/manager dùng khác key, có thể tạo nhiều connection cùng lúc và làm mã tưởng ở trong transaction nhưng truy vấn lại ở connection khác.

## 7. Lazy connection hỗ trợ routing theo readOnly/isolation

Một hệ thống có thể dùng DataSource router lựa chọn pool ghi (primary) hoặc pool chỉ đọc (replica) theo transaction flag. Nếu router bị gọi **trước khi** Spring gắn read-only/isolation metadata, quyết định routing có thể sai.

Đặt lazy proxy trước router có thể trì hoãn việc chọn pool cho đến lúc thực sự tạo Statement:

~~~text
@Transactional(readOnly = true)
            |
   Spring transaction context
            |
 LazyConnectionDataSourceProxy
            |
 AbstractRoutingDataSource
        /         \
   primary      replica
     pool        pool
~~~

Spring 6.1.2 trở lên còn có API gắn read-only DataSource trực tiếp cho lazy proxy:

~~~java
LazyConnectionDataSourceProxy lazy =
        new LazyConnectionDataSourceProxy(primaryDataSource);
lazy.setReadOnlyDataSource(replicaDataSource);
~~~

Đoạn mã là minh họa trong ứng dụng đã khai báo primaryDataSource và replicaDataSource. Khi transaction được đánh dấu readOnly và điều kiện framework cho phép, proxy có thể chọn DataSource chỉ đọc lúc lấy target connection. Thực tế cần kiểm tra driver, pool, transaction metadata và transaction manager đang hoạt động.

Read-only **không** tự bảo đảm mọi câu lệnh write bị cấm, và replica có thể bị **replication lag**. Luồng ghi rồi lập tức đọc cần yêu cầu consistency riêng; có thể phải đọc primary, không tùy tiện routing sang replica. Cần xét thêm propagation, nested transaction, tự gọi bean nội bộ và lựa chọn pool trong ngữ cảnh transaction thật.

## 8. Demo Java 17+ đo chính xác lượt mượn target connection

Ví dụ này dùng **Spring JDBC 6.2.14 và H2**, chạy bằng Gradle. Một CountingDataSource bọc DriverManagerDataSource (không phải Hikari pool) để đếm bao nhiêu lần target.getConnection() được gọi. Ví dụ minh họa **thời điểm**, không đo thông lượng pool.

Tệp build.gradle:

~~~groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-jdbc:6.2.14'
    runtimeOnly 'com.h2database:h2:2.3.232'
}

application {
    mainClass = 'example.LazyFetchDemo'
}
~~~

Tệp src/main/java/example/LazyFetchDemo.java:

~~~java
package example;

import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.concurrent.atomic.AtomicInteger;
import javax.sql.DataSource;
import org.springframework.jdbc.datasource.DelegatingDataSource;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.jdbc.datasource.LazyConnectionDataSourceProxy;

public class LazyFetchDemo {
    public static void main(String[] args) throws SQLException {
        DataSource raw = new DriverManagerDataSource(
                "jdbc:h2:mem:lazy_demo;DB_CLOSE_DELAY=-1", "sa", ""
        );
        CountingDataSource counting = new CountingDataSource(raw);
        LazyConnectionDataSourceProxy lazy =
                new LazyConnectionDataSourceProxy(counting);

        // Giá trị mặc định được biết trước trong bài thử H2.
        // Không tự áp dụng nếu chưa kiểm tra target DataSource thật.
        lazy.setDefaultAutoCommit(true);
        lazy.setDefaultTransactionIsolation(
                Connection.TRANSACTION_READ_COMMITTED
        );

        try (Connection connection = lazy.getConnection()) {
            System.out.println("after getConnection: "
                    + counting.borrowCount());

            connection.setReadOnly(true);
            System.out.println("after setReadOnly: "
                    + counting.borrowCount());

            try (PreparedStatement statement =
                         connection.prepareStatement("SELECT 1")) {
                System.out.println("after prepareStatement: "
                        + counting.borrowCount());

                try (ResultSet result = statement.executeQuery()) {
                    result.next();
                    System.out.println("SQL value: " + result.getInt(1));
                }
            }
        }

        System.out.println("after close: " + counting.borrowCount());
    }

    static final class CountingDataSource extends DelegatingDataSource {
        private final AtomicInteger count = new AtomicInteger();

        CountingDataSource(DataSource target) {
            super(target);
        }

        @Override
        public Connection getConnection() throws SQLException {
            Connection result = super.getConnection();
            count.incrementAndGet();
            return result;
        }

        int borrowCount() {
            return count.get();
        }
    }
}
~~~

Chạy khi có Gradle Wrapper trong dự án:

~~~bash
./gradlew run
~~~

Trên PowerShell/Windows:

~~~powershell
.\gradlew.bat run
~~~

Bỏ qua thông báo Gradle, stdout do main in:

~~~text
after getConnection: 0
after setReadOnly: 0
after prepareStatement: 1
SQL value: 1
after close: 1
~~~

Giải thích: trả logical handle chưa tăng count; setReadOnly được ghi nhận; **prepareStatement** yêu cầu target Connection, nên count tăng thành 1; thực thi SELECT 1 trả số 1; close không làm giảm **tổng lượt mượn** đã đếm. Nếu bỏ hai setter mặc định hoặc thay phiên bản/driver, proxy có thể mượn một connection sớm để kiểm tra default auto-commit/isolation; khi đó cần điều chỉnh phép đo theo lượt khởi tạo.

Vì chương trình import Spring JDBC và driver H2, chỉ gọi javac/java mà **không có classpath dependency** sẽ báo thiếu package. Gradle tải và cung cấp jar cần thiết. Đối với Java thuần chỉ dùng JDK thì có thể dùng javac/java trực tiếp.

### 8.1. Đừng lẫn các loại số đếm

- **Borrow count trong demo:** tổng số lần target DataSource.getConnection() được gọi.
- **HikariCP Active:** số connection đang được mượn tại thời điểm quan sát.
- **HikariCP Total:** số connection đang được pool quản lý.
- **Số TCP socket mới:** có thể thấp hơn borrow count vì pool tái sử dụng kết nối.
- **Số câu SQL:** có thể lớn hơn borrow count vì nhiều Statement dùng chung một connection.

Không thể suy ra “pool mở thêm connection” chỉ từ borrow count tăng, cũng không thể chứng minh “không mượn connection” chỉ bằng cách không thấy log SQL.

## 9. Quan sát Spring Boot Actuator và xác minh hiệu quả

Với Actuator/Micrometer đã được cấu hình và expose phù hợp, HikariCP thường cung cấp các metric như:

~~~text
hikaricp.connections.active
hikaricp.connections.idle
hikaricp.connections.pending
hikaricp.connections.acquire
hikaricp.connections.usage
~~~

Tên metric thực tế phụ thuộc phiên bản/registry, cần liệt kê meter được expose. Ví dụ môi trường test đã bật metrics:

~~~bash
curl http://localhost:8080/actuator/metrics
curl http://localhost:8080/actuator/metrics/hikaricp.connections.active
~~~

Để chứng minh lazy hoạt động đúng:

1. Đo **DataSource bean nào** được JdbcTemplate/transaction manager sử dụng.
2. Instrument target.getConnection() ngay dưới lazy proxy; phân biệt lượt khởi tạo default properties.
3. Ghi nhận mốc vào transaction, logical getConnection, tạo Statement và execute SQL.
4. Theo dõi pool Active/Idle/Pending cùng connection acquire/usage time.
5. Đối chiếu truy vấn khởi tạo schema, Flyway/Liquibase, health check, Hibernate validation và các job có thể mượn connection ngoài nghiệp vụ.
6. So sánh tải giống nhau trước/sau bật lazy; đo cả latency, throughput và DB metrics.

Active=0 tại một thời điểm **không đủ** khẳng định không truy vấn nào chạy: connection có thể đã mượn rồi trả giữa hai lần scrape. Ngược lại, Active tăng ở một nhánh không tạo Statement trong chính service có thể do một thành phần khác đang chạy đồng thời.

### Bảng dự đoán mượn connection

| Tình huống | Có thể mượn target connection? |
| --- | --- |
| Mở logical connection, setReadOnly, close, không Statement | Thường không, sau khởi tạo defaults |
| Tạo PreparedStatement rồi không execute | **Có** |
| Chạy JdbcTemplate.queryForObject("SELECT 1") | **Có** |
| @Transactional rỗng không tạo Statement | Thường không, nếu không có xử lý DB khác |
| Transaction manager chạy SET TRANSACTION READ ONLY | **Có**, vì tạo Statement |
| ConnectionProxy.getTargetConnection() hoặc unwrap native | Có thể có ngay |
| Đọc kết quả từ JPA/Hibernate cache | Có thể không, tùy provider/transaction handling |
| JDBC đã chạy SQL trong transaction rồi gọi HTTP bên ngoài | Connection có thể tiếp tục Active đến cuối transaction |

## 10. Ranh giới của lợi ích lazy và lỗi thường gặp

### 10.1. Lazy không giải quyết query chậm hay transaction giữ connection lâu

Proxy chỉ giảm thời gian chiếm connection **trước lần truy cập JDBC đầu tiên** và loại bỏ lượt mượn của transaction rỗng. Sau khi query đầu tiên chạy, một transaction kéo dài với lock wait, gọi dịch vụ HTTP bên ngoài hay xử lý tính toán nặng vẫn có thể giữ connection đến lúc commit/rollback. Muốn giảm Active, thường cần tối ưu SQL, rút ngắn transaction, kiểm tra index/lock và đặt ranh giới giao dịch hợp lý.

### 10.2. Không tự sửa connection leak

Dùng JDBC thuần mà không close connection/statement/result set đúng cách vẫn có thể gây leak. Với JDBC thuần, dùng try-with-resources; với Spring, dùng JdbcTemplate/DataSourceUtils hoặc transaction manager. Không tự đóng connection đang được Spring transaction quản lý chỉ vì nghĩ cần “trả pool sớm”.

### 10.3. Không đảm bảo mọi framework đều lười lấy connection

JPA/Hibernate có cơ chế riêng cho EntityManager, flush, cache và connection handling mode; migration, health check, metadata lookup hoặc code driver-specific có thể tạo Statement sớm. @Transactional không phải bằng chứng rằng lazy chắc chắn hoạt động tương tự trong mọi stack.

### 10.4. Không thay thế giới hạn pool và timeout

maximumPoolSize/connectionTimeout của HikariCP vẫn quyết định khả năng cấp connection vật lý. Khi đã đến mốc tạo Statement, ứng dụng có thể chờ mượn và timeout như bình thường. Lazy không tự tăng công suất database, không biến JDBC thành truy cập không đồng bộ và không đặt query timeout.

### 10.5. Sai bean identity hoặc thứ tự proxy làm transaction khác mong muốn

Nếu manager quản lý raw Hikari DataSource còn DAO dùng một proxy khác, Spring có thể không chia sẻ một thread-bound connection như dự kiến. Nếu dùng TransactionAwareDataSourceProxy, phải đặt ngoài LazyConnectionDataSourceProxy. Kiểm tra @Primary, @Qualifier, tên bean, @Transactional propagation và connection thực qua instrument.

### 10.6. “Read-only thì luôn vào replica” là giả định nguy hiểm

Cấu hình routing dựa trên TransactionSynchronizationManager chỉ hoạt động khi read-only flag đã có đúng thời điểm chọn pool. Replica có thể trễ sao chép; một read ngay sau write cần thiết kế consistency. Quyền ghi phải được thực thi ở database và tầng nghiệp vụ, không dựa duy nhất vào @Transactional(readOnly = true).

### Bảng chẩn đoán nhanh

| Triệu chứng | Khả năng nguyên nhân | Nên kiểm tra |
| --- | --- | --- |
| Transaction rỗng vẫn mượn connection | Khởi tạo default auto-commit/isolation; metadata; SQL từ transaction manager | Trace lần đầu và mốc tạo Statement |
| Tạo PreparedStatement đã làm Hikari Active tăng | Hành vi **đúng** của lazy proxy | Phân biệt prepare với execute |
| Bật lazy nhưng không giảm Active | Phần lớn request vẫn truy cập DB; transaction giữ connection lâu | Tỉ lệ empty transaction và usage time |
| @Transactional không có hiệu lực | Self-invocation, sai bean, sai proxy hoặc manager | Đường gọi Spring bean và cấu hình transaction |
| Read-only routing sang sai pool | Chọn route trước khi flag có hiệu lực; sai thứ tự proxy | Log routing key ngay tại target borrow |
| Ứng dụng báo timeout khi prepareStatement | Pool chưa cấp được connection lúc proxy cần target | Hikari Pending, acquisition latency, DB constraints |
| Đếm lần getConnection đầu = 1 dù chưa SQL | Lazy đọc default properties | Khởi tạo riêng và đo lại, không khai default sai |
| DAO và transaction manager dùng các connection khác nhau | Hai DataSource bean/proxy identity khác nhau | Wiring @Qualifier/@Primary và DataSourceUtils |

## 11. Bài tập tự kiểm tra

**Bài 1.** Với lazy proxy đã biết giá trị mặc định, ứng dụng getConnection(), setReadOnly(true), close() mà không tạo Statement. Có bắt buộc pool cấp connection không?

**Đáp án:** Không; handle logic có thể được tạo và đóng mà không cần target connection.

**Bài 2.** Ứng dụng gọi prepareStatement("SELECT 1") rồi không bao giờ executeQuery(). Có thể đã mượn pool connection chưa?

**Đáp án:** Đã có thể mượn ngay tại prepareStatement(); “không execute” không có nghĩa “không tạo Statement”.

**Bài 3.** Một service @Transactional truy cập bộ nhớ cache và trả kết quả. Transaction có thể kết thúc mà không mượn connection thật không?

**Đáp án:** Có, khi dùng lazy proxy đúng chỗ, không tạo Statement hay hoạt động khác buộc lấy target, và không tính lượt khởi tạo thuộc tính mặc định. Đây là lý do chính để dùng proxy.

**Bài 4.** Transaction manager dùng HikariDataSource trực tiếp, JdbcTemplate dùng LazyConnectionDataSourceProxy bọc Hikari đó. Có nên giả định transaction và DAO chắc chắn chia sẻ một JDBC connection?

**Đáp án:** Không. Cần wiring đúng resource identity, thường cho manager và JdbcTemplate dùng **cùng lazy DataSource bean**.

**Bài 5.** Hikari Active vẫn cao sau khi một truy vấn ngắn chạy xong, nhưng method @Transactional còn gọi HTTP 4 giây. Lazy có tự trả connection sau truy vấn đầu không?

**Đáp án:** Không. Connection đã mượn có thể bị giữ tới cuối transaction. Nên xem lại ranh giới transaction, tránh bao công việc không liên quan đến DB.

**Bài 6.** Có thể bật spring.datasource.connection-fetch=lazy trên Boot 3.3 và tin rằng proxy đã tự hoạt động?

**Đáp án:** Không. Thuộc tính được giới thiệu trong Boot 4.1; với Boot 3.x hãy dùng cấu hình bean tương ứng và kiểm tra runtime.

**Bài 7.** Muốn đo lazy, gọi ConnectionProxy.getTargetConnection() ngay sau getConnection() có phù hợp không?

**Đáp án:** Không phù hợp nếu mục tiêu là đo nhánh không mượn connection: thao tác lấy native target có thể tự buộc proxy mượn. Hãy instrument DataSource đích thay vì ép lấy connection thật.

**Bài 8.** LazyConnectionDataSourceProxy được đặt trước AbstractRoutingDataSource có ích gì?

**Đáp án:** Cho phép trì hoãn chọn target pool đến khi transaction metadata như readOnly/isolation đã có, giúp router có thêm thông tin đúng lúc tạo Statement; vẫn phải kiểm tra consistency, propagation và cơ chế routing thực tế.

## 12. Những điều cần nhớ

- **getConnection() của lazy proxy** trả Connection logic; **createStatement()/prepareStatement()/prepareCall()** thường là mốc mượn connection thật.
- **Bắt đầu @Transactional** khác với **mượn pooled connection**; transaction rỗng có thể kết thúc mà không sử dụng DB.
- **Lần đầu dò default auto-commit/isolation**, thao tác metadata/native hoặc SQL khởi tạo giao dịch có thể khiến connection được mượn sớm.
- **JdbcTemplate và transaction manager** nên tham chiếu cùng DataSource lazy; nếu dùng TransactionAwareDataSourceProxy thì đặt nó ngoài cùng.
- **Read-only routing** có thể hưởng lợi từ lazy nhưng không tự giải quyết phân quyền hoặc độ nhất quán replica.
- **Lazy không tối ưu truy vấn** và không thay thế Hikari pool/transaction management; khi đã có SQL, connection vẫn có thể được giữ tới cuối transaction.
- **Spring Boot 4.1+** có cấu hình connection-fetch=lazy khi auto-configure pooled DataSource; ứng dụng Boot 3.x cần wiring phù hợp với phiên bản.

### Tài liệu chính thức để đối chiếu

- Spring Framework 6.1.2, LazyConnectionDataSourceProxy Javadoc: https://docs.spring.io/spring-framework/docs/6.1.2/javadoc-api/org/springframework/jdbc/datasource/LazyConnectionDataSourceProxy.html
- Spring Framework, Controlling Database Connections: https://docs.spring.io/spring-framework/reference/data-access/jdbc/connections.html
- Spring Framework, Synchronizing Resources with Transactions: https://docs.spring.io/spring-framework/reference/data-access/transaction/tx-resource-synchronization.html
- Spring Boot 3.5, SQL Databases: https://docs.spring.io/spring-boot/3.5/reference/data/sql.html
- Spring Boot 4.1, SQL Databases / Lazy Connection Proxy: https://docs.spring.io/spring-boot/4.1-SNAPSHOT/reference/data/sql.html
