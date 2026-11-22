# JDBC statement timeout và hỗ trợ của công cụ truy cập dữ liệu

## 1. Vấn đề: @Transactional(timeout=...) có tự ngắt mọi câu JDBC không?

Giả sử một chức năng tìm kiếm báo cáo trong Spring Framework có đoạn:

~~~java
@Transactional(readOnly = true, timeout = 20)
public Report loadReport() {
    // Truy vấn dữ liệu bằng JDBC, ORM, hoặc SQL thuần.
}
~~~

Đây là đoạn minh họa, **không phải chương trình biên dịch độc lập**. Chỉ nhìn `timeout = 20` chưa đủ để khẳng định *bất kỳ* câu SQL nào trong method cũng chắc chắn bị hủy đúng sau 20 giây. Spring cần một **transaction manager**, một **DataSource/Connection đang tham gia transaction** và một **công cụ truy cập dữ liệu biết áp timeout lên từng JDBC Statement**. Driver/database còn phải thực thi việc hủy câu lệnh theo khả năng của mình.

Trong ứng dụng JDBC sử dụng `DataSourceTransactionManager` hoặc `JdbcTransactionManager`, Spring hỗ trợ cách này thông qua:

- `@Transactional(timeout = N)`: khai báo **time budget cho transaction mới**, theo giây, không phải tự động cắt ngang mọi Java thread.
- `JdbcTemplate`: khi tạo `Statement`/`PreparedStatement`/`CallableStatement`, nó có thể áp **thời gian còn lại của transaction** lên JDBC statement.
- `DataSourceUtils.applyTransactionTimeout(statement, dataSource)`: hỗ trợ **code JDBC thủ công** gắn timeout transaction hiện tại lên một statement đã tạo.
- `Statement.setQueryTimeout(seconds)`: JDBC API cho phép driver nhận một thời gian tối đa thực thi statement, còn cách driver/DB dừng câu lệnh phụ thuộc implementation.

**Thông điệp:** transaction timeout là **chính sách trong transaction**, còn query timeout là **thiết lập trên mỗi JDBC statement**. Có quan hệ giữa chúng khi công cụ truy cập dữ liệu **chủ động chuyển đổi và áp dụng**. Không phải một annotation đơn lẻ tự động thay đổi tất cả câu JDBC do mọi library tạo ra.

### Sơ đồ luồng

~~~text
Caller gọi Spring bean qua transaction proxy
                      |
                      v
@Transactional(timeout = 20)
                      |
                      v
DataSourceTransactionManager bắt đầu JDBC transaction
và giữ thời hạn transaction trên resource đang tham gia
                      |
                      v
Service gọi JDBC:
    |
    +-- JdbcTemplate / NamedParameterJdbcTemplate
    |       |
    |       +-- tạo Statement qua Spring-managed connection
    |       +-- áp remaining transaction timeout
    |       +-- driver nhận setQueryTimeout(seconds)
    |
    +-- JDBC thủ công dùng DataSourceUtils
    |       |
    |       +-- getConnection(dataSource)
    |       +-- connection.prepareStatement(...)
    |       +-- applyTransactionTimeout(statement, dataSource)
    |       +-- driver nhận query timeout
    |
    +-- JDBC thủ công bỏ qua helper
            |
            +-- không được bảo đảm tự nhận transaction timeout
                      |
                      v
Database/driver có thực thi hủy, khóa chờ, retry?
                      |
                      v
Spring nhận thành công/SQLException rồi áp completion/rollback rules
~~~

Câu hỏi cần trả lời trong thực tế không chỉ là “transaction có timeout chưa?”, mà còn là **“SQL này được phát qua API nào, trên connection nào, statement có nhận query timeout không, và DB có thực thi nó không?”**

## 2. Phân biệt các loại timeout để không sửa sai tầng

Các chữ “timeout” xuất hiện ở nhiều tầng. Chúng **không đồng nghĩa**:

| Khái niệm | Đơn vị/đối tượng | Tác dụng chính | Không bảo đảm |
| --- | --- | --- | --- |
| `@Transactional(timeout = 20)` | Giây; **transaction mới** | Spring đặt thời hạn transaction khi manager hỗ trợ | Không tự ngắt mọi đoạn Java, HTTP, file I/O hoặc statement của thư viện bất kỳ. |
| `JdbcTemplate.setQueryTimeout(7)` | Giây; các JDBC statements do template tạo | Gửi query timeout cấu hình cho driver khi thực thi ngoài transaction có time budget | Không thay transaction timeout; có thể bị thời hạn transaction còn lại **ghi đè**. |
| `Statement.setQueryTimeout(3)` | Giây; **statement cụ thể** | Yêu cầu JDBC driver giới hạn thời gian thực thi statement | Hành vi cancel và exception chính xác tùy JDBC driver/DB. |
| JDBC `Connection.setNetworkTimeout(...)` | Mili giây; thao tác mạng của connection | Cấu hình network timeout khi driver hỗ trợ | Không tương đương thời gian chạy nghiệp vụ hay transaction toàn phần. |
| Connection-pool acquisition timeout | Thường mili giây; **chờ lấy connection** | Giới hạn việc chờ tài nguyên trong pool | Không giới hạn độ dài câu SQL sau khi có connection. |
| Database statement/lock timeout | Theo DB; statement hoặc chờ khóa | Engine trực tiếp áp giới hạn của mình | Không tự thay chính sách transaction Spring/JDBC. |
| HTTP client timeout | Theo client; network call | Giới hạn kết nối/đọc HTTP | Không rollback một tác động bên ngoài đã hoàn tất. |

Ví dụ: connection pool hết chỗ khiến request chờ 5 giây. `Statement.setQueryTimeout(3)` **không có tác dụng** trong lúc request còn chưa lấy được connection để tạo statement. Ngược lại, pool nhanh nhưng SQL chờ khóa lâu thì phải xem query timeout/lock timeout phía DB.

Trong JDBC, `Statement.setQueryTimeout(int seconds)` nhận số giây; giá trị `0` theo JDBC thường nghĩa là **không giới hạn query timeout**. Ngược lại, mặc định `JdbcTemplate` là `queryTimeout = -1`, biểu thị template không chủ động đặt timeout cố định ngoài transaction; các giá trị này **không được dùng thay thế cho nhau**.

### Đọc “timeout trong transaction” đúng nghĩa

`@Transactional(timeout=20)` không đặt một bộ hẹn giờ Java tiêu diệt thread sau đúng 20 giây. Với `DataSourceTransactionManager`, Spring giữ transaction deadline trên resource và giúp các câu SQL thực hiện qua công cụ transaction-aware nhận **thời gian còn lại**. Một số hoạt động có thể không kiểm tra time budget cho đến khi chuẩn bị/thi hành câu JDBC kế tiếp. Hiệu lực với JDBC statement vẫn phụ thuộc driver.

Điều này cũng giải thích tại sao `Thread.sleep(25000)` trong một method transactional không phải bài test chuẩn cho “driver tự cancel SQL”: trong lúc sleep không có statement nào để driver hủy. Thay vào đó, kiểm tra **statement setting** và nếu cần, dùng một SQL chậm có kiểm soát trên **đúng database đích** để kiểm thử cancellation.

## 3. Transaction timeout đi tới JDBC Statement bằng cơ chế nào?

### 3.1. DataSourceTransactionManager quản lý connection và deadline

Trong Spring JDBC, `DataSourceTransactionManager` quản lý một JDBC connection cho `DataSource` nhất định; trong transaction imperative thường ràng buộc connection với thread. Lời gọi qua `JdbcTemplate` lấy connection theo cơ chế `DataSourceUtils` nên dùng được connection đang tham gia transaction.

Khi transaction được tạo với timeout, Spring lưu thông tin thời hạn để các thao tác dữ liệu sau đó tra được **remaining transaction timeout**. Điều này khác với việc gọi `Connection.setNetworkTimeout`: transaction deadline là một chính sách thời gian của Spring resource holder, không phải chỉ một giá trị network timeout.

Nếu ứng dụng dùng **hai DataSource khác nhau**, hoặc service dùng một manager mà câu JDBC kết nối tới resource khác, việc truyền deadline không được bảo đảm. Tên method và annotation không thể thay thế việc phối hợp resource thực sự.

### 3.2. JdbcTemplate tự áp statement settings

Với các thao tác chuẩn của `JdbcTemplate`, Spring tạo JDBC statement và gọi mã áp statement settings trước khi chạy callback/execute SQL. Logic timeout dùng `DataSourceUtils.applyTimeout(statement, dataSource, configuredQueryTimeout)`.

Chính sách quan trọng:

1. **Không có transaction timeout hiện tại:** nếu template được đặt `queryTimeout = 7`, statement của template nhận yêu cầu timeout **7 giây**.
2. **Có transaction deadline:** **thời gian còn lại của transaction ghi đè** query timeout được cấu hình tại template; không nhất thiết lấy `min(7, remaining)`. Ví dụ transaction mới còn gần 20 giây có thể làm statement nhận query timeout gần 20, dù template được cấu hình 7.
3. **Transaction gần hết thời gian:** time budget giảm; các statement được tạo muộn nhận giá trị còn lại thấp hơn hoặc có thể gặp lỗi timeout khi deadline đã hết.
4. **Không nên so sánh giá trị chính xác tới từng mili giây:** API JDBC `setQueryTimeout` nhận **số giây nguyên**; giá trị “còn lại” bị ảnh hưởng bởi thời gian thực tế, làm tròn và độ trễ hệ thống.

~~~java
// Minh họa cấu hình ở mức bean; chưa phải project độc lập.
JdbcTemplate jdbc = new JdbcTemplate(dataSource);
jdbc.setQueryTimeout(7);
~~~

Bài lab bên dưới kiểm tra ngay bên trong `PreparedStatementCallback` rằng một statement tạo **ngoài transaction** nhận số 7, còn một statement tạo **trong transaction timeout=20** phản ánh thời gian còn lại của transaction.

**Không hiểu “transaction override template query timeout” thành “transaction luôn cancel chắc chắn sau 20 giây”.** Nó chứng minh code Spring chuyển yêu cầu xuống JDBC statement; việc driver hủy thực sự và DB phản ứng thế nào vẫn phải test riêng.

### 3.3. NamedParameterJdbcTemplate, JdbcClient và thư viện cấp cao

`NamedParameterJdbcTemplate` dùng `JdbcTemplate` phía dưới cho nhiều thao tác JDBC, nên khi được cấu hình đúng với cùng datasource và template, các statement do nó tạo hưởng cơ chế Spring JDBC tương ứng. `JdbcClient` trong Spring JDBC cũng sử dụng các template này cho cách gọi fluent thích hợp.

Ví dụ:

~~~java
// Minh họa: thực thi qua template Spring.
namedParameterJdbcTemplate.queryForObject(
    "SELECT COUNT(*) FROM orders WHERE status = :status",
    Map.of("status", "NEW"),
    Long.class
);
~~~

Đây là snippet không độc lập, yêu cầu bean và bảng `orders` có thật. Điểm cần nhớ: **thư viện nào tạo statement là thư viện phải xử lý timeout**. Khi bọc `JdbcTemplate` bằng API khác, hãy xác minh wrapper cuối cùng vẫn dùng đúng Spring-managed template/connection, thay vì tạo JDBC statement qua đường code riêng.

### 3.4. JDBC thủ công: DataSourceUtils.applyTransactionTimeout

Nếu code bắt buộc tự tạo `PreparedStatement`/`Statement`, Spring cung cấp helper:

~~~java
Connection connection = DataSourceUtils.getConnection(dataSource);
try (PreparedStatement statement =
         connection.prepareStatement("SELECT 1")) {
    DataSourceUtils.applyTransactionTimeout(statement, dataSource);
    try (ResultSet rs = statement.executeQuery()) {
        // Xử lý ResultSet.
    }
} finally {
    DataSourceUtils.releaseConnection(connection, dataSource);
}
~~~

Đây là **đoạn minh họa rút gọn**, cần imports/catch SQLException và context; code chạy được nằm trong `StatementProbe.java` ở phần 6. Dùng `DataSourceUtils.getConnection` thay cho lấy kết nối độc lập tùy ý; không gọi `connection.close()` trực tiếp đối với connection được Spring bind vào transaction. `DataSourceUtils.releaseConnection` sẽ xử lý đúng kết nối đang do transaction quản lý.

**Điểm rất dễ sai:** `DataSourceUtils.applyTransactionTimeout` cần **DataSource giống resource** mà transaction manager đang quản lý. Không truyền ngẫu nhiên một DataSource wrapper khác hoặc datasource tới database khác rồi chờ helper tìm thấy deadline hiện tại.

Với JDBC thủ công, tạo **mỗi statement mới** thì cần áp timeout lên statement đó. `applyTransactionTimeout` không phải thao tác cấu hình **vĩnh viễn trên toàn connection**.

### 3.5. Cơ chế TransactionAwareDataSourceProxy

`TransactionAwareDataSourceProxy` là một adapter cho code JDBC cũ chỉ biết gọi API `DataSource` chuẩn, giúp truy cập connection có awareness với Spring transaction. Spring tài liệu khuyến nghị trong code mới **ưu tiên JdbcTemplate/DataSourceUtils**. Đừng dựng thêm nhiều datasource proxies để sửa timeout khi code có thể chuyển thẳng sang template.

Sự có mặt của proxy không phải phép bảo đảm mọi JDBC library dùng statement timeout như mong muốn trong mọi trường hợp; cần kiểm tra đường tạo statement và behavior của wrapper cụ thể.

## 4. @Transactional(timeout) không phải cấu hình toàn cục cho method con

Một điều quan trọng khác là **timeout chỉ áp khi bắt đầu transaction mới** theo transaction propagation.

~~~java
@Service
class OuterService {
    private final InnerService inner;

    OuterService(InnerService inner) {
        this.inner = inner;
    }

    @Transactional(timeout = 60)
    public void outer() {
        inner.inner();
    }
}

@Service
class InnerService {
    @Transactional(
        propagation = Propagation.REQUIRED,
        timeout = 5
    )
    public void inner() {
        // Tham gia outer transaction, không reset deadline xuống 5 giây.
    }
}
~~~

Đây là **mã minh họa**, chưa đầy đủ imports. Khi hai Spring beans được gọi qua proxy, `inner` dùng `REQUIRED` nên tham gia physical transaction outer. **Deadline của outer được giữ nguyên**, thay vì inner đặt lại còn 5 giây.

So sánh:

| Gọi method inner | Trạng thái transaction trước lời gọi | Timeout nào có cơ hội áp? |
| --- | --- | --- |
| `REQUIRED(timeout=5)` gọi độc lập | Chưa có transaction | Inner mở transaction mới và yêu cầu 5 giây |
| `REQUIRED(timeout=5)` gọi từ `outer(timeout=60)` | Đã có physical transaction | Dùng time budget của outer 60 giây còn lại, không reset thành 5 |
| `REQUIRES_NEW(timeout=5)` gọi từ outer | Đã có outer transaction | Inner mở transaction độc lập, có deadline riêng 5 giây |
| `this.inner()` trong cùng target | Có thể có transaction từ outer hoặc không | Annotation inner thường **bypass proxy** nên không tạo timeout scope như bạn nghĩ |

`REQUIRES_NEW` không đơn thuần là cách “ép query nhanh hơn”: nó mở transaction độc lập, có thể commit dù outer rollback, cần connection khác và có nguy cơ chờ khóa/pool exhaustion. Khi cần một query cụ thể có timeout thấp hơn, có thể cân nhắc cấu hình **statement/query timeout** thích hợp thay vì thay propagation và ý nghĩa commit của nghiệp vụ.

### Inner time budget vs physical transaction deadline

Có thể có nhiều logical scopes `@Transactional` nhưng chỉ một physical transaction `REQUIRED`. Transaction manager giữ deadline của physical transaction; không tạo đồng hồ mới cho mỗi inner method được gọi. Vì thế đo deadline bằng cách xem chú thích trên method inner là không đủ.

Nếu inner exception thoát qua proxy, rollback rules vẫn có thể tác động lên transaction chung; timeout và rollback policy là hai khía cạnh khác nhau. Một query timeout có thể ném `SQLException` được dịch thành exception Spring, nhưng việc transaction có rollback hay không còn tùy rule, transaction state và DB có cho phép tiếp tục sau lỗi hay không.

## 5. Hỗ trợ thật sự của driver/database và các kiểu lỗi

### 5.1. JDBC query timeout là *yêu cầu cancel*

Theo JDBC, `Statement.setQueryTimeout(int seconds)` đưa ra giới hạn thời gian cho quá trình statement chạy. Khi driver/DB hỗ trợ, việc quá hạn có thể gây `SQLTimeoutException` hoặc một SQLException tương ứng từ driver. Tuy nhiên:

- Driver có thể kiểm tra timeout tại nhiều điểm khác nhau và không hứa chính xác tới mili giây.
- Một số engine tính thời gian đợi khóa, server statement execution hoặc network khác nhau.
- Việc gửi yêu cầu cancel không đồng nghĩa server chắc chắn dừng đúng tức thì.
- Nếu statement đã thực hiện một phần thay đổi hoặc transaction bị đánh dấu lỗi, cần xác định rollback/cancel semantics của database.
- `Statement.cancel()` cũng chỉ là API yêu cầu hủy; kết quả phụ thuộc driver/engine.

Không nên hardcode “cứ timeout là luôn nhận đúng `SQLTimeoutException`” trên mọi DB. Spring JDBC có thể dịch `SQLException` thành một subclass của `DataAccessException` (chẳng hạn `QueryTimeoutException` ở trường hợp được nhận diện); loại exception chính xác phụ thuộc SQL state, error code và driver.

### 5.2. Statement timeout không thể thay toàn bộ time budget nghiệp vụ

Giả sử một service:

~~~text
BEGIN TRANSACTION timeout=20s
  |
  +-- SELECT nhanh: 1s
  +-- Gọi HTTP ngoài database: 15s
  +-- Lắp ghép dữ liệu Java: 3s
  +-- SELECT thứ hai: bắt đầu khi chỉ còn ~1s
  |
  +-- Transaction deadline có thể đã gần/hết khi tạo statement mới
  +-- Driver chỉ hủy SQL nếu được áp/công cụ hỗ trợ
COMMIT hoặc ROLLBACK theo trạng thái thực tế
~~~

Với các thao tác HTTP, file I/O, CPU, thread pool, queue hoặc đợi connection, phải đặt giới hạn ở **đúng tầng**, không trông chờ `@Transactional(timeout=20)` tự áp lên chúng. Giữ transaction mở qua network call cũng có thể giữ lock/connection lâu không cần thiết.

### 5.3. Database timeout, lock timeout, network timeout

Ví dụ PostgreSQL có tham số server `statement_timeout` và `lock_timeout`; chúng do database quản lý và có tác động riêng so với JDBC `Statement.setQueryTimeout`. MySQL, SQL Server, Oracle và H2 không nhất thiết cung cấp cùng tên hoặc semantics. Chỉ đưa ví dụ này như minh họa, không sao chép nguyên câu `SET statement_timeout` sang mọi DB.

`Connection.setNetworkTimeout(executor, millis)` thuộc API connection/network, đơn vị mili giây, có hợp đồng khác query timeout. Còn HikariCP `connectionTimeout` là thời gian tối đa chờ mượn connection từ pool. Đây là ba lớp riêng; không dùng cùng một giá trị để che giấu lỗi tầng khác.

## 6. Lab đầy đủ: Java 17, Spring Boot, JDBC và H2

Bài lab sử dụng **Spring Boot 3.5.0**, Java 17+, Spring JDBC, H2 in-memory, JUnit 5. Nó **không** chạy câu SQL ngủ/khóa chờ để cố tình timeout thật; thay vào đó kiểm tra giá trị `Statement.getQueryTimeout()` mà driver H2 báo lại **ngay trước lúc thực thi một câu SELECT 1**. Cách này ít phụ thuộc thời gian và thể hiện rõ công cụ JDBC đã áp dụng setting nào.

Đặc biệt, lab có hai tình huống:

1. Cấu hình template query timeout cố định 7 giây khi không có transaction deadline.
2. Transaction timeout 20 giây **ghi đè query timeout của template** bằng thời gian còn lại.
3. JDBC thủ công tự đặt 3 giây, nếu không gọi helper thì giữ setting 3 giây dù có transaction.
4. JDBC thủ công gọi `DataSourceUtils.applyTransactionTimeout` được Spring đồng bộ với time budget transaction.
5. Inner `REQUIRED(timeout=5)` gọi độc lập tạo deadline 5 giây.
6. Inner `REQUIRED(timeout=5)` tham gia outer `timeout=60` không thay deadline thành 5 giây.

### 6.1. Cấu trúc dự án

~~~text
jdbc-statement-timeout-lab/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/timeoutlab/
    │   │   ├── TimeoutLabApplication.java
    │   │   ├── StatementProbe.java
    │   │   ├── TimeoutCasesService.java
    │   │   ├── ShortTimeoutService.java
    │   │   └── OuterTimeoutService.java
    │   └── resources/
    │       └── application.properties
    └── test/
        └── java/com/example/timeoutlab/
            └── StatementTimeoutTest.java
~~~

Bài lab chỉ cần `SELECT 1` nên **không cần schema.sql** hoặc dữ liệu khởi tạo. Code Java thuộc package `com.example.timeoutlab` ở tất cả các file.

### 6.2. pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>jdbc-statement-timeout-lab</artifactId>
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
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <scope>runtime</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
~~~

### 6.3. application.properties

~~~properties
spring.datasource.url=jdbc:h2:mem:timeout_lab;DB_CLOSE_DELAY=-1
spring.datasource.driver-class-name=org.h2.Driver
spring.datasource.username=sa
spring.datasource.password=
~~~

H2 là database thử nghiệm. `DB_CLOSE_DELAY=-1` giữ DB tồn tại tới khi JVM kết thúc; bài này không dựa trên dữ liệu lâu dài. JDBC settings được thử với H2, không tuyên bố mọi driver sẽ phản hồi tương tự.

### 6.4. TimeoutLabApplication.java: cùng DataSource và transaction manager

~~~java
package com.example.timeoutlab;

import javax.sql.DataSource;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.transaction.PlatformTransactionManager;

@SpringBootApplication
public class TimeoutLabApplication {
    public static void main(String[] args) {
        SpringApplication.run(TimeoutLabApplication.class, args);
    }

    @Bean
    public PlatformTransactionManager transactionManager(
            DataSource dataSource) {
        return new DataSourceTransactionManager(dataSource);
    }

    @Bean
    public JdbcTemplate jdbcTemplate(DataSource dataSource) {
        JdbcTemplate jdbc = new JdbcTemplate(dataSource);
        jdbc.setQueryTimeout(7);
        return jdbc;
    }
}
~~~

Ở đây khai báo **một transaction manager** cho `DataSource` H2 và một `JdbcTemplate` dùng **chính DataSource ấy**. `JdbcTemplate.setQueryTimeout(7)` cấu hình template cho statement ngoài transaction deadline. Bên trong transaction có timeout, Spring `DataSourceUtils.applyTimeout` dùng thời gian còn lại của transaction và có thể ghi đè 7.

Chú ý: nếu dùng Spring Boot auto-config `JdbcTemplate` thay vì bean tự khai báo, có thể cấu hình query timeout bằng properties theo hỗ trợ của Boot phiên bản tương ứng; ở lab chọn Java bean cho dễ kiểm tra.

### 6.5. StatementProbe.java: quan sát statement đang được thực thi

~~~java
package com.example.timeoutlab;

import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Statement;
import java.util.Objects;

import javax.sql.DataSource;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.PreparedStatementCallback;
import org.springframework.jdbc.datasource.DataSourceUtils;
import org.springframework.stereotype.Component;

@Component
public class StatementProbe {
    private final JdbcTemplate jdbc;
    private final DataSource dataSource;

    public StatementProbe(JdbcTemplate jdbc, DataSource dataSource) {
        this.jdbc = jdbc;
        this.dataSource = dataSource;
    }

    // JdbcTemplate áp statement settings trước khi gọi callback này.
    public int templateQueryTimeout() {
        Integer seconds = jdbc.execute(
            "SELECT 1",
            (PreparedStatementCallback<Integer>) statement -> {
                int configured = statement.getQueryTimeout();
                try (ResultSet rs = statement.executeQuery()) {
                    if (!rs.next()) {
                        throw new SQLException("SELECT 1 returned no row");
                    }
                }
                return configured;
            }
        );
        return Objects.requireNonNull(seconds, "No timeout returned");
    }

    // Code JDBC thủ công: có thể chọn gọi helper hoặc không.
    public int manualStatement(boolean applySpringTimeout) {
        Connection connection = DataSourceUtils.getConnection(dataSource);
        try (Statement statement = connection.createStatement()) {
            statement.setQueryTimeout(3);

            if (applySpringTimeout) {
                DataSourceUtils.applyTransactionTimeout(
                    statement, dataSource
                );
            }

            int configured = statement.getQueryTimeout();

            try (ResultSet rs = statement.executeQuery("SELECT 1")) {
                if (!rs.next()) {
                    throw new SQLException("SELECT 1 returned no row");
                }
            }
            return configured;
        } catch (SQLException ex) {
            throw new IllegalStateException(
                "JDBC statement inspection failed", ex
            );
        } finally {
            DataSourceUtils.releaseConnection(connection, dataSource);
        }
    }
}
~~~

Đây là class Java 17 hoàn chỉnh; `PreparedStatement` import có thể bỏ vì callback đã nhận statement đúng kiểu, nhưng một import thừa không làm lỗi biên dịch. Phần `templateQueryTimeout()` đọc `getQueryTimeout()` **bên trong callback của JdbcTemplate**, sau bước `applyStatementSettings` và trước khi thực thi `SELECT 1`.

`manualStatement(...)` dùng `DataSourceUtils.getConnection`/`releaseConnection` để lấy connection transaction-aware. Tạo JDBC `Statement` rồi đặt 3 giây bằng JDBC chuẩn, sau đó **chỉ khi được yêu cầu** mới gọi `applyTransactionTimeout` của Spring. Như vậy có thể so sánh cùng raw JDBC code với/không với cầu nối của Spring, thay vì nhầm lẫn “đã dùng connection Spring là statement tự có timeout”.

**Quan trọng:** việc áp timeout cần được thực hiện trên statement **mỗi lần tạo mới**. Một `DataSourceUtils.getConnection` đúng resource giải quyết việc **tham gia transaction**, nhưng không có nghĩa mọi statement tạo bằng `connection.createStatement` sẽ tự nhận deadline nếu không dùng helper hoặc wrapper hỗ trợ.

### 6.6. TimeoutCasesService.java: các phép thử transaction thông thường

~~~java
package com.example.timeoutlab;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class TimeoutCasesService {
    private final StatementProbe probe;

    public TimeoutCasesService(StatementProbe probe) {
        this.probe = probe;
    }

    // Không có transaction từ service. Template dùng 7 giây.
    public int templateOutsideTransaction() {
        return probe.templateQueryTimeout();
    }

    @Transactional(timeout = 20, readOnly = true)
    public int templateInsideTransaction() {
        return probe.templateQueryTimeout();
    }

    // Cùng transaction 20 giây, nhưng raw Statement giữ 3 giây.
    @Transactional(timeout = 20)
    public int manualWithoutSpringHelper() {
        return probe.manualStatement(false);
    }

    // Cùng transaction, helper chuyển remaining time sang Statement.
    @Transactional(timeout = 20)
    public int manualWithSpringHelper() {
        return probe.manualStatement(true);
    }
}
~~~

`StatementProbe` không tự đặt `@Transactional`; các method của nó được chạy trong phạm vi do `TimeoutCasesService` đã mở. Vì caller (test) gọi public method của `TimeoutCasesService` qua Spring bean proxy, các `@Transactional` ở service có hiệu lực. Không dùng `new TimeoutCasesService(...)` trong test.

### 6.7. ShortTimeoutService.java và OuterTimeoutService.java: mô tả tham gia transaction

Tệp `src/main/java/com/example/timeoutlab/ShortTimeoutService.java`:

~~~java
package com.example.timeoutlab;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.interceptor.TransactionAspectSupport;

@Service
public class ShortTimeoutService {
    public record TimeoutView(
        boolean newTransaction,
        int queryTimeoutSeconds
    ) {}

    private final StatementProbe probe;

    public ShortTimeoutService(StatementProbe probe) {
        this.probe = probe;
    }

    @Transactional(
        propagation = Propagation.REQUIRED,
        timeout = 5
    )
    public TimeoutView inspect() {
        boolean newTransaction = TransactionAspectSupport
            .currentTransactionStatus()
            .isNewTransaction();

        return new TimeoutView(
            newTransaction,
            probe.templateQueryTimeout()
        );
    }
}
~~~

Tệp `src/main/java/com/example/timeoutlab/OuterTimeoutService.java`:

~~~java
package com.example.timeoutlab;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OuterTimeoutService {
    private final ShortTimeoutService inner;

    public OuterTimeoutService(ShortTimeoutService inner) {
        this.inner = inner;
    }

    @Transactional(timeout = 60)
    public ShortTimeoutService.TimeoutView callInnerRequired() {
        return inner.inspect();
    }
}
~~~

Khi test gọi `ShortTimeoutService.inspect()` **độc lập**, `REQUIRED(timeout=5)` phải bắt đầu một transaction mới, `newTransaction=true`, và statement qua JdbcTemplate nhận khoảng thời gian còn lại của 5 giây (thường từ 1 đến 5 nếu SQL bắt đầu sớm).

Khi test gọi `OuterTimeoutService.callInnerRequired()`, outer mở deadline **60 giây**, rồi gọi inner `REQUIRED(timeout=5)`. Vì inner **tham gia** transaction ngoài, `newTransaction=false`, query timeout của statement theo outer **remaining time**, thường lớn hơn 5 giây nếu không có trì hoãn bất thường. Đây là phép thử khác biệt giữa **annotation khai báo tại inner** và **timeout vật lý thực đang được Spring quản lý**.

Các test này không gọi `Thread.sleep`; chúng kiểm tra timeout đã được áp lên statement, không tạo ngẫu nhiên một lệnh SQL chậm.

### 6.8. StatementTimeoutTest.java: sáu integration tests

~~~java
package com.example.timeoutlab;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest
class StatementTimeoutTest {
    @Autowired
    private TimeoutCasesService cases;

    @Autowired
    private ShortTimeoutService shortService;

    @Autowired
    private OuterTimeoutService outer;

    private static void between(int value, int min, int max) {
        assertTrue(
            value >= min && value <= max,
            "Expected timeout in [" + min + ", " + max
                + "], actual=" + value
        );
    }

    @Test
    void templateWithoutTransactionUsesSevenSeconds() {
        assertEquals(7, cases.templateOutsideTransaction());
    }

    @Test
    void transactionBudgetOverridesConfiguredTemplateTimeout() {
        int observed = cases.templateInsideTransaction();
        between(observed, 1, 20);
    }

    @Test
    void manuallyConfiguredStatementStaysAtThreeWithoutBridge() {
        assertEquals(3, cases.manualWithoutSpringHelper());
    }

    @Test
    void manualStatementWithSpringBridgeReceivesTransactionTime() {
        int observed = cases.manualWithSpringHelper();
        between(observed, 1, 20);
    }

    @Test
    void standaloneRequiredUsesItsOwnFiveSecondDeadline() {
        ShortTimeoutService.TimeoutView result =
            shortService.inspect();

        assertTrue(result.newTransaction());
        between(result.queryTimeoutSeconds(), 1, 5);
    }

    @Test
    void innerRequiredDoesNotReplaceOuterSixtySecondDeadline() {
        ShortTimeoutService.TimeoutView result =
            outer.callInnerRequired();

        assertFalse(result.newTransaction());
        between(result.queryTimeoutSeconds(), 1, 60);
        // Với máy chạy bình thường, do outer vừa mở 60 giây,
        // giá trị quan sát thường lớn hơn 5 giây.
    }
}
~~~

Cần lưu ý một điểm đo đạc: `queryTimeoutSeconds` là **giá trị còn lại khi statement được tạo**, không phải một hằng số luôn đúng bằng 20, 5 hoặc 60. Vì vậy test chỉ khẳng định trong khoảng, **không buộc** giá trị bằng chính xác full deadline. Nếu môi trường chậm bất thường khiến time budget đã hết trước khi query chạy, Spring có thể ném lỗi timeout; đó là lý do một test thời gian sống thực cần thiết kế riêng và không lấy kết quả sleep làm chân lý.

Trong test cuối, `newTransaction=false` trực tiếp xác nhận inner đang tham gia outer. Kết hợp với lý giải Spring về propagation và `getQueryTimeout()`, khi hoạt động không bị trì hoãn, statement nhận **remaining outer deadline** thay vì inner 5 giây. Nếu muốn kiểm tra số giây cụ thể bằng assertion cứng, cần quản lý scheduler và cơ chế đồng hồ thử nghiệm kỹ hơn.

**Không gắn `@Transactional` trên test class.** Nếu Spring Test tự mở transaction ngoài, `templateOutsideTransaction()` và `shortService.inspect()` sẽ không còn những tình huống standalone như dự định; đó là một trong những bẫy phổ biến nhất khi kiểm thử propagation/timeout.

### 6.9. Chạy dự án

Yêu cầu JDK 17+, Maven 3.9+ và khả năng tải dependencies:

~~~bash
java -version
mvn -version
mvn test
~~~

Với Spring/H2 driver tương thích như mã đã chọn, kỳ vọng **6 tests pass, 0 failures, 0 errors**. Đây là **kết quả dự kiến từ mã**, không phải log của một lần chạy thật được thực hiện trong bài này. Các assertions test sự chuyển **setting** xuống JDBC, không cố tạo SQL cancellation. Trên database đích, nếu cần chắc chắn statement quá thời gian bị cancel, phải làm integration test riêng có câu SQL chậm/lock wait đã được kiểm soát.

### 6.10. Điều chứng minh và không chứng minh

| Test | Được chứng minh trong môi trường H2 | Chưa chứng minh |
| --- | --- | --- |
| Template không có transaction | Statement do template tạo có `getQueryTimeout=7` | Mọi SQL đều bị driver hủy đúng giây thứ 7. |
| Template trong transaction=20 | Statement đọc được một time budget trong khoảng 1–20 từ transaction | Java thread tự bị interrupt đúng giây 20. |
| Raw JDBC không dùng bridge | Statement vẫn có setting thủ công 3 giây | Spring đã áp deadline 20 vào statement ấy. |
| Raw JDBC có bridge | Spring helper thay setting bằng remaining transaction timeout | Timeout của một DB khác hoạt động y hệt H2. |
| Inner REQUIRED độc lập=5 | Có physical transaction mới và statement nhận timeout tối đa 5 giây | Timeout 5 áp cho mọi network call khác. |
| Inner REQUIRED tham gia outer=60 | Inner không mở physical transaction mới | Inner `timeout=5` có thể đổi deadline outer (không). |

Mục tiêu của bài lab **không phải chứng minh tốc độ của `SELECT 1`**, mà là chứng minh **điểm nối Spring transaction timeout → JDBC statement setting**.

## 7. Khi nào Spring không tự áp query timeout?

### 7.1. Dùng một thư viện tự quản lý JDBC Statement

Có những thư viện tạo statement bằng connection riêng hoặc bỏ qua các helper Spring. Dù method bên ngoài có `@Transactional(timeout=...)`, library ấy có thể **không tham gia đúng connection** hoặc không gọi `setQueryTimeout`. Muốn đảm bảo, cần xem cách thư viện tích hợp transaction và statement configuration, không suy luận từ tên thư viện.

### 7.2. Dùng `DataSource.getConnection` trực tiếp, không transaction-aware

Trong code JDBC imperative do Spring quản lý, nên ưu tiên `JdbcTemplate` hoặc `DataSourceUtils.getConnection`. Gọi `dataSource.getConnection()` trực tiếp từ một pool gốc có thể mượn **một connection khác** không bind với Spring transaction hiện tại; query timeout/commit/rollback có thể bị tách khỏi transaction nghiệp vụ.

Nếu phải truyền `DataSource` cho legacy code, `TransactionAwareDataSourceProxy` có thể là giải pháp tích hợp, nhưng hãy xác minh khả năng API và thời gian mà wrapper áp dụng. Không tự đóng connection Spring-bound bằng `connection.close()`.

### 7.3. Tạo statement bằng tay nhưng quên áp timeout

`DataSourceUtils.getConnection` giúp lấy connection đúng; nó không tự đặt timeout lên mọi `Statement` bạn gọi từ connection ấy. Sau `prepareStatement(...)` hoặc `createStatement()`, cần áp `DataSourceUtils.applyTransactionTimeout` nếu muốn Spring chuyển deadline vào statement theo cơ chế này.

### 7.4. Dùng JPA/Hibernate hoặc R2DBC

Trong JPA/Hibernate, Spring `@Transactional(timeout=...)` có thể được chuyển qua provider/dialect hoặc API query timeout theo cơ chế khác; kết quả còn phụ thuộc `JpaTransactionManager`, `EntityManager`, các query hints/provider settings và database. Không được lấy code `JdbcTemplate` làm bằng chứng một JPA query native/JPQL chắc chắn có cùng query timeout.

Reactive `R2dbcTransactionManager` dùng resource và context khác JDBC thread-bound. Nó không tạo `java.sql.Statement`, do đó `DataSourceUtils.applyTransactionTimeout` không phải API để quản lý query timeout của reactive driver.

### 7.5. Transaction của inner không phải transaction mới

`@Transactional(timeout=2)` trong method `REQUIRED` thường không áp nếu outer transaction đã tồn tại. Đặt timeout ở **transaction owner** hoặc cấu hình statement-level trong phạm vi phù hợp. Bật `REQUIRES_NEW` chỉ vì muốn câu SQL timeout ngắn hơn có thể gây commit độc lập ngoài ý muốn.

## 8. Khi query timeout thật sự xảy ra: ứng xử thế nào?

Giả sử JDBC driver đã cancel một câu truy vấn, hoặc server trả về lỗi timeout. Các bước cần xử lý:

1. **Ghi nhận lỗi và root cause**: phân biệt JDBC `SQLTimeoutException`, exception được Spring JDBC dịch, lock wait timeout, serialization failure, server connection loss hoặc timeout của pool.
2. **Xác định transaction còn sử dụng được không**: một số database đưa transaction vào trạng thái lỗi sau statement failure; không tiếp tục ghi SQL rồi commit như không có gì.
3. **Quyết định rollback theo nghiệp vụ**: `@Transactional` mặc định rollback cho `RuntimeException` và `Error`; `DataAccessException` của Spring thuộc loại runtime. Nếu code bắt/nuốt lỗi và trả về bình thường, interceptor có thể không tự rollback trừ khi transaction đã rollback-only.
4. **Đừng tự động retry vô hạn**: câu SQL chậm do mất index, deadlock hoặc contention có thể lặp lại. Retry toàn operation cần idempotency và backoff phù hợp, quan sát trạng thái đã commit.
5. **Đặt timeout ở đúng tầng**: truy vấn chậm do execution plan cần index/tối ưu SQL; thiếu connection do pool cần tuning; lock contention cần transaction/locking strategy.

Ví dụ lỗi trong controller có thể biến thành HTTP 504 khi upstream mất thời gian, nhưng **HTTP 504 không nói database transaction chắc chắn rollback**. Nếu request bị hủy sau khi DB đã commit, client phải xử lý khả năng retry trùng bằng request ID/idempotency.

### Vì sao không nên trông chờ `Thread.interrupt()`?

JDBC driver thường thực hiện query cancellation bằng cơ chế DB/driver riêng. `@Transactional(timeout)` không phát lệnh `Thread.interrupt` cho mọi đoạn Java của method. Chạy tác vụ chậm CPU hoặc sleep không đồng nghĩa statement deadline đang được kiểm tra. Hãy đo timeout tại statement và kiểm thử bằng query/lock thực sự nếu cần.

## 9. Checklist triển khai trong dự án thật

Trước khi coi timeout là cơ chế bảo vệ production:

1. **Xác định transaction owner**: method nào mở physical transaction, timeout nào khai báo ở đó?
2. **Xác nhận interceptor/proxy**: có self-invocation, bean được `new` thủ công, hoặc lời gọi ở thread khác không?
3. **Xác định manager và resource**: `DataSourceTransactionManager` hay manager khác, cùng `DataSource` với code JDBC không?
4. **Phân loại JDBC API**: `JdbcTemplate`/`NamedParameterJdbcTemplate`, ORM, raw JDBC hay third-party library?
5. **Xác định statement đã được áp gì**: `JdbcTemplate.getQueryTimeout` là cấu hình template; `Statement.getQueryTimeout` trên statement thực thi mới cho biết JDBC setting cuối cùng.
6. **Phân biệt transaction override**: với transaction deadline, `JdbcTemplate.setQueryTimeout(7)` có thể bị **remaining transaction timeout** ghi đè.
7. **Nếu dùng raw JDBC**: lấy connection qua `DataSourceUtils` và áp timeout cho từng statement cần thiết.
8. **Test driver/database đích**: thử statement chậm và lock wait có kiểm soát; ghi nhận exception type/SQLState, rollback và độ trễ cancel.
9. **Kiểm tra timeout khác**: pool acquisition, network, DB statement/lock timeout, HTTP timeout; không trộn đơn vị giây/mili giây.
10. **Thiết kế retry và quan sát**: metrics duration/timeout count, logs có correlation ID, rollback, index/SQL plan và idempotency.

Hãy lưu ý chi phí vận hành: timeout quá ngắn sẽ tạo lỗi giả khi DB tải cao; timeout quá dài giữ lock/connection lâu. Thông số nên dựa trên latency SLO, khả năng hệ thống và mục tiêu nghiệp vụ, không dùng cùng một con số tùy ý cho mọi loại truy vấn.

## 10. Câu hỏi tự kiểm tra

1. **`@Transactional(timeout=20)` có tự interrupt Java thread sau 20 giây không?** — Không; đây là transaction time budget được manager/resource thực hiện theo khả năng, thường chuyển thành JDBC statement query timeout khi dùng công cụ phù hợp.
2. **`JdbcTemplate.setQueryTimeout(7)` có bị transaction timeout=20 override không?** — Có; Spring tài liệu nêu remaining transaction timeout ghi đè template query timeout nếu transaction có deadline.
3. **JDBC statement timeout được gắn bằng API gì?** — `Statement.setQueryTimeout(int seconds)`, theo khả năng driver.
4. **Raw JDBC đã gọi `DataSourceUtils.getConnection` có tự nhận statement timeout không?** — Không bảo đảm; cần `DataSourceUtils.applyTransactionTimeout` lên mỗi statement nếu muốn cơ chế Spring áp deadline.
5. **Đơn vị của `Statement.setQueryTimeout` là gì?** — Giây nguyên; JDBC `0` thường nghĩa là không có giới hạn riêng từ API này.
6. **`@Transactional(timeout=5)` của inner REQUIRED khi outer timeout=60 có reset deadline không?** — Thường không; inner tham gia physical transaction outer đã mở.
7. **Query timeout bằng 7 giây có giống connection-pool timeout 7 giây không?** — Không: một cái giới hạn statement execution, cái kia giới hạn thời gian chờ mượn connection.
8. **Nếu driver hủy SQL sau timeout, mọi database có trả đúng `SQLTimeoutException` không?** — Không; driver/engine và exception translation của Spring có thể khác.
9. **Tại sao test trong bài không dùng `Thread.sleep(25000)`?** — Vì sleep đo thời gian Java, không chứng minh statement đã nhận `setQueryTimeout` hoặc server thực sự hủy SQL.
10. **H2 trả `getQueryTimeout=20` có đủ đảm bảo PostgreSQL hủy SQL như vậy không?** — Không; cần test database/driver production và query thực sự.
11. **Read-only liên quan gì?** — `readOnly=true` có thể giúp tối ưu nhưng không tự áp statement timeout và không thay quyền database.
12. **Nếu code nuốt exception timeout rồi trả bình thường, có chắc Spring rollback không?** — Không; cần xem rollback-only state, exception propagation và rollback rules.
13. **`JdbcClient` dùng JDBC template hạ tầng có thể hưởng timeout không?** — Có khi thực sự dùng cùng Spring-managed templates/resource; vẫn cần xác minh path và settings.
14. **Tại sao phải dùng cùng DataSource ở manager và helper?** — Để tìm đúng resource holder/deadline của transaction đang chạy.

## 11. Tổng kết

**JDBC statement timeout không tự động xuất hiện trên mọi câu SQL chỉ vì method có `@Transactional(timeout=...)`.** Trong Spring JDBC, cơ chế đúng là:

~~~text
@Transactional(timeout = N) trên method mở transaction mới
              |
              v
Transaction manager / DataSource cùng resource
              |
              v
Statement được tạo bởi JdbcTemplate
HOẶC code raw JDBC gọi DataSourceUtils.applyTransactionTimeout
              |
              v
JDBC Statement.setQueryTimeout(remaining seconds)
              |
              v
Driver/DB thực thi theo khả năng, trả kết quả hoặc exception
~~~

Một thiết kế đúng cần **tách transaction deadline khỏi query timeout**, **đặt giới hạn đúng tầng**, **đảm bảo các SQL sử dụng transaction-aware tooling** và **kiểm tra behavior trên driver/database mục tiêu**.

### Tài liệu tham khảo chính thức

- [Spring Framework — Controlling Database Connections](https://docs.spring.io/spring-framework/reference/data-access/jdbc/connections.html)
- [Spring Framework — JDBC Core Classes](https://docs.spring.io/spring-framework/reference/data-access/jdbc/core.html)
- [Spring Framework — DataSourceUtils API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jdbc/datasource/DataSourceUtils.html)
- [Spring Framework — JdbcTemplate API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jdbc/core/JdbcTemplate.html)
- [Spring Framework — @Transactional API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/transaction/annotation/Transactional.html)
- [Java SE 17 — Statement.setQueryTimeout](https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/Statement.html#setQueryTimeout(int))
