# Thiết kế API không trả tài nguyên JDBC đã hết hiệu lực

## 1. Vì sao đây là vấn đề của thiết kế API?

Trong **JDBC (Java Database Connectivity)**, ứng dụng Java truy cập cơ sở dữ liệu quan hệ thông qua các giao diện như `Connection`, `Statement`, `PreparedStatement` và `ResultSet`. Chúng không đơn thuần là các đối tượng lưu dữ liệu: mỗi đối tượng thường đại diện cho **tài nguyên đang được quản lý** bởi JDBC driver, kết nối mạng, database server hoặc connection pool.

Một phương thức repository có thể viết SQL đúng, chạy truy vấn thành công rồi vẫn trả kết quả **không thể sử dụng**, nếu nó trả một `ResultSet` sau khi `Statement` hoặc `Connection` đã đóng.

~~~java
// SAI: phương thức trả một ResultSet phụ thuộc Statement đã đóng.
public ResultSet findUsersBad(DataSource dataSource) throws SQLException {
    try (Connection connection = dataSource.getConnection();
         PreparedStatement statement = connection.prepareStatement(
                 "SELECT id, name FROM app_user")) {
        return statement.executeQuery();
    }
}

// Bên gọi nhận ResultSet nhưng Statement và Connection đã được đóng.
// rs.next() có thể ném SQLException: ResultSet is closed.
~~~

Vấn đề không nằm ở câu SQL. **Vòng đời của kết quả đã vượt khỏi vòng đời của tài nguyên mà nó phụ thuộc.** Nếu bỏ `try-with-resources` để giữ `ResultSet` sống lâu hơn, mã lại có nguy cơ rò rỉ kết nối và con trỏ database vì không xác định được ai phải đóng chúng.

Mục tiêu bài học thuộc chương **Vòng đời tài nguyên** là thiết kế API để:

1. Bên **tạo/mượn** tài nguyên biết rõ trách nhiệm đóng.
2. Đối tượng trả về vẫn hợp lệ sau khi tài nguyên JDBC đã được giải phóng.
3. Dữ liệu lớn có thể xử lý theo luồng **ngay bên trong phạm vi mở tài nguyên**.
4. Lỗi, transaction, connection pool và xử lý bất đồng bộ không phá vỡ hợp đồng vòng đời.

## 2. Bản đồ phụ thuộc tài nguyên trong JDBC

~~~mermaid
flowchart TD
    A[DataSource / Connection pool] -->|getConnection| B[Connection]
    B -->|prepareStatement| C[PreparedStatement]
    C -->|executeQuery| D[ResultSet]
    D -->|getXXX| E[Giá trị Java đã được tách khỏi JDBC]
    E --> F[DTO / record / List bất biến]
    D -. không trả ra ngoài phạm vi .-> G[Repository boundary]
    F --> G
    G --> H[Service / Controller / API caller]
~~~

Đối với các truy vấn thông thường, cấu trúc phụ thuộc là:

- **`Connection`** mở phiên giao tiếp hoặc đại diện cho connection đang được mượn từ pool.
- **`Statement`/`PreparedStatement`** gắn với một connection và thực hiện câu SQL.
- **`ResultSet`** gắn với statement đã tạo ra nó; việc tiến con trỏ hoặc đọc cột có thể cần driver, bộ đệm hoặc trao đổi với server.
- **Dữ liệu Java đã materialize** như `String`, `long`, `BigDecimal` hoặc một `record` được tạo từ giá trị cột thường có thể sử dụng sau khi đóng JDBC resources.

Bảng sau tóm tắt điểm kết thúc vòng đời:

| Tài nguyên | Ai thường tạo? | Khi nào cần kết thúc? | Có nên trả trực tiếp từ repository không? |
| --- | --- | --- | --- |
| `Connection` | `DataSource.getConnection()` | Sau khi hoàn tất phạm vi SQL/transaction do bên gọi sở hữu. | Thường **không**, trừ API hạ tầng được thiết kế rõ để chuyển giao quyền sở hữu. |
| `PreparedStatement` | `Connection.prepareStatement()` | Khi không còn thực thi hay đọc kết quả thuộc statement. | Không trong API repository nghiệp vụ thông thường. |
| `ResultSet` | `executeQuery()` / metadata | Khi xử lý xong các hàng, trước khi đóng statement. | Không nếu tài nguyên sẽ được đóng trong phương thức. |
| `InputStream`/`Reader` từ cột LOB | `ResultSet.getBinaryStream()`/`getCharacterStream()` | Khi đọc xong luồng và trước khi giải phóng những resource nó phụ thuộc. | Không nếu luồng vẫn đọc từ JDBC. |
| `Blob`/`Clob`/`SQLXML` | `ResultSet.getBlob()`, `getClob()`, `getSQLXML()`... | Trong phạm vi resource hợp lệ; giải phóng khi thích hợp. | Không mặc định; đây có thể là locator hoặc tài nguyên gắn với connection. |
| DTO/record gồm giá trị đã sao chép | Mapper tạo từ kết quả | Theo vòng đời object Java thông thường. | **Có**, đây thường là hợp đồng API an toàn nhất. |

**Điểm cần nhớ:** Một đối tượng Java có thể vẫn tồn tại trong heap nhưng **không còn hợp lệ để sử dụng**. `ResultSet` là ví dụ rõ ràng: tham chiếu chưa bị garbage collector thu hồi không có nghĩa cursor hoặc connection vẫn hoạt động.

### 2.1. Những thao tác đóng gây hiệu ứng dây chuyền

Theo mô hình JDBC thông thường:

- Đóng `Statement` sẽ đóng `ResultSet` hiện tại do statement quản lý.
- Một `Statement` thường chỉ có một `ResultSet` hiện tại; thực thi một lệnh khác trên cùng statement có thể đóng kết quả cũ, trừ những cơ chế xử lý nhiều kết quả được hỗ trợ.
- Đóng `Connection` kết thúc quyền sử dụng những statement/result set phụ thuộc.
- Với connection pool, `Connection.close()` thường trả **logical connection** về pool thay vì đóng socket vật lý. **Bên gọi vẫn không được tiếp tục dùng proxy connection hoặc result set của lần mượn đã kết thúc.**

Không thiết kế API dựa trên giả định rằng con trỏ sẽ tiếp tục hoạt động sau khi tài nguyên cha đóng, kể cả một driver tình cờ giữ lại bộ đệm đủ đọc ở một tình huống cụ thể.

## 3. Mẫu sai thường gặp: trả `ResultSet` ra ngoài phạm vi tài nguyên

Xem một phương thức có vẻ hợp lý:

~~~java
public ResultSet listOrders(DataSource dataSource) throws SQLException {
    Connection connection = dataSource.getConnection();
    PreparedStatement statement = connection.prepareStatement(
            "SELECT id, total_amount FROM orders ORDER BY id");
    return statement.executeQuery();
}
~~~

Mẫu này tránh đóng quá sớm, nhưng chuyển trách nhiệm giải phóng tài nguyên sang bên gọi một cách **ẩn**. Bên gọi có thể chỉ thấy kiểu trả về `ResultSet` mà không biết phải đóng **cả** statement và connection do repository đang giữ. Điều này tạo ra nhiều rủi ro:

1. **Rò rỉ connection:** Không có nơi rõ ràng để trả connection về pool.
2. **Rò rỉ statement/cursor:** Driver hoặc DBMS tiếp tục giữ tài nguyên cho truy vấn.
3. **Đường lỗi khó dọn dẹp:** Nếu `prepareStatement()` hoặc `executeQuery()` ném exception, connection có thể bị bỏ quên.
4. **Giao tiếp sai giữa các tầng:** Controller/service phải hiểu chi tiết vòng đời JDBC dù chỉ muốn danh sách đơn hàng.
5. **Coupling với transaction:** Kết quả có thể chỉ còn hợp lệ trong transaction do repository tạo hoặc bên gọi đang kiểm soát.

Một biến thể khác cũng sai:

~~~java
public Stream<String> namesBad(DataSource dataSource)
        throws SQLException {
    try (Connection connection = dataSource.getConnection();
         PreparedStatement statement = connection.prepareStatement(
                 "SELECT name FROM app_user");
         ResultSet rs = statement.executeQuery()) {
        // Stream được đánh giá trễ và giữ tham chiếu tới ResultSet.
        return Stream.generate(() -> readNextName(rs));
    }
}
~~~

`readNextName(rs)` trong ví dụ là hàm minh họa việc đọc hàng; chi tiết triển khai không làm mẫu này an toàn hơn. Khi bên gọi bắt đầu duyệt `Stream`, khối `try-with-resources` đã kết thúc, khiến kết quả dựa vào `ResultSet` hết hiệu lực. Việc chuyển sang `Iterator`, `Spliterator` hoặc `Supplier` cũng không giải quyết được vấn đề nếu chúng vẫn đọc tài nguyên đã đóng.

**Quy tắc:** Không trả về một **lazy view** vẫn cần JDBC resources khi phạm vi tài nguyên đã kết thúc.

## 4. API tốt phải có hợp đồng sở hữu rõ ràng

Một repository nên làm rõ ba điều:

- **Ai mượn/mở connection?** Repository tự lấy từ `DataSource`, hay transaction manager/bên gọi cấp connection?
- **Ai đóng?** Bên mở chịu trách nhiệm cho tài nguyên mình sở hữu; các tầng khác chỉ dùng dữ liệu đã được trả về theo hợp đồng.
- **Kết quả còn phụ thuộc tài nguyên không?** Nếu có, phải được xử lý trong callback/consumer khi tài nguyên còn mở, hoặc dùng một abstraction chuyên biệt có quyền sở hữu và `close()` tường minh.

Hai cách thiết kế thường phù hợp:

| Kiểu API | Bên gọi nhận gì? | Bên nào sở hữu tài nguyên? | Khi nào dùng? |
| --- | --- | --- | --- |
| **Materialize rồi trả về** | `Optional<User>`, `List<Order>`, DTO, bản ghi thống kê... | Repository/cơ chế transaction | Dữ liệu nhỏ hoặc vừa, dùng rộng rãi trong service/API. |
| **Callback đồng bộ trong resource scope** | Trả về kết quả tổng hợp hoặc số hàng đã xử lý | Repository/cơ chế transaction | Tập kết quả lớn, xử lý từng hàng, tránh giữ toàn bộ dữ liệu trong RAM. |

Một API trả tài nguyên thô vẫn có thể được thiết kế ở tầng **infrastructure** với chủ sở hữu chuyển giao rõ ràng, chẳng hạn kiểu chuyên dụng triển khai `AutoCloseable`. Tuy vậy, phần lớn repository nghiệp vụ có thể tránh sự phức tạp đó bằng hai cách trên.

## 5. Cách 1: ánh xạ đầy đủ rồi trả về DTO độc lập

Ví dụ repository tìm người dùng theo ID, trả một Java `record` không phụ thuộc vào connection:

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.Optional;
import javax.sql.DataSource;

public final class UserRepository {
    private final DataSource dataSource;

    public UserRepository(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public record User(long id, String name, String email) {}

    public Optional<User> findById(long userId) throws SQLException {
        final String sql = """
                SELECT id, name, email
                FROM app_user
                WHERE id = ?
                """;

        try (Connection connection = dataSource.getConnection();
             PreparedStatement statement =
                     connection.prepareStatement(sql)) {

            statement.setLong(1, userId);

            try (ResultSet rs = statement.executeQuery()) {
                if (!rs.next()) {
                    return Optional.empty();
                }

                User user = new User(
                        rs.getLong("id"),
                        rs.getString("name"),
                        rs.getString("email"));

                return Optional.of(user);
            }
        }
    }
}
~~~

Điểm quan trọng trong trình tự thực thi:

1. `DataSource.getConnection()` cấp connection cho phương thức.
2. `PreparedStatement` nhận tham số qua `setLong()`; cách này tránh ghép trực tiếp giá trị ID vào SQL.
3. `rs.next()` và `rs.getXXX()` được gọi **khi result set và statement còn mở**.
4. `User` được tạo hoàn chỉnh từ các giá trị Java. `Optional<User>` không giữ tham chiếu `ResultSet`.
5. Khi phương thức `return`, Java vẫn chạy phần đóng tài nguyên của `try-with-resources` theo thứ tự ngược trước khi chuyển kết quả cho bên gọi.

Bên gọi có thể sử dụng `user.name()`, gửi DTO sang tầng HTTP hoặc đưa vào một tác vụ khác sau khi repository trả về. Các chuỗi và giá trị số trong ví dụ đã được đọc xong, không cần connection nữa.

**Không gọi `rs.getString(...)` ở controller** và không đưa `ResultSet` vào DTO như một trường ẩn. Việc đổi kiểu bên ngoài thành `Object` hay `Supplier<String>` cũng không làm dữ liệu tự trở nên độc lập.

### 5.1. Trả về danh sách sau khi đọc hết kết quả

~~~java
public List<UserRepository.User> findByEmailDomain(
        DataSource dataSource, String domain) throws SQLException {

    String sql = """
            SELECT id, name, email
            FROM app_user
            WHERE email LIKE ?
            ORDER BY id
            """;

    try (Connection connection = dataSource.getConnection();
         PreparedStatement statement = connection.prepareStatement(sql)) {
        statement.setString(1, "%@" + domain);

        try (ResultSet rs = statement.executeQuery()) {
            List<UserRepository.User> users = new ArrayList<>();

            while (rs.next()) {
                users.add(new UserRepository.User(
                        rs.getLong("id"),
                        rs.getString("name"),
                        rs.getString("email")));
            }

            return List.copyOf(users);
        }
    }
}
~~~

Đoạn trích dùng `java.util.List` và `java.util.ArrayList`. `List.copyOf(users)` tạo danh sách không cho phép thêm/xóa phần tử; bản thân mỗi `User` là record gồm các trường đã materialize. Với query lớn, danh sách vẫn dùng bộ nhớ tỉ lệ theo số hàng; cần giới hạn/trang hóa thay vì luôn đưa toàn bộ database về bộ nhớ.

**Phân biệt bất biến nông và sâu:** `List.copyOf` không tự sao chép sâu đối tượng bên trong. Nếu DTO chứa `byte[]`, `Date` mutable hoặc đối tượng tham chiếu khác, có thể cần defensive copy khi tạo DTO và khi công bố giá trị cho bên ngoài.

## 6. Thiết kế API mapper: giấu việc duyệt `ResultSet`

Nếu có nhiều repository, có thể dùng một abstraction để áp dụng nhất quán quy tắc **“đọc JDBC trong phạm vi mở, chỉ trả dữ liệu Java”**.

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.ArrayList;
import java.util.List;
import javax.sql.DataSource;

public final class JdbcQueries {
    private JdbcQueries() {}

    @FunctionalInterface
    public interface Binder {
        void bind(PreparedStatement statement) throws SQLException;
    }

    @FunctionalInterface
    public interface RowMapper<T> {
        T map(ResultSet rs) throws SQLException;
    }

    public static <T> List<T> queryAll(
            DataSource dataSource,
            String sql,
            Binder binder,
            RowMapper<T> mapper) throws SQLException {

        try (Connection connection = dataSource.getConnection();
             PreparedStatement statement =
                     connection.prepareStatement(sql)) {

            binder.bind(statement);

            try (ResultSet rs = statement.executeQuery()) {
                List<T> results = new ArrayList<>();

                while (rs.next()) {
                    results.add(mapper.map(rs));
                }

                return List.copyOf(results);
            }
        }
    }
}
~~~

Cách sử dụng:

~~~java
List<UserRepository.User> users = JdbcQueries.queryAll(
        dataSource,
        "SELECT id, name, email FROM app_user WHERE id >= ? ORDER BY id",
        statement -> statement.setLong(1, 100L),
        rs -> new UserRepository.User(
                rs.getLong("id"),
                rs.getString("name"),
                rs.getString("email")));
~~~

**Hợp đồng của `RowMapper<T>`:** Phương thức `map` phải trả một giá trị **đã tách khỏi resource**, không trả `ResultSet`, `Blob`, `InputStream` hoặc một hàm lazy tiếp tục đọc `rs`. Kiểu generic `T` không tự ngăn người viết mapper vi phạm hợp đồng; cần quy ước API, review và kiểm thử.

Trong thư viện thực tế như Spring JDBC, `RowMapper`/`ResultSetExtractor` cũng dựa trên nguyên tắc callback được thực thi trong khi framework quản lý result set. Để dùng đúng framework, hãy đọc contract của chính framework thay vì tự đóng connection mà transaction manager đang sở hữu.

### 6.1. Ai sở hữu transaction?

Abstraction `JdbcQueries.queryAll` ở trên tự mượn rồi đóng connection; nó phù hợp các truy vấn độc lập mà repository sở hữu phạm vi connection. Nếu một service phải thực hiện **nhiều truy vấn trong cùng transaction**, tầng transaction cần sở hữu connection và truyền nó cho các helper **không được đóng connection đó**.

Ví dụ về phân quyền:

~~~text
Service / Transaction manager: sở hữu Connection và commit/rollback
  |
  +-- Repository A: tạo + đóng PreparedStatement/ResultSet của mình
  |
  +-- Repository B: tạo + đóng PreparedStatement/ResultSet của mình
  |
  +-- Transaction manager: commit hoặc rollback, kết thúc Connection
~~~

Đừng dùng một helper luôn `getConnection()` mới cho mỗi SQL rồi cho rằng tất cả câu lệnh sẽ tự nằm trong transaction của tầng trên. Hành vi còn tùy framework và cơ chế gắn connection vào transaction.

## 7. Cách 2: xử lý dữ liệu lớn bằng callback đồng bộ

Nếu truy vấn trả hàng trăm nghìn dòng, tạo `List` toàn bộ có thể tăng áp lực heap và garbage collection. Một lựa chọn khác là **repository giữ tài nguyên mở và gọi callback cho từng hàng ngay trong vòng lặp**.

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import javax.sql.DataSource;
import java.util.function.Consumer;

public final class UserExporter {
    public record UserRow(long id, String name) {}

    public static long forEachUser(
            DataSource dataSource,
            Consumer<UserRow> consumer) throws SQLException {

        String sql = "SELECT id, name FROM app_user ORDER BY id";
        long rows = 0;

        try (Connection connection = dataSource.getConnection();
             PreparedStatement statement =
                     connection.prepareStatement(sql)) {

            // Đây là hint; driver quyết định có fetch theo lô hay không.
            statement.setFetchSize(100);

            try (ResultSet rs = statement.executeQuery()) {
                while (rs.next()) {
                    UserRow row = new UserRow(
                            rs.getLong("id"),
                            rs.getString("name"));

                    // Callback chạy đồng bộ, tài nguyên còn mở.
                    consumer.accept(row);
                    rows++;
                }
            }
        }

        return rows;
    }
}
~~~

Cách gọi:

~~~java
long count = UserExporter.forEachUser(
        dataSource,
        row -> System.out.println(row.id() + " " + row.name()));
~~~

Bên gọi nhận một `UserRow` đã materialize, **không nhận `ResultSet`**. Khi callback kết thúc hoặc ném runtime exception, `try-with-resources` vẫn đóng những tài nguyên đã mở. Nếu callback ném exception sau khi đã gửi dữ liệu ra hệ thống khác, cần xử lý **partial output**: đóng JDBC resource không tự đảo ngược file/network/queue đã ghi.

### 7.1. Điều kiện khi dùng callback

- **Đồng bộ trong cùng call stack:** không lưu `ResultSet` hoặc một `InputStream` phụ thuộc vào nó để dùng sau callback.
- **Chi phí mỗi hàng:** callback xử lý quá chậm khiến connection và có thể cả transaction bị giữ lâu.
- **Backpressure:** nếu đẩy dữ liệu vào hàng đợi, cần giới hạn số lượng đang chờ; enqueue DTO không đồng nghĩa consumer downstream xử lý ngay.
- **Fetch size và transaction:** `setFetchSize(...)` chỉ là gợi ý; một số driver yêu cầu cấu hình hoặc chế độ transaction cụ thể để thật sự stream dữ liệu. Kiểm tra tài liệu driver và benchmark.
- **Hủy giữa chừng:** khi callback ném exception hoặc caller hủy công việc, cần xác định transaction rollback và xử lý kết quả từng phần.
- **Không đem `Connection`/`ResultSet` sang thread khác.** Thread nhận callback không nên tiếp tục dùng JDBC resource sau khi phương thức xử lý đã kết thúc.

Nếu một API cần **trả `Stream<T>` cho bên gọi xử lý trễ**, phải thiết kế một abstraction có vòng đời đóng tường minh và bảo đảm caller đóng sau khi tiêu thụ. Đây là một hợp đồng khác, phức tạp hơn việc trả `List<T>`; chỉ dùng khi toàn bộ đường đi sử dụng và đóng stream được kiểm soát.

## 8. Bẫy đặc biệt: `Blob`, `Clob` và luồng đọc dữ liệu lớn

Không phải mọi giá trị lấy từ `ResultSet` đều tách khỏi JDBC bằng một lời gọi getter. Một số getter có thể trả **locator** hoặc stream đọc dữ liệu theo yêu cầu:

~~~java
// Nguy hiểm: stream có thể phụ thuộc ResultSet và Connection.
public InputStream openDocumentBad(DataSource dataSource, long id)
        throws SQLException {
    try (Connection connection = dataSource.getConnection();
         PreparedStatement ps = connection.prepareStatement(
                 "SELECT content FROM document_store WHERE id = ?")) {
        ps.setLong(1, id);
        try (ResultSet rs = ps.executeQuery()) {
            if (!rs.next()) {
                return InputStream.nullInputStream();
            }
            return rs.getBinaryStream("content");
        }
    }
}
~~~

Giá trị `InputStream.nullInputStream()` ở nhánh không tìm thấy hoàn toàn độc lập, nhưng stream được trả từ `rs.getBinaryStream("content")` có thể không còn dùng được vì statement/result set và connection đã đóng.

### 8.1. Cách an toàn với nội dung nhỏ: materialize

Nếu giới hạn kích thước dữ liệu nhỏ và đã được kiểm soát:

~~~java
public byte[] findDocumentBytes(
        DataSource dataSource, long id) throws SQLException {
    try (Connection connection = dataSource.getConnection();
         PreparedStatement ps = connection.prepareStatement(
                 "SELECT content FROM document_store WHERE id = ?")) {

        ps.setLong(1, id);
        try (ResultSet rs = ps.executeQuery()) {
            if (!rs.next()) {
                return null; // Hoặc thiết kế kiểu trả về không mơ hồ.
            }

            return rs.getBytes("content");
        }
    }
}
~~~

Mảng byte đã đọc xong có thể được dùng sau khi connection đóng; tuy nhiên, một trường BLOB lớn có thể làm đầy heap. Ngoài ra, `null` ở đây không phân biệt “không có hàng” và “cột SQL NULL”; trong API thực tế có thể dùng kiểu kết quả có trạng thái rõ ràng.

Nếu công bố mảng byte trong DTO, cần **sao chép phòng vệ** để tránh mã gọi sửa dữ liệu ngoài ý muốn. `byte[]` tự nó là một giá trị mutable dù đã tách khỏi JDBC.

### 8.2. Cách an toàn với nội dung lớn: copy trong resource scope

~~~java
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import javax.sql.DataSource;

public static boolean copyDocument(
        DataSource dataSource,
        long id,
        OutputStream destination) throws SQLException, IOException {

    try (Connection connection = dataSource.getConnection();
         PreparedStatement ps = connection.prepareStatement(
                 "SELECT content FROM document_store WHERE id = ?")) {

        ps.setLong(1, id);

        try (ResultSet rs = ps.executeQuery()) {
            if (!rs.next()) {
                return false;
            }

            try (InputStream input = rs.getBinaryStream("content")) {
                if (input != null) {
                    input.transferTo(destination);
                }
            }
        }
    }

    return true;
}
~~~

`destination` do bên gọi sở hữu; repository **không đóng** nó vì đó không phải tài nguyên repository tạo ra. Chỉ `input`, result set, statement và connection được đóng trong method. Nếu cột `content` là SQL NULL, ví dụ giữ nguyên output stream và trả `true` để nói hàng tồn tại; ứng dụng có thể phân biệt trường hợp này qua một kiểu kết quả riêng.

**Khi trả dữ liệu qua HTTP:** nếu `destination` là luồng phản hồi mạng và DB/connection xảy ra lỗi giữa chừng, một phần body có thể đã được gửi. Không thể thu hồi bytes đã gửi; tầng API phải có chiến lược báo lỗi, giới hạn dữ liệu, timeout và hành vi retry phù hợp. Giữ connection mở trong suốt thời gian client tải chậm cũng có chi phí, nên cân nhắc thiết kế truyền tải/tạm lưu theo quy mô.

### 8.3. Các kiểu dữ liệu khác

`Blob`, `Clob`, `NClob`, `SQLXML`, `Array` và `Ref` có các chi tiết quản lý tài nguyên phụ thuộc driver. Một số kiểu công bố phương thức `free()`; với những đối tượng mà code đã lấy quyền sở hữu, cần giải phóng theo hợp đồng. Không giả định rằng giữ một locator Java sẽ tự giữ connection hợp lệ.

Ngược lại, `String` và các giá trị Java đã được đọc đầy đủ thường an toàn để trả về. Với XML/JSON hoặc object riêng của driver, phải kiểm tra đối tượng trả về là **bản sao dữ liệu** hay **view lazy** dựa vào JDBC.

## 9. Dùng `try-with-resources` để đóng đúng thứ tự

Mẫu thường dùng:

~~~java
try (Connection connection = dataSource.getConnection();
     PreparedStatement statement = connection.prepareStatement(sql)) {

    try (ResultSet rs = statement.executeQuery()) {
        while (rs.next()) {
            // Đọc dữ liệu và tạo DTO trong phạm vi này.
        }
    }
}
~~~

Java đóng các tài nguyên theo **thứ tự ngược với thứ tự khai báo**:

~~~text
Khi mở:   Connection -> PreparedStatement -> ResultSet
Khi đóng: ResultSet -> PreparedStatement -> Connection
~~~

Ngay cả khi code có `return` bên trong, hoặc `rs.next()`/mapper ném exception, Java vẫn đi qua các lệnh đóng tương ứng. Nếu một thao tác trong `try` thất bại và `close()` cũng thất bại, Java giữ exception chính và bổ sung lỗi đóng dưới dạng **suppressed exception**.

~~~java
try (Connection connection = dataSource.getConnection();
     PreparedStatement statement = connection.prepareStatement(sql);
     ResultSet rs = statement.executeQuery()) {
    // ...
} catch (SQLException primary) {
    System.err.println("SQLState: " + primary.getSQLState());
    for (Throwable suppressed : primary.getSuppressed()) {
        System.err.println("Lỗi khi đóng tài nguyên: "
                + suppressed.getClass().getSimpleName());
    }
    throw primary;
}
~~~

Không cần tự gọi `close()` một lần nữa trong `finally` nếu tài nguyên đã được quản lý bởi `try-with-resources`. Ngược lại, **không bỏ qua lỗi đóng/rollback quan trọng** bằng cách bắt mọi exception rồi trả một kết quả giả thành công.

### 9.1. Nếu không sở hữu connection, đừng đóng connection đó

Trong một transaction được quản lý ở tầng service hoặc framework, helper repository có thể nhận `Connection` do bên gọi cung cấp:

~~~java
public static long countUsers(Connection connection)
        throws SQLException {
    try (PreparedStatement ps = connection.prepareStatement(
            "SELECT COUNT(*) FROM app_user");
         ResultSet rs = ps.executeQuery()) {

        if (!rs.next()) {
            throw new SQLException("COUNT(*) không trả về kết quả");
        }

        return rs.getLong(1);
    }
}
~~~

Helper sở hữu và đóng `PreparedStatement`/`ResultSet` mình tạo ra; **không đóng `connection`** vì bên gọi hoặc transaction manager sở hữu connection. Quy ước này cần được nói rõ trong tên phương thức, API contract hoặc tài liệu, để không có hai tầng cùng cho rằng mình phải đóng một tài nguyên.

## 10. Connection pool không kéo dài quyền sử dụng đối tượng JDBC

Với pool, đoạn code sau vẫn sai:

~~~java
Connection connection = dataSource.getConnection();
PreparedStatement ps =
        connection.prepareStatement("SELECT id FROM app_user");
ResultSet rs = ps.executeQuery();

connection.close(); // Trả logical connection về pool.
rs.next();          // Không hợp lệ để dựa vào nữa.
~~~

Dù connection vật lý được pool giữ lại, **quyền mượn đã kết thúc**. Hơn nữa, pool có thể cấp connection đó cho request khác; giữ statement/result set còn sống có thể tạo ra tương tác không mong đợi và làm hỏng tính cách ly giữa request.

Một API repository tốt thường:

- Mượn kết nối chỉ khi chuẩn bị làm SQL.
- Đọc và ánh xạ đầy đủ dữ liệu khi connection còn hợp lệ.
- Đóng statement/result set đúng chỗ và trả connection về pool sớm.
- Trả DTO, số đếm hoặc báo cáo kết quả không phụ thuộc session JDBC.
- Nếu transaction do framework sở hữu, dùng cơ chế quản lý connection của framework và không tự cắt ngắn vòng đời transaction.

**Không lưu `Connection`, `Statement` hoặc `ResultSet` vào field static, singleton, HTTP session hay cache ứng dụng** để dùng lại sau phạm vi request/transaction. Tái sử dụng kết nối là trách nhiệm của pool, không phải của repository bằng cách giữ proxy connection.

## 11. Transaction làm ranh giới hiệu lực chặt hơn

Không phải chỉ đóng statement mới làm resource mất hiệu lực; thao tác transaction có thể ảnh hưởng con trỏ:

- `commit()` có thể đóng hoặc giữ cursor, tùy **result set holdability** và DBMS.
- `rollback()`, lỗi SQL nghiêm trọng hoặc mất kết nối có thể làm cursor không còn hoạt động.
- Một số database cần transaction mở để stream/fetch các hàng; kết thúc transaction sớm khiến dữ liệu phía client chưa được lấy đủ.
- `ResultSet.HOLD_CURSORS_OVER_COMMIT` có nghĩa driver công bố hỗ trợ giữ cursor qua commit theo điều kiện của nó, **không có nghĩa được giữ cursor qua đóng statement/connection**.

Ví dụ về cách kiểm tra:

~~~java
DatabaseMetaData metadata = connection.getMetaData();

boolean supported = metadata.supportsResultSetHoldability(
        ResultSet.HOLD_CURSORS_OVER_COMMIT);

int actual = connection.getHoldability();
System.out.println("Can hold over commit: " + supported);
System.out.println("Current holdability: " + actual);
~~~

Kiểm tra metadata giúp hiểu khả năng của driver, nhưng API repository vẫn nên trả dữ liệu đã materialize nếu tầng gọi cần dùng sau transaction.

### 11.1. Không tách kết quả lazy khỏi transaction

Trong một service:

~~~text
begin transaction
  repository: query và trả lazy cursor/stream
end transaction
controller: duyệt cursor/stream  <-- vòng đời đã kết thúc
~~~

Ngay cả khi transaction manager không đóng connection vật lý tức thì, tầng controller đã đi ra ngoài hợp đồng transaction. Thiết kế an toàn là **duyệt và ánh xạ trong transaction** hoặc thiết kế lại thành phân trang/đọc từng đợt độc lập.

## 12. Bất đồng bộ và đa luồng

Một lỗi khác là trả `ResultSet` cho một `CompletableFuture` hoặc callback chạy **sau** khi repository đóng tài nguyên:

~~~java
// SAI: task có thể chạy sau khi connection đã đóng.
try (Connection connection = dataSource.getConnection();
     PreparedStatement ps = connection.prepareStatement(sql);
     ResultSet rs = ps.executeQuery()) {

    CompletableFuture.runAsync(() -> processLater(rs));
}
~~~

`processLater(rs)` là helper giả định; vấn đề chính là một thread khác được trao resource phụ thuộc vào connection sắp đóng. Ngoài vòng đời, phần lớn thao tác JDBC trên cùng một connection/result set cũng không thể mặc định dùng đồng thời an toàn giữa các thread.

**Cách phù hợp:** Tác vụ async tự mở và đóng connection **trong chính phạm vi tác vụ**, sau đó trả DTO đã materialize.

~~~java
import java.sql.SQLException;
import java.util.List;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.Executor;

public CompletableFuture<List<UserRepository.User>> findAsync(
        Executor executor,
        UserQueryService service) {

    return CompletableFuture.supplyAsync(() -> {
        try {
            // Service tự quản lý JDBC resource trong worker thread.
            return service.loadUsers();
        } catch (SQLException ex) {
            throw new CompletionException(ex);
        }
    }, executor);
}
~~~

`UserQueryService.loadUsers()` trong ví dụ là API đọc dữ liệu đã materialize do ứng dụng cung cấp. Để áp dụng thực tế, bảo đảm connection được mượn/đóng **bên trong** `loadUsers()` hoặc transaction hợp lệ của thread đó. Không truyền `Connection` đã mượn trong request thread vào task không có hợp đồng đồng bộ hóa và vòng đời phù hợp.

Nếu triển khai reactive API hoặc server-sent events, hãy chọn thư viện và transaction/resource-management tương thích với mô hình reactive; một `Stream` từ JDBC blocking không tự nhiên trở thành luồng reactive an toàn chỉ nhờ đổi tên kiểu trả về.

## 13. API nên trả gì? So sánh các lựa chọn

| Kiểu trả về từ repository | Độ an toàn sau khi đóng JDBC | Khi nào phù hợp? |
| --- | --- | --- |
| `Optional<User>` hoặc `User` đã materialize | Cao, nếu trường dữ liệu không còn phụ thuộc JDBC. | Truy vấn một hàng. |
| `List<User>` đã materialize | Cao, cần giới hạn số hàng và nhớ. | Danh sách nhỏ/vừa, phân trang. |
| `long`/`BigDecimal`/báo cáo thống kê | Cao, giá trị đã đọc xong. | COUNT, SUM, aggregation. |
| `byte[]`/`String` đã đọc đủ | Hợp lệ sau đóng JDBC nhưng có thể tốn RAM; `byte[]` mutable. | LOB nhỏ có giới hạn. |
| `ResultSet` trực tiếp | Thấp nếu repository đóng connection; nếu chuyển ownership thì rất dễ dùng sai. | Chỉ API hạ tầng sở hữu resource tường minh, hiếm khi cho service/controller. |
| `Stream<User>` lazy đọc `ResultSet` | Nguy hiểm nếu không có contract đóng stream và giữ transaction rõ ràng. | Chỉ trong abstraction quản lý vòng đời chuyên biệt. |
| `InputStream` từ `getBinaryStream()` | Không bảo đảm còn dùng được sau đóng JDBC. | Ưu tiên copy qua callback/OutputStream trong scope hợp lệ. |
| Callback đồng bộ nhận DTO từng hàng | Cao nếu callback không giữ resource JDBC. | Export, batch processing, xử lý tập dữ liệu lớn. |

**Điểm quyết định không phải tên kiểu trả về, mà là phụ thuộc còn sống hay không.** Một DTO chứa `Supplier<String>` tiếp tục đọc từ `ResultSet` cũng không an toàn, dù lớp DTO trông như đối tượng nghiệp vụ. Ngược lại, callback xử lý `UserRow` đã copy có thể rất an toàn khi JDBC resources được quản lý trọn trong repository.

## 14. Xử lý lỗi và đảm bảo tính đúng đắn

Một phương thức JDBC có nhiều vị trí có thể thất bại: lấy connection, tạo statement, bind tham số, thực thi SQL, `rs.next()`, ánh xạ từng cột, đóng tài nguyên. API tốt phải:

1. **Đóng mọi tài nguyên đã mở** khi có exception, ưu tiên `try-with-resources`.
2. **Không trả kết quả nửa vời như kết quả thành công**, trừ khi hợp đồng API có hỗ trợ dữ liệu một phần và trạng thái rõ ràng.
3. **Bảo toàn nguyên nhân gốc**: giữ `SQLException` hoặc bọc nó cùng cause, bao gồm `SQLState`/vendor code khi cần điều tra.
4. **Không retry mù quáng** sau lỗi ghi hoặc lỗi mạng: thao tác có thể đã được áp dụng một phần.
5. **Giữ exception close/rollback** như thông tin bổ sung, không che lỗi SQL nghiệp vụ chính.
6. **Định nghĩa ownership khi nhận tài nguyên đầu vào**: ví dụ repository không đóng `OutputStream` hoặc connection do caller sở hữu, trừ khi hợp đồng nói rõ chuyển giao.

Nếu API cần phân biệt “không tìm thấy dữ liệu” với “truy vấn thất bại”, `Optional.empty()` nên chỉ đại diện cho **không có hàng**. Không bắt `SQLException` rồi đổi thành `Optional.empty()`, vì như vậy kết quả có vẻ hợp lệ trong khi database đang lỗi.

## 15. Kiểm thử việc không trả tài nguyên hết hiệu lực

Chỉ đọc dữ liệu khi tài nguyên còn mở chưa đủ để chứng minh thiết kế API. Nên có test theo các góc sau:

| Tình huống test | Điều cần xác minh |
| --- | --- |
| Truy vấn trả một hàng | DTO vẫn đọc được sau khi repository return và connection được đóng/trả pool. |
| Không tìm thấy hàng | API trả `Optional.empty()`/kết quả được quy định, không rò rỉ tài nguyên. |
| Mapper ném exception giữa chừng | `ResultSet`, statement và connection vẫn được đóng; lỗi gốc được giữ. |
| Lấy nhiều hàng | Danh sách là dữ liệu hoàn chỉnh, không chứa `ResultSet`/supplier lazy. |
| Đọc BLOB nhỏ | Bytes/String đã được copy; cần test giới hạn kích thước và tính mutable nếu công bố qua DTO. |
| Copy BLOB lớn | Stream nguồn được đóng ngay cả khi copy lỗi; caller sở hữu output stream. |
| Callback lỗi ở hàng N | JDBC resources đóng và tác động phía callback được xử lý như partial output. |
| Transaction commit/rollback | Không truy cập cursor sau khi transaction kết thúc; kết quả đã map vẫn hợp lệ. |
| Pool tái sử dụng connection | Không giữ JDBC resource từ lần mượn cũ; số connection active trở lại baseline. |

Có thể dùng integration test với database test, pool theo dõi active/idle và statement/connection wrapper có counters. Khi test tác vụ lớn, quan sát cả memory, connection hold time và việc hủy giữa chừng; một implementation luôn materialize có thể đúng về lifetime nhưng thiếu giới hạn RAM.

### 15.1. Ví dụ test hành vi ngoài phạm vi connection

~~~java
// Pseudocode trong test tích hợp:
Optional<UserRepository.User> result = repository.findById(101L);

// Đến thời điểm này, method đã trả kết quả và tài nguyên trong
// try-with-resources của repository đã được đóng.
assertTrue(result.isPresent());
assertEquals("Lan", result.orElseThrow().name());

// Dùng wrapper/pool metrics để xác minh connection đã được trả về.
// Không cần và không nên truy cập ResultSet từ test caller.
~~~

Test kiểm tra dữ liệu **sau khi resource scope kết thúc**, đồng thời kiểm tra cleanup ở phía driver/pool. Đó mới là bằng chứng về hợp đồng API, thay vì chỉ kiểm tra truy vấn đúng SQL trong thân phương thức.

## 16. Bài tập tình huống

Một API `GET /orders` đang hoạt động như sau:

~~~java
public ResultSet findOrders() throws SQLException {
    Connection connection = dataSource.getConnection();
    PreparedStatement ps = connection.prepareStatement(
            "SELECT id, total_amount FROM orders");
    return ps.executeQuery();
}
~~~

Controller duyệt `ResultSet` để chuyển thành JSON và quên đóng statement. Khi số request tăng, pool báo timeout.

**Yêu cầu sửa:** 

- Chuyển repository thành `List<OrderDto> findOrders(limit, offset)`, sử dụng `PreparedStatement` với phân trang theo cú pháp DBMS đích.
- Đọc `ResultSet` và tạo `OrderDto` trong `try-with-resources`; đóng connection đúng chỗ.
- Controller chỉ tuần tự hóa DTO, không biết `ResultSet`/`Connection`.
- Với export lượng lớn, dùng API callback đồng bộ hoặc pagination có giới hạn thay vì trả `ResultSet` cho controller.
- Kiểm thử cùng một endpoint khi truy vấn thành công, trả 0 hàng, lỗi giữa chừng và dưới tải đồng thời; xác minh pool active/idle trở lại trạng thái mong đợi.

~~~mermaid
flowchart LR
    A[Controller] -->|gọi API| B[OrderRepository]
    B -->|mượn| C[Connection]
    C --> D[PreparedStatement]
    D --> E[ResultSet]
    E -->|map từng hàng| F[OrderDto List]
    F -->|trả về sau close| A
    E -->|close| D
    D -->|close| C
    C -->|close / return pool| G[DataSource]
~~~

Đầu ra đúng của repository là **danh sách đối tượng độc lập**, còn resource lifetime của JDBC nằm trọn bên trong tầng sở hữu.

## 17. Checklist thiết kế API an toàn với vòng đời JDBC

- [ ] Xác định ai sở hữu `Connection`, `Statement` và `ResultSet`; ownership được ghi rõ trong API contract.
- [ ] Không trả `ResultSet`, `Statement`, `Connection` hoặc stream phụ thuộc chúng từ phương thức sẽ đóng tài nguyên.
- [ ] Đọc và materialize DTO/record hoặc giá trị Java trước khi resource scope kết thúc.
- [ ] Với truy vấn lớn, chọn phân trang hoặc callback xử lý từng hàng; đánh giá thời gian giữ connection và bộ nhớ.
- [ ] Không để `Stream`/`Iterator`/`Supplier` lazy giữ tham chiếu tới result set đã đóng.
- [ ] Kiểm tra `Blob`/`Clob`/`SQLXML`/stream và giải phóng resource theo hợp đồng driver.
- [ ] Đóng tài nguyên theo `try-with-resources`, giữ exception gốc và suppressed exception khi cần.
- [ ] Không tự đóng connection do transaction manager hoặc caller sở hữu.
- [ ] Không tiếp tục dùng connection/proxy JDBC sau khi `close()` trả về pool.
- [ ] Không chuyển resource JDBC sang công việc async kết thúc sau resource scope.
- [ ] Có test cho nhánh thành công, không có hàng, exception, transaction và pool reuse.
- [ ] Không che lỗi SQL bằng danh sách rỗng hoặc `Optional.empty()` giả thành công.

**Ghi nhớ:** Khi thiết kế API JDBC, hãy làm cho **vòng đời của giá trị trả về độc lập với vòng đời của tài nguyên kết nối**. Repository hoặc transaction manager sở hữu việc đóng; các tầng bên ngoài làm việc với dữ liệu đã đọc xong. Nếu cần xử lý theo luồng, hãy đặt việc tiêu thụ dữ liệu trong phạm vi JDBC còn mở với ownership rõ ràng, để không vừa trả resource hết hiệu lực vừa làm rò rỉ kết nối.
