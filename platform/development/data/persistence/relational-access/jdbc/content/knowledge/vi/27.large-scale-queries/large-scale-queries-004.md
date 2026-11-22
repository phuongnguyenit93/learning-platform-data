# Đọc theo luồng và kiểm tra điều kiện do JDBC driver yêu cầu

Khi một truy vấn chỉ trả vài chục hàng, ứng dụng Java có thể đọc toàn bộ `ResultSet` vào một `List` mà không gặp vấn đề đáng kể. Nhưng với hàng trăm nghìn hoặc hàng triệu bản ghi, cách đó có thể làm heap tăng mạnh, gây nhiều lần thu gom rác (*GC*) và cuối cùng dẫn đến `OutOfMemoryError`. Một cách tiếp cận là **đọc và xử lý từng hàng theo luồng**, không giữ toàn bộ tập kết quả trong bộ nhớ ứng dụng.

Trong **JDBC**, việc gọi `ResultSet.next()` trong một vòng lặp **chưa đủ để chứng minh dữ liệu được truyền dần từ server**. Một số driver có thể tải hoặc đệm toàn bộ kết quả trước khi trả `ResultSet`; một số khác cần cấu hình fetch size, chế độ transaction hoặc kiểu con trỏ cụ thể để thực sự đọc theo từng đợt. Vì vậy, lập trình truy vấn quy mô lớn cần phối hợp **mã xử lý từng hàng**, **điều kiện của JDBC driver**, **vòng đời kết nối** và **kiểm thử tài nguyên**.

Bài thuộc chương **Truy vấn quy mô lớn** của module **JDBC**, sử dụng các API chuẩn như `DataSource`, `Connection`, `PreparedStatement`, `ResultSet` và `SQLException`. Nội dung tập trung vào hai câu hỏi: **làm sao xử lý dữ liệu với bộ nhớ có giới hạn** và **làm sao xác nhận driver thực sự đang sử dụng cơ chế fetch/streaming mong muốn**.

Sau bài học, bạn có thể:

- Phân biệt **đọc `ResultSet` từng hàng**, **fetch từng đợt từ DB** và **đọc từng phần một giá trị LOB**.
- Dùng `TYPE_FORWARD_ONLY`, `CONCUR_READ_ONLY` và `setFetchSize(...)` đúng ngữ cảnh.
- Nhận biết các điều kiện triển khai khác nhau ở PostgreSQL JDBC, MySQL Connector/J, SQL Server JDBC và Oracle JDBC.
- Viết một tác vụ xuất dữ liệu theo từng hàng, không tạo `List` chứa toàn bộ kết quả.
- Đóng tài nguyên đúng lúc và tránh giữ connection/transaction quá lâu khi đọc dữ liệu lớn.
- Đo bộ nhớ, thời gian, số lượt fetch và khả năng phục hồi khi truy vấn bị gián đoạn.

## 1. Ba khái niệm thường bị gọi chung là “streaming”

Cần tách ba tầng xử lý:

| Tầng | Mục tiêu | Ví dụ API hoặc cơ chế | Điều **không** được suy ra |
| --- | --- | --- | --- |
| **Xử lý từng hàng trong Java** | Không gom tất cả hàng vào `List` | `while (rs.next()) { processRow(rs); }` | Driver chắc chắn không tải sẵn toàn bộ kết quả |
| **Fetch từng đợt qua driver/DB** | Hạn chế lượng kết quả đang đệm giữa server và client | `Statement.setFetchSize(n)`, server cursor, driver streaming mode | Mọi driver đều hiểu `fetchSize` giống nhau |
| **Stream một giá trị lớn trong hàng** | Đọc BLOB/CLOB theo từng phần, không đưa cả LOB vào `byte[]` hoặc `String` | `getBinaryStream`, `getCharacterStream` | Bản thân các **hàng** của truy vấn cũng được fetch từng đợt |

Ví dụ một vòng lặp:

```java
try (ResultSet rs = statement.executeQuery()) {
    while (rs.next()) {
        long id = rs.getLong("event_id");
        // Xử lý ngay id, không đưa mọi hàng vào một List.
    }
}
```

Đoạn mã này tốt ở **tầng ứng dụng** vì không tích lũy tất cả hàng. Tuy nhiên, trước khi `executeQuery()` trả về, driver **có thể** đã nhận và lưu một phần lớn hoặc toàn bộ dữ liệu. Muốn biết liệu memory của driver có được giới hạn thực sự hay không, phải hiểu khả năng và cấu hình của driver đang dùng.

### Hai mô hình cấp phát bộ nhớ

```text
Cách A: gom tất cả hàng

DB -> JDBC -> ResultSet -> List<Row> chứa hàng triệu đối tượng
                                    |
                              Heap tăng theo N

Cách B: xử lý từng hàng và fetch theo đợt (khi driver hỗ trợ)

DB -> cursor/fetch -> vùng đệm driver có giới hạn -> ResultSet.next()
                                                      |
                                              xử lý/ghi đầu ra
                                                      |
                                              bỏ tham chiếu hàng
```

Với cách B, mục tiêu là giữ **bộ nhớ tăng theo kích thước vùng đệm và hàng đang xử lý**, thay vì tăng tuyến tính theo tổng số hàng. Đây là mục tiêu thiết kế cần **đo và xác minh**, không phải một bảo đảm mà mọi lệnh `setFetchSize` tự động cung cấp.

## 2. `TYPE_FORWARD_ONLY`, `CONCUR_READ_ONLY` và `setFetchSize`

Để diễn đạt ý định đọc tuần tự, `Connection.prepareStatement` có overload chỉ định loại và khả năng cập nhật của `ResultSet`:

```java
String sql = "SELECT event_id, event_type FROM audit_event ORDER BY event_id";

try (PreparedStatement statement = connection.prepareStatement(
        sql,
        ResultSet.TYPE_FORWARD_ONLY,
        ResultSet.CONCUR_READ_ONLY)) {

    statement.setFetchSize(256);

    try (ResultSet rs = statement.executeQuery()) {
        while (rs.next()) {
            // Xử lý hàng hiện tại rồi chuyển tới hàng kế tiếp.
        }
    }
}
```

Các lựa chọn có ý nghĩa riêng:

- **`TYPE_FORWARD_ONLY`**: yêu cầu con trỏ tiến về phía trước. Tránh cần khả năng di chuyển ngược hoặc tới vị trí bất kỳ, vốn có thể buộc driver đệm nhiều dữ liệu hơn.
- **`CONCUR_READ_ONLY`**: cho biết ứng dụng không cần cập nhật hàng thông qua `ResultSet`. Điều này có thể cho phép driver dùng đường đọc đơn giản hơn.
- **`setFetchSize(256)`**: cung cấp **gợi ý** về số hàng nên fetch trong một đợt. Giá trị dương có ý nghĩa với nhiều driver, nhưng driver có thể diễn giải khác hoặc bỏ qua tùy ngữ cảnh.

`setFetchSize` không phải “giới hạn tối đa 256 hàng được trả”. Nếu truy vấn có một triệu hàng, vòng lặp vẫn có thể đi qua toàn bộ một triệu hàng. Nó cũng không bảo đảm driver chỉ cấp phát đúng 256 đối tượng; metadata, bộ đệm giao thức, chuyển đổi cột và cách triển khai đều ảnh hưởng mức sử dụng bộ nhớ.

### `fetchSize = 0` nghĩa là gì?

Theo JDBC, `0` thường có nghĩa driver được phép tự quyết định fetch size mặc định. **Không nên đồng nhất `0` với một kích thước cố định hoặc với streaming mode.** Một số driver mặc định đệm toàn bộ kết quả, trong khi driver khác áp dụng cơ chế fetch linh hoạt. Giá trị thực tế cần xem tài liệu và kiểm thử phiên bản driver.

Một số driver dùng **giá trị đặc biệt** (ví dụ `Integer.MIN_VALUE` ở cơ chế streaming riêng của MySQL Connector/J). Đây là ngoại lệ theo **quy ước của driver**, không phải ý nghĩa tiêu chuẩn “fetch âm” của JDBC. Không đem mẹo của một driver áp dụng cho mọi DBMS.

### Fetch size không phải max rows hay phân trang

| API hoặc cách làm | Tác dụng | Có tương đương streaming không? |
| --- | --- | --- |
| `setFetchSize(256)` | Gợi ý số hàng driver nên fetch mỗi đợt | Không bảo đảm, phải kiểm chứng |
| `setMaxRows(1000)` | Giới hạn số hàng tối đa của một kết quả theo hỗ trợ JDBC | Không chứng minh 1000 hàng được fetch dần |
| `WHERE id > ? ORDER BY id` + giới hạn trang | Chia tổng dữ liệu thành nhiều truy vấn có kích thước hữu hạn | Là chiến lược **phân trang**, không phải một cursor dài |
| `while (rs.next())` | Xử lý từng hàng của `ResultSet` | Chỉ bảo đảm vòng lặp Java không tự tích lũy hàng |

Nếu mục tiêu là xử lý **một số lượng hữu hạn** dữ liệu mỗi request, phân trang có thể phù hợp hơn một truy vấn streaming kéo dài rất lâu.

## 3. Điều kiện đọc theo luồng khác nhau giữa các JDBC driver

Không có một bộ tham số JDBC duy nhất bảo đảm streaming giống nhau cho PostgreSQL, MySQL, SQL Server và Oracle. Một số trường hợp thường gặp:

| DB/driver | Điểm cần kiểm tra | Giới hạn cần nhớ |
| --- | --- | --- |
| **PostgreSQL JDBC (pgJDBC)** | Để dùng cursor fetch thông thường: `autoCommit = false`, `TYPE_FORWARD_ONLY`, `fetchSize > 0` và câu lệnh/kết quả đáp ứng điều kiện cursor của driver | Nếu thiếu điều kiện, driver có thể lấy toàn bộ kết quả; cursor gắn với transaction và connection |
| **MySQL Connector/J** | Có các cơ chế khác nhau: cursor-based fetch với cấu hình như `useCursorFetch=true` và fetch size dương; cơ chế streaming cũ có thể dùng forward-only/read-only với `Integer.MIN_VALUE` | Kiểm tra phiên bản, khả năng server-side prepared statements, cách cấu hình và điều kiện của từng chế độ; không trộn hai cơ chế theo suy đoán |
| **Microsoft JDBC Driver for SQL Server** | Kiểm tra chiến lược đệm kết quả như `responseBuffering=adaptive`, loại cursor và hành vi khi đọc cột lớn | `setFetchSize` không phải lời hứa dùng server cursor hoặc giới hạn chính xác memory cho mọi kết quả |
| **Oracle JDBC** | Kiểm tra row prefetch/fetch size, loại result set và cách driver đọc LOB | `setFetchSize` có thể điều khiển số hàng prefetch nhưng không tương đương một cơ chế streaming chung ở mọi driver |

**Các mục này là những điểm cần kiểm chứng, không phải bảng cấu hình copy-paste áp dụng mọi phiên bản.** Driver có thể thay đổi mặc định, giao thức hoặc tên thuộc tính khi nâng cấp. Với những hệ quản trị khác, hãy đọc tài liệu của chính driver tương ứng.

### PostgreSQL: vì sao `autoCommit = false` thường quan trọng?

Với cơ chế cursor-based fetching của pgJDBC, server cursor cần tồn tại trong một transaction. Nếu ứng dụng để `autoCommit = true`, transaction có thể kết thúc ngay sau khi câu lệnh thực thi theo chế độ thông thường; driver có thể không sử dụng đường fetch cursor như mong muốn và nạp toàn bộ dữ liệu.

Một mô hình thường dùng:

```java
try (Connection connection = dataSource.getConnection()) {
    connection.setAutoCommit(false);

    try (PreparedStatement statement = connection.prepareStatement(
            "SELECT event_id FROM audit_event ORDER BY event_id",
            ResultSet.TYPE_FORWARD_ONLY,
            ResultSet.CONCUR_READ_ONLY)) {

        statement.setFetchSize(256);

        try (ResultSet rs = statement.executeQuery()) {
            while (rs.next()) {
                // Đọc lần lượt, không giữ toàn bộ hàng.
            }
        }
    }

    connection.commit(); // Kết thúc transaction đọc.
}
```

Ví dụ thể hiện các điều kiện cốt lõi thường được tài liệu pgJDBC nêu, nhưng **chưa có nhánh rollback khi lỗi**; xem ví dụ đầy đủ phần sau. `setAutoCommit(false)` không nhất thiết là yêu cầu của mọi driver. Với PostgreSQL, giữ transaction đọc rất lâu còn có thể ảnh hưởng khả năng dọn phiên bản hàng theo MVCC, nên cần đặt giới hạn thời gian và khối lượng dữ liệu phù hợp.

### MySQL: hai cơ chế rất dễ nhầm

Với **MySQL Connector/J**, cần phân biệt:

1. **Cursor-based fetching** theo cơ chế cấu hình hỗ trợ cursor của driver, thường gắn với `useCursorFetch=true`, server-side prepared statement và `setFetchSize(n)` dương.
2. **Streaming result set** theo cơ chế riêng có thể yêu cầu `TYPE_FORWARD_ONLY`, `CONCUR_READ_ONLY` và `setFetchSize(Integer.MIN_VALUE)` trên những phiên bản hỗ trợ.

Đừng mặc định chỉ thêm `setFetchSize(100)` vào ứng dụng MySQL đang dùng cấu hình mặc định là chắc chắn đã chuyển sang fetch cursor. Cũng đừng đặt `Integer.MIN_VALUE` trong mã dùng chung cho PostgreSQL hay Oracle. Hãy chọn **một cơ chế được tài liệu driver/phiên bản xác nhận**, chạy integration test kiểm tra memory và hành vi kết nối.

Với một số chế độ streaming của Connector/J, trong lúc `ResultSet` lớn còn mở, kết nối có thể bị ràng buộc vào việc đọc hết kết quả; thực hiện một truy vấn khác trên **cùng connection** có thể bị từ chối hoặc buộc kết quả cũ phải được đóng/tiêu thụ theo chính sách driver. Đây là lý do không nên vừa giữ một `ResultSet` streaming vừa chạy các truy vấn lookup bổ sung trên chính kết nối đó cho từng hàng.

### SQL Server và Oracle: đừng suy diễn từ kích thước fetch

Microsoft JDBC Driver có các lựa chọn về cách đệm phản hồi, còn Oracle JDBC có cơ chế row prefetch. Dù cả hai có thể đọc kết quả lớn hiệu quả, việc `statement.getFetchSize()` trả một số dương **không tự chứng minh** server đang giữ cursor theo cùng ngữ nghĩa với pgJDBC. Một câu truy vấn có các cột LOB, loại cursor đặc biệt hoặc một phương thức getter khác có thể có hành vi bộ nhớ riêng.

Trong mọi trường hợp, đừng chỉ kiểm tra một thuộc tính cấu hình. Hãy theo dõi mức heap/driver memory, số hàng đã xử lý trước khi tăng bộ nhớ, số lượt trao đổi với DB và trạng thái connection khi đóng kết quả sớm.

## 4. Thiết kế truy vấn để streaming có ý nghĩa

Giả sử hệ thống bán hàng cần xuất một tập đơn hàng lớn. Bảng minh họa:

```sql
CREATE TABLE sales_order (
    order_id     BIGINT PRIMARY KEY,
    customer_id  BIGINT NOT NULL,
    total_amount DECIMAL(14, 2) NOT NULL,
    order_status VARCHAR(20) NOT NULL
);
```

Câu SQL xuất dữ liệu theo khóa chính:

```sql
SELECT order_id, customer_id, total_amount, order_status
FROM sales_order
WHERE order_id > ?
ORDER BY order_id;
```

Đây là câu SQL **tham số hóa**: caller truyền khóa bắt đầu, không ghép giá trị vào chuỗi truy vấn. `ORDER BY order_id` cung cấp thứ tự ổn định theo khóa duy nhất trong một lần thực thi, hữu ích cho việc kiểm tra, ghi file và thiết kế resume theo khóa.

Nhưng cần nhớ: **streaming giảm nhu cầu đệm dữ liệu ở client; nó không tự làm câu SQL trên server chạy nhanh**. Nếu truy vấn có `ORDER BY` trên cột không có index, `DISTINCT`, `GROUP BY`, `JOIN` rộng hoặc phép sắp xếp lớn, DB có thể cần xử lý nhiều dữ liệu trước khi trả hàng đầu tiên. Kế hoạch truy vấn, index, kích thước hàng và số cột luôn quan trọng.

### Những điều nên chuẩn bị trước khi đọc hàng triệu bản ghi

- Chỉ lấy **cột cần xuất**, không dùng `SELECT *` nếu có BLOB/CLOB hoặc cột không liên quan.
- Dùng điều kiện `WHERE` theo nghiệp vụ để giảm tập dữ liệu cần đọc.
- Chọn `ORDER BY` có ý nghĩa khi cần kết quả có thứ tự; tạo index tương ứng khi hợp lý.
- Không thực hiện một `SELECT` bổ sung cho **mỗi hàng** (*N+1 queries*) trong khi vẫn giữ cursor lớn mở.
- Dự trù nơi nhận kết quả: file, network stream, bộ xử lý tổng hợp hoặc pipeline; không gọi `.toList()` cho toàn bộ kết quả nếu mục tiêu là tiết kiệm bộ nhớ.
- Xác định cơ chế hủy tác vụ và đóng kết nối khi client ngắt giữa chừng.

## 5. Ví dụ JDBC đầy đủ: xuất CSV từng hàng, không tạo `List`

Ví dụ sau dùng Java 17+, `DataSource` được cấu hình sẵn và một `Writer` do caller cung cấp. Nó lấy từng hàng từ `ResultSet`, ghi thành CSV và bỏ tham chiếu dữ liệu sau khi xử lý. Mã sử dụng `TYPE_FORWARD_ONLY`, `CONCUR_READ_ONLY`, `setFetchSize(256)` và một transaction đọc rõ ràng để tương thích với những driver yêu cầu `autoCommit = false` cho cursor fetch.

Tệp minh họa `OrderCsvExporter.java`:

```java
import java.io.IOException;
import java.io.Writer;
import java.math.BigDecimal;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.Objects;
import javax.sql.DataSource;

public final class OrderCsvExporter {
    private static final String SQL = """
            SELECT order_id, customer_id, total_amount, order_status
            FROM sales_order
            WHERE order_id > ?
            ORDER BY order_id
            """;

    private static final int FETCH_SIZE = 256;

    private final DataSource dataSource;

    public OrderCsvExporter(DataSource dataSource) {
        this.dataSource = Objects.requireNonNull(dataSource, "dataSource");
    }

    // Writer do caller sở hữu; phương thức này không đóng Writer.
    public long exportAfter(long lastSeenId, Writer output)
            throws SQLException, IOException {

        if (lastSeenId < 0) {
            throw new IllegalArgumentException("lastSeenId must be nonnegative");
        }
        Objects.requireNonNull(output, "output");

        try (Connection connection = dataSource.getConnection()) {
            // Đây là hint cho driver/DB; cần kiểm tra hỗ trợ thực tế.
            connection.setReadOnly(true);
            connection.setAutoCommit(false);

            try {
                long exported = 0;

                try (PreparedStatement statement = connection.prepareStatement(
                        SQL,
                        ResultSet.TYPE_FORWARD_ONLY,
                        ResultSet.CONCUR_READ_ONLY)) {

                    statement.setLong(1, lastSeenId);
                    statement.setFetchSize(FETCH_SIZE);

                    try (ResultSet rs = statement.executeQuery()) {
                        output.write(
                                "order_id,customer_id,total_amount,order_status\r\n");

                        while (rs.next()) {
                            long orderId = rs.getLong("order_id");
                            long customerId = rs.getLong("customer_id");
                            BigDecimal amount = rs.getBigDecimal("total_amount");
                            String status = rs.getString("order_status");

                            if (amount == null || status == null) {
                                throw new SQLException(
                                        "Unexpected NULL in non-null order fields");
                            }

                            // Chỉ xây dựng một dòng CSV tại một thời điểm.
                            output.write(Long.toString(orderId));
                            output.write(',');
                            output.write(Long.toString(customerId));
                            output.write(',');
                            output.write(amount.toPlainString());
                            output.write(',');
                            output.write(csvText(status));
                            output.write("\r\n");
                            exported++;
                        }
                    }
                }

                output.flush();
                connection.commit(); // Kết thúc transaction chỉ đọc.
                return exported;
            } catch (SQLException | IOException | RuntimeException failure) {
                try {
                    connection.rollback();
                } catch (SQLException rollbackFailure) {
                    failure.addSuppressed(rollbackFailure);
                }
                throw failure;
            }
        }
    }

    private static String csvText(String text) {
        // Quote và nhân đôi dấu nháy để giữ đúng định dạng CSV.
        return "\"" + text.replace("\"", "\"\"") + "\"";
    }
}
```

Ví dụ caller tạo file qua `java.nio.file`:

```java
import java.io.BufferedWriter;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

OrderCsvExporter exporter = new OrderCsvExporter(dataSource);
Path target = Path.of("orders-export.csv");

try (BufferedWriter writer = Files.newBufferedWriter(
        target, StandardCharsets.UTF_8)) {
    long rows = exporter.exportAfter(0L, writer);
    System.out.println("Exported rows: " + rows);
}
```

Khi ghi CSV từ dữ liệu không tin cậy để mở trong phần mềm bảng tính, ứng dụng còn cần chính sách chống *CSV formula injection* đối với trường văn bản bắt đầu bằng các ký tự được phần mềm bảng tính diễn giải là công thức. Hàm `csvText` ở trên chỉ đảm bảo **cú pháp CSV**, không phải lớp phòng vệ công thức hoặc bộ quy tắc encoding cho mọi ứng dụng xuất file.

### Điều gì khiến ví dụ tiết kiệm bộ nhớ?

1. Không tạo `List<OrderRow>` chứa toàn bộ hàng.
2. Mỗi vòng lặp đọc vài giá trị và ghi ngay tới `Writer`.
3. `ResultSet` được đóng trước statement; statement được đóng trước khi transaction kết thúc.
4. `setFetchSize(256)` thể hiện yêu cầu fetch theo đợt, nhưng **chỉ thực sự giảm đệm driver nếu driver/DB đáp ứng các điều kiện của nó**.
5. `Writer` có thể là `BufferedWriter` ra file; nếu caller truyền `StringWriter`, **toàn bộ CSV sẽ vẫn nằm trong bộ nhớ**, phá mục tiêu tiết kiệm heap.

Đầu ra CSV cũng là một tác động **nằm ngoài transaction JDBC**. Nếu kết nối DB lỗi sau khi đã ghi một nửa file, `connection.rollback()` không xóa một nửa file đó. Trong hệ thống sản xuất, có thể xuất ra **file tạm**, chỉ đổi tên/thông báo “hoàn thành” khi đọc hết và flush thành công, rồi dọn file tạm nếu lỗi. Cần cẩn thận với lỗi không rõ tại bước kết thúc và quy tắc tồn tại file tạm của hệ điều hành.

### Vì sao dùng `connection.setReadOnly(true)`?

`Connection.setReadOnly(true)` là một **gợi ý về dự định chỉ đọc**, không bảo đảm DB cấm mọi lệnh ghi hoặc tự giúp truy vấn streaming. Một số driver/DB có thể không hỗ trợ thay đổi thuộc tính này trong một số trạng thái transaction. Ví dụ gọi trước `setAutoCommit(false)` và trước truy vấn; nếu môi trường không hỗ trợ, có thể xử lý bằng cấu hình riêng phù hợp driver thay vì coi nó là điều kiện bắt buộc để streaming hoạt động.

`setAutoCommit(false)` trong ví dụ là lựa chọn rõ ràng để hỗ trợ các driver yêu cầu transaction cho server cursor (đặc biệt pgJDBC). Nó cũng có chi phí: giữ transaction trong suốt lúc ghi file. Với MySQL/SQL Server/Oracle, điều kiện cụ thể có thể khác. **Không biến ví dụ thành quy tắc phổ quát mà không xem tài liệu driver.**

## 6. Đọc dữ liệu LOB: một dạng streaming khác

Đọc từng hàng theo luồng chưa đủ nếu **một hàng** chứa BLOB 500 MB. `ResultSet.getBytes(...)` có thể tạo một mảng lớn; `getString(...)` trên CLOB dài có thể tạo chuỗi lớn. Khi cần truyền nội dung nguyên vẹn ra file hoặc network stream, có thể dùng:

```java
import java.io.InputStream;
import java.io.OutputStream;
import java.sql.ResultSet;

// rs đang đứng trên một hàng chứa cột BLOB tên payload.
// destination là OutputStream mà caller đã mở cho hàng này.
try (InputStream input = rs.getBinaryStream("payload")) {
    if (input != null) {
        input.transferTo(destination);
    }
}
```

`getBinaryStream` dành cho dữ liệu nhị phân; `getCharacterStream` phù hợp văn bản lớn. `InputStream.transferTo(...)` có trong Java 9+, ví dụ chính dùng Java 17+. Nếu driver trả `null`, phải phân biệt SQL `NULL` với BLOB rỗng theo hợp đồng cột.

**Quy tắc vòng đời:** đọc xong và đóng stream của hàng hiện tại **trước khi gọi `rs.next()`** hoặc đọc một cột khác có thể ảnh hưởng tới dữ liệu đang stream, vì JDBC driver có thể đóng hoặc thay đổi trạng thái stream khi di chuyển con trỏ. `destination` do caller sở hữu; không đóng stream đích bên trong một helper nếu caller còn cần dùng nó.

LOB streaming không bảo đảm driver chưa đệm dữ liệu lớn trước đó; cần kiểm thử cả chế độ row fetch và cách getter LOB hoạt động. Khi file được tạo từ hàng cơ sở dữ liệu, còn cần quy định đặt tên file an toàn, giới hạn dung lượng, quyền truy cập và dọn file nếu stream bị cắt giữa chừng.

## 7. Vòng đời cursor, transaction và connection pool

Một truy vấn streaming có thể giữ **kết nối vật lý được mượn từ pool** trong suốt quá trình đọc. Nếu xuất một triệu hàng mất 15 phút, kết nối ấy cũng có thể bị chiếm 15 phút; trên DB có server cursor, cursor và trạng thái transaction có thể tồn tại cùng khoảng thời gian.

| Tài nguyên | Điều xảy ra khi streaming kéo dài |
| --- | --- |
| `Connection` trong pool | Không được trả về pool cho đến khi ứng dụng đóng nó |
| `PreparedStatement` | Gắn với kết quả hiện tại; có thể giữ handle/cursor trên server |
| `ResultSet` | Giữ con trỏ và bộ đệm driver tới khi đọc hết hoặc đóng |
| Transaction | Có thể giữ snapshot, khóa hoặc tài nguyên MVCC tùy isolation/DB |
| `Writer`/network đích | Nếu đầu nhận chậm, luồng đọc DB cũng chậm theo (*backpressure*) |
| Heap/JVM | Bộ đệm JDBC, hàng hiện tại, bộ đệm xuất và LOB đều góp vào mức sử dụng |

**Không được chia sẻ một `ResultSet` đang streaming giữa các thread** với giả định chúng có thể gọi `next()` đồng thời. `ResultSet` và `PreparedStatement` giữ trạng thái, driver không bảo đảm mô hình đa luồng này an toàn. Cũng không nên dùng một connection đang stream kết quả lớn để thực hiện đồng thời các `UPDATE` hoặc tra cứu bổ sung cho từng hàng.

### Đóng sớm khi không cần đọc hết

Nếu gặp điều kiện dừng (ví dụ chỉ muốn xử lý 10.000 hàng đầu), hãy thoát vòng lặp rồi để `try-with-resources` đóng `ResultSet`, statement và connection theo đúng thứ tự. **Không cần tiêu thụ hết mọi hàng chỉ để cho phép đóng kết quả**, nhưng một số driver có thể xử lý các dữ liệu chưa đọc khi đóng/cancel theo cách riêng, dẫn đến độ trễ hoặc chi phí mạng. Hãy thử tình huống hủy giữa chừng trên driver thực tế.

Có thể dùng `Statement.cancel()` để yêu cầu hủy một câu lệnh đang chạy, nhưng đây không phải cam kết hủy tức thì trên mọi DB. Việc đóng kết nối cũng không thay thế chiến lược timeout và cancellation được kiểm chứng. Với tác vụ dài, nên có cơ chế hủy có kiểm soát và luôn đóng tài nguyên trong `finally`/`try-with-resources`.

### Transaction đọc dài không hoàn toàn miễn phí

Ngay cả khi chỉ `SELECT`, một transaction kéo dài có thể giữ snapshot hoặc ảnh hưởng việc dọn phiên bản cũ của hàng theo hệ quản trị. Ở những isolation level cao, phạm vi khóa/snapshot và khả năng tranh chấp có thể khác đáng kể. Nếu export kéo dài quá lâu, cân nhắc **phân trang theo khóa** và kết thúc transaction sau mỗi trang — nhưng điều đó thay đổi tính nhất quán của ảnh chụp dữ liệu giữa các trang. Sự lựa chọn phải dựa trên yêu cầu nghiệp vụ.

## 8. Streaming so với phân trang theo khóa (*keyset pagination*)

Không phải cứ có hàng triệu hàng là cần giữ một cursor mở cho đến khi đọc hết. Một lựa chọn là truy vấn từng trang với kích thước giới hạn:

```sql
SELECT order_id, customer_id, total_amount, order_status
FROM sales_order
WHERE order_id > ?
ORDER BY order_id
FETCH FIRST 500 ROWS ONLY;
```

`FETCH FIRST ... ROWS ONLY` là cú pháp minh họa theo SQL standard; các DB có thể dùng `LIMIT`, `TOP`, `OFFSET ... FETCH` hoặc cú pháp khác. Mỗi trang được xử lý xong rồi đóng statement/connection, sau đó dùng **khóa `order_id` cuối cùng đã xử lý** làm điểm bắt đầu trang tiếp theo.

| Yếu tố | Streaming một `ResultSet` lớn | Keyset pagination theo trang |
| --- | --- | --- |
| Số lần mở truy vấn | Thường một truy vấn dài | Nhiều truy vấn ngắn |
| Thời gian chiếm connection | Có thể rất dài | Có thể trả connection giữa các trang |
| Bộ nhớ ứng dụng | Thấp khi driver fetch đúng và xử lý từng hàng | Bị chặn trên mỗi trang nếu không gom vô hạn |
| Snapshot dữ liệu | Có thể có một ảnh chụp tương đối nhất quán tùy isolation/DB | Các trang ở transaction khác nhau có thể thấy thay đổi khác nhau |
| Khả năng tiếp tục sau lỗi | Thường phải tự thiết kế checkpoint; cursor cũ không sống qua mất kết nối | Dễ lưu khóa cuối và truy vấn trang tiếp theo hơn |
| Tương thích driver | Phụ thuộc điều kiện streaming/cursor của driver | Ít phụ thuộc streaming, nhưng phụ thuộc cú pháp pagination của DB |

Keyset pagination tránh chi phí bỏ qua ngày càng nhiều hàng như `OFFSET` lớn trong một số workload có index phù hợp. Tuy nhiên, **thêm/xóa/cập nhật dữ liệu đồng thời vẫn có thể ảnh hưởng tập kết quả**. Nếu yêu cầu export đúng một ảnh chụp dữ liệu tại một thời điểm, phải xác định transaction isolation, snapshot hoặc bộ lọc mốc thời gian/phiên bản phù hợp; không thể chỉ dùng `order_id > lastId` rồi mặc định tập kết quả bất biến.

Khi resume sau lỗi, checkpoint phải gắn với **đầu ra đã ghi bền vững**. Chỉ lưu “ID cuối đã đọc trong RAM” mà không bảo đảm dòng CSV tương ứng đã được flush và chấp nhận có thể làm mất hoặc lặp dữ liệu khi chạy tiếp.

## 9. Kiểm tra driver có thực sự dùng streaming không?

Thành công của `statement.setFetchSize(256)` hoặc việc `statement.getFetchSize()` trả `256` **không chứng minh** dữ liệu được fetch theo đợt trên server. Đó chỉ là thông tin API ở phía Java. Để xác nhận, cần phối hợp **kiểm tra hỗ trợ**, **kiểm thử hành vi** và **quan sát tài nguyên**.

### A. Kiểm tra metadata về loại result set

JDBC có thể hỏi khả năng hỗ trợ loại `ResultSet` và concurrency:

```java
var metadata = connection.getMetaData();

boolean forwardOnly = metadata.supportsResultSetType(
        ResultSet.TYPE_FORWARD_ONLY);

boolean readOnly = metadata.supportsResultSetConcurrency(
        ResultSet.TYPE_FORWARD_ONLY,
        ResultSet.CONCUR_READ_ONLY);

System.out.println("Forward-only supported: " + forwardOnly);
System.out.println("Forward-only/read-only supported: " + readOnly);
```

Trong đoạn này, `connection` là kết nối JDBC đã mở. Metadata giúp biết driver **báo có hỗ trợ** kiểu con trỏ, nhưng không khẳng định server cursor đã được dùng hay bộ nhớ bị giới hạn. Một số driver có thể thay đổi loại result set theo khả năng thật hoặc SQL thực thi; vì vậy, trên một `ResultSet` có thể kiểm tra `rs.getType()`/`rs.getConcurrency()` nếu cần chẩn đoán. Điều kiện streaming vẫn phải đối chiếu tài liệu driver.

### B. Kiểm tra cấu hình và phiên bản driver

Một bản ghi kiểm thử nên lưu:

- Tên DBMS, phiên bản DBMS, tên JDBC driver và phiên bản driver (`Connection.getMetaData()`).
- URL/các thuộc tính kết nối liên quan tới fetch mode, server-side prepare hoặc buffering — **không ghi mật khẩu hay thông tin bí mật**.
- Giá trị `autoCommit`, result-set type/concurrency, fetch size, isolation level và kích thước truy vấn.
- Tình huống driver không hỗ trợ hint hoặc tự điều chỉnh chế độ khi gặp LOB/scrollability.

Metadata không có một phương thức chuẩn kiểu `isResultSetStreaming()` cho mọi driver. Nếu driver không cung cấp metrics fetch/cursor, phải dựa vào **bằng chứng hành vi**.

### C. Đo bộ nhớ và thời điểm nhận hàng đầu tiên

Thiết kế một bài thử với hàng trăm nghìn hàng có kích thước dự đoán được:

1. **Baseline:** chạy câu SQL với cấu hình mặc định, đọc từng hàng và ghi ra một đầu nhận không giữ tất cả dữ liệu.
2. **Ứng viên streaming:** dùng cấu hình driver đề xuất, cùng SQL và cùng bộ dữ liệu; ghi nhận heap usage, GC và bộ nhớ tiến trình.
3. Đo **thời gian từ `executeQuery()` đến hàng đầu tiên** và tổng thời gian đọc toàn bộ, phân biệt thời gian chuẩn bị/truy vấn với thời gian xử lý từng hàng.
4. Quan sát server cursor, fetch calls hoặc driver logs nếu công cụ của sản phẩm có cung cấp.
5. Tăng tổng số hàng trong khi giữ fetch size cố định; kiểm tra mức bộ nhớ có tăng gần tuyến tính theo tổng số hàng không.
6. Thử **đóng result set sớm**, hủy giữa chừng và dùng một truy vấn khác sau khi đóng để xác minh connection không bị kẹt.

Mức heap ổn định là một dấu hiệu tốt nhưng không đủ để khẳng định tuyệt đối driver không đệm dữ liệu ngoài heap, và thời gian tới hàng đầu tiên còn bị ảnh hưởng bởi `ORDER BY`, index, network và khả năng DB phải thực hiện phép toán blocking. Cần kết hợp nhiều bằng chứng trước khi đưa ra kết luận.

### D. Kiểm tra giới hạn tài nguyên của hệ thống

| Chỉ số | Câu hỏi cần trả lời |
| --- | --- |
| Heap và GC của JVM | Có đang tạo hàng triệu đối tượng hoặc giữ toàn bộ kết quả? |
| Bộ nhớ tiến trình/native buffers | Driver có thể dùng bộ nhớ ngoài heap không? |
| Pool active/idle/pending connections | Có tác vụ streaming giữ hết kết nối của pool? |
| Session/cursor/transaction trên DB | Có cursor hoặc transaction đọc kéo dài bất thường? |
| Lưu lượng mạng và thời gian fetch | Dữ liệu đến theo đợt hay bị tải trước quá nhiều? |
| Thời gian `executeQuery()` và `next()` | Bước nào thực sự gây chờ? |
| Timeout và cancellation | Khi bên nhận chậm hoặc hủy, tài nguyên có được trả về? |

Nếu ứng dụng xuất dữ liệu qua HTTP, tốc độ đọc của client có thể chậm hơn tốc độ DB. Khi đó giữ connection DB trong khi `Writer` chờ network là một rủi ro về thông lượng. Cân nhắc xuất ra file tạm hoặc pipeline có giới hạn bộ đệm, hoặc phân trang từng đợt để tránh giữ transaction dài quá mức.

## 10. Timeout, lỗi và cách tiếp tục khi đọc lớn

Một truy vấn dài có nhiều điểm có thể thất bại: ngay lúc `executeQuery`, trong `rs.next()`, khi giải mã một cột, khi ghi đầu ra hoặc khi đóng result set. Vì thế, `try-with-resources` phải bao quanh **toàn bộ quá trình đọc**, không chỉ phần chuẩn bị câu lệnh.

```java
try (Connection connection = dataSource.getConnection();
     PreparedStatement statement = connection.prepareStatement(SQL)) {

    statement.setFetchSize(256);
    try (ResultSet rs = statement.executeQuery()) {
        while (rs.next()) {
            // Mỗi rs.next()/getXxx đều có thể ném SQLException.
        }
    }
}
```

`Statement.setQueryTimeout(int seconds)` có thể giới hạn thời gian thực thi câu lệnh theo mức hỗ trợ của driver; `Connection.setNetworkTimeout(...)` liên quan timeout cho hoạt động mạng theo hợp đồng JDBC. **Không** mặc định các API này bảo đảm một tổng thời gian tuyệt đối cho toàn bộ quá trình xử lý hàng triệu hàng hoặc thay thế lock timeout do DB cấu hình. Với một số driver, timeout có thể được áp dụng khác nhau cho `executeQuery` và các lần fetch tiếp theo.

Khi xảy ra `SQLException` giữa quá trình đọc, **không được** tiếp tục coi kết quả đã hoàn tất. Đóng các tài nguyên, kết thúc hoặc rollback transaction nếu đang sở hữu nó, ghi nhận số hàng đã xử lý và thông tin checkpoint đã được xác nhận bền vững. Với lỗi mạng ở đầu ra, có thể dữ liệu đã ghi một phần; rollback DB không thu hồi nội dung file hay HTTP response.

### Retry thế nào để không thiếu hoặc trùng hàng?

Nếu chỉ đọc để tính tổng số liệu, chạy lại từ đầu có thể an toàn về mặt thay đổi DB nhưng gây tốn kém. Nếu đang xuất dữ liệu cho hệ thống khác hoặc tạo file, retry từ đầu có thể tạo **nội dung trùng**. Một chiến lược resume phải xác định:

- Khóa sắp xếp duy nhất và điều kiện truy vấn tiếp tục (`id > lastConfirmedId`).
- “Đã xác nhận” có nghĩa **đầu nhận đã lưu bền vững** hàng trước đó, không chỉ Java đã gọi `output.write`.
- Cách xử lý hàng bị thêm, xóa hoặc chỉnh sửa sau lần truy vấn trước.
- Chữ ký hoặc mã định danh của lần export để không ghép nhầm dữ liệu giữa hai cấu hình khác nhau.
- Chính sách đối soát tổng số hàng và kiểm tra tính toàn vẹn đầu ra.

Đừng coi cursor ở server là checkpoint có thể khôi phục sau khi mất connection; phần lớn cursor liên quan tới session/transaction của kết nối cũ và không thể tiếp tục tùy ý từ một connection mới.

## 11. Những lỗi thiết kế phổ biến

| Sai lầm | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Gọi `while (rs.next())` rồi tuyên bố driver streaming | Driver có thể đã đệm toàn bộ tập kết quả | Kiểm tra fetch mode, transaction, cấu hình và đo bộ nhớ |
| Gọi `setFetchSize(256)` rồi mặc định mọi driver tuân thủ | Fetch hint có thể bị bỏ qua hoặc được diễn giải khác | Xem tài liệu driver, đo hành vi thực tế |
| Giữ `autoCommit = true` khi trông chờ pgJDBC cursor fetch | Có thể không dùng đường cursor mong muốn | Dùng transaction đúng điều kiện pgJDBC, đóng/commit sớm |
| Dùng `Integer.MIN_VALUE` cho mọi driver | Không phải giá trị streaming chuẩn JDBC | Chỉ dùng quy ước này khi driver cụ thể hỗ trợ |
| Dùng `TYPE_SCROLL_INSENSITIVE` vì “tiện quay lại” | Có thể buộc driver đệm hoặc làm mất điều kiện streaming | Ưu tiên `TYPE_FORWARD_ONLY` khi chỉ cần duyệt một chiều |
| Thu mọi hàng vào `ArrayList` hoặc `StringBuilder` lớn | Heap vẫn tăng theo số hàng dù driver fetch theo đợt | Xử lý/ghi từng hàng vào đầu nhận có giới hạn |
| Truy vấn thêm dữ liệu cho mỗi hàng trên cùng connection | N+1, giữ cursor, có thể bị driver từ chối | Thiết kế `JOIN`, truy vấn trước hoặc kết cấu pipeline khác |
| Giữ kết nối đến khi client HTTP chậm đọc hết | Cạn pool, transaction và cursor kéo dài | Tách bước xuất, dùng file tạm hoặc phân trang phù hợp |
| Dùng `getBytes()` cho BLOB rất lớn | Có thể cấp phát mảng lớn | Dùng stream LOB và kiểm tra driver |
| Không đóng `ResultSet` khi hủy giữa chừng | Giữ tài nguyên DB/client | Dùng `try-with-resources`, thử cancellation thực tế |
| Coi fetch size là giới hạn tổng số hàng | Truy vấn vẫn có thể trả hàng triệu hàng | Dùng SQL filter/row limit/pagination nếu cần |
| Retry xuất file mà không có checkpoint bền vững | Trùng hoặc thiếu hàng trong file | Thiết kế resume, file tạm và đối soát |
| Tin rằng streaming giúp `ORDER BY`/`JOIN` chậm trở nên nhanh | Server vẫn phải thực thi query plan | Tối ưu index, lọc cột và kiểm tra execution plan |

## 12. Kiểm thử thực tế trên DB và driver triển khai

Bộ integration test nên chạy trên đúng **DBMS, driver, URL/cấu hình kết nối, connection pool và kích thước dữ liệu** dự kiến trong sản xuất. Một số tình huống quan trọng:

| Tình huống | Cách kiểm tra | Kết quả mong đợi |
| --- | --- | --- |
| Tập nhỏ, 3 hàng | Đọc bằng exporter | CSV có header và đúng 3 dòng dữ liệu |
| Tập rỗng | Truy vấn `WHERE order_id >` giá trị rất lớn | CSV chỉ có header; trả số hàng 0 |
| Hàng có ký tự `,`, `"`, xuống dòng trong cột văn bản | Ghi CSV và đọc lại bằng CSV parser | Giá trị được escape đúng định dạng |
| Tập lớn với cấu hình mặc định | Đo peak heap và thời gian | Xác định baseline, không suy ra streaming chỉ từ vòng lặp |
| Tập lớn với fetch mode được driver hỗ trợ | Giữ nguyên SQL và đầu nhận, thay cấu hình | Đo được sự khác biệt trong bộ nhớ/fetch nếu streaming thật |
| PostgreSQL bật/tắt `autoCommit` trong test | So sánh với `TYPE_FORWARD_ONLY`, fetch size dương | Xác nhận điều kiện cursor của driver đích |
| MySQL với/không có cấu hình cursor fetch | Quan sát buffer và hành vi connection | Xác minh đúng chế độ, không nhầm với streaming đặc biệt |
| Đóng khi mới đọc một phần | `break` sau 100 hàng rồi đóng | Pool trả connection, không giữ result set/cursor rò rỉ |
| Đầu nhận dữ liệu chậm | Thêm writer bị giới hạn throughput | Quan sát pool saturation và transaction lifetime |
| Lỗi ghi đầu ra giữa chừng | Writer ném `IOException` sau một số hàng | Tài nguyên JDBC được đóng; file/response một phần không được báo hoàn tất |
| BLOB lớn trong một hàng | Dùng `getBinaryStream` | Không bắt buộc cấp phát `byte[]` bằng kích thước BLOB |
| Hủy tác vụ/timeout | Thử cancel và connection close | Quan sát khả năng dừng, thời gian giải phóng tài nguyên |

Khi làm benchmark, **đầu nhận cũng phải streaming**: dùng `BufferedWriter` đến file hoặc một output được tiêu thụ ngay, tránh `StringWriter`, `ByteArrayOutputStream` hoặc `List` lớn làm sai kết quả đo. Giữ cùng điều kiện DB, dữ liệu, query plan và mức concurrency giữa các lần thử; tách số đo warm-up với trạng thái ổn định.

Đối với dữ liệu rất lớn, đừng chỉ đo heap Java. Một driver hoặc cơ chế nén/đệm mạng có thể dùng bộ nhớ native, còn server có thể tạo temporary files để sắp xếp. Đo cả JVM process memory, DB metrics và số session/cursor đang mở để có đánh giá đầy đủ.

## 13. Bài tập tự kiểm tra

**Bài 1 — Streaming thật hay chỉ đọc theo vòng lặp?** Chương trình dùng `while (rs.next())` và không tạo `List`. Có thể khẳng định driver đang fetch từng đợt từ DB không?

**Đáp án:** Không. Mã Java xử lý từng hàng nhưng driver có thể đã đệm toàn bộ kết quả. Cần xác minh chế độ fetch của driver và quan sát bộ nhớ/hành vi.

**Bài 2 — Fetch size.** `setFetchSize(200)` có nghĩa truy vấn tối đa trả 200 hàng hay chỉ gợi ý kích thước từng đợt đọc?

**Đáp án:** Nó là gợi ý về fetch, không phải giới hạn tổng số hàng. Khi cần giới hạn tổng hàng phải dùng điều kiện SQL hoặc cơ chế row limit phù hợp.

**Bài 3 — PostgreSQL.** Một ứng dụng pgJDBC dùng `TYPE_FORWARD_ONLY` và `fetchSize = 256` nhưng luôn `autoCommit = true`. Vì sao vẫn có thể tải toàn bộ kết quả?

**Gợi ý:** Cơ chế cursor fetch thông thường của pgJDBC yêu cầu transaction tồn tại, thường đặt `autoCommit = false`; ngoài ra còn các điều kiện driver khác phải đáp ứng.

**Bài 4 — MySQL.** Có nên sao chép `setFetchSize(Integer.MIN_VALUE)` từ ví dụ MySQL sang mã truy vấn chung cho SQL Server, Oracle và PostgreSQL?

**Đáp án:** Không. Đây là quy ước streaming đặc biệt của một driver, không phải ý nghĩa fetch size chuẩn JDBC. Cần chọn cấu hình riêng theo driver và phiên bản.

**Bài 5 — Memory.** Ứng dụng dùng fetch cursor đúng cách nhưng sau đó gọi `rows.add(mapRow(rs))` cho cả triệu hàng. Vì sao vẫn có thể hết heap?

**Đáp án:** Vùng đệm driver có thể được giới hạn, nhưng `ArrayList` của ứng dụng vẫn giữ mọi đối tượng và tăng theo tổng số hàng.

**Bài 6 — Tài nguyên pool.** Một task export chạy 30 phút và dùng `Connection` từ pool có 10 kết nối. Nếu 10 tác vụ tương tự chạy đồng thời, API CRUD khác có thể gặp chuyện gì?

**Gợi ý:** Pool có thể hết kết nối rảnh; request khác phải chờ hoặc timeout. Cân nhắc giới hạn concurrency export, phân trang hoặc kiến trúc xuất riêng.

**Bài 7 — BLOB.** Vì sao `rs.getBinaryStream("payload")` và `setFetchSize(256)` giải quyết hai vấn đề khác nhau?

**Đáp án:** `getBinaryStream` giúp đọc **một giá trị BLOB** theo phần; `setFetchSize` là gợi ý về cách **nhiều hàng** được lấy qua driver. Cần kiểm thử cả hai.

**Bài 8 — File xuất lỗi giữa chừng.** Một task viết 5.000 hàng vào CSV rồi mạng tới DB lỗi; `connection.rollback()` có xóa 5.000 dòng đã ghi vào file không?

**Đáp án:** Không. File nằm ngoài transaction JDBC. Cần ghi vào file tạm, đánh dấu hoàn tất khi thành công hoặc dọn file lỗi; muốn resume phải có checkpoint bền vững.

**Bài 9 — Chọn chiến lược.** Khi nào phân trang theo `order_id` có thể phù hợp hơn giữ một `ResultSet` streaming suốt 45 phút?

**Gợi ý:** Khi cần trả connection sớm, hạn chế transaction dài, kiểm soát memory theo trang và hỗ trợ resume. Đổi lại, phải xử lý tính nhất quán giữa các trang khi dữ liệu thay đổi đồng thời.

## Tổng kết

Đọc dữ liệu quy mô lớn bằng JDBC đòi hỏi **hai điều kiện đồng thời**: ứng dụng phải xử lý từng hàng thay vì giữ toàn bộ kết quả, và driver phải thực sự hỗ trợ cách fetch/streaming có giới hạn bộ đệm theo cấu hình và điều kiện của nó. `TYPE_FORWARD_ONLY`, `CONCUR_READ_ONLY` và `setFetchSize(...)` là những công cụ quan trọng, nhưng **không phải phép bảo đảm streaming chung cho mọi driver**. Hãy kiểm tra yêu cầu về `autoCommit`, server cursor, driver properties và cách đệm kết quả của DBMS thực tế; giữ `ResultSet`, `PreparedStatement` và `Connection` trong `try-with-resources`; tránh transaction dài, N+1 queries và đầu ra tích lũy toàn bộ dữ liệu. Cuối cùng, đo memory, fetch behavior, pool usage, lỗi hủy giữa chừng và cân nhắc keyset pagination khi một cursor dài không phù hợp với yêu cầu vận hành.
