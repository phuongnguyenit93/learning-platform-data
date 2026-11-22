# Cập nhật hoặc xóa theo lô với thứ tự và điều kiện tiếp nối trong SQL

Khi dữ liệu chỉ có vài chục hàng, một câu `UPDATE` hoặc `DELETE` có thể hoàn thành rất nhanh. Nhưng với bảng hàng triệu hoặc hàng tỷ dòng, việc sửa hoặc xóa tất cả hàng đủ điều kiện trong **một giao dịch khổng lồ** có thể tạo ra nhiều vấn đề: giữ khóa quá lâu, tạo lượng log/WAL lớn, tăng độ trễ của truy vấn khác, gây áp lực lên replication, phát sinh deadlock hoặc làm khó việc dừng và tiếp tục công việc.

Giải pháp thường dùng là **xử lý theo lô** (*batched UPDATE/DELETE*): mỗi lần chọn một số lượng hàng có giới hạn, thay đổi đúng những hàng ấy, kết thúc giao dịch, sau đó tiếp tục với những hàng còn lại. Tuy nhiên, chia thành lô không chỉ là thêm `LIMIT 1000`. Muốn kết quả đúng, ta phải xác định **thứ tự lựa chọn**, **điều kiện tiếp nối**, **cơ chế xử lý giao dịch đồng thời** và **điều kiện dừng**.

Một ví dụ:

~~~text
Bảng có 8 yêu cầu cần xử lý
  Lô 1: nhận tối đa 3 yêu cầu chưa xử lý
  Lô 2: nhận tối đa 3 yêu cầu tiếp theo
  Lô 3: nhận 2 yêu cầu còn lại
  Kết thúc: không còn yêu cầu thỏa điều kiện
~~~

Với bài toán khác, cần dọn nhật ký cũ:

~~~text
Điều kiện: xóa bản ghi trước 01/10/2026 và không bị giữ để kiểm toán
  Lô 1: xóa tối đa 3 bản ghi cũ nhất
  Lô 2: xóa tối đa 3 bản ghi cũ nhất còn lại
  ...
  Kết thúc: không còn bản ghi hợp lệ để xóa
~~~

Bài này thuộc chương **Cập nhật và xóa** của Database SQL. Ta sẽ thực hành chủ yếu trên **PostgreSQL**, đồng thời giải thích mẫu `UPDATE ... ORDER BY ... LIMIT` ở MySQL, `TOP` và `OUTPUT` ở SQL Server, phương án `ROWID`/row limiting trên Oracle, cùng một số khác biệt của SQLite. Phần quan trọng nhất không phải ghi nhớ một câu lệnh duy nhất mà là xây dựng quy trình **không bỏ sót, không xử lý trùng ngoài ý muốn, không khóa dữ liệu quá lâu và có thể khôi phục khi gặp lỗi**.

## 1. “Theo lô” nghĩa là gì?

Trong bài này, **một lô** là tập tối đa `N` hàng được lựa chọn cho **một lượt xử lý**. Mỗi lượt thường gồm:

1. Xác định tập hàng còn đủ điều kiện;
2. Chọn **tối đa `N` hàng** theo tiêu chí rõ ràng;
3. `UPDATE` hoặc `DELETE` đúng tập hàng được chọn;
4. Ghi nhận số hàng thực sự bị tác động và dữ liệu cần tiếp nối;
5. `COMMIT` hoặc `ROLLBACK` lượt hiện tại;
6. Tiếp tục nếu chưa đạt điều kiện dừng.

Một hình dung:

~~~mermaid
flowchart TD
    A["Bắt đầu: chốt phạm vi và điều kiện"] --> B["Chọn tối đa N hàng\ncó thứ tự ổn định"]
    B --> C["UPDATE / DELETE\ncùng giao dịch"]
    C --> D{"Lượt này thành công?"}
    D -->|"Không"| E["ROLLBACK, ghi lỗi,\nretry theo chính sách"]
    D -->|"Có"| F["COMMIT và ghi tiến độ"]
    F --> G{"Còn việc phải xử lý?"}
    G -->|"Có"| B
    G -->|"Không"| H["Kết thúc và đối soát"]
    E --> B
~~~

**Cần phân biệt:**

- `LIMIT`/`TOP` giới hạn **số hàng ứng viên hoặc số hàng bị tác động**, tùy cú pháp của DBMS.
- `ORDER BY` ở bước chọn xác định **ưu tiên hàng nào được đưa vào lô**.
- `WHERE` định nghĩa **hàng nào còn hợp lệ để thao tác**.
- **Điều kiện tiếp nối** quyết định sau một lượt có nên chạy tiếp, cần dùng con trỏ nào, và khi nào coi là xong.

Không có một cú pháp `UPDATE ... LIMIT ... ORDER BY ...` chung chạy nguyên văn trên mọi DBMS. Ta cần hiểu quy tắc rồi mới áp dụng cú pháp đúng hệ quản trị.

## 2. Vì sao không nên mặc định chạy một UPDATE/DELETE cực lớn?

Giả sử bảng có 20 triệu bản ghi nhật ký đã hết hạn:

~~~sql
-- Chỉ minh họa yêu cầu, KHÔNG chạy trực tiếp trên dữ liệu thật:
DELETE FROM nhat_ky
WHERE xay_ra_luc < TIMESTAMPTZ '2026-10-01 00:00:00+07';
~~~

Trong một số hệ thống, câu lệnh đơn có thể tạo ra:

| Vấn đề | Biểu hiện |
| --- | --- |
| Giao dịch dài | Khóa và tài nguyên giao dịch bị giữ lâu |
| Log/WAL lớn | Đĩa, replication hoặc redo/undo chịu tải cao |
| Tranh chấp với nghiệp vụ trực tuyến | INSERT/UPDATE khác bị chờ hoặc gặp deadlock |
| Khó tạm dừng | Khi câu lệnh đang chạy, không có điểm nghỉ sau từng lô |
| Rollback lớn | Nếu phát hiện lỗi muộn, việc hoàn nguyên có thể rất tốn kém |
| Giới hạn vận hành | Kéo dài maintenance window, tăng tải trên replica |

Chia lô giúp tạo **các điểm COMMIT nhỏ** và kiểm soát nhịp xử lý, nhưng đi kèm những đánh đổi:

- Nhiều lệnh và nhiều commit có chi phí riêng.
- Mỗi lô có thể nhìn thấy **trạng thái dữ liệu khác nhau** dưới mức cô lập như `READ COMMITTED`.
- Các hàng đang bị session khác khóa có thể bị chờ hoặc bị bỏ qua tạm thời.
- Nếu tiến độ lưu không đúng hoặc truy vấn không có thứ tự ổn định, có thể bỏ sót hoặc xử lý lại hàng.

Do đó, “chia lô” là một **chiến lược vận hành và tính đúng đắn**, không tự động là bảo đảm hiệu năng tốt hơn cho mọi bảng.

## 3. Bộ dữ liệu thực hành PostgreSQL

Ta dùng hai bảng tạm: một bảng yêu cầu cần **cập nhật trạng thái theo lô**, một bảng nhật ký cần **xóa theo lô**. Các bảng `TEMP` chỉ tồn tại trong phiên PostgreSQL hiện tại.

### 3.1. Hàng đợi yêu cầu

~~~sql
CREATE TEMP TABLE yeu_cau_lo (
    id BIGINT PRIMARY KEY,
    to_chuc_id INTEGER NOT NULL,
    trang_thai TEXT NOT NULL
        CHECK (trang_thai IN (
            'CHO_XU_LY', 'DANG_XU_LY', 'HOAN_TAT', 'DA_HUY'
        )),
    muc_uu_tien INTEGER NOT NULL
        CHECK (muc_uu_tien BETWEEN 1 AND 5),
    tao_luc TIMESTAMPTZ NOT NULL,
    nhan_luc TIMESTAMPTZ,
    so_lan_nhan INTEGER NOT NULL DEFAULT 0
        CHECK (so_lan_nhan >= 0)
);

INSERT INTO yeu_cau_lo
    (id, to_chuc_id, trang_thai, muc_uu_tien, tao_luc)
VALUES
    (101, 10, 'CHO_XU_LY', 3, '2026-10-01 08:00:00+07'),
    (102, 10, 'CHO_XU_LY', 2, '2026-10-01 08:00:00+07'),
    (103, 10, 'CHO_XU_LY', 3, '2026-10-01 09:00:00+07'),
    (104, 10, 'HOAN_TAT',   5, '2026-10-01 07:00:00+07'),
    (105, 10, 'CHO_XU_LY', 1, '2026-10-02 08:00:00+07'),
    (106, 20, 'CHO_XU_LY', 4, '2026-10-01 08:00:00+07'),
    (107, 20, 'CHO_XU_LY', 3, '2026-10-02 08:00:00+07'),
    (108, 10, 'CHO_XU_LY', 3, '2026-10-01 10:00:00+07'),
    (109, 10, 'CHO_XU_LY', 2, '2026-10-02 09:00:00+07'),
    (110, 10, 'DA_HUY',    5, '2026-10-01 06:00:00+07');
~~~

Có **10 hàng**. Trong tổ chức `10`, **6 yêu cầu có trạng thái `CHO_XU_LY`**: 101, 102, 103, 105, 108 và 109. Các mã 104 và 110 không còn trong hàng chờ; 106 và 107 thuộc tổ chức 20. Trong ví dụ, danh sách ID cụ thể này là nguồn đối chiếu của các phép cập nhật theo lô.

Các cột:

- `id`: khóa chính duy nhất và là **tie-breaker** khi có cùng thời điểm.
- `to_chuc_id`: giữ phạm vi thao tác đúng tổ chức.
- `trang_thai`: điều kiện để biết yêu cầu **còn cần nhận** hay không.
- `muc_uu_tien`: số càng lớn càng ưu tiên.
- `tao_luc`: thời điểm tạo; giúp xử lý hàng chờ lâu trước.
- `nhan_luc` và `so_lan_nhan`: thông tin theo dõi lượt nhận.

### 3.2. Nhật ký cần lưu giữ hoặc xóa

~~~sql
CREATE TEMP TABLE nhat_ky_lo (
    id BIGINT PRIMARY KEY,
    to_chuc_id INTEGER NOT NULL,
    xay_ra_luc TIMESTAMPTZ NOT NULL,
    loai_su_kien TEXT NOT NULL,
    giu_lai BOOLEAN NOT NULL DEFAULT FALSE
);

INSERT INTO nhat_ky_lo
    (id, to_chuc_id, xay_ra_luc, loai_su_kien, giu_lai)
VALUES
    (201, 10, '2026-09-01 08:00:00+07', 'LOGIN', FALSE),
    (202, 10, '2026-09-02 08:00:00+07', 'LOGIN', FALSE),
    (203, 10, '2026-09-02 08:00:00+07', 'AUDIT', TRUE),
    (204, 10, '2026-09-03 08:00:00+07', 'LOGIN', FALSE),
    (205, 10, '2026-09-04 08:00:00+07', 'LOGIN', FALSE),
    (206, 10, '2026-09-05 08:00:00+07', 'LOGIN', FALSE),
    (207, 10, '2026-10-03 08:00:00+07', 'LOGIN', FALSE),
    (208, 20, '2026-09-01 08:00:00+07', 'LOGIN', FALSE),
    (209, 20, '2026-09-02 08:00:00+07', 'LOGIN', FALSE),
    (210, 10, '2026-09-06 08:00:00+07', 'LOGIN', FALSE);
~~~

Giả sử chính sách lưu giữ yêu cầu:

> Chỉ xóa nhật ký của tổ chức 10 có `xay_ra_luc < 2026-10-01 00:00:00+07` **và** `giu_lai = FALSE`.

Các ID đủ điều kiện là **201, 202, 204, 205, 206, 210** (**6 hàng**). ID 203 bị giữ để kiểm toán, ID 207 chưa quá hạn, còn 208–209 thuộc tổ chức khác.

**Đây chỉ là dữ liệu mô phỏng.** Khi xóa dữ liệu thật, phải có chính sách retention hợp lệ, kiểm tra quyền, yêu cầu pháp lý và sao lưu/khôi phục. Không dùng câu lệnh minh họa để xóa tùy ý bảng sản xuất.

### 3.3. Xem dữ liệu và số hàng trước khi xử lý

~~~sql
SELECT id, to_chuc_id, trang_thai, muc_uu_tien, tao_luc
FROM yeu_cau_lo
ORDER BY to_chuc_id, muc_uu_tien DESC, tao_luc, id;

SELECT id, to_chuc_id, xay_ra_luc, giu_lai
FROM nhat_ky_lo
ORDER BY to_chuc_id, xay_ra_luc, id;

SELECT COUNT(*) AS so_nhat_ky_du_dieu_kien
FROM nhat_ky_lo
WHERE to_chuc_id = 10
  AND xay_ra_luc < TIMESTAMPTZ '2026-10-01 00:00:00+07'
  AND giu_lai = FALSE;
~~~

Kết quả câu `COUNT(*)` cuối trên dữ liệu ban đầu là **6**.

## 4. Phải xác định thứ tự chọn lô

Một câu SQL có `WHERE` chỉ định **tập hàng được phép xử lý**. Nếu cần xử lý các hàng “cũ nhất trước” hoặc “ưu tiên cao nhất trước”, ta phải định nghĩa thêm **thứ tự chọn ứng viên**.

### 4.1. Thứ tự có ý nghĩa nghiệp vụ

Ví dụ chọn hai yêu cầu ưu tiên nhất của tổ chức 10:

~~~sql
SELECT id, muc_uu_tien, tao_luc
FROM yeu_cau_lo
WHERE to_chuc_id = 10
  AND trang_thai = 'CHO_XU_LY'
ORDER BY muc_uu_tien DESC, tao_luc ASC, id ASC
LIMIT 2;
~~~

Trên dữ liệu mẫu, hai ứng viên là **101 và 103**:

- Cả hai có mức ưu tiên 3;
- 101 tạo lúc 08:00 và 103 lúc 09:00;
- Mức ưu tiên 2 và 1 được xử lý sau nhóm ưu tiên 3.

Nếu bỏ `id`, hai hàng cùng ưu tiên và cùng `tao_luc` có thể đồng hạng. Một **tie-breaker duy nhất** giúp thứ tự trở nên ổn định và thích hợp làm con trỏ tiếp nối.

### 4.2. Thứ tự chọn không phải thứ tự cập nhật vật lý

Đây là khác biệt cốt lõi:

- `ORDER BY ... LIMIT` ở **truy vấn chọn lô** quyết định *những ID nào* được chọn.
- Khi `UPDATE`/`DELETE` chạy, DBMS **không nhất thiết tác động từng hàng theo thứ tự SELECT**.
- Các hàng được trả từ `RETURNING`/`OUTPUT` **không được mặc định bảo đảm** theo thứ tự chọn.

Vì vậy, nếu muốn hiển thị danh sách ID theo thứ tự, hãy **sắp xếp result set cuối**; nếu muốn thao tác theo một thứ tự nghiêm ngặt từng hàng, phải xác định cơ chế giao dịch và điều phối phù hợp, không suy từ `ORDER BY` trong subquery.

### 4.3. Thứ tự ổn định phụ thuộc dữ liệu nguồn

Đối với việc tiếp nối theo khóa:

~~~sql
ORDER BY tao_luc ASC, id ASC
~~~

`id` phải định danh duy nhất, còn `tao_luc` nên được xem là **bất biến trong suốt lượt quét**. Nếu có tác nhân khác sửa `tao_luc` giữa các lô, một hàng có thể di chuyển qua ranh giới con trỏ và bị bỏ sót hoặc xuất hiện lại.

Với hàng đợi ưu tiên, `muc_uu_tien` có thể thay đổi trong vận hành. Do đó con trỏ dài hạn dựa trên `(muc_uu_tien, tao_luc, id)` đòi hỏi chính sách riêng về thay đổi ưu tiên; không thể mặc định cách này tương đương việc luôn chọn những hàng ưu tiên cao nhất còn lại.

## 5. PostgreSQL không có UPDATE ... LIMIT đơn giản

PostgreSQL không hỗ trợ trực tiếp kiểu câu:

~~~sql
-- Không phải cú pháp PostgreSQL hợp lệ:
-- UPDATE yeu_cau_lo
-- SET trang_thai = 'DANG_XU_LY'
-- WHERE trang_thai = 'CHO_XU_LY'
-- ORDER BY id
-- LIMIT 2;
~~~

Thay vào đó, thông thường **chọn ID trong CTE/subquery**, rồi `UPDATE` những ID đó.

### 5.1. Mẫu UPDATE theo lô qua CTE

~~~sql
BEGIN;

WITH ung_vien AS (
    SELECT id
    FROM yeu_cau_lo
    WHERE to_chuc_id = 10
      AND trang_thai = 'CHO_XU_LY'
    ORDER BY muc_uu_tien DESC, tao_luc, id
    LIMIT 2
    FOR UPDATE SKIP LOCKED
)
UPDATE yeu_cau_lo AS y
SET trang_thai = 'DANG_XU_LY',
    nhan_luc = CURRENT_TIMESTAMP,
    so_lan_nhan = y.so_lan_nhan + 1
FROM ung_vien AS u
WHERE y.id = u.id
RETURNING
    y.id,
    y.to_chuc_id,
    y.trang_thai,
    y.so_lan_nhan;

ROLLBACK;
~~~

Trong trạng thái **không có worker khác giữ khóa**, câu trên nhận tối đa **2 yêu cầu**, tương ứng ID **101, 103**. `ROLLBACK` hủy thay đổi để bạn có thể chạy lại ví dụ mà không phải tạo lại bảng.

Để thực sự xử lý lô, ứng dụng phải `COMMIT` thay vì `ROLLBACK` sau khi kiểm tra và hoàn thành công việc giao dịch cần thiết.

Phân tích:

1. CTE `ung_vien` chọn **tối đa 2 hàng** còn `CHO_XU_LY`, thuộc tổ chức 10.
2. `ORDER BY` xác định ưu tiên chọn.
3. `FOR UPDATE` yêu cầu khóa những hàng ứng viên.
4. `SKIP LOCKED` bỏ qua những hàng đang bị transaction khác khóa thay vì chờ chúng (theo quy tắc PostgreSQL).
5. `UPDATE ... FROM ung_vien` chỉ đổi hàng có ID được chọn.
6. `RETURNING` cho biết **hàng thực sự được cập nhật**, không phải toàn bộ bảng.

Đây là mẫu **claim hàng đợi** thường gặp. Nhưng nó có những giới hạn vận hành và công bằng sẽ được trình bày ở phần concurrency.

### 5.2. Vì sao phải lặp lại điều kiện theo status?

`WHERE trang_thai = 'CHO_XU_LY'` trong CTE xác định **tập còn phải nhận**. Sau khi UPDATE chuyển thành `DANG_XU_LY`, các hàng ấy **không còn thỏa điều kiện của lô tiếp theo**.

Vì vậy, một vòng lặp **không dùng OFFSET** vẫn có thể đi tiếp an toàn theo trạng thái:

~~~text
Lượt 1: chọn 2 hàng CHO_XU_LY → đổi DANG_XU_LY → COMMIT
Lượt 2: chọn 2 hàng CHO_XU_LY còn lại → đổi DANG_XU_LY → COMMIT
Lượt 3: chọn 2 hàng còn lại → đổi DANG_XU_LY → COMMIT
Lượt 4: không còn hàng CHO_XU_LY → xem xét điều kiện dừng
~~~

Theo dữ liệu ban đầu, tổ chức 10 có **6** yêu cầu chờ, nên nếu không có thay đổi đồng thời và không có lỗi, batch size 2 cần **3 lượt cập nhật**, lượt tiếp theo không còn hàng.

**Lưu ý:** sau khi claim `DANG_XU_LY`, một worker vẫn phải **thực hiện nghiệp vụ** và chuyển tiếp sang `HOAN_TAT` hoặc trạng thái lỗi thích hợp. Ví dụ trên chỉ dạy cách **nhận theo lô**, không phải cơ chế xử lý queue hoàn chỉnh.

### 5.3. Khi không cần SKIP LOCKED

Một job bảo trì có **một worker duy nhất** có thể dùng `FOR UPDATE` thông thường hoặc điều kiện DML được bảo vệ bởi giao dịch. `SKIP LOCKED` hữu ích khi **nhiều worker cần tránh chờ nhau**, nhưng có thể khiến công việc đang bị khóa bị bỏ qua tạm thời và khó xác nhận “đã hết hàng”.

Không thêm `SKIP LOCKED` vào mọi UPDATE/DELETE theo lô theo thói quen.

## 6. PostgreSQL: DELETE theo lô với CTE

Với nhật ký cũ, ta muốn xóa **nhiều nhất 3 hàng** trong một lượt, ưu tiên những hàng có thời điểm cũ nhất:

~~~sql
BEGIN;

WITH can_xoa AS (
    SELECT id
    FROM nhat_ky_lo
    WHERE to_chuc_id = 10
      AND xay_ra_luc < TIMESTAMPTZ '2026-10-01 00:00:00+07'
      AND giu_lai = FALSE
    ORDER BY xay_ra_luc, id
    LIMIT 3
    FOR UPDATE SKIP LOCKED
)
DELETE FROM nhat_ky_lo AS n
USING can_xoa AS x
WHERE n.id = x.id
RETURNING
    n.id,
    n.to_chuc_id,
    n.xay_ra_luc;

ROLLBACK;
~~~

Không có khóa cạnh tranh, ba ID sẽ là **201, 202, 204**. ID **203 không bị xóa** vì `giu_lai = TRUE`. Kết quả `RETURNING` có ba hàng nhưng **không được dựa vào thứ tự hàng output** để tạo con trỏ.

Nếu thay `ROLLBACK` bằng `COMMIT` và chạy lặp lại:

| Lượt | Ứng viên xóa theo `ORDER BY` | Còn đủ điều kiện sau COMMIT |
| ---: | --- | ---: |
| 1 | 201, 202, 204 | 3 |
| 2 | 205, 206, 210 | 0 |
| 3 | Không có | 0 |

**Điều kiện `WHERE` phải được giữ đúng qua mọi lượt.** Nếu vô tình bỏ `to_chuc_id = 10` hoặc `giu_lai = FALSE`, vòng lặp có thể xóa dữ liệu thuộc tổ chức khác hoặc dữ liệu phải được bảo vệ.

### 6.1. DELETE không dùng OFFSET

Một điểm thuận tiện là **hàng đã DELETE sẽ biến mất khỏi tập ứng viên**, nên lượt tiếp theo chỉ cần chọn tiếp **những hàng còn tồn tại và còn thỏa điều kiện**, luôn bắt đầu từ đầu tập đó.

Ví dụ:

~~~sql
WITH can_xoa AS (
    SELECT id
    FROM nhat_ky_lo
    WHERE to_chuc_id = 10
      AND xay_ra_luc < TIMESTAMPTZ '2026-10-01 00:00:00+07'
      AND NOT giu_lai
    ORDER BY xay_ra_luc, id
    LIMIT 3
)
DELETE FROM nhat_ky_lo AS n
USING can_xoa AS x
WHERE n.id = x.id
RETURNING n.id;
~~~

Sau `COMMIT`, chạy lại cùng câu sẽ chọn các ID đủ điều kiện còn lại. Không cần một biến `offset = offset + 3`.

### 6.2. Lựa chọn dùng CTE, IN hay USING

Trong PostgreSQL, hai mẫu thường gặp:

~~~sql
WITH can_xoa AS (
    SELECT id FROM nhat_ky_lo
    WHERE to_chuc_id = 10
    ORDER BY id
    LIMIT 3
)
DELETE FROM nhat_ky_lo
WHERE id IN (SELECT id FROM can_xoa);
~~~

và:

~~~sql
WITH can_xoa AS (
    SELECT id FROM nhat_ky_lo
    WHERE to_chuc_id = 10
    ORDER BY id
    LIMIT 3
)
DELETE FROM nhat_ky_lo AS n
USING can_xoa AS x
WHERE n.id = x.id;
~~~

Hai mẫu **có thể** tác động cùng tập ID trong điều kiện phù hợp. Nếu muốn xử lý đồng thời với nhiều worker, nên xem xét khóa ứng viên `FOR UPDATE SKIP LOCKED` trong CTE, cùng điều kiện xóa và giao dịch thích hợp. Những ví dụ trên cố ý lược bỏ điều kiện retention để minh họa hình dạng cú pháp, **không phải truy vấn nên dùng cho job xóa nhật ký thật**.

## 7. Quy tắc vàng: đừng dùng OFFSET để đi qua tập đang thay đổi

Một lỗi phổ biến:

~~~text
Lô 1: lấy OFFSET 0 LIMIT 2 rồi DELETE
Lô 2: lấy OFFSET 2 LIMIT 2 rồi DELETE
Lô 3: lấy OFFSET 4 LIMIT 2 rồi DELETE
~~~

Giả sử ban đầu có sáu ID:

~~~text
Ban đầu: [1, 2, 3, 4, 5, 6]
Lô 1 xóa: [1, 2]
Còn lại: [3, 4, 5, 6]
Lô 2 OFFSET 2 LIMIT 2 trên tập CÒN LẠI → [5, 6]
Kết quả: [3, 4] bị bỏ qua!
~~~

Trong `UPDATE`, vấn đề tương tự xảy ra nếu việc cập nhật khiến hàng **không còn thỏa điều kiện `WHERE`**. Sau mỗi lượt, tập ứng viên co lại; `OFFSET` ngày càng bỏ qua những hàng chưa xử lý.

**Hai chiến lược thường đúng hơn:**

1. **Lặp theo tập còn đủ điều kiện:** mỗi lượt `WHERE status='CHO_XU_LY' ORDER BY ... LIMIT N`, sau đó đổi status để hàng không còn thuộc tập; hoặc `DELETE` để hàng biến mất.
2. **Keyset/cursor:** giữ khóa sắp xếp cuối đã xử lý và chọn những hàng có khóa **lớn hơn khóa đó** trong lượt sau, với điều kiện thứ tự ổn định.

Hai chiến lược có điều kiện áp dụng khác nhau. Không phải mọi bài toán đều cần cursor, và cursor chỉ an toàn khi việc tiến qua các khóa **không bỏ qua hàng chưa được xử lý có thể xuất hiện về sau**.

## 8. Điều kiện tiếp nối kiểu 1: luôn lấy từ các hàng còn hợp lệ

Đây là hướng tự nhiên khi thao tác của mỗi lượt **làm hàng rời khỏi tập ứng viên**.

Ví dụ:

- `UPDATE` từ `CHO_XU_LY` sang `DANG_XU_LY`;
- `UPDATE da_xu_ly = TRUE` với điều kiện `WHERE da_xu_ly = FALSE`;
- `DELETE` các hàng hết hạn;
- `UPDATE` cột cờ migration từ `chua_chuyen = TRUE` sang `FALSE`.

### 8.1. Pseudocode cho job xóa

~~~text
batchSize = 3
cutoff = mốc thời gian lưu giữ đã được chốt

loop:
    BEGIN transaction
    deletedRows = execute DELETE-batch query với cutoff và batchSize
    COMMIT transaction

    ghi log số hàng đã xóa
    nếu deletedRows == 0:
        xác nhận không còn ứng viên bị khóa/đang chờ theo chính sách
        nếu thực sự đã xong: break
~~~

Đây là **pseudocode điều phối ở ứng dụng**, không phải cú pháp SQL có thể chạy nguyên văn. Trong hệ thống thật, cần bảo đảm phát hiện lỗi, rollback, giới hạn số lần retry, timeout và khả năng dừng an toàn.

### 8.2. Đừng vô tình làm điều kiện luôn đúng

Ví dụ nguy hiểm:

~~~sql
-- Không phải chiến lược tiến tới hoàn thành:
-- UPDATE yeu_cau_lo
-- SET so_lan_nhan = so_lan_nhan + 1
-- WHERE trang_thai = 'CHO_XU_LY'
-- LIMIT ...;
~~~

Nếu chỉ tăng `so_lan_nhan` mà **không đổi trạng thái/đánh dấu tiến độ**, hàng vừa sửa **vẫn thỏa `trang_thai = 'CHO_XU_LY'`** và có thể bị chọn lặp vô hạn.

Mỗi vòng phải có một **bất biến tiến độ**: hàng đã xử lý không còn thỏa điều kiện, hoặc cursor tiến về phía trước trên một khóa ổn định.

### 8.3. Điều kiện dừng dựa vào số hàng thực sự bị tác động

Nếu sau mỗi lượt DELETE:

~~~text
deletedRows = 3 → có thể còn nhiều việc, tiếp tục
deletedRows = 1 → có thể là lô cuối, nhưng nên xác nhận
deletedRows = 0 → có thể đã hết, hoặc toàn bộ ứng viên đang bị khóa/không còn khả dụng
~~~

**Không chỉ dùng `deletedRows < batchSize` như bằng chứng tuyệt đối rằng không còn hàng** trong hệ thống nhiều worker hoặc có `SKIP LOCKED`. Những hàng bị khóa có thể chưa được chọn dù đủ điều kiện. Ngoài ra, trong lúc job chạy, dữ liệu có thể được chèn hoặc trở thành đủ điều kiện.

## 9. Điều kiện tiếp nối kiểu 2: keyset cursor

Keyset pagination dùng **khóa sắp xếp của hàng cuối đã xử lý**, thay vì số lượng hàng cần bỏ qua như `OFFSET`.

Giả sử cần xử lý theo `id` tăng dần:

~~~sql
SELECT id
FROM yeu_cau_lo
WHERE to_chuc_id = 10
  AND id > :last_id
ORDER BY id
LIMIT :batch_size;
~~~

`:last_id` và `:batch_size` là **tham số được ứng dụng bind**. Nếu lô trước kết thúc ở ID 103, lô sau bắt đầu từ `id > 103`, không phải `OFFSET 3`.

### 9.1. Cách dùng keyset đơn giản

~~~text
lastId = 0
loop:
    lấy tối đa N hàng WHERE id > lastId ORDER BY id
    xử lý/ghi đúng những ID được chọn
    nếu không có hàng:
        kết thúc hoặc chờ/retry theo chính sách
    nếu thành công:
        lastId = ID lớn nhất trong lô đã hoàn tất
        lưu checkpoint sau khi đảm bảo tính nhất quán với thao tác ghi
~~~

Ưu điểm: `id > lastId` có thể tận dụng chỉ mục khóa chính và tránh việc **càng về sau phải bỏ qua một OFFSET lớn**.

Điều kiện an toàn:

- `id` không thay đổi;
- Thứ tự là **duy nhất và xác định**;
- Không có hàng chưa xử lý với `id <= lastId` xuất hiện sau do late-arrival, thay đổi điều kiện hoặc bị bỏ qua;
- Checkpoint và thay đổi dữ liệu được quản lý nhất quán;
- Có ranh giới hoặc quy tắc hoàn tất cho dữ liệu đến trong lúc job chạy.

### 9.2. Keyset theo hai cột: thời điểm và ID

Nếu muốn xử lý theo thời gian tạo nhưng nhiều hàng cùng timestamp:

~~~sql
SELECT id, tao_luc
FROM yeu_cau_lo
WHERE to_chuc_id = 10
  AND (tao_luc, id) > (
      :last_tao_luc,
      :last_id
  )
ORDER BY tao_luc, id
LIMIT :batch_size;
~~~

PostgreSQL hỗ trợ **so sánh hàng (row constructor comparison)** theo thứ tự từ trái sang phải. Với khóa `(tao_luc, id)`:

~~~text
Nếu tao_luc > last_tao_luc           → hàng phía sau
Nếu tao_luc = last_tao_luc
   và id > last_id                   → hàng phía sau
Nếu tao_luc < last_tao_luc           → hàng phía trước
~~~

Vì `id` là duy nhất và cả hai cột không `NULL` trong bảng mẫu, cặp khóa tạo **thứ tự toàn phần** phù hợp để tiếp nối.

**Chú ý:** không dùng `(tao_luc, id) > (...)` nguyên xi như một mẫu di động cho mọi DBMS. SQL Server chẳng hạn thường cần viết điều kiện tường minh:

~~~sql
WHERE tao_luc > @last_tao_luc
   OR (tao_luc = @last_tao_luc AND id > @last_id)
~~~

### 9.3. Cursor phải cùng hướng với ORDER BY

Nếu sắp theo `ORDER BY muc_uu_tien DESC, tao_luc ASC, id ASC`, điều kiện tiếp nối **không thể** chỉ là `id > last_id`. Cần biểu thức so sánh từ điển (*lexicographic*) theo đúng **hướng tăng/giảm của từng cột**, và cần đảm bảo `muc_uu_tien` không thay đổi làm hàng di chuyển giữa các lô.

Khi ưu tiên có thể đổi trong lúc xử lý, cách **mỗi lượt lấy hàng hợp lệ ưu tiên cao nhất còn lại** thường phù hợp hơn một cursor di chuyển một chiều qua thứ tự ưu tiên.

## 10. PostgreSQL: UPDATE theo keyset với checkpoint

Giả sử muốn đánh dấu những yêu cầu `CHO_XU_LY` của tổ chức 10 theo **ID tăng dần**; dùng `:last_id` do ứng dụng lưu.

~~~sql
WITH ung_vien AS (
    SELECT id
    FROM yeu_cau_lo
    WHERE to_chuc_id = 10
      AND trang_thai = 'CHO_XU_LY'
      AND id > :last_id
    ORDER BY id
    LIMIT :batch_size
    FOR UPDATE
),
da_cap_nhat AS (
    UPDATE yeu_cau_lo AS y
    SET trang_thai = 'DANG_XU_LY',
        nhan_luc = CURRENT_TIMESTAMP,
        so_lan_nhan = y.so_lan_nhan + 1
    FROM ung_vien AS u
    WHERE y.id = u.id
    RETURNING y.id
)
SELECT id
FROM da_cap_nhat
ORDER BY id;
~~~

`SELECT` cuối **sắp xếp những ID được trả về**. Ứng dụng có thể dùng ID cuối làm checkpoint **sau khi câu lệnh và transaction được xác nhận thành công**.

**Điểm an toàn:** ví dụ dùng `FOR UPDATE` (không `SKIP LOCKED`) để không âm thầm lướt qua một hàng có ID nhỏ hơn nhưng đang bị khóa. Nếu phối hợp cursor một chiều với `SKIP LOCKED`, rất dễ xảy ra:

~~~text
ID 101 đang bị worker khác khóa → SKIP LOCKED bỏ qua
Lô hiện tại lấy 102 và 103 → lưu lastId = 103
ID 101 được mở khóa và vẫn CHO_XU_LY
Lượt sau WHERE id > 103 → sẽ không bao giờ xét lại 101
~~~

Đây là lỗi **bỏ sót do cursor + SKIP LOCKED**. Khi dùng `SKIP LOCKED`, nên áp dụng chiến lược **quét lại các hàng còn đủ điều kiện** hoặc có cơ chế riêng để **đánh dấu/revisit** những khóa bị bỏ qua.

### 10.1. Checkpoint không được tiến trước khi ghi thành công

Nếu ứng dụng ghi `lastId = 103` vào một nơi lưu trữ độc lập **trước khi UPDATE commit**, sau đó transaction bị rollback, lần chạy sau sẽ bỏ qua ID 101–103 dù chúng vẫn chưa được xử lý.

Một cơ chế mạnh hơn là:

- Lưu checkpoint và cập nhật dữ liệu trong **cùng transaction** nếu checkpoint nằm ở cùng database; hoặc
- Thiết kế thao tác **idempotent**, cho phép retry và đối soát, khi checkpoint ở hệ khác; hoặc
- Không dùng cursor mà dựa trên **trạng thái còn đủ điều kiện** làm nguồn tiến độ.

### 10.2. Keyset không có nghĩa là snapshot cố định

Trong `READ COMMITTED`, mỗi câu lệnh có thể thấy dữ liệu đã commit mới. Một hàng có khóa nhỏ hơn checkpoint nhưng **được chèn muộn** sẽ không được quét. Nếu cần quét chính xác một tập dữ liệu tại thời điểm bắt đầu, có thể phải chốt **high-water mark**, ghi danh sách công việc hoặc dùng chiến lược snapshot/phân vùng phù hợp.

## 11. Chốt phạm vi bằng cutoff và high-water mark

Một job có thể chạy nhiều phút hoặc nhiều giờ; trong lúc đó hệ thống vẫn tạo bản ghi mới. Nếu cứ xử lý `WHERE tao_luc < CURRENT_TIMESTAMP` ở mỗi lượt, **đường biên trượt về phía trước**, khiến job liên tục nhận thêm việc mới.

Với dọn dữ liệu, nên **chốt một cutoff** lúc bắt đầu:

~~~text
cutoff = 2026-10-01 00:00:00+07
Mọi lô dùng cùng cutoff này
Không tự thay cutoff bằng NOW() mới sau mỗi lượt
~~~

Ví dụ:

~~~sql
SELECT id, xay_ra_luc
FROM nhat_ky_lo
WHERE to_chuc_id = 10
  AND xay_ra_luc < TIMESTAMPTZ '2026-10-01 00:00:00+07'
  AND giu_lai = FALSE
ORDER BY xay_ra_luc, id
LIMIT 3;
~~~

Điều kiện cố định giúp giải thích chính xác một lượt job thuộc **kỳ xử lý nào**.

### 11.1. High-water mark theo khóa

Nếu bảng có một khóa tăng theo một trật tự được bảo đảm và business cần “chỉ xử lý các bản ghi đã tồn tại ở thời điểm bắt đầu”, job có thể chốt **mốc khóa lớn nhất** `high_id`:

~~~sql
-- Chỉ là mẫu xác định mốc theo tập mục tiêu.
SELECT MAX(id) AS high_id
FROM yeu_cau_lo
WHERE to_chuc_id = 10
  AND trang_thai = 'CHO_XU_LY';
~~~

Sau đó các lô thêm `AND id <= :high_id`. Nhưng cần hiểu:

- Một ID tự sinh **không nhất thiết có thứ tự commit**. Transaction có ID nhỏ có thể commit sau transaction có ID lớn.
- Giá trị khóa nhỏ hơn high-water vẫn có thể được ghi nhận muộn trong một số hệ thống.
- Cờ trạng thái có thể thay đổi trong lúc job chạy.

Vì vậy, **high-water theo ID chỉ là ranh giới khóa**, không mặc nhiên là ảnh chụp giao dịch chính xác của toàn bộ tập hàng hiện hữu. Khi cần **tập chính xác tại thời điểm chốt**, phải dùng snapshot/queue manifest/staging table hoặc cơ chế nhất quán tương ứng.

### 11.2. Cutoff thời gian và khóa cursor có vai trò khác

- **Cutoff:** giới hạn miền nghiệp vụ được phép xử lý, ví dụ “cũ hơn 30 ngày”.
- **Cursor:** đánh dấu nơi đã tiến tới theo thứ tự chọn, ví dụ cặp `(xay_ra_luc, id)`.

Một truy vấn có thể cần **cả hai**:

~~~sql
SELECT id, xay_ra_luc
FROM nhat_ky_lo
WHERE to_chuc_id = 10
  AND giu_lai = FALSE
  AND xay_ra_luc < :cutoff
  AND (xay_ra_luc, id) > (:last_time, :last_id)
ORDER BY xay_ra_luc, id
LIMIT :batch_size;
~~~

Muốn cursor đáng tin cậy, `xay_ra_luc` phải ổn định và các hàng bị bỏ qua vì khóa/thay đổi điều kiện cần có cách được xét lại. Với dữ liệu chỉ cần `DELETE`, chiến lược **chọn từ tập còn lại mà không dùng cursor** thường đơn giản hơn.

## 12. Lấy đúng điểm tiếp nối từ kết quả DML

Trong PostgreSQL, `UPDATE ... RETURNING` và `DELETE ... RETURNING` trả các hàng bị tác động. Nhưng **không nên mặc định thứ tự của `RETURNING`**.

Ví dụ:

~~~sql
WITH can_xoa AS (
    SELECT id
    FROM nhat_ky_lo
    WHERE to_chuc_id = 10
      AND NOT giu_lai
      AND xay_ra_luc < TIMESTAMPTZ '2026-10-01 00:00:00+07'
    ORDER BY xay_ra_luc, id
    LIMIT 3
),
da_xoa AS (
    DELETE FROM nhat_ky_lo AS n
    USING can_xoa AS x
    WHERE n.id = x.id
    RETURNING n.id, n.xay_ra_luc
)
SELECT id, xay_ra_luc
FROM da_xoa
ORDER BY xay_ra_luc, id;
~~~

`SELECT` cuối đảm bảo **thứ tự trình bày** của các hàng đã xóa. Nếu dùng keyset, ứng dụng lấy **cặp khóa cuối theo thứ tự đã sắp** để làm cursor, sau khi kết quả DML và giao dịch thành công.

Tuy nhiên, không nên kết hợp cursor với `SKIP LOCKED` mà không có cơ chế revisit như mục 10. Kết quả `RETURNING` cũng có thể rỗng do **không có hàng đủ điều kiện**, do **tranh chấp khóa/skip** hoặc do **điều kiện thay đổi**, nên phải giải thích theo mô hình vận hành cụ thể.

### 12.1. DML RETURNING không chứng minh COMMIT

~~~sql
BEGIN;

DELETE FROM nhat_ky_lo
WHERE id = 201
RETURNING id;

ROLLBACK;
~~~

Câu `DELETE` có thể trả ID **201**, nhưng `ROLLBACK` khôi phục hàng. Nếu một hệ thống bên ngoài đã nhận thông báo “xóa vĩnh viễn ID 201” trước khi transaction hoàn tất, hai hệ thống có thể không còn nhất quán.

Checkpoint bền vững, log kiểm toán và sự kiện gửi ra ngoài phải được thiết kế dựa trên **trạng thái commit**, không chỉ dựa vào việc câu SQL đã sinh một result set.

## 13. Nhiều worker: khóa hàng và SKIP LOCKED

Trong một hệ thống queue, có thể có nhiều tiến trình cùng tìm hàng `CHO_XU_LY`. Nếu cả hai cùng:

~~~sql
SELECT id
FROM yeu_cau_lo
WHERE trang_thai = 'CHO_XU_LY'
ORDER BY id
LIMIT 2;
~~~

rồi **sau đó** UPDATE bằng một câu riêng mà không có giao dịch/khóa/điều kiện cạnh tranh phù hợp, cả hai có thể nhìn thấy cùng các ID và cùng cố nhận việc.

### 13.1. Nhận việc nguyên tử bằng CTE có khóa

Một mẫu PostgreSQL:

~~~sql
WITH can_nhan AS (
    SELECT id
    FROM yeu_cau_lo
    WHERE to_chuc_id = 10
      AND trang_thai = 'CHO_XU_LY'
    ORDER BY muc_uu_tien DESC, tao_luc, id
    LIMIT 2
    FOR UPDATE SKIP LOCKED
)
UPDATE yeu_cau_lo AS y
SET trang_thai = 'DANG_XU_LY',
    nhan_luc = CURRENT_TIMESTAMP,
    so_lan_nhan = y.so_lan_nhan + 1
FROM can_nhan AS c
WHERE y.id = c.id
RETURNING y.id, y.nhan_luc, y.so_lan_nhan;
~~~

Chọn và cập nhật trong **một câu DML** giúp giảm khoảng trống thời gian giữa bước “đã đọc ứng viên” và bước “thực sự đổi trạng thái”.

`SKIP LOCKED` có nghĩa là **không chờ những hàng đang được transaction khác khóa** trong phạm vi cách PostgreSQL áp dụng. Nó **không bảo đảm thứ tự FIFO tuyệt đối**, không khóa toàn bộ các thay đổi schema và không tạo ảnh chụp nhất quán của toàn bộ queue. PostgreSQL cũng có thể vẫn cần lấy khóa ở cấp bảng theo quy tắc của câu lệnh.

### 13.2. Hàng bị khóa có thể bị bỏ qua tạm thời

Giả sử hàng 101 đang bị transaction khác giữ khóa; worker B dùng `SKIP LOCKED` có thể nhận 103 và 108 trước. Sau khi 101 được mở khóa, nó vẫn cần được xử lý ở một lượt sau nếu còn `CHO_XU_LY`.

Điều này phù hợp với queue thiên về **throughput**, nhưng không phù hợp nếu nghiệp vụ đòi **xử lý tuyệt đối đúng thứ tự thời gian** bất chấp worker bị chậm. Thứ tự `ORDER BY` là **thứ tự ưu tiên chọn trong tập có thể khóa**, không phải hợp đồng hoàn tất tác vụ theo thứ tự đó.

### 13.3. Starvation và retry

Một hàng luôn bị khóa hoặc liên tục bị bỏ qua có thể bị **starvation** (chờ lâu). Cần có:

- Job kiểm tra các hàng chờ quá lâu;
- Cơ chế retry sau khi khóa được giải phóng;
- Giới hạn số lần nhận và chính sách thất bại;
- Chỉ tiêu giám sát tuổi của hàng cũ nhất chưa xử lý;
- Cách xử lý worker bị lỗi khi đã đổi trạng thái sang `DANG_XU_LY`.

Không chỉ nhìn `0 hàng RETURNING` trong một lượt có `SKIP LOCKED` rồi tuyên bố **không còn việc**.

### 13.4. Claim và thực hiện tác vụ là hai pha khác nhau

Nếu tác vụ là gửi email, gọi API hoặc chạy phép tính mất vài phút, không nên mặc định giữ transaction/row lock **trong suốt tác vụ bên ngoài database**. Một thiết kế phổ biến:

~~~text
Transaction ngắn:
  Nhận hàng → chuyển DANG_XU_LY → ghi lease/owner/nhan_luc → COMMIT

Thực hiện công việc ngoài transaction:
  Gọi hệ thống khác hoặc xử lý nội dung

Transaction ngắn tiếp:
  Xác nhận kết quả → chuyển HOAN_TAT/THAT_BAI
~~~

Nếu worker crash sau bước claim, hàng có thể **mắc kẹt ở DANG_XU_LY**. Để phục hồi, hệ thống thật có thể dùng **lease hết hạn** (`lease_until`), chủ sở hữu worker, bộ đếm retry và thao tác idempotent. Bảng mẫu chỉ có `nhan_luc` và `so_lan_nhan` để giới thiệu; nó **chưa phải một queue an toàn hoàn chỉnh**.

## 14. Điều kiện dừng khi có thao tác đồng thời

Giả sử một worker chạy dọn dữ liệu, một worker khác giữ khóa những hàng cũ. Lượt của worker thứ nhất với `SKIP LOCKED` có thể trả **0 hàng** ngay cả khi vẫn còn bản ghi đủ điều kiện.

Có ít nhất ba trạng thái:

1. **Thật sự hết việc:** không còn hàng phù hợp với cutoff và chính sách.
2. **Có việc nhưng đang bị khóa:** lô hiện tại bỏ qua chúng.
3. **Có việc xuất hiện sau thời điểm kiểm tra:** một transaction khác vừa commit dữ liệu mới thỏa điều kiện.

Một vòng lặp thực tế nên có điều kiện dừng rõ:

~~~text
Nếu lô trả > 0 hàng:
    COMMIT, ghi tiến độ, tiếp tục

Nếu lô trả 0 hàng:
    không tự động coi là hoàn tất trong mô hình SKIP LOCKED
    kiểm tra lại tập ứng viên/worker đang chạy/cutoff theo chính sách
    nếu còn hàng bị khóa: chờ hoặc lên lịch lượt sau
    nếu không còn việc trong phạm vi đã chốt: kết thúc

Nếu lỗi:
    ROLLBACK, ghi thông tin, retry có giới hạn hoặc chuyển sang xử lý lỗi
~~~

**Không nên chờ vô hạn bằng vòng lặp chạy sát nhau** vì sẽ tạo áp lực không cần thiết. Trong ứng dụng, dùng sleep/backoff, lịch chạy hoặc thông báo hàng đợi phù hợp; việc dùng công cụ lập lịch không nằm trong một câu SQL `UPDATE` đơn.

### 14.1. Đếm lại vẫn có thể bị race

Một câu:

~~~sql
SELECT COUNT(*)
FROM nhat_ky_lo
WHERE to_chuc_id = 10
  AND xay_ra_luc < TIMESTAMPTZ '2026-10-01 00:00:00+07'
  AND giu_lai = FALSE;
~~~

cho biết số hàng phù hợp **theo snapshot của lần đọc đó**, không ngăn transaction khác thay đổi dữ liệu ngay sau đó. Nếu cần một kết luận **toàn cục, tuyệt đối** rằng job đã dọn một tập chính xác tại một thời điểm, phải định nghĩa cơ chế đồng bộ, snapshot hoặc đánh dấu phạm vi tiến trình chặt chẽ hơn.

## 15. Giao dịch ngắn và xử lý lỗi

Một batch nên là một **đơn vị giao dịch có thể xác nhận**:

~~~sql
BEGIN;

WITH can_xoa AS (
    SELECT id
    FROM nhat_ky_lo
    WHERE to_chuc_id = 10
      AND xay_ra_luc < TIMESTAMPTZ '2026-10-01 00:00:00+07'
      AND NOT giu_lai
    ORDER BY xay_ra_luc, id
    LIMIT 3
    FOR UPDATE
)
DELETE FROM nhat_ky_lo AS n
USING can_xoa AS c
WHERE n.id = c.id
RETURNING n.id;

-- Trong hệ thống thật: COMMIT nếu mọi điều kiện thành công.
ROLLBACK;
~~~

Trong ví dụ dùng `ROLLBACK` để không phá dữ liệu thực hành. Khi job chạy thật, `COMMIT` một lô rồi mới bắt đầu lô tiếp theo giúp tránh một giao dịch kéo dài qua hàng triệu hàng.

### 15.1. Mỗi lô COMMIT riêng tạo ra trạng thái trung gian

Vì mỗi lô đã commit có thể nhìn thấy bởi session khác, một job nhiều lô **không phải một thao tác nguyên tử trên toàn bộ bảng**. Ví dụ sau hai lô đầu, một phần bản ghi cũ đã xóa, phần còn lại chưa xóa.

Nếu nghiệp vụ yêu cầu **“hoặc tất cả cập nhật thành công, hoặc không có cập nhật nào”**, chia thành nhiều transaction commit riêng **không đáp ứng** yêu cầu nguyên tử đó. Khi ấy cần thiết kế khác như shadow table, chuyển partition, staging/đổi con trỏ phiên bản, hoặc một transaction duy nhất (với chi phí tương ứng).

### 15.2. Deadlock và retry

Các worker có thể giữ khóa theo những thứ tự khác nhau, dẫn đến deadlock. DBMS thường phát hiện và hủy một transaction. Ứng dụng phải:

- Nhận diện lỗi có thể retry;
- `ROLLBACK` transaction thất bại;
- Thực thi lại **toàn bộ batch** theo chính sách, không giả định đã commit một phần;
- Có backoff/giới hạn retry;
- Tránh phát tác động không hoàn nguyên ra hệ khác trước khi commit.

Chọn ứng viên theo **một thứ tự nhất quán** có thể giảm một số tình huống tranh chấp, nhưng không bảo đảm loại bỏ mọi deadlock.

### 15.3. Mức cô lập giao dịch

Ở PostgreSQL `READ COMMITTED`, các câu lệnh trong những transaction khác nhau có thể thấy dữ liệu đã commit mới. Một job theo lô thường **chủ động** chấp nhận việc mỗi batch quan sát trạng thái mới.

`REPEATABLE READ` hoặc `SERIALIZABLE` có những quy tắc snapshot, xung đột và retry riêng; nâng isolation level không tự biến một chương trình có nhiều giao dịch độc lập thành snapshot của toàn bộ job. Cần chọn mức cô lập theo yêu cầu cụ thể và thiết kế cơ chế tiếp nối tương thích.

## 16. UPDATE/DELETE theo lô có điều kiện thay đổi trong lúc chạy

Giả sử job đặt:

~~~sql
WHERE trang_thai = 'CHO_XU_LY'
~~~

Trong lúc job chạy, một tiến trình khác có thể đổi yêu cầu từ `CHO_XU_LY` sang `DA_HUY`. Nếu ứng dụng **chọn ID ở một câu**, sau đó **UPDATE ID ở một câu riêng** mà không có khóa/điều kiện kiểm tra lại, nó có thể ghi đè quyết định hủy.

### 16.1. Recheck điều kiện ở DML khi chọn tách biệt

Một cách phòng vệ:

~~~sql
-- Trường hợp ID đã được lấy từ bước chọn trước,
-- nhưng ứng dụng vẫn cần kiểm tra trạng thái lúc ghi.
UPDATE yeu_cau_lo
SET trang_thai = 'DANG_XU_LY',
    nhan_luc = CURRENT_TIMESTAMP,
    so_lan_nhan = so_lan_nhan + 1
WHERE id = :id_ung_vien
  AND to_chuc_id = 10
  AND trang_thai = 'CHO_XU_LY'
RETURNING id, trang_thai;
~~~

Nếu ID đã bị hủy, câu UPDATE trả **0 hàng** thay vì ghi đè thành `DANG_XU_LY`.

**Lưu ý:** chỉ thêm `WHERE` thôi chưa xử lý mọi race giữa nhiều hàng và nhiều bước. Khi cần claim nguyên tử, nên dùng DML trên tập ứng viên được khóa hoặc cơ chế optimistic concurrency có **version**.

### 16.2. Optimistic locking bằng version

Một thiết kế khác dùng cột phiên bản:

~~~sql
-- Mẫu cho bảng giả định có cot phien_ban:
UPDATE yeu_cau
SET trang_thai = 'DANG_XU_LY',
    phien_ban = phien_ban + 1
WHERE id = :id
  AND phien_ban = :phien_ban_da_doc
  AND trang_thai = 'CHO_XU_LY';
~~~

Nếu số hàng ảnh hưởng bằng 0, dữ liệu có thể đã đổi kể từ lúc đọc; ứng dụng cần reload/giải quyết xung đột, không mù quáng báo thành công. Phương án này hữu ích khi không muốn khóa từ sớm, nhưng cần thiết kế version và retry đúng.

### 16.3. Khi khóa sắp xếp bị sửa

Đối với keyset cursor `(tao_luc, id)`, nếu có cập nhật `tao_luc`:

~~~text
Hàng 150 trước đó ở sau cursor
Trong lúc job chạy, tao_luc bị sửa thành trước cursor
Lượt sau WHERE (tao_luc,id) > last_key sẽ không nhìn thấy hàng 150
~~~

Để tránh, cần cột thứ tự **bất biến**, snapshot/staging tập mục tiêu, hoặc chiến lược quét lại hàng còn đủ điều kiện. Với hàng đợi ưu tiên thay đổi thường xuyên, **quét từ đầu tập chưa nhận** là lựa chọn trực quan hơn.

## 17. MySQL: UPDATE/DELETE một bảng với ORDER BY và LIMIT

MySQL có cú pháp thuận tiện cho thao tác trên **một bảng**:

~~~sql
-- MySQL: UPDATE một bảng
UPDATE yeu_cau
SET trang_thai = 'DANG_XU_LY'
WHERE to_chuc_id = 10
  AND trang_thai = 'CHO_XU_LY'
ORDER BY muc_uu_tien DESC, tao_luc, id
LIMIT 2;
~~~

và:

~~~sql
-- MySQL: DELETE một bảng
DELETE FROM nhat_ky
WHERE to_chuc_id = 10
  AND xay_ra_luc < '2026-10-01 00:00:00'
  AND giu_lai = 0
ORDER BY xay_ra_luc, id
LIMIT 3;
~~~

Trong **single-table UPDATE/DELETE** MySQL, `ORDER BY` và `LIMIT` có ý nghĩa tương ứng với việc giới hạn tập thao tác. Nhưng cần chú ý:

1. **Multi-table UPDATE/DELETE** có cú pháp/giới hạn khác và không hỗ trợ mọi tổ hợp `ORDER BY`/`LIMIT` như single-table DML.
2. Thứ tự ảnh hưởng có ý nghĩa riêng khi cập nhật khóa unique; không lấy đó làm bảo đảm mọi trigger, thao tác ngoài hệ thống hoặc quá trình commit sẽ hoàn tất theo cùng thứ tự nghiệp vụ.
3. Một batch được thực hiện trong transaction; nhiều batch cần điều phối bằng vòng lặp ở ứng dụng hoặc stored procedure.
4. Với `LIMIT`, số hàng khớp/số hàng thực sự thay đổi có thể khác nhau theo cách MySQL và driver báo affected rows.

### 17.1. Một vấn đề khi dựa vào affected rows của UPDATE

Giả sử:

~~~sql
UPDATE yeu_cau
SET trang_thai = 'CHO_XU_LY'
WHERE trang_thai = 'CHO_XU_LY'
ORDER BY id
LIMIT 10;
~~~

Đây là phép **gán cùng giá trị**. Không có tiến độ thực sự; tùy cấu hình/driver, affected-row count có thể biểu thị **matched rows** hoặc **changed rows**. Dù số đếm là 0 hay 10, vòng lặp cũng **không thể coi là đã xử lý xong**.

Hãy bảo đảm mỗi lượt **đổi trạng thái để hàng không còn thỏa WHERE**, hoặc dùng cursor tiến trên khóa ổn định.

### 17.2. MySQL không có RETURNING như PostgreSQL

Trong MySQL 8.x, không mặc định có `UPDATE ... RETURNING id` hoặc `DELETE ... RETURNING id` theo cú pháp PostgreSQL. Nếu cần biết chính xác ID bị tác động để cập nhật checkpoint/audit, có thể cần chọn và khóa ứng viên trước bằng `SELECT ... FOR UPDATE` trong cùng transaction, sau đó DML theo ID và ghi nhận tập ID; phải giữ điều kiện chống race.

MySQL 8 có `SKIP LOCKED` trong các ngữ cảnh khóa phù hợp, nhưng cần đối chiếu mức cô lập, storage engine và cú pháp thực tế. **Không chép nguyên CTE DML PostgreSQL có `RETURNING` vào MySQL.**

## 18. SQL Server: TOP không tự cho thứ tự

SQL Server hỗ trợ `TOP (N)` trong `UPDATE` và `DELETE`, nhưng:

~~~sql
-- SQL Server:
UPDATE TOP (100) dbo.YeuCau
SET TrangThai = N'DANG_XU_LY'
WHERE TrangThai = N'CHO_XU_LY';
~~~

**không bảo đảm** những hàng nào trong tập phù hợp được chọn theo thứ tự mong muốn. Bản thân `TOP` trong DML không đủ để diễn đạt “100 hàng cũ nhất”.

### 18.1. Chọn TOP theo thứ tự trong CTE

Một mẫu T-SQL:

~~~sql
;WITH UngVien AS (
    SELECT TOP (100) Id
    FROM dbo.YeuCau
    WHERE ToChucId = 10
      AND TrangThai = N'CHO_XU_LY'
    ORDER BY TaoLuc ASC, Id ASC
)
UPDATE y
SET TrangThai = N'DANG_XU_LY'
OUTPUT INSERTED.Id, INSERTED.TrangThai
FROM dbo.YeuCau AS y
JOIN UngVien AS u
    ON u.Id = y.Id;
~~~

`ORDER BY` trong CTE cùng `TOP (100)` quyết định **nhóm ID ứng viên**. `OUTPUT` trả các ID thực sự được cập nhật, nhưng **thứ tự các hàng OUTPUT không được bảo đảm**.

Đây là mẫu minh họa **lựa chọn có thứ tự**, chưa phải cơ chế queue đồng thời hoàn chỉnh. Khi nhiều session cùng chọn ứng viên, cần kiểm soát khóa, isolation, kết quả thay đổi và retry, ví dụ xem xét `UPDLOCK`/`READPAST` theo quy tắc SQL Server.

### 18.2. DELETE theo lô và sắp xếp ứng viên

~~~sql
;WITH CanXoa AS (
    SELECT TOP (100) Id
    FROM dbo.NhatKy
    WHERE ToChucId = 10
      AND XayRaLuc < @Cutoff
      AND GiuLai = 0
    ORDER BY XayRaLuc, Id
)
DELETE n
OUTPUT DELETED.Id
FROM dbo.NhatKy AS n
JOIN CanXoa AS c
    ON c.Id = n.Id;
~~~

Thứ tự chọn ID nằm trong `SELECT TOP ... ORDER BY`, không phải trong `DELETE TOP (100)` trực tiếp.

### 18.3. READPAST và UPDLOCK

SQL Server có các lock hints như:

- `UPDLOCK`: yêu cầu kiểu khóa cập nhật trong những ngữ cảnh phù hợp;
- `READPAST`: bỏ qua một số hàng đang bị khóa thay vì chờ, với các giới hạn về isolation/kiểu khóa;
- `ROWLOCK`: gợi ý granularity, **không bảo đảm** mọi khóa luôn là row lock.

Ví dụ hướng thiết kế:

~~~sql
;WITH UngVien AS (
    SELECT TOP (20) Id
    FROM dbo.YeuCau WITH (UPDLOCK, READPAST, ROWLOCK)
    WHERE TrangThai = N'CHO_XU_LY'
    ORDER BY TaoLuc, Id
)
UPDATE y
SET TrangThai = N'DANG_XU_LY'
OUTPUT INSERTED.Id
FROM dbo.YeuCau AS y
JOIN UngVien AS u
    ON u.Id = y.Id;
~~~

**Chỉ dùng những hint này khi hiểu chính xác isolation level và phiên bản SQL Server.** `READPAST` có giới hạn dưới các thiết lập như `READ_COMMITTED_SNAPSHOT` và không đồng nhất hoàn toàn với PostgreSQL `SKIP LOCKED`. Hơn nữa, khi bỏ qua hàng bị khóa thì **không được dùng một cursor một chiều và quên xét lại hàng bị bỏ qua**.

## 19. Oracle: giới hạn ứng viên qua subquery/ROWID

Oracle Database không sử dụng nguyên cú pháp PostgreSQL `DELETE ... USING ... LIMIT N`. Một cách khái quát là **lựa chọn tối đa N ROWID của những hàng đủ điều kiện theo thứ tự**, rồi xóa đúng những ROWID ấy.

Ví dụ Oracle có bảng `NHAT_KY` và biến bind `:cutoff`, `:batch_size`:

~~~sql
DELETE FROM nhat_ky n
WHERE n.ROWID IN (
    SELECT rid
    FROM (
        SELECT ROWID AS rid
        FROM nhat_ky
        WHERE to_chuc_id = 10
          AND xay_ra_luc < :cutoff
          AND giu_lai = 0
        ORDER BY xay_ra_luc, id
    )
    WHERE ROWNUM <= :batch_size
);
~~~

Ở đây:

1. Truy vấn trong cùng `ORDER BY` xác định thứ tự các ROWID ứng viên;
2. `ROWNUM <= :batch_size` đặt ở cấp ngoài để giới hạn sau lựa chọn có thứ tự;
3. Câu `DELETE` xóa những hàng mang ROWID được chọn.

**ROWID** là định danh vị trí hàng Oracle trong ngữ cảnh bảng tương ứng, không phải khóa nghiệp vụ lâu dài để lưu ở hệ thống bên ngoài. Với các trường hợp di chuyển hàng, IOT, view, partition và cấu trúc lưu trữ đặc biệt, cần kiểm tra khả năng áp dụng ROWID cụ thể.

### 19.1. Với UPDATE tương tự

~~~sql
UPDATE yeu_cau y
SET trang_thai = 'DANG_XU_LY'
WHERE y.ROWID IN (
    SELECT rid
    FROM (
        SELECT ROWID AS rid
        FROM yeu_cau
        WHERE to_chuc_id = 10
          AND trang_thai = 'CHO_XU_LY'
        ORDER BY tao_luc, id
    )
    WHERE ROWNUM <= :batch_size
);
~~~

Mẫu này minh họa **giới hạn tập ứng viên**, không phải bảo đảm tranh chấp an toàn khi nhiều worker chạy đồng thời. Đối với xử lý queue Oracle, có thể dùng một cursor `SELECT ... FOR UPDATE SKIP LOCKED` và fetch từng lô trong PL/SQL/app, nhưng phải kiểm tra quy tắc **kết hợp row limiting và FOR UPDATE**: không phải mọi vị trí `FETCH FIRST`, `ROWNUM`, `FOR UPDATE` đều có thể ghép tùy ý.

### 19.2. Oracle và RETURNING

Oracle có `RETURNING ... INTO` với biến PL/SQL hoặc bind output, và các cơ chế bulk trong PL/SQL. Nó không hoạt động giống result set `RETURNING id` của PostgreSQL trong mọi ngữ cảnh.

Đối với job lớn, khi cần lưu tiến độ, ứng dụng có thể ghi **ID nghiệp vụ/khóa chọn đã xử lý** vào một bảng job-control trong transaction tương ứng thay vì dùng ROWID như một checkpoint lâu dài.

## 20. SQLite: chọn khóa rồi UPDATE/DELETE

SQLite hỗ trợ các cú pháp với `ORDER BY`/`LIMIT` trong `UPDATE`/`DELETE` **nếu bản build được biên dịch với tùy chọn `SQLITE_ENABLE_UPDATE_DELETE_LIMIT`**. Không nên mặc định mọi bản SQLite nhúng đều có tùy chọn này.

Một mẫu dùng subquery chọn ID có thứ tự:

~~~sql
-- SQLite: giả sử bảng yeu_cau có cột id là khóa chính.
UPDATE yeu_cau
SET trang_thai = 'DANG_XU_LY'
WHERE id IN (
    SELECT id
    FROM yeu_cau
    WHERE trang_thai = 'CHO_XU_LY'
    ORDER BY tao_luc, id
    LIMIT 100
);
~~~

Với xóa:

~~~sql
DELETE FROM nhat_ky
WHERE id IN (
    SELECT id
    FROM nhat_ky
    WHERE xay_ra_luc < '2026-10-01'
    ORDER BY xay_ra_luc, id
    LIMIT 100
);
~~~

Các mẫu vẫn cần **điều kiện nghiệp vụ đầy đủ**: tổ chức, chính sách giữ dữ liệu, trạng thái, cutoff và khóa duy nhất. Cơ chế đồng thời của SQLite khác PostgreSQL/MySQL/SQL Server; thông thường chỉ một writer có thể ghi tại một thời điểm theo chế độ giao dịch/lưu trữ phù hợp, nên không chép `SKIP LOCKED` vào SQLite.

SQLite 3.35+ hỗ trợ `RETURNING` trong `UPDATE`/`DELETE` ở những ngữ cảnh phù hợp, nhưng có giới hạn riêng về thứ tự đầu ra và cách sử dụng DML RETURNING trong subquery.

## 21. Tóm tắt khác biệt phương ngữ

| DBMS | Giới hạn batch UPDATE/DELETE | Chọn thứ tự | Cơ chế phối hợp nhiều worker |
| --- | --- | --- | --- |
| **PostgreSQL** | Chọn ID trong CTE/subquery với `LIMIT`, sau đó DML | `ORDER BY` trong CTE chọn ứng viên | `FOR UPDATE SKIP LOCKED`, transaction, retry |
| **MySQL** | Single-table `UPDATE/DELETE ... ORDER BY ... LIMIT N` | `ORDER BY` trong chính DML một bảng | InnoDB row locking, `SELECT ... FOR UPDATE`, `SKIP LOCKED` theo phiên bản |
| **SQL Server** | `TOP (N)` hoặc CTE chọn `TOP (N)` | `ORDER BY` trong CTE/nguồn `TOP` để xác định ứng viên | Transaction, `UPDLOCK`/`READPAST` theo isolation |
| **Oracle** | Subquery chọn `ROWID`/`ID` giới hạn bằng `ROWNUM`/row limiting | `ORDER BY` ở subquery trước giới hạn | Cursor `FOR UPDATE SKIP LOCKED`, PL/SQL/app, transaction |
| **SQLite** | Chọn ID qua subquery `ORDER BY ... LIMIT`; DML LIMIT tùy compile option | Thứ tự ở truy vấn chọn ID | Cơ chế writer locking của SQLite, transaction/retry |

**Không phải cứ DBMS có `LIMIT`, `TOP` hay `FETCH FIRST` là gắn được trực tiếp vào cùng vị trí trong `UPDATE`/`DELETE`.** Dạng câu và ràng buộc cú pháp cần được đối chiếu phiên bản thực tế.

## 22. Giới hạn batch size: lớn hay nhỏ?

Không có con số batch size đúng cho mọi hệ thống. Chẳng hạn, `100`, `500` hoặc `1000` hàng mỗi lượt có thể là **điểm bắt đầu để thử nghiệm**, không phải quy tắc bắt buộc.

Những yếu tố ảnh hưởng:

- Kích thước hàng và các cột lớn (JSON, BLOB, TEXT);
- Số lượng index cần cập nhật;
- Trigger, foreign key, cascade;
- Tốc độ ổ đĩa, WAL/redo/undo, replication;
- Tải đọc/ghi đang diễn ra;
- Mức tranh chấp và yêu cầu độ trễ;
- Thời gian tối đa cho một transaction;
- Khả năng rollback/khôi phục và giới hạn maintenance window.

Một job vận hành có thể **điều chỉnh động batch size** dựa trên latency và mức tải, ví dụ giảm khi lock wait tăng hoặc replica lag vượt ngưỡng. Tuy nhiên, tăng/giảm batch size không được làm sai thuật toán tiếp nối.

### 22.1. Cần giới hạn thời gian chạy

Ngoài số hàng tối đa mỗi lô, có thể đặt:

- Thời gian tối đa của một batch;
- Thời gian tối đa của toàn job;
- Số lô tối đa trong một lần chạy;
- Mức tải CPU/IO hoặc replication lag cho phép;
- Tín hiệu dừng hoặc lịch maintenance window.

Với batch size nhỏ nhưng một truy vấn thiếu index quét toàn bảng mỗi lần, tổng chi phí vẫn có thể rất lớn.

## 23. Chỉ mục hỗ trợ điều kiện lọc và thứ tự

Với PostgreSQL, một truy vấn tìm hàng chờ:

~~~sql
SELECT id
FROM yeu_cau_lo
WHERE to_chuc_id = 10
  AND trang_thai = 'CHO_XU_LY'
ORDER BY muc_uu_tien DESC, tao_luc, id
LIMIT 2;
~~~

có thể được hỗ trợ bởi chỉ mục có tiền tố phù hợp:

~~~sql
CREATE INDEX idx_yeu_cau_lo_chon_batch
ON yeu_cau_lo (
    to_chuc_id,
    trang_thai,
    muc_uu_tien DESC,
    tao_luc,
    id
);
~~~

Với dọn nhật ký:

~~~sql
CREATE INDEX idx_nhat_ky_lo_retention
ON nhat_ky_lo (to_chuc_id, giu_lai, xay_ra_luc, id);
~~~

Hai index trên chỉ để **minh họa cách kết nối WHERE với ORDER BY**. Trong hệ thống thật:

- Cần kiểm tra index đã có, phân bố giá trị và thống kê;
- Bảng có nhiều cập nhật trạng thái sẽ phát sinh **chi phí duy trì index**;
- Chỉ mục phù hợp không buộc optimizer luôn sử dụng nó;
- Trên bảng thực hành chỉ vài dòng, seq scan có thể rẻ hơn index scan;
- Với job retention rất lớn, **partitioning theo thời gian** và loại bỏ cả partition có thể là hướng tốt hơn DELETE hàng loạt nếu chính sách cho phép.

### 23.1. Index và số lượng hàng bị khóa

`LIMIT N` không bảo đảm mọi hoạt động của truy vấn chỉ đọc hoặc khóa đúng N hàng ở mọi DBMS và isolation. Với `WHERE` phức tạp, `JOIN`, `SKIP LOCKED`, ORDER BY, bộ tối ưu hóa có thể phải đọc nhiều ứng viên để tìm đủ N hàng thích hợp.

Hãy đo **số hàng thực sự scan, lock wait và thời gian transaction**, không chỉ nhìn con số N.

### 23.2. EXPLAIN chỉ để quan sát kế hoạch

~~~sql
EXPLAIN
WITH can_xoa AS (
    SELECT id
    FROM nhat_ky_lo
    WHERE to_chuc_id = 10
      AND NOT giu_lai
      AND xay_ra_luc < TIMESTAMPTZ '2026-10-01 00:00:00+07'
    ORDER BY xay_ra_luc, id
    LIMIT 3
)
DELETE FROM nhat_ky_lo AS n
USING can_xoa AS c
WHERE n.id = c.id;
~~~

Trong PostgreSQL, `EXPLAIN` mô tả kế hoạch dự kiến. **`EXPLAIN (ANALYZE)` thực sự thực thi DML**, nên cần cẩn thận: nếu chạy với DML trên dữ liệu thật, nó **sửa hoặc xóa dữ liệu**; có thể bọc trong transaction và rollback trong môi trường thử nghiệm, nhưng một số side effect ngoài giao dịch vẫn có thể tồn tại.

## 24. Xóa dữ liệu có khóa ngoại và cascade

Một câu:

~~~sql
DELETE FROM don_hang
WHERE tao_luc < :cutoff;
~~~

có thể thất bại nếu có bảng `chi_tiet_don` tham chiếu đến `don_hang` bằng khóa ngoại `ON DELETE RESTRICT` hoặc `NO ACTION`. Với `ON DELETE CASCADE`, xóa một số ít hàng cha có thể kéo theo **rất nhiều hàng con**.

Do đó, batch size `100` trên **bảng cha** không đồng nghĩa chỉ có `100` row writes tổng cộng.

### 24.1. Chọn chiến lược dữ liệu có quan hệ

Có thể cần:

- Xóa dữ liệu con trước dữ liệu cha theo transaction/quy tắc FK;
- Dùng cascade nếu nghiệp vụ và tải hệ thống phù hợp;
- Lưu/ẩn danh dữ liệu thay vì xóa nếu có nghĩa vụ lưu giữ;
- Tách lịch sử sang kho lưu trữ trước khi purge;
- Xóa/đổi partition theo chính sách thời gian;
- Giữ audit record hoặc tombstone theo yêu cầu nghiệp vụ.

Không được “giải quyết” vấn đề bằng cách tắt khóa ngoại tùy tiện ở production để chạy DELETE nhanh.

### 24.2. Soft delete và hard delete

Hai kỹ thuật khác nhau:

**Soft delete:**

~~~sql
-- Mẫu trên bảng giả định có xoa_luc:
UPDATE tai_khoan
SET xoa_luc = CURRENT_TIMESTAMP
WHERE id = :id
  AND xoa_luc IS NULL;
~~~

**Hard delete:**

~~~sql
DELETE FROM tai_khoan
WHERE id = :id;
~~~

Soft delete có thể giúp tạm ẩn dữ liệu, nhưng hàng vẫn tồn tại, index vẫn tốn chỗ, và chính sách truy vấn/phân quyền phải **loại hàng bị xóa mềm** đúng cách. Với hard delete theo lô, cần xác định quyền, retention và các quan hệ phụ thuộc.

## 25. Đo lường tiến độ và khả năng khôi phục

Một job batch đáng tin cậy cần biết **đã làm được bao nhiêu** và **đang dừng ở đâu**.

Các chỉ tiêu thường được ghi:

| Chỉ tiêu | Ý nghĩa |
| --- | --- |
| `job_id` | Định danh một lượt vận hành |
| `started_at`, `finished_at` | Thời điểm bắt đầu/kết thúc |
| `cutoff` | Mốc dữ liệu cố định của lượt |
| `batch_size` | Số hàng tối đa một lô |
| `batch_number` | Số lượt đã chạy |
| `affected_rows` | Số hàng thực sự UPDATE/DELETE ở lô |
| `total_affected` | Tổng số hàng đã tác động thành công |
| `last_key` | Checkpoint nếu dùng keyset |
| `duration_ms` | Độ trễ mỗi lô |
| `retry_count` | Số lần lỗi cần retry |
| `status` | RUNNING, PAUSED, COMPLETED, FAILED... |

### 25.1. Không ghi checkpoint bằng biến bộ nhớ rồi tin rằng đã bền vững

Nếu tiến độ chỉ nằm trong RAM và tiến trình bị kill, job có thể phải bắt đầu lại. Điều này **không nhất thiết nguy hiểm** nếu mỗi lượt DML có điều kiện idempotent, ví dụ:

~~~sql
UPDATE yeu_cau_lo
SET trang_thai = 'DANG_XU_LY'
WHERE trang_thai = 'CHO_XU_LY';
~~~

Hàng đã chuyển trạng thái sẽ không bị nhận lại theo chính điều kiện đó. Nhưng nếu thao tác tăng `so_du = so_du + 100` mà không có dấu đã xử lý, chạy lại có thể **cộng tiền thêm lần nữa**. Các thao tác có tác dụng không idempotent cần chiến lược khác.

### 25.2. Mẫu bảng quản lý job

~~~sql
-- Mô hình gợi ý, không bắt buộc cho mọi batch job.
CREATE TEMP TABLE tien_do_batch (
    job_id TEXT PRIMARY KEY,
    cutoff TIMESTAMPTZ NOT NULL,
    last_id BIGINT,
    total_affected BIGINT NOT NULL DEFAULT 0,
    trang_thai TEXT NOT NULL DEFAULT 'RUNNING',
    cap_nhat_luc TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
~~~

Với job dùng keyset, nếu checkpoint nằm cùng database, hãy cập nhật bảng tiến độ **trong cùng transaction** với DML của lô (theo thiết kế phù hợp) để giảm nguy cơ “checkpoint đã tiến nhưng dữ liệu chưa đổi”.

### 25.3. Monitoring và alert

Một job chạy quá lâu có thể không lỗi SQL nhưng vẫn không đạt mục tiêu. Nên giám sát:

- Lô nào liên tục trả 0 hàng trong khi vẫn còn ứng viên?
- Có bao nhiêu hàng ở trạng thái `DANG_XU_LY` lâu bất thường?
- Số lần retry và deadlock có tăng?
- Độ trễ mỗi lô, lock wait và lag replica có vượt ngưỡng?
- Có tenant nào bị bỏ đói do ưu tiên hoặc SKIP LOCKED?
- Tổng số hàng xử lý có phù hợp số dự kiến trong phạm vi cutoff?

Việc hoàn tất một job phải gắn với **định nghĩa dữ liệu đã được xử lý**, không chỉ một vòng lặp kết thúc.

## 26. Checklist thiết kế trước khi chạy batch trên production

1. **Điều kiện WHERE có đủ chặt không?** Có `to_chuc_id`, trạng thái, cutoff, cờ giữ dữ liệu hay không?
2. **Đã xem trước tập ứng viên chưa?** Dùng `SELECT` với đúng điều kiện, quan sát số lượng và các khóa quan trọng.
3. **Khóa sắp xếp có ổn định không?** Có tie-breaker duy nhất? Có bị thay đổi khi update?
4. **Chiến lược tiếp nối là gì?** Lặp theo hàng còn đủ điều kiện hay keyset với cursor?
5. **Điều kiện nào làm hàng rời tập?** Status đổi hay hàng bị xóa?
6. **Có dùng OFFSET không?** Tránh OFFSET khi tập đang co lại.
7. **Có nhiều worker không?** Nếu có, khóa và skip-locked, retry, lease, fairness xử lý ra sao?
8. **Khi nhận 0 hàng có thực sự hết việc không?** Có thể là hàng bị khóa hoặc mới commit muộn.
9. **Mỗi lô có transaction riêng không?** COMMIT/ROLLBACK, timeout, deadlock retry được xử lý chưa?
10. **Checkpoint có nhất quán với COMMIT không?** Có thể bỏ sót sau crash không?
11. **Có quan hệ FK/cascade/trigger không?** Một hàng cha có kéo theo nhiều thay đổi?
12. **Có index phù hợp chưa?** Có tránh quét toàn bảng ở mỗi lượt?
13. **Batch size và điều kiện dừng vận hành đã chốt chưa?** Có giới hạn thời gian và khả năng pause?
14. **Có cơ chế quan sát và khôi phục không?** Audit, tổng số hàng, lỗi, backup/recovery.
15. **Có cần tính nguyên tử toàn bảng không?** Nếu có, nhiều COMMIT nhỏ không tự đáp ứng.

## 27. Những lỗi thường gặp

| Sai lầm | Nguyên nhân | Hướng khắc phục |
| --- | --- | --- |
| `DELETE` rồi tăng `OFFSET` mỗi lượt | Tập còn lại co lại, các hàng dịch vị trí | Luôn chọn đầu tập còn hợp lệ hoặc dùng keyset |
| `UPDATE` chỉ sửa cột không ảnh hưởng điều kiện | Cùng hàng bị chọn lặp vô hạn | Đổi trạng thái/đánh dấu đã xử lý hoặc tiến cursor |
| `LIMIT N` nhưng không có thứ tự rõ | Lô chọn hàng nào không xác định theo yêu cầu | `ORDER BY` có khóa duy nhất |
| Coi thứ tự RETURNING/OUTPUT là thứ tự xử lý | DML không bảo đảm output theo thứ tự ứng viên | `ORDER BY` khi trình bày/lấy checkpoint |
| Dùng cursor `id > last_id` với hàng bị SKIP LOCKED | Bỏ qua hàng khóa cũ mãi mãi | Quét lại tập chưa xử lý hoặc có cơ chế revisit |
| Cursor dựa vào cột bị UPDATE | Hàng vượt qua biên cursor | Dùng khóa bất biến hoặc staging |
| Cứ thay `cutoff` bằng giờ hiện tại ở mỗi lô | Phạm vi job liên tục mở rộng | Chốt cutoff của lượt vận hành |
| `0 affected rows` được coi luôn là xong | Có thể bị skip locked/điều kiện thay đổi | Đối soát và retry theo chính sách |
| Dùng `MAX(id)` làm checkpoint toàn cục mà không xét commit | ID không phải thứ tự commit | Chốt phạm vi chính xác hoặc có chiến lược bù |
| Bỏ `to_chuc_id` trong WHERE | Tác động dữ liệu tenant khác | Giữ đủ khóa/phạm vi |
| Chỉ SELECT ID rồi UPDATE sau không khóa | Race và khả năng ghi đè trạng thái đã đổi | DML nguyên tử/khóa/recheck |
| Giữ transaction trong lúc gọi API chậm | Khóa lâu, tăng deadlock/latency | Claim ngắn, COMMIT, lease và xử lý ngoài |
| Không có lease cho queue | Worker crash để hàng DANG_XU_LY mãi | Lease timeout/retry/owner |
| Chia lô rồi nghĩ toàn bộ job nguyên tử | Mỗi COMMIT làm trạng thái trung gian lộ ra | Thiết kế staging/transaction khác nếu cần atomic |
| Xóa parent mà không xét child | FK lỗi hoặc cascade cực lớn | Xem quan hệ và chiến lược xóa |
| Dùng cú pháp `UPDATE LIMIT` MySQL trên PostgreSQL | Khác phương ngữ | PostgreSQL dùng CTE chọn ID |
| Dùng `UPDATE TOP(N)` SQL Server để chọn “N cũ nhất” | TOP không tự bảo đảm thứ tự | CTE `SELECT TOP ... ORDER BY` |
| Dùng `ROWID` như khóa nghiệp vụ lâu dài | ROWID có tính chất vị trí/triển khai Oracle | Dùng khóa PK/business key cho checkpoint |

## 28. Bài tập thực hành có lời giải

Các bài 1–13 dùng PostgreSQL và bộ dữ liệu ở mục 3, trừ khi có ghi chú khác. Những ví dụ có `BEGIN; ... ROLLBACK;` dùng để **thực hành mà không giữ thay đổi**; nếu muốn thử vòng lặp thực sự, cần quản lý `COMMIT` và tạo lại dữ liệu khi cần.

### Bài 1. Chọn hai yêu cầu ưu tiên cao nhất

**Yêu cầu:** lấy tối đa hai hàng `CHO_XU_LY` của tổ chức 10, ưu tiên lớn trước, thời gian sớm trước, ID nhỏ trước.

**Lời giải:**

~~~sql
SELECT id, muc_uu_tien, tao_luc
FROM yeu_cau_lo
WHERE to_chuc_id = 10
  AND trang_thai = 'CHO_XU_LY'
ORDER BY muc_uu_tien DESC, tao_luc, id
LIMIT 2;
~~~

Kết quả từ dữ liệu gốc: **101 và 103**.

### Bài 2. UPDATE tối đa hai hàng trong PostgreSQL

**Yêu cầu:** chuyển hai ứng viên ở bài 1 sang `DANG_XU_LY`, trả ID, không giữ thay đổi.

**Lời giải:**

~~~sql
BEGIN;

WITH ung_vien AS (
    SELECT id
    FROM yeu_cau_lo
    WHERE to_chuc_id = 10
      AND trang_thai = 'CHO_XU_LY'
    ORDER BY muc_uu_tien DESC, tao_luc, id
    LIMIT 2
    FOR UPDATE SKIP LOCKED
)
UPDATE yeu_cau_lo AS y
SET trang_thai = 'DANG_XU_LY'
FROM ung_vien AS u
WHERE y.id = u.id
RETURNING y.id, y.trang_thai;

ROLLBACK;
~~~

Không có session khác giữ khóa, hai hàng được cập nhật là **101 và 103**. `ROLLBACK` đưa chúng trở về `CHO_XU_LY`.

### Bài 3. Xóa ba nhật ký cũ nhất đủ điều kiện

**Yêu cầu:** chỉ xóa nhật ký tổ chức 10 trước 01/10, không xóa hàng `giu_lai=TRUE`.

**Lời giải:**

~~~sql
BEGIN;

WITH ung_vien AS (
    SELECT id
    FROM nhat_ky_lo
    WHERE to_chuc_id = 10
      AND xay_ra_luc < TIMESTAMPTZ '2026-10-01 00:00:00+07'
      AND giu_lai = FALSE
    ORDER BY xay_ra_luc, id
    LIMIT 3
    FOR UPDATE
)
DELETE FROM nhat_ky_lo AS n
USING ung_vien AS u
WHERE n.id = u.id
RETURNING n.id;

ROLLBACK;
~~~

Ba ID là **201, 202, 204**. ID 203 thuộc diện giữ lại nên không bị chọn dù thời điểm của nó cũng cũ.

### Bài 4. Vì sao OFFSET bỏ sót?

Có sáu ID `1,2,3,4,5,6`. Sau khi xóa `1,2`, tập còn `3,4,5,6`. Lần tiếp theo dùng `OFFSET 2 LIMIT 2` thì chọn gì?

**Lời giải:** Chọn **5,6**, bỏ qua **3,4**. Sau khi DML làm tập ứng viên co lại, không tăng OFFSET theo số hàng đã xóa. Hãy chọn lại các hàng đủ điều kiện từ đầu hoặc dùng keyset đúng cách.

### Bài 5. Đếm số lô cần xử lý

Ban đầu tổ chức 10 có sáu yêu cầu `CHO_XU_LY`. Nếu mỗi lô nhận chính xác tối đa hai hàng và không có worker khác/công việc mới, cần bao nhiêu lô có cập nhật?

**Lời giải:** **Ba lô** (2 + 2 + 2). Một lượt truy vấn tiếp theo trả 0 hàng để nhận biết tập ứng viên đã hết trong điều kiện không có đồng thời. Nếu có `SKIP LOCKED` và session khác, 0 hàng không còn là bằng chứng tuyệt đối.

### Bài 6. Lặp theo điều kiện còn hợp lệ

**Yêu cầu:** giải thích vì sao có thể không dùng cursor khi chuyển `CHO_XU_LY` thành `DANG_XU_LY` theo lô.

**Lời giải:** Sau `COMMIT`, những hàng vừa đổi **không còn thỏa `WHERE trang_thai='CHO_XU_LY'`**, nên lượt sau sẽ chọn những hàng còn chờ. Điều kiện phải được giữ ở tất cả các lượt; nếu UPDATE chỉ sửa một cột khác và không làm hàng rời tập, cùng hàng có thể bị chọn lặp.

### Bài 7. Keyset theo ID

**Yêu cầu:** viết SELECT lấy tối đa ba hàng sau ID 103 của tổ chức 10, sắp theo ID, không dùng OFFSET.

**Lời giải:**

~~~sql
SELECT id
FROM yeu_cau_lo
WHERE to_chuc_id = 10
  AND id > 103
ORDER BY id
LIMIT 3;
~~~

Trên dữ liệu gốc, các ID là **104, 105, 108** (đây là toàn bộ trạng thái). Nếu yêu cầu chỉ lấy hàng `CHO_XU_LY`, phải thêm `AND trang_thai='CHO_XU_LY'`, khi ấy kết quả là **105, 108, 109**. Không được lẫn kết quả có lọc trạng thái với không lọc.

### Bài 8. Keyset với hai cột

**Yêu cầu:** tiếp tục sau cặp `(tao_luc='2026-10-01 08:00:00+07', id=101)` theo `ORDER BY tao_luc,id`.

**Lời giải PostgreSQL:**

~~~sql
SELECT id, tao_luc
FROM yeu_cau_lo
WHERE to_chuc_id = 10
  AND (tao_luc, id) > (
      TIMESTAMPTZ '2026-10-01 08:00:00+07',
      101
  )
ORDER BY tao_luc, id
LIMIT 3;
~~~

Cặp khóa xử lý trường hợp **nhiều hàng trùng thời điểm**, nhờ ID làm tie-breaker. Khi chỉ muốn hàng chờ, phải thêm điều kiện trạng thái tương ứng.

### Bài 9. Cursor cộng SKIP LOCKED nguy hiểm ở đâu?

Giả sử ID 101 bị khóa, worker nhận 102–103 bằng `SKIP LOCKED` rồi lưu `last_id=103`. Vì sao ID 101 có nguy cơ bị bỏ sót?

**Lời giải:** Lượt sau `WHERE id > 103` không còn xét ID 101 dù đã mở khóa và vẫn cần xử lý. Cần **quét lại tập còn hợp lệ** hoặc một cơ chế revisit/ghi nhận ID bị skip. Không dùng cursor một chiều mà không xét các hàng bị bỏ qua.

### Bài 10. Vì sao phải chốt cutoff?

**Yêu cầu:** job xóa nhật ký cũ chạy 20 phút. Nên dùng `CURRENT_TIMESTAMP` mới tính tại mỗi lô làm ranh giới hay chốt một cutoff cố định?

**Lời giải:** Thường nên **chốt cutoff** cho một lượt job, ví dụ `2026-10-01 00:00:00+07`. Nếu mỗi lượt tính cutoff mới, tập dữ liệu có thể mở rộng dần, khó biết job đã hoàn thành **kỳ dữ liệu nào**. Quy tắc retention chính thức vẫn phải do nghiệp vụ quy định.

### Bài 11. SQL Server có TOP nhưng chưa có thứ tự

**Yêu cầu:** chọn 100 yêu cầu `CHO_XU_LY` cũ nhất trong SQL Server để cập nhật.

**Lời giải T-SQL:**

~~~sql
;WITH UngVien AS (
    SELECT TOP (100) Id
    FROM dbo.YeuCau
    WHERE TrangThai = N'CHO_XU_LY'
    ORDER BY TaoLuc, Id
)
UPDATE y
SET TrangThai = N'DANG_XU_LY'
FROM dbo.YeuCau AS y
JOIN UngVien AS u ON u.Id = y.Id;
~~~

`UPDATE TOP(100)` đơn lẻ không cho biết 100 hàng nào là “cũ nhất”; phần **chọn ứng viên với ORDER BY** mới diễn đạt yêu cầu đó.

### Bài 12. MySQL một bảng

**Yêu cầu:** xóa tối đa 100 nhật ký cũ nhất trong MySQL, với cutoff và cờ giữ dữ liệu.

**Lời giải:**

~~~sql
DELETE FROM nhat_ky
WHERE to_chuc_id = 10
  AND xay_ra_luc < '2026-10-01 00:00:00'
  AND giu_lai = 0
ORDER BY xay_ra_luc, id
LIMIT 100;
~~~

Đây là cú pháp **single-table DELETE** MySQL. Không suy rằng PostgreSQL hoặc mọi dạng multi-table DELETE MySQL có cùng cú pháp.

### Bài 13. Oracle giới hạn tập ứng viên

**Yêu cầu:** nêu cách xóa tối đa 50 hàng theo `xay_ra_luc,id` ở Oracle.

**Lời giải:** Chọn ROWID của tối đa 50 hàng từ một subquery đã `ORDER BY`, sau đó `DELETE WHERE ROWID IN (...)` như mục 19. Khi nhiều worker chạy song song, mẫu này cần bổ sung chiến lược concurrency và transaction; `ROWID` không phải checkpoint nghiệp vụ lâu dài.

### Bài 14. Giao dịch nhiều lô có nguyên tử toàn bộ không?

**Câu hỏi:** ba lô đã `COMMIT` lần lượt, lô thứ tư thất bại và rollback. Có tự động hoàn nguyên ba lô đầu không?

**Lời giải:** **Không.** Ba lô đã commit vẫn giữ tác động. Nếu nghiệp vụ đòi “tất cả hoặc không có gì”, phải chọn thiết kế giao dịch/triển khai khác; chia lô với COMMIT riêng không tạo tính nguyên tử toàn job.

### Bài 15. 0 hàng được trả trong SKIP LOCKED

**Câu hỏi:** lô với `FOR UPDATE SKIP LOCKED` trả 0 hàng. Có thể khẳng định hàng đợi trống không?

**Lời giải:** **Không.** Các hàng thỏa điều kiện có thể đang bị khóa, hoặc dữ liệu thay đổi đồng thời. Cần đối soát/phân biệt “hết việc” và “không có hàng khả dụng ở lượt này”, sau đó retry/backoff theo chính sách.

### Bài 16. Soft delete có bảo đảm không xử lý lại?

Giả sử soft delete được thực hiện:

~~~sql
UPDATE tai_khoan
SET xoa_luc = CURRENT_TIMESTAMP
WHERE id IN (SELECT id FROM tai_khoan ORDER BY id LIMIT 100);
~~~

**Câu hỏi:** Nếu lặp câu này, nó có tiến dần qua các tài khoản chưa bị xóa mềm không?

**Lời giải:** **Không bảo đảm.** Không có `WHERE xoa_luc IS NULL`, nên những hàng đã đánh dấu vẫn có thể được chọn lại. Cần đưa điều kiện “chưa xóa mềm” vào **truy vấn chọn ứng viên và/hoặc DML**, cùng kiểm soát quyền/phạm vi.

### Bài 17. Chọn batch size

**Câu hỏi:** 1000 hàng/lô có phải luôn tốt hơn 100 hàng/lô?

**Lời giải:** **Không.** Batch lớn có thể giảm overhead số lần lặp nhưng tăng lock time, WAL, áp lực replication, chi phí rollback và latency; batch nhỏ giảm một số rủi ro nhưng tăng số lần lệnh/commit và scan. Cần **đo trên workload thực tế**, có giới hạn thời gian và giám sát.

### Bài 18. Thiết kế quy trình xóa nhật ký an toàn

**Yêu cầu:** mô tả ngắn một job retention theo lô cho dữ liệu nhiều tổ chức.

**Gợi ý lời giải:**

1. Chọn **một tổ chức hoặc phạm vi tenant được phép**, chốt `cutoff` và chính sách `giu_lai`.
2. `SELECT` xem trước số hàng và ID cũ nhất trong phạm vi đó.
3. Chọn các ID bằng `ORDER BY xay_ra_luc,id LIMIT N`; dùng transaction và khóa phù hợp.
4. `DELETE` đúng tập ID ứng viên, trả ID đã xóa nếu DBMS hỗ trợ và cần audit.
5. `COMMIT` từng lô, ghi tổng số hàng/tốc độ và lỗi.
6. Lặp theo **hàng còn đủ điều kiện**, không tăng OFFSET.
7. Nếu `SKIP LOCKED` trả 0 hàng, đối soát/đợi những hàng bị khóa theo chính sách; không mặc định hoàn tất.
8. Kết thúc khi phạm vi đã chốt **không còn hàng phải xóa** theo điều kiện kiểm tra nhất quán phù hợp, rồi lưu báo cáo job.

## 29. Tóm tắt lựa chọn chiến lược

| Tình huống | Cách tiếp nối thường phù hợp | Điều cần bảo đảm |
| --- | --- | --- |
| DELETE các hàng đã quá hạn | Lặp chọn **N hàng còn đủ điều kiện** | Chốt cutoff, giữ điều kiện, chú ý FK/lock |
| UPDATE cờ `chua_xu_ly` → `da_xu_ly` | Lặp theo trạng thái/cờ còn lại | UPDATE làm hàng rời tập ứng viên |
| Quét bảng đọc/ghi theo một khóa bất biến | Keyset `id > last_id` | Checkpoint đúng sau COMMIT; không bỏ sót khóa nhỏ đến muộn |
| Quét theo timestamp có trùng | Keyset `(timestamp,id) > (last_time,last_id)` | Có tie-breaker, timestamp không đổi |
| Queue nhiều worker, throughput quan trọng | Chọn/lấy khóa bằng `SKIP LOCKED`, quét lại tập còn chờ | Retry, lease, fairness, 0 hàng chưa chắc hết |
| Ưu tiên thay đổi động | Mỗi lô chọn ưu tiên cao nhất **còn hợp lệ** | Không dùng cursor đơn giản theo priority biến động |
| Cần xử lý tuyệt đối đúng thứ tự | Điều phối/khóa đơn tuyến hoặc thiết kế tuần tự rõ | Không trông đợi SKIP LOCKED bảo đảm FIFO |
| Cần all-or-nothing toàn bảng | Thiết kế transaction/staging khác | Nhiều COMMIT riêng không nguyên tử toàn job |
| Bảng retention theo phân vùng thời gian | Cân nhắc thao tác partition | Phạm vi ngày, FK, quyền, tác động vận hành |

## 30. Kết luận

`UPDATE` và `DELETE` theo lô là kỹ thuật quan trọng khi xử lý **dữ liệu lớn, hàng đợi và công việc bảo trì định kỳ**. Nhưng giới hạn `N` hàng chỉ là bước đầu; một quy trình tin cậy phải phối hợp được:

1. **Điều kiện lọc đúng:** tác động đúng tổ chức, trạng thái, cutoff và dữ liệu được phép thay đổi.
2. **Thứ tự xác định:** `ORDER BY` phù hợp nghiệp vụ và có khóa phân xử duy nhất.
3. **Điều kiện tiếp nối:** hoặc lặp trên những hàng còn đủ điều kiện, hoặc keyset trên khóa ổn định; tránh `OFFSET` khi tập đang thay đổi.
4. **Giao dịch hợp lý:** mỗi lô có ranh giới commit, rollback và retry rõ; không lẫn thành công của câu DML với thành công của toàn job.
5. **Đồng thời có kiểm soát:** dùng khóa hàng, `SKIP LOCKED`/cơ chế tương ứng khi phù hợp, và luôn xử lý khả năng bỏ qua tạm thời hoặc worker crash.
6. **Điều kiện dừng đáng tin:** một lô trả 0 hàng có thể là hết việc, cũng có thể chỉ là chưa có hàng khả dụng ở thời điểm đó.
7. **Khả năng quan sát/khôi phục:** lưu cutoff, checkpoint, số hàng tác động, lỗi và tiến độ; đo hiệu năng và giữ quy trình dữ liệu an toàn.

**Điểm mấu chốt:** đừng hỏi chỉ “làm sao UPDATE/DELETE 1000 hàng mỗi lần?”. Hãy hỏi thêm **“1000 hàng nào, theo thứ tự nào, sau lô này tôi tiếp tục từ đâu, và nếu có lỗi hoặc session khác đang xử lý thì hàng nào có thể bị bỏ sót?”**. Trả lời được những câu hỏi đó là nền tảng để viết SQL batch đúng, bền vững và có thể vận hành thực tế.
