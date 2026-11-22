# Tránh nạp toàn bộ ResultSet vào danh sách lớn

Một truy vấn JDBC trả vài trăm dòng thường có thể được ánh xạ thành `List<DTO>` mà không gây vấn đề. Nhưng khi bảng có hàng triệu bản ghi, thói quen **đọc toàn bộ `ResultSet` vào một `ArrayList` rồi mới bắt đầu xử lý** có thể khiến heap tăng liên tục, gây nhiều chu kỳ garbage collection, độ trễ cao và cuối cùng là `OutOfMemoryError`.

Giải pháp không chỉ là thay `ArrayList` bằng một collection khác. Với **JDBC**, ta nên thay đổi **hợp đồng xử lý dữ liệu**: đọc một dòng, xử lý hoặc ghi nó ra nơi nhận, rồi chuyển sang dòng kế tiếp. Nếu cần gom nhiều dòng để tăng hiệu quả, chỉ giữ **một batch kích thước giới hạn**. Nếu công việc kéo dài, có thể thay một `ResultSet` mở suốt thời gian xử lý bằng **keyset pagination**.

Bài này thuộc chương **Truy vấn quy mô lớn** của module **JDBC**. Nội dung kết hợp `DataSource`, `PreparedStatement`, `ResultSet`, SQL có tham số, quản lý connection/transaction, cấu hình fetch, xử lý lỗi và đo hiệu năng bằng các API chuẩn.

Sau bài học, bạn có thể:

- Nhận biết các mẫu code làm bộ nhớ tăng theo tổng số dòng.
- Thiết kế API kiểu **callback/consumer** thay vì luôn trả `List`.
- Đọc và xử lý từng dòng trong phạm vi `ResultSet` còn mở, có dọn tài nguyên khi lỗi.
- Dùng batch có giới hạn và backpressure mà không vô tình giữ toàn bộ dữ liệu ở tầng khác.
- Hiểu `setFetchSize` chỉ là một *hint*, không bảo đảm driver luôn fetch tăng dần.
- Chọn keyset pagination khi không thể giữ connection/transaction trong suốt một job dài.
- Kiểm chứng tính đầy đủ, sự ổn định của thứ tự và mức tiêu thụ bộ nhớ ở dữ liệu lớn.

## 1. Cái bẫy: `while (rs.next())` nhưng vẫn nạp hết vào RAM

Ví dụ phổ biến:

~~~java
List<OrderRow> rows = new ArrayList<>();

String sql = "SELECT order_id, amount, status FROM orders";

try (PreparedStatement ps = connection.prepareStatement(sql);
     ResultSet rs = ps.executeQuery()) {

    while (rs.next()) {
        rows.add(new OrderRow(
                rs.getLong("order_id"),
                rs.getBigDecimal("amount"),
                rs.getString("status")));
    }
}

// Chỉ đến đây mới bắt đầu xử lý.
for (OrderRow row : rows) {
    export(row);
}
~~~

Vấn đề chính nằm ở `rows.add(...)`: mỗi lần lặp giữ thêm đối tượng trong bộ nhớ cho đến khi kết thúc toàn bộ truy vấn. Nếu lượng dữ liệu tăng gấp 10, bộ nhớ giữ bởi danh sách cũng có xu hướng tăng tương ứng.

`ArrayList` không chỉ giữ chính dữ liệu; nó giữ mảng tham chiếu, còn từng `OrderRow` giữ thêm đối tượng và trường như `BigDecimal`, `String`. Đồng thời JDBC driver có thể lưu dữ liệu gốc trong buffer và tầng export có thể tạo buffer khác.

~~~mermaid
flowchart LR
    A["Database"] --> B["Driver/JDBC buffer"]
    B --> C["ResultSet"]
    C --> D["List chứa mọi DTO"]
    D --> E["Formatter / Serializer"]
    E --> F["File / HTTP / hệ thống khác"]
~~~

Một số biểu hiện:

- Heap tăng dần trong quá trình đọc, dù các dòng cũ đã được “xử lý” bằng cách thêm vào danh sách.
- Truy vấn xong vẫn phải đợi thêm một giai đoạn convert/serialize toàn bộ danh sách.
- Bộ nhớ đỉnh cao hơn mức cần thiết vì `ResultSet`, `List` và dữ liệu đầu ra cùng tồn tại.
- Khi có lỗi ở dòng thứ 900.000, toàn bộ danh sách đã được tạo rồi có thể bị bỏ.
- Tầng gọi mặc định rằng mọi truy vấn phải trả một collection đã materialize.

**Kết luận quan trọng:** Vòng lặp `while (rs.next())` tự nó không gây OOM. **Cách giữ lại dữ liệu** trong vòng lặp mới là nguyên nhân trực tiếp ở tầng ứng dụng.

## 2. Hai giới hạn bộ nhớ độc lập

Muốn nói một luồng xử lý “không nạp toàn bộ”, phải xét **hai tầng**:

| Tầng | Nguy cơ | Cách kiểm soát |
| --- | --- | --- |
| **Ứng dụng Java** | `List`, `Map`, `StringBuilder`, queue hoặc serializer giữ tất cả DTO | Xử lý từng dòng, batch giới hạn, output streaming, backpressure |
| **JDBC driver/database client** | Driver tự fetch/materialize nhiều dòng hoặc cả kết quả trước khi Java gọi `next()` | `fetchSize`, kiểu result set, cấu hình cursor và driver-specific streaming |
| **Database server** | Sort, join, aggregation, hash table hoặc cursor giữ bộ nhớ/tài nguyên | SQL chọn lọc, index, kế hoạch thực thi, điều chỉnh query |
| **Hệ thống đích** | Sink lưu tất cả dữ liệu chờ ghi, queue không giới hạn | Bounded queue, flush, áp lực ngược, batch đồng bộ |

Ví dụ code có thể **không tạo `List` nào** nhưng vẫn tốn nhiều RAM nếu driver đọc hết kết quả vào buffer. Ngược lại, driver có server-side cursor nhưng ứng dụng gọi `collect(toList())` thì vẫn bị OOM.

Mục tiêu thiết kế là khiến dung lượng đang giữ trong Java phụ thuộc vào **một dòng + buffer driver + buffer đầu ra**, hoặc **một batch giới hạn**, chứ không phụ thuộc tổng số dòng.

## 3. Chọn chiến lược theo nhu cầu

| Trường hợp | Chiến lược nên xem xét | Vì sao |
| --- | --- | --- |
| Hiển thị 20–100 dòng trên một màn hình | `LIMIT`/`FETCH` và trả `List` nhỏ | Đơn giản, có giới hạn rõ ràng |
| Xuất CSV/JSONL qua file | Duyệt `ResultSet` và ghi từng dòng | Không cần giữ tất cả kết quả |
| Tính tổng, đếm, min/max | Đưa aggregation vào SQL hoặc cộng dồn số nhỏ | Không cần DTO cho từng dòng |
| Đồng bộ sang hệ thống khác bằng batch | Batch có giới hạn và consumer có backpressure | Tận dụng ghi theo lô, kiểm soát RAM |
| Job chạy hàng giờ, cần resume | Keyset pagination theo khóa ổn định | Kết thúc transaction từng trang, lưu checkpoint |
| Tệp/BLOB hoặc CLOB lớn | `getBinaryStream`/`getCharacterStream` | Tránh tạo mảng byte hay chuỗi quá lớn |
| Cần nhiều thao tác ngẫu nhiên trên toàn tập trong RAM | Cân nhắc thuật toán/thiết kế lại, xử lý ngoài bộ nhớ | Không thể vừa giữ tất cả vừa yêu cầu RAM cố định |

Không cần cấm `List` hoàn toàn. **Một danh sách tối đa 100 hoặc 500 phần tử có chủ đích** là công cụ hữu ích. Sai lầm là collection **không có giới hạn kích thước** trong luồng dữ liệu lớn.

## 4. API tốt hơn: consumer thay vì trả `List`

Một repository trả `List<OrderRow>` thường buộc người gọi đợi truy vấn hoàn tất:

~~~java
List<OrderRow> findAllOrders(); // Hợp đồng ngầm: giữ tất cả dòng
~~~

Đổi thành **callback**:

~~~java
void forEachOrder(OrderConsumer consumer)
        throws SQLException, IOException;
~~~

Tầng gọi truyền hành động xử lý một dòng. Repository kiểm soát connection, statement và result set; callback được gọi **ngay trong lúc tài nguyên JDBC còn mở**.

~~~mermaid
sequenceDiagram
    participant Caller as Caller / Writer
    participant Repo as JDBC Repository
    participant DB as Database
    Caller->>Repo: scanOrders(consumer)
    Repo->>DB: SELECT ...
    loop Mỗi dòng ResultSet
        DB-->>Repo: row
        Repo->>Caller: consumer.accept(row)
        Note over Caller,Repo: Xử lý/ghi xong rồi mới lấy dòng kế
    end
    Repo->>Repo: Đóng ResultSet/Statement/Connection
    Repo-->>Caller: Tổng số dòng
~~~

Ưu điểm:

- Không phải tạo một `List` tổng.
- Dễ kiểm soát vòng đời `Connection` và `ResultSet` trong đúng một phương thức.
- Đầu ra chậm sẽ làm việc đọc tiếp chậm lại (**backpressure đồng bộ tự nhiên**).
- Dữ liệu được xử lý sớm mà không phải chờ hết truy vấn.

Giới hạn:

- Callback nên thực hiện nhanh hoặc ghi ra sink được quản lý tốt.
- Nếu callback thêm tất cả dòng vào collection riêng, vấn đề OOM chỉ **dịch sang tầng gọi**.
- Không lưu `ResultSet` hoặc `Row` tham chiếu đến cursor để dùng sau khi phương thức kết thúc.
- Nếu muốn xử lý song song, cần thiết kế hàng đợi có giới hạn hoặc phân trang; không chuyển cùng một `ResultSet` qua nhiều thread.

## 5. Ví dụ Java hoàn chỉnh: scan đơn hàng theo từng dòng

Giả sử bảng SQL:

~~~sql
CREATE TABLE orders (
    order_id BIGINT PRIMARY KEY,
    amount DECIMAL(19, 2) NOT NULL,
    status VARCHAR(24) NOT NULL
);
~~~

Schema có cú pháp minh họa; bảng thực tế phải có index/khóa phù hợp. Ta chọn đúng ba cột cần dùng, không `SELECT *`.

### 5.1. Consumer có thể báo lỗi I/O

~~~java
import java.io.IOException;
import java.math.BigDecimal;
import java.sql.SQLException;

@FunctionalInterface
public interface OrderConsumer {
    void accept(long orderId, BigDecimal amount, String status)
            throws IOException, SQLException;
}
~~~

Tại sao interface cho phép ném `IOException`? Vì một ứng dụng xuất CSV hoặc ghi dữ liệu qua network có thể thất bại ở **sink**, không phải ở database. Khi callback ném lỗi, repository phải đóng tài nguyên JDBC thay vì tiếp tục đọc vô hạn.

### 5.2. Repository sở hữu connection và cursor

~~~java
import java.io.IOException;
import java.math.BigDecimal;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.Objects;
import javax.sql.DataSource;

public final class OrderScanner {
    private final DataSource dataSource;

    public OrderScanner(DataSource dataSource) {
        this.dataSource = Objects.requireNonNull(dataSource);
    }

    public long scanOrders(
            long firstId, long lastId, OrderConsumer consumer)
            throws SQLException, IOException {

        Objects.requireNonNull(consumer, "consumer");
        if (firstId > lastId) {
            throw new IllegalArgumentException("Khoảng ID không hợp lệ");
        }

        String sql = "SELECT order_id, amount, status "
                   + "FROM orders "
                   + "WHERE order_id >= ? AND order_id <= ? "
                   + "ORDER BY order_id";

        try (Connection connection = dataSource.getConnection()) {
            // Đặt chế độ trước khi bắt đầu thực thi SQL.
            connection.setReadOnly(true);

            // Một số driver dùng transaction để duy trì cursor fetch;
            // ví dụ pgJDBC có điều kiện auto-commit=false.
            connection.setAutoCommit(false);

            try {
                long processed = 0L;

                try (PreparedStatement ps = connection.prepareStatement(
                        sql,
                        ResultSet.TYPE_FORWARD_ONLY,
                        ResultSet.CONCUR_READ_ONLY)) {

                    ps.setLong(1, firstId);
                    ps.setLong(2, lastId);
                    ps.setFetchSize(500);
                    ps.setQueryTimeout(120);

                    try (ResultSet rs = ps.executeQuery()) {
                        while (rs.next()) {
                            long id = rs.getLong("order_id");
                            if (rs.wasNull()) {
                                throw new SQLException(
                                        "order_id bắt buộc không NULL");
                            }

                            BigDecimal amount =
                                    rs.getBigDecimal("amount");
                            String status = rs.getString("status");

                            if (amount == null || status == null) {
                                throw new SQLException(
                                        "Bản ghi sai hợp đồng NULL");
                            }

                            // Consumer xử lý dòng trước khi gọi next().
                            consumer.accept(id, amount, status);
                            processed++;
                        }
                    }
                }

                // Transaction chỉ đọc: kết thúc rõ ràng.
                connection.rollback();
                return processed;

            } catch (SQLException | IOException | RuntimeException failure) {
                try {
                    connection.rollback();
                } catch (SQLException rollbackError) {
                    failure.addSuppressed(rollbackError);
                }
                throw failure;
            }
        }
    }
}
~~~

**Hợp đồng của `scanOrders`:** nó không trả `List` và không cho caller giữ `ResultSet`. Một callback chỉ nhận ba giá trị đã đọc. Khi callback trả về, vòng lặp đọc dòng tiếp theo; khi callback ném lỗi, tài nguyên tự đóng nhờ `try-with-resources`.

Một số điểm tinh tế:

1. **`TYPE_FORWARD_ONLY` và `CONCUR_READ_ONLY`** phù hợp với luồng đọc tuần tự không cập nhật qua cursor.
2. **`setFetchSize(500)` là một hint**, không phải bảo đảm rằng driver chỉ giữ tối đa 500 dòng.
3. **`autoCommit=false`** giúp một số driver dùng server-side cursor; thao tác đọc trở thành transaction có thời gian sống bằng toàn bộ việc scan.
4. **`connection.rollback()`** được dùng để kết thúc transaction chỉ đọc khi thành công. Vì không có DML, nó không nhằm hủy một tác vụ ghi; nếu application có chiến lược transaction riêng, cần điều chỉnh.
5. **`setReadOnly(true)`** là một hint/cấu hình DBMS, không thay thế quyền `SELECT` và phân quyền dữ liệu.
6. **`setQueryTimeout(120)`** chỉ giới hạn thực thi statement theo khả năng driver; nó không phải deadline chắc chắn cho toàn bộ thời gian callback xuất dữ liệu.
7. Nếu callback ném `IOException` ở giữa, phần đầu ra có thể đã được ghi **một phần**. Phương thức này không thể tự rollback các byte đã gửi đến file hoặc client.

Việc truy vấn có thể kết thúc sớm nếu người gọi chủ động ném một ngoại lệ riêng từ callback; cần định nghĩa chính sách hủy, cleanup và số dòng đã ghi khi triển khai job thực tế.

## 6. Xuất CSV mà không tạo danh sách

Caller sở hữu file và `Writer`, còn `OrderScanner` sở hữu JDBC resources:

~~~java
import java.io.BufferedWriter;
import java.io.IOException;
import java.io.Writer;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public final class OrderCsvExport {
    public static long writeFile(
            OrderScanner scanner, Path destination)
            throws Exception {

        // File đích được tạo/ghi đè theo chính sách ở ví dụ.
        try (BufferedWriter out = Files.newBufferedWriter(
                destination, StandardCharsets.UTF_8)) {

            out.write("order_id,amount,status\n");

            return scanner.scanOrders(1L, Long.MAX_VALUE,
                    (orderId, amount, status) -> {
                        out.write(Long.toString(orderId));
                        out.write(',');
                        out.write(amount.toPlainString());
                        out.write(',');
                        writeQuotedCsvField(out, status);
                        out.write('\n');
                    });
        }
    }

    private static void writeQuotedCsvField(
            Writer out, String text) throws IOException {
        out.write('"');
        for (int i = 0; i < text.length(); i++) {
            char ch = text.charAt(i);
            if (ch == '"') {
                out.write('"');
            }
            out.write(ch);
        }
        out.write('"');
    }
}
~~~

Kết quả `writeFile` là tổng số dòng đã xử lý thành công trước khi mọi tài nguyên đóng; **không phải danh sách toàn bộ đơn hàng**. Writer được buffer, giúp tránh quá nhiều lời gọi ghi nhỏ.

**Lưu ý về tính an toàn của CSV:** Bao trường văn bản bằng dấu nháy kép là cách escape CSV thông dụng, nhưng **không tự ngăn công thức độc hại** nếu file được mở bằng phần mềm bảng tính. Nếu `status` hoặc trường text khác đến từ người dùng, cần chính sách xử lý CSV/formula injection phù hợp với nơi nhận. Không giả định dữ liệu nhận từ database luôn an toàn cho mọi định dạng đầu ra.

Khi xuất file thực tế, nên ghi vào **file tạm**, chỉ đổi tên/công bố sau khi hoàn tất và xác minh dữ liệu. Nếu `IOException` xảy ra ở dòng thứ 100.000, file đã ghi một phần không được quảng bá là bản export hoàn chỉnh. Việc đổi tên nguyên tử chỉ thực hiện được khi filesystem hỗ trợ và ứng dụng chọn cách gọi phù hợp.

### Không làm thế này ở callback

~~~java
List<String> allLines = new ArrayList<>();

scanner.scanOrders(1L, Long.MAX_VALUE,
        (id, amount, status) -> {
            allLines.add(id + "," + amount + "," + status);
        });

// Vẫn giữ toàn bộ dữ liệu ở allLines!
~~~

API callback chỉ **cho phép** xử lý liên tục; nó không ép caller dùng bộ nhớ đúng cách.

## 7. `setFetchSize` giải quyết phần nào của bài toán?

Ứng dụng không dùng `List` mới xử lý được **nửa bài toán**. Phần còn lại là driver có thực sự fetch dữ liệu dần dần hay đã materialize toàn bộ trước khi trả `ResultSet`.

~~~java
PreparedStatement ps = connection.prepareStatement(
        sql,
        ResultSet.TYPE_FORWARD_ONLY,
        ResultSet.CONCUR_READ_ONLY);

ps.setFetchSize(500);
~~~

`setFetchSize` là **gợi ý cho driver** về số dòng nên lấy từ database mỗi đợt. JDBC không cam kết driver áp dụng đúng con số này hay đạt bộ nhớ đỉnh tương ứng. Đọc `ps.getFetchSize()` chỉ kiểm tra giá trị hint mà driver báo cáo, **không chứng minh** streaming đang hoạt động.

Các khác biệt thường gặp:

| Driver / DBMS | Điểm cần kiểm tra |
| --- | --- |
| **PostgreSQL (pgJDBC)** | Cursor-based fetching thường cần `autoCommit=false`, `fetchSize > 0`, result set forward-only và các điều kiện driver tương ứng |
| **MySQL (Connector/J)** | Cursor fetch thường yêu cầu cấu hình driver như `useCursorFetch=true` với fetch size dương; một số cấu hình cũng liên quan server-side prepared statement |
| **MySQL streaming kiểu cũ** | Một số phiên bản Connector/J có chế độ đặc thù dùng `Integer.MIN_VALUE`; **không phải quy tắc JDBC chung** |
| **Microsoft JDBC Driver / SQL Server** | Adaptive buffering và thuộc tính response buffering ảnh hưởng cách nhận và giữ dữ liệu |
| **Oracle JDBC** | Prefetch/fetch size, loại cột và driver ảnh hưởng số dòng đọc mỗi lượt |
| **DB nhúng** | Có thể không có server cursor qua mạng; bộ nhớ phụ thuộc engine và driver |

Bảng mang tính định hướng. **Driver version, cấu hình JDBC URL, dạng câu lệnh, transaction và fetch size thực tế** phải được kiểm thử trên môi trường mục tiêu.

### Chọn fetch size như thế nào?

Nếu dòng chỉ có vài cột số và chuỗi ngắn, 500 dòng có thể là batch vừa phải. Nhưng nếu một dòng chứa CLOB 20 MB, một batch 500 dòng có thể quá lớn. Cách chọn đúng:

- Đo kích thước trung bình và trường hợp xấu nhất của mỗi dòng.
- Thử các mức như 100, 500, 2.000 trên dữ liệu kiểm thử đại diện.
- Đo thời gian, số round trip và peak heap/RSS.
- Giảm batch nếu buffer lớn hoặc garbage collection tăng.
- Tăng batch có kiểm soát nếu độ trễ mạng chiếm phần lớn thời gian và bộ nhớ vẫn phù hợp.

Không dùng `setMaxRows(500)` thay cho `setFetchSize(500)`: `setMaxRows` **giới hạn tổng số dòng**, nghĩa là có thể bỏ dữ liệu cần xử lý; `fetchSize` chỉ hướng dẫn số dòng mỗi lần fetch.

## 8. Batch có giới hạn: khi xử lý một dòng là quá nhỏ

Một hệ thống gửi dữ liệu sang dịch vụ khác có thể hiệu quả hơn nếu xử lý từng **lô cố định**, ví dụ 250 đơn hàng. Mấu chốt là không để batch tăng vô hạn.

~~~java
import java.math.BigDecimal;

public final class OrderRow {
    public final long id;
    public final BigDecimal amount;
    public final String status;

    public OrderRow(long id, BigDecimal amount, String status) {
        this.id = id;
        this.amount = amount;
        this.status = status;
    }
}
~~~

Một mẫu xử lý batch **đồng bộ**:

~~~java
import java.util.ArrayList;
import java.util.List;

final int BATCH_SIZE = 250;
final List<OrderRow> batch = new ArrayList<>(BATCH_SIZE);

scanner.scanOrders(1L, Long.MAX_VALUE,
        (id, amount, status) -> {
            batch.add(new OrderRow(id, amount, status));

            if (batch.size() == BATCH_SIZE) {
                persistBatchSynchronously(batch);
                batch.clear();
            }
        });

if (!batch.isEmpty()) {
    persistBatchSynchronously(batch);
    batch.clear();
}
~~~

`persistBatchSynchronously` là helper nghiệp vụ do ứng dụng cung cấp. **Hợp đồng bắt buộc:** phương thức này xử lý xong batch **trước khi trả về**, không giữ tham chiếu đến danh sách, phần tử hoặc truyền nó sang một queue không giới hạn. Nếu helper đưa batch vào hàng đợi bất đồng bộ rồi trả về, `batch.clear()` có thể làm consumer nhận một danh sách đã bị xóa.

Nếu cần xử lý bất đồng bộ:

1. Tạo **batch immutable hoặc bản sao** cho mỗi lần gửi.
2. Dùng **bounded queue** thay vì unbounded queue.
3. Giới hạn số batch đang chờ.
4. Có cơ chế chờ/backpressure khi consumer không theo kịp.
5. Có đường lỗi/cancel dừng truy vấn và giải phóng connection.
6. Xác định rõ khi nào batch được coi là xử lý bền vững và có thể checkpoint.

Bộ nhớ trong mô hình này xấp xỉ phụ thuộc vào kích thước batch và số batch được phép chờ, chứ không phụ thuộc tổng số dòng. Tuy nhiên, cần nhớ **kích thước byte mỗi phần tử** vẫn quan trọng: giới hạn 250 dòng không đủ nếu mỗi dòng có một chuỗi nhiều megabyte.

### Có nên dùng `parallelStream()` trên `ResultSet`?

Không nên tự biến `ResultSet` thành một stream chạy song song bằng cách chia sẻ một cursor giữa nhiều thread. `ResultSet`/`Connection` không có hợp đồng thread-safe phổ quát cho việc đọc đồng thời.

Nếu tác vụ có khả năng phân vùng dữ liệu theo khóa, có thể dùng **nhiều truy vấn độc lập trên các connection riêng**, mỗi truy vấn đọc một vùng khóa không chồng lặp, đồng thời kiểm soát pool size và thứ tự kết quả. Đó là một quyết định kiến trúc khác, không phải chỉ thay `stream()` thành `parallelStream()`.

## 9. Đừng trả lazy `Stream` sau khi đóng tài nguyên JDBC

Một cách khác tưởng như tiết kiệm bộ nhớ là trả `Stream<OrderRow>` từ repository. Nhưng nếu repository đóng `Connection` trước khi caller duyệt, stream sẽ hỏng:

~~~java
// Sai về vòng đời: minh họa ý tưởng.
Stream<OrderRow> findAll() throws SQLException {
    try (Connection c = dataSource.getConnection();
         PreparedStatement ps = c.prepareStatement(SQL);
         ResultSet rs = ps.executeQuery()) {

        return createLazyStream(rs); // Cursor bị đóng khi return!
    }
}
~~~

Ngược lại, nếu repository **không** đóng connection và mong caller nhớ gọi `stream.close()`, hệ thống dễ rò connection trong pool khi caller quên đóng hoặc khi có ngoại lệ.

Ba thiết kế an toàn hơn:

| Thiết kế | Ranh giới sở hữu tài nguyên |
| --- | --- |
| `scanOrders(consumer)` | Repository mở và đóng JDBC trong cùng method |
| `withOrders(Function<ResultSet, T>)` hoặc callback tương tự | Repository giữ JDBC mở cho đến khi callback hoàn thành |
| Một `CloseableIterator`/cursor wrapper được thiết kế kỹ | Caller phải `try-with-resources`; wrapper đóng ResultSet, Statement và Connection |

Đối với nhóm học JDBC cơ bản đến trung cấp, **callback có đồng bộ và phạm vi rõ ràng** dễ kiểm thử và ít rò tài nguyên hơn API trả stream lazy không được mô tả đầy đủ.

## 10. Tốc độ consumer và thời gian giữ connection

Xử lý từng dòng ngay trong callback giúp tiết kiệm RAM, nhưng một vấn đề khác xuất hiện: **consumer có thể quá chậm**.

Ví dụ:

~~~java
scanner.scanOrders(1L, Long.MAX_VALUE,
        (id, amount, status) -> {
            // Không khuyến khích: mỗi dòng lại gọi API qua mạng,
            // có thể kéo dài transaction và giữ connection lâu.
            remoteService.sendOneOrder(id, amount, status);
        });
~~~

Nếu remote API mất hàng trăm mili giây cho mỗi dòng, connection và transaction có thể bị giữ hàng giờ. Điều này làm:

- Chiếm connection pool, giảm khả năng phục vụ request khác.
- Giữ snapshot/MVCC hoặc khóa trong DBMS lâu hơn cần thiết.
- Dễ gặp timeout khi mạng DB hoặc mạng tới consumer có sự cố.
- Tăng rủi ro job bị hủy giữa chừng mà chưa có checkpoint.
- Khi gọi dịch vụ ngoài ngay trong transaction, rollback JDBC không hoàn tác các tác động đã gửi.

Một số lựa chọn cải tiến:

- Ghi tạm ra file và xử lý từ file sau khi đóng DB connection.
- Dùng batch giới hạn nếu sink hỗ trợ ghi theo lô.
- Dùng bounded queue với backpressure và checkpoint bền vững.
- Dùng **keyset pagination**, đọc xong từng trang rồi giải phóng connection.
- Thiết kế retry/idempotency ở nơi nhận.

**Không có phương án hoàn hảo cho mọi nghiệp vụ.** Nếu cần snapshot nhất quán xuyên suốt toàn bộ dữ liệu, một transaction/cursor dài có thể có ý nghĩa nhưng phải cân đối chi phí và cấu hình DBMS. Nếu ưu tiên khả năng resume và thời gian giữ connection ngắn, phân trang theo khóa thường thuận tiện hơn.

## 11. Keyset pagination: xử lý nhiều trang nhỏ

Với bảng có khóa `order_id` **duy nhất, không đổi và được index**, ta có thể đọc theo từng trang:

~~~sql
SELECT order_id, amount, status
FROM orders
WHERE order_id > ? AND order_id <= ?
ORDER BY order_id ASC
LIMIT ?;
~~~

**Chú ý:** `LIMIT` là cú pháp được PostgreSQL/MySQL hỗ trợ, **không phải cú pháp chung của mọi SQL DBMS**. SQL Server và Oracle có cú pháp phân trang riêng. `?` cho kích thước trang cũng cần driver hỗ trợ ở vị trí đó.

### 11.1. Quy trình

1. Xác định phạm vi khóa trên, chẳng hạn `upperId` từ thời điểm bắt đầu job.
2. Đặt `lastId` ở trước khóa đầu tiên cần xử lý.
3. Query `WHERE order_id > lastId AND order_id <= upperId ORDER BY order_id LIMIT pageSize`.
4. Xử lý từng dòng của trang; sau dòng thành công, cập nhật `lastId`.
5. Khi hết trang, đóng `ResultSet`, statement và connection.
6. Nếu trang không có dòng, kết thúc job.
7. Với job cần khôi phục, **lưu checkpoint chỉ sau khi dữ liệu đã được ghi bền vững**.

~~~mermaid
flowchart TD
    S["lastId + upperId"] --> Q["SELECT page WHERE id > lastId"]
    Q --> R{"Trang có dòng?"}
    R -->|Không| E["Hoàn thành"]
    R -->|Có| P["Xử lý từng dòng, số lượng <= N"]
    P --> K["Lưu checkpoint sau khi sink xác nhận"]
    K --> Q
~~~

### 11.2. Ví dụ Java theo trang, không tích lũy dữ liệu

~~~java
import java.io.IOException;
import java.math.BigDecimal;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.Objects;
import javax.sql.DataSource;

public final class PagedOrderScanner {
    private final DataSource dataSource;

    public PagedOrderScanner(DataSource dataSource) {
        this.dataSource = Objects.requireNonNull(dataSource);
    }

    public long scan(
            long lastProcessedId,
            long upperId,
            int pageSize,
            OrderConsumer consumer) throws SQLException, IOException {

        if (pageSize < 1 || pageSize > 1000) {
            throw new IllegalArgumentException(
                    "pageSize phải trong khoảng 1..1000");
        }
        Objects.requireNonNull(consumer, "consumer");

        // PostgreSQL/MySQL syntax; cần sửa nếu dùng DBMS khác.
        String sql = "SELECT order_id, amount, status "
                   + "FROM orders "
                   + "WHERE order_id > ? AND order_id <= ? "
                   + "ORDER BY order_id ASC LIMIT ?";

        long current = lastProcessedId;
        long processed = 0L;

        while (current < upperId) {
            long rowsInPage = 0L;

            // Một connection mới mỗi trang (qua pool).
            try (Connection c = dataSource.getConnection();
                 PreparedStatement ps = c.prepareStatement(
                         sql,
                         ResultSet.TYPE_FORWARD_ONLY,
                         ResultSet.CONCUR_READ_ONLY)) {

                ps.setLong(1, current);
                ps.setLong(2, upperId);
                ps.setInt(3, pageSize);

                try (ResultSet rs = ps.executeQuery()) {
                    while (rs.next()) {
                        long id = rs.getLong("order_id");
                        if (rs.wasNull() || id <= current || id > upperId) {
                            throw new SQLException(
                                    "Thứ tự/khóa dữ liệu không hợp lệ");
                        }

                        BigDecimal amount =
                                rs.getBigDecimal("amount");
                        String status = rs.getString("status");

                        if (amount == null || status == null) {
                            throw new SQLException(
                                    "Bản ghi sai hợp đồng NULL");
                        }

                        consumer.accept(id, amount, status);
                        current = id;
                        processed++;
                        rowsInPage++;
                    }
                }
            }

            if (rowsInPage == 0) {
                break; // Không còn dòng trong phạm vi.
            }
        }

        return processed;
    }
}
~~~

Đoạn này **không trả List** và không giữ một connection xuyên suốt mọi trang. `lastProcessedId` là checkpoint đầu vào; ứng dụng nên dùng ID nhỏ hơn khóa cần xử lý đầu tiên. `upperId` phải được xác định phù hợp với tập dữ liệu mục tiêu, ví dụ đọc giá trị `MAX(order_id)` ở đầu job; không lấy giá trị tùy tiện mà không xét schema. Nếu cần hỗ trợ khóa âm, khóa không tuần tự hoặc thứ tự phức hợp, điều kiện và checkpoint phải được thiết kế lại.

**Điểm cần sửa cho hệ thống thật:** Biến `current` trong bộ nhớ chỉ tiến sau callback hoàn thành; nó **chưa phải checkpoint bền vững**. Nếu process chết giữa trang, caller cần cơ chế lưu checkpoint sau khi sink ghi thành công, chấp nhận khả năng đọc lại dòng cuối và xử lý idempotent. Không thể bảo đảm exactly-once chỉ với một phép so sánh `id > ?`.

### 11.3. Keyset không đồng nghĩa một snapshot

Nếu mỗi trang chạy trong transaction riêng, dữ liệu có thể thay đổi giữa các trang:

- Dòng mới có ID lớn hơn `lastId` và nhỏ hơn `upperId` có thể xuất hiện trong các trang sau.
- Dòng mới có ID nhỏ hơn `lastId` có thể không bao giờ được đọc.
- Dòng đã xóa sau một trang có thể biến mất ở trang khác.
- Giá trị các cột không khóa có thể bị cập nhật giữa các lần đọc; báo cáo không nhất thiết phản ánh cùng một thời điểm.

Giới hạn `upperId` giúp cố định **phạm vi ID**, không tạo snapshot nhất quán của mọi cột. Khi yêu cầu nghiệp vụ là một snapshot nhất quán, phải chọn isolation/transaction hoặc cơ chế snapshot do DBMS cung cấp; đổi lại có thể tăng chi phí duy trì phiên bản dữ liệu.

### 11.4. Vì sao không chỉ dùng `OFFSET`?

~~~sql
SELECT order_id, amount, status
FROM orders
ORDER BY order_id
LIMIT ? OFFSET ?;
~~~

Khi `OFFSET` lớn, DBMS có thể phải duyệt/bỏ qua nhiều dòng trước khi trả trang; dữ liệu chèn/xóa đồng thời còn làm thay đổi vị trí dòng, gây trùng hoặc bỏ sót. Keyset dựa vào điều kiện trên khóa được index thường hiệu quả và ổn định hơn cho quét tuần tự quy mô lớn.

Tuy nhiên, keyset đòi hỏi điều kiện sắp xếp rõ ràng. Nếu sort theo `created_at` có các giá trị trùng nhau, phải dùng cặp khóa như `(created_at, order_id)` và biểu thức seek tương ứng, không chỉ dùng timestamp.

## 12. Khi chỉ cần tổng hợp, hãy đẩy phép tính về SQL

Đừng đọc một triệu dòng thành `List` chỉ để đếm:

~~~java
List<OrderRow> orders = findAllOrders();
long count = orders.size();
~~~

Thay bằng:

~~~sql
SELECT COUNT(*) AS total
FROM orders
WHERE status = ?;
~~~

JDBC:

~~~java
String sql = "SELECT COUNT(*) AS total "
           + "FROM orders WHERE status = ?";

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setString(1, "PAID");

    try (ResultSet rs = ps.executeQuery()) {
        if (rs.next()) {
            long count = rs.getLong("total");
            // Xử lý count.
        }
    }
}
~~~

Tương tự, dùng `SUM`, `AVG`, `MIN`, `MAX`, `GROUP BY` khi đúng với nghiệp vụ. Database được thiết kế để tối ưu phép tính trên tập dữ liệu; chuyển hết về Java chỉ để thực hiện phép tổng hợp đơn giản thường tăng network, CPU và heap không cần thiết.

Cũng cần chú ý SQL aggregate có thể gây tốn tài nguyên trên server với truy vấn phức tạp. Hãy kiểm tra index và execution plan; không có đảm bảo mọi câu `GROUP BY` đều rẻ.

## 13. Giảm kích thước từng dòng

Không chỉ **số dòng** quyết định bộ nhớ. Một dòng có thể chứa BLOB, CLOB, JSON lớn hoặc rất nhiều cột:

~~~sql
-- Tránh lấy cả cột lớn nếu chỉ cần metadata ngắn.
SELECT order_id, amount, status
FROM orders
WHERE order_id BETWEEN ? AND ?;
~~~

Thực hành tốt:

- Chọn **đúng cột** cần cho consumer; không dùng `SELECT *` trong export lớn.
- Đưa bộ lọc chính xác vào SQL thay vì tải mọi dòng rồi lọc trong Java.
- Chọn khóa và index phù hợp cho `WHERE`, `ORDER BY`.
- Dùng `getBigDecimal` cho `DECIMAL` để không giảm độ chính xác.
- Với BLOB/CLOB lớn, cân nhắc `getBinaryStream`/`getCharacterStream` thay vì `getBytes`/`getString` materialize cả giá trị.
- Tránh ánh xạ một hàng thành graph object nặng với nhiều collection liên kết nếu consumer chỉ cần vài trường.
- Giữ payload nhạy cảm khỏi log và file tạm không được phép.

Một `List` 1.000 dòng với mỗi dòng chứa một chuỗi vài MB vẫn có thể làm cạn bộ nhớ. Hãy đo theo **byte dữ liệu** chứ không chỉ đếm số phần tử.

## 14. Cần chú ý khi dùng ORM, RowSet và JSON serializer

Mặc dù bài học tập trung vào JDBC chuẩn, cùng nguyên nhân có thể xuất hiện ở tầng khác:

- **ORM persistence context:** lặp qua nhiều entity nhưng không giải phóng context có thể giữ hàng nghìn entity trong cache cấp phiên.
- **CachedRowSet/WebRowSet:** chúng chủ động cache dữ liệu trong bộ nhớ để hỗ trợ ngoại tuyến; không thay thế streaming cho tập cực lớn.
- **Serializer:** một số thư viện chỉ phát JSON sau khi đã nhận một `List`; dùng writer/streaming serializer nếu API cho phép.
- **Queue:** một producer đọc JDBC nhanh nhưng đẩy toàn bộ DTO vào queue không giới hạn sẽ chuyển OOM từ repository sang worker.
- **Reactive API:** gọi `collectList` hoặc ghép toàn bộ thành một buffer vẫn materialize kết quả dù trước đó là stream.

Đổi tên API thành “stream” không chứng minh bộ nhớ ổn định. Phải xem **toàn bộ đường đi của dữ liệu** từ driver tới nơi nhận.

## 15. Tính đúng đắn: đọc đủ, không trùng, không mất

Tối ưu bộ nhớ không được làm sai kết quả.

Một số rủi ro:

1. **Không có `ORDER BY`:** Thứ tự dòng không có bảo đảm; checkpoint theo ID không có ý nghĩa nếu truy vấn đọc theo thứ tự ngẫu nhiên.
2. **Dùng `LIMIT` nhưng quên trang tiếp theo:** Chỉ xuất một phần dữ liệu.
3. **Đổi query khi đang resume:** Điều kiện lọc thay đổi có thể khiến tập đầu ra không nhất quán.
4. **Lưu checkpoint trước khi sink xác nhận:** Nếu job lỗi, các dòng chưa ghi vẫn bị coi là đã hoàn tất.
5. **Retry không idempotent:** Một trang có thể được gửi hai lần sau lỗi.
6. **Giữ `ResultSet` ngoài transaction/connection của nó:** Có thể ném lỗi hoặc đọc sai do tài nguyên đã đóng.
7. **Không phân biệt `NULL`:** `getLong` trả 0 cho SQL NULL; phải gọi `wasNull()` nếu cột nullable/kiểm tra hợp đồng.
8. **Transaction dài bị timeout/abort:** Một job lớn có thể thất bại muộn; cần chiến lược resume hoặc chia trang.

Nếu chỉ cần đọc một snapshot đã commit và xuất file, có thể dùng một transaction đọc phù hợp và kết thúc đúng sau khi xử lý. Nếu cần thay đổi DB trong lúc scan, phải thiết kế riêng quy tắc transaction, khóa, batching và các tình huống xử lý lỗi; không biến một callback đọc thành nơi commit ngẫu nhiên.

## 16. Đo kiểm mức dùng bộ nhớ trên dữ liệu thật

Một chương trình chạy tốt với 100 dòng chưa chứng minh phù hợp với 10 triệu dòng. Cần kiểm thử trên driver/DBMS mục tiêu với dữ liệu đại diện.

### 16.1. Các chỉ số nên đo

| Chỉ số | Mục đích |
| --- | --- |
| **Peak Java heap** | Phát hiện collection hay driver buffer tăng theo tổng số dòng |
| **RSS/native memory** | Nhận ra memory ngoài heap, buffer/socket/driver |
| **GC pauses và allocation rate** | Xem có tạo quá nhiều object tạm hay không |
| **Rows/second** | Đánh giá throughput thực tế |
| **DB round trips/fetch count** | Kiểm chứng `fetchSize` và cursor có hiệu lực |
| **Connection/transaction duration** | Phát hiện cursor/transaction giữ quá lâu |
| **Pool active/waiting** | Đánh giá ảnh hưởng đến request khác |
| **Số dòng và checksum đầu ra** | Kiểm chứng không mất/trùng dữ liệu |
| **Số batch đang chờ** | Xác minh backpressure thực sự giới hạn bộ nhớ |
| **Thời gian cleanup khi lỗi** | Xem có rò result set, connection, file handle không |

Một thử nghiệm tốt có **các mức tổng số dòng tăng dần**: 10 nghìn, 100 nghìn, 1 triệu... Mục tiêu không phải heap tuyệt đối bằng nhau ở mọi thời điểm, mà là tránh xu hướng đỉnh bộ nhớ tăng gần tuyến tính với **tổng số dòng**, khi kích thước một dòng và cấu hình fetch/batch giữ tương tự.

### 16.2. Test nào cho biết code còn nạp hết vào List?

Đưa vào test dataset lớn hơn khả năng chứa trong `List` theo ngân sách bộ nhớ. Chạy:

- **Baseline:** `findAll()` đọc mọi dòng thành `List`.
- **Consumer:** `scanOrders(consumer)` ghi từng dòng ra một sink không giữ dữ liệu.
- **Batch giới hạn:** xử lý từng batch 250 dòng, không có queue vô hạn.
- **Keyset:** xử lý các trang 500 dòng và đóng connection sau từng trang.

So sánh peak memory và thời gian xử lý. Nếu consumer vẫn tăng bộ nhớ theo toàn bộ dữ liệu, kiểm tra driver streaming, buffer của serializer/output, callback giữ tham chiếu hoặc memory leak.

### 16.3. Các ca lỗi phải kiểm thử

- Result set rỗng: callback không chạy; tài nguyên vẫn đóng.
- Một dòng và đúng ngưỡng batch: không bị xử lý hai lần.
- Batch cuối nhỏ hơn `BATCH_SIZE`: vẫn được xử lý.
- Callback ném `IOException` giữa vòng lặp: result set, statement và connection được đóng.
- SQL timeout hoặc connection mất giữa fetch: lỗi được chuyển lên, không trả thành công giả.
- Consumer chậm hoặc hủy request: không giữ connection vô hạn.
- Driver không áp dụng `fetchSize` như kỳ vọng: đo memory và tìm cấu hình phù hợp.
- Keyset khi có chèn/xóa đồng thời: chính sách nhất quán được mô tả và kiểm thử.
- Job resume: không mất dữ liệu khi lỗi ngay sau sink ghi thành công nhưng trước khi lưu checkpoint.
- Pool nhỏ và nhiều job đồng thời: không cạn connection vì giữ quá nhiều cursor.
- Tệp đầu ra lỗi: file tạm/đánh dấu chưa hoàn tất được dọn theo chính sách.

## 17. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Giải pháp |
| --- | --- | --- |
| `List<OrderRow> findAll()` với bảng rất lớn | Heap tăng theo tổng dòng | Callback, batch giới hạn hoặc phân trang |
| `setFetchSize(500)` nhưng vẫn `rows.add(...)` mãi | Driver có thể fetch theo lô nhưng ứng dụng giữ tất cả | Bỏ danh sách tổng hoặc giới hạn kích thước |
| Dùng `setMaxRows(500)` và nghĩ đã export hết | Chỉ lấy tối đa 500 dòng | Dùng fetch size hoặc phân trang đủ dữ liệu |
| Trả `Stream` gắn với `ResultSet` đã đóng | Lỗi đọc lazy | Giữ vòng đời JDBC trong callback hoặc cursor wrapper đúng hợp đồng |
| Queue không giới hạn | OOM ở worker xử lý sau | Bounded queue và backpressure |
| Gửi HTTP trên từng dòng trong transaction dài | Chiếm connection, giữ snapshot/khóa | Batch, file trung gian, phân trang |
| `OFFSET` hàng triệu | Có thể phải quét bỏ nhiều dòng, dễ lệch khi dữ liệu thay đổi | Keyset với index/khóa ổn định |
| Bắt lỗi và trả `List` đã có một phần | Caller hiểu nhầm là dữ liệu đầy đủ | Báo lỗi, ghi trạng thái partial, chính sách resume |
| Không phân biệt `NULL` và giá trị mặc định của getter | Sai dữ liệu | Getter object hoặc `wasNull()` |
| Nghĩ `while (rs.next())` đồng nghĩa driver streaming | Vẫn có thể OOM từ driver | Kiểm thử trên DBMS/driver thật |

## 18. Bài tập tự luyện

### Bài 1 — Phân tích bộ nhớ

Cho chương trình:

~~~java
List<UserDto> users = new ArrayList<>();
while (rs.next()) {
    users.add(mapUser(rs));
}
sendToClient(users);
~~~

Hãy nêu ít nhất ba vị trí có thể giữ bản sao dữ liệu và đề xuất thiết kế để không cần nạp toàn bộ `users` trước khi gửi.

**Gợi ý:** Driver buffer, danh sách `users` và serializer/output. Dùng callback ghi tuần tự qua một writer/streaming serializer và kiểm tra fetch của driver.

### Bài 2 — Kiểm chứng `fetchSize`

Một developer gọi `ps.setFetchSize(100)` nhưng vẫn thấy heap tăng theo số dòng. Có thể kết luận JDBC bị lỗi không?

**Gợi ý:** Không. Driver có thể vẫn materialize kết quả hoặc callback giữ tất cả DTO. `fetchSize` là hint, không phải memory cap.

### Bài 3 — Batch đồng bộ và bất đồng bộ

Đoạn code sau có nguy cơ gì?

~~~java
List<OrderRow> batch = new ArrayList<>();
while (rs.next()) {
    batch.add(mapOrder(rs));
    if (batch.size() == 200) {
        executor.submit(() -> processBatch(batch));
        batch.clear();
    }
}
~~~

**Gợi ý:** Lambda giữ tham chiếu đến danh sách đang bị `clear`, dữ liệu có thể bị mất/sai hoặc truy cập đồng thời không an toàn. Cần bản sao immutable, bounded executor/queue và chờ backpressure.

### Bài 4 — Tính nhất quán khi phân trang

Job lưu `lastId=5000`, sau đó một dòng mới có `id=3000` được insert. Lần đọc tiếp theo dùng `WHERE id > 5000`. Dòng mới có được đọc không?

**Gợi ý:** Không. Keyset dựa theo khóa không cung cấp snapshot đầy đủ khi có insert với khóa cũ. Cần quyết định quy tắc dataset/snapshot của job.

### Bài 5 — Tránh mất dữ liệu khi retry

Sink đã nhận thành công dòng `id=800`, nhưng process chết trước khi lưu checkpoint. Sau restart, job có thể gửi lại dòng 800. Cần thiết kế gì?

**Gợi ý:** Idempotency hoặc upsert/dedup theo khóa ở sink; checkpoint chỉ sau xác nhận bền vững và quản lý phạm vi retry.

### Bài 6 — Chọn chiến lược

Hãy chọn giữa (a) `List` nhỏ có limit, (b) callback từng dòng, (c) batch có giới hạn, (d) keyset pagination cho: màn hình 50 dòng, CSV 100.000 dòng, đồng bộ API theo batch 200 dòng, và job 20 triệu dòng cần resume.

**Gợi ý:** Tương ứng (a), (b), (c), (d). Trong thực tế có thể kết hợp keyset với batch hoặc callback.

---

## 19. Checklist trước khi đưa vào production

- [ ] Query chỉ chọn cột cần thiết; có điều kiện lọc và `ORDER BY` phù hợp.
- [ ] Không có collection/queue/StringBuilder tăng vô hạn trên đường đi của dữ liệu.
- [ ] `ResultSet`, `PreparedStatement` và `Connection` được đóng rõ ràng.
- [ ] Không trả lazy stream/cursor sau khi đã đóng JDBC resources.
- [ ] Consumer đồng bộ không giữ mọi DTO; consumer bất đồng bộ có queue/batch giới hạn.
- [ ] Đã kiểm tra `setFetchSize` và yêu cầu của driver/DBMS để fetch tăng dần.
- [ ] Có ngân sách heap, đo memory/GC và test với số dòng lớn.
- [ ] Nếu transaction/cursor dài, đã xem xét snapshot, timeout và ảnh hưởng tới pool.
- [ ] Nếu dùng keyset, khóa sắp xếp ổn định, có index và chính sách thay đổi dữ liệu.
- [ ] Có checkpoint/idempotency nếu job cần resume.
- [ ] Lỗi SQL/I/O/cancel không khiến kết quả dang dở bị công bố là hoàn chỉnh.
- [ ] Dữ liệu nhạy cảm không bị đưa vào log, file tạm hay queue không được phép.

**Nguyên tắc ghi nhớ:** Để **tránh nạp toàn bộ `ResultSet` vào danh sách lớn** trong JDBC, hãy thiết kế luồng dữ liệu theo hướng **đọc → xử lý/ghi ngay → giải phóng**, hoặc giữ một batch có giới hạn. Kết hợp với cấu hình fetch thực tế của driver, giới hạn dữ liệu bằng SQL, quản lý vòng đời connection và phân trang khi cần. Mục tiêu không phải loại bỏ mọi `List`, mà là **không để bộ nhớ tăng theo toàn bộ số dòng mà nghiệp vụ phải xử lý**.
