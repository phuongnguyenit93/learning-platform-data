# Đọc số hàng từng phần tử và `SUCCESS_NO_INFO` khi cập nhật theo lô

Trong Spring Framework Data Access, `JdbcTemplate.batchUpdate(...)` cho phép gửi nhiều lần thực thi SQL theo lô (batch) và trả về thông tin về **số hàng chịu tác động của từng phần tử**. Người học cần đọc đúng cả kết quả số không âm lẫn mã đặc biệt `Statement.SUCCESS_NO_INFO`: một thao tác đã thành công **không đồng nghĩa** với việc JDBC luôn biết chính xác bao nhiêu hàng chịu tác động.

## 1. Kết quả của batch là kết quả theo từng phần tử

Giả sử ứng dụng cần cập nhật trạng thái của ba đơn hàng theo thứ tự:

| Vị trí trong batch (index) | Đầu vào | SQL thực thi với tham số |
| --- | --- | --- |
| 0 | `id = 101`, `status = DONE` | `UPDATE orders SET status = ? WHERE id = ?` |
| 1 | `id = 102`, `status = DONE` | Cùng SQL, bộ tham số tiếp theo |
| 2 | `id = 103`, `status = DONE` | Cùng SQL, bộ tham số tiếp theo |

Nếu `batchUpdate` trả `int[] counts = {1, 0, -2}`, thì `counts[0]` dành cho phần tử đầu tiên, `counts[1]` dành cho phần tử thứ hai và `counts[2]` dành cho phần tử thứ ba. Các phần tử **không** đại diện cho từng bảng, từng câu lệnh SQL khác loại hay một tổng chung. Với API thông thường, thứ tự kết quả tương ứng thứ tự lệnh được thêm vào batch.

Quy trình khái quát:

1. Ứng dụng lập danh sách các bộ tham số theo thứ tự xác định.
2. `JdbcTemplate` dùng JDBC `PreparedStatement` để thực thi lô; việc driver có hỗ trợ batching thực sự hay Spring phải thực thi riêng từng lần tùy khả năng driver.
3. JDBC báo số hàng chịu tác động hoặc mã đặc biệt cho từng lệnh.
4. Ứng dụng đối chiếu `counts[i]` với phần tử đầu vào ở vị trí `i`, từ đó lập log, kiểm tra điều kiện nghiệp vụ hoặc tổng hợp thống kê.

**Chú ý:** Kết quả một lệnh đã chạy thành công chưa nói rằng giao dịch đã `COMMIT`. Nếu transaction về sau bị rollback, thay đổi có thể không được lưu vĩnh viễn.

## 2. Ý nghĩa chính xác của các giá trị

`java.sql.Statement` định nghĩa các hằng số quan trọng sau:

| Giá trị | Cách hiểu | Có thể kết luận điều gì? |
| --- | --- | --- |
| `0` | Lệnh xử lý thành công, số hàng được báo là 0 | Không có hàng chịu tác động theo cách driver/DBMS báo kết quả; có thể `WHERE` không khớp hoặc câu lệnh có điều kiện không thực hiện thay đổi. |
| Số dương, ví dụ `1` hoặc `5` | Lệnh thành công, số hàng chịu tác động được báo tương ứng | Có thể dùng số này để thống kê số hàng đã **biết**. |
| `Statement.SUCCESS_NO_INFO` = `-2` | Lệnh **thành công** nhưng driver **không cung cấp** số hàng chịu tác động | Không suy ra được 0, 1 hay bất kỳ con số cụ thể nào. |
| `Statement.EXECUTE_FAILED` = `-3` | Lệnh thực thi **thất bại** | Thường gặp trong mảng `getUpdateCounts()` khi `BatchUpdateException` xảy ra và driver vẫn tiếp tục các lệnh còn lại. |

Các quy tắc cần nhớ:

- `count >= 0`: thành công, có số hàng được báo.
- `count == Statement.SUCCESS_NO_INFO`: thành công nhưng **không biết số hàng**; không được cộng `-2` vào tổng.
- `count == Statement.EXECUTE_FAILED`: thất bại; không được xem đây là “thành công với số hàng âm”.
- Không dựa vào điều kiện `count > 0` để phân loại thành công, vì `0` và `-2` đều có thể biểu thị lệnh thành công.
- Không mặc định “mỗi phần tử update thành công phải có `count == 1`”. Một lệnh có thể tác động 0, 1 hoặc nhiều hàng, tùy SQL; `-2` còn khiến số lượng thực tế không quan sát được.

**Phân biệt hai lớp thông tin:** “lệnh thực thi thành công hay thất bại” và “lệnh tác động bao nhiêu hàng” là hai câu hỏi khác nhau. `SUCCESS_NO_INFO` trả lời câu thứ nhất là **thành công** nhưng để ngỏ câu thứ hai.

## 3. Đọc `int[]` qua `JdbcTemplate.batchUpdate`

Ví dụ sau thuộc một ứng dụng Spring có dependency `spring-jdbc`, đã cấu hình `DataSource`/`JdbcTemplate`, và bảng `orders(id, status)` tồn tại trong cơ sở dữ liệu. Đặt mã vào file `OrderBatchRepository.java` trong package được Spring quét; đây là lớp dùng trong dự án Spring, không phải chương trình chạy độc lập chỉ bằng JDK.

```java
import java.sql.PreparedStatement;
import java.sql.SQLException;
import java.util.List;

import org.springframework.jdbc.core.BatchPreparedStatementSetter;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

record StatusChange(long id, String status) {}

@Repository
public class OrderBatchRepository {
    private final JdbcTemplate jdbcTemplate;

    public OrderBatchRepository(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    public int[] updateStatuses(List<StatusChange> changes) {
        String sql = "UPDATE orders SET status = ? WHERE id = ?";

        return jdbcTemplate.batchUpdate(sql, new BatchPreparedStatementSetter() {
            @Override
            public void setValues(PreparedStatement ps, int i) throws SQLException {
                StatusChange item = changes.get(i);
                ps.setString(1, item.status());
                ps.setLong(2, item.id());
            }

            @Override
            public int getBatchSize() {
                return changes.size();
            }
        });
    }
}
```

Ý nghĩa của những dòng quan trọng:

- `getBatchSize()` cho biết số phần tử cần xử lý; `setValues(ps, i)` gắn tham số của phần tử thứ `i`.
- Hai dấu `?` lần lượt nhận `status` và `id`; dùng tham số để tránh nối trực tiếp giá trị vào SQL.
- Với một lệnh SQL và danh sách bộ tham số, phương thức trả `int[]`. Khi xử lý thành công, `counts[i]` tương ứng `changes.get(i)`.
- Giá trị trong mảng do driver JDBC báo lên; Spring **không tự biến** `-2` thành `1` hay chạy `SELECT COUNT(*)` để đoán số hàng.
- Nếu cập nhật bị lỗi, phương thức có thể ném `DataAccessException`; không xây dựng logic giả định mọi lần gọi đều trả một mảng thành công.

Ví dụ giả sử `changes` gồm ba phần tử và driver trả `{1, 0, Statement.SUCCESS_NO_INFO}`:

| Phần tử | `counts[i]` | Cách hiển thị đúng |
| --- | --- | --- |
| `changes.get(0)` | `1` | Đã thực thi, có 1 hàng được báo là chịu tác động. |
| `changes.get(1)` | `0` | Đã thực thi, có 0 hàng được báo là chịu tác động; cần xem quy tắc nghiệp vụ có chấp nhận không. |
| `changes.get(2)` | `-2` | Đã thực thi thành công, chưa biết số hàng; không phải 0 hàng và không phải lỗi. |

## 4. Chương trình Java 17+ đọc từng kết quả và tổng hợp đúng

Ví dụ này **chạy độc lập bằng JDK**, cố ý mô phỏng một mảng count đã nhận từ JDBC để kiểm tra cách đọc kết quả mà không cần cấu hình database hay Spring. Lưu mã vào `BatchCountReader.java`.

```java
import java.sql.Statement;

public final class BatchCountReader {
    public static void main(String[] args) {
        // Dữ liệu mô phỏng do executeBatch()/batchUpdate() trả về.
        int[] counts = {1, 0, Statement.SUCCESS_NO_INFO, 3};

        long knownRows = 0;
        int unknownSuccesses = 0;

        for (int i = 0; i < counts.length; i++) {
            int count = counts[i];

            if (count >= 0) {
                knownRows += count;
                System.out.printf("[%d] OK: %d hàng%n", i, count);
            } else if (count == Statement.SUCCESS_NO_INFO) {
                unknownSuccesses++;
                System.out.printf("[%d] OK: chưa biết số hàng%n", i);
            } else if (count == Statement.EXECUTE_FAILED) {
                System.out.printf("[%d] LỖI: phần tử batch thất bại%n", i);
            } else {
                throw new IllegalStateException("Mã count không xác định: " + count);
            }
        }

        System.out.printf(
                "Known rows: %d; unknown successes: %d%n",
                knownRows, unknownSuccesses);
    }
}
```

Biên dịch và chạy tại thư mục chứa file (đặt encoding UTF-8 để giữ chữ tiếng Việt trong source):

```bash
javac -encoding UTF-8 BatchCountReader.java
java BatchCountReader
```

Kết quả:

```text
[0] OK: 1 hàng
[1] OK: 0 hàng
[2] OK: chưa biết số hàng
[3] OK: 3 hàng
Known rows: 4; unknown successes: 1
```

Tổng `knownRows = 1 + 0 + 3 = 4` chỉ là **tổng của những count đã biết**. Trong ví dụ có một lệnh thành công nhưng chưa rõ số hàng, nên **không thể khẳng định tổng thực tế của cả lô là 4**. Dùng `long` để cộng các số không âm nhằm giảm nguy cơ tràn khi tổng nhiều kết quả `int`, nhưng `long` cũng không giúp khôi phục thông tin bị thiếu bởi `-2`.

Mẫu kiểm tra tối thiểu khi xử lý kết quả:

```java
if (count == Statement.SUCCESS_NO_INFO) {
    // Thành công; số hàng là UNKNOWN.
} else if (count == Statement.EXECUTE_FAILED) {
    // Thất bại; thường đọc ở kết quả ngoại lệ batch.
} else if (count >= 0) {
    // Thành công; count là số hàng driver báo.
} else {
    // Giá trị không mong đợi: cần kiểm tra driver/API.
}
```

Đoạn `if` này là **mảnh mã minh họa** bên trong vòng lặp đã có biến `count`; tự nó không phải một chương trình độc lập.

## 5. Khi Spring trả `int[][]` thay vì `int[]`

Spring còn có overload:

`JdbcTemplate.batchUpdate(String sql, Collection<T> batchArgs, int batchSize, ParameterizedPreparedStatementSetter<T> pss)`

Overload này chia đầu vào thành các nhóm kích thước tối đa `batchSize` và trả **`int[][]`**: mảng ngoài là các nhóm, mảng trong là kết quả của các phần tử trong từng nhóm.

Ví dụ đoạn mã dưới đây có thể đặt **bên trong một method của `OrderBatchRepository`** ở trên, nơi đã có biến `jdbcTemplate` và `List<StatusChange> changes`:

```java
int[][] groups = jdbcTemplate.batchUpdate(
        "UPDATE orders SET status = ? WHERE id = ?",
        changes,
        200,
        (ps, change) -> {
            ps.setString(1, change.status());
            ps.setLong(2, change.id());
        });

int originalIndex = 0;
for (int group = 0; group < groups.length; group++) {
    for (int offset = 0; offset < groups[group].length; offset++) {
        int count = groups[group][offset];
        StatusChange item = changes.get(originalIndex++);
        // Đối chiếu item với count, kiểm tra -2 trước khi cộng tổng.
    }
}
```

Giả sử có 5 phần tử, kích thước nhóm 2 và tất cả nhóm hoàn tất: một hình dạng trả về có thể là `{{1, -2}, {0, 1}, {1}}`. Cách đọc theo thứ tự gốc là `1, -2, 0, 1, 1`; tuyệt đối không nhầm `groups.length == 3` là ba hàng chịu tác động, hoặc coi `groups[0][1]` là “phần tử số 1 trong toàn bộ request” của những nhóm khác.

Khi mapping kết quả đến đối tượng đầu vào, hãy dùng danh sách có thứ tự ổn định. Không tự suy diễn số phần tử thành công của toàn bộ request nếu batch ném ngoại lệ giữa chừng.

## 6. `SUCCESS_NO_INFO` ảnh hưởng thế nào đến kiểm tra nghiệp vụ?

Xét yêu cầu: cập nhật **đúng một** bản ghi theo `id` và `version` để phát hiện xung đột optimistic locking.

```sql
UPDATE orders
SET status = ?, version = version + 1
WHERE id = ? AND version = ?
```

Ứng dụng có thể đặt quy tắc như sau:

- `count == 1`: driver đã báo đúng một hàng; điều kiện đếm được thỏa mãn.
- `count == 0`: driver báo không có hàng bị tác động; có thể bản ghi không tồn tại hoặc phiên bản đã thay đổi. Cần xác định theo ngữ cảnh.
- `count > 1`: bất thường nếu khóa/điều kiện thiết kế chỉ cho phép một bản ghi.
- `count == SUCCESS_NO_INFO`: **không đủ bằng chứng** để khẳng định “đúng một hàng”, dù lệnh được báo thành công.

Nếu yêu cầu nghiệp vụ **bắt buộc chứng minh** từng thao tác ảnh hưởng đúng một hàng, không được chuyển `SUCCESS_NO_INFO` thành `1` để vượt kiểm tra. Cân nhắc cập nhật riêng để có count thích hợp, dùng cơ chế kiểm soát version của tầng dữ liệu, hoặc thực hiện xác minh DB phù hợp với transaction/isolation và quy tắc của hệ quản trị. Truy vấn lại sau khi cập nhật không tự động loại bỏ mọi vấn đề đồng thời.

Ngược lại, nếu nghiệp vụ chỉ cần biết batch thực thi thành công, thì `-2` không phải lý do để tự động báo thất bại. Quy tắc kiểm tra phải phù hợp mục đích, khả năng của JDBC driver và yêu cầu tính nhất quán dữ liệu.

## 7. Ngoại lệ batch và `EXECUTE_FAILED`

Với JDBC thuần, khi một lệnh trong `executeBatch()` thất bại, driver ném `java.sql.BatchUpdateException`. Có hai kiểu hành vi theo driver:

1. **Dừng ở lệnh lỗi:** `getUpdateCounts()` chỉ chứa kết quả của các lệnh thành công **trước** lỗi. Nếu đã thêm 4 lệnh mà mảng dài 2, **không** được tự kết luận 2 lệnh còn lại đều đã chạy và thất bại; chúng có thể chưa được thực thi.
2. **Tiếp tục sau lỗi:** mảng `getUpdateCounts()` có thể chứa kết quả cho **mọi** lệnh đã thêm; vị trí thất bại có `Statement.EXECUTE_FAILED` (`-3`), vị trí thành công không biết row count vẫn có thể là `Statement.SUCCESS_NO_INFO` (`-2`).

Ví dụ, với 3 lệnh, `{1, -3, -2}` trong `BatchUpdateException.getUpdateCounts()` của driver tiếp tục sau lỗi mang nghĩa: lệnh 0 có 1 hàng được báo, lệnh 1 thất bại, lệnh 2 thành công nhưng không biết số hàng. Mảng này **không** có nghĩa toàn bộ lô đã thành công. Trạng thái dữ liệu cuối cùng còn phụ thuộc transaction và rollback.

Đoạn JDBC minh họa để xử lý ngoại lệ (giả định `PreparedStatement ps` đã được tạo và các lệnh đã được `addBatch()`):

```java
try {
    int[] counts = ps.executeBatch();
    // Chỉ đến đây khi executeBatch() trả về bình thường.
} catch (java.sql.BatchUpdateException ex) {
    int[] partialCounts = ex.getUpdateCounts();
    // Kiểm tra độ dài và từng mã; không tự suy luận
    // những lệnh chưa có kết quả đã được thực thi.
    throw ex;
}
```

Với `JdbcTemplate`, lỗi SQL thường được Spring chuyển thành ngoại lệ thuộc `DataAccessException`; ngoại lệ gốc JDBC có thể nằm trong chuỗi nguyên nhân để phục vụ chẩn đoán. Không dựa vào một subclass ngoại lệ gốc duy nhất cho mọi driver, và không nuốt ngoại lệ rồi dùng mảng count dở dang như kết quả toàn phần.

Trong Spring, `@Transactional` ở service phù hợp giúp quản lý transaction; mặc định ngoại lệ runtime lan ra ngoài method transactional dẫn đến rollback theo quy tắc Spring, nhưng còn phụ thuộc transaction manager, cơ sở dữ liệu và kiểu thao tác. Việc batch trả `0` hoặc `-2` **không tự kích hoạt rollback**. Nếu ứng dụng bắt một lỗi rồi tiếp tục, cần quyết định rõ có rollback hay không; không mặc định batch là nguyên tử chỉ vì được gửi thành một lô.

Với số hàng có thể vượt `Integer.MAX_VALUE`, JDBC còn có `executeLargeBatch()` trả `long[]` và `BatchUpdateException.getLargeUpdateCounts()`. Các mã `SUCCESS_NO_INFO` và `EXECUTE_FAILED` vẫn có cùng ý nghĩa.

## 8. Logging, monitoring và kiểm thử cho đúng

Khi ghi nhận số liệu batch, nên tách ít nhất bốn số liệu:

- **Số lệnh yêu cầu:** kích thước danh sách đầu vào.
- **Số hàng đã biết:** tổng những `count >= 0`, không cộng các mã âm.
- **Số lệnh thành công nhưng không biết số hàng:** số phần tử `count == -2`.
- **Tình trạng lỗi:** có ngoại lệ batch hay mã `-3` trong kết quả chẩn đoán hay không, cùng vị trí và SQL state/cause khi có.

Ví dụ log phù hợp: `submitted=4, knownAffectedRows=4, successCountUnknown=1, failure=none`. Tránh log `totalAffectedRows=4` khi còn `-2`, bởi tên trường này khẳng định điều mà hệ thống chưa biết. Cũng không đánh đồng số **lệnh** thành công với tổng số **hàng** chịu tác động.

Các ca kiểm thử nên có:

| Kết quả | Kỳ vọng |
| --- | --- |
| `{1, 1, 1}` | 3 phần tử có count xác định, tổng đã biết = 3. |
| `{1, 0, 2}` | Không đánh dấu `0` là lỗi JDBC; tổng đã biết = 3. |
| `{1, -2, 2}` | Có 1 thành công không rõ số hàng; tổng đã biết = 3, tổng thực tế không xác định. |
| `BatchUpdateException` kèm `{1, -3, -2}` | Có lỗi ở phần tử 1; không báo toàn batch thành công. |
| `BatchUpdateException` kèm mảng tiền tố `{1}` | Biết lệnh đầu đã được báo thành công trước lỗi; không đoán trạng thái các lệnh còn lại. |

Để kiểm thử hành vi thực tế, dùng DB/driver giống môi trường triển khai nếu có thể: từng RDBMS và JDBC driver có thể báo affected rows khác nhau trong những trường hợp như update cùng giá trị, `UPSERT`, `ON CONFLICT DO NOTHING`, các cấu hình rewrite batch, hoặc việc driver có trả count cụ thể hay `-2`. Kiểm thử trên mảng giả giúp xác minh **logic giải mã**; integration test mới xác minh **cách driver trả kết quả**.

## 9. Các nhầm lẫn thường gặp

**“`-2` là lỗi?”** Không. `Statement.SUCCESS_NO_INFO` có nghĩa thành công nhưng không có số hàng; lỗi batch được biểu thị bằng ngoại lệ và trong một số trường hợp bằng `EXECUTE_FAILED`.

**“Mảng `{1, -2, 1}` chứng tỏ có hai hàng được cập nhật?”** Chỉ biết hai count bằng 1, còn count ở giữa là chưa biết. Tổng đã biết bằng 2, tổng của cả batch chưa biết.

**“`count == 0` chắc chắn là thao tác không thực thi?”** Không. Lệnh có thể được thực thi và báo 0 hàng chịu tác động; cần hiểu điều kiện SQL và cách driver/DBMS xác định affected rows.

**“Có thể cộng tất cả phần tử bằng `IntStream.sum()`?”** Không khi có `-2` hoặc `-3`. Chỉ cộng những count không âm và ghi riêng số kết quả chưa xác định, lỗi.

**“Bắt được `BatchUpdateException` rồi có thể retry toàn bộ ngay?”** Không mặc định. Một số lệnh có thể đã được thực thi; trạng thái transaction và tính idempotent của lệnh quyết định cách phục hồi. Xử lý transaction, rollback và retry có chủ đích.

## 10. Ghi nhớ và tài liệu tra cứu

Khi nhận kết quả từ batch, hãy **ghép phần tử theo thứ tự**, **kiểm tra hằng số JDBC trước khi tổng hợp** và **giữ trạng thái “chưa biết số hàng” thành một trạng thái riêng**. `SUCCESS_NO_INFO` có nghĩa là *success*, nhưng số hàng *no info*. Nếu bài toán yêu cầu xác nhận “chính xác một hàng”, kết quả này cần được xử lý như **chưa đủ bằng chứng**, không được ép về `1`.

Tài liệu chính thức để đối chiếu:

- JDBC `Statement.executeBatch()` và các hằng số: https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/Statement.html
- JDBC `BatchUpdateException.getUpdateCounts()`: https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/BatchUpdateException.html
- Spring Framework, *JDBC Batch Operations*: https://docs.spring.io/spring-framework/reference/data-access/jdbc/advanced.html
- Spring Framework, `JdbcTemplate.batchUpdate(...)` JavaDoc: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jdbc/core/JdbcTemplate.html