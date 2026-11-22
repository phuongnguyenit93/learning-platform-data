# Lọc hàng bằng WHERE trong SQL

> **Chủ đề:** Database SQL → Truy vấn cơ bản  
> **Nội dung chính:** Mệnh đề **WHERE** chọn những hàng (dòng, bản ghi) thỏa điều kiện trong một truy vấn SQL. Bài học tập trung vào cú pháp, cách kết hợp điều kiện và cách xử lý **NULL**, đồng thời giải thích những khác biệt thường gây lỗi khi truy vấn thực tế.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

- Viết câu lệnh **SELECT ... FROM ... WHERE ...** để tìm đúng các hàng cần thiết.
- Sử dụng các toán tử so sánh **=**, **<>**, **>**, **>=**, **<**, **<=**.
- Kết hợp điều kiện bằng **AND**, **OR**, **NOT** và dấu ngoặc để tránh nhầm thứ tự ưu tiên.
- Lọc theo tập giá trị bằng **IN**, theo khoảng bằng **BETWEEN**, theo mẫu chuỗi bằng **LIKE**, và theo dữ liệu thiếu bằng **IS NULL**.
- Hiểu vì sao điều kiện cho kết quả **UNKNOWN** khi so sánh với **NULL**, và tại sao WHERE chỉ giữ hàng có điều kiện **TRUE**.
- Phân biệt WHERE với **HAVING**, điều kiện **ON** trong JOIN và **ORDER BY**.
- Viết bộ lọc có tham số trong ứng dụng, tránh nối giá trị người dùng trực tiếp vào câu SQL.
- Nhận biết các biểu thức WHERE có thể làm truy vấn trả sai hàng hoặc sử dụng chỉ mục kém hiệu quả.

## 2. WHERE là gì?

**WHERE** là mệnh đề dùng để **lọc hàng** trong SQL: chỉ các hàng mà biểu thức điều kiện được xác định là đúng (**TRUE**) mới đi tiếp vào kết quả của truy vấn.

Cấu trúc cơ bản:

~~~sql
SELECT cot_1, cot_2, ...
FROM ten_bang
WHERE dieu_kien;
~~~

Ví dụ, chọn các sản phẩm có giá bán trên 100.000:

~~~sql
SELECT ma_san_pham, ten_san_pham, gia_ban
FROM san_pham
WHERE gia_ban > 100000;
~~~

Trong câu lệnh này:

- **SELECT** quy định những **cột** nào xuất hiện trong kết quả.
- **FROM** xác định bảng hoặc nguồn dữ liệu để đọc.
- **WHERE** xác định **hàng nào** được giữ lại.
- Dấu **;** kết thúc câu lệnh trong nhiều công cụ SQL.

Điểm cần phân biệt: **SELECT tên cột** là chọn thông tin để hiển thị; **WHERE** là chọn những hàng thỏa điều kiện. Một câu lệnh có thể chọn ba cột nhưng trả về hàng nghìn dòng, hoặc chọn mười cột nhưng không có dòng nào.

Nếu bỏ WHERE, truy vấn thông thường đọc tất cả hàng từ nguồn đã chọn, trừ khi có mệnh đề khác ảnh hưởng đến số dòng kết quả.

~~~sql
-- Lấy cột mã và tên của tất cả sản phẩm.
SELECT ma_san_pham, ten_san_pham
FROM san_pham;
~~~

~~~sql
-- Chỉ lấy sản phẩm còn đang bán.
SELECT ma_san_pham, ten_san_pham
FROM san_pham
WHERE dang_ban = 1;
~~~

**WHERE không thay đổi dữ liệu đang lưu** khi dùng trong SELECT. Nó chỉ quyết định hàng nào thuộc kết quả. Tuy nhiên, WHERE trong UPDATE và DELETE sẽ quyết định các hàng bị thay đổi hoặc xóa, nên phải kiểm tra rất cẩn thận.

## 3. Bộ dữ liệu minh họa

Giả sử hệ thống bán hàng có bảng **san_pham** sau. Cột **gia_ban** có đơn vị đồng Việt Nam, **so_luong_ton** là số đơn vị còn trong kho, **dang_ban** dùng quy ước **1 = đang bán** và **0 = ngừng bán**.

| ma_san_pham | ten_san_pham | danh_muc | gia_ban | so_luong_ton | dang_ban | ngay_tao |
|---:|---|---|---:|---:|---:|---|
| 101 | Sổ tay | Văn phòng phẩm | 45000 | 100 | 1 | 2026-01-10 |
| 102 | Bút gel | Văn phòng phẩm | 18000 | 0 | 1 | 2026-01-12 |
| 103 | Tai nghe | Điện tử | 350000 | 12 | 1 | 2026-02-01 |
| 104 | Bàn phím | Điện tử | 750000 | 5 | 0 | 2026-02-15 |
| 105 | Bình nước | Gia dụng | 120000 | 20 | 1 | 2026-03-01 |
| 106 | Đèn bàn | Gia dụng | NULL | 8 | 1 | 2026-03-20 |
| 107 | Chuột không dây | Điện tử | 250000 | 4 | 1 | 2026-04-05 |
| 108 | Bút bi | Văn phòng phẩm | 12000 | 200 | 1 | 2026-04-12 |

Các truy vấn trong bài giả định bảng tồn tại với các cột, kiểu dữ liệu và hàng như trên. **NULL** ở giá bán sản phẩm 106 có nghĩa giá chưa được xác định trong dữ liệu mẫu, không có nghĩa giá bằng 0. Cột ngay_tao được hiểu là kiểu ngày (**DATE**), không phải chuỗi ký tự. Khi chạy truy vấn lọc theo ngày trong DBMS thật, nên truyền tham số ngày đúng kiểu qua driver.

Các mã sản phẩm được giả định là duy nhất. Vì thế, khi cần phân biệt các hàng hoặc sắp xếp ổn định, có thể dùng **ma_san_pham**.

## 4. Lọc với các toán tử so sánh

### 4.1. Danh sách toán tử thường gặp

| Toán tử SQL | Ý nghĩa | Ví dụ |
|---|---|---|
| **=** | Bằng | gia_ban = 120000 |
| **<>** | Khác | danh_muc <> 'Điện tử' |
| **>** | Lớn hơn | gia_ban > 100000 |
| **>=** | Lớn hơn hoặc bằng | gia_ban >= 100000 |
| **<** | Nhỏ hơn | gia_ban < 50000 |
| **<=** | Nhỏ hơn hoặc bằng | gia_ban <= 50000 |

Ví dụ lấy sản phẩm có giá bán **từ 100.000 trở lên**:

~~~sql
SELECT ma_san_pham, ten_san_pham, gia_ban
FROM san_pham
WHERE gia_ban >= 100000
ORDER BY ma_san_pham;
~~~

Theo dữ liệu mẫu, kết quả có mã **103, 104, 105, 107**. Sản phẩm 106 có giá NULL nên **không** được giữ lại; điều này được giải thích ở phần NULL.

Lọc sản phẩm thuộc danh mục Điện tử:

~~~sql
SELECT ma_san_pham, ten_san_pham
FROM san_pham
WHERE danh_muc = 'Điện tử'
ORDER BY ma_san_pham;
~~~

Kết quả có mã **103, 104, 107**.

Lọc sản phẩm có tồn kho bằng 0:

~~~sql
SELECT ma_san_pham, ten_san_pham, so_luong_ton
FROM san_pham
WHERE so_luong_ton = 0;
~~~

Kết quả chỉ có **Bút gel (102)**.

### 4.2. Dấu bằng và dấu gán

Trong SQL, điều kiện so sánh bằng được viết bằng **=**, không phải **==** theo thói quen từ nhiều ngôn ngữ lập trình. Một số DBMS có thể chấp nhận toán tử mở rộng, nhưng **=** là cách viết chung dễ chuyển hệ hơn.

~~~sql
-- Cú pháp nên dùng:
WHERE dang_ban = 1
~~~

~~~sql
-- Không dùng theo thói quen từ Java/C:
WHERE dang_ban == 1
~~~

Trong các ngôn ngữ như Java, **=** thường là toán tử gán. Trong điều kiện SQL, **=** thể hiện phép so sánh bằng. SQL cũng có các ngữ cảnh gán giá trị riêng, chẳng hạn **SET gia_ban = 120000** trong UPDATE.

### 4.3. Dữ liệu chuỗi và dấu nháy

Giá trị chuỗi trong SQL thường đặt trong **nháy đơn**:

~~~sql
SELECT ma_san_pham, ten_san_pham
FROM san_pham
WHERE danh_muc = 'Gia dụng';
~~~

Dùng nháy kép cho giá trị chuỗi có thể gây lỗi hoặc được hiểu là định danh (tên cột/bảng) ở nhiều DBMS. Dấu nháy kép có ý nghĩa riêng trong cú pháp định danh SQL.

Giá trị chuỗi cũng chịu quy tắc so sánh và **collation** của cơ sở dữ liệu. Ví dụ, việc **'búT gel'** có được xem bằng **'Bút gel'** hay không có thể phụ thuộc vào cấu hình phân biệt hoa/thường và dấu. Không nên khẳng định phép bằng trên văn bản cho kết quả giống nhau ở mọi hệ quản trị.

### 4.4. Lọc số thập phân

Nếu **gia_ban** là **DECIMAL/NUMERIC**, biểu thức như sau hợp lệ về ý nghĩa:

~~~sql
SELECT ma_san_pham, ten_san_pham, gia_ban
FROM san_pham
WHERE gia_ban >= 120000.00;
~~~

Đối với giá tiền, nên dùng kiểu số thập phân chính xác và chuẩn hóa cách truyền tham số. Không nên lưu giá bằng chuỗi rồi kỳ vọng so sánh **'120000' > '90000'** cho ra kết quả số học, vì so sánh chuỗi và so sánh số có ngữ nghĩa khác nhau.

## 5. Kết hợp nhiều điều kiện bằng AND

**AND** yêu cầu **tất cả điều kiện thành phần** đều đúng thì cả biểu thức mới TRUE.

Yêu cầu: “Tìm sản phẩm đang bán, còn hàng và giá từ 100.000 trở lên”.

~~~sql
SELECT
    ma_san_pham,
    ten_san_pham,
    gia_ban,
    so_luong_ton
FROM san_pham
WHERE dang_ban = 1
  AND so_luong_ton > 0
  AND gia_ban >= 100000
ORDER BY ma_san_pham;
~~~

Kết quả:

| ma_san_pham | ten_san_pham | gia_ban | so_luong_ton |
|---:|---|---:|---:|
| 103 | Tai nghe | 350000 | 12 |
| 105 | Bình nước | 120000 | 20 |
| 107 | Chuột không dây | 250000 | 4 |

Vì sao các sản phẩm khác bị loại?

- **101**: giá dưới 100.000.
- **102**: đã hết hàng và giá dưới 100.000.
- **104**: ngừng bán, dù giá và tồn kho thỏa điều kiện.
- **106**: giá NULL, không thể xác nhận giá từ 100.000 trở lên.
- **108**: giá dưới 100.000.

**AND** nên dùng khi nghiệp vụ yêu cầu đồng thời nhiều tiêu chí. Mỗi điều kiện có thể ở một dòng để dễ đọc và sửa.

## 6. Kết hợp điều kiện bằng OR

**OR** yêu cầu **ít nhất một điều kiện thành phần** đúng.

Ví dụ, chọn sản phẩm thuộc danh mục **Điện tử** hoặc **Gia dụng**:

~~~sql
SELECT ma_san_pham, ten_san_pham, danh_muc
FROM san_pham
WHERE danh_muc = 'Điện tử'
   OR danh_muc = 'Gia dụng'
ORDER BY ma_san_pham;
~~~

Kết quả có mã **103, 104, 105, 106, 107**.

Một sản phẩm thỏa đồng thời hai nhánh OR vẫn chỉ xuất hiện một lần từ một hàng nguồn trong truy vấn SELECT đơn giản. OR không giống UNION ALL và không tự nhân đôi dòng.

### 6.1. AND và OR khác nhau thế nào?

| Biểu thức | Ý nghĩa |
|---|---|
| A **AND** B | A đúng **và** B đúng |
| A **OR** B | A đúng **hoặc** B đúng, có thể cả hai đúng |
| **NOT** A | Phủ định A |
| (A **OR** B) **AND** C | Phải thỏa C và ít nhất một trong A/B |

Chọn AND hay OR dựa trên câu hỏi nghiệp vụ, không dựa trên việc cách nào “trả nhiều dòng hơn”.

## 7. Thứ tự ưu tiên: NOT, AND, OR và dấu ngoặc

Khi viết nhiều toán tử logic, SQL có thứ tự ưu tiên thông dụng:

1. **NOT**.
2. **AND**.
3. **OR**.

So sánh và các toán tử đặc thù được áp dụng theo quy tắc ngữ pháp của biểu thức; khi kết hợp các điều kiện độc lập, thứ tự trên là điều quan trọng cần ghi nhớ.

Xét:

~~~sql
SELECT ma_san_pham, ten_san_pham
FROM san_pham
WHERE danh_muc = 'Điện tử'
   OR danh_muc = 'Gia dụng'
  AND dang_ban = 1;
~~~

Câu lệnh trên tương đương cách nhóm:

~~~sql
WHERE danh_muc = 'Điện tử'
   OR (danh_muc = 'Gia dụng' AND dang_ban = 1)
~~~

Nó **vẫn chọn Bàn phím (104)** vì sản phẩm này thuộc Điện tử, dù đã ngừng bán.

Nếu ý định thực sự là “đang bán **và** thuộc Điện tử hoặc Gia dụng”, phải dùng dấu ngoặc:

~~~sql
SELECT ma_san_pham, ten_san_pham
FROM san_pham
WHERE (danh_muc = 'Điện tử' OR danh_muc = 'Gia dụng')
  AND dang_ban = 1
ORDER BY ma_san_pham;
~~~

Kết quả có mã **103, 105, 106, 107**, loại 104 do không còn bán.

**Quy tắc dễ áp dụng:** khi phối hợp AND và OR, hãy đặt dấu ngoặc để thể hiện đúng nhóm điều kiện trong yêu cầu nghiệp vụ. Không nên dựa vào việc người đọc phải nhớ ưu tiên toán tử để hiểu truy vấn.

## 8. Phủ định bằng NOT

**NOT** đảo kết quả logic của điều kiện: TRUE thành FALSE, FALSE thành TRUE; riêng UNKNOWN vẫn là UNKNOWN.

Ví dụ, tìm sản phẩm **không** thuộc danh mục Điện tử:

~~~sql
SELECT ma_san_pham, ten_san_pham, danh_muc
FROM san_pham
WHERE NOT (danh_muc = 'Điện tử')
ORDER BY ma_san_pham;
~~~

Với dữ liệu mẫu, kết quả là **101, 102, 105, 106, 108**.

Một cách viết đơn giản hơn:

~~~sql
SELECT ma_san_pham, ten_san_pham, danh_muc
FROM san_pham
WHERE danh_muc <> 'Điện tử'
ORDER BY ma_san_pham;
~~~

Hai biểu thức này cùng ý nghĩa đối với so sánh thông thường. Tuy nhiên, nếu **danh_muc** NULL, cả hai điều kiện đều là UNKNOWN và dòng bị loại. “Không bằng một giá trị” trong SQL **không tự động** đồng nghĩa “bao gồm mọi dòng thiếu giá trị đó”.

### 8.1. Cẩn thận khi phủ định điều kiện có NULL

~~~sql
SELECT ma_san_pham, gia_ban
FROM san_pham
WHERE NOT (gia_ban >= 300000);
~~~

Kết quả có giá xác định dưới 300.000: **101, 102, 105, 107, 108**. Sản phẩm **106** không xuất hiện vì **NULL >= 300000** là UNKNOWN và **NOT UNKNOWN** vẫn UNKNOWN.

Nếu nghiệp vụ muốn “sản phẩm có giá dưới 300.000 **hoặc** giá chưa được xác định”:

~~~sql
SELECT ma_san_pham, gia_ban
FROM san_pham
WHERE gia_ban < 300000
   OR gia_ban IS NULL
ORDER BY ma_san_pham;
~~~

Khi này có thêm sản phẩm **106**.

## 9. Lọc theo danh sách giá trị bằng IN

Khi cần so sánh một cột với nhiều giá trị, **IN** thường gọn và dễ đọc hơn một chuỗi OR:

~~~sql
SELECT ma_san_pham, ten_san_pham, danh_muc
FROM san_pham
WHERE danh_muc IN ('Điện tử', 'Gia dụng')
ORDER BY ma_san_pham;
~~~

Với dữ liệu mẫu, kết quả có mã **103, 104, 105, 106, 107**.

Biểu thức trên có ý nghĩa tương tự:

~~~sql
WHERE danh_muc = 'Điện tử'
   OR danh_muc = 'Gia dụng'
~~~

Để tìm sản phẩm **không** thuộc hai danh mục trên:

~~~sql
SELECT ma_san_pham, ten_san_pham, danh_muc
FROM san_pham
WHERE danh_muc NOT IN ('Điện tử', 'Gia dụng')
ORDER BY ma_san_pham;
~~~

Kết quả: **101, 102, 108**, đều thuộc Văn phòng phẩm.

### 9.1. Bẫy NULL trong NOT IN

Giả sử viết:

~~~sql
-- Minh họa bẫy:
SELECT ma_san_pham, danh_muc
FROM san_pham
WHERE danh_muc NOT IN ('Điện tử', NULL);
~~~

Mỗi dòng có **danh_muc = 'Điện tử'** sẽ làm IN TRUE, nên NOT IN FALSE. Với danh mục khác Điện tử, một phép so sánh với NULL trả UNKNOWN, khiến IN và NOT IN có thể vẫn UNKNOWN. WHERE không giữ UNKNOWN. Trong tình huống dữ liệu hiện tại, truy vấn trên không trả dòng nào.

**NOT IN với truy vấn con** càng cần chú ý:

~~~sql
-- Dễ cho kết quả bất ngờ nếu cột danh_muc trong truy vấn con có NULL.
SELECT s.ma_san_pham
FROM san_pham s
WHERE s.danh_muc NOT IN (
    SELECT m.ten_danh_muc
    FROM danh_muc_bi_chan m
);
~~~

Để tránh bẫy này, cần bảo đảm tập bên trong không có NULL, ví dụ lọc **WHERE m.ten_danh_muc IS NOT NULL** nếu đúng yêu cầu nghiệp vụ. Trong nhiều bài toán “không có bản ghi liên quan”, **NOT EXISTS** là lựa chọn dễ diễn đạt và ít gây nhầm hơn.

### 9.2. Danh sách IN rỗng

Không nên tạo SQL như **IN ()** khi ứng dụng nhận một danh sách bộ lọc rỗng, vì cú pháp này không được chấp nhận ở nhiều DBMS. Tầng ứng dụng cần quyết định rõ: danh sách rỗng có nghĩa **không chọn sản phẩm nào** hay **bỏ qua tiêu chí lọc**. Hai cách hiểu dẫn tới hai truy vấn khác nhau, nên không thể tự chọn một cách tùy tiện.

## 10. Lọc theo khoảng bằng BETWEEN

**BETWEEN** kiểm tra một giá trị nằm trong khoảng **bao gồm cả hai đầu mút**:

~~~sql
SELECT ma_san_pham, ten_san_pham, gia_ban
FROM san_pham
WHERE gia_ban BETWEEN 50000 AND 300000
ORDER BY ma_san_pham;
~~~

Kết quả có mã **105 (120.000)** và **107 (250.000)**.

Điều kiện này tương đương với hai so sánh:

~~~sql
WHERE gia_ban >= 50000
  AND gia_ban <= 300000
~~~

Lưu ý:

- **BETWEEN** có tính **bao gồm** hai ranh giới, nên giá chính xác bằng 50.000 hoặc 300.000 vẫn được chọn.
- Nếu giá là NULL, điều kiện **gia_ban BETWEEN ...** không TRUE, nên WHERE loại dòng.
- **NOT BETWEEN** cũng không tự bao gồm giá NULL.
- Với dữ liệu chữ, BETWEEN áp dụng quy tắc so sánh chuỗi/collation của DBMS, không giống sắp xếp số.
- Khoảng cần có thứ tự ý nghĩa rõ ràng; **BETWEEN 300000 AND 50000** không tự đổi hai đầu cho người dùng.

### 10.1. Với thời gian, ưu tiên khoảng nửa mở

Nếu **ngay_tao** là kiểu DATE, truy vấn từ ngày 01/03/2026 đến hết 31/03/2026 có thể dùng hai tham số ngày:

~~~sql
SELECT ma_san_pham, ten_san_pham, ngay_tao
FROM san_pham
WHERE ngay_tao >= ?
  AND ngay_tao < ?
ORDER BY ngay_tao, ma_san_pham;
~~~

Trong ứng dụng JDBC, bind tham số thứ nhất là **2026-03-01** và tham số thứ hai là **2026-04-01**, đều có kiểu ngày phù hợp. Khi đó, khoảng gồm toàn bộ tháng 3 và không lấy ngày 01/04.

Cách **>= ngày đầu** kết hợp **< ngày kế tiếp** còn hữu ích khi cột có kiểu **TIMESTAMP**, vì không phải đoán thời điểm cuối ngày có chính xác bao nhiêu chữ số phần giây. Nếu dữ liệu lưu theo múi giờ hoặc là một thời điểm tuyệt đối, phải xác định múi giờ và quy tắc chuyển đổi tương ứng.

Dấu **?** là ký hiệu tham số trong JDBC, không phải câu SQL độc lập sẽ chạy trong mọi trình quản trị. Ví dụ mã Java ở phần sau sẽ cho thấy cách bind tham số.

## 11. Lọc chuỗi theo mẫu bằng LIKE

**LIKE** so sánh một chuỗi với một mẫu, thường dùng với hai ký tự đại diện:

| Ký tự | Ý nghĩa |
|---|---|
| **%** | Không hoặc nhiều ký tự bất kỳ |
| **_** | Đúng một ký tự theo quy tắc ký tự của DBMS |

Ví dụ, tìm sản phẩm có tên bắt đầu bằng “Bút”:

~~~sql
SELECT ma_san_pham, ten_san_pham
FROM san_pham
WHERE ten_san_pham LIKE 'Bút%'
ORDER BY ma_san_pham;
~~~

Kết quả: **102 (Bút gel)** và **108 (Bút bi)**.

Tìm sản phẩm có chữ “bàn” ở bất kỳ vị trí nào:

~~~sql
SELECT ma_san_pham, ten_san_pham
FROM san_pham
WHERE ten_san_pham LIKE '%bàn%';
~~~

Kết quả có thể phụ thuộc **collation** và quy tắc phân biệt hoa/thường. Theo kiểu so khớp không phân biệt chữ hoa/thường, ví dụ sẽ tìm **Bàn phím (104)** và **Đèn bàn (106)**. Trong môi trường phân biệt chữ hoa/thường, **'Bàn phím'** có chữ B viết hoa nên mẫu chữ thường **'%bàn%'** có thể chỉ tìm được Đèn bàn. Nếu nghiệp vụ yêu cầu kết quả giống nhau trên nhiều hệ, cần thống nhất collation hoặc dùng cơ chế chuẩn hóa/so khớp phù hợp.

Một mẫu cố định hai ký tự sau “Bút ”:

~~~sql
SELECT ma_san_pham, ten_san_pham
FROM san_pham
WHERE ten_san_pham LIKE 'Bút __';
~~~

Mẫu này tìm tên có tiền tố **Bút** + dấu cách + **đúng hai ký tự tiếp theo**. Trong tập mẫu, **Bút bi** thỏa điều kiện, còn **Bút gel** có ba ký tự sau dấu cách nên không thỏa. Với Unicode phức tạp hoặc collation đặc thù, khái niệm “ký tự” có thể cần kiểm tra theo DBMS.

### 11.1. Phân biệt LIKE và =

~~~sql
WHERE ten_san_pham = 'Bút%'
~~~

Câu này so sánh với giá trị chuỗi thật **Bút%**, không dùng dấu % như wildcard.

~~~sql
WHERE ten_san_pham LIKE 'Bút%'
~~~

Câu này chọn các tên **bắt đầu bằng Bút**.

### 11.2. Tìm ký tự % hoặc _ thật trong dữ liệu

Trong nhiều DBMS, cú pháp **ESCAPE** cho phép chỉ định ký tự dùng để thoát wildcard. Ví dụ, để tìm tên có dấu phần trăm:

~~~sql
SELECT ma_san_pham, ten_san_pham
FROM san_pham
WHERE ten_san_pham LIKE '%!%%' ESCAPE '!';
~~~

Trong mẫu trên, **!%** có nghĩa là dấu **%** thật, còn hai dấu % ở ngoài là wildcard. Không có sản phẩm nào trong bảng mẫu chứa ký tự %, nên kết quả rỗng.

Khi mẫu LIKE đến từ đầu vào người dùng, cần xử lý ký tự **%**, **_** và ký tự escape theo yêu cầu tìm kiếm: người dùng muốn gõ một từ có wildcard hay muốn tìm chuỗi nguyên văn? Đồng thời luôn truyền mẫu thông qua tham số của driver.

### 11.3. NOT LIKE và NULL

~~~sql
SELECT ma_san_pham, ten_san_pham
FROM san_pham
WHERE ten_san_pham NOT LIKE 'Bút%';
~~~

Truy vấn này chọn các sản phẩm không bắt đầu bằng Bút, **miễn tên không NULL**. Nếu một hàng có **ten_san_pham = NULL**, điều kiện **NOT LIKE** không TRUE và hàng không xuất hiện. Cần thêm **OR ten_san_pham IS NULL** nếu yêu cầu bao gồm tên chưa khai báo.

## 12. NULL và logic ba giá trị trong WHERE

SQL dùng logic ba giá trị:

| Giá trị điều kiện | Ý nghĩa | WHERE có giữ hàng không? |
|---|---|---|
| **TRUE** | Điều kiện đúng | Có |
| **FALSE** | Điều kiện sai | Không |
| **UNKNOWN** | Chưa xác định đúng hay sai | Không |

Một phép so sánh thông thường có toán hạng NULL thường trả UNKNOWN:

~~~sql
-- Với gia_ban = NULL:
gia_ban > 100000      -- UNKNOWN
gia_ban = 0           -- UNKNOWN
gia_ban <> 0          -- UNKNOWN
gia_ban = NULL        -- UNKNOWN
NOT (gia_ban > 0)     -- UNKNOWN
~~~

Vì vậy:

~~~sql
-- Không tìm đúng những sản phẩm thiếu giá:
SELECT ma_san_pham, ten_san_pham
FROM san_pham
WHERE gia_ban = NULL;
~~~

Cách đúng là **IS NULL**:

~~~sql
SELECT ma_san_pham, ten_san_pham
FROM san_pham
WHERE gia_ban IS NULL;
~~~

Kết quả có **Đèn bàn (106)**.

Tìm những sản phẩm **đã xác định giá**:

~~~sql
SELECT ma_san_pham, ten_san_pham
FROM san_pham
WHERE gia_ban IS NOT NULL
ORDER BY ma_san_pham;
~~~

Kết quả có tất cả mã trừ **106**.

### 12.1. Phép AND và OR khi gặp UNKNOWN

Các quy tắc quan trọng:

| Biểu thức | Kết quả |
|---|---|
| **NOT UNKNOWN** | UNKNOWN |
| **TRUE AND UNKNOWN** | UNKNOWN |
| **FALSE AND UNKNOWN** | FALSE |
| **TRUE OR UNKNOWN** | TRUE |
| **FALSE OR UNKNOWN** | UNKNOWN |

Ví dụ với Đèn bàn (106), **gia_ban >= 100000** là UNKNOWN, nhưng **danh_muc = 'Gia dụng'** là TRUE:

~~~sql
SELECT ma_san_pham, ten_san_pham
FROM san_pham
WHERE gia_ban >= 100000
   OR danh_muc = 'Gia dụng';
~~~

Sản phẩm 106 **được chọn**, vì **UNKNOWN OR TRUE = TRUE**.

Nếu thay OR bằng AND, sản phẩm 106 bị loại vì **UNKNOWN AND TRUE = UNKNOWN**.

### 12.2. Đừng tự đổi NULL thành 0 khi chưa có quy tắc nghiệp vụ

~~~sql
SELECT ma_san_pham, gia_ban
FROM san_pham
WHERE COALESCE(gia_ban, 0) < 50000;
~~~

Câu này chọn cả sản phẩm có giá **dưới 50.000** và sản phẩm **không có giá** vì đã dùng 0 thay NULL. Theo dữ liệu mẫu, có mã **101, 102, 106, 108**.

Nếu chỉ muốn sản phẩm có giá thật sự dưới 50.000:

~~~sql
SELECT ma_san_pham, gia_ban
FROM san_pham
WHERE gia_ban < 50000
ORDER BY ma_san_pham;
~~~

Kết quả chỉ có **101, 102, 108**.

COALESCE có ích khi nghiệp vụ quy định rõ cách thay thế giá trị thiếu. Nếu không, việc biến NULL thành giá trị cụ thể có thể làm báo cáo sai ý nghĩa.

## 13. Lọc với EXISTS khi điều kiện phụ thuộc bảng khác

WHERE không chỉ so sánh giá trị trong cùng bảng; nó có thể kiểm tra **có hay không có dòng liên quan** ở một bảng khác.

Giả sử thêm bảng **chi_tiet_don_hang**:

| ma_don_hang | ma_san_pham | so_luong |
|---:|---:|---:|
| 5001 | 101 | 2 |
| 5002 | 103 | 1 |
| 5003 | 103 | 3 |
| 5004 | 105 | 1 |
| 5005 | 107 | 2 |

Yêu cầu: “Tìm những sản phẩm đã từng xuất hiện trong chi tiết đơn hàng”.

~~~sql
SELECT
    s.ma_san_pham,
    s.ten_san_pham
FROM san_pham s
WHERE EXISTS (
    SELECT 1
    FROM chi_tiet_don_hang c
    WHERE c.ma_san_pham = s.ma_san_pham
)
ORDER BY s.ma_san_pham;
~~~

Kết quả có mã **101, 103, 105, 107**.

**EXISTS** trả TRUE nếu truy vấn con có ít nhất một dòng thỏa điều kiện, dù dòng đó có các cột khác chứa NULL. Các phần tử của SELECT trong truy vấn con không quyết định trực tiếp tồn tại hay không, nên **SELECT 1** là cách thể hiện thường dùng.

Để tìm sản phẩm **chưa từng xuất hiện** trong chi tiết đơn hàng:

~~~sql
SELECT
    s.ma_san_pham,
    s.ten_san_pham
FROM san_pham s
WHERE NOT EXISTS (
    SELECT 1
    FROM chi_tiet_don_hang c
    WHERE c.ma_san_pham = s.ma_san_pham
)
ORDER BY s.ma_san_pham;
~~~

Kết quả: **102, 104, 106, 108**.

### 13.1. Phân biệt EXISTS với JOIN

Một JOIN thường tạo một hàng kết quả cho mỗi cặp hàng khớp. Vì sản phẩm 103 xuất hiện trong hai chi tiết đơn hàng, JOIN trực tiếp có thể tạo hai hàng cho sản phẩm đó nếu không dùng DISTINCT hoặc gộp nhóm.

EXISTS chỉ hỏi **có ít nhất một hàng khớp không** nên mỗi sản phẩm ở bảng ngoài vẫn được xét như một dòng riêng. Trong bài toán tìm sự tồn tại, cách viết EXISTS thường diễn đạt đúng ý định mà không cần loại hàng trùng từ JOIN.

## 14. WHERE khi có JOIN: phân biệt lọc dòng và điều kiện nối

Giả sử có bảng **don_hang**:

| ma_don_hang | ma_khach_hang | trang_thai |
|---:|---:|---|
| 9001 | 1 | PAID |
| 9002 | 1 | CANCELLED |
| 9003 | 2 | PENDING |

Và bảng **khach_hang**:

| ma_khach_hang | ten_khach_hang |
|---:|---|
| 1 | An |
| 2 | Bình |
| 3 | Chi |

### 14.1. INNER JOIN

~~~sql
SELECT
    k.ten_khach_hang,
    d.ma_don_hang
FROM khach_hang k
JOIN don_hang d
    ON d.ma_khach_hang = k.ma_khach_hang
WHERE d.trang_thai = 'PAID';
~~~

Kết quả: **An — 9001**. INNER JOIN chỉ tạo cặp hàng khớp điều kiện ON, rồi WHERE chỉ giữ những cặp có trạng thái PAID.

### 14.2. LEFT JOIN: đặt điều kiện ở ON hay WHERE tạo kết quả khác nhau

Yêu cầu: “Hiển thị **mọi khách hàng**, kèm mã đơn đã thanh toán nếu có.”

~~~sql
SELECT
    k.ten_khach_hang,
    d.ma_don_hang
FROM khach_hang k
LEFT JOIN don_hang d
    ON d.ma_khach_hang = k.ma_khach_hang
   AND d.trang_thai = 'PAID'
ORDER BY k.ma_khach_hang;
~~~

Kết quả:

| ten_khach_hang | ma_don_hang |
|---|---:|
| An | 9001 |
| Bình | NULL |
| Chi | NULL |

Nếu chuyển điều kiện trạng thái xuống WHERE:

~~~sql
SELECT
    k.ten_khach_hang,
    d.ma_don_hang
FROM khach_hang k
LEFT JOIN don_hang d
    ON d.ma_khach_hang = k.ma_khach_hang
WHERE d.trang_thai = 'PAID';
~~~

Kết quả chỉ có **An — 9001**. Bình có đơn PENDING nên bị lọc; Chi không có đơn, nhận NULL ở cột trạng thái phía phải, nên điều kiện WHERE cho UNKNOWN và bị lọc.

**Quy tắc:** Với OUTER JOIN, **ON** quyết định dòng nào khớp để nối, còn **WHERE** lọc các dòng kết quả sau bước nối logic. Nếu phải giữ hàng không có quan hệ ở phía ngoài, việc đặt điều kiện ở đúng chỗ rất quan trọng.

## 15. WHERE trong trình tự xử lý logic của SELECT

Thứ tự viết cú pháp thường là:

~~~sql
SELECT ...
FROM ...
WHERE ...
GROUP BY ...
HAVING ...
ORDER BY ...;
~~~

Nhưng để hiểu kết quả, có thể dùng mô hình xử lý logic đơn giản:

~~~text
FROM / JOIN     -> hình thành nguồn hàng
WHERE           -> lọc từng hàng trước khi gộp nhóm
GROUP BY        -> tạo nhóm (nếu có)
HAVING          -> lọc nhóm (nếu có)
SELECT          -> chọn và tính cột đầu ra
ORDER BY        -> sắp xếp kết quả cuối
~~~

Đây là **mô hình tư duy về ngữ nghĩa**, không phải lời khẳng định DBMS thực thi vật lý từng bước theo đúng trình tự. Bộ tối ưu có thể chuyển vị trí phép lọc, đẩy điều kiện xuống chỉ mục hoặc chọn kế hoạch khác miễn bảo toàn kết quả.

### 15.1. WHERE không dùng trực tiếp hàm tổng hợp để lọc nhóm

Giả sử bảng **chi_tiet_don_hang** có các dòng như phần 13. Yêu cầu: “Sản phẩm nào xuất hiện trong ít nhất hai dòng chi tiết đơn hàng?”

Sai:

~~~sql
-- Không hợp lệ trong WHERE thông thường:
SELECT ma_san_pham, COUNT(*) AS so_dong
FROM chi_tiet_don_hang
WHERE COUNT(*) >= 2
GROUP BY ma_san_pham;
~~~

Hàm tổng hợp COUNT(*) được xác định theo nhóm, trong khi WHERE lọc từng dòng **trước khi** nhóm hình thành.

Đúng:

~~~sql
SELECT ma_san_pham, COUNT(*) AS so_dong
FROM chi_tiet_don_hang
GROUP BY ma_san_pham
HAVING COUNT(*) >= 2;
~~~

Kết quả là **ma_san_pham = 103**, **so_dong = 2**.

### 15.2. WHERE trước GROUP BY vẫn rất hữu ích

Nếu chỉ muốn tính tổng số lượng của các dòng có **so_luong >= 2**:

~~~sql
SELECT
    c.ma_san_pham,
    SUM(c.so_luong) AS tong_so_luong
FROM chi_tiet_don_hang c
WHERE c.so_luong >= 2
GROUP BY c.ma_san_pham
ORDER BY c.ma_san_pham;
~~~

WHERE lọc bớt những dòng có số lượng dưới 2 trước khi SUM/GROUP BY. HAVING có thể dùng thêm nếu muốn lọc **nhóm sau tổng hợp**.

## 16. Không tham chiếu bí danh cột SELECT trong WHERE của cùng query block

Một lỗi phổ biến:

~~~sql
-- Thường lỗi: WHERE không thấy alias cột gia_sau_thue vừa đặt ở SELECT.
SELECT
    ma_san_pham,
    gia_ban * 1.08 AS gia_sau_thue
FROM san_pham
WHERE gia_sau_thue >= 300000;
~~~

Trong mô hình xử lý logic, WHERE diễn ra trước khi danh sách đầu ra SELECT được đặt tên. Một số phương ngữ có ngoại lệ nhưng không nên dựa vào chúng khi viết SQL phổ biến.

Có thể lặp biểu thức gốc:

~~~sql
SELECT
    ma_san_pham,
    gia_ban * 1.08 AS gia_sau_thue
FROM san_pham
WHERE gia_ban * 1.08 >= 300000;
~~~

Hoặc dùng CTE:

~~~sql
WITH bang_gia AS (
    SELECT
        ma_san_pham,
        ten_san_pham,
        gia_ban * 1.08 AS gia_sau_thue
    FROM san_pham
)
SELECT
    ma_san_pham,
    ten_san_pham,
    gia_sau_thue
FROM bang_gia
WHERE gia_sau_thue >= 300000;
~~~

Ở query block bên ngoài, **gia_sau_thue** đã trở thành cột của nguồn bang_gia nên có thể dùng trong WHERE.

Trong nhiều DBMS, alias cột đầu ra được phép dùng ở **ORDER BY** cuối cùng:

~~~sql
SELECT
    ma_san_pham,
    gia_ban * 1.08 AS gia_sau_thue
FROM san_pham
ORDER BY gia_sau_thue DESC;
~~~

**WHERE** lọc dòng, còn **ORDER BY** sắp xếp những dòng kết quả. Thêm ORDER BY không khiến điều kiện WHERE trở thành hợp lệ nếu tham chiếu alias sai phạm vi.

## 17. WHERE và ORDER BY: lọc không đồng nghĩa sắp xếp

Truy vấn:

~~~sql
SELECT ma_san_pham, ten_san_pham, gia_ban
FROM san_pham
WHERE dang_ban = 1;
~~~

chọn các sản phẩm đang bán nhưng **không bảo đảm thứ tự hiển thị**. Nếu cần kết quả tăng dần theo giá:

~~~sql
SELECT ma_san_pham, ten_san_pham, gia_ban
FROM san_pham
WHERE dang_ban = 1
ORDER BY gia_ban ASC, ma_san_pham ASC;
~~~

Vị trí các hàng có **gia_ban = NULL** phụ thuộc vào DBMS và lựa chọn NULLS FIRST/LAST nếu được hỗ trợ. Có thể dùng CASE để biểu diễn ưu tiên đẩy NULL về cuối một cách rõ ràng hơn trong môi trường đa DBMS:

~~~sql
SELECT ma_san_pham, ten_san_pham, gia_ban
FROM san_pham
WHERE dang_ban = 1
ORDER BY
    CASE WHEN gia_ban IS NULL THEN 1 ELSE 0 END,
    gia_ban ASC,
    ma_san_pham ASC;
~~~

Việc thêm **ma_san_pham** làm khóa phụ giúp thứ tự ổn định khi hai sản phẩm có cùng giá.

Nếu ứng dụng cần lấy **N dòng đầu tiên**, hãy kết hợp ORDER BY với cú pháp giới hạn dòng theo đúng DBMS: ví dụ LIMIT ở PostgreSQL/MySQL/SQLite, TOP hoặc OFFSET/FETCH ở SQL Server, FETCH FIRST ở các bản Oracle hiện đại. Không mặc định một cú pháp giới hạn dòng chạy trên mọi hệ.

## 18. WHERE trong UPDATE và DELETE

WHERE cũng được dùng để **chọn những hàng chịu tác động** trong câu lệnh cập nhật và xóa:

~~~sql
-- Chỉ cập nhật sản phẩm có mã 102.
UPDATE san_pham
SET so_luong_ton = 50
WHERE ma_san_pham = 102;
~~~

~~~sql
-- Chỉ minh họa cú pháp. Không chạy xóa dữ liệu thật nếu chưa xác nhận.
DELETE FROM san_pham
WHERE dang_ban = 0;
~~~

Đặc biệt lưu ý:

- **UPDATE không có WHERE** có thể cập nhật tất cả hàng trong bảng.
- **DELETE không có WHERE** có thể xóa tất cả hàng trong bảng.
- Nếu WHERE chứa NULL hoặc nhiều AND/OR, số hàng bị ảnh hưởng có thể khác trực giác.
- Ở môi trường có dữ liệu quan trọng, hãy thử điều kiện bằng **SELECT** trước, xem số hàng dự kiến và thực hiện trong giao dịch phù hợp; kiểm tra số hàng chịu tác động sau câu lệnh ghi.
- Kiểm tra thêm chính sách khóa, ràng buộc tham chiếu, transaction và quyền truy cập của DBMS.

Ví dụ kiểm tra điều kiện trước khi cập nhật:

~~~sql
SELECT ma_san_pham, ten_san_pham, so_luong_ton
FROM san_pham
WHERE ma_san_pham = 102;
~~~

Sau khi xác nhận kết quả đúng mục tiêu mới dùng cùng điều kiện trong UPDATE.

## 19. Truyền tham số vào WHERE trong Java JDBC

Trong ứng dụng thực tế, giá trị bộ lọc thường đến từ người dùng hoặc một dịch vụ khác. Không nên nối trực tiếp đầu vào vào chuỗi SQL:

~~~java
// Không an toàn và dễ lỗi nháy/kiểu dữ liệu:
String sql = "SELECT * FROM san_pham WHERE danh_muc = '" + input + "'";
~~~

Cách này có nguy cơ **SQL injection** và dễ hỏng khi văn bản chứa dấu nháy đơn.

Với JDBC, nên dùng **PreparedStatement** và ký hiệu **?**:

~~~java
String sql = """
    SELECT ma_san_pham, ten_san_pham, gia_ban
    FROM san_pham
    WHERE danh_muc = ?
      AND dang_ban = ?
      AND gia_ban >= ?
    ORDER BY ma_san_pham
    """;

try (PreparedStatement statement = connection.prepareStatement(sql)) {
    statement.setString(1, "Điện tử");
    statement.setInt(2, 1);
    statement.setBigDecimal(3, new java.math.BigDecimal("200000"));

    try (ResultSet result = statement.executeQuery()) {
        while (result.next()) {
            int ma = result.getInt("ma_san_pham");
            String ten = result.getString("ten_san_pham");
            java.math.BigDecimal gia =
                result.getBigDecimal("gia_ban");

            System.out.println(ma + " - " + ten + " - " + gia);
        }
    }
}
~~~

Với dữ liệu mẫu, truy vấn chọn **Tai nghe (103)** và **Chuột không dây (107)**. Sản phẩm 104 thuộc Điện tử và giá trên 200.000 nhưng **dang_ban = 0** nên bị loại.

Lợi ích của prepared statement:

- Giá trị được truyền qua cơ chế tham số hóa thay vì chèn trực tiếp vào cú pháp SQL.
- Có thể bind đúng kiểu dữ liệu, ví dụ **setBigDecimal**, **setInt**, **setDate** hoặc **setObject** với kiểu phù hợp.
- Dễ giữ một câu truy vấn ổn định với nhiều giá trị bộ lọc khác nhau.

**Tham số chỉ đại diện cho giá trị**, không mặc nhiên thay thế được tên bảng, tên cột hoặc từ khóa SQL. Nếu người dùng được chọn trường sắp xếp hay cột tìm kiếm, ứng dụng phải ánh xạ lựa chọn đó tới một **danh sách định danh được phép** và tự tạo phần cú pháp tương ứng an toàn.

### 19.1. Bộ lọc tùy chọn

Giả sử màn hình tìm kiếm có **danh mục** (có thể bỏ trống) và **giá tối thiểu** (có thể bỏ trống). Một cách đơn giản là xây dựng câu SQL từ các điều kiện đã được định nghĩa trước, chỉ thêm WHERE khi người dùng cung cấp tiêu chí; mỗi giá trị vẫn bind qua PreparedStatement.

Pseudocode:

~~~text
base SQL: SELECT ... FROM san_pham WHERE 1 = 1
if category present:
    append " AND danh_muc = ?"
    bind category
if minPrice present:
    append " AND gia_ban >= ?"
    bind minPrice
append " ORDER BY ma_san_pham"
~~~

**WHERE 1 = 1** luôn TRUE, nên có thể đơn giản hóa thao tác nối các điều kiện AND. Nó không phải cú pháp bắt buộc của WHERE và không cần dùng khi câu SQL cố định. Khi bộ lọc phức tạp hơn, nên dùng bộ xây dựng truy vấn hoặc một cấu trúc rõ ràng để quản lý dấu ngoặc và thứ tự tham số.

Nếu một tiêu chí **không được cung cấp**, đừng tự truyền NULL vào **= ?** rồi kỳ vọng điều kiện được bỏ qua. **cot = NULL** là UNKNOWN trong SQL thông thường. Lựa chọn “không lọc cột” và lựa chọn “tìm dòng có cột NULL” là hai yêu cầu khác nhau.

### 19.2. Bộ lọc danh sách có tham số

Nếu cần IN với danh sách biến độ dài, hầu hết API PreparedStatement không cho bind toàn bộ một danh sách vào đúng một dấu **?** theo cách phổ quát. Ứng dụng thường tạo đúng số lượng **placeholder** hoặc dùng API bảng/array riêng của DBMS nếu được hỗ trợ.

Ví dụ với ba mã:

~~~sql
SELECT ma_san_pham, ten_san_pham
FROM san_pham
WHERE ma_san_pham IN (?, ?, ?);
~~~

Rồi bind từng mã cho ba vị trí. Với danh sách rỗng, ứng dụng phải có quy tắc riêng như đã nêu ở phần IN.

## 20. Lọc hàng và hiệu năng: điều kiện nào tận dụng chỉ mục?

WHERE ảnh hưởng không chỉ kết quả mà cả hiệu năng. Trong nhiều trường hợp, **chỉ mục (index)** giúp DBMS tìm nhanh những hàng thỏa điều kiện mà không cần đọc toàn bộ bảng.

Ví dụ, nếu có chỉ mục thích hợp trên **ma_san_pham**, truy vấn:

~~~sql
SELECT ma_san_pham, ten_san_pham
FROM san_pham
WHERE ma_san_pham = 107;
~~~

có thể tận dụng nó để tìm hàng đích nhanh hơn.

Nhưng việc DBMS **thực sự dùng chỉ mục hay không** phụ thuộc vào số lượng dữ liệu, thống kê, tỷ lệ hàng khớp, cấu trúc chỉ mục và bộ tối ưu. Không thể bảo đảm chỉ vì WHERE dùng toán tử bằng thì truy vấn chắc chắn sẽ dùng index.

### 20.1. Tránh biến đổi cột không cần thiết trong điều kiện lọc

Giả sử bảng sản phẩm có chỉ mục trên **gia_ban**. Hai biểu thức có thể phục vụ ý định gần nhau nhưng khả năng tận dụng chỉ mục khác:

~~~sql
-- Thường thuận lợi hơn cho tìm kiếm theo khoảng trên chỉ mục cột gốc.
SELECT ma_san_pham, gia_ban
FROM san_pham
WHERE gia_ban >= 100000;
~~~

~~~sql
-- Phép tính trên cột có thể khiến chỉ mục thông thường khó được dùng trực tiếp.
SELECT ma_san_pham, gia_ban
FROM san_pham
WHERE gia_ban * 1.10 >= 110000;
~~~

Nếu phép toán có thể được biến đổi tương đương **mà không đổi kiểu, làm tròn hoặc ngữ nghĩa NULL**, biểu thức dùng trực tiếp cột gốc thường dễ tối ưu. Tuy nhiên, không tự biến đổi phương trình số học khi có nguy cơ sai lệch do kiểu số, phép làm tròn hoặc sai số.

Một ví dụ với ngày giờ:

~~~sql
-- Cách có thể hỗ trợ range scan trên chỉ mục ngay_tao.
WHERE ngay_tao >= ?
  AND ngay_tao < ?
~~~

so với việc dùng hàm trích tháng/năm trên cột trong WHERE. Hàm áp lên cột có thể cản trở một chỉ mục thông thường, dù một số DBMS hỗ trợ **functional index/expression index** hoặc tối ưu chuyên biệt.

### 20.2. LIKE và tiền tố

~~~sql
WHERE ten_san_pham LIKE 'Bút%'
~~~

Mẫu có tiền tố cố định đôi khi tận dụng được chỉ mục phù hợp, tùy collation và loại chỉ mục.

~~~sql
WHERE ten_san_pham LIKE '%bút%'
~~~

Mẫu bắt đầu bằng % thường khó tận dụng chỉ mục B-tree thông thường để tìm theo tiền tố. Với chức năng tìm kiếm văn bản lớn, cần xem xét chỉ mục hoặc công cụ tìm kiếm phù hợp DBMS.

### 20.3. Đừng thêm quá nhiều điều kiện theo cảm tính

Nhiều điều kiện AND không tự đảm bảo nhanh hơn, vì DBMS vẫn phải đánh giá mức chọn lọc và cách truy cập dữ liệu. Truy vấn có OR trên nhiều cột cũng có thể ảnh hưởng khả năng sử dụng chỉ mục. Khi hiệu năng quan trọng, nên dùng **EXPLAIN** hoặc công cụ xem execution plan tương ứng DBMS, đối chiếu số dòng ước lượng/thực tế và đo trên dữ liệu có quy mô gần thật.

Mục tiêu đầu tiên là **đúng ngữ nghĩa**; sau đó mới tối ưu và kiểm tra hiệu năng. Tránh thay đổi logic lọc chỉ để ép dùng index nếu thay đổi đó làm sai kết quả.

## 21. Các lỗi thường gặp khi dùng WHERE

| Lỗi/ngộ nhận | Hệ quả | Cách viết hoặc cách nghĩ đúng |
|---|---|---|
| Dùng **==** theo thói quen lập trình | Không portable, thường lỗi cú pháp | Dùng **=** |
| Dùng **email = NULL** | Điều kiện UNKNOWN | Dùng **email IS NULL** |
| Dùng **email <> NULL** | Điều kiện UNKNOWN | Dùng **email IS NOT NULL** |
| Bỏ dấu ngoặc trong AND/OR | Lọc sai nhóm hàng | Viết nhóm điều kiện tường minh |
| Dùng **BETWEEN** nhưng quên hai đầu mút được tính | Thừa/thiếu dữ liệu tại biên | Dùng >= và <= khi cần diễn giải rõ |
| Dùng **BETWEEN** cho khoảng TIMESTAMP đến cuối ngày với giờ 00:00 | Bỏ sót dữ liệu cuối ngày | Dùng >= ngày đầu và < ngày kế tiếp |
| Dùng **LIKE** khi cần bằng chính xác | Wildcard có thể mở rộng phạm vi kết quả | Dùng **=** nếu so bằng chính xác |
| Dùng **NOT IN** với tập con chứa NULL | Có thể không trả hàng mong đợi | Lọc NULL hoặc cân nhắc NOT EXISTS |
| Viết **WHERE COUNT(*) > ...** | Tổng hợp chưa có ở bước WHERE | Dùng HAVING |
| Dùng alias SELECT trong WHERE cùng cấp | Thường lỗi phân giải tên | Lặp biểu thức hoặc dùng CTE/truy vấn con |
| Đưa điều kiện phía phải LEFT JOIN vào WHERE | Loại hàng không khớp | Đặt điều kiện nối phù hợp trong ON |
| Xem **NULL** như **0** hoặc chuỗi rỗng | Sai ý nghĩa dữ liệu thiếu | Dùng IS NULL; chỉ COALESCE khi nghiệp vụ cho phép |
| Quên WHERE trong UPDATE/DELETE | Có thể sửa/xóa mọi hàng | Kiểm tra bằng SELECT và đối chiếu số hàng trước ghi |
| Nối chuỗi từ đầu vào người dùng vào SQL | SQL injection hoặc lỗi ký tự | Dùng PreparedStatement và bind tham số |
| Cho rằng WHERE tự sắp xếp kết quả | Kết quả có thứ tự không xác định | Thêm ORDER BY |
| Tin rằng điều kiện phía trái của AND luôn được thực thi trước | Có thể gặp lỗi hoặc kết quả bất ngờ khi bộ tối ưu biến đổi | Không phụ thuộc thứ tự vật lý, viết biểu thức an toàn |

## 22. Bài tập thực hành

Sử dụng bảng **san_pham** ở phần 3 cho các bài từ 1 đến 8 và bảng quan hệ ở những phần tương ứng cho bài 9–10.

### Bài 1 — Lọc bằng phép so sánh

Viết truy vấn lấy mã, tên và giá sản phẩm có **gia_ban <= 50000**. Dự đoán các mã được chọn.

<details>
<summary>Gợi ý đáp án</summary>

~~~sql
SELECT ma_san_pham, ten_san_pham, gia_ban
FROM san_pham
WHERE gia_ban <= 50000
ORDER BY ma_san_pham;
~~~

Kết quả: **101, 102, 108**. Sản phẩm 106 có giá NULL nên không được giữ.

</details>

### Bài 2 — Kết hợp AND

Lấy sản phẩm **đang bán**, **còn hàng** và **giá dưới 300.000**.

<details>
<summary>Gợi ý đáp án</summary>

~~~sql
SELECT ma_san_pham, ten_san_pham
FROM san_pham
WHERE dang_ban = 1
  AND so_luong_ton > 0
  AND gia_ban < 300000
ORDER BY ma_san_pham;
~~~

Kết quả: **101, 105, 107, 108**. Sản phẩm 102 hết hàng; sản phẩm 106 chưa có giá; sản phẩm 103 giá 350.000; sản phẩm 104 đã ngừng bán.

</details>

### Bài 3 — Dấu ngoặc và OR

Yêu cầu: “Lấy sản phẩm đang bán thuộc **Điện tử** hoặc **Gia dụng**.” Câu nào đúng?

~~~sql
-- A
WHERE danh_muc = 'Điện tử'
   OR danh_muc = 'Gia dụng'
  AND dang_ban = 1
~~~

~~~sql
-- B
WHERE (danh_muc = 'Điện tử' OR danh_muc = 'Gia dụng')
  AND dang_ban = 1
~~~

<details>
<summary>Gợi ý đáp án</summary>

**B đúng ý định.** Trong A, AND có ưu tiên cao hơn OR, nên sản phẩm thuộc Điện tử có thể được giữ dù không còn bán. B trả **103, 105, 106, 107**.

</details>

### Bài 4 — IN

Viết truy vấn lấy sản phẩm thuộc danh mục Văn phòng phẩm hoặc Gia dụng.

<details>
<summary>Gợi ý đáp án</summary>

~~~sql
SELECT ma_san_pham, ten_san_pham
FROM san_pham
WHERE danh_muc IN ('Văn phòng phẩm', 'Gia dụng')
ORDER BY ma_san_pham;
~~~

Kết quả: **101, 102, 105, 106, 108**.

</details>

### Bài 5 — BETWEEN

Lấy sản phẩm có giá **từ 120.000 đến 350.000**, tính cả hai đầu mút.

<details>
<summary>Gợi ý đáp án</summary>

~~~sql
SELECT ma_san_pham, ten_san_pham, gia_ban
FROM san_pham
WHERE gia_ban BETWEEN 120000 AND 350000
ORDER BY ma_san_pham;
~~~

Kết quả: **103, 105, 107**. Giá bằng 120.000 hoặc 350.000 đều được giữ.

</details>

### Bài 6 — LIKE

Lấy những sản phẩm có tên **bắt đầu bằng “Bút”**.

<details>
<summary>Gợi ý đáp án</summary>

~~~sql
SELECT ma_san_pham, ten_san_pham
FROM san_pham
WHERE ten_san_pham LIKE 'Bút%'
ORDER BY ma_san_pham;
~~~

Kết quả: **102, 108**.

</details>

### Bài 7 — NULL

Yêu cầu: “Lấy những sản phẩm có giá từ 100.000 trở lên **hoặc chưa xác định giá**.”

<details>
<summary>Gợi ý đáp án</summary>

~~~sql
SELECT ma_san_pham, ten_san_pham, gia_ban
FROM san_pham
WHERE gia_ban >= 100000
   OR gia_ban IS NULL
ORDER BY ma_san_pham;
~~~

Kết quả: **103, 104, 105, 106, 107**. Đặt **gia_ban = NULL** ở vế OR sẽ không thực hiện được ý định này.

</details>

### Bài 8 — Phủ định

Truy vấn sau có chọn sản phẩm 106 không?

~~~sql
SELECT ma_san_pham
FROM san_pham
WHERE NOT (gia_ban > 50000);
~~~

<details>
<summary>Gợi ý đáp án</summary>

**Không.** Với sản phẩm 106, gia_ban NULL làm **gia_ban > 50000** = UNKNOWN. **NOT UNKNOWN** vẫn UNKNOWN, nên WHERE loại dòng. Các mã được chọn là **101, 102, 108**.

</details>

### Bài 9 — WHERE và HAVING

Từ bảng **chi_tiet_don_hang**, viết truy vấn thống kê mỗi sản phẩm có bao nhiêu dòng chi tiết và chỉ hiển thị sản phẩm xuất hiện **ít nhất hai dòng**.

<details>
<summary>Gợi ý đáp án</summary>

~~~sql
SELECT ma_san_pham, COUNT(*) AS so_dong
FROM chi_tiet_don_hang
GROUP BY ma_san_pham
HAVING COUNT(*) >= 2;
~~~

Kết quả: **ma_san_pham = 103, so_dong = 2**. Không đặt COUNT(*) trực tiếp trong WHERE vì WHERE lọc từng hàng trước bước GROUP BY.

</details>

### Bài 10 — LEFT JOIN

Lấy tất cả khách hàng và mã đơn hàng có trạng thái PAID, kể cả khách không có đơn PAID.

<details>
<summary>Gợi ý đáp án</summary>

~~~sql
SELECT k.ten_khach_hang, d.ma_don_hang
FROM khach_hang k
LEFT JOIN don_hang d
    ON d.ma_khach_hang = k.ma_khach_hang
   AND d.trang_thai = 'PAID'
ORDER BY k.ma_khach_hang;
~~~

Với dữ liệu phần 14, kết quả là **An — 9001**, **Bình — NULL**, **Chi — NULL**. Đặt điều kiện trạng thái trong ON giúp LEFT JOIN giữ các khách không có đơn phù hợp.

</details>

### Bài 11 — Mô tả một bộ lọc thực tế

Ứng dụng có các trường tìm kiếm: **từ khóa tên sản phẩm**, **danh mục tùy chọn**, **giá tối thiểu**, **giá tối đa**, **chỉ lấy hàng còn bán**. Hãy nêu các điểm cần xử lý khi biến các bộ lọc này thành WHERE.

<details>
<summary>Gợi ý đáp án</summary>

- Tên sản phẩm: dùng LIKE với mẫu phù hợp, quyết định cách xử lý ký tự **%** và **_** do người dùng nhập.
- Danh mục: thêm **danh_muc = ?** khi được chọn; nếu không chọn thì bỏ điều kiện, không truyền NULL vào dấu bằng.
- Giá tối thiểu/tối đa: bind giá trị số đúng kiểu, xác định rõ **>=**, **<=** và giới hạn có tính bao gồm hay không.
- Còn bán: dùng **dang_ban = 1** theo quy ước của bảng mẫu.
- Các điều kiện độc lập thường ghép bằng **AND**, nhóm OR nếu người dùng chọn nhiều danh mục hoặc nhiều từ khóa.
- Dùng PreparedStatement; không nối trực tiếp giá trị đầu vào vào câu SQL.
- Xác định sản phẩm giá NULL cần được giữ hay loại và kiểm thử các trường hợp bộ lọc trống.
- Nếu kết quả cần phân trang, thêm ORDER BY ổn định và cú pháp phân trang phù hợp DBMS.

</details>

## 23. Tình huống tổng hợp: viết WHERE từ yêu cầu nghiệp vụ

Giả sử cửa hàng cần báo cáo:

> “Tìm các sản phẩm **đang bán**, **còn hàng**, có giá **từ 100.000 đến 400.000**, thuộc **Điện tử hoặc Gia dụng**. Hiển thị giá cao trước, nếu bằng giá thì sắp xếp theo mã tăng dần.”

Ta tách yêu cầu thành các nhóm:

| Yêu cầu | Điều kiện SQL |
|---|---|
| Đang bán | dang_ban = 1 |
| Còn hàng | so_luong_ton > 0 |
| Giá từ 100.000 đến 400.000 | gia_ban BETWEEN 100000 AND 400000 |
| Điện tử hoặc Gia dụng | danh_muc IN ('Điện tử', 'Gia dụng') |
| Giá giảm dần, mã tăng dần | ORDER BY gia_ban DESC, ma_san_pham ASC |

Truy vấn hoàn chỉnh:

~~~sql
SELECT
    ma_san_pham,
    ten_san_pham,
    danh_muc,
    gia_ban,
    so_luong_ton
FROM san_pham
WHERE dang_ban = 1
  AND so_luong_ton > 0
  AND gia_ban BETWEEN 100000 AND 400000
  AND danh_muc IN ('Điện tử', 'Gia dụng')
ORDER BY gia_ban DESC, ma_san_pham ASC;
~~~

Kết quả:

| ma_san_pham | ten_san_pham | danh_muc | gia_ban | so_luong_ton |
|---:|---|---|---:|---:|
| 103 | Tai nghe | Điện tử | 350000 | 12 |
| 107 | Chuột không dây | Điện tử | 250000 | 4 |
| 105 | Bình nước | Gia dụng | 120000 | 20 |

Ở đây, điều kiện WHERE đã loại Bàn phím (104) vì không còn bán, Đèn bàn (106) vì chưa có giá xác định và các sản phẩm Văn phòng phẩm vì không thuộc nhóm danh mục yêu cầu.

Nếu nghiệp vụ thay đổi thành “bao gồm cả sản phẩm chưa có giá”, chỉ cần thay điều kiện về giá bằng một nhóm được đặt ngoặc rõ ràng:

~~~sql
WHERE dang_ban = 1
  AND so_luong_ton > 0
  AND (gia_ban BETWEEN 100000 AND 400000 OR gia_ban IS NULL)
  AND danh_muc IN ('Điện tử', 'Gia dụng')
~~~

Khi đó, sản phẩm Đèn bàn (106) được bổ sung vào kết quả. Khi sắp xếp, cần xác định vị trí của NULL nếu muốn đầu ra giống nhau trên các DBMS.

## 24. Ghi nhớ cuối bài

1. **WHERE lọc hàng**: chỉ điều kiện TRUE mới giữ dòng; FALSE và UNKNOWN đều bị loại khỏi kết quả.
2. Dùng **=**, **<>**, **>**, **>=**, **<**, **<=** để so sánh; dùng **IN**, **BETWEEN**, **LIKE** khi bài toán phù hợp.
3. **AND** yêu cầu mọi điều kiện đúng, **OR** yêu cầu ít nhất một điều kiện đúng, **NOT** phủ định điều kiện; dùng **dấu ngoặc** khi trộn AND và OR.
4. **NULL không phải 0 hay FALSE**. Muốn tìm dữ liệu thiếu, dùng **IS NULL**; muốn tìm giá trị hiện có, dùng **IS NOT NULL**.
5. **NOT IN** với tập con chứa NULL có thể cho kết quả bất ngờ. Với yêu cầu “không có bản ghi liên quan”, cân nhắc **NOT EXISTS**.
6. **WHERE lọc trước GROUP BY**; **HAVING lọc sau GROUP BY**. Không dùng hàm tổng hợp trong WHERE thông thường để lọc nhóm.
7. **WHERE và JOIN ... ON** có vai trò khác nhau, đặc biệt khi dùng LEFT JOIN.
8. **WHERE không bảo đảm thứ tự dòng**. Muốn sắp xếp, phải có ORDER BY.
9. Khi giá trị lọc đến từ người dùng, dùng **prepared statement và tham số hóa** để vừa an toàn vừa đúng kiểu dữ liệu.
10. Đầu tiên hãy bảo đảm truy vấn **trả đúng hàng theo yêu cầu nghiệp vụ**; sau đó mới xem xét chỉ mục, kế hoạch thực thi và tối ưu hiệu năng.

### Tài liệu tham khảo định hướng

Khi áp dụng vào sản phẩm cụ thể, đối chiếu tài liệu chính thức của **PostgreSQL (SELECT, WHERE, Comparison Functions and Operators)**, **MySQL (SELECT Statement, Comparison Functions, LIKE)**, **Microsoft SQL Server / Transact-SQL (SELECT — WHERE, Search Condition)**, **Oracle Database SQL Language Reference (Conditions, SELECT)** và **SQLite (SELECT, Expressions)**. Các hệ quản trị chia sẻ nền tảng SQL nhưng có khác biệt về kiểu dữ liệu, collation, hàm, cú pháp tham số và một số tính năng riêng; cần xác nhận trên đúng phiên bản DBMS và driver đang triển khai.
