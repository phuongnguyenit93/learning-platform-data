# CREATE INDEX, DROP INDEX và chỉ mục nhiều cột

Một truy vấn SQL đúng về mặt kết quả chưa chắc đã chạy nhanh. Ví dụ, để tìm ba đơn hàng đã thanh toán mới nhất của một khách thuê (*tenant*) trong bảng chứa hàng triệu đơn, hệ quản trị có thể phải đọc rất nhiều hàng, lọc, sắp xếp rồi mới trả ba dòng. Nếu bảng có **chỉ mục (*index*) phù hợp**, cơ sở dữ liệu có thêm một cấu trúc truy cập giúp tìm những hàng cần thiết theo khóa và thứ tự nhanh hơn trong nhiều trường hợp.

Hai lệnh DDL cơ bản để quản lý cấu trúc này là:

- **`CREATE INDEX`**: tạo chỉ mục trên một hoặc nhiều cột hoặc biểu thức của bảng.
- **`DROP INDEX`**: loại bỏ chỉ mục không còn cần thiết, không phải xóa dữ liệu của bảng.

Điểm quan trọng của bài không phải chỉ thuộc cú pháp, mà là hiểu **vì sao thứ tự các cột của chỉ mục ghép quyết định những truy vấn nào tận dụng được nó**. Chỉ mục `(tenant_id, status, ordered_at)` không có cùng tác dụng với `(ordered_at, status, tenant_id)`, dù chứa đúng ba cột giống nhau.

Bài học dùng **PostgreSQL và chỉ mục B-tree** làm ví dụ chính, liên hệ trực tiếp đến `WHERE`, `ORDER BY`, `LIMIT`, `JOIN` và `EXPLAIN`. Sau đó, ta mở rộng sang chỉ mục duy nhất, chỉ mục có điều kiện, chỉ mục biểu thức, chỉ mục bao phủ, chi phí duy trì, xóa và tạo chỉ mục an toàn, cùng sự khác biệt cú pháp trong MySQL, SQL Server, SQLite và Oracle.

> **Phạm vi thực hành:** Các lệnh `CREATE INDEX` và `DROP INDEX` làm thay đổi cấu trúc database, có thể sử dụng CPU, bộ nhớ, I/O và khóa. Chỉ chạy ví dụ trên database thực hành hoặc môi trường đã được cho phép. Trên hệ thống thật, cần xem xét tải ghi, thời điểm bảo trì, phương án khôi phục và kế hoạch thực thi trước khi thay đổi chỉ mục.

## 1. Chỉ mục là gì và tại sao có thể giúp truy vấn?

Hình dung một cuốn sách có hàng nghìn trang. Nếu muốn tìm khái niệm “transaction”, bạn có thể:

1. Đọc từng trang từ đầu đến cuối.
2. Tra mục lục theo vần chữ rồi tới các trang được chỉ ra.

Một chỉ mục trong cơ sở dữ liệu đóng vai trò gần với **cấu trúc tra cứu**: nó lưu những giá trị khóa theo một cách tổ chức phù hợp để hệ quản trị tìm hoặc duyệt hàng nhanh hơn. Nhưng chỉ mục không phải bản sao đầy đủ của bảng trong mọi trường hợp, và không phải mọi kiểu chỉ mục đều được lưu giống một mục lục sách.

### 1.1. Bảng và chỉ mục là hai cấu trúc khác nhau

Ví dụ bảng `sales_orders_idx` có các cột:

```text
order_id | tenant_id | customer_id | status | ordered_at | total_amount
```

Nếu tạo chỉ mục B-tree:

```sql
CREATE INDEX idx_orders_tenant_status_time
ON sales_orders_idx (tenant_id, status, ordered_at DESC);
```

PostgreSQL tạo một cấu trúc chỉ mục riêng dựa trên **khóa `(tenant_id, status, ordered_at)`**, cùng thông tin để định vị hàng bảng. Chỉ mục có thể giúp truy vấn tìm nhanh một khoảng khóa, nhưng truy vấn vẫn có thể cần đọc hàng trong bảng để lấy cột không nằm trong chỉ mục.

### 1.2. Chỉ mục B-tree và thứ tự khóa

B-tree thường hữu ích cho:

- So sánh bằng: `tenant_id = 10`.
- So sánh khoảng: `ordered_at >= ...` và `ordered_at < ...`.
- Điều kiện thứ tự: `ORDER BY ordered_at DESC` khi các khóa đi trước đã được ràng buộc phù hợp.
- Truy vấn có `LIMIT` muốn lấy một số ít hàng đầu theo thứ tự.
- Tra cứu khóa trong phép `JOIN`, nếu bộ tối ưu thấy có lợi.

Với khóa ghép:

```text
(tenant_id, status, ordered_at DESC)
```

thứ tự được tổ chức theo **tenant trước**, rồi **status trong mỗi tenant**, rồi **ordered_at trong mỗi nhóm tenant/status**.

```text
tenant = 1
    status = CANCELLED -> các thời điểm
    status = NEW       -> các thời điểm
    status = PAID      -> các thời điểm giảm dần
tenant = 2
    status = CANCELLED -> các thời điểm
    status = NEW       -> các thời điểm
    status = PAID      -> các thời điểm giảm dần
...
```

Sơ đồ chỉ diễn giải **thứ tự logic của khóa**, không mô phỏng chính xác số trang hay cấu trúc cây vật lý.

### 1.3. Chỉ mục không làm mọi truy vấn nhanh hơn

Lợi ích có thể nhỏ hoặc không có nếu:

- Bảng rất nhỏ, đọc toàn bảng rẻ hơn đi qua chỉ mục.
- Điều kiện khớp phần lớn số hàng, nên dùng chỉ mục rồi đọc lại bảng tốn hơn quét tuần tự.
- Truy vấn cần phần lớn các cột mà chỉ mục không bao phủ.
- Thứ tự cột của chỉ mục không hợp với điều kiện.
- Bộ tối ưu ước lượng thống kê và chọn kế hoạch khác.
- Truy vấn dùng phép biến đổi cột hoặc kiểu so sánh mà chỉ mục thông thường không hỗ trợ hiệu quả.

Chỉ mục còn làm tăng **dung lượng lưu trữ**, **chi phí INSERT/UPDATE/DELETE** và thời gian bảo trì. Vì thế, **không có quy tắc “càng nhiều chỉ mục càng tốt”**.

## 2. Chuẩn bị dữ liệu mẫu PostgreSQL

Các câu SQL thực hành trong phần chính hướng tới **PostgreSQL**. Để các ví dụ độc lập với hệ thống sẵn có, ta dùng bảng riêng `sales_orders_idx`.

### 2.1. Tạo bảng

```sql
CREATE TABLE sales_orders_idx (
    order_id BIGINT PRIMARY KEY,
    tenant_id INTEGER NOT NULL,
    customer_id INTEGER NOT NULL,
    external_ref TEXT NOT NULL,
    status TEXT NOT NULL
        CHECK (status IN ('NEW', 'PAID', 'CANCELLED')),
    ordered_at TIMESTAMPTZ NOT NULL,
    total_amount NUMERIC(12, 2) NOT NULL
        CHECK (total_amount >= 0)
);
```

Trong bảng này:

- `order_id` là **khóa kỹ thuật duy nhất toàn bảng**. Khóa chính đã có chỉ mục phục vụ ràng buộc; không cần tạo thêm một chỉ mục đơn trùng chức năng trên `order_id`.
- `tenant_id` phân biệt nhiều khách thuê dùng chung bảng.
- `customer_id` nhận diện khách hàng thuộc tenant.
- `external_ref` là mã đơn từ hệ thống nguồn; mã có thể trùng **giữa các tenant** nhưng theo quy tắc nghiệp vụ phải duy nhất **trong một tenant**.
- `status` chỉ có ba giá trị.
- `ordered_at` là thời điểm đặt đơn có múi giờ.
- `total_amount` là tổng tiền đơn.

### 2.2. Nạp 18 đơn hàng

```sql
INSERT INTO sales_orders_idx
    (order_id, tenant_id, customer_id, external_ref,
     status, ordered_at, total_amount)
VALUES
    (1001, 1, 11, 'SHARED-001', 'PAID',
     TIMESTAMPTZ '2025-09-01 08:00:00+00', 120.00),
    (1002, 1, 11, 'T1-002', 'NEW',
     TIMESTAMPTZ '2025-09-01 09:00:00+00', 80.00),
    (1003, 1, 12, 'T1-003', 'PAID',
     TIMESTAMPTZ '2025-09-02 10:00:00+00', 90.00),
    (1004, 1, 11, 'T1-004', 'PAID',
     TIMESTAMPTZ '2025-09-03 08:00:00+00', 200.00),
    (1005, 1, 13, 'T1-005', 'CANCELLED',
     TIMESTAMPTZ '2025-09-04 09:00:00+00', 60.00),
    (1006, 1, 12, 'T1-006', 'PAID',
     TIMESTAMPTZ '2025-09-04 11:00:00+00', 180.00),
    (1007, 1, 11, 'T1-007', 'PAID',
     TIMESTAMPTZ '2025-09-05 12:00:00+00', 110.00),
    (1008, 1, 13, 'T1-008', 'NEW',
     TIMESTAMPTZ '2025-09-05 14:00:00+00', 40.00),

    (2001, 2, 21, 'SHARED-001', 'PAID',
     TIMESTAMPTZ '2025-09-01 08:30:00+00', 100.00),
    (2002, 2, 22, 'T2-002', 'NEW',
     TIMESTAMPTZ '2025-09-01 10:00:00+00', 50.00),
    (2003, 2, 21, 'T2-003', 'PAID',
     TIMESTAMPTZ '2025-09-02 08:30:00+00', 150.00),
    (2004, 2, 23, 'T2-004', 'PAID',
     TIMESTAMPTZ '2025-09-03 13:00:00+00', 75.00),
    (2005, 2, 23, 'T2-005', 'CANCELLED',
     TIMESTAMPTZ '2025-09-04 15:00:00+00', 40.00),
    (2006, 2, 22, 'T2-006', 'PAID',
     TIMESTAMPTZ '2025-09-05 08:00:00+00', 190.00),

    (3001, 3, 31, 'T3-001', 'PAID',
     TIMESTAMPTZ '2025-09-01 08:00:00+00', 70.00),
    (3002, 3, 32, 'T3-002', 'PAID',
     TIMESTAMPTZ '2025-09-02 15:00:00+00', 210.00),
    (3003, 3, 32, 'T3-003', 'NEW',
     TIMESTAMPTZ '2025-09-03 15:00:00+00', 20.00),
    (3004, 3, 31, 'T3-004', 'PAID',
     TIMESTAMPTZ '2025-09-05 15:00:00+00', 140.00);
```

Tập dữ liệu cố định có:

| Tenant | Tổng đơn | PAID | NEW | CANCELLED |
|---:|---:|---:|---:|---:|
| 1 | 8 | 5 | 2 | 1 |
| 2 | 6 | 4 | 1 | 1 |
| 3 | 4 | 3 | 1 | 0 |
| **Tổng** | **18** | **12** | **4** | **2** |

Với tập chỉ **18 hàng**, PostgreSQL có thể chọn `Seq Scan` ngay cả khi chỉ mục đã tạo, vì đọc bảng nhỏ rất rẻ. Những ví dụ sau minh họa **cấu trúc chỉ mục có khả năng hỗ trợ một dạng truy vấn trên dữ liệu lớn**, **không cam kết** bộ tối ưu sẽ dùng chỉ mục trên bảng nhỏ này.

### 2.3. Truy vấn mục tiêu

Giả sử màn hình của tenant 1 muốn **ba đơn PAID mới nhất kể từ 03/09/2025**:

```sql
SELECT
    order_id,
    tenant_id,
    status,
    ordered_at,
    total_amount
FROM sales_orders_idx
WHERE tenant_id = 1
  AND status = 'PAID'
  AND ordered_at >= TIMESTAMPTZ '2025-09-03 00:00:00+00'
ORDER BY ordered_at DESC, order_id DESC
LIMIT 3;
```

Trên dữ liệu mẫu, kết quả:

| order_id | tenant_id | status | ordered_at (UTC) | total_amount |
|---:|---:|---|---|---:|
| 1007 | 1 | PAID | 2025-09-05 12:00 | 110.00 |
| 1006 | 1 | PAID | 2025-09-04 11:00 | 180.00 |
| 1004 | 1 | PAID | 2025-09-03 08:00 | 200.00 |

Đây là truy vấn xuyên suốt để giải thích thứ tự cột, phép lọc bằng, phạm vi thời gian, sắp xếp và giới hạn số hàng.

## 3. CREATE INDEX trên một cột

Cú pháp PostgreSQL cơ bản:

```sql
CREATE INDEX index_name
ON table_name (column_name);
```

Ví dụ chỉ mục cho tra cứu tenant:

```sql
CREATE INDEX idx_orders_tenant
ON sales_orders_idx (tenant_id);
```

Hoặc chỉ mục phục vụ lọc theo thời điểm:

```sql
CREATE INDEX idx_orders_ordered_at
ON sales_orders_idx (ordered_at);
```

Một chỉ mục B-tree trên `tenant_id` có thể hỗ trợ:

```sql
SELECT order_id, status
FROM sales_orders_idx
WHERE tenant_id = 2;
```

Nhưng nếu tenant 2 chiếm phần lớn bảng, việc đọc trực tiếp phần lớn dữ liệu có thể vẫn rẻ hơn sử dụng chỉ mục rồi truy cập bảng nhiều lần.

### 3.1. Tên chỉ mục nên nói rõ bảng và khóa

Một quy ước đơn giản:

```text
idx_<table>_<key1>_<key2>_...
```

Ví dụ:

- `idx_orders_tenant`: khóa `tenant_id`.
- `idx_orders_tenant_status_time`: khóa tenant, status, thời gian.
- `uq_orders_tenant_ref`: unique index cho tenant và mã nguồn.

Tên có ích cho bảo trì, nhưng **không ảnh hưởng trực tiếp đến logic lọc**. Đừng đặt tên ám chỉ duy nhất khi chỉ mục không khai báo `UNIQUE`.

### 3.2. USING btree

PostgreSQL mặc định tạo B-tree khi không ghi phương thức chỉ mục trong những cú pháp thông dụng:

```sql
CREATE INDEX idx_orders_status
ON sales_orders_idx USING btree (status);
```

B-tree không phải loại duy nhất. PostgreSQL còn có các access method như GIN, GiST, BRIN và hash cho những kiểu truy vấn phù hợp. Bài này tập trung vào **B-tree và chỉ mục ghép**, không giả định quy tắc sử dụng của B-tree áp dụng nguyên vẹn cho mọi cấu trúc chỉ mục khác.

### 3.3. IF NOT EXISTS

```sql
CREATE INDEX IF NOT EXISTS idx_orders_tenant
ON sales_orders_idx (tenant_id);
```

Nếu tên chỉ mục đã tồn tại, PostgreSQL có thể bỏ qua thao tác và đưa ra thông báo. **`IF NOT EXISTS` không xác nhận rằng chỉ mục hiện có có đúng định nghĩa mong muốn**. Một chỉ mục trùng tên nhưng khác thứ tự cột hoặc điều kiện vẫn là vấn đề triển khai; cần quản lý schema bằng migration và kiểm tra catalog khi phù hợp.

## 4. CREATE INDEX nhiều cột: chỉ mục ghép

Chỉ mục nhiều cột, còn gọi là **composite/multicolumn index**, lưu khóa từ nhiều cột theo **thứ tự được khai báo**.

```sql
CREATE INDEX idx_orders_tenant_status_time
ON sales_orders_idx (
    tenant_id,
    status,
    ordered_at DESC,
    order_id DESC
);
```

Chỉ mục này có bốn **key columns** theo thứ tự:

1. `tenant_id`.
2. `status`.
3. `ordered_at` giảm dần.
4. `order_id` giảm dần.

### 4.1. Vì sao thứ tự cột có ý nghĩa?

Trong B-tree, thứ tự khóa có thể hình dung như một danh bạ được sắp:

```text
(tenant_id, status, ordered_at DESC, order_id DESC)

(1, CANCELLED, ...)
(1, NEW,       ...)
(1, PAID,      2025-09-05 12:00, 1007)
(1, PAID,      2025-09-04 11:00, 1006)
(1, PAID,      2025-09-03 08:00, 1004)
(1, PAID,      2025-09-02 10:00, 1003)
(1, PAID,      2025-09-01 08:00, 1001)
(2, CANCELLED, ...)
(2, NEW,       ...)
(2, PAID,      ...)
...
```

Với `tenant_id = 1 AND status = 'PAID'`, các khóa tương ứng tạo một **phạm vi liên tiếp** trong chỉ mục. Bên trong phạm vi đó, `ordered_at DESC, order_id DESC` đã có thứ tự mong muốn.

Đó là lý do chỉ mục đặc biệt phù hợp cho truy vấn mục 2.3: hai cột đầu so bằng; thời gian tiếp theo dùng điều kiện khoảng và thứ tự; khóa cuối phân định các đơn có cùng thời điểm.

### 4.2. Thứ tự cột không giao hoán

So sánh:

```sql
-- Thiên về truy vấn biết tenant và status, cần thời gian mới nhất.
CREATE INDEX idx_orders_tenant_status_time
ON sales_orders_idx (tenant_id, status, ordered_at DESC, order_id DESC);

-- Cùng các cột nhưng khác thứ tự khóa.
CREATE INDEX idx_orders_time_tenant_status
ON sales_orders_idx (ordered_at DESC, tenant_id, status, order_id DESC);
```

Ở chỉ mục thứ hai, bảng được tổ chức theo **thời gian trước**, nên các đơn của tenant 1/status PAID có thể nằm rải rác trong nhiều vùng thời gian. Nó có thể hữu ích cho một truy vấn khác, ví dụ “mọi đơn mới nhất trên toàn hệ thống”, nhưng không có cùng khả năng khoanh vùng tenant/status.

**Chứa cùng tập cột không có nghĩa hai chỉ mục là tương đương.**

### 4.3. Chỉ mục ghép khác nhiều chỉ mục đơn

Các lệnh:

```sql
CREATE INDEX idx_orders_tenant ON sales_orders_idx (tenant_id);
CREATE INDEX idx_orders_status ON sales_orders_idx (status);
CREATE INDEX idx_orders_time ON sales_orders_idx (ordered_at);
```

không tạo ra cùng cấu trúc với:

```sql
CREATE INDEX idx_orders_tenant_status_time
ON sales_orders_idx (tenant_id, status, ordered_at DESC);
```

PostgreSQL có thể **kết hợp nhiều chỉ mục** bằng bitmap scan trong một số truy vấn, nhưng phép kết hợp này có chi phí riêng và không tự bảo toàn thứ tự ghép cần cho `ORDER BY ... LIMIT`. Một B-tree ghép phù hợp đôi khi hiệu quả hơn; đôi khi các chỉ mục đơn linh hoạt hơn cho nhiều truy vấn khác nhau.

Không có quy tắc buộc phải tạo cả hai nhóm chỉ mục. Quyết định dựa trên **workload** và kế hoạch thực thi đo được.

## 5. Nguyên tắc tiền tố trái (*leftmost prefix*)

Với chỉ mục B-tree nhiều cột:

```sql
(tenant_id, status, ordered_at DESC, order_id DESC)
```

những điều kiện ràng buộc **các cột khóa ở bên trái** thường giúp thu hẹp vùng chỉ mục hiệu quả nhất.

### 5.1. Các dạng điều kiện

| Điều kiện truy vấn | Mức độ phù hợp điển hình |
|---|---|
| `tenant_id = 1` | Dùng tiền tố đầu tiên |
| `tenant_id = 1 AND status = 'PAID'` | Dùng hai cột khóa đầu |
| `tenant_id = 1 AND status = 'PAID' AND ordered_at >= ...` | Dùng hai điều kiện bằng, rồi phạm vi thời gian |
| `tenant_id = 1 AND ordered_at >= ...` | Có tenant, nhưng bỏ trống `status` ở giữa; thời gian khó tạo một vùng liên tiếp duy nhất trong chỉ mục |
| `status = 'PAID'` | Không ràng buộc cột đầu; thường kém thuận lợi cho kiểu seek theo tiền tố |
| `ordered_at >= ...` | Bỏ trống hai cột đầu; chỉ mục này không phải lựa chọn tự nhiên cho toàn bộ mốc thời gian |

Nguyên tắc thực dụng:

> **Các cột bằng ở bên trái → cột khoảng hoặc cột sắp xếp tiếp theo → các cột phụ tùy truy vấn.**

Đây là **heuristic thiết kế**, không phải định luật máy tối ưu luôn tuân thủ. PostgreSQL và một số DBMS có thể cân nhắc kỹ thuật như **skip scan**, quét một phần/đọc toàn chỉ mục, bitmap index combination hoặc quét bảng, kể cả khi điều kiện không dùng cột đầu. Vì vậy nói “chỉ mục ghép *không bao giờ* được dùng nếu thiếu cột đầu” là quá tuyệt đối.

### 5.2. Hai điều kiện bằng rồi một điều kiện khoảng

Truy vấn:

```sql
SELECT order_id, ordered_at
FROM sales_orders_idx
WHERE tenant_id = 1
  AND status = 'PAID'
  AND ordered_at >= TIMESTAMPTZ '2025-09-03 00:00:00+00'
ORDER BY ordered_at DESC, order_id DESC
LIMIT 3;
```

với chỉ mục:

```sql
(tenant_id, status, ordered_at DESC, order_id DESC)
```

có thể giúp bộ tối ưu:

1. Tới vùng khóa có tenant 1.
2. Trong tenant 1, tới nhóm `PAID`.
3. Đi theo thứ tự thời gian giảm dần.
4. Chỉ xem các bản ghi đáp ứng mốc thời gian.
5. Dừng sớm sau đủ ba hàng nếu kế hoạch và điều kiện cho phép.

**Phạm vi thời gian không có nghĩa index chỉ xử lý mọi thứ bằng một phép seek duy nhất** trong mọi DBMS. Cách biểu diễn `Index Cond` và những khóa được dùng để khoanh vùng/phân loại còn phụ thuộc optimizer.

### 5.3. Sau cột phạm vi, các cột sau vẫn có thể hữu ích

Giả sử chỉ mục:

```sql
(tenant_id, ordered_at, status)
```

và truy vấn:

```sql
WHERE tenant_id = 1
  AND ordered_at >= TIMESTAMPTZ '2025-09-01 00:00:00+00'
  AND status = 'PAID'
```

Cột `status` đứng **sau một điều kiện khoảng** trên `ordered_at`. Trong B-tree, nó thường **không giúp giới hạn dải thời gian liên tiếp theo cách giống các cột bằng đứng trước**, nhưng vẫn có thể được kiểm tra từ dữ liệu chỉ mục hoặc góp phần giảm đọc bảng, tùy DBMS/plan.

Không nên diễn giải quy tắc “sau cột khoảng vô ích hoàn toàn”. Đúng hơn là: **hiệu quả thu hẹp vùng quét thường giảm khi gặp khóa phạm vi trước các khóa sau**.

### 5.4. Mô hình ưu tiên EQ – Range – Sort

Một cách khởi đầu khi thiết kế:

1. Xác định các điều kiện **bằng** xuất hiện thường xuyên.
2. Xác định điều kiện **khoảng** hoặc tập giá trị.
3. Xác định `ORDER BY` và `LIMIT`.
4. Xác định cột cần trả để cân nhắc độ bao phủ.
5. Đo bằng `EXPLAIN` với dữ liệu đại diện.

Với một workload nhiều loại truy vấn, thứ tự cột tối ưu có thể khác mẫu “equality trước range”. Ví dụ có thể ưu tiên một chỉ mục theo **thời gian** nếu dashboard chủ yếu lấy 20 đơn mới nhất toàn bảng, dù đôi khi có điều kiện tenant. Đừng tối ưu một câu duy nhất mà làm toàn bộ workload chậm hơn.

## 6. Chỉ mục ghép và ORDER BY

Chỉ mục B-tree được sắp theo khóa. Nếu thứ tự truy vấn tương thích với thứ tự chỉ mục **sau các điều kiện ràng buộc ở tiền tố**, cơ sở dữ liệu có thể tránh hoặc giảm việc `Sort` riêng.

### 6.1. Dùng cùng chỉ mục cho lọc và sắp xếp

```sql
CREATE INDEX idx_orders_tenant_status_time
ON sales_orders_idx (
    tenant_id,
    status,
    ordered_at DESC,
    order_id DESC
);
```

Với:

```sql
WHERE tenant_id = 1
  AND status = 'PAID'
ORDER BY ordered_at DESC, order_id DESC
LIMIT 3
```

hai cột đầu được cố định; các khóa còn lại đã theo thứ tự cần trả.

### 6.2. Bỏ một cột giữa có thể phá thứ tự toàn cục

Giả sử truy vấn:

```sql
SELECT order_id, status, ordered_at
FROM sales_orders_idx
WHERE tenant_id = 1
ORDER BY ordered_at DESC, order_id DESC
LIMIT 3;
```

Nếu chỉ có chỉ mục:

```sql
(tenant_id, status, ordered_at DESC, order_id DESC)
```

thì trong tenant 1 các hàng được gom theo **status trước**, rồi thời gian **trong mỗi status**. Truy vấn lại muốn **thời gian giảm dần trên mọi trạng thái**. Vì vậy chỉ mục không tự cung cấp thứ tự toàn cục yêu cầu.

Một chỉ mục khác phù hợp hơn:

```sql
CREATE INDEX idx_orders_tenant_time
ON sales_orders_idx (
    tenant_id,
    ordered_at DESC,
    order_id DESC
);
```

Chỉ mục này phục vụ “đơn mới nhất của một tenant **bất kể trạng thái**”.

**Đừng nhầm:** Cả hai chỉ mục đều có `tenant_id` và `ordered_at`, nhưng việc `status` đứng **giữa** ở chỉ mục đầu làm ngữ nghĩa thứ tự khác.

### 6.3. ASC, DESC và hướng quét chỉ mục

Ví dụ PostgreSQL:

```sql
CREATE INDEX idx_orders_tenant_time
ON sales_orders_idx (
    tenant_id ASC,
    ordered_at DESC,
    order_id DESC
);
```

B-tree có thể được quét tiến hoặc lùi, nên không phải lúc nào muốn `DESC` cũng cần tạo một chỉ mục riêng khác với `ASC`. Nhưng với **chỉ mục nhiều cột có hướng trộn**, các dạng:

```sql
ORDER BY a ASC, b DESC
```

và:

```sql
ORDER BY a ASC, b ASC
```

không phải lúc nào cũng được đáp ứng bởi cùng một chỉ mục khi chỉ dùng một hướng quét. Đặc biệt nếu cả `a` và `b` đều cần sắp xếp trong đầu ra, cần xem hướng khóa và kế hoạch thực thi.

### 6.4. NULLS FIRST/LAST và collation

Nếu cột sắp xếp cho phép `NULL`, thứ tự cũng phụ thuộc quy tắc:

```sql
ORDER BY ranked_at DESC NULLS LAST
```

Trong PostgreSQL, `DESC` mặc định thường đặt `NULL` trước, nên `NULLS LAST` có ý nghĩa rõ. Một chỉ mục có thể khai báo:

```sql
-- Minh họa trên một bảng khác có cột ranked_at nullable.
CREATE INDEX idx_example_ranked_at
ON example_table (ranked_at DESC NULLS LAST);
```

Đoạn này là **mẫu cú pháp**, không chạy với `sales_orders_idx` vì bảng đó không có `ranked_at`. Cách sắp chuỗi văn bản còn phụ thuộc collation. Khi chuyển DBMS hoặc đổi collation, so sánh và mức phù hợp của chỉ mục với `ORDER BY` có thể thay đổi.

### 6.5. Có chỉ mục không có nghĩa kết quả tự sắp xếp

Kể cả khi optimizer sử dụng chỉ mục đã sắp, câu:

```sql
SELECT * FROM sales_orders_idx WHERE tenant_id = 1;
```

**không bảo đảm thứ tự hiển thị** vì nó không có `ORDER BY` ở cấp kết quả. Bộ tối ưu có thể chọn quét bảng, bitmap heap scan, parallel scan hoặc kế hoạch khác. Muốn kết quả đúng thứ tự cần **viết `ORDER BY` tường minh**, không dựa vào trật tự lưu trữ hay thứ tự của chỉ mục.

## 7. Nhiều truy vấn, nhiều lựa chọn thứ tự cột

Xét bốn màn hình:

| Màn hình | SQL chính | Chỉ mục ứng viên |
|---|---|---|
| A. Đơn PAID mới nhất tenant | `tenant_id=? AND status='PAID' ORDER BY ordered_at DESC` | `(tenant_id,status,ordered_at DESC,order_id DESC)` |
| B. Đơn mới nhất tenant, mọi status | `tenant_id=? ORDER BY ordered_at DESC` | `(tenant_id,ordered_at DESC,order_id DESC)` |
| C. Đơn của một khách tenant | `tenant_id=? AND customer_id=? ORDER BY ordered_at DESC` | `(tenant_id,customer_id,ordered_at DESC,order_id DESC)` |
| D. Đơn mới nhất toàn hệ thống | `ORDER BY ordered_at DESC` | `(ordered_at DESC,order_id DESC)` |

Không có một chỉ mục ghép nào mặc nhiên tối ưu cả bốn. Trước khi tạo, cần quyết định:

- Màn hình nào chạy nhiều và chiếm nhiều thời gian nhất?
- Mức chọn lọc của tenant, status, customer?
- Truy vấn có cần trả nhiều cột không?
- Tần suất ghi là bao nhiêu?
- Có những chỉ mục đã tồn tại phục vụ một phần nhu cầu chưa?

### 7.1. Có nên đặt cột “chọn lọc cao nhất” đầu tiên?

Một lời khuyên thường nghe là đặt cột có **nhiều giá trị phân biệt nhất** lên đầu. Điều đó có thể hữu ích trong một số hoàn cảnh, nhưng không phải quy tắc đủ để thiết kế chỉ mục ghép.

Ví dụ:

```sql
WHERE tenant_id = 1
  AND status = 'PAID'
```

Nếu hai điều kiện đều là **bằng** và cả hai luôn xuất hiện cùng nhau, thứ tự `(tenant_id,status)` và `(status,tenant_id)` đều có thể khoanh vùng khóa tương ứng. Tuy nhiên:

- `(tenant_id,status)` còn hỗ trợ truy vấn **chỉ theo tenant** tốt hơn.
- `(status,tenant_id)` còn hỗ trợ truy vấn **chỉ theo status** tốt hơn.
- Phân bố dữ liệu, quyền truy cập theo tenant, truy vấn thực tế và yêu cầu `ORDER BY` quyết định hướng nào có ích hơn.

Do đó, hãy ưu tiên **mẫu truy vấn thực tế và khả năng dùng tiền tố**, không dùng một chỉ số cardinality duy nhất để quyết định mọi thiết kế.

### 7.2. Cột ít giá trị không tự nhiên vô ích

`status` chỉ có ba giá trị nên chỉ mục một cột `(status)` có thể không hữu ích nếu gần như mọi hàng là `PAID`. Nhưng trong chỉ mục ghép:

```sql
(tenant_id, status, ordered_at DESC)
```

`status` có thể rất hữu ích vì tạo vùng khóa riêng cho `PAID` trong **mỗi tenant** và giúp truy vấn mới nhất sau điều kiện bằng.

Nói “cột status ít phân biệt nên không bao giờ đưa vào index” là sai.

## 8. CREATE UNIQUE INDEX trên nhiều cột

Chỉ mục **`UNIQUE`** không chỉ là một gợi ý tối ưu: nó còn **thực thi quy tắc không trùng khóa** trên tập cột được khai báo, với chi tiết xử lý `NULL` phụ thuộc DBMS.

Trong dữ liệu mẫu, mã `external_ref` có thể giống nhau ở hai tenant:

```text
tenant 1, external_ref = SHARED-001 -> order 1001
tenant 2, external_ref = SHARED-001 -> order 2001
```

Vì vậy **không** nên:

```sql
-- Sai quy tắc nghiệp vụ vì cấm trùng external_ref giữa các tenant.
CREATE UNIQUE INDEX uq_orders_ref
ON sales_orders_idx (external_ref);
```

Nó sẽ bị xung đột dữ liệu mẫu và không phù hợp quy tắc đã nêu.

### 8.1. Chỉ mục duy nhất theo tenant và mã nguồn

```sql
CREATE UNIQUE INDEX uq_orders_tenant_ref
ON sales_orders_idx (tenant_id, external_ref);
```

Nó cho phép:

```text
(1, SHARED-001)
(2, SHARED-001)
```

nhưng cấm **hai hàng cùng cặp `(tenant_id, external_ref)`**, ví dụ hai đơn khác nhau đều mang `(1, T1-003)`.

### 8.2. UNIQUE nhiều cột không có nghĩa từng cột duy nhất

Với `UNIQUE(tenant_id, external_ref)`:

- Một `tenant_id` có thể xuất hiện ở hàng nghìn đơn.
- Một `external_ref` có thể xuất hiện ở nhiều tenant.
- **Cặp giá trị** mới phải duy nhất theo quy tắc.

Đây là mô hình rất phổ biến trong hệ thống multi-tenant: ràng buộc khóa nghiệp vụ trong phạm vi tổ chức/chi nhánh/kho, thay vì trên toàn database.

### 8.3. UNIQUE và NULL

Trong PostgreSQL thông thường, unique index mặc định coi các `NULL` là **khác nhau** để kiểm tra duy nhất, nên nhiều hàng có `NULL` trong cột khóa có thể vẫn được cho phép. PostgreSQL từ phiên bản 15 có tùy chọn `NULLS NOT DISTINCT` để điều chỉnh quy tắc này.

Bảng mẫu dùng `external_ref TEXT NOT NULL`, nên trường hợp `NULL` không xảy ra. Trên DBMS khác, quy tắc unique với `NULL` có thể khác. Không dựa vào một chuẩn đoán chung “unique index cấm mọi NULL trùng” khi thiết kế đa hệ quản trị.

### 8.4. Unique index và unique constraint

Trong PostgreSQL, có thể tạo ràng buộc bảng:

```sql
ALTER TABLE sales_orders_idx
ADD CONSTRAINT uq_orders_tenant_ref_constraint
UNIQUE (tenant_id, external_ref);
```

Lệnh trên thể hiện **quy tắc toàn vẹn ở mức schema** và PostgreSQL tạo cấu trúc chỉ mục hỗ trợ. Không nên tạo cả unique index và unique constraint giống hệt nhau một cách không chủ đích, vì có thể tạo chi phí thừa.

Nếu cần xóa một chỉ mục đang **phục vụ PRIMARY KEY hoặc UNIQUE constraint**, không thể coi nó như chỉ mục tối ưu phụ thông thường. `DROP INDEX` đơn giản có thể bị từ chối do phụ thuộc ràng buộc; muốn thay đổi constraint phải làm migration có kiểm soát, không gỡ ràng buộc để “tối ưu tốc độ” một cách tùy tiện.

## 9. Chỉ mục từng phần (*partial/filtered index*)

Nếu phần lớn truy vấn chỉ quan tâm đơn đã thanh toán, PostgreSQL có thể tạo chỉ mục **chỉ trên những hàng thỏa điều kiện**:

```sql
CREATE INDEX idx_orders_paid_tenant_time
ON sales_orders_idx (
    tenant_id,
    ordered_at DESC,
    order_id DESC
)
WHERE status = 'PAID';
```

Chỉ những hàng `status = 'PAID'` được đưa vào cấu trúc chỉ mục này. Nó có thể **nhỏ hơn** một chỉ mục bao trùm mọi trạng thái và hữu ích cho:

```sql
SELECT order_id, ordered_at
FROM sales_orders_idx
WHERE tenant_id = 1
  AND status = 'PAID'
ORDER BY ordered_at DESC, order_id DESC
LIMIT 3;
```

### 9.1. Cột status không nhất thiết phải nằm trong key

Ở chỉ mục trên:

```sql
ON (tenant_id, ordered_at DESC, order_id DESC)
WHERE status = 'PAID'
```

`status` không phải key column, nhưng **predicate của partial index** bảo đảm các hàng nằm trong chỉ mục đều là PAID. Vì thế trong một số truy vấn chỉ xét PAID, chỉ mục có thể vừa lọc theo nghiệp vụ vừa cung cấp thứ tự theo tenant/thời gian.

### 9.2. Query planner phải nhận ra điều kiện phù hợp

Để dùng partial index, bộ tối ưu phải có thể suy ra từ điều kiện truy vấn rằng các hàng cần tìm nằm trong **tập mà predicate của index bao phủ**.

Ví dụ `WHERE status = 'PAID'` khớp rõ ràng. Nhưng với một prepared statement:

```sql
WHERE status = $1
```

khi tạo **generic plan** và giá trị tham số chưa biết, bộ tối ưu không phải lúc nào cũng chứng minh được `$1` luôn là `PAID`. Khi ấy chỉ mục partial có thể không được chọn dù chương trình thường truyền `'PAID'`.

Không kết luận “chỉ mục bị hỏng” chỉ vì một prepared query không dùng nó. Cần quan sát kế hoạch thực tế và cách PostgreSQL lập kế hoạch cho tham số.

### 9.3. Partial index không phải lúc nào cũng tốt

Nếu một ứng dụng còn có nhiều truy vấn `NEW`, `CANCELLED` hoặc tất cả đơn, chỉ mục `WHERE status = 'PAID'` không phục vụ mọi màn hình. Có thể cần một index tổng quát khác hoặc chấp nhận đọc bảng cho các truy vấn ít dùng.

Với SQL Server, khái niệm gần tương đương là **filtered index**. MySQL không hỗ trợ trực tiếp cú pháp `CREATE INDEX ... WHERE predicate` giống PostgreSQL; SQLite có hỗ trợ partial index; Oracle có các kỹ thuật khác phụ thuộc phiên bản và thiết kế.

## 10. Chỉ mục biểu thức (*expression/function-based index*)

Truy vấn:

```sql
WHERE LOWER(email) = 'an@example.com'
```

không nhất thiết tận dụng hiệu quả một chỉ mục B-tree thông thường trên cột `email`, vì truy vấn đang lọc **giá trị sau khi gọi hàm `LOWER`**, không phải trực tiếp giá trị gốc.

### 10.1. Ví dụ PostgreSQL

Giả sử có bảng:

```sql
CREATE TABLE customer_email_idx (
    customer_id BIGINT PRIMARY KEY,
    email TEXT NOT NULL
);

INSERT INTO customer_email_idx (customer_id, email)
VALUES
    (1, 'An@Example.com'),
    (2, 'binh@example.com'),
    (3, 'chi@example.com');
```

Tạo chỉ mục trên biểu thức:

```sql
CREATE INDEX idx_customer_email_lower
ON customer_email_idx (LOWER(email));
```

Truy vấn:

```sql
SELECT customer_id, email
FROM customer_email_idx
WHERE LOWER(email) = 'an@example.com';
```

có thể tận dụng chỉ mục biểu thức phù hợp, nếu optimizer đánh giá có lợi.

### 10.2. Biểu thức phải khớp ý nghĩa truy vấn

Chỉ mục `LOWER(email)` không tự động có nghĩa mọi phép tìm kiếm chuỗi đều được tăng tốc:

- `email = 'An@Example.com'` là phép so khác.
- `LOWER(TRIM(email)) = ...` thêm xử lý khoảng trắng; có thể cần biểu thức index tương ứng.
- `LIKE '%example.com'` có dấu `%` ở đầu thường không tận dụng một B-tree thông thường theo cách tìm tiền tố.
- Ngữ nghĩa chữ hoa/thường và sắp chuỗi phụ thuộc collation.

Trong PostgreSQL, `LIKE 'abc%'` có thể cần điều kiện collation/operator class hoặc chỉ mục chuyên biệt để đạt hiệu quả mong đợi. Đừng cho rằng chỉ tạo `INDEX(email)` sẽ tăng tốc mọi dạng `LIKE` và regex.

### 10.3. Không lạm dụng chỉ mục biểu thức

Mỗi lần một hàng được chèn hoặc giá trị ảnh hưởng đến biểu thức thay đổi, database có thể phải tính và duy trì khóa chỉ mục. Chỉ nên dùng khi phép biến đổi được truy vấn thường xuyên và có ích đáng kể so với chi phí ghi/lưu trữ.

## 11. Chỉ mục bao phủ và INCLUDE

Một truy vấn cần tìm đúng hàng **và trả một số cột**. Nếu tất cả các cột cần thiết đều có trong chỉ mục, một số hệ quản trị có thể thực hiện **index-only scan/covering access** trong điều kiện thích hợp.

### 11.1. PostgreSQL INCLUDE

Giả sử query phổ biến:

```sql
SELECT order_id, ordered_at, total_amount
FROM sales_orders_idx
WHERE tenant_id = 1
  AND status = 'PAID'
ORDER BY ordered_at DESC, order_id DESC
LIMIT 3;
```

Một chỉ mục ứng viên:

```sql
CREATE INDEX idx_orders_tenant_status_time_inc
ON sales_orders_idx (
    tenant_id,
    status,
    ordered_at DESC,
    order_id DESC
)
INCLUDE (total_amount);
```

Sự khác nhau:

- `tenant_id, status, ordered_at, order_id` là **key columns**: tham gia thứ tự của B-tree và có thể hỗ trợ lọc/sắp.
- `total_amount` là **included column**: được lưu để phục vụ việc trả dữ liệu, **không tham gia thứ tự khóa** và không dùng như một cột key để tìm phạm vi theo giá trị.

Vì vậy, `INCLUDE(total_amount)` **không giống** đưa `total_amount` lên đầu hoặc cuối key list để thay đổi cách sắp xếp.

### 11.2. Index-only scan không được bảo đảm

PostgreSQL dùng MVCC. Để tránh đọc bảng khi thực hiện index-only scan, nó còn phải xác định khả năng nhìn thấy (*visibility*) của các hàng, thường dựa trên **visibility map**. Nếu các trang bảng chưa được đánh dấu phù hợp, PostgreSQL vẫn có thể phải truy cập heap để kiểm tra tính hiển thị.

Do đó:

> Có đủ cột trong index là **điều kiện hỗ trợ**, không phải cam kết truy vấn chắc chắn không đọc bảng.

Index-only scan cũng không nhất thiết rẻ nhất: included columns làm chỉ mục lớn hơn, tăng chi phí ghi, bộ nhớ cache và bảo trì. Trên bảng cập nhật liên tục, lợi ích có thể không như kỳ vọng.

### 11.3. INCLUDE khác unique key

Khi tạo **unique index** có `INCLUDE`, tính duy nhất được đánh giá theo **key columns**, không theo included columns. Không dùng `INCLUDE` để thêm một cột vào khóa nghiệp vụ duy nhất mà vẫn giữ nguyên ý nghĩa unique.

### 11.4. Khác biệt phương ngữ

SQL Server cũng có `INCLUDE` trên một số kiểu nonclustered index. PostgreSQL hỗ trợ `INCLUDE` cho B-tree và các trường hợp được phương thức chỉ mục hỗ trợ. MySQL và SQLite không cung cấp một cú pháp `INCLUDE (...)` tương đương tổng quát trong `CREATE INDEX` thông thường; cần chọn thiết kế phù hợp từng DBMS.

## 12. DROP INDEX: xóa cấu trúc chỉ mục, không xóa dữ liệu bảng

Trên PostgreSQL:

```sql
DROP INDEX idx_orders_tenant;
```

Lệnh này xóa **chỉ mục** `idx_orders_tenant`. Những hàng trong `sales_orders_idx` vẫn tồn tại; truy vấn vẫn trả dữ liệu đúng nếu không phụ thuộc đến đối tượng index theo cách đặc biệt.

### 12.1. Vì sao phải DROP INDEX?

Các lý do phổ biến:

- Index không còn được sử dụng bởi workload hiện tại.
- Hai index trùng/lặp chức năng và chi phí duy trì vượt lợi ích.
- Một index cũ không phù hợp sau khi đổi thứ tự cột hoặc mẫu truy vấn.
- Index rất lớn nhưng không mang lại lợi ích tương xứng.
- Cần dọn một index lỗi/không hợp lệ từ quá trình xây dựng không hoàn tất.

**Không** kết luận index vô ích chỉ vì một lần `EXPLAIN` trên bảng nhỏ không thấy dùng nó. Nó có thể phục vụ truy vấn khác, ràng buộc dữ liệu, hoạt động bảo trì, hoặc một thời điểm khác trong chu kỳ tải.

### 12.2. DROP INDEX IF EXISTS

```sql
DROP INDEX IF EXISTS idx_orders_tenant;
```

Nếu index không tồn tại, PostgreSQL có thể phát thông báo và bỏ qua lỗi “không tìm thấy”. Điều này hữu ích trong migration được thiết kế cẩn thận, nhưng **không thay thế việc xác định đúng index và đúng schema**.

Trong môi trường có nhiều schema, tên có thể cần được chỉ rõ schema:

```sql
DROP INDEX IF EXISTS public.idx_orders_tenant;
```

Chỉ sử dụng ví dụ này nếu index nằm trong schema `public`. Không tự suy ra schema từ tên bảng.

### 12.3. DROP INDEX không phải DROP TABLE

| Lệnh | Tác động chính |
|---|---|
| `DROP INDEX index_name` | Loại cấu trúc chỉ mục |
| `DROP TABLE table_name` | Loại bảng và dữ liệu của bảng theo cơ chế DBMS |
| `DELETE FROM table WHERE ...` | Xóa các hàng khớp điều kiện |
| `TRUNCATE TABLE ...` | Loại toàn bộ hàng trong bảng theo ngữ nghĩa riêng |

Không thay thế những lệnh này cho nhau. `DROP INDEX` không làm mất hàng dữ liệu, nhưng có thể làm truy vấn **chậm đi đáng kể** hoặc ảnh hưởng tính duy nhất nếu index đang là ràng buộc không thể xóa riêng.

### 12.4. Index phục vụ constraint có quan hệ phụ thuộc

Trong PostgreSQL, chỉ mục tự động hỗ trợ `PRIMARY KEY` hoặc `UNIQUE constraint` có phụ thuộc với constraint. Câu:

```sql
DROP INDEX sales_orders_idx_pkey;
```

có thể bị từ chối vì chỉ mục phục vụ khóa chính. **Không dùng `CASCADE` một cách tùy tiện** để cố xóa bằng được; có thể kéo theo gỡ ràng buộc hoặc đối tượng phụ thuộc quan trọng.

Muốn đổi thiết kế ràng buộc cần một migration riêng có kế hoạch, không gộp vào bài “dọn index” thông thường.

## 13. PostgreSQL: CREATE INDEX CONCURRENTLY và DROP INDEX CONCURRENTLY

Tạo hoặc xóa chỉ mục trên bảng đang phục vụ ứng dụng có thể ảnh hưởng đến giao dịch ghi.

### 13.1. CREATE INDEX thông thường

```sql
CREATE INDEX idx_orders_customer_time
ON sales_orders_idx (
    tenant_id,
    customer_id,
    ordered_at DESC,
    order_id DESC
);
```

Trên một bảng lớn đang được ghi liên tục, thao tác tạo chỉ mục thông thường có thể **chặn một số thao tác ghi** trong thời gian xây dựng. Chính xác loại khóa và hành vi chờ phụ thuộc DBMS, phiên bản và cách xây dựng.

### 13.2. CREATE INDEX CONCURRENTLY

PostgreSQL hỗ trợ:

```sql
CREATE INDEX CONCURRENTLY idx_orders_customer_time
ON sales_orders_idx (
    tenant_id,
    customer_id,
    ordered_at DESC,
    order_id DESC
);
```

Mục tiêu của `CONCURRENTLY` là xây dựng chỉ mục với **mức cản trở thao tác ghi thông thường thấp hơn** so với cách tạo thông thường. Tuy nhiên:

- Có thể cần nhiều lần quét bảng và mất nhiều thời gian hơn.
- Vẫn phải phối hợp với các transaction đang chạy và có những khoảng chờ.
- Tốn I/O, CPU và tài nguyên lưu trữ.
- Có những hạn chế khi xây dựng index trên bảng phân vùng hoặc thao tác trong những trạng thái đặc biệt.
- Nếu thao tác thất bại, có thể để lại **index không hợp lệ (*invalid index*)** cần được kiểm tra và xử lý.

**Ràng buộc cú pháp quan trọng:** `CREATE INDEX CONCURRENTLY` **không được chạy bên trong một transaction block tường minh** trong PostgreSQL.

```sql
-- KHÔNG hợp lệ trong PostgreSQL:
BEGIN;
CREATE INDEX CONCURRENTLY idx_orders_customer_time
ON sales_orders_idx (tenant_id, customer_id, ordered_at);
COMMIT;
```

Điều này cũng quan trọng với **migration framework** mặc định bọc mọi DDL trong transaction; phải cấu hình bước tương ứng cho phép thao tác không nằm trong transaction block khi dùng `CONCURRENTLY`.

### 13.3. DROP INDEX CONCURRENTLY

PostgreSQL có:

```sql
DROP INDEX CONCURRENTLY IF EXISTS idx_orders_customer_time;
```

Lệnh nhằm giảm cản trở truy cập so với cách drop thông thường trong những điều kiện hỗ trợ. Nó cũng có hạn chế:

- Không chạy trong transaction block tường minh.
- Không dùng với `CASCADE` theo cú pháp thông thường của tùy chọn này.
- Không được dùng để tùy tiện loại index phục vụ constraint.
- Cần xét các transaction đang chạy và đối tượng phụ thuộc.

Đừng coi `CONCURRENTLY` là “không có khóa, không có chờ, không có rủi ro”; nó **giảm một loại gián đoạn**, không loại bỏ hoàn toàn chi phí triển khai.

### 13.4. Khi nào nên dùng CREATE INDEX thường?

Trên bảng nhỏ, môi trường phát triển, hoặc giai đoạn bảo trì có kiểm soát, `CREATE INDEX` thông thường có thể đơn giản và nhanh hơn. Trên bảng sản xuất lớn phải phục vụ ghi liên tục, `CONCURRENTLY` thường đáng cân nhắc, nhưng cần đánh giá tải và cách quản lý lỗi.

## 14. Đọc kế hoạch truy vấn bằng EXPLAIN

`CREATE INDEX` chỉ tạo ra một **lựa chọn** cho optimizer, không ép nó phải dùng lựa chọn đó.

### 14.1. EXPLAIN chỉ xem kế hoạch

Trong PostgreSQL:

```sql
EXPLAIN
SELECT order_id, ordered_at
FROM sales_orders_idx
WHERE tenant_id = 1
  AND status = 'PAID'
ORDER BY ordered_at DESC, order_id DESC
LIMIT 3;
```

`EXPLAIN` trả về kế hoạch được ước lượng. Các nút có thể gặp:

| Nút kế hoạch | Ý nghĩa khái quát |
|---|---|
| `Seq Scan` | Đọc tuần tự dữ liệu của bảng |
| `Index Scan` | Dùng index để tìm hàng rồi có thể đọc bảng |
| `Index Only Scan` | Có khả năng trả dữ liệu từ index, vẫn có thể cần kiểm tra visibility ở heap |
| `Bitmap Index Scan` + `Bitmap Heap Scan` | Gom vị trí hàng qua index rồi đọc các trang bảng cần thiết |
| `Sort` | Sắp xếp dữ liệu theo yêu cầu |
| `Limit` | Giới hạn số hàng đầu ra |
| `Nested Loop`, `Hash Join`, `Merge Join` | Những chiến lược nối bảng có thể xuất hiện trong truy vấn phức tạp |

Với chỉ mục ghép phù hợp và dữ liệu đủ lớn, kế hoạch **có thể** có `Index Scan` cùng `Limit`, không cần `Sort` riêng. Nhưng trên bảng 18 hàng của bài, `Seq Scan` cộng `Sort` có thể hoàn toàn hợp lý.

### 14.2. EXPLAIN ANALYZE đo thực thi thật

`EXPLAIN` thông thường chủ yếu hiển thị **ước lượng**; còn:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT order_id, ordered_at
FROM sales_orders_idx
WHERE tenant_id = 1
  AND status = 'PAID'
ORDER BY ordered_at DESC, order_id DESC
LIMIT 3;
```

thực thi câu truy vấn và ghi nhận thông tin đo được, như thời gian, số hàng thực tế, bộ đệm và số lần lặp. Khi đọc:

- `rows` ước lượng khác xa `actual rows` có thể gợi ý vấn đề thống kê/phân bố.
- `Buffers` cho biết hoạt động bộ đệm được ghi nhận, không phải chỉ một con số “tốc độ”.
- `Sort` có thể tiêu tốn bộ nhớ hoặc I/O tùy kích thước.
- Một index có thể giúp giảm thời gian hoặc đọc I/O, nhưng không bảo đảm luôn được chọn.

**Cảnh báo:** `EXPLAIN ANALYZE` **thực sự chạy câu lệnh**. Với `UPDATE`, `DELETE` hoặc `INSERT`, nó có thể thay đổi dữ liệu thật. Không chạy phân tích DML trên sản xuất mà không kiểm soát transaction và hậu quả; kể cả rollback vẫn có những side effect ngoài giao dịch cần cân nhắc.

### 14.3. Thống kê của bộ tối ưu

PostgreSQL có:

```sql
ANALYZE sales_orders_idx;
```

để thu thập/cập nhật thống kê giúp bộ tối ưu ước lượng phân bố và số hàng. Tạo index không tự bảo đảm thống kê của mọi cột và mọi mối tương quan đủ để chọn kế hoạch tốt.

Khi dữ liệu thay đổi lớn hoặc phân bố bị lệch giữa các tenant, thống kê và ước lượng có thể ảnh hưởng đáng kể đến cách dùng chỉ mục.

### 14.4. Không “chứng minh” chỉ mục tốt bằng một lần EXPLAIN

Một đánh giá phù hợp thường xem:

1. Truy vấn thực tế có tham số đại diện.
2. Số hàng, phân bố tenant/status và độ chọn lọc thật.
3. Kế hoạch và thời gian trước/sau khi đổi chỉ mục.
4. Chi phí INSERT/UPDATE/DELETE và kích thước index.
5. Tác động với các truy vấn khác.
6. Tải đồng thời và cache trong điều kiện phù hợp.

Không cần cố ép optimizer dùng index chỉ vì đã bỏ công tạo nó; mục tiêu là **thời gian và chi phí tổng thể tốt hơn**, không phải “plan phải có chữ Index Scan”.

## 15. Chỉ mục và JOIN

Trong một phép `JOIN`, một bảng có thể cần tìm nhanh các hàng liên quan theo khóa ngoại hoặc khóa nghiệp vụ.

Giả sử có bảng khách:

```sql
CREATE TABLE customers_index_lab (
    tenant_id INTEGER NOT NULL,
    customer_id INTEGER NOT NULL,
    customer_name TEXT NOT NULL,
    PRIMARY KEY (tenant_id, customer_id)
);
```

Bảng này có khóa ghép `(tenant_id,customer_id)`. Khi cần báo cáo đơn theo khách:

```sql
SELECT
    c.customer_name,
    o.order_id,
    o.ordered_at
FROM customers_index_lab AS c
JOIN sales_orders_idx AS o
    ON o.tenant_id = c.tenant_id
   AND o.customer_id = c.customer_id
WHERE c.tenant_id = 1
  AND c.customer_id = 11
ORDER BY o.ordered_at DESC, o.order_id DESC;
```

Một index trên bảng đơn như:

```sql
CREATE INDEX idx_orders_customer_time
ON sales_orders_idx (
    tenant_id,
    customer_id,
    ordered_at DESC,
    order_id DESC
);
```

có thể hữu ích cho việc tìm các đơn của một khách, rồi trả theo thứ tự mới nhất.

### 15.1. Khóa ngoại và chỉ mục không phải một điều

Trong PostgreSQL, một `FOREIGN KEY` **không tự động tạo index trên mọi cột khóa ngoại ở phía bảng con**. Tùy workload, ta có thể cần chỉ mục ở phía con để:

- Tìm những hàng con khi truy vấn theo khóa cha.
- Hỗ trợ kiểm tra tác động khi xóa/cập nhật khóa cha.
- Giảm chi phí của một số phép JOIN.

Nhưng không phải khóa ngoại nào cũng cần một chỉ mục riêng trong mọi thiết kế. Nếu đã có composite index với đúng tiền tố, có thể chỉ mục đó đã phục vụ nhu cầu; tạo thêm index đơn trùng chức năng có thể tốn chi phí ghi.

### 15.2. Index không quyết định toàn bộ JOIN plan

Bộ tối ưu có thể chọn **nested loop**, **hash join** hoặc **merge join** tùy kích thước và điều kiện. Một truy vấn nối hai bảng lớn để đọc phần lớn dữ liệu đôi khi dùng hash join/quét bảng nhanh hơn tra chỉ mục từng hàng.

Không mặc định “có index thì JOIN phải là nested loop” hoặc “JOIN không dùng index tức là thiếu index”.

## 16. Chi phí của chỉ mục và các dấu hiệu lạm dụng

Chỉ mục cải thiện đường đọc của **một số truy vấn**, nhưng có chi phí ở các hoạt động khác.

### 16.1. Chi phí lưu trữ

Mỗi index chiếm không gian trên đĩa và buffer cache. Một index có nhiều key columns, cột văn bản dài hoặc `INCLUDE` nhiều cột thường lớn hơn một index ngắn trên khóa gọn.

### 16.2. Chi phí ghi

Khi chèn một đơn:

```sql
INSERT INTO sales_orders_idx (...)
VALUES (...);
```

database phải cập nhật các index liên quan bên cạnh bảng.

Khi sửa `status`, `ordered_at` hoặc những cột được index:

```sql
UPDATE sales_orders_idx
SET status = 'PAID'
WHERE order_id = 1002;
```

việc thay đổi có thể đòi hỏi bảo trì các chỉ mục liên quan. Trong PostgreSQL còn có tối ưu cập nhật như **HOT update** trong những điều kiện nhất định; thêm index trên một cột thường xuyên thay đổi có thể làm giảm cơ hội tối ưu đó.

### 16.3. Chỉ mục có thể trùng chức năng

Giả sử đã có:

```sql
CREATE INDEX idx_orders_tenant
ON sales_orders_idx (tenant_id);

CREATE INDEX idx_orders_tenant_status
ON sales_orders_idx (tenant_id, status);
```

Chỉ mục thứ hai có **tiền tố `tenant_id`**, nên có thể phục vụ nhiều truy vấn chỉ lọc tenant mà chỉ mục đầu cũng phục vụ. Nhưng chưa chắc index đơn là thừa: nó nhỏ hơn, có thể tiết kiệm I/O cho một workload đặc biệt, và một số cơ chế optimizer khác nhau.

Muốn loại index cần đánh giá:

- Truy vấn và tần suất sử dụng trong thời gian đại diện.
- Dung lượng và chi phí bảo trì.
- Khả năng phục vụ `ORDER BY`/covering và điều kiện khác.
- Thời gian đo được trước và sau trong thử nghiệm phù hợp.
- Index có đang hỗ trợ constraint không.

Không xóa index chỉ dựa trên việc thấy **cùng cột đầu tiên**.

### 16.4. Tránh “mỗi truy vấn một index” không kiểm soát

Nếu ứng dụng có hàng trăm câu query, việc tạo riêng một index ghép cho mỗi câu có thể:

- Làm tăng thời gian ghi.
- Tốn bộ nhớ cache và đĩa.
- Làm migration/bảo trì phức tạp.
- Khiến lựa chọn kế hoạch trở nên khó dự đoán hơn.

Thay vào đó, nhóm các truy vấn có **cùng tiền tố lọc/thứ tự**, tìm vài index phục vụ tốt các luồng quan trọng nhất, rồi đo tác động tổng thể.

## 17. Cú pháp theo các hệ quản trị

Ý tưởng chỉ mục trên nhiều cột xuất hiện rộng rãi, nhưng cú pháp tạo/xóa và các tính năng bổ sung không đồng nhất.

### 17.1. PostgreSQL

```sql
-- Chỉ mục ghép thông thường:
CREATE INDEX idx_orders_tenant_status_time
ON sales_orders_idx (
    tenant_id,
    status,
    ordered_at DESC,
    order_id DESC
);

-- Chỉ mục duy nhất trên cặp khóa:
CREATE UNIQUE INDEX uq_orders_tenant_ref
ON sales_orders_idx (tenant_id, external_ref);

-- Chỉ mục partial:
CREATE INDEX idx_orders_paid_time
ON sales_orders_idx (tenant_id, ordered_at DESC)
WHERE status = 'PAID';

-- Xóa:
DROP INDEX IF EXISTS idx_orders_paid_time;
```

PostgreSQL có `CONCURRENTLY` cho những tình huống tạo/xóa index online hơn, có `INCLUDE`, expression index và nhiều loại access method. `DROP INDEX` nhận tên index, **không** viết thêm `ON table_name` như MySQL.

### 17.2. MySQL / InnoDB

```sql
-- MySQL:
CREATE INDEX idx_orders_tenant_status_time
ON sales_orders_idx (
    tenant_id,
    status,
    ordered_at DESC,
    order_id DESC
);

-- Xóa index phải chỉ rõ bảng:
DROP INDEX idx_orders_tenant_status_time
ON sales_orders_idx;
```

Ngoài ra MySQL có:

```sql
ALTER TABLE sales_orders_idx
DROP INDEX idx_orders_tenant_status_time;
```

Những điểm cần chú ý:

- Trong InnoDB, **PRIMARY KEY** gắn với clustered organization; secondary index chứa thông tin khóa để định vị hàng. Thiết kế index vì thế có chi phí/đặc điểm khác PostgreSQL.
- MySQL 8.0 có hỗ trợ **descending index key parts** phù hợp phiên bản/engine; không giả định mọi bản cũ xử lý `DESC` tương đương.
- Việc tạo/xóa index online và khóa dùng các tùy chọn DDL khác như `ALGORITHM`/`LOCK` tùy phiên bản và loại thao tác, **không dùng `CONCURRENTLY` của PostgreSQL**.
- Function-based indexing, generated columns và độ dài index trên chuỗi phụ thuộc phiên bản/charset/engine.
- Cú pháp `CREATE INDEX ... WHERE status = 'PAID'` của PostgreSQL **không** chuyển nguyên văn sang MySQL.

Trong MySQL, xem kế hoạch có thể dùng:

```sql
EXPLAIN
SELECT order_id
FROM sales_orders_idx
WHERE tenant_id = 1
  AND status = 'PAID';
```

### 17.3. SQL Server

```sql
-- SQL Server:
CREATE NONCLUSTERED INDEX idx_orders_tenant_status_time
ON dbo.sales_orders_idx (
    tenant_id,
    status,
    ordered_at DESC,
    order_id DESC
)
INCLUDE (total_amount);
```

SQL Server có **clustered index** và **nonclustered index** với khác biệt quan trọng: clustered index quyết định cách tổ chức dữ liệu của bảng theo khóa, còn nonclustered index là cấu trúc tra cứu phụ. Không đồng nhất chúng với index B-tree phụ của PostgreSQL chỉ vì tên khóa giống nhau.

Xóa chỉ mục không phải constraint:

```sql
DROP INDEX idx_orders_tenant_status_time
ON dbo.sales_orders_idx;
```

Filtered index trong SQL Server có dạng:

```sql
CREATE NONCLUSTERED INDEX idx_orders_paid
ON dbo.sales_orders_idx (tenant_id, ordered_at DESC)
WHERE status = 'PAID';
```

Các tùy chọn như `ONLINE = ON` cho tạo lại/quản lý chỉ mục phụ thuộc phiên bản, edition, loại index và tác vụ. **Không có bảo đảm mọi thao tác index đều online**.

Kế hoạch truy vấn có thể xem bằng **Actual/Estimated Execution Plan** hoặc công cụ tương ứng; các tên operator và số liệu khác PostgreSQL.

### 17.4. SQLite

```sql
-- SQLite:
CREATE INDEX IF NOT EXISTS idx_orders_tenant_status_time
ON sales_orders_idx (
    tenant_id,
    status,
    ordered_at DESC,
    order_id DESC
);

DROP INDEX IF EXISTS idx_orders_tenant_status_time;
```

SQLite hỗ trợ **chỉ mục nhiều cột**, expression index và partial index ở các phiên bản có tính năng tương ứng:

```sql
CREATE INDEX idx_orders_paid
ON sales_orders_idx (tenant_id, ordered_at DESC)
WHERE status = 'PAID';
```

Trong SQLite, kiểu dữ liệu, collation, quy tắc so khớp và cách tối ưu truy vấn có khác biệt; không áp đặt mọi chi tiết của PostgreSQL.

Xem kế hoạch:

```sql
EXPLAIN QUERY PLAN
SELECT order_id
FROM sales_orders_idx
WHERE tenant_id = 1
  AND status = 'PAID';
```

`EXPLAIN QUERY PLAN` của SQLite có định dạng riêng, không có các operator/tùy chọn `BUFFERS` như PostgreSQL.

### 17.5. Oracle Database

```sql
-- Oracle:
CREATE INDEX idx_orders_tenant_status_time
ON sales_orders_idx (
    tenant_id,
    status,
    ordered_at DESC,
    order_id DESC
);

DROP INDEX idx_orders_tenant_status_time;
```

Oracle có B-tree composite indexes, function-based indexes, index-organized tables, bitmap indexes và các tùy chọn online tùy phiên bản. Một chỉ mục bitmap có thể có ích trong một số kho phân tích ít cập nhật, nhưng không nên dùng nó như thay thế mặc định cho B-tree của ứng dụng OLTP ghi liên tục.

Oracle có các công cụ xem execution plan như `EXPLAIN PLAN` và `DBMS_XPLAN`, khác cách trình bày của PostgreSQL.

### 17.6. Bảng so sánh nhanh

| Nhu cầu | PostgreSQL | MySQL | SQL Server | SQLite | Oracle |
|---|---|---|---|---|---|
| Chỉ mục ghép | `CREATE INDEX ... ON t(a,b)` | Tương tự | `CREATE INDEX ... ON dbo.t(a,b)` | Tương tự | Tương tự |
| Xóa index | `DROP INDEX idx` | `DROP INDEX idx ON t` | `DROP INDEX idx ON dbo.t` | `DROP INDEX idx` | `DROP INDEX idx` |
| Descending key | Hỗ trợ | MySQL 8.0+/engine phù hợp | Hỗ trợ | Hỗ trợ | Hỗ trợ |
| Partial/filtered index | `WHERE predicate` | Không cùng cú pháp trực tiếp | Filtered index `WHERE` | Partial index `WHERE` | Cần kỹ thuật/tính năng khác |
| Included columns | `INCLUDE` | Không cùng cú pháp phổ biến | `INCLUDE` | Không cùng cú pháp | Cơ chế khác tùy phiên bản |
| Chỉ mục biểu thức | Hỗ trợ | Theo phiên bản/engine | Computed column/index hoặc cách tương ứng | Hỗ trợ | Function-based index |
| Thao tác giảm chặn ghi | `CONCURRENTLY` | Online DDL options | `ONLINE` và tùy chọn khác | Cơ chế khóa giao dịch riêng | Online index options |
| Xem kế hoạch | `EXPLAIN` | `EXPLAIN` | Execution Plan | `EXPLAIN QUERY PLAN` | `EXPLAIN PLAN`/`DBMS_XPLAN` |

Khi port SQL, phải kiểm tra **đúng DBMS, phiên bản và kiểu index**. Một tùy chọn có cùng tên chưa chắc cho cùng mức khóa, cùng cách xử lý `NULL` hoặc cùng chi phí.

## 18. Quy trình thiết kế và quản lý chỉ mục

Thay vì tạo index ngay khi thấy một câu query chậm, có thể làm theo quy trình:

### Bước 1 — Xác định truy vấn và mục tiêu

Ví dụ:

> Trả ba đơn PAID mới nhất của một tenant trong khoảng ngày. Truy vấn chạy hàng nghìn lần mỗi phút; cần độ trễ thấp.

Ghi lại `WHERE`, `JOIN`, `ORDER BY`, `LIMIT` và các cột trả ra.

### Bước 2 — Xác định khóa và phân bố

Xem tenant có bao nhiêu đơn, status phổ biến đến đâu, mốc thời gian thường chọn rộng hay hẹp, bảng có bao nhiêu lần ghi mỗi giây.

### Bước 3 — Đề xuất thứ tự khóa

Với query:

```sql
WHERE tenant_id = ?
  AND status = 'PAID'
  AND ordered_at >= ?
ORDER BY ordered_at DESC, order_id DESC
LIMIT 3
```

ứng viên hợp lý:

```sql
(tenant_id, status, ordered_at DESC, order_id DESC)
```

hoặc partial index chỉ chứa PAID:

```sql
(tenant_id, ordered_at DESC, order_id DESC)
WHERE status = 'PAID'
```

### Bước 4 — Xem chỉ mục hiện có

Kiểm tra khóa chính, chỉ mục duy nhất, tiền tố trùng, chỉ mục phục vụ những query khác. Tránh tạo index dư thừa chỉ vì không nhớ schema.

### Bước 5 — Đo trước khi thay đổi

Xem kế hoạch và thời gian với dữ liệu đủ lớn, số lượng hàng đi qua các bước, số lần đọc bảng, mức sort và tải ghi. Bảng 18 dòng chỉ đủ minh họa chức năng SQL, không đại diện hiệu năng sản xuất.

### Bước 6 — Tạo/chỉnh chỉ mục trong quy trình được phép

Lựa chọn tạo thông thường hay online/concurrent phù hợp. Tính đến lock, thời gian chạy, tài nguyên và khả năng index invalid nếu build lỗi.

### Bước 7 — Đo sau khi thay đổi

Kiểm tra truy vấn mục tiêu, truy vấn khác và chi phí ghi. Nếu lợi ích quá nhỏ hoặc tải ghi tăng nhiều, cân nhắc điều chỉnh.

### Bước 8 — Xóa chỉ mục cũ có kiểm soát

Chỉ drop khi xác định không còn cần cho workload hoặc constraint, có kế hoạch quay lại nếu hiệu năng giảm. Kiểm tra chính xác tên và schema, tránh dùng `CASCADE` không cần thiết.

## 19. Các lỗi thường gặp

### Lỗi 1 — Nghĩ thứ tự cột của composite index không quan trọng

`(tenant_id,status,ordered_at)` và `(ordered_at,status,tenant_id)` khác nhau rõ về vùng khóa và thứ tự. Phải thiết kế theo `WHERE` và `ORDER BY`.

### Lỗi 2 — Khẳng định chỉ mục ghép tuyệt đối không dùng nếu thiếu cột đầu

Quy tắc tiền tố trái là heuristic quan trọng, nhưng optimizer có thể dùng skip scan, bitmap/combine, hoặc quét chỉ mục theo cách khác. Đừng biến heuristic thành một khẳng định tuyệt đối.

### Lỗi 3 — Tin rằng cột sau điều kiện range hoàn toàn vô ích

Cột phía sau có thể góp phần kiểm tra trong index, bao phủ hoặc sắp thứ tự trong phạm vi hẹp; nhưng thường không giúp giới hạn dải quét mạnh như equality columns đứng trước.

### Lỗi 4 — Tạo từng index đơn rồi cho rằng bằng một composite index

Index intersection có thể xảy ra nhưng chi phí và khả năng giữ thứ tự khác composite index. Đừng mặc định ba index đơn thay thế một B-tree ba cột.

### Lỗi 5 — Đưa status vào giữa nhưng vẫn muốn sort theo thời gian toàn tenant

`(tenant_id,status,ordered_at DESC)` được chia nhóm theo status trước. Muốn `ORDER BY ordered_at DESC` **trên mọi status** của một tenant, cần cân nhắc `(tenant_id,ordered_at DESC)`.

### Lỗi 6 — Có index thì kết quả SELECT tự được sắp

Không có `ORDER BY` cuối cùng, SQL không cam kết thứ tự. Index scan có thể bị thay bằng Seq Scan/Bitmap Scan hoặc kế hoạch khác.

### Lỗi 7 — Tạo index trên mọi cột trong WHERE

Chỉ mục nào cũng có chi phí. Một cột lọc ít chọn lọc hoặc query đọc phần lớn bảng có thể không được hưởng lợi. Hãy ưu tiên workload và đo kế hoạch.

### Lỗi 8 — Chỉ dùng cardinality để chọn thứ tự cột

Điều kiện bằng, yêu cầu dùng tiền tố, ORDER BY, LIMIT và phân bố dữ liệu đều ảnh hưởng. Không có một thứ tự đúng cho mọi query.

### Lỗi 9 — Cho rằng index-only scan luôn không đọc bảng

PostgreSQL còn phải kiểm tra visibility. Included columns giúp bao phủ dữ liệu, nhưng không bảo đảm không có heap fetch.

### Lỗi 10 — Nghĩ INCLUDE tương đương key column

`INCLUDE(total_amount)` lưu payload để trả giá trị; nó không tạo thứ tự tìm kiếm theo `total_amount` như key column.

### Lỗi 11 — Tạo UNIQUE trên mã nghiệp vụ quên phạm vi tenant

`UNIQUE(external_ref)` sai khi mã chỉ duy nhất **trong từng tenant**. Dùng cặp `(tenant_id,external_ref)` nếu đúng quy tắc.

### Lỗi 12 — Nghĩ UNIQUE xử lý NULL giống nhau trên mọi DBMS

Quy tắc `NULL` trong unique index/constraint có thể khác theo hệ và phiên bản. Xác định rõ khi nào khóa được phép thiếu và cách biểu diễn thiếu.

### Lỗi 13 — Xóa index của PRIMARY KEY như index thường

Index phục vụ constraint có quan hệ phụ thuộc; `DROP INDEX` có thể bị từ chối. Không gỡ ràng buộc để đổi hiệu năng mà không có migration rõ ràng.

### Lỗi 14 — Nghĩ DROP INDEX xóa dữ liệu bảng

`DROP INDEX` xóa cấu trúc truy cập, không xóa các hàng. Nhưng truy vấn có thể chậm hơn; không nhầm với `DROP TABLE` hoặc `DELETE`.

### Lỗi 15 — Nghĩ IF NOT EXISTS xác minh định nghĩa

`CREATE INDEX IF NOT EXISTS idx...` chủ yếu xử lý tồn tại **theo tên**, không chứng minh cấu trúc index đã có là đúng khóa, hướng, predicate hoặc INCLUDE mong muốn.

### Lỗi 16 — Chạy CREATE INDEX CONCURRENTLY bên trong BEGIN

Trong PostgreSQL, `CREATE INDEX CONCURRENTLY` không được chạy trong transaction block tường minh. Migration framework phải hỗ trợ bước ngoài transaction.

### Lỗi 17 — Coi CONCURRENTLY là không có khóa/chờ

Concurrent build vẫn tiêu thụ tài nguyên, có thể chờ giao dịch và để lại invalid index khi lỗi. Cần theo dõi trạng thái xây và có phương án xử lý.

### Lỗi 18 — Tin rằng EXPLAIN phải dùng Index Scan mới là tốt

Trên bảng nhỏ hoặc query đọc nhiều hàng, `Seq Scan` có thể hợp lý. Mục tiêu là chi phí/thời gian tổng thể, không phải ép một operator xuất hiện.

### Lỗi 19 — Dùng EXPLAIN ANALYZE với DELETE mà không biết nó thực thi thật

`EXPLAIN ANALYZE` chạy statement; với DML, dữ liệu có thể bị thay đổi. Phải có môi trường và transaction phù hợp, không thử bừa trên sản xuất.

### Lỗi 20 — Sao chép DROP INDEX giữa các DBMS

PostgreSQL dùng `DROP INDEX idx`; MySQL và SQL Server thường cần `DROP INDEX idx ON table`; SQLite/Oracle lại có dạng riêng. Cú pháp không hoán đổi nguyên văn.

### Lỗi 21 — Tạo index phục vụ một query nhưng không xét ghi dữ liệu

Index có thể tăng tốc SELECT nhưng làm INSERT/UPDATE/DELETE chậm hơn, tăng dung lượng và giảm khả năng HOT update trong những trường hợp PostgreSQL. Cần cân bằng đọc–ghi.

### Lỗi 22 — Tạo partial index rồi không hiểu vì sao prepared query không dùng

Planner phải chứng minh predicate truy vấn hàm ý predicate index. Với tham số chưa biết và generic plan, điều này có thể không thực hiện được.

### Lỗi 23 — Tạo trùng nhiều index rồi xóa bừa một cái

Hai index có cùng tiền tố có thể phục vụ các query khác nhau; đồng thời index nhỏ có thể tiết kiệm chi phí hơn cho truy vấn hẹp. Phải xem usage và plan thực tế trước khi drop.

### Lỗi 24 — Không kiểm tra sự tồn tại của index khóa ngoại phía con

Trong PostgreSQL, khóa ngoại ở bảng con không mặc định có index tự động trên mọi cột tham chiếu. Với join hoặc xóa/cập nhật hàng cha thường xuyên, cần cân nhắc chỉ mục phù hợp ở phía con.

## 20. Bài tập thực hành có đáp án

Các bài dưới đây dùng bảng `sales_orders_idx` và 18 hàng ở mục 2. Các bài về hiệu năng tập trung vào **phân tích cấu trúc chỉ mục có thể hữu ích**, không yêu cầu DBMS chắc chắn chọn `Index Scan` trên bảng nhỏ. Khi thử tạo/xóa, hãy thực hành trong môi trường riêng và xác định index nào đã được tạo ở bài trước để tránh lỗi trùng tên.

### Bài 1 — Tạo index một cột

Viết chỉ mục cho truy vấn `WHERE tenant_id = ?`:

```sql
CREATE INDEX idx_orders_tenant
ON sales_orders_idx (tenant_id);
```

**Đáp án:** đây là B-tree một cột theo mặc định trong PostgreSQL. Nó có thể giúp lọc tenant, nhưng trên bảng 18 hàng optimizer vẫn có thể chọn `Seq Scan`.

### Bài 2 — Tạo chỉ mục cho đơn PAID mới nhất

Truy vấn cần `tenant_id = 1`, `status = 'PAID'`, thời gian từ 03/09 và `ORDER BY ordered_at DESC, order_id DESC LIMIT 3`.

```sql
CREATE INDEX idx_orders_tenant_status_time
ON sales_orders_idx (
    tenant_id, status, ordered_at DESC, order_id DESC
);
```

**Đáp án:** hai khóa bằng đứng trước, tiếp theo thời gian và khóa phân định. Trên dữ liệu mẫu, truy vấn trả **1007, 1006, 1004**.

### Bài 3 — Dùng một index khác cho mọi trạng thái

Màn hình mới muốn ba đơn mới nhất của tenant 1, **không lọc status**. Đề xuất:

```sql
CREATE INDEX idx_orders_tenant_time
ON sales_orders_idx (
    tenant_id, ordered_at DESC, order_id DESC
);
```

**Đáp án:** trong tenant 1, các hàng được sắp theo thời gian mà không bị chia nhóm status. Truy vấn tương ứng có thể trả các ID **1008, 1007, 1006** theo timestamp giảm dần trên dữ liệu mẫu.

### Bài 4 — Vì sao status ở giữa làm thay đổi kết quả sắp xếp?

Giải thích vì sao `(tenant_id,status,ordered_at DESC)` không phải chỉ mục lý tưởng để bảo đảm `ORDER BY ordered_at DESC` **trên tất cả trạng thái của tenant**.

**Đáp án:** index chia các hàng của tenant theo `status` trước, nên từng nhóm status có thứ tự thời gian riêng, không phải một thứ tự thời gian chung cho mọi status.

### Bài 5 — Tiền tố trái

Với index `(tenant_id,status,ordered_at DESC,order_id DESC)`, hai query:

```sql
-- A
WHERE tenant_id = 1 AND status = 'PAID'

-- B
WHERE status = 'PAID'
```

query nào khớp tiền tố thuận lợi hơn?

**Đáp án:** A dùng được tiền tố tenant/status rõ ràng. B bỏ cột đầu; optimizer có thể cần quét vùng rộng, dùng skip scan/chiến lược khác hoặc chọn index khác.

### Bài 6 — Điều kiện khoảng sau điều kiện bằng

Viết truy vấn lấy đơn PAID của tenant 1 từ 03/09/2025 và dự đoán số hàng:

```sql
SELECT order_id
FROM sales_orders_idx
WHERE tenant_id = 1
  AND status = 'PAID'
  AND ordered_at >= TIMESTAMPTZ '2025-09-03 00:00:00+00'
ORDER BY ordered_at DESC, order_id DESC;
```

**Đáp án:** **1007, 1006, 1004**, tổng 3 hàng. Chỉ mục `(tenant_id,status,ordered_at DESC,order_id DESC)` có cấu trúc phù hợp với mẫu lọc và sort này.

### Bài 7 — Chỉ mục cho một khách trong tenant

Yêu cầu: lọc `tenant_id = 1 AND customer_id = 11`, trả đơn mới nhất. Chỉ mục:

```sql
CREATE INDEX idx_orders_tenant_customer_time
ON sales_orders_idx (
    tenant_id, customer_id, ordered_at DESC, order_id DESC
);
```

**Đáp án:** `tenant_id` và `customer_id` nhận diện nhóm, sau đó sắp mới nhất. Khách 11 của tenant 1 có các đơn **1007, 1004, 1002, 1001** theo thời gian giảm dần.

### Bài 8 — Hai index đơn hay một index ghép?

So sánh `INDEX(tenant_id)` và `INDEX(status)` với `INDEX(tenant_id,status,ordered_at DESC)` cho query lọc đồng thời tenant/status và lấy ba đơn mới nhất.

**Đáp án:** hai index đơn có thể được kết hợp trong một số plan, nhưng không tự tạo một dải khóa có thứ tự thời gian trong từng tenant/status. Index ghép thường là ứng viên tốt cho query này, cần đo thực tế.

### Bài 9 — Unique theo tenant

Chọn ràng buộc đúng khi `SHARED-001` xuất hiện ở tenant 1 và tenant 2 nhưng không được lặp **trong cùng tenant**:

```sql
CREATE UNIQUE INDEX uq_orders_tenant_ref
ON sales_orders_idx (tenant_id, external_ref);
```

**Đáp án:** unique trên cặp khóa, không unique chỉ trên `external_ref`.

### Bài 10 — Chỉ mục từng phần cho PAID

```sql
CREATE INDEX idx_orders_paid_tenant_time
ON sales_orders_idx (
    tenant_id, ordered_at DESC, order_id DESC
)
WHERE status = 'PAID';
```

**Đáp án:** chỉ mục chứa các hàng PAID. `status` không cần nằm trong key nếu partial predicate đã giới hạn đúng nhóm. Một truy vấn không lọc PAID không thể dùng chỉ mục này để đọc đủ mọi trạng thái.

### Bài 11 — Expression index

Đề bài: ứng dụng tìm email không phân biệt hoa/thường qua `LOWER(email) = ?`. Hãy viết index trên bảng `customer_email_idx`:

```sql
CREATE INDEX idx_customer_email_lower
ON customer_email_idx (LOWER(email));
```

**Đáp án:** index trên biểu thức `LOWER(email)` có thể phù hợp hơn index trên email gốc cho đúng dạng điều kiện này. Cần xét collation và mức chọn lọc.

### Bài 12 — Included column

Query lấy `order_id, ordered_at, total_amount` và lọc theo tenant/status. Viết index để `total_amount` có thể được đọc từ index nhưng không tham gia thứ tự key:

```sql
CREATE INDEX idx_orders_tenant_status_time_inc
ON sales_orders_idx (
    tenant_id, status, ordered_at DESC, order_id DESC
)
INCLUDE (total_amount);
```

**Đáp án:** `total_amount` là included column; PostgreSQL vẫn có thể cần heap fetch vì MVCC visibility.

### Bài 13 — DROP INDEX đúng cú pháp PostgreSQL

Xóa index `idx_orders_tenant` mà không xóa hàng:

```sql
DROP INDEX IF EXISTS idx_orders_tenant;
```

**Đáp án:** các đơn trong `sales_orders_idx` vẫn giữ nguyên. Bộ tối ưu chỉ mất một tùy chọn truy cập.

### Bài 14 — Vì sao không DROP index của PRIMARY KEY?

`order_id BIGINT PRIMARY KEY` đã tạo cấu trúc chỉ mục hỗ trợ. Có nên dùng `DROP INDEX sales_orders_idx_pkey` để giảm chi phí ghi không?

**Đáp án:** không. Index phục vụ constraint có phụ thuộc; việc gỡ sẽ ảnh hưởng toàn vẹn khóa chính và có thể bị PostgreSQL từ chối. Thay đổi constraint cần migration riêng.

### Bài 15 — CONCURRENTLY và transaction

Điều nào đúng?

```sql
-- A: lệnh có thể dùng ngoài transaction block tường minh.
CREATE INDEX CONCURRENTLY idx_orders_customer_time
ON sales_orders_idx (tenant_id, customer_id, ordered_at);

-- B: không được bọc CREATE INDEX CONCURRENTLY trong BEGIN/COMMIT.
BEGIN;
CREATE INDEX CONCURRENTLY idx_orders_customer_time
ON sales_orders_idx (tenant_id, customer_id, ordered_at);
COMMIT;
```

**Đáp án:** A thể hiện cú pháp hợp lệ nếu chưa có index cùng tên và điều kiện hỗ trợ; B không hợp lệ trong PostgreSQL vì `CREATE INDEX CONCURRENTLY` không chạy trong transaction block tường minh.

### Bài 16 — Đổi cú pháp DROP INDEX sang MySQL

Viết lệnh xóa `idx_orders_tenant_status_time` trên MySQL:

```sql
DROP INDEX idx_orders_tenant_status_time
ON sales_orders_idx;
```

**Đáp án:** MySQL yêu cầu chỉ rõ bảng trong mẫu này, khác PostgreSQL `DROP INDEX idx_orders_tenant_status_time;`.

### Bài 17 — Vì sao EXPLAIN không dùng index trên bảng nhỏ?

PostgreSQL vẫn chọn `Seq Scan` sau khi bạn tạo một composite index trên bảng 18 hàng. Có chắc chỉ mục sai không?

**Đáp án:** không. Bảng nhỏ có thể quét tuần tự rẻ hơn. Cần đánh giá với kích thước, phân bố, tham số và workload đại diện.

### Bài 18 — EXPLAIN ANALYZE có thực thi không?

Một người đề xuất:

```sql
EXPLAIN (ANALYZE, BUFFERS)
DELETE FROM sales_orders_idx
WHERE tenant_id = 1;
```

Có an toàn để chạy “chỉ xem kế hoạch” trên sản xuất không?

**Đáp án:** không. `ANALYZE` trong `EXPLAIN ANALYZE` thực thi statement. Với `DELETE`, dữ liệu có thể bị xóa thật. Muốn chỉ xem kế hoạch, dùng `EXPLAIN` không `ANALYZE` và vẫn cân nhắc câu lệnh/khả năng side effect.

### Bài 19 — Sắp xếp hướng trộn

Ứng dụng cần:

```sql
ORDER BY tenant_id ASC, ordered_at DESC
```

Đề xuất:

```sql
CREATE INDEX idx_orders_tenant_asc_time_desc
ON sales_orders_idx (tenant_id ASC, ordered_at DESC);
```

**Đáp án:** hướng hỗn hợp có ý nghĩa trong B-tree nhiều cột. Không giả định index hai cột đều ASC luôn đáp ứng thứ tự ASC/DESC hỗn hợp chỉ bằng quét ngược.

### Bài 20 — Tại sao cột status ít giá trị vẫn hữu ích?

`status` chỉ có ba giá trị. Có nên bỏ khỏi `(tenant_id,status,ordered_at DESC)` vì “low cardinality” không?

**Đáp án:** không nên kết luận như vậy. Nếu truy vấn thường lọc `tenant_id = ? AND status = 'PAID'`, `status` giúp phân nhóm khóa trong mỗi tenant và kết hợp với thời gian. Quyết định cần xét truy vấn thực.

### Bài 21 — Chỉ mục khóa ngoại phía con

Nếu bảng chi tiết đơn tham chiếu `order_id` nhưng không có index trên cột đó, điều gì cần xem?

**Đáp án:** trong PostgreSQL, foreign key không tự thêm index ở phía con. Với thao tác nối/xóa/cập nhật khóa cha thường xuyên, nên cân nhắc index trên cột tham chiếu hoặc composite index có tiền tố phù hợp. Không tự tạo nếu workload không cần.

### Bài 22 — Quyết định có drop index trùng tiền tố

Bảng có hai index `(tenant_id)` và `(tenant_id,status,ordered_at)`. Có nên xóa ngay index đầu?

**Đáp án:** chưa đủ thông tin. Index ghép có tiền tố tenant, nhưng index đơn có thể nhỏ hơn và phục vụ hiệu quả truy vấn chỉ lọc tenant. Đo usage, chi phí và plan trước khi drop; đồng thời xem các index đang hỗ trợ constraint nào.

### Bài 23 — Hai yêu cầu không thể gộp đơn giản

Màn hình A lọc tenant/status, lấy mới nhất; màn hình B chỉ lọc tenant, lấy mới nhất **trên mọi status**. Đề xuất:

```sql
-- Màn hình A:
(tenant_id, status, ordered_at DESC, order_id DESC)

-- Màn hình B:
(tenant_id, ordered_at DESC, order_id DESC)
```

**Đáp án:** hai index có thể phục vụ hai yêu cầu sắp xếp khác nhau. Cần cân nhắc tạo cả hai nếu lợi ích được đo đủ lớn so với chi phí ghi/lưu trữ.

### Bài 24 — Chọn index theo workload thay vì theo thói quen

Một bảng ghi rất nhiều lần mỗi giây, nhưng chỉ có một báo cáo chạy mỗi tháng lọc theo cột ít chọn lọc. Có nên tạo index mới ngay không?

**Đáp án định hướng:** chưa chắc. Đo chi phí báo cáo, tần suất thực tế, chi phí ghi, khả năng quét bảng/phân vùng và lựa chọn giải pháp khác. Chỉ tạo index nếu lợi ích tổng thể hợp lý.

## 21. Bảng ghi nhớ nhanh

| Nhu cầu | Mẫu PostgreSQL | Điểm cần nhớ |
|---|---|---|
| Tạo chỉ mục một cột | `CREATE INDEX idx ON t(col);` | Giúp một số phép tra cứu, không bảo đảm luôn được dùng |
| Tạo chỉ mục ghép | `CREATE INDEX idx ON t(a,b,c);` | **Thứ tự cột có ý nghĩa** |
| Lọc bằng rồi khoảng | `INDEX(a,b,c)` với `a=?,b=?,c>=?` | Các điều kiện bằng ở tiền tố thường thuận lợi |
| Chọn mới nhất theo tenant/status | `(tenant_id,status,ordered_at DESC,order_id DESC)` | Có thể kết hợp lọc, sắp và LIMIT |
| Chọn mới nhất theo tenant mọi status | `(tenant_id,ordered_at DESC,order_id DESC)` | Không để status chen giữa nếu cần thứ tự thời gian chung |
| UNIQUE theo cặp | `CREATE UNIQUE INDEX ... ON t(tenant_id,ref);` | Unique trên cặp, không từng cột |
| Partial index | `CREATE INDEX ... ON t(...) WHERE status='PAID';` | Chỉ bao phủ hàng thỏa predicate |
| Expression index | `CREATE INDEX ... ON t(LOWER(email));` | Phù hợp điều kiện trên biểu thức tương ứng |
| Covering | `CREATE INDEX ... ON t(keys) INCLUDE (payload);` | INCLUDE không tham gia thứ tự key |
| Xóa index | `DROP INDEX IF EXISTS idx;` | Không xóa hàng bảng |
| Tạo hạn chế chặn ghi | `CREATE INDEX CONCURRENTLY ...` | Không trong transaction block, vẫn có chi phí/chờ |
| Xóa giảm gián đoạn | `DROP INDEX CONCURRENTLY ...` | Có hạn chế, không phải zero-lock |
| Xem kế hoạch | `EXPLAIN SELECT ...` | Ước lượng; optimizer có thể chọn Seq Scan |
| Đo thực thi | `EXPLAIN (ANALYZE, BUFFERS) SELECT ...` | Thực thi thật, đặc biệt nguy hiểm với DML |
| DROP MySQL/SQL Server | `DROP INDEX idx ON table` | Khác PostgreSQL |
| DROP SQLite/Oracle | `DROP INDEX idx` | Cú pháp giống phần cơ bản, chi tiết khác |
| Quy tắc tối ưu | **Workload → index ứng viên → EXPLAIN → đo → quyết định** | Không tạo hoặc drop chỉ mục theo cảm tính |

## Kết luận

**`CREATE INDEX` và `DROP INDEX`** là hai công cụ DDL quan trọng để quản lý đường truy cập dữ liệu. Nhưng giá trị thật của chúng phụ thuộc cách ta hiểu **mẫu truy vấn và thứ tự khóa**:

- **Chỉ mục một cột** có thể tăng tốc lọc/tra cứu, nhưng bộ tối ưu vẫn có thể quét bảng khi chi phí thấp hơn.
- **Chỉ mục nhiều cột** tổ chức khóa theo thứ tự được khai báo. Tiền tố bên trái thường đóng vai trò quan trọng; các điều kiện bằng, khoảng và `ORDER BY` cần được xét cùng nhau.
- **`(tenant_id,status,ordered_at)` không tương đương `(tenant_id,ordered_at)`** cho một truy vấn sắp thời gian trên mọi status. Cùng tập cột nhưng khác thứ tự hoặc hướng sắp có thể tạo khác biệt lớn.
- **`UNIQUE`, partial index, expression index và `INCLUDE`** giải quyết những nhu cầu khác nhau: bảo vệ khóa nghiệp vụ, chỉ lưu tập con, tra cứu giá trị sau biến đổi hoặc giảm nhu cầu đọc bảng.
- **`DROP INDEX` không xóa dữ liệu**, nhưng có thể ảnh hưởng hiệu năng và không được tùy tiện gỡ index đang bảo vệ constraint.
- **`CONCURRENTLY` của PostgreSQL** giúp giảm gián đoạn một số thao tác xây/xóa index, nhưng có giới hạn và không chạy trong transaction block tường minh.
- **`EXPLAIN` và số liệu đo thực tế** quyết định một index có hữu ích hay không; không có chỉ mục nào tốt cho mọi query và mọi workload.
- **Các phương ngữ khác nhau**: PostgreSQL, MySQL, SQL Server, SQLite và Oracle có cách tạo/xóa index, tính năng bao phủ/partial/online và kế hoạch thực thi riêng.

Thói quen quan trọng nhất là **xuất phát từ truy vấn cần tối ưu, mô tả đúng tiền tố và thứ tự khóa, tạo chỉ mục có chủ đích, đo kế hoạch và cân bằng chi phí đọc–ghi trước khi giữ hay xóa nó**. Khi làm như vậy, chỉ mục trở thành một phần của thiết kế hiệu năng có thể giải thích và duy trì, thay vì một loạt lệnh DDL được thêm vào theo phỏng đoán.
