# Quản lý `PreparedStatement` cache và giới hạn tài nguyên trong pool kết nối JDBC

Trong ứng dụng Java dùng JDBC, một truy vấn có tham số thường được thực hiện qua `PreparedStatement`: tạo statement từ SQL có dấu `?`, gán tham số, gọi `executeQuery()` hoặc `executeUpdate()`, rồi đóng statement. Khi cùng một mẫu SQL được lặp lại hàng nghìn lần, việc chuẩn bị câu lệnh có thể tạo thêm chi phí phân tích SQL, trao đổi với server hoặc cấp phát đối tượng. Một số **JDBC driver** và **connection pool** cung cấp *prepared-statement cache* để tái sử dụng một phần công việc chuẩn bị đó.

Nhưng cache không miễn phí. Mỗi mục có thể giữ metadata, bộ nhớ phía driver, một handle phía database hoặc tài nguyên liên quan tới phiên kết nối. Nếu pool có nhiều kết nối và mỗi kết nối giữ một cache lớn, tổng mức tiêu thụ tài nguyên có thể tăng rất nhanh. Vì vậy, câu hỏi đúng không chỉ là **“có bật cache không?”** mà còn là **“cache ở tầng nào, bao nhiêu mục, theo kết nối nào, và khi nào tài nguyên được giải phóng?”**.

Bài thuộc chương **Pool kết nối** của module **JDBC**, tập trung vào quản lý cache dành cho `PreparedStatement` và giới hạn tài nguyên. Các ví dụ dùng API chuẩn `DataSource`, `Connection`, `PreparedStatement`, `ResultSet`, `SQLException` và SQL tham số hóa; tên tùy chọn cache cụ thể cần tra theo driver/pool được triển khai, không phải API JDBC thống nhất.

Sau bài học, bạn có thể:

- Phân biệt cache tại **driver**, **connection pool** và **database server**.
- Hiểu vì sao statement thường gắn với **kết nối vật lý**, không thể chia sẻ tùy ý giữa các request.
- Viết code JDBC đóng statement đúng cách ngay cả khi cache đang bật.
- Tính ngân sách tài nguyên dựa trên số kết nối, sức chứa cache và số instance ứng dụng.
- Giảm số mẫu SQL khác nhau để cải thiện khả năng tái sử dụng mà vẫn an toàn trước SQL injection.
- Theo dõi cache hit/miss, số kết nối, tài nguyên DB và phát hiện rò rỉ thực tế.
- Lựa chọn cấu hình, phép kiểm thử và phương án xử lý khi cache gây lỗi hoặc không có lợi ích.

## 1. Vì sao cùng một câu SQL lại cần chuẩn bị nhiều lần?

Xét một truy vấn gọi nhiều lần:

```sql
SELECT account_id, display_name, active
FROM customer_account
WHERE account_id = ?;
```

Ở lời gọi thứ nhất, ứng dụng gán `account_id = 10`; lời gọi tiếp theo gán `account_id = 20`. **Cấu trúc SQL giống nhau**, chỉ khác giá trị truyền qua placeholder.

```text
Request A                          Request B
   |                                  |
setLong(1, 10)                   setLong(1, 20)
   |                                  |
PreparedStatement                PreparedStatement
   |                                  |
   +------- Cùng SQL template --------+
                      |
             Driver / pool / DB
                      |
              Có thể tái sử dụng
              công việc chuẩn bị
```

Tùy hệ thống, quá trình chuẩn bị có thể bao gồm phân tích cú pháp, mô tả tham số, tạo handle câu lệnh trên server hoặc chọn kế hoạch thực thi. **Không phải mọi lời gọi `prepareStatement()` đều tạo một prepared statement trên server**, và cache không bảo đảm một kế hoạch truy vấn sẽ được tái dùng vĩnh viễn: driver có thể chuẩn bị ở client, DB có thể tự dùng plan cache, hoặc kế hoạch có thể bị hủy khi schema hay điều kiện thực thi thay đổi.

`PreparedStatement` trước hết là công cụ **tham số hóa và thực thi SQL an toàn**. Cache là một tối ưu hóa tùy chọn; câu SQL vẫn phải chạy đúng khi cache tắt hoặc không được hỗ trợ.

### Dấu hiệu workload phù hợp với cache

| Đặc điểm workload | Ý nghĩa với cache |
| --- | --- |
| Lặp lại ít mẫu SQL với các bộ tham số khác nhau | Có khả năng tái sử dụng cao |
| Mỗi request tạo câu SQL hoàn toàn khác | Dễ cache miss và làm nhiều mục cũ bị đẩy ra |
| Truy vấn có thời gian chạy rất dài | Chi phí prepare có thể nhỏ so với chi phí thực thi |
| Nhiều truy vấn ngắn được gọi liên tục | Overhead của prepare có thể đáng kể; cần đo |
| Nhiều kết nối vật lý trong pool | Mỗi kết nối có thể cần chuẩn bị/cache riêng cùng một mẫu SQL |
| DB giới hạn số statement/handle trên session | Cache lớn có thể gây cạn tài nguyên dù ứng dụng ít request |

Không nên bật cache chỉ vì “mọi ứng dụng JDBC đều cần”. Nếu driver và server đã tối ưu việc chuẩn bị đủ tốt, lợi ích thêm của cache tại pool có thể thấp hơn chi phí bộ nhớ và độ phức tạp vận hành.

## 2. Ba tầng dễ bị nhầm là cùng một cache

Khái niệm *prepared-statement cache* có thể chỉ những cơ chế rất khác nhau:

| Tầng | Có thể cache cái gì? | Phạm vi thường gặp | Ai cấu hình? |
| --- | --- | --- | --- |
| **JDBC driver** | Thông tin phân tích SQL, metadata tham số, handle prepared statement theo kết nối | Thường theo kết nối vật lý; phụ thuộc driver | Thuộc tính driver hoặc `DataSource` của driver |
| **Connection pool** | Wrapper hoặc statement được trả về để tái sử dụng, nếu pool có tính năng đó | Thường gắn với một kết nối vật lý trong pool | Cấu hình pool, nếu được hỗ trợ |
| **Database server** | Prepared statement thuộc session, parsed statement hoặc execution plan | Có thể theo session, database hay cache kế hoạch chung tùy DB | Cấu hình DB và giao thức driver |

**Đừng đồng nhất ba tầng này.** Một driver có thể cache prepared handle nhưng pool không có statement cache; một DB có plan cache ngay cả khi ứng dụng không bật prepared-statement cache; một pool có thể cache các object phía Java mà server không giữ handle tương ứng.

```text
Ứng dụng Java
    |
    | DataSource.getConnection()
    v
Connection pool
    |   physical connection #1 ---- Driver cache #1 ---- DB session #1
    |   physical connection #2 ---- Driver cache #2 ---- DB session #2
    |   physical connection #3 ---- Driver cache #3 ---- DB session #3
    |
    v
Ứng dụng mượn logical Connection
    |
    +-- prepareStatement(SQL) -> dùng lại nếu cơ chế hỗ trợ
    +-- statement.close()     -> giải phóng hoặc đưa về cache
    +-- connection.close()    -> trả kết nối về pool
```

Sơ đồ chỉ diễn tả **mô hình thường gặp**, không mô tả chính xác mọi sản phẩm. Có pool không triển khai cache statement; có driver dùng cache phạm vi khác; có DB chia sẻ plan giữa nhiều session. Phải xác định thành phần nào **thực sự** được bật trong hệ thống trước khi đo hoặc thay đổi cấu hình.

### `Connection.close()` và `PreparedStatement.close()` có còn ý nghĩa không?

**Có.** Theo hợp đồng JDBC, code ứng dụng phải đóng những tài nguyên mà nó sở hữu. Khi dùng pool, `Connection.close()` trên kết nối logic thường trả kết nối vật lý về pool thay vì đóng socket ngay. Khi dùng statement cache, `PreparedStatement.close()` có thể giúp driver/pool trả statement đủ điều kiện vào cache, hoặc thực sự đóng tài nguyên nếu không cache.

Ứng dụng **không được dựa vào hành vi nội bộ** để bỏ `close()`. Việc không đóng `PreparedStatement` có thể làm statement vẫn đang được mượn, giữ `ResultSet`/cursor mở hoặc làm cạn giới hạn tài nguyên. Cache không phải công cụ sửa lỗi leak.

## 3. Cache thường gắn với kết nối vật lý

Trong nhiều DB và driver, prepared statement hoặc handle phía server thuộc **một session/kết nối vật lý**. Nếu pool có ba kết nối vật lý và cả ba cùng thực thi SQL giống nhau, mỗi kết nối có thể chuẩn bị hoặc cache một phiên bản riêng của SQL đó. Không thể mặc định một statement tạo ở kết nối A sẽ tái sử dụng được ở kết nối B.

Ví dụ:

```text
Pool size = 3

Connection A: cache [SELECT by id, UPDATE status]
Connection B: cache [SELECT by id]
Connection C: cache [SELECT by email, INSERT account]

Tổng số mục đang giữ = 2 + 1 + 2 = 5
```

Các mục không nhất thiết được phân phối đều. Một request chỉ đến kết nối B có thể cache miss dù SQL ấy đã nằm trong cache của kết nối A. Tương tự, khi một kết nối vật lý bị pool loại bỏ vì hết vòng đời, lỗi mạng hoặc thay đổi cấu hình, những mục cache gắn với kết nối đó thường mất hiệu lực và phải được chuẩn bị lại trên kết nối mới.

**Hệ quả thiết kế:** không lưu `PreparedStatement` làm trường tĩnh (`static`) hoặc singleton để dùng chung giữa các thread. Nó gắn với `Connection`, giữ trạng thái tham số và kết quả, không có bảo đảm dùng đồng thời an toàn. Một `DataSource`/pool có thể được chia sẻ cho nhiều request; **statement được tạo và đóng trong phạm vi thao tác hoặc một lần mượn kết nối**.

### Cache khác với tái sử dụng thủ công trong một phương thức

Tái sử dụng thủ công:

```java
try (Connection connection = dataSource.getConnection();
     PreparedStatement statement = connection.prepareStatement(SQL)) {

    for (long id : ids) {
        statement.setLong(1, id);
        try (ResultSet rs = statement.executeQuery()) {
            // Đọc xong ResultSet trước khi đổi tham số và thực thi tiếp.
        }
    }
}
```

Trong ví dụ này, một đối tượng `PreparedStatement` được dùng lại **trong một lần mượn kết nối**. Đây là tối ưu hóa hợp lệ ngay cả khi cache bị tắt. Còn *statement cache* ở driver/pool thường liên quan tới việc **một lần gọi sau** có thể tạo statement từ cùng SQL và tái sử dụng công việc chuẩn bị khi statement cũ đã đóng hoặc được trả về cache.

Không nên giữ statement sống trong một service chỉ để tránh gọi `prepareStatement()` ở request sau. Làm vậy kéo dài quyền sở hữu kết nối, khó kiểm soát đồng thời và phá vỡ mô hình trả kết nối về pool.

## 4. Mẫu SQL ổn định quyết định tỷ lệ cache hit

Cache thường nhận diện mục từ SQL đã chuẩn bị và các thuộc tính liên quan. **Giá trị tham số không phải lý do để tạo một SQL template mới**.

```java
// NÊN: SQL cố định, dữ liệu được bind qua placeholder.
String sql = "SELECT account_id FROM customer_account WHERE email = ?";
try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setString(1, requestedEmail);
    try (ResultSet rs = ps.executeQuery()) {
        // ...
    }
}
```

So với:

```java
// KHÔNG NÊN: Ghép dữ liệu vào SQL, vừa giảm tái sử dụng vừa nguy cơ SQL injection.
String sql = "SELECT account_id FROM customer_account WHERE email = '"
        + requestedEmail + "'";
```

Trong ví dụ sai, mỗi email tạo chuỗi SQL khác và dữ liệu không còn được tham số hóa. **Prepared-statement cache không tự biến SQL ghép chuỗi thành an toàn.** Dùng `PreparedStatement` đúng cách là yêu cầu bảo mật độc lập với hiệu năng cache.

### Cache key không chỉ là giá trị câu SQL trong mọi driver

Tùy driver/pool, khóa của cache có thể còn phụ thuộc:

- Loại statement và overload `prepareStatement`, ví dụ có yêu cầu `RETURN_GENERATED_KEYS` hay không.
- `ResultSet` type, concurrency, holdability hoặc các thuộc tính statement liên quan.
- Catalog, schema, ngữ cảnh session, tùy chọn truy vấn hay kiểu tham số mà driver cần phân biệt.
- Cách SQL được chuẩn hóa (hoặc **không** chuẩn hóa), bao gồm khoảng trắng và comment.

Do đó, không khẳng định hai chuỗi SQL chỉ khác khoảng trắng chắc chắn cùng một cache entry. Nếu repository đang tạo SQL tự động, nên giữ format ổn định thay vì cố làm một bộ chuẩn hóa SQL tùy tiện có nguy cơ thay đổi literal hay comment. Những khác biệt về schema, quyền hoặc session state cũng có thể khiến việc tái sử dụng một statement không còn hợp lệ.

### `IN` động và số mẫu SQL bùng nổ

Ví dụ:

```sql
SELECT account_id, display_name
FROM customer_account
WHERE account_id IN (?, ?, ?);
```

Nếu ứng dụng tạo đúng một dấu `?` cho mỗi ID, danh sách 1 ID, 2 ID, 3 ID ... có thể tạo ra **nhiều mẫu SQL khác nhau**. Bên cạnh cache miss, danh sách quá dài có thể vượt giới hạn tham số hoặc kích thước statement của DB. Có thể cân nhắc:

- Chia truy vấn thành các mẫu độ dài đã kiểm soát hoặc những trang dữ liệu nhỏ.
- Dùng array parameter, table-valued parameter hoặc bảng tạm **khi DB/driver có hỗ trợ**.
- Chọn một hình thức truy vấn khác nếu cần xử lý hàng nghìn ID, sau khi đo chi phí thực tế.

Không được bù dấu `?` bằng cách chèn thêm giá trị giả vào danh sách mà có thể làm thay đổi kết quả. Cũng không tự dùng `?` để truyền **tên bảng hoặc tên cột**: placeholder chỉ đại diện cho giá trị dữ liệu, không thay phần cấu trúc SQL. Với định danh SQL động, dùng danh sách cho phép rõ ràng.

## 5. Ví dụ repository JDBC vẫn đúng dù cache bật hoặc tắt

Để thấy ranh giới tài nguyên, xét bảng minh họa:

```sql
CREATE TABLE customer_account (
    account_id    BIGINT PRIMARY KEY,
    display_name  VARCHAR(120) NOT NULL,
    email         VARCHAR(255) NOT NULL,
    active        BOOLEAN NOT NULL
);
```

Cú pháp `BOOLEAN` và ràng buộc thực tế có thể khác tùy DBMS. Repository sau dùng cùng những mẫu SQL cố định cho mỗi request, nhưng **không tự cài cache**. Việc tái sử dụng các prepared statement phía dưới do driver/pool được cấu hình quyết định.

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.Objects;
import java.util.Optional;
import javax.sql.DataSource;

public final class AccountRepository {
    private static final String FIND_BY_ID = """
            SELECT account_id, display_name, email, active
            FROM customer_account
            WHERE account_id = ?
            """;

    private static final String SET_ACTIVE = """
            UPDATE customer_account
            SET active = ?
            WHERE account_id = ?
            """;

    public record AccountRow(
            long id, String name, String email, boolean active) {
    }

    private final DataSource dataSource;

    public AccountRepository(DataSource dataSource) {
        this.dataSource = Objects.requireNonNull(dataSource, "dataSource");
    }

    public Optional<AccountRow> findById(long id) throws SQLException {
        try (Connection connection = dataSource.getConnection();
             PreparedStatement statement =
                     connection.prepareStatement(FIND_BY_ID)) {

            statement.setLong(1, id);

            try (ResultSet rs = statement.executeQuery()) {
                if (!rs.next()) {
                    return Optional.empty();
                }

                return Optional.of(new AccountRow(
                        rs.getLong("account_id"),
                        rs.getString("display_name"),
                        rs.getString("email"),
                        rs.getBoolean("active")));
            }
        }
    }

    public boolean setActive(long id, boolean active) throws SQLException {
        try (Connection connection = dataSource.getConnection();
             PreparedStatement statement =
                     connection.prepareStatement(SET_ACTIVE)) {

            statement.setBoolean(1, active);
            statement.setLong(2, id);

            int updated = statement.executeUpdate();
            if (updated > 1) {
                throw new SQLException("Expected at most one account row");
            }
            return updated == 1;
        }
    }
}
```

Mã dùng Java 17 trở lên (`record` và text block). Những điểm quan trọng:

1. `DataSource` là thành phần lâu sống, có thể được nhiều request sử dụng đồng thời.
2. Mỗi phương thức mượn **một `Connection`** và tạo **một `PreparedStatement` cho thao tác của mình**.
3. Các giá trị `id` và `active` được bind qua `setXxx`, không làm thay đổi chuỗi SQL.
4. `ResultSet` được đóng trước statement; statement được đóng trước connection nhờ `try-with-resources`.
5. Nếu driver/pool có cache, việc đóng statement **có thể** cho phép cache thu hồi hoặc lưu tài nguyên chuẩn bị để tái dùng; nếu không có cache, API và tính đúng đắn không đổi.
6. Không có statement nào được trả ra ngoài repository hoặc chia sẻ với thread khác.

Đoạn `setActive` là một câu DML đơn lẻ; với các thao tác gồm nhiều lệnh cập nhật phải thành công cùng nhau, vẫn cần một transaction qua `setAutoCommit(false)`, `commit()` và `rollback()` theo ranh giới nghiệp vụ. Cache **không** thay thế transaction hoặc khóa đồng thời.

## 6. Tái sử dụng statement trong batch và trong một lần mượn kết nối

Một cách giảm số lần tạo statement **không cần cache** là chuẩn bị một SQL duy nhất và thực thi nhiều bộ tham số ngay trên cùng kết nối. Ví dụ tăng trạng thái cho nhiều ID:

```java
String sql = "UPDATE customer_account SET active = ? WHERE account_id = ?";

try (Connection connection = dataSource.getConnection()) {
    connection.setAutoCommit(false);
    try {
        try (PreparedStatement statement = connection.prepareStatement(sql)) {
            for (long id : accountIds) {
                statement.setBoolean(1, true);
                statement.setLong(2, id);
                statement.addBatch();
            }

            int[] counts = statement.executeBatch();
            // Áp dụng chính sách kiểm tra counts của nghiệp vụ tại đây.
        }
        connection.commit();
    } catch (SQLException | RuntimeException failure) {
        try {
            connection.rollback();
        } catch (SQLException rollbackFailure) {
            failure.addSuppressed(rollbackFailure);
        }
        throw failure;
    }
}
```

Đoạn mã minh họa vòng đời statement và transaction; `accountIds` là danh sách ID do tầng gọi cung cấp. Một ứng dụng thật cần kiểm tra đủ số hàng và các mã trạng thái `Statement.SUCCESS_NO_INFO`, `EXECUTE_FAILED`, cũng như giới hạn batch size và khả năng xử lý `BatchUpdateException` của driver. `executeBatch()` chỉ gom lệnh, không bảo đảm nguyên tử; giao dịch trên `Connection` mới là ranh giới rollback.

**Hai cách tái sử dụng có vai trò khác nhau:**

| Cách | Phạm vi | Cần cấu hình cache? |
| --- | --- | --- |
| Tái sử dụng cùng `PreparedStatement` trong vòng lặp/batch | Trong thời gian statement đang mở trên một kết nối | Không |
| Driver/pool tái sử dụng công việc chuẩn bị sau khi statement đã đóng | Giữa các lần tạo statement với điều kiện tương thích | Có, nếu cơ chế cache được hỗ trợ và bật |

Không cố để `PreparedStatement` mở qua nhiều request để đạt hiệu quả cache. Hãy để driver/pool quản lý vòng đời của cache và giữ code nghiệp vụ ngắn gọn, đóng tài nguyên đúng quy tắc.

## 7. Tính giới hạn tài nguyên theo toàn bộ pool

Giả sử một instance ứng dụng có:

- `P`: số kết nối vật lý tối đa trong pool.
- `C`: số mục prepared-statement cache tối đa **trên mỗi kết nối vật lý**, nếu driver/pool dùng loại cache này.
- `N`: số instance ứng dụng cùng nối tới database.

Số mục cache tiềm năng ở quy mô triển khai có thể ước tính:

\[
\text{Cached entries}_{\max} \approx P \times C \times N
\]

Ví dụ một instance có `P = 20`, mỗi kết nối giữ tối đa `C = 50` mục thì sức chứa cộng gộp là **1.000 mục/instance**. Nếu chạy **4 instance**, con số có thể lên tới **4.000 mục**. Đây là ngân sách sức chứa, không phải dự báo chắc chắn sẽ có đúng bấy nhiêu statement phía server: việc cache có tạo server handle, những mục nào được nạp và cơ chế chia sẻ kế hoạch còn phụ thuộc driver/DB.

Đối với tài nguyên thực, cần xem thêm:

| Giới hạn | Tác động cần xem |
| --- | --- |
| **Số kết nối vật lý** | Socket, session, memory, giới hạn kết nối DB |
| **Số prepared statement trên kết nối** | Handle/cursor server, metadata, native resources, cache entries |
| **Số statement đang được mượn** | Không thể tái sử dụng nếu còn đang thực thi hoặc còn result set |
| **Số result set/cursor mở** | Có thể giữ tài nguyên server cho tới khi đóng/đọc xong |
| **Bộ nhớ ứng dụng** | Metadata SQL, wrapper, bộ đệm tham số và kết quả |
| **Số instance/pod** | Nhân tổng nhu cầu kết nối và cache lên theo số tiến trình |
| **Giới hạn DBMS** | Max connections, max open cursors/prepared statements, memory quota theo session |

Nếu DB giới hạn tài nguyên theo session, **cache càng lớn không nhất thiết càng tốt**. Cấu hình pool 40 kết nối và cache 200 mục trên mỗi kết nối có thể giữ nhiều tài nguyên hơn đáng kể so với pool 10 kết nối và cache 30 mục, dù workload có thể không cần tất cả các mục đó.

### Cần phân biệt dung lượng cache và số statement mở đồng thời

Một cache có giới hạn `C = 50` mục không nhất thiết chặn một request cố mở **100 `PreparedStatement` đang hoạt động** trên cùng connection. Tùy provider, cache chỉ lưu các mục đã trả lại, trong khi statement đang được mượn và `ResultSet` chưa đóng tiếp tục tiêu tốn tài nguyên. Vì vậy, phải giới hạn cả **kiểu sử dụng trong code** lẫn cấu hình cache.

Tương tự, giới hạn cache entries không thay thế giới hạn thời gian chờ mượn kết nối. Nếu tất cả `Connection` đều bận, request vẫn có thể timeout trước khi đụng tới statement cache; muốn tìm nguyên nhân phải xem metrics của pool và các transaction đang mở.

## 8. Khi cache đầy, điều gì xảy ra?

Cache thường có một chính sách loại bỏ mục cũ hoặc ít được dùng, chẳng hạn biến thể của **LRU** (*least recently used*). Tuy nhiên, **JDBC không chuẩn hóa thuật toán eviction cho prepared-statement cache**. Các driver/pool có thể dùng giới hạn theo số mục, độ dài SQL, bộ nhớ, thời gian sống hoặc quy tắc riêng.

Khi một mẫu SQL không còn trong cache, lần gọi tương ứng có thể chuẩn bị lại statement và tăng chi phí. Hiện tượng **cache churn** xảy ra khi số mẫu SQL được dùng thường xuyên vượt quá sức chứa cache: các mục vừa lưu đã bị đẩy ra trước khi có lần tái sử dụng tiếp theo.

```text
Cache capacity = 3

Tải tuần tự: SQL-A, SQL-B, SQL-C, SQL-D, SQL-A, SQL-B, ...

Cache có thể liên tục đẩy các mục cũ ra để nhận mẫu mới.
Nếu workload có nhiều mẫu hơn sức chứa, hit ratio giảm.
```

Không nên sửa churn bằng cách **tăng cache vô hạn**. Trước hết cần hiểu số mẫu SQL thực sự hữu ích, độ lặp của từng mẫu, kích thước statement và chi phí tài nguyên ở server. Đôi khi sửa việc sinh SQL không ổn định hoặc giữ các truy vấn có tham số cố định đem lại lợi ích lớn hơn tăng số mục cache.

### Statement bị vô hiệu sau DDL hay thay đổi session

Thay đổi schema (`ALTER TABLE`, thay đổi kiểu cột, xóa bảng), điều chỉnh quyền, thay đổi session hay lỗi kết nối có thể làm prepared handle hoặc execution plan cũ không còn sử dụng được. Một số driver/DB tự xử lý chuẩn bị lại; số khác có thể báo `SQLException` khi statement được dùng tiếp.

Ứng dụng không nên tự **bắt mọi `SQLException` rồi thử lại vô hạn** với câu lệnh ghi: lỗi có thể đến từ dữ liệu, ràng buộc, transaction đã hỏng hoặc trạng thái commit không rõ. Khi triển khai migration, cần kiểm tra hành vi invalidate cache, điều kiện thay mới kết nối và chính sách retry an toàn trên DB/driver đích.

## 9. Cấu hình cache: chỉ dùng tùy chọn đúng với thành phần thực tế

JDBC chuẩn có `DataSource` và `Connection.prepareStatement()`, nhưng **không có một thuộc tính chung tên `maxPreparedStatementCacheSize` áp dụng cho mọi pool và driver**. Một số driver hỗ trợ cache statement ở client hoặc cache handle server; một số pool có tính năng caching của riêng chúng; nhiều pool chủ động để driver quản lý việc cache.

Quy trình cấu hình phù hợp:

1. **Xác định JDBC driver và phiên bản**, DBMS/phiên bản, và thư viện connection pool.
2. **Xác định tầng thật sự có cache**; không bật hai cache độc lập vì tưởng chúng bổ sung cho nhau khi chưa biết tương tác.
3. **Chọn giới hạn theo tài nguyên**: số mục tối đa trên mỗi kết nối, kích thước SQL có được cache, thời gian sống hoặc cách eviction nếu có.
4. **Kiểm tra server-side preparation**: một số driver có tùy chọn quyết định khi nào chuẩn bị statement phía server; điều này khác với cache metadata ở client.
5. **Đo với workload thật** và kiểm tra metrics DB: bộ nhớ, số prepared handles, truy vấn/giây, độ trễ và lỗi tài nguyên.
6. **Kiểm tra hành vi sau rollback, DDL và đổi kết nối** trước khi đưa ra môi trường nhiều instance.

Từng driver có tên thuộc tính riêng, và những tên đó có thể thay đổi theo phiên bản. Vì vậy bài này không gán một bộ khóa cấu hình giả định cho tất cả sản phẩm. Khi dùng PostgreSQL JDBC, MySQL Connector/J, Oracle JDBC hoặc SQL Server JDBC, hãy đọc tài liệu **đúng phiên bản**, đặc biệt các phần statement cache, server-side prepare, cursor và statement close.

### `Statement.setPoolable(...)` là gợi ý, không phải cache bắt buộc

JDBC cung cấp một API để statement báo rằng nó có phù hợp với pooling hay không:

```java
try (PreparedStatement statement = connection.prepareStatement(sql)) {
    statement.setPoolable(true);
    // ... bind tham số, thực thi, đọc kết quả ...
}
```

`setPoolable(true)` là **hint** tới driver/pool theo hỗ trợ thực tế; không có nghĩa cache chắc chắn bật hoặc mục này sẽ được giữ lại. `statement.isPoolable()` trả trạng thái gợi ý của statement, **không phải phép đo cache hit**. Với statement không nên cache (chẳng hạn câu SQL cực hiếm hoặc dữ liệu SQL sinh ra rất dài), có thể cân nhắc `setPoolable(false)` nếu driver xem xét hint này; vẫn phải thử nghiệm vì không phải mọi triển khai đều xử lý như nhau.

Thay vì tự viết `Map<String, PreparedStatement>` toàn cục trong ứng dụng, nên dùng cơ chế đã được kiểm chứng của driver/pool. Một map tự viết dễ giữ nhầm statement từ kết nối đã đóng, trả cùng statement cho nhiều thread, không làm sạch tham số hoặc không giới hạn handle DB đúng cách.

## 10. Các trạng thái statement phải được xử lý khi tái sử dụng

Một `PreparedStatement` là đối tượng **có trạng thái**: giá trị tham số, batch đang chờ, `ResultSet` hiện tại, cảnh báo, `queryTimeout`, `fetchSize`, `maxRows` và nhiều lựa chọn thực thi có thể thay đổi trong đời sống của statement. Khi driver/pool cache và phát lại statement, nó cần có chiến lược reset hợp lệ; API JDBC không cho phép ứng dụng giả định mọi tùy chọn đã về một giá trị cụ thể chỉ vì vừa gọi `prepareStatement()`.

Do đó, code nghiệp vụ nên bảo vệ chính nó:

- Gán **đầy đủ tất cả placeholder** mỗi lần thực thi, kể cả những vị trí được phép `NULL`.
- Dùng `setNull(index, Types.X)` với kiểu SQL phù hợp khi cần truyền SQL `NULL`.
- Đặt rõ `queryTimeout`, `fetchSize` hoặc cấu hình khác khi hành vi của request **phụ thuộc** vào chúng; không dựa vào trạng thái do request trước để lại.
- Gọi `clearBatch()` khi muốn bỏ các lệnh batch **chưa** thực thi; đừng nhầm nó với `rollback()`.
- Đóng mọi `ResultSet` sau khi đọc và luôn đóng `PreparedStatement` khi xong.
- Không truyền một statement đã đóng hoặc thuộc kết nối đã trả về pool cho luồng khác.

Ví dụ với tham số nullable:

```java
String sql = "UPDATE customer_account SET display_name = ? WHERE account_id = ?";
try (PreparedStatement statement = connection.prepareStatement(sql)) {
    if (newName == null) {
        statement.setNull(1, java.sql.Types.VARCHAR);
    } else {
        statement.setString(1, newName);
    }
    statement.setLong(2, accountId);
    statement.executeUpdate();
}
```

Đoạn mã chỉ minh họa cách bind đủ tham số. Với schema `display_name NOT NULL` ở phần trước, `newName == null` sẽ **bị DB từ chối**; đó là điều đúng theo ràng buộc. Ứng dụng thật nên kiểm tra đầu vào để không cố truyền `NULL` vào cột bắt buộc. Điểm quan trọng là **không bỏ qua lần gán tham số 1** và vô tình dùng lại giá trị từ lần thực thi khác.

### `clearParameters()` có vai trò gì?

`PreparedStatement.clearParameters()` xóa **các giá trị tham số hiện đang gán**, hữu ích trong một số luồng dùng lại cùng statement. Nó không xóa các lệnh đã đưa vào batch (`clearBatch()` làm việc đó), không thay thế đóng statement và không phải lệnh xóa cache. Khi mỗi lượt luôn gán đủ tham số, không cần gọi `clearParameters()` một cách máy móc trước mọi lần thực thi.

## 11. Theo dõi cache và pool bằng chỉ số vận hành

Không có một API JDBC chuẩn trả các số **statement-cache hit**, **miss** hoặc **eviction** cho mọi driver. Các thông số này thường nằm ở metrics, JMX, log hoặc công cụ theo dõi riêng của driver/pool/DBMS.

| Nhóm chỉ số | Câu hỏi cần trả lời |
| --- | --- |
| Pool: active / idle / total connections | Pool có đủ kết nối không? Có kết nối nào bị giữ quá lâu? |
| Pool: pending threads / acquisition latency | Request có phải chờ mượn kết nối không? |
| Cache: hit, miss, eviction nếu có | Mẫu SQL có tái sử dụng được không, hay cache đang churn? |
| DB: open prepared statements/cursors theo session | Cache có đẩy tài nguyên phía server đến gần giới hạn không? |
| DB: parse/prepare rate và query execution time | Thời gian chuẩn bị có phải nút thắt thực sự? |
| JVM: heap/native memory, GC | Cache có tạo áp lực bộ nhớ không? |
| Error: timeout/too many statements/invalid statement | Có lỗi vượt giới hạn hay invalidation sau migration không? |

**Cache hit ratio** thường được tính từ hit và miss mà một thành phần thực sự xuất ra:

\[
\text{Hit ratio} = \frac{\text{hits}}{\text{hits} + \text{misses}}
\]

Đây là công thức tham khảo. Nếu driver không công bố hit/miss, **không tự suy ra con số đó từ thời gian truy vấn**. Một truy vấn nhanh có thể do dữ liệu nằm trong buffer cache của DB, execution plan cache hoặc mạng gần, chứ không nhất thiết là cache hit của prepared statement.

Không lấy hit ratio cao làm mục tiêu duy nhất. Một cache có 99% hit nhưng khiến DB giữ quá nhiều cursor cũng có thể là cấu hình tệ. Hãy đánh giá **độ trễ, throughput, memory, khả năng chịu lỗi và giới hạn DB** cùng lúc.

### Phân biệt leak kết nối với cache giữ tài nguyên hợp lệ

Một pool có 20 kết nối idle nhưng phía DB vẫn thấy nhiều prepared handle **không tự chứng minh có leak**: handle có thể đang được cache hợp lệ trên session idle. Ngược lại, statement chưa được đóng có thể gây leak ngay cả khi cache size được đặt nhỏ.

Để chẩn đoán, cần quan sát vòng đời `Connection`/`PreparedStatement` trong code, số handle tăng theo thời gian, lượng cache ổn định sau warm-up và việc tài nguyên có giảm khi kết nối vật lý thực sự bị đóng không. Khi nghi ngờ leak, kiểm tra `try-with-resources` và những đường lỗi trước; đừng chỉ tắt cache rồi coi triệu chứng biến mất là nguyên nhân đã được giải quyết.

## 12. Kiểm thử hiệu quả và tính đúng đắn khi bật cache

Một benchmark có ích cần so sánh **cùng workload** giữa cache bật và cache tắt, cùng pool size, cùng SQL, cùng tập dữ liệu và cùng số kết nối đồng thời. Nên đo cả giai đoạn **warm-up** và giai đoạn đã ổn định, vì những lần đầu có thể phải chuẩn bị statement và lấp đầy cache.

| Tình huống | Cách kiểm tra | Kết quả mong đợi |
| --- | --- | --- |
| SQL cố định lặp lại | Gọi `findById` nhiều lần trên các ID khác nhau | Kết quả đúng; nếu có metrics thì quan sát tỷ lệ tái sử dụng |
| Cache tắt | Chạy cùng workload mà không bật cache | Chức năng không đổi, đo baseline thời gian và resource |
| Nhiều kết nối vật lý | Tăng request đồng thời trong giới hạn pool | Xem cache/handle theo kết nối, không giả định một cache chia sẻ |
| Nhiều mẫu SQL hiếm dùng | Phát sinh nhiều template khác nhau | Phát hiện churn, eviction hoặc chi phí prepare nếu có metrics |
| Statement/result set được đóng | Chạy tải lâu và theo dõi tài nguyên | Không tăng vô hạn số handle hay số kết nối đang mượn |
| Thiếu bind một tham số | Tạo test kiểm tra nhánh setter | Code phát hiện hoặc gán đủ tham số, không lấy giá trị cũ từ request trước |
| Batch lỗi giữa chừng | Ném lỗi từ một `executeBatch` có transaction | Rollback đúng ranh giới, không tạo kết quả một phần ngoài hợp đồng |
| Schema thay đổi trong môi trường thử nghiệm | Migration rồi chạy lại SQL liên quan | Driver/DB xử lý invalidation hoặc báo lỗi rõ ràng; ứng dụng không nuốt lỗi |
| Kết nối vật lý bị thay | Buộc pool tạo lại connection trong test | Statement cũ không bị dùng trái kết nối; cache mới được warm-up nếu cần |
| Hệ thống nhiều instance | Nhân số tiến trình ứng dụng | Tổng số kết nối/handle vẫn nằm trong ngân sách DB |

### Kiểm chứng bằng thử nghiệm có kiểm soát

Một quy trình đo đạc ngắn:

1. Chọn **2–5 SQL template được gọi nhiều nhất**, cố định bộ dữ liệu và độ phức tạp truy vấn.
2. Chạy với cache tắt và pool size phù hợp để có baseline.
3. Bật cache đúng một tầng đã xác định, đặt sức chứa **nhỏ và có giới hạn**.
4. Warm-up các SQL template trên đủ kết nối mà workload thực tế sử dụng.
5. So sánh độ trễ p50/p95/p99, throughput, parse/prepare rate và tài nguyên DB.
6. Tăng số mẫu SQL để quan sát churn, sau đó nâng/hạ kích thước cache nếu kết quả đo biện minh được.
7. Kiểm thử lỗi và migration; chỉ dùng cấu hình mới nếu tính đúng đắn và giới hạn tài nguyên đều được giữ.

Tránh chạy thử chỉ một thread rồi suy luận hiệu năng khi triển khai hàng chục instance. Tỷ lệ cache hit, số kết nối hoạt động và áp lực DB thường thay đổi khi tăng concurrency; ở một số workload, việc giữ nhiều kết nối vật lý còn khiến cache phân tán hơn.

## 13. Những lỗi thiết kế thường gặp

| Sai lầm | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Không đóng `PreparedStatement` vì đã có cache | Giữ statement/cursor đang hoạt động, có thể cạn tài nguyên | Luôn dùng `try-with-resources` |
| Lưu statement trong singleton chia sẻ nhiều thread | Race condition ở tham số, kết quả và vòng đời Connection | Chỉ chia sẻ `DataSource`, không chia sẻ statement mutable |
| Tưởng pool luôn có statement cache | Bật sai chỗ hoặc đánh giá sai mức tái sử dụng | Kiểm tra tài liệu driver/pool theo phiên bản |
| Bật cache đồng thời ở nhiều tầng mà không hiểu tương tác | Tăng memory/handle, khó chẩn đoán lợi ích | Xác định một chiến lược caching và đo thực tế |
| Chỉ tính cache size trên một kết nối | Tổng tài nguyên có thể nhân theo pool size và số instance | Tính ngân sách `P × C × N` kèm giới hạn DB |
| Tăng cache size vô hạn để cải thiện hit ratio | Có thể vượt memory, max cursors hoặc quota session | Đặt giới hạn, quan sát eviction và resource |
| Tạo SQL bằng ghép dữ liệu người dùng | SQL injection và rất nhiều SQL template | Dùng tham số `?` và setter JDBC |
| Dùng `ORDER BY`, comment hay whitespace động vô hạn | Cache key có thể thay đổi liên tục | Giữ SQL template ổn định khi có thể |
| Tin rằng `setPoolable(true)` bảo đảm cache hit | Hiểu sai API hint của JDBC | Kiểm tra metrics thực tế của driver/pool |
| Quên gán một tham số khi statement được dùng lại | Dùng nhầm giá trị cũ hoặc gặp lỗi tham số | Bind đủ placeholder mỗi lần |
| Dùng `clearParameters()` thay `close()` | Không trả statement/resource về đúng vòng đời | `close()` đúng lúc; clear chỉ xóa tham số hiện tại |
| Thấy DB giữ prepared handles rồi kết luận leak | Có thể là cache hợp lệ của kết nối idle | Quan sát chu kỳ cache, close và session lifetime |
| Nuốt mọi `SQLException` rồi tự retry câu `UPDATE` | Có thể lặp tác động, hỏng transaction hoặc mất lỗi thật | Phân loại lỗi, rollback và retry toàn giao dịch khi an toàn |

## 14. Bài tập tự kiểm tra

**Bài 1 — Tính ngân sách.** Một hệ thống chạy 3 instance, mỗi instance có pool tối đa 15 kết nối vật lý; cache của driver chứa tối đa 40 mục trên mỗi kết nối. Tổng sức chứa lý thuyết của các cache theo kết nối là bao nhiêu?

**Đáp án:** `3 × 15 × 40 = 1.800` mục. Đây không nhất thiết là 1.800 handle server, vì cách lưu cache phụ thuộc driver và DB.

**Bài 2 — Có nên bỏ `close()`?** Khi `PreparedStatement.close()` có thể trả statement về cache, vì sao vẫn phải gọi nó trong `try-with-resources`?

**Đáp án:** Đóng statement là cách ứng dụng kết thúc quyền sở hữu và cho phép driver/pool giải phóng hoặc tái sử dụng đúng cách. Bỏ `close()` có thể khiến statement vẫn đang hoạt động và giữ tài nguyên.

**Bài 3 — Một cache cho cả pool?** Có hai `Connection` vật lý A và B. A đã cache SQL `SELECT ... WHERE id = ?`; B chưa từng dùng SQL ấy. Có thể khẳng định lời gọi trên B chắc chắn là cache hit không?

**Đáp án:** Không. Prepared-statement cache thường gắn với kết nối vật lý; chỉ có thể kết luận từ cơ chế cụ thể của driver/pool và metrics của nó.

**Bài 4 — SQL động.** Một chương trình tạo SQL `SELECT ... WHERE email = 'a@example.test'` và thay email trực tiếp vào chuỗi ở mỗi request. Hãy chỉ ra hai vấn đề liên quan bảo mật và cache.

**Đáp án:** Dữ liệu không được tham số hóa nên có nguy cơ SQL injection; các email khác nhau tạo SQL template khác nhau, làm giảm khả năng tái sử dụng cache. Sửa thành `WHERE email = ?` và `setString(1, email)`.

**Bài 5 — `setPoolable`.** Một statement trả `isPoolable() == true`. Có thể kết luận statement hiện nằm trong cache và lần chạy tiếp theo sẽ nhanh hơn không?

**Đáp án:** Không. Đây là trạng thái gợi ý về pooling, không phải thống kê hit/miss hay bảo đảm về kế hoạch thực thi.

**Bài 6 — Chẩn đoán tài nguyên.** Pool có nhiều kết nối idle, DB còn giữ nhiều prepared handle và số handle ổn định sau khi warm-up. Đây chắc chắn là leak hay không? Bạn cần xem thêm chỉ số nào?

**Gợi ý:** Không chắc. Quan sát tài nguyên theo session, số statement đang mở, cache entries, vòng đời close, pool active/idle và hành vi khi đóng hẳn kết nối vật lý.

**Bài 7 — Transaction và cache.** Trong một transaction chuyển tiền, lệnh trừ tiền thành công nhưng lệnh cộng tiền thất bại. Prepared-statement cache có làm hai thay đổi thành nguyên tử không?

**Đáp án:** Không. Cần cùng `Connection`, `autoCommit = false`, `commit()` nếu cả hai thành công hoặc `rollback()` nếu lỗi. Cache chỉ tác động đến chi phí chuẩn bị statement.

**Bài 8 — Chọn cấu hình.** Hai workload có cùng 10.000 request/phút: workload A lặp 5 SQL template, workload B tạo 8.000 SQL template hiếm dùng. Workload nào có khả năng được lợi hơn từ cache dung lượng nhỏ?

**Đáp án:** Workload A thường có cơ hội hit cao hơn. Với B, cache nhỏ dễ churn; nên xem lại việc sinh SQL hoặc chọn chiến lược truy vấn phù hợp trước khi tăng cache.

## Tổng kết

Trong JDBC, `PreparedStatement` cache là **cơ chế tối ưu tùy driver/pool/DB**, không phải một phần bắt buộc của `Connection.prepareStatement()`. Giá trị chính của cache là tái sử dụng công việc chuẩn bị đối với **những mẫu SQL ổn định**, nhưng mỗi kết nối vật lý có thể giữ tài nguyên riêng và tổng ngân sách có thể tăng theo **pool size × cache size × số instance**. Dù cache bật hay tắt, code ứng dụng vẫn phải bind đủ tham số, dùng `try-with-resources` để đóng `ResultSet`/statement/connection, không chia sẻ statement giữa thread và quản lý transaction bằng API JDBC chuẩn. Hãy chọn giới hạn tài nguyên có kiểm soát, đo hit/miss và chi phí server khi các metrics đó có sẵn, kiểm thử invalidation và trường hợp lỗi, đồng thời tối ưu SQL template trước khi mở rộng cache.
