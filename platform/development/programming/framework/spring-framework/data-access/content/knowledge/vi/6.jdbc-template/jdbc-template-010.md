# Nhận diện RdbmsOperation và các lớp biểu diễn thao tác SQL khi đọc mã Spring JDBC hiện có

> **Mục tiêu:** Khi gặp các lớp `RdbmsOperation`, `MappingSqlQuery`, `SqlUpdate`, `BatchSqlUpdate` hoặc `StoredProcedure` trong một codebase, bạn phân biệt được từng loại thao tác, lần theo nơi cấu hình SQL và tham số, xác định lúc thật sự chạy SQL, đọc đúng kiểu kết quả và ranh giới giao dịch. Bài này tập trung vào **đọc và bảo trì mã hiện có**, đồng thời minh họa bằng project Java 17+ có thể chạy.

Các lớp này thuộc `org.springframework.jdbc.object` của **Spring Framework JDBC**. Chúng có thể vẫn xuất hiện trong dự án lâu năm dù code mới thường ưu tiên `JdbcTemplate`, `JdbcClient` hoặc `SimpleJdbcCall`. Không đánh đồng chúng với Spring Data Repository hay ORM/Hibernate.

## 1. Ý tưởng cốt lõi của RdbmsOperation

`RdbmsOperation` là **abstract class** biểu diễn một thao tác trên relational database dưới dạng **đối tượng cấu hình một lần rồi sử dụng nhiều lần**. Thao tác có thể là SELECT, INSERT/UPDATE/DELETE hoặc stored procedure. Nó **không** phải JDBC `Connection`/`Statement`, không trực tiếp đại diện cho một transaction nghiệp vụ và không yêu cầu có JPA.

Mẫu tư duy:

```text
Khởi tạo một operation:
  DataSource hoặc JdbcTemplate
       + SQL / procedure name
       + SqlParameter / SqlOutParameter
       + mapper hoặc các option
               |
            compile()
               |
          sẵn sàng sử dụng
               |
        execute/findObject/update
               |
         Spring JDBC / JdbcTemplate
               |
      JDBC PreparedStatement / CallableStatement
               |
            database
               |
       kết quả + cleanup
```

Nhìn thấy constructor hoặc `compile()` **chưa chứng minh SQL đã chạy**. Chỉ khi caller thực hiện `execute`, `findObject`, `update` hay API thực thi phù hợp, operation mới truy cập database.

Các trách nhiệm chung thường xuất hiện khi đọc `RdbmsOperation`:

- `setDataSource(DataSource)` hoặc `setJdbcTemplate(JdbcTemplate)`: xác định nguồn kết nối và hạ tầng JDBC sử dụng.
- `setSql(String)` và `getSql()`: câu SQL hoặc tên routine trong một số lớp.
- `declareParameter(SqlParameter)`, `setParameters(...)`, `setTypes(...)`: khai báo JDBC type và thứ tự tham số.
- `compile()`, `isCompiled()`, `afterPropertiesSet()`: hoàn tất metadata/configuration trước khi dùng.
- `setQueryTimeout(...)`, `setFetchSize(...)`, `setMaxRows(...)`: cấu hình hành vi JDBC theo driver và transaction.
- `setReturnGeneratedKeys(...)`, `setGeneratedKeysColumnNames(...)`: cấu hình generated key cho trường hợp được hỗ trợ.

RDBMS operation classes dùng hạ tầng `JdbcTemplate`, nên được hưởng xử lý resource và cơ chế `DataAccessException` của Spring JDBC. Bản thân object đã cấu hình thường được chia sẻ/tái sử dụng an toàn, **ngoại trừ `BatchSqlUpdate` không thread-safe**.

## 2. Cây kế thừa: đọc tên lớp là nhận diện thao tác

```text
RdbmsOperation [abstract]
|
+-- SqlOperation [abstract: SQL query/update]
|   |
|   +-- SqlQuery<T> [abstract: truy vấn SELECT]
|   |   |
|   |   +-- GenericSqlQuery<T> [concrete + RowMapper]
|   |   +-- MappingSqlQueryWithParameters<T> [abstract]
|   |   |     |
|   |   |     +-- MappingSqlQuery<T> [abstract]
|   |   |           |
|   |   |           +-- SqlFunction<T>
|   |   +-- UpdatableSqlQuery<T>
|   |
|   +-- SqlUpdate [concrete: INSERT/UPDATE/DELETE]
|         |
|         +-- BatchSqlUpdate [có hàng đợi batch]
|
+-- SqlCall [abstract: CallableStatement]
      |
      +-- StoredProcedure [abstract]
            |
            +-- GenericStoredProcedure [concrete]
```

| Lớp | Dấu hiệu khi đọc code | Kiểu trả về/tác động chính |
| --- | --- | --- |
| `RdbmsOperation` | Base class, cấu hình datasource/SQL/parameters | Không có một kiểu execute chung cho mọi nhánh |
| `SqlOperation` | Abstract class giữa base và SQL thông thường | Chuẩn bị `PreparedStatement` |
| `SqlQuery<T>` | `execute(...)`, `findObject(...)` | `List<T>`; `T` hoặc `null` |
| `MappingSqlQuery<T>` | Subclass override `mapRow(ResultSet,int)` | Một DTO/domain object mỗi hàng |
| `MappingSqlQueryWithParameters<T>` | Mapper còn nhận `parameters` và `context` | Từng object có thể dùng context |
| `GenericSqlQuery<T>` | `setRowMapper(...)`, không cần subclass | Query ánh xạ với RowMapper |
| `SqlUpdate` | `update(...)`, `setRequiredRowsAffected(...)` | `int` số hàng ảnh hưởng |
| `BatchSqlUpdate` | `setBatchSize`, `update`, `flush`, `reset` | Hàng đợi và kết quả thực thi batch |
| `SqlCall` / `StoredProcedure` | `setFunction`, IN/OUT parameters | `Map<String,Object>` của procedure |
| `GenericStoredProcedure` | Stored procedure định nghĩa bằng cấu hình | Output Map |
| `SqlFunction<T>` | Lớp nằm dưới `MappingSqlQuery<T>` | Wrapper truy vấn SQL giá trị |
| `UpdatableSqlQuery<T>` | Override `updateRow`, updatable ResultSet | Trường hợp đặc biệt, ít gặp |

**Phân biệt tên:** `SqlFunction` nằm dưới nhánh `SqlQuery`, còn một *stored function* có thể được khai báo bằng `StoredProcedure` + `setFunction(true)`. Không suy luận hai kiểu có cùng cách gọi chỉ vì tên đều chứa “function”.

## 3. Bảy câu hỏi để đọc bất kỳ RDBMS operation nào

Khi mở file Java, XML bean hoặc code cấu hình Spring, lần theo:

1. **Class thật là gì?** `SqlQuery`, `SqlUpdate` hay `SqlCall`? Field khai báo kiểu cha có thể giữ subclass khác nhau, nên tìm nơi tạo object.
2. **Object được tạo ở đâu?** `new` trong constructor DAO, `@Bean` method, XML bean definition hay factory? Một operation reusable nên thường khởi tạo một lần.
3. **SQL nằm ở đâu?** `super(dataSource, sql)`, `setSql`, property XML, constant hoặc config file? Với `StoredProcedure`, `sql` thường là *tên routine*.
4. **Tham số là gì?** Số dấu `?`, `declareParameter`, JDBC `Types`, thứ tự truyền, named variants; procedure còn có IN/OUT/INOUT.
5. **Compile lúc nào?** `compile()` trong constructor/`@Bean` hay `InitializingBean.afterPropertiesSet()` khi bean được khởi tạo?
6. **Thực thi và lấy kết quả ở đâu?** `execute` cho list/procedure, `findObject` cho một hàng, `update` cho count; mapper nào chuyển `ResultSet` thành object?
7. **Giao dịch do ai quản lý?** Lời gọi từ `@Transactional` service, datasource/transaction manager nào, có cùng transaction hay chỉ từng query độc lập?

Với code dài, có thể ghi ra luồng:

```text
Controller/Job -> Service
                   |
                   +-> Dao.find...()
                         |
                         +-> MappingSqlQuery.execute(id)
                               |
                               +-> SQL SELECT + RowMapper
                   |
                   +-> Dao.update...()
                         |
                         +-> SqlUpdate.update(values...)
                               |
                               +-> SQL UPDATE + affected rows
                   |
              transaction boundary ở service nếu cần
```

Tên `FindOrderQuery` hay `DeactivateUser` chỉ là gợi ý; **SQL và class kế thừa mới quyết định bản chất thao tác**.

## 4. Thứ tự cấu hình và ý nghĩa thực của compile()

Một đoạn code minh họa:

```java
// Snippet trong cấu hình/DAO đã có DataSource ds.
SqlUpdate update = new SqlUpdate(ds,
        "UPDATE books SET title = ? WHERE id = ?");
update.declareParameter(new SqlParameter("title", Types.VARCHAR));
update.declareParameter(new SqlParameter("id", Types.BIGINT));
update.setRequiredRowsAffected(1);
update.compile();

int affected = update.update("New title", 10L);
```

- `new SqlUpdate` và `declareParameter` chỉ cấu hình operation.
- `SqlParameter` thuộc `org.springframework.jdbc.core`, `Types` thuộc `java.sql`. Những khai báo này mô tả SQL type chứ không tự thực thi.
- `compile()` chuẩn bị metadata / statement creator factory của Spring. **Nó không phải Java compilation và không mặc định gửi SQL sang database để chạy optimizer hoặc kiểm tra dữ liệu.**
- `update("New title", 10L)` mới chạy DML; thứ tự bind là title trước, id sau.
- `setRequiredRowsAffected(1)` yêu cầu UPDATE ảnh hưởng đúng một hàng, không phải “chỉ thực thi một lần”.

### Lifecycle khi operation là Spring bean

`RdbmsOperation` triển khai `InitializingBean` và có `afterPropertiesSet()` bảo đảm compilation. Do đó, trong codebase có thể **không thấy `compile()` tường minh** nếu property injection và bean initialization đã thực hiện nó. Một số đường thực thi cũng có kiểm tra và biên dịch lười. Khi đọc mã hãy tìm toàn bộ configuration trước khi báo “quên compile”.

**Không thay `setSql`, `declareParameter`, mapper hoặc các setter cấu hình trên cùng singleton khi nhiều thread đang dùng.** Mô hình là cấu hình trước, tái sử dụng sau.

## 5. Nhận diện các kiểu tham số

**Positional parameters:** SQL chứa `?`, các giá trị ở `update(v1, v2)` hay `execute(v1, v2)` được bind theo vị trí. Thứ tự `declareParameter` quan trọng.

```java
// Snippet minh họa, DataSource ds và imports cần được cung cấp.
SqlUpdate setStatus = new SqlUpdate(
        ds, "UPDATE orders SET status = ? WHERE id = ?");
setStatus.declareParameter(
        new SqlParameter("status", Types.VARCHAR));
setStatus.declareParameter(
        new SqlParameter("id", Types.BIGINT));
setStatus.compile();

int count = setStatus.update("PAID", 42L);
```

**Chú ý:** đặt tên `"status"` cho `SqlParameter` không tự biến SQL `?` thành `:status`. Các phương thức `executeByNamedParam(Map)` / `updateByNamedParam(Map)` có contract named parameter; hãy đọc SQL/cấu hình của lớp và overload đang gọi. `StoredProcedure.execute(Map)` có semantics khai báo procedure IN/OUT, không nên nhầm với map context của `SqlQuery.execute(..., context)`.

**Không lấy kiểu Java làm JDBC type một cách tùy tiện:** `java.sql.Types.BIGINT`, `VARCHAR`, `TIMESTAMP`, `DECIMAL` v.v. tương ứng với SQL parameter metadata; đặc biệt chú ý SQL NULL, decimal scale, timezone và các custom vendor types.

Các lỗi điển hình khi đọc hoặc sửa code:

- SQL có hai dấu `?` nhưng chỉ khai báo một tham số hoặc truyền nhầm thứ tự.
- Người gọi truyền `id` trước `status` dù SQL cần status trước.
- `Types` khai báo sai, driver không thể bind/convert.
- Đổi `WHERE` hoặc thêm placeholder nhưng không cập nhật `declareParameter`.
- Nhầm positional API với map named API, hoặc khai báo tên giống nhau ở procedure IN/OUT không phù hợp.

## 6. SqlQuery<T>: SELECT và cách đọc kết quả

`SqlQuery<T>` là lớp abstract cung cấp các thao tác SELECT reusable. Có nhiều overload:

- `execute(...)` trả **`List<T>`**, từ không có hàng (list rỗng) đến nhiều hàng.
- `findObject(...)` đại diện cho kết quả **không quá một hàng**. Mặc định trả `null` khi không tìm thấy, và coi nhiều hàng là lỗi; không giống hệt `JdbcTemplate.queryForObject` trên trường hợp không có hàng.
- `executeByNamedParam(Map)` hoặc `findObjectByNamedParam(Map)` khi dùng contract named parameters.
- Một số phiên bản mới (Spring Framework 7) có `stream(...)`, cần đóng stream đúng cách vì liên quan JDBC resources; không tự dùng API này trên nhánh Spring cũ.

Vì vậy cần xem caller dùng `query.execute(id)` hay `query.findObject(id)`, chứ không chỉ xem query định nghĩa SELECT gì.

### MappingSqlQuery<T>: subclass tự viết mapRow

```java
public class FindBookById extends MappingSqlQuery<Book> {

    public FindBookById(DataSource ds) {
        super(ds, "SELECT id, title FROM books WHERE id = ?");
        declareParameter(new SqlParameter("id", Types.BIGINT));
        compile();
    }

    @Override
    protected Book mapRow(ResultSet rs, int rowNum)
            throws SQLException {
        return new Book(rs.getLong("id"),
                        rs.getString("title"));
    }
}
```

Đoạn này cần class `Book`, import JDBC/Spring và package tương ứng, nên chỉ là snippet; project đầy đủ ở mục 10. Trong cách viết này, `MappingSqlQuery` đã cung cấp machinery mapping; subclass chỉ cần chuyển **một hàng** `ResultSet` thành `Book`. `rowNum` bắt đầu từ 0, **không phải database id**.

Khi thấy `MappingSqlQueryWithParameters<T>`, callback ở subclass nhận thêm `parameters` và `context`; dùng khi mapping cần dữ liệu bên ngoài hàng SQL. Đừng tìm signature hai tham số của `MappingSqlQuery` trong lớp này.

### GenericSqlQuery<T>: RowMapper được inject

```java
// Snippet yêu cầu DataSource ds, record Book, imports.
GenericSqlQuery<Book> query = new GenericSqlQuery<>();
query.setDataSource(ds);
query.setSql("SELECT id, title FROM books WHERE id = ?");
query.declareParameter(new SqlParameter("id", Types.BIGINT));
query.setRowMapper((rs, rowNum) ->
        new Book(rs.getLong("id"), rs.getString("title")));
query.compile();

List<Book> found = query.execute(1L);
```

Ở đây có `RowMapper` cấu hình qua setter, **không có lớp FindBookQuery riêng**. Nếu code dùng `setRowMapperClass`, lần theo class mapper. Điều quan trọng khi refactor là giữ nguyên xử lý SQL NULL, column aliases, thứ tự cột và mapping kiểu dữ liệu.

## 7. SqlUpdate: số hàng ảnh hưởng, generated keys và guardrails

`SqlUpdate` là lớp **concrete** biểu diễn một DML operation. Nó có các overload `update(...)`/`updateByNamedParam(...)`, có thể nhận `KeyHolder` để lưu generated keys khi đã cấu hình đúng và driver hỗ trợ.

```java
// Snippet minh họa, DataSource ds và imports.
SqlUpdate deleteInactive = new SqlUpdate(ds,
        "DELETE FROM sessions WHERE active = ?");
deleteInactive.declareParameter(
        new SqlParameter("active", Types.BOOLEAN));
deleteInactive.setMaxRowsAffected(100);
deleteInactive.compile();

int rows = deleteInactive.update(false);
```

**Đọc đúng count:** `rows` là số hàng ảnh hưởng từ SQL execution, không phải tổng số đối tượng Java đang có. `setMaxRowsAffected` là ràng buộc kiểm tra kết quả, không phải cách tự động thêm `LIMIT 100` vào SQL. `setRequiredRowsAffected(1)` yêu cầu chính xác một hàng; useful cho UPDATE theo khóa định danh.

Khi có generated keys, đọc cả `setReturnGeneratedKeys`/`setGeneratedKeysColumnNames` và overload `update(params, keyHolder)`. Không suy diễn `update(...)` mặc định trả khóa mới; kiểu cơ bản là `int`.

**Lưu ý transaction:** Nếu một command thực thi SQL trước khi phát hiện count không khớp, dữ liệu phải được rollback trong transaction phù hợp khi nghiệp vụ yêu cầu. Đừng nghĩ chỉ cần set guard là mọi DB change đã tự hoàn tác nếu caller đã commit hoặc không có transaction.

## 8. BatchSqlUpdate: cùng họ nhưng KHÔNG thread-safe

`BatchSqlUpdate extends SqlUpdate`, tuy nhiên cách thực thi khác rõ rệt: `update(...)` **đưa bộ tham số vào hàng đợi**; batch được thực thi khi đạt size hoặc gọi `flush()`. Các API thường gặp: `setBatchSize`, `getQueueCount`, `getExecutionCount`, `getRowsAffected`, `flush`, `reset`.

```java
// Snippet cần DataSource ds và bảng books có cột status.
BatchSqlUpdate batch = new BatchSqlUpdate(
        ds,
        "UPDATE books SET status = ? WHERE id = ?",
        new int[] { Types.VARCHAR, Types.BIGINT },
        100
);
batch.update("READY", 1L);
batch.update("READY", 2L);
int[] counts = batch.flush();
```

**Đọc code kiểu này khác với `SqlUpdate`:** hai lần `batch.update` có thể **chưa** gửi hai lệnh DB ngay; phải tìm `flush` và xử lý exception/partial counts. `BatchSqlUpdate` có queue mutable và **được Spring Javadoc ghi rõ không thread-safe**. Không giữ một instance cho nhiều request song song rồi giả định an toàn như `SqlQuery` đã compile. Cần scope mỗi batch thích hợp hoặc cách đồng bộ khác; cũng không giả định batch tự bảo đảm atomicity nếu không có transaction.

## 9. SqlCall, StoredProcedure và output parameters

Nhánh procedure là:

```text
RdbmsOperation
  -> SqlCall
      -> StoredProcedure
          -> GenericStoredProcedure
```

`SqlCall` cấu hình `CallableStatement` thay vì SQL SELECT thông thường. `StoredProcedure` là abstract: thường có subclass theo nghiệp vụ, hoặc `GenericStoredProcedure` là implementation để cấu hình bean. Tên SQL ở `StoredProcedure` thường là **tên procedure/function trong DB**. Có thể thấy `setFunction(true)`, `setSqlReadyForUse(true)`, hoặc danh sách `SqlParameter`, `SqlOutParameter`, `SqlInOutParameter`.

| Khai báo | Vai trò |
| --- | --- |
| `new SqlParameter("p_id", Types.BIGINT)` | IN parameter |
| `new SqlOutParameter("p_status", Types.VARCHAR)` | OUT parameter |
| `new SqlInOutParameter("p_value", Types.NUMERIC)` | INOUT parameter |

Ví dụ **minh họa**, không chạy được nếu chưa có stored procedure `read_status` với signature tương ứng:

```java
final class ReadStatus extends StoredProcedure {
    ReadStatus(DataSource ds) {
        super(ds, "read_status");
        declareParameter(new SqlParameter("p_id", Types.BIGINT));
        declareParameter(
                new SqlOutParameter("p_status", Types.VARCHAR));
        compile();
    }

    String read(long id) {
        Map<String, Object> out =
                execute(Map.of("p_id", id));
        return (String) out.get("p_status");
    }
}
```

Để dùng đoạn này phải import `javax.sql.DataSource`, `java.sql.Types`, `java.util.Map`, `org.springframework.jdbc.object.StoredProcedure`, `org.springframework.jdbc.core.SqlParameter` và `SqlOutParameter`. Lúc đọc code thật, kiểm tra routine name, thứ tự parameter, vendor DB, OUT types và transaction. `execute(Map)` trả `Map<String,Object>`, khác `SqlQuery.execute(...)` trả `List<T>`.

**Đừng nhầm `SqlFunction<T>` với stored function:** `SqlFunction<T>` là wrapper cho câu query dưới nhánh `SqlQuery`, trong khi procedure/function call theo `SqlCall` có semantics riêng. API tiện hơn `SimpleJdbcCall` cũng gọi routine nhưng **không phải subclass của `RdbmsOperation`**.

## 10. Ví dụ hoàn chỉnh chạy được với Java 17+, Spring Boot và H2

Ví dụ này minh họa đúng mô hình **khai báo operation một lần, compile rồi thực thi nhiều lần**. Dùng **Java 17+, Maven, Spring Boot 3.5.16, Spring JDBC và H2**. Không sử dụng Spring Data hay Hibernate. Đây là project nhiều file, nên không chạy một đoạn Java riêng bằng `javac` khi chưa có dependency.

**Cấu trúc:**

```text
jdbc-object-demo/
├── pom.xml
└── src/main/
    ├── java/com/example/jdbcobjects/JdbcObjectApplication.java
    └── resources/
        ├── application.properties
        ├── schema.sql
        └── data.sql
```

**pom.xml**

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
    <artifactId>jdbc-object-demo</artifactId>
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

**src/main/resources/schema.sql**

```sql
CREATE TABLE books (
    id BIGINT PRIMARY KEY,
    title VARCHAR(120) NOT NULL
);
```

**src/main/resources/data.sql**

```sql
INSERT INTO books (id, title) VALUES (1, 'Initial');
```

**src/main/resources/application.properties**

```properties
spring.main.web-application-type=none
spring.main.banner-mode=off
logging.level.root=ERROR
spring.datasource.url=jdbc:h2:mem:jdbcobjects;DB_CLOSE_DELAY=-1
spring.sql.init.mode=always
```

**src/main/java/com/example/jdbcobjects/JdbcObjectApplication.java**

```java
package com.example.jdbcobjects;

import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Types;
import javax.sql.DataSource;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.SqlParameter;
import org.springframework.jdbc.object.MappingSqlQuery;
import org.springframework.jdbc.object.SqlUpdate;

@SpringBootApplication
public class JdbcObjectApplication {

    public static void main(String[] args) {
        SpringApplication.run(JdbcObjectApplication.class, args);
    }

    public record Book(long id, String title) {}

    // SELECT reusable.
    public static class FindBookById extends MappingSqlQuery<Book> {

        public FindBookById(DataSource ds) {
            super(ds, "SELECT id, title FROM books WHERE id = ?");
            declareParameter(new SqlParameter("id", Types.BIGINT));
            compile();
        }

        @Override
        protected Book mapRow(ResultSet rs, int rowNum)
                throws SQLException {
            return new Book(rs.getLong("id"),
                            rs.getString("title"));
        }
    }

    @Bean
    FindBookById findBook(DataSource ds) {
        return new FindBookById(ds);
    }

    // UPDATE reusable.
    @Bean
    SqlUpdate renameBook(DataSource ds) {
        SqlUpdate op = new SqlUpdate(
                ds, "UPDATE books SET title = ? WHERE id = ?");
        op.declareParameter(new SqlParameter("title", Types.VARCHAR));
        op.declareParameter(new SqlParameter("id", Types.BIGINT));
        op.setRequiredRowsAffected(1);
        op.compile();
        return op;
    }

    @Bean
    CommandLineRunner demo(FindBookById findBook, SqlUpdate renameBook) {
        return args -> {
            System.out.println("before=" + findBook.findObject(1L));
            System.out.println("updated=" +
                    renameBook.update("Revised", 1L));
            System.out.println("after=" + findBook.findObject(1L));
            System.out.println("missing=" + findBook.findObject(999L));
        };
    }
}
```

**Chạy** từ thư mục chứa `pom.xml` với JDK 17+ và Maven:

```bash
mvn spring-boot:run
```

**Các dòng do ứng dụng chủ động in** (ngoài log Maven/Spring):

```text
before=Book[id=1, title=Initial]
updated=1
after=Book[id=1, title=Revised]
missing=null
```

**Giải thích:**

1. Spring Boot cấu hình `DataSource` và khởi tạo bảng cùng hàng dữ liệu của H2.
2. Bean `FindBookById` mô tả SELECT, bind BIGINT và map mỗi dòng thành record `Book`. `compile()` chỉ chuẩn bị operation.
3. Bean `SqlUpdate` mô tả UPDATE với hai `SqlParameter` và ràng buộc cập nhật đúng một hàng.
4. `findObject(1L)` query DB, trả record; `update("Revised",1L)` mới gửi DML và trả số hàng ảnh hưởng; query sau xác nhận title mới.
5. `findObject(999L)` trả `null` vì không có hàng. Nếu query trả nhiều hàng, API finder coi đó là lỗi.
6. Các lời gọi riêng trong runner không chứng minh có một transaction bao toàn bộ. Để gom nhiều thay đổi phải atomic, đặt `@Transactional` trên service nghiệp vụ thích hợp.

Đây là ví dụ sử dụng API có trong Spring Framework được Spring Boot 3.5 quản lý. **Không dùng những API chỉ có trên Spring Framework 7** khi chạy với stack này.

## 11. Nhận diện cấu hình kiểu XML trong ứng dụng cũ

Nhiều codebase Spring XML không tạo `SqlUpdate` trực tiếp trong Java mà khai báo bean:

```xml
<bean id="deactivateUser"
      class="org.springframework.jdbc.object.SqlUpdate">
    <property name="dataSource" ref="dataSource"/>
    <property name="sql"
              value="UPDATE users SET active = ? WHERE id = ?"/>
    <property name="types">
        <list>
            <value>16</value>
            <value>-5</value>
        </list>
    </property>
</bean>
```

Đây là minh họa cấu hình Spring XML: mã `16` và `-5` tương ứng `Types.BOOLEAN` và `Types.BIGINT`. Trong dự án thực, hãy tra thêm bean parent, aliases, property placeholders và bean factories. `RdbmsOperation` triển khai `InitializingBean` nên container có thể gọi `afterPropertiesSet` để hoàn tất compilation. **Không sửa code Java rồi nghĩ SQL đã thay đổi** nếu câu SQL thật nằm trong cấu hình ngoài class.

Ví dụ Java tương ứng về ý nghĩa:

```java
SqlUpdate deactivateUser = new SqlUpdate(ds,
        "UPDATE users SET active = ? WHERE id = ?");
deactivateUser.declareParameter(
        new SqlParameter("active", Types.BOOLEAN));
deactivateUser.declareParameter(
        new SqlParameter("id", Types.BIGINT));
deactivateUser.compile();
```

Khi migration từ XML sang `@Configuration`, cần giữ đúng datasource, SQL, các JDBC types và thời điểm khởi tạo.

## 12. Phân biệt với các API đang dùng phổ biến

| API nhìn thấy | Đọc như thế nào? | Quan hệ với RdbmsOperation |
| --- | --- | --- |
| `JdbcTemplate.query(sql, mapper, params)` | SQL và mapper tại call site | Cùng hạ tầng Spring JDBC; không cần object query riêng |
| `NamedParameterJdbcTemplate` | SQL/params thường dùng `:name` | Wrapper của JdbcTemplate, không thuộc cây RdbmsOperation |
| `JdbcClient` | Fluent facade query/update (Spring Framework 6.1+) | API hiện đại hơn; không phải subclass RdbmsOperation |
| `SimpleJdbcCall` | Stored procedure/function với cấu hình thường tận dụng DB metadata | Không thuộc nhánh `StoredProcedure`/`RdbmsOperation` |
| `SimpleJdbcInsert` | INSERT dựa metadata/cấu hình bảng | Không phải `SqlUpdate` |
| `JpaRepository` | Repository của Spring Data JPA | Khác tầng, thường dùng JPA provider/ORM |
| `EntityManager` / Hibernate | Persistence context và ORM mapping | Không phải JdbcTemplate/RDBMS object |

Trong phần tài liệu chính thức về **object-oriented JDBC operations**, Spring ghi nhận nhiều use case của `MappingSqlQuery`/`SqlUpdate` có thể dùng `JdbcTemplate` trực tiếp đơn giản hơn. Vì vậy nhiệm vụ bảo trì thường là **đọc đúng hành vi hiện tại trước**, sau đó mới quyết định có đáng refactor.

Ví dụ hai kiểu tương đương khi SQL/mapping/parameter hoàn toàn trùng:

```java
// Object style, giả định query đã compile.
List<Book> a = findBooks.execute(10L);

// JdbcTemplate style, giả định jdbcTemplate và Book tồn tại.
List<Book> b = jdbcTemplate.query(
        "SELECT id, title FROM books WHERE id >= ?",
        (rs, rowNum) ->
                new Book(rs.getLong("id"), rs.getString("title")),
        10L);
```

Đoạn minh họa không khẳng định `findBooks` thực tế có SQL trên; phải mở class của nó để đối chiếu. Khi đổi API, giữ nguyên sự khác biệt `execute` (0-n hàng), `findObject` (0-1 hàng), mapping null, generated keys, query timeout, required rows và transaction.

## 13. Ranh giới transaction và thread safety

Một operation đã cấu hình thường dùng chung an toàn sau khi init, nhưng **không tự mở một business transaction bao nhiều lời gọi**. Nếu service chuyển trạng thái user, ghi audit và cập nhật quota phải cùng commit/rollback, hãy đặt `@Transactional` trên entry point nghiệp vụ:

```java
// Đoạn minh họa service: các SqlUpdate bean riêng phải tồn tại.
@Service
public class ActivateAccountService {
    private final SqlUpdate activate;
    private final SqlUpdate logChange;

    public ActivateAccountService(
            SqlUpdate activate, SqlUpdate logChange) {
        this.activate = activate;
        this.logChange = logChange;
    }

    @Transactional
    public void activate(long id) {
        activate.update(true, id);
        logChange.update(id);
    }
}
```

Đoạn này cần imports `org.springframework.stereotype.Service`, `org.springframework.transaction.annotation.Transactional`, `SqlUpdate`, hai bean cấu hình riêng và `@Qualifier` nếu nhiều bean cùng type. Chỉ minh họa cách *service* điều phối transaction, không phải chương trình độc lập. Cùng datasource và transaction manager phải được cấu hình chính xác.

**Không lẫn hai khái niệm:**

- **Thread-safety của operation:** cấu hình immutable sau initialization, mỗi lần execute dùng state invocation riêng; riêng `BatchSqlUpdate` có queue không thread-safe.
- **Tính nhất quán nghiệp vụ:** transaction, isolation, locking, SQL constraints và exception/rollback. Một operation thread-safe không thay thế transaction.

Tránh cache JDBC `Connection` hoặc `ResultSet` trong field của singleton operation. Hạ tầng `JdbcTemplate` quản lý connection/statement/result set cho từng invocation, tham gia Spring transaction khi datasource/manager phù hợp. Không tự `commit()` hoặc `close()` connection do transaction manager kiểm soát.

## 14. Lỗi thường gặp khi đọc và sửa mã

1. **Hiểu `RdbmsOperation` là đối tượng JDBC `Statement`.** Nó chỉ là wrapper mô tả thao tác, không giữ một prepared statement có thể dùng chung giữa mọi request.
2. **Cho rằng `compile()` thực thi query.** Đây là bước cấu hình/factory; SQL chạy ở `execute/findObject/update`.
3. **Nhầm return của `SqlQuery.execute` với `StoredProcedure.execute`.** Cái đầu là `List<T>`; procedure trả map output.
4. **Áp logic của `JdbcTemplate.queryForObject` cho `SqlQuery.findObject`.** Với finder, trường hợp không có hàng có thể trả `null`, không phải luôn exception.
5. **Bỏ qua constructor của subclass.** SQL và parameter có thể khai báo trong `super(ds, sql)` của class khác.
6. **Chỉ tìm SQL trong Java, bỏ qua XML bean/`@Bean` config.** SQL có thể được inject từ configuration.
7. **Thay thứ tự params khi refactor.** Tên `SqlParameter` không thay thế vị trí `?` trong positional calls.
8. **Tưởng `setMaxRowsAffected` biến thành SQL LIMIT.** Nó kiểm tra count hậu thực thi; rollback phụ thuộc transaction.
9. **Chia sẻ `BatchSqlUpdate` như singleton giữa threads.** Queue mutable và không thread-safe.
10. **Quên gọi `flush()` cho batch chưa đầy.** Những bản ghi đã enqueue có thể chưa được gửi đi.
11. **Nhầm `SqlFunction` là `StoredProcedure`.** Hai nhánh API khác nhau.
12. **Sửa SQL mà không cập nhật mapper/alias/JDBC types.** Có thể lỗi runtime hoặc mapping sai dữ liệu.
13. **Cho rằng object operation là Spring Data Repository hoặc Hibernate.** Thuộc `org.springframework.jdbc.object` của Spring Framework JDBC.
14. **Giả định mọi method gọi chung transaction.** Phải tìm `@Transactional`, manager, datasource và thread boundary.
15. **Đổi toàn bộ sang API mới mà thiếu regression test.** Cần so sánh query result, row count, lỗi và transaction.

## 15. Câu hỏi tự kiểm tra khi xem pull request

**Tình huống A:** `class FindAccount extends MappingSqlQuery<Account>`, code gọi `findObject(id)`. Hỏi class nào cần mở và trả gì nếu không có hàng?  
**Đáp:** mở constructor/mapping của `FindAccount` để lấy SQL, parameter, mapper; finder mặc định có thể trả `null`, caller phải xử lý.

**Tình huống B:** `SqlUpdate.setRequiredRowsAffected(1)` đặt trên UPDATE theo id. Hỏi tại sao code còn kiểm tra count?  
**Đáp:** operation đã có quy tắc kiểm tra expected count; xem exception contract và transaction. Count không phải primary key hay generated key.

**Tình huống C:** `BatchSqlUpdate.update(...)` gọi hai lần, batch size 500 và không thấy `flush()`. Hỏi đã chắc DB nhận hai lệnh chưa?  
**Đáp:** chưa; có thể chỉ ở queue. Cần tìm nơi flush hoặc lifecycle của batch và kiểm tra concurrency/transaction.

**Tình huống D:** `StoredProcedure.execute(Map.of("id", 1L))`. Hỏi có chắc trả `List<User>` không?  
**Đáp:** không; API procedure trả `Map` output, muốn biết chính xác phải xem OUT declarations và routine contract.

**Tình huống E:** Bean `SqlUpdate` không gọi `compile` nhưng XML đặt datasource, SQL và types. Hỏi có chắc sai không?  
**Đáp:** không; bean lifecycle qua `InitializingBean.afterPropertiesSet` có thể compile. Kiểm tra cấu hình và integration test.

**Tình huống F:** Code chỉ import `org.springframework.jdbc.object.MappingSqlQuery` và không có JPA. Có cần Hibernate không?  
**Đáp:** không. Đây là Spring JDBC, không tự yêu cầu ORM provider.

## 16. Checklist thực hành khi đọc mã hiện có

- [ ] Xác định class thật thuộc `SqlQuery`, `SqlUpdate` hay `SqlCall`.
- [ ] Tìm đủ constructor, `@Bean`/XML, datasource và transaction manager.
- [ ] Lấy đúng SQL/procedure name và dấu `?`/parameter names.
- [ ] So thứ tự `declareParameter` và giá trị ở call site, JDBC `Types`/null.
- [ ] Phân biệt cấu hình/`compile` với lời gọi thực thi.
- [ ] Biết `execute` trả List, `findObject` một object/null, `update` row count, procedure output Map.
- [ ] Đọc callback `mapRow`/`RowMapper` và xử lý zero/multiple rows.
- [ ] Nếu batch, tìm queue/`flush`, thread-safety và ranh giới transaction.
- [ ] Kiểm tra `setRequiredRowsAffected`, `setMaxRowsAffected`, generated keys và SQL WHERE.
- [ ] Xác định đúng transaction, checked/unchecked exceptions, isolation và connection ownership.
- [ ] Đọc cả XML/config và regression test trước khi đề xuất đổi sang `JdbcTemplate`/`JdbcClient`.

## Tài liệu tham khảo chính thức

- Spring Framework — Modeling JDBC Operations as Java Objects: https://docs.spring.io/spring-framework/reference/data-access/jdbc/object.html
- Spring Framework — Choosing an Approach for JDBC Database Access: https://docs.spring.io/spring-framework/reference/data-access/jdbc/choose-style.html
- Spring Framework — JdbcTemplate: https://docs.spring.io/spring-framework/reference/data-access/jdbc/core.html
- Spring API — RdbmsOperation: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jdbc/object/RdbmsOperation.html
- Spring API — SqlQuery: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jdbc/object/SqlQuery.html
- Spring API — MappingSqlQuery: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jdbc/object/MappingSqlQuery.html
- Spring API — SqlUpdate: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jdbc/object/SqlUpdate.html
- Spring API — StoredProcedure: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jdbc/object/StoredProcedure.html
- Spring API — BatchSqlUpdate: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jdbc/object/BatchSqlUpdate.html

**Ghi nhớ cuối bài:** `RdbmsOperation` là **đối tượng mô tả thao tác SQL tái sử dụng**. Khi thấy nó trong code, lần theo **cây class → nơi cấu hình datasource/SQL/params → compile/lifecycle → execute/update/findObject → mapping/output → transaction**. Đặc biệt, **`BatchSqlUpdate` có queue và không thread-safe**, còn các operation thông thường được thiết kế để tái sử dụng sau initialization.