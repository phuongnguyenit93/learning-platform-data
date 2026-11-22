# Giảm số lượt trao đổi bằng truy vấn và batch phù hợp trong JDBC

Khi ứng dụng Java dùng **JDBC** truy cập cơ sở dữ liệu quan hệ, thời gian xử lý không chỉ phụ thuộc câu SQL chạy nhanh hay chậm ở server. Mỗi lần ứng dụng yêu cầu dữ liệu, một phần chi phí có thể đến từ truyền lệnh qua mạng, chờ phản hồi, parse/execute SQL, chuyển đổi dữ liệu và quản lý tài nguyên. Đặc biệt, vòng lặp thực thi hàng trăm câu `SELECT` hoặc `INSERT` riêng lẻ dễ khiến độ trễ tăng dù mỗi câu rất đơn giản.

Trong chương **Hiệu năng**, bài học này tập trung vào cách **giảm số lượt trao đổi giữa ứng dụng và cơ sở dữ liệu bằng cách chọn truy vấn và batching phù hợp**. Chúng ta sẽ nhận diện N+1 query, sử dụng `JOIN`/`GROUP BY` và truy vấn theo nhóm khóa, phân biệt SQL tập hợp với `PreparedStatement.addBatch()`/`executeBatch()`, điều chỉnh kích thước lô, quản lý transaction, xử lý lỗi và đo hiệu quả thực tế. Mọi ví dụ đều dựa trên các API JDBC chuẩn như `DataSource`, `Connection`, `PreparedStatement` và `ResultSet`.

**Điểm cốt lõi:** giảm **số lệnh gọi JDBC** không phải lúc nào cũng tương đương giảm **số lượt mạng**, và giảm lượt mạng không tự động làm hệ thống nhanh hơn. Kết quả cuối cùng còn tùy cách driver truyền batch, khả năng tối ưu SQL của database, kích thước dữ liệu trả về, khóa, transaction và tải đồng thời.

## 1. Vì sao nhiều lượt trao đổi nhỏ thường đắt?

Hãy hình dung một dịch vụ trả danh sách 100 khách hàng kèm số đơn hàng đã đặt. Nếu lần đầu đọc danh sách khách hàng, rồi chạy thêm một truy vấn đếm đơn cho từng người, service có thể gửi:

```text
1 lần SELECT customers
  ├─ 1 SELECT COUNT(*) cho khách A
  ├─ 1 SELECT COUNT(*) cho khách B
  ├─ ...
  └─ 1 SELECT COUNT(*) cho khách thứ 100

Tổng cộng: 1 + 100 = 101 truy vấn SQL.
```

Nếu phần lớn truy vấn đơn giản nhưng mỗi lần ứng dụng phải chờ phản hồi, chi phí truyền và điều phối có thể đáng kể. Một mô hình **xấp xỉ** để suy nghĩ:

```text
T_total ≈ N_round_trips × RTT
        + T_database_execution
        + T_transfer_and_decode
        + T_application_processing
```

Trong đó:

- `N_round_trips` là **số vòng trao đổi mạng thực tế**, không nhất thiết bằng số lần gọi `executeQuery()` hoặc `executeUpdate()`.
- `RTT` là thời gian mạng qua lại mang tính đại diện; trên thực tế nó dao động theo tải, kết nối và cơ chế truyền.
- `T_database_execution` gồm lập kế hoạch/thực thi SQL, đọc/ghi, khóa và tranh chấp tài nguyên.
- `T_transfer_and_decode` phụ thuộc số dòng, số cột, kiểu dữ liệu và cách driver nhận/giải mã.
- `T_application_processing` gồm ánh xạ đối tượng, kiểm tra nghiệp vụ, GC và các bước khác.

Mô hình này **không phải công thức đo thời gian chính xác**: driver có thể pipeline hay gộp lệnh, server làm việc song song, thời gian network và execution có thể chồng lấn. Nó chỉ giải thích vì sao tối ưu từ **101 truy vấn xuống 2 truy vấn** có thể đáng giá khi độ trễ mỗi lượt tương đối cao.

Nhưng nếu thay 101 truy vấn bằng một `JOIN` làm kết quả tăng từ 100 lên hàng triệu dòng, chi phí transfer và memory có thể lớn hơn phần RTT tiết kiệm. Do đó cần **tối ưu số lượt cùng với tổng công việc**.

## 2. Đo trước khi sửa: truy vấn, lượt mạng và thời gian giữ kết nối

Trước khi tối ưu, nên có số liệu cho cùng một request hoặc nghiệp vụ:

| Nhóm số liệu | Cần biết | Cách quan sát |
| --- | --- | --- |
| Số thao tác JDBC | Bao nhiêu `executeQuery()`, `executeUpdate()`, `executeBatch()`? | Instrument DAO, tracing hoặc JDBC proxy phù hợp |
| Lượt trao đổi mạng | Driver thực sự gửi bao nhiêu request/nhận bao nhiêu phản hồi? | Driver metrics, tracing mạng hoặc database nếu có |
| Độ trễ từng SQL | Câu nào chiếm p50/p95/p99 cao? | Timer ở DAO kết hợp database query statistics |
| Thời gian mượn/giữ `Connection` | Có chờ pool? Transaction giữ kết nối bao lâu? | Metric `DataSource`/pool và timer |
| Dữ liệu trả về | Bao nhiêu dòng, bao nhiêu byte, có lặp do `JOIN` không? | Đếm dòng/khối lượng, log có kiểm soát |
| Chi phí database | Scan, index, sort, lock wait, CPU, IO | Execution plan và công cụ DBMS |
| Độ ổn định | Timeout, deadlock, rollback, batch failure | SQLState, lỗi driver, metric transaction |

**Đừng dùng mỗi thời gian của `executeQuery()` làm số đo trọn vẹn**: driver có thể chỉ trả cursor ban đầu, còn chi phí fetch xuất hiện trong các lần `ResultSet.next()`. Cũng không nên loại thời gian đợi `getConnection()` khỏi thời gian end-to-end của request nếu người dùng phải chờ cả giai đoạn đó.

Có thể đo nguyên một thao tác JDBC bằng `System.nanoTime()`:

```java
long started = System.nanoTime();
long rowCount = 0;

try (PreparedStatement statement = connection.prepareStatement(sql)) {
    statement.setLong(1, customerId);

    try (ResultSet rs = statement.executeQuery()) {
        while (rs.next()) {
            rowCount++;
            // Đọc cột và ánh xạ DTO tại đây.
        }
    }
} finally {
    long elapsedNanos = System.nanoTime() - started;
    // Ghi elapsedNanos, rowCount và tên thao tác ổn định
    // bằng metrics/log; không ghi tham số nhạy cảm.
}
```

Đoạn minh họa giả định `connection` và `sql` do scope khác quản lý. Khi benchmark, ghi số lần chạy, dữ liệu, driver, phiên bản DB, cấu hình pool, thời gian warm-up, mức đồng thời và cách lấy percentile. Một lần chạy nhanh hơn chưa chứng minh tối ưu có lợi trong production.

## 3. Phát hiện N+1 query khi ánh xạ dữ liệu quan hệ

Giả sử có hai bảng:

```sql
CREATE TABLE customers (
    id BIGINT PRIMARY KEY,
    name VARCHAR(120) NOT NULL,
    status VARCHAR(20) NOT NULL
);

CREATE TABLE orders (
    id BIGINT PRIMARY KEY,
    customer_id BIGINT NOT NULL,
    total DECIMAL(18, 2) NOT NULL,
    FOREIGN KEY (customer_id) REFERENCES customers(id)
);
```

Mục tiêu: lấy các khách hàng đang hoạt động cùng **số đơn hàng** của từng khách.

Một cách viết dễ mắc lỗi N+1 (mã minh họa, không phải chương trình độc lập):

```java
List<Customer> customers = findActiveCustomers(connection);

for (Customer customer : customers) {
    // Mỗi vòng lặp chạy thêm một SELECT COUNT(*).
    long count = countOrdersByCustomerId(
            connection, customer.getId());
    customer.setOrderCount(count);
}
```

Nếu có `N` khách hàng, thường sẽ có **1 + N lượt thực thi SELECT**. Câu truy vấn con có thể dùng chỉ mục rất tốt, nhưng phần overhead lặp lại vẫn tăng theo `N`.

Dấu hiệu nhận biết:

- Log/tracing có hàng chục câu SQL giống nhau, chỉ khác tham số `customer_id`.
- Khi tăng số khách trong response từ 20 lên 200, số query tăng gần tuyến tính.
- Database CPU chưa chắc cao, nhưng latency của request tăng do nhiều lượt chờ.
- Việc đưa `PreparedStatement` ra khỏi vòng lặp giảm chi phí tạo statement, **không tự loại bỏ** N lần thực thi/truyền yêu cầu.

Cần chú ý phân biệt **N+1 vì truy cập dữ liệu từng phần** với N+1 query hợp lý do nghiệp vụ cố ý thao tác tuần tự không thể gom. Chỉ gom các công việc có thể thực hiện độc lập hoặc cùng ngữ nghĩa dữ liệu.

## 4. Cách một: gom vào một truy vấn `JOIN` và `GROUP BY`

Nếu chỉ cần số đơn hàng, database có thể tổng hợp ngay trong một truy vấn:

```sql
SELECT
    c.id,
    c.name,
    COUNT(o.id) AS order_count
FROM customers c
LEFT JOIN orders o ON o.customer_id = c.id
WHERE c.status = ?
GROUP BY c.id, c.name
ORDER BY c.id;
```

Ý nghĩa:

1. `LEFT JOIN` giữ cả khách hàng chưa có đơn.
2. `COUNT(o.id)` trả `0` khi không có đơn; dùng `COUNT(*)` trên `LEFT JOIN` sẽ đếm cả dòng khách hàng không khớp và có thể trả `1` sai.
3. `GROUP BY c.id, c.name` đưa một khách hàng về một dòng kết quả. Các cột được chọn phải phù hợp quy tắc nhóm của DB đang dùng.
4. `ORDER BY` giúp thứ tự ổn định nếu ứng dụng cần; nó cũng có thể tăng chi phí sort.
5. Index trên `orders(customer_id)` thường đáng xem xét; hiệu quả cụ thể phải xác nhận bằng execution plan.

Ví dụ DAO:

```java
import javax.sql.DataSource;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.LinkedHashMap;
import java.util.Map;

public final class CustomerSummaryDao {
    private final DataSource dataSource;

    public CustomerSummaryDao(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public Map<Long, Long> countOrdersForActiveCustomers()
            throws SQLException {

        String sql =
                "SELECT c.id, COUNT(o.id) AS order_count " +
                "FROM customers c " +
                "LEFT JOIN orders o ON o.customer_id = c.id " +
                "WHERE c.status = ? " +
                "GROUP BY c.id " +
                "ORDER BY c.id";

        Map<Long, Long> counts = new LinkedHashMap<>();

        try (Connection connection = dataSource.getConnection();
             PreparedStatement statement =
                     connection.prepareStatement(sql)) {

            statement.setString(1, "ACTIVE");

            try (ResultSet rs = statement.executeQuery()) {
                while (rs.next()) {
                    counts.put(
                            rs.getLong("id"),
                            rs.getLong("order_count"));
                }
            }
        }
        return counts;
    }
}
```

Đoạn Java chỉ chọn `id` và `COUNT`, vì vậy `GROUP BY c.id` phù hợp với những cột không tổng hợp trong `SELECT`; không cần dựa vào quy tắc phụ thuộc hàm của một DB riêng. Ví dụ SQL đầy đủ ở đầu phần có cả `name` nên nhóm theo cả `c.id` và `c.name`.

**Một query không bảo đảm là phương án tối ưu.** Nếu tập khách hàng rất lớn, query vẫn phải nhóm hàng triệu đơn, chuyển nhiều kết quả và có thể cần sort/hash aggregation. Cần kết hợp điều kiện lọc, phân trang và index theo workload.

### Khi cần tổng tiền

Có thể thêm:

```sql
COALESCE(SUM(o.total), 0) AS lifetime_total
```

Khi dùng `LEFT JOIN`, khách không có đơn sẽ có `SUM(o.total) = NULL` nên `COALESCE` trả `0`. Tuy nhiên, kiểu số SQL và `BigDecimal` trên Java phải được kiểm tra; tránh ép sang `double` cho tiền.

## 5. Cách hai: truy vấn hàng loạt theo danh sách khóa

Không phải lúc nào cũng thuận tiện đưa dữ liệu cha và tất cả thông tin con vào một `JOIN`. Có thể dùng hai bước:

1. Truy vấn **một trang khách hàng**.
2. Thu thập ID của trang và truy vấn số đơn hàng cho **toàn bộ ID trong một hoặc vài câu SQL**.

Ví dụ SQL cho ba khách hàng:

```sql
SELECT customer_id, COUNT(*) AS order_count
FROM orders
WHERE customer_id IN (?, ?, ?)
GROUP BY customer_id;
```

Khác N+1, số truy vấn phụ thuộc **số lô ID**, thay vì số ID. Nếu mỗi lô chứa tối đa 200 ID và có 450 khách duy nhất, cần khoảng **3 truy vấn đếm** thay vì 450.

Ví dụ triển khai Java 8+; các ID đi qua placeholder chứ không nối giá trị trực tiếp vào chuỗi SQL:

```java
import javax.sql.DataSource;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Objects;

public final class BulkOrderCountDao {
    private static final int IDS_PER_QUERY = 200;

    private final DataSource dataSource;

    public BulkOrderCountDao(DataSource dataSource) {
        this.dataSource = Objects.requireNonNull(dataSource);
    }

    public Map<Long, Long> countForCustomers(List<Long> customerIds)
            throws SQLException {

        Objects.requireNonNull(customerIds, "customerIds");

        // Loại trùng để không gửi nhiều placeholder vô ích.
        LinkedHashSet<Long> distinct = new LinkedHashSet<>();
        for (Long id : customerIds) {
            distinct.add(Objects.requireNonNull(id, "customer ID"));
        }

        List<Long> ids = new ArrayList<>(distinct);
        Map<Long, Long> counts = new LinkedHashMap<>();
        for (Long id : ids) {
            counts.put(id, 0L); // Khách chưa có đơn vẫn được trả 0.
        }
        if (ids.isEmpty()) {
            return counts;
        }

        try (Connection connection = dataSource.getConnection()) {
            for (int from = 0; from < ids.size();
                    from += IDS_PER_QUERY) {

                int to = Math.min(from + IDS_PER_QUERY, ids.size());
                int size = to - from;

                String placeholders = String.join(
                        ", ", Collections.nCopies(size, "?"));

                String sql =
                        "SELECT customer_id, COUNT(*) AS order_count " +
                        "FROM orders WHERE customer_id IN (" +
                        placeholders + ") GROUP BY customer_id";

                try (PreparedStatement statement =
                             connection.prepareStatement(sql)) {

                    for (int j = from; j < to; j++) {
                        statement.setLong(
                                j - from + 1, ids.get(j));
                    }

                    try (ResultSet rs = statement.executeQuery()) {
                        while (rs.next()) {
                            counts.put(
                                    rs.getLong("customer_id"),
                                    rs.getLong("order_count"));
                        }
                    }
                }
            }
        }

        return counts;
    }
}
```

**Các chi tiết quan trọng:**

- `Collections.nCopies(size, "?")` sinh đúng số placeholder, không nối **giá trị** ID vào SQL. Tên bảng và cột trong câu SQL là hằng do ứng dụng kiểm soát.
- `LinkedHashSet` loại bỏ ID trùng để giảm dữ liệu cần gửi, đồng thời giữ thứ tự xuất hiện. `LinkedHashMap` trả kết quả kể cả ID không có đơn, mặc định `0`.
- Trường hợp danh sách rỗng **không tạo câu SQL `IN ()`** vốn không được hỗ trợ thống nhất giữa các database.
- `IDS_PER_QUERY = 200` chỉ là ví dụ. Số lượng bind parameter tối đa và giới hạn danh sách `IN` thay đổi giữa các database, driver và kiểu câu SQL. Phải đặt giá trị dựa trên sản phẩm, giới hạn thực tế và phép đo.
- Những lô query được chạy trên cùng kết nối trong ví dụ. Nếu ứng dụng cần **ảnh chụp nhất quán** giữa các lô, phải xem transaction/isolation; chỉ tái sử dụng một `Connection` ở chế độ auto-commit không đảm bảo mọi truy vấn đọc cùng snapshot.
- Dù có 3 câu SQL cho 450 ID, số vòng mạng thực tế có thể khác do giao thức driver. Đừng dùng số câu SQL làm thước đo duy nhất.

### `IN` không phải đáp án duy nhất

Với danh sách khóa lớn, các chiến lược khác có thể phù hợp hơn: join với bảng tạm, đưa tập khóa vào bảng staging, table-valued parameter, array binding hoặc phương thức bulk-specific của DB. Những kỹ thuật đó không đồng nhất giữa hệ quản trị và có chi phí thiết lập riêng. So sánh trên khối lượng dữ liệu thật thay vì luôn tăng kích thước `IN`.

## 6. Cẩn thận `JOIN` nhân số hàng và phân trang sai phạm vi

Giảm số truy vấn bằng `JOIN` có thể tạo một vấn đề mới: **nhân bản dòng kết quả**.

Giả sử một khách có 2 đơn hàng và 3 địa chỉ. Nếu cùng join hai quan hệ một-nhiều:

```sql
SELECT c.id, o.id AS order_id, a.id AS address_id
FROM customers c
LEFT JOIN orders o ON o.customer_id = c.id
LEFT JOIN addresses a ON a.customer_id = c.id
WHERE c.id = ?;
```

Kết quả có thể có **2 × 3 = 6 dòng** cho một khách. Nếu cộng `o.total` trực tiếp trên tập join này, mỗi đơn có thể bị tính lặp ba lần. Đây **không phải** cách tối ưu N+1 hợp lệ nếu kết quả sai.

Các lựa chọn:

- **Pre-aggregate** từng tập con theo `customer_id` trong query/subquery trước khi join.
- Truy vấn cha một lần, rồi **bulk load** đơn và địa chỉ bằng **hai query** theo tập ID.
- Nếu thực sự cần ánh xạ nhiều quan hệ từ join, dùng identity map và tập ID để **tránh tạo đối tượng con trùng**, nhưng vẫn phải tính chi phí mạng của số dòng nhân lên.
- Nếu chỉ cần `COUNT` hoặc `SUM`, ưu tiên tổng hợp ngay trong SQL thay vì lấy toàn bộ chi tiết về Java.

**Phân trang là điểm dễ mắc lỗi:** nếu áp `LIMIT`/`FETCH FIRST` trực tiếp lên các dòng join cha–con, giới hạn có thể cắt ngang tập con của một khách hoặc trả ít khách hơn mong muốn. Cách đáng tin cậy là **xác định trang khách hàng trước**, sau đó bulk load các bản ghi con của chính trang đó. Cú pháp phân trang (`LIMIT`, `OFFSET`, `FETCH FIRST` hoặc keyset pagination) thay đổi giữa hệ quản trị.

Một ứng dụng có yêu cầu “20 khách trên mỗi trang” cần phân trang **20 khách**, không phải 20 hàng vật lý của phép join.

## 7. Đưa phép biến đổi vào một câu SQL thay vì đọc–tính–ghi

Một kiểu tốn lượt trao đổi thường gặp:

```text
SELECT available FROM inventory WHERE product_id = ?
       ↓
Java: newAvailable = available - quantity
       ↓
UPDATE inventory SET available = ? WHERE product_id = ?
```

Nó cần đọc rồi ghi và còn dễ mắc **lost update** khi nhiều transaction cùng tính trên số lượng cũ.

Thay thế bằng SQL tường minh có điều kiện:

```sql
UPDATE inventory
SET available = available - ?
WHERE product_id = ? AND available >= ?;
```

Ví dụ Java:

```java
public boolean reserve(
        Connection connection, long productId, int quantity)
        throws SQLException {

    if (quantity <= 0) {
        throw new IllegalArgumentException("quantity must be positive");
    }

    String sql =
            "UPDATE inventory SET available = available - ? " +
            "WHERE product_id = ? AND available >= ?";

    try (PreparedStatement statement =
                 connection.prepareStatement(sql)) {

        statement.setInt(1, quantity);
        statement.setLong(2, productId);
        statement.setInt(3, quantity);

        int updated = statement.executeUpdate();
        if (updated > 1) {
            throw new SQLException(
                    "Expected at most one inventory row, got " + updated);
        }
        return updated == 1;
    }
}
```

Hàm minh họa nằm trong DAO nhận `Connection` do tầng gọi sở hữu. Nó chỉ cần **một câu SQL ghi**, đồng thời điều kiện tồn kho được server kiểm tra khi thực thi. `false` có thể nghĩa sản phẩm không tồn tại **hoặc không đủ hàng**; nếu nghiệp vụ phải phân biệt, cần thêm hợp đồng kết quả phù hợp.

Kỹ thuật `UPDATE ... SET value = value + ?` hoặc `DELETE ... WHERE ...` có điều kiện thường làm giảm số câu SQL **và** giúp biểu đạt rõ bất biến nghiệp vụ. Tuy vậy, khóa, mức cô lập và các ràng buộc khác vẫn phải được đánh giá nếu thao tác liên quan nhiều hàng/bảng.

## 8. `PreparedStatement.addBatch()` và `executeBatch()` giải quyết vấn đề nào?

Khi cần ghi nhiều hàng, JDBC cho phép đưa nhiều bộ tham số vào một statement rồi thực thi theo **batch**:

```text
Cách riêng lẻ:
  set params #1 → executeUpdate()
  set params #2 → executeUpdate()
  ...
  set params #100 → executeUpdate()

Cách batch:
  set params #1 → addBatch()
  set params #2 → addBatch()
  ...
  set params #100 → addBatch()
  executeBatch()
```

API chính:

| Phương thức | Vai trò | Điều không nên suy diễn |
| --- | --- | --- |
| `PreparedStatement.addBatch()` | Ghi nhận một bộ tham số cho statement đã chuẩn bị | Không có nghĩa hàng đã được ghi xuống database ngay |
| `PreparedStatement.executeBatch()` | Yêu cầu thực thi các bộ lệnh đã thêm | Không tự bảo đảm một transaction nguyên tử hoặc một lượt mạng |
| `PreparedStatement.clearBatch()` | Xóa các lệnh batch đang được tích lũy | Không hoàn tác những lệnh đã thực thi |
| `BatchUpdateException.getUpdateCounts()` | Thông tin số hàng tác động của các phần tử batch đã được báo | Không luôn cho biết chính xác mọi phần tử đã chạy khi có lỗi |
| `Statement.SUCCESS_NO_INFO` | Thành công nhưng không biết số hàng tác động | Không được coi là thất bại |
| `Statement.EXECUTE_FAILED` | Một phần tử thất bại khi driver báo kết quả theo dạng này | Không tự làm rollback tất cả phần tử khác |

`executeBatch()` thường có cơ hội giảm số lượt trao đổi và overhead so với gọi `executeUpdate()` cho từng phần tử, nhưng **mức giảm thực tế phụ thuộc driver và cấu hình**: driver có thể rewrite batch thành multi-row `INSERT`, pipeline các lệnh, gửi nhiều request hay giữ nguyên một số vòng trao đổi.

**Batch update không phải công cụ tiêu chuẩn để gộp nhiều `SELECT` rồi lấy nhiều `ResultSet` độc lập.** `executeBatch()` được thiết kế cho các lệnh cập nhật và trả update counts; với nhu cầu đọc N khách, hãy dùng `JOIN`, truy vấn tổng hợp, `IN`/bulk load hoặc API riêng của database khi phù hợp.

## 9. Ví dụ thực tế: chèn audit events theo lô trong một transaction

Giả sử ứng dụng cần ghi nhiều sự kiện audit sau khi nhập dữ liệu. Bảng đơn giản:

```sql
CREATE TABLE order_audit (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    order_id BIGINT NOT NULL,
    event_type VARCHAR(40) NOT NULL
);
```

Cú pháp sinh khóa `GENERATED ALWAYS AS IDENTITY` có thể cần điều chỉnh theo phiên bản và hệ quản trị; phần Java dưới đây **không cần lấy ID tự sinh**. Cần dùng bảng giao dịch và kiểu dữ liệu phù hợp DB thực.

Ví dụ Java 8+ sử dụng một `DataSource`, một `Connection`, `PreparedStatement` tái sử dụng và flush lô 200 sự kiện:

```java
import javax.sql.DataSource;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;
import java.sql.Statement;
import java.util.List;
import java.util.Objects;

public final class AuditBatchDao {
    private static final int BATCH_SIZE = 200;
    private final DataSource dataSource;

    public AuditBatchDao(DataSource dataSource) {
        this.dataSource = Objects.requireNonNull(dataSource);
    }

    public void insertAll(List<AuditEvent> events) throws SQLException {
        Objects.requireNonNull(events, "events");
        if (events.isEmpty()) {
            return;
        }

        String sql =
                "INSERT INTO order_audit (order_id, event_type) " +
                "VALUES (?, ?)";

        try (Connection connection = dataSource.getConnection()) {
            boolean originalAutoCommit = connection.getAutoCommit();

            // DAO này tự sở hữu transaction; không tham gia
            // vào một transaction đã được bên khác quản lý.
            if (!originalAutoCommit) {
                throw new SQLException(
                        "Expected autoCommit=true at DAO transaction boundary");
            }

            connection.setAutoCommit(false);
            boolean transactionEnded = false;
            Throwable primaryFailure = null;

            try {
                try (PreparedStatement statement =
                             connection.prepareStatement(sql)) {

                    int queued = 0;

                    for (AuditEvent event : events) {
                        Objects.requireNonNull(event, "event");
                        Objects.requireNonNull(
                                event.type, "event type");

                        statement.setLong(1, event.orderId);
                        statement.setString(2, event.type);
                        statement.addBatch();
                        queued++;

                        if (queued == BATCH_SIZE) {
                            checkBatch(statement.executeBatch(), queued);
                            statement.clearBatch();
                            queued = 0;
                        }
                    }

                    if (queued > 0) {
                        checkBatch(statement.executeBatch(), queued);
                        statement.clearBatch();
                    }
                }

                connection.commit();
                transactionEnded = true;

            } catch (SQLException | RuntimeException | Error failure) {
                primaryFailure = failure;

                try {
                    connection.rollback();
                    transactionEnded = true;
                } catch (SQLException rollbackFailure) {
                    failure.addSuppressed(rollbackFailure);
                }

                throw failure;

            } finally {
                // Không tự chuyển autoCommit sang true nếu
                // rollback thất bại và transaction chưa rõ trạng thái.
                if (transactionEnded) {
                    try {
                        connection.setAutoCommit(originalAutoCommit);
                    } catch (SQLException restoreFailure) {
                        if (primaryFailure != null) {
                            primaryFailure.addSuppressed(restoreFailure);
                        } else {
                            throw restoreFailure;
                        }
                    }
                }
            }
        }
    }

    private static void checkBatch(int[] counts, int queued)
            throws SQLException {
        if (counts.length != queued) {
            throw new SQLException("Unexpected batch update count length");
        }

        for (int count : counts) {
            if (count == Statement.EXECUTE_FAILED) {
                throw new SQLException("One batch command failed");
            }
            // SUCCESS_NO_INFO (-2) được chấp nhận:
            // thành công nhưng không biết số hàng bị tác động.
        }
    }

    public static final class AuditEvent {
        public final long orderId;
        public final String type;

        public AuditEvent(long orderId, String type) {
            this.orderId = orderId;
            this.type = type;
        }
    }
}
```

Ví dụ gọi:

```java
List<AuditBatchDao.AuditEvent> events = Arrays.asList(
        new AuditBatchDao.AuditEvent(101L, "CREATED"),
        new AuditBatchDao.AuditEvent(102L, "PAID"),
        new AuditBatchDao.AuditEvent(103L, "SHIPPED"));

new AuditBatchDao(dataSource).insertAll(events);
```

Đoạn gọi cần import `java.util.List` và `java.util.Arrays`, giả định `dataSource` đã được cấu hình. Mã DAO ở trên là ví dụ minh họa **quản lý transaction độc lập**; nếu service đang quản lý transaction bao trùm nhiều DAO, hãy tách helper nhận `Connection` và để service quyết định `commit()`/`rollback()`, thay vì mỗi DAO tự mở transaction.

### Điều ví dụ bảo đảm và điều cần tự kiểm chứng

- **Giảm số lần `executeBatch()`:** 450 sự kiện sẽ tạo các lần flush kích thước 200, 200 và 50. Các `addBatch()` chỉ tích lũy tham số, không được xem là 450 lệnh đã commit.
- **Giới hạn bộ nhớ:** mỗi lần flush có tối đa 200 bộ tham số ở phía JDBC thay vì giữ toàn bộ sự kiện trong một batch rất lớn. Danh sách `events` đầu vào vẫn có thể lớn; dữ liệu stream có thể cần xử lý từng trang hoặc iterator có hợp đồng rõ.
- **Transaction chủ động:** cả ba lần `executeBatch()` dùng cùng một connection và chỉ `commit()` sau khi tất cả thành công. Khi có `SQLException`, mã cố rollback toàn bộ thay đổi chưa commit.
- **`clearBatch()` sau flush:** giúp vòng tiếp theo không mang theo các lệnh đã chạy; không phải thao tác rollback.
- **Update counts:** trên đường thành công, JDBC trả mảng thông tin từng lệnh; `SUCCESS_NO_INFO` vẫn có thể là thành công. Nếu nghiệp vụ đòi **đúng một hàng cho mỗi UPDATE**, `SUCCESS_NO_INFO` không cung cấp đủ bằng chứng và cần lựa chọn khác hoặc kiểm chứng hậu điều kiện.
- **Khả năng driver hỗ trợ:** nên kiểm tra `DatabaseMetaData.supportsBatchUpdates()` và chạy kiểm thử tích hợp; metadata `true` không chứng minh mọi batch trong mọi bảng có cùng hiệu năng/giá trị count.
- **Lỗi rollback:** nếu `rollback()` thất bại, `setAutoCommit(true)` không được gọi vô điều kiện vì có thể commit transaction đang mở. Pool cần cơ chế loại bỏ kết nối không rõ trạng thái; `close()` trên proxy pool không tự là bằng chứng kết nối vật lý đã được loại bỏ.
- **Lỗi commit/restore:** một `SQLException` sau khi server commit có thể để lại trạng thái kết quả nghiệp vụ **chưa chắc chắn**. Không retry tất cả sự kiện chỉ vì client nhận ngoại lệ, nếu chưa có idempotency hoặc đối soát.

Một batch lớn không có nghĩa transaction phải quá lớn. Nếu nghiệp vụ cho phép **commit từng phần**, có thể tách thành nhiều transaction nhỏ và theo dõi checkpoint; nhưng đó là **thay đổi ngữ nghĩa nghiệp vụ**, không phải chỉ là chỉnh `BATCH_SIZE`. Nếu yêu cầu tất cả hoặc không có gì, các flush trong ví dụ phải ở cùng transaction như đã viết.

## 10. Khi batch chứa `UPDATE` có điều kiện: không bỏ qua ý nghĩa số hàng

Với câu:

```sql
UPDATE inventory
SET available = available - ?
WHERE product_id = ? AND available >= ?;
```

Nếu cập nhật từng sản phẩm, `executeUpdate()` trả `1` hoặc `0` để báo có giữ được hàng. Nếu đưa nhiều câu tương tự vào batch, kết quả có thể bao gồm:

```text
1             → thường là một hàng đã được cập nhật
0             → không có hàng khớp điều kiện
SUCCESS_NO_INFO (-2) → thành công nhưng không biết số hàng
EXECUTE_FAILED (-3)  → lệnh thất bại (trong những đường driver báo)
```

Vì vậy, **đừng dùng cùng chính sách đọc counts cho mọi loại batch**:

- Với **audit INSERT** ở phần 9, mục tiêu là ghi các hàng; `SUCCESS_NO_INFO` có thể được chấp nhận nếu driver báo thành công và transaction commit.
- Với **giữ tồn kho**, service cần xác nhận từng dòng có được cập nhật hay không. `SUCCESS_NO_INFO` không thể thay thế kết quả `1`. Có thể chọn SQL tập hợp khác, yêu cầu driver cung cấp counts đáng tin cậy, dùng cập nhật từng dòng có điều kiện trong một transaction, hoặc kiểm tra hậu điều kiện trước commit.
- Với thao tác **idempotent**, `0` đôi khi là kết quả hợp lệ; với thao tác phải tồn tại hàng, `0` có thể là lỗi. Quyết định phụ thuộc hợp đồng nghiệp vụ.

Nếu `executeBatch()` ném `BatchUpdateException`, `getUpdateCounts()` có thể chỉ chứa phần trước lỗi khi driver dừng, hoặc có kết quả cho các phần tử khác khi driver tiếp tục. **Không được suy rằng toàn batch chưa thực thi**. Khi cần nguyên tử, thực hiện rollback theo transaction và kiểm tra lỗi rollback; nếu trạng thái commit chưa rõ, dùng đối soát/idempotency trước retry.

## 11. Batch size: tối ưu theo chi phí và rủi ro, không có con số kỳ diệu

Kích thước batch có các đánh đổi:

| Batch rất nhỏ | Batch vừa phải | Batch quá lớn |
| --- | --- | --- |
| Nhiều lần `executeBatch()`, overhead lớn | Cân bằng chi phí truyền và bộ nhớ | Ít lần gọi, nhưng có thể tốn nhiều memory/packet |
| Dễ cô lập phần tử lỗi | Có thể kiểm tra từng nhóm | Lỗi khó chẩn đoán và xử lý hơn |
| Transaction có thể kéo dài do nhiều lượt mạng | Dễ đo độ trễ từng lô | Có thể tăng lock duration hoặc giữ transaction rất lâu |
| Áp lực server mỗi lần nhỏ | Giảm overhead mà không dồn toàn bộ tải | Driver/server có giới hạn kích thước packet/parameter |

Một thí nghiệm nên so sánh các giá trị, ví dụ **20, 100, 200, 500, 1.000** phần tử mỗi batch — đây chỉ là các điểm đo, không phải khuyến nghị chung.

Các yếu tố làm kích thước tốt nhất thay đổi:

1. **Độ rộng của mỗi hàng:** một batch chứa nhiều chuỗi dài/LOB chiếm bộ nhớ và băng thông lớn hơn batch gồm hai số nguyên.
2. **Driver và cách rewrite:** có driver tối ưu multi-values `INSERT` hoặc pipeline; có driver vẫn gửi nhiều lệnh nhỏ.
3. **Giới hạn database/protocol:** số bind parameter, kích thước packet, transaction log, thời gian khóa, giới hạn số hàng.
4. **Mạng:** RTT cao thường làm giảm số lượt trao đổi hữu ích, nhưng chi phí truyền một payload lớn vẫn đáng kể.
5. **Yêu cầu atomicity:** một transaction gồm hàng trăm nghìn thao tác có thể giữ tài nguyên quá lâu dù flush từng nhóm nhỏ.
6. **Xử lý lỗi và khả năng retry:** lô lớn làm việc xác định phần đã thực thi, đối soát và retry phức tạp hơn.
7. **Tải đồng thời:** một batch đơn lẻ nhanh hơn chưa chắc khiến throughput toàn database cao hơn khi có nhiều writer cạnh tranh.

Tối ưu batch size là một **phép đo dưới tải đại diện**, không phải quy tắc “batch càng lớn càng nhanh”. Dùng biểu đồ throughput, p95/p99, số lần flush, memory, thời gian giữ connection, lock wait và lỗi.

### Batch và prepared statement caching

Tái sử dụng **cùng một `PreparedStatement` trong một batch** thường tránh phải tạo statement mới ở mỗi vòng lặp phía Java. Một số driver hoặc connection pool có cơ chế cache prepared statement, nhưng không nên mặc định chúng được bật hoặc có cùng tác động với `addBatch()`.

Tạo statement một lần trong vòng lặp mà vẫn gọi `executeUpdate()` từng phần tử sẽ giảm **chi phí chuẩn bị statement** ở client, nhưng có thể vẫn giữ **N lần thực thi**. Batch giải quyết một phần khác: cho driver cơ hội gộp/điều phối việc thực thi nhiều bộ tham số.

## 12. Khi nào nên dùng SQL tập hợp thay vì JDBC batch?

Nếu nhiều dòng có thể được xử lý bằng **một điều kiện hoặc biểu thức SQL duy nhất**, câu DML dạng tập hợp thường đáng thử trước.

Ví dụ, thay vì đọc từng đơn hàng quá hạn rồi cập nhật từng hàng:

```text
SELECT id FROM orders WHERE status = 'PENDING' AND expires_at < ?
UPDATE orders SET status = 'EXPIRED' WHERE id = ?
UPDATE orders SET status = 'EXPIRED' WHERE id = ?
...
```

Có thể dùng:

```sql
UPDATE orders
SET status = 'EXPIRED'
WHERE status = 'PENDING' AND expires_at < ?;
```

Đây là một câu SQL **set-based**, không phải một `PreparedStatement` batch gồm nhiều lệnh. Nó có các lợi thế tiềm năng:

- Bớt một lần đọc ID và một loạt lần cập nhật riêng.
- Database có thể tối ưu truy vấn/lọc bằng index phù hợp.
- Điều kiện `WHERE` được kiểm tra tại thời điểm ghi, giúp tránh việc Java dùng tập ID đã cũ.
- `executeUpdate()` trả tổng số hàng bị tác động, hữu ích cho thống kê nghiệp vụ.

Nhưng cần lưu ý:

- Nếu mỗi hàng phải cập nhật **giá trị khác nhau**, một `UPDATE` đơn giản có thể không đủ; dùng batch, `CASE`, join với staging table hoặc cơ chế bulk của DB.
- Một lệnh set-based chạm quá nhiều hàng có thể giữ khóa lâu, tạo log lớn và tăng tải. Có thể chia phạm vi theo khóa hoặc thời gian nếu nghiệp vụ cho phép.
- Nếu có trigger, cascade hoặc quy tắc phức tạp, một câu lớn không tự đồng nghĩa nhẹ hơn nhiều lệnh nhỏ.
- Câu SQL trả row count **tổng**, không cho biết mọi kết quả chi tiết theo ID nếu cần phân biệt từng hàng.

Một cách phân loại:

| Nhu cầu | Hướng triển khai thường nên thử |
| --- | --- |
| Một điều kiện áp dụng cho nhiều hàng | Một câu `UPDATE/DELETE ... WHERE ...` dạng tập hợp |
| Tổng hợp hoặc đếm nhiều hàng | `GROUP BY`, aggregate, pre-aggregation |
| Nhiều ID cần truy vấn cùng loại | `IN` có phân lô, bulk load hoặc join với bảng staging |
| Nhiều `INSERT` với cùng cấu trúc | `PreparedStatement.addBatch()/executeBatch()` |
| Nhiều `UPDATE` có bộ tham số riêng | JDBC batch nếu update counts/atomicity phù hợp |
| Nhiều thao tác cần quyết định theo thứ tự | Transaction và SQL có điều kiện; không ép batch nếu làm sai quy tắc |

## 13. Đừng giảm round trip bằng cách chuyển quá nhiều dữ liệu

Các “tối ưu” có thể phản tác dụng:

### `SELECT *` lấy dữ liệu không dùng

```sql
SELECT *
FROM orders
WHERE customer_id = ?;
```

Nếu tầng gọi chỉ cần `id` và `status`, nên chọn hai cột đó thay vì cả LOB, mô tả dài và metadata không cần thiết. Ít query hơn nhưng nhiều byte hơn vẫn có thể chậm.

### Gom tất cả quan hệ vào một `JOIN`

Một join nhiều quan hệ 1-N có thể gây **row multiplication**. Nếu một đơn có 50 items và 10 shipment events, một join trực tiếp có thể tạo tới 500 dòng cho cùng đơn. Hai query bulk trên hai tập con có thể nhẹ hơn một query phình lớn.

### Dùng `IN` với hàng chục nghìn tham số

Có thể vượt giới hạn bind, tăng chi phí parse/plan hoặc tạo SQL dài khó cache. Nên phân trang ID, dùng tập tham số phù hợp, staging/table-valued parameter hoặc cơ chế bulk của DB khi đáng giá.

### Không phân trang kết quả

Một lần `SELECT` trả hàng triệu dòng có thể chiếm nhiều bộ nhớ JVM, giữ `ResultSet`/connection lâu và làm pool cạn. Hãy phân trang ở cấp bản ghi nghiệp vụ (ví dụ khách hàng trước khi join các đơn) hoặc stream có kiểm soát.

### Nhầm `setFetchSize()` với JDBC write batch

`Statement.setFetchSize(int)` là **gợi ý về số dòng driver nên fetch mỗi đợt** cho `ResultSet`; nó không phải `PreparedStatement.addBatch()` và không có nghĩa driver nhất định giảm số lượt mạng. Một số driver yêu cầu cấu hình transaction/cursor để fetch theo từng đợt, số khác có thể bỏ qua gợi ý.

Nếu cần xử lý kết quả lớn, kiểm tra `ResultSet` type, fetch size, hành vi cursor, `autoCommit` và độ trễ khi duyệt `next()`; đừng suy từ `setFetchSize(500)` rằng chỉ còn đúng một lượt mạng cho 500 dòng.

## 14. Transaction, connection pool và giới hạn thời gian

Tối ưu round trip không thể tách khỏi quản lý connection:

- **Một connection cho một transaction:** tất cả câu SQL thuộc cùng nghiệp vụ nguyên tử phải dùng cùng `Connection`. Không mở kết nối mới cho mỗi hàng trong vòng lặp.
- **Không giữ connection quá lâu:** lấy connection ngay trước phần SQL và đóng/trả về pool khi xong. Đừng gọi API mạng bên ngoài hoặc đợi người dùng tương tác trong khi giữ connection nếu không cần thiết.
- **Flush batch không đồng nghĩa commit:** `executeBatch()` gửi lệnh thực thi, còn transaction vẫn chưa hoàn tất khi `autoCommit=false`. Điều này cho phép rollback cả các batch trước đó nếu cùng transaction.
- **Commit theo ranh giới nghiệp vụ:** không tự tách transaction chỉ để đạt benchmark. Commit từng lô là thay đổi semantics nếu yêu cầu “all or nothing”.
- **Giới hạn thời gian:** một batch hoặc query khổng lồ có thể vượt timeout, giữ khóa và tài nguyên lâu. Dùng cùng request deadline cho mỗi thao tác, xem `setQueryTimeout()`, giới hạn server và policy của pool, nhưng không coi hủy query là bằng chứng rollback.
- **Lỗi kết nối sau ghi:** nếu mạng hỏng ngay sau `INSERT`/`COMMIT`, client có thể không biết server đã ghi hay chưa. Không tự lặp batch khi chưa có idempotency hoặc đối soát.
- **Phục hồi trạng thái connection:** nếu tự đổi `autoCommit` hoặc isolation, kết thúc transaction bằng `commit()`/`rollback()` trước khi phục hồi. Nếu rollback lỗi, kết nối có thể không an toàn để tái sử dụng.

Kích thước pool lớn hơn không giải quyết được N+1 hay query thiếu index. Nếu mỗi request giữ connection qua 100 query nhỏ, pool dễ bão hòa và khiến các request sau chờ mượn, dù CPU database chưa đạt ngưỡng.

### Round trip và transaction đồng thời

Hai batch có cùng số dòng có thể cho kết quả thời gian rất khác nếu nhiều transaction tranh chấp cùng hàng hoặc chỉ mục. Mỗi phép đo nên ghi cả **mức đồng thời**, lock wait, transaction abort và số connection active/pending. Một tối ưu giảm RTT nhưng tăng khóa có thể làm **p99 xấu hơn**.

## 15. Các bẫy khi đọc generated keys và batch results

Nếu một batch `INSERT` tạo khóa chính do database sinh, có thể yêu cầu:

```java
PreparedStatement statement = connection.prepareStatement(
        "INSERT INTO customers (name) VALUES (?)",
        Statement.RETURN_GENERATED_KEYS);
```

Sau `executeBatch()`, `statement.getGeneratedKeys()` có thể cung cấp khóa sinh theo hỗ trợ của driver và loại SQL. Nhưng **không mặc định mỗi phần tử input có đúng một khóa tương ứng theo thứ tự input** nếu driver chưa cam kết. Khi rewrite một batch thành multi-row `INSERT`, cách trả khóa và update counts có thể thay đổi.

Nếu nghiệp vụ phải liên kết đơn hàng với ID sinh ra từ từng `INSERT`, cần kiểm thử số lượng, thứ tự và kiểu khóa trên **driver/database cụ thể**, hoặc chọn chiến lược phát sinh ID trước khi chèn hoặc cú pháp SQL có `RETURNING` tương ứng. Đừng gán nhầm khóa do giả định “dòng thứ i thuộc item thứ i” mà không kiểm chứng.

Khi batch bị lỗi:

1. Bắt `BatchUpdateException` nếu cần thông tin theo phần tử.
2. Đọc `getUpdateCounts()` và `getNextException()`; có thể có cập nhật trước lỗi.
3. Xác định transaction đã commit hay chưa và cố rollback nếu đang sở hữu transaction.
4. Không gửi lại **toàn batch** theo mặc định.
5. Ghi log tên thao tác và số phần tử/lô, SQLState/vendor code nhưng **không đưa tham số nhạy cảm** vào log công khai.

Đặc biệt, `Statement.SUCCESS_NO_INFO` mang nghĩa **thành công nhưng không biết số dòng**; đừng nhầm nó với `Statement.EXECUTE_FAILED`. Nếu yêu cầu nghiệp vụ phụ thuộc “đã cập nhật chính xác một hàng”, hãy kiểm tra tính khả dụng của update count theo driver và thiết kế phương án thay thế.

## 16. Kịch bản đánh giá: từ N+1 sang truy vấn tổng hợp, từ lệnh lẻ sang batch

Giả sử endpoint hiển thị 120 khách hàng và nhận 500 sự kiện audit để ghi. Một triển khai ban đầu:

```text
Đọc khách hàng:             1 SELECT
Đếm đơn của từng khách:   120 SELECT
Chèn audit từng sự kiện:  500 INSERT/executeUpdate
-----------------------------------------------
Tổng lệnh SQL thực thi:   621
```

Một thiết kế khác:

```text
Đọc khách và đếm đơn:      1 SELECT JOIN/GROUP BY
Chèn audit theo 200:       3 executeBatch calls
-----------------------------------------------
Tổng lời gọi thực thi:     4
```

**Đây là phép đếm lời gọi ở tầng Java, không phải phép đo số round trip thực tế.** Ba `executeBatch()` có thể được driver thực hiện thành nhiều request mạng; query tổng hợp có thể làm việc nhiều hơn một `SELECT` đơn giản; và nếu ghi audit và truy vấn dùng transaction khác nhau, cần xác nhận ranh giới nghiệp vụ.

Các bước benchmark có giá trị:

1. Dùng cùng dữ liệu thử nghiệm với 120, 1.200 và 12.000 khách; xem query aggregate có còn phù hợp không.
2. Với audit, đo `executeUpdate()` từng dòng so với batch size 20, 100, 200, 500.
3. Đo cả **thời gian hoàn tất request, throughput và p95/p99**, số query, network RTT, bytes trả về, DB CPU/IO và lock wait.
4. Chạy dưới tải đồng thời và các trạng thái pool có `active/idle/pending` khác nhau.
5. Thử lỗi duplicate key ở giữa batch và xác nhận transaction rollback đúng.
6. Thử thao tác có `SUCCESS_NO_INFO` và kiểm tra quyết định nghiệp vụ có phụ thuộc số dòng chính xác hay không.
7. Ghi driver/version và cấu hình batch rewrite (nếu có); không chuyển kết luận sang database khác bằng suy đoán.

Một thay đổi chỉ nên được xem là cải thiện khi **cùng ngữ nghĩa và tính đúng**, không khiến bộ nhớ, tải DB hoặc tỷ lệ lỗi tăng ngoài mức chấp nhận.

## 17. Checklist ra quyết định

| Câu hỏi | Hành động thực tế |
| --- | --- |
| Có N+1 query không? | Tracing theo request, đếm số query và tham số khác nhau |
| Có thể dùng một aggregate không? | `GROUP BY`/`COUNT`/`SUM`, kiểm tra index và execution plan |
| JOIN có nhân số dòng không? | Kiểm tra quan hệ 1-N, pre-aggregate hoặc bulk load theo tập khóa |
| Có cần lấy dữ liệu theo nhiều ID? | Dùng `IN` phân lô hoặc join với staging, không nối giá trị vào SQL |
| Nhiều hàng có chung biểu thức cập nhật? | Ưu tiên DML set-based `UPDATE/DELETE ... WHERE ...` nếu phù hợp |
| Nhiều bộ tham số cho cùng cấu trúc SQL? | Dùng `PreparedStatement.addBatch()/executeBatch()`, đo batch size |
| Kết quả từng phần tử có quan trọng? | Xem update counts, `SUCCESS_NO_INFO`, generated keys và trường hợp rollback |
| Nghiệp vụ cần atomicity? | Giữ các lô trong cùng transaction; rollback toàn bộ khi lỗi |
| Kết quả hoặc dữ liệu quá lớn? | Projection, phân trang theo cha, streaming/fetch size có kiểm chứng |
| Có thực sự giảm latency không? | Đo p95/p99, throughput, bytes, DB work, lock và pool dưới tải thực |
| Có rủi ro retry ghi trùng không? | Idempotency, đối soát, giữ lỗi gốc khi commit/batch không rõ trạng thái |
| Driver có hỗ trợ tối ưu cần dùng? | Kiểm tra tài liệu và integration test đúng phiên bản |

### Bài thực hành

1. Tạo bảng `customers` và `orders` như phần 3, nạp ít nhất 100 khách và một số đơn cho mỗi khách.
2. Viết phiên bản N+1: truy vấn danh sách khách rồi đếm đơn từng khách. Đếm số `executeQuery()` và thời gian end-to-end.
3. Viết phiên bản `LEFT JOIN + GROUP BY`, đối chiếu kết quả với N+1, đặc biệt khách **không có đơn**.
4. Viết phiên bản truy vấn theo lô `IN` cho một trang khách. Thử danh sách trống, danh sách có ID trùng và kích thước vượt một lô.
5. Viết DAO chèn audit một dòng mỗi lần, sau đó dùng `addBatch()/executeBatch()` với batch size 20, 100, 200.
6. Chèn một giá trị vi phạm constraint ở giữa batch, kiểm tra `BatchUpdateException` và xác minh rollback trên database thật.
7. Đổi sang câu `UPDATE` set-based cho một nhóm đơn hàng, so sánh số lệnh với batch update từng ID.
8. Đo p95/p99 và DB load dưới ít nhất hai mức đồng thời. Trình bày trường hợp số lệnh giảm nhưng thời gian **không giảm** do kết quả JOIN lớn hoặc lock wait.

### Câu hỏi tự kiểm tra

- Giảm từ 100 lần `executeUpdate()` xuống một `executeBatch()` có bảo đảm đúng một round trip mạng không?
- Vì sao `COUNT(*)` trên `LEFT JOIN` có thể cho kết quả sai với khách không có đơn?
- Tại sao `PreparedStatement` được tái sử dụng trong vòng lặp vẫn chưa loại bỏ N+1 query?
- Khi nào hai truy vấn bulk tốt hơn một `JOIN` lớn?
- `SUCCESS_NO_INFO` có cho phép khẳng định chính xác một hàng được `UPDATE` không?
- Nếu `executeBatch()` thất bại ở phần tử thứ 50, có thể gửi lại 100 phần tử như chưa có gì xảy ra không?
- Khi nào một câu `UPDATE ... WHERE ...` tốt hơn vòng `SELECT` rồi cập nhật trong Java?
- Vì sao nên đo thời gian giữ connection và lock wait trước khi tăng `maximumPoolSize`?

## 18. Tổng kết

1. **Ưu tiên loại bỏ N+1 query** bằng `JOIN`/aggregate hoặc bulk load theo danh sách khóa, nhưng phải kiểm tra row multiplication, giới hạn tham số và phân trang.
2. **Dùng SQL dạng tập hợp** khi nhiều hàng có cùng điều kiện hoặc biểu thức cập nhật. Nó có thể vừa giảm lượt trao đổi vừa bảo vệ điều kiện ở thời điểm ghi.
3. **Dùng JDBC batch cho nhiều bộ tham số của cùng DML**. `addBatch()` tích lũy, `executeBatch()` thực thi; khả năng giảm round trip phụ thuộc driver.
4. **Điều chỉnh batch size bằng đo đạc**. Không tự chọn batch càng lớn càng tốt; cần cân bằng bộ nhớ, timeout, log, lock và khả năng xử lý lỗi.
5. **Bảo toàn tính đúng của transaction**. Batch flush không phải commit; khi có lỗi phải xử lý rollback và trạng thái chưa rõ trước khi retry.
6. **Đọc đúng update counts và generated keys**. Không suy từ `SUCCESS_NO_INFO` ra số hàng chính xác hoặc từ batch ra thứ tự khóa không được driver cam kết.
7. **Đo toàn bộ request và tải DB**. Một tối ưu đáng giữ phải cải thiện latency/throughput mà vẫn đúng nghiệp vụ và không gây nghẽn connection pool, CPU, mạng hoặc khóa.

**Kết luận:** trong JDBC, giảm số lượt trao đổi có hiệu quả nhất khi **chuyển các thao tác nhỏ lặp lại thành SQL tập hợp hoặc những batch có kích thước hợp lý**, đồng thời giữ được kiểm soát lỗi, transaction và khối lượng dữ liệu. Đừng tối ưu theo số lời gọi Java đơn thuần: hãy xác nhận kết quả đúng và đo p95/p99, số round trip thực tế, tài nguyên database và hành vi dưới tải.
