# Vai trò của WebRowSet trong biểu diễn XML

Khi xây dựng ứng dụng **JDBC**, chúng ta thường đọc dữ liệu quan hệ qua `Connection`, `PreparedStatement` và `ResultSet`. Nhưng nếu cần **giữ một tập dữ liệu sau khi đã đóng kết nối**, trao đổi tập dữ liệu đó với một thành phần khác hoặc lưu nó thành một tài liệu XML để mở lại, `ResultSet` thông thường không phù hợp: nó gắn với statement và connection đang hoạt động.

**`WebRowSet`** giải quyết một phần nhu cầu này. Đây là giao diện JDBC RowSet cho phép biểu diễn dữ liệu dạng bảng, metadata và một số thuộc tính/trạng thái RowSet bằng **XML có cấu trúc được quy định theo WebRowSet**. `WebRowSet` kế thừa `CachedRowSet` nên có thể hoạt động ở chế độ **ngắt kết nối** (*disconnected*): lấy dữ liệu từ nguồn, lưu bản sao trong bộ nhớ, đóng connection, sau đó duyệt dữ liệu hoặc ghi/đọc XML.

Tuy nhiên, phải phân biệt rõ:

- **Ngoại tuyến không có nghĩa là không dùng bộ nhớ.** `WebRowSet` là một RowSet lưu dữ liệu đã được cache, không phải cơ chế đọc hàng triệu dòng trực tiếp từ XML với bộ nhớ cố định.
- **XML không tự động đồng bộ database.** Gọi `writeXml` chỉ xuất biểu diễn XML; `readXml` chỉ nạp lại RowSet. Muốn ghi thay đổi ngược về database còn cần một cơ chế đồng bộ riêng và hợp đồng cập nhật phù hợp.
- **XML không mặc nhiên an toàn để công khai.** Tài liệu có thể chứa toàn bộ giá trị cột, metadata và thuộc tính RowSet; cần kiểm soát dữ liệu nhạy cảm, quyền truy cập và nguồn XML đầu vào.

Bài học nằm trong chương **RowSet ngoại tuyến** của module **JDBC** và tập trung vào việc hiểu `WebRowSet` là gì, nó được dùng thế nào và ranh giới trách nhiệm so với `ResultSet` và các loại RowSet khác.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích mối quan hệ giữa `ResultSet`, `CachedRowSet` và `WebRowSet`.
2. Tạo `WebRowSet` qua `RowSetProvider` mà không phụ thuộc lớp nội bộ của JDK.
3. Dùng `populate(ResultSet)` để lấy bản sao dữ liệu từ một truy vấn `PreparedStatement`.
4. Dùng `writeXml(OutputStream)` hoặc `writeXml(Writer)` để xuất RowSet thành XML.
5. Dùng `readXml(InputStream)` hoặc `readXml(Reader)` để phục hồi RowSet từ XML.
6. Hiểu phần **properties**, **metadata**, **data** và dấu trạng thái dòng trong biểu diễn XML.
7. Đọc dữ liệu đã phục hồi mà không cần một JDBC connection đang mở.
8. Phân biệt XML round-trip với giao dịch/đồng bộ ngược database.
9. Chỉ ra các rủi ro về dữ liệu nhạy cảm, XML không tin cậy, bộ nhớ và sự thay đổi schema.

## 2. WebRowSet nằm ở đâu trong hệ sinh thái JDBC?

API JDBC có hai mô hình dữ liệu liên quan nhưng không đồng nhất:

- `ResultSet`: kết quả của việc thực thi một statement; vòng đời và khả năng cuộn/sửa dữ liệu phụ thuộc statement, connection và driver.
- `RowSet`: họ giao diện mở rộng khả năng sử dụng tập dữ liệu dạng bảng. Một số triển khai được kết nối liên tục, một số khác lưu bản sao trong bộ nhớ để làm việc ngoại tuyến.

Các giao diện trong họ RowSet đáng chú ý:

| Giao diện | Vai trò chính | Tính chất |
| --- | --- | --- |
| `javax.sql.rowset.JdbcRowSet` | Bọc trải nghiệm `ResultSet` với các tiện ích RowSet | Kết nối với nguồn dữ liệu trong quá trình làm việc |
| `javax.sql.rowset.CachedRowSet` | Cache một tập dòng để sử dụng sau khi ngắt kết nối | Disconnected; có thể sửa dữ liệu cache và đồng bộ nếu cấu hình phù hợp |
| `javax.sql.rowset.WebRowSet` | Bổ sung khả năng đọc/ghi biểu diễn XML cho CachedRowSet | Disconnected và hỗ trợ XML |
| `javax.sql.rowset.FilteredRowSet` | Cho phép áp dụng điều kiện lọc đối với RowSet | Gắn với CachedRowSet theo API kế thừa |
| `javax.sql.rowset.JoinRowSet` | Kết hợp dữ liệu từ các RowSet theo khả năng được hỗ trợ | Thích hợp một số trường hợp tổng hợp phía ứng dụng |

Quan hệ kế thừa quan trọng:

~~~text
ResultSet
   ^
   |
  RowSet
   ^
   |
CachedRowSet
   ^
   |
WebRowSet
~~~

`WebRowSet` là **giao diện**, không phải một lớp Java để gọi trực tiếp `new WebRowSet()`. Sử dụng `RowSetProvider` và `RowSetFactory` để yêu cầu một triển khai:

~~~java
import javax.sql.rowset.RowSetProvider;
import javax.sql.rowset.WebRowSet;

try (WebRowSet web = RowSetProvider.newFactory().createWebRowSet()) {
    // Sử dụng web như một tập dữ liệu có thể ghi/đọc XML.
}
~~~

`RowSetProvider` có sẵn trong Java SE. Khi dùng Java Platform Module System (JPMS), module ứng dụng cần khai báo phụ thuộc phù hợp, chẳng hạn:

~~~java
module example.jdbc {
    requires java.sql;
    requires java.sql.rowset;
}
~~~

Không nên tạo trực tiếp lớp nội bộ như `com.sun.rowset.WebRowSetImpl` trong code ứng dụng. API `javax.sql.rowset` và `RowSetProvider` là ranh giới được Java hỗ trợ; đường dẫn lớp nội bộ có thể thay đổi hoặc bị giới hạn bởi cơ chế module.

## 3. Kiến trúc ngoại tuyến: dữ liệu di chuyển như thế nào?

~~~mermaid
flowchart TD
    A["Database"] --> B["Connection + PreparedStatement"]
    B --> C["ResultSet đang kết nối"]
    C -->|"WebRowSet.populate(rs)"| D["WebRowSet: dữ liệu cache"]
    D --> E["Đóng ResultSet / Statement / Connection"]
    D -->|"writeXml(...)"| F["Tài liệu XML"]
    F -->|"readXml(...)"| G["WebRowSet mới: dữ liệu cache"]
    G --> H["Duyệt bằng next/getXxx không cần DB"]
    G -.->|"Đồng bộ riêng, nếu có cấu hình"| I["Database"]
~~~

Có bốn giai đoạn khác nhau:

1. **Truy vấn:** Database trả các dòng qua `ResultSet`.
2. **Tách khỏi kết nối:** `populate(rs)` copy dữ liệu cần thiết cùng thông tin mô tả vào `WebRowSet`. Sau khi nạp xong, có thể đóng connection.
3. **Biểu diễn XML:** `writeXml` chuyển trạng thái RowSet sang một tài liệu XML theo định dạng do API định nghĩa.
4. **Phục hồi:** Một `WebRowSet` mới dùng `readXml` để tái tạo dữ liệu/metadata và được duyệt qua các getter JDBC quen thuộc.

Điều này khác với việc xuất dữ liệu bằng câu SQL `SELECT ... FOR XML` hay một thư viện tự tạo các thẻ XML. `WebRowSet` có **định dạng XML riêng**, không phải bất kỳ XML tự do nào cũng có thể nạp bằng `readXml`.

## 4. Bộ API chính cần nhớ

| Thành phần | Phương thức | Chức năng |
| --- | --- | --- |
| Tạo RowSet | `RowSetProvider.newFactory().createWebRowSet()` | Tạo đối tượng qua provider chuẩn |
| Nạp dữ liệu | `populate(ResultSet)` | Copy các dòng và metadata từ `ResultSet` vào RowSet |
| Xuất XML | `writeXml(OutputStream)` | Ghi biểu diễn XML ra luồng byte |
| Xuất XML | `writeXml(Writer)` | Ghi biểu diễn XML ra luồng ký tự |
| Nạp XML | `readXml(InputStream)` | Khôi phục RowSet từ tài liệu XML |
| Nạp XML | `readXml(Reader)` | Khôi phục từ luồng ký tự |
| Duyệt dữ liệu | `beforeFirst()`, `next()`, `getXxx(...)` | Truy cập dữ liệu đã cache |
| Metadata | `getMetaData()` | Lấy tên, kiểu và đặc tính các cột |
| Đọc trạng thái hàng | `rowInserted()`, `rowUpdated()`, `rowDeleted()` | Kiểm tra một số dấu trạng thái của dòng khi thích hợp |
| Đồng bộ DB | `acceptChanges(...)` | Yêu cầu cơ chế `SyncProvider` ghi thay đổi về nguồn dữ liệu; **khác với XML** |

`WebRowSet` còn có overload `writeXml(ResultSet, OutputStream)` và `writeXml(ResultSet, Writer)`. Các overload này giúp xuất dựa trên một `ResultSet`. Nhưng **không nên suy rằng chúng xử lý theo streaming với bộ nhớ cố định**: `WebRowSet` vẫn mang đặc tính cache của `CachedRowSet`. Nếu cần xuất hàng triệu dòng bằng bộ nhớ bị chặn, dùng vòng lặp `ResultSet.next()` và một XML writer streaming được thiết kế riêng.

## 5. Ví dụ đầy đủ: đọc dữ liệu JDBC rồi lưu XML

Giả sử có bảng danh mục tồn kho (cú pháp SQL mang tính minh họa, cần điều chỉnh cho DBMS đích):

~~~sql
CREATE TABLE inventory_items (
    item_id BIGINT PRIMARY KEY,
    item_name VARCHAR(100) NOT NULL,
    available_units INTEGER
);
~~~

Dữ liệu mẫu:

~~~sql
INSERT INTO inventory_items (item_id, item_name, available_units)
VALUES
    (1001, 'Keyboard', 12),
    (1002, 'Mouse', NULL),
    (1003, 'Monitor', 7);
~~~

Ở đây `available_units` có thể `NULL`. Cần phân biệt `NULL` với số 0 khi đọc lại.

### 5.1. Xuất snapshot sang file XML

~~~java
import java.io.IOException;
import java.io.OutputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.Objects;
import javax.sql.DataSource;
import javax.sql.rowset.RowSetProvider;
import javax.sql.rowset.WebRowSet;

public final class InventoryXmlArchive {
    private final DataSource dataSource;

    public InventoryXmlArchive(DataSource dataSource) {
        this.dataSource = Objects.requireNonNull(dataSource);
    }

    public void exportSnapshot(long startId, Path xmlPath)
            throws SQLException, IOException {

        Objects.requireNonNull(xmlPath, "xmlPath");

        String sql = "SELECT item_id, item_name, available_units "
                   + "FROM inventory_items WHERE item_id >= ? "
                   + "ORDER BY item_id";

        try (Connection connection = dataSource.getConnection();
             PreparedStatement ps = connection.prepareStatement(sql)) {

            ps.setLong(1, startId);

            // Giới hạn số dòng để WebRowSet không cache quá nhiều.
            ps.setMaxRows(1_000);

            try (ResultSet rs = ps.executeQuery();
                 WebRowSet web =
                         RowSetProvider.newFactory().createWebRowSet()) {

                // Dữ liệu và metadata được sao chép vào cache.
                web.populate(rs);

                // Đây là nội dung do WebRowSet sở hữu.
                // Connection không còn cần thiết để ghi XML
                // sau khi populate hoàn tất.
                try (OutputStream output =
                             Files.newOutputStream(xmlPath)) {
                    web.writeXml(output);
                }
            }
        }
    }
}
~~~

Ví dụ sử dụng:

~~~java
import java.nio.file.Path;
import java.nio.file.Paths;

InventoryXmlArchive archive = new InventoryXmlArchive(dataSource);
Path target = Paths.get("inventory-snapshot.xml");

archive.exportSnapshot(1001L, target);
~~~

**Giải thích:**

- `Connection` và `PreparedStatement` do phương thức sở hữu, được đóng bằng `try-with-resources`.
- `PreparedStatement` dùng placeholder `?` thay vì nối `startId` vào SQL.
- `ps.setMaxRows(1_000)` giới hạn số dòng nhận được trong ví dụ. Một `WebRowSet` vẫn lưu dữ liệu trong bộ nhớ; giới hạn này giúp tránh một thao tác vô tình tải cả bảng.
- `web.populate(rs)` tạo bản sao dữ liệu và metadata. Sau đó `web.writeXml(output)` ghi tài liệu XML mà không cần gửi thêm câu SQL.
- `OutputStream` được đóng đúng phạm vi. Nếu có lỗi `IOException` hoặc `SQLException`, tài nguyên JDBC cũng được giải phóng.
- Ví dụ ghi trực tiếp vào file đích; **nếu ghi lỗi, file có thể chỉ được ghi một phần**. Với dữ liệu quan trọng, ghi vào file tạm trong cùng thư mục và chỉ công bố/đổi tên sau khi ghi thành công, kèm chính sách xử lý khi filesystem không hỗ trợ atomic move.

`WebRowSet` không tự kiểm tra các điều kiện nghiệp vụ như `available_units >= 0` hoặc `item_name` có hợp lệ với ứng dụng. Nó chỉ lưu biểu diễn dữ liệu từ JDBC. Việc validate thuộc tầng nghiệp vụ hoặc tầng nhập dữ liệu riêng.

### 5.2. Nếu chỉ cần XML mà không dùng snapshot ngoại tuyến

Một câu hỏi thiết kế cần đặt ra: **Có cần một `WebRowSet` hay chỉ cần luồng XML?**

- Nếu muốn **gửi/nhận một RowSet có metadata và cấu trúc theo chuẩn WebRowSet**, `WebRowSet` là lựa chọn hợp lý.
- Nếu chỉ muốn API trả XML nghiệp vụ gồm vài trường, định dạng WebRowSet có thể thừa metadata và khó tương thích với client không dùng JDBC.
- Nếu muốn xuất hàng triệu dòng, nên duyệt `ResultSet` và ghi XML theo luồng bằng StAX/SAX hoặc cách tương đương; `WebRowSet` cache toàn bộ dữ liệu đã lấy nên có thể tốn RAM.

## 6. XML của WebRowSet chứa những gì?

Tài liệu do `writeXml` tạo có cấu trúc gắn với **định dạng WebRowSet** (thường mang namespace `http://java.sun.com/xml/ns/jdbc`). Các vùng thông tin quan trọng:

| Phần XML | Vai trò |
| --- | --- |
| `webRowSet` | Phần tử gốc và thông tin namespace/schema |
| `properties` | Một số thuộc tính của RowSet như cấu hình liên quan đến thao tác SQL và trạng thái |
| `metadata` | Số cột, nhãn/tên cột, kiểu JDBC và thông tin mô tả cột |
| `data` | Các dòng và giá trị cột được mã hóa theo định dạng WebRowSet |
| `currentRow` | Một dạng biểu diễn dòng dữ liệu hiện có |
| `insertRow`, `deleteRow`, `modifyRow` | Các dạng biểu diễn trạng thái thay đổi dòng theo schema/implementation |
| `columnValue` và các phần tử giá trị cập nhật | Giá trị cột và trong một số trường hợp trạng thái sửa đổi |

Sơ đồ bên dưới chỉ minh họa **các khối thông tin**, không phải tài liệu XML hoàn chỉnh có thể đưa thẳng vào `readXml`:

~~~xml
<webRowSet xmlns="http://java.sun.com/xml/ns/jdbc">
  <properties>...</properties>
  <metadata>...</metadata>
  <data>
    <currentRow>
      <columnValue>1001</columnValue>
      <columnValue>Keyboard</columnValue>
      <columnValue>12</columnValue>
    </currentRow>
  </data>
</webRowSet>
~~~

Tài liệu thật có các thành phần bắt buộc, thuộc tính và metadata theo schema của WebRowSet. **Không dùng ví dụ rút gọn này để thử `readXml`.** Cách tạo XML đúng là để `writeXml` sinh ra tài liệu rồi kiểm thử round-trip.

### Metadata giúp ích như thế nào?

Nếu ứng dụng chỉ viết:

~~~xml
<item>
  <id>1001</id>
  <name>Keyboard</name>
</item>
~~~

thì XML này truyền tải giá trị nhưng không nêu đầy đủ kiểu SQL, số cột hoặc trạng thái của RowSet. Ngược lại, XML của `WebRowSet` được thiết kế để mô tả **một tập dữ liệu quan hệ theo quy ước JDBC**, giúp một `WebRowSet` tương thích tái tạo tập dòng và truy cập chúng bằng các phương thức `ResultSet`.

Metadata có thể hữu ích khi trao đổi dữ liệu giữa hai thành phần Java cùng hiểu WebRowSet. Nhưng nó cũng làm tài liệu **dài hơn** và mang thêm chi tiết triển khai database. Nếu mục tiêu chỉ là trao đổi dữ liệu nghiệp vụ với web/mobile, XML tùy biến theo contract API hoặc JSON thường dễ quản lý và an toàn hơn.

### SQL `NULL` không giống chuỗi rỗng

Trong WebRowSet XML, giá trị SQL `NULL` phải được biểu diễn theo quy tắc XML của RowSet; không được tự suy rằng một thẻ không có ký tự luôn là `NULL`. Ví dụ:

- Cột `available_units = 0` là số 0 hợp lệ.
- Cột `available_units = NULL` là SQL null.
- Cột `item_name = ""` là chuỗi rỗng, không tương đương SQL null.

Khi đọc qua API JDBC, dùng getter phù hợp và `wasNull()` nếu getter trả primitive.

~~~java
int units = web.getInt("available_units");
Integer nullableUnits = web.wasNull()
        ? null
        : Integer.valueOf(units);
~~~

Việc giữ đúng ngữ nghĩa `NULL` là một lý do nên để `writeXml/readXml` xử lý định dạng WebRowSet, thay vì tự sửa nội dung XML bằng các phép thay chuỗi.

## 7. Đọc XML và khôi phục WebRowSet ngoại tuyến

Đọc lại file đã được `writeXml` tạo bằng một `WebRowSet` mới:

~~~java
import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.sql.SQLException;
import javax.sql.rowset.RowSetProvider;
import javax.sql.rowset.WebRowSet;

public final class InventoryXmlReader {
    public static long readAndPrint(Path xmlPath)
            throws IOException, SQLException {

        try (InputStream input = Files.newInputStream(xmlPath);
             WebRowSet web =
                     RowSetProvider.newFactory().createWebRowSet()) {

            web.readXml(input);
            web.beforeFirst();

            long rowCount = 0L;

            while (web.next()) {
                long id = web.getLong("item_id");
                if (web.wasNull()) {
                    throw new SQLException("item_id là NULL");
                }

                String name = web.getString("item_name");
                if (name == null) {
                    throw new SQLException("item_name là NULL");
                }

                int unitsValue = web.getInt("available_units");
                Integer units = web.wasNull()
                        ? null
                        : Integer.valueOf(unitsValue);

                System.out.println(
                        "item=" + id + " name=" + name
                      + " units=" + units);

                rowCount++;
            }

            return rowCount;
        }
    }
}
~~~

Lời gọi:

~~~java
Path snapshot = Paths.get("inventory-snapshot.xml");
long count = InventoryXmlReader.readAndPrint(snapshot);
System.out.println("Đã đọc " + count + " dòng từ XML");
~~~

Ví dụ gọi cần import `java.nio.file.Path` và `Paths`. Quan trọng hơn, `readAndPrint` **không có `DataSource` hoặc `Connection`**: đây là điểm minh họa khả năng đọc dữ liệu **ngoại tuyến**.

Tuy vậy, `web.readXml(input)` phải nạp và tái tạo RowSet trong bộ nhớ trước khi code duyệt dữ liệu. Do đó:

- Không lấy file WebRowSet XML rất lớn từ nguồn tùy ý và cho rằng `readXml` sẽ chỉ giữ một dòng tại một thời điểm.
- Với dữ liệu lớn hơn giới hạn bộ nhớ dự kiến, phải thay đổi chiến lược, ví dụ XML parser streaming, phân lô hoặc một định dạng dành cho dữ liệu lớn.
- Không mặc định việc phục hồi từ XML là cách kết nối lại database: `readXml` không chạy `SELECT` và không tự đồng bộ.
- Dữ liệu từ file có thể cũ so với database hiện tại; cần gắn thời điểm tạo snapshot và version nếu nghiệp vụ yêu cầu.

## 8. `writeXml` và `readXml`: chọn byte stream hay character stream?

`WebRowSet` cung cấp cả overload nhận `OutputStream`/`InputStream` và overload nhận `Writer`/`Reader`.

~~~java
// Luồng byte:
web.writeXml(outputStream);
web.readXml(inputStream);

// Luồng ký tự:
web.writeXml(writer);
web.readXml(reader);
~~~

Cần chú ý các điểm sau:

1. **`OutputStream`/`InputStream`** phù hợp khi làm việc với file hoặc dữ liệu mạng dưới dạng byte. Chúng tránh việc ứng dụng tự chọn một character encoding không khớp với XML declaration.
2. **`Writer`/`Reader`** yêu cầu một quyết định encoding ở tầng tạo writer/reader nếu bên dưới là luồng byte. Ví dụ `OutputStreamWriter` nên chỉ định charset rõ ràng thay vì phụ thuộc charset mặc định của máy.
3. **Không tự ghép XML từ những mảnh string** rồi gọi đó là WebRowSet XML. Biểu diễn XML gồm metadata, properties và row data, không chỉ giá trị cột.
4. **Không gọi `writeXml` rồi tiếp tục sửa dữ liệu RowSet và nghĩ file tự cập nhật.** File là một snapshot tại thời điểm phương thức ghi hoàn tất.
5. **Không cố trộn phiên bản XML khác nhau** khi chưa kiểm thử tính tương thích của parser/provider.

Đối với file lưu trữ, nên có một lớp quản lý version và thời điểm tạo snapshot bên ngoài file, ví dụ tên tệp, manifest đã ký hoặc metadata quản lý trên hệ thống lưu trữ. Không suy mọi metadata nghiệp vụ tùy ý đều được `WebRowSet` tự lưu.

## 9. Trạng thái dòng: ngoài dữ liệu hiện tại còn có gì?

`CachedRowSet` cho phép thao tác với dữ liệu đã cache ở bộ nhớ. Tùy cấu hình, một dòng có thể được đánh dấu là mới thêm, đã cập nhật hoặc đã xóa. `WebRowSet` được thiết kế để biểu diễn **cả nội dung và các trạng thái thay đổi này** theo cấu trúc XML của RowSet.

Một luồng công việc có thể là:

~~~text
1. Nạp các dòng từ database vào WebRowSet.
2. Ngắt kết nối.
3. Thay đổi giá trị trong RowSet ở phía Java.
4. Xuất RowSet thành XML.
5. Nhập XML vào một WebRowSet mới.
6. Xem xét những thay đổi và quyết định có đồng bộ không.
~~~

Những trạng thái này không nên bị hiểu thành transaction log của database:

- `rowInserted()`, `rowUpdated()` hoặc `rowDeleted()` mô tả trạng thái trong ngữ cảnh RowSet.
- Chúng không chứng minh rằng một câu `INSERT`/`UPDATE`/`DELETE` đã được commit trên server.
- Việc thay đổi RowSet **không tự gửi câu SQL** ngay lúc `updateRow()`, `insertRow()` hay `deleteRow()` như một repository ghi trực tiếp.
- Việc serialize trạng thái qua XML **không có nghĩa** một hệ thống khác bắt buộc phải chấp nhận và áp dụng thay đổi đó.

Nếu cần một hệ thống đồng bộ dữ liệu chính thức, phải có cơ chế kiểm soát version, khóa dữ liệu, người có quyền cập nhật, xung đột và audit; `WebRowSet` không thay thế được những yêu cầu này.

## 10. XML round-trip khác với `acceptChanges()`

Một trong những nhầm lẫn phổ biến nhất là xem việc ghi/đọc XML như một bước commit.

| Thao tác | Tác động vào đâu? | Có ghi DB không? |
| --- | --- | --- |
| `populate(rs)` | Cache dữ liệu `ResultSet` vào RowSet | Không ghi dữ liệu mới vào DB |
| `web.updateXxx(...)`, `updateRow()` | Thay đổi trạng thái cache của RowSet | **Chưa** đồng bộ DB |
| `web.writeXml(output)` | Xuất trạng thái RowSet thành XML | Không |
| `web.readXml(input)` | Tái tạo RowSet từ XML | Không |
| `web.acceptChanges(...)` | Yêu cầu `SyncProvider` đồng bộ các thay đổi | Có thể, **nếu** được cấu hình và hỗ trợ |
| `Connection.commit()` | Commit transaction của connection | Có, với những thay đổi thuộc transaction đó |

Vì `WebRowSet` kế thừa `CachedRowSet`, nó có thể sử dụng cơ chế `acceptChanges`. Nhưng việc đồng bộ ngược về DB cần các điều kiện như:

- RowSet có thông tin về bảng/khóa và nguồn dữ liệu phù hợp.
- Có `SyncProvider` hỗ trợ và cấu hình để xác định dòng cần cập nhật.
- Dữ liệu và schema còn tương thích.
- Quyền truy cập cho phép ghi.
- Không có xung đột với những thay đổi đã commit từ các transaction khác, hoặc có chính sách giải quyết xung đột.
- Transaction được điều phối rõ ràng.

Nếu có xung đột, cơ chế đồng bộ có thể ném `SyncProviderException` và cung cấp `SyncResolver` để xử lý theo cách provider hỗ trợ. **Không nên tự động gọi `acceptChanges` đối với XML do người dùng tải lên**, bởi XML có thể mô tả các trạng thái thay đổi không được phép.

Ví dụ thực tế: một bản snapshot sản phẩm lấy hôm thứ Hai, được chỉnh offline vào thứ Ba, nhưng giá và trạng thái sản phẩm trên database đã thay đổi vào chiều thứ Hai. Việc đồng bộ một bản cũ không thể chỉ dựa vào RowSet XML; cần version/timestamp hoặc optimistic locking và chính sách khi dữ liệu xung đột.

### Chọn `CachedRowSet` hay `WebRowSet`?

Nếu chỉ cần dữ liệu ngoại tuyến trong **cùng một tiến trình Java**, `CachedRowSet` có thể đủ. Chọn `WebRowSet` khi cần một định dạng **XML có khả năng trao đổi/khôi phục** của RowSet. Cả hai đều là dữ liệu cache, không phải ORM và không phải database nhúng có cơ chế lưu trữ bền vững tùy ý.

## 11. WebRowSet XML có phải format interchange phổ quát không?

Không hoàn toàn. `WebRowSet` XML hữu ích khi **hai đầu đều hiểu contract của Java RowSet**, nhưng nó không phải một API XML nghiệp vụ phổ quát.

Các yếu tố làm giảm tính di động:

1. **Metadata JDBC.** Một hệ thống không dùng Java có thể không cần hoặc không hiểu mã SQL type, metadata cột hay trạng thái hàng.
2. **Kiểu đặc thù của DBMS.** `ARRAY`, `STRUCT`, kiểu `OTHER` hoặc dữ liệu riêng driver có thể không round-trip tốt giữa hai provider.
3. **Phiên bản schema.** Một cột đổi kiểu/tên có thể khiến code ở đầu nhận không còn ánh xạ được.
4. **Kích thước.** XML nhiều metadata và thẻ lặp lại thường lớn hơn dữ liệu nhị phân hay format truyền tải chuyên dụng.
5. **Mục tiêu nghiệp vụ.** XML của WebRowSet mô tả bảng/cursor, trong khi API công khai thường cần các khái niệm như đơn hàng, khách hàng, phân trang, quyền truy cập và version.

Để trao đổi XML với bên thứ ba, nên cân nhắc một schema nghiệp vụ rõ ràng và chỉ xuất các trường được phép. Dùng WebRowSet XML khi thực sự cần **đặc điểm RowSet**, không phải vì từ “Web” trong tên giao diện khiến nó phù hợp mọi website.

### Phân biệt với `SQLXML`

`java.sql.SQLXML` biểu diễn **giá trị XML của một cột SQL** hoặc tham số kiểu XML. `WebRowSet` là **một tập dữ liệu nhiều dòng/cột** có khả năng serialize thành XML. Hai khái niệm khác nhau:

~~~text
SQLXML:         giá trị XML trong một ô SQL
WebRowSet XML:  biểu diễn của cả một tập dòng JDBC
~~~

Không dùng `ResultSet.getSQLXML("payload")` để đọc toàn bộ tài liệu WebRowSet, trừ khi database thực sự lưu tài liệu đó trong một cột XML. Cũng không giả định một `WebRowSet` được xây từ cột `SQLXML` sẽ tự biến nội dung XML của ô thành các cột mới.

## 12. Bảo mật: XML có thể chứa nhiều thông tin hơn bạn nghĩ

`WebRowSet` có thể đưa dữ liệu cột, metadata và một số thuộc tính RowSet vào XML. Với dữ liệu khách hàng, nhân sự hoặc giao dịch, file XML phải được xem như **một bản sao dữ liệu có thể nhạy cảm**.

### 12.1. Kiểm soát dữ liệu đầu ra

- **Chỉ truy vấn những cột cần xuất.** Tránh `SELECT *` nếu bảng có email, địa chỉ, token, trường nội bộ hoặc nội dung không được phép chia sẻ.
- **Áp dụng điều kiện quyền truy cập ngay trong truy vấn.** Ví dụ giới hạn tenant, tổ chức hoặc phạm vi dữ liệu của người yêu cầu.
- **Không đưa thông tin xác thực vào thuộc tính RowSet.** Nếu ứng dụng sử dụng các property như URL, username, password, command, data source name, cần xem định dạng/implementation sẽ serialize những gì. Đừng xuất XML từ RowSet có cấu hình chứa secret nếu chưa kiểm tra output.
- **Không log nguyên văn XML** hoặc toàn bộ đối tượng RowSet. Chỉ log mã tác vụ, số dòng, thời gian, checksum hoặc trace ID khi phù hợp.
- **Bảo vệ file và kênh truyền.** Dùng quyền truy cập file, TLS, mã hóa tại nơi lưu nếu có yêu cầu, giới hạn thời gian giữ và kiểm soát việc chia sẻ.
- **Kiểm tra nội dung sinh ra bằng test.** Tạo secret giả trong môi trường test và xác nhận không xuất hiện trong file XML ngoài ý muốn.

`writeXml` là chức năng biểu diễn dữ liệu, **không phải mã hóa hoặc ẩn danh dữ liệu**.

### 12.2. Không tin cậy XML đầu vào

`readXml` sẽ xử lý một tài liệu XML và tái tạo RowSet. Không nên coi đây là API an toàn mặc định để nhận mọi file XML từ Internet.

Rủi ro cần đánh giá:

| Rủi ro | Phương án kiểm soát |
| --- | --- |
| XML quá lớn khiến cấp phát nhiều bộ nhớ | Giới hạn dung lượng đầu vào, số dòng/cột và quota tài nguyên trước khi cho sử dụng |
| XML với cấu trúc/metadata không mong đợi | Chỉ cho phép đúng định dạng WebRowSet được tin cậy; kiểm tra các cột và kiểu sau khi đọc |
| XXE, external entity hoặc DTD tùy cách parser/provider xử lý | Đánh giá cấu hình an toàn của XML parser/RowSet provider; không nhận nguồn tùy ý khi chưa có biện pháp và kiểm thử |
| Dữ liệu bị chỉnh sửa trong quá trình truyền/lưu | Dùng chữ ký, checksum có xác thực hoặc kênh lưu trữ tin cậy tùy mô hình đe dọa |
| Giá trị không hợp lệ theo nghiệp vụ | Validate id, nullability, độ dài, phạm vi, enum và quyền truy cập khi nhập |
| XML có trạng thái dòng bị sửa/xóa | Không tự động đồng bộ thay đổi về DB; yêu cầu phân quyền và kiểm tra xung đột |
| Tên file do người dùng truyền vào | Giới hạn thư mục/đường dẫn được phép; không ghép path tùy ý |

Ví dụ giới hạn cơ bản khi đọc một file do hệ thống tạo:

~~~java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

static void checkSnapshotSize(Path file) throws IOException {
    long maxBytes = 10L * 1024 * 1024; // Ví dụ: 10 MiB.
    long size = Files.size(file);

    if (size > maxBytes) {
        throw new IOException("XML snapshot vượt giới hạn cho phép");
    }
}
~~~

Kiểm tra `Files.size` chỉ là bước **sàng lọc sơ bộ**: file có thể thay đổi sau lần kiểm tra hoặc đến từ một stream không có kích thước biết trước. Với input không tin cậy, cần giới hạn **số byte thực sự được đọc**, quota tài nguyên và chính sách parsing an toàn, không chỉ kiểm tra metadata file.

Khi đầu vào không nằm dưới sự kiểm soát của ứng dụng, có thể chọn **không sử dụng `readXml` trực tiếp**, thay bằng parser XML được cấu hình và kiểm soát chặt chẽ để ánh xạ vào DTO nghiệp vụ đã validate.

## 13. Bộ nhớ và hiệu năng: WebRowSet không thay thế streaming

Một sai lầm là sử dụng `WebRowSet` để “tránh giữ connection” rồi nghĩ rằng ứng dụng không còn nguy cơ thiếu RAM.

~~~mermaid
flowchart LR
    A["ResultSet N dòng"] --> B["WebRowSet cache N dòng"]
    B --> C["writeXml ra file"]
    C --> D["readXml"]
    D --> E["WebRowSet mới cache N dòng"]
~~~

Cả bước `populate` lẫn `readXml` có thể phải tạo cấu trúc dữ liệu cho **toàn bộ các dòng**. Khi N lớn, bộ nhớ vẫn tăng theo N. Ngoài ra, biểu diễn XML có metadata và overhead từ các thẻ/giá trị.

Bảng lựa chọn:

| Bài toán | Hướng tiếp cận |
| --- | --- |
| Vài chục đến vài nghìn dòng, cần thao tác offline và trao đổi theo định dạng RowSet XML | `WebRowSet` phù hợp khi đã kiểm tra giới hạn bộ nhớ |
| Cần cache dữ liệu offline nhưng không cần XML | `CachedRowSet` có thể đơn giản hơn |
| Xuất hàng triệu dòng để đối tác đọc XML | `ResultSet` với fetch/cursor phù hợp + XML writer streaming, không gom toàn bộ |
| Đồng bộ offline phức tạp với sửa/xóa/xung đột | API đồng bộ chuyên biệt, versioning và transaction rõ ràng |
| Chia sẻ dữ liệu qua REST với client không dùng JDBC | DTO/JSON/XML nghiệp vụ được version hóa |
| Tệp dữ liệu nhạy cảm | Giảm cột, mã hóa, phân quyền, audit và chính sách lưu trữ |

**Hãy đo peak heap và bộ nhớ native** trên database/driver mục tiêu nếu muốn biết WebRowSet dùng được với tập dữ liệu bao nhiêu dòng. Không đặt ngưỡng chỉ theo “số dòng”: 100 dòng chứa CLOB rất lớn có thể tốn hơn hàng nghìn dòng số nguyên.

## 14. Kiểm thử round-trip và tính đúng đắn

Một quy trình kiểm thử tốt nên sử dụng **database thử nghiệm và cùng driver/provider như môi trường triển khai**, không chỉ mock `ResultSet`:

1. Tạo fixture có dữ liệu số, text, `NULL` và Unicode; commit fixture.
2. Truy vấn bằng `PreparedStatement`, nạp vào `WebRowSet` rồi ghi XML.
3. Đóng mọi connection JDBC.
4. Tạo `WebRowSet` mới, đọc XML khi **không có connection mở**.
5. Kiểm tra số dòng, thứ tự mong đợi, giá trị cột và SQL `NULL`.
6. Đối chiếu metadata: số cột, kiểu cột, tên/nhãn cột.
7. Kiểm tra XML không chứa cột không được phép, dữ liệu nhạy cảm hay thông tin xác thực giả.
8. Kiểm tra lỗi khi file XML bị cắt giữa chừng, bị đổi cột/kiểu hoặc vượt giới hạn kích thước.
9. Kiểm tra thời gian/bộ nhớ với số dòng và kích thước dữ liệu lớn hơn.
10. Nếu có chức năng sửa dữ liệu offline, kiểm thử trạng thái dòng và **đồng bộ ngược trong transaction riêng**, bao gồm trường hợp xung đột.

### Một số assertion có thể áp dụng

~~~java
// Sau khi readXml(input) thành công:
web.beforeFirst();

int rows = 0;
while (web.next()) {
    rows++;

    long id = web.getLong("item_id");
    if (web.wasNull() || id <= 0) {
        throw new AssertionError("ID không hợp lệ");
    }
}

if (rows != 3) {
    throw new AssertionError("Sai số dòng sau XML round-trip");
}
~~~

Đoạn này minh họa cách kiểm tra khi XML được tạo từ ba dòng fixture. Giá trị `rows == 3` phải được thay bằng số dòng phù hợp với trường hợp test thực tế. Đừng lấy số dòng test làm một giới hạn chung cho mọi `WebRowSet`.

### Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân thường gặp | Cách kiểm tra |
| --- | --- | --- |
| `readXml` không đọc được file XML tự tạo | XML không tuân theo cấu trúc/schema WebRowSet | Sinh file mẫu bằng `writeXml` rồi làm round-trip |
| Dữ liệu bị thiếu cột | Truy vấn nguồn không chọn cột, alias/metadata thay đổi | Kiểm tra `ResultSetMetaData` trước khi `populate` |
| `getInt` trả `0` nhưng nguồn là `NULL` | Không gọi `wasNull()` | Kiểm tra ngay sau getter primitive |
| Đóng connection trước khi nạp xong | `populate` chưa kết thúc | Chỉ đóng connection sau khi populate thành công |
| Hết bộ nhớ khi xuất XML | `WebRowSet` cache quá nhiều dòng hoặc giá trị lớn | Giới hạn rows/bytes hoặc dùng streaming |
| File XML chỉ có một phần | Ghi file bị lỗi giữa chừng | Ghi file tạm, xác minh rồi công bố |
| Dữ liệu XML được phục hồi nhưng DB chưa đổi | `readXml` không đồng bộ DB | Phân biệt import snapshot với `acceptChanges` |
| Lỗi khi đồng bộ DB | Thiếu key/table metadata, quyền hoặc xung đột bản ghi | Kiểm tra `SyncProvider` và transaction |
| XML có thông tin không nên công khai | Xuất quá nhiều cột/thuộc tính RowSet | Giảm dữ liệu tại SQL, kiểm tra output, bảo vệ file |

## 15. Bài tập thực hành

### Bài 1 — Chọn giao diện

Ứng dụng cần lấy 200 dòng sản phẩm, đóng database connection và cho một màn hình nội bộ chỉnh sửa tạm thời trong bộ nhớ, không cần xuất XML. Khi nào `CachedRowSet` là đủ? Khi nào nên dùng `WebRowSet`?

**Gợi ý:** `WebRowSet` cần thiết khi yêu cầu giao tiếp/khôi phục qua định dạng WebRowSet XML. Nếu chỉ thao tác cache cùng tiến trình, `CachedRowSet` có thể đủ.

### Bài 2 — Viết chương trình round-trip

Hãy viết hai phương thức:

- `exportItems(DataSource ds, Path file)`: truy vấn có tham số, `populate(rs)` và `writeXml`.
- `readItems(Path file)`: `readXml`, `beforeFirst` và duyệt các dòng bằng `next/getXxx` mà không dùng `DataSource`.

Đối chiếu các giá trị `NULL` và số 0, thứ tự dòng, Unicode. Nếu không có DB test, có thể thực hành bước đọc từ **tài liệu XML hợp lệ do chính WebRowSet tạo** trong một test có setup phù hợp.

### Bài 3 — XML có phải backup DB không?

Bạn đã ghi XML chứa 100 dòng, sau đó xóa 100 dòng khỏi database. Khi gọi `readXml`, database có tự phục hồi không? Nếu không, cần thêm những điều kiện gì để đồng bộ ngược một cách an toàn?

**Gợi ý:** `readXml` chỉ tạo lại RowSet trong bộ nhớ. Đồng bộ cần provider, metadata/khóa, quyền, transaction và chính sách xử lý xung đột; không phải cứ có XML là có thể restore bảng.

### Bài 4 — Kiểm tra lộ thông tin

Một developer dùng `SELECT * FROM users` để tạo XML cho khách hàng tải xuống; bảng chứa password hash, token reset và email nội bộ. Vấn đề ở đâu và nên sửa ở tầng nào?

**Gợi ý:** Giới hạn cột và hàng ngay ở truy vấn có phân quyền, không dựa vào việc tự xóa chuỗi nhạy cảm sau khi `writeXml`. Cũng phải kiểm tra properties/metadata được serialize.

### Bài 5 — WebRowSet với một triệu dòng

Một job xuất một triệu bản ghi lớn qua `WebRowSet.populate(rs)` và có `OutOfMemoryError`. Vì sao thêm `ps.setFetchSize(500)` chưa chắc giải quyết được vấn đề?

**Gợi ý:** Fetch size chỉ điều khiển cách driver lấy dòng, trong khi `WebRowSet` vẫn **cache cả một triệu dòng**. Cần streaming writer, phân lô hoặc thay đổi định dạng/xử lý.

### Bài 6 — Trạng thái offline và xung đột

Một XML snapshot được tạo lúc 09:00. Người dùng sửa một dòng khi offline; trước khi nhận file, người khác đã cập nhật cùng dòng trên DB lúc 09:30. Có nên gọi `acceptChanges` ngay sau `readXml` không?

**Gợi ý:** Không. Cần xác thực nguồn, quyền cập nhật, version/optimistic locking, thông tin khóa và cơ chế xử lý conflict. XML không tự xác minh dữ liệu còn mới.

---

## 16. Checklist áp dụng WebRowSet

- [ ] Nhu cầu thực sự là **RowSet ngoại tuyến có thể biểu diễn XML**, không chỉ xuất XML nghiệp vụ.
- [ ] Tạo đối tượng qua `RowSetProvider.newFactory().createWebRowSet()`.
- [ ] Dùng `PreparedStatement` tham số hóa và chọn **chỉ các cột cần thiết**.
- [ ] `populate(rs)` hoàn tất **trước khi đóng** `ResultSet` và connection.
- [ ] Sử dụng `writeXml/readXml` đúng overload, đóng luồng đầu vào/đầu ra.
- [ ] Kiểm thử XML do `writeXml` sinh ra có thể phục hồi qua `readXml`.
- [ ] Phân biệt dữ liệu SQL `NULL` với giá trị 0/chuỗi rỗng.
- [ ] Không xem XML là commit DB hoặc cơ chế sao lưu/khôi phục tự động.
- [ ] Có giới hạn số dòng/byte và đo bộ nhớ trước khi dùng với tập dữ liệu lớn.
- [ ] Kiểm soát dữ liệu nhạy cảm, properties RowSet, quyền file và nguồn XML không tin cậy.
- [ ] Có quy trình riêng nếu muốn đồng bộ cập nhật offline về database.
- [ ] Có kiểm thử schema/version, lỗi parsing, dữ liệu giả nhạy cảm và tài nguyên khi lỗi.

**Kết luận:** `WebRowSet` là cầu nối giữa **mô hình dữ liệu dạng bảng của JDBC** và **định dạng XML mang thông tin RowSet**, đặc biệt hữu ích khi cần sử dụng dữ liệu sau khi đã ngắt kết nối hoặc trao đổi snapshot giữa các thành phần hiểu chuẩn WebRowSet. Nó không thay thế SQL streaming, không tự đồng bộ database và không tự bảo vệ XML chứa dữ liệu nhạy cảm. Chọn `WebRowSet` khi cần đúng giá trị **XML round-trip của một CachedRowSet**, với phạm vi dữ liệu, bảo mật và vòng đời tài nguyên được kiểm soát.
