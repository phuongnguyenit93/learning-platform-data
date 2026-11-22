# Giới hạn số dòng và kích thước trường cần đọc khi thực thi SQL với JDBC

## 1. Bài toán: tại sao không nên đọc mọi hàng và mọi cột?

**JDBC (Java Database Connectivity)** là API Java dùng để truy cập cơ sở dữ liệu quan hệ, thực thi SQL và lấy kết quả qua `java.sql.ResultSet`. Một câu `SELECT` có thể trả hàng triệu bản ghi; mỗi hàng lại có thể chứa chuỗi dài, JSON, văn bản, ảnh hoặc tệp nhị phân. Nếu ứng dụng đọc dữ liệu không có giới hạn, nó có thể tiêu tốn bộ nhớ, băng thông, thời gian xử lý và chiếm giữ kết nối database quá lâu.

Chẳng hạn, một màn hình danh sách tài liệu chỉ cần **20 tài liệu mới nhất**, mỗi tài liệu gồm mã, tiêu đề và **200 ký tự trích dẫn**. Đọc toàn bộ bảng cùng nội dung đầy đủ của từng tài liệu rồi cắt bớt ở Java sẽ tạo ra nhiều dữ liệu trung gian không cần thiết.

Trong chương **Thực thi SQL**, việc đặt giới hạn cần được xem ở ba chiều độc lập:

1. **Số hàng:** ứng dụng được nhận bao nhiêu bản ghi?
2. **Số cột và kích thước từng giá trị:** mỗi hàng cần chứa những trường nào và bao nhiêu dữ liệu?
3. **Cách truyền và duyệt dữ liệu:** driver có thể lấy từng nhóm hàng thay vì giữ toàn bộ kết quả cùng lúc không?

JDBC cung cấp `Statement.setMaxRows(...)`, `Statement.setLargeMaxRows(...)`, `Statement.setMaxFieldSize(...)` và `Statement.setFetchSize(...)`. SQL cũng có các cách giới hạn số hàng, lọc cột hoặc tạo đoạn trích ngay tại database. Các cơ chế này **khác mục đích** và không thể thay thế lẫn nhau.

Sau bài này, bạn sẽ biết chọn giới hạn ở đúng tầng, hiểu đơn vị của từng API, xử lý kết quả không đầy đủ và viết truy vấn chỉ đọc phần dữ liệu nghiệp vụ cần.

## 2. Bốn cơ chế thường bị nhầm lẫn

| Cơ chế | Giới hạn/điều khiển cái gì? | Tính chất | Có tự giảm công việc database? |
|---|---|---|---|
| `Statement.setMaxRows(int)` | Số hàng tối đa trong `ResultSet` do statement tạo ra | Giới hạn JDBC, `0` nghĩa là không đặt giới hạn | **Không bảo đảm** database sẽ tối ưu truy vấn tương ứng |
| `Statement.setLargeMaxRows(long)` | Giới hạn số hàng với kiểu `long` thay vì `int` | Giống mục đích `setMaxRows`, hữu ích khi giới hạn vượt kiểu `int` | **Không bảo đảm** |
| `Statement.setMaxFieldSize(int)` | Số **byte** tối đa trong giá trị cột ký tự/nhị phân thuộc các loại được quy định | Có thể cắt dữ liệu từng trường; `0` là không giới hạn | **Không bảo đảm** server chỉ đọc hoặc truyền từng ấy byte |
| `Statement.setFetchSize(int)` | Gợi ý số hàng driver nên lấy mỗi đợt | **Hint**, không phải giới hạn tổng số hàng; `0` để driver quyết định | Phụ thuộc driver, cursor và cấu hình |
| `LIMIT`, `FETCH FIRST`, `TOP` trong SQL | Số hàng mà truy vấn yêu cầu trả về | Ràng buộc ở **câu SQL**, cú pháp khác nhau theo hệ quản trị | Có thể giúp database tối ưu, nhưng không cam kết công việc luôn nhỏ |
| `SELECT` cột cụ thể, `SUBSTRING(...)` | Các cột và phần giá trị được database trả về | Chủ động xác định dữ liệu cần đọc trong SQL | Thường giảm dữ liệu trả về; hiệu quả phụ thuộc truy vấn và database |

Sơ đồ:

~~~mermaid
flowchart LR
    A["SQL WHERE / ORDER BY / LIMIT<br/>và danh sách cột"] --> B[("Database")]
    B --> C["JDBC driver"]
    D["setFetchSize()<br/>gợi ý cách lấy hàng"] -.-> C
    E["setMaxRows()<br/>giới hạn hàng ResultSet"] -.-> C
    F["setMaxFieldSize()<br/>giới hạn byte của<br/>một số giá trị cột"] -.-> C
    C --> G["ResultSet"]
    G --> H["DTO / xử lý nghiệp vụ"]
~~~

Một trang cần 20 hàng không nên chỉ gọi `setFetchSize(20)`: câu lệnh đó **không nói rằng chỉ được trả 20 hàng**. Ngược lại, đặt `setMaxRows(20)` không đồng nghĩa dữ liệu mỗi hàng được giới hạn kích thước.

## 3. `setMaxRows(int)`: giới hạn số hàng trong kết quả JDBC

`Statement.setMaxRows(int max)` đặt số hàng tối đa mà `ResultSet` sinh từ statement đó có thể chứa. `PreparedStatement` kế thừa `Statement`, vì vậy cũng sử dụng phương thức này.

- Giá trị **dương** đặt giới hạn số hàng.
- Giá trị **`0`** loại bỏ giới hạn do thuộc tính này đặt ra.
- Giá trị **âm** không hợp lệ và gây `SQLException`.
- Giới hạn được đặt trên **statement**, không phải mặc định cho mọi kết nối hoặc mọi truy vấn của ứng dụng.
- Khi kết quả có nhiều hàng hơn giới hạn, các hàng vượt giới hạn không được cung cấp trong `ResultSet` đó.

### Ví dụ: chỉ đọc tối đa 50 hàng

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import javax.sql.DataSource;

public final class RecentOrderPrinter {
    public static void printRecentOrders(DataSource source)
            throws SQLException {
        String sql = """
                SELECT id, customer_id, total_amount
                FROM orders
                ORDER BY created_at DESC, id DESC
                """;

        try (Connection connection = source.getConnection();
             PreparedStatement statement = connection.prepareStatement(sql)) {
            statement.setMaxRows(50);

            try (ResultSet rs = statement.executeQuery()) {
                while (rs.next()) {
                    System.out.printf("order=%d customer=%d total=%s%n",
                            rs.getLong("id"),
                            rs.getLong("customer_id"),
                            rs.getBigDecimal("total_amount"));
                }
            }
        }
    }
}
~~~

Ví dụ giả định có bảng `orders` với các cột tương ứng, driver hỗ trợ JDBC và `DataSource` đã cấu hình. `ORDER BY created_at DESC, id DESC` yêu cầu thứ tự rõ ràng, đồng thời dùng khóa `id` làm tiêu chí phụ để phân định khi nhiều đơn có cùng thời gian tạo.

Nếu có 12 hàng phù hợp, vòng lặp đọc 12 hàng; nếu có 1.000 hàng, `ResultSet` được giới hạn ở 50 hàng. Đây là **giới hạn kết quả mà ứng dụng có thể đọc**, không phải một hợp đồng rằng database chỉ cần kiểm tra 50 hàng hay chỉ truyền 50 hàng qua mạng. Hành vi thực tế phụ thuộc driver và kế hoạch thực thi của database.

### `setMaxRows` không phải cơ chế phân trang

Gọi `setMaxRows(50)` rồi chạy lại cùng câu `SELECT` không tự nhảy sang hàng 51–100. Nó chỉ áp dụng giới hạn đầu kết quả theo thứ tự truy vấn. Khi cần trang tiếp theo, phải thêm điều kiện/phân trang vào câu SQL hoặc thiết kế cursor phù hợp.

Nếu không có `ORDER BY`, tập hàng “đầu tiên” không có ý nghĩa ổn định. Database có quyền trả các hàng theo thứ tự khác nhau giữa những lần chạy.

### `setLargeMaxRows(long)`

Với API JDBC hiện đại, `Statement.setLargeMaxRows(long max)` sử dụng kiểu `long` để biểu diễn giới hạn có thể lớn hơn `Integer.MAX_VALUE`. Quy tắc `0` không giới hạn và giá trị âm không hợp lệ tương tự `setMaxRows`.

~~~java
statement.setLargeMaxRows(1_000_000L);
long configured = statement.getLargeMaxRows();
~~~

Ví dụ này chỉ minh họa API; lấy một triệu hàng vào bộ nhớ thường không phù hợp cho API trả danh sách. Khi nhu cầu dữ liệu thật sự lớn, cần cân nhắc streaming, phân lô và kích thước trường thay vì tăng giới hạn một cách máy móc.

## 4. Đặt giới hạn ngay trong SQL

Nếu mục tiêu nghiệp vụ là “chỉ lấy tối đa 20 bản ghi”, việc đặt giới hạn **trực tiếp trong SQL** giúp hệ quản trị có cơ hội chọn kế hoạch thực thi hợp lý hơn. Cú pháp khác nhau tùy database:

| Hệ quản trị | Câu SQL minh họa |
|---|---|
| PostgreSQL, MySQL | `SELECT id FROM orders ORDER BY id LIMIT 20` |
| SQL Server | `SELECT TOP (20) id FROM orders ORDER BY id` |
| Oracle Database phiên bản hỗ trợ cú pháp row limiting | `SELECT id FROM orders ORDER BY id FETCH FIRST 20 ROWS ONLY` |
| Hệ quản trị hỗ trợ cú pháp SQL standard tương ứng | `SELECT id FROM orders ORDER BY id FETCH FIRST 20 ROWS ONLY` |

Không có một cú pháp SQL giới hạn số hàng duy nhất chạy nguyên vẹn trên mọi hệ quản trị. Tính năng và cách bind tham số trong mệnh đề giới hạn phải kiểm tra theo database/driver thực tế.

### Ví dụ thực tế: giới hạn truy vấn bằng `LIMIT ?`

Ví dụ dưới đây dùng **PostgreSQL/MySQL** và chỉ tải nội dung cần hiển thị:

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.ArrayList;
import java.util.List;
import javax.sql.DataSource;

record DocumentPreview(long id, String title, String excerpt) {}

public final class DocumentCatalog {
    private static final int MAX_PAGE_SIZE = 100;
    private final DataSource dataSource;

    public DocumentCatalog(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public List<DocumentPreview> firstPage(int requestedSize)
            throws SQLException {
        if (requestedSize < 1) {
            throw new IllegalArgumentException("Page size phải lớn hơn 0");
        }
        int pageSize = Math.min(requestedSize, MAX_PAGE_SIZE);

        // Ví dụ cú pháp PostgreSQL/MySQL.
        String sql = """
                SELECT id,
                       title,
                       SUBSTRING(content, 1, 200) AS excerpt
                FROM documents
                WHERE published = ?
                ORDER BY published_at DESC, id DESC
                LIMIT ?
                """;

        List<DocumentPreview> previews = new ArrayList<>();
        try (Connection connection = dataSource.getConnection();
             PreparedStatement statement = connection.prepareStatement(sql)) {
            statement.setBoolean(1, true);
            statement.setInt(2, pageSize);

            // Giới hạn dự phòng ở tầng JDBC, không thay thế LIMIT.
            statement.setMaxRows(pageSize);

            try (ResultSet rs = statement.executeQuery()) {
                while (rs.next()) {
                    previews.add(new DocumentPreview(
                            rs.getLong("id"),
                            rs.getString("title"),
                            rs.getString("excerpt")));
                }
            }
        }
        return previews;
    }
}
~~~

Mã dùng **Java 17+** (`record` và text block), giả định bảng `documents(id, title, content, published, published_at)`. `SUBSTRING(content, 1, 200)` là ví dụ lấy **tối đa 200 ký tự theo ngữ nghĩa chuỗi của database**, không phải 200 byte. Hãy kiểm tra cú pháp hàm chuỗi và quy ước đếm ký tự của hệ quản trị cụ thể.

Điểm cần thấy:

1. `requestedSize` được kiểm tra và chặn tối đa ở tầng ứng dụng để một request không tự ý yêu cầu hàng triệu hàng.
2. `WHERE` giảm các hàng cần xét theo điều kiện nghiệp vụ.
3. `SELECT` chỉ liệt kê ba cột cần cho danh sách; trường `content` chỉ được lấy dưới dạng đoạn trích.
4. `ORDER BY` xác định thứ tự cho trang đầu.
5. `LIMIT ?` đặt giới hạn **tại SQL**, còn `setMaxRows(pageSize)` là lớp bảo vệ bổ sung cho kết quả JDBC.
6. Dữ liệu được ánh xạ vào `List<DocumentPreview>` khi kết nối còn mở, sau đó các tài nguyên JDBC được đóng.

Ngay cả với `LIMIT`, database có thể phải đọc hoặc sắp xếp nhiều hàng để tìm những hàng đứng đầu nếu thiếu index phù hợp. Đặt giới hạn là điều kiện quan trọng, nhưng **không thay thế việc kiểm tra execution plan** khi dữ liệu lớn.

## 5. Phân trang đúng cách: giới hạn số hàng nhưng vẫn lấy được trang sau

### 5.1. Phân trang theo offset

Với PostgreSQL/MySQL:

~~~sql
SELECT id, title
FROM documents
WHERE published = TRUE
ORDER BY published_at DESC, id DESC
LIMIT 20 OFFSET 40;
~~~

Ví dụ lấy trang có 20 hàng bắt đầu sau 40 hàng đầu theo thứ tự truy vấn. `LIMIT` và `OFFSET` có cú pháp tương ứng tùy database; SQL Server, Oracle và một số hệ khác dùng cách diễn đạt riêng.

**Nhược điểm của offset lớn:** database có thể phải duyệt/bỏ qua nhiều hàng trước khi trả trang hiện tại. Nếu có bản ghi mới hoặc cập nhật giữa hai lần truy vấn, offset còn có thể dẫn đến bỏ sót hoặc đọc lặp bản ghi. `ORDER BY` giúp xác định thứ tự cho từng truy vấn nhưng không đóng băng dữ liệu xuyên các request.

### 5.2. Keyset pagination khi danh sách dài

Thay vì nhảy theo vị trí, ứng dụng có thể ghi nhớ khóa của hàng cuối đã hiển thị:

~~~sql
-- PostgreSQL/MySQL: tham số lần lượt là
-- lastPublishedAt, lastPublishedAt, lastId và pageSize.
SELECT id, title, published_at
FROM documents
WHERE published = TRUE
  AND (
      published_at < ?
      OR (published_at = ? AND id < ?)
  )
ORDER BY published_at DESC, id DESC
LIMIT ?;
~~~

Ví dụ giả định `published_at` **không `NULL`** và `id` là khóa duy nhất. Cặp `(published_at, id)` định vị hàng cuối, sau đó truy vấn lấy các hàng nằm sau theo thứ tự giảm dần. Cách này thường phù hợp với các danh sách dài, nhất là khi có index hỗ trợ; cần thiết kế cursor và xử lý bản ghi thay đổi theo yêu cầu nghiệp vụ.

### 5.3. Cần biết có trang tiếp theo?

Một kỹ thuật phổ biến là truy vấn **`pageSize + 1`** hàng, trả tối đa `pageSize` hàng cho client và dùng hàng dư để nhận biết còn trang kế. Nếu dùng kỹ thuật này, cả giới hạn SQL và `setMaxRows` (nếu có) phải cho phép đọc **`pageSize + 1`**, nếu không ứng dụng sẽ không nhìn thấy hàng dư.

Số hàng bằng giới hạn **không chứng minh** chắc chắn còn hàng tiếp theo. Muốn biết tổng số hàng, ứng dụng phải dùng truy vấn đếm phù hợp hoặc một cơ chế metadata khác; truy vấn đếm có chi phí riêng và không nhất thiết phản ánh cùng snapshot khi dữ liệu đang thay đổi.

## 6. `setMaxFieldSize(int)`: giới hạn kích thước giá trị cột

`Statement.setMaxFieldSize(int max)` quy định số **byte** tối đa trả về cho các giá trị thuộc **nhóm cột ký tự hoặc nhị phân được JDBC chỉ định** khi đọc `ResultSet` do statement tạo.

Theo hợp đồng JDBC, giới hạn này áp dụng cho các kiểu như:

- `CHAR`, `VARCHAR`, `LONGVARCHAR`, `NCHAR`, `NVARCHAR`, `LONGNVARCHAR`.
- `BINARY`, `VARBINARY`, `LONGVARBINARY`.

Nó **không phải giới hạn hàng**, **không phải giới hạn toàn bộ `ResultSet`**, và không được xem là cách chung để giới hạn mọi loại dữ liệu, đặc biệt các đối tượng LOB như `BLOB` hoặc `CLOB`.

Quy tắc:

- `max > 0`: giá trị cột thuộc nhóm được áp dụng có thể bị cắt ở giới hạn byte tương ứng.
- `max = 0`: không đặt giới hạn bằng thuộc tính này.
- `max < 0`: không hợp lệ, ném `SQLException`.
- Khi vượt giới hạn, dữ liệu dư có thể bị **loại bỏ âm thầm** theo hợp đồng của API. Không nên dựa vào việc luôn có warning hoặc exception báo cắt dữ liệu.

### Ví dụ: chỉ lấy tối đa 1.024 byte mỗi trường phù hợp

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import javax.sql.DataSource;

public final class NoteReader {
    public static void showNotes(DataSource source) throws SQLException {
        String sql = """
                SELECT id, title, note_text
                FROM notes
                ORDER BY id
                """;

        try (Connection connection = source.getConnection();
             PreparedStatement statement = connection.prepareStatement(sql)) {
            statement.setMaxRows(20);        // Số hàng tối đa.
            statement.setMaxFieldSize(1024); // Byte mỗi giá trị ký tự/nhị phân áp dụng.

            try (ResultSet rs = statement.executeQuery()) {
                while (rs.next()) {
                    long id = rs.getLong("id");
                    String title = rs.getString("title");
                    String noteText = rs.getString("note_text");

                    // noteText có thể chỉ là một phần của giá trị SQL gốc.
                    System.out.printf("%d %s: %s%n", id, title, noteText);
                }
            }
        }
    }
}
~~~

Ví dụ giả định `notes(id, title, note_text)`, trong đó `title` và `note_text` thuộc các kiểu ký tự chịu tác động của `setMaxFieldSize`. Nếu một ghi chú có 4.000 byte, ứng dụng **không được giả định** `getString("note_text")` trả về đầy đủ nội dung. Tương tự, một tiêu đề dài cũng có thể bị cắt: giới hạn này áp dụng theo **loại giá trị cột**, không chỉ riêng cột `note_text`.

**Điểm dễ mắc lỗi:** `setMaxFieldSize(1024)` giới hạn **byte**, không phải 1.024 ký tự Unicode. Một ký tự tiếng Việt có thể chiếm nhiều byte trong bảng mã như UTF-8. Cách tính/biểu diễn byte thực tế chịu ảnh hưởng của dữ liệu và driver, vì vậy không dùng thuộc tính này để làm giao diện “hiển thị đúng 1.024 ký tự”.

### Nguy cơ mất dữ liệu âm thầm

Giới hạn trường có thể hữu ích khi chấp nhận kết quả bị cắt cho mục đích hiển thị/tổng quan. Tuy nhiên, dữ liệu đã bị cắt **không còn toàn vẹn**. Không dùng kết quả này để:

- So sánh chuỗi đầy đủ, kiểm tra chữ ký/hash hoặc xác thực nội dung.
- Phân tích JSON/XML đòi hỏi cú pháp hoàn chỉnh.
- Trích xuất định danh, email, URL hoặc trường nghiệp vụ có thể nằm cuối chuỗi.
- Xuất báo cáo pháp lý/tài chính phải bảo đảm dữ liệu đầy đủ.
- Ghi lại database như thể đó là giá trị gốc.

Nếu nghiệp vụ cần một đoạn trích chính xác theo số **ký tự**, hãy chọn cột, dùng hàm chuỗi SQL phù hợp hoặc cắt sau khi đã biết giới hạn dữ liệu; nếu nghiệp vụ cần **nguyên vẹn**, không đặt giới hạn có khả năng cắt sai giá trị.

## 7. Cắt nội dung ở SQL và cắt ở JDBC khác nhau thế nào?

Xem hai lựa chọn:

~~~sql
-- Cách 1: yêu cầu database trả đúng trường cần hiển thị.
-- Cú pháp minh họa PostgreSQL/MySQL.
SELECT id, title, SUBSTRING(content, 1, 200) AS excerpt
FROM documents
ORDER BY id
LIMIT 20;
~~~

~~~java
// Cách 2: JDBC giới hạn độ dài giá trị ký tự/nhị phân được trả về.
statement.setMaxRows(20);
statement.setMaxFieldSize(1024);
~~~

Khác biệt:

| Tiêu chí | `SUBSTRING(...)` trong SQL | `setMaxFieldSize(...)` trong JDBC |
|---|---|---|
| Đặt giới hạn ở đâu? | Trong biểu thức SQL, ngay tại database | Trên statement JDBC |
| Đơn vị thường dùng | Số ký tự theo hàm/collation của database | Số byte |
| Chọn cột nào? | Chỉ cột được đưa qua biểu thức `SUBSTRING` | Áp dụng theo loại dữ liệu cột phù hợp trong kết quả |
| Tên trường trả về | Có thể dùng alias như `excerpt` | Không thay đổi tên trường |
| Khả năng giảm dữ liệu truyền | Có thể giúp giảm phần giá trị trả về | Không được mặc định là server cắt trước khi truyền |
| Nguy cơ mất dữ liệu | Có, nếu nhầm đoạn trích là toàn bộ giá trị | Có, đặc biệt vì có thể cắt âm thầm |

Để hiển thị danh sách, phương án chủ động **`SELECT` đúng cột + tạo `excerpt` ở SQL** thường rõ ý định hơn. Đối với cột chứa giá trị lớn, database có thể vẫn phải truy cập dữ liệu gốc để tạo đoạn trích; cần đo hiệu năng thay vì giả định truy vấn luôn rẻ.

## 8. `setFetchSize` giúp điều khiển cách đọc, không giới hạn số hàng

`Statement.setFetchSize(int rows)` là một **gợi ý** cho JDBC driver về số hàng nên lấy mỗi đợt. Cơ chế này có thể ảnh hưởng đến số lần trao đổi mạng và bộ nhớ đệm, nhưng phụ thuộc khả năng hỗ trợ của driver, cursor và cấu hình kết nối.

~~~java
String sql = "SELECT id, event_type FROM audit_events ORDER BY id";
try (Connection connection = dataSource.getConnection();
     PreparedStatement statement = connection.prepareStatement(sql)) {

    statement.setFetchSize(500); // Hint: khoảng 500 hàng mỗi đợt, nếu driver hỗ trợ.

    try (ResultSet rs = statement.executeQuery()) {
        while (rs.next()) {
            process(rs.getLong("id"), rs.getString("event_type"));
        }
    }
}
~~~

Đây là đoạn minh họa trong phương thức đã có `dataSource` và `process(long, String)`, có xử lý hoặc khai báo `SQLException`. **Dù đặt `fetchSize = 500`, vòng lặp vẫn có thể đọc toàn bộ số hàng**. Một số driver dùng cursor phía server hoặc yêu cầu auto-commit/transaction mode cụ thể để hỗ trợ streaming. Nếu không thỏa điều kiện, driver có thể đệm nhiều dữ liệu hơn mong đợi.

### Đặt `setMaxRows` và `setFetchSize` cùng lúc

~~~java
statement.setMaxRows(1_000); // Tối đa 1.000 hàng trong kết quả JDBC.
statement.setFetchSize(100); // Gợi ý fetch khoảng 100 hàng mỗi đợt.
~~~

Hai câu lệnh trên **không mâu thuẫn**: một bên đặt giới hạn tổng số hàng, bên kia đưa ra gợi ý cách truyền theo đợt. Chúng cũng **không bảo đảm** tiêu thụ chính xác 100 hàng hoặc một mức bộ nhớ cố định. Cần thử nghiệm trên đúng driver/database và đọc tài liệu về streaming/cursor.

## 9. Trường có dữ liệu lớn: xử lý `BLOB`/`CLOB` theo luồng

`setMaxFieldSize` không được thiết kế như cơ chế giới hạn phổ quát cho LOB. Với cột `BLOB`/`CLOB` hoặc dữ liệu quá lớn, hãy cân nhắc những cách sau:

1. **Không `SELECT` cột lớn** khi màn hình chỉ cần metadata, trạng thái hoặc đoạn trích.
2. **Trả đoạn trích từ database** nếu cần preview.
3. **Dùng stream** như `ResultSet.getBinaryStream(...)` hoặc `getCharacterStream(...)` khi cần đọc dữ liệu lớn mà không muốn tạo `byte[]` hoặc `String` chứa toàn bộ kết quả.
4. **Giới hạn tổng số byte ứng dụng chấp nhận** bằng logic riêng hoặc quy tắc nghiệp vụ, kể cả khi đang stream.
5. **Đóng stream và tài nguyên JDBC** đúng vòng đời. Driver có thể giữ kết nối/cursor mở trong lúc stream chưa được tiêu thụ xong.

Ví dụ truyền dữ liệu nhị phân qua bộ đệm cố định, với giới hạn đọc trong ứng dụng:

~~~java
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import javax.sql.DataSource;

public final class AttachmentReader {
    private static final long MAX_BYTES = 10L * 1024 * 1024; // 10 MiB.

    public static void copyAttachment(
            DataSource source, long attachmentId, OutputStream destination)
            throws SQLException, IOException {

        String sql = "SELECT content FROM attachments WHERE id = ?";
        try (Connection connection = source.getConnection();
             PreparedStatement statement = connection.prepareStatement(sql)) {
            statement.setLong(1, attachmentId);

            try (ResultSet rs = statement.executeQuery()) {
                if (!rs.next()) {
                    throw new IllegalArgumentException("Không tìm thấy tệp");
                }

                try (InputStream input = rs.getBinaryStream("content")) {
                    if (input == null) {
                        return; // Cột SQL NULL.
                    }
                    byte[] buffer = new byte[8192];
                    long copied = 0;
                    int n;
                    while ((n = input.read(buffer)) != -1) {
                        if (n > MAX_BYTES - copied) {
                            throw new IOException("Tệp vượt giới hạn 10 MiB");
                        }
                        destination.write(buffer, 0, n);
                        copied += n;
                    }
                }
            }
        }
    }
}
~~~

Ví dụ giả định `attachments(id, content)`, `destination` do caller cung cấp và caller quản lý vòng đời của nó. Tệp bị từ chối sau khi đã viết một phần dữ liệu ra `destination`; nếu cần tính nguyên tử của đầu ra, hãy ghi vào vùng tạm, kiểm tra kích thước rồi mới công bố thành phẩm hoặc kiểm tra kích thước trước khi stream nếu metadata đáng tin cậy. Không dùng ví dụ này như một giao thức tải tệp hoàn chỉnh có retry/range request.

Mã trên giới hạn **số byte do chính ứng dụng xử lý**, độc lập với số hàng. Driver vẫn có thể tự đệm dữ liệu theo cách triển khai của nó, nên stream không bảo đảm tổng bộ nhớ ở mức cố định trên mọi driver.

## 10. Giới hạn dữ liệu trả về của cả một API

Giới hạn số hàng và một số giá trị cột chỉ là phần của bài toán. Kích thước thực tế còn phụ thuộc vào số cột, metadata, mã hóa ký tự, định dạng trả về như JSON và các đối tượng lồng nhau.

Ví dụ: 100 hàng, mỗi hàng 20 cột với dữ liệu trung bình 1 KiB cho mỗi cột có thể tạo ra khoảng 2 MiB dữ liệu thô, chưa tính metadata và overhead ở Java/JSON. Do đó:

- **Giới hạn số hàng:** chặn `pageSize`, `LIMIT`/`FETCH FIRST`, hoặc `setMaxRows` phù hợp.
- **Giới hạn số cột:** tránh `SELECT *`; chỉ lấy trường yêu cầu.
- **Giới hạn giá trị lớn:** dùng projection, đoạn trích hoặc luồng với hạn mức.
- **Giới hạn thời gian:** dùng `setQueryTimeout(...)` khi phù hợp để hạn chế truy vấn kéo dài, lưu ý nó không phải giới hạn byte hoặc hàng.
- **Giới hạn memory/output:** kiểm soát kích thước DTO, response, tệp xuất và phân lô trên tầng ứng dụng.

Với hệ thống multi-tenant hoặc dữ liệu nhạy cảm, luôn đặt điều kiện phân quyền/tenant trong truy vấn hoặc tầng bảo vệ phù hợp. **`LIMIT 20` không phải biện pháp kiểm soát quyền truy cập:** một hàng bị lộ vẫn là một sự cố bảo mật.

## 11. Những hiểu nhầm và lỗi thường gặp

### “`setFetchSize(100)` chỉ trả về 100 hàng”

Sai. Đây là gợi ý số hàng trong một lần fetch. Nếu không có giới hạn khác, vòng lặp `while (rs.next())` vẫn có thể đọc mọi hàng của kết quả.

### “`setMaxRows(20)` làm database chắc chắn chỉ quét 20 hàng”

Sai. Đây là giới hạn kết quả ở tầng JDBC, không phải cam kết kế hoạch thực thi. Với truy vấn phức tạp và thiếu index, database vẫn có thể đọc hoặc sắp xếp số lượng hàng lớn. Dùng giới hạn trong SQL và đo execution plan khi cần.

### “`setMaxFieldSize(100)` có nghĩa là 100 ký tự”

Sai. Đơn vị là **byte**, và chỉ áp dụng cho những loại giá trị ký tự/nhị phân cụ thể. Số ký tự Unicode có thể khác số byte.

### “Giới hạn trường sẽ ném lỗi nếu nội dung quá dài”

Không nên dựa vào điều đó. Theo hợp đồng JDBC, dữ liệu dư có thể bị loại bỏ âm thầm. Nếu cần biết dữ liệu gốc có vượt ngưỡng hay không, kiểm tra bằng phép đo/metadata được hỗ trợ hoặc kiểm tra kích thước đầy đủ ở tầng thích hợp.

### “`SELECT *` rồi bỏ các cột không cần ở Java là đủ”

Không tối ưu cho trường lớn: database/driver có thể vẫn tạo và truyền dữ liệu của các cột đó. Ưu tiên `SELECT id, name, status` cho màn hình chỉ dùng các giá trị này.

### “Tăng `maxRows` lên rất lớn giúp streaming hiệu quả hơn”

Sai. Kích thước `maxRows` kiểm soát kết quả tối đa, không quyết định driver có streaming hay không. Với dữ liệu lớn, cần thiết kế luồng/phân trang và kiểm tra `fetchSize` trên driver cụ thể.

### “Có `ORDER BY` nên các trang offset luôn không trùng nhau”

Không hẳn. `ORDER BY` xác định thứ tự ở mỗi lần đọc, nhưng nếu dữ liệu thay đổi giữa các request, trang theo offset có thể lặp hoặc thiếu hàng. Cân nhắc keyset pagination hoặc snapshot phù hợp với yêu cầu.

### “Đặt giới hạn ở JDBC đủ để bảo vệ mọi trường hợp”

Không hẳn. `setMaxFieldSize` không giới hạn mọi kiểu dữ liệu, `setMaxRows` không giới hạn dung lượng một hàng và cả hai không bảo đảm giới hạn tổng byte đầu ra. Kết hợp lựa chọn cột, SQL giới hạn, kiểm soát kích thước đầu ra và lifecycle tài nguyên.

## 12. Quy trình chọn giới hạn trước khi viết truy vấn

1. **Xác định nhu cầu nghiệp vụ:** màn hình cần 20 kết quả, báo cáo cần toàn bộ 30.000 bản ghi hay người dùng cần xem một tệp?
2. **Chọn cột được đọc:** có cần nội dung đầy đủ của `content`, hay chỉ `id`, `title`, `excerpt`?
3. **Giới hạn tại SQL nếu có thể:** thêm `WHERE`, thứ tự `ORDER BY` ổn định, `LIMIT`/`FETCH FIRST`/`TOP` theo database và bind các tham số hợp lệ.
4. **Giới hạn ở API:** validate `pageSize` và đặt trần để request bất thường không khiến hệ thống trả quá nhiều dữ liệu.
5. **Dùng API JDBC bổ sung khi phù hợp:** `setMaxRows` để chặn số hàng của `ResultSet`, `setMaxFieldSize` chỉ khi chấp nhận mất phần dữ liệu, `setFetchSize` khi cần điều chỉnh cách lấy hàng và đã biết điều kiện driver.
6. **Đối với dữ liệu lớn:** cân nhắc phân trang, streaming, stream LOB, giới hạn tổng byte và kiểm soát backpressure.
7. **Đóng tài nguyên đúng lúc:** `ResultSet` → `Statement` → `Connection` bằng `try-with-resources`, kể cả khi đọc bị hủy do vượt giới hạn.
8. **Đo và kiểm tra:** lượng dữ liệu trả về, thời gian SQL, số hàng/byte, bộ nhớ, query plan và tình trạng connection pool trên database thực tế.

### Ví dụ lựa chọn theo tình huống

| Tình huống | Cách phù hợp | Tránh |
|---|---|---|
| Danh sách 20 đơn mới | `SELECT` cột cần thiết + `ORDER BY` + `LIMIT 20` | `SELECT *` toàn bộ đơn rồi cắt `List` |
| Tóm tắt nội dung bài viết | SQL `SUBSTRING`/projection lấy đoạn trích | Dùng `setMaxFieldSize` rồi coi kết quả là nội dung đầy đủ |
| Export một triệu hàng | Streaming/cursor hoặc truy vấn theo lô, giám sát memory/connection | Nạp tất cả vào `List` chỉ để ghi tệp |
| Đọc tệp lớn qua JDBC | `getBinaryStream` và hạn mức byte ứng dụng | `getBytes()` cho tệp không giới hạn |
| Phân trang API | Trần `pageSize`, `ORDER BY`, LIMIT/offset hoặc keyset | Dựa vào `setFetchSize` để phân trang |
| Cập nhật bản ghi cần nội dung nguyên vẹn | Đọc đầy đủ trường cần thiết | Dùng giá trị đã bị `setMaxFieldSize` cắt để ghi lại |

## 13. Câu hỏi tự kiểm tra

1. Một statement đặt `setFetchSize(50)` nhưng truy vấn trả 10.000 hàng. Tối đa bao nhiêu hàng vòng lặp `rs.next()` có thể duyệt nếu không có giới hạn khác?
2. `setMaxRows(100)` khác gì với `LIMIT 100`? Cách nào cho database cơ hội tối ưu trực tiếp ngay trong SQL?
3. `setMaxFieldSize(200)` giới hạn 200 **byte** hay 200 **ký tự**? Điều gì có thể xảy ra với chuỗi tiếng Việt dài?
4. Truy vấn trả 30 hàng đúng bằng `pageSize`. Vì sao chưa thể kết luận có trang tiếp theo, và có thể lấy thêm một hàng để kiểm tra ra sao?
5. Vì sao `SELECT id, title, SUBSTRING(content, 1, 200)` thường phù hợp hơn `SELECT *` cho danh sách tài liệu?
6. `setMaxFieldSize` có bảo đảm giới hạn kích thước dữ liệu `BLOB` không? Khi đọc tệp lớn nên dùng những API và giới hạn nào?
7. Nếu chuyển `LIMIT/OFFSET` từ MySQL sang SQL Server, có thể giữ nguyên câu SQL không?
8. Khi một stream đang ghi tệp vượt hạn mức, vì sao ứng dụng phải xử lý phần tệp đã ghi dở và vẫn đóng các tài nguyên JDBC?

**Ghi nhớ:** giới hạn dữ liệu JDBC là sự kết hợp giữa **số hàng**, **số cột/giá trị** và **cách lấy dữ liệu**. `setMaxRows` giới hạn hàng trong `ResultSet`; `setMaxFieldSize` giới hạn byte cho một số giá trị ký tự/nhị phân và có thể cắt mất dữ liệu; `setFetchSize` chỉ gợi ý kích thước mỗi đợt fetch. Với chức năng hiển thị hoặc phân trang, cách hiệu quả và minh bạch là chọn đúng cột và đặt giới hạn trong SQL, sau đó bổ sung các ràng buộc ở tầng ứng dụng.

### Tài liệu tham khảo chính thức

- [Java SE 21 — `java.sql.Statement` (setMaxRows, setLargeMaxRows, setMaxFieldSize, setFetchSize)](https://docs.oracle.com/en/java/javase/21/docs/api/java.sql/java/sql/Statement.html)
- [Java SE 21 — `java.sql.PreparedStatement`](https://docs.oracle.com/en/java/javase/21/docs/api/java.sql/java/sql/PreparedStatement.html)
- [Java SE 21 — `java.sql.ResultSet` (getBinaryStream, getCharacterStream)](https://docs.oracle.com/en/java/javase/21/docs/api/java.sql/java/sql/ResultSet.html)
- [PostgreSQL — SELECT, LIMIT và OFFSET](https://www.postgresql.org/docs/current/queries-limit.html)
- [MySQL 8.4 — SELECT statement](https://dev.mysql.com/doc/refman/8.4/en/select.html)
- [Microsoft SQL Server — TOP](https://learn.microsoft.com/en-us/sql/t-sql/queries/top-transact-sql)
