# JOIN với NULL, khóa trùng và dữ liệu thiếu tham chiếu trong SQL

> **Module:** Database SQL  
> **Chương:** Kết nối bảng  
> **Bài học:** JOIN với NULL, khóa trùng và dữ liệu thiếu tham chiếu

Khi kết nối các bảng bằng **JOIN**, truy vấn không chỉ phải đúng cú pháp mà còn phải phản ánh đúng **quan hệ dữ liệu**. Một cột khóa chứa **NULL**, một mã khách hàng không tồn tại trong bảng khách, hoặc một khóa bị lặp ngoài dự kiến đều có thể khiến kết quả mất dòng, sinh dòng NULL hoặc nhân số liệu lên nhiều lần. Những lỗi này đặc biệt nguy hiểm trong báo cáo doanh thu, phân quyền, đồng bộ dữ liệu và kiểm tra tính toàn vẹn.

Bài học tập trung vào ba tình huống gắn bó với nhau:

1. **NULL trong điều kiện JOIN:** vì sao hai giá trị NULL không tự khớp khi dùng toán tử **=**, và INNER/OUTER JOIN xử lý dòng không khớp thế nào.
2. **Khóa trùng:** vì sao cùng một giá trị khóa xuất hiện nhiều lần có thể tạo nhiều cặp dòng, dẫn đến đếm và cộng tiền sai.
3. **Thiếu tham chiếu:** khi một hàng có khóa ngoại trỏ tới khóa cha không tồn tại, cách nhận diện và xử lý bằng truy vấn, ràng buộc hoặc quy trình nhập dữ liệu.

---

## 1. Mục tiêu học tập

Sau khi học, bạn có thể:

- Giải thích được ý nghĩa của **điều kiện ON** và quy tắc một cặp dòng chỉ khớp khi điều kiện có kết quả **TRUE**.
- Phân biệt **NULL có sẵn trong dữ liệu** với **NULL được sinh ra để đệm dòng trong OUTER JOIN**.
- Dự đoán kết quả của **INNER JOIN**, **LEFT JOIN**, **RIGHT JOIN**, **FULL OUTER JOIN** khi hai bảng có khóa NULL hoặc khóa không tồn tại ở bảng còn lại.
- Hiểu cách tính số dòng khi khóa trùng, đặc biệt với quan hệ **một–nhiều** và **nhiều–nhiều**.
- Phát hiện **orphan records** (bản ghi mồ côi), khóa thiếu giá trị và khóa lặp ngoài quy tắc bằng SQL.
- Sử dụng đúng **COUNT(*)**, **COUNT(cot)**, **COUNT(DISTINCT ...)**, **EXISTS/NOT EXISTS** và tổng hợp trước JOIN khi cần.
- Phân biệt đặt điều kiện lọc trong **ON** và **WHERE**, đặc biệt với LEFT JOIN.
- Hiểu vai trò của **PRIMARY KEY**, **UNIQUE**, **FOREIGN KEY**, **NOT NULL**, cũng như giới hạn của chúng khi dữ liệu nhập chưa được kiểm soát.
- Nhận ra khác biệt phương ngữ liên quan đến phép so sánh an toàn với NULL và hỗ trợ FULL OUTER JOIN.

## 2. Mô hình dữ liệu mẫu

Ta dùng hai bảng chính:

**khach_hang**

| ma_khach_hang | ten_khach_hang |
|---:|---|
| 1 | An |
| 2 | Bình |
| 3 | Chi |
| 4 | Dũng |

Giả định **ma_khach_hang** là khóa chính (**PRIMARY KEY**), nên trong bảng khách chuẩn này mỗi mã xuất hiện nhiều nhất một lần và không NULL.

**don_hang**

| ma_don_hang | ma_khach_hang | trang_thai | tong_tien |
|---:|---:|---|---:|
| 101 | 1 | PAID | 200000 |
| 102 | 1 | PENDING | 150000 |
| 103 | 2 | PAID | 300000 |
| 104 | NULL | CANCELLED | 90000 |
| 105 | 999 | PAID | 500000 |
| 106 | 2 | PAID | NULL |

Giả định **ma_don_hang** là khóa chính của bảng đơn hàng; **ma_khach_hang** ở bảng đơn là cột dùng để tham chiếu khách; **tong_tien** cho phép NULL.

Có ba tình huống chủ ý trong dữ liệu mẫu:

- **Đơn 104:** mã khách bằng **NULL**, tức là chưa có giá trị tham chiếu khách hàng.
- **Đơn 105:** mã khách bằng **999**, nhưng bảng khach_hang không có khách 999. Đây là **tham chiếu mồ côi**.
- **Đơn 106:** có khách hợp lệ (mã 2), nhưng **tong_tien = NULL**, giúp phân biệt dòng khớp thật với dòng được OUTER JOIN đệm NULL.

**Lưu ý quan trọng:** nếu bảng đơn có một **FOREIGN KEY đang được thực thi** trỏ tới khóa chính khách hàng, bản ghi tham chiếu 999 thường không thể được chèn như trên. Tập mẫu dùng để **minh họa dữ liệu nhập lỗi**, chẳng hạn bảng staging, dữ liệu trước khi tạo constraint, dữ liệu được nạp khi kiểm tra ràng buộc bị tắt, hoặc một cơ sở dữ liệu chưa khai báo quan hệ. Không nên coi dữ liệu mồ côi là trạng thái bình thường khi toàn vẹn tham chiếu được thực thi đúng.

### 2.1. Lược đồ giả định khi chưa kiểm tra FOREIGN KEY

~~~sql
CREATE TABLE khach_hang (
    ma_khach_hang INTEGER PRIMARY KEY,
    ten_khach_hang VARCHAR(100) NOT NULL
);

CREATE TABLE don_hang (
    ma_don_hang INTEGER PRIMARY KEY,
    ma_khach_hang INTEGER,
    trang_thai VARCHAR(20) NOT NULL,
    tong_tien DECIMAL(12, 2)
);
~~~

Đây là cú pháp minh họa tương đối phổ biến; cách định nghĩa kiểu số, cú pháp tạo bảng và các ràng buộc có thể thay đổi theo DBMS. **Chưa có FOREIGN KEY** ở bảng don_hang nên ta có thể quan sát tham chiếu 999 để thực hành phát hiện lỗi.

### 2.2. Ba khái niệm cần phân biệt trước khi JOIN

| Khái niệm | Ví dụ | Diễn giải |
|---|---|---|
| Khóa chính | khach_hang.ma_khach_hang | Định danh duy nhất một khách |
| Khóa tham chiếu/khóa ngoại | don_hang.ma_khach_hang | Giá trị dùng để nối một đơn với khách |
| Điều kiện JOIN | d.ma_khach_hang = k.ma_khach_hang | Quy tắc tạo cặp khớp giữa hai bảng |

Một cột được **dùng như khóa ngoại về mặt nghiệp vụ** chưa chắc đã có constraint **FOREIGN KEY** được khai báo và thực thi. JOIN có thể được viết ngay cả khi DBMS không biết hoặc không kiểm tra quan hệ đó.

---

## 3. JOIN hoạt động theo cặp dòng

Đối với điều kiện:

~~~sql
FROM khach_hang k
JOIN don_hang d
    ON d.ma_khach_hang = k.ma_khach_hang
~~~

hãy hình dung SQL xét các cặp hàng khả dĩ từ hai nguồn:

~~~text
Khách 1 (An)     + Đơn 101 (mã khách 1)    -> khớp
Khách 1 (An)     + Đơn 102 (mã khách 1)    -> khớp
Khách 1 (An)     + Đơn 103 (mã khách 2)    -> không khớp
Khách 2 (Bình)   + Đơn 103 (mã khách 2)    -> khớp
Khách 2 (Bình)   + Đơn 106 (mã khách 2)    -> khớp
Bất kỳ khách nào + Đơn 104 (mã khách NULL) -> không khớp với =
Bất kỳ khách nào + Đơn 105 (mã khách 999)  -> không khớp
~~~

Trong SQL thông thường, điều kiện ở **ON** sử dụng logic ba giá trị (**TRUE**, **FALSE**, **UNKNOWN**). Một cặp dòng chỉ được xem là **khớp** khi biểu thức ON trả **TRUE**.

Nếu điều kiện trả **FALSE** hoặc **UNKNOWN**, cặp đó không được chọn làm cặp khớp. Sau đó, loại JOIN quyết định có giữ **dòng không khớp** ở phía trái/phải bằng cách đệm NULL hay không.

**INNER JOIN** giữ các cặp khớp. **LEFT/RIGHT/FULL OUTER JOIN** có thêm quy tắc giữ dòng không khớp.

## 4. NULL trong điều kiện ON: vì sao không khớp bằng dấu bằng?

Giả sử:

~~~sql
d.ma_khach_hang = k.ma_khach_hang
~~~

Khi **d.ma_khach_hang = NULL**, biểu thức so sánh với mã khách 1, 2, 3 hoặc 4 không trả FALSE một cách chắc chắn mà trả **UNKNOWN**.

Một số kết quả điển hình:

| Điều kiện | Kết quả logic |
|---|---|
| 1 = 1 | TRUE |
| 1 = 2 | FALSE |
| NULL = 1 | UNKNOWN |
| NULL = NULL | UNKNOWN |
| NULL <> 1 | UNKNOWN |
| NULL IS NULL | TRUE |
| 1 IS NULL | FALSE |

**NULL = NULL không phải TRUE.** Hai vị trí đều thiếu giá trị không phải bằng chứng hai giá trị đã biết giống nhau.

Hệ quả với JOIN:

~~~sql
SELECT k.ma_khach_hang, d.ma_don_hang
FROM khach_hang k
JOIN don_hang d
    ON k.ma_khach_hang = d.ma_khach_hang;
~~~

Đơn 104 có mã khách NULL nên **không nối với khách nào**. Nó cũng sẽ không tự nối với một hàng khách có khóa NULL bằng phép **=**, nếu thiết kế cho phép hai phía chứa NULL.

### 4.1. Không dùng = NULL để tìm khóa thiếu

~~~sql
-- Sai ý định:
SELECT ma_don_hang
FROM don_hang
WHERE ma_khach_hang = NULL;
~~~

Cách đúng:

~~~sql
SELECT ma_don_hang
FROM don_hang
WHERE ma_khach_hang IS NULL;
~~~

Kết quả trên tập mẫu: **104**.

Muốn loại những đơn chưa có mã khách:

~~~sql
SELECT ma_don_hang
FROM don_hang
WHERE ma_khach_hang IS NOT NULL;
~~~

Kết quả: **101, 102, 103, 105, 106**.

### 4.2. Khóa NULL và khóa không tồn tại là hai lỗi khác nhau

- **Đơn 104:** chưa có khóa tham chiếu; không thể biết khách đích chỉ từ cột đang có.
- **Đơn 105:** có khóa tham chiếu cụ thể **999**, nhưng không tồn tại khách tương ứng.

Không nên gọi cả hai đơn giản là “NULL ở JOIN” rồi xử lý giống nhau. Một trường hợp thiếu **giá trị khóa**, một trường hợp có **giá trị khóa không hợp lệ đối với nguồn cha**. Chúng có thể cần các chính sách sửa dữ liệu khác nhau.

## 5. INNER JOIN: chỉ lấy cặp khớp

~~~sql
SELECT
    k.ma_khach_hang,
    k.ten_khach_hang,
    d.ma_don_hang,
    d.trang_thai,
    d.tong_tien
FROM khach_hang k
INNER JOIN don_hang d
    ON d.ma_khach_hang = k.ma_khach_hang
ORDER BY k.ma_khach_hang, d.ma_don_hang;
~~~

Kết quả:

| ma_khach_hang | ten_khach_hang | ma_don_hang | trang_thai | tong_tien |
|---:|---|---:|---|---:|
| 1 | An | 101 | PAID | 200000 |
| 1 | An | 102 | PENDING | 150000 |
| 2 | Bình | 103 | PAID | 300000 |
| 2 | Bình | 106 | PAID | NULL |

Có **4 dòng**:

- Khách 1 nối hai đơn 101, 102.
- Khách 2 nối hai đơn 103, 106.
- Khách 3 và 4 không có đơn nên không xuất hiện.
- Đơn 104 có khóa NULL và đơn 105 có khóa 999 không tìm thấy khách nên không xuất hiện.

**INNER JOIN không sửa, không xóa bản ghi gốc.** Nó chỉ loại các cặp không khớp khỏi **kết quả truy vấn**. Bản ghi 104 và 105 vẫn có trong bảng don_hang.

### 5.1. JOIN không phải phép “một dòng trái lấy tối đa một dòng phải”

Một câu INNER JOIN với khóa khách có thể trả **nhiều dòng cho một khách**, vì khóa ngoại ở bảng đơn được phép lặp qua nhiều đơn. Đây là quan hệ **một–nhiều** hợp lệ, không nhất thiết là lỗi.

Chỉ khi yêu cầu nghiệp vụ cần **mỗi khách một dòng**, bạn mới phải tổng hợp, dùng EXISTS hoặc chọn đúng một bản ghi đại diện thay vì mong INNER JOIN tự giới hạn số dòng.

## 6. LEFT JOIN: giữ mọi dòng phía trái

~~~sql
SELECT
    k.ma_khach_hang,
    k.ten_khach_hang,
    d.ma_don_hang,
    d.tong_tien
FROM khach_hang k
LEFT JOIN don_hang d
    ON d.ma_khach_hang = k.ma_khach_hang
ORDER BY k.ma_khach_hang, d.ma_don_hang;
~~~

Kết quả:

| ma_khach_hang | ten_khach_hang | ma_don_hang | tong_tien |
|---:|---|---:|---:|
| 1 | An | 101 | 200000 |
| 1 | An | 102 | 150000 |
| 2 | Bình | 103 | 300000 |
| 2 | Bình | 106 | NULL |
| 3 | Chi | NULL | NULL |
| 4 | Dũng | NULL | NULL |

Có **6 dòng**: bốn dòng khớp từ INNER JOIN cộng hai khách không có đơn.

Với khách **Chi** và **Dũng**, các cột thuộc bảng **d** được đệm NULL vì không có đơn nào khớp. Tuy nhiên, với khách **Bình**, đơn **106** là bản ghi có thật: **d.ma_don_hang = 106** nhưng **d.tong_tien = NULL** vốn có sẵn.

Đây là điểm quan trọng: **không thể dùng một cột phía phải vốn cho phép NULL để kết luận chắc chắn “không có dòng JOIN”.**

### 6.1. Xác định dòng không khớp bằng khóa NOT NULL của bảng phải

Nếu **d.ma_don_hang** là khóa chính NOT NULL:

~~~sql
SELECT
    k.ma_khach_hang,
    k.ten_khach_hang
FROM khach_hang k
LEFT JOIN don_hang d
    ON d.ma_khach_hang = k.ma_khach_hang
WHERE d.ma_don_hang IS NULL
ORDER BY k.ma_khach_hang;
~~~

Kết quả: **Chi (3)** và **Dũng (4)**.

Điều kiện **d.ma_don_hang IS NULL** an toàn cho ý định này vì mọi dòng đơn thật có ma_don_hang khác NULL. Một NULL tại cột đó trong kết quả LEFT JOIN báo hiệu không có dòng đơn khớp.

Nếu thay bằng:

~~~sql
WHERE d.tong_tien IS NULL
~~~

thì **Bình (2)** cũng xuất hiện vì có đơn 106 thật nhưng chưa có tổng tiền. Truy vấn sẽ phân loại sai Bình thành khách không có đơn.

### 6.2. Một dòng trái có thể xuất hiện nhiều lần

LEFT JOIN giữ **ít nhất một dòng cho mỗi dòng trái** (nếu không có điều kiện WHERE lọc tiếp), nhưng không bảo đảm **chính xác một dòng**. Khách An có hai đơn nên xuất hiện hai lần, không phải một lần.

## 7. RIGHT JOIN: giữ mọi dòng phía phải

Nếu đổi vị trí giữ dòng:

~~~sql
SELECT
    k.ma_khach_hang,
    k.ten_khach_hang,
    d.ma_don_hang,
    d.ma_khach_hang AS ma_khach_trong_don
FROM khach_hang k
RIGHT JOIN don_hang d
    ON d.ma_khach_hang = k.ma_khach_hang
ORDER BY d.ma_don_hang;
~~~

Kết quả:

| ma_khach_hang | ten_khach_hang | ma_don_hang | ma_khach_trong_don |
|---:|---|---:|---:|
| 1 | An | 101 | 1 |
| 1 | An | 102 | 1 |
| 2 | Bình | 103 | 2 |
| NULL | NULL | 104 | NULL |
| NULL | NULL | 105 | 999 |
| 2 | Bình | 106 | 2 |

Có **6 dòng** vì mỗi đơn được giữ lại, kể cả đơn 104 và 105 không tìm được khách.

Điểm đáng chú ý:

- Đơn **104**: **k.ma_khach_hang NULL** do không ghép được; **d.ma_khach_hang NULL** vốn có trong dữ liệu đơn.
- Đơn **105**: **k.ma_khach_hang NULL** do không ghép được; **d.ma_khach_hang = 999** cho biết mã tham chiếu đang sai.

RIGHT JOIN thường có thể được viết lại thành **LEFT JOIN** bằng cách đổi thứ tự hai bảng:

~~~sql
SELECT
    k.ma_khach_hang,
    k.ten_khach_hang,
    d.ma_don_hang,
    d.ma_khach_hang AS ma_khach_trong_don
FROM don_hang d
LEFT JOIN khach_hang k
    ON k.ma_khach_hang = d.ma_khach_hang
ORDER BY d.ma_don_hang;
~~~

Cách viết bảng đơn bên trái thường dễ đọc hơn khi mục tiêu là **giữ mọi đơn**. Ngoài ra, việc hỗ trợ RIGHT JOIN ở các phiên bản SQLite cũ cũng có giới hạn; đổi sang LEFT JOIN có thể thuận tiện hơn khi cần khả chuyển.

## 8. FULL OUTER JOIN: giữ cả hai phía

FULL OUTER JOIN giữ:

1. Mọi cặp dòng khớp.
2. Dòng phía trái không có cặp khớp (các cột phải được đệm NULL).
3. Dòng phía phải không có cặp khớp (các cột trái được đệm NULL).

~~~sql
SELECT
    k.ma_khach_hang AS ma_khach_trong_bang_khach,
    k.ten_khach_hang,
    d.ma_don_hang,
    d.ma_khach_hang AS ma_khach_trong_don
FROM khach_hang k
FULL OUTER JOIN don_hang d
    ON d.ma_khach_hang = k.ma_khach_hang;
~~~

Với tập mẫu có **4 cặp khớp**, **2 khách không có đơn** và **2 đơn không có khách**, FULL OUTER JOIN trả **8 dòng**.

| Loại dòng | Ví dụ | Số dòng |
|---|---|---:|
| Khớp hai phía | 1–101, 1–102, 2–103, 2–106 | 4 |
| Chỉ ở bảng khách | 3–NULL, 4–NULL | 2 |
| Chỉ ở bảng đơn | NULL–104, NULL–105 | 2 |
| **Tổng** | | **8** |

**Tính khả chuyển:** PostgreSQL và SQL Server hỗ trợ FULL OUTER JOIN; Oracle Database cũng hỗ trợ. MySQL không hỗ trợ cú pháp FULL OUTER JOIN trực tiếp trong các phiên bản thông dụng; SQLite hỗ trợ RIGHT/FULL OUTER JOIN từ **3.39.0**. Khi DBMS không hỗ trợ, có thể mô phỏng bằng LEFT JOIN kết hợp các dòng không khớp phía còn lại, với điều kiện chú ý **UNION ALL**, khóa kiểm tra không khớp và trường hợp khóa trùng. Không nên mặc định đổi FULL JOIN thành hai INNER JOIN hay dùng UNION không kiểm soát vì dễ mất hoặc loại nhầm dòng.

### 8.1. Tìm các trường hợp không khớp ở cả hai phía

Trên DBMS hỗ trợ FULL OUTER JOIN:

~~~sql
SELECT
    k.ma_khach_hang AS ma_khach,
    d.ma_don_hang,
    d.ma_khach_hang AS ma_khach_trong_don
FROM khach_hang k
FULL OUTER JOIN don_hang d
    ON d.ma_khach_hang = k.ma_khach_hang
WHERE k.ma_khach_hang IS NULL
   OR d.ma_don_hang IS NULL;
~~~

Kết quả gồm các trường hợp: **khách 3**, **khách 4**, **đơn 104**, **đơn 105**. Điều kiện nhận diện dùng hai khóa chính giả định NOT NULL; do đó NULL ở khóa của phía bị thiếu có ý nghĩa không có dòng khớp.

### 8.2. So sánh nhanh các kiểu JOIN

| Kiểu | Dòng khớp | Dòng chỉ ở trái | Dòng chỉ ở phải |
|---|---|---|---|
| INNER JOIN | Giữ | Loại | Loại |
| LEFT JOIN | Giữ | Giữ | Loại |
| RIGHT JOIN | Giữ | Loại | Giữ |
| FULL OUTER JOIN | Giữ | Giữ | Giữ |

Bảng mô tả **việc giữ dòng** theo phép JOIN trước các điều kiện WHERE ở cấp ngoài. Nếu có WHERE tiếp theo, cả những dòng được OUTER JOIN giữ lại cũng có thể bị lọc.

## 9. ON và WHERE khác nhau khi làm việc với OUTER JOIN

Đây là lỗi thực tế rất thường gặp.

Yêu cầu:

> **Liệt kê tất cả khách hàng, kèm đơn đã thanh toán nếu có; vẫn giữ khách không có đơn PAID.**

### 9.1. Đặt điều kiện trạng thái ở ON

~~~sql
SELECT
    k.ma_khach_hang,
    k.ten_khach_hang,
    d.ma_don_hang,
    d.trang_thai
FROM khach_hang k
LEFT JOIN don_hang d
    ON d.ma_khach_hang = k.ma_khach_hang
   AND d.trang_thai = 'PAID'
ORDER BY k.ma_khach_hang, d.ma_don_hang;
~~~

Kết quả:

| Khách | Đơn PAID | Ghi chú |
|---|---:|---|
| An | 101 | Đơn 102 PENDING không được ghép |
| Bình | 103 | PAID |
| Bình | 106 | PAID |
| Chi | NULL | Không có đơn PAID |
| Dũng | NULL | Không có đơn PAID |

Có **5 dòng**. Điều kiện PAID nằm trong ON quyết định **đơn nào được xem là khớp**, còn LEFT JOIN vẫn giữ khách không có đơn khớp.

### 9.2. Đưa điều kiện xuống WHERE

~~~sql
SELECT
    k.ma_khach_hang,
    k.ten_khach_hang,
    d.ma_don_hang
FROM khach_hang k
LEFT JOIN don_hang d
    ON d.ma_khach_hang = k.ma_khach_hang
WHERE d.trang_thai = 'PAID'
ORDER BY k.ma_khach_hang, d.ma_don_hang;
~~~

Kết quả chỉ còn **An–101**, **Bình–103**, **Bình–106** (3 dòng).

Đối với Chi và Dũng, cột **d.trang_thai** là NULL do LEFT JOIN đệm. Biểu thức **NULL = 'PAID'** cho **UNKNOWN**; WHERE chỉ giữ TRUE nên hai khách bị loại.

Kết quả có thể trở nên tương tự INNER JOIN theo tiêu chí PAID, trái với yêu cầu giữ mọi khách.

### 9.3. Thêm OR d.ma_don_hang IS NULL có luôn tương đương ON không?

Có thể gặp cách viết:

~~~sql
WHERE d.trang_thai = 'PAID'
   OR d.ma_don_hang IS NULL
~~~

Cách này **không luôn tương đương** với đặt điều kiện trạng thái trong ON.

Ví dụ, giả sử một khách có **duy nhất một đơn PENDING** nhưng không có đơn PAID. LEFT JOIN theo mỗi mã khách vẫn tạo dòng khớp PENDING, nên **d.ma_don_hang không NULL**. WHERE sẽ loại dòng PENDING; khách đó **không xuất hiện**, dù yêu cầu là giữ mọi khách.

Đặt tiêu chí PAID trong ON, hoặc thiết kế truy vấn con phù hợp, mới trực tiếp thể hiện “giữ khách, nối đơn PAID nếu có”.

### 9.4. Một điều kiện thuộc về quan hệ hay thuộc về kết quả?

Đặt câu hỏi:

- **Điều kiện quyết định hai dòng có được ghép không?** Thường thuộc ON.
- **Điều kiện quyết định dòng kết quả cuối cùng có được giữ không?** Thường thuộc WHERE.
- **Yêu cầu phải giữ dòng không có quan hệ ở phía OUTER JOIN?** Tránh vô tình lọc chúng bằng điều kiện không nhận TRUE khi phía còn lại NULL.

Với INNER JOIN, nhiều điều kiện giữa ON và WHERE có thể được chuyển đổi tương đương về ngữ nghĩa, nhưng với OUTER JOIN cần đặc biệt cẩn thận.

## 10. Khóa trùng: vì sao JOIN có thể nhân số dòng?

Các truy vấn SQL thông thường sử dụng ngữ nghĩa **đa tập (bag/multiset)**: mỗi dòng khớp có thể đóng góp vào nhiều kết quả. JOIN không tự loại trùng.

Giả sử trong bảng nhập liệu **khach_hang_nhap** xuất hiện lỗi trùng mã:

| ma_khach_hang | ten_khach_hang |
|---:|---|
| 1 | An |
| 2 | Bình |
| 2 | Bình (bản ghi nhập lại) |

Còn bảng đơn có các dòng:

| ma_don_hang | ma_khach_hang |
|---:|---:|
| 101 | 1 |
| 102 | 1 |
| 103 | 2 |
| 106 | 2 |

Nếu JOIN:

~~~sql
SELECT
    k.ma_khach_hang,
    k.ten_khach_hang,
    d.ma_don_hang
FROM khach_hang_nhap k
JOIN don_hang d
    ON d.ma_khach_hang = k.ma_khach_hang
ORDER BY d.ma_don_hang, k.ten_khach_hang;
~~~

Kết quả sẽ có:

| Khách từ nguồn nhập | Đơn | Số lần xuất hiện |
|---|---|---:|
| An (mã 1) | 101 | 1 |
| An (mã 1) | 102 | 1 |
| Bình (mã 2) | 103 | 1 |
| Bình (bản ghi nhập lại, mã 2) | 103 | 1 |
| Bình (mã 2) | 106 | 1 |
| Bình (bản ghi nhập lại, mã 2) | 106 | 1 |

Tổng **6 dòng**, dù bảng đơn chỉ có bốn mã đơn liên quan.

Vì mỗi đơn có mã khách 2 sẽ khớp với **hai hàng** mang mã 2 ở phía bảng khách nhập liệu, nên hai đơn 103 và 106 mỗi đơn tạo **hai dòng kết quả**.

### 10.1. Công thức số cặp khớp theo từng khóa

Giả sử với một giá trị khóa cụ thể **v**:

- Bảng trái có **L(v)** dòng mang khóa v.
- Bảng phải có **R(v)** dòng mang khóa v.

Khi nối bằng **a.khoa = b.khoa** và **v không NULL**, số cặp khớp do khóa đó tạo ra là:

\[
L(v) \times R(v)
\]

Ví dụ:

| Khóa | Số dòng trái | Số dòng phải | Số cặp INNER JOIN |
|---|---:|---:|---:|
| 1 | 1 | 2 | 2 |
| 2 | 2 | 2 | 4 |
| 3 | 1 | 0 | 0 |
| 4 | 0 | 3 | 0 |
| **Tổng khớp** | | | **6** |

Nếu khóa có **3 dòng ở trái** và **4 dòng ở phải**, JOIN tạo **12 cặp**, không phải 3, 4 hay 7 dòng.

Đối với khóa NULL, phép **=** thông thường không tạo cặp khớp, nên không trực tiếp áp dụng phép nhân như một khóa v bình thường. Nếu dùng phép so sánh chuyên biệt coi hai NULL là khớp, kết quả có thể nhân theo số dòng NULL ở cả hai phía.

### 10.2. Khóa trùng hợp lệ và khóa trùng sai

**Trùng giá trị khóa không luôn là lỗi.** Điều đó phụ thuộc quan hệ.

- **Khách 1 có hai đơn:** don_hang.ma_khach_hang xuất hiện hai lần, hoàn toàn hợp lệ trong quan hệ một khách–nhiều đơn.
- **Khách 2 xuất hiện hai lần trong bảng khách có yêu cầu một mã–một khách:** lỗi vì cột lẽ ra là khóa chính/UNIQUE.
- **Chi tiết đơn hàng có cùng ma_don_hang nhiều lần:** hợp lệ nếu mỗi dòng là một sản phẩm khác nhau, miễn khóa thực sự của chi tiết (ví dụ ma_don_hang + so_dong) được đảm bảo.
- **Bảng nối nhiều–nhiều:** cùng một mã ở mỗi phía có thể lặp lại theo thiết kế; cần khóa ghép phù hợp.

Trước khi đánh dấu “duplicate”, cần xác định **khóa ứng viên** và mức chi tiết của từng bảng.

## 11. Quan hệ một–một, một–nhiều và nhiều–nhiều

| Quan hệ | Ví dụ | Hệ quả khi JOIN |
|---|---|---|
| **Một–một** | Một khách và một hồ sơ bổ sung có khóa UNIQUE | Mỗi dòng trái có tối đa một dòng phải khớp |
| **Một–nhiều** | Một khách có nhiều đơn | Một khách có thể xuất hiện nhiều dòng |
| **Nhiều–nhiều** | Một đơn có nhiều sản phẩm và một sản phẩm thuộc nhiều đơn | Phải đi qua bảng nối/chi tiết; số dòng có thể lớn |
| **Sai khóa nối** | Chỉ nối theo tên khách trùng nhau | Tạo cặp sai và có thể nhân dòng |

Ví dụ:

~~~sql
SELECT
    k.ma_khach_hang,
    d.ma_don_hang
FROM khach_hang k
JOIN don_hang d
    ON d.ma_khach_hang = k.ma_khach_hang;
~~~

Ở đây, dữ liệu chuẩn có thể tạo nhiều dòng cho mỗi khách vì bảng đơn có khóa tham chiếu lặp. Điều đó không phải dấu hiệu JOIN “hỏng”.

**Một dòng trong kết quả JOIN đại diện cho một cặp dòng nguồn khớp**, trừ khi truy vấn còn tổng hợp hoặc loại trùng. Vì vậy, cần xác định **grain/mức chi tiết** mong muốn trước khi viết SELECT và GROUP BY.

## 12. Phát hiện khóa trùng bằng GROUP BY và HAVING

Nếu bảng nguồn **khach_hang_nhap** được kỳ vọng chỉ có một dòng mỗi mã khách:

~~~sql
SELECT
    ma_khach_hang,
    COUNT(*) AS so_lan_xuat_hien
FROM khach_hang_nhap
WHERE ma_khach_hang IS NOT NULL
GROUP BY ma_khach_hang
HAVING COUNT(*) > 1
ORDER BY so_lan_xuat_hien DESC, ma_khach_hang;
~~~

Kết quả theo dữ liệu lỗi ở phần 10: **ma_khach_hang = 2**, **so_lan_xuat_hien = 2**.

Nếu muốn lấy đầy đủ các hàng bị trùng khóa để kiểm tra:

~~~sql
WITH khoa_trung AS (
    SELECT ma_khach_hang
    FROM khach_hang_nhap
    WHERE ma_khach_hang IS NOT NULL
    GROUP BY ma_khach_hang
    HAVING COUNT(*) > 1
)
SELECT k.*
FROM khach_hang_nhap k
JOIN khoa_trung t
    ON t.ma_khach_hang = k.ma_khach_hang
ORDER BY k.ma_khach_hang, k.ten_khach_hang;
~~~

Các hàng có khóa 2 sẽ được trả để đối chiếu. Nếu bảng nhập liệu có mã bản ghi nguồn riêng (ví dụ **id_nhap**), hãy chọn thêm nó để phân biệt các hàng có cùng nội dung.

### 12.1. NULL trong khóa cũng cần bài kiểm tra riêng

GROUP BY thường gom những dòng có khóa NULL thành một nhóm. Tuy nhiên, khóa NULL không khớp nhau bằng **=** trong JOIN. Vì vậy có thể chia kiểm tra thành:

~~~sql
-- Dữ liệu thiếu khóa:
SELECT *
FROM khach_hang_nhap
WHERE ma_khach_hang IS NULL;
~~~

và:

~~~sql
-- Các khóa có giá trị bị lặp:
SELECT ma_khach_hang, COUNT(*) AS so_dong
FROM khach_hang_nhap
WHERE ma_khach_hang IS NOT NULL
GROUP BY ma_khach_hang
HAVING COUNT(*) > 1;
~~~

Như vậy, không lẫn **thiếu khóa** với **trùng một khóa cụ thể**.

### 12.2. GROUP BY không chứng minh khóa là duy nhất ở mọi thời điểm

Một truy vấn kiểm tra duplicate chỉ phản ánh dữ liệu **tại thời điểm đọc**. Nếu ứng dụng cho phép thêm dòng đồng thời mà không có ràng buộc UNIQUE/PRIMARY KEY, một câu SELECT kiểm tra “chưa trùng” rồi INSERT vẫn có thể bị chạy đua. Để bảo đảm duy nhất trong cơ sở dữ liệu, cần constraint hoặc chỉ mục duy nhất với ngữ nghĩa phù hợp.

## 13. Cảnh giác với COUNT(*) sau JOIN

Yêu cầu: “Mỗi khách có bao nhiêu đơn?”

Cách dùng LEFT JOIN chưa đúng:

~~~sql
SELECT
    k.ma_khach_hang,
    COUNT(*) AS so_don
FROM khach_hang k
LEFT JOIN don_hang d
    ON d.ma_khach_hang = k.ma_khach_hang
GROUP BY k.ma_khach_hang;
~~~

Với khách **Chi** và **Dũng**, LEFT JOIN vẫn tạo **một dòng được đệm NULL phía phải**. COUNT(*) đếm dòng kết quả đó, nên trả **1**, mặc dù khách không có đơn.

Cách đúng khi **d.ma_don_hang** là khóa chính NOT NULL:

~~~sql
SELECT
    k.ma_khach_hang,
    k.ten_khach_hang,
    COUNT(d.ma_don_hang) AS so_don
FROM khach_hang k
LEFT JOIN don_hang d
    ON d.ma_khach_hang = k.ma_khach_hang
GROUP BY k.ma_khach_hang, k.ten_khach_hang
ORDER BY k.ma_khach_hang;
~~~

Kết quả:

| Khách | Số đơn |
|---|---:|
| An (1) | 2 |
| Bình (2) | 2 |
| Chi (3) | 0 |
| Dũng (4) | 0 |

**COUNT(cot)** bỏ qua các giá trị NULL. Vì **d.ma_don_hang** chỉ NULL trên dòng được LEFT JOIN đệm (khóa chính của đơn thật không NULL), COUNT(d.ma_don_hang) đếm đúng số dòng đơn khớp.

### 13.1. COUNT(cột có thể NULL) cũng có thể sai

~~~sql
SELECT
    k.ma_khach_hang,
    COUNT(d.tong_tien) AS so_don
FROM khach_hang k
LEFT JOIN don_hang d
    ON d.ma_khach_hang = k.ma_khach_hang
GROUP BY k.ma_khach_hang;
~~~

Với khách Bình có hai đơn 103 và 106, nhưng **tong_tien của đơn 106 là NULL**. COUNT(d.tong_tien) chỉ trả **1**, không phải 2.

Khi cần đếm các dòng có quan hệ, hãy chọn **cột định danh NOT NULL** ở bảng phải hoặc dùng một truy vấn được xây đúng theo mức chi tiết nghiệp vụ.

### 13.2. COUNT(DISTINCT ...) không chữa mọi vấn đề

Nếu JOIN sang bảng chi tiết đơn gây nhiều dòng cho một đơn:

~~~sql
SELECT
    k.ma_khach_hang,
    COUNT(DISTINCT d.ma_don_hang) AS so_don
FROM khach_hang k
LEFT JOIN don_hang d
    ON d.ma_khach_hang = k.ma_khach_hang
LEFT JOIN chi_tiet_don_hang ct
    ON ct.ma_don_hang = d.ma_don_hang
GROUP BY k.ma_khach_hang;
~~~

COUNT(DISTINCT d.ma_don_hang) có thể cho đúng số đơn phân biệt, nhưng nó **không tự bảo đảm các phép SUM khác trong cùng truy vấn là đúng**. Nếu có chi tiết đơn hàng nhân dòng, SUM(d.tong_tien) vẫn có thể bị tính lặp.

## 14. JOIN một–nhiều có thể làm cộng tiền sai

Giả sử có thêm bảng **chi_tiet_don_hang**:

| ma_don_hang | ma_san_pham | so_luong |
|---:|---:|---:|
| 101 | 10 | 1 |
| 101 | 11 | 2 |
| 102 | 12 | 1 |
| 103 | 13 | 1 |

Đơn 101 có **hai dòng chi tiết** nhưng tổng tiền của đơn vẫn chỉ có **một giá trị** 200000 trong bảng don_hang.

Nếu JOIN rồi SUM ngay cột tiền của bảng đơn:

~~~sql
-- Có nguy cơ nhân tiền đơn theo số dòng chi tiết.
SELECT
    d.ma_khach_hang,
    SUM(d.tong_tien) AS tong_tien
FROM don_hang d
JOIN chi_tiet_don_hang ct
    ON ct.ma_don_hang = d.ma_don_hang
GROUP BY d.ma_khach_hang;
~~~

Đối với khách An:

~~~text
Đơn 101 ghép 2 chi tiết: 200000 + 200000
Đơn 102 ghép 1 chi tiết: 150000
SUM sau JOIN = 550000
~~~

Nhưng tổng tiền của hai đơn thật là:

~~~text
200000 + 150000 = 350000
~~~

**Lỗi là sai mức chi tiết của nguồn SUM**, không phải lỗi của hàm SUM.

### 14.1. Không dùng SUM(DISTINCT tong_tien) để che lỗi

Có thể người viết thử:

~~~sql
SUM(DISTINCT d.tong_tien)
~~~

Nhưng nếu khách có **hai đơn khác nhau cùng tổng tiền 200000**, SUM(DISTINCT tong_tien) sẽ chỉ tính giá trị 200000 một lần. Nó loại các **giá trị tiền trùng**, không loại dòng lặp dựa trên **mã đơn**.

Cách sửa phải bám vào khóa và mức chi tiết thật của dữ liệu.

### 14.2. Tổng hợp mỗi nguồn trước khi JOIN

Nếu chỉ cần tổng tiền theo khách, không cần JOIN chi tiết:

~~~sql
SELECT
    ma_khach_hang,
    SUM(tong_tien) AS tong_tien_don
FROM don_hang
GROUP BY ma_khach_hang;
~~~

Nếu cần cả số lượng sản phẩm, tổng hợp riêng hai nguồn:

~~~sql
WITH tien_theo_khach AS (
    SELECT
        ma_khach_hang,
        COUNT(*) AS so_don,
        SUM(tong_tien) AS tong_tien
    FROM don_hang
    WHERE ma_khach_hang IS NOT NULL
    GROUP BY ma_khach_hang
),
so_luong_theo_khach AS (
    SELECT
        d.ma_khach_hang,
        SUM(ct.so_luong) AS tong_so_luong
    FROM don_hang d
    JOIN chi_tiet_don_hang ct
        ON ct.ma_don_hang = d.ma_don_hang
    WHERE d.ma_khach_hang IS NOT NULL
    GROUP BY d.ma_khach_hang
)
SELECT
    k.ma_khach_hang,
    k.ten_khach_hang,
    COALESCE(t.so_don, 0) AS so_don,
    COALESCE(t.tong_tien, 0) AS tong_tien,
    COALESCE(s.tong_so_luong, 0) AS tong_so_luong
FROM khach_hang k
LEFT JOIN tien_theo_khach t
    ON t.ma_khach_hang = k.ma_khach_hang
LEFT JOIN so_luong_theo_khach s
    ON s.ma_khach_hang = k.ma_khach_hang
ORDER BY k.ma_khach_hang;
~~~

Các CTE xác định rõ:

- **tien_theo_khach:** một dòng cho mỗi mã khách.
- **so_luong_theo_khach:** một dòng cho mỗi mã khách.
- **khach_hang:** một dòng cho mỗi khách vì có PRIMARY KEY.

Khi JOIN những nguồn đã được đảm bảo **mỗi khóa một dòng**, rủi ro nhân doanh thu do nhiều chi tiết giảm đáng kể. Nếu dữ liệu thật vẫn có khóa trùng ở CTE hay bảng khách, cần xử lý riêng; đừng coi việc dùng CTE tự đảm bảo tính duy nhất.

**Lưu ý COALESCE:** đổi SUM NULL thành 0 là chính sách trình bày/đo lường. Nếu tiền chưa xác định khác với tổng tiền bằng 0, hãy giữ NULL hoặc hiển thị thêm cờ thiếu dữ liệu.

## 15. Thiếu tham chiếu: bản ghi mồ côi là gì?

Một **bản ghi mồ côi** (*orphan record*) trong quan hệ cha–con thường là bản ghi con có **khóa tham chiếu không NULL** nhưng **không có bản ghi cha tương ứng**.

Trong dữ liệu mẫu:

- Đơn 105 có **ma_khach_hang = 999**.
- Bảng khách không có **ma_khach_hang = 999**.
- Vì vậy, đơn 105 là **orphan** theo quan hệ đơn → khách.

Đơn 104 có **ma_khach_hang = NULL**. Nó là bản ghi **chưa có tham chiếu**, nhưng có gọi là “mồ côi” hay không tùy định nghĩa kiểm tra chất lượng dữ liệu. Nhiều báo cáo tách hai nhóm:

1. **Thiếu giá trị khóa ngoại:** khóa IS NULL.
2. **Có khóa nhưng không tồn tại cha:** khóa IS NOT NULL và không tìm thấy bản ghi cha.

Tách nhóm giúp quyết định xử lý:

- Thiếu khóa có thể cần bổ sung thông tin khách, hoặc cho phép nếu nghiệp vụ chấp nhận đơn không gắn khách.
- Mã 999 sai có thể là lỗi nhập, mapping sai, khách bị xóa không phù hợp hoặc dữ liệu cha chưa được đồng bộ.

### 15.1. Tìm mồ côi bằng LEFT JOIN

~~~sql
SELECT
    d.ma_don_hang,
    d.ma_khach_hang
FROM don_hang d
LEFT JOIN khach_hang k
    ON k.ma_khach_hang = d.ma_khach_hang
WHERE d.ma_khach_hang IS NOT NULL
  AND k.ma_khach_hang IS NULL
ORDER BY d.ma_don_hang;
~~~

Kết quả:

| ma_don_hang | ma_khach_hang |
|---:|---:|
| 105 | 999 |

Giải thích:

- **d.ma_khach_hang IS NOT NULL** yêu cầu đơn có khai báo mã khách.
- **k.ma_khach_hang IS NULL** yêu cầu không có dòng khách nào khớp.
- Hai điều kiện kết hợp cho **khóa có giá trị nhưng thiếu bản ghi đích**.

### 15.2. Tìm mồ côi bằng NOT EXISTS

~~~sql
SELECT
    d.ma_don_hang,
    d.ma_khach_hang
FROM don_hang d
WHERE d.ma_khach_hang IS NOT NULL
  AND NOT EXISTS (
      SELECT 1
      FROM khach_hang k
      WHERE k.ma_khach_hang = d.ma_khach_hang
  )
ORDER BY d.ma_don_hang;
~~~

Kết quả cũng là **105**.

**NOT EXISTS** hỏi “không có dòng cha nào đáp ứng điều kiện”, thường dễ đọc cho bài toán chống khớp (*anti-join*). Nó không tạo dòng nhân bản chỉ vì bảng cha có nhiều dòng cùng khóa; chỉ cần tồn tại ít nhất một dòng là EXISTS TRUE.

### 15.3. Tìm tất cả đơn không ghép được khách

Nếu yêu cầu bao gồm **cả thiếu khóa và khóa không có khách**:

~~~sql
SELECT
    d.ma_don_hang,
    d.ma_khach_hang
FROM don_hang d
LEFT JOIN khach_hang k
    ON k.ma_khach_hang = d.ma_khach_hang
WHERE k.ma_khach_hang IS NULL
ORDER BY d.ma_don_hang;
~~~

Kết quả: **104** và **105**.

Đây là tập **không ghép được khách**, rộng hơn tập orphan theo định nghĩa “có khóa nhưng cha không tồn tại”.

## 16. Phân loại tình trạng tham chiếu bằng CASE

Một báo cáo kiểm tra chất lượng dữ liệu hữu ích cần biết **tại sao** từng đơn không khớp:

~~~sql
SELECT
    d.ma_don_hang,
    d.ma_khach_hang,
    CASE
        WHEN d.ma_khach_hang IS NULL THEN 'THIEU_KHOA'
        WHEN k.ma_khach_hang IS NULL THEN 'THAM_CHIEU_MO_COI'
        ELSE 'HOP_LE'
    END AS tinh_trang_tham_chieu
FROM don_hang d
LEFT JOIN khach_hang k
    ON k.ma_khach_hang = d.ma_khach_hang
ORDER BY d.ma_don_hang;
~~~

Với dữ liệu mẫu:

| ma_don_hang | ma_khach_hang | tinh_trang_tham_chieu |
|---:|---:|---|
| 101 | 1 | HOP_LE |
| 102 | 1 | HOP_LE |
| 103 | 2 | HOP_LE |
| 104 | NULL | THIEU_KHOA |
| 105 | 999 | THAM_CHIEU_MO_COI |
| 106 | 2 | HOP_LE |

Thứ tự WHEN là có chủ đích:

1. Nếu khóa của đơn NULL, phân loại **THIEU_KHOA** trước.
2. Nếu khóa có giá trị nhưng không tìm được khách, phân loại **THAM_CHIEU_MO_COI**.
3. Còn lại là khớp hợp lệ với bảng khách hiện tại.

Đây là ví dụ tốt của việc không gộp NULL và orphan thành một nhãn “lỗi JOIN” không đủ thông tin.

### 16.1. Tổng hợp số bản ghi theo tình trạng

Có thể bọc phân loại trong CTE:

~~~sql
WITH kiem_tra AS (
    SELECT
        d.ma_don_hang,
        CASE
            WHEN d.ma_khach_hang IS NULL THEN 'THIEU_KHOA'
            WHEN k.ma_khach_hang IS NULL THEN 'THAM_CHIEU_MO_COI'
            ELSE 'HOP_LE'
        END AS tinh_trang
    FROM don_hang d
    LEFT JOIN khach_hang k
        ON k.ma_khach_hang = d.ma_khach_hang
)
SELECT
    tinh_trang,
    COUNT(*) AS so_don
FROM kiem_tra
GROUP BY tinh_trang;
~~~

Theo dữ liệu mẫu: **HOP_LE = 4**, **THIEU_KHOA = 1**, **THAM_CHIEU_MO_COI = 1**.

Truy vấn giả định **khach_hang.ma_khach_hang** là khóa duy nhất. Nếu bảng khách có khóa trùng, LEFT JOIN có thể nhân các dòng hợp lệ trước khi GROUP BY, khiến COUNT(*) sai. Khi kiểm tra nguồn chưa tin cậy, hãy kiểm tra **tính duy nhất** hoặc dùng EXISTS để phân loại mà không nhân dòng.

## 17. Phân loại tham chiếu khi bảng cha có khóa trùng

Nếu dữ liệu cha là bảng staging có thể trùng mã, cách phân loại dựa vào EXISTS thích hợp để mỗi đơn chỉ xuất hiện một lần:

~~~sql
SELECT
    d.ma_don_hang,
    d.ma_khach_hang,
    CASE
        WHEN d.ma_khach_hang IS NULL THEN 'THIEU_KHOA'
        WHEN EXISTS (
            SELECT 1
            FROM khach_hang_nhap k
            WHERE k.ma_khach_hang = d.ma_khach_hang
        ) THEN 'CO_KHACH'
        ELSE 'THAM_CHIEU_MO_COI'
    END AS tinh_trang
FROM don_hang d
ORDER BY d.ma_don_hang;
~~~

Nếu trong bảng nhập có **hai khách cùng mã 2**, EXISTS vẫn trả TRUE một lần cho câu hỏi “có khách mã 2 không?”. Truy vấn giữ **một dòng cho mỗi đơn** trong bảng ngoài.

Nhưng việc **có ít nhất một dòng khớp** không chứng minh bảng cha hợp lệ: khóa cha trùng vẫn có thể vi phạm quy tắc định danh. Vì vậy, cần **hai phép kiểm tra khác nhau**:

- Kiểm tra **tồn tại tham chiếu** bằng EXISTS/NOT EXISTS.
- Kiểm tra **tính duy nhất của khóa cha** bằng GROUP BY/HAVING hoặc constraint.

### 17.1. Một phép thống kê không thể thay thế cả hai

Nếu chỉ đếm số dòng sau JOIN, số dòng lớn bất thường có thể do:

- Một khách có nhiều đơn hợp lệ.
- Bảng khách trùng khóa.
- Một JOIN sai điều kiện và tạo nhiều cặp ngoài ý định.
- Có thêm bảng chi tiết một–nhiều.
- Một khóa ghép bị thiếu cột.
- Dữ liệu nguồn đã bị lặp trước khi JOIN.

Để chẩn đoán, cần kiểm tra **khóa của từng nguồn** và **tỷ lệ khớp của quan hệ**, không chỉ nhìn tổng số dòng trả về.

## 18. PRIMARY KEY, UNIQUE, FOREIGN KEY và NOT NULL

Các ràng buộc dữ liệu giúp ngăn nhiều lỗi JOIN trước khi chúng xảy ra.

### 18.1. PRIMARY KEY

Khóa chính xác định duy nhất một bản ghi và không cho NULL ở cột khóa theo ngữ nghĩa SQL thông thường:

~~~sql
CREATE TABLE khach_hang (
    ma_khach_hang INTEGER PRIMARY KEY,
    ten_khach_hang VARCHAR(100) NOT NULL
);
~~~

Một khách không thể có hai dòng trùng ma_khach_hang nếu constraint được thực thi đúng. Điều này giúp JOIN từ đơn sang khách có **tối đa một dòng khách** cho mỗi mã tham chiếu hợp lệ.

### 18.2. UNIQUE

UNIQUE ngăn các giá trị khóa lặp theo chính sách ràng buộc của DBMS. Với cột có thể NULL, cách xử lý nhiều NULL trong UNIQUE **khác nhau theo sản phẩm và tùy chọn**. Không nên suy luận rằng UNIQUE luôn coi hai NULL là trùng hay luôn cho phép nhiều NULL.

Nếu nghiệp vụ yêu cầu mã khách bắt buộc có và duy nhất, **PRIMARY KEY** hoặc tổ hợp **NOT NULL + UNIQUE** theo thiết kế phù hợp rõ ràng hơn một cột UNIQUE nhưng có thể NULL.

### 18.3. FOREIGN KEY

Khóa ngoại khai báo quan hệ tham chiếu tới bảng cha:

~~~sql
CREATE TABLE don_hang (
    ma_don_hang INTEGER PRIMARY KEY,
    ma_khach_hang INTEGER,
    trang_thai VARCHAR(20) NOT NULL,
    tong_tien DECIMAL(12, 2),
    CONSTRAINT fk_don_hang_khach
        FOREIGN KEY (ma_khach_hang)
        REFERENCES khach_hang(ma_khach_hang)
);
~~~

Trong nhiều DBMS, cột khóa ngoại **được phép NULL** nếu không khai báo NOT NULL; khi có giá trị không NULL, nó phải tham chiếu tới khóa hợp lệ ở bảng cha (trừ những cơ chế trì hoãn kiểm tra/tình huống đặc biệt được cấu hình).

Với cấu trúc này:

- **ma_khach_hang = 1**: được chấp nhận vì khách 1 tồn tại.
- **ma_khach_hang = 999**: thường bị FOREIGN KEY từ chối vì không có khách 999.
- **ma_khach_hang = NULL**: thường được chấp nhận nếu cột cho phép NULL, theo ngữ nghĩa khóa ngoại một cột.

Nếu mọi đơn bắt buộc thuộc về một khách:

~~~sql
ma_khach_hang INTEGER NOT NULL
~~~

kết hợp FOREIGN KEY sẽ ngăn cả **thiếu khóa** lẫn **khóa không tồn tại**, với điều kiện các constraint được thực thi.

### 18.4. Khóa ngoại không có nghĩa JOIN tự động xảy ra

FOREIGN KEY giúp đảm bảo quan hệ dữ liệu, nhưng câu SELECT vẫn phải viết JOIN phù hợp:

~~~sql
SELECT d.ma_don_hang, k.ten_khach_hang
FROM don_hang d
JOIN khach_hang k
    ON k.ma_khach_hang = d.ma_khach_hang;
~~~

Đừng giả định DBMS sẽ tự động đi từ bảng đơn tới bảng khách chỉ vì khóa ngoại đã được khai báo.

### 18.5. Quy tắc khi xóa bản ghi cha

Một FOREIGN KEY có thể có các hành vi khi xóa/cập nhật khóa cha, tùy thiết kế và DBMS:

- **RESTRICT / NO ACTION:** từ chối thao tác gây mất tham chiếu (thời điểm kiểm tra có thể khác trong vài hệ).
- **ON DELETE CASCADE:** xóa các bản ghi con liên quan khi xóa cha.
- **ON DELETE SET NULL:** đặt khóa ngoại của con thành NULL nếu cột và điều kiện hỗ trợ.
- **ON DELETE SET DEFAULT:** dùng giá trị mặc định theo hỗ trợ và ràng buộc tương ứng.

Ví dụ:

~~~sql
CONSTRAINT fk_don_hang_khach
FOREIGN KEY (ma_khach_hang)
REFERENCES khach_hang(ma_khach_hang)
ON DELETE SET NULL
~~~

Quy tắc này có thể phù hợp khi muốn giữ lịch sử đơn nhưng cho phép không còn liên kết khách. Tuy nhiên, nó biến quan hệ thành **thiếu khóa** khi xóa khách, và không phải lúc nào cũng phù hợp yêu cầu kiểm toán.

Không tự chọn CASCADE chỉ để tránh lỗi FOREIGN KEY: hành vi xóa dây chuyền có thể tác động đến dữ liệu quan trọng.

## 19. Tại sao vẫn có orphan dù hệ thống đã thiết kế FOREIGN KEY?

Các nguồn thường gặp:

1. **Bảng staging/import** không có constraint để nhận dữ liệu từ bên ngoài.
2. **Ràng buộc bị tắt hoặc chưa được kiểm tra lại** trong quá trình nạp dữ liệu hay migration.
3. **Dữ liệu cũ** tồn tại từ trước khi thêm FOREIGN KEY.
4. **Khóa mapping sai** do thay đổi hệ thống nguồn, đổi mã định danh hoặc ghép dữ liệu không cùng miền khóa.
5. **Đồng bộ không đồng thời:** bản ghi con đến trước bản ghi cha trong pipeline, tạo trạng thái thiếu tạm thời ở kho staging.
6. **Logic ứng dụng không ràng buộc:** quan hệ chỉ được mô tả trên giấy/tầng ORM, nhưng DBMS không có FOREIGN KEY thực thi.
7. **Khóa ghép thiếu cột:** giá trị tồn tại ở một tenant khác nhưng không tồn tại trong đúng tenant.

Khi phát hiện orphan, cần kiểm tra nguồn gốc và quy tắc nghiệp vụ trước khi sửa. Đôi khi bảng cha chưa được nạp, và cách đúng là **hoàn thiện đồng bộ** thay vì xóa bản ghi con.

### 19.1. Thêm FOREIGN KEY vào bảng đang có dữ liệu lỗi

Nếu bảng don_hang đang chứa đơn 105 tham chiếu 999, việc thêm ràng buộc FOREIGN KEY có kiểm tra dữ liệu hiện có thường thất bại hoặc đòi xử lý dữ liệu trước. Cách triển khai constraint, tình trạng “trusted/validated” và cơ chế tạm hoãn kiểm tra khác nhau theo DBMS.

Quy trình chung:

1. Kiểm tra NULL và orphan trên bảng con.
2. Xác định bản ghi thiếu cha là lỗi thật hay do pipeline chưa hoàn tất.
3. Sửa mapping, nạp cha còn thiếu hoặc xử lý bản ghi lỗi theo chính sách đã phê duyệt.
4. Kiểm tra khóa cha có duy nhất không.
5. Thêm/kiểm tra lại FOREIGN KEY theo tính năng của hệ quản trị.
6. Giám sát để phát hiện sự cố nạp dữ liệu tái xuất hiện.

**Không dùng việc thêm constraint thất bại như tín hiệu tự động xóa dữ liệu.**

## 20. Khóa ghép: nối thiếu một cột có thể tạo bản ghi “giả khớp”

Trong hệ thống đa khách hàng doanh nghiệp (*multi-tenant*), mã 15 có thể tồn tại ở nhiều tenant. Một khóa định danh có thể là cặp:

~~~text
(tenant_id, ma_khach_hang)
~~~

Giả sử:

**khach_hang**

| tenant_id | ma_khach_hang | ten_khach_hang |
|---|---:|---|
| A | 15 | An - Tenant A |
| B | 15 | Bình - Tenant B |

**don_hang**

| tenant_id | ma_don_hang | ma_khach_hang |
|---|---:|---:|
| A | 201 | 15 |

JOIN sai:

~~~sql
SELECT
    d.ma_don_hang,
    k.ten_khach_hang
FROM don_hang d
JOIN khach_hang k
    ON d.ma_khach_hang = k.ma_khach_hang;
~~~

Đơn A–201 sẽ khớp **cả hai khách A–15 và B–15**, tạo hai dòng và có nguy cơ làm lộ/ghép sai dữ liệu giữa các tenant.

JOIN đúng:

~~~sql
SELECT
    d.tenant_id,
    d.ma_don_hang,
    k.ten_khach_hang
FROM don_hang d
JOIN khach_hang k
    ON d.tenant_id = k.tenant_id
   AND d.ma_khach_hang = k.ma_khach_hang;
~~~

Chỉ có **A–15** khớp đơn A–201.

**Nguyên tắc:** tham chiếu phải sử dụng **đầy đủ các cột tạo nên định danh quan hệ**, không chỉ chọn cột tên giống nhau hoặc một phần khóa ghép.

Khi quan hệ dùng khóa ghép, FOREIGN KEY tương ứng cũng cần được thiết kế trỏ tới tổ hợp khóa duy nhất đúng miền dữ liệu. Quy tắc NULL trong khóa ngoại ghép có khác biệt giữa các cơ chế MATCH và DBMS; không nên áp dụng máy móc quy tắc khóa ngoại một cột.

## 21. Sai kiểu dữ liệu, khoảng trắng và collation có thể tạo “thiếu tham chiếu giả”

Không phải mọi dòng không khớp đều do khóa cha thật sự vắng mặt. Đôi khi hai giá trị **trông giống nhau** nhưng không so sánh bằng theo DBMS hoặc đã bị biến đổi:

- Bảng A lưu khóa dạng số **101**; bảng B lưu khóa dạng chuỗi **'00101'**.
- Mã chứa dấu cách đầu/cuối, ví dụ **'AB12'** và **' AB12 '**.
- Khóa chữ phân biệt hoa/thường, ví dụ **'abc'** và **'ABC'**.
- Khác kiểu mã Unicode chuẩn hóa: ký tự ghép sẵn với ký tự cơ sở + dấu kết hợp.
- Khác charset/collation nên phép so sánh có quy tắc khác.
- Sai phiên bản mapping mã khách giữa hai hệ thống.

Không nên lập tức dùng:

~~~sql
ON TRIM(LOWER(a.ma)) = TRIM(LOWER(b.ma))
~~~

để “chữa” mọi dữ liệu không khớp. Cách này có thể **nhập hai khóa vốn phải phân biệt**, gây nhân dòng, hoặc làm điều kiện khó tận dụng chỉ mục thông thường. Với mã định danh, phải có **đặc tả chuẩn hóa** chính thức và xử lý dữ liệu ở bước nhập/migration thích hợp.

Nếu hai cột dùng kiểu số và chuỗi, ép kiểu tự động có thể gây lỗi, chuyển đổi bất ngờ hoặc khiến tối ưu kém. Một truy vấn JOIN đúng cần điều kiện so sánh giữa **các kiểu tương thích theo thiết kế**.

### 21.1. NATURAL JOIN và USING: không thay thế việc hiểu khóa

Một số DBMS hỗ trợ:

~~~sql
FROM bang_a a
JOIN bang_b b USING (ma_khach_hang)
~~~

Cú pháp USING gọn khi cột khóa có cùng tên và ngữ nghĩa tương thích, nhưng vẫn chịu quy tắc NULL và trùng khóa như JOIN theo bằng thông thường.

**NATURAL JOIN** tự suy ra các cột cùng tên làm điều kiện nối. Nó dễ rủi ro trong hệ thống thay đổi schema: thêm một cột cùng tên ở hai bảng có thể âm thầm đổi điều kiện JOIN. Khi điều tra lỗi NULL, duplicate hoặc orphan, **ON tường minh** thường dễ kiểm tra nhất.

## 22. So sánh an toàn với NULL khi nghiệp vụ muốn hai NULL khớp

Đôi khi dữ liệu không phải quan hệ khóa chính–khóa ngoại mà là **so sánh hai tập thuộc tính**, trong đó nghiệp vụ cố ý xem **hai giá trị NULL là tương đương**.

SQL có phép:

~~~sql
a.cot IS NOT DISTINCT FROM b.cot
~~~

Ở các DBMS hỗ trợ, nó trả TRUE khi:

- Hai giá trị không NULL bằng nhau.
- **Cả hai cùng NULL**.

Ví dụ về các phép so sánh:

| a | b | a = b | a IS NOT DISTINCT FROM b |
|---|---|---|---|
| 2 | 2 | TRUE | TRUE |
| 2 | 3 | FALSE | FALSE |
| 2 | NULL | UNKNOWN | FALSE |
| NULL | 2 | UNKNOWN | FALSE |
| NULL | NULL | UNKNOWN | TRUE |

PostgreSQL hỗ trợ IS [NOT] DISTINCT FROM; SQL Server có từ phiên bản 2022; MySQL thường dùng toán tử so sánh an toàn với NULL **<=>**; các hệ khác có cú pháp và giới hạn riêng.

Trong một số hệ, có thể viết điều kiện tương đương về mặt ý nghĩa:

~~~sql
ON a.ma = b.ma
OR (a.ma IS NULL AND b.ma IS NULL)
~~~

**Nhưng không nên dùng điều kiện đó mặc định cho quan hệ khóa ngoại.** Nếu bảng trái có **3 dòng khóa NULL**, bảng phải có **2 dòng khóa NULL**, một JOIN coi NULL = NULL sẽ tạo **3 × 2 = 6 cặp khớp** chỉ riêng nhóm NULL. Chúng không nhất thiết đại diện cho sáu quan hệ có ý nghĩa nghiệp vụ.

### 22.1. Vì sao COALESCE về một giá trị giả có thể nguy hiểm?

Một mẹo thường thấy:

~~~sql
ON COALESCE(a.ma, -1) = COALESCE(b.ma, -1)
~~~

Nếu **-1** là khóa có thật ở một phía, nó sẽ bị gộp nhầm với NULL. Thậm chí khi -1 hiện chưa xuất hiện, quy ước có thể bị phá vỡ trong tương lai hoặc khi di chuyển hệ thống. Hàm trên cột còn có thể ảnh hưởng khả năng sử dụng chỉ mục.

Nếu mục đích là so sánh an toàn với NULL, dùng **toán tử null-safe phù hợp DBMS** hoặc một điều kiện tường minh được thiết kế có chủ đích; nếu mục đích là quan hệ khóa ngoại, hãy kiểm tra khóa theo quy tắc dữ liệu thay vì tự nối các NULL.

## 23. NOT IN và NOT EXISTS khi tìm bản ghi không có tham chiếu

Một truy vấn “tìm đơn không thuộc khách nào” dễ được viết bằng NOT IN:

~~~sql
SELECT d.ma_don_hang
FROM don_hang d
WHERE d.ma_khach_hang NOT IN (
    SELECT k.ma_khach_hang
    FROM khach_hang k
);
~~~

Với bảng khach_hang chuẩn có khóa chính NOT NULL, tập con không chứa NULL. Truy vấn trả **đơn 105** nhưng **không trả đơn 104** vì **d.ma_khach_hang = NULL** làm NOT IN trả UNKNOWN.

Nếu bảng nguồn khóa ở truy vấn con **cũng có NULL**, NOT IN còn có thể tạo kết quả bất ngờ hoặc rỗng ngoài ý định.

### 23.1. Dùng NOT EXISTS cho ý định “không có dòng khớp”

~~~sql
SELECT d.ma_don_hang, d.ma_khach_hang
FROM don_hang d
WHERE NOT EXISTS (
    SELECT 1
    FROM khach_hang k
    WHERE k.ma_khach_hang = d.ma_khach_hang
)
ORDER BY d.ma_don_hang;
~~~

Với dữ liệu mẫu, kết quả gồm **104 và 105**:

- Đơn 104: khóa NULL không khớp bất kỳ khóa khách nào bằng =.
- Đơn 105: khóa 999 không có khách.

Nếu chỉ muốn orphan **có giá trị khóa**, thêm:

~~~sql
WHERE d.ma_khach_hang IS NOT NULL
  AND NOT EXISTS (
      SELECT 1
      FROM khach_hang k
      WHERE k.ma_khach_hang = d.ma_khach_hang
  )
~~~

Kết quả chỉ có **105**.

**EXISTS/NOT EXISTS không bị “nhiễm UNKNOWN” theo cách NOT IN bị ảnh hưởng khi có NULL trong danh sách.** EXISTS chỉ kiểm tra có ít nhất một dòng thỏa truy vấn con hay không. Tuy nhiên, phép so sánh bên trong truy vấn con vẫn có ngữ nghĩa NULL; cần xác định chính sách cho khóa ngoài NULL.

### 23.2. Tìm khách không có đơn bằng NOT EXISTS

~~~sql
SELECT k.ma_khach_hang, k.ten_khach_hang
FROM khach_hang k
WHERE NOT EXISTS (
    SELECT 1
    FROM don_hang d
    WHERE d.ma_khach_hang = k.ma_khach_hang
)
ORDER BY k.ma_khach_hang;
~~~

Kết quả: **Chi (3)** và **Dũng (4)**.

Cách này **không nhân dòng khách** cho dù một khách có nhiều đơn. Nó thể hiện đúng câu hỏi **“không tồn tại bất kỳ đơn khớp nào”**, trong khi INNER JOIN là thao tác tạo các cặp dòng khớp.

## 24. JOIN khóa trùng và DISTINCT: khi nào nên, khi nào không?

Một cách “chữa” số dòng nhiều hơn dự kiến là:

~~~sql
SELECT DISTINCT k.ma_khach_hang, k.ten_khach_hang
FROM khach_hang_nhap k
JOIN don_hang d
    ON d.ma_khach_hang = k.ma_khach_hang;
~~~

Câu này có thể làm hai dòng nguồn trùng cùng tên biến thành một dòng hiển thị, nhưng **không xác nhận dữ liệu gốc có đúng không**. Nếu tên của hai bản ghi trùng khóa khác nhau, cả hai có thể vẫn xuất hiện; nếu có cột khác trong SELECT, DISTINCT lại có kết quả khác.

DISTINCT thích hợp khi **ý định** thật sự là “danh sách các tổ hợp cột phân biệt”. Nó không thay thế ràng buộc khóa duy nhất, xử lý orphan hoặc phân tích mức chi tiết của JOIN.

Nếu chỉ muốn khách **có ít nhất một đơn**, rõ hơn là:

~~~sql
SELECT k.ma_khach_hang, k.ten_khach_hang
FROM khach_hang k
WHERE EXISTS (
    SELECT 1
    FROM don_hang d
    WHERE d.ma_khach_hang = k.ma_khach_hang
);
~~~

Câu này dựa vào bảng khách chuẩn có một dòng mỗi mã. Nếu chính bảng khách bị trùng khóa, EXISTS sẽ trả từng dòng khách trùng; vì vậy vẫn cần sửa nguồn dữ liệu.

## 25. JOIN nhiều bảng: rủi ro nhân dòng theo tầng

Giả sử có quan hệ:

~~~text
khach_hang (1) --- (N) don_hang (1) --- (N) chi_tiet_don_hang
                                          |
                                         (N)
                                          |
                                       san_pham
~~~

Khi JOIN khách → đơn → chi tiết, một khách xuất hiện **một dòng trên mỗi chi tiết của từng đơn**, không phải một dòng trên mỗi khách hay một dòng trên mỗi đơn.

Nếu tiếp tục JOIN một bảng khác cũng có nhiều dòng cho cùng đơn (ví dụ bảng thanh toán nhiều đợt), các tổ hợp có thể tạo **phép nhân giữa các nhóm con**.

Ví dụ:

- Một đơn có **3 dòng chi tiết sản phẩm**.
- Cùng đơn có **2 dòng thanh toán**.

JOIN cả hai bảng con trực tiếp theo ma_don_hang có thể tạo:

~~~text
3 dòng chi tiết × 2 dòng thanh toán = 6 dòng kết quả
~~~

Nếu SUM số lượng chi tiết sau JOIN, mỗi dòng chi tiết có thể bị tính hai lần. Nếu SUM số tiền thanh toán, mỗi dòng thanh toán có thể bị tính ba lần.

### 25.1. Tách tổng hợp ở đúng grain

~~~sql
WITH tien_thanh_toan AS (
    SELECT
        ma_don_hang,
        SUM(so_tien) AS da_thanh_toan
    FROM thanh_toan
    GROUP BY ma_don_hang
),
so_luong_san_pham AS (
    SELECT
        ma_don_hang,
        SUM(so_luong) AS so_luong
    FROM chi_tiet_don_hang
    GROUP BY ma_don_hang
)
SELECT
    d.ma_don_hang,
    t.da_thanh_toan,
    s.so_luong
FROM don_hang d
LEFT JOIN tien_thanh_toan t
    ON t.ma_don_hang = d.ma_don_hang
LEFT JOIN so_luong_san_pham s
    ON s.ma_don_hang = d.ma_don_hang;
~~~

Mỗi CTE tổng hợp về **một dòng mỗi mã đơn**, sau đó mới JOIN. Cách này tránh phép nhân giữa hai nguồn nhiều dòng. Tên bảng **thanh_toan** chỉ là ví dụ; quy tắc tiền thanh toán cần tùy nghiệp vụ (hoàn tiền, thanh toán thất bại, nhiều đơn vị tiền tệ, v.v.).

## 26. Kiểm thử JOIN với dữ liệu có chủ đích

Một bộ thử chỉ gồm khóa hợp lệ, không NULL và duy nhất thường không bộc lộ lỗi. Nên thiết kế dữ liệu đại diện cho các trường hợp:

| Nhóm kiểm thử | Dữ liệu | Điều cần xác nhận |
|---|---|---|
| Khớp một–một | 1 khóa trái ↔ 1 khóa phải | Trả đúng 1 cặp |
| Khớp một–nhiều | 1 khóa trái ↔ 2 đơn | Có đúng 2 cặp, không tự gộp |
| Khóa trái không có phải | Khách 3, 4 không có đơn | INNER loại, LEFT giữ |
| Khóa phải không có trái | Đơn 105 trỏ 999 | INNER loại, RIGHT giữ |
| Khóa phải NULL | Đơn 104 | = không khớp, phân loại THIEU_KHOA |
| Trùng khóa bảng cha | 2 khách cùng mã 2 ở staging | JOIN nhân các đơn mã 2 |
| Dữ liệu thật có cột NULL | Đơn 106 tong_tien NULL | Không nhầm với dòng outer được đệm |
| Nhiều dòng con ở hai bảng | 3 chi tiết, 2 thanh toán | Tránh nhân 6 dòng khi tổng hợp |
| Khóa ghép | Hai tenant cùng mã khách | JOIN phải dùng cả tenant_id và mã khách |
| Khác kiểu/collation | 'abc'/'ABC', 101/'00101' | Kết quả đúng quy tắc định danh |
| Danh sách NOT IN có NULL | NULL trong tập con | Tránh kết quả bất ngờ |
| Không có dòng ở cả nguồn | Bảng rỗng | Hiểu INNER/OUTER JOIN và tập kết quả |
| Dữ liệu thay đổi khi đọc | Cha bị xóa/con được thêm trong transaction | Xem mức nhất quán và ràng buộc |

### 26.1. Bảng dự đoán số dòng từ dữ liệu mẫu

Với bảng khách 4 dòng và bảng đơn 6 dòng như phần 2:

| Truy vấn | Số dòng mong đợi |
|---|---:|
| INNER JOIN theo mã khách | 4 |
| LEFT JOIN khách → đơn | 6 |
| RIGHT JOIN khách → đơn | 6 |
| FULL OUTER JOIN | 8 |
| LEFT JOIN + WHERE d.ma_don_hang IS NULL | 2 |
| Đơn d LEFT JOIN khách k + WHERE k.ma_khach_hang IS NULL | 2 |
| Orphan có khóa (d.ma_khach_hang IS NOT NULL, thiếu cha) | 1 |

Đây là bảng kiểm tra có thể dùng làm **oracle** cho bộ test. Nếu số dòng thực tế khác, cần xem lại dữ liệu nguồn, điều kiện JOIN, số dòng trùng và điều kiện WHERE bổ sung.

### 26.2. Không kiểm tra chỉ bằng tổng số dòng

Hai truy vấn khác nhau có thể đều trả **6 dòng** nhưng là sáu dòng khác nhau. Vì vậy, bộ test nên so sánh **tập cặp khóa** hoặc kết quả chi tiết:

~~~text
INNER JOIN mong đợi:
(1, 101)
(1, 102)
(2, 103)
(2, 106)
~~~

Với outer join, ghi rõ các hàng không khớp và NULL đệm. Nếu thứ tự dòng là một phần yêu cầu kiểm thử, phải có **ORDER BY** tường minh; JOIN tự nó không bảo đảm thứ tự.

## 27. Phân biệt lỗi dữ liệu và lỗi truy vấn

Một truy vấn JOIN có thể không trả dòng vì:

1. **Không có quan hệ thực:** khóa ngoại đúng là NULL hoặc không có bản ghi tương ứng theo nghiệp vụ.
2. **Dữ liệu sai:** mã tham chiếu không tồn tại, khóa cha trùng, giá trị không chuẩn hóa.
3. **Viết sai JOIN:** nối nhầm cột, thiếu cột trong khóa ghép, dùng INNER thay LEFT.
4. **Điều kiện WHERE loại dòng OUTER JOIN:** ví dụ d.trang_thai = 'PAID' ở WHERE.
5. **Kiểu/collation không tương thích:** so sánh hai khóa có cách lưu khác nhau.
6. **Tập nguồn bị lọc từ trước:** CTE/bảng dẫn xuất đã loại bản ghi cần thiết.
7. **Dữ liệu thay đổi đồng thời:** các truy vấn khác nhau đọc snapshot khác nhau.

Cách tiếp cận điều tra:

- Kiểm tra **từng bảng riêng** để biết dòng nguồn có tồn tại.
- Kiểm tra **giá trị khóa** của bản ghi đang thiếu.
- Kiểm tra **NULL** và **khóa trùng** ở cả hai nguồn.
- Thử **LEFT JOIN và hiển thị cả khóa trái lẫn khóa phải** để nhìn điểm không khớp.
- Xem lại **ON**, **WHERE** và đầy đủ cột khóa ghép.
- Xác nhận ràng buộc và kiểu dữ liệu.
- Chỉ sau khi đúng ngữ nghĩa mới đánh giá hiệu năng và kế hoạch truy vấn.

## 28. Hiệu năng: chỉ mục, tính chọn lọc và cardinality

Ngoài tính đúng, NULL và khóa trùng ảnh hưởng số dòng dự kiến mà DBMS phải xử lý.

### 28.1. Chỉ mục trên cột tham chiếu

Một bảng đơn lớn thường được JOIN theo **don_hang.ma_khach_hang**. Tùy DBMS và nhu cầu truy vấn, chỉ mục trên cột này có thể giúp tìm đơn của từng khách nhanh hơn:

~~~sql
CREATE INDEX idx_don_hang_ma_khach
ON don_hang (ma_khach_hang);
~~~

**Không nên mặc định FOREIGN KEY luôn tự tạo chỉ mục ở phía bảng con.** Điều đó tùy sản phẩm và cấu hình. PRIMARY KEY/UNIQUE thường đi kèm cơ chế truy cập phù hợp để bảo đảm duy nhất, nhưng cách tổ chức cũng khác.

### 28.2. Khóa trùng làm thay đổi cardinality

Nếu một giá trị khóa xuất hiện nhiều lần ở cả hai nguồn, số dòng JOIN có thể tăng mạnh. Bộ tối ưu dựa vào thống kê dữ liệu, phân phối khóa và ràng buộc để ước lượng **cardinality** (số dòng). Khi thống kê cũ hoặc dữ liệu bị skew nặng, kế hoạch có thể kém hiệu quả.

Ràng buộc khóa chính và khóa duy nhất có thể giúp DBMS suy luận tính duy nhất, nhưng trước tiên dữ liệu phải thực sự tuân thủ ràng buộc.

### 28.3. Tránh biến đổi khóa không cần thiết trong ON

~~~sql
-- Có thể khó tận dụng chỉ mục thường trên khóa gốc.
ON CAST(d.ma_khach_hang AS VARCHAR(20)) = k.ma_khach_text
~~~

hoặc:

~~~sql
ON TRIM(LOWER(a.ma)) = TRIM(LOWER(b.ma))
~~~

có thể có chi phí xử lý và rủi ro ngữ nghĩa. Tốt hơn là xác định **định dạng khóa thống nhất tại bước nhập** hoặc dùng cột chuẩn hóa/functional index được thiết kế rõ, thay vì cố tình ép kiểu trong mọi JOIN.

### 28.4. Đúng dữ liệu trước, tối ưu sau

Không dùng DISTINCT chỉ để làm số dòng nhỏ lại hoặc chuyển LEFT JOIN thành INNER JOIN chỉ để có kế hoạch “nhanh hơn”, nếu yêu cầu cần giữ các dòng không khớp. Cần phân biệt **truy vấn chậm do dữ liệu nhiều hợp lệ** với **truy vấn sai làm bùng nổ số dòng**.

Dùng công cụ execution plan như **EXPLAIN**, **EXPLAIN ANALYZE** hoặc các công cụ tương đương DBMS để đo kế hoạch, số dòng ước lượng/thực tế và chi phí. Không suy đoán chỉ từ cú pháp rằng một kiểu JOIN luôn nhanh nhất.

## 29. Áp dụng trong Java/JDBC

Ứng dụng Java thường truy vấn bảng đơn kèm tên khách. Với dữ liệu có khả năng thiếu tham chiếu, phải lựa chọn **INNER** hoặc **LEFT** theo mục đích.

### 29.1. Hiển thị tất cả đơn, kể cả đơn chưa tìm được khách

~~~java
String sql = """
    SELECT
        d.ma_don_hang,
        d.ma_khach_hang,
        k.ten_khach_hang,
        d.tong_tien
    FROM don_hang d
    LEFT JOIN khach_hang k
        ON k.ma_khach_hang = d.ma_khach_hang
    ORDER BY d.ma_don_hang
    """;

try (PreparedStatement ps = connection.prepareStatement(sql);
     ResultSet rs = ps.executeQuery()) {
    while (rs.next()) {
        int maDon = rs.getInt("ma_don_hang");
        String tenKhach = rs.getString("ten_khach_hang");
        java.math.BigDecimal tongTien =
            rs.getBigDecimal("tong_tien");

        System.out.println(
            maDon + " | " +
            (tenKhach == null ? "(chưa tìm thấy khách)" : tenKhach) +
            " | " + tongTien
        );
    }
}
~~~

Ở ví dụ, **getString** trả Java null khi cột SQL NULL. Với cột kiểu số nguyên có thể NULL, **getInt** trả 0 khi SQL NULL và cần **rs.wasNull()** ngay sau khi đọc để phân biệt 0 thật; hoặc dùng API đối tượng phù hợp với driver.

Không nên chỉ dựa vào **tenKhach == null** để kết luận **bản ghi khách không tồn tại** nếu bảng khách thật cho phép ten_khach_hang NULL. Khi cần phân loại chắc chắn, SELECT thêm **k.ma_khach_hang** (khóa chính NOT NULL khi có dòng) và **d.ma_khach_hang** để phân biệt thiếu khóa với orphan.

### 29.2. Lọc một khách cụ thể bằng tham số

~~~java
String sql = """
    SELECT d.ma_don_hang, d.tong_tien
    FROM don_hang d
    WHERE d.ma_khach_hang = ?
    ORDER BY d.ma_don_hang
    """;

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setInt(1, 2);

    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            System.out.println(rs.getInt("ma_don_hang"));
        }
    }
}
~~~

Đây là truy vấn lọc đơn theo mã khách, không nhất thiết cần JOIN bảng khách nếu chỉ cần thuộc tính của đơn. Việc dùng PreparedStatement giúp truyền tham số đúng kiểu và tránh ghép SQL từ dữ liệu đầu vào.

Nếu tham số khóa là NULL, **d.ma_khach_hang = ?** khi bind NULL sẽ không tự tìm đơn 104. Khi cần tìm đơn chưa gán khách, dùng điều kiện **d.ma_khach_hang IS NULL** theo yêu cầu nghiệp vụ.

### 29.3. Tránh “sửa” mồ côi bằng giá trị ngầm

Giả sử ứng dụng muốn thay mọi tên khách không tìm được bằng **'Khách lẻ'**:

~~~sql
SELECT
    d.ma_don_hang,
    COALESCE(k.ten_khach_hang, 'Khách lẻ') AS ten_hien_thi
FROM don_hang d
LEFT JOIN khach_hang k
    ON k.ma_khach_hang = d.ma_khach_hang;
~~~

Điều này **chỉ là nhãn hiển thị**; không biến đơn 105 thành đơn thuộc khách “Khách lẻ” trong quan hệ dữ liệu. Khi cần xử lý nghiệp vụ chính xác, nên mang theo **trạng thái tham chiếu** và giá trị khóa gốc để không che khuất lỗi dữ liệu.

## 30. Các lỗi thường gặp và cách sửa

| Ngộ nhận/lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Nghĩ **NULL = NULL** trong ON là TRUE | Dòng có khóa NULL không khớp như dự kiến | Dùng IS NULL để kiểm tra; chỉ dùng null-safe JOIN khi nghiệp vụ yêu cầu |
| Dùng INNER JOIN để tìm đơn chưa có khách | Dòng không khớp bị loại khỏi kết quả | Dùng don_hang LEFT JOIN khach_hang rồi kiểm tra khóa phải NULL |
| Gộp khóa NULL với khóa 999 | Không biết dữ liệu thiếu hay tham chiếu mồ côi | Phân loại riêng THIEU_KHOA/THAM_CHIEU_MO_COI |
| Dùng **d.tong_tien IS NULL** để tìm khách không có đơn | Đơn thật có tiền NULL bị phân loại sai | Kiểm tra khóa NOT NULL của bảng phải hoặc NOT EXISTS |
| Dùng **COUNT(*)** sau LEFT JOIN để đếm đơn | Khách không có đơn có thể bị đếm 1 | COUNT(d.ma_don_hang) |
| Dùng **COUNT(d.tong_tien)** để đếm số đơn | Đơn có tiền NULL không được đếm | Dùng định danh đơn NOT NULL |
| Đặt điều kiện cột phải của LEFT JOIN vào WHERE | Dòng trái không có khớp có thể bị loại | Đặt điều kiện ghép trong ON khi muốn giữ trái |
| Cho rằng LEFT JOIN trả chính xác một dòng mỗi khách | Khách có nhiều đơn vẫn xuất hiện nhiều dòng | GROUP BY/EXISTS/chọn dòng theo đúng yêu cầu |
| Cho rằng khóa trùng ở mọi bảng đều sai | Khóa ngoại được phép lặp trong quan hệ một–nhiều | Xác định grain/khóa thật trước khi chẩn đoán |
| Trùng khóa ở bảng cha nhưng không kiểm tra | JOIN nhân dữ liệu con | PRIMARY KEY/UNIQUE, kiểm tra duplicate ở staging |
| Dùng DISTINCT để che số dòng tăng | Che lỗi và không bảo đảm tổng hợp đúng | Kiểm tra điều kiện JOIN và tính duy nhất |
| Dùng SUM(DISTINCT tien) để sửa SUM bị lặp | Hai đơn cùng tiền bị gộp | Tổng hợp theo mã đơn/khách đúng grain |
| Dùng NOT IN với tập có NULL | Có thể không tìm được bản ghi mong đợi | NOT EXISTS hoặc xử lý NULL rõ ràng |
| Nối thiếu tenant_id trong khóa ghép | Sai cặp, có nguy cơ lộ dữ liệu tenant | JOIN trên đầy đủ khóa ghép |
| Dùng COALESCE(khoa, -1) trong ON | NULL có thể ghép nhầm với -1 thật | Thiết kế null-safe rõ ràng hoặc sửa dữ liệu |
| Tin FOREIGN KEY sẽ tự JOIN bảng | Truy vấn vẫn phải nêu quan hệ | Viết ON rõ ràng |
| Thêm FK khi dữ liệu đang mồ côi mà không xử lý | Migration/constraint thất bại hoặc không được xác thực | Kiểm tra và làm sạch dữ liệu trước |
| Dùng NATURAL JOIN mà không xem schema | Thêm cột cùng tên có thể đổi điều kiện JOIN | ON tường minh |
| Tin JOIN tự sắp xếp kết quả | Thứ tự không được bảo đảm | ORDER BY cuối cùng |

## 31. Bài tập tự luyện

Các bài dưới đây sử dụng bảng **khach_hang** và **don_hang** ở phần 2, trừ khi đề bài nói rõ bảng khác. Mỗi bài có đáp án gợi ý để tự đối chiếu.

### Bài 1 — Đếm dòng INNER JOIN

Với bốn khách 1, 2, 3, 4 và sáu đơn 101–106 trong dữ liệu mẫu, truy vấn sau trả bao nhiêu dòng?

~~~sql
SELECT k.ma_khach_hang, d.ma_don_hang
FROM khach_hang k
INNER JOIN don_hang d
    ON k.ma_khach_hang = d.ma_khach_hang;
~~~

<details>
<summary>Đáp án gợi ý</summary>

**4 dòng:** (1,101), (1,102), (2,103), (2,106). Đơn 104 có mã khách NULL, đơn 105 trỏ 999; khách 3 và 4 không có đơn.

</details>

### Bài 2 — LEFT JOIN có bao nhiêu dòng?

~~~sql
SELECT k.ma_khach_hang, d.ma_don_hang
FROM khach_hang k
LEFT JOIN don_hang d
    ON k.ma_khach_hang = d.ma_khach_hang;
~~~

Kết quả có bao nhiêu dòng và vì sao?

<details>
<summary>Đáp án gợi ý</summary>

**6 dòng:** bốn cặp khớp và hai khách 3, 4 không có đơn được giữ bằng hai dòng đệm NULL ở phía đơn.

</details>

### Bài 3 — NULL dữ liệu thật hay NULL do LEFT JOIN?

Khi LEFT JOIN khách → đơn, có dòng kết quả:

~~~text
ma_khach_hang = 2, ma_don_hang = 106, tong_tien = NULL
~~~

Có thể kết luận khách 2 chưa từng có đơn không?

<details>
<summary>Đáp án gợi ý</summary>

**Không.** Đơn 106 tồn tại thật, nhưng cột tong_tien của chính đơn đó là NULL. Nếu tìm khách không có đơn, dùng **d.ma_don_hang IS NULL** vì ma_don_hang là khóa chính NOT NULL của đơn thật.

</details>

### Bài 4 — Phân biệt orphan và thiếu khóa

Đơn nào có **khóa NULL** và đơn nào có **tham chiếu mồ côi** trong dữ liệu mẫu?

<details>
<summary>Đáp án gợi ý</summary>

**Đơn 104** có ma_khach_hang NULL (thiếu khóa); **đơn 105** có ma_khach_hang = 999 nhưng không có khách 999 (orphan có khóa cụ thể).

</details>

### Bài 5 — Viết truy vấn tìm orphan có khóa

Viết truy vấn trả mã đơn và mã khách của **đơn có ma_khach_hang không NULL nhưng không tìm được khách**.

<details>
<summary>Đáp án gợi ý</summary>

~~~sql
SELECT d.ma_don_hang, d.ma_khach_hang
FROM don_hang d
WHERE d.ma_khach_hang IS NOT NULL
  AND NOT EXISTS (
      SELECT 1
      FROM khach_hang k
      WHERE k.ma_khach_hang = d.ma_khach_hang
  );
~~~

Kết quả: **105, 999**. Có thể dùng LEFT JOIN + kiểm tra khóa bảng phải NULL với cùng điều kiện d.ma_khach_hang IS NOT NULL.

</details>

### Bài 6 — Vì sao WHERE khác ON?

Yêu cầu “mọi khách, kèm đơn PAID nếu có”. Nên đặt **d.trang_thai = 'PAID'** trong ON hay WHERE của LEFT JOIN?

<details>
<summary>Đáp án gợi ý</summary>

Đặt trong **ON**:

~~~sql
SELECT k.ma_khach_hang, d.ma_don_hang
FROM khach_hang k
LEFT JOIN don_hang d
    ON d.ma_khach_hang = k.ma_khach_hang
   AND d.trang_thai = 'PAID';
~~~

Nếu đặt trong WHERE, khách 3 và 4 có dòng đệm NULL bị loại vì NULL = 'PAID' là UNKNOWN.

</details>

### Bài 7 — Số cặp khi khóa trùng

Bảng trái có **3 dòng** khóa X; bảng phải có **4 dòng** khóa X. INNER JOIN bằng khóa X tạo bao nhiêu cặp?

<details>
<summary>Đáp án gợi ý</summary>

**12 cặp (3 × 4)**, giả sử điều kiện ON chỉ yêu cầu các khóa X bằng nhau và không có điều kiện khác loại cặp. JOIN theo đa tập không tự loại dòng trùng.

</details>

### Bài 8 — Trùng khóa hợp lệ hay lỗi?

Một khách có hai đơn cùng ma_khach_hang = 2. Điều này có nhất thiết vi phạm khóa dữ liệu không? Nếu bảng khach_hang có hai dòng ma_khach_hang = 2 thì sao?

<details>
<summary>Đáp án gợi ý</summary>

Hai đơn cùng mã khách 2 là **hợp lệ** trong quan hệ một–nhiều. Nhưng hai dòng ở bảng khách có cùng ma_khach_hang = 2 là **không hợp lệ** nếu ma_khach_hang được định nghĩa là PRIMARY KEY hoặc được yêu cầu duy nhất.

</details>

### Bài 9 — Đếm đơn sau LEFT JOIN

Viết truy vấn đếm số đơn mỗi khách, gồm cả khách chưa có đơn với kết quả 0.

<details>
<summary>Đáp án gợi ý</summary>

~~~sql
SELECT
    k.ma_khach_hang,
    k.ten_khach_hang,
    COUNT(d.ma_don_hang) AS so_don
FROM khach_hang k
LEFT JOIN don_hang d
    ON d.ma_khach_hang = k.ma_khach_hang
GROUP BY k.ma_khach_hang, k.ten_khach_hang;
~~~

Kết quả: khách 1 = 2, khách 2 = 2, khách 3 = 0, khách 4 = 0.

</details>

### Bài 10 — Vì sao SUM sau JOIN sai?

Đơn 101 có tong_tien = 200000 và hai dòng chi tiết; đơn 102 có tong_tien = 150000 và một dòng chi tiết. Nếu JOIN đơn với chi tiết rồi SUM(tong_tien) của đơn, kết quả cho khách 1 là bao nhiêu? Tổng đúng là bao nhiêu?

<details>
<summary>Đáp án gợi ý</summary>

Sau JOIN: **200000 + 200000 + 150000 = 550000**. Tổng đúng theo hai đơn là **200000 + 150000 = 350000**. Cần SUM từ bảng đơn ở grain mỗi đơn hoặc tổng hợp riêng trước khi JOIN.

</details>

### Bài 11 — SUM(DISTINCT) có giải quyết được không?

Nếu có hai đơn khác nhau cùng tong_tien = 200000, dùng **SUM(DISTINCT tong_tien)** có thể làm sai báo cáo như thế nào?

<details>
<summary>Đáp án gợi ý</summary>

SUM(DISTINCT tong_tien) chỉ cộng **một lần mỗi giá trị tiền khác biệt**, nên hai đơn thật khác nhau cùng tiền có thể bị tính một lần, làm thiếu doanh thu. Nó không phải cách loại dòng trùng dựa theo mã đơn.

</details>

### Bài 12 — JOIN đa tenant

Bảng khách có (A, 15) và (B, 15). Đơn thuộc tenant A, mã khách 15. Cần JOIN trên những cột nào?

<details>
<summary>Đáp án gợi ý</summary>

Cần đủ khóa ghép:

~~~sql
ON d.tenant_id = k.tenant_id
AND d.ma_khach_hang = k.ma_khach_hang
~~~

Nếu chỉ JOIN ma_khach_hang, đơn có thể ghép cả khách của tenant B, gây sai dữ liệu và rủi ro phân tách tenant.

</details>

### Bài 13 — NOT IN với NULL

Điều kiện:

~~~sql
WHERE d.ma_khach_hang NOT IN (1, 2, NULL)
~~~

có chắc chắn trả đơn 105 với mã khách 999 không?

<details>
<summary>Đáp án gợi ý</summary>

**Không.** Với 999, các so sánh =1, =2 là FALSE còn =NULL là UNKNOWN; NOT IN có kết quả UNKNOWN, WHERE loại dòng. Nên dùng NOT EXISTS hoặc xử lý NULL trong tập con phù hợp.

</details>

### Bài 14 — FULL OUTER JOIN

Với dữ liệu mẫu, FULL OUTER JOIN có bao nhiêu dòng khớp, chỉ trái, chỉ phải và tổng cộng?

<details>
<summary>Đáp án gợi ý</summary>

**4 khớp**, **2 chỉ phía khách** (khách 3, 4), **2 chỉ phía đơn** (đơn 104, 105), tổng **8 dòng**.

</details>

### Bài 15 — Có nên nối NULL với NULL?

Giả sử bảng A có 3 dòng khóa NULL, bảng B có 2 dòng khóa NULL. Nếu dùng điều kiện **a.k IS NOT DISTINCT FROM b.k**, riêng các dòng NULL tạo bao nhiêu cặp và điều gì cần cân nhắc?

<details>
<summary>Đáp án gợi ý</summary>

Tạo **6 cặp (3 × 2)** nếu toán tử được DBMS hỗ trợ và không có điều kiện khác. Cần chắc chắn nghiệp vụ thực sự muốn coi mọi NULL thuộc cùng một nhóm khớp; điều này thường không phù hợp với khóa ngoại thiếu giá trị.

</details>

### Bài 16 — Chỉ khách có đơn, không nhân khách theo số đơn

Yêu cầu “danh sách những khách có ít nhất một đơn”, mỗi khách một dòng. Chọn INNER JOIN rồi DISTINCT hay EXISTS?

<details>
<summary>Đáp án gợi ý</summary>

Với bảng khách có khóa chính hợp lệ, **EXISTS** thể hiện ý định trực tiếp và không nhân dòng:

~~~sql
SELECT k.ma_khach_hang, k.ten_khach_hang
FROM khach_hang k
WHERE EXISTS (
    SELECT 1
    FROM don_hang d
    WHERE d.ma_khach_hang = k.ma_khach_hang
);
~~~

Kết quả: khách 1 và 2.

</details>

### Bài 17 — FOREIGN KEY có cho NULL không?

Nếu cột don_hang.ma_khach_hang có FOREIGN KEY đến khach_hang(ma_khach_hang) nhưng **không có NOT NULL**, liệu mã khách NULL có bị từ chối ở khóa ngoại một cột trong ngữ nghĩa phổ biến không?

<details>
<summary>Đáp án gợi ý</summary>

Thông thường **không**. FOREIGN KEY một cột cho phép NULL khi cột được phép NULL, còn giá trị không NULL phải tham chiếu đúng khóa cha. Muốn mọi đơn bắt buộc có khách, thêm NOT NULL (và FOREIGN KEY).

</details>

### Bài 18 — Bộ test chống nhân dòng

Một đơn có **3 chi tiết** và **2 dòng thanh toán**. Nếu JOIN cả hai bảng con theo ma_don_hang mà không tổng hợp trước, có thể tạo bao nhiêu dòng cho đơn đó? Cách sửa là gì?

<details>
<summary>Đáp án gợi ý</summary>

Có thể tạo **6 dòng** cho đơn. Tổng hợp bảng chi tiết thành một dòng/đơn và bảng thanh toán thành một dòng/đơn trước, sau đó JOIN hai tập kết quả vào bảng đơn. Việc tổng hợp phải phù hợp quy tắc nghiệp vụ của từng bảng.

</details>

### Bài 19 — Xác định lý do không khớp

Viết CASE phân loại mỗi đơn thành **THIEU_KHOA**, **THAM_CHIEU_MO_COI**, **HOP_LE**.

<details>
<summary>Đáp án gợi ý</summary>

~~~sql
SELECT
    d.ma_don_hang,
    CASE
        WHEN d.ma_khach_hang IS NULL THEN 'THIEU_KHOA'
        WHEN k.ma_khach_hang IS NULL THEN 'THAM_CHIEU_MO_COI'
        ELSE 'HOP_LE'
    END AS tinh_trang
FROM don_hang d
LEFT JOIN khach_hang k
    ON k.ma_khach_hang = d.ma_khach_hang;
~~~

Kết quả có **104 = THIEU_KHOA**, **105 = THAM_CHIEU_MO_COI**, các đơn còn lại **HOP_LE** khi khóa khách là duy nhất.

</details>

### Bài 20 — Debug kết quả JOIN tăng gấp đôi

Sau một lần nhập dữ liệu, truy vấn số đơn theo khách trả số tiền của khách Bình gấp đôi. Chưa có bằng chứng dữ liệu đơn bị thêm mới. Hãy nêu ba nơi nên kiểm tra đầu tiên.

<details>
<summary>Đáp án gợi ý</summary>

Có thể kiểm tra:

1. **Khóa cha có bị trùng không?** Dùng GROUP BY ma_khach_hang HAVING COUNT(*) > 1 trên bảng khách nguồn.
2. **Quan hệ JOIN có thêm bảng một–nhiều không?** Ví dụ chi tiết đơn hoặc thanh toán khiến dòng đơn bị nhân.
3. **Điều kiện ON có thiếu cột khóa ghép không?** Ví dụ thiếu tenant_id hoặc loại/mã nguồn.

Cũng nên so sánh số dòng đơn trước JOIN với số dòng sau JOIN ở từng mã đơn, thay vì dùng DISTINCT để che chênh lệch.

</details>

## 32. Tình huống tổng hợp: đối soát đơn hàng và khách hàng

Giả sử một nhóm dữ liệu cần báo cáo:

> “Với mỗi khách hàng trong danh sách chính thức, hiển thị tên khách, số đơn PAID và tổng tiền PAID; giữ cả khách không có đơn PAID. Đồng thời phải có báo cáo độc lập cho đơn chưa gán khách và đơn tham chiếu khách không tồn tại.”

Nên tách **hai mục đích**:

1. **Báo cáo nghiệp vụ theo khách:** chỉ dùng các đơn ghép đúng khách, bảo đảm mỗi khách một dòng.
2. **Báo cáo chất lượng dữ liệu:** giữ mọi đơn để phát hiện lỗi hoặc thiếu tham chiếu.

### 32.1. Báo cáo theo khách

~~~sql
SELECT
    k.ma_khach_hang,
    k.ten_khach_hang,
    COUNT(d.ma_don_hang) AS so_don_paid,
    COALESCE(SUM(d.tong_tien), 0) AS tong_tien_paid
FROM khach_hang k
LEFT JOIN don_hang d
    ON d.ma_khach_hang = k.ma_khach_hang
   AND d.trang_thai = 'PAID'
GROUP BY
    k.ma_khach_hang,
    k.ten_khach_hang
ORDER BY k.ma_khach_hang;
~~~

Kết quả với dữ liệu mẫu:

| Khách | Số đơn PAID | Tổng tiền PAID |
|---|---:|---:|
| An (1) | 1 | 200000 |
| Bình (2) | 2 | 300000 |
| Chi (3) | 0 | 0 |
| Dũng (4) | 0 | 0 |

**Giải thích kết quả Bình:** có hai đơn PAID, 103 tiền 300000 và 106 tiền NULL. COUNT(d.ma_don_hang) = 2, còn SUM(tong_tien) bỏ qua NULL nên = 300000. Đây là **tổng tiền đã biết**, không chứng minh tổng tiền hoàn chỉnh của mọi đơn.

Nếu cần biết có bao nhiêu đơn PAID chưa có tổng tiền:

~~~sql
SELECT
    k.ma_khach_hang,
    COUNT(d.ma_don_hang) AS so_don_paid,
    COUNT(d.tong_tien) AS so_don_paid_co_tien,
    COUNT(d.ma_don_hang) - COUNT(d.tong_tien)
        AS so_don_paid_thieu_tien
FROM khach_hang k
LEFT JOIN don_hang d
    ON d.ma_khach_hang = k.ma_khach_hang
   AND d.trang_thai = 'PAID'
GROUP BY k.ma_khach_hang;
~~~

Với Bình: **2 đơn PAID**, **1 đơn PAID có tiền**, **1 đơn PAID thiếu tiền**.

Không nên tự xem **tổng tiền của khách Bình bằng 300000** là một con số đầy đủ khi một đơn chưa có giá trị.

### 32.2. Báo cáo kiểm tra khóa tham chiếu

~~~sql
SELECT
    d.ma_don_hang,
    d.ma_khach_hang,
    CASE
        WHEN d.ma_khach_hang IS NULL THEN 'THIEU_KHOA'
        WHEN NOT EXISTS (
            SELECT 1
            FROM khach_hang k
            WHERE k.ma_khach_hang = d.ma_khach_hang
        ) THEN 'MO_COI'
        ELSE 'HOP_LE'
    END AS tinh_trang
FROM don_hang d
ORDER BY d.ma_don_hang;
~~~

Truy vấn này không cần JOIN ra dữ liệu khách, vì chỉ kiểm tra **tồn tại hay không tồn tại**. Nó giữ đúng một dòng cho mỗi đơn, ngay cả khi nguồn khách (trong bài toán khác) có khóa trùng.

### 32.3. Vì sao không dùng một JOIN lớn làm tất cả?

Nếu cố đưa cả đơn hợp lệ, đơn không có khách và báo cáo mỗi khách một dòng vào cùng một SELECT GROUP BY mà không xác định grain, dễ gặp:

- Đơn 104/105 biến mất khi nhóm theo khách từ bảng chính thức.
- Đơn không có khách bị gộp vào một nhóm NULL không phân biệt lý do.
- Khách không có đơn bị mất khi dùng INNER JOIN.
- COUNT(*) đếm dòng đệm và cho 1 đơn giả.
- Thêm bảng chi tiết gây nhân tổng tiền.
- Chỉ số tiền thiếu bị che bởi COALESCE(SUM(...), 0).

**Tách báo cáo nghiệp vụ khỏi báo cáo kiểm tra chất lượng** thường giúp câu SQL rõ hơn, dễ kiểm thử và tránh nhầm một tập kết quả phục vụ hai ý nghĩa khác nhau.

## 33. Quy trình xử lý sự cố JOIN trong dự án thực tế

Khi thấy số dòng hoặc số tiền sai, có thể thực hiện theo trình tự:

### Bước 1 — Xác định mức chi tiết mong muốn

Cần **mỗi khách một dòng**, **mỗi đơn một dòng**, hay **mỗi chi tiết sản phẩm một dòng**? Một kết quả có nhiều dòng/khách có thể hoàn toàn đúng nếu đang lấy thông tin mỗi đơn.

### Bước 2 — Kiểm tra dòng nguồn tồn tại

~~~sql
SELECT COUNT(*) FROM khach_hang;
SELECT COUNT(*) FROM don_hang;
~~~

Đếm từng bảng riêng. Nếu nghi vấn cụ thể, lọc theo khóa và xem giá trị gốc:

~~~sql
SELECT *
FROM don_hang
WHERE ma_don_hang = 105;
~~~

### Bước 3 — Kiểm tra NULL

~~~sql
SELECT COUNT(*) AS so_don_thieu_ma_khach
FROM don_hang
WHERE ma_khach_hang IS NULL;
~~~

### Bước 4 — Kiểm tra orphan

~~~sql
SELECT COUNT(*) AS so_don_mo_coi
FROM don_hang d
WHERE d.ma_khach_hang IS NOT NULL
  AND NOT EXISTS (
      SELECT 1
      FROM khach_hang k
      WHERE k.ma_khach_hang = d.ma_khach_hang
  );
~~~

### Bước 5 — Kiểm tra duplicate ở nguồn phải duy nhất

~~~sql
SELECT ma_khach_hang, COUNT(*) AS so_dong
FROM khach_hang_nhap
WHERE ma_khach_hang IS NOT NULL
GROUP BY ma_khach_hang
HAVING COUNT(*) > 1;
~~~

Nếu đang nối bảng chính đã có PRIMARY KEY được thực thi, lỗi trùng khóa có thể nằm ở một **bảng khác trong chuỗi JOIN** hoặc ở khóa ghép thiếu cột.

### Bước 6 — Kiểm tra số dòng sau từng JOIN

Với truy vấn có ba bảng, tách thành các phép kiểm tra trung gian. Quan sát khi thêm JOIN chi tiết đơn thì số dòng tăng như thế nào, có đúng số dòng chi tiết hay tăng bất thường do trùng khóa.

### Bước 7 — Đánh giá ON và WHERE

Nếu dùng LEFT JOIN, kiểm tra điều kiện phía phải có bị đặt ở WHERE khiến mất dòng trái hay không.

### Bước 8 — Xác minh khóa ghép và loại dữ liệu

Kiểm tra tenant_id, nguồn hệ thống, kiểu số/chuỗi, collation, khoảng trắng và quy tắc chuẩn hóa trước khi sửa biểu thức JOIN.

### Bước 9 — Chọn hướng xử lý dữ liệu

Có thể cần bổ sung bản ghi cha, sửa mã mapping, nạp dữ liệu lại, bổ sung constraint hoặc đặt quy trình cách ly dữ liệu lỗi. Tránh cập nhật/xóa tự động những dòng chưa rõ nguyên nhân.

### Bước 10 — Kiểm tra kết quả mong đợi bằng cặp khóa

Đối chiếu không chỉ tổng số dòng mà cả những cặp **(ma_khach_hang, ma_don_hang)** và những dòng không khớp. Thêm các trường hợp NULL, duplicate và orphan vào bộ kiểm thử hồi quy.

## 34. Ghi nhớ cuối bài

1. **JOIN tạo cặp dòng theo điều kiện ON.** Với phép so sánh bằng thông thường, điều kiện chỉ khớp khi TRUE; NULL so sánh bằng cho UNKNOWN nên không tạo cặp khớp.
2. **INNER JOIN** chỉ giữ cặp khớp; **LEFT/RIGHT/FULL OUTER JOIN** còn giữ dòng không khớp ở những phía tương ứng bằng cách đệm NULL.
3. **NULL có sẵn trong bản ghi** khác với **NULL do OUTER JOIN tạo ra**. Muốn phát hiện không khớp, kiểm tra một khóa NOT NULL ở phía có thể bị thiếu, không chọn cột tùy ý có thể NULL.
4. **ON và WHERE khác nhau**, đặc biệt với OUTER JOIN. Đưa điều kiện cột phải xuống WHERE có thể loại dòng trái bạn muốn giữ.
5. **Khóa ngoại lặp ở bảng con** là bình thường trong quan hệ một–nhiều; **khóa cha bị lặp** thường vi phạm thiết kế nếu nó được yêu cầu duy nhất.
6. Với một khóa không NULL xuất hiện **L** lần ở bảng trái và **R** lần ở bảng phải, JOIN bằng khóa có thể sinh **L × R cặp**.
7. **COUNT(*)** sau LEFT JOIN có thể đếm dòng đệm; **COUNT(khóa NOT NULL phía phải)** phù hợp hơn để đếm bản ghi phải khớp.
8. **SUM sau JOIN một–nhiều** có thể nhân số tiền; **SUM(DISTINCT giá trị)** không chữa đúng mọi trường hợp. Hãy tổng hợp đúng grain trước khi JOIN.
9. **NULL ở khóa con** và **khóa con không tồn tại ở bảng cha** là hai tình trạng khác nhau. Phân loại riêng để điều tra và sửa dữ liệu.
10. **NOT EXISTS** thường thích hợp để kiểm tra không có bản ghi liên quan; **NOT IN** có thể gây kết quả bất ngờ khi xuất hiện NULL.
11. **PRIMARY KEY, UNIQUE, FOREIGN KEY và NOT NULL** có vai trò bổ sung nhau trong bảo vệ tính duy nhất, sự tồn tại tham chiếu và sự bắt buộc nhập khóa.
12. Với **khóa ghép**, phải nối trên **toàn bộ các cột định danh**. Thiếu tenant_id hoặc một phần khóa có thể tạo cặp giả và rủi ro bảo mật dữ liệu.
13. Khi gặp lỗi JOIN, **xác định yêu cầu, kiểm tra từng nguồn, NULL, duplicate, orphan, ON/WHERE và số dòng sau mỗi JOIN** trước khi thử DISTINCT hoặc thay đổi kiểu JOIN.
14. Bộ test JOIN nên có **khớp, không khớp, khóa NULL, khóa lặp, tham chiếu mồ côi, dữ liệu một–nhiều và nhiều–nhiều**; câu SQL chạy được chưa đủ chứng minh kết quả đúng.

### Tài liệu tham khảo để đối chiếu theo DBMS

Khi triển khai trong hệ thống cụ thể, tra cứu tài liệu chính thức theo đúng phiên bản và những mục như **JOIN syntax**, **NULL and three-valued logic**, **PRIMARY KEY**, **FOREIGN KEY**, **UNIQUE**, **EXISTS**, **aggregate functions**, **query execution plans**:

- **PostgreSQL Documentation:** *Table Expressions / Joined Tables*, *Comparison Functions and Operators*, *Constraints*, *Subquery Expressions*.
- **MySQL Reference Manual:** *JOIN Clause*, *Working with NULL Values*, *Foreign Key Constraints*, *Comparison Functions and Operators*.
- **Microsoft Learn — Transact-SQL:** *FROM and JOIN*, *NULL and UNKNOWN*, *Primary and Foreign Key Constraints*, *EXISTS*.
- **Oracle Database SQL Language Reference:** *Joins*, *Nulls*, *Conditions*, *Integrity Constraints*.
- **SQLite Documentation:** *SELECT*, *Foreign Key Support*, *NULL Handling*, *Query Planner*.

**Thông điệp xuyên suốt:** khi JOIN cho kết quả thiếu hoặc nhiều dòng ngoài dự kiến, đừng chỉ hỏi “viết INNER hay LEFT?”. Hãy hỏi **“điều kiện nào định nghĩa một quan hệ hợp lệ, mỗi khóa xuất hiện bao nhiêu lần, và dữ liệu NULL hoặc không tìm thấy bản ghi cha phải được hiểu như thế nào?”**. Trả lời được ba câu hỏi ấy sẽ giúp tránh nhiều lỗi SQL nguy hiểm nhưng khó phát hiện bằng dữ liệu thử thông thường.
