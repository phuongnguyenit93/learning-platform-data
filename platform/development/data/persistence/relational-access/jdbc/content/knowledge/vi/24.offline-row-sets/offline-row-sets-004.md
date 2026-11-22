# Sử dụng `CachedRowSet` cho dữ liệu làm việc ngoại tuyến trong JDBC

Với JDBC thông thường, ứng dụng mở `Connection`, thực thi `PreparedStatement` và đọc các hàng qua `ResultSet`. Cách này phù hợp khi xử lý dữ liệu ngay lúc truy vấn, nhưng một `ResultSet` thông thường gắn với câu lệnh và kết nối đã tạo ra nó. Nếu giao diện cần cho người dùng xem hoặc sửa một tập dữ liệu trong thời gian dài, việc giữ kết nối cơ sở dữ liệu mở suốt thời gian đó vừa tốn tài nguyên vừa làm tăng rủi ro lỗi kết nối.

**`CachedRowSet`** giải quyết một phần bài toán bằng cách giữ **bản sao dữ liệu và metadata của kết quả truy vấn trong bộ nhớ**, cho phép ứng dụng duyệt, đọc và chỉnh sửa bản sao ngay cả khi `ResultSet` và `Connection` ban đầu đã đóng. Khi cần, ứng dụng có thể thử **đồng bộ các thay đổi** trở lại cơ sở dữ liệu thông qua cơ chế `acceptChanges` của *RowSet provider*.

Bài thuộc chương **RowSet ngoại tuyến** của module **JDBC**. Ta sẽ kết hợp các API chuẩn `DataSource`, `PreparedStatement`, `ResultSet`, `RowSetProvider`, `CachedRowSet` và `SQLException`, phân biệt bản sao dữ liệu với trạng thái DB thật, kiểm soát kết nối và xử lý các tình huống xung đột khi đồng bộ.

Sau bài học, bạn có thể:

- Tạo một `CachedRowSet` bằng `RowSetProvider` và nạp dữ liệu qua `populate(ResultSet)`.
- Đọc dữ liệu đã nạp **sau khi đóng toàn bộ tài nguyên JDBC ban đầu**.
- Chỉnh sửa, thêm hoặc xóa hàng trong bản sao mà không nhầm với cập nhật đã commit ở DB.
- Hiểu vai trò của `acceptChanges(Connection)`, `setTableName` và `setKeyColumns` khi đồng bộ.
- Nhận biết `SyncProviderException`, xung đột dữ liệu và các giới hạn hỗ trợ của provider/driver.
- Quyết định khi nào `CachedRowSet` phù hợp hơn việc ánh xạ `ResultSet` thành `List<record>`.

## 1. `CachedRowSet` là gì và vì sao gọi là ngoại tuyến?

`javax.sql.rowset.CachedRowSet` là giao diện của một **RowSet có thể hoạt động ở trạng thái ngắt kết nối** (*disconnected RowSet*). Nó hỗ trợ nhiều thao tác quen thuộc của `ResultSet`, như `next()`, `getString()`, `getLong()`, `beforeFirst()` và các phương thức `updateXxx()`. Khác với `ResultSet` đang đọc trực tiếp từ DB, dữ liệu của `CachedRowSet` được giữ trong bộ nhớ của ứng dụng sau khi tải.

```text
             GIAI ĐOẠN NẠP DỮ LIỆU

 DataSource -> Connection -> PreparedStatement -> ResultSet
                                          |
                                CachedRowSet.populate(rs)
                                          |
                               Bản sao hàng + metadata
                                          |
             Đóng ResultSet, Statement và Connection

             GIAI ĐOẠN LÀM VIỆC NGOẠI TUYẾN

                 CachedRowSet trong bộ nhớ
                       |            |
                  Duyệt / đọc   Sửa / thêm / xóa
                       |            |
                  Hiển thị      Đánh dấu thay đổi

             GIAI ĐOẠN ĐỒNG BỘ (NẾU CẦN)

        Mở Connection mới -> acceptChanges(connection)
                                      |
                         Provider cố đồng bộ về DB
                                      |
                        Thành công hoặc xung đột
```

Ở đây, **ngoại tuyến** có nghĩa bản sao đã nạp không cần giữ kết nối JDBC mở để duyệt và chỉnh sửa cục bộ. Nó **không đồng nghĩa** ứng dụng tự có một cơ sở dữ liệu ngoại tuyến bền vững, được mã hóa hoặc có thể truy cập sau khi chương trình tắt. `CachedRowSet` mặc định là dữ liệu trong bộ nhớ; nếu muốn lưu lâu dài qua nhiều phiên làm việc, cần thiết kế định dạng lưu trữ và cơ chế đồng bộ riêng.

### Các đối tượng cùng họ RowSet

| Giao diện | Mục đích chính | Đặc điểm |
| --- | --- | --- |
| `JdbcRowSet` | Giao diện kiểu RowSet trên JDBC có kết nối | Thường sử dụng kết nối khi thao tác với dữ liệu |
| `CachedRowSet` | Làm việc với bản sao dữ liệu ngắt kết nối | Có thể đọc/sửa trong bộ nhớ; đồng bộ nếu provider hỗ trợ |
| `WebRowSet` | Biểu diễn RowSet thành XML và đọc lại XML | Mở rộng `CachedRowSet`, không tự biến XML thành cơ chế đồng bộ an toàn |
| `FilteredRowSet` | Áp dụng điều kiện lọc trên RowSet | Mở rộng khả năng thao tác tập kết quả |
| `JoinRowSet` | Kết hợp dữ liệu từ các RowSet | Có các giới hạn riêng về kiểu kết nối và hỗ trợ provider |

Bài tập trung vào `CachedRowSet`. Không phải ứng dụng CRUD nào cũng cần RowSet: nếu chỉ truy vấn, ánh xạ dữ liệu vào `List<Customer>` rồi trả cho tầng nghiệp vụ, cách làm đó thường đơn giản hơn.

## 2. Tạo `CachedRowSet` với API JDBC chuẩn

Thay vì phụ thuộc vào một lớp triển khai cụ thể trong JDK, hãy tạo RowSet bằng `RowSetProvider`:

```java
import javax.sql.rowset.CachedRowSet;
import javax.sql.rowset.RowSetProvider;

CachedRowSet cached = RowSetProvider.newFactory().createCachedRowSet();
```

`RowSetProvider` chọn một triển khai `RowSetFactory` theo cơ chế provider của Java. Chương trình sử dụng giao diện `CachedRowSet`, không cần import các lớp triển khai nội bộ của JDK như `com.sun.rowset.*`. Nếu dự án dùng **Java Platform Module System (JPMS)**, cần có module `java.sql.rowset` trong cấu hình module; đây là API chuẩn trong Java hiện đại.

`CachedRowSet` cũng là tài nguyên có thể đóng; khi hoàn tất xử lý, caller nên gọi `close()` hoặc sử dụng `try-with-resources`:

```java
try (CachedRowSet rows = RowSetProvider.newFactory().createCachedRowSet()) {
    // Nạp, duyệt hoặc chỉnh sửa dữ liệu.
}
```

Không đóng RowSet ngay trước khi trả nó từ một repository, vì caller sẽ không còn dữ liệu để dùng. Quyền sở hữu `CachedRowSet` cần rõ ràng: **phương thức tạo trả RowSet đang mở, phương thức nhận có trách nhiệm đóng**; hoặc repository tự đọc hết RowSet và trả DTO bất biến.

## 3. Ví dụ: nạp dữ liệu bằng `populate(ResultSet)`

Giả sử hệ thống quản lý các ghi chú của khách hàng. Bảng minh họa:

```sql
CREATE TABLE customer_note (
    note_id     BIGINT PRIMARY KEY,
    customer_id BIGINT NOT NULL,
    note_text   VARCHAR(200) NOT NULL,
    revision    INTEGER NOT NULL DEFAULT 0
);
```

`note_id` là khóa chính; `customer_id` xác định chủ sở hữu ghi chú; `revision` là cột ứng dụng có thể dùng để kiểm soát phiên bản khi tự viết cơ chế cập nhật. **Việc có cột `revision` không tự động khiến mọi `CachedRowSet` provider kiểm tra optimistic locking bằng cột này.** Muốn bảo đảm quy tắc phiên bản cụ thể, phải thiết kế và kiểm thử cơ chế đồng bộ thích hợp.

Repository sau chỉ tải các ghi chú của một khách hàng, dùng `PreparedStatement` để gán `customerId` an toàn:

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.Objects;
import javax.sql.DataSource;
import javax.sql.rowset.CachedRowSet;
import javax.sql.rowset.RowSetProvider;

public final class NoteRowSetRepository {
    private static final String SELECT_NOTES = """
            SELECT note_id, customer_id, note_text, revision
            FROM customer_note
            WHERE customer_id = ?
            ORDER BY note_id
            """;

    private final DataSource dataSource;

    public NoteRowSetRepository(DataSource dataSource) {
        this.dataSource = Objects.requireNonNull(dataSource, "dataSource");
    }

    public CachedRowSet loadForCustomer(long customerId) throws SQLException {
        if (customerId <= 0) {
            throw new IllegalArgumentException("customerId must be positive");
        }

        CachedRowSet cached = RowSetProvider.newFactory().createCachedRowSet();

        try (Connection connection = dataSource.getConnection();
             PreparedStatement statement =
                     connection.prepareStatement(SELECT_NOTES)) {

            statement.setLong(1, customerId);

            try (ResultSet result = statement.executeQuery()) {
                cached.populate(result);
            }

            // Đã sao chép các hàng. Không cần giữ statement/connection.
        } catch (SQLException | RuntimeException failure) {
            try {
                cached.close();
            } catch (SQLException closeFailure) {
                failure.addSuppressed(closeFailure);
            }
            throw failure;
        }

        return cached; // Caller sở hữu và sẽ đóng CachedRowSet.
    }
}
```

Cách dùng ở nơi gọi:

```java
NoteRowSetRepository repository = new NoteRowSetRepository(dataSource);

try (CachedRowSet notes = repository.loadForCustomer(42L)) {
    notes.beforeFirst();

    while (notes.next()) {
        long id = notes.getLong("note_id");
        String text = notes.getString("note_text");
        int revision = notes.getInt("revision");

        System.out.printf("%d | %s | rev=%d%n", id, text, revision);
    }

    // Lúc này Connection dùng trong loadForCustomer đã được đóng.
    // RowSet vẫn có thể chuyển vị trí con trỏ và đọc lại bản sao.
    notes.beforeFirst();
    if (notes.next()) {
        System.out.println("Ghi chú đầu tiên: " + notes.getString("note_text"));
    }
}
```

Đoạn mã dùng Java 17+ để có SQL text block `"""`; với Java cũ hơn, có thể dùng chuỗi thông thường. `CachedRowSet.populate(result)` phải chạy **khi `ResultSet` và kết nối nguồn vẫn mở**. Sau khi `populate` hoàn tất, dữ liệu đã được nạp vào bản sao. Lời gọi `close()` của `Connection` đến từ `try-with-resources` dù phương thức trả RowSet; không cần chuyển quyền sở hữu connection sang caller.

### Vì sao chọn rõ các cột trong `SELECT`?

Câu SQL liệt kê `note_id`, `customer_id`, `note_text`, `revision` thay vì `SELECT *`. Điều này giúp giữ ổn định thứ tự và tên cột, tránh tải dữ liệu không cần thiết. Đặc biệt, trong phần đồng bộ ta sẽ cấu hình **cột khóa chính là cột số 1**. Nếu tùy ý đổi thứ tự cột trong `SELECT`, cấu hình đó có thể trở nên sai. Khi muốn chỉnh sửa RowSet, cần biết rõ bảng đích và những cột có thể ghi lại.

## 4. Duyệt RowSet ngoại tuyến như một `ResultSet`

Sau `populate`, `CachedRowSet` hỗ trợ các phương thức di chuyển con trỏ của giao diện `ResultSet`. Khả năng duyệt lại bản sao mà không truy cập server là một ưu điểm lớn so với việc giữ `ResultSet` thông thường mở lâu.

| API | Tác dụng |
| --- | --- |
| `next()` | Di chuyển đến hàng tiếp theo và trả `false` khi hết |
| `previous()` | Di chuyển về hàng trước, nếu trạng thái con trỏ hợp lệ |
| `beforeFirst()` | Đặt con trỏ trước hàng đầu tiên |
| `afterLast()` | Đặt con trỏ sau hàng cuối cùng |
| `absolute(n)` | Di chuyển tới hàng có vị trí tương ứng theo API |
| `getString("note_text")` | Đọc cột ở hàng hiện tại |
| `getLong("note_id")` | Đọc khóa chính của hàng hiện tại |
| `getMetaData()` | Trả metadata về các cột của RowSet |

Khác với một câu SQL `SELECT` mới, gọi `notes.beforeFirst()` rồi lặp `next()` **không tự làm mới dữ liệu từ DB**. Các thay đổi do người dùng khác commit sau lần nạp sẽ không tự xuất hiện trong bản sao. Nếu cần dữ liệu mới nhất, phải quyết định **nạp lại** hoặc **đối soát** một cách tường minh.

### Dữ liệu `NULL` vẫn tuân theo quy tắc JDBC

`CachedRowSet` triển khai các thao tác đọc kiểu JDBC, nên vẫn cần phân biệt SQL `NULL` với giá trị mặc định khi đọc kiểu nguyên thủy:

```java
long value = notes.getLong("optional_parent_id");
Long parentId = notes.wasNull() ? null : value;
```

Đoạn minh họa giả định RowSet có cột `optional_parent_id` cho phép `NULL`, **không phải** cột của bảng `customer_note` đang dùng trong ví dụ. Nếu đọc `getLong` từ SQL `NULL`, kết quả `0` cần được phân biệt bằng `wasNull()` ngay sau getter. Các getter kiểu tham chiếu như `getString()` thường trả `null` trực tiếp.

## 5. Chỉnh sửa bản sao mà chưa ghi DB

Khi provider cung cấp RowSet có khả năng cập nhật, có thể sửa một hàng trong bộ nhớ bằng cặp `updateXxx(...)` và `updateRow()`:

```java
try (CachedRowSet notes = repository.loadForCustomer(42L)) {
    notes.beforeFirst();

    while (notes.next()) {
        if (notes.getLong("note_id") == 501L) {
            notes.updateString("note_text", "Gọi khách trước khi giao hàng");
            notes.updateRow();
            break;
        }
    }

    // Có thể đọc giá trị mới từ CachedRowSet ngay bây giờ.
    // Chưa có lệnh đồng bộ hay commit lên database.
}
```

Trong ví dụ trên, `updateString` gán giá trị mới cho cột đang được xử lý; `updateRow()` ghi nhận thay đổi ở **hàng của `CachedRowSet`**. Kết thúc khối mà không gọi cơ chế đồng bộ thì DB vẫn giữ giá trị cũ. Đóng RowSet không phải một lệnh tự động `UPDATE` hay `commit`.

Các thao tác cục bộ khác:

| Thao tác | Ý nghĩa ở bản sao |
| --- | --- |
| `updateString`, `updateInt`, ... | Đặt giá trị mới cho cột hiện tại |
| `updateRow()` | Ghi nhận bản cập nhật hàng trong RowSet |
| `moveToInsertRow()` | Chuyển sang vùng nhập dữ liệu cho hàng mới |
| `insertRow()` | Chèn hàng mới vào RowSet, chưa mặc nhiên chèn vào DB |
| `moveToCurrentRow()` | Quay về vị trí con trỏ đã dùng trước khi nhập |
| `deleteRow()` | Đánh dấu hoặc xử lý hàng bị xóa theo cơ chế RowSet; DB chưa xóa |
| `rowUpdated()`, `rowInserted()`, `rowDeleted()` | Kiểm tra trạng thái thay đổi của hàng hiện tại theo provider |

Ví dụ thêm một hàng **vào bản sao**:

```java
notes.moveToInsertRow();
notes.updateLong("note_id", 9001L);
notes.updateLong("customer_id", 42L);
notes.updateString("note_text", "Khách muốn nhận hóa đơn điện tử");
notes.updateInt("revision", 0);
notes.insertRow();
notes.moveToCurrentRow();
```

Lời gọi này minh họa thao tác RowSet và giả định `notes` là `CachedRowSet` đang mở với metadata cột phù hợp. ID `9001` chỉ là giá trị giả định; trong hệ thống dùng khóa **tự sinh**, không thể tự cấp ID rồi kỳ vọng provider luôn xử lý đúng. Khi phải tạo bản ghi mới có generated key và quan hệ cha-con, thường nên dùng một repository JDBC rõ ràng với `PreparedStatement`, `getGeneratedKeys()` và transaction thay vì trông cậy vào đồng bộ RowSet tổng quát.

### Cần phân biệt ba trạng thái

```text
Trạng thái 1: RowSet vừa nạp           -> bản sao của DB lúc đọc
Trạng thái 2: RowSet đã updateRow      -> bản sao có thay đổi chưa đồng bộ
Trạng thái 3: acceptChanges thành công -> provider đã đồng bộ thay đổi
```

Việc UI hiển thị dữ liệu đã sửa **không chứng minh** DB đã nhận thay đổi. Tầng ứng dụng cần có trạng thái rõ ràng như “đã chỉnh sửa”, “đang đồng bộ”, “đã lưu” hoặc “có xung đột”, thay vì dùng cùng một thông báo “lưu thành công” cho cả `updateRow()` và `acceptChanges()`.

## 6. Đồng bộ qua `acceptChanges(Connection)`

`CachedRowSet.acceptChanges()` và `acceptChanges(Connection)` yêu cầu **RowSet provider** dùng cơ chế đồng bộ của nó để ghi các thay đổi cục bộ trở lại nguồn dữ liệu. Với overload nhận `Connection`, caller cung cấp kết nối sẽ dùng để đồng bộ:

```java
import java.sql.Connection;
import javax.sql.rowset.CachedRowSet;

try (CachedRowSet notes = repository.loadForCustomer(42L)) {
    // Thao tác ngoại tuyến: tìm hàng và gọi updateXxx + updateRow.
    notes.beforeFirst();
    while (notes.next()) {
        if (notes.getLong("note_id") == 501L) {
            notes.updateString("note_text", "Đã xác nhận địa chỉ");
            notes.updateRow();
            break;
        }
    }

    // Khai báo thông tin để provider nhận diện bảng và khóa hàng.
    notes.setTableName("customer_note");
    notes.setKeyColumns(new int[] { 1 }); // note_id là cột SELECT đầu tiên.

    // Khi kết nối mạng / cơ sở dữ liệu sẵn sàng trở lại:
    try (Connection syncConnection = dataSource.getConnection()) {
        notes.acceptChanges(syncConnection);
    }
}
```

Đây là **mẫu cơ chế đồng bộ**, không phải lời bảo đảm rằng mọi driver sẽ ghi được ngay sau khi `populate(ResultSet)`. Việc `acceptChanges` thành công phụ thuộc nhiều yếu tố: RowSet provider có writer hỗ trợ cập nhật không, bảng và khóa đã được xác định đủ chưa, `SELECT` có ánh xạ ngược về bảng gốc được không, quyền ghi DB có đủ không, các hàng có thay đổi đồng thời không, và DB có hỗ trợ các thao tác transaction mà provider cần hay không.

Điểm đặc biệt quan trọng: **`acceptChanges(Connection)` có thể quản lý việc commit hoặc rollback trên kết nối được truyền vào** theo hợp đồng cơ chế đồng bộ. Vì vậy, không nên truyền một `Connection` đang tham gia transaction nghiệp vụ lớn hơn rồi mặc định provider sẽ chỉ ghi mà không kết thúc transaction đó. Với transaction do ứng dụng kiểm soát, hãy xác minh hợp đồng provider hoặc tự viết câu SQL `UPDATE`/`DELETE` trong một repository rõ ràng.

### `setTableName` và `setKeyColumns` làm gì?

Trong ví dụ, RowSet được nạp từ:

```sql
SELECT note_id, customer_id, note_text, revision
FROM customer_note
WHERE customer_id = ?
ORDER BY note_id;
```

Khi đồng bộ, provider cần biết **bảng nào sẽ bị sửa** và **hàng nào trong bảng tương ứng với một hàng của bản sao**. `setTableName("customer_note")` định danh bảng; `setKeyColumns(new int[] {1})` khai báo cột số 1 (`note_id`) là cột khóa. Chỉ số ở đây cũng **bắt đầu từ 1**, không phải từ 0.

Một số provider có thể tự suy ra bảng/khóa từ metadata truy vấn, nhưng không nên mặc định suy luận đó đầy đủ. Với `JOIN` nhiều bảng, alias phức tạp, cột tính toán hoặc projection thiếu khóa chính, việc đồng bộ chung có thể không thực hiện được hoặc có rủi ro nhắm sai hàng. Khi nghiệp vụ cần `UPDATE` có điều kiện và kiểm tra phiên bản, **viết SQL tường minh** thường dễ dự đoán hơn.

### `acceptChanges()` không nhận kết nối

Biến thể không đối số có thể được dùng nếu RowSet đã được cấu hình đủ **nguồn kết nối, lệnh truy vấn, thông tin xác thực và provider** để tự lấy connection khi cần. Nếu RowSet chỉ được tạo trống rồi nạp bằng `populate(ResultSet)`, đừng giả định nó có sẵn thông tin kết nối để gọi `acceptChanges()` không đối số. Ví dụ này chọn `acceptChanges(syncConnection)` để thể hiện rõ việc **mở lại kết nối tại thời điểm đồng bộ**, thay vì để RowSet tự quản lý thông tin đăng nhập.

Không nên nhúng username/password trực tiếp vào mã nguồn hoặc lưu vào bản sao RowSet nếu ứng dụng có thể sử dụng `DataSource` được cấu hình an toàn.

## 7. Xung đột đồng bộ và dữ liệu bị cũ

Giả sử hai người A và B cùng nạp ghi chú `note_id = 501` khi văn bản là `"Giao sáng"`:

```text
Thời điểm       Người A                       Người B
-----------     ----------------------------  ----------------------------
t1              Nạp ghi chú: "Giao sáng"      Nạp ghi chú: "Giao sáng"
t2              Sửa thành "Giao chiều"        Chưa sửa
t3              Đồng bộ thành công            Sửa thành "Giao tối"
t4              DB có "Giao chiều"            Thử acceptChanges
                                                |
                                                v
                                         Có thể xảy ra conflict
```

Nếu provider dùng cơ chế **optimistic synchronization**, nó có thể so sánh dữ liệu gốc được nạp với dữ liệu hiện tại trong DB trước khi ghi. Khi phát hiện một người khác đã thay đổi cùng hàng, provider có thể ném `SyncProviderException` để ứng dụng xử lý. Mức độ kiểm tra thay đổi phụ thuộc `SyncProvider`, metadata, khóa hàng và cơ sở dữ liệu; **không được tự khẳng định mọi provider đều phát hiện xung đột như nhau**.

`javax.sql.rowset.spi.SyncProviderException` là một loại `SQLException`. Nó có thể cung cấp `SyncResolver` để mô tả hoặc xử lý xung đột theo khả năng provider:

```java
import javax.sql.rowset.spi.SyncProviderException;

try (Connection syncConnection = dataSource.getConnection()) {
    notes.acceptChanges(syncConnection);
} catch (SyncProviderException conflict) {
    // Đồng bộ thất bại. Không thông báo UI rằng đã lưu thành công.
    // Tùy provider, có thể dùng conflict.getSyncResolver() để xem chi tiết.
    // Chính sách an toàn mặc định: báo xung đột và yêu cầu tải/đối soát.
    throw conflict;
}
```

Ở đây `notes` là RowSet đang mở và đã có thay đổi; đoạn mã minh họa cách phân loại ngoại lệ. Một `SyncProviderException` không nhất thiết chỉ có nguyên nhân tranh chấp cùng hàng: nó cũng có thể báo **provider không đồng bộ được** vì hạn chế kỹ thuật hoặc xung đột ràng buộc. Phải xem thông tin lỗi thực tế trước khi quyết định “ưu tiên giá trị của ai”.

### Không tự giải quyết mọi conflict bằng ghi đè

Nếu một người sửa số điện thoại, người khác sửa địa chỉ, ứng dụng có thể muốn **gộp thay đổi không chồng lấn**. Nhưng nếu cả hai cùng sửa số dư, giá bán hoặc trạng thái phê duyệt, việc tự ghi đè bản mới lên bản cũ có thể làm mất dữ liệu hoặc vi phạm nghiệp vụ. Một số chính sách phổ biến:

- **Từ chối và yêu cầu tải lại:** phù hợp dữ liệu quan trọng khi chưa có logic gộp đáng tin cậy.
- **So sánh phiên bản:** dùng cột `revision` hoặc `updated_at` kết hợp với `UPDATE ... WHERE id = ? AND revision = ?`, sau đó kiểm tra số hàng được cập nhật; đây là cơ chế SQL ứng dụng phải thiết kế rõ ràng.
- **Gộp từng trường:** chỉ khi miền nghiệp vụ xác định được trường nào có thể gộp an toàn.
- **Ưu tiên một phía:** chỉ dùng khi có chính sách nghiệp vụ rõ ràng và chấp nhận nguy cơ mất thay đổi.

Nếu cần bảo đảm tuyệt đối rằng cột `revision` tăng đúng một lần với mọi cập nhật, ví dụ SQL tường minh thường dễ kiểm soát hơn cơ chế provider tổng quát:

```sql
UPDATE customer_note
SET note_text = ?, revision = revision + 1
WHERE note_id = ? AND revision = ?;
```

Khi dùng câu SQL trên qua `PreparedStatement`, `executeUpdate() == 1` nghĩa điều kiện phiên bản khớp và hàng đã được cập nhật; `0` nghĩa hàng không tồn tại hoặc revision đã khác. Điều này **không tự do `CachedRowSet` thực hiện** chỉ vì bảng có cột `revision`. Đây là một **phương án thay thế** khi muốn quy tắc xung đột minh bạch và có thể kiểm thử.

## 8. Vai trò của `SyncProvider` và `SyncResolver`

`CachedRowSet` được triển khai bởi một **RowSet provider**, với phần đồng bộ được điều phối qua cơ chế trong gói `javax.sql.rowset.spi`. Những khái niệm đáng biết:

| Thành phần | Trách nhiệm |
| --- | --- |
| `RowSetProvider` / `RowSetFactory` | Tạo các RowSet dựa trên triển khai được chọn |
| `CachedRowSet` | Giữ dữ liệu, metadata và trạng thái thay đổi ở bộ nhớ |
| `SyncProvider` | Cung cấp chiến lược đọc/ghi và khả năng đồng bộ theo provider |
| `SyncResolver` | Cho phép xem/xử lý các xung đột đồng bộ khi provider hỗ trợ |
| `SyncProviderException` | Thông báo việc đồng bộ không hoàn tất, có thể kèm thông tin xung đột |

Khả năng đồng bộ khác nhau theo provider. Không phải cứ `RowSetProvider.newFactory().createCachedRowSet()` tạo thành công là mọi thao tác `insertRow`, `deleteRow`, `acceptChanges` đều hoạt động với mọi kiểu truy vấn, mọi DBMS và mọi JDBC driver.

Để tìm hiểu mức đồng bộ, ứng dụng có thể xem provider được RowSet sử dụng bằng `getSyncProvider()` nếu triển khai hỗ trợ và thông tin trả về phù hợp. Tuy nhiên, tên provider hay mức hỗ trợ được công bố không thay thế integration test cho các trường hợp `UPDATE`, `INSERT`, `DELETE` và tranh chấp thực tế.

### Nếu cần quan sát hàng bị thay đổi

Trên hàng hiện tại, `rowUpdated()`, `rowInserted()` và `rowDeleted()` có thể cung cấp dấu hiệu đã thay đổi theo hợp đồng RowSet. Khi xóa, một số RowSet ẩn các hàng đã đánh dấu xóa trong vòng lặp mặc định; `setShowDeleted(true)` cho phép hiển thị các hàng bị đánh dấu theo khả năng API. Việc một hàng xuất hiện hay không trong vòng lặp sau `deleteRow()` **không phải bằng chứng DB đã bị xóa**.

Trong ứng dụng có yêu cầu audit nghiêm ngặt, nên ghi lại danh sách thao tác nghiệp vụ rõ ràng (khóa, giá trị cũ, giá trị mới, người thực hiện, thời điểm) thay vì chỉ dựa vào trạng thái nội bộ của RowSet.

## 9. Dữ liệu lớn: phân trang và giới hạn bộ nhớ

Lợi ích của `CachedRowSet` đi kèm chi phí: toàn bộ các hàng được nạp chiếm **bộ nhớ ứng dụng**. Nếu câu truy vấn trả một triệu hàng, việc sao chép tất cả vào RowSet có thể gây áp lực cấp phát, GC hoặc hết bộ nhớ. Không nên dùng `CachedRowSet` làm nơi lưu toàn bộ một bảng lớn chỉ vì muốn thao tác ngoại tuyến.

Những biện pháp thường dùng:

1. **Giới hạn tập kết quả ở SQL:** `WHERE`, `ORDER BY`, phân trang hay lọc theo khóa nghiệp vụ.
2. **Chỉ chọn cột cần thiết:** đặc biệt tránh tải BLOB/CLOB lớn khi UI chỉ cần thông tin tóm tắt.
3. **Đo bộ nhớ và thời gian `populate`:** chi phí nằm ở kích thước dữ liệu và cách provider lưu trữ, không chỉ số hàng.
4. **Quản lý số RowSet sống đồng thời:** mỗi tab hoặc phiên người dùng giữ một bản sao riêng có thể làm tăng bộ nhớ nhanh chóng.
5. **Đóng RowSet khi xong:** đặc biệt khi dữ liệu có tài nguyên phụ hoặc provider giữ tham chiếu không cần thiết.

`CachedRowSet` có các phương thức liên quan phân trang như `setPageSize(...)`, `nextPage()` và `previousPage()`, nhưng hành vi và nguồn dữ liệu cần được cấu hình đúng, đồng thời phụ thuộc provider. **Đừng mặc định chỉ đặt `setPageSize(100)` trước `populate(rs)` là đã có cơ chế phân trang server an toàn và không cần giữ kết nối.** Nếu ứng dụng cần phân trang thực sự, nhiều trường hợp truy vấn SQL theo từng trang với `LIMIT/OFFSET` hoặc keyset pagination tùy DB rõ ràng hơn.

Khi phân trang, hãy giữ `ORDER BY` ổn định theo một khóa duy nhất và cân nhắc thay đổi đồng thời làm dữ liệu giữa các trang không hoàn toàn nhất quán. Điều này không phải lỗi riêng của `CachedRowSet`; nó là vấn đề thiết kế truy vấn và mức cô lập dữ liệu.

## 10. So sánh `CachedRowSet` với `List<record>` và `ResultSet`

| Tiêu chí | `ResultSet` trực tiếp | `CachedRowSet` | `List<record>` |
| --- | --- | --- | --- |
| Cần giữ kết nối/trạng thái JDBC khi duyệt? | Thường có | Không sau khi đã nạp | Không |
| Duyệt qua con trỏ kiểu JDBC | Có | Có | Không; dùng vòng lặp Java thông thường |
| Có metadata cột JDBC | Có | Có | Thường không cần |
| Chỉnh sửa dữ liệu cục bộ | Tùy loại ResultSet | Có qua `updateXxx`, `updateRow`, ... nếu provider hỗ trợ | Record bất biến; tạo giá trị mới thay vì sửa tại chỗ |
| Đồng bộ thay đổi về DB | Qua SQL trực tiếp hoặc ResultSet updatable | Có `acceptChanges` tùy provider | Repository phải tự viết SQL cập nhật |
| Khả năng kiểm soát concurrency | Theo truy vấn/transaction | Phụ thuộc provider và chính sách xung đột | Do repository/SQL quyết định rõ ràng |
| Chi phí bộ nhớ cho nhiều hàng | Có thể đọc dần theo driver | Giữ bản sao dữ liệu | Giữ các đối tượng Java đã ánh xạ |
| Mức gắn kết với JDBC | Cao | Vẫn dùng API kiểu JDBC | Thấp, phù hợp domain/service/API |

Nếu người dùng chỉ cần xem danh sách đơn hàng sau khi kết nối đóng, **ánh xạ `ResultSet` thành `List<OrderSummary>` bất biến** thường dễ bảo trì hơn. `CachedRowSet` có ích khi ứng dụng thực sự muốn giữ **bản sao có metadata, con trỏ và trạng thái sửa đổi**, chẳng hạn các công cụ dữ liệu, màn hình desktop hoặc quy trình thử chỉnh sửa nhiều hàng trước khi đồng bộ.

Ở hệ thống web hiện đại, việc đặt `CachedRowSet` trực tiếp vào HTTP session cho nhiều người dùng có thể tạo chi phí bộ nhớ và vấn đề chia sẻ trạng thái. Nên thiết kế DTO, API cập nhật và cơ chế kiểm tra phiên bản thay vì mặc định RowSet là mô hình dữ liệu trung tâm.

## 11. Các lỗi và hiểu lầm thường gặp

| Hiểu lầm hoặc lỗi | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Giữ `ResultSet` nguồn để đọc sau khi đóng kết nối | Con trỏ có thể không còn hợp lệ | Gọi `cached.populate(rs)` trước khi đóng tài nguyên nguồn |
| Coi `updateRow()` là cập nhật DB | UI báo lưu thành công trong khi DB chưa đổi | Phân biệt sửa cục bộ với `acceptChanges` thành công |
| Không cung cấp bảng hoặc khóa cần thiết khi đồng bộ | Provider không biết cập nhật hàng nào | Cấu hình `setTableName`, `setKeyColumns` hoặc dùng SQL tường minh |
| Dùng index cột 0 trong `setKeyColumns` | JDBC đánh chỉ số cột từ 1 | Kiểm tra thứ tự SELECT và dùng chỉ số 1-based |
| Giả định mọi provider hỗ trợ `acceptChanges` | Có thể bị từ chối hoặc cập nhật không đúng kỳ vọng | Kiểm thử với đúng RowSet provider/driver/schema |
| Truyền Connection đang ở transaction lớn vào `acceptChanges` | Provider có thể commit/rollback ngoài ý muốn | Dùng transaction độc lập hoặc kiểm soát SQL bằng repository |
| Hai người chỉnh cùng hàng và mặc định người cuối thắng | Mất thay đổi hoặc xung đột không được xử lý | Phát hiện xung đột, đối soát hoặc dùng version check tường minh |
| Nạp toàn bộ bảng vào RowSet | Dùng nhiều RAM, thời gian nạp dài | Giới hạn truy vấn và phân trang rõ ràng |
| Dùng `CachedRowSet` như kho dữ liệu lâu dài | Mất thay đổi khi ứng dụng dừng nếu chưa lưu | Thiết kế lưu trữ ngoại tuyến bền vững riêng |
| Chia sẻ RowSet đang sửa giữa nhiều thread | Trạng thái con trỏ và cập nhật có thể tranh chấp | Không chia sẻ mutable RowSet nếu không có thiết kế đồng bộ rõ ràng |
| Mở RowSet nhưng quên đóng | Giữ tài nguyên không cần thiết | `try-with-resources` và quy định quyền sở hữu |
| Coi bản sao là dữ liệu mới nhất | Dữ liệu DB có thể đã thay đổi trong lúc ngoại tuyến | Nạp lại hoặc đối soát phiên bản khi đồng bộ |

### An toàn thông tin cho dữ liệu ngoại tuyến

`CachedRowSet` tạo thêm một bản sao dữ liệu trong bộ nhớ ứng dụng. Đối với dữ liệu cá nhân hoặc nhạy cảm, cần kiểm soát tập cột truy vấn, thời gian giữ bản sao, quyền truy cập ở tầng ứng dụng và các hoạt động xuất dữ liệu. Không mặc định RowSet tự mã hóa dữ liệu hoặc áp dụng quyền truy cập của DB khi ứng dụng đã ngắt kết nối.

Nếu người dùng A chỉ được xem ghi chú của khách hàng A, việc giữ dữ liệu trong bộ nhớ không tự bảo đảm chính sách ủy quyền cho những lần sửa hoặc đồng bộ tiếp theo. Khi ghi lại vào DB, hệ thống vẫn phải kiểm tra quyền và phạm vi dữ liệu theo yêu cầu nghiệp vụ.

## 12. Kiểm thử trên DB và RowSet provider thật

Không phải mock `CachedRowSet` chạy được `next()` là đã chứng minh đồng bộ hoạt động đúng. Một bộ integration test nên có cả thao tác ngoại tuyến lẫn xác minh dữ liệu sau khi đồng bộ bằng **một kết nối mới**.

| Tình huống | Cách thử | Kết quả kỳ vọng |
| --- | --- | --- |
| Nạp hai ghi chú | `populate(rs)` khi connection nguồn mở | RowSet chứa đúng hai hàng và metadata cột |
| Đọc khi đã đóng connection nguồn | Tạo RowSet, thoát repository, gọi `beforeFirst`/`next` | Đọc lại được các giá trị đã nạp |
| Sửa RowSet chưa đồng bộ | `updateString` + `updateRow` rồi đọc DB bằng connection khác | Bản sao có giá trị mới; DB vẫn giữ giá trị cũ |
| Sửa và đồng bộ thành công | Cấu hình table/key, gọi `acceptChanges(connection)` | Đọc DB lại thấy thay đổi, nếu provider hỗ trợ |
| Đồng bộ khi hàng đã bị xóa ở DB | Nạp rồi xóa hàng tại kết nối khác, sau đó `acceptChanges` | Phát hiện lỗi hoặc xung đột theo khả năng provider; không giả vờ thành công |
| Hai người sửa một hàng | Nạp hai RowSet, đồng bộ bản A rồi bản B | Kiểm tra cơ chế phát hiện conflict thật của provider |
| Thiếu hoặc sai key columns | Gọi đồng bộ với cấu hình khóa sai | Lỗi được báo; không cập nhật nhầm hàng |
| `NULL` trong cột nullable | Đọc/ghi giá trị nullable theo schema | Phân biệt `NULL` và giá trị mặc định |
| Nạp tập kết quả lớn | Đo heap, thời gian và GC của `populate` | Hiểu giới hạn trước khi đưa vào sản xuất |
| Không có mạng lúc đồng bộ | Làm việc với bản sao rồi thử `acceptChanges` khi DB không sẵn sàng | Ghi nhận đồng bộ thất bại; không báo đã lưu |

### Một phép thử tối thiểu minh họa việc ngắt kết nối

```java
try (CachedRowSet notes = repository.loadForCustomer(42L)) {
    // Repository đã đóng Connection mà nó sở hữu.
    notes.beforeFirst();

    int count = 0;
    while (notes.next()) {
        count++;
        System.out.println(notes.getString("note_text"));
    }
    System.out.println("Cached rows = " + count);
}
```

Phép thử này chỉ xác nhận **đọc ngoại tuyến**. Muốn kiểm tra đồng bộ, phải thực hiện `updateRow()`, gọi `acceptChanges` có cấu hình phù hợp và đọc DB lại qua connection khác. Đồng thời cần kiểm tra trường hợp một bên đã sửa dữ liệu sau khi RowSet được nạp; không chỉ kiểm tra đường thành công một người dùng.

## 13. Bài tập tự kiểm tra

**Bài 1 — Phân biệt hai kết nối.** Một repository nạp kết quả vào `CachedRowSet` qua `populate(rs)` rồi đóng `ResultSet`, `PreparedStatement` và `Connection`. Caller có đọc lại ghi chú từ RowSet bằng `beforeFirst()` và `next()` được không? Vì sao?

**Đáp án:** Có, khi `populate` thành công và RowSet còn mở. Các hàng đã nằm trong bộ nhớ; con trỏ của RowSet không cần kết nối nguồn để duyệt lại.

**Bài 2 — Chỉnh sửa có phải lưu?** Người dùng đổi `note_text`, gọi `updateRow()` nhưng không gọi `acceptChanges()`. DB có chắc chắn được cập nhật không?

**Đáp án:** Không. `updateRow` ghi nhận thay đổi cục bộ; DB chỉ được sửa bởi một bước đồng bộ hoặc câu SQL khác được thực thi và xác nhận.

**Bài 3 — Khóa hàng.** Một `CachedRowSet` được nạp từ `SELECT note_id, customer_id, note_text, revision`. Muốn dùng cột `note_id` làm khóa, gọi `setKeyColumns(new int[] {0})` hay `setKeyColumns(new int[] {1})`?

**Đáp án:** Dùng `{1}` vì chỉ số cột trong JDBC bắt đầu từ 1. Cũng cần `setTableName` và khả năng đồng bộ phù hợp của provider.

**Bài 4 — Hai người sửa.** A và B cùng nạp ghi chú gốc, A đồng bộ thay đổi trước, B tiếp tục đồng bộ. Có thể coi lần đồng bộ của B luôn thành công và tự ghi đè A không?

**Đáp án:** Không. Cần xem xung đột theo provider và chính sách nghiệp vụ; khi không chắc chắn, từ chối/đối soát thay vì ghi đè mù quáng.

**Bài 5 — Transaction bên ngoài.** Một service đang thực hiện transaction gồm cập nhật đơn hàng, tồn kho và ghi chú. Có nên truyền cùng `Connection` đó vào một `CachedRowSet.acceptChanges(connection)` khi chưa biết provider có commit không?

**Đáp án:** Không nên. Cơ chế đồng bộ có thể quản lý commit/rollback; cần kiểm chứng hoặc tự dùng `PreparedStatement` trên connection do service sở hữu để giữ đúng ranh giới transaction.

**Bài 6 — Chọn công cụ.** API chỉ cần trả danh sách gồm `note_id` và `note_text` cho người dùng xem, không cho chỉnh sửa ngoại tuyến. `CachedRowSet` hay `List<NoteSummary>` bất biến thường phù hợp hơn?

**Đáp án:** `List<NoteSummary>` thường đơn giản, ít phụ thuộc JDBC hơn. `CachedRowSet` có ý nghĩa khi cần duyệt theo kiểu RowSet, giữ metadata hoặc chỉnh sửa/đồng bộ bản sao.

**Bài 7 — Phân trang.** Vì sao nạp một triệu hàng vào `CachedRowSet` có thể không phù hợp dù sau đó không cần mở kết nối lâu?

**Đáp án:** RowSet giữ dữ liệu trong bộ nhớ ứng dụng, làm tăng RAM và GC. Nên giới hạn truy vấn, đo tải thực tế và dùng phân trang SQL hoặc chiến lược xử lý khác.

**Bài 8 — Dữ liệu tồn tại qua các phiên.** Người dùng sửa RowSet khi mất mạng và đóng ứng dụng trước khi đồng bộ. `CachedRowSet` có tự bảo đảm lần sau mở ứng dụng vẫn giữ thay đổi không?

**Đáp án:** Không. Bản sao trong bộ nhớ không phải kho lưu trữ ngoại tuyến bền vững; nếu cần làm việc qua nhiều phiên, phải thiết kế lưu trạng thái và quá trình đồng bộ riêng.

## Tổng kết

`CachedRowSet` trong JDBC giúp **sao chép dữ liệu từ `ResultSet` vào bộ nhớ để tiếp tục đọc và chỉnh sửa sau khi đóng kết nối nguồn**. Tạo RowSet qua `RowSetProvider`, nạp bằng `populate(rs)` khi kết quả truy vấn còn mở, rồi chuyển quyền sở hữu RowSet cho caller và đóng nó khi xong. Những thay đổi qua `updateXxx`, `updateRow`, `insertRow` hoặc `deleteRow` vẫn chỉ ở bản sao cho đến khi được đồng bộ thành công. `acceptChanges(Connection)` phụ thuộc RowSet provider, thông tin bảng/khóa và trạng thái DB; xung đột đồng thời phải được xử lý rõ ràng, đặc biệt khi provider có thể điều khiển transaction của connection dùng để đồng bộ. Hãy chọn `CachedRowSet` khi thật sự cần **bản sao có trạng thái ngoại tuyến**, còn với truy vấn chỉ đọc hoặc cập nhật cần kiểm soát chặt, `List<record>` và `PreparedStatement` tường minh thường dễ duy trì hơn.
