# Chỉ mục nhiều cột và vai trò thứ tự cột trong PostgreSQL

Một ứng dụng thường tìm đơn hàng theo **khách hàng**, **trạng thái** và **thời điểm tạo**. Nếu PostgreSQL chỉ có chỉ mục trên một cột, mỗi truy vấn có thể phải đọc nhiều hàng không liên quan hoặc kết hợp nhiều index trước khi lọc. Chỉ mục nhiều cột (*multicolumn index*, còn gọi *composite index*) cho phép PostgreSQL lưu nhiều giá trị khóa trong **một cấu trúc chỉ mục**, từ đó hỗ trợ tìm kiếm, kết hợp điều kiện, sắp xếp và lấy một số lượng hàng nhỏ hiệu quả hơn.

Tuy nhiên, viết:

```sql
CREATE INDEX idx_orders_tenant_status_created
ON orders (tenant_id, status, created_at DESC);
```

không có nghĩa PostgreSQL xem ba cột như một tập hợp không thứ tự. Với **B-tree**, thứ tự từ trái sang phải xác định cách các giá trị được sắp xếp trong index. Vì thế chỉ mục trên `(tenant_id, status, created_at)` và chỉ mục trên `(created_at, tenant_id, status)` có thể hỗ trợ **hai nhóm truy vấn khác nhau** và có chi phí hoàn toàn khác nhau.

Bài học này tập trung vào câu hỏi quan trọng nhất: **đặt cột nào trước, cột nào sau và vì sao?** Ta sẽ đi từ cơ chế B-tree, điều kiện bằng/range, xử lý `ORDER BY ... LIMIT`, chỉ mục covering với `INCLUDE`, index-only scan, composite uniqueness, partial/expression index, cho tới đo `EXPLAIN` và ra quyết định dựa trên workload.

## 1. Mục tiêu học tập

Sau khi học, bạn có thể:

1. Giải thích cấu trúc sắp xếp khóa theo thứ tự trong B-tree nhiều cột.
2. Hiểu vì sao **các điều kiện bằng trên tiền tố** và **điều kiện phạm vi ở cột tiếp theo** thường rất hữu ích.
3. Tránh quan niệm sai rằng PostgreSQL chỉ sử dụng một composite index khi có điều kiện trên cột đầu tiên.
4. Biết vai trò và giới hạn của **B-tree skip scan** ở những phiên bản/hình huống được hỗ trợ.
5. Phân biệt **index condition** và **filter**, đồng thời hiểu các điều kiện trên cột sau có thể vẫn được kiểm tra tại index mà không thu hẹp được phạm vi quét.
6. Thiết kế composite index cho `WHERE`, `ORDER BY`, `LIMIT`, pagination và JOIN.
7. Phân biệt khóa index với cột `INCLUDE`, hiểu yêu cầu visibility map của index-only scan.
8. Thiết kế unique constraint nhiều cột, partial index và expression index đúng ngữ nghĩa.
9. So sánh một composite index với nhiều single-column indexes và bitmap index combination.
10. Dùng `EXPLAIN (ANALYZE, BUFFERS)`, thống kê và dữ liệu đủ đại diện để kiểm chứng lựa chọn.

## 2. Chỉ mục nhiều cột là gì?

Với bảng đơn hàng:

```text
orders
  order_id
  tenant_id
  customer_id
  status
  created_at
  total_amount
```

Chỉ mục một cột:

```sql
CREATE INDEX idx_orders_tenant
ON orders (tenant_id);
```

Chỉ mục nhiều cột:

```sql
CREATE INDEX idx_orders_tenant_status_date
ON orders (tenant_id, status, created_at);
```

**B-tree nhiều cột** sắp xếp các khóa theo thứ tự từ trái sang phải:

```text
(tenant_id, status, created_at)

(1, 'paid',    2026-10-01)
(1, 'paid',    2026-10-05)
(1, 'pending', 2026-10-02)
(1, 'shipped', 2026-10-03)
(2, 'paid',    2026-10-01)
(2, 'pending', 2026-10-07)
(3, 'paid',    2026-10-08)
...
```

Sơ đồ mang tính minh họa. Thứ tự thực tế của `text` còn phụ thuộc collation, và một index khai báo `created_at DESC` sẽ sắp khác ở chiều thời gian. Điểm quan trọng là: PostgreSQL so sánh **cột đầu tiên trước**, chỉ xét cột kế tiếp để phân biệt các khóa có cột trước bằng nhau.

### 2.1. Khóa ghép không phải phép nối chuỗi

Index `(tenant_id, status)` **không** lưu một chuỗi `'1|paid'` rồi so sánh text. PostgreSQL tạo khóa B-tree từ các thuộc tính dữ liệu có kiểu và operator class/collation thích hợp. Việc dùng câu SQL để ghép text:

```sql
-- Không tương đương về ngữ nghĩa và khả năng tối ưu:
-- CREATE INDEX idx_bad
-- ON orders ((tenant_id::text || '|' || status));
```

khác với composite B-tree. Ghép chuỗi có thể gặp vấn đề delimiter, NULL, kiểu và khả năng tối ưu riêng; không nên coi nó là cách tạo khóa nhiều cột tiêu chuẩn.

### 2.2. PostgreSQL hỗ trợ nhiều phương pháp index

Các phương pháp index có ngữ nghĩa không giống nhau:

| Phương pháp | Khả năng nhiều cột và lưu ý chính |
| --- | --- |
| **B-tree** | Phổ biến nhất cho so sánh bằng, phạm vi, sắp xếp và truy vấn theo tiền tố. **Thứ tự cột đặc biệt quan trọng.** |
| **GiST** | Hỗ trợ chỉ mục nhiều cột với operator classes tương ứng; hiệu quả phụ thuộc kiểu dữ liệu/toán tử và có thể nhạy với cột đầu. |
| **GIN** | Hỗ trợ nhiều cột; phù hợp trường hợp membership/array/JSONB/full-text tùy operator class, không tuân theo quy tắc sắp xếp tiền tố như B-tree. |
| **BRIN** | Lưu thông tin tóm tắt theo khoảng trang, hợp với dữ liệu có tương quan vật lý; nhiều cột không có cơ chế prefix B-tree. |
| **Hash** | Không phải lựa chọn composite index nhiều cột tiêu chuẩn của PostgreSQL. |

Phần lớn ví dụ trong bài dùng **B-tree**, vì đó là phương pháp thường gặp trong hệ quản trị quan hệ với `WHERE tenant_id = ... AND status = ... ORDER BY created_at`. Không áp dụng máy móc quy tắc B-tree sang GIN/GiST/BRIN.

## 3. Dữ liệu thực hành: hệ thống đơn hàng nhiều tenant

Các ví dụ dưới đây dùng schema riêng, có thể chạy trong PostgreSQL test. **Không chạy DDL trên bảng production chỉ để thử bài học.**

### 3.1. Tạo schema và bảng

```sql
CREATE SCHEMA IF NOT EXISTS multicol_index_lab;

CREATE TABLE multicol_index_lab.orders (
    order_id bigint PRIMARY KEY,
    tenant_id integer NOT NULL,
    customer_id bigint NOT NULL,
    status text NOT NULL
        CHECK (status IN ('pending', 'paid', 'shipped', 'cancelled')),
    created_at timestamptz NOT NULL,
    total_amount numeric(12, 2) NOT NULL
        CHECK (total_amount >= 0),
    store_id integer NOT NULL,
    shipped_at timestamptz
);
```

`order_id` là primary key được cung cấp tường minh trong lab để các kết quả dễ đối chiếu. Hệ thống thực tế có thể sử dụng `IDENTITY`, sequence hoặc phương án tạo ID khác.

### 3.2. Chèn 24 đơn hàng

```sql
INSERT INTO multicol_index_lab.orders
    (order_id, tenant_id, customer_id, status,
     created_at, total_amount, store_id, shipped_at)
VALUES
    (101, 1, 10, 'pending',   '2026-10-01 08:00+00', 200, 1, NULL),
    (102, 1, 10, 'paid',      '2026-10-02 08:00+00', 300, 1, NULL),
    (103, 1, 11, 'paid',      '2026-10-03 08:00+00', 450, 1, NULL),
    (104, 1, 12, 'shipped',   '2026-10-04 08:00+00', 600, 2, '2026-10-05 09:00+00'),
    (105, 1, 11, 'paid',      '2026-10-05 08:00+00', 180, 1, NULL),
    (106, 1, 10, 'cancelled', '2026-10-06 08:00+00',  90, 1, NULL),
    (107, 1, 13, 'paid',      '2026-10-07 08:00+00', 320, 2, NULL),
    (108, 1, 14, 'pending',   '2026-10-08 08:00+00', 700, 2, NULL),

    (201, 2, 20, 'paid',      '2026-10-01 09:00+00', 100, 1, NULL),
    (202, 2, 21, 'pending',   '2026-10-02 09:00+00', 220, 1, NULL),
    (203, 2, 22, 'shipped',   '2026-10-03 09:00+00', 340, 2, '2026-10-04 10:00+00'),
    (204, 2, 20, 'paid',      '2026-10-04 09:00+00', 460, 2, NULL),
    (205, 2, 21, 'cancelled', '2026-10-05 09:00+00',  70, 1, NULL),
    (206, 2, 23, 'paid',      '2026-10-06 09:00+00', 520, 1, NULL),
    (207, 2, 23, 'shipped',   '2026-10-07 09:00+00', 650, 2, '2026-10-08 10:00+00'),
    (208, 2, 24, 'pending',   '2026-10-08 09:00+00', 770, 2, NULL),

    (301, 3, 30, 'pending',   '2026-10-01 10:00+00', 130, 1, NULL),
    (302, 3, 31, 'paid',      '2026-10-02 10:00+00', 260, 1, NULL),
    (303, 3, 32, 'shipped',   '2026-10-03 10:00+00', 390, 1, '2026-10-04 11:00+00'),
    (304, 3, 30, 'paid',      '2026-10-04 10:00+00', 420, 2, NULL),
    (305, 3, 33, 'pending',   '2026-10-05 10:00+00', 550, 2, NULL),
    (306, 3, 34, 'cancelled', '2026-10-06 10:00+00',  80, 1, NULL),
    (307, 3, 31, 'paid',      '2026-10-07 10:00+00', 680, 2, NULL),
    (308, 3, 35, 'shipped',   '2026-10-08 10:00+00', 810, 2, '2026-10-09 11:00+00');
```

### 3.3. Xem dữ liệu đầu vào

```sql
SELECT
    tenant_id, order_id, customer_id, status,
    created_at, total_amount
FROM multicol_index_lab.orders
ORDER BY tenant_id, created_at, order_id;
```

Mỗi tenant có tám đơn. Với tenant 1:

| order_id | status | created_at (UTC, ngày) | total_amount |
| ---: | --- | --- | ---: |
| 101 | pending | 2026-10-01 | 200 |
| 102 | paid | 2026-10-02 | 300 |
| 103 | paid | 2026-10-03 | 450 |
| 104 | shipped | 2026-10-04 | 600 |
| 105 | paid | 2026-10-05 | 180 |
| 106 | cancelled | 2026-10-06 | 90 |
| 107 | paid | 2026-10-07 | 320 |
| 108 | pending | 2026-10-08 | 700 |

`created_at` là `timestamptz`: giá trị hiển thị phụ thuộc timezone của session. Ngày UTC trong bảng minh họa không có nghĩa PostgreSQL lưu một chuỗi timezone nguyên vẹn cho từng hàng.

### 3.4. Dữ liệu nhỏ và EXPLAIN

Với chỉ **24 hàng**, PostgreSQL có thể chọn `Seq Scan` cho hầu hết câu hỏi dù đã tạo index đúng. Đó thường là quyết định chi phí hợp lý: quét vài trang heap có thể rẻ hơn traversal qua index.

Do đó ví dụ SQL dạy **ngữ nghĩa** được chạy trên dữ liệu nhỏ, còn kết luận về **hiệu năng** chỉ nên rút ra sau khi dùng dữ liệu đủ đại diện, `ANALYZE` và `EXPLAIN (ANALYZE, BUFFERS)`. Phần sau có cách tạo thêm dữ liệu lab tùy chọn.

## 4. Thứ tự lexicographic: nền tảng của composite B-tree

Giả sử tạo:

```sql
CREATE INDEX idx_lab_tenant_status_created
ON multicol_index_lab.orders
    (tenant_id, status, created_at DESC);
```

Khóa index có ba thành phần:

```text
1. tenant_id
2. status
3. created_at DESC
```

Trực giác tìm kiếm:

```text
Index (tenant_id, status, created_at DESC)

tenant=1
    status='cancelled': created_at...
    status='paid':      newest -> oldest
    status='pending':   newest -> oldest
    status='shipped':   newest -> oldest

tenant=2
    status='cancelled': created_at...
    status='paid':      newest -> oldest
    ...

tenant=3
    ...
```

Index được sắp theo tenant trước, tiếp đến status trong tenant, sau đó ngày giảm trong mỗi cặp tenant/status. **Dòng thời gian của toàn tenant bị chia thành từng khối status.**

### 4.1. Thứ tự cột ảnh hưởng mạnh tới ORDER BY

Với query:

```sql
SELECT order_id, created_at
FROM multicol_index_lab.orders
WHERE tenant_id = 1
  AND status = 'paid'
ORDER BY created_at DESC
LIMIT 10;
```

chỉ mục `(tenant_id, status, created_at DESC)` có thể hỗ trợ:

1. Chọn nhóm `tenant_id = 1`.
2. Trong nhóm ấy, chọn `status = 'paid'`.
3. Duyệt thời gian `created_at DESC`.
4. Dừng sớm sau số hàng phù hợp với `LIMIT`, nếu kế hoạch dùng index scan.

Nhưng với:

```sql
SELECT order_id, status, created_at
FROM multicol_index_lab.orders
WHERE tenant_id = 1
ORDER BY created_at DESC
LIMIT 10;
```

cùng index không cung cấp trực tiếp thứ tự `created_at DESC` **trên toàn bộ tenant**, vì các trạng thái nằm thành từng nhóm. PostgreSQL có thể cần sort hoặc chọn index khác.

### 4.2. Đổi vị trí cột là đổi nhóm truy vấn ưu tiên

Index khác:

```sql
CREATE INDEX idx_lab_tenant_created_status
ON multicol_index_lab.orders
    (tenant_id, created_at DESC, status);
```

Với index này, sau khi cố định tenant, các hàng được sắp theo thời gian mới nhất trước, không chia khối status. Nó thường phù hợp hơn với:

```sql
SELECT order_id, status, created_at
FROM multicol_index_lab.orders
WHERE tenant_id = 1
ORDER BY created_at DESC
LIMIT 10;
```

Đổi lại, với query có `tenant_id=1 AND status='paid'`, status nằm **sau cột created_at** và có thể phải quét nhiều hàng của tenant rồi kiểm tra status, đặc biệt nếu không có điều kiện thu hẹp thời gian. Sự đánh đổi nằm ở **khả năng thu hẹp phạm vi quét và thứ tự trả kết quả**, không đơn giản ở việc một index có chứa cột hay không.

## 5. Quy tắc thực dụng: equality, rồi range

Với B-tree nhiều cột, tình huống thường hiệu quả là:

```sql
-- Đã tạo ở phần 4; IF NOT EXISTS giúp chạy lại riêng ví dụ trong lab.
CREATE INDEX IF NOT EXISTS idx_lab_tenant_status_created
ON multicol_index_lab.orders
    (tenant_id, status, created_at DESC);
```

Truy vấn:

```sql
SELECT order_id, total_amount, created_at
FROM multicol_index_lab.orders
WHERE tenant_id = 1
  AND status = 'paid'
  AND created_at >= TIMESTAMPTZ '2026-10-03 00:00+00'
ORDER BY created_at DESC;
```

Phân tích:

| Cột theo thứ tự index | Predicate | Vai trò |
| --- | --- | --- |
| `tenant_id` | `= 1` | Điều kiện bằng trên cột đầu: chọn đoạn khóa theo tenant. |
| `status` | `= 'paid'` | Điều kiện bằng tiếp theo: chọn đoạn theo status trong tenant. |
| `created_at` | `>= cutoff` | Điều kiện phạm vi trên cột tiếp: giới hạn phần thời gian cần quét. |

Nhờ các điều kiện bằng ở tiền tố, B-tree có thể tìm nhanh đoạn index tương ứng `(tenant=1, status='paid')`, sau đó áp điều kiện phạm vi thời gian trong đoạn ấy.

### 5.1. Equality/range không phải luật bắt buộc cứng

Không nên biến quy tắc trên thành câu sai:

> “Chỉ mục B-tree nhiều cột chỉ có ích khi query lọc cột đầu, và mọi điều kiện sau range đều bị bỏ qua.”

Thực tế PostgreSQL:

- Có thể đánh giá các điều kiện trên các cột index **ở phía sau**, dù chúng không làm hẹp span index tuần tự theo cách tiền tố bằng.
- Có thể chọn **skip scan** ở một số phiên bản/hình huống có lợi.
- Có thể dùng **bitmap index scan**, kết hợp nhiều index, hoặc chỉ dùng index để cung cấp thứ tự.
- Có thể quyết định không dùng index nếu thống kê và chi phí cho thấy quét bảng rẻ hơn.

Quy tắc “equality trước range” là **heuristic để thiết kế một B-tree key order**, không phải sự mô tả mọi plan có thể có.

### 5.2. Khi có nhiều cột equality

Với:

```sql
WHERE tenant_id = 1
  AND status = 'paid'
```

cả index `(tenant_id, status)` và `(status, tenant_id)` có thể thu hẹp hiệu quả xuống cặp giá trị chính xác. **Không có quy tắc tổng quát rằng phải luôn đặt cột có selectivity cao hơn trước** khi tất cả cột đều có phép so sánh bằng.

Thứ tự nên xét:

- Truy vấn nào chỉ lọc **một trong hai** cột?
- Có `ORDER BY` hoặc range sau những cột bằng không?
- Có yêu cầu cô lập tenant trong mọi query không?
- Số lượng giá trị phân biệt, phân bố và tương quan thực tế là gì?
- Có thể tái sử dụng cùng index cho nhiều query quan trọng không?

Nếu các query thường có `tenant_id=?` nhưng hiếm khi có `status` một mình, đưa tenant lên đầu có thể phục vụ workload tốt hơn. Nếu truy vấn toàn hệ thống chủ yếu lọc trạng thái và thời gian, thứ tự khác có thể hợp lý.

## 6. Vì sao “leftmost prefix rule” cần hiểu cho đúng?

Trong nhiều tài liệu nhập môn, quy tắc tiền tố trái được diễn giải:

```text
Index (a,b,c) tốt nhất cho:
  a
  a,b
  a,b,c
```

Ý này hữu ích như điểm khởi đầu, nhưng dễ dẫn đến kết luận quá mạnh rằng `WHERE b=?` **không bao giờ** dùng được index `(a,b,c)`. PostgreSQL có thể thực thi các đường đi khác nhau nếu cost model thấy đáng giá.

### 6.1. Ví dụ có cột đầu tiên

```sql
SELECT order_id, status
FROM multicol_index_lab.orders
WHERE tenant_id = 2
ORDER BY status;
```

Index `(tenant_id, status, created_at DESC)` phù hợp với việc lấy nhóm tenant và thứ tự theo status.

### 6.2. Ví dụ không có cột đầu tiên

```sql
SELECT order_id, tenant_id, created_at
FROM multicol_index_lab.orders
WHERE status = 'paid';
```

Với index `(tenant_id, status, created_at DESC)`, PostgreSQL không có một đoạn liên tục duy nhất chứa tất cả `status='paid'` trên mọi tenant. Tuy vậy, index vẫn **có thể** được chọn trong một số plan, chẳng hạn khi các khóa khác rẻ để quét hoặc skip scan khả thi. Nhưng điều đó không có nghĩa index này lý tưởng cho truy vấn status-only.

Nếu ứng dụng truy vấn status-only rất thường xuyên, có thể cần:

```sql
CREATE INDEX idx_lab_status_created
ON multicol_index_lab.orders
    (status, created_at DESC);
```

Mỗi index thêm đều tốn storage và chi phí ghi; không nên tạo tất cả biến thể chỉ vì mỗi WHERE có một tổ hợp khác.

### 6.3. Điều kiện trên cột cuối không tự tạo vùng quét nhỏ

Ví dụ:

```sql
SELECT order_id, tenant_id, status
FROM multicol_index_lab.orders
WHERE created_at >= TIMESTAMPTZ '2026-10-07 00:00+00';
```

Trong index `(tenant_id, status, created_at DESC)`, những giá trị created_at gần đây nằm rải qua từng cặp tenant/status. Để tìm chỉ các ngày mới, PostgreSQL có thể thấy index `(created_at)` hoặc `(created_at DESC, tenant_id)` phù hợp hơn, tùy selectivity và query.

Không có nghĩa PostgreSQL hoàn toàn không đọc được cột cuối. Nhưng **khả năng đọc được điều kiện** khác với **khả năng giới hạn chính xác vùng index cần đi qua**.

## 7. B-tree skip scan: ngoại lệ hữu ích của quy tắc tiền tố

Ở những phiên bản PostgreSQL hỗ trợ B-tree skip scan, planner có thể tận dụng một chỉ mục nhiều cột dù query **thiếu điều kiện bằng trên cột đầu**, bằng cách thực hiện những lượt tìm kiếm tương ứng với các giá trị có thể có của cột đầu.

Giả sử có index:

```sql
CREATE INDEX idx_lab_store_customer
ON multicol_index_lab.orders (store_id, customer_id);
```

Query:

```sql
SELECT order_id, store_id, customer_id
FROM multicol_index_lab.orders
WHERE customer_id = 10;
```

Nếu `store_id` chỉ có rất ít giá trị phân biệt, planner có thể thấy có lợi khi tìm:

```text
(store_id = 1, customer_id = 10)
(store_id = 2, customer_id = 10)
...
```

thay vì quét mọi leaf entry. Ý tưởng là tạo ra các ranh giới tìm kiếm theo cột đầu còn thiếu để tận dụng điều kiện trên cột sau.

### 7.1. Khi skip scan có thể có lợi?

- Cột dẫn đầu có **ít giá trị phân biệt**.
- Predicate trên cột sau đủ chọn lọc.
- Chi phí nhiều lượt index search thấp hơn quét rộng/seq scan.
- Phiên bản PostgreSQL và access method/optimizer hỗ trợ phương án đó.

Nếu cột đầu có hàng triệu giá trị khác nhau, thực hiện tìm kiếm cho quá nhiều khả năng có thể rất tốn kém. Planner có thể chọn scan khác.

### 7.2. Không thiết kế toàn bộ chiến lược dựa vào skip scan

Đây là một khả năng tối ưu **phụ thuộc phiên bản và cost**, không phải hợp đồng rằng index `(a,b)` luôn thay thế tốt index `(b)` cho `WHERE b=?`.

Khi làm việc với PostgreSQL phiên bản cụ thể:

1. Kiểm tra tài liệu chính thức của major đang chạy.
2. Quan sát plan thực bằng `EXPLAIN`.
3. Dùng dữ liệu có cardinality phù hợp thực tế.
4. Nếu truy vấn b-only là hot path, cân nhắc một index phù hợp hơn thay vì mặc định skip scan sẽ cứu.

## 8. Equality ở trước, range ở giữa, equality ở cuối

Xét một index:

```sql
CREATE INDEX idx_lab_tenant_time_status
ON multicol_index_lab.orders
    (tenant_id, created_at DESC, status);
```

Truy vấn:

```sql
SELECT order_id, created_at, status
FROM multicol_index_lab.orders
WHERE tenant_id = 1
  AND created_at >= TIMESTAMPTZ '2026-10-01 00:00+00'
  AND status = 'paid';
```

Với index này:

1. `tenant_id=1` xác định một vùng.
2. `created_at >= ...` chọn một đoạn thời gian bên trong tenant.
3. `status='paid'` vẫn có thể được kiểm tra tại index, nhưng thông thường không giúp thu hẹp đoạn thời gian đã xác định giống như khi status đứng trước created_at.

Vì thế nếu tenant có 100 triệu đơn và predicate thời gian bao trùm nhiều năm nhưng chỉ một tỷ lệ nhỏ đơn là paid, index `(tenant_id,status,created_at)` có thể tốt hơn đáng kể cho truy vấn cụ thể này.

Ngược lại, nếu luôn lấy **20 đơn gần nhất của tenant bất kể status**:

```sql
SELECT order_id, status, created_at
FROM multicol_index_lab.orders
WHERE tenant_id = 1
ORDER BY created_at DESC, order_id DESC
LIMIT 20;
```

thì index `(tenant_id,created_at DESC,order_id DESC)` thường đáng cân nhắc hơn.

**Không thể chọn thứ tự cột chỉ bằng nhìn một WHERE.** Phải xét cả điều kiện range, sort, limit và tần suất truy vấn.

## 9. Phép so sánh bằng, IN, BETWEEN và biểu thức

### 9.1. Equality

```sql
WHERE tenant_id = 1
  AND status = 'paid'
```

Hai điều kiện bằng thường tạo tiền tố tốt trên index `(tenant_id,status,created_at)`.

### 9.2. IN

```sql
WHERE tenant_id = 1
  AND status IN ('paid', 'shipped')
```

`IN` là tập nhiều giá trị, không đơn thuần một equality duy nhất theo nghĩa một vùng liên tục. PostgreSQL có thể xử lý bằng các index probes, scalar-array operator hoặc plan khác. Kết quả đọc có thể gồm **nhiều nhóm status**, không được đảm bảo sắp theo thời gian toàn cục chỉ vì mỗi nhóm status sắp thời gian.

Ví dụ:

```sql
SELECT order_id, status, created_at
FROM multicol_index_lab.orders
WHERE tenant_id = 1
  AND status IN ('paid', 'shipped')
ORDER BY created_at DESC
LIMIT 10;
```

Với index `(tenant_id,status,created_at DESC)`, PostgreSQL có thể cần thêm sort/merge logic để bảo đảm `ORDER BY created_at DESC` trên cả hai status. Không suy luận “status có IN nên đã giống equality và sort tự được đáp ứng”.

### 9.3. BETWEEN và phạm vi nửa mở

```sql
WHERE tenant_id = 1
  AND created_at >= TIMESTAMPTZ '2026-10-01 00:00+00'
  AND created_at <  TIMESTAMPTZ '2026-11-01 00:00+00'
```

Với timestamp, khoảng `[start,end)` thường thuận tiện hơn `BETWEEN` hai đầu đóng khi lọc một ngày/tháng. `BETWEEN` không sai, nhưng người mới dễ tạo sai ranh giới `23:59:59` khi dữ liệu có phần microsecond.

Index `(tenant_id,created_at)` có thể tìm đoạn thời gian của một tenant tốt theo mẫu này.

### 9.4. Biểu thức trên cột index

Giả sử query dùng:

```sql
WHERE tenant_id = 1
  AND created_at::date = DATE '2026-10-07'
```

Việc cast cột `created_at` thành ngày không tương đương điều kiện range trực tiếp đối với planner/index B-tree thông thường. Ngoài ra `created_at::date` trên `timestamptz` còn phụ thuộc timezone session.

Với trường hợp cần ngày UTC, dùng ranh giới rõ:

```sql
WHERE tenant_id = 1
  AND created_at >= TIMESTAMPTZ '2026-10-07 00:00+00'
  AND created_at <  TIMESTAMPTZ '2026-10-08 00:00+00'
```

Điều kiện trên cột gốc thường dễ tận dụng B-tree `(tenant_id,created_at)` hơn. Nếu workload cần tra cứu theo biểu thức cụ thể, có thể thiết kế expression index tương ứng khi biểu thức đáp ứng yêu cầu PostgreSQL.

## 10. Thứ tự cột cho ORDER BY và LIMIT

B-tree không chỉ giúp lọc: nó còn lưu khóa theo thứ tự. Khi chỉ mục có thể cung cấp đúng thứ tự đầu ra, PostgreSQL có thể tránh hoặc giảm thao tác Sort.

### 10.1. Lịch sử đơn mới nhất của một tenant

```sql
CREATE INDEX idx_lab_tenant_created_order
ON multicol_index_lab.orders
    (tenant_id, created_at DESC, order_id DESC);
```

Truy vấn:

```sql
SELECT order_id, status, created_at
FROM multicol_index_lab.orders
WHERE tenant_id = 2
ORDER BY created_at DESC, order_id DESC
LIMIT 5;
```

Ở đây:

- `tenant_id=2` cố định cột đầu.
- `created_at DESC` và `order_id DESC` phù hợp thứ tự index còn lại.
- `LIMIT 5` mở khả năng dừng sớm sau khi tìm đủ hàng, nếu planner chọn index scan và các điều kiện khác không đòi xét thêm quá nhiều hàng.

`order_id` là khóa phụ giúp kết quả **ổn định** khi có hai đơn cùng `created_at`. Nếu chỉ `ORDER BY created_at DESC`, thứ tự giữa hai hàng trùng timestamp không được định nghĩa.

### 10.2. Có thể dùng quét ngược trên B-tree

Một B-tree:

```sql
CREATE INDEX idx_lab_tenant_created_asc
ON multicol_index_lab.orders
    (tenant_id ASC, created_at ASC);
```

có thể được quét xuôi hoặc ngược. Khi **tenant đã được cố định bởi equality**, truy vấn `ORDER BY created_at DESC` có thể dùng scan ngược trên đoạn tenant tương ứng. Vì vậy không phải luôn tạo thêm index DESC chỉ để đảo chiều một cột.

Tuy nhiên nếu query đòi thứ tự **hỗn hợp** trên nhiều cột mà cả hai không cố định:

```sql
ORDER BY tenant_id ASC, created_at DESC
```

thì index `(tenant_id ASC, created_at DESC)` có thể cung cấp thứ tự đó trực tiếp; scan ngược `(tenant_id ASC,created_at ASC)` tạo chiều đảo cho **cả hai cột**, chứ không độc lập đảo một cột.

### 10.3. Thứ tự mixed ASC/DESC

```sql
CREATE INDEX idx_lab_mixed_sort
ON multicol_index_lab.orders
    (tenant_id ASC, created_at DESC, order_id DESC);
```

Hỗ trợ một hướng sắp xếp:

```sql
SELECT tenant_id, created_at, order_id
FROM multicol_index_lab.orders
ORDER BY tenant_id ASC, created_at DESC, order_id DESC;
```

Quét ngược toàn bộ index có thể cung cấp thứ tự đảo của tất cả thành phần, có tính đến NULL ordering đã khai báo.

Nếu query yêu cầu `tenant_id DESC, created_at DESC` trên tất cả tenant, index hỗn hợp này **không tự** cung cấp thứ tự đó qua một lượt quét ngược duy nhất.

### 10.4. NULLS FIRST / NULLS LAST

Với B-tree PostgreSQL, những quy tắc thường gặp:

- `ASC` mặc định đi cùng `NULLS LAST`.
- `DESC` mặc định đi cùng `NULLS FIRST`.
- Scan ngược đảo cả chiều khóa và cách NULL được đặt.

Ví dụ bảng có `shipped_at` nullable:

```sql
CREATE INDEX idx_lab_tenant_shipped_nulls_last
ON multicol_index_lab.orders
    (tenant_id ASC, shipped_at DESC NULLS LAST);
```

Query:

```sql
SELECT order_id, tenant_id, shipped_at
FROM multicol_index_lab.orders
WHERE tenant_id = 2
ORDER BY shipped_at DESC NULLS LAST
LIMIT 10;
```

Không thể tự cho rằng một index `DESC` mặc định sẽ đúng yêu cầu `DESC NULLS LAST`. Với cột khóa có NULL, khai báo thứ tự cần thiết cho workload.

## 11. Vì sao cột bị “kẹt” giữa WHERE và ORDER BY?

Xét index:

```sql
-- Chỉ mục đã có từ phần 4; nhắc lại định nghĩa để đối chiếu.
CREATE INDEX IF NOT EXISTS idx_lab_tenant_status_created
ON multicol_index_lab.orders
    (tenant_id, status, created_at DESC);
```

Query 1:

```sql
SELECT order_id, status, created_at
FROM multicol_index_lab.orders
WHERE tenant_id = 1
  AND status = 'paid'
ORDER BY created_at DESC;
```

Trong cặp `(tenant_id,status)` cố định, created_at có thứ tự DESC hữu ích.

Query 2:

```sql
SELECT order_id, status, created_at
FROM multicol_index_lab.orders
WHERE tenant_id = 1
ORDER BY created_at DESC;
```

Status không được cố định. Các hàng trong tenant được xếp thành nhiều nhóm status, và mỗi nhóm có thời gian DESC riêng. **Gộp các nhóm ấy lại không mặc nhiên là thời gian DESC toàn tenant.**

### 11.1. Bài học thiết kế

Nếu màn hình phổ biến nhất là “danh sách đơn mới nhất của tenant”, nên ưu tiên một index kiểu:

```sql
(tenant_id, created_at DESC, order_id DESC)
```

Nếu màn hình phổ biến nhất là “danh sách đơn đã thanh toán mới nhất của tenant”, index kiểu:

```sql
(tenant_id, status, created_at DESC, order_id DESC)
```

có thể phù hợp hơn.

Nếu **cả hai** truy vấn đều rất quan trọng và có volume lớn, có thể cần hai index với chi phí tương ứng. Đây là lựa chọn từ workload, không phải một quy tắc SQL tuyệt đối.

## 12. Pagination theo khóa và composite index

Với lượng đơn lớn, `OFFSET` tăng dần khiến database thường phải đi qua nhiều hàng trước khi lấy trang sau:

```sql
SELECT order_id, created_at
FROM multicol_index_lab.orders
WHERE tenant_id = 1
ORDER BY created_at DESC, order_id DESC
LIMIT 20 OFFSET 200000;
```

Một hướng thường tốt hơn cho luồng đọc liên tục theo thời gian là **keyset pagination** (seek pagination).

### 12.1. Trang đầu

```sql
SELECT order_id, created_at, status
FROM multicol_index_lab.orders
WHERE tenant_id = 1
ORDER BY created_at DESC, order_id DESC
LIMIT 20;
```

Ghi lại `(created_at, order_id)` của hàng cuối làm cursor.

### 12.2. Trang tiếp theo

Giả sử hàng cuối có ngày và ID:

```sql
SELECT order_id, created_at, status
FROM multicol_index_lab.orders
WHERE tenant_id = 1
  AND (created_at, order_id) <
      (TIMESTAMPTZ '2026-10-04 08:00+00', 104)
ORDER BY created_at DESC, order_id DESC
LIMIT 20;
```

Với thứ tự DESC cho cả created_at và order_id, phép so sánh tuple `<` chọn các khóa nằm **sau cursor trong trật tự giảm dần**. Index `(tenant_id, created_at DESC, order_id DESC)` có thể hỗ trợ tốt kiểu truy vấn này.

Điều kiện cần:

- Cặp khóa đủ để tạo thứ tự **đơn trị**, ví dụ order_id là unique.
- Các cột cursor cần được xử lý rõ nếu có NULL; lab đặt created_at NOT NULL.
- Query page sau phải dùng cùng bộ lọc và cùng thứ tự.
- Dữ liệu có thể thay đổi giữa các trang. Keyset giúp tránh chi phí OFFSET lớn, nhưng không tự cung cấp snapshot nhất quán xuyên nhiều HTTP requests.

### 12.3. Vì sao order_id nên ở cuối?

Nếu hai đơn có cùng `created_at` và ORDER BY chỉ có ngày, cursor không biết phân biệt chúng. Khóa phụ `order_id` giải quyết ties.

Đặt `order_id DESC` sau `created_at DESC` trong index làm index có thể phục vụ cả so sánh tuple và sắp xếp theo hai thành phần. Đặt order_id trước created_at sẽ thay đổi thứ tự vật lý và không còn phù hợp với query muốn thời gian là thành phần chính.

## 13. Composite index và truy vấn JOIN

Giả sử bảng đơn hàng có `tenant_id` và `customer_id`. Một ứng dụng thường lấy đơn của một khách bên trong một tenant:

```sql
SELECT order_id, created_at, total_amount
FROM multicol_index_lab.orders
WHERE tenant_id = 1
  AND customer_id = 10
ORDER BY created_at DESC, order_id DESC;
```

Index cân nhắc:

```sql
CREATE INDEX idx_lab_tenant_customer_created
ON multicol_index_lab.orders
    (tenant_id, customer_id, created_at DESC, order_id DESC);
```

Nó phù hợp với access pattern:

```text
tenant_id = ?
    customer_id = ?
        created_at DESC
            order_id DESC
```

### 13.1. Khi join từ bảng customers

Giả sử có bảng `customers` chứa `(tenant_id, customer_id)`:

```sql
CREATE TABLE multicol_index_lab.customers (
    tenant_id integer NOT NULL,
    customer_id bigint NOT NULL,
    display_name text NOT NULL,
    PRIMARY KEY (tenant_id, customer_id)
);

INSERT INTO multicol_index_lab.customers
    (tenant_id, customer_id, display_name)
VALUES
    (1, 10, 'Khách A'),
    (1, 11, 'Khách B'),
    (2, 20, 'Khách C');
```

Truy vấn JOIN:

```sql
SELECT
    c.display_name,
    o.order_id,
    o.created_at
FROM multicol_index_lab.customers AS c
JOIN multicol_index_lab.orders AS o
    ON o.tenant_id = c.tenant_id
   AND o.customer_id = c.customer_id
WHERE c.tenant_id = 1
  AND c.customer_id = 10
ORDER BY o.created_at DESC, o.order_id DESC;
```

Một phương án có thể là nested-loop join truy cập `orders` qua index `(tenant_id,customer_id,created_at DESC,order_id DESC)`. Nhưng PostgreSQL cũng có thể chọn hash/merge join hoặc seq scan khi số hàng ít hoặc join có tính chọn lọc khác.

### 13.2. Chỉ mục phía bảng tham chiếu

Primary key `customers(tenant_id,customer_id)` tự có unique B-tree index phù hợp. Trong khi đó, nếu `orders` có foreign key tham chiếu `customers`, PostgreSQL **không tự động tạo mọi index cần thiết ở bảng con chỉ vì có foreign key**.

Index `(tenant_id,customer_id)` hoặc composite mở rộng có thể hữu ích cho query JOIN và thao tác xóa/cập nhật khóa ở bảng cha, tùy workload.

### 13.3. Chỉ mục trên JOIN không tự bảo đảm dùng được cho mọi join

Ví dụ một query lấy tất cả khách và mọi đơn, không lọc tenant/customer, có thể chọn hash join và seq scan. Chỉ mục tốt cho lookup chọn lọc không nhất thiết tốt cho quét toàn bảng.

## 14. Composite UNIQUE: thứ tự index và tính duy nhất

Chỉ mục nhiều cột không chỉ để tăng tốc; nó còn thực thi quy tắc dữ liệu:

> Một mã đơn ngoài hệ thống chỉ cần duy nhất **trong từng tenant**, không cần duy nhất trên toàn nền tảng.

Ví dụ tạo bảng độc lập:

```sql
CREATE TABLE multicol_index_lab.external_orders (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id integer NOT NULL,
    external_order_no text NOT NULL,
    amount numeric(12, 2) NOT NULL,
    CONSTRAINT uq_external_orders_tenant_no
        UNIQUE (tenant_id, external_order_no)
);
```

Hai hàng có cùng external_order_no nhưng tenant khác nhau là hợp lệ:

```sql
INSERT INTO multicol_index_lab.external_orders
    (tenant_id, external_order_no, amount)
VALUES
    (1, 'INV-001', 200.00),
    (2, 'INV-001', 400.00);
```

Chèn lại cùng cặp `(tenant_id=1, external_order_no='INV-001')` sẽ vi phạm unique constraint.

### 14.1. Khác nhau giữa uniqueness và hiệu quả query

Về **ràng buộc tính duy nhất của cả cặp**, `UNIQUE(tenant_id,external_order_no)` và `UNIQUE(external_order_no,tenant_id)` đều cấm trùng cùng cặp (khi tính tới cùng NULL semantics).

Nhưng hai thứ tự phục vụ truy vấn khác nhau:

- `(tenant_id,external_order_no)` hợp với lookup/list theo tenant.
- `(external_order_no,tenant_id)` hợp với lookup theo mã ngoài trên toàn hệ thống.

Không thay đổi thứ tự composite unique chỉ vì nghĩ cột “được nhập trước” quan trọng hơn. Hãy xét cả ngữ nghĩa ràng buộc **và đường truy vấn phổ biến**.

### 14.2. NULL trong unique nhiều cột

Theo mặc định, PostgreSQL coi NULL là không bằng NULL cho mục đích unique constraint thông thường; nếu thành phần khóa có NULL, nhiều hàng có thể cùng những giá trị non-NULL và NULL tương ứng mà không bị coi là trùng.

Trong lab, `external_order_no NOT NULL` nên không có tình huống này. Với cột nullable, từ PostgreSQL 15 có cú pháp **`UNIQUE NULLS NOT DISTINCT`** để yêu cầu NULL được đối xử như không phân biệt nhau cho uniqueness:

```sql
-- PostgreSQL 15+; ví dụ schema riêng:
CREATE TABLE multicol_index_lab.optional_codes (
    tenant_id integer NOT NULL,
    optional_code text,
    UNIQUE NULLS NOT DISTINCT (tenant_id, optional_code)
);
```

Với ràng buộc đó, hai hàng có cùng tenant_id và optional_code NULL sẽ bị coi là trùng. **Đừng dùng cú pháp này trên PostgreSQL major cũ không hỗ trợ.**

## 15. INCLUDE: cột trả về không nhất thiết cần là cột khóa

Giả sử hot query:

```sql
SELECT
    order_id,
    created_at,
    total_amount
FROM multicol_index_lab.orders
WHERE tenant_id = 1
  AND status = 'paid'
ORDER BY created_at DESC, order_id DESC
LIMIT 10;
```

Một index có thể được thiết kế:

```sql
CREATE INDEX idx_lab_paid_order_cover
ON multicol_index_lab.orders
    (tenant_id, status, created_at DESC, order_id DESC)
INCLUDE (total_amount);
```

Các cột trong phần `(...)` chính là **key columns**. Cột sau `INCLUDE` là **payload/non-key column**:

| Thành phần | Vai trò |
| --- | --- |
| `tenant_id` | Key: lọc tenant. |
| `status` | Key: lọc status. |
| `created_at DESC` | Key: lọc/sắp theo thời gian. |
| `order_id DESC` | Key: phá hòa, hỗ trợ order/lookup. |
| `total_amount` | INCLUDE: hỗ trợ trả kết quả mà không nhất thiết đọc heap để lấy cột này. |

### 15.1. INCLUDE không trở thành điều kiện dẫn đường

Nếu một index là:

```sql
CREATE INDEX idx_lab_tenant_time_includes
ON multicol_index_lab.orders
    (tenant_id, created_at DESC)
INCLUDE (status, total_amount);
```

thì query `WHERE status='paid'` **không có nghĩa status trở thành phần khóa thứ ba** có thể thu hẹp phạm vi index như `(tenant_id,created_at,status)`. INCLUDE không tham gia thứ tự B-tree hoặc tìm kiếm qua key comparisons.

PostgreSQL có thể đánh giá một số thông tin từ index trong phương án index-only phù hợp, nhưng việc mang cột vào INCLUDE khác với biến nó thành key được sắp.

### 15.2. Index-only scan cần điều kiện bổ sung

Một index chứa đủ các cột query cần **không bảo đảm** PostgreSQL chắc chắn dùng `Index Only Scan`:

- Các cột cần đọc phải có sẵn từ index theo khả năng của access method.
- PostgreSQL vẫn phải kiểm tra MVCC visibility; visibility map cho biết trang heap có toàn-visible hay chưa.
- Nếu trang chưa all-visible, PostgreSQL vẫn có thể cần đọc heap để xác minh.
- Planner có thể thấy seq scan/index scan thông thường rẻ hơn.

Thực hành:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT order_id, created_at, total_amount
FROM multicol_index_lab.orders
WHERE tenant_id = 1
  AND status = 'paid'
ORDER BY created_at DESC, order_id DESC
LIMIT 10;
```

Nếu plan có `Index Only Scan`, xem thêm `Heap Fetches`. Trên bảng nhỏ hoặc mới ghi/UPDATE, nó có thể vẫn phải fetch heap.

### 15.3. Chi phí INCLUDE

Thêm payload làm index to hơn, tăng I/O/chi phí ghi, có thể giảm fanout hoặc ảnh hưởng HOT update khi dữ liệu index thay đổi. Không “INCLUDE mọi cột SELECT” một cách máy móc, đặc biệt với text/JSONB lớn và các cột thay đổi thường xuyên.

PostgreSQL còn có giới hạn kích thước index tuple; thêm payload quá lớn có thể làm `CREATE INDEX` hoặc `INSERT/UPDATE` gặp lỗi. Chỉ thêm cột có lợi ích đo được.

## 16. Một composite index có thay được single-column index không?

Giả sử đang có:

```sql
CREATE INDEX idx_lab_tenant_only
ON multicol_index_lab.orders (tenant_id);

CREATE INDEX idx_lab_tenant_status
ON multicol_index_lab.orders (tenant_id, status);
```

Với B-tree, index thứ hai thường có thể phục vụ truy vấn chỉ lọc `tenant_id`:

```sql
SELECT COUNT(*)
FROM multicol_index_lab.orders
WHERE tenant_id = 2;
```

Về mặt khả năng truy cập dữ liệu, đây là lý do một index trên **tiền tố cột** đôi khi bị coi là dư thừa so với index ghép dài hơn.

Tuy nhiên **không nên xóa ngay index (tenant_id)** chỉ vì tồn tại index (tenant_id,status):

- Index một cột thường **nhỏ hơn**, có thể đọc nhanh hơn cho những query chỉ cần tenant.
- Index lớn hơn có thể gây nhiều cache misses hoặc ghi đĩa hơn.
- Một index có unique, partial predicate, expression, collation hoặc sort order khác không phải lúc nào cũng thay được index kia về tất cả ngữ nghĩa.
- Tần suất query tenant-only có thể lớn hơn rất nhiều so với tenant+status.
- Planner có thể chọn đường đi khác theo dữ liệu thực.

### 16.1. Tư duy đúng về index dư thừa

Hãy so sánh:

1. Mục đích của từng index (SELECT, JOIN, FK checks, uniqueness, ORDER BY).
2. Khóa và thứ tự cột.
3. `WHERE` của partial index, các expression, collations/operator classes.
4. Kích thước vật lý và chi phí duy trì.
5. Thống kê tần suất dùng và hot queries có thể bị ảnh hưởng.
6. Kế hoạch rollback nếu xóa index làm latency tăng.

Tối ưu index là tối ưu **tổng workload đọc/ghi**, không phải trò chơi có ít index nhất hay nhiều index nhất.

### 16.2. Index (a,b) khác hai index (a) và (b)

Với:

```sql
WHERE tenant_id = 1
  AND status = 'paid'
```

PostgreSQL có thể:

- Sử dụng index `(tenant_id,status)` để đến trực tiếp vùng khóa phù hợp.
- Sử dụng riêng index `(tenant_id)` rồi lọc status.
- Sử dụng riêng index `(status)` rồi lọc tenant.
- Kết hợp bitmap từ các index riêng trên hai cột.
- Chọn sequential scan.

Hai index riêng **không trở thành** một composite index có cùng thứ tự lexicographic. Đặc biệt, bitmap kết hợp từ hai index thường không tự bảo toàn thứ tự `ORDER BY` cần thiết cho top-N.

## 17. Bitmap Index Scan: kết hợp chỉ mục, nhưng mất thứ tự

Giả sử có hai index:

```sql
CREATE INDEX idx_lab_tenant_bitmap
ON multicol_index_lab.orders (tenant_id);

CREATE INDEX idx_lab_status_bitmap
ON multicol_index_lab.orders (status);
```

Một kế hoạch có thể là:

```text
Bitmap Heap Scan on orders
  Recheck Cond: ...
  -> BitmapAnd
       -> Bitmap Index Scan on idx_lab_tenant_bitmap
       -> Bitmap Index Scan on idx_lab_status_bitmap
```

Đây là **sơ đồ plan minh họa**, không phải kết quả được bảo đảm từ bảng 24 hàng của bài. Trên dữ liệu nhỏ, PostgreSQL có thể dùng seq scan.

### 17.1. Vì sao có Bitmap Heap Scan?

Mỗi index xác định những vị trí heap có thể chứa hàng phù hợp. PostgreSQL có thể kết hợp bitmap với `BitmapAnd` hoặc `BitmapOr`, sau đó đọc heap pages theo cách phù hợp để kiểm tra/thu thập hàng.

Ưu điểm là có thể tận dụng nhiều index đơn có sẵn. Nhược điểm liên quan thứ tự:

- Bitmap heap scan trả hàng theo hành vi quét trang heap, **không duy trì thứ tự khóa B-tree** theo cách index scan có thể làm.
- Nếu truy vấn yêu cầu `ORDER BY created_at DESC LIMIT 20`, có thể cần Sort/Top-N sort.
- Một composite B-tree phù hợp cả filter và order thường có lợi thế cho hot query cần top-N nhanh.

### 17.2. Bitmap có thể tốt hơn composite không?

Có. Nếu các predicate thay đổi linh hoạt, người dùng có hàng chục tổ hợp filter, việc tạo một composite index cho **mọi hoán vị** không khả thi. Một số index đơn/chỉ mục theo các tổ hợp quan trọng có thể giúp planner chọn phương án bitmap hữu ích.

Không kết luận composite **luôn** nhanh hơn: selectivity, số hàng, số trang heap, clustering dữ liệu, RAM và cache có thể làm khác kết quả.

### 17.3. Index path còn có Index Scan và Index Only Scan

| Plan node | Đặc điểm điển hình |
| --- | --- |
| `Index Scan` | Dùng index để lấy TID và thường đọc heap row; có thể duy trì key order thích hợp. |
| `Index Only Scan` | Cột query có trong index, nhưng vẫn phải xác minh visibility; có thể cần heap fetch. |
| `Bitmap Index Scan` + `Bitmap Heap Scan` | Tập hợp row positions và đọc heap theo bitmap; không tự giữ thứ tự key của index. |
| `Seq Scan` | Quét bảng; có thể tốt nếu phần lớn hàng cần đọc hoặc bảng nhỏ. |

Đừng mặc định nhìn thấy chữ `Index` trong plan là tối ưu. Phải đo số hàng, buffers, thời gian và chi phí cho workload thực tế.

## 18. Partial composite index: chỉ đánh chỉ mục một phần bảng

Nếu màn hình hot path chỉ truy cập các đơn `status='pending'`, index toàn bộ mọi trạng thái có thể quá lớn so với nhu cầu.

PostgreSQL hỗ trợ partial index:

```sql
CREATE INDEX idx_lab_pending_tenant_created
ON multicol_index_lab.orders
    (tenant_id, created_at DESC, order_id DESC)
WHERE status = 'pending';
```

Ý nghĩa:

- Chỉ các hàng thỏa `status='pending'` được đưa vào index theo điều kiện predicate.
- Trong tập này, keys được sắp theo `tenant_id`, `created_at DESC`, `order_id DESC`.
- Cột `status` **không cần nằm trong key** nếu index chỉ gồm các hàng pending và query đã chứng minh predicate ấy.

Truy vấn mục tiêu:

```sql
SELECT order_id, created_at
FROM multicol_index_lab.orders
WHERE tenant_id = 1
  AND status = 'pending'
ORDER BY created_at DESC, order_id DESC
LIMIT 20;
```

### 18.1. Predicate phải được planner nhận ra

Một partial index chỉ hữu ích khi PostgreSQL có thể chứng minh **predicate của query kéo theo predicate của index** trong ngữ cảnh plan.

Truy vấn:

```sql
WHERE tenant_id = 1
  AND status = 'paid'
```

không thể dùng partial index chỉ chứa pending để trả đủ những hàng paid.

Với prepared statement:

```sql
PREPARE pending_lookup(integer, text) AS
SELECT order_id, created_at
FROM multicol_index_lab.orders
WHERE tenant_id = $1
  AND status = $2
ORDER BY created_at DESC
LIMIT 20;
```

Một **generic plan** không thể giả định `$2` luôn là `'pending'`. Vì vậy partial index có thể không được chọn dù ứng dụng thực tế thường truyền pending. PostgreSQL có cơ chế custom/generic plan tùy trường hợp, nên hiệu quả phải đo đúng loại statement và cách bind tham số.

### 18.2. Không đặt now() vào predicate của partial index

Một ý tưởng dễ mắc lỗi:

```sql
-- Không hợp lệ về yêu cầu tính bất biến của index predicate:
-- CREATE INDEX idx_recent
-- ON multicol_index_lab.orders (created_at)
-- WHERE created_at >= now() - INTERVAL '7 days';
```

`now()` thay đổi theo transaction, không phải biểu thức bất biến cho điều kiện của index. Dù tạo được một ranh giới thời gian động kiểu đó, membership của partial index cũng không thể tự di chuyển khi đồng hồ chạy.

Nếu dữ liệu có retention theo ngày, cân nhắc điều kiện hằng theo đợt, partitioning hoặc index trên cột thời gian với cutoff tính lúc query:

```sql
SELECT order_id
FROM multicol_index_lab.orders
WHERE tenant_id = 1
  AND created_at >= now() - INTERVAL '7 days';
```

### 18.3. Partial index và thay đổi trạng thái

Khi đơn chuyển từ pending sang paid, index partial phải cập nhật membership. Nếu status đổi liên tục, chi phí duy trì cũng cần được tính.

Đây là lý do partial index nhỏ hơn có thể nhanh cho SELECT nhưng không “miễn phí” cho UPDATE.

## 19. Expression index nhiều cột: chuẩn hóa khóa tìm kiếm

Một ứng dụng nhiều tenant muốn email không phân biệt chữ hoa/thường **trong từng tenant**:

```text
tenant 1: Alice@Example.com
tenant 1: alice@example.com   -> trùng theo quy tắc nghiệp vụ
tenant 2: alice@example.com   -> hợp lệ vì tenant khác
```

Có thể dùng unique expression index:

```sql
CREATE TABLE multicol_index_lab.contacts (
    contact_id bigint PRIMARY KEY,
    tenant_id integer NOT NULL,
    email text NOT NULL
);

CREATE UNIQUE INDEX idx_contacts_tenant_email_lower
ON multicol_index_lab.contacts
    (tenant_id, lower(email));
```

Thử:

```sql
INSERT INTO multicol_index_lab.contacts
    (contact_id, tenant_id, email)
VALUES
    (1, 1, 'Alice@Example.com'),
    (2, 2, 'alice@example.com');

SELECT contact_id, tenant_id, email
FROM multicol_index_lab.contacts
WHERE tenant_id = 1
  AND lower(email) = lower('ALICE@example.com');
```

Index gồm hai khóa:

1. `tenant_id` — cột thông thường.
2. `lower(email)` — giá trị biểu thức tính từ email.

### 19.1. Query cần viết tương thích biểu thức

Index trên `lower(email)` không nhất thiết hỗ trợ tối ưu câu `WHERE email = 'ALICE@example.com'` giống hệt vì đây là phép so sánh khác ngữ nghĩa.

Hãy viết điều kiện theo chính biểu thức chuẩn hóa hoặc chọn phương án dữ liệu phù hợp. Ngoài ra, quy tắc so sánh email thực tế có thể phức tạp hơn `lower` đơn giản, phụ thuộc collation, chuẩn hóa Unicode và yêu cầu sản phẩm.

### 19.2. Khi nào dùng cột dữ liệu chuẩn hóa?

Trong hệ thống lớn, có thể cân nhắc:

- Lưu email gốc và thêm giá trị normalized được kiểm soát.
- Sử dụng collation hoặc kiểu dữ liệu phù hợp khi PostgreSQL/extension hỗ trợ.
- Đặt unique index theo giá trị chuẩn hóa đã định nghĩa rõ.

Không giả định mọi chuỗi Unicode hoặc định danh địa chỉ đều được xử lý đầy đủ chỉ bằng `lower(text)` theo một collation bất kỳ.

### 19.3. Thứ tự expression cũng quan trọng

Index `(tenant_id, lower(email))` phù hợp lookup theo tenant + email. Index `(lower(email), tenant_id)` phù hợp hơn nếu query thường tìm email trên **mọi tenant**, nhưng cần cân nhắc quyền riêng tư và mô hình multi-tenancy khi làm cross-tenant lookup.

## 20. Composite index và GROUP BY, DISTINCT ON

Index có thứ tự có thể hữu ích cho một số bài toán nhóm và chọn hàng đầu tiên trong mỗi nhóm, dù planner vẫn có thể chọn hash aggregation hoặc sort riêng.

### 20.1. GROUP BY tenant và status

```sql
SELECT
    tenant_id,
    status,
    COUNT(*) AS order_count
FROM multicol_index_lab.orders
GROUP BY tenant_id, status
ORDER BY tenant_id, status;
```

Một B-tree `(tenant_id,status)` sắp các cặp khóa cùng nhóm cạnh nhau, có thể hữu ích nếu PostgreSQL chọn đường đi theo thứ tự và `GroupAggregate`. Nhưng `HashAggregate` hoặc seq scan có thể rẻ hơn, nhất là trên bảng nhỏ.

### 20.2. Đơn mới nhất của mỗi khách

Giả sử muốn **một đơn mới nhất cho mỗi cặp (tenant,customer)**:

```sql
SELECT DISTINCT ON (tenant_id, customer_id)
    tenant_id,
    customer_id,
    order_id,
    created_at,
    status
FROM multicol_index_lab.orders
ORDER BY
    tenant_id,
    customer_id,
    created_at DESC,
    order_id DESC;
```

PostgreSQL có cú pháp `DISTINCT ON`: chọn hàng đầu tiên trong mỗi nhóm theo `ORDER BY` đã xác định. Ở đây `order_id DESC` phá hòa khi created_at trùng.

Index phù hợp:

```sql
CREATE INDEX idx_lab_customer_latest
ON multicol_index_lab.orders
    (tenant_id, customer_id, created_at DESC, order_id DESC);
```

Index có thể cung cấp thứ tự thuận lợi cho DISTINCT ON. Nhưng nếu vẫn phải xem rất nhiều index entries để chọn một hàng mỗi nhóm, tổng chi phí chưa chắc nhỏ. Hãy kiểm tra plan thực và cỡ dữ liệu.

### 20.3. DISTINCT ON không giống GROUP BY MAX rồi JOIN tùy tiện

Một cách thường thấy:

```sql
SELECT tenant_id, customer_id, MAX(created_at)
FROM multicol_index_lab.orders
GROUP BY tenant_id, customer_id;
```

Query này trả ngày mới nhất nhưng **chưa trả chắc chắn một order_id duy nhất** nếu nhiều đơn có cùng created_at. `DISTINCT ON` kèm thứ tự phá hòa giải quyết lựa chọn một hàng rõ ràng.

### 20.4. Keyset cho từng nhóm không giống pagination toàn bảng

Index `(tenant_id,customer_id,created_at DESC,order_id DESC)` được sắp theo từng khách trong tenant. Nó không cung cấp thứ tự created_at DESC **trên mọi khách của tenant** khi customer_id chưa cố định.

Đây là cùng nguyên lý “cột đứng giữa” ở phần trước, áp dụng vào top-1-per-group và pagination.

## 21. Collation và operator class cũng là một phần của thiết kế

Với cột `text`, index order và phép so sánh có thể phụ thuộc vào collation/operator class. Hai index cùng danh sách tên cột nhưng cấu hình so sánh khác có thể phục vụ workload khác nhau.

Ví dụ tạo index cho tìm kiếm exact match theo tenant:

```sql
CREATE INDEX idx_lab_tenant_status_text
ON multicol_index_lab.orders (tenant_id, status);
```

Nếu query sắp theo một collation cụ thể khác collation của index, PostgreSQL không thể mặc định dùng index để đáp ứng order đó theo cùng cách.

### 21.1. LIKE tiền tố và text_pattern_ops

Trong một số cấu hình collation không phải `C`, việc tối ưu `LIKE 'abc%'` bằng B-tree có thể cần operator class phù hợp như `text_pattern_ops`:

```sql
CREATE INDEX idx_lab_tenant_status_prefix
ON multicol_index_lab.orders
    (tenant_id, status text_pattern_ops);
```

Mục đích là hỗ trợ pattern matching dạng tiền tố khi điều kiện và operator class phù hợp. Không áp dụng một cách máy móc cho:

```sql
WHERE status LIKE '%aid%'
```

vì mẫu bắt đầu bằng wildcard không tương tự prefix range B-tree. Với substring search/full-text, cân nhắc phương pháp index khác như trigram GIN nếu extension và workload cho phép.

### 21.2. Index không chỉ có thứ tự tên cột

Một định nghĩa B-tree có thể chỉ rõ:

- `ASC` hoặc `DESC` cho từng cột.
- `NULLS FIRST` / `NULLS LAST`.
- `COLLATE` cho cột text phù hợp.
- Operator class như `text_pattern_ops`.
- Expression keys.
- `INCLUDE`.
- `WHERE` cho partial index.

Khi đánh giá hai index “gần giống nhau”, phải so đầy đủ các thuộc tính này; chỉ so tên cột có thể dẫn tới quyết định xóa sai.

## 22. Đọc EXPLAIN: Index Cond và Filter

Xem một query:

```sql
EXPLAIN
SELECT order_id, created_at, status
FROM multicol_index_lab.orders
WHERE tenant_id = 1
  AND created_at >= TIMESTAMPTZ '2026-10-01 00:00+00'
  AND status = 'paid';
```

Nếu PostgreSQL dùng index `(tenant_id,created_at,status)`, plan có thể có **Index Cond**, **Filter**, hoặc điều kiện được xử lý ở nhiều cấp, tùy plan. Đây là những khái niệm khác nhau:

| Thành phần EXPLAIN | Cách hiểu |
| --- | --- |
| `Index Cond` | Điều kiện được đưa cho index access method để xét khi truy cập chỉ mục. |
| `Filter` | Điều kiện được áp dụng ở node tương ứng sau hoặc ngoài bước truy cập index. |
| `Rows Removed by Filter` | Số hàng bị loại bởi filter tại node, theo thống kê thực thi. |
| `Rows Removed by Index Recheck` | Liên quan recheck index conditions ở các plan có recheck, ví dụ bitmap lossy. |
| `Heap Fetches` | Ở Index Only Scan, số lượt phải kiểm tra heap vì visibility chưa được chứng minh chỉ từ visibility map. |

**Một cột có mặt trong Index Cond không tự bảo đảm nó thu hẹp số leaf entries quét giống như điều kiện bằng ở tiền tố.** Với multicolumn B-tree, phép so sánh trên cột sau có thể được index xử lý mà vẫn phải đi qua nhiều khóa do cột trước chưa đủ ràng buộc.

### 22.1. Ví dụ plan minh họa

```text
Index Scan using idx_lab_tenant_time_status on orders
  Index Cond: (
      tenant_id = 1
      AND created_at >= <cutoff>
  )
  Filter: (status = 'paid')
```

Đây **không phải** plan được bảo đảm xuất hiện trên PostgreSQL. Trong nhiều tình huống PostgreSQL có thể đưa cả điều kiện status vào `Index Cond`, chọn một index khác hoặc seq scan. Hình minh họa giúp bạn đặt câu hỏi đúng: **bao nhiêu entries/pages thực sự đã bị truy cập?**

### 22.2. Câu hỏi khi xem plan

1. PostgreSQL dùng index nào, và index ấy có key order ra sao?
2. `Index Cond` gồm những điều kiện nào?
3. Có `Filter` ngoài index không, lọc đi bao nhiêu hàng?
4. Có `Sort`/`Incremental Sort` không, vì sao?
5. Có `Limit`, và đường đi có thể dừng sớm không?
6. Có `Bitmap Heap Scan`/`BitmapAnd` không?
7. Có `Index Only Scan` với `Heap Fetches` nhiều không?
8. Số row ước lượng có khác xa số row thực không?
9. Buffer hits/reads và thời gian có tương ứng kỳ vọng không?

## 23. EXPLAIN (ANALYZE, BUFFERS): đo trên dữ liệu có ý nghĩa

Thử:

```sql
ANALYZE multicol_index_lab.orders;

EXPLAIN (ANALYZE, BUFFERS)
SELECT order_id, status, created_at
FROM multicol_index_lab.orders
WHERE tenant_id = 1
ORDER BY created_at DESC, order_id DESC
LIMIT 5;
```

Với 24 hàng, `Seq Scan + Sort` hoàn toàn có thể là plan tốt. Điều cần rút ra là **planner đang ước lượng chi phí** trên thống kê và dữ liệu hiện có, không phải một chỉ mục mới chắc chắn được chọn.

### 23.1. Bộ dữ liệu bổ sung tùy chọn

Nếu muốn quan sát rõ khác biệt khi bảng lớn hơn, chỉ trên **database lab**, có thể thêm 100.000 hàng mô phỏng:

```sql
INSERT INTO multicol_index_lab.orders
    (order_id, tenant_id, customer_id, status,
     created_at, total_amount, store_id, shipped_at)
SELECT
    100000 + g AS order_id,
    1 + (g % 50) AS tenant_id,
    1000 + (g % 500) AS customer_id,
    CASE (g % 4)
        WHEN 0 THEN 'pending'
        WHEN 1 THEN 'paid'
        WHEN 2 THEN 'shipped'
        ELSE 'cancelled'
    END AS status,
    TIMESTAMPTZ '2025-01-01 00:00+00'
        + g * INTERVAL '1 minute' AS created_at,
    (50 + (g % 1000))::numeric AS total_amount,
    1 + (g % 4) AS store_id,
    NULL::timestamptz AS shipped_at
FROM generate_series(1, 100000) AS series(g);

ANALYZE multicol_index_lab.orders;
```

Các `order_id` này không trùng với 101–308 của dữ liệu ban đầu. **Chỉ chèn một lần**, nếu chạy lại sẽ gặp lỗi primary key trùng. Thí nghiệm có thể tốn tài nguyên tạo index, WAL và disk nên không chạy trên database có dữ liệu quan trọng.

**Giới hạn mô phỏng:** dữ liệu sinh bằng modulo có tương quan nhân tạo giữa tenant, status, customer và store; nó chỉ giúp xem planner với nhiều hàng, không đại diện thực tế cho phân bố của một hệ thống thương mại.

### 23.2. Hai truy vấn cạnh tranh

Truy vấn A — tất cả đơn mới nhất của tenant:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT order_id, status, created_at
FROM multicol_index_lab.orders
WHERE tenant_id = 1
ORDER BY created_at DESC, order_id DESC
LIMIT 20;
```

Truy vấn B — đơn paid mới nhất của tenant:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT order_id, status, created_at
FROM multicol_index_lab.orders
WHERE tenant_id = 1
  AND status = 'paid'
ORDER BY created_at DESC, order_id DESC
LIMIT 20;
```

Đánh giá index phù hợp:

```sql
CREATE INDEX idx_lab_tenant_latest
ON multicol_index_lab.orders
    (tenant_id, created_at DESC, order_id DESC);

CREATE INDEX idx_lab_tenant_status_latest
ON multicol_index_lab.orders
    (tenant_id, status, created_at DESC, order_id DESC);
```

Lưu ý trong lab trước đó đã có vài index tương tự nhưng khác cột cuối. Đừng dùng ví dụ này để tạo hàng loạt index trùng trong một hệ thống thực; mục đích là minh họa cách so **một index thiên về query A** với **một index thiên về query B**.

### 23.3. Chưa chắc hai truy vấn sinh từ modulo giống production

Do cách sinh dữ liệu, một số tenant có trạng thái phân bố khá lệch hoặc đồng nhất. Planner có thể có kết quả khác hẳn điều bạn hình dung. Đó cũng là bài học: **cardinality và correlation của dữ liệu thực quyết định cost**. Không kết luận dựa trên cấu trúc index mà bỏ qua thống kê.

## 24. Extended statistics cho các cột có tương quan

Một vấn đề thường gặp của truy vấn đa điều kiện là các cột **không độc lập**:

- Trong tenant A, 90% đơn là `paid`.
- Trong tenant B, chỉ 5% đơn là `paid`.
- Một số khách chỉ đặt hàng tại một store.

Nếu planner ước lượng `tenant_id` và `status` là độc lập, số hàng dự đoán cho `tenant_id=... AND status=...` có thể sai lệch.

PostgreSQL có **extended statistics**:

```sql
CREATE STATISTICS stats_lab_tenant_status
    (dependencies, ndistinct, mcv)
ON tenant_id, status
FROM multicol_index_lab.orders;

ANALYZE multicol_index_lab.orders;
```

Ý tưởng:

- `dependencies`: thông tin phụ thuộc chức năng giữa cột, trong phạm vi mà planner có thể tận dụng.
- `ndistinct`: ước lượng số tổ hợp giá trị phân biệt.
- `mcv`: các tổ hợp giá trị thường gặp, hữu ích khi phân bố lệch.

### 24.1. Statistics không phải index

`CREATE STATISTICS` không tạo đường truy cập dữ liệu giống B-tree. Nó cải thiện thông tin để planner **chọn** plan/index có lợi hơn theo workload, khi loại thống kê đó được hỗ trợ trong kiểu truy vấn tương ứng.

Không kỳ vọng tạo stats sẽ tự khiến mọi JOIN/WHERE ước lượng hoàn hảo. Khả năng áp dụng extended statistics có giới hạn và phụ thuộc PostgreSQL major.

### 24.2. Xem thống kê

```sql
SELECT
    statistics_name,
    schemaname,
    tablename,
    attnames,
    kinds
FROM pg_stats_ext
WHERE schemaname = 'multicol_index_lab'
  AND tablename = 'orders';
```

`pg_stats_ext` hiển thị thông tin thống kê được phép xem theo quyền. Độ tin cậy của thống kê còn phụ thuộc lúc `ANALYZE` gần nhất và cách dữ liệu thay đổi.

### 24.3. Đừng nhầm column order của index với column order của statistics

Trong B-tree, thứ tự khóa quyết định đường tìm kiếm và sắp xếp. Với extended statistics, danh sách cột mô tả **nhóm thuộc tính có quan hệ thống kê**; nó không tạo thứ tự B-tree hay thay thế index.

## 25. Vì sao selectivity cao nhất không luôn phải đứng đầu?

Một lời khuyên phổ biến:

> “Cột càng chọn lọc càng phải đứng trước trong chỉ mục nhiều cột.”

Câu này **không phải quy tắc tuyệt đối**.

Giả sử:

- `tenant_id` có 50 giá trị.
- `customer_id` có 100.000 giá trị.
- Một query luôn dùng `tenant_id=? AND customer_id=?`.

Hai index:

```sql
(tenant_id, customer_id)
(customer_id, tenant_id)
```

đều có thể tìm đúng cặp giá trị bằng tương đối hiệu quả. Không nên chọn `customer_id` trước **chỉ vì số giá trị distinct lớn hơn**.

### 25.1. Xét những query phụ

| Query thường gặp | Index thiên về nó |
| --- | --- |
| `WHERE tenant_id=?` | `(tenant_id, customer_id)`. |
| `WHERE customer_id=?` toàn hệ thống | `(customer_id, tenant_id)`. |
| `WHERE tenant_id=? AND customer_id=?` | Cả hai có thể phù hợp cho lookup cặp equality. |
| `WHERE tenant_id=? ORDER BY customer_id` | `(tenant_id, customer_id)`. |
| `WHERE customer_id=? ORDER BY tenant_id` | `(customer_id, tenant_id)`. |

### 25.2. Equality trước range là quy tắc gần hơn

Với:

```sql
WHERE tenant_id = ?
  AND status = ?
  AND created_at >= ?
ORDER BY created_at DESC
```

index kiểu `(tenant_id,status,created_at DESC)` thường phù hợp vì có **hai equality keys theo tiền tố và range/order key ngay sau**.

Việc đảo thứ tự **giữa hai equality keys** có thể ít ảnh hưởng hơn việc đẩy `created_at` lên trước `status` — vì khi đó phạm vi thời gian có thể ngăn status trở thành giới hạn chặt của đoạn index, và đổi thứ tự sort.

### 25.3. Phân phối dữ liệu không đồng đều

Nếu tenant A chiếm 90% số hàng và tenant B chỉ 0.01%, cùng một index có thể đem lại plan khác nhau cho từng tham số. Planner và prepared statement caching còn có thể chọn generic plan chưa tối ưu cho từng tenant.

Vì vậy test với **tenant lớn, tenant nhỏ, status hiếm, status phổ biến**, thay vì chỉ một bộ bind values.

## 26. Tối ưu cho workload: chọn vài index tốt hơn mọi hoán vị

Giả định hệ thống có bốn truy vấn quan trọng:

| Workload | SQL mẫu | Hướng index |
| --- | --- | --- |
| A. Danh sách đơn mới nhất theo tenant | `tenant_id=? ORDER BY created_at DESC, order_id DESC LIMIT 20` | `(tenant_id,created_at DESC,order_id DESC)` |
| B. Danh sách đơn theo trạng thái | `tenant_id=? AND status=? ORDER BY created_at DESC,order_id DESC LIMIT 20` | `(tenant_id,status,created_at DESC,order_id DESC)` |
| C. Lịch sử đơn khách hàng | `tenant_id=? AND customer_id=? ORDER BY created_at DESC,order_id DESC` | `(tenant_id,customer_id,created_at DESC,order_id DESC)` |
| D. Tìm trạng thái toàn hệ thống | `status=? ORDER BY created_at DESC LIMIT 20` | `(status,created_at DESC)` nếu đủ quan trọng |

Không nhất thiết tạo cả bốn ngay. Một quy trình tốt:

1. Thu thập tần suất và độ trễ của từng query thật.
2. Xác định SLA quan trọng (p95/p99 latency, throughput).
3. Đo từng query với index hiện tại.
4. Ưu tiên index phục vụ **hot path và selectivity có ý nghĩa**.
5. Cân nhắc partial index nếu chỉ một trạng thái rất phổ biến trong truy vấn.
6. Đo thêm chi phí INSERT/UPDATE/DELETE và storage.
7. Loại bỏ index dư thừa một cách có kiểm soát khi có bằng chứng.

### 26.1. Vì sao không tạo tất cả 3! hoán vị?

Với ba cột `tenant_id`, `status`, `created_at` có sáu thứ tự sắp xếp. Nhưng thêm sáu index trên bảng lớn:

- Chiếm thêm dung lượng.
- Làm các thao tác ghi phải bảo trì nhiều cấu trúc.
- Tăng lượng WAL.
- Có thể giảm khả năng HOT update nếu nhiều thuộc tính được index.
- Tăng thời gian build, backup/restore và bảo trì.
- Khiến planner có nhiều lựa chọn, không đồng nghĩa query nhanh hơn.

Chọn index theo **truy vấn thực tế** thay vì liệt kê mọi tổ hợp có thể.

### 26.2. INCLUDE không thay thế thiếu key

Nếu workload A và B cạnh tranh, một phương án:

```sql
CREATE INDEX idx_lab_tenant_latest_with_status
ON multicol_index_lab.orders
    (tenant_id, created_at DESC, order_id DESC)
INCLUDE (status);
```

có thể hỗ trợ query A và giúp trả status từ index, nhưng **không cho phép chọn trực tiếp nhóm `status='paid'` như index có status ở key ngay sau tenant**. Query B có thể vẫn phải duyệt nhiều đơn rồi lọc status.

Ngược lại, index `(tenant_id,status,created_at DESC)` phục vụ tốt B nhưng không tự đáp ứng order-by-time toàn tenant của A. Đây là đánh đổi không thể giải quyết chỉ bằng INCLUDE.

## 27. Chi phí của một composite index lớn

Một chỉ mục tăng tốc đọc không miễn phí cho write-heavy workload.

### 27.1. INSERT

Mỗi bản ghi mới có thể cần thêm entry vào nhiều index. Composite index dài có khóa lớn hơn, ảnh hưởng dung lượng và I/O khi bảo trì.

### 27.2. UPDATE

Nếu UPDATE thay đổi một cột xuất hiện trong index key hoặc INCLUDE, PostgreSQL có thể phải cập nhật phần index liên quan và ảnh hưởng điều kiện dùng HOT update.

Ví dụ:

```sql
UPDATE multicol_index_lab.orders
SET status = 'shipped'
WHERE order_id = 102;
```

Mỗi index có status trong key hoặc INCLUDE có thể chịu chi phí cập nhật. Khi status là trường thay đổi thường xuyên, index toàn bộ nhiều biến thể status có thể làm write amplification lớn.

Không chạy ví dụ UPDATE này nếu bạn muốn giữ nguyên dữ liệu lab để đối chiếu những bảng dự đoán trước; có thể bọc thử trong transaction rồi `ROLLBACK`.

### 27.3. DELETE và VACUUM

DELETE/UPDATE tạo thay đổi MVCC; VACUUM có vai trò bảo trì heap/index khi old versions đủ điều kiện cleanup. Nhiều index làm tổng công việc duy trì và vacuum có thể tăng.

### 27.4. Index cột có text lớn

Đưa một cột text dài vào key nhiều cột có thể làm index nặng, thậm chí chạm giới hạn kích thước entry. Không mặc định composite key nên chứa mọi cột có trong WHERE, nhất là dữ liệu JSONB/chuỗi dài mà phương pháp khác phù hợp hơn.

## 28. B-tree nhiều cột khác GIN, GiST, BRIN nhiều cột

Mặc dù cùng viết `CREATE INDEX ... (col1, col2)`, các access methods có chiến lược khác nhau.

### 28.1. GIN

GIN hữu ích cho dữ liệu có nhiều thành phần truy vấn như array, tsvector hoặc JSONB với operator class phù hợp.

Ví dụ:

```sql
CREATE TABLE multicol_index_lab.documents (
    document_id bigint PRIMARY KEY,
    tags text[] NOT NULL,
    search_vector tsvector NOT NULL
);

CREATE INDEX idx_lab_documents_gin
ON multicol_index_lab.documents
USING GIN (tags, search_vector);
```

Truy vấn:

```sql
SELECT document_id
FROM multicol_index_lab.documents
WHERE tags @> ARRAY['postgres']::text[]
  AND search_vector @@ to_tsquery('simple', 'index');
```

GIN không có ý nghĩa “sắp toàn bộ keys theo (tags, search_vector) để thỏa ORDER BY” như composite B-tree. Không áp quy tắc equality-prefix/range của B-tree cho ví dụ này.

### 28.2. GiST

GiST dùng operator class và các cơ chế dựa trên vùng/đặc trưng của dữ liệu phù hợp, ví dụ bài toán không gian hoặc kiểu đặc thù. Với multicolumn GiST, hiệu quả có thể nhạy với cột đầu tiên, nhưng ngữ nghĩa không giống index B-tree có thứ tự lexicographic.

Để dùng GiST thực tế cần xác định data type, operator class và truy vấn mục tiêu. Không nên thay B-tree bằng GiST chỉ vì muốn một index nhiều cột.

### 28.3. BRIN

BRIN lưu thông tin tóm tắt theo **block ranges**, hữu ích khi giá trị cột tương quan với vị trí vật lý của dữ liệu, chẳng hạn bản ghi append theo thời gian:

```sql
CREATE INDEX idx_lab_brin_tenant_created
ON multicol_index_lab.orders
USING BRIN (tenant_id, created_at);
```

BRIN có thể rất nhỏ so với B-tree, nhưng thường cung cấp thông tin lossy theo phạm vi trang và có thể cần recheck. Nó không giúp lấy top 20 đơn gần nhất theo thứ tự khóa như B-tree phù hợp.

Để so hiệu quả, phải xét mức tương quan vật lý và distribution; trên bảng nhỏ hoặc dữ liệu sinh xen kẽ tenant, BRIN không nhất thiết có lợi.

### 28.4. Bảng đối chiếu

| Tiêu chí | B-tree | GIN | GiST | BRIN |
| --- | --- | --- | --- | --- |
| Equality theo key columns | Rất phù hợp. | Theo operators/operator class. | Theo operators/operator class. | Lọc theo tóm tắt range khi phù hợp. |
| Range scalar và ORDER BY thông thường | Rất phù hợp với key order. | Không cung cấp thứ tự B-tree. | Không phải trật tự B-tree thông thường. | Không cung cấp thứ tự B-tree. |
| Thứ tự cột đặc biệt quan trọng | Có, theo quy tắc lexicographic. | Không áp quy tắc tiền tố B-tree. | Có thể quan trọng theo tính chất index. | Không áp quy tắc tiền tố B-tree. |
| Cơ chế chọn ứng viên | Index keys theo B-tree. | Inverted entries. | Phân vùng tìm kiếm tùy operator class. | Block range summaries. |

## 29. PostgreSQL partitioning và composite index

**Table partitioning** chia dữ liệu thành các quan hệ con; **composite index** sắp khóa nhiều cột trong một index. Chúng là hai cơ chế riêng.

Giả sử một bảng đơn được partition theo tháng `created_at`. Một query:

```sql
WHERE tenant_id = 1
  AND created_at >= TIMESTAMPTZ '2026-10-01 00:00+00'
  AND created_at <  TIMESTAMPTZ '2026-11-01 00:00+00'
```

có thể hưởng lợi từ:

1. **Partition pruning:** chỉ truy cập những partition có khoảng created_at phù hợp.
2. **Index scan bên trong partition:** dùng index local phù hợp như `(tenant_id,status,created_at)`.

Không cho rằng có partitioning thì không cần index, cũng không cho rằng index nhiều cột thay thế partition pruning. Sự kết hợp và chi phí phụ thuộc số partition, kích thước mỗi partition và tần suất query.

### 29.1. Chỉ mục và unique constraint trên partitioned table

PostgreSQL có những quy tắc riêng về unique/primary key trên partitioned tables; thông thường để bảo đảm uniqueness toàn bộ qua các partition, khóa unique phải chứa các cột partition key theo các điều kiện được hệ thống hỗ trợ.

Vì thế, khi chuyển từ bảng thường sang partitioned table, **không nên sao chép nguyên composite UNIQUE rồi giả định PostgreSQL bảo đảm tính duy nhất toàn bảng giống cũ**. Cần thiết kế partition key và unique constraints cùng nhau.

### 29.2. Local index order vẫn quan trọng

Một index trong từng partition như `(tenant_id,created_at DESC)` vẫn áp dụng quy tắc B-tree tiền tố và ordering giống trong bảng không partition. Số partition bị quét và việc hợp nhất dữ liệu nhiều partition có thể thêm chi phí sắp xếp/merge ở cấp trên.

## 30. Quy trình chọn thứ tự cột trong dự án thực tế

Hãy bắt đầu từ **danh mục truy vấn thật**, không bắt đầu từ danh mục cột của bảng.

### Bước 1. Liệt kê truy vấn thường xuyên

Ví dụ:

```text
Q1: tenant_id=? ORDER BY created_at DESC, order_id DESC LIMIT 20
Q2: tenant_id=? AND status=? ORDER BY created_at DESC LIMIT 20
Q3: tenant_id=? AND customer_id=? ORDER BY created_at DESC LIMIT 50
Q4: status=? AND created_at >= ?  (báo cáo toàn hệ thống)
```

### Bước 2. Phân loại predicate

Với mỗi query:

- **Equality**: `=`, điều kiện lọc exact match.
- **Range**: `<`, `<=`, `>`, `>=`, một khoảng thời gian.
- **Multi-value**: `IN`, `ANY`, OR.
- **ORDER BY**: thứ tự và chiều ASC/DESC, xử lý NULL.
- **LIMIT**: có cần dừng sớm không?
- **SELECT list**: có lợi từ INCLUDE/index-only không?

### Bước 3. Thiết kế một candidate index

Đặt các cột equality thường xuyên cần cùng xuất hiện ở đầu, sau đó tới cột range/order theo workload. Giữa các cột equality, xét khả năng prefix reuse và các query phụ.

Ví dụ:

```sql
CREATE INDEX idx_candidate
ON multicol_index_lab.orders
    (tenant_id, status, created_at DESC, order_id DESC);
```

### Bước 4. So với workload cạnh tranh

Index trên giúp Q2 nhưng có thể không đáp ứng trực tiếp thứ tự created_at của Q1 khi status không cố định. Cần cân nhắc một index chuyên Q1 nếu Q1 rất quan trọng.

### Bước 5. Kiểm tra số liệu và plan

```sql
ANALYZE multicol_index_lab.orders;

EXPLAIN (ANALYZE, BUFFERS)
SELECT order_id, created_at
FROM multicol_index_lab.orders
WHERE tenant_id = 1
  AND status = 'paid'
ORDER BY created_at DESC, order_id DESC
LIMIT 20;
```

Kiểm tra số hàng thực, Sort, buffers, heap fetches, startup/total time và index choice. Lặp lại với các bộ tham số có selectivity khác nhau.

### Bước 6. Kiểm tra chi phí ghi

Đo latency INSERT/UPDATE/DELETE, WAL generation, index size, vacuum và lưu trữ. Nếu status cập nhật liên tục, một index trên status có thể gây chi phí đáng kể.

### Bước 7. Chỉ giữ index có ích

Gộp hoặc bỏ index dư thừa sau khi có bằng chứng, nhưng không làm trên production mà thiếu kế hoạch rollback và quan sát hot path sau thay đổi.

## 31. Tạo index trên hệ thống đang hoạt động

Ví dụ lab thường dùng:

```sql
CREATE INDEX idx_lab_example
ON multicol_index_lab.orders (tenant_id, created_at);
```

Trong production, tạo index thông thường có thể chặn các lệnh ghi trên bảng trong quá trình build. PostgreSQL hỗ trợ `CREATE INDEX CONCURRENTLY` trong những điều kiện thích hợp để giảm mức chặn hoạt động ghi:

```sql
-- Mẫu minh họa; kiểm tra lock, space và phiên bản trước khi dùng:
CREATE INDEX CONCURRENTLY idx_lab_example_concurrent
ON multicol_index_lab.orders (tenant_id, created_at);
```

Nhưng phải nhớ:

- `CREATE INDEX CONCURRENTLY` **không được chạy trong transaction block tường minh**.
- Nó thường mất nhiều công việc/thời gian hơn so với build thường.
- Có thể phải chờ những transaction/snapshot đang hoạt động theo từng giai đoạn.
- Khi lỗi hoặc bị hủy, có thể để lại **invalid index** cần xử lý.
- Vẫn có chi phí CPU/I/O/WAL và dung lượng đĩa.

Không tự chạy lệnh concurrently trên production như một “thao tác không downtime tuyệt đối”. Cần xem plan triển khai, monitoring và rollback.

### 31.1. Theo dõi tiến độ tạo index

```sql
SELECT
    pid,
    relid::regclass AS table_name,
    index_relid::regclass AS index_name,
    command,
    phase,
    blocks_total,
    blocks_done
FROM pg_stat_progress_create_index;
```

View có thể hiển thị tiến độ build đang chạy theo phiên bản PostgreSQL phù hợp. Khi không có hàng, không nhất thiết PostgreSQL không có index — chỉ là hiện không có thao tác build được theo dõi tại thời điểm truy vấn.

### 31.2. Xem định nghĩa index đang có

```sql
SELECT
    schemaname,
    tablename,
    indexname,
    indexdef
FROM pg_indexes
WHERE schemaname = 'multicol_index_lab'
ORDER BY tablename, indexname;
```

`indexdef` giúp xem thứ tự cột, chiều sort, INCLUDE, WHERE và method nếu có.

### 31.3. Xem index usage và size

```sql
SELECT
    s.schemaname,
    s.relname AS table_name,
    s.indexrelname AS index_name,
    s.idx_scan,
    s.idx_tup_read,
    s.idx_tup_fetch,
    pg_size_pretty(pg_relation_size(s.indexrelid))
        AS index_size
FROM pg_stat_user_indexes AS s
WHERE s.schemaname = 'multicol_index_lab'
ORDER BY pg_relation_size(s.indexrelid) DESC;
```

Các thống kê usage có thể bị reset; chỉ số thấp không chứng minh index vô dụng nếu nó phục vụ constraint, workload hiếm nhưng quan trọng, hoặc mới được tạo. `idx_tup_read` và `idx_tup_fetch` cũng không phải lúc nào tương ứng trực tiếp một-một do cơ chế index-only, bitmap và visibility.

## 32. Những hiểu nhầm thường gặp

### Hiểu nhầm 1. “Cột có selectivity cao nhất luôn phải đứng đầu”

Không. Với nhiều điều kiện equality, cả hai thứ tự có thể lookup theo cặp; cần xét prefix reuse, range, sort, joins và workload.

### Hiểu nhầm 2. “Index (a,b,c) tương đương index (c,b,a)”

Không. Chúng sắp khóa lexicographic khác nhau, phục vụ truy vấn thiếu cột và order khác nhau.

### Hiểu nhầm 3. “Không lọc a thì index (a,b) chắc chắn vô dụng”

Không hoàn toàn. Có thể có skip scan hoặc đường đi khác khi được hỗ trợ/cost hợp lý; nhưng nó không mặc nhiên là index tốt cho b-only.

### Hiểu nhầm 4. “Có Index Cond trên cột sau nghĩa là index chỉ quét đúng những hàng ấy”

Không. Các điều kiện sau range hoặc khi thiếu tiền tố có thể được xử lý trong index nhưng không thu hẹp span quét như equality tiền tố.

### Hiểu nhầm 5. “Equality ở mọi vị trí đều đủ, ORDER BY không quan trọng”

Sai. Index `(tenant,status,created_at)` với tenant equality nhưng status không cố định không cung cấp global created_at order của tenant.

### Hiểu nhầm 6. “Hai index một cột tương đương một index hai cột”

Không. Bitmap combination có thể hữu ích nhưng không giữ key order và có chi phí khác composite index.

### Hiểu nhầm 7. “Nếu một index bao gồm đủ SELECT columns thì chắc dùng Index Only Scan”

Không. Planner còn xét chi phí và MVCC visibility; `Heap Fetches` có thể lớn.

### Hiểu nhầm 8. “INCLUDE status giúp lọc status y như key status”

Không. INCLUDE chứa payload, không tham gia thứ tự hoặc phép dẫn đường theo key.

### Hiểu nhầm 9. “DESC luôn cần index DESC riêng”

Không. PostgreSQL có thể scan B-tree ngược khi thứ tự cần thiết phù hợp. Nhưng mixed directions/NULL ordering cần thiết kế cẩn thận.

### Hiểu nhầm 10. “ORDER BY trong SQL chỉ cần index có các cột đó bất kể thứ tự”

Không. Thứ tự `(a,b)` khác `(b,a)`; cột chưa cố định đứng giữa có thể phá khả năng trả đúng sort.

### Hiểu nhầm 11. “Chỉ mục nhiều cột luôn nhanh hơn seq scan”

Không. Với bảng nhỏ hoặc predicate chọn phần lớn bảng, seq scan có thể rẻ hơn.

### Hiểu nhầm 12. “Partial index dùng được với mọi bind parameter”

Không. Planner phải chứng minh query kéo theo predicate của index. Generic prepared plan với `status=$1` không thể biết status luôn pending.

### Hiểu nhầm 13. “Partial index WHERE created_at >= now()-7days là một rolling index”

Không. Predicate có hàm thời gian không immutable không hợp lệ theo yêu cầu index. Giới hạn động thuộc truy vấn hoặc kiến trúc retention khác.

### Hiểu nhầm 14. “Composite UNIQUE buộc từng cột tự duy nhất”

Không. `UNIQUE(a,b)` ràng buộc **tổ hợp** (với NULL semantics tương ứng), không bắt từng a hay từng b là unique riêng.

### Hiểu nhầm 15. “UNIQUE(a,b) và UNIQUE(b,a) khác tính duy nhất của cặp”

Về cặp giá trị, không khác nếu cùng semantics; khác **thứ tự index** và hiệu quả query.

### Hiểu nhầm 16. “NULLS FIRST/LAST không ảnh hưởng index order”

Sai. Null ordering là một phần trật tự B-tree và khả năng thỏa ORDER BY.

### Hiểu nhầm 17. “EXPLAIN trên 24 hàng đủ chứng minh index mới nhanh”

Không. Seq scan trên bảng rất nhỏ thường rẻ hơn; cần dữ liệu và tham số đại diện.

### Hiểu nhầm 18. “Ít index hơn luôn tốt hơn”

Không. Query hot path có thể cần index chuyên biệt. Phải cân đối read latency, write throughput, storage và maintenance.

### Hiểu nhầm 19. “Nhiều index càng tốt vì planner tự chọn”

Không. Mỗi index gây chi phí ghi và tài nguyên; index trùng lặp không tự tăng performance.

### Hiểu nhầm 20. “GROUP BY hoặc DISTINCT ON luôn sử dụng composite index”

Không. Nó có thể giúp thứ tự, nhưng planner cũng có thể hash/sort/scan tùy chi phí.

### Hiểu nhầm 21. “Thứ tự cột B-tree áp dụng nguyên cho GIN/GiST/BRIN”

Không. Mỗi access method có nguyên lý và operator classes riêng.

### Hiểu nhầm 22. “Table partitioning thay thế composite indexes”

Không. Pruning chọn partitions; index vẫn có thể tối ưu truy cập **bên trong** các partitions.

### Hiểu nhầm 23. “Status-only query chắc chắn cần composite (tenant,status)”

Không. Nếu status-only là hot path, một index bắt đầu từ status có thể hợp lý hơn; quyết định phải đo trên workload.

### Hiểu nhầm 24. “CREATE INDEX CONCURRENTLY không thể gặp blocking/chờ”

Không. Nó giảm một số dạng chặn write so với build thường nhưng vẫn có nhiều pha, có thể chờ transaction và cần giám sát.

## 33. Bài tập thực hành

Các bài tập sử dụng schema `multicol_index_lab` đã tạo ở phần 3, 13, 14, 19, 28. Khi bài yêu cầu tạo index, nên thử trong database lab; không cần xây dựng mọi index minh họa trong cùng một bảng production. Với câu hỏi về plan, câu trả lời đúng là **khả năng hỗ trợ và những điểm cần quan sát**, không hứa planner phải chọn một node duy nhất.

### Bài 1. Giải thích thứ tự khóa

Một index B-tree được định nghĩa như sau:

```sql
CREATE INDEX idx_exercise_1
ON multicol_index_lab.orders
    (tenant_id, status, created_at DESC);
```

Mô tả thứ tự khóa khi có nhiều tenant, nhiều status và nhiều ngày. Những hàng cùng tenant có được sắp theo created_at DESC **trên toàn tenant** không?

### Bài 2. Tìm kiếm theo tiền tố

Với index `(tenant_id,status,created_at DESC)`, hai query dưới đây khác nhau thế nào về khả năng giới hạn vùng quét?

```sql
-- A
WHERE tenant_id = 1
  AND status = 'paid'

-- B
WHERE status = 'paid'
```

### Bài 3. Nhiều điều kiện bằng

Query luôn có `tenant_id=? AND customer_id=?`. Có thể khẳng định index `(customer_id,tenant_id)` luôn nhanh hơn `(tenant_id,customer_id)` vì customer_id có nhiều giá trị distinct hơn không?

### Bài 4. Equality và range

Thiết kế một composite B-tree index cho:

```sql
SELECT order_id, created_at
FROM multicol_index_lab.orders
WHERE tenant_id = 2
  AND status = 'paid'
  AND created_at >= TIMESTAMPTZ '2026-10-01 00:00+00'
ORDER BY created_at DESC, order_id DESC
LIMIT 10;
```

Giải thích thứ tự cột.

### Bài 5. ORDER BY khi thiếu status

Chỉ mục `(tenant_id,status,created_at DESC)` có đáp ứng trực tiếp:

```sql
WHERE tenant_id = 1
ORDER BY created_at DESC
```

trên toàn tenant không? Vì sao?

### Bài 6. Top-N theo tenant

Thiết kế index cho truy vấn lấy 20 đơn mới nhất của một tenant, với thứ tự ổn định kể cả khi nhiều đơn trùng timestamp.

### Bài 7. IN nhiều trạng thái

Vì sao `WHERE tenant_id=1 AND status IN ('paid','shipped') ORDER BY created_at DESC` có thể phải sắp xếp dù có index `(tenant_id,status,created_at DESC)`?

### Bài 8. Scan ngược

Một index `(tenant_id ASC, created_at ASC)` có thể giúp truy vấn `WHERE tenant_id=1 ORDER BY created_at DESC` không? Khi nào cần một index mixed-direction khác?

### Bài 9. NULLS LAST

Viết một index phù hợp cho truy vấn:

```sql
SELECT order_id, shipped_at
FROM multicol_index_lab.orders
WHERE tenant_id = 1
ORDER BY shipped_at DESC NULLS LAST
LIMIT 10;
```

### Bài 10. Keyset pagination

Cho thứ tự `ORDER BY created_at DESC, order_id DESC` và cursor cuối trang `(2026-10-04 08:00+00, 104)`. Viết WHERE để lấy các hàng sau cursor trong tenant 1.

### Bài 11. Composite UNIQUE

Thiết kế constraint để `external_order_no` duy nhất **trong mỗi tenant** nhưng mã đó có thể lặp giữa hai tenant. Có bắt `external_order_no` một mình duy nhất không?

### Bài 12. Nullable unique

Giải thích mặc định PostgreSQL xử lý NULL như thế nào trong composite unique key. Từ PostgreSQL 15 có cú pháp gì để NULL được coi là không phân biệt cho uniqueness?

### Bài 13. INCLUDE

Thiết kế index hỗ trợ tìm đơn paid theo tenant, thời gian giảm dần và trả cả `total_amount` mà không đặt `total_amount` thành key. Tại sao INCLUDE không giúp lọc theo amount như key?

### Bài 14. Index Only Scan

Nếu index đã chứa đủ những cột query đọc, có thể bỏ qua mọi heap access được không? Vai trò của visibility map và `Heap Fetches` là gì?

### Bài 15. Partial index

Thiết kế index nhỏ cho màn hình chỉ hiển thị đơn pending mới nhất của từng tenant. Query tìm đơn shipped có dùng index này để trả đủ kết quả không?

### Bài 16. Prepared statement với partial index

Vì sao query `WHERE status=$1` có thể không dùng partial index chỉ dành cho `status='pending'` khi PostgreSQL chọn generic plan?

### Bài 17. Expression index

Viết unique index để trong mỗi tenant không có hai giá trị email trùng theo `lower(email)`. Truy vấn nào tương thích với biểu thức đó?

### Bài 18. Bitmap kết hợp index

Giả sử chỉ có index `(tenant_id)` và `(status)`. PostgreSQL có thể kết hợp chúng thế nào cho query hai điều kiện? Vì sao `ORDER BY created_at DESC LIMIT 20` vẫn có thể cần Sort?

### Bài 19. Index Cond và Filter

Một plan có `Index Cond: tenant_id=1` và `Filter: status='paid'`. Nó chứng minh điều gì và **không chứng minh** điều gì về chi phí?

### Bài 20. Dữ liệu nhỏ và EXPLAIN

Vì sao PostgreSQL có thể không dùng index composite trên bảng 24 hàng dù index phù hợp? Lệnh nào giúp đo số liệu thực thi và bộ nhớ đệm?

### Bài 21. DISTINCT ON

Viết một index cho truy vấn chọn đơn mới nhất **của mỗi khách trong từng tenant**, dùng `DISTINCT ON (tenant_id, customer_id)` và tie-breaker `order_id`.

### Bài 22. Extended statistics

`tenant_id` và `status` có tương quan mạnh. Viết lệnh `CREATE STATISTICS` cho `mcv` và `dependencies`, sau đó cập nhật thống kê. Vì sao đây không phải là index?

### Bài 23. Chi phí UPDATE

Hệ thống có 10 composite indexes đều chứa `status` và status đổi thường xuyên. Điều gì có thể xảy ra với throughput ghi, WAL, kích thước và HOT update?

### Bài 24. Skip scan

Index `(store_id,customer_id)` có thể phục vụ `WHERE customer_id=10` trong một số PostgreSQL không? Khi nào skip scan có thể có lợi, và vì sao không nên mặc định nó luôn được dùng?

### Bài 25. B-tree và BRIN

Một bảng log cực lớn được nạp theo thời gian vật lý, chủ yếu query theo khoảng thời gian dài. So sánh nhanh một BRIN trên thời gian với B-tree trên `(tenant_id,created_at)`. Chúng có cùng khả năng trả `ORDER BY created_at DESC LIMIT 20` không?

### Bài 26. Chọn index theo workload

Bạn có ba query:

```text
Q1: WHERE tenant_id=? ORDER BY created_at DESC LIMIT 20
Q2: WHERE tenant_id=? AND status=? ORDER BY created_at DESC LIMIT 20
Q3: WHERE tenant_id=? AND customer_id=? ORDER BY created_at DESC LIMIT 20
```

Đề xuất bộ index ứng viên và giải thích vì sao chưa chắc phải tạo đủ cả ba.

## 34. Gợi ý lời giải

### Đáp án 1. Thứ tự khóa

Index được sắp theo `tenant_id` trước, rồi theo `status` trong tenant, rồi `created_at DESC` trong mỗi cặp tenant/status. Nó **không** bảo đảm created_at giảm dần toàn tenant khi status chưa cố định.

### Đáp án 2. Tiền tố

Query A có điều kiện bằng trên hai cột đầu nên B-tree có thể đi đến vùng khóa `(tenant=1,status='paid')`. Query B bỏ tenant: paid phân tán qua nhiều vùng tenant; index có thể vẫn dùng bằng những phương án khác nhưng không đạt cùng lợi thế tìm một đoạn liên tục. Nếu status-only là hot path, cân nhắc index bắt đầu từ status.

### Đáp án 3. Thứ tự của các equality keys

Không. Cả hai thứ tự có thể phù hợp khi query luôn có equality cho cả hai cột. Chọn dựa trên khả năng phục vụ query chỉ lọc tenant hoặc customer, ORDER BY và toàn workload, không chỉ dựa vào cardinality của một cột.

### Đáp án 4. Equality rồi range/sort

```sql
CREATE INDEX idx_exercise_4
ON multicol_index_lab.orders
    (tenant_id, status, created_at DESC, order_id DESC);
```

Hai cột đầu là equality, tiếp theo thời gian phục vụ phạm vi và sort, order_id tạo tie-breaker. Đây là một candidate index hợp lý; PostgreSQL không bắt buộc phải chọn nó với dữ liệu nhỏ.

### Đáp án 5. Cột status ở giữa

Không trực tiếp trên toàn tenant. Index phân nhóm theo status trước created_at, nên thời gian có thứ tự riêng trong mỗi nhóm status. PostgreSQL có thể cần Sort hoặc index `(tenant_id,created_at DESC)` phù hợp hơn.

### Đáp án 6. Top-N

```sql
CREATE INDEX idx_exercise_6
ON multicol_index_lab.orders
    (tenant_id, created_at DESC, order_id DESC);
```

Query:

```sql
SELECT order_id, created_at
FROM multicol_index_lab.orders
WHERE tenant_id = 1
ORDER BY created_at DESC, order_id DESC
LIMIT 20;
```

`order_id` phá hòa khi timestamp bằng nhau, giúp thứ tự và cursor ổn định.

### Đáp án 7. IN

`IN` trên status chọn nhiều khối status. Index có thứ tự created_at riêng trong từng khối, không bảo đảm trộn tất cả trạng thái theo thời gian toàn cục. PostgreSQL có thể cần Sort hoặc kế hoạch khác.

### Đáp án 8. Scan ngược

Có. Khi `tenant_id` cố định, scan ngược trên vùng tenant có thể phục vụ created_at DESC. Nhưng nếu không cố định tenant và cần `tenant_id ASC,created_at DESC`, index mixed-direction thường phù hợp hơn do scan ngược index ASC/ASC đảo chiều cả hai cột.

### Đáp án 9. NULL ordering

```sql
CREATE INDEX idx_exercise_9
ON multicol_index_lab.orders
    (tenant_id, shipped_at DESC NULLS LAST);
```

Khi tenant đã cố định, index có thể cung cấp `shipped_at DESC NULLS LAST`.

### Đáp án 10. Keyset

```sql
SELECT order_id, created_at
FROM multicol_index_lab.orders
WHERE tenant_id = 1
  AND (created_at, order_id) <
      (TIMESTAMPTZ '2026-10-04 08:00+00', 104)
ORDER BY created_at DESC, order_id DESC
LIMIT 20;
```

Phép so sánh tuple và hai khóa DESC chọn phần sau cursor. Cần xử lý rõ NULL, filters và thay đổi dữ liệu giữa các page trong hệ thống thực tế.

### Đáp án 11. Composite uniqueness

```sql
CREATE TABLE multicol_index_lab.partner_refs (
    tenant_id integer NOT NULL,
    external_order_no text NOT NULL,
    UNIQUE (tenant_id, external_order_no)
);
```

Không bắt `external_order_no` tự duy nhất. `('INV-001'` ở tenant 1) và cùng mã ở tenant 2 vẫn hợp lệ.

### Đáp án 12. NULL

Mặc định unique thông thường có thể cho phép nhiều tổ hợp có NULL ở thành phần khóa mà không coi NULL giống nhau. Từ PostgreSQL 15 có:

```sql
UNIQUE NULLS NOT DISTINCT (tenant_id, optional_code)
```

Nên kiểm tra yêu cầu business trước khi chọn semantics.

### Đáp án 13. INCLUDE

```sql
CREATE INDEX idx_exercise_13
ON multicol_index_lab.orders
    (tenant_id, status, created_at DESC, order_id DESC)
INCLUDE (total_amount);
```

`total_amount` là payload, không tham gia sắp xếp/tìm kiếm key. Nó có thể giúp index-only scan khi visibility cho phép, nhưng không biến predicate amount thành vùng quét được dẫn đường như key.

### Đáp án 14. Index-only

Không bảo đảm. PostgreSQL vẫn phải xác minh MVCC visibility; khi heap page chưa all-visible, index-only scan có thể truy cập heap. `Heap Fetches` phản ánh số lượt kiểm tra heap ở plan tương ứng; planner còn có thể chọn phương án khác.

### Đáp án 15. Partial index

```sql
CREATE INDEX idx_exercise_15
ON multicol_index_lab.orders
    (tenant_id, created_at DESC, order_id DESC)
WHERE status = 'pending';
```

Index chỉ chứa pending, không thể phục vụ đầy đủ một query chỉ tìm shipped.

### Đáp án 16. Generic prepared plan

Trong generic plan, `status=$1` có thể là bất kỳ giá trị nào, không chứng minh query luôn thỏa `status='pending'` của index. Custom plan trong trường hợp cụ thể có thể khác, nên kiểm tra plan cho cách ứng dụng thực thi.

### Đáp án 17. Expression index

```sql
CREATE UNIQUE INDEX idx_exercise_17
ON multicol_index_lab.contacts
    (tenant_id, lower(email));
```

Lookup:

```sql
SELECT contact_id
FROM multicol_index_lab.contacts
WHERE tenant_id = 1
  AND lower(email) = lower('Alice@Example.com');
```

Khả năng chuẩn hóa email đầy đủ phụ thuộc quy định nghiệp vụ và collation.

### Đáp án 18. Bitmap

Planner có thể dùng `BitmapAnd` của `Bitmap Index Scan` từ hai index, rồi `Bitmap Heap Scan`. Bitmap không giữ thứ tự của B-tree, nên ORDER BY thời gian có thể cần sort và không có lợi thế early-stop giống index phù hợp cho top-N.

### Đáp án 19. EXPLAIN

Plan cho thấy index access có điều kiện tenant và node còn lọc status. Nhưng nó không chứng minh index hiệu quả: cần số rows/buffers/time, tình trạng cache và selectivity. Một plan khác cũng có thể đưa status vào `Index Cond` tùy index và planner.

### Đáp án 20. EXPLAIN ANALYZE

Trên bảng rất nhỏ, seq scan thường rẻ hơn traversing index + heap. Dùng:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT order_id
FROM multicol_index_lab.orders
WHERE tenant_id = 1
  AND status = 'paid';
```

Kết quả thực phụ thuộc dữ liệu, cache và index đang tồn tại.

### Đáp án 21. DISTINCT ON

```sql
CREATE INDEX idx_exercise_21
ON multicol_index_lab.orders
    (tenant_id, customer_id, created_at DESC, order_id DESC);
```

```sql
SELECT DISTINCT ON (tenant_id, customer_id)
    tenant_id, customer_id, order_id, created_at
FROM multicol_index_lab.orders
ORDER BY
    tenant_id, customer_id,
    created_at DESC, order_id DESC;
```

Index cung cấp thứ tự hữu ích; nhưng planner vẫn có thể chọn phương án khác tùy chi phí.

### Đáp án 22. Extended statistics

```sql
CREATE STATISTICS stats_exercise_22
    (dependencies, mcv)
ON tenant_id, status
FROM multicol_index_lab.orders;

ANALYZE multicol_index_lab.orders;
```

Statistics giúp planner ước lượng phân bố/độ phụ thuộc, không tạo cấu trúc lưu TID có thứ tự để tìm hàng như B-tree.

### Đáp án 23. Write cost

Mỗi UPDATE làm thay đổi status có thể phải bảo trì nhiều index, tăng WAL/I/O và index storage. Nếu các cột được index (kể cả INCLUDE) thay đổi, HOT update có thể bị hạn chế. Cần đo và giảm index không đem lợi ích đủ lớn.

### Đáp án 24. Skip scan

Có thể có ở phiên bản PostgreSQL hỗ trợ và khi cost model thấy phù hợp, nhất là cột đầu store_id ít giá trị distinct còn customer_id rất chọn lọc. Không phải tối ưu luôn xuất hiện; nếu query customer-only quan trọng cần đo hoặc tạo index bắt đầu bằng customer_id.

### Đáp án 25. BRIN

BRIN thường nhỏ, phù hợp với block-range summaries khi giá trị có tương quan vật lý. Nó có thể lọc thô các phạm vi nhưng **không có thứ tự B-tree** phục vụ top-N chính xác. B-tree `(tenant_id,created_at)` tốt cho lookup tenant + time và sort theo time khi đúng chiều, đổi lại tốn nhiều storage/write cost hơn.

### Đáp án 26. Bộ index ứng viên

Có thể đề xuất:

```sql
-- Q1: toàn tenant theo thời gian
CREATE INDEX idx_workload_q1
ON multicol_index_lab.orders
    (tenant_id, created_at DESC, order_id DESC);

-- Q2: tenant + status theo thời gian
CREATE INDEX idx_workload_q2
ON multicol_index_lab.orders
    (tenant_id, status, created_at DESC, order_id DESC);

-- Q3: tenant + customer theo thời gian
CREATE INDEX idx_workload_q3
ON multicol_index_lab.orders
    (tenant_id, customer_id, created_at DESC, order_id DESC);
```

Trong lab **không cần chạy cả ba** nếu đã có các index tương đương ở những phần trước. Trên production, phải đo tần suất Q1/Q2/Q3, selectivity, latency và write overhead. Có thể chỉ một hoặc hai query đủ quan trọng để đáng tạo index chuyên dụng; những query còn lại dùng plan khác vẫn đáp ứng SLA.

## 35. Checklist thiết kế và vận hành composite index

Trước khi thêm một index mới, hãy trả lời:

1. **Query nào cần tối ưu?** Có SQL thật và thông số tần suất/latency không?
2. **Grain của dữ liệu là gì?** Một hàng một đơn, nhiều hàng chi tiết hay nhiều tenant?
3. **Điều kiện bằng nào luôn hiện diện?** Có thể tạo tiền tố hữu ích?
4. **Cột nào dùng range?** Nó nên đứng đâu sau các equality keys?
5. **ORDER BY cần gì?** Thứ tự cột, ASC/DESC, NULLS, collation đã khớp chưa?
6. **Có LIMIT không?** Index có thể tránh sort và dừng sớm không?
7. **Có tie-breaker không?** Pagination có thứ tự ổn định theo unique key?
8. **Có hot query thiếu cột đầu không?** Có cần index riêng, hay skip scan/bitmap đủ?
9. **IN chọn một hay nhiều giá trị?** Nhiều nhóm có phá global sort không?
10. **INCLUDE có đủ lợi ích không?** Cột có thật sự cần để giảm heap fetch không?
11. **Partial index có phù hợp không?** Query có chứng minh được predicate, nhất là prepared statements?
12. **Expression/collation có khớp SQL không?** Có cast cột hoặc dùng `lower` không?
13. **Composite UNIQUE đang bảo đảm quy tắc gì?** NULL semantics có đúng không?
14. **Đã xem composite indexes hiện có chưa?** Có index nào trùng/bao tiền tố có thể tái sử dụng?
15. **Thống kê có mới không?** Cần `ANALYZE` hoặc extended stats cho cột tương quan?
16. **Dữ liệu thử có đại diện không?** Có tenant lớn/nhỏ, status hiếm/phổ biến?
17. **EXPLAIN đã đo thật chưa?** Có Sort, Bitmap, Index Only, Heap Fetches, nhiều buffers không?
18. **Chi phí ghi tăng bao nhiêu?** Index keys/INCLUDE có là cột thường UPDATE?
19. **Dung lượng và WAL có đủ không?** Index build trên bảng lớn tốn tài nguyên.
20. **Kế hoạch production an toàn chưa?** Có cân nhắc concurrent build, monitoring và xử lý invalid index không?
21. **Có ràng buộc partitioning không?** Index/unique key tương tác partition key ra sao?
22. **Có chỉ mục ở bảng con JOIN/FK không?** Không giả định FK tự tạo mọi index cần thiết.

## 36. Sơ đồ quyết định nhanh

```text
                       Query cần tối ưu
                              |
                              v
                    Xác định equality keys
                              |
                              v
                  Có range hoặc ORDER BY?
                     /                 \
                   Có                 Không
                   |                    |
                   v                    v
          Đặt range/order key    Xét prefix reuse,
          sau equality keys      các query một phần
                   |                    |
                   +----------+---------+
                              |
                              v
                    Query có LIMIT?
                       /          \
                     Có          Không
                     |             |
                     v             v
             Xem khả năng dừng  Đo selectivity,
             sớm và sort       scans, bitmap
                     |             |
                     +------+------+ 
                            |
                            v
                    Cần cột trả về?
                            |
                            v
                     Cân nhắc INCLUDE
                            |
                            v
                Cần partial/expression?
                            |
                            v
                 ANALYZE + EXPLAIN thực
                            |
                            v
                 So read gain vs write cost
                            |
                            v
                    Giữ ít index hữu ích
```

Sơ đồ này là **quy trình gợi ý**, không phải thuật toán chắc chắn tìm ra cấu trúc tối ưu cho mọi workload. Một query có nhiều pattern hoặc bảng partitioned cần đánh giá thêm các phương án khác.

## 37. Tổng kết

Chỉ mục nhiều cột trong PostgreSQL, đặc biệt **B-tree**, là công cụ rất mạnh nhưng phải được thiết kế theo **truy vấn thực tế**:

- **Thứ tự cột quyết định thứ tự khóa.** `(tenant_id,status,created_at)` khác `(tenant_id,created_at,status)`, đặc biệt khi thiếu điều kiện trên cột ở giữa.
- **Tiền tố equality + cột range/order tiếp theo** thường là hình thức truy vấn phù hợp để thu hẹp vùng quét và tránh sort. Nhưng đây là heuristic, không phải luật tuyệt đối cho mọi plan.
- **Nhiều equality keys** có thể được đổi thứ tự mà vẫn lookup theo cặp hiệu quả; khả năng phục vụ query tiền tố, sort và workload mới quyết định thứ tự tốt hơn.
- **Không có cột đầu không nhất thiết không dùng được index.** PostgreSQL có các đường đi khác, bao gồm skip scan ở phiên bản/tình huống được hỗ trợ; tuy nhiên nên đo thay vì phụ thuộc mặc định.
- **`ORDER BY ... LIMIT`** là lý do rất quan trọng để ưu tiên index chứa thời gian và tie-breaker theo thứ tự phù hợp; keyset pagination có thể tránh OFFSET rất lớn.
- **INCLUDE** là payload để hỗ trợ trả dữ liệu/index-only scan, không biến cột thành key tìm kiếm. Index-only scan còn phụ thuộc visibility map và quyết định planner.
- **Composite UNIQUE, partial và expression index** còn phục vụ tính đúng đắn và những query đặc biệt; phải xét NULL, collation, predicate và prepared statements.
- **Nhiều single-column indexes** có thể kết hợp qua bitmap, nhưng bitmap thường không giữ thứ tự khóa. Composite index tốt có thể giảm việc quét/sort trên hot path.
- **Hiệu quả không chỉ nằm ở SELECT.** Mỗi index làm tăng chi phí storage, INSERT, UPDATE, DELETE, WAL và maintenance.
- **`EXPLAIN (ANALYZE, BUFFERS)` và dữ liệu đại diện** mới cho bằng chứng đáng tin để chọn key order; không thể kết luận từ SQL text hoặc một bảng 24 hàng.

Nguyên tắc ghi nhớ:

> Đừng hỏi “bảng có những cột nào để đưa hết vào index?”. Hãy hỏi **“PostgreSQL sẽ lọc theo những giá trị nào, cần đi qua khóa theo thứ tự gì, cần dừng ở đâu và workload khác có tái sử dụng được chỉ mục đó không?”**

Trả lời được bốn câu hỏi này, bạn sẽ chủ động chọn thứ tự cột trong composite indexes thay vì thử các hoán vị ngẫu nhiên.


