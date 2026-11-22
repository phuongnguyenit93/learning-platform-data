# Đánh giá chỉ mục và kế hoạch thực thi từ phía cơ sở dữ liệu trong JDBC

Một truy vấn JDBC có thể được viết bằng `PreparedStatement`, dùng tham số đúng cách và đóng `ResultSet` đầy đủ nhưng vẫn chậm. Nguyên nhân đôi khi không nằm trong Java mà ở phía cơ sở dữ liệu: **đọc quá nhiều hàng, không dùng được chỉ mục (index), sắp xếp tốn kém, thống kê lỗi thời hoặc chọn một kế hoạch thực thi không phù hợp với tham số thực tế**.

Lập trình viên cần biết cách kiểm tra **database đã thực sự thực thi SQL như thế nào**, thay vì chỉ suy luận rằng “đã có index thì truy vấn phải nhanh”. Với PostgreSQL, ta thường dùng `EXPLAIN` và `EXPLAIN (ANALYZE, BUFFERS)`; các hệ quản trị khác có công cụ tương tự nhưng cú pháp, đơn vị chi phí và tên toán tử khác nhau.

Bài thuộc chương **Hiệu năng** của module JDBC. Mục tiêu là hình thành một quy trình lặp lại được: **đo từ JDBC → xác định câu SQL và tham số → xem kế hoạch phía DB → xây giả thuyết về index hoặc cách viết query → thay đổi có kiểm soát → đo lại toàn bộ**.

## 1. Vì sao cần xem kế hoạch thực thi?

Xét một hệ thống bán hàng nhiều tenant. Ứng dụng gọi SQL:

```sql
SELECT id, customer_id, total_amount, created_at
FROM sales_orders
WHERE tenant_id = ?
  AND created_at >= ?
  AND created_at < ?
ORDER BY created_at DESC, id DESC
LIMIT ?;
```

Khi có 50 triệu đơn hàng, để trả 20 đơn gần nhất của một tenant, DBMS có nhiều lựa chọn:

- Đọc lần lượt hàng trong bảng rồi lọc `tenant_id` và khoảng thời gian.
- Dùng index trên `tenant_id` để thu hẹp rồi lọc thời gian và sắp xếp.
- Dùng index ghép `(tenant_id, created_at DESC, id DESC)` để tìm đúng khoảng và duyệt theo thứ tự cần trả.
- Kết hợp index và các phép đọc heap, bitmap scan hoặc sắp xếp tùy thống kê và chi phí.

Cùng câu SQL nhưng lựa chọn tốt nhất có thể thay đổi theo **số hàng, phân bố tenant, độ chọn lọc, giá trị tham số, tình trạng cache và độ mới của thống kê**.

```text
SQL + tham số JDBC
       |
       v
  PostgreSQL planner
       |
       +-- thống kê số hàng / phân bố giá trị
       +-- các index khả dụng
       +-- điều kiện lọc / JOIN / ORDER BY / LIMIT
       +-- ước lượng chi phí I/O và CPU
       |
       v
  Execution plan (kế hoạch thực thi)
       |
       +-- Seq Scan / Index Scan / Bitmap Heap Scan
       +-- Sort / Hash Join / Nested Loop / Aggregate ...
       |
       v
  Số hàng thực tế + I/O + thời gian + dữ liệu trả về JDBC
```

**Index không được lựa chọn không đồng nghĩa index bị lỗi.** DBMS có thể cố ý chọn quét bảng vì truy vấn đọc phần lớn dữ liệu, bảng quá nhỏ, hoặc chi phí truy cập ngẫu nhiên qua index lớn hơn quét tuần tự. Kế hoạch cần được đánh giá dựa trên dữ liệu và workload thực, không dựa vào sự hiện diện của chữ `Index Scan`.

## 2. Chuẩn bị ví dụ: bảng, truy vấn và chỉ mục

Các lệnh sau sử dụng **PostgreSQL** để có một minh họa nhất quán. Không coi chúng là cú pháp dùng được nguyên vẹn trên mọi DBMS.

```sql
CREATE TABLE sales_orders (
    id           BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id    BIGINT NOT NULL,
    customer_id  BIGINT NOT NULL,
    status       VARCHAR(20) NOT NULL,
    created_at   TIMESTAMPTZ NOT NULL,
    total_amount NUMERIC(14, 2) NOT NULL
);

-- Index tối ưu theo giả thuyết cho truy vấn của bài:
CREATE INDEX idx_sales_orders_tenant_created_id
ON sales_orders (tenant_id, created_at DESC, id DESC);
```

Index ghép trên được chọn để phục vụ mô hình:

1. `tenant_id = ?` là điều kiện **bằng** trên cột đầu.
2. `created_at >= ? AND created_at < ?` là điều kiện **khoảng** trên cột thứ hai.
3. `ORDER BY created_at DESC, id DESC` tương ứng thứ tự các cột của index.
4. `LIMIT ?` cho phép DBMS dừng sớm khi đã tìm đủ hàng phù hợp, nếu kế hoạch và điều kiện cho phép.

Đây là một **giả thuyết kỹ thuật**, không phải lời hứa chắc chắn index sẽ xuất hiện trong kế hoạch. Với bảng rất nhỏ hoặc yêu cầu lấy gần như toàn bộ hàng, PostgreSQL có thể chọn `Seq Scan` và `Sort` dù index tồn tại.

### Dữ liệu mẫu để học và dữ liệu đủ lớn để benchmark

Có thể thêm vài hàng để kiểm tra kết quả SQL:

```sql
INSERT INTO sales_orders
    (tenant_id, customer_id, status, created_at, total_amount)
VALUES
    (7, 101, 'PAID', '2026-11-01T10:00:00Z', 120000.00),
    (7, 102, 'NEW',  '2026-11-02T09:00:00Z',  85000.00),
    (7, 103, 'PAID', '2026-11-03T08:00:00Z', 240000.00),
    (8, 201, 'NEW',  '2026-11-03T08:30:00Z', 170000.00);
```

**Không dùng bốn hàng này để kết luận index hiệu quả hay không.** Kế hoạch trên bảng tí hon gần như không đại diện cho production. Kiểm thử hiệu năng nên dùng dữ liệu đủ lớn, phân bố tenant/trạng thái/ngày tháng tương tự workload thực, cùng thống kê đã được cập nhật và cấu hình DB tương đương.

Trên môi trường lab, sau khi nạp lượng lớn dữ liệu hoặc tạo index, có thể chạy:

```sql
ANALYZE sales_orders;
```

`ANALYZE` giúp PostgreSQL cập nhật thống kê để planner ước lượng số hàng và độ chọn lọc tốt hơn. Nó **không bảo đảm** planner luôn chọn index, và việc cập nhật thống kê có thể làm kế hoạch thay đổi theo cả hai hướng.

## 3. Phân biệt `EXPLAIN` và `EXPLAIN ANALYZE`

Hai công cụ phục vụ những câu hỏi khác nhau:

| Công cụ PostgreSQL | Hoạt động | Trả lời câu hỏi |
|---|---|---|
| `EXPLAIN SELECT ...` | Lập kế hoạch, thường **không chạy** truy vấn SELECT | “Planner dự định làm gì?” |
| `EXPLAIN (FORMAT JSON) SELECT ...` | Xuất kế hoạch dưới dạng có cấu trúc | “Có thể phân tích/lưu kế hoạch bằng công cụ không?” |
| `EXPLAIN (ANALYZE) SELECT ...` | **Thực thi** SELECT rồi ghi lại số hàng/thời gian thực tế | “Truy vấn thực sự đã làm gì?” |
| `EXPLAIN (ANALYZE, BUFFERS) SELECT ...` | Thực thi và thêm thông tin buffer | “Tốn công đọc/ghi trang dữ liệu ở đâu?” |

Ví dụ:

```sql
EXPLAIN
SELECT id, customer_id, total_amount, created_at
FROM sales_orders
WHERE tenant_id = 7
ORDER BY created_at DESC, id DESC
LIMIT 20;
```

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT id, customer_id, total_amount, created_at
FROM sales_orders
WHERE tenant_id = 7
ORDER BY created_at DESC, id DESC
LIMIT 20;
```

**Cảnh báo quan trọng:** `EXPLAIN ANALYZE` **thực thi câu lệnh**. Nếu dùng với `INSERT`, `UPDATE`, `DELETE` hoặc những câu SQL có side effect, nó có thể **thật sự sửa dữ liệu**, chạy trigger và giữ khóa. Không thử trực tiếp trên production chỉ để xem kế hoạch.

Ngay cả với SELECT, `EXPLAIN ANALYZE` có thể chạy truy vấn rất lâu, thực thi function có side effect, gây tải I/O hoặc giữ tài nguyên. Nên chạy trên **database thử nghiệm**, với quyền/cấu hình và giới hạn thời gian phù hợp. Khi chỉ muốn ước lượng kế hoạch mà không phát SQL thực thi, ưu tiên `EXPLAIN` không có `ANALYZE`.

### 3.1. Chi phí ước lượng không phải mili giây

Một plan PostgreSQL có thể hiển thị:

```text
Index Scan using idx_sales_orders_tenant_created_id on sales_orders
  (cost=0.43..120.00 rows=50 width=40)
```

Trong đó:

- `cost=startup..total` là **đơn vị chi phí nội bộ của planner**, không phải dự đoán chính xác số mili giây.
- `rows` là **số hàng ước lượng** mà node phát ra theo mô hình thống kê.
- `width` là kích thước trung bình ước lượng của một hàng tại node, theo byte.
- Tên index cho biết kế hoạch dự kiến sử dụng index nào.

Không nên so sánh các con số `cost` như thể một plan có `cost=20` sẽ chạy đúng 20 ms. Công cụ tối ưu dùng cost để lựa chọn giữa các kế hoạch dưới những giả định của cấu hình; **phép đo thực tế** cần `EXPLAIN ANALYZE` hoặc latency ở ứng dụng.

## 4. Đọc những toán tử thường gặp của kế hoạch

Kế hoạch thực thi là một **cây toán tử**. Node phía dưới cung cấp hàng cho node phía trên. Người đọc cần nhận diện nơi DBMS đọc dữ liệu, lọc, JOIN, sắp xếp và tổng hợp.

| Toán tử PostgreSQL | Diễn giải | Điều cần xem |
|---|---|---|
| `Seq Scan` | Quét tuần tự bảng | Số hàng đọc/lọc, tỷ lệ dữ liệu cần, kích thước bảng |
| `Index Scan` | Dùng index tìm hàng rồi lấy dữ liệu cần thiết | `Index Cond`, số hàng trả, heap access |
| `Index Only Scan` | Cố gắng đáp ứng truy vấn từ index | `Heap Fetches`, cột được index bao phủ, visibility map |
| `Bitmap Index Scan` + `Bitmap Heap Scan` | Thu thập vị trí hàng từ index, đọc heap theo bitmap | Số trang heap, độ chọn lọc, `Recheck Cond` |
| `Sort` | Sắp xếp dữ liệu | Bộ nhớ, sort method, temp I/O, có được tránh nhờ index không |
| `Nested Loop` | Lặp tìm hàng bên trong theo hàng phía ngoài | Số `loops`, kết quả mỗi vòng, index phía trong |
| `Hash Join` | Xây hash table rồi ghép | Kích thước hash, batch, memory và số hàng |
| `Merge Join` | Ghép dữ liệu đã có thứ tự | Chi phí sort/index, số hàng |
| `Aggregate` / `HashAggregate` | Tính tổng hợp như `COUNT`, `SUM` | Số hàng đầu vào, memory, số nhóm |
| `Limit` | Dừng khi đạt giới hạn | Node phía dưới có thể ngừng sớm hay vẫn phải đọc/sort nhiều hàng |

### 4.1. `Seq Scan` không luôn là lỗi

Nếu bảng chỉ có vài trăm hàng, hoặc truy vấn trả 90% hàng, đọc bảng tuần tự có thể rẻ hơn duyệt index rồi đọc từng vị trí dữ liệu. Tạo index chỉ vì thấy `Seq Scan` có thể khiến hoạt động ghi chậm đi mà không giảm latency.

Cần hỏi: **truy vấn trả bao nhiêu hàng so với tổng dữ liệu, và bao nhiêu hàng bị đọc rồi loại bỏ?**

### 4.2. `Index Scan` không luôn là nhanh

Index được dùng nhưng truy vấn vẫn có thể chậm nếu:

- Điều kiện index chưa đủ chọn lọc, phải đọc rất nhiều hàng.
- Truy vấn lấy nhiều cột ngoài index, cần nhiều heap fetch ngẫu nhiên.
- Kế hoạch có sort, aggregate hoặc join đắt ở bước tiếp theo.
- Index bị cạnh tranh I/O, cache lạnh hoặc bảng/index bị bloat.
- Query chạy nhiều lần (N+1) dù mỗi lần rất nhanh.

Một index scan “đúng tên” không thể thay thế phép đo cuối cùng.

### 4.3. `Index Only Scan` có thể vẫn đọc heap

Với PostgreSQL, `Index Only Scan` chỉ tránh đọc heap khi thông tin cần đã có trong index **và** trạng thái hiển thị hàng (visibility) có thể được xác nhận thích hợp. Vì thế cần xem `Heap Fetches` trong plan thực tế; tên toán tử “Index Only” không chứng minh 100% không truy cập heap.

Nếu dùng `INCLUDE` để đưa thêm các cột đọc vào index, hãy cân nhắc kích thước index và chi phí cập nhật/ghi; covering index không miễn phí.

## 5. Đọc `EXPLAIN (ANALYZE, BUFFERS)` có phương pháp

Khi có plan thực tế, không chỉ nhìn dòng cuối có `Execution Time`. Đọc từ trên xuống để xác định phạm vi, rồi đi xuống nhánh tốn chi phí:

```text
Limit (actual time=... rows=20 loops=1)
  -> Index Scan using idx_sales_orders_tenant_created_id ...
       (actual time=... rows=20 loops=1)
       Index Cond: (tenant_id = 7 ...)
Planning Time: ...
Execution Time: ...
```

*Đây là bản minh họa cấu trúc, không phải kết quả chạy thật trên bốn hàng mẫu. Toán tử, thời gian và số hàng sẽ khác theo môi trường.*

Các trường nên đọc:

| Trường | Ý nghĩa | Câu hỏi thực hành |
|---|---|---|
| `actual time=start..end` | Thời gian trung bình/quan sát ở node theo cơ chế EXPLAIN, đơn vị ms | Node nào mất thời gian nhiều? |
| `rows` trong `actual` | Số hàng thực tế phát ra **mỗi lượt thực thi node** | Sai lệch bao nhiêu so với `rows` ước lượng? |
| `loops` | Số lần node được thực thi | Node bên trong Nested Loop bị chạy hàng nghìn lần không? |
| `Rows Removed by Filter` | Số hàng bị loại bởi điều kiện filter | Có thể đẩy điều kiện vào `Index Cond` không? |
| `Index Cond` | Điều kiện dùng được trong phần truy cập index | Index có phù hợp với các predicate chính không? |
| `Filter` | Điều kiện được kiểm tra sau bước truy cập của node | Có đang đọc quá nhiều hàng rồi mới lọc không? |
| `Sort Method` / `Disk` | Cách sort và dấu hiệu tràn ra disk | ORDER BY hoặc bộ nhớ có gây temp I/O? |
| `Buffers: shared hit` | Số block tìm thấy trong shared buffer cache của PostgreSQL | Truy vấn dùng nhiều block cache không? |
| `Buffers: shared read` | Block PostgreSQL phải đọc vào shared buffers | Có I/O nào cần khảo sát? |
| `temp read/written` | Block tạm đọc/ghi, thường liên quan sort/hash | Có spill? |
| `Planning Time` | Thời gian planner | Câu SQL phức tạp có tốn đáng kể phần lập kế hoạch không? |
| `Execution Time` | Thời gian thực thi được EXPLAIN báo | So với latency JDBC đầu cuối chênh bao nhiêu? |

**Chú ý khi tính hàng trong node lặp:** `actual rows` thường là số hàng trung bình cho một vòng, nên phải xét **`rows × loops`** khi đánh giá tổng công việc của node. Đừng nhìn `rows=1` và kết luận node nhẹ nếu `loops=100000`.

**Chú ý I/O:** `shared read` cho biết PostgreSQL đọc block vào shared buffer cache; số block này có thể đến từ OS page cache, **không tự chứng minh từng block là một lần đọc vật lý từ đĩa**. `shared hit` là hit trong PostgreSQL shared buffers, không phải chỉ số tương đương cache ứng dụng Java.

### Sai lệch ước lượng là tín hiệu quan trọng

Một ví dụ:

```text
Nested Loop (cost=... rows=10 ...)
            (actual time=... rows=500000 loops=1)
```

Khi planner ước lượng 10 hàng nhưng thực tế 500.000 hàng, việc lựa chọn `Nested Loop` thay vì hash/merge join có thể trở nên đắt. Nguyên nhân có thể là:

- Thống kê số lượng/phân bố giá trị không còn phù hợp.
- Các cột có tương quan mà thống kê đơn cột không thể mô tả đủ.
- Dữ liệu lệch mạnh giữa các tenant hoặc các giá trị.
- Predicate khó ước lượng, biểu thức hoặc hàm che mất tính chọn lọc.
- Parameter plan khác nhau giữa những lần thực thi.

Cần kiểm chứng nguyên nhân trước khi can thiệp. Trong PostgreSQL, thống kê mở rộng (`CREATE STATISTICS`) có thể hữu ích ở một số tình huống tương quan cột, nhưng phải đo tác động thật; không tự tạo thống kê mới cho mọi query.

## 6. Thứ tự cột của index ghép cần bám theo truy vấn

Index:

```sql
CREATE INDEX idx_sales_orders_tenant_created_id
ON sales_orders (tenant_id, created_at DESC, id DESC);
```

phù hợp với pattern `tenant_id = ?` + khoảng `created_at` + `ORDER BY created_at DESC, id DESC` trong nhiều trường hợp PostgreSQL B-tree. Tuy nhiên, index này không phải lúc nào cũng tối ưu cho truy vấn chỉ lọc theo `created_at` mà không có điều kiện `tenant_id`.

### 6.1. Điều kiện bằng trước, khoảng sau

Một heuristic hữu ích cho nhiều hệ quản trị dùng B-tree:

- Các cột có điều kiện **bằng** thường là ứng viên ở phần đầu index.
- Cột dùng **range** (`>=`, `<`, `BETWEEN`) thường tiếp theo.
- Cân nhắc cột của `ORDER BY` và chiều sắp xếp để giảm sort.
- Cột chỉ cần hiển thị có thể cân nhắc `INCLUDE` nếu DBMS hỗ trợ, sau khi đánh giá dung lượng và tần suất cập nhật.

Đây là heuristic, **không phải công thức bất biến**: optimizer có thể dùng skip scan, bitmap, index intersection hoặc các khả năng riêng; thứ tự cột tối ưu còn phụ thuộc số lượng giá trị phân biệt, join, limit và dữ liệu.

### 6.2. Ví dụ: index một cột so với index ghép

Với truy vấn:

```sql
SELECT id, total_amount
FROM sales_orders
WHERE tenant_id = 7
  AND created_at >= TIMESTAMPTZ '2026-11-01T00:00:00Z'
  AND created_at <  TIMESTAMPTZ '2026-12-01T00:00:00Z'
ORDER BY created_at DESC, id DESC
LIMIT 20;
```

Index chỉ có `tenant_id` có thể giúp tìm mọi đơn của tenant 7, nhưng vẫn phải xét khoảng ngày và sắp xếp. Index ghép có khả năng giúp giảm công việc này.

Dù vậy, nếu tenant 7 chỉ có vài hàng hoặc khoảng thời gian rất rộng, planner có thể chọn kế hoạch khác. Cần lấy plan với **các tenant có nhiều/ít đơn** và nhiều độ rộng khoảng thời gian thay vì chỉ dùng một bộ tham số đẹp.

### 6.3. Index có đánh đổi

Mỗi index mới có chi phí:

- Tăng không gian lưu trữ.
- Tăng công việc khi `INSERT`, `DELETE` và những `UPDATE` tác động cột được index.
- Tăng chi phí vacuum/maintenance, backup hoặc replication tùy kiến trúc.
- Có thể làm thay đổi kế hoạch của nhiều query khác.
- Có thể cạnh tranh tài nguyên cache với dữ liệu bảng.

Vì vậy, một index phục vụ một SELECT ít được gọi chưa chắc đáng tạo nếu làm chậm một bảng ghi hàng chục nghìn dòng mỗi giây. Cần đánh giá cả **read workload** và **write workload**.

## 7. Query viết không phù hợp cũng có thể ngăn index phát huy tác dụng

Một index tốt không thể tự sửa mọi cách viết predicate.

### 7.1. Áp hàm lên cột thời gian

Ví dụ kém linh hoạt:

```sql
-- Dễ làm mất lợi thế tìm range trực tiếp trên created_at:
SELECT id
FROM sales_orders
WHERE DATE(created_at) = DATE '2026-11-01';
```

Việc áp hàm vào cột có thể khiến DBMS khó dùng index thường trên `created_at` cho điều kiện tìm kiếm. Có thể dùng expression index trong PostgreSQL với biểu thức phù hợp, nhưng ở đây cách viết range thường rõ ràng hơn:

```sql
SELECT id
FROM sales_orders
WHERE created_at >= TIMESTAMPTZ '2026-11-01T00:00:00Z'
  AND created_at <  TIMESTAMPTZ '2026-11-02T00:00:00Z';
```

Đây là **khoảng ngày theo UTC**. Nếu nghiệp vụ dùng ngày theo múi giờ `Asia/Ho_Chi_Minh` hoặc vùng có DST, phải chuyển ranh giới **đầu ngày địa phương** và **đầu ngày kế tiếp** thành các instant tương ứng, thay vì luôn cộng 24 giờ theo cảm tính.

### 7.2. So sánh khác kiểu và implicit cast

Truyền `String` khi cột là số/ngày có thể khiến DBMS phải chuyển kiểu hoặc tối ưu kém, tùy driver và câu SQL. Nên bind đúng kiểu:

```java
ps.setLong(1, tenantId);
ps.setObject(2,
        java.time.OffsetDateTime.ofInstant(
                fromInstant, java.time.ZoneOffset.UTC));
ps.setObject(3,
        java.time.OffsetDateTime.ofInstant(
                toInstant, java.time.ZoneOffset.UTC));
```

`OffsetDateTime` với JDBC 4.2 và PostgreSQL `TIMESTAMPTZ` là ví dụ nhất quán về ngữ nghĩa instant; phải kiểm tra driver thực tế. Nếu cột kiểu khác, chọn kiểu Java/SQL tương ứng.

### 7.3. Wildcard tiền tố và wildcard đầu chuỗi

Một số index B-tree có thể hỗ trợ truy vấn prefix như `LIKE 'ABC%'` theo collation/operator class phù hợp, trong khi `LIKE '%ABC'` có wildcard đầu chuỗi thường không tận dụng B-tree thông thường cho phép tìm prefix. Ở PostgreSQL, `pg_trgm` hoặc loại index thích hợp có thể phục vụ các pattern tìm chuỗi khác, nhưng cần đánh giá cấu hình extension và workload.

Không suy rằng mọi `LIKE` đều sử dụng index hoặc mọi `ILIKE` đều không thể được tối ưu; hãy xem plan thật cùng collation và loại index đã tạo.

### 7.4. `SELECT *` khiến đọc thêm dữ liệu

Nếu ứng dụng chỉ cần `id` và `status`, `SELECT *` buộc DB/driver chuyển nhiều cột hơn. Nó cũng có thể khiến truy vấn không còn được index cover, tăng heap reads và byte qua mạng.

Nên chọn đúng cột cần dùng:

```sql
SELECT id, status
FROM sales_orders
WHERE tenant_id = ?
ORDER BY created_at DESC, id DESC
LIMIT ?;
```

Dù `SELECT` ít cột hơn không nhất thiết đổi kế hoạch, nó vẫn có thể giảm chi phí đọc/ghi buffer và truyền dữ liệu; cần đo cả latency lẫn số byte/hàng trả về.

## 8. Giữ query và tham số JDBC đúng với workload khi chạy `EXPLAIN`

Một lỗi phổ biến là thấy query production chậm với `tenant_id=9000` nhưng chỉ chạy:

```sql
EXPLAIN SELECT ... WHERE tenant_id = 1;
```

Nếu tenant 1 chỉ có 10 hàng còn tenant 9000 có 10 triệu hàng, so sánh đó không đại diện.

Để đánh giá đúng:

1. Lấy **câu SQL thực sự** do tầng DAO/repository dùng, không đoán qua mô tả nghiệp vụ.
2. Ghi lại **kiểu dữ liệu của bind parameter** và một bộ tham số được phép sử dụng trong môi trường test.
3. Chọn nhiều trường hợp: tenant nhỏ/lớn, ngày gần/xa, dữ liệu có/không có kết quả.
4. Dùng connection cùng DB/driver/config hoặc môi trường tương đương, tránh trộn các cấu hình khác biệt.
5. Đo plan **ước lượng và thực tế** trong phạm vi kiểm soát.
6. So sánh elapsed JDBC đầy đủ, vì dữ liệu trả về/mạng/fetch cũng ảnh hưởng.
7. Ghi lại version DBMS, thời điểm ANALYZE, số hàng và index hiện hành.

### 8.1. Prepared statements và generic/custom plan

PostgreSQL có thể chọn **custom plan** dựa trên giá trị tham số hoặc **generic plan** dùng chung cho nhiều lần thực thi prepared statement, tùy cơ chế và chính sách kế hoạch. Driver JDBC còn có hành vi chuẩn bị statement phía client/server và các ngưỡng riêng.

Vì vậy, kế hoạch từ SQL literal như `WHERE tenant_id=7` **không nhất thiết** giống kế hoạch khi ứng dụng thực thi query bằng `PreparedStatement` qua nhiều lần với các giá trị khác nhau.

Nếu nghi ngờ *parameter-sensitive plan*, cần tái hiện **đúng đường thực thi JDBC, phiên bản driver, giá trị bind và số lần chạy**. Có thể dùng các công cụ DBA của PostgreSQL để kiểm tra generic/custom plans trong lab; không đưa các tham số ép plan vào production khi chưa phân tích toàn bộ workload.

## 9. Ví dụ Java: xem kế hoạch từ chính `PreparedStatement`

Khi tối ưu JDBC, có thể tạo **một câu EXPLAIN có cùng cấu trúc SELECT và cùng kiểu bind** để xem plan. Ví dụ sau dùng PostgreSQL; nó chạy `EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT)` nên **thực thi SELECT**. Chỉ dùng trong môi trường đo có kiểm soát, không tạo endpoint cho người dùng tùy ý truyền SQL.

```java
import javax.sql.DataSource;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.time.Instant;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.util.ArrayList;
import java.util.List;

public final class OrderPlanInspector {
    private OrderPlanInspector() {
    }

    public static List<String> explainOrders(
            DataSource source,
            long tenantId,
            Instant fromInclusive,
            Instant toExclusive,
            int maxRows) throws SQLException {

        if (source == null || fromInclusive == null
                || toExclusive == null
                || !fromInclusive.isBefore(toExclusive)
                || maxRows <= 0 || maxRows > 1000) {
            throw new IllegalArgumentException("Tham số EXPLAIN không hợp lệ");
        }

        String sql =
                "EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT) " +
                "SELECT id, customer_id, total_amount, created_at " +
                "FROM sales_orders " +
                "WHERE tenant_id = ? " +
                "  AND created_at >= ? " +
                "  AND created_at < ? " +
                "ORDER BY created_at DESC, id DESC " +
                "LIMIT ?";

        List<String> plan = new ArrayList<>();

        try (Connection connection = source.getConnection();
             PreparedStatement ps = connection.prepareStatement(sql)) {

            ps.setLong(1, tenantId);
            ps.setObject(2, OffsetDateTime.ofInstant(
                    fromInclusive, ZoneOffset.UTC));
            ps.setObject(3, OffsetDateTime.ofInstant(
                    toExclusive, ZoneOffset.UTC));
            ps.setInt(4, maxRows);

            // Đây là giới hạn JDBC theo giây, không phải hard deadline
            // cho mọi driver, mạng hay câu SQL.
            ps.setQueryTimeout(10);

            try (ResultSet rs = ps.executeQuery()) {
                while (rs.next()) {
                    plan.add(rs.getString(1));
                }
            }
        }

        return plan;
    }
}
```

Gọi trong một phép thử với `DataSource` của PostgreSQL:

```java
List<String> lines = OrderPlanInspector.explainOrders(
        dataSource,
        7L,
        Instant.parse("2026-11-01T00:00:00Z"),
        Instant.parse("2026-12-01T00:00:00Z"),
        20);

lines.forEach(System.out::println);
```

Các điểm cần kiểm soát:

- `PreparedStatement` vẫn bind tham số, không nối `tenantId` hay ngày vào chuỗi SQL.
- `ResultSet` của `EXPLAIN ... FORMAT TEXT` chứa **các dòng text của kế hoạch**, không phải bản ghi `sales_orders`.
- Khi `ANALYZE` có mặt, DBMS thực thi SELECT để thu số liệu, nên kết quả chịu ảnh hưởng load và cache thực tế.
- Không tự động chạy mã đo trên mọi request production; query nặng hoặc sai tham số có thể tăng tải đáng kể.
- Nếu cần kết quả có cấu trúc để phân tích bằng công cụ, PostgreSQL hỗ trợ `FORMAT JSON`; cần parser JSON phù hợp và kiểm soát phiên bản schema output.

**Cảnh báo với DML:** Đừng biến helper này thành hàm `explain(String sql)` nhận SQL bất kỳ từ người dùng. `EXPLAIN ANALYZE UPDATE/DELETE/INSERT` có thể ghi dữ liệu và kích hoạt trigger; rollback sau đó cũng không hứa hoàn tác mọi side effect ngoài DB.

### 9.1. Đọc plan dạng JSON khi tự động hóa

PostgreSQL hỗ trợ:

```sql
EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)
SELECT id
FROM sales_orders
WHERE tenant_id = 7
LIMIT 10;
```

`FORMAT JSON` thuận tiện để lưu cây kế hoạch vào công cụ kiểm thử/hồ sơ performance. Tuy nhiên, bản plan có thể thay đổi về tên trường/toán tử theo phiên bản PostgreSQL, và chính việc bật `ANALYZE` vẫn thực thi câu SQL. Không nên viết assertion cố định “plan bắt buộc có Index Scan” cho mọi lượng dữ liệu; test nên ưu tiên metric và điều kiện hiệu năng thực tế.

## 10. Đo latency JDBC đầu cuối, không chỉ thời gian DB

`EXPLAIN ANALYZE` đo thời gian thực thi phía PostgreSQL theo cơ chế instrument của nó, nhưng request người dùng còn chi phí:

```text
HTTP request
  -> chờ connection từ pool
  -> prepare / bind / gửi SQL
  -> DB lập kế hoạch và thực thi
  -> driver fetch dữ liệu / mạng
  -> Java duyệt ResultSet và ánh xạ object
  -> serialize dữ liệu / trả HTTP response
```

Nếu `Execution Time` của DB chỉ 2 ms mà endpoint mất 500 ms, có thể vấn đề ở pool wait, N+1 queries, mạng, xử lý Java, serialization hoặc downstream service. Cần đo **từng giai đoạn** thay vì cố bổ sung index.

Ví dụ đo từ lúc lấy connection tới khi đọc hết rows:

```java
import javax.sql.DataSource;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.time.Instant;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.util.concurrent.TimeUnit;

public final class JdbcLatencyProbe {
    private JdbcLatencyProbe() {
    }

    public static long countFetched(
            DataSource source,
            long tenantId,
            Instant from,
            Instant to) throws SQLException {

        String sql =
                "SELECT id, customer_id, total_amount, created_at " +
                "FROM sales_orders " +
                "WHERE tenant_id = ? " +
                "  AND created_at >= ? AND created_at < ? " +
                "ORDER BY created_at DESC, id DESC";

        long beforeBorrow = System.nanoTime();

        try (Connection connection = source.getConnection()) {
            long afterBorrow = System.nanoTime();

            long count = 0L;
            try (PreparedStatement ps = connection.prepareStatement(sql)) {
                ps.setLong(1, tenantId);
                ps.setObject(2, OffsetDateTime.ofInstant(from, ZoneOffset.UTC));
                ps.setObject(3, OffsetDateTime.ofInstant(to, ZoneOffset.UTC));

                try (ResultSet rs = ps.executeQuery()) {
                    while (rs.next()) {
                        // Đọc dữ liệu để phép đo bao gồm fetch qua JDBC.
                        rs.getLong("id");
                        rs.getLong("customer_id");
                        rs.getBigDecimal("total_amount");
                        rs.getObject("created_at", OffsetDateTime.class);
                        count++;
                    }
                }
            }

            long afterFetch = System.nanoTime();
            System.out.println("Pool borrow (ms): " +
                    TimeUnit.NANOSECONDS.toMillis(
                            afterBorrow - beforeBorrow));
            System.out.println("SQL + fetch + mapping (ms): " +
                    TimeUnit.NANOSECONDS.toMillis(
                            afterFetch - afterBorrow));
            System.out.println("Rows fetched: " + count);
            return count;
        }
    }
}
```

Đây là **probe học tập**, không phải microbenchmark chính xác cho sản xuất. Việc in ra stdout, GC, JIT, cached plan, network và nhiệt độ cache DB có thể tác động lớn lên một lần đo. Trong production nên dùng metrics/tracing, log query chậm và tổng hợp phân vị `p50/p95/p99` trên nhiều request.

Khi so sánh trước/sau index, hãy dùng cùng lượng dữ liệu, cùng phạm vi ngày, cùng độ lớn kết quả và phương pháp đo. Chỉ đo `executeQuery()` mà không gọi `rs.next()` có thể bỏ sót phần lớn thời gian **fetch**, tùy driver.

## 11. Vì sao optimizer không dùng index vừa tạo?

Không nên phản xạ “ép dùng index” ngay khi `EXPLAIN` không cho ra `Index Scan`. Hãy phân tích theo thứ tự:

1. **Bảng nhỏ hoặc query trả quá nhiều hàng:** `Seq Scan` có thể đúng.
2. **Thống kê cũ:** tải dữ liệu lớn chưa `ANALYZE` hoặc phân bố mới khác hẳn.
3. **Điều kiện không chọn lọc:** `status='NEW'` có thể khớp 80% bảng.
4. **Thứ tự cột index không phù hợp:** chỉ lọc cột thứ hai mà bỏ cột dẫn đầu.
5. **Biểu thức trên cột:** `LOWER(email)`, `DATE(created_at)`, cast hoặc function có thể cần index biểu thức hay rewrite.
6. **Kiểu bind/implicit conversion:** SQL và Java đang so sánh kiểu không phù hợp.
7. **ORDER BY/JOIN/aggregation:** index có thể giúp phần lọc nhưng làm kế hoạch tổng thể tốn hơn.
8. **Parameter-sensitive plans:** truy vấn bind có thể dùng generic plan khác với thử nghiệm literal.
9. **Table/index bloat, cache và cấu hình I/O cost:** planner có mô hình chi phí và dữ liệu thực không trùng.
10. **Index thiếu khả năng áp dụng:** partial index, operator class, collation hoặc loại index không khớp điều kiện SQL.

### 11.1. Partial index phải phù hợp điều kiện truy vấn

Trên PostgreSQL, có thể tạo partial index cho dữ liệu thường được lọc theo một trạng thái:

```sql
CREATE INDEX idx_sales_orders_paid_recent
ON sales_orders (tenant_id, created_at DESC)
WHERE status = 'PAID';
```

Index này có thể hữu ích nếu truy vấn **chỉ cần đơn PAID** và planner chứng minh predicate phù hợp. Nhưng:

- Nó **không phục vụ chung** mọi giá trị `status`.
- Với prepared statement `WHERE status = ?` và generic plan không biết giá trị cụ thể, planner có thể không kết luận điều kiện luôn thỏa predicate `status='PAID'`.
- Thay đổi SQL để hard-code giá trị chỉ nhằm ép index là quyết định kiến trúc và cần bảo đảm nghiệp vụ thực sự chỉ dùng trạng thái đó.
- Partial index vẫn tăng chi phí bảo trì đối với dữ liệu nằm trong tập được index.

Phải kiểm chứng plan trong **đường truy vấn thật**, không chỉ xem index tồn tại ở `pg_indexes`.

### 11.2. Chỉ mục bao phủ (`INCLUDE`)

PostgreSQL có thể tạo:

```sql
CREATE INDEX idx_sales_orders_tenant_recent_cover
ON sales_orders (tenant_id, created_at DESC, id DESC)
INCLUDE (customer_id, total_amount);
```

Khi các cột SELECT đều có trong index, planner có thể cân nhắc `Index Only Scan`. Nhưng `INCLUDE` làm index lớn hơn và có thể giảm hiệu năng ghi, cache hit. Một truy vấn trả hàng triệu dòng chưa chắc được lợi. Hơn nữa, `Index Only Scan` vẫn có thể cần `Heap Fetches` để kiểm tra tính hiển thị.

Không tạo cả index ghép thường và index covering tương tự một cách máy móc: chúng có thể trùng lặp đáng kể và tăng gánh nặng duy trì.

## 12. Cách quan sát index đang tồn tại và được sử dụng

### 12.1. Metadata JDBC cho biết chỉ mục có gì

`DatabaseMetaData.getIndexInfo(...)` giúp lấy thông tin index của một bảng, phục vụ bước khám phá schema:

```java
import java.sql.Connection;
import java.sql.DatabaseMetaData;
import java.sql.ResultSet;
import java.sql.SQLException;

public static void showIndexes(Connection connection)
        throws SQLException {

    DatabaseMetaData meta = connection.getMetaData();

    // catalog, schema, table ở đây là tên chính xác,
    // không phải các pattern có ký tự % hoặc _.
    try (ResultSet rs = meta.getIndexInfo(
            null, "public", "sales_orders", false, false)) {

        while (rs.next()) {
            short type = rs.getShort("TYPE");
            if (type == DatabaseMetaData.tableIndexStatistic) {
                continue;
            }

            String index = rs.getString("INDEX_NAME");
            String column = rs.getString("COLUMN_NAME");
            short ordinal = rs.getShort("ORDINAL_POSITION");

            System.out.println(index + " position " +
                    ordinal + " -> " + column);
        }
    }
}
```

Đoạn là một phương thức Java có thể đặt trong lớp tiện ích; caller sở hữu và đóng `Connection`. Giá trị `approximate=false` yêu cầu metadata chính xác theo khả năng driver, nhưng không buộc DBMS thực thi mọi phép đo tốn kém ngoài hợp đồng của nó.

`getIndexInfo(...)` cho biết **các index được khai báo**, không cho biết planner **đã chọn index đó trong query đang chậm**. Phải xem `EXPLAIN` để biết plan.

### 12.2. PostgreSQL có thống kê sử dụng index

Trong môi trường có quyền phù hợp, có thể xem:

```sql
SELECT schemaname,
       relname,
       indexrelname,
       idx_scan,
       idx_tup_read,
       idx_tup_fetch
FROM pg_stat_user_indexes
WHERE relname = 'sales_orders'
ORDER BY idx_scan DESC;
```

Đây là thống kê tích lũy theo cơ chế PostgreSQL, không phải dấu vết một query cụ thể. Các chỉ số có thể bị reset, chịu ảnh hưởng nhiều workload và khoảng thời gian quan sát. `idx_scan=0` trong một thời điểm chưa đủ để quyết định xóa index: nó có thể dùng cho truy vấn theo mùa, khóa/constraint hoặc công việc định kỳ.

Nếu có extension `pg_stat_statements` đã được DBA cấu hình, nó có thể hỗ trợ xếp hạng các query theo tổng thời gian, số lần gọi và số hàng trả về. Không giả định extension có sẵn hoặc mọi ứng dụng đều có quyền cài đặt.

## 13. Đánh giá bằng workload đại diện, không chỉ một query

Một index có thể cải thiện truy vấn A nhưng làm giảm throughput ghi hoặc khiến truy vấn B bị đổi kế hoạch. Nên có một **bộ workload** trước khi kết luận:

| Kịch bản | Dữ liệu/điều kiện | Chỉ số quan trọng |
|---|---|---|
| Tenant nhỏ, lấy 20 đơn gần nhất | Vài chục hàng/tenant | Latency, plan, overhead lập kế hoạch |
| Tenant lớn, lấy 20 đơn gần nhất | Hàng triệu đơn/tenant | Buffer và số hàng bị đọc để trả 20 hàng |
| Khoảng thời gian rất rộng | Trả nhiều hàng | Seq Scan vs Index Scan, fetch, byte qua mạng |
| Khoảng hẹp không có kết quả | Hầu như không trả hàng | Index seek, planning overhead |
| Báo cáo theo trạng thái | `GROUP BY status` | Aggregate, sort/hash, số hàng đầu vào |
| Ghi đơn hàng liên tục | Nhiều `INSERT`/`UPDATE` | Throughput, WAL, lock, CPU, index maintenance |
| Hai truy vấn cạnh tranh | Đọc và ghi cùng bảng | p95/p99, lock wait, transaction contention |

Với mỗi kịch bản, ghi **trước/sau thay đổi**:

- Median và p95/p99 latency ở Java.
- `Planning Time`, `Execution Time` và số hàng thực tế từ `EXPLAIN ANALYZE` trong lab.
- `shared hit/read`, temp I/O và số rows removed.
- Số rows trả về, độ rộng kết quả, khối lượng dữ liệu qua mạng.
- CPU/IO của DB, connection pool wait, concurrent load, deadlock/timeout.
- Throughput và thời gian commit của thao tác ghi.

Cần so sánh ở **cùng điều kiện đại diện**. Benchmark một lần với cache lạnh rồi đo lại khi cache ấm có thể tạo ra “cải thiện” không liên quan đến index. Nên lặp nhiều lần, đảo thứ tự thử nghiệm hợp lý và ghi điều kiện cache/instance để giảm sai lệch.

### 13.1. Khi nào cần xem xét keyset pagination?

Với truy vấn `ORDER BY created_at DESC, id DESC`, phân trang `OFFSET 100000 LIMIT 20` có thể buộc DB xử lý/bỏ qua rất nhiều hàng, dù có index tốt.

Nếu UI cần chuyển tiếp theo mốc (không cần nhảy tùy ý trang 5000), có thể dùng **keyset pagination**:

```sql
SELECT id, created_at, total_amount
FROM sales_orders
WHERE tenant_id = ?
  AND (created_at, id) < (?, ?)
ORDER BY created_at DESC, id DESC
LIMIT 20;
```

Với thứ tự giảm dần, tuple comparison trên các cột có thứ tự tương ứng có thể giúp truy vấn tiến tiếp từ khóa của trang trước. Cần có tie-breaker `id` để thứ tự ổn định, và phải xét boundary/NULL/type/collation phù hợp. Keyset không thay thế mọi dạng phân trang, nhưng là một kỹ thuật nên đánh giá khi offset lớn.

## 14. MySQL, Oracle và SQL Server: cùng ý tưởng, khác công cụ

Bài dùng PostgreSQL để minh họa, nhưng cách đặt câu hỏi “DB đã chọn kế hoạch nào?” là phổ quát. Lệnh và trường hiển thị không thể sao chép nguyên giữa các hệ quản trị:

| DBMS | Công cụ ví dụ | Điểm cần lưu ý |
|---|---|---|
| PostgreSQL | `EXPLAIN`, `EXPLAIN (ANALYZE, BUFFERS)`, `FORMAT JSON` | Phân biệt ước lượng và thực thi, đọc `loops`/buffers |
| MySQL | `EXPLAIN SELECT ...`, `EXPLAIN FORMAT=JSON ...`, `EXPLAIN ANALYZE` trên phiên bản hỗ trợ | Dùng thông tin `type`, `key`, `rows`, `Extra` hoặc cây thực thi phù hợp phiên bản |
| Oracle Database | `EXPLAIN PLAN`, `DBMS_XPLAN`, execution plans trong công cụ chẩn đoán | Cần phân biệt estimated plan và actual cursor plan theo phiên bản/quyền |
| SQL Server | Estimated/Actual Execution Plan qua công cụ quản trị, DMVs/Query Store | Xem scans/seeks, actual vs estimated rows, warnings, memory grants |

Không nên đồng nhất `cost` trên PostgreSQL với cost của Oracle hoặc SQL Server. Kể cả cùng một DBMS, các phiên bản optimizer có thể chọn plan khác nhau sau nâng cấp. Khi có performance regression, lưu **version, plan, SQL, schema/index/statistics và workload** để đối chiếu.

## 15. Những lỗi tối ưu hóa thường gặp

| Phản xạ sai | Hậu quả | Thay bằng |
|---|---|---|
| Thấy `Seq Scan` thì tạo index ngay | Tăng chi phí ghi, có thể không cải thiện đọc | Kiểm tra độ chọn lọc, kích thước bảng và plan thực tế |
| Thấy `Index Scan` rồi kết luận query đã tốt | Có thể còn nhiều heap reads, sort hoặc loops | Đọc actual rows, loops, filters, buffers và latency |
| So `cost` với số mili giây | Đánh giá sai ưu tiên tối ưu | Dùng cost để hiểu quyết định planner; đo thời gian thực |
| Dùng `EXPLAIN ANALYZE UPDATE` trên production | Có thể sửa dữ liệu, kích hoạt trigger | Đo trong môi trường thử nghiệm; dùng `EXPLAIN` khi chỉ cần dự kiến |
| Tạo index trên mọi cột trong WHERE | Index trùng lặp, chậm ghi và tăng disk | Thiết kế theo query pattern và workload |
| Chỉ dùng dữ liệu mẫu vài hàng | Planner chọn seq scan, kết luận lệch production | Seed dữ liệu đại diện, cập nhật statistics |
| Chỉ test `tenant_id=1` | Bỏ sót data skew và parameter-sensitive plans | Test nhiều giá trị tham số thực tế |
| Viết `DATE(created_at)` rồi than index không dùng | Có thể mất điều kiện range tận dụng index | Viết half-open range hoặc expression index phù hợp |
| Dùng `SELECT *` cho bảng rộng | Tăng byte truyền, heap reads và memory | Chỉ lấy cột cần thiết |
| Đo `executeQuery()` không fetch | Bỏ sót phần lớn chi phí chuyển dữ liệu | Đo tới khi đọc hết rows |
| Tập trung DB khi endpoint chậm do pool | Tạo index không giải quyết bottleneck | Phân tách pool wait, DB time, network, mapping |
| Cố định assert “phải là Index Scan” | Test flaky khi statistics/version thay đổi | Kiểm tra correctness, latency và plan như tín hiệu |
| So đo trước/sau khác điều kiện cache | Tưởng có cải thiện do index | Chuẩn hóa workload, chạy nhiều lần |
| Bỏ qua chi phí write workload | Đọc nhanh hơn nhưng ghi chậm nặng | Đo cả INSERT/UPDATE/DELETE và contention |

## 16. Bài thực hành tích hợp

Các bài dưới đây dùng PostgreSQL và `DataSource` đã cấu hình đúng. Không chạy stress test/`EXPLAIN ANALYZE` trên production nếu chưa kiểm soát tải và ảnh hưởng.

### Bài 1: So sánh có và không có index

Trong môi trường lab, tạo bảng dữ liệu đủ lớn, ghi plan/latency cho truy vấn `tenant_id` + `created_at` trước khi tạo index ghép. Tạo `idx_sales_orders_tenant_created_id`, chạy `ANALYZE`, đo lại cùng các bộ tham số. Không đánh giá chỉ dựa trên một lần chạy hoặc một plan.

### Bài 2: Khảo sát tên toán tử và số hàng

Dùng `EXPLAIN (ANALYZE, BUFFERS)` cho tenant ít đơn và tenant nhiều đơn. Ghi `Seq Scan`/`Index Scan`/`Bitmap Heap Scan`, số hàng ước lượng và thực tế, `loops`, `shared hit/read`. Nếu có sai lệch hàng lớn, thử cập nhật thống kê trong lab rồi đối chiếu.

### Bài 3: Kiểm tra sort và LIMIT

So sánh truy vấn có/không có `ORDER BY created_at DESC, id DESC`. Kiểm tra plan có `Sort` không và số hàng DB phải đọc để trả `LIMIT 20`. Thử với index một cột rồi index ghép, ghi chi phí maintenance.

### Bài 4: Sargability và khoảng thời gian

So sánh `DATE(created_at) = ...` với khoảng `created_at >= ... AND created_at < ...`. Dùng cùng mốc ngày theo UTC hoặc chuyển đúng đầu ngày theo múi giờ nghiệp vụ. Kiểm tra cả kết quả trả về, không chỉ tốc độ.

### Bài 5: Bind parameters và plan

Gọi `OrderPlanInspector.explainOrders(...)` với vài tenant và khoảng ngày khác nhau. Đối chiếu plan từ `PreparedStatement` với `EXPLAIN` trên SQL literal có cùng dữ liệu. Nếu khác, kiểm tra khả năng generic/custom plan, driver settings và transaction trước khi kết luận.

### Bài 6: Ảnh hưởng đến ghi

Nạp thêm hàng qua `PreparedStatement` batch có transaction, đo throughput và commit latency khi có/không có index phụ trong môi trường test. Kiểm tra xem lợi ích cho một SELECT có tương xứng với chi phí cho INSERT/UPDATE không.

### Bài 7: So sánh phía DB và JDBC

Dùng `JdbcLatencyProbe` để đo borrow, SQL + fetch và số hàng. So với `EXPLAIN ANALYZE` trong cùng điều kiện thử nghiệm, phân tích chênh lệch do pool, network, fetch và mapping Java.

### Bài 8: Tối ưu phân trang

Thử `OFFSET` lớn và keyset pagination trên index `(tenant_id, created_at DESC, id DESC)`. Xác minh thứ tự không trùng/bỏ sót trong một snapshot dữ liệu ổn định; đánh giá khi có dữ liệu mới được ghi đồng thời.

## 17. Checklist trước khi kết luận một index hữu ích

1. Đã lấy **SQL và tham số thực tế** từ đường gọi JDBC chưa?
2. Kết quả có đúng dữ liệu và thứ tự nghiệp vụ không?
3. Đã thu plan bằng `EXPLAIN` và số liệu thực bằng `EXPLAIN ANALYZE` trong môi trường phù hợp chưa?
4. Có hiểu `cost`, `estimated rows`, `actual rows`, `loops`, `Index Cond`, `Filter` và `Buffers` không?
5. Index có đúng thứ tự cột và phù hợp `WHERE`, `ORDER BY`, `JOIN`, `LIMIT` không?
6. Có xét dữ liệu lệch, kiểu tham số, generic/custom plan và độ mới của statistics không?
7. Đã đo **latency JDBC gồm fetch**, cùng pool wait, network, số row và memory chưa?
8. Đã so sánh workload đọc **và** ghi, không chỉ một câu SELECT chưa?
9. Đã chạy nhiều lần dưới điều kiện tương đương và ghi version DB/driver/index/statistics chưa?
10. Có phương án rollback thay đổi index/query nếu gây regression ở production không?

## Ghi nhớ

- **Index là một phương án truy cập dữ liệu**, không phải bảo đảm query nhanh.
- **`EXPLAIN` cho biết kế hoạch dự kiến; `EXPLAIN ANALYZE` thực sự chạy câu SQL** và phải dùng thận trọng.
- Đọc `estimated rows`, `actual rows × loops`, `Index Cond`, `Filter`, `Sort` và `Buffers` để tìm bước tốn công.
- Chỉ mục ghép cần bám **mẫu lọc, sắp xếp và độ phân bố dữ liệu**; mỗi index có chi phí lưu trữ và ghi.
- Kiểu tham số `PreparedStatement`, SQL thực tế, dữ liệu skew và **generic/custom plan** có thể đổi quyết định optimizer.
- **Đo cả phía DB và Java/JDBC**: thời gian mượn connection, thực thi SQL, fetch `ResultSet` và ánh xạ dữ liệu là những phần khác nhau.
- Chỉ tối ưu khi đã xác định bottleneck và kiểm chứng trên workload/DBMS/driver đại diện.

Một quy trình đánh giá có căn cứ sẽ giúp lập trình viên JDBC tránh “tối ưu theo cảm giác”: **quan sát plan → đọc dấu hiệu số hàng và I/O → lập giả thuyết → thử thay đổi nhỏ → đo lại kết quả nghiệp vụ lẫn latency**. Nhờ đó, các cải tiến chỉ mục và SQL vừa tăng hiệu năng truy vấn, vừa không vô tình làm giảm độ ổn định của hệ thống.
