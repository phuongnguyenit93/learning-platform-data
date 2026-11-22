# LEAST, GREATEST và ảnh hưởng của NULL hoặc chuyển kiểu trong Oracle SQL

Trong Oracle Database, hai hàm **`LEAST`** và **`GREATEST`** dùng để chọn giá trị nhỏ nhất hoặc lớn nhất trong một danh sách biểu thức. Chúng thường xuất hiện trong các bài toán như chọn ngày bắt đầu/kết thúc sớm hơn, lấy mức giá thấp nhất giữa giá niêm yết và giá khuyến mãi, giới hạn một giá trị trong khoảng cho phép hoặc so sánh nhiều ngưỡng trên cùng một hàng.

```sql
SELECT LEAST(100, 80, 120) AS lowest_value,
       GREATEST(100, 80, 120) AS highest_value
FROM dual;
```

Kết quả lần lượt là `80` và `120`. Tuy nhiên, kết quả có thể gây bất ngờ khi danh sách chứa **`NULL`**, các biểu thức có **kiểu dữ liệu khác nhau**, hoặc đối số đầu tiên là chuỗi thay vì số/ngày. Trong Oracle, kiểu dữ liệu của đối số đầu tiên có vai trò quan trọng đối với quy tắc chuyển kiểu và kiểu kết quả. Vì vậy, không nên xem hai hàm này như phép `MIN`/`MAX` tổng hợp hay giả định Oracle luôn tự hiểu kiểu nghiệp vụ mong muốn.

## 1. LEAST và GREATEST là hàm scalar so sánh trong một hàng

`LEAST(expr1, expr2 [, expr3 ...])` trả về giá trị nhỏ nhất trong các biểu thức được truyền vào.

`GREATEST(expr1, expr2 [, expr3 ...])` trả về giá trị lớn nhất trong các biểu thức được truyền vào.

Hai hàm là **scalar function**: mỗi lần gọi xử lý các đối số của một lần đánh giá biểu thức, thường là trên từng hàng của truy vấn. Chúng không tự gom nhiều hàng thành một kết quả tổng hợp.

```sql
SELECT LEAST(12, 5, 9) AS min_in_list,
       GREATEST(12, 5, 9) AS max_in_list
FROM dual;
```

| Biểu thức | Kết quả |
|---|---:|
| `LEAST(12, 5, 9)` | 5 |
| `GREATEST(12, 5, 9)` | 12 |

Ví dụ theo từng hàng:

```sql
SELECT product_id,
       regular_price,
       sale_price,
       LEAST(regular_price, sale_price) AS effective_price,
       GREATEST(regular_price, sale_price) AS higher_price
FROM products;
```

Với mỗi sản phẩm, Oracle so sánh `REGULAR_PRICE` và `SALE_PRICE` của **chính hàng đó**. Một hàng không ảnh hưởng trực tiếp đến kết quả của hàng khác.

### 1.1. So sánh nhiều đối số

Hai hàm nhận từ hai biểu thức trở lên và có thể nhận nhiều biểu thức:

```sql
SELECT LEAST(25, 18, 31, 12, 20) AS least_value,
       GREATEST(25, 18, 31, 12, 20) AS greatest_value
FROM dual;
```

Kết quả là `12` và `31`. Khi viết biểu thức dài, nên xuống dòng hoặc dùng CTE/biểu thức có tên để người đọc nhận ra từng ngưỡng. Đừng truyền một danh sách kiểu dữ liệu lẫn lộn mà không kiểm soát thứ tự và conversion.

### 1.2. So sánh với MIN và MAX

Tên hàm dễ gây nhầm lẫn:

- **`LEAST(a, b)`**: so sánh nhiều biểu thức trong cùng một lần đánh giá, thường là trên một hàng.
- **`GREATEST(a, b)`**: tương tự, chọn giá trị lớn nhất trong các biểu thức cùng hàng.
- **`MIN(column)`**: hàm tổng hợp, tìm giá trị nhỏ nhất của một cột trên một nhóm hàng.
- **`MAX(column)`**: hàm tổng hợp, tìm giá trị lớn nhất của một cột trên một nhóm hàng.

Ví dụ:

```sql
-- Chọn giá thấp hơn giữa hai cột trên từng sản phẩm.
SELECT product_id, LEAST(regular_price, sale_price) AS lower_price
FROM products;

-- Chọn giá thấp nhất của toàn bộ sản phẩm.
SELECT MIN(regular_price) AS lowest_regular_price
FROM products;
```

`MIN`/`MAX` là aggregate functions và thông thường **bỏ qua các giá trị NULL** trong nhóm; nếu mọi giá trị đều NULL thì kết quả là NULL. `LEAST`/`GREATEST` trong Oracle có hành vi khác: **một đối số NULL có thể làm kết quả của cả hàm thành NULL**. Đây là khác biệt quan trọng khi chuyển logic từ aggregate sang scalar hoặc ngược lại.

## 2. Cú pháp và kiểu dữ liệu của đối số

Cú pháp tổng quát:

```sql
LEAST(expr1, expr2 [, expr3 ...])
GREATEST(expr1, expr2 [, expr3 ...])
```

Oracle cần so sánh các đối số theo một kiểu dữ liệu và quy tắc so sánh tương thích. Cách xác định kiểu có hai trường hợp chính:

1. **Nếu biểu thức đầu tiên có kiểu số:** Oracle xác định kiểu số có độ ưu tiên cao nhất trong danh sách, chuyển các đối số còn lại về kiểu số đó và trả về kiểu số có độ ưu tiên cao nhất.
2. **Nếu biểu thức đầu tiên không phải kiểu số:** Oracle chuyển các biểu thức sau về kiểu dữ liệu của biểu thức đầu tiên trước khi so sánh; kiểu trả về theo kiểu của biểu thức đầu tiên.

Vì vậy, **thứ tự đối số có thể làm thay đổi cả phép so sánh và kiểu kết quả**. Đối với danh sách có kiểu dữ liệu khác nhau, hãy đặt đối số đầu tiên theo kiểu nghiệp vụ mong muốn và dùng `CAST`, `TO_NUMBER`, `TO_DATE`, `TO_TIMESTAMP` tường minh khi cần.

## 3. LEAST và GREATEST với kiểu NUMBER

Với các đối số cùng kiểu số, hành vi trực quan:

```sql
SELECT LEAST(10, 20, 5) AS smallest_number,
       GREATEST(10, 20, 5) AS largest_number
FROM dual;
```

Kết quả là `5` và `20`.

### 3.1. Đối số số có kiểu khác nhau

Oracle có thứ tự ưu tiên kiểu số. Trong các kiểu số thường gặp, thứ tự ưu tiên là:

```text
BINARY_DOUBLE  >  BINARY_FLOAT  >  NUMBER
```

Nếu đối số đầu tiên là kiểu số, Oracle xét các đối số số trong danh sách để xác định kiểu có độ ưu tiên cao nhất, sau đó chuyển những đối số khác về kiểu đó.

Ví dụ minh họa:

```sql
SELECT LEAST(
           CAST(10 AS NUMBER),
           CAST(2.5 AS BINARY_DOUBLE),
           CAST(7 AS NUMBER)
       ) AS least_numeric
FROM dual;
```

Trong ví dụ, `BINARY_DOUBLE` có độ ưu tiên cao hơn `NUMBER`, nên kiểu số kết quả theo quy tắc numeric precedence là `BINARY_DOUBLE`. Nếu ứng dụng cần độ chính xác thập phân cho tiền tệ, không nên tùy tiện đưa `BINARY_FLOAT`/`BINARY_DOUBLE` vào biểu thức vốn dùng `NUMBER`; hãy dùng kiểu và bind phù hợp.

### 3.2. Tránh trộn NUMBER với chuỗi không kiểm soát

```sql
-- Oracle phải chuyển chuỗi '20' sang kiểu số vì đối số đầu tiên là NUMBER.
SELECT LEAST(10, '20') AS result
FROM dual;
```

Oracle có thể chuyển `'20'` thành số `20`, kết quả là `10`. Nhưng nếu chuỗi không biểu diễn số hợp lệ:

```sql
-- Có thể phát sinh lỗi chuyển kiểu, ví dụ ORA-01722.
SELECT LEAST(10, 'TWENTY')
FROM dual;
```

thì biểu thức không thể chuyển thành số và câu SQL có thể thất bại. Không dùng chuỗi ký tự làm số chỉ vì một bộ dữ liệu hiện tại đang chứa toàn ký tự số. Kiểu dữ liệu của cột, bind parameter và literal nên được khai báo nhất quán.

### 3.3. Đối số đầu tiên là CHAR: kết quả có thể khác

So sánh hai câu:

```sql
SELECT LEAST(10, '2') AS numeric_first,
       LEAST('10', 2) AS character_first
FROM dual;
```

Theo quy tắc kiểu dữ liệu:

- `LEAST(10, '2')`: đối số đầu tiên là số, nên Oracle chuyển `'2'` sang số; kết quả số là `2`.
- `LEAST('10', 2)`: đối số đầu tiên là ký tự, nên Oracle chuyển `2` sang kiểu ký tự để so sánh. Theo thứ tự ký tự thông thường, `'10'` đứng trước `'2'`, nên kết quả là chuỗi `'10'`.

| Biểu thức | Kiểu so sánh | Kết quả minh họa |
|---|---|---|
| `LEAST(10, '2')` | Số | `2` |
| `LEAST('10', 2)` | Ký tự | `'10'` |
| `GREATEST(10, '2')` | Số | `10` |
| `GREATEST('10', 2)` | Ký tự | `'2'` |

Đây là ví dụ quan trọng cho thấy **đổi vị trí đối số có thể đổi kết quả**. Không nên viết `LEAST(char_column, numeric_column)` nếu ý định nghiệp vụ là so sánh số; hãy chuyển kiểu tường minh hoặc sửa schema.

### 3.4. Chuyển chuỗi sang NUMBER tường minh

Nếu nguồn dữ liệu là ký tự nhưng có ý nghĩa số, hãy chuyển đổi trước khi so sánh:

```sql
SELECT LEAST(
           TO_NUMBER('125'),
           TO_NUMBER('80'),
           100
       ) AS least_amount
FROM dual;
```

Kết quả là `80` kiểu số. Với dữ liệu thực tế, nên dùng format model và NLS parameter rõ ràng nếu chuỗi chứa dấu thập phân hoặc dấu phân nhóm:

```sql
-- Ví dụ chuyển chuỗi dùng dấu phẩy thập phân, dấu chấm phân nhóm.
SELECT TO_NUMBER(
           '1.234,50',
           '9G999D99',
           'NLS_NUMERIC_CHARACTERS = '',.'''
       ) AS parsed_amount
FROM dual;
```

`NLS_NUMERIC_CHARACTERS = ',.'` quy định dấu phẩy là dấu thập phân và dấu chấm là dấu phân nhóm. Cú pháp chuỗi trong ví dụ được escape dấu nháy theo SQL Oracle. Khi parse dữ liệu nhập từ CSV/API, cần biết format của nguồn và không dựa vào `NLS_NUMERIC_CHARACTERS` ngầm của session.

## 4. LEAST và GREATEST với kiểu ký tự

Khi đối số đầu tiên là kiểu ký tự, Oracle chuyển các đối số còn lại về kiểu ký tự tương ứng trước khi so sánh. Do đó kết quả dựa trên **thứ tự so sánh chuỗi**, không phải giá trị số mà chuỗi có thể biểu diễn.

```sql
SELECT LEAST('100', '20', '3') AS least_text,
       GREATEST('100', '20', '3') AS greatest_text
FROM dual;
```

Theo thứ tự ký tự binary thường gặp, kết quả minh họa là `'100'` và `'3'`. Điều này khác so sánh số, nơi 3 là nhỏ nhất và 100 là lớn nhất.

### 4.1. So sánh chuỗi không phải so sánh số

```sql
SELECT LEAST('2', '10') AS result
FROM dual;
```

Kết quả theo so sánh ký tự thông thường là `'10'`, vì ký tự đầu tiên `'1'` đứng trước `'2'`. Nếu muốn kết quả số, viết:

```sql
SELECT LEAST(TO_NUMBER('2'), TO_NUMBER('10')) AS result
FROM dual;
```

Kết quả là số `2`. Đừng sửa dữ liệu kiểu ký tự bằng cách thêm số 0 đầu chuỗi chỉ để làm thứ tự từ điển giống thứ tự số nếu cột thực chất là dữ liệu số; giải pháp tốt hơn là lưu đúng datatype `NUMBER`.

### 4.2. Collation và NLS ảnh hưởng so sánh ký tự

Khi so sánh dữ liệu ký tự, Oracle áp dụng quy tắc so sánh/collation có hiệu lực cho biểu thức theo phiên bản và cấu hình. Thứ tự binary, linguistic, case-insensitive hoặc accent-insensitive có thể tạo kết quả khác nhau đối với chữ hoa/thường, dấu và ngôn ngữ.

Ví dụ, nếu một hệ thống có yêu cầu so sánh không phân biệt hoa thường hoặc dấu, không nên giả định `LEAST('a','B')` có cùng kết quả ở mọi collation. Cần xác định collation hoặc NLS settings đang áp dụng, sau đó kiểm thử trên đúng database. **Character set và collation là hai khái niệm khác nhau**: character set xác định cách biểu diễn ký tự; collation xác định cách so sánh và sắp xếp.

### 4.3. CHAR và VARCHAR2

`CHAR` có ngữ nghĩa độ dài cố định và có thể được đệm khoảng trắng; `VARCHAR2` lưu chuỗi độ dài biến đổi. Oracle có các quy tắc so sánh ký tự như padded/nonpadded semantics tùy kiểu biểu thức. Khi truyền các kiểu ký tự khác nhau vào `LEAST`/`GREATEST`, hãy chú ý kiểu của đối số đầu tiên và cách chuyển kiểu.

Trong các hệ thống có mã định danh dạng chuỗi, nên thống nhất datatype và quy tắc chuẩn hóa. Không để một cột `CHAR(10)` so sánh với `VARCHAR2` từ client mà không hiểu tác động của khoảng trắng cuối.

### 4.4. UPPER/LOWER không tự biến phép so sánh thành ngôn ngữ tự nhiên

Có thể viết:

```sql
SELECT LEAST(UPPER(code_a), UPPER(code_b)) AS least_upper_code
FROM lab_codes;
```

nhưng kết quả vẫn là phép so sánh theo quy tắc collation áp dụng cho chuỗi sau khi chuyển hoa. Nó không tự loại dấu, chuẩn hóa Unicode hoặc giải quyết mọi quy tắc locale. Nếu cần quy tắc ngôn ngữ, hãy xác định rõ NLS/collation và bảo đảm các biểu thức được xử lý nhất quán.

## 5. LEAST và GREATEST với DATE/TIMESTAMP

Hai hàm có thể chọn giá trị ngày/giờ sớm nhất hoặc muộn nhất khi các đối số có kiểu tương thích.

```sql
SELECT LEAST(
           DATE '2026-11-01',
           DATE '2026-11-15',
           DATE '2026-11-10'
       ) AS earliest_date,
       GREATEST(
           DATE '2026-11-01',
           DATE '2026-11-15',
           DATE '2026-11-10'
       ) AS latest_date
FROM dual;
```

Kết quả là `2026-11-01` và `2026-11-15`. Oracle `DATE` chứa cả ngày và giờ đến giây, dù literal `DATE 'YYYY-MM-DD'` bắt đầu tại 00:00:00.

### 5.1. Dùng LEAST để tìm ngày bắt đầu sớm hơn

```sql
SELECT booking_id,
       LEAST(check_in_date, requested_date) AS effective_start
FROM bookings;
```

Mỗi hàng trả về ngày sớm hơn giữa ngày check-in và ngày được yêu cầu. Nếu một trong hai cột có `NULL`, kết quả `LEAST` sẽ là `NULL`; không mặc định Oracle tự chọn ngày còn lại.

### 5.2. Dùng GREATEST để giới hạn thời điểm

```sql
SELECT booking_id,
       GREATEST(valid_from, DATE '2026-01-01') AS effective_from
FROM subscriptions;
```

Biểu thức lấy ngày muộn hơn giữa `VALID_FROM` và mốc 01/01/2026. Nếu `VALID_FROM` có `NULL`, kết quả vẫn là `NULL`; nếu nghiệp vụ coi `NULL` là “không giới hạn” hoặc “chưa thiết lập”, cần viết logic riêng.

### 5.3. Tránh chuỗi ngày phụ thuộc NLS_DATE_FORMAT

Không nên dựa vào chuyển kiểu ngầm định từ chuỗi:

```sql
-- Không khuyến nghị: phụ thuộc NLS_DATE_FORMAT của session.
SELECT LEAST('01/02/2026', DATE '2026-02-10')
FROM dual;
```

Chuỗi `'01/02/2026'` có thể được hiểu khác nhau theo format session hoặc không chuyển được. Hãy dùng date literal hoặc `TO_DATE` với format rõ:

```sql
SELECT LEAST(
           TO_DATE('01/02/2026', 'DD/MM/YYYY'),
           DATE '2026-02-10'
       ) AS earliest_date
FROM dual;
```

Kết quả là ngày 01/02/2026. Cách này nêu rõ chuỗi nguồn dùng `DD/MM/YYYY`.

### 5.4. DATE và TIMESTAMP cần CAST rõ ràng

`DATE`, `TIMESTAMP`, `TIMESTAMP WITH TIME ZONE` và `TIMESTAMP WITH LOCAL TIME ZONE` có độ chính xác và quy tắc timezone khác nhau. Không nên trộn chúng tùy tiện trong `LEAST`/`GREATEST`, vì Oracle có thể chuyển đổi theo kiểu của đối số đầu tiên hoặc quy tắc datatype tương ứng, làm mất phần fractional seconds hoặc thay đổi cách diễn giải timezone.

Nếu nghiệp vụ yêu cầu so sánh timestamp, hãy chuyển các đối số về cùng kiểu rõ ràng, ví dụ:

```sql
SELECT LEAST(
           CAST(start_time AS TIMESTAMP),
           CAST(end_time AS TIMESTAMP)
       ) AS earlier_timestamp
FROM lab_schedule;
```

Đây là ví dụ trên bảng `LAB_SCHEDULE` giả định. Nếu dữ liệu có timezone, phải thống nhất mốc thời gian (ví dụ UTC) và dùng datatype có timezone phù hợp; `CAST` đơn thuần không thay thế quyết định nghiệp vụ về timezone.

## 6. NULL: điểm dễ gây bất ngờ nhất

Trong Oracle SQL, `NULL` thể hiện giá trị chưa biết hoặc không được cung cấp. Với `LEAST` và `GREATEST`, **nếu một đối số là `NULL`, kết quả của hàm là `NULL`**.

```sql
SELECT LEAST(10, NULL, 20) AS least_value,
       GREATEST(10, NULL, 20) AS greatest_value
FROM dual;
```

Kết quả của cả hai biểu thức là `NULL`.

### 6.1. Một cột NULL làm kết quả cả hàm NULL

Giả sử bảng `PRODUCT_PRICES` có `REGULAR_PRICE` và `SALE_PRICE`:

| Product | Regular price | Sale price | `LEAST(regular_price, sale_price)` |
|---|---:|---:|---|
| A | 100 | 80 | 80 |
| B | 150 | `NULL` | `NULL` |
| C | `NULL` | 90 | `NULL` |
| D | `NULL` | `NULL` | `NULL` |

Nếu `SALE_PRICE` chưa có giá trị, `LEAST` không tự hiểu rằng cần lấy `REGULAR_PRICE`. Hàm chỉ biết một đối số chưa xác định nên kết quả chưa xác định theo quy tắc null propagation.

### 6.2. NULL khác 0 và khác một giá trị mặc định

Không nên giả định `NULL` tương đương 0:

```sql
SELECT LEAST(100, NULL) AS result
FROM dual;
```

Kết quả là `NULL`, không phải 0 và cũng không phải 100. Nếu nghiệp vụ muốn coi giá chưa có là 0, phải thể hiện rõ bằng `NVL`/`COALESCE`, nhưng cần đánh giá ý nghĩa. Với giá bán, thay giá chưa biết thành 0 có thể làm báo cáo cho rằng sản phẩm miễn phí.

### 6.3. Bảng chân trị không phải cơ chế của LEAST/GREATEST

`LEAST`/`GREATEST` không trả `TRUE/FALSE/UNKNOWN`; chúng trả về **một giá trị có kiểu dữ liệu của biểu thức** hoặc `NULL`. Logic ba giá trị xuất hiện khi kết quả đó được dùng trong một điều kiện so sánh:

```sql
SELECT product_id
FROM products
WHERE LEAST(regular_price, sale_price) < 100;
```

Nếu `LEAST(...)` trả `NULL`, phép `< 100` trở thành `UNKNOWN`, nên hàng không được chọn trong `WHERE`.

## 7. Cách xử lý NULL tùy theo nghiệp vụ

Không có một cách thay `NULL` duy nhất đúng cho mọi bài toán. Trước khi dùng `NVL`, `COALESCE` hoặc `CASE`, cần trả lời: **NULL có nghĩa là thiếu dữ liệu, không áp dụng, chưa biết hay không giới hạn?**

### 7.1. NVL: thay NULL bằng giá trị mặc định

`NVL(expr1, expr2)` trả `expr2` khi `expr1` là `NULL`, nếu không trả `expr1`.

```sql
SELECT LEAST(
           NVL(regular_price, 999999),
           NVL(sale_price, 999999)
       ) AS lowest_available_price
FROM product_prices;
```

Ví dụ dùng giá trị lớn `999999` như một **sentinel** để một giá còn lại được chọn nếu giá kia chưa có. Nhưng sentinel chỉ hợp lệ nếu miền giá thực tế luôn thấp hơn ngưỡng đó và ý nghĩa `NULL` thực sự là “không có ứng viên”. Nếu giá có thể lớn hơn, hoặc `NULL` mang nghĩa “chưa xác định”, cách này có thể sai.

`NVL` còn có quy tắc chuyển kiểu riêng dựa trên đối số đầu tiên và numeric precedence; không nên truyền các kiểu không tương thích rồi dựa vào implicit conversion.

### 7.2. COALESCE: chọn biểu thức đầu tiên không NULL

`COALESCE(expr1, expr2, ...)` trả về biểu thức đầu tiên không `NULL` theo thứ tự. Nó thường dễ đọc khi có nhiều nguồn fallback:

```sql
SELECT COALESCE(sale_price, regular_price, list_price) AS chosen_price
FROM product_prices;
```

Đây là **chọn ưu tiên theo thứ tự**, không phải chọn giá nhỏ nhất. Nếu `SALE_PRICE` có giá trị thì trả nó ngay, kể cả khi `REGULAR_PRICE` thấp hơn. Không dùng `COALESCE` thay `LEAST` nếu nghiệp vụ cần so sánh mọi giá trị.

### 7.3. COALESCE kết hợp LEAST/GREATEST

Nếu muốn lấy giá nhỏ nhất trong các giá **đã biết**, một cách có thể dùng là lọc/loại null trước hoặc thay thế có kiểm soát. Với hai cột, `CASE` diễn đạt rõ:

```sql
SELECT product_id,
       CASE
           WHEN regular_price IS NULL THEN sale_price
           WHEN sale_price IS NULL THEN regular_price
           ELSE LEAST(regular_price, sale_price)
       END AS lowest_known_price
FROM product_prices;
```

Kết quả:

- Cả hai có giá: lấy giá nhỏ hơn.
- Chỉ có giá niêm yết: lấy giá niêm yết.
- Chỉ có giá khuyến mãi: lấy giá khuyến mãi.
- Cả hai `NULL`: trả `NULL`.

Đây là quy tắc **“bỏ qua một giá chưa biết nếu còn giá kia”**. Nếu nghiệp vụ cần “không thể kết luận giá thấp nhất khi bất kỳ giá nào chưa được cập nhật”, thì nên giữ nguyên hành vi null propagation của `LEAST`.

### 7.4. GREATEST với NULL và mốc không giới hạn

Giả sử một hợp đồng có `valid_from` và `valid_until`. Nếu `VALID_UNTIL = NULL` nghĩa là “không có ngày hết hạn”, không thể mặc nhiên viết:

```sql
GREATEST(valid_from, valid_until)
```

vì kết quả sẽ là `NULL`. Cần diễn đạt nghiệp vụ rõ ràng, ví dụ chọn ngày bắt đầu hiệu lực muộn hơn giữa ngày bắt đầu và mốc kiểm tra:

```sql
SELECT contract_id,
       GREATEST(valid_from, DATE '2026-01-01') AS effective_start
FROM contracts;
```

Nếu cần tính ngày kết thúc lớn nhất nhưng `NULL` biểu thị vô thời hạn, phải định nghĩa quy tắc riêng (ví dụ trả một trạng thái `UNBOUNDED` hoặc không trả ngày kết thúc). Không dùng một sentinel ngày xa trong tương lai nếu ứng dụng có thể diễn giải nhầm thành ngày hết hạn thật.

### 7.5. CASE để giữ nguyên ba trường hợp

Khi nghiệp vụ phức tạp, `CASE` thường dễ kiểm soát hơn:

```sql
SELECT product_id,
       CASE
           WHEN regular_price IS NULL AND sale_price IS NULL THEN NULL
           WHEN regular_price IS NULL THEN sale_price
           WHEN sale_price IS NULL THEN regular_price
           WHEN regular_price <= sale_price THEN regular_price
           ELSE sale_price
       END AS lowest_known_price
FROM product_prices;
```

Biểu thức này giữ nguyên kiểu `NUMBER` nếu các cột là `NUMBER`, đồng thời biểu đạt chính sách rõ ràng. Khi có ba hoặc nhiều cột, có thể dùng `UNPIVOT`, `CROSS APPLY`/`LATERAL` hoặc cấu trúc dữ liệu phù hợp để lọc null rồi lấy `MIN`, nhưng cần cân nhắc độ phức tạp và hiệu năng.

## 8. So sánh LEAST/GREATEST với MIN/MAX aggregate

Sự khác biệt về `NULL` có thể tóm tắt:

| Tình huống | `LEAST(a, b)` | `MIN(a)` trong nhóm |
|---|---|---|
| `a=10`, `b=5` | 5 | Aggregate phụ thuộc các hàng của cột |
| Một đối số/giá trị NULL | Hàm scalar trả NULL nếu có đối số NULL | `MIN` bỏ qua NULL khi còn giá trị không null |
| Tất cả giá trị NULL | NULL | NULL |
| Nhiều hàng | Tính từng hàng khi gọi trong SELECT | Tổng hợp nhiều hàng trong nhóm |

Ví dụ trên một bảng giả định:

```sql
-- Chọn giá thấp hơn trong từng hàng, rồi tìm giá thấp nhất giữa các hàng.
SELECT MIN(LEAST(price_a, price_b)) AS lowest_row_price
FROM lab_compare_prices;
```

Trong truy vấn này, nếu một hàng có `PRICE_A` hoặc `PRICE_B` là `NULL`, `LEAST` của hàng đó là `NULL`; sau đó `MIN` ở tầng aggregate bỏ qua kết quả null đó nếu còn kết quả khác. Đây là hai tầng xử lý khác nhau. Nếu cần bỏ qua null ở cấp từng hàng, hãy dùng `CASE` như phần trước.

## 9. Chuyển kiểu ngầm định và lỗi thường gặp

Oracle cho phép chuyển kiểu ngầm định trong một số biểu thức, nhưng dựa vào conversion ngầm có thể gây lỗi hoặc thay đổi kết quả khi dữ liệu, NLS hay thứ tự đối số thay đổi.

### 9.1. Chuỗi số không hợp lệ

```sql
SELECT LEAST(100, 'ABC')
FROM dual;
```

Vì đối số đầu tiên là số, Oracle cố chuyển `'ABC'` sang số. Việc chuyển đổi thất bại, thường dẫn đến `ORA-01722: invalid number`. Lỗi có thể chỉ xuất hiện khi dữ liệu có một giá trị xấu, nên môi trường test nhỏ có thể không phát hiện.

### 9.2. Chuỗi ngày phụ thuộc NLS_DATE_FORMAT

```sql
-- Không khuyến nghị: chuỗi ngày không có format rõ.
SELECT LEAST(DATE '2026-01-01', '02/01/2026')
FROM dual;
```

Nếu đối số đầu tiên là `DATE`, Oracle cần chuyển chuỗi còn lại sang DATE theo quy tắc chuyển đổi ngầm và định dạng session. Một session có `DD/MM/YYYY`, session khác `MM/DD/YYYY` có thể diễn giải khác; hoặc chuỗi có thể gây lỗi chuyển ngày. Hãy dùng `TO_DATE` có format mask:

```sql
SELECT LEAST(
           DATE '2026-01-01',
           TO_DATE('02/01/2026', 'DD/MM/YYYY')
       ) AS earliest_date
FROM dual;
```

### 9.3. Không tương thích datatype

Nếu các đối số thuộc nhóm kiểu dữ liệu không thể chuyển đổi hợp lệ, Oracle có thể báo lỗi kiểu dữ liệu không nhất quán, chẳng hạn `ORA-00932`. Cần kiểm tra kiểu cột bằng data dictionary và xác định conversion hợp lệ trước khi dùng hàm.

```sql
SELECT column_name, data_type, data_length, data_precision, data_scale
FROM user_tab_columns
WHERE table_name = 'PRODUCT_PRICES'
ORDER BY column_id;
```

### 9.4. Quy tắc chuyển kiểu của đối số đầu tiên

| Danh sách | Kiểu của đối số đầu | Cách Oracle xử lý chính | Rủi ro |
|---|---|---|---|
| `LEAST(10, '20')` | NUMBER | Chuyển chuỗi sang NUMBER | Chuỗi không phải số gây lỗi |
| `LEAST('10', 20)` | Ký tự | Chuyển số sang kiểu ký tự | So sánh từ điển, không phải số |
| `LEAST(date_col, '2026-01-01')` | DATE | Chuyển chuỗi sang DATE | Phụ thuộc NLS nếu không format rõ |
| `LEAST('2026-01-01', date_col)` | Ký tự | Chuyển DATE sang ký tự | So sánh chuỗi, định dạng ngày ảnh hưởng |
| `LEAST(number_col, binary_double_expr)` | Số | Chọn numeric precedence cao nhất | Có thể đổi độ chính xác/kiểu kết quả |

Để truy vấn dễ bảo trì, **các đối số nên có cùng datatype và cùng ý nghĩa**. Nếu khác kiểu, hãy dùng `CAST` hoặc hàm chuyển đổi tường minh, đồng thời xác định rõ kiểu kết quả mong muốn.

## 10. Ảnh hưởng của NLS và collation

NLS (National Language Support) điều khiển nhiều quy tắc theo ngôn ngữ/vùng, chẳng hạn định dạng số/ngày, ngôn ngữ sort và so sánh. Đối với `LEAST`/`GREATEST`:

- Nếu so sánh số, NLS có thể ảnh hưởng **chuyển chuỗi sang số** khi implicit conversion diễn ra.
- Nếu so sánh ngày, NLS có thể ảnh hưởng **chuyển chuỗi sang DATE** khi không dùng format mask.
- Nếu so sánh ký tự, collation/quy tắc linguistic áp dụng cho biểu thức có thể ảnh hưởng thứ tự chữ hoa/thường, dấu và ngôn ngữ.

Kiểm tra thiết lập session khi điều tra kết quả không nhất quán:

```sql
SELECT parameter, value
FROM nls_session_parameters
WHERE parameter IN (
    'NLS_DATE_FORMAT',
    'NLS_DATE_LANGUAGE',
    'NLS_NUMERIC_CHARACTERS',
    'NLS_SORT',
    'NLS_COMP'
)
ORDER BY parameter;
```

Các tham số session có thể khác giữa SQL client và connection pool của ứng dụng. Không nên giả định truy vấn chạy trong SQL Developer sẽ luôn chuyển kiểu giống truy vấn từ JDBC.

### 10.1. Không dựa vào NLS mặc định cho dữ liệu nhập

Nếu API gửi ngày dưới dạng chuỗi, parse thành kiểu ngày ở tầng ứng dụng hoặc dùng `TO_DATE(:text, 'YYYY-MM-DD')` theo contract rõ. Nếu API gửi số thập phân dưới dạng chuỗi, dùng `TO_NUMBER` với format/NLS phù hợp hoặc parse thành `BigDecimal` trước khi bind. **Đừng để `LEAST`/`GREATEST` tự đoán kiểu dữ liệu đầu vào từ string.**

### 10.2. Character set khác collation

Database có `AL32UTF8` không tự làm phép so sánh chuỗi trở thành case-insensitive hoặc accent-insensitive. Character set quyết định khả năng biểu diễn ký tự; collation quyết định quy tắc so sánh. Khi dùng `LEAST`/`GREATEST` trên chuỗi đa ngôn ngữ, cần xác định collation áp dụng thay vì chỉ nhìn `NLS_CHARACTERSET`.

## 11. Sử dụng LEAST/GREATEST trong biểu thức nghiệp vụ

### 11.1. Giới hạn giá trị trong một khoảng (clamp)

Một bài toán phổ biến là ép một giá trị nằm trong khoảng `[min_value, max_value]`:

```sql
SELECT input_value,
       GREATEST(min_value,
           LEAST(input_value, max_value)
       ) AS clamped_value
FROM lab_ranges;
```

Logic:

1. `LEAST(input_value, max_value)` giới hạn phía trên: nếu input vượt max, lấy max.
2. `GREATEST(min_value, ...)` giới hạn phía dưới: nếu kết quả nhỏ hơn min, lấy min.

Ví dụ:

| Min | Input | Max | Clamp |
|---:|---:|---:|---:|
| 0 | -5 | 100 | 0 |
| 0 | 40 | 100 | 40 |
| 0 | 150 | 100 | 100 |

Nếu bất kỳ đối số nào có thể `NULL`, toàn bộ biểu thức có thể thành `NULL`. Phải quyết định trước khi dùng clamp rằng `NULL` có phải lỗi dữ liệu, giá trị mặc định hay trạng thái chưa biết.

### 11.2. Chọn giá nhỏ hơn giữa giá niêm yết và giá khuyến mãi

```sql
SELECT product_id,
       LEAST(list_price, promotion_price) AS display_price
FROM product_prices;
```

Chỉ dùng trực tiếp khi cả hai cột bắt buộc có giá trị. Nếu `PROMOTION_PRICE` chỉ có khi sản phẩm được khuyến mãi và để `NULL` khi không có, biểu thức trên trả NULL cho sản phẩm không khuyến mãi. Nếu muốn giá hiển thị là giá niêm yết trong trường hợp không khuyến mãi, dùng:

```sql
SELECT product_id,
       COALESCE(LEAST(list_price, promotion_price), list_price) AS display_price
FROM product_prices;
```

Biểu thức trên vẫn có một giả định: nếu `LIST_PRICE` cũng `NULL`, kết quả vẫn `NULL`; nếu promotion price là giá thấp hơn thì lấy promotion. Cần kiểm tra `LIST_PRICE NOT NULL` hoặc viết `CASE` rõ nếu cả hai cột có thể thiếu.

### 11.3. Chọn thời điểm sớm nhất giữa nhiều mốc

```sql
SELECT task_id,
       LEAST(planned_start, approved_start, actual_start) AS earliest_start
FROM task_schedule;
```

Nếu một mốc chưa được nhập, kết quả là `NULL`. Nếu nghiệp vụ muốn lấy mốc sớm nhất **trong các mốc đã biết**, phải xử lý null rõ ràng. Với ba cột, có thể dùng biểu thức `CASE`, hoặc chuẩn hóa các mốc thành hàng rồi dùng `MIN` trên tập giá trị không null. Lựa chọn phụ thuộc khả năng mở rộng và hiệu năng.

### 11.4. Tính hạn xử lý nhỏ nhất giữa SLA và deadline

```sql
SELECT ticket_id,
       LEAST(sla_deadline, customer_deadline) AS effective_deadline
FROM support_tickets;
```

Truy vấn chọn deadline sớm hơn. Nhưng nếu khách hàng không đặt deadline (`CUSTOMER_DEADLINE = NULL`), Oracle trả NULL; nếu ý nghĩa của NULL là “không có deadline bổ sung”, có thể muốn dùng `SLA_DEADLINE`. Đây là quyết định nghiệp vụ cần diễn đạt tường minh bằng `CASE`/`COALESCE`, không để người đọc đoán từ tên hàm.

## 12. JDBC và bind parameter: tránh conversion ngầm

Ứng dụng Java nên bind giá trị đúng kiểu thay vì truyền mọi thứ thành chuỗi. Ví dụ dùng `LEAST` trên hai tham số số:

```java
String sql = "SELECT LEAST(?, ?) AS lower_value FROM dual";

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setBigDecimal(1, new BigDecimal("125.50"));
    ps.setBigDecimal(2, new BigDecimal("80.25"));

    try (ResultSet rs = ps.executeQuery()) {
        if (rs.next()) {
            BigDecimal value = rs.getBigDecimal("lower_value");
            System.out.println(value);
        }
    }
}
```

Kết quả là `80.25`. `BigDecimal` phù hợp cho dữ liệu tiền tệ cần độ chính xác thập phân; không nên dùng `double` cho mọi phép tính tiền.

### 12.1. Bind DATE/TIMESTAMP bằng kiểu tương ứng

```java
String sql = "SELECT LEAST(?, ?) AS earlier_date FROM dual";

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setDate(1, java.sql.Date.valueOf("2026-11-01"));
    ps.setDate(2, java.sql.Date.valueOf("2026-11-15"));

    try (ResultSet rs = ps.executeQuery()) {
        if (rs.next()) {
            java.sql.Date earlier = rs.getDate("earlier_date");
        }
    }
}
```

Đối với timestamp có phần giờ/phút/giây hoặc timezone, chọn API JDBC phù hợp (`setTimestamp`, `setObject` với kiểu Java time được driver hỗ trợ, v.v.) và thống nhất timezone. Không bind chuỗi `'01/11/2026'` cho một biểu thức ngày nếu có thể bind `DATE` trực tiếp.

### 12.2. Bind NULL phải có kiểu

Nếu tham số có thể `NULL`, JDBC cần truyền kiểu SQL thích hợp khi dùng `setNull`:

```java
ps.setNull(1, java.sql.Types.NUMERIC);
```

hoặc dùng `setObject(index, null, sqlType)` theo driver/framework hỗ trợ. Bind null không đúng kiểu có thể dẫn đến lỗi suy luận kiểu hoặc chuyển đổi không mong muốn. Và nếu một đối số `LEAST`/`GREATEST` là null, kết quả hàm có thể null; ứng dụng phải xử lý kết quả nullable bằng `getBigDecimal`/`getDate` và `wasNull()` khi API đọc kiểu primitive.

### 12.3. Không nối literal do người dùng nhập

Tránh:

```java
// Không khuyến nghị: nối chuỗi người dùng vào SQL.
String sql = "SELECT LEAST(" + inputA + ", " + inputB + ") FROM dual";
```

Dùng bind parameters giúp tránh SQL injection và đảm bảo datatype được gửi theo contract. Tuy nhiên bind chỉ thay **giá trị**, không thay tên cột/tên bảng hoặc từ khóa SQL; những phần cấu trúc phải được chọn từ danh sách cho phép.

## 13. Các lỗi thường gặp

| Triệu chứng/lỗi | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Kết quả `LEAST` là NULL dù một giá trị có dữ liệu | Có ít nhất một đối số NULL | Xác định ý nghĩa NULL; dùng CASE/COALESCE nếu muốn bỏ qua NULL |
| Kết quả `LEAST('10','2')` là `'10'` | So sánh ký tự, không phải số | Chuyển kiểu số tường minh hoặc sửa schema |
| `ORA-01722: invalid number` | Chuỗi được chuyển sang số nhưng có giá trị không hợp lệ | Kiểm tra dữ liệu, dùng conversion có kiểm soát và format rõ |
| `ORA-01861`/lỗi ngày tháng | Chuỗi ngày không khớp format khi implicit conversion | Dùng `DATE` literal hoặc `TO_DATE` có format mask |
| `ORA-00932: inconsistent datatypes` | Các đối số không thể chuyển về kiểu tương thích | Kiểm tra datatype, `CAST` rõ ràng |
| Kết quả khác giữa SQL client và ứng dụng | NLS session, bind datatype hoặc timezone khác | So sánh session parameters và kiểu bind |
| So sánh chuỗi cho kết quả bất ngờ | Collation, thứ tự binary/linguistic, CHAR/VARCHAR2 | Xác định collation và test chuỗi thực |
| Dùng MIN thay LEAST làm thay đổi kết quả với NULL | MIN aggregate bỏ qua NULL, LEAST scalar truyền NULL ra kết quả | Chọn đúng loại hàm theo cấp hàng hay nhóm |
| Clamp trả NULL | Một trong các đối số min/input/max NULL | Định nghĩa chính sách dữ liệu thiếu trước khi clamp |

Mã lỗi cụ thể phụ thuộc biểu thức và datatype thực tế. Không bắt lỗi bằng cách tự động thay mọi NULL thành 0 hoặc chuỗi rỗng; điều đó có thể che lỗi dữ liệu và làm sai nghiệp vụ.

## 14. Thực hành Oracle SQL

Bài thực hành dùng bảng giả `LAB_LEAST_GREATEST`. Chỉ chạy trong schema **DEV/TEST** được cấp quyền `CREATE TABLE` và quota. Xác minh container/service trước khi chạy; không dùng dữ liệu thật hoặc chạy DDL trên production.

### Bước 1 — Xác nhận môi trường

```sql
SELECT SYS_CONTEXT('USERENV', 'CON_NAME') AS container_name,
       SYS_CONTEXT('USERENV', 'SERVICE_NAME') AS service_name,
       SYS_CONTEXT('USERENV', 'SESSION_USER') AS session_user
FROM dual;
```

### Bước 2 — Tạo bảng và dữ liệu

```sql
CREATE TABLE lab_least_greatest (
    item_id NUMBER PRIMARY KEY,
    price_a NUMBER(10, 2),
    price_b NUMBER(10, 2),
    start_date DATE,
    end_date DATE,
    code_a VARCHAR2(20 CHAR),
    code_b VARCHAR2(20 CHAR)
);

INSERT ALL
    INTO lab_least_greatest VALUES
        (1, 100, 80, DATE '2026-11-01', DATE '2026-11-10', 'A10', 'A20')
    INTO lab_least_greatest VALUES
        (2, 150, NULL, DATE '2026-11-05', DATE '2026-11-03', 'B20', 'B10')
    INTO lab_least_greatest VALUES
        (3, NULL, 90, NULL, DATE '2026-11-08', 'C30', 'C20')
    INTO lab_least_greatest VALUES
        (4, NULL, NULL, DATE '2026-11-04', NULL, NULL, 'D10')
SELECT 1 FROM dual;

COMMIT;
```

### Bước 3 — So sánh từng hàng

```sql
SELECT item_id,
       price_a,
       price_b,
       LEAST(price_a, price_b) AS least_price,
       GREATEST(price_a, price_b) AS greatest_price
FROM lab_least_greatest
ORDER BY item_id;
```

Quan sát:

- Hàng 1: kết quả lần lượt 80 và 100.
- Hàng 2: cả hai biểu thức là NULL do `PRICE_B` NULL.
- Hàng 3: cả hai biểu thức là NULL do `PRICE_A` NULL.
- Hàng 4: cả hai biểu thức là NULL do cả hai đối số NULL.

### Bước 4 — Chọn giá đã biết theo quy tắc nghiệp vụ

```sql
SELECT item_id,
       CASE
           WHEN price_a IS NULL THEN price_b
           WHEN price_b IS NULL THEN price_a
           ELSE LEAST(price_a, price_b)
       END AS least_known_price
FROM lab_least_greatest
ORDER BY item_id;
```

Kết quả lần lượt: 80, 150, 90, NULL. Giải thích tại sao hàng 2 và 3 có kết quả khác câu truy vấn ở bước 3.

### Bước 5 — So sánh ngày

```sql
SELECT item_id,
       start_date,
       end_date,
       LEAST(start_date, end_date) AS earlier_date,
       GREATEST(start_date, end_date) AS later_date
FROM lab_least_greatest
ORDER BY item_id;
```

Hàng 1 có earlier date là 01/11 và later date là 10/11; hàng 2 có ngày 03/11 và 05/11; hàng 3 và 4 trả NULL do có ít nhất một mốc NULL. Nếu yêu cầu “lấy mốc đã biết sớm nhất”, hãy viết logic bỏ qua null riêng.

### Bước 6 — Thử chuyển kiểu

```sql
SELECT LEAST(10, '2') AS numeric_result,
       LEAST('10', 2) AS character_result
FROM dual;
```

Quan sát khác biệt kiểu và kết quả. Sau đó thử trên **một câu lệnh riêng trong môi trường lab** với chuỗi không chuyển được:

```sql
-- Cố tình gây lỗi conversion; không đưa vào script chạy tự động.
SELECT LEAST(10, 'TEN') FROM dual;
```

Ghi nhận mã lỗi thực tế và giải thích vì sao đối số đầu tiên là NUMBER khiến Oracle chuyển chuỗi sang số.

### Bước 7 — So sánh scalar với aggregate

```sql
SELECT MIN(price_a) AS min_price_a,
       MAX(price_a) AS max_price_a,
       MIN(LEAST(price_a, price_b)) AS min_of_row_least
FROM lab_least_greatest;
```

Giải thích vì sao `MIN(price_a)` có thể trả về một giá trị dù có các hàng NULL, trong khi `LEAST(price_a, price_b)` ở các hàng đó là NULL và bị `MIN` ở tầng ngoài bỏ qua.

### Bước 8 — Dọn dữ liệu thực hành

Chỉ khi đã xác nhận đúng bảng lab do mình tạo trong DEV/TEST và không có người khác sử dụng:

```sql
DROP TABLE lab_least_greatest PURGE;
```

Đây là thao tác DDL xóa object/dữ liệu và không đưa vào recycle bin. Không chạy trên production hoặc bất kỳ bảng nào ngoài phạm vi thực hành.

## 15. Checklist tư duy trước khi dùng LEAST/GREATEST

Trước khi đưa biểu thức vào view, report, stored procedure hoặc API, hãy tự trả lời:

1. Tôi đang so sánh **nhiều cột trên cùng một hàng** hay cần tổng hợp **nhiều hàng**? Nếu là nhiều hàng, có thể cần `MIN`/`MAX`.
2. Tất cả đối số có cùng datatype không? Nếu không, kiểu của đối số đầu tiên sẽ làm thay đổi conversion thế nào?
3. Nếu một đối số là NULL, kết quả NULL có đúng nghiệp vụ không?
4. Nếu muốn bỏ qua NULL, quy tắc là lấy giá trị còn lại, dùng giá trị mặc định hay báo dữ liệu chưa đầy đủ?
5. Có chuỗi số/ngày đang phụ thuộc NLS session không? Có thể dùng `TO_NUMBER`, `TO_DATE`, `CAST` rõ ràng không?
6. Với chuỗi Unicode, collation và locale có phù hợp với yêu cầu so sánh không?
7. Ứng dụng JDBC bind đúng kiểu (`BigDecimal`, `Date`, `Timestamp`) và xử lý kết quả nullable chưa?
8. Truy vấn có dùng trên bảng lớn không? Cần kiểm tra plan và chi phí khi hàm xuất hiện trong predicate hay không?

## 16. Câu hỏi ôn tập

**Câu 1.** `LEAST(10, 5, 20)` trả về gì?

**Đáp án:** `5`, giá trị nhỏ nhất trong các đối số số.

**Câu 2.** `GREATEST(10, NULL, 20)` trả về gì trong Oracle?

**Đáp án:** `NULL`, vì có một đối số NULL.

**Câu 3.** Vì sao `LEAST(10, '2')` có thể trả 2 nhưng `LEAST('10', 2)` có thể trả `'10'`?

**Đáp án:** Đối số đầu tiên là NUMBER trong câu đầu nên Oracle chuyển chuỗi sang số; đối số đầu tiên là ký tự trong câu sau nên Oracle chuyển số sang kiểu ký tự và so sánh theo thứ tự chuỗi.

**Câu 4.** `LEAST` khác `MIN` như thế nào khi có NULL?

**Đáp án:** `LEAST` trả NULL nếu có một đối số NULL; `MIN` aggregate bỏ qua giá trị NULL nếu trong nhóm còn giá trị không null.

**Câu 5.** Vì sao `LEAST(DATE '2026-01-01', '02/01/2026')` có thể phụ thuộc session?

**Đáp án:** Chuỗi ngày có thể được chuyển ngầm sang DATE theo `NLS_DATE_FORMAT`; dùng `TO_DATE` với format mask rõ ràng.

**Câu 6.** Muốn lấy giá nhỏ nhất trong hai cột, nhưng bỏ qua một cột NULL nếu cột còn lại có giá trị, nên viết gì?

**Đáp án:** Có thể dùng `CASE` kiểm tra từng cột NULL rồi mới gọi `LEAST` khi cả hai có giá trị.

**Câu 7.** `COALESCE(sale_price, regular_price)` có nghĩa là lấy giá nhỏ nhất không?

**Đáp án:** Không. Nó lấy giá trị đầu tiên không NULL theo thứ tự đối số; không so sánh độ lớn.

**Câu 8.** Khi so sánh chuỗi bằng `LEAST`, `AL32UTF8` có bảo đảm không phân biệt hoa thường không?

**Đáp án:** Không. Character set và collation là hai khái niệm khác nhau; phải xem collation/NLS rules áp dụng.

**Câu 9.** Vì sao JDBC nên bind ngày và số đúng datatype thay vì bind chuỗi?

**Đáp án:** Tránh implicit conversion phụ thuộc NLS, giảm lỗi định dạng và giúp contract dữ liệu rõ ràng.

**Câu 10.** `LEAST` và `GREATEST` có tự động bỏ qua các đối số NULL như MIN/MAX không?

**Đáp án:** Không. Trong Oracle, một đối số NULL có thể làm kết quả scalar function thành NULL; muốn bỏ qua phải viết logic riêng.

## Kết luận

**`LEAST` chọn giá trị nhỏ nhất và `GREATEST` chọn giá trị lớn nhất trong các biểu thức được truyền vào, thường là trên từng hàng.** Chúng khác `MIN`/`MAX` aggregate về phạm vi tính toán và đặc biệt khác ở cách xử lý `NULL`: trong Oracle, một đối số NULL làm kết quả của `LEAST`/`GREATEST` thành NULL. Nếu nghiệp vụ muốn bỏ qua giá trị chưa biết hoặc thay bằng mặc định, hãy thể hiện rõ bằng `CASE`, `COALESCE` hoặc `NVL`.

Quy tắc chuyển kiểu cũng rất quan trọng: với đối số đầu tiên là số, Oracle dùng numeric precedence; với đối số đầu tiên không phải số, các đối số sau được chuyển về kiểu của đối số đầu tiên trước khi so sánh. Vì vậy, `LEAST(10, '2')` và `LEAST('10', 2)` có thể cho kết quả khác nhau. Hãy thống nhất datatype, dùng `CAST`/`TO_NUMBER`/`TO_DATE` tường minh, tránh phụ thuộc NLS ngầm và bind đúng kiểu từ JDBC. Khi so sánh chuỗi đa ngôn ngữ, kiểm tra collation thay vì chỉ dựa vào character set. Những quyết định này giúp biểu thức ngắn gọn nhưng vẫn chính xác, ổn định giữa các môi trường.
