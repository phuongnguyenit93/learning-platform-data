# So sánh với NULL bằng IS NULL và IS NOT NULL

Trong SQL, `NULL` biểu thị **không có giá trị được biết hoặc được lưu tại vị trí đó**. Muốn tìm những bản ghi có giá trị `NULL`, hãy dùng `IS NULL`; muốn tìm những bản ghi có giá trị khác `NULL`, hãy dùng `IS NOT NULL`.

Đây là một khác biệt quan trọng so với cách so sánh các giá trị thông thường. Câu `column = NULL` không tương đương `column IS NULL`, và `column <> NULL` không tương đương `column IS NOT NULL`. Hai phép so sánh bằng `=` và khác `<>` với `NULL` cho kết quả *UNKNOWN* (không xác định) trong logic ba giá trị của SQL, dẫn đến việc bộ lọc `WHERE` loại bỏ những dòng mà người học tưởng rằng sẽ được chọn.

Bài học nằm trong chủ đề **Database SQL → NULL và logic**, tập trung vào cú pháp, ý nghĩa, kết quả truy vấn và các lỗi thường gặp của hai toán tử `IS NULL` và `IS NOT NULL`.

## 1. Hiểu đúng ý nghĩa của NULL

Xét một bảng công việc với cột `assignee` (người được giao việc) và `finished_at` (ngày hoàn thành):

- `assignee = 'An'`: đã ghi nhận người phụ trách là An.
- `assignee = NULL`: chưa có giá trị người phụ trách được lưu ở cột này. Có thể do chưa phân công, chưa biết hoặc dữ liệu chưa được nhập; ý nghĩa cụ thể phụ thuộc quy tắc nghiệp vụ.
- `assignee = ''`: đã lưu một **chuỗi rỗng**, khác `NULL` trong PostgreSQL và hầu hết các hệ quản trị SQL.
- `finished_at = NULL`: chưa có ngày hoàn thành được lưu. Điều này chưa chắc chứng minh công việc *chưa hoàn thành*, trừ khi hệ thống đã quy định như vậy.

Các trường hợp sau cũng không nên đồng nhất:

| Giá trị | Ý nghĩa dữ liệu | Có phải NULL? |
| --- | --- | --- |
| `NULL` | Thiếu/chưa biết giá trị | Có |
| `0` | Số không | Không |
| `''` | Chuỗi rỗng | Không, trong PostgreSQL |
| `' '` | Chuỗi chứa một khoảng trắng | Không |
| `FALSE` | Giá trị Boolean sai | Không |
| `'NULL'` | Chuỗi gồm bốn ký tự N-U-L-L | Không |

Ví dụ, một phép thống kê giá tiền cần phân biệt “giá bằng 0” với “chưa có giá”. Tương tự, trong bảng sinh viên, “chưa có điểm” không có nghĩa điểm bằng 0.

**Lưu ý về hệ quản trị:** ví dụ thực hành trong bài dùng **PostgreSQL**. Đặc biệt, Oracle Database thường coi chuỗi ký tự có độ dài bằng 0 là `NULL` trong nhiều ngữ cảnh chuỗi. Không áp quy tắc về chuỗi rỗng của PostgreSQL cho mọi cơ sở dữ liệu.

## 2. Tạo dữ liệu thực hành

Hãy mở một database thử nghiệm PostgreSQL, sau đó chạy **một lần** đoạn SQL sau. Tên bảng `null_lab_tasks` được chọn riêng cho bài này; nếu đã có bảng trùng tên, đừng chạy lại lệnh tạo bảng và chèn dữ liệu một cách vô thức.

~~~sql
CREATE TABLE null_lab_tasks (
    task_id INTEGER PRIMARY KEY,
    task_name VARCHAR(80) NOT NULL,
    assignee VARCHAR(40),
    finished_at DATE,
    priority INTEGER NOT NULL
);

INSERT INTO null_lab_tasks
    (task_id, task_name, assignee, finished_at, priority)
VALUES
    (1, 'Viet tai lieu',       'An',   NULL,              2),
    (2, 'Kiem thu API',        NULL,   DATE '2026-11-10', 1),
    (3, 'Thiet ke database',   'Binh', NULL,              3),
    (4, 'Cap nhat dashboard',  NULL,   NULL,              2),
    (5, 'Don dep du lieu',     '',     DATE '2026-11-12', 1);
~~~

Hai cột `assignee` và `finished_at` **được phép chứa `NULL`** vì phần khai báo không có `NOT NULL`. Cột `task_name` và `priority` bắt buộc có giá trị. Dấu `NULL` trong `INSERT` là từ khóa SQL; `'NULL'` có dấu nháy sẽ là một chuỗi.

Để xem dữ liệu:

~~~sql
SELECT task_id, task_name, assignee, finished_at, priority
FROM null_lab_tasks
ORDER BY task_id;
~~~

| task_id | task_name | assignee | finished_at | priority |
| ---: | --- | --- | --- | ---: |
| 1 | Viet tai lieu | An | `NULL` | 2 |
| 2 | Kiem thu API | `NULL` | 2026-11-10 | 1 |
| 3 | Thiet ke database | Binh | `NULL` | 3 |
| 4 | Cap nhat dashboard | `NULL` | `NULL` | 2 |
| 5 | Don dep du lieu | `''` (rỗng) | 2026-11-12 | 1 |

Tùy phần mềm quản lý database, một ô chứa `NULL` có thể được hiển thị bằng chữ `NULL`, nền mờ hoặc ô trống. **Đừng chỉ dựa vào giao diện ô trống để kết luận đó là `NULL`**: có thể ô đó chứa chuỗi rỗng. Hãy kiểm tra bằng biểu thức SQL.

## 3. Cú pháp và ý nghĩa của IS NULL

Cú pháp tổng quát:

~~~sql
<bieu_thuc> IS NULL
~~~

`IS NULL` là một **điều kiện kiểm tra có `NULL`** (*null predicate*). Nó trả về `TRUE` khi biểu thức có giá trị `NULL`; trả về `FALSE` khi biểu thức có giá trị khác `NULL`.

Ví dụ, tìm những công việc chưa có người phụ trách được lưu:

~~~sql
SELECT task_id, task_name, assignee
FROM null_lab_tasks
WHERE assignee IS NULL
ORDER BY task_id;
~~~

Kết quả:

| task_id | task_name | assignee |
| ---: | --- | --- |
| 2 | Kiem thu API | `NULL` |
| 4 | Cap nhat dashboard | `NULL` |

Chỉ hai dòng `task_id = 2` và `task_id = 4` thỏa điều kiện. Dòng 5 có `assignee = ''` nên **không** được chọn.

Một ví dụ khác: tìm công việc chưa ghi nhận ngày hoàn thành:

~~~sql
SELECT task_id, task_name
FROM null_lab_tasks
WHERE finished_at IS NULL
ORDER BY task_id;
~~~

Kết quả có các `task_id` là **1, 3, 4**. Lưu ý: đây là “chưa lưu ngày hoàn thành”; nếu ứng dụng muốn gọi chúng là “chưa hoàn thành”, cần có quy tắc dữ liệu bảo đảm mối liên hệ đó.

`IS NULL` cũng dùng được trong biểu thức của `SELECT`, chẳng hạn:

~~~sql
SELECT
    task_id,
    assignee,
    assignee IS NULL AS thieu_nguoi_phu_trach
FROM null_lab_tasks
ORDER BY task_id;
~~~

Trong PostgreSQL, cột `thieu_nguoi_phu_trach` trả về giá trị Boolean `TRUE` ở các dòng 2 và 4, `FALSE` ở các dòng 1, 3, 5. Tùy công cụ, kết quả Boolean có thể hiển thị thành `t/f` hoặc biểu diễn khác.

### IS NULL có thể kiểm tra một biểu thức

Đối tượng bên trái không bắt buộc chỉ là tên cột. Ví dụ:

~~~sql
SELECT task_id
FROM null_lab_tasks
WHERE NULLIF(assignee, '') IS NULL
ORDER BY task_id;
~~~

Trên PostgreSQL, hàm `NULLIF(assignee, '')` trả về `NULL` nếu `assignee` bằng chuỗi rỗng `''`, đồng thời vẫn giữ `NULL` ban đầu. Bởi vậy truy vấn này chọn **2, 4, 5**: hai dòng thiếu người phụ trách và một dòng có chuỗi rỗng.

Đó là quy tắc kiểm tra được **chủ ý mở rộng**; đừng ngầm xem mọi chuỗi rỗng là `NULL`. Nếu dữ liệu có khoảng trắng như `'   '`, `NULLIF(assignee, '')` vẫn không coi nó là chuỗi rỗng.

## 4. Cú pháp và ý nghĩa của IS NOT NULL

Cú pháp tổng quát:

~~~sql
<bieu_thuc> IS NOT NULL
~~~

`IS NOT NULL` trả về `TRUE` khi biểu thức **có giá trị khác `NULL`**, và `FALSE` khi biểu thức là `NULL`. Có thể hiểu đây là phủ định của `IS NULL` trên cùng biểu thức:

~~~sql
NOT (assignee IS NULL)
~~~

Ví dụ, tìm các công việc đã có một giá trị ở cột người phụ trách:

~~~sql
SELECT task_id, task_name, assignee
FROM null_lab_tasks
WHERE assignee IS NOT NULL
ORDER BY task_id;
~~~

Kết quả:

| task_id | task_name | assignee |
| ---: | --- | --- |
| 1 | Viet tai lieu | An |
| 3 | Thiet ke database | Binh |
| 5 | Don dep du lieu | `''` (rỗng) |

**Dòng 5 vẫn có mặt**, vì `IS NOT NULL` chỉ kiểm tra sự tồn tại của giá trị khác `NULL`; nó không kiểm tra tên có nội dung hay không.

Tìm những việc đã lưu ngày hoàn thành:

~~~sql
SELECT task_id, task_name, finished_at
FROM null_lab_tasks
WHERE finished_at IS NOT NULL
ORDER BY task_id;
~~~

Kết quả gồm công việc **2 và 5**. Hai toán tử `IS NULL` và `IS NOT NULL` chia dữ liệu thành hai tập không giao nhau, bao phủ toàn bộ các hàng đối với **một biểu thức đơn** trong ví dụ này.

Nếu cần “đã có tên không rỗng” trong PostgreSQL, điều kiện phải chặt chẽ hơn:

~~~sql
SELECT task_id, assignee
FROM null_lab_tasks
WHERE assignee IS NOT NULL
  AND assignee <> ''
ORDER BY task_id;
~~~

Chỉ còn **1 (An)** và **3 (Binh)**. Nếu khoảng trắng cũng được coi là tên không hợp lệ, cần xác định quy tắc chuẩn hóa, chẳng hạn `TRIM(assignee) <> ''` kết hợp với kiểm tra `IS NOT NULL`.

## 5. Vì sao không dùng = NULL hoặc <> NULL?

Với giá trị thông thường, `=` hỏi “có bằng nhau không?”, còn `<>` hỏi “có khác nhau không?”. Nhưng `NULL` không phải là một giá trị bình thường có thể so sánh trực tiếp theo cách đó.

Trong SQL, biểu thức như:

~~~sql
SELECT
    5 = NULL      AS so_sanh_bang,
    5 <> NULL     AS so_sanh_khac,
    NULL = NULL   AS hai_null_bang_nhau;
~~~

đều cho kết quả **UNKNOWN**; PostgreSQL thường hiển thị kết quả Boolean không xác định này bằng `NULL`. Điều này **không** có nghĩa ba biểu thức đều trả về `FALSE`.

So sánh với cách kiểm tra chuẩn:

~~~sql
SELECT
    NULL IS NULL         AS mot,   -- TRUE
    NULL IS NOT NULL     AS hai,   -- FALSE
    'An' IS NULL         AS ba,    -- FALSE
    'An' IS NOT NULL     AS bon;   -- TRUE
~~~

### Sai lầm phổ biến khi lọc trong WHERE

~~~sql
-- SAI: khong tim thay cac dong co assignee NULL.
SELECT task_id
FROM null_lab_tasks
WHERE assignee = NULL;
~~~

Trên dữ liệu mẫu, truy vấn trả về **0 dòng**, dù bảng có hai `assignee` là `NULL`. Nguyên nhân là `assignee = NULL` tạo `UNKNOWN` cho mọi hàng; điều kiện `WHERE` chỉ giữ những hàng có kết quả `TRUE`.

Sửa:

~~~sql
SELECT task_id
FROM null_lab_tasks
WHERE assignee IS NULL
ORDER BY task_id;
~~~

Kết quả là **2, 4**.

Tương tự, câu sau **không** tìm được các dòng có giá trị khác `NULL`:

~~~sql
-- SAI: UNKNOWN khong duoc WHERE giu lai.
SELECT task_id
FROM null_lab_tasks
WHERE assignee <> NULL;
~~~

Sửa:

~~~sql
SELECT task_id
FROM null_lab_tasks
WHERE assignee IS NOT NULL
ORDER BY task_id;
~~~

Kết quả là **1, 3, 5**.

### Bảng giá trị ba trạng thái

Trong điều kiện SQL, kết quả có thể là:

- **TRUE** — điều kiện đúng.
- **FALSE** — điều kiện sai.
- **UNKNOWN** — không thể kết luận TRUE hay FALSE từ giá trị đang có.

Đối với ví dụ kiểm tra một cột `x`:

| Giá trị của x | `x = 'An'` | `x <> 'An'` | `x = NULL` | `x IS NULL` | `x IS NOT NULL` |
| --- | --- | --- | --- | --- | --- |
| `'An'` | TRUE | FALSE | UNKNOWN | FALSE | TRUE |
| `'Binh'` | FALSE | TRUE | UNKNOWN | FALSE | TRUE |
| `NULL` | UNKNOWN | UNKNOWN | UNKNOWN | TRUE | FALSE |
| `''` | FALSE | TRUE | UNKNOWN | FALSE | TRUE |

**Quy tắc then chốt:** `IS NULL` và `IS NOT NULL` cho kết quả TRUE/FALSE rõ ràng; còn so sánh `= NULL` và `<> NULL` tạo UNKNOWN. Vì vậy cú pháp có chữ `IS` không thể được thay bằng toán tử bằng/khác.

## 6. UNKNOWN tương tác với WHERE, NOT, AND và OR như thế nào?

`WHERE` chỉ giữ các dòng có điều kiện cuối cùng là **TRUE**. Dòng có `FALSE` hoặc `UNKNOWN` đều bị loại.

~~~sql
SELECT task_id, assignee
FROM null_lab_tasks
WHERE assignee = 'An'
ORDER BY task_id;
~~~

Chỉ chọn dòng **1**. Dòng 2 và 4 có `assignee = NULL` cho kết quả UNKNOWN, nên không được giữ.

Điều kiện phủ định sau đây cũng **không** tự động đưa NULL quay lại:

~~~sql
-- Chi lay nhung gia tri khac 'An' va khong phai NULL.
SELECT task_id, assignee
FROM null_lab_tasks
WHERE NOT (assignee = 'An')
ORDER BY task_id;
~~~

Kết quả **3, 5**. Bởi vì `NOT UNKNOWN` vẫn là `UNKNOWN`, không phải TRUE. Nếu yêu cầu là “tất cả công việc không giao cho An, **kể cả chưa được phân công**”, viết tường minh:

~~~sql
SELECT task_id, assignee
FROM null_lab_tasks
WHERE assignee <> 'An'
   OR assignee IS NULL
ORDER BY task_id;
~~~

Kết quả **2, 3, 4, 5**.

Một số quy tắc logic ba giá trị:

| Biểu thức | Kết quả |
| --- | --- |
| `NOT UNKNOWN` | UNKNOWN |
| `TRUE AND UNKNOWN` | UNKNOWN |
| `FALSE AND UNKNOWN` | FALSE |
| `TRUE OR UNKNOWN` | TRUE |
| `FALSE OR UNKNOWN` | UNKNOWN |

Do vậy, khi viết nhiều điều kiện, hãy xác định rõ tập dữ liệu mong muốn thay vì dựa vào trực giác rằng “khác An” sẽ bao gồm cả hàng chưa biết người phụ trách.

### Kết hợp hai cột có thể NULL

Tìm việc **vừa chưa có người phụ trách, vừa chưa có ngày hoàn thành**:

~~~sql
SELECT task_id, task_name
FROM null_lab_tasks
WHERE assignee IS NULL
  AND finished_at IS NULL
ORDER BY task_id;
~~~

Chỉ có dòng **4**.

Tìm việc **thiếu ít nhất một trong hai thông tin**:

~~~sql
SELECT task_id, task_name
FROM null_lab_tasks
WHERE assignee IS NULL
   OR finished_at IS NULL
ORDER BY task_id;
~~~

Kết quả **1, 2, 3, 4**; dòng 5 không thỏa vì người phụ trách là chuỗi rỗng (khác NULL) và có ngày hoàn thành.

Khi kết hợp `AND` với `OR`, nên thêm dấu ngoặc để thể hiện chính xác yêu cầu, ví dụ “việc ưu tiên 2 và còn thiếu người phụ trách **hoặc** ngày hoàn thành”:

~~~sql
SELECT task_id
FROM null_lab_tasks
WHERE priority = 2
  AND (assignee IS NULL OR finished_at IS NULL)
ORDER BY task_id;
~~~

Kết quả **1, 4**. Nếu bỏ ngoặc, thứ tự ưu tiên toán tử `AND` trước `OR` có thể làm truy vấn chọn thêm những dòng ngoài mức ưu tiên 2.

## 7. IS NULL và IS NOT NULL trong các tác vụ thực tế

### 7.1. Đếm giá trị có và thiếu

`COUNT(*)` đếm tất cả hàng; `COUNT(column)` chỉ đếm các giá trị **khác NULL** trong cột tương ứng:

~~~sql
SELECT
    COUNT(*) AS tong_cong_viec,
    COUNT(assignee) AS co_gia_tri_assignee
FROM null_lab_tasks;
~~~

Kết quả:

| tong_cong_viec | co_gia_tri_assignee |
| ---: | ---: |
| 5 | 3 |

`COUNT(assignee)` đếm cả chuỗi rỗng của dòng 5 vì nó không phải `NULL`. Có thể đếm hai nhóm bằng bộ lọc:

~~~sql
SELECT
    COUNT(*) AS thieu_nguoi_phu_trach
FROM null_lab_tasks
WHERE assignee IS NULL;
~~~

Kết quả **2**.

~~~sql
SELECT
    COUNT(*) AS da_co_gia_tri
FROM null_lab_tasks
WHERE assignee IS NOT NULL;
~~~

Kết quả **3**. Hai số cộng lại bằng tổng số hàng **5**.

Trong PostgreSQL, có thể đếm cả hai nhóm trong một câu bằng cú pháp `FILTER`:

~~~sql
SELECT
    COUNT(*) FILTER (WHERE assignee IS NULL) AS so_null,
    COUNT(*) FILTER (WHERE assignee IS NOT NULL) AS so_khac_null
FROM null_lab_tasks;
~~~

Kết quả `so_null = 2` và `so_khac_null = 3`. `FILTER` không được hỗ trợ giống nhau ở mọi hệ quản trị; hai truy vấn `WHERE` ở trên dễ chuyển đổi hơn.

### 7.2. Gắn nhãn hiển thị bằng CASE

Khi cần hiển thị tình trạng dữ liệu, có thể dùng `CASE` kết hợp hai kiểm tra:

~~~sql
SELECT
    task_id,
    assignee,
    CASE
        WHEN assignee IS NULL THEN 'Chua co gia tri'
        WHEN assignee = '' THEN 'Chuoi rong'
        ELSE 'Da co ten'
    END AS tinh_trang_assignee
FROM null_lab_tasks
ORDER BY task_id;
~~~

Kết quả tương ứng:

| task_id | tinh_trang_assignee |
| ---: | --- |
| 1 | Da co ten |
| 2 | Chua co gia tri |
| 3 | Da co ten |
| 4 | Chua co gia tri |
| 5 | Chuoi rong |

Thứ tự nhánh `WHEN` hữu ích ở đây: bạn kiểm tra `NULL` trước, sau đó phân biệt chuỗi rỗng với chuỗi có nội dung.

### 7.3. Dùng COALESCE để hiển thị giá trị thay thế

`COALESCE` trả về đối số đầu tiên khác `NULL`. Đây là cách hiển thị một nhãn mặc định mà vẫn giữ giá trị `NULL` trong bảng:

~~~sql
SELECT
    task_id,
    COALESCE(assignee, '[Chua phan cong]') AS hien_thi_assignee
FROM null_lab_tasks
ORDER BY task_id;
~~~

Dòng 2 và 4 hiện `[Chua phan cong]`, còn dòng 5 vẫn hiển thị chuỗi rỗng. `COALESCE` không thay đổi dữ liệu lưu trữ và **không tương đương** phép kiểm tra `IS NULL` khi mục đích là lọc hàng.

### 7.4. Kiểm tra NULL trước khi UPDATE

Nếu yêu cầu là chỉ gán người phụ trách cho công việc chưa có giá trị ở cột này, hãy xác định dòng được chọn bằng `SELECT`:

~~~sql
SELECT task_id, assignee
FROM null_lab_tasks
WHERE task_id = 4
  AND assignee IS NULL;
~~~

Kết quả gồm một dòng, `task_id = 4`. Trong database thử nghiệm PostgreSQL, có thể thử cập nhật trong transaction rồi hoàn tác:

~~~sql
BEGIN;

UPDATE null_lab_tasks
SET assignee = 'Chi'
WHERE task_id = 4
  AND assignee IS NULL;

SELECT task_id, assignee
FROM null_lab_tasks
WHERE task_id = 4;

ROLLBACK;
~~~

Giữa `UPDATE` và `ROLLBACK`, dòng 4 có người phụ trách là Chi **trong transaction hiện tại**. Sau `ROLLBACK`, thay đổi chưa commit được hủy; dữ liệu mẫu quay về trạng thái ban đầu.

Điều kiện `assignee IS NULL` giúp giới hạn thao tác theo đúng ý định, nhưng không tự bảo đảm toàn bộ quy tắc nghiệp vụ hay xử lý mọi vấn đề đồng thời. Với `DELETE`, kiểm tra bằng `SELECT` và xác định phạm vi thay đổi còn quan trọng hơn.

### 7.5. Kiểm tra NULL trên kết quả JOIN

Giả sử muốn liệt kê những công việc chưa có ngày hoàn thành:

~~~sql
SELECT task_id, task_name
FROM null_lab_tasks
WHERE finished_at IS NULL
ORDER BY task_id;
~~~

`IS NULL` ở đây kiểm tra một **cột thực có thể NULL**. Trong câu truy vấn `LEFT JOIN`, `IS NULL` còn thường được sử dụng để tìm dòng **không ghép được** với bảng bên phải:

~~~sql
-- Vi du cau truc tong quat; khong can tao bang moi de hoc cu phap.
SELECT p.parent_id
FROM parent_table AS p
LEFT JOIN child_table AS c
    ON c.parent_id = p.parent_id
WHERE c.child_id IS NULL;
~~~

Mẫu trên có ý nghĩa “lấy bản ghi cha không có bản ghi con khớp”, **nếu** `c.child_id` là cột khóa không thể `NULL` khi có dòng con thực sự, và điều kiện nối đúng. Nếu kiểm tra cột nullable không phải khóa ở bảng con, một bản ghi con có tồn tại nhưng giá trị cột đó là `NULL` cũng có thể khiến kết quả bị hiểu nhầm là “không có dòng con”.

## 8. Các lỗi dễ mắc và cách sửa

| Viết dễ nhầm | Vấn đề | Cách phù hợp |
| --- | --- | --- |
| `WHERE assignee = NULL` | So sánh với NULL tạo UNKNOWN, không chọn dòng cần tìm | `WHERE assignee IS NULL` |
| `WHERE assignee <> NULL` | Không chọn dòng khác NULL | `WHERE assignee IS NOT NULL` |
| `WHERE NOT (assignee = 'An')` với ý định bao gồm cả chưa phân công | NULL cho UNKNOWN, phủ định vẫn UNKNOWN | `WHERE assignee <> 'An' OR assignee IS NULL` |
| `IS NOT NULL` được hiểu là “không rỗng” | Chuỗi `''` vẫn khác NULL trong PostgreSQL | Thêm `assignee <> ''`, và có thể thêm kiểm tra khoảng trắng |
| Đếm `COUNT(assignee)` rồi cho rằng đó là số người khác nhau | Đếm số ô khác NULL, kể cả chuỗi rỗng và giá trị trùng | Xác định mục tiêu: `COUNT(DISTINCT assignee)` nếu muốn số giá trị phân biệt khác NULL; cân nhắc dữ liệu rỗng |
| Dùng `COALESCE` như thể đã điền dữ liệu thiếu vào bảng | `COALESCE` chỉ trả về giá trị của một biểu thức | Dùng để trình bày, hoặc `UPDATE` có điều kiện nếu thực sự muốn thay dữ liệu |
| Kết luận “chưa hoàn thành” từ `finished_at IS NULL` mà không có quy tắc | NULL chỉ nói rằng chưa lưu ngày | Xác nhận quy ước dữ liệu, hoặc dùng cột trạng thái nghiệp vụ phù hợp |

Một lỗi liên quan đến logic NULL là `NOT IN` khi danh sách hoặc truy vấn con có thể chứa `NULL`. Ví dụ trong PostgreSQL:

~~~sql
SELECT task_id
FROM null_lab_tasks
WHERE task_id NOT IN (1, NULL);
~~~

Câu này **không** trả về các ID khác 1 như suy luận thông thường: với các ID khác 1, kết quả còn liên quan so sánh với `NULL` nên là UNKNOWN; ID 1 là FALSE. Nếu thực sự chỉ muốn loại ID 1, hãy dùng `task_id <> 1`. Với truy vấn con, thường cần cân nhắc `NOT EXISTS` hoặc loại bỏ `NULL` đúng theo ý nghĩa dữ liệu. Đây là lý do phải nghĩ về khả năng chứa `NULL` khi kết hợp các toán tử.

## 9. Bài tập thực hành và đáp án

Các bài sau dùng nguyên dữ liệu năm dòng ở mục 2. Nếu bạn đã `COMMIT` những thay đổi thử nghiệm, số dòng có thể khác; hãy dùng dữ liệu mẫu mới khi cần đối chiếu.

**Bài 1 — Tìm việc chưa có ngày hoàn thành**

Viết câu `SELECT` trả về `task_id` và `task_name` của các dòng có `finished_at` là `NULL`, sắp theo ID tăng dần.

**Đáp án bài 1**

~~~sql
SELECT task_id, task_name
FROM null_lab_tasks
WHERE finished_at IS NULL
ORDER BY task_id;
~~~

Kết quả ID: **1, 3, 4**.

**Bài 2 — Tìm việc đã có người phụ trách theo nghĩa khác NULL**

Trả về các ID mà `assignee` khác `NULL`. Dòng có chuỗi rỗng có xuất hiện không?

**Đáp án bài 2**

~~~sql
SELECT task_id, assignee
FROM null_lab_tasks
WHERE assignee IS NOT NULL
ORDER BY task_id;
~~~

Kết quả ID: **1, 3, 5**. Dòng 5 vẫn xuất hiện vì `''` khác `NULL` trong PostgreSQL.

**Bài 3 — Tìm việc thiếu cả người phụ trách và ngày hoàn thành**

Viết điều kiện dùng cả `IS NULL` và `AND`.

**Đáp án bài 3**

~~~sql
SELECT task_id
FROM null_lab_tasks
WHERE assignee IS NULL
  AND finished_at IS NULL;
~~~

Kết quả ID: **4**.

**Bài 4 — Sửa truy vấn không ra dòng nào**

Truy vấn bên dưới không lấy được việc chưa phân công:

~~~sql
SELECT task_id
FROM null_lab_tasks
WHERE assignee = NULL;
~~~

Vì sao? Hãy sửa đúng một toán tử.

**Đáp án bài 4**

`= NULL` tạo UNKNOWN cho từng dòng, trong khi `WHERE` chỉ giữ TRUE. Sửa bằng:

~~~sql
SELECT task_id
FROM null_lab_tasks
WHERE assignee IS NULL;
~~~

Kết quả ID: **2, 4**.

**Bài 5 — Chọn tất cả việc không giao cho An, kể cả chưa biết người phụ trách**

Yêu cầu cụ thể: nhận cả tên khác An, chuỗi rỗng và `NULL`, nhưng không nhận người phụ trách là An.

**Đáp án bài 5**

~~~sql
SELECT task_id
FROM null_lab_tasks
WHERE assignee <> 'An'
   OR assignee IS NULL
ORDER BY task_id;
~~~

Kết quả ID: **2, 3, 4, 5**. Chỉ dùng `<> 'An'` sẽ bỏ dòng 2 và 4 vì kết quả so sánh với NULL là UNKNOWN.

**Bài 6 — Kiểm tra số lượng**

Với dữ liệu mẫu, hãy dự đoán ba con số sau trước khi chạy:

~~~sql
SELECT
    COUNT(*) AS tong,
    COUNT(assignee) AS khac_null,
    COUNT(*) FILTER (WHERE assignee IS NULL) AS null_count
FROM null_lab_tasks;
~~~

**Đáp án bài 6**

`tong = 5`, `khac_null = 3`, `null_count = 2`. Cột `assignee` có ba ô khác NULL (gồm chuỗi rỗng), hai ô NULL.

## 10. Ghi nhớ và áp dụng

| Muốn kiểm tra | Điều kiện SQL | Ý nghĩa |
| --- | --- | --- |
| Giá trị đang là NULL | `expression IS NULL` | TRUE chỉ khi biểu thức là NULL |
| Giá trị không phải NULL | `expression IS NOT NULL` | TRUE chỉ khi biểu thức khác NULL |
| Không bằng một giá trị cụ thể, **không bao gồm NULL** | `column <> 'An'` | Các dòng NULL cho UNKNOWN và bị WHERE bỏ |
| Không bằng một giá trị cụ thể, **bao gồm NULL** | `column <> 'An' OR column IS NULL` | Đưa dòng NULL vào bằng điều kiện tường minh |
| Có nội dung không rỗng (PostgreSQL) | `column IS NOT NULL AND column <> ''` | Loại NULL và chuỗi rỗng, chưa loại chuỗi toàn dấu cách |

Khi thấy `NULL`, hãy đặt câu hỏi: **“Cần tìm bản ghi thiếu giá trị, bản ghi đã có giá trị hay cần so sánh hai giá trị thông thường?”** Nếu cần kiểm tra có/không có giá trị, chọn `IS NULL` hoặc `IS NOT NULL`. Đồng thời nhớ rằng **UNKNOWN không được bộ lọc WHERE giữ lại**, và “khác NULL” không đồng nghĩa “dữ liệu đầy đủ, hợp lệ theo nghiệp vụ”.
