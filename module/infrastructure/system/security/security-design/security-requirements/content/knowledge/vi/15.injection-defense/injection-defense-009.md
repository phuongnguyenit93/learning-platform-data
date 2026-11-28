# Parameterized query — Đặc tả truy vấn tham số hóa để giữ dữ liệu tách khỏi SQL

## 1. Mục tiêu của yêu cầu bảo mật

Một chức năng tìm kiếm nhận tên khách hàng rồi ghép nó vào SQL. Đội phát triển thêm một bước kiểm tra ký tự, sau đó tạo `PreparedStatement` từ chuỗi đã ghép và cho rằng truy vấn đã an toàn.

Vấn đề nằm ở thời điểm dữ liệu trở thành cú pháp. Nếu giá trị đầu vào đã được nối vào văn bản SQL trước khi chuẩn bị câu lệnh, việc gọi `prepareStatement` sau đó không khôi phục ranh giới đã mất.

**Parameterized query** là cách giữ mẫu truy vấn và giá trị dữ liệu tách biệt: ứng dụng xác định cấu trúc SQL, đặt parameter marker ở vị trí giá trị và truyền dữ liệu qua API binding của driver hoặc framework.

Trong module yêu cầu bảo mật, mục tiêu cần được đặc tả như sau:

> Các giá trị chịu ảnh hưởng từ nguồn không tin cậy phải được truyền vào truy vấn qua cơ chế bind phù hợp. Những lựa chọn làm thay đổi cấu trúc SQL phải được cố định hoặc ánh xạ từ các lựa chọn nghiệp vụ sang tập cấu trúc do ứng dụng sở hữu.

Yêu cầu này áp dụng cho dữ liệu từ request, import, message, dịch vụ khác và dữ liệu đã lưu rồi được dùng lại. Nguồn dữ liệu nằm trong database không tự làm nó trở thành một đoạn SQL đáng tin.

OWASP phân biệt rõ tham số cho dữ liệu với các phần cấu trúc như tên bảng, tên cột và hướng sắp xếp. Tham khảo [OWASP SQL Injection Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/SQL_Injection_Prevention_Cheat_Sheet).

## 2. Ranh giới giữa mẫu SQL và giá trị

### 2.1. Cách ghép chuỗi làm mất ranh giới

```java
// Không an toàn: customerName đã trở thành một phần văn bản SQL.
String sql =
        "SELECT id FROM customers WHERE customer_name = '"
        + customerName
        + "'";

PreparedStatement statement = connection.prepareStatement(sql);
```

Tên lớp `PreparedStatement` không đủ làm bằng chứng. Trong ví dụ, không có parameter marker cho `customerName`; driver nhận một chuỗi SQL đã chứa dữ liệu nối vào.

Thay một phép cộng chuỗi bằng string interpolation hoặc template cũng không thay đổi tính chất nếu kết quả vẫn là văn bản SQL có nhúng input.

### 2.2. Mẫu và dữ liệu đi qua hai đường riêng

```java
String sql =
        "SELECT id FROM customers WHERE customer_name = ?";

try (PreparedStatement statement =
        connection.prepareStatement(sql)) {

    statement.setString(1, customerName);

    try (ResultSet rows = statement.executeQuery()) {
        while (rows.next()) {
            long customerId = rows.getLong("id");
            // Xử lý kết quả theo quyền và nghiệp vụ của ứng dụng.
        }
    }
}
```

Ở đây, mẫu truy vấn giữ nguyên khi `customerName` thay đổi. Driver nhận giá trị qua `setString` thay vì ứng dụng tự thêm dấu nháy và escape.

Nếu tên là `O'Neil`, dấu nháy là dữ liệu trong giá trị, không phải lý do để sửa tên hoặc tạo một nhánh SQL đặc biệt. Một chuỗi có hình thức giống biểu thức SQL cũng phải giữ vai trò dữ liệu tại vị trí tham số.

Cơ chế thực thi chi tiết có thể khác giữa driver và database. Yêu cầu bảo mật cần xác minh API binding, cấu hình và đường thực thi được hỗ trợ, không dựa vào suy đoán rằng mọi driver luôn tạo cùng một loại đối tượng prepared statement phía server.

### 2.3. Parameter marker không nằm trong dấu nháy SQL

```sql
-- Đúng: marker nằm ở vị trí giá trị.
WHERE customer_name = ?

-- Sai mục đích: đây là literal chứa dấu hỏi, không phải giá trị được bind.
WHERE customer_name = '?'
```

Không tự thêm dấu nháy quanh parameter marker để “giúp SQL hiểu là chuỗi”. Kiểu và giá trị được truyền qua setter hoặc API bind tương ứng.

Oracle mô tả cách tạo statement và cung cấp giá trị qua setter trong [Using Prepared Statements](https://docs.oracle.com/javase/tutorial/jdbc/basics/prepared.html).

## 3. Tham số hóa bảo vệ điều gì và không bảo vệ điều gì?

| Vấn đề | Tham số hóa giúp giải quyết? | Kiểm soát bổ sung |
|---|---|---|
| Giá trị chuỗi bị diễn giải thành SQL | Có, khi giá trị được bind đúng và không bị diễn giải lại ở tầng khác | Kiểm tra mọi sink và dynamic SQL downstream |
| Caller chọn cột hoặc hướng sắp xếp tùy ý | Không tự giải quyết | Ánh xạ sang cấu trúc cố định |
| Truy vấn thiếu điều kiện tenant | Không | Phân quyền và phạm vi dữ liệu |
| Tìm kiếm LIKE có wildcard ngoài ý muốn | Không tự thay đổi ngữ nghĩa wildcard | Chính sách pattern và escape wildcard nếu cần |
| Query hợp lệ nhưng rất tốn tài nguyên | Không | Giới hạn đầu vào, phân trang, timeout và thiết kế truy vấn |
| Tài khoản database có quyền quá lớn | Không | Quyền tối thiểu và tách vai trò |
| Log chứa giá trị tham số nhạy cảm | Không | Chính sách logging và cấu hình driver/APM |
| Dữ liệu được đọc rồi ghép vào query khác | Không tự bảo vệ query thứ hai | Bind lại ở lần sử dụng tiếp theo |
| Sai transaction hoặc cập nhật ngoài phạm vi | Không | Điều kiện nghiệp vụ và transaction đúng |

Không nên đưa ra yêu cầu “mọi truy vấn dùng PreparedStatement thì không cần input validation”. Validation vẫn xác định giá trị có đúng kiểu, độ dài, khoảng và ý nghĩa nghiệp vụ hay không.

Ngược lại, một giá trị đã qua validation vẫn nên được bind. Hai kiểm soát giải quyết hai ranh giới khác nhau: dữ liệu được phép và dữ liệu không trở thành cấu trúc SQL.

## 4. Các phần không thể biến thành identifier bằng binding

Trong truy vấn thông thường, parameter marker biểu diễn **giá trị**, không phải tên bảng, tên cột hay một từ khóa SQL.

Ví dụ sau không có nghĩa chọn cột theo tên được bind:

```sql
SELECT ? FROM orders
```

Tùy hệ quản trị và ngữ cảnh, nó có thể là một giá trị hằng được trả về cho mỗi hàng hoặc không hợp lệ với mục đích mong muốn. Tương tự, `ORDER BY ?` không phải cơ chế tổng quát để caller gửi tên cột sắp xếp.

Một API có tham số `sort=createdNewest` nên ánh xạ lựa chọn đó sang cấu trúc do ứng dụng định nghĩa:

```text
createdNewest -> created_at DESC, id ASC
createdOldest -> created_at ASC, id ASC
amountHigh    -> amount DESC, id ASC
```

Ứng dụng chỉ ghép giá trị bên phải trong bảng ánh xạ, không ghép chính chuỗi `sort` mà client gửi.

Điều này cho thấy không phải mọi phép nối chuỗi trong quá trình dựng truy vấn đều đồng nghĩa injection. Nối các fragment cố định do ứng dụng sở hữu có thể là cách triển khai hợp lệ. Cần chứng minh nguồn fragment, không chỉ tìm dấu cộng trong code.

Một regex cho tên cột cũng chưa xác định caller có được chọn cột đó hay không. Một identifier đúng cú pháp có thể trỏ tới dữ liệu ngoài quyền hoặc một biểu thức không thuộc chức năng sản phẩm.

Nếu thật sự cần identifier động trong một hệ thống quản trị đặc thù, phải có mô hình phân quyền, tập identifier và cơ chế quoting theo database riêng. Không dùng binding giá trị hoặc escape chuỗi literal để thay cho quoting identifier.

## 5. Xây dựng hợp đồng cho endpoint tìm đơn hàng

Giả sử một endpoint đọc đơn hàng theo tenant, trạng thái và kiểu sắp xếp. Hệ thống minh họa dùng PostgreSQL qua JDBC và schema có `tenant_id` dạng chuỗi UUID, `status` dạng văn bản, `amount` dạng số và `id` dạng số nguyên.

| Thành phần | Nguồn được phép | Cách đưa vào truy vấn |
|---|---|---|
| Tenant | Ngữ cảnh xác thực và phân quyền của server | Bind như một giá trị |
| Status | Enum nghiệp vụ | Bind giá trị được ánh xạ |
| Sort | Một trong các lựa chọn API đã công bố | Fragment SQL cố định trong enum |
| Page size | Số nguyên trong khoảng 1..100 | Bind theo cú pháp PostgreSQL được hỗ trợ |
| Tên bảng, tên cột | Mã ứng dụng | Cố định |
| Điều kiện tenant | Mẫu truy vấn | Luôn có, không phải filter tùy chọn |
| Giá trị lỗi | Mã lỗi của ứng dụng | Không ghép vào SQL hoặc phản chiếu payload thô |

Các ngưỡng và giá trị enum là ví dụ, không phải chuẩn áp dụng cho mọi hệ thống.

Tenant ID không được lấy từ một field request rồi gọi là “authenticated tenant”. Server phải xác định caller thuộc phạm vi nào và có được thực hiện thao tác đó không.

Tương tự, bind một `orderId` hoàn toàn không chứng minh caller được đọc đơn hàng đó. Query vẫn cần những điều kiện phạm vi phù hợp với mô hình quyền.

## 6. Ví dụ Java: bind giá trị, ánh xạ phần cấu trúc

Đoạn mã sau minh họa truy vấn đọc. Connection và transaction do tầng gọi sở hữu; method chỉ đóng statement và result set do mình tạo.

```java
import java.math.BigDecimal;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;
import java.util.UUID;

public final class OrderQueryExample {
    public enum OrderStatus {
        NEW, PAID, CANCELLED;

        public static OrderStatus fromApi(String value) {
            if (value == null) {
                throw new IllegalArgumentException("STATUS_REQUIRED");
            }

            return switch (value) {
                case "new" -> NEW;
                case "paid" -> PAID;
                case "cancelled" -> CANCELLED;
                default -> throw new IllegalArgumentException(
                        "STATUS_NOT_ALLOWED");
            };
        }
    }

    public enum SortOption {
        CREATED_NEWEST("created_at DESC, id ASC"),
        CREATED_OLDEST("created_at ASC, id ASC"),
        AMOUNT_HIGH("amount DESC, id ASC");

        private final String sql;

        SortOption(String sql) {
            this.sql = sql;
        }

        public static SortOption fromApi(String value) {
            if (value == null) {
                throw new IllegalArgumentException("SORT_REQUIRED");
            }

            return switch (value) {
                case "createdNewest" -> CREATED_NEWEST;
                case "createdOldest" -> CREATED_OLDEST;
                case "amountHigh" -> AMOUNT_HIGH;
                default -> throw new IllegalArgumentException(
                        "SORT_NOT_ALLOWED");
            };
        }
    }

    public record OrderSummary(
            long id,
            String status,
            BigDecimal amount) {
    }

    public static List<OrderSummary> list(
            Connection connection,
            UUID authenticatedTenantId,
            OrderStatus status,
            SortOption sort,
            int pageSize) throws SQLException {

        Objects.requireNonNull(connection);
        Objects.requireNonNull(authenticatedTenantId);
        Objects.requireNonNull(status);
        Objects.requireNonNull(sort);

        if (pageSize < 1 || pageSize > 100) {
            throw new IllegalArgumentException("PAGE_SIZE_OUT_OF_RANGE");
        }

        String sql =
                "SELECT id, status, amount FROM orders "
                + "WHERE tenant_id = ? AND status = ? "
                + "ORDER BY " + sort.sql + " LIMIT ?";

        List<OrderSummary> result = new ArrayList<>();

        try (PreparedStatement statement =
                connection.prepareStatement(sql)) {

            // tenant_id của schema minh họa là cột kiểu chuỗi.
            statement.setString(1, authenticatedTenantId.toString());
            statement.setString(2, status.name());
            statement.setInt(3, pageSize);

            try (ResultSet rows = statement.executeQuery()) {
                while (rows.next()) {
                    result.add(new OrderSummary(
                            rows.getLong("id"),
                            rows.getString("status"),
                            rows.getBigDecimal("amount")));
                }
            }
        }

        return List.copyOf(result);
    }
}
```

Cần đọc đúng các giả định:

- `authenticatedTenantId` phải đến từ đường phân quyền tin cậy; tên biến không tự tạo ra sự tin cậy.
- Fragment `sort.sql` chỉ có thể là một trong ba hằng số do enum khai báo.
- Các giá trị tenant, status và page size đều được bind.
- Setter phù hợp với schema minh họa; nếu cột tenant là kiểu UUID native, phải dùng mapping phù hợp với database và driver thực tế.
- Cú pháp `LIMIT ?` được dùng cho ví dụ PostgreSQL, không được giả định dùng nguyên cho mọi database.
- Điều kiện tenant là thành phần bắt buộc của mẫu, không biến mất khi một filter khác rỗng.

Các setter của JDBC cần tương thích với kiểu SQL tại vị trí tham số. Chỉ số tham số bắt đầu từ 1. Xem [Java PreparedStatement API](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/PreparedStatement.html).

Giới hạn số hàng trả về không đồng nghĩa giới hạn toàn bộ chi phí thực thi. Một truy vấn vẫn có thể quét hoặc sắp xếp nhiều dữ liệu trước khi trả kết quả. Timeout, index và ngân sách truy vấn là các yêu cầu bổ sung.

## 7. Các trường hợp dễ làm sai khi áp dụng binding

### 7.1. Danh sách IN không phải một chuỗi CSV

```sql
WHERE id IN (?)
```

Bind `"10,20,30"` vào một marker không có nghĩa truyền ba số. Nó là một giá trị theo kiểu mà driver gửi. Không chuyển sang nối chuỗi CSV để “sửa” vấn đề.

Một lựa chọn là tạo số marker từ **số phần tử đã được giới hạn**, rồi bind từng phần tử:

```java
// ids đã được parse thành List<Long>, không chứa null,
// có 1..100 phần tử; tenantId đến từ ngữ cảnh đã phân quyền.
String markers = String.join(
        ",", java.util.Collections.nCopies(ids.size(), "?"));

String sql =
        "SELECT id FROM orders WHERE tenant_id = ? "
        + "AND id IN (" + markers + ")";

try (PreparedStatement statement =
        connection.prepareStatement(sql)) {

    statement.setString(1, tenantId.toString());

    for (int i = 0; i < ids.size(); i++) {
        statement.setLong(i + 2, ids.get(i));
    }

    // Thực thi và xử lý ResultSet theo hợp đồng method.
}
```

Phần ghép vào SQL chỉ chứa marker do chương trình sinh, không chứa giá trị ID. Cần xử lý danh sách rỗng rõ ràng, chẳng hạn trả kết quả rỗng theo nghiệp vụ; không bỏ toàn bộ điều kiện ID rồi vô tình mở rộng truy vấn.

Một số database hoặc framework hỗ trợ array binding hay collection expansion. Chỉ dùng theo hợp đồng và cấu hình thực tế; không giả định mọi JDBC driver xử lý collection giống nhau.

### 7.2. LIKE: an toàn cú pháp chưa đủ đúng ngữ nghĩa tìm kiếm

Nếu bind `"%"` vào pattern LIKE, giá trị vẫn là dữ liệu, nhưng nó có ngữ nghĩa wildcard. Đây không nhất thiết là SQL injection; có thể là chức năng tìm kiếm quá rộng so với yêu cầu.

Nếu sản phẩm muốn tìm literal, phải định nghĩa cách escape wildcard. Ví dụ PostgreSQL dùng `!` làm escape character được chọn rõ ràng:

```java
static String escapeLikeLiteral(String value) {
    return value
            .replace("!", "!!")
            .replace("%", "!%")
            .replace("_", "!_");
}
```

```java
String sql =
        "SELECT id FROM customers "
        + "WHERE tenant_id = ? "
        + "AND customer_name LIKE ? ESCAPE '!'";

try (PreparedStatement statement =
        connection.prepareStatement(sql)) {

    statement.setString(1, tenantId.toString());
    statement.setString(2, "%" + escapeLikeLiteral(term) + "%");

    // Thực thi theo giới hạn và chính sách tìm kiếm.
}
```

Phép cộng trong giá trị của tham số không làm nó trở thành SQL. Kết quả vẫn được bind. Hàm trên xử lý ngữ nghĩa LIKE, không phải tự escape literal để nối vào SQL.

Các ký hiệu wildcard và cơ chế ESCAPE được mô tả trong [PostgreSQL Pattern Matching](https://www.postgresql.org/docs/current/functions-matching.html). Chính sách tìm literal hay pattern phải được chọn trước khi viết helper.

### 7.3. Null, thiếu filter và chuỗi rỗng là các trường hợp khác nhau

Bind SQL NULL vào phép so sánh `column = ?` không làm nó có cùng nghĩa với `column IS NULL`. Quy tắc null của SQL phải được phản ánh trong thiết kế.

Nếu nghiệp vụ cần lọc hàng có giá trị null, chọn một nhánh mẫu cố định dùng `IS NULL`. Nếu field không được gửi có nghĩa bỏ filter, hãy mô tả riêng. Không để việc chuyển đổi null vô tình loại điều kiện tenant hoặc điều kiện quyền.

Khi bind null, dùng API và kiểu phù hợp với driver, chẳng hạn `setNull` với SQL type đã xác định. Đừng nối từ `NULL` vào SQL bằng một nhánh dựa trên chuỗi tùy ý.

### 7.4. Batch và tái sử dụng statement

Với batch, mọi bộ giá trị phải được bind đúng cho từng phần tử trước khi thêm vào batch. Nếu statement được tái sử dụng mà một tham số không được đặt lại, giá trị cũ có thể dẫn tới thao tác sai nghiệp vụ.

Không chia sẻ một statement mutable giữa những request đồng thời hoặc tenant khác nhau như một tối ưu tùy tiện. Quản lý vòng đời và cache statement phải phù hợp với thư viện và connection pool đang dùng.

Tính đúng về binding cần đi cùng transaction: một batch lỗi được rollback toàn bộ hay báo kết quả từng phần là quyết định nghiệp vụ riêng.

## 8. ORM, query builder và stored procedure

### 8.1. ORM không tự bảo vệ chuỗi query do ứng dụng tự ghép

Một framework có API bind vẫn có thể bị dùng sai:

```text
Sai: tạo JPQL/HQL/SQL bằng cách nối giá trị người dùng vào chuỗi.
Đúng: mẫu do ứng dụng sở hữu và truyền giá trị qua API bind của framework.
```

Query builder cần được đánh giá theo từng API. Một method dành cho raw SQL hoặc raw expression có thể bỏ qua ranh giới mà các method typed thông thường duy trì.

Không kết luận “dùng ORM nên không có injection”. Cần lập danh mục các nhánh raw query, native query, truy vấn báo cáo và filter động.

### 8.2. Stored procedure an toàn ở ngoài chưa đủ an toàn ở trong

Một ứng dụng có thể gọi procedure bằng tham số đúng, nhưng procedure lại nối giá trị đó vào dynamic SQL. Lần diễn giải thứ hai vẫn là một sink cần bảo vệ.

Đặc tả phải bao phủ phần SQL bên trong procedure: dữ liệu dùng binding phù hợp, cấu trúc động có nguồn cố định hoặc mapping được phép. Việc dùng `CallableStatement` ở lớp Java không tự chứng minh thân procedure an toàn.

PostgreSQL phân biệt các giá trị truyền qua `USING` với identifier phải xử lý riêng khi thực thi dynamic SQL. Tham khảo [PostgreSQL — Executing Dynamic Commands](https://www.postgresql.org/docs/current/plpgsql-statements.html#PLPGSQL-STATEMENTS-EXECUTING-DYN).

### 8.3. Dữ liệu đã lưu vẫn phải được bind khi đọc lại

Một tên báo cáo được lưu an toàn bằng INSERT có binding vẫn có thể gây vấn đề nếu job đêm đọc tên đó rồi nối vào một query khác.

An toàn của lần lưu trước không trở thành một thuộc tính vĩnh viễn của chuỗi. Mỗi lần dữ liệu đi qua ranh giới diễn giải SQL đều cần giữ đúng vai trò dữ liệu.

## 9. Bộ yêu cầu bảo mật và bằng chứng

Các mã sau là một bộ minh họa cho dự án. Chúng cần được gắn với repository, procedure, endpoint hoặc job cụ thể.

### PQ-01 — Mọi giá trị động được bind tại sink

Các giá trị dữ liệu chịu ảnh hưởng từ nguồn bên ngoài phải được truyền qua API bind trước khi thực thi truy vấn. Không nối hoặc nội suy giá trị vào văn bản SQL.

**Bằng chứng:** danh mục sink; mẫu query và các lệnh bind; kiểm tra đường đi dữ liệu từ request, import và dữ liệu lưu trước đó.

### PQ-02 — Cấu trúc động chỉ đến từ nguồn ứng dụng sở hữu

Bảng, cột, biểu thức sắp xếp và các fragment cấu trúc phải cố định hoặc được chọn từ mapping hữu hạn của ứng dụng. Field không có trong tập lựa chọn phải bị từ chối.

**Bằng chứng:** enum hoặc mapping; test gửi cấu trúc ngoài tập; query shape quan sát được.

### PQ-03 — Không diễn giải lại dữ liệu ở tầng tiếp theo

Procedure, query builder, helper và job downstream không được biến tham số đã bind thành SQL bằng cách nối chuỗi không được kiểm soát.

**Bằng chứng:** kiểm tra thân procedure và các raw query; test dữ liệu được lưu rồi dùng lại.

### PQ-04 — Binding đúng kiểu và đủ tham số

Mỗi nhánh query phải có số marker, thứ tự, kiểu và giá trị bind phù hợp. Null và danh sách rỗng phải có hành vi được xác định.

**Bằng chứng:** test từng nhánh filter, batch, null, biên số và số lượng phần tử.

### PQ-05 — Phân quyền giữ độc lập với chống injection

Điều kiện phạm vi tenant hoặc quyền tài nguyên phải được áp dụng đúng trên mọi truy vấn liên quan. Binding một ID không được coi là bằng chứng quyền truy cập.

**Bằng chứng:** fixture nhiều tenant; kết quả đọc và tác động ghi đúng phạm vi; điều kiện quyền không biến mất khi filter rỗng.

### PQ-06 — Không fallback sang ghép SQL khi lỗi

Lỗi binding, kiểu dữ liệu hoặc cấu hình driver không được kích hoạt một nhánh thử lại bằng query nối chuỗi. Lỗi phải đi qua cơ chế xử lý đã định nghĩa.

**Bằng chứng:** fault injection với lỗi prepare/bind/execute; không có một câu query raw dự phòng chứa payload.

### PQ-07 — Giới hạn dữ liệu và công việc truy vấn

Đầu vào phải có giới hạn phù hợp về độ dài, số phần tử, khoảng giá trị, số hàng và thời gian hoặc tài nguyên truy vấn. Parameterization không được dùng để bỏ qua các giới hạn này.

**Bằng chứng:** test query hợp lệ nhưng lớn, danh sách ID vượt biên, phân trang và cấu hình giới hạn được triển khai.

### PQ-08 — Bảo vệ dữ liệu tại lớp quan sát

SQL tracing, APM, log driver và log lỗi không được làm lộ secret hoặc dữ liệu nhạy cảm thông qua giá trị tham số hay query được render. Việc bật debug không được phá chính sách này.

**Bằng chứng:** quan sát log và trace với dữ liệu tổng hợp; xác minh cả đường lỗi và cấu hình hỗ trợ.

### PQ-09 — Kiểm tra trên driver và database thực tế

Các tính năng binding và kiểu dữ liệu phải được kiểm chứng trên tổ hợp driver, database và cấu hình triển khai được hỗ trợ. Thay đổi có ảnh hưởng tới query generation hoặc binding phải có kiểm tra tương thích.

**Bằng chứng:** test tích hợp; phiên bản cấu hình; kết quả các ca Unicode, null, collection và truy vấn động.

## 10. Thiết kế kiểm thử chứng minh ranh giới

### 10.1. Kiểm tra mẫu và lời gọi bind

Ở mức repository, có thể dùng test double hoặc cơ chế quan sát có kiểm soát để xác nhận:

- Mẫu SQL không chứa giá trị đầu vào được nội suy.
- Các tham số được bind ở đúng vị trí và kiểu.
- Sort và fragment cấu trúc chỉ đến từ mapping cố định.
- Mọi nhánh đều giữ điều kiện phạm vi bắt buộc.
- Lỗi không mở một đường execute raw khác.

Không chỉ kiểm tra rằng method `prepareStatement` đã được gọi. Ví dụ đầu bài cũng gọi method đó nhưng đã nối dữ liệu vào SQL.

### 10.2. Kiểm thử tích hợp ngữ nghĩa

Dùng database thử nghiệm với dữ liệu giả, tối thiểu có:

1. Hai tenant có dữ liệu khác nhau.
2. Giá trị chứa dấu nháy và Unicode hợp lệ.
3. Giá trị chứa các chuỗi trông giống toán tử hoặc comment SQL.
4. Dữ liệu phục vụ test null và chuỗi rỗng.
5. Giá trị có `%`, `_` và escape character cho tìm kiếm LIKE.
6. Danh sách ID rỗng, một phần tử và ở giới hạn tối đa.

Kết quả mong đợi phải được định nghĩa theo nghiệp vụ. Ví dụ tìm một chuỗi có hình thức giống SQL không được mở rộng thành toàn bộ bảng; nhưng nếu database có bản ghi đúng bằng chuỗi đó và caller có quyền, trả về bản ghi ấy vẫn là hành vi đúng.

Không dùng quy tắc “mọi chuỗi có dấu nháy đều phải bị từ chối”. Điều đó làm sai dữ liệu hợp lệ mà không chứng minh được binding.

### 10.3. Kiểm tra tác động, không chỉ response

Với INSERT, UPDATE hoặc DELETE, cần xác minh dữ liệu thực sự thay đổi trong phạm vi được phép và transaction có hành vi đúng. Response lỗi không đủ nếu hệ thống đã cập nhật trước đó.

Với truy vấn đọc, xác minh tập hàng và cột trả về, không chỉ mã HTTP. Một query không có injection vẫn có thể trả dữ liệu tenant khác do thiếu điều kiện quyền.

### 10.4. Phân biệt query hiển thị với cơ chế thực thi

Một số công cụ tracing hiển thị SQL đã render giá trị để dễ đọc. Hình thức hiển thị đó không tự chứng minh ứng dụng ghép chuỗi hoặc không dùng binding.

Ngược lại, một log chỉ in template có dấu hỏi cũng không chứng minh giá trị thật được bind đúng. Bằng chứng phải đến từ code path, lời gọi driver hoặc quan sát phù hợp, kết hợp với test tích hợp.

Không bật ghi tham số nhạy cảm trên production chỉ để thu bằng chứng. Dữ liệu giả và phạm vi thử nghiệm có kiểm soát thường đủ cho mục đích kiểm chứng.

## 11. Ma trận nghiệm thu minh họa

| Kịch bản | Kết quả mong đợi | Bằng chứng trọng tâm |
|---|---|---|
| Tên `O'Neil` | Được xử lý như dữ liệu theo hợp đồng | Giá trị bind và kết quả đúng |
| Chuỗi trông giống điều kiện SQL | Không làm thay đổi query shape hoặc phạm vi | Mẫu SQL ổn định, dữ liệu trả về đúng |
| Sort ngoài mapping | Từ chối trước execute | Không có raw ORDER BY từ caller |
| UUID tenant của người khác | Không mở rộng quyền | Ngữ cảnh server và fixture nhiều tenant |
| IN có nhiều ID | Một bind cho mỗi phần tử hoặc API collection phù hợp | Số marker và thứ tự bind |
| IN rỗng | Hành vi được chốt, không tự bỏ filter | Kết quả rỗng hoặc lỗi theo hợp đồng |
| LIKE chứa `%` hoặc `_` | Đúng ngữ nghĩa literal/pattern đã chọn | Không nhầm SQL safety với search semantics |
| Null hoặc field thiếu | Đúng nhánh query được định nghĩa | Không mất điều kiện quyền |
| Dữ liệu lưu rồi dùng lại | Vẫn bind ở sink sau | Không có second-order query nối chuỗi |
| Procedure có dynamic SQL | Giá trị không trở thành cú pháp bên trong | Kiểm tra procedure và test tích hợp |
| Lỗi driver hoặc bind | Không có fallback raw query | Quan sát đường lỗi |
| Debug hoặc trace bật | Không lộ dữ liệu nhạy cảm | Payload log/trace được kiểm tra |
| Query hợp lệ nhưng quá lớn | Bị giới hạn theo ngân sách | Không dựa vào parameterization để kiểm soát tài nguyên |

Một bộ payload cố định không thay thế danh mục sink và nhánh query. Nếu chức năng báo cáo hoặc import dùng một đường truy vấn khác, chúng cần bằng chứng riêng.

## 12. Những nhầm lẫn thường gặp khi viết yêu cầu

| Cách viết chưa đủ | Điểm còn thiếu | Cách đặc tả rõ hơn |
|---|---|---|
| “Dùng PreparedStatement” | Query có thể đã chứa input nối vào | Tách mẫu khỏi giá trị và chỉ ra API bind |
| “Input đã escape nên nối được” | Escape phụ thuộc kiểu và dialect, dễ sai ngữ cảnh | Binding cho giá trị, mapping cho cấu trúc |
| “Dùng ? cho tên cột” | Marker không biến thành identifier | Chọn fragment từ mapping cố định |
| “Dùng ORM là an toàn” | Raw query và string query vẫn có thể sai | Bao phủ mọi sink và API raw |
| “Stored procedure đã được gọi bằng parameter” | Thân procedure có thể ghép dynamic SQL | Kiểm tra cả lần diễn giải bên trong |
| “Không có SQL injection nên không cần ACL” | Query vẫn có thể đọc sai tenant | Yêu cầu phạm vi quyền độc lập |
| “% đã được bind nên tìm literal” | Wildcard vẫn có ý nghĩa LIKE | Chốt ngữ nghĩa và escape wildcard khi cần |
| “Prepared query luôn nhanh hơn” | Kế hoạch và hiệu năng phụ thuộc workload | Đo hiệu năng riêng, không suy từ kiểm soát injection |
| “Log template có ? là bằng chứng đủ” | Không chứng minh đường thực thi | Kết hợp code path, binding và tích hợp |
| “Tất cả dữ liệu trong DB đều tin cậy” | Dữ liệu có thể do người dùng tạo trước đó | Bind lại ở mỗi sink |

Tham số hóa là cơ chế an toàn cú pháp quan trọng, nhưng không phải một nhãn có thể gắn cho cả ứng dụng chỉ từ một lớp repository. Yêu cầu nên xác định phạm vi và các ngoại lệ cần xử lý bằng chứng cụ thể.

## 13. Bài tập áp dụng

Một endpoint nhận `customerName`, `sort`, `ids` và `tenantId`. Backend dùng PreparedStatement nhưng đã nối customerName và sort vào SQL. Danh sách IDs được chuyển thành CSV. Job báo cáo gọi stored procedure có dynamic SQL.

Hãy viết một đặc tả thay thế:

1. Xác định field nào là giá trị, field nào là lựa chọn cấu trúc.
2. Chọn nguồn tenant đáng tin và điều kiện quyền cần giữ trong query.
3. Thiết kế binding cho customerName và danh sách IDs.
4. Nêu hành vi với danh sách rỗng, null và giá trị vượt giới hạn.
5. Tạo mapping sort hữu hạn và cách từ chối lựa chọn ngoài tập.
6. Mô tả phần phải kiểm tra bên trong stored procedure.
7. Viết ca kiểm thử cho dữ liệu hợp lệ có dấu nháy và Unicode.
8. Định nghĩa bằng chứng cho second-order injection và lỗi fallback.
9. Xác định dữ liệu nào không được xuất vào SQL trace hoặc log.

Kết quả cần liên kết từng yêu cầu với mẫu truy vấn, vị trí bind và bằng chứng. Không kết thúc ở việc thay một lớp Statement bằng một lớp có tên PreparedStatement.

## 14. Tài liệu tham khảo

- [OWASP SQL Injection Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/SQL_Injection_Prevention_Cheat_Sheet): ranh giới giá trị và cấu trúc SQL.
- [Oracle — Using Prepared Statements](https://docs.oracle.com/javase/tutorial/jdbc/basics/prepared.html): mẫu sử dụng JDBC prepared statement.
- [Java PreparedStatement API](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/PreparedStatement.html): binding và kiểu tham số.
- [PostgreSQL — PREPARE](https://www.postgresql.org/docs/current/sql-prepare.html): tham số và đối tượng prepared statement phía server.
- [PostgreSQL — Pattern Matching](https://www.postgresql.org/docs/current/functions-matching.html): ngữ nghĩa LIKE và escape character.
- [PostgreSQL — Executing Dynamic Commands](https://www.postgresql.org/docs/current/plpgsql-statements.html#PLPGSQL-STATEMENTS-EXECUTING-DYN): dynamic SQL bên trong procedure.

Một yêu cầu truy vấn tham số hóa đạt độ rõ cần thiết khi xác định được phần SQL do ứng dụng sở hữu, dữ liệu được bind và những nơi dữ liệu có thể bị diễn giải lại. Bằng chứng phải cho thấy ranh giới đó được giữ trên các nhánh truy vấn thực tế, đồng thời phạm vi quyền và giới hạn tài nguyên vẫn được thực thi.
