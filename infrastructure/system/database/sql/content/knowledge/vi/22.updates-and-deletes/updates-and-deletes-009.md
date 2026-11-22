# Xem trước tập hàng mục tiêu bằng SELECT tương ứng trước UPDATE và DELETE

Khi viết `UPDATE` hoặc `DELETE`, phần khó và nguy hiểm nhất thường không phải cú pháp `SET` hay từ khóa `DELETE`. Vấn đề là xác định **chính xác những hàng nào sẽ bị tác động**. Một dấu `=` nhầm, một cặp ngoặc thiếu quanh `AND/OR`, một điều kiện JOIN chưa đủ hoặc một khoảng ngày không đúng đều có thể khiến câu lệnh sửa hoặc xóa nhiều hàng hơn dự kiến.

Thói quen an toàn là **dùng một câu `SELECT` tương ứng để xem trước tập hàng mục tiêu**, trước khi chạy lệnh thay đổi dữ liệu. Với UPDATE, ngoài danh sách hàng, nên xem cả **giá trị hiện tại** và **giá trị dự kiến sau cập nhật**. Với DELETE, nên xem **khóa chính**, **số hàng**, **quan hệ khóa ngoại** và hậu quả xóa.

Ví dụ một lệnh cập nhật:

~~~sql
UPDATE don_hang
SET da_thong_bao = TRUE
WHERE trang_thai = 'NEW'
  AND ngay_dat < DATE '2026-10-05';
~~~

Câu SELECT xem trước tương ứng:

~~~sql
SELECT
    id,
    trang_thai,
    ngay_dat,
    da_thong_bao
FROM don_hang
WHERE trang_thai = 'NEW'
  AND ngay_dat < DATE '2026-10-05'
ORDER BY id;
~~~

Hai câu cùng dùng **bảng mục tiêu** và **điều kiện lọc**. Câu SELECT chỉ đọc; nó cho phép người viết kiểm tra trước khi quyết định chạy UPDATE. Tuy nhiên, một SELECT chạy trước không tự bảo đảm dữ liệu sẽ giữ nguyên đến lúc UPDATE, nhất là khi có nhiều người cùng thao tác. Vì thế bài học còn trình bày transaction, kiểm tra `RETURNING` và vấn đề đồng thời.

Bài thuộc chương **Cập nhật và xóa** của module **Database SQL**. Các ví dụ dùng PostgreSQL với bảng tạm trong môi trường thực hành, để minh họa kỹ thuật tiền kiểm mà không yêu cầu thay đổi dữ liệu sản xuất.

## 1. Mục tiêu bài học

Sau bài này, bạn có thể:

1. Biến một câu UPDATE/DELETE đơn bảng thành **SELECT xem trước** với cùng điều kiện lựa chọn.
2. Liệt kê **khóa chính**, **giá trị cũ**, **giá trị mới dự kiến**, đếm số hàng và phát hiện tập mục tiêu bất thường.
3. Xem trước chính xác khi câu UPDATE/DELETE có `JOIN`, `EXISTS`, `IN`, bảng dẫn xuất hoặc CTE.
4. Phân biệt **số dòng JOIN** với **số hàng mục tiêu khác nhau**.
5. Nhận ra lỗi dễ gặp với `AND/OR`, `NULL`, khoảng ngày, điều kiện thiếu và `UPDATE ... FROM` có nhiều dòng khớp.
6. Xác định những ràng buộc **FOREIGN KEY** hoặc hành động xóa dây chuyền có thể ảnh hưởng đến DELETE.
7. Kết hợp `BEGIN`, `SELECT`, `UPDATE/DELETE ... RETURNING`, `COMMIT` hoặc `ROLLBACK` trong thao tác có kiểm soát.
8. Giải thích vì sao **SELECT tiền kiểm không phải bảo đảm tuyệt đối về đồng thời**, và khi nào phải khóa hàng hoặc cố định danh sách ID.
9. Áp dụng tư duy tương tự trong Java/JDBC và những hệ quản trị khác.

## 2. Quy trình tư duy: từ câu lệnh thay đổi sang SELECT

Trước một thao tác nguy hiểm, hãy trả lời bốn câu hỏi:

- **Bảng mục tiêu nào?** Ví dụ `don_hang` hay `khach_hang`.
- **Điều kiện gì chọn hàng?** Phải giữ đúng logic `WHERE`, các điều kiện tương quan và quy tắc JOIN.
- **Một hàng được định danh bằng khóa nào?** Thường là PRIMARY KEY `id`; nếu khóa tổng hợp, dùng đầy đủ các cột khóa.
- **Thay đổi cụ thể là gì?** Với UPDATE, mỗi cột sẽ chuyển từ giá trị nào sang giá trị nào; với DELETE, hàng nào mất và quan hệ liên quan ra sao.

Mẫu cơ bản:

~~~text
Bước A: Xác định predicate dùng để chọn hàng
                         │
                         ▼
Bước B: SELECT id, cột quan trọng, giá trị dự kiến
                         │
                         ▼
Bước C: COUNT(*) và so tập ID với kỳ vọng
                         │
                         ▼
Bước D: Kiểm tra FK / quyền / quy tắc nghiệp vụ
                         │
                         ▼
Bước E: BEGIN → UPDATE/DELETE → RETURNING
                         │
                    ┌────┴────┐
                    ▼         ▼
                Đúng      Không đúng
                    │         │
                 COMMIT    ROLLBACK
~~~

Đây là quy trình thực hành. Trên hệ thống thật, thường có bước phê duyệt, ghi audit, phân quyền và giới hạn số hàng bổ sung.

### 2.1. SELECT là bước quan sát, không phải UPDATE giả

Một SELECT không làm thay đổi dữ liệu:

~~~sql
SELECT id, trang_thai
FROM don_hang
WHERE trang_thai = 'CANCELLED';
~~~

Trong khi:

~~~sql
DELETE FROM don_hang
WHERE trang_thai = 'CANCELLED';
~~~

là một lệnh xóa thực sự. Dù có thể kết thúc transaction bằng ROLLBACK, hãy luôn nhớ: **DELETE đã chạy trong transaction vẫn là một thao tác ghi**, có thể khóa hàng, gọi trigger và tốn tài nguyên trước khi rollback. Nếu mục tiêu chỉ là quan sát, SELECT là bước phù hợp.

### 2.2. Đừng chỉ nhìn số hàng

Một câu SELECT trả đúng ba hàng chưa đủ chứng minh đúng nghiệp vụ: đó có thể là **ba hàng khác với ba hàng mong muốn**. Cần xem khóa định danh và thuộc tính như khách hàng, trạng thái, ngày, mức tiền.

Tối thiểu nên có:

~~~sql
SELECT
    id,
    khach_hang_id,
    trang_thai,
    ngay_dat
FROM don_hang
WHERE ...
ORDER BY id;
~~~

Dấu `...` trong ví dụ tổng quát là vị trí thay điều kiện thật, không phải SQL hoàn chỉnh.

## 3. Bộ dữ liệu thực hành PostgreSQL

Các ví dụ sẽ dùng một bảng khách hàng, một bảng đơn hàng, bảng chi tiết đơn và bảng chính sách ưu tiên theo khu vực. Hãy chạy trong **database thử nghiệm** và **cùng một phiên kết nối**.

Mọi bảng bên dưới đều là `TEMP TABLE`. Các đoạn UPDATE/DELETE minh họa thường được bao trong transaction rồi **ROLLBACK** để giữ dữ liệu gốc cho các phần tiếp theo.

### 3.1. Bảng khách hàng

~~~sql
CREATE TEMP TABLE pv_khach_hang (
    id INTEGER PRIMARY KEY,
    ho_ten TEXT NOT NULL,
    khu_vuc TEXT NOT NULL,
    trang_thai TEXT NOT NULL
        CHECK (trang_thai IN ('ACTIVE', 'INACTIVE'))
);

INSERT INTO pv_khach_hang
    (id, ho_ten, khu_vuc, trang_thai)
VALUES
    (1, 'An',   'BAC',   'ACTIVE'),
    (2, 'Bình', 'NAM',   'ACTIVE'),
    (3, 'Chi',  'BAC',   'ACTIVE'),
    (4, 'Dũng', 'TRUNG', 'INACTIVE'),
    (5, 'Hà',   'NAM',   'ACTIVE'),
    (6, 'Lan',  'NAM',   'INACTIVE'),
    (7, 'Minh', 'BAC',   'INACTIVE');
~~~

Khách **Minh** chưa có đơn hàng. Đây là tình huống hữu ích khi kiểm tra một DELETE khách hàng không còn hoạt động và không có bản ghi phụ thuộc.

### 3.2. Bảng đơn hàng

~~~sql
CREATE TEMP TABLE pv_don_hang (
    id INTEGER PRIMARY KEY,
    khach_hang_id INTEGER NOT NULL
        REFERENCES pv_khach_hang(id),
    ngay_dat DATE NOT NULL,
    trang_thai TEXT NOT NULL
        CHECK (trang_thai IN ('NEW', 'PAID', 'CANCELLED')),
    tong_tien NUMERIC(12,2) NOT NULL
        CHECK (tong_tien >= 0),
    da_thong_bao BOOLEAN NOT NULL DEFAULT FALSE,
    ghi_chu TEXT
);

INSERT INTO pv_don_hang
    (id, khach_hang_id, ngay_dat, trang_thai, tong_tien)
VALUES
    (101, 1, DATE '2026-10-01', 'NEW',       150000),
    (102, 1, DATE '2026-10-05', 'PAID',      240000),
    (103, 2, DATE '2026-10-03', 'NEW',       300000),
    (104, 2, DATE '2026-09-20', 'CANCELLED',  80000),
    (105, 3, DATE '2026-10-07', 'NEW',       120000),
    (106, 4, DATE '2026-08-10', 'CANCELLED',  50000),
    (107, 4, DATE '2026-10-09', 'PAID',      100000),
    (108, 5, DATE '2026-10-02', 'NEW',       250000),
    (109, 5, DATE '2026-10-11', 'CANCELLED', 180000),
    (110, 6, DATE '2026-09-01', 'CANCELLED',  70000),
    (111, 6, DATE '2026-10-12', 'NEW',        90000);
~~~

Ban đầu, tất cả `da_thong_bao = FALSE` và `ghi_chu = NULL` theo DEFAULT của bảng.

### 3.3. Bảng chi tiết đơn hàng

~~~sql
CREATE TEMP TABLE pv_chi_tiet_don (
    id INTEGER PRIMARY KEY,
    don_hang_id INTEGER NOT NULL
        REFERENCES pv_don_hang(id),
    ten_san_pham TEXT NOT NULL,
    so_luong INTEGER NOT NULL CHECK (so_luong > 0)
);

INSERT INTO pv_chi_tiet_don
    (id, don_hang_id, ten_san_pham, so_luong)
VALUES
    (1001, 101, 'Sách SQL',  2),
    (1002, 101, 'Sổ tay',    1),
    (1003, 102, 'Sách SQL',  1),
    (1004, 103, 'Bút',       3),
    (1005, 103, 'Sổ tay',    1),
    (1006, 104, 'Bút',       1),
    (1007, 105, 'Sách SQL',  1),
    (1008, 106, 'Sổ tay',    1),
    (1009, 107, 'Bút',       2),
    (1010, 108, 'Sách SQL',  2),
    (1011, 109, 'Sổ tay',    1),
    (1012, 110, 'Bút',       1),
    (1013, 111, 'Sách SQL',  1);
~~~

Khóa ngoại mặc định của PostgreSQL không tự cho phép xóa đơn cha nếu còn dòng chi tiết tham chiếu. Đây là một yếu tố quan trọng khi **xem trước DELETE**.

Quan hệ:

~~~text
pv_khach_hang (1) ──── (N) pv_don_hang
                               │
                               │ (1)
                               ▼
                         pv_chi_tiet_don (N)
~~~

### 3.4. Chính sách ưu tiên theo khu vực

~~~sql
CREATE TEMP TABLE pv_chinh_sach_vung (
    khu_vuc TEXT PRIMARY KEY,
    nguong_uu_tien NUMERIC(12,2) NOT NULL
        CHECK (nguong_uu_tien >= 0)
);

INSERT INTO pv_chinh_sach_vung
    (khu_vuc, nguong_uu_tien)
VALUES
    ('BAC',   100000),
    ('NAM',   200000),
    ('TRUNG', 120000);
~~~

Một đơn NEW có thể được đánh dấu ưu tiên nếu `tong_tien >= nguong_uu_tien` của khu vực khách hàng. Bảng chính sách có **mỗi khu vực đúng một hàng** vì PRIMARY KEY, nên khi JOIN theo khu vực không làm nhân dòng do chính sách trùng lặp.

### 3.5. Dữ liệu mẫu cần ghi nhớ

| ID đơn | Khách | Khu vực | Ngày | Trạng thái | Tiền |
|---:|---|---|---|---|---:|
| 101 | An | BAC | 01/10 | NEW | 150000 |
| 102 | An | BAC | 05/10 | PAID | 240000 |
| 103 | Bình | NAM | 03/10 | NEW | 300000 |
| 104 | Bình | NAM | 20/09 | CANCELLED | 80000 |
| 105 | Chi | BAC | 07/10 | NEW | 120000 |
| 106 | Dũng | TRUNG | 10/08 | CANCELLED | 50000 |
| 107 | Dũng | TRUNG | 09/10 | PAID | 100000 |
| 108 | Hà | NAM | 02/10 | NEW | 250000 |
| 109 | Hà | NAM | 11/10 | CANCELLED | 180000 |
| 110 | Lan | NAM | 01/09 | CANCELLED | 70000 |
| 111 | Lan | NAM | 12/10 | NEW | 90000 |

Tổng quan:

- **7 khách hàng**; khách Minh (ID 7) chưa có đơn.
- **11 đơn hàng**: 5 NEW, 2 PAID, 4 CANCELLED.
- **13 dòng chi tiết**: đơn 101 và 103 có hai dòng; những đơn còn lại có một dòng.
- Đơn CANCELLED **trước ngày 01/10/2026**: 104, 106, 110.
- Đơn NEW **trước ngày 05/10/2026**: 101, 103, 108.
- Đơn NEW đủ ngưỡng ưu tiên khu vực: 101, 103, 105, 108.

Những con số trên là kết quả mong đợi của bộ dữ liệu cố định. Chúng hỗ trợ bạn đọc kết quả trong lúc học, không phải lý do để gắn cứng ID vào ứng dụng thật.

## 4. Mẫu 1: xem trước UPDATE đơn giản

Yêu cầu: đánh dấu đã thông báo cho **các đơn NEW đặt trước 05/10/2026** nhưng chưa được thông báo.

### 4.1. Viết SELECT tương ứng trước

~~~sql
SELECT
    id,
    khach_hang_id,
    ngay_dat,
    trang_thai,
    da_thong_bao
FROM pv_don_hang
WHERE trang_thai = 'NEW'
  AND ngay_dat < DATE '2026-10-05'
  AND da_thong_bao = FALSE
ORDER BY id;
~~~

Kết quả:

| id | khach_hang_id | ngay_dat | trang_thai | da_thong_bao |
|---:|---:|---|---|---|
| 101 | 1 | 2026-10-01 | NEW | false |
| 103 | 2 | 2026-10-03 | NEW | false |
| 108 | 5 | 2026-10-02 | NEW | false |

**Ba hàng mục tiêu**, ID 101, 103, 108.

### 4.2. Đếm chính xác tập mục tiêu

~~~sql
SELECT COUNT(*) AS so_don_du_kien
FROM pv_don_hang
WHERE trang_thai = 'NEW'
  AND ngay_dat < DATE '2026-10-05'
  AND da_thong_bao = FALSE;
~~~

Kết quả: `3`.

Việc kết hợp **SELECT liệt kê khóa** và **SELECT COUNT(*)** giúp trả lời cả “đúng những đơn nào?” và “bao nhiêu đơn?”.

### 4.3. UPDATE với cùng điều kiện

~~~sql
UPDATE pv_don_hang
SET da_thong_bao = TRUE
WHERE trang_thai = 'NEW'
  AND ngay_dat < DATE '2026-10-05'
  AND da_thong_bao = FALSE;
~~~

Để giữ dữ liệu mẫu ban đầu, các phần sau sẽ thực hiện UPDATE trong transaction và ROLLBACK. Nếu bạn vừa chạy UPDATE trên ngoài transaction và DB client đã auto-commit, dữ liệu ban đầu đã thay đổi; hãy tái tạo bảng tạm hoặc điều chỉnh trước khi đối chiếu ví dụ.

### 4.4. Quy tắc chuyển UPDATE thành SELECT

| Phần của UPDATE | SELECT xem trước |
|---|---|
| `UPDATE pv_don_hang` | `FROM pv_don_hang` |
| `SET da_thong_bao = TRUE` | Hiển thị cột cũ và giá trị mới dự kiến |
| `WHERE trang_thai = ...` | Giữ nguyên điều kiện ở WHERE |
| Không yêu cầu thứ tự ghi | `ORDER BY id` để dễ đối chiếu kết quả xem trước |

Chỉ thêm `ORDER BY` vào SELECT để tiện kiểm tra; không hiểu nhầm rằng UPDATE sẽ tác động hàng theo thứ tự này.

## 5. Xem trước cả giá trị cũ và giá trị mới

Khi cập nhật nhiều cột hoặc các biểu thức có điều kiện, không chỉ xem ID. Hãy hiển thị **trạng thái trước/sau dự kiến**.

### 5.1. Cập nhật cùng một giá trị cho nhiều hàng

~~~sql
SELECT
    id,
    ngay_dat,
    da_thong_bao AS da_thong_bao_cu,
    TRUE AS da_thong_bao_du_kien
FROM pv_don_hang
WHERE trang_thai = 'NEW'
  AND ngay_dat < DATE '2026-10-05'
  AND da_thong_bao = FALSE
ORDER BY id;
~~~

Cột `da_thong_bao_du_kien` chỉ là **hằng số trong kết quả SELECT**. Cơ sở dữ liệu chưa cập nhật bất kỳ hàng nào.

### 5.2. Cập nhật bằng biểu thức có điều kiện

Giả sử cần ghi chú:

- Đơn NEW và `tong_tien >= 200000` nhận `'UU_TIEN'`.
- Những đơn NEW còn lại nhận `'THUONG'`.

SELECT xem trước:

~~~sql
SELECT
    id,
    tong_tien,
    ghi_chu AS ghi_chu_cu,
    CASE
        WHEN tong_tien >= 200000 THEN 'UU_TIEN'
        ELSE 'THUONG'
    END AS ghi_chu_moi_du_kien
FROM pv_don_hang
WHERE trang_thai = 'NEW'
ORDER BY id;
~~~

Kết quả:

| id | tong_tien | ghi_chu_cu | ghi_chu_moi_du_kien |
|---:|---:|---|---|
| 101 | 150000 | NULL | THUONG |
| 103 | 300000 | NULL | UU_TIEN |
| 105 | 120000 | NULL | THUONG |
| 108 | 250000 | NULL | UU_TIEN |
| 111 | 90000 | NULL | THUONG |

UPDATE tương ứng:

~~~sql
UPDATE pv_don_hang
SET ghi_chu = CASE
    WHEN tong_tien >= 200000 THEN 'UU_TIEN'
    ELSE 'THUONG'
END
WHERE trang_thai = 'NEW';
~~~

**Cần giữ giống nhau cả predicate lẫn biểu thức**. Nếu SELECT tính theo ngưỡng 200000 mà UPDATE dùng 250000, việc xem trước không còn phản ánh thay đổi thực tế.

### 5.3. Nhiều cột cùng lúc

Một UPDATE có thể đặt lại hai cột:

~~~sql
UPDATE pv_don_hang
SET
    da_thong_bao = FALSE,
    ghi_chu = NULL
WHERE trang_thai = 'CANCELLED';
~~~

SELECT tiền kiểm tương ứng:

~~~sql
SELECT
    id,
    trang_thai,
    da_thong_bao AS thong_bao_cu,
    FALSE AS thong_bao_moi,
    ghi_chu AS ghi_chu_cu,
    NULL::TEXT AS ghi_chu_moi
FROM pv_don_hang
WHERE trang_thai = 'CANCELLED'
ORDER BY id;
~~~

Câu SELECT giúp người vận hành biết **cả hai cột** sẽ đổi như thế nào, không chỉ số đơn bị tác động.

## 6. Xem trước bằng SELECT trong transaction, rồi RETURNING

Với PostgreSQL, `RETURNING` cho phép lấy các hàng thực sự được UPDATE/DELETE. Kết hợp tiền kiểm và `RETURNING` để so sánh **tập dự kiến** và **tập đã tác động**.

### 6.1. Thực hành an toàn bằng ROLLBACK

~~~sql
BEGIN;

-- Bước 1: xem trước.
SELECT
    id,
    trang_thai,
    ngay_dat,
    da_thong_bao
FROM pv_don_hang
WHERE trang_thai = 'NEW'
  AND ngay_dat < DATE '2026-10-05'
  AND da_thong_bao = FALSE
ORDER BY id;

-- Bước 2: thực hiện cập nhật trong transaction.
UPDATE pv_don_hang
SET da_thong_bao = TRUE
WHERE trang_thai = 'NEW'
  AND ngay_dat < DATE '2026-10-05'
  AND da_thong_bao = FALSE
RETURNING id, ngay_dat, trang_thai, da_thong_bao;

-- Bước 3: thực hành chỉ quan sát, không giữ thay đổi.
ROLLBACK;
~~~

Trong dữ liệu mẫu chưa sửa, SELECT đầu liệt kê 101, 103, 108; `RETURNING` cũng trả các ID ấy với `da_thong_bao = true`. ROLLBACK hoàn tác UPDATE, để các ví dụ tiếp theo vẫn dùng tập gốc.

**Không được hiểu ROLLBACK là thuộc tính của SELECT**. UPDATE đã chạy và tạo thay đổi tạm trong transaction; ROLLBACK đưa trạng thái dữ liệu về trước transaction, khi những cơ chế được rollback phù hợp.

### 6.2. Khi nào dùng COMMIT?

Trong thao tác thật, chỉ `COMMIT` khi:

- Người dùng hoặc quy trình có quyền thay đổi dữ liệu.
- Tập mục tiêu khớp yêu cầu nghiệp vụ.
- Số hàng/tập khóa tác động hợp lý.
- Các kiểm tra khác, bao gồm ràng buộc và kết quả nghiệp vụ, thành công.

Nếu bất kỳ điều kiện nào sai, hãy rollback hoặc hủy thao tác theo quy trình đã định nghĩa.

### 6.3. RETURNING không tự bảo đảm đã duyệt đúng hàng

`RETURNING` cho biết hàng **thực sự được tác động** bởi câu lệnh; nó không biết ý định nghiệp vụ ban đầu của bạn. Một UPDATE thiếu WHERE sẽ trả nhiều hàng, nhưng đó vẫn có thể là sai nghiêm trọng.

Vì vậy, hãy kiểm tra **trước khi chạy**, không chỉ hy vọng phát hiện sai sau RETURNING.

## 7. Mẫu 2: xem trước DELETE đơn giản

Yêu cầu: xóa khách hàng **INACTIVE và chưa có bất kỳ đơn hàng nào**.

### 7.1. SELECT xem trước với NOT EXISTS

~~~sql
SELECT
    kh.id,
    kh.ho_ten,
    kh.khu_vuc,
    kh.trang_thai
FROM pv_khach_hang AS kh
WHERE kh.trang_thai = 'INACTIVE'
  AND NOT EXISTS (
      SELECT 1
      FROM pv_don_hang AS dh
      WHERE dh.khach_hang_id = kh.id
  )
ORDER BY kh.id;
~~~

Kết quả duy nhất:

| id | ho_ten | khu_vuc | trang_thai |
|---:|---|---|---|
| 7 | Minh | BAC | INACTIVE |

Dũng và Lan đều INACTIVE, nhưng vẫn có đơn hàng, nên **không thuộc tập xóa**.

### 7.2. DELETE với cùng điều kiện

~~~sql
BEGIN;

DELETE FROM pv_khach_hang AS kh
WHERE kh.trang_thai = 'INACTIVE'
  AND NOT EXISTS (
      SELECT 1
      FROM pv_don_hang AS dh
      WHERE dh.khach_hang_id = kh.id
  )
RETURNING kh.id, kh.ho_ten;

ROLLBACK;
~~~

Với bộ dữ liệu nguyên trạng, DELETE trả một hàng Minh. ROLLBACK giữ lại Minh để có thể làm các bài tập tiếp theo.

### 7.3. Vì sao không dùng DELETE mọi khách INACTIVE?

~~~sql
-- Nguy hiểm và có thể vi phạm FOREIGN KEY:
DELETE FROM pv_khach_hang
WHERE trang_thai = 'INACTIVE';
~~~

Lệnh này chọn cả Dũng, Lan và Minh. Vì Dũng và Lan có đơn tham chiếu, cơ sở dữ liệu sẽ từ chối xóa những hàng cha tương ứng nếu ràng buộc FK không cho phép. Nhưng phụ thuộc vào lỗi FK để “bảo vệ” khỏi một điều kiện xóa quá rộng là tư duy không đủ an toàn. Cần **định nghĩa tập đúng ngay trong WHERE**.

### 7.4. Số hàng DELETE thực tế

Một câu DELETE có thể tác động **0 hàng** do không có bản ghi phù hợp. Nếu người vận hành kỳ vọng xóa một khách nhưng kết quả 0, đó có thể là dấu hiệu ID sai hoặc có đơn phát sinh mới. Không nên mặc định “câu lệnh chạy không lỗi” đồng nghĩa thao tác nghiệp vụ đã hoàn thành.

## 8. Mẫu 3: SELECT tương ứng cho UPDATE có JOIN

Yêu cầu: đánh dấu `ghi_chu = 'CAN_UU_TIEN'` cho các đơn:

- Trạng thái **NEW**.
- Tổng tiền **từ ngưỡng ưu tiên của khu vực khách hàng trở lên**.

Ngưỡng nằm trong bảng khác; cần JOIN khách hàng và chính sách khu vực.

### 8.1. SELECT tiền kiểm với cùng chuỗi JOIN

~~~sql
SELECT
    dh.id AS don_hang_id,
    kh.ho_ten,
    kh.khu_vuc,
    dh.trang_thai,
    dh.tong_tien,
    cs.nguong_uu_tien,
    dh.ghi_chu AS ghi_chu_cu,
    'CAN_UU_TIEN' AS ghi_chu_moi
FROM pv_don_hang AS dh
JOIN pv_khach_hang AS kh
    ON kh.id = dh.khach_hang_id
JOIN pv_chinh_sach_vung AS cs
    ON cs.khu_vuc = kh.khu_vuc
WHERE dh.trang_thai = 'NEW'
  AND dh.tong_tien >= cs.nguong_uu_tien
ORDER BY dh.id;
~~~

Kết quả:

| ID | Khách | Khu vực | Tổng tiền | Ngưỡng | Ghi chú mới |
|---:|---|---|---:|---:|---|
| 101 | An | BAC | 150000 | 100000 | CAN_UU_TIEN |
| 103 | Bình | NAM | 300000 | 200000 | CAN_UU_TIEN |
| 105 | Chi | BAC | 120000 | 100000 | CAN_UU_TIEN |
| 108 | Hà | NAM | 250000 | 200000 | CAN_UU_TIEN |

Đơn 111 là NEW nhưng chỉ có 90000 ở NAM, nhỏ hơn 200000, nên không được chọn.

### 8.2. PostgreSQL UPDATE ... FROM tương ứng

~~~sql
BEGIN;

UPDATE pv_don_hang AS dh
SET ghi_chu = 'CAN_UU_TIEN'
FROM pv_khach_hang AS kh
JOIN pv_chinh_sach_vung AS cs
    ON cs.khu_vuc = kh.khu_vuc
WHERE dh.khach_hang_id = kh.id
  AND dh.trang_thai = 'NEW'
  AND dh.tong_tien >= cs.nguong_uu_tien
RETURNING
    dh.id,
    dh.trang_thai,
    dh.tong_tien,
    dh.ghi_chu;

ROLLBACK;
~~~

Điểm quan trọng: `dh` là **bảng được cập nhật**. Ở cú pháp `UPDATE ... FROM` của PostgreSQL, liên kết từ bảng mục tiêu sang các bảng nguồn được diễn đạt trong `WHERE` bằng:

~~~sql
dh.khach_hang_id = kh.id
~~~

Trong SELECT xem trước, ta viết mối quan hệ tương đương bằng `JOIN ... ON`. Nếu quên điều kiện nối này trong UPDATE, phạm vi có thể bị mở rộng sai nghiêm trọng.

### 8.3. JOIN nguồn phải bảo đảm số hàng khớp phù hợp

Bảng chính sách có PRIMARY KEY `khu_vuc` nên mỗi khách hàng khớp tối đa một chính sách. Nhưng nếu bạn JOIN bảng khác có nhiều dòng cho một đơn, SELECT xem trước có thể trả **nhiều dòng cho cùng một ID đơn**.

Với UPDATE FROM, nếu một hàng mục tiêu khớp **nhiều hàng nguồn**, việc lấy giá trị từ nguồn nào có thể không xác định theo ý định nghiệp vụ. Hãy bảo đảm một hàng nguồn cho mỗi mục tiêu khi giá trị SET phụ thuộc nguồn, hoặc dùng tổng hợp/xác định quy tắc lựa chọn.

## 9. Phân biệt số dòng JOIN và số hàng mục tiêu

Xét câu SELECT:

~~~sql
SELECT
    dh.id AS don_hang_id,
    ct.id AS dong_don_id
FROM pv_don_hang AS dh
JOIN pv_chi_tiet_don AS ct
    ON ct.don_hang_id = dh.id
WHERE dh.id IN (101, 103)
ORDER BY dh.id, ct.id;
~~~

Kết quả có **4 dòng**:

| don_hang_id | dong_don_id |
|---:|---:|
| 101 | 1001 |
| 101 | 1002 |
| 103 | 1004 |
| 103 | 1005 |

Nhưng chỉ có **2 đơn hàng mục tiêu**: 101 và 103.

Nếu mục tiêu của UPDATE là **bảng đơn hàng**, đếm bốn dòng JOIN không được hiểu thành sẽ UPDATE bốn hàng đơn. Hàng mục tiêu 101 có thể khớp hai dòng chi tiết, nhưng đó vẫn là một hàng `pv_don_hang`.

### 9.1. Đếm các khóa mục tiêu riêng biệt

~~~sql
SELECT
    COUNT(*) AS so_dong_join,
    COUNT(DISTINCT dh.id) AS so_don_muc_tieu
FROM pv_don_hang AS dh
JOIN pv_chi_tiet_don AS ct
    ON ct.don_hang_id = dh.id
WHERE dh.id IN (101, 103);
~~~

Kết quả:

| so_dong_join | so_don_muc_tieu |
|---:|---:|
| 4 | 2 |

### 9.2. SELECT DISTINCT để xem đúng tập mục tiêu

~~~sql
SELECT DISTINCT
    dh.id,
    dh.trang_thai,
    dh.ghi_chu
FROM pv_don_hang AS dh
JOIN pv_chi_tiet_don AS ct
    ON ct.don_hang_id = dh.id
WHERE dh.id IN (101, 103)
ORDER BY dh.id;
~~~

Kết quả gồm đúng hai ID. `DISTINCT` ở bước quan sát có thể giúp loại các bản sao do JOIN, nhưng **không giải quyết bản chất nhiều dòng nguồn** nếu UPDATE lấy một giá trị bất kỳ từ những dòng khác nhau.

### 9.3. Dùng EXISTS khi chỉ hỏi “có chi tiết nào khớp không?”

Ví dụ cập nhật đơn có ít nhất một sản phẩm tên Sách SQL:

~~~sql
SELECT
    dh.id,
    dh.trang_thai
FROM pv_don_hang AS dh
WHERE EXISTS (
    SELECT 1
    FROM pv_chi_tiet_don AS ct
    WHERE ct.don_hang_id = dh.id
      AND ct.ten_san_pham = 'Sách SQL'
)
ORDER BY dh.id;
~~~

Mỗi đơn xuất hiện tối đa một lần, vì `EXISTS` chỉ kiểm tra sự tồn tại. Nếu câu UPDATE chỉ cần điều kiện có/không và không lấy giá trị từ dòng con, `EXISTS` thường dễ kiểm soát cấp hàng hơn JOIN trực tiếp.

### 9.4. Không chọn một dòng nguồn ngẫu nhiên

Giả sử một đơn có hai dòng chi tiết, mỗi dòng có số lượng khác nhau, và bạn viết `UPDATE ... FROM ct SET ghi_chu = ct.so_luong::TEXT` mà không quy định chọn dòng nào. Kết quả ghi chú có thể phụ thuộc dòng nguồn mà bộ thực thi dùng.

Nếu yêu cầu là **tổng số lượng của đơn**, cần tổng hợp:

~~~sql
SELECT
    don_hang_id,
    SUM(so_luong) AS tong_so_luong
FROM pv_chi_tiet_don
GROUP BY don_hang_id;
~~~

Rồi JOIN bảng tổng hợp **một dòng mỗi đơn** vào UPDATE. Đó mới là nguồn giá trị được xác định đúng nghiệp vụ.

## 10. Mẫu 4: cập nhật dựa trên tổng hợp của bảng con

Yêu cầu: với các đơn NEW có **tổng số lượng dòng chi tiết từ 3 trở lên**, đặt ghi chú `'DON_NHIEU_HANG'`.

### 10.1. Tính nguồn thống kê trước

~~~sql
SELECT
    don_hang_id,
    SUM(so_luong) AS tong_so_luong
FROM pv_chi_tiet_don
GROUP BY don_hang_id
ORDER BY don_hang_id;
~~~

Ví dụ:

- Đơn 101 có 2 + 1 = **3** sản phẩm.
- Đơn 103 có 3 + 1 = **4** sản phẩm.
- Đơn 108 có **2** sản phẩm.

### 10.2. SELECT tiền kiểm đúng một hàng mỗi đơn

~~~sql
WITH so_luong_theo_don AS (
    SELECT
        don_hang_id,
        SUM(so_luong) AS tong_so_luong
    FROM pv_chi_tiet_don
    GROUP BY don_hang_id
)
SELECT
    dh.id,
    dh.trang_thai,
    sl.tong_so_luong,
    dh.ghi_chu AS ghi_chu_cu,
    'DON_NHIEU_HANG' AS ghi_chu_moi
FROM pv_don_hang AS dh
JOIN so_luong_theo_don AS sl
    ON sl.don_hang_id = dh.id
WHERE dh.trang_thai = 'NEW'
  AND sl.tong_so_luong >= 3
ORDER BY dh.id;
~~~

Kết quả: hai đơn **101** và **103**.

### 10.3. UPDATE dùng cùng nguồn và điều kiện

~~~sql
BEGIN;

WITH so_luong_theo_don AS (
    SELECT
        don_hang_id,
        SUM(so_luong) AS tong_so_luong
    FROM pv_chi_tiet_don
    GROUP BY don_hang_id
)
UPDATE pv_don_hang AS dh
SET ghi_chu = 'DON_NHIEU_HANG'
FROM so_luong_theo_don AS sl
WHERE sl.don_hang_id = dh.id
  AND dh.trang_thai = 'NEW'
  AND sl.tong_so_luong >= 3
RETURNING dh.id, dh.ghi_chu;

ROLLBACK;
~~~

Bảng `so_luong_theo_don` có **tối đa một dòng/đơn**, vì GROUP BY trên `don_hang_id`. Điều này giúp tránh nguồn dữ liệu mơ hồ khi dùng UPDATE FROM.

### 10.4. Mẫu khác dùng EXISTS hoặc IN

Nếu bạn chỉ cần điều kiện tổng số lượng đạt ngưỡng, có thể dùng:

~~~sql
SELECT dh.id
FROM pv_don_hang AS dh
WHERE dh.trang_thai = 'NEW'
  AND dh.id IN (
      SELECT ct.don_hang_id
      FROM pv_chi_tiet_don AS ct
      GROUP BY ct.don_hang_id
      HAVING SUM(ct.so_luong) >= 3
  )
ORDER BY dh.id;
~~~

Tập ID vẫn là 101 và 103. Khi chuyển thành UPDATE, giữ điều kiện `IN` tương ứng; cách viết nào rõ hơn tùy độ phức tạp và cột cần lấy.

## 11. SELECT tương ứng cho DELETE ... USING

PostgreSQL hỗ trợ `DELETE ... USING` để xóa một bảng dựa trên các bảng khác.

Ví dụ yêu cầu: xóa **dòng chi tiết của những đơn CANCELLED trước 01/10/2026**. Đây là bước có thể cần làm trước khi xóa đơn cha vì FK.

### 11.1. SELECT tiền kiểm theo đúng JOIN

~~~sql
SELECT
    ct.id AS dong_don_id,
    ct.don_hang_id,
    dh.trang_thai,
    dh.ngay_dat,
    ct.ten_san_pham,
    ct.so_luong
FROM pv_chi_tiet_don AS ct
JOIN pv_don_hang AS dh
    ON dh.id = ct.don_hang_id
WHERE dh.trang_thai = 'CANCELLED'
  AND dh.ngay_dat < DATE '2026-10-01'
ORDER BY ct.id;
~~~

Kết quả:

| dong_don_id | don_hang_id | trang_thai | ngay_dat |
|---:|---:|---|---|
| 1006 | 104 | CANCELLED | 2026-09-20 |
| 1008 | 106 | CANCELLED | 2026-08-10 |
| 1012 | 110 | CANCELLED | 2026-09-01 |

Có **3 dòng chi tiết** thuộc ba đơn cũ.

### 11.2. DELETE ... USING tương ứng

~~~sql
BEGIN;

DELETE FROM pv_chi_tiet_don AS ct
USING pv_don_hang AS dh
WHERE ct.don_hang_id = dh.id
  AND dh.trang_thai = 'CANCELLED'
  AND dh.ngay_dat < DATE '2026-10-01'
RETURNING ct.id, ct.don_hang_id;

ROLLBACK;
~~~

Câu SELECT tiền kiểm dùng `JOIN ... ON`, còn DELETE USING đặt điều kiện nối:

~~~sql
ct.don_hang_id = dh.id
~~~

trong `WHERE`. Nếu bỏ điều kiện này, điều kiện ngày/trạng thái ở bảng đơn có thể khiến **mọi dòng chi tiết** trở thành ứng viên xóa khi có ít nhất một đơn thỏa điều kiện — một lỗi rất nghiêm trọng.

### 11.3. Khóa mục tiêu là khóa của bảng bị xóa

Trong ví dụ này, **bảng mục tiêu là `pv_chi_tiet_don`**, không phải `pv_don_hang`. Vì vậy, danh sách tiền kiểm cần chú trọng `ct.id` và số dòng con, dù điều kiện tham chiếu đến bảng đơn.

Đếm `COUNT(DISTINCT dh.id)` chỉ cho biết số **đơn cha**, không phải số **dòng chi tiết bị xóa**. Đối với DELETE bảng con, số dòng bị xóa phải tính theo `ct.id`.

## 12. Trước DELETE bảng cha, kiểm tra ràng buộc tham chiếu

Yêu cầu: xóa ba đơn CANCELLED cũ: 104, 106, 110.

### 12.1. SELECT xem trước bảng cha

~~~sql
SELECT
    dh.id,
    dh.khach_hang_id,
    dh.ngay_dat,
    dh.trang_thai,
    dh.tong_tien
FROM pv_don_hang AS dh
WHERE dh.trang_thai = 'CANCELLED'
  AND dh.ngay_dat < DATE '2026-10-01'
ORDER BY dh.id;
~~~

Kết quả: **104, 106, 110**.

### 12.2. Xem trước số dòng con tham chiếu

~~~sql
SELECT
    dh.id AS don_hang_id,
    COUNT(ct.id) AS so_dong_chi_tiet
FROM pv_don_hang AS dh
LEFT JOIN pv_chi_tiet_don AS ct
    ON ct.don_hang_id = dh.id
WHERE dh.trang_thai = 'CANCELLED'
  AND dh.ngay_dat < DATE '2026-10-01'
GROUP BY dh.id
ORDER BY dh.id;
~~~

Trong dữ liệu mẫu, mỗi đơn mục tiêu có **một dòng chi tiết**. Vì FK của `pv_chi_tiet_don` không khai báo `ON DELETE CASCADE`, xóa trực tiếp đơn cha trước sẽ bị từ chối khi còn dòng con.

### 12.3. Trình tự xóa con rồi cha trong một transaction

~~~sql
BEGIN;

-- Tiền kiểm tập đơn cha.
SELECT dh.id, dh.trang_thai, dh.ngay_dat
FROM pv_don_hang AS dh
WHERE dh.trang_thai = 'CANCELLED'
  AND dh.ngay_dat < DATE '2026-10-01'
ORDER BY dh.id
FOR UPDATE;

-- Bước 1: xóa các dòng con của tập đơn đó.
DELETE FROM pv_chi_tiet_don AS ct
USING pv_don_hang AS dh
WHERE ct.don_hang_id = dh.id
  AND dh.trang_thai = 'CANCELLED'
  AND dh.ngay_dat < DATE '2026-10-01'
RETURNING ct.id, ct.don_hang_id;

-- Bước 2: xóa các đơn cha tương ứng.
DELETE FROM pv_don_hang AS dh
WHERE dh.trang_thai = 'CANCELLED'
  AND dh.ngay_dat < DATE '2026-10-01'
RETURNING dh.id, dh.khach_hang_id;

-- Bài học chỉ mô phỏng, giữ nguyên dữ liệu gốc.
ROLLBACK;
~~~

Trong dữ liệu mẫu không có thao tác đồng thời, bước 1 xóa tạm ba dòng 1006, 1008, 1012; bước 2 xóa tạm ba đơn 104, 106, 110; ROLLBACK đưa chúng trở lại.

**Lưu ý:** `FOR UPDATE` đặt khóa trên các hàng cha tìm được trong PostgreSQL, nhưng không nên xem nó là bảo đảm tuyệt đối rằng mọi tập dòng có thể bị ảnh hưởng sẽ bất biến trước mọi giao dịch khác. Việc đồng bộ các thao tác xóa phức tạp cần xét khóa FK, mức cô lập, thứ tự khóa và các thao tác ghi đang cạnh tranh.

### 12.4. Nếu có ON DELETE CASCADE thì sao?

Nếu FK ở bảng con được thiết kế `ON DELETE CASCADE`, xóa đơn cha có thể tự động xóa các dòng con liên quan. Khi đó, chỉ xem trước **ba đơn cha** là chưa đủ để diễn tả đầy đủ hậu quả. Cần kiểm tra **số dòng con sẽ bị xóa dây chuyền**, các bảng phụ thuộc khác và trigger.

Trong schema thực hành, FK dùng quy tắc không tự cascade; **không được giả định** cascade diễn ra chỉ vì các bảng có quan hệ cha–con.

### 12.5. Có khi chỉ nên đánh dấu xóa mềm

Nhiều hệ thống có yêu cầu giữ lịch sử đơn hàng. Thay vì DELETE vật lý:

~~~sql
UPDATE pv_don_hang
SET ghi_chu = 'LUU_TRU'
WHERE trang_thai = 'CANCELLED'
  AND ngay_dat < DATE '2026-10-01';
~~~

Bạn vẫn phải SELECT xem trước, kiểm tra số hàng và quyền nghiệp vụ. Tuy nhiên, gắn ghi chú không tự tạo một hệ thống **soft delete** đầy đủ; ứng dụng thật thường có cột trạng thái xóa, thời điểm, người thao tác, chính sách đọc và các ràng buộc riêng.

## 13. SELECT với EXISTS và NOT EXISTS

Các điều kiện tồn tại rất hữu ích khi mục tiêu là **“có ít nhất một bản ghi liên quan”** hoặc **“không có bản ghi liên quan”**.

### 13.1. Khách có đơn PAID

~~~sql
SELECT
    kh.id,
    kh.ho_ten
FROM pv_khach_hang AS kh
WHERE EXISTS (
    SELECT 1
    FROM pv_don_hang AS dh
    WHERE dh.khach_hang_id = kh.id
      AND dh.trang_thai = 'PAID'
)
ORDER BY kh.id;
~~~

Kết quả: khách **An** (ID 1) và **Dũng** (ID 4).

Nếu UPDATE khách hàng dựa trên điều kiện này, `EXISTS` không nhân An hay Dũng theo số đơn PAID. Điều kiện của UPDATE cần giữ giống SELECT, ví dụ thêm cờ đã xác minh ở bảng khách thực nếu schema có cột tương ứng.

### 13.2. Khách INACTIVE chưa có đơn

Đã xem ở phần 7:

~~~sql
WHERE kh.trang_thai = 'INACTIVE'
  AND NOT EXISTS (
      SELECT 1
      FROM pv_don_hang AS dh
      WHERE dh.khach_hang_id = kh.id
  )
~~~

Kết quả đúng là Minh.

### 13.3. Vì sao cần cẩn thận với NOT IN?

Ví dụ độc lập:

~~~sql
SELECT a.id
FROM (VALUES (1), (2), (3)) AS a(id)
WHERE a.id NOT IN (
    SELECT b.id
    FROM (VALUES (1), (NULL::INTEGER)) AS b(id)
)
ORDER BY a.id;
~~~

Kết quả: **không có hàng nào**, vì NULL trong tập con làm phép so sánh đối với các giá trị không khớp trở thành UNKNOWN.

`NOT EXISTS` với điều kiện tương quan thường thể hiện câu hỏi “không có bản ghi phù hợp” rõ hơn khi nguồn có thể chứa NULL. Không thay thế `NOT EXISTS` bằng `NOT IN` mà chưa xác định các biểu thức có chắc chắn NOT NULL hay không.

## 14. AND, OR và dấu ngoặc: tiền kiểm phát hiện mở rộng sai

Yêu cầu: chọn đơn **CANCELLED trước 01/10**. Điều kiện đúng:

~~~sql
WHERE trang_thai = 'CANCELLED'
  AND ngay_dat < DATE '2026-10-01'
~~~

Nhưng câu sau có ý nghĩa khác:

~~~sql
WHERE trang_thai = 'CANCELLED'
  AND ngay_dat < DATE '2026-10-01'
  OR khach_hang_id = 4
~~~

Theo độ ưu tiên toán tử SQL, `AND` được đánh giá trước `OR`, nên biểu thức tương đương:

~~~sql
WHERE (
    trang_thai = 'CANCELLED'
    AND ngay_dat < DATE '2026-10-01'
)
OR khach_hang_id = 4
~~~

Nó chọn **104, 106, 110** và thêm **107** vì đơn 107 thuộc khách 4, dù đã PAID và có ngày 09/10.

### 14.1. Khi ý định là khách 4 nhưng vẫn phải CANCELLED cũ

Nếu nghiệp vụ muốn chỉ đơn CANCELLED cũ **của khách 4**, phải viết:

~~~sql
WHERE trang_thai = 'CANCELLED'
  AND ngay_dat < DATE '2026-10-01'
  AND khach_hang_id = 4
~~~

Kết quả chỉ có **106**.

### 14.2. Cách quan sát rõ nguyên nhân một hàng được chọn

~~~sql
SELECT
    id,
    khach_hang_id,
    trang_thai,
    ngay_dat,
    (
        trang_thai = 'CANCELLED'
        AND ngay_dat < DATE '2026-10-01'
    ) AS thoa_nhom_huy_cu,
    (khach_hang_id = 4) AS thoa_khach_4
FROM pv_don_hang
WHERE (
    trang_thai = 'CANCELLED'
    AND ngay_dat < DATE '2026-10-01'
)
OR khach_hang_id = 4
ORDER BY id;
~~~

Hai cột boolean giúp thấy rõ **107 được chọn bởi nhánh thứ hai**. Đây là kỹ thuật xem trước hữu ích khi điều kiện có nhiều nhánh phức tạp.

## 15. NULL và các điều kiện không chọn được như bạn tưởng

SQL sử dụng logic ba giá trị: TRUE, FALSE và UNKNOWN. Trong WHERE, chỉ những hàng có điều kiện **TRUE** được giữ.

### 15.1. Không dùng = NULL

Sai:

~~~sql
SELECT id, ghi_chu
FROM pv_don_hang
WHERE ghi_chu = NULL;
~~~

Điều kiện so sánh với NULL trả UNKNOWN, nên không chọn những hàng có ghi chú NULL như mong muốn.

Đúng:

~~~sql
SELECT id, ghi_chu
FROM pv_don_hang
WHERE ghi_chu IS NULL
ORDER BY id;
~~~

Với dữ liệu vừa tạo, kết quả có **11 đơn**, vì mọi `ghi_chu` ban đầu đều NULL.

### 15.2. Cập nhật hàng NULL cần SELECT đúng predicate

Yêu cầu đặt `ghi_chu = 'CHUA_GHI_CHU'` cho các đơn còn thiếu ghi chú.

Xem trước:

~~~sql
SELECT
    id,
    ghi_chu AS ghi_chu_cu,
    'CHUA_GHI_CHU' AS ghi_chu_moi
FROM pv_don_hang
WHERE ghi_chu IS NULL
ORDER BY id;
~~~

UPDATE:

~~~sql
UPDATE pv_don_hang
SET ghi_chu = 'CHUA_GHI_CHU'
WHERE ghi_chu IS NULL;
~~~

Nếu thay điều kiện UPDATE bằng `ghi_chu = NULL`, kết quả thực sẽ là **0 hàng**, dù SELECT tiền kiểm đúng có 11. Điều này nhấn mạnh rằng **cùng một predicate** là nguyên tắc cốt lõi.

### 15.3. IS DISTINCT FROM trong PostgreSQL

Khi cần so sánh an toàn với NULL, PostgreSQL có:

~~~sql
a IS DISTINCT FROM b
~~~

Khác `a <> b` thông thường, `IS DISTINCT FROM` trả TRUE/FALSE theo cách xem NULL như một giá trị có thể so khác. Ví dụ:

~~~sql
SELECT
    id,
    ghi_chu
FROM pv_don_hang
WHERE ghi_chu IS DISTINCT FROM 'CAN_UU_TIEN'
ORDER BY id;
~~~

Với dữ liệu ban đầu ghi chú NULL, điều kiện chọn toàn bộ đơn. Cách viết này hữu ích khi bạn **chỉ muốn UPDATE những hàng có giá trị khác giá trị đích**, kể cả từ NULL sang văn bản.

### 15.4. Idempotency không thay thế việc xem trước

Một thao tác lặp:

~~~sql
UPDATE pv_don_hang
SET da_thong_bao = TRUE
WHERE trang_thai = 'NEW';
~~~

lần đầu và lần hai có thể cùng chọn năm hàng ngay cả khi chúng đã TRUE, nếu predicate không kiểm tra giá trị cũ. Nếu chỉ muốn tác động những hàng **thật sự cần đổi**:

~~~sql
WHERE trang_thai = 'NEW'
  AND da_thong_bao = FALSE
~~~

Một số hệ quản trị/driver phân biệt số hàng khớp và số hàng thực sự đổi giá trị ở các báo cáo affected rows; không nên dựa vào số đó mà bỏ kiểm tra predicate.

## 16. Ranh giới thời gian: DATE, TIMESTAMP và khoảng nửa mở

Một câu SELECT tiền kiểm sai ngày sẽ làm UPDATE/DELETE sai cùng cách.

### 16.1. “Trước ngày” khác “đến hết ngày”

~~~sql
-- Trước 05/10: không gồm 05/10.
WHERE ngay_dat < DATE '2026-10-05'
~~~

~~~sql
-- Từ 01/10 đến hết 05/10 với cột DATE.
WHERE ngay_dat >= DATE '2026-10-01'
  AND ngay_dat <= DATE '2026-10-05'
~~~

Đối với cột `DATE`, `<= DATE '2026-10-05'` bao gồm ngày 05/10. Nhưng nếu cột là TIMESTAMP chứa cả giờ phút giây, so sánh với một DATE được chuyển thành thời điểm đầu ngày có thể không bao phủ phần còn lại của ngày ấy như bạn tưởng.

### 16.2. Khoảng nửa mở cho thời điểm

Mẫu thường an toàn khi lọc khoảng thời gian:

~~~sql
WHERE tao_luc >= TIMESTAMP '2026-10-01 00:00:00'
  AND tao_luc <  TIMESTAMP '2026-11-01 00:00:00'
~~~

Nó có nghĩa **từ đầu 01/10 đến trước đầu 01/11**. Không cần dự đoán độ chính xác đến mili-giây hay micro-giây ở cuối ngày 31/10.

### 16.3. Múi giờ là một phần yêu cầu

Nếu cột `TIMESTAMPTZ` lưu thời điểm tuyệt đối và báo cáo định nghĩa tháng theo giờ Việt Nam, cần xác định **múi giờ nghiệp vụ** trước khi tạo ranh giới. Không sử dụng một mốc thời gian mơ hồ ở UTC rồi gọi là “trước 00:00 giờ địa phương”.

Trong bộ dữ liệu mẫu, `ngay_dat` là DATE thuần túy, nên ví dụ tránh những vấn đề chuyển đổi thời điểm phức tạp hơn.

## 17. ORDER BY và LIMIT trong SELECT chỉ để xem trước

Một cách xem nhanh:

~~~sql
SELECT id, trang_thai, ngay_dat
FROM pv_don_hang
WHERE trang_thai = 'NEW'
ORDER BY id
LIMIT 2;
~~~

Câu này chỉ hiển thị **hai trong năm đơn NEW**. Nó **không chứng minh** UPDATE có cùng WHERE sẽ chỉ tác động hai hàng.

Nếu câu DML là:

~~~sql
UPDATE pv_don_hang
SET ghi_chu = 'XEM_XET'
WHERE trang_thai = 'NEW';
~~~

thì trong dữ liệu gốc, mục tiêu là **5 đơn**, không phải 2.

### 17.1. Tránh dùng LIMIT cho tiền kiểm cuối cùng

Đối với thao tác ghi quan trọng, nên:

1. Đếm **toàn bộ tập** bằng COUNT.
2. Liệt kê khóa hoặc xuất một danh sách được kiểm soát.
3. Nếu kết quả quá lớn để hiển thị, dùng phân trang chỉ để **duyệt**, nhưng vẫn nắm rõ tổng số ID mục tiêu.
4. Giới hạn thực sự **bằng predicate ở câu UPDATE/DELETE**, không dựa vào LIMIT chỉ có trong SELECT.

### 17.2. PostgreSQL UPDATE/DELETE và LIMIT

PostgreSQL không dùng trực tiếp `UPDATE ... LIMIT n` hoặc `DELETE ... LIMIT n` như một cú pháp mặc định. Nếu cần thay đổi đúng một tập nhỏ, có thể chọn ID trong CTE rồi UPDATE theo ID. Nhưng để an toàn trong môi trường đồng thời, cần xét cách chọn ID, thứ tự ổn định, khóa hàng và sự thay đổi của dữ liệu.

Ví dụ **chỉ minh họa ý tưởng**, không nên xem là mẫu xóa production chỉ bằng việc chép lại:

~~~sql
WITH muc_tieu AS (
    SELECT id
    FROM pv_don_hang
    WHERE trang_thai = 'NEW'
    ORDER BY ngay_dat, id
    LIMIT 2
)
SELECT dh.*
FROM pv_don_hang AS dh
JOIN muc_tieu AS mt
    ON mt.id = dh.id
ORDER BY dh.ngay_dat, dh.id;
~~~

CTE xác định **hai ID được xem trước**. Khi thật sự cập nhật, phải dùng cùng tập ID và bảo đảm chính sách chọn hàng ổn định trong transaction; không chỉ chạy một SELECT LIMIT rồi UPDATE bằng WHERE rộng hơn.

### 17.3. Không nhầm thứ tự hiển thị với thứ tự cập nhật/xóa

`ORDER BY` ở SELECT ngoài giúp con người đọc kết quả. UPDATE/DELETE quan hệ không cam kết sửa các hàng theo thứ tự đó, trừ khi có cơ chế được DBMS tài liệu hóa cho tình huống cụ thể.

## 18. SELECT xem trước và dữ liệu thay đổi đồng thời

Một câu SELECT chạy lúc 10:00, còn UPDATE chạy lúc 10:01, không bảo đảm dữ liệu giữa hai thời điểm giống nhau.

### 18.1. Ví dụ nguy cơ

~~~text
Kết nối A: SELECT các đơn NEW trước 05/10
           → thấy 101, 103, 108

Kết nối B: thay đơn 103 từ NEW sang PAID và COMMIT

Kết nối A: UPDATE ... WHERE trang_thai = 'NEW'
           AND ngay_dat < 05/10
           → có thể chỉ tác động 101, 108
~~~

Cả SELECT và UPDATE có thể đúng theo dữ liệu tại thời điểm **riêng của từng statement**. Nhưng tập cuối khác tập đã xem trước.

### 18.2. READ COMMITTED: mỗi statement có thể thấy snapshot khác

Ở PostgreSQL với mức cô lập `READ COMMITTED` thường dùng, các statement trong cùng transaction có thể đọc những phiên bản dữ liệu khác nhau khi các giao dịch khác COMMIT giữa các statement.

Do đó:

~~~sql
BEGIN;
SELECT ...;
UPDATE ...;
COMMIT;
~~~

**không tự bảo đảm** tập SELECT và UPDATE giống nhau chỉ vì chúng nằm trong cùng transaction.

### 18.3. SELECT FOR UPDATE để khóa các hàng được chọn

Nếu cần xem trước rồi thao tác trên chính những hàng hiện có, có thể khóa chúng trong transaction:

~~~sql
BEGIN;

SELECT
    id,
    trang_thai,
    ngay_dat,
    da_thong_bao
FROM pv_don_hang
WHERE trang_thai = 'NEW'
  AND ngay_dat < DATE '2026-10-05'
  AND da_thong_bao = FALSE
ORDER BY id
FOR UPDATE;

UPDATE pv_don_hang
SET da_thong_bao = TRUE
WHERE trang_thai = 'NEW'
  AND ngay_dat < DATE '2026-10-05'
  AND da_thong_bao = FALSE
RETURNING id;

ROLLBACK;
~~~

`FOR UPDATE` tạo khóa hàng trên những dòng SELECT tìm thấy, có thể chặn các giao dịch khác sửa/xóa chính những hàng ấy cho đến khi transaction kết thúc.

**Nhưng:** khóa các hàng đã tìm thấy không tự khóa mọi **hàng mới có thể lọt vào predicate**. Một giao dịch khác có thể chèn thêm đơn NEW hoặc làm một hàng khác thỏa điều kiện. Nếu cần bảo đảm UPDATE chỉ tác động **chính xác danh sách ID đã duyệt**, phải thiết kế thao tác theo tập ID cố định và chính sách đồng thời phù hợp.

### 18.4. Cố định tập ID đã duyệt

Ở ứng dụng, có thể lưu danh sách khóa đã chấp thuận như `101, 103, 108`; khi cập nhật, dùng:

~~~sql
BEGIN;

UPDATE pv_don_hang
SET da_thong_bao = TRUE
WHERE id IN (101, 103, 108)
  AND trang_thai = 'NEW'
  AND ngay_dat < DATE '2026-10-05'
  AND da_thong_bao = FALSE
RETURNING id;

ROLLBACK;
~~~

Câu này **không tác động các ID ngoài danh sách**, ngay cả khi chúng mới thỏa điều kiện. Việc kiểm tra lại các predicate trong UPDATE giúp tránh cập nhật một ID đã đổi trạng thái.

Tuy nhiên, nếu một ID đã không còn đáp ứng điều kiện, UPDATE có thể trả ít hơn ba hàng. Ứng dụng cần **so sánh tập ID RETURNING với tập đã chấp thuận**, rồi quyết định rollback, yêu cầu duyệt lại hoặc xử lý theo nghiệp vụ.

Đây là ví dụ với các ID đã biết trong dữ liệu mẫu. Trong ứng dụng thật, dùng **tham số hóa danh sách ID** chứ không ghép chuỗi tùy tiện từ đầu vào người dùng.

### 18.5. Mức cô lập cao hơn cũng có chi phí

`REPEATABLE READ` hoặc `SERIALIZABLE` ở PostgreSQL có thể cung cấp bảo đảm mạnh hơn về snapshot hoặc phát hiện xung đột phù hợp, nhưng cũng có thể gây lỗi serialization/retry và không thay thế việc xác định tập ID, ràng buộc, quyền và điều kiện nghiệp vụ.

Không nên chuyển mọi câu lệnh sang SERIALIZABLE chỉ vì một bài toán SELECT xem trước. Cần hiểu mức cô lập mong muốn và kiểu cạnh tranh của hệ thống.

### 18.6. Đừng giữ khóa suốt thời gian chờ người duyệt

Nếu người dùng mở màn hình xem trước rồi ngồi đọc nhiều phút, giữ một transaction có `FOR UPDATE` trong thời gian đó có thể gây khóa kéo dài và làm chậm các thao tác khác.

Một thiết kế thường dùng là:

1. SELECT để tạo **bản xem trước** và cho người dùng duyệt ngoài transaction ghi kéo dài.
2. Khi người dùng xác nhận, bắt đầu transaction mới.
3. Khóa/kiểm tra lại những ID dự định tác động và các điều kiện trước khi ghi.
4. Nếu dữ liệu đã thay đổi, yêu cầu duyệt lại thay vì âm thầm áp dụng trên tập khác.
5. UPDATE/DELETE, so RETURNING, rồi COMMIT hoặc ROLLBACK.

Không có một chiến lược duy nhất cho mọi ứng dụng; chi tiết tùy yêu cầu nhất quán và mức độ rủi ro.

## 19. So sánh tập mục tiêu bằng ID và RETURNING

Một kỹ thuật kiểm tra có giá trị là lưu **tập khóa mục tiêu** từ SELECT, rồi so với **tập khóa thật sự đã đổi**.

Ví dụ ở thao tác báo đơn NEW cũ:

~~~text
Dự kiến:  {101, 103, 108}
Thực tế: {101, 103, 108}
→ Tập giống nhau.
~~~

Nhưng nếu:

~~~text
Dự kiến:  {101, 103, 108}
Thực tế: {101, 108}
→ Thiếu 103; cần tìm nguyên nhân, chưa nên tự động COMMIT.
~~~

### 19.1. COUNT bằng nhau chưa đủ

Hai tập:

~~~text
Dự kiến:  {101, 103, 108}
Thực tế: {101, 105, 108}
~~~

đều có **3 hàng** nhưng **khác một ID**. Vì thế với thao tác quan trọng, so **tập khóa** tốt hơn chỉ so số dòng.

### 19.2. Trong PostgreSQL, RETURNING cho khóa thật sự tác động

~~~sql
UPDATE pv_don_hang
SET da_thong_bao = TRUE
WHERE trang_thai = 'NEW'
  AND ngay_dat < DATE '2026-10-05'
  AND da_thong_bao = FALSE
RETURNING id;
~~~

Truy vấn trả mỗi ID của hàng được UPDATE. Khi DELETE:

~~~sql
DELETE FROM pv_khach_hang AS kh
WHERE kh.id = 7
  AND kh.trang_thai = 'INACTIVE'
  AND NOT EXISTS (
      SELECT 1 FROM pv_don_hang AS dh
      WHERE dh.khach_hang_id = kh.id
  )
RETURNING kh.id;
~~~

nó trả ID khách đã bị xóa. Trong các ví dụ thực hành, hãy bọc bằng transaction và rollback nếu chỉ muốn mô phỏng.

### 19.3. Giá trị cũ và mới: phụ thuộc DBMS

Ở PostgreSQL, `UPDATE ... RETURNING` thường được dùng để trả các **giá trị của hàng sau UPDATE**. Để xem giá trị trước đó, dùng SELECT tiền kiểm, CTE chụp dữ liệu hoặc cơ chế audit phù hợp với phiên bản PostgreSQL.

Ở SQL Server, mệnh đề OUTPUT có bảng logic `deleted` và `inserted` để lấy giá trị cũ/mới theo cú pháp riêng. Đừng sao chép `OUTPUT deleted...` sang PostgreSQL rồi giả định hoạt động tương tự.

## 20. Với một khóa chính tổng hợp, phải xem đủ các cột

Một số bảng không có `id` đơn. Ví dụ bảng liên kết:

~~~sql
CREATE TEMP TABLE pv_dang_ky (
    sinh_vien_id INTEGER NOT NULL,
    khoa_hoc_id INTEGER NOT NULL,
    trang_thai TEXT NOT NULL,
    PRIMARY KEY (sinh_vien_id, khoa_hoc_id)
);

INSERT INTO pv_dang_ky
    (sinh_vien_id, khoa_hoc_id, trang_thai)
VALUES
    (1, 100, 'PENDING'),
    (1, 200, 'ACTIVE'),
    (2, 100, 'PENDING');
~~~

Yêu cầu xóa đăng ký PENDING của sinh viên 1:

~~~sql
SELECT
    sinh_vien_id,
    khoa_hoc_id,
    trang_thai
FROM pv_dang_ky
WHERE sinh_vien_id = 1
  AND trang_thai = 'PENDING'
ORDER BY khoa_hoc_id;
~~~

Kết quả: cặp khóa **(1, 100)**.

DELETE tương ứng:

~~~sql
BEGIN;

DELETE FROM pv_dang_ky
WHERE sinh_vien_id = 1
  AND trang_thai = 'PENDING'
RETURNING sinh_vien_id, khoa_hoc_id;

ROLLBACK;
~~~

Ở đây **khóa của một hàng là cặp `(sinh_vien_id, khoa_hoc_id)`**. Chỉ xem `sinh_vien_id = 1` chưa đủ nhận diện chính xác đăng ký nào được xóa.

## 21. Dùng CTE để chia tập mục tiêu có tên

Khi điều kiện phức tạp, CTE giúp tách **xác định mục tiêu** khỏi **dự đoán thay đổi**.

### 21.1. SELECT xem trước với CTE

~~~sql
WITH muc_tieu AS (
    SELECT
        dh.id,
        dh.trang_thai,
        dh.ngay_dat,
        dh.da_thong_bao
    FROM pv_don_hang AS dh
    WHERE dh.trang_thai = 'NEW'
      AND dh.ngay_dat < DATE '2026-10-05'
      AND dh.da_thong_bao = FALSE
)
SELECT
    id,
    trang_thai,
    ngay_dat,
    da_thong_bao AS gia_tri_cu,
    TRUE AS gia_tri_moi
FROM muc_tieu
ORDER BY id;
~~~

Kết quả: 101, 103, 108.

### 21.2. Dùng CTE tập ID trong UPDATE

~~~sql
BEGIN;

WITH muc_tieu AS (
    SELECT id
    FROM pv_don_hang
    WHERE trang_thai = 'NEW'
      AND ngay_dat < DATE '2026-10-05'
      AND da_thong_bao = FALSE
)
UPDATE pv_don_hang AS dh
SET da_thong_bao = TRUE
FROM muc_tieu AS mt
WHERE dh.id = mt.id
RETURNING dh.id, dh.da_thong_bao;

ROLLBACK;
~~~

Ý tưởng là **định danh tập ID mục tiêu một cách rõ ràng**. Ở đây CTE chỉ có một hàng cho mỗi ID vì lấy trực tiếp khóa chính từ bảng đơn.

### 21.3. Không nhầm “CTE tên giống nhau” với snapshot cố định giữa hai statement

Nếu bạn chạy một SELECT có `WITH muc_tieu AS (...)`, rồi một UPDATE ở **statement khác** cũng khai báo CTE cùng tên, hai câu lệnh có thể nhìn thấy dữ liệu khác nhau do concurrency.

CTE không tồn tại ngoài statement và không tự “đóng băng” tập hàng ở lần chạy trước. Muốn cố định danh sách duyệt qua nhiều bước, cần lưu ID ở ứng dụng/bảng staging phù hợp và thực thi theo cơ chế transaction, khóa hoặc mức cô lập đã chọn.

## 22. SELECT kiểm tra trước khi sửa hàng loạt theo danh sách ID

Đôi khi yêu cầu đã được xác định bằng một danh sách ID cụ thể do người có quyền phê duyệt. Khi ấy, tốt hơn nên giữ đúng danh sách ID trong cả SELECT và DML.

Ví dụ người dùng chỉ phê duyệt đơn 101 và 103:

~~~sql
SELECT
    id,
    trang_thai,
    ghi_chu
FROM pv_don_hang
WHERE id IN (101, 103)
ORDER BY id;
~~~

Sau đó:

~~~sql
BEGIN;

UPDATE pv_don_hang
SET ghi_chu = 'DA_DUYET'
WHERE id IN (101, 103)
  AND trang_thai = 'NEW'
RETURNING id, ghi_chu;

ROLLBACK;
~~~

Điều kiện `trang_thai = 'NEW'` ở UPDATE là một **điều kiện kiểm tra lại**. Nếu trạng thái của một đơn thay đổi sau màn hình xem trước, câu lệnh có thể không tác động nó. Đó thường là lựa chọn an toàn hơn so với cưỡng ép cập nhật một đơn đã chuyển sang PAID/CANCELLED.

### 22.1. SELECT cũng phải thể hiện điều kiện bổ sung

Để màn hình tiền kiểm dự đoán gần nhất với UPDATE, SELECT nên dùng:

~~~sql
SELECT id, trang_thai, ghi_chu
FROM pv_don_hang
WHERE id IN (101, 103)
  AND trang_thai = 'NEW'
ORDER BY id;
~~~

Nếu SELECT chỉ lọc ID nhưng UPDATE còn kiểm tra trạng thái, số hàng xem trước và số hàng thay đổi có thể khác ngay cả khi không có concurrency. **Mọi điều kiện ảnh hưởng tập mục tiêu phải được phản ánh trong tiền kiểm**.

### 22.2. Danh sách ID từ người dùng phải được tham số hóa

Trong ứng dụng, không ghép raw text như:

~~~text
"WHERE id IN (" + userSuppliedString + ")"
~~~

vào SQL. Hãy dùng prepared statements, array parameters, bảng tạm có kiểm soát hoặc cơ chế của framework để truyền danh sách khóa an toàn, và kiểm tra quyền từng ID.

## 23. SELECT có điều kiện JOIN nhưng DELETE bảng nào?

Một câu SELECT có thể đọc cả bảng đơn và bảng chi tiết:

~~~sql
SELECT
    dh.id AS don_hang_id,
    ct.id AS dong_don_id
FROM pv_don_hang AS dh
JOIN pv_chi_tiet_don AS ct
    ON ct.don_hang_id = dh.id
WHERE dh.trang_thai = 'CANCELLED'
ORDER BY dh.id, ct.id;
~~~

Nhưng nó chưa nói rõ bạn định xóa **đơn cha** hay **dòng con**.

- `DELETE FROM pv_don_hang`: tập mục tiêu là các ID **dh.id**, cần xét FK/cascade.
- `DELETE FROM pv_chi_tiet_don`: tập mục tiêu là các ID **ct.id**, đơn cha được giữ.
- Hai DELETE trong transaction: có thể loại cả hai cấp khi nghiệp vụ cho phép và thứ tự đúng.

Trong thao tác thật, màn hình tiền kiểm nên ghi rõ:

~~~text
Bảng tác động: pv_chi_tiet_don
Số dòng con dự kiến xóa: 3
Thuộc các đơn: 104, 106, 110
Bảng đơn cha: không xóa ở statement này
~~~

Thay vì chỉ hiển thị “3 bản ghi” mà không biết bản ghi của bảng nào.

## 24. Thực hành Java/JDBC: cùng predicate và tham số

Trong ứng dụng Java, một nguồn lỗi phổ biến là **màn hình SELECT xem trước** và **lệnh UPDATE khi xác nhận** do hai đoạn code khác nhau tạo ra, làm điều kiện bị lệch.

### 24.1. Chia sẻ cùng định nghĩa điều kiện

Ví dụ dùng `PreparedStatement` và hai tham số `trang_thai`, `ngay_dat`. Điều kiện gồm cả cờ chưa thông báo:

~~~java
String predicate = """
    trang_thai = ?
    AND ngay_dat < ?
    AND da_thong_bao = FALSE
    """;

String previewSql = """
    SELECT id, khach_hang_id, ngay_dat, da_thong_bao
    FROM pv_don_hang
    WHERE
    """ + predicate + " ORDER BY id";

String updateSql = """
    UPDATE pv_don_hang
    SET da_thong_bao = TRUE
    WHERE
    """ + predicate + " RETURNING id";
~~~

Đây là mẫu code minh họa, không phải cơ chế bảo mật tự động. `predicate` là **chuỗi SQL cố định do lập trình viên định nghĩa**, không phải phần SQL nhận trực tiếp từ người dùng. Các giá trị dữ liệu vẫn được truyền bằng tham số JDBC.

### 24.2. Gắn cùng tham số

~~~java
import java.sql.Date;
import java.sql.PreparedStatement;

static void bindTarget(
        PreparedStatement ps
) throws java.sql.SQLException {
    ps.setString(1, "NEW");
    ps.setDate(2, Date.valueOf("2026-10-05"));
}
~~~

Khi `previewSql` và `updateSql` cùng predicate và cùng thứ tự dấu `?`, bạn giảm rủi ro SELECT tìm đơn NEW trước 05/10 nhưng UPDATE lại dùng ngày hoặc trạng thái khác.

### 24.3. Thu thập tập ID trước khi thực hiện

Mẫu Java/JDBC ngắn:

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Date;
import java.util.HashSet;
import java.util.Set;

static Set<Integer> previewIds(
        Connection conn
) throws SQLException {
    String sql = """
        SELECT id
        FROM pv_don_hang
        WHERE trang_thai = ?
          AND ngay_dat < ?
          AND da_thong_bao = FALSE
        ORDER BY id
        """;

    Set<Integer> result = new HashSet<>();

    try (PreparedStatement ps = conn.prepareStatement(sql)) {
        ps.setString(1, "NEW");
        ps.setDate(2, Date.valueOf("2026-10-05"));

        try (ResultSet rs = ps.executeQuery()) {
            while (rs.next()) {
                result.add(rs.getInt("id"));
            }
        }
    }
    return result;
}
~~~

Hàm trả **tập ID** thay vì chỉ COUNT, để có thể đối chiếu các khóa.

### 24.4. Khi xác nhận, cần kiểm tra lại thay vì tin snapshot cũ

Trong ứng dụng thực, giao diện có thể nhận một bản xem trước rồi người dùng nhấn xác nhận sau một khoảng thời gian. Hãy bắt đầu transaction, thực hiện một kiểm tra mới trên các ID đã phê duyệt, rồi UPDATE có điều kiện và so tập ID thực tế.

Một mẫu tư duy:

~~~text
ID đã duyệt = {101, 103, 108}
          │
          ▼
Bắt đầu transaction
          │
          ▼
SELECT các ID đó + kiểm tra trạng thái/phiên bản
          │
          ▼
UPDATE ... WHERE id IN (ID đã duyệt)
             AND điều kiện nghiệp vụ còn đúng
RETURNING id
          │
          ▼
So tập RETURNING với tập đã duyệt
          │
      ┌───┴────┐
      ▼        ▼
    Khớp     Khác
      │        │
    COMMIT   ROLLBACK và báo dữ liệu đã thay đổi
~~~

Nếu thao tác có giá trị cao, có thể dùng **optimistic locking** với cột phiên bản cập nhật, `SELECT FOR UPDATE` hoặc ràng buộc khác theo thiết kế. Không chờ lâu trong transaction có khóa chỉ để người dùng duyệt màn hình.

### 24.5. Kiểm tra số hàng trả về

Với PostgreSQL JDBC, lệnh `UPDATE ... RETURNING id` có thể được thực thi và đọc bằng `executeQuery()` như một tập kết quả. Những DBMS/driver khác có API và cú pháp RETURNING/OUTPUT riêng.

Nếu không dùng RETURNING, `executeUpdate()` trả số hàng ảnh hưởng theo ngữ nghĩa driver. Nhưng so số lượng không phát hiện được tập ID khác nhau; với các thao tác quan trọng, việc ghi lại và đối chiếu khóa vẫn có giá trị.

## 25. Khác biệt cú pháp theo hệ quản trị

Ý tưởng **SELECT trước, dùng cùng điều kiện trong DML** có thể áp dụng rộng rãi. Tuy nhiên, `UPDATE ... FROM`, `DELETE ... USING` và cách trả hàng đã tác động khác nhau giữa các DBMS.

| DBMS | UPDATE/DELETE có nhiều nguồn | Quan sát hàng đã tác động |
|---|---|---|
| **PostgreSQL** | `UPDATE ... FROM`, `DELETE ... USING` | `RETURNING` |
| **MySQL** | `UPDATE ... JOIN`; cú pháp multi-table DELETE | `ROW_COUNT()`/affected rows; `RETURNING` không phải cú pháp chung cho MySQL như PostgreSQL |
| **MariaDB** | UPDATE JOIN và các biến thể DELETE | Có các dạng RETURNING ở phiên bản hỗ trợ, cần kiểm tra loại lệnh |
| **SQL Server** | `UPDATE ... FROM`, DELETE với FROM/JOIN theo T-SQL | `OUTPUT inserted...` và `OUTPUT deleted...` |
| **Oracle** | Điều kiện tương quan, `MERGE` và các cú pháp cập nhật theo phiên bản | `RETURNING ... INTO` trong ngữ cảnh phù hợp |
| **SQLite hiện đại** | `UPDATE ... FROM` ở các phiên bản hỗ trợ; DELETE với subquery | `RETURNING` ở phiên bản hỗ trợ |

### 25.1. PostgreSQL: SELECT và UPDATE FROM

~~~sql
-- Xem trước.
SELECT dh.id, kh.khu_vuc
FROM pv_don_hang AS dh
JOIN pv_khach_hang AS kh
    ON kh.id = dh.khach_hang_id
WHERE dh.trang_thai = 'NEW'
  AND kh.khu_vuc = 'BAC';

-- UPDATE tương ứng.
UPDATE pv_don_hang AS dh
SET ghi_chu = 'KHACH_BAC'
FROM pv_khach_hang AS kh
WHERE kh.id = dh.khach_hang_id
  AND dh.trang_thai = 'NEW'
  AND kh.khu_vuc = 'BAC'
RETURNING dh.id;
~~~

Cả hai phải giữ điều kiện `kh.id = dh.khach_hang_id` và phạm vi khu vực. Câu UPDATE ở đây sẽ sửa dữ liệu nếu chạy ngoài transaction có rollback; chỉ thực hiện khi bạn đang thực hành trên bảng tạm hoặc có chủ đích ghi.

### 25.2. MySQL: UPDATE JOIN

Mẫu cú pháp MySQL, giả sử có bảng `don_hang` và `khach_hang`:

~~~sql
UPDATE don_hang AS dh
JOIN khach_hang AS kh
    ON kh.id = dh.khach_hang_id
SET dh.ghi_chu = 'KHACH_BAC'
WHERE dh.trang_thai = 'NEW'
  AND kh.khu_vuc = 'BAC';
~~~

SELECT tiền kiểm cũng dùng cùng JOIN và WHERE. MySQL khác PostgreSQL ở vị trí các thành phần và cách đặt điều kiện; không sao chép nguyên `UPDATE ... FROM` sang MySQL.

### 25.3. SQL Server: OUTPUT cho giá trị cũ và mới

Ví dụ T-SQL với bảng giả định `dbo.DonHang`:

~~~sql
UPDATE dbo.DonHang
SET DaThongBao = 1
OUTPUT
    DELETED.Id,
    DELETED.DaThongBao AS GiaTriCu,
    INSERTED.DaThongBao AS GiaTriMoi
WHERE TrangThai = 'NEW'
  AND NgayDat < '2026-10-05'
  AND DaThongBao = 0;
~~~

`DELETED` và `INSERTED` là những bảng logic của mệnh đề OUTPUT theo T-SQL, **không phải** bảng dữ liệu `pv_don_hang` của PostgreSQL. Cần xét các hạn chế OUTPUT liên quan trigger theo phiên bản và cấu trúc bảng.

### 25.4. MySQL và SQL Server có thể có cú pháp LIMIT/TOP riêng

Một số hệ quản trị hỗ trợ biến thể giới hạn số hàng bị cập nhật/xóa, nhưng **không nên coi LIMIT 2 là cách an toàn để thay thế predicate** nếu không có thứ tự/khóa ổn định và điều kiện đúng.

Mục tiêu của SELECT tiền kiểm vẫn là xác định được **chính xác tập khóa** sẽ bị tác động, không chỉ giới hạn số lượng ngẫu nhiên.

### 25.5. Oracle và SQLite

Oracle thường dùng điều kiện tương quan `EXISTS`, `MERGE` hoặc những biến thể cập nhật phù hợp phiên bản, đồng thời có cơ chế RETURNING INTO trong ngữ cảnh tương ứng. SQLite có RETURNING ở phiên bản hiện đại, nhưng cú pháp multi-table DELETE không giống PostgreSQL DELETE USING.

**Nguyên tắc di động hơn cú pháp:** mô tả đúng predicate bằng SELECT, kiểm tra khóa/số hàng, rồi thực hiện DML bằng cú pháp của DBMS thực tế.

## 26. Những sai sót thường gặp

| Sai sót | Hậu quả | Cách phòng tránh |
|---|---|---|
| UPDATE/DELETE quên WHERE | Có thể sửa/xóa toàn bảng | Luôn kiểm tra predicate và tập ID trước |
| Chỉ SELECT COUNT(*) | Biết số hàng nhưng không biết hàng nào | Liệt kê PK và cột nghiệp vụ |
| SELECT có LIMIT còn DML không có | Đánh giá thiếu phạm vi tác động | COUNT toàn tập, xem đủ khóa mục tiêu |
| SELECT và DML không cùng điều kiện | Thay đổi hàng không được xem trước | Giữ predicate nhất quán, tham số hóa |
| WHERE với `AND/OR` thiếu ngoặc | Chọn thêm cả hàng không mong muốn | Dùng ngoặc theo mục đích nghiệp vụ |
| Viết `= NULL` | Không chọn hàng NULL như mong muốn | `IS NULL` hoặc `IS DISTINCT FROM` phù hợp |
| Dùng NOT IN khi subquery có NULL | Có thể ra tập rỗng bất ngờ | `NOT EXISTS`/xử lý NULL rõ ràng |
| SELECT JOIN trả nhiều dòng mỗi mục tiêu | Đếm nhầm số hàng UPDATE/DELETE | Đếm DISTINCT khóa bảng mục tiêu |
| UPDATE FROM có nhiều hàng nguồn cho một đích | Giá trị SET từ nguồn có thể không xác định | Ràng buộc unique hoặc tổng hợp một hàng/khóa |
| Quên điều kiện nối trong UPDATE FROM/DELETE USING | Có thể tác động hàng loạt ngoài ý định | So JOIN/ON của SELECT với WHERE của DML |
| Chỉ xem trước hàng cha trước DELETE | Bỏ sót FK, cascade, trigger | Kiểm tra bảng con và ràng buộc |
| DELETE bảng cha có FK con | Lỗi FK hoặc xóa dây chuyền ngoài ý định | Xác định chính sách và trình tự/transaction |
| SELECT rồi UPDATE cách nhau lâu | Tập hàng thay đổi do concurrency | Recheck, khóa phù hợp, tập ID được duyệt |
| Cho rằng BEGIN đủ cố định snapshot | READ COMMITTED có thể thấy thay đổi | Chọn mức cô lập/khóa đúng mục đích |
| Dùng ORDER BY SELECT làm thứ tự xóa | Không có bảo đảm thứ tự DML | Không dựa vào thứ tự hiển thị |
| So chỉ COUNT RETURNING | Hai tập ID khác nhau vẫn cùng COUNT | So tập khóa khi cần tính chính xác cao |
| COMMIT trước khi đối chiếu | Khó quay lại khi phát hiện sai | Kiểm tra trong transaction trước COMMIT |
| Dùng rollback production như “xem trước” mặc định | Trigger/khóa/tài nguyên vẫn có thể bị ảnh hưởng | Ưu tiên SELECT tiền kiểm, dùng DML thử có kiểm soát |
| Tin FK tự kiểm tra quyền sở hữu | FK chỉ đảm bảo quan hệ tồn tại | Phân quyền và kiểm tra nghiệp vụ |
| Tính thời gian bằng ngày kết thúc sai | Có thể thiếu dữ liệu cuối ngày | Khoảng thời gian nửa mở |

## 27. Bài tập thực hành có lời giải

Các bài sử dụng bảng `pv_khach_hang`, `pv_don_hang`, `pv_chi_tiet_don` và `pv_chinh_sach_vung` từ phần 3. Các bài UPDATE/DELETE được bọc trong transaction và kết thúc bằng ROLLBACK để không ảnh hưởng bài sau.

### Bài 1. Xem trước các đơn NEW cũ

**Đề bài:** liệt kê các đơn NEW trước 05/10/2026 chưa được thông báo. Phải có ID, ngày, trạng thái và cờ thông báo.

~~~sql
SELECT id, ngay_dat, trang_thai, da_thong_bao
FROM pv_don_hang
WHERE trang_thai = 'NEW'
  AND ngay_dat < DATE '2026-10-05'
  AND da_thong_bao = FALSE
ORDER BY id;
~~~

**Đáp án:** ID **101, 103, 108**, tổng 3 đơn.

### Bài 2. Viết UPDATE tương ứng và rollback

~~~sql
BEGIN;

UPDATE pv_don_hang
SET da_thong_bao = TRUE
WHERE trang_thai = 'NEW'
  AND ngay_dat < DATE '2026-10-05'
  AND da_thong_bao = FALSE
RETURNING id, da_thong_bao;

ROLLBACK;
~~~

**Đáp án:** RETURNING trả 3 ID 101, 103, 108, cờ sau cập nhật là TRUE; ROLLBACK khôi phục FALSE.

### Bài 3. SELECT xem trước cả giá trị mới theo CASE

**Đề bài:** với đơn NEW, ghi chú mới là UU_TIEN nếu từ 200000 trở lên, còn lại THUONG.

~~~sql
SELECT
    id,
    tong_tien,
    ghi_chu AS ghi_chu_cu,
    CASE WHEN tong_tien >= 200000
         THEN 'UU_TIEN'
         ELSE 'THUONG'
    END AS ghi_chu_moi
FROM pv_don_hang
WHERE trang_thai = 'NEW'
ORDER BY id;
~~~

**Đáp án:** 103 và 108 được UU_TIEN; 101, 105, 111 được THUONG.

### Bài 4. Đếm đúng các hàng của bảng đích khi JOIN

~~~sql
SELECT
    COUNT(*) AS so_dong_join,
    COUNT(DISTINCT dh.id) AS so_don
FROM pv_don_hang AS dh
JOIN pv_chi_tiet_don AS ct
    ON ct.don_hang_id = dh.id
WHERE dh.id IN (101, 103);
~~~

**Đáp án:** 4 dòng JOIN nhưng chỉ 2 đơn mục tiêu.

### Bài 5. UPDATE theo ngưỡng của khu vực

**Đề bài:** viết SELECT xem trước cho các đơn NEW đạt ngưỡng trong bảng chính sách.

~~~sql
SELECT
    dh.id,
    dh.tong_tien,
    kh.khu_vuc,
    cs.nguong_uu_tien
FROM pv_don_hang AS dh
JOIN pv_khach_hang AS kh
    ON kh.id = dh.khach_hang_id
JOIN pv_chinh_sach_vung AS cs
    ON cs.khu_vuc = kh.khu_vuc
WHERE dh.trang_thai = 'NEW'
  AND dh.tong_tien >= cs.nguong_uu_tien
ORDER BY dh.id;
~~~

**Đáp án:** 101, 103, 105, 108. Đơn 111 không đạt ngưỡng NAM.

### Bài 6. Tìm khách có thể xóa mà không mất đơn

~~~sql
SELECT kh.id, kh.ho_ten
FROM pv_khach_hang AS kh
WHERE kh.trang_thai = 'INACTIVE'
  AND NOT EXISTS (
      SELECT 1
      FROM pv_don_hang AS dh
      WHERE dh.khach_hang_id = kh.id
  )
ORDER BY kh.id;
~~~

**Đáp án:** chỉ có Minh (ID 7). Dũng và Lan vẫn có đơn nên không thuộc tập.

### Bài 7. DELETE khách không có đơn trong transaction

~~~sql
BEGIN;

DELETE FROM pv_khach_hang AS kh
WHERE kh.trang_thai = 'INACTIVE'
  AND NOT EXISTS (
      SELECT 1
      FROM pv_don_hang AS dh
      WHERE dh.khach_hang_id = kh.id
  )
RETURNING kh.id, kh.ho_ten;

ROLLBACK;
~~~

**Đáp án:** RETURNING trả Minh, sau ROLLBACK Minh vẫn tồn tại.

### Bài 8. Xem trước đơn CANCELLED cũ

~~~sql
SELECT id, ngay_dat, trang_thai
FROM pv_don_hang
WHERE trang_thai = 'CANCELLED'
  AND ngay_dat < DATE '2026-10-01'
ORDER BY id;
~~~

**Đáp án:** 104, 106, 110. Đơn 109 cũng CANCELLED nhưng ở 11/10, không thuộc tập.

### Bài 9. Vì sao không xóa trực tiếp ba đơn cũ?

**Đề bài:** ba đơn 104, 106, 110 có dòng chi tiết. Schema dùng FK không CASCADE. Xóa trực tiếp có điều gì xảy ra?

**Đáp án:** PostgreSQL từ chối xóa cha khi còn con tham chiếu. Cần kiểm tra và quyết định chính sách xóa: xóa dòng con trước rồi xóa cha trong transaction khi nghiệp vụ cho phép, hoặc lưu trữ/soft delete. Không tự động gỡ ràng buộc FK để xóa cho nhanh.

### Bài 10. Xem trước các dòng con cần xóa

~~~sql
SELECT
    ct.id AS dong_don_id,
    ct.don_hang_id,
    dh.ngay_dat
FROM pv_chi_tiet_don AS ct
JOIN pv_don_hang AS dh
    ON dh.id = ct.don_hang_id
WHERE dh.trang_thai = 'CANCELLED'
  AND dh.ngay_dat < DATE '2026-10-01'
ORDER BY ct.id;
~~~

**Đáp án:** dòng 1006 của đơn 104, dòng 1008 của đơn 106, dòng 1012 của đơn 110.

### Bài 11. Tìm lỗi AND/OR

**Đề bài:** câu SELECT sau chọn những ID nào?

~~~sql
SELECT id
FROM pv_don_hang
WHERE trang_thai = 'CANCELLED'
  AND ngay_dat < DATE '2026-10-01'
  OR khach_hang_id = 4
ORDER BY id;
~~~

**Đáp án:** **104, 106, 107, 110**. Đơn 107 là PAID nhưng thuộc khách 4 nên được thêm bởi nhánh OR. Nếu chỉ muốn đơn CANCELLED cũ của khách 4, đổi OR thành AND và chỉ còn 106.

### Bài 12. Tìm các đơn có ghi chú NULL

~~~sql
SELECT id, ghi_chu
FROM pv_don_hang
WHERE ghi_chu IS NULL
ORDER BY id;
~~~

**Đáp án:** có 11 đơn nếu chưa chạy UPDATE có COMMIT. `ghi_chu = NULL` không phải điều kiện tương đương.

### Bài 13. Xem trước đơn có tổng số lượng ít nhất 3

~~~sql
WITH tong_so_luong AS (
    SELECT don_hang_id, SUM(so_luong) AS so_luong
    FROM pv_chi_tiet_don
    GROUP BY don_hang_id
)
SELECT dh.id, sl.so_luong
FROM pv_don_hang AS dh
JOIN tong_so_luong AS sl
    ON sl.don_hang_id = dh.id
WHERE dh.trang_thai = 'NEW'
  AND sl.so_luong >= 3
ORDER BY dh.id;
~~~

**Đáp án:** 101 có tổng số lượng 3, 103 có tổng số lượng 4.

### Bài 14. Vì sao SELECT LIMIT 2 không bảo vệ UPDATE?

**Đề bài:** SELECT những đơn NEW với LIMIT 2 rồi chạy UPDATE WHERE trang_thai = 'NEW'. UPDATE có tác động đúng hai đơn không?

**Đáp án:** không. Với tập dữ liệu gốc, WHERE này chọn **5 đơn NEW** (101, 103, 105, 108, 111). LIMIT trong SELECT chỉ giới hạn phần hiển thị. Nếu chỉ muốn đúng hai ID được duyệt, phải đưa chính danh sách ID hoặc cách chọn mục tiêu tương ứng vào DML.

### Bài 15. So tập khóa thay vì chỉ COUNT

**Đề bài:** SELECT tiền kiểm cho `{101, 103, 108}`; RETURNING sau UPDATE cho `{101, 105, 108}`. Có thể COMMIT vì cùng ba hàng không?

**Đáp án:** không. Hai tập có cùng số lượng nhưng khác ID 103 và 105; đó là sai tập mục tiêu. Cần rollback hoặc điều tra và duyệt lại theo chính sách.

### Bài 16. WHERE trước và sau phải giữ cùng điều kiện

**Đề bài:** SELECT xem trước dùng:

~~~sql
WHERE trang_thai = 'NEW'
  AND ngay_dat < DATE '2026-10-05'
  AND da_thong_bao = FALSE
~~~

nhưng UPDATE chỉ dùng:

~~~sql
WHERE trang_thai = 'NEW'
~~~

**Đáp án:** UPDATE sẽ mở rộng tập từ 3 đơn thành 5 đơn trong dữ liệu gốc. Cần sử dụng cùng predicate, kiểm tra chính sách mới và dùng RETURNING để đối chiếu.

### Bài 17. Khách có đơn PAID bằng EXISTS

~~~sql
SELECT kh.id, kh.ho_ten
FROM pv_khach_hang AS kh
WHERE EXISTS (
    SELECT 1
    FROM pv_don_hang AS dh
    WHERE dh.khach_hang_id = kh.id
      AND dh.trang_thai = 'PAID'
)
ORDER BY kh.id;
~~~

**Đáp án:** An và Dũng. `EXISTS` không làm lặp khách vì số đơn liên quan.

### Bài 18. Bài tình huống tổng hợp

**Yêu cầu:** trước khi xóa đơn CANCELLED cũ, nhóm vận hành phải trả lời:

- Xóa bao nhiêu đơn?
- Những ID nào?
- Có bao nhiêu dòng chi tiết liên quan?
- Có cần xóa con trước không?
- Nếu kết quả lúc chạy khác lúc duyệt phải làm gì?

**Lời giải:** SELECT đơn cha với WHERE trạng thái CANCELLED và ngày trước 01/10 → **3 đơn: 104, 106, 110**. JOIN chi tiết, đếm theo `ct.id` → **3 dòng con: 1006, 1008, 1012**. FK không CASCADE nên phải có chính sách xóa con trước cha hoặc không xóa vật lý. Thực hiện trong transaction, kiểm tra RETURNING/tập ID và rollback nếu dữ liệu thay đổi ngoài dự kiến; không tự ý commit vì chỉ đếm bằng nhau.

## 28. Checklist trước khi thực hiện UPDATE/DELETE

Khi chuẩn bị chạy câu DML có khả năng tác động nhiều hàng, bạn nên xác định:

1. **Đúng database, schema và môi trường chưa?** Không được nhầm bản thử nghiệm với production.
2. **Đúng bảng mục tiêu chưa?** Với JOIN nhiều bảng, xác định bảng thực sự bị UPDATE/DELETE.
3. **WHERE có hiện diện và đúng ý nghĩa?** Nhất là AND/OR, NULL, dấu ngoặc và phạm vi ngày.
4. **SELECT tiền kiểm dùng cùng predicate chưa?** Không được chỉ nhìn một query gần giống.
5. **Đã liệt kê khóa chính chưa?** Đếm số hàng thôi chưa đủ.
6. **Đã xem các cột nghiệp vụ quan trọng chưa?** Trạng thái, khách hàng, thời gian và giá trị.
7. **Với UPDATE, đã tính cột giá trị mới dự kiến chưa?** Đặc biệt với CASE và biểu thức toán học.
8. **Với JOIN, đã phân biệt số dòng JOIN và số hàng mục tiêu chưa?**
9. **Mỗi hàng đích có nguồn dữ liệu cập nhật duy nhất chưa?** Tránh UPDATE FROM có nhiều match.
10. **Với DELETE, đã xem FK, cascade và bảng con chưa?**
11. **SELECT có LIMIT khiến mình chỉ nhìn một phần không?** Đếm toàn tập trước.
12. **Có rủi ro thay đổi đồng thời giữa xem trước và ghi không?**
13. **Có cần cố định danh sách ID đã duyệt hoặc dùng khóa hàng không?**
14. **Đã chuẩn bị transaction, RETURNING, chính sách COMMIT/ROLLBACK chưa?**
15. **Nếu số hàng hoặc tập ID thực tế khác kỳ vọng, hệ thống có dừng được không?**
16. **Có phân quyền và lưu audit phù hợp không?** FK không thay thế bảo mật.
17. **Có thể cần xóa mềm thay vì xóa vật lý không?**
18. **Nếu dùng DBMS khác PostgreSQL, đã điều chỉnh cú pháp DML và kiểm tra driver chưa?**

## 29. Tổng kết

**Xem trước tập hàng mục tiêu bằng SELECT tương ứng** là một thao tác đơn giản nhưng có tác dụng rất lớn đối với độ an toàn khi cập nhật và xóa dữ liệu.

- Với **UPDATE**, hãy SELECT cùng WHERE để xem **ID, giá trị cũ và giá trị mới dự kiến**.
- Với **DELETE**, hãy SELECT cùng điều kiện để xem **những khóa sẽ mất**, sau đó kiểm tra **khóa ngoại, dòng con và khả năng xóa dây chuyền**.
- Với **UPDATE FROM/DELETE USING**, phải giữ đúng quan hệ JOIN và xem **khóa của chính bảng mục tiêu**, không nhầm số dòng JOIN với số bản ghi bị thay đổi.
- Với điều kiện phức tạp, sử dụng **EXISTS, bảng dẫn xuất hoặc CTE** để biểu diễn tập hàng rõ ràng, nhưng không để SELECT và DML khác predicate.
- **COUNT đúng chưa đủ**: hai tập ID có thể cùng số lượng nhưng khác nhau. Khi cần tính chính xác cao, đối chiếu danh sách khóa với kết quả RETURNING.
- Một SELECT trước UPDATE/DELETE **không tự cố định dữ liệu** trong môi trường đồng thời. Với yêu cầu nghiêm ngặt, phải có chiến lược transaction, khóa, kiểm tra lại và/hoặc danh sách ID đã được duyệt.
- `BEGIN` và `ROLLBACK` giúp thực hành và kiểm soát thao tác ghi, nhưng không thay thế việc quan sát trước bằng SELECT và phê duyệt đúng nghiệp vụ.

Hãy xây dựng thói quen **SELECT xem trước → kiểm tra khóa và số hàng → xác nhận điều kiện → UPDATE/DELETE trong transaction → đối chiếu RETURNING → COMMIT hoặc ROLLBACK**. Khi những bước này trở thành quy trình mặc định, các thao tác cập nhật và xóa dữ liệu sẽ minh bạch, dễ kiểm soát và ít rủi ro hơn.
