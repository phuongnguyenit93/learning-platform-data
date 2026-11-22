# Phân biệt byte array, luồng nhị phân và BLOB trong JDBC

Trong JDBC (*Java Database Connectivity*, API Java để truy cập cơ sở dữ liệu quan hệ), ứng dụng thường phải lưu hoặc đọc dữ liệu nhị phân: ảnh đại diện, tệp PDF, chữ ký số, âm thanh hoặc tệp đính kèm. Một tệp vài kilobyte và một tệp nhiều gigabyte đều là dãy byte, nhưng cách giữ và truyền chúng trong bộ nhớ cần khác nhau.

Chương **Dữ liệu lớn** tập trung vào ba khái niệm hay bị nhầm với nhau: **`byte[]`**, **luồng nhị phân (`InputStream`/`OutputStream`)** và **BLOB**. Hiểu đúng nơi dữ liệu tồn tại, vòng đời tài nguyên và API JDBC phù hợp sẽ giúp tránh lỗi thiếu bộ nhớ, rò rỉ kết nối và tệp bị cắt ngắn.

## 1. Ba khái niệm thuộc ba lớp khác nhau

### `byte[]`: dữ liệu đang nằm trong bộ nhớ Java

`byte[]` là mảng byte trong heap của JVM. Mỗi phần tử được truy cập trực tiếp theo chỉ số. Mảng phù hợp khi toàn bộ dữ liệu đã nhỏ và cần thao tác nhiều lần: kiểm tra header, tính hash cho payload nhỏ, mã hóa hoặc gửi một ảnh thu nhỏ.

```java
byte[] content = new byte[] {0x01, 0x02, 0x03};
int length = content.length;
byte first = content[0];
```

Khi gọi `Files.readAllBytes(path)` hoặc `ResultSet.getBytes("payload")`, chương trình có thể tạo một mảng chứa **toàn bộ** dữ liệu. Bộ nhớ cần dùng tăng theo kích thước tệp; thêm các bản sao từ driver JDBC, tầng mạng hoặc mã ứng dụng có thể làm mức sử dụng heap tăng cao hơn. Mảng Java được đánh chỉ số bằng `int`, vì vậy không nên coi một `byte[]` là cấu trúc thích hợp để biểu diễn các payload cực lớn.

### Luồng nhị phân: đọc hoặc ghi tuần tự

`InputStream` cung cấp các byte để đọc dần; `OutputStream` nhận các byte để ghi dần. Đây là **giao diện truyền dữ liệu**, không phải kiểu cột SQL và cũng không đảm bảo nguồn nằm trên đĩa: một luồng có thể đọc từ file, socket, bộ nhớ hoặc dữ liệu do driver cung cấp.

```java
try (InputStream input = Files.newInputStream(sourcePath);
     OutputStream output = Files.newOutputStream(targetPath)) {
    input.transferTo(output); // Java 9+: chuyển dần các byte
}
```

Trong cách sử dụng thông thường, chương trình chỉ cần bộ đệm nhỏ thay vì một mảng bằng toàn bộ kích thước dữ liệu. Đổi lại, phải quản lý thời gian mở luồng, lỗi I/O và việc đóng tài nguyên. `InputStream` cũng có thể không hỗ trợ đọc lại hoặc tua về đầu; không thể giả định `mark/reset` hoạt động trên mọi luồng.

### BLOB: giá trị nhị phân lớn trong cơ sở dữ liệu

**BLOB** (*Binary Large Object*) mô tả dữ liệu nhị phân lớn được lưu ở phía cơ sở dữ liệu, thường dưới dạng một cột hoặc cơ chế large object của hệ quản trị. **`java.sql.Blob`** lại là giao diện JDBC để thao tác với giá trị BLOB: tùy driver, đối tượng này có thể hoạt động như một *locator* tham chiếu đến dữ liệu ở máy chủ hoặc một dạng biểu diễn khác do driver quản lý.

Vì vậy cần phân biệt hai cách dùng từ “BLOB”:

- **Cột BLOB/kiểu tương đương:** mô tả cách database lưu giá trị.
- **Đối tượng `Blob` trong Java:** đại diện JDBC cho giá trị đó; có `length()`, `getBinaryStream()`, `getBytes(...)` và `free()`.

Một cột nhị phân lớn không bắt buộc phải được đọc bằng `getBlob()`. Khi driver và kiểu cột hỗ trợ, ứng dụng cũng có thể đọc qua `getBytes()` hoặc `getBinaryStream()`.

| Góc nhìn | `byte[]` | `InputStream` / `OutputStream` | SQL BLOB và `java.sql.Blob` |
|---|---|---|---|
| Bản chất | Mảng trong heap Java | Luồng đọc/ghi tuần tự | Giá trị trong database và giao diện JDBC truy cập nó |
| Dung lượng ở phía ứng dụng | Thường tỷ lệ với toàn bộ payload | Có thể chỉ cần bộ đệm nhỏ | Phụ thuộc driver và cách lấy dữ liệu; locator có thể không chứa toàn bộ byte |
| Truy cập | Ngẫu nhiên theo chỉ số | Thường tuần tự | `Blob` hỗ trợ lấy đoạn hoặc mở stream, tùy khả năng driver |
| Vòng đời | Do GC quản lý | Phải đóng luồng | Có thể phụ thuộc kết nối/transaction; gọi `free()` khi dùng xong |
| Phù hợp | Payload đã biết là nhỏ | Truyền tải tệp lớn | Lưu giá trị nhị phân lớn, cần API LOB hoặc khả năng của database |

Không có quy tắc “dữ liệu BLOB phải đọc qua `Blob`”. Việc chọn API phụ thuộc **kích thước**, **mục đích xử lý** và **khả năng thực tế của driver**.

## 2. Đối chiếu API JDBC

| Nhu cầu | Ghi vào `PreparedStatement` | Đọc từ `ResultSet` | Đặc điểm |
|---|---|---|---|
| Ghi/đọc mảng byte nhỏ | `setBytes(index, byte[])` | `getBytes(column)` | Tiện, nhưng thường giữ toàn bộ nội dung trong heap |
| Đưa luồng vào cột nhị phân | `setBinaryStream(index, input, length)` | `getBinaryStream(column)` | Truyền theo luồng; mức buffering thực tế phụ thuộc driver |
| Làm việc với đối tượng LOB | `setBlob(index, blob)` hoặc các overload dùng `InputStream` | `getBlob(column)` | Dùng API `Blob`; cần hiểu vòng đời tài nguyên và khả năng hỗ trợ của driver |
| Ghi một giá trị SQL `NULL` | `setNull(index, Types.BLOB)` hoặc kiểu SQL phù hợp | `getBytes()` / `getBinaryStream()` có thể trả `null` | Phải phân biệt `NULL` với payload có độ dài bằng 0 |

Với thao tác tải tệp thông thường, lựa chọn dễ hiểu là:

```text
Tệp trên đĩa  → InputStream → PreparedStatement.setBinaryStream(...) → cột nhị phân
Cột nhị phân → ResultSet.getBinaryStream(...) → OutputStream            → tệp trên đĩa
```

Đường đi `byte[]` ngắn hơn nhưng đưa toàn bộ payload qua heap:

```text
byte[] → PreparedStatement.setBytes(...) → database
byte[] ← ResultSet.getBytes(...)         ← database
```

Lưu ý sự khác nhau giữa các hệ quản trị: PostgreSQL thường dùng `BYTEA` cho dữ liệu nhị phân trong hàng và còn có cơ chế large object riêng; MySQL có `BLOB`, `MEDIUMBLOB`, `LONGBLOB` với giới hạn kích thước khác nhau; Oracle có `BLOB`; SQL Server thường dùng `VARBINARY(MAX)`. Tên kiểu SQL và một số phép toán LOB không hoàn toàn tương thích. Đặc biệt, `getBlob()` không nhất thiết hoạt động trên **mọi** kiểu cột nhị phân của **mọi** driver.

## 3. Ví dụ lưu tài liệu bằng JDBC

Giả sử có bảng minh họa sau; hãy thay kiểu cột `BLOB` bằng kiểu có dung lượng phù hợp với hệ quản trị đang sử dụng:

```sql
CREATE TABLE documents (
    id         BIGINT PRIMARY KEY,
    file_name  VARCHAR(255) NOT NULL,
    payload    BLOB NOT NULL
);
```

Ứng dụng có `DataSource` được cấu hình sẵn. Các ví dụ tiếp theo dùng Java 17+ và giả định driver hỗ trợ `setBinaryStream`, `getBinaryStream` trên kiểu cột đã chọn. Chúng không tự cấu hình JDBC driver, connection pool hoặc xác thực quyền truy cập tệp; các phần đó thuộc kiến trúc ứng dụng.

### 3.1. Dữ liệu nhỏ: `setBytes()` và `getBytes()`

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.Optional;
import javax.sql.DataSource;

public final class SmallDocumentDao {
    private final DataSource dataSource;

    public SmallDocumentDao(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public void insert(long id, String fileName, byte[] data)
            throws SQLException {
        String sql = "INSERT INTO documents (id, file_name, payload) VALUES (?, ?, ?)";
        try (Connection connection = dataSource.getConnection();
             PreparedStatement statement = connection.prepareStatement(sql)) {
            statement.setLong(1, id);
            statement.setString(2, fileName);
            statement.setBytes(3, data);
            if (statement.executeUpdate() != 1) {
                throw new SQLException("Không chèn được đúng một bản ghi");
            }
        }
    }

    public Optional<byte[]> findPayload(long id) throws SQLException {
        String sql = "SELECT payload FROM documents WHERE id = ?";
        try (Connection connection = dataSource.getConnection();
             PreparedStatement statement = connection.prepareStatement(sql)) {
            statement.setLong(1, id);
            try (ResultSet result = statement.executeQuery()) {
                if (!result.next()) {
                    return Optional.empty();
                }
                // Chỉ dùng khi đã biết chắc payload đủ nhỏ để chứa trong heap.
                return Optional.of(result.getBytes("payload"));
            }
        }
    }
}
```

Ở bảng minh họa, `payload` là `NOT NULL` nên có thể dùng `Optional.of(...)` sau khi tìm thấy hàng. Nếu cột cho phép `NULL`, `getBytes()` có thể trả `null`, cần thiết kế kết quả trả về để phân biệt “không có bản ghi”, “giá trị SQL NULL” và “dãy byte rỗng”.

Ví dụ trên cố ý dùng `getBytes()` để thấy sự thuận tiện của mảng byte. **Không dùng nó để đọc file lớn không kiểm soát kích thước**: giới hạn HTTP upload ở phía API chưa đủ để đảm bảo mọi hàng cũ trong database đều nhỏ. Nếu cần đọc các payload lớn, hãy dùng cách ở phần tiếp theo.

### 3.2. Dữ liệu lớn: `setBinaryStream()` và `getBinaryStream()`

```java
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import javax.sql.DataSource;

public final class StreamingDocumentDao {
    private final DataSource dataSource;

    public StreamingDocumentDao(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public void upload(long id, String fileName, Path source)
            throws SQLException, IOException {
        long length = Files.size(source);
        String sql = "INSERT INTO documents (id, file_name, payload) VALUES (?, ?, ?)";

        try (InputStream input = Files.newInputStream(source);
             Connection connection = dataSource.getConnection();
             PreparedStatement statement = connection.prepareStatement(sql)) {
            statement.setLong(1, id);
            statement.setString(2, fileName);
            statement.setBinaryStream(3, input, length);

            // Giữ input mở cho đến khi driver thực thi xong INSERT.
            if (statement.executeUpdate() != 1) {
                throw new SQLException("Không chèn được đúng một bản ghi");
            }
        }
    }

    public void download(long id, Path destination)
            throws SQLException, IOException {
        String sql = "SELECT payload FROM documents WHERE id = ?";

        try (Connection connection = dataSource.getConnection();
             PreparedStatement statement = connection.prepareStatement(sql)) {
            statement.setLong(1, id);
            try (ResultSet result = statement.executeQuery()) {
                if (!result.next()) {
                    throw new IllegalArgumentException("Không tìm thấy tài liệu: " + id);
                }

                InputStream source = result.getBinaryStream("payload");
                if (source == null) {
                    throw new SQLException("payload là SQL NULL");
                }

                // Đọc khi ResultSet và Connection vẫn đang mở.
                try (InputStream input = source;
                     OutputStream output = Files.newOutputStream(destination)) {
                    input.transferTo(output);
                }
            }
        }
    }
}
```

Ở `upload`, tham số `length` dùng kiểu `long`, lấy từ kích thước tệp. Nên đảm bảo file nguồn không bị thay đổi trong lúc truyền, vì nội dung đọc và độ dài đã khai báo có thể không còn khớp. JDBC cũng cung cấp overload `setBinaryStream(index, input)` không truyền độ dài; mức hỗ trợ và cách driver truyền tải khác nhau, vì vậy hãy thử nghiệm với hệ quản trị đích.

Ở `download`, chương trình **tiêu thụ toàn bộ stream trước khi đóng `ResultSet` và `Connection`**. Đây là điểm rất quan trọng: không trả `InputStream` trực tiếp ra ngoài phương thức trong khi `try-with-resources` đã đóng connection. Một số driver gắn stream với hàng hiện tại hoặc transaction, nên gọi `result.next()` hoặc getter khác khi chưa đọc hết stream cũng có thể khiến luồng bị đóng hoặc mất tính hợp lệ. Nếu cần thêm metadata, nên đọc nó trước khi mở stream.

`Files.newOutputStream(destination)` theo mặc định có thể tạo hoặc ghi đè file đích. Nếu muốn tránh để lại file tải dở sau lỗi mạng/database, ứng dụng sản xuất nên ghi vào tệp tạm trên cùng filesystem, xác minh dữ liệu rồi chuyển tệp tạm sang tên đích; xóa tệp tạm nếu thất bại. Việc chọn nơi lưu tệp và xử lý tên tệp đến từ người dùng phải được kiểm tra ở lớp ứng dụng.

## 4. Khi nào cần dùng trực tiếp `java.sql.Blob`?

`Blob` hữu ích khi cần API LOB chuyên biệt, chẳng hạn truy vấn độ dài hoặc truy cập một đoạn giá trị mà driver hỗ trợ. Phương thức `getBytes(long pos, int length)` của `Blob` dùng vị trí bắt đầu **từ 1**, khác với chỉ số mảng Java bắt đầu từ 0. Tuy vậy, `getBytes(...)` vẫn tạo mảng byte cho đoạn đã yêu cầu; gọi nó với độ dài rất lớn vẫn có nguy cơ dùng quá nhiều heap.

Ví dụ minh họa dưới đây đặt trong phạm vi một `ResultSet` đã định vị ở hàng cần đọc:

```java
import java.sql.Blob;

Blob blob = result.getBlob("payload");
if (blob != null) {
    try {
        long size = blob.length();
        System.out.println("Dung lượng BLOB (byte): " + size);

        try (InputStream input = blob.getBinaryStream();
             OutputStream output = Files.newOutputStream(destination)) {
            input.transferTo(output);
        }
    } finally {
        blob.free(); // Giải phóng tài nguyên do Blob/driver nắm giữ.
    }
}
```

Đoạn này giả định các biến `result` và `destination` đã tồn tại, đồng thời các lớp `InputStream`, `OutputStream`, `Files`, `Path` đã được import ở nơi sử dụng. Nó không phải phương thức độc lập. Một số driver sử dụng locator gắn với transaction; vì thế nên đọc và giải phóng BLOB **trước khi đóng transaction/kết nối**, trừ khi tài liệu driver bảo đảm khác.

`Connection.createBlob()` cho phép yêu cầu driver tạo đối tượng `Blob`, sau đó ghi dữ liệu vào qua `setBinaryStream(...)` hoặc `setBytes(...)` khi hỗ trợ. Đó không phải bước bắt buộc khi upload: với nhu cầu truyền từ file lên database, `PreparedStatement.setBinaryStream(...)` thường rõ ràng và ít phải quản lý tài nguyên hơn. Khi ứng dụng tự tạo một `Blob`, vẫn phải gọi `free()` sau khi dùng xong; không giữ đối tượng đó làm cache lâu dài.

Với PostgreSQL, chẳng hạn, cột `BYTEA` thường thích hợp với `setBytes()`/`getBytes()` hoặc các API stream được driver hỗ trợ; không suy luận rằng `getBlob()` luôn dùng được với `BYTEA`. Các thao tác LOB đặc thù cần kiểm tra tài liệu và thử nghiệm trên driver thật.

## 5. “Stream” không đồng nghĩa với “không tốn bộ nhớ”

Sử dụng `InputStream`/`OutputStream` cho phép ứng dụng xử lý tuần tự, nhưng **không tự bảo đảm driver JDBC đọc và ghi theo các chunk nhỏ trên đường truyền hoặc phía database**. Driver có thể đệm dữ liệu để biết trước độ dài, thực hiện chuyển đổi kiểu, hoặc chịu giới hạn của giao thức máy chủ. Một số cơ sở dữ liệu cũng giữ thêm bản sao nội bộ khi thao tác LOB.

Cần phân biệt ba nguồn tiêu thụ tài nguyên:

| Nguồn | Điều xảy ra | Cách kiểm soát |
|---|---|---|
| Heap ứng dụng | Mã Java tạo `byte[]` bằng toàn bộ file hoặc sao chép dữ liệu | Chọn API stream, tránh `readAllBytes()`/`getBytes()` cho payload lớn |
| Bộ nhớ driver/máy chủ | Driver hoặc database đệm hoặc chuyển đổi nội dung | Kiểm tra tài liệu driver, thử nghiệm với file lớn và đo heap/network |
| Kết nối và transaction | Stream còn mở có thể giữ `ResultSet`, connection, transaction và tài nguyên LOB | Đóng tài nguyên nhanh, đặt timeout và giới hạn số lượt tải đồng thời |

`Statement.setFetchSize(n)` chỉ là **gợi ý về số hàng** cần lấy mỗi đợt của một truy vấn. Nó không tự biến một cột BLOB lớn thành stream và không bảo đảm tài nguyên sử dụng theo đúng `n` hàng; một số driver yêu cầu cấu hình cursor hoặc transaction riêng để phát huy tác dụng. Tương tự, tải lên theo stream vẫn cần xem giới hạn kích thước packet, timeout và cấu hình của hệ quản trị.

Nếu xử lý một tập dữ liệu gồm nhiều hàng có BLOB, hãy đọc từng hàng và giải phóng stream của hàng đó trước khi chuyển sang hàng kế tiếp. Tránh gom hàng trăm giá trị `byte[]` vào `List` rồi mới ghi tệp: chi phí bộ nhớ sẽ bằng **tổng** dung lượng các payload đang giữ.

## 6. Phân biệt dữ liệu nhị phân với văn bản lớn

Ảnh, file nén, PDF hay dữ liệu mã hóa là **nhị phân**: các byte phải được giữ nguyên, thường qua `BLOB` hoặc kiểu cột nhị phân tương đương. Văn bản lớn như XML hoặc báo cáo nhiều ký tự có thể thích hợp với **CLOB** (*Character Large Object*) hoặc kiểu text của hệ quản trị.

| Loại nội dung | API theo byte | API theo ký tự |
|---|---|---|
| Ảnh, PDF, ZIP | `setBinaryStream()` / `getBinaryStream()` | Không dùng để diễn giải nội dung như ký tự |
| Văn bản Unicode lớn | Có thể lưu dưới dạng byte nếu giao thức yêu cầu | `setCharacterStream()` / `getCharacterStream()`, hoặc API `Clob` |

Sự khác nhau nằm ở **đơn vị xử lý**: luồng nhị phân làm việc với byte; `Reader`/`Writer` làm việc với ký tự. Khi đọc hoặc ghi văn bản từ file, xác định bộ mã như UTF-8 để chuyển đổi giữa byte và ký tự một cách nhất quán. Không tự ý dùng `new String(bytes)` không chỉ rõ charset để biến một file nhị phân thành văn bản.

## 7. Lựa chọn giải pháp theo kích thước và nghiệp vụ

Không có ngưỡng dung lượng cố định được JDBC quy định để chuyển từ `byte[]` sang stream. Ngưỡng phụ thuộc heap, số request đồng thời, chính sách giới hạn upload và cách driver xử lý dữ liệu.

| Tình huống | Cách chọn hợp lý | Lý do |
|---|---|---|
| Ảnh thumbnail vài KB | `byte[]`, `setBytes()`, `getBytes()` | Gọn, dễ kiểm tra, chi phí heap nhỏ |
| File PDF vài chục MB | `setBinaryStream()` và `getBinaryStream()` | Không bắt buộc đọc toàn bộ file vào mảng byte |
| File rất lớn hoặc nhiều tải xuống đồng thời | Stream và hạn mức kích thước, thời gian, kết nối; cân nhắc object storage theo kiến trúc hệ thống | Giảm áp lực heap, tránh giữ transaction/kết nối JDBC quá lâu |
| Cần kiểm tra kích thước hoặc API LOB đặc thù | `Blob.length()`, `Blob.getBinaryStream()` nếu driver hỗ trợ | Truy cập metadata/đối tượng LOB có kiểm soát tài nguyên |
| Văn bản lớn | CLOB/text và `Reader`/`Writer` | Giữ đúng ngữ nghĩa ký tự |

Lưu BLOB trong database có ưu điểm là tận dụng quyền truy cập, transaction và backup của database; đổi lại, tải nhiều tệp lớn có thể làm tăng dung lượng lưu trữ, thời gian sao lưu và số kết nối bận. Trong hệ thống có tần suất truy cập file cao, lưu file trong object storage và chỉ giữ metadata, đường dẫn hoặc object key trong database cũng là một lựa chọn kiến trúc cần đánh giá. API JDBC vẫn hữu ích để quản lý metadata và các ràng buộc nghiệp vụ.

## 8. Lỗi thường gặp và cách kiểm tra

| Lỗi | Vì sao nguy hiểm | Cách phòng tránh |
|---|---|---|
| `Files.readAllBytes()` cho file bất kỳ | Payload quá lớn có thể gây `OutOfMemoryError` | Giới hạn kích thước và dùng stream |
| `getBytes()` cho cột LOB không biết dung lượng | Driver có thể cấp phát cả giá trị thành một mảng | Dùng `getBinaryStream()`/`Blob.getBinaryStream()` |
| Trả `InputStream` sau khi đóng `ResultSet` | Luồng có thể không còn hợp lệ | Tiêu thụ stream trong vòng đời connection/result set |
| Đóng input trước `executeUpdate()` | Driver chưa kịp đọc hết nội dung | Giữ input mở đến khi lệnh kết thúc |
| Không gọi `Blob.free()` | Locator hoặc tài nguyên driver có thể bị giữ | Dùng `try/finally` để `free()` |
| Coi SQL `NULL` là file rỗng | Sai ngữ nghĩa dữ liệu | Kiểm tra `null` riêng; file rỗng có 0 byte |
| Dùng `Blob.getBytes(1, (int) blob.length())` cho file rất lớn | Ép `long` thành `int` có thể tràn và vẫn tạo mảng lớn | Đọc theo stream hoặc từng đoạn nhỏ có giới hạn |
| Tin rằng stream luôn được driver truyền từng chunk | Có thể đệm ngầm | Benchmark trên driver và database đích |
| Ghi thẳng đích rồi lỗi giữa chừng | Tệp đích có thể bị ghi dở hoặc bị ghi đè | Ghi tệp tạm, xác minh rồi chuyển sang đích |

Để kiểm tra phần triển khai, tạo ít nhất ba payload: một file rỗng (0 byte), một file nhỏ vài kilobyte và một file lớn hơn đáng kể so với bộ nhớ đệm thông thường. Sau khi upload/download, so sánh kích thước và **SHA-256** của file nguồn với file tải về; đồng thời thử tình huống ID không tồn tại và lỗi giữa lúc truyền. Theo dõi heap, số kết nối đang mở và thời gian xử lý để phát hiện driver buffering hoặc lỗi đóng tài nguyên. Các kiểm thử phải chạy với **driver và database mục tiêu**, vì cùng một lời gọi JDBC không luôn có hành vi truyền dữ liệu giống nhau ở mọi hệ quản trị.

## 9. Câu hỏi tự luyện

1. Một file PDF 200 MB cần lưu vào database. Vì sao `Files.readAllBytes()` rồi `setBytes()` có thể rủi ro khi có hàng chục lượt tải đồng thời? Cặp API nào phù hợp hơn?
2. Khi `getBinaryStream()` trả về `InputStream`, liệu có thể đóng `ResultSet` rồi mới đọc luồng đó ở tầng HTTP controller không? Bạn sẽ tổ chức vòng đời connection ra sao?
3. Vì sao `java.sql.Blob` không nhất thiết là một mảng chứa toàn bộ nội dung? Khi nào phải gọi `free()`?
4. `BLOB NULL` và BLOB có độ dài 0 có giống nhau không? Điều gì xảy ra nếu dùng `getBytes()` trên mỗi trường hợp?
5. Một chương trình đã dùng `setBinaryStream()` nhưng heap vẫn tăng mạnh. Bạn sẽ kiểm tra những tầng nào trước khi kết luận lỗi đến từ ứng dụng?

**Điểm cốt lõi:** `byte[]` là **nội dung đã nằm trong heap**, `InputStream`/`OutputStream` là **cách truyền dữ liệu tuần tự**, còn BLOB là **giá trị nhị phân trong database** và `java.sql.Blob` là **giao diện JDBC để làm việc với giá trị ấy**. Với tệp lớn, ưu tiên xử lý theo luồng, giữ tài nguyên JDBC mở đúng thời điểm và xác minh hành vi thực tế của driver.
