# Đánh giá chi phí bộ nhớ và giới hạn của dữ liệu tách kết nối trong JDBC

Trong chương **RowSet ngoại tuyến**, một ưu điểm của JDBC là có thể **đưa kết quả truy vấn ra khỏi vòng đời của kết nối**: đọc các hàng từ cơ sở dữ liệu, lưu chúng trong một đối tượng `CachedRowSet`, đóng `ResultSet`/`PreparedStatement`/`Connection` rồi tiếp tục xử lý dữ liệu ở phía Java.

Nhưng sự tiện lợi ấy đi kèm đánh đổi: **đã tách kết nối thì ứng dụng phải giữ dữ liệu ở đâu đó**. Với `CachedRowSet`, phần lớn nội dung được materialize vào bộ nhớ của tiến trình Java; dữ liệu có thể bị cũ, số hàng và kích thước từng cột có thể vượt dự tính, và những thay đổi thực hiện ngoại tuyến không tự động trở thành giao dịch đã commit trong DBMS.

Trong module **JDBC**, ngoài thao tác CRUD bằng `PreparedStatement`, đọc dữ liệu qua `ResultSet` và quản lý transaction, bạn cần hiểu khi nào RowSet ngoại tuyến phù hợp, cách đặt giới hạn tài nguyên, khi nào nên chuyển sang streaming/phân trang, và cách nhận diện xung đột lúc đồng bộ.

Sau bài học, bạn có thể:

- Phân biệt `CachedRowSet` với `ResultSet` kết nối trực tiếp và `JdbcRowSet`.
- Giải thích các nguồn chi phí bộ nhớ: giá trị cột, metadata, trạng thái hàng, bản gốc/bản sửa, đối tượng Java và bản sao khi biến đổi.
- Viết mã dùng `RowSetProvider` để nạp một tập dữ liệu **có giới hạn**, rồi đóng connection trước khi duyệt.
- Ước lượng và đo bộ nhớ bằng công cụ JVM thay vì chỉ dựa vào kích thước payload.
- Phân biệt khả năng lưu ngoại tuyến, phân trang, tính nhất quán dữ liệu và xung đột khi `acceptChanges()`.
- Chọn cách thay thế phù hợp cho xuất dữ liệu lớn, ứng dụng nhiều người dùng và workload có BLOB/CLOB.

## 1. Dữ liệu tách kết nối là gì?

Một `ResultSet` JDBC thông thường gắn với `Statement` và `Connection` tạo ra nó. Khi chương trình gọi `rs.next()`, driver có thể truy xuất dữ liệu từ bộ đệm hoặc DBMS theo từng đợt. Vòng đời của `ResultSet` gắn chặt với tài nguyên JDBC và có thể bị ảnh hưởng khi statement/connection đóng, transaction kết thúc hoặc driver đóng server cursor.

`CachedRowSet` là một triển khai RowSet **disconnected**, cho phép giữ tập kết quả bên phía Java và sử dụng nó sau khi kết nối nguồn đã đóng. Ví dụ:

~~~mermaid
flowchart LR
    A["DBMS"] --> B["Connection + PreparedStatement"]
    B --> C["ResultSet đang kết nối"]
    C --> D["CachedRowSet: nạp bản sao các hàng"]
    D --> E["Đóng ResultSet và Connection"]
    E --> F["Duyệt, lọc hoặc chỉnh dữ liệu trong Java"]
    F --> G["Đồng bộ có kiểm soát hoặc bỏ dữ liệu"]
~~~

**“Disconnected” không phải “lưu vĩnh viễn xuống ổ đĩa”.** Dữ liệu trong `CachedRowSet` nằm trong đối tượng Java; khi không còn tham chiếu, đối tượng có thể được thu gom rác. Nếu muốn lưu qua lần chạy ứng dụng khác, cần cơ chế lưu trữ rõ ràng, đi kèm bảo mật và versioning.

### Các loại RowSet dễ nhầm

| Loại | Bản chất | Nên dùng khi |
| --- | --- | --- |
| `java.sql.ResultSet` | Kết quả truy vấn qua JDBC; vòng đời gắn với statement/connection | Đọc một lượt, đặc biệt khi cần xử lý nhiều hàng |
| `javax.sql.rowset.JdbcRowSet` | RowSet kiểu **connected**, dùng JDBC connection để hoạt động | Muốn API RowSet và điều hướng nhưng vẫn có kết nối |
| `javax.sql.rowset.CachedRowSet` | RowSet kiểu **disconnected**, giữ dữ liệu đã nạp để dùng ngoại tuyến | Tập dữ liệu vừa phải cần duyệt/chỉnh sửa sau khi đóng connection |
| `WebRowSet` | Mở rộng `CachedRowSet`, hỗ trợ biểu diễn/trao đổi dữ liệu dạng XML | Có yêu cầu xuất/nhập RowSet XML có kiểm soát |
| `FilteredRowSet` | Mở rộng RowSet với cơ chế lọc dựa trên predicate | Lọc một tập dữ liệu đã có, không thay thế `WHERE` ở DB |
| `JoinRowSet` | Hỗ trợ kết hợp dữ liệu RowSet theo quy tắc API | Một số trường hợp ghép dữ liệu phía Java, không thay thế JOIN ở DB cho dữ liệu lớn |

Không nên kết luận rằng tất cả các RowSet đều hoạt động ngoại tuyến hoặc có cùng đặc điểm về RAM. Với bài này, **`CachedRowSet` là ví dụ trung tâm**.

## 2. Vì sao `CachedRowSet` tiêu tốn bộ nhớ?

Khi gọi `CachedRowSet.populate(ResultSet)`, ứng dụng nạp các hàng từ kết quả nguồn vào một cấu trúc dữ liệu Java do RowSet provider quản lý. Dữ liệu không còn chỉ nằm ở DBMS hoặc trên dòng truyền mạng.

Mức dùng bộ nhớ không chỉ bằng tổng số byte SQL được truyền:

| Nguồn chi phí | Nội dung |
| --- | --- |
| **Giá trị các cột** | `String`, số, ngày giờ, mảng byte, đối tượng do driver chuyển đổi |
| **Cấu trúc hàng và cột** | Đối tượng chứa hàng, tham chiếu, cấu trúc nội bộ của provider |
| **Metadata** | Tên cột, SQL type, khả năng nullable, precision/scale và thuộc tính khác |
| **Trạng thái thay đổi** | Cờ insert/update/delete, giá trị gốc hoặc thông tin cần cho đồng bộ xung đột |
| **Bản sao không mong muốn** | Chuỗi/mảng byte được copy khi nạp, khi thao tác, khi serialize hay xuất ra định dạng khác |
| **Bộ đệm JDBC** | Driver có thể buffer `ResultSet` nguồn hoặc toàn bộ truy vấn trước khi `populate()` |
| **Đối tượng bên ngoài RowSet** | DTO, list, map, JSON, file export hoặc cache của ứng dụng cùng giữ tham chiếu |

Cách ước lượng ban đầu:

\[
M_{\text{heap}} \approx M_{\text{dữ liệu nạp}} + M_{\text{đối tượng/hàng}} + M_{\text{metadata}} + M_{\text{bản sao và trạng thái}}
\]

Đây chỉ là **mô hình tư duy**, không phải công thức có thể cho số byte chính xác. Java VM có thể dùng compact strings, object alignment, nén tham chiếu và cấu trúc nội bộ khác nhau; provider cũng có thể lưu dữ liệu theo cách khác.

### Ví dụ quy mô

Giả sử đọc **100.000 hàng**, mỗi hàng có một payload văn bản dài trung bình 1 KiB theo biểu diễn đo ở một bước nào đó:

- Phần payload đã khoảng **100 MiB** (100.000 × 1.024 byte ≈ 97,7 MiB).
- Thêm `id`, các cột khác, đối tượng `String`, cấu trúc hàng, metadata và trạng thái RowSet.
- Nếu ứng dụng cùng lúc tạo `List<DTO>` hoặc một chuỗi JSON chứa mọi hàng, có thể tồn tại **hai hoặc nhiều biểu diễn dữ liệu** trong heap.
- Nếu driver cũng giữ kết quả gốc trong bộ nhớ, đỉnh sử dụng RAM có thể vượt xa kích thước payload ước tính.

**Không nên gán một tỷ lệ chính xác như “CachedRowSet tốn gấp 2 lần” cho mọi driver.** Cần đo chính workload, provider, phiên bản JDK và DBMS.

### Độ phức tạp bộ nhớ

Nếu nạp \(R\) hàng, mỗi hàng trung bình giữ \(S\) byte giá trị đã được biểu diễn trong Java, bộ nhớ lưu dữ liệu ít nhất có xu hướng tăng theo \(O(R \times S)\), cộng thêm overhead. Điều này khác với cách xử lý theo luồng, nơi ứng dụng có thể chỉ giữ một phần nhỏ tập kết quả tại một thời điểm.

**Giới hạn heap là giới hạn chung của cả ứng dụng**, không phải một ngân sách riêng cho RowSet. Nạp một CachedRowSet rất lớn có thể gây tăng áp lực GC, tạm dừng lâu hoặc `OutOfMemoryError`, khiến cả các request khác bị ảnh hưởng.

## 3. So sánh bộ nhớ và vòng đời tài nguyên

| Tiêu chí | `ResultSet` đọc theo luồng | `CachedRowSet` ngoại tuyến |
| --- | --- | --- |
| Cần connection khi duyệt? | Thông thường có | Không, sau khi nạp xong |
| Bộ nhớ cho toàn bộ tập kết quả | Có thể thấp nếu driver fetch theo đợt, nhưng **không mặc nhiên bảo đảm** | Thường tỷ lệ với lượng dữ liệu đã nạp |
| Đọc lại các hàng cũ | Tùy loại cursor/driver, có thể không hỗ trợ | Có thể di chuyển con trỏ trên dữ liệu đã lưu |
| Dễ chuyển qua nhiều lớp sau khi đóng DB connection | Không | Có |
| Dữ liệu được tự động cập nhật từ DB? | Phụ thuộc ResultSet type, isolation và driver | **Không**; dữ liệu đã nạp không tự refresh |
| Thay đổi rồi ghi lại DB | Qua SQL/transaction hoặc updatable ResultSet khi được hỗ trợ | Có `acceptChanges()` nhưng phải xử lý xung đột |
| Phù hợp với hàng triệu bản ghi | Thường dùng streaming/chunking hợp lý hơn | Thường không phù hợp nếu nạp toàn bộ |
| Rủi ro giữ tài nguyên DB lâu | Có nếu đọc chậm/giữ cursor mở | Thấp hơn sau lúc populate, nhưng đổi sang tiêu thụ RAM |
| Rủi ro dữ liệu cũ | Cần hiểu snapshot/isolation | Rất rõ: dữ liệu không tự đồng bộ |

**Không có công cụ nào miễn phí:** streaming tránh nạp toàn bộ vào heap nhưng có thể giữ connection/server cursor lâu; cached data trả kết nối sớm nhưng giữ nội dung ở RAM và có thể lỗi thời.

## 4. Ví dụ Java: nạp `CachedRowSet` rồi đóng connection

API tiêu chuẩn `javax.sql.rowset.RowSetProvider` tạo `CachedRowSet` mà không cần phụ thuộc trực tiếp vào một lớp triển khai nội bộ JDK.

Giả sử bảng:

~~~sql
CREATE TABLE tasks (
    id BIGINT PRIMARY KEY,
    title VARCHAR(200) NOT NULL,
    status VARCHAR(30) NOT NULL,
    version BIGINT NOT NULL DEFAULT 0
);
~~~

Ví dụ nạp một tập kết quả có giới hạn, chỉ lấy các cột cần thiết:

~~~java
import javax.sql.DataSource;
import javax.sql.rowset.CachedRowSet;
import javax.sql.rowset.RowSetProvider;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.Objects;

public final class TaskSnapshotRepository {
    private static final int MAX_PAGE_SIZE = 500;
    private final DataSource dataSource;

    public TaskSnapshotRepository(DataSource dataSource) {
        this.dataSource = Objects.requireNonNull(dataSource);
    }

    /**
     * Caller sở hữu CachedRowSet được trả về và phải close().
     * Chỉ trả các hàng có id > afterId, tối đa pageSize.
     */
    public CachedRowSet loadAfter(long afterId, int pageSize)
            throws SQLException {
        if (pageSize < 1 || pageSize > MAX_PAGE_SIZE) {
            throw new IllegalArgumentException(
                "pageSize phải nằm trong khoảng 1..500"
            );
        }

        String sql = """
            SELECT id, title, status, version
            FROM tasks
            WHERE id > ?
            ORDER BY id
            """;

        CachedRowSet cached =
            RowSetProvider.newFactory().createCachedRowSet();

        try (Connection conn = dataSource.getConnection();
             PreparedStatement ps = conn.prepareStatement(sql)) {

            ps.setLong(1, afterId);

            // Giới hạn số hàng của ResultSet: giảm lượng nạp vào RowSet.
            ps.setMaxRows(pageSize);

            // Gợi ý số hàng fetch; không phải cam kết streaming từ DBMS.
            ps.setFetchSize(pageSize);

            try (ResultSet source = ps.executeQuery()) {
                cached.populate(source);
            }

            // Connection và ResultSet nguồn được đóng trước khi trả về.
            return cached;

        } catch (SQLException | RuntimeException failure) {
            try {
                cached.close();
            } catch (SQLException closeFailure) {
                failure.addSuppressed(closeFailure);
            }
            throw failure;
        }
    }
}
~~~

Ví dụ sử dụng:

~~~java
import javax.sql.rowset.CachedRowSet;

TaskSnapshotRepository repository =
    new TaskSnapshotRepository(dataSource);

try (CachedRowSet page = repository.loadAfter(0L, 200)) {
    while (page.next()) {
        System.out.printf(
            "id=%d, title=%s, status=%s%n",
            page.getLong("id"),
            page.getString("title"),
            page.getString("status")
        );
    }

    // Có thể quay lại hàng đầu tiên mà không cần DB connection.
    if (page.first()) {
        System.out.println("First task: " + page.getLong("id"));
    }
}
~~~

### Vì sao ví dụ có giới hạn ở cả SQL lẫn RowSet?

- `WHERE id > ? ORDER BY id` tạo ranh giới truy xuất theo **khóa ổn định**, thuận lợi để phân trang.
- `setMaxRows(pageSize)` yêu cầu statement giới hạn **số hàng trả về cho ứng dụng**, giúp tránh nạp vô hạn vào `CachedRowSet`.
- `setFetchSize(pageSize)` là một **hint cho driver**, không bảo đảm DBMS chỉ quét đúng `pageSize` hàng hoặc mạng chỉ truyền lượng ấy.
- Một câu `SELECT *` có thể vô tình nạp BLOB/CLOB và cột không sử dụng; chọn đúng cột giảm đáng kể payload.
- `CachedRowSet` được đóng bởi caller; mặc dù nó tách khỏi connection, vẫn cần giải phóng các tài nguyên và tham chiếu dữ liệu sớm.

**Giới hạn kỹ thuật:** `setMaxRows()` không phải cú pháp phân trang server-side tối ưu cho mọi DBMS. Driver có thể xử lý kết quả hoặc buffer nhiều hàng trước khi ứng dụng chỉ nhìn thấy `pageSize` hàng. Với workload lớn, nên sử dụng `FETCH FIRST`, `LIMIT` hoặc cơ chế tương đương **đúng cú pháp DBMS đích**, kết hợp chỉ mục phù hợp và đo execution plan.

### Tối ưu độ ổn định khi phân trang

Câu truy vấn dùng `id > ?` là kiểu **keyset pagination**. Điều đó tốt hơn việc dựa vào thứ tự hàng không xác định, nhưng **không tự tạo snapshot nhất quán cho toàn bộ tập dữ liệu qua nhiều lần truy vấn**.

Nếu hàng bị thêm/xóa/cập nhật giữa các trang:

- Hàng mới có `id` lớn hơn con trỏ có thể xuất hiện ở trang sau.
- Một hàng mới nhưng có `id` nhỏ hơn con trỏ có thể không được thấy.
- Giá trị `title` hoặc `status` của cùng một hàng có thể khác nhau giữa các lần lấy trang.

Nếu nghiệp vụ cần xuất một tập cố định tại một thời điểm, phải thiết kế transaction isolation/snapshot, dữ liệu phiên bản hoặc chiến lược export thích hợp ở phía DBMS. Không dùng `CachedRowSet` theo từng trang rồi suy luận rằng mọi trang thuộc một snapshot bất biến.

## 5. Xử lý nhiều trang mà không giữ toàn bộ vào RAM

Ví dụ một tác vụ đọc toàn bộ bảng `tasks` và xử lý từng trang:

~~~java
import javax.sql.rowset.CachedRowSet;

static void processAllTasks(TaskSnapshotRepository repository)
        throws java.sql.SQLException {

    final int pageSize = 200;
    long afterId = 0L;

    while (true) {
        int rowsInPage = 0;
        long lastId = afterId;

        try (CachedRowSet page = repository.loadAfter(
                afterId, pageSize)) {

            while (page.next()) {
                long id = page.getLong("id");
                String title = page.getString("title");

                // Xử lý từng hàng, không giữ toàn bộ vào List.
                consumeTask(id, title);

                lastId = id;
                rowsInPage++;
            }
        }

        if (rowsInPage < pageSize) {
            break;
        }
        afterId = lastId;
    }
}
~~~

`consumeTask` đại diện cho một hàm nghiệp vụ xử lý từng dòng, không lưu tất cả dòng trong bộ nhớ. Mỗi vòng chỉ có **một CachedRowSet tối đa 200 hàng**, rồi đóng trước khi tải trang kế tiếp.

**Những điều phải bổ sung cho sản phẩm thực tế:**

- Bảo đảm `consumeTask` không giữ tham chiếu tới toàn bộ giá trị cột qua nhiều vòng. Nếu nó cho vào một `List` hoặc hàng đợi không giới hạn, mục tiêu giảm bộ nhớ thất bại.
- Có **checkpoint `lastId`** nếu muốn tiếp tục sau sự cố. Nếu xử lý tạo side effect, cần idempotency để không thực hiện trùng khi retry.
- Hạn chế số tác vụ xử lý đồng thời. Ví dụ 100 request cùng giữ mỗi request 500 hàng với payload lớn vẫn có thể gây quá tải heap.
- Nếu một hàng chứa LOB rất lớn, chỉ giới hạn số hàng **chưa đủ**. Cần giới hạn tổng số byte hoặc xử lý LOB theo luồng.
- Với bảng có thể bị thay đổi, hãy xác định chính sách nhất quán dữ liệu; keyset không thay thế snapshot isolation.

## 6. `CachedRowSet.setPageSize()` và `nextPage()` có giúp tiết kiệm RAM không?

JDBC `CachedRowSet` cung cấp cơ chế paging:

~~~java
import javax.sql.rowset.CachedRowSet;
import javax.sql.rowset.RowSetProvider;

CachedRowSet cached =
    RowSetProvider.newFactory().createCachedRowSet();

cached.setPageSize(200);
// Nạp dữ liệu theo API provider hỗ trợ, rồi có thể sử dụng
// cached.nextPage() hoặc previousPage() để chuyển trang.
~~~

Các phương thức liên quan bao gồm `setPageSize(int)`, `getPageSize()`, `nextPage()` và `previousPage()`.

Tuy nhiên, **paging của CachedRowSet không đồng nhất với phân trang SQL ở server**:

1. Cách provider nạp dữ liệu khi `execute()`/`populate(...)` và chuyển trang có thể khác nhau.
2. Driver vẫn có thể giữ toàn bộ `ResultSet` gốc trong bộ nhớ hoặc materialize nhiều hàng phía client.
3. Mỗi lần chuyển trang có thể cần kết nối đến DBMS hoặc nguồn dữ liệu thích hợp, tùy cách RowSet được thiết lập.
4. Khả năng và hiệu năng của paging phải được thử với RowSet provider/driver cụ thể.
5. Nếu query không có thứ tự ổn định, các trang có thể chồng lặp hoặc bỏ sót hàng khi dữ liệu thay đổi.

Vì thế, **đặt `pageSize = 200` không phải bảo đảm toàn bộ quy trình chỉ dùng bộ nhớ tương đương 200 hàng**. Với tập dữ liệu rất lớn, phân trang ở truy vấn SQL, chỉ lấy cột cần dùng và đóng từng page sau khi xử lý thường dễ kiểm soát và đo lường hơn.

## 7. Dữ liệu lớn trong một hàng: BLOB, CLOB, JSON và text dài

Một hàng duy nhất có thể có payload lớn hơn hàng nghìn hàng nhỏ. Ví dụ:

~~~sql
SELECT id, title, attachment_blob
FROM documents
WHERE id = ?;
~~~

Nếu `attachment_blob` chứa tệp 200 MiB, nạp nó vào `CachedRowSet` có thể khiến provider/driver phải giữ mảng byte hoặc LOB object lớn trong bộ nhớ. Việc sao chép, serialize hoặc chỉnh sửa có thể tạo thêm các bản sao.

**Không dựa vào giả định rằng tất cả RowSet provider đều lazy-load LOB theo cùng cách.** Một số kiểu LOB hoặc locator phụ thuộc connection/transaction; cần thử khả năng đọc sau khi disconnect, và điều gì xảy ra nếu nguồn đã đóng.

### Với tệp nhị phân hoặc text rất lớn

Ưu tiên xử lý từ `ResultSet` được kết nối và đọc theo luồng:

~~~java
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;

static void exportAttachment(
        Connection conn, long id, Path output
) throws Exception {
    String sql = """
        SELECT attachment_blob
        FROM documents
        WHERE id = ?
        """;

    try (PreparedStatement ps = conn.prepareStatement(sql)) {
        ps.setLong(1, id);

        try (ResultSet rs = ps.executeQuery()) {
            if (!rs.next()) {
                throw new IllegalArgumentException(
                    "Không tìm thấy tài liệu"
                );
            }

            try (InputStream in =
                     rs.getBinaryStream("attachment_blob")) {
                if (in == null) {
                    throw new IllegalStateException(
                        "attachment_blob là SQL NULL"
                    );
                }
                Files.copy(in, output);
            }
        }
    }
}
~~~

Đoạn mã minh họa không mở `CachedRowSet`; nó xử lý dữ liệu từ stream khi `ResultSet` và connection còn mở. Nếu file đích có thể tồn tại hoặc yêu cầu xuất **nguyên vẹn**, cần ghi vào file tạm rồi chuyển thành file chính sau khi hoàn tất, xử lý lỗi giữa chừng và giới hạn kích thước.

**Streaming qua API JDBC không đồng nghĩa driver chắc chắn không buffer.** Cần kiểm tra hỗ trợ fetch/stream của driver, transaction và khả năng server cursor. Đừng chỉ dùng `setFetchSize()` rồi cho rằng hàng chứa BLOB khổng lồ sẽ luôn có chi phí RAM thấp.

### Nên hạn chế những cột nào trong RowSet?

Với giao diện danh sách tài liệu, có thể chỉ truy vấn:

~~~sql
SELECT id, title, size_bytes, status
FROM documents
WHERE id > ?
ORDER BY id;
~~~

Chỉ khi người dùng mở chi tiết mới tải `attachment_blob` theo luồng. Đây là nguyên tắc **projection**: không chuyển dữ liệu lớn nếu chức năng không cần đến.

## 8. Sửa dữ liệu ngoại tuyến: `updateRow()` chưa phải commit vào DB

`CachedRowSet` có thể cho phép sửa giá trị cục bộ:

~~~java
if (cached.next()) {
    cached.updateString("status", "REVIEWED");
    cached.updateRow();
}
~~~

Ở đây dữ liệu nằm trong **bản sao RowSet trong bộ nhớ**. Lời gọi `updateRow()` đánh dấu cập nhật tại RowSet; nó **không tự chạy một câu `UPDATE` đã commit trên DBMS**.

Để cố đồng bộ thay đổi về cơ sở dữ liệu, `CachedRowSet` có `acceptChanges()` và `acceptChanges(Connection)`. Đây là nơi xuất hiện những vấn đề quan trọng:

- Sau khi RowSet được nạp, dữ liệu gốc có thể đã được transaction khác cập nhật/xóa.
- Bộ đồng bộ của RowSet cần xác định đúng bảng, khóa và giá trị gốc. Với truy vấn join, expression, thiếu khóa chính hoặc metadata không đầy đủ, đồng bộ có thể không thực hiện được.
- `acceptChanges()` có thể tạo kết nối để đồng bộ nếu RowSet được cấu hình thích hợp; `acceptChanges(conn)` dùng connection được cung cấp. Hành vi transaction cụ thể và rollback/commit của provider cần được kiểm tra.
- Nếu có xung đột, JDBC RowSet API có thể ném `SyncProviderException` và cung cấp `SyncResolver` để xử lý xung đột.
- Không phải mọi provider bảo đảm cùng một chính sách khóa, phát hiện xung đột hoặc mức độ hỗ trợ cho mọi loại câu SQL.

### Ví dụ đồng bộ có kiểm tra xung đột

~~~java
import javax.sql.DataSource;
import javax.sql.rowset.CachedRowSet;
import javax.sql.rowset.spi.SyncProviderException;
import java.sql.Connection;
import java.sql.SQLException;

static void markFirstTaskReviewed(
        TaskSnapshotRepository repository,
        DataSource dataSource
) throws SQLException {

    try (CachedRowSet cached = repository.loadAfter(0L, 50)) {
        // Cho provider biết bảng và khóa khi hỗ trợ cập nhật.
        cached.setTableName("tasks");
        cached.setKeyColumns(new int[] {1});

        if (!cached.next()) {
            return;
        }

        cached.updateString("status", "REVIEWED");
        cached.updateRow(); // Chỉ sửa dữ liệu ngoại tuyến.

        try (Connection conn = dataSource.getConnection()) {
            try {
                cached.acceptChanges(conn);
            } catch (SyncProviderException conflict) {
                // Không tự ghi đè thay đổi của người khác.
                // Có thể dùng conflict.getSyncResolver()
                // để kiểm tra xung đột rồi quyết định tải lại/hòa giải.
                throw conflict;
            }
        }
    }
}
~~~

**Quan trọng:** Đoạn này chỉ minh họa API đồng bộ, không cam kết mọi DBMS/driver/RowSet provider có thể cập nhật thành công. Cần thử với provider cụ thể, bảo đảm đủ metadata khóa, quyền ghi và isolation phù hợp. Nếu nghiệp vụ đã quản lý transaction ngoài, không tùy tiện kết hợp `acceptChanges(conn)` mà chưa xác minh **ai có quyền commit/rollback connection** trong triển khai provider; có thể có tác dụng ngoài dự kiến.

`SyncProviderException` **không có nghĩa cơ chế giải quyết xung đột tự động đúng với nghiệp vụ**. Ứng dụng phải xác định nên lấy bản mới của DBMS, yêu cầu người dùng xem lại, hay hợp nhất trường nào.

### Lựa chọn thường dễ kiểm soát hơn: cập nhật có điều kiện phiên bản

Một cách khác là đọc dữ liệu ngoại tuyến chỉ để hiển thị, rồi khi người dùng lưu thì gửi SQL tường minh:

~~~sql
UPDATE tasks
SET status = ?, version = version + 1
WHERE id = ? AND version = ?;
~~~

Ví dụ Java:

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;

static boolean updateStatusIfUnchanged(
        Connection conn, long id,
        long expectedVersion, String newStatus
) throws SQLException {

    String sql = """
        UPDATE tasks
        SET status = ?, version = version + 1
        WHERE id = ? AND version = ?
        """;

    try (PreparedStatement ps = conn.prepareStatement(sql)) {
        ps.setString(1, newStatus);
        ps.setLong(2, id);
        ps.setLong(3, expectedVersion);

        return ps.executeUpdate() == 1;
    }
}
~~~

Nếu trả về `false`, hàng có thể đã bị xóa hoặc `version` đã thay đổi. Đây là **optimistic locking** theo quy tắc nghiệp vụ: ứng dụng không tự ghi đè dữ liệu mới. Connection owner vẫn phải quản lý commit/rollback theo giao dịch mong muốn.

Khi dùng `CachedRowSet` làm dữ liệu hiển thị, hãy giữ bản `version` đã đọc để gửi lại. Tránh thao tác “cập nhật toàn bộ hàng” từ snapshot cũ vì có thể vô tình ghi đè các cột mà người khác đã sửa.

## 9. Dữ liệu ngoại tuyến không phải snapshot mới nhất

Giả sử lúc 09:00 ứng dụng A nạp `CachedRowSet`:

~~~text
task id=10, status=OPEN, version=3
~~~

Lúc 09:05 ứng dụng B đổi thành:

~~~text
task id=10, status=DONE, version=4
~~~

Lúc 09:10 người dùng A vẫn thấy `OPEN` trong RowSet cũ. Bản sao không có kết nối theo dõi trạng thái DBMS nên **không tự đổi**.

~~~mermaid
sequenceDiagram
    participant A as Ứng dụng A - CachedRowSet
    participant DB as CSDL
    participant B as Ứng dụng B
    A->>DB: SELECT task id=10
    DB-->>A: OPEN, version=3
    Note over A: Ngắt kết nối, giữ bản sao
    B->>DB: UPDATE status=DONE, version=4
    B->>DB: COMMIT
    A->>A: Vẫn thấy OPEN, version=3
    A->>DB: UPDATE WHERE id=10 AND version=3
    DB-->>A: 0 rows affected
    Note over A: Báo xung đột, tải lại/hòa giải
~~~

Các điểm cần phân biệt:

- **Dữ liệu cũ** là vấn đề thường trực của bản sao ngoại tuyến, không phụ thuộc chỉ vào việc transaction lúc nạp là `READ_COMMITTED` hay `REPEATABLE_READ`.
- **Transaction isolation** quyết định tính nhất quán trong giao dịch khi đọc; nó không biến một RowSet đã ngắt kết nối thành bản sao luôn cập nhật.
- **Dữ liệu đã nạp không nhất thiết là snapshot toàn hệ thống.** Nếu query có nhiều bảng, thời điểm đọc và isolation cụ thể ảnh hưởng tính nhất quán.
- **Đồng bộ có xung đột** là vấn đề khác với bộ nhớ. Một tập dữ liệu rất nhỏ vẫn có thể làm mất cập nhật nếu nghiệp vụ ghi đè mù quáng.

Với giao diện cần độ mới, dùng TTL, nút làm mới, invalidation, truy vấn lại theo key hoặc cơ chế subscription chuyên biệt. Không dùng `CachedRowSet` như nguồn dữ liệu “đúng nhất” về trạng thái hiện tại của DBMS.

## 10. Đo chi phí bộ nhớ thực tế

Không nên đánh giá dựa trên cảm giác “chỉ có 10.000 hàng chắc không sao”. Cần xác định **hàng to nhất, số lượng cột, số lượng yêu cầu đồng thời và bản sao dữ liệu**.

### Chỉ số cần đo

| Chỉ số | Ý nghĩa |
| --- | --- |
| Heap used trước/sau nạp | Mức tăng quan sát được của tiến trình; không tự bằng retained size riêng của RowSet |
| Peak heap used trong khi `populate()` | Phát hiện thời điểm driver và RowSet cùng giữ dữ liệu |
| Allocated bytes và GC activity | Phát hiện nhiều bản sao/tạo đối tượng tạm |
| `CachedRowSet` retained heap | Đối tượng nào giữ dữ liệu sau khi nạp xong; xem bằng heap dump/profiler |
| Số hàng × kích thước trung bình và p95/p99 | Không để một vài hàng LOB lớn phá ngân sách |
| Số request/nhiệm vụ đồng thời | Một RowSet 20 MiB × 100 request có thể gây áp lực lớn |
| Thời gian query, populate, duyệt và đóng | Phân biệt chi phí DB/network và chi phí materialize |

### Quy trình thử nghiệm có thể lặp lại

1. Chuẩn bị dữ liệu thử nghiệm với nhiều mức quy mô: 100, 1.000, 10.000, 100.000 hàng; có cả hàng chứa text lớn/nullable.
2. Chạy một baseline chỉ đọc qua `ResultSet` và xử lý từng hàng, không giữ `List`.
3. Chạy cùng query qua `CachedRowSet.populate(...)`, sau đó đóng nguồn và duyệt RowSet.
4. Lặp lại với projection ít cột, gồm/không gồm LOB, và nhiều page size.
5. Dùng Java Flight Recorder (JFR), Java Mission Control hoặc profiler/heap dump phù hợp để xem allocation và retained heap; kết hợp JMX `MemoryMXBean` nếu cần theo dõi heap tổng.
6. Đo ở mức độ đồng thời thực tế và sau thời gian đủ dài để thấy GC/đỉnh heap, không chỉ một lần nạp.
7. Đặt giới hạn số hàng/byte và giám sát từ production; cảnh báo khi heap/GC latency vượt ngân sách.

**Không dùng một phép tính `Runtime.totalMemory() - Runtime.freeMemory()` ở một thời điểm như con số chính xác “mỗi RowSet tốn X byte”.** Nó bao gồm nhiều đối tượng khác, phụ thuộc GC và thời điểm đo. Cũng không cần gọi `System.gc()` liên tục trong request để “đo chính xác”; điều đó có thể làm méo latency và không bảo đảm reclaim ngay.

### Ngân sách bộ nhớ minh họa

Giả sử ứng dụng đặt ngân sách **300 MiB heap** cho tất cả dữ liệu ngoại tuyến đang hoạt động. Sau benchmark, một trang 500 hàng chiếm retained heap bình quân 3 MiB (con số giả định, không phải hằng số của JDBC).

- 20 trang đồng thời: khoảng 60 MiB retained heap.
- 80 trang đồng thời: khoảng 240 MiB; phần còn lại phải dành cho driver, metadata khác, bản sao, request, GC và ứng dụng.
- Nếu một số trang có payload gấp 10 lần, trung bình trở nên không đủ để quyết định giới hạn.

Do đó, chính sách an toàn cần **giới hạn theo worst-case/percentile phù hợp**, không chỉ số trang hoặc số hàng.

## 11. Serialize và chuyển RowSet ra khỏi tiến trình có miễn phí không?

`WebRowSet` có thể ghi dữ liệu thành XML; một số RowSet có thể được serialize theo đặc tính API. Việc lưu hoặc truyền dữ liệu ngoại tuyến có chi phí:

- XML/JSON có thể lớn hơn dữ liệu thô vì tên trường, ký tự escape và cấu trúc lặp.
- Việc tạo một chuỗi XML/JSON duy nhất có thể làm tăng đỉnh heap; khi có thể, ghi ra `OutputStream`/`Writer` phù hợp thay vì nạp hết vào một `String`.
- Dữ liệu trong RowSet có thể chứa thông tin nhạy cảm. **Tách kết nối không làm dữ liệu tự mã hóa hoặc tự ẩn danh.**
- Nếu serialize dữ liệu để lưu cache hoặc truyền giữa tiến trình, cần kiểm soát quyền truy cập, mã hóa khi lưu/truyền nếu cần, thời hạn lưu và chính sách xóa.
- Đầu vào XML/serialized object từ bên ngoài cần được coi là không đáng tin; dùng cơ chế parse an toàn và giới hạn kích thước, tránh deserialization không kiểm soát.
- Một bản sao RowSet được truyền qua mạng vẫn là dữ liệu tại **thời điểm nạp**, không tự được đồng bộ với DBMS nguồn.

Trong hệ thống cần trao đổi lượng dữ liệu lớn, thường nên chọn **DTO/phân trang hoặc định dạng truyền theo luồng** thay vì gửi toàn bộ `CachedRowSet` với các trạng thái nội bộ.

## 12. Các lựa chọn thay thế theo nhu cầu

| Nhu cầu | Giải pháp thường phù hợp | Đánh đổi cần chấp nhận |
| --- | --- | --- |
| Lấy 20–500 hàng cho một màn hình, cho phép quay lại | `CachedRowSet` có giới hạn hoặc DTO page | RAM cho mỗi trang, dữ liệu có thể cũ |
| Xuất hàng triệu hàng ra CSV | `ResultSet` forward-only, fetch theo đợt/streaming | Connection có thể mở lâu; driver có thể buffer |
| API phân trang cho người dùng | Query pagination với `LIMIT`/`FETCH FIRST` hoặc keyset tùy DBMS | Dữ liệu thay đổi giữa các trang nếu không có snapshot |
| Tra cứu một bản ghi rồi sửa sau nhiều phút | DTO nhỏ + `version` + SQL optimistic locking | Cần xử lý xung đột |
| Dữ liệu lớn hơn RAM | Phân mảnh, streaming, file tạm/định dạng lưu trữ phù hợp | Cần quản lý I/O và checkpoint |
| Phân tích tổng hợp trên tập lớn | `GROUP BY`/`SUM`/`COUNT` tại DBMS, trả kết quả nhỏ | SQL và index cần được tối ưu |
| Lọc một tập nhỏ đã tải | `FilteredRowSet` hoặc lọc trong Java | Lọc không làm giảm chi phí tải tập ban đầu |
| Ghép dữ liệu từ nhiều bảng | SQL `JOIN`, chọn projection cần dùng | Cần đánh giá kế hoạch thực thi |
| Làm việc ngoại tuyến rồi đồng bộ | `CachedRowSet` + conflict handling hoặc DTO/version | Không có tính nhất quán tức thời |

Không phải “offline” luôn đồng nghĩa “phải dùng CachedRowSet”. Một `List<TaskDto>` được giới hạn về số lượng cũng là dữ liệu tách kết nối. Đổi lại, DTO có thể giúp kiểm soát kiểu, trường được giữ và chính sách serialize rõ ràng hơn; `CachedRowSet` thuận tiện khi cần giao diện cursor/metadata theo JDBC.

## 13. Những ngộ nhận và lỗi thường gặp

| Ngộ nhận | Rủi ro | Cách đúng |
| --- | --- | --- |
| `CachedRowSet` không tốn RAM vì đã đóng connection | Dữ liệu được giữ trong bộ nhớ Java | Đặt giới hạn, đo retained heap |
| Một trang có 100 hàng chắc chắn nhỏ | Một hàng có thể chứa BLOB hàng trăm MB | Giới hạn cả byte/LOB, chỉ lấy cột cần |
| `setPageSize(100)` đảm bảo DB chỉ xử lý đúng 100 hàng | Provider/driver có thể buffer nhiều hơn | Dùng SQL pagination và đo thực tế |
| `setFetchSize(100)` làm driver không buffer | Fetch size là gợi ý | Kiểm tra cấu hình/driver và profiler |
| Gọi `populate()` rồi đóng connection là dữ liệu luôn mới | Bản sao không tự refresh | TTL, truy vấn lại hoặc cơ chế cập nhật |
| `updateRow()` trong CachedRowSet đã ghi vào DB | Chỉ thay đổi dữ liệu ngoại tuyến | Đồng bộ bằng `acceptChanges()` hoặc SQL tường minh |
| `acceptChanges()` luôn ghi thành công mà không xung đột | Có thể có thay đổi từ transaction khác | Xử lý `SyncProviderException` và quyết định hòa giải |
| `CachedRowSet` tự bảo đảm transaction cho nhiều dịch vụ | Chỉ đồng bộ phần dữ liệu RowSet quản lý theo provider | Thiết kế transaction riêng cho nghiệp vụ |
| RowSet có metadata nên không cần primary key | Đồng bộ khó xác định chính xác hàng | Nạp khóa chính, kiểm tra cấu hình provider |
| Đóng connection sớm luôn cải thiện throughput | Có thể chuyển chi phí sang heap/GC và thời gian copy | So sánh latency, heap, peak concurrency |
| Chia thành nhiều RowSet nhỏ nhưng giữ tất cả trong `List` | Tổng bộ nhớ vẫn tăng theo toàn bộ dữ liệu | Xử lý và giải phóng từng trang |
| Serialize RowSet là dữ liệu an toàn để chia sẻ | Có thể lộ thông tin và tốn tài nguyên | Phân quyền, giới hạn dữ liệu, mã hóa khi cần |
| Dùng RowSet cho tất cả export | Khó mở rộng với hàng triệu hàng | Streaming và checkpoint |
| Dùng dữ liệu ngoại tuyến để ghi đè không kiểm tra | Lost update | Dùng version hoặc xung đột RowSet provider |

## 14. Câu hỏi luyện tập

**Tình huống A.** Một dịch vụ nạp 500.000 dòng, mỗi dòng có 2 KiB nội dung vào `CachedRowSet`. Sau đó đóng connection. Bộ nhớ có được giải phóng ngay không?

**Đáp án:** Không. Đóng connection chỉ giải phóng tài nguyên JDBC liên quan; `CachedRowSet` vẫn giữ bản sao các hàng. Payload đã ở quy mô gần 1 GiB trước khi tính overhead, bản sao và metadata. Nên phân trang hoặc streaming.

**Tình huống B.** Một ứng dụng chỉ lấy 50 hàng nhưng mỗi hàng chứa BLOB 30 MiB. Giới hạn `setMaxRows(50)` đã đủ để bảo vệ heap chưa?

**Đáp án:** Chưa. Số hàng nhỏ không đồng nghĩa payload nhỏ; chỉ BLOB đã khoảng 1.500 MiB trước các bản sao. Loại bỏ cột BLOB khỏi danh sách và tải nội dung theo stream khi cần.

**Tình huống C.** `setPageSize(200)` được cấu hình, nhưng profiler vẫn ghi nhận heap tăng rất mạnh. Có chắc driver bị lỗi không?

**Đáp án:** Không. Cơ chế paging của provider và driver có thể vẫn materialize/buffer dữ liệu; cũng có thể ứng dụng giữ các trang đã duyệt. Phải kiểm tra SQL, fetch strategy, đối tượng giữ tham chiếu và chính workload.

**Tình huống D.** Bản ghi `status=OPEN, version=3` được tải ngoại tuyến. Người khác cập nhật thành `DONE, version=4`. Nếu người dùng thứ nhất lưu trạng thái mới bằng `UPDATE ... WHERE id=? AND version=3` thì điều gì xảy ra?

**Đáp án:** Thông thường cập nhật `0` hàng vì version không còn khớp. Ứng dụng phải báo xung đột, tải dữ liệu mới hoặc áp dụng quy tắc hòa giải.

**Tình huống E.** Sau khi gọi `cached.updateString("status", "REVIEWED"); cached.updateRow();`, một `SELECT` từ connection khác vẫn thấy trạng thái cũ. Đây có phải lỗi?

**Đáp án:** Không. Hai lệnh chỉ thay đổi bản sao ngoại tuyến. Muốn ghi DB cần `acceptChanges()` với provider thích hợp hoặc SQL tường minh trong transaction.

**Tình huống F.** Một chương trình tạo CachedRowSet cho mỗi trang, nhưng sau đó thêm tất cả vào `List<CachedRowSet>` cho đến khi kết thúc export. Có giảm RAM so với một RowSet lớn không?

**Đáp án:** Không nhất thiết. Tổng số hàng vẫn được giữ trong bộ nhớ, thậm chí thêm overhead nhiều RowSet. Phải xử lý từng trang và đóng/giải phóng trước khi lấy trang tiếp theo.

**Tình huống G.** Dịch vụ cần CSV chứa 5 triệu hàng. Nên dùng CachedRowSet để có thể đóng connection trước khi ghi file không?

**Đáp án:** Thường không. Nên xem xét ResultSet forward-only, fetch có kiểm soát và ghi CSV streaming, hoặc cơ chế export của DBMS. Đánh giá thời gian connection mở, khả năng driver buffer, transaction và checkpoint.

**Tình huống H.** Một CachedRowSet có 1.000 hàng được nạp lúc 10:00. Lúc 10:30 giao dịch khác đã sửa nhiều hàng. `ResultSet.TYPE_SCROLL_SENSITIVE` có làm CachedRowSet tự nhận mọi thay đổi không?

**Đáp án:** Không. CachedRowSet là bản dữ liệu tách kết nối; không tự theo dõi DB. Sensitivity của ResultSet kết nối không biến bản sao ngoại tuyến thành cursor sống.

**Tình huống I.** `acceptChanges(conn)` ném `SyncProviderException`. Có nên thử lại ngay lập tức cho đến khi thành công?

**Đáp án:** Không. Cần xác định hàng/cột xung đột, làm rõ chính sách hòa giải, tải dữ liệu mới nếu cần và kiểm tra transaction provider; retry mù có thể ghi đè thay đổi hợp lệ.

**Tình huống J.** Đo heap trước và sau `populate()` một lần thấy tăng 10 MiB. Có thể kết luận mỗi lần nạp đều tốn đúng 10 MiB không?

**Đáp án:** Không. Kết quả phụ thuộc GC, các đối tượng khác, kích thước payload, JDK, driver và provider. Cần đo nhiều mức dữ liệu, retained heap, đỉnh heap và mức độ đồng thời thực tế.

## Ghi nhớ

- **`CachedRowSet` đổi thời gian giữ connection lấy chi phí lưu dữ liệu trong Java heap**. Đóng kết nối không giải phóng bản sao đang được ứng dụng giữ.
- **Bộ nhớ phụ thuộc số hàng, kích thước từng cột, đối tượng, metadata, dữ liệu gốc/bản sửa và bản sao tạm**; phải đo peak/retained heap chứ không chỉ đếm hàng.
- **Phân trang tại SQL, chỉ lấy cột cần dùng và giải phóng từng trang** thường hiệu quả hơn việc nạp trọn tập kết quả lớn vào một RowSet.
- **LOB lớn cần chiến lược riêng**: stream dữ liệu qua JDBC hoặc lưu/truy xuất riêng, không dựa vào giới hạn số hàng.
- **Cached data có thể cũ.** `updateRow()` chỉ sửa ngoại tuyến; khi đồng bộ phải xử lý xung đột, transaction và phiên bản dữ liệu.
- **`setPageSize()` và `setFetchSize()` không phải bảo đảm cứng về RAM**. Kiểm thử với driver/DBMS, JFR/profiler và mức tải thật để đặt giới hạn an toàn.
