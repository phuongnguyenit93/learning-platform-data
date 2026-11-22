# Thiết kế thí nghiệm hai kết nối để quan sát các hiện tượng mức cô lập giao dịch

## 1. Tại sao cần hai kết nối?

Khi học `@Transactional(isolation = ...)` trong Spring, chỉ đọc định nghĩa `READ_COMMITTED`, `REPEATABLE_READ` hay `SERIALIZABLE` không đủ để hình dung **một giao dịch có thể nhìn thấy những thay đổi của giao dịch khác ở thời điểm nào**.

Một chương trình thực nghiệm tốt phải mô phỏng **hai phiên làm việc độc lập với cơ sở dữ liệu**:

- **Kết nối A** đại diện cho transaction T1 đang đọc, giữ một snapshot hoặc tính toán quyết định nghiệp vụ.
- **Kết nối B** đại diện cho transaction T2 thay đổi dữ liệu và chủ động `COMMIT` hoặc `ROLLBACK`.
- Chương trình **điều khiển chính xác thứ tự** các câu lệnh A/B, thay vì dựa vào `Thread.sleep(...)` hay hy vọng một race condition sẽ xuất hiện.
- Sau từng thí nghiệm, dữ liệu được **reset về một trạng thái đã biết** để kết quả không phụ thuộc vào thí nghiệm trước.
- Kết quả được giải thích dựa trên **DBMS và mức cô lập thực tế**. Tiêu chuẩn SQL quy định mức bảo đảm tối thiểu, không bắt mọi hệ quản trị tạo ra cùng một hiện tượng.

Bài học này thiết kế một phòng thí nghiệm cho chủ đề **Mức cô lập (transaction isolation)** trong Spring Framework transaction management. Phần thực hành chính dùng **hai JDBC `Connection` thực sự khác nhau**, Java 17+, Spring Boot và PostgreSQL.

> **Quy tắc cốt lõi:** không thể quan sát dirty read, non-repeatable read, phantom read hoặc các anomaly đồng thời khác bằng cách chỉ chạy tuần tự mọi câu lệnh trên **một transaction/connection duy nhất**. Cần ít nhất hai transaction có thứ tự đan xen được kiểm soát.

### Kết quả mong đợi sau bài học

Bạn có thể:

1. Viết một lịch thao tác (schedule) rõ ràng cho hai kết nối A/B: ai `BEGIN`, ai đọc, ai ghi, ai `COMMIT/ROLLBACK`, ai đọc lần hai.
2. Phân biệt **dirty read**, **non-repeatable read**, **phantom read**, **lost update** do read-modify-write không an toàn và **serialization anomaly**.
3. Chạy Java 17+ với **hai JDBC connections** và quan sát các kết quả định lượng có thể tái lập.
4. Biết **vì sao PostgreSQL không cho dirty read ngay cả khi yêu cầu `READ_UNCOMMITTED`**, và vì sao PostgreSQL `REPEATABLE_READ` cũng chặn phantom read.
5. Kết nối việc đo đạc với `@Transactional(isolation = ...)` của Spring, propagation và transaction manager.
6. Tránh kết luận sai do auto-commit, snapshot khởi tạo muộn, lấy nhầm cùng connection, lock chờ hoặc test đã có transaction ngoài.

## 2. Định nghĩa các hiện tượng cần quan sát

### 2.1. Dirty read — đọc dữ liệu chưa commit

T2 cập nhật số dư từ 100 lên 200 **nhưng chưa commit**. T1 đọc được 200. Sau đó T2 rollback khiến dữ liệu thật trở về 100.

```text
Trạng thái ban đầu: balance = 100

B / T2: BEGIN
B / T2: UPDATE balance = 200       (chưa COMMIT)
A / T1: SELECT balance              (nếu thấy 200 => dirty read)
B / T2: ROLLBACK
A / T1: SELECT balance              (có thể lại thấy 100)
```

Một DBMS có thể **không hỗ trợ dirty read** ngay cả khi SQL API chấp nhận isolation `READ_UNCOMMITTED`. PostgreSQL là ví dụ quan trọng: yêu cầu `READ_UNCOMMITTED` được xử lý với bảo đảm như `READ_COMMITTED`, nên thí nghiệm PostgreSQL phải thấy **100**, không thấy 200.

Nếu muốn trình diễn dirty read thật sự, cần chọn một hệ quản trị và cấu hình cho phép nó, chẳng hạn MySQL/InnoDB tại `READ UNCOMMITTED`, và kiểm chứng trên phiên bản đó. **Không dùng dirty read trong xử lý tiền hoặc nghiệp vụ cần consistency**.

### 2.2. Non-repeatable read — cùng một hàng, hai giá trị

T1 đọc cùng một hàng hai lần trong **cùng một transaction**. Giữa hai lần đọc, T2 cập nhật hàng đó và **commit**:

```text
Ban đầu: balance = 100

A / T1: BEGIN
A / T1: SELECT balance  -> 100
B / T2: BEGIN
B / T2: UPDATE balance = 120
B / T2: COMMIT
A / T1: SELECT balance  -> 120 (READ_COMMITTED ở PostgreSQL)
A / T1: ROLLBACK
```

Hiện tượng là **một hàng đã đọc thay đổi giá trị giữa hai lần đọc**. Đối chiếu:

- PostgreSQL `READ_COMMITTED`: SELECT thứ hai thường thấy 120 vì mỗi statement có snapshot mới.
- PostgreSQL `REPEATABLE_READ`: SELECT thứ hai vẫn thấy 100, vì transaction T1 tiếp tục nhìn snapshot đã cố định từ lần statement đầu.

### 2.3. Phantom read — cùng điều kiện, tập hàng thay đổi

T1 thực hiện lại một truy vấn lọc theo điều kiện:

```sql
SELECT COUNT(*) FROM lab_items WHERE category = 'READY';
```

T2 chèn một bản ghi mới có `category='READY'` rồi commit giữa hai lần SELECT của T1:

```text
Ban đầu: READY có 1 hàng

A / T1: SELECT COUNT(*) WHERE category='READY' -> 1
B / T2: INSERT hàng READY mới
B / T2: COMMIT
A / T1: SELECT COUNT(*) WHERE category='READY' -> 2 (có phantom)
```

Khác với non-repeatable read, ở đây **tập hàng thỏa điều kiện thay đổi** chứ không chỉ giá trị của hàng đã đọc. Một phép `COUNT(*)` rất tiện để quan sát, nhưng không nên đánh đồng bản thân số đếm với bản chất của hiện tượng: nó đại diện cho tập kết quả đã thay đổi.

PostgreSQL `READ_COMMITTED` cho phép phantom read; PostgreSQL `REPEATABLE_READ` **ngăn phantom read**, dù tiêu chuẩn SQL có thể cho phép phantom ở mức REPEATABLE READ như một bảo đảm tối thiểu.

### 2.4. Lost update — ghi đè kết quả từ phép đọc cũ

Hai transaction đọc cùng `balance=100`. T2 tính `100+20=120` và commit. T1 sau đó lấy giá trị **đã đọc từ trước** để tính `100+10=110` rồi UPDATE số dư bằng hằng 110, ghi đè giá trị mới của T2.

```text
A: READ balance -> 100
B: READ balance -> 100
B: UPDATE balance = 120; COMMIT
A: UPDATE balance = 110; COMMIT

Cuối cùng: balance = 110
Đúng nếu cộng cả +20 và +10: balance = 130
```

Đây là **lost update do client read–modify–write không an toàn**. Nó có thể xuất hiện tại PostgreSQL `READ_COMMITTED` khi một ứng dụng đọc giá trị cũ vào Java và sau đó gửi `UPDATE balance = ?` từ giá trị đã tính trước.

**Cách giảm rủi ro:** câu SQL `UPDATE lab_account SET balance = balance + ? WHERE id = ?` tính trên giá trị hiện hành tại DB, optimistic locking với version, pessimistic lock hoặc transaction/isolation thích hợp. Không xem mọi dạng lost update là một hiện tượng tiêu chuẩn có cùng định nghĩa/chế độ ở tất cả DBMS.

### 2.5. Serialization anomaly / write skew — mức nâng cao

Hai transaction cùng kiểm tra một điều kiện tổng thể, ví dụ “phải còn ít nhất một bác sĩ trực”, rồi mỗi transaction cập nhật **một hàng khác nhau**. Nếu cả hai đọc trạng thái trước khi người kia commit, mỗi người có thể tin còn bác sĩ khác và tự rời ca. Cuối cùng không còn ai trực.

PostgreSQL `REPEATABLE_READ` có thể cho tình huống write skew này xảy ra vì snapshot không đảm bảo lịch sử tương đương thực thi tuần tự cho mọi trường hợp. `SERIALIZABLE` của PostgreSQL có thể phát hiện một lịch trình không tuần tự hóa được và **hủy một transaction bằng SQLSTATE `40001`**. Ứng dụng cần retry **toàn bộ transaction** khi gặp serialization failure.

Bài chính trước hết cố định bốn phép đo đơn giản; cuối bài có thêm lịch hai cửa sổ SQL cho write skew/serializable.

## 3. Bảng đối chiếu: tiêu chuẩn SQL và PostgreSQL

| Isolation | Dirty read (PG) | Non-repeatable read (PG) | Phantom read (PG) | Serialization anomaly |
| --- | --- | --- | --- | --- |
| `READ_UNCOMMITTED` | Không | Có thể | Có thể | Có thể |
| `READ_COMMITTED` | Không | Có thể | Có thể | Có thể |
| `REPEATABLE_READ` | Không | Không | **Không** | Có thể |
| `SERIALIZABLE` | Không | Không | Không | Không cho cả hai transaction cùng commit với lịch trình không tuần tự hóa được; có thể trả lỗi `40001` |

Bảng này nói riêng về **PostgreSQL**; không dùng nó để tiên đoán SQL Server, Oracle, MySQL hay H2 mà không xem tài liệu DBMS tương ứng.

Hai ngoại lệ dễ nhớ:

1. PostgreSQL thực thi `READ_UNCOMMITTED` giống `READ_COMMITTED`, nên không đọc dữ liệu chưa commit.
2. PostgreSQL `REPEATABLE_READ` mạnh hơn mức bảo đảm tối thiểu của tiêu chuẩn ở khía cạnh phantom read, vì dựa trên snapshot.

### Snapshot thực sự được lấy ở thời điểm nào?

Với PostgreSQL `READ_COMMITTED`, mỗi statement `SELECT` thông thường nhìn một snapshot tại lúc statement bắt đầu. Hai SELECT khác nhau trong cùng T1 có thể nhìn giá trị khác nhau khi T2 đã commit ở giữa.

Với PostgreSQL `REPEATABLE_READ`, snapshot của transaction được cố định ở **lần đầu chạy một statement không phải câu lệnh điều khiển transaction**, chứ không nhất thiết ngay tại dòng Java `setAutoCommit(false)`. Do đó, để thí nghiệm đúng:

- Cho A chạy **SELECT đầu tiên** để thiết lập snapshot;
- Sau đó mới cho B thay đổi và commit;
- Cuối cùng cho A chạy SELECT thứ hai trong **cùng transaction A**.

Nếu bạn gọi B commit **trước lần SELECT đầu của A**, không thể dùng kết quả đó chứng minh repeatable read có giữ snapshot hay không.

## 4. Thiết kế lịch thao tác hai kết nối một cách khoa học

### 4.1. Quy ước

- **A** = reader hoặc transaction thứ nhất.
- **B** = writer hoặc transaction thứ hai.
- **T1/T2** = hai physical transactions độc lập.
- **R1/R2** = lần đọc thứ nhất/thứ hai của A.
- **W2** = thao tác ghi của B.
- **C2** = `COMMIT` của B.
- **X2** = `ROLLBACK` của B.
- **S0** = trạng thái database đã reset và commit trước mỗi thí nghiệm.

Đối với các thí nghiệm có thể điều khiển hoàn toàn bằng thứ tự statement, **không cần hai Java threads**: một chương trình Java có thể mở hai `Connection` cùng lúc và lần lượt gửi lệnh A/B theo lịch định sẵn. Database vẫn nhìn thấy **hai transaction đồng thời chưa kết thúc**, dù thread Java luân phiên thao tác trên chúng.

### 4.2. Bốn lịch thí nghiệm chính

| Hiện tượng | Lịch bắt buộc | Đọc gì? | Điều có thể kết luận |
| --- | --- | --- | --- |
| Dirty read | S0 → B BEGIN → B UPDATE chưa commit → A SELECT → B ROLLBACK | Giá trị A thấy khi B chưa commit | Có/không thấy uncommitted value |
| Non-repeatable read | S0 → A BEGIN/R1 → B BEGIN/W2/C2 → A R2 | Hai lần SELECT cùng hàng của A | Giá trị một hàng có đổi trong T1 không |
| Phantom read | S0 → A BEGIN/R1 (predicate) → B INSERT/C2 → A R2 (cùng predicate) | Hai tập hàng/COUNT của A | Tập kết quả có đổi không |
| Lost update | S0 → A đọc cũ → B đọc cũ → B UPDATE/C2 → A UPDATE từ giá trị cũ/C1 | Giá trị cuối của một hàng | Một update có bị ghi đè bởi stale write không |

Để so sánh các isolation levels, **giữ nguyên lịch thao tác và dữ liệu**, chỉ thay isolation của connection phù hợp; nếu thay nhiều thứ cùng lúc, bạn không biết yếu tố nào làm kết quả đổi.

### 4.3. Những biến phải kiểm soát

1. **DBMS/phiên bản:** dùng đúng PostgreSQL trong thí nghiệm chính.
2. **Hai physical connections:** không tạo hai biến Java trỏ đến cùng `Connection`.
3. **Auto-commit:** đặt `setAutoCommit(false)` cho A/B trước lịch thử, để connection giữ transaction qua nhiều statements.
4. **Isolation:** gọi `setTransactionIsolation(...)` trước khi transaction của connection bắt đầu.
5. **Trạng thái ban đầu:** reset DB bằng một connection riêng, để reset **commit xong** trước khi bắt đầu A/B.
6. **Thứ tự A/B:** không dựa vào độ trễ thread; điều khiển rõ ai commit/rollback trước ai đọc lần hai.
7. **Phép đọc so sánh:** cùng câu SQL, cùng predicate, trên **cùng connection A và cùng T1**.
8. **Cleanup:** đóng `ResultSet`/`Statement`; kết thúc T1/T2 bằng commit hoặc rollback trong mọi đường đi; sau đó đóng cả hai connection.
9. **Hiện tượng phụ:** tránh row locks không cần thiết, triggers, cache ứng dụng, background jobs hoặc test data bị tái sử dụng.
10. **Đầu ra:** in con số cụ thể và isolation dùng để giải thích vì sao quan sát có hoặc không có anomaly.

### 4.4. Tại sao không dùng @Transactional bao quanh một test method rồi mở “hai kết nối”?

Khi mục tiêu là **kiểm soát hai physical JDBC transactions thủ công**, đặt `@Transactional` trên chính method điều phối có thể gây nhiễu: Spring có thể gắn transaction vào thread hoặc bạn vô tình dùng `JdbcTemplate`/repository tham gia một transaction đã có.

Thí nghiệm dưới đây chủ động dùng `DataSource.getConnection()` lấy **hai JDBC connections riêng**, điều khiển `autoCommit/commit/rollback` **trực tiếp**, và không đánh dấu `@Transactional` lên `CommandLineRunner`. Đây là cách cô lập biến “isolation level” tốt hơn cho bài lab.

Trong ứng dụng nghiệp vụ thực, bạn có thể dùng `@Transactional(isolation = ...)` và Spring transaction manager để quản lý transaction; mục 10 giải thích cách ánh xạ kết quả.

## 5. Môi trường thí nghiệm tái lập

### 5.1. PostgreSQL thử nghiệm

Cần Docker đang chạy. Tạo một database PostgreSQL 16 **chỉ cho mục đích local lab**:

```bash
docker run --name spring-isolation-lab \
  -e POSTGRES_DB=isolation_lab \
  -e POSTGRES_USER=lab \
  -e POSTGRES_PASSWORD=lab \
  -p 55432:5432 \
  -d postgres:16
```

Lệnh trên theo cú pháp bash. Trên Windows PowerShell, có thể viết thành **một dòng**:

```powershell
docker run --name spring-isolation-lab -e POSTGRES_DB=isolation_lab -e POSTGRES_USER=lab -e POSTGRES_PASSWORD=lab -p 55432:5432 -d postgres:16
```

Kiểm tra container đã sẵn sàng:

```bash
docker exec spring-isolation-lab pg_isready -U lab -d isolation_lab
```

Nếu tên container hoặc port đã tồn tại, chọn tên/port khác rồi điều chỉnh URL JDBC. Tránh dùng những user/password demo này ngoài máy học. Bài học tự xóa/tạo lại **bảng có prefix `lab_`** trong database thử nghiệm, nên **không trỏ nó vào database có dữ liệu thật**.

### 5.2. Project Spring Boot Java 17+

Tạo Maven project từ Spring Initializr với:

- Java 17+; Spring Boot 3.x phù hợp với JDK.
- Dependencies **Spring JDBC** / `spring-boot-starter-jdbc` và **PostgreSQL Driver**.
- Package: `com.example.isolationlab`.

Giữ file `pom.xml` đầy đủ do Initializr tạo, gồm Spring Boot parent, version và Maven plugin. Phần dependencies tương ứng:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-jdbc</artifactId>
    </dependency>
    <dependency>
        <groupId>org.postgresql</groupId>
        <artifactId>postgresql</artifactId>
        <scope>runtime</scope>
    </dependency>
</dependencies>
```

Đây chỉ là **phần dependencies**, không phải toàn bộ POM. Spring Boot dependency management sẽ cung cấp các version tương thích với bản Boot đã chọn.

Cấu trúc file:

```text
src/main/
  java/com/example/isolationlab/
    IsolationLabApplication.java
  resources/
    application.properties
```

File `src/main/resources/application.properties`:

```properties
spring.main.web-application-type=none
spring.datasource.url=jdbc:postgresql://localhost:55432/isolation_lab
spring.datasource.username=lab
spring.datasource.password=lab
spring.datasource.hikari.maximum-pool-size=5
spring.datasource.hikari.auto-commit=true
logging.level.root=WARN
```

Pool size 5 đủ cho một bài lab điều khiển đồng bộ, nơi A/B cùng giữ hai connections. Đây không phải thông số dành cho production; khi ứng dụng chạy nhiều transaction đồng thời, cần tính capacity theo workload.

## 6. Chương trình Java 17+ đầy đủ với hai JDBC connections

File duy nhất `src/main/java/com/example/isolationlab/IsolationLabApplication.java`:

```java
package com.example.isolationlab;

import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Statement;

import javax.sql.DataSource;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class IsolationLabApplication {

    public static void main(String[] args) {
        SpringApplication.run(IsolationLabApplication.class, args);
    }

    @Bean
    CommandLineRunner lab(DataSource dataSource) {
        return args -> {
            initialize(dataSource);
            verifyConnections(dataSource);

            dirtyRead(dataSource);
            nonRepeatableRead(
                dataSource, Connection.TRANSACTION_READ_COMMITTED,
                "READ_COMMITTED");
            nonRepeatableRead(
                dataSource, Connection.TRANSACTION_REPEATABLE_READ,
                "REPEATABLE_READ");

            phantomRead(
                dataSource, Connection.TRANSACTION_READ_COMMITTED,
                "READ_COMMITTED");
            phantomRead(
                dataSource, Connection.TRANSACTION_REPEATABLE_READ,
                "REPEATABLE_READ");

            lostUpdate(dataSource);
            atomicIncrement(dataSource);
        };
    }

    private static void initialize(DataSource ds) throws SQLException {
        // Chỉ chạy trên DB LAB riêng: thao tác DDL xóa bảng thử nghiệm.
        try (Connection c = ds.getConnection();
             Statement s = c.createStatement()) {
            s.execute("DROP TABLE IF EXISTS lab_items");
            s.execute("DROP TABLE IF EXISTS lab_account");

            s.execute("""
                CREATE TABLE lab_account (
                    id INTEGER PRIMARY KEY,
                    balance INTEGER NOT NULL
                )
                """);
            s.execute("""
                INSERT INTO lab_account(id, balance) VALUES (1, 100)
                """);

            s.execute("""
                CREATE TABLE lab_items (
                    id INTEGER PRIMARY KEY,
                    category VARCHAR(20) NOT NULL
                )
                """);
            s.execute("""
                INSERT INTO lab_items(id, category) VALUES (1, 'READY')
                """);
        }
    }

    private static void verifyConnections(DataSource ds)
            throws SQLException {
        try (Connection a = ds.getConnection();
             Connection b = ds.getConnection()) {

            int pidA = number(a, "SELECT pg_backend_pid()");
            int pidB = number(b, "SELECT pg_backend_pid()");

            System.out.println(
                "[lab] distinct-backends=" + (pidA != pidB));
        }
    }

    private static void dirtyRead(DataSource ds) throws SQLException {
        resetAccount(ds);

        try (Connection a = ds.getConnection();
             Connection b = ds.getConnection()) {

            // A là reader, B là writer.
            a.setTransactionIsolation(
                Connection.TRANSACTION_READ_UNCOMMITTED);
            b.setTransactionIsolation(
                Connection.TRANSACTION_READ_COMMITTED);
            a.setAutoCommit(false);
            b.setAutoCommit(false);

            setBalance(b, 200);    // B chưa commit.
            int seen = balance(a); // PostgreSQL không đọc giá trị dirty.

            b.rollback();          // Hủy thay đổi chưa commit của B.
            int afterRollback = balance(a);

            a.rollback();

            System.out.printf(
                "[lab] dirty READ_UNCOMMITTED (PostgreSQL): "
                    + "seen=%d, afterRollback=%d%n",
                seen, afterRollback);
        }
    }

    private static void nonRepeatableRead(
            DataSource ds, int isolation, String label)
            throws SQLException {

        resetAccount(ds);

        try (Connection a = ds.getConnection();
             Connection b = ds.getConnection()) {

            a.setTransactionIsolation(isolation);
            b.setTransactionIsolation(
                Connection.TRANSACTION_READ_COMMITTED);
            a.setAutoCommit(false);
            b.setAutoCommit(false);

            // Chính SELECT đầu tiên thiết lập snapshot của A.
            int first = balance(a);

            setBalance(b, 120);
            b.commit();            // B commit giữa hai lần SELECT.

            int second = balance(a); // Cùng query, cùng A/T1.
            a.rollback();

            System.out.printf(
                "[lab] non-repeatable %s: first=%d, second=%d%n",
                label, first, second);
        }
    }

    private static void phantomRead(
            DataSource ds, int isolation, String label)
            throws SQLException {

        resetItems(ds);

        try (Connection a = ds.getConnection();
             Connection b = ds.getConnection()) {

            a.setTransactionIsolation(isolation);
            b.setTransactionIsolation(
                Connection.TRANSACTION_READ_COMMITTED);
            a.setAutoCommit(false);
            b.setAutoCommit(false);

            int first = countReady(a);

            try (PreparedStatement p = b.prepareStatement("""
                    INSERT INTO lab_items(id, category)
                    VALUES (?, ?)
                    """)) {
                p.setInt(1, 2);
                p.setString(2, "READY");
                p.executeUpdate();
            }
            b.commit();             // Thêm phantom row đã commit.

            int second = countReady(a);
            a.rollback();

            System.out.printf(
                "[lab] phantom %s: first=%d, second=%d%n",
                label, first, second);
        }
    }

    private static void lostUpdate(DataSource ds)
            throws SQLException {

        resetAccount(ds);

        try (Connection a = ds.getConnection();
             Connection b = ds.getConnection()) {

            a.setTransactionIsolation(
                Connection.TRANSACTION_READ_COMMITTED);
            b.setTransactionIsolation(
                Connection.TRANSACTION_READ_COMMITTED);
            a.setAutoCommit(false);
            b.setAutoCommit(false);

            int firstA = balance(a); // A nhớ 100 trong Java.
            int firstB = balance(b); // B cũng nhớ 100.

            setBalance(b, firstB + 20); // Ghi 120.
            b.commit();

            // Ghi từ stale value 100+10, đè lên 120.
            setBalance(a, firstA + 10);
            a.commit();

            int finalBalance = freshBalance(ds);
            System.out.printf(
                "[lab] lost-update READ_COMMITTED: "
                    + "firstA=%d, firstB=%d, final=%d%n",
                firstA, firstB, finalBalance);
        }
    }

    private static void atomicIncrement(DataSource ds)
            throws SQLException {

        resetAccount(ds);

        try (Connection a = ds.getConnection();
             Connection b = ds.getConnection()) {

            a.setTransactionIsolation(
                Connection.TRANSACTION_READ_COMMITTED);
            b.setTransactionIsolation(
                Connection.TRANSACTION_READ_COMMITTED);
            a.setAutoCommit(false);
            b.setAutoCommit(false);

            // Cả hai đều có thể đọc 100, nhưng KHÔNG dùng
            // giá trị cũ làm tham số ghi lại.
            balance(a);
            balance(b);

            addToBalance(b, 20);
            b.commit();
            addToBalance(a, 10);
            a.commit();
        }

        System.out.println(
            "[lab] atomic-increment READ_COMMITTED: final="
                + freshBalance(ds));
    }

    private static void resetAccount(DataSource ds)
            throws SQLException {
        try (Connection c = ds.getConnection();
             Statement s = c.createStatement()) {
            s.executeUpdate(
                "UPDATE lab_account SET balance = 100 WHERE id = 1");
        }
    }

    private static void resetItems(DataSource ds)
            throws SQLException {
        try (Connection c = ds.getConnection();
             Statement s = c.createStatement()) {
            s.executeUpdate("DELETE FROM lab_items");
            s.executeUpdate("""
                INSERT INTO lab_items(id, category)
                VALUES (1, 'READY')
                """);
        }
    }

    private static void setBalance(Connection c, int value)
            throws SQLException {
        try (PreparedStatement p = c.prepareStatement("""
                UPDATE lab_account SET balance = ? WHERE id = 1
                """)) {
            p.setInt(1, value);
            p.executeUpdate();
        }
    }

    private static void addToBalance(Connection c, int increment)
            throws SQLException {
        try (PreparedStatement p = c.prepareStatement("""
                UPDATE lab_account
                SET balance = balance + ?
                WHERE id = 1
                """)) {
            p.setInt(1, increment);
            p.executeUpdate();
        }
    }

    private static int freshBalance(DataSource ds)
            throws SQLException {
        try (Connection c = ds.getConnection()) {
            return balance(c);
        }
    }

    private static int balance(Connection c) throws SQLException {
        return number(
            c, "SELECT balance FROM lab_account WHERE id = 1");
    }

    private static int countReady(Connection c)
            throws SQLException {
        return number(c, """
            SELECT COUNT(*) FROM lab_items
            WHERE category = 'READY'
            """);
    }

    private static int number(Connection c, String sql)
            throws SQLException {
        try (Statement s = c.createStatement();
             ResultSet rs = s.executeQuery(sql)) {
            if (!rs.next()) {
                throw new SQLException(
                    "Query did not return a row: " + sql);
            }
            return rs.getInt(1);
        }
    }
}
```

### 6.1. Vì sao mã trên đáp ứng “hai kết nối”?

Mỗi phép đo mở:

```java
try (Connection a = ds.getConnection();
     Connection b = ds.getConnection()) {
    // Lịch điều phối hai transaction.
}
```

Hai connection được lấy cùng lúc và giữ tới cuối phép đo. `verifyConnections(...)` dùng hàm riêng của PostgreSQL `pg_backend_pid()` để xác nhận có **hai backend session khác nhau** trong demo.

Cả A và B đều gọi `setAutoCommit(false)` nên không tự commit ngay sau statement. Chính ứng dụng quyết định khi nào B commit/rollback và khi nào A đọc lại.

Các thao tác thay đổi dữ liệu khởi tạo được thực hiện qua connection reset khác, **trước khi** A/B bắt đầu thí nghiệm tiếp theo. Chúng được auto-commit theo cấu hình pool. Vì vậy:

- Non-repeatable read luôn bắt đầu từ `balance=100`.
- Phantom read luôn bắt đầu từ **một** hàng `READY`.
- Lost update và atomic increment đều bắt đầu từ `balance=100`.

Chương trình không dùng `Thread.sleep`; không phải đợi “đúng thời điểm” để thí nghiệm thành công.

### 6.2. Lệnh chạy

Đảm bảo container PostgreSQL đã sẵn sàng. Trong thư mục chứa `pom.xml`:

```bash
./mvnw spring-boot:run
```

Trên Windows PowerShell:

```powershell
.\mvnw.cmd spring-boot:run
```

Nếu Spring Initializr không tạo Maven Wrapper, cài Maven rồi dùng `mvn spring-boot:run`.

### 6.3. Kết quả in ra dự kiến

Ngoài log Spring/Maven, chương trình in các dòng sau:

```text
[lab] distinct-backends=true
[lab] dirty READ_UNCOMMITTED (PostgreSQL): seen=100, afterRollback=100
[lab] non-repeatable READ_COMMITTED: first=100, second=120
[lab] non-repeatable REPEATABLE_READ: first=100, second=100
[lab] phantom READ_COMMITTED: first=1, second=2
[lab] phantom REPEATABLE_READ: first=1, second=1
[lab] lost-update READ_COMMITTED: firstA=100, firstB=100, final=110
[lab] atomic-increment READ_COMMITTED: final=130
```

Các con số dựa trên **PostgreSQL với JDBC, schema và lịch thao tác của code**, không phải lời khẳng định cho mọi DBMS. Nếu có trigger, dữ liệu khác hoặc thay đổi code/isolation, cần phân tích lại.

### 6.4. Đọc kết quả của từng phép đo

**`distinct-backends=true`:** hai `Connection` đồng thời có backend process ID khác nhau. Điều này loại trừ sai lầm quan sát hai biến Java nhưng thực chất chỉ thao tác trên cùng một connection/transaction.

**Dirty read:** B ghi 200 chưa commit; A yêu cầu `READ_UNCOMMITTED` nhưng PostgreSQL xử lý theo `READ_COMMITTED`. A vẫn thấy 100; sau B rollback, A vẫn thấy 100. Đây là **chứng minh hiện tượng bị ngăn**, không phải “test dirty read không chạy”.

**Non-repeatable, READ_COMMITTED:** A thấy 100 ở lần đầu; B commit 120; A thấy 120 ở lần thứ hai. Hai lần đọc cùng một hàng trong cùng T1 cho hai giá trị khác nhau.

**Non-repeatable, REPEATABLE_READ:** A thấy 100 ở cả hai lần, dù B đã commit 120. A giữ snapshot cũ; để thấy 120 theo snapshot mới, cần kết thúc T1 và mở một transaction mới.

**Phantom, READ_COMMITTED:** lần đầu `COUNT READY=1`; B insert thêm hàng READY và commit; A đếm lại thành 2.

**Phantom, REPEATABLE_READ:** A vẫn đếm 1 vì PostgreSQL dùng snapshot nhất quán cho transaction. Điều này **không mâu thuẫn tiêu chuẩn SQL**: tiêu chuẩn chỉ cho phép DB có bảo đảm mạnh hơn mức tối thiểu.

**Lost update:** A và B cùng đọc 100; B ghi 120 trước; A gửi một giá trị Java tính từ dữ liệu cũ là 110. Kết quả cuối 110, làm mất tác động +20 từ B.

**Atomic increment:** A/B vẫn có thể đọc giá trị cũ, nhưng `UPDATE balance = balance + ?` không dùng bản sao 100 đã lưu tại client. B cộng 20, rồi A cộng 10 trên giá trị hiện hành, kết quả 130.

### 6.5. Vì sao mã không dùng hai threads?

Vì mục tiêu hiện tại là **khả năng tái lập hiện tượng**, không phải benchmark throughput. Hai database transactions có thể cùng tồn tại dù Java gửi lệnh luân phiên trên cùng thread:

```text
Java thread       Connection A / T1      Connection B / T2
    |                    |                       |
    |--- SELECT -------->|                       |
    |                    |                       |
    |--- UPDATE --------------------------------->|
    |--- COMMIT --------------------------------->|
    |                    |                       |
    |--- SELECT -------->|                       |
    v                    v                       v
```

Khi cần kiểm tra blocking, deadlock, lock wait timeout hoặc race thật, nên dùng hai threads với `CountDownLatch` hoặc hai `psql` sessions, kèm timeout/cleanup. Nhưng **không dùng sleep làm điều kiện đồng bộ duy nhất**, vì máy chạy nhanh/chậm khác nhau sẽ cho lịch khác.

## 7. Thiết kế thủ công qua hai cửa sổ psql

Chương trình Java là cách tự động. Khi giảng dạy trực quan, dùng **hai terminal SQL** cũng hữu ích vì người học thấy chính xác câu lệnh nào đang chạy ở từng connection.

Mở terminal A:

```bash
docker exec -it spring-isolation-lab psql -U lab -d isolation_lab
```

Mở terminal B bằng **một lệnh riêng giống hệt**:

```bash
docker exec -it spring-isolation-lab psql -U lab -d isolation_lab
```

Mỗi terminal mở một PostgreSQL session riêng. Có thể chạy:

```sql
SELECT pg_backend_pid();
SHOW transaction_isolation;
```

Để quan sát non-repeatable read theo lịch:

**Terminal A — chạy trước:**

```sql
BEGIN ISOLATION LEVEL READ COMMITTED;
SELECT balance FROM lab_account WHERE id = 1;
```

**Terminal B — chạy sau khi A đã SELECT:**

```sql
BEGIN;
UPDATE lab_account SET balance = 120 WHERE id = 1;
COMMIT;
```

**Terminal A — chạy lại:**

```sql
SELECT balance FROM lab_account WHERE id = 1;
ROLLBACK;
```

Nếu trạng thái khởi đầu của bạn không còn là 100, hãy reset bảng `lab_account` về 100 **ngoài mọi transaction đang mở** trước khi bắt đầu. Để so sánh REPEATABLE READ, reset dữ liệu lần nữa rồi thay `BEGIN ISOLATION LEVEL READ COMMITTED` trong A thành `BEGIN ISOLATION LEVEL REPEATABLE READ`, giữ nguyên lịch.

### Bảng phiếu ghi kết quả

| Test ID | DBMS/version | Isolation A | A đọc lần 1 | Thao tác của B | B kết thúc | A đọc lần 2 | Nhận xét |
| --- | --- | --- | --- | --- | --- | --- | --- |
| NR-1 | PostgreSQL 16 | READ COMMITTED | 100 | UPDATE 120 | COMMIT | 120 | Non-repeatable |
| NR-2 | PostgreSQL 16 | REPEATABLE READ | 100 | UPDATE 120 | COMMIT | 100 | Snapshot ổn định |
| PH-1 | PostgreSQL 16 | READ COMMITTED | COUNT=1 | INSERT READY | COMMIT | COUNT=2 | Phantom |
| PH-2 | PostgreSQL 16 | REPEATABLE READ | COUNT=1 | INSERT READY | COMMIT | COUNT=1 | Phantom bị ngăn |
| DR-1 | PostgreSQL 16 | READ UNCOMMITTED | 100 | UPDATE 200 | Chưa COMMIT → ROLLBACK | 100 | Không thấy dirty |
| LU-1 | PostgreSQL 16 | READ COMMITTED | 100 | B ghi 120, commit | COMMIT | A stale-write 110 | Lost update |

Các hàng là **mẫu dự kiến** cho đúng lịch, không phải kết quả bạn đã chạy trong môi trường của mình. Khi tự làm, ghi thêm transaction IDs/log/SQLSTATE thực tế nếu kết quả khác.

## 8. Tại sao một số thí nghiệm có thể không ra hiện tượng?

### 8.1. B commit quá sớm

Nếu ở phép non-repeatable hoặc phantom bạn để B commit **trước lần đọc đầu tiên của A**, A tại REPEATABLE_READ có thể nhận snapshot đã thấy dữ liệu mới và hai lần đọc đều giống nhau. Đó không phải bằng chứng rằng hiện tượng ở READ_COMMITTED bị ngăn; bạn đã thay đổi lịch.

**Sửa:** luôn có điểm kiểm soát `A.R1 xong` rồi mới cho B commit, sau đó mới `A.R2`.

### 8.2. A bật auto-commit

Nếu A có `autoCommit=true`, mỗi SELECT có thể kết thúc trong transaction riêng. Lúc ấy phép đo “hai lần đọc trong cùng T1” không còn đúng, dù hai SELECT cho hai kết quả khác nhau.

**Sửa:** `setAutoCommit(false)` trước SELECT đầu và chỉ `commit/rollback` A sau SELECT thứ hai.

### 8.3. Dùng cùng một connection

Nếu A và B chỉ là hai biến trỏ tới cùng một connection, SELECT của A có thể nhìn thấy chính thay đổi chưa commit của connection đó. Đó là **read-your-own-writes**, không phải dirty read giữa hai transaction.

**Sửa:** mở hai connection cùng lúc và kiểm chứng session identity; trong PostgreSQL có `pg_backend_pid()`.

### 8.4. DBMS ngăn hiện tượng

Không thể ép PostgreSQL tạo dirty read bằng cách yêu cầu `READ_UNCOMMITTED`: PostgreSQL có behavior giống READ_COMMITTED. Cũng không thể dùng PostgreSQL REPEATABLE_READ để “chứng minh phantom có thể xảy ra ở mọi hệ thống ở mức đó”, vì PostgreSQL chặn phantom.

**Sửa:** phân biệt **hiện tượng được tiêu chuẩn cho phép** với **hiện tượng DBMS cụ thể thực hiện**, và ghi rõ DBMS trong kết luận.

### 8.5. Test đang chạy bên trong transaction của Spring

Nếu một test dùng `@Transactional` trên test method hoặc chạy qua service transactional, một số JDBC/repository calls có thể dùng connection thread-bound từ transaction ngoài. Khi đó code tưởng có nhiều transaction nhưng đang bị transaction manager điều phối theo cách khác.

**Sửa:** với bài lab thủ công, chạy trong entry point **không có transaction** và lấy hai JDBC connections trực tiếp; với bài test Spring annotation, tạo hai Spring beans/proxies và orchestration phù hợp.

### 8.6. Dùng ORM cache thay vì dữ liệu DB

JPA/Hibernate có first-level persistence context; gọi `EntityManager.find(...)` hai lần có thể trả về entity đã quản lý trong cache, dù database ở READ_COMMITTED đã có giá trị mới.

**Sửa:** để quan sát isolation database thuần, dùng JDBC SELECT trực tiếp như bài này. Nếu test ORM, dùng `clear/refresh` đúng lúc và ghi rõ hành vi của persistence context, không gọi hiện tượng cache là tính chất của isolation level.

### 8.7. Tranh chấp khóa khiến phép thử treo

Một lịch sai có thể cho B cố UPDATE một hàng đang bị A giữ row lock hoặc đưa T2 vào tình trạng đợi T1 commit trong khi Java đang chờ T2. Khi đó chương trình có thể block thay vì in kết quả.

**Sửa:** ở các test đọc thuần, dùng SELECT thường **không có FOR UPDATE**; cho writer B commit trước bước đọc lại, không bắt B đợi lock mà A chưa thả. Với khóa và deadlock, xây một bài thí nghiệm khác có timeout và nhiều threads.

### 8.8. Không reset dữ liệu giữa hai phép đo

Nếu phantom test trước đã thêm hàng READY id=2, test sau sẽ có dữ liệu đầu vào khác. Có thể thấy COUNT đầu=2 thay vì 1 và kết luận sai.

**Sửa:** một hàm reset riêng chạy và commit **trước khi mở A/B**, như `resetItems(...)` trong code.

## 9. Quan sát dirty read thật sự trên hệ quản trị khác

Trong PostgreSQL, thí nghiệm dirty read của mục 6 phải in `seen=100`. Nếu mục tiêu đào tạo bắt buộc **nhìn thấy 200 chưa commit**, hãy thực hiện một bài lab riêng trong DBMS có cơ chế `READ UNCOMMITTED` thực tế.

Ví dụ trình tự **minh họa cho MySQL/InnoDB** với bảng `lab_account(id,balance)` đã tồn tại và có một hàng `(1,100)`:

**Session A — reader:**

```sql
SET SESSION TRANSACTION ISOLATION LEVEL READ UNCOMMITTED;
START TRANSACTION;
-- Dừng ở đây và cho B UPDATE trước khi chạy câu dưới.
SELECT balance FROM lab_account WHERE id = 1;
```

**Session B — writer:**

```sql
START TRANSACTION;
UPDATE lab_account SET balance = 200 WHERE id = 1;
-- Chưa COMMIT: để transaction B còn mở.
```

Trở lại session A, chạy SELECT lần nữa trong transaction của A. Trong cấu hình hỗ trợ dirty read, A **có thể** thấy 200 chưa commit.

Sau đó ở session B:

```sql
ROLLBACK;
```

Rồi ở A:

```sql
SELECT balance FROM lab_account WHERE id = 1;
ROLLBACK;
```

A có thể thấy lại 100 sau B rollback. Đây là **demo phụ thuộc MySQL/InnoDB/cấu hình phiên bản**; phải tự kiểm chứng. Trong bài production, READ_UNCOMMITTED không nên được chọn chỉ vì có thể quan sát một hiện tượng “thú vị”.

Quan trọng: nếu dùng application-side caching, SELECT không có cùng ngữ nghĩa; hãy dùng connection/SQL thuần để quan sát transaction isolation.

## 10. Liên hệ với Spring @Transactional(isolation = ...)

Spring khai báo transaction isolation ở method service:

```java
@Service
public class AccountReadService {

    @Transactional(
        propagation = Propagation.REQUIRED,
        isolation = Isolation.REPEATABLE_READ,
        readOnly = true
    )
    public void inspectAccount() {
        // Các câu JDBC/JPA sử dụng đúng DataSource/manager
        // của transaction này sẽ chịu mức cô lập tương ứng.
    }
}
```

Đây là **snippet minh họa**, cần import `org.springframework.stereotype.Service`, `org.springframework.transaction.annotation.Transactional`, `org.springframework.transaction.annotation.Propagation`, `org.springframework.transaction.annotation.Isolation` và triển khai DAO.

### Điều kiện để thuộc tính isolation có tác dụng

1. Lời gọi phải đi qua **Spring transaction proxy** hoặc cơ chế transactional interception tương ứng. `this.inspectAccount()` bên trong cùng bean ở proxy mode có thể bỏ qua interceptor.
2. `PlatformTransactionManager` phải quản lý đúng datasource/connection của câu SQL.
3. Thuộc tính `isolation` của `@Transactional` chủ yếu áp dụng cho **transaction mới được tạo** bởi các propagation như `REQUIRED` khi chưa có transaction và `REQUIRES_NEW`. Nếu method chỉ **tham gia transaction ngoài đang tồn tại**, declaration isolation cục bộ thông thường **không thay isolation transaction ngoài**.
4. Với nhiều manager, có thể chỉ rõ `@Transactional(transactionManager="...")` để không nhầm tài nguyên.
5. DBMS có quyền áp dụng mức bảo đảm thực tế mạnh hơn minimum của tiêu chuẩn. Ví dụ annotation `Isolation.READ_UNCOMMITTED` trên PostgreSQL không làm PostgreSQL bắt đầu trả dirty reads.

### Manual JDBC ở bài lab so với annotation Spring

| Thí nghiệm bằng JDBC thủ công | Ứng dụng Spring declarative |
| --- | --- |
| `dataSource.getConnection()` hai lần | Spring bean/transaction manager quyết định connection phù hợp |
| `a.setTransactionIsolation(...)` trước transaction | `@Transactional(isolation = ...)` khai báo policy |
| `a.setAutoCommit(false)` | Manager bắt đầu transaction |
| `a.commit() / a.rollback()` | Interceptor + manager commit/rollback dựa trên kết quả, rollback rules |
| Điều phối R1 → W2 → C2 → R2 bằng Java | Phải điều phối hai transaction/proxies nếu muốn cùng một lịch |
| Xem trực tiếp trạng thái JDBC | Thường kết hợp JDBC test, DB state, logging và transaction metadata |

**Không pha trộn tùy tiện:** trong method đã được `@Transactional` quản lý, tự gọi `commit()` trên connection lấy qua cơ chế Spring hoặc thay đổi isolation giữa transaction có thể phá vỡ hợp đồng Spring. Bài lab dùng **kết nối thủ công có chủ đích và ngoài transactional method**, không phải mẫu DAO production.

### Nếu muốn thử bằng @Transactional thật

Một kiến trúc kiểm thử có thể gồm:

- `Coordinator` không transactional, điều khiển lịch thử.
- Hai worker Spring beans với các method `@Transactional(propagation = REQUIRES_NEW, isolation = ...)`.
- Các barrier/lock cho phép **hai worker giữ transaction mở đồng thời**, thường phải dùng hai threads vì mỗi method annotated tự commit khi return.
- `CountDownLatch` để bảo đảm A đã SELECT lần một trước khi B UPDATE/COMMIT, rồi A mới SELECT lần hai.

Nhưng chú ý: nếu method A đã return sau SELECT đầu, transaction A có thể **đã kết thúc**, khiến lần SELECT sau không còn thuộc cùng transaction. Để chứng minh non-repeatable read, cả R1 và R2 phải nằm **trong cùng lời gọi transactional A**, trong khi B có cơ hội commit ở giữa. Đây là lý do test hai JDBC connections thủ công đơn luồng dễ tái lập hơn cho người mới.

## 11. Bài nâng cao: write skew và SERIALIZABLE

Đây là bài thí nghiệm **tự làm qua hai terminal PostgreSQL**, không nằm trong stdout của chương trình mục 6. Mục đích là chỉ ra “không có dirty/non-repeatable/phantom read” vẫn **chưa đủ chứng minh lịch trình có thể tuần tự hóa**.

### 11.1. Dữ liệu ban đầu

Dùng một terminal không có transaction đang mở:

```sql
DROP TABLE IF EXISTS lab_doctors;

CREATE TABLE lab_doctors (
    id INTEGER PRIMARY KEY,
    on_call BOOLEAN NOT NULL
);

INSERT INTO lab_doctors(id, on_call)
VALUES (1, TRUE), (2, TRUE);
```

Invariant nghiệp vụ: **phải có ít nhất một bác sĩ trực**.

### 11.2. Hai session ở REPEATABLE READ

**Session A:**

```sql
BEGIN ISOLATION LEVEL REPEATABLE READ;
SELECT COUNT(*) FROM lab_doctors WHERE on_call = TRUE;
-- Kết quả: 2. Giữ transaction A mở.
```

**Session B (trước khi A UPDATE):**

```sql
BEGIN ISOLATION LEVEL REPEATABLE READ;
SELECT COUNT(*) FROM lab_doctors WHERE on_call = TRUE;
-- Kết quả: 2. Giữ transaction B mở.
```

Sau khi **cả hai đều SELECT thấy 2**:

**Session A:**

```sql
UPDATE lab_doctors SET on_call = FALSE WHERE id = 1;
```

**Session B:**

```sql
UPDATE lab_doctors SET on_call = FALSE WHERE id = 2;
```

Hai transaction sửa **hai hàng khác nhau**, nên PostgreSQL REPEATABLE READ có thể cho cả hai hoàn tất:

**Session A:**

```sql
COMMIT;
```

**Session B:**

```sql
COMMIT;
```

Kiểm tra bằng một session ngoài transaction:

```sql
SELECT COUNT(*) AS remaining_on_call
FROM lab_doctors WHERE on_call = TRUE;
```

**Kết quả có thể là 0**, vi phạm invariant “ít nhất một người trực”. Đây là **write skew/serialization anomaly**: mỗi T1/T2 quyết định trên snapshot riêng hợp lệ, nhưng tổng kết quả không tương đương với một lịch thực thi tuần tự tôn trọng điều kiện kiểm tra.

### 11.3. Thử lại bằng SERIALIZABLE

Reset bảng:

```sql
UPDATE lab_doctors SET on_call = TRUE;
```

Mở lại cả hai transaction với:

```sql
BEGIN ISOLATION LEVEL SERIALIZABLE;
```

Chạy **cùng lịch**: cả hai SELECT COUNT thấy 2, mỗi transaction UPDATE một hàng khác nhau, rồi cả hai cố COMMIT.

Ở PostgreSQL, hệ thống có thể phát hiện xung đột serializability và **một transaction sẽ không commit thành công**, thường báo SQLSTATE `40001` với thông báo về serialization failure. Không được quy định cứng A hay B chắc chắn sẽ thất bại; quyết định có thể phụ thuộc lịch thực thi và thời điểm phát hiện xung đột.

Sau khi rollback/cleanup transaction bị lỗi, thông thường vẫn còn **ít nhất một người trực** theo các thay đổi đã commit. Ứng dụng phải có chiến lược **retry toàn bộ transaction** bị lỗi serialization, bao gồm bước đọc kiểm tra invariant, không chỉ retry câu UPDATE cuối.

### 11.4. Giới hạn của ví dụ

- Đây là bài minh họa invariant với **hai rows khác nhau**; không phải cứ dùng `REPEATABLE_READ` thì sẽ mất dữ liệu trong mọi bài toán.
- Nếu có constraint/lock hoặc một thiết kế khác bảo vệ invariant, kết quả có thể thay đổi.
- Serializable trong PostgreSQL **không bảo đảm mọi transaction commit**; nó bảo đảm các transaction **commit thành công** có kết quả tương đương một thứ tự tuần tự, và có thể buộc abort/retry những transaction khác.
- Khi chuyển sang MySQL hoặc SQL Server, cách xử lý snapshot/locking/serializable khác và phải kiểm tra tài liệu vendor.

## 12. Lost update: cách thử và cách sửa cho đúng

Bài lab ghi đè giá trị bằng cách lưu bản cũ vào Java:

```java
int aSeen = balance(a);  // 100
int bSeen = balance(b);  // 100

setBalance(b, bSeen + 20); // UPDATE balance = 120
b.commit();

setBalance(a, aSeen + 10); // UPDATE balance = 110
a.commit();
```

Đây là **trích đoạn từ chương trình hoàn chỉnh**, không phải file chạy độc lập. Điểm nguy hiểm không nằm ở phép cộng số học mà ở việc **viết đè bằng giá trị cũ**.

### 12.1. Atomic update

```sql
UPDATE lab_account
SET balance = balance + 10
WHERE id = 1;
```

Tính tăng ở phía database, theo trạng thái/khóa hiện hành khi UPDATE thực thi. Trong lịch demo, B cộng 20 rồi commit, A cộng 10 sau đó → 130, không phải 110.

Đừng nhầm rằng một SQL UPDATE nguyên tử giải quyết **mọi** điều kiện nghiệp vụ; nếu cần “không cho số dư âm”, có thể phải thêm `WHERE balance >= :amount` và kiểm tra số hàng được cập nhật hoặc dùng constraint.

### 12.2. Optimistic locking

Thêm cột `version`, sau đó ghi:

```sql
UPDATE lab_account
SET balance = ?, version = version + 1
WHERE id = ? AND version = ?;
```

Nếu A đã đọc version cũ và B vừa commit tăng version, UPDATE của A sẽ ảnh hưởng **0 hàng**. Ứng dụng có thể phát hiện conflict và retry **toàn bộ logic nghiệp vụ**, thay vì âm thầm ghi đè.

Trong JPA, có thể dùng `@Version` khi mapping entity phù hợp; vẫn cần xử lý `OptimisticLockException` và quyết định retry hay báo lỗi.

### 12.3. Pessimistic locking và transaction isolation

`SELECT ... FOR UPDATE` có thể khóa hàng để tránh hai transaction đồng thời cùng sửa từ giá trị cũ, nhưng kéo theo lock wait và nguy cơ deadlock nếu truy cập nhiều hàng không theo cùng thứ tự.

Tăng isolation lên `SERIALIZABLE` có thể ngăn một số lịch không hợp lệ bằng blocking hoặc abort, tùy database. Không nên thay thế thuật toán concurrency control bằng “đổi isolation lên cao nhất” mà không đo hiệu năng và xử lý retry.

## 13. Một số câu hỏi chẩn đoán trước khi kết luận

### Tại sao PostgreSQL READ_UNCOMMITTED vẫn in 100?

Vì PostgreSQL xử lý mức yêu cầu đó tương đương READ_COMMITTED: không cho đọc uncommitted data của transaction khác. Kết quả đúng không phải “phòng lab lỗi”, mà là **đặc điểm triển khai của DBMS**.

### Tại sao REPEATABLE_READ vẫn thấy thay đổi do chính T1 thực hiện?

Vì snapshot nhất quán không cấm transaction nhìn thấy **thay đổi của chính nó**. Thí nghiệm non-repeatable ở đây cố ý cho **B** thay đổi, còn A chỉ SELECT; nếu A tự UPDATE giữa R1/R2, bạn đang đo read-your-own-writes thay vì hiện tượng từ transaction khác.

### Tại sao hai `Connection` phải mở cùng lúc?

Để giữ transaction A mở khi B làm việc. Nếu đóng A rồi mở lại trước lần SELECT thứ hai, bạn không còn một transaction A xuyên suốt lịch. Với connection pool, hai đối tượng đang mở cùng lúc cũng giúp tránh nhầm lẫn về việc pool tái sử dụng cùng physical connection theo thời gian.

### Có bắt buộc transaction B kết thúc trước lần SELECT thứ hai?

Với thí nghiệm non-repeatable và phantom ở READ_COMMITTED, cần B **COMMIT** để A có thể nhìn thay đổi committed. Nếu B chưa commit, bạn vô tình chuyển bài toán sang dirty read hoặc lock visibility. Đó là một thí nghiệm khác.

### Khi chạy lần đầu chương trình hoạt động nhưng lần hai báo duplicate key?

Có thể do bạn tự chỉnh mã và bỏ reset, hoặc kết nối sang database có dữ liệu từ trước. Demo `initialize()` có `DROP TABLE IF EXISTS lab_*` và tạo lại dữ liệu; kiểm tra chính xác URL JDBC và đảm bảo DB chỉ dành cho thí nghiệm.

### Tại sao đổi isolation của A sau SELECT đầu không cho kết quả dự kiến?

Thay isolation **giữa một transaction đang hoạt động** thường bị hạn chế hoặc không làm transaction cũ có snapshot khác. Trong lab, `setTransactionIsolation(...)` được gọi trước `setAutoCommit(false)` và trước SELECT đầu tiên. Muốn thí nghiệm mức mới, **kết thúc transaction hiện tại, reset dữ liệu, bắt đầu transaction mới**.

### Tại sao một phép UPDATE có thể bị chờ?

Vì cơ chế isolation cùng lock manager thực hiện kiểm soát tranh chấp. Một câu SELECT thường ở PostgreSQL MVCC không khóa row như `FOR UPDATE`; nhưng hai UPDATE cùng hàng, foreign keys hoặc constraint có thể cần khóa. Thí nghiệm đã chọn lịch tránh waiting không cần thiết để cô lập biến quan sát.

## 14. Bộ tiêu chí kiểm thử đạt yêu cầu

Một báo cáo lab hoàn chỉnh nên có:

- [ ] Nêu chính xác **DBMS/version** (PostgreSQL 16 cho ví dụ chính).
- [ ] Chứng minh A/B là **hai connections khác nhau**, ví dụ `pg_backend_pid()`.
- [ ] Xác nhận `autoCommit=false` cho A/B và mức isolation được thiết lập trước transaction.
- [ ] Ghi **dữ liệu ban đầu S0** và reset trước mỗi thí nghiệm.
- [ ] Ghi rõ thứ tự statement của A và B, đặc biệt **R1 trước B COMMIT, R2 sau B COMMIT**.
- [ ] Đảm bảo R1/R2 chạy trên **cùng connection/transaction A**.
- [ ] Kết thúc A/B bằng commit hoặc rollback; không để connection/transaction bị bỏ mở.
- [ ] Có expected output cụ thể, đối chiếu với con số thật.
- [ ] Phân biệt anomaly **được phép** bởi tiêu chuẩn và anomaly **được triển khai** bởi DBMS.
- [ ] Với lost update, kiểm tra kết quả cuối so với giá trị đúng dự kiến (110 vs 130), không chỉ in số.
- [ ] Với SERIALIZABLE, xử lý SQLSTATE `40001` và retry toàn bộ business transaction nếu cần.
- [ ] Khi chuyển sang Spring `@Transactional`, xác định proxy, transaction manager, propagation và thời điểm bắt đầu transaction mới.
- [ ] Không dùng `Thread.sleep` hay ORM cache làm bằng chứng duy nhất về mức cô lập.

### Mẫu báo cáo thí nghiệm

```text
Tên: Phantom read
DBMS: PostgreSQL 16
Isolation A: READ COMMITTED
Isolation B: READ COMMITTED
Initial data: READY count = 1
A.R1: SELECT COUNT(*) ... = 1
B.W2: INSERT READY id=2
B.C2: COMMIT thành công
A.R2: SELECT COUNT(*) ... = 2
A.X1: ROLLBACK (chỉ kết thúc transaction đọc)
Kết luận: PostgreSQL READ COMMITTED cho phantom theo lịch này.
So sánh: cùng lịch với REPEATABLE READ cho 1 -> 1.
```

Nếu kết quả khác, nộp **lịch SQL, trạng thái auto-commit, isolation thực tế và DBMS** trước khi kết luận code/framework sai.

## 15. Bài tập tự luyện

**Bài 1.** A mở transaction READ_COMMITTED, đọc balance=100. B UPDATE balance=150 nhưng **chưa commit**. A đọc lần hai. Có đủ điều kiện gọi là non-repeatable read chưa?

**Đáp án:** Chưa. Non-repeatable read trong định nghĩa ở đây đòi thay đổi của B **được commit trước lần đọc lại**. Nếu A thấy 150 khi B chưa commit, đó là dirty read; PostgreSQL READ_COMMITTED không cho việc đó.

**Bài 2.** A mở REPEATABLE_READ, nhưng B commit update **trước khi A thực hiện SELECT đầu tiên**. A đọc được 150 trong cả hai SELECT. Có chứng minh được repeatable read ngăn non-repeatable không?

**Đáp án:** Không theo lịch kiểm chứng mong muốn. Snapshot của A được xác định sau B commit, nên cả hai thấy 150. Cần làm A.R1 trước B.C2 rồi mới A.R2 để so sánh đúng.

**Bài 3.** Vì sao PostgreSQL `REPEATABLE_READ` trong demo không cho phantom, dù một số bảng trong sách SQL ghi phantom “có thể”?

**Đáp án:** Bảng tiêu chuẩn mô tả mức bảo đảm tối thiểu; PostgreSQL hiện thực REPEATABLE_READ theo snapshot nhất quán mạnh hơn về phantom read.

**Bài 4.** Hai Java threads có thực sự bắt buộc để dựng các lịch dirty/non-repeatable/phantom không?

**Đáp án:** Không, nếu hai JDBC connections được mở đồng thời và một thread điều phối statement/commit theo thứ tự. Cần threads hoặc hai terminal khi muốn đo waiting/race thật hoặc khi code transaction ở mỗi worker không thể tạm dừng bằng orchestrator đơn luồng.

**Bài 5.** Trong lost update, A đọc 100, B tăng 20 và commit, A gửi `UPDATE balance=110`. Vì sao final=110 không có nghĩa DB đã “cộng sai”?

**Đáp án:** DB thực hiện đúng câu UPDATE bằng **giá trị hằng 110** mà ứng dụng đưa ra. Lỗi nằm ở read–modify–write từ dữ liệu stale của client, không phải phép cộng của database.

**Bài 6.** Một Spring service có `@Transactional(isolation = Isolation.SERIALIZABLE, propagation = REQUIRED)` nhưng đang tham gia transaction của caller đã mở ở READ_COMMITTED. Có chắc method tự nâng transaction ngoài lên SERIALIZABLE không?

**Đáp án:** Không. Với Spring transaction management thông thường, isolation annotation của method tham gia existing transaction không tự thay đổi physical transaction đã mở. Cần xem propagation, transaction manager và chính sách validate existing transaction.

**Bài 7.** Hai bác sĩ ở REPEATABLE_READ đều thấy có 2 người trực, rồi mỗi người nghỉ ở một hàng khác nhau; cả hai commit. Đây có phải non-repeatable read không?

**Đáp án:** Không. Mỗi người có thể đọc cùng một snapshot ổn định, nhưng tổng kết quả vi phạm invariant. Đây là write skew/serialization anomaly, minh họa vì sao REPEATABLE_READ không tương đương SERIALIZABLE ở PostgreSQL.

**Bài 8.** Một integration test `@Transactional` gọi method A SELECT, rồi method B UPDATE, rồi A SELECT lại. Vì sao khó biết có hai transaction không?

**Đáp án:** Các lời gọi có thể tham gia **cùng transaction do test/caller đã mở**, nhất là nếu dùng cùng transaction manager và propagation REQUIRED. Cần thiết kế hai physical transaction, hai connections và lịch commit rõ ràng.

## 16. Kết luận

**Thiết kế thí nghiệm isolation tốt là thiết kế lịch hai connection**, không chỉ thay một giá trị annotation:

1. Reset dữ liệu đã commit.
2. Bắt đầu T1/T2 trên hai physical connections khác nhau.
3. Cố định isolation level trước khi bắt đầu.
4. Cho A đọc lần đầu, B ghi và commit/rollback đúng thời điểm, A đọc lại trên **cùng T1**.
5. Kết thúc các transaction và so sánh kết quả theo **DBMS thực tế**.
6. Với bài toán ghi, đo cả **kết quả cuối và invariant**, không chỉ các giá trị SELECT.

Ở PostgreSQL: `READ_COMMITTED` có thể cho non-repeatable/phantom; `REPEATABLE_READ` dùng snapshot ổn định và ngăn cả hai trong thí nghiệm này; `READ_UNCOMMITTED` không tạo dirty reads; `SERIALIZABLE` có thể trả lỗi 40001 để ngăn lịch không thể tuần tự hóa. Khi chuyển kiến thức vào Spring `@Transactional`, cần kiểm tra transaction được **mở mới**, proxy áp dụng policy và repository thực sự dùng đúng tài nguyên được quản lý.

### Tài liệu chính thức

- PostgreSQL — Transaction Isolation: https://www.postgresql.org/docs/16/transaction-iso.html
- PostgreSQL — Explicit Locking: https://www.postgresql.org/docs/16/explicit-locking.html
- PostgreSQL — Handling Serialization Failures: https://www.postgresql.org/docs/16/mvcc-serialization-failure-handling.html
- Spring Framework — `@Transactional` settings, isolation và propagation: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html
- Spring Framework — Transaction Propagation: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html
- Spring Javadoc — `Isolation` enum: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/transaction/annotation/Isolation.html
- Java SE JDBC — `Connection.setTransactionIsolation(int)`: https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/Connection.html
