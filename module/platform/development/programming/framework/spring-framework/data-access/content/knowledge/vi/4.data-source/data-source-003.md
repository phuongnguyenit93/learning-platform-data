# Phân biệt DriverManagerDataSource với nguồn có nhóm kết nối

Trong Spring Data Access, `DataSource` là điểm vào để lấy kết nối JDBC. Hai đối tượng cùng triển khai `javax.sql.DataSource` có thể được truyền cho **cùng một `JdbcTemplate`**, nhưng chi phí, khả năng xử lý đồng thời và hành vi khi gọi `Connection.close()` khác nhau đáng kể:

- `DriverManagerDataSource` của Spring **không có connection pool**. Mỗi lần `getConnection()` thực sự cần một kết nối mới, nó mở một kết nối JDBC vật lý qua driver; đóng kết nối thường kết thúc kết nối vật lý đó.
- Một `DataSource` có **connection pool** (ví dụ `HikariDataSource` của HikariCP) quản lý tập kết nối vật lý có thể tái sử dụng. `getConnection()` mượn một kết nối logic; `close()` thường trả kết nối về pool để lượt tiếp theo sử dụng.

Điểm cần phân biệt ngay: **API giống nhau không có nghĩa chi phí sử dụng giống nhau**. Và **pool không đồng nghĩa với transaction**: quản lý vòng đời kết nối, giới hạn số kết nối và điều khiển giao dịch là ba trách nhiệm liên quan nhưng khác nhau.

## 1. DataSource là hợp đồng chung, không phải một loại pool

`javax.sql.DataSource` là interface tiêu chuẩn JDBC. Ứng dụng hỏi `DataSource.getConnection()` để nhận một `java.sql.Connection`, dùng JDBC để truy vấn, rồi giải phóng bằng `close()`. Interface không cam kết rằng mỗi lời gọi sẽ tạo kết nối vật lý mới, tái sử dụng kết nối cũ hay áp dụng giới hạn đồng thời.

Trong Spring, `JdbcTemplate` nhận một `DataSource`; nó quản lý thao tác lấy và giải phóng `Connection` theo cơ chế hỗ trợ giao dịch của Spring. Do đó, đổi cấu hình nguồn kết nối từ direct sang pooled thường **không cần sửa câu SQL hoặc mã DAO**.

```text
            Spring service / DAO
                     |
                     v
                JdbcTemplate
                     |
                     v
             DataSource (JDBC API)
                  /        \
                 /          \
DriverManagerDataSource     HikariDataSource
     không pool                có pool
         |                       |
  tạo connection mới      mượn / trả connection
         |                       |
         +----------> Database <-+
```

### 1.1. DriverManagerDataSource hoạt động thế nào?

`DriverManagerDataSource` nằm trong `org.springframework.jdbc.datasource`. Mỗi lần mã ứng dụng thực sự yêu cầu kết nối mới, nó dùng thông tin JDBC URL, username/password, driver để mở một connection vật lý. Nó không duy trì danh sách kết nối nhàn rỗi để cho lần sau mượn.

Vòng đời cơ bản khi **không nằm trong transaction đang quản lý kết nối**:

1. `getConnection()` → driver thiết lập phiên/kết nối vật lý tới DB.
2. Ứng dụng thực hiện câu lệnh.
3. `close()` → đóng kết nối vật lý; lần gọi `getConnection()` tiếp theo lại mở mới.

Tạo kết nối vật lý có thể phải thực hiện thiết lập socket, xác thực, TLS, session và tài nguyên phía DB. Những bước này làm tăng độ trễ và tải khi nhiều tác vụ truy vấn ngắn chạy liên tiếp. Không nên suy rằng mỗi **câu SQL** luôn tạo connection mới: nếu có một transaction Spring đang hoạt động và mã sử dụng `JdbcTemplate`/`DataSourceUtils` đúng cách, các thao tác trong transaction có thể cùng sử dụng một connection gắn với transaction đó.

### 1.2. DataSource có pool hoạt động thế nào?

`HikariDataSource` là một triển khai pooling phổ biến. Nó quản lý connection vật lý và cấp cho ứng dụng một `Connection` logic (thường là proxy). Pool phân biệt:

- **Idle:** connection vật lý có sẵn để mượn.
- **Active / in use:** connection đang được ứng dụng giữ.
- **Pending / waiting:** lời gọi đang chờ vì chưa có connection khả dụng.
- **Total:** tổng số connection vật lý hiện được quản lý, gồm active và idle.

Vòng đời cơ bản:

1. `getConnection()` → pool cấp connection nhàn rỗi, hoặc tạo thêm nếu dưới giới hạn và cần thiết.
2. Ứng dụng thực hiện câu lệnh với connection đã mượn.
3. `close()` trên connection logic → pool thu hồi, khôi phục trạng thái mà pool quản lý và đưa connection vật lý về trạng thái có thể dùng lại nếu vẫn hợp lệ.
4. Một yêu cầu khác có thể mượn lại connection vật lý đó.

Pool có thể kiểm tra, loại bỏ hay thay thế connection lỗi/hết tuổi thọ. Do đó, **không phải mọi lần `close()` đều bảo đảm đưa chính connection vật lý đó về idle**; nhưng quy tắc sử dụng vẫn là phải đóng connection logic đúng thời điểm.

## 2. So sánh theo tiêu chí thực tế

| Tiêu chí | `DriverManagerDataSource` | `HikariDataSource` hoặc pool JDBC khác |
| --- | --- | --- |
| Tạo connection vật lý | Mở mới khi cần một `getConnection()` mới. | Mượn kết nối có sẵn; có thể mở thêm trong giới hạn pool. |
| `Connection.close()` | Thông thường đóng connection vật lý. | Thông thường trả connection logic cho pool; connection vật lý có thể tái sử dụng. |
| Chi phí cho nhiều truy vấn ngắn | Phải lặp lại chi phí thiết lập connection. | Có thể tiết kiệm chi phí nhờ tái sử dụng. |
| Giới hạn connection của chính DataSource | Không tự thực thi `maximumPoolSize`. | Có cấu hình giới hạn số connection vật lý mỗi pool. |
| Khi nhiều request đồng thời | Mỗi lần mượn thường cố mở connection mới; DB có thể từ chối khi quá giới hạn. | Khi hết connection rảnh và pool đã đạt giới hạn, request chờ rồi có thể timeout. |
| Quản lý connection nhàn rỗi | Không giữ pool idle. | Có chính sách minimum idle, idle timeout, max lifetime. |
| Quan sát vận hành | Ít chỉ số về pool, cần quan sát driver/DB. | Có thể quan sát active, idle, pending, total; tích hợp metrics. |
| Chi phí cấu hình/lifecycle | Đơn giản, không có pool cần đóng. | Cần cấu hình hợp lý và đóng `HikariDataSource` khi ứng dụng dừng. |
| Phù hợp | Thử nghiệm đơn giản, ví dụ nhỏ, các trường hợp số lần truy cập rất ít. | Dịch vụ thực tế có request lặp lại, concurrency và yêu cầu độ trễ ổn định. |

Spring Framework khuyến cáo `DriverManagerDataSource` và `SimpleDriverDataSource` chủ yếu cho **mục đích thử nghiệm**; khi nhiều yêu cầu kết nối, nên sử dụng pooling. Điều đó không có nghĩa test bắt buộc dùng direct: integration test có tải hoặc cần mô phỏng hành vi production cũng nên kiểm thử với pool.

## 3. Tại sao connection pooling quan trọng khi có tải?

Giả sử một dịch vụ nhận nhiều request đọc cơ sở dữ liệu:

**Không có pool** (nếu mỗi request cần và tự đóng một connection):
- Mỗi request có thể phải chờ mở kết nối vật lý.
- Các request đồng thời làm tăng số lần tạo connection và số connection đồng thời ở DB.
- DB có thể hết giới hạn kết nối hoặc tốn tài nguyên cho việc thiết lập/hủy phiên, dù từng truy vấn SQL rất nhanh.

**Có pool** (ví dụ `maximumPoolSize = 3`):
- Tại một thời điểm, **mỗi pool** quản lý tối đa 3 connection vật lý đến database theo chính sách của nó.
- Nếu cả 3 đang được sử dụng, request thứ tư phải đợi có connection được trả lại; nếu chờ quá `connectionTimeout` thì thất bại với lỗi lấy connection.
- Khi request ngắn hoàn thành, một connection được tái sử dụng, không phải thiết lập phiên mới mỗi lượt.

Ví dụ thời điểm 5 tác vụ cùng muốn mượn kết nối của một pool giới hạn 3:

```text
Tác vụ A ---> Connection #1 (active)
Tác vụ B ---> Connection #2 (active)
Tác vụ C ---> Connection #3 (active)
Tác vụ D ---> chờ connection rảnh -----+
Tác vụ E ---> chờ connection rảnh -----+
                                      |
                    A đóng logic -----+--> D có thể mượn lại #1
```

Giới hạn pool **không** có nghĩa toàn bộ hệ thống chỉ có 3 connection: nếu chạy 4 instance ứng dụng, mỗi instance có pool tối đa 3, tổng khả năng đạt 12 connection (chưa kể ứng dụng khác, migration, admin, công cụ vận hành). Vì vậy sizing cần dựa trên ngân sách connection của database và số instance tối đa, không chỉ số lượng thread HTTP.

### 3.1. Pool không làm SQL chậm tự nhiên trở nên nhanh

Pooling chủ yếu giảm chi phí **thiết lập** connection và quản lý concurrency; nó không thay đổi kế hoạch truy vấn, index, lock hay độ nhanh của SQL. Nếu giữ transaction quá lâu, pool nhanh chóng cạn active connections. Tăng `maximumPoolSize` vô hạn thường còn tăng cạnh tranh DB và có thể khiến hiệu năng xấu đi.

Độ trễ tổng thể có thể phân tách để chẩn đoán:

```text
Thời gian request liên quan DB
≈ thời gian đợi được connection
+ thời gian thực hiện SQL / đợi lock / truyền dữ liệu
+ thời gian xử lý kết quả và giữ connection
```

Đây là mô hình phân tích gần đúng, không phải công thức đo đạc tuyệt đối. Khi pool cạn, cần tìm **vì sao connection bị giữ lâu**, không chỉ tăng ngưỡng.

## 4. Cấu hình Spring Framework với hai cách cấp DataSource

Các ví dụ bên dưới dùng **Java 17+, Spring JDBC, HikariCP và H2** để thấy sự khác nhau. Hai cấu hình là **hai lựa chọn thay thế**: kích hoạt đúng một profile `direct` hoặc `pooled`. `H2` được dùng làm DB thử nghiệm; địa chỉ `jdbc:h2:mem:datasource_demo;DB_CLOSE_DELAY=-1` giữ database in-memory tồn tại sau khi connection cuối cùng đóng trong phạm vi tiến trình, phù hợp với việc `DriverManagerDataSource` mở/đóng nhiều connection. Cấu hình URL này là dành cho demo, không phải khuyến nghị triển khai production.

### 4.1. Cấu hình direct: DriverManagerDataSource

Tệp `DirectDataSourceConfig.java`:

```java
import javax.sql.DataSource;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;
import org.springframework.jdbc.datasource.DriverManagerDataSource;

@Configuration(proxyBeanMethods = false)
@Profile("direct")
public class DirectDataSourceConfig {

    @Bean
    public DataSource dataSource() {
        DriverManagerDataSource ds = new DriverManagerDataSource();
        ds.setDriverClassName("org.h2.Driver");
        ds.setUrl("jdbc:h2:mem:datasource_demo;DB_CLOSE_DELAY=-1");
        ds.setUsername("sa");
        ds.setPassword("");
        return ds;
    }
}
```

Cấu hình chứa driver, URL, username/password và tạo Bean `DataSource` thông thường. Mỗi lần phải lấy connection mới, `DriverManagerDataSource` không có kho idle connection để tái sử dụng. Trong ứng dụng thật, không ghi thông tin truy cập production trực tiếp trong mã nguồn; ví dụ dùng tài khoản H2 thử nghiệm.

### 4.2. Cấu hình pooled: HikariDataSource

Tệp `PooledDataSourceConfig.java`:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;

import com.zaxxer.hikari.HikariConfig;
import com.zaxxer.hikari.HikariDataSource;

@Configuration(proxyBeanMethods = false)
@Profile("pooled")
public class PooledDataSourceConfig {

    @Bean(destroyMethod = "close")
    public HikariDataSource dataSource() {
        HikariConfig cfg = new HikariConfig();
        cfg.setDriverClassName("org.h2.Driver");
        cfg.setJdbcUrl("jdbc:h2:mem:datasource_demo;DB_CLOSE_DELAY=-1");
        cfg.setUsername("sa");
        cfg.setPassword("");

        cfg.setPoolName("datasource-demo");
        cfg.setMaximumPoolSize(3);
        cfg.setMinimumIdle(1);
        cfg.setConnectionTimeout(2_000); // tối đa 2 giây chờ mượn
        return new HikariDataSource(cfg);
    }
}
```

Cùng tên Bean `dataSource` và cùng kết nối H2, nhưng cơ chế cấp connection khác nhau. `destroyMethod = "close"` bảo đảm Spring đóng pool khi ApplicationContext dừng bình thường. Chỉ bật một profile để tránh có hai Bean cạnh tranh.

Trong một project Spring Boot có `spring-boot-starter-jdbc` và driver H2, có thể đưa hai lớp trên vào package Spring quét, sau đó chạy:

```bash
./gradlew bootRun --args='--spring.profiles.active=direct'
./gradlew bootRun --args='--spring.profiles.active=pooled'
```

Hai lệnh là **hai lần chạy độc lập**; không chạy chúng đồng thời trên cùng ứng dụng chỉ để so sánh. Phần dependencies tương ứng trong project Spring Boot dùng Gradle:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    runtimeOnly 'com.h2database:h2'
}
```

Khi dùng Spring Boot starter JDBC, HikariCP thông thường đã có sẵn qua dependency. Nếu tự cấu hình Spring Framework không dùng starter, phải khai báo tường minh `spring-jdbc`, `HikariCP` và JDBC driver với phiên bản tương thích. Hai ví dụ Java trên là **lớp cấu hình trong ứng dụng Spring**, không phải một chương trình standalone có thể biên dịch bằng `javac` mà không có thư viện.

### 4.3. Mã truy vấn không cần đổi theo loại DataSource

Tệp `ProbeRepository.java`, dùng chung được với cả hai profile:

```java
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class ProbeRepository {
    private final JdbcTemplate jdbc;

    public ProbeRepository(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public int pingDatabase() {
        Integer result = jdbc.queryForObject("SELECT 1", Integer.class);
        if (result == null) {
            throw new IllegalStateException("Database did not return 1");
        }
        return result;
    }
}
```

Trong cả hai profile, với H2, `pingDatabase()` trả về **1**. Điều đó chỉ chứng minh cùng một hợp đồng truy vấn chạy được; **không chứng minh hai nguồn có hiệu năng tương đương**. Việc chứng minh pooling cần quan sát quá trình tạo connection, active/idle/pending hoặc thử nghiệm concurrency, không chỉ kiểm tra dữ liệu trả về.

## 5. Cấu hình thông dụng của Spring Boot trong ứng dụng thật

Với ứng dụng Spring Boot sử dụng `spring-boot-starter-jdbc` hoặc `spring-boot-starter-data-jpa`, HikariCP thường có sẵn và được Spring Boot ưu tiên tự cấu hình khi không có `DataSource` Bean tự định nghĩa. Khi đó có thể cấu hình pool bằng `application.yml` thay vì tự tạo `HikariDataSource` trong Java.

Ví dụ cấu hình PostgreSQL với giá trị được cấp qua biến môi trường:

```yaml
spring:
  datasource:
    url: jdbc:postgresql://localhost:5432/learning
    username: learning_user
    password: change-at-deployment
    hikari:
      pool-name: learning-db
      maximum-pool-size: 10
      minimum-idle: 2
      connection-timeout: 3000
      max-lifetime: 1800000
```

**Giải thích:** Đây là ví dụ dạng cấu hình, không phải bộ thông tin đăng nhập cần dùng nguyên văn. Trong hệ thống thật, đọc URL/user/password từ external configuration hoặc secret manager; không commit mật khẩu thật. `connection-timeout` và `max-lifetime` của Hikari sử dụng **mili-giây**, còn `maximum-pool-size` là số connection, không phải số request.

Một số property quan trọng:

| Property Hikari | Tác dụng | Rủi ro khi chọn sai |
| --- | --- | --- |
| `maximumPoolSize` | Tối đa connection vật lý do pool quản lý (idle + active). | Quá thấp gây chờ; quá cao làm DB quá tải, nhất là nhiều instance. |
| `minimumIdle` | Số connection idle mà pool cố duy trì. | Đặt cao có thể giữ nhiều phiên DB không dùng. |
| `connectionTimeout` | Thời gian tối đa chờ mượn connection khi không có sẵn. | Quá dài tích tụ request; quá ngắn gây timeout khi tải đột biến. |
| `maxLifetime` | Tuổi thọ tối đa dự kiến của connection trong pool. | Nên nhỏ hơn giới hạn của hạ tầng/DB có thể cắt kết nối; connection đang được dùng không bị cắt giữa chừng chỉ vì đạt ngưỡng này. |
| `idleTimeout` | Khoảng idle trước khi connection dư thừa có thể được loại bỏ. | Có tác dụng khi `minimumIdle < maximumPoolSize`; không nên tin là bộ đếm đúng từng mili-giây. |
| `leakDetectionThreshold` | Ghi log cảnh báo khi connection bị giữ quá lâu. | Là cơ chế cảnh báo nghi vấn, **không tự trả hoặc thu hồi** connection bị rò rỉ. |

Đây là các **tham số cần hiểu**, không phải bộ giá trị tối ưu cố định. Với HikariCP, nếu không đặt `minimumIdle`, mặc định thường theo `maximumPoolSize`; cấu hình pool gần như cố định cỡ đó. Chỉ cấu hình `minimumIdle` thấp hơn khi có lý do vận hành và đã kiểm tra hành vi tăng/giảm kết nối.

**Cạm bẫy Spring Boot:** Nếu ứng dụng khai báo Bean `DataSource` của chính mình (như `DriverManagerDataSource` ở trên), cơ chế auto-configuration `DataSource` mặc định thường sẽ nhường quyền. Thêm `spring.datasource.hikari.maximum-pool-size` vào YAML **không tự biến** một Bean `DriverManagerDataSource` do bạn tạo thành pooled source; property Hikari chỉ có ý nghĩa nếu thực sự đang chạy Hikari (hoặc tự bind cấu hình cho Bean tương ứng).

## 6. Giao dịch Spring và vòng đời Connection

Một hiểu nhầm thường gặp là “pool luôn lấy connection mới cho mỗi SQL” hoặc “có `@Transactional` thì không cần pooling”. Cả hai đều sai.

### 6.1. Ngoài transaction

Với `JdbcTemplate` và một thao tác truy vấn đơn lẻ, Spring lấy một connection rồi giải phóng khi thao tác xong:

- Direct DataSource: thường tạo và đóng kết nối vật lý cho mỗi lần lấy/giải phóng không tham gia transaction.
- Pooled DataSource: mượn connection logic, sau đó trả vào pool; lần kế tiếp có thể dùng lại kết nối vật lý.

### 6.2. Trong transaction

Với transaction JDBC được quản lý bởi `DataSourceTransactionManager` hoặc `JdbcTransactionManager`:

1. Spring bắt đầu transaction và liên kết resource `Connection` với luồng thực thi theo quy tắc quản lý transaction.
2. Những thao tác `JdbcTemplate` trong cùng transaction lấy connection theo `DataSourceUtils` và thường dùng chung connection đã liên kết.
3. Sau commit/rollback, Spring giải phóng connection về DataSource; direct sẽ đóng vật lý, pooled sẽ trả về pool nếu hợp lệ.

Do vậy, số connection vật lý tạo ra còn phụ thuộc **ranh giới transaction** và thời gian giữ transaction. Một transaction chạy lâu vừa giữ tài nguyên DB, vừa chiếm slot active của pool. `@Transactional` kiểm soát tính nhất quán/commit/rollback, còn pool kiểm soát việc cấp phát và tái sử dụng kết nối giữa nhiều transaction.

### 6.3. Đóng connection đúng API

Khi dùng JDBC thuần ngoài Spring-managed transaction, dùng `try-with-resources`:

```java
import java.sql.Connection;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Statement;
import javax.sql.DataSource;

public final class PlainJdbcProbe {
    public static int readOne(DataSource ds) throws SQLException {
        try (Connection con = ds.getConnection();
             Statement statement = con.createStatement();
             ResultSet result = statement.executeQuery("SELECT 1")) {
            if (!result.next()) {
                throw new SQLException("No row returned");
            }
            return result.getInt(1);
        }
    }
}
```

Hàm trên trả **1** khi SQL `SELECT 1` trả một hàng có số 1 (ví dụ H2/PostgreSQL). `try-with-resources` gọi `close()` kể cả khi xảy ra ngoại lệ. Với direct, kết nối vật lý kết thúc; với Hikari, handle thường được trả pool.

Trong Spring-managed transaction, tránh tự gọi `dataSource.getConnection()` và tự `close()` tùy tiện vì có thể bỏ qua context giao dịch. Ưu tiên `JdbcTemplate`. Nếu cần dùng JDBC `Connection` trực tiếp mà vẫn tham gia transaction của Spring, dùng cặp API:

```java
import java.sql.Connection;
import java.sql.SQLException;
import javax.sql.DataSource;

import org.springframework.jdbc.datasource.DataSourceUtils;

public final class SpringAwareProbe {
    public static void run(DataSource ds) throws SQLException {
        Connection con = DataSourceUtils.getConnection(ds);
        try {
            try (var statement = con.createStatement();
                 var result = statement.executeQuery("SELECT 1")) {
                result.next();
                int value = result.getInt(1);
                if (value != 1) {
                    throw new SQLException("Unexpected result");
                }
            }
        } finally {
            DataSourceUtils.releaseConnection(con, ds);
        }
    }
}
```

`DataSourceUtils.releaseConnection` chỉ đóng/giải phóng khi phù hợp với ranh giới transaction. Không giữ connection ngoài thời gian cần thiết; một connection không được dùng chung tùy tiện giữa nhiều luồng. Ngay cả khi đã dùng pool, vẫn phải giải phóng tất cả `ResultSet`, `Statement` và `Connection` đúng cách.

## 7. Kiểm chứng trực tiếp sự khác nhau

Một thí nghiệm hữu ích là cấp **hai connection cùng lúc** khi pool chỉ cho phép một connection. Ví dụ sau là mã Java 17 hoàn chỉnh ở mức lớp `ConnectionPoolExperiment.java`, có thể chạy trong project đã có `spring-jdbc`, `HikariCP`, H2 và runtime logging phù hợp.

```java
import java.sql.Connection;
import java.sql.SQLTransientConnectionException;

import com.zaxxer.hikari.HikariConfig;
import com.zaxxer.hikari.HikariDataSource;
import org.springframework.jdbc.datasource.DriverManagerDataSource;

public final class ConnectionPoolExperiment {
    private static final String URL =
        "jdbc:h2:mem:pool_experiment;DB_CLOSE_DELAY=-1";

    public static void main(String[] args) throws Exception {
        DriverManagerDataSource direct = new DriverManagerDataSource();
        direct.setDriverClassName("org.h2.Driver");
        direct.setUrl(URL);
        direct.setUsername("sa");
        direct.setPassword("");

        try (Connection first = direct.getConnection();
             Connection second = direct.getConnection()) {
            System.out.println("Direct: obtained two connections");
        }

        HikariConfig config = new HikariConfig();
        config.setJdbcUrl(URL);
        config.setUsername("sa");
        config.setPassword("");
        config.setMaximumPoolSize(1);
        config.setMinimumIdle(1);
        config.setConnectionTimeout(1_000);

        try (HikariDataSource pool = new HikariDataSource(config);
             Connection held = pool.getConnection()) {
            try (Connection second = pool.getConnection()) {
                System.out.println("Unexpected second connection");
            } catch (SQLTransientConnectionException expected) {
                System.out.println("Pool: second checkout timed out");
            }
        }
    }
}
```

**Các dòng do chương trình in ra `System.out` trong điều kiện H2 hoạt động và pool cấu hình như trên:**

```text
Direct: obtained two connections
Pool: second checkout timed out
```

HikariCP và các thư viện logging có thể in thêm thông tin riêng ngoài hai dòng trên. Thí nghiệm cho thấy:

- Direct tạo được 2 kết nối đồng thời do chính nó **không có giới hạn pool** (DB vẫn có thể có giới hạn riêng).
- Pool `maximumPoolSize=1` giữ một connection active, nên lời gọi thứ hai chờ tối đa khoảng 1 giây rồi thất bại khi không ai trả connection.
- **Đây là ví dụ giới hạn concurrency**, không phải phép benchmark về tốc độ. Nó cũng không chứng minh rằng Hikari chỉ tạo đúng một kết nối trong mọi trạng thái: khi lỗi/hết hạn, nó có thể thay connection vật lý theo chính sách của pool.

Không dùng `Connection.equals()`, `hashCode()` hoặc so sánh `first == second` để kết luận có tái sử dụng connection vật lý: pooled DataSource có thể trả những đối tượng wrapper khác nhau cho cùng một connection vật lý.

### 7.1. Quan sát trực tiếp pool thay vì suy đoán

Với `HikariDataSource` đã khởi tạo, có thể kiểm tra pool MXBean:

```java
HikariDataSource pool = /* DataSource đã được tạo ở ví dụ pooled */;
var mx = pool.getHikariPoolMXBean();

int total = mx.getTotalConnections();
int active = mx.getActiveConnections();
int idle = mx.getIdleConnections();
int pending = mx.getThreadsAwaitingConnection();
```

Đây là **đoạn minh họa đặt bên trong mã đã có biến `pool`**, không phải chương trình Java độc lập. Giá trị của các bộ đếm thay đổi liên tục theo tải; không kiểm thử bằng một giá trị cố định trong mọi thời điểm. Với Spring Boot Actuator + Micrometer, có thể theo dõi các metric Hikari tương ứng khi cấu hình hỗ trợ. Ghép metric ứng dụng với số phiên DB, lỗi timeout, thời gian truy vấn và thời gian transaction để xác định nút thắt.

## 8. Chọn cấu hình và xử lý lỗi thường gặp

### Khi nên dùng DriverManagerDataSource

- Test rất nhỏ, script minh họa một vài thao tác JDBC, hoặc môi trường cần cấu hình đơn giản để học cơ chế kết nối.
- Khi mục tiêu là quan sát rõ một lần kết nối vật lý được mở/đóng; không cần lượng request lặp lại.
- Tránh đưa direct DataSource vào môi trường xử lý nhiều request thường xuyên chỉ vì cấu hình ít dòng hơn.

### Khi nên dùng pooled DataSource

- Ứng dụng web/API, batch, worker hoặc hệ thống thực tế truy vấn DB nhiều lần.
- Có concurrency cần giới hạn, cơ chế chờ, timeout, giám sát và chính sách tái sử dụng kết nối.
- Có nhu cầu kiểm soát tổng số kết nối đến DB theo số instance và budget tài nguyên.

Không vì đã có pool mà đặt `maximumPoolSize` càng lớn càng tốt. Hãy đo: số connection active lúc cao điểm, thời gian chờ mượn, tỷ lệ timeout, độ trễ SQL, lock contention, số instance và giới hạn connection của DB.

### Tình huống chẩn đoán

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
| --- | --- | --- |
| Mỗi request đều có chi phí kết nối lớn | Đang dùng `DriverManagerDataSource` không pool | Xác nhận loại Bean `DataSource` thực tế; cân nhắc pooled DataSource. |
| Hikari báo timeout khi mượn | Pool cạn do connection bị giữ lâu, rò rỉ, SQL chậm hoặc giới hạn quá nhỏ | Kiểm tra active/pending, transaction duration, đường giải phóng connection, DB locks. |
| DB báo quá nhiều kết nối | Tổng pool của nhiều instance/ứng dụng vượt khả năng DB | Tính tổng cấu hình `maximumPoolSize` theo số instance; điều chỉnh ngân sách. |
| Tăng pool mà request không nhanh hơn | DB/SQL/lock là nút thắt | Dùng query plan, slow query log, metrics và kiểm tra transaction. |
| Connection đôi khi lỗi sau idle | DB/network cắt kết nối, timeout hạ tầng, validation/lifetime chưa phù hợp | Đối chiếu timeout DB, proxy, load balancer và `maxLifetime`/keepalive. |
| Có warning nghi leak | Connection bị giữ lâu hoặc chưa giải phóng; có thể là truy vấn lâu hợp lệ | Kiểm tra stack, ranh giới transaction và thời gian thực tế; leak detection chỉ cảnh báo. |
| Chỉnh `spring.datasource.hikari.*` mà không thấy tác dụng | Ứng dụng đã tự tạo `DriverManagerDataSource` hay loại Bean khác | Xác nhận lớp của Bean, điều kiện auto-configuration và nguồn cấu hình đang có hiệu lực. |

### Cạm bẫy về đóng kết nối

**Sai:** nghĩ pooled connection không cần `close()` vì “pool sẽ tự thu hồi”. Khi quên `close()`, connection vẫn bị đánh dấu active; cuối cùng pool có thể cạn. **Đúng:** luôn giải phóng connection logic bằng `close()` hoặc API quản lý của Spring.

**Sai:** nghĩ Hikari `close()` luôn phá hủy connection vật lý. **Đúng:** thường trả lại để tái sử dụng; pool có thể loại bỏ connection không còn đủ điều kiện.

**Sai:** dùng `try (Connection c = dataSource.getConnection())` bên trong một transaction Spring đang quản lý rồi giả định connection đó chắc chắn tham gia transaction hiện hành. **Đúng:** dùng `JdbcTemplate` hoặc `DataSourceUtils` để giữ tương thích với resource gắn transaction.

**Sai:** gọi một singleton `Connection` dùng chung giữa nhiều request để thay pool. **Đúng:** chia sẻ **`DataSource`** như Bean, mỗi luồng tác vụ mượn và trả `Connection` theo đúng vòng đời.

## 9. Câu hỏi tự kiểm tra

**1.** `DriverManagerDataSource` có triển khai interface `DataSource` không, và nó có tự pooling không?  
**Trả lời:** Có triển khai `DataSource` nhưng không tự pooling; mỗi lần phải tạo connection mới sẽ mở kết nối vật lý.

**2.** Với Hikari pool giới hạn 2 connection, cả hai đang bận, request thứ ba gọi `getConnection()` sẽ thế nào?  
**Trả lời:** Nó chờ connection được trả lại, tối đa tới `connectionTimeout`; nếu hết thời gian chờ thì phát sinh lỗi lấy connection. Không tự vượt giới hạn chỉ để phục vụ request đó.

**3.** Gọi `close()` trên một connection mượn từ pool có phải lúc nào cũng đóng socket tới DB không?  
**Trả lời:** Không. Nó thường trả handle cho pool; connection vật lý có thể tái sử dụng nếu còn hợp lệ.

**4.** Hai DAO cùng dùng `JdbcTemplate` trong một `@Transactional` thường cần hai connection vật lý?  
**Trả lời:** Không nhất thiết. Khi cùng DataSource và transaction được quản lý đúng, các thao tác có thể chia sẻ một connection gắn với transaction. Điều này đúng cả khi nguồn là direct hoặc pooled.

**5.** `maximumPoolSize=10` và có 6 instance ứng dụng thì DB luôn chỉ dùng tối đa 10 connection?  
**Trả lời:** Sai. Chỉ riêng sáu pool đã có thể tổng cộng tới 60 connection vật lý, ngoài những kết nối khác.

**6.** Có thể xác định pooling bằng việc kiểm tra hai `Connection` Java có `==` hay không?  
**Trả lời:** Không. Các đối tượng có thể là wrapper/proxy, không phản ánh trực tiếp identity của kết nối vật lý bên dưới.

## 10. Checklist trước khi đưa vào production

1. Xác nhận **loại `DataSource` thực sự** đang là Bean runtime, không chỉ nhìn dependency hoặc YAML.
2. Dùng pooled DataSource cho workload lặp lại; tách rõ quản lý pool với transaction và SQL.
3. Cấu hình ngân sách connection theo **DB limit × số instance**, chọn `maximumPoolSize` bằng đo đạc, tránh ước lượng chỉ từ số thread.
4. Thiết lập `connectionTimeout` hợp lý với SLA; đo cả thời gian đợi mượn và thời gian giữ connection.
5. Đóng/mượn kết nối đúng vòng đời; dùng `JdbcTemplate`/`DataSourceUtils` với transaction Spring.
6. Theo dõi active, idle, pending, timeout, query latency, transaction duration và lỗi DB.
7. Kiểm tra chính sách `maxLifetime`, idle, keepalive trước các timeout của DB/network.
8. Đảm bảo đóng pool khi ứng dụng dừng; bảo vệ credentials qua cơ chế cấu hình phù hợp.
9. Với integration/performance test, dùng cấu hình pool đại diện cho production khi cần kiểm chứng concurrency.

## Nguồn tham khảo chính thức

- [Spring Framework – Controlling Database Connections](https://docs.spring.io/spring-framework/reference/data-access/jdbc/connections.html): mục `DataSource`, `DriverManagerDataSource`, `DataSourceUtils` và transaction.
- [Spring Boot – SQL Databases / DataSource Configuration](https://docs.spring.io/spring-boot/reference/data/sql.html): lựa chọn pool và `spring.datasource.hikari.*` khi auto-configure.
- [HikariCP – Configuration README](https://github.com/brettwooldridge/HikariCP): `maximumPoolSize`, `connectionTimeout`, `minimumIdle`, `maxLifetime`, leak detection.

**Ghi nhớ:** `DriverManagerDataSource` tạo kết nối vật lý mới cho lần lấy kết nối cần thiết; pooled `DataSource` cung cấp connection logic từ tập connection vật lý được quản lý. Cả hai đều cung cấp interface `DataSource` cho `JdbcTemplate`; sự khác biệt quyết định hiệu năng tải lặp lại, giới hạn concurrency và trách nhiệm trả kết nối.
