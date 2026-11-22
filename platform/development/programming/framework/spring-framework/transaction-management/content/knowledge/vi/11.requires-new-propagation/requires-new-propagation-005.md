# Nhu cầu thêm kết nối trong connection pool khi dùng PROPAGATION_REQUIRES_NEW

## 1. Tại sao một request có thể giữ hai JDBC connection?

Khi một method đã chạy trong transaction Spring gọi một method khác với `@Transactional(propagation = Propagation.REQUIRES_NEW)` **qua transaction proxy**, Spring phải tạo một **physical transaction mới** cho method bên trong. Physical transaction ngoài được **tạm ngưng (suspend)** trong lúc inner hoạt động, sau đó mới được khôi phục (resume).

Trong ứng dụng JDBC dùng `DataSourceTransactionManager` hoặc `JdbcTransactionManager` với một `DataSource` có connection pool, điều quan trọng là **suspend transaction không đồng nghĩa trả connection của transaction ngoài về pool**. Nếu outer đã mượn connection C1, connection đó vẫn được giữ để tiếp tục physical transaction T1. Inner `REQUIRES_NEW` cần một transaction vật lý T2 độc lập và thường mượn connection **C2** từ cùng pool. Vì vậy một Java thread có thể **đồng thời chiếm hai pool slots** dù không chạy hai đoạn Java song song.

~~~text
Caller -> OuterService proxy
             |
             v
        @Transactional(REQUIRED) outer:
        begin T1, giữ JDBC connection C1
             |
             v
        InnerService proxy:
        @Transactional(REQUIRES_NEW)
             |
             +-- suspend context T1; C1 vẫn thuộc outer
             +-- begin T2, mượn connection C2
             +-- chạy SQL, commit/rollback T2, trả C2
             |
             v
        resume T1; tiếp tục dùng C1
        commit/rollback T1; trả C1
~~~

Nhu cầu thêm connection là **cái giá tài nguyên cho ngữ nghĩa commit/rollback độc lập**: inner commit thành công không bị hủy chỉ vì outer rollback sau đó. Không thể vừa đòi hai transaction vật lý độc lập vừa mặc nhiên dùng duy nhất một JDBC connection vẫn đang nằm trong outer transaction.

**Giới hạn phát biểu:** Đây là đường đi điển hình với Spring JDBC và outer **đã borrow JDBC connection thật**. Nếu không có outer transaction, hoặc outer dùng cơ chế lazy connection và chưa thực sự đụng DB, mức active đo được có thể khác. JPA, JTA, reactive R2DBC có cách quản lý tài nguyên riêng; không áp một con số cố định cho mọi hệ.

## 2. So sánh REQUIRED, REQUIRES_NEW và NESTED dưới góc nhìn tài nguyên

Giả sử mọi bean/method được gọi qua Spring AOP proxy đúng cách và dùng **một JDBC DataSource**:

| Propagation inner | Physical transaction | Connection khi outer đang giữ C1 | Khả năng hoàn tất độc lập |
| --- | --- | --- | --- |
| `REQUIRED` | Tham gia T1 có sẵn | Thường tiếp tục dùng C1 đã gắn với transaction | Không commit riêng; inner có thể đặt shared transaction rollback-only |
| `REQUIRES_NEW` | Suspend T1, mở T2 độc lập | C1 còn giữ; T2 thường mượn C2 | Có; T2 commit/rollback riêng với T1 |
| `NESTED` | Thường dùng savepoint trong T1 | Thường tiếp tục C1 | Có thể rollback một phần đến savepoint, **không** commit riêng khỏi T1 |
| Không có transaction ngoài và gọi `REQUIRES_NEW` | Tạo mới T2 | Chỉ cần connection cho T2 theo cơ chế thông thường | Không có C1 phải giữ |

`REQUIRED` không mặc nhiên cần thêm connection khi outer và inner dùng cùng manager/resource. `NESTED` không phải một cách tương đương để tạo transaction audit độc lập: nếu outer rollback, toàn bộ physical transaction bao gồm thay đổi sau savepoint của inner vẫn bị hủy.

`REQUIRES_NEW` không chỉ là tên khác của `REQUIRED`. Spring có thể áp dụng isolation, timeout, read-only riêng cho T2, và khóa mà T2 giữ thường được giải phóng khi T2 hoàn tất. Đó là những lợi ích thực sự, nhưng tạo thêm áp lực lên pool nếu outer đang giữ connection.

## 3. Sơ đồ tài nguyên trong cùng một thread

~~~mermaid
flowchart TD
    A["Java thread gọi outer qua proxy"] --> O["Physical transaction T1"]
    O --> C1["Borrow JDBC Connection C1"]
    C1 --> H["Outer thực thi SQL rồi giữ C1"]
    H --> S["inner() qua Spring proxy<br/>PROPAGATION_REQUIRES_NEW"]
    S --> P["Suspend context T1<br/>C1 chưa trả về pool"]
    P --> I["Physical transaction T2"]
    I --> C2["Borrow JDBC Connection C2"]
    C2 --> DB[("Cơ sở dữ liệu")]
    C1 --> DB
    C2 --> E["Inner commit/rollback T2<br/>release C2"]
    E --> R["Resume T1 trên C1"]
    R --> F["Outer hoàn tất T1<br/>release C1"]
~~~

Dòng trạng thái có thể quan sát ở **ứng dụng JDBC/Hikari đơn luồng cô lập**:

| Mốc | Trạng thái T1 | Trạng thái T2 | `activeConnections` |
| --- | --- | --- | ---: |
| Trước outer | Chưa có | Chưa có | 0 |
| Outer begin và đã borrow C1 | Hoạt động | Chưa có | 1 |
| Inner begin T2 | Suspend, giữ C1 | Hoạt động trên C2 | 2 |
| Inner kết thúc | Vẫn giữ C1 | C2 được trả | 1 |
| Outer kết thúc | C1 được trả | Đã kết thúc | 0 |

Đây là **mốc lý luận của ví dụ bên dưới**, không phải chuẩn bắt buộc cho mọi cấu hình ORM hoặc nhiều request. Một pool có nhiều traffic cũng có thể cho active=5, 10... ở những thời điểm tương ứng.

### Spring suspend điều gì?

Trong Spring imperative, transaction manager và synchronization infrastructure quản lý liên kết tài nguyên với thread hiện tại. Khi vào inner `REQUIRES_NEW`, framework suspend transaction context ngoài, gỡ/tạm lưu tài nguyên của outer khỏi ngữ cảnh hiện hành và tạo context mới. **Nó không phải lệnh commit/rollback của outer.**

Nếu connection C1 thuộc T1 chưa hoàn tất, trả C1 cho một giao dịch khác sẽ vi phạm việc bảo toàn trạng thái transaction. Vì thế outer giữ C1 cho đến khi T1 hoàn tất, còn T2 cần một resource riêng. Dù `JdbcTemplate` trong hai service dùng **cùng bean DataSource**, nó vẫn có thể nhận hai connection **khác nhau**, do transaction context tại lúc borrow khác nhau.

## 4. Tình huống cạn pool: mọi luồng giữ một connection và cùng đợi connection nữa

Giả sử `maximumPoolSize=3`, ba thread đồng thời xử lý ba request, mỗi request đã mở outer transaction, thực thi SQL và giữ connection:

~~~text
Pool maximum = 3

Thread A: outer T1A giữ C1 -> gọi inner REQUIRES_NEW -> chờ C4
Thread B: outer T1B giữ C2 -> gọi inner REQUIRES_NEW -> chờ C4
Thread C: outer T1C giữ C3 -> gọi inner REQUIRES_NEW -> chờ C4

Active=3, Idle=0, Awaiting=3.
Không còn connection cho bất kỳ inner nào được cấp phát.
~~~

Tất cả thread **giữ connection ngoài trong lúc chờ connection trong**. Không inner nào có connection để chạy và hoàn tất, nên không slot nào được giải phóng theo đường bình thường. Đây là **pool-locking / pool starvation**, thường dẫn đến **timeout khi acquire connection** khi hết `connectionTimeout`, hoặc gây nghẽn kéo dài nếu cơ chế chờ không được giới hạn tốt.

Cần phân biệt:

- **Pool-locking:** inner không có connection để bắt đầu SQL vì mọi connection đã được các outer giữ.
- **Database deadlock/row-lock wait:** inner **đã** mượn connection nhưng SQL chờ lock do outer/transaction khác giữ. Tăng pool không chữa dependency khóa này.
- **Connection leak:** code mượn connection nhưng không release đúng; khác với việc outer giữ connection hợp lệ đến cuối transaction.
- **Transaction timeout:** giới hạn thời gian của transaction; khác `connectionTimeout` khi chờ pool.

### Nếu tăng pool lên 4?

Một connection thứ tư có thể được cấp cho **một inner**. Nếu inner không chờ row lock hoặc tài nguyên đang bị giữ bởi các outer khác, nó có thể hoàn tất, trả connection cho inner tiếp theo. Như vậy pool có **đường tiến** thay vì tất cả cùng đợi.

Nhưng `maximumPoolSize=4` chỉ đủ cho **một inner chạy tại một lúc** trong trạng thái cả ba outer cùng giữ connection. Để cả ba inner cùng giữ connection đồng thời trong mô hình ấy, peak cần khoảng **6 active connections**. Việc có tối thiểu một slot trống để tránh pool-locking **khác** việc không muốn xếp hàng trong giờ cao điểm.

## 5. Tính pool size: hai câu hỏi, hai loại ngưỡng

Gọi:

- `T` = số thread/request đồng thời **đang giữ connection ngoài** từ một pool.
- `C` = số connection tối đa mà **một thread có thể đồng thời giữ** do các nested transaction, trong mô hình outer + một inner `REQUIRES_NEW` thì `C=2`.
- `P` = kích thước tối đa của **cùng pool**, bao gồm cả active và idle.
- `B` = connection dùng bởi công việc khác chung pool trong cùng thời gian (scheduler, các request khác, v.v.).

### 5.1. Ngưỡng tránh pool-locking trong mô hình tài nguyên đơn giản

HikariCP nêu một công thức lý thuyết giúp tránh trường hợp mọi thread đều giữ gần hết tài nguyên rồi cùng chờ một connection cuối:

\[
P_{\text{min}} = T \times (C-1) + 1
\]

Với một outer và một inner (`C=2`), ta có `P >= T+1`. Đây là nền tảng cảnh báo của Spring: pool cần **lớn hơn số thread có outer transaction đồng thời ít nhất một connection** trong trường hợp điển hình.

Ví dụ 8 outer cùng giữ 8 connection thì 8+1=9 có thể cho một inner có đường tiến. Nếu một thread có thể giữ **ba** connection do outer → inner `REQUIRES_NEW` → inner sâu hơn `REQUIRES_NEW`, thì `C=3` và với 8 thread, ngưỡng lý thuyết thành 8×(3−1)+1=17.

**Lưu ý:** Điều kiện này áp dụng một mô hình pool-level resource allocation, giả định inner được cấp slot có thể hoàn tất và trả slot. Nó **không** bảo đảm không có DB row-lock deadlock, không phải công thức tối ưu performance, và không tính hết nhu cầu `B`. Nếu phải giữ thêm connection từ các pool độc lập, tính riêng từng pool và ngân sách DB tổng thể.

### 5.2. Mức peak để mọi luồng có thể chạy inner cùng lúc

Khi toàn bộ `T` luồng cùng giữ tối đa `C` connection, peak demand (chưa tính overhead khác) có thể xấp xỉ:

\[
P_{\text{peak}} \approx T \times C + B
\]

Đây là phép ước lượng **khả năng xảy ra demand**, không phải khuyến nghị luôn cấu hình pool bằng giá trị ấy. Mở quá nhiều connections có thể làm giảm throughput database hoặc vượt quota session toàn hệ thống. Đôi khi giảm concurrency hiệu quả hơn tăng pool.

| T outer đồng thời | C max / thread | Ngưỡng để có đường tiến: `T(C−1)+1` | Peak khi tất cả giữ C, chưa tính B |
| ---: | ---: | ---: | ---: |
| 1 | 2 | 2 | 2 |
| 3 | 2 | 4 | 6 |
| 8 | 2 | 9 | 16 |
| 16 | 2 | 17 | 32 |
| 8 | 3 | 17 | 24 |

Ví dụ pool max 17 cho 16 outer + một inner mỗi luồng có thể cho một inner hoạt động trong trạng thái xấu nhất, nhưng các inner khác còn xếp hàng. Nếu muốn đồng thời giữ 32 connections, phải xem **database có chịu nổi 32 active SQL sessions hay không** và các pool khác có dùng cùng DB không.

### 5.3. Concurrency cần đo bằng request thật, không dùng nhầm số liệu

`T` **không phải tổng user đăng nhập** hay số HTTP connection. Chỉ cần đếm các flow đang giữ connection trong cùng thời điểm. Một web server có 200 request threads nhưng đồng thời chỉ 12 thread giữ JDBC connection thì `T` liên quan đến resource này gần 12 ở đỉnh tải đã đo; ngược lại một job executor có ít thread nhưng transaction rất dài cũng dễ gây pool pressure.

Tác nhân làm thay đổi tính toán gồm: thời gian giữ outer connection, I/O bên ngoài DB trong transaction, số tầng `REQUIRES_NEW`, multiple DataSources, JDBC connection acquisition lazy, pool của job khác, và giới hạn `max_connections` trên DB.

## 6. Spring Boot và HikariCP: các cài đặt thực sự liên quan

Với `spring-boot-starter-jdbc` hoặc Spring Data JPA starter, Spring Boot thường có sẵn dependency HikariCP. Khi datasource được Boot tự tạo, cấu hình thường nằm ở:

~~~properties
# Ví dụ minh họa, cần thay URL/credential/driver theo môi trường.
spring.datasource.url=jdbc:postgresql://db.example.internal:5432/orders
spring.datasource.username=orders_app

spring.datasource.hikari.pool-name=orders-pool
spring.datasource.hikari.maximum-pool-size=12
spring.datasource.hikari.minimum-idle=4
spring.datasource.hikari.connection-timeout=2000
~~~

**Không sử dụng máy chủ/credential giả định trên trong production.** Đo tải và ngân sách connections trước khi chọn giá trị, dùng secrets cho password.

| Thuộc tính | Tác động chính | Nhầm lẫn cần tránh |
| --- | --- | --- |
| `maximumPoolSize` | Tổng connection tối đa của pool, active + idle | Không phải số thread tối đa; không dành riêng slot cho inner |
| `minimumIdle` | Mức idle pool cố duy trì | Không cho phép vượt maximum khi pool đã đầy |
| `connectionTimeout` | Thời gian tối đa đợi borrow connection | Khác timeout của SQL/query hoặc toàn transaction |
| `poolName` | Tên dễ phân biệt pool trong log/metrics | Không thay đổi semantics của `REQUIRES_NEW` |
| `maxLifetime` | Giới hạn vòng đời connection trong pool | Không phải timeout giao dịch |
| `leakDetectionThreshold` | Cảnh báo connection giữ quá lâu | Có thể cảnh báo outer transaction dài hợp lệ, không chứng minh leak |

HikariCP khi hết idle connections và đã đạt `maximumPoolSize` sẽ chờ borrow tối đa `connectionTimeout` rồi báo lỗi lấy connection. Spring có thể bọc nguyên nhân JDBC thành exception tầng transaction, ví dụ `CannotCreateTransactionException` khi không thể begin inner transaction. Chuỗi log/loại exception cuối cùng phụ thuộc manager/driver/version.

**Ba timeout khác nhau:** `connectionTimeout` (chờ pool), `@Transactional(timeout=...)` (scope transaction, tùy manager), và statement/query timeout (SQL/DB). Chỉ tăng `connectionTimeout` làm request chờ lâu hơn, không tạo ra connection thứ hai nếu mọi outer vẫn đang giữ hết pool.

## 7. Demo hoàn chỉnh Java 17+: quan sát Hikari active=1 → 2 → 1 → 0

Ví dụ sử dụng **Spring Boot 3.3.5**, Java 17+, Maven, Spring JDBC, HikariCP và H2 in-memory. Có đúng một pool với `maximumPoolSize=2` và hai Spring service beans. Outer ghi hàng id=1 trong T1, inner `REQUIRES_NEW` ghi hàng id=2 trong T2. Hai hàng khác nhau tránh tạo lock dependency giữa T1 và T2. Outer cố tình ném unchecked exception để rollback **sau** khi inner đã commit, giúp kiểm chứng độc lập bằng dữ liệu.

### 7.1. Cấu trúc project

~~~text
requires-new-pool-demo/
├── pom.xml
└── src/main/java/example/txpool/
    ├── PoolDemoApplication.java
    ├── OuterService.java
    └── InnerService.java
~~~

### 7.2. Tệp pom.xml

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
    <artifactId>requires-new-pool-demo</artifactId>
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
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
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

### 7.3. Tệp src/main/java/example/txpool/PoolDemoApplication.java

~~~java
package example.txpool;

import com.zaxxer.hikari.HikariDataSource;
import javax.sql.DataSource;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.support.JdbcTransactionManager;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.annotation.EnableTransactionManagement;

@SpringBootApplication
@EnableTransactionManagement
public class PoolDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(PoolDemoApplication.class, args);
    }

    @Bean
    HikariDataSource dataSource() {
        HikariDataSource ds = new HikariDataSource();
        ds.setPoolName("requires-new-demo-pool");
        ds.setDriverClassName("org.h2.Driver");
        ds.setJdbcUrl("jdbc:h2:mem:txpool;DB_CLOSE_DELAY=-1");
        ds.setUsername("sa");
        ds.setPassword("");
        ds.setMaximumPoolSize(2);
        ds.setMinimumIdle(0);
        ds.setConnectionTimeout(1500);
        return ds;
    }

    @Bean
    PlatformTransactionManager transactionManager(DataSource ds) {
        return new JdbcTransactionManager(ds);
    }

    @Bean
    CommandLineRunner demo(
            JdbcTemplate jdbc, OuterService outer, HikariDataSource pool) {
        return args -> {
            jdbc.execute(
                "CREATE TABLE account (id INT PRIMARY KEY, balance INT NOT NULL)"
            );
            jdbc.update("INSERT INTO account (id, balance) VALUES (?, ?)", 1, 100);
            jdbc.update("INSERT INTO account (id, balance) VALUES (?, ?)", 2, 200);

            System.out.println("BEFORE=" + balances(jdbc));
            try {
                outer.writeAndRollback();
            } catch (IllegalStateException ex) {
                System.out.println("OUTER_ERROR=" + ex.getMessage());
            }
            System.out.println("AFTER=" + balances(jdbc));
            System.out.println(
                "ACTIVE_AFTER="
                + pool.getHikariPoolMXBean().getActiveConnections()
            );
        };
    }

    private static String balances(JdbcTemplate jdbc) {
        Integer a = jdbc.queryForObject(
            "SELECT balance FROM account WHERE id = ?", Integer.class, 1
        );
        Integer b = jdbc.queryForObject(
            "SELECT balance FROM account WHERE id = ?", Integer.class, 2
        );
        return a + "/" + b;
    }
}
~~~

**Tại sao tạo `HikariDataSource` bean?** Để demo chủ động đặt pool max=2, thay vì phụ thuộc default từng môi trường. Spring Boot thấy một `DataSource` và cung cấp `JdbcTemplate` tương ứng; bean transaction manager được tạo rõ ràng từ **chính** datasource đó. `DB_CLOSE_DELAY=-1` giữ H2 in-memory database sống trong lúc pool mượn/trả connection.

### 7.4. Tệp src/main/java/example/txpool/OuterService.java

~~~java
package example.txpool;

import com.zaxxer.hikari.HikariDataSource;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OuterService {
    private final JdbcTemplate jdbc;
    private final InnerService inner;
    private final HikariDataSource pool;

    public OuterService(
            JdbcTemplate jdbc, InnerService inner, HikariDataSource pool) {
        this.jdbc = jdbc;
        this.inner = inner;
        this.pool = pool;
    }

    @Transactional
    public void writeAndRollback() {
        jdbc.update(
            "UPDATE account SET balance = balance + ? WHERE id = ?",
            10, 1
        );
        System.out.println(
            "OUTER_ACTIVE="
                + pool.getHikariPoolMXBean().getActiveConnections()
        );

        inner.creditIndependently();

        System.out.println(
            "OUTER_RESUMED_ACTIVE="
                + pool.getHikariPoolMXBean().getActiveConnections()
        );
        throw new IllegalStateException("outer-rollback");
    }
}
~~~

### 7.5. Tệp src/main/java/example/txpool/InnerService.java

~~~java
package example.txpool;

import com.zaxxer.hikari.HikariDataSource;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

@Service
public class InnerService {
    private final JdbcTemplate jdbc;
    private final HikariDataSource pool;

    public InnerService(JdbcTemplate jdbc, HikariDataSource pool) {
        this.jdbc = jdbc;
        this.pool = pool;
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void creditIndependently() {
        jdbc.update(
            "UPDATE account SET balance = balance + ? WHERE id = ?",
            20, 2
        );
        System.out.println(
            "INNER_ACTIVE="
                + pool.getHikariPoolMXBean().getActiveConnections()
        );
    }
}
~~~

### 7.6. Lệnh chạy

Yêu cầu JDK 17+ và Maven, có thể cần tải dependencies từ Maven Central lần đầu. Trong thư mục chứa `pom.xml`:

~~~bash
mvn -q spring-boot:run
~~~

Chỉ xét **các dòng do chương trình in**; log khởi động Spring Boot/Hikari có thể thêm dòng khác:

~~~text
BEFORE=100/200
OUTER_ACTIVE=1
INNER_ACTIVE=2
OUTER_RESUMED_ACTIVE=1
OUTER_ERROR=outer-rollback
AFTER=100/220
ACTIVE_AFTER=0
~~~

### 7.7. Đọc đúng kết quả và thứ tự transaction

1. `BEFORE=100/200`: hai hàng khởi tạo ngoài method transaction của service.
2. `OUTER_ACTIVE=1`: caller `CommandLineRunner` gọi `OuterService` qua Spring proxy; outer mở transaction T1 và thực hiện UPDATE hàng id=1 trên C1. T1 chưa commit, nên connection vẫn active.
3. `INNER_ACTIVE=2`: gọi sang **bean `InnerService` được inject** nên đi qua proxy. `REQUIRES_NEW` suspend T1, mượn C2, update hàng id=2 trong transaction T2. Lúc này C1 vẫn thuộc outer, C2 thuộc inner: active=2.
4. Inner hoàn tất thành công, manager commit T2 và release C2. Spring resume T1.
5. `OUTER_RESUMED_ACTIVE=1`: chỉ C1 của outer còn borrowed.
6. Outer ném `IllegalStateException`. Vì lỗi unchecked thoát qua outer proxy, transaction T1 rollback, C1 được trả. Caller bắt exception **sau** proxy.
7. `AFTER=100/220`: hàng 1 +10 đã bị rollback với outer; hàng 2 +20 vẫn tồn tại do inner commit độc lập.
8. `ACTIVE_AFTER=0`: sau khi các câu SELECT cuối được giải phóng, demo cô lập không còn connection nào đang borrowed.

**Hai UPDATE cố ý dùng hai hàng khác nhau.** Nếu inner T2 cố UPDATE đúng hàng outer T1 đã khóa, inner có thể chờ row lock của T1 ngay cả khi pool max=2; outer đang chờ inner xong nên vòng chờ có thể làm demo thất bại. Đây là vấn đề lock khác với bài toán pool capacity.

Đo Hikari active tại các thời điểm ở ví dụ chứng minh behavior **trong môi trường một luồng/một pool**. Với production có các workload khác, con số active còn chịu ảnh hưởng của các borrower khác; không dùng chúng để suy ra số connection cho mỗi method trong mọi phiên bản JPA hoặc driver.

## 8. Bài thử thay pool size=1: thất bại borrow connection

Sau khi chạy thành công bản demo, có thể thử đổi **một dòng** ở `PoolDemoApplication.java`:

~~~java
ds.setMaximumPoolSize(1);
~~~

Đây chỉ là **biến thể thử nghiệm**, không phải cấu hình của stdout thành công ở mục 7.

Outer mượn C1 và giữ đến khi transaction hoàn tất. Inner `REQUIRES_NEW` cần C2 nhưng pool không có slot thứ hai. Với `connectionTimeout=1500` ms, HikariCP chờ rồi báo không thể acquire connection, Spring có thể ném exception transaction liên quan, chẳng hạn `CannotCreateTransactionException` có cause JDBC timeout. Loại exception và log chính xác phụ thuộc môi trường; **không** kỳ vọng chương trình tiếp tục in `INNER_ACTIVE=2` hoặc `AFTER=100/220` trong biến thể này.

Vì runner của demo chỉ catch `IllegalStateException` được outer chủ động ném sau inner, biến thể pool max=1 có thể khiến quá trình chạy kết thúc bằng lỗi. Điều đó phù hợp mục tiêu chứng minh rằng **ngay một thread** cũng có thể không hoàn tất một outer → REQUIRES_NEW khi outer đang giữ connection mà pool chỉ có một slot.

Trả pool max về 2 sau khi thử. Không sử dụng kích thước 1 cho flow có independent transaction lồng nhau nếu outer thường đang giữ connection.

### Với nhiều outer đồng thời, vấn đề lớn hơn

Nếu có 8 outer đang giữ 8 connection của pool max=8, cả 8 inner đang đợi C9, pool có `active=8`, `idle=0`, `pending≈8`. Khi pool max=9, một inner có thể chạy rồi trả C9; các inner khác sẽ xếp hàng. Khi pool max=16, trong mô hình đơn giản có thể có 8 outer + 8 inner đồng thời, nhưng database cũng phải chịu được số session/query đó.

## 9. Đo và giám sát pool thay vì đoán cấu hình

Để chẩn đoán, cần đồng thời kiểm tra transaction call graph và pool metrics.

| Chỉ số | Đang đo điều gì? | Dấu hiệu cần xem |
| --- | --- | --- |
| Active connections | Số connection đã được borrow | Liên tục chạm maximum trong giờ cao điểm |
| Idle connections | Số connection có thể cấp ngay | Gần 0 khi latency tăng |
| Pending / threads awaiting connection | Số thread đang chờ borrow | Tăng đúng khi các outer gọi inner `REQUIRES_NEW` |
| Total connections | Tổng connection đang tồn tại | Gần max; phân biệt với active |
| Acquisition latency | Thời gian mượn connection | p95/p99 cao trước timeout |
| Connection timeouts | Số lần borrow hết thời gian | Tăng trong burst hoặc pool-locking |
| Transaction duration | Độ dài outer giữ connection | Transaction dài làm nhu cầu concurrent connection cao hơn |
| DB lock waits | SQL đang chờ lock | Tăng dù pool còn connection, phân biệt row lock |

`HikariDataSource#getHikariPoolMXBean()` cho phép đọc `getActiveConnections()`, `getIdleConnections()`, `getTotalConnections()`, `getThreadsAwaitingConnection()`. Khi dùng Spring Boot Actuator/Micrometer có thể có metrics của Hikari; kiểm tra tên metric thực tế theo version và backend quan sát. Với nhiều pools, luôn phân tách theo `poolName`.

Log thử nghiệm có thể bật:

~~~properties
logging.level.org.springframework.transaction.interceptor=TRACE
logging.level.org.springframework.jdbc.datasource=DEBUG
logging.level.com.zaxxer.hikari=DEBUG
~~~

Không bật DEBUG quá rộng trong production vì chi phí và thông tin nhạy cảm. Thông điệp log thay đổi theo version/manager.

### Cách đọc một lần timeout

1. Timeout đến từ **pool nào**, kích thước thực tế bao nhiêu?
2. Có bao nhiêu outer transactions đang giữ connection lúc đó?
3. Có lời gọi `REQUIRES_NEW` nào đang chờ borrow connection? Có bao nhiêu tầng?
4. Inner đã lấy connection chưa, hay đang chờ DB lock sau khi lấy?
5. Outer transaction giữ connection lâu vì SQL, HTTP call, sleep/retry hay logic bất đồng bộ?
6. `connectionTimeout` có bị đặt quá ngắn/ quá dài so với SLO không?
7. Có chương trình khác cùng pool (batch, scheduler, listener), hoặc nhiều app instances cộng dồn connections trên một DB?
8. Transaction manager và `DataSource` của outer/inner có đúng cùng pool dự kiến không?
9. Connection được trả sau khi scope hoàn tất hay có leak thật?
10. Test tải có tái tạo lỗi với số outer đồng thời và resource dependencies tương ứng không?

Một lần snapshot `active=maximum` chưa đủ để kết luận có deadlock; pool hoạt động hiệu quả đôi khi đầy mà vẫn có throughput tốt nếu borrower nhả connection kịp. Tín hiệu mạnh hơn là **active gần max + pending tăng + borrow latency/timeout + call graph outer giữ connection rồi gọi REQUIRES_NEW**.

## 10. Những cách giảm áp lực pool và giới hạn của từng cách

### 10.1. Chỉ dùng REQUIRES_NEW khi cần transaction độc lập

Nếu nghiệp vụ muốn **mọi thay đổi cùng commit hoặc cùng rollback**, `REQUIRED` thường phù hợp hơn và không tách transaction vật lý. Nếu nghiệp vụ yêu cầu một bước độc lập tồn tại ngay cả khi outer thất bại (ví dụ audit quan trọng), `REQUIRES_NEW` có ý nghĩa, nhưng phải trả giá về connection và atomicity.

**Không đổi propagation mù quáng** chỉ để xử lý timeout. Đổi `REQUIRES_NEW` thành `REQUIRED` có thể khiến một thông tin audit trước đây tồn tại sau khi outer rollback nay cũng bị rollback.

### 10.2. Rút ngắn transaction ngoài

Outer càng giữ connection lâu, càng nhiều request có thể cùng chiếm pool. Hạn chế HTTP calls, sleep, xử lý file, tính toán nặng và chờ remote service **trong transaction** khi logic nghiệp vụ cho phép. Thiết kế ranh giới transaction quanh những thao tác DB thực sự cần atomicity.

Ví dụ cấu trúc minh họa, **không phải code chạy độc lập**:

~~~java
ValidationResult validated = remoteValidator.validate(request);
transactionalService.persist(validated);
~~~

Không chuyển một bước ra khỏi transaction nếu điều đó phá invariants/consistency; mục tiêu là rút ngắn resource hold time **mà vẫn đúng nghiệp vụ**.

### 10.3. Giới hạn concurrency hoặc tạo hàng đợi

Nếu database không chịu được peak 2T connections, việc tăng pool vô hạn không phải giải pháp. Có thể giới hạn số flow đồng thời bằng bounded executor, queue hoặc semaphore, chừa slot cho inner và workload khác. Tính concurrency budget từ database capacity và số pool trong toàn fleet (mọi instance), không chỉ từ Java thread pool ở một JVM.

### 10.4. NESTED/savepoint khi mục đích là rollback một phần

Khi manager/driver JDBC hỗ trợ `PROPAGATION_NESTED`, inner có thể rollback đến savepoint trên cùng physical transaction. Nó thường không cần connection T2 riêng như `REQUIRES_NEW`. Nhưng inner **không commit độc lập**: outer rollback vẫn hủy mọi thay đổi còn nằm trong T1. Chỉ chọn nếu semantics này phù hợp.

### 10.5. TransactionTemplate không tránh được connection thứ hai

Nếu dùng programmatic transaction:

~~~java
// Trích đoạn trong Spring bean, đã inject PlatformTransactionManager manager.
TransactionTemplate template = new TransactionTemplate(manager);
template.setPropagationBehavior(
    TransactionDefinition.PROPAGATION_REQUIRES_NEW
);
template.executeWithoutResult(status -> {
    // JDBC work cần transaction mới.
});
~~~

`TransactionTemplate` tránh giới hạn self-invocation vì boundary được tạo trực tiếp, nhưng vẫn yêu cầu **physical transaction mới**, nên không làm biến mất nhu cầu C2 nếu outer đã giữ C1.

### 10.6. Không nhầm hai pool với một transaction phân tán

Nếu outer dùng `ordersDataSource` còn inner dùng `auditDataSource`, mỗi pool có budget riêng. Phải chọn đúng transaction manager cho từng bean; dùng hai DataSources không tự tạo một distributed atomic transaction. Nếu hai pool cùng trỏ một database, tổng connection của **cả hai** vẫn ăn vào quota session của DB.

## 11. Những ngoại lệ và bẫy đáng chú ý

### 11.1. Lazy connection acquisition

`LazyConnectionDataSourceProxy` hoặc một số ORM có thể trì hoãn borrow physical JDBC connection đến câu SQL đầu tiên. Outer chỉ chạy logic Java nhưng chưa SQL thì có thể chưa chiếm một pool slot. Khi inner chạy, bạn có thể quan sát active=1 thay vì 2. **Đừng suy ra `REQUIRES_NEW` bị bỏ qua chỉ từ một số đo active thấp**: hãy kiểm chứng proxy, manager, connection timing và commit độc lập.

### 11.2. JPA/Hibernate

`JpaTransactionManager` quản lý `EntityManager` và persistence context, thường dùng JDBC connection ở tầng thấp. Thời điểm borrow/release có thể phụ thuộc JPA provider. Cảnh báo về resource pressure vẫn quan trọng, nhưng không khẳng định mọi outer annotated đều ngay lập tức mượn một connection hay mọi nested JPA setup giống Spring JDBC.

### 11.3. R2DBC không dùng HikariCP JDBC

`R2dbcTransactionManager` dùng `ConnectionFactory` và Reactor subscriber context, không phải `javax.sql.DataSource` của Hikari trong ví dụ. Dù transaction độc lập có thể làm tăng tài nguyên pool của R2DBC, key `spring.datasource.hikari.maximum-pool-size` không sửa trực tiếp pool R2DBC. Phải quan sát/cấu hình đúng driver/connection factory tương ứng.

### 11.4. Self-invocation có thể làm mất REQUIRES_NEW

Một bean tự gọi `this.inner()` trong proxy mode thường **bỏ qua interceptor của inner**, nên annotation `@Transactional(REQUIRES_NEW)` trên inner không tạo transaction mới. Có thể thấy chỉ một connection, nhưng đó **không phải** thành công tối ưu tài nguyên: semantics cần thiết có thể không được đáp ứng. Để có boundary đúng, tách method sang bean khác rồi gọi qua proxy, hoặc dùng `TransactionTemplate` trong trường hợp phù hợp.

### 11.5. Row-lock deadlock không thể sửa bằng tăng pool

T1 outer UPDATE hàng `id=1` và giữ lock chưa commit. Inner T2 `REQUIRES_NEW` cũng UPDATE hàng `id=1`, nhưng T2 chờ lock của T1; T1 lại đang chờ inner return mới tiếp tục. Dù pool có 2, 12 hay 100 connections, tăng pool **không gỡ vòng chờ khóa này**. Phải đổi phạm vi/ thứ tự lock/ dữ liệu inner cần truy cập, hoặc thay kiến trúc.

### 11.6. Pool active không phải thread count

Một thread có thể giữ hai connection; nhiều thread có thể cùng chia sẻ các connection qua các transaction nối tiếp khi chúng được release. Vì vậy `activeConnections` không bằng số request concurrent theo mọi thời điểm. Hãy đọc pool metrics **cùng** timeline borrow/release và propagation.

## 12. Thiết kế kiểm thử capacity đúng

### Test đơn luồng

1. Tạo H2 và Hikari pool max 2, dùng Spring proxy thật.
2. Outer UPDATE một hàng để chắc chắn đã giữ physical connection.
3. Inner `REQUIRES_NEW` UPDATE hàng khác và in `getActiveConnections()`.
4. Assert chuỗi active 1 → 2 → 1, và active 0 sau khi outer hoàn tất.
5. Outer cố tình rollback; assert chỉ update của inner tồn tại.
6. Tạo **một test riêng** với pool max 1 và timeout ngắn để xác nhận không borrow được inner connection. Không thay đổi config của test thành công rồi kỳ vọng cùng stdout.

### Test nhiều luồng

1. Chọn `T=3` và tạo ba outer transactions dùng ba hàng DB **khác nhau**.
2. Trong test harness, dùng barrier đợi cả ba outer đã borrow connection trước khi cho gọi inner.
3. Với pool max 3, quan sát pending tăng và borrow timeout khi mọi inner cần connection mới.
4. Với pool max 4, có thể ít nhất một inner bắt đầu nếu không có row-lock dependencies; các inner khác chờ slot.
5. Với pool max 6, về mặt connection có đủ cho cả ba inner đồng thời, nhưng SQL/DB có thể vẫn xếp hàng vì CPU, locks hoặc session quota.
6. Bảo đảm executor được shutdown, database reset và không có active connections bị giữ sau test.

Tránh `@Transactional` ngay trên test method nếu nó khiến service tham gia một outer test transaction rồi rollback ở cuối test, làm số connection/commit khác dự đoán. Đo từ một caller không bị bọc transaction test và kiểm tra dữ liệu **sau khi proxy hoàn tất**.

## 13. Bảng chẩn đoán nhanh

| Triệu chứng | Nghi vấn | Hướng xử lý |
| --- | --- | --- |
| Pool max 1, outer giữ C1, inner `REQUIRES_NEW` timeout | Thiếu C2 để bắt đầu T2 | Có slot cho inner hoặc đổi semantics nếu được phép |
| T outer giữ T connections, mọi inner đều pending | Pool-locking | Chừa capacity, giảm concurrency và transaction duration |
| Pool `T+1` không deadlock nhưng latency lớn | Chỉ một inner có thể chạy khi mọi outer giữ slot | Xem peak demand, SQL latency và DB capacity |
| Pool nhiều slot nhưng inner treo ở SQL | Row lock/DB resource dependency | Xem lock graph, không chỉ chỉnh pool |
| `REQUIRES_NEW` có trong code nhưng chỉ một transaction và dữ liệu inner rollback cùng outer | Self-invocation/manager/wiring sai | Xác minh đường qua proxy và integration test |
| Tăng `connectionTimeout` giảm lỗi nhưng p99 tăng | Chờ lâu hơn, không tăng supply | Sửa capacity/concurrency; dùng timeout phù hợp SLO |
| Thấy Hikari active cao trong lúc outer suspend | Outer giữ connection hợp lệ | Phân biệt với leak; kiểm tra bao lâu và release cuối scope |
| Tăng pool một instance rồi DB báo quá nhiều connections | Tổng pools của các replicas vượt DB quota | Budget connections toàn hệ thống |
| Inner cập nhật cùng hàng outer, vẫn treo khi pool đủ | T1 giữ lock mà T2 cần | Thiết kế lại thao tác/ranh giới transaction |
| Chuyển `REQUIRES_NEW` sang `NESTED` làm audit không còn commit độc lập | Semantics savepoint khác physical transaction độc lập | Chọn propagation theo nghiệp vụ |

## 14. Bài tập dự đoán trước khi chạy

**Câu 1.** Có 5 outer transactions đồng thời đã borrow 5 connections từ pool max 5; mỗi outer gọi inner `REQUIRES_NEW`. Điều gì có thể xảy ra?

**Đáp án:** Cả năm outer giữ hết pool; các inner cùng chờ connection thứ sáu và có thể timeout vì không ai tiến được. Đây là pool-locking theo mô hình đơn giản.

**Câu 2.** Đổi pool max từ 5 lên 6. Có đảm bảo năm inner chạy đồng thời không?

**Đáp án:** Không. Một slot trống có thể đủ cho **một inner** tiến lên rồi nhả slot cho inner khác nếu không chờ lock. Muốn năm outer + năm inner **đều active cùng lúc**, peak demand là 10 connections, chưa tính việc DB có chịu nổi hay không.

**Câu 3.** Một request có outer và hai tầng `REQUIRES_NEW` lồng nhau, cả ba physical transaction đều giữ connection. Pool max 2 đủ không?

**Đáp án:** Không cho tình huống cả ba cần sống đồng thời; có thể cần ba connections cho một thread. Phải xem depth và thời điểm trả resource.

**Câu 4.** Có 8 thread, mỗi thread tối đa giữ 3 connections. Công thức phòng pool-locking đơn giản của Hikari cho ngưỡng lý thuyết nào?

**Đáp án:** `8 × (3−1) + 1 = 17`. Con số này không phải cam kết throughput hay tránh DB deadlock.

**Câu 5.** Inner T2 commit rồi outer T1 rollback, thay đổi inner có bắt buộc bị rollback cùng không?

**Đáp án:** Không, nếu inner thật sự tạo transaction `REQUIRES_NEW` độc lập và commit thành công. Đây chính là khác biệt semantics phải bảo toàn khi chọn kiến trúc.

**Câu 6.** Pool max 20 còn idle nhưng inner T2 chờ UPDATE một hàng outer đang khóa. Tăng lên 40 có sửa không?

**Đáp án:** Không. Đây là phụ thuộc row lock giữa hai transaction, không phải thiếu connection.

**Câu 7.** Một service dùng `TransactionTemplate` với `PROPAGATION_REQUIRES_NEW` thay annotation. Có tái sử dụng connection outer C1 để né pool capacity không?

**Đáp án:** Không. Programmatic API chỉ tạo boundary theo cách khác; transaction vật lý mới vẫn cần resource riêng khi outer đã giữ C1.

## 15. Kết luận

**`REQUIRES_NEW` cần một transaction vật lý độc lập; với Spring JDBC và outer transaction đang giữ connection, điều đó thường đòi hỏi connection thứ hai từ pool.** Suspend outer không làm release C1. Một Java thread có thể tạm chiếm hai pool slots, và nhiều thread cùng giữ outer connection có thể khiến inner đồng loạt chờ rồi timeout.

Thiết kế dựa trên **concurrent outer thật**, **độ sâu `REQUIRES_NEW`**, **thời gian giữ resource**, **pool metrics** và **database capacity**, không chỉ số annotation hay số request. `T+1` giúp có đường tiến trong mô hình một outer–một inner, nhưng không phải đảm bảo latency. Dùng bounded concurrency, transaction ngắn, resource budget, integration tests và phân biệt pool starvation với row-lock dependency.

Giữ đúng ngữ nghĩa commit/rollback là ưu tiên: đừng dùng self-invocation, đổi propagation tùy tiện hoặc chỉ kéo timeout để che một vấn đề tài nguyên.

## Tài liệu tham khảo chính thức

- [Spring Framework — Transaction Propagation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html): `REQUIRES_NEW` giữ tài nguyên outer, lấy connection mới và cảnh báo pool exhaustion.
- [Spring Framework — Using @Transactional](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html): propagation, timeout, read-only và proxy.
- [Spring Framework — JDBC Connections](https://docs.spring.io/spring-framework/reference/data-access/jdbc/connections.html): `DataSourceTransactionManager`, `JdbcTransactionManager`, `DataSourceUtils`.
- [HikariCP — README](https://github.com/brettwooldridge/HikariCP): cấu hình `maximumPoolSize` và `connectionTimeout`.
- [HikariCP — About Pool Sizing](https://github.com/brettwooldridge/HikariCP/wiki/About-Pool-Sizing): nguyên tắc chống pool-locking và giới hạn cơ sở dữ liệu.
- [Spring Boot — SQL Databases](https://docs.spring.io/spring-boot/reference/data/sql.html): DataSource autoconfiguration và HikariCP.
