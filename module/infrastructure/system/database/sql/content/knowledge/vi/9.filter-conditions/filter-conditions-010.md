# Tránh điều kiện mâu thuẫn, dư thừa và sai ưu tiên trong SQL

Điều kiện lọc quyết định **dòng nào được giữ lại** trong kết quả truy vấn hoặc **dòng nào bị tác động** bởi một câu lệnh cập nhật, xóa. Một sai sót nhỏ trong `WHERE`, chẳng hạn thiếu dấu ngoặc khi kết hợp `AND` với `OR`, có thể khiến truy vấn trả về khách hàng của tổ chức khác; còn một điều kiện tự mâu thuẫn có thể trả về **0 dòng** dù dữ liệu tồn tại. Điều kiện dư thừa thường làm câu SQL khó đọc hơn, che khuất ý định và đôi khi ảnh hưởng đến cách tối ưu hóa truy vấn.

Bài học này tập trung vào ba nhóm sai sót:

1. **Mâu thuẫn:** các điều kiện không thể cùng đúng với bất kỳ hàng nào.
2. **Dư thừa:** một điều kiện đã được điều kiện khác bao hàm, nên bỏ đi vẫn giữ nguyên ý nghĩa trong ngữ cảnh thích hợp.
3. **Sai ưu tiên:** `AND`, `OR`, `NOT` được kết hợp khác với mong muốn do thiếu dấu ngoặc hoặc phủ định không đúng.

Để hiểu và sửa ba nhóm lỗi đó, cần nắm thêm logic ba giá trị của SQL với `NULL`, các điều kiện khoảng, `IN`/`NOT IN`, tác động của `JOIN` và cách xác nhận yêu cầu nghiệp vụ. Ví dụ chạy được trên **PostgreSQL** trừ những đoạn ghi rõ là cú pháp minh họa; cách xử lý logic `AND`/`OR`/`NOT` về cơ bản phổ biến ở nhiều hệ quản trị quan hệ.

## 1. Điều kiện lọc là một biểu thức logic

Một điều kiện trong `WHERE` có thể gồm:

- Phép so sánh: `=`, `<>`, `<`, `<=`, `>`, `>=`;
- Kiểm tra tập giá trị: `IN (...)`, `NOT IN (...)`;
- Kiểm tra khoảng: `BETWEEN ... AND ...`;
- Kiểm tra dạng chuỗi: `LIKE`, `ILIKE` (PostgreSQL), biểu thức chính quy theo DBMS;
- Kiểm tra giá trị thiếu: `IS NULL`, `IS NOT NULL`;
- Kiểm tra sự tồn tại của hàng liên quan: `EXISTS (...)`, `NOT EXISTS (...)`;
- Toán tử logic nối các điều kiện: `AND`, `OR`, `NOT`.

Ví dụ:

~~~sql
SELECT id, trang_thai, tong_tien
FROM don_hang_loc
WHERE tong_tien >= 100000
  AND trang_thai = 'DA_THANH_TOAN';
~~~

Mỗi hàng chỉ được trả về khi **cả hai** điều kiện đều đúng. Tuy nhiên, khi có `NULL`, biểu thức SQL có thể nhận thêm trạng thái **`UNKNOWN`** (chưa xác định), không đơn thuần chỉ `TRUE`/`FALSE`. Trong `WHERE`, chỉ hàng có kết quả cuối cùng là `TRUE` được giữ lại; `FALSE` và `UNKNOWN` đều bị loại.

Đọc câu SQL đúng không chỉ là nhìn từng phép so sánh, mà phải hiểu **biểu thức logic hoàn chỉnh** và trường hợp giá trị thiếu.

## 2. Bộ dữ liệu minh họa xuyên suốt

Giả sử một ứng dụng bán hàng phục vụ nhiều tổ chức. Mỗi đơn hàng có `to_chuc_id`, trạng thái, tổng tiền, thời điểm tạo, kênh bán và cờ xóa mềm.

Ví dụ dưới đây tạo bảng tạm trong một phiên PostgreSQL; nếu mở phiên mới, cần tạo lại bảng và dữ liệu.

~~~sql
CREATE TEMP TABLE don_hang_loc (
    id INTEGER PRIMARY KEY,
    khach_hang_id INTEGER NOT NULL,
    to_chuc_id INTEGER NOT NULL,
    trang_thai TEXT,
    tong_tien NUMERIC(12, 2) NOT NULL CHECK (tong_tien >= 0),
    thoi_diem_tao TIMESTAMPTZ NOT NULL,
    kenh_ban TEXT NOT NULL,
    da_xoa BOOLEAN NOT NULL DEFAULT FALSE
);

INSERT INTO don_hang_loc
    (id, khach_hang_id, to_chuc_id, trang_thai,
     tong_tien, thoi_diem_tao, kenh_ban, da_xoa)
VALUES
    (101, 1, 10, 'MOI',          80000, '2026-10-01 09:00:00+07', 'WEB', FALSE),
    (102, 1, 10, 'DA_THANH_TOAN',220000, '2026-10-03 10:00:00+07', 'APP', FALSE),
    (103, 2, 10, 'DA_HUY',      150000, '2026-10-05 08:00:00+07', 'WEB', FALSE),
    (104, 3, 10, NULL,          300000, '2026-10-07 14:00:00+07', 'APP', FALSE),
    (105, 4, 20, 'DA_THANH_TOAN',250000, '2026-10-08 11:00:00+07', 'WEB', FALSE),
    (106, 5, 20, 'MOI',          30000, '2026-10-09 16:00:00+07', 'APP', FALSE),
    (107, 6, 10, 'DA_THANH_TOAN',110000, '2026-10-12 09:30:00+07', 'WEB', TRUE),
    (108, 7, 10, 'MOI',         450000, '2026-11-01 00:00:00+07', 'WEB', FALSE);
~~~

Để dễ theo dõi, một số cột quan trọng:

| id | to_chuc_id | trang_thai | tong_tien | da_xoa |
| ---: | ---: | --- | ---: | --- |
| 101 | 10 | `MOI` | 80.000 | `FALSE` |
| 102 | 10 | `DA_THANH_TOAN` | 220.000 | `FALSE` |
| 103 | 10 | `DA_HUY` | 150.000 | `FALSE` |
| 104 | 10 | `NULL` | 300.000 | `FALSE` |
| 105 | 20 | `DA_THANH_TOAN` | 250.000 | `FALSE` |
| 106 | 20 | `MOI` | 30.000 | `FALSE` |
| 107 | 10 | `DA_THANH_TOAN` | 110.000 | `TRUE` |
| 108 | 10 | `MOI` | 450.000 | `FALSE` |

Cờ `da_xoa = TRUE` biểu thị đơn đã bị xóa mềm nhưng còn được lưu làm lịch sử. Dòng 104 cố ý có trạng thái `NULL` để minh họa cách SQL xử lý dữ liệu chưa biết. Đây là dữ liệu thực hành; hệ thống thật thường bổ sung các ràng buộc và quy tắc nghiệp vụ thích hợp.

## 3. Thứ tự ưu tiên: NOT, AND, OR

Khi các toán tử logic xuất hiện trong cùng biểu thức mà thiếu ngoặc, **`NOT` có độ ưu tiên cao hơn `AND`, và `AND` có độ ưu tiên cao hơn `OR`** trong SQL thông thường:

| Mức ưu tiên | Toán tử | Ý nghĩa |
| --- | --- | --- |
| Cao nhất trong ba toán tử | `NOT` | Phủ định một điều kiện |
| Tiếp theo | `AND` | Hai điều kiện cần đồng thời đúng |
| Thấp nhất | `OR` | Chỉ cần một điều kiện đúng |

Ngoặc tròn `(...)` làm rõ nhóm điều kiện và có thể thay đổi cách biểu thức được hiểu.

### 3.1. Lỗi OR làm lọt dữ liệu ngoài phạm vi

Giả sử yêu cầu: **“Chỉ lấy đơn của tổ chức 10, chưa xóa mềm, có trạng thái MỚI hoặc ĐÃ THANH TOÁN.”**

Truy vấn dễ viết sai:

~~~sql
SELECT id, to_chuc_id, trang_thai
FROM don_hang_loc
WHERE to_chuc_id = 10
  AND trang_thai = 'MOI'
  OR trang_thai = 'DA_THANH_TOAN';
~~~

SQL hiểu biểu thức tương đương:

~~~sql
WHERE (to_chuc_id = 10 AND trang_thai = 'MOI')
   OR trang_thai = 'DA_THANH_TOAN'
~~~

Theo dữ liệu mẫu, truy vấn sẽ nhận các ID `101`, `102`, `105`, `107`, `108`. Đáng chú ý:

- `105` thuộc **tổ chức 20** nhưng vẫn lọt vào nhờ vế `trang_thai = 'DA_THANH_TOAN'`;
- `107` đã **xóa mềm**, vì câu truy vấn còn chưa kiểm tra `da_xoa`.

Với ứng dụng đa tổ chức, lỗi đặt ngoặc có thể gây **lộ dữ liệu giữa các phạm vi truy cập**. Không nên phụ thuộc vào cảm giác khi đọc câu SQL: cần viết điều kiện theo nhóm nghiệp vụ rõ ràng.

Câu đúng:

~~~sql
SELECT id, to_chuc_id, trang_thai
FROM don_hang_loc
WHERE to_chuc_id = 10
  AND da_xoa = FALSE
  AND (
      trang_thai = 'MOI'
      OR trang_thai = 'DA_THANH_TOAN'
  )
ORDER BY id;
~~~

Kết quả đúng cho yêu cầu là `101`, `102`, `108`. Có thể viết gọn hơn bằng `IN`:

~~~sql
SELECT id, trang_thai
FROM don_hang_loc
WHERE to_chuc_id = 10
  AND da_xoa = FALSE
  AND trang_thai IN ('MOI', 'DA_THANH_TOAN')
ORDER BY id;
~~~

Hai câu đúng trên có cùng tập kết quả với bộ dữ liệu đã cho. Việc dùng `IN` khi kiểm tra nhiều giá trị của **cùng một cột** thường dễ đọc hơn chuỗi `OR` lặp lại.

### 3.2. Dấu ngoặc phải thể hiện đúng ý định

So sánh:

~~~sql
-- Nghĩa A: tổ chức 10, và (đơn mới hoặc đã thanh toán).
WHERE to_chuc_id = 10
  AND (trang_thai = 'MOI' OR trang_thai = 'DA_THANH_TOAN')
~~~

với:

~~~sql
-- Nghĩa B: (đơn mới thuộc tổ chức 10) hoặc
-- (mọi đơn đã thanh toán, bất kể tổ chức).
WHERE (to_chuc_id = 10 AND trang_thai = 'MOI')
   OR trang_thai = 'DA_THANH_TOAN'
~~~

Hai biểu thức có cùng các từ khóa và giá trị, nhưng **khác hoàn toàn về phạm vi hàng được giữ lại**. Ngoặc là một phần của ý nghĩa, không đơn thuần là trang trí.

### 3.3. NOT phủ định nhóm hay phủ định một điều kiện?

~~~sql
-- Không ở trạng thái MỚI, đồng thời thuộc tổ chức 10.
WHERE to_chuc_id = 10
  AND NOT (trang_thai = 'MOI')
~~~

khác với:

~~~sql
-- Phủ định toàn bộ tổ hợp điều kiện ở trong ngoặc.
WHERE NOT (to_chuc_id = 10 AND trang_thai = 'MOI')
~~~

Ở câu thứ hai, hàng **không thuộc tổ chức 10** có thể được giữ lại. Khi kết hợp `NOT` với nhiều điều kiện, đặt ngoặc sát **phần muốn phủ định**.

## 4. Điều kiện mâu thuẫn: không hàng nào có thể thỏa mãn

Hai hoặc nhiều điều kiện **mâu thuẫn** nếu không có giá trị hợp lệ nào có thể làm cho biểu thức `AND` của chúng nhận kết quả `TRUE`.

Ví dụ:

~~~sql
SELECT *
FROM don_hang_loc
WHERE trang_thai = 'MOI'
  AND trang_thai = 'DA_THANH_TOAN';
~~~

Một giá trị đơn lẻ `trang_thai` không thể đồng thời bằng hai chuỗi khác nhau. Dòng có `trang_thai = NULL` cũng không đáp ứng, vì các phép so sánh với `NULL` cho `UNKNOWN`. Truy vấn này luôn có **0 dòng** theo ngữ nghĩa thông thường, bất kể bảng có dữ liệu gì.

### 4.1. Những dạng mâu thuẫn thường gặp

| Điều kiện | Vì sao không có giá trị thỏa mãn? | Cách diễn đạt có thể đúng nếu nghiệp vụ là... |
| --- | --- | --- |
| `id = 101 AND id = 102` | Một ID không thể bằng hai số khác nhau | Chọn một trong hai ID: `id IN (101, 102)` |
| `tong_tien >= 200000 AND tong_tien < 100000` | Cận dưới lớn hơn cận trên | Sửa khoảng cho đúng yêu cầu |
| `tong_tien > 100000 AND tong_tien <= 100000` | Hai cận loại trừ nhau tại cùng mốc | Chọn `>=`, `>`, `<=`, `<` hợp lý |
| `trang_thai = 'MOI' AND trang_thai <> 'MOI'` | Một giá trị không thể vừa bằng vừa khác cùng chuỗi | Xác định cần điều kiện khẳng định hay phủ định |
| `id IS NULL AND id IS NOT NULL` | Không có giá trị đồng thời thiếu và không thiếu | Giữ một điều kiện |
| `trang_thai IN ('MOI') AND trang_thai IN ('DA_HUY')` | Hai tập giá trị không giao nhau | Dùng một tập giá trị đúng mục đích hoặc `OR` nếu chọn cả hai |

Một ví dụ dễ gây lỗi khi lập điều kiện động:

~~~sql
-- Phần tìm kiếm mặc định yêu cầu trạng thái MOI.
-- Một bộ lọc bổ sung lại buộc trạng thái DA_HUY.
WHERE trang_thai = 'MOI'
  AND trang_thai = 'DA_HUY'
~~~

Nếu yêu cầu thật là “trạng thái MỚI **hoặc** ĐÃ HỦY”, cần:

~~~sql
WHERE trang_thai IN ('MOI', 'DA_HUY')
~~~

Nhưng **không tự động thay mọi `AND` giữa hai trạng thái bằng `OR`**. Có thể nghiệp vụ muốn phát hiện một cấu hình lọc bất khả thi và báo người dùng rằng các tùy chọn đang xung đột; quyết định phải dựa vào ý nghĩa của yêu cầu.

### 4.2. Mâu thuẫn trong một hàng khác với yêu cầu trên nhiều hàng

Giả sử câu hỏi: “Tìm khách hàng **đã từng có đơn MỚI và cũng từng có đơn ĐÃ THANH TOÁN**.” Điều này hoàn toàn có thể xảy ra vì **mỗi trạng thái nằm ở một đơn khác nhau**.

Sai nếu viết trên **một hàng đơn**:

~~~sql
SELECT khach_hang_id
FROM don_hang_loc
WHERE trang_thai = 'MOI'
  AND trang_thai = 'DA_THANH_TOAN';
~~~

Một cách diễn đạt đúng là kiểm tra hai tập hàng liên quan:

~~~sql
SELECT DISTINCT d1.khach_hang_id
FROM don_hang_loc AS d1
WHERE EXISTS (
    SELECT 1
    FROM don_hang_loc AS d_moi
    WHERE d_moi.khach_hang_id = d1.khach_hang_id
      AND d_moi.trang_thai = 'MOI'
)
AND EXISTS (
    SELECT 1
    FROM don_hang_loc AS d_paid
    WHERE d_paid.khach_hang_id = d1.khach_hang_id
      AND d_paid.trang_thai = 'DA_THANH_TOAN'
)
ORDER BY d1.khach_hang_id;
~~~

Trong dữ liệu mẫu, khách hàng `1` có đơn MỚI (101) và ĐÃ THANH TOÁN (102). Ở truy vấn này, hai `EXISTS` có thể được thỏa mãn bởi **hai hàng khác nhau**, nên không mâu thuẫn. Truy vấn minh họa lịch sử trên toàn bộ bảng; nếu nghiệp vụ giới hạn theo tổ chức hoặc loại trừ đơn đã xóa mềm, phải đưa phạm vi đó vào từng nhánh thích hợp.

**Nguyên tắc:** khi hai trạng thái không thể cùng tồn tại trên **một hàng**, hãy xác định nghiệp vụ đang yêu cầu **một hàng**, **nhiều hàng của cùng thực thể**, hay **trạng thái hiện tại và lịch sử**.

### 4.3. “Không có kết quả” chưa chắc do điều kiện mâu thuẫn

`WHERE tong_tien > 1000000000` có thể trả 0 dòng vì **dữ liệu hiện tại** không có số tiền lớn như vậy, dù về mặt logic điều kiện vẫn có thể đúng trong tương lai. Còn `WHERE tong_tien > 200000 AND tong_tien < 100000` là điều kiện **không thể đúng về mặt toán học** cho một giá trị số.

Vì vậy cần phân biệt:

- **Vô nghiệm theo logic:** biểu thức không thể nhận `TRUE`.
- **Không khớp dữ liệu hiện tại:** biểu thức có thể đúng, nhưng bảng đang không có hàng đáp ứng.
- **Bị loại bởi `NULL`:** biểu thức có thể cho `UNKNOWN`, khiến `WHERE` không giữ hàng.
- **Bị lọc ở bước khác:** `JOIN`, `HAVING`, phân trang hoặc điều kiện quyền truy cập làm thay đổi tập kết quả.

Không thể khẳng định câu SQL mâu thuẫn chỉ vì chạy thử thấy 0 dòng.

## 5. Điều kiện dư thừa: lặp ý nghĩa mà không lọc thêm

Điều kiện **dư thừa** là điều kiện có thể bỏ đi mà không thay đổi tập hàng được chọn trong ngữ cảnh và quy tắc đánh giá liên quan. Loại bỏ dư thừa giúp câu SQL rõ ý hơn; tuy nhiên không phải mọi biểu thức trông có vẻ lặp đều an toàn để xóa, nhất là khi có `NULL`, ép kiểu, collation hoặc hàm có tác dụng phụ.

### 5.1. Điều kiện mạnh hơn đã bao hàm điều kiện yếu hơn

~~~sql
WHERE tong_tien >= 100000
  AND tong_tien >= 200000
~~~

Với cột số, nếu `tong_tien >= 200000` đúng thì `tong_tien >= 100000` cũng đúng. Do đó biểu thức trên tương đương với:

~~~sql
WHERE tong_tien >= 200000
~~~

Tương tự:

~~~sql
-- Hai điều kiện:
WHERE tong_tien < 500000
   OR tong_tien < 800000
~~~

trong ngữ cảnh so sánh số thông thường có cùng tập hàng với:

~~~sql
WHERE tong_tien < 800000
~~~

Vế `< 500000` không bổ sung giá trị nào cho phép `OR` so với `< 800000`.

### 5.2. Điều kiện bằng đã hàm ý thuộc tập

~~~sql
WHERE trang_thai = 'MOI'
  AND trang_thai IN ('MOI', 'DA_THANH_TOAN')
~~~

Nếu một hàng có `trang_thai = 'MOI'`, nó cũng nằm trong tập của `IN`. Biểu thức có cùng tập hàng được `WHERE` giữ lại như:

~~~sql
WHERE trang_thai = 'MOI'
~~~

Ngược lại, nếu dùng `OR`:

~~~sql
WHERE trang_thai = 'MOI'
   OR trang_thai IN ('MOI', 'DA_THANH_TOAN')
~~~

thì điều kiện `= 'MOI'` bị điều kiện `IN` bao hàm, nên vế `OR` đầu dư thừa.

### 5.3. IS NOT NULL thường bị điều kiện so sánh bao hàm

~~~sql
WHERE tong_tien IS NOT NULL
  AND tong_tien > 0
~~~

Trong `WHERE`, `tong_tien > 0` chỉ nhận `TRUE` khi `tong_tien` khác `NULL`. Vì vậy có thể viết:

~~~sql
WHERE tong_tien > 0
~~~

Đây là phép rút gọn theo **tập hàng được lọc trong `WHERE`**. Không suy rộng thành “mọi biểu thức có `NULL` đều giống nhau” ở mọi ngữ cảnh; `NULL` có thể đổi kết quả của một biểu thức khi đi vào `NOT`, `OR`, phép gán, `CHECK` hoặc tính toán.

### 5.4. Những điều kiện tưởng dư thừa nhưng không phải

| Điều kiện | Có thể bỏ một vế không? | Lý do |
| --- | --- | --- |
| `tong_tien >= 100000 AND tong_tien <= 300000` | **Không** | Hai vế tạo khoảng có cận dưới và cận trên. |
| `to_chuc_id = 10 AND da_xoa = FALSE` | **Không** | Mỗi vế lọc theo một thuộc tính khác nhau. |
| `trang_thai = 'MOI' OR trang_thai = 'DA_THANH_TOAN'` | **Không** | Hai vế bao phủ hai nhóm giá trị khác nhau. |
| `trang_thai <> 'DA_HUY' OR trang_thai IS NULL` | **Không** | Vế thứ hai giữ lại `NULL` bị phép `<>` loại khỏi `WHERE`. |
| `tong_tien > 100000 AND tong_tien < 300000` | **Không** | Cả hai cận đều cần thiết. |
| `thoi_diem_tao >= moc_a AND thoi_diem_tao < moc_b` | **Không** | Hai cận tạo một khoảng thời gian nửa mở. |

### 5.5. Giản lược theo logic, không dựa vào kết quả ngẫu nhiên

Giả sử trong dữ liệu hiện tại tất cả đơn của tổ chức 10 đều có `da_xoa = FALSE`. Điều này **không có nghĩa**:

~~~sql
WHERE to_chuc_id = 10 AND da_xoa = FALSE
~~~

có thể giản lược vĩnh viễn thành `WHERE to_chuc_id = 10`. Ngày mai có thể có đơn xóa mềm. Chỉ được bỏ vế nếu có **bất biến thực sự** được bảo đảm bởi mô hình, ràng buộc, hoặc yêu cầu nghiệp vụ, không phải chỉ do tình cờ quan sát dữ liệu mẫu.

Tương tự, hai điều kiện chỉ trùng theo **giả định ngoài DB** có thể không trùng trên dữ liệu bẩn hoặc trong lúc migration. Cân nhắc nguồn bảo đảm trước khi rút gọn.

## 6. Logic ba giá trị: TRUE, FALSE và UNKNOWN

SQL sử dụng logic ba giá trị trong biểu thức điều kiện thông thường:

- `TRUE`: điều kiện đúng;
- `FALSE`: điều kiện sai;
- `UNKNOWN`: chưa thể xác định đúng/sai, thường xuất hiện khi so sánh với `NULL`.

Ví dụ:

~~~sql
SELECT
    NULL = 'MOI' AS so_sanh_bang,
    NULL <> 'MOI' AS so_sanh_khac,
    NULL IS NULL AS kiem_tra_null;
~~~

Hai phép `=` và `<>` trả `UNKNOWN` (thường hiển thị `NULL`), còn `NULL IS NULL` trả `TRUE`.

### 6.1. Bảng chân trị của AND và OR

Ký hiệu `T = TRUE`, `F = FALSE`, `U = UNKNOWN`:

| A | B | A AND B | A OR B |
| --- | --- | --- | --- |
| T | T | T | T |
| T | F | F | T |
| T | U | U | T |
| F | T | F | T |
| F | F | F | F |
| F | U | F | U |
| U | T | U | T |
| U | F | F | U |
| U | U | U | U |

`NOT TRUE = FALSE`, `NOT FALSE = TRUE`, và **`NOT UNKNOWN = UNKNOWN`**. Vì vậy phủ định một so sánh chứa `NULL` không tự biến nó thành `TRUE`.

### 6.2. NOT không có nghĩa “bao gồm các giá trị chưa biết”

Lấy những đơn khác trạng thái ĐÃ HỦY trong tổ chức 10, chưa xóa mềm:

~~~sql
SELECT id, trang_thai
FROM don_hang_loc
WHERE to_chuc_id = 10
  AND da_xoa = FALSE
  AND trang_thai <> 'DA_HUY'
ORDER BY id;
~~~

Kết quả là `101`, `102`, `108`. Dòng `104` có `trang_thai = NULL` bị loại, vì `NULL <> 'DA_HUY'` là `UNKNOWN`.

Nếu nghiệp vụ nói **“cho phép cả đơn chưa xác định trạng thái, chỉ loại ĐÃ HỦY”**, phải viết rõ:

~~~sql
SELECT id, trang_thai
FROM don_hang_loc
WHERE to_chuc_id = 10
  AND da_xoa = FALSE
  AND (
      trang_thai <> 'DA_HUY'
      OR trang_thai IS NULL
  )
ORDER BY id;
~~~

Lúc này kết quả có `101`, `102`, `104`, `108`.

PostgreSQL còn có phép so sánh null-safe:

~~~sql
SELECT id, trang_thai
FROM don_hang_loc
WHERE to_chuc_id = 10
  AND da_xoa = FALSE
  AND trang_thai IS DISTINCT FROM 'DA_HUY'
ORDER BY id;
~~~

`IS DISTINCT FROM` cho kết quả `TRUE`/`FALSE` theo ngữ nghĩa hai `NULL` được xem là không khác nhau, và **`NULL` khác một giá trị không `NULL`**. Nó giúp diễn đạt ý định bao gồm trạng thái thiếu khi lọc “khác ĐÃ HỦY”. Mức hỗ trợ và cú pháp so sánh null-safe có thể khác giữa các DBMS.

### 6.3. Phủ định và định luật De Morgan

Đối với biểu thức logic SQL thông thường, các phép đổi nhóm De Morgan vẫn đúng trong logic ba giá trị:

~~~sql
NOT (A OR B)  -- tương đương: (NOT A) AND (NOT B)
NOT (A AND B) -- tương đương: (NOT A) OR (NOT B)
~~~

Ví dụ:

~~~sql
WHERE NOT (
    trang_thai = 'MOI'
    OR trang_thai = 'DA_HUY'
)
~~~

tương đương về kết quả logic với:

~~~sql
WHERE trang_thai <> 'MOI'
  AND trang_thai <> 'DA_HUY'
~~~

**Cả hai đều loại hàng có `NULL`** khỏi `WHERE`, bởi các phép so sánh dẫn đến `UNKNOWN`. Không tự thêm ý nghĩa “các trạng thái khác kể cả chưa biết” khi phủ định; nếu muốn giữ `NULL`, phải thêm điều kiện `IS NULL` hoặc phép so sánh phù hợp.

## 7. NOT IN và bẫy NULL

`IN` hữu ích để viết gọn nhiều điều kiện `OR` trên cùng một biểu thức:

~~~sql
WHERE trang_thai IN ('MOI', 'DA_THANH_TOAN')
~~~

Nhưng `NOT IN` có một bẫy quan trọng khi **danh sách hoặc kết quả truy vấn con chứa `NULL`**.

~~~sql
-- Tưởng muốn lấy đơn có trạng thái khác MOI và DA_HUY:
SELECT id, trang_thai
FROM don_hang_loc
WHERE trang_thai NOT IN ('MOI', 'DA_HUY', NULL);
~~~

Với một trạng thái khác `MOI`/`DA_HUY`, phép so sánh còn lại với `NULL` tạo `UNKNOWN`. Do `NOT IN` về mặt logic tương đương phủ định việc thuộc tập, truy vấn trên **không trả hàng nào** trong dữ liệu mẫu. Với trạng thái `MOI` hoặc `DA_HUY`, `NOT IN` là `FALSE`; với các trạng thái khác, kết quả là `UNKNOWN`.

### 7.1. NOT IN (subquery) có thể bị một NULL làm vô hiệu hóa lọc

Giả sử có danh sách khách hàng bị chặn, trong đó một hàng chưa xác định mã:

~~~sql
CREATE TEMP TABLE khach_bi_chan (
    khach_hang_id INTEGER
);

INSERT INTO khach_bi_chan (khach_hang_id)
VALUES (2), (NULL);

SELECT id, khach_hang_id
FROM don_hang_loc
WHERE khach_hang_id NOT IN (
    SELECT khach_hang_id
    FROM khach_bi_chan
);
~~~

Kết quả **không có dòng**, dù chỉ có khách `2` thực sự được liệt kê với mã rõ ràng. Nguyên nhân là `NULL` trong tập con làm cho phép `NOT IN` đối với các mã không khớp `2` trở thành `UNKNOWN`.

Nếu yêu cầu là “không có một hàng chặn khớp mã khách”, `NOT EXISTS` thường diễn đạt chính xác và ổn định hơn:

~~~sql
SELECT d.id, d.khach_hang_id
FROM don_hang_loc AS d
WHERE NOT EXISTS (
    SELECT 1
    FROM khach_bi_chan AS b
    WHERE b.khach_hang_id = d.khach_hang_id
)
ORDER BY d.id;
~~~

Truy vấn này trả các đơn của khách **khác 2**, không bị hàng `NULL` trong `khach_bi_chan` làm mất kết quả. Trường hợp khóa phía ngoài có thể `NULL` cần xác định ý nghĩa riêng: `NOT EXISTS` dựa trên điều kiện khớp hàng, trong khi `NOT IN` có logic ba giá trị. Hai cách **không tự động tương đương** trong mọi tình huống.

Nếu vẫn dùng `NOT IN`, cần bảo đảm tập con không có `NULL` bằng thiết kế dữ liệu (`NOT NULL`) hoặc lọc thích hợp, đồng thời xử lý rõ giá trị `NULL` ở cột phía ngoài. Không dùng `COALESCE` với một giá trị giả một cách tùy tiện vì có thể gây xung đột với dữ liệu hợp lệ.

## 8. Điều kiện khoảng: BETWEEN, cận đóng và cận mở

Sai điều kiện khoảng có thể tạo **mâu thuẫn**, **dư thừa** hoặc **bỏ sót dữ liệu ở ranh giới**.

### 8.1. BETWEEN bao gồm cả hai đầu

~~~sql
SELECT id, tong_tien
FROM don_hang_loc
WHERE tong_tien BETWEEN 100000 AND 300000
ORDER BY id;
~~~

Với giá trị không `NULL`, biểu thức:

~~~sql
tong_tien BETWEEN 100000 AND 300000
~~~

thường tương đương:

~~~sql
tong_tien >= 100000 AND tong_tien <= 300000
~~~

Cả hai đầu `100000` và `300000` được bao gồm. Trên dữ liệu mẫu, các ID phù hợp là `102`, `103`, `104`, `105`, `107`. Nếu nghiệp vụ yêu cầu **nhỏ hơn 300000** thì `BETWEEN` không diễn đạt đúng; cần dùng `< 300000`.

### 8.2. Khoảng mâu thuẫn và khoảng rỗng

~~~sql
WHERE tong_tien >= 300000
  AND tong_tien < 100000
~~~

không thể đúng. Một biểu thức `BETWEEN 300000 AND 100000` cũng không có kết quả `TRUE` cho giá trị số thông thường vì cận dưới lớn hơn cận trên. Đừng tự đảo hai cận nếu chúng được nhập từ bộ lọc người dùng mà chưa xác định chính sách ứng dụng: có hệ thống cần **báo lỗi “từ lớn hơn đến”**, có hệ thống cho phép hoán đổi sau xác nhận.

### 8.3. Khoảng thời gian nên dùng cận trên mở

Giả sử muốn lấy **mọi đơn trong tháng 10/2026 theo giờ Việt Nam (UTC+07)**. Một cách viết dễ bỏ sót:

~~~sql
-- Không bao phủ cả ngày 31/10:
WHERE thoi_diem_tao BETWEEN
      '2026-10-01 00:00:00+07'::timestamptz
  AND '2026-10-31 00:00:00+07'::timestamptz
~~~

`BETWEEN` có tính bao gồm đầu cuối, nhưng cận cuối được viết ở **đầu ngày 31/10**, nên các đơn phát sinh sau 00:00 ngày đó bị loại.

Mẫu dễ dùng cho thời điểm:

~~~sql
SELECT id, thoi_diem_tao
FROM don_hang_loc
WHERE thoi_diem_tao >= '2026-10-01 00:00:00+07'::timestamptz
  AND thoi_diem_tao <  '2026-11-01 00:00:00+07'::timestamptz
ORDER BY thoi_diem_tao, id;
~~~

Đây là khoảng **nửa mở** `[bắt đầu, kết thúc)`: giữ mọi thời điểm từ đầu tháng 10 đến **trước** đầu tháng 11. Nó bao gồm các đơn `101` đến `107` trong dữ liệu mẫu, nhưng loại `108` đúng tại 00:00 ngày 01/11. Nếu cần lọc thêm tổ chức, xóa mềm hay trạng thái, bổ sung chúng bằng `AND` theo phạm vi nghiệp vụ.

Với múi giờ có thay đổi giờ mùa hè, cần tính **ranh giới ngày địa phương** trong múi giờ đúng rồi chuyển sang thời điểm để so sánh; không luôn giả định một ngày dài chính xác 24 giờ. Khi cột có chỉ mục, so sánh trực tiếp với cận thời gian thường thuận lợi hơn việc bọc cột bằng hàm `DATE(thoi_diem_tao)`, dù hiệu năng cuối cùng còn phụ thuộc kế hoạch thực thi.

## 9. AND và OR trong bộ lọc nhiều lựa chọn

Một bộ lọc UI thường có hai loại lựa chọn:

- **Giữa các nhóm thuộc tính khác nhau:** thường kết hợp bằng `AND`, ví dụ *thuộc tổ chức 10* **và** *chưa xóa mềm* **và** *nằm trong khoảng tiền*.
- **Giữa các giá trị có thể chấp nhận của cùng một thuộc tính:** thường kết hợp bằng `OR` hoặc `IN`, ví dụ trạng thái *MỚI hoặc ĐÃ THANH TOÁN*.

Ví dụ yêu cầu: “Tổ chức 10, chưa xóa mềm, đơn tạo trong tháng 10, và (kênh WEB hoặc tổng tiền từ 200.000 trở lên).”

~~~sql
SELECT id, kenh_ban, tong_tien
FROM don_hang_loc
WHERE to_chuc_id = 10
  AND da_xoa = FALSE
  AND thoi_diem_tao >= '2026-10-01 00:00:00+07'::timestamptz
  AND thoi_diem_tao <  '2026-11-01 00:00:00+07'::timestamptz
  AND (
      kenh_ban = 'WEB'
      OR tong_tien >= 200000
  )
ORDER BY id;
~~~

Kết quả theo bảng mẫu là `101`, `102`, `103`, `104`. Dòng `107` bị loại vì đã xóa mềm, `105` vì thuộc tổ chức 20, `108` vì ở đầu tháng 11.

Nếu bỏ ngoặc ở cuối:

~~~sql
WHERE to_chuc_id = 10
  AND da_xoa = FALSE
  AND thoi_diem_tao >= '2026-10-01 00:00:00+07'::timestamptz
  AND thoi_diem_tao <  '2026-11-01 00:00:00+07'::timestamptz
  AND kenh_ban = 'WEB'
  OR tong_tien >= 200000
~~~

vế `tong_tien >= 200000` sẽ đứng **ngoài toàn bộ chuỗi `AND` phía trước**. Khi đó các đơn ngoài tổ chức, đã xóa mềm hoặc ngoài thời gian vẫn có thể lọt vào nếu tổng tiền đủ lớn. **Ngoặc bảo vệ phạm vi lọc** khi có `OR`.

### 9.1. Điều kiện loại trừ nhiều giá trị

Nếu muốn trạng thái **khác cả MỚI lẫn ĐÃ HỦY**:

~~~sql
WHERE trang_thai <> 'MOI'
  AND trang_thai <> 'DA_HUY'
~~~

hoặc:

~~~sql
WHERE trang_thai NOT IN ('MOI', 'DA_HUY')
~~~

Hai cách có ngữ nghĩa tương đương cho các giá trị thông thường khi danh sách không chứa `NULL`; cả hai loại dòng `trang_thai = NULL` khỏi `WHERE`. Dùng `OR` ở đây là lỗi:

~~~sql
-- Sai ý nghĩa “khác cả hai”:
WHERE trang_thai <> 'MOI'
   OR trang_thai <> 'DA_HUY'
~~~

Với bất kỳ trạng thái **khác `NULL`**, ít nhất một vế trong hai phép `<>` sẽ đúng, vì một trạng thái không thể đồng thời bằng cả `MOI` và `DA_HUY`. Biểu thức lỗi hầu như không loại được trạng thái nào đã biết.

Đây là lỗi logic phổ biến: khi **loại nhiều giá trị**, dùng `AND` giữa các phép “khác”, còn khi **chấp nhận nhiều giá trị**, dùng `OR` giữa các phép “bằng”.

## 10. Bộ lọc tùy chọn và SQL được xây dựng từ ứng dụng

Ứng dụng thường cho phép nhập trạng thái, số tiền tối thiểu, kênh bán và thời gian mà không bắt buộc nhập tất cả. Việc ghép điều kiện động cần bảo đảm **bộ lọc bắt buộc luôn có hiệu lực**.

Ví dụ cú pháp **tham số đặt tên minh họa ở tầng thư viện/ORM** (không phải một câu lệnh PostgreSQL độc lập có thể chạy nguyên văn trong `psql`):

~~~sql
SELECT id, to_chuc_id, trang_thai, tong_tien
FROM don_hang_loc
WHERE to_chuc_id = :to_chuc_id
  AND da_xoa = FALSE
  AND (:trang_thai IS NULL OR trang_thai = :trang_thai)
  AND (:tong_tien_tu IS NULL OR tong_tien >= :tong_tien_tu);
~~~

Quy ước ví dụ: khi tham số `:trang_thai` là `NULL`, ứng dụng hiểu là **không áp dụng lọc trạng thái**; khi khác `NULL`, nó phải khớp cột `trang_thai`. Các dấu ngoặc bảo đảm mỗi `OR` chỉ thuộc **một bộ lọc tùy chọn**, không nới lỏng `to_chuc_id` hoặc `da_xoa`.

Điểm cần lưu ý:

- Cách dùng tham số `NULL` để **bỏ qua bộ lọc** khác với yêu cầu tìm **hàng có cột `NULL`**. Để tìm trạng thái chưa biết, cần một lựa chọn/filter riêng dùng `IS NULL`.
- Truy vấn kiểu `(:p IS NULL OR cot = :p)` có thể khó tối ưu với một số dữ liệu và DBMS; đôi khi tạo SQL có các điều kiện tùy chọn thực sự xuất hiện là phù hợp hơn. Dù chọn cách nào cũng phải bind **giá trị bằng tham số**, không nối trực tiếp dữ liệu do người dùng nhập.
- Nếu ứng dụng tạo điều kiện `OR` động, cần nhóm các nhánh ngay từ lúc xây dựng biểu thức. Tránh phụ thuộc vào việc ghép thêm chuỗi `AND ... OR ...` rồi hy vọng ưu tiên tự đúng.
- Bộ lọc phạm vi dữ liệu/định danh tổ chức phải được thực thi theo thiết kế quyền truy cập của hệ thống; việc đặt đúng ngoặc trong một truy vấn không thay thế toàn bộ cơ chế phân quyền.

## 11. WHERE, ON và HAVING: điều kiện được áp dụng ở giai đoạn nào?

Một điều kiện đúng về mặt cú pháp vẫn có thể trả kết quả sai nếu đặt ở **vị trí không phù hợp** trong câu SQL.

### 11.1. ON trong LEFT JOIN khác WHERE

Thêm một bảng thanh toán:

~~~sql
CREATE TEMP TABLE thanh_toan_loc (
    id INTEGER PRIMARY KEY,
    don_hang_id INTEGER NOT NULL REFERENCES don_hang_loc(id),
    ket_qua TEXT NOT NULL
);

INSERT INTO thanh_toan_loc (id, don_hang_id, ket_qua)
VALUES
    (201, 102, 'THANH_CONG'),
    (202, 105, 'THANH_CONG'),
    (203, 107, 'THAT_BAI');
~~~

Muốn lấy **mọi đơn chưa xóa mềm của tổ chức 10**, và hiển thị mã thanh toán thành công **nếu có**:

~~~sql
SELECT d.id AS don_hang_id, t.id AS thanh_toan_thanh_cong_id
FROM don_hang_loc AS d
LEFT JOIN thanh_toan_loc AS t
    ON t.don_hang_id = d.id
   AND t.ket_qua = 'THANH_CONG'
WHERE d.to_chuc_id = 10
  AND d.da_xoa = FALSE
ORDER BY d.id;
~~~

Ở đây, điều kiện `t.ket_qua = 'THANH_CONG'` nằm trong **`ON`**, nên các đơn **không có** thanh toán thành công vẫn xuất hiện với cột `t.id = NULL`.

Nếu chuyển điều kiện đó sang `WHERE`:

~~~sql
SELECT d.id AS don_hang_id, t.id AS thanh_toan_thanh_cong_id
FROM don_hang_loc AS d
LEFT JOIN thanh_toan_loc AS t
    ON t.don_hang_id = d.id
WHERE d.to_chuc_id = 10
  AND d.da_xoa = FALSE
  AND t.ket_qua = 'THANH_CONG'
ORDER BY d.id;
~~~

các đơn không có thanh toán sẽ bị loại vì so sánh trên cột `t.ket_qua = NULL` là `UNKNOWN`; truy vấn chỉ còn đơn `102`. Vậy **điều kiện trên bảng bên phải của LEFT JOIN trong WHERE** có thể làm mất tác dụng giữ hàng không khớp của `LEFT JOIN`.

Không có công thức “đưa mọi điều kiện vào ON” hay “mọi điều kiện vào WHERE” cho tất cả loại JOIN. Cần xác định muốn **lọc hàng của bảng chính**, **giới hạn hàng bên phải được ghép**, hay **chỉ lấy hàng có quan hệ khớp**.

### 11.2. WHERE lọc hàng; HAVING lọc nhóm

Yêu cầu: “Tìm khách có **ít nhất hai đơn chưa xóa mềm** trong tổ chức 10.”

~~~sql
SELECT
    khach_hang_id,
    COUNT(*) AS so_don
FROM don_hang_loc
WHERE to_chuc_id = 10
  AND da_xoa = FALSE
GROUP BY khach_hang_id
HAVING COUNT(*) >= 2
ORDER BY khach_hang_id;
~~~

`WHERE` chỉ đưa các đơn thuộc phạm vi vào phép nhóm. `HAVING` chọn những nhóm có số đơn đạt điều kiện. Với dữ liệu mẫu, khách hàng `1` có hai đơn (101 và 102) thỏa mãn.

Nếu nghiệp vụ yêu cầu “ít nhất hai đơn **đã thanh toán**”, phải thêm điều kiện trạng thái **trước khi đếm**, hoặc dùng hàm tổng hợp có điều kiện:

~~~sql
SELECT
    khach_hang_id,
    COUNT(*) AS so_don_da_thanh_toan
FROM don_hang_loc
WHERE to_chuc_id = 10
  AND da_xoa = FALSE
  AND trang_thai = 'DA_THANH_TOAN'
GROUP BY khach_hang_id
HAVING COUNT(*) >= 2;
~~~

Truy vấn này không có kết quả theo dữ liệu mẫu. Không nên lấy tổng số đơn của khách rồi nhầm thành số đơn đã thanh toán.

## 12. Tối ưu điều kiện nhưng phải bảo toàn ngữ nghĩa

Các biến đổi logic có thể làm câu SQL rõ hơn hoặc giúp bộ tối ưu hóa sử dụng chỉ mục, nhưng **tối ưu hiệu năng chỉ có giá trị khi kết quả vẫn đúng**.

### 12.1. Viết điều kiện trực tiếp trên cột khi có thể

~~~sql
-- Minh họa cách lọc theo ngày qua biểu thức trên cột:
SELECT id
FROM don_hang_loc
WHERE thoi_diem_tao::date = DATE '2026-10-03';
~~~

Trong PostgreSQL, việc ép `TIMESTAMPTZ` sang `DATE` còn phụ thuộc múi giờ của phiên; cách diễn đạt theo khoảng sẽ rõ mốc thời gian hơn khi nghiệp vụ chọn múi giờ cố định:

~~~sql
SELECT id
FROM don_hang_loc
WHERE thoi_diem_tao >= '2026-10-03 00:00:00+07'::timestamptz
  AND thoi_diem_tao <  '2026-10-04 00:00:00+07'::timestamptz;
~~~

So sánh trực tiếp cột với hai cận cũng thường thuận lợi cho chỉ mục B-tree thông thường hơn việc áp dụng hàm lên cột. Song nếu DBMS có expression index hoặc dữ liệu nhỏ, kế hoạch thực thi có thể khác; đừng đánh đồng “viết khác” với “luôn nhanh hơn”.

### 12.2. OR có thể được biểu diễn lại nhưng không tự đổi sang UNION tùy ý

Ví dụ:

~~~sql
WHERE to_chuc_id = 10
  AND (trang_thai = 'MOI' OR trang_thai = 'DA_THANH_TOAN')
~~~

với cột `trang_thai` đơn lẻ có thể viết:

~~~sql
WHERE to_chuc_id = 10
  AND trang_thai IN ('MOI', 'DA_THANH_TOAN')
~~~

Nhưng khi thay `OR` bằng hai câu `SELECT ... UNION ALL ...`, một hàng có thể thỏa **cả hai nhánh** và xuất hiện hai lần. `UNION` lại loại dòng trùng trong kết quả của hai nhánh, có thể thay đổi ngữ nghĩa số lần xuất hiện. Nếu dùng biến đổi ở mức tập kết quả, cần xem xét **duplicates, `NULL`, `ORDER BY` và số cột**.

### 12.3. Không mặc định SQL đánh giá điều kiện theo kiểu short-circuit

Trong một số ngôn ngữ lập trình, khi vế trái của `AND` là `FALSE`, vế phải thường không được thực thi. SQL **không cam kết một thứ tự đánh giá vật lý cố định cho mọi biểu thức `WHERE`**: bộ tối ưu hóa có thể sắp xếp lại điều kiện, thực thi một phần trước hoặc sau vì mục đích tối ưu.

Vì vậy không nên dựa vào:

~~~sql
-- Không coi thứ tự AND là biện pháp chắc chắn
-- ngăn mọi lỗi ép kiểu trong mọi DBMS:
WHERE chuoi_du_lieu ~ '^[0-9]+$'
  AND CAST(chuoi_du_lieu AS INTEGER) > 100
~~~

để khẳng định phép `CAST` **chắc chắn** chỉ chạy với dữ liệu hợp lệ. Trong PostgreSQL, cách phù hợp có thể là xây dựng biểu thức `CASE` có kiểm soát, làm sạch dữ liệu, lưu cột bằng kiểu đúng từ đầu, hoặc dùng hàm chuyển đổi an toàn mà DBMS hỗ trợ. Không nên dùng trình tự gõ điều kiện trong `WHERE` như cơ chế xử lý lỗi.

### 12.4. Các biểu thức không thuần có thể làm phép rút gọn trở nên không an toàn

Những ví dụ rút gọn ở phần trước áp dụng cho **so sánh thuần trên các cột/giá trị thông thường**. Nếu biểu thức gọi hàm biến đổi trạng thái, hàm sinh số ngẫu nhiên, hàm phụ thuộc thời gian hoặc phép ép kiểu có thể lỗi, việc gộp hoặc di chuyển biểu thức có thể thay đổi tác dụng thực thi. Với điều kiện SQL phức tạp, cần nắm tính chất của hàm và cách DBMS tối ưu, không biến đổi chỉ dựa trên phép đại số ký hiệu.

## 13. Quy trình thiết kế điều kiện lọc rõ nghĩa

Khi viết một truy vấn mới, có thể diễn đạt yêu cầu bằng các nhóm độc lập:

1. **Phạm vi bắt buộc:** tổ chức, quyền truy cập, trạng thái xóa mềm, dữ liệu hiện hành.
2. **Khoảng thời gian hoặc khoảng giá trị:** cận dưới/cận trên, loại cận đóng/mở, múi giờ.
3. **Lựa chọn thay thế:** các trạng thái được chấp nhận, kênh bán hoặc loại giao dịch; gom bằng `IN` hoặc `OR` trong ngoặc.
4. **Ngoại lệ `NULL`:** giá trị thiếu được giữ lại, loại đi hay báo dữ liệu chưa hoàn chỉnh?
5. **Mức chi tiết:** điều kiện áp dụng cho cùng một hàng, cho một nhóm hàng, hay cần `EXISTS` trên nhiều hàng liên quan?

Từ yêu cầu “đơn chưa xóa mềm của tổ chức 10, trong tháng 10, trạng thái MỚI hoặc ĐÃ THANH TOÁN, tổng tiền từ 100.000” có thể tạo biểu thức:

~~~sql
SELECT id, to_chuc_id, trang_thai, tong_tien
FROM don_hang_loc
WHERE to_chuc_id = 10
  AND da_xoa = FALSE
  AND thoi_diem_tao >= '2026-10-01 00:00:00+07'::timestamptz
  AND thoi_diem_tao <  '2026-11-01 00:00:00+07'::timestamptz
  AND trang_thai IN ('MOI', 'DA_THANH_TOAN')
  AND tong_tien >= 100000
ORDER BY id;
~~~

Với dữ liệu mẫu, câu trên trả **chỉ đơn 102**: đơn 101 có trạng thái MỚI nhưng dưới 100.000, đơn 107 đã xóa mềm, đơn 108 ngoài tháng 10; các đơn khác không thỏa những điều kiện còn lại.

Một cách nhìn bằng sơ đồ:

~~~mermaid
flowchart TD
    A["Tập đơn hàng nguồn"] --> B{"Đúng tổ chức và chưa xóa mềm?"}
    B -->|Không| X["Loại hàng"]
    B -->|Có| C{"Trong khoảng thời gian nửa mở?"}
    C -->|Không| X
    C -->|Có| D{"Trạng thái thuộc tập được chọn?"}
    D -->|Không hoặc UNKNOWN| X
    D -->|Có| E{"Đạt điều kiện số tiền?"}
    E -->|Không| X
    E -->|Có| F["Giữ hàng trong kết quả"]
~~~

Sơ đồ là cách giải thích logic để học; DBMS không nhất thiết chạy các phép kiểm tra theo thứ tự vật lý từ trên xuống.

## 14. Phân biệt mâu thuẫn, dư thừa và sai ưu tiên

| Dấu hiệu | Ví dụ | Hậu quả chính | Cách xử lý |
| --- | --- | --- | --- |
| **Mâu thuẫn** | `gia >= 200 AND gia < 100` | Không có hàng nào thỏa về mặt logic | Xác định lại cận đúng |
| **Mâu thuẫn trạng thái** | `status = 'MOI' AND status = 'DA_HUY'` | Không hàng nào có cùng lúc hai giá trị khác nhau | Xác định cần `OR` hay cần hai hàng/EXISTS |
| **Dư thừa** | `gia > 100 AND gia > 200` | Một vế không thu hẹp thêm kết quả | Giữ `gia > 200` |
| **Dư thừa theo tập** | `status = 'MOI' AND status IN ('MOI','DA_HUY')` | `IN` đã bị `=` bao hàm | Giữ điều kiện chính xác nhất |
| **Sai ưu tiên** | `tenant = 10 AND status = 'MOI' OR status = 'PAID'` | Có thể lấy dữ liệu ngoài tenant 10 | `tenant = 10 AND status IN (...)` |
| **Phủ định sai** | `status <> 'MOI' OR status <> 'DA_HUY'` | Gần như mọi trạng thái đã biết đều lọt qua | Dùng `AND` giữa hai phép `<>` |
| **NULL bất ngờ** | `status <> 'DA_HUY'` | Loại cả hàng `status IS NULL` | Quyết định có cần thêm `OR status IS NULL` |
| **NOT IN có NULL** | `id NOT IN (1, NULL)` | Các ID không phải 1 cũng có kết quả `UNKNOWN` | Dùng `NOT EXISTS` hoặc xử lý NULL rõ ràng |
| **Sai ranh giới** | `BETWEEN dau_thang AND dau_ngay_cuoi` | Bỏ sót phần lớn ngày cuối | Dùng khoảng thời gian nửa mở |
| **Sai vị trí lọc** | `LEFT JOIN ... WHERE bang_phai.col = ...` | Loại hàng không khớp ở bảng phải | Chọn `ON` hay `WHERE` theo mục tiêu |

## 15. Bài tập thực hành có lời giải

Các câu sau dùng bảng `don_hang_loc` ở mục 2, trừ khi ghi khác. Hãy tự dự đoán kết quả dựa trên ý nghĩa của điều kiện, không chỉ chạy thử và ghi nhận số dòng.

### Bài 1: Ưu tiên AND/OR

~~~sql
SELECT id
FROM don_hang_loc
WHERE to_chuc_id = 10
  AND trang_thai = 'MOI'
  OR trang_thai = 'DA_THANH_TOAN'
ORDER BY id;
~~~

**Câu hỏi:** Câu trên giữ những ID nào? Làm sao sửa để chỉ lấy tổ chức 10, trạng thái MỚI hoặc ĐÃ THANH TOÁN, và chưa xóa mềm?

**Lời giải:** Câu hiện tại giữ `101`, `102`, `105`, `107`, `108` do `AND` ưu tiên hơn `OR`. Sửa:

~~~sql
SELECT id
FROM don_hang_loc
WHERE to_chuc_id = 10
  AND da_xoa = FALSE
  AND trang_thai IN ('MOI', 'DA_THANH_TOAN')
ORDER BY id;
~~~

Kết quả: `101`, `102`, `108`.

### Bài 2: Phát hiện điều kiện mâu thuẫn

~~~sql
SELECT id
FROM don_hang_loc
WHERE tong_tien > 250000
  AND tong_tien <= 100000;
~~~

**Lời giải:** Không giá trị số nào đồng thời lớn hơn 250.000 và không vượt 100.000. Truy vấn vô nghiệm theo logic. Nếu yêu cầu thực tế là số tiền **nhỏ hơn hoặc bằng 100.000 hoặc lớn hơn 250.000**, cần:

~~~sql
WHERE tong_tien <= 100000
   OR tong_tien > 250000
~~~

Nhưng việc thay bằng `OR` chỉ đúng khi đó thật sự là yêu cầu của người dùng.

### Bài 3: Rút gọn điều kiện dư thừa

~~~sql
WHERE tong_tien >= 50000
  AND tong_tien >= 100000
  AND tong_tien > 200000
~~~

**Lời giải:** Với cột số thông thường, `tong_tien > 200000` đã bao hàm hai điều kiện còn lại. Có thể viết `WHERE tong_tien > 200000`. Nếu thêm `AND tong_tien < 300000`, vế mới **không dư thừa** vì nó đặt cận trên.

### Bài 4: NOT với hai giá trị loại trừ

~~~sql
SELECT id, trang_thai
FROM don_hang_loc
WHERE trang_thai <> 'MOI'
   OR trang_thai <> 'DA_HUY'
ORDER BY id;
~~~

**Câu hỏi:** Biểu thức đã loại cả trạng thái MỚI và ĐÃ HỦY chưa?

**Lời giải:** Chưa. Mọi trạng thái đã biết đều khác **ít nhất một** trong hai chuỗi, vì vậy được giữ. Dùng:

~~~sql
WHERE trang_thai <> 'MOI'
  AND trang_thai <> 'DA_HUY'
~~~

hoặc `WHERE trang_thai NOT IN ('MOI', 'DA_HUY')`. Cả hai tiếp tục **loại `NULL`**; nếu muốn giữ trạng thái chưa biết cần bổ sung `OR trang_thai IS NULL` với ngoặc đúng.

### Bài 5: Chọn NULL có chủ đích

Yêu cầu: “Chỉ đơn của tổ chức 10, chưa xóa mềm, **không phải ĐÃ HỦY**, kể cả đơn chưa biết trạng thái.” Viết điều kiện.

**Lời giải:**

~~~sql
SELECT id
FROM don_hang_loc
WHERE to_chuc_id = 10
  AND da_xoa = FALSE
  AND (
      trang_thai <> 'DA_HUY'
      OR trang_thai IS NULL
  )
ORDER BY id;
~~~

Kết quả `101`, `102`, `104`, `108`. Nếu bỏ `OR trang_thai IS NULL`, dòng 104 bị loại.

### Bài 6: NOT IN với NULL trong tập

~~~sql
SELECT id
FROM don_hang_loc
WHERE khach_hang_id NOT IN (2, NULL);
~~~

**Lời giải:** Không trả hàng trong bảng mẫu. Với khách ID 2, điều kiện là `FALSE`; với các khách khác, kết quả là `UNKNOWN` do thành phần `NULL`. Nếu yêu cầu chỉ loại khách `2`, viết `WHERE khach_hang_id <> 2` (ở đây cột `khach_hang_id` được khai báo `NOT NULL`). Khi danh sách đến từ bảng phụ, `NOT EXISTS` thường phù hợp nếu cần xét quan hệ không tồn tại.

### Bài 7: Khoảng thời gian

Yêu cầu lấy tất cả đơn phát sinh trong tháng 10/2026 theo UTC+07, bao gồm cả ngày 31/10 và không bao gồm 01/11. Điều kiện nào rõ nhất?

**Lời giải:**

~~~sql
WHERE thoi_diem_tao >= '2026-10-01 00:00:00+07'::timestamptz
  AND thoi_diem_tao <  '2026-11-01 00:00:00+07'::timestamptz
~~~

Khoảng nửa mở không bỏ sót thời điểm trong ngày cuối và không yêu cầu đoán độ chính xác tối đa của cột để đặt mốc `23:59:59.999...`.

### Bài 8: Một hàng hay nhiều hàng?

Yêu cầu: tìm khách hàng từng có ít nhất một đơn MỚI **và** ít nhất một đơn ĐÃ THANH TOÁN. Có thể dùng trên cùng một hàng `trang_thai = 'MOI' AND trang_thai = 'DA_THANH_TOAN'` không?

**Lời giải:** Không, vì một hàng không thể có đồng thời hai trạng thái khác nhau. Có thể dùng hai `EXISTS` theo `khach_hang_id`, mỗi nhánh tìm một **đơn có trạng thái tương ứng**, như ví dụ ở mục 4. Với dữ liệu mẫu, khách hàng `1` thỏa.

### Bài 9: Bộ lọc động

Giả sử thư viện ứng dụng dùng tham số `:trang_thai` và `:to_chuc_id`. Hãy sửa đoạn dễ sai:

~~~sql
WHERE to_chuc_id = :to_chuc_id
  AND :trang_thai IS NULL
  OR trang_thai = :trang_thai
~~~

**Lời giải:** Dùng:

~~~sql
WHERE to_chuc_id = :to_chuc_id
  AND (:trang_thai IS NULL OR trang_thai = :trang_thai)
~~~

Khi tham số trạng thái có giá trị, mọi hàng trả về vẫn phải thuộc đúng tổ chức. Với ứng dụng thực tế nên có thêm điều kiện quyền truy cập và xóa mềm theo thiết kế hệ thống; ví dụ chỉ minh họa ưu tiên toán tử.

### Bài 10: Lọc ở JOIN

Một báo cáo cần hiện tất cả đơn chưa xóa mềm của tổ chức 10, kèm mã thanh toán **thành công nếu có**. Nên đặt điều kiện `t.ket_qua = 'THANH_CONG'` trong `LEFT JOIN ... ON` hay `WHERE`?

**Lời giải:** Đặt trong `ON` của `LEFT JOIN` để giữ các đơn chưa có thanh toán thành công. Nếu đặt ở `WHERE`, hàng không khớp sẽ có `t.ket_qua = NULL` và bị loại. Nếu báo cáo **chỉ muốn đơn có thanh toán thành công**, đưa điều kiện vào `WHERE` hoặc dùng `INNER JOIN` có thể phù hợp hơn.

## 16. Ghi nhớ khi thiết kế và đọc điều kiện lọc

Một biểu thức SQL đúng cần đáp ứng đồng thời **logic của yêu cầu**, **ngữ nghĩa `NULL`**, **phạm vi dữ liệu** và **mức chi tiết hàng được lọc**.

- **Ưu tiên:** `NOT` cao hơn `AND`, `AND` cao hơn `OR`. Dùng ngoặc để thể hiện các lựa chọn thay thế và giữ phạm vi tổ chức, quyền truy cập, xóa mềm ở ngoài nhóm `OR`.
- **Mâu thuẫn:** một cột không thể đồng thời có hai giá trị khác nhau, hoặc một số không thể nằm trong khoảng cận dưới lớn hơn cận trên. Nếu cần “cùng khách từng có cả hai trạng thái”, phải xét **nhiều hàng**, không `AND` trên cùng một hàng.
- **Dư thừa:** điều kiện mạnh hơn có thể bao hàm điều kiện yếu hơn; chỉ rút gọn khi ngữ nghĩa được bảo đảm, không dựa vào dữ liệu tình cờ hiện có.
- **`NULL`:** `NOT` không biến `UNKNOWN` thành `TRUE`; `NOT IN` với `NULL` trong tập có thể khiến toàn bộ kết quả bị loại. Dùng `IS NULL`/`IS NOT NULL`, `NOT EXISTS` và phép so sánh null-safe khi phù hợp.
- **Khoảng:** `BETWEEN` bao gồm hai cận. Với timestamp, khoảng `>= start AND < end` thường diễn đạt ranh giới thời gian rõ hơn.
- **Vị trí điều kiện:** `ON`, `WHERE`, `HAVING` có vai trò khác nhau, đặc biệt với `LEFT JOIN` và truy vấn nhóm.

Khi kết quả SQL bất ngờ bằng 0 hoặc có thêm hàng không mong muốn, hãy đọc **toàn bộ biểu thức lọc đã được nhóm bằng ngoặc**, rồi tự hỏi từng hàng sẽ cho `TRUE`, `FALSE` hay `UNKNOWN`. Cách nhìn này giúp nhận ra điều kiện mâu thuẫn, dư thừa hoặc sai ưu tiên trước khi chúng trở thành lỗi dữ liệu trong ứng dụng.
