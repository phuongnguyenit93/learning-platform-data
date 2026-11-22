# Phối hợp batch với khóa sinh và kiểm tra tính khả chuyển trong JDBC

Trong chương **Xử lý theo lô**, `PreparedStatement.addBatch()` và `executeBatch()` giúp giảm số lượt trao đổi giữa ứng dụng Java và cơ sở dữ liệu khi cần chèn hoặc cập nhật nhiều bản ghi. Nhưng một yêu cầu thực tế thường phức tạp hơn việc “chạy 100 câu `INSERT`”: sau mỗi lần chèn, ứng dụng còn cần lấy **khóa do cơ sở dữ liệu sinh ra** để tạo bản ghi con hoặc liên kết khóa đó với đối tượng đầu vào.

JDBC cung cấp `getGeneratedKeys()`, song khi kết hợp với batch, **khả năng trả khóa, số lượng khóa, thứ tự kết quả và cách xử lý lỗi phụ thuộc driver và hệ quản trị cơ sở dữ liệu**. Ngay cả khi driver báo hỗ trợ batch và generated keys, điều đó chưa bảo đảm từng khóa có thể gán cho từng phần tử đầu vào bằng chỉ số mảng.

Bài này hướng dẫn dùng các API chuẩn `DataSource`, `Connection`, `PreparedStatement` và `ResultSet`, kiểm tra tính năng với `DatabaseMetaData`, xử lý `BatchUpdateException`, kiểm soát transaction và chọn phương án tương thích khi cần ghép chính xác khóa với từng bản ghi.

## 1. Bài toán: batch `INSERT` cần biết ID của từng phần tử

Giả sử có bảng khách hàng với khóa chính được DB tạo:

```sql
CREATE TABLE customer (
    id           BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    request_code VARCHAR(64) NOT NULL UNIQUE,
    email        VARCHAR(255) NOT NULL
);
```

`GENERATED ALWAYS AS IDENTITY` là cú pháp có ở nhiều hệ quản trị theo SQL chuẩn; các DB như MySQL hoặc SQLite có thể yêu cầu cú pháp khai báo khóa sinh khác. Cột `request_code` là **mã đối chiếu do ứng dụng tạo, không phải khóa tự sinh**; nó giúp tìm lại đúng bản ghi khi việc ánh xạ khóa từ batch không đáng tin cậy.

Ba phần tử đầu vào:

| Vị trí đầu vào | `request_code` | `email` |
| --- | --- | --- |
| 0 | `req-A` | `an@example.com` |
| 1 | `req-B` | `binh@example.com` |
| 2 | `req-C` | `chi@example.com` |

DB có thể sinh các ID như `101`, `105` và `108`. Đây chỉ là ví dụ: ID có thể không liên tục vì sequence, transaction bị hủy hoặc các bản ghi khác cùng được tạo.

Hai yêu cầu **khác nhau** cần phân biệt:

1. **Lấy danh sách những khóa được trả về:** có thể đọc các hàng trong `ResultSet` của `getGeneratedKeys()` khi driver hỗ trợ.
2. **Xác định ID của chính `req-B` là bao nhiêu:** cần có bảo đảm về quan hệ giữa **hàng kết quả và phần tử đầu vào**, hoặc dùng mã đối chiếu trong dữ liệu; số lượng khóa bằng số lượng đầu vào **chưa đủ** chứng minh thứ tự ánh xạ.

Nếu gán nhầm ID, ứng dụng có thể tạo hóa đơn, địa chỉ hoặc giao dịch cho sai khách hàng dù không có câu SQL nào ném lỗi.

## 2. Cơ chế batch cơ bản trong `PreparedStatement`

Với SQL có tham số, ứng dụng đặt giá trị cho từng bộ tham số rồi gọi `addBatch()`. `executeBatch()` gửi tập lệnh đã thêm để DB/driver thực thi và trả về số dòng chịu ảnh hưởng:

```java
String sql = """
        INSERT INTO customer (request_code, email)
        VALUES (?, ?)
        """;

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setString(1, "req-A");
    ps.setString(2, "an@example.com");
    ps.addBatch();

    ps.setString(1, "req-B");
    ps.setString(2, "binh@example.com");
    ps.addBatch();

    int[] counts = ps.executeBatch();
}
```

`addBatch()` đưa bộ tham số hiện tại vào lô; nó **chưa thực thi `INSERT`**. `executeBatch()` mới gửi/chạy các thao tác và nhận thông tin kết quả. Batch không mặc nhiên tạo transaction nguyên tử, vì việc commit phụ thuộc chế độ `autoCommit`, DB và tầng quản lý transaction. Với một loạt bản ghi có quan hệ logic, cần xác định transaction bao trùm cả lô.

Không nhầm `clearParameters()` với `clearBatch()`:

- `clearParameters()` xóa giá trị tham số đã đặt cho `PreparedStatement`; nó không xóa các bộ tham số đã thêm vào batch.
- `clearBatch()` xóa tập lệnh đang chờ thực thi; nó **không rollback** những lệnh đã chạy ở DB.
- Thường không cần gọi cả hai sau mỗi `addBatch()`, miễn là mọi vị trí `?` cần thiết đều được gán lại đúng giá trị cho phần tử tiếp theo.

## 3. Yêu cầu generated keys ngay khi chuẩn bị statement

Muốn nhận khóa sinh, hãy yêu cầu từ lúc tạo `PreparedStatement`:

```java
String sql =
        "INSERT INTO customer (request_code, email) VALUES (?, ?)";

// Cách A: yêu cầu driver trả khóa sinh theo cơ chế mặc định.
PreparedStatement a = connection.prepareStatement(
        sql, Statement.RETURN_GENERATED_KEYS);

// Cách B: yêu cầu đích danh cột id.
PreparedStatement b = connection.prepareStatement(
        sql, new String[] {"id"});

// Cách C: yêu cầu cột thứ nhất của bảng, không phải tham số ? thứ nhất.
PreparedStatement c = connection.prepareStatement(
        sql, new int[] {1});
```

Ba statement trên chỉ minh họa các overload, cần được đóng khi dùng thực tế. **Không chuẩn bị cả ba** cho một lô chỉ để “chắc ăn”. Chọn một cách đã được kiểm chứng trên driver dự án:

| Overload | Ý nghĩa | Lưu ý về tính khả chuyển |
| --- | --- | --- |
| `prepareStatement(sql, Statement.RETURN_GENERATED_KEYS)` | Yêu cầu các khóa do driver xác định | Cột và hình dạng `ResultSet` có thể khác nhau |
| `prepareStatement(sql, new String[]{"id"})` | Yêu cầu trả cột `id` | Driver có thể không hỗ trợ yêu cầu tên cột cụ thể |
| `prepareStatement(sql, new int[]{1})` | Yêu cầu cột vị trí 1 của bảng đích | Phụ thuộc thứ tự schema và khả năng driver |

Với thao tác tạo ID, yêu cầu theo **tên cột** giúp thể hiện rõ ý định, nhưng phải kiểm thử. Một số driver chỉ hỗ trợ `RETURN_GENERATED_KEYS` mặc định; một số khác cần khai báo tên cột rõ ràng. Chỉ số trong `columnIndexes` là chỉ số **cột bảng**, không phải thứ tự dấu `?`.

Sau `executeBatch()`, dùng `ps.getGeneratedKeys()` để đọc các khóa mà driver trả:

```java
int[] counts = ps.executeBatch();

try (ResultSet keys = ps.getGeneratedKeys()) {
    while (keys.next()) {
        long id = keys.getLong(1);
        if (keys.wasNull()) {
            throw new SQLException("Driver trả khóa NULL");
        }
        System.out.println("Khóa được trả về: " + id);
    }
}
```

Đoạn trên giả định `ps` đã chuẩn bị với chế độ trả khóa và kiểu `id` tương thích `long`. Nó **in danh sách khóa**, chưa xác định ID của từng `request_code`. `getGeneratedKeys()` không phải cơ chế ánh xạ đầu vào → khóa một cách phổ quát cho mọi batch.

## 4. Kiểm tra khả năng hỗ trợ của driver trước khi dựa vào batch + keys

`DatabaseMetaData` có hai phép kiểm tra hữu ích:

```java
import java.sql.Connection;
import java.sql.DatabaseMetaData;
import java.sql.SQLException;
import javax.sql.DataSource;

public static void inspectSupport(DataSource dataSource)
        throws SQLException {
    try (Connection connection = dataSource.getConnection()) {
        DatabaseMetaData meta = connection.getMetaData();

        System.out.println("Batch: " + meta.supportsBatchUpdates());
        System.out.println(
                "Generated keys: " + meta.supportsGetGeneratedKeys());
        System.out.println("DB: " + meta.getDatabaseProductName()
                + " " + meta.getDatabaseProductVersion());
        System.out.println("Driver: " + meta.getDriverName()
                + " " + meta.getDriverVersion());
    }
}
```

- `supportsBatchUpdates()` cho biết driver công bố hỗ trợ batch updates.
- `supportsGetGeneratedKeys()` cho biết driver công bố hỗ trợ lấy khóa sinh.
- Cả hai cùng trả `true` chỉ là **điều kiện cần để cân nhắc**, chưa chứng minh batch sinh **đủ khóa, đúng thứ tự** hoặc hỗ trợ tên cột cụ thể.

Ngay cả khi metadata trả `true`, driver vẫn có thể ném `SQLFeatureNotSupportedException`, `SQLException` hoặc trả ít khóa hơn cho một câu lệnh hay cấu hình nhất định. Không có phép kiểm tra metadata JDBC chuẩn nào bảo đảm **thứ tự các hàng do `getGeneratedKeys()` trả về sẽ luôn tương ứng vị trí từng `addBatch()`** trong mọi hệ quản trị.

Nếu ứng dụng cần ghép khóa chính xác, hãy xác minh đầy đủ bằng một **kiểm thử round-trip** trên đúng DB, phiên bản driver, kiểu cột và cơ chế batch; đồng thời xem tài liệu driver để biết mức bảo đảm được công bố.

## 5. Đọc `executeBatch()` và `BatchUpdateException` đúng cách

Giá trị trả về từ `executeBatch()` là một mảng `int[]`. Khi lô thành công, mỗi phần tử mô tả kết quả của một lệnh trong batch (thường theo thứ tự lệnh được thêm); **giá trị không nhất thiết luôn là số dương**.

| Kết quả cập nhật | Ý nghĩa |
| --- | --- |
| `0`, `1`, `2`, ... | Số dòng bị ảnh hưởng mà driver báo |
| `Statement.SUCCESS_NO_INFO` (`-2`) | Lệnh thành công nhưng driver không thể cho biết số dòng |
| `Statement.EXECUTE_FAILED` (`-3`) | Lệnh được báo thất bại trong kết quả batch; thường gặp trong `BatchUpdateException` nếu driver tiếp tục xử lý sau lỗi |

`SUCCESS_NO_INFO` **không phải lỗi** và cũng không có nghĩa “0 dòng”. Nếu bạn cần biết chắc mỗi `INSERT` ảnh hưởng đúng một dòng, `-2` chỉ cho biết driver không xác nhận được con số; phải chọn chính sách xác minh khác.

Khi một lệnh trong lô lỗi, `executeBatch()` thường ném `BatchUpdateException`:

```java
import java.sql.BatchUpdateException;
import java.sql.SQLException;
import java.sql.Statement;
import java.util.Arrays;

try {
    int[] counts = ps.executeBatch();
    System.out.println(Arrays.toString(counts));
} catch (BatchUpdateException failure) {
    int[] partial = failure.getUpdateCounts();
    System.err.println("Batch counts: " + Arrays.toString(partial));
    System.err.println("SQLState: " + failure.getSQLState());
    System.err.println("Vendor code: " + failure.getErrorCode());

    for (int n : partial) {
        if (n == Statement.EXECUTE_FAILED) {
            System.err.println("Có lệnh batch bị báo thất bại");
        }
    }
    throw failure;
}
```

`ps` trong ví dụ là `PreparedStatement` đã có batch. Tùy driver, sau lỗi:

- **Dừng tại câu lệnh lỗi:** mảng `getUpdateCounts()` có thể chỉ chứa kết quả của các lệnh **đã chạy trước** câu lệnh lỗi.
- **Tiếp tục sau lỗi:** mảng có thể có một phần tử cho mỗi lệnh, với `EXECUTE_FAILED` tại vị trí bị lỗi.
- Các lệnh thực thi trước khi phát sinh lỗi có thể đã thay đổi dữ liệu trong transaction; **bắt exception không tự rollback** chúng.

Với batch rất lớn hoặc khi cần số đếm kiểu `long`, JDBC có `executeLargeBatch()` và `BatchUpdateException.getLargeUpdateCounts()`. Khả năng triển khai và giới hạn cụ thể vẫn phải được kiểm tra trên driver hiện hành.

## 6. Ví dụ JDBC: chèn batch, kiểm tra số đếm và thu thập khóa

Ví dụ sau thực hiện một batch trong transaction do phương thức sở hữu. Phương thức trả hai tập kết quả **tách biệt**: `updateCounts` và các khóa theo **thứ tự driver trả về**. Nó **không** khẳng định khóa vị trí `i` thuộc đầu vào vị trí `i`.

```java
import java.sql.BatchUpdateException;
import java.sql.Connection;
import java.sql.DatabaseMetaData;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.SQLFeatureNotSupportedException;
import java.sql.Statement;
import java.util.ArrayList;
import java.util.List;
import javax.sql.DataSource;

public final class BatchCustomerRepository {
    public record BatchOutcome(int[] updateCounts, List<Long> returnedKeys) {}

    private final DataSource dataSource;

    public BatchCustomerRepository(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public BatchOutcome insertBatch(List<CustomerInput> inputs)
            throws SQLException {
        if (inputs.isEmpty()) {
            return new BatchOutcome(new int[0], List.of());
        }

        String sql = """
                INSERT INTO customer (request_code, email)
                VALUES (?, ?)
                """;

        try (Connection connection = dataSource.getConnection()) {
            // Ví dụ sở hữu một Connection mới, không tham gia transaction
            // đang được caller hoặc framework quản lý.
            if (!connection.getAutoCommit()) {
                throw new SQLException("Ví dụ yêu cầu autoCommit=true ban đầu");
            }
            DatabaseMetaData meta = connection.getMetaData();
            if (!meta.supportsBatchUpdates()
                    || !meta.supportsGetGeneratedKeys()) {
                throw new SQLFeatureNotSupportedException(
                        "Driver không công bố đủ khả năng batch + keys");
            }

            connection.setAutoCommit(false);
            boolean ended = false;
            try {
                int[] counts;
                List<Long> keys = new ArrayList<>();

                try (PreparedStatement ps = connection.prepareStatement(
                        sql, new String[] {"id"})) {
                    for (CustomerInput input : inputs) {
                        ps.setString(1, input.requestCode());
                        ps.setString(2, input.email());
                        ps.addBatch();
                    }

                    counts = ps.executeBatch();
                    if (counts.length != inputs.size()) {
                        throw new SQLException("Số update count không khớp batch");
                    }
                    for (int count : counts) {
                        if (count != 1 && count != Statement.SUCCESS_NO_INFO) {
                            throw new SQLException(
                                    "Kết quả INSERT ngoài dự kiến: " + count);
                        }
                    }

                    try (ResultSet generated = ps.getGeneratedKeys()) {
                        while (generated.next()) {
                            long id = generated.getLong(1);
                            if (generated.wasNull()) {
                                throw new SQLException("Khóa sinh là NULL");
                            }
                            keys.add(id);
                        }
                    }
                }

                if (keys.size() != inputs.size()) {
                    throw new SQLException(
                            "Số khóa trả về không khớp số lệnh INSERT");
                }

                connection.commit();
                ended = true;
                // Khóa được trả theo thứ tự driver, không ghép với inputs[i].
                return new BatchOutcome(counts, List.copyOf(keys));
            } catch (SQLException | RuntimeException failure) {
                if (!ended) {
                    try {
                        connection.rollback();
                        ended = true;
                    } catch (SQLException rollbackFailure) {
                        failure.addSuppressed(rollbackFailure);
                    }
                }
                throw failure;
            } finally {
                if (ended) {
                    // Khôi phục cờ trước khi trả Connection về pool.
                    connection.setAutoCommit(true);
                }
                // Nếu rollback thất bại, đừng bật autoCommit vì có nguy cơ
                // commit một transaction đang ở trạng thái không rõ ràng.
            }
        }
    }

    public record CustomerInput(String requestCode, String email) {}
}
```

Ví dụ dùng Java 16+ cho `record` và SQL text block; phiên bản Java cũ có thể thay bằng lớp dữ liệu và chuỗi SQL thông thường. Giả định đầu vào đã được xác thực (không `null`, mã đối chiếu duy nhất, độ dài trường hợp lệ), cột `id` là `BIGINT` và driver hỗ trợ yêu cầu trả tên cột. Phương thức chủ động **rollback** khi số đếm hoặc số khóa không đạt kỳ vọng.

Chú ý ba giới hạn:

1. `keys.size() == inputs.size()` **không chứng minh đúng thứ tự**. API trên chỉ trả các khóa thu được; không nên ghép `inputs.get(i)` với `returnedKeys.get(i)` nếu chưa có bảo đảm từ driver.
2. `count == Statement.SUCCESS_NO_INFO` báo lệnh thành công nhưng không xác định số dòng. Mẫu chấp nhận trường hợp này nếu đồng thời nhận đủ khóa, nhưng hệ thống yêu cầu kiểm toán nghiêm ngặt có thể cần đối chiếu lại từng bản ghi.
3. Nếu `commit()` thất bại do mất kết nối, kết quả commit có thể **không xác định**. Rollback thử sau đó không chứng minh giao dịch chưa được commit; không tự chạy lại batch tạo dữ liệu khi thiếu cơ chế idempotency.

Trong ứng dụng có transaction manager, nên tách phần `addBatch/executeBatch/getGeneratedKeys` thành phương thức nhận `Connection` do tầng ngoài sở hữu, để tầng ngoài chịu trách nhiệm `commit`, `rollback` và cấu hình lại kết nối. Ví dụ trên dành cho một thao tác độc lập sở hữu transaction của mình.

## 7. Khi cần ánh xạ chính xác từng bản ghi với ID: hai phương án

### Phương án A: Chèn từng dòng và lấy khóa ngay trong cùng transaction

Nếu driver không bảo đảm thứ tự generated keys khi batch, cách dễ hiểu và có tính tương thích cao hơn là dùng một `PreparedStatement`, thực thi từng `INSERT` và lấy khóa **ngay sau mỗi lần**:

```java
String sql = """
        INSERT INTO customer (request_code, email)
        VALUES (?, ?)
        """;

try (PreparedStatement ps = connection.prepareStatement(
        sql, new String[] {"id"})) {
    for (CustomerInput input : inputs) {
        ps.setString(1, input.requestCode());
        ps.setString(2, input.email());

        if (ps.executeUpdate() != 1) {
            throw new SQLException("INSERT không ảnh hưởng đúng một hàng");
        }
        try (ResultSet keys = ps.getGeneratedKeys()) {
            if (!keys.next()) {
                throw new SQLException("Driver không trả id");
            }
            long id = keys.getLong(1);
            if (keys.wasNull() || keys.next()) {
                throw new SQLException("Số hoặc giá trị khóa không hợp lệ");
            }
            System.out.println(input.requestCode() + " => " + id);
        }
    }
}
```

Đoạn này nằm **bên trong transaction** có `Connection` còn mở; dùng cùng đối tượng `PreparedStatement` nhưng thực thi một hàng mỗi lần. Nó tạo ánh xạ theo chính câu `INSERT` vừa thực thi, không dựa vào thứ tự khóa trong batch. Đổi lại, có thể tăng số lượt giao tiếp với DB; vẫn cần xác minh driver có trả một khóa đúng kiểu cho từng lệnh.

### Phương án B: Giữ batch, ánh xạ bằng mã đối chiếu

Nếu tính năng batch nhanh và ổn định nhưng generated keys thiếu thứ tự đáng tin cậy, có thể chèn kèm một **`request_code` duy nhất**:

```sql
INSERT INTO customer (request_code, email)
VALUES (?, ?);

-- Thực hiện sau batch, trên cùng transaction:
SELECT id, request_code
FROM customer
WHERE request_code IN (?, ?, ?);
```

Khi đó chương trình tạo `Map<requestCode, id>` từ cặp cột **được DB trả cùng một hàng**, thay vì giả định thứ tự `ResultSet` trùng thứ tự `addBatch()`. Các giá trị `?` trong `IN` phải được bind bằng `PreparedStatement`; có thể xây số placeholder từ kích thước batch đã kiểm soát và chia thành các truy vấn nhỏ nếu vượt giới hạn tham số của DB.

**Điều kiện để phương án này đáng tin:** `request_code` phải duy nhất và được lưu cùng bản ghi ngay trong thao tác chèn; ứng dụng cần kiểm tra đúng số lượng mã tìm thấy, không có trùng hoặc thiếu, và query được chạy trong cùng transaction khi cần nhìn thấy các bản ghi chưa commit. Nếu ứng dụng cần retry an toàn sau mất kết nối ở thời điểm commit, mã yêu cầu có thể làm cơ sở chống trùng, nhưng nghiệp vụ vẫn phải thiết kế rõ cách xử lý bản ghi đã tồn tại.

Một số DB có cú pháp riêng cho `INSERT ... RETURNING ...` hoặc `OUTPUT` để lấy cột do DB tạo cùng mã đối chiếu. Các cú pháp này không có hành vi batch thống nhất qua mọi JDBC driver, nên cần xác minh trực tiếp trước khi dùng để thay thế.

## 8. Lỗi giữa batch và transaction: tránh tạo dữ liệu nửa chừng

Giả sử lô 100 khách hàng gặp ràng buộc `UNIQUE` tại phần tử thứ 40. Tùy driver, `BatchUpdateException.getUpdateCounts()` có thể chứa kết quả của 39 lệnh đầu hoặc báo thêm những lệnh phía sau đã được thực thi. Nếu `autoCommit=true`, một phần bản ghi có thể đã được commit trước khi exception được ném.

Với yêu cầu **“thành công toàn bộ hoặc không ghi gì”**:

1. Mượn `Connection` và bắt đầu transaction bằng `setAutoCommit(false)` khi được quyền sở hữu.
2. Chuẩn bị statement yêu cầu generated keys và thực thi batch.
3. Đọc **cả** update counts lẫn generated keys trước khi commit; xác minh các kỳ vọng phù hợp với driver.
4. Chỉ `commit()` khi mọi bước hợp lệ; khi `BatchUpdateException`/`SQLException` xảy ra, `rollback()` toàn bộ transaction nếu trạng thái cho phép.
5. Sau lỗi commit hoặc mất kết nối, xử lý kết quả chưa xác định bằng mã yêu cầu/idempotency và đối chiếu DB trước khi thử lại.

`clearBatch()` không hoàn tác thao tác đã chạy. `getGeneratedKeys()` cũng không cho biết chắc transaction đã commit hay chưa. Cả hai đều không thay thế `commit/rollback`.

**Giới hạn của transaction:** Một số thao tác, chẳng hạn DDL hoặc cơ chế đặc thù của DB, có thể có quy tắc commit riêng. Với ví dụ `INSERT` vào bảng transactional, cần chọn engine hỗ trợ transaction và kiểm tra hành vi rollback trên môi trường thật.

Nếu ứng dụng chia 10.000 bản ghi thành nhiều chunk, cần quyết định rõ:

- **Một transaction cho toàn công việc:** mọi chunk cùng commit/rollback, có thể giữ tài nguyên lâu và gây áp lực log/lock.
- **Mỗi chunk một transaction:** giảm phạm vi transaction nhưng cho phép hoàn thành một phần; phải có cơ chế ghi nhận chunk đã commit và chống chèn trùng khi retry.

Chỉ giảm kích thước chunk không tự giải quyết khả năng ánh xạ sai generated keys.

## 9. Ma trận kiểm tra tính khả chuyển giữa các driver

Trước khi phụ thuộc vào batch + generated keys trong production, kiểm tra trên **đúng DB, phiên bản server, driver, JDK và cấu hình kết nối**:

| Tình huống thử nghiệm | Điều cần xác minh |
| --- | --- |
| `supportsBatchUpdates()` và `supportsGetGeneratedKeys()` | Hai tính năng có được driver công bố hỗ trợ không? |
| `RETURN_GENERATED_KEYS` so với `new String[]{"id"}` | Overload nào trả được ID trong batch? Có exception không? |
| Batch 1, 2 và nhiều bản ghi | Số update counts, kiểu giá trị `1`/`SUCCESS_NO_INFO` và số khóa trả |
| Thứ tự đầu vào có `request_code` khác nhau | Đối chiếu `id` với `request_code` đã lưu trong DB; không chỉ so độ dài danh sách |
| Batch có lỗi unique/constraint ở giữa | Driver dừng hay tiếp tục? `getUpdateCounts()` chứa gì? Rollback có đủ không? |
| `INSERT` nhiều hàng trong **một SQL** so với nhiều lần `addBatch()` | Generated keys và update counts có cùng cách trả không? |
| Batch có trigger/default/sequence | Các cột sinh có được trả như mong đợi không? |
| Batch chia nhiều chunk | Có thiếu/trùng ID, sai ánh xạ, đổi thứ tự hoặc bị giới hạn số tham số không? |
| Mất kết nối lúc `executeBatch()` hoặc `commit()` | Có cách phát hiện kết quả đã ghi để retry an toàn không? |
| Nâng cấp driver hoặc thay DB | Các bảo đảm đã kiểm tra trước đây còn đúng không? |

Với test ánh xạ, đừng chỉ so `returnedKeys.size() == inputs.size()`. Hãy truy vấn ngược `SELECT id, request_code FROM customer` để xác định **mỗi khóa thuộc mã nào**, rồi so với giả định vị trí của driver. Lặp lại ở kích thước lô thực tế và khi driver bật tính năng tối ưu/rewrite batch, vì cơ chế thực thi có thể thay đổi.

Trong quá trình benchmark, đo tổng thời gian, số lượt round-trip, độ trễ p95/p99 và chi phí truy vấn kiểm tra đối chiếu. Lựa chọn “batch + truy vấn theo `request_code`” có thể nhanh hơn việc chèn từng hàng, nhưng kết quả phụ thuộc tải và DB; số liệu thực nghiệm mới quyết định.

## 10. Tổng kết lựa chọn triển khai

| Nhu cầu nghiệp vụ | Hướng triển khai |
| --- | --- |
| Chèn nhiều dòng, không cần khóa của từng dòng | `addBatch()`/`executeBatch()` với update counts và transaction |
| Cần thu thập khóa sinh, không cần gán cho từng input | Batch + `getGeneratedKeys()`, kiểm tra tính năng và số khóa |
| Cần ánh xạ `input → id` chính xác, driver có hợp đồng thứ tự rõ ràng | Có thể dùng batch keys theo thứ tự **sau khi** kiểm chứng trên driver cụ thể |
| Cần ánh xạ chính xác, driver không bảo đảm thứ tự | Batch + `request_code` duy nhất rồi truy vấn đối chiếu, hoặc chèn từng hàng và đọc key ngay |
| Batch có thể thất bại một phần | Transaction, xử lý `BatchUpdateException`, rollback và idempotency |
| Triển khai cho nhiều hệ quản trị | Xác minh từng DB/driver; giữ một đường fallback đã thử nghiệm |

**Ghi nhớ:** Batch giúp giảm chi phí gửi nhiều câu lệnh SQL, còn `getGeneratedKeys()` giúp lấy khóa do DB tạo. Khi kết hợp hai tính năng, **đừng suy ra ánh xạ ID từ thứ tự hoặc số lượng khóa khi driver chưa bảo đảm điều đó**. Kiểm tra `DatabaseMetaData`, đọc đúng `executeBatch()`/`BatchUpdateException`, giữ ranh giới transaction rõ ràng và dùng mã đối chiếu hoặc chèn từng hàng nếu nghiệp vụ yêu cầu liên kết khóa tuyệt đối chính xác.
