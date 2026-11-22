# Đánh giá chi phí bộ nhớ và tính khả chuyển của con trỏ cuộn

> **Chương:** ResultSet nâng cao  
> **Phạm vi:** JDBC chuẩn, `DataSource`, `Connection`, `PreparedStatement` và `ResultSet` trên các hệ quản trị quan hệ. Ví dụ Java sử dụng Java 17+ và JDBC 4.2+.

Một màn hình quản trị cần xem bản ghi thứ 500, quay về bản ghi thứ 20 rồi nhảy đến cuối kết quả. JDBC cung cấp **con trỏ cuộn** (*scrollable result set*) với các thao tác `absolute()`, `relative()`, `previous()`, `first()` và `last()`. Tuy nhiên, nếu truy vấn trả hàng triệu hàng, khả năng nhảy vị trí có thể khiến driver giữ toàn bộ kết quả trong bộ nhớ hoặc buộc database giữ tài nguyên cursor lâu hơn. Hơn nữa, **một loại `ResultSet` được yêu cầu không có nghĩa driver thực sự hỗ trợ hoặc thực hiện giống nhau trên mọi hệ quản trị**.

Bài này giúp trả lời ba câu hỏi thiết kế:

1. **Có thật sự cần cuộn không?** Hay ứng dụng chỉ cần đọc tuần tự, tìm theo khóa hoặc lấy một trang dữ liệu?
2. **Chi phí nằm ở đâu?** Heap Java, bộ đệm của driver, bộ nhớ/server cursor, mạng, thời gian giữ connection, transaction và tài nguyên database?
3. **Có di chuyển được giữa driver/DBMS không?** Khả năng hỗ trợ, kiểu thực tế, hiệu lực sau commit, và khả năng thấy cập nhật đồng thời được xác nhận bằng API và kiểm thử thế nào?

Kết luận định hướng là: **ưu tiên `TYPE_FORWARD_ONLY` cho xử lý tuần tự dữ liệu lớn; chỉ chọn con trỏ cuộn khi yêu cầu điều hướng thật sự cần và đã đo chi phí với driver thực tế**. Đây là nguyên tắc đánh giá, không phải quy tắc cấm dùng con trỏ cuộn.

## 1. Con trỏ `ResultSet` làm việc như thế nào?

Sau khi `executeQuery()`, `ResultSet` có một vị trí logic so với các hàng trong kết quả. Với `ResultSet.TYPE_FORWARD_ONLY`, ứng dụng thường dùng `next()` để đi theo chiều tiến:

```java
try (Connection connection = dataSource.getConnection();
     PreparedStatement statement = connection.prepareStatement(
         "SELECT id, category FROM audit_events ORDER BY id");
     ResultSet rs = statement.executeQuery()) {

    while (rs.next()) {
        long id = rs.getLong("id");
        String category = rs.getString("category");
        // Xử lý từng hàng; không cần quay ngược.
    }
}
```

Con trỏ cuộn mở rộng API di chuyển:

| Phương thức | Công dụng | Điều cần nhớ |
|---|---|---|
| `next()` | Tiến đến hàng tiếp theo | Dùng được với mọi loại result set |
| `previous()` | Quay về hàng trước | Cần result set cuộn |
| `first()` / `last()` | Đến hàng đầu/cuối | `last()` có thể buộc driver duyệt hoặc buffer hết kết quả |
| `beforeFirst()` / `afterLast()` | Đặt trước hàng đầu / sau hàng cuối | Vị trí không chứa hàng để đọc |
| `absolute(n)` | Đến hàng thứ `n`; chỉ số dương tính từ 1, âm tính từ cuối | `absolute(-1)` yêu cầu biết hàng cuối; `absolute(0)` đưa về trước hàng đầu |
| `relative(n)` | Dịch `n` hàng tính từ vị trí hiện tại | `relative(0)` không tự đọc một hàng mới |
| `getRow()` | Trả vị trí hàng hiện tại, bắt đầu từ 1 | Trả `0` khi con trỏ không ở hàng hợp lệ; không đồng nghĩa tổng số hàng |
| `isBeforeFirst()` / `isAfterLast()` | Hỏi vị trí tương đối | Kết quả với tập rỗng cần đọc theo hợp đồng JDBC |
| `isFirst()` / `isLast()` | Hỏi hàng hiện tại có phải đầu/cuối không | Một số driver có thể cần thêm công việc để xác định cuối kết quả |

**Di chuyển con trỏ không phải phân trang SQL.** `rs.absolute(500000)` điều hướng **bên trong tập kết quả mà truy vấn đã tạo**; nó không biến câu `SELECT` thành một truy vấn có điều kiện `WHERE` hoặc `LIMIT` mới. Nếu kết quả ban đầu rất lớn, ứng dụng vẫn có thể phải xử lý chi phí chuyển, lưu hoặc duy trì tập kết quả đó.

## 2. Ba kiểu `ResultSet` trong JDBC

JDBC định nghĩa ba kiểu con trỏ qua các hằng trên `java.sql.ResultSet`:

| Kiểu | Di chuyển | Nhìn thấy thay đổi của giao dịch khác? | Ứng dụng nên kỳ vọng |
|---|---|---|---|
| `TYPE_FORWARD_ONLY` | Chủ yếu `next()` theo chiều tiến | Không đưa ra hợp đồng snapshot/cuộn như hai kiểu dưới | Đơn giản, phù hợp xử lý một lượt; không mặc nhiên bảo đảm streaming không buffer |
| `TYPE_SCROLL_INSENSITIVE` | Có thể đi tới/lui, nhảy vị trí | **Thông thường không phản ánh** thay đổi bên ngoài xảy ra sau khi tạo result set | Hữu ích khi cần đọc lại cùng một tập kết quả tương đối ổn định |
| `TYPE_SCROLL_SENSITIVE` | Có thể đi tới/lui, nhảy vị trí | Có khả năng phản ánh một số thay đổi từ bên ngoài, nhưng mức độ nhìn thấy phụ thuộc hỗ trợ/DBMS/isolation | **Không được giả định** mọi update/insert/delete đồng thời đều hiện ngay |

`TYPE_SCROLL_SENSITIVE` không phải “live data subscription”. Thay đổi từ giao dịch khác có thể không hiển thị vì mức isolation, implementation hoặc giới hạn của driver. Ngay cả khi driver báo hỗ trợ kiểu này, không nên xây dựng logic nghiệp vụ bắt buộc phải thấy mọi thay đổi đồng thời thông qua cursor đang mở. Nếu cần dữ liệu mới nhất, có thể phải thực hiện truy vấn mới hoặc dùng cơ chế sự kiện/phân trang phù hợp.

JDBC còn có **chế độ đồng thời (concurrency)** độc lập với loại cuộn:

- `ResultSet.CONCUR_READ_ONLY`: chỉ đọc; thường phù hợp cho màn hình xem, export và báo cáo.
- `ResultSet.CONCUR_UPDATABLE`: một số driver cho phép cập nhật hàng qua `ResultSet.updateXxx()` và `updateRow()` khi truy vấn/schema đáp ứng điều kiện.

Đừng nhầm `TYPE_SCROLL_SENSITIVE` với `CONCUR_UPDATABLE`. Một result set có thể cuộn nhưng chỉ đọc. Yêu cầu cập nhật qua cursor có thể cần metadata, khóa hoặc điều kiện truy vấn riêng và làm tăng chi phí, vì vậy bài này ưu tiên `CONCUR_READ_ONLY` khi đo ảnh hưởng của **khả năng cuộn**.

## 3. Cách yêu cầu kiểu cursor khi tạo statement

Dùng overload của `Connection.prepareStatement()` với hai tham số loại và concurrency:

```java
String sql = """
    SELECT id, category, description
    FROM audit_events
    ORDER BY id
    """;

try (Connection connection = dataSource.getConnection();
     PreparedStatement statement = connection.prepareStatement(
         sql,
         ResultSet.TYPE_SCROLL_INSENSITIVE,
         ResultSet.CONCUR_READ_ONLY
     );
     ResultSet rs = statement.executeQuery()) {

    System.out.println("Actual type = " + rs.getType());
    System.out.println("Actual concurrency = " + rs.getConcurrency());

    if (rs.getType() != ResultSet.TYPE_SCROLL_INSENSITIVE) {
        throw new SQLException("Requested scroll-insensitive ResultSet unavailable");
    }

    if (rs.absolute(5)) {
        System.out.printf("Row 5: id=%d, category=%s%n",
            rs.getLong("id"), rs.getString("category"));
    }

    if (rs.previous()) {
        System.out.printf("Row 4: id=%d%n", rs.getLong("id"));
    }

    if (rs.last()) {
        System.out.printf("Last row: id=%d; cursor row=%d%n",
            rs.getLong("id"), rs.getRow());
    }

    rs.beforeFirst(); // Có thể lặp lại từ đầu.
    while (rs.next()) {
        // Xử lý từng hàng.
    }
}
```

**Chỉ số hàng khác khóa chính.** `rs.absolute(5)` chọn **hàng thứ năm trong thứ tự kết quả**, không phải hàng có `id = 5`. Nếu có gap trong khóa, hoặc dữ liệu lọc/sắp xếp, `id` và vị trí không trùng nhau.

**Đừng viết mã mặc định tin rằng driver đã chấp nhận yêu cầu.** Với một số driver, một kiểu/concurrency không hỗ trợ có thể khiến `prepareStatement()` ném `SQLException`; trong các trường hợp khác driver có thể trả một cấu hình đã bị giảm cấp và phát `SQLWarning`. Kiểm tra `ResultSet.getType()` và `getConcurrency()` của **kết quả thực tế**, không chỉ của tham số truyền vào.

## 4. Kiểm tra khả năng hỗ trợ trước khi dùng

JDBC cung cấp `DatabaseMetaData` để hỏi khả năng của driver/database:

```java
import java.sql.Connection;
import java.sql.DatabaseMetaData;
import java.sql.ResultSet;
import java.sql.SQLException;

static void printCapabilities(Connection connection) throws SQLException {
    DatabaseMetaData meta = connection.getMetaData();

    int[] types = {
        ResultSet.TYPE_FORWARD_ONLY,
        ResultSet.TYPE_SCROLL_INSENSITIVE,
        ResultSet.TYPE_SCROLL_SENSITIVE
    };

    for (int type : types) {
        boolean typeSupported = meta.supportsResultSetType(type);
        boolean readOnlySupported = typeSupported
            && meta.supportsResultSetConcurrency(
                type, ResultSet.CONCUR_READ_ONLY
            );
        boolean updatableSupported = typeSupported
            && meta.supportsResultSetConcurrency(
                type, ResultSet.CONCUR_UPDATABLE
            );

        System.out.printf(
            "type=%d supported=%s readOnly=%s updatable=%s%n",
            type, typeSupported, readOnlySupported, updatableSupported
        );
    }

    System.out.println("Driver: " + meta.getDriverName()
        + " / " + meta.getDriverVersion());
    System.out.println("DBMS: " + meta.getDatabaseProductName()
        + " / " + meta.getDatabaseProductVersion());
}
```

Kiểm tra kiểu và concurrency **cùng nhau**, vì driver có thể hỗ trợ `TYPE_SCROLL_INSENSITIVE` với `CONCUR_READ_ONLY` nhưng không hỗ trợ kết hợp với `CONCUR_UPDATABLE`.

Các API liên quan khác:

| API | Dùng để kiểm tra |
|---|---|
| `DatabaseMetaData.supportsResultSetType(type)` | Driver/database cho biết có hỗ trợ kiểu cursor hay không |
| `supportsResultSetConcurrency(type, concurrency)` | Khả năng kết hợp type và concurrency |
| `supportsResultSetHoldability(holdability)` | Khả năng giữ cursor qua commit theo chế độ holdability |
| `Connection.getHoldability()` | Giá trị holdability của connection |
| `ResultSet.getHoldability()` | Giá trị thực tế của result set |
| `ResultSet.getType()` / `getConcurrency()` | Loại và concurrency của result set đã tạo |
| `Statement.getWarnings()` / `Connection.getWarnings()` | Có thể chứa cảnh báo điều chỉnh cấu hình hoặc điều kiện khác |

Metadata là **bước sàng lọc**, không phải bảo đảm hiệu năng và đầy đủ mọi hành vi tại runtime. Một driver có thể báo hỗ trợ nhưng thực hiện bằng cách tải cả kết quả vào heap; driver khác có thể giảm cấp khi truy vấn không phù hợp. Sau kiểm tra metadata vẫn phải **tạo result set, xem loại thực tế và chạy bộ kiểm thử con trỏ**.

### Đọc cảnh báo để nhận diện giảm cấp

```java
import java.sql.SQLWarning;

static void reportWarnings(PreparedStatement statement)
        throws SQLException {

    for (SQLWarning warning = statement.getWarnings();
         warning != null;
         warning = warning.getNextWarning()) {

        System.err.printf(
            "JDBC warning: state=%s code=%d message=%s%n",
            warning.getSQLState(),
            warning.getErrorCode(),
            warning.getMessage()
        );
    }
}
```

Không phải driver nào cũng phát warning cho cùng trường hợp. **Không có warning không có nghĩa loại cursor được yêu cầu đã được thực hiện đầy đủ.** Mã sản xuất nên log có kiểm soát, không đưa tham số SQL nhạy cảm vào log.

## 5. Chi phí bộ nhớ: cuộn thường cần giữ trạng thái nhiều hơn

Con trỏ đọc tiến có thể bỏ qua một hàng sau khi xử lý, còn con trỏ cho phép quay lại cần có cách **truy cập lại** hàng cũ. Driver/database có thể hiện thực bằng nhiều chiến lược:

1. **Buffer phía client:** driver giữ các hàng và dữ liệu cột trong heap Java hoặc bộ đệm riêng. Quay lại nhanh nhưng bộ nhớ tăng theo số hàng/cột.
2. **Cursor phía server:** DBMS giữ cursor, snapshot, vùng tạm hoặc trạng thái truy vấn; driver fetch các phần khi cần. Heap Java có thể thấp hơn, nhưng server, mạng và connection có chi phí khác.
3. **Cơ chế hỗn hợp:** driver tải một phần, cache các hàng đã đi qua, giữ metadata và fetch theo khối; một số thao tác như `last()` có thể làm cache phình lên.
4. **Materialization ở database:** query có `ORDER BY`, `DISTINCT` hoặc join lớn có thể phải sort/materialize trên server **ngay cả khi phía Java dùng `TYPE_FORWARD_ONLY`**.

Như vậy, **không thể suy từ tên `TYPE_SCROLL_INSENSITIVE` rằng toàn bộ dữ liệu chắc chắn nằm trong Java heap**, cũng không thể suy từ `TYPE_FORWARD_ONLY` rằng driver thực sự stream mà không buffer. Các khái niệm này là **hợp đồng thao tác JDBC**, không phải đặc tả thuật toán lưu bộ đệm của từng driver.

### Một ước lượng kích thước giúp đặt câu hỏi đúng

Giả sử truy vấn trả **100.000 hàng**, mỗi hàng có khoảng **2 KiB dữ liệu nhị phân**. Riêng payload thô đã cỡ **195 MiB** (100.000 × 2.048 byte), chưa tính đối tượng Java, reference, mảng, giải mã chuỗi, bộ đệm driver và metadata. Nếu ứng dụng tự gom hàng vào `List` hoặc driver materialize toàn bộ, footprint có thể cao hơn đáng kể.

Đây là **ước lượng để nhìn thấy độ lớn**, không phải khẳng định một cấu hình JDBC cụ thể sẽ chiếm chính xác từng ấy heap. Chi phí thực tế còn phụ thuộc số cột, kiểu dữ liệu, dữ liệu nén, định dạng dây truyền và cách driver giữ hàng.

| Quyết định | Nguy cơ chi phí |
|---|---|
| `SELECT *` với các cột `BLOB`/`TEXT` lớn | Tăng byte truyền, bộ nhớ và thời gian materialize |
| `TYPE_SCROLL_INSENSITIVE` rồi `last()` ngay lập tức | Có thể buộc tải toàn bộ hàng để biết cuối tập kết quả |
| Gọi `absolute(-1)` hoặc `isLast()` lặp đi lặp lại | Có thể kích hoạt truy cập/cuộn và fetch không tối ưu |
| `setFetchSize(100)` | Có thể giảm lượng fetch một lần nếu driver hỗ trợ; **không** giới hạn tổng số hàng |
| Đọc `ResultSet` rồi thêm mọi hàng vào `ArrayList` | **Ứng dụng tự materialize** dù result set có stream |
| Giữ cursor mở khi người dùng xem từng trang chậm | Giữ connection, tài nguyên server và có thể giữ transaction lâu |
| Sử dụng `CONCUR_UPDATABLE` không cần thiết | Có thể tạo thêm chi phí metadata/khóa hoặc hạn chế query hỗ trợ |

**Hai chỗ có thể dùng nhiều bộ nhớ độc lập:** buffer do driver quản lý và bộ sưu tập do ứng dụng tự tạo. Khi đo, cần kiểm tra cả hai, không quy toàn bộ tăng heap cho con trỏ cuộn.

## 6. `fetchSize` không đồng nghĩa bảo đảm stream

`Statement.setFetchSize(int rows)` là **gợi ý** số hàng để driver lấy về một lần:

```java
try (Connection connection = dataSource.getConnection();
     PreparedStatement ps = connection.prepareStatement(
         "SELECT id, category FROM audit_events ORDER BY id",
         ResultSet.TYPE_FORWARD_ONLY,
         ResultSet.CONCUR_READ_ONLY
     )) {

    ps.setFetchSize(256);

    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            process(rs.getLong("id"), rs.getString("category"));
        }
    }
}
```

Trong ví dụ này, `process(long, String)` là hàm xử lý của ứng dụng; **không giữ lại toàn bộ các hàng** nếu mục tiêu là streaming.

`ps.getFetchSize()` cho biết kích thước fetch đã được đặt/trả về theo API, **không chứng minh** driver đang lấy đúng 256 hàng mỗi chuyến mạng. Cách stream phụ thuộc driver:

- **PostgreSQL JDBC (pgJDBC):** cursor-based fetching thường cần connection ở `autoCommit=false`, `TYPE_FORWARD_ONLY` và fetch size dương, cùng các điều kiện truy vấn/driver phù hợp. Với `autoCommit=true`, result set có thể được tải toàn bộ bất chấp fetch size. Giữ transaction trong lúc duyệt nhiều hàng làm tăng thời gian chiếm connection và có thể kéo dài snapshot.
- **MySQL Connector/J:** có cơ chế cursor-based fetching qua các tùy chọn driver (chẳng hạn cấu hình `useCursorFetch`) và fetch size dương trong điều kiện phù hợp; còn các chế độ streaming khác có hành vi/hạn chế khác. Không lấy cấu hình từ PostgreSQL áp vào MySQL hoặc ngược lại.
- **Driver khác:** một số không hỗ trợ fetch streaming trong mọi kiểu result set; một số dùng cursor phía server, số khác buffer toàn bộ.

Các chi tiết trên là **điểm cần xác minh với tài liệu và integration test cho phiên bản driver mục tiêu**, không phải hợp đồng chung của JDBC. Với `TYPE_SCROLL_INSENSITIVE`, ngay cả khi `setFetchSize(256)` được chấp nhận, driver vẫn có thể cần materialize cả tập kết quả để hỗ trợ `previous()`/`absolute()`.

**Chú ý transaction:** Không thay đổi `setAutoCommit()` giữa chừng khi đang dùng `ResultSet` mở để thử “bật streaming”; việc đổi trạng thái auto-commit có thể làm kết thúc transaction, đóng cursor hoặc thay đổi ngữ nghĩa truy vấn. Cấu hình trước khi thực thi SQL, và kết thúc đúng transaction sau khi đọc xong.

## 7. Holdability: cursor sống qua `commit()` hay không?

Ngoài type và concurrency, JDBC có thuộc tính **holdability**:

- `ResultSet.CLOSE_CURSORS_AT_COMMIT`: cursor được đóng khi transaction commit theo hợp đồng này.
- `ResultSet.HOLD_CURSORS_OVER_COMMIT`: cursor được giữ qua commit nếu driver/database hỗ trợ.

Có thể yêu cầu holdability bằng overload của `prepareStatement()`:

```java
try (Connection connection = dataSource.getConnection()) {
    DatabaseMetaData meta = connection.getMetaData();

    int holdability = ResultSet.CLOSE_CURSORS_AT_COMMIT;

    if (!meta.supportsResultSetHoldability(holdability)) {
        throw new SQLException("Requested holdability not supported");
    }

    try (PreparedStatement ps = connection.prepareStatement(
             "SELECT id FROM audit_events ORDER BY id",
             ResultSet.TYPE_SCROLL_INSENSITIVE,
             ResultSet.CONCUR_READ_ONLY,
             holdability
         );
         ResultSet rs = ps.executeQuery()) {

        System.out.println("Actual holdability: " + rs.getHoldability());
        // Thực hiện truy vấn trong ranh giới transaction phù hợp.
    }
}
```

Một số triển khai có thể không hỗ trợ kết hợp holdability/scroll type theo yêu cầu. `HOLD_CURSORS_OVER_COMMIT` không miễn phí: cursor giữ qua commit có thể cần lưu dữ liệu hoặc tài nguyên lâu hơn, và **không cam kết** xử lý được mọi thay đổi đồng thời. Không giữ result set mở qua một chuỗi HTTP request của người dùng chỉ vì holdability cho phép: connection pool, tài nguyên database, timeout và độ nhất quán có thể trở thành vấn đề lớn.

Khi ứng dụng tự quản lý transaction, commit/rollback vẫn phải thuộc thành phần sở hữu `Connection`. Một DAO không nên commit chỉ để thử xem cursor còn đọc được hay không khi service đang dùng chung transaction cho nhiều thao tác.

## 8. Ví dụ điều hướng an toàn trên result set cuộn

Để minh họa vị trí con trỏ mà không phụ thuộc vào việc ID liên tục, dùng một bảng được sắp xếp rõ ràng.

### Schema và dữ liệu mẫu

```sql
CREATE TABLE audit_events (
    id BIGINT PRIMARY KEY,
    category VARCHAR(40) NOT NULL,
    description VARCHAR(2048) NOT NULL
);

INSERT INTO audit_events (id, category, description) VALUES
    (10, 'LOGIN', 'Đăng nhập'),
    (20, 'ORDER', 'Tạo đơn hàng'),
    (40, 'PAYMENT', 'Thanh toán'),
    (70, 'ORDER', 'Hủy đơn hàng'),
    (90, 'LOGIN', 'Đăng xuất');
```

Các câu SQL này chỉ dùng các kiểu/biểu thức phổ biến; môi trường triển khai có thể cần điều chỉnh kiểu chuỗi hoặc chính sách mã hóa Unicode.

### Di chuyển và đọc

```java
String sql = """
    SELECT id, category, description
    FROM audit_events
    ORDER BY id
    """;

try (Connection connection = dataSource.getConnection();
     PreparedStatement ps = connection.prepareStatement(
         sql, ResultSet.TYPE_SCROLL_INSENSITIVE,
         ResultSet.CONCUR_READ_ONLY
     );
     ResultSet rs = ps.executeQuery()) {

    if (rs.getType() != ResultSet.TYPE_SCROLL_INSENSITIVE) {
        throw new SQLFeatureNotSupportedException(
            "This example requires scroll-insensitive ResultSet"
        );
    }

    if (rs.absolute(3)) {
        System.out.println(rs.getLong("id")); // 40
        System.out.println(rs.getRow());      // 3
    }

    if (rs.previous()) {
        System.out.println(rs.getLong("id")); // 20
    }

    if (rs.last()) {
        System.out.println(rs.getLong("id")); // 90
    }

    if (rs.absolute(-2)) {
        System.out.println(rs.getLong("id")); // 70
    }

    rs.beforeFirst();
    int visited = 0;

    while (rs.next()) {
        visited++;
    }
    System.out.println("Visited: " + visited); // 5
}
```

Thêm import `java.sql.SQLFeatureNotSupportedException` cho đoạn ví dụ.

**Vì sao có `ORDER BY id`?** Thứ tự hàng của một câu `SELECT` **không có `ORDER BY` không được bảo đảm**. Dùng `absolute(3)` trên một truy vấn thiếu thứ tự rõ ràng sẽ khiến cùng code trả hàng khác nhau giữa các lần chạy hoặc các DBMS. Ngay cả khi có `ORDER BY category`, các hàng trùng `category` chưa có thứ tự ổn định; thêm `id` làm tie-breaker.

Khi kết quả rỗng, các phương thức như `first()`, `last()` và `absolute(1)` có thể trả `false`; không gọi `getLong()` nếu chưa có hàng hợp lệ. Sau `beforeFirst()` hoặc `afterLast()`, cũng không đọc cột khi con trỏ chưa nằm trên một hàng.

## 9. Cách viết mã có fallback thay vì phụ thuộc tuyệt đối vào cursor cuộn

Một thư viện DAO dùng trên nhiều DBMS nên biết chính xác **khả năng nào là bắt buộc** và có chiến lược thay thế khi con trỏ cuộn không được hỗ trợ.

Ví dụ cùng câu `SELECT`, nhưng **chỉ cuộn nếu metadata cho phép và type thực tế đúng**, nếu không xử lý tuần tự:

```java
import java.sql.Connection;
import java.sql.DatabaseMetaData;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import javax.sql.DataSource;

static void inspectEvents(DataSource dataSource) throws SQLException {
    String sql = """
        SELECT id, category
        FROM audit_events
        ORDER BY id
        """;

    try (Connection connection = dataSource.getConnection()) {
        DatabaseMetaData meta = connection.getMetaData();

        boolean canRequestScroll =
            meta.supportsResultSetType(
                ResultSet.TYPE_SCROLL_INSENSITIVE
            ) &&
            meta.supportsResultSetConcurrency(
                ResultSet.TYPE_SCROLL_INSENSITIVE,
                ResultSet.CONCUR_READ_ONLY
            );

        int requestedType = canRequestScroll
            ? ResultSet.TYPE_SCROLL_INSENSITIVE
            : ResultSet.TYPE_FORWARD_ONLY;

        try (PreparedStatement ps = connection.prepareStatement(
                 sql, requestedType, ResultSet.CONCUR_READ_ONLY
             );
             ResultSet rs = ps.executeQuery()) {

            if (rs.getType() == ResultSet.TYPE_SCROLL_INSENSITIVE) {
                if (rs.last()) {
                    System.out.println(
                        "Last event ID: " + rs.getLong("id")
                    );
                }
                rs.beforeFirst();
            } else {
                System.out.println(
                    "Scrollable ResultSet unavailable; scanning forward"
                );
            }

            while (rs.next()) {
                System.out.printf("%d %s%n",
                    rs.getLong("id"),
                    rs.getString("category"));
            }
        }
    }
}
```

Bản này có **graceful degradation khi driver trả kiểu khác với kiểu đã yêu cầu**. Tuy nhiên, nếu `prepareStatement(...)` **ném lỗi ngay khi yêu cầu scroll**, nó chưa tự retry; đó là chủ ý để **không nuốt mọi lỗi SQL**. Với một API thư viện thực tế, có thể bắt **riêng** `SQLFeatureNotSupportedException` hoặc mã lỗi đã được driver xác nhận là “unsupported feature”, đóng statement/connection liên quan rồi chuẩn bị lại câu SQL với `TYPE_FORWARD_ONLY`. Không catch mọi `SQLException` để fallback vì một lỗi mạng, quyền truy cập hoặc cú pháp SQL không phải thiếu tính năng cuộn.

Nếu chức năng nghiệp vụ thật sự cần “đến bản ghi thứ 500” chứ không chỉ chạy một vòng `next()`, fallback forward-only có thể dùng **SQL paging** để lấy trang chứa bản ghi đó, không cần tải toàn bộ kết quả vào Java.

## 10. Thay cuộn bằng keyset pagination khi dữ liệu lớn

Nhu cầu “đến trang kế tiếp” khác với nhu cầu “giữ cả tập kết quả và có thể nhảy mọi vị trí”. Khi truy vấn kết quả lớn, phân trang ở SQL thường phù hợp hơn.

### 10.1. Lấy trang sau bằng khóa ổn định

Ví dụ cú pháp `LIMIT` của **PostgreSQL/MySQL**:

```sql
SELECT id, category, description
FROM audit_events
WHERE id > ?
ORDER BY id
LIMIT ?;
```

Lưu `lastSeenId` là ID cuối của trang trước; ở lần kế tiếp bind cùng ID vào dấu `?` đầu và page size vào dấu `?` thứ hai. Không giữ `ResultSet` hay connection mở giữa các request; mỗi trang là một truy vấn ngắn.

Mẫu Java:

```java
record AuditEvent(long id, String category, String description) {}

static List<AuditEvent> nextPage(
        DataSource dataSource, long lastSeenId, int pageSize
) throws SQLException {

    if (pageSize < 1 || pageSize > 500) {
        throw new IllegalArgumentException("Invalid pageSize");
    }

    String sql = """
        SELECT id, category, description
        FROM audit_events
        WHERE id > ?
        ORDER BY id
        LIMIT ?
        """;

    try (Connection connection = dataSource.getConnection();
         PreparedStatement ps = connection.prepareStatement(
             sql, ResultSet.TYPE_FORWARD_ONLY,
             ResultSet.CONCUR_READ_ONLY
         )) {

        ps.setLong(1, lastSeenId);
        ps.setInt(2, pageSize);

        try (ResultSet rs = ps.executeQuery()) {
            List<AuditEvent> page = new ArrayList<>(pageSize);

            while (rs.next()) {
                page.add(new AuditEvent(
                    rs.getLong("id"),
                    rs.getString("category"),
                    rs.getString("description")
                ));
            }
            return page;
        }
    }
}
```

Import thêm `java.util.ArrayList`, `java.util.List` và các lớp `java.sql`/`javax.sql.DataSource` như đã dùng trong ví dụ.

**Tính đúng đắn:** `id` phải có thứ tự ổn định và duy nhất; phân trang theo `category` cần một tie-breaker như `(category, id)`, với điều kiện keyset tương ứng. Khi dữ liệu có chèn/xóa/cập nhật trong lúc duyệt nhiều trang, các trang có thể phản ánh các thời điểm khác nhau. Muốn xuất một snapshot nhất quán, phải xác định isolation, snapshot hoặc watermark theo DBMS và yêu cầu nghiệp vụ. Không mặc định keyset pagination là một phép “đọc đúng một snapshot” khi mỗi trang dùng transaction mới.

### 10.2. Giới hạn của `OFFSET` và keyset

`LIMIT ? OFFSET ?` dễ dùng để “nhảy đến trang 50”, nhưng offset lớn có thể buộc database xử lý/bỏ qua nhiều hàng trước đó và trở nên kém hiệu quả. Keyset thường hiệu quả cho “trang kế tiếp” khi cột sắp xếp có chỉ mục và dữ liệu lớn. Ngược lại, keyset **không tự đáp ứng việc nhảy tới số trang tùy ý** nếu không có mốc khóa hoặc cấu trúc hỗ trợ.

Đừng nhầm:

- `rs.absolute(n)`: di chuyển trong kết quả đã lấy/mở.
- `LIMIT/OFFSET`: yêu cầu database chỉ trả một phần tập kết quả theo thứ tự xác định.
- **Keyset**: truy vấn trang tiếp theo theo khóa cuối đã thấy.

Việc chọn cách nào phụ thuộc trải nghiệm sản phẩm, lượng dữ liệu, yêu cầu snapshot, khả năng nhảy trang ngẫu nhiên và chỉ mục trên database.

## 11. Không dùng `last()` để đếm hàng khổng lồ

Một mẹo thường thấy với con trỏ cuộn:

```java
rs.last();
int totalRows = rs.getRow();
rs.beforeFirst();
```

Cách này có thể dùng cho kết quả nhỏ nếu cursor thực sự cuộn, nhưng **không phù hợp làm chiến lược mặc định để đếm hàng triệu bản ghi**:

- `last()` có thể buộc driver đọc/materialize toàn bộ kết quả hoặc yêu cầu nhiều tương tác với server.
- `getRow()` dùng `int` để biểu thị vị trí; về mặt API nó không phải một cơ chế tổng hợp `COUNT(*)` độc lập, và dữ liệu quá lớn có thể vượt giới hạn có ý nghĩa.
- Sau `beforeFirst()`, bạn tiếp tục duyệt các hàng đã đọc để xử lý; có thể vừa mất chi phí tải toàn bộ vừa giữ kết quả lâu.

Nếu giao diện cần đếm số hàng theo filter, cân nhắc truy vấn `SELECT COUNT(*) ...` riêng:

```sql
SELECT COUNT(*)
FROM audit_events
WHERE category = ?;
```

Nhưng đếm ở database cũng có chi phí với filter phức tạp, có thể phản ánh snapshot khác với trang dữ liệu nếu không cùng isolation/transaction, và không nhất thiết cần thiết cho UI. Nhiều giao diện chỉ cần nút “Xem thêm” thay vì tổng số trang chính xác.

## 12. Thiết kế thí nghiệm đo heap và chi phí thực tế

Đừng đưa ra kết luận từ một dòng cấu hình như `TYPE_SCROLL_INSENSITIVE` hay `setFetchSize(100)`. **Phải đo và so sánh trên cùng dữ liệu, cùng driver, cùng DBMS và cùng môi trường**.

### 12.1. Bộ kịch bản đề xuất

Tạo dữ liệu thử có cỡ hàng giống dữ liệu production (ví dụ 10.000, 100.000 và 1.000.000 hàng). Chọn các truy vấn chứa cột nhỏ và cột lớn:

| Kịch bản | Cách đọc | Mục tiêu |
|---|---|---|
| A — `TYPE_FORWARD_ONLY`, fetch size mặc định | `while (rs.next())`, không lưu toàn bộ hàng | Baseline của driver |
| B — `TYPE_FORWARD_ONLY`, fetch size dương và cấu hình streaming đúng driver | Duyệt một lượt | Đo tác động của fetch size/cursor server |
| C — `TYPE_SCROLL_INSENSITIVE`, duyệt một lượt | `while (rs.next())` | Đo chi phí chỉ vì khả năng cuộn |
| D — `TYPE_SCROLL_INSENSITIVE`, nhảy đến cuối rồi quay về | `last()`, `beforeFirst()`, duyệt | Đo chi phí điều hướng/khả năng materialize |
| E — SQL keyset, trang cố định | Mỗi trang truy vấn riêng, đóng tài nguyên | Đánh giá phương án không giữ cursor lâu |
| F — `TYPE_SCROLL_SENSITIVE` (nếu hỗ trợ) | Cuộn và thử thay đổi đồng thời | Đo độ nhạy/độ khả chuyển, không giả định tính năng luôn có |

**Đảm bảo so sánh công bằng:** các kịch bản A/B/C cùng truy vấn và cùng xử lý số hàng; D có một thao tác bổ sung và phải được báo là phép đo **một trải nghiệm khác** (nhảy cuối rồi duyệt). Không kết luận kiểu cursor “chậm hơn X%” nếu đã thay đổi đồng thời SQL, chỉ mục, số cột hoặc tập dữ liệu.

### 12.2. Những chỉ số cần lấy

- **Thời gian:** lúc bắt đầu `executeQuery()`, thời điểm đọc hàng đầu, thời điểm đọc hàng cuối, thời gian `close()`, và tổng thời gian use case.
- **Bộ nhớ Java:** peak heap/RSS, object allocations và GC pause; với `TYPE_SCROLL_INSENSITIVE`, xem bộ nhớ tăng ở `executeQuery()` hay tăng dần trong vòng `next()`.
- **Tài nguyên database:** session/cursor mở, bộ nhớ cấp cho query, temporary files, sort, transaction age, snapshot và lock duration nếu có.
- **Mạng:** số byte truyền, số chuyến round-trip hoặc thời gian chờ mạng, khả năng fetch theo khối.
- **Connection pool:** thời gian giữ connection và số request phải chờ connection.
- **Tính đúng đắn:** số hàng và thứ tự trả về, hành vi `previous()/absolute()`, khả năng thấy thay đổi đồng thời.

### 12.3. Khung đo thời gian, không tự gom dữ liệu

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import javax.sql.DataSource;

record ScanStats(long rows, long elapsedNanos) {}

static ScanStats scan(
        DataSource dataSource,
        int resultSetType,
        int fetchSize
) throws SQLException {

    long start = System.nanoTime();
    long rows = 0;

    String sql = """
        SELECT id, category, description
        FROM audit_events
        ORDER BY id
        """;

    try (Connection connection = dataSource.getConnection();
         PreparedStatement ps = connection.prepareStatement(
             sql, resultSetType, ResultSet.CONCUR_READ_ONLY
         )) {

        ps.setFetchSize(fetchSize);

        try (ResultSet rs = ps.executeQuery()) {
            System.out.printf(
                "requested=%d actual=%d fetch=%d%n",
                resultSetType, rs.getType(), ps.getFetchSize()
            );

            while (rs.next()) {
                // Đọc dữ liệu đủ để mô phỏng workload thực tế.
                rs.getLong("id");
                rs.getString("category");
                rs.getString("description");
                rows++;
            }
        }
    }

    return new ScanStats(rows, System.nanoTime() - start);
}
```

Ví dụ so sánh:

```java
ScanStats forward = scan(
    dataSource, ResultSet.TYPE_FORWARD_ONLY, 256
);
ScanStats scroll = scan(
    dataSource, ResultSet.TYPE_SCROLL_INSENSITIVE, 256
);

System.out.println("Forward: " + forward);
System.out.println("Scroll: " + scroll);
```

**Giới hạn của khung trên:**

1. `System.nanoTime()` chỉ đo thời gian, **không đo heap hoặc peak memory**. Dùng Java Flight Recorder (JFR), profiler hoặc metric JVM/server phù hợp để đo cấp phát/GC và RSS.
2. Chỉ chạy một lượt không đủ để kết luận: cần warm-up, nhiều lần đo, kiểm soát cache, GC, JIT và thứ tự chạy.
3. `ps.setFetchSize(256)` **không bảo đảm** streaming thực tế; phải kiểm tra tài liệu và cấu hình driver.
4. Nếu driver không hỗ trợ kiểu cuộn, test cần ghi nhận unsupported/downgrade thay vì so sánh số đo như thể hai kiểu đã được thực thi.
5. `getString()` có thể cấp phát String; nếu giữ lại các String trong một List, bạn đang đo cả bộ nhớ của **ứng dụng** chứ không chỉ buffer driver.
6. Đo `last()/absolute()` trong một case riêng vì chúng có thể làm phát sinh fetch hoặc materialization mà vòng duyệt tuần tự không cần.

## 13. Kiểm thử tính khả chuyển giữa driver/DBMS

Tính khả chuyển không chỉ là SQL có chạy hay không. Cần kiểm thử các hợp đồng cursor cụ thể:

| Tiêu chí | Bài test | Câu hỏi khi không đạt |
|---|---|---|
| Tạo `TYPE_SCROLL_INSENSITIVE` | `supportsResultSetType` rồi `prepareStatement(...)` | Driver không hỗ trợ hay không hỗ trợ tổ hợp concurrency? |
| Kiểu thực tế | `rs.getType()` và `rs.getConcurrency()` | Driver có giảm cấp dù API request hợp lệ không? |
| Di chuyển | `first()`, `absolute(3)`, `previous()`, `last()`, `beforeFirst()` | Trả `boolean`, vị trí và dữ liệu đúng trên tập mẫu không? |
| Kết quả rỗng | Thử `first()`, `last()`, `absolute(1)` | Code có đọc cột khi con trỏ không ở hàng hợp lệ không? |
| `TYPE_SCROLL_SENSITIVE` | Mở cursor, transaction thứ hai `UPDATE` rồi commit | Thay đổi có hiện ra không và trong isolation nào? |
| Fetch size | Duyệt dataset lớn ở nhiều giá trị `fetchSize` | Heap/latency/server cursor thay đổi thực tế không? |
| Holdability | Kiểm tra metadata, tạo cursor theo chế độ và thực hiện commit | Cursor có đóng/giữ như hợp đồng không? |
| Nhiều kết quả/statement | Mở thêm statement trên cùng connection | Driver có hạn chế việc đọc kết quả song song không? |
| Hủy giữa chừng | Đóng result set hoặc client timeout | Connection có trả về pool, cursor server có giải phóng không? |
| Khối lượng lớn | 100.000+ hàng, payload lớn | Có vượt heap, timeout hoặc chiếm tài nguyên DB quá lâu không? |

**Khi thử sensitive cursor:** thay đổi hàng từ một connection thứ hai và commit, sau đó trên result set đang mở đọc lại hàng liên quan. Ghi rõ isolation và cấu hình driver; không suy ra có bug nếu một thay đổi không được nhìn thấy vì DBMS/driver có thể không bảo đảm sensitivity đầy đủ hoặc transaction snapshot đang giữ dữ liệu cũ.

**Khi thử holdability:** không làm thí nghiệm `commit()` trên connection đang thuộc giao dịch service thực tế. Tạo connection riêng cho test; kiểm tra `Connection.getHoldability()`, `ResultSet.getHoldability()`, trạng thái cursor trước/sau commit và đóng tài nguyên đúng cách.

## 14. Tránh các lỗi thiết kế thường gặp

| Sai lầm | Hậu quả có thể gặp | Giải pháp |
|---|---|---|
| “`TYPE_FORWARD_ONLY` chắc chắn không tốn RAM” | Driver vẫn có thể buffer toàn bộ hàng | Đo heap, xác nhận streaming behavior của driver |
| “`TYPE_SCROLL_INSENSITIVE` chắc chắn buffer ở client” | Có thể thực hiện bằng cursor/cache phía server | Đo cả client và DBMS; không suy diễn từ tên kiểu |
| Yêu cầu scroll type rồi dùng `absolute()` ngay | Có thể bị downgrade hoặc unsupported | Kiểm tra metadata, kiểu thực tế và xử lý fallback |
| `SELECT *` rồi `last()` để biết tổng số hàng | Có thể tải rất nhiều dữ liệu vô ích | Chỉ lấy cột cần dùng, `COUNT(*)`/paging khi thật sự cần |
| Tin rằng `TYPE_SCROLL_SENSITIVE` phản ánh mọi thay đổi realtime | Hiển thị dữ liệu không đồng nhất kỳ vọng | Xác minh sensitivity, isolation; query lại khi cần |
| Lấy `fetchSize` làm giới hạn số hàng | Vẫn có thể trả triệu hàng | Dùng `LIMIT`/paging hoặc giới hạn nghiệp vụ |
| Dùng `absolute(500000)` để tối ưu phân trang | Có thể đã tải/giữ tập kết quả khổng lồ | Chuyển sang SQL paging/keyset |
| Giữ `ResultSet` sống giữa các HTTP request | Cạn pool, stale data, cursor timeout | Đóng mỗi request; lưu bookmark/keyset |
| DAO đóng connection được service cho mượn | Transaction nhiều DAO bị hỏng | Service sở hữu connection, DAO chỉ đóng statement/result set |
| Quên `ORDER BY` khi kiểm thử `absolute(n)` | Thứ tự dữ liệu thay đổi giữa lần chạy | Xác định thứ tự bằng khóa và tie-breaker |
| Dùng `CONCUR_UPDATABLE` khi chỉ đọc | Tăng hạn chế query và chi phí không cần thiết | Dùng `CONCUR_READ_ONLY` |
| Gọi `rs.getRow()` như “tổng hàng” ở bất kỳ vị trí nào | Sai ngữ nghĩa vị trí cursor | `getRow()` là hàng hiện tại; đếm bằng giải pháp phù hợp |

## 15. Bài thực hành

1. **Kiểm tra năng lực driver:** in `DatabaseMetaData` cho ba kiểu `ResultSet` và hai concurrency; ghi lại tên/phiên bản JDBC driver và DBMS. Tạo cursor scroll-insensitive, xác minh `getType()`/`getConcurrency()` thực tế.
2. **Thực hành vị trí:** tạo năm hàng `audit_events` như mục 8; dùng `absolute(3)`, `previous()`, `last()`, `absolute(-2)` và `beforeFirst()`. Giải thích vì sao `absolute(3)` trả `id = 40` thay vì `id = 3`.
3. **Bẫy thứ tự:** bỏ `ORDER BY`, chạy lại test trên dữ liệu khác và giải thích vì sao ứng dụng không được dựa vào thứ tự nhìn thấy tình cờ.
4. **Fallback:** điều chỉnh `inspectEvents()` để bắt riêng lỗi *feature unsupported* ở giai đoạn tạo statement và chạy forward-only, đồng thời vẫn ném lại các lỗi mạng/SQL khác.
5. **So sánh bộ nhớ:** tạo dataset khoảng 100.000 hàng với description lớn. Đo `TYPE_FORWARD_ONLY` và `TYPE_SCROLL_INSENSITIVE` trong cùng điều kiện; dùng JFR hoặc profiler để quan sát peak heap và allocation.
6. **Chi phí nhảy cuối:** trên scroll-insensitive, so sánh thời gian và bộ nhớ khi duyệt tuần tự với khi gọi `last()` trước rồi `beforeFirst()`. Thảo luận ảnh hưởng của materialization.
7. **Kiểm tra `fetchSize`:** chạy với `0`, `100` và `1000` theo driver mục tiêu; ghi nhận liệu heap, độ trễ hàng đầu, băng thông và thời gian giữ connection có thay đổi không. Không mặc định `0` có cùng nghĩa thực thi ở mọi driver.
8. **Holdability và commit:** kiểm tra `supportsResultSetHoldability()` rồi chạy test commit trên connection thử nghiệm; xác minh con trỏ còn đọc được hay đã đóng.
9. **Sensitive cursor:** nếu driver hỗ trợ, mở `TYPE_SCROLL_SENSITIVE` và cập nhật một hàng từ connection khác. Đo khả năng nhìn thấy thay đổi với isolation được khai báo, không mặc định mọi thay đổi đều phải hiện.
10. **Thiết kế phân trang:** thay thao tác `absolute(500000)` bằng truy vấn keyset `WHERE id > ? ORDER BY id LIMIT ?`; phân tích ưu/nhược khi cần nhảy ngẫu nhiên, bảo toàn thứ tự và dữ liệu đang thay đổi.

### Checklist quyết định trước khi chọn cursor cuộn

- **Yêu cầu:** người dùng có thực sự phải quay lui/nhảy trong **cùng một tập kết quả đã mở**, hay chỉ cần trang tiếp theo?
- **Dữ liệu:** số hàng tối đa và kích thước mỗi hàng đã được giới hạn/đo chưa?
- **Driver:** có hỗ trợ chính xác type, concurrency và holdability yêu cầu không? `ResultSet.getType()` trả gì?
- **Bộ nhớ:** đã đo peak heap, memory driver/database và sự thay đổi khi gọi `last()` chưa?
- **Vòng đời:** cursor và connection đóng trong một request/use case hay bị giữ lâu qua mạng người dùng?
- **Tính đúng đắn:** có `ORDER BY` đủ tie-breaker, xử lý kết quả rỗng và isolation phù hợp không?
- **Fallback:** nếu scroll không khả dụng, có thể dùng forward-only, `LIMIT/OFFSET`, keyset hoặc truy vấn theo ID không?
- **Kiểm thử:** có chạy integration test trên từng driver/DBMS thực mà sản phẩm hỗ trợ không?

**Tiêu chí hoàn thành:** người học phân biệt đúng các loại `ResultSet` và API di chuyển con trỏ; biết chi phí bộ nhớ có thể nằm ở client lẫn database; kiểm tra hỗ trợ thực tế qua `DatabaseMetaData`, `getType()`, `getConcurrency()` và holdability; không nhầm `fetchSize` với giới hạn dữ liệu; và thiết kế được phép đo, test tính khả chuyển cùng phương án thay thế bằng truy vấn phân trang khi xử lý tập kết quả lớn.
