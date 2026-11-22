# Composite index, leftmost prefix và thứ tự các cột

Composite index (chỉ mục ghép) là chỉ mục được tạo trên từ hai cột trở lên. Trong MySQL, thứ tự các cột trong chỉ mục ghép quyết định cách B+Tree sắp xếp khóa và những điều kiện truy vấn có thể tận dụng chỉ mục. Chỉ mục `(tenant_id, status, created_at)` không tương đương với `(status, tenant_id, created_at)`, dù cả hai chứa cùng ba cột.

Quy tắc quan trọng nhất là **leftmost prefix**: MySQL thường khai thác chỉ mục ghép hiệu quả từ cột ngoài cùng bên trái, rồi tiếp tục sang các cột kế tiếp theo thứ tự. Khi thiết kế index, cần bắt đầu từ hình dạng truy vấn thực tế, xác định cột lọc bằng, cột lọc khoảng, cột sắp xếp hoặc nhóm, sau đó chọn thứ tự cột phù hợp.

## 1. Composite index được sắp xếp như thế nào?

Giả sử có bảng đơn hàng:

```sql
CREATE TABLE orders (
    order_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    tenant_id BIGINT UNSIGNED NOT NULL,
    customer_id BIGINT UNSIGNED NOT NULL,
    status VARCHAR(20) NOT NULL,
    created_at DATETIME NOT NULL,
    total_amount DECIMAL(12, 2) NOT NULL,
    PRIMARY KEY (order_id)
) ENGINE = InnoDB;
```

Tạo chỉ mục ghép:

```sql
CREATE INDEX idx_orders_tenant_status_created
ON orders (tenant_id, status, created_at);
```

Các mục trong index được sắp xếp theo thứ tự từ điển (lexicographic):

1. So sánh `tenant_id` trước.
2. Nếu `tenant_id` bằng nhau, so sánh `status`.
3. Nếu cả hai cột đầu bằng nhau, so sánh `created_at`.

Ví dụ thứ tự khóa minh họa:

| tenant_id | status | created_at |
|---:|---|---|
| 10 | CANCELLED | 2026-01-02 09:00:00 |
| 10 | PAID | 2026-01-01 10:00:00 |
| 10 | PAID | 2026-01-03 08:00:00 |
| 10 | PENDING | 2026-01-02 12:00:00 |
| 20 | PAID | 2026-01-01 11:00:00 |

Thứ tự này cho phép tìm một tenant, thu hẹp tiếp theo trạng thái, rồi quét theo thời gian trong nhóm tenant và trạng thái đó. Index không được sắp xếp độc lập theo từng cột; các cột phía sau chỉ có thứ tự có ý nghĩa bên trong nhóm được tạo bởi những cột đứng trước.

## 2. Quy tắc leftmost prefix

Với index:

```sql
INDEX (tenant_id, status, created_at)
```

Các tiền tố trái có thể được dùng để định vị phạm vi khóa:

- `(tenant_id)`
- `(tenant_id, status)`
- `(tenant_id, status, created_at)`

Ví dụ các truy vấn phù hợp:

```sql
-- Dùng phần đầu tenant_id
SELECT order_id, status
FROM orders
WHERE tenant_id = 10;

-- Dùng tenant_id và status
SELECT order_id, created_at
FROM orders
WHERE tenant_id = 10
  AND status = 'PAID';

-- Dùng cả ba cột để lọc
SELECT order_id, total_amount
FROM orders
WHERE tenant_id = 10
  AND status = 'PAID'
  AND created_at >= '2026-01-01 00:00:00';
```

Truy vấn chỉ lọc theo `status` thường không thể định vị một khoảng liên tục hiệu quả bằng index này vì không có giá trị `tenant_id` ở đầu:

```sql
SELECT order_id
FROM orders
WHERE status = 'PAID';
```

Tương tự, điều kiện chỉ trên `created_at` không bắt đầu từ cột trái nhất. Optimizer có thể cân nhắc những chiến lược khác, chẳng hạn index khác, quét bảng hoặc trong một số điều kiện cụ thể dùng skip scan. Không nên thiết kế truy vấn quan trọng dựa vào giả định rằng MySQL sẽ luôn bỏ qua được các cột đầu bị thiếu.

Điều đó không có nghĩa một index ghép chỉ phục vụ đúng một câu SQL. Index `(tenant_id, status, created_at)` có thể phục vụ truy vấn theo `tenant_id`, theo cặp `tenant_id + status`, hoặc cả ba cột. Đây là lợi ích của tiền tố trái khi chọn index cho nhiều truy vấn có chung phần đầu.

## 3. Thứ tự cột: equality trước, range sau

Trong nhiều truy vấn, một cách thiết kế hữu ích là đặt các cột có điều kiện bằng (equality) trước cột dùng điều kiện khoảng (range), rồi cân nhắc cột sắp xếp hoặc nhóm.

Ví dụ:

```sql
SELECT order_id, created_at, total_amount
FROM orders
WHERE tenant_id = 10
  AND status = 'PAID'
  AND created_at >= '2026-01-01 00:00:00'
  AND created_at <  '2026-02-01 00:00:00'
ORDER BY created_at;
```

Index `(tenant_id, status, created_at)` phù hợp vì MySQL có thể cố định hai cột đầu bằng điều kiện equality, sau đó quét một khoảng `created_at` trong nhóm đó.

Nếu index được đổi thành `(created_at, tenant_id, status)`, điều kiện khoảng trên `created_at` xuất hiện ở cột đầu. Các cột phía sau vẫn có thể được kiểm tra trong index hoặc bằng Index Condition Pushdown tùy kế hoạch, nhưng chúng thường không giúp thu hẹp tiếp một range liên tục sau điểm range đầu tiên theo cách tương tự.

Quy tắc này là điểm khởi đầu, không phải công thức cứng cho mọi index. Nếu truy vấn chủ yếu tìm theo `created_at` trên toàn hệ thống, index bắt đầu bằng `created_at` có thể hợp lý. Nếu truy vấn khác thường lọc theo `status` riêng, có thể cần một index khác. Hãy thiết kế theo workload thay vì sắp xếp cột chỉ theo một tiêu chí chung như độ chọn lọc.

### Equality có thể gồm nhiều giá trị

Điều kiện `IN` có thể tạo nhiều phạm vi bằng cho cột:

```sql
SELECT order_id, created_at
FROM orders
WHERE tenant_id = 10
  AND status IN ('PAID', 'PENDING')
  AND created_at >= '2026-01-01';
```

Optimizer có thể thực hiện nhiều lần dò hoặc range scan phù hợp với các giá trị `status`. Chi phí thực tế phụ thuộc số lượng giá trị trong `IN`, thống kê và dữ liệu. Khi `IN` chứa rất nhiều giá trị, hãy kiểm tra kế hoạch và thời gian thực thi thay vì mặc định nó tương đương một equality đơn giản.

## 4. Composite index hỗ trợ ORDER BY như thế nào?

Index có thể giúp MySQL trả kết quả theo thứ tự mà không cần bước sắp xếp bổ sung, nếu thứ tự truy vấn phù hợp với thứ tự index và các cột đứng trước được cố định thích hợp.

Với index `(tenant_id, status, created_at)`, truy vấn sau có thể đọc theo thứ tự `created_at` trong phạm vi một tenant và một status:

```sql
SELECT order_id, created_at
FROM orders
WHERE tenant_id = 10
  AND status = 'PAID'
ORDER BY created_at DESC
LIMIT 20;
```

Hai cột đầu có giá trị cố định; phần còn lại của index được sắp xếp theo `created_at`. MySQL có thể duyệt index theo chiều ngược để đáp ứng thứ tự giảm dần khi cấu trúc và kế hoạch phù hợp.

Nếu bỏ điều kiện `tenant_id` hoặc `status`, index không tự nhiên tạo ra một thứ tự toàn cục chỉ theo `created_at`, bởi các hàng được nhóm theo các cột đứng trước. MySQL có thể phải filesort hoặc chọn kế hoạch khác.

Với thứ tự hỗn hợp nhiều cột, ví dụ `ORDER BY created_at DESC, order_id ASC`, cần chú ý chiều sắp xếp của từng thành phần index. MySQL 8.0 hỗ trợ descending index key parts; việc tạo index với chiều tương ứng có thể hữu ích cho truy vấn có thứ tự hỗn hợp:

```sql
CREATE INDEX idx_orders_tenant_created_order
ON orders (tenant_id, created_at DESC, order_id ASC);
```

Không phải mọi `ORDER BY` đều được index đáp ứng. Biểu thức trên cột, khác biệt collation, thứ tự cột không tương thích hoặc các cột đầu không được cố định có thể khiến MySQL cần sắp xếp bổ sung. Xem `Using filesort` trong `EXPLAIN` để biết kế hoạch có bước filesort; thuật ngữ này không nhất thiết có nghĩa dữ liệu chắc chắn được ghi ra đĩa.

## 5. Composite index và GROUP BY

Index cũng có thể giúp truy vấn nhóm dữ liệu nếu thứ tự cột phù hợp với điều kiện lọc và cột nhóm:

```sql
SELECT status, COUNT(*) AS order_count
FROM orders
WHERE tenant_id = 10
GROUP BY status;
```

Index `(tenant_id, status, created_at)` đặt `tenant_id` trước và `status` tiếp theo, phù hợp với việc lọc tenant rồi nhóm theo trạng thái. Tuy nhiên, MySQL có nhiều chiến lược thực thi `GROUP BY`; optimizer có thể chọn cách khác tùy cardinality, thống kê và lượng dữ liệu cần đọc.

Nếu truy vấn nhóm theo `status` trên mọi tenant, index bắt đầu bằng `tenant_id` có thể không tạo thứ tự toàn cục theo `status`. Một index bắt đầu bằng `status` có thể phù hợp hơn cho workload đó, nhưng cũng làm tăng chi phí ghi và dung lượng. Hãy so sánh các truy vấn thực tế trước khi thêm index.

## 6. Covering index và Index Condition Pushdown

Hai cơ chế này thường được nhắc đến khi phân tích composite index, nhưng chúng giải quyết hai vấn đề khác nhau.

### Covering index

Một index là covering cho một truy vấn khi nó chứa đủ các cột cần để lọc và trả kết quả. Ví dụ, với index `(tenant_id, status, created_at)` đã tạo ở mục 1:

```sql
SELECT tenant_id, status, created_at
FROM orders
WHERE tenant_id = 10
  AND status = 'PAID';
```

Truy vấn chỉ cần các cột có trong index. Trên InnoDB, secondary index còn mang khóa chính, nên truy vấn lấy thêm `order_id` cũng có thể được bao phủ bởi index này.

### Index Condition Pushdown (ICP)

ICP cho phép storage engine kiểm tra một số điều kiện ngay trên các mục secondary index trước khi phải đọc hàng đầy đủ từ clustered index. Điều này có thể giảm số lần tra cứu hàng, nhưng không biến truy vấn thành covering index nếu truy vấn vẫn cần các cột không có trong index.

Ví dụ tạo thêm index `(tenant_id, created_at, status)`. Cột `status` đứng sau cột range `created_at`, nên có thể được kiểm tra bằng ICP trước khi phải đọc hàng đầy đủ:

```sql
CREATE INDEX idx_orders_tenant_created_status
ON orders (tenant_id, created_at, status);

SELECT order_id, total_amount
FROM orders
WHERE tenant_id = 10
  AND created_at >= '2026-01-01'
  AND status = 'PAID';
```

Index có thể dùng `tenant_id` và khoảng `created_at` để định vị phạm vi, rồi kiểm tra `status` ngay trên mục index trước khi tra cứu clustered index. Vì `total_amount` không nằm trong index, truy vấn vẫn cần đọc hàng đầy đủ cho những mục vượt qua điều kiện. Hãy xem `Using index condition` trong `EXPLAIN` khi ICP được áp dụng.

## 7. Composite index hay nhiều single-column index?

Giả sử ứng dụng thường truy vấn:

```sql
SELECT order_id, created_at
FROM orders
WHERE tenant_id = 10
  AND status = 'PAID';
```

Hai chỉ mục đơn riêng biệt:

```sql
CREATE INDEX idx_orders_tenant ON orders (tenant_id);
CREATE INDEX idx_orders_status ON orders (status);
```

không tương đương với một chỉ mục ghép:

```sql
CREATE INDEX idx_orders_tenant_status
ON orders (tenant_id, status);
```

Với composite index, MySQL có thể định vị trực tiếp nhóm có cả `tenant_id` và `status` theo thứ tự của một B+Tree. Với hai index đơn, optimizer có thể chọn một index, dùng Index Merge hoặc chọn quét bảng tùy chi phí ước lượng. Index Merge không phải lúc nào cũng rẻ bằng index ghép phù hợp.

Tuy nhiên, hai index đơn có thể phục vụ các truy vấn độc lập như tìm tất cả đơn hàng của một tenant hoặc tất cả đơn hàng theo status. Composite index `(tenant_id, status)` hỗ trợ tốt truy vấn theo `tenant_id` và theo cả cặp, nhưng không phải lựa chọn tiền tố trái cho truy vấn chỉ theo `status`.

Hãy cân nhắc:

- Các mẫu `WHERE`, `JOIN`, `ORDER BY` và `GROUP BY` xuất hiện thường xuyên.
- Số lượng hàng cần đọc và độ chọn lọc của điều kiện.
- Index có thể dùng chung cho nhiều truy vấn hay không.
- Chi phí bổ sung khi `INSERT`, `UPDATE`, `DELETE` và dung lượng lưu trữ.

## 8. Cách chọn thứ tự cột trong thực tế

Không nên áp dụng máy móc câu “cột có độ chọn lọc cao nhất luôn đứng đầu”. Thứ tự index phải phục vụ các truy vấn cần tối ưu và khả năng dùng tiền tố trái.

Một quy trình thực tế:

1. Thu thập các câu truy vấn quan trọng và tần suất chạy của chúng.
2. Ghi lại cột được lọc bằng, cột được lọc theo khoảng, cột nối bảng, cột sắp xếp và cột nhóm.
3. Xác định những truy vấn có chung các cột dẫn đầu để có thể dùng chung index.
4. Thử đặt các cột equality thường cố định trước, cột range sau; điều chỉnh nếu truy vấn khác cần thứ tự khác.
5. Cân nhắc thêm cột để hỗ trợ `ORDER BY` hoặc tạo covering index khi lợi ích lớn hơn chi phí.
6. Kiểm tra bằng `EXPLAIN` hoặc `EXPLAIN ANALYZE`, đo trên dữ liệu đại diện và theo dõi sau triển khai.

Ví dụ hai truy vấn có hình dạng khác nhau:

```sql
-- Truy vấn A: tenant và trạng thái cố định, quét theo thời gian
SELECT order_id, created_at
FROM orders
WHERE tenant_id = 10
  AND status = 'PAID'
ORDER BY created_at DESC
LIMIT 50;

-- Truy vấn B: tìm theo khách hàng và thời gian
SELECT order_id, created_at
FROM orders
WHERE customer_id = 2001
  AND created_at >= '2026-01-01'
ORDER BY created_at DESC;
```

Index phù hợp cho A có thể là `(tenant_id, status, created_at)`, trong khi B có thể cần `(customer_id, created_at)`. Một index duy nhất không nhất thiết tối ưu cả hai. Chỉ tạo index thứ hai nếu tần suất và chi phí truy vấn B đủ lớn để biện minh cho chi phí ghi và lưu trữ.

## 9. Xác minh bằng EXPLAIN

Sau khi tạo index, hãy kiểm tra kế hoạch thực thi thay vì chỉ xác nhận index đã tồn tại:

```sql
EXPLAIN
SELECT order_id, created_at, total_amount
FROM orders
WHERE tenant_id = 10
  AND status = 'PAID'
  AND created_at >= '2026-01-01'
ORDER BY created_at DESC
LIMIT 20;
```

Các trường thường cần xem:

- `key`: index optimizer chọn.
- `key_len`: độ dài phần khóa được dùng; cần diễn giải theo kiểu dữ liệu, nullability và các phần khóa được sử dụng.
- `type`: kiểu truy cập như `ref`, `range` hoặc `ALL`.
- `rows` và `filtered`: số hàng ước lượng và tỷ lệ hàng còn lại sau lọc.
- `Extra`: có thể hiển thị `Using index` (covering), `Using index condition` (ICP), hoặc `Using filesort`.

MySQL 8.0.18 trở lên hỗ trợ `EXPLAIN ANALYZE`, thực thi câu truy vấn và báo thời gian cùng số hàng thực tế ở các iterator:

```sql
EXPLAIN ANALYZE
SELECT order_id, created_at, total_amount
FROM orders
WHERE tenant_id = 10
  AND status = 'PAID'
  AND created_at >= '2026-01-01'
ORDER BY created_at DESC
LIMIT 20;
```

`EXPLAIN ANALYZE` thực sự thực thi câu `SELECT` được phân tích và báo thời gian cùng số hàng thực tế. Chỉ chạy với truy vấn đọc mà bạn có thể thực thi an toàn; trên production, cần tính đến tải bổ sung do chính truy vấn tạo ra. So sánh estimated rows với actual rows để nhận biết sai lệch thống kê hoặc giả định về dữ liệu.

## 10. Những lỗi thường gặp

**Đổi thứ tự cột tùy tiện.** `(a, b)` và `(b, a)` có khả năng sử dụng khác nhau. Xác định cột dẫn đầu theo mẫu truy vấn thực tế.

**Chỉ kiểm tra index có tồn tại.** Index tồn tại không đồng nghĩa optimizer chọn nó. Kiểm tra `key`, `rows`, `Extra` và thời gian thực thi.

**Cho rằng cột phía sau luôn thu hẹp range.** Khi đã gặp điều kiện range trên một cột, cột tiếp theo có thể vẫn được kiểm tra trong index nhưng thường không tiếp tục thu hẹp khoảng quét theo cách equality prefix làm được.

**Tạo nhiều index đơn thay cho index ghép mà truy vấn cần.** Optimizer có thể dùng Index Merge, nhưng điều đó không đảm bảo hiệu quả bằng composite index đúng thứ tự.

**Tạo index ghép quá rộng.** Index rộng làm tăng dung lượng và công việc bảo trì khi ghi. Chỉ thêm cột bao phủ khi lợi ích đọc đã được đo.

**Nhầm leftmost prefix với prefix index trên chuỗi.** Leftmost prefix nói về các cột đầu của một index ghép. Prefix index như `INDEX(name(20))` chỉ lưu một phần ký tự đầu của một cột chuỗi; đó là khái niệm khác.

## 11. Tự kiểm tra

1. Index `(tenant_id, status, created_at)` được sắp xếp theo thứ tự nào?
2. Vì sao truy vấn chỉ có `status = 'PAID'` thường không tận dụng hiệu quả index trên?
3. Vì sao thường đặt các điều kiện equality trước cột range?
4. Khi nào index ghép có thể hỗ trợ `ORDER BY created_at` mà không cần filesort?
5. Covering index khác Index Condition Pushdown ở điểm nào?
6. Composite index `(tenant_id, status)` khác hai single-column index ra sao?
7. Vì sao không thể luôn chọn cột có cardinality cao nhất làm cột đầu tiên?
8. Cần xem những thông tin nào trong `EXPLAIN` để đánh giá index vừa tạo?

