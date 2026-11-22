# Chỉ mục hỗ trợ sắp xếp và truy vấn chỉ đọc các trường cần thiết

Một chỉ mục (index) không chỉ giúp cơ sở dữ liệu tìm những bản ghi thỏa mãn điều kiện `WHERE`. Khi thứ tự trong chỉ mục phù hợp với `ORDER BY`, hệ quản trị có thể trả kết quả theo thứ tự mong muốn mà không phải sắp xếp lại toàn bộ tập bản ghi. Nếu chỉ mục đồng thời chứa mọi cột cần để lọc, sắp xếp và trả về kết quả, truy vấn còn có cơ hội đọc dữ liệu trực tiếp từ chỉ mục, hạn chế truy cập bảng gốc.

Hai kỹ thuật này đặc biệt hữu ích cho màn hình danh sách, lịch sử giao dịch, bảng điều khiển và các API Java đọc một số lượng nhỏ bản ghi mới nhất từ một tập dữ liệu lớn. Chúng liên quan nhưng không đồng nhất:

- **Đọc theo thứ tự chỉ mục (index-ordered scan):** tận dụng thứ tự khóa để giảm hoặc loại bỏ thao tác `Sort`.
- **Truy vấn được chỉ mục bao phủ (covering query):** các cột cần dùng đều có trong chỉ mục; một số hệ quản trị có thể thực hiện `Index Only Scan` hoặc cơ chế tương đương, giảm số lần đọc hàng dữ liệu gốc.

Mục tiêu là thiết kế chỉ mục dựa trên câu truy vấn thực tế, hiểu khi nào bộ tối ưu có thể dùng chỉ mục, và đo được lợi ích cũng như chi phí của lựa chọn đó.

## 1. Vì sao chỉ mục có thể hỗ trợ sắp xếp?

Với chỉ mục B-tree thông dụng, các mục chỉ mục được duy trì theo thứ tự của khóa. Chẳng hạn, chỉ mục kết hợp `(customer_id, status, created_at DESC, order_id DESC)` sắp xếp dữ liệu trước hết theo khách hàng, tiếp đó theo trạng thái, rồi theo thời gian tạo giảm dần và mã đơn hàng giảm dần.

Giả sử ứng dụng cần 20 đơn hàng đã thanh toán gần nhất của khách hàng 42:

```sql
SELECT order_id, created_at, total_amount
FROM orders
WHERE customer_id = 42
  AND status = 'PAID'
ORDER BY created_at DESC, order_id DESC
LIMIT 20;
```

Khi có chỉ mục phù hợp, cơ sở dữ liệu có thể tìm đến vùng có `customer_id = 42` và `status = 'PAID'`, đọc theo thứ tự `created_at DESC, order_id DESC` rồi dừng sau khi tìm đủ 20 kết quả. Nếu không có đường truy cập phù hợp, hệ quản trị có thể phải lọc nhiều hàng, sắp xếp chúng và sau đó mới lấy 20 hàng đầu.

```text
Không có đường đọc phù hợp:
  Đọc các hàng ứng viên -> Lọc -> Sort -> LIMIT 20

Có chỉ mục phù hợp:
  Tìm vùng khóa (customer_id, status)
      -> Đọc các khóa đã được sắp theo created_at, order_id
      -> LIMIT 20
```

Đây là **khả năng** của chỉ mục, không phải cam kết về kế hoạch thực thi. Bộ tối ưu vẫn cân nhắc số hàng, độ chọn lọc, thống kê dữ liệu, chi phí I/O và việc phải đọc thêm bảng gốc. Với tập dữ liệu nhỏ hoặc bộ lọc trả về phần lớn bảng, quét bảng rồi sắp xếp đôi khi rẻ hơn.

## 2. Ghép thứ tự cột của chỉ mục với WHERE và ORDER BY

Một quy tắc thiết kế thường hiệu quả cho truy vấn dùng B-tree là:

1. Đặt các cột được lọc bằng phép bằng (`=`) thường xuyên ở đầu khóa chỉ mục.
2. Đặt các cột dùng để sắp xếp tiếp theo, đúng thứ tự và chiều sắp xếp mà truy vấn cần.
3. Chỉ thêm các cột trả về nhưng không cần tìm kiếm hoặc sắp xếp khi lợi ích đọc bù được chi phí lưu trữ và ghi.

Ví dụ sau dùng **PostgreSQL** để minh họa cú pháp `INCLUDE`. Các hệ quản trị khác có cú pháp và cơ chế truy cập khác nhau.

```sql
CREATE TABLE orders (
    order_id     BIGINT PRIMARY KEY,
    customer_id  BIGINT NOT NULL,
    status       VARCHAR(20) NOT NULL,
    created_at   TIMESTAMP NOT NULL,
    total_amount NUMERIC(18, 2) NOT NULL,
    note         TEXT
);

CREATE INDEX idx_orders_customer_status_recent
ON orders (
    customer_id,
    status,
    created_at DESC,
    order_id DESC
)
INCLUDE (total_amount);
```

Trong chỉ mục này, `customer_id` và `status` tạo vùng tìm kiếm liên tiếp; `created_at` và `order_id` xác định thứ tự duyệt. `total_amount` là cột dữ liệu đi kèm (`INCLUDE`), phục vụ truy vấn chỉ cần đọc từ chỉ mục nếu điều kiện thực thi cho phép. Cột `INCLUDE` **không** tham gia xác định thứ tự khóa hoặc điều kiện tìm kiếm theo khóa.

| Câu truy vấn | Khả năng tận dụng chỉ mục trên |
| --- | --- |
| `customer_id = 42 AND status = 'PAID' ORDER BY created_at DESC, order_id DESC` | Phù hợp vùng khóa và thứ tự sắp xếp. |
| Cùng bộ lọc, `ORDER BY created_at DESC LIMIT 20` | Có thể đọc đúng thứ tự; `order_id` còn giúp tạo thứ tự xác định nếu được thêm vào `ORDER BY`. |
| `customer_id = 42 AND status IN ('PAID', 'SHIPPED') ORDER BY created_at DESC` | Dữ liệu nằm trong các nhóm `status` khác nhau; không mặc nhiên có thứ tự `created_at` chung, có thể cần bước gộp/sắp xếp. |
| `customer_id = 42 ORDER BY created_at DESC` | Thiếu điều kiện cố định `status`; thứ tự trong chỉ mục ưu tiên `status`, nên không bảo đảm thứ tự thời gian toàn cục. |
| `customer_id = 42 AND status = 'PAID' ORDER BY total_amount DESC` | `total_amount` là cột `INCLUDE` nên không cung cấp thứ tự khóa mong muốn. |
| Cùng bộ lọc, `ORDER BY created_at DESC, order_id ASC` | Chiều khóa thứ hai không trùng chỉ mục; có thể cần sắp xếp bổ sung. |

Các lưu ý quan trọng:

- **Thứ tự cột quan trọng.** Chỉ mục `(customer_id, status, created_at)` khác `(created_at, customer_id, status)`. Khả năng tìm kiếm theo tiền tố khóa và duy trì thứ tự phụ thuộc vào điều kiện truy vấn.
- **Chiều sắp xếp phải tương thích.** B-tree nhiều hệ quản trị có thể quét ngược để đảo tất cả chiều sắp xếp, nhưng trộn `ASC` và `DESC` tùy cột có thể cần khai báo rõ trong chỉ mục. Chi tiết khác nhau giữa các hệ quản trị.
- **Giá trị NULL và collation có ảnh hưởng.** Quy tắc `NULLS FIRST/LAST` và thứ tự so sánh chuỗi của truy vấn phải tương thích với chỉ mục. Ví dụ này dùng `created_at NOT NULL` để không phát sinh vấn đề về vị trí `NULL`.
- **Điều kiện phạm vi cần được xem xét.** Chẳng hạn, `created_at >= ...` kết hợp với `ORDER BY created_at DESC` vẫn có thể đọc một vùng khóa có thứ tự khi các cột đứng trước đã được cố định; điều kiện phạm vi đặt ở cột khác có thể khiến kế hoạch khó giữ thứ tự mong muốn.
- **Biểu thức có thể phá vỡ thứ tự sẵn có.** `ORDER BY DATE(created_at)` không tương đương với việc bộ tối ưu luôn dùng chỉ mục trên `created_at`. Một số hệ quản trị hỗ trợ chỉ mục biểu thức cho nhu cầu này.

Đừng thiết kế chỉ mục chỉ bằng cách ghép cơ học tất cả cột xuất hiện trong SQL. Tần suất truy vấn, mức độ phân biệt của khóa, các đường truy cập khác và kích thước chỉ mục đều ảnh hưởng đến phương án tốt nhất.

## 3. Truy vấn chỉ đọc các trường cần thiết (covering index)

Truy vấn dưới đây chỉ cần ba cột kết quả, hai điều kiện lọc và hai cột sắp xếp:

```sql
SELECT order_id, created_at, total_amount
FROM orders
WHERE customer_id = 42
  AND status = 'PAID'
ORDER BY created_at DESC, order_id DESC
LIMIT 20;
```

Tất cả các cột mà truy vấn sử dụng đều đã nằm trong `idx_orders_customer_status_recent`: bốn cột khóa cùng cột `total_amount` được thêm bằng `INCLUDE`. Vì vậy truy vấn là **được chỉ mục bao phủ** về mặt dữ liệu. Nếu thực thi chỉ bằng các mục chỉ mục, hệ quản trị tránh phải tra cứu từng hàng trong bảng để lấy `total_amount`.

Ngược lại, câu lệnh:

```sql
SELECT *
FROM orders
WHERE customer_id = 42
  AND status = 'PAID'
ORDER BY created_at DESC, order_id DESC
LIMIT 20;
```

cần thêm `note`, vốn không có trong chỉ mục. Kế hoạch có thể vẫn sử dụng chỉ mục để lọc hoặc giữ thứ tự, nhưng phải đọc thêm hàng trong bảng để trả về cột còn thiếu. Vì thế, khi API chỉ hiển thị mã đơn, thời điểm và số tiền, hãy chọn đúng ba trường thay vì `SELECT *`.

Một chỉ mục *bao phủ* được xét **đối với một truy vấn cụ thể**; không có một danh sách cột nào bảo đảm bao phủ mọi truy vấn. Cũng cần phân biệt:

| Thuật ngữ | Ý nghĩa |
| --- | --- |
| `Index Scan` | Đọc các mục chỉ mục để tìm hàng, nhưng có thể vẫn truy cập bảng gốc. |
| `Covering index/query` | Chỉ mục chứa đủ những cột mà một truy vấn cần. Đây là thuộc tính của sự kết hợp chỉ mục và truy vấn. |
| `Index Only Scan` (PostgreSQL) | Nút kế hoạch cố gắng lấy dữ liệu từ chỉ mục. PostgreSQL vẫn có thể truy cập heap để kiểm tra tính hiển thị của hàng theo MVCC. |
| `Using index` (MySQL/InnoDB) | Dấu hiệu thường thấy trong `EXPLAIN` khi dữ liệu cần cho truy vấn được lấy từ chỉ mục; không đồng nghĩa với việc đã tránh mọi thao tác sắp xếp. |

**Điểm riêng của PostgreSQL:** index-only scan vẫn phụ thuộc vào *visibility map*. Khi các trang heap chưa được đánh dấu *all-visible*, PostgreSQL cần kiểm tra tính hiển thị trên heap; vì vậy kế hoạch `Index Only Scan` vẫn có thể báo `Heap Fetches` lớn hơn 0. Các bảng cập nhật liên tục có thể ít được hưởng lợi hơn bảng chủ yếu đọc.

**Điểm riêng của MySQL/InnoDB:** không có cú pháp `INCLUDE` giống PostgreSQL; muốn cột `total_amount` có trong chỉ mục phụ, có thể phải đặt nó vào danh sách cột khóa, sau khi cân nhắc độ rộng chỉ mục. Các chỉ mục phụ InnoDB còn chứa giá trị khóa chính để định vị hàng; điều đó không có nghĩa chúng chứa mọi cột khác trong bảng.

**Điểm riêng của SQLite:** `EXPLAIN QUERY PLAN` có thể hiển thị `USING COVERING INDEX` khi truy vấn đọc đủ dữ liệu từ chỉ mục. Trong SQLite, các cột chỉ dùng để trả về thường được thêm vào cuối khóa của chỉ mục nhiều cột.

## 4. Kết hợp cả hai lợi ích trong một API Java

Giả sử repository cần trả về danh sách đơn đã thanh toán mới nhất theo từng trang (chẳng hạn 20 đơn). API chỉ trả về trường đang sử dụng ở giao diện, nên có thể ánh xạ trực tiếp sang DTO/record thay vì lấy toàn bộ thực thể.

```java
import java.math.BigDecimal;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.List;

public final class OrderReader {
    public record OrderSummary(long orderId, LocalDateTime createdAt,
                               BigDecimal totalAmount) {}

    public List<OrderSummary> findRecentPaidOrders(
            Connection connection, long customerId, int pageSize)
            throws SQLException {
        if (pageSize < 1 || pageSize > 100) {
            throw new IllegalArgumentException("pageSize phải nằm trong 1..100");
        }

        String sql = """
            SELECT order_id, created_at, total_amount
            FROM orders
            WHERE customer_id = ? AND status = 'PAID'
            ORDER BY created_at DESC, order_id DESC
            LIMIT ?
            """;

        List<OrderSummary> result = new ArrayList<>();
        try (PreparedStatement statement = connection.prepareStatement(sql)) {
            statement.setLong(1, customerId);
            statement.setInt(2, pageSize);
            try (ResultSet rows = statement.executeQuery()) {
                while (rows.next()) {
                    result.add(new OrderSummary(
                        rows.getLong("order_id"),
                        rows.getObject("created_at", LocalDateTime.class),
                        rows.getBigDecimal("total_amount")));
                }
            }
        }
        return result;
    }
}
```

Đoạn mã dùng Java có hỗ trợ `record` và text block, cùng JDBC driver hỗ trợ ánh xạ `TIMESTAMP` sang `LocalDateTime`. `PreparedStatement` gắn tham số giá trị an toàn. Truy vấn có thứ tự phụ `order_id DESC` để hai đơn cùng thời điểm không dẫn đến thứ tự không xác định. Giới hạn kích thước trang giúp khống chế lượng dữ liệu truyền về, nhưng không tự bảo đảm rằng cơ sở dữ liệu sẽ chọn đúng chỉ mục: cần xem kế hoạch thực thi.

Nếu cần chọn tên cột hoặc chiều `ORDER BY` theo đầu vào người dùng, không ghép trực tiếp chuỗi không tin cậy vào SQL. Dấu `?` không thay thế tên cột hoặc từ khóa `ASC/DESC`; ứng dụng phải ánh xạ lựa chọn hợp lệ sang một tập biểu thức sắp xếp cho phép, rồi đánh giá chỉ mục phù hợp với từng kiểu sắp xếp được hỗ trợ.

## 5. Phân trang: chỉ mục tốt vẫn có thể phải bỏ qua nhiều hàng

Với dữ liệu lớn, câu lệnh dưới đây có thể tốn chi phí đáng kể ngay cả khi đọc đúng thứ tự chỉ mục:

```sql
SELECT order_id, created_at, total_amount
FROM orders
WHERE customer_id = 42 AND status = 'PAID'
ORDER BY created_at DESC, order_id DESC
LIMIT 20 OFFSET 100000;
```

Hệ quản trị thường phải bước qua rất nhiều mục phù hợp trước khi trả lại 20 hàng của trang này. Khi giao diện có thao tác "Tải thêm", có thể dùng **keyset pagination** (seek pagination): lưu `(created_at, order_id)` của hàng cuối trang trước và truy vấn trang sau.

```sql
-- Ví dụ PostgreSQL; hai giá trị cursor đến từ hàng cuối trang trước.
SELECT order_id, created_at, total_amount
FROM orders
WHERE customer_id = 42
  AND status = 'PAID'
  AND (created_at, order_id) < (:last_created_at, :last_order_id)
ORDER BY created_at DESC, order_id DESC
LIMIT 20;
```

Các tham số có tiền tố `:` ở đây là ký hiệu minh họa cho cơ chế bind của tầng ứng dụng; với JDBC `PreparedStatement`, dùng dấu `?` tương ứng. Do cả hai cột sắp xếp đều giảm dần, điều kiện tuple `<` lấy các khóa đứng sau cursor. Cần khóa phụ duy nhất (`order_id`) để tránh bỏ sót hoặc lặp các hàng có cùng `created_at`. Trong PostgreSQL, kiểu giá trị này có thể kết hợp với B-tree để đọc từ một vị trí khóa thích hợp.

Keyset pagination thường giảm lượng hàng phải bỏ qua khi đi sâu vào danh sách, nhưng không tạo ra một ảnh chụp dữ liệu cố định: các hàng được thêm, xóa hoặc sửa khóa sắp xếp giữa hai lần gọi vẫn có thể làm danh sách thay đổi. Nếu ứng dụng cần kết quả nhất quán xuyên nhiều trang, hãy thiết kế thêm quy tắc snapshot hoặc mốc thời gian theo yêu cầu nghiệp vụ.

## 6. Đọc kế hoạch thực thi để xác nhận

Không nên kết luận rằng truy vấn đã hết thao tác sắp xếp hoặc đọc bảng chỉ vì đã tạo chỉ mục. Trong PostgreSQL, hãy chạy:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT order_id, created_at, total_amount
FROM orders
WHERE customer_id = 42
  AND status = 'PAID'
ORDER BY created_at DESC, order_id DESC
LIMIT 20;
```

`EXPLAIN ANALYZE` **thực sự chạy** câu truy vấn, vì vậy nên dùng dữ liệu và môi trường đo phù hợp. Cần quan sát:

1. Nút `Limit` có lấy đầu vào từ `Index Scan` hoặc `Index Only Scan` trên đúng chỉ mục dự kiến hay không.
2. Có nút `Sort`, `Incremental Sort` hoặc một thao tác sắp xếp bổ sung nào không. Nếu có, cần tìm phần thứ tự chưa được chỉ mục đáp ứng.
3. `actual rows`, số hàng đọc/lọc và chênh lệch giữa số hàng ước lượng và thực tế.
4. `Buffers` và thời gian chạy; với `Index Only Scan`, xem thêm `Heap Fetches` để biết còn phải kiểm tra heap bao nhiêu lần.
5. Kết quả trên tập dữ liệu đại diện, ở cả trường hợp lọc ít và lọc nhiều hàng; độ nhanh ở bảng nhỏ chưa đủ để đánh giá lợi ích.

Trong MySQL, có thể dùng `EXPLAIN` / `EXPLAIN ANALYZE` và kiểm tra `Using filesort` (có thao tác sắp xếp riêng) cùng `Using index` (thường là dấu hiệu truy vấn được bao phủ). Trong SQLite, `EXPLAIN QUERY PLAN` có thể nêu `USING COVERING INDEX` hoặc `USE TEMP B-TREE FOR ORDER BY`. Các nhãn không hoàn toàn tương đương giữa các hệ quản trị.

Khi so sánh trước và sau thay đổi, nên ghi lại cùng một câu SQL, tham số, phân bố dữ liệu, chỉ số thời gian, lượng I/O và kế hoạch. Thống kê lạc hậu, mức độ phân mảnh hoặc dữ liệu thay đổi cũng có thể khiến bộ tối ưu chọn phương án khác.

## 7. Đánh đổi khi thiết kế chỉ mục bao phủ

Thêm cột vào chỉ mục làm tăng kích thước, chi phí cập nhật và lượng dữ liệu phải duy trì. Một chỉ mục chỉ phục vụ một API ít được gọi có thể không đáng giá nếu bảng nhận rất nhiều lệnh `INSERT`, `UPDATE` hoặc `DELETE`.

| Quyết định | Lợi ích tiềm năng | Chi phí / giới hạn |
| --- | --- | --- |
| Thêm cột lọc và sắp xếp vào khóa kết hợp | Tìm đúng vùng và trả kết quả có thứ tự | Tăng độ rộng khóa; phục vụ kém những truy vấn có tiền tố khác |
| Thêm `INCLUDE (total_amount)` trong PostgreSQL | Có cơ hội lấy cột kết quả ngay từ chỉ mục mà không đưa nó vào thứ tự khóa | Tốn chỗ; cập nhật cột này vẫn tác động đến chỉ mục; index-only scan còn phụ thuộc MVCC |
| Thêm nhiều cột chỉ để bao phủ `SELECT *` | Có thể giảm đọc bảng ở một vài truy vấn | Chỉ mục rất rộng, tăng I/O/cache pressure và chi phí ghi; có giới hạn kích thước từng hệ |
| Tạo nhiều chỉ mục gần giống nhau | Phục vụ các cách lọc/sắp xếp khác nhau | Tăng dung lượng, thời gian ghi và công bảo trì |
| Giữ chỉ mục nhỏ và chọn cột trong `SELECT` | Giảm truyền dữ liệu và giữ chỉ mục gọn | Truy vấn cần cột khác vẫn phải lấy từ bảng |

Các tối ưu cần được đánh giá theo **khối lượng truy vấn thực tế**. Ví dụ, PostgreSQL có thể dùng chỉ mục riêng cho các đơn `PAID` thông qua *partial index* khi bộ lọc này rất phổ biến và phù hợp điều kiện lập kế hoạch. Nhưng thêm quá nhiều biến thể chỉ mục theo từng màn hình sẽ làm hệ thống khó bảo trì.

Trong hệ thống Java, nên giữ SQL và ánh xạ dữ liệu ở ranh giới repository/persistence, phân biệt DTO đọc với entity dùng cho cập nhật. Khi API thay đổi danh sách cột trả về hoặc thứ tự sắp xếp, hãy xem lại giả định bao phủ và kế hoạch thực thi. Cũng cần theo dõi độ trễ truy vấn theo phân vị, số hàng đọc, cache hit và chi phí ghi, không chỉ một lần chạy `EXPLAIN`.

## 8. Checklist áp dụng cho một truy vấn

Trước khi thêm chỉ mục mới, hãy tự trả lời:

- Bộ lọc `WHERE` nào là cố định bằng `=`? Các cột sắp xếp theo thứ tự và chiều nào? Có khóa phụ duy nhất để giải quyết trường hợp trùng giá trị không?
- Những cột nào thật sự phải xuất hiện trong `SELECT`? Chỉ mục hiện tại đã bao phủ chúng chưa? Việc đọc thêm bảng có đang là vấn đề đo được không?
- `EXPLAIN` có xác nhận bộ tối ưu đọc đúng vùng chỉ mục, tránh sắp xếp không cần thiết và hạn chế truy cập heap/bảng gốc không?
- Có `OFFSET` lớn, biểu thức trên cột sắp xếp, `IN` nhiều nhóm, `JOIN` hoặc yêu cầu `NULLS` / collation nào khiến thứ tự chỉ mục không còn khớp không?
- Lợi ích đọc có đủ lớn so với dung lượng chỉ mục và chi phí ghi hay không?

### Bài tập thực hành

Một API lấy 30 bài viết đã xuất bản gần nhất của một tác giả:

```sql
SELECT post_id, published_at, title
FROM posts
WHERE author_id = 17 AND state = 'PUBLISHED'
ORDER BY published_at DESC, post_id DESC
LIMIT 30;
```

Hãy đề xuất một chỉ mục PostgreSQL phục vụ bộ lọc và thứ tự trên; xét thêm cách bao phủ `title` nếu đây là cột vừa phải về kích thước. Sau đó dùng `EXPLAIN (ANALYZE, BUFFERS)` để kiểm tra kế hoạch và thử chuyển toàn bộ danh sách cột trong mệnh đề `SELECT` thành `*`. Dự đoán sự thay đổi về khả năng index-only scan, rồi đối chiếu với kết quả trên dữ liệu thực.

Một phương án khởi đầu là:

```sql
CREATE INDEX idx_posts_author_state_recent
ON posts (author_id, state, published_at DESC, post_id DESC)
INCLUDE (title);
```

Phương án này giúp nhận ra hai yếu tố phải kiểm chứng độc lập: **thứ tự của khóa B-tree có phù hợp `ORDER BY` hay không**, và **những cột mà truy vấn cần có thể lấy trực tiếp từ chỉ mục hay không**. Cả hai đều chỉ đem lại hiệu quả khi kế hoạch thực thi và đặc điểm dữ liệu thực tế ủng hộ chúng.
