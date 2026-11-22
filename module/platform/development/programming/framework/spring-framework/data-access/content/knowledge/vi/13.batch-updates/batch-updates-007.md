# BatchUpdateException, thất bại một phần và thông tin từ trình điều khiển

## 1. Bối cảnh và mục tiêu

Trong module **Spring Framework – Data Access**, cập nhật theo lô (batch update) giúp gửi nhiều thao tác `INSERT`, `UPDATE` hoặc `DELETE` qua JDBC với ít lượt trao đổi với cơ sở dữ liệu hơn. Tuy nhiên, khi một lệnh gặp lỗi, câu hỏi không chỉ là “batch có lỗi hay không” mà còn là:

- Driver đã chạy đến lệnh nào, có tiếp tục sau lỗi không?
- Giá trị trả về có nghĩa là **đã thực thi**, **đã ảnh hưởng bao nhiêu dòng**, hay **đã commit**?
- Spring bọc lỗi JDBC thành exception nào, còn truy cập được thông tin gốc không?
- Làm thế nào để rollback, ghi log, khoanh vùng bản ghi và retry mà không làm sai dữ liệu?

Bài này tập trung vào `java.sql.BatchUpdateException`, kết quả thực thi từng lệnh và cách xử lý trong `JdbcTemplate`. Phạm vi là JDBC/Spring JDBC; không đồng nhất hành vi với JPA `saveAll` hay R2DBC.

## 2. Đường đi của một batch

Với JDBC thuần, ứng dụng thường đặt tham số rồi gọi `PreparedStatement.addBatch()` nhiều lần, cuối cùng gọi `executeBatch()`. Với Spring JDBC, `JdbcTemplate.batchUpdate(...)` đảm nhiệm việc tạo statement, gắn tham số, gọi JDBC và dọn tài nguyên.

```text
Danh sách đầu vào có thứ tự
    -> JdbcTemplate.batchUpdate(...)
    -> PreparedStatement / JDBC driver
    -> Cơ sở dữ liệu xử lý từng thao tác hoặc tối ưu hóa cả batch
    -> Thành công: int[] update counts
       Lỗi JDBC: SQLException / BatchUpdateException
    -> Spring dịch SQLException thành DataAccessException
```

Lưu ý: batch là cơ chế gửi/thi hành nhiều lệnh; **batch không tự tạo một ranh giới giao dịch nguyên tử**. Tính nguyên tử phụ thuộc transaction, driver và cơ sở dữ liệu.

## 3. BatchUpdateException là gì?

`BatchUpdateException` nằm trong `java.sql` và kế thừa `SQLException`. Nó có thể phát sinh khi `executeBatch()` gặp lỗi và chứa thông tin bổ sung về các lệnh đã xử lý:

| API / thông tin | Ý nghĩa | Cách dùng |
| --- | --- | --- |
| `getUpdateCounts()` | Mảng `int[]` các kết quả driver báo theo thứ tự thêm lệnh vào batch | Đối chiếu các vị trí đã được báo kết quả |
| `getLargeUpdateCounts()` | Mảng `long[]` tương ứng | Ưu tiên với `executeLargeBatch()` khi số dòng có thể rất lớn |
| `getSQLState()` | Mã SQLState do driver cung cấp; có thể `null` | Phân loại sơ bộ loại lỗi, đối chiếu tài liệu DB/driver |
| `getErrorCode()` | Mã lỗi riêng của nhà cung cấp; có thể là `0` | Tra cứu nguyên nhân cụ thể theo database |
| `getMessage()` | Thông báo của driver | Hỗ trợ điều tra, không dùng so khớp chuỗi để quyết định logic |
| `getNextException()` | Chuỗi `SQLException` bổ sung | Đọc lỗi chi tiết của một hoặc nhiều lệnh |
| `getCause()` | Nguyên nhân trong chuỗi exception Java | Truy ngược tầng bọc lỗi |

`BatchUpdateException` là **báo cáo từ driver**, không phải bảng trạng thái chắc chắn của các bản ghi sau commit. Nó cũng không luôn tồn tại: nếu driver không hỗ trợ JDBC batching, `JdbcTemplate` có thể thực hiện lần lượt các update và ném một `DataAccessException` với nguyên nhân JDBC khác.

### Các mã kết quả đặc biệt

| Giá trị một phần tử `counts[i]` | Diễn giải |
| --- | --- |
| `0` | Lệnh có báo kết quả, nhưng không ảnh hưởng dòng nào; không tự động là lỗi |
| Số dương như `1`, `2` | Số dòng bị ảnh hưởng do driver báo |
| `Statement.SUCCESS_NO_INFO` = `-2` | Lệnh thành công, nhưng driver không biết/không báo chính xác số dòng |
| `Statement.EXECUTE_FAILED` = `-3` | Lệnh tại vị trí đó thất bại; thường xuất hiện khi driver tiếp tục xử lý sau lỗi |

Không cộng các mã âm vào tổng “số dòng thành công”, không coi `-2` là lỗi, và không biến `0` thành “thành công nghiệp vụ” nếu yêu cầu của bạn là phải cập nhật đúng một dòng.

## 4. Hai kiểu thất bại một phần: driver dừng hoặc tiếp tục

Giả sử gửi bốn tham số theo thứ tự `[A, B, C, D]`.

**Trường hợp driver dừng ở lỗi:**

```text
Đầu vào:       A   B   C   D
getUpdateCounts() = [1, 0]
```

Hai kết quả đầu được báo (A ảnh hưởng 1 dòng, B ảnh hưởng 0 dòng). Driver không cung cấp phần tử kết quả cho C và D; theo hợp đồng JDBC “dừng tại lỗi”, lệnh kế tiếp sau hai lệnh thành công là ứng viên gây lỗi. Không có bằng chứng rằng D đã được thực thi. Việc A/B **đã commit hay chưa** phải xem transaction.

**Trường hợp driver tiếp tục sau lỗi:**

```text
Đầu vào:       A    B    C    D
getUpdateCounts() = [1, -3, -2, 0]
```

Driver báo A ảnh hưởng 1 dòng, B thất bại, C thành công nhưng không biết số dòng, D ảnh hưởng 0 dòng. Mảng có một phần tử cho mỗi lệnh; vị trí `-3` cho phép xác định lệnh bị driver báo thất bại. Dù vậy, giao dịch có thể cuối cùng rollback tất cả.

Đọc các kết quả phải xét **driver có dừng hay tiếp tục**, có rewrite/gộp batch hay không, và câu lệnh SQL thực tế. Một số tối ưu hóa ở driver có thể hạn chế độ chính xác khi truy vị trí bản ghi lỗi. Không suy diễn `counts.length == số đầu vào` thành “tất cả đã commit”.

## 5. Spring JDBC trả về và chuyển đổi exception như thế nào?

Một số API thường gặp:

| API | Kết quả khi hoàn thành | Đặc điểm |
| --- | --- | --- |
| `JdbcTemplate.batchUpdate(String, BatchPreparedStatementSetter)` | `int[]` | Một SQL, gắn tham số theo chỉ số `i` từ `0` |
| `JdbcTemplate.batchUpdate(String, List<Object[]>)` | `int[]` | Mỗi mảng chứa tham số cho một lần chạy cùng SQL |
| `NamedParameterJdbcTemplate.batchUpdate(String, SqlParameterSource[])` | `int[]` | Gắn tham số theo tên |
| `JdbcTemplate.batchUpdate(String, Collection<T>, int, ParameterizedPreparedStatementSetter<T>)` | `int[][]` | Chia thành các nhóm có kích thước chỉ định |

Mảng `int[][]` theo nhóm chỉ có ý nghĩa **khi lời gọi hoàn thành**; nếu một nhóm gặp lỗi và exception thoát ra, không có bảo đảm bạn nhận được mọi mảng kết quả như khi thành công.

`JdbcTemplate` sử dụng `SQLExceptionTranslator` để chuyển `SQLException` thành ngoại lệ không kiểm tra `DataAccessException` (chẳng hạn một subtype liên quan ràng buộc hoặc tài nguyên). **Không viết `catch (BatchUpdateException e)` trực tiếp quanh `jdbcTemplate.batchUpdate(...)`**: chữ ký Spring ném `DataAccessException`, còn exception JDBC gốc thường nằm trong chuỗi nguyên nhân. Không mặc định mọi lỗi trùng khóa đều luôn thành `DuplicateKeyException`; subtype tùy translator, mã lỗi và driver.

Nếu driver không hỗ trợ batch update, Spring có thể chuyển sang các update riêng trên một `PreparedStatement`. Vì vậy, thuật toán giám sát phải chấp nhận trường hợp không tìm thấy `BatchUpdateException`.

## 6. Ví dụ Spring: dữ liệu đầu vào có thứ tự và rollback

Giả sử đã có bảng `employee(id BIGINT PRIMARY KEY, full_name VARCHAR(200) NOT NULL)`, cấu hình `DataSource`, `JdbcTemplate` và transaction manager phù hợp. Đây là **một lớp dịch vụ Spring**, không phải chương trình Java thuần có thể chạy riêng nếu thiếu dependency/configuration:

```java
import java.sql.PreparedStatement;
import java.sql.SQLException;
import java.util.List;

import org.springframework.jdbc.core.BatchPreparedStatementSetter;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class EmployeeImportService {
    private final JdbcTemplate jdbcTemplate;

    public EmployeeImportService(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    @Transactional
    public int[] importEmployees(List<Employee> employees) {
        return jdbcTemplate.batchUpdate(
            "INSERT INTO employee (id, full_name) VALUES (?, ?)",
            new BatchPreparedStatementSetter() {
                @Override
                public void setValues(PreparedStatement ps, int i)
                        throws SQLException {
                    Employee e = employees.get(i);
                    ps.setLong(1, e.id());
                    ps.setString(2, e.fullName());
                }

                @Override
                public int getBatchSize() {
                    return employees.size();
                }
            }
        );
    }

    public record Employee(long id, String fullName) {}
}
```

`setValues(..., i)` gắn phần tử thứ `i` trong danh sách, nên cần giữ thứ tự/ID của `employees` để hỗ trợ chẩn đoán. Dùng placeholder `?` tránh ghép dữ liệu thẳng vào SQL.

Với `@Transactional` được kích hoạt qua Spring proxy và transaction manager dùng cùng `DataSource`, `DataAccessException` thoát ra khỏi phương thức (là `RuntimeException`) dẫn tới rollback theo quy tắc mặc định. Cần lưu ý rằng `@Transactional` có thể không được áp dụng khi gọi nội bộ phương thức qua `this` thay vì đi qua proxy. Ngoài ra, cơ sở dữ liệu phải hỗ trợ transaction đúng cho bảng/thao tác đó.

Nếu cần ghi log, đặt việc bắt lỗi ở **lớp gọi bên ngoài ranh giới transaction** hoặc bắt rồi ném lại. Nuốt ngoại lệ trong phương thức `@Transactional` khiến Spring không tự biết phải rollback; ở một số cơ sở dữ liệu, giao dịch đã bị đánh dấu lỗi và commit vẫn sẽ thất bại.

## 7. Tìm thông tin gốc trong chuỗi lỗi của Spring

Một exception ở tầng service có thể được bọc nhiều lớp. Chỉ gọi `getMessage()` của `DataAccessException` thường bỏ sót các mã SQL và update counts.

Đoạn Java 17 dưới đây là **hàm hỗ trợ độc lập**, tìm `BatchUpdateException` trong cả `getCause()` lẫn `SQLException.getNextException()`, tránh vòng lặp chuỗi lỗi:

```java
import java.sql.BatchUpdateException;
import java.sql.SQLException;
import java.util.ArrayDeque;
import java.util.Collections;
import java.util.Deque;
import java.util.IdentityHashMap;
import java.util.Set;

public final class BatchErrorInspector {
    private BatchErrorInspector() {}

    public static BatchUpdateException findBatchFailure(Throwable error) {
        if (error == null) {
            return null;
        }

        Deque<Throwable> queue = new ArrayDeque<>();
        Set<Throwable> seen =
            Collections.newSetFromMap(new IdentityHashMap<>());
        queue.add(error);

        while (!queue.isEmpty()) {
            Throwable current = queue.removeFirst();
            if (!seen.add(current)) {
                continue;
            }
            if (current instanceof BatchUpdateException batch) {
                return batch;
            }
            if (current.getCause() != null) {
                queue.addLast(current.getCause());
            }
            if (current instanceof SQLException sql
                    && sql.getNextException() != null) {
                queue.addLast(sql.getNextException());
            }
        }
        return null;
    }
}
```

Sau khi bắt `DataAccessException e` ở lớp gọi, có thể lấy `BatchUpdateException b = BatchErrorInspector.findBatchFailure(e)`. Nếu `b != null`, ghi `b.getSQLState()`, `b.getErrorCode()`, độ dài và các phần tử `b.getUpdateCounts()`; nếu `b == null`, vẫn ghi phân loại `DataAccessException` và nguyên nhân `SQLException` nếu có, vì lỗi có thể phát sinh ngoài `executeBatch()`.

Đọc chuỗi `getNextException()` để tìm lỗi chi tiết. Ví dụ, SQLState thuộc lớp `23` thường nói về vi phạm ràng buộc theo SQLState chuẩn; mã SQLState cụ thể, mã vendor, thông điệp và hành vi đều cần đối chiếu với **database + phiên bản JDBC driver thực tế**. Tránh xây logic trên thông báo tiếng Anh của driver.

**Dữ liệu chẩn đoán nên ghi:** tên thao tác, số lệnh trong batch, chỉ số nhóm, mã định danh nghiệp vụ không nhạy cảm của mỗi bản ghi (khi được phép), SQLState, vendor code, loại ngoại lệ, mảng counts và thông tin driver/database. **Không ghi mật khẩu, token, toàn bộ câu lệnh đã nội suy hoặc dữ liệu cá nhân của tham số**.

## 8. Ví dụ Java 17 chạy độc lập: hiểu update counts

Ví dụ này **tự tạo hai exception giả lập** để minh họa định dạng phản hồi. Nó không kết nối database và không chứng minh một driver cụ thể sẽ xử lý theo kiểu nào.

Lưu thành `BatchFailureDemo.java`:

```java
import java.sql.BatchUpdateException;
import java.sql.Statement;
import java.util.Arrays;

public class BatchFailureDemo {
    private static void explain(String label,
                                BatchUpdateException error,
                                int submitted) {
        int[] counts = error.getUpdateCounts();
        System.out.println(label + ": " + Arrays.toString(counts));

        for (int i = 0; i < counts.length; i++) {
            int value = counts[i];
            String meaning = value == Statement.SUCCESS_NO_INFO
                ? "SUCCESS_NO_INFO"
                : value == Statement.EXECUTE_FAILED
                    ? "EXECUTE_FAILED"
                    : "affected=" + value;
            System.out.println("  #" + i + ": " + meaning);
        }

        if (counts.length < submitted) {
            System.out.println("  no result from index " + counts.length);
        }
    }

    public static void main(String[] args) {
        BatchUpdateException stop = new BatchUpdateException(
            "Simulated failure", "23505", 0, new int[] {1, 0});
        BatchUpdateException continueAfterFailure =
            new BatchUpdateException(
                "Simulated failure", "23505", 0,
                new int[] {
                    1,
                    Statement.EXECUTE_FAILED,
                    Statement.SUCCESS_NO_INFO,
                    0
                });

        explain("stop", stop, 4);
        explain("continue", continueAfterFailure, 4);
    }
}
```

Chạy bằng JDK 17 trở lên:

```bash
javac BatchFailureDemo.java
java BatchFailureDemo
```

Kết quả stdout chính xác:

```text
stop: [1, 0]
  #0: affected=1
  #1: affected=0
  no result from index 2
continue: [1, -3, -2, 0]
  #0: affected=1
  #1: EXECUTE_FAILED
  #2: SUCCESS_NO_INFO
  #3: affected=0
```

Trong ứng dụng thật, nếu dùng `Statement.executeLargeBatch()` và số dòng lớn, ưu tiên `BatchUpdateException.getLargeUpdateCounts()` để tránh tràn phạm vi `int`. Không thay `int[]` trong API Spring bằng `long[]` khi chữ ký method chỉ trả `int[]`.

## 9. Thất bại một phần khác với trạng thái đã commit

Cần tách ba khái niệm:

1. **Đã gửi**: ứng dụng đã đưa lệnh vào batch.
2. **Driver báo đã thực thi**: một phần tử counts là số không âm hoặc `SUCCESS_NO_INFO`.
3. **Đã commit**: thay đổi có hiệu lực bền vững theo transaction.

`getUpdateCounts()` phản ánh cấp độ (2), **không chứng nhận (3)**. Ví dụ, driver báo `[1, 1]` rồi lệnh thứ ba lỗi; nếu toàn bộ batch ở trong một transaction và rollback thành công thì hai thay đổi đầu cũng không được commit. Trái lại, khi không có transaction bao phủ và auto-commit/driver/DB cho phép commit từng phần, dữ liệu có thể tồn tại một phần. Không suy đoán hành vi từ mảng counts; kiểm tra transaction, `autoCommit`, đặc tính DB, lỗi tại commit và dữ liệu sau giao dịch.

| Tổ chức giao dịch | Khi có lỗi giữa batch | Cách quyết định |
| --- | --- | --- |
| Một `@Transactional` bao toàn bộ import | Lỗi unchecked được truyền qua proxy thường dẫn tới rollback toàn bộ transaction | Chọn khi cần tất cả hoặc không có gì |
| Mỗi chunk có transaction riêng | Chunk trước có thể đã commit; chunk lỗi rollback | Chọn khi nghiệp vụ cho phép lưu tiến độ từng chunk |
| Không có transaction rõ ràng | Nguy cơ lưu một phần phụ thuộc connection/driver/DB | Không dùng nếu yêu cầu tính nguyên tử |
| Bắt exception rồi tiếp tục trong transaction | Trạng thái có thể không còn dùng được; commit có thể thất bại hoặc dữ liệu bị lưu dở | Không “tiếp tục như thường” nếu chưa có chính sách phục hồi |

Nên xác nhận hành vi qua integration test trên đúng DB và phiên bản driver chạy thật. Với một số DB, chỉ một câu SQL lỗi đã làm transaction hiện tại ở trạng thái phải rollback; savepoint hoặc recovery cần thiết kế và kiểm tra riêng.

## 10. Điều tra, cô lập và retry an toàn

Quy trình xử lý thực tế:

1. **Giữ thứ tự đầu vào:** lưu batch ID, chunk ID và ánh xạ chỉ số sang khóa nghiệp vụ, để counts có ý nghĩa; không cần lưu dữ liệu nhạy cảm trong log.
2. **Nhận ngoại lệ Spring:** quan sát subtype của `DataAccessException` và tìm `SQLException` / `BatchUpdateException` trong cả cause và next-exception chain.
3. **Diễn giải counts đúng nhánh:** phân biệt driver dừng, driver tiếp tục, `-2`, `-3` và các lệnh chưa có kết quả. Ghi rõ “chưa xác định” khi driver không cung cấp đủ chứng cứ.
4. **Xác nhận kết quả giao dịch:** đã rollback hay commit? Nếu lỗi xảy ra lúc commit, không giả sử dữ liệu chắc chắn chưa lưu; kiểm tra trạng thái bằng khóa nghiệp vụ/idempotency key.
5. **Phân loại nguyên nhân:** vi phạm unique/foreign key/not-null và dữ liệu sai cần sửa dữ liệu hoặc quy tắc; lỗi deadlock/kết nối tạm thời có thể xem xét retry sau rollback, tùy loại lỗi và khả năng lặp an toàn.
6. **Retry có kiểm soát:** chỉ retry trong transaction mới khi nguyên nhân phù hợp; dùng khóa duy nhất, idempotency key hoặc upsert được thiết kế rõ để tránh nhân đôi dữ liệu. Không chạy lại mù quáng cả batch trong trạng thái không chắc commit.
7. **Cô lập dữ liệu xấu nếu cần:** sau rollback, có thể chia nhỏ batch để tìm bản ghi gây lỗi, hoặc xử lý từng bản ghi trong các transaction độc lập, nhưng chỉ khi nghiệp vụ chấp nhận thành công một phần và có báo cáo đầy đủ.

Với Spring, cách đơn giản nhất cho một tác vụ **all-or-nothing** là để `DataAccessException` thoát khỏi phương thức `@Transactional`. Nếu muốn chấp nhận thành công một phần, phải thiết kế tường minh transaction theo chunk, trạng thái từng bản ghi, quy tắc retry và cách báo cáo kết quả sau commit.

## 11. Các lỗi hiểu sai thường gặp

- **“Có `-2` nghĩa là thất bại.”** Sai: `SUCCESS_NO_INFO` nghĩa là thành công nhưng không biết số dòng.
- **“`counts.length` nhỏ hơn đầu vào nên phần còn lại chắc chắn chưa động tới DB.”** Không thể kết luận tuyệt đối ngoài hợp đồng/hành vi driver đã xác minh; nhất là khi có tối ưu hóa batch và lỗi ở nhiều tầng.
- **“`1` trong counts nghĩa là bản ghi đã lưu vĩnh viễn.”** Sai: transaction có thể rollback.
- **“Spring luôn ném `BatchUpdateException`.”** Sai: tầng Spring thường ném `DataAccessException`, đôi khi không có `BatchUpdateException` bên dưới.
- **“Đã bắt và log lỗi trong `@Transactional` rồi return thì Spring tự rollback.”** Không bảo đảm; cần để exception thoát ra hoặc chủ động đánh dấu rollback theo thiết kế.
- **“Có thể retry mọi lỗi batch.”** Sai: lỗi ràng buộc/dữ liệu không tự biến mất, và retry không idempotent có thể gây trùng lặp.
- **“SQLState và mã lỗi giống nhau ở mọi DB.”** Sai: phải đối chiếu tài liệu hệ quản trị và driver tương ứng.

## 12. Bài tập kiểm chứng với hệ thống thật

Tạo bảng có khóa chính, gửi batch bốn dòng trong đó dòng thứ ba trùng khóa; chạy hai chế độ **có** và **không có** transaction bao phủ (trên môi trường thử nghiệm). Ghi lại:

- Kiểu exception mà Spring ném và toàn bộ `SQLException` lồng bên trong.
- `getSQLState()`, `getErrorCode()`, `getUpdateCounts()`, `getNextException()` khi tìm được `BatchUpdateException`.
- Thứ tự đầu vào ↔ chỉ số báo lỗi; driver dừng hay tiếp tục.
- Các dòng thực sự còn trong DB **sau** rollback/commit.
- Hành vi khi chia thành hai chunk và khi thử lại một chunk bằng thao tác idempotent.

Thử tiếp `UPDATE` với khóa không tồn tại để thấy counts `0` có thể là kết quả hợp lệ về mặt JDBC nhưng chưa chắc đạt yêu cầu nghiệp vụ. Thử `BatchPreparedStatementSetter` và overload có `batchSize` để quan sát sự khác biệt giữa `int[]` và `int[][]` khi thành công.

## Tài liệu gốc

- [Java 17: BatchUpdateException](https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/BatchUpdateException.html) — hợp đồng counts, dừng/tiếp tục, `getLargeUpdateCounts()`.
- [Spring Framework: JDBC Batch Operations](https://docs.spring.io/spring-framework/reference/6.2/data-access/jdbc/advanced.html) — các overload `batchUpdate`, kiểu kết quả và batching theo chunk.
- [Spring Framework: JDBC exception translation](https://docs.spring.io/spring-framework/reference/6.2/data-access/jdbc/core.html) — chuyển `SQLException` sang `DataAccessException`.
- [Spring Framework: Transaction rollback](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/declarative/rolling-back.html) — rollback mặc định với unchecked exception.
