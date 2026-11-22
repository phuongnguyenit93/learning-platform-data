# CAST, format model và kiểm soát chuyển đổi dữ liệu trong Oracle

## 1. Vì sao cần kiểm soát chuyển đổi dữ liệu?

Một ứng dụng có thể nhận giá tiền từ CSV dưới dạng chuỗi `'1.250,50'`, nhận ngày từ giao diện dưới dạng `'14/11/2026'`, rồi ghi vào các cột `NUMBER` và `DATE` trong Oracle Database. Một câu SQL chạy được trên máy phát triển chưa chắc chạy đúng trên máy kiểm thử hoặc production, vì cách Oracle chuyển đổi văn bản thành số/ngày có thể phụ thuộc thiết lập NLS của phiên.

Ví dụ:

```sql
-- Dữ liệu nguồn là chuỗi, chưa phải NUMBER.
SELECT '123.45' AS amount_text FROM dual;

-- Chuyển đổi tường minh thành NUMBER.
SELECT TO_NUMBER(
           '123.45',
           '999D99',
           'NLS_NUMERIC_CHARACTERS=''.,'''
       ) AS amount_value
FROM dual;
```

Khi cần chuyển một biểu thức từ kiểu này sang kiểu khác, Oracle cung cấp `CAST`. Khi cần đọc một chuỗi theo định dạng cụ thể, các hàm `TO_NUMBER`, `TO_DATE`, `TO_TIMESTAMP` và `TO_TIMESTAMP_TZ` cho phép chỉ rõ **format model**. Khi cần hiển thị giá trị theo một mẫu, dùng `TO_CHAR`.

Ba khái niệm cần phân biệt:

1. **Chuyển đổi kiểu dữ liệu (type conversion):** biến biểu thức từ kiểu nguồn sang kiểu đích, ví dụ `NUMBER` sang `VARCHAR2`.
2. **Format model:** mô tả cách đọc hoặc hiển thị thành phần của số/ngày giờ, ví dụ `YYYY-MM-DD` hay `9G999D99`.
3. **NLS parameters:** quy định các quy ước ngôn ngữ/lãnh thổ như dấu thập phân, dấu phân nhóm, tên tháng và cách hiển thị mặc định.

Mục tiêu của bài học thuộc chương **Hàm và biểu thức** là viết biểu thức chuyển đổi có kiểu đích rõ ràng, đọc đúng dữ liệu đầu vào, kiểm soát ảnh hưởng của NLS, phát hiện lỗi chuyển đổi và truyền giá trị an toàn từ ứng dụng Java/JDBC.

## 2. Kiểu dữ liệu nguồn, kiểu đích và chuyển đổi

Một biểu thức SQL luôn có kiểu dữ liệu. Ví dụ:

| Biểu thức | Kiểu dữ liệu điển hình |
|---|---|
| `123.45` | `NUMBER` |
| `'123.45'` | `VARCHAR2` literal |
| `DATE '2026-11-14'` | `DATE` |
| `TIMESTAMP '2026-11-14 10:30:00'` | `TIMESTAMP` |
| `CAST(NULL AS NUMBER)` | `NUMBER` với giá trị NULL |
| `TO_CHAR(SYSDATE, 'YYYY-MM-DD')` | `VARCHAR2` |
| `TO_NUMBER('123.45', '999D99')` | `NUMBER` |

Chuyển đổi dữ liệu là quá trình Oracle diễn giải giá trị nguồn và tạo giá trị có kiểu đích. Không phải mọi chuyển đổi đều an toàn:

- `'123'` có thể chuyển thành `NUMBER`.
- `'12A'` không phải biểu diễn số hợp lệ theo format model thông thường.
- `'14/11/2026'` có thể chuyển thành `DATE` khi format là `DD/MM/YYYY`.
- `'31/02/2026'` không phải ngày lịch hợp lệ.
- Một số có thể vượt độ chính xác hoặc độ dài của kiểu đích.
- Chuyển `TIMESTAMP` sang `DATE` làm mất phần lẻ giây.

### 2.1. Chuyển đổi tường minh và chuyển đổi ngầm

**Chuyển đổi tường minh (explicit conversion)** xuất hiện trực tiếp trong SQL:

```sql
SELECT TO_NUMBER('2500') AS amount FROM dual;
```

**Chuyển đổi ngầm (implicit conversion)** do Oracle thực hiện để hai toán hạng hoặc biểu thức có thể làm việc cùng nhau:

```sql
SELECT 2500 + '100' AS total FROM dual;
```

Trong trường hợp cụ thể này Oracle có thể chuyển chuỗi `'100'` thành số. Nhưng nếu chuỗi là `'100A'`, biểu thức có thể thất bại. Việc dựa vào chuyển đổi ngầm còn làm câu SQL phụ thuộc định dạng session, giảm khả năng đọc và có thể ảnh hưởng kế hoạch thực thi.

Quy tắc thực hành: **khi dữ liệu đi qua ranh giới kiểu hoặc ranh giới hệ thống, hãy chuyển đổi tường minh và ghi rõ ý nghĩa của dữ liệu**.

## 3. `CAST`: chuyển một biểu thức sang kiểu đích

### 3.1. Cú pháp cơ bản

```sql
CAST(expression AS datatype)
```

Ví dụ:

```sql
SELECT CAST('12345' AS NUMBER) AS numeric_value,
       CAST(12345 AS VARCHAR2(20)) AS text_value
FROM dual;
```

Biểu thức đầu có kiểu `NUMBER`, biểu thức thứ hai có kiểu ký tự. `CAST` nói rõ kiểu đích trong chính câu SQL.

### 3.2. Chuyển chuỗi số sang NUMBER

```sql
SELECT CAST('2500' AS NUMBER) AS amount
FROM dual;
```

Ví dụ này dùng chuỗi số đơn giản, có thể được diễn giải theo quy tắc chuyển đổi số mặc định của session. Với dữ liệu có dấu thập phân hoặc dấu phân nhóm phụ thuộc locale, không nên chỉ dựa vào `CAST`; dùng `TO_NUMBER` cùng format model và NLS parameter rõ ràng.

### 3.3. Chỉ định precision và scale

`CAST` có thể chuyển sang kiểu `NUMBER` với độ chính xác và số chữ số thập phân được khai báo:

```sql
SELECT CAST(123.456 AS NUMBER(8, 2)) AS rounded_value,
       CAST(12 AS NUMBER(8, 2)) AS integer_value
FROM dual;
```

`NUMBER(8,2)` cho phép tổng cộng tối đa tám chữ số, trong đó hai chữ số nằm sau dấu thập phân. Khi ép số có nhiều chữ số thập phân hơn scale, Oracle có thể làm tròn theo quy tắc của chuyển đổi số. Nếu giá trị vượt precision của kiểu đích, phép chuyển đổi có thể phát sinh lỗi.

Không nhầm `NUMBER(8,2)` với một format hiển thị. Kiểu dữ liệu kiểm soát độ chính xác số; `TO_CHAR` với format model kiểm soát cách hiển thị thành chuỗi.

### 3.4. Chuyển DATE và TIMESTAMP

```sql
SELECT CAST(DATE '2026-11-14' AS TIMESTAMP) AS timestamp_value
FROM dual;
```

Giá trị `DATE` được mở rộng sang `TIMESTAMP`; phần lẻ giây được bổ sung bằng 0.

Chiều ngược lại:

```sql
SELECT CAST(
           TIMESTAMP '2026-11-14 16:30:45.123456'
           AS DATE
       ) AS date_value
FROM dual;
```

Kiểu `DATE` chỉ giữ độ chính xác đến giây; phần `.123456` không được lưu trong kiểu đích.

**Không dùng `CAST` để đọc một chuỗi ngày theo format tự chọn.** `CAST` không nhận một format model ngày như tham số riêng. Khi nguồn là chuỗi, dùng `TO_DATE` hoặc `TO_TIMESTAMP` với format model:

```sql
SELECT TO_DATE('14/11/2026', 'FXDD/MM/YYYY') AS parsed_date
FROM dual;
```

### 3.5. CAST(NULL AS datatype): xác định kiểu cho NULL

Trong các biểu thức `UNION`, `CASE` hoặc truy vấn tạo dữ liệu có cột thiếu, có thể cần chỉ định kiểu cho NULL:

```sql
SELECT CAST(NULL AS NUMBER(12, 2)) AS amount
FROM dual;
```

Đây là một giá trị NULL có **kiểu NUMBER(12,2)** trong biểu thức. Cách viết này giúp Oracle xác định kiểu cột trong các phép kết hợp:

```sql
SELECT CAST(NULL AS NUMBER(12, 2)) AS amount
FROM dual
UNION ALL
SELECT CAST(125.50 AS NUMBER(12, 2)) AS amount
FROM dual;
```

`CAST(NULL AS ...)` không biến NULL thành số 0; nó chỉ gắn kiểu dữ liệu cho biểu thức NULL.

### 3.6. CAST trong CASE và UNION

Các nhánh `CASE` và các truy vấn kết hợp cần kiểu dữ liệu tương thích:

```sql
SELECT CASE
           WHEN 1 = 1 THEN CAST(100 AS NUMBER(10, 2))
           ELSE CAST(NULL AS NUMBER(10, 2))
       END AS amount
FROM dual;
```

Khi các nhánh có kiểu không tương thích, Oracle có thể báo lỗi về kiểu dữ liệu. Dùng `CAST` giúp thể hiện rõ kiểu chung mà truy vấn cần trả về.

### 3.7. CAST và chuỗi ký tự

```sql
SELECT CAST(12345 AS VARCHAR2(20)) AS code_text,
       CAST('AB' AS CHAR(5)) AS fixed_text
FROM dual;
```

`CHAR` là kiểu độ dài cố định, có quy tắc đệm dấu cách; `VARCHAR2` là kiểu độ dài biến thiên. Khi chuyển số thành chuỗi để tạo giao diện hoặc file xuất, `CAST(number AS VARCHAR2(...))` không cho bạn kiểm soát đầy đủ mẫu dấu thập phân, dấu nhóm hoặc số chữ số như `TO_CHAR`.

Ví dụ cần hiển thị hai chữ số thập phân:

```sql
SELECT TO_CHAR(
           1234.5,
           'FM9G999D00',
           'NLS_NUMERIC_CHARACTERS=''.,'''
       ) AS formatted_amount
FROM dual;
```

Ở đây `TO_CHAR` phù hợp hơn vì có format model cụ thể.

## 4. `CAST` khác `TO_CHAR`, `TO_NUMBER`, `TO_DATE` thế nào?

| Hàm | Hướng chuyển đổi | Dùng khi |
|---|---|---|
| `CAST(expr AS type)` | Chuyển biểu thức sang kiểu đích | Cần kiểu đầu ra rõ ràng, không cần mẫu parse/hiển thị riêng |
| `TO_CHAR(number, fmt, nlsparam)` | NUMBER → văn bản | Cần kiểm soát số chữ số, dấu thập phân, dấu phân nhóm, tiền tệ |
| `TO_CHAR(datetime, fmt, nlsparam)` | DATE/TIMESTAMP → văn bản | Cần kiểm soát thứ tự ngày/tháng/năm, giờ và timezone hiển thị |
| `TO_NUMBER(text, fmt, nlsparam)` | Văn bản → NUMBER | Đầu vào có định dạng số xác định |
| `TO_DATE(text, fmt, nlsparam)` | Văn bản → DATE | Đầu vào là ngày/giờ đến giây |
| `TO_TIMESTAMP(text, fmt, nlsparam)` | Văn bản → TIMESTAMP | Đầu vào có phần lẻ giây |
| `TO_TIMESTAMP_TZ(text, fmt, nlsparam)` | Văn bản → TIMESTAMP WITH TIME ZONE | Đầu vào có offset hoặc thông tin múi giờ theo format model |

Ví dụ so sánh:

```sql
-- Chuyển kiểu:
SELECT CAST(1234.5 AS VARCHAR2(30)) AS cast_text
FROM dual;

-- Chuyển và định dạng:
SELECT TO_CHAR(
           1234.5,
           'FM9G999D00',
           'NLS_NUMERIC_CHARACTERS=''.,'''
       ) AS formatted_text
FROM dual;
```

Hai câu đều trả về chuỗi, nhưng câu thứ hai diễn đạt rõ cách hiển thị `1,234.50` theo quy ước đã nêu. `CAST` không thay thế một format model.

## 5. Chuyển đổi ngầm: tiện nhưng dễ gây sai

Oracle có thể tự chuyển kiểu trong biểu thức, phép so sánh, phép nối và thao tác DML. Chuyển đổi ngầm giúp câu lệnh ngắn hơn, nhưng có thể làm ý nghĩa phụ thuộc NLS hoặc khiến Oracle phải xử lý hàm trên cột.

### 5.1. Chuỗi và số

Giả sử `orders.order_id` là `NUMBER`.

```sql
-- Có thể khiến Oracle chuyển chuỗi '1001' thành NUMBER:
SELECT *
FROM orders
WHERE order_id = '1001';
```

Viết rõ kiểu:

```sql
SELECT *
FROM orders
WHERE order_id = 1001;
```

Nếu đầu vào đến từ ứng dụng, hãy bind kiểu số thay vì tạo chuỗi SQL. Không để database phải đoán cách parse `'1,000'`, `'1.000'` hay `'1,000.00'`.

### 5.2. Ngày giờ và chuỗi

```sql
-- Phụ thuộc định dạng ngày của session:
SELECT *
FROM orders
WHERE created_at >= '14/11/2026';
```

Viết tường minh:

```sql
SELECT *
FROM orders
WHERE created_at >= DATE '2026-11-14';
```

Hoặc nếu đầu vào theo định dạng ngày/tháng/năm:

```sql
SELECT *
FROM orders
WHERE created_at >= TO_DATE('14/11/2026', 'FXDD/MM/YYYY');
```

### 5.3. Cột bị chuyển đổi có thể làm index khó được sử dụng

Giả sử cột `created_at` có index. Câu:

```sql
WHERE TO_CHAR(created_at, 'YYYY-MM-DD') = '2026-11-14'
```

áp dụng hàm lên cột trước khi so sánh. Oracle có thể không sử dụng index thường trên `created_at` theo cách mong đợi, vì điều kiện không còn là một khoảng trực tiếp trên cột.

Viết theo khoảng nửa mở:

```sql
WHERE created_at >= DATE '2026-11-14'
  AND created_at <  DATE '2026-11-15'
```

Cách này vừa tránh format chuỗi vừa tạo điều kiện range dễ tận dụng index phù hợp hơn. Execution plan vẫn phụ thuộc thống kê, độ chọn lọc và cấu trúc thực tế; không có một cú pháp nào bảo đảm index luôn được chọn.

### 5.4. Chiều chuyển đổi trong phép so sánh quan trọng

Nếu cột là `NUMBER` nhưng bind hoặc literal là chuỗi, Oracle có thể chuyển chuỗi sang số. Nếu cột là `VARCHAR2` nhưng so sánh với biểu thức số, Oracle có thể chuyển cột thành số trong một số ngữ cảnh. Nếu một hàng chứa `'A12'`, câu truy vấn có thể thất bại với lỗi invalid number.

**Đừng bắt Oracle chuyển cả cột chỉ vì một tham số có kiểu không phù hợp.** Dùng kiểu tham số đúng với kiểu cột và chuyển dữ liệu nguồn ở ranh giới nhận dữ liệu.

## 6. Format model là gì?

**Format model** là chuỗi ký hiệu mô tả cách Oracle đọc hoặc trình bày giá trị số/ngày giờ. Nó không phải kiểu dữ liệu, không thay đổi kiểu cột và cũng không phải chuỗi định dạng chung áp dụng cho mọi kiểu.

Ví dụ:

```sql
TO_CHAR(1234.5, 'FM9G999D00')
```

Format model nói rằng dùng vị trí chữ số `9`, dấu phân nhóm `G`, dấu thập phân `D`, hai chữ số thập phân `00` và fill mode `FM`.

Với ngày giờ:

```sql
TO_CHAR(SYSDATE, 'YYYY-MM-DD HH24:MI:SS')
```

`YYYY`, `MM`, `DD`, `HH24`, `MI`, `SS` chỉ rõ từng thành phần. Với hàm chuyển đổi đầu vào, format model còn quyết định Oracle diễn giải từng phần văn bản như thế nào.

## 7. Format model cho số

### 7.1. Các phần tử thường dùng

| Phần tử | Ý nghĩa | Ví dụ |
|---|---|---|
| `9` | Vị trí chữ số; có thể để trống nếu không có chữ số tương ứng | `9999` |
| `0` | Vị trí chữ số; hiển thị số 0 nếu vị trí không có chữ số | `0000` |
| `D` | Ký tự dấu thập phân theo NLS | `999D99` |
| `G` | Ký tự phân nhóm hàng nghìn theo NLS | `9G999` |
| `L` | Ký hiệu tiền tệ địa phương | `L999D00` |
| `C` | Ký hiệu tiền tệ ISO theo lãnh thổ | `C999D00` |
| `$` | Ký hiệu dollar | `$999D00` |
| `S` | Dấu cộng/trừ | `S9999` |
| `MI` | Dấu trừ ở cuối nếu số âm | `9999MI` |
| `PR` | Dấu ngoặc góc cho số âm theo format model | `9999PR` |
| `FM` | Fill mode, bỏ phần đệm khi phù hợp | `FM999G999D00` |
| `EEEE` | Ký pháp khoa học | `9.999EEEE` |

`D` và `G` là phần tử format, không phải ký tự dấu phẩy/chấm cố định. Dấu thực tế phụ thuộc `NLS_NUMERIC_CHARACTERS` hoặc tham số NLS truyền trực tiếp cho hàm.

### 7.2. `9` và `0` khác nhau

```sql
SELECT TO_CHAR(7, '9999') AS optional_digits,
       TO_CHAR(7, '0000') AS forced_zeroes
FROM dual;
```

`9` cho phép vị trí không có chữ số được để trống, còn `0` buộc hiển thị số 0 ở vị trí tương ứng. `TO_CHAR` còn có thể đệm khoảng trắng để giữ độ rộng format model; `FM` thường được dùng khi cần chuỗi gọn.

```sql
SELECT TO_CHAR(7, 'FM9999') AS compact_number,
       TO_CHAR(7, 'FM0000') AS padded_number
FROM dual;
```

Kết quả mong đợi về ý nghĩa: `7` và `0007`.

### 7.3. Dấu thập phân và phân nhóm

```sql
SELECT TO_CHAR(
           1234567.5,
           'FM9G999G999D00',
           'NLS_NUMERIC_CHARACTERS=''.,'''
       ) AS us_style
FROM dual;
```

Tham số NLS đặt dấu thập phân là `.` và dấu nhóm là `,`; kết quả hiển thị theo kiểu `1,234,567.50`.

Muốn biểu diễn kiểu thường thấy ở Việt Nam, đổi thứ tự hai ký tự:

```sql
SELECT TO_CHAR(
           1234567.5,
           'FM9G999G999D00',
           'NLS_NUMERIC_CHARACTERS='',.'''
       ) AS comma_decimal
FROM dual;
```

Kết quả minh họa: `1.234.567,50`.

Trong `NLS_NUMERIC_CHARACTERS`, **ký tự thứ nhất là dấu thập phân**, ký tự thứ hai là dấu phân nhóm. Tham số được truyền vào hàm giúp biểu thức có quy ước riêng mà không cần thay đổi NLS của toàn bộ session.

### 7.4. Đọc chuỗi số bằng TO_NUMBER

Khi nguồn gửi `1.234,56`, nếu đó là chuỗi theo quy ước dấu nhóm `.` và dấu thập phân `,`, hãy khai báo cả format model lẫn NLS:

```sql
SELECT TO_NUMBER(
           '1.234,56',
           '9G999D99',
           'NLS_NUMERIC_CHARACTERS='',.'''
       ) AS amount
FROM dual;
```

Kết quả là số `1234.56`, không phải chuỗi `1.234,56`.

Nếu dữ liệu theo quy ước dấu nhóm `,` và dấu thập phân `.`, dùng:

```sql
SELECT TO_NUMBER(
           '1,234.56',
           '9G999D99',
           'NLS_NUMERIC_CHARACTERS=''.,'''
       ) AS amount
FROM dual;
```

Không dùng cùng một format/NLS cho cả hai nguồn nếu quy ước đầu vào khác nhau. Hãy xác định định dạng tại ranh giới nhập dữ liệu (CSV, API, file đối tác) rồi parse theo hợp đồng đó.

### 7.5. Kiểm soát dấu và tiền tệ

```sql
SELECT TO_CHAR(
           -1250.5,
           'FMS999G999D00',
           'NLS_NUMERIC_CHARACTERS=''.,'''
       ) AS signed_amount
FROM dual;
```

`S` kiểm soát vị trí dấu theo format model. Nếu cần ký hiệu tiền tệ:

```sql
SELECT TO_CHAR(
           1250.5,
           'FML999G999D00',
           'NLS_NUMERIC_CHARACTERS='',.'' NLS_CURRENCY=''VND'''
       ) AS money_text
FROM dual;
```

Đây là ví dụ minh họa cách truyền NLS currency; ký hiệu tiền tệ thực tế cần theo chính sách hiển thị của ứng dụng. Không dùng chuỗi đã định dạng tiền tệ làm giá trị số để tính toán hoặc lưu trong cột `NUMBER`.

### 7.6. Format model không phải validation nghiệp vụ đầy đủ

`TO_NUMBER` kiểm tra chuỗi có thể chuyển đổi theo format model, nhưng điều đó không tự đảm bảo giá trị phù hợp nghiệp vụ. Ví dụ, `'0005'` có thể parse thành 5; nếu mã sản phẩm cần giữ các số 0 ở đầu thì nó phải được lưu như **mã ký tự**, không phải NUMBER.

Tương tự, giá tiền parse thành số hợp lệ không có nghĩa nó lớn hơn 0 hoặc nằm trong giới hạn cho phép. Hãy tách kiểm tra cú pháp, chuyển đổi kiểu và kiểm tra quy tắc nghiệp vụ.

## 8. Format model cho ngày và giờ

### 8.1. Các phần tử cơ bản

| Phần tử | Ý nghĩa |
|---|---|
| `YYYY` | Năm bốn chữ số |
| `YY` | Năm hai chữ số theo quy tắc Oracle |
| `RR` | Năm hai chữ số với quy tắc diễn giải thế kỷ đặc biệt |
| `MM` | Tháng dạng số |
| `MON` | Tên tháng viết tắt theo ngôn ngữ NLS |
| `MONTH` | Tên tháng đầy đủ theo ngôn ngữ NLS |
| `DD` | Ngày trong tháng |
| `DDD` | Ngày thứ bao nhiêu trong năm |
| `DY`, `DAY` | Tên thứ viết tắt/đầy đủ theo NLS |
| `HH24` | Giờ theo hệ 24 giờ |
| `HH12` hoặc `HH` | Giờ theo hệ 12 giờ |
| `MI` | Phút |
| `SS` | Giây |
| `FF`, `FF1`…`FF9` | Phần lẻ giây của TIMESTAMP |
| `TZH` | Phần giờ của offset múi giờ |
| `TZM` | Phần phút của offset múi giờ |
| `TZR` | Vùng múi giờ |
| `TZD` | Viết tắt trạng thái daylight saving theo vùng khi áp dụng |

**Bẫy quan trọng:** `MM` là tháng, `MI` là phút. Format `HH24:MM:SS` thường sai nếu bạn muốn biểu diễn giờ-phút-giây; nên dùng `HH24:MI:SS`.

### 8.2. Parse ngày bằng TO_DATE

```sql
SELECT TO_DATE('14/11/2026', 'DD/MM/YYYY') AS parsed_date
FROM dual;
```

Nếu muốn yêu cầu chuỗi khớp chính xác cấu trúc:

```sql
SELECT TO_DATE('14/11/2026', 'FXDD/MM/YYYY') AS parsed_date
FROM dual;
```

`FX` (*format exact*) yêu cầu khớp chính xác hơn giữa chuỗi đầu vào và format model, bao gồm dấu phân cách và độ dài phần tử theo quy tắc Oracle. Điều này hữu ích khi dữ liệu nhập có hợp đồng chặt chẽ, chẳng hạn file đối tác phải luôn gửi `DD/MM/YYYY`.

### 8.3. Ngày có tên tháng và NLS_DATE_LANGUAGE

```sql
SELECT TO_DATE(
           '14-NOV-2026',
           'DD-MON-YYYY',
           'NLS_DATE_LANGUAGE=ENGLISH'
       ) AS parsed_date
FROM dual;
```

`MON` cần nhận diện tên tháng theo ngôn ngữ. Nếu session đang dùng ngôn ngữ khác, việc không chỉ định NLS có thể làm parse thất bại hoặc diễn giải không như mong muốn. Nếu kiểm soát giao thức đầu vào, format số `YYYY-MM-DD` thường dễ trao đổi hơn tên tháng viết bằng ngôn ngữ tự nhiên.

### 8.4. Parse giờ 12 giờ và 24 giờ

Đầu vào:

```text
14/11/2026 04:30:15 PM
```

Format:

```sql
SELECT TO_DATE(
           '14/11/2026 04:30:15 PM',
           'DD/MM/YYYY HH12:MI:SS AM'
       ) AS parsed_datetime
FROM dual;
```

Nếu nguồn gửi `16:30:15`, dùng `HH24`:

```sql
SELECT TO_DATE(
           '14/11/2026 16:30:15',
           'DD/MM/YYYY HH24:MI:SS'
       ) AS parsed_datetime
FROM dual;
```

Không dùng `HH12` mà bỏ AM/PM nếu nguồn có thể mơ hồ giữa sáng và chiều.

### 8.5. Parse phần lẻ giây bằng TO_TIMESTAMP

```sql
SELECT TO_TIMESTAMP(
           '2026-11-14 16:30:15.123456',
           'YYYY-MM-DD HH24:MI:SS.FF6'
       ) AS precise_timestamp
FROM dual;
```

`DATE` không giữ phần lẻ giây; dùng `TIMESTAMP` khi cần. `FF6` diễn đạt sáu chữ số phần lẻ giây. Nếu chuỗi có ký tự `T` cố định:

```sql
SELECT TO_TIMESTAMP(
           '2026-11-14T16:30:15.123',
           'YYYY-MM-DD"T"HH24:MI:SS.FF3'
       ) AS precise_timestamp
FROM dual;
```

Ký tự `"T"` nằm trong dấu nháy kép của format model để Oracle hiểu đó là ký tự literal, không phải phần tử định dạng.

### 8.6. Parse timezone bằng TO_TIMESTAMP_TZ

```sql
SELECT TO_TIMESTAMP_TZ(
           '2026-11-14 16:30:15 +07:00',
           'YYYY-MM-DD HH24:MI:SS TZH:TZM'
       ) AS event_time
FROM dual;
```

`TZH:TZM` đọc offset giờ/phút. Nếu dữ liệu dùng tên vùng như `Europe/Paris`, format model có thể sử dụng `TZR` và trong một số tình huống `TZD`; kết quả còn phụ thuộc timezone file và quy tắc DST của Oracle. Một offset cố định không giữ đầy đủ quy tắc lịch sử của vùng.

### 8.7. Định dạng hiển thị bằng TO_CHAR

```sql
SELECT TO_CHAR(
           DATE '2026-11-14',
           'YYYY-MM-DD'
       ) AS iso_date,
       TO_CHAR(
           TIMESTAMP '2026-11-14 16:30:15.123456',
           'YYYY-MM-DD"T"HH24:MI:SS.FF6'
       ) AS iso_timestamp
FROM dual;
```

`TO_CHAR` trả về văn bản. Nó không thay đổi kiểu của cột nguồn và không nên được dùng để thay thế kiểu ngày giờ trong điều kiện lọc hoặc phép tính thời gian.

## 9. Literal chuẩn và format model: chọn cách nào?

Nếu mốc ngày giờ được viết cố định ngay trong SQL, có thể dùng literal chuẩn:

```sql
SELECT DATE '2026-11-14',
       TIMESTAMP '2026-11-14 16:30:15.123456',
       TIMESTAMP '2026-11-14 16:30:15 +07:00'
FROM dual;
```

Literal giúp tạo giá trị có kiểu mà không phải parse chuỗi theo NLS mặc định. Với đầu vào động, dùng hàm chuyển đổi có format model:

```sql
SELECT TO_DATE(:p_day, 'FXYYYY-MM-DD')
FROM dual;
```

Trong ứng dụng, cách tốt hơn nữa thường là parse chuỗi tại API theo hợp đồng đã công bố rồi **bind giá trị ngày giờ có kiểu**. Không cần đưa chuỗi qua Oracle chỉ để parse nếu Java đã có đối tượng thời gian hợp lệ và driver hỗ trợ bind phù hợp.

| Nguồn | Cách nên cân nhắc |
|---|---|
| Mốc cố định trong SQL | ANSI `DATE`/`TIMESTAMP` literal |
| Chuỗi ngày từ file/API | `TO_DATE` với format model và NLS rõ |
| Chuỗi timestamp có phần lẻ giây | `TO_TIMESTAMP` |
| Chuỗi có offset | `TO_TIMESTAMP_TZ` |
| Java đã có `LocalDate`/`LocalDateTime`/`OffsetDateTime` | Bind giá trị có kiểu qua JDBC |
| Cần xuất báo cáo dạng văn bản | `TO_CHAR` với format model rõ |
| Chỉ cần xác định kiểu kết quả trong biểu thức | `CAST` |

## 10. Kiểm soát NLS trong chuyển đổi số và ngày giờ

NLS (*National Language Support*) trong Oracle là nhóm thiết lập liên quan ngôn ngữ, lãnh thổ và cách trình bày/chuyển đổi dữ liệu.

### 10.1. Tham số NLS thường gặp

| Tham số | Ảnh hưởng |
|---|---|
| `NLS_NUMERIC_CHARACTERS` | Dấu thập phân và dấu phân nhóm |
| `NLS_CURRENCY` | Ký hiệu tiền tệ địa phương |
| `NLS_ISO_CURRENCY` | Quy tắc/ký hiệu tiền tệ ISO theo lãnh thổ |
| `NLS_DATE_FORMAT` | Mẫu mặc định cho DATE khi hiển thị/chuyển đổi ngầm |
| `NLS_TIMESTAMP_FORMAT` | Mẫu mặc định cho TIMESTAMP |
| `NLS_TIMESTAMP_TZ_FORMAT` | Mẫu mặc định cho TIMESTAMP WITH TIME ZONE |
| `NLS_DATE_LANGUAGE` | Tên tháng, tên thứ và ngôn ngữ ngày giờ |
| `NLS_TERRITORY` | Quy ước lãnh thổ và một số mặc định ngày giờ/số |

### 10.2. Kiểm tra thiết lập NLS của session

```sql
SELECT parameter, value
FROM nls_session_parameters
WHERE parameter IN (
    'NLS_NUMERIC_CHARACTERS',
    'NLS_CURRENCY',
    'NLS_DATE_FORMAT',
    'NLS_TIMESTAMP_FORMAT',
    'NLS_TIMESTAMP_TZ_FORMAT',
    'NLS_DATE_LANGUAGE',
    'NLS_TERRITORY'
)
ORDER BY parameter;
```

Giá trị thực tế có thể khác giữa SQL*Plus, SQL Developer, SQLcl và ứng dụng Java. Driver, cấu hình kết nối hoặc lệnh `ALTER SESSION` trong connection pool có thể tạo ra session có NLS khác nhau.

### 10.3. Truyền NLS parameter ngay trong hàm

Đối với số:

```sql
SELECT TO_NUMBER(
           '1.234,56',
           '9G999D99',
           'NLS_NUMERIC_CHARACTERS='',.'''
       )
FROM dual;
```

Đối với tên tháng:

```sql
SELECT TO_DATE(
           '14-NOV-2026',
           'DD-MON-YYYY',
           'NLS_DATE_LANGUAGE=ENGLISH'
       )
FROM dual;
```

Cách này giới hạn quy ước cho **một biểu thức**, giúp SQL tự mô tả rõ cách parse thay vì thay đổi trạng thái của cả session.

### 10.4. ALTER SESSION không phải cách thay thế format model tường minh

Có thể thay đổi thiết lập phiên trong môi trường kiểm thử:

```sql
ALTER SESSION SET NLS_DATE_FORMAT = 'DD/MM/YYYY';
ALTER SESSION SET NLS_NUMERIC_CHARACTERS = ',.';
```

Nhưng các câu SQL dựa vào chuyển đổi ngầm vẫn có thể chạy khác khi kết nối bằng session khác. Đặc biệt, connection pool tái sử dụng session khiến trạng thái NLS thay đổi ở request trước có thể ảnh hưởng request sau nếu không khôi phục.

`ALTER SESSION` hữu ích để kiểm tra sự phụ thuộc hoặc đáp ứng một quy ước vận hành có quản lý. Với logic ứng dụng, ưu tiên **format model và bind đúng kiểu**.

## 11. Kiểm soát lỗi chuyển đổi

Chuyển đổi tường minh giúp kiểm soát cách parse, nhưng không biến dữ liệu không hợp lệ thành hợp lệ. Một chuỗi có thể đúng cấu trúc mà sai giá trị, hoặc có giá trị vượt giới hạn kiểu đích.

### 11.1. Lỗi số không hợp lệ

```sql
SELECT TO_NUMBER('12A', '999')
FROM dual;
```

Chuỗi chứa ký tự không phù hợp có thể gây:

```text
ORA-01722: invalid number
```

Nguyên nhân có thể là ký tự lạ, dấu thập phân/phân nhóm sai, format model không phù hợp hoặc dữ liệu đầu vào đã hỏng.

### 11.2. Lỗi ngày giờ không khớp

```sql
SELECT TO_DATE('14/11/2026', 'FXYYYY-MM-DD')
FROM dual;
```

Chuỗi dùng thứ tự ngày/tháng/năm nhưng format yêu cầu năm-tháng-ngày, nên không khớp. Các lỗi liên quan có thể gồm:

- `ORA-01861`: literal không khớp format string.
- `ORA-01843`: tháng không hợp lệ.
- `ORA-01830`: format picture kết thúc trước khi chuyển đổi hết chuỗi.
- `ORA-01847`: ngày trong tháng nằm ngoài phạm vi hợp lệ.

Thông báo cụ thể phụ thuộc dữ liệu và format model.

### 11.3. Lỗi precision/độ dài kiểu đích

```sql
SELECT CAST(123456 AS NUMBER(4))
FROM dual;
```

Giá trị vượt độ chính xác khai báo có thể gây lỗi số vượt precision, thường gặp `ORA-01438` trong ngữ cảnh cột/kiểu số có giới hạn precision.

Với dữ liệu ký tự được ghi vào cột quá ngắn, có thể gặp `ORA-12899: value too large for column`. Đừng chỉ kiểm tra số ký tự bằng `LENGTH` nếu cột dùng byte semantics và database character set có ký tự đa byte; cần xem cả `LENGTHB` và metadata cột.

### 11.4. Tách validation, parse và business validation

Một pipeline nhập liệu nên có các bước:

```text
Văn bản đầu vào
      |
      v
Kiểm tra hợp đồng định dạng
      |
      v
Parse theo format model/NLS rõ ràng
      |
      v
Kiểm tra kiểu đích, precision, range
      |
      v
Kiểm tra quy tắc nghiệp vụ
      |
      v
Bind giá trị có kiểu và ghi database
```

Ví dụ với số tiền:

1. Chuỗi `'1.234,56'` có đúng format đối tác đã công bố không?
2. `TO_NUMBER` theo format/NLS đó có parse được không?
3. Giá trị có nằm trong miền số tiền cho phép không?
4. Có đúng số chữ số thập phân theo loại tiền không?
5. Có thể ghi vào cột `NUMBER(12,2)` không?

Không nên gộp tất cả thành một phép `CAST` rồi chỉ xử lý exception cuối cùng.

### 11.5. VALIDATE_CONVERSION trên phiên bản hỗ trợ

Một số phiên bản Oracle hỗ trợ hàm `VALIDATE_CONVERSION` để kiểm tra một biểu thức có thể chuyển đổi sang kiểu đích hay không:

```sql
SELECT VALIDATE_CONVERSION('123.45' AS NUMBER) AS can_convert_number,
       VALIDATE_CONVERSION('12A' AS NUMBER) AS cannot_convert_number
FROM dual;
```

Giá trị trả về thường là `1` khi chuyển đổi được và `0` khi không chuyển đổi được. Hàm này có từ các phiên bản Oracle hỗ trợ tính năng tương ứng (thường gặp ở 12.2 trở lên); hãy đối chiếu phiên bản database trước khi sử dụng.

Đầu vào NULL được xem là có thể chuyển đổi sang kiểu đích theo quy tắc của hàm, vì vậy `VALIDATE_CONVERSION(NULL AS NUMBER)` không thay thế `IS NULL`. Vẫn cần kiểm tra sự hiện diện của dữ liệu riêng.

## 12. Các mẫu chuyển đổi an toàn thường dùng

### 12.1. Chuyển số từ CSV có dấu phẩy thập phân

```sql
SELECT TO_NUMBER(
           amount_text,
           'FM9G999G999D99',
           'NLS_NUMERIC_CHARACTERS='',.'''
       ) AS amount_value
FROM import_rows;
```

Giả định `AMOUNT_TEXT` dùng dấu chấm phân nhóm và dấu phẩy thập phân. Nếu nguồn có quy ước khác, thay format/NLS cho đúng hợp đồng. Không đoán theo ngôn ngữ của máy chạy job.

### 12.2. Chuyển chuỗi ngày theo định dạng API

```sql
SELECT TO_DATE(date_text, 'FXYYYY-MM-DD') AS event_date
FROM import_rows;
```

Nếu nguồn gửi ngày-tháng-năm:

```sql
SELECT TO_DATE(date_text, 'FXDD/MM/YYYY') AS event_date
FROM import_rows;
```

Mỗi nguồn nên có một format model được định nghĩa rõ. Không dùng cùng một cột nguồn chứa nhiều quy tắc parse mà không có cách phân biệt.

### 12.3. Chuyển timestamp có phần lẻ giây

```sql
SELECT TO_TIMESTAMP(
           timestamp_text,
           'FXYYYY-MM-DD"T"HH24:MI:SS.FF6'
       ) AS event_timestamp
FROM import_rows;
```

Nếu dữ liệu có offset, chuyển sang `TIMESTAMP WITH TIME ZONE` bằng `TO_TIMESTAMP_TZ`, với format model bao gồm phần timezone.

### 12.4. Định dạng đầu ra có quy ước cố định

```sql
SELECT TO_CHAR(
           amount,
           'FM9G999G999D00',
           'NLS_NUMERIC_CHARACTERS='',.'''
       ) AS amount_display,
       TO_CHAR(
           created_at,
           'YYYY-MM-DD HH24:MI:SS'
       ) AS created_at_display
FROM orders;
```

Kết quả phù hợp cho báo cáo văn bản. Nếu dữ liệu tiếp tục được xử lý bằng ứng dụng, nên trả kiểu số/ngày giờ qua driver thay vì chuyển mọi thứ thành chuỗi ở database.

## 13. Chuyển đổi trong Java/JDBC

Trong Java, mỗi giá trị đã có kiểu ở tầng ứng dụng. Ví dụ:

| Java | Ý nghĩa | Kiểu Oracle thường được ánh xạ |
|---|---|---|
| `BigDecimal` | Số thập phân chính xác | `NUMBER` |
| `Long`/`Integer` | Số nguyên | `NUMBER` phù hợp |
| `String` | Văn bản | `VARCHAR2`/`NVARCHAR2` tùy schema |
| `LocalDate` | Ngày lịch | Cần mapping phù hợp với `DATE` |
| `LocalDateTime` | Ngày giờ không timezone | `TIMESTAMP` |
| `OffsetDateTime` | Ngày giờ có offset | `TIMESTAMP WITH TIME ZONE` nếu driver hỗ trợ |

### 13.1. Bind số bằng BigDecimal

```java
import java.math.BigDecimal;
import java.sql.PreparedStatement;

String sql = "INSERT INTO payments (payment_id, amount) VALUES (?, ?)";

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setLong(1, paymentId);
    ps.setBigDecimal(2, new BigDecimal("1234.56"));
    ps.executeUpdate();
}
```

Dùng `BigDecimal` để biểu diễn số thập phân cần độ chính xác, chẳng hạn tiền tệ. Tránh tạo `BigDecimal` từ một `double` đã có sai số nhị phân nếu yêu cầu là giữ chính xác chuỗi số đầu vào; constructor từ chuỗi là lựa chọn rõ ràng.

### 13.2. Parse văn bản tại ranh giới ứng dụng

Nếu API nhận `'1.234,56'` theo quy ước locale cụ thể, Java có thể parse ở tầng nhập liệu theo locale/hợp đồng đã xác định rồi bind `BigDecimal`. Hoặc hệ thống có thể đưa text vào staging table và dùng `TO_NUMBER` trong SQL với format/NLS tường minh. Hai phương án đều cần quy định đầu vào nhất quán.

Không nên gửi chuỗi locale-dependent rồi để Oracle tự đoán:

```java
// Không nên ghép văn bản người dùng vào SQL:
String sql = "INSERT INTO payments(amount) VALUES ('" + amountText + "')";
```

Thay vào đó, parse và bind:

```java
String sql = "INSERT INTO payments(amount) VALUES (?)";
try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setBigDecimal(1, parsedAmount);
    ps.executeUpdate();
}
```

### 13.3. Bind ngày giờ có kiểu

Ví dụ cho cột `TIMESTAMP`:

```java
import java.sql.PreparedStatement;
import java.sql.Timestamp;
import java.time.LocalDateTime;

LocalDateTime createdAt = LocalDateTime.of(2026, 11, 14, 16, 30, 15);

String sql = "INSERT INTO events (event_id, created_at) VALUES (?, ?)";
try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setLong(1, eventId);
    ps.setTimestamp(2, Timestamp.valueOf(createdAt));
    ps.executeUpdate();
}
```

Đoạn này giả định cột đích là timestamp không timezone và driver được cấu hình tương ứng. Với `DATE`, `TIMESTAMP WITH TIME ZONE` hoặc `TIMESTAMP WITH LOCAL TIME ZONE`, hãy chọn mapping/API phù hợp với semantics cần giữ. Đừng chuyển `LocalDateTime` thành chuỗi `DD/MM/YYYY HH24:MI:SS` rồi nối SQL.

### 13.4. Đọc kết quả thành kiểu Java

```java
try (PreparedStatement ps = connection.prepareStatement(
        "SELECT amount FROM payments WHERE payment_id = ?")) {
    ps.setLong(1, paymentId);

    try (ResultSet rs = ps.executeQuery()) {
        if (rs.next()) {
            BigDecimal amount = rs.getBigDecimal("amount");
        }
    }
}
```

`getBigDecimal` phù hợp cho số thập phân cần độ chính xác. Nếu cột có thể NULL, kiểm tra `wasNull()` khi dùng getter kiểu primitive; với object như `BigDecimal`, JDBC thường trả `null` cho SQL NULL.

## 14. Chuyển đổi và tối ưu truy vấn

### 14.1. Đặt chuyển đổi ở tham số, không tùy tiện ở cột

Giả sử `orders.created_at` có index. Tránh:

```sql
WHERE TO_CHAR(created_at, 'YYYY-MM-DD') = '2026-11-14'
```

Ưu tiên:

```sql
WHERE created_at >= DATE '2026-11-14'
  AND created_at <  DATE '2026-11-15'
```

Nếu nguồn chỉ có chuỗi:

```sql
WHERE created_at >= TO_DATE(:p_day, 'FXYYYY-MM-DD')
  AND created_at <  TO_DATE(:p_day, 'FXYYYY-MM-DD') + 1
```

Tốt hơn nữa, parse tham số một lần ở ứng dụng và bind hai mốc có kiểu. Khi cần biểu thức chuyển đổi trên cột vì yêu cầu nghiệp vụ, có thể cân nhắc function-based index, nhưng phải thiết kế và kiểm tra riêng.

### 14.2. Không dùng TO_CHAR để so sánh số

```sql
-- Không nên biến NUMBER thành text chỉ để lọc:
WHERE TO_CHAR(amount, '999D99') = '123,45'
```

Định dạng văn bản có thể phụ thuộc NLS và biểu thức trên cột làm truy vấn khó tận dụng index thông thường. So sánh bằng giá trị số:

```sql
WHERE amount = 123.45
```

Hoặc bind `BigDecimal` từ ứng dụng.

### 14.3. Conversion trong JOIN có thể gây tốn kém hoặc lỗi

Nếu `customers.customer_id` là NUMBER còn `orders.customer_id_text` là VARCHAR2, điều kiện:

```sql
ON customers.customer_id = orders.customer_id_text
```

có thể buộc Oracle chuyển kiểu. Nếu cột text chứa một giá trị không phải số, phép chuyển đổi có thể lỗi. Về thiết kế lâu dài, hai cột định danh dùng để JOIN nên có kiểu thống nhất. Khi không thể đổi schema ngay, cần xác định và làm sạch dữ liệu nguồn, kiểm soát conversion và đánh giá kế hoạch thực thi.

## 15. Các lỗi chuyển đổi thường gặp

| Lỗi | Tình huống thường gặp | Hướng xử lý |
|---|---|---|
| `ORA-01722: invalid number` | Chuỗi không parse được thành số hoặc NLS/format không khớp | Kiểm tra giá trị nguồn, `TO_NUMBER`, format và `NLS_NUMERIC_CHARACTERS` |
| `ORA-01861: literal does not match format string` | Chuỗi ngày giờ không khớp format model | Đối chiếu thứ tự, dấu phân cách và dùng `FX` khi cần strict |
| `ORA-01843: not a valid month` | Tháng không hợp lệ hoặc tên tháng không đúng `NLS_DATE_LANGUAGE` | Kiểm tra tháng và language |
| `ORA-01830: date format picture ends before converting entire input string` | Format model không mô tả hết chuỗi | Bổ sung giờ/phần lẻ giây/offset hoặc sửa nguồn |
| `ORA-01847: day of month must be between 1 and last day of month` | Ngày không tồn tại trong tháng | Kiểm tra tính hợp lệ lịch |
| `ORA-01438` | Giá trị số vượt precision của cột/kiểu | Kiểm tra precision, scale và giá trị nguồn |
| `ORA-12899` | Chuỗi vượt độ dài cột | Kiểm tra `DATA_LENGTH`, `CHAR_LENGTH`, byte semantics và encoding |
| `ORA-00932: inconsistent datatypes` | Biểu thức/nhánh UNION/CASE có kiểu không tương thích | Dùng `CAST` để thống nhất kiểu có chủ đích |

### Quy trình suy luận khi gặp lỗi

1. **Kiểu nguồn là gì?** Chuỗi, NUMBER, DATE hay TIMESTAMP?
2. **Kiểu đích cần là gì?** Đừng chỉ dựa vào kiểu hiển thị.
3. **Có cần format model không?** Nếu nguồn là chuỗi ngày/số có định dạng, ghi rõ format.
4. **NLS nào đang được áp dụng?** Dấu thập phân, phân nhóm, ngôn ngữ tháng và định dạng session.
5. **Giá trị có hợp lệ theo lịch/miền số không?** Format khớp chưa chắc dữ liệu hợp lệ.
6. **Có mất thông tin khi ép kiểu không?** Ví dụ TIMESTAMP sang DATE mất phần lẻ giây.
7. **Chuyển đổi đang áp dụng lên tham số hay lên cột?** Xem khả năng lỗi trên dữ liệu cũ và ảnh hưởng index.
8. **Có thể bind kiểu đúng từ ứng dụng không?** Nếu có, tránh parse chuỗi lần nữa ở database.

## 16. Bài thực hành tổng hợp

Các bước dưới đây dùng `DUAL` để thử chuyển đổi, sau đó tạo bảng riêng trong schema thực hành. Không chạy DDL/DML trên dữ liệu sản xuất.

### Bước 1. CAST và kiểu đích

```sql
SELECT CAST('12345' AS NUMBER) AS number_value,
       CAST(12345 AS VARCHAR2(20)) AS text_value,
       CAST(NULL AS NUMBER(10, 2)) AS typed_null
FROM dual;
```

Quan sát kiểu dữ liệu của từng biểu thức qua công cụ SQL hoặc metadata của kết quả.

### Bước 2. Chuyển đổi số theo hai quy ước

```sql
SELECT TO_NUMBER(
           '1,234.56',
           '9G999D99',
           'NLS_NUMERIC_CHARACTERS=''.,'''
       ) AS decimal_dot,
       TO_NUMBER(
           '1.234,56',
           '9G999D99',
           'NLS_NUMERIC_CHARACTERS='',.'''
       ) AS decimal_comma
FROM dual;
```

Hai biểu thức trả về cùng giá trị số 1234.56 nhưng parse từ hai cách biểu diễn khác nhau.

### Bước 3. Format số ra hai kiểu hiển thị

```sql
SELECT TO_CHAR(
           1234.5,
           'FM9G999D00',
           'NLS_NUMERIC_CHARACTERS=''.,'''
       ) AS style_dot,
       TO_CHAR(
           1234.5,
           'FM9G999D00',
           'NLS_NUMERIC_CHARACTERS='',.'''
       ) AS style_comma
FROM dual;
```

Kết quả minh họa lần lượt là `1,234.50` và `1.234,50`.

### Bước 4. Parse ngày và timestamp

```sql
SELECT TO_DATE('14/11/2026', 'FXDD/MM/YYYY') AS parsed_date,
       TO_TIMESTAMP(
           '2026-11-14T16:30:15.123456',
           'FXYYYY-MM-DD"T"HH24:MI:SS.FF6'
       ) AS parsed_timestamp
FROM dual;
```

Kiểm tra kiểu kết quả: cột đầu là DATE, cột thứ hai là TIMESTAMP.

### Bước 5. Kiểm soát ngôn ngữ tên tháng

```sql
SELECT TO_DATE(
           '14-NOV-2026',
           'FXDD-MON-YYYY',
           'NLS_DATE_LANGUAGE=ENGLISH'
       ) AS parsed_month
FROM dual;
```

Thử bỏ tham số ngôn ngữ trong một session có NLS_DATE_LANGUAGE khác để quan sát khác biệt nếu môi trường có cấu hình tương ứng.

### Bước 6. Tạo bảng thử nghiệm

```sql
CREATE TABLE demo_conversion (
    id           NUMBER PRIMARY KEY,
    amount       NUMBER(12, 2),
    event_date   DATE,
    event_time   TIMESTAMP(6),
    amount_text  VARCHAR2(30),
    date_text    VARCHAR2(30)
);
```

### Bước 7. Chèn dữ liệu đã chuyển đổi tường minh

```sql
INSERT INTO demo_conversion (
    id, amount, event_date, event_time, amount_text, date_text
) VALUES (
    1,
    TO_NUMBER(
        '1.234,56',
        '9G999D99',
        'NLS_NUMERIC_CHARACTERS='',.'''
    ),
    TO_DATE('14/11/2026', 'FXDD/MM/YYYY'),
    TO_TIMESTAMP(
        '2026-11-14 16:30:15.123456',
        'FXYYYY-MM-DD HH24:MI:SS.FF6'
    ),
    '1.234,56',
    '14/11/2026'
);

COMMIT;
```

Lệnh chèn dùng giá trị được parse theo quy tắc rõ ràng; không yêu cầu `NLS_DATE_FORMAT` phải là `DD/MM/YYYY`.

### Bước 8. Hiển thị bằng format model

```sql
SELECT id,
       TO_CHAR(
           amount,
           'FM9G999D00',
           'NLS_NUMERIC_CHARACTERS='',.'''
       ) AS amount_display,
       TO_CHAR(event_date, 'YYYY-MM-DD') AS date_display,
       TO_CHAR(event_time, 'YYYY-MM-DD HH24:MI:SS.FF6') AS time_display
FROM demo_conversion;
```

### Bước 9. Xem metadata kiểu cột

```sql
SELECT column_name,
       data_type,
       data_length,
       data_precision,
       data_scale
FROM user_tab_columns
WHERE table_name = 'DEMO_CONVERSION'
ORDER BY column_id;
```

Metadata giúp xác nhận kiểu đích đã được tạo đúng như thiết kế.

### Bước 10. Dọn bảng thực hành

Chỉ khi chắc chắn đây là bảng do chính bạn tạo và không cần giữ dữ liệu:

```sql
DROP TABLE demo_conversion PURGE;
```

`DROP TABLE ... PURGE` xóa đối tượng và dữ liệu, bỏ qua recycle bin theo hành vi của lệnh; đây là DDL có commit ngầm. Không dùng lệnh dọn trên bảng nghiệp vụ hoặc đối tượng dùng chung.

## 17. Quy tắc thực hành khi viết CAST và format model

| Tình huống | Nên dùng | Tránh |
|---|---|---|
| Muốn một biểu thức có kiểu NUMBER rõ ràng | `CAST(expr AS NUMBER(p,s))` | Dựa vào kiểu suy luận không rõ |
| Muốn parse chuỗi số theo locale cụ thể | `TO_NUMBER(text, fmt, nlsparam)` | `CAST(text AS NUMBER)` khi format đầu vào không cố định |
| Muốn parse chuỗi ngày | `TO_DATE(text, fmt, nlsparam)` | So sánh DATE với chuỗi NLS-dependent |
| Muốn parse timestamp có phần lẻ giây | `TO_TIMESTAMP(text, fmt, nlsparam)` | Parse qua DATE rồi hy vọng giữ phần lẻ |
| Muốn parse thời điểm có offset | `TO_TIMESTAMP_TZ` | Bỏ offset rồi lưu thành TIMESTAMP không timezone |
| Muốn xuất số có dấu phân nhóm/thập phân cụ thể | `TO_CHAR(number, fmt, nlsparam)` | `CAST(number AS VARCHAR2)` rồi giả định hiển thị |
| Muốn xuất ngày giờ chuẩn | `TO_CHAR(datetime, fmt, nlsparam)` | Phụ thuộc format mặc định của client |
| Muốn lọc một ngày trên cột DATE | Cận `>=` và `<` bằng giá trị có kiểu | `TO_CHAR(column, ...) = '...'` |
| Java đã có BigDecimal/ngày giờ | Bind giá trị có kiểu qua JDBC | Nối chuỗi vào SQL để Oracle parse |
| Cần dùng NULL trong UNION/CASE | `CAST(NULL AS target_type)` | Để Oracle tự suy đoán kiểu không tương thích |

Một câu SQL tốt nên cho người đọc biết **giá trị đến từ đâu, được parse theo quy tắc nào, kết quả thuộc kiểu gì và lỗi được xử lý ra sao**.

## 18. Câu hỏi tự kiểm tra

**Câu 1.** `CAST('123' AS NUMBER)` và `TO_NUMBER('123','999')` khác nhau ở mục đích nào?

**Trả lời:** CAST yêu cầu chuyển biểu thức sang kiểu đích; TO_NUMBER đọc văn bản theo format model số cụ thể và có thể nhận NLS parameter.

**Câu 2.** Có thể dùng `CAST('14/11/2026' AS DATE)` để luôn parse theo DD/MM/YYYY không?

**Trả lời:** Không nên. CAST không nhận format model riêng; chuyển đổi chuỗi ngày có thể phụ thuộc NLS. Dùng `TO_DATE('14/11/2026','FXDD/MM/YYYY')`.

**Câu 3.** `D` và `G` trong format số có phải luôn là dấu chấm và dấu phẩy?

**Trả lời:** Không. `D` là dấu thập phân và `G` là dấu phân nhóm theo NLS; có thể kiểm soát bằng `NLS_NUMERIC_CHARACTERS`.

**Câu 4.** Khi parse `1.234,56` theo quy ước Việt Nam, NLS_NUMERIC_CHARACTERS đặt thế nào?

**Trả lời:** Ký tự đầu là dấu thập phân `,`, ký tự thứ hai là dấu nhóm `.`, tức giá trị `',.'`.

**Câu 5.** `TO_DATE` có giữ phần mili giây không?

**Trả lời:** Không. DATE chỉ chính xác đến giây. Dùng `TO_TIMESTAMP` nếu cần phần lẻ giây.

**Câu 6.** Vì sao `TO_CHAR(created_at, 'YYYY-MM-DD')` trong WHERE có thể không tốt?

**Trả lời:** Hàm được áp lên cột trước khi so sánh, có thể cản trở sử dụng index thường và làm lọc theo chuỗi. Dùng điều kiện khoảng trên giá trị DATE/TIMESTAMP.

**Câu 7.** `CAST(NULL AS NUMBER)` có trả số 0 không?

**Trả lời:** Không. Nó vẫn là NULL nhưng có kiểu NUMBER.

**Câu 8.** `FX` có tác dụng gì?

**Trả lời:** Yêu cầu khớp chính xác hơn giữa chuỗi đầu vào và format model khi parse ngày giờ.

**Câu 9.** Khi format model có `HH24:MM:SS`, thành phần nào bị nhầm?

**Trả lời:** `MM` là tháng; phút phải dùng `MI`.

**Câu 10.** Vì sao ứng dụng Java nên bind `BigDecimal` thay vì ghép `'1.234,56'` vào SQL?

**Trả lời:** Bind tách dữ liệu khỏi cú pháp SQL, tránh SQL injection và tránh Oracle phải đoán định dạng theo NLS session.

**Câu 11.** Chuyển TIMESTAMP sang DATE có giữ phần lẻ giây không?

**Trả lời:** Không. Kiểu DATE chỉ giữ tới giây.

**Câu 12.** `VALIDATE_CONVERSION(NULL AS NUMBER)` có thay cho `IS NOT NULL` không?

**Trả lời:** Không. Hàm kiểm tra khả năng chuyển đổi; NULL được xem là có thể chuyển đổi theo quy tắc của hàm. Muốn kiểm tra thiếu dữ liệu, dùng `IS NULL`/`IS NOT NULL`.

## 19. Kết luận

`CAST` dùng để **chuyển một biểu thức sang kiểu dữ liệu đích**; `TO_NUMBER`, `TO_DATE`, `TO_TIMESTAMP` và `TO_TIMESTAMP_TZ` dùng để **đọc văn bản theo format model**; `TO_CHAR` dùng để **biểu diễn giá trị số/ngày giờ thành chuỗi**. Những công cụ này có vai trò khác nhau và không nên thay thế lẫn nhau một cách máy móc.

Khi nguồn là văn bản, hãy ghi rõ format model, chỉ định NLS parameter nếu có dấu thập phân, dấu nhóm hoặc tên tháng phụ thuộc ngôn ngữ, và kiểm tra dữ liệu không hợp lệ trước khi ghi. Khi nguồn đã là giá trị có kiểu trong Java, ưu tiên **bind đúng kiểu qua JDBC** thay vì chuyển thành chuỗi rồi parse lại. Hạn chế chuyển đổi ngầm, tránh áp hàm định dạng lên cột trong điều kiện lọc khi không cần, và luôn xét khả năng mất precision, phần lẻ giây hoặc thông tin timezone khi chuyển sang kiểu đích.
