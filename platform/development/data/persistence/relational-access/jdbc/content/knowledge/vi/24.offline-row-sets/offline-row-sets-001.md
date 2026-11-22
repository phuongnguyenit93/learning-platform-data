# Phân biệt `ResultSet` đang kết nối và dữ liệu có thể tách kết nối trong JDBC

## 1. Vì sao cần phân biệt hai cách sử dụng dữ liệu?

Trong **JDBC (Java Database Connectivity)** — API Java dùng để truy cập cơ sở dữ liệu quan hệ — chương trình thường chạy câu lệnh SQL rồi đọc các hàng thông qua `java.sql.ResultSet`. Với cách làm này, `ResultSet` gắn với câu lệnh và vòng đời tài nguyên JDBC đã tạo ra nó. Mã xử lý phải đọc kết quả trong khi các tài nguyên liên quan còn hợp lệ.

Tuy nhiên, không phải lúc nào ứng dụng cũng muốn giữ kết nối đến database trong suốt thời gian xử lý dữ liệu. Chẳng hạn:

- Một màn hình quản trị cần lấy danh sách bản ghi rồi cho người dùng xem, lọc hoặc chuyển trang ngay trên dữ liệu đã tải.
- Một thành phần cần nhận dữ liệu từ repository để xử lý sau khi repository đã trả kết nối về pool.
- Một tác vụ cần sao chép một tập bản ghi vừa phải để duyệt lại nhiều lần mà không giữ cursor database mở.
- Một ứng dụng máy tính có thể xem dữ liệu đã tải khi tạm thời không kết nối mạng.

JDBC có hai hướng xử lý khác nhau: **làm việc trực tiếp với `ResultSet` còn gắn với tài nguyên JDBC**, hoặc **sao chép dữ liệu thành cấu trúc độc lập có thể dùng sau khi đóng kết nối**, tiêu biểu là `javax.sql.rowset.CachedRowSet`.

Điểm cốt lõi: `ResultSet` không tự biến thành dữ liệu ngoại tuyến chỉ vì bạn đã đọc một vài hàng; dữ liệu cần được sao chép/ánh xạ **trước khi** đóng các tài nguyên nguồn.

## 2. `ResultSet` đang kết nối hoạt động như thế nào?

### 2.1. Mối liên hệ với `Statement` và `Connection`

Một luồng truy vấn JDBC thường có dạng:

~~~mermaid
flowchart LR
    A["Ứng dụng"] --> B["DataSource / DriverManager"]
    B --> C["Connection"]
    C --> D["PreparedStatement"]
    D --> E["ResultSet"]
    D --> F[("Database")]
    F --> D
    E --> G["Đọc từng hàng khi<br/>tài nguyên còn hợp lệ"]
~~~

Sau khi gọi `PreparedStatement.executeQuery()`, ứng dụng nhận `ResultSet` để dùng các phương thức:

- `next()` đưa con trỏ sang hàng tiếp theo, trả `false` khi đã hết.
- `getLong(...)`, `getString(...)`, `getBigDecimal(...)` và các getter khác đọc giá trị cột tại hàng hiện tại.
- `getMetaData()` đọc thông tin về các cột của kết quả.
- `close()` giải phóng tài nguyên gắn với `ResultSet`.

`ResultSet` thường được tạo với kiểu `TYPE_FORWARD_ONLY`, nghĩa là chỉ duyệt tiến theo thứ tự các hàng; các kiểu `TYPE_SCROLL_INSENSITIVE` và `TYPE_SCROLL_SENSITIVE` có thể cho phép di chuyển con trỏ theo cách khác nếu driver hỗ trợ. **Có thể cuộn không đồng nghĩa với có thể tách kết nối**: một `ResultSet` scrollable vẫn chịu ràng buộc bởi vòng đời JDBC.

Một driver có thể truyền dữ liệu theo từng nhóm hàng, hoặc nạp trước một phần/toàn bộ kết quả. Vì vậy, "đang kết nối" mô tả **mối liên hệ quản lý tài nguyên**, không khẳng định mọi lệnh `next()` đều bắt buộc thực hiện một lần truy cập mạng.

### 2.2. Vòng đời và quy tắc đóng tài nguyên

`ResultSet` phụ thuộc vào `Statement` đã tạo ra nó. Khi `Statement` đóng, `ResultSet` hiện hành của nó cũng đóng; việc thực thi lại cùng `Statement` cũng có thể đóng kết quả hiện hành. Đóng `Connection` giải phóng các tài nguyên JDBC liên quan, nên không nên sử dụng `ResultSet` sau khi rời khỏi phạm vi kết nối.

Ví dụ truy vấn và xử lý trực tiếp:

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import javax.sql.DataSource;

public final class ConnectedResultExample {
    public static void printActiveCustomers(DataSource dataSource)
            throws SQLException {

        String sql = "SELECT id, email FROM customers WHERE active = ?";

        try (Connection connection = dataSource.getConnection();
             PreparedStatement statement = connection.prepareStatement(sql)) {

            statement.setBoolean(1, true);

            try (ResultSet resultSet = statement.executeQuery()) {
                while (resultSet.next()) {
                    long id = resultSet.getLong("id");
                    String email = resultSet.getString("email");
                    System.out.printf("%d: %s%n", id, email);
                }
            }
        }
    }
}
~~~

**Vì sao đúng?** Mọi lần `next()` và `getString()` diễn ra bên trong phạm vi `try-with-resources`, khi kết nối, câu lệnh và kết quả còn mở. Tài nguyên được đóng tự động theo thứ tự ngược với thứ tự khởi tạo; nếu dùng connection pool, `Connection.close()` thường trả kết nối logic về pool.

**Lỗi thiết kế thường gặp:** tạo `ResultSet` trong DAO rồi trả thẳng đối tượng này cho tầng gọi, trong khi DAO đã đóng `Statement` hoặc `Connection`. Tầng gọi có thể nhận lỗi vì kết quả đã đóng. Giữ kết nối mở chỉ để cho phép tầng khác dùng `ResultSet` cũng dễ làm cạn pool hoặc giữ transaction quá lâu.

### 2.3. Dùng `ResultSet` khi nào?

Khi dữ liệu có nhiều hàng và có thể xử lý tuần tự ngay trong phạm vi kết nối, `ResultSet` thường phù hợp. Nó cho phép ứng dụng tránh giữ toàn bộ kết quả trong một collection riêng. Mức sử dụng bộ nhớ thực tế vẫn phụ thuộc driver, chế độ cursor, `fetchSize`, transaction và khả năng streaming của database.

Gọi `Statement.setFetchSize(int)` có thể đưa ra **gợi ý** về số hàng driver lấy mỗi đợt; đây không phải cam kết mọi driver sẽ streaming theo cùng cách. `ResultSet` không nên được chia sẻ tùy tiện giữa các thread, và không thích hợp để sử dụng sau khi đã đóng kết nối nguồn.

## 3. Dữ liệu có thể tách kết nối là gì?

**Dữ liệu tách kết nối (disconnected data)** là dữ liệu đã được sao chép khỏi kết quả truy vấn vào một cấu trúc có vòng đời độc lập. Sau bước tải, có thể đóng `ResultSet`, `Statement`, `Connection` mà vẫn đọc được bản sao đó.

Hai lựa chọn phổ biến là:

1. **Ánh xạ thành DTO hoặc collection Java** như `List<CustomerDto>`. Đây là cách thường gặp ở repository và web API; ứng dụng kiểm soát chính xác trường dữ liệu được giữ lại.
2. **Dùng `CachedRowSet`** thuộc gói `javax.sql.rowset`, một kiểu `RowSet` lưu dữ liệu theo dạng hàng/cột cùng metadata trong bộ nhớ, hỗ trợ di chuyển con trỏ và một số thao tác cập nhật ngoại tuyến.

~~~mermaid
sequenceDiagram
    participant App as Ứng dụng
    participant JDBC as Connection / ResultSet
    participant DB as Database
    participant Cache as CachedRowSet
    App->>JDBC: Mở kết nối và chạy SQL
    JDBC->>DB: Thực thi truy vấn
    DB-->>JDBC: Các hàng kết quả
    App->>Cache: populate(ResultSet)
    JDBC-->>App: Đã sao chép dữ liệu
    App->>JDBC: Đóng ResultSet / Statement / Connection
    Note over Cache: Vẫn giữ dữ liệu đã tải trong bộ nhớ
    App->>Cache: next(), getString(), absolute()...
    Cache-->>App: Dữ liệu bản sao
~~~

Đóng kết nối nguồn **không làm bản sao tự mất đi**, nhưng cũng **không làm bản sao tự cập nhật** khi dữ liệu trên database thay đổi. Tính nhất quán tại thời điểm đọc còn phụ thuộc isolation level và cách database thực thi truy vấn; việc lưu một `CachedRowSet` không tự tạo thêm bảo đảm transaction snapshot.

## 4. Bảng so sánh `ResultSet` và dữ liệu tách kết nối

| Tiêu chí | `ResultSet` gắn với JDBC | Dữ liệu tách kết nối / `CachedRowSet` |
|---|---|---|
| Quan hệ với database | Dùng trong phạm vi các tài nguyên JDBC còn hợp lệ | Sau khi sao chép đầy đủ có thể đóng kết nối nguồn |
| Nơi lưu dữ liệu | Tùy driver: cursor, bộ đệm driver hoặc phía server | Tập dữ liệu sao chép trong bộ nhớ ứng dụng |
| Cách duyệt | Thường tiến từng hàng; cuộn nếu kiểu và driver hỗ trợ | Có thể duyệt tiến/lùi, tìm hàng theo vị trí trên bản sao |
| Chi phí bộ nhớ ứng dụng | Có thể nhỏ khi đọc tuần tự/streaming, tùy driver | Tăng theo số hàng, cột và kích thước dữ liệu đã tải |
| Thời gian giữ connection | Suốt giai đoạn sử dụng `ResultSet` | Chỉ cần khi tải dữ liệu và khi đồng bộ lại (nếu có) |
| Độ mới của dữ liệu | Phụ thuộc transaction và database trong thời gian đọc | Là dữ liệu tại lần tải gần nhất; có thể nhanh chóng cũ |
| Cập nhật dữ liệu | `ResultSet` có thể cập nhật nếu loại concurrency/driver cho phép | Có thể sửa bản sao; ghi về database là bước riêng |
| Trường hợp điển hình | Export lớn, xử lý tuần tự, đọc nhanh trong DAO | Danh sách nhỏ/vừa, xem offline, cần duyệt lại nhiều lần |
| Quản lý tài nguyên | Phải đóng kết quả, câu lệnh và kết nối kịp thời | Vẫn phải đóng tài nguyên nguồn và giải phóng bản sao khi xong |

**Lưu ý:** `TYPE_SCROLL_INSENSITIVE` không biến `ResultSet` thành `CachedRowSet`. Hai khái niệm giải quyết các vấn đề khác nhau: *điều hướng con trỏ* và *phụ thuộc vòng đời kết nối*.

## 5. `CachedRowSet` hoạt động ra sao?

### 5.1. Vị trí trong hệ thống API

Trong Java SE:

- `java.sql.ResultSet` mô tả dữ liệu kết quả từ truy vấn JDBC.
- `javax.sql.RowSet` mở rộng `ResultSet` và bổ sung đặc điểm JavaBeans cùng cơ chế sự kiện.
- `javax.sql.rowset.CachedRowSet` mở rộng `RowSet` và hỗ trợ dữ liệu cache có thể sử dụng khi tách kết nối.
- `javax.sql.rowset.RowSetProvider` cung cấp cách tạo implementation `RowSet` qua factory.

Không phải mọi `RowSet` đều ngoại tuyến. Chẳng hạn, `javax.sql.rowset.JdbcRowSet` là loại **đang kết nối** và bọc một `ResultSet`; còn `CachedRowSet` được thiết kế cho mô hình disconnected. Các kiểu như `WebRowSet`, `FilteredRowSet` và `JoinRowSet` hỗ trợ những cách biểu diễn, lọc hoặc kết hợp dữ liệu chuyên biệt.

Từ Java 9, hai API `ResultSet` và `RowSet` thuộc module `java.sql`, còn `javax.sql.rowset.CachedRowSet` và `RowSetProvider` thuộc module `java.sql.rowset`. Nếu dùng Java named modules, cần khai báo module phụ thuộc tương ứng.

### 5.2. Ví dụ: tải vào `CachedRowSet`, đóng connection rồi mới đọc

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import javax.sql.DataSource;
import javax.sql.rowset.CachedRowSet;
import javax.sql.rowset.RowSetProvider;

public final class DisconnectedRowSetExample {
    public static void printSnapshot(DataSource dataSource)
            throws SQLException {

        String sql = "SELECT id, email FROM customers WHERE active = ?";

        try (CachedRowSet cached =
                     RowSetProvider.newFactory().createCachedRowSet()) {

            // Pha 1: tải bản sao khi Connection và ResultSet đang mở.
            try (Connection connection = dataSource.getConnection();
                 PreparedStatement statement = connection.prepareStatement(sql)) {

                statement.setBoolean(1, true);
                statement.setMaxRows(100); // Giới hạn dữ liệu được tải cho ví dụ.

                try (ResultSet resultSet = statement.executeQuery()) {
                    cached.populate(resultSet);
                }
            } // ResultSet, PreparedStatement, Connection đều đã đóng.

            // Pha 2: đọc bản sao mà không cần Connection nguồn.
            cached.beforeFirst();
            while (cached.next()) {
                System.out.printf("%d: %s%n",
                        cached.getLong("id"),
                        cached.getString("email"));
            }
        }
    }
}
~~~

Điểm cần chú ý:

1. `CachedRowSet` được tạo trước; `populate(resultSet)` **sao chép** dữ liệu khi `ResultSet` còn mở.
2. Sau khi kết thúc khối `try` bên trong, các tài nguyên JDBC nguồn đã được đóng.
3. `cached.beforeFirst()` và `cached.next()` vẫn hoạt động trên dữ liệu nội bộ, không cần truy vấn lại database.
4. `cached.close()` cũng quan trọng để giải phóng tài nguyên bản sao; `try-with-resources` tự gọi khi kết thúc.

Giả định ví dụ có bảng `customers` với các cột `id`, `email`, `active` và `DataSource` đã cấu hình. `setMaxRows(100)` được dùng để giảm lượng dữ liệu lấy về; ứng dụng thực tế vẫn nên thiết kế **lọc và phân trang trong SQL** để quản lý dung lượng, vì cache toàn bộ một bảng lớn có thể gây áp lực bộ nhớ.

### 5.3. Có thể tạo RowSet và tự thực hiện truy vấn

Ngoài `populate(ResultSet)`, `CachedRowSet` còn hỗ trợ cấu hình câu SQL, tham số và nguồn kết nối để gọi `execute()` rồi hoạt động tách kết nối. Cách này phụ thuộc implementation và cấu hình của `RowSet`.

Ý tưởng luồng xử lý:

~~~text
CachedRowSet + command/parameters + thông tin kết nối
    -> execute() tải dữ liệu từ database
    -> lưu hàng và metadata trong cache
    -> thao tác duyệt/chỉnh sửa cache sau khi tách kết nối
~~~

Với ứng dụng dùng `DataSource`/DI và muốn kiểm soát chính xác query, ví dụ `populate(ResultSet)` thường minh bạch hơn vì các bước cấp kết nối, thực thi SQL và đóng tài nguyên đều thể hiện rõ.

## 6. Dữ liệu ngoại tuyến không đồng nghĩa với tự động ghi về database

Sau khi tải `CachedRowSet`, bạn có thể cập nhật bản sao bằng các phương thức tương ứng với `ResultSet`, chẳng hạn `updateString(...)` rồi `updateRow()`. Nhưng:

- `updateRow()` trên `CachedRowSet` trước hết cập nhật **trạng thái hàng trong bản sao**; không nên hiểu là đã ghi thành công về database.
- Để đồng bộ ngược, `CachedRowSet` cung cấp `acceptChanges()` hoặc `acceptChanges(Connection)`. Việc đồng bộ phụ thuộc `SyncProvider`, dữ liệu định danh hàng, quyền truy cập và cấu hình nguồn dữ liệu.
- Giữa thời điểm tải và thời điểm đồng bộ, người khác có thể đã sửa/xóa cùng bản ghi. Đồng bộ có thể thất bại và báo `SyncProviderException`, cần chiến lược giải quyết xung đột.
- Đồng bộ nhiều thay đổi về database là thao tác thực sự có thể phát sinh lỗi hoặc cần transaction; không nên giả định luôn nguyên tử hoặc tương đương với một câu SQL đơn giản.

Ví dụ luồng trạng thái:

~~~mermaid
flowchart TD
    A["Tải dữ liệu vào CachedRowSet"] --> B["Đọc / sửa hàng trên bản sao"]
    B --> C{"Có cần ghi ngược?"}
    C -- "Không" --> D["Dùng dữ liệu snapshot rồi đóng RowSet"]
    C -- "Có" --> E["acceptChanges() qua SyncProvider"]
    E --> F{"Đồng bộ thành công?"}
    F -- "Có" --> G["Database nhận thay đổi"]
    F -- "Lỗi / xung đột" --> H["Xác minh trạng thái, xử lý xung đột, tải lại nếu cần"]
~~~

Nếu mục tiêu chỉ là trả dữ liệu để hiển thị, bạn **không cần** đồng bộ `CachedRowSet` trở lại. Với cập nhật nghiệp vụ thông thường, thực hiện `INSERT`/`UPDATE`/`DELETE` trực tiếp bằng `PreparedStatement` trong transaction được quản lý rõ ràng thường dễ kiểm soát và kiểm thử hơn.

## 7. Cách khác: ánh xạ `ResultSet` sang DTO hoặc `List`

**Disconnected data** là một *cách quản lý vòng đời dữ liệu*, không bắt buộc phải dùng `CachedRowSet`. Ở ứng dụng web hoặc service, ánh xạ kết quả sang kiểu Java phù hợp thường là lựa chọn rõ ràng hơn:

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.ArrayList;
import java.util.List;
import javax.sql.DataSource;

public final class CustomerEmailRepository {
    private final DataSource dataSource;

    public CustomerEmailRepository(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public List<String> findActiveEmails() throws SQLException {
        List<String> emails = new ArrayList<>();
        String sql = "SELECT email FROM customers WHERE active = ?";

        try (Connection connection = dataSource.getConnection();
             PreparedStatement statement = connection.prepareStatement(sql)) {
            statement.setBoolean(1, true);

            try (ResultSet resultSet = statement.executeQuery()) {
                while (resultSet.next()) {
                    emails.add(resultSet.getString("email"));
                }
            }
        }
        return emails; // Dữ liệu vẫn dùng được sau khi Connection đã đóng.
    }
}
~~~

`List<String>` là một bản sao chứa giá trị đã được đọc, không mang theo cursor hay `Connection`. Khi repository trả về, dữ liệu vẫn dùng được. Nếu cần ngăn sửa collection từ phía caller, có thể trả bản sao không chỉnh sửa được, ví dụ `List.copyOf(emails)` khi chắc chắn không chứa phần tử `null`; ngoài ra có thể thiết kế DTO bất biến.

So sánh nhanh hai loại dữ liệu ngoại tuyến:

| | `CachedRowSet` | DTO / collection |
|---|---|---|
| Hình dạng dữ liệu | Dạng bảng/hàng/cột và metadata SQL | Kiểu rõ nghĩa theo nghiệp vụ |
| API xử lý | Điều hướng cursor, getter theo cột, có khả năng update cache | Collection/stream và phương thức của kiểu miền |
| Khả năng đồng bộ JDBC | Có API `acceptChanges` với các điều kiện và giới hạn | Cập nhật qua repository/service chủ động |
| Phù hợp | Công cụ dữ liệu, giao diện duyệt/biên tập tập kết quả, nhu cầu JDBC RowSet | API, service, domain model, mã ứng dụng thông thường |

## 8. Những đánh đổi khi tách kết nối

### 8.1. Bộ nhớ và số lượng bản ghi

Việc sao chép hàng sang `CachedRowSet` hoặc `List` tiêu tốn bộ nhớ theo số hàng và kích thước cột. Cột BLOB/CLOB, dữ liệu văn bản dài hoặc kết quả gồm hàng trăm nghìn bản ghi có thể gây áp lực heap đáng kể. Nếu cần xuất dữ liệu lớn, hãy cân nhắc đọc tuần tự và ghi ra đích ngay trong phạm vi connection, hoặc chia nhỏ truy vấn và có giới hạn rõ ràng.

### 8.2. Tính mới và tính nhất quán

Sau khi cache được tạo, mọi thay đổi bên ngoài đều **không tự phản ánh** vào cache. Ví dụ: ứng dụng tải tồn kho lúc 10:00; người khác bán hàng lúc 10:01; bản sao cũ không được dùng như số tồn kho có thẩm quyền để xác nhận đơn hàng lúc 10:05.

Tách kết nối không thay thế isolation, optimistic locking, kiểm tra version, transaction hoặc ràng buộc database. Mọi quyết định nghiệp vụ đòi hỏi dữ liệu mới nhất cần được xác nhận lại tại thời điểm cập nhật.

### 8.3. Tuổi thọ kết nối và độ trễ tải

`CachedRowSet` giúp **rút ngắn giai đoạn giữ connection** khi sau đó còn nhiều thao tác đọc dữ liệu trong ứng dụng. Đổi lại, ứng dụng phải trả chi phí sao chép toàn bộ tập kết quả mục tiêu trước khi xử lý ngoại tuyến. Một `ResultSet` xử lý tuần tự có thể thích hợp hơn cho dữ liệu rất lớn hoặc khi không cần duyệt nhiều lần.

### 8.4. Dữ liệu nhạy cảm

Khi sao chép dữ liệu khỏi database, thông tin nhạy cảm còn nằm trong bộ nhớ ứng dụng ngay cả sau khi kết nối đã đóng. Chỉ lấy các cột cần thiết, giới hạn kích thước và vòng đời cache, kiểm soát logging và serialization. "Không kết nối" không có nghĩa là dữ liệu đã được xóa hoặc an toàn để chia sẻ.

## 9. Tình huống chọn cách tiếp cận

| Tình huống | Lựa chọn thường phù hợp | Lý do |
|---|---|---|
| Đọc và tính toán trên từng hàng của tập kết quả rất lớn | `ResultSet` duyệt tuần tự | Có thể không cần nhân bản mọi hàng vào bộ nhớ ứng dụng |
| Repository trả dữ liệu cho service/API sau khi đã đóng kết nối | DTO / collection | Hợp đồng dữ liệu rõ ràng, không lộ tài nguyên JDBC |
| Công cụ Java cần nạp một tập kết quả nhỏ rồi duyệt nhiều lần và xem cột linh hoạt | `CachedRowSet` | Có dữ liệu dạng bảng và cursor độc lập |
| Công cụ có tính năng đọc dữ liệu tạm thời khi mất kết nối | `CachedRowSet` hoặc cache/DTO chuyên biệt | Có thể tiếp tục xem bản sao đã tải |
| Cần đảm bảo số dư/tồn kho mới nhất khi ghi | Truy vấn và transaction tại database | Dữ liệu ngoại tuyến có thể đã cũ |
| Cần cập nhật hàng đã tải rồi đồng bộ sau | `CachedRowSet` nếu hỗ trợ sync phù hợp, hoặc DTO + command rõ ràng | Phải xử lý định danh hàng, phiên bản và xung đột |

## 10. Các nhầm lẫn phổ biến

**“Đã dùng `TYPE_SCROLL_INSENSITIVE` thì có thể đóng connection rồi đọc tiếp?”** Không. Khả năng cuộn của cursor không loại bỏ ràng buộc vòng đời JDBC.

**“Driver đã tải hết kết quả về RAM thì `ResultSet` chắc chắn còn đọc được sau khi đóng `Statement`?”** Không. Dù nội bộ driver đệm dữ liệu, hợp đồng `ResultSet` vẫn gắn với tài nguyên nguồn; đóng `Statement` khiến `ResultSet` tương ứng đóng.

**“`RowSet` nào cũng ngoại tuyến?”** Không. `JdbcRowSet` là một ví dụ RowSet có kết nối, còn `CachedRowSet` phục vụ mô hình tách kết nối.

**“`CachedRowSet.updateRow()` đã cập nhật database?”** Không. Cần một bước đồng bộ riêng nếu muốn ghi lại và vẫn có khả năng gặp xung đột.

**“Có `CachedRowSet` thì không cần đóng tài nguyên?”** Không. Phải đóng `ResultSet`/`Statement`/`Connection` sau khi sao chép và giải phóng `CachedRowSet` khi xong.

**“Dữ liệu tách kết nối luôn nhanh hơn?”** Không. Nó đổi thời gian giữ kết nối lấy chi phí sao chép, bộ nhớ, nguy cơ dữ liệu cũ và có thể cần đồng bộ phức tạp.

## 11. Câu hỏi tự kiểm tra

1. Một phương thức DAO dùng `try-with-resources` để đóng `Connection` trước khi trả về. Vì sao trả `ResultSet` từ phương thức đó dễ bị lỗi? Nên trả kiểu nào?
2. Hai đối tượng đều cho phép gọi `absolute(10)`. Một đối tượng là `ResultSet` scrollable và đối tượng kia là `CachedRowSet`. Khác biệt lớn nhất về vòng đời kết nối là gì?
3. Khi một `CachedRowSet` đã được nạp dữ liệu, database thay đổi bản ghi. `CachedRowSet.next()` có tự nhìn thấy dữ liệu mới không?
4. Khi duyệt 1 triệu hàng để xuất CSV, bạn chọn `ResultSet` hay `CachedRowSet`? Những chi tiết nào của driver và database cần kiểm tra?
5. Khi sửa dữ liệu trong `CachedRowSet`, thao tác nào chỉ sửa bản sao, và bước nào mới thử đồng bộ ngược với database?

**Điểm cần nhớ:** `ResultSet` là cursor của một truy vấn JDBC có vòng đời gắn với các tài nguyên tạo ra nó. Muốn dữ liệu sử dụng được sau khi kết nối đóng, hãy **sao chép dữ liệu trước** vào DTO/collection hoặc `CachedRowSet`. Bản sao được quyền sống lâu hơn kết nối, nhưng phải tự quản lý bộ nhớ, tính mới của dữ liệu và đồng bộ nếu có chỉnh sửa.

### Tài liệu tham khảo chính thức

- [Java SE 21 — `java.sql.ResultSet`](https://docs.oracle.com/en/java/javase/21/docs/api/java.sql/java/sql/ResultSet.html)
- [Java SE 21 — `javax.sql.RowSet`](https://docs.oracle.com/en/java/javase/21/docs/api/java.sql/javax/sql/RowSet.html)
- [Java SE 21 — `javax.sql.rowset.CachedRowSet`](https://docs.oracle.com/en/java/javase/21/docs/api/java.sql.rowset/javax/sql/rowset/CachedRowSet.html)
- [Java SE 21 — `javax.sql.rowset.RowSetProvider`](https://docs.oracle.com/en/java/javase/21/docs/api/java.sql.rowset/javax/sql/rowset/RowSetProvider.html)
- [Java SE 21 — `javax.sql.rowset.JdbcRowSet`](https://docs.oracle.com/en/java/javase/21/docs/api/java.sql.rowset/javax/sql/rowset/JdbcRowSet.html)
