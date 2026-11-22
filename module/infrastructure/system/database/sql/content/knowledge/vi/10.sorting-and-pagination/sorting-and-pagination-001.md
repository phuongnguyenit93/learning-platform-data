# ORDER BY với một cột và nhiều cột

Trong SQL, một bảng lưu các hàng dữ liệu nhưng **không cam kết thứ tự đọc các hàng**. Muốn xem danh sách từ điểm cao xuống thấp, từ ngày cũ đến ngày mới, hoặc nhóm theo khu vực rồi sắp xếp trong từng nhóm, ta dùng mệnh đề `ORDER BY` trong câu `SELECT`.

Sắp xếp theo **một cột** giúp trả lời câu hỏi như “Ai có điểm cao nhất?”. Sắp xếp theo **nhiều cột** giải quyết những tình huống có nhiều hàng bằng nhau theo tiêu chí đầu tiên, chẳng hạn “Điểm cao hơn đứng trước; nếu bằng điểm, người tham gia sớm hơn đứng trước; nếu vẫn bằng nhau, dùng mã thành viên để xác định thứ tự”. Cơ chế thứ hai đặc biệt quan trọng khi **phân trang** bằng `LIMIT` và `OFFSET`, vì thứ tự không ổn định có thể khiến các trang chứa hàng lặp hoặc bỏ sót.

Bài học thuộc **Database SQL → Sắp xếp và phân trang**. Ví dụ sử dụng PostgreSQL; những khác biệt về `NULL` và cú pháp phân trang của một số hệ quản trị khác được giải thích rõ ở phần cuối.

## 1. ORDER BY quyết định thứ tự kết quả như thế nào?

Cú pháp thông dụng:

~~~sql
SELECT cot_1, cot_2
FROM ten_bang
WHERE dieu_kien
ORDER BY cot_1 ASC;
~~~

`ORDER BY` xuất hiện sau `WHERE`, `GROUP BY` và `HAVING` nếu các mệnh đề này có mặt. Trong truy vấn thông thường, nó xác định **thứ tự các dòng được trả về**:

| Thành phần | Ý nghĩa |
| --- | --- |
| `ORDER BY` | Bắt đầu danh sách tiêu chí sắp xếp |
| `cot_1` | Cột hoặc biểu thức được dùng làm khóa sắp xếp |
| `ASC` | Sắp xếp tăng dần; thường là mặc định nếu không viết hướng |
| `DESC` | Sắp xếp giảm dần |
| `, cot_2 ...` | Tiêu chí tiếp theo dùng khi các tiêu chí trước đó bằng nhau |
| `NULLS FIRST` / `NULLS LAST` | Điều khiển vị trí giá trị `NULL` ở hệ hỗ trợ, như PostgreSQL |

Điều quan trọng: `ORDER BY` **không thay đổi thứ tự lưu vật lý của bảng** và cũng không cập nhật giá trị dữ liệu. Đây là cách yêu cầu hệ quản trị **trình bày tập kết quả** theo thứ tự mong muốn.

### Vì sao không nên dựa vào thứ tự tự nhiên?

~~~sql
SELECT member_id, full_name
FROM lab_order_members_126;
~~~

Nếu không có `ORDER BY`, kết quả có thể trông như thứ tự `INSERT`, thứ tự khóa chính hoặc một thứ tự khác. Những hiện tượng đó **không phải cam kết của SQL**. Cấu trúc chỉ mục, bộ tối ưu truy vấn, thao tác cập nhật, số lượng hàng hoặc kế hoạch chạy song song có thể làm thứ tự thay đổi.

Ngay cả khi một lần chạy trả về “đúng thứ tự mong muốn”, truy vấn vẫn cần `ORDER BY` nếu người dùng hoặc quy trình phía sau phụ thuộc vào thứ tự.

## 2. Chuẩn bị dữ liệu thực hành

Hãy dùng một database PostgreSQL thử nghiệm và tạo bảng `lab_order_members_126`. Đoạn dưới đây dành cho **lần chạy đầu tiên**, khi bảng chưa tồn tại:

~~~sql
CREATE TABLE lab_order_members_126 (
    member_id INTEGER PRIMARY KEY,
    full_name VARCHAR(80) NOT NULL,
    region VARCHAR(20) NOT NULL,
    score INTEGER CHECK (score BETWEEN 0 AND 100),
    joined_on DATE NOT NULL
);

INSERT INTO lab_order_members_126
    (member_id, full_name, region, score, joined_on)
VALUES
    (1,  'An',    'North',   90, DATE '2026-08-02'),
    (2,  'Binh',  'North',   90, DATE '2026-07-20'),
    (3,  'Chi',   'South',   75, DATE '2026-07-21'),
    (4,  'Dung',  'North',   75, DATE '2026-08-01'),
    (5,  'Ha',    'South',   90, DATE '2026-08-02'),
    (6,  'Lan',   'South',   75, DATE '2026-08-03'),
    (7,  'Minh',  'North', NULL, DATE '2026-07-28'),
    (8,  'Nga',   'South', NULL, DATE '2026-07-29'),
    (9,  'Phuc', 'Central',  95, DATE '2026-08-02'),
    (10, 'Trang','Central',  90, DATE '2026-07-20');
~~~

Bảng có **10 người**; điểm có thể trùng nhau và có hai hàng chưa có điểm (`NULL`). `member_id` là khóa chính nên không có hai người cùng mã. Cột ngày tham gia `joined_on` lưu kiểu `DATE` thật, thuận tiện để minh họa sắp xếp thời gian.

Để xem dữ liệu theo một thứ tự đã xác định:

~~~sql
SELECT member_id, full_name, region, score, joined_on
FROM lab_order_members_126
ORDER BY member_id ASC;
~~~

| member_id | full_name | region | score | joined_on |
| ---: | --- | --- | ---: | --- |
| 1 | An | North | 90 | 2026-08-02 |
| 2 | Binh | North | 90 | 2026-07-20 |
| 3 | Chi | South | 75 | 2026-07-21 |
| 4 | Dung | North | 75 | 2026-08-01 |
| 5 | Ha | South | 90 | 2026-08-02 |
| 6 | Lan | South | 75 | 2026-08-03 |
| 7 | Minh | North | `NULL` | 2026-07-28 |
| 8 | Nga | South | `NULL` | 2026-07-29 |
| 9 | Phuc | Central | 95 | 2026-08-02 |
| 10 | Trang | Central | 90 | 2026-07-20 |

Trong suốt bài, các bảng kết quả mô tả **dữ liệu khởi tạo nêu trên**. Nếu thay đổi hoặc thêm hàng trong quá trình luyện tập, kết quả sẽ thay đổi tương ứng.

## 3. ORDER BY một cột: ASC và DESC

### 3.1. Tăng dần bằng ASC

Ví dụ lấy các thành viên từ mã nhỏ đến lớn:

~~~sql
SELECT member_id, full_name
FROM lab_order_members_126
ORDER BY member_id ASC;
~~~

Kết quả có `member_id` lần lượt là **1, 2, 3, 4, 5, 6, 7, 8, 9, 10**. Vì mã thành viên là duy nhất, không tồn tại trường hợp hai hàng ngang nhau theo khóa sắp xếp này.

Trong SQL, `ASC` thường có thể bỏ:

~~~sql
SELECT member_id, full_name
FROM lab_order_members_126
ORDER BY member_id;
~~~

Truy vấn trên có cùng hướng tăng dần theo `member_id`.

### 3.2. Giảm dần bằng DESC

~~~sql
SELECT member_id, full_name
FROM lab_order_members_126
ORDER BY member_id DESC;
~~~

Kết quả có các ID: **10, 9, 8, 7, 6, 5, 4, 3, 2, 1**.

`ASC` và `DESC` áp dụng cho cột hoặc biểu thức ngay trước chúng, không thay đổi nội dung cột.

### 3.3. Sắp xếp điểm số theo một cột

~~~sql
SELECT member_id, full_name, score
FROM lab_order_members_126
ORDER BY score DESC NULLS LAST;
~~~

Trên PostgreSQL, câu này đưa điểm cao lên trước và đưa `NULL` xuống cuối:

| Nhóm điểm theo thứ tự | Các member_id thuộc nhóm |
| --- | --- |
| 95 | 9 |
| 90 | 1, 2, 5, 10 |
| 75 | 3, 4, 6 |
| `NULL` | 7, 8 |

**Chưa thể dự đoán thứ tự giữa các ID trong cùng nhóm điểm.** Chẳng hạn `1, 2, 5, 10` đều đạt 90, nên hệ quản trị có thể trả bốn hàng đó theo nhiều thứ tự khác nhau mà vẫn đúng câu `ORDER BY score DESC NULLS LAST`.

Nếu muốn thứ tự duy nhất cho mọi hàng, cần bổ sung một khóa sắp xếp nữa (mục 4).

### 3.4. Sắp xếp ngày

~~~sql
SELECT member_id, full_name, joined_on
FROM lab_order_members_126
ORDER BY joined_on ASC;
~~~

Ngày cũ hơn đứng trước ngày mới hơn. Hai người cùng ngày `2026-07-20` (Bình, Trang) vẫn có thể hoán đổi vị trí, vì mới có một khóa sắp xếp. Nếu muốn người có ngày mới nhất ở trên, đổi thành `ORDER BY joined_on DESC`.

Với cột có kiểu `DATE`, database so sánh theo giá trị ngày. Nếu ngày được lưu dưới dạng chuỗi không nhất quán như `'2/8/2026'` và `'10/7/2026'`, sắp xếp văn bản có thể không đúng thứ tự thời gian. Nên dùng đúng kiểu `DATE` hoặc `TIMESTAMP` thay vì kỳ vọng `ORDER BY` tự hiểu mọi định dạng chuỗi.

## 4. ORDER BY nhiều cột: ưu tiên từ trái sang phải

Cú pháp:

~~~sql
SELECT ...
FROM ...
ORDER BY cot_1 ASC, cot_2 DESC, cot_3 ASC;
~~~

Hệ quản trị xét **`cot_1` trước**. Chỉ khi hai hàng có giá trị khóa sắp xếp đầu giống nhau (hoặc cùng thuộc nhóm `NULL` theo quy tắc sắp xếp) mới dùng `cot_2`. Nếu hai hàng vẫn hòa ở tiêu chí thứ hai, mới xét `cot_3`, cứ tiếp tục như vậy.

Hình dung như xếp một danh sách theo thứ tự ưu tiên:

~~~text
1. So sanh cot_1
   |-- khac nhau --> xac dinh thu tu ngay
   +-- bang nhau --> so sanh cot_2
                      |-- khac nhau --> xac dinh thu tu
                      +-- bang nhau --> so sanh cot_3
                                         ...
~~~

Các tiêu chí phía sau **không lấn át** tiêu chí ở phía trước. Đây chính là nguyên tắc quan trọng nhất của `ORDER BY` nhiều cột.

### 4.1. Điểm giảm dần, rồi mã thành viên tăng dần

~~~sql
SELECT member_id, full_name, score
FROM lab_order_members_126
ORDER BY
    score DESC NULLS LAST,
    member_id ASC;
~~~

Kết quả:

| Vị trí | member_id | full_name | score |
| ---: | ---: | --- | ---: |
| 1 | 9 | Phuc | 95 |
| 2 | 1 | An | 90 |
| 3 | 2 | Binh | 90 |
| 4 | 5 | Ha | 90 |
| 5 | 10 | Trang | 90 |
| 6 | 3 | Chi | 75 |
| 7 | 4 | Dung | 75 |
| 8 | 6 | Lan | 75 |
| 9 | 7 | Minh | `NULL` |
| 10 | 8 | Nga | `NULL` |

Lý do:

- Thành viên 9 có điểm **95**, cao nhất nên đứng đầu.
- Nhóm điểm **90** được phân biệt bằng `member_id ASC`: 1, 2, 5, 10.
- Nhóm điểm **75** có thứ tự 3, 4, 6.
- Hai hàng `score IS NULL` được đặt cuối và có thứ tự 7, 8 theo mã thành viên.

Vì `member_id` là **khóa duy nhất** và nằm cuối danh sách sắp xếp, câu này xác định thứ tự của mọi hàng trong dữ liệu mẫu, kể cả các hàng hòa điểm.

### 4.2. Điểm cao trước; nếu bằng điểm, người tham gia sớm trước

~~~sql
SELECT member_id, full_name, score, joined_on
FROM lab_order_members_126
ORDER BY
    score DESC NULLS LAST,
    joined_on ASC,
    member_id ASC;
~~~

Thứ tự ID:

~~~text
9, 2, 10, 1, 5, 3, 4, 6, 7, 8
~~~

Giải thích vài vị trí quan trọng:

- ID **9** đạt 95 điểm nên vẫn đứng đầu dù tham gia không sớm nhất.
- Trong nhóm **90 điểm**, ID 2 và 10 cùng tham gia ngày `2026-07-20` nên được xếp trước ID 1 và 5 (ngày `2026-08-02`).
- Hai người ID 2 và 10 cùng điểm và cùng ngày, nên `member_id ASC` quyết định thứ tự **2 trước 10**.
- Nhóm **75 điểm** có ngày lần lượt `2026-07-21` (ID 3), `2026-08-01` (ID 4), `2026-08-03` (ID 6).
- Nhóm điểm `NULL` đứng cuối; ID 7 có ngày `2026-07-28` nên trước ID 8 (`2026-07-29`).

Ở đây, cột `joined_on` **không** được xét giữa một người 90 điểm và một người 75 điểm. Dù người 75 điểm tham gia sớm hơn, tiêu chí **điểm** được ưu tiên nên người 90 điểm vẫn đứng trước.

### 4.3. Nhóm theo khu vực, rồi sắp điểm trong khu vực

~~~sql
SELECT member_id, full_name, region, score
FROM lab_order_members_126
ORDER BY
    region ASC,
    score DESC NULLS LAST,
    member_id ASC;
~~~

Với các nhãn tiếng Anh `Central`, `North`, `South` trong dữ liệu mẫu, thứ tự nhóm theo quy tắc chữ cái thông thường là:

| Nhóm khu vực | Thứ tự ID trong nhóm |
| --- | --- |
| Central | 9 (95), 10 (90) |
| North | 1 (90), 2 (90), 4 (75), 7 (`NULL`) |
| South | 5 (90), 3 (75), 6 (75), 8 (`NULL`) |

Chú ý: `ORDER BY region, score DESC` **không** có nghĩa “sắp toàn bộ người theo điểm rồi mới nhóm khu vực”. Tiêu chí đứng đầu là `region`, vì vậy **mọi** người ở nhóm Central xuất hiện trước nhóm North trong thứ tự chữ cái ví dụ này, dù có ai ở North đạt điểm cao hơn người ở Central.

Thứ tự văn bản còn phụ thuộc **collation** của database/cột/truy vấn. Trong những cơ sở dữ liệu dùng collation đặc biệt, thứ tự chữ có dấu, chữ hoa/chữ thường hoặc một số chuỗi có thể khác trực giác. Khi cần kết quả so sánh tái hiện chính xác giữa các môi trường, hãy nêu rõ yêu cầu collation và kiểm tra hệ quản trị đang dùng.

## 5. ASC và DESC là tùy chọn riêng cho từng tiêu chí

Trong danh sách nhiều cột, từng cột có thể có hướng sắp xếp riêng:

~~~sql
ORDER BY region ASC, score DESC, member_id ASC
~~~

Đây là thứ tự: khu vực tăng dần; **trong cùng khu vực** điểm giảm dần; **trong cùng khu vực và cùng điểm** mã tăng dần.

Một số cách viết gần giống nhau nhưng khác kết quả:

| Mệnh đề | Cách hiểu |
| --- | --- |
| `ORDER BY score ASC, member_id ASC` | Điểm thấp trước; hòa điểm thì ID nhỏ trước |
| `ORDER BY score DESC, member_id ASC` | Điểm cao trước; hòa điểm thì ID nhỏ trước |
| `ORDER BY score DESC, member_id DESC` | Điểm cao trước; hòa điểm thì ID lớn trước |
| `ORDER BY joined_on ASC, score DESC` | Người tham gia sớm trước; trong cùng ngày, điểm cao trước |
| `ORDER BY score DESC, joined_on ASC` | Người điểm cao trước; trong cùng điểm, ngày cũ trước |

**Thứ tự liệt kê cột là một phần ngữ nghĩa của truy vấn.** Đổi chỗ `joined_on` và `score` có thể tạo danh sách khác, ngay cả khi đều dùng đúng `ASC` và `DESC`.

Nếu không viết `ASC`/`DESC` cho một tiêu chí, tiêu chí đó dùng hướng mặc định `ASC`:

~~~sql
-- Tuong duong trong SQL thong thuong.
ORDER BY region, score DESC, member_id;

ORDER BY region ASC, score DESC, member_id ASC;
~~~

Không nên diễn giải `ORDER BY region, score DESC, member_id` thành “cả ba cột đều giảm dần”: `DESC` chỉ đi với `score`.

## 6. Xử lý NULL khi sắp xếp

`NULL` biểu thị giá trị không có hoặc chưa biết. Khi sắp xếp, bạn phải xác định liệu những hàng thiếu điểm sẽ đứng đầu hay cuối.

Trong **PostgreSQL**, quy tắc mặc định là:

| Cách viết | Vị trí `NULL` mặc định ở PostgreSQL |
| --- | --- |
| `ORDER BY score ASC` | `NULL` cuối (`NULLS LAST`) |
| `ORDER BY score DESC` | `NULL` đầu (`NULLS FIRST`) |
| `ORDER BY score ASC NULLS FIRST` | `NULL` đầu, được yêu cầu tường minh |
| `ORDER BY score DESC NULLS LAST` | `NULL` cuối, được yêu cầu tường minh |

Ví dụ:

~~~sql
SELECT member_id, full_name, score
FROM lab_order_members_126
ORDER BY score DESC;
~~~

Trên PostgreSQL, hai thành viên **Minh và Nga** có điểm `NULL` thuộc nhóm đầu của kết quả, trước điểm 95. Thứ tự giữa hai hàng này không được xác định khi chỉ sắp một cột.

Nếu yêu cầu là “người có điểm cao nhất đứng đầu, người chưa có điểm đứng cuối”, hãy **ghi tường minh**:

~~~sql
SELECT member_id, full_name, score
FROM lab_order_members_126
ORDER BY score DESC NULLS LAST, member_id ASC;
~~~

Với truy vấn nhiều cột, vị trí `NULLS FIRST` hay `NULLS LAST` được gắn với **từng biểu thức**:

~~~sql
ORDER BY region ASC,
         score DESC NULLS LAST,
         joined_on ASC,
         member_id ASC
~~~

Ở đây các hàng có điểm `NULL` nằm cuối **trong từng khu vực**, còn thứ tự chung vẫn phụ thuộc `region`.

### 6.1. Nếu hệ quản trị không hỗ trợ NULLS FIRST/LAST?

Một cách kiểm soát thứ tự theo ý nghĩa dữ liệu, được nhiều hệ quản trị hỗ trợ, là sắp xếp bằng biểu thức `CASE`:

~~~sql
SELECT member_id, full_name, score
FROM lab_order_members_126
ORDER BY
    CASE WHEN score IS NULL THEN 1 ELSE 0 END ASC,
    score DESC,
    member_id ASC;
~~~

Biểu thức `CASE` trả về `0` cho điểm đã biết và `1` cho điểm `NULL`; do đó các hàng có điểm nằm trước. Tiếp theo, `score DESC` xếp điểm cao trước trong nhóm có điểm. `member_id ASC` phân định những hàng bằng nhau.

Đừng mặc định rằng tất cả cơ sở dữ liệu đều đặt `NULL` cùng phía: PostgreSQL thường xem `NULL` lớn hơn giá trị không-NULL cho mục đích `ORDER BY` mặc định, trong khi MySQL, SQL Server và SQLite thường đưa `NULL` lên đầu khi sắp tăng dần. Cú pháp `NULLS FIRST/LAST` cũng không được hỗ trợ giống nhau giữa các hệ.

### 6.2. COALESCE có phải luôn là cách thay NULL khi sắp xếp?

Có thể viết:

~~~sql
ORDER BY COALESCE(score, -1) DESC, member_id ASC
~~~

Vì ví dụ có `CHECK (score BETWEEN 0 AND 100)`, `-1` nằm dưới mọi điểm hợp lệ. Nhưng cách này biến `NULL` thành một **giá trị giả trong biểu thức sắp xếp**. Nếu miền giá trị có thể chứa số âm hoặc thay đổi sau này, cách thay thế có thể gây sai thứ tự.

Khi muốn phân biệt rõ giá trị thiếu và giá trị thật, `NULLS LAST` (ở hệ hỗ trợ) hoặc biểu thức `CASE WHEN score IS NULL ...` thường diễn đạt ý định dễ đọc hơn.

## 7. Sắp xếp theo biểu thức, cột không hiển thị và bí danh

`ORDER BY` không nhất thiết dùng một tên cột gốc. Nó có thể tham chiếu một biểu thức hoặc tên cột kết quả.

### 7.1. Sắp xếp theo biểu thức tính toán

Giả sử cần ưu tiên người có điểm cao, nhưng muốn xem điểm được nhân hệ số 10:

~~~sql
SELECT
    member_id,
    full_name,
    score,
    score * 10 AS weighted_score
FROM lab_order_members_126
ORDER BY score * 10 DESC NULLS LAST, member_id ASC;
~~~

Khi `score IS NULL`, biểu thức `score * 10` cũng là `NULL`. Nếu hệ số giống nhau và dương cho mọi hàng, thứ tự theo `score * 10` tương ứng thứ tự theo `score`; đây chỉ là ví dụ cho thấy **biểu thức có thể là khóa sắp xếp**.

### 7.2. Sắp xếp theo bí danh cột kết quả

~~~sql
SELECT
    member_id,
    full_name,
    score * 10 AS weighted_score
FROM lab_order_members_126
ORDER BY weighted_score DESC NULLS LAST, member_id ASC;
~~~

Trong PostgreSQL, `ORDER BY` có thể dùng bí danh `weighted_score` được khai báo trong danh sách `SELECT`. Cách này tránh lặp lại biểu thức `score * 10` trong mệnh đề sắp xếp.

**Bí danh cột kết quả** khác với **bí danh bảng**:

~~~sql
SELECT m.member_id, m.full_name, m.score AS exam_score
FROM lab_order_members_126 AS m
ORDER BY exam_score DESC NULLS LAST, m.member_id ASC;
~~~

`m` là tên tạm của **bảng**, còn `exam_score` là tên của **cột kết quả**. Chúng có phạm vi và cách sử dụng khác nhau.

### 7.3. Có thể sắp theo cột không nằm trong SELECT

Với `SELECT` thông thường trên PostgreSQL:

~~~sql
SELECT member_id, full_name
FROM lab_order_members_126
ORDER BY joined_on DESC, member_id ASC;
~~~

`joined_on` không được hiển thị nhưng vẫn tham gia xác định thứ tự. Đây là cách giữ giao diện gọn khi người xem không cần thấy toàn bộ tiêu chí sắp xếp.

Một số trường hợp có `SELECT DISTINCT`, phép tập hợp như `UNION` hoặc các quy tắc SQL riêng có giới hạn đối với biểu thức `ORDER BY` được phép sử dụng. Ví dụ PostgreSQL yêu cầu biểu thức sắp xếp của `SELECT DISTINCT` phải xuất hiện trong danh sách `SELECT`. Không suy rộng khả năng sắp theo cột ẩn của truy vấn đơn giản sang mọi dạng truy vấn.

### 7.4. Sắp xếp theo vị trí cột: đọc được nhưng dễ vỡ

PostgreSQL và nhiều hệ quản trị hỗ trợ `ORDER BY 2 DESC, 1 ASC` để chỉ các cột **thứ hai và thứ nhất** trong danh sách `SELECT`:

~~~sql
SELECT member_id, score
FROM lab_order_members_126
ORDER BY 2 DESC NULLS LAST, 1 ASC;
~~~

Ở đây `2` có nghĩa cột kết quả `score`, `1` là cột `member_id`. Tuy nhiên, chỉ cần đổi vị trí cột trong `SELECT` là ngữ nghĩa sắp xếp đổi theo. Trong bài học và các truy vấn cần bảo trì, nên ưu tiên **tên cột hoặc bí danh rõ nghĩa**.

## 8. ORDER BY kết hợp WHERE, GROUP BY và LIMIT

### 8.1. Lọc trước, sắp xếp tập kết quả sau

Yêu cầu: chỉ xem người ở khu vực North, ưu tiên điểm cao:

~~~sql
SELECT member_id, full_name, region, score
FROM lab_order_members_126
WHERE region = 'North'
ORDER BY score DESC NULLS LAST, member_id ASC;
~~~

Kết quả có các ID **1, 2, 4, 7**. `WHERE` chọn đúng các hàng khu vực North; `ORDER BY` sắp **tập hàng được chọn** theo điểm và ID.

Một lỗi tư duy thường gặp là “ORDER BY chỉ trả về các hàng ở đầu bảng”. Không phải vậy: `ORDER BY` chỉ xếp thứ tự, **không giới hạn số hàng**. Muốn lấy một số hàng đầu cần dùng `LIMIT`, `FETCH` hoặc `TOP` tùy SQL dialect.

### 8.2. Sắp xếp các nhóm sau GROUP BY

Ví dụ đếm người theo khu vực rồi xếp khu vực đông người trước:

~~~sql
SELECT
    region,
    COUNT(*) AS member_count
FROM lab_order_members_126
GROUP BY region
ORDER BY member_count DESC, region ASC;
~~~

Kết quả:

| region | member_count |
| --- | ---: |
| North | 4 |
| South | 4 |
| Central | 2 |

`COUNT(*)` tạo ra một giá trị cho mỗi nhóm `region`. `ORDER BY member_count DESC` xếp nhóm có nhiều người trước; `region ASC` phân định nhóm North và South khi cùng có bốn người.

Ở đây `ORDER BY` được áp dụng lên **kết quả sau khi tổng hợp**, vì truy vấn có `GROUP BY`. Nếu sắp theo một biểu thức tổng hợp khác, có thể viết trực tiếp như `ORDER BY COUNT(*) DESC` khi dialect hỗ trợ.

## 9. ORDER BY và phân trang: cần một thứ tự xác định

Phân trang là lấy một phần của một danh sách lớn. Ví dụ người dùng xem ba hàng trên mỗi trang. Với PostgreSQL, có thể dùng `LIMIT` và `OFFSET`:

~~~sql
SELECT member_id, full_name, score, joined_on
FROM lab_order_members_126
ORDER BY
    score DESC NULLS LAST,
    joined_on ASC,
    member_id ASC
LIMIT 3 OFFSET 0;
~~~

**Trang 1** gồm các ID: **9, 2, 10**.

Trang kế tiếp bỏ qua ba hàng đầu của cùng thứ tự:

~~~sql
SELECT member_id, full_name, score, joined_on
FROM lab_order_members_126
ORDER BY
    score DESC NULLS LAST,
    joined_on ASC,
    member_id ASC
LIMIT 3 OFFSET 3;
~~~

**Trang 2** gồm các ID: **1, 5, 3**.

Nếu trang 3, dùng `LIMIT 3 OFFSET 6`, nhận các ID **4, 6, 7**. Trang 4 (`OFFSET 9`) còn ID **8**.

| Trang | `LIMIT` | `OFFSET` | ID theo thứ tự |
| ---: | ---: | ---: | --- |
| 1 | 3 | 0 | 9, 2, 10 |
| 2 | 3 | 3 | 1, 5, 3 |
| 3 | 3 | 6 | 4, 6, 7 |
| 4 | 3 | 9 | 8 |

Công thức khi đánh số trang từ 1:

~~~text
OFFSET = (page_number - 1) * page_size
~~~

Đây là ví dụ để hiểu cách kết hợp `ORDER BY` và phân trang. Trong ứng dụng, `page_size` và `page_number` cần được kiểm tra giới hạn; không nên cho phép kích thước trang hoặc offset bất hợp lý.

### 9.1. Vì sao phải thêm khóa duy nhất cuối ORDER BY?

Giả sử dùng chỉ:

~~~sql
ORDER BY score DESC NULLS LAST
LIMIT 3 OFFSET 3
~~~

Nhiều người cùng có điểm 90. Nếu thứ tự giữa họ thay đổi qua các lần chạy, một hàng có thể xuất hiện ở trang này trong lần truy vấn đầu và ở trang khác trong lần truy vấn kế. Thêm `member_id ASC` ở cuối giúp biến thứ tự thành **xác định cho một trạng thái dữ liệu cố định**, vì `member_id` là duy nhất.

Nếu đã dùng `joined_on` làm tiêu chí thứ hai, nó vẫn chưa đủ: ID 2 và 10 cùng điểm 90 và cùng ngày `2026-07-20`; ID 1 và 5 cũng cùng điểm 90 và ngày `2026-08-02`. Khóa `member_id` giải quyết các trường hợp còn hòa này.

**Một lưu ý quan trọng:** thêm khóa duy nhất giúp loại bỏ **thứ tự tùy ý giữa các hàng bằng nhau**, nhưng **không khóa cố định dữ liệu qua các lần tải trang**. Khi một người mới được thêm, bị xóa hoặc điểm thay đổi giữa lần xem trang 1 và trang 2, phân trang theo `OFFSET` vẫn có thể lặp/bỏ sót hàng do dữ liệu bị dịch vị trí. Hệ thống cần cơ chế phù hợp như cùng snapshot giao dịch hoặc **phân trang theo khóa/cursor** (*keyset pagination*) khi yêu cầu tính nhất quán cao.

### 9.2. Kết quả giới hạn hàng không đồng nghĩa thứ tự tùy ý là chấp nhận được

~~~sql
-- Co the tra 3 hang, nhung khong xac dinh '3 hang dau' theo nghia nao.
SELECT member_id, full_name
FROM lab_order_members_126
LIMIT 3;
~~~

Với `LIMIT` mà không có `ORDER BY`, không có cơ sở để gọi ba hàng trả về là “ba người mới nhất” hoặc “ba điểm cao nhất”. Phải định nghĩa rõ tiêu chí sắp xếp rồi mới cắt trang.

## 10. ORDER BY trong truy vấn con và phạm vi kết quả cuối

Để yêu cầu **thứ tự đầu ra cuối cùng**, hãy đặt `ORDER BY` tại cấp truy vấn trả kết quả cho người dùng:

~~~sql
SELECT m.member_id, m.full_name, m.score
FROM (
    SELECT member_id, full_name, score
    FROM lab_order_members_126
    WHERE score IS NOT NULL
) AS m
ORDER BY m.score DESC, m.member_id ASC;
~~~

Viết `ORDER BY` trong truy vấn con không phải là lời bảo đảm chung rằng mọi câu truy vấn bên ngoài tự động giữ thứ tự ấy. Khi truy vấn ngoài tiếp tục `JOIN`, tổng hợp hay xử lý dữ liệu, thứ tự cần thiết cho **đầu ra cuối** vẫn phải được xác định ở `ORDER BY` ngoài.

Một trường hợp khác là truy vấn con có `ORDER BY ... LIMIT` để **chọn** các hàng “top N” trước khi dùng ở truy vấn ngoài. Khi đó việc sắp trong truy vấn con có ý nghĩa đối với **việc chọn hàng**, nhưng thứ tự hiển thị cuối cùng vẫn nên được khai báo riêng.

## 11. Cân nhắc hiệu năng khi sắp xếp nhiều cột

Khi dữ liệu nhỏ, `ORDER BY` hầu như không gây khó khăn. Nhưng với hàng triệu dòng, database có thể phải thu thập nhiều hàng, sắp xếp trong bộ nhớ hoặc dùng không gian tạm. Kết hợp nhiều tiêu chí, phép tính phức tạp và `OFFSET` lớn có thể làm thời gian truy vấn tăng.

Trong PostgreSQL, một chỉ mục theo thứ tự các khóa có thể **hỗ trợ** một số truy vấn sắp xếp:

~~~sql
-- Minh hoa chi muc co thu tu khop truy van diem / ngay / ID.
CREATE INDEX lab_members_126_sort_idx
ON lab_order_members_126 (
    score DESC NULLS LAST,
    joined_on ASC,
    member_id ASC
);
~~~

Chỉ mục trên là một **thay đổi cấu trúc thật** nếu được chạy. Nó có thể hỗ trợ truy vấn như:

~~~sql
SELECT member_id, full_name, score, joined_on
FROM lab_order_members_126
ORDER BY
    score DESC NULLS LAST,
    joined_on ASC,
    member_id ASC
LIMIT 20;
~~~

Tuy nhiên, tạo chỉ mục **không bảo đảm** bộ tối ưu luôn sử dụng nó. Kế hoạch còn phụ thuộc bộ lọc, số hàng, thống kê, chi phí đọc bảng, kiểu chỉ mục và cả hướng sắp xếp từng cột. Mỗi chỉ mục còn tốn dung lượng và chi phí duy trì khi ghi dữ liệu. Trên bảng thực hành chỉ có 10 hàng, PostgreSQL hoàn toàn có thể chọn quét bảng và sắp xếp thay vì dùng chỉ mục.

Để quan sát kế hoạch mà không chạy một câu có tác động, PostgreSQL hỗ trợ:

~~~sql
EXPLAIN
SELECT member_id, full_name, score
FROM lab_order_members_126
ORDER BY score DESC NULLS LAST, joined_on ASC, member_id ASC
LIMIT 3;
~~~

Kế hoạch là thông tin chẩn đoán; nó không thay đổi quy tắc kết quả mà `ORDER BY` yêu cầu. Còn `EXPLAIN ANALYZE` sẽ thực sự thực thi truy vấn; chỉ dùng với tác vụ được phép chạy.

## 12. Khác biệt giữa các hệ quản trị SQL

Ý tưởng `ORDER BY cot_1 ASC, cot_2 DESC` rất phổ biến, nhưng cú pháp phân trang và vị trí `NULL` mặc định có thể khác:

| Hệ quản trị | Sắp xếp nhiều cột | Phân trang phổ biến | NULL mặc định khi ASC |
| --- | --- | --- | --- |
| PostgreSQL | `ORDER BY a ASC, b DESC` | `LIMIT n OFFSET m` hoặc `OFFSET ... FETCH` | Thường cuối |
| MySQL | `ORDER BY a ASC, b DESC` | `LIMIT n OFFSET m` | Thường đầu |
| SQLite | `ORDER BY a ASC, b DESC` | `LIMIT n OFFSET m` | Thường đầu |
| SQL Server | `ORDER BY a ASC, b DESC` | `ORDER BY ... OFFSET m ROWS FETCH NEXT n ROWS ONLY` | Thường đầu |
| Oracle Database | `ORDER BY a ASC, b DESC` | `OFFSET m ROWS FETCH NEXT n ROWS ONLY` (các phiên bản hiện đại) | Thường cuối |

PostgreSQL, SQLite và Oracle hiện đại hỗ trợ cú pháp `NULLS FIRST` / `NULLS LAST` trong ngữ cảnh sắp xếp thích hợp; các phiên bản MySQL và SQL Server phổ biến không hỗ trợ trực tiếp cú pháp đó. Vì vậy các ví dụ `NULLS LAST` trong bài phải được điều chỉnh khi chuyển hệ quản trị.

Ví dụ phân trang trong **SQL Server**:

~~~sql
SELECT member_id, full_name, score
FROM dbo.members
ORDER BY score DESC, member_id ASC
OFFSET 3 ROWS FETCH NEXT 3 ROWS ONLY;
~~~

Câu SQL Server trên chỉ minh họa cú pháp và giả định có bảng `dbo.members` tương ứng; nó **không** dùng để chạy trực tiếp trên bảng PostgreSQL `lab_order_members_126`.

Với **MySQL**, ví dụ thường có dạng:

~~~sql
SELECT member_id, full_name, score
FROM members
ORDER BY score DESC, member_id ASC
LIMIT 3 OFFSET 3;
~~~

Cần kiểm tra tên bảng, đặc điểm dữ liệu và cách xếp `NULL` riêng của từng hệ. Để đạt cùng một hành vi qua các hệ, bạn có thể viết thêm biểu thức `CASE WHEN ... IS NULL ...` làm tiêu chí rõ ràng.

## 13. Các lỗi thường gặp

| Cách viết hoặc quan niệm dễ sai | Vì sao có vấn đề? | Cách phù hợp |
| --- | --- | --- |
| Truy vấn không `ORDER BY` nhưng dựa vào thứ tự `INSERT` | SQL không cam kết thứ tự hàng khi đọc | Viết `ORDER BY` theo yêu cầu hiển thị |
| `ORDER BY score DESC` rồi cho rằng những người cùng điểm có thứ tự ổn định | Các khóa bằng nhau không được phân định | Thêm tiêu chí phụ, cuối cùng là khóa duy nhất khi cần |
| `ORDER BY joined_on, score DESC` nhưng yêu cầu “điểm cao trước” | Tiêu chí ngày được ưu tiên trước điểm | `ORDER BY score DESC, joined_on ASC` |
| `ORDER BY region, score DESC` nhưng cho rằng tất cả cột giảm dần | `DESC` chỉ áp dụng cho `score` | Viết hướng tường minh cho từng tiêu chí |
| `ORDER BY score DESC` và tưởng `NULL` cuối trên PostgreSQL | DESC mặc định đưa `NULL` lên đầu | `ORDER BY score DESC NULLS LAST` |
| `LIMIT 10` không có thứ tự mà gọi là “top 10” | Không xác định “top” theo tiêu chí nào | Kết hợp `ORDER BY` rõ ràng |
| Dùng `LIMIT/OFFSET` với thứ tự có nhiều hàng hòa | Các trang có thể không ổn định trên cùng dữ liệu | Thêm khóa duy nhất vào `ORDER BY` |
| Sắp chuỗi ngày tháng như văn bản tự do | Thứ tự chữ có thể khác thứ tự thời gian | Lưu và sắp bằng kiểu ngày/giờ thực |
| Dùng `ORDER BY 2` trong truy vấn thường xuyên chỉnh `SELECT` | Đổi thứ tự cột có thể âm thầm đổi cách sắp | Dùng tên cột hoặc bí danh |
| Chỉ đặt `ORDER BY` trong truy vấn con rồi tin đầu ra ngoài giữ nguyên | Truy vấn ngoài có quyền xử lý/đổi thứ tự | Đặt `ORDER BY` ở truy vấn ngoài khi cần kết quả cuối |

## 14. Bài tập thực hành

Mỗi bài sử dụng 10 hàng mẫu ở mục 2. Hãy tự viết SQL và dự đoán thứ tự hoặc nhóm kết quả trước khi mở đáp án.

### Bài 1 — Một cột giảm dần

Yêu cầu: liệt kê `member_id` và `full_name` từ mã lớn đến mã nhỏ.

**Đáp án:**

~~~sql
SELECT member_id, full_name
FROM lab_order_members_126
ORDER BY member_id DESC;
~~~

ID theo thứ tự: **10, 9, 8, 7, 6, 5, 4, 3, 2, 1**.

### Bài 2 — Điểm cao trước, NULL cuối và không hòa thứ tự

Yêu cầu: điểm cao trước, chưa có điểm đứng cuối, nếu bằng điểm thì ID nhỏ trước.

**Đáp án (PostgreSQL):**

~~~sql
SELECT member_id, full_name, score
FROM lab_order_members_126
ORDER BY score DESC NULLS LAST, member_id ASC;
~~~

ID theo thứ tự: **9, 1, 2, 5, 10, 3, 4, 6, 7, 8**.

### Bài 3 — Ba tiêu chí theo thứ tự ưu tiên

Yêu cầu: điểm cao trước; cùng điểm thì ngày tham gia sớm trước; cùng điểm và ngày thì ID nhỏ trước; `NULL` cuối.

**Đáp án:**

~~~sql
SELECT member_id, full_name, score, joined_on
FROM lab_order_members_126
ORDER BY
    score DESC NULLS LAST,
    joined_on ASC,
    member_id ASC;
~~~

ID theo thứ tự: **9, 2, 10, 1, 5, 3, 4, 6, 7, 8**.

### Bài 4 — Đổi thứ tự hai tiêu chí có ảnh hưởng không?

So sánh:

~~~sql
-- Truy van A
SELECT member_id
FROM lab_order_members_126
ORDER BY score DESC NULLS LAST, joined_on ASC, member_id ASC;

-- Truy van B
SELECT member_id
FROM lab_order_members_126
ORDER BY joined_on ASC, score DESC NULLS LAST, member_id ASC;
~~~

**Đáp án:** hai truy vấn có thể trả kết quả theo thứ tự khác nhau. A ưu tiên **điểm**, còn B ưu tiên **ngày tham gia**. Ví dụ B đưa người có ngày `2026-07-20` lên trước người có ngày `2026-08-02` dù điểm có thể thấp hơn. Chỉ đổi vị trí các tiêu chí đã thay đổi ý nghĩa.

### Bài 5 — Phân trang ba hàng mỗi trang

Yêu cầu: dùng thứ tự điểm giảm, ngày tăng, ID tăng như bài 3. Lấy trang số 2 (đánh số từ 1) với ba hàng mỗi trang.

**Đáp án:**

~~~sql
SELECT member_id, full_name, score
FROM lab_order_members_126
ORDER BY score DESC NULLS LAST, joined_on ASC, member_id ASC
LIMIT 3 OFFSET 3;
~~~

Kết quả ID **1, 5, 3**. `OFFSET 3` bỏ qua ba hàng đầu của cùng thứ tự, sau đó `LIMIT 3` lấy ba hàng.

### Bài 6 — Sắp xếp trong từng khu vực

Yêu cầu: khu vực tăng dần; trong cùng khu vực, điểm giảm dần, `NULL` cuối; nếu cùng điểm, ID tăng dần.

**Đáp án:**

~~~sql
SELECT member_id, full_name, region, score
FROM lab_order_members_126
ORDER BY region ASC, score DESC NULLS LAST, member_id ASC;
~~~

Nhóm Central có ID 9, 10; nhóm North có 1, 2, 4, 7; nhóm South có 5, 3, 6, 8 (theo quy tắc sắp tên khu vực của dữ liệu mẫu).

### Bài 7 — Đếm và sắp nhóm

Yêu cầu: đếm thành viên từng khu vực, khu vực nhiều người đứng trước; nếu bằng số người, tên khu vực tăng dần.

**Đáp án:**

~~~sql
SELECT region, COUNT(*) AS member_count
FROM lab_order_members_126
GROUP BY region
ORDER BY member_count DESC, region ASC;
~~~

Kết quả: North (4), South (4), Central (2). Tiêu chí thứ hai phân định North và South khi cùng bốn thành viên.

### Bài 8 — Xác định lỗi trong yêu cầu “ngày mới nhất trước”

Một người viết:

~~~sql
SELECT member_id, joined_on
FROM lab_order_members_126
ORDER BY joined_on ASC, member_id ASC;
~~~

Yêu cầu thật là “ngày tham gia **mới nhất** đứng trước; cùng ngày ID nhỏ đứng trước”.

**Đáp án:** đổi hướng của `joined_on` sang `DESC`:

~~~sql
SELECT member_id, joined_on
FROM lab_order_members_126
ORDER BY joined_on DESC, member_id ASC;
~~~

ID đứng đầu là **6** (ngày `2026-08-03`), tiếp theo là **1, 5, 9** (cùng ngày `2026-08-02`, phân định bằng ID), rồi các ngày cũ hơn.

## 15. Ghi nhớ khi viết ORDER BY

- `ORDER BY cot ASC` sắp tăng dần; `ORDER BY cot DESC` sắp giảm dần. Nếu bỏ hướng, mặc định thường là tăng dần.
- Với **nhiều cột**, đọc tiêu chí từ **trái sang phải**. Chỉ dùng cột thứ hai khi cột thứ nhất hòa; chỉ dùng cột thứ ba khi hai cột trước hòa.
- Dấu phẩy ngăn các tiêu chí; mỗi tiêu chí có thể chọn `ASC` hoặc `DESC` riêng.
- Cần cân nhắc **`NULL`**, vì vị trí mặc định và cú pháp điều khiển có thể khác giữa các hệ quản trị.
- Khi kết quả cần thứ tự hoàn toàn xác định, đặc biệt trước `LIMIT`/`OFFSET`, hãy thêm khóa duy nhất như `member_id` làm tiêu chí cuối nếu các tiêu chí trước còn khả năng hòa.
- `ORDER BY` xác định **cách trả kết quả**, không sắp lại dữ liệu vật lý hay tự giới hạn số hàng.

Khi đọc một truy vấn có `ORDER BY` nhiều cột, hãy diễn đạt thành một câu: **“Ưu tiên theo cột nào trước, hòa thì theo cột nào tiếp, và nếu vẫn hòa thì dựa vào đâu để xác định thứ tự?”** Trả lời được ba phần này giúp bạn viết đúng câu SQL, giải thích kết quả và xây dựng phân trang đáng tin cậy hơn.
