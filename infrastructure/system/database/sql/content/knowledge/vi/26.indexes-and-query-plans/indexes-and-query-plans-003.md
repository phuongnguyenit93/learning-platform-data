# Thứ tự cột trong chỉ mục và mẫu điều kiện lọc trong SQL

Khi có bảng dữ liệu lớn, tạo chỉ mục (*index*) không chỉ là chọn **những cột thường xuất hiện trong `WHERE`**. Với chỉ mục nhiều cột, **thứ tự cột** quyết định những truy vấn nào có thể thu hẹp phạm vi tra cứu hiệu quả, hỗ trợ sắp xếp, và những truy vấn nào vẫn phải đọc nhiều mục chỉ mục hoặc sắp xếp lại kết quả.

Xét hai chỉ mục B-tree:

~~~sql
CREATE INDEX ix_a
ON don_hang (customer_id, status, created_at);

CREATE INDEX ix_b
ON don_hang (status, created_at, customer_id);
~~~

Hai chỉ mục chứa cùng ba cột, nhưng **không tương đương**.

- Với `WHERE customer_id = 10 AND status = 'PAID' AND created_at >= ...`, chỉ mục `ix_a` có hai điều kiện bằng nhau liên tiếp ở đầu, rồi đến khoảng thời gian.
- Với `WHERE status = 'PAID' AND created_at >= ...`, `ix_b` có hai điều kiện phù hợp ở đầu, trong khi `ix_a` thiếu điều kiện cho cột đầu `customer_id`.
- Với `WHERE customer_id = 10 ORDER BY created_at DESC`, `ix_a` chưa chắc trả đúng thứ tự `created_at` toàn cục trong khách 10, vì có cột `status` nằm giữa.

Bài học này tập trung vào **“Thứ tự cột trong chỉ mục và mẫu điều kiện lọc”** thuộc chương **Chỉ mục và kế hoạch** của module **Database SQL**. Ta sẽ học cách đọc truy vấn, đề xuất thứ tự cột, kiểm tra bằng `EXPLAIN` và tránh những quy tắc máy móc như “luôn đặt cột chọn lọc nhất đầu tiên”.

Các ví dụ dùng **PostgreSQL** và B-tree, loại chỉ mục mặc định khi viết `CREATE INDEX` thông thường. Hành vi tối ưu có thể thay đổi theo phiên bản, phân bố dữ liệu, thống kê, mức tương quan, số hàng và chi phí I/O. Những nguyên tắc dưới đây là **cách phân tích và kiểm chứng**, không phải lời hứa rằng optimizer sẽ luôn dùng một chỉ mục nhất định.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích ý nghĩa của **khóa chỉ mục gồm nhiều cột** và trật tự sắp xếp vật lý/logical trong B-tree.
2. Nhận ra vai trò của các điều kiện **bằng (`=`)**, **khoảng (`<`, `>`, `BETWEEN`)** và **IN** đối với cột dẫn đầu.
3. Hiểu quy tắc **tiền tố bên trái (*leftmost prefix*)** trong việc xác định phần chỉ mục có thể thu hẹp.
4. Biết khi nào một cột lọc xuất hiện trong chỉ mục nhưng **không đủ để thu hẹp phạm vi quét đáng kể**.
5. Lựa chọn thứ tự cột cho các truy vấn có `WHERE`, `ORDER BY`, `LIMIT`, `JOIN` và phân trang.
6. Phân biệt chỉ mục có cùng bộ cột nhưng **khác thứ tự**, và chỉ mục một cột so với chỉ mục tổng hợp.
7. Hiểu vì sao “cột có độ chọn lọc cao nhất đứng đầu” **không phải quy tắc tuyệt đối**.
8. Biết lúc nào cần xem xét **partial index**, **expression index**, **covering index với INCLUDE**.
9. Xử lý các mẫu `OR`, `IS NULL`, `LIKE` và điều kiện có hàm trên cột.
10. Đọc một số dấu hiệu cơ bản trong `EXPLAIN (ANALYZE, BUFFERS)`: `Index Cond`, `Filter`, `Sort`, `Bitmap Index Scan`.
11. Đánh giá sự đánh đổi giữa tốc độ đọc, số lượng chỉ mục, dung lượng và chi phí ghi.
12. Vận dụng vào bài tập chọn thứ tự cột cho các workload khác nhau.

## 2. Hình dung B-tree nhiều cột như một danh sách đã sắp xếp

Một chỉ mục B-tree trên:

~~~sql
(customer_id, status, created_at)
~~~

có thể hình dung theo thứ tự từ trái qua phải:

~~~text
customer_id    status       created_at
--------------------------------------
10             CANCELLED    ...
10             NEW          ...
10             PAID         2026-10-05 ...
10             PAID         2026-10-12 ...
20             CANCELLED    ...
20             NEW          ...
20             PAID         2026-10-04 ...
20             PAID         2026-10-09 ...
30             NEW          ...
30             PAID         ...
...
~~~

Đây là **mô hình khái niệm**, không phải ảnh chụp chính xác các trang index trên đĩa. B-tree tổ chức các khóa để có thể tìm tới một vị trí và duyệt các mục theo thứ tự của khóa chỉ mục.

Thứ tự so sánh là **từ cột đầu, rồi mới tới cột sau**:

1. So `customer_id`.
2. Nếu cùng `customer_id`, so `status`.
3. Nếu cùng cả hai, so `created_at`.

Điểm mấu chốt: những giá trị `created_at` của **các status khác nhau** không nhất thiết nằm trong một dãy chung đã sắp xếp theo thời gian cho cùng khách hàng.

### 2.1. Một công thức nhớ

~~~text
INDEX(a, b, c)

Các nhóm lớn: a
  └── Trong từng a, nhóm nhỏ: b
        └── Trong từng (a,b), sắp xếp: c
~~~

Vì vậy:

- Biết `a = ?` giúp đi vào một nhóm.
- Biết `a = ? AND b = ?` giúp đi vào một nhóm nhỏ hơn.
- Biết thêm `c` thuộc khoảng nào có thể thu hẹp tiếp vùng cần đọc.
- Chỉ biết `c = ?` mà không biết `a` hay `b` thường không có cùng lợi thế của một tiền tố liên tiếp.

Tuy nhiên, đây là nguyên tắc tra cứu B-tree thông thường. Một số phiên bản/optimizer có các lựa chọn như **skip scan**, quét toàn index hoặc kết hợp bitmap, nên không được khẳng định “thiếu cột đầu thì index hoàn toàn không thể sử dụng”.

## 3. Chuẩn bị bảng dữ liệu thực hành

Các câu SQL sau dùng PostgreSQL. Bảng được tạo bằng `TEMP TABLE` để chỉ tồn tại trong **phiên kết nối** học tập; nếu mở kết nối mới, bạn phải tạo lại.

### 3.1. Tạo bảng đơn hàng

~~~sql
CREATE TEMP TABLE idx324_don_hang (
    id INTEGER PRIMARY KEY,
    customer_id INTEGER NOT NULL,
    status TEXT NOT NULL
        CHECK (status IN ('NEW', 'PAID', 'CANCELLED')),
    created_at TIMESTAMP NOT NULL,
    total NUMERIC(12,2) NOT NULL
        CHECK (total >= 0),
    region TEXT,
    archived_at TIMESTAMP,
    code TEXT NOT NULL UNIQUE
);
~~~

Một hàng đại diện cho **một đơn hàng**:

- `id`: khóa chính.
- `customer_id`: mã khách hàng.
- `status`: trạng thái đơn.
- `created_at`: thời điểm tạo đơn, dùng kiểu TIMESTAMP không kèm múi giờ để dễ thực hành.
- `total`: tổng tiền đơn.
- `region`: khu vực, có thể NULL.
- `archived_at`: thời điểm lưu trữ, NULL khi chưa lưu trữ.
- `code`: mã đơn duy nhất, ví dụ `ORD-00005`.

PRIMARY KEY và UNIQUE tự tạo những cơ chế chỉ mục thích hợp ở PostgreSQL. Ta sẽ chủ động tạo thêm chỉ mục cho các **mẫu truy vấn nghiệp vụ**, không coi chỉ mục PK trên `id` là câu trả lời cho mọi truy vấn.

### 3.2. Nạp 25 đơn hàng mẫu

~~~sql
INSERT INTO idx324_don_hang
    (id, customer_id, status, created_at, total, region, code)
SELECT
    v.id,
    v.customer_id,
    v.status,
    v.created_text::TIMESTAMP,
    v.total,
    v.region,
    'ORD-' || LPAD(v.id::TEXT, 5, '0')
FROM (
    VALUES
        ( 1, 10, 'NEW',       '2026-10-01 09:00:00', 120, 'BAC'),
        ( 2, 10, 'PAID',      '2026-10-05 15:00:00', 200, 'BAC'),
        ( 3, 10, 'PAID',      '2026-10-05 15:00:00', 300, 'BAC'),
        ( 4, 10, 'CANCELLED', '2026-10-06 12:00:00',  80, 'BAC'),
        ( 5, 10, 'PAID',      '2026-10-12 09:00:00', 500, 'BAC'),

        ( 6, 20, 'NEW',       '2026-10-01 11:00:00',  90, 'NAM'),
        ( 7, 20, 'PAID',      '2026-10-04 08:00:00', 300, 'NAM'),
        ( 8, 20, 'PAID',      '2026-10-09 09:00:00', 180, 'NAM'),
        ( 9, 20, 'PAID',      '2026-10-20 14:00:00', 230, 'NAM'),
        (10, 20, 'CANCELLED', '2026-11-02 17:00:00',  60, 'NAM'),

        (11, 30, 'NEW',       '2026-10-07 10:00:00', 110, 'TRUNG'),
        (12, 30, 'PAID',      '2026-10-10 10:00:00', 130, 'TRUNG'),
        (13, 30, 'PAID',      '2026-10-18 18:00:00', 350, 'TRUNG'),
        (14, 30, 'PAID',      '2026-11-03 10:00:00', 220, 'TRUNG'),

        (15, 40, 'NEW',       '2026-10-13 10:00:00', 150, 'BAC'),
        (16, 40, 'PAID',      '2026-10-15 10:00:00', 400, 'BAC'),
        (17, 40, 'PAID',      '2026-10-21 10:00:00', 310, 'BAC'),
        (18, 40, 'PAID',      '2026-11-01 09:00:00', 700, 'BAC'),

        (19, 50, 'PAID',      '2026-10-11 10:00:00',  40, 'NAM'),
        (20, 50, 'PAID',      '2026-10-16 10:00:00', 450, 'NAM'),
        (21, 50, 'NEW',       '2026-10-22 10:00:00', 200, 'NAM'),
        (22, 50, 'PAID',      '2026-11-04 12:00:00', 600, 'NAM'),

        (23, 60, 'NEW',       '2026-10-03 10:00:00', 100, 'TRUNG'),
        (24, 60, 'PAID',      '2026-10-30 10:00:00', 270, 'TRUNG'),
        (25, 60, 'PAID',      '2026-11-08 10:00:00', 390, NULL)
) AS v(id, customer_id, status, created_text, total, region);
~~~

Điểm được cố ý đưa vào bộ dữ liệu:

- Khách `10` có hai đơn PAID **cùng thời điểm**: ID 2 và 3. Ta sẽ dùng `id` phá hòa khi sắp xếp và phân trang.
- Khách `20` có đơn NEW, PAID và CANCELLED.
- Một số đơn ở tháng 11 để kiểm tra khoảng tháng 10.
- Đơn ID 25 có `region IS NULL` để thực hành điều kiện NULL.
- Cột `status` có một số ít giá trị khác nhau, trong khi `customer_id` có nhiều giá trị phân nhóm hơn.

### 3.3. Đánh dấu hai đơn đã lưu trữ

~~~sql
UPDATE idx324_don_hang
SET archived_at = TIMESTAMP '2026-11-10 00:00:00'
WHERE id IN (4, 10);
~~~

Như vậy, ban đầu chỉ có **hai hàng archived_at khác NULL**. Phần partial index sẽ lọc các đơn chưa lưu trữ bằng `archived_at IS NULL`.

### 3.4. Cập nhật thống kê

~~~sql
ANALYZE idx324_don_hang;
~~~

PostgreSQL cần thống kê để ước lượng số hàng và chọn kế hoạch. Đối với **bảng tạm**, bạn nên chủ động ANALYZE trong phiên thực hành khi muốn kiểm tra planner; quá trình auto-analyze không xử lý bảng tạm theo cách bảng thường.

### 3.5. Kiểm tra tổng quan dữ liệu

~~~sql
SELECT
    status,
    COUNT(*) AS so_don
FROM idx324_don_hang
GROUP BY status
ORDER BY status;
~~~

Kỳ vọng:

| status | so_don |
|---|---:|
| CANCELLED | 2 |
| NEW | 6 |
| PAID | 17 |

~~~sql
SELECT
    customer_id,
    COUNT(*) AS so_don
FROM idx324_don_hang
GROUP BY customer_id
ORDER BY customer_id;
~~~

Kỳ vọng: khách 10 có 5 đơn, 20 có 5, 30 có 4, 40 có 4, 50 có 4, 60 có 3; tổng **25 đơn**.

~~~sql
SELECT COUNT(*) AS so_don_thang_10
FROM idx324_don_hang
WHERE created_at >= TIMESTAMP '2026-10-01'
  AND created_at <  TIMESTAMP '2026-11-01';
~~~

Kỳ vọng: **20 đơn** thuộc tháng 10.

**Lưu ý về kế hoạch:** 25 hàng là quá nhỏ để so sánh đáng tin cậy hiệu năng giữa các chỉ mục. PostgreSQL có thể chọn `Seq Scan` vì đọc hết bảng ít tốn chi phí hơn đi qua B-tree. Ta dùng bảng nhỏ để **hiểu kết quả logic**, còn phần EXPLAIN và bộ dữ liệu lớn minh họa cách **kiểm chứng hiệu năng**.

## 4. Bắt đầu từ mẫu truy vấn, không bắt đầu từ “cột nào cần index?”

Giả sử hệ thống có các yêu cầu:

**Mẫu A:** lịch sử đơn PAID của một khách, mới nhất trước:

~~~sql
SELECT id, created_at, total
FROM idx324_don_hang
WHERE customer_id = 10
  AND status = 'PAID'
ORDER BY created_at DESC, id DESC
LIMIT 10;
~~~

**Mẫu B:** toàn bộ đơn PAID trong tháng 10:

~~~sql
SELECT id, customer_id, created_at
FROM idx324_don_hang
WHERE status = 'PAID'
  AND created_at >= TIMESTAMP '2026-10-01'
  AND created_at <  TIMESTAMP '2026-11-01'
ORDER BY created_at DESC, id DESC;
~~~

**Mẫu C:** mọi trạng thái của một khách, sắp theo ngày tạo:

~~~sql
SELECT id, status, created_at
FROM idx324_don_hang
WHERE customer_id = 10
ORDER BY created_at DESC, id DESC;
~~~

**Mẫu D:** truy vấn theo thời điểm tạo, không phân khách hoặc trạng thái:

~~~sql
SELECT id, customer_id, status, created_at
FROM idx324_don_hang
WHERE created_at >= TIMESTAMP '2026-11-01'
ORDER BY created_at DESC;
~~~

Bốn mẫu này không được phục vụ tối ưu như nhau bởi một chỉ mục duy nhất. **Cần biết các mẫu thực sự quan trọng, tần suất, khối lượng, độ trễ yêu cầu và tỷ lệ dữ liệu** rồi mới chọn chỉ mục.

### 4.1. Ma trận truy vấn

| Mẫu | Điều kiện bằng | Điều kiện khoảng | Sắp xếp | Gợi ý thứ tự khóa |
|---|---|---|---|---|
| A | `customer_id`, `status` | Không hoặc `created_at` | `created_at DESC, id DESC` | `(customer_id, status, created_at DESC, id DESC)` |
| B | `status` | `created_at` | `created_at DESC, id DESC` | `(status, created_at DESC, id DESC)` |
| C | `customer_id` | Không | `created_at DESC, id DESC` | `(customer_id, created_at DESC, id DESC)` |
| D | Không | `created_at` | `created_at DESC` | `(created_at DESC)` hoặc dạng khác theo workload |

Đây là **ứng viên cần thử** chứ không phải yêu cầu tạo cả bốn chỉ mục. Trên hệ thống có nhiều INSERT/UPDATE/DELETE, bốn chỉ mục mới có thể gây chi phí ghi và dung lượng đáng kể.

## 5. Chỉ mục tổng hợp: điều kiện bằng ở tiền tố trái

Tạo chỉ mục ứng viên cho mẫu A:

~~~sql
CREATE INDEX idx324_customer_status_created
ON idx324_don_hang (
    customer_id,
    status,
    created_at DESC,
    id DESC
);
~~~

Một truy vấn rất phù hợp:

~~~sql
SELECT
    id,
    customer_id,
    status,
    created_at,
    total
FROM idx324_don_hang
WHERE customer_id = 10
  AND status = 'PAID'
  AND created_at >= TIMESTAMP '2026-10-01'
  AND created_at <  TIMESTAMP '2026-11-01'
ORDER BY created_at DESC, id DESC;
~~~

Kết quả trên dữ liệu mẫu:

| id | customer_id | status | created_at |
|---:|---:|---|---|
| 5 | 10 | PAID | 2026-10-12 09:00:00 |
| 3 | 10 | PAID | 2026-10-05 15:00:00 |
| 2 | 10 | PAID | 2026-10-05 15:00:00 |

### 5.1. Đọc cấu trúc truy vấn

~~~text
INDEX(customer_id, status, created_at DESC, id DESC)
      │             │          │               │
      =10           ='PAID'    >= và <        phá hòa ORDER BY
      └──── hai điều kiện bằng ở đầu ────┘
~~~

- `customer_id = 10` chọn một nhóm khách.
- `status = 'PAID'` chọn nhóm trạng thái bên trong khách ấy.
- `created_at >= ... AND created_at < ...` chọn khoảng thời điểm trong nhóm nhỏ.
- `ORDER BY created_at DESC, id DESC` cùng chiều với khóa sắp xếp còn lại.

Với dữ liệu phân bố phù hợp, chỉ mục có thể giúp **lọc và trả thứ tự** mà không cần sort lớn.

### 5.2. Vì sao ID đứng cuối?

Ngày và giờ tạo có thể trùng nhau (ID 2 và 3). Nếu chỉ `ORDER BY created_at DESC`, hai hàng trùng thời điểm không có thứ tự ổn định theo yêu cầu ứng dụng.

Thêm `id DESC` giúp:

- Kết quả xác định giữa các hàng cùng `created_at`.
- Phân trang theo cursor ổn định hơn.
- Khớp với thứ tự trong chỉ mục.

Đừng xem chỉ mục tự tạo một thứ tự “ngẫu nhiên nhưng đủ dùng” cho các hàng bằng khóa nếu ORDER BY không diễn đạt rõ quy tắc phá hòa.

### 5.3. Thứ tự cột trong WHERE không cần giống thứ tự index

Hai câu WHERE tương đương về logic:

~~~sql
WHERE customer_id = 10
  AND status = 'PAID'
~~~

và:

~~~sql
WHERE status = 'PAID'
  AND customer_id = 10
~~~

Thông thường optimizer có thể nhận ra chúng là cùng các điều kiện bằng nhau. **Thứ tự viết AND trong WHERE không làm đổi cấu trúc chỉ mục**. Điều quan trọng là cột nào xuất hiện ở **vị trí nào trong CREATE INDEX** và kiểu điều kiện của nó.

## 6. Quy tắc tiền tố trái (leftmost prefix)

Với B-tree:

~~~sql
(customer_id, status, created_at)
~~~

một cách khái quát, các trường hợp sau có lợi thế tra cứu khác nhau:

| Predicate | Tiền tố có thể dùng thuận lợi theo quy tắc cơ bản |
|---|---|
| `customer_id = 10` | Cột đầu |
| `customer_id = 10 AND status = 'PAID'` | Hai cột đầu |
| `customer_id = 10 AND status = 'PAID' AND created_at >= ...` | Hai bằng, rồi khoảng cột ba |
| `status = 'PAID'` | Thiếu cột đầu, ít thuận lợi theo mô hình tiền tố thường |
| `created_at >= ...` | Thiếu hai cột đầu, ít thuận lợi theo mô hình tiền tố thường |
| `customer_id = 10 AND created_at >= ...` | Dùng tiền tố `customer_id`; thiếu cột `status` ở giữa |

Trong PostgreSQL, mô tả chính xác hơn là: các ràng buộc **bằng trên các cột dẫn đầu** và bất đẳng thức đầu tiên trên cột tiếp theo thường quyết định phạm vi có thể quét liên tục. Điều kiện ở những cột sau vẫn có thể được kiểm tra ngay trong quá trình quét index, nhưng không nhất thiết thu hẹp đáng kể phạm vi đã đọc.

### 6.1. Thiếu cột ở giữa

~~~sql
SELECT id, status, created_at
FROM idx324_don_hang
WHERE customer_id = 10
  AND created_at >= TIMESTAMP '2026-10-05'
ORDER BY created_at DESC;
~~~

Với index `(customer_id, status, created_at)`:

- `customer_id = 10` hữu ích.
- Không có điều kiện cố định `status`.
- Các dòng của khách 10 vẫn được nhóm theo `status` trước khi sắp theo `created_at`.
- Do đó index này **không mặc nhiên đáp ứng ORDER BY created_at DESC** cho toàn bộ khách 10.

Trong trường hợp cần truy vấn này thường xuyên, index `(customer_id, created_at DESC)` có thể phù hợp hơn.

### 6.2. Ngoại lệ quan trọng: skip scan và lựa chọn của optimizer

Một số phiên bản/cơ chế PostgreSQL có thể sử dụng **skip scan** với B-tree nhiều cột: lặp việc tìm kiếm theo những giá trị của cột dẫn đầu chưa được cố định để tận dụng điều kiện của cột sau. Khả năng và lợi ích phụ thuộc phiên bản, số lượng giá trị phân biệt, phân bố và chi phí.

Ngoài ra, planner còn có thể quét cả index rồi lọc, hoặc chọn `Bitmap Index Scan`/`Seq Scan`. Vì vậy, quy tắc tiền tố trái nên được hiểu là **nguyên lý thiết kế khả năng thu hẹp phạm vi truy cập**, không phải câu luật “thiếu cột đầu thì PostgreSQL tuyệt đối không thể dùng index”.

### 6.3. Vì sao số giá trị phân biệt ở cột đầu quan trọng?

Nếu cột dẫn đầu có rất ít giá trị phân biệt, một số kỹ thuật quét bỏ qua nhóm có thể khả thi hơn. Nếu có hàng triệu giá trị phân biệt, việc lặp tìm kiếm theo từng nhóm có thể không kinh tế.

Đây là một trong những lý do phải có **thống kê và EXPLAIN trên dữ liệu thật**, thay vì áp dụng máy móc một mẹo duy nhất cho mọi database.

## 7. Điều kiện bằng, điều kiện khoảng và thứ tự cột

Mẫu phổ biến:

~~~sql
WHERE a = ?
  AND b = ?
  AND c >= ?
  AND c < ?
~~~

Một ứng viên tự nhiên:

~~~sql
(a, b, c)
~~~

Vì các điều kiện bằng nhau ở đầu xác định nhóm, còn khoảng trên `c` giới hạn phạm vi trong nhóm.

### 7.1. Ví dụ so sánh

Giả sử một truy vấn thường chạy:

~~~sql
SELECT id, created_at
FROM idx324_don_hang
WHERE customer_id = 20
  AND status = 'PAID'
  AND created_at >= TIMESTAMP '2026-10-01'
  AND created_at <  TIMESTAMP '2026-11-01';
~~~

Tập kết quả: ID **7, 8, 9** (không xét thứ tự nếu SELECT không ORDER BY).

Ứng viên:

~~~sql
(customer_id, status, created_at)
~~~

thường phù hợp với điều kiện **bằng–bằng–khoảng**.

Đổi thành:

~~~sql
(created_at, customer_id, status)
~~~

thì khoảng thời gian nằm ngay cột đầu; nếu tháng 10 chiếm rất nhiều dữ liệu, index có thể phải xét nhiều đơn trong khoảng trước khi lọc xuống đúng khách và trạng thái.

### 7.2. Một điều kiện khoảng đặt trước cột bằng có thể làm giảm hiệu quả lọc

Xét:

~~~sql
(customer_id, created_at, status)
~~~

với:

~~~sql
WHERE customer_id = 20
  AND created_at >= TIMESTAMP '2026-10-01'
  AND created_at <  TIMESTAMP '2026-11-01'
  AND status = 'PAID'
~~~

B-tree vẫn có thể kiểm tra `status = 'PAID'` trong index. Nhưng vì `created_at` là khoảng thay đổi, `status` ở phía sau thường không còn thu hẹp phạm vi quét giống trường hợp `status` là điều kiện bằng đứng trước khoảng.

**Nguyên tắc thực hành:** nếu một truy vấn dùng điều kiện bằng ở một số cột và khoảng ở một cột, hãy **thử** đưa các cột bằng cần thiết lên trước, rồi cột khoảng. Sau đó xem yêu cầu ORDER BY và những truy vấn khác trước khi chốt.

### 7.3. Không phải mọi so sánh đều đơn giản thành “= hay range”

`IN`, `IS NULL`, `IS NOT DISTINCT FROM`, `LIKE` có tiền tố, so sánh hàng và các biểu thức phức tạp có hành vi tối ưu khác nhau. Khi lựa chọn thứ tự cột, cần biết **toán tử và operator class** mà index hỗ trợ, không chỉ nhìn tên cột.

## 8. Có nên luôn đặt cột chọn lọc nhất đầu tiên?

**Không.** Lời khuyên “cột có độ chọn lọc cao nhất lên đầu” có thể hữu ích trong một số tình huống, nhưng không phải quy tắc tối ưu chung cho B-tree tổng hợp.

### 8.1. Độ chọn lọc là gì?

Một điều kiện có độ chọn lọc cao khi nó giữ **ít hàng** trong bảng.

Ví dụ trên 25 đơn mẫu:

- `status = 'PAID'` giữ 17/25 đơn → không quá chọn lọc.
- `customer_id = 60` giữ 3/25 đơn → chọn lọc hơn trên tập nhỏ này.
- `id = 5` giữ 1/25 đơn → rất chọn lọc, nhưng PRIMARY KEY đã có index.

Độ chọn lọc phụ thuộc **giá trị cụ thể, phân bố và thống kê**, không chỉ tên kiểu dữ liệu.

### 8.2. Hai cột đều có điều kiện bằng

Nếu một truy vấn **luôn** có:

~~~sql
WHERE customer_id = 10
  AND status = 'PAID'
~~~

cả hai chỉ mục:

~~~sql
(customer_id, status)
(status, customer_id)
~~~

đều có hai điều kiện bằng trên hai cột đầu, nên cùng có thể xác định vùng khóa tương ứng. Không có lý do đơn giản để bảo đảm một thứ tự luôn thắng chỉ dựa trên độ chọn lọc từng cột.

Nhưng:

- `(customer_id, status)` hỗ trợ thêm mẫu **chỉ lọc customer_id**.
- `(status, customer_id)` hỗ trợ thêm mẫu **chỉ lọc status**.
- Nếu còn `created_at` và ORDER BY, vị trí các cột trở nên quan trọng hơn.

### 8.3. Câu hỏi đúng là “workload cần tiền tố nào?”

Nếu ứng dụng gần như luôn tải **đơn của một khách**, `customer_id` ở đầu có lợi về khả năng dùng lại tiền tố.

Nếu ứng dụng thường xuyên chạy báo cáo **mọi đơn PAID gần đây**, `status` hoặc `created_at` ở đầu có thể phù hợp hơn.

Nếu có cả hai workload quan trọng, bạn có thể cần **hai chỉ mục khác nhau**, hoặc thay đổi cách tổ chức truy vấn, partial index, bảng báo cáo riêng... sau khi cân nhắc chi phí thực tế.

### 8.4. Cột trạng thái ít giá trị không mặc nhiên vô dụng

`status` chỉ có ba giá trị nhưng có thể vẫn hữu ích trong index `(status, created_at)` khi:

- Điều kiện status xác định một nhóm cần báo cáo.
- Điều kiện created_at thu hẹp mạnh phạm vi trong nhóm.
- Kết quả cần ORDER BY created_at.
- Truy vấn chạy nhiều và `LIMIT` nhỏ.

Ngược lại, chỉ mục một cột `status` cho một tập trong đó PAID chiếm đa số có thể không đủ lợi thế để planner bỏ qua `Seq Scan`.

## 9. Mẫu lọc trạng thái trước, thời gian sau

Với báo cáo tất cả đơn PAID trong tháng 10, không có điều kiện khách hàng:

~~~sql
SELECT
    id,
    customer_id,
    created_at
FROM idx324_don_hang
WHERE status = 'PAID'
  AND created_at >= TIMESTAMP '2026-10-01'
  AND created_at <  TIMESTAMP '2026-11-01'
ORDER BY created_at DESC, id DESC;
~~~

Kết quả: **13 đơn PAID** trong tháng 10 trên bộ dữ liệu mẫu.

Ứng viên:

~~~sql
CREATE INDEX idx324_status_created
ON idx324_don_hang (
    status,
    created_at DESC,
    id DESC
);
~~~

### 9.1. Vì sao chỉ mục customer-first không phải ứng viên chính?

Index đã tạo trước:

~~~sql
(customer_id, status, created_at DESC, id DESC)
~~~

sắp theo từng khách trước. Trong mỗi khách, status và thời điểm mới được xét; tổng hợp đơn PAID của **mọi khách** không có `customer_id` cố định nên thứ tự ngày không tạo thành một dãy toàn cục đơn giản.

Index `(status, created_at DESC, id DESC)` phù hợp hơn với truy vấn không phân khách vì sau `status = 'PAID'`, các khóa theo thời gian đã liền nhau.

### 9.2. Có cần thêm customer_id cuối không?

Nếu truy vấn luôn trả `customer_id`, có thể xét:

~~~sql
CREATE INDEX idx324_status_created_cover
ON idx324_don_hang (
    status,
    created_at DESC,
    id DESC
)
INCLUDE (customer_id);
~~~

`customer_id` ở `INCLUDE` là cột **payload**. Nó có thể giúp index-only scan nếu các điều kiện khác phù hợp, nhưng **không trở thành cột khóa dùng để tìm kiếm/sắp xếp**. Phần sau phân tích kỹ hơn.

### 9.3. Không tạo trùng mọi index ứng viên ở production

Các CREATE INDEX trong bài là ví dụ để so sánh. Việc có đồng thời `idx324_status_created` và `idx324_status_created_cover` trên một bảng nhỏ là không cần thiết trong ứng dụng thật; hãy đánh giá, chọn cấu trúc phù hợp và loại index chồng lấn không mang lại lợi ích.

## 10. Mẫu lọc theo khách, mọi trạng thái, sắp theo thời gian

Xét yêu cầu lịch sử **toàn bộ đơn của khách 10**:

~~~sql
SELECT
    id,
    status,
    created_at,
    total
FROM idx324_don_hang
WHERE customer_id = 10
ORDER BY created_at DESC, id DESC;
~~~

Tập kết quả (theo thứ tự mong muốn):

| id | status | created_at |
|---:|---|---|
| 5 | PAID | 2026-10-12 09:00 |
| 4 | CANCELLED | 2026-10-06 12:00 |
| 3 | PAID | 2026-10-05 15:00 |
| 2 | PAID | 2026-10-05 15:00 |
| 1 | NEW | 2026-10-01 09:00 |

### 10.1. Vì sao (customer_id, status, created_at) có thể phải SORT?

Sau `customer_id = 10`, index ấy sắp các dòng theo `status` trước, rồi mới theo `created_at` trong mỗi nhóm status.

Nhưng truy vấn cần tất cả các trạng thái **trộn chung và sắp theo created_at**. Vì thế, thứ tự index không tự thỏa ORDER BY.

Ứng viên phù hợp hơn:

~~~sql
CREATE INDEX idx324_customer_created
ON idx324_don_hang (
    customer_id,
    created_at DESC,
    id DESC
);
~~~

Với một customer cụ thể, hai khóa sau trực tiếp biểu diễn thứ tự cần hiển thị.

### 10.2. Hai index có cùng một số cột nhưng phục vụ hai mẫu

| Index | Tốt cho mẫu nào? |
|---|---|
| `(customer_id, status, created_at DESC, id DESC)` | Khách + trạng thái cụ thể + thời gian |
| `(customer_id, created_at DESC, id DESC)` | Toàn bộ trạng thái của khách + thời gian |

Nếu truy vấn mẫu A hiếm nhưng mẫu C rất phổ biến, việc giữ index thứ nhất vì nó “có nhiều cột hơn” không phải lựa chọn mặc nhiên.

### 10.3. Cột dư không luôn giúp

Một index có thêm cột `status` vào giữa có thể làm **mất khả năng đáp ứng trực tiếp thứ tự theo created_at** cho truy vấn không lọc status.

Đây là ví dụ điển hình rằng **nhiều cột không đồng nghĩa nhiều lợi ích hơn**. Thứ tự cột quan trọng ít nhất bằng việc có cột nào.

## 11. ORDER BY kết hợp LIMIT: chỉ mục còn phục vụ việc dừng sớm

Một truy vấn giao diện thường chỉ lấy mười đơn mới nhất:

~~~sql
SELECT
    id,
    created_at,
    total
FROM idx324_don_hang
WHERE customer_id = 10
  AND status = 'PAID'
ORDER BY created_at DESC, id DESC
LIMIT 10;
~~~

Nếu một index phù hợp cả lọc lẫn thứ tự, PostgreSQL có thể đi theo index và **dừng khi đã đủ số hàng thỏa yêu cầu**, thay vì quét/lọc và sắp toàn bộ kết quả trước.

### 11.1. Trường hợp có filter bổ sung

Giả sử:

~~~sql
WHERE customer_id = 10
  AND status = 'PAID'
  AND total >= 300
ORDER BY created_at DESC, id DESC
LIMIT 10
~~~

Với index `(customer_id, status, created_at DESC, id DESC)`, cột `total` không ở phần khóa. PostgreSQL có thể phải đọc/kiểm tra thêm các hàng trước khi đủ 10 đơn có `total >= 300`.

Nếu `total` là điều kiện lọc thường xuyên và chọn lọc mạnh, có thể cần cấu trúc khác, nhưng việc đặt `total` trước `created_at` sẽ ảnh hưởng đến khả năng trả `ORDER BY created_at`. Chọn index phải cân bằng giữa **lọc mạnh** và **sắp xếp/dừng sớm**.

### 11.2. Không có ORDER BY thì LIMIT không có ý nghĩa “mới nhất”

~~~sql
SELECT *
FROM idx324_don_hang
WHERE customer_id = 10
LIMIT 3;
~~~

Câu này không bảo đảm lấy ba đơn mới nhất; thứ tự trả về có thể thay đổi theo kế hoạch. Muốn “mới nhất”, phải có `ORDER BY created_at DESC, id DESC`.

## 12. ASC, DESC, NULLS FIRST/LAST và chỉ mục tổng hợp

PostgreSQL B-tree có thể được duyệt xuôi hoặc ngược. Với **một cột sắp xếp**, index tăng dần có thể hỗ trợ cả thứ tự tăng và giảm thông qua chiều quét tương ứng.

Nhưng với **nhiều cột có hướng trộn nhau**, lựa chọn thứ tự khóa có thể quan trọng.

### 12.1. Hai cột cùng chiều

~~~sql
ORDER BY created_at DESC, id DESC
~~~

Ứng viên:

~~~sql
(customer_id, created_at DESC, id DESC)
~~~

sau `customer_id = ?` có thể trả đúng thứ tự, và một số cấu hình index chiều ngược đồng nhất cũng có thể được quét ngược để đáp ứng.

### 12.2. Hai cột khác chiều

~~~sql
ORDER BY created_at DESC, id ASC
~~~

Nếu đây là mẫu quan trọng, index cụ thể:

~~~sql
CREATE INDEX idx324_customer_mixed_sort
ON idx324_don_hang (
    customer_id,
    created_at DESC,
    id ASC
);
~~~

có thể hữu ích. Một lần quét ngược toàn bộ index `(created_at ASC, id ASC)` thường đảo **cả hai hướng**, không tự biến thành `created_at DESC, id ASC`.

### 12.3. Cột có NULL

`created_at` trong bộ dữ liệu là NOT NULL, nhưng `region` có thể NULL. Nếu báo cáo dùng:

~~~sql
ORDER BY region ASC NULLS LAST
~~~

cần biết quy tắc NULLS của DBMS. Trong PostgreSQL, thứ tự NULL mặc định gắn với hướng ASC/DESC; index có thể khai báo rõ:

~~~sql
CREATE INDEX idx324_region_order
ON idx324_don_hang (region ASC NULLS LAST);
~~~

Nếu truy vấn yêu cầu `DESC NULLS LAST` và nhiều cột khác, nên đối chiếu chính xác thứ tự/index direction. Tuy nhiên, thứ tự NULL không thay đổi bản chất: **cột khóa bên trái vẫn quyết định nhóm trước các cột sau**.

## 13. WHERE IN, nhiều nhóm bằng nhau và thứ tự toàn cục

Một predicate:

~~~sql
WHERE status IN ('NEW', 'PAID')
~~~

tương tự việc chọn **nhiều giá trị** của cột status. Với index:

~~~sql
(status, created_at DESC)
~~~

các dòng NEW và PAID nằm trong **hai nhóm status riêng**.

Nếu truy vấn:

~~~sql
SELECT id, status, created_at
FROM idx324_don_hang
WHERE status IN ('NEW', 'PAID')
ORDER BY created_at DESC, id DESC;
~~~

nó yêu cầu trộn cả hai nhóm theo ngày. Index sắp nhóm status trước không tự bảo đảm thứ tự ngày toàn cục; PostgreSQL có thể cần Sort hoặc cách gộp các luồng theo kế hoạch phù hợp.

### 13.1. IN trên cột dẫn đầu vẫn có thể hữu ích

Điều kiện IN không làm index trở nên vô dụng. Planner có thể thực hiện các lần tra cứu/range phù hợp cho các giá trị thuộc tập IN, hoặc dùng bitmap/plan khác.

Nhưng khi **ORDER BY không gồm status**, cần xét việc kết quả từ nhiều giá trị status phải được sắp lại.

### 13.2. Ví dụ với khách hàng

~~~sql
SELECT id, customer_id, created_at
FROM idx324_don_hang
WHERE customer_id IN (10, 20)
ORDER BY created_at DESC, id DESC;
~~~

Index `(customer_id, created_at DESC)` có thể giúp tìm hai nhóm khách, nhưng kết quả của hai nhóm **không tự** là một dãy theo created_at toàn cục. Đừng nhầm “có ORDER BY trong cấu trúc index” với “index đáp ứng mọi ORDER BY bất kể cột đứng đầu có nhiều giá trị”.

## 14. Điều kiện khoảng thời gian và cột được biến đổi bằng hàm

Một mẫu phổ biến:

~~~sql
WHERE created_at >= TIMESTAMP '2026-10-01'
  AND created_at <  TIMESTAMP '2026-11-01'
~~~

Đây là khoảng **nửa mở**: gồm từ đầu tháng 10 đến trước đầu tháng 11.

### 14.1. Vì sao không chỉ dùng BETWEEN với ngày cuối?

~~~sql
WHERE created_at BETWEEN
      TIMESTAMP '2026-10-01'
  AND TIMESTAMP '2026-10-31'
~~~

Với cột TIMESTAMP chứa giờ phút, giới hạn `2026-10-31 00:00:00` không bao gồm phần lớn ngày 31/10. Khoảng nửa mở tới `2026-11-01` dễ đúng hơn và phù hợp với range scan trên index thời điểm.

### 14.2. Hàm áp lên cột có thể làm khó dùng index thường

~~~sql
WHERE created_at::DATE = DATE '2026-10-05'
~~~

Một index thông thường trên `created_at` lưu giá trị thời điểm, không trực tiếp lưu biểu thức `created_at::DATE`. Planner có thể phải quét và tính biểu thức hoặc chọn plan khác.

Viết lại:

~~~sql
WHERE created_at >= TIMESTAMP '2026-10-05'
  AND created_at <  TIMESTAMP '2026-10-06'
~~~

thường phù hợp hơn với B-tree trên `created_at` vì so sánh trực tiếp vào cột.

### 14.3. Nếu nghiệp vụ luôn lọc theo ngày, có thể dùng expression index

Với cột TIMESTAMP **không kèm múi giờ** như bộ dữ liệu:

~~~sql
CREATE INDEX idx324_created_day_expr
ON idx324_don_hang ((created_at::DATE));
~~~

Khi đó một truy vấn có biểu thức tương ứng có thể tận dụng index:

~~~sql
SELECT id, created_at
FROM idx324_don_hang
WHERE created_at::DATE = DATE '2026-10-05';
~~~

Nhưng expression index tăng chi phí lưu trữ và ghi. Nếu biểu thức chỉ xuất hiện thỉnh thoảng, viết khoảng thời gian trên index gốc có thể hợp lý hơn.

**Lưu ý:** ép `TIMESTAMPTZ` sang DATE phụ thuộc múi giờ của phiên, không cùng tính chất bất biến như ép TIMESTAMP không múi giờ. Không sao chép nguyên expression index này cho mọi kiểu cột mà chưa kiểm tra tính immutable và ngữ nghĩa ngày nghiệp vụ.

## 15. OR và khả năng kết hợp nhiều chỉ mục

Xem truy vấn:

~~~sql
SELECT id, customer_id, status
FROM idx324_don_hang
WHERE customer_id = 10
   OR status = 'CANCELLED';
~~~

Hai điều kiện nằm trên **hai cột khác nhau** với OR.

PostgreSQL có thể cân nhắc:

- `Seq Scan` rồi lọc.
- Một kế hoạch bitmap kết hợp nhiều index, chẳng hạn `BitmapOr` giữa các bitmap index scan khi có index phù hợp.
- Một kế hoạch khác tùy thống kê và chi phí.

### 15.1. Composite index không tự giải mọi OR

Một index:

~~~sql
(customer_id, status)
~~~

được tổ chức tốt cho `customer_id = ? AND status = ?`, nhưng OR “khách 10 **hoặc** bất kỳ đơn CANCELLED” là tập hợp của hai vùng dữ liệu khác nhau.

Có thể cần hai index một cột, hoặc hai ứng viên phù hợp hai nhánh, nhưng nếu phần lớn bảng được chọn, Seq Scan vẫn có thể rẻ hơn.

### 15.2. Đừng biến OR thành AND

~~~sql
WHERE customer_id = 10
  AND status = 'CANCELLED'
~~~

khác hoàn toàn:

~~~sql
WHERE customer_id = 10
   OR status = 'CANCELLED'
~~~

Câu đầu chỉ chọn đơn CANCELLED của khách 10; câu sau chọn **mọi đơn của khách 10 và mọi đơn CANCELLED của mọi khách**. Thay đổi logic để “dùng index nhanh hơn” là sai nếu nó làm khác yêu cầu nghiệp vụ.

### 15.3. OR trên cùng một cột

~~~sql
WHERE status = 'NEW'
   OR status = 'PAID'
~~~

có thể biểu diễn gọn bằng:

~~~sql
WHERE status IN ('NEW', 'PAID')
~~~

Cách này dễ diễn đạt tập giá trị, nhưng việc dùng index và kế hoạch vẫn cần được đo. Không mặc định mọi lần đổi OR thành IN sẽ có kế hoạch giống nhau hoặc luôn nhanh hơn trong mọi DBMS.

## 16. IS NULL và IS NOT NULL

Cột `region` cho phép NULL. Đơn ID 25 có region NULL.

~~~sql
SELECT id, customer_id, region
FROM idx324_don_hang
WHERE region IS NULL;
~~~

Kết quả: **ID 25**.

### 16.1. B-tree PostgreSQL có thể lưu và tìm NULL

Trong PostgreSQL, B-tree có thể hỗ trợ điều kiện `IS NULL` tùy cấu trúc và kế hoạch. Không cần tự kết luận “index không chứa NULL” như một quy tắc chung của mọi DBMS.

Ví dụ ứng viên:

~~~sql
CREATE INDEX idx324_region_created
ON idx324_don_hang (region, created_at DESC);
~~~

Với:

~~~sql
WHERE region IS NULL
ORDER BY created_at DESC
~~~

cột dẫn đầu được lọc ở nhóm NULL, sau đó khóa created_at có thể hỗ trợ thứ tự trong nhóm.

### 16.2. IS NOT NULL thường rộng

Nếu 24/25 đơn có region khác NULL, điều kiện:

~~~sql
WHERE region IS NOT NULL
~~~

chọn gần như toàn bảng. Planner có thể thấy `Seq Scan` kinh tế hơn việc đi qua index. **Có thể dùng index** không đồng nghĩa **nên dùng index**.

### 16.3. Partial index cho dữ liệu có NULL

Nếu hệ thống thường xử lý những đơn chưa lưu trữ:

~~~sql
WHERE archived_at IS NULL
~~~

có thể xây một partial index chỉ chứa hàng đáp ứng predicate đó. Mẫu này hữu ích khi tập hoạt động nhỏ hơn nhiều so với lịch sử, sẽ học ở phần 18.

## 17. LIKE, ILIKE và tiền tố chuỗi

Cột `code` chứa các giá trị như `ORD-00001`, `ORD-00005`.

### 17.1. Tìm đúng mã

~~~sql
SELECT id, code
FROM idx324_don_hang
WHERE code = 'ORD-00005';
~~~

`code` có ràng buộc UNIQUE, nên PostgreSQL đã có index để tìm theo giá trị chính xác; tạo thêm một B-tree giống hệt thường không cần thiết.

### 17.2. LIKE có tiền tố cố định

~~~sql
SELECT id, code
FROM idx324_don_hang
WHERE code LIKE 'ORD-0001%';
~~~

Mẫu này có một tiền tố chuỗi đã biết từ đầu. Trong PostgreSQL, khả năng dùng B-tree cho LIKE prefix phụ thuộc **collation/operator class**. Với các collation không phải C, có thể cần operator class dạng pattern:

~~~sql
CREATE INDEX idx324_code_pattern
ON idx324_don_hang (code text_pattern_ops);
~~~

Đây là index **ứng viên bổ sung** nếu workload thật thường tìm theo tiền tố và index UNIQUE hiện có không đáp ứng tốt điều kiện/collation đó.

### 17.3. LIKE có wildcard ở đầu

~~~sql
WHERE code LIKE '%0005'
~~~

B-tree theo chuỗi thường **không thể nhảy tới một dãy liên tục chỉ từ hậu tố**. Nếu tìm chuỗi con/hậu tố là nghiệp vụ phổ biến, PostgreSQL có thể dùng extension `pg_trgm` và chỉ mục GIN/GiST phù hợp, khi extension có sẵn và các điều kiện áp dụng cho toán tử được hỗ trợ.

Không nên thêm extension và nhiều index chỉ để tối ưu một truy vấn hiếm, nhất là khi bảng nhỏ.

### 17.4. ILIKE và LOWER

~~~sql
WHERE code ILIKE 'ord-00005'
~~~

là so khớp không phân biệt hoa/thường theo ngữ nghĩa phù hợp. Một index UNIQUE B-tree thông thường trên `code` không mặc nhiên bảo đảm tối ưu mọi ILIKE.

Nếu tìm chính xác nhưng không phân biệt hoa/thường:

~~~sql
SELECT id, code
FROM idx324_don_hang
WHERE LOWER(code) = 'ord-00005';
~~~

có thể dùng expression index:

~~~sql
CREATE INDEX idx324_code_lower
ON idx324_don_hang (LOWER(code));
~~~

Vẫn cần xem liệu có cách chuẩn hóa mã/kiểu cột/collation tốt hơn không. Expression index giải quyết một mẫu biểu thức xác định, không phải mọi truy vấn LIKE/ILIKE tùy ý.

## 18. Partial index: chỉ lưu những hàng phù hợp điều kiện phổ biến

**Partial index** chỉ chứa các hàng thỏa một điều kiện cố định lúc định nghĩa index.

Giả sử hệ thống hiển thị đơn PAID **chưa lưu trữ** của một khách:

~~~sql
SELECT
    id,
    created_at,
    total
FROM idx324_don_hang
WHERE customer_id = 10
  AND status = 'PAID'
  AND archived_at IS NULL
ORDER BY created_at DESC, id DESC;
~~~

Có thể cân nhắc:

~~~sql
CREATE INDEX idx324_paid_active_customer_date
ON idx324_don_hang (
    customer_id,
    created_at DESC,
    id DESC
)
WHERE status = 'PAID'
  AND archived_at IS NULL;
~~~

### 18.1. Vì sao bỏ status khỏi phần khóa?

Mọi hàng **có mặt** trong partial index này đều có `status = 'PAID'` và `archived_at IS NULL`. Vì vậy, đối với truy vấn bị giới hạn đúng như predicate, không cần dành cột khóa đứng trước cho status.

B-tree bên trong partial index được tổ chức chủ yếu theo:

~~~text
customer_id → created_at DESC → id DESC
~~~

trong **tập đơn PAID chưa lưu trữ**, không phải toàn bộ bảng.

### 18.2. Khi nào partial index đáng cân nhắc?

Khi predicate chọn một **tập con nhỏ và được truy cập nhiều**, partial index có thể:

- Chiếm ít dung lượng hơn full index.
- Giảm số mục phải duyệt trong những truy vấn phù hợp.
- Giảm chi phí duy trì các hàng ngoài predicate, tùy kiểu thay đổi.

Trong bộ dữ liệu của bài, 17/25 đơn đều PAID và 23/25 đơn chưa lưu trữ; partial index không tự chứng minh hiệu năng vượt trội. Giá trị của nó cần được kiểm chứng trên phân bố dữ liệu thật.

### 18.3. Truy vấn phải hàm ý predicate của partial index

Truy vấn:

~~~sql
WHERE status = 'PAID'
  AND archived_at IS NULL
  AND customer_id = 10
~~~

hàm ý điều kiện của partial index một cách rõ ràng.

Nhưng:

~~~sql
WHERE customer_id = 10
~~~

không nói status và archived_at; index chỉ có một phần dữ liệu nên không thể là nguồn duy nhất để trả toàn bộ đơn của khách 10.

Tương tự:

~~~sql
WHERE status IN ('NEW', 'PAID')
~~~

không hàm ý chỉ có PAID, nên partial index chỉ chứa PAID không thể đáp ứng toàn bộ tập một mình.

### 18.4. Prepared statements và generic plan

Trong PostgreSQL, điều kiện được tham số hóa:

~~~sql
WHERE status = $1
  AND archived_at IS NULL
~~~

có thể khiến planner ở **generic plan** không chứng minh được rằng mọi giá trị `$1` đều thỏa `status = 'PAID'` của partial index. Một custom plan biết giá trị cụ thể có thể xử lý khác.

Do đó, một partial index nhìn rất phù hợp với câu SQL có literal vẫn có thể không được chọn trong một số prepared statement, tùy kiểu plan và giá trị bind. Hãy kiểm tra kế hoạch **đúng dạng ứng dụng thực thi**, không chỉ EXPLAIN một câu thay tham số bằng hằng số.

### 18.5. Không dùng mốc “NOW()” biến động trong định nghĩa partial index

Predicate partial index phải thỏa các yêu cầu về tính bất biến của biểu thức index. Một điều kiện thay đổi theo thời gian thực như:

~~~sql
WHERE created_at >= NOW() - INTERVAL '7 days'
~~~

không phải cách hợp lệ để tạo một partial index tự luôn đại diện “bảy ngày gần nhất” trong PostgreSQL, vì `NOW()` không immutable.

Nếu cần tối ưu dữ liệu theo thời gian, cân nhắc điều kiện mốc cố định được quản lý theo chính sách, partitioning, BRIN hoặc thiết kế khác phù hợp.

## 19. Covering index và INCLUDE: cột trả về không nhất thiết là khóa

Giả sử màn hình thường hiển thị:

~~~sql
SELECT id, created_at, total, region
FROM idx324_don_hang
WHERE customer_id = 10
  AND status = 'PAID'
ORDER BY created_at DESC, id DESC;
~~~

Ta đã có index trên:

~~~sql
(customer_id, status, created_at DESC, id DESC)
~~~

Nhưng `total` và `region` không nằm trong index đó, nên một kế hoạch Index Scan thông thường có thể cần đọc thêm hàng ở bảng (*heap*) để lấy hai giá trị.

### 19.1. INCLUDE lưu cột payload

~~~sql
CREATE INDEX idx324_customer_paid_cover
ON idx324_don_hang (
    customer_id,
    status,
    created_at DESC,
    id DESC
)
INCLUDE (total, region);
~~~

- Các cột trước `INCLUDE` là **khóa B-tree** để tìm kiếm/sắp xếp.
- `total` và `region` là cột **payload** được lưu kèm, phục vụ truy vấn đọc cột mà không phải đưa chúng vào thứ tự B-tree.
- `INCLUDE` **không biến total thành cột dùng lọc phạm vi** và không hỗ trợ ORDER BY total chỉ vì nó đã được kèm theo.

### 19.2. Index-only scan không phải lúc nào cũng xảy ra

Dù mọi cột SELECT được bao phủ bởi index, PostgreSQL còn phải xem xét **MVCC visibility**. `Index Only Scan` có thể phải truy cập heap để kiểm tra khả năng nhìn thấy hàng nếu visibility map chưa đánh dấu các trang phù hợp là all-visible.

Trên bảng mới INSERT/UPDATE thường xuyên hoặc bảng tạm rất nhỏ, optimizer có thể không chọn Index Only Scan. Vì vậy, INCLUDE **tạo điều kiện**, không bảo đảm “không bao giờ đọc bảng”.

### 19.3. Đánh đổi của INCLUDE

Một index chứa nhiều payload:

- Có thể lớn hơn.
- Tốn thêm I/O và bộ nhớ cache.
- Có thể khiến INSERT/UPDATE phát sinh thêm chi phí.
- Không phải cột nào cũng đáng lưu trong index, đặc biệt cột rất rộng hoặc thay đổi thường xuyên.

Chỉ INCLUDE cột được đọc thường xuyên và có khả năng mang lại lợi ích thực sự theo `EXPLAIN` và phép đo.

### 19.4. Đừng nhầm INCLUDE với phần khóa sau điều kiện khoảng

Index:

~~~sql
(customer_id, status, created_at) INCLUDE (total)
~~~

và:

~~~sql
(customer_id, status, created_at, total)
~~~

không tương đương. Trong index thứ hai, `total` là khóa có thể ảnh hưởng cấu trúc sắp xếp/lọc; trong index thứ nhất, nó chỉ là payload.

## 20. Nhiều chỉ mục đơn cột hay một composite index?

Giả sử có:

~~~sql
CREATE INDEX idx324_customer_only
ON idx324_don_hang (customer_id);

CREATE INDEX idx324_status_only
ON idx324_don_hang (status);

CREATE INDEX idx324_created_only
ON idx324_don_hang (created_at);
~~~

PostgreSQL có thể xét **kết hợp bitmap** giữa các index để đáp ứng các điều kiện AND/OR, hoặc quét một index rồi lọc điều kiện còn lại.

### 20.1. BitmapAnd

Một truy vấn:

~~~sql
WHERE customer_id = 10
  AND status = 'PAID'
~~~

có thể được thực hiện bằng:

- Index Scan trên một index phù hợp.
- Bitmap Index Scan cho customer và status, kết hợp bằng `BitmapAnd` rồi truy cập heap.
- Composite index `(customer_id, status)`.
- Seq Scan nếu đủ rẻ.

**Không có bảo đảm bitmap luôn nhanh hơn composite**. Một composite index phù hợp có thể tiết kiệm công đoạn kết hợp và hỗ trợ ORDER BY mà một bitmap heap scan thường không giữ được thứ tự index.

### 20.2. BitmapOr

Một truy vấn:

~~~sql
WHERE customer_id = 10
   OR status = 'CANCELLED'
~~~

có thể dùng `BitmapOr` giữa hai index phù hợp. Nhưng nếu kết quả bao phủ phần lớn bảng, Seq Scan có thể thắng.

### 20.3. Lợi thế của composite đối với ORDER BY

Một index:

~~~sql
(customer_id, status, created_at DESC, id DESC)
~~~

có thể đáp ứng mẫu lọc hai cột rồi trả kết quả theo thời gian, giảm nhu cầu Sort.

Một tập các index đơn cột không tự bảo toàn thứ tự đó khi kết hợp bitmap. Đây là một lý do quan trọng chọn composite khi truy vấn có **lọc và sắp xếp cùng lúc**.

### 20.4. Khi nào index đơn cột có thể đủ?

- Nhiều truy vấn khác nhau chỉ lọc riêng một cột.
- Các điều kiện kết hợp thay đổi đa dạng.
- Planner có thể kết hợp bitmap tốt.
- Workload ghi cao, chưa đáng tạo quá nhiều composite index cho từng biến thể WHERE.

**Lựa chọn nên dựa trên workload**, không nên tuyên bố một loại index luôn hơn loại kia.

## 21. JOIN: khóa nối có nên đứng đầu index?

Xét mô hình đơn hàng và khách:

~~~sql
CREATE TEMP TABLE idx324_khach_hang (
    id INTEGER PRIMARY KEY,
    ten TEXT NOT NULL
);

INSERT INTO idx324_khach_hang (id, ten)
VALUES
    (10, 'An'),
    (20, 'Bình'),
    (30, 'Chi'),
    (40, 'Dũng'),
    (50, 'Hà'),
    (60, 'Lan');
~~~

Truy vấn:

~~~sql
SELECT
    kh.id,
    kh.ten,
    dh.id AS don_id,
    dh.created_at
FROM idx324_khach_hang AS kh
JOIN idx324_don_hang AS dh
    ON dh.customer_id = kh.id
WHERE kh.id = 10
  AND dh.status = 'PAID'
ORDER BY dh.created_at DESC, dh.id DESC;
~~~

Ứng viên `(customer_id, status, created_at DESC, id DESC)` phù hợp vì điều kiện JOIN tạo ra sự ràng buộc `customer_id = kh.id`, đồng thời status được cố định.

### 21.1. Không phải cứ thấy JOIN là thêm index mọi cột

- Bảng khách đã có PRIMARY KEY trên `id`.
- Tối ưu có thể chọn nested loop, hash join hoặc merge join tùy số dòng và lọc.
- Nếu join quét phần lớn hai bảng, index trên khóa bên trong chưa chắc được sử dụng.
- Nếu chỉ cập nhật hoặc thống kê toàn bộ dữ liệu, cách truy cập có thể khác truy vấn trả vài hàng.

Với các truy vấn bắt đầu từ một khách cụ thể, index trên `don_hang.customer_id` hoặc composite bắt đầu bằng cột này thường đáng cân nhắc. Với báo cáo xuyên mọi khách, index customer-first có thể không phải cấu trúc chính.

### 21.2. Khóa ngoại không mặc nhiên có index ở bảng con

Trong PostgreSQL, khai báo FOREIGN KEY ở bảng con **không tự tạo index trên cột FK**. Nếu ứng dụng thường JOIN, DELETE cha hoặc tìm con theo FK, cần cân nhắc index ở cột FK của bảng con.

Bảng mẫu `idx324_don_hang` chưa khai báo FK cho customer_id, nhưng tư duy chọn index theo `JOIN` vẫn tương tự khi dữ liệu có ràng buộc thật.

## 22. Phân trang: ORDER BY và keyset cursor

Giao diện đơn hàng có thể hiển thị nhiều trang:

~~~sql
SELECT id, created_at, total
FROM idx324_don_hang
WHERE customer_id = 10
  AND status = 'PAID'
ORDER BY created_at DESC, id DESC
LIMIT 2 OFFSET 0;
~~~

Trên dữ liệu mẫu, trang đầu có ID **5, 3**. Trang tiếp theo:

~~~sql
SELECT id, created_at, total
FROM idx324_don_hang
WHERE customer_id = 10
  AND status = 'PAID'
ORDER BY created_at DESC, id DESC
LIMIT 2 OFFSET 2;
~~~

có ID **2**.

### 22.1. Vì sao OFFSET sâu có thể tốn chi phí?

Dù có index tốt, OFFSET lớn vẫn có thể buộc PostgreSQL duyệt/bỏ qua nhiều hàng trước khi trả trang hiện tại. Nếu người dùng liên tục đi tới các trang sâu, phương pháp keyset/cursor thường có thể tránh một phần chi phí ấy.

### 22.2. Keyset pagination với khóa (created_at, id)

Giả sử trang đầu kết thúc tại:

~~~text
created_at = 2026-10-05 15:00:00
id = 3
~~~

Dãy sắp `created_at DESC, id DESC`. Trang kế tiếp chỉ lấy những hàng có cặp khóa **nhỏ hơn** cursor:

~~~sql
SELECT id, created_at, total
FROM idx324_don_hang
WHERE customer_id = 10
  AND status = 'PAID'
  AND (created_at, id) <
      (TIMESTAMP '2026-10-05 15:00:00', 3)
ORDER BY created_at DESC, id DESC
LIMIT 2;
~~~

Kết quả: **ID 2**. ID 2 có thời điểm trùng với ID 3 nhưng ID nhỏ hơn, nên xuất hiện sau trong thứ tự DESC.

### 22.3. Index phù hợp cho cursor

~~~sql
(customer_id, status, created_at DESC, id DESC)
~~~

phù hợp với hai điều kiện bằng, rồi thứ tự/cặp cursor. B-tree hỗ trợ so sánh theo khóa có thứ tự; hiệu quả cụ thể vẫn cần EXPLAIN.

Các điều kiện quan trọng:

- `created_at` và `id` phải đủ xác định thứ tự, không có tie chưa xử lý.
- Hai cột ví dụ NOT NULL nên phép so sánh cặp không gặp UNKNOWN do NULL.
- Khi filter giữa các trang thay đổi hoặc dữ liệu được thêm/xóa, ngay cả keyset pagination cũng cần chính sách nhất quán tùy giao diện.
- Nếu các cột sắp có hướng trái ngược, biểu thức so sánh cursor phải được thiết kế lại, không sao chép mù dấu `<` của ví dụ.

## 23. EXPLAIN: kiểm tra lời phỏng đoán về thứ tự cột

Sau khi đề xuất một index, hãy xem PostgreSQL thực sự chọn kế hoạch gì.

### 23.1. EXPLAIN không chạy câu SELECT

~~~sql
EXPLAIN
SELECT id, created_at, total
FROM idx324_don_hang
WHERE customer_id = 10
  AND status = 'PAID'
ORDER BY created_at DESC, id DESC
LIMIT 10;
~~~

`EXPLAIN` mặc định cho **kế hoạch ước lượng**, chưa chạy SELECT để đo thời gian thực.

### 23.2. EXPLAIN ANALYZE chạy truy vấn

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT id, created_at, total
FROM idx324_don_hang
WHERE customer_id = 10
  AND status = 'PAID'
ORDER BY created_at DESC, id DESC
LIMIT 10;
~~~

Với SELECT, câu lệnh được thực thi để đo. Với DML, `EXPLAIN ANALYZE INSERT/UPDATE/DELETE` cũng **thực thi việc ghi**, nên chỉ sử dụng trong môi trường thử nghiệm hoặc transaction có kiểm soát nếu thật sự cần đo DML.

### 23.3. Những nút kế hoạch thường gặp

| Dấu hiệu | Gợi ý về cách thực thi |
|---|---|
| `Seq Scan` | Quét bảng và lọc |
| `Index Scan using ...` | Duyệt index, có thể cần đọc hàng ở heap |
| `Index Only Scan using ...` | Dùng dữ liệu index; có thể vẫn phải kiểm tra visibility qua heap |
| `Bitmap Index Scan` | Tạo tập vị trí hàng từ index |
| `Bitmap Heap Scan` | Truy cập hàng từ bitmap |
| `BitmapAnd`, `BitmapOr` | Kết hợp bitmap của các điều kiện |
| `Sort` | Cần sắp xếp theo yêu cầu |
| `Limit` | Giới hạn số hàng trả |
| `Index Cond` | Điều kiện được dùng trong truy cập index |
| `Filter` | Điều kiện lọc bổ sung sau một phần đường truy cập |
| `Rows Removed by Filter` | Hàng bị loại bởi bước lọc tại nút đó |

`Index Cond` không tự đồng nghĩa mọi cột được dùng để **thu hẹp** đoạn quét ở mức tối đa. Với B-tree nhiều cột, một số điều kiện trên cột sau có thể được kiểm tra ngay trong index nhưng không giảm phạm vi cần duyệt như tiền tố bằng + cột range.

### 23.4. Estimated rows và actual rows

Planner đưa ra `rows` ước lượng theo thống kê; `EXPLAIN ANALYZE` cung cấp số hàng thực tế tại từng nút (và số lần lặp).

Nếu ước lượng rất khác thực tế, nguyên nhân có thể gồm:

- Thống kê cũ.
- Dữ liệu lệch phân bố.
- Tương quan mạnh giữa các cột.
- Tham số truy vấn biến thiên.
- Điều kiện phức tạp mà optimizer ước lượng khó.

Hãy **ANALYZE** và kiểm tra thống kê trước khi kết luận thứ tự index sai.

### 23.5. Vì sao bảng 25 hàng thường Seq Scan?

Để đọc 25 hàng, một Seq Scan có thể rẻ hơn đi vào B-tree, lấy TID, rồi đọc heap. Vì vậy, việc không thấy index trong plan ở bảng nhỏ **không chứng minh chỉ mục vô dụng** trên bảng lớn.

Không dùng một kế hoạch của 25 hàng để tuyên bố tốc độ production với hàng triệu hàng.

### 23.6. Không ép planner làm bài thay dữ liệu thật

PostgreSQL có các cài đặt thử nghiệm như `enable_seqscan` để so sánh kế hoạch trong môi trường thích hợp, nhưng bật/tắt một kiểu scan **không làm một index trở nên tốt trong workload thực**. Hãy đo truy vấn với phân bố dữ liệu, cache và tham số đại diện. Tránh đưa thay đổi planner toàn hệ thống vào production chỉ để một truy vấn demo hiển thị Index Scan.

## 24. Thực hành EXPLAIN với dữ liệu lớn hơn

Bộ 25 hàng giúp nhìn logic, nhưng để thấy khác biệt của prefix, hãy tạo một bảng thử nghiệm riêng với nhiều hàng. Đoạn PostgreSQL dưới tạo dữ liệu **tổng hợp**, không phải số liệu thật:

~~~sql
CREATE TEMP TABLE idx324_don_hang_lon AS
SELECT
    g.n AS id,
    ((g.n * 7) % 10000) + 1 AS customer_id,
    CASE
        WHEN g.n % 20 < 15 THEN 'PAID'
        WHEN g.n % 20 < 19 THEN 'NEW'
        ELSE 'CANCELLED'
    END AS status,
    TIMESTAMP '2026-01-01'
        + (g.n % 320) * INTERVAL '1 day'
        + (g.n % 86400) * INTERVAL '1 second'
        AS created_at,
    (g.n % 5000)::NUMERIC AS total
FROM generate_series(1, 200000) AS g(n);

ANALYZE idx324_don_hang_lon;
~~~

Bảng có 200.000 hàng theo công thức được xác định. Phân bố được tạo bằng phép modulo có thể có **tương quan nhân tạo** giữa customer/status/time; vì vậy phép đo chỉ là mô phỏng, không được coi là benchmark chính xác cho dữ liệu sản xuất.

### 24.1. Tạo một chỉ mục ứng viên

~~~sql
CREATE INDEX idx324_lon_customer_status_date
ON idx324_don_hang_lon (
    customer_id,
    status,
    created_at DESC,
    id DESC
);

ANALYZE idx324_don_hang_lon;
~~~

### 24.2. Đo truy vấn có đầy đủ tiền tố

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT id, created_at
FROM idx324_don_hang_lon
WHERE customer_id = 100
  AND status = 'PAID'
  AND created_at >= TIMESTAMP '2026-07-01'
  AND created_at <  TIMESTAMP '2026-11-01'
ORDER BY created_at DESC, id DESC
LIMIT 20;
~~~

### 24.3. Đo truy vấn thiếu cột đầu

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT id, customer_id, created_at
FROM idx324_don_hang_lon
WHERE status = 'PAID'
  AND created_at >= TIMESTAMP '2026-07-01'
  AND created_at <  TIMESTAMP '2026-11-01'
ORDER BY created_at DESC, id DESC
LIMIT 20;
~~~

So sánh kế hoạch, số hàng quét, thời gian, Buffer hits/reads, có Sort hay không. **Đừng chỉ so một lần chạy** vì cache, tải hệ thống và lựa chọn tham số ảnh hưởng kết quả.

### 24.4. Thử một thứ tự cột khác

~~~sql
CREATE INDEX idx324_lon_status_date
ON idx324_don_hang_lon (
    status,
    created_at DESC,
    id DESC
);

ANALYZE idx324_don_hang_lon;
~~~

Chạy lại câu ở phần 24.3. Nếu index status-first phù hợp hơn, bạn có thể thấy kế hoạch và số lượng trang đọc khác.

Tuy vậy, khi cùng tồn tại hai index, optimizer có thể chọn một trong nhiều đường truy cập. Muốn đánh giá công bằng trên dữ liệu thật, cần cân nhắc chi phí duy trì index, tần suất truy vấn, kiểu số liệu và thống kê, không chỉ xem latency của một SELECT.

## 25. Thống kê, tương quan và kế hoạch chọn index

Cơ sở dữ liệu không đọc ý định nghiệp vụ của bạn. Planner dựa trên **thống kê và mô hình chi phí** để ước lượng số hàng và các đường truy cập có thể dùng.

### 25.1. Một cột có nhiều giá trị phân biệt chưa chắc cho điều kiện chọn lọc cao

Ví dụ một cột có 10.000 khách hàng, nhưng một khách lớn có 40% đơn còn phần còn lại chia nhỏ. `customer_id = khach_lon` có độ chọn lọc khác xa `customer_id = khach_hiem`.

Vì vậy, chỉ nhìn số lượng giá trị khác nhau của `customer_id` chưa đủ. Cần quan sát phân bố thực, các giá trị phổ biến và tham số truy vấn.

### 25.2. Tương quan giữa các cột

Ví dụ trong dữ liệu thật, một số khách có gần như toàn đơn PAID, một số khác toàn NEW. Hai điều kiện:

~~~sql
WHERE customer_id = ?
  AND status = 'PAID'
~~~

không độc lập về xác suất. Nếu planner ước lượng chúng như độc lập, số hàng dự kiến có thể sai.

PostgreSQL hỗ trợ các cơ chế **extended statistics** để lưu thêm thông tin liên hệ giữa một số cột.

Ví dụ thử nghiệm:

~~~sql
CREATE STATISTICS idx324_stat_customer_status
    (dependencies, ndistinct)
ON customer_id, status
FROM idx324_don_hang;

ANALYZE idx324_don_hang;
~~~

Extended statistics có thể giúp ước lượng một số điều kiện kết hợp chính xác hơn. Nó **không thay thế chỉ mục** và không bảo đảm planner dùng một index cụ thể.

### 25.3. Khác biệt giữa thống kê và cấu trúc index

- **Thống kê** giúp optimizer đoán số hàng và chi phí.
- **Index** cung cấp một đường truy cập có thứ tự và cấu trúc tìm kiếm.
- **EXPLAIN** cho biết đường nào được chọn.
- **EXPLAIN ANALYZE** cho biết chi phí thực tế của lần chạy trong môi trường đang thử.

Nếu chỉ số liệu dự đoán sai, việc tạo thêm index có thể không giải quyết gốc rễ; cần xem thống kê và các giả định.

### 25.4. Parameters và generic plans

Một statement có tham số có thể được lập kế hoạch theo giá trị cụ thể hoặc dùng kế hoạch chung cho nhiều giá trị. Khi dữ liệu rất lệch, cùng câu SQL với `customer_id` hiếm và khách lớn có thể cần đường truy cập khác nhau.

Đừng giả định một plan từ SQL có literal tự động đại diện cho mọi lần gọi PreparedStatement. Hãy kiểm tra việc prepare/bind thực tế nếu vấn đề hiệu năng xảy ra trong ứng dụng.

## 26. Thứ tự cột và ảnh hưởng tới ghi dữ liệu

Index không miễn phí.

Mỗi INSERT có thể phải ghi thêm vào các index liên quan. UPDATE các cột được đánh index có thể làm tăng chi phí duy trì index và tác động đến khả năng HOT update của PostgreSQL; DELETE cũng cần được xử lý trong cấu trúc lưu trữ và quá trình dọn dẹp tương ứng.

### 26.1. Nhiều index có cấu trúc gần giống nhau

Nếu bạn tạo:

~~~sql
(customer_id)
(customer_id, status)
(customer_id, status, created_at)
(customer_id, status, created_at, id)
~~~

có thể có nhiều chỉ mục chồng lấn. Nhưng index dài hơn không luôn thay thế hoàn toàn index ngắn hơn:

- Index ngắn thường nhỏ hơn và có thể rẻ hơn cho một số truy vấn.
- Index dài có thể hỗ trợ ORDER BY/điều kiện sâu hơn.
- Hướng ASC/DESC, uniqueness, INCLUDE, partial predicate có thể làm khác công dụng.
- Chi phí viết và cache phải được tính.

Vì vậy, không tự xóa index ngắn chỉ vì có một index dài bắt đầu bằng cùng cột; hãy kiểm tra mức sử dụng và đặc tính workload.

### 26.2. Ưu tiên một số truy vấn quan trọng

Một quy trình thực tế:

1. Liệt kê các câu SELECT/JOIN/UPDATE quan trọng.
2. Ghi tần suất, độ trễ, số hàng trả, khoảng lọc.
3. Nhóm các câu có cùng điều kiện bằng và ORDER BY.
4. Chọn số ít index ứng viên dùng chung tốt.
5. Đo bằng EXPLAIN ANALYZE với tham số và dữ liệu đại diện.
6. Đánh giá dung lượng, insert/update throughput, VACUUM và cache.
7. Giữ hoặc loại bỏ ứng viên theo bằng chứng đo được.

Không lập danh sách mọi hoán vị cột rồi CREATE INDEX tất cả; số biến thể tăng rất nhanh khi có nhiều cột.

## 27. Khi B-tree tổng hợp không phải lựa chọn duy nhất

Bài này trọng tâm B-tree nhưng một số workload cần các loại chỉ mục khác.

### 27.1. BRIN cho dữ liệu rất lớn có tương quan vật lý theo thời gian

Với bảng log/sự kiện khổng lồ, được append theo thời gian, `created_at` có thể tương quan mạnh với thứ tự lưu trang. PostgreSQL có **BRIN** để tóm tắt vùng trang, dùng rất ít dung lượng trong trường hợp phù hợp.

~~~sql
CREATE INDEX idx324_lon_brin_created
ON idx324_don_hang_lon
USING BRIN (created_at);
~~~

BRIN thường là đường truy cập **lossy**, có thể phải đọc và kiểm tra nhiều hàng trong vùng trang; nó không tự thay B-tree để đáp ứng `ORDER BY created_at DESC LIMIT 20` nhanh. Chọn dựa trên mô hình dữ liệu và truy vấn.

### 27.2. GIN cho tìm kiếm tập hợp/văn bản

Truy vấn tìm phần tử trong JSONB/array hoặc tìm chuỗi con với trigram có thể cần GIN/GiST phù hợp thay vì chỉ đổi thứ tự cột B-tree.

### 27.3. Partitioning cho bảng lịch sử rất lớn

Nếu dữ liệu chia theo tháng/năm, partitioning có thể giúp **loại trừ phân vùng** khi WHERE có điều kiện phù hợp, kết hợp với các chỉ mục trong từng phân vùng. Nhưng partitioning có chi phí vận hành và thay đổi cách quản lý khóa/chỉ mục.

### 27.4. Tối ưu hóa phải dựa trên câu hỏi

- Cần tìm vài hàng bằng khóa? B-tree thường là ứng viên tốt.
- Cần dãy có thứ tự và LIMIT? Thứ tự khóa B-tree rất quan trọng.
- Cần quét một khoảng thời gian lớn trên dữ liệu lưu tuần tự? Xem cả BRIN/partitioning.
- Cần tìm chuỗi con? Xem trigram.
- Cần tổng hợp phần lớn bảng? Seq Scan/parallel scan có thể đúng hơn Index Scan.

Không thể chữa mọi truy vấn chậm bằng việc thêm nhiều cột vào B-tree.

## 28. Bộ quy tắc thiết kế ứng viên theo mẫu WHERE

Bảng dưới giúp chọn **điểm xuất phát**:

| Mẫu WHERE/ORDER BY | Ứng viên B-tree | Cảnh báo |
|---|---|---|
| `a = ?` | `(a)` | Nếu chọn nhiều hàng, Seq Scan có thể tốt hơn |
| `a = ? AND b = ?` | `(a,b)` hoặc `(b,a)` | Chọn thứ tự theo các truy vấn chỉ có a hoặc b |
| `a = ? AND b BETWEEN ...` | `(a,b)` | Cột bằng trước, khoảng sau |
| `a = ? AND b = ? AND c BETWEEN ...` | `(a,b,c)` | Xem ORDER BY và tiền tố dùng lại |
| `a = ? ORDER BY c DESC LIMIT n` | `(a,c DESC)` | Cột b chèn giữa có thể phá thứ tự c |
| `a = ? AND b = ? ORDER BY c DESC, id DESC` | `(a,b,c DESC,id DESC)` | Tie-breaker cần đúng hướng |
| `b = ? AND c BETWEEN ...`, không có a | `(b,c)` | `(a,b,c)` có thể kém nếu a không cố định |
| `status = 'PAID' AND active` | Partial index theo status/active | Predicate phải được truy vấn hàm ý |
| `LOWER(code) = ?` | Expression index `(LOWER(code))` | Cân nhắc chuẩn hóa mã và collation |
| `a = ?`, SELECT thêm vài cột nhỏ | `(a) INCLUDE (...)` | INCLUDE không tạo khóa lọc |
| `a = ? OR b = ?` | Hai index + bitmap hoặc Seq Scan | Composite index không tự tối ưu mọi OR |
| `created_at::DATE = ?` | Range trên timestamp hoặc expression index | Cast TIMESTAMPTZ có vấn đề múi giờ/immutable |
| `code LIKE 'ABC%'` | B-tree/pattern_ops khi phù hợp | Phụ thuộc collation |
| `code LIKE '%ABC%'` | Trigram GIN/GiST khi cần | B-tree prefix không tối ưu hậu tố |

**Đừng coi bảng này là kết quả cuối**. Chọn index phải xét thêm phân bố dữ liệu, loại thao tác ghi, bản ghi NULL, JOIN, thứ tự sắp, mức cô lập, dữ liệu nóng/lạnh và khả năng optimizer.

## 29. Những lỗi thường gặp khi chọn thứ tự cột

| Sai lầm | Vì sao có thể sai? | Cách suy nghĩ tốt hơn |
|---|---|---|
| “Mỗi cột ở WHERE đều có index là đủ” | Nhiều index một cột không tự phục vụ ORDER BY nhiều cột | Xét composite khi có lọc + sắp xếp |
| “Cột chọn lọc nhất luôn đứng đầu” | Hai điều kiện bằng có thể dùng cả hai thứ tự; workload khác nhau cần tiền tố khác | Chọn theo mẫu truy vấn thực |
| “Có cột created_at ở cuối index thì sort theo created_at được” | Cột đứng trước chưa cố định có thể chia dữ liệu thành nhóm | Kiểm tra ORDER BY trên phần suffix sau các prefix equality |
| “Thiếu cột đầu thì index tuyệt đối vô dụng” | Planner có thể quét index/skip scan/bitmap | Hiểu quy tắc thông thường và xem EXPLAIN |
| “Cột sau range vô ích hoàn toàn” | Có thể vẫn làm điều kiện lọc trong index, dù không thu hẹp vùng quét tốt như prefix | Phân biệt bound scan và residual filter |
| “WHERE viết AND theo thứ tự index mới nhanh” | Optimizer phân tích predicate, không dựa trình tự văn bản của AND | Thứ tự CREATE INDEX mới là trọng tâm |
| “INDEX(a,b,c) luôn thay được INDEX(a,c)” | B ở giữa làm thay đổi thứ tự c trong từng a | So yêu cầu ORDER BY và lọc |
| “INDEX nhiều cột hơn chắc tốt hơn” | Index lớn, thêm chi phí ghi/cache và có thể không khớp ORDER BY | Giữ vừa đủ khóa và INCLUDE |
| “INCLUDE là cột khóa tìm kiếm” | Payload không tham gia thứ tự B-tree | Dùng key cho lọc/range/sort |
| “Partial index tự dùng cho mọi query” | Query phải hàm ý predicate; generic plan có thể không chứng minh | EXPLAIN với đúng query/parameters |
| “B-tree LIKE luôn dùng được” | Collation/operator class và wildcard đầu ảnh hưởng | Xem pattern_ops/trigram |
| “Tìm NULL không dùng được B-tree” | PostgreSQL B-tree có thể lưu NULL | Kiểm tra dữ liệu và plan |
| “Hàm trên cột không ảnh hưởng gì” | Có thể không khớp index cột gốc | Viết range hoặc expression index |
| “Tìm ngày bằng BETWEEN tới ngày cuối là đủ” | Timestamp ngày cuối có giờ, dễ mất dữ liệu | Dùng khoảng nửa mở |
| “COUNT nhỏ thì index chắc nhanh” | Bảng nhỏ thường Seq Scan rẻ hơn | Đo trên dữ liệu đại diện |
| “Không thấy Index Scan trong 25 hàng nghĩa index sai” | Planner chọn đường rẻ theo số liệu hiện tại | Kiểm tra quy mô/ANALYZE |
| “Chỉ cần EXPLAIN một lần” | Cache, tham số và thống kê thay đổi | Đo lặp, so dữ liệu đại diện |
| “ORDER BY id không cần vì index có thứ tự ngầm” | SQL không cam kết thứ tự nếu thiếu ORDER BY | Viết ORDER BY đầy đủ |
| “OFFSET sâu vẫn nhanh vì có index” | Vẫn có thể duyệt/bỏ nhiều hàng | Cân nhắc keyset cursor |
| “Cứ tạo index cho mọi hoán vị” | Tốn dung lượng và chi phí INSERT/UPDATE/DELETE | Chọn số ít theo workload |

## 30. Bài tập thực hành có lời giải

Các bài dùng bảng `idx324_don_hang` đã nạp 25 dòng. Những bài `CREATE INDEX` chỉ tạo ứng viên trên bảng thử nghiệm; nếu chạy lặp, bạn cần dùng tên mới hoặc xóa index cũ trong môi trường học. Không áp dụng nguyên số lượng index của bài vào hệ thống sản xuất.

### Bài 1. Chọn index cho lọc khách + trạng thái + ngày

**Đề:** Truy vấn:

~~~sql
SELECT id, created_at
FROM idx324_don_hang
WHERE customer_id = 20
  AND status = 'PAID'
  AND created_at >= TIMESTAMP '2026-10-01'
  AND created_at <  TIMESTAMP '2026-11-01'
ORDER BY created_at DESC, id DESC;
~~~

Chọn thứ tự khóa nào?

**Đáp án:** ứng viên tự nhiên là `(customer_id, status, created_at DESC, id DESC)`. Hai điều kiện bằng ở đầu, khoảng thời gian tiếp theo, rồi thứ tự phù hợp. Dữ liệu mẫu trả ba ID **9, 8, 7** theo thời gian DESC.

### Bài 2. Chỉ lọc status và ngày

**Đề:** Báo cáo đơn PAID tháng 10 của **mọi khách**, vì sao `(customer_id,status,created_at)` chưa chắc phù hợp bằng `(status,created_at)`?

**Đáp án:** truy vấn không cố định customer_id, nên cột đầu của index customer-first tạo nhiều nhóm khách; không có một vùng liên tục PAID theo thời gian trên toàn bảng như ứng viên status-first. PostgreSQL vẫn có thể dùng các kỹ thuật quét khác, nhưng không nên thiết kế customer-first làm lựa chọn chính chỉ cho workload này.

### Bài 3. Tổng số đơn PAID tháng 10

~~~sql
SELECT COUNT(*) AS so_don
FROM idx324_don_hang
WHERE status = 'PAID'
  AND created_at >= TIMESTAMP '2026-10-01'
  AND created_at <  TIMESTAMP '2026-11-01';
~~~

**Đáp án:** **13** trên bộ dữ liệu mẫu. Số hàng trả ít hay nhiều trên bảng thật phụ thuộc phân bố; không suy ra index sẽ được chọn chỉ từ phép đếm mẫu.

### Bài 4. Tại sao index có cột status ở giữa không đáp ứng ORDER BY?

**Đề:** Index `(customer_id,status,created_at DESC)`, truy vấn `WHERE customer_id=10 ORDER BY created_at DESC`.

**Đáp án:** trong cùng customer_id, index nhóm theo status trước nên các thời điểm thuộc status khác nhau không nằm trong một dãy created_at DESC toàn cục. Một ứng viên `(customer_id,created_at DESC)` phù hợp hơn cho truy vấn mọi trạng thái của một khách.

### Bài 5. Lọc một khách không có status

~~~sql
SELECT id, status, created_at
FROM idx324_don_hang
WHERE customer_id = 10
ORDER BY created_at DESC, id DESC;
~~~

**Đáp án:** ID theo thứ tự **5, 4, 3, 2, 1**. Cột `status` không cố định nên index `(customer_id,status,created_at)` có thể cần Sort.

### Bài 6. Điều kiện khoảng trước equality

**Đề:** So sánh `(customer_id,status,created_at)` với `(created_at,customer_id,status)` khi truy vấn có customer_id bằng, status bằng, thời gian thuộc cả tháng.

**Đáp án:** index equality-first thường có khả năng giới hạn về đúng nhóm khách/trạng thái trước khi đi qua khoảng thời gian. Index date-first có thể phải xét nhiều hàng trong khoảng trên mọi khách. Cần đo trên phân bố thực, không kết luận một index luôn thắng trong mọi trường hợp.

### Bài 7. Cột chọn lọc hơn phải đứng đầu?

**Đề:** Vì sao không thể chỉ dựa vào việc customer_id chọn ít dòng hơn status để quyết định index `(customer_id,status)`?

**Đáp án:** nếu phần lớn workload chỉ lọc status, index status-first được dùng theo tiền tố; nếu phần lớn chỉ lọc customer, customer-first hữu ích. Với hai điều kiện bằng cùng xuất hiện, cả hai thứ tự đều có thể tìm đúng nhóm. Phải xét các truy vấn khác, ORDER BY và phân bố.

### Bài 8. IN và thứ tự

~~~sql
SELECT id, status, created_at
FROM idx324_don_hang
WHERE status IN ('NEW', 'PAID')
ORDER BY created_at DESC, id DESC;
~~~

**Hỏi:** index `(status,created_at DESC,id DESC)` có tự bảo đảm kết quả ORDER BY không?

**Đáp án:** không tự bảo đảm, vì kết quả gồm **hai giá trị status** và cần trộn theo ngày toàn cục. PostgreSQL có thể cần Sort/plan kết hợp các luồng phù hợp.

### Bài 9. Timestamp theo tháng

**Đề:** Vì sao nên dùng:

~~~sql
WHERE created_at >= TIMESTAMP '2026-10-01'
  AND created_at < TIMESTAMP '2026-11-01'
~~~

thay vì BETWEEN đầu tháng và `2026-10-31 00:00:00`?

**Đáp án:** BETWEEN tới đầu ngày 31/10 bỏ sót các thời điểm còn lại của ngày cuối tháng. Khoảng nửa mở bao phủ đúng mọi thời điểm trong tháng 10 và phù hợp range predicate trên TIMESTAMP.

### Bài 10. Truy vấn có hàm trên cột

~~~sql
SELECT id
FROM idx324_don_hang
WHERE created_at::DATE = DATE '2026-10-05';
~~~

**Đáp án:** có thể viết lại thành `created_at >= TIMESTAMP '2026-10-05' AND created_at < TIMESTAMP '2026-10-06'` để phù hợp B-tree thường trên created_at, hoặc cân nhắc expression index nếu truy vấn theo DATE là workload chính. Dữ liệu mẫu có ID **2 và 3**.

### Bài 11. IS NULL

~~~sql
SELECT id, region
FROM idx324_don_hang
WHERE region IS NULL;
~~~

**Đáp án:** ID **25**. PostgreSQL B-tree có thể phục vụ IS NULL tùy index và kế hoạch, không mặc định NULL bị loại khỏi mọi index.

### Bài 12. Partial index cho đơn PAID chưa lưu trữ

**Đề:** Chọn index cho truy vấn có `customer_id = ? AND status = 'PAID' AND archived_at IS NULL ORDER BY created_at DESC,id DESC`.

**Đáp án:**

~~~sql
CREATE INDEX idx324_bt12_paid_active
ON idx324_don_hang (customer_id, created_at DESC, id DESC)
WHERE status = 'PAID'
  AND archived_at IS NULL;
~~~

Trong tập dữ liệu partial, status và archived_at đã cố định theo predicate nên không nhất thiết cần nằm trong key. Truy vấn phải hàm ý chính xác điều kiện partial index và planner có thể còn phụ thuộc prepared statements.

### Bài 13. Vì sao partial index không giúp mọi đơn?

**Đề:** Index ở bài 12 chỉ chứa PAID chưa lưu trữ. Có thể dùng nó làm nguồn duy nhất cho `SELECT ... WHERE customer_id=10` không?

**Đáp án:** không, vì truy vấn còn cần cả NEW/CANCELLED hoặc các đơn đã lưu trữ; những hàng ấy không nằm trong partial index.

### Bài 14. INCLUDE khác key

**Đề:** Index `(customer_id,created_at DESC) INCLUDE (total)` có dùng `total >= 300` như một khóa range tìm kiếm tương đương `(customer_id,total,created_at)` không?

**Đáp án:** không. INCLUDE chỉ lưu payload, không tạo thứ tự tìm kiếm theo total. Nó có thể giúp đọc total mà không cần heap trong một số index-only plan, nhưng không thay đổi bản chất key.

### Bài 15. LIKE tiền tố và hậu tố

**Đề:** Hai truy vấn `code LIKE 'ORD-0001%'` và `code LIKE '%0001'` có cùng cơ hội dùng B-tree prefix không?

**Đáp án:** không. Truy vấn đầu có tiền tố cố định nên B-tree/pattern_ops có thể hữu ích; truy vấn thứ hai có wildcard ở đầu, B-tree sắp từ trái thường không tìm trực tiếp theo hậu tố. Nếu tìm chuỗi con phổ biến, xem xét pg_trgm khi phù hợp.

### Bài 16. Từ WHERE sang ứng viên ORDER BY

**Đề:** Mẫu `WHERE customer_id=? ORDER BY created_at DESC,id ASC LIMIT 20` cần index nào?

**Đáp án:** có thể thử `(customer_id, created_at DESC, id ASC)` vì hướng sắp hỗn hợp. Một index hai cột ASC rồi quét ngược thường đảo cả hai chiều, không tự cho created_at DESC nhưng id ASC.

### Bài 17. Phân trang có bản ghi trùng thời điểm

**Đề:** Khách 10 có hai đơn PAID cùng `2026-10-05 15:00` là ID 2 và 3. Trang đầu trả 5 và 3. Cursor ở ID 3. Viết điều kiện trang tiếp.

~~~sql
SELECT id, created_at
FROM idx324_don_hang
WHERE customer_id = 10
  AND status = 'PAID'
  AND (created_at, id)
      < (TIMESTAMP '2026-10-05 15:00:00', 3)
ORDER BY created_at DESC, id DESC
LIMIT 2;
~~~

**Đáp án:** ID **2**. Nếu chỉ so created_at, ID 2 có thể bị bỏ sót vì trùng thời điểm với cursor.

### Bài 18. Vì sao Seq Scan không chứng minh index sai?

**Đề:** EXPLAIN trên bảng 25 hàng trả Seq Scan dù đã CREATE INDEX.

**Đáp án:** bảng quá nhỏ, đọc toàn bộ có thể rẻ hơn đi qua B-tree rồi lấy heap. Hãy ANALYZE, kiểm tra plan và đo trên dữ liệu đại diện; không ép planner chỉ để nhìn thấy chữ Index Scan.

### Bài 19. Số dòng JOIN và thứ tự index

**Đề:** Từ bảng khách hàng, lấy đơn PAID của một khách `kh.id=10` với ORDER BY thời gian. Cột nào nên đứng đầu index bảng đơn?

**Đáp án:** `customer_id` là ứng viên ở đầu vì được ràng buộc bằng khóa JOIN với khách cụ thể. `status` có thể đứng thứ hai, sau đó `created_at DESC,id DESC`. Nhưng nếu join toàn bộ khách và quét phần lớn đơn, kế hoạch và nhu cầu index có thể khác.

### Bài 20. Hai index đơn cột hay một composite?

**Đề:** Có index riêng `customer_id` và `status`; truy vấn `WHERE customer_id=10 AND status='PAID' ORDER BY created_at DESC` chạy rất thường xuyên. Có nên cân nhắc composite?

**Đáp án:** có. Composite `(customer_id,status,created_at DESC,id DESC)` có thể kết hợp lọc và sắp; bitmap kết hợp hai index đơn cột thường không giữ thứ tự theo created_at. Nhưng phải đo chi phí và đánh giá các index đang có.

### Bài 21. Kiểm tra kế hoạch đúng cách

**Đề:** Lệnh nào đo thực tế plan của một SELECT trong PostgreSQL?

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT id
FROM idx324_don_hang
WHERE customer_id = 10;
~~~

**Đáp án:** lệnh trên chạy SELECT và cung cấp thời gian/đọc buffer ở kế hoạch. Với UPDATE/DELETE, EXPLAIN ANALYZE sẽ thực thi thay đổi nên cần môi trường thử hoặc transaction có kiểm soát.

### Bài 22. Workload nhiều loại điều kiện

**Đề:** Hệ thống có 80% truy vấn `WHERE customer_id=? ORDER BY created_at DESC LIMIT 20`, 15% truy vấn `WHERE customer_id=? AND status='PAID' ORDER BY created_at DESC`, 5% báo cáo `WHERE status='PAID' AND created_at BETWEEN ...`. Có nên tạo ngay ba chỉ mục?

**Đáp án:** chưa thể kết luận. `(customer_id,created_at DESC,id DESC)` là ứng viên mạnh cho mẫu chiếm 80%; truy vấn 15% có thể lọc status thêm, hoặc cần một index khác nếu số dòng mỗi khách lớn; báo cáo 5% có thể cần status-first nếu ảnh hưởng độ trễ quan trọng. Phải đo với phân bố/tần suất/chi phí ghi trước khi chọn tổ hợp.

## 31. Checklist thiết kế thứ tự cột trong chỉ mục

Khi bắt đầu tối ưu một câu SQL, hãy kiểm tra:

1. **Query thật là gì?** Đừng chọn index chỉ từ tên cột trên schema.
2. **Bảng mục tiêu có bao nhiêu hàng và dữ liệu phân bố ra sao?**
3. **Các điều kiện WHERE nào là bằng, khoảng, IN, OR, NULL hoặc biểu thức?**
4. **Những cột nào thường xuất hiện đồng thời?**
5. **Có mẫu chỉ dùng tiền tố một/ hai cột không?**
6. **Có cột nào chưa được cố định nằm trước cột ORDER BY không?**
7. **Điều kiện range xuất hiện ở vị trí nào trong khóa index?**
8. **Có ORDER BY hỗn hợp ASC/DESC và NULLS FIRST/LAST không?**
9. **LIMIT nhỏ hay trả phần lớn bảng?**
10. **Có phân trang OFFSET sâu hoặc keyset cursor không?**
11. **Có cần khóa tie-breaker để thứ tự ổn định không?**
12. **Có thể dùng partial index cho tập con thường truy cập không?**
13. **Query có hàm như LOWER/CAST/DATE trên cột không?**
14. **Cột cần trả về có đáng INCLUDE không?**
15. **Một index tổng hợp có thay thế hoặc chồng lấn index khác không?**
16. **Có cần xét bitmap của nhiều index đơn cột không?**
17. **B-tree có phù hợp kiểu toán tử LIKE/ILIKE/JSON không?**
18. **Đã chạy ANALYZE để planner có thống kê đủ mới chưa?**
19. **Đã xem Index Cond, Filter, Sort, estimated/actual rows trong EXPLAIN chưa?**
20. **Đã đo với dataset/param đại diện và không chỉ một truy vấn giả lập không?**
21. **Chi phí INSERT/UPDATE/DELETE, dung lượng, cache có chấp nhận được không?**
22. **Có câu truy vấn khác bị chậm đi hoặc lợi ích suy giảm khi thêm index không?**
23. **Có cần kiểm tra PostgreSQL version/driver vì skip scan hoặc generic plan không?**
24. **Có đang mặc định một quy tắc “selective first” mà bỏ qua workload không?**

## 32. Tổng kết

**Thứ tự cột trong chỉ mục nhiều cột quyết định khả năng sử dụng chỉ mục cho từng mẫu điều kiện lọc và sắp xếp**.

- Trong B-tree, các khóa được tổ chức từ **cột trái sang cột phải**. Những điều kiện bằng trên tiền tố dẫn đầu, tiếp theo một điều kiện khoảng, thường là cấu trúc thuận lợi để thu hẹp vùng đọc.
- Một cột có mặt trong index **không có nghĩa** mọi truy vấn lọc theo cột ấy đều tận dụng được index hiệu quả như khi nó nằm ở tiền tố.
- `(customer_id,status,created_at)` và `(status,created_at,customer_id)` có thể phục vụ những workload khác nhau; thứ tự viết AND trong WHERE không thay đổi thứ tự khóa đã định nghĩa.
- **Không có quy tắc tuyệt đối “cột chọn lọc nhất luôn đứng đầu”**. Chọn thứ tự cần xét các mẫu truy vấn chỉ có tiền tố, ORDER BY, LIMIT, JOIN, độ chọn lọc theo giá trị và thống kê.
- Với `ORDER BY` và phân trang, vị trí/hướng các cột sắp xếp và khóa phá hòa như `id` thường quan trọng không kém việc lọc.
- `IN`, `OR`, `IS NULL`, `LIKE`, biểu thức trên cột và partial predicate có những đặc điểm riêng; không thể tối ưu chúng chỉ bằng mẹo đổi vị trí cột.
- **Partial index** giới hạn tập hàng được lưu; **INCLUDE** lưu payload phục vụ đọc, không tạo thêm khóa lọc; **expression index** phục vụ biểu thức có định nghĩa phù hợp.
- PostgreSQL có nhiều đường truy cập: Index Scan, Index Only Scan, Bitmap, skip scan khi được hỗ trợ, hoặc Seq Scan. **Việc planner chọn Seq Scan không tự chứng minh một index vô dụng**.
- Chỉ mục mang chi phí lưu trữ và ghi, nên cần chọn **số ít chỉ mục thực sự phục vụ workload**, dùng EXPLAIN/ANALYZE và dữ liệu đại diện để quyết định.

Hãy bắt đầu từ **mẫu WHERE → tiền tố bằng → điều kiện khoảng → ORDER BY/LIMIT → lựa chọn thứ tự cột → EXPLAIN trên dữ liệu thật → đo chi phí đọc và ghi**, thay vì tạo index theo cảm tính chỉ vì một số cột thường xuất hiện trong truy vấn.
