# COUNT(*), COUNT(cột), SUM, AVG, MIN và MAX trong Oracle Database

Các hàm tổng hợp (*aggregate functions*) biến nhiều hàng dữ liệu thành một hoặc nhiều kết quả thống kê. Trong Oracle Database, sáu cách tính thường gặp là:

- **`COUNT(*)`**: đếm số hàng.
- **`COUNT(expression)`**: đếm số hàng mà biểu thức không phải `NULL`.
- **`SUM(expression)`**: tính tổng các giá trị số không-NULL.
- **`AVG(expression)`**: tính trung bình các giá trị số không-NULL.
- **`MIN(expression)`**: lấy giá trị nhỏ nhất theo quy tắc so sánh của kiểu dữ liệu.
- **`MAX(expression)`**: lấy giá trị lớn nhất theo quy tắc so sánh của kiểu dữ liệu.

Điểm quan trọng nhất khi dùng các hàm này là hiểu **NULL được xử lý thế nào**. Ví dụ, `COUNT(*)` vẫn đếm hàng dù một số cột trong hàng là NULL; `COUNT(amount)` bỏ qua hàng có `AMOUNT=NULL`; còn `AVG(amount)` chỉ chia cho số giá trị amount thực sự có mặt. Nếu không nắm rõ điều đó, báo cáo số lượng, tổng tiền và trung bình có thể khác với ý nghĩa nghiệp vụ.

Bài học này giải thích cách dùng từng hàm, kết hợp với `GROUP BY` và `HAVING`, đếm có điều kiện, xử lý tập kết quả rỗng, các tình huống join làm nhân bản hàng và cách đọc kết quả trong báo cáo Oracle.

## 1. Hàm tổng hợp là gì?

### 1.1. Từ nhiều hàng thành một kết quả

Giả sử bảng bán hàng có các giá trị:

```text
SALE_ID    AMOUNT
-------    ------
1          1000
2          1500
3          1000
4          NULL
5          3000
```

Các hàm tổng hợp trả về thông tin tóm tắt:

| Biểu thức | Kết quả | Ý nghĩa |
| --- | ---: | --- |
| `COUNT(*)` | 5 | Có 5 hàng |
| `COUNT(amount)` | 4 | Có 4 hàng có amount không-NULL |
| `SUM(amount)` | 6500 | Tổng 1000 + 1500 + 1000 + 3000 |
| `AVG(amount)` | 1625 | Tổng 6500 chia cho 4 giá trị có mặt |
| `MIN(amount)` | 1000 | Giá trị nhỏ nhất |
| `MAX(amount)` | 3000 | Giá trị lớn nhất |

`COUNT(*)` trả về số hàng trong tập đầu vào. Các hàm còn lại trong ví dụ bỏ qua `NULL` ở biểu thức được tính.

### 1.2. Hàm tổng hợp không nhất thiết trả một hàng cho mỗi hàng đầu vào

Không có `GROUP BY`, một câu truy vấn tổng hợp thường trả về **một hàng kết quả** cho toàn bộ tập đầu vào:

```sql
SELECT COUNT(*) AS row_count,
       SUM(amount) AS total_amount,
       AVG(amount) AS average_amount
FROM   sales;
```

Nếu thêm `GROUP BY`, Oracle tính riêng cho từng nhóm:

```sql
SELECT region,
       COUNT(*) AS sale_count,
       SUM(amount) AS total_amount
FROM   sales
GROUP  BY region;
```

Ví dụ sau trả về một dòng cho mỗi vùng có ít nhất một hàng trong tập đầu vào. Phần `NULL` ở cột `REGION` cũng tạo thành một nhóm riêng nếu có dữ liệu như vậy.

### 1.3. Phân biệt hàm tổng hợp và hàm trên từng hàng

Hàm trên từng hàng (scalar function) nhận đầu vào từ một hàng và trả kết quả cho hàng đó, ví dụ `UPPER(name)` hoặc `ROUND(amount, 2)`. Hàm tổng hợp nhận nhiều hàng và trả một kết quả cho cả tập hoặc cho từng nhóm.

Có thể dùng scalar function bên trong aggregate:

```sql
SELECT SUM(ROUND(amount, 2)) AS total_rounded
FROM   sales;
```

Ở đây `ROUND` được áp dụng cho từng giá trị amount trước khi `SUM` tổng hợp. Thứ tự áp dụng hàm có thể làm thay đổi kết quả; cần chọn theo ý nghĩa nghiệp vụ.

## 2. Dữ liệu mẫu để thực hành

Các ví dụ sau sử dụng bảng `DEMO_SALES`. Tạo bảng trong schema thử nghiệm:

```sql
CREATE TABLE demo_sales (
    sale_id     NUMBER(10) PRIMARY KEY,
    region      VARCHAR2(30),
    salesperson VARCHAR2(50),
    amount      NUMBER(12,2),
    status      VARCHAR2(20) NOT NULL,
    sold_at     DATE NOT NULL
);
```

Thêm dữ liệu:

```sql
INSERT INTO demo_sales VALUES (
    1, 'NORTH', 'An', 1000,
    'PAID', DATE '2026-11-01'
);

INSERT INTO demo_sales VALUES (
    2, 'NORTH', 'An', 1500,
    'PAID', DATE '2026-11-02'
);

INSERT INTO demo_sales VALUES (
    3, 'NORTH', 'Binh', 1000,
    'PENDING', DATE '2026-11-03'
);

INSERT INTO demo_sales VALUES (
    4, 'SOUTH', 'Chi', 2000,
    'PAID', DATE '2026-11-04'
);

INSERT INTO demo_sales VALUES (
    5, 'SOUTH', 'Chi', NULL,
    'PENDING', DATE '2026-11-05'
);

INSERT INTO demo_sales VALUES (
    6, 'SOUTH', 'Dung', 3000,
    'PAID', DATE '2026-11-06'
);

INSERT INTO demo_sales VALUES (
    7, 'EAST', 'An', NULL,
    'CANCELLED', DATE '2026-11-07'
);

INSERT INTO demo_sales VALUES (
    8, 'EAST', 'Binh', 500,
    'PAID', DATE '2026-11-08'
);

INSERT INTO demo_sales VALUES (
    9, 'EAST', 'Binh', 500,
    'PAID', DATE '2026-11-09'
);

INSERT INTO demo_sales VALUES (
    10, NULL, 'Ema', 700,
    'PAID', DATE '2026-11-10'
);

COMMIT;
```

Bảng có 10 hàng; hai hàng có `AMOUNT=NULL`; giá trị 500 xuất hiện hai lần. Đây là dữ liệu có chủ đích để thấy sự khác biệt giữa đếm hàng, đếm giá trị không-NULL và đếm giá trị phân biệt.

| SALE_ID | REGION | SALESPERSON | AMOUNT | STATUS |
| ---: | --- | --- | ---: | --- |
| 1 | NORTH | An | 1.000 | PAID |
| 2 | NORTH | An | 1.500 | PAID |
| 3 | NORTH | Binh | 1.000 | PENDING |
| 4 | SOUTH | Chi | 2.000 | PAID |
| 5 | SOUTH | Chi | NULL | PENDING |
| 6 | SOUTH | Dung | 3.000 | PAID |
| 7 | EAST | An | NULL | CANCELLED |
| 8 | EAST | Binh | 500 | PAID |
| 9 | EAST | Binh | 500 | PAID |
| 10 | NULL | Ema | 700 | PAID |

## 3. COUNT(*): đếm số hàng

### 3.1. Cú pháp và ví dụ

```sql
SELECT COUNT(*) AS total_sales
FROM   demo_sales;
```

Kết quả:

```text
TOTAL_SALES
-----------
10
```

`COUNT(*)` đếm **mọi hàng** trong tập kết quả sau khi áp dụng các điều kiện `FROM`, `JOIN` và `WHERE`. Nó không kiểm tra từng cột có NULL hay không.

Ví dụ:

```sql
SELECT COUNT(*) AS north_sales
FROM   demo_sales
WHERE  region = 'NORTH';
```

Kết quả là **3** vì có ba hàng thuộc NORTH.

### 3.2. COUNT(*) vẫn đếm hàng có cột NULL

```sql
SELECT COUNT(*) AS total_rows,
       COUNT(amount) AS rows_with_amount
FROM   demo_sales;
```

Kết quả:

| TOTAL_ROWS | ROWS_WITH_AMOUNT |
| ---: | ---: |
| 10 | 8 |

Hai hàng ID 5 và 7 có amount NULL nhưng vẫn là hàng tồn tại, nên `COUNT(*)` tính cả hai.

Đây là câu hỏi cần phân biệt:

- “Có bao nhiêu giao dịch?” → thường dùng `COUNT(*)`.
- “Có bao nhiêu giao dịch đã có giá trị amount?” → dùng `COUNT(amount)`.

### 3.3. COUNT(1) và COUNT(*)

Trong Oracle, `COUNT(1)` đếm số hàng vì biểu thức hằng số 1 không bao giờ NULL. Về ý nghĩa kết quả, nó tương đương `COUNT(*)` trong truy vấn thông thường:

```sql
SELECT COUNT(*) AS count_star,
       COUNT(1) AS count_one
FROM   demo_sales;
```

Hai kết quả đều bằng 10. `COUNT(1)` không phải mẹo tối ưu hiệu năng đáng tin cậy so với `COUNT(*)`. Khi muốn đếm hàng, dùng `COUNT(*)` vì nó thể hiện đúng ý định và không khiến người đọc nghĩ rằng đang đếm một cột cụ thể.

### 3.4. COUNT(*) sau JOIN đếm hàng của kết quả JOIN

Nếu một khách hàng có ba đơn hàng, khi join bảng khách hàng với bảng đơn hàng, khách hàng đó xuất hiện ba dòng trong tập kết quả. `COUNT(*)` khi ấy đếm **ba dòng kết quả join**, không phải một khách hàng duy nhất.

Ví dụ tổng quát:

```sql
SELECT COUNT(*) AS joined_rows
FROM   customers c
JOIN   orders o
       ON o.customer_id = c.customer_id;
```

Nếu mục tiêu là đếm khách hàng có ít nhất một đơn, có thể dùng:

```sql
SELECT COUNT(DISTINCT c.customer_id) AS customers_with_orders
FROM   customers c
JOIN   orders o
       ON o.customer_id = c.customer_id;
```

Hoặc dùng `EXISTS` để thể hiện ý định kiểm tra sự tồn tại. Luôn xác định **đơn vị cần đếm**: hàng kết quả, đơn hàng, khách hàng hay một thực thể nghiệp vụ khác.

## 4. COUNT(expression): đếm biểu thức không NULL

### 4.1. Cú pháp

```sql
COUNT(expression)
```

Hàm đếm số hàng mà `expression` đánh giá thành giá trị **khác NULL**. Biểu thức có thể là một cột, phép tính hoặc `CASE`.

Ví dụ:

```sql
SELECT COUNT(amount) AS known_amount_count,
       COUNT(region) AS known_region_count,
       COUNT(salesperson) AS known_salesperson_count
FROM   demo_sales;
```

Theo dữ liệu mẫu:

| Biểu thức | Kết quả | Vì sao |
| --- | ---: | --- |
| `COUNT(amount)` | 8 | Hai hàng amount NULL |
| `COUNT(region)` | 9 | Một hàng region NULL |
| `COUNT(salesperson)` | 10 | Cả mười hàng có salesperson |

### 4.2. COUNT(expression) không đếm số khác 0

Giả sử cột `AMOUNT` có các giá trị 0, 100 và NULL:

- `COUNT(amount)` đếm 0 và 100, kết quả 2.
- `COUNT(amount)` bỏ qua NULL, không bỏ qua số 0.

Nếu nghiệp vụ muốn đếm amount lớn hơn 0, phải thêm điều kiện:

```sql
SELECT COUNT(*) AS positive_amount_count
FROM   demo_sales
WHERE  amount > 0;
```

Không dùng `COUNT(amount)` thay cho việc kiểm tra giá trị dương/âm/0.

### 4.3. COUNT trên biểu thức

```sql
SELECT COUNT(amount * 2) AS count_calculated_amount
FROM   demo_sales;
```

Nếu `AMOUNT` là NULL, phép nhân cũng trả NULL nên hàng đó không được đếm. Nếu biểu thức không phải NULL ở mọi hàng, `COUNT(expression)` có thể bằng `COUNT(*)`.

Một ví dụ có điều kiện:

```sql
SELECT COUNT(
         CASE
           WHEN status = 'PAID' THEN 1
         END
       ) AS paid_sales
FROM   demo_sales;
```

`CASE` trả 1 cho giao dịch PAID, và mặc định trả NULL cho những trạng thái còn lại. `COUNT` chỉ đếm các giá trị 1 khác NULL.

**Không viết `ELSE 0` trong mẫu COUNT có điều kiện này nếu mục tiêu là đếm các hàng PAID.** Số 0 cũng không phải NULL, nên `COUNT(CASE ... ELSE 0 END)` sẽ đếm cả các hàng không PAID.

### 4.4. COUNT(DISTINCT expression)

`DISTINCT` yêu cầu chỉ đếm các giá trị khác nhau:

```sql
SELECT COUNT(amount) AS non_null_amount_rows,
       COUNT(DISTINCT amount) AS distinct_amounts
FROM   demo_sales;
```

Kết quả:

| NON_NULL_AMOUNT_ROWS | DISTINCT_AMOUNTS |
| ---: | ---: |
| 8 | 6 |

Có tám hàng có amount nhưng chỉ có sáu giá trị amount khác nhau: 500, 700, 1000, 1500, 2000 và 3000. Hai giá trị 500 ở ID 8 và 9 chỉ được tính một lần trong `COUNT(DISTINCT amount)`.

`COUNT(DISTINCT expression)` cũng bỏ qua NULL. Trong bảng mẫu, hai amount NULL không tạo thành một giá trị phân biệt để đếm.

### 4.5. COUNT(DISTINCT) khác đếm số hàng duy nhất

`COUNT(DISTINCT amount)` đếm **giá trị amount khác nhau**, không đếm giao dịch duy nhất. Hai giao dịch khác nhau cùng có amount 500 vẫn đóng góp một giá trị vào kết quả distinct.

Nếu muốn đếm số giao dịch, dùng khóa chính phù hợp hoặc `COUNT(*)` theo tập giao dịch đã lọc. Không thay bằng `COUNT(DISTINCT amount)` chỉ vì thấy dữ liệu có nhiều giá trị lặp.

## 5. SUM: tính tổng giá trị số

### 5.1. Cú pháp và ví dụ

```sql
SELECT SUM(amount) AS total_amount
FROM   demo_sales;
```

Theo bảng mẫu, tổng là:

```text
TOTAL_AMOUNT
------------
10200
```

Oracle cộng các giá trị không-NULL. Hai hàng có `AMOUNT=NULL` không tham gia tổng; chúng không được tự coi là 0 trong phép tính.

### 5.2. SUM bỏ qua NULL, nhưng không bỏ qua số 0

Giả sử tập dữ liệu có `AMOUNT` là 10, 0 và NULL:

- Tổng là 10.
- Số lượng giá trị được tính bởi `COUNT(amount)` là 2.
- Số lượng hàng bởi `COUNT(*)` là 3.

NULL biểu thị không có giá trị được cung cấp/biết; số 0 là một giá trị số thực sự. Không được tự thay mọi NULL bằng 0 nếu điều đó làm thay đổi ý nghĩa dữ liệu.

### 5.3. SUM(DISTINCT expression)

Oracle hỗ trợ:

```sql
SELECT SUM(amount) AS sum_all_rows,
       SUM(DISTINCT amount) AS sum_distinct_values
FROM   demo_sales;
```

Với bảng mẫu:

- `SUM(amount)` = **10200**.
- `SUM(DISTINCT amount)` = **8700** (500 + 700 + 1000 + 1500 + 2000 + 3000 = 8700).

Đây là hai câu hỏi khác nhau. Tổng doanh thu thường phải cộng từng giao dịch, kể cả hai giao dịch có cùng số tiền. `SUM(DISTINCT amount)` sẽ loại một lần lặp giá trị 500 và do đó không còn là tổng doanh thu của các hàng.

Chỉ dùng `DISTINCT` khi nghiệp vụ thực sự yêu cầu tổng các **mức giá trị duy nhất**, không dùng để chữa lỗi nhân bản hàng do JOIN.

### 5.4. Tổng theo điều kiện

Có thể dùng `CASE` bên trong `SUM`:

```sql
SELECT SUM(
         CASE
           WHEN status = 'PAID' THEN amount
           ELSE 0
         END
       ) AS paid_amount
FROM   demo_sales;
```

Kết quả là **9200**. Chỉ các hàng PAID đóng góp amount; các trạng thái khác đóng góp 0. Nếu amount của một hàng PAID là NULL, giá trị đó vẫn bị SUM bỏ qua.

Một cách khác là lọc trước:

```sql
SELECT SUM(amount) AS paid_amount
FROM   demo_sales
WHERE  status = 'PAID';
```

Kết quả tương tự khi chỉ cần một tổng cho các hàng PAID. `CASE` bên trong aggregate đặc biệt hữu ích khi muốn tính **nhiều chỉ số có điều kiện trong cùng một lượt nhóm**.

### 5.5. SUM với số âm và số thập phân

`SUM` không yêu cầu mọi giá trị phải dương. Nếu dữ liệu có hoàn tiền hoặc bút toán điều chỉnh, số âm có thể làm giảm tổng:

```sql
SELECT SUM(amount) AS net_amount
FROM   account_transactions;
```

Đối với tiền tệ, thường dùng `NUMBER(p,s)` với precision/scale phù hợp để giữ quy tắc số thập phân. Không nên chuyển tiền sang `BINARY_FLOAT`/`BINARY_DOUBLE` chỉ để lưu ít byte hơn nếu nghiệp vụ đòi hỏi kết quả decimal chính xác.

### 5.6. SUM và kiểu dữ liệu trả về

`SUM` nhận biểu thức số. Kiểu dữ liệu trả về phụ thuộc kiểu đối số theo quy tắc Oracle. Khi dùng `NUMBER`, cần chú ý precision và khả năng vượt phạm vi trong các phép tính lớn; khi dùng kiểu số dấu phẩy động nhị phân, kết quả có thể chịu sai số biểu diễn.

Nếu tổng được đưa sang ứng dụng, nên giữ mapping kiểu số phù hợp và không tự chuyển sang kiểu dấu phẩy động của ngôn ngữ lập trình nếu cần độ chính xác tiền tệ.

## 6. AVG: tính trung bình cộng

### 6.1. Cú pháp và ví dụ

```sql
SELECT AVG(amount) AS average_amount
FROM   demo_sales;
```

Với dữ liệu mẫu:

- Tổng các amount không-NULL: 10200.
- Số giá trị amount không-NULL: 8.
- Trung bình: 10200 / 8 = **1275**.

`AVG(amount)` thực hiện phép tính trên những giá trị không-NULL. Mẫu số không phải tổng số hàng khi có NULL.

### 6.2. AVG khác SUM chia COUNT(*) khi có NULL

Cách tính đúng theo ngữ nghĩa aggregate:

```sql
SELECT AVG(amount) AS average_amount,
       SUM(amount) / COUNT(*) AS wrong_if_nulls
FROM   demo_sales;
```

Với bảng mẫu:

- `AVG(amount)` = 1275.
- `SUM(amount) / COUNT(*)` = 1020.

Phép chia thứ hai dùng 10 hàng làm mẫu số, dù chỉ có 8 giá trị amount. Nếu muốn tự tính trung bình theo các giá trị hiện diện, mẫu số tương ứng là `COUNT(amount)`:

```sql
SELECT SUM(amount) / COUNT(amount) AS calculated_average,
       AVG(amount) AS built_in_average
FROM   demo_sales;
```

Hai kết quả bằng nhau khi cùng biểu thức và cùng tập hàng, đồng thời mẫu số khác 0. Thông thường nên dùng `AVG` vì nó diễn đạt trực tiếp ý định và tránh viết sai mẫu số.

### 6.3. AVG(DISTINCT expression)

```sql
SELECT AVG(amount) AS average_all_rows,
       AVG(DISTINCT amount) AS average_distinct_amounts
FROM   demo_sales;
```

Với dữ liệu mẫu:

- `AVG(amount)` = **1275**.
- `AVG(DISTINCT amount)` = **1450** (8700 / 6).

Trung bình distinct trả lời “trung bình của các mức amount khác nhau”, không phải “trung bình amount trên mỗi giao dịch”. Hai giao dịch 500 có trọng số hai lần trong `AVG(amount)`, nhưng chỉ một lần trong `AVG(DISTINCT amount)`.

### 6.4. Làm tròn kết quả AVG

`AVG` có thể trả về nhiều chữ số thập phân:

```sql
SELECT ROUND(AVG(amount), 2) AS average_amount_2dp
FROM   demo_sales;
```

`ROUND` chỉ làm tròn kết quả cho mục đích hiển thị hoặc quy tắc tính toán đã xác định. Không nên làm tròn từng hàng trước khi tính trung bình nếu nghiệp vụ yêu cầu trung bình của giá trị gốc; hai cách có thể khác nhau.

### 6.5. AVG có điều kiện

```sql
SELECT AVG(
         CASE
           WHEN status = 'PAID' THEN amount
         END
       ) AS average_paid_amount
FROM   demo_sales;
```

Các hàng không PAID cho ra NULL từ CASE và không tham gia AVG. Hàng PAID có amount NULL cũng không được tính. Đây là cách hữu ích để tính nhiều trung bình theo trạng thái trong một truy vấn nhóm.

### 6.6. Trung bình có trọng số

`AVG(amount)` tính trung bình cộng đơn giản, mỗi giá trị không-NULL có trọng số bằng nhau. Nếu mỗi quan sát có một trọng số, công thức tổng quát là:

\[
\text{Weighted average} =
\frac{\sum(value \times weight)}{\sum(weight)}
\]

Ví dụ khi cả `VALUE` và `WEIGHT` đều phải có giá trị:

```sql
SELECT SUM(value * weight) / NULLIF(SUM(weight), 0)
         AS weighted_average
FROM   demo_measurements
WHERE  value IS NOT NULL
AND    weight IS NOT NULL;
```

`NULLIF(SUM(weight), 0)` trả NULL nếu tổng trọng số bằng 0, tránh phép chia cho 0. Cần xác định thêm quy tắc về trọng số âm, trọng số bằng 0 và dữ liệu thiếu; không dùng công thức này mà chưa thống nhất ý nghĩa nghiệp vụ.

## 7. MIN và MAX: giá trị nhỏ nhất và lớn nhất

### 7.1. Cú pháp

```sql
SELECT MIN(amount) AS minimum_amount,
       MAX(amount) AS maximum_amount
FROM   demo_sales;
```

Theo bảng mẫu:

| MINIMUM_AMOUNT | MAXIMUM_AMOUNT |
| ---: | ---: |
| 500 | 3000 |

`MIN` lấy giá trị nhỏ nhất; `MAX` lấy giá trị lớn nhất theo quy tắc so sánh của kiểu dữ liệu. Cả hai bỏ qua NULL.

### 7.2. MIN/MAX không chỉ áp dụng cho số

Oracle có thể dùng `MIN`/`MAX` trên các kiểu dữ liệu có thứ tự so sánh phù hợp, chẳng hạn:

- `NUMBER`: số nhỏ nhất/lớn nhất.
- `DATE`: thời điểm sớm nhất/muộn nhất.
- `TIMESTAMP`: thời điểm sớm nhất/muộn nhất.
- Kiểu ký tự: giá trị nhỏ nhất/lớn nhất theo quy tắc so sánh/collation.

Ví dụ tìm ngày giao dịch đầu tiên và cuối cùng:

```sql
SELECT MIN(sold_at) AS first_sale_date,
       MAX(sold_at) AS last_sale_date
FROM   demo_sales;
```

Nếu cột là `DATE`, giá trị có thể chứa giờ, phút, giây. Đừng chỉ xem định dạng hiển thị ngày rồi kết luận hai bản ghi cùng thời điểm.

### 7.3. MIN/MAX trên chuỗi không phải “ngắn nhất/dài nhất”

Ví dụ:

```sql
SELECT MIN(region) AS first_region,
       MAX(region) AS last_region
FROM   demo_sales;
```

Kết quả dựa trên thứ tự so sánh chuỗi, không phải độ dài ký tự hoặc thứ tự nghiệp vụ do ứng dụng tự quy định. Collation, kiểu dữ liệu và cấu hình so sánh có thể ảnh hưởng kết quả.

Nếu muốn tên có độ dài ngắn nhất, đó là một bài toán khác, có thể kết hợp `LENGTH` và truy vấn phù hợp; `MIN(name)` không tự chọn chuỗi ngắn nhất.

### 7.4. MIN/MAX và NULL

Với cột có NULL:

```sql
SELECT MIN(amount),
       MAX(amount),
       COUNT(amount)
FROM   demo_sales;
```

Hai hàm MIN/MAX bỏ qua các giá trị NULL và trả kết quả dựa trên các giá trị không-NULL còn lại. Nếu toàn bộ biểu thức đầu vào là NULL hoặc tập đầu vào không có hàng, MIN/MAX trả NULL.

Nếu báo cáo cần phân biệt “không có hàng” với “có hàng nhưng mọi amount đều NULL”, kết hợp `COUNT(*)` và `COUNT(amount)`.

### 7.5. MIN/MAX không trả về toàn bộ hàng tương ứng

Truy vấn:

```sql
SELECT MAX(amount)
FROM   demo_sales;
```

chỉ trả **giá trị amount lớn nhất**, không trả tự động `SALE_ID` hoặc `SALESPERSON` của giao dịch có giá trị đó.

Muốn lấy hàng có amount lớn nhất, có thể dùng subquery:

```sql
SELECT sale_id, salesperson, amount
FROM   demo_sales
WHERE  amount = (
         SELECT MAX(amount)
         FROM   demo_sales
       );
```

Nếu nhiều hàng cùng amount lớn nhất, truy vấn trả tất cả hàng đồng hạng. Nếu cần đúng một hàng, phải xác định quy tắc phá hòa, ví dụ sắp theo amount giảm dần rồi theo sale_id tăng dần và dùng cơ chế top-N/row limiting phù hợp.

## 8. NULL và tập kết quả rỗng

### 8.1. Quy tắc tổng quát

Trong các aggregate cơ bản:

- `COUNT(*)` đếm hàng, không bỏ hàng vì cột có NULL.
- `COUNT(expression)` bỏ những hàng mà expression là NULL.
- `SUM`, `AVG`, `MIN`, `MAX` bỏ NULL trong expression.

Ví dụ:

```sql
SELECT COUNT(*) AS row_count,
       COUNT(amount) AS known_amount_count,
       SUM(amount) AS total_amount,
       AVG(amount) AS average_amount,
       MIN(amount) AS min_amount,
       MAX(amount) AS max_amount
FROM   demo_sales;
```

Kết quả mẫu:

| ROW_COUNT | KNOWN_AMOUNT_COUNT | TOTAL_AMOUNT | AVERAGE_AMOUNT | MIN_AMOUNT | MAX_AMOUNT |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 10 | 8 | 10200 | 1275 | 500 | 3000 |

### 8.2. Tập đầu vào không có hàng

Chạy:

```sql
SELECT COUNT(*) AS row_count,
       COUNT(amount) AS amount_count,
       SUM(amount) AS total_amount,
       AVG(amount) AS average_amount,
       MIN(amount) AS min_amount,
       MAX(amount) AS max_amount
FROM   demo_sales
WHERE  1 = 0;
```

Kết quả vẫn là **một hàng tổng hợp**:

| ROW_COUNT | AMOUNT_COUNT | TOTAL_AMOUNT | AVERAGE_AMOUNT | MIN_AMOUNT | MAX_AMOUNT |
| ---: | ---: | --- | --- | --- | --- |
| 0 | 0 | NULL | NULL | NULL | NULL |

`COUNT` trả 0; các aggregate còn lại trả NULL vì không có giá trị nào để tính. Đây là khác biệt cần xử lý trong API/report.

### 8.3. Có hàng nhưng toàn bộ giá trị NULL

Giả sử có hai giao dịch nhưng amount đều NULL. Kết quả:

- `COUNT(*)` = 2.
- `COUNT(amount)` = 0.
- `SUM(amount)` = NULL.
- `AVG(amount)` = NULL.
- `MIN(amount)` = NULL.
- `MAX(amount)` = NULL.

Vì vậy, một kết quả `SUM=NULL` có thể có nghĩa tập đầu vào rỗng **hoặc** có hàng nhưng không có giá trị amount nào khác NULL. Kết hợp các count giúp phân biệt hai tình huống.

### 8.4. Có nên thay SUM NULL thành 0?

Có thể dùng:

```sql
SELECT NVL(SUM(amount), 0) AS total_amount
FROM   demo_sales
WHERE  status = 'UNKNOWN_STATUS';
```

Kết quả hiển thị 0 thay vì NULL. Nhưng điều này thay đổi cách biểu diễn kết quả: “không có giá trị để tổng hợp” được chuyển thành “tổng bằng 0”.

Chỉ dùng `NVL(SUM(...), 0)` nếu quy tắc báo cáo coi hai trạng thái này tương đương. Nếu cần phân biệt, giữ NULL và hiển thị thông điệp phù hợp ở tầng ứng dụng.

### 8.5. NULL trong GROUP BY

Oracle gom các hàng có `REGION=NULL` vào cùng một nhóm:

```sql
SELECT region,
       COUNT(*) AS sale_count,
       COUNT(amount) AS amount_count,
       SUM(amount) AS total_amount
FROM   demo_sales
GROUP  BY region
ORDER  BY region NULLS LAST;
```

Kết quả có một nhóm region NULL gồm sale ID 10. Trong nhóm đó, `COUNT(*)` là 1 và `COUNT(amount)` cũng là 1.

Nếu có nhiều hàng region NULL, chúng cùng nằm trong một nhóm. `GROUP BY` không loại NULL giống điều kiện `WHERE region = NULL`; muốn lọc nhóm NULL, dùng `HAVING region IS NULL` hoặc lọc ở WHERE trước khi nhóm.

## 9. GROUP BY: tính aggregate theo từng nhóm

### 9.1. Cú pháp cơ bản

```sql
SELECT group_column,
       aggregate_function(...)
FROM   table_name
WHERE  row_condition
GROUP  BY group_column
ORDER  BY group_column;
```

Ví dụ tổng doanh thu theo vùng:

```sql
SELECT region,
       COUNT(*) AS sale_count,
       COUNT(amount) AS amount_count,
       SUM(amount) AS total_amount,
       AVG(amount) AS average_amount,
       MIN(amount) AS min_amount,
       MAX(amount) AS max_amount
FROM   demo_sales
GROUP  BY region
ORDER  BY region NULLS LAST;
```

Kết quả theo dữ liệu mẫu:

| REGION | SALE_COUNT | AMOUNT_COUNT | TOTAL_AMOUNT | AVERAGE_AMOUNT | MIN_AMOUNT | MAX_AMOUNT |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
Trong bảng mẫu có **ba** giao dịch EAST (ID 7, 8, 9). Hai hàng có amount không-NULL là 500 và 500; tổng 1000, trung bình 500, min 500, max 500.

| REGION | SALE_COUNT | AMOUNT_COUNT | TOTAL_AMOUNT | AVERAGE_AMOUNT | MIN_AMOUNT | MAX_AMOUNT |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| EAST | 3 | 2 | 1000 | 500 | 500 | 500 |
| NORTH | 3 | 3 | 3500 | 1166.67 | 1000 | 1500 |
| SOUTH | 3 | 2 | 5000 | 2500 | 2000 | 3000 |
| NULL | 1 | 1 | 700 | 700 | 700 | 700 |

Mỗi dòng là một nhóm region, và các hàm tổng hợp được tính độc lập trong nhóm đó.

### 9.2. Nhiều cột GROUP BY

Có thể nhóm theo nhiều chiều:

```sql
SELECT region,
       status,
       COUNT(*) AS sale_count,
       SUM(amount) AS total_amount
FROM   demo_sales
GROUP  BY region, status
ORDER  BY region NULLS LAST, status;
```

Một nhóm được xác định bởi **tổ hợp giá trị** của tất cả cột trong `GROUP BY`. Ví dụ `(NORTH, PAID)` khác `(NORTH, PENDING)`.

Nếu muốn thống kê theo vùng và nhân viên, thay `status` bằng `salesperson` hoặc bổ sung cột theo đúng câu hỏi nghiệp vụ. Nhiều cột nhóm hơn thường tạo nhiều nhóm nhỏ hơn.

### 9.3. SELECT với GROUP BY

Trong truy vấn có `GROUP BY`, các biểu thức ở `SELECT` thông thường phải là:

- Biểu thức được dùng trong `GROUP BY`; hoặc
- Hàm tổng hợp áp dụng lên dữ liệu trong nhóm; hoặc
- Biểu thức được xây dựng hợp lệ từ các biểu thức nhóm/aggregate theo quy tắc Oracle.

Ví dụ sai:

```sql
SELECT region,
       salesperson,
       SUM(amount)
FROM   demo_sales
GROUP  BY region;
```

`SALESPERSON` không được nhóm và cũng không được tổng hợp, nên Oracle không biết phải chọn tên nhân viên nào cho một nhóm region có nhiều nhân viên.

Cách sửa tùy mục tiêu:

```sql
SELECT region,
       salesperson,
       SUM(amount)
FROM   demo_sales
GROUP  BY region, salesperson;
```

hoặc nếu chỉ cần tổng theo vùng, bỏ `SALESPERSON` khỏi SELECT.

### 9.4. GROUP BY không tự sắp xếp kết quả

Dù có thể quan sát kết quả thường được trả theo một thứ tự nào đó, **không được dựa vào thứ tự mặc định của GROUP BY**. Muốn thứ tự ổn định, dùng `ORDER BY`:

```sql
SELECT region, SUM(amount) AS total_amount
FROM   demo_sales
GROUP  BY region
ORDER  BY total_amount DESC NULLS LAST;
```

Thứ tự trình bày là một yêu cầu riêng, không phải thuộc tính bảo đảm của phép nhóm.

## 10. HAVING: lọc nhóm sau khi tổng hợp

### 10.1. WHERE và HAVING khác nhau

- **`WHERE`** lọc các hàng đầu vào **trước khi nhóm**.
- **`HAVING`** lọc các nhóm **sau khi GROUP BY và aggregate**.

Ví dụ lấy các vùng có tổng amount ít nhất 3000:

```sql
SELECT region,
       SUM(amount) AS total_amount
FROM   demo_sales
GROUP  BY region
HAVING SUM(amount) >= 3000
ORDER  BY total_amount DESC;
```

Theo bảng mẫu, NORTH có 3500 và SOUTH có 5000; cả hai thỏa điều kiện. EAST (1000) và nhóm NULL (700) bị loại.

### 10.2. Lọc hàng trước, lọc nhóm sau

Yêu cầu: chỉ tính giao dịch PAID, sau đó chỉ lấy vùng có tổng PAID amount trên 3000:

```sql
SELECT region,
       COUNT(*) AS paid_count,
       SUM(amount) AS paid_total
FROM   demo_sales
WHERE  status = 'PAID'
GROUP  BY region
HAVING SUM(amount) > 3000
ORDER  BY paid_total DESC;
```

`WHERE status='PAID'` loại giao dịch không PAID trước khi tính. `HAVING SUM(amount)>3000` chỉ giữ các nhóm có tổng đạt ngưỡng.

### 10.3. Không dùng aggregate trực tiếp trong WHERE cùng cấp

Không viết:

```sql
SELECT region, SUM(amount)
FROM   demo_sales
WHERE  SUM(amount) > 3000
GROUP  BY region;
```

Vì `WHERE` được áp dụng trước khi aggregate của nhóm được tính. Hãy chuyển điều kiện nhóm sang `HAVING`:

```sql
SELECT region, SUM(amount)
FROM   demo_sales
GROUP  BY region
HAVING SUM(amount) > 3000;
```

Nếu muốn lọc dựa trên aggregate của một truy vấn con, có thể tổng hợp ở subquery rồi lọc ở truy vấn ngoài.

### 10.4. HAVING không bắt buộc phải có GROUP BY tường minh

Có thể dùng aggregate trong `HAVING` mà không có `GROUP BY` để lọc toàn bộ tập như một nhóm:

```sql
SELECT SUM(amount) AS total_amount
FROM   demo_sales
HAVING SUM(amount) > 10000;
```

Nếu tổng lớn hơn 10000, truy vấn trả một hàng; nếu không, không có hàng kết quả. Cách viết này ít gặp hơn nhưng giúp hiểu rằng HAVING là điều kiện trên kết quả aggregate.

## 11. Đếm và tính tổng có điều kiện

Conditional aggregation là cách tính nhiều chỉ số trong một câu truy vấn, thường dùng `CASE` bên trong aggregate.

### 11.1. Đếm theo trạng thái

```sql
SELECT COUNT(*) AS all_sales,
       COUNT(CASE WHEN status = 'PAID' THEN 1 END) AS paid_sales,
       COUNT(CASE WHEN status = 'PENDING' THEN 1 END) AS pending_sales,
       COUNT(CASE WHEN status = 'CANCELLED' THEN 1 END) AS cancelled_sales
FROM   demo_sales;
```

Theo bảng mẫu:

| ALL_SALES | PAID_SALES | PENDING_SALES | CANCELLED_SALES |
| ---: | ---: | ---: | ---: |
| 10 | 7 | 2 | 1 |

Các nhánh CASE không khớp trả NULL, vì vậy COUNT chỉ đếm trạng thái tương ứng.

### 11.2. Tổng doanh thu theo trạng thái

```sql
SELECT SUM(CASE WHEN status = 'PAID'
                THEN amount ELSE 0 END) AS paid_amount,
       SUM(CASE WHEN status = 'PENDING'
                THEN amount ELSE 0 END) AS pending_amount,
       SUM(CASE WHEN status = 'CANCELLED'
                THEN amount ELSE 0 END) AS cancelled_amount
FROM   demo_sales;
```

Theo dữ liệu mẫu:

- PAID: 9200.
- PENDING: 1000 (hàng ID 3; ID 5 có amount NULL).
- CANCELLED: NULL được chuyển thành 0 bởi nhánh ELSE 0 trong hàng có trạng thái CANCELLED, do đó tổng kết quả là 0.

Nếu muốn kết quả nhóm không có giá trị được tính là NULL thay vì 0, bỏ `ELSE 0`:

```sql
SUM(CASE WHEN status = 'CANCELLED' THEN amount END)
```

Với các hàng CANCELLED có amount NULL, biểu thức trên trả NULL vì không có giá trị số không-NULL để cộng.

### 11.3. Tính nhiều KPI trong một lần GROUP BY

```sql
SELECT region,
       COUNT(*) AS total_sales,
       COUNT(CASE WHEN status = 'PAID' THEN 1 END) AS paid_count,
       SUM(CASE WHEN status = 'PAID' THEN amount ELSE 0 END) AS paid_total,
       AVG(CASE WHEN status = 'PAID' THEN amount END) AS paid_average,
       MIN(CASE WHEN status = 'PAID' THEN amount END) AS min_paid_amount,
       MAX(CASE WHEN status = 'PAID' THEN amount END) AS max_paid_amount
FROM   demo_sales
GROUP  BY region
ORDER  BY region NULLS LAST;
```

Mỗi aggregate có biểu thức đầu vào riêng, nhưng tất cả cùng tính trên từng nhóm region. Cách này hữu ích cho báo cáo dashboard và bảng tổng hợp.

### 11.4. COUNT có điều kiện và lỗi ELSE 0

So sánh:

```sql
SELECT COUNT(CASE WHEN status = 'PAID' THEN 1 END) AS correct_count,
       COUNT(CASE WHEN status = 'PAID' THEN 1 ELSE 0 END) AS counts_every_row
FROM   demo_sales;
```

Kết quả đầu tiên là 7; kết quả thứ hai là 10 vì cả 1 lẫn 0 đều khác NULL. Khi dùng `COUNT(CASE...)` để đếm điều kiện, thông thường **không cần ELSE**.

### 11.5. Tỷ lệ phần trăm

Có thể tính tỷ lệ PAID trên tổng số giao dịch:

```sql
SELECT
    COUNT(CASE WHEN status = 'PAID' THEN 1 END) AS paid_count,
    COUNT(*) AS total_count,
    ROUND(
      100 * COUNT(CASE WHEN status = 'PAID' THEN 1 END)
          / NULLIF(COUNT(*), 0),
      2
    ) AS paid_percent
FROM demo_sales;
```

`NULLIF(COUNT(*), 0)` bảo vệ phép chia khi tập đầu vào không có hàng. Với truy vấn aggregate không GROUP BY, COUNT trả 0 trên tập rỗng và phép chia được chuyển thành chia cho NULL thay vì chia cho 0.

## 12. Aggregate kết hợp JOIN: tránh đếm và cộng trùng

### 12.1. Một hàng cha có nhiều hàng con

Giả sử một đơn hàng có nhiều dòng chi tiết. Khi join:

```sql
SELECT o.order_id,
       o.total_amount,
       i.item_id
FROM   orders o
JOIN   order_items i
       ON i.order_id = o.order_id;
```

Nếu một order có ba items, giá trị `TOTAL_AMOUNT` của order xuất hiện ba lần trong kết quả join. Vì vậy:

```sql
SELECT SUM(o.total_amount) AS total_order_amount
FROM   orders o
JOIN   order_items i
       ON i.order_id = o.order_id;
```

có thể **cộng lặp tổng tiền đơn hàng theo số dòng item**, không còn là tổng tiền các order.

Đây là lỗi fan-out rất phổ biến trong báo cáo.

### 12.2. Tổng hợp trước rồi mới JOIN

Nếu mục tiêu là tổng doanh thu theo khách hàng từ bảng orders, hãy aggregate orders trước:

```sql
SELECT c.customer_id,
       c.customer_name,
       NVL(x.order_total, 0) AS order_total
FROM   customers c
LEFT JOIN (
    SELECT customer_id,
           SUM(total_amount) AS order_total
    FROM   orders
    GROUP  BY customer_id
) x
       ON x.customer_id = c.customer_id;
```

Subquery tạo một hàng tổng hợp cho mỗi customer_id; khi join với customers, tổng không bị nhân lên bởi số item.

Nếu cần thống kê số items, hãy tổng hợp bảng items riêng theo order/customer rồi join các kết quả đã tổng hợp theo khóa đúng.

### 12.3. COUNT(*) và COUNT(child_id) trong LEFT JOIN

Ví dụ:

```sql
SELECT c.customer_id,
       COUNT(*) AS joined_rows,
       COUNT(o.order_id) AS actual_orders
FROM   customers c
LEFT JOIN orders o
       ON o.customer_id = c.customer_id
GROUP  BY c.customer_id;
```

Với customer chưa có order:

- `COUNT(*)` vẫn là 1 vì LEFT JOIN tạo một hàng kết quả với các cột phía order được đặt NULL.
- `COUNT(o.order_id)` là 0 nếu `ORDER_ID` không NULL trong các hàng order thật.

Để đếm hàng con thực sự, hãy dùng `COUNT` trên một cột khóa của bảng con được bảo đảm NOT NULL, thường là primary key. Đây là khác biệt quan trọng khi viết báo cáo số đơn hàng theo từng khách hàng.

### 12.4. COUNT(DISTINCT) có thể đúng nhưng không phải cách sửa mọi join

Nếu mục tiêu đếm số khách hàng duy nhất sau join, `COUNT(DISTINCT customer_id)` có thể phù hợp. Nhưng nếu tổng tiền bị nhân lên, dùng `SUM(DISTINCT total_amount)` không phải giải pháp chung: hai đơn hàng khác nhau có thể có cùng tổng tiền và khi đó một giá trị sẽ bị loại sai.

Cách sửa đúng là xác định **grain (mức chi tiết) của dữ liệu**, aggregate ở mức đúng trước khi join, hoặc dùng join/EXISTS theo đúng câu hỏi.

## 13. Tập hợp rỗng, nhóm rỗng và truy vấn con

### 13.1. Aggregate không GROUP BY

```sql
SELECT COUNT(*) AS row_count,
       SUM(amount) AS total_amount
FROM   demo_sales
WHERE  status = 'NOT_A_STATUS';
```

Kết quả có một hàng: `ROW_COUNT=0`, `TOTAL_AMOUNT=NULL`.

### 13.2. Aggregate với GROUP BY

```sql
SELECT region,
       COUNT(*) AS row_count,
       SUM(amount) AS total_amount
FROM   demo_sales
WHERE  status = 'NOT_A_STATUS'
GROUP  BY region;
```

Không có hàng đầu vào nên không có nhóm nào được hình thành; kết quả là **0 hàng**, không phải một hàng có count 0.

### 13.3. Tổng hợp qua subquery

Ví dụ muốn tìm các vùng có tổng doanh thu cao hơn mức trung bình doanh thu theo vùng:

```sql
SELECT region,
       SUM(amount) AS region_total
FROM   demo_sales
GROUP  BY region
HAVING SUM(amount) > (
    SELECT AVG(region_total)
    FROM (
        SELECT SUM(amount) AS region_total
        FROM   demo_sales
        GROUP  BY region
    )
)
ORDER BY region_total DESC;
```

Subquery trong cùng truy vấn tính tổng từng vùng; truy vấn ngoài tính trung bình của các tổng vùng rồi lọc nhóm vượt ngưỡng. Đây là cách dùng subquery khi cần aggregate trên kết quả aggregate khác.

Không nên viết trực tiếp `AVG(SUM(amount))` trong cùng cấp SELECT/GROUP BY nếu không có cấu trúc truy vấn lồng thích hợp. Khi cần tổng hợp nhiều tầng, dùng subquery hoặc CTE để tách các bước.

### 13.4. CTE giúp đọc truy vấn nhiều bước

```sql
WITH region_totals AS (
    SELECT region,
           COUNT(*) AS sale_count,
           SUM(amount) AS total_amount
    FROM   demo_sales
    GROUP  BY region
)
SELECT region,
       sale_count,
       total_amount
FROM   region_totals
WHERE  total_amount >= 3000
ORDER  BY total_amount DESC;
```

CTE đặt tên cho kết quả trung gian, giúp tách logic tổng hợp khỏi logic lọc/hiển thị. Oracle Optimizer có thể biến đổi cách thực thi; CTE không mặc nhiên có nghĩa dữ liệu luôn được vật hóa thành bảng tạm.

## 14. Hiệu năng và cách đọc kế hoạch thực thi

### 14.1. Aggregate có thể phải đọc nhiều dữ liệu

Một truy vấn:

```sql
SELECT SUM(amount)
FROM   demo_sales;
```

cần xem xét tất cả giá trị thuộc tập đầu vào để tính tổng chính xác. Oracle có thể chọn full table scan, index scan hoặc chiến lược khác tùy cấu trúc và thống kê. Không có nghĩa cứ tạo index trên `AMOUNT` là `SUM` sẽ nhanh hơn.

### 14.2. COUNT(*) và COUNT(column) không phải hai cách tối ưu hóa tùy ý

Chọn hàm theo ý nghĩa:

- `COUNT(*)` khi cần số hàng.
- `COUNT(column)` khi cần số giá trị không NULL.
- `COUNT(DISTINCT column)` khi cần số giá trị khác nhau.

Đừng đổi `COUNT(*)` thành `COUNT(1)` vì kỳ vọng tăng tốc. Đừng đổi `COUNT(*)` thành `COUNT(column)` nếu cột có thể NULL; kết quả khi đó thay đổi.

### 14.3. Index và MIN/MAX

Với index phù hợp, Oracle đôi khi có thể tìm MIN/MAX bằng cách truy cập một đầu của index thay vì đọc toàn bộ bảng. Khả năng này phụ thuộc điều kiện lọc, thứ tự index, NULL, thống kê và execution plan.

Không suy ra hiệu năng chỉ từ việc cột đã có index. Kiểm tra kế hoạch và số liệu thực tế.

### 14.4. GROUP BY và bộ nhớ

Các truy vấn có nhiều nhóm có thể dùng cơ chế hash aggregation hoặc sort/group by. Số lượng nhóm, kích thước dữ liệu, phân phối giá trị, parallelism và bộ nhớ ảnh hưởng chi phí. Nếu bộ nhớ không đủ, một số thao tác có thể spill ra TEMP.

Đối với báo cáo lớn, nên:

- Lọc hàng sớm bằng điều kiện phù hợp.
- Chọn đúng cột nhóm, tránh tạo nhóm chi tiết hơn yêu cầu.
- Kiểm tra thống kê bảng và index.
- Đo execution plan/runtime.
- Tránh join fan-out trước khi aggregate.

### 14.5. Xem execution plan

Ví dụ:

```sql
EXPLAIN PLAN FOR
SELECT region,
       COUNT(*) AS sale_count,
       SUM(amount) AS total_amount
FROM   demo_sales
GROUP  BY region;

SELECT *
FROM   TABLE(DBMS_XPLAN.DISPLAY);
```

`EXPLAIN PLAN` hiển thị kế hoạch ước lượng. Khi cần điều tra truy vấn đã chạy, DBA có thể xem cursor plan và thống kê runtime theo quyền/công cụ phù hợp. Với bảng demo rất nhỏ, full scan là lựa chọn bình thường; không cần tạo index chỉ để tránh nó.

## 15. Những lỗi và nhầm lẫn thường gặp

### 15.1. Đếm sai do NULL

**Dấu hiệu:** `COUNT(*)` lớn hơn `COUNT(amount)`.

**Nguyên nhân:** một số hàng không có amount. Đây là khác biệt ngữ nghĩa, không phải lỗi đếm.

**Cách xử lý:** xác định báo cáo cần đếm giao dịch hay đếm giao dịch đã có giá trị amount.

### 15.2. AVG thấp hơn dự kiến

**Nguyên nhân có thể:** chia tổng cho COUNT(*) thay vì COUNT(cột), hoặc tập dữ liệu có các giá trị 0 thực sự. `AVG` bỏ NULL nhưng vẫn tính số 0.

**Cách xử lý:** xem số lượng không-NULL, phân biệt 0 với NULL, và xác định điều kiện lọc trước khi tính.

### 15.3. SUM trả NULL dù bảng có hàng

Có thể tất cả giá trị của biểu thức được SUM đều NULL hoặc WHERE không chọn hàng nào. Kết hợp `COUNT(*)` và `COUNT(expression)` để phân biệt.

### 15.4. COUNT sau LEFT JOIN trả 1 dù không có con

LEFT JOIN tạo hàng cha với cột con NULL. `COUNT(*)` đếm hàng join này; dùng `COUNT(child.primary_key)` để đếm hàng con thực sự.

### 15.5. SUM bị lớn bất thường sau JOIN

Một hàng cha có thể lặp lại theo số hàng con. Kiểm tra grain của kết quả join và tổng hợp bảng con/cha riêng trước khi ghép.

### 15.6. SUM(DISTINCT) làm thiếu doanh thu

DISTINCT loại giá trị trùng, không loại hàng trùng theo khóa giao dịch. Hai giao dịch hợp lệ có cùng amount sẽ chỉ được cộng một lần. Không dùng nó để sửa fan-out.

### 15.7. MIN/MAX trên chuỗi cho kết quả không như ngôn ngữ tự nhiên

Đây là phép so sánh theo thứ tự chuỗi/collation, không phải so theo ý nghĩa nghiệp vụ. Nếu cần min/max theo độ dài, thứ tự ưu tiên riêng hoặc một quy tắc khác, phải biểu diễn quy tắc đó tường minh.

### 15.8. Dùng WHERE để lọc kết quả tổng hợp

Aggregate ở cùng cấp SELECT không dùng trực tiếp trong WHERE. Dùng HAVING hoặc đặt aggregate trong subquery/CTE rồi lọc ở ngoài.

### 15.9. GROUP BY không trả một dòng khi không có dữ liệu

Không có GROUP BY: aggregate thường trả một hàng kết quả, COUNT có thể bằng 0. Có GROUP BY: tập rỗng tạo không nhóm nào, nên không có hàng kết quả.

### 15.10. Không phân biệt tổng 0 và tổng NULL

0 là một giá trị số; NULL là không có giá trị aggregate được xác định. Chỉ chuyển NULL thành 0 bằng NVL/COALESCE khi báo cáo/nghiệp vụ muốn hai trạng thái được biểu diễn như nhau.

## 16. Quy trình thiết kế một báo cáo aggregate

Trước khi viết truy vấn báo cáo, trả lời các câu hỏi sau:

1. **Đơn vị cần đếm là gì?** Hàng, giao dịch, khách hàng, sản phẩm hay nhóm giá trị?
2. **NULL có ý nghĩa gì?** Không biết, chưa nhập, không áp dụng hay phải coi là 0?
3. **Có cần loại trùng không?** DISTINCT trên giá trị nào và vì sao?
4. **Cần tính trên tập nào?** Điều kiện WHERE nào áp dụng trước khi nhóm?
5. **Nhóm theo chiều nào?** Vùng, tháng, trạng thái, nhân viên hay tổ hợp?
6. **Lọc nhóm theo tiêu chí gì?** HAVING sau khi aggregate.
7. **Có JOIN làm nhân bản hàng không?** Kiểm tra quan hệ 1:N và grain trước khi SUM/COUNT.
8. **Tập rỗng cần hiển thị gì?** 0, NULL hay không có hàng?
9. **Có cần phân biệt giá trị duy nhất hay từng giao dịch?** Tránh dùng SUM(DISTINCT) sai mục tiêu.
10. **Có cần lấy cả hàng tương ứng MIN/MAX không?** Viết truy vấn tìm hàng và quy tắc xử lý đồng hạng.

Mẫu truy vấn báo cáo:

```sql
SELECT group_key,
       COUNT(*) AS row_count,
       COUNT(value_column) AS known_value_count,
       SUM(value_column) AS total_value,
       AVG(value_column) AS average_value,
       MIN(value_column) AS minimum_value,
       MAX(value_column) AS maximum_value
FROM   source_table
WHERE  row_level_condition
GROUP  BY group_key
HAVING COUNT(*) >= :minimum_rows
ORDER  BY group_key;
```

Đây chỉ là khung minh họa; thay tên bảng/cột và điều kiện theo đúng grain và quy tắc nghiệp vụ.

## 17. Bài tập tự kiểm tra

Dùng bảng `DEMO_SALES` đã tạo ở phần 2.

### Câu 1 — COUNT(*)

Viết truy vấn đếm tổng số hàng trong bảng.

**Gợi ý:**

```sql
SELECT COUNT(*) FROM demo_sales;
```

Kết quả là 10.

### Câu 2 — COUNT(cột)

Viết truy vấn đếm số hàng có amount không NULL. Kết quả có bằng COUNT(*) không?

**Gợi ý:** Dùng `COUNT(amount)`; kết quả là 8 vì hai hàng amount NULL.

### Câu 3 — COUNT(DISTINCT)

Có bao nhiêu mức amount khác nhau, không tính NULL?

**Gợi ý:** `COUNT(DISTINCT amount)`; kết quả là 6.

### Câu 4 — SUM

Tính tổng amount của mọi giao dịch. Hai hàng NULL ảnh hưởng thế nào?

**Gợi ý:** `SUM(amount)` = 10200; NULL bị bỏ qua.

### Câu 5 — AVG

Tính trung bình amount và giải thích mẫu số.

**Gợi ý:** `AVG(amount)` = 1275; mẫu số là 8 giá trị không NULL.

### Câu 6 — MIN/MAX

Tìm amount thấp nhất và cao nhất.

**Gợi ý:** `MIN(amount)=500` và `MAX(amount)=3000`.

### Câu 7 — GROUP BY

Tính số giao dịch và tổng amount theo region, gồm cả nhóm NULL.

**Gợi ý:** `GROUP BY region`; nhóm NULL có một hàng, tổng 700.

### Câu 8 — HAVING

Chỉ hiển thị region có tổng amount ít nhất 3000.

**Gợi ý:** `GROUP BY region HAVING SUM(amount) >= 3000`. NORTH và SOUTH thỏa.

### Câu 9 — Đếm có điều kiện

Đếm số giao dịch PAID mà không dùng WHERE để loại các trạng thái khác.

**Gợi ý:**

```sql
SELECT COUNT(CASE WHEN status = 'PAID' THEN 1 END)
FROM demo_sales;
```

Kết quả 7.

### Câu 10 — COUNT CASE và ELSE 0

Vì sao `COUNT(CASE WHEN status='PAID' THEN 1 ELSE 0 END)` trả 10 thay vì 7?

**Gợi ý:** Cả 1 và 0 đều khác NULL nên COUNT đếm tất cả các hàng.

### Câu 11 — Tổng PAID

Tính tổng amount của các giao dịch PAID.

**Gợi ý:** `SUM(CASE WHEN status='PAID' THEN amount END)` hoặc lọc `WHERE status='PAID'`; kết quả 9200.

### Câu 12 — Tập rỗng

Chạy aggregate với `WHERE 1=0`. COUNT và SUM trả gì?

**Gợi ý:** COUNT trả 0; SUM trả NULL. Không GROUP BY nên vẫn có một hàng kết quả.

### Câu 13 — LEFT JOIN

Một khách hàng chưa có đơn hàng xuất hiện sau LEFT JOIN. Tại sao `COUNT(*)` bằng 1 nhưng `COUNT(order_id)` bằng 0?

**Gợi ý:** Hàng được LEFT JOIN giữ lại với cột phía order NULL; COUNT(*) đếm hàng join, COUNT(order_id) bỏ NULL.

### Câu 14 — SUM DISTINCT

Hai giao dịch khác nhau đều có amount 500. Vì sao `SUM(DISTINCT amount)` không phù hợp để tính doanh thu thực?

**Gợi ý:** DISTINCT loại một trong hai giá trị 500 dù chúng là hai giao dịch riêng biệt.

### Câu 15 — JOIN fan-out

Một order có bốn dòng item. Nếu join order với item rồi SUM(order.total_amount), tổng tiền order bị ảnh hưởng thế nào?

**Gợi ý:** Tổng tiền order xuất hiện bốn lần trong tập join và có thể bị cộng bốn lần. Aggregate order trước khi join hoặc tổng hợp đúng grain.

### Câu 16 — MIN/MAX ngày giờ

Viết truy vấn tìm thời điểm bán sớm nhất và muộn nhất.

**Gợi ý:** `MIN(sold_at)` và `MAX(sold_at)`.

### Câu 17 — AVG có điều kiện

Tính trung bình amount của giao dịch PAID.

**Gợi ý:**

```sql
SELECT AVG(CASE WHEN status = 'PAID' THEN amount END)
FROM demo_sales;
```

### Câu 18 — Phân biệt NULL và 0

Nếu báo cáo không có giao dịch trong kỳ, có nên luôn hiển thị SUM là 0 không?

**Gợi ý:** Tùy nghiệp vụ. NULL thể hiện không có giá trị để tổng hợp; chỉ chuyển sang 0 khi báo cáo muốn diễn giải như vậy.

## 18. Dọn dữ liệu thực hành

Chỉ thực hiện khi xác nhận các bảng là dữ liệu demo do bạn tạo và không chứa dữ liệu cần giữ:

```sql
-- THAO TÁC PHÁ HỦY: chỉ dành cho schema học tập.
DROP TABLE demo_sales PURGE;
```

Lệnh DROP là DDL và xóa bảng cùng dữ liệu. Không chạy trên bảng ứng dụng; không dựa vào ROLLBACK để khôi phục DDL đã thực hiện.

## 19. Tài liệu Oracle tham khảo

- [Oracle Database SQL Language Reference — Aggregate Functions](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/Aggregate-Functions.html): quy tắc tổng quát về hàm tổng hợp và cách xử lý NULL.
- [Oracle Database SQL Language Reference — COUNT](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/COUNT.html): `COUNT(*)`, `COUNT(expression)` và `COUNT(DISTINCT ...)`.
- [Oracle Database SQL Language Reference — SUM](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/SUM.html): tổng các giá trị và kiểu dữ liệu trả về.
- [Oracle Database SQL Language Reference — AVG](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/AVG.html): trung bình và cách xử lý NULL.
- [Oracle Database SQL Language Reference — MIN](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/MIN.html) và [MAX](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/MAX.html): giá trị nhỏ nhất/lớn nhất.
- [Oracle Database SQL Language Reference — SELECT](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/SELECT.html): `WHERE`, `GROUP BY`, `HAVING` và `ORDER BY`.
- [Oracle Database SQL Tuning Guide](https://docs.oracle.com/en/database/oracle/oracle-database/19/tgsql/): execution plan, optimizer và hiệu năng aggregate.

Khi dùng các hàm tổng hợp trong Oracle, hãy luôn xác định **đang đếm hàng hay đếm giá trị**, **NULL có được bỏ qua hay không**, **cần tổng hợp trên từng giao dịch hay từng giá trị duy nhất**, và **JOIN có làm nhân bản dữ liệu trước khi tính hay không**. Dùng `GROUP BY` để tạo nhóm, `HAVING` để lọc nhóm và `CASE` để tính chỉ số có điều kiện. Khi các ý nghĩa này rõ ràng, báo cáo COUNT, SUM, AVG, MIN và MAX sẽ phản ánh đúng dữ liệu nghiệp vụ.
