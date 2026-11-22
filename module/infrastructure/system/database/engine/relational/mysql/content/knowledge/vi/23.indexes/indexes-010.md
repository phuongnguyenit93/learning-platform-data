# Chỉ mục

## Descending index và truy vấn sắp xếp nhiều chiều

Khi truy vấn cần sắp xếp theo nhiều cột với hướng khác nhau, chẳng hạn điểm số giảm dần nhưng thời điểm tạo tăng dần, một B-tree index thông thường có thể không cung cấp đúng thứ tự mà câu `ORDER BY` yêu cầu. MySQL 8.0 hỗ trợ descending index, cho phép khai báo hướng `ASC` hoặc `DESC` riêng cho từng key part. Nhờ đó, InnoDB có thể đọc index theo thứ tự phù hợp và giảm hoặc loại bỏ bước sắp xếp bổ sung.

Descending index đặc biệt hữu ích cho bảng xếp hạng, danh sách giao dịch, lịch sử sự kiện và các màn hình lấy top-N có nhiều tiêu chí sắp xếp. Tuy nhiên, index chỉ giúp khi thứ tự cột, hướng sắp xếp, điều kiện lọc và biểu thức truy vấn tương thích với cấu trúc index. Thêm `DESC` vào index không tự động làm mọi truy vấn `ORDER BY` nhanh hơn.

### 1. Vì sao cần sắp xếp nhiều chiều?

Một truy vấn có thể sắp xếp theo nhiều tiêu chí. Ví dụ, trang bảng xếp hạng cần điểm cao nhất trước; nếu hai người bằng điểm, người đạt điểm sớm hơn đứng trước; nếu vẫn trùng, dùng `id` để tạo thứ tự xác định:

```sql
SELECT id, player_name, score, achieved_at
FROM leaderboard
WHERE season_id = 2026
ORDER BY score DESC, achieved_at ASC, id ASC
LIMIT 20;
```

Thứ tự yêu cầu là:

1. `score DESC`: điểm lớn đứng trước.
2. `achieved_at ASC`: trong cùng điểm, thời điểm sớm đứng trước.
3. `id ASC`: dùng khóa duy nhất để phân định các hàng còn hòa.

Nếu chỉ có index `(season_id, score)`, index có thể giúp lọc theo mùa và sắp xếp theo điểm, nhưng không nhất thiết đáp ứng được hai hướng tiếp theo. Khi dữ liệu lớn, MySQL có thể phải thực hiện thêm bước sort. Index có hướng phù hợp cho cả ba cột sắp xếp sẽ giúp InnoDB đọc các hàng theo đúng thứ tự mong muốn.

### 2. ASC, DESC và khả năng đọc ngược B-tree

B-tree index có thứ tự khóa. Một index khai báo tất cả key part theo chiều tăng dần có thể được đọc xuôi hoặc đọc ngược. Ví dụ index `(a ASC, b ASC)` có thể phục vụ:

```sql
-- Đọc xuôi theo index.
ORDER BY a ASC, b ASC

-- Đọc ngược toàn bộ thứ tự index.
ORDER BY a DESC, b DESC
```

Khi đọc ngược, hướng của tất cả key part bị đảo cùng lúc. Vì vậy, index `(a ASC, b ASC)` không thể cung cấp trực tiếp thứ tự hỗn hợp `a ASC, b DESC` chỉ bằng cách quét ngược: quét ngược sẽ tạo ra `a DESC, b DESC`.

Descending index giải quyết trường hợp này bằng cách lưu hướng riêng cho từng key part. Ví dụ:

```sql
CREATE INDEX idx_a_asc_b_desc
    ON sample_table (a ASC, b DESC);
```

Index này có thể được đọc xuôi cho `ORDER BY a ASC, b DESC`, hoặc đọc ngược cho thứ tự đảo toàn bộ `ORDER BY a DESC, b ASC`.

| Định nghĩa index | Thứ tự có thể đáp ứng bằng scan xuôi | Thứ tự có thể đáp ứng bằng scan ngược |
| --- | --- | --- |
| `(a ASC, b ASC)` | `a ASC, b ASC` | `a DESC, b DESC` |
| `(a ASC, b DESC)` | `a ASC, b DESC` | `a DESC, b ASC` |
| `(a DESC, b ASC)` | `a DESC, b ASC` | `a ASC, b DESC` |

Điểm cốt lõi là hướng của toàn bộ chuỗi key part phải khớp theo một chiều đọc nhất quán: xuôi hoặc đảo ngược toàn bộ. Nếu chỉ một số cột đổi hướng, cần định nghĩa index có hướng tương ứng.

### 3. Cú pháp descending index trong MySQL 8.0

Có thể khai báo hướng ngay trong danh sách cột của `CREATE INDEX`:

```sql
CREATE INDEX ten_index
ON ten_bang (
    cot_1 ASC,
    cot_2 DESC,
    cot_3 ASC
);
```

Hoặc khai báo trong `CREATE TABLE` / `ALTER TABLE`:

```sql
ALTER TABLE leaderboard
ADD INDEX idx_season_score_time (
    season_id ASC,
    score DESC,
    achieved_at ASC,
    id ASC
);
```

MySQL 8.0 hỗ trợ descending index thực sự trong InnoDB. Trên các phiên bản cũ hơn, từ khóa `DESC` trong định nghĩa index được chấp nhận nhưng bị bỏ qua; index được tạo theo hướng tăng dần. Do đó, phải xác nhận phiên bản máy chủ trước khi dựa vào mixed-direction index để tối ưu truy vấn.

### 4. Ví dụ: top-N theo nhiều chiều

Giả sử có bảng xếp hạng theo mùa:

```sql
CREATE TABLE leaderboard (
    id BIGINT NOT NULL,
    season_id INT NOT NULL,
    player_name VARCHAR(100) NOT NULL,
    score INT NOT NULL,
    achieved_at DATETIME NOT NULL,
    PRIMARY KEY (id)
) ENGINE = InnoDB;
```

Truy vấn cần lấy 20 người đứng đầu trong một mùa:

```sql
SELECT id, player_name, score, achieved_at
FROM leaderboard
WHERE season_id = 2026
ORDER BY score DESC, achieved_at ASC, id ASC
LIMIT 20;
```

Index phù hợp với điều kiện lọc và thứ tự:

```sql
CREATE INDEX idx_leaderboard_season_score_time
ON leaderboard (
    season_id ASC,
    score DESC,
    achieved_at ASC,
    id ASC
);
```

`season_id` đứng đầu vì truy vấn lọc bằng một giá trị mùa. Sau khi cố định key part đầu, InnoDB có thể đọc các entry theo `score DESC`, `achieved_at ASC`, `id ASC`. Nếu index cung cấp đủ thứ tự, MySQL có thể tránh sort bổ sung và dừng sau khi lấy đủ 20 hàng phù hợp.

Nếu truy vấn chỉ trả về các cột đã có trong index, có thể thiết kế covering index bằng cách bổ sung cột cần đọc. Tuy nhiên, thêm `player_name` vào index làm index lớn hơn và tăng chi phí ghi; cần đo lợi ích thực tế trước khi mở rộng:

```sql
CREATE INDEX idx_leaderboard_top_cover
ON leaderboard (
    season_id ASC,
    score DESC,
    achieved_at ASC,
    id ASC,
    player_name ASC
);
```

Với InnoDB, secondary index đã chứa khóa chính làm phần định vị hàng. Không cần lặp lại cột primary key một cách máy móc nếu nó đã được bổ sung ngầm; nhưng thứ tự key part tường minh vẫn cần được thiết kế và kiểm tra theo yêu cầu truy vấn. Một index covering quá rộng có thể gây hại nhiều hơn lợi.

### 5. Quy tắc leftmost prefix và điều kiện lọc

Index nhiều cột tuân theo nguyên tắc leftmost prefix: thứ tự key part bắt đầu từ cột đầu tiên. Các cột đứng trước phần `ORDER BY` thường cần được cố định bằng điều kiện bằng để index có thể cung cấp thứ tự cho các cột phía sau.

Ví dụ index:

```sql
CREATE INDEX idx_order_status_date
ON orders (status ASC, created_at DESC, id ASC);
```

Truy vấn sau phù hợp:

```sql
SELECT id, created_at
FROM orders
WHERE status = 'paid'
ORDER BY created_at DESC, id ASC
LIMIT 50;
```

`status` được cố định bằng một giá trị, vì vậy phần index còn lại có thể cung cấp thứ tự `created_at DESC, id ASC`.

Nếu bỏ điều kiện `status`:

```sql
SELECT id, status, created_at
FROM orders
ORDER BY created_at DESC, id ASC;
```

Index trên sắp xếp trước theo `status`; các hàng thuộc nhiều trạng thái không được sắp xếp toàn cục chỉ theo `created_at`. Optimizer có thể chọn index khác hoặc thực hiện sort.

Điều kiện range ở một key part cũng cần được xem xét. Ví dụ `status = 'paid' AND created_at < ... ORDER BY created_at DESC, id ASC` vẫn có thể tận dụng dải index theo thời gian. Nhưng nếu một cột đứng trước các cột sắp xếp không được cố định, hoặc truy vấn cần thứ tự không liên tục theo nhiều nhóm giá trị, index có thể không cung cấp thứ tự toàn cục như mong muốn. `IN` trên key part đầu với nhiều giá trị cũng có thể tạo nhiều range; hãy kiểm tra kế hoạch thực tế thay vì suy luận rằng nó tương đương một giá trị bằng duy nhất.

### 6. Sắp xếp hỗn hợp và quét ngược toàn bộ index

Xét truy vấn:

```sql
SELECT id, priority, created_at
FROM support_ticket
WHERE tenant_id = 42
ORDER BY priority DESC, created_at ASC, id ASC
LIMIT 30;
```

Index có hướng phù hợp:

```sql
CREATE INDEX idx_ticket_tenant_priority_time
ON support_ticket (
    tenant_id ASC,
    priority DESC,
    created_at ASC,
    id ASC
);
```

Index này được đọc xuôi cho thứ tự đã yêu cầu. Nếu truy vấn yêu cầu đảo tất cả hướng:

```sql
ORDER BY priority ASC, created_at DESC, id DESC
```

MySQL có thể đọc ngược index sau khi `tenant_id` được cố định. Nhưng nếu chỉ đảo một phần, ví dụ `priority ASC, created_at ASC, id ASC`, đó không phải thứ tự ngược hoàn toàn của index trên; một index khác hoặc bước sort có thể cần thiết.

Khi thiết kế, hãy ghi rõ thứ tự mong muốn cho từng cột trước khi tạo index. Không nên chỉ nhìn cột đầu tiên là `DESC` rồi kết luận index hỗ trợ mọi tổ hợp `ASC`/`DESC`.

### 7. LIMIT, top-N và phân trang

Descending index thường đem lại lợi ích rõ khi truy vấn chỉ cần một số lượng nhỏ hàng đầu:

```sql
SELECT id, score, achieved_at
FROM leaderboard
WHERE season_id = 2026
ORDER BY score DESC, achieved_at ASC, id ASC
LIMIT 20;
```

Nếu index phù hợp, InnoDB có thể định vị vùng key theo `season_id`, đọc theo đúng thứ tự và dừng khi đủ hàng. Khi không có index phù hợp, MySQL có thể phải thu thập các hàng ứng viên rồi sort; `LIMIT` có thể giúp giảm bộ nhớ/chi phí của thuật toán top-N nhưng không loại bỏ việc xem xét các hàng phù hợp.

Với phân trang sâu, `LIMIT offset, count` có thể phải bỏ qua nhiều entry trước khi trả trang cần thiết. Có thể dùng keyset pagination dựa trên toàn bộ khóa sắp xếp để tiếp tục từ hàng cuối trang trước. Với thứ tự `score DESC, achieved_at ASC, id ASC`, điều kiện tiếp theo có dạng:

```sql
SELECT id, score, achieved_at
FROM leaderboard
WHERE season_id = 2026
  AND (
      score < :last_score
      OR (score = :last_score AND achieved_at > :last_achieved_at)
      OR (
          score = :last_score
          AND achieved_at = :last_achieved_at
          AND id > :last_id
      )
  )
ORDER BY score DESC, achieved_at ASC, id ASC
LIMIT 20;
```

Các placeholder `:last_score`, `:last_achieved_at`, `:last_id` là giá trị ứng dụng bind từ hàng cuối trang trước. Điều kiện phải phản ánh đúng hướng từng key part; dùng một phép so sánh tuple đơn giản theo cùng một chiều có thể sai khi hướng sắp xếp hỗn hợp. Khóa cuối nên duy nhất để không bỏ sót hoặc lặp hàng giữa các trang.

### 8. NULL, collation và biểu thức ORDER BY

Hướng index phải phù hợp với cách MySQL sắp xếp giá trị. Với thứ tự mặc định của MySQL, `NULL` đứng trước giá trị không NULL trong `ASC` và đứng sau trong `DESC`. Nếu ứng dụng cần thứ tự NULL riêng, ví dụ luôn đưa NULL xuống cuối bất kể hướng, có thể phải dùng biểu thức `CASE` hoặc một cột sinh/functional index phù hợp.

Ví dụ:

```sql
SELECT id, published_at
FROM article
ORDER BY
    (published_at IS NULL) ASC,
    published_at DESC,
    id ASC;
```

Index chỉ gồm `(published_at DESC, id ASC)` không nhất thiết đáp ứng toàn bộ thứ tự vì biểu thức `(published_at IS NULL)` là key part đầu tiên. Nếu đây là truy vấn quan trọng, có thể tạo generated column biểu diễn cờ NULL và index theo đúng các key part, sau đó kiểm tra optimizer có dùng được index hay không.

Tương tự, `ORDER BY LOWER(name)` hoặc sắp xếp theo một collation khác với index có thể cần tính toán/sort bổ sung. Functional index hoặc generated column có thể giúp khi biểu thức được hỗ trợ và khớp với truy vấn. Tránh bọc cột trong hàm nếu không có lý do và không có index tương ứng.

### 9. ORDER BY với JOIN và nhiều bảng

Khi truy vấn JOIN, thứ tự dữ liệu của một bảng riêng lẻ không bảo đảm thứ tự kết quả sau join. Optimizer có thể chọn thứ tự join khác nhau và cần sort sau khi kết hợp hàng. Index trên bảng dẫn đầu có thể giúp lọc và sắp xếp, nhưng khả năng loại bỏ sort phụ thuộc join order, điều kiện join, cardinality và các cột `ORDER BY`.

Ví dụ:

```sql
SELECT o.id, o.total, c.name
FROM orders AS o
JOIN customers AS c ON c.id = o.customer_id
WHERE o.status = 'paid'
ORDER BY o.total DESC, o.created_at ASC, o.id ASC
LIMIT 50;
```

Một index tiềm năng trên bảng `orders`:

```sql
CREATE INDEX idx_orders_status_total_date
ON orders (status ASC, total DESC, created_at ASC, id ASC);
```

Index này có thể hỗ trợ lọc và thứ tự trên `orders`; bảng `customers` cần index phù hợp cho khóa join (thường là primary key `id`). Tuy vậy, nếu optimizer chọn một join plan khác hoặc phải xử lý điều kiện bổ sung, vẫn có thể xuất hiện sort. Phải kiểm tra bằng `EXPLAIN` trên truy vấn hoàn chỉnh.

### 10. Chi phí và giới hạn của descending index

Mỗi index bổ sung làm tăng dung lượng và chi phí ghi. Descending index cũng cần được duy trì khi insert, delete hoặc update key part. Trước khi tạo index, cân nhắc:

- Truy vấn nào thực sự cần thứ tự hỗn hợp và tần suất chạy.
- Tỷ lệ hàng được lọc, số hàng trả về và độ chọn lọc của các key part đầu.
- Khả năng index hiện có đã phục vụ thứ tự bằng scan xuôi/ngược hay chưa.
- Kích thước index, độ rộng khóa, buffer pool và chi phí ghi bổ sung.
- Truy vấn có cần covering index hay chỉ cần index để lọc/sắp xếp rồi lookup hàng.

Trong InnoDB, change buffering không áp dụng cho secondary index có key part descending. Với workload ghi nhiều, điều này có thể ảnh hưởng chi phí I/O so với secondary index tăng dần tương đương. Hãy benchmark theo đúng mẫu ghi/đọc thực tế trước khi triển khai rộng.

Không tạo hai index chỉ khác hướng nếu không có truy vấn thực sự cần cả hai thứ tự. Một index có thể phục vụ thứ tự đảo hoàn toàn bằng scan ngược, vì vậy hãy kiểm tra khả năng tái sử dụng index hiện hữu trước.

### 11. Kiểm tra index và kế hoạch thực thi

Xem định nghĩa index:

```sql
SHOW CREATE TABLE leaderboard;

SHOW INDEX FROM leaderboard;
```

Trong MySQL, `INFORMATION_SCHEMA.STATISTICS.COLLATION` thường cho biết hướng key part: `A` là ascending, `D` là descending; giá trị `NULL` có thể xuất hiện với loại index không có thứ tự như spatial index.

```sql
SELECT
    INDEX_NAME,
    SEQ_IN_INDEX,
    COLUMN_NAME,
    COLLATION,
    CARDINALITY
FROM information_schema.statistics
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'leaderboard'
ORDER BY INDEX_NAME, SEQ_IN_INDEX;
```

Kiểm tra truy vấn:

```sql
EXPLAIN
SELECT id, player_name, score, achieved_at
FROM leaderboard
WHERE season_id = 2026
ORDER BY score DESC, achieved_at ASC, id ASC
LIMIT 20;
```

Quan sát `key`, `type`, `rows`, `filtered` và `Extra`. Nếu `Extra` có `Using filesort`, MySQL đang cần một bước sort bổ sung cho kế hoạch đó. Tên `filesort` không có nghĩa chắc chắn sort ra file trên đĩa; thuật toán có thể sử dụng bộ nhớ hoặc file tạm tùy kích thước và cấu hình.

Trên MySQL 8.0.18 trở lên, `EXPLAIN ANALYZE` thực thi truy vấn và báo thời gian/số hàng thực tế ở các iterator:

```sql
EXPLAIN ANALYZE
SELECT id, player_name, score, achieved_at
FROM leaderboard
WHERE season_id = 2026
ORDER BY score DESC, achieved_at ASC, id ASC
LIMIT 20;
```

Chỉ dùng `EXPLAIN ANALYZE` khi chấp nhận việc câu truy vấn thực sự chạy và có thể tiêu thụ tài nguyên tương ứng. Đối chiếu ước lượng với số hàng/thời gian thực tế để phát hiện sai lệch thống kê hoặc kế hoạch không như mong muốn.

### 12. Quy trình thiết kế và benchmark

1. Viết truy vấn thật với điều kiện `WHERE`, toàn bộ danh sách `ORDER BY` và `LIMIT`.
2. Ghi hướng `ASC`/`DESC` cho từng key part, bao gồm cột tie-breaker duy nhất.
3. Đặt các cột lọc bằng phù hợp ở đầu index; tiếp theo là các key part phục vụ thứ tự.
4. Kiểm tra index hiện tại có thể phục vụ bằng scan xuôi hoặc đảo ngược toàn bộ hay không.
5. Tạo index thử nghiệm và chạy `EXPLAIN`; xác nhận key được chọn, số hàng quét và có `Using filesort` hay không.
6. Dùng `EXPLAIN ANALYZE` và benchmark với phân bố dữ liệu gần production; đo latency p50/p95/p99, CPU, I/O và chi phí insert/update.
7. So sánh với kế hoạch trước khi thêm index; giữ index mới chỉ khi lợi ích đọc/sắp xếp lớn hơn chi phí lưu trữ và ghi.

Một benchmark chỉ chạy một truy vấn trên buffer pool nóng có thể không đại diện cho tải thật. Nên kiểm tra cả trường hợp cache nóng/lạnh hợp lý, nhiều giá trị filter, dữ liệu trùng nhiều ở key part đầu và workload ghi đồng thời.

### 13. Checklist trước khi tạo descending index

1. Có truy vấn quan trọng dùng `ORDER BY` hỗn hợp ASC/DESC hay không?
2. MySQL đang chạy phiên bản 8.0 hỗ trợ descending index thực sự hay phiên bản cũ bỏ qua hướng `DESC`?
3. Thứ tự key part và hướng của index có khớp với `ORDER BY` theo scan xuôi hoặc đảo ngược toàn bộ không?
4. Các key part đứng trước đã được cố định bằng điều kiện phù hợp chưa?
5. Có cần khóa tie-breaker duy nhất để phân trang ổn định không?
6. NULL, collation, biểu thức hoặc JOIN có làm thứ tự khác với index không?
7. `EXPLAIN` và `EXPLAIN ANALYZE` có xác nhận lợi ích thực tế không?
8. Chi phí dung lượng, buffer pool, DML và change buffering có chấp nhận được không?

Descending index cho phép InnoDB lưu hướng sắp xếp riêng trên từng key part, nhờ đó hỗ trợ các truy vấn có nhiều chiều ASC/DESC mà index tăng dần thông thường không thể cung cấp chỉ bằng một lần quét ngược. Thiết kế hiệu quả cần khớp điều kiện lọc, leftmost prefix, thứ tự đầy đủ, LIMIT và workload thực tế; `EXPLAIN` cùng benchmark là bước xác nhận cuối cùng.
