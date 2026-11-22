# Bộ tối ưu và thống kê

## Optimizer trace và cách đối chiếu quyết định tối ưu

`EXPLAIN` cho biết kế hoạch mà MySQL chọn, nhưng thường không cho thấy đầy đủ những phương án mà optimizer đã cân nhắc rồi loại bỏ. Khi cần hiểu vì sao MySQL chọn table scan thay vì index, chọn thứ tự JOIN nào, không dùng một range scan hoặc phải sắp xếp bổ sung, có thể bật **optimizer trace**. Trace ghi lại các bước chuẩn bị và tối ưu hóa câu lệnh, bao gồm nhiều ứng viên truy cập, ước lượng hàng, chi phí và lý do một số phương án được chọn hoặc bị loại.

Optimizer trace là công cụ giải thích quyết định lập kế hoạch. Nó không đo thời gian chạy thực tế và không thay thế `EXPLAIN ANALYZE`, slow query log hay Performance Schema. Muốn tìm nguyên nhân một truy vấn chậm, cần đối chiếu trace với kế hoạch cuối cùng, thống kê dữ liệu và số liệu thực thi.

### 1. Optimizer trace trả lời câu hỏi gì?

Trace hữu ích khi đã có một truy vấn cụ thể và muốn biết optimizer đã đi đến quyết định như thế nào. Một số câu hỏi điển hình:

- Vì sao optimizer chọn `ALL` (full table scan) dù bảng có index phù hợp về mặt cột?
- Vì sao một index xuất hiện trong danh sách ứng viên nhưng không được chọn?
- Vì sao optimizer chọn thứ tự JOIN A trước B thay vì B trước A?
- Vì sao truy vấn cần `filesort` hoặc temporary table dù đã có index?
- Vì sao điều kiện `WHERE` không tạo được range scan?
- Vì sao sau khi cập nhật thống kê, optimizer chọn kế hoạch khác?
- Một thay đổi `optimizer_switch`, index hoặc cách viết điều kiện đã tác động đến quyết định nào?

Trace cho thấy các bước optimizer đã thực hiện và các ước lượng dùng để so sánh. Nó có thể giúp hình thành giả thuyết về nguyên nhân, nhưng cần xác nhận giả thuyết bằng dữ liệu thực tế và phép đo.

### 2. Bật trace và lấy kết quả trong cùng session

Optimizer trace được điều khiển bằng các biến session. Hãy bật trace trước khi chạy câu lệnh cần phân tích, chạy truy vấn, đọc trace ngay trong cùng kết nối rồi tắt trace:

```sql
SET SESSION optimizer_trace = 'enabled=on';
SET SESSION optimizer_trace_max_mem_size = 1048576;

SELECT id, customer_id, created_at, total
FROM orders
WHERE status = 'paid'
  AND created_at >= '2026-01-01'
  AND created_at < '2026-02-01'
ORDER BY created_at DESC
LIMIT 100;

SELECT
    QUERY,
    MISSING_BYTES_BEYOND_MAX_MEM_SIZE,
    INSUFFICIENT_PRIVILEGES,
    TRACE
FROM INFORMATION_SCHEMA.OPTIMIZER_TRACE;

SET SESSION optimizer_trace = 'enabled=off';
```

Trong ví dụ, `optimizer_trace_max_mem_size` đặt giới hạn bộ nhớ cho nội dung trace của session. Có thể đọc JSON dễ hơn bằng `JSON_PRETTY`:

```sql
SELECT
    QUERY,
    MISSING_BYTES_BEYOND_MAX_MEM_SIZE,
    INSUFFICIENT_PRIVILEGES,
    JSON_PRETTY(TRACE) AS TRACE_PRETTY
FROM INFORMATION_SCHEMA.OPTIMIZER_TRACE;
```

Các điểm cần nhớ:

1. Bật trace trước câu lệnh cần xem; truy vấn chạy trước khi bật sẽ không có trace tương ứng.
2. Đọc `INFORMATION_SCHEMA.OPTIMIZER_TRACE` ngay sau câu lệnh cần phân tích và trong cùng session. Không chuyển sang một kết nối khác trong connection pool.
3. Nếu trace bị cắt do giới hạn bộ nhớ, `MISSING_BYTES_BEYOND_MAX_MEM_SIZE` sẽ cho biết còn bao nhiêu byte không được lưu. Tăng giới hạn vừa đủ rồi chạy lại.
4. `INSUFFICIENT_PRIVILEGES` báo tình trạng trace không thể hiển thị đầy đủ do quyền truy cập.
5. Tắt trace sau khi hoàn tất để tránh ghi trace cho những câu lệnh không cần phân tích.

Nếu muốn xem kế hoạch mà không chạy câu `SELECT` thật, có thể bật trace rồi chạy `EXPLAIN` cho câu truy vấn. `EXPLAIN ANALYZE` thì thực sự thực thi câu lệnh được phân tích; chỉ dùng khi có thể chấp nhận chi phí chạy truy vấn.

### 3. Đọc cấu trúc tổng thể của trace

Trace thường là JSON có trường `steps`. Với một câu `SELECT`, các phần cấp cao thường gặp gồm:

| Phần | Ý nghĩa |
| --- | --- |
| `join_preparation` | Chuẩn bị query block, mở rộng cú pháp và thực hiện một số biến đổi ban đầu |
| `join_optimization` | Tối ưu điều kiện, ước lượng hàng, đánh giá access path và thứ tự JOIN |
| `join_execution` | Thông tin liên quan giai đoạn thực thi nếu loại câu lệnh và phiên bản ghi nhận phần này |

Trong `join_optimization`, các bước con thường chứa thông tin như:

- `condition_processing`: biến đổi và đơn giản hóa điều kiện.
- `table_dependencies`: quan hệ phụ thuộc giữa các bảng trong query block.
- `ref_optimizer_key_uses`: các khả năng dùng index theo phép so sánh tham chiếu.
- `rows_estimation`: ước lượng số hàng và đánh giá range access.
- `considered_execution_plans`: các phương án truy cập và thứ tự JOIN được cân nhắc.
- `attaching_conditions_to_tables`: điều kiện được gắn vào từng bảng trong kế hoạch.
- `refine_plan` hoặc các bước hoàn thiện kế hoạch: điều chỉnh kế hoạch đã chọn.

Tên, cấu trúc và mức chi tiết của các node có thể khác theo phiên bản MySQL, loại câu lệnh và tính năng optimizer được sử dụng. Hãy đọc trace như một cây quyết định có cấu trúc, không phụ thuộc cứng vào một đường dẫn JSON duy nhất.

### 4. Bước join_preparation: optimizer đã chuẩn hóa truy vấn ra sao?

`join_preparation` thường cho thấy câu lệnh sau khi MySQL mở rộng cú pháp và chuẩn bị query block. Một số node có thể gặp:

- `expanded_query`: dạng truy vấn đã được mở rộng, ví dụ bổ sung biểu thức hoặc chuẩn hóa cách tham chiếu cột.
- Các bước biến đổi subquery, view hoặc derived table nếu áp dụng.
- Thông tin về query block và cấu trúc truy vấn sau chuẩn bị.

Phần này hữu ích khi truy vấn có view, subquery, biểu thức hoặc nhiều điều kiện lồng nhau. Nó giúp xác định optimizer thực sự đang tối ưu cấu trúc nào sau các phép biến đổi ban đầu.

Ví dụ, điều kiện có biểu thức hằng có thể được đơn giản hóa trước khi chọn access path. Nếu truy vấn qua view, hãy kiểm tra view được merge vào query block hay được xử lý như một derived table/materialized result. Cách xử lý đó có thể làm thay đổi tập index có thể sử dụng và thứ tự JOIN.

### 5. condition_processing: điều kiện được biến đổi thế nào?

Optimizer có thể thực hiện các phép biến đổi logic để đơn giản hóa điều kiện. Trace có thể thể hiện các bước như:

- `equality_propagation`: truyền các đẳng thức qua những biểu thức tương đương.
- `constant_propagation`: thay biểu thức bằng giá trị hằng đã biết.
- `trivial_condition_removal`: loại bỏ điều kiện hiển nhiên hoặc không còn cần thiết.

Ví dụ:

```sql
SELECT o.id, o.total
FROM orders AS o
JOIN customers AS c ON c.id = o.customer_id
WHERE c.id = 42
  AND o.status = 'paid';
```

Từ `c.id = 42` và điều kiện JOIN `c.id = o.customer_id`, optimizer có thể suy ra điều kiện tương đương trên `o.customer_id`. Điều này có thể mở ra access path bằng index trên bảng `orders` mà người viết không nêu trực tiếp trong `WHERE`.

Khi đọc trace, hãy xem điều kiện đầu vào và điều kiện sau biến đổi. Nếu một điều kiện bị loại hoặc được thay bằng biểu thức khác, cần hiểu lý do trước khi kết luận optimizer đã bỏ qua điều kiện nghiệp vụ.

### 6. rows_estimation và range_analysis: optimizer ước lượng hàng ra sao?

Đây là một trong những khu vực quan trọng nhất khi điều tra lựa chọn index. Optimizer cần ước lượng số hàng mà mỗi access path phải đọc để tính chi phí. Trace có thể chứa:

- `potential_range_indexes`: các index có thể tham gia range analysis và trạng thái có thể dùng.
- `range_analysis`: quá trình đánh giá điều kiện có thể tạo range scan.
- `range_scan_alternatives`: các phương án range scan trên từng index, gồm ước lượng hàng và chi phí.
- `analyzing_roworder_intersect` hoặc thông tin index merge nếu optimizer xem xét kết hợp nhiều index.
- `chosen_range_access_summary`: tóm tắt phương án range được chọn nếu có.

Không phải mọi truy vấn đều có đủ các node trên. Nếu điều kiện không tạo được range hợp lệ, optimizer có thể loại một index trước khi so sánh chi phí range scan.

Ví dụ, bảng `orders` có các index:

```sql
CREATE TABLE orders (
    id BIGINT NOT NULL PRIMARY KEY,
    customer_id BIGINT NOT NULL,
    status VARCHAR(20) NOT NULL,
    created_at DATETIME NOT NULL,
    total DECIMAL(12, 2) NOT NULL,
    KEY idx_status_created (status, created_at),
    KEY idx_created (created_at)
) ENGINE = InnoDB;
```

Truy vấn lọc theo trạng thái và khoảng thời gian:

```sql
SELECT id, customer_id, created_at, total
FROM orders
WHERE status = 'paid'
  AND created_at >= '2026-01-01'
  AND created_at < '2026-02-01'
ORDER BY created_at DESC
LIMIT 100;
```

Khi đọc `range_analysis`, tìm `idx_status_created` và `idx_created`. Kiểm tra optimizer có tạo range cho từng index không, ước lượng bao nhiêu hàng phải đọc, chi phí ước lượng và phương án nào có `chosen` hoặc được tóm tắt là phương án tốt nhất. Với `status` được cố định bằng phép bằng, index ghép `(status, created_at)` có thể thu hẹp phạm vi theo thời gian và cung cấp thứ tự thời gian trong phạm vi trạng thái.

Nếu optimizer chọn `idx_created` hoặc table scan, không kết luận ngay đó là lỗi. Có thể trạng thái `paid` chiếm phần lớn bảng, khoảng thời gian quá rộng hoặc việc lookup clustered record khiến index ghép có chi phí cao hơn. Đối chiếu ước lượng hàng và cost trong trace với phân bố dữ liệu thực tế.

### 7. Vì sao index có thể bị loại dù cột xuất hiện trong WHERE?

Có index trên cột không đồng nghĩa mọi điều kiện dùng cột đó đều tạo được range scan. Một số nguyên nhân phổ biến:

1. Cột bị bọc trong hàm hoặc biểu thức không khớp functional index.
2. Kiểu dữ liệu so sánh dẫn tới chuyển đổi trên cột được index hóa.
3. Điều kiện không có dạng sargable để xác định khoảng index phù hợp.
4. Key part đứng trước trong index ghép không được cố định hoặc không thể dùng cho điều kiện.
5. Phạm vi điều kiện quá rộng khiến scan index rồi lookup hàng đắt hơn table scan.
6. Thống kê hoặc histogram không phản ánh đúng phân bố dữ liệu, khiến ước lượng sai.

Ví dụ điều kiện không thuận lợi cho index thông thường trên `created_at`:

```sql
SELECT id, created_at
FROM orders
WHERE DATE(created_at) = '2026-01-15';
```

Hàm `DATE()` được áp dụng lên cột nên index B-tree thông thường trên `created_at` không thể trực tiếp dùng một range đơn giản cho điều kiện này. Có thể viết lại thành khoảng nửa mở:

```sql
SELECT id, created_at
FROM orders
WHERE created_at >= '2026-01-15 00:00:00'
  AND created_at <  '2026-01-16 00:00:00';
```

Sau khi viết lại, chạy trace lại để xem `range_analysis` có tạo được khoảng trên `idx_created` hay không. So sánh trace trước và sau sẽ cho thấy thay đổi ở bước tạo range và access path được chọn.

### 8. considered_execution_plans: so sánh các kế hoạch truy cập và thứ tự JOIN

Với truy vấn nhiều bảng, optimizer phải chọn cách truy cập từng bảng và thứ tự JOIN. `considered_execution_plans` thường cho thấy các plan prefix và access path được đánh giá. Có thể bắt gặp các trường như `plan_prefix`, `table`, `best_access_path`, `considered_access_paths`, `cost_for_plan`, `rows_for_plan` hoặc `chosen`, tùy phiên bản và nhánh tối ưu hóa.

Ví dụ:

```sql
SELECT o.id, o.total, c.name
FROM customers AS c
JOIN orders AS o ON o.customer_id = c.id
WHERE c.region = 'south'
  AND o.created_at >= '2026-01-01'
ORDER BY o.created_at DESC
LIMIT 100;
```

Optimizer có thể cân nhắc:

- Đọc các khách hàng thuộc `region = 'south'` trước, sau đó lookup đơn hàng theo `customer_id`.
- Đọc đơn hàng trong khoảng thời gian trước, sau đó lookup khách hàng theo primary key.
- Chọn một access path khác nếu ước lượng số hàng hoặc chi phí thay đổi.

Trong trace, so sánh từng plan prefix, số hàng ước lượng sau khi nối, chi phí tích lũy và lý do plan bị loại. Nếu plan cuối bắt đầu từ `orders`, hãy xem trace đã ước lượng khoảng thời gian trên bảng này chọn lọc hơn tập khách hàng south hay chưa.

Thứ tự bảng trong câu SQL không nhất thiết là thứ tự thực thi. Với inner join, optimizer thường có thể đổi thứ tự join dựa trên cost. Outer join và các phụ thuộc ngữ nghĩa có thể giới hạn những thứ tự hợp lệ.

### 9. Đọc cost và rows đúng cách

Trace thường chứa các ước lượng `rows`, `cost`, `read_cost`, `eval_cost`, `prefix_cost`, `rows_for_plan` hoặc tên tương tự. Cần hiểu đây là giá trị phục vụ mô hình chi phí nội bộ, không phải thời gian mili giây.

| Giá trị | Cách diễn giải |
| --- | --- |
| `rows` | Số hàng optimizer ước lượng một access path sẽ đọc hoặc trả về ở một bước |
| `cost` | Chi phí ước lượng cho một phương án ở phạm vi node tương ứng |
| `read_cost` | Phần chi phí đọc dữ liệu/index theo mô hình cost |
| `eval_cost` | Phần chi phí đánh giá điều kiện hoặc xử lý hàng theo mô hình cost |
| `prefix_cost` | Chi phí tích lũy của plan prefix trong một số phần trace |
| `rows_for_plan` | Ước lượng số hàng của kế hoạch sau các bước đã nối |

Tên và cách phân rã cost phụ thuộc phiên bản và loại access path. Không so sánh trực tiếp một giá trị cost giữa hai máy chủ có cấu hình, thống kê hoặc phiên bản khác nhau như thể đó là số đo thời gian. Dùng cost để hiểu optimizer so sánh phương án trong cùng ngữ cảnh; dùng runtime metrics để đo hiệu năng thực.

Nếu `rows` ước lượng lệch xa số hàng thực tế, hãy kiểm tra thống kê index, histogram, phân bố lệch (skew), tương quan giữa các cột và điều kiện truy vấn. Optimizer có thể chọn một plan hợp lý theo dữ liệu thống kê mà nó nhìn thấy, nhưng dữ liệu thống kê đó có thể chưa đủ chính xác.

### 10. Đối chiếu trace với EXPLAIN và EXPLAIN ANALYZE

Bốn công cụ có vai trò khác nhau:

| Công cụ | Trả lời câu hỏi | Có thực thi truy vấn SELECT? |
| --- | --- | --- |
| `EXPLAIN` | Kế hoạch cuối cùng optimizer chọn là gì? | Không chạy phần truy vấn SELECT để trả kết quả |
| `EXPLAIN FORMAT=JSON` | Kế hoạch cuối cùng và nhiều chi tiết ước lượng ở dạng JSON là gì? | Không chạy phần truy vấn SELECT để trả kết quả |
| Optimizer trace | Optimizer đã cân nhắc những phương án nào và vì sao chọn/bỏ chúng? | Trace ghi quyết định tối ưu; bản thân việc lấy trace không phải phép đo runtime |
| `EXPLAIN ANALYZE` | Các iterator thực tế chạy bao lâu, lặp bao nhiêu lần và trả bao nhiêu hàng? | Có, truy vấn được thực thi |

Quy trình đọc nên đi từ kết quả tổng quan tới nguyên nhân:

1. Chạy `EXPLAIN` để xác định bảng, access type, key, rows ước lượng và `Extra`.
2. Dùng optimizer trace để xem các ứng viên và lý do chọn access path hoặc join order.
3. Dùng `EXPLAIN ANALYZE` trên truy vấn có thể chạy an toàn để so sánh số hàng và thời gian thực tế với ước lượng.
4. Nếu plan đúng nhưng truy vấn vẫn chậm, điều tra I/O, buffer pool, lock wait, concurrency, network và lượng dữ liệu trả về.

Ví dụ:

```sql
EXPLAIN FORMAT=JSON
SELECT id, customer_id, created_at, total
FROM orders
WHERE status = 'paid'
  AND created_at >= '2026-01-01'
  AND created_at < '2026-02-01'
ORDER BY created_at DESC
LIMIT 100;

EXPLAIN ANALYZE
SELECT id, customer_id, created_at, total
FROM orders
WHERE status = 'paid'
  AND created_at >= '2026-01-01'
  AND created_at < '2026-02-01'
ORDER BY created_at DESC
LIMIT 100;
```

`EXPLAIN ANALYZE` có từ MySQL 8.0.18. Cần thận trọng với truy vấn nặng vì nó chạy thật; không dùng nó như một lệnh chỉ xem kế hoạch trên production mà không đánh giá tải.

### 11. Dùng trace để điều tra quyết định chọn table scan

Giả sử có index `idx_status(status)` nhưng truy vấn sau vẫn chọn full table scan:

```sql
SELECT id, status, total
FROM orders
WHERE status = 'paid';
```

Trace có thể cho thấy optimizer đã xem xét index, ước lượng số hàng `paid` chiếm tỷ lệ lớn, rồi kết luận đọc phần lớn secondary index và quay về clustered index để lấy `total` đắt hơn quét tuần tự clustered index. Đây là quyết định có thể hợp lý nếu điều kiện ít chọn lọc.

Hãy kiểm tra:

- `potential_range_indexes`: index có được xem xét không?
- `range_scan_alternatives`: range scan có hợp lệ và ước lượng bao nhiêu hàng?
- `considered_access_paths`: table scan, index scan hoặc ref/range có chi phí nào?
- `chosen`/`cause` hoặc phần tóm tắt tương đương: phương án nào được chọn và vì sao?
- Thống kê `CARDINALITY`, histogram và số hàng thực tế có phản ánh đúng tỷ lệ `paid` không?

Không nên dùng `FORCE INDEX` chỉ để ép optimizer dùng index sau khi thấy table scan. Trước tiên xác nhận truy vấn có thật sự cần index, có thể tạo covering index phù hợp hay không, và table scan có thực sự chậm trên dữ liệu hiện tại không. Một full scan đôi khi là kế hoạch tốt nhất.

### 12. Dùng trace để điều tra filesort hoặc temporary table

Khi `EXPLAIN` cho thấy `Using filesort` hoặc `Using temporary`, hãy kiểm tra điều kiện lọc, thứ tự cột và hướng của index. Optimizer có thể không dùng được thứ tự index vì:

- Key part đứng trước cột sắp xếp chưa được cố định.
- Hướng ASC/DESC của các key part không khớp với `ORDER BY` theo scan xuôi hoặc ngược.
- Truy vấn sắp xếp theo biểu thức hoặc collation không tương thích với index.
- JOIN order hoặc cách materialize derived table khiến thứ tự index không còn phù hợp.
- Lợi ích của index không đủ bù chi phí lookup theo ước lượng.

Trace có thể chỉ ra ứng viên ordering và quyết định liên quan trong các bước tối ưu query block. Cấu trúc cụ thể phụ thuộc phiên bản; hãy tìm các node liên quan tới ordering, `filesort`, grouping, temporary table hoặc access path thay vì dựa vào một đường dẫn cố định.

Sau khi thay đổi index, chạy lại cùng câu lệnh và đối chiếu trace. Nếu `Using filesort` biến mất nhưng runtime không cải thiện, có thể truy vấn bị giới hạn bởi I/O khác, số hàng trả về, lookup ngẫu nhiên hoặc chi phí JOIN.

### 13. So sánh trace trước và sau khi cập nhật thống kê

Optimizer quyết định dựa trên thống kê index và các thông tin phân bố dữ liệu mà nó có. Nếu thống kê cũ hoặc thiếu chi tiết, số hàng ước lượng có thể lệch.

Ví dụ cập nhật thống kê index:

```sql
ANALYZE TABLE orders;
```

Với cột có phân bố lệch đáng kể, MySQL hỗ trợ histogram:

```sql
ANALYZE TABLE orders
UPDATE HISTOGRAM ON status WITH 32 BUCKETS;
```

Có thể xem histogram trong `INFORMATION_SCHEMA.COLUMN_STATISTICS` trên phiên bản hỗ trợ. Khi cần loại bỏ histogram:

```sql
ANALYZE TABLE orders
DROP HISTOGRAM ON status;
```

Để đánh giá tác động, giữ nguyên câu truy vấn và tham số, lấy trace trước khi cập nhật thống kê, chạy `ANALYZE TABLE` hoặc thay đổi histogram, sau đó lấy trace lại. So sánh:

1. Ước lượng hàng trong `rows_estimation`.
2. Range và index candidate được xem xét.
3. Chi phí của từng access path.
4. Thứ tự JOIN được chọn.
5. Kế hoạch cuối trong `EXPLAIN` và số liệu thực tế trong `EXPLAIN ANALYZE`.

Histogram có thể cải thiện ước lượng cho phân bố một cột, nhưng không mô tả đầy đủ tương quan giữa nhiều cột. Nếu `status` và `created_at` có tương quan theo thời gian, histogram đơn cột có thể chưa đủ để ước lượng chính xác kết hợp điều kiện.

### 14. So sánh trace khi thay đổi optimizer_switch hoặc index

Khi cần kiểm tra một tính năng optimizer, có thể thay đổi `optimizer_switch` ở phạm vi session trong môi trường thử nghiệm:

```sql
SELECT @@SESSION.optimizer_switch;

SET SESSION optimizer_switch = 'index_merge=off';

-- Bật optimizer trace, chạy truy vấn và lấy trace để so sánh.

SET SESSION optimizer_switch = DEFAULT;
```

Đây chỉ là ví dụ kiểm tra `index_merge`; tên tùy chọn và giá trị hợp lệ phụ thuộc phiên bản. Không thay đổi GLOBAL hoặc tắt hàng loạt tính năng trên production chỉ vì một trace cho thấy optimizer chọn plan không mong muốn.

Có thể dùng invisible index để thử ảnh hưởng của việc loại một index khỏi lựa chọn optimizer mà chưa drop vật lý. Trace trước và sau khi thay visibility giúp xác định optimizer chuyển sang access path nào. Lưu ý invisible index vẫn được duy trì khi ghi; phép thử này đánh giá lựa chọn đọc của optimizer, không đo chi phí ghi sau khi index bị xóa.

Khi so sánh, chỉ thay đổi một yếu tố mỗi lần. Nếu đồng thời thay index, histogram, optimizer_switch và SQL, sẽ khó xác định nguyên nhân làm plan đổi.

### 15. Giới hạn và những điều trace không thể kết luận

Optimizer trace có giá trị chẩn đoán nhưng có những giới hạn:

- Trace mô tả quyết định tối ưu và ước lượng, không phải số đo thời gian thực thi.
- Trace có thể bị cắt bởi `optimizer_trace_max_mem_size`; phải kiểm tra `MISSING_BYTES_BEYOND_MAX_MEM_SIZE`.
- Một số chi tiết có thể không xuất hiện do quyền, loại câu lệnh, tính năng hoặc phiên bản.
- Tên node và cấu trúc JSON có thể thay đổi; công cụ phân tích tự động cần chịu được node thiếu hoặc khác cấu trúc.
- Optimizer có thể chọn đúng theo thống kê nhưng runtime vẫn chậm do cache miss, I/O, lock wait, contention, network hoặc dữ liệu trả về quá lớn.
- Một truy vấn chạy nhanh trong lần đo thứ hai có thể chỉ do page đã nằm trong buffer pool; không được quy toàn bộ khác biệt cho plan.
- Cost nội bộ không phải đơn vị mili giây và không thể so sánh tùy tiện giữa máy chủ khác cấu hình.

Không lưu trace vô thời hạn nếu nó chứa câu SQL và giá trị literal nhạy cảm. Khi chia sẻ trace để điều tra, cần tuân thủ chính sách bảo vệ dữ liệu và ẩn thông tin nhận dạng phù hợp.

### 16. Quy trình chẩn đoán có thể lặp lại

1. **Chụp baseline:** lưu SQL, tham số, phiên bản MySQL, `optimizer_switch`, thống kê bảng và `EXPLAIN` hiện tại.
2. **Bật trace:** dùng đúng session, tăng giới hạn bộ nhớ nếu cần và chạy đúng câu lệnh cần phân tích.
3. **Đọc trace:** xem `join_preparation`, `condition_processing`, `rows_estimation`, `range_analysis` và `considered_execution_plans`.
4. **Xác định điểm quyết định:** tìm ứng viên bị loại, số hàng/cost ước lượng và plan cuối cùng được chọn.
5. **Đối chiếu dữ liệu:** kiểm tra cardinality, histogram, skew, tương quan cột và tính sargable của điều kiện.
6. **Thay đổi một yếu tố:** SQL, index, thống kê hoặc optimizer setting; ghi rõ giả thuyết trước khi thử.
7. **Đo lại:** so sánh trace, `EXPLAIN`, `EXPLAIN ANALYZE`, latency và tài nguyên.
8. **Giữ hoặc hoàn tác:** chỉ giữ thay đổi nếu cải thiện được workload đại diện mà không gây hồi quy đáng kể ở các truy vấn khác.

### 17. Checklist khi đọc optimizer trace

1. Trace có đúng câu SQL và đúng session không?
2. `MISSING_BYTES_BEYOND_MAX_MEM_SIZE` có bằng 0 không?
3. `INSUFFICIENT_PRIVILEGES` có báo trace thiếu thông tin không?
4. Query đã được mở rộng/biến đổi thế nào trong `join_preparation`?
5. Điều kiện trong `condition_processing` có được truyền hoặc đơn giản hóa như dự kiến không?
6. Index nào xuất hiện trong `potential_range_indexes` và `range_scan_alternatives`?
7. Số hàng và cost ước lượng có hợp lý với dữ liệu thật không?
8. Những access path và join order nào được cân nhắc, phương án nào bị loại?
9. Kế hoạch cuối có khớp với `EXPLAIN` không?
10. `EXPLAIN ANALYZE` và runtime metrics có xác nhận lợi ích thực tế không?

Optimizer trace giúp chuyển câu hỏi “MySQL chọn plan này vì sao?” thành một quá trình điều tra có bằng chứng: xem điều kiện sau biến đổi, index/range được cân nhắc, số hàng và chi phí ước lượng, thứ tự JOIN rồi đối chiếu với kế hoạch cuối và số liệu thực thi. Dùng trace cùng `EXPLAIN`, `EXPLAIN ANALYZE` và thống kê đúng cách sẽ giúp điều chỉnh SQL, index và thống kê có căn cứ hơn.
