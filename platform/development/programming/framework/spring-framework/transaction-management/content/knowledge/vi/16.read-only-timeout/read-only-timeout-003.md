# setEnforceReadOnly trong DataSourceTransactionManager của Spring Framework

## 1. Bài toán: readOnly=true có thực sự cấm ghi?

Khi thấy `@Transactional(readOnly = true)`, nhiều người cho rằng Spring sẽ chặn tất cả câu lệnh `INSERT`, `UPDATE` hoặc `DELETE` bên trong method. Suy luận này không đúng cho mọi JDBC driver và cơ sở dữ liệu.

Trong Spring JDBC có hai cấp xử lý cần phân biệt:

1. **JDBC hint**: Khi bắt đầu một transaction mới khai báo read-only, Spring chuẩn bị connection bằng lời gọi `Connection.setReadOnly(true)` khi thích hợp. Theo contract JDBC, đây là gợi ý để driver/database tối ưu hoặc áp dụng chế độ read-only; driver có thể hỗ trợ hay bỏ qua, nên không được khẳng định nó luôn cấm ghi.
2. **Database transaction mode được enforce**: Khi cấu hình `DataSourceTransactionManager.setEnforceReadOnly(true)`, Spring chạy câu lệnh `SET TRANSACTION READ ONLY` trên connection **khi bắt đầu một physical transaction mới có định nghĩa readOnly=true**. Những database hỗ trợ lệnh này sẽ thực thi quy tắc transaction read-only ở mức SQL.

Flag `enforceReadOnly` của `DataSourceTransactionManager` **mặc định là false**. Điều đó không có nghĩa mọi driver chắc chắn cho phép UPDATE: một số JDBC driver chủ động chuyển `Connection.setReadOnly(true)` thành SQL read-only mode. Ví dụ pgJDBC mặc định `readOnlyMode=transaction` có thể mở `BEGIN READ ONLY`. Vì thế nên kiểm tra trạng thái thực sự của database, không chỉ nhìn một flag.

Bài học tập trung vào chính API `setEnforceReadOnly`, thời điểm nó có hiệu lực, những điều nó không bảo đảm, sự khác nhau giữa transaction mới và transaction tham gia, cùng ví dụ Java 17+ chạy với PostgreSQL để quan sát SQL read-only mode.

## 2. API thuộc về manager, không thuộc annotation

Setter nằm trên class:

~~~java
org.springframework.jdbc.datasource.DataSourceTransactionManager
~~~

`JdbcTransactionManager` là subclass của `DataSourceTransactionManager` nên cũng có API này. Cấu hình một manager đơn giản:

~~~java
import javax.sql.DataSource;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;

@Configuration
class TxConfiguration {
    @Bean
    DataSourceTransactionManager transactionManager(DataSource ds) {
        DataSourceTransactionManager tx = new DataSourceTransactionManager(ds);
        tx.setEnforceReadOnly(true);
        return tx;
    }
}
~~~

Ví dụ chỉ là lớp cấu hình; toàn ứng dụng cần `DataSource` và hạ tầng quản lý `@Transactional`. Nên bật flag **một lần tại startup**, không chỉnh trong lúc các request production đang chạy. Với nhiều transaction managers, phải bảo đảm service dùng **đúng bean manager** đã bật flag. Tạo một `DataSourceTransactionManager` mới ngoài Spring context hoặc bật flag ở manager không quản lý JDBC connection của DAO sẽ không có tác dụng như dự định.

`@Transactional(readOnly=true)` là **transaction definition** mà transaction advice cung cấp; `setEnforceReadOnly(true)` là **cách transaction manager chuyển định nghĩa đó thành thao tác với database**. Hai cấu hình này cần đồng thời xuất hiện ở đúng boundary mới có tác dụng.

### Một lựa chọn tương đương khi dùng JdbcTransactionManager

~~~java
@Bean
org.springframework.jdbc.support.JdbcTransactionManager transactionManager(
        DataSource ds) {
    var manager = new org.springframework.jdbc.support.JdbcTransactionManager(ds);
    manager.setEnforceReadOnly(true);
    return manager;
}
~~~

Đây là **phương án thay thế** cho bean `DataSourceTransactionManager` phía trên, **không khai báo đồng thời cả hai** dưới cùng tên bean. `JdbcTransactionManager` có khả năng dịch lỗi JDBC trong commit/rollback tốt hơn ở các trường hợp tương ứng, nhưng cơ chế `setEnforceReadOnly` được kế thừa.

## 3. Chính xác khi nào Spring phát SET TRANSACTION READ ONLY?

`DataSourceTransactionManager` có hook protected `prepareTransactionalConnection(Connection, TransactionDefinition)`. Theo triển khai mặc định, hook thực thi:

~~~sql
SET TRANSACTION READ ONLY;
~~~

khi **cả hai điều kiện** đúng:

- Manager có `enforceReadOnly=true`.
- `TransactionDefinition.isReadOnly()` của transaction **đang được bắt đầu mới** bằng true.

Quy trình điển hình với JDBC:

1. Caller gọi method transactional **qua Spring AOP proxy**.
2. `TransactionInterceptor` quyết định mở transaction mới hay tham gia transaction hiện có.
3. Nếu mở transaction mới, `DataSourceTransactionManager` lấy JDBC connection từ `DataSource`, chuẩn bị read-only hint và isolation nếu cần, xử lý auto-commit.
4. Manager gọi `prepareTransactionalConnection`; nếu đủ điều kiện, statement `SET TRANSACTION READ ONLY` được phát **trước SQL nghiệp vụ của method**.
5. `JdbcTemplate` dùng transaction-bound connection để chạy SELECT/UPDATE.
6. Manager commit/rollback, dọn transaction context, khôi phục trạng thái connection cần thiết và trả connection về pool.

Trong đường đi này, transaction manager **không phát lệnh SET cho từng SELECT** và không tạo một transaction mới cho mọi method chỉ vì method có annotation.

~~~mermaid
flowchart TD
    A["Caller gọi bean qua Spring proxy"] --> B["TransactionInterceptor đọc @Transactional"]
    B --> C{"Có physical transaction hiện hữu?"}
    C -->|"Không; REQUIRED hoặc REQUIRES_NEW tạo mới"| D["DataSourceTransactionManager bắt đầu T mới"]
    C -->|"Có; REQUIRED tham gia"| J["Reuse physical transaction hiện tại"]
    D --> E["Connection.setReadOnly(true) nếu readOnly"]
    E --> F{"enforceReadOnly và definition.readOnly đều true?"}
    F -->|"Có"| G["SET TRANSACTION READ ONLY"]
    F -->|"Không"| H["Không có SQL SET explicit từ hook"]
    G --> I["Thực thi method qua JDBC connection của T"]
    H --> I
    J --> K["Không bắt đầu T mới; không tự SET read-only"]
    K --> I
~~~

### Đặt SET vào đúng transaction

`SET TRANSACTION READ ONLY` là thuộc tính của **physical transaction**, không phải toàn bộ application. Trong PostgreSQL, transaction characteristics phải được đặt trước các lệnh truy vấn/DML làm transaction tiến triển. Spring manager xử lý tại **begin hook** để đáp ứng điều kiện đó. Không tùy tiện phát lệnh ở giữa một service method đã có SQL và kỳ vọng DB cho thay đổi access mode.

## 4. So sánh JDBC read-only hint và database-enforced read-only

| Câu hỏi | `Connection.setReadOnly(true)` | `SET TRANSACTION READ ONLY` |
| --- | --- | --- |
| Ai nhận yêu cầu? | JDBC driver, rồi có thể tới DB | Database SQL engine |
| Có thể chỉ là hint? | Có | Nếu câu lệnh được DB hỗ trợ và thành công, access mode được áp dụng |
| Có cấm ghi bảng thường? | Không bảo đảm với mọi driver | PostgreSQL và các DB tương thích chặn nhiều loại DML/DDL bị cấm |
| Ảnh hưởng toàn bộ connection pool? | Không; chỉ connection/transaction liên quan | Không; chỉ physical transaction được SET |
| Có phải phân quyền bảo mật? | Không | Không, vẫn cần role/privilege |
| Có thay transaction isolation? | Không mặc nhiên | Không mặc nhiên: READ ONLY khác SERIALIZABLE |
| Có áp dụng vào inner REQUIRED join? | Không bắt đầu connection mới do inner | Không chạy hook begin mới |

Trên PostgreSQL, read-only transaction cấm `INSERT`, `UPDATE`, `DELETE`, `MERGE` với bảng không phải temporary và nhiều lệnh DDL. PostgreSQL có một số ngoại lệ cho temporary tables; read-only mode **không bảo đảm không có một byte nào được ghi ra đĩa**, càng không ngăn side effects HTTP, Kafka hay file do Java gọi. Do đó read-only là **database transaction access mode**, không phải hệ thống bảo mật tổng quát.

Theo Javadoc Spring, các DB như Oracle, MySQL và PostgreSQL hiểu ý tưởng `SET TRANSACTION READ ONLY`; semantics cụ thể, phiên bản, dialect, driver và các đặc tính snapshot khác nhau. Ví dụ Oracle có read consistency riêng cho read-only transaction. Không tự suy ra câu lệnh này hoạt động giống nhau ở mọi engine.

## 5. Chú ý pgJDBC: flag false nhưng database vẫn có thể read-only

PostgreSQL JDBC driver có thuộc tính `readOnlyMode`:

| pgJDBC `readOnlyMode` | Hành vi chính |
| --- | --- |
| `ignore` | `Connection.setReadOnly(true)` không tự đổi transaction access mode phía server |
| `transaction` (mặc định thường gặp) | Khi connection read-only và auto-commit false, driver có thể bắt đầu `BEGIN READ ONLY` |
| `always` | Ngoài behavior transaction, có thể đặt session read-only khi auto-commit true theo semantics driver |

Vì vậy, trên PostgreSQL với `readOnlyMode=transaction`, bạn có thể quan sát DB read-only **dù `DataSourceTransactionManager.setEnforceReadOnly(false)`**. Đó không nhất thiết là lỗi Spring hay dấu hiệu flag không hoạt động: driver đã chuyển JDBC hint thành SQL ở một tầng khác.

Ví dụ thực nghiệm trong bài **cố ý** dùng URL:

~~~properties
spring.datasource.url=jdbc:postgresql://localhost:55432/readonly_demo?readOnlyMode=ignore
~~~

Chỉ để tách sự khác nhau giữa **hint không được driver enforce** và **SQL SET explicit do manager phát**. `readOnlyMode=ignore` **không phải** cấu hình được khuyến nghị cho production; dùng nó có thể làm giảm bảo vệ đang có nếu manager không bật enforce và một method read-only vô tình ghi dữ liệu.

Hãy đọc đúng cả ba tín hiệu:

- `TransactionSynchronizationManager.isCurrentTransactionReadOnly()`: Spring context khai báo read-only?
- `Connection.isReadOnly()`: JDBC driver báo cờ hint thế nào?
- `SHOW transaction_read_only` trên PostgreSQL: **server** đang có transaction access mode nào?

Chỉ một trong ba tín hiệu, đặc biệt cờ Spring, **không đủ** để khẳng định database chắc chắn chặn UPDATE.

## 6. Propagation: transaction mới khác inner tham gia

Manager có `setEnforceReadOnly(true)`, nhưng hiệu quả phụ thuộc propagation:

| Phạm vi | Physical transaction | Phát SQL SET cho phạm vi này? |
| --- | --- | --- |
| `@Transactional(readOnly=true)`, không có transaction ngoài | Tạo mới | Có, nếu dùng đúng manager/DB |
| `@Transactional(readOnly=false)`, không có transaction ngoài | Tạo mới | Không |
| `@Transactional` không ghi readOnly | Tạo mới, default readOnly=false | Không |
| `REQUIRES_NEW, readOnly=true` bên trong outer read-write | Suspend outer, tạo inner độc lập | Có cho inner |
| `REQUIRED, readOnly=true` tham gia outer read-write | Dùng lại transaction outer | Không phát SQL SET mới từ annotation inner |
| `REQUIRED, readOnly=false` tham gia outer read-only | Dùng lại transaction outer | Inner không tự tắt chế độ read-only outer |
| `NESTED` qua savepoint khi được hỗ trợ | Không có physical transaction độc lập | Không dùng hook như mở transaction mới |
| `SUPPORTS` không có transaction vật lý | Không mở physical transaction | Không |
| Self-invocation `this.inner()` trong proxy mode | Bỏ qua transaction advice của inner | Annotation inner không tự phát SET |

### Ví dụ tham gia REQUIRED

~~~java
@Service
class OuterService {
    private final InnerService inner;

    OuterService(InnerService inner) {
        this.inner = inner;
    }

    @Transactional(readOnly = false)
    public void outer() {
        inner.readSomething();
    }
}

@Service
class InnerService {
    @Transactional(
        propagation = Propagation.REQUIRED,
        readOnly = true
    )
    public void readSomething() {
        // Transaction của outer vẫn là read-write theo mặc định.
    }
}
~~~

Đây là đoạn cấu trúc minh họa; cần bổ sung imports/bean database nếu chạy độc lập. Lời gọi phải đi **qua proxy bean InnerService** để manager xử lý metadata inner. Dù vậy, `REQUIRED` tham gia cùng transaction đã mở bởi outer, nên `setEnforceReadOnly(true)` **không nâng** outer từ read-write lên read-only.

### validateExistingTransaction khác enforceReadOnly

`setValidateExistingTransaction(true)` là một setting **khác** của các transaction manager dựa trên `AbstractPlatformTransactionManager`. Nó yêu cầu kiểm tra sự tương thích của transaction definition khi **tham gia một transaction có sẵn**. Nó không làm `REQUIRED` thành transaction mới và không thay thế hook `SET TRANSACTION READ ONLY`.

Ví dụ, khi inner **read-write** tham gia outer **read-only**, strict validation có thể từ chối vì definition của inner không tương thích với transaction ngoài. Tuy nhiên không được khẳng định validator kiểm tra **đối xứng** mọi trường hợp: logic Spring có hướng kiểm tra cụ thể; inner read-only tham gia outer read-write thường vẫn join mà không bị ép sang read-only. Muốn inner độc lập, dùng `REQUIRES_NEW` và chấp nhận thay đổi semantics commit/rollback.

## 7. Cấu hình @Transactional ở class/method và chọn đúng manager

Nếu class có `@Transactional(readOnly=true)` nhưng method lại ghi `@Transactional`, annotation method thường được chọn trước. Method trống có `readOnly=false` mặc định, nên không được enforce chỉ vì class đặt readOnly=true.

~~~java
@Transactional(readOnly = true)
class SearchService {
    public void list() {
        // Không có annotation riêng: lấy policy của class.
    }

    @Transactional
    public void refreshCacheTable() {
        // Annotation method được chọn, readOnly mặc định là false.
    }
}
~~~

Đây là mã minh họa. **Spring không ghép từng thuộc tính thiếu** giữa annotation method và annotation class. Việc một method không bị DB chặn UPDATE có thể do class policy bị override, transaction không qua proxy, hoặc dùng nhầm manager/datasource — không chỉ do flag enforce.

Trong multi-datasource application, dùng tên manager tường minh khi cần, chẳng hạn `@Transactional(transactionManager="reportingTx", readOnly=true)`. Cấu hình `setEnforceReadOnly(true)` trên `reportingTx` không tác động tự động lên `ordersTx`. Đảm bảo `JdbcTemplate` cũng dùng chính nguồn mà manager quản lý; nếu tạo connection trực tiếp từ datasource khác, SQL có thể nằm ngoài transaction được enforce.

## 8. Demo Java 17+ thực tế với Spring Boot, PostgreSQL và Docker Compose

Demo này kiểm chứng chính hành vi của manager trên PostgreSQL, **không dùng H2 để giả định dialect tương thích**. Bộ công cụ: Java 17+, Maven, Docker Compose, Spring Boot **3.3.5** (Spring Framework 6.1.x), pgJDBC, PostgreSQL **16**.

Các tình huống:

1. JDBC hint nhưng `enforceReadOnly=false` với driver `readOnlyMode=ignore`: Spring thấy readOnly=true, server vẫn báo off, UPDATE +1 thành công.
2. Bật `enforceReadOnly=true` ngoài mọi transaction: server báo on, UPDATE bảng thường bị từ chối và rollback; dữ liệu không đổi.
3. SELECT trong read-only transaction vẫn thành công, còn method read-write được phép UPDATE.
4. Inner `REQUIRED, readOnly=true` tham gia outer read-write, server vẫn off.
5. Inner `REQUIRES_NEW, readOnly=true` mở transaction độc lập: server on bên trong rồi trở lại off ở outer.

**Trong production, không sửa flag trên manager khi có concurrent requests.** Ở đây chương trình CLI chạy tuần tự và chỉ đổi flag giữa các lời gọi để dễ thấy tác dụng.

### 8.1. Cấu trúc project

~~~text
enforce-readonly-demo/
├── compose.yaml
├── pom.xml
└── src/main/
    ├── resources/application.properties
    └── java/example/readonly/
        ├── ReadOnlyDemoApplication.java
        ├── ReadOnlyService.java
        └── OuterService.java
~~~

Các mật khẩu `demo` và cổng localhost chỉ dùng cho sandbox cục bộ.

### 8.2. compose.yaml

~~~yaml
services:
  pg:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: readonly_demo
      POSTGRES_USER: demo
      POSTGRES_PASSWORD: demo
    ports:
      - "127.0.0.1:55432:5432"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U demo -d readonly_demo"]
      interval: 2s
      timeout: 3s
      retries: 30
~~~

### 8.3. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>
    <groupId>example</groupId>
    <artifactId>enforce-readonly-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-jdbc</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-aop</artifactId>
        </dependency>
        <dependency>
            <groupId>org.postgresql</groupId>
            <artifactId>postgresql</artifactId>
            <scope>runtime</scope>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 8.4. src/main/resources/application.properties

~~~properties
spring.main.web-application-type=none
spring.datasource.url=jdbc:postgresql://localhost:55432/readonly_demo?readOnlyMode=ignore
spring.datasource.username=demo
spring.datasource.password=demo
spring.datasource.hikari.maximum-pool-size=5
~~~

`readOnlyMode=ignore` chỉ nhằm cô lập effect của Spring SQL hook; với pgJDBC mặc định, riêng JDBC hint đã có thể tạo server read-only transaction.

### 8.5. src/main/java/example/readonly/ReadOnlyDemoApplication.java

~~~java
package example.readonly;

import javax.sql.DataSource;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.dao.DataAccessException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.transaction.annotation.EnableTransactionManagement;

@SpringBootApplication
@EnableTransactionManagement
public class ReadOnlyDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(ReadOnlyDemoApplication.class, args);
    }

    @Bean
    DataSourceTransactionManager transactionManager(DataSource ds) {
        var manager = new DataSourceTransactionManager(ds);
        manager.setEnforceReadOnly(false);
        return manager;
    }

    @Bean
    CommandLineRunner run(
            JdbcTemplate jdbc,
            DataSourceTransactionManager manager,
            ReadOnlyService service,
            OuterService outer) {
        return args -> {
            jdbc.execute(
                "CREATE TABLE IF NOT EXISTS public.tx_counter "
                + "(id INT PRIMARY KEY, amount INT NOT NULL)"
            );
            jdbc.update("DELETE FROM public.tx_counter");
            jdbc.update(
                "INSERT INTO public.tx_counter (id, amount) VALUES (?, ?)",
                1, 100
            );
            System.out.println("START=" + amount(jdbc));

            manager.setEnforceReadOnly(false);
            service.attemptWrite("HINT");
            System.out.println("AFTER_HINT=" + amount(jdbc));

            manager.setEnforceReadOnly(true);
            try {
                service.attemptWrite("ENFORCED");
            } catch (DataAccessException ex) {
                System.out.println("ENFORCED_UPDATE_REJECTED=true");
            }
            System.out.println("AFTER_ENFORCED=" + amount(jdbc));

            service.queryReadOnly();
            service.writeNormally();
            System.out.println("AFTER_WRITE=" + amount(jdbc));

            outer.joinReadOnly();
            outer.newReadOnly();
            System.out.println("END=" + amount(jdbc));
        };
    }

    private static Integer amount(JdbcTemplate jdbc) {
        return jdbc.queryForObject(
            "SELECT amount FROM public.tx_counter WHERE id = ?",
            Integer.class, 1
        );
    }
}
~~~

### 8.6. src/main/java/example/readonly/ReadOnlyService.java

~~~java
package example.readonly;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionSynchronizationManager;

@Service
public class ReadOnlyService {
    private final JdbcTemplate jdbc;

    public ReadOnlyService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional(readOnly = true)
    public void attemptWrite(String label) {
        System.out.println(
            label + "_SPRING_READ_ONLY="
                + TransactionSynchronizationManager.isCurrentTransactionReadOnly()
        );
        System.out.println(label + "_DB_READ_ONLY=" + mode());
        jdbc.update(
            "UPDATE public.tx_counter SET amount = amount + 1 WHERE id = 1"
        );
    }

    @Transactional(readOnly = true)
    public void queryReadOnly() {
        System.out.println("READ_ONLY_DB=" + mode());
        Integer amount = jdbc.queryForObject(
            "SELECT amount FROM public.tx_counter WHERE id = 1",
            Integer.class
        );
        System.out.println("READ_ONLY_SELECT=" + amount);
    }

    @Transactional(readOnly = false)
    public void writeNormally() {
        System.out.println("WRITE_DB=" + mode());
        jdbc.update(
            "UPDATE public.tx_counter SET amount = amount + 10 WHERE id = 1"
        );
    }

    @Transactional(
        readOnly = true,
        propagation = Propagation.REQUIRED
    )
    public void reportJoined() {
        System.out.println("JOIN_DB=" + mode());
    }

    @Transactional(
        readOnly = true,
        propagation = Propagation.REQUIRES_NEW
    )
    public void reportNew() {
        System.out.println("NEW_DB=" + mode());
    }

    private String mode() {
        return jdbc.queryForObject(
            "SHOW transaction_read_only", String.class
        );
    }
}
~~~

### 8.7. src/main/java/example/readonly/OuterService.java

~~~java
package example.readonly;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OuterService {
    private final JdbcTemplate jdbc;
    private final ReadOnlyService inner;

    public OuterService(JdbcTemplate jdbc, ReadOnlyService inner) {
        this.jdbc = jdbc;
        this.inner = inner;
    }

    @Transactional(readOnly = false)
    public void joinReadOnly() {
        System.out.println("OUTER_JOIN_BEFORE=" + mode());
        inner.reportJoined();
        System.out.println("OUTER_JOIN_AFTER=" + mode());
    }

    @Transactional(readOnly = false)
    public void newReadOnly() {
        System.out.println("OUTER_NEW_BEFORE=" + mode());
        inner.reportNew();
        System.out.println("OUTER_NEW_AFTER=" + mode());
    }

    private String mode() {
        return jdbc.queryForObject(
            "SHOW transaction_read_only", String.class
        );
    }
}
~~~

### 8.8. Chạy và kiểm tra kết quả

Từ thư mục chứa `pom.xml`:

~~~bash
docker compose up -d
docker compose exec -T pg pg_isready -U demo -d readonly_demo
mvn -q spring-boot:run
~~~

Nếu `pg_isready` chưa báo server ready, chỉ chạy Maven sau khi PostgreSQL đã sẵn sàng. Đầu ra **chỉ tính những dòng ứng dụng tự in** (không tính log Spring Boot/HikariCP):

~~~text
START=100
HINT_SPRING_READ_ONLY=true
HINT_DB_READ_ONLY=off
AFTER_HINT=101
ENFORCED_SPRING_READ_ONLY=true
ENFORCED_DB_READ_ONLY=on
ENFORCED_UPDATE_REJECTED=true
AFTER_ENFORCED=101
READ_ONLY_DB=on
READ_ONLY_SELECT=101
WRITE_DB=off
AFTER_WRITE=111
OUTER_JOIN_BEFORE=off
JOIN_DB=off
OUTER_JOIN_AFTER=off
OUTER_NEW_BEFORE=off
NEW_DB=on
OUTER_NEW_AFTER=off
END=111
~~~

**Giải thích những mốc cốt lõi:**

- `HINT_SPRING_READ_ONLY=true`: Spring context nhận read-only definition.
- `HINT_DB_READ_ONLY=off`: driver `readOnlyMode=ignore` không enforce hint, manager flag false không gửi SET, nên server transaction là read-write.
- `AFTER_HINT=101`: update +1 thành công, minh họa rằng read-only annotation đơn lẻ **không phải** cam kết SQL bị từ chối khi driver bỏ qua hint.
- `ENFORCED_DB_READ_ONLY=on`: flag true khiến Spring manager phát SET trước business SQL.
- `ENFORCED_UPDATE_REJECTED=true`: PostgreSQL từ chối UPDATE bảng thường, `JdbcTemplate` dịch SQLException thành `DataAccessException`; exception đi qua service proxy, transaction rollback và caller bắt ngoài boundary.
- `AFTER_ENFORCED=101`: dữ liệu không đổi sau lỗi.
- `READ_ONLY_SELECT=101`: transaction read-only vẫn đọc được.
- `WRITE_DB=off`, `AFTER_WRITE=111`: manager flag true không cấm transaction khai báo read-write.
- `JOIN_DB=off`: inner REQUIRED tham gia outer read-write; không có physical transaction mới để chạy SET.
- `NEW_DB=on`: inner REQUIRES_NEW tạo transaction read-only riêng, trong khi outer tạm suspend; sau đó OUTER_NEW_AFTER trở về off.
- `END=111`: các bước kiểm tra join/new không sửa dữ liệu.

Ví dụ dựa trên PostgreSQL 16, pgJDBC `readOnlyMode=ignore`, một manager và các beans được Spring inject. Nếu thay DB, driver property, propagation hoặc config khác, **không được mặc định giữ nguyên stdout**. Chạy demo ở database sandbox duy nhất vì runner `DELETE FROM public.tx_counter` để reset dữ liệu.

Dọn container lab khi hoàn tất:

~~~bash
docker compose down
~~~

## 9. Vì sao không dùng H2 để chứng minh SQL enforcement của flag?

H2 thường hữu ích cho unit/integration tests Spring JDBC, nhưng H2 không nhất thiết hỗ trợ cùng cú pháp và semantics `SET TRANSACTION READ ONLY` như PostgreSQL. H2 documentation mô tả `Connection.setReadOnly` có thể chỉ là hint; SQL command catalog thông dụng không có cùng lệnh `SET TRANSACTION READ ONLY` như PostgreSQL.

Nếu bật `setEnforceReadOnly(true)` trong manager mặc định và driver/DB không chấp nhận statement đó, lỗi có thể phát sinh **ngay khi bắt đầu transaction**, trước khi method chạy. Đây là lỗi **khác biệt SQL dialect**, không phải một “read-only UPDATE rejected” thành công. Với dự án dùng H2 để test và PostgreSQL ở production, nên phân tách:

- Unit tests của service logic có thể không bật explicit enforcement nếu H2 không hỗ trợ statement.
- Integration tests xác minh enforcement thực sự phải chạy đúng PostgreSQL (ví dụ Testcontainers) hoặc DB giống production.
- Nếu DB cần câu lệnh riêng, có thể tùy biến `prepareTransactionalConnection` có kiểm soát.
- Không suy ra hành vi của transaction manager chỉ từ test H2 thành công trong chế độ hint.

## 10. Tùy biến prepareTransactionalConnection khi SQL dialect khác

Spring cho phép subclass `DataSourceTransactionManager` và override hook:

~~~java
@Override
protected void prepareTransactionalConnection(
        Connection con, TransactionDefinition definition) throws SQLException {
    // Phát SQL chỉ nếu definition.isReadOnly()
    // và DB đã được xác nhận hỗ trợ cú pháp tương ứng.
}
~~~

Đây là **trích đoạn hook**, cần imports `java.sql.Connection`, `java.sql.SQLException` và `TransactionDefinition`. Không phải mọi database đều dùng nguyên lệnh `SET TRANSACTION READ ONLY`. Nếu override:

- Hook chạy **khi physical transaction mới bắt đầu**, không chạy mỗi lần inner REQUIRED join.
- Dùng `try (Statement st = con.createStatement()) { ... }` khi thực thi SQL.
- Không tự gọi `con.commit()`, `con.rollback()` hoặc `con.close()` trong hook.
- Nếu gọi `super.prepareTransactionalConnection(...)` cùng lúc phát câu lệnh tùy biến, cần tránh phát SQL hai lần hoặc thứ tự sai.
- Lệnh access mode phải được thực thi đúng **thời điểm DB cho phép thay đổi transaction characteristics**, thường trước SQL nghiệp vụ đầu tiên.
- Lỗi SQL từ hook có thể làm transaction begin thất bại; đừng nuốt lỗi rồi tiếp tục một transaction read-write mà caller tưởng được enforce.

Đây là extension point chuyên sâu. Nếu không có yêu cầu dialect riêng, tốt hơn dùng implementation mặc định với DB được Spring hỗ trợ và viết integration test.

## 11. Read-only khác isolation, timeout và quyền ghi

Một service có thể khai báo:

~~~java
@Transactional(
    readOnly = true,
    isolation = Isolation.READ_COMMITTED,
    timeout = 10,
    propagation = Propagation.REQUIRED
)
public void produceReport() {
    // Trích đoạn minh họa.
}
~~~

Mỗi thuộc tính phục vụ mục tiêu khác nhau:

| Thuộc tính | Vai trò |
| --- | --- |
| `readOnly=true` | Đề nghị transaction chỉ đọc; với flag enforce đúng manager có thể phát SQL READ ONLY |
| `isolation=READ_COMMITTED` | Quy tắc visibility giữa concurrent transactions, không phải read-only |
| `timeout=10` | Deadline giao dịch do manager/hệ nền hỗ trợ, không phải phép cấm DML |
| `propagation=REQUIRED` | Join một physical transaction có sẵn hoặc tạo mới nếu chưa có |

`READ ONLY` không đồng nghĩa `SERIALIZABLE`, và `setEnforceReadOnly` không bảo đảm SQL nhanh hơn hay tự hạn chế mọi query. Một transaction read-only có thể vẫn cần lock, bị chặn bởi transaction khác hoặc gặp timeout. Tùy DB, một số tối ưu read-only có thể phát huy hiệu quả, nhưng cần đo.

**Bảo mật:** `SET TRANSACTION READ ONLY` không thay thế DB roles/privileges. Một ứng dụng có DB user quyền UPDATE có thể dùng một transaction read-write ở request khác. Nếu cần tài khoản chỉ đọc, thiết kế role database với privilege phù hợp; flag read-only chỉ là lớp phòng thủ vận hành bổ sung.

**Ngoài database:** read-only không ngăn gọi HTTP endpoint, xuất event Kafka, gửi email hoặc ghi file từ cùng method. Các side effects ngoài transaction có thể xảy ra ngay cả khi SQL transaction bị rollback.

## 12. Khi bật flag nhưng UPDATE vẫn thành công: checklist debug

1. **Có đúng manager không?** Service dùng `DataSourceTransactionManager` hoặc `JdbcTransactionManager` đã bật flag, hay thực tế chạy `JpaTransactionManager`/một bean khác?
2. **Annotation nào có hiệu lực?** Method annotation có thể override policy class; `@Transactional` trống có `readOnly=false` mặc định.
3. **Invocation qua proxy chưa?** `this.inner()` trong proxy mode thường không kích hoạt transaction interceptor của inner.
4. **Có physical transaction mới không?** `REQUIRED` inner tham gia outer read-write thì không SET lại.
5. **Manager quản lý đúng DataSource chưa?** DAO/JdbcTemplate có dùng cùng nguồn không? Có connection được lấy trực tiếp ngoài Spring transaction awareness không?
6. **Driver đã biến hint thành SQL chưa?** Với pgJDBC mặc định `readOnlyMode=transaction`, server có thể ở read-only ngay cả khi flag false.
7. **Database hiểu statement không?** Xem log từ `prepareTransactionalConnection` và lỗi syntax/dialect khi begin.
8. **Bạn đang đo Spring flag hay DB mode?** Dùng `SHOW transaction_read_only` cho PostgreSQL, không chỉ `isCurrentTransactionReadOnly()`.
9. **Loại bảng và SQL nào?** PostgreSQL có ngoại lệ với temporary tables; test UPDATE vào bảng thường để thấy read-only restriction.
10. **Có transaction test bọc ngoài?** `@Transactional` ở test method có thể tạo physical transaction trước khi service được gọi, khiến service join thay vì tạo mới.
11. **Có ngoại lệ bị catch không?** Một DB error có thể khiến transaction aborted/rollback-only, nên sau catch không tự giả định có thể commit.
12. **Read-only mode có bị dùng nhầm như security policy không?** Kiểm tra DB permissions và đường truy cập khác.

Có thể bật log có kiểm soát trong môi trường test:

~~~properties
logging.level.org.springframework.jdbc.datasource.DataSourceTransactionManager=DEBUG
logging.level.org.springframework.transaction.interceptor=TRACE
logging.level.org.springframework.jdbc.core.JdbcTemplate=DEBUG
~~~

Log hỗ trợ xác định proxy/manager và begin hook, nhưng **đọc server mode là bằng chứng trực tiếp hơn** về enforcement.

## 13. Những lỗi tư duy thường gặp

| Ngộ nhận | Sự thật |
| --- | --- |
| “`readOnly=true` luôn cấm DML” | Theo JDBC, read-only hint có thể không được enforce |
| “Flag false nghĩa là PostgreSQL chắc chắn cho UPDATE” | pgJDBC có thể tự `BEGIN READ ONLY` |
| “Flag true áp dụng cho mọi manager/DB” | Đây là setter của JDBC manager cụ thể, cần dialect được hỗ trợ |
| “Inner REQUIRED readOnly=true biến outer read-write thành read-only” | Tham gia physical transaction không mở begin hook mới |
| “`REQUIRES_NEW` chỉ đổi read-only mà không đổi atomicity” | Inner là transaction vật lý độc lập |
| “`setValidateExistingTransaction(true)` cũng là flag enforce SQL” | Nó kiểm tra compatibility khi join, không phát `SET TRANSACTION READ ONLY` thay thế |
| “H2 chạy được JDBC hint nghĩa là hỗ trợ SET của PostgreSQL” | JDBC API và SQL dialect là hai tầng khác |
| “Spring context readOnly=true chứng minh DB read-only” | Spring metadata và server access mode có thể khác nhau |
| “Read-only là authorization” | Quyền database user vẫn phải thiết kế riêng |
| “Không DML thì không side effects” | Java vẫn có thể gửi HTTP/message, thay đổi cache hoặc file |
| “Bật flag chỉ là tối ưu hiệu năng” | Có thể thay đổi behavior của luồng ghi nhầm và gây lỗi ở DB không hỗ trợ |
| “Tăng isolation sẽ thay flag” | Isolation và access mode là hai thuộc tính khác nhau |

## 14. Bài tập có đáp án

**Bài 1.** Method `@Transactional(readOnly=true)` mở transaction mới với manager đã `setEnforceReadOnly(true)`. DB PostgreSQL hỗ trợ SQL SET. Có gì xảy ra trước khi service SELECT?

**Đáp án:** Manager phát `SET TRANSACTION READ ONLY` ở begin hook cho transaction đó; SELECT chạy dưới server read-only mode.

**Bài 2.** Inner `REQUIRED` readOnly=true join outer readOnly=false. Manager bật enforcement. Có cấm UPDATE trong inner không?

**Đáp án:** Không tự cấm bởi flag này: inner không mở physical transaction mới. Nếu DB/resource có cơ chế khác thì kết quả phải đo riêng; trong mô hình PostgreSQL có outer read-write, SET của inner không được phát.

**Bài 3.** Đổi inner thành `REQUIRES_NEW` readOnly=true, outer vẫn read-write. Kết quả?

**Đáp án:** Outer suspend, inner mở transaction mới và được SET READ ONLY nếu DB hỗ trợ; khi inner kết thúc, outer resume read-write. Inner có commit/rollback độc lập.

**Bài 4.** Với pgJDBC mặc định, flag Spring false nhưng UPDATE trong readOnly=true bị PostgreSQL từ chối. Có phải Spring vẫn lén bật flag true?

**Đáp án:** Không cần. Driver có thể biến `Connection.setReadOnly(true)` thành `BEGIN READ ONLY`. Phải kiểm tra `readOnlyMode` và SQL log/server state.

**Bài 5.** Đã bật flag true nhưng method annotated không qua Spring proxy do `this.method()`. Điều gì cần kiểm tra?

**Đáp án:** Transaction advice của method self-called có thể hoàn toàn không chạy. Cần proxy boundary hoặc programmatic `TransactionTemplate` phù hợp để tạo transaction.

**Bài 6.** Test trên H2 bị lỗi cú pháp tại begin, có phải test chứng minh DML bị chặn?

**Đáp án:** Không. Manager có thể không khởi tạo được transaction vì H2 không hiểu câu SQL dialect. Dùng đúng DB production-like hoặc custom hook có kiểm soát.

**Bài 7.** Server read-only từ chối UPDATE nhưng service đã gửi email trước đó. Rollback transaction có thu hồi email không?

**Đáp án:** Không. Enforcement chỉ giới hạn database transaction; cần thiết kế side effects riêng.

## 15. Kết luận và tài liệu chính thức

`setEnforceReadOnly(true)` là cơ chế **enforce ở tầng SQL** cho **transaction JDBC mới có readOnly=true** mà `DataSourceTransactionManager` quản lý. Nó làm rõ hơn ý định của `@Transactional(readOnly=true)` bằng lệnh `SET TRANSACTION READ ONLY`, nhưng tác dụng phụ thuộc database, driver, propagation, proxy invocation và lựa chọn manager.

Không nhầm nó với JDBC hint `Connection.setReadOnly(true)`, isolation, timeout, `setValidateExistingTransaction` hay quyền database. Một số driver PostgreSQL **đã enforce từ hint** ngay khi flag false. Để kiểm chứng đáng tin, so sánh server mode trên đúng connection/physical transaction, cố tình UPDATE bảng thường, đọc dữ liệu sau khi proxy hoàn tất và dùng DB tương thích.

Nguồn tham khảo:

- [Spring Framework — DataSourceTransactionManager Javadoc 6.1](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/jdbc/datasource/DataSourceTransactionManager.html): `setEnforceReadOnly` và `prepareTransactionalConnection`.
- [Spring Framework — Transaction Propagation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html): REQUIRED vs REQUIRES_NEW và physical transaction.
- [Spring Framework — Using @Transactional](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html): readOnly, proxy và default metadata.
- [PostgreSQL — SET TRANSACTION](https://www.postgresql.org/docs/current/sql-set-transaction.html): read-only access mode và lệnh bị hạn chế.
- [pgJDBC — Initializing the Driver](https://jdbc.postgresql.org/documentation/use/): `readOnlyMode=ignore`, `transaction`, `always`.
- [Java 17 — java.sql.Connection](https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/Connection.html): `setReadOnly` là hint.
- [H2 — SQL Commands](https://h2database.com/html/commands.html): cú pháp SQL mà H2 hỗ trợ.
