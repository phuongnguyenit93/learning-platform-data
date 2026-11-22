# JdbcTemplate: query(), queryForObject(), update() và execute()

## Bạn sẽ học được gì?

`JdbcTemplate` là thành phần cốt lõi của Spring JDBC, giúp ứng dụng gửi SQL đến cơ sở dữ liệu mà không phải lặp đi lặp lại mã lấy kết nối, tạo statement, đọc `ResultSet`, đóng tài nguyên và chuyển phần lớn lỗi JDBC sang phân cấp `DataAccessException`.

Khi bắt đầu viết repository với Spring JDBC, bốn nhóm phương thức dễ gây nhầm lẫn là:

- **`query(...)`**: chạy truy vấn và ánh xạ **nhiều dòng** thành danh sách hoặc xử lý kết quả qua callback.
- **`queryForObject(...)`**: chạy truy vấn mà người gọi **kỳ vọng đúng một dòng**, có thể trả đối tượng từ `RowMapper` hoặc một giá trị đơn.
- **`update(...)`**: thực thi các lệnh thao tác dữ liệu như `INSERT`, `UPDATE`, `DELETE`; trả về **số dòng chịu tác động**.
- **`execute(...)`**: thực thi SQL hoặc một thao tác JDBC tổng quát; overload nhận một chuỗi SQL thường dùng cho DDL hoặc tác vụ không cần đọc dữ liệu trả về.

Mục tiêu sau bài học: chọn đúng phương thức theo SQL và cardinality mong đợi; đọc đúng kết quả/ngoại lệ; bind tham số an toàn; đặt mỗi lệnh vào ranh giới transaction phù hợp; và chạy được một ví dụ Java 17+ với Spring Framework + H2.

> Bài này minh họa Spring Framework 6.2.x và Spring JDBC. Đây không phải API của JPA `EntityManager`. Spring Boot có thể tự cấu hình các bean liên quan nhưng không thay đổi ý nghĩa của những phương thức này.

## 1. Bảng quyết định nhanh

| Nhu cầu | Phương thức thường chọn | Dữ liệu trả về | Nếu không có dòng phù hợp |
| --- | --- | --- | --- |
| Lấy danh sách sách theo điều kiện | `query(sql, rowMapper, args...)` | `List<Book>` | Danh sách rỗng |
| Tìm sách bằng ID duy nhất, bắt buộc tồn tại | `queryForObject(sql, rowMapper, args...)` | Một `Book` | Ném `EmptyResultDataAccessException` |
| Đọc một số đếm, tổng, tên hoặc giá trị đơn | `queryForObject(sql, Long.class, args...)` | Một giá trị đơn hoặc `null` nếu giá trị SQL là NULL | Không có dòng: ngoại lệ; `COUNT(*)` không có `GROUP BY` vẫn trả một dòng chứa 0 |
| Chèn, sửa, xóa dữ liệu | `update(sql, args...)` | `int` số dòng chịu tác động | Thường trả 0 cho UPDATE/DELETE không khớp |
| Tạo bảng trong demo, chạy DDL | `execute(sql)` | `void` với overload nhận một `String` | Phụ thuộc câu DDL và database; thường không có tập dòng để ánh xạ |
| Cần quyền truy cập mức thấp qua JDBC callback | Overload `execute(ConnectionCallback<T>)` / `execute(PreparedStatementCreator, PreparedStatementCallback<T>)` | `T` do callback trả | Phụ thuộc callback |

**Quy tắc chọn theo ý nghĩa dữ liệu, không theo tên SQL:** `queryForObject` chỉ đúng khi *đúng một dòng* là hợp đồng của use case. Thêm `LIMIT 1` để che việc nhiều dòng có thể là lỗi dữ liệu là một quyết định khác, không nên làm tự động.

## 2. Cơ chế chung của JdbcTemplate

Một dòng chảy điển hình:

```text
Service / Use case
       |
       v
Repository: chọn query/queryForObject/update/execute
       |
       v
JdbcTemplate: tạo Statement/PreparedStatement, bind tham số
       |
       v
DataSource -> JDBC Connection -> JDBC Driver -> Database
       |
       v
ResultSet / số dòng ảnh hưởng / lỗi SQL
       |
       v
JdbcTemplate: map dữ liệu, đóng tài nguyên, dịch lỗi
       |
       v
Repository trả List<T> / T / int / void cho Service
```

`JdbcTemplate` được tạo từ `DataSource`. Khi nó được dùng đúng trong một giao dịch do Spring quản lý, các thao tác JDBC thông thường tham gia connection gắn với transaction hiện tại. Khi không có transaction Spring bao quanh, cách commit mỗi câu lệnh phụ thuộc cấu hình connection/JDBC (thường là auto-commit). **Việc chọn `query` hay `update` không tự đặt toàn bộ quy trình nghiệp vụ vào một transaction.**

Có nhiều overload của từng phương thức. Bài này ưu tiên chữ ký hiện đại quen dùng với `RowMapper`, `Class<T>` và tham số dạng `Object... args`. Với một số overload chỉ nhận SQL tĩnh, Spring có thể dùng JDBC `Statement`; overload có tham số thường tạo `PreparedStatement` và bind dữ liệu.

Từ Spring Framework 5.3, nhiều overload cũ nhận `Object[]` **trước** mapper/type đã bị đánh dấu deprecated; nên dùng thứ tự mới như `queryForObject(sql, String.class, id)` hoặc `queryForObject(sql, bookMapper, id)`.

## 3. query(): khi muốn danh sách hoặc nhiều dòng

### 3.1. Lấy List<T> bằng RowMapper<T>

Ví dụ SQL trả nhiều sách:

```sql
SELECT id, title, price, available
FROM books
WHERE price >= ?
ORDER BY id;
```

Gọi Spring JDBC:

```java
RowMapper<Book> mapper = (rs, rowNum) ->
        new Book(
                rs.getLong("id"),
                rs.getString("title"),
                rs.getInt("price"),
                rs.getBoolean("available"));

List<Book> books = jdbc.query(
        """
        SELECT id, title, price, available
        FROM books
        WHERE price >= ?
        ORDER BY id
        """,
        mapper,
        150);
```

**Đây là đoạn trích minh họa**, giả định `Book` là một record đã khai báo và `jdbc` là bean `JdbcTemplate`. Chương 7 chứa chương trình đầy đủ, biên dịch/chạy được.

`RowMapper<Book>` nhận một `ResultSet` tại dòng hiện tại và chỉ số dòng `rowNum` (bắt đầu từ 0), sau đó tạo **một** đối tượng `Book`. `JdbcTemplate` tự lặp qua các dòng, gọi mapper cho từng dòng và xây danh sách. Không gọi `rs.next()` bên trong `RowMapper`; làm vậy có thể bỏ qua dòng hoặc làm hỏng luồng ánh xạ.

Đặc điểm:

- **0 dòng**: trả `List.of()` về mặt ý nghĩa danh sách rỗng (không cần giả định implementation cụ thể của `List`).
- **1 dòng**: danh sách có đúng một phần tử.
- **N dòng**: danh sách có N phần tử, theo thứ tự kết quả SQL cung cấp.
- Nếu thứ tự quan trọng, phải chỉ định `ORDER BY`. Database không đảm bảo thứ tự ổn định nếu không có điều khoản sắp xếp.
- Nếu đọc hàng triệu dòng vào `List<T>`, bộ nhớ ứng dụng có thể quá tải. Cân nhắc phân trang hoặc callback/stream phù hợp với vòng đời tài nguyên.

### 3.2. RowMapper không phải trình quản lý query

`RowMapper` chịu trách nhiệm chuyển **một dòng** thành đối tượng Java, không quyết định SQL chạy bao nhiêu lần hay có bao nhiêu dòng. Với cột kiểu `NULL`, phải chọn getter và xử lý phù hợp: ví dụ `rs.getInt(...)` trả 0 cả khi dữ liệu thực là NULL, muốn phân biệt phải dùng `rs.wasNull()` hoặc `rs.getObject(..., Integer.class)` khi driver hỗ trợ.

Ví dụ mapper trả record:

```java
record Book(long id, String title, int price, boolean available) {}
```

Nó giả định `price` và `available` đều `NOT NULL` trong schema. Nếu hai cột này nullable, Java model và logic mapping phải thay đổi.

### 3.3. query() không có nghĩa SQL luôn phải trả hơn một dòng

Truy vấn theo một ID chỉ trả tối đa một dòng vẫn **có thể** dùng `query()`:

```java
List<Book> result = jdbc.query(
        "SELECT id, title, price, available FROM books WHERE id = ?",
        mapper,
        42L);
```

Điều này hữu ích khi “không tìm thấy” là kết quả hợp lệ. Khi biết `id` là primary key:

```java
Optional<Book> found = result.stream().findFirst();
```

Đây là đoạn trích; cần `import java.util.Optional;` và `result` đã được gán. Đừng áp dụng `findFirst()` một cách máy móc nếu query có thể trả nhiều dòng mà use case kỳ vọng duy nhất: như vậy bạn đang bỏ qua nguy cơ dữ liệu sai. Nếu thuộc tính phải unique, nên có ràng buộc unique/primary key trong database.

### 3.4. Những overload query khác

Ngoài `RowMapper`, `query` còn có các dạng callback như `ResultSetExtractor<T>` (xử lý toàn bộ `ResultSet` theo ý muốn), `RowCallbackHandler` (xử lý từng dòng, không tự gom thành list) và các overload dùng PreparedStatement. Những công cụ đó phù hợp khi cần tổng hợp dữ liệu đặc biệt hoặc tránh lưu toàn bộ kết quả vào memory. Với CRUD thông thường, `query(sql, RowMapper, args...)` dễ đọc và dễ test nhất.

## 4. queryForObject(): hợp đồng đúng một dòng

### 4.1. Đọc một giá trị đơn

Muốn lấy tên sách bằng khóa chính:

```java
String title = jdbc.queryForObject(
        "SELECT title FROM books WHERE id = ?",
        String.class,
        2L);
```

Overload nhận `Class<T>` này dùng cho kết quả **một dòng, một cột**. Nếu SQL trả hai cột, Spring có thể ném `IncorrectResultSetColumnCountException`. Nếu kiểu chuyển đổi từ JDBC không phù hợp, cũng có thể phát sinh lỗi chuyển đổi/đọc dữ liệu.

Ví dụ tổng số dòng:

```java
Long total = jdbc.queryForObject(
        "SELECT COUNT(*) FROM books",
        Long.class);
```

Vì `COUNT(*)` không có `GROUP BY` trả một dòng tổng hợp ngay cả khi bảng không có dữ liệu, `total` thường là 0 thay vì `EmptyResultDataAccessException`. Đừng nhầm “COUNT bằng 0” với “SQL không trả dòng”.

### 4.2. Ánh xạ một đối tượng có nhiều cột

Nếu query trả một dòng và nhiều cột, dùng overload nhận `RowMapper`:

```java
Book book = jdbc.queryForObject(
        """
        SELECT id, title, price, available
        FROM books
        WHERE id = ?
        """,
        mapper,
        2L);
```

Ở đây `mapper` quyết định cách tạo `Book` từ một dòng, còn `queryForObject` kiểm tra số dòng. `RowMapper` có thể tự trả `null`; nếu query thật sự có một dòng thì giá trị kết quả có thể là `null` mà không phải lỗi “không có dòng”.

### 4.3. Điều gì xảy ra khi có 0, 1 hoặc nhiều dòng?

| Số dòng SQL thực tế | `queryForObject(sql, RowMapper, ...)` | `queryForObject(sql, Class<T>, ...)` |
| --- | --- | --- |
| 0 | Ném `EmptyResultDataAccessException` | Ném `EmptyResultDataAccessException` |
| 1 | Trả object do mapper tạo (có thể `null`) | Trả scalar, có thể `null` nếu SQL NULL; yêu cầu đúng một cột |
| 2 trở lên | Ném `IncorrectResultSizeDataAccessException` | Ném `IncorrectResultSizeDataAccessException` |

`EmptyResultDataAccessException` là một subtype của `IncorrectResultSizeDataAccessException`; nếu muốn catch riêng, đặt nhánh EmptyResult trước nhánh cha.

**Quan trọng:** `queryForObject` **không đơn thuần lấy phần tử đầu tiên**. Nó là phép kiểm tra hợp đồng đúng một dòng. Với truy vấn `SELECT title FROM books WHERE available = TRUE` khi có nhiều sách, gọi `queryForObject` là lựa chọn sai dù SQL hợp lệ. Dùng `query`, hoặc thiết kế query/ràng buộc để thực sự có một dòng.

### 4.4. Không tìm thấy là lỗi hay trạng thái hợp lệ?

Giả sử `findRequiredById(id)` trong nghiệp vụ cho rằng ID phải tồn tại, `queryForObject` phù hợp; service có thể chuyển `EmptyResultDataAccessException` thành ngoại lệ domain.

Nếu API `findById(id)` có thể trả “không có”, có hai cách hợp lý:

1. Dùng `query` với filter theo PK, chuyển danh sách 0/1 phần tử thành `Optional<Book>`.
2. Gọi `queryForObject`, bắt **riêng** `EmptyResultDataAccessException` rồi trả `Optional.empty()`.

Đừng catch chung `DataAccessException` và trả dữ liệu rỗng: điều đó nuốt cả lỗi connection, SQL sai, unique violation hoặc sự cố khác. Tách “không tồn tại” khỏi “database hỏng” giúp nghiệp vụ xử lý đúng.

Một lưu ý khác: thêm `LIMIT 1` chỉ khiến query trả nhiều nhất một dòng; nó **không kiểm chứng được tính duy nhất** của dữ liệu. Nếu muốn chặn duplicate, phải dùng ràng buộc database hoặc chiến lược kiểm tra thực sự đáp ứng yêu cầu.

## 5. update(): INSERT, UPDATE, DELETE và số dòng chịu tác động

`JdbcTemplate.update(...)` thường dùng cho các thao tác thay đổi dữ liệu:

```java
int inserted = jdbc.update(
        "INSERT INTO books (id, title, price, available) VALUES (?, ?, ?, ?)",
        4L, "Data Access", 180, true);

int changed = jdbc.update(
        "UPDATE books SET price = ? WHERE id = ?",
        220, 4L);

int deleted = jdbc.update(
        "DELETE FROM books WHERE id = ?",
        4L);
```

Biến nhận kết quả là `int`, có ý nghĩa **số dòng bị ảnh hưởng** do JDBC driver trả về (với kiểu câu lệnh/cơ sở dữ liệu có thể có khác biệt quy tắc đếm). Đừng đồng nhất giá trị đó với boolean “nghiệp vụ đã thành công”.

### 5.1. Ý nghĩa của kết quả 0, 1, N

- Với `INSERT` một dòng thành công, thông thường trả 1.
- Với `UPDATE ... WHERE id = ?`, **0** thường cho thấy không tìm thấy dòng phù hợp. Không có exception chỉ vì không có gì để cập nhật.
- Với `DELETE ... WHERE id = ?`, **0** thường có nghĩa không tồn tại dòng cần xóa hoặc điều kiện không khớp.
- Với `UPDATE` hoặc `DELETE` điều kiện quá rộng, số dòng bị tác động có thể lớn hơn dự kiến; đây có thể là lỗi nghiêm trọng, đặc biệt nếu quên `WHERE`.

Ví dụ khi nghiệp vụ phải cập nhật đúng một đơn hàng:

```java
int affected = jdbc.update(
        "UPDATE orders SET status = ? WHERE id = ?",
        "PAID",
        orderId);

if (affected != 1) {
    throw new IllegalStateException(
            "Expected one order row, updated " + affected);
}
```

Đây là **đoạn minh họa**, giả định bảng `orders` và biến `orderId` đã có; không phải file Java độc lập. Nếu 0 dòng là kết quả hợp lệ (ví dụ thao tác xóa idempotent), quyết định có báo lỗi hay không phải dựa trên nghiệp vụ.

### 5.2. Dùng row count để tránh lost update

Một cách triển khai optimistic locking là cập nhật có điều kiện theo version:

```sql
UPDATE accounts
SET balance = ?, version = version + 1
WHERE id = ? AND version = ?;
```

Khi gọi `update`, kết quả 1 có nghĩa điều kiện được thỏa và thao tác đã áp dụng trên một dòng; kết quả 0 có thể do dòng không tồn tại hoặc version đã thay đổi bởi giao dịch khác. Service có thể trả lỗi xung đột để client đọc lại dữ liệu. Đây chỉ là ví dụ về **vai trò của affected rows**, không phải thay thế hoàn chỉnh cho mô hình transaction/isolation.

### 5.3. Lấy khóa tự sinh có dùng return của update không?

Không. `int` do `update` trả về là số dòng ảnh hưởng, **không phải ID tự sinh**. Nếu DB tạo ID bằng identity/sequence, Spring JDBC hỗ trợ các overload dùng `PreparedStatementCreator` và `KeyHolder`, hoặc `SimpleJdbcInsert` để lấy generated key. Cần cấu hình driver, tên cột khóa và cách tạo statement phù hợp DBMS. Không suy luận `inserted == generatedId`.

### 5.4. update không tự bao trọn transaction

Hai câu `update` chạy tuần tự không mặc định commit/rollback thành một đơn vị nghiệp vụ. Một service cần bảo đảm tất cả thao tác thành công cùng nhau thường dùng `@Transactional` với transaction manager phù hợp, qua lời gọi do Spring quản lý. Chi tiết được giải thích ở phần 10.

## 6. execute(): thực thi SQL hoặc callback JDBC tổng quát

### 6.1. Overload nhận SQL String

```java
jdbc.execute("""
        CREATE TABLE books (
            id BIGINT PRIMARY KEY,
            title VARCHAR(120) NOT NULL,
            price INT NOT NULL,
            available BOOLEAN NOT NULL
        )
        """);
```

`execute(String sql)` không ánh xạ `ResultSet` sang `List` hay scalar, và overload này trả `void`. Vì vậy nó tiện cho tạo bảng/schema trong demo, hoặc SQL lệnh không cần lấy dữ liệu trả về. Nó **không nên là lựa chọn mặc định** cho `SELECT` chỉ vì tên “execute” nghe chung chung: với `SELECT`, hãy dùng `query`/`queryForObject` nếu cần lấy kết quả. Với DML cần số dòng cập nhật, dùng `update`.

Phân biệt giữa **Spring `JdbcTemplate.execute(String)`** và phương thức **JDBC `Statement.execute(String)`** mức thấp; chúng không có cùng kiểu kết quả. JDBC `Statement.execute` có thể trả boolean để biểu thị dạng kết quả đầu tiên, còn overload Spring `execute(String)` này không trả boolean.

**Không lạm dụng DDL trong ứng dụng production.** Schema thực tế thường do migration tool/đội vận hành quản lý (Flyway, Liquibase hoặc quy trình tương tự), tránh tạo/sửa bảng ngẫu nhiên khi xử lý HTTP request. Tác động transaction của DDL cũng khác nhau tùy DBMS.

### 6.2. Các overload execute nhận callback có mục đích khác

`JdbcTemplate` còn có nhóm overload nhận `ConnectionCallback<T>`, `StatementCallback<T>` hoặc `PreparedStatementCreator` + `PreparedStatementCallback<T>`. Chúng cho phép làm việc ở mức JDBC thấp hơn nhưng vẫn tận dụng quản lý tài nguyên và chuyển dịch exception của Spring.

Ví dụ trích đoạn dùng connection callback để đọc thông tin JDBC driver:

```java
String product = jdbc.execute(
        (ConnectionCallback<String>) connection ->
                connection.getMetaData().getDatabaseProductName());
```

Đây **không phải chương trình độc lập**; cần biến `jdbc` là `JdbcTemplate` và import `org.springframework.jdbc.core.ConnectionCallback`. Overload callback có thể trả `String`/`T` do callback cung cấp, trái với `void execute(String sql)`.

Cần dùng callback khi có yêu cầu JDBC thực sự đặc biệt, không phải để tự viết lại toàn bộ `ResultSet` loop cho CRUD thông thường. Nếu callback nhận connection của transaction, không tự đóng connection mà Spring đang quản lý; để framework xử lý vòng đời tài nguyên theo hợp đồng callback.

### 6.3. execute không “bỏ qua” database

Dù trả `void`, lệnh vẫn được gửi tới database. SQL không hợp lệ, thiếu quyền hay lỗi cấu trúc dữ liệu vẫn có thể ném `DataAccessException`. Với callback, lệnh có thể đọc/ghi tùy logic callback, vì vậy phải đọc code và xác định tác động trước khi dùng trong hệ thống thật.

## 7. Bind tham số và chuyển kiểu dữ liệu

### 7.1. Dùng placeholder cho giá trị do người dùng cung cấp

```java
List<Book> books = jdbc.query(
        "SELECT id, title, price, available FROM books WHERE title = ?",
        mapper,
        userTitle);
```

Đoạn trích giả định `mapper`, `userTitle` hợp lệ. Placeholder `?` giúp tách dữ liệu người dùng khỏi câu SQL. Cách này đúng cho `query`, `queryForObject` và `update` khi sử dụng overload nhận tham số. Không ghép `" ... WHERE title = '" + userTitle + "'"` vì rủi ro SQL injection và xử lý dấu nháy sai.

Placeholder **không thay thế tên bảng, tên cột, hướng `ASC`/`DESC` hoặc toàn bộ câu lệnh SQL**. Khi cần sắp xếp theo tên cột động, chọn trong allowlist những cột/hướng cho phép, rồi mới tạo cấu trúc SQL tương ứng.

### 7.2. Chú ý kiểu dữ liệu JDBC

`JdbcTemplate` thường để JDBC driver tự suy ra kiểu SQL từ giá trị Java khi bind `Object... args`. Với `null`, kiểu đặc biệt hoặc timestamp, đôi lúc cần cung cấp `SQLType` rõ ràng bằng `SqlParameterValue`, `PreparedStatementSetter` hoặc cấu hình phù hợp. Với `ResultSet`, getters trả giá trị primitive có thể che thông tin SQL NULL; dùng kiểu wrapper hoặc kiểm tra `wasNull()` khi cần.

Đọc `TIMESTAMP`/`TIMESTAMP WITH TIME ZONE` phải xác định timezone, kiểu Java (`Instant`, `LocalDateTime`, `OffsetDateTime`...) và behavior của JDBC driver. Ví dụ demo dùng số nguyên/boolean để tập trung vào ý nghĩa bốn phương thức.

### 7.3. Lỗi từ database không biến mất

Spring chuyển nhiều `SQLException` thành phân cấp `DataAccessException` (unchecked). Ví dụ: trùng primary key, SQL sai, connection failure hay lỗi ràng buộc khác. Không catch chung rồi trả danh sách rỗng hoặc 0; chỉ chuyển những lỗi mà tầng nghiệp vụ có thể xử lý với ý nghĩa đúng. Log đủ thông tin để chẩn đoán nhưng không để lộ secrets hay dữ liệu nhạy cảm.

## 8. Ví dụ chạy được: Java 17, Spring JdbcTemplate và H2

Ví dụ dưới đây cho thấy **đủ cả bốn nhóm phương thức** với dữ liệu và kết quả xác định. Dùng **Java 17+**, Spring Framework **6.2.12**, Gradle và H2 in-memory. Không cần Spring Boot, Docker hay cài database bên ngoài.

### 8.1. Cấu trúc thư mục

```text
jdbc-operations-demo/
├── build.gradle
└── src/main/java/example/JdbcTemplateOperationsDemo.java
```

### 8.2. Cấu hình build.gradle

```groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.12'
    implementation 'org.springframework:spring-jdbc:6.2.12'
    runtimeOnly 'com.h2database:h2:2.3.232'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'example.JdbcTemplateOperationsDemo'
}
```

`spring-jdbc` cung cấp `JdbcTemplate` và các loại callback/exception liên quan. `spring-context` cung cấp Spring container và annotation `@Configuration`, `@Bean`. H2 là JDBC driver + database chạy lúc thực thi, nên đặt trong `runtimeOnly` phù hợp ví dụ này.

### 8.3. File Java hoàn chỉnh

Tạo `src/main/java/example/JdbcTemplateOperationsDemo.java`:

```java
package example;

import java.util.List;
import javax.sql.DataSource;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.dao.EmptyResultDataAccessException;
import org.springframework.dao.IncorrectResultSizeDataAccessException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.RowMapper;
import org.springframework.jdbc.datasource.DriverManagerDataSource;

@Configuration
public class JdbcTemplateOperationsDemo {

    @Bean
    DataSource dataSource() {
        DriverManagerDataSource ds = new DriverManagerDataSource();
        ds.setDriverClassName("org.h2.Driver");
        ds.setUrl("jdbc:h2:mem:jdbc_operations;DB_CLOSE_DELAY=-1");
        ds.setUsername("sa");
        ds.setPassword("");
        return ds;
    }

    @Bean
    JdbcTemplate jdbcTemplate(DataSource dataSource) {
        return new JdbcTemplate(dataSource);
    }

    record Book(long id, String title, int price, boolean available) {}

    private static final RowMapper<Book> BOOK_MAPPER = (rs, rowNum) ->
            new Book(
                    rs.getLong("id"),
                    rs.getString("title"),
                    rs.getInt("price"),
                    rs.getBoolean("available"));

    public static void main(String[] args) {
        try (var context =
                     new AnnotationConfigApplicationContext(
                             JdbcTemplateOperationsDemo.class)) {

            JdbcTemplate jdbc = context.getBean(JdbcTemplate.class);

            // execute(String): schema DDL, không cần nhận dữ liệu kết quả.
            jdbc.execute("""
                    CREATE TABLE books (
                        id BIGINT PRIMARY KEY,
                        title VARCHAR(120) NOT NULL,
                        price INT NOT NULL,
                        available BOOLEAN NOT NULL
                    )
                    """);

            // update(String, Object...): INSERT, nhận số dòng ảnh hưởng.
            int a = jdbc.update(
                    "INSERT INTO books (id, title, price, available) VALUES (?, ?, ?, ?)",
                    1L, "Java Basics", 100, true);

            int b = jdbc.update(
                    "INSERT INTO books (id, title, price, available) VALUES (?, ?, ?, ?)",
                    2L, "Spring JDBC", 200, true);

            int c = jdbc.update(
                    "INSERT INTO books (id, title, price, available) VALUES (?, ?, ?, ?)",
                    3L, "SQL Patterns", 150, false);

            System.out.println("inserted=" + (a + b + c));

            // query: nhiều dòng, RowMapper chuyển từng dòng thành Book.
            List<Book> list = jdbc.query(
                    """
                    SELECT id, title, price, available
                    FROM books
                    WHERE price >= ?
                    ORDER BY id
                    """,
                    BOOK_MAPPER,
                    150);

            System.out.println("query=" + list);

            // queryForObject với RowMapper: đúng 1 dòng, nhiều cột.
            Book one = jdbc.queryForObject(
                    "SELECT id, title, price, available FROM books WHERE id = ?",
                    BOOK_MAPPER,
                    2L);
            System.out.println("one=" + one);

            // queryForObject với Class<T>: đúng 1 dòng, 1 cột.
            String title = jdbc.queryForObject(
                    "SELECT title FROM books WHERE id = ?",
                    String.class,
                    1L);
            System.out.println("title=" + title);

            Long count = jdbc.queryForObject(
                    "SELECT COUNT(*) FROM books",
                    Long.class);
            System.out.println("count=" + count);

            // update với UPDATE, kể cả trường hợp không có dòng khớp.
            int updated = jdbc.update(
                    "UPDATE books SET price = ? WHERE id = ?",
                    225,
                    2L);

            int missingUpdated = jdbc.update(
                    "UPDATE books SET price = ? WHERE id = ?",
                    999,
                    42L);

            System.out.println(
                    "updated=" + updated + ",missingUpdated=" + missingUpdated);

            // update với DELETE.
            int deleted = jdbc.update(
                    "DELETE FROM books WHERE id = ?",
                    3L);
            System.out.println("deleted=" + deleted);

            // query không có dòng: List rỗng, không phải exception.
            List<Book> empty = jdbc.query(
                    """
                    SELECT id, title, price, available
                    FROM books
                    WHERE price > ?
                    ORDER BY id
                    """,
                    BOOK_MAPPER,
                    1000);
            System.out.println("emptyQuery=" + empty.size());

            // queryForObject không có dòng: ngoại lệ.
            try {
                jdbc.queryForObject(
                        "SELECT title FROM books WHERE id = ?",
                        String.class,
                        999L);
            } catch (EmptyResultDataAccessException ex) {
                System.out.println(
                        "missingOne=EmptyResultDataAccessException");
            }

            // queryForObject có > 1 dòng: ngoại lệ.
            // Ở thời điểm này còn 2 sách (ID 1 và 2).
            try {
                jdbc.queryForObject(
                        "SELECT title FROM books",
                        String.class);
            } catch (IncorrectResultSizeDataAccessException ex) {
                System.out.println(
                        "multiple=IncorrectResultSizeDataAccessException");
            }

            System.out.println(
                    "finalCount=" + jdbc.queryForObject(
                            "SELECT COUNT(*) FROM books",
                            Long.class));
        }
    }
}
```

Trong chương trình này, `@Bean` khai báo một `DataSource` H2 và một `JdbcTemplate`. Chỉ có một bean `DataSource`, nên tham số `DataSource dataSource` được Spring phân giải duy nhất. Không cần `@Qualifier`; import `Qualifier` trong ví dụ này không được sử dụng và có thể bỏ khi chép code vào dự án thật.

`BOOK_MAPPER` ánh xạ cột từ `ResultSet` sang Java record. Bảng `books` quy định các cột `price`, `available` là `NOT NULL` nên ánh xạ về `int` và `boolean` không mất thông tin NULL. `JdbcTemplate` quản lý vòng đời JDBC qua `DataSource` mà không cần viết `Connection.close()` trong từng query.

**Giới hạn demo:** `DriverManagerDataSource` tạo kết nối mới theo yêu cầu, không phải connection pool tối ưu cho production. `DB_CLOSE_DELAY=-1` cho phép H2 in-memory tồn tại giữa các lần đóng connection trong cùng JVM; dữ liệu biến mất sau khi tiến trình kết thúc.

### 8.4. Chạy chương trình và kiểm tra stdout

Trong thư mục dự án có `build.gradle`, chạy:

```bash
gradle run
```

Nếu có Gradle Wrapper trong dự án, dùng `./gradlew run` trên Linux/macOS hoặc `gradlew.bat run` trên Windows. Gradle có thể in log build riêng; **các dòng do Java `System.out.println` phát ra** theo thứ tự là:

```text
inserted=3
query=[Book[id=2, title=Spring JDBC, price=200, available=true], Book[id=3, title=SQL Patterns, price=150, available=false]]
one=Book[id=2, title=Spring JDBC, price=200, available=true]
title=Java Basics
count=3
updated=1,missingUpdated=0
deleted=1
emptyQuery=0
missingOne=EmptyResultDataAccessException
multiple=IncorrectResultSizeDataAccessException
finalCount=2
```

**Đối chiếu với câu SQL từng bước:**

1. `execute(...)` tạo bảng. Ba lần `update(INSERT)` chèn sách 1, 2, 3; tổng ba lần ảnh hưởng là 3.
2. `query(...)` với `price >= 150` lấy sách ID 2 (200) và ID 3 (150). `ORDER BY id` bảo đảm trình tự in ID 2 rồi ID 3.
3. `queryForObject(..., BOOK_MAPPER, 2L)` trả một `Book`; overload `String.class` trả tên của ID 1. `COUNT(*)` bằng 3.
4. `update(UPDATE)` đổi giá sách 2 thành 225 và trả 1; cập nhật ID 42 không tồn tại trả 0.
5. `update(DELETE)` xóa sách 3 và trả 1. Truy vấn `price > 1000` không có sách nào nên `query` trả danh sách rỗng.
6. `queryForObject` theo ID 999 ném ngoại lệ không có dòng. `queryForObject` không có `WHERE` tìm tên từ **hai dòng** còn lại nên ném ngoại lệ kích thước kết quả.
7. `COUNT(*)` cuối cùng bằng 2.

Ở đây `queryForObject` ném ngoại lệ do kết quả sai **số dòng**, khác với `update` trả 0 khi câu UPDATE không tìm thấy dòng. Đó là điểm cần nhớ khi viết service.

### 8.5. Một cách kiểm tra lỗi thường gặp

Thử sửa `jdbc.query(...)` trong chương trình thành `jdbc.queryForObject(...)` cho câu `price >= 150`. Vì ban đầu có hai sách thỏa điều kiện, cách gọi chỉ kỳ vọng một dòng sẽ ném `IncorrectResultSizeDataAccessException`. Sửa lại bằng `query`. Ngược lại, nếu định nghĩa API `findRequiredById` thì dùng `queryForObject` với ID unique và xử lý ngoại lệ một cách có chủ đích.

## 9. Viết Repository: đưa lựa chọn phương thức về đúng nơi

Trong ứng dụng thực tế, controller không nên tự biết SQL và cách tạo `RowMapper`. Một repository Spring JDBC có thể định nghĩa các use case đọc/ghi rõ ràng:

```java
@Repository
public class BookRepository {
    private final JdbcTemplate jdbc;

    public BookRepository(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public List<Book> findAffordable(int maxPrice) {
        return jdbc.query(
                """
                SELECT id, title, price, available
                FROM books
                WHERE price <= ?
                ORDER BY id
                """,
                BOOK_MAPPER,
                maxPrice);
    }

    public Book requireById(long id) {
        return jdbc.queryForObject(
                "SELECT id, title, price, available FROM books WHERE id = ?",
                BOOK_MAPPER,
                id);
    }

    public int changePrice(long id, int newPrice) {
        return jdbc.update(
                "UPDATE books SET price = ? WHERE id = ?",
                newPrice, id);
    }
}
```

Đây là **đoạn minh họa, không phải file Java độc lập**: giả định đã có `Book`, `BOOK_MAPPER`, các import `Repository`/`JdbcTemplate`/`List` và table `books`. Khi tổ chức mã thật, nên đưa `RowMapper` dùng chung vào repository hoặc class riêng, và khai báo kiểu record ở vị trí có thể dùng từ repository.

Với repository:

- `findAffordable` trả danh sách, kể cả rỗng.
- `requireById` thể hiện rõ hợp đồng “bắt buộc có một sách”.
- `changePrice` trả affected rows để service quyết định 0 dòng có phải lỗi.
- DDL được quản lý khi khởi tạo/migration schema, không đặt trong method xử lý từng request.

Nếu việc tìm sách theo ID **có thể không tồn tại** là bình thường, có thể đổi API thành `Optional<Book> findById(long id)` và dùng `query` 0/1 dòng như đã giải thích, hoặc bắt riêng `EmptyResultDataAccessException`.

## 10. Transaction: phương thức nào nằm trong giao dịch?

Bốn phương thức `JdbcTemplate` chỉ quyết định cách thực thi một thao tác. Khi nghiệp vụ gồm nhiều bước cần commit hoặc rollback cùng nhau, ranh giới transaction thường thuộc tầng service:

```java
@Service
public class OrderService {
    private final OrderRepository orders;
    private final InventoryRepository inventory;

    public OrderService(
            OrderRepository orders,
            InventoryRepository inventory) {
        this.orders = orders;
        this.inventory = inventory;
    }

    @Transactional
    public void placeOrder(long productId, int quantity) {
        inventory.decreaseStock(productId, quantity);
        orders.insertOrder(productId, quantity);
    }
}
```

Đây là **mẫu thiết kế minh họa**; `OrderRepository`, `InventoryRepository` chưa được định nghĩa nên không thể biên dịch như một file độc lập. Nó cần Spring-managed service, transaction management được bật và transaction manager phù hợp, đồng thời các repository dùng resource tham gia cùng transaction.

Điểm kỹ thuật:

- Với Spring JDBC đơn nguồn, `DataSourceTransactionManager` hoặc `JdbcTransactionManager` có thể quản lý transaction gắn với `DataSource` tương ứng.
- `JdbcTemplate` tận dụng Spring transaction synchronization để dùng connection được gắn với thread/transaction hiện tại. Tự mở `dataSource.getConnection()` không đúng cơ chế có thể khiến truy vấn nằm ngoài transaction.
- `@Transactional` trong chế độ proxy mặc định yêu cầu lời gọi đi qua bean Spring proxy; self-invocation trong cùng object thường không kích hoạt transaction advice.
- Mặc định, transaction declarative rollback với `RuntimeException` và `Error`, không tự rollback mọi checked exception; cấu hình `rollbackFor` khi thật sự cần.
- Transaction local của một `DataSource` không bảo đảm atomic commit trên hai database khác nhau. Nếu có nhiều nguồn, phải chọn manager đúng và thiết kế nhất quán liên hệ thống.
- `@Transactional(readOnly = true)` là một gợi ý/cấu hình hỗ trợ đọc, không thay thế quyền database hoặc bảo đảm lệnh `update` sẽ luôn bị chặn.

## 11. Lỗi cần phân biệt trước khi xử lý

| Tình huống | Biểu hiện | Quyết định hợp lý |
| --- | --- | --- |
| `query` trả 0 dòng | Danh sách rỗng | Hiển thị “không có kết quả”/trả collection trống |
| `queryForObject` trả 0 dòng | `EmptyResultDataAccessException` | Nếu bắt buộc có thì báo not found; nếu không thì chuyển thành Optional |
| `queryForObject` trả >1 dòng | `IncorrectResultSizeDataAccessException` | Kiểm tra SQL, ràng buộc unique, dữ liệu; không tùy tiện lấy dòng đầu |
| `queryForObject(sql, Class<T>)` trả >1 cột | `IncorrectResultSetColumnCountException` | Chọn một cột hoặc đổi sang `RowMapper` |
| `queryForObject` có một dòng nhưng SQL giá trị NULL | Có thể trả `null` | Phân biệt với không có dòng; thiết kế nullable rõ |
| `update` không có dòng phù hợp | Trả 0 | Tùy use case: có thể no-op, not found hoặc conflict |
| `update` tác động nhiều dòng ngoài dự kiến | Trả N > mong đợi | Kiểm tra `WHERE`, khóa, transaction và dữ liệu |
| SQL, unique/FK, connection hoặc permission lỗi | Một subtype `DataAccessException` | Xử lý theo phân loại lỗi, không biến thành “không tìm thấy” |
| `execute` chạy DDL không hợp lệ | Có thể ném exception | Sửa schema/DDL/migration; không xem là lỗi truy vấn không có dữ liệu |

Nhớ rằng Spring exception **không đồng nghĩa** luôn có thể retry. Vi phạm unique constraint không nên retry vô hạn; lỗi kết nối tạm thời có thể retry nếu thao tác được thiết kế idempotent và có chính sách giới hạn.

## 12. Hiệu năng và an toàn trong ứng dụng thật

**Chỉ lấy thứ cần dùng.** Ưu tiên tên cột rõ thay cho `SELECT *` khi cần mapping ổn định. Thêm điều kiện lọc và `ORDER BY` phù hợp, dùng pagination cho bảng lớn thay vì đưa toàn bộ dữ liệu vào `List`.

**Cẩn thận query trong vòng lặp.** Một `queryForObject` theo từng ID trong 1.000 phần tử tạo 1.000 database round trips. Cân nhắc truy vấn theo tập, batch query hoặc thiết kế join/projection phù hợp.

**Chủ động kiểm soát dữ liệu quá lớn.** `query(...)` với `RowMapper` gom kết quả vào list; với tập dữ liệu rất lớn, dùng phân trang hoặc callback/stream có quản lý tài nguyên đúng thay vì tự xây một list khổng lồ.

**Quan sát SQL đúng lớp.** Spring JDBC có thể log SQL ở mức DEBUG (thường category `org.springframework.jdbc.core.JdbcTemplate`), nhưng không tự kết luận thời gian database chỉ từ một log. Xem query plan, index, connection pool, số lần query, network và locking khi endpoint chậm. Tránh ghi log giá trị PII, mật khẩu, token hoặc thông tin nhạy cảm.

**Đừng đồng nhất execute với update.** `execute` không tự trả số dòng bị tác động; nếu nghiệp vụ cần xác minh chính xác một dòng bị thay đổi, `update` phù hợp hơn. Không chạy DDL tùy tiện ở production.

**Kiểm tra bằng database thực tế.** H2 giúp học API nhưng không giống mọi DBMS về SQL dialect, kiểu dữ liệu, transaction và generated keys. Với ứng dụng vận hành trên PostgreSQL/MySQL, nên có integration test trên engine tương ứng, ví dụ qua Testcontainers.

## 13. Những lỗi tư duy phổ biến

| Hiểu nhầm | Cách hiểu đúng |
| --- | --- |
| “`query` luôn trả ít nhất một dòng.” | Không, không có dòng thì trả list rỗng. |
| “`queryForObject` lấy dòng đầu tiên.” | Không, nó yêu cầu đúng một dòng; 0 hoặc >1 là ngoại lệ. |
| “`queryForObject(sql, Long.class)` dùng được cho mọi SELECT.” | Chỉ phù hợp kết quả một dòng, một cột chuyển được về `Long`. |
| “`COUNT(*) = 0` sẽ ném `EmptyResultDataAccessException`.” | Không có `GROUP BY`, COUNT trả một dòng chứa 0. |
| “`update` trả generated ID.” | Nó trả số dòng affected; lấy ID cần `KeyHolder` hoặc giải pháp tương đương. |
| “`update` trả 0 tức là lỗi SQL.” | Có thể SQL hợp lệ nhưng không khớp dữ liệu. |
| “`execute` là cách tốt nhất cho mọi SQL.” | Với dữ liệu đọc/ghi thông thường, chọn `query`/`queryForObject`/`update` theo hợp đồng. |
| “`RowMapper` phải gọi `rs.next()`.” | `JdbcTemplate` đã duyệt từng dòng trước khi gọi mapper. |
| “Bốn phương thức tự tạo một transaction nghiệp vụ.” | Transaction boundary cần được cấu hình/điều phối riêng. |
| “Catch `DataAccessException` và trả rỗng là an toàn.” | Cách đó che mất lỗi database, làm sai ý nghĩa nghiệp vụ. |

## 14. Tự kiểm tra kiến thức

1. Một màn hình tìm kiếm có thể không có kết quả hoặc có hàng trăm sách. Chọn `query` hay `queryForObject`? Vì sao?
2. Một API “lấy đơn hàng bắt buộc theo primary key” cần xử lý trường hợp 0, 1 và nhiều dòng ra sao?
3. Vì sao `SELECT COUNT(*)` không có `GROUP BY` thường khác với `SELECT title WHERE id = ?` khi không có dữ liệu?
4. Với `UPDATE books SET price=? WHERE id=?`, `int affected=0` có đồng nghĩa cú pháp SQL sai không?
5. Khi cần khóa chính được tạo tự động, vì sao `update` return 1 không thể dùng làm ID?
6. Khi nào `execute(String)` phù hợp hơn `update(String, Object...)`?
7. Tại sao mapper không nên tự gọi `rs.next()`?
8. Khi cập nhật tồn kho rồi tạo đơn hàng, cách nào đảm bảo rollback cả hai thao tác khi lỗi?
9. Nếu query trả một dòng với cột SQL NULL, kết quả của overload scalar có thể là gì?
10. Có thể bắt `EmptyResultDataAccessException` để trả Optional.empty() được không? Vì sao không nên catch mọi `DataAccessException` để làm việc đó?

**Ghi nhớ:** `query` phản ánh tập kết quả **0..N dòng**; `queryForObject` diễn tả **đúng một dòng**; `update` diễn tả **ghi dữ liệu và đếm dòng chịu tác động**; `execute` là đường chạy SQL/callback mức thấp cho các nhu cầu còn lại. Chọn phương thức theo hợp đồng dữ liệu, sau đó xử lý cardinality, lỗi, tham số và transaction một cách rõ ràng.

### Tài liệu chính thức để tra cứu

- Spring Framework — [JDBC Core: Querying, Updating, JdbcTemplate](https://docs.spring.io/spring-framework/reference/6.2/data-access/jdbc/core.html).
- Spring Framework — [JdbcTemplate Javadoc 6.2](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jdbc/core/JdbcTemplate.html).
- Spring Framework — [JdbcOperations Javadoc 6.2](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jdbc/core/JdbcOperations.html).
- Spring Framework — [Transaction Management](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction.html).
