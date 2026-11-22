# Đọc update counts và các giá trị trạng thái đặc biệt

> **Chương:** Xử lý theo lô  
> **Ngữ cảnh:** Ứng dụng Java dùng **JDBC** qua `DataSource`, `PreparedStatement` và `Connection` để gửi nhiều lệnh SQL bằng `addBatch()`/`executeBatch()`, quản lý transaction và xử lý lỗi.

Một ứng dụng cập nhật giá của 500 sản phẩm bằng `PreparedStatement.executeBatch()`. Driver trả về mảng `[1, 1, 0, -2, ...]`. Điều đó có nghĩa cả 500 câu lệnh đều chạy thành công? `0` có phải lỗi? `-2` có phải là đã cập nhật âm hai hàng? Nếu câu lệnh thứ 200 thất bại và `executeBatch()` ném `BatchUpdateException`, các lệnh trước nó đã được commit hay chưa?

JDBC dùng **update counts** để báo số hàng bị ảnh hưởng *khi driver xác định được*, và dùng **mã trạng thái đặc biệt** khi không thể báo số hàng cụ thể hoặc có câu lệnh thất bại. Đọc đúng những giá trị này giúp ứng dụng phân biệt kết quả SQL, quyết định nghiệp vụ, phát hiện lỗi batch và rollback giao dịch đúng phạm vi.

Trong bài này, người học sẽ:

- Đọc đúng thứ tự của `int[]` từ `executeBatch()` và ánh xạ từng phần tử về lệnh đã thêm.
- Phân biệt số hàng `0`, `Statement.SUCCESS_NO_INFO` và `Statement.EXECUTE_FAILED`.
- Xử lý hai tình huống driver **dừng** hoặc **tiếp tục** sau một lệnh lỗi qua `BatchUpdateException.getUpdateCounts()`.
- Phân biệt **lệnh đã thực thi**, **lệnh được báo thành công** và **giao dịch đã commit**.
- Biết khi nào cần `executeLargeBatch()`/`getLargeUpdateCounts()`, kiểm thử driver và thiết kế rollback/retry an toàn.

Ví dụ SQL sử dụng PostgreSQL để minh họa, nhưng các API và hằng số nêu trong bài là của JDBC. Hành vi thực tế khi batch bị lỗi, cách tính số hàng và mức hỗ trợ các API cần được xác nhận với đúng driver, DBMS và phiên bản đang triển khai.

## 1. `executeBatch()` trả về gì?

Với `PreparedStatement`, ứng dụng bind một bộ tham số, gọi `addBatch()` để xếp lệnh vào batch, lặp lại nhiều lần, rồi gọi `executeBatch()`:

```java
String sql = "UPDATE product_prices SET price = ? WHERE product_id = ?";

try (Connection connection = dataSource.getConnection();
     PreparedStatement ps = connection.prepareStatement(sql)) {

    ps.setBigDecimal(1, new BigDecimal("15.00"));
    ps.setLong(2, 101L);
    ps.addBatch(); // Lệnh ở vị trí 0.

    ps.setBigDecimal(1, new BigDecimal("20.00"));
    ps.setLong(2, 102L);
    ps.addBatch(); // Lệnh ở vị trí 1.

    ps.setBigDecimal(1, new BigDecimal("35.00"));
    ps.setLong(2, 103L);
    ps.addBatch(); // Lệnh ở vị trí 2.

    int[] counts = ps.executeBatch();
    System.out.println(Arrays.toString(counts));
}
```

Các import cần có ở ví dụ này là `java.sql.Connection`, `java.sql.PreparedStatement`, `java.math.BigDecimal` và `java.util.Arrays`; giả định `dataSource` đã được cấu hình.

Nếu ba lệnh được thực thi thành công và driver có thể báo số hàng cho từng lệnh, `counts.length == 3`. **`counts[i]` tương ứng với lệnh ở vị trí `i` trong thứ tự `addBatch()`**. Không sắp xếp lại danh sách input sau khi tạo batch, vì như vậy làm mất ánh xạ từ kết quả về bản ghi.

Số hàng trong mỗi phần tử là số hàng **database/driver báo bị ảnh hưởng bởi lệnh tương ứng**, không phải:

- Số hàng Java đã kiểm tra hợp lệ trước khi gửi.
- Số lệnh đã commit trên database.
- Số bản ghi được chèn thành công trên toàn bộ batch.
- Số hàng mà người dùng mong đợi theo quy tắc nghiệp vụ.

### `Statement` và `PreparedStatement`

Cả hai đều có cơ chế batch:

```java
// PreparedStatement: một mẫu SQL, nhiều bộ giá trị tham số.
ps.setLong(1, 101L);
ps.addBatch();
ps.setLong(1, 102L);
ps.addBatch();
int[] counts = ps.executeBatch();
```

```java
// Statement: nhiều chuỗi SQL hoàn chỉnh (dành cho SQL tin cậy).
try (Statement statement = connection.createStatement()) {
    statement.addBatch(
        "UPDATE product_prices SET price = 15.00 WHERE product_id = 101"
    );
    statement.addBatch(
        "UPDATE product_prices SET price = 20.00 WHERE product_id = 102"
    );
    int[] counts = statement.executeBatch();
}
```

Trong ứng dụng nhận dữ liệu từ client, ưu tiên **`PreparedStatement` và bind tham số** để tránh nối giá trị không đáng tin cậy vào SQL. Dù dùng loại statement nào, mảng kết quả phải được diễn giải theo cùng các giá trị trạng thái chuẩn.

## 2. Ba nhóm giá trị hợp lệ cần phân biệt

JDBC định nghĩa hai hằng số trên `java.sql.Statement`:

```java
Statement.SUCCESS_NO_INFO   // -2
Statement.EXECUTE_FAILED    // -3
```

Bảng diễn giải:

| `counts[i]` | Ý nghĩa ở mức JDBC | Có thể suy ra điều gì? |
|---|---|---|
| `0` | Lệnh đã thực thi nhưng số hàng bị ảnh hưởng được báo là **0** | Không tự động coi là lỗi SQL; có thể không khớp `WHERE` |
| Số dương, ví dụ `1`, `3` | Driver báo **số hàng bị ảnh hưởng** | Có số đếm cụ thể cho lệnh tương ứng |
| `Statement.SUCCESS_NO_INFO` (`-2`) | Driver báo lệnh **thành công**, nhưng **không cung cấp số hàng bị ảnh hưởng** | Không biết là 0, 1 hay nhiều hàng; không được cộng `-2` vào tổng |
| `Statement.EXECUTE_FAILED` (`-3`) | Driver báo lệnh **thất bại**, khi nó tiếp tục xử lý batch sau lỗi | Dùng để chỉ mục lệnh thất bại trong thông tin batch |
| Giá trị âm khác | Không thuộc các giá trị kết quả batch chuẩn ở bảng này | Điều tra driver/API; không tự quy thành thành công hoặc thất bại |

**`Statement.SUCCESS_NO_INFO` là thông báo thành công, không phải lỗi.** Nếu một ứng dụng đơn giản coi mọi giá trị âm là lỗi, nó sẽ đánh dấu sai những lệnh mà JDBC cho biết đã thành công nhưng không đếm được hàng.

**`Statement.EXECUTE_FAILED` không phải “âm ba hàng”.** Đây là một mã trạng thái của batch. Nó thường được quan sát trong mảng `getUpdateCounts()` của `BatchUpdateException` khi driver vẫn tiếp tục thực thi những lệnh còn lại sau một lỗi.

Đặc biệt, **`Statement.getUpdateCount() == -1` là một ngữ cảnh khác**: API này dùng sau những lệnh thực thi đơn lẻ hoặc khi duyệt nhiều kết quả, với `-1` để biểu thị không có update count hiện tại hoặc không còn kết quả tương ứng. Không áp dụng ý nghĩa của `getUpdateCount()` sang từng phần tử của mảng `executeBatch()`.

### Vì sao `0` không giống `EXECUTE_FAILED`?

Xét SQL:

```sql
UPDATE product_prices
SET price = ?
WHERE product_id = ?;
```

Nếu `product_id` không tồn tại, SQL có thể thực thi hợp lệ và báo `0` hàng bị ảnh hưởng. Đây thường là **tình huống nghiệp vụ** (bản ghi không tồn tại, cập nhật sai mã, hoặc dữ liệu đã thay đổi); nó không nhất thiết khiến JDBC ném exception.

Ngoài ra, một số DBMS/driver có sự khác biệt về cách báo số hàng **đã khớp** hay **thực sự thay đổi**, đặc biệt với UPDATE đặt lại cùng giá trị hoặc cấu hình driver. Muốn xử lý `0` thành `404 Not Found` hay `409 Conflict`, cần căn cứ SQL, DBMS và hợp đồng nghiệp vụ, không chỉ dựa vào số đếm.

## 3. Đọc kết quả batch trên dữ liệu thử

Tạo bảng PostgreSQL:

```sql
CREATE TABLE product_prices (
    product_id BIGINT PRIMARY KEY,
    price NUMERIC(12, 2) NOT NULL CHECK (price >= 0)
);

INSERT INTO product_prices (product_id, price) VALUES
    (101, 10.00),
    (103, 30.00);
```

Gửi ba lệnh cập nhật, trong đó `product_id = 102` **không có** trong bảng:

```java
record PriceChange(long productId, BigDecimal newPrice) {}

List<PriceChange> changes = List.of(
    new PriceChange(101L, new BigDecimal("15.00")),
    new PriceChange(102L, new BigDecimal("20.00")),
    new PriceChange(103L, new BigDecimal("35.00"))
);

String sql = "UPDATE product_prices SET price = ? WHERE product_id = ?";

try (Connection connection = dataSource.getConnection();
     PreparedStatement ps = connection.prepareStatement(sql)) {

    for (PriceChange change : changes) {
        ps.setBigDecimal(1, change.newPrice());
        ps.setLong(2, change.productId());
        ps.addBatch();
    }

    int[] counts = ps.executeBatch();
    for (int i = 0; i < counts.length; i++) {
        System.out.printf(
            "input[%d]: productId=%d, updateCount=%d%n",
            i, changes.get(i).productId(), counts[i]
        );
    }
}
```

Giả sử PostgreSQL driver báo số hàng cụ thể cho từng lệnh trong thử nghiệm này, kết quả **minh họa** là:

```text
input[0]: productId=101, updateCount=1
input[1]: productId=102, updateCount=0
input[2]: productId=103, updateCount=1
```

Nên đọc như sau:

- `input[0]`: update cho `101` có một hàng bị ảnh hưởng.
- `input[1]`: câu SQL cho `102` thực thi nhưng không có hàng khớp.
- `input[2]`: update cho `103` có một hàng bị ảnh hưởng.

Không được kết luận hai câu lệnh “thành công” và một câu lệnh “lỗi JDBC” chỉ vì có một số `0`. Nếu yêu cầu **mọi sản phẩm phải tồn tại và đúng một hàng phải được cập nhật**, chính service phải coi kết quả `0` là vi phạm nghiệp vụ và **rollback toàn transaction**. Nếu nghiệp vụ cho phép “bỏ qua sản phẩm không tồn tại”, kết quả `0` có thể được chấp nhận.

**Lưu ý:** ví dụ Java ở mục này chưa mở transaction thủ công. Khi `autoCommit=true`, không được dùng mảng update counts để suy ra cả batch là một đơn vị nguyên tử. Mục 6 sẽ xây dựng transaction phù hợp.

## 4. Xử lý `SUCCESS_NO_INFO` và tổng số hàng bị ảnh hưởng

Giả sử một driver trả:

```text
counts = [1, -2, 0, 3]
```

Diễn giải: lệnh đầu báo một hàng; lệnh thứ hai **thành công nhưng không biết số hàng**; lệnh thứ ba báo không có hàng ảnh hưởng; lệnh thứ tư báo ba hàng. Ta chỉ biết có **4 hàng được báo cụ thể** từ ba vị trí biết số đếm (`1 + 0 + 3`). **Không thể tính chính xác tổng số hàng ảnh hưởng của cả batch** từ mảng này.

Không viết:

```java
// SAI: SUCCESS_NO_INFO = -2 không phải số hàng âm.
long total = Arrays.stream(counts).sum();
```

Thay vào đó, lập báo cáo giữ riêng số hàng biết được và số lệnh có kết quả không xác định:

```java
import java.sql.SQLException;
import java.sql.Statement;

record BatchCountSummary(
    int submitted,
    long knownAffectedRows,
    int succeededWithoutCount
) {}

static BatchCountSummary summarizeSuccessfulBatch(
        int[] counts,
        int submitted
) throws SQLException {
    if (counts.length != submitted) {
        throw new SQLException(
            "Successful batch returned " + counts.length
            + " counts for " + submitted + " commands"
        );
    }

    long knownAffected = 0;
    int succeededWithoutCount = 0;

    for (int i = 0; i < counts.length; i++) {
        int value = counts[i];

        if (value == Statement.SUCCESS_NO_INFO) {
            succeededWithoutCount++;
        } else if (value == Statement.EXECUTE_FAILED) {
            throw new SQLException(
                "Batch reported failed command at index " + i
            );
        } else if (value >= 0) {
            knownAffected += value;
        } else {
            throw new SQLException(
                "Unexpected batch update count " + value
                + " at index " + i
            );
        }
    }

    return new BatchCountSummary(
        submitted, knownAffected, succeededWithoutCount
    );
}
```

Với mảng `[1, -2, 0, 3]`, kết quả là:

```text
submitted = 4
knownAffectedRows = 4
succeededWithoutCount = 1
```

Tên `knownAffectedRows` được chọn có chủ ý: **đó chỉ là tổng các count đã biết**, không tự động trở thành “tổng số hàng được cập nhật”. Trong báo cáo vận hành, nên hiển thị cả `succeededWithoutCount` hoặc một trường `exactTotalKnown=false`; nếu không người đọc sẽ nhầm tổng 4 là con số chính xác.

### Nếu nghiệp vụ đòi đúng một hàng cho mỗi lệnh

Giả sử API nhận 50 cập nhật theo ID, và **tất cả ID phải tồn tại**. Với `counts[i] == 1`, mục tiêu được xác nhận trực tiếp; với `counts[i] == 0`, mục tiêu không đạt. Với `SUCCESS_NO_INFO`, JDBC chỉ xác nhận lệnh thành công nhưng **chưa chứng minh có đúng một hàng khớp**.

Ứng dụng có thể chọn một trong hai chính sách được định nghĩa rõ:

1. **Chặt chẽ:** không commit nếu không thể xác nhận mọi lệnh ảnh hưởng đúng một hàng; rollback rồi báo rằng không đủ thông tin xác minh. Ở chính sách này `SUCCESS_NO_INFO` *không phải lỗi JDBC*, nhưng không đáp ứng điều kiện chứng minh của nghiệp vụ.
2. **Xác minh bổ sung:** dùng truy vấn theo các ID và version/giá trị mong đợi **trong cùng transaction**, hoặc thiết kế SQL trả thông tin thích hợp của DBMS. Cần cân nhắc cạnh tranh dữ liệu, khóa và cách đo lường kết quả.

Đừng thay `SUCCESS_NO_INFO` bằng `1` chỉ để cho báo cáo “đẹp”. Một statement có thể ảnh hưởng nhiều hàng; trạng thái `-2` không chứa số lượng đó.

## 5. Khi `executeBatch()` ném `BatchUpdateException`

Một lệnh SQL trong batch có thể lỗi vì vi phạm `UNIQUE`/`FOREIGN KEY`, lỗi dữ liệu, deadlock, timeout hoặc mất kết nối. Khi batch thực thi thất bại, API có thể ném **`java.sql.BatchUpdateException`**, lớp con của `SQLException`.

`BatchUpdateException` cung cấp `getUpdateCounts()` để xem thông tin **đã được driver báo** trước/đến lúc thất bại. Quan trọng: JDBC cho phép driver chọn dừng ngay tại lỗi hoặc tiếp tục các lệnh sau lỗi; ta phải giải thích mảng theo trường hợp thực tế.

### 5.1. Trường hợp driver dừng tại lỗi đầu tiên

Giả sử có năm lệnh `addBatch()` được gửi. Driver chạy thành công lệnh 0 và 1, rồi lệnh 2 gây vi phạm constraint và driver dừng. Mảng từ `failure.getUpdateCounts()` có thể là:

```text
submitted input indexes:   0   1   2   3   4
getUpdateCounts():        [1,  1]
                           └──┘
                           các lệnh trước lỗi đầu tiên
```

Khi driver thực hiện đúng chế độ **dừng ngay tại lỗi đầu tiên**, độ dài mảng thể hiện các lệnh đã thành công trước lỗi; lệnh ở `index = counts.length` là vị trí lỗi đầu tiên. Những lệnh sau đó thường **chưa được thực thi** trong batch này.

Cẩn trọng: nếu đang có lỗi kết nối hoặc batch rewrite đặc thù, đừng coi mảng trả về là bằng chứng đủ để kết luận mọi thay đổi trên server hoặc trạng thái commit. Phần tử không xuất hiện **không có nghĩa nó chắc chắn đã rollback**.

### 5.2. Trường hợp driver tiếp tục sau lỗi

Một driver khác có thể cố chạy tiếp những lệnh còn lại và trả mảng dài bằng số lệnh đã gửi, đánh dấu mục lỗi bằng `Statement.EXECUTE_FAILED`:

```text
submitted input indexes:    0    1    2    3
getUpdateCounts():         [1,  -3,   0,   1]
                                 │
                                 └── Statement.EXECUTE_FAILED
```

Ở ví dụ này:

- `0`: một hàng được báo ảnh hưởng.
- `1`: lệnh báo thất bại.
- `2`: lệnh thực thi với 0 hàng ảnh hưởng.
- `3`: một hàng được báo ảnh hưởng.

Mảng trên là **ví dụ cấu trúc**, không khẳng định PostgreSQL hay bất kỳ driver cụ thể nào sẽ thực thi tiếp sau mọi loại lỗi. PostgreSQL có thể đặt transaction vào trạng thái bị lỗi sau một câu SQL thất bại; kết quả của các lệnh sau phụ thuộc cách driver và transaction được xử lý. **Hãy kiểm thử đúng DBMS/driver** trước khi dựa vào hành vi tiếp tục.

### 5.3. Đọc lỗi và ánh xạ với input gốc

Đoạn helper sau có thể dùng để tạo báo cáo chẩn đoán từ `BatchUpdateException`:

```java
import java.sql.BatchUpdateException;
import java.sql.SQLException;
import java.sql.Statement;
import java.util.List;

static void inspectBatchFailure(
        BatchUpdateException failure,
        List<Long> submittedIds
) {
    int[] counts = failure.getUpdateCounts();

    System.err.printf(
        "Batch failed: submitted=%d, reported=%d, SQLState=%s%n",
        submittedIds.size(),
        counts.length,
        failure.getSQLState()
    );

    for (int i = 0; i < counts.length && i < submittedIds.size(); i++) {
        int count = counts[i];
        String status;

        if (count == Statement.SUCCESS_NO_INFO) {
            status = "SUCCESS_NO_INFO";
        } else if (count == Statement.EXECUTE_FAILED) {
            status = "EXECUTE_FAILED";
        } else if (count >= 0) {
            status = "affected=" + count;
        } else {
            status = "UNKNOWN_CODE=" + count;
        }

        System.err.printf(
            "batch[%d] id=%d: %s%n", i, submittedIds.get(i), status
        );
    }

    if (counts.length < submittedIds.size()) {
        System.err.println(
            "Driver reported a partial prefix; check failing command "
            + "and commands without reported results"
        );
    }

    for (SQLException next = failure.getNextException();
         next != null;
         next = next.getNextException()) {

        System.err.printf(
            "next SQL error: state=%s, code=%d, message=%s%n",
            next.getSQLState(),
            next.getErrorCode(),
            next.getMessage()
        );
    }
}
```

Để ánh xạ đúng, danh sách `submittedIds` phải được xây dựng **đúng thứ tự với mỗi lần `addBatch()`**. Nếu app ghi batch nhiều chunk, phải lưu cả **chỉ số chunk và chỉ số toàn cục**; ví dụ `globalIndex = chunkStart + localIndex`, tránh nhầm lỗi trong chunk thứ ba thành bản ghi đầu tiên của toàn tác vụ.

Ở môi trường sản xuất, log phải có giới hạn kích thước và tránh ghi giá trị SQL nhạy cảm. `getNextException()` có thể mang thông tin cụ thể hơn lỗi SQL đầu tiên; cũng nên giữ `getCause()` và `getSuppressed()` khi error đi qua nhiều tầng. Nếu tự viết logger duyệt exception chain, nên giới hạn số phần tử để tránh log vô hạn do driver lỗi.

**Điểm mấu chốt:** mảng `getUpdateCounts()` giúp khoanh vùng câu lệnh mà driver đã báo trạng thái. Nó **không chứng minh** những thay đổi đó đã commit, cũng không phải là danh sách các bản ghi được phép retry riêng lẻ.

## 6. Phối hợp update counts với transaction JDBC

Một batch không tự động trở thành transaction nghiệp vụ nguyên tử. Nếu ứng dụng yêu cầu “tất cả cập nhật thành công hoặc không cập nhật gì”, phải dùng **một `Connection`, `setAutoCommit(false)`, kiểm tra toàn bộ kết quả rồi mới `commit()`**.

Không nên làm:

```java
// Nguy cơ: batch không được bao trong transaction do ứng dụng quản lý.
try (Connection connection = dataSource.getConnection();
     PreparedStatement ps = connection.prepareStatement(updateSql)) {
    // addBatch() cho các thay đổi...
    int[] counts = ps.executeBatch();
    // Trả thành công ngay, không xem xét nghiệp vụ và trạng thái commit.
}
```

Với `autoCommit=true`, driver/database có thể đã xác nhận một số câu lệnh trước khi batch báo lỗi; không có bảo đảm chung về **all-or-nothing** cho toàn batch như một use case. Ngay cả khi `executeBatch()` trả mảng đầy đủ, điều đó không tự thay thế bước kiểm tra invariant nghiệp vụ.

### 6.1. Ví dụ đầy đủ: cập nhật giá theo lô, yêu cầu mỗi ID khớp đúng một hàng

Giả sử yêu cầu nghiệp vụ là: **tất cả sản phẩm đã tồn tại**, mỗi phần tử input cập nhật đúng **một** hàng, và mọi thay đổi được commit cùng nhau. Bảng `product_prices` đã tạo ở mục 3.

Lưu ý: code dưới đây cố ý **không chấp nhận `SUCCESS_NO_INFO`** vì không thể xác minh yêu cầu “đúng một hàng” chỉ từ update count. Đây là chính sách của ví dụ, không phải coi `-2` là lỗi của JDBC.

```java
import java.math.BigDecimal;
import java.sql.BatchUpdateException;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;
import java.sql.Statement;
import java.util.List;
import java.util.Objects;
import javax.sql.DataSource;

record PriceChange(long productId, BigDecimal newPrice) {}

public final class PriceBatchService {
    private final DataSource dataSource;

    public PriceBatchService(DataSource dataSource) {
        this.dataSource = Objects.requireNonNull(dataSource);
    }

    public void updateAll(List<PriceChange> changes) throws SQLException {
        Objects.requireNonNull(changes, "changes");

        for (PriceChange change : changes) {
            Objects.requireNonNull(change, "change");
            BigDecimal price = Objects.requireNonNull(
                change.newPrice(), "newPrice"
            );
            if (price.signum() < 0 || price.scale() > 2) {
                throw new IllegalArgumentException(
                    "Price must be nonnegative with at most 2 decimals"
                );
            }
        }

        String sql = """
            UPDATE product_prices
            SET price = ?
            WHERE product_id = ?
            """;

        try (Connection connection = dataSource.getConnection()) {
            if (!connection.getAutoCommit()) {
                throw new SQLException(
                    "Expected a fresh auto-commit connection"
                );
            }

            connection.setAutoCommit(false);
            boolean transactionEnded = false;
            Throwable failure = null;

            try {
                int[] counts;

                try (PreparedStatement ps =
                         connection.prepareStatement(sql)) {

                    for (PriceChange change : changes) {
                        ps.setBigDecimal(1, change.newPrice());
                        ps.setLong(2, change.productId());
                        ps.addBatch();
                    }

                    try {
                        counts = ps.executeBatch();
                    } catch (BatchUpdateException batchFailure) {
                        System.err.printf(
                            "Batch SQL failure: SQLState=%s, "
                            + "reportedCounts=%d%n",
                            batchFailure.getSQLState(),
                            batchFailure.getUpdateCounts().length
                        );
                        throw batchFailure;
                    }
                }

                // Chỉ kiểm tra counts sau khi statement đã đóng.
                if (counts.length != changes.size()) {
                    throw new SQLException(
                        "Unexpected batch count length: " + counts.length
                    );
                }

                for (int i = 0; i < counts.length; i++) {
                    int count = counts[i];

                    if (count == Statement.SUCCESS_NO_INFO) {
                        throw new SQLException(
                            "Could not verify exactly one row for product "
                            + changes.get(i).productId()
                        );
                    }
                    if (count == Statement.EXECUTE_FAILED) {
                        throw new SQLException(
                            "Batch failed at index " + i
                        );
                    }
                    if (count != 1) {
                        throw new SQLException(
                            "Expected one row for product "
                            + changes.get(i).productId()
                            + ", actual count=" + count
                        );
                    }
                }

                connection.commit();
                transactionEnded = true;

            } catch (SQLException | RuntimeException ex) {
                failure = ex;

                try {
                    connection.rollback();
                    transactionEnded = true;
                } catch (SQLException rollbackFailure) {
                    ex.addSuppressed(rollbackFailure);
                }

                throw ex;

            } finally {
                // Chỉ reset trạng thái nếu đã biết transaction kết thúc.
                if (transactionEnded) {
                    try {
                        connection.setAutoCommit(true);
                    } catch (SQLException resetFailure) {
                        if (failure != null) {
                            failure.addSuppressed(resetFailure);
                        } else {
                            throw resetFailure;
                        }
                    }
                }
            }
            // try-with-resources đóng/trả connection về pool.
        }
    }
}
```

Khi dùng dịch vụ trên:

```java
PriceBatchService service = new PriceBatchService(dataSource);

List<PriceChange> changes = List.of(
    new PriceChange(101L, new BigDecimal("15.00")),
    new PriceChange(103L, new BigDecimal("35.00"))
);

service.updateAll(changes); // Chỉ trả về khi commit xong.
```

Kết quả kỳ vọng với dữ liệu mẫu là giá sản phẩm `101` và `103` cùng được cập nhật. Nếu thêm phần tử `productId = 102` vào giữa, `UPDATE` cho `102` có thể trả `0`; service sẽ ném exception và rollback cả các cập nhật đã thực hiện trước đó trong cùng transaction.

**Lưu ý về chính sách cleanup:** ví dụ giả định connection do `DataSource` cấp đang ở `autoCommit=true` và service là chủ transaction. Nếu `rollback()` thất bại, service không gọi `setAutoCommit(true)` khi trạng thái transaction chưa rõ; `close()` của proxy pool phải được kiểm tra theo triển khai thực tế để loại bỏ/reset connection lỗi. Nếu `commit()` gặp lỗi mạng, trạng thái commit có thể không rõ từ phía client, vì thế retry cần kết hợp idempotency và đối soát kết quả.

### 6.2. `executeBatch()` thành công chưa phải `commit()`

Phân biệt ba trạng thái:

| Điều đã biết | Có thể kết luận | Chưa thể kết luận |
|---|---|---|
| `executeBatch()` trả mảng hợp lệ | Driver báo hoàn thành xử lý batch | Transaction đã commit, invariant nghiệp vụ đã đạt |
| Mỗi count `== 1` theo chính sách ví dụ | Driver báo đúng một hàng ảnh hưởng ở mỗi lệnh | Những thay đổi này đã commit nếu chưa gọi `commit()` |
| `connection.commit()` trả về thành công | Transaction đã được xác nhận theo phản hồi JDBC | Các hành động ngoài database (email, HTTP) đã hoàn thành |

Ngay cả khi tất cả lệnh SQL đã chạy, một lỗi ở câu lệnh kiểm tra sau batch vẫn có thể khiến chủ transaction rollback. Ngược lại, lỗi trong `Connection.close()` sau khi `commit()` thành công không đồng nghĩa batch chưa được commit.

## 7. `executeLargeBatch()` và số đếm `long[]`

`executeBatch()` trả `int[]` nên một update count rất lớn có nguy cơ vượt quá phạm vi `int`. JDBC 4.2 bổ sung những API hướng tới số đếm lớn:

```java
// JDBC 4.2+, tùy driver hỗ trợ.
long[] counts = preparedStatement.executeLargeBatch();
```

Khi có lỗi batch, đọc dạng `long[]`:

```java
try {
    long[] counts = preparedStatement.executeLargeBatch();

    for (long value : counts) {
        if (value == Statement.SUCCESS_NO_INFO) {
            // Thành công nhưng không biết số hàng.
        } else if (value == Statement.EXECUTE_FAILED) {
            // Mã báo lỗi một lệnh.
        } else if (value >= 0) {
            // Số hàng ảnh hưởng có thể lớn hơn Integer.MAX_VALUE.
        } else {
            throw new SQLException("Unexpected count: " + value);
        }
    }
} catch (BatchUpdateException failure) {
    long[] partial = failure.getLargeUpdateCounts();
    System.err.println("Reported large counts: " + partial.length);
    throw failure;
}
```

Ý nghĩa của `SUCCESS_NO_INFO` và `EXECUTE_FAILED` **không đổi** khi chuyển sang `long[]`. Việc dùng `long[]` giải quyết **giới hạn miền số đếm**, không làm driver đột nhiên biết số hàng mà nó vốn không thể báo.

`BatchUpdateException.getUpdateCounts()` vẫn có thể được dùng cho các đoạn code cũ, nhưng khi ứng dụng chọn `executeLargeBatch()` thì nên xử lý nhất quán bằng `getLargeUpdateCounts()`. Cần kiểm thử mức hỗ trợ thực tế của driver và phương thức mới; một số driver cũ có thể chưa triển khai đầy đủ.

## 8. Đừng nhầm update counts với generated keys

Hai kết quả phục vụ hai câu hỏi khác nhau:

- **Update count:** câu lệnh ảnh hưởng bao nhiêu hàng, hoặc driver không báo được số lượng?
- **Generated key:** database đã tạo giá trị khóa chính/khóa sinh nào cho hàng vừa insert?

Ví dụ:

```java
PreparedStatement ps = connection.prepareStatement(
    "INSERT INTO customers (name) VALUES (?)",
    Statement.RETURN_GENERATED_KEYS
);
```

Đối với INSERT từng hàng, có thể đọc `ps.getGeneratedKeys()` sau khi thực thi khi DBMS/driver hỗ trợ. **Không suy ra ID từ update count**: `counts[i] == 1` chỉ mô tả số hàng ảnh hưởng, không phải giá trị khóa được sinh.

Khi batch nhiều lệnh INSERT và cần generated keys, mức hỗ trợ, thứ tự khóa trả về và tương ứng giữa keys với từng input **phụ thuộc driver/DBMS và cách batch được thực thi**. Không mặc định `getGeneratedKeys()` trả một hàng cho mỗi `addBatch()` theo đúng thứ tự mà không kiểm chứng. Nếu yêu cầu ánh xạ khóa chính xác, phải kiểm thử driver mục tiêu hoặc sử dụng cơ chế `RETURNING`/SQL dialect và khóa do ứng dụng tạo phù hợp.

## 9. Cắt batch thành chunk: đếm đúng, rollback đúng, retry đúng

Một tác vụ gồm 100.000 thay đổi không nhất thiết gửi qua **một** `executeBatch()`. Ứng dụng thường chia thành các chunk giới hạn theo kích thước phù hợp với driver, độ lớn câu lệnh, dung lượng bộ nhớ, transaction timeout và tải của database.

Ví dụ:

```text
Toàn bộ input:         0 ... 999
Chunk 0:               0 ... 199
Chunk 1:             200 ... 399
Chunk 2:             400 ... 599
...
Chunk 2 local index 7 -> global index 407
```

Với mỗi chunk, lưu danh sách tham số/ID theo đúng thứ tự `addBatch()`; gọi `executeBatch()`, kiểm tra kết quả, rồi chuẩn bị chunk kế tiếp. Phân biệt **hai chính sách transaction**:

1. **Một transaction bao nhiều chunk:** chỉ `commit()` sau khi tất cả chunk hoàn thành và đáp ứng điều kiện nghiệp vụ. Lỗi ở chunk cuối có thể rollback toàn bộ thay đổi trước đó, nhưng transaction kéo dài có thể giữ nhiều lock và tài nguyên.
2. **Một transaction cho mỗi chunk:** commit từng chunk; lỗi ở chunk sau không rollback những chunk trước. Đây là xử lý **thành công một phần có chủ ý**, cần checkpoint, idempotency, kế hoạch tiếp tục và khả năng đối soát.

Không có một kích thước chunk chuẩn tối ưu cho mọi workload; cần đo throughput, latency, memory, lock duration và số lỗi trên môi trường đại diện. **`clearBatch()`** có thể xóa các lệnh đang chờ trên statement, nhưng **không rollback** những thay đổi SQL đã thực thi. Sau `BatchUpdateException`, lựa chọn an toàn thường là rollback transaction theo hợp đồng nghiệp vụ, sau đó tạo batch mới/statement mới theo quyết định retry; không giả định batch cũ còn đầy đủ để chạy lại.

### Retry sau `BatchUpdateException`

Trước khi retry, tự hỏi:

- Transaction chứa batch lỗi đã rollback thành công chưa?
- Driver dừng hay tiếp tục sau lỗi? Có câu lệnh nào đã được database xử lý trước khi mất kết nối không?
- Lỗi là tạm thời (deadlock, serialization failure) hay dữ liệu sai (trùng khóa, vi phạm `CHECK`)?
- Tác vụ có idempotency key/unique key/điểm checkpoint ổn định hay không?
- Nếu commit thất bại với kết quả không rõ, có thể truy vấn đối soát để tránh xử lý hai lần không?

**Không retry riêng các dòng có count khác `1`** nếu không hiểu hợp đồng giao dịch. Sau rollback thành công của transaction nguyên tử, **toàn bộ transaction** cần được xem xét retry với định danh request ổn định. Nếu chunk đã commit riêng, cần retry theo checkpoint và tránh chèn/cập nhật trùng.

## 10. Những lỗi diễn giải thường gặp

| Sai lầm | Vì sao sai? | Cách xử lý |
|---|---|---|
| `if (count < 0) throw ...` | `SUCCESS_NO_INFO = -2` là thành công | So sánh với hằng `Statement.SUCCESS_NO_INFO` và `EXECUTE_FAILED` trước |
| `Arrays.stream(counts).sum()` là tổng số hàng | `-2`/`-3` là mã trạng thái, không phải số hàng | Cộng riêng count không âm; công bố tổng là chưa đầy đủ nếu có `-2` |
| `count == 0` nghĩa SQL lỗi | `UPDATE` có thể hợp lệ nhưng không khớp hàng | Xử lý theo yêu cầu nghiệp vụ của từng lệnh |
| `executeBatch()` trả về nên đã commit | Batch execution và transaction commit là hai bước khác nhau khi `autoCommit=false` | Commit sau khi kiểm tra và rollback khi cần |
| `getUpdateCounts().length < input.size()` nghĩa các input còn lại đều không được chạy | Mảng chỉ mô tả trạng thái được driver báo, đặc biệt không đủ khi lỗi mạng | Theo hành vi driver; rollback và đối soát nếu trạng thái không rõ |
| `-3` là một lỗi có thể bỏ qua để commit phần còn lại | `EXECUTE_FAILED` đánh dấu lệnh lỗi | Áp dụng chính sách all-or-nothing hoặc partial success đã thiết kế |
| Count `1` chính là generated key `1` | Update count không phải khóa chính | Dùng `getGeneratedKeys()` hoặc API/SQL thích hợp |
| Dựa vào thứ tự hàng trả về từ `getGeneratedKeys()` mà không kiểm thử | Driver/DBMS có thể tối ưu lại batch và cách báo keys | Xác nhận tương thích hoặc dùng khóa do ứng dụng sinh |
| `clearBatch()` là rollback | Nó chỉ xử lý tập lệnh batch đang giữ | Dùng `Connection.rollback()` cho transaction |
| Retry mọi lệnh khi timeout | Một số thay đổi có thể đã commit nếu không rõ trạng thái | Dùng ID ổn định, checkpoint và đối soát |

## 11. Kiểm thử với driver và database thật

Mock `PreparedStatement` có thể giúp kiểm tra logic phân loại `-2` và `-3`, nhưng **không thể xác minh** driver thực sự trả count thế nào khi batch có constraint failure hoặc database thực thi song song. Nên có integration test trên đúng DBMS và phiên bản driver đang dùng.

| Tình huống | Cách thiết lập | Cần khẳng định |
|---|---|---|
| Mọi update khớp một hàng | 3 ID tồn tại | Đúng thứ tự 3 count, mỗi count được diễn giải theo driver |
| Có ID không tồn tại | Lệnh giữa batch dùng ID không tồn tại | `0` được xử lý như kết quả nghiệp vụ, không phải SQL exception |
| Câu lệnh vi phạm constraint | Batch chứa `INSERT` trùng `PRIMARY KEY` | Bắt `BatchUpdateException`; lưu `getUpdateCounts()` và SQLState |
| Driver dừng hay tiếp tục | Có câu lệnh hợp lệ đứng sau lệnh lỗi | Kiểm chứng chiều dài và mã `EXECUTE_FAILED` theo driver |
| Batch cần nguyên tử | Lệnh sau lỗi, lệnh trước cập nhật thành công | Sau rollback không còn thay đổi của transaction |
| Driver có `SUCCESS_NO_INFO` | Dùng tình huống/driver có hỗ trợ báo không xác định | Không cộng `-2` vào tổng, không coi là thất bại |
| Nhiều chunk | Chia input thành nhiều phần | Mapping local/global index và checkpoint chính xác |
| Failure khi rollback/close | Giả lập bằng lớp test/mô phỏng | Exception chính vẫn được giữ, lỗi cleanup nằm trong `suppressed` |
| Đọc số đếm lớn | Driver hỗ trợ `executeLargeBatch()` | Giữ `long[]` và các trạng thái đặc biệt |

### Bài thực hành

1. Tạo bảng `product_prices` như mục 3, chạy batch ba cập nhật cho các ID `101`, `102`, `103`. Giải thích vì sao kết quả minh họa `[1,0,1]` không đồng nghĩa “câu lệnh thứ hai lỗi SQL”.
2. Viết hàm nhận `int[]` để trả về **số count đã biết**, **số `SUCCESS_NO_INFO`** và danh sách chỉ mục có `EXECUTE_FAILED`. Thử `[2,-2,0,1]` và `[1,-3,1]`.
3. Tạo batch `INSERT` có hai lệnh dùng cùng `PRIMARY KEY`. Bắt `BatchUpdateException`, in `getUpdateCounts()`, `getSQLState()` và `getNextException()`; ghi nhận driver dừng hay tiếp tục sau lỗi.
4. Bật transaction thủ công, chạy batch có lệnh lỗi rồi gọi `rollback()`. Đọc lại bảng để chứng minh những cập nhật trước lỗi không còn được lưu.
5. Thử `executeLargeBatch()` và `getLargeUpdateCounts()` trên driver hiện tại, so sánh ý nghĩa `-2`/`-3` với phiên bản `int[]`.
6. Chia một danh sách thành ba chunk. Với lỗi ở local index `7` của chunk bắt đầu tại global index `400`, chỉ ra bản ghi đầu vào tương ứng và thiết kế checkpoint/retry phù hợp chính sách transaction.
7. Thảo luận tình huống nghiệp vụ “mỗi `UPDATE` phải khớp chính xác một hàng”: khi driver trả `SUCCESS_NO_INFO`, hãy chọn giữa rollback và xác minh bổ sung; giải thích giới hạn của từng lựa chọn.

**Tiêu chí hoàn thành:** người học giải thích chính xác ý nghĩa update count không âm, `Statement.SUCCESS_NO_INFO` và `Statement.EXECUTE_FAILED`; đọc `BatchUpdateException.getUpdateCounts()` trong cả hai tình huống driver dừng/tiếp tục; ánh xạ từng kết quả về lệnh input; quản lý transaction để tránh partial commit ngoài ý muốn; và thiết kế được kiểm thử, báo cáo số hàng, batching theo chunk cùng retry phù hợp.
