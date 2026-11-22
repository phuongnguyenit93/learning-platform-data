# Kiểm tra điều kiện ở các giá trị biên và dữ liệu bất thường trong SQL

> **Module:** Database SQL  
> **Chương:** Điều kiện lọc  
> **Bài học:** Kiểm tra điều kiện ở các giá trị biên và dữ liệu bất thường

Một câu lệnh SQL có thể chạy đúng cú pháp và cho kết quả hợp lý với dữ liệu thông thường, nhưng vẫn sai ở đúng những hàng nằm sát ranh giới: giá bằng ngưỡng, thời điểm cuối ngày, chuỗi rỗng, giá trị NULL, số thập phân rất nhỏ, ký tự có dấu hoặc bản ghi không tuân thủ quy tắc nghiệp vụ. Bài học này trình bày cách **thiết kế dữ liệu kiểm thử và xác định kết quả mong đợi** cho điều kiện lọc, đặc biệt là các mệnh đề WHERE, JOIN ... ON và HAVING.

## 1. Mục tiêu

Sau khi học, bạn có thể:

- Xác định các **ranh giới** trong một điều kiện SQL: bằng ngưỡng, ngay dưới ngưỡng, ngay trên ngưỡng, đầu và cuối khoảng.
- Phân biệt **cận bao gồm** với **cận loại trừ** khi dùng =, <, <=, >, >=, BETWEEN.
- Đề xuất dữ liệu kiểm thử có chủ đích thay vì thử ngẫu nhiên vài hàng “bình thường”.
- Dự đoán đúng cách WHERE xử lý **TRUE, FALSE và UNKNOWN**, đặc biệt khi cột có NULL.
- Nhận diện trường hợp bất thường về số, văn bản, Unicode, ngày giờ, kiểu dữ liệu và quan hệ giữa các bảng.
- Kiểm tra AND, OR, NOT, IN, NOT IN, LIKE, EXISTS và điều kiện JOIN tại các trường hợp biên.
- Viết truy vấn kiểm thử độc lập, có **kết quả mong đợi cụ thể**, biết cách phân biệt lỗi dữ liệu với lỗi câu SQL.
- Áp dụng tư duy giá trị biên vào thiết kế bộ lọc tìm kiếm, kiểm thử tích hợp và thay đổi phiên bản DBMS.

## 2. Tại sao phải kiểm tra dữ liệu biên?

Giả sử cửa hàng muốn lấy đơn hàng có tổng tiền **từ 100.000 đồng trở lên**. Câu SQL tự nhiên là:

~~~sql
SELECT ma_don_hang, tong_tien
FROM don_hang
WHERE tong_tien >= 100000;
~~~

Nếu chỉ thử tổng tiền **200000**, truy vấn sẽ trả đơn hàng đúng như kỳ vọng. Nhưng một lỗi rất phổ biến là lập trình viên vô tình viết:

~~~sql
WHERE tong_tien > 100000
~~~

Cả hai câu đều chọn 200000, nên một bài thử bằng giá trị thông thường không phát hiện được lỗi. Chỉ khi thử **100000 chính xác**, sự khác biệt mới lộ ra:

- **tong_tien = 99999.99:** không đạt ngưỡng ở cả hai câu.
- **tong_tien = 100000.00:** đạt với >= nhưng không đạt với >.
- **tong_tien = 100000.01:** đạt với cả hai câu.

Đây là ý tưởng của **kiểm thử giá trị biên** (*boundary value analysis*): tập trung vào các vị trí mà kết quả của điều kiện **có khả năng đổi từ được chọn sang bị loại**.

Kiểm thử dữ liệu bất thường (*edge cases / exceptional data*) bổ sung các trường hợp như NULL, chuỗi rỗng, dữ liệu có khoảng trắng, giá âm, dữ liệu sai kiểu, bản ghi thiếu quan hệ hoặc thời điểm trùng đúng ranh giới ngày. Giá trị biên không nhất thiết bất hợp lệ; ví dụ giá đúng 100000 là giá trị hoàn toàn hợp lệ nhưng dễ bị lọc sai.

## 3. Một tập dữ liệu minh họa dùng xuyên suốt

Giả sử bảng **don_hang** có các cột:

| Cột | Kiểu dữ liệu dự kiến | Ý nghĩa |
|---|---|---|
| **ma_don_hang** | INTEGER, khóa chính | Mã đơn duy nhất, không NULL |
| **trang_thai** | VARCHAR(20) | PAID, PENDING, CANCELLED... |
| **tong_tien** | DECIMAL(12,2), cho phép NULL | Tổng tiền đồng Việt Nam |
| **email** | VARCHAR(120), cho phép NULL | Email khách hàng |
| **tao_luc** | TIMESTAMP, cho phép NULL | Thời điểm tạo đơn |

Tập dữ liệu thử:

| Mã | Trạng thái | Tổng tiền | Email | Thời điểm tạo |
|---:|---|---:|---|---|
| 1 | PAID | 0.00 | an@example.com | 2026-03-01 00:00:00 |
| 2 | PAID | 99999.99 | binh@example.com | 2026-03-31 23:59:59 |
| 3 | PAID | 100000.00 | NULL | 2026-04-01 00:00:00 |
| 4 | PAID | 100000.01 | chuỗi rỗng | 2026-03-15 12:00:00 |
| 5 | CANCELLED | NULL | chi@example.com | NULL |
| 6 | PAID | -1.00 | dung@example.com | 2026-02-28 23:59:59 |
| 7 | PAID | 500000.00 | hoa@example.com | 2026-04-05 10:00:00 |
| 8 | PENDING | 100000.00 | em@example.com | 2026-03-20 09:00:00 |
| 9 | PAID | 100000.00 | lan@example.com | 2026-03-21 09:00:00 |
| 10 | PAID | 100000.00 | có khoảng trắng ở đầu/cuối | 2026-03-30 14:00:00 |

Đây là **dữ liệu kiểm thử được thiết kế cố ý**, không khẳng định một hệ thống thực tế phải cho phép đơn âm tiền hoặc thiếu thời gian tạo. Những giá trị như **-1.00** và **NULL** được đưa vào để quan sát hành vi khi dữ liệu không như mong đợi.

Trong các ví dụ, cột **tao_luc** được giả định lưu thời điểm cùng một quy ước múi giờ. Nếu hệ thống có kiểu thời gian kèm múi giờ hoặc lưu thời điểm UTC, việc chuyển biên thời gian phải thực hiện theo quy tắc tương ứng.

**Lưu ý khả chuyển:** một số DBMS (đặc biệt là Oracle Database truyền thống) coi chuỗi rỗng như NULL. Vì vậy, những bài thử cần **phân biệt chuỗi rỗng với NULL** phải được chạy trên DBMS cụ thể; không nên mặc định kết quả giống nhau ở mọi hệ.

### 3.1. Tạo bảng dùng cho môi trường thử nghiệm

Có thể bắt đầu từ lược đồ minh họa sau rồi điều chỉnh cú pháp kiểu dữ liệu theo DBMS:

~~~sql
CREATE TABLE don_hang (
    ma_don_hang INTEGER PRIMARY KEY,
    trang_thai VARCHAR(20) NOT NULL,
    tong_tien DECIMAL(12, 2),
    email VARCHAR(120),
    tao_luc TIMESTAMP
);
~~~

Kiểu TIMESTAMP, ràng buộc và cú pháp truyền giá trị ngày giờ có khác biệt giữa các hệ quản trị. Các bảng dữ liệu phía trên mô tả **giá trị logic cần nạp**, tránh phụ thuộc vào một cú pháp literal ngày giờ chỉ đúng cho một phương ngữ.

Khi xây bộ thử thật, tạo dữ liệu trong **cơ sở dữ liệu dành riêng cho test**, với transaction hoặc cơ chế khởi tạo và xóa dữ liệu phù hợp. Đừng chạy thao tác nạp/sửa/xóa dữ liệu minh họa vào cơ sở dữ liệu sản xuất.

## 4. Kỹ thuật ba điểm quanh một ngưỡng

Với điều kiện **x >= B**, nên thử ít nhất:

1. Giá trị hợp lệ ngay **dưới** B.
2. Giá trị **bằng** B.
3. Giá trị hợp lệ ngay **trên** B.

Giả sử x có kiểu **DECIMAL(12,2)**, ngưỡng B = 100000.00 và bước nhỏ nhất của dữ liệu là 0.01:

| Giá trị x | x >= 100000 | x > 100000 |
|---:|---|---|
| 99999.99 | FALSE | FALSE |
| 100000.00 | TRUE | FALSE |
| 100000.01 | TRUE | TRUE |

Một truy vấn lọc theo yêu cầu “ít nhất 100000”:

~~~sql
SELECT ma_don_hang, tong_tien
FROM don_hang
WHERE tong_tien >= 100000
ORDER BY ma_don_hang;
~~~

Theo dữ liệu mẫu, các mã được chọn là **3, 4, 7, 8, 9, 10**. Sản phẩm có mã 2 thấp hơn ngưỡng đúng 0.01; mã 3, 8, 9, 10 bằng ngưỡng; mã 4 nhỉnh hơn 0.01.

**Không phải kiểu dữ liệu nào cũng có một bước liền kề đơn giản.** Với INTEGER, điểm sát ngưỡng là B−1, B, B+1. Với DECIMAL có hai chữ số phần thập phân, bước dữ liệu thường là 0.01. Với FLOAT/DOUBLE, các giá trị nhị phân biểu diễn được không cách đều và có sai số, nên đừng chọn một “epsilon” tùy tiện rồi coi nó là giá trị kế cận trong mọi trường hợp.

### 4.1. Các phép so sánh ở đúng ranh giới

| Điều kiện | 99999.99 | 100000.00 | 100000.01 |
|---|---|---|---|
| x > 100000 | Loại | Loại | Chọn |
| x >= 100000 | Loại | Chọn | Chọn |
| x < 100000 | Chọn | Loại | Loại |
| x <= 100000 | Chọn | Chọn | Loại |
| x = 100000 | Loại | Chọn | Loại |
| x <> 100000 | Chọn | Loại | Chọn |

Trong bảng này, **Chọn** nghĩa điều kiện là TRUE và WHERE giữ hàng; **Loại** nghĩa FALSE. Nếu **x = NULL**, những phép so sánh thông thường phía trên cho **UNKNOWN** và hàng cũng bị WHERE loại.

## 5. Kiểm tra cả hai đầu của một khoảng

Một khoảng có bốn cách định nghĩa:

| Khoảng | Biểu thức SQL | Bao gồm đầu dưới? | Bao gồm đầu trên? |
|---|---|---|---|
| [A, B] | x >= A AND x <= B | Có | Có |
| [A, B) | x >= A AND x < B | Có | Không |
| (A, B] | x > A AND x <= B | Không | Có |
| (A, B) | x > A AND x < B | Không | Không |

Dấu ngoặc vuông/ngang ở bảng là **ký hiệu toán học mô tả khoảng**, không phải cú pháp SQL để gõ trực tiếp vào WHERE.

Giả sử yêu cầu “đơn có tổng tiền **từ 100000 và nhỏ hơn 500000**”:

~~~sql
SELECT ma_don_hang, tong_tien
FROM don_hang
WHERE tong_tien >= 100000
  AND tong_tien < 500000
ORDER BY ma_don_hang;
~~~

Kết quả: **3, 4, 8, 9, 10**.

Điểm biên đáng thử:

| Giá trị | Được chọn? | Lý do |
|---:|---|---|
| 99999.99 | Không | Dưới cận thấp |
| 100000.00 | Có | Cận thấp được bao gồm |
| 100000.01 | Có | Nằm bên trong |
| 499999.99 | Có | Sát cận trên từ bên trong |
| 500000.00 | Không | Cận trên bị loại trừ |
| 500000.01 | Không | Vượt cận trên |
| NULL | Không | So sánh không TRUE |

Tập dữ liệu mẫu có sẵn mã 7 với **500000.00**, giúp phát hiện lỗi viết **<= 500000** thay cho **< 500000**.

### 5.1. BETWEEN bao gồm cả hai đầu

~~~sql
SELECT ma_don_hang, tong_tien
FROM don_hang
WHERE tong_tien BETWEEN 100000 AND 500000
ORDER BY ma_don_hang;
~~~

Về ngữ nghĩa điều kiện khoảng thông thường, biểu thức trên tương đương:

~~~sql
WHERE tong_tien >= 100000
  AND tong_tien <= 500000
~~~

Kết quả sẽ có thêm **mã 7** so với khoảng nửa mở. Vì vậy, **BETWEEN không thích hợp nếu yêu cầu cận trên là loại trừ**.

### 5.2. Khi đầu khoảng bị đảo ngược

Giả sử bộ lọc nhận **min = 500000** và **max = 100000**. Truy vấn:

~~~sql
WHERE tong_tien BETWEEN 500000 AND 100000
~~~

không tự động tráo hai đầu mút. Với các giá trị số thông thường, không hàng nào thỏa mãn. Ở tầng ứng dụng cần quyết định rõ: từ chối bộ lọc sai, yêu cầu người dùng sửa hay chủ động hoán đổi hai đầu nếu sản phẩm có quy tắc đó. Không nên xem việc trả tập rỗng là một cách xử lý lỗi đầu vào đủ rõ ràng cho mọi ứng dụng.

### 5.3. Khoảng rỗng và khoảng chỉ chứa một điểm

Với x kiểu số:

~~~sql
WHERE x >= 100000 AND x < 100000
~~~

là khoảng rỗng: không giá trị không NULL nào thỏa điều kiện. Trong khi:

~~~sql
WHERE x >= 100000 AND x <= 100000
~~~

chỉ chọn x bằng chính xác 100000.

Hai trường hợp này quan trọng khi người dùng nhập **min = max**. Yêu cầu “chính xác bằng 100000” cần cận bao gồm, còn yêu cầu “từ 100000 đến trước 100000” tạo khoảng rỗng.

## 6. Dữ liệu NULL: biên không nằm trên trục số

NULL không phải một giá trị rất nhỏ, rất lớn, bằng 0 hoặc bằng chuỗi rỗng. Nó là dấu hiệu **không có giá trị** tại vị trí dữ liệu đó.

Với **tong_tien = NULL**:

~~~sql
tong_tien >= 0       -- UNKNOWN
tong_tien < 0        -- UNKNOWN
tong_tien = NULL     -- UNKNOWN
tong_tien <> 0       -- UNKNOWN
NOT (tong_tien > 0)  -- UNKNOWN
~~~

Mệnh đề **WHERE chỉ giữ hàng có điều kiện TRUE**. Cả FALSE và UNKNOWN đều bị loại. Vì vậy:

~~~sql
-- Không tìm được hàng thiếu tiền theo ý định.
SELECT ma_don_hang
FROM don_hang
WHERE tong_tien = NULL;
~~~

Đúng là:

~~~sql
SELECT ma_don_hang
FROM don_hang
WHERE tong_tien IS NULL;
~~~

Theo dữ liệu mẫu, kết quả có **mã 5**.

Để lấy các hàng có giá trị tổng tiền:

~~~sql
SELECT ma_don_hang
FROM don_hang
WHERE tong_tien IS NOT NULL
ORDER BY ma_don_hang;
~~~

Kết quả có tất cả mã trừ **5**.

### 6.1. Bảng chân trị rút gọn

| P | Q | P AND Q | P OR Q |
|---|---|---|---|
| TRUE | UNKNOWN | UNKNOWN | TRUE |
| FALSE | UNKNOWN | FALSE | UNKNOWN |
| UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN |

Và **NOT UNKNOWN = UNKNOWN**.

Ví dụ với mã 5:

~~~sql
WHERE tong_tien < 100000
   OR trang_thai = 'CANCELLED'
~~~

Ở mã 5, vế đầu UNKNOWN, vế sau TRUE, nên **UNKNOWN OR TRUE = TRUE**: mã 5 được giữ.

Nếu đổi OR thành AND, kết quả là **UNKNOWN AND TRUE = UNKNOWN**: mã 5 bị loại.

### 6.2. Phủ định không tự đưa NULL trở lại

~~~sql
SELECT ma_don_hang
FROM don_hang
WHERE NOT (tong_tien >= 100000)
ORDER BY ma_don_hang;
~~~

Câu này chọn giá **xác định** dưới 100000: **mã 1, 2, 6**. Mã 5 có tổng tiền NULL vẫn bị loại.

Nếu nghiệp vụ là “chưa được xác nhận có tổng tiền từ 100000 trở lên”, gồm cả giá thiếu:

~~~sql
SELECT ma_don_hang
FROM don_hang
WHERE tong_tien < 100000
   OR tong_tien IS NULL
ORDER BY ma_don_hang;
~~~

Kết quả: **1, 2, 5, 6**.

Hai tập hợp “chắc chắn dưới ngưỡng” và “chưa được xác nhận đạt ngưỡng” khác nhau về cách xử lý dữ liệu thiếu.

### 6.3. Cẩn thận với COALESCE

~~~sql
WHERE COALESCE(tong_tien, 0) < 100000
~~~

Sẽ chọn **1, 2, 5, 6** vì đã chủ động thay NULL bằng 0. Nó có thể phù hợp nếu quy tắc nghiệp vụ là “khi chưa có tổng tiền, tạm tính 0”, nhưng nếu tổng tiền NULL nghĩa là dữ liệu chưa được xác nhận thì cách làm này **che giấu dữ liệu thiếu**.

Khi kiểm thử, nên có ít nhất một hàng **0 thật** (mã 1) và một hàng **NULL** (mã 5) để phát hiện việc gộp nhầm hai tình huống.

## 7. Dữ liệu số bất thường: âm, 0, cực lớn và sai số

### 7.1. Giá trị âm và số 0

Giả sử tổng tiền của đơn hàng được phép 0 nhưng không được âm. Các biên nghiệp vụ là:

| Giá trị | Trạng thái mong đợi | Gợi ý kiểm tra |
|---:|---|---|
| -0.01 | Bất hợp lệ | Có bị ngăn tại ghi dữ liệu hoặc phát hiện ở truy vấn kiểm tra? |
| 0.00 | Hợp lệ | Điều kiện >= 0 phải giữ hàng |
| 0.01 | Hợp lệ | Điều kiện > 0 phải giữ hàng |
| NULL | Phụ thuộc quy tắc | NOT NULL hoặc xử lý dữ liệu thiếu |

Truy vấn phát hiện giá âm:

~~~sql
SELECT ma_don_hang, tong_tien
FROM don_hang
WHERE tong_tien < 0;
~~~

Kết quả có **mã 6** với **-1.00**.

Truy vấn này không phát hiện NULL, vì NULL < 0 là UNKNOWN. Nếu cần tìm tất cả bản ghi **cần kiểm tra vì âm hoặc thiếu tổng tiền**:

~~~sql
SELECT ma_don_hang, tong_tien
FROM don_hang
WHERE tong_tien < 0
   OR tong_tien IS NULL
ORDER BY ma_don_hang;
~~~

Kết quả **5, 6**.

Nếu muốn ngăn giá âm khi ghi dữ liệu, có thể khai báo ràng buộc:

~~~sql
ALTER TABLE don_hang
ADD CONSTRAINT ck_tong_tien_khong_am
CHECK (tong_tien >= 0);
~~~

Đây là cú pháp minh họa; cần điều chỉnh cho DBMS cụ thể. **CHECK** thông thường chỉ từ chối điều kiện FALSE và có thể chấp nhận UNKNOWN, nên nếu yêu cầu tổng tiền bắt buộc có giá trị thì cần thêm **NOT NULL**. Trong dữ liệu kiểm thử hiện có, mã 6 sẽ vi phạm ràng buộc đó; không thể áp dụng trực tiếp khi chưa xử lý dữ liệu sai.

### 7.2. Precision và scale của DECIMAL

Kiểu **DECIMAL(12,2)** mô tả tối đa 12 chữ số với 2 chữ số sau dấu thập phân trong các hệ dùng ngữ nghĩa DECIMAL thông thường. Chẳng hạn, giá trị lớn nhất có thể lưu theo dải số dương tương ứng là **9999999999.99**; giới hạn chính xác còn cần xem kiểu và DBMS đang dùng.

Khi kiểm thử giá trị biên của **cột lưu dữ liệu**, cần phân biệt:

- **Biên miền giá trị của kiểu dữ liệu:** có lưu được giá rất lớn/nhỏ hay không?
- **Biên của quy tắc nghiệp vụ:** ví dụ tổng tiền phải không âm và không vượt 500 triệu.
- **Biên của bộ lọc:** ví dụ chỉ chọn đơn từ 100000 tới dưới 500000.
- **Biên của phép tính:** nhân số lượng với đơn giá có thể gây tràn, làm tròn hoặc đổi scale.

Với một giá trị có **nhiều hơn hai chữ số phần thập phân** như 100000.005, DBMS có thể làm tròn, báo lỗi hoặc chuyển đổi theo quy tắc riêng khi ghi vào cột DECIMAL(12,2). Không nên so sánh kết quả trước khi xác định chính xác **giá trị đã được lưu**.

### 7.3. FLOAT và DOUBLE: gần bằng không nhất thiết bằng

Nếu một cột dùng kiểu số thực nhị phân **FLOAT/REAL/DOUBLE**, các phép tính như **0.1 + 0.2** có thể không cho giá trị được biểu diễn chính xác bằng **0.3**.

Ví dụ minh họa ý định có thể gây rủi ro:

~~~sql
WHERE diem_tinh_toan = 0.3
~~~

Dòng có điểm được tính bằng số thực nhị phân có thể không khớp phép bằng, dù khi hiển thị làm tròn nó giống 0.3.

Cần xác định tính chất dữ liệu:

- Với tiền tệ và các giá trị cần chính xác đến phần nhỏ cố định, ưu tiên DECIMAL/NUMERIC và quy tắc làm tròn đã quy định.
- Với đại lượng đo lường dạng FLOAT/DOUBLE, nếu nghiệp vụ cho phép sai số thì thiết kế khoảng dung sai có cơ sở, ví dụ **ABS(x - B) <= epsilon**, với epsilon được chọn theo độ lớn và độ chính xác cần thiết.
- Không mặc định một epsilon dùng được cho mọi thang đo hoặc mọi biểu thức tính toán.
- Các phép tính trên cột trong WHERE có thể ảnh hưởng khả năng sử dụng chỉ mục; chỉ tối ưu sau khi đã xác nhận phép tính tương đương.

### 7.4. Tràn số, ép kiểu và dữ liệu nguồn sai định dạng

Trong hệ thống nhập dữ liệu, giá có thể ban đầu nằm ở cột văn bản như **gia_nhap = '100,000'**, **'100000đ'**, **'N/A'** hoặc **'1e20'**. Những chuỗi này không đồng nghĩa một giá trị DECIMAL hợp lệ trên mọi DBMS.

Không nên kỳ vọng SQL tự chuyển đổi kiểu an toàn:

~~~sql
-- Minh họa rủi ro nếu tong_tien_text chứa chuỗi không phải số.
SELECT *
FROM du_lieu_nhap
WHERE CAST(tong_tien_text AS DECIMAL(12, 2)) >= 100000;
~~~

Tùy DBMS và cấu hình, phép chuyển kiểu có thể báo lỗi, bị cắt, làm tròn hoặc cho một kết quả khó đoán. Cần kiểm tra định dạng **trước khi chuyển**, có quy tắc xử lý dòng sai, và kiểm thử với đúng driver/phiên bản. Một số hệ hỗ trợ các hàm **TRY_CAST/SAFE_CAST** hoặc cơ chế tương đương, nhưng cách đặt tên và hành vi khác nhau.

**Không nên dựa vào thứ tự hai điều kiện AND như một cam kết chống lỗi chuyển kiểu**, vì bộ tối ưu có thể thay đổi thứ tự đánh giá vật lý.

## 8. Thời gian: đầu ngày, cuối ngày và ranh giới tháng

Lọc theo thời gian đặc biệt dễ sai do một cột có thể lưu **ngày** hoặc **ngày kèm giờ**, độ chính xác đến giây, mili giây, micro giây hoặc cao hơn.

### 8.1. Sai lầm phổ biến với cuối ngày

Yêu cầu: “Tìm đơn được tạo trong tháng 3 năm 2026”.

Một cách viết có rủi ro nếu **tao_luc** là TIMESTAMP:

~~~sql
-- Không bao phủ cả ngày 31/03 nếu cận trên là đầu ngày.
WHERE tao_luc BETWEEN :dau_thang AND :cuoi_ngay_31
~~~

Nếu **:cuoi_ngay_31** được bind bằng **2026-03-31 00:00:00**, thì đơn lúc **2026-03-31 23:59:59** (mã 2) không được chọn.

Cách rõ ràng và thường an toàn hơn là **khoảng nửa mở**:

~~~sql
SELECT ma_don_hang, tao_luc
FROM don_hang
WHERE tao_luc >= ?
  AND tao_luc < ?
ORDER BY tao_luc, ma_don_hang;
~~~

Trong JDBC, bind hai tham số là:

- Cận dưới: **2026-03-01 00:00:00**.
- Cận trên: **2026-04-01 00:00:00**.

Theo dữ liệu mẫu, kết quả gồm các mã **1, 2, 4, 8, 9, 10**.

### 8.2. Bảng kiểm thử biên thời gian

| Thời điểm | Có thuộc [2026-03-01 00:00:00, 2026-04-01 00:00:00)? |
|---|---|
| 2026-02-28 23:59:59 | Không |
| 2026-03-01 00:00:00 | Có |
| 2026-03-31 23:59:59 | Có |
| 2026-03-31 23:59:59.999 | Có, nếu kiểu lưu hỗ trợ phần lẻ giây |
| 2026-04-01 00:00:00 | Không |
| 2026-04-01 00:00:00.001 | Không |
| NULL | Không |

Chủ đích là kiểm tra cận **đúng tại thời điểm chuyển tháng**, không đoán “giây cuối ngày” của mọi hệ thống. Nếu dùng điều kiện **<= '2026-03-31 23:59:59'**, các bản ghi có phần lẻ giây sau 23:59:59 vẫn bị bỏ sót.

### 8.3. DATE khác TIMESTAMP

Với cột kiểu **DATE** chỉ lưu ngày lịch, yêu cầu cả tháng 3 có thể được mô tả bằng ngày từ **2026-03-01 đến 2026-03-31**. Với cột kiểu **TIMESTAMP**, cách an toàn thường là [đầu tháng, đầu tháng sau) vì thời gian có nhiều giá trị trong cùng một ngày.

Đừng dùng chuỗi thời gian không có kiểu rõ ràng và dựa vào DBMS tự suy diễn theo cấu hình ngày tháng. Trong ứng dụng, bind tham số đúng kiểu ngày/giờ qua API truy cập dữ liệu.

### 8.4. Múi giờ, ngày địa phương và chuyển giờ mùa hè

Một mốc **2026-03-01 00:00:00** không phải lúc nào cũng chỉ một thời điểm tuyệt đối: nó có thể đại diện cho giờ địa phương ở Hà Nội, New York hoặc UTC. Cùng một sự kiện có thể thuộc ngày khác nhau khi hiển thị ở múi giờ khác.

Nếu nghiệp vụ yêu cầu “đơn được tạo trong **ngày địa phương của người dùng**”:

1. Xác định **vùng giờ IANA** của người dùng hoặc đơn vị nghiệp vụ, ví dụ **Asia/Ho_Chi_Minh**.
2. Tạo mốc bắt đầu ngày địa phương và bắt đầu **ngày kế tiếp** trong vùng giờ đó.
3. Chuyển hai mốc thành kiểu thời điểm thống nhất dùng trong lưu trữ/truy vấn.
4. Lọc theo khoảng **>= đầu ngày** và **< đầu ngày kế tiếp**.

Không phải mọi ngày địa phương đều dài đúng 24 giờ ở những vùng có chuyển giờ mùa hè (DST). Vì vậy, không nên mặc định cộng đúng 24 giờ trong UTC sẽ luôn ra đầu ngày địa phương tiếp theo.

### 8.5. Đồng hồ hệ thống, thời gian tương lai và dữ liệu thiếu

Ngoài cận tháng/ngày, cần thử:

- **tao_luc = NULL** (mã 5).
- Thời điểm **trước khi hệ thống được cho là hoạt động**.
- Thời điểm **trong tương lai** so với thời điểm kiểm thử (cần cố định đồng hồ của test).
- Bản ghi được tạo đúng **tại mốc hết hạn**.
- Nhiều bản ghi có cùng timestamp nhưng khác mã.
- Chênh lệch giữa thời gian **ứng dụng gửi** và thời gian **DBMS ghi**.

Một bài thử phụ thuộc trực tiếp vào **CURRENT_TIMESTAMP** có thể cho kết quả khác khi chạy vào lúc khác. Với bộ test cần lặp lại, nên truyền thời điểm “hiện tại” dưới dạng giá trị cố định hoặc dùng cơ chế giả lập đồng hồ của ứng dụng.

## 9. Chuỗi và dữ liệu bất thường

Bộ lọc văn bản thường chịu ảnh hưởng của **collation**, Unicode, khoảng trắng, chữ hoa/thường, dấu và ký tự đại diện.

### 9.1. NULL, chuỗi rỗng và chuỗi có khoảng trắng

Các trường hợp khác nhau cần thử là:

| Giá trị cột email | Ý nghĩa khả dĩ |
|---|---|
| NULL | Chưa có dữ liệu email |
| '' | Chuỗi rỗng (nếu DBMS phân biệt) |
| ' ' | Một dấu cách |
| '  mai@example.com  ' | Có khoảng trắng đầu/cuối |
| 'an@example.com' | Chuỗi thông thường |

Truy vấn:

~~~sql
SELECT ma_don_hang, email
FROM don_hang
WHERE email IS NULL;
~~~

sẽ tìm **mã 3** trên những hệ giữ NULL và chuỗi rỗng là hai giá trị khác nhau. Trên một số hệ (ví dụ Oracle truyền thống), chuỗi rỗng có thể được xử lý như NULL nên hành vi với mã 4 có thể khác.

Nếu yêu cầu là “email không được rỗng sau khi bỏ khoảng trắng”, cần phát biểu quy tắc rõ ràng. Một mẫu truy vấn:

~~~sql
SELECT ma_don_hang, email
FROM don_hang
WHERE email IS NULL
   OR TRIM(email) = '';
~~~

Với DBMS phân biệt NULL và chuỗi rỗng, truy vấn phát hiện **mã 3 và 4**. Nó không chọn mã 10 vì chuỗi đó còn nội dung sau TRIM. Tuy nhiên, hành vi TRIM và các loại ký tự trắng được xử lý cần kiểm tra trên DBMS; tab, xuống dòng, khoảng trắng không ngắt (non-breaking space) và các ký tự Unicode khác có thể không bị loại bỏ như dấu cách ASCII.

Nếu muốn nhận cả trường hợp **chỉ chứa khoảng trắng Unicode**, ứng dụng có thể cần chuẩn hóa văn bản theo quy tắc nghiệp vụ trước khi lưu, thay vì phụ thuộc vào TRIM mặc định.

### 9.2. Chữ hoa/thường và dấu tiếng Việt

Xem điều kiện:

~~~sql
WHERE ten_san_pham = 'Cà phê'
~~~

Các giá trị **'Cà phê'**, **'cà phê'**, **'Ca phe'** có được xem bằng nhau hay không phụ thuộc **collation** hoặc chức năng so sánh văn bản của DBMS. Nhiều cơ sở dữ liệu có tùy chọn **phân biệt chữ hoa** và **phân biệt dấu**; mặc định không thống nhất.

Bộ dữ liệu thử nên có ít nhất:

- Cùng từ nhưng chữ hoa/thường khác nhau.
- Có dấu và không dấu.
- Chuỗi có dấu ở đầu/cuối.
- Dạng Unicode được tạo bằng các tổ hợp mã ký tự khác nhau nhưng hiển thị tương tự.
- Ký tự nằm ngoài bảng chữ cái Latin cơ bản nếu ứng dụng hỗ trợ đa ngôn ngữ.

Ví dụ, chữ hiển thị có dấu có thể được mã hóa bằng một **ký tự ghép sẵn** hoặc một **ký tự cơ sở kết hợp dấu**, và việc so sánh tùy thuộc chuẩn hóa Unicode cùng collation. Hai chuỗi nhìn giống nhau trên màn hình không luôn có biểu diễn byte giống nhau.

**Quy tắc kiểm thử:** đừng viết “phải tìm thấy” chỉ dựa vào cảm quan; trước hết xác định yêu cầu tìm kiếm có phân biệt hoa/thường, dấu và chuẩn hóa Unicode hay không.

### 9.3. Độ dài chuỗi và khoảng trắng ở cuối

Một số DBMS hoặc kiểu CHAR có quy tắc đệm khoảng trắng; phép bằng đối với chuỗi có khoảng trắng cuối có thể khác với việc so sánh byte. Kiểm thử nên phân biệt:

- VARCHAR chứa **'abc'**.
- VARCHAR chứa **'abc '**.
- CHAR có chiều dài cố định lưu **'abc'**.
- Chuỗi có nhiều khoảng trắng đầu/cuối.
- Chuỗi vượt giới hạn cột một ký tự.

Hạn chế dùng một bộ so sánh chuỗi mơ hồ cho các giá trị có ý nghĩa **mã định danh**, ví dụ mã xác thực, mã sản phẩm hoặc hash. Các giá trị đó có thể cần quy tắc so khớp byte hoặc collation nhị phân được quy định rõ.

## 10. LIKE: kiểm tra dấu %, _, ký tự escape và đầu vào người dùng

**LIKE** hỗ trợ mẫu chuỗi, trong đó:

- **%** khớp không hoặc nhiều ký tự.
- **_** khớp một ký tự theo quy tắc của DBMS.

Ví dụ:

~~~sql
SELECT ma_don_hang, email
FROM don_hang
WHERE email LIKE '%@example.com'
ORDER BY ma_don_hang;
~~~

Truy vấn minh họa tìm email có hậu tố **@example.com**, nhưng với email NULL điều kiện LIKE cho UNKNOWN nên bị loại. Email có khoảng trắng sau **.com** (mã 10) không khớp mẫu hậu tố như dự tính; việc so sánh dấu cách và collation vẫn phụ thuộc DBMS, vì vậy cần đặt kỳ vọng dựa trên sản phẩm thực tế.

### 10.1. Những dữ liệu biên cho LIKE

Với mẫu **'AB%'**, hãy thử:

| Dữ liệu | Ý nghĩa kiểm thử |
|---|---|
| 'AB' | % khớp chuỗi độ dài 0 |
| 'ABC' | % khớp một ký tự |
| 'ABCD' | % khớp nhiều ký tự |
| 'A' | Thiếu một ký tự bắt buộc |
| 'XAB' | Đúng chuỗi nhưng sai vị trí tiền tố |
| '' | Chuỗi rỗng |
| NULL | LIKE không trả TRUE |
| 'ab' | Phụ thuộc quy tắc hoa/thường |
| 'AB%' | Có ký tự % thật trong dữ liệu |

Với mẫu **'AB_'**, chuỗi 'AB' không khớp vì dấu _ yêu cầu một ký tự; 'ABC' khớp; 'ABCD' không khớp vì thừa một ký tự.

### 10.2. Khi người dùng muốn tìm ký tự % hoặc _ thật

Giả sử người dùng nhập từ khóa **'20%'** và muốn tìm dấu phần trăm **thật**, không dùng nó như wildcard. Ứng dụng cần escape ký tự đặc biệt khi tạo mẫu LIKE.

Một cách minh họa SQL:

~~~sql
SELECT ten_san_pham
FROM san_pham
WHERE ten_san_pham LIKE '%!%%' ESCAPE '!';
~~~

Trong đó **!%** là dấu phần trăm literal, còn hai dấu % ngoài cùng là wildcard. Quy tắc escape và cách driver truyền mẫu cần được kiểm tra theo phương ngữ.

**Lưu ý:** Sử dụng PreparedStatement giúp tránh SQL injection cho tham số giá trị, nhưng nó không tự động biến ký tự % hay _ trong một tham số LIKE thành ký tự thường. Hai việc **tham số hóa SQL** và **escape wildcard theo ý định tìm kiếm** giải quyết hai vấn đề khác nhau.

## 11. AND, OR, NOT: trường hợp biên của logic kết hợp

Lỗi thường gặp không nằm ở một toán tử so sánh mà ở cách kết hợp điều kiện.

Yêu cầu: “Chọn đơn **PAID** và có tổng tiền **từ 100000 đến dưới 500000**.”

~~~sql
SELECT ma_don_hang, trang_thai, tong_tien
FROM don_hang
WHERE trang_thai = 'PAID'
  AND tong_tien >= 100000
  AND tong_tien < 500000
ORDER BY ma_don_hang;
~~~

Kết quả là **3, 4, 9, 10**.

Bộ dữ liệu mẫu đã cố tình có:

- **Mã 8:** giá bằng 100000 nhưng trạng thái **PENDING**, phải bị loại.
- **Mã 7:** trạng thái **PAID** nhưng giá bằng 500000, phải bị loại.
- **Mã 3, 9, 10:** PAID và giá bằng 100000, phải được giữ.
- **Mã 4:** PAID và giá ngay trên ngưỡng, phải được giữ.
- **Mã 5:** tổng tiền NULL nhưng trạng thái CANCELLED, không được giữ.
- **Mã 6:** PAID nhưng giá âm, không được giữ.

### 11.1. Kiểm tra dấu ngoặc khi trộn AND với OR

Xét yêu cầu: “Chọn đơn PAID có tổng tiền từ 100000 trở lên **hoặc** đơn PENDING cần theo dõi bất kể giá”.

Cách đúng ý định:

~~~sql
SELECT ma_don_hang
FROM don_hang
WHERE (trang_thai = 'PAID' AND tong_tien >= 100000)
   OR trang_thai = 'PENDING'
ORDER BY ma_don_hang;
~~~

Kết quả: **3, 4, 7, 8, 9, 10**.

Nhưng nếu viết:

~~~sql
WHERE trang_thai = 'PAID'
  AND (tong_tien >= 100000 OR trang_thai = 'PENDING')
~~~

sẽ **không chọn mã 8**, vì điều kiện ngoài yêu cầu trang_thai phải PAID. Một thay đổi dấu ngoặc có thể biến điều kiện nghiệp vụ thành một điều kiện khác hoàn toàn.

### 11.2. Độ bao phủ điều kiện với nhiều nhánh

Với các điều kiện A, B, C, bộ thử tốt cần có dòng:

1. **Chỉ A đúng**, B/C sai.
2. **Chỉ B đúng**, A/C sai.
3. **Chỉ C đúng**, A/B sai.
4. **A và B cùng đúng**.
5. **Không điều kiện nào đúng**.
6. **Một vế UNKNOWN** do NULL, các vế còn lại TRUE/FALSE.
7. **Đúng ngay biên** của một so sánh nằm bên trong nhánh.

Không nhất thiết thử mọi tổ hợp nếu số điều kiện rất lớn. Có thể áp dụng **phân hoạch tương đương**, **kiểm thử giá trị biên** và kỹ thuật thay đổi từng điều kiện quan trọng để chọn tập nhỏ nhưng có khả năng phát hiện lỗi.

### 11.3. Không dựa vào AND/OR để bảo đảm thứ tự tính toán

Xem điều kiện có nguy cơ chia cho 0:

~~~sql
-- Không nên coi thứ tự chữ viết là bảo đảm phép chia luôn an toàn.
WHERE so_luong <> 0
  AND tong_tien / so_luong > 1000
~~~

Bộ tối ưu SQL có thể biến đổi biểu thức; quy tắc xử lý lỗi và thứ tự đánh giá không nên dựa vào “đánh giá vế trái trước” như một bảo đảm chung.

Một cách diễn đạt tránh mẫu số 0 là:

~~~sql
WHERE tong_tien / NULLIF(so_luong, 0) > 1000
~~~

Khi so_luong = 0, **NULLIF(so_luong, 0)** trả NULL và biểu thức chia thường cho NULL, tiếp đó điều kiện so sánh cho UNKNOWN, hàng bị lọc. Vẫn cần kiểm tra tính hợp lệ của số lượng, kiểu dữ liệu và lỗi khác theo DBMS thực tế.

## 12. IN và NOT IN với tập rỗng, phần tử trùng và NULL

### 12.1. IN không yêu cầu mỗi giá trị chỉ xuất hiện một lần

~~~sql
WHERE trang_thai IN ('PAID', 'PAID', 'PENDING')
~~~

Về ý nghĩa chọn hàng, giá trị **PAID** bị lặp trong danh sách không làm một đơn hàng xuất hiện hai lần. Một hàng có thể khớp nhiều phần tử, nhưng WHERE chỉ quyết định có giữ hàng đó hay không.

Bộ thử cần có hàng:

- Khớp phần tử đầu tiên.
- Khớp phần tử cuối cùng.
- Không khớp phần tử nào.
- Giá trị cột NULL.
- Giá trị khác hoa/thường hoặc chứa khoảng trắng.
- Danh sách đầu vào rỗng ở phía ứng dụng.

### 12.2. Danh sách rỗng

~~~sql
WHERE ma_don_hang IN ()
~~~

không phải cú pháp SQL được hỗ trợ thống nhất và thường bị từ chối. Nếu ứng dụng nhận danh sách mã rỗng, cần có **hợp đồng** rõ ràng:

- “Chỉ lấy các mã nằm trong danh sách” với danh sách rỗng → không lấy hàng nào.
- “Nếu không chọn mã nào thì bỏ bộ lọc mã” → không áp dụng điều kiện theo mã.

Hai ý nghĩa khác nhau dẫn đến hai câu truy vấn khác nhau. Trong mã ứng dụng, không nên tạo IN () một cách máy móc.

### 12.3. NOT IN gặp NULL

~~~sql
SELECT ma_don_hang
FROM don_hang
WHERE ma_don_hang NOT IN (2, NULL);
~~~

Với mã khác 2, một phép so sánh với NULL tạo UNKNOWN; **NOT IN** có thể cho UNKNOWN, và WHERE không chọn hàng. Mã 2 thì IN TRUE, NOT IN FALSE nên cũng bị loại. Kết quả ví dụ này là **rỗng**.

Đây là bẫy quan trọng khi danh sách lấy từ truy vấn con có cột có thể NULL:

~~~sql
-- Rủi ro nếu s.ma_don_hang chứa NULL.
SELECT d.ma_don_hang
FROM don_hang d
WHERE d.ma_don_hang NOT IN (
    SELECT s.ma_don_hang
    FROM don_bi_chan s
);
~~~

Với bài toán “không có bản ghi bị chặn tương ứng”, có thể viết:

~~~sql
SELECT d.ma_don_hang
FROM don_hang d
WHERE NOT EXISTS (
    SELECT 1
    FROM don_bi_chan s
    WHERE s.ma_don_hang = d.ma_don_hang
);
~~~

Vì **d.ma_don_hang** là khóa chính không NULL trong mô hình minh họa, cách viết này diễn đạt rõ “không tồn tại dòng phù hợp”, và NULL trong cột phía truy vấn con không tự làm mọi hàng bị loại. Nếu cột phía ngoài có thể NULL, cần xét lại quy tắc khớp dữ liệu của nghiệp vụ.

## 13. Điều kiện JOIN: dữ liệu mồ côi và khóa NULL

Giả sử có thêm bảng:

**khach_hang**

| ma_khach_hang | ten_khach_hang |
|---:|---|
| 1 | An |
| 2 | Bình |
| 3 | Chi |

**don_hang_khach**

| ma_don_hang | ma_khach_hang | trang_thai |
|---:|---:|---|
| 101 | 1 | PAID |
| 102 | 1 | PENDING |
| 103 | 2 | CANCELLED |
| 104 | NULL | PAID |

Bảng đơn 104 cố tình có mã khách NULL để thử trường hợp dữ liệu thiếu quan hệ.

### 13.1. INNER JOIN chỉ tạo cặp khớp khi ON TRUE

~~~sql
SELECT
    k.ma_khach_hang,
    k.ten_khach_hang,
    d.ma_don_hang
FROM khach_hang k
JOIN don_hang_khach d
    ON d.ma_khach_hang = k.ma_khach_hang
ORDER BY k.ma_khach_hang, d.ma_don_hang;
~~~

Kết quả gồm **(1,101)**, **(1,102)**, **(2,103)**.

Mã đơn **104** không khớp dòng khách nào vì **NULL = k.ma_khach_hang** cho UNKNOWN. Khách Chi (3) cũng không có đơn khớp. Các cặp có điều kiện ON FALSE hoặc UNKNOWN đều không được INNER JOIN chọn.

### 13.2. LEFT JOIN: biên của “không tồn tại đơn phù hợp”

~~~sql
SELECT k.ma_khach_hang, k.ten_khach_hang, d.ma_don_hang
FROM khach_hang k
LEFT JOIN don_hang_khach d
    ON d.ma_khach_hang = k.ma_khach_hang
ORDER BY k.ma_khach_hang, d.ma_don_hang;
~~~

Truy vấn giữ cả khách Chi, với **d.ma_don_hang = NULL** do không có hàng khớp. Đây là NULL do **bước outer join đệm vào**, không nhất thiết là NULL có sẵn trong bảng đơn.

Nếu cần tìm những khách không có bất kỳ đơn nào:

~~~sql
SELECT k.ma_khach_hang, k.ten_khach_hang
FROM khach_hang k
WHERE NOT EXISTS (
    SELECT 1
    FROM don_hang_khach d
    WHERE d.ma_khach_hang = k.ma_khach_hang
);
~~~

Kết quả: **Chi (3)**.

Một bài kiểm thử quan trọng là “khách **có đơn nhưng không có đơn PAID**” khác với “khách **không có bất kỳ đơn nào**”. Phải thay đổi điều kiện EXISTS/NOT EXISTS tương ứng.

### 13.3. Đưa điều kiện từ ON sang WHERE có thể đổi kết quả

Mục tiêu: “giữ mọi khách, ghép đơn PAID nếu có”.

~~~sql
SELECT k.ten_khach_hang, d.ma_don_hang
FROM khach_hang k
LEFT JOIN don_hang_khach d
    ON d.ma_khach_hang = k.ma_khach_hang
   AND d.trang_thai = 'PAID';
~~~

Kết quả logic gồm **An — 101**, **Bình — NULL**, **Chi — NULL**.

Nếu chuyển **d.trang_thai = 'PAID'** vào WHERE, Bình và Chi sẽ bị loại. Với Chi, cột phía đơn là NULL, điều kiện WHERE nhận UNKNOWN; với Bình, dòng đơn CANCELLED khiến điều kiện FALSE. Dữ liệu thử cần có đủ cả **không có đơn** và **có đơn không đúng trạng thái** để phát hiện lỗi.

## 14. Dữ liệu trùng, quan hệ một-nhiều và điều kiện lọc

Một hàng ở bảng trái có thể ghép với nhiều hàng phía phải. Do đó:

~~~sql
SELECT k.ma_khach_hang, d.ma_don_hang
FROM khach_hang k
JOIN don_hang_khach d
    ON d.ma_khach_hang = k.ma_khach_hang
WHERE k.ma_khach_hang = 1;
~~~

trả **hai dòng** cho khách An, vì có đơn 101 và 102.

Nếu ứng dụng cần “khách có ít nhất một đơn” mà không muốn nhân bản khách, dùng EXISTS:

~~~sql
SELECT k.ma_khach_hang, k.ten_khach_hang
FROM khach_hang k
WHERE EXISTS (
    SELECT 1
    FROM don_hang_khach d
    WHERE d.ma_khach_hang = k.ma_khach_hang
);
~~~

Kiểm thử trường hợp **0, 1 và nhiều dòng liên quan** sẽ phân biệt rõ giữa truy vấn JOIN và truy vấn EXISTS.

Nếu có dữ liệu trùng ngoài dự kiến, cần xác định đó là lỗi dữ liệu hay đặc trưng mô hình. **SELECT DISTINCT** có thể loại trùng ở kết quả, nhưng không tự giải quyết nguyên nhân trùng bản ghi hoặc thiếu ràng buộc duy nhất.

## 15. Điều kiện với tổng hợp và HAVING

WHERE lọc **hàng đầu vào**, còn HAVING lọc **nhóm sau GROUP BY** theo mô hình logic.

Giả sử cần tìm trạng thái có ít nhất **hai đơn**:

~~~sql
SELECT trang_thai, COUNT(*) AS so_don
FROM don_hang
GROUP BY trang_thai
HAVING COUNT(*) >= 2;
~~~

Với tập dữ liệu mẫu:

- PAID có 8 đơn (**1, 2, 3, 4, 6, 7, 9, 10**).
- PENDING có 1 đơn (**8**).
- CANCELLED có 1 đơn (**5**).

Kết quả chỉ có **PAID — 8**.

Thử các ranh giới số lượng **0, 1, 2, 3**, đặc biệt đúng bằng 2. Tập dữ liệu chỉ có nhóm 8 và nhóm 1 không trực tiếp thử được cận 2: bộ test cần bổ sung một nhóm gồm chính xác hai hàng nếu muốn kiểm tra lỗi **HAVING COUNT(*) > 2** so với **>= 2**.

### 15.1. COUNT(*) và COUNT(cot) khác nhau khi có NULL

~~~sql
SELECT
    COUNT(*) AS so_don,
    COUNT(tong_tien) AS so_don_co_tien
FROM don_hang;
~~~

Trong dữ liệu mẫu:

- **COUNT(*) = 10**.
- **COUNT(tong_tien) = 9** vì mã 5 có tổng tiền NULL.

Bộ kiểm thử cần có ít nhất một hàng NULL để bắt lỗi dùng COUNT(cot) khi yêu cầu đếm mọi hàng.

### 15.2. SUM của nhóm toàn NULL

Với các hàm tổng hợp như SUM và AVG, SQL thông thường bỏ qua giá trị NULL. Nếu nhóm có các dòng nhưng toàn bộ giá trị đem tổng hợp là NULL, **SUM** trả NULL chứ không tự trả 0.

Ví dụ:

~~~sql
SELECT trang_thai, SUM(tong_tien) AS tong
FROM don_hang
GROUP BY trang_thai
HAVING SUM(tong_tien) >= 0;
~~~

Nhóm **CANCELLED** chỉ có một giá trị tong_tien NULL nên SUM trả NULL; **NULL >= 0** là UNKNOWN, nhóm bị HAVING loại.

Nếu nghiệp vụ muốn coi tổng không có giá trị là 0, có thể biểu diễn:

~~~sql
HAVING COALESCE(SUM(tong_tien), 0) >= 0
~~~

Nhưng đây là **quy tắc nghiệp vụ về dữ liệu thiếu**, không phải phép thay thế luôn an toàn. Khi kiểm thử, phân biệt nhóm có **0 thật**, nhóm toàn NULL và nhóm không có dòng đầu vào.

## 16. Quy tắc dữ liệu: điều kiện lọc và ràng buộc không giống nhau

Một bộ lọc có thể phát hiện dữ liệu sai:

~~~sql
SELECT ma_don_hang, tong_tien
FROM don_hang
WHERE tong_tien < 0
   OR tong_tien IS NULL;
~~~

Tuy nhiên, phát hiện sai sau khi dữ liệu đã được lưu không thay thế cho việc **ngăn dữ liệu sai ngay khi ghi**.

Nếu quy tắc yêu cầu:

- Mã đơn duy nhất, không NULL.
- Trạng thái chỉ nhận giá trị được cho phép.
- Tổng tiền luôn không âm.
- Thời điểm tạo đơn bắt buộc có giá trị.

thì lược đồ có thể dùng **PRIMARY KEY**, **NOT NULL**, **CHECK**, **FOREIGN KEY** và các quy tắc bổ sung ở tầng ứng dụng.

### 16.1. CHECK có khác WHERE ở UNKNOWN

Giả sử:

~~~sql
CREATE TABLE so_lieu (
    ma INTEGER PRIMARY KEY,
    so_luong INTEGER,
    CHECK (so_luong > 0)
);
~~~

Nếu **so_luong = NULL**, điều kiện CHECK thường có kết quả UNKNOWN. Ràng buộc CHECK theo SQL thông thường **không từ chối UNKNOWN**, chỉ từ chối FALSE. Trong khi:

~~~sql
SELECT *
FROM so_lieu
WHERE so_luong > 0;
~~~

sẽ không chọn dòng NULL.

Do đó, để bắt buộc số lượng phải lớn hơn 0 và có mặt:

~~~sql
CREATE TABLE so_lieu (
    ma INTEGER PRIMARY KEY,
    so_luong INTEGER NOT NULL,
    CHECK (so_luong > 0)
);
~~~

Một bộ kiểm thử nên thử cả **NULL, 0, 1 và -1** để phân biệt ràng buộc NOT NULL với CHECK. Khả năng thực thi CHECK cần kiểm tra theo phiên bản DBMS.

### 16.2. Không dùng bộ lọc để “sửa ngầm” dữ liệu sai

Nếu dữ liệu có giá âm, một câu:

~~~sql
WHERE tong_tien >= 0
~~~

sẽ bỏ qua hàng bất thường trong báo cáo nhưng không làm biến mất vấn đề chất lượng dữ liệu. Với những báo cáo cần kiểm toán, cần cân nhắc vừa lọc kết quả nghiệp vụ vừa thống kê riêng các bản ghi không hợp lệ, hoặc đặt cơ chế cảnh báo ở quá trình nhập dữ liệu.

## 17. Bản ghi mới, thứ tự thay đổi và bộ lọc phân trang

Bộ lọc thường đi cùng ORDER BY và phân trang. Ví dụ:

~~~sql
SELECT ma_don_hang, tong_tien
FROM don_hang
WHERE tong_tien >= 100000
ORDER BY tong_tien DESC, ma_don_hang ASC;
~~~

Một lỗi kiểm thử là giả định truy vấn không có ORDER BY sẽ luôn trả dòng theo thứ tự nhập. **SQL không cam kết thứ tự nếu không có ORDER BY ngoài cùng**.

Khi nhiều dòng có cùng tong_tien = 100000 (mã 3, 8, 9, 10), ORDER BY chỉ theo tong_tien không xác định thứ tự của những dòng hòa. Thêm khóa duy nhất như ma_don_hang làm tiêu chí phụ.

Nếu dùng phân trang OFFSET, dữ liệu được chèn/xóa giữa hai lần lấy trang có thể làm một dòng xuất hiện lại hoặc bị bỏ qua, dù ORDER BY đã ổn định trong từng lần gọi. Đối với nhu cầu đọc liên tục trong dữ liệu thay đổi, cân nhắc:

- Mức nhất quán của giao dịch/snapshot phù hợp.
- Phân trang theo khóa (**keyset pagination**) khi hợp lý.
- Cách xử lý khi một hàng đổi giá trị dùng trong điều kiện lọc hoặc sắp xếp.

Đây là trường hợp biên về **thời điểm hệ thống thay đổi**, không chỉ về giá trị của một cột.

## 18. Kiểm thử tính năng tìm kiếm: từ yêu cầu đến bảng quyết định

Ví dụ yêu cầu:

> “Chỉ hiển thị các đơn **PAID**, có tổng tiền **từ 100000 đến dưới 500000**, được tạo trong **tháng 3/2026**.”

Câu truy vấn:

~~~sql
SELECT
    ma_don_hang,
    trang_thai,
    tong_tien,
    tao_luc
FROM don_hang
WHERE trang_thai = 'PAID'
  AND tong_tien >= 100000
  AND tong_tien < 500000
  AND tao_luc >= ?
  AND tao_luc < ?
ORDER BY ma_don_hang;
~~~

Bind hai tham số thời gian:

- Bắt đầu: **2026-03-01 00:00:00**.
- Kết thúc loại trừ: **2026-04-01 00:00:00**.

Theo dữ liệu mẫu, kết quả mong đợi là **mã 4, 9, 10**.

### 18.1. Bảng quyết định theo từng hàng

| Mã | PAID? | 100000 ≤ tiền < 500000? | Trong tháng 3? | Chọn? |
|---:|---|---|---|---|
| 1 | Có | Không | Có | Không |
| 2 | Có | Không | Có | Không |
| 3 | Có | Có | Không | Không |
| 4 | Có | Có | Có | **Có** |
| 5 | Không | UNKNOWN (NULL) | UNKNOWN (NULL) | Không |
| 6 | Có | Không | Không | Không |
| 7 | Có | Không (bằng cận trên) | Không | Không |
| 8 | Không | Có | Có | Không |
| 9 | Có | Có | Có | **Có** |
| 10 | Có | Có | Có | **Có** |

Bảng này đóng vai trò **oracle** cho bài thử: trước khi chạy truy vấn, ta đã viết rõ những mã nào phải được chọn. Nếu kết quả thực tế khác, cần kiểm tra từng điều kiện, dữ liệu đã lưu và cấu hình DBMS.

### 18.2. Kết quả mong đợi khi đổi đúng một biên

Giả sử yêu cầu đổi từ **tong_tien < 500000** sang **tong_tien <= 500000**. Trong tập dữ liệu hiện tại, **mã 7** sẽ đạt điều kiện tiền nhưng vẫn **không** được chọn vì thời gian nằm ngoài tháng 3. Vì vậy, nếu chỉ so sánh **kết quả cuối cùng**, bộ thử tổng hợp **không phát hiện được** lỗi ở cận 500000.

Đây là điểm quan trọng trong thiết kế dữ liệu: để kiểm tra riêng biên trên, cần có một hàng **PAID**, tiền **500000** và thời điểm **nằm trong tháng 3**. Ta có thể bổ sung một hàng kiểm thử mới vào bộ dữ liệu, hoặc viết một bài thử riêng cho bộ lọc tiền. Không nên cho rằng cứ có giá bằng cận trên trong bảng là chắc chắn đã kiểm tra được biên đó khi còn các điều kiện AND khác.

### 18.3. Thiết kế test tách từng yếu tố

Một bộ test hiệu quả gồm:

1. **Test riêng cho từng điều kiện:** tiền, trạng thái, thời gian.
2. **Test kết hợp các điều kiện:** các hàng cùng lúc thỏa tất cả, chỉ sai một điều kiện, sai nhiều điều kiện.
3. **Test trường hợp NULL:** từng cột có thể NULL và nhiều cột NULL đồng thời.
4. **Test tính bất biến kết quả:** đổi thứ tự nhập dữ liệu, thêm hàng không liên quan, thay đổi số lượng dòng trùng giá.
5. **Test theo DBMS mục tiêu:** collation, kiểu ngày giờ, độ chính xác số, chế độ ép kiểu.

Một bài thử kết hợp nhiều điều kiện chỉ kiểm chứng đầy đủ khi có dữ liệu làm **mỗi điều kiện ảnh hưởng thật đến kết quả**.

## 19. Kiểm thử truy vấn bằng CASE để quan sát ba trạng thái

Khi điều kiện khó hiểu, có thể viết một truy vấn chẩn đoán **đặt nhãn cho từng hàng**:

~~~sql
SELECT
    ma_don_hang,
    tong_tien,
    CASE
        WHEN tong_tien >= 100000 THEN 'TRUE'
        WHEN NOT (tong_tien >= 100000) THEN 'FALSE'
        ELSE 'UNKNOWN'
    END AS ket_qua_kiem_tra
FROM don_hang
ORDER BY ma_don_hang;
~~~

Kết quả với các biên quan trọng:

| Mã | Tổng tiền | Nhãn |
|---:|---:|---|
| 1 | 0.00 | FALSE |
| 2 | 99999.99 | FALSE |
| 3 | 100000.00 | TRUE |
| 4 | 100000.01 | TRUE |
| 5 | NULL | UNKNOWN |
| 6 | -1.00 | FALSE |
| 7 | 500000.00 | TRUE |

Các nhãn **'TRUE'**, **'FALSE'**, **'UNKNOWN'** trong ví dụ chỉ là **chuỗi văn bản do CASE trả về** để minh họa, không đòi DBMS phải có một kiểu Boolean ba giá trị để hiển thị.

Dùng CASE làm truy vấn chẩn đoán giúp người học thấy rõ rằng một hàng bị WHERE loại vì **FALSE** hay vì **UNKNOWN**. Đây là thông tin có ích khi điều kiện chứa nhiều NULL.

## 20. Kiểm thử với tập dữ liệu nhỏ độc lập

Khi chưa muốn tạo bảng thật, bạn có thể dựng một tập giá trị nhỏ trong CTE hoặc bảng tạm. Cú pháp tạo các hàng hằng khác nhau theo DBMS; ví dụ dưới đây dùng các phép SELECT với biểu thức số, phù hợp với một số DBMS như PostgreSQL, SQL Server, SQLite và MySQL ở các phiên bản hỗ trợ cách viết này.

~~~sql
WITH gia_tri_thu AS (
    SELECT 1 AS stt, CAST(99999.99 AS DECIMAL(12, 2)) AS x
    UNION ALL
    SELECT 2, CAST(100000.00 AS DECIMAL(12, 2))
    UNION ALL
    SELECT 3, CAST(100000.01 AS DECIMAL(12, 2))
    UNION ALL
    SELECT 4, CAST(NULL AS DECIMAL(12, 2))
)
SELECT
    stt,
    x,
    CASE
        WHEN x >= 100000 THEN 'CHON'
        WHEN x < 100000 THEN 'LOAI'
        ELSE 'KHONG_XAC_DINH'
    END AS danh_gia
FROM gia_tri_thu
ORDER BY stt;
~~~

Kết quả mong đợi:

| stt | x | danh_gia |
|---:|---:|---|
| 1 | 99999.99 | LOAI |
| 2 | 100000.00 | CHON |
| 3 | 100000.01 | CHON |
| 4 | NULL | KHONG_XAC_DINH |

**Lưu ý:** Oracle Database ở các phiên bản cũ có thể cần **FROM DUAL** trong mỗi SELECT hằng; SQLite không có cùng quy tắc kiểu DECIMAL chặt như một số hệ khác. Nếu thử trên nhiều DBMS, điều chỉnh cú pháp tạo dữ liệu thử nhưng giữ nguyên **bảng giá trị và kết quả mong đợi**.

## 21. Tham số hóa để kết quả kiểm thử có ý nghĩa

Nếu lấy giá trị tìm kiếm từ người dùng, không nên ghép chuỗi trực tiếp vào SQL:

~~~java
// Không nên:
String sql = "SELECT * FROM don_hang WHERE tong_tien >= " + rawInput;
~~~

Cách này có thể tạo SQL injection, lỗi định dạng số hoặc lỗi dấu phân cách tùy ngôn ngữ. Với JDBC:

~~~java
String sql = """
    SELECT ma_don_hang, tong_tien
    FROM don_hang
    WHERE tong_tien >= ?
      AND tong_tien < ?
    ORDER BY ma_don_hang
    """;

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setBigDecimal(1, new java.math.BigDecimal("100000.00"));
    ps.setBigDecimal(2, new java.math.BigDecimal("500000.00"));

    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            System.out.println(
                rs.getInt("ma_don_hang") + " : "
                + rs.getBigDecimal("tong_tien")
            );
        }
    }
}
~~~

Với dữ liệu mẫu, kết quả là **3, 4, 8, 9, 10**. Đặc biệt, **BigDecimal("100000.00")** biểu diễn giá trị thập phân đã xác định, tránh tạo đầu vào từ một phép tính số thực nhị phân không cần thiết.

### 21.1. Bind biên thời gian

~~~java
String sql = """
    SELECT ma_don_hang
    FROM don_hang
    WHERE tao_luc >= ?
      AND tao_luc < ?
    ORDER BY ma_don_hang
    """;

java.time.LocalDateTime start =
    java.time.LocalDateTime.of(2026, 3, 1, 0, 0);
java.time.LocalDateTime end =
    java.time.LocalDateTime.of(2026, 4, 1, 0, 0);

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setObject(1, start);
    ps.setObject(2, end);

    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            System.out.println(rs.getInt("ma_don_hang"));
        }
    }
}
~~~

Ví dụ giả định **tao_luc** là một kiểu TIMESTAMP không có múi giờ và driver hỗ trợ ánh xạ **LocalDateTime** tương ứng. Nếu cột biểu diễn thời điểm tuyệt đối, ứng dụng cần chuyển các biên từ vùng giờ nghiệp vụ sang **Instant/OffsetDateTime** hoặc kiểu tương đương được driver hỗ trợ, thay vì bind LocalDateTime thiếu ngữ cảnh múi giờ.

### 21.2. Ký hiệu tham số không thay đổi ngữ nghĩa NULL

Nếu bind giá trị Java NULL cho:

~~~sql
WHERE email = ?
~~~

phép so sánh SQL vẫn không tương đương **email IS NULL**. Bộ lọc tùy chọn phải phân biệt hai ý nghĩa:

- **Không truyền email** → có thể là bỏ qua bộ lọc.
- **Chủ động yêu cầu email chưa có** → dùng email IS NULL.
- **Truyền email cụ thể** → dùng email = ? và bind giá trị.

Thiết kế bộ thử nên có cả ba trường hợp; không gộp chúng thành một nhánh xử lý NULL mơ hồ.

## 22. Kiểm tra hành vi khi dữ liệu thay đổi giữa các truy vấn

Trong hệ thống đồng thời, các tình huống biên còn xuất hiện khi trạng thái đơn hoặc tổng tiền thay đổi.

Ví dụ:

1. Lần đọc thứ nhất thấy đơn 9 là PAID, tổng tiền 100000.
2. Một giao dịch khác đổi tổng tiền thành 99999.99 hoặc đổi trạng thái thành CANCELLED.
3. Lần đọc thứ hai chạy cùng WHERE nhưng kết quả khác.

Đó không nhất thiết là lỗi WHERE; nó có thể là kết quả hợp lệ theo **mức cô lập giao dịch** và thời điểm dữ liệu được đọc. Với bài kiểm thử tính đúng đắn của điều kiện, cần:

- Cố định dữ liệu đầu vào hoặc giao dịch/snapshot thích hợp.
- Xác định đang kiểm thử **kết quả tại một thời điểm** hay **tính nhất quán giữa nhiều lần đọc**.
- Không khẳng định hai lần truy vấn phải giống nhau nếu dữ liệu được phép thay đổi.
- Nếu có kiểm thử đồng thời, xác định kết quả nào được chấp nhận theo thiết kế giao dịch.

Với bộ lọc “đơn tạo gần đây”, tránh phụ thuộc đồng hồ thật; nên cố định mốc thời gian cho kịch bản kiểm thử.

## 23. Cách tổ chức một bộ test cho điều kiện lọc

Một bộ test dễ duy trì cần có **yêu cầu bằng lời**, **dữ liệu đầu vào**, **câu SQL hoặc API gọi truy vấn**, **danh sách mã mong đợi** và **DBMS/phiên bản thử**.

Ví dụ bản đặc tả:

| Trường | Giá trị |
|---|---|
| Tên ca | Lọc đơn có giá từ ngưỡng |
| Nguồn | don_hang (tập dữ liệu mục 3) |
| Điều kiện | tong_tien >= 100000 |
| Trường hợp biên | 99999.99, 100000.00, 100000.01, NULL |
| Mã mong đợi | 3, 4, 7, 8, 9, 10 |
| Thứ tự so sánh | Sắp xếp theo ma_don_hang |
| Môi trường | DBMS/phiên bản/driver cấu hình cho test |
| Điều cần phát hiện | Dùng > thay cho >=; nhầm NULL thành 0 |

### 23.1. Các nhóm dữ liệu nên có

| Nhóm | Những hàng thử điển hình | Mục tiêu phát hiện |
|---|---|---|
| **Biên thấp** | B−ε, B, B+ε | Sai < / <= / > / >= |
| **Biên cao** | U−ε, U, U+ε | Sai cận trên bao gồm/loại trừ |
| **NULL** | NULL ở từng cột liên quan | Nhầm UNKNOWN với FALSE hoặc 0 |
| **Chuỗi rỗng/trắng** | '', ' ', '  abc  ' | Nhầm thiếu dữ liệu hoặc trim |
| **Unicode/collation** | Hoa/thường, có/không dấu, chuẩn hóa khác nhau | So khớp văn bản khác kỳ vọng |
| **Giá trị bất hợp lệ** | Số âm, dữ liệu ngoài miền, giá quá lớn | Thiếu ràng buộc, chuyển kiểu sai |
| **Trạng thái khác nhau** | PAID, PENDING, CANCELLED | Lỗi AND/OR |
| **Quan hệ** | 0, 1, nhiều dòng khớp | JOIN nhân dòng, EXISTS/NOT EXISTS |
| **Ngày giờ** | Ngay trước, đúng tại, ngay sau ranh giới | Sai cuối ngày/tháng hoặc múi giờ |
| **Tập kết quả** | 0, 1, nhiều dòng, các dòng hòa thứ tự | Kết quả rỗng, phân trang không ổn định |
| **Đồng thời** | Giá/trạng thái đổi trong khi đọc | Nhầm khác biệt snapshot với lỗi điều kiện |

### 23.2. Kiểm thử tự động cần có dữ liệu mong đợi rõ ràng

Pseudocode minh họa:

~~~text
seedDatabaseWithKnownRows()

actualIds = queryIds(
    "SELECT ma_don_hang FROM don_hang " +
    "WHERE trang_thai = ? " +
    "AND tong_tien >= ? " +
    "AND tong_tien < ? " +
    "ORDER BY ma_don_hang",
    ["PAID", 100000.00, 500000.00]
)

expectedIds = [3, 4, 9, 10]

assert actualIds == expectedIds
~~~

Dữ liệu mẫu được nạp vào môi trường kiểm thử biệt lập. **Đừng** chỉ khẳng định “truy vấn trả ít nhất một dòng” hoặc “không bị lỗi SQL”; bài kiểm thử như vậy không phát hiện được các hàng sai nằm gần biên.

Khi thứ tự không phải một phần của yêu cầu, so sánh **tập mã** thay vì thứ tự. Nếu yêu cầu có ORDER BY, kiểm tra cả thứ tự và các trường hợp nhiều hàng có giá trị sắp xếp bằng nhau.

### 23.3. Thử sau khi thay đổi DBMS hoặc schema

Một bộ lọc SQL có thể thay đổi kết quả nếu:

- Kiểu cột đổi từ INTEGER sang DECIMAL hoặc từ TIMESTAMP sang DATE.
- Collation thay đổi quy tắc phân biệt chữ hoa/dấu.
- Độ chính xác của cột thời gian đổi.
- Một cột trước đây NOT NULL nay cho phép NULL.
- Driver đổi cách bind giá trị ngày, giờ hoặc số.
- DBMS thay đổi hành vi ép kiểu, quy tắc literal hoặc chế độ SQL.
- Chỉ mục/migration khiến kế hoạch thực thi đổi, làm lộ giả định sai về thứ tự dòng khi không có ORDER BY.

Vì vậy, bộ test giá trị biên nên chạy lại sau các thay đổi ảnh hưởng kiểu dữ liệu, truy vấn, migration hoặc cấu hình cơ sở dữ liệu.

## 24. Những lỗi thường gặp

| Lỗi | Vì sao khó nhận thấy khi chỉ thử dữ liệu “đẹp”? | Hướng xử lý |
|---|---|---|
| Dùng **>** thay **>=** | Giá trị xa ngưỡng vẫn cho kết quả như nhau | Thử bằng chính xác ngưỡng |
| Dùng **BETWEEN** cho cận trên loại trừ | Giá trị bên trong khoảng vẫn giống nhau | Thử đúng cận trên |
| Dùng **23:59:59** làm cuối ngày | Mất bản ghi có phần lẻ giây | Lọc [đầu ngày, đầu ngày kế tiếp) |
| So sánh **= NULL** | Không chọn dòng thiếu dữ liệu | Dùng IS NULL |
| Coi **NULL** bằng 0 | Trường hợp thông thường không khác | Thử riêng NULL và 0 |
| Lọc bằng **NOT** rồi tưởng sẽ gồm NULL | NOT UNKNOWN vẫn UNKNOWN | Nêu chính sách với NULL |
| **NOT IN** có NULL trong tập con | Kết quả có thể rỗng ngoài dự kiến | Lọc NULL hoặc dùng NOT EXISTS phù hợp |
| Đưa điều kiện phía phải LEFT JOIN vào WHERE | Khách không có dòng khớp bị loại | Phân biệt điều kiện ON và WHERE |
| So sánh chuỗi chưa xác định collation | Chữ hoa/dấu và khoảng trắng làm kết quả lệch | Quy định so khớp rồi kiểm thử |
| Dùng FLOAT cho ngưỡng tiền | Có sai số biểu diễn | Dùng DECIMAL/BigDecimal đúng quy tắc |
| Ép kiểu chuỗi sai định dạng ngay trong WHERE | DBMS có thể lỗi hoặc ép kiểu bất ngờ | Kiểm tra và chuyển dữ liệu có kiểm soát |
| Dùng COUNT(cot) để đếm mọi dòng | Bỏ qua cột NULL | Dùng COUNT(*) nếu muốn đếm dòng |
| Dùng cùng một hàng để thử nhiều điều kiện AND | Một điều kiện sai khác che mất lỗi ở biên | Thiết kế hàng thỏa các điều kiện khác khi kiểm tra từng biên |
| Không có ORDER BY nhưng kiểm tra thứ tự | Thứ tự không được cam kết | Sắp xếp tường minh hoặc so tập |
| Chỉ kiểm tra truy vấn “chạy được” | Sai số hàng vẫn lọt | So kết quả với oracle xác định trước |
| Test dùng đồng hồ/dữ liệu thay đổi | Kết quả không tái lập | Cố định thời gian và dữ liệu test |

## 25. Bài tập thực hành

### Bài 1 — Biên dưới

Yêu cầu: “Tìm đơn có tong_tien **ít nhất 100000**”.

**Câu hỏi:** Trong ba giá trị **99999.99**, **100000.00**, **100000.01**, giá trị nào phải được chọn? Viết điều kiện SQL.

<details>
<summary>Gợi ý đáp án</summary>

Chọn **100000.00** và **100000.01**; loại **99999.99**.

~~~sql
WHERE tong_tien >= 100000
~~~

</details>

### Bài 2 — Biên trên

Yêu cầu: “Tổng tiền nhỏ hơn 500000, không bao gồm 500000”.

**Câu hỏi:** **499999.99**, **500000.00**, **500000.01** có được chọn không?

<details>
<summary>Gợi ý đáp án</summary>

Chỉ **499999.99** được chọn.

~~~sql
WHERE tong_tien < 500000
~~~

</details>

### Bài 3 — NULL trong điều kiện phủ định

Cho dòng có **tong_tien = NULL**:

~~~sql
WHERE NOT (tong_tien >= 100000)
~~~

Dòng có được giữ không? Nếu muốn giữ thêm dòng chưa có tổng tiền, viết lại thế nào?

<details>
<summary>Gợi ý đáp án</summary>

Không. Phép so sánh tạo UNKNOWN, phủ định vẫn UNKNOWN, WHERE loại dòng.

~~~sql
WHERE tong_tien < 100000
   OR tong_tien IS NULL
~~~

</details>

### Bài 4 — Cận thời gian

Yêu cầu: “Tìm đơn thuộc tháng 3/2026” với **tao_luc** là TIMESTAMP.

**Câu hỏi:** Có nên dùng <= 2026-03-31 23:59:59 làm cận trên không? Viết điều kiện ít rủi ro hơn.

<details>
<summary>Gợi ý đáp án</summary>

Không nên, vì thời điểm **23:59:59.500** vẫn thuộc tháng 3 nhưng lớn hơn 23:59:59.

~~~sql
WHERE tao_luc >= ?
  AND tao_luc < ?
~~~

Bind cận đầu **2026-03-01 00:00:00**, cận cuối **2026-04-01 00:00:00**, sau khi đã xác định múi giờ/ngữ nghĩa kiểu thời gian.

</details>

### Bài 5 — Dữ liệu sai

Trong bảng mẫu, mã đơn nào được tìm bởi:

~~~sql
SELECT ma_don_hang
FROM don_hang
WHERE tong_tien < 0 OR tong_tien IS NULL
ORDER BY ma_don_hang;
~~~

<details>
<summary>Gợi ý đáp án</summary>

**Mã 5 và 6.** Mã 5 có NULL, mã 6 có tổng tiền -1.00.

</details>

### Bài 6 — Dấu ngoặc

Yêu cầu: “Đơn PAID có tổng từ 100000 trở lên **hoặc** đơn PENDING”.

**Câu hỏi:** Viết điều kiện có dấu ngoặc và chỉ ra vì sao mã 8 phải được chọn.

<details>
<summary>Gợi ý đáp án</summary>

~~~sql
WHERE (trang_thai = 'PAID' AND tong_tien >= 100000)
   OR trang_thai = 'PENDING'
~~~

Mã 8 có trạng thái PENDING nên nhánh phải TRUE, bất kể tổng tiền thế nào. Nếu yêu cầu cả hai nhóm đều phải có tổng từ 100000 trở lên, điều kiện phải được đặt lại thành **(trang_thai IN (...)) AND tong_tien >= 100000**.

</details>

### Bài 7 — Bộ lọc tổng hợp

Với tập dữ liệu phần 3, câu truy vấn này phải trả những mã nào?

~~~sql
SELECT ma_don_hang
FROM don_hang
WHERE trang_thai = 'PAID'
  AND tong_tien >= 100000
  AND tong_tien < 500000
ORDER BY ma_don_hang;
~~~

<details>
<summary>Gợi ý đáp án</summary>

**3, 4, 9, 10**. Mã 7 bằng đúng cận trên và bị loại; mã 8 có tiền đúng ngưỡng nhưng trạng thái PENDING.

</details>

### Bài 8 — Thiết kế dữ liệu kiểm thử có sức phát hiện lỗi

Trong bộ lọc tổng hợp ở phần 18, có cần thêm một hàng PAID giá **500000** thuộc tháng 3 không? Vì sao?

<details>
<summary>Gợi ý đáp án</summary>

**Có**, nếu muốn kiểm tra trực tiếp lỗi đổi **< 500000** thành **<= 500000** ở kết quả cuối. Mã 7 hiện có giá 500000 nhưng nằm ngoài tháng 3, nên vẫn bị loại ngay cả khi cận tiền bị viết sai. Một hàng có các điều kiện khác đều đúng sẽ làm riêng biên tiền quyết định kết quả.

</details>

### Bài 9 — LEFT JOIN

Tại sao chuyển **d.trang_thai = 'PAID'** từ ON sang WHERE trong LEFT JOIN có thể làm mất khách hàng không có đơn PAID?

<details>
<summary>Gợi ý đáp án</summary>

Với LEFT JOIN, ON quyết định đơn nào được ghép nhưng vẫn giữ khách ở phía trái nếu không có đơn khớp. Khi điều kiện trạng thái được đưa xuống WHERE, dòng đã được đệm NULL từ phía đơn có **NULL = 'PAID' = UNKNOWN**, nên bị loại; dòng có trạng thái khác cũng bị loại vì FALSE.

</details>

### Bài 10 — LIKE và ký tự đặc biệt

Người dùng nhập chuỗi **"50%"** và muốn tìm sản phẩm có dấu phần trăm thật trong tên, không có ý định wildcard. PreparedStatement đã đủ để đảm bảo đúng ý định tìm kiếm chưa?

<details>
<summary>Gợi ý đáp án</summary>

Chưa. PreparedStatement giúp **tham số hóa dữ liệu SQL**, nhưng dấu **%** bên trong mẫu LIKE vẫn có ý nghĩa wildcard. Cần xử lý **escape wildcard** theo cú pháp DBMS và xác định rõ quy tắc tìm kiếm nguyên văn.

</details>

### Bài 11 — Decimal và Float

Tại sao kiểm tra **tong_tien = 0.3** có thể rủi ro nếu tong_tien được tính bằng phép cộng số thực nhị phân? Với dữ liệu tiền, giải pháp phổ biến hơn là gì?

<details>
<summary>Gợi ý đáp án</summary>

Số thực nhị phân có thể không biểu diễn chính xác các giá trị thập phân như 0.1, 0.2 hoặc 0.3. Giá trị hiển thị sau làm tròn có thể bằng 0.3 nhưng phép so sánh chính xác lại khác. Với tiền, thường dùng **DECIMAL/NUMERIC** và **BigDecimal** ở Java, kèm quy tắc scale/làm tròn được xác định.

</details>

### Bài 12 — Test WHERE hay test CHECK?

Giả sử cột **so_luong** có CHECK(so_luong > 0) nhưng không có NOT NULL. Nếu ghi so_luong = NULL, CHECK thông thường từ chối hay chấp nhận? Nếu SELECT với WHERE so_luong > 0 thì dòng có xuất hiện không?

<details>
<summary>Gợi ý đáp án</summary>

CHECK thông thường **chấp nhận UNKNOWN**, nên có thể chấp nhận NULL. WHERE chỉ giữ TRUE nên **không chọn dòng NULL**. Muốn bắt buộc số lượng dương và có mặt, cần **NOT NULL** cùng **CHECK (so_luong > 0)**.

</details>

## 26. Tổng kết kiến thức cần ghi nhớ

1. **Giá trị biên** là vị trí điều kiện có thể đổi từ chọn sang loại. Với ngưỡng, cần thử **ngay dưới — bằng — ngay trên**.
2. Với khoảng, phải ghi rõ cận dưới/cận trên được **bao gồm hay loại trừ**; **BETWEEN** bao gồm hai đầu mút.
3. Với kiểu thời gian có giờ, ưu tiên **[đầu kỳ, đầu kỳ kế tiếp)** để không bỏ sót phần lẻ giây ở cuối ngày hoặc cuối tháng.
4. **NULL không phải 0 hoặc FALSE**; WHERE chỉ giữ TRUE, nên phép so sánh cho UNKNOWN sẽ loại hàng. Dùng IS NULL/IS NOT NULL khi cần xử lý dữ liệu thiếu.
5. Dữ liệu bất thường gồm **âm, quá lớn, sai định dạng, chuỗi rỗng, khoảng trắng, Unicode, collation, thời điểm sai vùng giờ và quan hệ không khớp**.
6. Với nhiều điều kiện AND/OR, cần có dữ liệu làm **mỗi điều kiện tự quyết định kết quả**, tránh để điều kiện khác che mất lỗi ở biên.
7. **NOT IN**, **LEFT JOIN**, **COUNT(cot)**, **SUM**, **CHECK** có quy tắc riêng khi NULL xuất hiện; phải thử với tập có NULL, không suy luận bằng logic hai giá trị.
8. Một ca kiểm thử hữu ích phải có **dữ liệu đầu vào xác định, câu lọc, danh sách mã mong đợi và môi trường DBMS rõ ràng**.
9. Dùng tham số đúng kiểu và cô lập dữ liệu kiểm thử; nếu dữ liệu có thể thay đổi đồng thời, xác định ngữ nghĩa thời điểm và mức nhất quán mong muốn.
10. Truy vấn “chạy thành công” chưa đủ để kết luận đúng: phải kiểm tra chính xác **những hàng được giữ, những hàng bị loại và lý do tại từng biên**.

### Tài liệu đối chiếu khi triển khai

Để xác minh chi tiết cho một hệ quản trị cụ thể, tra cứu tài liệu chính thức ở các phần **comparison operators**, **NULL semantics**, **SELECT/WHERE**, **JOIN**, **CHECK**, **date/time types**, **collation**, **numeric types** và **query plans** của:

- PostgreSQL Documentation.
- MySQL Reference Manual.
- Microsoft Learn — Transact-SQL.
- Oracle Database SQL Language Reference.
- SQLite Documentation.

Tính chính xác của một bộ lọc còn phụ thuộc **kiểu dữ liệu, phiên bản DBMS, collation, driver và múi giờ**. Khi các yếu tố này thay đổi, cần chạy lại bộ test giá trị biên trên môi trường mục tiêu.
