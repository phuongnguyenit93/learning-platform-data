# Gom bộ tham số bằng `PreparedStatement.addBatch()` trong JDBC

Khi ứng dụng Java cần chèn hàng trăm dòng hóa đơn, cập nhật tồn kho cho nhiều sản phẩm hoặc ghi một nhóm sự kiện, cách đơn giản nhất là gọi `PreparedStatement.executeUpdate()` một lần cho mỗi bản ghi. Cách này đúng về mặt chức năng nhưng thường tạo nhiều lượt trao đổi giữa ứng dụng, JDBC driver và cơ sở dữ liệu. Với **cùng một cấu trúc SQL, chỉ thay đổi giá trị tham số**, JDBC cung cấp cơ chế *batch processing*: gọi `PreparedStatement.addBatch()` để gom nhiều bộ tham số, sau đó dùng `executeBatch()` để yêu cầu thực thi cả nhóm.

Bài thuộc chương **Xử lý theo lô** của module **JDBC**, tập trung vào việc gom **bộ tham số** của `PreparedStatement`, quản lý kích thước batch, phân tích kết quả và phối hợp transaction. Các API liên quan gồm `DataSource`, `Connection`, `PreparedStatement`, `Statement`, `BatchUpdateException` và `SQLException`. Không cần ORM hoặc thư viện batching riêng.

Sau bài học, bạn sẽ có thể:

- Phân biệt `addBatch()`, `executeBatch()`, `clearBatch()` và `clearParameters()`.
- Gom nhiều bộ giá trị vào **một câu SQL tham số hóa** và thực thi theo từng nhóm.
- Đọc `int[]` kết quả, xử lý `SUCCESS_NO_INFO`, `EXECUTE_FAILED` và `BatchUpdateException`.
- Đặt các batch trong một transaction với `commit()`/`rollback()` phù hợp yêu cầu nguyên tử.
- Chọn batch size và tránh những giả định sai về thứ tự khóa sinh, tốc độ hay hành vi driver.

## 1. Từ từng câu lệnh riêng lẻ đến batch tham số

Giả sử cần chèn ba dòng điều chỉnh tồn kho vào cùng bảng:

```sql
INSERT INTO stock_adjustment
    (request_id, line_no, product_sku, quantity_delta)
VALUES (?, ?, ?, ?);
```

Mỗi dòng có `request_id`, thứ tự dòng, mã sản phẩm và lượng thay đổi khác nhau. Cấu trúc SQL hoàn toàn giống nhau. Nếu gọi `executeUpdate()` ba lần, ứng dụng yêu cầu driver thực thi lần lượt ba bộ giá trị; nếu dùng batch, ứng dụng chuyển các bộ giá trị vào danh sách lệnh chờ:

```text
PreparedStatement: INSERT ... VALUES (?, ?, ?, ?)

setString/setInt ("REQ-7", 1, "SKU-A", +5)  -> addBatch()
setString/setInt ("REQ-7", 2, "SKU-B", -2)  -> addBatch()
setString/setInt ("REQ-7", 3, "SKU-C", +8)  -> addBatch()
                                               |
                                         executeBatch()
                                               |
                                       JDBC driver / DBMS
                                               |
                                        int[] kết quả
```

`addBatch()` **đưa bộ tham số hiện tại vào batch**; nó không phải lệnh commit, cũng không có nghĩa từng hàng đã được ghi vào DB ngay lúc đó. `executeBatch()` mới là thao tác yêu cầu thực thi những lệnh đang chờ. Sau khi một lượt `executeBatch()` hoàn tất, batch lệnh của statement được xóa theo hợp đồng JDBC; vẫn có thể gán tham số mới và tiếp tục gom batch khác trên cùng `PreparedStatement`.

### Ví dụ tối thiểu

```java
String sql = """
        INSERT INTO stock_adjustment
            (request_id, line_no, product_sku, quantity_delta)
        VALUES (?, ?, ?, ?)
        """;

try (Connection connection = dataSource.getConnection();
     PreparedStatement statement = connection.prepareStatement(sql)) {

    statement.setString(1, "REQ-7");
    statement.setInt(2, 1);
    statement.setString(3, "SKU-A");
    statement.setInt(4, 5);
    statement.addBatch(); // Bộ tham số thứ nhất.

    statement.setString(1, "REQ-7");
    statement.setInt(2, 2);
    statement.setString(3, "SKU-B");
    statement.setInt(4, -2);
    statement.addBatch(); // Bộ tham số thứ hai.

    int[] results = statement.executeBatch();
    System.out.println("Số kết quả: " + results.length); // Thông thường: 2.
}
```

Ví dụ trên minh họa cách gom tham số, nhưng **chưa quản lý một transaction bao trùm nhiều batch**. Nếu DB để `autoCommit = true`, hành vi khi một phần batch thất bại có thể khác nhau giữa driver và DBMS. Đối với một yêu cầu ghi nhiều dòng cần *hoặc tất cả, hoặc không dòng nào*, hãy dùng mô hình transaction ở phần 4.

## 2. `addBatch()` khác gì `executeBatch()` và `clearBatch()`?

| API | Vai trò | Điều cần nhớ |
| --- | --- | --- |
| `setInt`, `setString`, `setBigDecimal`, ... | Gán tham số cho lần thêm lệnh hiện tại | Dùng chỉ số tham số bắt đầu từ **1** |
| `PreparedStatement.addBatch()` | Ghi nhận bộ tham số hiện tại thành một lệnh chờ | Có thể gọi nhiều lần trước khi thực thi |
| `PreparedStatement.executeBatch()` | Yêu cầu thực thi nhóm lệnh và trả `int[]` | Có thể ném `BatchUpdateException` nếu một lệnh lỗi |
| `PreparedStatement.clearBatch()` | Hủy các lệnh đã gom nhưng chưa thực thi | Không hoàn tác các lệnh đã chạy trên DB |
| `PreparedStatement.clearParameters()` | Xóa **giá trị tham số hiện tại** của statement | Không dùng để xóa các lệnh đã lưu trong batch |
| `Connection.commit()` / `rollback()` | Xác nhận / hoàn tác transaction | Không phải API thay thế cho `executeBatch()` |

Một khác biệt dễ gây lỗi là **tham số được giữ giữa các lần gán**. Nếu lần đầu gán đủ bốn vị trí nhưng lần sau quên gán vị trí 4, giá trị trước đó có thể vẫn còn trong trạng thái tham số của `PreparedStatement`. Quy tắc thực tế là **gán toàn bộ placeholder của mỗi dòng trước khi gọi `addBatch()`**, nhất là khi một số cột được phép `NULL`.

```java
// Với một cột VARCHAR cho phép NULL:
if (note == null) {
    statement.setNull(5, java.sql.Types.VARCHAR);
} else {
    statement.setString(5, note);
}
statement.addBatch();
```

Đoạn minh họa này giả định câu SQL có **tham số thứ 5** cho `note`; không áp dụng trực tiếp cho câu `INSERT` bốn tham số ở trên. `setNull` cho phép khai báo rõ kiểu SQL của giá trị `NULL` theo hợp đồng cột và khả năng chuyển kiểu của driver.

Khi dùng `PreparedStatement`, cần phân biệt `addBatch()` **không đối số** với `Statement.addBatch(String sql)`. Biến thể có chuỗi SQL là dành cho `Statement` thông thường và không phải cách gom nhiều bộ tham số của một `PreparedStatement` đã biên dịch SQL. Mục tiêu của bài là giữ nguyên câu SQL, chỉ thay giá trị tham số bằng các `setXxx` rồi gọi `addBatch()`.

## 3. Chuẩn bị bảng và mô hình dữ liệu

Ví dụ chính ghi một nhóm thay đổi tồn kho phục vụ kiểm toán. Mỗi yêu cầu có `request_id` và nhiều dòng `line_no`. Đây là **nhật ký thay đổi**, chưa phải thao tác cập nhật trực tiếp số lượng tồn kho; việc áp dụng thay đổi lên bảng tồn kho thực tế là một quyết định nghiệp vụ khác.

```sql
CREATE TABLE stock_adjustment (
    request_id     VARCHAR(64) NOT NULL,
    line_no        INTEGER NOT NULL,
    product_sku    VARCHAR(64) NOT NULL,
    quantity_delta INTEGER NOT NULL CHECK (quantity_delta <> 0),
    PRIMARY KEY (request_id, line_no)
);
```

Khóa chính ghép `(request_id, line_no)` giúp xác định duy nhất từng dòng trong một yêu cầu. Nếu hai yêu cầu dùng cùng `request_id`, chúng có thể tranh chấp khóa chính; việc tự động xử lý yêu cầu trùng (*idempotency*) cần thiết kế riêng, không được mặc định batch sẽ bỏ qua dòng trùng.

Đầu vào Java nên có kiểu rõ ràng. Dùng `record` (Java 16+) để biểu diễn một dòng không đổi sau khi tạo:

```java
import java.util.Objects;

public record AdjustmentLine(String sku, int quantityDelta) {
    public AdjustmentLine {
        Objects.requireNonNull(sku, "sku");
        if (sku.isBlank() || sku.length() > 64) {
            throw new IllegalArgumentException("sku must contain 1..64 characters");
        }
        if (quantityDelta == 0) {
            throw new IllegalArgumentException("quantityDelta must not be zero");
        }
    }
}
```

Các kiểm tra này chỉ phục vụ ví dụ. Ứng dụng thật còn phải xác định liệu SKU có phân biệt chữ hoa/chữ thường, có cần chuẩn hóa Unicode hay có bị hạn chế ký tự; không tự ý sửa chuỗi trong mapper chỉ để mã chạy qua kiểm tra DB.

## 4. Ví dụ đầy đủ: gom tối đa 500 bộ tham số mỗi lượt

Một batch khổng lồ có thể chiếm nhiều bộ nhớ ở ứng dụng hoặc driver và gặp giới hạn số tham số/kích thước gói tin của DB. Thay vì gom mọi dòng rồi mới thực thi, có thể **chia thành từng nhóm có giới hạn** trên cùng `PreparedStatement` và cùng transaction.

Đoạn `AdjustmentBatchWriter` sau nhận một `requestId` và danh sách dòng, gom tối đa `500` bộ tham số/lượt, gọi `executeBatch()` khi nhóm đầy, rồi xử lý nhóm cuối cùng nếu còn dữ liệu. Nó chỉ `commit()` **sau khi tất cả các nhóm thành công**.

```java
import java.sql.BatchUpdateException;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;
import java.sql.Statement;
import java.util.List;
import java.util.Objects;
import javax.sql.DataSource;

public final class AdjustmentBatchWriter {
    private static final int BATCH_SIZE = 500;

    private static final String INSERT = """
            INSERT INTO stock_adjustment
                (request_id, line_no, product_sku, quantity_delta)
            VALUES (?, ?, ?, ?)
            """;

    private final DataSource dataSource;

    public AdjustmentBatchWriter(DataSource dataSource) {
        this.dataSource = Objects.requireNonNull(dataSource, "dataSource");
    }

    public int insert(String requestId, List<AdjustmentLine> input)
            throws SQLException {
        Objects.requireNonNull(requestId, "requestId");
        if (requestId.isBlank() || requestId.length() > 64) {
            throw new IllegalArgumentException("Invalid requestId");
        }

        List<AdjustmentLine> lines = List.copyOf(
                Objects.requireNonNull(input, "input"));
        if (lines.isEmpty()) {
            return 0; // Không mở connection khi không có dòng nào.
        }

        try (Connection connection = dataSource.getConnection()) {
            connection.setAutoCommit(false);
            try {
                try (PreparedStatement statement = connection.prepareStatement(INSERT)) {
                    int pending = 0;

                    for (int i = 0; i < lines.size(); i++) {
                        AdjustmentLine line = lines.get(i);

                        // Gán đủ bốn tham số cho MỖI bộ.
                        statement.setString(1, requestId);
                        statement.setInt(2, i + 1);
                        statement.setString(3, line.sku());
                        statement.setInt(4, line.quantityDelta());
                        statement.addBatch();
                        pending++;

                        if (pending == BATCH_SIZE) {
                            verifyCounts(statement.executeBatch(), pending);
                            pending = 0;
                        }
                    }

                    if (pending > 0) {
                        verifyCounts(statement.executeBatch(), pending);
                    }
                }

                // Chỉ commit sau khi mọi batch đã chạy thành công.
                connection.commit();
                return lines.size();
            } catch (SQLException | RuntimeException failure) {
                try {
                    connection.rollback();
                } catch (SQLException rollbackFailure) {
                    failure.addSuppressed(rollbackFailure);
                }
                throw failure;
            }
        }
    }

    private static void verifyCounts(int[] counts, int expected)
            throws SQLException {
        if (counts.length != expected) {
            throw new SQLException("Unexpected batch result length: "
                    + counts.length + " instead of " + expected);
        }

        for (int count : counts) {
            if (count != 1 && count != Statement.SUCCESS_NO_INFO) {
                throw new SQLException("Unexpected INSERT count: " + count);
            }
        }
    }
}
```

Ví dụ gọi:

```java
import java.util.List;

AdjustmentBatchWriter writer = new AdjustmentBatchWriter(dataSource);

int inserted = writer.insert("REQ-2026-001", List.of(
        new AdjustmentLine("SKU-A", 5),
        new AdjustmentLine("SKU-B", -2),
        new AdjustmentLine("SKU-C", 8)));

System.out.println("Số dòng đã yêu cầu thêm thành công: " + inserted);
// 3, nếu mọi executeBatch và commit hoàn tất thành công.
```

Ví dụ dùng Java 17+ để hỗ trợ `record` và *text block* `"""`. Nó giả định `dataSource` đã được cấu hình, DB hỗ trợ transaction và driver hỗ trợ batch với `PreparedStatement`. Một số DB có cú pháp `CHECK` hoặc giới hạn độ dài `VARCHAR` khác nhau; cần điều chỉnh DDL theo môi trường thực tế. Mã chủ động ném lỗi nếu nhận kết quả cập nhật không phù hợp với giả định “mỗi bộ tham số thêm đúng một hàng”, thay vì im lặng báo thành công.

### Phân tích các điểm quan trọng

| Vị trí | Ý nghĩa |
| --- | --- |
| `List.copyOf(input)` | Cố định danh sách đầu vào trong lúc tạo batch; các phần tử `AdjustmentLine` là record bất biến |
| `setString` / `setInt` | Gán các giá trị vào placeholder của **cùng một** câu SQL |
| `statement.addBatch()` | Ghi nhận bộ tham số vừa gán, chưa commit dữ liệu |
| `pending == BATCH_SIZE` | Giới hạn số bộ tham số đang chờ; tránh gom vô hạn |
| `statement.executeBatch()` | Thực thi một nhóm đã gom và trả kết quả |
| `verifyCounts(...)` | Xác nhận kết quả theo hợp đồng một `INSERT`/một hàng |
| `connection.commit()` | Xác nhận **tất cả** các nhóm trong một giao dịch |
| `connection.rollback()` | Cố gắng hoàn tác toàn bộ nhóm đã thực thi nhưng chưa commit khi thất bại |

Tại mỗi lượt, `pending` đếm **số bộ tham số đang chờ**, không phải tổng số dòng đã commit. Sau khi `executeBatch()` thành công, batch lệnh của statement được xóa và `pending` được đặt lại về 0. Những lệnh đã thực thi trong nhóm trước vẫn đang là **thay đổi chưa commit** của transaction; nếu nhóm sau lỗi, `rollback()` vẫn có thể hoàn tác chúng trên DB hỗ trợ giao dịch.

Giá trị trả về `lines.size()` là **số bộ tham số được xác nhận thành công theo chính sách của phương thức** sau khi `commit` hoàn tất, không phải tổng được tính từ `int[]`. Điều này cần phân biệt bởi `SUCCESS_NO_INFO` cho biết driver báo lệnh thành công nhưng không cung cấp số hàng bị tác động. Nếu nghiệp vụ cần đếm số hàng thực tế một cách chính xác, phải chọn một hợp đồng DB/driver phù hợp hoặc đối chiếu bằng truy vấn sau commit; không tự quy đổi `SUCCESS_NO_INFO` thành “đúng một hàng đã thay đổi” trong mọi loại câu SQL.

## 5. Hiểu `executeBatch()` trả gì?

Khi chạy thành công, `PreparedStatement.executeBatch()` trả về `int[]`. Theo hợp đồng JDBC, các phần tử tương ứng với những lệnh trong batch theo thứ tự chúng được thêm, nhưng một driver có thể thông báo **không biết số hàng tác động** thay vì một con số cụ thể.

Các giá trị thường thấy:

| Giá trị trong `int[]` | Ý nghĩa | Cách hiểu trong ví dụ `INSERT` |
| --- | --- | --- |
| `1` | Một hàng đã bị tác động | Phù hợp kỳ vọng thêm một dòng |
| `0` | Không có hàng nào bị tác động | Bất thường với `INSERT` mẫu; xử lý lỗi |
| `2` hoặc số dương khác | Số hàng bị tác động mà driver thông báo | Bất thường với hợp đồng một dòng; cần xem lại SQL/driver |
| `Statement.SUCCESS_NO_INFO` (`-2`) | Lệnh thành công nhưng driver không cung cấp số hàng | Chấp nhận thành công mà không suy diễn số hàng cụ thể |
| `Statement.EXECUTE_FAILED` (`-3`) | Lệnh trong batch thất bại | Báo lỗi và rollback nếu yêu cầu nguyên tử |

Ví dụ kiểm tra kết quả một batch:

```java
int[] counts = statement.executeBatch();
for (int count : counts) {
    if (count == Statement.SUCCESS_NO_INFO) {
        // Thành công, không biết chính xác số hàng.
    } else if (count == Statement.EXECUTE_FAILED) {
        throw new SQLException("A batch command failed");
    } else if (count != 1) {
        throw new SQLException("Expected one inserted row, got " + count);
    }
}
```

`EXECUTE_FAILED` thường được quan sát trong **mảng đếm của `BatchUpdateException` khi driver tiếp tục thực thi sau một lỗi**; đường thực thi thành công thông thường không cần xuất hiện trạng thái này. Không nên lấy tổng các số nguyên trong mảng vì giá trị âm mang ý nghĩa trạng thái, không phải số hàng bị tác động.

### Khi gặp `BatchUpdateException`

Nếu một lệnh trong batch thất bại, driver có thể ném `BatchUpdateException` (một loại `SQLException`). Lúc đó, không có một quy tắc chung rằng DB đã tự rollback **toàn bộ** những lệnh chạy trước đó. JDBC cho phép driver dừng ngay tại lỗi hoặc tiếp tục những lệnh phía sau; kết quả chi tiết tùy cách driver thông báo.

```java
try {
    int[] counts = statement.executeBatch();
    verifyCounts(counts, expected);
} catch (BatchUpdateException failure) {
    int[] partialCounts = failure.getUpdateCounts();
    // Phục vụ chẩn đoán: một số lệnh có thể đã chạy trước lỗi.
    // Không coi những lệnh có count = 1 là đã được commit.
    // Tầng sở hữu Connection phải rollback theo hợp đồng nghiệp vụ.
    throw failure;
}
```

Đoạn trên giả định đặt trong lớp có phương thức `verifyCounts` như ví dụ chính và các biến `statement`, `expected` đã được khai báo. Nó minh họa cách **đọc thông tin chẩn đoán** nhưng vẫn giữ lỗi cho tầng transaction. Nếu muốn dùng kiểu đếm `long[]` cho số cập nhật lớn, JDBC còn cung cấp `executeLargeBatch()` và `BatchUpdateException.getLargeUpdateCounts()` trên driver hỗ trợ; không cần đổi sang API này chỉ vì danh sách batch có nhiều phần tử, vì `int[]` biểu diễn **số hàng mỗi lệnh**, không phải độ dài danh sách batch.

**Quy tắc vận hành:** Khi yêu cầu phải ghi đủ cả lô, lỗi ở bất kỳ bộ tham số nào đều khiến thao tác bị coi là thất bại. Tầng sở hữu transaction sẽ rollback và trả lỗi. Không tự lặp lại riêng các bộ tham số “đang lỗi” ngay trong một transaction có trạng thái chưa rõ, vì một số DB đánh dấu transaction là lỗi sau khi gặp vi phạm ràng buộc.

## 6. Batch và transaction giải quyết hai việc khác nhau

`PreparedStatement.addBatch()` và `executeBatch()` là công cụ **gom lệnh và yêu cầu thực thi theo nhóm**. Chúng không tự quy định tính nguyên tử trên nhiều bộ tham số, đặc biệt khi `Connection` đang ở `autoCommit = true`. Muốn “cả lô hoặc không có gì”, phải quản lý transaction một cách rõ ràng.

| Khía cạnh | Batch | Transaction |
| --- | --- | --- |
| API chủ yếu | `addBatch`, `executeBatch`, `clearBatch` | `setAutoCommit(false)`, `commit`, `rollback` |
| Mục đích | Giảm chi phí thực thi nhiều lệnh cùng cấu trúc | Giữ tính nguyên tử và nhất quán của thay đổi |
| Khi một lệnh lỗi | Driver có thể dừng hoặc tiếp tục một phần batch | Ứng dụng quyết định rollback toàn transaction nếu không thể chấp nhận kết quả một phần |
| Liên quan batch size | Có, để kiểm soát số lệnh chờ | Có thể chứa **nhiều** batch cùng một giao dịch |
| Khả năng thay thế | Không thay transaction | Không tự tối ưu số lượt gửi SQL |

Chẳng hạn, một đơn có 1.200 dòng và `BATCH_SIZE = 500` sẽ chạy ba lượt: **500 + 500 + 200**. Cả ba lượt vẫn thuộc cùng một transaction trong ví dụ `AdjustmentBatchWriter`. Nếu lượt thứ ba gặp lỗi khóa chính, những dòng vừa thực thi thành công ở hai lượt đầu **cũng phải được rollback**.

Lưu ý rằng `commit()` có thể thất bại do mất kết nối tại đúng thời điểm DB đang xác nhận transaction. Trong trường hợp đó, client có thể **không biết chắc** thao tác đã commit hay chưa; `rollback()` sau một lỗi mạng không luôn chứng minh rằng mọi thay đổi đã bị hoàn tác. Khi thiết kế retry, cần dùng định danh yêu cầu hoặc cơ chế đối soát phù hợp để tránh tạo trùng dữ liệu. Khóa `(request_id, line_no)` trong ví dụ có thể giúp nhận diện bản ghi của một yêu cầu, nhưng để có API idempotent thực sự cần xử lý đầy đủ trạng thái và kết quả của lần gọi trước.

### Có nên `commit()` sau mỗi batch nhỏ?

Điều này phụ thuộc yêu cầu nghiệp vụ. Với thao tác cần nguyên tử trên **toàn danh sách**, commit sau mỗi 500 dòng sẽ sai hợp đồng: batch thứ ba lỗi vẫn để lại 1.000 dòng đã commit. Với nhập liệu lớn mà nghiệp vụ cho phép mỗi nhóm là một đơn vị độc lập, commit theo nhóm có thể giảm thời gian giữ khóa và kích thước transaction, nhưng phải ghi rõ kết quả nhóm nào đã hoàn thành và cách chạy lại nhóm lỗi.

## 7. `clearBatch()` và quản lý những lệnh chưa thực thi

Không phải luồng nào cũng thực thi mọi bộ tham số đã gom. Ví dụ người dùng hủy thao tác trước khi gọi `executeBatch()`, hoặc chương trình phát hiện một giá trị không hợp lệ sau khi đã thêm vài bộ. Khi đó có thể gọi `clearBatch()` để bỏ những lệnh **đang chờ trong `PreparedStatement`**:

```java
statement.setString(1, "REQ-8");
statement.setInt(2, 1);
statement.setString(3, "SKU-A");
statement.setInt(4, 2);
statement.addBatch();

if (cancelRequested) {
    statement.clearBatch(); // Hủy bộ đang chờ, chưa gửi qua executeBatch.
} else {
    statement.executeBatch();
}
```

`clearBatch()` **không có nghĩa rollback**. Nếu đã `executeBatch()` nhóm thứ nhất rồi mới `clearBatch()` ở nhóm thứ hai, những thay đổi của nhóm thứ nhất vẫn nằm trong transaction, và phải `rollback()` nếu muốn hủy chúng. Tương tự, `clearParameters()` chỉ xóa các giá trị đang gán vào statement; nó không thay thế `clearBatch()`.

Khi một batch thất bại, nên đóng `PreparedStatement` và xử lý transaction theo chính sách đã định, thay vì tìm cách đoán trạng thái nội bộ rồi tiếp tục sử dụng cùng statement cho các bản ghi quan trọng.

## 8. Chọn batch size và hiệu năng thực tế

Không có con số tối ưu chung cho mọi ứng dụng. `BATCH_SIZE = 500` trong ví dụ là **giá trị minh họa**, không phải khuyến nghị bắt buộc. Giá trị phù hợp phụ thuộc kích thước từng hàng, số placeholder, giới hạn DB/driver, tốc độ mạng, transaction log, memory pressure và số kết nối đồng thời.

| Batch quá nhỏ | Batch vừa phải | Batch quá lớn |
| --- | --- | --- |
| Nhiều lượt gửi lệnh và overhead JDBC | Cân bằng lượt gửi và bộ nhớ, dễ đo đạc | Có thể dùng nhiều RAM, giữ transaction lâu hoặc chạm giới hạn gói tin/tham số |
| Dễ xác định dòng lỗi | Dễ chia lô, kiểm soát rollback | Lỗi ở cuối lô có thể lãng phí nhiều công việc trước đó |
| Thường không tận dụng hết driver | Thường là điểm bắt đầu thực nghiệm | Không bảo đảm nhanh hơn nếu DB bottleneck ở ghi đĩa/khóa |

Các bước đo đạc hợp lý:

1. Lấy **trường hợp không batch** làm mốc: cùng bộ dữ liệu, cùng DB và cùng điều kiện transaction.
2. Thử các cỡ batch có kiểm soát, ví dụ 50, 200, 500, 1.000 dòng, tùy giới hạn thực tế.
3. Đo tổng thời gian xử lý, số lệnh/giây, thời gian transaction, bộ nhớ và lỗi chờ khóa.
4. Đo với số lượng kết nối đồng thời gần thực tế, không chỉ một thread không tranh chấp.
5. Kiểm tra dữ liệu sau khi commit và kiểm thử lỗi giữa các batch để chắc chắn tối ưu không làm sai tính nguyên tử.

Một số driver có cơ chế **viết lại batch** thành SQL nhiều hàng hoặc dùng giao thức riêng để tăng hiệu năng, và có thể cần tùy chọn cấu hình driver. Không mặc định `executeBatch()` luôn tương đương **một lượt mạng** hoặc luôn được DB nhận như **một câu SQL**. Nên kiểm tra tài liệu driver cụ thể và đo trên hệ thống triển khai. Nếu tối ưu đổi cách thực thi hoặc thứ tự xử lý, cần xác minh thêm ràng buộc, generated keys và tương tác với trigger.

### Kiểm tra hỗ trợ batch từ driver

JDBC cung cấp metadata:

```java
try (Connection connection = dataSource.getConnection()) {
    boolean supported = connection.getMetaData().supportsBatchUpdates();
    System.out.println("Batch updates supported: " + supported);
}
```

Giá trị `true` cho biết driver/DB báo hỗ trợ batch; không bảo đảm mọi loại câu SQL hay tính năng đặc biệt có cùng hành vi trên mọi phiên bản driver. Nếu `false`, ứng dụng có thể dùng vòng lặp `executeUpdate()` với **cùng `PreparedStatement` và transaction**; hiệu năng có thể thấp hơn nhưng vẫn bảo toàn hợp đồng nguyên tử nếu quản lý commit/rollback đúng cách. Với ứng dụng bắt buộc phải có batch, có thể báo lỗi cấu hình sớm và dừng trước khi ghi.

## 9. Giới hạn của batching và những lỗi thường gặp

| Sai lầm hoặc tình huống | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Quên `addBatch()` trong vòng lặp | Chỉ bộ cuối hoặc không bộ nào được thực thi qua batch | Gọi `addBatch()` sau khi gán đủ tham số mỗi dòng |
| Quên `executeBatch()` | Danh sách chờ không được yêu cầu thực thi | Flush khi đủ nhóm và flush phần còn lại cuối vòng lặp |
| Quên gán một placeholder ở dòng sau | Có thể dùng lại giá trị tham số cũ | Luôn gán đủ các placeholder, kể cả `setNull` |
| Gọi `clearParameters()` để xóa batch | Các bộ đã gom vẫn có thể còn trong hàng chờ | Dùng `clearBatch()` khi muốn bỏ lệnh chưa chạy |
| `executeBatch()` thành công rồi mặc định đã commit | Với `autoCommit = false`, transaction vẫn chưa kết thúc | Chỉ trả thành công sau `commit()` |
| Batch thứ hai lỗi nhưng batch đầu đã commit | Lưu được một phần yêu cầu nguyên tử | Bao các nhóm trong một transaction, rollback nếu lỗi |
| Cộng trực tiếp các số trong `int[]` | `SUCCESS_NO_INFO = -2` không phải số hàng âm | Diễn giải riêng từng trạng thái |
| Bắt `BatchUpdateException` và bỏ qua | Có thể để lại một phần thay đổi | Chẩn đoán từ update counts rồi rollback hoặc xử lý theo chính sách có chủ đích |
| Dùng batch quá lớn | Tăng RAM, áp lực transaction, gặp giới hạn driver/DB | Chia nhóm và đo hiệu năng thực tế |
| Mong đợi `getGeneratedKeys()` khớp mọi dòng trong batch | Số lượng hoặc thứ tự khóa sinh có thể khác nhau theo driver/cơ chế rewrite | Thử nghiệm trên DB đích hoặc chèn từng cha cần khóa chính xác |
| Batch có SQL không đồng nhất bằng `PreparedStatement` | Không phù hợp cơ chế gom bộ tham số | Tách thành các `PreparedStatement` tương ứng từng cấu trúc SQL |

### Batch có phù hợp với generated keys không?

JDBC có API `getGeneratedKeys()`, và một số driver có thể trả nhiều khóa khi `INSERT` được batch. Tuy nhiên, **không nên mặc định khóa trả về sẽ luôn đủ, đúng kiểu và khớp từng dòng theo thứ tự** trên mọi driver, đặc biệt khi driver viết lại batch thành `INSERT` nhiều hàng. Nếu phải ghép chính xác khóa sinh cho từng bản ghi cha để tạo con, hãy xác minh hợp đồng của DB/driver hoặc dùng phương án thêm từng cha và lấy khóa riêng cho mỗi hàng. Ví dụ chính dùng khóa nghiệp vụ `(request_id, line_no)` để tránh phụ thuộc vào khóa tự sinh.

### Batch có bảo vệ khỏi SQL injection không?

`PreparedStatement` với placeholder `?` và các phương thức `setXxx` giúp **tham số hóa giá trị SQL**. Đó là cơ chế bảo vệ khỏi việc ghép dữ liệu người dùng trực tiếp vào cú pháp SQL. `addBatch()` chỉ gom nhiều lần gán tham số; nó không cho phép dùng placeholder thay tên bảng, tên cột hoặc cấu trúc SQL. Nếu phải xây dựng phần định danh SQL động, chỉ sử dụng những giá trị đã được cho phép rõ ràng từ ứng dụng.

## 10. Kiểm thử batching với cơ sở dữ liệu thực

Một số hành vi của batch thuộc hợp đồng JDBC chung, nhưng cách thực thi và báo kết quả chịu ảnh hưởng driver/DB. Những ca kiểm thử nên có:

| Tình huống | Kết quả cần xác minh |
| --- | --- |
| 3 dòng hợp lệ, một batch | Ghi đủ 3 dòng đúng `line_no`, SKU và số lượng thay đổi |
| Danh sách rỗng | Trả 0, không mở transaction không cần thiết |
| 500 dòng | Flush đúng một batch; commit đầy đủ |
| 501 dòng | Flush hai batch (500 và 1); dữ liệu đầy đủ |
| 1.200 dòng | Flush ba batch (500, 500 và 200); commit một transaction |
| Batch sau có một khóa chính trùng | Xảy ra lỗi; toàn bộ dòng mới của yêu cầu rollback, kể cả các batch trước |
| Driver báo `SUCCESS_NO_INFO` | Không xem `-2` là số hàng âm, vẫn xử lý trạng thái thành công |
| Một lệnh batch thất bại | Quan sát `BatchUpdateException.getUpdateCounts()`; rollback theo hợp đồng |
| Mất kết nối ngay lúc commit | Không mặc định kết quả là rollback; đối soát trước khi thử lại |
| Hai yêu cầu dùng cùng `request_id` | Ràng buộc khóa chính hoặc chính sách idempotency xử lý nhất quán |

**Chú ý khi kiểm thử rollback:** record `AdjustmentLine` từ chối `quantityDelta = 0` ngay trong Java, nên chỉ gửi giá trị `0` không chứng minh rằng DB có thể rollback sau khi đã chạy một phần batch. Để kiểm thử rollback thực sự, có thể chuẩn bị sẵn một hàng có khóa `(request_id, line_no)` trùng **với dòng ở giữa hoặc cuối lượt chạy**, sau đó gọi `insert`. Sau khi lỗi xảy ra, truy vấn bằng một kết nối khác và kiểm tra chỉ còn dữ liệu đã tồn tại **trước transaction**, không có các dòng mới của lần gọi thất bại.

Với bài kiểm thử hiệu năng, nên đồng thời ghi lại thời gian và kết quả dữ liệu, không chỉ số lượt gọi `executeBatch()`. Việc gom batch có thể giảm overhead, nhưng hiệu quả phụ thuộc cả index, constraint, trigger, engine ghi dữ liệu và tải đồng thời.

## 11. Bài tập tự kiểm tra

**Bài 1 — Tìm lỗi thiếu flush.** Với 1.001 dòng và batch size 500, một vòng lặp chỉ gọi `executeBatch()` khi `pending == 500`, không xử lý gì sau khi kết thúc. Có bao nhiêu dòng được yêu cầu thực thi?

**Đáp án:** 1.000 dòng được yêu cầu thực thi trong hai batch; **1 dòng cuối vẫn ở trạng thái chờ**. Cần gọi `executeBatch()` thêm một lần khi `pending > 0`.

**Bài 2 — Phân biệt các API.** Một phương thức đã gọi `addBatch()` ba lần. Việc gọi `clearParameters()` rồi `executeBatch()` có phải cách đúng để hủy ba bộ tham số đã gom không?

**Đáp án:** Không. `clearParameters()` xóa giá trị tham số hiện tại; `clearBatch()` mới hủy các lệnh đang chờ trong batch.

**Bài 3 — Đọc kết quả.** Một lượt `executeBatch()` trả `[1, SUCCESS_NO_INFO, 1]`. Có thể cộng các phần tử để kết luận đã cập nhật đúng 0 hàng không?

**Đáp án:** Không. `SUCCESS_NO_INFO = -2` là mã trạng thái báo thành công nhưng **không biết số hàng**, không phải giá trị số học để cộng.

**Bài 4 — Xử lý lỗi giữa nhiều batch.** Batch 1 và 2 đã chạy thành công nhưng chưa commit. Batch 3 ném `BatchUpdateException`. Nếu yêu cầu phải ghi đầy đủ cả 1.200 dòng, cần làm gì?

**Đáp án:** Thử `rollback()` toàn transaction và trả lỗi; không giữ hai batch đầu như một phần thành công.

**Bài 5 — Tham số bị giữ lại.** Câu `INSERT` có năm placeholder, trong đó tham số 5 là ghi chú nullable. Dòng 1 gán ghi chú, dòng 2 không có ghi chú và chỉ gán bốn tham số đầu. Vì sao nguy hiểm?

**Đáp án:** Placeholder thứ 5 có thể giữ giá trị dòng trước. Phải gán `setNull(5, Types.VARCHAR)` ở dòng không có ghi chú trước khi gọi `addBatch()`.

**Bài 6 — Chọn transaction.** Đội nhập liệu muốn lưu 100.000 sự kiện, cho phép từng lô 500 sự kiện được commit độc lập và có cơ chế chạy lại lô lỗi. Có bắt buộc dùng một transaction cho toàn bộ 100.000 sự kiện không?

**Đáp án:** Không; khi nghiệp vụ chấp nhận thành công một phần theo từng lô, có thể commit theo từng nhóm và ghi nhận tiến độ. Nếu toàn bộ 100.000 dòng là một thao tác nguyên tử, phải giữ một ranh giới transaction phù hợp hoặc thiết kế lại yêu cầu để tránh transaction quá lớn.

## Tổng kết

`PreparedStatement.addBatch()` là công cụ chuẩn của JDBC để **gom nhiều bộ tham số cho cùng một câu SQL**. Với mỗi dòng, gán đủ tham số bằng `setXxx`, gọi `addBatch()`, sau đó `executeBatch()` khi đạt kích thước nhóm hoặc kết thúc danh sách. Đọc kết quả theo ý nghĩa từng phần tử, đặc biệt `SUCCESS_NO_INFO` và `BatchUpdateException`; đừng tự suy diễn rằng mọi lệnh đã commit. Nếu một yêu cầu phải thành công toàn bộ, dùng cùng `Connection` với `autoCommit = false`, thực thi mọi nhóm rồi `commit()` một lần hoặc `rollback()` khi có lỗi. Hãy kiểm chứng `supportsBatchUpdates()`, batch size, generated keys và hành vi lỗi trên đúng DB/driver triển khai để đạt hiệu năng mà vẫn giữ đúng hợp đồng dữ liệu.
