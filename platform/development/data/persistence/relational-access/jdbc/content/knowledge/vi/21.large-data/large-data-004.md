# Đọc dữ liệu lớn mà không nạp toàn bộ vào bộ nhớ

Khi một ứng dụng Java phải xuất hàng triệu dòng báo cáo, duyệt lịch sử giao dịch hoặc tải một tệp lớn từ cơ sở dữ liệu, cách viết đơn giản **đọc tất cả kết quả vào một `List` rồi mới xử lý** có thể khiến bộ nhớ tăng theo kích thước dữ liệu. Trong JDBC, hướng tiếp cận phù hợp là **đọc và xử lý tăng dần**: lấy từng dòng từ `ResultSet`, truyền kết quả sang nơi nhận, hoặc đọc dữ liệu BLOB/CLOB qua luồng (`InputStream`/`Reader`).

Tuy nhiên, **`while (rs.next())` chưa đủ để bảo đảm truy vấn thật sự stream từ server**. Driver có thể tải hoặc đệm nhiều dòng trước khi cung cấp cho Java. Vì vậy, ngoài cách viết vòng lặp, ứng dụng phải kiểm soát cách fetch của JDBC driver, số cột và kích thước mỗi trường, vòng đời `Connection`/`ResultSet`, transaction và tốc độ xử lý của nơi nhận.

Bài học thuộc chương **Dữ liệu lớn** của module **JDBC**, áp dụng các API chuẩn `DataSource`, `PreparedStatement`, `ResultSet`, `setFetchSize`, `getBinaryStream` và `getCharacterStream`.

Sau bài học, bạn có thể:

- Nhận ra vì sao `ResultSet` duyệt từng dòng vẫn có thể tiêu tốn nhiều RAM.
- Duyệt hàng triệu dòng với bộ nhớ ứng dụng gần như không phụ thuộc tổng số dòng, khi driver hỗ trợ fetch tăng dần.
- Chọn `fetchSize` và cấu hình cursor/streaming phù hợp với từng DBMS.
- Xuất dữ liệu ra `Writer`/`OutputStream` mà không gom toàn bộ vào `List`, `String` hoặc mảng byte.
- Đọc dữ liệu `BLOB`/`CLOB` theo từng khối mà không gọi `getBytes`/`getString` cho toàn bộ tệp.
- Cân nhắc keyset pagination khi một cursor kéo dài gây khóa, giữ snapshot hoặc chiếm connection.
- Kiểm thử bộ nhớ, tính đầy đủ của dữ liệu, timeout và khả năng dọn dẹp khi lỗi.

## 1. Vấn đề: từ vài trăm dòng đến hàng triệu dòng

Một cách truy vấn quen thuộc là đọc toàn bộ dòng vào `List`:

~~~java
List<Order> orders = new ArrayList<>();

try (PreparedStatement ps = connection.prepareStatement(
        "SELECT id, amount, status FROM orders");
     ResultSet rs = ps.executeQuery()) {

    while (rs.next()) {
        orders.add(new Order(
                rs.getLong("id"),
                rs.getBigDecimal("amount"),
                rs.getString("status")));
    }
}

return orders;
~~~

Đoạn mã trên có thể phù hợp với một trang dữ liệu nhỏ, nhưng `orders` sẽ tăng theo số dòng. Nếu mỗi đối tượng Java cùng các chuỗi và cấu trúc phụ chiếm trung bình 300 byte, một triệu bản ghi đã có thể cần khoảng 300 MB chỉ cho dữ liệu được ánh xạ, chưa tính chi phí của `ArrayList`, kết quả trong JDBC driver, hàng đợi xử lý, mã hóa JSON và hoạt động của garbage collector. Đây là phép tính minh họa, không phải kích thước cố định của một đối tượng Java.

Các yếu tố làm tăng áp lực bộ nhớ thường nằm trên **nhiều tầng**:

~~~mermaid
flowchart LR
    A["Database"] --> B["Network / JDBC driver buffer"]
    B --> C["ResultSet"]
    C --> D["Java DTO / List"]
    D --> E["JSON / CSV / file buffer"]
    E --> F["Nơi nhận"]
~~~

Ngay cả khi bỏ `List`, tầng driver vẫn có thể tải cả kết quả. Ngược lại, cấu hình cursor tốt cũng không giúp nếu ứng dụng gọi `collect(toList())`, gom tất cả thành `StringBuilder` hoặc tạo một mảng byte chứa toàn bộ BLOB.

Mục tiêu nên là **bộ nhớ bị chặn bởi số dòng/byte đang được xử lý**, chẳng hạn một lô fetch, một dòng và một bộ đệm đầu ra, thay vì bị chặn bởi tổng kích thước truy vấn.

## 2. Ba kỹ thuật cần phân biệt

| Kỹ thuật | Kiểm soát gì? | Phù hợp với | Giới hạn cần nhớ |
| --- | --- | --- | --- |
| **Duyệt `ResultSet` từng dòng** | Không tích lũy đối tượng ở tầng ứng dụng | Báo cáo, xử lý dữ liệu tuần tự | Driver vẫn có thể đệm cả kết quả |
| **Fetch/cursor từ server** | Số dòng driver nhận mỗi lượt hoặc cách driver lấy dữ liệu | Kết quả nhiều dòng | `setFetchSize` chỉ là *hint* JDBC; hành vi phụ thuộc driver và transaction |
| **Stream BLOB/CLOB** | Đọc nội dung một trường lớn theo nhiều khối | File, ảnh, tài liệu, nội dung văn bản lớn | Đọc luồng phải hoàn tất khi `ResultSet` và connection còn mở; driver có thể có cách đệm riêng |
| **Keyset pagination** | Chia truy vấn thành những trang nhỏ theo khóa ổn định | Job dài, resume, xử lý theo lô | Không tự mang lại snapshot nhất quán giữa các trang |
| **Batch xử lý giới hạn** | Chỉ giữ tối đa N đối tượng rồi ghi/xử lý và giải phóng | Import/export, pipeline xử lý theo lô | Không để các batch tích lũy mãi ở bộ nhớ hoặc queue khác |

Trong thực tế, một hệ thống thường kết hợp nhiều kỹ thuật. Ví dụ: truy vấn phân trang theo ID, trong mỗi trang duyệt `ResultSet` từng dòng, và đối với cột nhị phân lớn thì dùng `getBinaryStream`.

## 3. `ResultSet` duyệt tiến và `fetchSize`

Một `ResultSet` là một cursor API mà ứng dụng gọi `rs.next()` để di chuyển. Cấu hình thông dụng cho xử lý tuần tự:

~~~java
String sql = "SELECT id, amount, status "
           + "FROM orders WHERE id >= ? ORDER BY id";

try (PreparedStatement ps = connection.prepareStatement(
        sql,
        ResultSet.TYPE_FORWARD_ONLY,
        ResultSet.CONCUR_READ_ONLY)) {

    ps.setLong(1, startId);
    ps.setFetchSize(500);

    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            long id = rs.getLong("id");
            BigDecimal amount = rs.getBigDecimal("amount");
            String status = rs.getString("status");

            // Xử lý ngay, không thêm vào List tăng vô hạn.
        }
    }
}
~~~

Ý nghĩa các lựa chọn:

- `TYPE_FORWARD_ONLY`: duyệt tiến từ đầu đến cuối; không yêu cầu chức năng kéo ngược cursor.
- `CONCUR_READ_ONLY`: chỉ đọc dữ liệu; không cần cơ chế cập nhật dòng qua `ResultSet`.
- `setFetchSize(500)`: **gợi ý** driver lấy khoảng 500 dòng mỗi lượt; không phải giới hạn cứng của bộ nhớ hoặc điều khoản bắt buộc server chỉ gửi đúng 500 dòng.
- `ORDER BY id`: giúp định nghĩa thứ tự ổn định cho báo cáo và phục vụ cơ chế tiếp tục theo khóa, miễn `id` là khóa duy nhất, không đổi.
- `while (rs.next())`: xử lý lần lượt từng dòng, miễn hàm xử lý cũng không tích lũy kết quả vô hạn.

Một số driver có thể trả về toàn bộ kết quả dù `setFetchSize` dương; một số cần thêm thuộc tính connection, tắt auto-commit hoặc chế độ server-side cursor. **Không thể khẳng định kết quả streaming chỉ bằng cách đọc đoạn Java này.**

### Các phương thức liên quan dễ bị hiểu nhầm

| API | Vai trò thực tế |
| --- | --- |
| `Statement.setFetchSize(n)` | Hint về số dòng nên fetch mỗi lượt |
| `ResultSet.setFetchSize(n)` | Có thể điều chỉnh hint cho result set hiện có, nếu driver hỗ trợ |
| `Statement.getFetchSize()` | Cho biết hint đã thiết lập hoặc giá trị driver báo cáo; không chứng minh RAM đang dùng |
| `Statement.setMaxRows(n)` | Giới hạn tổng số dòng được trả về; không thay thế streaming khi cần đọc **toàn bộ** dữ liệu |
| `Statement.setQueryTimeout(seconds)` | Yêu cầu driver giới hạn thời gian thực thi câu lệnh; không bảo đảm mọi loại chờ mạng/đọc stream đều dừng đúng hạn |
| `Connection.setReadOnly(true)` | Hint/thiết lập read-only tùy driver và DBMS; không phải cơ chế giới hạn bộ nhớ |
| `Statement.setFetchDirection(ResultSet.FETCH_FORWARD)` | Hint hướng fetch khi driver hỗ trợ; không bật streaming một cách phổ quát |

`setFetchSize(0)` thường để driver sử dụng thiết lập mặc định. Tránh lấy một giá trị như 500, 1.000 hay 10.000 làm đáp án tuyệt đối: lựa chọn hợp lý phụ thuộc kích thước dòng, độ trễ mạng, giới hạn RAM, cách driver prefetch và tài nguyên DB.

## 4. Ví dụ đầy đủ: xuất CSV từng dòng với `DataSource`

Giả sử bảng `orders` đã có:

~~~sql
CREATE TABLE orders (
    id BIGINT PRIMARY KEY,
    amount DECIMAL(19, 2) NOT NULL,
    status VARCHAR(32) NOT NULL
);
~~~

Ta cần xuất một tập lớn các đơn hàng sang CSV. Thay vì tạo `List<Order>` hoặc `StringBuilder` cho mọi dòng, phương thức nhận một `Writer` của caller và ghi ngay từng dòng.

~~~java
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
    private final DataSource dataSource;

    public OrderCsvExporter(DataSource dataSource) {
        this.dataSource = Objects.requireNonNull(dataSource);
    }

    public long exportFrom(long startId, Writer output)
            throws SQLException, IOException {
        Objects.requireNonNull(output, "output");

        String sql = "SELECT id, amount, status "
                   + "FROM orders WHERE id >= ? ORDER BY id";

        try (Connection connection = dataSource.getConnection()) {
            // Read-only được đặt trước khi bắt đầu transaction.
            connection.setReadOnly(true);
            // Với một số driver, ví dụ pgJDBC, cursor fetch
            // cần auto-commit được tắt.
            connection.setAutoCommit(false);

            try {
                long writtenRows = 0;

                try (PreparedStatement ps = connection.prepareStatement(
                        sql,
                        ResultSet.TYPE_FORWARD_ONLY,
                        ResultSet.CONCUR_READ_ONLY)) {

                    ps.setLong(1, startId);
                    ps.setFetchSize(500);
                    ps.setQueryTimeout(120);

                    output.write("id,amount,status\n");

                    try (ResultSet rs = ps.executeQuery()) {
                        while (rs.next()) {
                            long id = rs.getLong("id");
                            if (rs.wasNull()) {
                                throw new SQLException("orders.id là NULL");
                            }

                            BigDecimal amount = rs.getBigDecimal("amount");
                            String status = rs.getString("status");

                            if (amount == null || status == null) {
                                throw new SQLException(
                                        "Dữ liệu bắt buộc là NULL");
                            }

                            output.write(Long.toString(id));
                            output.write(',');
                            output.write(amount.toPlainString());
                            output.write(',');
                            writeCsvField(output, status);
                            output.write('\n');

                            writtenRows++;
                        }
                    }
                }

                // Chỉ đọc: kết thúc transaction, không có thay đổi DML.
                connection.rollback();
                return writtenRows;

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

    private static void writeCsvField(Writer output, String value)
            throws IOException {
        // Escape dấu ngoặc kép theo quy ước CSV.
        output.write('"');

        for (int i = 0; i < value.length(); i++) {
            char character = value.charAt(i);
            if (character == '"') {
                output.write('"');
            }
            output.write(character);
        }

        output.write('"');
    }
}
~~~

Cách sử dụng khi đã có `DataSource` và file đích:

~~~java
import java.io.BufferedWriter;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;

OrderCsvExporter exporter = new OrderCsvExporter(dataSource);
Path destination = Paths.get("orders-export.csv");

try (BufferedWriter writer = Files.newBufferedWriter(
        destination, StandardCharsets.UTF_8)) {

    long exported = exporter.exportFrom(1L, writer);
    System.out.println("Số dòng đã xuất: " + exported);
}
~~~

Trong ví dụ:

1. **Không có `List` chứa toàn bộ kết quả.** Mỗi dòng được đọc, ghi ra `Writer` rồi xử lý dòng tiếp.
2. **`Writer` do caller sở hữu.** Repository không đóng writer; caller quyết định dùng file, response HTTP hoặc luồng đầu ra khác. `BufferedWriter` giúp hạn chế số lần ghi vật lý nhỏ.
3. **Các cột được chọn có kích thước tương đối nhỏ.** `getString("status")` chỉ materialize một ô `VARCHAR(32)`; nếu cột là CLOB hàng gigabyte, phải chọn `getCharacterStream` thay vì `getString`.
4. **`setFetchSize(500)` chỉ là hint.** Trên pgJDBC, `autoCommit=false` và fetch size dương là một phần điều kiện cần để sử dụng cursor-based fetching với result set forward-only. Driver khác có quy tắc khác.
5. **Transaction chỉ đọc kết thúc bằng `rollback()`.** Trong ví dụ không có DML, rollback dùng để kết thúc transaction sau khi xuất xong. Nếu ứng dụng yêu cầu commit một transaction đọc vì chính sách riêng, có thể thiết kế lại; đừng để transaction mở vô hạn.
6. **Ngoại lệ đầu ra cũng khiến tài nguyên JDBC được đóng.** Nếu `Writer` gặp `IOException` (ổ đĩa đầy, client ngắt kết nối), truy vấn dừng và connection được dọn theo best effort.
7. **Gọi `setReadOnly(true)` không cấp quyền bảo mật.** Tài khoản DB vẫn cần được cấp quyền thích hợp; khả năng read-only còn phụ thuộc driver và database.
8. **Đây là CSV cho pipeline do ứng dụng kiểm soát.** Nếu các cột văn bản đến từ người dùng và CSV được mở bằng phần mềm bảng tính, cần thêm chính sách xử lý CSV/formula injection. Chỉ thêm dấu ngoặc kép theo CSV chưa đủ để ngăn một ô bị diễn giải thành công thức.

**Bộ nhớ ứng dụng** của exporter phụ thuộc bộ đệm writer, dữ liệu của dòng hiện tại và lượng dữ liệu mà JDBC driver đệm; ứng dụng không nhân bộ nhớ theo số dòng. Tuy vậy, nếu driver vẫn tải toàn bộ kết quả từ server, thiết kế này chưa bảo đảm tổng bộ nhớ process bị chặn. Cần xác minh cấu hình và hành vi bằng test.

### Lưu ý khi xuất qua HTTP

Nếu `output` là `Writer` gắn với response HTTP, một client rất chậm có thể khiến transaction và DB connection mở trong thời gian dài. Tùy mục tiêu sản phẩm, có thể xuất trước sang file lưu trữ tạm hoặc dùng job nền có phân trang theo khóa, sau đó cho client tải file. Đồng thời xử lý khi client hủy request để đóng `ResultSet` và kết thúc transaction kịp thời.

## 5. Tùy driver: thế nào là streaming thực sự?

Các thuộc tính cần thiết cho fetch tăng dần **không hoàn toàn có thể di chuyển giữa DBMS**. Bảng sau là định hướng thiết kế, không thay thế tài liệu phiên bản driver đang chạy.

| Driver/DBMS | Hướng tiếp cận thường dùng | Điều cần kiểm chứng |
| --- | --- | --- |
| **PostgreSQL / pgJDBC** | `setFetchSize(n > 0)`, `autoCommit=false`, `TYPE_FORWARD_ONLY`; driver có thể dùng cursor qua các lần fetch | Driver/server version, transaction vẫn mở, truy vấn có đáp ứng điều kiện cursor hay không |
| **MySQL / Connector/J** | Chế độ cursor fetch với thuộc tính driver như `useCursorFetch=true` và fetch size dương; một số phiên bản/cấu hình liên quan server-side prepared statements | Thuộc tính URL, kiểu statement, việc driver có đệm toàn bộ kết quả mặc định không |
| **MySQL legacy streaming** | Một số phiên bản Connector/J hỗ trợ kiểu streaming đặc thù với forward-only, read-only và `setFetchSize(Integer.MIN_VALUE)` | Đây là cơ chế **riêng của driver**, không dùng giá trị âm đó như quy tắc JDBC chung |
| **SQL Server / Microsoft JDBC Driver** | Adaptive buffering và các chế độ `responseBuffering`/fetch theo đặc tính driver | Driver có materialize toàn bộ cột/result không, khả năng streaming LOB và các giới hạn kết quả |
| **Oracle JDBC** | Row prefetch/fetch size và kiểu result set phù hợp | Số lần round trip, kích thước prefetched rows, ảnh hưởng của LOB và thuộc tính driver |
| **SQLite** | Truy vấn được thực thi trong engine cục bộ; cơ chế server cursor qua mạng không áp dụng giống DBMS client/server | Bộ nhớ engine, cách driver ánh xạ row, transaction và read-lock |

Khi chạy thử, cần xem **dòng dữ liệu có thực sự được lấy theo lô hay chỉ `next()` đang duyệt một cấu trúc đã materialize?** Có thể đo resident memory/heap, thống kê số lượt fetch/round trip bằng công cụ driver hoặc DBMS, và thử với tập lớn hơn RAM thực tế. `getFetchSize()==500` chỉ xác nhận cấu hình hint, không xác nhận streaming.

### Chọn fetch size

Giả sử mỗi dòng dữ liệu cần trung bình 2 KB ở phần đệm driver: 500 dòng tương đương khoảng 1 MB dữ liệu thô mỗi đợt, chưa tính overhead, metadata, chuyển kiểu và cách driver thực thi. Nếu một dòng có BLOB 5 MB, cùng fetch size có thể rất tốn bộ nhớ.

Thực nghiệm có thể dùng các mức như 100, 500, 2.000, sau đó đánh giá:

- **Peak heap/RSS** của Java process.
- Thời gian tổng và số round trip tới database.
- Độ trễ xử lý một batch và thời gian giữ transaction.
- Mức ảnh hưởng đến server, connection pool và các truy vấn khác.
- Lỗi timeout, server cursor, lock và tính nhất quán dữ liệu.

Fetch size quá nhỏ có thể tăng số lượt round trip; quá lớn có thể làm tăng bộ đệm và garbage collection. Không có một giá trị tối ưu chung cho mọi câu truy vấn.

## 6. Đọc BLOB mà không tạo một mảng byte khổng lồ

Với dữ liệu nhị phân lớn, tránh `ResultSet.getBytes(column)` nếu kích thước không bị giới hạn: API này trả một `byte[]` chứa toàn bộ giá trị. Thay vào đó, dùng `getBinaryStream` để đọc từng khối.

Giả sử bảng có cột nhị phân tên `file_body`; **kiểu SQL của cột có thể là `BLOB`, `BYTEA`, `VARBINARY(MAX)` hoặc kiểu riêng của DBMS**.

~~~java
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.Objects;
import javax.sql.DataSource;

public final class DocumentDownloader {
    private final DataSource dataSource;

    public DocumentDownloader(DataSource dataSource) {
        this.dataSource = Objects.requireNonNull(dataSource);
    }

    public long copyBody(long id, OutputStream destination)
            throws SQLException, IOException {

        Objects.requireNonNull(destination, "destination");

        String sql = "SELECT file_body FROM documents WHERE id = ?";

        try (Connection connection = dataSource.getConnection();
             PreparedStatement ps = connection.prepareStatement(
                     sql,
                     ResultSet.TYPE_FORWARD_ONLY,
                     ResultSet.CONCUR_READ_ONLY)) {

            ps.setLong(1, id);
            ps.setFetchSize(1);

            try (ResultSet rs = ps.executeQuery()) {
                if (!rs.next()) {
                    throw new SQLException("Không tìm thấy tài liệu");
                }

                try (InputStream input = rs.getBinaryStream("file_body")) {
                    if (input == null) {
                        throw new SQLException("Nội dung tài liệu là NULL");
                    }

                    byte[] buffer = new byte[64 * 1024];
                    long totalBytes = 0L;
                    int count;

                    while ((count = input.read(buffer)) != -1) {
                        destination.write(buffer, 0, count);
                        totalBytes += count;
                    }

                    return totalBytes;
                }
            }
        }
    }
}
~~~

Lợi ích của cách viết:

- Dùng **một mảng byte 64 KiB**, tái sử dụng cho mọi lần đọc.
- Không gọi `getBytes`, `readAllBytes`, `ByteArrayOutputStream` rồi `toByteArray` để materialize cả tệp.
- Giữ `ResultSet`, `PreparedStatement` và `Connection` mở **trong khi đọc stream**.
- Không đóng `OutputStream` do caller cung cấp; caller có thể là file hoặc HTTP response và chịu trách nhiệm đóng nó.
- Không gọi `rs.next()` hoặc đóng `ResultSet` **trước khi** đọc xong nội dung nhị phân đang mở.
- Không dùng `InputStream.available()` để quyết định đã hết dữ liệu; vòng `read(...) != -1` mới xác định EOF đúng.

Điểm cần thận trọng: **`getBinaryStream` cung cấp giao diện streaming, nhưng driver vẫn có thể materialize một phần hoặc toàn bộ LOB trong một số cấu hình.** Với tệp nhiều GB, cần kiểm tra tài liệu driver và quan sát bộ nhớ trong một bài test trên DB thật. Một số driver yêu cầu transaction vẫn mở khi truy cập LOB locator; ví dụ nên được điều chỉnh theo DBMS nếu xuất hiện lỗi cursor/locator.

Đối với dữ liệu nhạy cảm, việc stream không thay thế kiểm tra **quyền truy cập**. Câu SQL thực tế có thể phải thêm điều kiện tenant/owner đã tham số hóa, và không log hoặc lưu bản sao BLOB ngoài nơi được phép.

### Đọc CLOB theo `Reader`

Nếu cột chứa văn bản dài (`CLOB` hoặc kiểu text dung lượng lớn), dùng `getCharacterStream` thay vì `getString`:

~~~java
try (Reader source = rs.getCharacterStream("large_text")) {
    if (source == null) {
        throw new SQLException("large_text là NULL");
    }

    char[] buffer = new char[16 * 1024];
    int charsRead;

    while ((charsRead = source.read(buffer)) != -1) {
        destinationWriter.write(buffer, 0, charsRead);
    }
}
~~~

Đoạn này giả định `rs` và `destinationWriter` đã được tạo và còn mở, đồng thời đã import `java.io.Reader`. `Reader`/`Writer` làm việc với ký tự; cách mã hóa UTF-8 hay khác được quyết định ở ranh giới tạo stream đầu ra, chẳng hạn `OutputStreamWriter`.

**Một chuỗi Java `String` có kích thước của cả CLOB vẫn tiêu tốn bộ nhớ theo kích thước cột.** Tránh nối chuỗi từng phần vào một `StringBuilder` nếu mục tiêu là xuất liên tục.

## 7. Không làm hỏng streaming trong tầng xử lý

Ngay cả khi driver fetch theo lô, cách tổ chức pipeline vẫn có thể khiến bộ nhớ tăng vô hạn.

Các dạng code cần xem lại:

~~~java
// 1. Tích lũy toàn bộ dữ liệu.
List<Row> all = new ArrayList<>();
while (rs.next()) {
    all.add(mapRow(rs));
}

// 2. Gom toàn bộ nội dung vào một chuỗi.
StringBuilder allText = new StringBuilder();
while (rs.next()) {
    allText.append(rs.getString("description"));
}

// 3. Bỏ toàn bộ kết quả vào queue không giới hạn.
while (rs.next()) {
    unboundedQueue.add(mapRow(rs));
}
~~~

Cách thay thế:

- **Consumer đồng bộ:** xử lý/ghi từng dòng ngay trong vòng `while (rs.next())`.
- **Batch giới hạn:** giữ một danh sách cố định khoảng 100–1.000 dòng, xử lý xong rồi gọi `clear()` trước batch sau.
- **Queue có giới hạn:** dùng `ArrayBlockingQueue` hoặc cơ chế backpressure, bảo đảm producer chờ nếu consumer chậm.
- **File/stream output:** ghi trực tiếp qua `BufferedWriter` hoặc `BufferedOutputStream`, không gom toàn bộ ở Java heap.
- **Không chia sẻ `ResultSet` giữa các thread:** đọc và xử lý trong phạm vi connection/statement đang sở hữu; nếu cần xử lý song song, chuyển sang các DTO nhỏ có giới hạn số lượng.

### Ví dụ batch giới hạn

~~~java
List<SmallRow> batch = new ArrayList<>(500);

while (rs.next()) {
    batch.add(mapSmallRow(rs));

    if (batch.size() == 500) {
        processBatch(batch);
        batch.clear();
    }
}

if (!batch.isEmpty()) {
    processBatch(batch);
    batch.clear();
}
~~~

`processBatch` phải xử lý xong hoặc chuyển quyền sở hữu sang một hàng đợi **có giới hạn** trước khi trả về. Nếu nó giữ tham chiếu đến `batch` ở nơi khác hoặc tạo một danh sách tổng hợp tăng vô hạn, bộ nhớ vẫn có thể tăng. Không dùng lại chính `batch` nếu consumer bất đồng bộ còn đang truy cập danh sách đó.

Giới hạn batch cũng cần dựa trên **số byte trung bình mỗi dòng**, không chỉ số dòng. 500 dòng có metadata ngắn khác xa 500 dòng chứa chuỗi nhiều MB.

## 8. Cursor kéo dài hay keyset pagination?

Cursor là một cách đọc liên tục, nhưng đôi khi phải giữ transaction/connection mở lâu để driver lấy thêm dữ liệu. Với các job chạy nhiều giờ hoặc có consumer chậm, điều này có thể giữ snapshot, khóa hoặc tài nguyên cursor phía server, tăng áp lực lên database và chiếm connection pool.

**Keyset pagination** (seek pagination) là phương án chia thành các truy vấn giới hạn số dòng theo khóa sắp xếp ổn định.

Ví dụ dưới đây dùng **cú pháp `LIMIT` của PostgreSQL/MySQL**, không phải SQL dùng chung mọi DBMS:

~~~sql
SELECT id, amount, status
FROM orders
WHERE id > ?
ORDER BY id ASC
LIMIT ?;
~~~

Lần đầu truyền `lastId = 0` và `pageSize = 500`; sau khi xử lý xong trang, lấy `id` lớn nhất đã xử lý làm `lastId` rồi truy vấn trang kế tiếp. Nếu không còn dòng, job hoàn thành.

~~~mermaid
flowchart TD
    S["lastId = điểm bắt đầu"] --> Q["SELECT WHERE id > lastId ORDER BY id LIMIT N"]
    Q --> E{"Có dòng nào?"}
    E -->|Không| D["Hoàn tất"]
    E -->|Có| P["Xử lý từng dòng của trang"]
    P --> U["Cập nhật lastId = id cuối"]
    U --> Q
~~~

Ưu điểm:

- Một trang được truy vấn và xử lý trong khoảng thời gian ngắn, sau đó giải phóng connection.
- Không cần giữ một server cursor/transaction từ đầu đến cuối hàng triệu dòng.
- Có thể lưu lại `lastId` như **checkpoint** và tiếp tục sau lỗi.
- Với index phù hợp trên `id`, thường tránh được việc quét bỏ qua số lượng dòng lớn như `OFFSET` tăng dần.

Giới hạn:

1. **Cần thứ tự toàn phần, ổn định.** `id` nên là khóa duy nhất, không đổi, tăng theo quy tắc thích hợp. Nếu sắp xếp bằng `created_at`, dùng thêm khóa duy nhất để phá hòa và điều kiện seek tương ứng.
2. **Không tự bảo đảm snapshot nhất quán.** Dữ liệu có thể được insert, update hoặc delete giữa các trang; những bản ghi mới có khóa nhỏ hơn `lastId` có thể bị bỏ qua, còn dòng có giá trị sort thay đổi có thể bị đọc lặp hoặc bỏ sót.
3. **Checkpoint cần gắn với xác nhận xử lý.** Chỉ lưu `lastId` sau khi kết quả trang đã được xuất/ghi bền vững; nếu không có thể mất dòng sau lỗi.
4. **Đầu ra có thể bị trùng khi retry.** Consumer hoặc sink cần idempotency, khóa duy nhất hoặc cơ chế tiếp tục an toàn.
5. **Mỗi DBMS có cú pháp phân trang riêng.** PostgreSQL/MySQL thường dùng `LIMIT`; SQL Server dùng `OFFSET ... FETCH` hoặc `TOP` trong những ngữ cảnh phù hợp. Không ghép trực tiếp giá trị phân trang từ input chưa kiểm soát vào SQL.

### So sánh cursor và keyset pagination

| Yêu cầu | Fetch theo cursor | Keyset pagination |
| --- | --- | --- |
| Xử lý một báo cáo trong một transaction/snapshot nếu DBMS hỗ trợ | Có thể thuận tiện | Khó giữ cùng snapshot nếu mỗi trang dùng transaction khác |
| Job rất lâu, có checkpoint/restart | Kém thuận tiện hơn | Thường phù hợp hơn |
| Consumer HTTP rất chậm | Connection/transaction có thể bị giữ lâu | Có thể tách job và nơi tải file |
| Kết quả có hàng triệu dòng | Có thể hiệu quả nếu driver stream thật | Có thể hiệu quả với index/khóa seek |
| Dữ liệu thay đổi trong lúc xuất | Tùy isolation/snapshot của transaction | Cần chính sách nhất quán giữa các trang |
| Kích thước mỗi trang hoặc fetch | `fetchSize` là hint của driver | `LIMIT`/`FETCH` thường giới hạn số dòng truy vấn |

Khi nghiệp vụ yêu cầu “toàn bộ dữ liệu tại đúng một thời điểm”, cần thiết kế snapshot/isolation phù hợp. Chỉ thêm `ORDER BY` hoặc sử dụng keyset chưa đủ bảo đảm tập kết quả nhất quán khi dữ liệu đang thay đổi.

## 9. SQL, index và kích thước dòng có ảnh hưởng trực tiếp

Stream tốt vẫn có thể chậm hoặc tiêu tốn RAM nếu câu SQL không phù hợp:

~~~sql
-- Tránh SELECT * nếu chỉ cần 3 cột.
SELECT id, amount, status
FROM orders
WHERE id >= ?
ORDER BY id;
~~~

Một số nguyên tắc:

- **Chỉ chọn cột cần dùng.** Tránh đưa BLOB/CLOB vào truy vấn xuất danh sách nếu sẽ không dùng đến.
- **Giới hạn phạm vi dữ liệu bằng điều kiện có tham số.** Ví dụ khoảng thời gian, tenant ID và trạng thái.
- **Có index hỗ trợ bộ lọc và thứ tự** trong phạm vi truy vấn lớn; kiểm tra kế hoạch thực thi (`EXPLAIN`) theo DBMS.
- **Không giả định stream giải quyết mọi vấn đề database.** Sorting, hash aggregation hoặc join lớn có thể tốn bộ nhớ/tệp tạm **trên server**, dù Java client chỉ nhận từng dòng.
- **Không gọi thêm một query cho từng dòng** nếu có thể gom dữ liệu bằng join/batch phù hợp; N+1 queries khiến mạng và DB chịu tải quá lớn.
- **Tránh giữ khóa trong lúc gọi dịch vụ ngoài.** Nếu mỗi dòng cần gọi HTTP lâu, cân nhắc tách việc đọc DB và xử lý ngoài transaction với queue/batch có giới hạn.

Một kết quả có triệu dòng và chỉ ba cột nhỏ dễ xử lý hơn rất nhiều so với kết quả có mười nghìn dòng chứa hàng trăm trường hoặc LOB cỡ hàng chục MB.

## 10. Vòng đời tài nguyên và xử lý lỗi

Streaming thường giữ tài nguyên lâu hơn truy vấn nhỏ, nên cần xác định rõ **ai sở hữu và khi nào đóng**:

~~~mermaid
flowchart TD
    C["Mở Connection"] --> P["Tạo PreparedStatement"]
    P --> R["executeQuery -> ResultSet"]
    R --> L["next -> xử lý / ghi ra output"]
    L -->|Còn dòng| L
    L -->|Hết / lỗi| X["Đóng ResultSet, Statement"]
    X --> T["Kết thúc transaction nếu có"]
    T --> Z["Đóng / trả Connection về pool"]
~~~

Nguyên tắc:

1. `ResultSet` chỉ được sử dụng khi statement và connection của nó còn hợp lệ.
2. Không trả `ResultSet` trực tiếp ra tầng UI hoặc một stream lazy mà tầng repository đã đóng connection; đó là lỗi vòng đời tài nguyên. Nếu API trả luồng dữ liệu, tầng gọi phải có hợp đồng đóng/cancel rõ ràng.
3. Đọc `InputStream`/`Reader` của LOB **trong khi ResultSet còn mở**; không lưu stream để đọc sau khi trả connection về pool.
4. Sử dụng `try-with-resources` để đóng `ResultSet`, `PreparedStatement` và `Connection` theo đúng phạm vi.
5. Nếu giao dịch đã tắt auto-commit, kết thúc bằng `commit` hoặc `rollback` có chủ đích trước khi trả connection; không trông đợi `close()` luôn rollback giống nhau trên mọi driver/pool.
6. Xử lý riêng `SQLException`, `IOException` và trường hợp client hủy đầu ra. Khi output ghi một phần rồi lỗi, file/HTTP response có thể đã chứa một phần kết quả; cần cơ chế xóa file tạm hoặc ghi vào file tạm rồi đổi tên sau khi thành công.
7. Log mã query, số dòng đã xuất, thời gian, kích thước byte và loại lỗi phù hợp; tránh log toàn bộ dữ liệu hoặc tham số nhạy cảm.

### Timeout và transaction dài

- `setQueryTimeout` có thể giới hạn thời gian thực thi SQL tùy driver, **không phải deadline chắc chắn cho toàn bộ quá trình xuất**.
- JDBC `Connection.setNetworkTimeout` có thể được hỗ trợ để giới hạn thời gian hoạt động mạng; cần executor và cấu hình phù hợp, không coi đây là giải pháp duy nhất.
- DBMS có thể có `statement_timeout`, `lock_timeout`, timeout cursor hoặc giới hạn transaction; chúng cần được cấu hình và kiểm thử ở môi trường thực.
- Transaction đọc quá dài có thể giữ snapshot phiên bản cũ, khiến công việc dọn phiên bản/MVCC hoặc pool bị ảnh hưởng. Không giữ nó mở chỉ vì đầu ra đang chờ một consumer chậm.
- Với kết quả rất lớn, nên có **deadline, cancel, monitoring và checkpoint**. Nếu không thể bảo đảm thời gian đọc ngắn, cân nhắc job phân trang thay vì cursor kéo dài.

## 11. Cách kiểm chứng ứng dụng không nạp toàn bộ vào RAM

Một phép thử với 100 dòng không thể chứng minh xử lý tốt dữ liệu lớn. Hãy tạo dataset thử tăng dần theo kích thước trên DBMS/driver mục tiêu và đo ít nhất:

| Phép đo | Điều cần xem |
| --- | --- |
| Peak heap Java | Có tăng gần tuyến tính với tổng số dòng không? |
| RSS/native memory | Driver có cấp phát ngoài Java heap hoặc buffer mạng lớn không? |
| Số dòng xử lý | Đếm đúng, không bỏ sót/trùng do phân trang |
| Thời gian xử lý và throughput | Có bị tăng mạnh do fetch quá nhỏ hoặc query không có index không? |
| Round trip DB | Fetch theo lô có giảm số lượt nhận dữ liệu như kỳ vọng không? |
| Connection/transaction duration | Có giữ connection quá lâu, gây cạn pool hoặc giữ snapshot không? |
| Hủy giữa chừng | Đã đóng ResultSet/stream/connection và cleanup file tạm chưa? |
| Một BLOB rất lớn | Có copy được với buffer cố định thay vì mảng byte theo kích thước tệp không? |
| Consumer chậm | Backpressure có chặn producer một cách có kiểm soát không? |

### Các trường hợp kiểm thử nên có

- Truy vấn **không có dòng**: header CSV có được ghi một lần, không lỗi `rs.next()` hay rò tài nguyên?
- Truy vấn **một dòng** và nhiều dòng: thứ tự theo khóa chính và số dòng trả về chính xác?
- Dữ liệu vài trăm nghìn đến hàng triệu dòng: peak memory có nằm trong giới hạn chấp nhận được?
- Mỗi dòng nhỏ nhưng có một cột văn bản rất lớn: code có vô tình gọi `getString` cho cả CLOB không?
- Một BLOB lớn hơn heap cho phép: streaming copy thành công nếu driver hỗ trợ; không dùng `getBytes`.
- `NULL` ở cột có thể thiếu: code phân biệt null với chuỗi rỗng và số 0?
- `SQLException` giữa vòng lặp: statement/result set/connection được đóng, transaction kết thúc?
- `IOException` từ writer sau N dòng: có dừng truy vấn, cleanup, xử lý file/response dang dở?
- Hai client tải đồng thời: pool có đủ connection, DB có bị giữ snapshot quá lâu?
- Keyset pagination khi có insert/update song song: chính sách snapshot hoặc xử lý trùng/bỏ sót có được tôn trọng?

**Thử cùng câu SQL ở nhiều fetch size và nhiều độ lớn dữ liệu**. Nếu bộ nhớ đỉnh vẫn tăng đều theo số dòng dù ứng dụng không giữ `List`, nghi ngờ driver đang materialize kết quả, query có một cột rất lớn hoặc nơi nhận đang gom dữ liệu.

### Bài tập tự luyện

1. Một phương thức dùng `while (rs.next())` nhưng gọi `rows.add(map(rs))` rồi trả `List`. Vì sao nó vẫn có thể hết RAM?
2. Vì sao `ps.setFetchSize(500)` không bảo đảm driver chỉ dùng bộ nhớ cho 500 dòng?
3. Nếu muốn xuất một BLOB 2 GB, vì sao `rs.getBytes("file_body")` là lựa chọn nguy hiểm? API nào phù hợp hơn?
4. Điều gì xảy ra nếu repository trả `InputStream` của `ResultSet` ra ngoài nhưng đã đóng connection bằng `try-with-resources`?
5. Khi một job đọc hàng chục triệu dòng và consumer rất chậm, vì sao keyset pagination có thể phù hợp hơn một cursor kéo dài?
6. Phân trang với `ORDER BY created_at` nhưng nhiều dòng trùng thời điểm có nguy cơ gì? Nên bổ sung điều gì?
7. Một file CSV bị ghi lỗi ở dòng thứ 100.000. Kết quả đầu ra đã phát hành có thể gặp vấn đề gì và nên xử lý theo cơ chế nào?

**Gợi ý:** (1) `List` vẫn tăng cùng số dòng; (2) fetch size là hint, driver có thể đệm toàn bộ hoặc cần cấu hình cursor; (3) `getBytes` tạo mảng byte khổng lồ, dùng `getBinaryStream` và buffer cố định; (4) stream có thể không đọc tiếp được vì tài nguyên JDBC đã đóng; (5) pagination cho phép kết thúc transaction từng trang và checkpoint; (6) cần thêm khóa duy nhất như `id` làm tie-breaker; (7) dữ liệu xuất có thể dang dở, nên dùng file tạm/đánh dấu chưa hoàn tất rồi chỉ công bố khi thành công.

---

**Nguyên tắc ghi nhớ:** Với JDBC, đọc dữ liệu lớn hiệu quả cần **xử lý từng phần ở tất cả các tầng**: câu SQL chỉ lấy dữ liệu cần thiết, driver fetch theo lô/cursor thực sự, Java không gom toàn bộ kết quả, LOB được đọc qua stream và output có backpressure hoặc buffer giới hạn. `setFetchSize` cùng `rs.next()` là điểm khởi đầu quan trọng; hành vi streaming thực tế phải được kiểm chứng bằng **driver, DBMS và dữ liệu lớn trên môi trường thử nghiệm**.
