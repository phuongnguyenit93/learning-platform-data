# Quan sát log begin, commit, rollback và giải phóng kết nối trong Spring

Một phương thức được gắn **@Transactional** chạy không báo lỗi chưa đủ chứng minh dữ liệu đã commit đúng. Khi học giao dịch đầu tiên với Spring, chúng ta cần nhìn thấy **một transaction được tạo hoặc tham gia khi nào, kết thúc bằng commit hay rollback, và JDBC Connection được trả về đâu**. Kết hợp log của Spring với việc đọc lại dữ liệu từ database sẽ giúp phân biệt hoạt động của transaction manager, JDBC driver, DBMS và connection pool.

Mục tiêu của bài:

- Bật đúng logger để thấy vòng đời giao dịch JDBC trong Spring.
- Đọc được dấu hiệu của **begin → thực thi SQL → commit/rollback → cleanup/release** mà không nhầm log thông báo với kết quả bền vững của DB.
- Chạy hai kịch bản thành công và lỗi chủ động với Java 17+, Spring JDBC, H2 và connection pool.
- Hiểu tại sao **release connection không nhất thiết là đóng kết nối vật lý**, cách nhận biết leak hoặc transaction kéo dài.
- Xử lý các trường hợp thường gây hiểu nhầm: method không đi qua proxy, transaction tham gia transaction ngoài, exception bị bắt, checked exception, connection ngoài phạm vi Spring.

Phạm vi chính là **giao dịch JDBC imperative** do JdbcTransactionManager/DataSourceTransactionManager điều phối. Khi dùng JPA/JTA hoặc R2DBC, ý nghĩa các pha tương tự nhưng logger và tài nguyên cụ thể có thể khác.

## 1. Điều gì thực sự diễn ra sau lời gọi @Transactional?

Ví dụ service chuyển 10 đơn vị từ A sang B. Nếu hai UPDATE cùng thuộc một transaction JDBC, hệ thống mong đợi:

- Không có lỗi: DBMS chấp nhận **cả hai** thay đổi tại commit.
- Có lỗi làm rollback: DBMS hủy **cả hai** thay đổi chưa commit.
- Dù commit hay rollback, Spring **dọn transaction context và giải phóng tài nguyên đã mượn**.

Đường đi thông dụng:

~~~mermaid
sequenceDiagram
    actor Caller
    participant Proxy as Spring TransactionInterceptor
    participant TM as JdbcTransactionManager
    participant Pool as DataSource / Connection Pool
    participant DB as JDBC Driver / DBMS
    Caller->>Proxy: Gọi service method
    Proxy->>TM: getTransaction(definition)
    TM->>Pool: Lấy JDBC Connection
    Pool-->>TM: Connection
    TM->>TM: Gắn Connection vào transaction context
    TM->>DB: Cấu hình Connection (thường autoCommit=false)
    Proxy->>DB: Thực thi SQL qua JdbcTemplate
    alt Thành công
        Proxy->>TM: commit
        TM->>DB: Connection.commit()
    else Lỗi cần rollback
        Proxy->>TM: rollback
        TM->>DB: Connection.rollback()
    end
    TM->>TM: Khôi phục và hủy ràng buộc transaction
    TM->>Pool: release Connection
    Pool-->>TM: Trở về pool hoặc đóng tùy DataSource
    Proxy-->>Caller: Kết quả / ngoại lệ
~~~

Sơ đồ mô tả **logic của một transaction JDBC local mới mở**. Nó không khẳng định driver nào cũng gửi lệnh SQL BEGIN tường minh. Với nhiều JDBC driver/DBMS, Spring chuyển connection sang **autoCommit=false**, DBMS bắt đầu transaction thực tế theo quy tắc của nó khi thao tác được thực hiện.

Đặc biệt, **@Transactional không trực tiếp điều khiển JDBC Connection**. TransactionInterceptor nhờ TransactionManager; manager phối hợp với DataSource; JDBC driver nói chuyện với DBMS. Nếu phương thức chỉ tham gia một transaction đang tồn tại (PROPAGATION_REQUIRED), phương thức đó thường **không tạo hoặc kết thúc một transaction vật lý mới**.

## 2. Bật log đúng chỗ

Spring không nhất thiết hiển thị transaction ở INFO. Với Spring Boot sử dụng JDBC, bắt đầu bằng mức DEBUG cho các package hẹp, tăng TRACE tại interceptor khi thật sự cần theo dõi lời gọi.

**application.yml** trong ứng dụng Spring Boot:

~~~yaml
logging:
  level:
    org.springframework.transaction.interceptor: TRACE
    org.springframework.jdbc.support: DEBUG
    org.springframework.jdbc.datasource: DEBUG
    com.zaxxer.hikari: INFO
~~~

Cách tương đương với **application.properties**:

~~~properties
logging.level.org.springframework.transaction.interceptor=TRACE
logging.level.org.springframework.jdbc.support=DEBUG
logging.level.org.springframework.jdbc.datasource=DEBUG
logging.level.com.zaxxer.hikari=INFO
~~~

Không cần cấu hình cả hai file; chọn loại file cấu hình của ứng dụng. Với **DataSourceTransactionManager**, logger thường nằm trong package **org.springframework.jdbc.datasource**; với **JdbcTransactionManager**, logger của subclass nằm trong **org.springframework.jdbc.support**. Bật cả hai giúp theo dõi khi chưa biết manager thực tế. **org.springframework.transaction.interceptor** cho biết advice transaction quanh lời gọi phương thức.

Nếu sử dụng **JpaTransactionManager**, cần bật thêm **org.springframework.orm.jpa** ở DEBUG; với Hibernate có thể bổ sung log SQL/flush theo nhu cầu. Với R2DBC, dùng logger tương ứng của Spring R2DBC và driver, không kỳ vọng câu chữ JDBC như dưới đây. Log JDBC cũng không bảo đảm mọi statement đều được in: logger của transaction manager chủ yếu ghi **vòng đời transaction**, không phải mọi câu SQL hay giá trị bind.

Khi dùng một Java application không có Spring Boot, chỉ riêng setting trong application.yml sẽ không tự được đọc. Ví dụ chạy độc lập ở phần 5 cấu hình **SLF4J SimpleLogger bằng Java system properties** để không cần Boot.

**Cân nhắc trong môi trường thật:** DEBUG/TRACE nhiều traffic tạo log lớn. Chỉ bật tạm thời ở môi trường được phép; hạn chế ghi giá trị tham số SQL, thông tin định danh, token và dữ liệu nhạy cảm. Nếu dùng Logback, Log4j2 hoặc hệ ghi log khác, cấu hình tương ứng thay cho SimpleLogger.

## 3. Bảng đọc log: mỗi dòng chứng minh điều gì?

| Dấu hiệu log thường gặp | Thành phần | Ý nghĩa chính | Không được kết luận chỉ từ dòng đó |
| --- | --- | --- | --- |
| **Creating new transaction with name [...]** | TransactionManager | Spring quyết định mở một transaction mới | DBMS đã ghi BEGIN SQL hay đã commit |
| **Acquired Connection [...] for JDBC transaction** | DataSourceTransactionManager/JdbcTransactionManager | Có một JDBC Connection được lấy cho giao dịch | Đây là socket vật lý mới được tạo |
| **Switching JDBC Connection [...] to manual commit** | JDBC transaction manager | Manager yêu cầu tắt autocommit | DBMS đã bắt đầu thực thi câu SQL |
| **Getting transaction for [...]** | TransactionInterceptor ở TRACE | Advice đang quản lý lời gọi được intercept | Tài nguyên chưa chắc được cấp mới nếu transaction đã có |
| **Participating in existing transaction** | TransactionManager | Lời gọi tham gia transaction hiện tại | Phương thức trong sẽ tự commit khi trả về |
| **Initiating transaction commit** | TransactionManager | Spring bước vào tiến trình commit | Commit đã chắc chắn thành công |
| **Committing JDBC transaction on Connection [...]** | JDBC transaction manager | Spring sắp gọi hoặc đang gọi Connection.commit() | DBMS đã xác nhận thành công nếu log kế tiếp có lỗi |
| **Initiating transaction rollback** | TransactionManager | Spring bắt đầu nhánh rollback | Mọi side effect ngoài DB đã được hủy |
| **Rolling back JDBC transaction on Connection [...]** | JDBC transaction manager | Spring yêu cầu Connection.rollback() | Dữ liệu nằm trên connection khác cũng được rollback |
| **Releasing JDBC Connection [...] after transaction** | JDBC transaction manager | Cleanup đang giải phóng connection do manager nắm | Kết nối vật lý đã bị đóng |
| **Returning JDBC Connection to DataSource** | DataSourceUtils, tùy cấu hình log | Spring hoàn tất bước bàn giao connection | Pool đã giảm số connection vật lý |
| **HikariPool ... Shutdown completed** | HikariCP | Toàn pool đang đóng/đã đóng | Đây là log xuất hiện sau mọi transaction bình thường |

Câu chữ, category và mức log có thể thay đổi theo **phiên bản Spring, transaction manager, logging framework và DataSource**. Các dấu hiệu ở bảng là mẫu để nhận diện, không phải yêu cầu mọi lần chạy phải in đủ từng dòng. Với tên method, connection ID, thread, thời gian hoặc thứ tự các dòng từ nhiều logger khác nhau, hãy đối chiếu theo thực tế.

**Điểm dễ nhầm nhất:** chữ **begin** trong câu hỏi nghiệp vụ không đồng nghĩa phải nhìn thấy văn bản nguyên xi **BEGIN TRANSACTION**. Trong local JDBC transaction, dấu hiệu có giá trị thường là **Creating new transaction**, **Acquired Connection** và **Switching ... to manual commit**.

## 4. Tách pha điều khiển transaction khỏi việc thực thi SQL

### Pha 1: Mở transaction

Với một JDBC transaction mới, Spring nhận metadata của @Transactional, chọn transaction manager, lấy connection từ DataSource, chuẩn bị isolation/read-only nếu cần, chuyển autoCommit khi thích hợp và gắn tài nguyên vào context của thread hiện tại.

- Manager có thể không gọi setAutoCommit(false) nếu connection đã có autoCommit=false.
- **LazyConnectionDataSourceProxy** có thể hoãn lấy connection vật lý cho tới SQL đầu tiên; transaction không chạy SQL có thể không cần mượn connection thật.
- Transaction được tạo bởi transaction manager không nhất thiết tương ứng với một câu BEGIN SQL hiển thị trong SQL log.

### Pha 2: Chạy mã nghiệp vụ và SQL

JdbcTemplate sử dụng cơ chế **DataSourceUtils** để lấy đúng connection đã liên kết với transaction. Nhiều thao tác JDBC trong cùng transaction sử dụng cùng tài nguyên thích hợp. Nếu tự gọi DriverManager.getConnection(...) hoặc sử dụng một DataSource khác, kết nối riêng có thể không tham gia transaction của service.

### Pha 3A: Commit

Khi method kết thúc bình thường mà không bị đánh dấu rollback-only, advice yêu cầu manager commit tại ranh giới sở hữu transaction. Manager gọi **Connection.commit()**, driver gửi yêu cầu tới DBMS; DBMS quyết định tính hợp lệ, ghi nhận thay đổi và phản hồi. Vì lỗi có thể xảy ra trong lúc commit, **log “Initiating transaction commit” không tự chứng minh commit thành công**.

### Pha 3B: Rollback

Khi ngoại lệ phù hợp rollback rule thoát khỏi ranh giới, hoặc transaction đã rollback-only, advice yêu cầu rollback. Manager gọi **Connection.rollback()**, DBMS hủy thay đổi chưa commit thuộc transaction đó. Giao dịch khác hoặc một HTTP request/email đã gửi bên ngoài không tự rollback theo.

### Pha 4: Cleanup và release

Sau khi kết thúc, manager khôi phục các trạng thái connection mà nó đã đổi khi cần, tháo ràng buộc từ thread, hoàn tất transaction synchronization và giải phóng connection. Với pool như HikariCP, **close() trên wrapper** thường có nghĩa là **trả connection logic về pool**, nơi connection vật lý có thể tiếp tục được tái sử dụng.

**Release sau commit và release sau rollback đều bình thường.** Không được phân loại một giao dịch thành công hay thất bại chỉ từ dòng release. Xem các dòng commit/rollback trước đó và đọc lại trạng thái DB.

## 5. Chạy một ứng dụng Java 17+ quan sát cả commit và rollback

Ví dụ sau dùng **Spring Framework 6.2.12, H2 2.3.232, HikariCP 5.1.0 và SLF4J Simple 2.0.17**. Nó tạo một Spring application context thật, bật proxy transaction, gọi service qua bean Spring, chạy một giao dịch thành công và một giao dịch cố ý ném RuntimeException. Dữ liệu được kiểm tra sau mỗi trường hợp.

**Cấu trúc:**

~~~text
tx-log-demo/
├── pom.xml
└── src/main/java/demo/TxLogDemo.java
~~~

**pom.xml:**

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>tx-log-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.12</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-jdbc</artifactId>
            <version>6.2.12</version>
        </dependency>
        <dependency>
            <groupId>com.zaxxer</groupId>
            <artifactId>HikariCP</artifactId>
            <version>5.1.0</version>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <version>2.3.232</version>
        </dependency>
        <dependency>
            <groupId>org.slf4j</groupId>
            <artifactId>slf4j-simple</artifactId>
            <version>2.0.17</version>
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
                <version>3.5.1</version>
                <configuration>
                    <mainClass>demo.TxLogDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**src/main/java/demo/TxLogDemo.java:**

~~~java
package demo;

import com.zaxxer.hikari.HikariConfig;
import com.zaxxer.hikari.HikariDataSource;
import javax.sql.DataSource;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.support.JdbcTransactionManager;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.annotation.EnableTransactionManagement;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionSynchronizationManager;

public final class TxLogDemo {
    private TxLogDemo() {}

    public static void main(String[] args) {
        // Phải đặt trước khi các logger của ứng dụng được khởi tạo.
        System.setProperty("org.slf4j.simpleLogger.defaultLogLevel", "warn");
        System.setProperty("org.slf4j.simpleLogger.showDateTime", "false");
        System.setProperty("org.slf4j.simpleLogger.showThreadName", "true");
        System.setProperty(
                "org.slf4j.simpleLogger.log.org.springframework.jdbc.support",
                "debug");
        System.setProperty(
                "org.slf4j.simpleLogger.log.org.springframework.jdbc.datasource",
                "debug");
        System.setProperty(
                "org.slf4j.simpleLogger.log.org.springframework.transaction.interceptor",
                "trace");

        try (var context = new AnnotationConfigApplicationContext(Config.class)) {
            JdbcTemplate jdbc = context.getBean(JdbcTemplate.class);
            DataSource dataSource = context.getBean(DataSource.class);
            TransferService service = context.getBean(TransferService.class);

            jdbc.execute("CREATE TABLE account (" +
                    "id INT PRIMARY KEY, balance INT NOT NULL CHECK (balance >= 0))");
            jdbc.update("INSERT INTO account(id, balance) VALUES (?, ?)", 1, 100);
            jdbc.update("INSERT INTO account(id, balance) VALUES (?, ?)", 2, 100);
            printBalances(jdbc, "INITIAL");

            System.out.println("=== COMMIT ===");
            service.successfulTransfer(); // Lời gọi qua Spring proxy
            printBalances(jdbc, "AFTER COMMIT");
            System.out.println("after commit: resourceBound=" +
                    TransactionSynchronizationManager.hasResource(dataSource));

            System.out.println("=== ROLLBACK ===");
            try {
                service.failedTransfer();  // Lời gọi qua Spring proxy
            } catch (IllegalStateException ex) {
                System.out.println("caught: " + ex.getMessage());
            }
            printBalances(jdbc, "AFTER ROLLBACK");
            System.out.println("after rollback: resourceBound=" +
                    TransactionSynchronizationManager.hasResource(dataSource));
        }
        // context.close() đóng HikariDataSource/pool ở cuối chương trình.
    }

    private static void printBalances(JdbcTemplate jdbc, String label) {
        Integer a = jdbc.queryForObject(
                "SELECT balance FROM account WHERE id = ?", Integer.class, 1);
        Integer b = jdbc.queryForObject(
                "SELECT balance FROM account WHERE id = ?", Integer.class, 2);
        System.out.printf("%s: A=%d, B=%d%n", label, a, b);
    }

    @Configuration(proxyBeanMethods = false)
    @EnableTransactionManagement(proxyTargetClass = true)
    public static class Config {
        @Bean(destroyMethod = "close")
        public HikariDataSource dataSource() {
            HikariConfig config = new HikariConfig();
            config.setJdbcUrl("jdbc:h2:mem:tx_log_demo;DB_CLOSE_DELAY=-1");
            config.setUsername("sa");
            config.setPassword("");
            config.setPoolName("tx-log-pool");
            config.setMinimumIdle(1);
            config.setMaximumPoolSize(3);
            return new HikariDataSource(config);
        }

        @Bean
        public JdbcTemplate jdbcTemplate(DataSource dataSource) {
            return new JdbcTemplate(dataSource);
        }

        @Bean
        public PlatformTransactionManager transactionManager(DataSource dataSource) {
            return new JdbcTransactionManager(dataSource);
        }

        @Bean
        public TransferService transferService(JdbcTemplate jdbcTemplate) {
            return new TransferService(jdbcTemplate);
        }
    }

    public static class TransferService {
        private final JdbcTemplate jdbc;

        public TransferService(JdbcTemplate jdbc) {
            this.jdbc = jdbc;
        }

        @Transactional
        public void successfulTransfer() {
            System.out.println("inside commit: active=" +
                    TransactionSynchronizationManager.isActualTransactionActive());
            jdbc.update(
                    "UPDATE account SET balance = balance - 10 WHERE id = 1");
            jdbc.update(
                    "UPDATE account SET balance = balance + 10 WHERE id = 2");
        }

        @Transactional
        public void failedTransfer() {
            System.out.println("inside rollback: active=" +
                    TransactionSynchronizationManager.isActualTransactionActive());
            jdbc.update(
                    "UPDATE account SET balance = balance - 20 WHERE id = 1");
            jdbc.update(
                    "UPDATE account SET balance = balance + 20 WHERE id = 2");
            throw new IllegalStateException("simulated error");
        }
    }
}
~~~

**Điểm cần kiểm chứng trong mã:**

1. **@EnableTransactionManagement(proxyTargetClass = true)** kích hoạt interceptor và ép proxy lớp, giúp lời gọi lấy bean TransferService theo class type được chặn. TransferService có phương thức public, không phải final.
2. **transactionManager** là bean JdbcTransactionManager sử dụng **đúng HikariDataSource** mà JdbcTemplate dùng.
3. **@Transactional** trên hai phương thức chạy qua Spring proxy, không gọi this.method() nội bộ.
4. **TransactionSynchronizationManager.isActualTransactionActive()** quan sát context bên trong phương thức.
5. **TransactionSynchronizationManager.hasResource(dataSource)** quan sát tài nguyên còn gắn với thread hay không **sau khi** phương thức transaction kết thúc. Giá trị false không có nghĩa pool đã đóng.
6. **IllegalStateException** là RuntimeException: mặc định Spring yêu cầu rollback khi exception này thoát khỏi phương thức transactional.
7. Cả hai UPDATE dùng cùng transaction-bound resource. H2 thực hiện commit/rollback; Spring chỉ điều phối thời điểm gọi qua driver.

**Chạy thử** trên máy có JDK 17+ và Maven:

~~~bash
cd tx-log-demo
mvn -q compile exec:java
~~~

**Các dòng do System.out.println/printf của chương trình chủ động tạo ra** (không tính DEBUG/TRACE phát qua logger hoặc output riêng của Maven):

~~~text
INITIAL: A=100, B=100
=== COMMIT ===
inside commit: active=true
AFTER COMMIT: A=90, B=110
after commit: resourceBound=false
=== ROLLBACK ===
inside rollback: active=true
caught: simulated error
AFTER ROLLBACK: A=90, B=110
after rollback: resourceBound=false
~~~

SLF4J SimpleLogger mặc định có thể in DEBUG/TRACE ra **stderr**, vì vậy terminal hiển thị xen kẽ với stdout. Không dùng vị trí xen kẽ giữa hai stream làm bằng chứng thứ tự tuyệt đối; hãy đọc **tên logger, tên thread và các mốc transaction**.

Lưu ý: bộ dependency và ví dụ theo Java 17+/Spring 6.2; với dự án đang có Spring Boot, ưu tiên các phiên bản phụ thuộc được BOM của Boot quản lý thay vì sao chép cứng version từ ví dụ.

## 6. Diễn giải log thực tế theo từng pha

Phần dưới trình bày **mẫu dòng DEBUG/TRACE có thể quan sát**, lược bỏ timestamp, tên thread, hash/ID connection và những dòng không quyết định ý nghĩa. Nội dung cụ thể của log phụ thuộc phiên bản và cách cấu hình.

### 6.1. Trường hợp commit

~~~text
Creating new transaction with name [demo.TxLogDemo$TransferService.successfulTransfer]
Acquired Connection [...] for JDBC transaction
Switching JDBC Connection [...] to manual commit
Getting transaction for [demo.TxLogDemo$TransferService.successfulTransfer]
... application executes UPDATE A and UPDATE B ...
Completing transaction for [demo.TxLogDemo$TransferService.successfulTransfer]
Initiating transaction commit
Committing JDBC transaction on Connection [...]
Releasing JDBC Connection [...] after transaction
~~~

**Cách đọc:**

- **Creating new transaction:** Spring đang mở một transaction vật lý local vì service là entrypoint giao dịch.
- **Acquired Connection:** manager đã mượn một JDBC Connection từ HikariDataSource.
- **manual commit:** Spring chuyển sang điều khiển commit theo ranh giới thay vì autocommit từng statement. Đây là **cơ chế phổ biến**, không phải chứng cứ đã gửi SQL BEGIN.
- **Getting transaction / Completing transaction:** dấu vết intercept một method. Các dòng này không thay thế log DBMS.
- **Initiating commit / Committing JDBC transaction:** Spring yêu cầu driver thực hiện commit. Nếu commit báo lỗi, cần điều tra trạng thái DB thực tế, không khẳng định đã thành công từ dòng “Initiating”.
- **Releasing JDBC Connection:** Spring giải phóng connection do nó mượn. HikariCP có thể giữ **kết nối vật lý** để phục vụ request tiếp theo.

Kết quả nghiệp vụ **AFTER COMMIT: A=90, B=110** được đọc lại từ JdbcTemplate sau khi method hoàn tất; đây là bằng chứng hữu ích hơn việc chỉ có chữ “commit” trong log.

### 6.2. Trường hợp rollback

~~~text
Creating new transaction with name [demo.TxLogDemo$TransferService.failedTransfer]
Acquired Connection [...] for JDBC transaction
Switching JDBC Connection [...] to manual commit
Getting transaction for [demo.TxLogDemo$TransferService.failedTransfer]
... application executes UPDATE A and UPDATE B ...
Completing transaction for [...] after exception: java.lang.IllegalStateException
Initiating transaction rollback
Rolling back JDBC transaction on Connection [...]
Releasing JDBC Connection [...] after transaction
~~~

Phương thức failedTransfer() đã chạy cả hai UPDATE rồi ném RuntimeException. Proxy thấy ngoại lệ thoát khỏi method, quyết định rollback theo quy tắc mặc định. H2 hủy hai cập nhật chưa commit; kết quả **AFTER ROLLBACK: A=90, B=110** bằng trạng thái trước phương thức failedTransfer().

**Không suy luận “thành công” chỉ vì đã nhìn thấy hai UPDATE**. Hai lệnh có thể đã thực thi thành công trong transaction nhưng sau đó bị rollback.

### 6.3. Vì sao có thể thấy “begin” mà không có rollback/commit ngay?

Nếu propagation **REQUIRED** tham gia transaction đã tồn tại, log có thể là **Participating in existing transaction**. Method con hoàn tất thì logical scope con kết thúc, nhưng **transaction vật lý** chỉ commit/rollback ở ranh giới method ngoài. Đếm số lời gọi @Transactional rồi so với số COMMIT vật lý thường cho kết quả khác nhau.

Nếu dùng **REQUIRES_NEW**, manager tạm suspend transaction ngoài và mở transaction mới; log thể hiện một nhánh commit/rollback độc lập và sau đó resume tài nguyên ngoài. Nếu dùng **NESTED** qua savepoint được hỗ trợ, log và hành vi có thể khác REQUIRES_NEW: rollback một nhánh về savepoint vẫn thuộc transaction vật lý bên ngoài.

## 7. Release JDBC Connection có nghĩa gì?

Đây là nội dung cốt lõi của việc đọc log kết thúc transaction.

| Sự kiện | Ý nghĩa |
| --- | --- |
| Spring **unbind** resource | ConnectionHolder không còn gắn với thread/context transaction hiện tại |
| Spring **reset** connection state | Khôi phục trạng thái đã thay đổi khi mở transaction, như autocommit, isolation, read-only khi phù hợp |
| Spring gọi **DataSourceUtils.releaseConnection** | Bàn giao connection do manager đã lấy |
| Hikari proxy connection **close()** | Trả lease logic về pool; không nhất thiết đóng socket/physical connection |
| Pool chủ động đóng connection vật lý | Xảy ra khi connection hết vòng đời, hỏng, bị evict hoặc pool shutdown theo chính sách |
| DBMS đóng session | Sự kiện ở tầng server, không thể suy ra chỉ từ thông báo release của Spring |

Trong ví dụ, bên trong method log **active=true**, sau method **resourceBound=false**. Kết quả cho thấy transaction context đã dọn sạch khỏi thread. Nó **không chứng minh Hikari pool đã bị shutdown**; thực tế pool vẫn tồn tại đến khi đóng application context.

HikariCP có thể cung cấp các chỉ số quan sát **active connections**, **idle connections**, **pending threads** và **total connections**. Trong ứng dụng Spring Boot có Micrometer/Actuator, các metric tương ứng giúp phân biệt “connection đang được mượn” với “connection vẫn còn mở trong pool”. Số idle > 0 sau khi release thường hoàn toàn bình thường.

**Không nên tự gọi connection.close() bên trong phương thức @Transactional** khi connection đang được Spring quản lý; hãy dùng JdbcTemplate hoặc DataSourceUtils đúng cách. Nếu tự mở DriverManager connection, người viết mã phải tự quản lý và đóng connection đó; nó không tự tham gia transaction của Spring.

### Ranh giới connection vật lý

Một JDBC Connection logic có thể được pool bọc bằng proxy. Chuỗi biểu diễn trong log như HikariProxyConnection@... có thể thay đổi giữa các lần mượn, và **không phải định danh giao dịch kinh doanh bền vững**. Để ghép log thành một yêu cầu, sử dụng trace ID/correlation ID và tên transaction thích hợp; không lấy hash object làm transaction ID trong thiết kế hệ thống.

### Khi release chưa có nghĩa transaction kết thúc sạch

Nếu Connection.commit() hoặc rollback() ném SQLException, Spring vẫn có nhánh cleanup cố gắng giải phóng tài nguyên. Do vậy có thể thấy log release **sau khi đã xuất hiện lỗi commit**. Người phân tích phải xem ngoại lệ gốc và dữ liệu DB, không tự hiểu release như xác nhận commit.

Nếu log cho thấy connection active hoặc pending tăng kéo dài, chưa chắc là leak: có thể transaction dài, SQL chờ lock, pool quá nhỏ hoặc application giữ connection ngoài transaction. Kết hợp thời gian giao dịch, thread dump, DB locks và pool metrics để phân biệt.

## 8. Đọc đúng nguồn log trong ứng dụng thật

### Transaction manager logs

Spring TransactionManager thích hợp để tìm begin, commit, rollback và release. Kiểm tra **manager thật sự** mà bean đang dùng:

- **JdbcTransactionManager / DataSourceTransactionManager**: các mẫu JDBC ở bài này.
- **JpaTransactionManager**: có thể xuất hiện log mở/đóng EntityManager, bắt đầu JPA transaction, flush, commit/rollback; không ép nó phải có chữ “Switching JDBC Connection”.
- **JtaTransactionManager**: trạng thái và commit qua JTA coordinator, có thể nhiều tài nguyên.
- **R2dbcTransactionManager**: transaction reactive dựa vào Reactor Context, connection R2DBC; không dùng mô hình ThreadLocal JDBC cho mọi reactive callback.

### TransactionInterceptor logs

TRACE của interceptor cho biết **phương thức nào đã được Spring intercept**. Nếu method tự gọi nội bộ trong cùng bean ở proxy mode, đôi khi sẽ không có log interceptor mới cho method đó. Đây là dấu hiệu cần kiểm tra **self-invocation** và proxy.

Nếu method không được gọi qua Spring bean, hoặc transaction management chưa được kích hoạt, không nên mong chờ log transaction chỉ vì mã nguồn có @Transactional.

### Connection pool logs

HikariCP ghi log về khởi tạo pool, shutdown, validation, timeout và một số thao tác pool tùy log level. Log **HikariPool - Shutdown** chỉ xuất hiện khi pool thật sự bị đóng hoặc ứng dụng kết thúc, không phải sau mỗi @Transactional thành công. Đừng bật Hikari DEBUG toàn bộ trong production chỉ để xác định transaction đã commit.

### Driver/DBMS logs

Một số hệ quản trị có transaction ID, backend PID, slow query log, statement log hoặc audit log riêng. Chúng giúp xác minh bên server, nhưng cần cấu hình DBA phù hợp. **SQL log chỉ cho biết câu lệnh được gửi/thực hiện; nó không tự cho biết kết quả commit sau cùng.**

## 9. Quan sát khi lỗi bị bắt hoặc rollback-only

Ví dụ một phương thức:

~~~java
// Snippet: nằm trong Spring-managed service đã cấu hình repository.
@Transactional
public void saveAndCatch() {
    try {
        repository.writeA();
        repository.writeBThatThrows();
    } catch (IllegalArgumentException ex) {
        applicationLogger.warn("Bị lỗi nhưng method vẫn trả về bình thường", ex);
    }
}
~~~

Nếu exception bị catch và method trả về bình thường, interceptor bên ngoài có thể **commit**, trừ khi transaction đã rollback-only bởi tài nguyên hoặc một scope transactional khác. Vì vậy việc đọc log phải đi cùng với việc kiểm tra **exception nào thực sự thoát qua transaction boundary**.

Spring @Transactional mặc định rollback với **RuntimeException** và **Error**; checked exception thông thường không tự rollback nếu không có rollbackFor hoặc chính sách tương ứng. Ví dụ:

~~~java
// Snippet: PaymentCheckedException là checked exception của ứng dụng.
@Transactional(rollbackFor = PaymentCheckedException.class)
public void saveWithCheckedFailure() throws PaymentCheckedException {
    repository.writeA();
    throw new PaymentCheckedException("rejected");
}
~~~

Đây là **đoạn mã minh họa, không phải chương trình độc lập**. Với cấu hình rollbackFor như trên, ngoại lệ checked thoát ra sẽ khiến Spring yêu cầu rollback.

Trong trường hợp inner REQUIRED đã đánh dấu rollback-only nhưng outer cố commit, Spring có thể ném **UnexpectedRollbackException**. Log trước đó có thể cho thấy một scope đánh dấu rollback-only, còn rollback vật lý xảy ra ở outer. Nếu chỉ nhìn phần cuối và bỏ qua bối cảnh nested transaction, sẽ khó hiểu nguyên nhân.

## 10. Tên transaction, thread và correlation để không nhầm request

Khi có nhiều request chạy đồng thời, các log transaction từ thread khác nhau có thể xen kẽ. Thêm những thông tin phù hợp trong log format:

- Timestamp với timezone và độ phân giải đủ để so thứ tự.
- Logger name, log level, thread name.
- Correlation/trace ID gắn từ đầu request, truyền qua các thành phần tương thích.
- Operation name hoặc service method; tránh nhúng trực tiếp email, số tài khoản hay dữ liệu nhạy cảm vào transaction name.

Một cách thực tế khi dùng Spring Boot + Micrometer Tracing là đưa **traceId/spanId** vào log pattern theo cấu hình logging hiện hành. Khi chưa dùng tracing, có thể dùng MDC để thêm correlation ID cho request, nhưng phải **dọn MDC khi request/worker thread kết thúc**, nếu không thông tin cũ có thể bị dùng lại.

Đối với @Async, task scheduler và Executor, transaction imperative theo thread **không tự truyền sang thread mới**. Thread name/correlation ID rất có ích để phát hiện lỗi tưởng rằng hai thao tác ở cùng transaction trong khi thực tế không.

## 11. Cách xác minh kết quả thay vì chỉ tin log

Một bài test giao dịch có giá trị cần kiểm chứng **trạng thái đã commit**:

1. Khởi tạo A=100, B=100 ở transaction đã hoàn thành.
2. Gọi service qua Spring bean proxy để thực thi thành công A-=10, B+=10.
3. Khi method trả về, đọc lại bằng một connection/transaction khác; kỳ vọng A=90, B=110.
4. Gọi nhánh lỗi cố ý cập nhật A-=20, B+=20 rồi ném RuntimeException.
5. Khi exception đã thoát khỏi proxy và rollback hoàn tất, đọc lại bằng connection/transaction độc lập; kỳ vọng vẫn A=90, B=110.
6. So thời điểm ghi log commit/rollback và release với những kết quả trên.

Trong ví dụ đơn giản, các truy vấn sau mỗi lời gọi được chạy **ngoài transaction service**, vì vậy có thể kiểm chứng trạng thái đã được chấp nhận sau khi transaction kết thúc. Với JPA, tránh chỉ đọc entity còn nằm trong persistence context cũ; dùng một context/transaction đọc độc lập để kiểm tra bền vững.

**Ghi chú về test:** nếu integration test được annotate @Transactional và test framework tự rollback ở cuối, các lệnh kiểm tra bên trong test có thể thấy dữ liệu chưa commit của chính nó. Muốn kiểm tra commit thật, cần tạo ranh giới test thích hợp hoặc dùng công cụ TestTransaction/REQUIRES_NEW theo mô hình được kiểm soát.

## 12. Troubleshooting: log thiếu hoặc trái kỳ vọng

| Triệu chứng | Khả năng cần điều tra | Hành động kiểm tra |
| --- | --- | --- |
| Không có Creating new transaction | Sai logger, method không qua proxy, manager khác, hoặc đang tham gia transaction có sẵn | Xác nhận @EnableTransactionManagement/Boot config, bean proxy, package logger, propagation |
| Có Getting transaction nhưng không thấy JDBC Connection | Dùng JPA/R2DBC/JTA, LazyConnectionDataSourceProxy, hoặc không có SQL | Xác định manager/DataSource thật và có phát sinh truy vấn hay không |
| Thấy COMMIT nhưng dữ liệu không như mong đợi | Truy vấn sai DB/schema, SQL không cập nhật dòng nào, transaction khác, đọc từ cache, race condition | Kiểm tra update count, datasource, readback ở connection độc lập và DB logs |
| Thấy ROLLBACK nhưng một thay đổi vẫn tồn tại | SQL chạy trên connection ngoài transaction, DB khác, thao tác đã commit trước đó | Kiểm tra JDBC Connection và manager đúng DataSource, tự mở connection, @Async |
| Có RELEASE nhưng pool vẫn còn nhiều connection | Pool tái sử dụng kết nối vật lý, không hẳn leak | Xem active/idle/pending, pool config và thời gian chờ |
| Pool timeout hoặc connection bị giữ lâu | Transaction dài, SQL chờ lock, thao tác mạng trong transaction, pool nhỏ | Đo độ dài transaction, DB lock, thread dump, pool metrics |
| Câu log commit xuất hiện trước exception | Lỗi xảy ra sau commit, afterCommit callback hoặc một thao tác khác | Xác định scope phát lỗi; kiểm tra dữ liệu DB và stack trace |
| Outer bị UnexpectedRollbackException | Inner REQUIRED đã đánh dấu rollback-only | Xem các log trước đó, propagation, exception bị catch |
| Không thấy UPDATE trong log transaction | Log transaction manager không phải SQL logger | Bật logger JDBC/ORM phù hợp và kiểm soát dữ liệu nhạy cảm |
| Cùng số connection xuất hiện trong hai transaction | Pool tái sử dụng connection vật lý | Phân biệt mỗi lần borrow/lease và transaction boundary |

**Chẩn đoán ưu tiên theo thứ tự:** (1) đúng method đi qua proxy, (2) đúng transaction manager và DataSource, (3) đúng propagation, (4) đúng log begin/commit/rollback, (5) đúng cleanup/release, (6) đúng trạng thái DB sau kết thúc, (7) pool metrics và DB server khi cần.

## 13. Tránh làm sai transaction khi chỉ muốn thêm quan sát

- Không gọi **Connection.commit()** hoặc **Connection.rollback()** thủ công trên connection đang được Spring quản lý để “thấy rõ” log; điều đó phá hợp đồng transaction của manager.
- Không giữ một transaction mở chỉ để theo dõi; SQL chờ lock hoặc gọi HTTP dài có thể giữ connection quá lâu.
- Không in nguyên câu SQL kèm thông tin nhạy cảm nếu không có quyền kiểm soát log.
- Không dùng thông báo RELEASE làm tín hiệu “business operation thành công”.
- Không bật DEBUG/TRACE toàn cục suốt thời gian dài; chỉ chọn logger, khoảng thời gian và môi trường phù hợp.
- Không suy luận mọi ứng dụng Spring đều dùng JdbcTransactionManager: xác nhận JPA, JTA, JDBC hay R2DBC trước khi đọc câu chữ.
- Không diễn giải **close logical connection = physical close** khi dùng pool.

## 14. Bài tập tự kiểm tra

**Bài tập A — Commit:** Sau lời gọi @Transactional thành công, bạn thấy “Initiating transaction commit” và “Releasing JDBC Connection”. Điều gì cần kiểm tra để khẳng định DB thật sự lưu dữ liệu?  
**Đáp án:** Xác minh không có lỗi commit/exception và đọc lại trạng thái bằng connection/transaction độc lập sau khi method kết thúc. Hai dòng log chỉ phản ánh bước điều phối và cleanup.

**Bài tập B — Rollback:** Service cập nhật hai bảng rồi ném RuntimeException, log có “Rolling back JDBC transaction”. Nhưng một hàng vẫn đổi. Tầng nào cần điều tra trước?  
**Đáp án:** Kiểm tra mọi thao tác có dùng cùng transaction manager/DataSource/transaction-bound connection hay không, có connection tự mở hoặc request ở thread khác không, rồi kiểm tra engine/DB và thời điểm commit trước đó.

**Bài tập C — Connection:** Log “Releasing JDBC Connection” xuất hiện sau commit, nhưng Hikari vẫn còn idle connection. Đây có phải connection leak?  
**Đáp án:** Không. Connection đã được trả về pool để tái sử dụng. Leak chỉ đáng nghi khi active/borrowed không được trả, pending tăng dai dẳng hoặc pool cảnh báo sau thời gian được cấu hình.

**Bài tập D — BEGIN:** Vì sao không thấy câu lệnh SQL BEGIN trong log nhưng @Transactional vẫn hoạt động?  
**Đáp án:** Một local JDBC transaction thường được điều khiển bằng Connection.setAutoCommit(false); DBMS/driver có thể không hiển thị BEGIN như câu SQL độc lập. Kiểm tra transaction manager log, hành vi connection và kết quả commit/rollback.

**Bài tập E — Nested scope:** Inner REQUIRED trả về bình thường nhưng outer mới commit. Tại sao không có COMMIT vật lý sau inner?  
**Đáp án:** Inner tham gia transaction hiện tại. Quyết định cuối cùng và commit thuộc về transaction owner bên ngoài.

**Bài tập F — Proxy:** Gọi this.inner() có @Transactional nhưng không thấy interceptor log cho inner. Có vấn đề gì?  
**Đáp án:** Self-invocation thường bỏ qua Spring AOP proxy trong proxy mode, nên metadata @Transactional của inner có thể không được áp dụng. Cần gọi qua một Spring bean/proxy khác hoặc thiết kế lại boundary.

## 15. Checklist quan sát một transaction đầu tiên

- [ ] Cấu hình đúng logger transaction manager và interceptor ở DEBUG/TRACE trong môi trường học.
- [ ] Xác nhận phương thức được gọi qua Spring-managed proxy hoặc một transaction template phù hợp.
- [ ] Xác nhận **Creating new transaction** hoặc **Participating in existing transaction** theo propagation.
- [ ] Với JDBC local, nhận diện connection được mượn và autocommit được điều khiển.
- [ ] Quan sát riêng nhánh thành công **commit** và nhánh lỗi **rollback**.
- [ ] Xác nhận **release connection** sau cả hai nhánh, hiểu logical vs physical connection.
- [ ] Đọc lại dữ liệu sau khi transaction kết thúc để kiểm tra trạng thái thực tế.
- [ ] Đối chiếu correlation ID, logger và thread nếu nhiều request chạy đồng thời.
- [ ] Tắt mức logging chi tiết không cần thiết khi kết thúc buổi debug.

**Ghi nhớ:** Spring log cho biết *ai đang điều phối transaction và ở pha nào*. Kết quả ở DBMS mới chứng minh dữ liệu cuối cùng; log release chứng minh đường cleanup chứ không chứng minh commit. Với connection pool, connection vật lý còn mở sau khi trả về pool thường là hành vi bình thường.

## Tài liệu tham khảo

- [Spring Framework — Understanding the Declarative Transaction Implementation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-decl-explained.html)
- [Spring Framework — Example of Declarative Transaction Implementation (transaction log)](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/first-example.html)
- [Spring Framework — Controlling Database Connections](https://docs.spring.io/spring-framework/reference/data-access/jdbc/connections.html)
- [Spring Framework — Synchronizing Resources with Transactions](https://docs.spring.io/spring-framework/reference/data-access/transaction/tx-resource-synchronization.html)
- [Spring Framework — Transaction Propagation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html)
- [Spring Framework — TransactionSynchronizationManager API](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/transaction/support/TransactionSynchronizationManager.html)
- [HikariCP — Configuration and Pool Lifecycle](https://github.com/brettwooldridge/HikariCP)
