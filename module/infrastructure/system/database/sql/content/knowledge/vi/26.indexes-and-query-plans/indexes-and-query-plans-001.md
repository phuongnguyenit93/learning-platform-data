# Chỉ mục hỗ trợ truy vấn như thế nào ở mức SQL

Một bảng SQL có thể chứa hàng triệu đơn hàng. Người dùng mở danh sách “đơn của tổ chức 10, đã thanh toán, mới nhất trước” và mong trang đầu hiển thị nhanh. Nếu database phải đọc mọi hàng, lọc rồi sắp xếp toàn bộ kết quả, chi phí có thể lớn. **Chỉ mục (*index*)** là cấu trúc dữ liệu bổ sung giúp hệ quản trị tìm những hàng cần thiết, hoặc đọc chúng theo thứ tự hữu ích, mà **không nhất thiết quét toàn bộ bảng**.

Nhưng chỉ thêm một câu `CREATE INDEX` không bảo đảm truy vấn nhanh. Index chỉ là **một trong nhiều đường truy cập (*access paths*)** mà bộ tối ưu hóa (*query optimizer/planner*) có thể chọn. Tùy lượng dữ liệu, độ chọn lọc của điều kiện, thứ tự cột, số hàng cần đọc, cách JOIN, phép sắp xếp và chi phí đọc trang dữ liệu, quét toàn bảng đôi khi lại tốt hơn.

Bài học này thuộc **Database SQL → Chỉ mục và kế hoạch**. Ta tập trung vào **cách index phục vụ câu SQL**: `WHERE`, `JOIN`, `ORDER BY`, `LIMIT`, `GROUP BY`, `DISTINCT`, index ghép, index bao phủ, partial/expression indexes, cách đọc `EXPLAIN` và đánh đổi khi ghi dữ liệu. Ví dụ chính dùng **PostgreSQL**; cuối bài có đối chiếu MySQL/InnoDB, SQL Server, Oracle và SQLite.

## 1. Hình dung bảng và index như hai cách tìm dữ liệu

Giả sử bảng `don_hang` có một triệu hàng. Mỗi hàng lưu `id`, `to_chuc_id`, `khach_hang_id`, `trang_thai`, `tao_luc` và `tong_tien`.

Truy vấn:

~~~sql
SELECT id, tao_luc, tong_tien
FROM don_hang
WHERE to_chuc_id = 10
  AND trang_thai = 'DA_THANH_TOAN'
ORDER BY tao_luc DESC, id DESC
LIMIT 20;
~~~

Có hai hình dung cơ bản:

**Không sử dụng chỉ mục phù hợp:** database đọc một lượng lớn dữ liệu từ bảng, kiểm tra điều kiện của từng hàng, xác định tập khớp, sau đó có thể phải sắp xếp để lấy 20 hàng đầu.

**Sử dụng chỉ mục phù hợp:** database có thể đi tới nhóm khóa của tổ chức 10 và trạng thái DA_THANH_TOAN trên index, đọc tiếp theo thứ tự `tao_luc DESC, id DESC` và dừng sau khi có đủ 20 hàng cần thiết, nếu các điều kiện khác cũng cho phép.

~~~mermaid
flowchart TB
    Q["SQL: lọc + ORDER BY + LIMIT"] --> P{"Planner chọn đường truy cập"}
    P --> S["Sequential scan\nĐọc hàng trong bảng"]
    P --> I["Index scan\nTìm khóa trên index"]
    S --> F["Kiểm tra điều kiện\nCó thể sort"]
    I --> H["Đọc hàng phù hợp\nCó thể đã đúng thứ tự"]
    F --> R["Trả kết quả"]
    H --> R
~~~

Đây là mô hình khái niệm, **không phải dự đoán chắc chắn một execution plan cụ thể**. Index cũng có chi phí tra cứu và lấy dữ liệu gốc; nếu điều kiện trả về phần lớn bảng, đọc tuần tự có thể rẻ hơn.

### 1.1. Chỉ mục lưu gì?

Với PostgreSQL, một B-tree index thường lưu **giá trị khóa đã sắp** và thông tin trỏ tới phiên bản hàng ở bảng. Bảng vật lý và B-tree là **hai cấu trúc riêng**. Index không phải bản sao hoàn chỉnh của toàn bộ bảng.

Minh họa:

~~~text
Bảng (heap)
┌───────────┬────────────┬──────────────┬─────────┐
│ id        │ to_chuc_id │ trang_thai   │ ...     │
├───────────┼────────────┼──────────────┼─────────┤
│ 101       │ 10         │ DA_THANH_TOAN│ ...     │
│ 102       │ 20         │ MOI          │ ...     │
│ 103       │ 10         │ DA_THANH_TOAN│ ...     │
└───────────┴────────────┴──────────────┴─────────┘

Index B-tree (to_chuc_id, trang_thai, tao_luc)
   khóa 10, DA_THANH_TOAN, 2026-10-01 → vị trí hàng 101
   khóa 10, DA_THANH_TOAN, 2026-10-02 → vị trí hàng 103
   khóa 20, MOI, ...                  → vị trí hàng 102
~~~

Khi cần `tong_tien` mà index không chứa cột đó, engine thường phải đọc thêm từ bảng. Vì thế **tìm ít hàng bằng index** thường có lợi, nhưng **đọc gần như toàn bộ hàng bằng index rồi nhảy tới bảng** có thể đắt hơn đọc bảng tuần tự.

### 1.2. Chỉ mục không đổi nội dung logic của SELECT

Index thường giúp cải thiện **cách thực thi**, không thay đổi tập kết quả đúng về mặt SQL. Câu SQL không có `ORDER BY` vẫn **không được bảo đảm thứ tự đầu ra**, kể cả planner tình cờ dùng một B-tree theo thứ tự khóa.

Vì vậy không viết ứng dụng dựa trên giả định:

> “Có index ở cột ngày nên SELECT sẽ luôn trả theo ngày tăng dần.”

Muốn yêu cầu thứ tự, phải dùng **`ORDER BY` tường minh**.

## 2. Bộ dữ liệu thực hành PostgreSQL

Bảng mẫu lưu đơn hàng nhiều tổ chức, có một số khách hàng lặp lại và thời điểm tạo bị trùng để minh họa khóa phụ khi sắp xếp.

~~~sql
CREATE TEMP TABLE don_hang_idx (
    id BIGINT PRIMARY KEY,
    to_chuc_id INTEGER NOT NULL,
    khach_hang_id INTEGER NOT NULL,
    trang_thai TEXT NOT NULL
        CHECK (trang_thai IN (
            'MOI', 'DANG_XU_LY', 'DA_THANH_TOAN', 'DA_HUY'
        )),
    tao_luc TIMESTAMPTZ NOT NULL,
    tong_tien NUMERIC(12, 2) NOT NULL CHECK (tong_tien >= 0),
    kenh TEXT NOT NULL,
    ghi_chu TEXT
);

INSERT INTO don_hang_idx
    (id, to_chuc_id, khach_hang_id,
     trang_thai, tao_luc, tong_tien, kenh, ghi_chu)
VALUES
    (101, 10, 501, 'MOI',           '2026-10-01 08:00+07', 150000, 'WEB', NULL),
    (102, 10, 502, 'DA_THANH_TOAN', '2026-10-01 09:00+07', 250000, 'APP', NULL),
    (103, 10, 501, 'DA_THANH_TOAN', '2026-10-02 09:00+07', 330000, 'WEB', NULL),
    (104, 20, 701, 'DA_THANH_TOAN', '2026-10-02 10:00+07', 420000, 'APP', NULL),
    (105, 10, 503, 'DANG_XU_LY',    '2026-10-03 08:00+07', 180000, 'WEB', 'Gấp'),
    (106, 10, 502, 'DA_THANH_TOAN', '2026-10-03 08:00+07', 510000, 'APP', NULL),
    (107, 20, 702, 'MOI',           '2026-10-03 09:00+07',  90000, 'WEB', NULL),
    (108, 10, 501, 'DA_HUY',        '2026-10-04 08:00+07', 120000, 'APP', NULL),
    (109, 10, 504, 'DA_THANH_TOAN', '2026-10-04 08:00+07', 700000, 'WEB', NULL),
    (110, 10, 503, 'DA_THANH_TOAN', '2026-10-05 09:00+07', 215000, 'APP', NULL),
    (111, 20, 701, 'DANG_XU_LY',    '2026-10-05 09:00+07', 340000, 'APP', NULL),
    (112, 10, 502, 'MOI',           '2026-10-05 09:00+07',  80000, 'WEB', NULL),
    (113, 10, 501, 'DA_THANH_TOAN', '2026-10-06 10:00+07', 460000, 'APP', NULL),
    (114, 20, 703, 'DA_THANH_TOAN', '2026-10-06 10:00+07', 610000, 'WEB', NULL),
    (115, 10, 503, 'DA_THANH_TOAN', '2026-10-07 09:00+07', 520000, 'WEB', NULL),
    (116, 10, 504, 'MOI',           '2026-10-07 09:00+07', 110000, 'APP', NULL),
    (117, 10, 502, 'DA_THANH_TOAN', '2026-10-08 11:00+07', 750000, 'WEB', NULL),
    (118, 20, 701, 'DA_HUY',        '2026-10-08 11:00+07',  50000, 'APP', NULL),
    (119, 10, 505, 'DANG_XU_LY',    '2026-10-09 12:00+07', 160000, 'WEB', NULL),
    (120, 10, 501, 'DA_THANH_TOAN', '2026-10-10 12:00+07', 810000, 'APP', NULL);

ANALYZE don_hang_idx;
~~~

Có **20 hàng**, trong đó tổ chức 10 có **15 hàng**, tổ chức 20 có **5 hàng**. Bảng có khóa chính `id` nên PostgreSQL đã tạo chỉ mục duy nhất trên `id`.

Kiểm tra:

~~~sql
SELECT to_chuc_id, trang_thai, COUNT(*) AS so_don
FROM don_hang_idx
GROUP BY to_chuc_id, trang_thai
ORDER BY to_chuc_id, trang_thai;

SELECT id, to_chuc_id, tao_luc, tong_tien
FROM don_hang_idx
ORDER BY tao_luc DESC, id DESC;
~~~

**Lưu ý về quy mô:** 20 hàng là quá nhỏ để mong planner nhất thiết chọn index. PostgreSQL có thể quyết định `Seq Scan` rẻ hơn `Index Scan`. Các ví dụ ở đây nhằm hiểu **cơ chế và thiết kế**, không dùng số liệu từ bảng 20 hàng để kết luận về hiệu năng ở hàng triệu hàng.

## 3. B-tree: loại index thường gặp nhất

**B-tree** phù hợp cho nhiều điều kiện lọc và sắp xếp có thứ tự:

- So sánh bằng: `=`;
- So sánh khoảng: `<`, `<=`, `>`, `>=`;
- Nhiều trường hợp `BETWEEN`, `IN`, `IS NULL`;
- `ORDER BY` tăng/giảm theo các cột được sắp phù hợp;
- Một số điều kiện tiền tố ký tự tùy collation/operator class.

Ví dụ:

~~~sql
CREATE INDEX idx_don_hang_org
ON don_hang_idx (to_chuc_id);
~~~

Truy vấn:

~~~sql
SELECT id, trang_thai, tong_tien
FROM don_hang_idx
WHERE to_chuc_id = 10;
~~~

Bộ tối ưu hóa **có thể** dùng index để tìm các hàng có khóa `to_chuc_id = 10`. Nhưng dữ liệu mẫu có **15/20 = 75%** hàng thuộc tổ chức 10; đọc phần lớn bảng qua index có thể không lợi bằng quét tuần tự.

### 3.1. Index là cấu trúc vật lý, không phải điều kiện nghiệp vụ

Câu:

~~~sql
CREATE INDEX idx_don_hang_org
ON don_hang_idx (to_chuc_id);
~~~

**không có nghĩa** chỉ những tổ chức đã tồn tại mới được INSERT, cũng không ngăn hai hàng cùng tổ chức. Đó là **non-unique index** hỗ trợ truy cập.

Muốn ràng buộc duy nhất:

~~~sql
-- Ví dụ trên bảng khác:
CREATE UNIQUE INDEX uq_ma_don_tren_to_chuc
ON don_hang (to_chuc_id, ma_don);
~~~

`UNIQUE` vừa là cấu trúc index vừa hỗ trợ **quy tắc dữ liệu**. Nhưng ngay cả unique index cũng có các chi tiết về `NULL` và collation khác nhau theo DBMS.

### 3.2. Một index không phải nhiều bản sao đã sắp

Index trên `(to_chuc_id, tao_luc)` giúp truy vấn sắp theo **to_chuc_id rồi tao_luc**, chứ không tự động giống hai index độc lập trên `to_chuc_id` và `tao_luc`. Cấu trúc nhiều cột có thứ tự khóa **từ trái sang phải**.

## 4. Độ chọn lọc và vì sao planner có thể bỏ qua index

Hai điều kiện:

~~~sql
WHERE id = 117
~~~

và:

~~~sql
WHERE to_chuc_id = 10
~~~

có thể có độ chọn lọc rất khác nhau. Với bảng mẫu:

- `id = 117` khớp **1/20 hàng**.
- `to_chuc_id = 10` khớp **15/20 hàng**.

**Selectivity** là tỷ lệ hàng khớp điều kiện (càng nhỏ nghĩa là càng chọn lọc). **Cardinality** trong ngữ cảnh planner thường liên quan đến số lượng hàng dự kiến của một tập kết quả hoặc số giá trị phân biệt của cột, tùy tài liệu đang dùng.

Một truy vấn `WHERE id = 117` thường có lý do rõ để dùng index khóa chính khi bảng đủ lớn. Với `WHERE to_chuc_id = 10` trả phần lớn bảng, việc đọc hết dữ liệu theo tuần tự có thể tốt hơn.

### 4.1. Đừng đưa ra quy tắc ngưỡng phần trăm cứng

Không có quy tắc toàn cầu như “index luôn nhanh nếu dưới 10% hàng”. Chi phí phụ thuộc:

- Kích thước hàng và kích thước index;
- Dữ liệu đang ở cache hay phải đọc đĩa;
- Độ tương quan giữa thứ tự trong index và cách hàng được lưu;
- Số cột cần trả (có cần đọc bảng gốc không);
- Số lần truy cập bảng ngẫu nhiên;
- Tốc độ I/O, CPU, bộ nhớ;
- Các phép JOIN, ORDER BY, GROUP BY và LIMIT phía sau.

Một điều kiện ít chọn lọc vẫn có thể hưởng lợi từ index nếu chỉ cần **một vài hàng đầu đúng thứ tự**; ngược lại, một điều kiện có vẻ chọn lọc nhưng tính toán/lookup tốn kém cũng không bảo đảm kế hoạch tốt.

### 4.2. Thống kê giúp planner ước lượng

PostgreSQL lưu thống kê về phân bố giá trị, số giá trị phân biệt và những đặc tính liên quan. Lệnh:

~~~sql
ANALYZE don_hang_idx;
~~~

giúp cập nhật thông tin thống kê cho bảng mẫu. Trên bảng lớn thay đổi nhiều, thống kê cũ có thể khiến planner **ước lượng sai số hàng**, từ đó chọn đường truy cập hoặc JOIN không phù hợp.

Không nên chỉ thêm index rồi bỏ qua **ANALYZE**, thông tin dữ liệu lệch phân bố, hoặc điều kiện nhiều cột có quan hệ thống kê với nhau.

## 5. Chỉ mục phục vụ WHERE như thế nào?

Câu:

~~~sql
SELECT id, tong_tien
FROM don_hang_idx
WHERE to_chuc_id = 10
  AND khach_hang_id = 501;
~~~

Nếu tạo index:

~~~sql
CREATE INDEX idx_don_hang_org_khach
ON don_hang_idx (to_chuc_id, khach_hang_id);
~~~

database có thể thu hẹp vùng index bằng cả hai điều kiện bằng.

Trong PostgreSQL, `EXPLAIN` có thể cho thấy:

~~~text
Index Scan using idx_don_hang_org_khach on don_hang_idx
  Index Cond: ((to_chuc_id = 10) AND (khach_hang_id = 501))
~~~

Đây là **hình minh họa có thể xuất hiện**, không phải stdout đo được từ bảng mẫu. Trên 20 hàng, kế hoạch thật có thể là Seq Scan.

### 5.1. Index Cond và Filter không phải một thứ

Trong plan PostgreSQL:

- **Index Cond**: phần điều kiện có thể được dùng để giới hạn hoặc kiểm tra qua cơ chế truy cập index của plan.
- **Filter**: điều kiện còn lại cần được áp dụng lên các hàng do node đã đọc.
- **Rows Removed by Filter**: số hàng bị loại ở bước Filter khi có thông số thực thi.

Ví dụ:

~~~sql
SELECT id, tong_tien
FROM don_hang_idx
WHERE to_chuc_id = 10
  AND tong_tien >= 500000;
~~~

Nếu chỉ có index trên `to_chuc_id`, điều kiện `tong_tien >= 500000` có thể phải được áp dụng như **Filter** sau khi lấy các hàng cùng tổ chức. Một index ghép hoặc index khác có thể giúp theo điều kiện và kế hoạch, nhưng không có nghĩa cứ đưa cả hai cột vào index là nhanh nhất.

### 5.2. Không phải mọi điều kiện WHERE đều truy cập index tốt

Ví dụ:

~~~sql
WHERE lower(ten_khach) = 'an'
~~~

Index B-tree thông thường trên `ten_khach` có thể không phục vụ được biểu thức `lower(ten_khach)` theo cách trực tiếp. Muốn index biểu thức có thể dùng **expression index** trong PostgreSQL; xem mục 12.

Index không hoạt động dựa trên “tên cột xuất hiện trong câu WHERE” đơn thuần, mà dựa trên **điều kiện có khớp khóa/biểu thức/toán tử mà index hỗ trợ hay không**.

## 6. Index nhiều cột: thứ tự cột rất quan trọng

Ví dụ cho màn hình đơn hàng:

~~~sql
SELECT id, tao_luc, tong_tien
FROM don_hang_idx
WHERE to_chuc_id = 10
  AND trang_thai = 'DA_THANH_TOAN'
  AND tao_luc >= TIMESTAMPTZ '2026-10-01 00:00:00+07'
ORDER BY tao_luc DESC, id DESC
LIMIT 5;
~~~

Một index có định hướng tương ứng:

~~~sql
CREATE INDEX idx_don_hang_loc_sap_xep
ON don_hang_idx (
    to_chuc_id,
    trang_thai,
    tao_luc DESC,
    id DESC
);
~~~

Ý tưởng:

1. `to_chuc_id = 10` thu hẹp theo tiền tố khóa thứ nhất.
2. `trang_thai = 'DA_THANH_TOAN'` tiếp tục thu hẹp theo khóa thứ hai.
3. Điều kiện khoảng trên `tao_luc` hỗ trợ tìm trong vùng thời gian.
4. `ORDER BY tao_luc DESC, id DESC` có thể tương thích với thứ tự đọc của index.
5. `LIMIT 5` có thể giúp dừng sau khi đủ kết quả, thay vì xử lý mọi hàng phù hợp.

### 6.1. Quy tắc tư duy “equality → range/order” 

Một heuristic hữu ích khi thiết kế B-tree nhiều cột là:

- Đưa những cột **lọc bằng** thường xuyên vào phần tiền tố;
- Sau đó cân nhắc cột **lọc khoảng hoặc sắp xếp**;
- Thêm khóa phân xử độc nhất nếu cần thứ tự ổn định;
- Không thêm mọi cột WHERE vô điều kiện.

Ví dụ:

~~~sql
CREATE INDEX idx_tra_cuu
ON don_hang_idx (to_chuc_id, trang_thai, tao_luc);
~~~

không có nghĩa một truy vấn chỉ có `WHERE tao_luc >= ...` sẽ luôn dùng index này hiệu quả ngang index bắt đầu bằng `tao_luc`.

### 6.2. Leftmost prefix: hiểu đúng và đừng tuyệt đối hóa

Với index `(A, B, C)`, các truy vấn:

| Điều kiện | Khả năng khai thác index ghép |
| --- | --- |
| `A = ?` | Thường khai thác tốt tiền tố |
| `A = ? AND B = ?` | Thường khai thác tốt hơn |
| `A = ? AND B = ? AND C >= ?` | Thường có thể thu hẹp theo tiền tố rồi khoảng |
| Chỉ `B = ?` | Không có tiền tố A; hiệu quả tùy DBMS, thống kê và kỹ thuật |
| Chỉ `C = ?` | Không có tiền tố A/B; thường không phải trường hợp lý tưởng |
| `A >= ? AND B = ?` | Phạm vi trên A có thể hạn chế khả năng thu hẹp tiếp bằng B |

Quy tắc tiền tố rất hữu ích, nhưng **không phải một định luật cấm planner sử dụng index** khi thiếu cột đầu. PostgreSQL ở các phiên bản phù hợp có thể dùng kỹ thuật như **skip scan** trong điều kiện thuận lợi; các DBMS cũng có thể quét index rồi filter, bitmap scan hoặc lựa chọn khác. Điều cần phân biệt là **index được dùng** và **index giảm được bao nhiêu công việc**.

### 6.3. Đổi thứ tự WHERE không đồng nghĩa đổi index

Hai câu:

~~~sql
WHERE to_chuc_id = 10 AND trang_thai = 'DA_THANH_TOAN'
~~~

và:

~~~sql
WHERE trang_thai = 'DA_THANH_TOAN' AND to_chuc_id = 10
~~~

tương đương logic với các cột không NULL của dữ liệu ví dụ. Thứ tự viết hai predicate trong `WHERE` **không ép planner tra theo thứ tự đó**. Điều quan trọng là **thứ tự cột trong định nghĩa index** và mô hình truy vấn.

### 6.4. Đừng thiết kế hai cột bằng nhau theo khẩu hiệu duy nhất

Với hai điều kiện `A = ? AND B = ?`, việc cột A hay B đứng trước trong index còn phụ thuộc:

- Có truy vấn chỉ lọc theo A hay chỉ B không?
- Có cần ORDER BY sau khi lọc một trong hai?
- Dữ liệu phân bố lệch không?
- Các truy vấn khác có dùng cùng index?
- Index có phục vụ cả JOIN và LIMIT không?

Tập **workload** quyết định thứ tự cột tối ưu, không phải chỉ một câu khẩu hiệu “cột có độ chọn lọc lớn nhất luôn đứng trước”.

## 7. Index có thể phục vụ ORDER BY và LIMIT

Ngay cả khi WHERE không quá chọn lọc, index có thể hữu ích nếu truy vấn cần **lấy vài hàng đầu theo thứ tự**.

~~~sql
CREATE INDEX idx_don_hang_moi_nhat
ON don_hang_idx (to_chuc_id, tao_luc DESC, id DESC);

SELECT id, tao_luc, tong_tien
FROM don_hang_idx
WHERE to_chuc_id = 10
ORDER BY tao_luc DESC, id DESC
LIMIT 3;
~~~

Đối với dữ liệu mẫu, ba đơn mới nhất của tổ chức 10 là **120, 119, 117**. Index có thể giúp trả các hàng ấy mà không cần sort một tập lớn, nếu plan phù hợp.

### 7.1. Khóa phân xử ổn định

Nếu chỉ dùng:

~~~sql
ORDER BY tao_luc DESC
~~~

hai đơn cùng `tao_luc` có thể **đồng hạng**. SQL không quy định thứ tự tương đối giữa các hàng đồng giá trị. Dùng:

~~~sql
ORDER BY tao_luc DESC, id DESC
~~~

để có **thứ tự toàn phần** khi `id` là duy nhất.

### 7.2. Index giảm sort nhưng không luôn loại mọi sort

Nếu index là:

~~~sql
ON don_hang_idx (to_chuc_id, tao_luc DESC)
~~~

và truy vấn sắp theo `tao_luc DESC, id DESC`, index đã cung cấp một phần thứ tự. Planner có thể cần sắp xếp bổ sung theo `id`, hoặc dùng **incremental sort** tùy phiên bản và kế hoạch.

Nếu truy vấn đổi sang:

~~~sql
ORDER BY tong_tien DESC
~~~

index theo `tao_luc` không tự nhiên cung cấp thứ tự tổng tiền. Muốn tối ưu, cần xét một index khác hoặc chấp nhận bước Sort.

### 7.3. Keyset pagination và index

Trang tiếp theo của màn hình đơn mới nhất thường có thể dùng keyset:

~~~sql
SELECT id, tao_luc, tong_tien
FROM don_hang_idx
WHERE to_chuc_id = 10
  AND (tao_luc, id) <
      (TIMESTAMPTZ '2026-10-08 11:00:00+07', 117)
ORDER BY tao_luc DESC, id DESC
LIMIT 3;
~~~

Cặp điều kiện `<` tương ứng với việc đi **sau** mốc (tao_luc, id) trong thứ tự giảm dần. Index `(to_chuc_id, tao_luc DESC, id DESC)` có thể giúp.

Không dùng `OFFSET 100000` như giải pháp mặc định cho trang sâu: ngay cả khi dùng index, engine vẫn có thể cần đi qua lượng lớn hàng bị bỏ qua. Keyset có thể hiệu quả hơn, nhưng đòi hỏi khóa sắp xếp ổn định và hợp đồng phân trang phù hợp.

## 8. Index phục vụ JOIN

Một JOIN phổ biến:

~~~sql
SELECT
    k.id,
    k.ten,
    d.id AS don_hang_id,
    d.tong_tien
FROM khach_hang AS k
JOIN don_hang AS d
  ON d.khach_hang_id = k.id
WHERE k.id = 501;
~~~

Nếu `khach_hang.id` là khóa chính, bảng khách có index tương ứng. Với nhiều đơn trên mỗi khách, index:

~~~sql
CREATE INDEX idx_don_hang_khach
ON don_hang (khach_hang_id);
~~~

có thể giúp tìm các đơn khớp `k.id`. Đây là mẫu đặc biệt hữu ích khi planner chọn **Nested Loop Join**: mỗi khách từ phía ngoài dẫn tới một lần tìm các đơn ở phía trong.

### 8.1. Khóa ngoại không phải lúc nào cũng tự tạo index

Một số hệ quản trị không tự tạo index trên **cột tham chiếu khóa ngoại ở bảng con** chỉ vì có FOREIGN KEY. Trong PostgreSQL, khai báo:

~~~sql
FOREIGN KEY (khach_hang_id) REFERENCES khach_hang(id)
~~~

không tự tạo index trên `don_hang.khach_hang_id`. Khóa được tham chiếu phía cha thường có ràng buộc PK/UNIQUE với index, nhưng phía con có thể cần index riêng để tối ưu JOIN, kiểm tra/xóa/cập nhật hàng cha.

**Không có nghĩa mọi FK đều cần index riêng:** hãy xét kích thước, tần suất JOIN, DML và các index ghép đã có.

### 8.2. Index không ép planner dùng Nested Loop

Một JOIN trên bảng lớn có thể phù hợp với:

- **Nested Loop**: thường thuận lợi nếu phía ngoài ít hàng và phía trong có index tốt.
- **Hash Join**: có thể hiệu quả khi đọc nhiều hàng và so khớp theo khóa bằng bảng băm.
- **Merge Join**: tận dụng đầu vào đã sắp hoặc có thể sắp hiệu quả, phù hợp điều kiện nối tương ứng.

Một index mới có thể thay đổi lựa chọn plan, nhưng **Hash Join quét tuần tự** đôi khi nhanh hơn hàng triệu lần tra index ngẫu nhiên.

### 8.3. JOIN đa tổ chức cần khóa đúng

Nếu hệ thống có cùng `khach_hang_id` ở nhiều tổ chức, điều kiện JOIN chỉ theo `khach_hang_id` có thể ghép sai dữ liệu. Mẫu đúng khi business key là ghép:

~~~sql
ON d.to_chuc_id = k.to_chuc_id
AND d.khach_hang_id = k.id
~~~

Khi đó cần xem xét index `(to_chuc_id, khach_hang_id)` ở phía phù hợp. **Index không sửa được JOIN sai về mặt logic**.

## 9. Index trong GROUP BY và DISTINCT

Truy vấn tổng hợp:

~~~sql
SELECT khach_hang_id, COUNT(*) AS so_don
FROM don_hang_idx
WHERE to_chuc_id = 10
GROUP BY khach_hang_id;
~~~

Index:

~~~sql
CREATE INDEX idx_don_hang_org_nhom_khach
ON don_hang_idx (to_chuc_id, khach_hang_id);
~~~

có thể giúp đọc các hàng của tổ chức 10 theo thứ tự `khach_hang_id`, thuận lợi cho một số kế hoạch tổng hợp theo nhóm.

Tuy nhiên, PostgreSQL có thể chọn **HashAggregate**, **GroupAggregate** hoặc phương án khác. Index **không tự động biến COUNT(*) thành O(1)**: database vẫn phải xác định những hàng thực sự được tính theo snapshot MVCC và điều kiện truy vấn.

### 9.1. DISTINCT có thể hưởng lợi từ thứ tự index

~~~sql
SELECT DISTINCT khach_hang_id
FROM don_hang_idx
WHERE to_chuc_id = 10
ORDER BY khach_hang_id;
~~~

Index `(to_chuc_id, khach_hang_id)` có thể đưa các giá trị giống nhau gần nhau, thuận tiện cho xử lý unique/streaming. Nhưng kế hoạch có thể khác nếu tập dữ liệu nhỏ hoặc planner đánh giá hash/sort tốt hơn.

### 9.2. Index không thay định nghĩa grain

Nếu JOIN làm một đơn xuất hiện nhiều hàng, thêm index không làm `COUNT(*)` tự trở về đếm số đơn duy nhất. Phải xử lý **mức chi tiết của kết quả** bằng JOIN đúng hoặc `COUNT(DISTINCT d.id)` khi nghiệp vụ yêu cầu.

## 10. Covering index và Index Only Scan

Một truy vấn cần trả:

~~~sql
SELECT tao_luc, id, tong_tien
FROM don_hang_idx
WHERE to_chuc_id = 10
ORDER BY tao_luc DESC, id DESC
LIMIT 20;
~~~

Nếu index chỉ chứa `to_chuc_id, tao_luc, id`, cột `tong_tien` cần lấy từ bảng gốc. PostgreSQL hỗ trợ **INCLUDE** để mang thêm cột payload vào B-tree mà không biến nó thành cột khóa sắp xếp:

~~~sql
CREATE INDEX idx_don_hang_cover
ON don_hang_idx (to_chuc_id, tao_luc DESC, id DESC)
INCLUDE (tong_tien);
~~~

| Thành phần | Vai trò |
| --- | --- |
| `to_chuc_id` | Khóa lọc |
| `tao_luc DESC` | Khóa hỗ trợ sắp xếp/thời gian |
| `id DESC` | Khóa phân xử thứ tự |
| `INCLUDE (tong_tien)` | Cột payload để có thể đọc từ index |

### 10.1. Index Only Scan không bảo đảm “không hề đụng heap”

PostgreSQL sử dụng **MVCC**. Một index entry không tự chứa mọi thông tin xác định phiên bản hàng có thể nhìn thấy đối với transaction hiện tại. **Index Only Scan** chỉ tránh đọc heap hiệu quả nếu **visibility map** cho biết các trang dữ liệu tương ứng đã đủ điều kiện nhìn thấy; nếu không, engine vẫn có thể phải kiểm tra heap.

Vì vậy, `EXPLAIN (ANALYZE, BUFFERS)` có thể hiển thị:

~~~text
Index Only Scan using idx_don_hang_cover ...
  Heap Fetches: ...
~~~

`Heap Fetches` lớn không phải bằng chứng index hỏng; có thể do trạng thái visibility, bảng cập nhật thường xuyên hoặc điều kiện hiện tại. Một index bao phủ các cột **là điều kiện cần cho nhiều index-only scan**, nhưng chưa chắc đủ.

### 10.2. INCLUDE không miễn phí

Cột INCLUDE làm index lớn hơn, tăng chi phí ghi, lưu trữ và cache. Không đưa toàn bộ cột SELECT vào INCLUDE theo thói quen, đặc biệt cột TEXT/JSON lớn hoặc thường thay đổi. Index quá rộng có thể chậm hơn giải pháp đọc bảng gốc với số ít hàng.

### 10.3. Covering phụ thuộc DBMS

MySQL/InnoDB, SQL Server và PostgreSQL có khái niệm/triển khai khác nhau của việc truy vấn được đáp ứng từ index. Ví dụ SQL Server có nonclustered index với INCLUDE và có thể phát sinh **Key Lookup** nếu thiếu cột; MySQL InnoDB secondary index chứa khóa chính, nhưng không dùng cú pháp INCLUDE theo PostgreSQL.

## 11. Partial index: chỉ đánh index những hàng quan trọng

Một hàng đợi có rất nhiều đơn đã hoàn tất nhưng rất ít đơn `MOI` hoặc `DANG_XU_LY`. Nếu ứng dụng chủ yếu lấy đơn chờ xử lý, có thể tạo **partial index** trên tập con:

~~~sql
CREATE INDEX idx_don_hang_cho_xu_ly
ON don_hang_idx (to_chuc_id, tao_luc, id)
WHERE trang_thai = 'MOI';
~~~

Truy vấn phù hợp:

~~~sql
SELECT id, tao_luc
FROM don_hang_idx
WHERE to_chuc_id = 10
  AND trang_thai = 'MOI'
ORDER BY tao_luc, id
LIMIT 10;
~~~

Index này **không chứa** các hàng trạng thái khác. Nó có thể nhỏ và hiệu quả nếu `MOI` chiếm tỷ lệ rất ít trên bảng lớn.

### 11.1. Điều kiện truy vấn phải suy ra được predicate của index

Partial index:

~~~sql
WHERE trang_thai = 'MOI'
~~~

chỉ có thể dùng khi planner **chứng minh được** truy vấn cần những hàng thuộc tập ấy. Nếu câu SQL:

~~~sql
WHERE trang_thai IN ('MOI', 'DA_THANH_TOAN')
~~~

thì partial index chỉ chứa MOI **không bao phủ toàn bộ tập kết quả**, nên không thể tự thay thế mọi đường truy cập cần thiết.

Ngoài ra, với một prepared statement có tham số:

~~~sql
WHERE trang_thai = $1
~~~

planner dùng **generic plan** có thể không biết `$1` luôn là 'MOI', nên không nhất thiết chọn partial index dù phần lớn các lần chạy truyền giá trị đó. Hiệu quả của index phụ thuộc **cách chuẩn bị kế hoạch và khả năng chứng minh predicate tại planning time**.

### 11.2. Khi nào tránh partial index?

Không nhất thiết tạo partial index nếu trạng thái thay đổi liên tục, truy vấn dùng nhiều trạng thái khác nhau, hoặc predicate khó khớp với cách viết câu SQL của ứng dụng. Cần đánh giá lợi ích đọc so với chi phí index maintenance trên mỗi chuyển trạng thái.

## 12. Expression index: index trên biểu thức

Truy vấn tìm email không phân biệt chữ hoa thường:

~~~sql
SELECT id
FROM khach_hang
WHERE lower(email) = 'an@example.test';
~~~

Index thông thường trên `email` có thể không được sử dụng tối ưu cho biểu thức `lower(email)`. PostgreSQL cho phép tạo index trên **biểu thức**:

~~~sql
CREATE INDEX idx_khach_email_lower
ON khach_hang (lower(email));
~~~

Khi điều kiện WHERE sử dụng biểu thức phù hợp, planner có thể dùng index này.

### 12.1. Bài toán chuẩn hóa dữ liệu

Tìm email không phân biệt chữ hoa thường không chỉ là hiệu năng. Cần xác định semantics:

- So khớp theo collation nào?
- Bỏ khoảng trắng trước/sau không?
- Có cần xử lý Unicode, ký tự đặc biệt, chuẩn hóa địa chỉ?
- Duy nhất theo email chuẩn hóa hay theo email gốc?
- Có cột chuẩn hóa riêng hoặc kiểu dữ liệu/collation phù hợp không?

Index expression **không tự định nghĩa đúng nghiệp vụ**. Nếu muốn ràng buộc duy nhất theo biểu thức, PostgreSQL còn có unique expression index trong các trường hợp phù hợp.

### 12.2. Tránh bọc cột ngày trong hàm khi có thể viết khoảng

Một câu thường gặp:

~~~sql
SELECT id
FROM don_hang_idx
WHERE (tao_luc AT TIME ZONE 'Asia/Ho_Chi_Minh')::date
      = DATE '2026-10-05';
~~~

Điều kiện đúng về ngày địa phương nhưng có thể khó khai thác một index B-tree thông thường chỉ trên `tao_luc` vì cột được đưa vào biểu thức. Khi biết biên ngày và múi giờ, có thể viết **khoảng nửa mở** trên chính timestamp:

~~~sql
SELECT id
FROM don_hang_idx
WHERE tao_luc >= TIMESTAMPTZ '2026-10-05 00:00:00+07'
  AND tao_luc <  TIMESTAMPTZ '2026-10-06 00:00:00+07';
~~~

Khoảng này mô tả đúng ngày 05/10 trong múi giờ UTC+07 cố định ở ví dụ và có thể phục vụ index trên `tao_luc`. Với khu vực có DST, phải tính **hai mốc nửa đêm theo múi giờ nghiệp vụ** thay vì mặc định cộng 24 giờ tuyệt đối cho mọi ngày.

### 12.3. CAST không cần thiết có thể ảnh hưởng truy cập

Ví dụ:

~~~sql
WHERE id::text = '117'
~~~

khác về cách truy cập với:

~~~sql
WHERE id = 117
~~~

Index B-tree trên `id BIGINT` thường phù hợp tự nhiên với phép so sánh numeric đúng kiểu. Ép cột sang TEXT có thể khiến planner khó dùng index đó theo toán tử/biểu thức hiện hành. Nên **bind tham số đúng kiểu**, không đổi kiểu cột tùy tiện chỉ để tránh xử lý kiểu ở ứng dụng.

## 13. LIKE, tiền tố và tìm kiếm chuỗi

Một truy vấn:

~~~sql
WHERE ma_don LIKE 'WEB-%'
~~~

có **tiền tố cố định**. Trong PostgreSQL, B-tree index có thể giúp một số truy vấn LIKE tiền tố, tùy collation và **operator class**, ví dụ các trường hợp dùng `text_pattern_ops`:

~~~sql
CREATE INDEX idx_ma_don_pattern
ON don_hang (ma_don text_pattern_ops);
~~~

Nhưng truy vấn:

~~~sql
WHERE ma_don LIKE '%2026%'
~~~

có ký tự đại diện **ở đầu**. Một B-tree thông thường không thể đi thẳng tới một khoảng khóa liên tiếp cho mọi chuỗi chứa '2026' ở vị trí bất kỳ.

Tại PostgreSQL, tùy bài toán có thể xem xét extension **pg_trgm** và index GIN/GiST cho tìm kiếm tương tự hoặc LIKE/ILIKE phù hợp. Không biến `LIKE '%...%'` thành `LIKE '...%'` chỉ để index chạy nhanh nếu điều đó **thay đổi ngữ nghĩa kết quả**.

### 13.1. Index không thay thế công cụ full-text search

Tìm kiếm nhiều từ, stemming, ranking, ngôn ngữ và phân tích văn bản thường cần cơ chế **full-text search** phù hợp (ví dụ `tsvector`/GIN ở PostgreSQL) hoặc hệ thống tìm kiếm chuyên biệt. Index B-tree trên cột TEXT không tự giải quyết mọi truy vấn tìm kiếm nội dung.

## 14. OR, IN và kết hợp nhiều index

Ví dụ:

~~~sql
SELECT id
FROM don_hang_idx
WHERE khach_hang_id = 501
   OR khach_hang_id = 502;
~~~

Planner có thể dùng index trên `khach_hang_id`, xử lý `OR` hoặc biến đổi tương đương tùy hệ quản trị. Viết:

~~~sql
WHERE khach_hang_id IN (501, 502)
~~~

thường rõ nghĩa cho danh sách giá trị thuộc cùng cột, nhưng hiệu năng vẫn cần xem plan thực tế.

### 14.1. PostgreSQL BitmapOr và BitmapAnd

Khi có nhiều index đơn cột, PostgreSQL có thể sử dụng:

- `Bitmap Index Scan` từ một hoặc nhiều index;
- `BitmapOr` để hợp các tập ứng viên;
- `BitmapAnd` để giao các tập ứng viên;
- `Bitmap Heap Scan` để đọc các trang/hàng tương ứng ở bảng.

Ví dụ:

~~~sql
CREATE INDEX idx_don_hang_khach
ON don_hang_idx (khach_hang_id);

CREATE INDEX idx_don_hang_trang_thai
ON don_hang_idx (trang_thai);

SELECT id, tong_tien
FROM don_hang_idx
WHERE khach_hang_id = 501
  AND trang_thai = 'DA_THANH_TOAN';
~~~

Trên bảng lớn, planner **có thể** kết hợp hai index. Nhưng không nhất thiết luôn làm vậy: index ghép, index đơn, seq scan, hoặc phương án khác có thể có chi phí thấp hơn.

**Lưu ý về thứ tự:** bitmap heap scan thường không giữ thứ tự khóa B-tree. Nếu còn `ORDER BY`, có thể cần Sort. Đây là lý do đôi khi một **Index Scan theo index ghép** phù hợp hơn kết hợp nhiều index riêng trong truy vấn có LIMIT và ORDER BY.

## 15. Index duy nhất, PRIMARY KEY và NULL

Khóa chính:

~~~sql
CREATE TEMP TABLE san_pham_idx (
    id BIGINT PRIMARY KEY,
    ma_sku TEXT NOT NULL UNIQUE,
    ten TEXT NOT NULL
);
~~~

PostgreSQL tự tạo index duy nhất để thực thi các ràng buộc PRIMARY KEY và UNIQUE thích hợp. Vì vậy, không cần mặc định tạo thêm index `ON san_pham_idx(id)` chỉ để phục vụ điều kiện `WHERE id = ...`: có thể là index trùng không cần thiết.

### 15.1. UNIQUE có ý nghĩa khác nhau với NULL

Trong nhiều DBMS, UNIQUE cho phép nhiều giá trị NULL tùy kiểu ràng buộc, phiên bản và thiết lập. PostgreSQL mặc định xem các NULL là **khác nhau** cho unique constraint/index, nhưng PostgreSQL 15+ có lựa chọn `NULLS NOT DISTINCT`:

~~~sql
-- PostgreSQL 15+; chỉ là ví dụ độc lập:
CREATE UNIQUE INDEX uq_ma_phu_mot_null
ON bang_co_ma_phu (ma_phu) NULLS NOT DISTINCT;
~~~

Bảng `bang_co_ma_phu` ở đây là bảng **giả định**, không thuộc dữ liệu thực hành. Tránh coi quy tắc UNIQUE-NULL là giống hệt giữa SQL Server, Oracle, MySQL, SQLite và PostgreSQL.

### 15.2. Index có thể hỗ trợ IS NULL

Một số người nghĩ B-tree không chứa thông tin NULL. Trong PostgreSQL, B-tree có thể được dùng cho điều kiện `IS NULL` hoặc `IS NOT NULL` tùy index và kế hoạch. Tuy nhiên, nếu đa số hàng đều NULL, độ chọn lọc thấp có thể khiến seq scan hợp lý hơn.

## 16. Các loại index không chỉ có B-tree

PostgreSQL cung cấp nhiều **index access methods**, phù hợp những loại toán tử và dữ liệu khác nhau.

| Loại | Mục đích thường gặp | Ví dụ điều kiện |
| --- | --- | --- |
| **B-tree** | Bằng, so sánh phạm vi, sắp xếp | `id = ?`, `tao_luc >= ?`, ORDER BY |
| **Hash** | So sánh bằng | `cot = ?` |
| **GIN** | Dữ liệu có nhiều phần tử/token: array, JSONB, full-text, trigram tùy operator class | `tags @> ARRAY[...]`, JSONB containment |
| **GiST** | Range, hình học, tìm kiếm gần nhau và nhiều loại toán tử đặc thù | Toán tử range/spatial |
| **BRIN** | Bảng rất lớn, dữ liệu có liên hệ mạnh với vị trí trang, ví dụ thời gian tăng theo append | Lọc khoảng thời gian trên log lớn |
| **SP-GiST** | Một số kiểu dữ liệu/phân hoạch không gian phù hợp | Truy vấn hình học/đặc thù |

### 16.1. GIN cho JSONB

Ví dụ bảng giả định:

~~~sql
CREATE TABLE su_kien_json (
    id BIGINT PRIMARY KEY,
    payload JSONB NOT NULL
);

CREATE INDEX idx_su_kien_payload_gin
ON su_kien_json USING GIN (payload);

SELECT id
FROM su_kien_json
WHERE payload @> '{"loai":"LOGIN"}'::jsonb;
~~~

GIN thường hữu ích cho truy vấn containment với operator class tương ứng. Nhưng nếu ứng dụng chủ yếu lọc theo **một trường JSON cố định**, một expression index trên biểu thức như `payload->>'loai'` có thể phù hợp hơn. Không có một index JSON “tốt nhất” cho mọi predicate.

### 16.2. BRIN cho log thời gian rất lớn

Nếu hàng log được thêm gần theo thời gian và vị trí lưu dữ liệu tương quan với `xay_ra_luc`:

~~~sql
CREATE INDEX idx_log_time_brin
ON nhat_ky_lon USING BRIN (xay_ra_luc);
~~~

BRIN lưu thông tin tóm tắt theo phạm vi trang và thường có kích thước index nhỏ. Nó có thể giúp **loại bỏ nhiều vùng trang** không chứa thời gian cần tìm, nhưng là phương pháp **lossy** trong nhiều trường hợp: engine phải đọc/recheck các hàng thuộc phạm vi có khả năng khớp.

BRIN không thay thế B-tree khi yêu cầu tìm **một ID duy nhất** trong bảng và cần lookup rất chọn lọc. Bảng `nhat_ky_lon` chỉ là mô hình minh họa, chưa được tạo ở mục 2.

## 17. Khi nào index không giúp nhiều?

Một số tình huống:

1. **Bảng quá nhỏ:** đọc toàn bảng nhanh hơn tìm cây rồi đọc heap.
2. **Điều kiện ít chọn lọc:** truy vấn đọc phần lớn hàng.
3. **Trả nhiều cột lớn:** index chỉ giúp tìm khóa, vẫn phải lấy dữ liệu gốc.
4. **Predicate không khớp index:** CAST, hàm, toán tử hoặc collation khác.
5. **Đặt sai thứ tự cột của index ghép:** thiếu tiền tố dùng trong workload quan trọng.
6. **ORDER BY khác thứ tự index:** phải sort bổ sung.
7. **Thống kê sai/cũ:** planner ước lượng không chính xác.
8. **Index quá rộng hoặc nhiều index trùng:** chi phí ghi và cache tăng.
9. **Việc đọc bị chi phối bởi JOIN/tổng hợp:** thời gian không nằm ở nơi index có thể rút ngắn.
10. **Tải giao dịch đang tranh chấp:** khóa, WAL, I/O hay replication mới là nút thắt.

Không nên kết luận “index không có tác dụng” chỉ vì `EXPLAIN` trên bảng 20 dòng vẫn hiển thị `Seq Scan`.

## 18. Đọc EXPLAIN ở mức SQL

PostgreSQL:

~~~sql
EXPLAIN
SELECT id, tao_luc, tong_tien
FROM don_hang_idx
WHERE to_chuc_id = 10
  AND trang_thai = 'DA_THANH_TOAN'
ORDER BY tao_luc DESC, id DESC
LIMIT 5;
~~~

`EXPLAIN` trả **kế hoạch dự kiến**, không chạy SELECT lấy kết quả cho client. Có thể thấy các node như:

| Node | Diễn giải |
| --- | --- |
| `Seq Scan` | Đọc bảng theo hướng quét tuần tự |
| `Index Scan` | Đi qua index và có thể đọc heap |
| `Index Only Scan` | Dùng dữ liệu index, có thể cần heap fetch để kiểm tra visibility |
| `Bitmap Index Scan` | Tạo tập vị trí ứng viên từ index |
| `Bitmap Heap Scan` | Đọc các trang/hàng theo bitmap |
| `Sort` | Sắp xếp dữ liệu |
| `Incremental Sort` | Tận dụng một phần thứ tự có sẵn |
| `Limit` | Trả tối đa số hàng yêu cầu |
| `Nested Loop` | Nối lặp, có thể tra index phía trong |
| `Hash Join` | Dùng bảng băm để nối |
| `Merge Join` | Nối theo đầu vào được sắp |
| `HashAggregate` / `GroupAggregate` | Tính kết quả tổng hợp |

### 18.1. EXPLAIN ANALYZE

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT id, tao_luc, tong_tien
FROM don_hang_idx
WHERE to_chuc_id = 10
  AND trang_thai = 'DA_THANH_TOAN'
ORDER BY tao_luc DESC, id DESC
LIMIT 5;
~~~

Khác với EXPLAIN thường, **ANALYZE thực thi câu truy vấn** để đo actual rows, actual time và loops. `BUFFERS` báo hoạt động bộ đệm, giúp phân biệt phần nào của truy vấn đọc dữ liệu.

Trong kết quả, phân biệt:

- **cost**: đơn vị chi phí nội bộ ước lượng của planner, không phải milliseconds;
- **rows** trong kế hoạch ước lượng: số hàng dự kiến;
- **actual rows**: số hàng thực tế trên mỗi lần loop của node, đọc cùng `loops`;
- **actual time**: thời gian thực thi đo được, bị ảnh hưởng bởi cache, tải hệ thống và môi trường;
- **Rows Removed by Filter**: hàng bị loại ở bước filter khi có đo thực tế;
- **Buffers**: số truy cập buffer theo loại như hit/read (cần hiểu ý nghĩa thống kê từng mục).

### 18.2. Ví dụ giả định đọc plan

~~~text
Limit
  -> Index Scan using idx_don_hang_loc_sap_xep on don_hang_idx
       Index Cond: ((to_chuc_id = 10)
                    AND (trang_thai = 'DA_THANH_TOAN'))
~~~

Diễn giải: planner có thể lần theo index để tìm các hàng của tổ chức và trạng thái, trong thứ tự hữu ích cho LIMIT. Đây **không phải output được xác nhận của bộ dữ liệu 20 hàng**, chỉ là minh họa cách đọc.

Một plan khác hoàn toàn có thể hợp lý:

~~~text
Limit
  -> Sort
       Sort Key: tao_luc DESC, id DESC
       -> Seq Scan on don_hang_idx
            Filter: ((to_chuc_id = 10) AND ...)
~~~

Trên bảng nhỏ, vài thao tác quét và sort trong bộ nhớ có thể rẻ hơn mở index scan.

### 18.3. Không đánh giá chỉ bằng một lần đo

Muốn so trước/sau tạo index trên hệ thống thật:

1. Dùng dữ liệu đủ đại diện và có phân bố hợp lý;
2. Giữ nguyên câu SQL và tham số;
3. Cập nhật thống kê thích hợp;
4. Quan sát nhiều lần dưới trạng thái cache/tải được ghi nhận;
5. So **actual time**, I/O và số hàng đọc;
6. Kiểm tra tác động của index tới INSERT/UPDATE/DELETE;
7. Xem plan với các trường hợp tham số hiếm gặp lẫn phổ biến.

Tránh chụp một lần thời gian rồi tuyên bố index A luôn nhanh hơn index B trong mọi workload.

### 18.4. Chú ý EXPLAIN ANALYZE cho DML

Nếu áp dụng:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
UPDATE don_hang_idx
SET trang_thai = 'DA_HUY'
WHERE id = 101;
~~~

thì lệnh **thực sự cập nhật dữ liệu**. Trong môi trường thử nghiệm có thể đặt trong transaction rồi ROLLBACK, nhưng không coi rollback là bảo đảm hoàn nguyên mọi side effect (như sequence hoặc hệ thống ngoài). Không chạy DML EXPLAIN ANALYZE trên production theo thói quen.

## 19. Index và chi phí ghi

Index không phải tài nguyên miễn phí. Mỗi khi INSERT một hàng, database có thể phải cập nhật các index liên quan. Khi UPDATE cột làm thay đổi khóa index, các entry index có thể cần thay đổi; DELETE cũng tạo việc phải dọn theo cơ chế lưu trữ.

| Hoạt động | Tác động có thể có từ index |
| --- | --- |
| SELECT lọc chọn lọc | Có thể giảm lượng dữ liệu phải đọc |
| SELECT ORDER BY LIMIT | Có thể tránh sort và dừng sớm |
| INSERT | Ghi thêm entry index, tăng log/I/O |
| UPDATE khóa index | Thêm công việc cập nhật cấu trúc index |
| DELETE | Tạo công việc dọn, xử lý phiên bản theo DBMS |
| VACUUM/maintenance | Cần quản lý dead tuples/index bloat theo cơ chế DBMS |
| Backup/storage | Tăng không gian và thời gian vận hành |

### 19.1. Không tạo index cho mọi cột

Một bảng có 30 cột không cần mặc định 30 index đơn cột. Việc đó có thể:

- Gây tải ghi và storage lớn;
- Tăng chi phí vacuum/reindex/backup;
- Khiến optimizer có nhiều phương án nhưng không tăng chất lượng plan tương xứng;
- Trùng với các index ghép và khóa chính đã có.

Index nên xuất phát từ **truy vấn thật và ràng buộc cần thiết**, không phải từ số lượng cột.

### 19.2. Index trùng hoặc gần trùng

Nếu đã có:

~~~sql
CREATE INDEX idx_org_created
ON don_hang_idx (to_chuc_id, tao_luc);
~~~

thêm:

~~~sql
CREATE INDEX idx_org
ON don_hang_idx (to_chuc_id);
~~~

có thể **trùng công dụng cho nhiều truy vấn chỉ lọc to_chuc_id**. Tuy nhiên index đơn thường nhỏ hơn index ghép và có thể mang lợi ích riêng; không xóa index chỉ dựa vào hình dạng định nghĩa mà chưa xem workload, kích thước, tần suất sử dụng và DML.

### 19.3. Tạo index trên bảng lớn cần tính tác động vận hành

PostgreSQL hỗ trợ `CREATE INDEX CONCURRENTLY` trong ngữ cảnh phù hợp để giảm một số dạng chặn ghi, nhưng có giới hạn (ví dụ **không chạy trong transaction block**) và chi phí xây dựng riêng. Không dùng tùy tiện với bảng tạm hay trên môi trường production mà không đọc điều kiện áp dụng.

Ngoài ra cần cân nhắc index bloat, VACUUM, REINDEX, replication lag, dung lượng trống và maintenance window.

## 20. Partitioning và index

Nếu bảng đơn hàng được partition theo tháng hoặc tổ chức, database có thể **prune** những partition không liên quan khi WHERE có điều kiện phù hợp. Điều đó có thể giảm rất nhiều dữ liệu cần đọc trước cả việc chọn index bên trong partition.

Ví dụ tư duy:

~~~sql
WHERE tao_luc >= TIMESTAMPTZ '2026-10-01 00:00:00+07'
  AND tao_luc <  TIMESTAMPTZ '2026-11-01 00:00:00+07'
~~~

Nếu partition theo phạm vi `tao_luc` phù hợp, planner có thể giới hạn partition cần quét. Nhưng index và partitioning phục vụ các mục đích **bổ sung nhau**; phân vùng không có nghĩa mọi truy vấn tự trở nên nhanh hoặc mọi partition đều cần cùng tập index.

Với PostgreSQL partitioned table, cách tạo/đính index trên partition, hỗ trợ unique constraint và khóa partition cần tuân thủ các quy tắc riêng. Thiết kế phải dựa trên query patterns và cách quản lý dữ liệu dài hạn.

## 21. Khác biệt giữa các hệ quản trị

Các khái niệm `WHERE`, `ORDER BY`, selectivity và query optimizer có mặt ở nhiều DBMS, nhưng **cách lưu index và cú pháp** khác nhau.

| Chủ đề | PostgreSQL | MySQL/InnoDB | SQL Server | SQLite | Oracle |
| --- | --- | --- | --- | --- | --- |
| Index mặc định phổ biến | B-tree | B-tree trong InnoDB | Clustered/nonclustered B-tree | B-tree | B-tree và loại khác |
| Bảng và index | Heap tách với B-tree | Clustered PK tổ chức hàng; secondary chứa PK | Clustered index tổ chức dữ liệu khi được chọn; nonclustered có locator | Bảng rowid và index riêng hoặc WITHOUT ROWID | Heap table, index-organized table tùy thiết kế |
| Index đa cột | Có | Có | Có | Có | Có |
| Covering | `INCLUDE` và Index Only Scan với MVCC/visibility | Secondary index bao phủ cột có thể dùng “Using index” | Nonclustered `INCLUDE`, Key Lookup | Covering index theo query plan | Index-only khả thi trong trường hợp phù hợp |
| Partial/filtered | Partial index | Không có cú pháp partial index PostgreSQL tương đương trực tiếp | Filtered index | Partial index | Có cơ chế/chiến lược khác |
| Expression/function | Expression index | Functional index và generated column tùy phiên bản | Computed column/index có điều kiện | Expression index | Function-based index |
| Xem plan | `EXPLAIN (ANALYZE, BUFFERS)` | `EXPLAIN`, `EXPLAIN ANALYZE` theo phiên bản | Actual/estimated execution plan | `EXPLAIN QUERY PLAN` | `EXPLAIN PLAN`, DBMS_XPLAN |

### 21.1. MySQL/InnoDB

Trong InnoDB, **PRIMARY KEY** thường là clustered index; bản ghi dữ liệu được tổ chức theo khóa chính. **Secondary index** thường chứa khóa chính để xác định hàng. Điều này ảnh hưởng đến lựa chọn khóa chính và chi phí secondary index.

Ví dụ:

~~~sql
CREATE INDEX idx_order_org_status_time
ON don_hang (to_chuc_id, trang_thai, tao_luc);

EXPLAIN
SELECT id, tao_luc
FROM don_hang
WHERE to_chuc_id = 10
  AND trang_thai = 'DA_THANH_TOAN'
ORDER BY tao_luc DESC
LIMIT 20;
~~~

MySQL có thể hiển thị các cột `type`, `key`, `rows`, `Extra` trong EXPLAIN truyền thống. “Using index” có ý nghĩa về việc query được cover bởi index; “Using filesort” biểu thị cơ chế sắp xếp, **không nhất thiết ghi file ra đĩa** như tên gọi dễ gây hiểu nhầm.

### 21.2. SQL Server

SQL Server có clustered và nonclustered indexes; một bảng thường có tối đa một clustered index, còn nonclustered indexes dùng để tối ưu các đường đọc khác. Có thể thêm cột payload bằng `INCLUDE`:

~~~sql
CREATE INDEX IX_DonHang_Org_Status_Time
ON dbo.DonHang (ToChucId, TrangThai, TaoLuc DESC)
INCLUDE (TongTien);
~~~

Kế hoạch có thể hiển thị `Index Seek`, `Index Scan`, `Key Lookup`, `Clustered Index Scan`, `Sort`... Một `Key Lookup` lặp nhiều lần có thể tạo chi phí lớn, nhưng không phải cứ xuất hiện Key Lookup là phải thêm INCLUDE ngay lập tức.

SQL Server hỗ trợ **filtered index**:

~~~sql
CREATE INDEX IX_DonHang_Moi
ON dbo.DonHang (ToChucId, TaoLuc)
WHERE TrangThai = N'MOI';
~~~

Chi tiết về supported predicates, parameterization và query optimizer khác PostgreSQL.

### 21.3. SQLite

SQLite hỗ trợ index đa cột, partial index và expression index:

~~~sql
CREATE INDEX idx_order_org_time
ON don_hang (to_chuc_id, tao_luc);

EXPLAIN QUERY PLAN
SELECT id
FROM don_hang
WHERE to_chuc_id = 10
ORDER BY tao_luc DESC
LIMIT 10;
~~~

`EXPLAIN QUERY PLAN` có thể báo `SCAN` hoặc `SEARCH ... USING INDEX`/`USING COVERING INDEX`. SQLite có cơ chế tự tạo index tạm trong một số kế hoạch; điều đó không có nghĩa nên phụ thuộc hoàn toàn vào automatic indexes cho mọi truy vấn production.

### 21.4. Oracle Database

Oracle hỗ trợ B-tree, bitmap, function-based indexes và nhiều lựa chọn vật lý khác. **Bitmap index** có thể phù hợp một số workload phân tích ít ghi với cột cardinality thấp, nhưng thường không phải lựa chọn mặc định cho bảng OLTP cập nhật đồng thời thường xuyên.

Ví dụ function-based index:

~~~sql
CREATE INDEX idx_khach_lower_email
ON khach_hang (LOWER(email));
~~~

Planner Oracle có thể chọn full table scan, index range scan, index unique scan, index fast full scan... tùy thống kê, predicate và cost model. Đọc plan bằng công cụ như `DBMS_XPLAN` phù hợp với môi trường.

## 22. Quy trình thiết kế index từ một câu SQL

Thay vì bắt đầu bằng “bảng có cột gì?”, hãy bắt đầu từ **workload**.

### Bước 1 — Viết câu SQL và kiểm tra tính đúng

~~~sql
SELECT id, tao_luc, tong_tien
FROM don_hang_idx
WHERE to_chuc_id = 10
  AND trang_thai = 'DA_THANH_TOAN'
  AND tao_luc >= TIMESTAMPTZ '2026-10-01 00:00:00+07'
  AND tao_luc <  TIMESTAMPTZ '2026-11-01 00:00:00+07'
ORDER BY tao_luc DESC, id DESC
LIMIT 20;
~~~

Kiểm tra scope tổ chức, trạng thái, khoảng thời gian và tie-breaker. **Index không thể sửa truy vấn sai business logic**.

### Bước 2 — Xác định cột lọc và loại điều kiện

| Cột | Điều kiện | Tính chất |
| --- | --- | --- |
| `to_chuc_id` | `= 10` | Equality |
| `trang_thai` | `= 'DA_THANH_TOAN'` | Equality |
| `tao_luc` | `>= ... AND < ...` | Range |
| `tao_luc, id` | `ORDER BY DESC` | Order |
| `tong_tien` | Chỉ SELECT | Payload |

### Bước 3 — Đề xuất index ứng viên

~~~sql
CREATE INDEX idx_orders_query
ON don_hang_idx (
    to_chuc_id,
    trang_thai,
    tao_luc DESC,
    id DESC
)
INCLUDE (tong_tien);
~~~

Đây là **một ứng viên** dựa trên query. Nếu bảng có cả màn hình “tất cả trạng thái” theo thời gian, có thể cần index `(to_chuc_id, tao_luc DESC, id DESC)` khác hoặc cân bằng bằng một phương án ít index hơn.

### Bước 4 — Quan sát plan và kiểm tra số hàng

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT id, tao_luc, tong_tien
FROM don_hang_idx
WHERE to_chuc_id = 10
  AND trang_thai = 'DA_THANH_TOAN'
  AND tao_luc >= TIMESTAMPTZ '2026-10-01 00:00:00+07'
  AND tao_luc <  TIMESTAMPTZ '2026-11-01 00:00:00+07'
ORDER BY tao_luc DESC, id DESC
LIMIT 20;
~~~

Quan sát node đọc, sort, estimate so với actual, buffer activity. Với bảng mẫu nhỏ, có thể vẫn là Seq Scan; đó không phải bằng chứng index mới vô dụng trên workload thật.

### Bước 5 — Đánh giá tác động tổng thể

Kiểm tra các truy vấn khác, tốc độ INSERT/UPDATE/DELETE, dung lượng index, thống kê, khả năng duy trì, quy tắc tạo index production và các index đã có.

Một index tốt phải có lợi ích **đủ lớn cho workload** so với chi phí dài hạn.

## 23. Những ngộ nhận thường gặp

| Ngộ nhận | Điều đúng hơn |
| --- | --- |
| “Có index là SQL luôn nhanh.” | Planner chọn access path theo cost; index đôi khi không lợi. |
| “WHERE có cột được index thì chắc dùng index.” | Cần xét toán tử, biểu thức, selectivity, thứ tự index và plan. |
| “Thứ tự predicate trong WHERE quyết định thứ tự index.” | Thứ tự cột trong index và optimizer mới quan trọng. |
| “Index đa cột (A,B,C) tương đương ba index (A),(B),(C).” | Index ghép có thứ tự khóa riêng, không thay mọi index đơn. |
| “Thiếu cột trái thì index không thể dùng.” | Có thể quét/skip-scan tùy DBMS nhưng thường kém hiệu quả hơn truy vấn đúng tiền tố. |
| “Index chỉ giúp WHERE.” | Có thể giúp JOIN, ORDER BY, LIMIT, DISTINCT, GROUP BY. |
| “Index sẽ luôn giữ thứ tự SELECT không có ORDER BY.” | SQL không bảo đảm thứ tự nếu không ghi ORDER BY. |
| “Index Only Scan luôn không đọc heap.” | PostgreSQL MVCC visibility có thể yêu cầu heap fetch. |
| “INCLUDE càng nhiều cột càng tốt.” | Index phình to, tốn ghi/cache và có giới hạn. |
| “Mọi index đều giúp INSERT/UPDATE.” | Index tăng chi phí bảo trì khi ghi. |
| “UNIQUE tự xử lý NULL giống nhau ở mọi DBMS.” | Semantics NULL khác theo DBMS/phiên bản. |
| “LIKE '%abc%' dùng B-tree tốt như 'abc%'.” | Leading wildcard không có tiền tố cố định để tra cứu B-tree thông thường. |
| “COUNT(*) luôn nhanh nếu có index.” | Cần xác định các hàng nhìn thấy và điều kiện MVCC, không tự O(1). |
| “Có index FK phía cha thì bảng con cũng tự có.” | PostgreSQL không tự tạo index ở cột FK phía con. |
| “Thấy Seq Scan tức là index thiết kế sai.” | Seq Scan có thể là kế hoạch tối ưu cho bảng nhỏ hoặc kết quả lớn. |
| “cost=1000 nghĩa là mất 1000ms.” | Cost là đơn vị ước lượng nội bộ của planner, không phải milliseconds. |
| “EXPLAIN ANALYZE không làm gì với UPDATE.” | Nó **thực thi DML**, có thể thay đổi dữ liệu. |
| “Một index tốt cho mọi tham số.” | Dữ liệu lệch và generic plan có thể dẫn tới kế hoạch khác nhau. |
| “Tối ưu index có thể bỏ kiểm tra kết quả truy vấn.” | Index chỉ là cơ chế truy cập, không thay logic, JOIN hoặc quyền dữ liệu. |

## 24. Bài tập thực hành có lời giải

Các bài 1–13 dựa trên `don_hang_idx` PostgreSQL đã tạo. Các bài còn lại ghi rõ khi dùng bảng giả định hoặc phương ngữ khác.

### Bài 1. Index khóa chính

**Yêu cầu:** tìm đơn 117 và cho biết có cần tạo thêm index trên id không.

~~~sql
SELECT id, to_chuc_id, tong_tien
FROM don_hang_idx
WHERE id = 117;
~~~

**Lời giải:** `id` đã là `PRIMARY KEY`, PostgreSQL tạo index duy nhất tương ứng. Không mặc định tạo thêm index `ON don_hang_idx(id)` vì có thể trùng chức năng.

### Bài 2. Tính độ chọn lọc

**Yêu cầu:** với bảng mẫu 20 hàng, điều kiện `to_chuc_id=10` khớp bao nhiêu phần trăm?

**Lời giải:** **15/20 = 75%**. Đây là điều kiện khá ít chọn lọc trên bộ dữ liệu. Planner có thể chọn Seq Scan thay vì index đơn cột. Không suy từ 20 hàng ra tốc độ bảng production lớn.

### Bài 3. Hai điều kiện bằng

**Yêu cầu:** tối ưu truy vấn tìm đơn theo tổ chức và khách hàng.

~~~sql
SELECT id, tao_luc
FROM don_hang_idx
WHERE to_chuc_id = 10
  AND khach_hang_id = 501;
~~~

**Lời giải:**

~~~sql
CREATE INDEX idx_bt_org_khach
ON don_hang_idx (to_chuc_id, khach_hang_id);
~~~

Truy vấn có thể khai thác tiền tố hai cột bằng. Trên bảng 20 hàng có thể vẫn quét tuần tự.

### Bài 4. Màn hình đơn mới nhất

**Yêu cầu:** tạo index hỗ trợ `WHERE to_chuc_id=? ORDER BY tao_luc DESC,id DESC LIMIT 10`.

**Lời giải:**

~~~sql
CREATE INDEX idx_bt_org_latest
ON don_hang_idx (to_chuc_id, tao_luc DESC, id DESC);
~~~

Index cho phép truy cập nhóm tổ chức và có thứ tự tương thích. Nếu cần `tong_tien` trên màn hình, có thể xét INCLUDE tùy chi phí.

### Bài 5. Giải thích tie-breaker

**Câu hỏi:** tại sao cần `id DESC` sau `tao_luc DESC`?

**Lời giải:** Có thể nhiều hàng cùng thời điểm; thêm ID duy nhất tạo thứ tự ổn định. Index không bảo đảm thứ tự mong muốn nếu truy vấn thiếu ORDER BY tường minh.

### Bài 6. Index ghép và cột giữa

Có index `(to_chuc_id, trang_thai, tao_luc)`. Truy vấn chỉ có `WHERE tao_luc>=...`. Có chắc index rất hiệu quả không?

**Lời giải:** Không. Thiếu điều kiện trên các cột đầu, B-tree có thể không thu hẹp được vùng quét hiệu quả. Một số plan hoặc kỹ thuật skip scan có thể vẫn dùng index, nhưng không nên coi nó giống index bắt đầu bằng `tao_luc`.

### Bài 7. WHERE dạng ngày

**Yêu cầu:** viết lại truy vấn lấy đơn trong ngày 05/10 giờ UTC+07 để index thường trên `tao_luc` có thể phục vụ.

**Lời giải:**

~~~sql
SELECT id
FROM don_hang_idx
WHERE tao_luc >= TIMESTAMPTZ '2026-10-05 00:00+07'
  AND tao_luc <  TIMESTAMPTZ '2026-10-06 00:00+07';
~~~

Khoảng nửa mở tránh bọc cột timestamp trong ép kiểu DATE. Với múi giờ có DST cần tính hai mốc theo timezone nghiệp vụ.

### Bài 8. Index Only Scan

**Câu hỏi:** `INCLUDE (tong_tien)` có bảo đảm PostgreSQL không đọc heap khi SELECT tong_tien không?

**Lời giải:** Không. Nó giúp index có đủ cột, nhưng tính nhìn thấy của hàng theo MVCC vẫn có thể yêu cầu heap fetch; xem node Index Only Scan và chỉ tiêu Heap Fetches trong EXPLAIN ANALYZE.

### Bài 9. Partial index

**Yêu cầu:** tạo index chỉ cho đơn MOI, ưu tiên đơn cũ trước.

**Lời giải:**

~~~sql
CREATE INDEX idx_bt_moi
ON don_hang_idx (to_chuc_id, tao_luc, id)
WHERE trang_thai = 'MOI';
~~~

Index nhỏ hơn nếu MOI là nhóm ít hàng. Truy vấn phải có predicate mà planner biết phù hợp với điều kiện partial index; generic parameter plan có thể hạn chế.

### Bài 10. LIKE ở đầu chuỗi

**Câu hỏi:** vì sao `LIKE '%ABC%'` không được phục vụ như `LIKE 'ABC%'` bởi B-tree thông thường?

**Lời giải:** Với tiền tố cố định, khóa có thể nằm trong một vùng thứ tự liên tiếp (tùy collation/operator class). Khi có ký tự đại diện ở đầu, các giá trị khớp có thể rải khắp index. Cân nhắc trigram/full-text nếu đúng nhu cầu.

### Bài 11. JOIN với khóa ngoại

**Câu hỏi:** PostgreSQL có tự tạo index trên mọi cột FK của bảng con không?

**Lời giải:** Không. PostgreSQL đảm bảo phía khóa được tham chiếu theo PK/UNIQUE phù hợp, nhưng index phía tham chiếu thường cần đánh giá và tạo riêng theo workload JOIN/DELETE/UPDATE.

### Bài 12. Index và COUNT

**Câu hỏi:** nếu có index `(to_chuc_id, trang_thai)`, câu `SELECT COUNT(*) ...` có luôn O(1) không?

**Lời giải:** Không. Database vẫn phải xác định các hàng hợp lệ theo predicate và MVCC, có thể dùng index-only/bitmap/seq scan nhưng không mặc định có bộ đếm chính xác tức thời cho mọi snapshot.

### Bài 13. EXPLAIN

**Yêu cầu:** chạy câu xem kế hoạch không thực thi SELECT và một câu đo thực tế.

**Lời giải:**

~~~sql
EXPLAIN
SELECT id FROM don_hang_idx WHERE id = 117;

EXPLAIN (ANALYZE, BUFFERS)
SELECT id FROM don_hang_idx WHERE id = 117;
~~~

Câu đầu chỉ cho plan; câu sau thực thi SELECT và trả thống kê thực tế. Trên bảng 20 dòng, Seq Scan vẫn có thể là lựa chọn của planner.

### Bài 14. Index ghép cho filter và order

**Yêu cầu:** ứng dụng thường tìm đơn đã thanh toán của từng tổ chức, mới nhất trước. Chọn index cơ sở.

**Lời giải:**

~~~sql
CREATE INDEX idx_bt_paid
ON don_hang_idx (
    to_chuc_id,
    trang_thai,
    tao_luc DESC,
    id DESC
);
~~~

Kiểm tra kế hoạch với query thực tế; có thể xét INCLUDE các cột nhỏ được trả thường xuyên, không bắt buộc.

### Bài 15. OR kết hợp index

**Câu hỏi:** khi có index riêng trên `khach_hang_id` và `trang_thai`, planner có bắt buộc chỉ dùng một index không?

**Lời giải:** Không. PostgreSQL có thể kết hợp qua BitmapAnd/BitmapOr trong điều kiện phù hợp, hoặc chọn index ghép/Seq Scan. Bitmap scan có thể mất thứ tự khóa nên truy vấn ORDER BY còn cần Sort.

### Bài 16. PostgreSQL và MySQL khác gì về cấu trúc?

**Câu hỏi:** vì sao không nên mô tả InnoDB secondary index giống hoàn toàn PostgreSQL B-tree trỏ trực tiếp tới heap tuple?

**Lời giải:** InnoDB có clustered primary key; secondary indexes thường lưu khóa chính làm row locator. PostgreSQL mặc định lưu bảng heap riêng và index trỏ tới vị trí hàng, có cơ chế MVCC/visibility riêng. Chi phí lookup và covering do đó khác nhau.

### Bài 17. SQL Server Key Lookup

**Câu hỏi:** xuất hiện Key Lookup trong plan SQL Server có nghĩa bắt buộc tạo INCLUDE cho mọi cột SELECT không?

**Lời giải:** Không. Với ít hàng được tra, Key Lookup có thể rất rẻ. Nếu nhiều lookup lặp lại và chi phí đáng kể, xem xét INCLUDE/index ghép có chọn lọc, đo tác động tới ghi và storage.

### Bài 18. Phân tích một index quá rộng

Một bảng có 10 index đơn cột và ba index ghép gần trùng. INSERT chậm. Có nên xóa bớt ngay?

**Lời giải:** Không tùy tiện. Cần xem truy vấn sử dụng index nào, độ trùng công dụng, kích thước/chi phí DML, ràng buộc uniqueness, plan thực tế và khoảng thời gian quan sát đại diện. Index UNIQUE/PK có thể bảo vệ tính đúng dữ liệu, không thể xóa chỉ vì ít lượt đọc.

### Bài 19. Tình huống cần BRIN

Log hàng tỷ dòng chủ yếu append theo thời gian, truy vấn hay lọc khoảng tháng, index B-tree quá lớn. Có lựa chọn nào?

**Lời giải:** Cân nhắc BRIN trên timestamp nếu thứ tự dữ liệu tương quan cao với vị trí trang; nó lưu tóm tắt theo vùng và có thể loại bỏ các block không liên quan. Chấp nhận lossy recheck; so sánh với partitioning và B-tree qua EXPLAIN/đo lường.

### Bài 20. Tối ưu nhưng không sửa sai ngữ nghĩa

Truy vấn theo tổ chức 10 và trạng thái DA_THANH_TOAN chậm. Có nên bỏ điều kiện tổ chức để planner dùng index trạng thái?

**Lời giải:** **Không.** Tốc độ không biện minh cho việc đọc dữ liệu tổ chức khác hoặc làm sai tập kết quả. Hãy chọn index phục vụ **đúng query nghiệp vụ**, ví dụ index ghép có cột tổ chức.

## 25. Checklist khi đề xuất index

1. **Truy vấn cần trả gì?** Đúng cột, JOIN, WHERE, GROUP BY, ORDER BY và LIMIT.
2. **Mức chi tiết kết quả đã đúng chưa?** Index không khử duplicate do JOIN sai.
3. **Predicate chọn lọc hay không?** Có chênh lệch lớn giữa các giá trị tham số không?
4. **Cột đầu của index ghép có khớp truy vấn chủ lực không?**
5. **Index có hỗ trợ ORDER BY/LIMIT không?** Cần tie-breaker?
6. **Có biểu thức/cast/collation/LIKE làm index thường khó được sử dụng không?**
7. **Có cần partial index, expression index hoặc một access method khác B-tree không?**
8. **Query có lấy cột payload không?** INCLUDE có lợi thực sự?
9. **Thống kê đã phản ánh dữ liệu mới chưa?** Cần ANALYZE hoặc extended statistics?
10. **EXPLAIN estimate có gần actual không?** Bottleneck ở Scan, JOIN, Sort hay Aggregate?
11. **Có index PK/UNIQUE hoặc index ghép hiện hữu phục vụ được không?**
12. **Gánh nặng INSERT/UPDATE/DELETE và chi phí bảo trì có chấp nhận được không?**
13. **Quy trình tạo index production có hạn chế khóa và khả năng rollback không?**
14. **Đã đo nhiều lần với dữ liệu/giá trị tham số đại diện chưa?**
15. **Mọi điều kiện phân quyền và phạm vi tổ chức vẫn nguyên vẹn chứ?**

## 26. Kết luận

**Index là cấu trúc dữ liệu hỗ trợ planner chọn một cách đọc hiệu quả**, không phải lời hứa rằng mọi SELECT sẽ nhanh hơn. Ở mức SQL, chỉ mục có thể:

- Giúp tìm một tập nhỏ hàng qua `WHERE`;
- Giúp tra hàng liên quan trong `JOIN`;
- Cung cấp thứ tự hữu ích cho `ORDER BY` và `LIMIT`;
- Hỗ trợ xử lý `GROUP BY`, `DISTINCT` trong một số kế hoạch;
- Giảm nhu cầu lấy dữ liệu gốc khi có **covering index** và điều kiện index-only phù hợp;
- Thực thi quy tắc `PRIMARY KEY` và `UNIQUE` trong những cấu hình thích hợp.

Ngược lại, index **không** tự đảm bảo kết quả có thứ tự nếu thiếu ORDER BY, không tự sửa điều kiện JOIN sai, không làm COUNT luôn O(1), không bảo đảm index-only tránh mọi heap fetch, và không miễn phí cho thao tác ghi.

**Cách tư duy bền vững:** bắt đầu từ **truy vấn đúng và workload thật**, xác định cột lọc bằng/khoảng, khóa sắp xếp, số hàng dự kiến và phạm vi nghiệp vụ. Từ đó đề xuất index phù hợp, đọc **EXPLAIN/EXPLAIN ANALYZE** để hiểu access path, rồi cân nhắc hiệu quả đọc so với chi phí ghi/lưu trữ. Chỉ mục tốt là **chỉ mục giải quyết đúng nút thắt của một tập truy vấn quan trọng**, không phải chỉ mục có nhiều cột nhất.
