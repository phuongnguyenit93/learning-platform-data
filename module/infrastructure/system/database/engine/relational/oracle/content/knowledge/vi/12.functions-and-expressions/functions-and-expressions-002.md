# Hàm số: ROUND, TRUNC, MOD, CEIL và FLOOR trong Oracle Database

Trong Oracle SQL, các hàm số học thường dùng để làm tròn, cắt phần thập phân, lấy phần dư hoặc xác định số nguyên gần nhất là **ROUND, TRUNC, MOD, CEIL và FLOOR**. Chúng có vẻ gần nhau nhưng quy tắc khác biệt, đặc biệt khi xử lý số âm:

- **ROUND** làm tròn đến vị trí chữ số được yêu cầu.
- **TRUNC** cắt chữ số ngoài vị trí được yêu cầu, theo hướng về 0.
- **MOD** lấy phần dư theo định nghĩa của Oracle.
- **CEIL** lấy số nguyên nhỏ nhất lớn hơn hoặc bằng giá trị đầu vào.
- **FLOOR** lấy số nguyên lớn nhất nhỏ hơn hoặc bằng giá trị đầu vào.

Ví dụ, TRUNC(-2.7) bằng -2, trong khi FLOOR(-2.7) bằng -3. Hiểu sai khác biệt này có thể làm sai số lượng, tiền, tỷ lệ hoặc cách chia dữ liệu vào nhóm. Bài học trình bày cú pháp, ví dụ SQL, ứng dụng, kiểu dữ liệu, NULL và bài lab sử dụng DUAL.

## 1. Tổng quan

| Hàm | Cú pháp | Ý nghĩa | Ví dụ | Kết quả |
|---|---|---|---|---:|
| ROUND | ROUND(n [, integer]) | Làm tròn đến vị trí chỉ định | ROUND(12.345, 2) | 12.35 |
| TRUNC | TRUNC(n [, integer]) | Cắt chữ số, hướng về 0 | TRUNC(12.345, 2) | 12.34 |
| MOD | MOD(n2, n1) | Phần dư của n2 chia n1 | MOD(17, 5) | 2 |
| CEIL | CEIL(n) | Số nguyên nhỏ nhất không nhỏ hơn n | CEIL(12.1) | 13 |
| FLOOR | FLOOR(n) | Số nguyên lớn nhất không lớn hơn n | FLOOR(12.9) | 12 |

n, n1 và n2 là biểu thức số. Đối số integer của ROUND và TRUNC xác định vị trí chữ số; nếu bỏ qua thì mặc định là 0, tức xử lý đến số nguyên.

Các hàm có thể được dùng trong SELECT list, WHERE, ORDER BY, biểu thức tính toán, truy vấn con, INSERT hoặc UPDATE. Khi gọi trong SELECT, chúng chỉ tạo giá trị kết quả; chúng không tự sửa dữ liệu đang lưu trong bảng.

## 2. ROUND: làm tròn số

### 2.1 Cú pháp và vị trí làm tròn

~~~sql
ROUND(number [, integer])
~~~

- number là giá trị số cần làm tròn.
- integer là vị trí chữ số cần làm tròn.
- Bỏ integer tương đương làm tròn đến số nguyên.
- integer dương chỉ vị trí bên phải dấu thập phân; integer âm chỉ vị trí bên trái.

~~~sql
SELECT ROUND(12.345)    AS rounded_integer,
       ROUND(12.345, 1) AS rounded_1_decimal,
       ROUND(12.345, 2) AS rounded_2_decimals,
       ROUND(12.345, 3) AS rounded_3_decimals
FROM dual;
~~~

Kết quả:

| ROUNDED_INTEGER | ROUNDED_1_DECIMAL | ROUNDED_2_DECIMALS | ROUNDED_3_DECIMALS |
|---:|---:|---:|---:|
| 12 | 12.3 | 12.35 | 12.345 |

Khi làm tròn đến hai chữ số, chữ số thứ ba là 5 nên kết quả 12.345 thành 12.35.

### 2.2 ROUND đến số nguyên và số âm

~~~sql
SELECT ROUND(2.1)  AS a,
       ROUND(2.5)  AS b,
       ROUND(2.9)  AS c,
       ROUND(-2.1) AS d,
       ROUND(-2.5) AS e,
       ROUND(-2.9) AS f
FROM dual;
~~~

Kết quả với NUMBER:

| Biểu thức | Kết quả |
|---|---:|
| ROUND(2.1) | 2 |
| ROUND(2.5) | 3 |
| ROUND(2.9) | 3 |
| ROUND(-2.1) | -2 |
| ROUND(-2.5) | -3 |
| ROUND(-2.9) | -3 |

Ở điểm đúng nửa đơn vị, ví dụ 2.5 và -2.5, cách làm tròn NUMBER của Oracle đi ra xa số 0. Đây là điểm cần nhớ khi xử lý số âm hoặc dữ liệu tài chính.

### 2.3 Đối số dương: làm tròn bên phải dấu thập phân

~~~sql
SELECT ROUND(123.4567, 0) AS p0,
       ROUND(123.4567, 1) AS p1,
       ROUND(123.4567, 2) AS p2,
       ROUND(123.4567, 3) AS p3
FROM dual;
~~~

| P0 | P1 | P2 | P3 |
|---:|---:|---:|---:|
| 123 | 123.5 | 123.46 | 123.457 |

### 2.4 Đối số âm: làm tròn bên trái dấu thập phân

~~~sql
SELECT ROUND(1234.56, -1) AS nearest_ten,
       ROUND(1234.56, -2) AS nearest_hundred,
       ROUND(1234.56, -3) AS nearest_thousand
FROM dual;
~~~

Kết quả lần lượt là 1230, 1200 và 1000.

~~~sql
SELECT ROUND(1249, -2) AS a,
       ROUND(1250, -2) AS b,
       ROUND(1251, -2) AS c
FROM dual;
~~~

Kết quả là 1200, 1300 và 1300. Với số âm:

~~~sql
SELECT ROUND(-1249, -2) AS a,
       ROUND(-1250, -2) AS b,
       ROUND(-1251, -2) AS c
FROM dual;
~~~

Kết quả là -1200, -1300 và -1300.

### 2.5 ROUND và định dạng hiển thị

~~~sql
SELECT ROUND(12.34567, 2) AS rounded_number,
       TO_CHAR(12.34567, 'FM9999990.00') AS formatted_text
FROM dual;
~~~

ROUND trả về giá trị số đã làm tròn. TO_CHAR trả về chuỗi theo format. Hai kết quả có thể trông giống nhau trên màn hình nhưng kiểu dữ liệu khác nhau. Nếu cần tính tiếp, giữ giá trị số; chỉ chuyển thành chuỗi ở bước hiển thị hoặc xuất báo cáo.

### 2.6 ROUND trong SELECT không cập nhật bảng

~~~sql
SELECT amount,
       ROUND(amount, 2) AS amount_rounded
FROM invoice_line;
~~~

Truy vấn chỉ tạo giá trị kết quả. Muốn ghi đè dữ liệu cần DML riêng:

~~~sql
UPDATE invoice_line
SET amount = ROUND(amount, 2);
~~~

UPDATE này thay đổi dữ liệu thật, có thể tác động đến audit, báo cáo và đối soát. Không chạy lệnh cập nhật diện rộng chỉ để xem kết quả của hàm.

## 3. TRUNC: cắt chữ số, hướng về 0

### 3.1 Cú pháp

~~~sql
TRUNC(number [, integer])
~~~

TRUNC loại bỏ các chữ số ngoài vị trí chỉ định, không làm tròn. Nếu bỏ đối số thứ hai, mặc định là 0.

~~~sql
SELECT TRUNC(12.9876)    AS t0,
       TRUNC(12.9876, 1) AS t1,
       TRUNC(12.9876, 2) AS t2,
       TRUNC(12.9876, 3) AS t3
FROM dual;
~~~

| T0 | T1 | T2 | T3 |
|---:|---:|---:|---:|
| 12 | 12.9 | 12.98 | 12.987 |

### 3.2 Số âm: TRUNC khác FLOOR

~~~sql
SELECT TRUNC(2.9) AS positive_value,
       TRUNC(-2.9) AS negative_value,
       FLOOR(-2.9) AS floored_value
FROM dual;
~~~

Kết quả lần lượt là 2, -2 và -3. TRUNC cắt về phía 0; FLOOR lấy số nguyên thấp hơn hoặc bằng giá trị.

### 3.3 Đối số âm của TRUNC

~~~sql
SELECT TRUNC(1234.567, -1) AS tens,
       TRUNC(1234.567, -2) AS hundreds,
       TRUNC(1234.567, -3) AS thousands
FROM dual;
~~~

Kết quả là 1230, 1200 và 1000. Ví dụ phân biệt với ROUND:

~~~sql
SELECT ROUND(1251, -2) AS rounded_hundred,
       TRUNC(1251, -2) AS truncated_hundred
FROM dual;
~~~

ROUND trả 1300; TRUNC trả 1200.

### 3.4 Ứng dụng

~~~sql
SELECT product_id,
       exact_quantity,
       TRUNC(exact_quantity, 0) AS whole_quantity
FROM inventory_measurement;
~~~

TRUNC có thể dùng khi quy tắc nghiệp vụ yêu cầu cắt phần lẻ hướng về 0. Nếu yêu cầu là làm tròn theo quy tắc đo lường, dùng ROUND; không tự thay thế hai quy tắc chỉ để kết quả trông gọn hơn.

### 3.5 TRUNC(number) và TRUNC(date)

Oracle có overload TRUNC cho cả NUMBER và DATE. Bài này tập trung vào số:

~~~sql
SELECT TRUNC(18.75, 1) AS numeric_truncation
FROM dual;
~~~

Nhưng:

~~~sql
SELECT TRUNC(SYSDATE) AS today_at_midnight
FROM dual;
~~~

dùng overload DATE để đưa thời gian về đầu ngày. Đối số thứ hai của TRUNC(DATE, fmt) là format model như 'MM' hoặc 'YYYY', không phải số chữ số thập phân. Kiểu đối số quyết định overload được gọi.

## 4. MOD: lấy phần dư

### 4.1 Cú pháp

~~~sql
MOD(n2, n1)
~~~

n2 là số bị chia; n1 là số chia. Ví dụ:

~~~sql
SELECT MOD(17, 5) AS remainder
FROM dual;
~~~

Vì 17 = 5 * 3 + 2 nên kết quả là 2.

### 4.2 Quy tắc của Oracle và số âm

Oracle định nghĩa MOD theo công thức:

~~~text
MOD(n2, n1) = n2 - n1 * FLOOR(n2 / n1)
~~~

Vì công thức dùng FLOOR, kết quả với số âm có thể khác toán tử remainder của Java, C hoặc các ngôn ngữ khác.

~~~sql
SELECT MOD(11, 4) AS a,
       MOD(-11, 4) AS b,
       MOD(11, -4) AS c,
       MOD(-11, -4) AS d
FROM dual;
~~~

Kết quả:

| A | B | C | D |
|---:|---:|---:|---:|
| 3 | 1 | -1 | -3 |

Giải thích:

- MOD(11,4) = 11 - 4 * FLOOR(2.75) = 3.
- MOD(-11,4) = -11 - 4 * FLOOR(-2.75) = 1.
- MOD(11,-4) = 11 - (-4) * FLOOR(-2.75) = -1.
- MOD(-11,-4) = -11 - (-4) * FLOOR(2.75) = -3.

### 4.3 Số chia bằng 0

Trong Oracle, MOD(n2, 0) trả về n2:

~~~sql
SELECT MOD(17, 0) AS result
FROM dual;
~~~

Kết quả là 17. Đây là quy tắc riêng của MOD; không thể suy ra phép chia 17 / 0 cũng hợp lệ. Trong ứng dụng, vẫn nên kiểm tra dữ liệu và xác định rõ trường hợp số chia bằng 0.

### 4.4 Chẵn/lẻ và chia nhóm

Với số nguyên không âm:

~~~sql
SELECT employee_id,
       MOD(employee_id, 2) AS parity
FROM staff;
~~~

MOD bằng 0 cho số chẵn, bằng 1 cho số lẻ. Nếu dữ liệu có số âm, hãy nhớ quy tắc MOD của Oracle; đừng áp dụng giả định từ toán tử % trong ngôn ngữ ứng dụng.

Ví dụ chia mã tác vụ vào bốn nhóm luân phiên:

~~~sql
SELECT task_id,
       MOD(task_id - 1, 4) + 1 AS worker_group
FROM task_queue;
~~~

Biểu thức phù hợp với ID dương và cách phân phối mong muốn. Nó không bảo đảm tải thực tế cân bằng nếu ID có khoảng trống hoặc dữ liệu đầu vào có pattern.

## 5. CEIL: lấy số nguyên trên

### 5.1 Cú pháp và ý nghĩa

~~~sql
CEIL(n)
~~~

CEIL trả về **số nguyên nhỏ nhất lớn hơn hoặc bằng n**. Có thể hình dung đó là số nguyên gần nhất ở phía trên hoặc trùng với giá trị trên trục số.

~~~sql
SELECT CEIL(2.1)  AS a,
       CEIL(2.9)  AS b,
       CEIL(2.0)  AS c,
       CEIL(-2.1) AS d,
       CEIL(-2.9) AS e
FROM dual;
~~~

Kết quả:

| A | B | C | D | E |
|---:|---:|---:|---:|---:|
| 3 | 3 | 2 | -2 | -2 |

CEIL(-2.1) là -2 vì -2 lớn hơn -2.1 và là số nguyên nhỏ nhất đáp ứng điều kiện. CEIL không có nghĩa là luôn tăng trị tuyệt đối.

### 5.2 Tính số trang

Một danh sách có 101 bản ghi, mỗi trang hiển thị 20 bản ghi:

~~~sql
SELECT CEIL(101 / 20) AS total_pages
FROM dual;
~~~

Kết quả là 6 trang. Năm trang đầu chứa 100 bản ghi, trang cuối chứa bản ghi còn lại. Đây là trường hợp phù hợp với CEIL vì số trang phải đủ để chứa toàn bộ dữ liệu.

Với dữ liệu động:

~~~sql
SELECT CEIL(total_rows / page_size) AS total_pages
FROM report_paging_config;
~~~

Phải bảo đảm PAGE_SIZE lớn hơn 0 và xử lý NULL theo chính sách. Không để phép tính phân trang phụ thuộc vào một mẫu số bằng 0 hoặc thiếu dữ liệu.

### 5.3 Tính số kiện/thùng cần cấp phát

Có 101 sản phẩm, mỗi thùng chứa tối đa 24 sản phẩm:

~~~sql
SELECT CEIL(101 / 24) AS boxes_needed
FROM dual;
~~~

Kết quả là 5 thùng. Bốn thùng chứa 96 sản phẩm, thùng cuối chứa 5 sản phẩm. CEIL phù hợp khi cần số đơn vị nguyên đủ sức chứa toàn bộ số lượng.

## 6. FLOOR: lấy số nguyên dưới

### 6.1 Cú pháp và ý nghĩa

~~~sql
FLOOR(n)
~~~

FLOOR trả về **số nguyên lớn nhất nhỏ hơn hoặc bằng n**.

~~~sql
SELECT FLOOR(2.1)  AS a,
       FLOOR(2.9)  AS b,
       FLOOR(2.0)  AS c,
       FLOOR(-2.1) AS d,
       FLOOR(-2.9) AS e
FROM dual;
~~~

Kết quả:

| A | B | C | D | E |
|---:|---:|---:|---:|---:|
| 2 | 2 | 2 | -3 | -3 |

Với số âm, FLOOR đi xuống theo trục số. -3 nhỏ hơn -2.1, còn -2 lớn hơn -2.1, nên FLOOR(-2.1) là -3.

### 6.2 Đếm số nhóm đầy đủ

Với 101 sản phẩm, mỗi thùng chứa 24 sản phẩm:

~~~sql
SELECT FLOOR(101 / 24) AS full_boxes,
       MOD(101, 24) AS remaining_items,
       CEIL(101 / 24) AS boxes_needed
FROM dual;
~~~

Kết quả:

| FULL_BOXES | REMAINING_ITEMS | BOXES_NEEDED |
|---:|---:|---:|
| 4 | 5 | 5 |

- FLOOR đếm số thùng đầy hoàn toàn.
- MOD đếm số sản phẩm còn lại sau các thùng đầy.
- CEIL đếm tổng số thùng cần cấp phát.

Đây là ví dụ kết hợp ba hàm để diễn đạt một yêu cầu nghiệp vụ.

### 6.3 FLOOR khác TRUNC với số âm

~~~sql
SELECT TRUNC(-2.7) AS truncated_value,
       FLOOR(-2.7) AS floored_value
FROM dual;
~~~

Kết quả là -2 và -3.

| Hàm | Quy tắc | Với -2.7 |
|---|---|---:|
| TRUNC | Cắt về phía 0 | -2 |
| FLOOR | Số nguyên lớn nhất không vượt quá n | -3 |
| CEIL | Số nguyên nhỏ nhất không thấp hơn n | -2 |

Không thay FLOOR bằng TRUNC khi tính số nhóm nguyên trong miền có thể có giá trị âm.

## 7. So sánh ROUND, TRUNC, CEIL và FLOOR

~~~sql
SELECT 2.7 AS input_value,
       ROUND(2.7) AS rounded,
       TRUNC(2.7) AS truncated,
       CEIL(2.7) AS ceiling,
       FLOOR(2.7) AS floor_value
FROM dual
UNION ALL
SELECT -2.7,
       ROUND(-2.7),
       TRUNC(-2.7),
       CEIL(-2.7),
       FLOOR(-2.7)
FROM dual;
~~~

Kết quả:

| INPUT_VALUE | ROUNDED | TRUNCATED | CEILING | FLOOR_VALUE |
|---:|---:|---:|---:|---:|
| 2.7 | 3 | 2 | 3 | 2 |
| -2.7 | -3 | -2 | -2 | -3 |

Có thể ghi nhớ theo mục tiêu:

| Nhu cầu | Hàm nên cân nhắc | Lý do |
|---|---|---|
| Làm tròn tiền đến 2 chữ số | ROUND(amount, 2) | Làm tròn theo chữ số tiếp theo |
| Cắt chữ số mà không tăng trị tuyệt đối | TRUNC(value, 2) | Hướng về 0 |
| Tính số trang hoặc số kiện cần dùng | CEIL(quantity / capacity) | Có phần lẻ thì cần thêm một đơn vị |
| Tính số nhóm đầy đủ | FLOOR(quantity / capacity) | Chỉ đếm phần nguyên hoàn chỉnh |
| Lấy phần dư/chẵn lẻ | MOD(value, divisor) | Tính phần dư theo quy tắc Oracle |
| Làm tròn đến hàng trăm gần nhất | ROUND(value, -2) | Đối số âm chỉ vị trí bên trái dấu thập phân |
| Cắt đến hàng nghìn | TRUNC(value, -3) | Bỏ các chữ số ngoài hàng nghìn |

## 8. Precision, scale và kiểu dữ liệu số

Oracle có các kiểu số thường gặp như NUMBER, BINARY_FLOAT và BINARY_DOUBLE. Kiểu dữ liệu đầu vào ảnh hưởng cách biểu diễn số và có thể ảnh hưởng kết quả tính toán.

### 8.1 NUMBER(p,s)

NUMBER(p,s) định nghĩa:

- p là precision, số chữ số có nghĩa tối đa.
- s là scale, số chữ số sau dấu thập phân; scale âm đặt độ chính xác ở bên trái dấu thập phân.

Ví dụ:

~~~sql
CREATE TABLE numeric_type_lab (
    amount_2dp NUMBER(12,2),
    rate_4dp   NUMBER(8,4),
    whole_no   NUMBER(8,0)
);
~~~

AMOUNT_2DP có scale 2; RATE_4DP có scale 4; WHOLE_NO có scale 0. Khi ghi một giá trị vào cột có scale giới hạn, Oracle áp dụng quy tắc chuyển giá trị sang kiểu đích, có thể làm tròn phần vượt scale. Nếu giá trị vượt precision, thao tác có thể báo lỗi.

### 8.2 ROUND trong biểu thức khác với scale cột

~~~sql
SELECT ROUND(123.456, 2) AS expression_value
FROM dual;
~~~

Biểu thức trả về một giá trị số đã làm tròn đến hai chữ số. Trong khi đó:

~~~sql
CREATE TABLE amount_store_lab (
    amount NUMBER(8,2)
);
~~~

định nghĩa cột có scale 2. Kiểu cột kiểm soát việc lưu trữ; hàm ROUND thể hiện quy tắc tính toán tại vị trí được gọi. Không nên dựa vào scale cột để thay thế quy tắc làm tròn nghiệp vụ trong SQL hoặc ứng dụng.

### 8.3 Dùng NUMBER cho dữ liệu tiền tệ

~~~sql
CREATE TABLE invoice_amount_lab (
    invoice_id NUMBER PRIMARY KEY,
    amount     NUMBER(14,2) NOT NULL
);
~~~

NUMBER là kiểu số thập phân phù hợp với nhiều bài toán tiền tệ cần quy tắc decimal rõ ràng. BINARY_FLOAT và BINARY_DOUBLE lưu số theo dạng floating-point nhị phân; một số phân số thập phân như 0.1 không có biểu diễn nhị phân hữu hạn chính xác. Vì vậy phép tính có thể chứa sai số xấp xỉ.

Nếu nghiệp vụ yêu cầu tính tiền chính xác theo scale đã quy định, nên dùng NUMBER với precision/scale phù hợp và xác định bước làm tròn. Floating-point phù hợp với những bài toán chấp nhận sai số xấp xỉ và cần đặc tính tính toán tương ứng.

### 8.4 Phân biệt giá trị số và chuỗi hiển thị

~~~sql
SELECT amount,
       ROUND(amount, 2) AS rounded_amount,
       TO_CHAR(amount, 'FM9999990.000000') AS display_six_places
FROM invoice_line;
~~~

Có ba thứ khác nhau:

1. Giá trị số gốc AMOUNT.
2. Giá trị số mới do ROUND trả về.
3. Chuỗi do TO_CHAR định dạng.

Định dạng hiển thị sáu chữ số không làm giá trị lưu trữ tự có scale 6; tương tự, TO_CHAR với hai chữ số không thay đổi số gốc.

## 9. Làm tròn từng dòng hay sau khi tổng hợp?

Hai biểu thức dưới đây không luôn cho kết quả giống nhau:

~~~sql
SUM(ROUND(line_amount, 2))
ROUND(SUM(line_amount), 2)
~~~

Ví dụ ba dòng, mỗi dòng có số tiền 0.005:

~~~sql
SELECT SUM(ROUND(amount, 2)) AS sum_rounded_lines,
       ROUND(SUM(amount), 2) AS rounded_total
FROM (
    SELECT 0.005 AS amount FROM dual
    UNION ALL
    SELECT 0.005 FROM dual
    UNION ALL
    SELECT 0.005 FROM dual
);
~~~

Với NUMBER:

- Mỗi dòng ROUND(0.005,2) thành 0.01; tổng ba dòng đã làm tròn là 0.03.
- Tổng giá trị gốc là 0.015; làm tròn tổng đến hai chữ số là 0.02.

Hai kết quả khác nhau: 0.03 và 0.02. Đây là hai chính sách tính toán khác nhau, không phải lỗi Oracle.

Trong nghiệp vụ hóa đơn/thuế, quy định có thể yêu cầu làm tròn từng dòng, theo từng loại thuế, theo từng chứng từ hoặc chỉ ở tổng cuối. Phải thống nhất quy tắc giữa database, backend, hệ thống thanh toán và báo cáo. Cần kiểm thử cả giá trị âm, hoàn tiền và trường hợp đúng ngưỡng nửa đơn vị.

## 10. NULL và chuyển kiểu

### 10.1 Đối số NULL

~~~sql
SELECT ROUND(CAST(NULL AS NUMBER), 2) AS round_null,
       TRUNC(CAST(NULL AS NUMBER), 2) AS trunc_null,
       MOD(CAST(NULL AS NUMBER), 3) AS mod_null,
       CEIL(CAST(NULL AS NUMBER)) AS ceil_null,
       FLOOR(CAST(NULL AS NUMBER)) AS floor_null
FROM dual;
~~~

CAST(NULL AS NUMBER) làm rõ kiểu số của giá trị NULL. Khi đối số cần thiết là NULL, kết quả hàm số thông thường là NULL. Hãy quyết định NULL mang nghĩa “chưa biết”, “không áp dụng” hay một giá trị mặc định được nghiệp vụ cho phép.

### 10.2 NVL và COALESCE

~~~sql
SELECT amount,
       ROUND(NVL(amount, 0), 2) AS rounded_or_zero
FROM invoice_line;
~~~

Nếu AMOUNT là NULL, kết quả được thay bằng 0 trước khi làm tròn. Đây là chính sách thay thế dữ liệu. Không dùng NVL chỉ để tránh nhìn thấy NULL nếu NULL thực sự có nghĩa là “chưa xác định”.

### 10.3 Tránh implicit conversion từ chuỗi

Không nên dựa vào chuyển kiểu ngầm:

~~~sql
SELECT ROUND('12.345', 2)
FROM dual;
~~~

Kết quả phụ thuộc khả năng chuyển chuỗi sang NUMBER và các quy tắc định dạng liên quan. Nếu đầu vào thực sự là chuỗi, chuyển kiểu rõ ràng:

~~~sql
SELECT ROUND(TO_NUMBER('12.345', '9999990D999'), 2)
FROM dual;
~~~

Với format model có dấu thập phân hoặc hàng nghìn, cần thống nhất NLS. Trong ứng dụng, tốt hơn là bind giá trị NUMBER thay vì gửi chuỗi số để Oracle tự đoán.

### 10.4 Kiểu kết quả

Các hàm này trả về giá trị số. Kiểu kết quả chịu ảnh hưởng của kiểu đối số và quy tắc numeric precedence của Oracle. Khi kết hợp NUMBER với BINARY_FLOAT hoặc BINARY_DOUBLE, biểu thức có thể được nâng lên kiểu có precedence cao hơn.

Khi thiết kế view, API hoặc bảng kết quả, hãy kiểm tra metadata và mapping của driver, nhất là khi kết hợp số thập phân tài chính với floating-point.

## 11. Ứng dụng thực tế

### 11.1 Tính số trang

~~~sql
SELECT CEIL(257 / 25) AS total_pages
FROM dual;
~~~

Kết quả là 11 trang nếu mỗi trang chứa tối đa 25 bản ghi. Khi dùng dữ liệu động, kiểm tra PAGE_SIZE lớn hơn 0 và xử lý NULL trước khi tính.

### 11.2 Tính số kiện và phần dư

~~~sql
SELECT product_id,
       quantity,
       FLOOR(quantity / 24) AS full_cases,
       MOD(quantity, 24) AS loose_units,
       CEIL(quantity / 24) AS cases_required
FROM warehouse_stock;
~~~

Giả sử quantity không âm và mỗi kiện chứa 24 đơn vị:

- FLOOR tính số kiện đủ 24 sản phẩm.
- MOD tính số sản phẩm còn lại.
- CEIL tính tổng số kiện cần cấp phát.

Nếu quantity có thể âm do điều chỉnh kho, cần định nghĩa nghiệp vụ riêng; không diễn giải máy móc kết quả âm thành số kiện.

### 11.3 Tính tỷ lệ phần trăm

~~~sql
SELECT department_id,
       actual_sales,
       target_sales,
       ROUND(
         actual_sales / NULLIF(target_sales, 0) * 100,
         2
       ) AS achievement_percent
FROM department_sales;
~~~

NULLIF(target_sales,0) tránh chia cho 0. Nếu target bằng 0, tỷ lệ trả về NULL; báo cáo có thể hiển thị N/A thay vì tự gán 0%.

### 11.4 Làm tròn hoặc cắt khối lượng

~~~sql
SELECT item_id,
       measured_weight,
       ROUND(measured_weight, 3) AS rounded_weight,
       TRUNC(measured_weight, 3) AS truncated_weight
FROM shipment_item;
~~~

ROUND và TRUNC có thể tạo kết quả khác nhau. Phải theo quy tắc đo lường/thanh toán; không chọn TRUNC chỉ vì muốn tránh làm tròn lên nếu quy định yêu cầu ROUND.

### 11.5 Chia dữ liệu vào nhóm luân phiên

~~~sql
SELECT task_id,
       MOD(task_id - 1, 4) + 1 AS worker_group
FROM task_queue;
~~~

Với ID dương và liên tiếp, biểu thức tạo nhóm 1, 2, 3, 4 rồi lặp lại. Nếu ID có khoảng trống hoặc dữ liệu có pattern, các nhóm có thể không cân bằng. Với workload production, phải đo phân bố thực tế.

### 11.6 Cắt hoặc làm tròn doanh thu đến hàng nghìn

~~~sql
SELECT branch_id,
       revenue,
       TRUNC(revenue, -3) AS revenue_thousand_truncated,
       ROUND(revenue, -3) AS revenue_thousand_rounded
FROM branch_revenue;
~~~

Với doanh thu 1.234.567, TRUNC đến hàng nghìn trả 1.234.000; ROUND trả 1.235.000. Alias giúp người đọc hiểu rõ cách xử lý.

## 12. DUAL để kiểm tra nhanh

DUAL là bảng hệ thống đặc biệt có một dòng, thường dùng để đánh giá biểu thức không cần đọc dữ liệu nghiệp vụ.

~~~sql
SELECT ROUND(12.345, 2) AS round_result,
       TRUNC(12.345, 2) AS trunc_result,
       MOD(17, 5) AS mod_result,
       CEIL(12.1) AS ceil_result,
       FLOOR(12.9) AS floor_result
FROM dual;
~~~

Kết quả có một dòng với năm cột. DUAL hữu ích để thử cú pháp, xác nhận quy tắc số âm hoặc so sánh các biểu thức trước khi đưa vào truy vấn bảng lớn.

Kiểm tra cả số âm:

~~~sql
SELECT ROUND(-2.5) AS rounded_negative,
       TRUNC(-2.5) AS truncated_negative,
       CEIL(-2.5) AS ceil_negative,
       FLOOR(-2.5) AS floor_negative,
       MOD(-11, 4) AS mod_negative
FROM dual;
~~~

Kết quả lần lượt là -3, -2, -2, -3 và 1.

Không INSERT, UPDATE hoặc DELETE vào SYS.DUAL để thực hành. Hãy dùng SELECT từ DUAL hoặc tạo bảng riêng trong schema lab nếu cần nhiều dòng.

## 13. Thực hành với bảng số liệu riêng

Các lệnh sau dành cho schema thực hành riêng có quyền tạo bảng và quota phù hợp. Không chạy DDL/DML thử nghiệm trên schema sản xuất. CREATE TABLE là DDL có implicit commit.

### 13.1 Tạo bảng và nạp dữ liệu

~~~sql
CREATE TABLE lab_numeric_values (
    value_id     NUMBER PRIMARY KEY,
    description  VARCHAR2(50) NOT NULL,
    amount       NUMBER(12,4),
    divisor      NUMBER(8,2)
);

INSERT INTO lab_numeric_values VALUES
    (1, 'POSITIVE_FRACTION', 12.3456, 5);
INSERT INTO lab_numeric_values VALUES
    (2, 'NEGATIVE_FRACTION', -12.3456, 4);
INSERT INTO lab_numeric_values VALUES
    (3, 'ROUNDING_BOUNDARY', 12.3450, 2);
INSERT INTO lab_numeric_values VALUES
    (4, 'ZERO', 0, 3);
INSERT INTO lab_numeric_values VALUES
    (5, 'NULL_AMOUNT', NULL, 5);
INSERT INTO lab_numeric_values VALUES
    (6, 'LARGE_VALUE', 1251, 100);

COMMIT;
~~~

### 13.2 Chạy các hàm trên từng hàng

~~~sql
SELECT value_id,
       description,
       amount,
       ROUND(amount, 2) AS amount_rounded,
       TRUNC(amount, 2) AS amount_truncated,
       CEIL(amount) AS amount_ceil,
       FLOOR(amount) AS amount_floor,
       MOD(amount, divisor) AS amount_mod
FROM lab_numeric_values
ORDER BY value_id;
~~~

Quan sát:

- Dòng số dương cho thấy ROUND và TRUNC khác nhau khi cần tăng chữ số cuối.
- Dòng số âm giúp thấy CEIL và FLOOR đi theo hai hướng khác nhau.
- Dòng NULL cho thấy các biểu thức phụ thuộc AMOUNT trả NULL.
- Dòng LARGE_VALUE dùng để thử ROUND/TRUNC với đối số âm.

### 13.3 So sánh đến hàng trăm

~~~sql
SELECT amount,
       ROUND(amount, -2) AS nearest_hundred,
       TRUNC(amount, -2) AS cut_to_hundred
FROM lab_numeric_values
WHERE value_id = 6;
~~~

Với 1.251, kết quả lần lượt là 1.300 và 1.200.

### 13.4 Đối chiếu tổng tiền

~~~sql
SELECT SUM(ROUND(amount, 2)) AS sum_after_line_rounding,
       ROUND(SUM(amount), 2) AS round_after_sum
FROM lab_numeric_values
WHERE amount IS NOT NULL;
~~~

Hai kết quả có thể khác nhau. Hãy giải thích bằng thứ tự làm tròn và tổng hợp, không coi một kết quả là lỗi.

Chỉ xóa bảng do bạn tạo trong schema lab khi đã xác nhận không còn cần dữ liệu. Không đặt DROP TABLE vào script có thể chạy nhầm production; ROLLBACK không thể hoàn tác DDL đã commit.

## 14. Hiệu năng và vị trí sử dụng hàm

### 14.1 Hàm trong SELECT list

~~~sql
SELECT order_id,
       ROUND(total_amount, 2) AS rounded_total
FROM orders;
~~~

Oracle tính biểu thức cho các dòng được truy vấn để tạo kết quả. Nếu bảng rất lớn, việc tính biểu thức trên nhiều dòng vẫn có chi phí CPU.

### 14.2 Hàm trên cột trong WHERE

~~~sql
SELECT order_id
FROM orders
WHERE TRUNC(total_amount) = 100;
~~~

Nếu có B-tree index thường trên TOTAL_AMOUNT, biểu thức TRUNC(total_amount) có thể khiến index đó khó được sử dụng trực tiếp như predicate range trên cột gốc. Có thể cân nhắc:

~~~sql
WHERE total_amount >= 100
  AND total_amount < 101
~~~

Hai điều kiện chỉ tương đương khi miền dữ liệu và ngữ nghĩa so sánh phù hợp. Với số âm, TRUNC hướng về 0 nên không được thay predicate một cách máy móc. Hãy xác định miền dữ liệu và kiểm tra execution plan.

Nếu truy vấn thường xuyên lọc theo biểu thức, function-based index có thể là phương án:

~~~sql
CREATE INDEX idx_orders_trunc_total
ON orders (TRUNC(total_amount));
~~~

Đây là DDL thay đổi cấu trúc và có chi phí lưu trữ/bảo trì. Chỉ cân nhắc sau khi xem workload, quyền và execution plan; không tạo index production chỉ để thử cú pháp.

### 14.3 Xem execution plan

~~~sql
EXPLAIN PLAN FOR
SELECT order_id,
       ROUND(total_amount, 2) AS rounded_total
FROM orders
WHERE total_amount >= 100
  AND total_amount < 101;

SELECT *
FROM TABLE(DBMS_XPLAN.DISPLAY);
~~~

EXPLAIN PLAN hiển thị kế hoạch dự kiến, không đo thời gian hay xác nhận số hàng thực tế. Khi tuning cần xem actual plan, cardinality, access predicates, CPU/I/O và phân bố dữ liệu.

## 15. NULL, lỗi và ngộ nhận thường gặp

| Ngộ nhận/lỗi | Thực tế | Cách xử lý |
|---|---|---|
| ROUND và TRUNC giống nhau | ROUND làm tròn, TRUNC cắt về 0 | Thử giá trị ngay dưới/trên ngưỡng |
| TRUNC(-2.7) = -3 | TRUNC(-2.7) = -2 | Dùng FLOOR nếu cần số nguyên thấp hơn |
| FLOOR(-2.7) = -2 | FLOOR(-2.7) = -3 | Hiểu FLOOR theo trục số |
| CEIL luôn tăng trị tuyệt đối | CEIL(-2.7) = -2 | CEIL là số nguyên nhỏ nhất không nhỏ hơn n |
| MOD giống toán tử % ở mọi ngôn ngữ | Oracle dùng FLOOR và có quy tắc riêng cho số âm | Thử các tổ hợp dấu |
| MOD với divisor 0 luôn báo lỗi | MOD(n2,0) trả n2 | Vẫn kiểm tra dữ liệu đầu vào |
| ROUND thay đổi dữ liệu bảng | SELECT ROUND chỉ tạo giá trị kết quả | UPDATE mới thay đổi dữ liệu |
| TO_CHAR làm tròn số lưu trữ | TO_CHAR tạo chuỗi hiển thị | Phân biệt formatting và numeric calculation |
| ROUND từng dòng luôn bằng ROUND tổng | Thứ tự làm tròn và cộng có thể tạo chênh lệch | Theo quy tắc nghiệp vụ |
| NULL tự động được xem là 0 | NULL truyền qua biểu thức số thường cho kết quả NULL | Dùng NVL/COALESCE khi được phép |
| NUMBER và BINARY_DOUBLE luôn giống nhau | Floating-point nhị phân có thể biểu diễn xấp xỉ | Dùng NUMBER cho số thập phân tài chính |
| ROUND(x,-2) làm tròn hai chữ số thập phân | Đối số âm chỉ vị trí bên trái dấu thập phân | Thử ví dụ hàng chục/hàng trăm |
| TRUNC luôn là TRUNC(number) | Oracle còn có TRUNC(date) | Xem kiểu đối số và overload |

Nếu dữ liệu đầu vào là chuỗi không hợp lệ, TO_NUMBER có thể phát sinh lỗi chuyển đổi. Không để chuỗi như '12,34' đi vào phép ROUND mà không xác định dấu thập phân và NLS. Hãy kiểm tra format đầu vào, bind NUMBER và xử lý dữ liệu lỗi ở biên nhập.

Khi ghi vào cột có precision giới hạn, giá trị vượt phạm vi có thể gây lỗi dù đã dùng ROUND. Thiết kế NUMBER(p,s) phải phù hợp miền giá trị; kiểm thử cả giá trị cực đại và cực tiểu.

## 16. Bài tập tự luyện

**Câu 1.** Dự đoán:

~~~sql
SELECT ROUND(8.765, 2),
       TRUNC(8.765, 2)
FROM dual;
~~~

Gợi ý: ROUND cho 8.77; TRUNC cho 8.76.

**Câu 2.** Dự đoán:

~~~sql
SELECT ROUND(-3.5),
       TRUNC(-3.5),
       CEIL(-3.5),
       FLOOR(-3.5)
FROM dual;
~~~

Gợi ý: -4, -3, -3 và -4.

**Câu 3.** Vì sao TRUNC(-8.9) khác FLOOR(-8.9)?

Gợi ý: TRUNC cắt về phía 0 nên bằng -8; FLOOR lấy số nguyên thấp hơn nên bằng -9.

**Câu 4.** Tính MOD(-13,5) theo công thức Oracle.

Gợi ý: -13 - 5 * FLOOR(-13/5) = -13 - 5*(-3) = 2.

**Câu 5.** Cần 73 sản phẩm, mỗi thùng chứa 12 sản phẩm. Viết SQL tính số thùng đầy, số hàng lẻ và tổng số thùng.

~~~sql
SELECT FLOOR(73 / 12) AS full_boxes,
       MOD(73, 12) AS remaining_units,
       CEIL(73 / 12) AS boxes_required
FROM dual;
~~~

Kết quả là 6, 1 và 7.

**Câu 6.** Một báo cáo có ba dòng 0.005. Vì sao SUM(ROUND(amount,2)) khác ROUND(SUM(amount),2)?

Gợi ý: Làm tròn từng dòng tạo ba giá trị 0.01 rồi cộng thành 0.03; cộng số gốc trước tạo 0.015 rồi làm tròn thành 0.02. Phải theo chính sách tài chính.

**Câu 7.** Khi nào nên dùng NUMBER thay vì BINARY_DOUBLE?

Gợi ý: Khi cần số thập phân chính xác theo quy tắc tài chính/đơn vị, NUMBER thường phù hợp hơn. BINARY_DOUBLE phù hợp với tính toán floating-point khi sai số xấp xỉ được chấp nhận.

**Câu 8.** ROUND(12345, -3) và TRUNC(12345, -3) cho kết quả nào?

Gợi ý: Cả hai là 12000. Thử 12501 để thấy ROUND là 13000 còn TRUNC là 12000.

**Câu 9.** Điều gì cần lưu ý khi dùng MOD(n,2) để chia nhóm nếu n có thể âm?

Gợi ý: MOD của Oracle dùng FLOOR; không áp dụng máy móc giả định remainder của Java/C.

**Câu 10.** TO_CHAR(ROUND(amount,2), 'FM9990.00') và ROUND(amount,2) khác nhau về kiểu gì?

Gợi ý: ROUND trả giá trị số; TO_CHAR trả chuỗi được định dạng.

## 17. Quy trình chọn hàm phù hợp

Trước khi viết biểu thức, hãy xác định yêu cầu:

1. Muốn giá trị gần nhất? Dùng ROUND và xác định số chữ số.
2. Muốn cắt bỏ chữ số, luôn hướng về 0? Dùng TRUNC.
3. Muốn số nguyên trên để đủ sức chứa hoặc đủ số trang? Dùng CEIL.
4. Muốn số nguyên dưới để đếm số nhóm đầy đủ? Dùng FLOOR.
5. Muốn phần dư hoặc kiểm tra chu kỳ? Dùng MOD và xác nhận ngữ nghĩa với số âm.
6. Dữ liệu có NULL không? Xác định ý nghĩa NULL trước khi thay bằng 0.
7. Kiểu số có phù hợp không? Dùng NUMBER cho dữ liệu thập phân chính xác khi cần; kiểm tra precision/scale của cột đích.
8. Kết quả chỉ để hiển thị hay còn tính tiếp? Giữ numeric type cho tính toán; chỉ TO_CHAR ở bước trình bày.

## 18. Tổng kết

Năm hàm số của Oracle giải quyết các nhu cầu khác nhau:

- ROUND(n, p) làm tròn theo vị trí p; p dương là bên phải dấu thập phân, p âm là bên trái.
- TRUNC(n, p) cắt chữ số theo hướng về 0, không làm tròn. Với số âm, kết quả khác FLOOR.
- MOD(n2, n1) lấy phần dư theo công thức dùng FLOOR; số âm có thể cho kết quả khác toán tử remainder trong ngôn ngữ ứng dụng.
- CEIL(n) lấy số nguyên nhỏ nhất không nhỏ hơn n.
- FLOOR(n) lấy số nguyên lớn nhất không lớn hơn n.

Khi dùng trong hệ thống thực tế, cần chú ý NULL, kiểu NUMBER so với floating-point, precision/scale, thời điểm làm tròn theo quy tắc nghiệp vụ và tác động của hàm lên predicate/index. Dùng DUAL để kiểm tra nhanh các giá trị biên, nhất là số âm và trường hợp chia hết, trước khi áp dụng lên dữ liệu thật. Chọn đúng hàm giúp biểu thức SQL dễ đọc, kết quả có thể giải thích và các phép tính trong báo cáo/ứng dụng nhất quán.
