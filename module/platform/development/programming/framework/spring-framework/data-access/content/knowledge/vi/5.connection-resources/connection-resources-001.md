# Chuỗi tài nguyên Connection, Statement và ResultSet trong JDBC và Spring Framework

> **Mục tiêu:** Hiểu chính xác ba tài nguyên JDBC được tạo ra, phụ thuộc và giải phóng như thế nào; đọc được luồng truy vấn từ `DataSource`/`Connection` đến `Statement` và `ResultSet`; viết mã Java 17+ không rò rỉ connection/cursor; và biết khi nào Spring `JdbcTemplate` hoặc transaction manager sở hữu vòng đời tài nguyên thay cho ứng dụng.

## 1. Bức tranh tổng thể: ba mắt xích, ba nhiệm vụ

Một thao tác JDBC truyền thống thường đi theo chuỗi:

```text
DataSource / DriverManager
       |
       | getConnection(...)
       v
Connection                  <-- phiên làm việc JDBC với database
       |
       | createStatement()
       | prepareStatement(sql)
       | prepareCall(sql)
       v
Statement                   <-- câu lệnh SQL và tham số/thực thi
  |- Statement
  |- PreparedStatement
  '- CallableStatement
       |
       | executeQuery(...)
       v
ResultSet                   <-- con trỏ đọc các hàng kết quả
       |
       | next(), getString(), getLong(), ...
       v
Dữ liệu Java (record, DTO, đối tượng domain)
       |
       v
close ResultSet -> close Statement -> close Connection
```

**Connection** đại diện cho phiên JDBC và trạng thái liên quan như auto-commit, transaction, isolation. **Statement** thực thi SQL bằng connection đó. **ResultSet** là đối tượng kết quả gắn với statement đã sinh ra nó; thường chứa cursor, metadata và tài nguyên phía driver/database. Dữ liệu Java đã được ánh xạ thành record/DTO thường có thể tồn tại sau khi các tài nguyên JDBC đóng.

| Đối tượng | Nguồn tạo | Vai trò | Ai phải quản lý đóng khi dùng JDBC thuần? |
| --- | --- | --- | --- |
| `Connection` | `dataSource.getConnection()` hoặc `DriverManager.getConnection(...)` | Giao tiếp với DB, giữ transaction state và tạo statement | Code đã mượn/tạo connection; đóng khi xong, trừ khi container/framework đang sở hữu |
| `Statement` | `connection.createStatement()` | Thực thi SQL tĩnh, thường không có dữ liệu đầu vào | Code đã tạo statement |
| `PreparedStatement` | `connection.prepareStatement(sql)` | SQL với tham số `?`; thường là lựa chọn mặc định | Code đã tạo prepared statement |
| `CallableStatement` | `connection.prepareCall(sql)` | Gọi stored procedure khi DB hỗ trợ | Code đã tạo callable statement |
| `ResultSet` | `statement.executeQuery(...)`, `preparedStatement.executeQuery()` hoặc `getGeneratedKeys()` | Duyệt hàng và đọc cột | Code nhận result set, trừ khi API cấp cao đang kiểm soát |

Cả `Connection`, `Statement` và `ResultSet` đều triển khai `AutoCloseable`. Vì vậy, **`try-with-resources` là cơ chế ưu tiên để đóng đúng cách**, kể cả khi SQL hoặc mapping ném exception.

## 2. Vòng đời từ lúc lấy connection đến lúc đọc hết dữ liệu

### Bước 1 — Mượn/lấy Connection

Ứng dụng thông thường inject một `javax.sql.DataSource` rồi gọi:

```java
Connection connection = dataSource.getConnection();
```

`DataSource` là nơi cấp connection; trong Spring Boot thường là datasource có connection pool (ví dụ HikariCP khi dependency phù hợp). Với pool, một lần `getConnection()` thường mượn một logical connection/handle, **`close()` thường trả handle về pool**, không nhất thiết đóng TCP connection vật lý. Dù vậy, code mượn vẫn phải đóng handle ngay sau khi sử dụng.

`Connection` có nhiều đặc tính cần phân biệt:

- `getAutoCommit()`: theo chuẩn JDBC, connection mới mặc định auto-commit; pool hoặc transaction manager có thể đặt lại chế độ trước khi giao cho mã ứng dụng.
- `setAutoCommit(false)`: các lệnh SQL tham gia transaction do chương trình quản lý; phải quyết định `commit()` hoặc `rollback()` rõ ràng.
- `setTransactionIsolation(...)`, `setReadOnly(...)`: cấu hình hành vi transaction/driver khi có hỗ trợ; không tự thay thế thiết kế transaction.
- `isClosed()` cho biết handle có bị đóng theo trạng thái API; nó **không phải** phép kiểm tra đáng tin cậy connection còn liên lạc DB. Pool thường quản lý validation; JDBC có `isValid(timeout)` khi cần.

### Bước 2 — Tạo Statement từ Connection

```java
Statement statement = connection.createStatement();

PreparedStatement prepared = connection.prepareStatement(
    "SELECT id, name FROM products WHERE id = ?"
);
```

`PreparedStatement` là kiểu con của `Statement`, giữ câu SQL ở lúc chuẩn bị. Dùng `setLong(1, id)`, `setString(2, value)`… để bind dữ liệu với tham số bắt đầu ở **chỉ số 1**. Parameter binding giúp tách giá trị dữ liệu khỏi cú pháp SQL, thường hỗ trợ tái sử dụng statement và giảm nguy cơ SQL injection.

**Phân biệt API:**

- Với `Statement`: `executeQuery("SELECT ...")`, `executeUpdate("UPDATE ...")`.
- Với `PreparedStatement`: `set...(...)` rồi gọi **`executeQuery()`** hoặc **`executeUpdate()`**, không truyền lại chuỗi SQL.
- `executeQuery` dùng cho câu lệnh trả một `ResultSet`; `executeUpdate` dùng cho DML/DDL không trả hàng kiểu truy vấn; `execute` dùng khi kết quả có thể là result set, update count hoặc nhiều kết quả.
- `CallableStatement` phục vụ procedure; có thể có output parameter và nhiều kết quả, cần hiểu cách driver trả chúng.

Dùng `PreparedStatement` cho dữ liệu đầu vào từ người dùng. **Không** nối chuỗi input vào SQL, kể cả nếu đã “escape thủ công”. Placeholder `?` đại diện cho **giá trị**, không thay được tên bảng/tên cột: những phần cấu trúc SQL động phải được kiểm soát bằng allowlist.

### Bước 3 — Thực thi và nhận ResultSet

```java
prepared.setLong(1, 42L);
try (ResultSet resultSet = prepared.executeQuery()) {
    while (resultSet.next()) {
        long id = resultSet.getLong("id");
        String name = resultSet.getString("name");
        // Ánh xạ id/name thành dữ liệu Java khi cursor còn mở.
    }
}
```

`ResultSet` là **cursor**. Ban đầu cursor đứng *trước hàng đầu tiên*; mỗi lần `next()` thành công chuyển tới một hàng và trả `true`. Khi không còn hàng, `next()` trả `false`. Chỉ gọi `getLong`/`getString` sau khi đã `next()` thành công và khi result set còn mở.

**Không có hàng:** vòng `while (rs.next())` không chạy; `ResultSet` vẫn phải đóng. **Một hàng:** dùng `if (rs.next())`, cần kiểm tra thêm `rs.next()` nếu nghiệp vụ bắt buộc đúng một hàng. **Nhiều hàng:** ánh xạ dần sang `List<DTO>`, hoặc tiêu thụ có giới hạn trong lúc result set còn sống.

### Bước 4 — Đóng theo thứ tự phụ thuộc ngược

```text
Tạo:       Connection  -> Statement          -> ResultSet
Sử dụng:                                     next/get...
Đóng:      Connection  <- Statement          <- ResultSet
           cuối cùng      sau ResultSet         đầu tiên
```

Khi thoát khỏi `try-with-resources` có nhiều resource, Java đóng **theo thứ tự ngược lại thứ tự khai báo**. Ví dụ khai báo connection, statement, result set trong một scope sẽ được đóng result set → statement → connection.

Theo JDBC, **đóng `Statement` cũng đóng `ResultSet` hiện tại do statement đó tạo ra**. Chạy lại statement thường cũng đóng result set hiện tại theo quy tắc JDBC, trừ những trường hợp nhiều kết quả được xử lý bằng API thích hợp. Vì vậy, không trả một `ResultSet` ra ngoài method rồi đóng statement; con trỏ sẽ không dùng được nữa. Dù cascading close tồn tại, vẫn nên quản lý result set rõ ràng để xác định đúng thời điểm giải phóng.

## 3. Mẫu try-with-resources đúng và đủ

Với query không cần bind tham số, có thể khai báo ba tài nguyên cùng một scope:

```java
// Mã minh họa nằm bên trong method "throws SQLException".
try (Connection con = dataSource.getConnection();
     Statement stmt = con.createStatement();
     ResultSet rs = stmt.executeQuery(
         "SELECT id, title FROM books ORDER BY id")) {

    while (rs.next()) {
        System.out.println(rs.getLong("id") + ":" + rs.getString("title"));
    }
}
// Đã đóng rs, stmt, con theo đúng thứ tự.
```

Với `PreparedStatement`, cần bind tham số **trước** khi `executeQuery()` nên cách rõ ràng nhất là scope lồng nhau:

```java
try (Connection con = dataSource.getConnection();
     PreparedStatement ps = con.prepareStatement(
         "SELECT id, title FROM books WHERE id = ?")) {

    ps.setLong(1, targetId);

    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            System.out.println(rs.getString("title"));
        }
    }  // Đóng rs.
}      // Đóng ps, rồi con.
```

Đây là **đoạn minh họa**, chưa độc lập để biên dịch vì giả định đã có `DataSource dataSource` và `long targetId`. Ví dụ chạy hoàn chỉnh ở mục 5.

**Đặt `try` bao quanh ngay lúc cấp phát:** nếu `prepareStatement` ném `SQLException` thì connection đã khai báo trước đó vẫn được đóng; nếu `executeQuery` ném lỗi thì statement và connection vẫn đóng. Không nên mở connection trước rồi mới đi qua nhiều nhánh `if`, `return` hoặc exception mà không có `finally` hay `try-with-resources` bảo vệ.

**Không chỉ tin vào GC:** garbage collector quản lý bộ nhớ Java, không bảo đảm database cursor/socket/connection được nhả đúng lúc. Rò tài nguyên thường khiến pool hết connection và request chờ/timeout, dù heap trông vẫn bình thường.

## 4. Một chương trình đầy đủ: JDBC thuần và Spring JdbcTemplate cùng một DB

Ví dụ dùng **Java 17+, Maven, Spring Boot 3.5.16, Spring JDBC và H2 in-memory**. Spring Boot dùng để tạo `DataSource`/`JdbcTemplate` nhanh; phần JDBC thuần vẫn sử dụng trực tiếp ba tài nguyên. Tất cả mã sau nằm trong một project, không phải các đoạn chạy độc lập. Spring Boot 3.5.16 là phiên bản đã phát hành; khi làm dự án thực tế hãy chọn nhánh Spring Boot còn được hỗ trợ.

**Cấu trúc:**

```text
jdbc-resource-chain/
├── pom.xml
└── src/main/
    ├── java/com/example/resources/ResourceChainApplication.java
    └── resources/
        ├── application.properties
        └── schema.sql
```

**`pom.xml`** — Spring Boot quản lý phiên bản transitive dependencies:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>jdbc-resource-chain</artifactId>
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
```

**`src/main/resources/schema.sql`** — tạo một bảng khi ứng dụng khởi động:

```sql
CREATE TABLE books (
    id BIGINT PRIMARY KEY,
    title VARCHAR(120) NOT NULL
);
```

**`src/main/resources/application.properties`** — dùng H2 trong bộ nhớ, tắt banner và giảm log để quan sát phần demo:

```properties
spring.main.web-application-type=none
spring.main.banner-mode=off
logging.level.root=ERROR
spring.datasource.url=jdbc:h2:mem:resourcechain;DB_CLOSE_DELAY=-1
spring.sql.init.mode=always
```

**`src/main/java/com/example/resources/ResourceChainApplication.java`**:

```java
package com.example.resources;

import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import javax.sql.DataSource;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.JdbcTemplate;

@SpringBootApplication
public class ResourceChainApplication {

    public static void main(String[] args) {
        SpringApplication.run(ResourceChainApplication.class, args);
    }

    @Bean
    CommandLineRunner demo(DataSource dataSource, JdbcTemplate jdbc) {
        return args -> {
            // 1) JDBC thuần: Connection -> PreparedStatement.
            try (Connection con = dataSource.getConnection();
                 PreparedStatement ps = con.prepareStatement(
                         "INSERT INTO books (id, title) VALUES (?, ?)")) {

                ps.setLong(1, 1L);
                ps.setString(2, "JDBC");
                System.out.println("inserted=" + ps.executeUpdate());
            }

            // 2) JDBC thuần: Connection -> PreparedStatement -> ResultSet.
            try (Connection con = dataSource.getConnection();
                 PreparedStatement ps = con.prepareStatement(
                         "SELECT id, title FROM books WHERE id = ?")) {

                ps.setLong(1, 1L);

                try (ResultSet rs = ps.executeQuery()) {
                    while (rs.next()) {
                        System.out.println(
                                "raw=" + rs.getLong("id")
                                + ":" + rs.getString("title"));
                    }
                }
            }

            // 3) Spring JDBC tự tạo/đóng tài nguyên trong thao tác query.
            String title = jdbc.queryForObject(
                    "SELECT title FROM books WHERE id = ?",
                    String.class, 1L);
            System.out.println("template=" + title);
        };
    }
}
```

**Chạy** từ thư mục `jdbc-resource-chain`, đã cài JDK 17+ và Maven:

```bash
mvn spring-boot:run
```

**Ba dòng do chương trình chủ động in** (không tính output của Maven/Spring):

```text
inserted=1
raw=1:JDBC
template=JDBC
```

Giải thích:

1. Block đầu **mượn connection**, tạo prepared statement, bind `id/title`, chạy INSERT; thoát block thì statement và connection được đóng/trả về pool.
2. Block thứ hai mở connection/statement mới, `executeQuery()` sinh result set, `next()` đọc đúng một hàng; Java đóng result set trước statement và connection.
3. `JdbcTemplate.queryForObject` đọc cùng database qua datasource đã cấu hình; code không tự tạo hay đóng ba đối tượng ở mức thấp vì Spring JDBC quản lý phạm vi tài nguyên của lời gọi.
4. H2 vẫn giữ database in-memory trong vòng đời ứng dụng nhờ `DB_CLOSE_DELAY=-1`; câu lệnh đầu hoàn tất và auto-commit mặc định cho ví dụ JDBC thuần. Ba đoạn trong demo **không được giới thiệu như một transaction duy nhất**.

Nếu quên đóng connection ở block raw JDBC trên một datasource có pool nhỏ, chạy lặp lại đủ lâu có thể làm pool cạn connection. Nếu giữ `ResultSet` ngoài block thứ hai, bạn sẽ truy cập cursor đã đóng.

## 5. Các quy tắc đóng tài nguyên dễ nhầm

| Hành động | Ảnh hưởng chính | Hệ quả thiết kế |
| --- | --- | --- |
| `resultSet.close()` | Nhả result set/cursor và tài nguyên tương ứng | **Không tự đóng statement hoặc connection** |
| `statement.close()` | Nhả statement; result set hiện hành do statement tạo cũng bị đóng | Không tiếp tục đọc result set sau khi statement đóng |
| `statement.executeQuery(...)` lần nữa | Theo hợp đồng JDBC thông thường, result set hiện tại của statement bị đóng khi thực thi mới | Đừng tái dùng cùng statement trước khi đọc xong cursor cũ |
| `connection.close()` | Nhả JDBC connection handle; đối tượng phụ thuộc không còn dùng được | Luôn đóng statement/result set chủ động để rõ thời điểm; pool có thể nhận lại handle |
| Hết dòng dữ liệu (`next()` trả false) | Cursor ở trạng thái sau hàng cuối; không đồng nghĩa tất cả tài nguyên đã nhả | Vẫn đóng result set và statement |
| Có exception khi execute/đọc result set | Không bảo đảm tự đóng tài nguyên nếu không có cleanup | Bao tất cả phần cấp phát trong `try-with-resources` |
| `executeUpdate()` trả về update count | Không có `ResultSet` thông thường để duyệt | Vẫn phải đóng `Statement` và `Connection` |
| `getGeneratedKeys()` | Trả về một `ResultSet` cho các khóa sinh tự động khi driver hỗ trợ | Phải tiêu thụ và đóng result set này |

**Điều quan trọng:** ResultSet gắn với statement sinh ra nó, nhưng đóng result set **không** có nghĩa statement đã đóng. Vì thế mẫu `return statement.executeQuery()` từ DAO trong khi DAO tự đóng statement/connection là lỗi vòng đời.

### Ví dụ sai: trả cursor còn phụ thuộc tài nguyên đã đóng

```java
// Ví dụ SAI, không phải phương thức nên sử dụng.
public ResultSet findBooks(DataSource source) throws SQLException {
    try (Connection con = source.getConnection();
         PreparedStatement ps = con.prepareStatement(
                 "SELECT id, title FROM books")) {
        return ps.executeQuery();
    } // ps/con đã đóng trước khi caller sử dụng ResultSet.
}
```

**Sửa:** đọc/ánh xạ trong block rồi trả kiểu dữ liệu độc lập như `List<Book>`, `Optional<Book>` hoặc DTO. Khi dữ liệu rất lớn, API streaming phải gắn rõ phạm vi mở/đóng và có contract bảo đảm consumer đóng stream.

```java
// Đoạn minh họa đặt trong method đã có DataSource và import JDBC/List.
List<String> titles = new ArrayList<>();
try (Connection con = dataSource.getConnection();
     PreparedStatement ps = con.prepareStatement(
             "SELECT title FROM books ORDER BY id");
     ResultSet rs = ps.executeQuery()) {

    while (rs.next()) {
        titles.add(rs.getString("title"));
    }
}
return titles; // List được dùng sau khi tất cả JDBC resources đã đóng.
```

Cần `import java.util.ArrayList` và `import java.util.List`; đây là đoạn minh họa, không phải chương trình hoàn chỉnh tách khỏi dự án.

## 6. Đọc ResultSet đúng: cursor, loại dữ liệu và SQL NULL

`ResultSet` mặc định thường là `TYPE_FORWARD_ONLY` và `CONCUR_READ_ONLY` với các statement tạo theo cấu hình cơ bản; driver có thể hỗ trợ các loại scrollable/updatable khác nếu yêu cầu và hỗ trợ. Đừng giả định có thể gọi `previous()` hoặc `absolute(...)` với forward-only cursor.

**Các quy tắc thực hành:**

- `next()` di chuyển con trỏ và báo còn hàng; chưa gọi `next()` thì chưa có hàng hiện hành.
- Chỉ số cột dựa trên **1**: `getString(1)` là cột đầu tiên. Tên cột/alias rõ ràng như `getString("display_name")` giúp tránh phụ thuộc thứ tự SELECT.
- SQL `NULL` có ngữ nghĩa khác 0/false/chuỗi rỗng. Với primitive getter `getInt(...)` hoặc `getLong(...)`, null được trả thành 0; gọi `rs.wasNull()` ngay sau getter nếu cần phân biệt.
- `rs.getObject("age", Integer.class)` có thể giữ `null` trong wrapper phù hợp khi driver hỗ trợ chuyển đổi; với số tiền, ngày giờ, kiểu JSON, hãy hiểu mapping JDBC và nullability.
- Lấy `Blob`/`Clob` hoặc binary stream cần quản lý vòng đời riêng; đừng giả định toàn bộ dữ liệu lớn đã nằm gọn trong bộ nhớ hoặc tài nguyên vẫn tồn tại sau khi đóng result set.

Ví dụ phân biệt `NULL`:

```java
int age = rs.getInt("age");
Integer nullableAge = rs.wasNull() ? null : age;
```

Đây là snippet chạy **bên trong vòng `while (rs.next())`**, trên result set có cột `age`. Gọi `wasNull()` ngay sau lần getter cần kiểm tra vì lần gọi getter tiếp theo có thể thay đổi kết quả `wasNull()`.

### ResultSet không phải collection bất biến

Một `ResultSet` có thể tải dữ liệu từng phần, giữ server-side cursor hoặc buffering ở driver tùy database, fetch size và cấu hình. Nó có thể chịu ảnh hưởng bởi transaction, việc đóng connection/statement, cursor holdability và isolation. Không xem `ResultSet` như `List` có thể truyền tự do qua các tầng hoặc lưu lâu trong field.

Nếu xử lý bảng rất lớn, cân nhắc:

- `setFetchSize(n)` / cấu hình statement khi phù hợp; đây là **hint**, cách driver thực thi khác nhau.
- Streaming có scope rõ ràng và connection tồn tại đủ lâu; không đóng transaction trước khi iterator/stream tiêu thụ.
- Giới hạn số hàng (`setMaxRows`/SQL `LIMIT` khi hỗ trợ), phân trang/keyset pagination, tránh tải vô hạn vào `List`.
- Đo timeout, batch size, pool usage và query plan; fetch size không chữa câu SQL thiếu index.

## 7. Statement, PreparedStatement và CallableStatement

Ba loại có liên hệ kế thừa nhưng mục đích sử dụng khác nhau:

| Loại | Tạo bằng | Gọi thực thi | Cách dùng |
| --- | --- | --- | --- |
| `Statement` | `con.createStatement()` | `executeQuery(sql)`, `executeUpdate(sql)` | SQL tĩnh đơn giản; tránh ghép input |
| `PreparedStatement` | `con.prepareStatement(sql)` | Bind `setXxx(index, value)`, rồi `executeQuery()`/`executeUpdate()` | Thường ưu tiên cho query có tham số, cập nhật và batch |
| `CallableStatement` | `con.prepareCall(callSql)` | Bind input, đăng ký output, `execute()`; đọc kết quả | Stored procedure khi hệ DB hỗ trợ |

**Một `Statement` không được coi là nơi chứa nhiều result set độc lập bất kỳ.** JDBC mặc định cho một result set hiện tại trên một statement; thực thi statement mới có thể đóng kết quả cũ. Với procedure hoặc SQL tạo nhiều kết quả, dùng `execute()`, `getResultSet()`, `getUpdateCount()` và `getMoreResults()` đúng hợp đồng driver, rồi đóng từng result set. Không lấy nhiều `ResultSet` từ cùng statement và giả định chúng sống độc lập.

**Khóa sinh tự động:** dùng `con.prepareStatement(sql, Statement.RETURN_GENERATED_KEYS)`, chạy `executeUpdate()`, rồi dùng `ps.getGeneratedKeys()` trong `try (ResultSet keys = ...)`; đây là một result set khác cũng cần đóng. Hãy kiểm tra tính năng hỗ trợ và thứ tự sinh khóa theo database/driver.

**Batch:** `addBatch`/`executeBatch` giảm nhiều round-trip khi thích hợp, nhưng statement và connection vẫn phải đóng; cần hiểu transaction/partial failures và batch counts. Batch không tự đồng nghĩa “atomic toàn bộ”.

## 8. Khi dùng Spring JdbcTemplate, ai sở hữu ba tài nguyên?

Spring Framework cung cấp `JdbcTemplate` để chuẩn hóa mẫu JDBC: lấy connection, tạo statement, bind, execute, duyệt result set, dịch `SQLException` thành hệ `DataAccessException` và cleanup. Ứng dụng viết SQL và logic mapping, **không tự đóng các tài nguyên mà template đang quản lý**.

```java
// Snippet trong DAO đã inject JdbcTemplate jdbc.
List<BookRow> rows = jdbc.query(
    "SELECT id, title FROM books WHERE id >= ? ORDER BY id",
    (rs, rowNum) -> new BookRow(
        rs.getLong("id"), rs.getString("title")),
    1L
);
```

Trong snippet trên cần một `record BookRow(long id, String title) {}`, import `java.util.List` và đối tượng `JdbcTemplate jdbc`. `RowMapper` nhận `ResultSet` đang mở trong callback, ánh xạ **một hàng** rồi trả object độc lập. `JdbcTemplate` giữ trách nhiệm đóng resource sau khi query hoàn thành, kể cả khi callback ném lỗi.

**Quy tắc callback:** không gọi `rs.close()`, `stmt.close()` hoặc `con.close()` với đối tượng do template cung cấp; không cache `rs`/`con` để dùng sau khi callback kết thúc. Nếu có nhu cầu đọc dòng theo cách đặc thù, dùng `ResultSetExtractor` hoặc `RowCallbackHandler` theo API; trách nhiệm cleanup vẫn thuộc template.

`JdbcTemplate` có các phương thức hay gặp:

- `query(...)` cho nhiều hàng / custom mapper.
- `queryForObject(...)` cho đúng một hàng hoặc giá trị; số hàng không đúng kỳ vọng có thể ném exception Spring, không nên dùng tùy tiện khi kết quả có thể trống.
- `update(...)` cho INSERT/UPDATE/DELETE và trả update count.
- `batchUpdate(...)` cho nhiều cập nhật.
- `execute(ConnectionCallback/StatementCallback/PreparedStatementCallback...)` để thực hiện công việc JDBC nâng cao trong phạm vi Spring kiểm soát.

Từ Spring Framework 6.1, `JdbcClient` có API fluent cho truy cập JDBC, vẫn xây trên hạ tầng Spring JDBC. Dù dùng `JdbcClient`, `NamedParameterJdbcTemplate` hay `JdbcTemplate`, người học vẫn cần hiểu ba tài nguyên gốc để phân tích lỗi, tuning và transaction.

### Streaming qua JdbcTemplate vẫn có trách nhiệm đóng

`JdbcTemplate.queryForStream(...)` trả một `Stream<T>` phụ thuộc tài nguyên JDBC còn mở. **Consumer phải đóng stream**:

```java
// Snippet có JdbcTemplate jdbc đã được inject.
try (Stream<String> titles = jdbc.queryForStream(
        "SELECT title FROM books ORDER BY id",
        (rs, rowNum) -> rs.getString("title"))) {

    titles.forEach(System.out::println);
}
```

Cần `import java.util.stream.Stream`. Không trả stream này ra ngoài rồi để transaction/service method kết thúc trước khi xử lý. Với nhu cầu đọc hàng triệu bản ghi, còn phải kiểm tra driver fetch/transaction behavior và backpressure; “stream” không bảo đảm không buffering.

## 9. Khi có @Transactional: Connection thuộc transaction manager

**Ranh giới quan trọng:** `@Transactional` trên Spring service có thể mở một transaction rồi giữ **một connection phù hợp** cho các hoạt động JDBC bên trong. `JdbcTemplate` sử dụng `DataSourceUtils`, nên nếu có connection ràng buộc với transaction hiện tại, nó tham gia thay vì tự mở và commit một connection độc lập cho mỗi lời gọi.

```text
Caller -> Spring transactional proxy -> Service @Transactional
                                        |
                                   DataSourceTransactionManager
                                        |
                               Connection gắn với thread
                                   /          \
                                  v            v
                         JdbcTemplate A   JdbcTemplate B
                                  \            /
                                   \          /
                                  cùng DB transaction
                                        |
                                   commit / rollback
                                        |
                              release connection/pool
```

Với transaction JDBC imperative do Spring quản lý:

- Dùng `JdbcTemplate` hoặc `DataSourceUtils.getConnection(dataSource)` để lấy connection phù hợp với transaction.
- Khi lấy qua `DataSourceUtils`, **dùng `DataSourceUtils.releaseConnection(connection, dataSource)`**, không gọi `connection.close()` trực tiếp. Trong transaction, helper biết connection phải còn do manager quản lý; ngoài transaction, nó có thể đóng/nhả handle.
- Nếu vẫn gọi thẳng `dataSource.getConnection()` trên datasource thông thường, bạn có thể vô tình lấy **connection khác**, không tham gia transaction đang có. `TransactionAwareDataSourceProxy` là cơ chế tương thích cho một số mã chỉ biết DataSource API, nhưng không phải lý do để tự đóng connection của transaction manager.
- `@Transactional` không tự quản lý mọi connection từ mọi datasource. Phải chọn transaction manager, datasource, propagation và thread context phù hợp.
- Spring AOP mặc định dùng proxy: lời gọi trong cùng object qua `this.someMethod()` có thể bỏ qua transaction advice. Không giả định annotation trên private method tự bật transaction.

**Ví dụ dùng DataSourceUtils cho JDBC cấp thấp trong một DAO** (mã minh họa cần imports, đặt trong class đã có `DataSource dataSource`):

```java
public List<String> findTitles() throws SQLException {
    Connection con = DataSourceUtils.getConnection(dataSource);
    try {
        List<String> titles = new ArrayList<>();
        try (PreparedStatement ps = con.prepareStatement(
                 "SELECT title FROM books ORDER BY id");
             ResultSet rs = ps.executeQuery()) {

            while (rs.next()) {
                titles.add(rs.getString("title"));
            }
        }
        return titles;
    } finally {
        DataSourceUtils.releaseConnection(con, dataSource);
    }
}
```

Ở đây `PreparedStatement` và `ResultSet` do DAO tạo nên DAO đóng bằng try-with-resources. **Connection do `DataSourceUtils` cấp** được hoàn trả bằng helper, để Spring transaction manager quyết định có đóng vật lý/trả về pool hay chưa. Imports: `java.sql.*`, `java.util.*`, `org.springframework.jdbc.datasource.DataSourceUtils`. Đoạn này minh họa cách làm khi thật sự cần API JDBC thấp; phần lớn CRUD nên ưu tiên `JdbcTemplate` để bớt boilerplate.

## 10. Đóng Connection không đồng nghĩa commit hay rollback đúng

Trong JDBC thuần, connection mới thường ở chế độ `autoCommit=true`. Mỗi lệnh SQL được commit theo quy tắc JDBC khi hoàn tất. Nếu thao tác nghiệp vụ có nhiều câu lệnh cần cùng thành công/thất bại, phải đặt ranh giới transaction rõ ràng:

```java
// Mẫu JDBC thuần trong method "throws SQLException".
// Giả định DataSource source, các câu SQL và tham số hợp lệ.
try (Connection con = source.getConnection()) {
    con.setAutoCommit(false);
    try {
        try (PreparedStatement debit = con.prepareStatement(
                 "UPDATE accounts SET balance = balance - ? WHERE id = ?")) {
            debit.setLong(1, amount);
            debit.setLong(2, fromId);
            debit.executeUpdate();
        }
        try (PreparedStatement credit = con.prepareStatement(
                 "UPDATE accounts SET balance = balance + ? WHERE id = ?")) {
            credit.setLong(1, amount);
            credit.setLong(2, toId);
            credit.executeUpdate();
        }
        con.commit();
    } catch (SQLException | RuntimeException ex) {
        try {
            con.rollback();
        } catch (SQLException rollbackFailure) {
            ex.addSuppressed(rollbackFailure);
        }
        throw ex;
    }
}
```

**Đoạn trên chỉ minh họa cách đóng và quyết định transaction**, không phải thiết kế chuyển tiền production: chưa kiểm tra số dư, hàng bị cập nhật, đồng thời, idempotency và bất biến. Biến `source`, `amount`, `fromId`, `toId` chưa khai báo trong snippet. Điều đáng học là transaction được commit/rollback **trước khi close connection**.

JDBC `Connection.close()` khi còn transaction đang hoạt động có kết quả phụ thuộc implementation/driver; **không được coi close là thao tác rollback chắc chắn**. Đổi `setAutoCommit(false)` trở lại `true` khi transaction còn mở còn có thể làm commit; không reset trạng thái tùy tiện trước khi rollback. Pool/transaction framework có trách nhiệm reset trạng thái cho connection trả về pool; mã tự quản lý phải xác minh hợp đồng cụ thể.

Với Spring service dùng `@Transactional`, **không** tự gọi `setAutoCommit(false)`, `commit()`, `rollback()` hoặc `close()` trên connection đang thuộc transaction manager. Hãy đặt transaction boundary ở service, sử dụng JDBC qua template/helper và để manager hoàn tất commit/rollback. Kết hợp quản lý thủ công và declarative transaction trên cùng connection dễ gây commit sớm hoặc phá rollback.

## 11. Exception và cleanup

Các hoạt động `getConnection`, `prepareStatement`, `executeQuery`, `rs.next`, `rs.getXxx` và `close` đều có thể ném `SQLException`. Khi dùng `try-with-resources`:

1. Nếu code trong khối thành công, Java đóng resource theo thứ tự ngược và báo lỗi close nếu có.
2. Nếu code ném lỗi, Java vẫn đóng mọi resource đã tạo thành công.
3. Nếu cả code chính và `close()` đều ném exception, exception từ `close()` được lưu dưới dạng **suppressed exception** (xem `Throwable.getSuppressed()`), giúp không làm mất lỗi ban đầu.

Ví dụ kiểm tra lỗi JDBC khi cần chẩn đoán:

```java
try (Connection con = dataSource.getConnection();
     PreparedStatement ps = con.prepareStatement(
         "SELECT id FROM books WHERE id = ?")) {
    ps.setLong(1, 1L);
    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            System.out.println(rs.getLong(1));
        }
    }
} catch (SQLException e) {
    System.err.println("SQLState=" + e.getSQLState());
    System.err.println("VendorError=" + e.getErrorCode());
    for (Throwable suppressed : e.getSuppressed()) {
        System.err.println("Close failure: " + suppressed);
    }
    throw e; // Để caller quyết định nghiệp vụ/transaction.
}
```

Đoạn này đặt trong method `throws SQLException`, với `dataSource` đã có; không phải chương trình riêng. `SQLException` còn có chuỗi `getNextException()` do driver cung cấp trong một số trường hợp. Không log SQL có dữ liệu nhạy cảm hoặc credentials. Với `JdbcTemplate`, Spring dịch lỗi thông dụng thành `DataAccessException` (unchecked); vẫn cần nhận biết exception cụ thể như constraint violation/connection failure để áp dụng retry hoặc thông báo phù hợp.

**Không nên catch rồi bỏ qua exception** chỉ để “chạy tiếp”: nếu đang trong transaction, có thể cần rollback toàn bộ. Mã cleanup thủ công nhiều tầng dễ có đường đi thiếu `close()`; `try-with-resources` làm cơ chế cleanup gần vị trí sở hữu tài nguyên.

## 12. Những lỗi dễ gặp và cách sửa

### Lỗi A — Chỉ đóng Connection, quên Statement/ResultSet

```java
// SAI: nếu có exception trước con.close(), cả connection có thể bị rò rỉ.
Connection con = dataSource.getConnection();
Statement stmt = con.createStatement();
ResultSet rs = stmt.executeQuery("SELECT * FROM books");
// xử lý nhiều bước, có thể ném exception...
con.close();
```

**Sửa:** dùng `try-with-resources` cho cả ba, đóng theo thứ tự ngược. Dù `Statement.close()` đóng result set hiện hành, cleanup tường minh giúp không giữ tài nguyên đến cuối request và tránh dựa vào hành vi gián tiếp.

### Lỗi B — Dùng ResultSet ngoài scope tạo Statement

```java
// SAI: ResultSet đã mất statement/connection.
ResultSet rs;
try (Connection con = dataSource.getConnection();
     Statement stmt = con.createStatement()) {
    rs = stmt.executeQuery("SELECT title FROM books");
}
rs.next(); // SQLException trên cursor đóng.
```

**Sửa:** ánh xạ dữ liệu trong scope đang mở hoặc thiết kế stream/callback có ownership rõ ràng.

### Lỗi C — Thực thi statement lần hai khi còn đang duyệt ResultSet đầu

```java
// SAI về vòng đời: executeQuery thứ hai thường đóng cursor đầu.
ResultSet first = stmt.executeQuery("SELECT id FROM books");
ResultSet second = stmt.executeQuery("SELECT title FROM books");
first.next();  // Không dùng được vì statement đã có kết quả mới.
```

**Sửa:** đọc xong và đóng result set đầu, hoặc dùng statement thứ hai trên connection khi thật sự cần hai cursor đồng thời và driver cho phép.

### Lỗi D — Nhầm return của executeQuery và executeUpdate

`executeQuery()` trả `ResultSet` cho query. `executeUpdate()` trả số hàng tác động, hoặc giá trị theo JDBC đối với lệnh không trả result set. Với procedure/SQL cho nhiều kết quả, `execute()` cùng API `getResultSet()`/`getUpdateCount()`. Chọn API theo loại SQL.

### Lỗi E — Nối chuỗi SQL với input

```java
// SAI: điều kiện có thể bị thay đổi bằng input độc hại.
String sql = "SELECT * FROM users WHERE email = '" + email + "'";

// ĐÚNG: bind giá trị qua PreparedStatement.
PreparedStatement ps = con.prepareStatement(
        "SELECT * FROM users WHERE email = ?");
ps.setString(1, email);
```

Đoạn đúng là snippet; `ps` phải nằm trong `try-with-resources` tại code thực tế. Binding không dùng cho identifier động; hãy allowlist tên cột/bảng cần thay.

### Lỗi F — Dùng Connection lấy trực tiếp khi đang có Spring transaction

Trong `@Transactional`, tự gọi `dataSource.getConnection()` rồi `close()` có thể tạo connection riêng, commit độc lập và không nằm trong transaction của service. **Sửa:** dùng `JdbcTemplate` hoặc `DataSourceUtils.getConnection/releaseConnection`. Không truyền connection giữa thread, không giữ nó trong field singleton.

### Lỗi G — Giữ cursor/connection quá lâu

Query hàng triệu dòng, rồi xử lý network, upload file hay chờ người dùng **trong cùng lúc giữ connection** sẽ làm pool thiếu tài nguyên. **Sửa:** phân trang hoặc tiêu thụ sớm trong scope ngắn; nếu streaming thật sự cần, đặt timeout và giới hạn, điều chỉnh fetch/batch theo DB, xử lý/giải phóng stream chắc chắn.

## 13. Kết nối với tầng dữ liệu của Spring Framework

Khi tổ chức ứng dụng Spring thành controller → service → repository/DAO:

- **DAO tự viết JDBC:** trách nhiệm đóng `Statement`/`ResultSet` là của DAO; connection lấy theo cơ chế phù hợp với transaction manager nếu có.
- **DAO dùng JdbcTemplate:** Spring làm boilerplate tạo/đóng resource; DAO trả về DTO/record/List thay vì JDBC cursor.
- **Service có `@Transactional`:** Spring quản lý ranh giới transaction và connection tham gia; repository không tự commit/close connection thuộc manager.
- **Connection pool:** datasource cấp logical handles cho nhiều lời gọi; không “fix” rò rỉ bằng cách tăng pool vô hạn. Theo dõi active/idle/pending, thời gian query và leak detection có kiểm soát.
- **Không phụ thuộc ORM:** `Connection`/`Statement`/`ResultSet` là mô hình JDBC. Hibernate/JPA cũng có thể thực thi qua JDBC bên dưới, nhưng entity/`EntityManager` có vòng đời và trừu tượng khác; không đồng nhất các object đó với cursor JDBC.

Một cách ghi nhớ trách nhiệm:

```text
JDBC thuần:
  Caller / DAO owns Connection -> Statement -> ResultSet
  Caller / DAO closes in reverse order.

Spring JdbcTemplate:
  Framework owns Connection/Statement/ResultSet scope.
  Callback owns only data mapping; return Java data.

Spring @Transactional:
  Transaction manager owns transactional Connection lifetime.
  JdbcTemplate/DataSourceUtils participate correctly.
  Service owns business transaction boundary.
```

## 14. Checklist trước khi hoàn tất một DAO hoặc truy vấn

- [ ] Tôi biết **ai tạo** connection/statement/result set và **ai phải đóng** chúng.
- [ ] Mọi tài nguyên tôi sở hữu được đặt trong `try-with-resources` hoặc có `finally` tương đương.
- [ ] `ResultSet` được đọc **trước** khi statement/connection đóng, không trả cursor thô ra ngoài.
- [ ] Tôi dùng `PreparedStatement` và bind tham số cho giá trị do người dùng cung cấp.
- [ ] Tôi kiểm tra `next()`, SQL `NULL`, cột đọc và kiểu dữ liệu chính xác.
- [ ] Tôi chọn đúng `executeQuery`/`executeUpdate`/`execute`.
- [ ] Transaction được commit/rollback rõ ràng khi tôi tự quản lý; không phó mặc cho `close()`.
- [ ] Nếu Spring quản lý transaction, tôi dùng `JdbcTemplate`/`DataSourceUtils` thay vì connection tách biệt.
- [ ] Callback của `JdbcTemplate` chỉ ánh xạ dữ liệu; tôi đóng stream được trả về khi API yêu cầu.
- [ ] Query lớn có chiến lược fetch/limit/stream với scope và timeout phù hợp.
- [ ] Đường đi exception vẫn đóng sạch resource và không nuốt mất nguyên nhân lỗi.
- [ ] Đã kiểm tra tình huống không hàng, nhiều hàng, SQL lỗi, mapping lỗi và pool usage trong test.

## 15. Tự kiểm tra

**1.** `Statement.close()` có đóng `ResultSet` hiện hành không?  
**Đáp án:** có, theo hợp đồng JDBC cho result set do statement đó tạo ra. Tuy nhiên vẫn nên dùng `try-with-resources` rõ ràng cho result set để nhả sớm và an toàn.

**2.** `ResultSet.close()` có đóng `Connection` không?  
**Đáp án:** không. Đóng mỗi result set không giải phóng connection; nơi sở hữu connection phải giải phóng theo đúng contract.

**3.** Một DAO trả `ResultSet` từ trong `try (Connection...; Statement...)`; caller duyệt sau đó. Đúng hay sai?  
**Đáp án:** sai vì statement/connection đã bị đóng khi method trả về. Hãy trả dữ liệu Java đã ánh xạ hoặc thiết kế streaming có scope.

**4.** `PreparedStatement` có tham số `?`; gọi `executeQuery("SELECT...")` như `Statement`. Đúng hay sai?  
**Đáp án:** sai mục đích API; bind bằng `setXxx` rồi gọi `executeQuery()` không tham số.

**5.** Trong service `@Transactional`, mỗi repository tự gọi `dataSource.getConnection()`. Có chắc các query chung một transaction?  
**Đáp án:** không. Với JDBC trong Spring nên dùng `JdbcTemplate`/`DataSourceUtils` và cùng datasource/transaction manager.

**6.** Pool bật HikariCP, `Connection.close()` có thể trả lại pool thay vì tắt TCP. Có cần gọi `close()` không?  
**Đáp án:** vẫn cần! Nếu không trả logical handle, pool hết connection cho request khác.

**7.** Trong JDBC thuần đã `setAutoCommit(false)`, chỉ `close()` mà không `commit()/rollback()`. Có bảo đảm rollback?  
**Đáp án:** không; kết quả khi đóng connection còn active transaction phụ thuộc implementation. Phải hoàn tất transaction tường minh.

## Tài liệu tham khảo chính thức

- Java SE 17 JDBC `Connection`: https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/Connection.html
- Java SE 17 JDBC `Statement`: https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/Statement.html
- Java SE 17 JDBC `PreparedStatement`: https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/PreparedStatement.html
- Java SE 17 JDBC `ResultSet`: https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/ResultSet.html
- Java SE 17 `try-with-resources`: https://docs.oracle.com/javase/tutorial/essential/exceptions/tryResourceClose.html
- Spring Framework — JDBC core/`JdbcTemplate`: https://docs.spring.io/spring-framework/reference/data-access/jdbc/core.html
- Spring Framework — Connection management/`DataSourceUtils`: https://docs.spring.io/spring-framework/reference/data-access/jdbc/connections.html
- Spring Framework — Transaction management: https://docs.spring.io/spring-framework/reference/data-access/transaction.html
- Spring Boot 3.5.16 release: https://spring.io/blog/2026/06/25/spring-boot-3-5-16-available-now/

**Ghi nhớ cuối bài:** `Connection` tạo `Statement`, `Statement` tạo `ResultSet`. Khi tự làm JDBC, **đóng ngược thứ tự bằng try-with-resources**. Khi dùng `JdbcTemplate`, **Spring sở hữu cleanup của callback**. Khi dùng `@Transactional`, **transaction manager sở hữu connection đang tham gia**. Nắm rõ *ai sở hữu tài nguyên* sẽ ngăn phần lớn lỗi rò connection, cursor đóng sớm và transaction sai.