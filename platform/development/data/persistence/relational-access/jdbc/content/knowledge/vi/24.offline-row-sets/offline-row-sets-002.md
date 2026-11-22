# Vai trò của `RowSet` và `RowSetProvider` trong JDBC

Trong chương **RowSet ngoại tuyến**, câu hỏi thực tế là: *Làm thế nào đọc dữ liệu từ cơ sở dữ liệu bằng JDBC, đóng kết nối sớm, nhưng vẫn duyệt và xử lý kết quả ở tầng ứng dụng?* `ResultSet` thông thường gắn với `Statement` và `Connection` đang mở. Nếu giữ kết nối trong lúc giao diện hiển thị, người dùng chỉnh sửa biểu mẫu hoặc hệ thống tạo báo cáo kéo dài, số kết nối đang mượn từ pool có thể tăng không cần thiết.

JDBC có họ API **`RowSet`**, trong đó `CachedRowSet` hỗ trợ **ngắt kết nối** (*disconnected*): sao chép các hàng truy vấn vào một đối tượng có thể di chuyển con trỏ, đọc và chỉnh sửa dữ liệu trong bộ nhớ sau khi `ResultSet`, `Statement` và `Connection` gốc được đóng. Để tạo đối tượng RowSet mà không phụ thuộc trực tiếp vào lớp triển khai riêng của JDK hoặc nhà cung cấp, Java cung cấp **`RowSetProvider`** và **`RowSetFactory`**.

Bài học giới thiệu vai trò, quan hệ giữa các giao diện, các biến thể RowSet, cách tạo bằng factory, ví dụ `DataSource` + `PreparedStatement` + `CachedRowSet.populate(...)`, cũng như những giới hạn về bộ nhớ, dữ liệu cũ, đồng bộ thay đổi, transaction và tính khả chuyển của driver.

## 1. `RowSet` là gì, khác `ResultSet` thế nào?

`javax.sql.RowSet` là giao diện **mở rộng `java.sql.ResultSet`** và mô hình thành phần JavaBeans. Ngoài việc truy cập các hàng/cột như `ResultSet`, một RowSet có thể cấu hình những thuộc tính như câu SQL, tham số, URL hoặc tên nguồn dữ liệu; nó còn hỗ trợ đăng ký `RowSetListener` để quan sát sự kiện.

Tuy nhiên, **không phải mọi RowSet đều hoạt động ngoại tuyến**. `RowSet` là khái niệm bao trùm, còn việc duy trì kết nối hay lưu dữ liệu tách rời phụ thuộc vào triển khai:

| Đặc điểm | `ResultSet` thông thường | `JdbcRowSet` | `CachedRowSet` |
| --- | --- | --- | --- |
| Cách tạo | `Statement.executeQuery()` | Qua `RowSetFactory.createJdbcRowSet()` | Qua `RowSetFactory.createCachedRowSet()` |
| Kết nối với DB | Thường gắn với statement/connection | **Connected**: giữ khả năng truy cập DB khi hoạt động | **Disconnected** sau khi được nạp dữ liệu |
| Tự cấu hình và thực thi truy vấn | Thông qua `Statement` | Có `setCommand(...)`, `execute()` | Có thể `populate(ResultSet)` hoặc `execute()` khi đã cấu hình |
| Duyệt dữ liệu sau khi đóng kết nối nguồn | Không thể dựa vào một `ResultSet` đã đóng | Không phù hợp với mục tiêu ngắt kết nối | Có, với dữ liệu đã nạp trong bộ nhớ |
| Chỉnh sửa cục bộ không lập tức cập nhật DB | Không phải mục đích chính | Làm việc qua kết nối DB | Có, nhưng cần đồng bộ riêng nếu muốn ghi về DB |

Một số driver hỗ trợ `ResultSet` cuộn hai chiều hoặc cập nhật trực tiếp, nhưng điều đó **không biến `ResultSet` thành bản sao ngoại tuyến**. Khi đóng `Connection`, `ResultSet` phụ thuộc vào nó không còn là nơi an toàn để truy cập dữ liệu.

### Luồng xử lý cơ bản

```text
                  JDBC với kết nối đang mở
 DataSource -> Connection -> PreparedStatement -> ResultSet
                                                   |
                                                   | populate(...)
                                                   v
                                              CachedRowSet
                                                   |
                    đóng ResultSet / Statement / Connection
                                                   |
                                                   v
                                duyệt hoặc chỉnh sửa dữ liệu offline
                                                   |
                                 đồng bộ về DB chỉ khi được yêu cầu
```

`CachedRowSet` là **ảnh chụp dữ liệu** tại thời điểm nạp, không phải một cơ chế tự động nhận cập nhật mới từ DB. Đọc lại snapshot sau vài phút sẽ không thấy một bản ghi vừa được người khác thêm, trừ khi ứng dụng nạp lại dữ liệu theo một phương thức phù hợp.

## 2. Các loại RowSet chuẩn thường gặp

Các giao diện quan trọng nằm trong gói `javax.sql.rowset`; giao diện gốc `RowSet` nằm trong `javax.sql`.

| Loại | Vai trò chính | Khi nào cân nhắc |
| --- | --- | --- |
| `JdbcRowSet` | Bao bọc cách làm việc `ResultSet` **có kết nối**, thêm giao diện JavaBeans và sự kiện RowSet | Ứng dụng cần API RowSet nhưng vẫn thao tác trực tiếp qua kết nối |
| `CachedRowSet` | Giữ các hàng và metadata trong bộ nhớ, cho phép sử dụng **sau khi ngắt kết nối** | Biểu mẫu, dữ liệu tra cứu hoặc tập kết quả vừa phải cần dùng ngoài phạm vi connection |
| `WebRowSet` | Mở rộng khả năng của CachedRowSet để đọc/ghi dữ liệu và metadata dưới dạng XML chuẩn RowSet | Trao đổi một snapshot qua XML hoặc tích hợp hệ thống kế thừa |
| `FilteredRowSet` | Cung cấp khả năng lọc những hàng thấy được thông qua `Predicate` | Cần view có điều kiện trên tập RowSet mà không nhất thiết truy vấn lại DB |
| `JoinRowSet` | Hỗ trợ kết hợp dữ liệu từ một số RowSet dựa vào cột khớp (*match column*) | Xử lý tập kết quả nhỏ từ nhiều nguồn theo quy tắc join được hỗ trợ |

Các loại `FilteredRowSet`, `JoinRowSet` và `WebRowSet` **không thay thế** SQL query engine. Lọc hoặc join ở phía Java có thể dùng nhiều bộ nhớ hơn và không tận dụng chỉ mục/cơ chế tối ưu của DB. Nếu chỉ cần các hàng thỏa điều kiện hoặc join dữ liệu lớn, thông thường nên làm ngay trong SQL bằng `WHERE`/`JOIN`.

`JdbcRowSet` cũng không phải biến thể ngoại tuyến. Đừng chọn nó chỉ vì có chữ `RowSet` khi mục tiêu là đóng kết nối càng sớm càng tốt.

## 3. `RowSetProvider` và `RowSetFactory` có vai trò gì?

**`RowSetProvider`** là điểm vào chuẩn để tìm và tạo một `RowSetFactory`. **`RowSetFactory`** là giao diện factory có các phương thức tạo từng loại RowSet. Nhờ đó code chỉ phụ thuộc vào API công khai, thay vì tự `new` lớp triển khai nội bộ.

```java
import javax.sql.rowset.CachedRowSet;
import javax.sql.rowset.FilteredRowSet;
import javax.sql.rowset.JdbcRowSet;
import javax.sql.rowset.JoinRowSet;
import javax.sql.rowset.RowSetFactory;
import javax.sql.rowset.RowSetProvider;
import javax.sql.rowset.WebRowSet;

RowSetFactory factory = RowSetProvider.newFactory();

CachedRowSet cached = factory.createCachedRowSet();
JdbcRowSet connected = factory.createJdbcRowSet();
FilteredRowSet filtered = factory.createFilteredRowSet();
JoinRowSet joined = factory.createJoinRowSet();
WebRowSet web = factory.createWebRowSet();

// Đóng các đối tượng sau khi không còn sử dụng.
cached.close();
connected.close();
filtered.close();
joined.close();
web.close();
```

Đây là ví dụ nhận diện API; trong ứng dụng thật, hãy **chỉ tạo loại cần dùng** và ưu tiên `try-with-resources`. Các phương thức factory có thể ném `SQLException` khi không tạo được triển khai tương ứng.

Ví dụ tốt hơn khi cần một CachedRowSet:

```java
import javax.sql.rowset.CachedRowSet;
import javax.sql.rowset.RowSetProvider;

try (CachedRowSet rows = RowSetProvider.newFactory()
        .createCachedRowSet()) {
    // Nạp hoặc cấu hình rows, sau đó sử dụng.
}
```

`RowSetProvider.newFactory()` có cơ chế lựa chọn triển khai từ cấu hình nhà cung cấp dịch vụ hoặc phương án mặc định của môi trường Java. Java còn có overload `newFactory(String factoryClassName, ClassLoader cl)` để chỉ rõ lớp factory khi cần kiểm soát triển khai. Trình tự phát hiện nhà cung cấp và phạm vi hỗ trợ nên được kiểm chứng theo phiên bản JDK sử dụng.

**Không phụ thuộc trực tiếp vào một class nội bộ**, chẳng hạn lớp thuộc `com.sun.rowset`. Các lớp này không phải điểm trừu tượng API mà ứng dụng nên dựa vào; tính sẵn có và cơ chế truy cập có thể thay đổi theo runtime hoặc cách đóng gói module.

### Khi ứng dụng dùng Java Platform Module System

Trong ứng dụng có `module-info.java`, cần khai báo module tương ứng với API RowSet:

```java
module example.jdbc.rowset {
    requires java.sql;
    requires java.sql.rowset;
}
```

Tên module `java.sql.rowset` khác tên package `javax.sql.rowset`. Dự án chạy trên classpath thông thường có thể không cần tự khai báo `module-info.java`.

## 4. Nạp `CachedRowSet` từ `ResultSet` rồi đóng kết nối

Ví dụ có bảng sách:

```sql
CREATE TABLE book (
    id             BIGINT PRIMARY KEY,
    title          VARCHAR(200) NOT NULL,
    published_year INTEGER NOT NULL
);
```

Ứng dụng cần lấy danh sách sách xuất bản từ một năm nhất định rồi trả kết quả cho lớp tạo giao diện mà **không giữ connection**.

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.Objects;
import javax.sql.DataSource;
import javax.sql.rowset.CachedRowSet;
import javax.sql.rowset.RowSetProvider;

public final class BookRepository {
    private final DataSource dataSource;

    public BookRepository(DataSource dataSource) {
        this.dataSource = Objects.requireNonNull(dataSource);
    }

    public CachedRowSet findSince(int year) throws SQLException {
        String sql = """
                SELECT id, title, published_year
                FROM book
                WHERE published_year >= ?
                ORDER BY id
                """;

        CachedRowSet snapshot = RowSetProvider.newFactory()
                .createCachedRowSet();
        try {
            try (Connection connection = dataSource.getConnection();
                 PreparedStatement ps = connection.prepareStatement(sql)) {
                ps.setInt(1, year);
                try (ResultSet rs = ps.executeQuery()) {
                    snapshot.populate(rs);
                }
            }
            return snapshot; // Đã đóng connection; snapshot vẫn mở.
        } catch (SQLException | RuntimeException failure) {
            try {
                snapshot.close();
            } catch (SQLException closeFailure) {
                failure.addSuppressed(closeFailure);
            }
            throw failure;
        }
    }
}
```

Trong mẫu này, `CachedRowSet` **được chuyển quyền sở hữu cho bên gọi** khi thành công; nếu nạp lỗi, repository đóng snapshot và giữ lỗi đóng ở dạng *suppressed exception*. Không đặt chính `snapshot` trong `try-with-resources` ở phương thức trả về nó, vì như vậy đối tượng sẽ đóng trước khi caller nhận. Dù truy vấn đọc dữ liệu từ JDBC, `snapshot` giữ các hàng trong bộ nhớ và sử dụng được sau khi kết nối đã trả về pool.

### Caller sử dụng kết quả hoàn toàn ngoại tuyến

```java
BookRepository repository = new BookRepository(dataSource);

try (CachedRowSet books = repository.findSince(2020)) {
    books.beforeFirst();
    while (books.next()) {
        long id = books.getLong("id");
        String title = books.getString("title");
        int year = books.getInt("published_year");

        System.out.printf("%d - %s (%d)%n", id, title, year);
    }
}
```

Ở đây `Connection`, `PreparedStatement` và `ResultSet` đã được đóng **trước khi** caller bắt đầu duyệt dữ liệu. Caller đóng `CachedRowSet` khi xong. Nếu truy vấn trả nhiều hàng, `CachedRowSet` có thể giữ lượng lớn dữ liệu trên heap: ưu tiên `WHERE`, giới hạn kết quả hoặc phân trang ở SQL thay vì nạp toàn bộ bảng.

## 5. Vì sao không nên dùng `JdbcRowSet` khi cần offline?

`JdbcRowSet` phù hợp hơn với mô hình **kết nối còn hoạt động**, dù nó có giao diện RowSet và hỗ trợ JavaBeans. Một ví dụ:

```java
import java.sql.SQLException;
import javax.sql.rowset.JdbcRowSet;
import javax.sql.rowset.RowSetProvider;

public static void printOneBook(
        String jdbcUrl, String username, String password, long bookId)
        throws SQLException {
    try (JdbcRowSet rows = RowSetProvider.newFactory()
            .createJdbcRowSet()) {
        rows.setUrl(jdbcUrl);
        rows.setUsername(username);
        rows.setPassword(password);
        rows.setCommand("SELECT id, title FROM book WHERE id = ?");
        rows.setLong(1, bookId);
        rows.execute();

        while (rows.next()) {
            System.out.println(rows.getString("title"));
        }
    }
}
```

Thông tin kết nối và mật khẩu trong ví dụ là **tham số do tầng cấu hình an toàn cung cấp**, không được hard-code trong mã nguồn hoặc ghi vào log. `JdbcRowSet` cần cấu hình nguồn kết nối phù hợp với driver; việc quản lý `DataSource` tập trung và connection pool có thể thuận tiện hơn trong kiến trúc web thông thường.

Sau `rows.execute()`, RowSet có khả năng sử dụng connection tới DB để duyệt và cập nhật; nó không được xem như một snapshot ngoại tuyến. Phương thức `close()` cần được gọi để giải phóng tài nguyên. Nếu ứng dụng chỉ muốn đọc một tập dữ liệu nhỏ rồi đóng kết nối, `PreparedStatement` + `CachedRowSet.populate(...)` như phần trước thường rõ ràng hơn.

## 6. Thuộc tính, sự kiện và đặc tính JavaBeans của `RowSet`

`RowSet` được thiết kế không chỉ như tập hàng mà còn như một thành phần JavaBeans: có thuộc tính cấu hình và có cơ chế sự kiện cho lớp khác theo dõi.

Một số phương thức liên quan:

- `setCommand(sql)`, `setInt(index, value)`, `execute()`: hỗ trợ cấu hình và chạy SQL trong những loại RowSet triển khai cơ chế đó.
- `setUrl(...)`, `setDataSourceName(...)`, `setUsername(...)` và `setPassword(...)`: dùng khi RowSet cần tự tạo kết nối; không có nghĩa kết nối đã mở ngay sau lệnh setter.
- `addRowSetListener(...)` và `removeRowSetListener(...)`: quản lý listener.
- `getMetaData()`: trả metadata cho các cột trong tập kết quả, giống cách `ResultSetMetaData` cung cấp thông tin kiểu và nhãn cột.

Một `RowSetListener` có ba callback:

```java
import javax.sql.RowSetEvent;
import javax.sql.RowSetListener;

RowSetListener listener = new RowSetListener() {
    @Override
    public void cursorMoved(RowSetEvent event) {
        System.out.println("Con trỏ RowSet thay đổi");
    }

    @Override
    public void rowChanged(RowSetEvent event) {
        System.out.println("Một hàng được thay đổi");
    }

    @Override
    public void rowSetChanged(RowSetEvent event) {
        System.out.println("Nội dung RowSet thay đổi");
    }
};

cached.addRowSetListener(listener);
// Sau khi không cần:
cached.removeRowSetListener(listener);
```

Đoạn mã giả định `cached` là `CachedRowSet` đang mở. Listener nhận sự kiện dựa trên thay đổi RowSet; đây không phải cơ chế subscribe để nhận **thay đổi trực tiếp từ DB do các transaction khác ghi**. Không dùng listener thay cho polling, CDC hoặc cơ chế thông báo của DB.

`RowSet` và các triển khai như `CachedRowSet` có trạng thái con trỏ và dữ liệu có thể thay đổi. Không nên chia sẻ cùng một đối tượng giữa các request/thread mà không có chiến lược đồng bộ hóa. Thường đơn giản hơn nếu tạo một snapshot riêng cho mỗi đơn vị công việc.

## 7. Chỉnh sửa ngoại tuyến và đồng bộ về cơ sở dữ liệu

Một `CachedRowSet` có thể được dùng để **chỉnh sửa dữ liệu cục bộ** qua các phương thức gần giống `ResultSet` có thể cập nhật:

```java
// cached đã được nạp từ bảng book và con trỏ có thể di chuyển.
cached.beforeFirst();
if (cached.next()) {
    cached.updateString("title", "Tên sách đã sửa");
    cached.updateRow(); // Chỉnh sửa trong bản sao CachedRowSet.
}
```

**`updateRow()` trên CachedRowSet không đồng nghĩa DB đã được cập nhật.** Dữ liệu chỉnh sửa được giữ trong đối tượng ngoại tuyến; để ghi lại DB, implementation phải có cơ chế đồng bộ thích hợp. Với `CachedRowSet` chuẩn, `acceptChanges()` hoặc `acceptChanges(Connection)` là những phương thức có thể cố gắng đồng bộ thay đổi thông qua một `SyncProvider`.

Một số thông tin thường cần cho quá trình này:

| Thông tin | Tác dụng |
| --- | --- |
| `setTableName("book")` | Cho biết bảng mục tiêu khi implementation cần sinh câu lệnh đồng bộ |
| `setKeyColumns(new int[]{1})` | Xác định cột khóa để tìm đúng hàng; vị trí cột theo RowSet |
| Các giá trị gốc và dữ liệu đã sửa | Phát hiện thay đổi/xung đột theo chiến lược của synchronization provider |
| `Connection` hoặc cấu hình nguồn dữ liệu | Cho phép writer truy cập DB khi đồng bộ |
| `SyncProvider` | Xác định cách đồng bộ, mức khóa, cách nhận biết xung đột do implementation cung cấp |

Ví dụ mang tính khái niệm:

```java
cached.setTableName("book");
cached.setKeyColumns(new int[] {1});

// Sau khi đã sửa dữ liệu trong cached, đồng bộ nếu có SyncProvider phù hợp.
// Đoạn này cần được đặt trong quy trình kiểm soát transaction của ứng dụng.
cached.acceptChanges(connection);
```

Không nên gọi đoạn này như một giải pháp “ghi offline là tự an toàn”. `acceptChanges(...)` có thể phát sinh `javax.sql.rowset.spi.SyncProviderException` khi xảy ra xung đột; một số triển khai có `SyncResolver` để xác định hàng/cột xung đột. Cách phát hiện, giải quyết xung đột, quản lý transaction và SQL được sinh ra **phụ thuộc implementation và DB**. Trước khi dùng production, hãy kiểm thử update, insert, delete, khóa chính, trigger và các trường hợp dữ liệu đã bị người khác sửa.

Đặc biệt, một snapshot cách đây vài phút có thể chứa **giá trị cũ**. Nếu một transaction khác đã cập nhật cùng hàng trong lúc người dùng đang sửa ngoại tuyến, việc đẩy thay đổi lên DB cần quy tắc phát hiện xung đột (như optimistic locking với `version` hoặc so sánh giá trị gốc), không được âm thầm ghi đè thay đổi của người khác.

Với luồng nghiệp vụ CRUD quan trọng, cách khác thường minh bạch hơn là: đưa snapshot hoặc DTO tới tầng giao diện, khi lưu thì chạy câu `UPDATE ... WHERE id = ? AND version = ?` bằng `PreparedStatement` trong transaction đã được thiết kế, rồi kiểm tra update count. Không bắt buộc phải dùng `acceptChanges()` chỉ vì đang sử dụng `CachedRowSet`.

## 8. `WebRowSet`, `FilteredRowSet` và `JoinRowSet` dùng khi nào?

### `WebRowSet`: biểu diễn snapshot dưới dạng XML

`WebRowSet` có thể ghi dữ liệu/metadata vào XML và đọc ngược trở lại, hữu ích với tích hợp hệ thống kế thừa:

```java
import java.io.StringWriter;
import javax.sql.rowset.WebRowSet;
import javax.sql.rowset.RowSetProvider;

try (WebRowSet web = RowSetProvider.newFactory().createWebRowSet()) {
    // Trước đó cần nạp dữ liệu hợp lệ vào web, chẳng hạn populate(ResultSet).
    try (StringWriter xml = new StringWriter()) {
        web.writeXml(xml);
        System.out.println(xml.toString());
    }
}
```

Đây là minh họa API, không phải chương trình tạo XML có nội dung nếu chưa nạp RowSet. **Đừng serialize và công khai một RowSet chưa được lọc dữ liệu**: XML có thể chứa dữ liệu hàng, metadata và những thuộc tính kết nối không nên để lộ. Với dữ liệu XML không tin cậy, cần áp dụng chính sách phân tích XML an toàn và kiểm tra giới hạn kích thước.

### `FilteredRowSet`: lọc tập kết quả tại phía Java

`FilteredRowSet` cho phép gắn một `javax.sql.rowset.Predicate` thông qua `setFilter(...)` để chỉ hiển thị các hàng phù hợp với điều kiện. Thao tác này có ích khi đã có dữ liệu trong bộ nhớ và muốn thay đổi cách nhìn, nhưng không thay thế điều kiện `WHERE` trong DB cho tập dữ liệu lớn hoặc dữ liệu nhạy cảm.

### `JoinRowSet`: kết hợp những RowSet

`JoinRowSet` cho phép thêm RowSet đã khai báo cột đối sánh (*match columns*) và truy vấn kết quả được join theo khả năng implementation. Nó không phải một SQL engine đầy đủ: loại join được hỗ trợ, thứ tự và chi phí bộ nhớ có thể khác nhau. Nếu cần join nhiều bảng lớn, vẫn nên dùng SQL `JOIN` và `PreparedStatement`.

## 9. Hiệu năng, bộ nhớ, tính nhất quán và bảo mật

`CachedRowSet` giải phóng kết nối sớm, nhưng đánh đổi bằng việc **tạo một bản sao dữ liệu trên heap Java**. Bảng dưới giúp chọn đúng công cụ:

| Nhu cầu | Lựa chọn thường phù hợp | Cảnh báo |
| --- | --- | --- |
| Duyệt tập kết quả rất lớn một lần | `ResultSet` theo chiến lược fetch/streaming đã kiểm chứng | Kết nối cần được duy trì đến khi đọc xong |
| Nạp vài chục/vài trăm hàng để xử lý sau khi đóng DB | `CachedRowSet` hoặc DTO/list dữ liệu | Định lượng bộ nhớ và kích thước từng cột |
| Truy vấn nhanh, một lần, trong một phương thức repository | `PreparedStatement` + `ResultSet` | Không cần thêm một lớp RowSet nếu không có lợi ích cụ thể |
| Cần JavaBeans và sự kiện con trỏ/hàng | `RowSet`/`RowSetListener` | Sự kiện không phải cập nhật trực tiếp từ DB |
| Muốn sửa ngoại tuyến rồi lưu lại | `CachedRowSet` + quy trình đồng bộ có phát hiện xung đột | Không được bỏ qua transaction và vấn đề lost update |
| Truyền snapshot ở định dạng XML | `WebRowSet` | Dữ liệu, thuộc tính kết nối và kích thước XML cần được kiểm soát |

Những điều nên kiểm tra trước khi dùng trong production:

1. **Giới hạn kết quả:** dùng `WHERE`, phân trang và giới hạn dòng; không `populate` toàn bộ bảng dữ liệu lớn.
2. **Kích thước hàng:** các cột `BLOB`/`CLOB` có thể làm snapshot lớn bất thường. Tránh chọn nội dung lớn khi chỉ cần metadata hoặc vài trường hiển thị.
3. **Snapshot cũ:** xác định thời hạn sử dụng dữ liệu, cách reload và chính sách xử lý khi DB đã thay đổi.
4. **Phân quyền:** RowSet chứa bản sao dữ liệu; đóng kết nối **không xóa dữ liệu nhạy cảm khỏi bộ nhớ**. Không truyền toàn bộ snapshot ra khỏi ranh giới tin cậy.
5. **Tài nguyên:** đóng RowSet sau khi dùng, dù không giữ kết nối DB; tránh giữ snapshot không giới hạn trong session HTTP.
6. **Driver và implementation:** kiểm tra hỗ trợ `populate`, kiểu SQL, cột đặc thù, scrollability, synchronization provider và khả năng xử lý lỗi trên đúng JDK/driver.
7. **Transaction:** snapshot không tự có isolation kéo dài ngoài thời điểm truy vấn. Muốn các thao tác ghi tiếp theo nhất quán, cần transaction và kiểm tra phiên bản khi ghi.

Nếu nghiệp vụ chỉ cần một danh sách bất biến gồm `id` và `title`, chuyển `ResultSet` thành `List<BookDto>` trong repository cũng là giải pháp hợp lệ, thường dễ kiểm soát kiểu dữ liệu và giảm phụ thuộc vào API RowSet ở tầng trên.

## 10. Những lỗi thường gặp

| Sai lầm | Vì sao nguy hiểm | Cách khắc phục |
| --- | --- | --- |
| Cho rằng mọi `RowSet` đều ngoại tuyến | `JdbcRowSet` vẫn gắn với kết nối | Chọn `CachedRowSet` cho snapshot disconnected |
| Trả `ResultSet` ra khỏi phương thức rồi đóng `Connection` | ResultSet không còn sử dụng an toàn | Sao chép sang CachedRowSet/DTO trước khi đóng |
| Trả `CachedRowSet` từ `try-with-resources` quản lý chính đối tượng ấy | Snapshot bị đóng trước khi caller nhận | Chuyển quyền đóng sang caller; đóng ở nhánh lỗi |
| Dùng `new com.sun.rowset...` | Phụ thuộc class nội bộ/implementation | Dùng `RowSetProvider.newFactory()` |
| Dùng `populate` cho hàng triệu bản ghi | Tốn heap, GC, tăng độ trễ | Lọc/paginate hoặc xử lý streaming ResultSet |
| Hiểu `updateRow()` như `UPDATE` SQL đã commit | DB chưa nhận thay đổi offline | Đồng bộ có kiểm soát hoặc gọi PreparedStatement UPDATE |
| Gọi `acceptChanges()` rồi bỏ qua xung đột | Có thể mất cập nhật hoặc trạng thái không rõ | Xử lý `SyncProviderException` và transaction |
| Coi RowSetListener là CDC của DB | Không nhận update từ transaction bên ngoài | Dùng cơ chế đồng bộ/thông báo DB khác |
| Serialize toàn bộ WebRowSet vào log hoặc API công khai | Rò rỉ hàng dữ liệu và metadata | Phân loại dữ liệu; chỉ xuất thông tin được phép |
| Chia sẻ một CachedRowSet giữa nhiều request | Con trỏ/dữ liệu có thể bị thay đổi đồng thời | Tạo snapshot riêng hoặc quản lý truy cập chặt chẽ |

## 11. Thực hành: tạo snapshot ngoại tuyến bằng factory

Để luyện tập các API trong bài:

1. **Chuẩn bị bảng:** tạo `book(id, title, published_year)` và thêm một số dòng kiểm thử.
2. **Tạo factory:** gọi `RowSetProvider.newFactory()` rồi `createCachedRowSet()`. Không dùng trực tiếp implementation nội bộ.
3. **Truy vấn tham số:** tạo `PreparedStatement` cho `WHERE published_year >= ?` và bind giá trị bằng `setInt(...)`.
4. **Nạp snapshot:** gọi `snapshot.populate(rs)` khi `ResultSet` còn mở, sau đó đóng `ResultSet`/`PreparedStatement`/`Connection`.
5. **Duyệt offline:** `beforeFirst()`, `next()`, `getLong("id")`, `getString("title")`. Xác nhận không cần mượn thêm connection để duyệt.
6. **Đối chiếu kiểu kết nối:** tạo `JdbcRowSet`, cấu hình và chạy một truy vấn tương đương trên DB thử nghiệm; quan sát sự khác biệt về vòng đời.
7. **Thử dữ liệu cũ:** nạp snapshot, rồi dùng kết nối khác sửa `title`. Kiểm tra snapshot cũ không tự thay đổi; nạp lại nếu muốn thấy dữ liệu mới.
8. **Thử sửa offline:** dùng `updateString(...)` + `updateRow()` trên CachedRowSet. Kiểm tra DB chưa đổi, sau đó thiết kế một câu `UPDATE` với `version` hoặc cơ chế đồng bộ phù hợp.
9. **Đo bộ nhớ:** tăng số lượng hàng và kích thước cột để thấy giới hạn của snapshot in-memory; so sánh với việc chuyển sang DTO hoặc đọc trực tiếp qua ResultSet.

**Câu hỏi tự kiểm tra:**

- Vì sao `CachedRowSet` có thể dùng sau khi đóng `Connection` mà `ResultSet` thường không?
- `RowSetProvider` và `RowSetFactory` có vai trò khác nhau như thế nào?
- `JdbcRowSet` có phải “offline RowSet” chỉ vì nó nằm trong cùng gói API không?
- Vì sao trả một `CachedRowSet` đã bị đóng ở cuối `try-with-resources` là lỗi vòng đời?
- `updateRow()` trên CachedRowSet đã lưu thay đổi xuống DB chưa?
- Khi nào nên dùng `CachedRowSet`, khi nào `List<DTO>` hoặc `ResultSet` streaming phù hợp hơn?
- Làm sao xử lý trường hợp dữ liệu ở DB đã đổi trước khi người dùng đồng bộ bản sửa offline?

**Ghi nhớ:** `RowSet` là họ giao diện JDBC mở rộng khả năng `ResultSet`; **`CachedRowSet`** mới là lựa chọn tiêu biểu cho dữ liệu **ngoại tuyến**, còn `JdbcRowSet` vẫn cần kết nối. **`RowSetProvider`** tìm `RowSetFactory` để ứng dụng tạo các biến thể RowSet mà không phụ thuộc vào class nội bộ. Hãy nạp snapshot trong khi JDBC resources còn mở, giao quyền đóng RowSet rõ ràng, giới hạn dữ liệu trong bộ nhớ và thiết kế cơ chế phát hiện xung đột nếu muốn ghi các thay đổi offline về DB.
