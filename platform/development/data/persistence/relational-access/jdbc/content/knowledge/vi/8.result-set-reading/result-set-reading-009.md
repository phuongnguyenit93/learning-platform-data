# Phân biệt thứ tự do SQL xác định và thứ tự xuất hiện tình cờ

## 1. Vì sao thứ tự hàng lại quan trọng khi đọc `ResultSet`?

Trong **JDBC (Java Database Connectivity)**, API Java dùng để truy cập cơ sở dữ liệu quan hệ, `java.sql.ResultSet` cho phép ứng dụng đọc từng hàng của kết quả truy vấn. Với một `ResultSet` thông thường, chương trình dùng `next()` để tiến tới hàng tiếp theo:

```java
try (ResultSet rs = statement.executeQuery()) {
    while (rs.next()) {
        System.out.println(rs.getLong("id"));
    }
}
```

Đoạn mã sẽ in các hàng **theo trình tự mà cơ sở dữ liệu trả về cho JDBC**. Tuy nhiên, việc có thể đọc lần lượt bằng `next()` **không có nghĩa SQL đã bảo đảm trình tự ấy**.

Cần phân biệt hai trường hợp:

- **Thứ tự do SQL xác định:** câu truy vấn có `ORDER BY` áp dụng cho kết quả cuối cùng, nêu rõ các khóa sắp xếp; khi cần thứ tự hoàn toàn xác định, các khóa phải đủ để phân biệt những hàng có thể bị hòa nhau.
- **Thứ tự xuất hiện tình cờ:** câu truy vấn không yêu cầu thứ tự ở mức kết quả cuối cùng, nhưng DBMS vẫn phải gửi từng hàng theo một trình tự nào đó. Trình tự quan sát được có thể do cách quét bảng, chỉ mục, thuật toán nối bảng, bộ tối ưu hoặc xử lý song song quyết định.

Đây là quy tắc nền tảng khi xây dựng danh sách, bảng dữ liệu, xuất báo cáo và phân trang trong ứng dụng JDBC: **muốn yêu cầu thứ tự, hãy diễn đạt bằng SQL `ORDER BY`**.

## 2. Truy vấn không có `ORDER BY`: có hàng, nhưng không có cam kết về thứ tự

Giả sử bảng `orders` đang có dữ liệu:

| `id` | `created_at` | `status` |
|---:|---|---|
| 103 | 2026-11-03 08:00:00 | NEW |
| 101 | 2026-11-01 09:00:00 | PAID |
| 102 | 2026-11-02 10:00:00 | NEW |

Ứng dụng thực hiện:

```sql
SELECT id, created_at, status
FROM orders;
```

Cơ sở dữ liệu **có thể** trả `101, 102, 103`, cũng **có thể** trả `103, 101, 102`, hoặc một trình tự khác. Không thể dùng thứ tự chèn vào bảng hoặc thứ tự từng thấy trong công cụ quản trị DB để kết luận rằng các lần chạy sau sẽ giữ nguyên.

Ví dụ, một kế hoạch truy vấn có thể quét bảng theo vị trí lưu trữ; kế hoạch khác có thể quét một chỉ mục; kế hoạch thứ ba sử dụng nhiều luồng xử lý và kết hợp kết quả. Việc thêm chỉ mục, thay đổi số lượng bản ghi, cập nhật thống kê hoặc nâng cấp phiên bản DBMS có thể làm kế hoạch thay đổi.

**Ngay cả khi chạy 1.000 lần đều thấy một thứ tự giống nhau, đó vẫn không phải là cam kết của SQL.** Thứ tự ngẫu nhiên ở đây không nhất thiết biến đổi mỗi lần thực thi; “tình cờ” nghĩa là **không được hợp đồng truy vấn bảo đảm**.

## 3. `ORDER BY` quy định thứ tự như thế nào?

Để sắp xếp đơn hàng theo thời điểm tạo từ cũ đến mới:

```sql
SELECT id, created_at, status
FROM orders
ORDER BY created_at ASC;
```

Để hiển thị các đơn mới nhất trước:

```sql
SELECT id, created_at, status
FROM orders
ORDER BY created_at DESC;
```

| Cú pháp | Ý nghĩa |
|---|---|
| `ORDER BY created_at` | Tăng dần theo `created_at`; `ASC` thường là mặc định |
| `ORDER BY created_at ASC` | Sắp xếp tăng dần tường minh |
| `ORDER BY created_at DESC` | Sắp xếp giảm dần |
| `ORDER BY status ASC, created_at DESC` | Nhóm theo `status` tăng dần; trong mỗi nhóm, thời điểm tạo giảm dần |

`ORDER BY` có thể chứa **nhiều biểu thức**, được xét theo thứ tự từ trái sang phải. Khi hai hàng có cùng giá trị ở biểu thức đầu, DBMS xét biểu thức tiếp theo. Nếu tất cả khóa sắp xếp vẫn bằng nhau, SQL chưa yêu cầu một thứ tự cụ thể giữa các hàng đó.

Với ứng dụng có yêu cầu hiển thị chính xác, nên định nghĩa rõ chiều sắp xếp và các khóa phụ thay vì phụ thuộc vào trạng thái vật lý của bảng.

## 4. Có `ORDER BY` vẫn có thể còn những hàng hòa nhau

Giả sử hai đơn được tạo đúng cùng một thời điểm:

| `id` | `created_at` |
|---:|---|
| 205 | 2026-11-10 09:30:00 |
| 206 | 2026-11-10 09:30:00 |
| 204 | 2026-11-09 17:00:00 |

Truy vấn sau đặt đơn mới trước nhưng **không chỉ định ai đứng trước giữa `205` và `206`**:

```sql
SELECT id, created_at
FROM orders
ORDER BY created_at DESC;
```

Hai kết quả đầu tiên đều có thể là `205, 206` hoặc `206, 205`. Cả hai đều thỏa mãn `ORDER BY created_at DESC`.

Nếu `id` là **khóa chính duy nhất**, có thể thêm khóa phụ để có thứ tự toàn phần trong cùng một trạng thái dữ liệu:

```sql
SELECT id, created_at
FROM orders
ORDER BY created_at DESC, id DESC;
```

Khi đó ba hàng trên phải xuất hiện theo thứ tự `206, 205, 204`. Nguyên tắc có thể tổng quát hóa:

> Nếu ứng dụng cần trình tự **có thể tái lập trên cùng một tập dữ liệu**, hãy bổ sung khóa sắp xếp đủ để phân biệt các hàng, thường kết thúc bằng một khóa duy nhất như `id`.

Điều này **không đảm bảo hai lần truy vấn ở hai thời điểm khác nhau sẽ trả đúng cùng các hàng**. Giao dịch khác có thể chèn, sửa hoặc xóa dữ liệu giữa hai lần chạy. `ORDER BY` quyết định trình tự đối với những hàng xuất hiện trong kết quả, còn **tính ổn định của tập dữ liệu** phụ thuộc giao dịch và mức cô lập.

## 5. JDBC có tự sắp xếp các hàng hay không?

Khi đã có kết quả SQL, `ResultSet.next()` chỉ chuyển sang hàng tiếp theo theo thứ tự mà driver cung cấp. Không có lựa chọn sắp xếp nào trong `next()`, `getInt()` hoặc `getString()`.

Ví dụ hoàn chỉnh sau lấy danh sách đơn hàng theo thời gian giảm dần, dùng `id` làm khóa phá hòa:

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import javax.sql.DataSource;

public final class OrderReader {
    private final DataSource dataSource;

    public OrderReader(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public void printRecentOrders(String status) throws SQLException {
        String sql = "SELECT id, created_at, status FROM orders " +
                     "WHERE status = ? " +
                     "ORDER BY created_at DESC, id DESC";

        try (Connection connection = dataSource.getConnection();
             PreparedStatement statement = connection.prepareStatement(sql)) {
            statement.setString(1, status);

            try (ResultSet rs = statement.executeQuery()) {
                while (rs.next()) {
                    long id = rs.getLong("id");
                    String createdAt = rs.getString("created_at");
                    System.out.println(id + " | " + createdAt);
                }
            }
        }
    }
}
```

Ví dụ giả định bảng có `id` là khóa duy nhất, `created_at` không `NULL`, cột `status` thuộc kiểu chuỗi và `DataSource` được cấu hình sẵn. `getString("created_at")` được dùng ở đây để minh họa giá trị in ra; trong nghiệp vụ xử lý thời gian, nên dùng kiểu `java.time` phù hợp với SQL và driver.

Điểm quyết định thứ tự là `ORDER BY created_at DESC, id DESC` **ở SQL**, không phải vòng lặp Java. `PreparedStatement` ràng buộc `status` an toàn dưới dạng **giá trị**; cách ràng buộc tham số này không làm thay đổi quy tắc sắp xếp.

Tương tự, `ResultSet.TYPE_SCROLL_INSENSITIVE` cho phép các thao tác điều hướng khi driver hỗ trợ, nhưng **không tạo ra bảo đảm thứ tự mới** cho kết quả SQL. `setFetchSize(...)` ảnh hưởng gợi ý cách lấy dữ liệu từ driver/DBMS, không phải thay thế `ORDER BY`.

## 6. Vì sao chỉ mục hoặc khóa chính không bảo đảm thứ tự đọc?

Một hiểu lầm phổ biến là: **“Bảng có khóa chính `id` nên `SELECT * FROM orders` tự tăng dần theo `id`.”** SQL không quy định như vậy.

Chỉ mục có thể hỗ trợ tìm kiếm hoặc giúp DBMS tạo thứ tự một cách hiệu quả, nhưng **việc có chỉ mục không buộc bộ tối ưu phải sử dụng nó**, cũng không buộc kết quả không có `ORDER BY` đi theo chỉ mục.

```text
SELECT id, status FROM orders;
              │
              ├── Kế hoạch A: quét bảng → trình tự theo cách đọc hiện tại
              ├── Kế hoạch B: quét chỉ mục → trình tự khác
              └── Kế hoạch C: thực thi song song → cách ghép hàng khác

Không có ORDER BY ⇒ không được dựa vào trình tự nào ở trên.
```

Ngay cả với hệ quản trị có *clustered index* hoặc cách lưu dữ liệu gần theo khóa chính, trình tự lưu vật lý **không thay thế yêu cầu sắp xếp trong câu SQL**. Mặt khác, khi có `ORDER BY`, bộ tối ưu có thể tận dụng chỉ mục phù hợp để tránh một phép sort riêng; **bảo đảm là từ mệnh đề `ORDER BY`, còn chỉ mục là chi tiết thực thi**.

## 7. `JOIN`, `GROUP BY`, `DISTINCT` có khiến kết quả được sắp xếp không?

Không nên suy luận thứ tự kết quả chỉ từ toán tử SQL đã dùng.

### `JOIN`

```sql
SELECT o.id, c.name
FROM orders o
JOIN customers c ON c.id = o.customer_id;
```

Thứ tự hàng có thể chịu ảnh hưởng của nested-loop join, hash join, merge join và lựa chọn kế hoạch của DBMS. Nếu giao diện cần đơn hàng mới trước, phải đặt `ORDER BY` cho kết quả truy vấn:

```sql
SELECT o.id, c.name, o.created_at
FROM orders o
JOIN customers c ON c.id = o.customer_id
ORDER BY o.created_at DESC, o.id DESC;
```

### `GROUP BY` và `DISTINCT`

```sql
SELECT status, COUNT(*) AS total
FROM orders
GROUP BY status;
```

`GROUP BY` tạo nhóm để tính tổng hợp; `DISTINCT` loại bỏ các hàng trùng theo biểu thức được chọn. **Cả hai không phải hợp đồng sắp xếp đầu ra.** Dù một kế hoạch dùng thuật toán sort trong quá trình nhóm, chương trình không được dựa vào việc kết quả sẽ tăng dần theo `status`.

Muốn báo cáo hiển thị số lượng lớn nhất trước:

```sql
SELECT status, COUNT(*) AS total
FROM orders
GROUP BY status
ORDER BY total DESC, status ASC;
```

Nếu `status` được cho phép là `NULL`, cần thiết kế thêm quy tắc xử lý `NULL` phù hợp với DBMS để tránh ngộ nhận thứ tự giữa các giá trị trống.

### Thứ tự của phép toán tập hợp

Với `UNION` hoặc `UNION ALL`, không nên mặc định thứ tự từ từng nhánh sẽ được giữ nguyên trong kết quả tổng hợp. Muốn sắp xếp toàn bộ kết quả, đặt `ORDER BY` ở **mức truy vấn tổng thể** theo cú pháp DBMS hỗ trợ.

## 8. `ORDER BY` trong truy vấn con không thay thế sắp xếp kết quả ngoài

Ví dụ:

```sql
SELECT id, created_at
FROM (
    SELECT id, created_at
    FROM orders
    ORDER BY created_at DESC
) AS recent_orders;
```

Một số DBMS cho phép dạng SQL này, một số yêu cầu cấu trúc khác. Dù truy vấn con được sắp xếp bên trong, **truy vấn ngoài không có `ORDER BY` nên không cung cấp bảo đảm tổng quát về thứ tự đầu ra**. Bộ tối ưu có thể biến đổi kế hoạch hoặc chọn cách thực thi khác.

Nếu cần thứ tự của danh sách ở tầng ngoài, hãy viết:

```sql
SELECT id, created_at
FROM orders
ORDER BY created_at DESC, id DESC;
```

Tương tự, `ORDER BY` trong một view hoặc common table expression (`WITH ...`) không nên được dùng làm bằng chứng thứ tự cho phép `SELECT` ngoài cùng. Một số cấu trúc như `ORDER BY ... LIMIT` bên trong truy vấn con **có thể quyết định tập hàng được chọn**; nhưng điều đó vẫn không thay thế việc sắp xếp ở truy vấn ngoài khi chương trình cần một trình tự hiển thị cụ thể.

## 9. `LIMIT`, `OFFSET` và phân trang cần thứ tự ổn định

Phân trang làm hậu quả của thứ tự tình cờ trở nên rõ rệt. Ví dụ PostgreSQL/MySQL thường hỗ trợ cú pháp:

```sql
SELECT id, created_at
FROM orders
LIMIT 10 OFFSET 10;
```

Đây là yêu cầu lấy một nhóm hàng, nhưng **không định nghĩa trang đó gồm những hàng nào theo một thứ tự nghiệp vụ**. Nếu kế hoạch truy vấn thay đổi, hai lần lấy trang có thể trả các hàng khác nhau dù dữ liệu không đổi.

Cách có ý nghĩa rõ ràng hơn:

```sql
SELECT id, created_at
FROM orders
ORDER BY created_at DESC, id DESC
LIMIT 10 OFFSET 10;
```

`LIMIT/OFFSET` là cú pháp của nhiều DBMS như PostgreSQL và MySQL; SQL Server thường dùng `OFFSET ... FETCH` kết hợp `ORDER BY`, còn các DBMS khác có biến thể riêng. Điều **không đổi** là: trước khi cắt trang, cần nêu rõ cách sắp xếp.

Ví dụ với `ORDER BY created_at DESC` nhưng không có `id` phá hòa, các hàng cùng thời điểm có thể đổi chỗ giữa các trang. Thêm khóa duy nhất làm thứ tự rõ ràng hơn **trên cùng trạng thái dữ liệu**.

Tuy nhiên, khi có request mới chèn đơn hàng vào đầu danh sách giữa lần lấy trang 1 và trang 2, `OFFSET` có thể bị dịch vị trí và gây trùng hoặc bỏ sót hàng, **ngay cả khi đã `ORDER BY` bằng khóa duy nhất**. Khi cần nhất quán qua nhiều trang trong lúc dữ liệu thay đổi, phải cân nhắc chiến lược phân trang khác và cơ chế nhất quán dữ liệu.

## 10. Phân trang theo khóa (*keyset pagination*) giữ quy tắc sắp xếp

Đối với danh sách đơn hàng mới nhất trước theo `created_at DESC, id DESC`, trang đầu tiên có thể lấy bằng:

```sql
SELECT id, created_at, status
FROM orders
ORDER BY created_at DESC, id DESC
LIMIT 10;
```

Giả sử hàng cuối cùng của trang trước có `(created_at, id)` bằng `(2026-11-10 09:30:00, 205)`. Trang tiếp theo dùng chính cặp khóa đó làm **mốc**:

```sql
SELECT id, created_at, status
FROM orders
WHERE created_at < ?
   OR (created_at = ? AND id < ?)
ORDER BY created_at DESC, id DESC
LIMIT 10;
```

Ví dụ JDBC, dùng `LocalDateTime` khi cột `created_at` là SQL `TIMESTAMP` **không có múi giờ** và driver hỗ trợ ánh xạ Java time:

```java
import java.time.LocalDateTime;
import java.sql.PreparedStatement;
import java.sql.ResultSet;

LocalDateTime lastCreatedAt = LocalDateTime.of(2026, 11, 10, 9, 30);
long lastId = 205L;

String sql = "SELECT id, created_at, status FROM orders " +
             "WHERE created_at < ? " +
             "OR (created_at = ? AND id < ?) " +
             "ORDER BY created_at DESC, id DESC LIMIT 10";

try (PreparedStatement statement = connection.prepareStatement(sql)) {
    statement.setObject(1, lastCreatedAt);
    statement.setObject(2, lastCreatedAt);
    statement.setLong(3, lastId);

    try (ResultSet rs = statement.executeQuery()) {
        while (rs.next()) {
            System.out.println(rs.getLong("id"));
        }
    }
}
```

Ví dụ giả định `connection` đang mở, `id` duy nhất, `created_at` khác `NULL`, các hàng có ý nghĩa bất biến đối với khóa phân trang và DBMS hỗ trợ `LIMIT`. Nếu chỉ muốn lấy đơn thuộc một tenant hoặc có trạng thái nhất định, **điều kiện lọc đó phải được giữ nhất quán ở mọi trang**.

Keyset pagination giúp tránh tình trạng trang sau phụ thuộc vào số hàng ở các vị trí đầu bị chèn thêm như với `OFFSET`; nhưng **không tự tạo ảnh chụp dữ liệu bất biến**. Việc cập nhật khóa sắp xếp, xóa bản ghi và thay đổi điều kiện lọc giữa các request vẫn có thể làm kết quả biến động. Nếu yêu cầu một báo cáo cố định qua nhiều lần đọc, cần một cơ chế snapshot/giao dịch hoặc lưu dấu mốc dữ liệu phù hợp.

## 11. `NULL`, collation và kiểu dữ liệu ảnh hưởng đến thứ tự

Ngay cả khi đã viết `ORDER BY`, cần biết **quy tắc so sánh** đang được dùng.

### Giá trị `NULL`

DBMS có thể đặt `NULL` trước hoặc sau giá trị khác theo chiều `ASC`/`DESC`; khả năng dùng `NULLS FIRST` hoặc `NULLS LAST` cũng khác nhau giữa hệ quản trị.

Nếu cần một quy tắc dễ diễn đạt trên nhiều DBMS hỗ trợ biểu thức `CASE`, có thể dùng:

```sql
SELECT id, completed_at
FROM tasks
ORDER BY
    CASE WHEN completed_at IS NULL THEN 1 ELSE 0 END ASC,
    completed_at ASC,
    id ASC;
```

Truy vấn đặt các công việc có `completed_at` khác `NULL` trước, theo thời điểm tăng dần, rồi mới đến công việc chưa hoàn thành. `id` duy nhất giúp giải quyết trường hợp hòa khóa. Cú pháp và khả năng tối ưu hóa vẫn cần kiểm tra trên DBMS cụ thể.

### Quy tắc so sánh chuỗi (*collation*)

Sắp xếp `ORDER BY customer_name` có thể khác nhau theo collation về chữ hoa/chữ thường, dấu tiếng Việt, Unicode và quy tắc ngôn ngữ. Vì thế, khi chuyển môi trường hoặc đổi collation, trình tự tên có thể khác dù truy vấn SQL không đổi.

Trong một collation coi hai chuỗi khác nhau là bằng nhau về thứ tự, thêm một khóa định danh duy nhất vẫn cần thiết nếu ứng dụng muốn một thứ tự toàn phần.

### Kiểu số so với chuỗi

Giả sử dữ liệu lần lượt là `"2"`, `"10"`, `"100"` trong một cột văn bản. `ORDER BY text_code` sẽ sắp xếp theo quy tắc chuỗi, có thể đưa `"10"` và `"100"` trước `"2"`, **khác với sắp xếp số học**. Hãy chọn kiểu SQL thể hiện đúng ngữ nghĩa: mã có số `0` đầu cần giữ như chuỗi, trong khi số lượng thực sự nên được lưu bằng kiểu số.

## 12. Sắp xếp động trong JDBC phải kiểm soát tên cột

Ứng dụng thường cho người dùng chọn “mới nhất”, “cũ nhất” hoặc “theo tên”. `PreparedStatement` ràng buộc **giá trị** bằng `?`, nhưng không thể dùng `?` để thay trực tiếp tên cột hoặc từ khóa `ASC`/`DESC`:

```sql
-- Sai ý định: ? là giá trị, không trở thành tên cột.
SELECT id, created_at FROM orders ORDER BY ?;
```

Một cách an toàn là ánh xạ lựa chọn của người dùng vào một **danh sách thứ tự SQL được định nghĩa sẵn**:

```java
String orderClause;

switch (sortMode) {
    case "OLDEST":
        orderClause = "created_at ASC, id ASC";
        break;
    case "NEWEST":
        orderClause = "created_at DESC, id DESC";
        break;
    default:
        throw new IllegalArgumentException("Kiểu sắp xếp không hợp lệ");
}

String sql = "SELECT id, created_at FROM orders " +
             "WHERE status = ? ORDER BY " + orderClause;

try (PreparedStatement statement = connection.prepareStatement(sql)) {
    statement.setString(1, requestedStatus);
    try (ResultSet rs = statement.executeQuery()) {
        while (rs.next()) {
            System.out.println(rs.getLong("id"));
        }
    }
}
```

Ví dụ giả định `sortMode`, `requestedStatus` và `connection` đã tồn tại. `orderClause` chỉ lấy từ **chuỗi SQL hằng do ứng dụng định nghĩa**, không chèn trực tiếp văn bản người dùng vào `ORDER BY`. Vẫn dùng tham số `?` cho `status` như bình thường.

## 13. Những nhầm lẫn phổ biến

| Nhận định sai | Vì sao sai? | Cách xử lý |
|---|---|---|
| “Không `ORDER BY` nhưng lần nào cũng thấy tăng dần nên chắc là ổn định.” | Thứ tự tình cờ không được SQL bảo đảm | Nêu rõ `ORDER BY` ở truy vấn trả kết quả |
| “Khóa chính hoặc index quyết định thứ tự mặc định.” | Bộ tối ưu có thể dùng kế hoạch truy cập khác | Sắp xếp theo khóa nghiệp vụ, bổ sung khóa phụ duy nhất nếu cần |
| “`ORDER BY created_at` luôn cho một thứ tự duy nhất.” | Nhiều hàng có thể cùng thời điểm | Thêm `id` hoặc khóa duy nhất làm tiêu chí phá hòa |
| “`GROUP BY` hoặc `DISTINCT` tự sắp xếp đầu ra.” | Chúng xử lý nhóm và tính duy nhất, không cam kết thứ tự | Sử dụng `ORDER BY` cho kết quả tổng hợp |
| “`ORDER BY` trong view/CTE đủ để sắp xếp mọi truy vấn ngoài.” | Thứ tự nội bộ không phải bảo đảm của kết quả ngoài | Đặt `ORDER BY` ở mức truy vấn sử dụng dữ liệu |
| “`LIMIT 10` luôn lấy mười bản ghi mới nhất.” | `LIMIT` chỉ giới hạn số hàng | Kết hợp `ORDER BY created_at DESC, id DESC` |
| “Có `ORDER BY` thì phân trang bằng `OFFSET` không bao giờ trùng hàng.” | Dữ liệu có thể thay đổi giữa các lần lấy trang | Cân nhắc keyset và nhất quán snapshot/giao dịch |
| “`ResultSet.next()` tự sắp xếp theo khóa chính.” | `next()` chỉ di chuyển con trỏ đọc | Đặt yêu cầu thứ tự trong SQL |
| “Sắp xếp chuỗi số luôn giống sắp xếp số.” | Collation và kiểu dữ liệu quyết định cách so sánh | Thiết kế kiểu dữ liệu phù hợp, kiểm tra quy tắc sort |

## 14. Bài tập tự kiểm tra

Cho bảng `events` có dữ liệu:

| `id` | `event_time` |
|---:|---|
| 7 | 2026-11-12 10:00:00 |
| 9 | 2026-11-13 08:00:00 |
| 8 | 2026-11-13 08:00:00 |

Hãy xem ba câu truy vấn:

```sql
-- A
SELECT id FROM events;

-- B
SELECT id FROM events ORDER BY event_time DESC;

-- C
SELECT id FROM events ORDER BY event_time DESC, id ASC;
```

**Câu hỏi:** Có thể kết luận chính xác thứ tự các ID được đọc bằng `while (rs.next())` cho từng truy vấn không?

- **A:** Không. Không có `ORDER BY`, nên SQL không bảo đảm trình tự các hàng.
- **B:** ID `8` và `9` cùng có thời điểm mới nhất, do đó cả `8, 9, 7` lẫn `9, 8, 7` đều thỏa mãn truy vấn.
- **C:** Có, nếu dữ liệu đúng như bảng và `id` là duy nhất: kết quả phải là **`8, 9, 7`**.

Giả sử sau đó có một event mới được chèn với thời điểm `2026-11-14 00:00:00`. Truy vấn C khi chạy lại sẽ đưa event mới lên trước; đó là **tập dữ liệu đã thay đổi**, không phải `ORDER BY` mất tính đúng đắn.

**Ghi nhớ:** `ResultSet` đọc tuần tự theo kết quả JDBC nhận được; **SQL `ORDER BY` mới là nơi xác định trình tự mà ứng dụng được phép dựa vào**. Không có `ORDER BY`, thứ tự quan sát được chỉ là hệ quả của cách thực thi. Có `ORDER BY` nhưng còn khóa hòa nhau, phải thêm tiêu chí phá hòa khi cần trình tự chính xác; đối với phân trang, còn phải quản lý việc dữ liệu thay đổi giữa các lần đọc.
