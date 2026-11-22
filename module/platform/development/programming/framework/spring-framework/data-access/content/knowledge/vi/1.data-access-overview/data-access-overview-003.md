# Những công việc Spring xử lý thay cho mã JDBC thủ công

## 1. Bài toán: JDBC thuần buộc lập trình viên làm những gì?

JDBC (Java Database Connectivity) là API tiêu chuẩn để Java làm việc với cơ sở dữ liệu quan hệ. JDBC cung cấp `Connection`, `PreparedStatement`, `ResultSet` và `SQLException`. Nó cho phép kiểm soát trực tiếp nhưng một thao tác rất đơn giản như “tìm người dùng theo mã” vẫn phải lặp đi lặp lại nhiều việc kỹ thuật:

1. Có `DataSource` hoặc thông tin kết nối; lấy một `Connection`.
2. Tạo `PreparedStatement` cho SQL và gán tham số theo đúng thứ tự, đúng kiểu.
3. Thực thi `executeQuery()` / `executeUpdate()` và đọc kết quả.
4. Duyệt `ResultSet`, lấy đúng cột và ánh xạ sang đối tượng Java.
5. Đóng `ResultSet`, `Statement` và `Connection` trên cả đường thành công lẫn đường lỗi.
6. Xử lý `SQLException`, quyết định ngoại lệ nào đưa lên tầng nghiệp vụ.
7. Nếu có nhiều lệnh cần nhất quán, chủ động điều khiển transaction (`autoCommit`, `commit`, `rollback`), tránh để các câu lệnh chạy trên những connection khác nhau.

Mẫu JDBC thuần dưới đây cho thấy riêng việc *đọc một bản ghi* đã cần nhiều dòng. `try-with-resources` giúp đóng tài nguyên an toàn nhưng không xóa được phần mã lặp:

```java
// Đoạn minh họa nằm trong một lớp đã có DataSource và record Person(long id, String name).
Person findByIdRaw(DataSource dataSource, long id) throws SQLException {
    String sql = "SELECT id, name FROM people WHERE id = ?";
    try (Connection connection = dataSource.getConnection();
         PreparedStatement statement = connection.prepareStatement(sql)) {
        statement.setLong(1, id);
        try (ResultSet rs = statement.executeQuery()) {
            if (!rs.next()) {
                return null;
            }
            return new Person(rs.getLong("id"), rs.getString("name"));
        }
    }
}
```

Các thao tác mở/đóng tài nguyên, dịch lỗi và lặp mẫu truy vấn là *phần hạ tầng*. Logic đặc thù ứng dụng thực chất chỉ là SQL, giá trị `id`, quy tắc xử lý kết quả và hành vi khi không tìm thấy.

## 2. Spring JDBC nhận những việc nào?

Thành phần tiêu biểu là `JdbcTemplate` trong module `spring-jdbc`. Ứng dụng cung cấp `DataSource` và chỉ diễn đạt SQL, tham số và phép ánh xạ; Spring điều phối chuỗi thao tác JDBC.

| Việc cần làm | JDBC thủ công | Spring JDBC |
| --- | --- | --- |
| Lấy và trả connection | Gọi `getConnection()` rồi `close()`; tự phối hợp nếu có transaction | `JdbcTemplate` dùng cơ chế lấy/giải phóng connection của Spring, phối hợp với transaction hiện hành khi cấu hình đúng |
| Tạo statement, đặt tham số | `prepareStatement`, `setXxx` theo vị trí | `query` / `update` nhận SQL và tham số; có callback cho trường hợp đặc biệt |
| Thực thi và đóng tài nguyên | Gọi execute và đóng `ResultSet`, `Statement`, connection | Template thực thi và dọn dẹp tài nguyên trong cả đường thành công/lỗi |
| Duyệt kết quả | `while (rs.next())`, tự tạo object | `RowMapper`, `ResultSetExtractor`, `RowCallbackHandler` |
| Lỗi SQL | Bắt/xử lý `SQLException` checked | Dịch sang phân cấp `DataAccessException` unchecked, có loại lỗi cụ thể khi nhận diện được |
| Nhiều lệnh ghi trong một transaction | Tự giữ cùng connection, tắt auto-commit, commit/rollback | `PlatformTransactionManager` và `@Transactional` quản lý ranh giới transaction khi được bật và dùng đúng |
| Câu lệnh có tham số đặt tên | JDBC `?` theo thứ tự | `NamedParameterJdbcTemplate` với `:name`, chuyển về tham số JDBC |
| Thao tác hàng loạt | Tự lập batch/flush | `batchUpdate` hỗ trợ tổ chức batch |
| Khóa tự sinh | `RETURN_GENERATED_KEYS` rồi đọc kết quả | `KeyHolder` / `GeneratedKeyHolder` hỗ trợ lấy khóa sinh từ DB |

**Ranh giới trách nhiệm:** Spring *không tự viết SQL đúng*, *không tự sửa schema*, *không ngăn mọi vấn đề hiệu năng* và *không tự tạo transaction chỉ vì bạn khởi tạo `JdbcTemplate`*. Lập trình viên vẫn chịu trách nhiệm thiết kế truy vấn, chỉ mục, tính đúng đắn nghiệp vụ, bảo mật đầu vào và cấu hình transaction.

### 2.1. Cơ chế xử lý một truy vấn

```text
Repository / DAO
    │  SQL + tham số + RowMapper
    ▼
JdbcTemplate
    ├─ lấy Connection từ DataSource theo cơ chế Spring
    ├─ chuẩn bị PreparedStatement và bind tham số
    ├─ chạy query/update
    ├─ đọc ResultSet bằng callback/RowMapper
    ├─ dịch SQLException thành DataAccessException
    └─ đóng ResultSet/Statement, giải phóng Connection phù hợp transaction
    ▼
Kết quả Java hoặc ngoại lệ đã được dịch
```

Thông thường `JdbcTemplate` dùng `DataSourceUtils` để có connection gắn với transaction của luồng hiện tại nếu tồn tại; khi một transaction đang hoạt động, việc “giải phóng” không đồng nghĩa đóng vật lý connection trước lúc kết thúc transaction. Với connection pool, `close()` thường là thao tác trả connection về pool, không phải đóng socket tới DB mỗi lần.

`JdbcTemplate` được thiết kế để dùng lại giữa các thành phần như một đối tượng đã cấu hình. Có thể tạo một instance cho mỗi `DataSource` (hoặc cấu hình thêm loại xử lý đặc thù); không tạo mới template cho mỗi bản ghi.

## 3. Ví dụ chạy được: cùng dữ liệu, hai cách truy vấn

Ví dụ dùng **Java 17+**, Maven, **Spring JDBC 6.2.12** và cơ sở dữ liệu H2 chạy trong bộ nhớ. Không cần cài máy chủ DB.

Cấu trúc:

```text
jdbc-work-demo/
├── pom.xml
└── src/main/java/example/JdbcWorkDemo.java
```

`pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>jdbc-work-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-jdbc</artifactId>
            <version>6.2.12</version>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <version>2.3.232</version>
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
            </plugin>
        </plugins>
    </build>
</project>
```

`src/main/java/example/JdbcWorkDemo.java`:

```java
package example;

import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.Map;
import javax.sql.DataSource;

import org.h2.jdbcx.JdbcDataSource;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.RowMapper;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;

public class JdbcWorkDemo {
    record Person(long id, String name) {}

    public static void main(String[] args) throws SQLException {
        JdbcDataSource dataSource = new JdbcDataSource();
        dataSource.setURL("jdbc:h2:mem:demo;DB_CLOSE_DELAY=-1");
        dataSource.setUser("sa");
        dataSource.setPassword("");

        JdbcTemplate jdbc = new JdbcTemplate(dataSource);
        jdbc.execute("CREATE TABLE people (id BIGINT PRIMARY KEY, name VARCHAR(100) NOT NULL)");
        jdbc.update("INSERT INTO people (id, name) VALUES (?, ?)", 1L, "Lan");
        jdbc.update("INSERT INTO people (id, name) VALUES (?, ?)", 2L, "Minh");

        Person raw = findByIdRaw(dataSource, 1L);
        System.out.println("Raw JDBC: " + raw);

        RowMapper<Person> mapper =
                (rs, rowNum) -> new Person(rs.getLong("id"), rs.getString("name"));

        Person fromTemplate = jdbc.queryForObject(
                "SELECT id, name FROM people WHERE id = ?", mapper, 2L);
        System.out.println("JdbcTemplate: " + fromTemplate);

        NamedParameterJdbcTemplate named = new NamedParameterJdbcTemplate(dataSource);
        Person fromNamed = named.queryForObject(
                "SELECT id, name FROM people WHERE id = :personId",
                Map.of("personId", 1L),
                mapper);
        System.out.println("NamedParameter: " + fromNamed);
    }

    static Person findByIdRaw(DataSource dataSource, long id) throws SQLException {
        String sql = "SELECT id, name FROM people WHERE id = ?";
        try (Connection connection = dataSource.getConnection();
             PreparedStatement statement = connection.prepareStatement(sql)) {
            statement.setLong(1, id);
            try (ResultSet rs = statement.executeQuery()) {
                if (!rs.next()) {
                    return null;
                }
                return new Person(rs.getLong("id"), rs.getString("name"));
            }
        }
    }
}
```

Trong thư mục chứa `pom.xml`, chạy:

```bash
mvn -q compile exec:java -Dexec.mainClass=example.JdbcWorkDemo
```

Kết quả in ra từ chương trình (Maven có thể có thông báo riêng tùy môi trường):

```text
Raw JDBC: Person[id=1, name=Lan]
JdbcTemplate: Person[id=2, name=Minh]
NamedParameter: Person[id=1, name=Lan]
```

**Giải thích:** Cả ba cách trả về cùng kiểu `Person`. Hàm JDBC thuần quản lý thủ công `Connection`, `PreparedStatement` và `ResultSet`. Hai truy vấn Spring chỉ nêu SQL, tham số và `RowMapper`; việc đóng tài nguyên và chuyển đổi `SQLException` thành ngoại lệ truy cập dữ liệu được template đảm nhiệm. Lệnh `jdbc.update(...)` trả về số hàng bị ảnh hưởng (ở đây mỗi lệnh insert là 1), hữu ích khi cần kiểm tra kỳ vọng.

## 4. Ánh xạ kết quả và số lượng bản ghi

`JdbcTemplate` không đoán mọi cấu trúc DTO của ứng dụng. Ta vẫn chọn cách đọc dữ liệu:

- `RowMapper<T>` ánh xạ **một hàng** của `ResultSet` thành một `T`. Dùng `query(sql, mapper, args...)` để lấy danh sách; template thực hiện vòng lặp.
- `queryForObject(sql, mapper, args...)` phù hợp khi kỳ vọng **chính xác một hàng**; không có hàng thường dẫn đến `EmptyResultDataAccessException`, nhiều hơn một hàng dẫn đến `IncorrectResultSizeDataAccessException`. Nó **không** tự trả `null` như nhánh minh họa raw JDBC.
- `ResultSetExtractor<T>` xử lý **toàn bộ** `ResultSet` theo cách tùy biến, chẳng hạn gộp nhiều hàng cho một aggregate.
- `RowCallbackHandler` xử lý tuần tự từng hàng qua callback khi không cần xây một danh sách kết quả. Tuy nhiên `ResultSet` vẫn chỉ có hiệu lực trong callback; không giữ nó dùng sau khi phương thức template kết thúc.

Ví dụ tìm nhiều hàng và xử lý trường hợp không có hàng:

```java
// Đoạn dùng bên trong một DAO đã có JdbcTemplate jdbc và RowMapper<Person> mapper.
List<Person> people = jdbc.query(
        "SELECT id, name FROM people ORDER BY id", mapper);

List<Person> matches = jdbc.query(
        "SELECT id, name FROM people WHERE id = ?", mapper, 999L);
Person optional = matches.isEmpty() ? null : matches.get(0);
```

Ví dụ này là **đoạn trích**, không phải file Java độc lập; cần import `java.util.List` và biến `jdbc`, `mapper`. Với truy vấn luôn tối đa một hàng, cách dùng `query(...)` rồi kiểm tra danh sách giúp diễn đạt rõ “có thể không tồn tại”.

Ánh xạ tự động như `BeanPropertyRowMapper` có thể giảm mã lặp với JavaBean phù hợp, nhưng ánh xạ rõ ràng bằng `RowMapper` thường dễ kiểm soát tên cột, kiểu, giá trị `NULL` và đối tượng immutable hơn.

## 5. Binding tham số: tiện lợi và an toàn

`JdbcTemplate` giữ mô hình `PreparedStatement` của JDBC: giá trị dữ liệu được bind tách khỏi cấu trúc SQL.

```java
// Đúng: giá trị id đi qua tham số.
jdbc.query("SELECT id, name FROM people WHERE id = ?", mapper, userId);

// Tránh: ghép trực tiếp dữ liệu người dùng vào SQL.
String unsafe = "SELECT id, name FROM people WHERE name = '" + inputName + "'";
```

Khi truy vấn có nhiều điều kiện, `NamedParameterJdbcTemplate` cho phép tên có nghĩa:

```java
String sql = """
        SELECT id, name FROM people
        WHERE id >= :minId AND name = :name
        ORDER BY id
        """;
Map<String, ?> params = Map.of("minId", 1L, "name", "Lan");
List<Person> result = named.query(sql, params, mapper);
```

Spring phân tích các tên `:minId` và `:name`, chuyển chúng sang placeholder JDBC và bind các giá trị tương ứng; bản thân DB không bắt buộc hỗ trợ cú pháp `:name`. Khi bind danh sách cho `IN (:ids)`, lưu ý danh sách rỗng và giới hạn tham số của từng DB; kiểm tra trước thay vì kỳ vọng mọi trường hợp được xử lý giống nhau.

**Giới hạn quan trọng:** placeholder chỉ dùng cho *giá trị* (như id, tên, thời gian), không dùng để thay tên bảng, tên cột hoặc hướng `ORDER BY`. Những thành phần cấu trúc SQL động phải đến từ danh sách cho phép ở phía ứng dụng.

Từ Spring Framework 6.1 có thêm `JdbcClient`, API fluent kết hợp tham số vị trí và tham số tên trên nền cơ chế JDBC quen thuộc. Đây là một cách viết khác, không làm mất nhu cầu hiểu `DataSource`, binding, mapping hay transaction.

## 6. Dịch ngoại lệ: từ SQLException sang DataAccessException

JDBC dùng `SQLException` (checked), khiến tầng nghiệp vụ thường phải `throws SQLException` hoặc `catch` và tự bọc lỗi. `JdbcTemplate` bắt lỗi JDBC và dùng `SQLExceptionTranslator` để đưa về phân cấp `org.springframework.dao.DataAccessException` (unchecked).

Một số loại thường gặp khi cơ sở dữ liệu và translator nhận diện được:

| Tình huống | Ngoại lệ Spring có thể gặp |
| --- | --- |
| Vi phạm unique/primary key | `DuplicateKeyException` |
| SQL không hợp lệ | `BadSqlGrammarException` |
| Không có hàng khi `queryForObject` kỳ vọng 1 | `EmptyResultDataAccessException` |
| Số hàng khác kỳ vọng | `IncorrectResultSizeDataAccessException` |
| Không phân loại được lỗi JDBC cụ thể | `UncategorizedSQLException` |

Việc dịch dựa vào subclass, SQLState, mã lỗi và cấu hình translator; **không bảo đảm** mọi driver/DB đều cho ra đúng một loại cụ thể ở mọi tình huống. Ngoại lệ gốc vẫn có thể được giữ làm nguyên nhân để chẩn đoán.

Ví dụ xử lý lỗi trùng khóa có chủ đích:

```java
try {
    jdbc.update("INSERT INTO people (id, name) VALUES (?, ?)", 1L, "Khac");
} catch (DuplicateKeyException ex) {
    // Có thể trả thông báo nghiệp vụ "id đã tồn tại";
    // không nên ghi log rồi lặng lẽ báo thao tác thành công.
}
```

Đây là đoạn trích thuộc DAO/service. `@Repository` hữu ích để đánh dấu tầng persistence và để áp dụng exception translation cho các API persistence phù hợp, nhưng **không phải điều kiện bắt buộc** để `JdbcTemplate` dịch `SQLException`: bản thân template đã làm việc đó.

## 7. Transaction: Spring tự phối hợp connection thế nào?

Có thể đọc/ghi một câu lệnh riêng lẻ mà không cần transaction do Spring quản lý. Nhưng một nghiệp vụ gồm nhiều lệnh thường cần **all-or-nothing**, ví dụ chuyển tiền gồm trừ tài khoản nguồn và cộng tài khoản đích.

Với JDBC thuần, lập trình viên phải giữ cùng `Connection`, tắt `autoCommit` và tự `commit` / `rollback` khi lỗi, cuối cùng phục hồi trạng thái connection thích hợp trước khi trả về pool. Viết thiếu một nhánh lỗi có thể khiến dữ liệu cập nhật dở dang hoặc để connection ở trạng thái ngoài ý muốn.

Trong Spring, ranh giới thường được đặt ở **service**:

```java
// Đoạn minh họa trong ứng dụng Spring đã cấu hình transaction manager cho DataSource.
@Service
public class TransferService {
    private final JdbcTemplate jdbc;

    public TransferService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public void transfer(long fromId, long toId, long amount) {
        if (amount <= 0 || fromId == toId) {
            throw new IllegalArgumentException("Invalid transfer");
        }
        int debit = jdbc.update(
                "UPDATE accounts SET balance = balance - ? " +
                "WHERE id = ? AND balance >= ?",
                amount, fromId, amount);
        if (debit != 1) {
            throw new IllegalStateException("Source missing or insufficient funds");
        }
        int credit = jdbc.update(
                "UPDATE accounts SET balance = balance + ? WHERE id = ?",
                amount, toId);
        if (credit != 1) {
            throw new IllegalStateException("Destination missing");
        }
    }
}
```

Các import minh họa: `org.springframework.stereotype.Service`, `org.springframework.transaction.annotation.Transactional` và `org.springframework.jdbc.core.JdbcTemplate`. Để chạy thực tế cần bảng `accounts`, bean `JdbcTemplate`, transaction manager phù hợp và cơ chế bật transaction. Đây là **ví dụ service**, không phải chương trình độc lập; các quy tắc nghiệp vụ về số dư, khóa, kiểu tiền và cạnh tranh đồng thời cần được thiết kế thêm theo DB thực tế.

Khi lời gọi tới `transfer(...)` đi qua Spring transaction proxy, transaction manager mở/tham gia transaction; `JdbcTemplate` lấy connection tương ứng từ cùng `DataSource`; nếu cả hai câu lệnh thành công transaction được commit, còn `RuntimeException` ở ví dụ trên mặc định làm rollback.

Cấu hình Spring Framework thuần điển hình:

```java
@Configuration
@EnableTransactionManagement
class JdbcConfig {
    @Bean
    PlatformTransactionManager transactionManager(DataSource dataSource) {
        return new JdbcTransactionManager(dataSource);
    }
}
```

Đoạn cấu hình minh họa cần các import `org.springframework.context.annotation.*`, `org.springframework.transaction.PlatformTransactionManager`, `org.springframework.jdbc.support.JdbcTransactionManager`, `javax.sql.DataSource` và một bean `DataSource` thực tế. Với Spring Boot và `spring-boot-starter-jdbc`, hệ thống thường tự cấu hình `DataSource`, `JdbcTemplate`, transaction manager khi có các điều kiện/dependency phù hợp; vẫn cần cấu hình URL/driver/credentials và kiểm tra môi trường thật.

Những điều dễ nhầm:

- `@Transactional` chỉ là metadata nếu không có transaction infrastructure hoạt động; `new TransferService(...)` nằm ngoài container không nhận proxy.
- Với chế độ proxy mặc định, **self-invocation** (`this.transfer(...)` gọi từ chính bean) không kích hoạt advice của phương thức được gọi; hãy gọi qua bean/proxy phù hợp hoặc thiết kế lại ranh giới service.
- `@Transactional` mặc định rollback cho `RuntimeException` và `Error`, không rollback cho checked exception nếu không cấu hình thêm (ví dụ `rollbackFor`). Catch rồi nuốt ngoại lệ cũng có thể khiến Spring commit vì phương thức trả về bình thường.
- `readOnly = true` thường là gợi ý tối ưu/thiết lập cho driver hoặc ORM, **không phải cơ chế kiểm soát quyền ghi tuyệt đối**.
- `JdbcTemplate` chỉ tự tham gia transaction khi nó dùng `DataSource` phù hợp với transaction manager. Tự mở connection bằng `dataSource.getConnection()` trong khối transaction có thể dùng connection khác và phá vỡ tính nguyên tử; ưu tiên template hoặc cơ chế `DataSourceUtils` khi tích hợp JDBC thấp tầng.
- Transaction của DB không làm an toàn mọi thao tác ngoài DB như gửi email hay HTTP call; chúng không tự rollback cùng transaction JDBC.

## 8. Những tiện ích JDBC khác Spring cung cấp

Ngoài truy vấn đơn, Spring JDBC còn có những API làm giảm mã lặp khi bài toán cần:

- **`batchUpdate`:** đưa nhiều nhóm tham số vào một batch, thường giảm chi phí gọi driver/database. Lợi ích thực tế phụ thuộc driver, kích thước batch, transaction và loại SQL; vẫn cần xử lý lỗi và số hàng cập nhật.
- **`KeyHolder` / `GeneratedKeyHolder`:** đọc khóa chính do DB sinh trong lúc INSERT; khả năng trả khóa phụ thuộc driver/SQL.
- **`SimpleJdbcInsert`:** API tiện ích cho INSERT, có thể dùng metadata DB để xây một phần câu lệnh; không phải ORM.
- **`JdbcClient` (Spring 6.1+):** cách viết fluent cho query/update; dùng các cơ chế Spring JDBC bên dưới.
- **`SimpleJdbcCall`:** hỗ trợ gọi stored procedure/function, vẫn chịu khác biệt khả năng metadata giữa các DB và driver.
- **`JdbcTestUtils`, `@JdbcTest` trong hệ sinh thái kiểm thử Spring:** giúp thiết lập kiểm thử truy cập DB; không thay thế việc kiểm tra trên dialect/DB sản xuất khi SQL phụ thuộc vendor.

Ví dụ batch độc lập với cấu hình transaction:

```java
List<Object[]> args = List.of(
        new Object[] { 3L, "An" },
        new Object[] { 4L, "Binh" }
);
int[] updateCounts = jdbc.batchUpdate(
        "INSERT INTO people (id, name) VALUES (?, ?)", args);
```

Đây là đoạn trích cần `java.util.List` và `jdbc` đã khởi tạo. Không suy luận số lượt round trip chỉ từ số phần tử của mảng; driver có thể xử lý batch khác nhau.

## 9. Spring không thay thế những quyết định nào của lập trình viên?

Hiểu ranh giới này sẽ tránh kỳ vọng sai về abstraction:

1. **SQL và schema:** Spring không tự chọn chỉ mục, tránh N+1, sửa câu SQL thiếu `WHERE`, điều chỉnh pagination hoặc quyết định isolation level phù hợp.
2. **An toàn dữ liệu:** vẫn phải validate input, giới hạn truy vấn động, xác thực/phân quyền và xử lý xung đột đồng thời. Binding tham số không tự bảo vệ tên cột/bảng được ghép động.
3. **Ngữ nghĩa “không tìm thấy”:** quyết định trả `Optional`, danh sách rỗng, lỗi 404 hay ngoại lệ nghiệp vụ; `queryForObject` thường ném ngoại lệ khi không có hàng.
4. **Tính nguyên tử:** cần cấu hình đúng transaction manager, ranh giới gọi qua proxy, `DataSource` và xử lý rollback. Một template đơn độc không bao toàn bộ service trong transaction.
5. **Tài nguyên và hiệu năng:** vẫn cần cấu hình connection pool, timeout, fetch size/batch hợp lý, quan sát slow SQL và số lượng connection. Template giúp dọn dẹp tài nguyên do nó tạo ra, không tự đóng tài nguyên tùy ý bạn mở ngoài template.
6. **ORM:** `JdbcTemplate` không cung cấp persistence context, dirty checking, lazy loading hay mapping quan hệ thực thể kiểu JPA/Hibernate. Spring Data JDBC cũng có mô hình riêng và không đồng nghĩa `JdbcTemplate`.

## 10. Sai lầm phổ biến và cách khắc phục

| Sai lầm | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Ghép giá trị người dùng trực tiếp vào SQL | SQL injection và lỗi quoting | Dùng placeholder `?` / `:name` và tham số bind |
| Dùng `queryForObject` cho truy vấn có thể trả 0 hoặc nhiều hàng | Ngoại lệ sai kỳ vọng | Chọn `query` hoặc xác lập unique constraint và xử lý 0 hàng rõ ràng |
| Tạo `JdbcTemplate` và nghĩ tất cả lệnh tự chạy trong 1 transaction | Ghi dở dang khi lệnh sau lỗi | Cấu hình transaction manager, đặt `@Transactional` tại service và xác minh rollback |
| Bắt `Exception` rồi chỉ log trong service transactional | Có thể commit dù nghiệp vụ thất bại | Để lỗi phù hợp nổi lên hoặc chủ động đánh dấu rollback theo thiết kế |
| Gọi `@Transactional` qua `this.method()` | Bỏ qua proxy mặc định | Thiết kế lời gọi qua Spring bean và kiểm thử transaction thực tế |
| Mở connection riêng trong nghiệp vụ đang dùng `JdbcTemplate` | Không cùng transaction; rò rỉ hoặc cập nhật một phần | Dùng template hoặc API tham gia Spring-managed transaction |
| Giữ `ResultSet` để dùng sau callback | ResultSet đã bị đóng khi template kết thúc | Chuyển kết quả thành DTO/collection ngay trong callback |
| Coi Spring thay toàn bộ tuning DB | Truy vấn vẫn chậm, contention, deadlock | EXPLAIN, chỉ mục, đo latency, pool và transaction duration |

## 11. Cách áp dụng vào dự án thực tế

Một hướng xây dựng nhỏ, dễ kiểm chứng:

1. **Cấu hình `DataSource`** tới DB thật và connection pool phù hợp; đặt credentials qua cơ chế quản lý bí mật, không hardcode trong mã nguồn.
2. **Tạo hoặc inject `JdbcTemplate`/`NamedParameterJdbcTemplate`**. Repository chịu trách nhiệm SQL, tham số, ánh xạ DTO; service điều phối use case.
3. **Chọn hợp đồng cho từng phương thức**: một hàng bắt buộc, không hoặc một hàng, nhiều hàng, hoặc số hàng cập nhật. Kiểm tra rõ `updateCount` khi business rule cần đúng một hàng.
4. **Đặt transaction tại service** cho các thao tác nhiều lệnh phải commit/rollback cùng nhau. Test đường thành công và đường lỗi ngay sau câu lệnh đầu tiên.
5. **Kiểm thử thực tế**: tạo dữ liệu cố định; test duplicate key, missing row, rollback, concurrent update và giới hạn dialect; theo dõi SQL/pool/lock khi chạy.
6. **Chỉ hạ xuống JDBC thấp tầng khi cần** các khả năng driver-specific; ngay cả khi đó vẫn phối hợp với connection/transaction mà Spring quản lý.

### Câu hỏi tự kiểm tra

- Vì sao `try-with-resources` trong JDBC thuần vẫn chưa giải quyết toàn bộ mã lặp?
- `RowMapper` làm gì, còn ai có trách nhiệm đóng `ResultSet`?
- Vì sao bind `:name` an toàn hơn ghép giá trị, nhưng không thể bind tên cột tùy ý?
- Nếu câu lệnh trừ tiền thành công nhưng câu lệnh cộng tiền thất bại, cần những điều kiện nào để rollback được câu lệnh đầu?
- `queryForObject` khác truy vấn raw trả `null` khi không có dữ liệu ở điểm nào?

**Điểm cần nhớ:** Spring JDBC loại bỏ phần lớn mã hạ tầng lặp của JDBC thuần: lấy/giải phóng tài nguyên, chuẩn bị và thực thi statement, duyệt/map kết quả, dịch ngoại lệ và tích hợp connection với transaction. Phần thiết kế SQL, hợp đồng nghiệp vụ, bảo mật, transaction boundary và hiệu năng vẫn do người viết ứng dụng quyết định.

### Tài liệu tham khảo chính thức

- Spring Framework — JDBC core: https://docs.spring.io/spring-framework/reference/data-access/jdbc/core.html
- Spring Framework — Using `@Transactional`: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html
- Spring Framework — JDBC transaction management: https://docs.spring.io/spring-framework/reference/data-access/transaction.html
