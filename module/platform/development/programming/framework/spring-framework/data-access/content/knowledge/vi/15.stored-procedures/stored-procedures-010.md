# Giao dịch, quyền truy cập và tính phụ thuộc nhà cung cấp của thủ tục trong Spring JDBC

## 1. Mục tiêu và bối cảnh

Một ứng dụng Spring có thể gọi stored procedure bằng `SimpleJdbcCall`, `JdbcTemplate` hoặc `CallableStatement`. Nhưng gọi đúng cú pháp chưa chứng minh dữ liệu được ghi an toàn: thủ tục chạy bên trong **database**, có thể thay đổi nhiều bảng, ném hoặc bắt lỗi, thực thi với quyền riêng và chịu ngữ nghĩa của từng hệ quản trị.

Xét nghiệp vụ chuyển 25 đơn vị từ tài khoản A sang B. Service gọi thủ tục trừ A, cộng B, sau đó Java ghi thêm nhật ký. Nếu bước ghi nhật ký thất bại, phần chuyển số dư có rollback không? Câu trả lời phụ thuộc **transaction manager của Spring, connection JDBC, thân thủ tục và luật của DBMS**. Annotation `@Transactional` một mình không đủ để kết luận.

Bài học này làm rõ ba nhóm quyết định:

- **Giao dịch:** ai quyết định `COMMIT`/`ROLLBACK`, điều kiện để procedure và Java cùng tham gia một transaction, phản ứng khi lỗi phát sinh hoặc bị nuốt, trường hợp procedure tự kết thúc transaction.
- **Quyền truy cập:** quyền `EXECUTE`, quyền truy cập bảng bên trong, mô hình invoker/definer, sở hữu schema, hạn chế quyền truy cập và rủi ro leo thang đặc quyền.
- **Phụ thuộc nhà cung cấp:** PostgreSQL, MySQL, SQL Server và Oracle khác nhau về cú pháp, transaction control, metadata, hàm/thủ tục, security context, OUT parameters và cách driver dịch JDBC call.

Mục tiêu sau bài học: thiết kế được điểm gọi thủ tục phù hợp transaction của Spring, kiểm thử rollback/privileges, phân biệt rõ phần Spring trừu tượng hóa với phần vẫn gắn chặt DBMS, và biết cách chẩn đoán lỗi production.

## 2. Spring quản lý transaction bên ngoài, DBMS thực thi bên trong

```text
Service method / TransactionTemplate
                |
                v
Spring PlatformTransactionManager
                |
                v
DataSource -> connection của transaction đang hoạt động
                |
                v
SimpleJdbcCall / JdbcTemplate / CallableStatement
                |
                v
Database CALL -> SQL nội bộ -> trigger/lock/exception/security
                |
                v
Connection commit/rollback theo ranh giới thực tế
```

Khi dùng `DataSourceTransactionManager` với một `DataSource` JDBC, Spring bind connection của transaction vào luồng thực thi. `JdbcTemplate` và `SimpleJdbcCall` sử dụng connection phù hợp qua hạ tầng Spring JDBC, nên có thể thực hiện nhiều lệnh SQL trong **cùng một transaction vật lý**.

Để việc này đúng:

1. Transaction manager phải quản lý chính `DataSource` dùng để gọi thủ tục; connection mở từ nguồn khác không tự động tham gia.
2. `@Transactional` phải được kích hoạt (ví dụ thông qua proxy Spring). Tự gọi `this.someTransactionalMethod()` trong cùng bean ở proxy mode thường bỏ qua advice của phương thức được gọi.
3. Các thao tác phải ở cùng ngữ cảnh transaction; một thread mới, kết nối được cấp thủ công hoặc dịch vụ bên ngoài không tự chia sẻ transaction JDBC đang mở.
4. Thân thủ tục phải tuân theo hợp đồng transaction mong muốn. Nếu procedure tự commit, dùng autonomous transaction hoặc DDL implicit commit, rollback từ Spring có thể không hoàn tác được tất cả.
5. Spring và database cần thống nhất isolation, timeout, lock, trạng thái lỗi và cơ chế retry.

**Phân biệt hai khái niệm:** Spring quyết định khi nào yêu cầu commit/rollback đối với connection nó quản lý; DBMS quyết định `CALL` có được phép tự điều khiển transaction, rollback những lệnh nào, và câu lệnh nào có tác động ngoài transaction.

## 3. Cách gọi procedure trong Spring không tự thiết lập transaction

### 3.1. SimpleJdbcCall và hợp đồng tham số

```java
SimpleJdbcCall transfer = new SimpleJdbcCall(jdbcTemplate)
        .withSchemaName("finance")
        .withProcedureName("transfer")
        .withoutProcedureColumnMetaDataAccess()
        .declareParameters(
            new SqlParameter("p_from", Types.INTEGER),
            new SqlParameter("p_to", Types.INTEGER),
            new SqlParameter("p_amount", Types.INTEGER)
        );

Map<String, Object> output = transfer.execute(Map.of(
    "p_from", 1,
    "p_to", 2,
    "p_amount", 25
));
```

Đoạn này minh họa **trong lớp đã có `jdbcTemplate` và import tương ứng**; chưa phải chương trình độc lập. `SimpleJdbcCall` cấu hình tên routine, schema, tham số IN/OUT và trả một Map chứa giá trị OUT (nếu có). `withoutProcedureColumnMetaDataAccess()` giúp tránh phụ thuộc metadata tham số từ driver; phải khai báo đúng đầy đủ tham số bằng `declareParameters(...)`. Khởi tạo/compile cấu hình một lần và dùng lại được sau đó.

Đối tượng `SimpleJdbcCall` không mở transaction thay cho service. Nó sẽ tham gia một transaction đang hoạt động nếu đúng cách lấy connection.

### 3.2. JdbcTemplate với CallableStatement

```java
jdbcTemplate.execute((Connection con) -> {
    try (CallableStatement cs =
                 con.prepareCall("{call finance.transfer(?, ?, ?)}")) {
        cs.setInt(1, 1);
        cs.setInt(2, 2);
        cs.setInt(3, 25);
        cs.execute();
    }
    return null;
});
```

Đây là đoạn mã trong phương thức đã có `jdbcTemplate`; import `java.sql.Connection` và `java.sql.CallableStatement`. Connection do `JdbcTemplate` cung cấp có thể thuộc transaction của Spring. Chỉ đóng `CallableStatement` của mình; **không gọi `con.commit()`, `con.rollback()` hoặc `con.close()`** trên connection được Spring quản lý.

JDBC escape syntax `{call ...}` cần được driver dịch sang SQL của database. Ví dụ **pgJDBC mặc định `escapeSyntaxCallMode=select`** để tương thích lời gọi function; khi gọi PostgreSQL procedure có thể cần cấu hình `escapeSyntaxCallMode=callIfNoReturn` hoặc `call`. Lệnh SQL `CALL ...` của PostgreSQL khác lời gọi function dạng `SELECT ...`. Không cho rằng mọi DBMS đều hiểu cùng một cú pháp native.

## 4. Khi nào thay đổi trong thủ tục rollback cùng service?

Nếu procedure chỉ thực hiện các lệnh DML và **không tự commit/rollback**, logic thường như sau:

| Tình huống | Kết quả cần hiểu |
|---|---|
| Service đang có `@Transactional` hoạt động; procedure dùng cùng connection | Các thay đổi thường tham gia cùng transaction của service. |
| Service gọi procedure rồi ném unchecked `RuntimeException` ra ngoài ranh giới transaction | Spring mặc định rollback; DBMS hoàn tác DML chưa commit trong cùng transaction. |
| Procedure gây `SQLException`; `JdbcTemplate` ném `DataAccessException` | Đây là ngoại lệ unchecked; Spring mặc định rollback nếu lỗi đi qua transaction interceptor. |
| Procedure tự bắt lỗi và trả mã trạng thái bình thường | Spring không biết đó là thất bại nghiệp vụ; transaction có thể commit nếu service không xử lý. |
| Java catch `DataAccessException` rồi trả bình thường | Spring có thể commit nếu transaction còn hợp lệ và chưa bị đánh dấu rollback-only. Một số DBMS như PostgreSQL có thể đưa transaction vào trạng thái lỗi cần rollback. |
| Procedure `COMMIT`, sử dụng autonomous transaction hoặc DDL implicit commit | Không thể khẳng định rollback ngoài sẽ hoàn tác tác động đó. |
| Gọi procedure ngoài transaction Spring và connection auto-commit | Thành công thường được commit theo quy tắc auto-commit/driver; không mặc định có transaction bao trùm nhiều lần gọi. |

### 4.1. Mặc định của @Transactional và ngoại lệ checked

Spring declarative transaction mặc định rollback với `RuntimeException`/`Error`; ngoại lệ checked thông thường không tự kích hoạt rollback. Nếu nghiệp vụ dùng checked exception, khai báo quy tắc rõ:

```java
@Transactional(rollbackFor = BusinessRuleException.class)
public void performBusinessOperation() throws BusinessRuleException {
    // Gọi thủ tục và cập nhật các bảng khác trong cùng transaction.
}
```

Đây là mã minh họa, không biên dịch độc lập: `BusinessRuleException` và thân method cần triển khai trong dự án. Cần phân biệt lỗi có **ngoại lệ** với lỗi được trả về như OUT status code. Nếu procedure trả `status = FAILED` mà service vẫn kết thúc bình thường, Spring không tự rollback.

Trong proxy-based Spring, `@Transactional` gắn lên phương thức public được gọi từ bên ngoài bean thường là cách dùng phổ biến; tự gọi nội bộ không tạo transaction advice mới. Nếu dùng nhiều transaction manager, phải chọn đúng manager cho JDBC đó.

### 4.2. Propagation và savepoint

- `REQUIRED` tham gia transaction hiện có hoặc mở mới nếu chưa có.
- `REQUIRES_NEW` tạo một transaction vật lý độc lập; phần được commit ở transaction này có thể tồn tại dù transaction ngoài rollback. Cần tính đến số lượng connection trong pool.
- `NESTED` có thể dùng JDBC savepoint với `DataSourceTransactionManager` và driver hỗ trợ, để rollback một phần trong cùng physical transaction.

Cả ba là chính sách **Spring**, không buộc procedure phải tuân theo nếu engine cho phép nó điều khiển transaction riêng. Không lạm dụng `REQUIRES_NEW` để “sửa lỗi rollback” khi chưa nắm rõ tác động đến tính nguyên tử.

## 5. Ví dụ Java 17+ với PostgreSQL: commit và rollback có thể đối chiếu

Ví dụ độc lập dùng PostgreSQL 16, Spring JDBC 6.2.12 và pgJDBC 42.7.7. Nó tạo schema thử nghiệm ngẫu nhiên, bảng tài khoản, bảng audit và procedure `transfer`; hai lần gọi chứng minh rollback khi Java ném lỗi và commit khi kết thúc bình thường. Procedure không gọi `COMMIT`/`ROLLBACK` để transaction do Spring quyết định.

### 5.1. Cấu trúc và pom.xml

```text
procedure-tx-demo/
├── pom.xml
└── src/main/java/demo/ProcedureTransactionDemo.java
```

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>procedure-tx-demo</artifactId>
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
            <groupId>org.postgresql</groupId>
            <artifactId>postgresql</artifactId>
            <version>42.7.7</version>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
                <configuration><release>17</release></configuration>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
                <configuration>
                    <mainClass>demo.ProcedureTransactionDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

### 5.2. Source code

```java
package demo;

import java.sql.Types;
import java.util.Map;
import java.util.UUID;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.SqlParameter;
import org.springframework.jdbc.core.simple.SimpleJdbcCall;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.transaction.support.TransactionTemplate;

public final class ProcedureTransactionDemo {

    public static void main(String[] args) {
        String url = System.getenv().getOrDefault(
            "DB_URL",
            "jdbc:postgresql://localhost:54329/lesson"
                + "?escapeSyntaxCallMode=callIfNoReturn"
        );
        String username = System.getenv().getOrDefault("DB_USER", "postgres");
        String password = System.getenv().getOrDefault(
            "DB_PASSWORD", "postgres"
        );

        DriverManagerDataSource dataSource = new DriverManagerDataSource();
        dataSource.setDriverClassName("org.postgresql.Driver");
        dataSource.setUrl(url);
        dataSource.setUsername(username);
        dataSource.setPassword(password);

        JdbcTemplate jdbc = new JdbcTemplate(dataSource);
        TransactionTemplate transaction = new TransactionTemplate(
            new DataSourceTransactionManager(dataSource)
        );

        // Chỉ làm việc trong schema demo mới tạo.
        String schema = "learn_" + UUID.randomUUID().toString()
                .replace("-", "").substring(0, 12);

        jdbc.execute("CREATE SCHEMA " + schema);
        try {
            jdbc.execute("""
                CREATE TABLE %s.accounts (
                    id INTEGER PRIMARY KEY,
                    balance INTEGER NOT NULL CHECK (balance >= 0)
                )
                """.formatted(schema));

            jdbc.execute("""
                CREATE TABLE %s.audit_log (
                    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
                    note TEXT NOT NULL
                )
                """.formatted(schema));

            jdbc.execute("""
                CREATE PROCEDURE %s.transfer(
                    p_from INTEGER, p_to INTEGER, p_amount INTEGER
                )
                LANGUAGE plpgsql
                AS $proc$
                BEGIN
                    IF p_amount <= 0 OR p_from = p_to THEN
                        RAISE EXCEPTION 'Invalid transfer parameters';
                    END IF;

                    UPDATE %s.accounts
                       SET balance = balance - p_amount
                     WHERE id = p_from AND balance >= p_amount;
                    IF NOT FOUND THEN
                        RAISE EXCEPTION 'Sender missing or insufficient balance';
                    END IF;

                    UPDATE %s.accounts
                       SET balance = balance + p_amount
                     WHERE id = p_to;
                    IF NOT FOUND THEN
                        RAISE EXCEPTION 'Receiver missing';
                    END IF;
                END;
                $proc$
                """.formatted(schema, schema, schema));

            jdbc.update("INSERT INTO " + schema
                    + ".accounts (id, balance) VALUES (1, 100), (2, 100)");

            SimpleJdbcCall call = new SimpleJdbcCall(jdbc)
                .withSchemaName(schema)
                .withProcedureName("transfer")
                .withoutProcedureColumnMetaDataAccess()
                .declareParameters(
                    new SqlParameter("p_from", Types.INTEGER),
                    new SqlParameter("p_to", Types.INTEGER),
                    new SqlParameter("p_amount", Types.INTEGER)
                );
            call.compile();

            // Lần 1: procedure đã update, nhưng Java ném lỗi.
            try {
                transaction.execute(status -> {
                    call.execute(Map.of(
                        "p_from", 1, "p_to", 2, "p_amount", 30
                    ));
                    jdbc.update("INSERT INTO " + schema
                        + ".audit_log(note) VALUES (?)", "will rollback");
                    throw new IllegalStateException("simulate rollback");
                });
                throw new AssertionError("Expected demo exception");
            } catch (IllegalStateException ex) {
                if (!"simulate rollback".equals(ex.getMessage())) {
                    throw ex;
                }
            }
            printState(jdbc, schema, "After rollback");

            // Lần 2: hoàn tất bình thường => commit.
            transaction.execute(status -> {
                call.execute(Map.of(
                    "p_from", 1, "p_to", 2, "p_amount", 25
                ));
                jdbc.update("INSERT INTO " + schema
                    + ".audit_log(note) VALUES (?)", "committed");
                return null;
            });
            printState(jdbc, schema, "After commit");
        } finally {
            jdbc.execute("DROP SCHEMA " + schema + " CASCADE");
        }
    }

    private static void printState(
            JdbcTemplate jdbc, String schema, String label) {
        Integer from = jdbc.queryForObject(
            "SELECT balance FROM " + schema + ".accounts WHERE id = 1",
            Integer.class
        );
        Integer to = jdbc.queryForObject(
            "SELECT balance FROM " + schema + ".accounts WHERE id = 2",
            Integer.class
        );
        Integer audit = jdbc.queryForObject(
            "SELECT COUNT(*) FROM " + schema + ".audit_log",
            Integer.class
        );
        System.out.printf("%s: from=%d, to=%d, audit=%d%n",
                          label, from, to, audit);
    }
}
```

Chương trình này là ví dụ chạy độc lập với một **PostgreSQL test server có sẵn**. `DriverManagerDataSource` phù hợp demo nhỏ; dự án production nên dùng connection pool phù hợp.

### 5.3. Chạy và giải thích kết quả

Nếu có Docker, khởi động PostgreSQL thử nghiệm trên cổng riêng:

```bash
docker run --rm -d --name jdbc-proc-lab \
  -e POSTGRES_PASSWORD=postgres \
  -e POSTGRES_DB=lesson \
  -p 54329:5432 postgres:16

# Kiểm tra trạng thái; chạy lại sau khi database khởi động xong:
docker exec jdbc-proc-lab pg_isready -U postgres -d lesson

# Ở thư mục chứa pom.xml và src/:
mvn -q compile exec:java

# Khi đã xong bài lab:
docker stop jdbc-proc-lab
```

Đầu ra Java **dự kiến** với PostgreSQL mới khởi động:

```text
After rollback: from=100, to=100, audit=0
After commit: from=75, to=125, audit=1
```

Giải thích: lần đầu procedure chuyển 30 rồi ghi audit, nhưng callback ném unchecked exception; `TransactionTemplate` rollback cả DML của procedure lẫn audit. Lần hai chuyển 25 và ghi audit thành công; Spring commit cả hai. Đây là bằng chứng kiểm tra **trạng thái database**, không chỉ là quan sát return value của `SimpleJdbcCall`.

Mã tạo schema chỉ chứa ký tự sinh tự động `learn_[a-z0-9]`, rồi xóa schema demo đó khi kết thúc; không chọn database production. Nếu dùng DB test có sẵn, đặt `DB_URL`, `DB_USER`, `DB_PASSWORD` bằng biến môi trường tương ứng. Tên bảng/schema trong SQL là identifier cấu hình; giá trị nghiệp vụ dùng bind parameter. Không cho phép user nhập tùy ý schema name để ghép trực tiếp vào SQL.

**Lưu ý về tính chính xác:** kết quả trên được suy ra từ chương trình và trạng thái HỆ CSDL test được mô tả. Muốn xác nhận trên môi trường của bạn, chạy với PostgreSQL và pgJDBC đúng phiên bản; nếu DB không sẵn sàng, thiếu quyền tạo schema hoặc URL sai, chương trình không thể chạy thành công.

## 6. Thủ tục tự COMMIT/ROLLBACK: mỗi nhà cung cấp có luật khác

### 6.1. PostgreSQL

PostgreSQL có **procedure** gọi bằng `CALL`, còn function thông thường gọi qua `SELECT`. Procedure có khả năng điều khiển transaction **trong những tình huống top-level được phép**, nhưng nếu `CALL` chạy bên trong transaction block do Spring hoặc client mở, thủ tục **không được dùng `COMMIT`/`ROLLBACK` để kết thúc transaction đó**.

Ngoài ra, một PostgreSQL procedure khai báo `SECURITY DEFINER` hoặc gắn `SET ...` trong định nghĩa **không được thực hiện transaction control**. Các ràng buộc khác liên quan ngữ cảnh lồng `CALL`/`DO` và exception blocks cũng có thể giới hạn transaction control.

Với ứng dụng Spring dùng `@Transactional`, lựa chọn rõ ràng nhất thường là **không đặt `COMMIT`/`ROLLBACK` trong procedure**; để transaction do service quyết định. Nếu procedure thật sự cần commit ở bên trong, hãy thiết kế đường gọi top-level riêng, xác định auto-commit và kiểm thử recovery, không bọc nó tùy tiện trong transaction của Spring.

### 6.2. MySQL

MySQL cho phép stored **procedure** thực thi transaction statements như `COMMIT` ở các ngữ cảnh hợp lệ; stored **function** không được chứa statements gây commit/rollback trực tiếp hoặc ngầm. Vì thế, procedure có `COMMIT` bên trong có thể kết thúc transaction mà service Spring kỳ vọng kiểm soát. MySQL còn có các DDL dẫn đến implicit commit.

Không suy luận rằng “gọi bằng `SimpleJdbcCall` thì an toàn với mọi `@Transactional`”: cần đọc body procedure, kiểm tra engine và version, đo hiệu lực rollback trên database.

### 6.3. Microsoft SQL Server

Stored procedure T-SQL có thể sử dụng `BEGIN TRANSACTION`, `COMMIT TRANSACTION`, `ROLLBACK TRANSACTION`, `TRY...CATCH`, `THROW`. `@@TRANCOUNT` cho biết mức lồng, nhưng các transaction lồng theo kiểu thường **không độc lập như nhiều physical transactions**. `ROLLBACK` không chỉ định savepoint có thể đảo ngược toàn bộ transaction của session; điều này ảnh hưởng transaction bên ngoài do ứng dụng khởi tạo.

Xem thêm trạng thái `XACT_STATE()` và cấu hình `XACT_ABORT` khi quyết định có thể tiếp tục hay cần rollback. Không tự viết catch/rollback trong procedure mà không hiểu hợp đồng với caller.

### 6.4. Oracle

Trong PL/SQL bình thường, `COMMIT`/`ROLLBACK` của procedure có thể ảnh hưởng transaction của session đang gọi. Oracle còn có `PRAGMA AUTONOMOUS_TRANSACTION`: một phần code chạy trong transaction độc lập, có thể commit audit dù transaction bên ngoài rollback. Nếu nghiệp vụ đòi hỏi tất cả-or-nothing, phải đặc biệt kiểm tra các routine autonomous và side effect ngoài DB.

### 6.5. Bảng đối chiếu

| DBMS | Cách gọi procedure tiêu biểu | Lưu ý transaction |
|---|---|---|
| PostgreSQL | `CALL schema.proc(...)` | Transaction control trong procedure chỉ hợp lệ trong ngữ cảnh đặc biệt; không được từ `CALL` bên trong transaction block. |
| MySQL | `CALL schema.proc(...)` | Procedure có thể tự commit/rollback; function bị hạn chế; DDL có thể implicit commit. |
| SQL Server | `EXEC schema.proc ...` hoặc JDBC call | Procedure có thể ảnh hưởng transaction của caller; chú ý `@@TRANCOUNT`, `XACT_STATE()`. |
| Oracle | PL/SQL/JDBC call | Procedure có thể commit; autonomous transaction độc lập. |

Đây là tóm tắt có phạm vi; khi triển khai, kiểm tra tài liệu của **đúng phiên bản DBMS + JDBC driver**.

## 7. Quyền truy cập: ai được gọi và ai có quyền trên dữ liệu?

Thông thường có hai vai trò:

- **Invoker/caller:** tài khoản database mà ứng dụng Spring dùng để gọi thủ tục.
- **Definer/owner:** tài khoản/role sở hữu hoặc định nghĩa routine, có thể là security context thực thi tùy DBMS.

Kiểm tra ba lớp quyền riêng biệt:

1. **Namespace/schema:** ví dụ quyền `USAGE` trên schema ở PostgreSQL.
2. **Quyền thực thi routine:** `EXECUTE` trên procedure/function.
3. **Quyền lên bảng, view, sequence và routine khác bên trong:** phụ thuộc mô hình definer/invoker, ownership chaining, role và dynamic SQL.

Có `EXECUTE` không tự bảo đảm thủ tục có đủ quyền truy cập mọi bảng, cũng không phải lý do để cấp quyền trực tiếp quá rộng cho tài khoản runtime.

### 7.1. PostgreSQL: cấp quyền có giới hạn

Giả định đã có schema `finance`, role `app_runtime` và thủ tục `finance.transfer(integer, integer, integer)`. Một DBA có thể thực thi:

```sql
BEGIN;

REVOKE ALL ON PROCEDURE finance.transfer(integer, integer, integer)
    FROM PUBLIC;

GRANT USAGE ON SCHEMA finance TO app_runtime;

GRANT EXECUTE ON PROCEDURE finance.transfer(integer, integer, integer)
    TO app_runtime;

COMMIT;
```

Đây là **đoạn quản trị quyền minh họa**, không phải script tạo đầy đủ role/routine. PostgreSQL có thể cấp quyền EXECUTE mặc định cho PUBLIC trên routine mới, nên cần chủ động rà soát. Chữ ký `(integer, integer, integer)` phân biệt overload; đừng grant nhầm routine cùng tên có kiểu tham số khác.

Nếu procedure chạy `SECURITY INVOKER` (thường là mặc định), `app_runtime` còn cần quyền cần thiết trên các đối tượng bên trong. Nếu procedure chạy `SECURITY DEFINER`, truy cập bên trong có thể dùng quyền owner; điều này cho phép giới hạn quyền bảng trực tiếp của app nhưng phải review body procedure kỹ hơn.

### 7.2. Invoker vs definer theo từng nhà cung cấp

| DBMS | Kiểu security context | Điểm cần kiểm tra |
|---|---|---|
| PostgreSQL | `SECURITY INVOKER` / `SECURITY DEFINER` | Owner privileges, `search_path`, schema/EXECUTE grants; definer procedure bị hạn chế transaction control. |
| MySQL | `SQL SECURITY DEFINER` / `SQL SECURITY INVOKER` với `DEFINER` account | Mặc định thường là DEFINER; caller cần EXECUTE, quyền bên trong theo context; definer account và active roles có quy tắc riêng. |
| SQL Server | `EXECUTE AS CALLER/OWNER/SELF`, ownership chaining, module signing | Quyền EXECUTE và chuỗi ownership; dynamic SQL có thể phải kiểm tra quyền khác DML tĩnh. |
| Oracle | `AUTHID DEFINER` / `AUTHID CURRENT_USER` | Definer rights mặc định; invoker rights dùng context người gọi; direct grants/roles cần xem kỹ. |

### 7.3. Quyền cao và dynamic SQL

Routine chạy với quyền definer có thể cho caller thực hiện những hành vi mà caller không được phép làm trực tiếp. Nếu thủ tục nhận dữ liệu để ghép thành dynamic SQL, tên đối tượng, điều kiện hoặc đường dẫn từ input không tin cậy, có rủi ro SQL injection hoặc lạm dụng quyền.

Nguyên tắc:

- Dữ liệu phải bind qua tham số đúng kiểu. **Không** ghép input thành câu SQL động tùy ý.
- Nếu thật sự phải tạo dynamic SQL với tên bảng/cột động, dùng cơ chế quote identifier đúng DBMS và allowlist; placeholder `?` không dùng để bind tên bảng/cột.
- Với PostgreSQL `SECURITY DEFINER`, cố định `search_path` vào các schema đáng tin và xử lý `pg_temp` an toàn; tránh schema mà user không tin cậy có quyền tạo object.
- Chỉ cấp `EXECUTE` đúng các routine cần thiết; tách role migration/schema owner khỏi role runtime.
- Kiểm tra privilege bằng đúng tài khoản database của ứng dụng, không chỉ bằng superuser trên máy dev.

`withSchemaName(...)` của Spring chỉ định vị routine; **không tự thêm `GRANT`**, không bật definer rights và không thay đổi role hiện hành.

## 8. Phụ thuộc nhà cung cấp của thủ tục/hàm: Spring trừu tượng hóa đến đâu?

Spring JDBC giúp tạo `CallableStatement`, bind IN/OUT parameters, ánh xạ result sets và dịch `SQLException` thành `DataAccessException`. Nó **không tự dịch body PL/pgSQL thành PL/SQL hay T-SQL**, cũng không bảo đảm cùng transaction/privilege semantics ở mọi database.

### 8.1. Cú pháp, function và procedure

- PostgreSQL phân biệt `CALL` cho procedure, `SELECT` cho function; với pgJDBC phải kiểm tra `escapeSyntaxCallMode`.
- MySQL có `CREATE PROCEDURE/CREATE FUNCTION`, `CALL`, `IN/OUT/INOUT` và `SQL SECURITY`.
- SQL Server dùng T-SQL `EXEC`, `OUTPUT` parameters, return status và có thể trả nhiều result sets.
- Oracle dùng PL/SQL procedure/function/package, `REF CURSOR` và các kiểu dữ liệu riêng.

Không nên đem nguyên file SQL tạo procedure của một hãng sang hãng khác và mong nó chạy không thay đổi.

### 8.2. JDBC metadata và khai báo tường minh

`SimpleJdbcCall` có thể dựa vào JDBC metadata để suy ra số lượng, tên và SQL types của tham số. Tuy nhiên, metadata không phải lúc nào giống nhau giữa driver/version, đặc biệt với overload, schema/catalog, REF_CURSOR và OUT parameters. Ví dụ tự khai báo:

```java
SimpleJdbcCall queryTotal = new SimpleJdbcCall(jdbcTemplate)
        .withSchemaName("finance")
        .withProcedureName("read_total")
        .withoutProcedureColumnMetaDataAccess()
        .declareParameters(
            new SqlParameter("p_id", Types.INTEGER),
            new SqlOutParameter("p_total", Types.NUMERIC)
        );
```

Đây là **mẫu API**, chỉ hợp lệ nếu schema, tên procedure, kiểu và hướng tham số thực tế khớp. Cần import `java.sql.Types`, `SqlParameter` và `SqlOutParameter`. OUT `NUMERIC` có thể trả `BigDecimal`; không ép bừa sang `int`. INOUT dùng `SqlInOutParameter` phù hợp.

Những điểm cần kiểm thử theo engine:

1. OUT/INOUT có thể có tên, vị trí và cách đăng ký khác nhau.
2. Function return value khác OUT parameter của procedure; chọn `withFunctionName`/`executeFunction` khi thực sự gọi function.
3. REF_CURSOR Oracle, PostgreSQL refcursor, result sets SQL Server/MySQL có giao thức và vòng đời connection khác nhau.
4. Tên output Map có thể đổi hoa/thường; `JdbcTemplate.setResultsMapCaseInsensitive(true)` có thể hữu ích khi thích hợp.
5. SQLSTATE/error code, khóa và timeout khác nhau; `DataAccessException` không làm chúng đồng nhất tuyệt đối.
6. Schema/case-sensitivity và overload của routine có thể tạo lời gọi mơ hồ hoặc chạy nhầm routine.

### 8.3. Ví dụ tùy chọn URL riêng của pgJDBC

```text
jdbc:postgresql://localhost:54329/lesson?escapeSyntaxCallMode=callIfNoReturn
```

Theo tài liệu pgJDBC, mặc định `select` dành cho khả năng tương thích gọi function. `callIfNoReturn` dịch JDBC escape không có return parameter sang `CALL` để gọi procedure, còn lời gọi có return parameter dùng con đường function. Không copy tùy chọn này sang driver của hãng khác mà không kiểm tra.

### 8.4. Khoanh vùng dependency trong tầng truy cập dữ liệu

```java
public interface TransferGateway {
    void transfer(int fromAccount, int toAccount, int amount);
}
```

Đây là interface minh họa; một adapter PostgreSQL có thể dùng `SimpleJdbcCall`, một adapter Oracle có thể dùng API/SQL khác. Interface giúp giới hạn phần code ứng dụng biết tên procedure và kiểu DBMS. Tuy nhiên, logic trong routine, DDL migration, quyền và transaction semantics vẫn phải được kiểm thử khi chuyển vendor. Không hứa rằng chỉ đổi JDBC URL là đủ.

## 9. Lỗi phổ biến và hướng xử lý

| Triệu chứng | Nguyên nhân thường gặp | Điều cần kiểm tra |
|---|---|---|
| `@Transactional` rollback nhưng dữ liệu procedure còn nguyên | Procedure đã commit, autonomous transaction, DDL implicit commit, hoặc khác connection/transaction. | Body routine, transaction manager, DataSource, engine semantics. |
| PostgreSQL báo `invalid transaction termination` | Procedure cố `COMMIT`/`ROLLBACK` trong transaction block hoặc context bị cấm. | Loại commit khỏi routine hoặc thiết kế lại lời gọi top-level. |
| `permission denied` khi gọi | Thiếu `EXECUTE` hoặc quyền schema, thiếu role, nhầm overload. | Runtime user, signature, schema, grants. |
| Có `EXECUTE` nhưng procedure thiếu quyền trên bảng | Invoker thiếu DML privilege, definer thiếu quyền hoặc security context không như dự kiến. | Invoker/definer, owner và quyền đối tượng nội bộ. |
| Kết quả OUT sai tên hoặc lỗi bind | Metadata driver không đáng tin, khác casing, sai kiểu IN/OUT/INOUT. | Driver/version, `declareParameters`, `SqlOutParameter`. |
| PostgreSQL escape call tìm function thay vì procedure | Driver đang ở `escapeSyntaxCallMode=select`. | Cấu hình driver hoặc native `CALL`. |
| Procedure trả “FAIL” nhưng dữ liệu đã commit | Lỗi bị bắt mà caller vẫn kết thúc bình thường. | Thỏa thuận OUT status/error, rollback rule và kiểm tra dữ liệu. |
| Lock timeout, deadlock, request treo | Procedure cập nhật nhiều đối tượng, lock order/isolation không nhất quán. | Lock wait, execution plan, timeout và retry chính xác. |
| Test local chạy nhưng production lỗi | Khác phiên bản DBMS/driver, privilege, schema, collation, type. | Integration test trên cấu hình và role runtime tương đương production. |

Không retry vô điều kiện khi connection mất giữa chừng: lỗi mạng không chứng minh procedure **chưa** commit. Thiết kế khóa idempotency, business unique constraint, reconciliation hoặc transactional outbox nếu cần đảm bảo phát sự kiện một lần theo nghiệp vụ. Dữ liệu gửi sang email, HTTP hoặc hàng đợi ngoài database không tự được rollback bởi JDBC.

## 10. Checklist kiểm thử integration và triển khai

Một unit test mock `SimpleJdbcCall` chỉ kiểm tra mapping ở Java, không chứng minh database rollback hay security context. Các ca kiểm thử quan trọng:

1. **Happy path:** procedure cập nhật đúng dữ liệu, OUT/result set đúng, transaction commit.
2. **Rollback sau CALL:** procedure ghi dữ liệu rồi service ném unchecked exception; đọc lại mọi bảng liên quan.
3. **Lỗi giữa CALL:** procedure cập nhật một phần rồi vi phạm constraint hoặc `RAISE`; không để lại thay đổi trái mong đợi.
4. **Kiểm thử bằng runtime role thật:** tài khoản có đúng `USAGE`/`EXECUTE`, bị từ chối khi truy cập bảng/routine không được cấp.
5. **Definer/Invoker:** cùng lời gọi với role khác nhau và các trường hợp dynamic SQL/search_path.
6. **Sai metadata:** overload, case của tên OUT, kiểu SQL, schema/catalog, driver options.
7. **Transaction control:** thử procedure có transaction statements (nếu được DBMS hỗ trợ) để xác định hợp đồng chính xác, nhất là khi có `@Transactional`.
8. **Concurrency:** hai giao dịch đồng thời, isolation, lock, deadlock và retry.
9. **Timeout/mất kết nối:** đối soát trạng thái commit trước khi retry; kiểm tra side effect ngoài database.

Trước khi release, xác định và ghi rõ ai sở hữu transaction, thủ tục có được phép commit không, quyền tối thiểu của role runtime, vendor/version và phương án phục hồi khi thất bại một phần.

## 11. Tự kiểm tra kiến thức

**1.** Service `@Transactional` gọi procedure thay đổi hai bảng, rồi ném `RuntimeException`. Khi nào rollback được cả hai bảng?  
**Đáp án:** khi Spring thực sự quản lý cùng transaction/connection, procedure không commit độc lập và DBMS có thể rollback các DML liên quan.

**2.** Vì sao PostgreSQL procedure chứa `COMMIT` không chạy được dưới `TransactionTemplate` như một lệnh bình thường?  
**Đáp án:** vì `CALL` đang nằm trong transaction block; PostgreSQL không cho routine kết thúc transaction ở context đó.

**3.** Tài khoản ứng dụng được cấp `EXECUTE` nhưng routine vẫn thiếu quyền `UPDATE` trên bảng. Có thể vì sao?  
**Đáp án:** procedure chạy với quyền invoker hoặc definer không có quyền phù hợp; cần kiểm tra context/owner/role/schema.

**4.** Oracle autonomous transaction ghi nhật ký đã `COMMIT`. Outer transaction rollback có xóa nhật ký đó không?  
**Đáp án:** không tự động; đó là transaction độc lập.

**5.** Procedure MySQL tự commit xong, service Spring báo lỗi. Có chắc mọi thay đổi rollback được?  
**Đáp án:** không; phải xem transaction control trong procedure, auto-commit và DBMS semantics.

**6.** Nếu dùng `SimpleJdbcCall` có thể bê nguyên logic PL/pgSQL sang SQL Server không?  
**Đáp án:** không. Spring hỗ trợ lời gọi JDBC, không dịch ngôn ngữ routine, quyền và luật transaction của vendor.

**7.** Procedure bắt lỗi, trả output `FAILED` và không ném exception. Spring có tự rollback không?  
**Đáp án:** không. Caller phải hiểu output và chuyển thành rollback/error theo hợp đồng nghiệp vụ.

## Tài liệu tham khảo

- Spring Framework — SimpleJdbcCall: https://docs.spring.io/spring-framework/reference/data-access/jdbc/simple.html
- Spring Framework — Declarative Transaction Implementation: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-decl-explained.html
- Spring Framework — Rollback Rules: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/rolling-back.html
- Spring Framework — Transaction Propagation: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html
- PostgreSQL — CALL: https://www.postgresql.org/docs/current/sql-call.html
- PostgreSQL — CREATE PROCEDURE: https://www.postgresql.org/docs/current/sql-createprocedure.html
- PostgreSQL — PL/pgSQL Transaction Management: https://www.postgresql.org/docs/current/plpgsql-transactions.html
- PostgreSQL — SECURITY DEFINER and search_path: https://www.postgresql.org/docs/current/sql-createfunction.html
- pgJDBC — Calling Stored Functions and Procedures: https://jdbc.postgresql.org/documentation/callproc/
- pgJDBC — Driver Settings: https://jdbc.postgresql.org/documentation/use/
- MySQL 8.4 — Stored Procedures and Functions: https://dev.mysql.com/doc/refman/8.4/en/create-procedure.html
- Microsoft SQL Server — EXECUTE AS: https://learn.microsoft.com/en-us/sql/t-sql/statements/execute-as-clause-transact-sql
- Oracle Database — Definer's/Invoker's Rights: https://docs.oracle.com/en/database/oracle/oracle-database/19/dbseg/definers-rights-and-invokers-rights.html
- Oracle Database — Autonomous Transactions: https://docs.oracle.com/en/database/oracle/oracle-database/26/lnpls/autonomous-transactions.html
