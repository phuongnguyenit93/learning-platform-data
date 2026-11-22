# Xây dựng điều kiện tùy chọn mà không ghép trực tiếp giá trị

Trong **JDBC (Java Database Connectivity)**, nhiều chức năng tìm kiếm cho phép người dùng chọn **một số bộ lọc hoặc không chọn bộ lọc nào**. Ví dụ, trang danh sách đơn hàng có thể lọc theo trạng thái, tổng tiền tối thiểu, ngày tạo và tên khách hàng. Số điều kiện thay đổi theo yêu cầu, nhưng ứng dụng vẫn phải truyền dữ liệu vào SQL an toàn.

Cách thực hiện thường dùng là **tạo động phần cấu trúc SQL từ những đoạn câu lệnh do lập trình viên kiểm soát**, đồng thời đưa **mọi giá trị đầu vào** vào tham số `?` của `PreparedStatement`. Đây là ranh giới quan trọng: ứng dụng có thể lựa chọn thêm hay bớt một điều kiện `WHERE`, nhưng không được đưa trực tiếp giá trị người dùng vào chuỗi SQL.

Bài học thuộc chương **Truy vấn tham số**. Sau khi học, bạn có thể triển khai truy vấn có nhiều điều kiện tùy chọn, giữ thứ tự tham số đồng bộ với SQL, xử lý đúng `null`/chuỗi rỗng/`LIKE`/`IN` và thiết kế phần sắp xếp, phân trang mà không tạo lỗ hổng SQL injection.

## 1. Vấn đề: biểu mẫu tìm kiếm không có bộ lọc cố định

Giả sử cơ sở dữ liệu quan hệ có bảng minh họa:

~~~sql
CREATE TABLE orders (
    id            BIGINT PRIMARY KEY,
    tenant_id     BIGINT NOT NULL,
    customer_name VARCHAR(200) NOT NULL,
    status        VARCHAR(30) NOT NULL,
    total         DECIMAL(12, 2) NOT NULL,
    created_on    DATE NOT NULL
);
~~~

Các yêu cầu có thể khác nhau:

| Đầu vào | SQL mong muốn |
| --- | --- |
| Không chọn bộ lọc tùy chọn | Chỉ lấy các đơn hàng thuộc tenant hiện tại |
| Chọn trạng thái `PAID` | Thêm `AND status = ?` |
| Chọn tổng tối thiểu `100.00` | Thêm `AND total >= ?` |
| Chọn cả trạng thái và ngày bắt đầu | Thêm **hai** điều kiện vào `WHERE` |
| Nhập từ khóa tìm tên khách | Thêm `AND customer_name LIKE ?` với giá trị đã xử lý wildcard |

Điều kiện `tenant_id = ?` là điều kiện **bắt buộc** trong ví dụ. Trong ứng dụng nhiều khách hàng/tenant, giá trị `tenantId` phải được lấy từ ngữ cảnh xác thực, phân quyền đã xác minh; không dựa vào `tenant_id` do client tự gửi.

Một truy vấn có một hay nhiều bộ lọc là những **dạng cấu trúc SQL** khác nhau. Việc có nhiều dạng cấu trúc không làm mất tính an toàn nếu các mảnh SQL chỉ là hằng số được lập trình viên định nghĩa và tất cả **giá trị** đều được bind bằng `PreparedStatement`.

## 2. Cách sai: ghép trực tiếp dữ liệu vào WHERE

Mẫu nguy hiểm:

~~~java
String sql = "SELECT id FROM orders WHERE tenant_id = " + tenantId;

if (status != null) {
    sql += " AND status = '" + status + "'";
}
~~~

Nếu `status` đến từ biểu mẫu, một đầu vào có ký tự nháy hoặc nội dung SQL có thể thay đổi cú pháp và ý nghĩa của truy vấn. Ngoài nguy cơ **SQL injection**, việc tự thêm dấu nháy còn dễ gặp lỗi với ký tự đặc biệt, kiểu số, ngày giờ và `NULL`.

Một cách **chưa đúng** khác là gọi `PreparedStatement` sau khi đã ghép giá trị:

~~~java
// Không an toàn: status đã bị đưa trực tiếp vào cấu trúc SQL.
String sql = "SELECT id FROM orders WHERE status = '" + status + "'";
PreparedStatement statement = connection.prepareStatement(sql);
~~~

`PreparedStatement` chỉ giúp phân biệt dữ liệu và cấu trúc nếu bạn **thực sự sử dụng các marker `?` và setter**:

~~~java
String sql = "SELECT id FROM orders WHERE tenant_id = ? AND status = ?";

try (PreparedStatement statement = connection.prepareStatement(sql)) {
    statement.setLong(1, tenantId);
    statement.setString(2, status);
    // statement.executeQuery() ...
}
~~~

Khi `status` chứa dấu nháy, driver vẫn xử lý nó như **giá trị dữ liệu**. Ứng dụng không cần tự chèn dấu nháy vào giá trị string và không nên tự xây dựng chuỗi SQL đã nội suy để gửi cho DB.

## 3. Quy tắc: động phần cấu trúc, cố định ranh giới giá trị

Khi xây một truy vấn có điều kiện tùy chọn, hãy tuân theo ba quy tắc:

1. **SQL gốc là hằng số đáng tin cậy.** Ví dụ: `SELECT ... FROM orders WHERE tenant_id = ?`.
2. **Chỉ thêm các đoạn SQL hằng số được chọn bởi logic ứng dụng.** Ví dụ: `" AND status = ?"`, `" AND total >= ?"`. Một giá trị boolean do người dùng nhập có thể quyết định *có thêm điều kiện hay không*, nhưng không được trở thành một đoạn SQL tùy ý.
3. **Bind tham số theo thứ tự xuất hiện của `?` từ trái sang phải.** Marker JDBC là tham số vị trí bắt đầu từ `1`; mỗi `?` phải nhận một giá trị tương ứng với kiểu đúng.

~~~text
Đầu vào: status="PAID", minTotal=100, createdFrom=null
             │
             ▼
Bộ tạo SQL chỉ chọn các đoạn cấu trúc đã định nghĩa
             │
             ├─ SQL: SELECT ... WHERE tenant_id = ?
             │          AND status = ?
             │          AND total >= ?
             │
             └─ Tham số:
                     1 → tenantId   (long)
                     2 → "PAID"     (String)
                     3 → 100.00     (BigDecimal)
             │
             ▼
PreparedStatement → Driver → Database
~~~

**Lưu ý:** Không thể thay cả một đoạn SQL bằng một tham số dữ liệu. Các marker `?` dùng cho **giá trị biểu thức**, không thay cho tên cột, tên bảng, từ khóa `AND`, `ASC`, `DESC` hay số lượng phần tử trong `IN (...)`.

## 4. Ví dụ hoàn chỉnh với PreparedStatement

Ví dụ bên dưới sử dụng **Java 17+**, `DataSource` và các `record` để truyền tiêu chí và kết quả. Người dùng có thể để trống từng bộ lọc; code chỉ thêm điều kiện khi giá trị tương ứng có ý nghĩa.

~~~java
import java.math.BigDecimal;
import java.sql.Connection;
import java.sql.Date;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.time.LocalDate;
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;
import javax.sql.DataSource;

public final class OrderSearchRepository {

    public enum Sort {
        NEWEST_FIRST,
        OLDEST_FIRST
    }

    public record Filter(
            String status,
            BigDecimal minTotal,
            LocalDate createdFrom,
            String customerNameContains,
            Sort sort) {
    }

    public record OrderRow(
            long id,
            String status,
            BigDecimal total,
            LocalDate createdOn) {
    }

    private final DataSource dataSource;

    public OrderSearchRepository(DataSource dataSource) {
        this.dataSource = Objects.requireNonNull(dataSource);
    }

    public List<OrderRow> search(long tenantId, Filter filter)
            throws SQLException {

        Objects.requireNonNull(filter, "filter");
        if (tenantId <= 0) {
            throw new IllegalArgumentException("Invalid tenantId");
        }

        boolean hasStatus =
                filter.status() != null && !filter.status().isBlank();

        boolean hasMinTotal = filter.minTotal() != null;
        boolean hasCreatedFrom = filter.createdFrom() != null;

        boolean hasName =
                filter.customerNameContains() != null
                && !filter.customerNameContains().isBlank();

        // Chỉ phần cấu trúc hằng số được ghép vào SQL.
        StringBuilder sql = new StringBuilder(
                "SELECT id, status, total, created_on " +
                "FROM orders WHERE tenant_id = ?");

        if (hasStatus) {
            sql.append(" AND status = ?");
        }
        if (hasMinTotal) {
            sql.append(" AND total >= ?");
        }
        if (hasCreatedFrom) {
            sql.append(" AND created_on >= ?");
        }
        if (hasName) {
            sql.append(" AND customer_name LIKE ? ESCAPE '!'");
        }

        // Chọn giữa hai đoạn ORDER BY đã được định nghĩa sẵn.
        if (filter.sort() == Sort.OLDEST_FIRST) {
            sql.append(" ORDER BY created_on ASC, id ASC");
        } else {
            sql.append(" ORDER BY created_on DESC, id DESC");
        }

        List<OrderRow> result = new ArrayList<>();

        try (Connection connection = dataSource.getConnection();
             PreparedStatement statement =
                     connection.prepareStatement(sql.toString())) {

            // Phải giữ đúng thứ tự các điều kiện khi tạo SQL.
            int index = 1;
            statement.setLong(index++, tenantId);

            if (hasStatus) {
                statement.setString(index++, filter.status().trim());
            }
            if (hasMinTotal) {
                statement.setBigDecimal(index++, filter.minTotal());
            }
            if (hasCreatedFrom) {
                statement.setDate(
                        index++, Date.valueOf(filter.createdFrom()));
            }
            if (hasName) {
                String literalTerm =
                        filter.customerNameContains().trim();
                String pattern =
                        "%" + escapeLike(literalTerm) + "%";
                statement.setString(index++, pattern);
            }

            try (ResultSet rows = statement.executeQuery()) {
                while (rows.next()) {
                    result.add(new OrderRow(
                            rows.getLong("id"),
                            rows.getString("status"),
                            rows.getBigDecimal("total"),
                            rows.getDate("created_on").toLocalDate()));
                }
            }
        }

        return result;
    }

    // '!' là escape character của LIKE trong SQL phía trên.
    private static String escapeLike(String input) {
        return input.replace("!", "!!")
                    .replace("%", "!%")
                    .replace("_", "!_");
    }
}
~~~

*Bảng `orders`, cột `customer_name`, enum `Sort` và record `Filter` là ví dụ. Cú pháp `LIKE ... ESCAPE '!'` thuộc SQL chuẩn nhưng hỗ trợ và khác biệt thực tế cần xác minh với hệ quản trị/driver đang sử dụng. Mã minh họa dùng các giá trị cột `created_on` không null; nếu schema cho phép null, cần kiểm tra trước khi gọi `toLocalDate()`.*

Sử dụng repository:

~~~java
OrderSearchRepository repository =
        new OrderSearchRepository(dataSource);

OrderSearchRepository.Filter filter =
        new OrderSearchRepository.Filter(
                "PAID",                             // status
                new java.math.BigDecimal("100.00"), // minTotal
                null,                               // không lọc ngày
                "An_%",                             // tìm chuỗi chứa An_%
                OrderSearchRepository.Sort.NEWEST_FIRST
        );

// tenantId lấy từ ngữ cảnh xác thực đã được kiểm tra.
List<OrderSearchRepository.OrderRow> orders =
        repository.search(tenantId, filter);
~~~

Với đầu vào trên, câu SQL được tạo có dạng:

~~~sql
SELECT id, status, total, created_on
FROM orders
WHERE tenant_id = ?
  AND status = ?
  AND total >= ?
  AND customer_name LIKE ? ESCAPE '!'
ORDER BY created_on DESC, id DESC
~~~

Các giá trị được bind theo đúng thứ tự:

| Vị trí | Setter | Dữ liệu |
| --- | --- | --- |
| `1` | `setLong(1, ...)` | `tenantId` |
| `2` | `setString(2, ...)` | `"PAID"` |
| `3` | `setBigDecimal(3, ...)` | `100.00` |
| `4` | `setString(4, ...)` | `"%An!_!%%"` |

Ở vị trí 4, `!_` và `!%` đại diện cho hai ký tự `_` và `%` *theo nghĩa đen*, còn ký tự `%` đầu/cuối là wildcard do ứng dụng cố ý thêm để tìm chuỗi **chứa** từ khóa. Người dùng không thể tự thêm wildcard mới qua `customerNameContains` vì code đã escape.

Ví dụ cho thấy **hai đoạn code phải đồng bộ**: thứ tự thêm `AND ... ?` khi tạo SQL và thứ tự gọi `setXxx(index++, ...)` khi bind. Mỗi điều kiện được kiểm tra bằng cùng một biến `has...` để giảm nguy cơ lệch vị trí.

## 5. Chọn cách biểu diễn “không có bộ lọc”

Với một bộ lọc tùy chọn, giá trị **không được cung cấp** và giá trị **SQL NULL** là hai ý nghĩa khác nhau.

Ví dụ, hệ thống tìm kiếm theo trạng thái có thể quy ước:

| Đầu vào từ ứng dụng | Ý nghĩa mong muốn | Cách xử lý |
| --- | --- | --- |
| `status == null` | Không yêu cầu lọc trạng thái | Không thêm `AND status = ?` |
| `status.isBlank()` | Người dùng để trống ô tìm kiếm | Không thêm điều kiện, nếu đây là quy ước UX |
| `status = "PAID"` | Chỉ trả đơn PAID | Thêm `AND status = ?` và bind chuỗi |
| “Trạng thái chưa được gán” (cờ riêng) | Chỉ lấy dòng có `status IS NULL` | Thêm đoạn hằng số `AND status IS NULL` |
| Muốn tìm đúng chuỗi rỗng `""` | Chỉ lấy dòng có chuỗi rỗng | Bind `""`, nếu DB phân biệt được chuỗi rỗng và NULL |

**Không nên đồng nhất tất cả trường hợp.** Ví dụ `status = NULL` trong SQL không phải cách đúng để lọc giá trị null: so sánh bằng `=` với `NULL` cho giá trị logic `UNKNOWN`, nên cần `IS NULL`.

Nếu cần một API phân biệt *không lọc*, *lọc theo NULL* và *lọc theo giá trị*, hãy dùng kiểu tiêu chí rõ ràng, chẳng hạn enum chế độ lọc và giá trị đi kèm:

~~~java
enum NoteFilterMode {
    ANY,       // không thêm điều kiện
    IS_NULL,   // thêm AND note IS NULL
    EQUALS     // thêm AND note = ? và bind giá trị
}
~~~

Đừng để `null` của Java tự động vừa có nghĩa “không lọc”, vừa có nghĩa “tìm SQL NULL” trong cùng một API.

## 6. Điều kiện LIKE: tham số giúp chống injection, nhưng không tự escape wildcard

Khi người dùng tìm tên khách hàng chứa từ khóa, cú pháp phổ biến là:

~~~sql
AND customer_name LIKE ?
~~~

Giá trị bind có thể là `"%An%"` để tìm chuỗi chứa `An`. `PreparedStatement` giúp dữ liệu không phá vỡ cú pháp SQL, nhưng **`%` và `_` trong giá trị LIKE vẫn có ý nghĩa wildcard theo SQL**. Nếu yêu cầu nghiệp vụ là tìm chuỗi nguyên văn, phải escape wildcard theo cú pháp của DB.

Ví dụ với ký tự escape `!`:

~~~java
private static String escapeLike(String value) {
    return value.replace("!", "!!")
                .replace("%", "!%")
                .replace("_", "!_");
}

String sql = "SELECT id FROM orders " +
             "WHERE customer_name LIKE ? ESCAPE '!'";

try (PreparedStatement statement = connection.prepareStatement(sql)) {
    String userText = "Nguyen_50%";
    statement.setString(1, "%" + escapeLike(userText) + "%");

    try (ResultSet rows = statement.executeQuery()) {
        // Đọc các dòng có tên chứa nguyên văn "Nguyen_50%".
    }
}
~~~

**Phân biệt hai mục tiêu:**

- Muốn người dùng **có quyền nhập wildcard** như một ngôn ngữ tìm kiếm: chỉ cần bind giá trị an toàn rồi xác định rõ quy ước wildcard được hỗ trợ.
- Muốn người dùng tìm **ký tự nguyên văn**: escape wildcard và escape chính ký tự escape như ví dụ.

`LIKE` thường phụ thuộc collation, quy tắc phân biệt chữ hoa/thường, dấu tiếng Việt và Unicode ở DB. Cũng cần quan sát hiệu năng: mẫu tìm kiếm bắt đầu bằng `%` có thể không tận dụng chỉ mục B-tree thông thường như kiểu tiền tố. Nếu tìm kiếm văn bản lớn, cân nhắc chỉ mục hoặc công cụ tìm kiếm phù hợp.

## 7. Danh sách tùy chọn với IN: một dấu hỏi cho mỗi giá trị

Câu SQL:

~~~sql
WHERE status IN (?, ?, ?)
~~~

có **ba marker tham số**, mỗi marker nhận **một giá trị**. Không thể viết `WHERE status IN (?)` rồi bind chuỗi `"PAID,SHIPPED"` và mong JDBC tự hiểu thành hai phần tử; đó chỉ là **một** giá trị chuỗi.

Khi số phần tử do người dùng chọn thay đổi, hãy tạo động **số lượng marker**, không ghép giá trị của danh sách:

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import javax.sql.DataSource;

public static List<Long> findIdsByStatuses(
        DataSource dataSource, long tenantId, List<String> statuses)
        throws SQLException {

    // Quy ước của API này: [] nghĩa là không chọn trạng thái nào,
    // tức không có dòng nào phù hợp.
    if (statuses == null || statuses.isEmpty()) {
        return List.of();
    }

    for (String status : statuses) {
        if (status == null || status.isBlank()) {
            throw new IllegalArgumentException("Invalid status");
        }
    }

    String placeholders =
            String.join(", ", Collections.nCopies(statuses.size(), "?"));

    String sql = "SELECT id FROM orders " +
                 "WHERE tenant_id = ? AND status IN (" +
                 placeholders + ")";

    List<Long> result = new ArrayList<>();

    try (Connection connection = dataSource.getConnection();
         PreparedStatement statement = connection.prepareStatement(sql)) {

        int index = 1;
        statement.setLong(index++, tenantId);
        for (String status : statuses) {
            statement.setString(index++, status);
        }

        try (ResultSet rows = statement.executeQuery()) {
            while (rows.next()) {
                result.add(rows.getLong(1));
            }
        }
    }

    return result;
}
~~~

Ở đây, `Collections.nCopies(statuses.size(), "?")` chỉ tạo các marker do chương trình kiểm soát; **không nối bất cứ nội dung nào của status vào SQL**.

Với danh sách rỗng, phải chọn ngữ nghĩa rõ ràng. Nếu `[]` có nghĩa “không lọc trạng thái”, hãy **bỏ điều kiện `IN`**. Nếu `[]` có nghĩa “không chọn giá trị nào nên không có bản ghi phù hợp”, hãy trả danh sách rỗng ngay như ví dụ hoặc dùng một mệnh đề luôn sai do code tạo ra. Đừng tự sinh `IN ()`, vì đây không phải cú pháp SQL có thể dùng nhất quán trên mọi DB.

Danh sách rất dài có thể vấp giới hạn số lượng marker của DB/driver và làm câu SQL khó tối ưu. Khi xử lý hàng nghìn giá trị, cân nhắc chia lô, bảng tạm, tham số mảng hoặc phương pháp riêng của DB phù hợp, sau khi đo đạc.

## 8. Sắp xếp động: tên cột và ASC/DESC cần danh sách cho phép

Marker `?` chỉ dành cho **giá trị**, không thay thế được tên cột hoặc từ khóa:

~~~sql
-- Sai ý tưởng: không dùng ? để thay tên cột hoặc ASC/DESC.
ORDER BY ? ?
~~~

Nếu tham số đầu là chuỗi `"created_on"`, DB có thể hiểu là **một hằng chuỗi** trong biểu thức sắp xếp, không phải tên cột. Hãy ánh xạ lựa chọn của người dùng sang **một đoạn SQL hằng số có trong allowlist**:

~~~java
String orderBy;

switch (requestedSort) {
    case "oldest":
        orderBy = "created_on ASC, id ASC";
        break;
    case "total-high":
        orderBy = "total DESC, id DESC";
        break;
    default:
        orderBy = "created_on DESC, id DESC";
}

sql.append(" ORDER BY ").append(orderBy);
~~~

`requestedSort` là tên lựa chọn bên ngoài, nhưng nó **chỉ được dùng để chọn** một đoạn SQL cố định. Không ghép trực tiếp:

~~~java
// Nguy hiểm: đầu vào ngoài có thể biến thành cú pháp SQL.
sql.append(" ORDER BY ").append(requestedSort);
~~~

Tương tự, nếu người dùng được chọn trường để lọc, tên bảng hoặc toán tử, dùng enum/allowlist để ánh xạ sang cấu trúc đã định nghĩa thay vì bind tên cột bằng dấu `?` hoặc chèn nguyên văn.

## 9. Phân trang với tham số: chuẩn hóa giới hạn và thứ tự

Truy vấn tìm kiếm có thể trả hàng triệu dòng. Một cách giới hạn số hàng là phân trang. Với **PostgreSQL, MySQL và một số DB hỗ trợ cú pháp này**, có thể dùng:

~~~sql
SELECT id, status
FROM orders
WHERE tenant_id = ?
ORDER BY created_on DESC, id DESC
LIMIT ? OFFSET ?
~~~

Ví dụ:

~~~java
int requestedSize = 25;
int pageIndex = 2;  // Trang thứ ba nếu đếm trang từ 0.

if (pageIndex < 0) {
    throw new IllegalArgumentException("Invalid pageIndex");
}

int pageSize = Math.min(100, Math.max(1, requestedSize));
int offset = Math.multiplyExact(pageIndex, pageSize);

try (PreparedStatement statement = connection.prepareStatement(sql)) {
    statement.setLong(1, tenantId);
    statement.setInt(2, pageSize);
    statement.setInt(3, offset);
    // executeQuery(), đọc ResultSet và đóng tài nguyên.
}
~~~

Trong ví dụ, `sql` là câu SQL đã được dựng sẵn với ba dấu `?`, và `connection` đang mở. `Math.multiplyExact` giúp phát hiện tràn số khi tính offset; trong ứng dụng thật, nên kiểm soát cả giá trị trang tối đa hoặc chuyển sang phân trang theo cursor/keyset khi dữ liệu lớn.

**Cú pháp phân trang không hoàn toàn di động.** SQL Server, Oracle và các hệ khác có thể dùng `OFFSET ... FETCH`, `TOP` hoặc cú pháp riêng; việc bind vị trí `LIMIT/OFFSET` cũng phụ thuộc driver. Tránh ghép trực tiếp số do người dùng gửi vào SQL chỉ để né các giới hạn đó; hãy chọn cú pháp phù hợp DB và bind tham số nơi được hỗ trợ.

Thứ tự ổn định có khóa phụ `id` giúp hạn chế việc bản ghi có cùng `created_on` bị sắp xếp không xác định. Khi dữ liệu thay đổi giữa các lần phân trang, `OFFSET` vẫn có thể bỏ sót/trùng dòng; đây là vấn đề nhất quán khi phân trang, không được giải quyết chỉ bằng PreparedStatement.

## 10. Phương án WHERE tĩnh với bộ lọc null: khi nào nên cân nhắc?

Ngoài việc thêm/bớt các đoạn SQL, có thể giữ một câu SQL cố định:

~~~sql
SELECT id, status
FROM orders
WHERE tenant_id = ?
  AND (? IS NULL OR status = ?)
  AND (? IS NULL OR total >= ?)
~~~

Ý tưởng: nếu tham số trạng thái vắng mặt, cho phép mọi trạng thái; nếu có, áp dụng phép so sánh. Tuy nhiên, mỗi bộ lọc **cần hai marker** trong ví dụ này và bạn phải bind cả hai.

~~~java
// Chỉ minh họa cách bind: SQL có 5 dấu ?.
statement.setLong(1, tenantId);

if (status == null) {
    statement.setNull(2, java.sql.Types.VARCHAR);
    statement.setNull(3, java.sql.Types.VARCHAR);
} else {
    statement.setString(2, status);
    statement.setString(3, status);
}

if (minTotal == null) {
    statement.setNull(4, java.sql.Types.DECIMAL);
    statement.setNull(5, java.sql.Types.DECIMAL);
} else {
    statement.setBigDecimal(4, minTotal);
    statement.setBigDecimal(5, minTotal);
}
~~~

Cách này có vài giới hạn thực tế:

- Một số driver/DB gặp khó khăn khi suy luận kiểu của marker trong biểu thức `? IS NULL`; cần kiểm tra cách bind kiểu và cú pháp tương thích.
- Các mệnh đề `OR` có thể làm kế hoạch thực thi kém hiệu quả so với các câu SQL chỉ chứa bộ lọc cần thiết, nhất là với cột có chỉ mục và dữ liệu lớn.
- Cần phân biệt rõ “không lọc” với “tìm dòng có giá trị SQL NULL”.

Vì thế, phương án **tạo các điều kiện cần thiết rồi bind tương ứng** thường dễ hiểu và dễ tối ưu cho biểu mẫu có nhiều bộ lọc tùy chọn. Cách `? IS NULL OR ...` vẫn có thể phù hợp khi đã kiểm thử hiệu năng và khả năng tương thích với DB đang dùng.

## 11. Giữ cấu trúc SQL và danh sách tham số đồng bộ

Khi có nhiều điều kiện, sai lầm phổ biến là thêm `AND ... ?` nhưng **quên bind** hoặc bind sai vị trí:

~~~java
// SQL có 3 marker:
String sql = "SELECT id FROM orders " +
             "WHERE tenant_id = ? AND status = ? AND total >= ?";

// Sai: giá trị status lại được bind vào vị trí tenant_id.
// statement.setString(1, status);
~~~

JDBC đánh số tham số từ **1**, theo thứ tự marker xuất hiện trong SQL. Đừng dùng chỉ số 0, và đừng cố dùng một index cố định cho từng loại lọc nếu các điều kiện trước đó có thể bị bỏ qua.

Hai cách quản lý thường gặp:

- **Cùng điều kiện boolean ở cả hai pha**: mã mục 4 dùng `hasStatus`, `hasMinTotal`, `hasCreatedFrom`, `hasName` khi ghép SQL và khi bind, với `int index = 1` và `index++`.
- **Gom cấu trúc điều kiện và hành động bind**: với hệ thống nhiều điều kiện phức tạp, tạo một đối tượng điều kiện bao gồm đoạn SQL cố định và hàm bind tham số có kiểu; sau khi dựng SQL, duyệt cùng danh sách điều kiện để bind. Nếu sử dụng thư viện query builder/ORM có hỗ trợ, để thư viện quản lý marker và vị trí tham số.

`ParameterMetaData` có thể giúp hỏi về tham số ở một số driver, nhưng không nên giả định mọi driver hỗ trợ đầy đủ metadata trước khi thực thi; đọc SQL được xây dựng và kiểm thử các tổ hợp bộ lọc vẫn là biện pháp nền tảng.

Một bộ lọc mới cần được cập nhật **ở cả phần SQL lẫn bind giá trị**, và nên có test cho trường hợp bộ lọc được bật độc lập cùng với trường hợp bật chung với bộ lọc khác.

## 12. Những điểm quan trọng về hiệu năng và tính nhất quán

`PreparedStatement` giúp phân biệt giá trị và cú pháp, đồng thời có thể cho phép driver/DB tái sử dụng kế hoạch thực thi. Tuy nhiên, **mỗi tổ hợp điều kiện tạo ra một cấu trúc SQL khác nhau**, nên không nhất thiết dùng chung một prepared plan. Đó là hành vi bình thường; không nên hy sinh kế hoạch truy vấn chỉ để mọi yêu cầu đều có một chuỗi SQL duy nhất.

Các yếu tố khác cần quan sát:

| Yếu tố | Rủi ro | Cách xử lý |
| --- | --- | --- |
| Nhiều điều kiện `OR` bao quanh bộ lọc không dùng | Có thể khó tối ưu hoặc giảm hiệu quả index | Cân nhắc chỉ thêm điều kiện thực sự cần |
| `LIKE '%...%'` | Dễ phải quét nhiều hàng | Dùng index/công cụ tìm kiếm phù hợp |
| `IN` quá dài | Vượt giới hạn marker, SQL phức tạp | Hạn chế số phần tử, cân nhắc giải pháp DB-specific |
| Không có `ORDER BY` ổn định | Phân trang không nhất quán | Sắp xếp theo các cột có thứ tự xác định |
| Bỏ sót bộ lọc quyền truy cập | Trả dữ liệu không thuộc quyền người dùng | Giữ điều kiện bảo mật bắt buộc ngoài logic tùy chọn |
| Dữ liệu thay đổi giữa hai câu truy vấn | `COUNT(*)` và danh sách trang có thể không khớp | Chọn transaction/isolation hoặc UX phù hợp |

Nếu chức năng tìm kiếm đếm tổng số và lấy một trang dữ liệu bằng hai câu SQL, kết quả có thể lệch khi có giao dịch khác thay đổi dữ liệu giữa hai lần đọc. JDBC bind đúng tham số không tự giải quyết vấn đề này; khi cần snapshot nhất quán, phải thiết kế giao dịch và mức cô lập phù hợp.

## 13. Các lỗi thường gặp

| Lỗi | Hệ quả | Cách sửa |
| --- | --- | --- |
| Ghép `" AND status = '" + userStatus + "'"` | Có thể bị SQL injection hoặc lỗi dấu nháy | Thêm `" AND status = ?"` và bind `setString` |
| Gọi `prepareStatement` sau khi đã nội suy đầu vào | Không được bảo vệ khỏi injection | Giữ giá trị ngoài SQL, dùng marker `?` thật |
| Bind cố định `setString(2, ...)` khi điều kiện trước có thể vắng mặt | Sai vị trí tham số hoặc thiếu marker | Dùng chỉ số `index++` theo thứ tự câu SQL |
| Dùng `column = ?` để tìm `NULL` | Phép so sánh `= NULL` không đúng ý nghĩa | Tạo điều kiện `IS NULL` riêng |
| Bind chuỗi `"A,B"` vào một dấu `?` trong `IN (?)` | DB xử lý thành một chuỗi, không phải danh sách | Tạo đúng số marker và bind từng phần tử |
| Ghép chuỗi `ORDER BY` từ request | Có thể cho phép thay đổi cú pháp ngoài dự kiến | Chọn đoạn `ORDER BY` từ allowlist/enum |
| Tin `LIKE ?` tự coi `%` và `_` là ký tự nguyên văn | Kết quả tìm kiếm rộng hơn mong muốn | Escape wildcard khi nghiệp vụ yêu cầu tìm nguyên văn |
| Tạo `IN ()` cho danh sách rỗng | Lỗi cú pháp hoặc hành vi không di động | Định nghĩa rõ ngữ nghĩa empty-list rồi skip/return empty |
| Bỏ điều kiện tenant vì xem nó là bộ lọc tùy chọn | Rò dữ liệu giữa người dùng/tenant | Luôn giữ predicate phân quyền bắt buộc |
| Trả `ResultSet` khi `Connection` đã đóng | Không thể duyệt kết quả hợp lệ | Ánh xạ dữ liệu trong phạm vi `try-with-resources` |

## 14. Bài tập thực hành

**Bài 1.** Người dùng không nhập trạng thái, nhưng nhập tổng tiền tối thiểu `250.00`. Với repository ở mục 4, SQL có bao nhiêu marker trước phần `ORDER BY`?

**Đáp án:** Hai marker: `tenant_id = ?` và `total >= ?`. Thứ tự bind là `tenantId` (vị trí 1), `minTotal` (vị trí 2).

**Bài 2.** Người dùng nhập từ khóa `50%_OFF` và yêu cầu tìm chuỗi đúng nghĩa đen. Có thể bind `"%50%_OFF%"` mà không escape không?

**Đáp án:** Không, nếu ứng dụng không muốn người dùng điều khiển wildcard. Với escape character `!`, mẫu bind là `"%50!%!_OFF%"`; phải dùng SQL có `ESCAPE '!'` tương ứng.

**Bài 3.** Một filter tìm đơn hàng có `note IS NULL`, một filter khác không xét `note`. Dùng một biến Java `note == null` cho cả hai ý nghĩa có tốt không?

**Đáp án:** Không. Nên có chế độ lọc rõ ràng, chẳng hạn `ANY`, `IS_NULL` và `EQUALS`, rồi tạo đúng điều kiện SQL. `= NULL` không tương đương `IS NULL`.

**Bài 4.** Muốn lọc trạng thái theo danh sách `["PAID", "SHIPPED", "CANCELLED"]`. Cần bao nhiêu marker bên trong `IN`?

**Đáp án:** Ba: `IN (?, ?, ?)`; bind từng phần tử bằng một `setString`. Một chuỗi `"PAID,SHIPPED,CANCELLED"` bind vào một dấu hỏi không thay thế cho danh sách.

**Bài 5.** Client gửi `requestedSort = "created_on; DROP TABLE orders"`. Làm thế nào để tránh chèn nội dung này vào SQL?

**Đáp án:** Không bao giờ ghép thẳng `requestedSort`. Chỉ ánh xạ các lựa chọn được phép sang những đoạn `ORDER BY` hằng số, còn giá trị không nằm trong danh sách thì từ chối hoặc dùng thứ tự mặc định.

**Bài 6.** Vì sao không nên coi `status` là bộ lọc tùy chọn nhưng lại cũng để `tenant_id` tùy chọn?

**Đáp án:** `status` là tiện ích tìm kiếm; `tenant_id` là phạm vi dữ liệu mà ứng dụng phải tuân thủ. Bỏ điều kiện tenant khi trống có thể trả dữ liệu không thuộc quyền truy cập của người gọi.

## 15. Ghi nhớ

Trong JDBC, **`PreparedStatement` chỉ bảo vệ dữ liệu được truyền qua marker tham số**. Với điều kiện tìm kiếm tùy chọn, hãy lắp ghép **những đoạn SQL hằng số** theo tiêu chí đã được kiểm tra, sau đó bind **mọi giá trị đầu vào** theo vị trí `1, 2, 3, ...` tương ứng. Dùng `IS NULL` cho nhu cầu tìm giá trị SQL NULL; xử lý `LIKE` và `IN` theo ngữ nghĩa mong muốn; chọn tên cột và `ORDER BY` qua allowlist; giới hạn phân trang và giữ các predicate phân quyền luôn có hiệu lực.

Mẫu thực hành có thể nhớ là: **xác định tiêu chí → dựng SQL chỉ bằng các mảnh tin cậy → tạo PreparedStatement → bind đúng thứ tự và kiểu → executeQuery → duyệt ResultSet trong try-with-resources**. Cách làm này vừa hạn chế SQL injection, vừa giữ logic lọc rõ ràng và dễ kiểm tra khi số lượng điều kiện tăng.
