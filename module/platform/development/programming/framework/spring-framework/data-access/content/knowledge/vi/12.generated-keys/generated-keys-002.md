# Đọc số hàng bị ảnh hưởng và kiểm tra kỳ vọng nghiệp vụ

> **Ngữ cảnh:** Spring Framework – Data Access, nhóm *Cập nhật và khóa sinh*. Mục tiêu là biết một lệnh ghi đã tác động tới bao nhiêu hàng, đối chiếu con số đó với quy tắc nghiệp vụ, rồi quyết định tiếp tục, trả về kết quả hay rollback.

## 1. Vì sao số hàng bị ảnh hưởng là một tín hiệu nghiệp vụ?

Khi thực thi `UPDATE, `DELETE hoặc `INSERT, tầng JDBC có thể trả về **update count** (*số hàng bị ảnh hưởng*). Với Spring JDBC, `JdbcTemplate.update(...) trả về `int, thường là số hàng mà cơ sở dữ liệu/JDBC driver báo đã chịu tác động của câu lệnh. Nó không đơn thuần là “SQL chạy không lỗi”.

Giả sử ứng dụng chỉ được chuyển **một** đơn hàng từ `PENDING sang `PAID:

```sql
UPDATE orders
SET status = 'PAID'
WHERE id = ? AND status = 'PENDING';
```

- **`1 hàng:** chuyển trạng thái hợp lệ của một đơn hàng đã được thực hiện; vẫn cần transaction commit thành công để kết luận thay đổi đã bền vững.
- **`0 hàng:** không có hàng nào đáp ứng toàn bộ điều kiện `WHERE. Đơn có thể không tồn tại, đã được thanh toán, đã hủy hoặc vừa bị request khác thay đổi; **không thể kết luận riêng từ count rằng “không tìm thấy ID”**.
- **`>1 hàng:** trái kỳ vọng “một đơn”. Nếu câu SQL có thể tác động nhiều hàng, đây là dấu hiệu điều kiện chưa đủ chặt hoặc quy tắc nghiệp vụ/schema có vấn đề. Phải xử lý trước khi commit.

**Cần phân biệt:**
- **Row count ≠ số bản ghi đọc được** từ `SELECT COUNT(*). Một giá trị đếm trước thao tác có thể lỗi thời khi có request đồng thời.
- **Row count ≠ số hàng có giá trị thực sự thay đổi trong mọi DB.** Một số hệ quản trị/driver báo số hàng *khớp điều kiện*, số khác báo số hàng *thực sự thay đổi*, nhất là `UPDATE gán lại đúng giá trị cũ. Hãy kiểm chứng với đúng DB và cấu hình driver đang chạy.
- **Row count ≠ chứng nhận toàn bộ nghiệp vụ thành công.** Constraint, trigger, transaction rollback, các bước liên quan và trạng thái của hệ thống ngoài DB vẫn phải xét riêng.
- **Row count ≠ khóa sinh (generated key).** `int từ `update cho biết số hàng; muốn lấy ID được sinh khi `INSERT thì sử dụng cơ chế generated keys/`KeyHolder tương ứng.

## 2. Xác định kỳ vọng trước khi gọi SQL

Đừng viết điều kiện `if (rows > 0) theo thói quen. Hãy xác định rõ số hàng **được phép** và phản ứng tương ứng từ use case.

| Thao tác | Kỳ vọng hợp lý | Phản ứng |
| --- | --- | --- |
| Sửa một thực thể theo khóa chính và điều kiện trạng thái | `rows == 1 | `0: không thỏa điều kiện; `>1: lỗi bất biến, không commit |
| Trừ tồn kho/chuyển tiền bằng `WHERE available >= amount | `rows == 1 | `0: thiếu điều kiện thực hiện hoặc dữ liệu đã đổi |
| Cập nhật có kiểm tra `version (optimistic concurrency) | `rows == 1 | `0: không tồn tại hoặc phiên bản đã cũ |
| Xóa một bản ghi có yêu cầu *phải tồn tại* | `rows == 1 | `0: báo không tìm thấy hoặc xung đột |
| Xóa theo hướng *idempotent* (“sau lệnh này không còn bản ghi”) | `rows == 0 **hoặc** `1 | `0 có thể là kết quả hợp lệ, tùy hợp đồng API |
| Cập nhật nhiều hàng theo tiêu chí | `0..N hoặc một số lượng dự kiến cụ thể | Kiểm tra giới hạn, sự hợp lệ của tập dữ liệu và tác động được phê duyệt |
| `INSERT một hàng thông thường | Thường `1 | Xử lý lỗi ràng buộc/duplicate; với `UPSERT/`ON CONFLICT cần quy ước riêng theo DB |

Một thiết kế dễ kiểm tra là nêu **invariant** ngay trong service: “Mỗi lần xác nhận đơn hàng phải cập nhật chính xác một hàng ở trạng thái `PENDING”. `rows == 0 là một **kết quả nghiệp vụ cần diễn giải**, không mặc định là lỗi hạ tầng. Ngược lại, `rows > 1 khi dùng khóa duy nhất là dấu hiệu nguy hiểm cần điều tra.

Đừng đưa `tenant_id, `status, `version, quyền sở hữu hay điều kiện nghiệp vụ ra khỏi `WHERE rồi chỉ dựa vào việc đã `SELECT trước đó. Cập nhật có điều kiện giúp DB kiểm tra điều kiện tại thời điểm ghi, giảm lỗi tranh chấp.

## 3. Đọc count bằng Spring JDBC

`JdbcTemplate.update(String sql, Object... args) thực thi câu lệnh ghi có tham số và trả lại số hàng bị ảnh hưởng. Các dấu `? được bind an toàn thông qua JDBC; không ghép input người dùng trực tiếp vào SQL.

Ví dụ tích hợp trong một ứng dụng Spring đã có `JdbcTemplate, bảng `orders và transaction manager (đoạn này **không phải chương trình Java độc lập**):

```java
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderPaymentService {
    private final JdbcTemplate jdbc;

    public OrderPaymentService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public void markPaid(long tenantId, long orderId) {
        int rows = jdbc.update(
            "UPDATE orders SET status = ? " +
            "WHERE id = ? AND tenant_id = ? AND status = ?",
            "PAID", orderId, tenantId, "PENDING"
        );

        if (rows != 1) {
            throw new IllegalStateException(
                "Expected one PENDING order, affected rows = " + rows
            );
        }
    }
}
```

Điểm cần hiểu:
1. `WHERE id = ? AND tenant_id = ? AND status = ? giới hạn đúng thực thể, đúng phạm vi thuê bao, đúng trạng thái ban đầu. Giá trị count xác nhận **toàn bộ** điều kiện đó có khớp tại thời điểm cập nhật hay không.
2. `@Transactional bao bọc thao tác. `IllegalStateException là unchecked exception; trong cấu hình rollback mặc định của Spring, exception thoát ra khỏi phương thức transaction sẽ khiến transaction rollback. Nếu trước đó có thêm bước ghi DB trong cùng transaction, bước đó cũng được rollback.
3. Nếu chỉ có `0 hàng, ứng dụng có thể lựa chọn truy vấn bổ sung (trong cùng ranh giới nhất quán phù hợp) để phân biệt “không tồn tại” với “đã ở trạng thái khác”, rồi trả mã lỗi nghiệp vụ thích hợp. Đừng tự suy luận nguyên nhân chỉ từ count.
4. Nếu code gọi phương thức `@Transactional trực tiếp từ một phương thức khác **trên cùng instance** trong cấu hình Spring proxy thông thường, transaction interceptor có thể không chạy. Đảm bảo lời gọi đi qua Spring proxy hoặc dùng `TransactionTemplate khi phù hợp.
5. Nếu bắt và nuốt exception **bên trong** phương thức `@Transactional, transaction có thể commit. Hãy để exception thoát ra hoặc chủ động đánh dấu rollback khi nghiệp vụ thực sự thất bại.

`NamedParameterJdbcTemplate.update(...) cũng trả `int, chỉ khác cách đặt tên tham số (ví dụ `:orderId thay cho `?). Dù dùng biến thể nào, quy tắc so sánh count vẫn nằm ở tầng nghiệp vụ.

## 4. Ví dụ chạy được: một cập nhật thành công, hai cập nhật bị từ chối

Ví dụ dùng **Java 17+, Spring JDBC 6.2.x và H2 2.x**, không cần Spring Boot. Mỗi thao tác nằm trong `TransactionTemplate; nếu count không đúng `1, `IllegalStateException làm transaction rollback. Dùng các phiên bản phụ thuộc dưới đây để tái lập ví dụ.

Cấu trúc:

```text
affected-rows-demo/
├── pom.xml
└── src/main/java/demo/AffectedRowsDemo.java
```

`pom.xml:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>affected-rows-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-jdbc</artifactId>
            <version>6.2.19</version>
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
                <version>3.14.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.6.3</version>
            </plugin>
        </plugins>
    </build>
</project>
```

`src/main/java/demo/AffectedRowsDemo.java:

```java
package demo;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;

public final class AffectedRowsDemo {
    private static final String DEBIT_SQL =
        "UPDATE account " +
        "SET balance = balance - ?, lock_version = lock_version + 1 " +
        "WHERE id = ? AND balance >= ? AND lock_version = ?";

    public static void main(String[] args) {
        var dataSource = new DriverManagerDataSource(
            "jdbc:h2:mem:counts;DB_CLOSE_DELAY=-1", "sa", ""
        );
        var jdbc = new JdbcTemplate(dataSource);
        var tx = new TransactionTemplate(
            new DataSourceTransactionManager(dataSource)
        );

        jdbc.execute(
            "CREATE TABLE account (" +
            "id BIGINT PRIMARY KEY, " +
            "balance INT NOT NULL, " +
            "lock_version INT NOT NULL)"
        );
        jdbc.update(
            "INSERT INTO account (id, balance, lock_version) VALUES (?, ?, ?)",
            7L, 100, 0
        );

        Integer accepted = tx.execute(status -> {
            int rows = jdbc.update(DEBIT_SQL, 30, 7L, 30, 0);
            requireOne(rows);
            return rows;
        });
        System.out.println("acceptedRows=" + accepted);

        try {
            tx.execute(status -> {
                int rows = jdbc.update(DEBIT_SQL, 80, 7L, 80, 1);
                requireOne(rows);
                return rows;
            });
        } catch (IllegalStateException ex) {
            System.out.println("insufficientFunds=REJECTED");
        }

        try {
            tx.execute(status -> {
                int rows = jdbc.update(DEBIT_SQL, 10, 7L, 10, 0);
                requireOne(rows);
                return rows;
            });
        } catch (IllegalStateException ex) {
            System.out.println("staleVersion=REJECTED");
        }

        Integer balance = jdbc.queryForObject(
            "SELECT balance FROM account WHERE id = ?",
            Integer.class, 7L
        );
        Integer version = jdbc.queryForObject(
            "SELECT lock_version FROM account WHERE id = ?",
            Integer.class, 7L
        );
        System.out.println(
            "balance=" + balance + ", lockVersion=" + version
        );
    }

    private static void requireOne(int affectedRows) {
        if (affectedRows != 1) {
            throw new IllegalStateException(
                "Expected exactly one row; actual=" + affectedRows
            );
        }
    }
}
```

Trong thư mục `affected-rows-demo, chạy:

```bash
mvn -q compile exec:java -Dexec.mainClass=demo.AffectedRowsDemo
```

Các dòng `System.out.println của chương trình (không tính thông điệp riêng của công cụ build nếu có):

```text
acceptedRows=1
insufficientFunds=REJECTED
staleVersion=REJECTED
balance=70, lockVersion=1
```

Giải thích từng lần:
- Lần đầu trừ `30 từ số dư `100, điều kiện `balance >= 30 và `lock_version = 0 đúng nên count = `1; sau commit số dư `70, version `1.
- Lần hai muốn trừ `80, số dư chỉ `70, nên count = `0; exception dẫn đến rollback.
- Lần ba trừ `10 nhưng gửi version cũ `0 thay vì `1, nên count = `0; không làm thay đổi số dư/version.
- Sau cùng vẫn có `balance = 70, `lockVersion = 1.

Ở ví dụ này, điều kiện số dư và version nằm trong **cùng** câu `UPDATE. Nếu làm `SELECT balance rồi cập nhật không kèm điều kiện, hai request đồng thời có thể cùng đọc số dư cũ và đưa ra quyết định sai. Mẫu `UPDATE ... WHERE balance >= ? AND lock_version = ? cung cấp một kiểm tra nguyên tử ở bước ghi.

## 5. Phân biệt `0 hàng: không tìm thấy, điều kiện không thỏa hay idempotent?

Không được máy móc biến mọi `0 thành HTTP `404. Ví dụ `UPDATE ... WHERE id = 42 AND status = 'PENDING' trả `0 trong ít nhất ba tình huống: không có ID `42, ID có thật nhưng trạng thái khác `PENDING, hoặc có thay đổi đồng thời trước khi câu lệnh thực thi.

Một quy trình hợp lý:
1. Định nghĩa hợp đồng nghiệp vụ trước: nếu lặp lại yêu cầu “đánh dấu đã thanh toán”, có muốn trả **thành công idempotent** hay **xung đột trạng thái**?
2. Chạy lệnh ghi có `WHERE đủ điều kiện. Khi count = `1, hoàn thành trong transaction.
3. Nếu count = `0, chỉ đọc bổ sung khi thực sự cần giải thích nguyên nhân cho caller. Truy vấn lại cũng có thể gặp dữ liệu thay đổi đồng thời; nó giúp chẩn đoán, không thay thế kiểm tra nguyên tử ở câu `UPDATE.
4. Nếu idempotency là yêu cầu mạnh, dùng request ID/khóa duy nhất hoặc trạng thái được thiết kế cho retry; **chỉ thấy `rows = 0 không chứng minh request cũ đã xử lý thành công**.

Ví dụ:
- `DELETE FROM saved_filters WHERE user_id = ? AND filter_id = ?: nếu hợp đồng là “bảo đảm filter vắng mặt”, count `0 thường chấp nhận được.
- `UPDATE orders SET status='SHIPPED' WHERE id=? AND status='PAID': count `0 có thể là request không hợp lệ về trạng thái, cần phân biệt với không tồn tại và ghi nhận rõ.
- `UPDATE inventory SET available=available-? WHERE sku=? AND available>=?: count `0 nghĩa là điều kiện trừ kho không được thỏa; không nên giả định chỉ có nguyên nhân hết hàng nếu `sku cũng có thể không tồn tại.

## 6. Kiểm soát cập nhật đồng thời và optimistic locking

Một mẫu thường gặp:

```sql
UPDATE documents
SET title = ?, lock_version = lock_version + 1
WHERE id = ? AND lock_version = ?;
```

- Client đọc document ở version `5, gửi version `5 lúc sửa.
- Nếu DB vẫn giữ version `5, count `1 và version tăng thành `6.
- Nếu request khác đã cập nhật lên `6, count `0; service phải báo conflict và cho caller tải lại dữ liệu.
- Nếu ID không tồn tại, count cũng `0; xử lý phân biệt khi cần.

Đây là **optimistic concurrency**: bản ghi không cần giữ lock dài hạn từ lúc đọc tới lúc người dùng lưu, nhưng điều kiện version phải được kiểm tra trong chính SQL ghi. Với JPA/Hibernate, `@Version thường quản lý optimistic locking cho cập nhật entity theo cơ chế ORM; **bulk JPQL update** cần được đánh giá riêng vì không tự áp dụng toàn bộ cơ chế entity-level đó.

Count còn giúp phát hiện thiếu ràng buộc duy nhất: nếu một hành động được thiết kế cho một thực thể mà count `2, không nên coi “ít nhất một bản ghi đã sửa” là thành công. Cần rollback, sửa `WHERE và cân nhắc unique constraint/index ở schema.

## 7. Batch update: không cộng tổng một cách mù quáng

Spring JDBC hỗ trợ `JdbcTemplate.batchUpdate(...). Với overload nhận `List<Object[]>, nó trả `int[] chứa count tương ứng từng lệnh trong batch. Overload có chia batch theo `batchSize có thể trả `int[][]. Kết quả do JDBC driver quyết định:

- Số `>= 0: count đã biết, trong đó `0 nghĩa là không có hàng bị ảnh hưởng.
- `Statement.SUCCESS_NO_INFO (`-2): lệnh được báo thành công nhưng **không biết** số hàng.
- `Statement.EXECUTE_FAILED (`-3): ký hiệu thất bại trong mảng update counts khi driver tiếp tục sau lỗi; lỗi batch cũng có thể làm JDBC ném `BatchUpdateException, được Spring chuyển thành exception truy cập dữ liệu.

Đoạn mã sau minh họa trong một service đã có `jdbc (không phải chương trình độc lập):

```java
import java.sql.Statement;
import java.util.ArrayList;
import java.util.List;

List<Object[]> params = new ArrayList<>();
params.add(new Object[] {"DONE", 11L, "PENDING"});
params.add(new Object[] {"DONE", 12L, "PENDING"});

int[] counts = jdbc.batchUpdate(
    "UPDATE jobs SET state = ? WHERE id = ? AND state = ?",
    params
);

for (int i = 0; i < counts.length; i++) {
    int count = counts[i];
    if (count == Statement.SUCCESS_NO_INFO) {
        throw new IllegalStateException(
            "Cannot prove expected count for batch item " + i
        );
    }
    if (count == Statement.EXECUTE_FAILED || count != 1) {
        throw new IllegalStateException(
            "Unexpected affected rows at batch item " + i + ": " + count
        );
    }
}
```

Nếu nghiệp vụ đòi **mỗi item đúng một hàng**, `-2 là **không đủ bằng chứng**, dù driver báo thực thi thành công. Có thể chọn từng `update riêng, dùng truy vấn xác minh theo khóa phù hợp hoặc cơ chế DB trả về kết quả chính xác. Không cộng `-2 như số âm để ra “tổng số hàng cập nhật”, không coi `counts.length là số hàng thành công. Bọc cả batch và kiểm tra count trong transaction nếu cần all-or-nothing; khả năng xử lý phần tử sau lỗi khác nhau theo driver, nên rollback toàn bộ khi không thỏa invariant.

## 8. Spring Data JPA: lấy count từ bulk update

Với repository dùng Spring Data JPA, có thể trả về `int từ phương thức `@Modifying @Query. Ví dụ **minh họa để tích hợp** vào ứng dụng đã có entity `Booking, enum `BookingState và `JpaRepository:

```java
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface BookingRepository extends JpaRepository<Booking, Long> {
    @Modifying
    @Query("""
           update Booking b
              set b.state = :next
            where b.id = :id
              and b.state = :expected
           """)
    int moveState(
        @Param("id") Long id,
        @Param("expected") BookingState expected,
        @Param("next") BookingState next
    );
}
```

Service gọi `moveState trong transaction và áp dụng `rows == 1 giống như với JDBC. Khác biệt cần biết:

- Các **query method được khai báo** trong Spring Data JPA không tự có cấu hình transaction mặc định như mọi method CRUD kế thừa; đặt `@Transactional ở service bao trùm thao tác (hoặc tại query method phù hợp).
- Bulk JPQL update/delete đi trực tiếp xuống DB, không đồng nhất với việc gọi `save(entity) theo vòng đời của từng entity. Nó có thể bỏ qua lifecycle callback, dirty checking theo entity và xử lý `@Version tự động. Nếu cần điều kiện optimistic locking, thể hiện rõ `WHERE version = :expectedVersion và cập nhật version theo chính sách của ứng dụng.
- Persistence context có thể còn entity cũ sau bulk update. `@Modifying(flushAutomatically = true, clearAutomatically = true) có thể dùng khi cần flush trước và clear sau, nhưng **clear sẽ detach các entity đang managed**; phải tính đến thay đổi chưa flush và những đối tượng code tiếp tục sử dụng.
- `save(...) trả entity, không trả row count; SQL do ORM phát sinh có thể được flush muộn. Đừng suy ra số hàng bị ghi từ giá trị trả về của `save.

## 9. Transaction và xử lý lỗi nghiệp vụ

Quy tắc an toàn là **ghi → đọc count → kiểm tra invariant → quyết định commit/rollback trong cùng transaction**.

- `rows == expected: thực hiện các bước còn lại rồi commit; commit vẫn có thể thất bại bởi ràng buộc, deadlock, kết nối hoặc sự cố DB.
- `rows == 0 không chấp nhận theo hợp đồng: ném exception nghiệp vụ phù hợp (thường unchecked) để rollback; sau đó map ra lỗi API/domain ở ranh giới phù hợp.
- `rows > expected: rollback và ghi log có cấu trúc gồm mã thao tác, tiêu chí ID/tenant an toàn, `expected, `actual. Tránh ghi SQL đầy đủ kèm dữ liệu nhạy cảm.
- Với checked exception, cấu hình `rollbackFor nếu quy tắc rollback mặc định không áp dụng; kiểm tra cấu hình Spring đang dùng.
- Hệ thống ngoài DB (gửi email, message, HTTP) không tự rollback cùng transaction DB. Để bảo đảm không phát sự kiện sai khi count không đạt, cân nhắc transactional outbox/after-commit phù hợp.

**Không làm:**

```java
// Sai khi nghiệp vụ bắt buộc chính xác một hàng:
jdbc.update("UPDATE orders SET status = ? WHERE id = ?", "PAID", orderId);
return true; // Bỏ qua count.

// Sai do 0 và nhiều hơn 1 đều có thể là bất thường:
return jdbc.update(sql, args) > 0;

// Sai nếu check-then-act được thực hiện không nguyên tử:
if (jdbc.queryForObject(checkSql, Integer.class, id) == 1) {
    jdbc.update(updateWithoutConditionSql, id);
}
```

Phương án đúng là đưa điều kiện cần bảo vệ vào `UPDATE ... WHERE ..., đọc count, rồi kiểm tra đúng số hàng theo use case.

## 10. Kiểm thử các trường hợp biên

Nên viết integration test với **cùng hệ quản trị DB/driver quan trọng của môi trường thật**, đặc biệt cho semantics của count và concurrent updates:

| Trường hợp | Kết quả cần xác minh |
| --- | --- |
| Có đúng một hàng phù hợp | Count `1, dữ liệu thay đổi đúng, transaction commit |
| ID không tồn tại | Count `0, nhánh nghiệp vụ đúng |
| ID có nhưng trạng thái không hợp lệ | Count `0, không ghi sai trạng thái |
| Hai request gửi cùng version cũ | Một request có thể count `1, request còn lại phải phát hiện count `0 sau khi version đổi (tùy lịch thực thi) |
| `WHERE quá rộng, có hai hàng phù hợp | Count `2 được phát hiện; transaction rollback toàn bộ |
| Nghiệp vụ cho phép retry idempotent | `0 được diễn giải theo contract, không trả success sai khi trạng thái cuối chưa xác minh |
| Batch có phần tử `0 hoặc `-2 | Không báo mọi item thành công; xử lý theo policy đã định |
| `UPDATE gán giá trị bằng giá trị cũ | Đo count thực tế với DB/driver hiện dùng; không giả định thống nhất |
| Exception xảy ra sau một lần cập nhật đúng count | Đảm bảo tất cả ghi trong transaction được rollback khi policy yêu cầu |

Checklist code review: `WHERE đã đủ khóa và điều kiện trạng thái/version/tenant chưa? Kỳ vọng count là `== 1, `0..1 hay `0..N? “0” có bao nhiêu nguyên nhân? Kiểm tra count xảy ra trước commit chứ? Transaction có thực sự hoạt động? Có batch trả count không xác định? Test cạnh tranh và idempotent có bao phủ không?

## 11. Ghi nhớ và tài liệu tham khảo

**Công thức thực hành:** xác định invariant từ yêu cầu nghiệp vụ → viết `UPDATE/DELETE với `WHERE bảo vệ invariant → lấy row count do JDBC/JPA báo → kiểm tra theo hợp đồng → commit hoặc rollback và diễn giải kết quả phù hợp. Count là tín hiệu cần thiết để phát hiện xung đột và cập nhật quá rộng, nhưng cần phối hợp với ràng buộc schema, transaction và kiểm thử concurrent access.

Tài liệu chính thức:
- Spring Framework, JDBC Batch Operations: https://docs.spring.io/spring-framework/reference/data-access/jdbc/advanced.html
- Spring Framework, `@Transactional settings và rollback: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html
- Spring Data JPA, modifying queries: https://docs.spring.io/spring-data/jpa/reference/jpa/query-methods.html
- Spring Data JPA, transactionality: https://docs.spring.io/spring-data/jpa/reference/jpa/transactions.html
- JDBC `Statement update counts: https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/Statement.html
