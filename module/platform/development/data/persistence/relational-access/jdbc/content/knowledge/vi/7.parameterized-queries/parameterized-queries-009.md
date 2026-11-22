# Xử lý danh sách IN rỗng và danh sách tham số có độ dài thay đổi

Trong **JDBC (Java Database Connectivity)**, một truy vấn thường cần lọc các bản ghi theo danh sách ID, mã sản phẩm hoặc trạng thái do ứng dụng cung cấp. Ví dụ: “Tìm các khách hàng có ID thuộc tập `[12, 35, 48]`”. SQL thường biểu diễn điều kiện này bằng `IN`:

~~~sql
SELECT id, full_name
FROM customer
WHERE id IN (12, 35, 48);
~~~

Nhưng khi dùng `PreparedStatement`, ứng dụng không nên nối các giá trị đầu vào vào SQL. Thay vào đó, mỗi giá trị cần được **bind** qua một dấu `?`. Vấn đề xuất hiện khi số phần tử thay đổi: ba ID cần ba dấu `?`; một ID cần một dấu `?`; còn **không có ID nào** thì cần quyết định rõ ngữ nghĩa và tránh sinh `IN ()`.

Bài thuộc chương **Truy vấn tham số** này hướng dẫn xây dựng danh sách marker an toàn, xử lý danh sách rỗng cho `SELECT` và lệnh sửa dữ liệu, phân biệt `IN` với `NOT IN`, kiểm soát `NULL` và lựa chọn phương án khi danh sách lớn. Trọng tâm là **ngữ nghĩa nghiệp vụ, cú pháp SQL hợp lệ và ranh giới tham số hóa trong JDBC**.

## 1. `IN` nhận một tập giá trị, còn `?` đại diện một giá trị

Với ba ID, câu SQL tham số hóa là:

~~~sql
SELECT id, full_name
FROM customer
WHERE id IN (?, ?, ?);
~~~

Các lời gọi bind tương ứng:

~~~java
try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setLong(1, 12L);
    ps.setLong(2, 35L);
    ps.setLong(3, 48L);
    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            // Đọc hàng kết quả.
        }
    }
}
~~~

Chỉ số tham số trong JDBC bắt đầu từ **1**. Dấu `?` đầu tiên ứng với `setLong(1, ...)`, dấu thứ hai với `setLong(2, ...)`, v.v.

Một lỗi phổ biến là viết `IN (?)` và gắn cả danh sách dưới dạng một chuỗi:

~~~java
String sql = "SELECT id FROM customer WHERE id IN (?)";
try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setString(1, "12,35,48"); // Không trở thành ba tham số SQL.
}
~~~

Ở đây SQL vẫn chỉ có **một** vị trí tham số. Chuỗi `"12,35,48"` là **một giá trị**, không tự được tách thành `12`, `35` và `48`. Driver/DBMS có thể báo lỗi kiểu dữ liệu, ép kiểu hoặc coi đó là một chuỗi, nhưng không nên kỳ vọng `IN (?)` tự bung danh sách theo JDBC tiêu chuẩn.

Tương tự, truyền trực tiếp `List<Long>` bằng `setObject(1, ids)` **không** phải cơ chế mở rộng `?` thành nhiều marker của JDBC. Nếu DBMS hỗ trợ kiểu SQL array hoặc table-valued parameter, cần dùng **API và cú pháp riêng được hỗ trợ**; nội dung đó khác với mở rộng danh sách `IN` thông thường.

## 2. Tạo đúng số dấu `?` cho danh sách thay đổi

Với danh sách có `n` phần tử và `n > 0`, tạo đúng `n` marker bằng cách lặp lại chuỗi cố định `"?"`, sau đó bind lần lượt từng phần tử.

~~~java
import java.util.Collections;
import java.util.List;

List<Long> ids = List.of(12L, 35L, 48L);

String markers = String.join(", ",
        Collections.nCopies(ids.size(), "?"));
String sql = "SELECT id FROM customer WHERE id IN (" + markers + ")";

System.out.println(markers); // ?, ?, ?
System.out.println(sql);
// SELECT id FROM customer WHERE id IN (?, ?, ?)
~~~

Đoạn trên chỉ **ghép các ký tự SQL cố định** (`?`, dấu phẩy, dấu ngoặc), không chèn giá trị không tin cậy vào câu SQL. Chính các giá trị thật sẽ được truyền vào `PreparedStatement.setXxx(...)`.

Số lượng marker phải khớp số giá trị được bind:

| Danh sách | Marker cần tạo | Các vị trí bind |
| --- | --- | --- |
| `[12]` | `?` | 1 |
| `[12, 35]` | `?, ?` | 1, 2 |
| `[12, 35, 48]` | `?, ?, ?` | 1, 2, 3 |
| `[]` | **Không dựng `IN ()`** | Xử lý riêng theo ý nghĩa nghiệp vụ |

Với `List<Long>` có phần tử null, `setLong` không thể truyền `null` do tham số Java `long` là kiểu nguyên thủy. Bài này áp dụng chính sách **ID phải khác null**; các trường hợp có giá trị SQL `NULL` được phân tích riêng bên dưới.

## 3. Danh sách rỗng cần được xử lý như một quyết định nghiệp vụ

Nhiều hệ quản trị không chấp nhận cú pháp:

~~~sql
-- Tránh sinh câu này:
SELECT id FROM customer WHERE id IN ();
~~~

Không nên phụ thuộc vào việc một DBMS cụ thể cho phép hay diễn giải `IN ()` ra sao. Điều quan trọng hơn là phân biệt **hai ý định khác nhau**:

1. **Người dùng yêu cầu tìm trong một tập ID xác định, nhưng tập đó rỗng.** Không có ID nào thỏa mãn, nên kết quả mong đợi là tập rỗng.
2. **Người dùng không cung cấp bộ lọc ID.** Ứng dụng có thể muốn bỏ qua điều kiện `id IN ...`; đây là hành vi khác và phải được quy định rõ, nhất là với truy vấn nhiều tenant hoặc thao tác `UPDATE`/`DELETE`.

Đừng coi `null` và `[]` đồng nghĩa một cách vô thức. Một hợp đồng API có thể định nghĩa:

| Giá trị bộ lọc | Ý nghĩa được chọn trong ví dụ |
| --- | --- |
| `null` | Không cung cấp bộ lọc; có thể áp dụng logic truy vấn khác hoặc từ chối |
| `[]` | Có cung cấp bộ lọc nhưng không có ID nào; trả kết quả rỗng |
| `[12, 35]` | Chỉ lấy ID 12 và 35 |

Đây là **quy ước của ứng dụng**, không phải quy tắc mặc định của JDBC. Nếu API nghiệp vụ yêu cầu bộ lọc luôn có ít nhất một ID thì có thể từ chối danh sách rỗng bằng lỗi validation; nếu yêu cầu “tìm mọi phần tử thuộc tập rỗng” thì nên trả kết quả rỗng.

### Cách A — Trả tập rỗng ngay trong Java

Với truy vấn chỉ nhằm đọc những ID được chọn, có thể dừng sớm:

~~~java
if (ids.isEmpty()) {
    return List.of();
}
~~~

Ưu điểm: không gọi DB vô ích, không sinh SQL sai cú pháp. Chỉ áp dụng khi trả tập rỗng **đúng hợp đồng** của phương thức. Nếu truy vấn còn tác động khác cần thực hiện, kiểm tra quyền hoặc ghi nhận dấu vết bắt buộc ở DB, không được bỏ qua những trách nhiệm đó một cách tùy tiện.

### Cách B — Dùng biểu thức luôn sai khi cần một SQL hợp lệ

Nếu xây dựng một truy vấn lớn và cần giữ cấu trúc SQL thực thi, có thể thay điều kiện `IN` rỗng bằng biểu thức cố định luôn sai:

~~~sql
SELECT id, full_name
FROM customer
WHERE tenant_id = ?
  AND 1 = 0;
~~~

Với danh sách không rỗng, tạo:

~~~sql
SELECT id, full_name
FROM customer
WHERE tenant_id = ?
  AND id IN (?, ?, ?);
~~~

Trong cả hai trường hợp vẫn phải bind `tenant_id` và giữ nguyên các điều kiện bắt buộc khác. `1 = 0` phù hợp với điều kiện “thuộc tập rỗng”; khi kết hợp nhiều biểu thức bằng `AND`/`OR`, hãy đặt ngoặc đúng và kiểm tra ý nghĩa của toàn bộ biểu thức.

Không nên thay danh sách rỗng bằng `IN (NULL)` chỉ để tránh lỗi cú pháp. Trong SQL ba trị, phép so sánh với `NULL` có thể tạo **UNKNOWN**; biểu thức đó đặc biệt nguy hiểm nếu bị tái sử dụng cho `NOT IN`.

## 4. Ví dụ hoàn chỉnh: tìm khách hàng theo danh sách ID

Giả sử bảng `customer` có các cột `id`, `tenant_id`, `full_name`. Một phương thức nhận ID của tenant đã xác thực cùng danh sách ID cần tìm. Nó trả danh sách rỗng khi không có ID nào; với danh sách không rỗng, nó tạo marker động và bind mọi giá trị.

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Objects;

public final class CustomerQueries {
    private CustomerQueries() {}

    public static final class Customer {
        public final long id;
        public final String fullName;

        public Customer(long id, String fullName) {
            this.id = id;
            this.fullName = fullName;
        }
    }

    public static List<Customer> findByIds(
            Connection connection,
            long authenticatedTenantId,
            List<Long> requestedIds
    ) throws SQLException {
        Objects.requireNonNull(connection, "connection");
        Objects.requireNonNull(requestedIds, "requestedIds");

        if (requestedIds.isEmpty()) {
            return List.of();
        }
        // Giới hạn minh họa, cần điều chỉnh theo DBMS và nghiệp vụ.
        if (requestedIds.size() > 500) {
            throw new IllegalArgumentException("Quá nhiều ID");
        }

        // Snapshot giúp số lượng marker khớp giá trị sẽ bind.
        // List.copyOf cũng từ chối phần tử null.
        List<Long> ids = List.copyOf(requestedIds);
        String markers = String.join(", ",
                Collections.nCopies(ids.size(), "?"));

        String sql = "SELECT id, full_name FROM customer "
                + "WHERE tenant_id = ? AND id IN (" + markers + ") "
                + "ORDER BY id";

        List<Customer> customers = new ArrayList<>();
        try (PreparedStatement ps = connection.prepareStatement(sql)) {
            ps.setLong(1, authenticatedTenantId);
            for (int i = 0; i < ids.size(); i++) {
                ps.setLong(i + 2, ids.get(i));
            }

            try (ResultSet rs = ps.executeQuery()) {
                while (rs.next()) {
                    customers.add(new Customer(
                            rs.getLong("id"),
                            rs.getString("full_name")));
                }
            }
        }
        return customers;
    }
}
~~~

Đoạn mã dùng `List.of`/`List.copyOf` (Java 9/10 trở lên). `connection` do bên gọi quản lý, vì vậy phương thức này đóng `PreparedStatement`/`ResultSet` nhưng **không tự đóng `Connection`**.

Với `authenticatedTenantId = 7` và `requestedIds = [12, 35, 48]`, câu lệnh thực tế có cấu trúc:

~~~sql
SELECT id, full_name
FROM customer
WHERE tenant_id = ? AND id IN (?, ?, ?)
ORDER BY id;
~~~

Tham số lần lượt là:

| Index JDBC | Giá trị | Ý nghĩa |
| --- | --- | --- |
| 1 | 7 | Tenant đã được xác thực |
| 2 | 12 | ID đầu tiên |
| 3 | 35 | ID thứ hai |
| 4 | 48 | ID thứ ba |

**Lưu ý bảo mật:** `authenticatedTenantId` phải lấy từ ngữ cảnh xác thực/ủy quyền đáng tin cậy. Nếu dùng ID tenant do client tự gửi mà không xác minh, truy vấn vẫn có thể truy cập sai tenant dù mọi giá trị đã được bind an toàn.

Trong một số hệ thống, ID trùng lặp như `[12, 12]` không cần tạo hai marker; có thể khử trùng lặp có chủ đích trước khi dựng SQL. `IN` dùng điều kiện thuộc tập, không bảo đảm kết quả xuất hiện theo thứ tự của danh sách đầu vào. Nếu cần giữ đúng thứ tự `[48, 12, 35]`, phải thiết kế sắp xếp rõ ràng ở Java hoặc bằng cơ chế SQL phù hợp DBMS.

## 5. Truy vấn có thêm tham số cố định: cách tránh lệch index

Khi câu SQL gồm cả các điều kiện cố định và `IN` động, rất dễ bind sai vị trí. Ví dụ:

~~~sql
SELECT id
FROM orders
WHERE tenant_id = ?
  AND status = ?
  AND id IN (?, ?, ?)
  AND created_at >= ?;
~~~

Thứ tự bind phải khớp **thứ tự dấu `?` xuất hiện từ trái sang phải**:

~~~java
String sql = "SELECT id FROM orders "
        + "WHERE tenant_id = ? AND status = ? "
        + "AND id IN (" + markers + ") "
        + "AND created_at >= ?";

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    int index = 1;
    ps.setLong(index++, authenticatedTenantId);
    ps.setString(index++, requiredStatus);

    for (Long id : ids) {
        ps.setLong(index++, id);
    }
    ps.setObject(index, createdSince); // Ví dụ LocalDateTime với cột TIMESTAMP.

    try (ResultSet rs = ps.executeQuery()) {
        // Đọc dữ liệu.
    }
}
~~~

Trong ví dụ, `markers` và `ids` được tạo/kiểm tra như phần trước; `createdSince` là giá trị `LocalDateTime` phù hợp khi cột `created_at` có nghĩa thời gian địa phương, driver hỗ trợ JDBC 4.2. Nếu cột lưu thời điểm tuyệt đối, hãy sử dụng kiểu thời gian và cách bind tương ứng với DBMS/driver.

Biến `index` giúp tránh sai vị trí khi số ID thay đổi. Chú ý `index++` tăng chỉ số **sau** khi truyền vào `setXxx`. Không suy rằng `getParameterMetaData()` luôn là giải pháp kiểm tra số tham số: một số driver không hỗ trợ đầy đủ metadata hoặc cần hỏi DBMS, nên quản lý số marker và danh sách bind một cách minh bạch.

### Tạo SQL động an toàn không có nghĩa được nối dữ liệu vào SQL

~~~java
// Không an toàn: ghép trực tiếp dữ liệu đầu vào.
String unsafe = "WHERE id IN (" + rawIdsFromRequest + ")";

// An toàn hơn: chỉ ghép các marker cố định.
String markers = String.join(", ",
        Collections.nCopies(ids.size(), "?"));
String safe = "WHERE id IN (" + markers + ")";
// Sau đó bind từng ID qua PreparedStatement.
~~~

Ngay cả khi dữ liệu được kiểm tra là số, tạo và bind marker vẫn là cách rõ ràng, nhất quán và dễ kiểm tra hơn so với ghép các giá trị vào SQL.

## 6. `NOT IN` rỗng có ngữ nghĩa khác `IN` rỗng

`IN` hỏi: “Giá trị có thuộc tập không?”. `NOT IN` hỏi: “Giá trị có nằm ngoài tập không?”.

Theo ý nghĩa tập hợp thông thường:

| Điều kiện | Với danh sách `[]` | Cách thực hiện hợp lý nếu áp dụng đúng ý nghĩa tập hợp |
| --- | --- | --- |
| `id IN ids` | Không có ID nào phù hợp | Trả rỗng hoặc `1 = 0` |
| `id NOT IN ids` | Không có ID bị loại | **Bỏ điều kiện loại trừ** hoặc dùng điều kiện luôn đúng |

Ví dụ: tìm khách hàng trong tenant 7 nhưng bỏ qua các ID bị cấm. Nếu danh sách ID bị cấm rỗng, câu truy vấn thường phải giữ mọi khách hàng **mà tenant có quyền xem**, thay vì trả rỗng:

~~~sql
-- Không có ID cần loại trừ:
SELECT id, full_name
FROM customer
WHERE tenant_id = ?;
~~~

Với danh sách loại trừ không rỗng:

~~~sql
SELECT id, full_name
FROM customer
WHERE tenant_id = ?
  AND id NOT IN (?, ?);
~~~

Quy tắc “bỏ `NOT IN` khi danh sách rỗng” chỉ áp dụng khi nghiệp vụ thật sự nói **“không loại trừ ID nào”**. Nếu API đòi ít nhất một ID hoặc có chính sách an toàn khác, phải tuân thủ hợp đồng đó.

**Cảnh báo:** bỏ điều kiện `id NOT IN ...` không có nghĩa được bỏ điều kiện `tenant_id = ?`, trạng thái bản ghi hoặc mọi kiểm soát quyền khác. Cần tách bạch **bộ lọc tùy chọn** với **điều kiện quyền bắt buộc**.

## 7. `NULL` khiến `IN`/`NOT IN` phức tạp hơn

SQL sử dụng logic ba trị: **TRUE**, **FALSE** và **UNKNOWN**. So sánh bằng `=` hoặc `<>` với `NULL` thường cho `UNKNOWN`, và `WHERE` chỉ giữ những hàng có điều kiện là TRUE.

Ví dụ minh họa:

~~~sql
-- Cột id giả định không NULL.
WHERE id IN (12, NULL)

-- Không đồng nghĩa với "loại 12, giữ mọi ID còn lại":
WHERE id NOT IN (12, NULL)
~~~

Với `id = 12`, `id IN (12, NULL)` là TRUE. Với một ID khác, điều kiện có thể là UNKNOWN thay vì FALSE; trong `WHERE` đều không chọn hàng. Đáng chú ý hơn, `id NOT IN (12, NULL)` không chọn các ID khác như bạn có thể mong đợi: các phép so sánh liên quan đến `NULL` dẫn đến UNKNOWN.

| Biểu thức | `id = 12` | `id = 35` |
| --- | --- | --- |
| `id IN (12, NULL)` | TRUE | UNKNOWN |
| `id NOT IN (12, NULL)` | FALSE | UNKNOWN |
| `id IN (12, 35)` | TRUE | TRUE |
| `id NOT IN (12, 35)` | FALSE | FALSE |

Vì vậy, phương thức tìm theo `List<Long>` ở ví dụ chính **từ chối phần tử Java null**, thay vì tự coi null là một ID hợp lệ.

Nếu cần tìm các hàng có cột `nullable_code` là `NULL`, hãy mô hình hóa điều kiện đó **riêng**:

~~~sql
-- Ví dụ: tìm code thuộc danh sách hoặc code NULL theo yêu cầu nghiệp vụ.
WHERE (nullable_code IN (?, ?) OR nullable_code IS NULL)
~~~

Không sử dụng `IN (NULL)` như một cách “thay thế an toàn” cho danh sách rỗng. Với `NOT IN`, lựa chọn này có thể làm toàn bộ truy vấn không trả hàng nào. Đối với cột bên trái có thể `NULL`, ngay cả `NOT IN` với danh sách **không có phần tử null** cũng thường không chọn các hàng mà cột đó là `NULL`; muốn giữ chúng cần có điều kiện `IS NULL` rõ ràng theo nghiệp vụ.

## 8. Danh sách rỗng trong `UPDATE` và `DELETE`

Với `SELECT`, sinh điều kiện luôn sai thường chỉ làm kết quả rỗng. Với lệnh **thay đổi dữ liệu**, việc bỏ điều kiện sai cách có thể gây hậu quả lớn.

Giả sử cần xóa chính xác các khách hàng được chọn:

~~~sql
DELETE FROM customer
WHERE tenant_id = ?
  AND id IN (?, ?);
~~~

Nếu danh sách ID rỗng, **không được** đơn giản bỏ `AND id IN (...)` rồi chạy:

~~~sql
-- Nguy hiểm nếu ý định chỉ là xóa những ID đã chọn.
DELETE FROM customer WHERE tenant_id = ?;
~~~

Đoạn SQL trên có thể xóa **mọi khách hàng của tenant**. Với hợp đồng “chỉ cập nhật/xóa các ID trong danh sách”, cách dễ hiểu là trả `0` ngay, không chạy SQL:

~~~java
public static int deleteSelected(
        Connection connection, long authenticatedTenantId, List<Long> ids)
        throws SQLException {
    Objects.requireNonNull(ids, "ids");
    if (ids.isEmpty()) {
        return 0;
    }
    if (ids.size() > 500) {
        throw new IllegalArgumentException("Quá nhiều ID");
    }
    List<Long> selected = List.copyOf(ids);
    String placeholders = String.join(", ",
            Collections.nCopies(selected.size(), "?"));
    String sql = "DELETE FROM customer WHERE tenant_id = ? "
            + "AND id IN (" + placeholders + ")";

    try (PreparedStatement ps = connection.prepareStatement(sql)) {
        ps.setLong(1, authenticatedTenantId);
        for (int i = 0; i < selected.size(); i++) {
            ps.setLong(i + 2, selected.get(i));
        }
        return ps.executeUpdate();
    }
}
~~~

Các import `Connection`, `PreparedStatement`, `SQLException`, `List`, `Objects` và `Collections` tương tự ví dụ trước. Phương thức này chỉ minh họa cách xử lý danh sách rỗng; hệ thống thực còn phải kiểm tra quyền xóa, ràng buộc FK, giao dịch, ghi nhận audit và các quy tắc nghiệp vụ khác.

Nếu nghiệp vụ **yêu cầu** tạo audit ngay cả khi không có ID nào, hãy xử lý audit độc lập và rõ ràng thay vì lặng lẽ bỏ qua.

## 9. Dùng bộ lọc tùy chọn mà không mở rộng phạm vi ngoài ý muốn

Một API thường có nhiều điều kiện: tenant bắt buộc, trạng thái tùy chọn, danh sách ID tùy chọn. Khi dựng truy vấn, hãy đặt tên rõ ý nghĩa:

~~~text
authenticatedTenantId : bắt buộc, lấy từ ngữ cảnh đã xác thực
statusFilter          : không cung cấp có thể nghĩa là mọi trạng thái
selectedIds           : [] nghĩa là tập lựa chọn rỗng
excludedIds           : [] nghĩa là không loại trừ gì
~~~

Có thể phát biểu quy tắc truy vấn như sau:

~~~mermaid
flowchart TD
    A["Nhận selectedIds"] --> B{"Filter ID có được cung cấp?"}
    B -->|"Không"| C["Áp dụng chính sách của API khi thiếu filter"]
    B -->|"Có"| D{"Danh sách rỗng?"}
    D -->|"Có"| E["SELECT: trả [] / WHERE 1=0; DML: no-op hoặc từ chối"]
    D -->|"Không"| F["Tạo n dấu ? và bind n giá trị"]
    C --> G["Luôn giữ các điều kiện quyền bắt buộc"]
    E --> G
    F --> G
~~~

Tùy thiết kế, `null` có thể bị từ chối hoàn toàn, hoặc biểu diễn “không có filter”. Điều cốt lõi là **không biến danh sách rỗng thành truy vấn tất cả hàng** chỉ vì xử lý chuỗi SQL tiện hơn.

## 10. Giới hạn độ dài danh sách và số lượng tham số

Một câu `IN (?, ?, ..., ?)` dài có những chi phí thực tế:

- Một số DBMS giới hạn số biểu thức trong `IN`, tổng số tham số hoặc độ dài câu lệnh SQL.
- SQL với số marker khác nhau có **văn bản khác nhau**, có thể khiến DBMS/driver cache hoặc chuẩn bị nhiều biến thể truy vấn.
- Câu SQL dài hơn làm tăng chi phí parse/plan và kích thước thông điệp; số lượng ID rất lớn có thể khiến kế hoạch truy vấn kém.
- Việc gửi nhiều giá trị trong một request cũng cần giới hạn tài nguyên, bất kể đã an toàn về SQL injection.

Không có một con số tối đa chung cho **mọi** JDBC driver và DBMS. Giới hạn `500` trong ví dụ là **chính sách minh họa của ứng dụng**, không phải giới hạn của JDBC. Phải kiểm chứng giới hạn thực tế theo loại DBMS, phiên bản và môi trường.

### Chia danh sách thành nhiều lượt truy vấn

Khi không thể hoặc không nên bind tất cả ID trong một câu, có thể chia thành từng nhóm kích thước vừa phải:

~~~java
int chunkSize = 200; // Chính sách ví dụ, không phải giới hạn JDBC.
for (int start = 0; start < ids.size(); start += chunkSize) {
    int end = Math.min(start + chunkSize, ids.size());
    List<Long> chunk = ids.subList(start, end);

    // Gọi phương thức truy vấn theo chunk với marker và binding riêng.
    // Gộp kết quả theo quy tắc nghiệp vụ, tránh ghi nhận trùng lặp.
}
~~~

Chia chunk có thể giúp tránh giới hạn marker, nhưng **không hoàn toàn tương đương** với một câu SQL lớn trong mọi tình huống:

- Nếu dữ liệu thay đổi giữa các lượt đọc, kết quả có thể quan sát các thời điểm khác nhau, tùy isolation/transaction.
- `ORDER BY` trên từng chunk không tự tạo ra **thứ tự toàn cục**; phân trang `LIMIT/OFFSET` cũng không thể áp dụng độc lập rồi ghép một cách tùy tiện.
- Với `UPDATE`/`DELETE`, nhiều lệnh có thể cần nằm trong **cùng transaction** để đảm bảo tính nguyên tử; mọi lỗi phải được xử lý theo ranh giới transaction.
- Cần cân nhắc khử trùng lặp ID, giới hạn số truy vấn và tránh phát sinh quá nhiều lượt đi–về DBMS.

Đối với danh sách rất lớn hoặc các thao tác đòi hỏi join, ưu tiên đánh giá các cơ chế phù hợp DBMS thay vì tăng số marker không giới hạn.

## 11. Phương án PostgreSQL: mảng SQL với `ANY`

Đối với **PostgreSQL**, có thể truyền một mảng được bind làm **một tham số SQL array** và dùng toán tử `= ANY(...)` thay cho việc tạo nhiều dấu `?`. Đây là giải pháp **riêng của PostgreSQL**, không phải cơ chế mở rộng `IN (?)` chung cho JDBC.

~~~sql
SELECT id, full_name
FROM customer
WHERE tenant_id = ?
  AND id = ANY (?::bigint[]);
~~~

Ví dụ bind bằng `java.sql.Array`:

~~~java
import java.sql.Array;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.List;
import java.util.Objects;

public static void findByPostgresArray(
        Connection connection, long tenantId, List<Long> ids)
        throws SQLException {
    Objects.requireNonNull(ids, "ids");
    // Không đưa null vào danh sách ID của ví dụ.
    Long[] values = List.copyOf(ids).toArray(new Long[0]);

    Array sqlArray = connection.createArrayOf("bigint", values);
    String sql = "SELECT id, full_name FROM customer "
            + "WHERE tenant_id = ? AND id = ANY (?::bigint[])";
    try {
        try (PreparedStatement ps = connection.prepareStatement(sql)) {
            ps.setLong(1, tenantId);
            ps.setArray(2, sqlArray);
            try (ResultSet rs = ps.executeQuery()) {
                while (rs.next()) {
                    // Ánh xạ hàng kết quả.
                }
            }
        }
    } finally {
        sqlArray.free();
    }
}
~~~

PostgreSQL có ngữ nghĩa **`x = ANY('{}'::bigint[])` là FALSE** khi mảng rỗng, nên cách này biểu diễn được bộ lọc `IN` rỗng mà không tạo `IN ()`. Tuy nhiên, với mảng chứa SQL `NULL`, việc so sánh có thể cho UNKNOWN, tương tự các vấn đề ở phần `NULL`.

`createArrayOf`, tên kiểu phần tử `"bigint"`, cú pháp `::bigint[]` và mức hỗ trợ `Array.free()` phải được kiểm chứng với driver. Tham số mảng có thể giảm số biến thể SQL do độ dài danh sách thay đổi, nhưng **không mặc nhiên hiệu năng tốt hơn trong mọi truy vấn**; vẫn cần thử trên dữ liệu và chỉ mục thực tế.

Không áp dụng nguyên ví dụ này cho MySQL, SQL Server hoặc các DBMS khác mà không kiểm tra cú pháp và API tương ứng.

## 12. Phương án khác cho danh sách lớn

Ngoài danh sách marker và mảng SQL, các DBMS có thể hỗ trợ những cách tổ chức khác:

| Phương án | Phù hợp khi | Điều cần chú ý |
| --- | --- | --- |
| **N marker `IN (?,...)`** | Danh sách nhỏ/vừa, cần tương thích JDBC rộng | Xử lý rỗng, giới hạn marker, biến thể SQL |
| **SQL array + `ANY` / cú pháp riêng** | DBMS có hỗ trợ array phù hợp | API/kiểu SQL riêng; kiểm tra null/rỗng |
| **Table-valued parameter** | DBMS/driver hỗ trợ tham số dạng bảng, chẳng hạn một số API SQL Server | Cơ chế nhà cung cấp, không phải JDBC chung |
| **Temporary/staging table** | Danh sách rất lớn, cần join với các cột khác | Vòng đời bảng, transaction, dọn trạng thái phiên khi dùng pool |
| **Join với bảng nghiệp vụ** | Tập ID đã nằm trong DB và có quan hệ dữ liệu rõ | Hạn chế chuyển ID ra Java rồi gửi ngược lại |
| **Truy vấn theo chunk** | Cần giải pháp chuyển tiếp, gặp giới hạn tham số | Chi phí nhiều round-trip, thứ tự và nhất quán giao dịch |

Ví dụ khi tập cần lọc đã có trong DB, một subquery thường rõ ràng hơn việc đọc ra `List<Long>` rồi tạo lại `IN` trong Java:

~~~sql
SELECT c.id, c.full_name
FROM customer AS c
WHERE c.tenant_id = ?
  AND c.id IN (
      SELECT a.customer_id
      FROM active_customer AS a
      WHERE a.tenant_id = ?
  );
~~~

Ở ví dụ, cả hai tham số tenant phải được bind từ ngữ cảnh đã xác thực. Cấu trúc truy vấn và sự tồn tại của bảng `active_customer` chỉ mang tính minh họa.

Nếu sử dụng **temporary table** trên kết nối từ pool, cần hiểu DBMS có giữ bảng tạm qua commit hoặc lần mượn sau hay không. Việc đóng `Connection` logic thường chỉ trả kết nối vật lý về pool; tài nguyên phiên còn sót có thể gây ảnh hưởng đến request khác.

## 13. Kiểm thử các trường hợp biên

Không chỉ kiểm tra truy vấn có ba ID. Các tình huống sau giúp phát hiện lỗi SQL, lỗi index và sai ý nghĩa nghiệp vụ:

| Tình huống | Giá trị đầu vào | Kỳ vọng |
| --- | --- | --- |
| Tập rỗng cho `IN` | `[]` | Không sinh `IN ()`; trả rỗng hoặc điều kiện luôn sai |
| Một ID | `[12]` | Đúng một marker; bind đúng ID |
| Nhiều ID | `[12,35,48]` | Ba marker; không nối giá trị vào SQL |
| ID trùng | `[12,12,35]` | Không tạo hàng trùng chỉ vì ID lặp trong `IN` |
| Có phần tử null | `[12,null]` | Từ chối/định nghĩa lại theo hợp đồng, không âm thầm bỏ qua |
| Không có bộ lọc | `null` | Hành vi khác `[]`, tuân thủ hợp đồng API |
| `NOT IN` rỗng | `[]` | Không loại trừ ID nào, nhưng vẫn giữ điều kiện quyền |
| `NOT IN` có null | `[12,null]` | Không chấp nhận kết quả ngoài dự kiến vì SQL UNKNOWN |
| Tham số trước/sau `IN` | Tenant + IDs + thời gian | Index bind đúng thứ tự từ trái sang phải |
| Danh sách vượt giới hạn | Nhiều nghìn ID | Từ chối, chunk hoặc dùng giải pháp DBMS được hỗ trợ |
| Xóa theo danh sách rỗng | `[]` | Không chuyển thành `DELETE` toàn bộ tenant |
| SQL array rỗng | Mảng rỗng trong DBMS hỗ trợ | Hành vi phù hợp tài liệu driver và yêu cầu nghiệp vụ |

Với phép kiểm thử JDBC tích hợp, nên xác minh **cả dữ liệu thực tế và số hàng ảnh hưởng**, không chỉ kiểm tra câu SQL không phát sinh lỗi. Kiểm tra đường lỗi và rollback nếu dùng các thao tác sửa dữ liệu theo chunk.

### Câu hỏi tự đánh giá

1. Vì sao `IN (?)` với `setString(1, "12,35,48")` không tương đương `IN (?,?,?)`?
2. Với danh sách `[]`, khi nào nên trả `List.of()` và khi nào nên tạo `WHERE 1=0`?
3. Vì sao `[]` và “không cung cấp bộ lọc” phải được phân biệt?
4. `NOT IN` với danh sách rỗng cần xử lý khác `IN` ra sao?
5. Phần tử `NULL` làm thay đổi kết quả `NOT IN` như thế nào?
6. Nếu SQL có hai tham số trước `IN` và một tham số sau `IN`, cách nào giúp tránh bind sai index?
7. Khi nào chia chunk có thể làm thay đổi thứ tự, phân trang hoặc tính nhất quán?
8. Giải pháp `= ANY(?)` với SQL array có phải tính năng mở rộng danh sách `IN` của JDBC tiêu chuẩn không?

## 14. Quy tắc thực hành khi viết `IN` động bằng JDBC

1. **Chốt hợp đồng đầu vào:** danh sách là bắt buộc hay tùy chọn; `null` và `[]` mang ý nghĩa gì?
2. **Xử lý danh sách rỗng trước khi dựng SQL:** với `IN`, trả rỗng hoặc dùng điều kiện luôn sai khi hợp lý; với `NOT IN`, thường bỏ riêng điều kiện loại trừ.
3. **Giữ các bộ lọc bắt buộc:** tenant, quyền truy cập, trạng thái và ràng buộc nghiệp vụ không được mất khi danh sách rỗng.
4. **Tạo đúng số marker cố định:** `String.join(", ", Collections.nCopies(n, "?"))` cho `n > 0`.
5. **Bind từng giá trị:** dùng `setLong`, `setString` hoặc kiểu JDBC tương ứng; đánh index từ **1** và tính cả các marker ở trước/sau danh sách.
6. **Định nghĩa chính sách `NULL` rõ ràng:** từ chối phần tử null nếu ID không được null; dùng `IS NULL` khi thực sự cần tìm null.
7. **Giới hạn kích thước đầu vào:** dựa vào khả năng DBMS/driver và nhu cầu thực tế; cân nhắc SQL array, bảng tạm hoặc join cho danh sách lớn.
8. **Thử cả đọc và ghi:** đặc biệt kiểm tra không có tình huống `UPDATE`/`DELETE` rỗng vô tình mở rộng sang nhiều bản ghi.

**Điểm cốt lõi:** `PreparedStatement` có thể bind **giá trị**, còn cấu trúc `IN` phải được tạo với đúng số vị trí tham số hoặc bằng một cơ chế dữ liệu tập hợp mà DBMS hỗ trợ. Xử lý danh sách rỗng theo đúng nghiệp vụ và giữ nguyên các điều kiện quyền giúp truy vấn JDBC vừa an toàn vừa có kết quả dễ dự đoán.
