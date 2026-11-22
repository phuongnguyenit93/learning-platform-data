# Kiểm soát tên bảng, tên cột và hướng sắp xếp bằng danh sách cho phép

Trong **JDBC**, `PreparedStatement` là công cụ quan trọng để truyền **giá trị dữ liệu** vào SQL một cách an toàn. Ví dụ `WHERE tenant_id = ?` hoặc `WHERE status = ?` cho phép ứng dụng dùng `setLong`, `setString` thay vì ghép dữ liệu đầu vào vào câu SQL. Nhưng có một giới hạn thường bị bỏ qua: **không thể dùng dấu `?` thay cho tên bảng, tên cột, từ khóa `ASC` hoặc `DESC`**.

Đây là vấn đề quen thuộc khi thiết kế API báo cáo, tìm kiếm và phân trang. Client có thể yêu cầu xem dữ liệu `orders` hoặc `invoices`, sắp xếp theo `amount` hoặc `createdAt`, tăng hoặc giảm. Nếu server ghép trực tiếp các chuỗi này vào câu SQL, một input không hợp lệ có thể thay đổi cấu trúc truy vấn, dẫn đến **SQL injection**, truy vấn ngoài ý muốn hoặc lộ dữ liệu không được cấp quyền.

Giải pháp là dùng **danh sách cho phép (allowlist)**: ánh xạ từng lựa chọn nghiệp vụ hợp lệ sang **mảnh SQL cố định do lập trình viên định nghĩa**, từ chối mọi giá trị khác, và tiếp tục bind các **giá trị dữ liệu** bằng `PreparedStatement`. Phương pháp này khác hoàn toàn với việc “lọc vài ký tự nguy hiểm” hoặc bao tên trong dấu nháy rồi hy vọng đầu vào an toàn.

Bài học thuộc chương **Bảo mật truy cập** của module **JDBC**, kết hợp SQL tham số hóa, `DataSource`, `Connection`, `PreparedStatement`, `ResultSet`, phân quyền theo tenant và giới hạn truy vấn quy mô lớn.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

- Phân biệt **giá trị SQL** với **định danh SQL** (bảng, cột, alias) và **từ khóa cú pháp** (như `ASC`, `DESC`).
- Giải thích tại sao `FROM ?`, `ORDER BY ?` và `ORDER BY column ?` không thay thế được việc kiểm soát cấu trúc SQL.
- Thiết kế allowlist cho **tên bảng**, **cột được phép sắp xếp** và **hướng sắp xếp** bằng enum/map ánh xạ cố định.
- Xây dựng repository JDBC có kiểm tra lựa chọn từ API, truy vấn tham số hóa và giới hạn kích thước kết quả.
- Ngăn tình trạng cột hợp lệ ở bảng này nhưng bị dùng sai trong truy vấn bảng khác.
- Phân biệt **cho phép sử dụng một identifier** với **quyền đọc/sửa dữ liệu** trong bảng đó.
- Viết test cho input hợp lệ, input lạ, chuỗi có ý định injection, dữ liệu `NULL`, thứ tự ổn định và giới hạn phân trang.
- Biết khi nào nên bỏ hoàn toàn SQL động để dùng các câu truy vấn cố định dễ kiểm toán hơn.

## 2. Vì sao `PreparedStatement` không giải quyết mọi SQL động?

Câu truy vấn sau là cách dùng tham số đúng:

~~~java
String sql = "SELECT order_id, amount "
           + "FROM orders WHERE status = ?";

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setString(1, requestedStatus);

    try (ResultSet rs = ps.executeQuery()) {
        // Duyệt dữ liệu đã lọc.
    }
}
~~~

Giá trị `requestedStatus` được truyền như **dữ liệu** chứ không phải một phần của cấu trúc SQL. Dù người dùng nhập ký tự nháy đơn hay chuỗi có vẻ giống câu lệnh SQL, nó vẫn phải được xử lý theo ngữ nghĩa của **giá trị tham số**.

Ngược lại, các dạng sau không diễn đạt đúng yêu cầu:

~~~sql
-- Sai: dấu ? không phải tên bảng.
SELECT order_id FROM ? WHERE status = ?;

-- Sai về ý định: ? ở ORDER BY là một giá trị,
-- không trở thành tên cột động.
SELECT order_id, amount FROM orders ORDER BY ?;

-- Sai: dấu ? không đại diện cho từ khóa ASC/DESC.
SELECT order_id, amount FROM orders ORDER BY amount ?;
~~~

Một driver/DBMS có thể từ chối các câu SQL này vì lỗi cú pháp. Với `ORDER BY ?`, có hệ quản trị hiểu nó như một **biểu thức giá trị cố định** hoặc báo lỗi, chứ không tự biến chuỗi `"amount"` thành định danh cột. Vì vậy, việc bind input không thể tự chọn tên bảng hoặc từ khóa SQL.

### Ba loại thành phần cần phân biệt

| Thành phần | Ví dụ | Có thể bind bằng `?`? | Cách xử lý |
| --- | --- | --- | --- |
| **Giá trị** | `tenant_id = 42`, `status = 'PAID'`, `LIMIT 50` nếu dialect hỗ trợ | **Có** | Dùng `setLong`, `setString`, `setInt`... |
| **Định danh** | `orders`, `invoices`, `amount`, `created_at` | **Không** | Chọn từ allowlist ánh xạ sang SQL cố định |
| **Từ khóa/hướng** | `ASC`, `DESC` | **Không** | Chọn từ enum/allowlist đã định nghĩa |
| **Biểu thức SQL** | `LOWER(r.name)`, `r.amount * r.quantity` | Không như một identifier | Chọn nguyên biểu thức cố định do server sở hữu |
| **Cấu trúc khác** | `JOIN`, tên schema, `NULLS FIRST/LAST` | Không | Dùng truy vấn cố định hoặc allowlist riêng có kiểm toán |

Một URL API có thể dùng các tên nghiệp vụ như `createdAt`, nhưng câu SQL thực tế dùng `r.created_at`. **Không bắt buộc tên công khai phải trùng tên cột vật lý**, và việc tách chúng giúp giảm ràng buộc client vào schema.

## 3. Cách SQL injection xuất hiện qua tên bảng/cột

Hãy xét đoạn mã ghép chuỗi:

~~~java
String sql = "SELECT order_id, amount FROM "
           + requestedTable
           + " ORDER BY "
           + requestedSortColumn
           + " "
           + requestedDirection;
~~~

Đoạn này có ba vị trí do client điều khiển trong **cấu trúc SQL**. Ngay cả khi một bộ lọc giá trị được bind đúng, toàn bộ truy vấn vẫn nguy hiểm nếu tên bảng, cột hoặc hướng sắp xếp bị đưa vào SQL mà không có allowlist.

Một số input cần bị từ chối hoàn toàn:

| Trường từ request | Giá trị minh họa | Rủi ro |
| --- | --- | --- |
| `table` | `"users"` khi API chỉ công bố `orders/invoices` | Truy vấn ngoài tập dữ liệu được phép |
| `table` | `"orders JOIN users ON ..."` | Thay đổi cấu trúc `FROM` |
| `sort` | `"amount DESC, id"` | Tiêm thêm biểu thức hoặc thay đổi thứ tự |
| `sort` | `"CASE WHEN ... THEN ... END"` | Buộc database thực hiện biểu thức do client kiểm soát |
| `direction` | `"DESC NULLS LAST"` khi API chỉ hỗ trợ ASC/DESC | Mở rộng cú pháp ngoài hợp đồng |
| `direction` | `"desc; ..."` | Có dấu hiệu cố thay đổi chuỗi lệnh SQL |

Tùy driver, DBMS và việc hỗ trợ nhiều statement, một payload cụ thể có thể bị từ chối hoặc có hậu quả khác. **Không dựa vào việc driver chặn nhiều statement** làm biện pháp bảo vệ chính. Injection không nhất thiết cần lệnh `DROP TABLE`; chỉ cần đổi biểu thức `WHERE`, `JOIN` hoặc `ORDER BY` cũng có thể thay đổi dữ liệu trả về, chi phí truy vấn hoặc suy lộ thông tin.

### Sơ đồ ranh giới tin cậy

~~~mermaid
flowchart TD
    R["Request: table, sort, direction, filter"] --> V["Validate + ánh xạ allowlist"]
    V -->|Không khớp| X["Từ chối yêu cầu / HTTP 400"]
    V -->|Hợp lệ| A["Tên bảng/cột/hướng SQL cố định"]
    A --> Q["Lắp truy vấn từ các fragment cố định"]
    R --> B["Giá trị lọc, limit"]
    B --> P["PreparedStatement.setXxx"]
    Q --> E["Thực thi JDBC"]
    P --> E
    E --> C["Kiểm tra quyền + dữ liệu phù hợp"]
~~~

Sơ đồ biểu diễn hai đường khác nhau: **cấu trúc truy vấn** chỉ lấy từ server-side allowlist, còn **giá trị dữ liệu** đi qua binding. Phần kiểm tra quyền phải được áp dụng trước/trong quá trình truy vấn, không chỉ ở bước lấy kết quả.

## 4. Allowlist đúng nghĩa là gì?

Một allowlist không đơn thuần là một biểu thức chính quy kiểu `[A-Za-z_]+`. Regex có thể loại ký tự đặc biệt nhưng vẫn cho phép tên bảng/cột **hợp lệ về cú pháp song không được phép truy cập**. Ví dụ `password_hash` là tên cột chỉ gồm chữ và dấu gạch dưới, nhưng rõ ràng không nên được client tự ý chọn.

Allowlist nên đáp ứng:

1. **Tập lựa chọn hữu hạn**, được định nghĩa trong code hoặc cấu hình được bảo vệ và kiểm soát phiên bản.
2. **Ánh xạ từ giá trị API sang fragment SQL tin cậy**. Không trả thẳng input request sau khi “làm sạch”.
3. **Fail closed**: giá trị lạ, null hoặc chuỗi không được hỗ trợ bị từ chối hoặc dùng default **được quy định rõ**, không tự rơi về một tên cột bất kỳ.
4. **Phân chia theo ngữ cảnh truy vấn**: tập cột cho phép phụ thuộc bảng, alias, quyền và mục đích sử dụng.
5. **Không tiết lộ thông tin nhạy cảm** qua thông báo lỗi hay log.
6. **Dễ kiểm thử**: có trường hợp hợp lệ, không hợp lệ và kết quả SQL được đối chiếu.

### So sánh các chiến lược

| Cách làm | Đánh giá |
| --- | --- |
| Ghép trực tiếp `request.sort` vào `ORDER BY` | **Không an toàn** |
| Xóa dấu nháy và dấu chấm phẩy khỏi input | Không đủ; còn nhiều dạng biểu thức hợp lệ |
| Dùng regex kiểm tra chỉ gồm chữ/số | Có ích như một rào kiểm tra phụ, nhưng **không phải allowlist quyền** |
| Quote tên do người dùng cung cấp | Chống một số lỗi cú pháp/escaping nhưng không xác nhận cột được phép |
| Dùng enum chứa SQL fragment cố định | **Phù hợp**, dễ kiểm toán |
| Dùng map `"createdAt" → "r.created_at"` do server khai báo | **Phù hợp**, đặc biệt khi tên API và tên SQL khác nhau |
| Dùng các query template cố định cho mỗi trường hợp | **Phù hợp nhất khi ít tổ hợp**, ít SQL động |
| Lấy tên cột qua `DatabaseMetaData` rồi cho client chọn bất kỳ cột nào | **Không đủ**: cột tồn tại không có nghĩa client được dùng nó |

## 5. Thiết kế hợp đồng API trước khi viết SQL

Giả sử endpoint báo cáo nội bộ cho phép:

~~~text
GET /reports?dataset=orders&sort=createdAt&direction=desc&pageSize=50
~~~

Hợp đồng công khai:

| Tham số | Giá trị chấp nhận | SQL fragment tương ứng |
| --- | --- | --- |
| `dataset` | `orders` | `orders` |
| `dataset` | `invoices` | `invoices` |
| `sort` | `id` | `r.id` |
| `sort` | `createdAt` | `r.created_at` |
| `sort` | `amount` | `r.amount` |
| `direction` | `asc` | `ASC` |
| `direction` | `desc` | `DESC` |
| `pageSize` | Số nguyên 1–100 | `LIMIT ?` với `setInt` |
| `tenantId` | Lấy từ ngữ cảnh xác thực, không tin client tự khai | `WHERE r.tenant_id = ?` với `setLong` |

Ví dụ này giả định **cả hai bảng có chung các cột** `id`, `tenant_id`, `created_at` và `amount`, nhằm trình bày rõ cách kiểm soát ba thành phần động. Trong ứng dụng thực, hai bảng có thể khác schema và cần **allowlist cột riêng cho từng bảng** (phần 8).

Một schema minh họa:

~~~sql
CREATE TABLE orders (
    id BIGINT PRIMARY KEY,
    tenant_id BIGINT NOT NULL,
    created_at TIMESTAMP NOT NULL,
    amount DECIMAL(19, 2) NOT NULL
);

CREATE TABLE invoices (
    id BIGINT PRIMARY KEY,
    tenant_id BIGINT NOT NULL,
    created_at TIMESTAMP NOT NULL,
    amount DECIMAL(19, 2) NOT NULL
);
~~~

`TIMESTAMP` trong ví dụ là ngày giờ không kèm thông tin timezone; ứng dụng phải xác định chính sách ngày giờ riêng nếu cần một thời điểm tuyệt đối. Quy tắc sắp xếp ở bài này không phụ thuộc vào việc chuyển `TIMESTAMP` sang `Instant`.

## 6. Ví dụ Java: enum ánh xạ sang SQL cố định

Ví dụ sử dụng Java 8+, `DataSource` và SQL `LIMIT ?` theo dialect của **PostgreSQL/MySQL**. Với DBMS khác phải đổi phần phân trang cho đúng dialect, nhưng **nguyên tắc allowlist giữ nguyên**.

### 6.1. DTO đọc từ database

~~~java
import java.math.BigDecimal;
import java.sql.Timestamp;
import java.time.LocalDateTime;

public final class ReportRow {
    private final long id;
    private final LocalDateTime createdAt;
    private final BigDecimal amount;

    public ReportRow(
            long id, LocalDateTime createdAt, BigDecimal amount) {
        this.id = id;
        this.createdAt = createdAt;
        this.amount = amount;
    }

    public long getId() {
        return id;
    }

    public LocalDateTime getCreatedAt() {
        return createdAt;
    }

    public BigDecimal getAmount() {
        return amount;
    }
}
~~~

DTO không chứa bất kỳ mảnh SQL nào. `LocalDateTime` biểu diễn giá trị ngày giờ của cột `TIMESTAMP` không có múi giờ theo hợp đồng schema này.

### 6.2. Repository với ba allowlist tách biệt

~~~java
import java.math.BigDecimal;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Timestamp;
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;
import javax.sql.DataSource;

public final class SafeReportRepository {
    private final DataSource dataSource;

    public SafeReportRepository(DataSource dataSource) {
        this.dataSource = Objects.requireNonNull(dataSource);
    }

    // Mỗi hằng số chứa SQL identifier do code sở hữu.
    private enum Dataset {
        ORDERS("orders"),
        INVOICES("invoices");

        final String tableSql;

        Dataset(String tableSql) {
            this.tableSql = tableSql;
        }

        static Dataset fromRequest(String input) {
            if ("orders".equals(input)) {
                return ORDERS;
            }
            if ("invoices".equals(input)) {
                return INVOICES;
            }
            throw new IllegalArgumentException(
                    "Dataset không được hỗ trợ");
        }
    }

    private enum SortKey {
        ID("r.id"),
        CREATED_AT("r.created_at"),
        AMOUNT("r.amount");

        final String columnSql;

        SortKey(String columnSql) {
            this.columnSql = columnSql;
        }

        static SortKey fromRequest(String input) {
            if ("id".equals(input)) {
                return ID;
            }
            if ("createdAt".equals(input)) {
                return CREATED_AT;
            }
            if ("amount".equals(input)) {
                return AMOUNT;
            }
            throw new IllegalArgumentException(
                    "Trường sắp xếp không được hỗ trợ");
        }
    }

    private enum SortDirection {
        ASC("ASC"),
        DESC("DESC");

        final String sql;

        SortDirection(String sql) {
            this.sql = sql;
        }

        static SortDirection fromRequest(String input) {
            if ("asc".equals(input)) {
                return ASC;
            }
            if ("desc".equals(input)) {
                return DESC;
            }
            throw new IllegalArgumentException(
                    "Hướng sắp xếp không được hỗ trợ");
        }
    }

    public List<ReportRow> loadPage(
            String datasetInput,
            String sortInput,
            String directionInput,
            long authenticatedTenantId,
            int pageSize) throws SQLException {

        // Validate trước khi tạo hoặc thực thi SQL.
        Dataset dataset = Dataset.fromRequest(datasetInput);
        SortKey key = SortKey.fromRequest(sortInput);
        SortDirection direction =
                SortDirection.fromRequest(directionInput);

        if (pageSize < 1 || pageSize > 100) {
            throw new IllegalArgumentException(
                    "pageSize phải trong khoảng 1..100");
        }
        if (authenticatedTenantId <= 0) {
            throw new IllegalArgumentException(
                    "Ngữ cảnh tenant không hợp lệ");
        }

        // Mọi fragment động đều xuất phát từ enum cố định.
        // Nếu sort theo id, không cần tie-breaker lần hai.
        String ordering = key == SortKey.ID
                ? key.columnSql + " " + direction.sql
                : key.columnSql + " " + direction.sql
                        + ", r.id ASC";

        // Chỉ tên bảng/cột/hướng SQL cố định được ghép.
        // Tenant và giới hạn trang luôn được bind.
        String sql = "SELECT r.id, r.created_at, r.amount "
                   + "FROM " + dataset.tableSql + " r "
                   + "WHERE r.tenant_id = ? "
                   + "ORDER BY " + ordering + " "
                   + "LIMIT ?";

        try (Connection con = dataSource.getConnection();
             PreparedStatement ps = con.prepareStatement(sql)) {

            ps.setLong(1, authenticatedTenantId);
            ps.setInt(2, pageSize);
            ps.setQueryTimeout(10);

            List<ReportRow> rows = new ArrayList<>(pageSize);

            try (ResultSet rs = ps.executeQuery()) {
                while (rs.next()) {
                    long id = rs.getLong("id");
                    if (rs.wasNull()) {
                        throw new SQLException(
                                "id bắt buộc không được NULL");
                    }

                    Timestamp timestamp =
                            rs.getTimestamp("created_at");
                    BigDecimal amount =
                            rs.getBigDecimal("amount");

                    if (timestamp == null || amount == null) {
                        throw new SQLException(
                                "Bản ghi thiếu trường bắt buộc");
                    }

                    rows.add(new ReportRow(
                            id,
                            timestamp.toLocalDateTime(),
                            amount));
                }
            }

            return rows;
        }
    }
}
~~~

**Tại sao cách này kiểm soát được SQL động?**

- Client chỉ gửi chuỗi `datasetInput`, `sortInput` và `directionInput` để **chọn** hằng số. Không có dòng nào nối **nguyên văn** các chuỗi từ client vào SQL.
- `Dataset.ORDERS.tableSql` và `Dataset.INVOICES.tableSql` được tạo từ literal do code khai báo. Không nhận tên bảng tự do như `"admin_users"`.
- `SortKey` ánh xạ tên API `"createdAt"` sang `"r.created_at"`. Client không thể yêu cầu thêm một expression như `"r.created_at DESC, r.amount"`.
- `SortDirection` chỉ có hai từ khóa `ASC` và `DESC`.
- `authenticatedTenantId` là **giá trị**, nên bind bằng `ps.setLong(1, ...)`; `pageSize` cũng được validate rồi bind bằng `setInt`.
- Query luôn chọn **ba cột được code định nghĩa** và trả tối đa 100 dòng trong một trang, tránh nạp tập kết quả lớn chỉ vì client đặt giới hạn quá cao.
- Với các cột có giá trị trùng nhau, `r.id ASC` tạo thứ tự phụ ổn định. Với sort theo ID thì ID duy nhất đã đủ.

### 6.3. Ví dụ kết quả SQL đã được dựng

Gọi:

~~~java
List<ReportRow> page = repository.loadPage(
        "orders",
        "amount",
        "desc",
        authenticatedTenantId,
        50);
~~~

Tại đây `authenticatedTenantId` phải do tầng xác thực/ủy quyền cung cấp, không lấy tùy tiện từ một query parameter có thể sửa. SQL được xây dựng:

~~~sql
SELECT r.id, r.created_at, r.amount
FROM orders r
WHERE r.tenant_id = ?
ORDER BY r.amount DESC, r.id ASC
LIMIT ?;
~~~

Hai giá trị ở `WHERE` và `LIMIT` **vẫn là dấu `?`** cho đến khi driver bind, không được nối thành chuỗi trước khi truyền vào `prepareStatement`.

Nếu client gửi:

~~~text
dataset=orders
sort=amount DESC, id
direction=desc
~~~

`SortKey.fromRequest(...)` sẽ ném `IllegalArgumentException` **trước khi tạo câu SQL**. Không có cơ chế “cố sửa input” rồi giữ lại một fragment chưa được thẩm định.

### 6.4. Những giới hạn cố ý của ví dụ

Ví dụ trên được thiết kế đơn giản để tập trung vào bảo mật identifier:

- `LIMIT ?` là cú pháp PostgreSQL/MySQL; với SQL Server hoặc Oracle cần một query template phân trang phù hợp. Phần SQL cố định đó cũng phải được kiểm toán.
- Hai bảng minh họa có cùng cấu trúc. Với schema thực tế khác nhau, không dùng chung một tập sort column nếu bảng không có các cột tương ứng.
- `LocalDateTime` từ SQL `TIMESTAMP` không tự mang thông tin offset/zone; nghiệp vụ thời gian cần chính sách riêng.
- Danh sách `List<ReportRow>` phù hợp vì **pageSize ≤ 100**. Với export hàng triệu bản ghi, cần JDBC cursor/stream hoặc phân trang tiếp thay vì tăng giới hạn.
- Ví dụ không thực hiện kiểm tra role nào được đọc `orders` và `invoices`. **Đó là nhiệm vụ bắt buộc của tầng ủy quyền** trước khi gọi repository hoặc một lớp policy chuyên biệt ở repository.

## 7. Kiểm soát quyền truy cập khác với allowlist SQL

Một client có thể chọn `dataset=orders` là giá trị **hợp lệ về API**, nhưng người dùng hiện tại vẫn có thể **không có quyền đọc báo cáo đơn hàng**. Allowlist chỉ xác nhận một lựa chọn thuộc tập cho phép dùng trong câu SQL; nó không xác nhận quyền của người yêu cầu.

Hãy phân biệt ba câu hỏi:

1. **Identifier hợp lệ?** `"orders"` có nằm trong tập tên cho phép xây SQL không?
2. **Người dùng được phép thực hiện thao tác này?** Role/permission hiện tại có được đọc báo cáo đơn hàng không?
3. **Dòng nào thuộc quyền sở hữu của người dùng?** `tenant_id`, tổ chức hoặc phạm vi dữ liệu nào cần được lọc?

Một luồng đúng:

~~~mermaid
flowchart TD
    A["Request + identity từ hệ thống xác thực"] --> B["Parse allowlist dataset/sort/direction"]
    B --> C{"Cú pháp hợp lệ?"}
    C -->|Không| D["400 Bad Request"]
    C -->|Có| E["Kiểm tra role/permission"]
    E -->|Không có quyền| F["403 Forbidden"]
    E -->|Có quyền| G["Lấy tenant/scopes từ auth context"]
    G --> H["Bind scope bằng PreparedStatement"]
    H --> I["Thực thi, trả dữ liệu được phép"]
~~~

**Không để client tự chỉ định `tenantId` rồi coi đó là quyền truy cập.** Nếu request chứa `tenantId=123` nhưng người dùng thuộc tenant 456, việc bind `123` bằng `PreparedStatement` chỉ chống injection chứ không ngăn **truy cập dữ liệu của tenant khác** (IDOR/BOLA). Tenant hoặc scope cần được kiểm tra từ identity và chính sách ủy quyền của server.

### Ví dụ mã tổ chức quyền riêng

~~~java
// Pseudocode tầng service, không phải framework cụ thể.
DatasetChoice choice = parseDataset(request.dataset);

if (!permissions.canReadReport(principal, choice)) {
    throw new AccessDeniedException();
}

long tenantId = principal.requireAuthorizedTenantId();

return repository.loadPage(
        choice.apiName(),
        request.sort,
        request.direction,
        tenantId,
        request.pageSize);
~~~

Các kiểu `DatasetChoice`, `permissions` và `principal` là thành phần ứng dụng giả định, không thuộc JDBC. Mục đích là cho thấy **ủy quyền phải được hoàn tất trước khi đọc dữ liệu**, không trộn quyền truy cập vào một hàm “sanitize SQL”.

Ngoài kiểm soát ở ứng dụng, nên áp dụng **least privilege** ở database:

- Tài khoản JDBC chỉ có quyền `SELECT`/`INSERT`/`UPDATE`/`DELETE` thực sự cần cho nghiệp vụ.
- Không cấp quyền đọc bảng chứa mật khẩu, token hoặc dữ liệu nhân sự cho tài khoản báo cáo chỉ cần đơn hàng.
- Nếu DBMS hỗ trợ **row-level security (RLS)**, có thể dùng như lớp bảo vệ bổ sung, nhưng phải kiểm tra thiết lập danh tính tenant an toàn với connection pool.
- Tách account cho tác vụ quản trị/migration khỏi account dùng trong request thông thường.
- Không cho phép client chọn schema hoặc database connection tùy ý.

## 8. Danh sách cột nên phụ thuộc bảng và mục đích

Nếu `orders` và `invoices` có schema khác nhau, một enum `SortKey` dùng chung có thể không đúng. Ví dụ:

~~~text
orders:
  order_id
  created_at
  total_amount

invoices:
  invoice_id
  issued_at
  amount_due
  customer_email
~~~

Có thể muốn API cho phép:

| Dataset | Sort key công khai | SQL fragment cố định |
| --- | --- | --- |
| `orders` | `id` | `r.order_id` |
| `orders` | `createdAt` | `r.created_at` |
| `orders` | `total` | `r.total_amount` |
| `invoices` | `id` | `r.invoice_id` |
| `invoices` | `issuedAt` | `r.issued_at` |
| `invoices` | `amount` | `r.amount_due` |

`customer_email` có thể tồn tại trong bảng nhưng **không xuất hiện trong allowlist sort** vì có lý do bảo mật, hiệu năng hoặc hợp đồng API. Một cột được DBMS công bố qua metadata không tự trở thành lựa chọn client được sử dụng.

Một phương án dễ kiểm soát là chọn allowlist theo dataset:

~~~java
static String orderByColumn(String dataset, String sort) {
    if ("orders".equals(dataset)) {
        switch (sort) {
            case "id":        return "r.order_id";
            case "createdAt": return "r.created_at";
            case "total":     return "r.total_amount";
            default:
                throw new IllegalArgumentException(
                        "Sort key không được hỗ trợ cho orders");
        }
    }

    if ("invoices".equals(dataset)) {
        switch (sort) {
            case "id":       return "r.invoice_id";
            case "issuedAt": return "r.issued_at";
            case "amount":   return "r.amount_due";
            default:
                throw new IllegalArgumentException(
                        "Sort key không được hỗ trợ cho invoices");
        }
    }

    throw new IllegalArgumentException(
            "Dataset không được hỗ trợ");
}
~~~

Các câu `return` đều là **literal cố định**. Không có nhánh:

~~~java
return "r." + sort; // Không được làm với input từ request.
~~~

Với nhiều dataset, có thể tổ chức thông tin trong enum/map immutable chứa **các fragment đã khai báo sẵn**, nhưng vẫn cần kiểm tra **cặp (dataset, sort)** thay vì hợp thức hóa riêng lẻ rồi ghép những tổ hợp không tương thích.

### Cột alias, JOIN và biểu thức tính toán

Trong truy vấn phức tạp:

~~~sql
SELECT o.order_id, c.display_name,
       o.quantity * o.unit_price AS order_total
FROM orders o
JOIN customers c ON c.customer_id = o.customer_id
WHERE o.tenant_id = ?
ORDER BY o.order_id ASC;
~~~

Một allowlist sort có thể ánh xạ:

~~~text
"id"       -> "o.order_id"
"customer" -> "c.display_name"
"total"    -> "o.quantity * o.unit_price"
~~~

Nếu muốn cho phép sắp xếp theo biểu thức `total`, biểu thức này phải được **định nghĩa nguyên vẹn trên server**; không nhận `"quantity * unit_price"` từ client rồi ghép vào SQL. Đồng thời cần kiểm soát chi phí tính toán và nguy cơ dữ liệu nhạy cảm bị suy ra từ thứ tự sắp xếp.

Cần phân biệt **identifier** và **biểu thức** khi dùng quote: ghép dấu quote quanh một biểu thức như `LOWER(name)` không khiến nó thành một biểu thức hợp lệ. Sử dụng fragment cố định rõ ràng dễ kiểm soát hơn.

## 9. Hướng sắp xếp, NULLS FIRST/LAST và collation

Hai giá trị `ASC` và `DESC` là từ khóa SQL, không phải dữ liệu. Cách an toàn là ánh xạ đúng hai lựa chọn:

~~~java
static String sortDirectionSql(String input) {
    if ("asc".equals(input)) {
        return "ASC";
    }
    if ("desc".equals(input)) {
        return "DESC";
    }
    throw new IllegalArgumentException("Direction không hợp lệ");
}
~~~

Tùy yêu cầu sản phẩm, có thể hỗ trợ default:

~~~java
String direction = requestDirection == null
        ? "asc"
        : requestDirection;
~~~

Nhưng đây phải là **quy tắc đã công bố**. Không nên lặng lẽ đổi mọi chuỗi sai thành `ASC`, khiến lỗi input hoặc hành vi bất thường không được phát hiện.

### Sắp xếp theo nhiều cột

Một API có thể yêu cầu sort theo nhiều trường. Không chấp nhận một chuỗi tự do:

~~~text
sort=created_at DESC, amount ASC
~~~

Thay vào đó, dùng danh sách **cấu trúc hóa** của các cặp `(field, direction)`, giới hạn số phần tử và kiểm tra allowlist cho **từng cặp**. Sau đó nối những fragment **đã kiểm soát** bằng dấu phẩy cố định.

Ví dụ pseudo-code:

~~~java
List<String> clauses = new ArrayList<>();

for (SortSpec spec : requestedSorts) {
    SortKey key = SortKey.fromRequest(spec.field());
    SortDirection dir =
            SortDirection.fromRequest(spec.direction());

    clauses.add(key.columnSql + " " + dir.sql);
}

if (clauses.size() > 3) {
    throw new IllegalArgumentException(
            "Chỉ hỗ trợ tối đa 3 khóa sort");
}

String orderBy = String.join(", ", clauses);
~~~

Các lớp `SortSpec` và các enum là thành phần do ứng dụng định nghĩa. Khi áp dụng thật, **kiểm tra giới hạn trước vòng lặp** để tránh xử lý một danh sách input quá lớn; xác định chính sách nếu có khóa trùng, và thêm một khóa duy nhất để giữ thứ tự ổn định khi phân trang.

### `NULLS FIRST`, `NULLS LAST` và `COLLATE`

Các thành phần như `NULLS FIRST`, `NULLS LAST`, tên collation hoặc hướng sắp xếp của biểu thức cũng là **cú pháp SQL**. Nếu thực sự cần cho phép lựa chọn, hãy tạo allowlist **riêng**:

~~~text
nullOrder = first -> "NULLS FIRST"
nullOrder = last  -> "NULLS LAST"
~~~

Nhưng không phải mọi DBMS hỗ trợ cùng cú pháp hoặc cùng thứ tự mặc định của `NULL`. Nếu yêu cầu sản phẩm là kết quả giống nhau trên nhiều database, cần query template riêng hoặc biểu thức cố định cho từng dialect.

Không bao giờ nối tên collation do client tự do cung cấp vào `ORDER BY ... COLLATE ...`. Collation có thể ảnh hưởng hành vi sort/index và tính tương thích; chỉ cho phép một số collation đã được test, nếu cần.

## 10. Sắp xếp ổn định và phân trang an toàn

Một truy vấn có `ORDER BY amount DESC` có thể có nhiều dòng cùng `amount`. Nếu dùng `LIMIT`/`OFFSET` mà không có khóa phá hòa, thứ tự các dòng bằng nhau không được đảm bảo ổn định, dẫn đến trùng hoặc bỏ sót khi client chuyển trang.

Trong ví dụ repository:

~~~sql
ORDER BY r.amount DESC, r.id ASC
LIMIT ?;
~~~

`r.id` là khóa duy nhất, tạo thứ tự **toàn phần** cho tập dữ liệu trả về. Nếu sort theo `r.id`, không cần thêm tie-breaker.

### Limit và offset là giá trị, không phải identifier

Nếu dialect hỗ trợ:

~~~sql
LIMIT ? OFFSET ?;
~~~

thì có thể bind:

~~~java
ps.setInt(1, pageSize);
ps.setLong(2, offset);
~~~

Nhưng phải kiểm tra input:

- `pageSize` có giới hạn min/max (ví dụ 1–100).
- `offset` không âm, tránh tính toán `pageIndex * pageSize` bị overflow.
- Có giới hạn số trang hoặc chiến lược xử lý offset lớn.
- Không coi `LIMIT ?` là “bảo đảm giá rẻ”: một truy vấn sort không có index vẫn có thể thực hiện nhiều công việc trên server.

Đối với tập dữ liệu lớn, **keyset pagination** dựa theo khóa thường hiệu quả hơn offset. Tuy nhiên, nếu sort theo `amount DESC, id ASC` thì điều kiện seek phải phù hợp với **cả hai khóa và cả hai hướng**, không thể dùng đơn giản `WHERE id > ?` như khi sort duy nhất theo ID. Với các cột nullable hoặc nhiều chiều sort, logic seek càng phải được thiết kế/kiểm thử theo DBMS.

### Thứ tự giữa các trang không đồng nghĩa snapshot nhất quán

Ngay cả với thứ tự toàn phần, dữ liệu có thể được thêm/xóa/sửa giữa lúc client lấy trang 1 và trang 2. Nếu yêu cầu là “báo cáo chốt tại một thời điểm”, cần xem xét transaction isolation/snapshot hoặc cơ chế lưu kết quả đã chốt. Allowlist bảo vệ **cấu trúc SQL**, không giải quyết vấn đề nhất quán theo thời gian.

## 11. Một số cách làm tưởng an toàn nhưng vẫn sai

### 11.1. Regex chỉ kiểm tra ký tự

~~~java
if (sort.matches("[A-Za-z_][A-Za-z0-9_]*")) {
    sql += " ORDER BY " + sort;
}
~~~

Regex chặn nhiều dấu hiệu SQL injection nhưng vẫn cho phép bất kỳ tên cột hợp lệ nào, kể cả cột nội bộ. **Không có danh sách chính xác cột được phép**.

### 11.2. Escape identifier nhưng không kiểm tra quyền

~~~java
// Giả sử quoteIdentifier thực hiện escaping đúng dialect.
sql += " ORDER BY " + quoteIdentifier(userColumn);
~~~

Việc quote có thể ngăn chuỗi bị phân tích thành nhiều token SQL, nhưng không biết `userColumn` có phải cột được phép sort hay không. Tên như `salary`, `internal_score` hoặc `password_hash` vẫn là tên hợp lệ về cú pháp.

### 11.3. Dựa vào `DatabaseMetaData.getColumns`

Có thể dùng `DatabaseMetaData` để **khám phá schema** trong công cụ quản trị nội bộ, nhưng không nên cho rằng tất cả tên cột do metadata trả về đều an toàn cho API công khai. Hệ thống database có thể có cột bảo mật, cột không cần thiết hoặc cột tốn tài nguyên khi sắp xếp.

### 11.4. Dùng `ORDER BY ?` rồi mong driver tự đổi thành tên cột

~~~java
PreparedStatement ps = con.prepareStatement(
        "SELECT id, amount FROM orders ORDER BY ?");
ps.setString(1, "amount");
~~~

Dấu `?` là một **giá trị**, không phải fragment SQL `amount`. Câu SQL có thể bị từ chối hoặc sắp xếp theo hằng số, không thực hiện yêu cầu mong muốn.

### 11.5. Map tên API sang SQL bằng cách nối chuỗi

~~~java
String sqlColumn = "r." + request.getSort();
~~~

Có prefix `r.` không làm phần còn lại an toàn. Cần mapping từ **khóa API hợp lệ** sang **toàn bộ fragment cố định**, ví dụ `"createdAt" → "r.created_at"`.

### 11.6. Chỉ kiểm soát sort mà bỏ bảng hoặc schema

~~~java
String safeSort = allowedSort.get(inputSort);
String sql = "SELECT * FROM " + inputTable
           + " ORDER BY " + safeSort;
~~~

Dù `safeSort` đã được kiểm soát, `inputTable` vẫn là điểm SQL động nguy hiểm. Phải xử lý **mọi vị trí do request điều khiển trong cấu trúc SQL**, không chỉ một vị trí.

### 11.7. Nối một danh sách lớn từ request

~~~java
String orderBy = String.join(",", request.getSortFields());
~~~

Không có giới hạn số phần tử, không validate từng cặp field-direction và vẫn đưa giá trị gốc vào SQL. Nếu cần multi-sort, hãy có contract cho số khóa tối đa và chuyển **từng khóa** qua allowlist.

## 12. Validation, xử lý lỗi và logging

Trong ứng dụng web, lỗi chọn dataset/sort/direction không hợp lệ thường được chuyển thành **HTTP 400 Bad Request**. Người dùng thiếu quyền truy cập dataset có thể nhận **403 Forbidden** theo chính sách, không nên trộn hai loại lỗi.

| Loại lỗi | Ví dụ | Xử lý phù hợp |
| --- | --- | --- |
| `dataset` không nằm trong allowlist | `"internal_users"` | Từ chối trước khi tạo SQL |
| `sort` không được hỗ trợ cho dataset | `"salary"` | Trả lỗi input hợp lệ, không suy ra tên cột gần giống |
| `direction` ngoài `asc/desc` | `"desc nulls last"` | Từ chối hoặc dùng API tùy chọn riêng đã xác định |
| Người dùng không có quyền xem `invoices` | Dataset hợp lệ nhưng role không đủ | Kiểm tra ủy quyền, không truy vấn |
| Tenant không được xác thực | Client tự gửi `tenantId` | Không tin tenantId từ client; yêu cầu identity/scopes |
| `SQLException` từ DB | Schema thay đổi, quyền SQL thiếu, kết nối lỗi | Báo lỗi server được kiểm soát, điều tra nội bộ |
| Quá nhiều sort keys/pageSize | `pageSize=1000000` | Giới hạn đầu vào để tránh lạm dụng tài nguyên |

Tránh trả về câu SQL đã dựng hoặc raw `SQLException.getMessage()` cho client. Thông báo lỗi cho client chỉ nên mô tả **tham số không được hỗ trợ** và có thể liệt kê **tập lựa chọn công khai** nếu điều đó phù hợp chính sách API.

Với logging:

- Ghi mã query cố định, chẳng hạn `report.list.v1`.
- Ghi lựa chọn enum đã được xác thực, không ghi nguyên payload chưa tin cậy nếu chứa ký tự điều khiển.
- Ghi trace ID và loại lỗi; không ghi giá trị nhạy cảm của `WHERE` hoặc dữ liệu trả về.
- Không ghi nguyên SQL đã mở rộng tham số nếu driver có thể chèn dữ liệu nhạy cảm vào `PreparedStatement.toString()`.
- Không dùng input sort/dataset tùy ý làm nhãn metric, vì dễ tăng cardinality.

Trong code ví dụ, `IllegalArgumentException` từ allowlist có thể được chuyển thành HTTP 400 ở tầng controller. `SQLException` phải được xử lý ở tầng lỗi database, không biến thành thông báo “sort không hợp lệ” vì che giấu lỗi thực sự.

## 13. Tối thiểu quyền ở database và kiểm soát truy vấn

Allowlist là một lớp bảo vệ ở tầng ứng dụng, không phải thay thế việc cấp quyền đúng ở DBMS.

Ví dụ, tài khoản JDBC dùng cho màn hình báo cáo nên:

1. Chỉ có quyền `SELECT` ở bảng/view cần thiết.
2. Không có quyền `CREATE`/`ALTER`/`DROP` hoặc đọc bảng hệ thống nhạy cảm nếu không cần.
3. Có phạm vi quyền phù hợp schema/tenant và cách tách môi trường.
4. Dùng các view chỉ bộc lộ cột được phép nếu DBMS và kiến trúc hỗ trợ.
5. Không có quyền thực thi thủ tục nguy hiểm không liên quan đến báo cáo.
6. Được cấp tài nguyên/timeout phù hợp để truy vấn sort lớn không ảnh hưởng toàn bộ hệ thống.

Một số hệ quản trị có thể cho cấp quyền ở mức cột hoặc dùng row-level security, nhưng hành vi và cấu hình khác nhau. Khi dùng connection pool cùng một tài khoản DB cho nhiều tenant, phải thiết kế rõ ràng **cách truyền danh tính/tenant đến DB một cách an toàn**, không dựa vào một session variable có nguy cơ bị tái sử dụng sai giữa request.

### Hiệu năng cũng là một phần của bảo mật truy cập

Sắp xếp theo một cột có thể hợp lệ về nghiệp vụ nhưng rất tốn kém nếu không có index, nhất là khi bảng lớn. Do đó, allowlist sort nên cân nhắc **chi phí**, không chỉ tính nhạy cảm của dữ liệu.

Ví dụ:

~~~sql
SELECT r.id, r.created_at, r.amount
FROM orders r
WHERE r.tenant_id = ?
ORDER BY r.created_at DESC, r.id ASC
LIMIT ?;
~~~

Có thể cần index phù hợp với `tenant_id` và thứ tự sort, tùy DBMS. Đừng cho phép sắp xếp theo một expression nặng hoặc một cột văn bản dài chỉ vì nó có trong schema.

Hãy kiểm tra `EXPLAIN`/execution plan của các tổ hợp sort thực sự được phép ở các tập dữ liệu lớn. `LIMIT` có thể giới hạn số dòng **trả về**, nhưng không nhất thiết giới hạn số dòng database phải đọc hoặc sắp xếp trước đó.

## 14. Kiểm thử danh sách cho phép

Kiểm thử ở hai tầng:

- **Unit test**: xác nhận mapping từ API string sang enum/fragment đúng; input lạ bị từ chối trước khi tạo statement.
- **Integration test**: chạy truy vấn qua JDBC thật và xác nhận đúng bảng, đúng cột, đúng hướng, đúng giới hạn tenant, đúng số dòng và behavior theo DBMS.

### Ma trận kiểm thử

| Trường hợp | Đầu vào | Kỳ vọng |
| --- | --- | --- |
| Dataset hợp lệ | `orders`, `invoices` | Tạo query đúng bảng cố định |
| Dataset khác chữ hoa/thường | `Orders` | Từ chối nếu contract phân biệt chữ hoa/thường |
| Dataset có khoảng trắng | `" orders "` | Từ chối hoặc normalize **trước allowlist** theo contract |
| Dataset ngoài danh sách | `users` | Không chạy SQL |
| Dataset có mảnh `JOIN` | `orders JOIN users ...` | Không chạy SQL |
| Cột hợp lệ | `id`, `createdAt`, `amount` | Chọn đúng fragment |
| Cột có dấu cách/biểu thức | `amount DESC, id` | Từ chối |
| Cột không thuộc bảng | `issuedAt` cho `orders` | Từ chối trong mapping theo dataset |
| Direction hợp lệ | `asc`, `desc` | SQL chỉ có `ASC` hoặc `DESC` |
| Direction lạ | `descending` | Từ chối |
| Direction có thêm cú pháp | `desc nulls last` | Từ chối nếu contract không hỗ trợ |
| Giá trị `WHERE` có nháy đơn | Text có ký tự `'` | Vẫn truyền qua `setString`, không đổi SQL |
| Page size bằng 0 / âm | `0`, `-1` | Từ chối |
| Page size quá lớn | `1000000` | Từ chối |
| Không có quyền xem dataset | Dataset hợp lệ, role không đủ | Không trả dữ liệu |
| Tenant khác | User tenant A yêu cầu tenant B | Không truy cập được dòng B |
| Nhiều dòng cùng giá trị sort | `amount` bằng nhau | Có tie-breaker theo ID |
| Schema cột thay đổi | Rename/drop cột | Integration test phát hiện query lỗi, cập nhật mapping có kiểm soát |

### Mẫu test kiểm chứng cơ chế fail closed

~~~java
// Pseudocode assertion: thay bằng JUnit trong dự án.
assertThrows(IllegalArgumentException.class,
        () -> repository.loadPage(
                "users", "id", "asc", 42L, 20));

assertThrows(IllegalArgumentException.class,
        () -> repository.loadPage(
                "orders", "amount DESC, id", "asc", 42L, 20));

assertThrows(IllegalArgumentException.class,
        () -> repository.loadPage(
                "orders", "id", "desc nulls last", 42L, 20));

assertThrows(IllegalArgumentException.class,
        () -> repository.loadPage(
                "orders", "id", "asc", 42L, 5000));
~~~

Ví dụ `assertThrows` là API kiểm thử minh họa; cần import từ JUnit hoặc framework test của dự án. **Kiểm thử injection không nên phụ thuộc vào việc database thực thi payload phá hoại.** Mục tiêu đúng là chứng minh input không nằm trong allowlist bị từ chối **trước khi SQL được tạo/thực thi**, và những input hợp lệ chỉ sinh các fragment cố định.

Để kiểm tra điều này tốt hơn, có thể tách hàm sinh query fragment và unit test mapping thuần, rồi tích hợp JDBC test để kiểm tra dữ liệu và quyền. Không cần log truy vấn chứa payload người dùng trong production.

## 15. Những quyết định thiết kế cần ghi rõ

### Có nên cho phép tên cột trực tiếp từ request?

Có thể, nếu **chính những tên đó** nằm trong allowlist được thiết kế cẩn thận. Tuy nhiên thường nên dùng tên API ổn định (`createdAt`, `total`) ánh xạ sang SQL thực, giúp schema thay đổi mà không buộc client đổi payload.

### Có nên tự động biến chữ hoa thành chữ thường?

Có thể nếu contract quy định, ví dụ `ASC` và `asc` cùng được chấp nhận. Nhưng chuẩn hóa phải diễn ra trước phép kiểm tra allowlist và **không được làm rộng tập giá trị vượt ngoài thiết kế**. Dùng chuẩn hóa locale độc lập (chẳng hạn `Locale.ROOT`) khi cần xử lý chữ hoa/chữ thường; hoặc đơn giản chỉ chấp nhận literal viết thường như ví dụ.

### Có nên cho client chọn tùy ý schema/table?

Đối với API ứng dụng thông thường, **không nên**. Nếu đây là công cụ quản trị có kiểm soát, vẫn cần phân quyền, giới hạn schema, quote identifier theo dialect, ghi audit và bảo vệ tài khoản DB. Kiểm tra tên hợp lệ chỉ là một phần, không thay thế quyền.

### Có nên kiểm tra mọi identifier bằng metadata?

Metadata phù hợp để kiểm tra **schema đã triển khai có đúng với hợp đồng** hoặc dùng trong công cụ quản trị. Nó **không tự quyết định** bảng/cột nào hợp lệ cho người dùng. Allowlist vẫn nên dựa trên thiết kế quyền và API.

### Nếu có nhiều loại báo cáo rất khác nhau?

Có thể tốt hơn khi tạo **nhiều câu SQL cố định**, mỗi loại báo cáo một repository/query template. Khi số tổ hợp hữu hạn và không lớn, SQL tĩnh thường dễ đọc, test và tối ưu hơn một bộ lắp ghép truy vấn tổng quát. Không nên cố xây “SQL builder động” chỉ để giảm vài dòng code.

## 16. Bài tập thực hành

### Bài 1 — Phát hiện SQL injection còn sót

Đoạn code:

~~~java
String sql = "SELECT id FROM " + request.table
           + " WHERE tenant_id = ? ORDER BY ?";

PreparedStatement ps = connection.prepareStatement(sql);
ps.setLong(1, authorizedTenantId);
ps.setString(2, request.sort);
~~~

**Câu hỏi:** Có bao nhiêu vấn đề? Dấu `?` bảo vệ được thành phần nào và không bảo vệ được thành phần nào?

**Gợi ý:** `request.table` được ghép trực tiếp nên nguy hiểm; `ORDER BY ?` không thay cho tên cột, thường là giá trị hoặc lỗi; `authorizedTenantId` mới là một giá trị phù hợp để bind. Cần allowlist bảng/cột.

### Bài 2 — Viết allowlist cho hai bảng khác schema

Cho `orders(order_id, created_at, total_amount)` và `invoices(invoice_id, issued_at, amount_due)`. API `sort=id` phải dùng cột nào với từng dataset? Nếu client gửi `sort=issuedAt` cho `orders`, hệ thống nên làm gì?

**Gợi ý:** Ánh xạ theo cặp dataset/sort; `orders` dùng `order_id`, `invoices` dùng `invoice_id`. `issuedAt` trên `orders` phải bị từ chối nếu không có hợp đồng chuyển đổi tương ứng.

### Bài 3 — Direction và cú pháp mở rộng

Tại sao `setString(1, "DESC")` không thay cho từ khóa `DESC` trong `ORDER BY amount ?`? Nếu API muốn thêm `NULLS LAST`, bạn sẽ kiểm soát nó ra sao?

**Gợi ý:** Dấu `?` biểu diễn giá trị, không phải keyword. Tạo enum/allowlist riêng cho chính sách `NULL`, kiểm tra cú pháp theo DBMS.

### Bài 4 — Ủy quyền theo tenant

Một API dùng `PreparedStatement` và cho phép `dataset=orders`, nhưng lấy `tenant_id` trực tiếp từ query parameter. Vì sao nó vẫn có thể lộ dữ liệu tenant khác? Cần lấy tenant từ đâu?

**Gợi ý:** Parameter binding chỉ chống injection, không chứng minh quyền sở hữu dữ liệu. Tenant/scopes phải đến từ identity và policy phía server.

### Bài 5 — Giới hạn phân trang

Client yêu cầu `pageSize=1000000` và `sort=amount`. Dù `amount` hợp lệ, hai rủi ro hiệu năng nào có thể xuất hiện? Bạn sẽ giới hạn kích thước trang và thiết kế index thế nào?

**Gợi ý:** Trả quá nhiều dòng làm tăng memory/băng thông; sort có thể tốn tài nguyên DB. Giới hạn pageSize, kiểm tra kế hoạch truy vấn và index phù hợp với tenant/sort.

### Bài 6 — Kiểm thử fail closed

Hãy thiết kế test để xác minh các chuỗi `"users"`, `"amount DESC, id"`, `"descending"` và `null` đều không thể được dùng trực tiếp làm SQL fragment. Test ở tầng mapping khác gì test ở database thật?

**Gợi ý:** Unit test kiểm tra từ chối trước SQL; integration test kiểm tra query hợp lệ, schema, thứ tự, lọc tenant và quyền trên driver/DBMS thật.

---

## 17. Checklist trước khi đưa vào production

- [ ] Tôi phân biệt **giá trị tham số** với **identifier/từ khóa SQL**.
- [ ] Không dùng `?` để cố bind tên bảng, tên cột hoặc `ASC/DESC`.
- [ ] Mọi fragment SQL do request tác động đều xuất phát từ **allowlist cố định**.
- [ ] Không nối nguyên văn chuỗi bảng/cột/direction từ request vào SQL.
- [ ] Allowlist cột được giới hạn theo dataset, alias, biểu thức và mục đích sử dụng.
- [ ] Giá trị `WHERE`, tenant, limit/offset được bind qua `PreparedStatement` khi dialect hỗ trợ.
- [ ] Dataset hợp lệ vẫn phải trải qua **ủy quyền role/tenant**.
- [ ] Tài khoản DB chỉ có quyền tối thiểu; dữ liệu nhạy cảm không nằm trong tập truy vấn nếu không cần.
- [ ] Có giới hạn `pageSize` và số sort keys, thứ tự có tie-breaker duy nhất.
- [ ] Đã kiểm tra hiệu năng các tổ hợp sort và index trên dữ liệu lớn.
- [ ] Input lạ bị từ chối theo fail closed; không tự “làm sạch” thành fragment mới.
- [ ] Log và phản hồi lỗi không lộ SQL nội bộ hoặc giá trị nhạy cảm.
- [ ] Đã kiểm thử allowlist, injection input, phân quyền và kết quả trên DBMS/driver thật.

**Nguyên tắc ghi nhớ:** `PreparedStatement` bảo vệ **giá trị dữ liệu**, còn **tên bảng, tên cột và từ khóa như `ASC/DESC`** phải được quyết định từ **danh sách cho phép do server kiểm soát**. Chỉ ghép những fragment SQL cố định, tiếp tục bind mọi giá trị bằng `?` và luôn kiểm tra quyền truy cập độc lập với allowlist. Bảo mật JDBC đúng không phải “làm sạch chuỗi rồi nối SQL”, mà là **không để dữ liệu chưa tin cậy quyết định cấu trúc câu truy vấn**.
