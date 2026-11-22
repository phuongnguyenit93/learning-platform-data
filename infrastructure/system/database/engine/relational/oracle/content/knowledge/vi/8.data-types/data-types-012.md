# Chuyển kiểu tường minh, chuyển kiểu ngầm định và lỗi mất dữ liệu trong Oracle

Trong Oracle Database, một giá trị có **kiểu dữ liệu**: số (`NUMBER`), ký tự (`VARCHAR2`), ngày giờ (`DATE`, `TIMESTAMP`), dữ liệu nhị phân, v.v. Khi ứng dụng Java ghi hoặc đọc dữ liệu, khi SQL so sánh hai biểu thức khác kiểu, hoặc khi ta nhập dữ liệu từ CSV, Oracle có thể phải chuyển giá trị từ kiểu này sang kiểu khác. Một số phép chuyển đổi được thực hiện **tường minh** theo ý định của lập trình viên; số khác xảy ra **ngầm định** theo quy tắc của Oracle.

Nếu không nhận ra bước chuyển kiểu, một câu SQL tưởng như hợp lệ có thể gặp `ORA-01722` (*invalid number*), đọc sai ngày/tháng theo cấu hình phiên, khiến index khó được sử dụng, hoặc lưu một con số đã **làm tròn** mà không ai chú ý. Đáng ngại hơn, không phải mọi thay đổi giá trị đều tạo lỗi: mất phần giây, mất độ chính xác số hoặc đổi cách biểu diễn thời điểm có thể diễn ra mà thao tác SQL vẫn thành công.

Bài này xây dựng một mô hình nhất quán để **nhận diện**, **chủ động chuyển đổi**, **kiểm tra dữ liệu trước khi lưu**, và **ngăn mất dữ liệu ngoài ý muốn** trong Oracle SQL/PLSQL và ứng dụng JDBC.

## 1. Bản đồ hai loại chuyển kiểu

**Chuyển kiểu tường minh (explicit conversion)** là khi câu SQL chỉ ra phép chuyển đổi, ví dụ `TO_NUMBER`, `TO_DATE`, `TO_TIMESTAMP`, `TO_CHAR` hoặc `CAST`:

~~~sql
SELECT TO_NUMBER('125.50',
                 '999D99',
                 'NLS_NUMERIC_CHARACTERS = ''.,''') AS amount
FROM dual;
~~~

**Chuyển kiểu ngầm định (implicit conversion)** là khi hai biểu thức không cùng kiểu nhưng Oracle tự chọn phép chuyển đổi thích hợp để đánh giá biểu thức, so sánh hoặc gán giá trị:

~~~sql
-- Nếu ORDER_ID là NUMBER, literal '101' là VARCHAR2.
-- Oracle có thể chuyển '101' thành NUMBER khi so sánh.
SELECT order_id
FROM lab_order
WHERE order_id = '101';
~~~

| Tiêu chí | Tường minh | Ngầm định |
|---|---|---|
| Ai chỉ ra phép đổi? | Người viết SQL/PLSQL hoặc API ứng dụng | Oracle dựa trên kiểu của các biểu thức/ngữ cảnh |
| Cách đọc ý định | Rõ ở câu lệnh: `TO_DATE(..., 'YYYY-MM-DD')` | Khó nhận thấy: `date_col = '2026-11-14'` |
| Kiểm soát format/NLS | Có thể chỉ định format model và NLS parameter | Dễ phụ thuộc thiết lập của session |
| Rủi ro khi schema/dữ liệu đổi | Dễ kiểm soát hơn nếu có validation | Có thể lỗi, đổi ngữ nghĩa hoặc ảnh hưởng execution plan |
| Cách dùng nên ưu tiên | Tại ranh giới nhập/xuất giữa các kiểu | Không nên dựa vào cho dữ liệu quan trọng hoặc SQL ứng dụng |

**Định hướng:** Dữ liệu nên có **đúng kiểu từ lúc bước vào hệ thống**. Dùng explicit conversion ở ranh giới tiếp nhận dữ liệu, sau đó giữ giá trị ở kiểu đúng trong bảng, biến PL/SQL và tham số JDBC.

## 2. Oracle lưu gì trong những kiểu dữ liệu thường gặp?

Trước khi chuyển kiểu, cần hiểu giá trị *thực sự* được lưu là gì:

| Kiểu Oracle | Nội dung | Điều cần thận trọng |
|---|---|---|
| `NUMBER` | Số thập phân, có thể khai báo precision/scale | Giới hạn số chữ số và làm tròn khi giảm scale |
| `BINARY_FLOAT` / `BINARY_DOUBLE` | Số thực dấu phẩy động nhị phân | Nhiều số thập phân không biểu diễn chính xác tuyệt đối |
| `CHAR` / `VARCHAR2` | Chuỗi ký tự | Phân biệt độ dài theo BYTE/CHAR; giá trị số/ngày lưu dạng text không tự có ngữ nghĩa số/ngày |
| `DATE` | Năm, tháng, ngày, giờ, phút, giây | **Có phần thời gian**, nhưng không có phần giây lẻ và không lưu múi giờ |
| `TIMESTAMP` | Ngày giờ với phần giây lẻ theo precision | Không chứa thông tin múi giờ |
| `TIMESTAMP WITH TIME ZONE` | Thời điểm ngày giờ cùng thông tin múi giờ/offset | Cần chọn quy tắc hiển thị/đổi vùng giờ khi tích hợp |
| `TIMESTAMP WITH LOCAL TIME ZONE` | Giá trị được chuẩn hóa theo cơ chế Oracle và hiển thị theo múi giờ session | Không bảo toàn nguyên văn offset ban đầu như một chuỗi độc lập |
| `RAW`, `BLOB` | Byte nhị phân | Không nên chuyển thành chuỗi ký tự tùy tiện |

Ví dụ `'125.50'` là **chuỗi**, khác với số `125.50`. Chuỗi `'2026-11-14'` khác với giá trị ngày `DATE '2026-11-14'`. Hai chuỗi có thể trông giống dữ liệu hợp lệ nhưng Oracle chỉ biết ngữ nghĩa sau khi chuyển kiểu theo quy tắc rõ ràng.

## 3. Những hàm chuyển đổi tường minh quan trọng

| Hàm/cú pháp | Công dụng điển hình | Ví dụ |
|---|---|---|
| `TO_NUMBER(text, format, nlsparam)` | Chuỗi sang số | `TO_NUMBER('1,234.50', '9G999D99', ...)` |
| `TO_CHAR(number, format, nlsparam)` | Số sang chuỗi trình bày | `TO_CHAR(1234.5, 'FM9G999D00', ...)` |
| `TO_DATE(text, format, nlsparam)` | Chuỗi sang `DATE` | `TO_DATE('2026-11-14', 'YYYY-MM-DD')` |
| `TO_TIMESTAMP(text, format)` | Chuỗi sang `TIMESTAMP` | `TO_TIMESTAMP('2026-11-14 08:30:12.123456', 'YYYY-MM-DD HH24:MI:SS.FF6')` |
| `TO_TIMESTAMP_TZ(text, format)` | Chuỗi sang timestamp có múi giờ | `TO_TIMESTAMP_TZ('2026-11-14 08:30 +07:00', 'YYYY-MM-DD HH24:MI TZH:TZM')` |
| `TO_CHAR(date_or_timestamp, format)` | Ngày giờ sang chuỗi hiển thị | `TO_CHAR(SYSDATE, 'YYYY-MM-DD HH24:MI:SS')` |
| `CAST(expr AS type)` | Ép một biểu thức sang kiểu SQL khác | `CAST(123.456 AS NUMBER(6,2))` |
| `DATE 'YYYY-MM-DD'` | Literal kiểu DATE theo cú pháp ANSI | `DATE '2026-11-14'` |
| `TIMESTAMP 'YYYY-MM-DD HH24:MI:SS...'` | Literal kiểu TIMESTAMP | `TIMESTAMP '2026-11-14 08:30:12.123'` |

Format model của Oracle có vai trò rất quan trọng: `YYYY` là năm bốn chữ số, `MM` là tháng số, `DD` là ngày; `HH24` là giờ 24 giờ, `MI` là phút và `SS` là giây. Với số, `D` biểu thị dấu thập phân và `G` biểu thị dấu phân nhóm theo thiết lập NLS.

### 3.1. Chuyển chuỗi sang số

~~~sql
SELECT TO_NUMBER(
         '1,234.50',
         '9G999D99',
         'NLS_NUMERIC_CHARACTERS = ''.,'''
       ) AS amount
FROM dual;
~~~

Trong ví dụ, đối số NLS chỉ rõ dấu thập phân là dấu chấm và dấu nhóm là dấu phẩy, nên chuỗi `1,234.50` mang nghĩa **một nghìn hai trăm ba mươi bốn phẩy năm mươi**. Không dùng một `TO_NUMBER('1,234.50')` không format cho dữ liệu nhập từ bên ngoài rồi giả định mọi session đều hiểu như nhau.

Khi chuyển ngược để **trình bày**:

~~~sql
SELECT TO_CHAR(
         1234.5,
         'FM9G999D00',
         'NLS_NUMERIC_CHARACTERS = ''.,'''
       ) AS formatted_amount
FROM dual;
~~~

`FM` giảm khoảng trắng đệm thường xuất hiện trong một số định dạng số; `D00` cho phép hiện hai chữ số thập phân theo format. Kết quả là **chuỗi để hiển thị**, không nên dùng chính chuỗi có phân nhóm thay cho `NUMBER` để tính toán hay sắp xếp số.

### 3.2. Chuyển chuỗi sang ngày giờ

~~~sql
SELECT TO_DATE('2026-11-14', 'YYYY-MM-DD') AS order_date
FROM dual;

SELECT TO_TIMESTAMP(
         '2026-11-14 08:30:12.123456',
         'YYYY-MM-DD HH24:MI:SS.FF6'
       ) AS event_time
FROM dual;

SELECT TO_TIMESTAMP_TZ(
         '2026-11-14 08:30:12.123456 +07:00',
         'YYYY-MM-DD HH24:MI:SS.FF6 TZH:TZM'
       ) AS event_time_tz
FROM dual;
~~~

Ba phép chuyển đổi tạo **ba kiểu khác nhau**: `DATE` (đến giây), `TIMESTAMP` (giây lẻ), và `TIMESTAMP WITH TIME ZONE` (có offset/múi giờ). Dữ liệu gốc từ API có kèm offset nên được giữ ở kiểu và contract hỗ trợ thông tin đó, thay vì cắt bỏ `+07:00` rồi lưu như giờ địa phương không có ngữ cảnh.

Nếu chỉ cần ngày không có phần giờ, có thể dùng literal:

~~~sql
INSERT INTO lab_event (event_date)
VALUES (DATE '2026-11-14');
~~~

Literal `DATE '2026-11-14'` độc lập với `NLS_DATE_FORMAT` và có phần thời gian bằng **00:00:00**. Nó phù hợp khi ngày thực sự là dữ liệu dạng ngày; nếu sự kiện có thời điểm giờ/phút/giây, cần lưu và chuyển đúng kiểu.

### 3.3. Chuyển số/DATE thành chuỗi để hiển thị

~~~sql
SELECT
  TO_CHAR(DATE '2026-11-14', 'DD/MM/YYYY') AS date_vi,
  TO_CHAR(
    TIMESTAMP '2026-11-14 08:30:12.123',
    'YYYY-MM-DD"T"HH24:MI:SS.FF3'
  ) AS event_text
FROM dual;
~~~

Đừng dùng phép chuyển sang chuỗi chỉ để lưu `DATE` hoặc `TIMESTAMP` vào một cột `VARCHAR2` nếu schema có thể lưu kiểu ngày giờ thật. Chuỗi chỉ có ích khi **xuất dữ liệu**, tạo báo cáo hoặc xử lý một giao thức cần text.

### 3.4. Dùng CAST khi đã biết kiểu đích

~~~sql
SELECT
  CAST(123.456 AS NUMBER(6,2)) AS rounded_amount,
  CAST(TIMESTAMP '2026-11-14 08:30:12.987'
       AS DATE) AS date_without_fraction
FROM dual;
~~~

`CAST` diễn đạt rõ kiểu đích nhưng **không thay thế format model** khi cần parse văn bản ngày giờ của hệ thống bên ngoài. Với dữ liệu chuỗi có cấu trúc `YYYY-MM-DD`, `TO_DATE(text, 'YYYY-MM-DD')` rõ ràng hơn việc ép kiểu phụ thuộc NLS.

## 4. Chuyển kiểu ngầm định: tiện nhưng khó dự đoán

Oracle cho phép implicit conversion trong một số phép so sánh, biểu thức và phép gán. Chẳng hạn cột `ORDER_ID NUMBER` được so sánh với chuỗi:

~~~sql
SELECT order_id
FROM lab_order
WHERE order_id = '101';
~~~

Vì phía trái là số, Oracle có thể chuyển chuỗi `'101'` sang số `101`. Truy vấn chạy được không chứng minh đây là cách viết tốt; nếu ứng dụng bắt đầu gửi `'101A'`, phép chuyển đổi sẽ thất bại.

Trường hợp ngược lại nguy hiểm hơn:

~~~sql
-- CUSTOMER_CODE là VARCHAR2, nhưng literal 1001 là NUMBER.
SELECT customer_code
FROM lab_customer
WHERE customer_code = 1001;
~~~

Trong so sánh số với chuỗi, Oracle có thể chuyển **giá trị cột ký tự sang số**. Các dòng `'1001'` có thể so khớp, nhưng cột chứa `'A1001'` hoặc `'001001X'` không thể chuyển thành số. Kết quả có thể là **`ORA-01722: invalid number`**; ngoài ra, việc áp dụng hàm lên cột có thể ảnh hưởng khả năng dùng index thông thường. Điều kiện lọc khác trong cùng câu SQL **không bảo đảm** luôn được đánh giá trước để loại dòng lỗi, vì optimizer được phép thay đổi kế hoạch và thứ tự xử lý.

Nếu `CUSTOMER_CODE` là **mã nghiệp vụ**, phải so sánh với **chuỗi**:

~~~sql
SELECT customer_code
FROM lab_customer
WHERE customer_code = '1001';
~~~

Ở đây `'01001'` và `'1001'` là **hai mã khác nhau**, dù giá trị số có thể giống nhau. Ép chuỗi mã thành số có thể làm mất các số 0 ở đầu, làm hỏng tính đồng nhất của mã.

### 4.1. Những ngữ cảnh dễ xảy ra implicit conversion

| Ngữ cảnh | Ví dụ rủi ro | Cách viết chủ động |
|---|---|---|
| So sánh `NUMBER` với text | `amount = '100.50'` | Bind tham số kiểu số hoặc `TO_NUMBER` có format/NLS |
| So sánh `VARCHAR2` với số | `customer_code = 1001` | `customer_code = '1001'` hoặc bind `VARCHAR2` |
| So sánh `DATE` với text | `order_date = '14/11/2026'` | `order_date = DATE '2026-11-14'` hoặc `TO_DATE` có format |
| Gán text vào cột số | `INSERT ... VALUES ('1,25')` | Chuyển/validate giá trị trước, rồi bind `NUMBER` |
| Ghép biểu thức khác kiểu | `CASE` hoặc `NVL` có nhiều kiểu | Chuẩn hóa các nhánh/đối số cùng kiểu mục tiêu |
| Kết nối JDBC | `setString` cho cột `NUMBER` | `setBigDecimal`, `setLong` tùy ngữ nghĩa |

**Lưu ý:** Oracle có bảng quy tắc implicit conversion cho các kiểu và toán tử khác nhau; không phải bất kỳ cặp kiểu nào cũng tự chuyển được. Chiều chuyển đổi còn phụ thuộc ngữ cảnh. Không nên lập trình dựa vào suy đoán “Oracle sẽ luôn chuyển bên phải sang bên trái”.

### 4.2. Tác động tới index và execution plan

Giả sử bảng có index trên `CUSTOMER_CODE VARCHAR2(32)`:

~~~sql
CREATE INDEX ix_lab_customer_code
ON lab_customer (customer_code);
~~~

So sánh đúng kiểu:

~~~sql
SELECT customer_id
FROM lab_customer
WHERE customer_code = :customer_code;
-- Bind :customer_code là VARCHAR2.
~~~

Nếu ứng dụng truyền tham số số, một predicate có thể bị biểu diễn theo hướng tương đương `TO_NUMBER(customer_code) = :number_value`. Phép chuyển cột thành số không chỉ có thể gây `ORA-01722` mà còn có thể ngăn sử dụng trực tiếp index thông thường trên cột chuỗi. Oracle có các khả năng tối ưu đặc biệt, nhưng sửa **đúng kiểu** thường là bước đầu tiên cần thực hiện.

Khi chẩn đoán, xem predicate trong execution plan bằng `DBMS_XPLAN.DISPLAY_CURSOR` (nếu có quyền và SQL đã chạy), tìm những biểu thức chuyển đổi như `TO_NUMBER(column_name)`, `INTERNAL_FUNCTION(...)` hoặc các phép conversion khác. Không thể chỉ dựa vào thời gian chạy để kết luận có implicit conversion; cần đọc plan và bind datatypes.

## 5. NLS: cùng một chuỗi, session khác nhau có thể hiểu khác

Oracle có các tham số **National Language Support (NLS)** ảnh hưởng đến cách đọc/hiển thị số và ngày khi chuyển đổi không có format đầy đủ:

~~~sql
SELECT parameter, value
FROM nls_session_parameters
WHERE parameter IN (
  'NLS_DATE_FORMAT',
  'NLS_TIMESTAMP_FORMAT',
  'NLS_DATE_LANGUAGE',
  'NLS_NUMERIC_CHARACTERS'
)
ORDER BY parameter;
~~~

### 5.1. NLS_DATE_FORMAT

Một session có thể cấu hình:

~~~sql
ALTER SESSION SET NLS_DATE_FORMAT = 'DD/MM/YYYY';
~~~

Khi đó một chuỗi `'14/11/2026'` có thể được Oracle hiểu theo kỳ vọng ở một phép chuyển ngày ngầm định. Nhưng ở session có `NLS_DATE_FORMAT = 'YYYY-MM-DD'`, cùng chuỗi có thể không khớp và sinh lỗi. Việc xem `DATE` ở SQL tool cũng có thể chỉ hiện ngày mà **che phần giờ**, dù giá trị bên trong vẫn chứa giờ/phút/giây.

Hãy ghi rõ format khi parse và khi hiển thị:

~~~sql
SELECT
  TO_DATE('14/11/2026', 'DD/MM/YYYY') AS parsed_date,
  TO_CHAR(
    TO_DATE('14/11/2026', 'DD/MM/YYYY'),
    'YYYY-MM-DD HH24:MI:SS'
  ) AS shown_date
FROM dual;
~~~

Đối với hệ thống nhập text nghiêm ngặt, có thể dùng modifier `FX` trong format model để yêu cầu đối chiếu format chặt chẽ hơn:

~~~sql
SELECT TO_DATE('2026-11-14', 'FXYYYY-MM-DD')
FROM dual;
~~~

Ngay cả format đúng vẫn không biến `'2026-02-30'` thành ngày hợp lệ. Các thành phần ngày phải có giá trị tồn tại thực tế.

### 5.2. NLS_DATE_LANGUAGE

Nếu chuỗi ngày chứa tên tháng:

~~~sql
SELECT TO_DATE(
         '15-MAR-2026',
         'DD-MON-YYYY',
         'NLS_DATE_LANGUAGE = American'
       ) AS parsed_date
FROM dual;
~~~

Chỉ định ngôn ngữ giúp giảm phụ thuộc session với ký hiệu tháng dạng chữ. Nếu có thể, nên truyền ngày tháng dạng số theo một giao thức rõ ràng hoặc truyền bind date/timestamp, thay vì dùng tên tháng bằng ngôn ngữ tự nhiên.

### 5.3. NLS_NUMERIC_CHARACTERS

Cùng chuỗi `1,234` có thể mang hai ý nghĩa: **một nghìn hai trăm ba mươi bốn** (dấu phẩy nhóm) hoặc **một phẩy hai ba bốn** (dấu phẩy thập phân). Không được tự suy.

~~~sql
-- 1,234 là một nghìn hai trăm ba mươi bốn.
SELECT TO_NUMBER(
  '1,234',
  '9G999',
  'NLS_NUMERIC_CHARACTERS = ''.,'''
) AS number_value
FROM dual;

-- 1,234 là một phẩy hai ba bốn.
SELECT TO_NUMBER(
  '1,234',
  '9D999',
  'NLS_NUMERIC_CHARACTERS = '',.'''
) AS number_value
FROM dual;
~~~

Trong import CSV hoặc API, **format đầu vào** phải là một phần của contract dữ liệu. Cấu hình NLS của session không thể thay thế hợp đồng này.

## 6. Mất dữ liệu không phải lúc nào cũng là lỗi

Khi nói “lỗi mất dữ liệu”, cần phân biệt ba hiện tượng:

1. **Chuyển đổi thất bại và có lỗi:** không ghi được giá trị, ví dụ `ORA-01438` hoặc `ORA-12899`.
2. **Chuyển đổi thành công nhưng giá trị thay đổi:** làm tròn số hoặc mất phần giây lẻ.
3. **Chuyển đổi vẫn ra giá trị nhưng sai ngữ nghĩa:** sai định dạng ngày, sai đơn vị tiền tệ, sai múi giờ hoặc mất số 0 đầu mã.

Không phải tất cả những trường hợp trên đều có thể tự động nhận ra bằng một câu SQL kiểm tra kiểu. Nhiều lỗi cần quy ước nghiệp vụ rõ ràng.

### 6.1. Precision và scale của NUMBER

Với `NUMBER(p,s)`:

- **p (precision):** tổng số chữ số có nghĩa được cho phép.
- **s (scale):** số chữ số thập phân được giữ theo cấu hình; Oracle có thể làm tròn khi gán vào độ chính xác thấp hơn.

Ví dụ:

~~~sql
CREATE TABLE lab_amount (
  amount_id NUMBER PRIMARY KEY,
  amount    NUMBER(5,2) NOT NULL
);

INSERT INTO lab_amount (amount_id, amount)
VALUES (1, 123.456);

SELECT amount
FROM lab_amount
WHERE amount_id = 1;
~~~

Giá trị có thể được lưu thành **123.46** vì scale là 2, dù giá trị nguồn là **123.456**. Câu `INSERT` có thể thành công: đây là **thay đổi độ chính xác mà không báo lỗi**. Nếu quy tắc nghiệp vụ không cho phép làm tròn tự động, ứng dụng phải phát hiện/kiểm tra độ chính xác trước khi ghi.

Ngược lại:

~~~sql
-- NUMBER(5,2) có tối đa ba chữ số trước dấu thập phân.
-- 1234.56 không thể chứa trong NUMBER(5,2).
INSERT INTO lab_amount (amount_id, amount)
VALUES (2, 1234.56);
~~~

Lệnh sẽ lỗi vì giá trị vượt precision/scale của cột (thường là **`ORA-01438`**). Trường hợp giá trị gần trần bị **làm tròn lên** có thể khiến số chữ số phần nguyên tăng và cũng vượt giới hạn.

**Quyết định thiết kế:** Với tiền, số lượng và tỷ lệ, chọn `NUMBER(p,s)` theo phạm vi giá trị, độ chính xác nghiệp vụ và quy tắc làm tròn. Đừng chỉ chọn `NUMBER(5,2)` theo cảm giác rằng “chắc đủ”.

### 6.2. BINARY_FLOAT/BINARY_DOUBLE và sai số nhị phân

`BINARY_FLOAT` và `BINARY_DOUBLE` dùng biểu diễn dấu phẩy động nhị phân. Giá trị thập phân như `0.1` thường không được biểu diễn chính xác tuyệt đối trong hệ nhị phân, nên tính toán có thể xuất hiện sai số làm tròn. Chuyển giữa `NUMBER` và các kiểu này có thể thay đổi độ chính xác.

~~~sql
SELECT
  CAST(0.1 AS BINARY_DOUBLE) AS binary_value,
  CAST(0.1 AS NUMBER) AS decimal_value
FROM dual;
~~~

Đừng chỉ xem chuỗi hiển thị ngắn để kết luận hai phép tính lưu hoàn toàn giống nhau. Khi yêu cầu tính toán thập phân chính xác như tiền tệ, thường nên dùng `NUMBER(p,s)` trong Oracle và `BigDecimal` trong Java; xác định quy tắc rounding thống nhất ở tầng nghiệp vụ.

### 6.3. DATE và TIMESTAMP: mất phần giây lẻ

Oracle `DATE` lưu giờ/phút/giây nhưng **không giữ phần giây lẻ**. Chuyển timestamp có fractional seconds sang DATE làm mất độ chính xác thời gian:

~~~sql
SELECT
  TO_CHAR(
    TIMESTAMP '2026-11-14 08:30:12.987654',
    'YYYY-MM-DD HH24:MI:SS.FF6'
  ) AS original_timestamp,
  TO_CHAR(
    CAST(TIMESTAMP '2026-11-14 08:30:12.987654' AS DATE),
    'YYYY-MM-DD HH24:MI:SS'
  ) AS cast_as_date
FROM dual;
~~~

Cột `CAST_AS_DATE` không còn phần `.987654`. Nếu bài toán cần thứ tự sự kiện ở mức mili- hoặc microsecond, phải dùng kiểu và precision thích hợp, không chuyển về DATE chỉ vì công cụ hiển thị dễ đọc hơn.

Một lỗi khác là **tự cắt thời gian khi định dạng**:

~~~sql
SELECT TO_DATE(
         TO_CHAR(
           TIMESTAMP '2026-11-14 08:30:12.987654',
           'YYYY-MM-DD'
         ),
         'YYYY-MM-DD'
       ) AS lost_time
FROM dual;
~~~

Kết quả chỉ còn ngày `2026-11-14` với giờ `00:00:00`. Đây là phép biến đổi có thể hữu ích khi cố ý lấy ngày, nhưng không phù hợp nếu cần giữ thời điểm gốc.

### 6.4. Nguy cơ đổi múi giờ hoặc mất offset

Giả sử API gửi:

~~~text
2026-11-14T08:30:12.123456+07:00
~~~

Giá trị này chứa thời gian và **offset +07:00**. Nếu chỉ lấy `'2026-11-14 08:30:12'` rồi gán sang `DATE` hoặc `TIMESTAMP` không kèm timezone, thông tin offset bị bỏ. Một hệ thống khác có thể hiểu đó là 08:30 UTC thay vì 08:30 ở +07:00, dẫn tới sai lệch **bảy giờ**.

Nếu cần lưu thời điểm có thông tin vùng giờ, có thể parse tường minh:

~~~sql
SELECT TO_TIMESTAMP_TZ(
  '2026-11-14 08:30:12.123456 +07:00',
  'YYYY-MM-DD HH24:MI:SS.FF6 TZH:TZM'
) AS event_instant
FROM dual;
~~~

Khi chuyển sang UTC hoặc sang timezone khác, hãy dùng chức năng date/timezone được Oracle hỗ trợ và quy ước thống nhất. `TIMESTAMP WITH LOCAL TIME ZONE` có cách chuẩn hóa/hiển thị theo timezone session; nó không phải kiểu lưu riêng nguyên văn chuỗi offset đã nhập.

### 6.5. VARCHAR2: BYTE khác CHAR

Kích thước ký tự Unicode và kích thước **byte** không phải lúc nào cũng bằng nhau. Ví dụ ở database character set `AL32UTF8`, ba ký tự `'ááá'` chiếm **sáu byte**:

~~~sql
SELECT
  LENGTH('ááá')  AS char_count,
  LENGTHB('ááá') AS byte_count
FROM dual;
~~~

Nếu cột dùng `VARCHAR2(5 BYTE)`, chuỗi này vượt giới hạn byte, dù chỉ có ba ký tự; khi insert có thể gặp **`ORA-12899`**. Với `VARCHAR2(5 CHAR)`, chuỗi ba ký tự phù hợp trong phạm vi giới hạn ký tự và giới hạn byte tối đa tương ứng của Oracle.

~~~sql
CREATE TABLE lab_text_limit (
  id        NUMBER PRIMARY KEY,
  text_byte VARCHAR2(5 BYTE),
  text_char VARCHAR2(5 CHAR)
);

-- Trong AL32UTF8, giá trị 3 ký tự này có thể chiếm 6 byte,
-- vượt giới hạn của TEXT_BYTE.
INSERT INTO lab_text_limit (id, text_byte)
VALUES (1, 'ááá');

-- Cột TEXT_CHAR cho phép tới 5 ký tự, với điều kiện
-- không vượt giới hạn byte tối đa do Oracle áp dụng.
INSERT INTO lab_text_limit (id, text_char)
VALUES (2, 'ááá');
~~~

Đối với tên tiếng Việt, mô tả hoặc văn bản đa ngôn ngữ, phải thống nhất character set và length semantics khi thiết kế schema. Không tự cắt chuỗi bằng số byte nếu yêu cầu là giới hạn số ký tự hiển thị.

### 6.6. Mã định danh không phải số đếm

Mã `'000123'`, mã bưu chính hoặc số tài khoản có thể chỉ chứa chữ số nhưng về mặt nghiệp vụ là **định danh ký tự**. Nếu chuyển `'000123'` sang `NUMBER`, các số 0 ở đầu biến mất. Chuyển lại bằng `TO_CHAR(123)` không thể suy chính xác mã gốc dài bao nhiêu, trừ khi có quy tắc format riêng được lưu.

Vì vậy, quyết định kiểu dựa trên **ngữ nghĩa**: có thực hiện cộng/trừ/nhân/chia không, hay chỉ so sánh và định danh? Nhiều chuỗi số cần giữ ở `VARCHAR2`.

## 7. Lỗi chuyển kiểu thường gặp và ý nghĩa

| Mã lỗi/dấu hiệu | Nguyên nhân thường gặp | Ví dụ / hướng xử lý |
|---|---|---|
| **`ORA-01722: invalid number`** | Chuỗi không chuyển được thành số khi so sánh/gán/chuyển kiểu | Không so sánh cột mã `VARCHAR2` với NUMBER; kiểm tra nguồn text trước `TO_NUMBER` |
| **`ORA-01861: literal does not match format string`** | Chuỗi ngày/giờ không khớp format model | Dùng `TO_DATE(text, 'YYYY-MM-DD')` với format thực của input |
| **`ORA-01843: not a valid month`** | Thành phần tháng không hợp lệ hoặc parse sai format | Kiểm tra thứ tự ngày/tháng, NLS date language |
| **`ORA-01830: date format picture ends before converting entire input string`** | Format không bao phủ toàn bộ chuỗi input | Bổ sung phần giờ/giây/offset tương ứng |
| **`ORA-01438: value larger than specified precision`** | Giá trị số vượt giới hạn cột `NUMBER(p,s)` | Chọn precision phù hợp, kiểm tra đầu vào |
| **`ORA-12899: value too large for column`** | Chuỗi vượt kích thước BYTE/CHAR của cột | Kiểm tra `LENGTH`/`LENGTHB` và length semantics |
| **`ORA-06502: PL/SQL numeric or value error`** | Chuyển/gán vào biến PL/SQL không đủ độ dài/precision hoặc lỗi giá trị | Xem biến đích, định nghĩa record, conversion |
| **Không có lỗi nhưng dữ liệu khác** | Làm tròn, bỏ phần giây, mất offset, bỏ số 0 đầu | So sánh kiểu và giá trị trước/sau ở ranh giới nhập |

Không nhất thiết mọi phiên bản/câu SQL đều báo đúng cùng một mã lỗi cho một dữ liệu sai: lỗi phụ thuộc câu lệnh, nơi chuyển đổi và kiểu đích. Điều quan trọng là xác định **giá trị nào đang được chuyển, từ kiểu nào sang kiểu nào, với format/NLS nào**.

### Tại sao thêm điều kiện lọc vẫn có thể nhận ORA-01722?

Giả sử `RAW_AMOUNT` là chuỗi và chứa cả `'100.00'` và `'UNKNOWN'`:

~~~sql
-- Không an toàn khi tin rằng điều kiện đầu tiên
-- luôn được đánh giá trước điều kiện thứ hai.
SELECT raw_amount
FROM lab_raw_payment
WHERE REGEXP_LIKE(raw_amount, '^[0-9]+(\.[0-9]+)?$')
  AND TO_NUMBER(raw_amount) > 50;
~~~

Optimizer có thể biến đổi và sắp xếp việc đánh giá predicate; không nên dựa vào thứ tự viết `AND` để bảo đảm việc ép kiểu chỉ diễn ra sau khi lọc. Ngoài ra regex chưa xử lý đầy đủ giới hạn precision, dấu âm, nhóm chữ số và mọi NLS format. Nên dùng cơ chế **kiểm tra/chuyển đổi an toàn** được Oracle hỗ trợ, hoặc làm sạch dữ liệu ngay từ giai đoạn nhập.

## 8. Kiểm tra dữ liệu trước khi chuyển với VALIDATE_CONVERSION

Oracle hỗ trợ `VALIDATE_CONVERSION` ở các phiên bản hiện đại (từ 12.2, với những kiểu chuyển đổi được hỗ trợ). Hàm này trả giá trị cho biết một biểu thức có thể chuyển sang kiểu đích theo format đã chỉ định hay không, thay vì buộc câu truy vấn phải thất bại ngay khi gặp một giá trị không chuyển được.

### 8.1. Bảng staging giữ dữ liệu thô

Khi nhập từ CSV hoặc nguồn ngoài, nên lưu bản gốc vào bảng **staging** trước khi chuyển sang kiểu nghiệp vụ:

~~~sql
CREATE TABLE lab_raw_payment (
  row_id        NUMBER PRIMARY KEY,
  raw_amount    VARCHAR2(60),
  raw_date      VARCHAR2(60)
);

INSERT INTO lab_raw_payment VALUES
  (1, '125.50', '2026-11-14');

INSERT INTO lab_raw_payment VALUES
  (2, 'UNKNOWN', '2026-11-14');

INSERT INTO lab_raw_payment VALUES
  (3, '90.00', '2026-02-30');

INSERT INTO lab_raw_payment VALUES
  (4, '1,200.50', '14/11/2026');

COMMIT;
~~~

Đây là dữ liệu tình huống: hàng 1 hợp lệ theo format đang chọn, hàng 2 sai số, hàng 3 sai ngày, hàng 4 có **một format khác**. Không được kết luận hàng 4 “vô nghĩa”; nó có thể hợp lệ với **contract khác**. Việc chọn format chuẩn phải được làm trước khi tự động chuyển đổi.

### 8.2. Phát hiện bản ghi sai format

Giả sử contract đầu vào yêu cầu số dạng `125.50` (dấu chấm thập phân, không dấu nhóm) và ngày dạng `YYYY-MM-DD`:

~~~sql
SELECT
  row_id,
  raw_amount,
  raw_date,
  VALIDATE_CONVERSION(
    raw_amount AS NUMBER,
    '9999999D99',
    'NLS_NUMERIC_CHARACTERS = ''.,'''
  ) AS amount_valid,
  VALIDATE_CONVERSION(
    raw_date AS DATE,
    'FXYYYY-MM-DD'
  ) AS date_valid
FROM lab_raw_payment
ORDER BY row_id;
~~~

Các cột `AMOUNT_VALID` và `DATE_VALID` giúp phân loại dữ liệu có thể được Oracle parse theo format đã chọn. Khi xử lý dữ liệu có `NULL`, phải xác định riêng quy tắc nghiệp vụ về null; một phép kiểm tra chuyển kiểu thành công không đồng nghĩa giá trị đã đáp ứng quy tắc **NOT NULL** hay giá trị hợp lệ của nghiệp vụ.

### 8.3. DEFAULT ... ON CONVERSION ERROR

Ở những phiên bản hỗ trợ (Oracle 12.2 trở lên), `TO_NUMBER`, `TO_DATE` và các hàm chuyển đổi liên quan có thể hỗ trợ cú pháp **`DEFAULT ... ON CONVERSION ERROR`**:

~~~sql
SELECT
  row_id,
  TO_NUMBER(
    raw_amount DEFAULT NULL ON CONVERSION ERROR,
    '9999999D99',
    'NLS_NUMERIC_CHARACTERS = ''.,'''
  ) AS amount_number,
  TO_DATE(
    raw_date DEFAULT NULL ON CONVERSION ERROR,
    'FXYYYY-MM-DD'
  ) AS payment_date
FROM lab_raw_payment
ORDER BY row_id;
~~~

Như vậy, giá trị không parse được sẽ thành `NULL` **theo lựa chọn rõ ràng của tác giả SQL** thay vì khiến cả truy vấn lỗi. Tuy nhiên, `NULL` vừa có thể nghĩa là đầu vào thiếu vừa có thể nghĩa là **đầu vào bị lỗi**; không nên âm thầm nhập những `NULL` này vào bảng nghiệp vụ. Hãy giữ cột raw, cờ kiểm tra và lý do lỗi ở staging để sửa dữ liệu hoặc phản hồi về hệ thống nguồn.

Lưu ý: `DEFAULT ... ON CONVERSION ERROR` chỉ xử lý lỗi trong **bước chuyển đổi** theo phạm vi mà hàm cho phép; lỗi xảy ra khi đánh giá biểu thức đầu vào hoặc những vi phạm constraint sau đó vẫn có thể phát sinh.

### 8.4. Chuyển vào bảng typed sau khi xác thực

Ví dụ một bảng đích có kiểu đúng:

~~~sql
CREATE TABLE lab_payment (
  payment_id   NUMBER PRIMARY KEY,
  amount       NUMBER(12,2) NOT NULL,
  payment_date DATE NOT NULL
);
~~~

Chỉ chọn những hàng đáp ứng **định dạng và giá trị** được chấp nhận:

~~~sql
INSERT INTO lab_payment (payment_id, amount, payment_date)
SELECT
  row_id,
  TO_NUMBER(
    raw_amount,
    '9999999D99',
    'NLS_NUMERIC_CHARACTERS = ''.,'''
  ),
  TO_DATE(raw_date, 'FXYYYY-MM-DD')
FROM lab_raw_payment
WHERE raw_amount IS NOT NULL
  AND raw_date IS NOT NULL
  AND VALIDATE_CONVERSION(
        raw_amount AS NUMBER,
        '9999999D99',
        'NLS_NUMERIC_CHARACTERS = ''.,'''
      ) = 1
  AND VALIDATE_CONVERSION(raw_date AS DATE, 'FXYYYY-MM-DD') = 1;
~~~

Đối với một pipeline thực tế, cách an toàn hơn nữa là tạo các biểu thức chuyển đổi **an toàn** ở bước staging, sau đó chọn bản ghi hợp lệ kèm các kiểm tra phạm vi số, constraint nghiệp vụ và tính chính xác trước khi insert. Không dùng thứ tự predicate như một cơ chế bảo vệ dữ liệu. Ở ví dụ này, `VALIDATE_CONVERSION` giúp diễn đạt điều kiện lọc theo format, nhưng cần đánh giá kiểu đích `NUMBER(12,2)`: một số parse được thành NUMBER vẫn có thể bị làm tròn hoặc vượt precision khi ghi.

### 8.5. Nếu Oracle cũ chưa có VALIDATE_CONVERSION

Không tự thay `VALIDATE_CONVERSION` bằng một regex đơn giản rồi cho rằng đã kiểm tra được tất cả số/ngày. Một hướng là xử lý parse ở ứng dụng/ETL với parser rõ format và lưu lỗi vào bảng reject; hoặc viết hàm PL/SQL chuyển đổi có **exception handling** cho từng bản ghi, trả về trạng thái lỗi thay vì khiến batch dừng. Hãy cân nhắc hiệu năng và chi phí gọi hàm khi xử lý dữ liệu lớn.

## 9. Kiểm soát mất độ chính xác trước khi lưu

Không đủ nếu một phép chuyển kiểu **không ném exception**. Với dữ liệu quan trọng, cần kiểm tra **giá trị trước và sau**.

### 9.1. Phát hiện số sẽ bị làm tròn

Với một số đã parse thành `NUMBER`, nếu cột đích là `NUMBER(12,2)` mà quy tắc nghiệp vụ **không cho phép** bất kỳ chữ số nào sau vị trí thập phân thứ hai:

~~~sql
SELECT
  123.456 AS source_amount,
  ROUND(123.456, 2) AS rounded_amount
FROM dual;

-- 123.456 <> ROUND(123.456, 2) nên nguồn sẽ bị thay đổi.
SELECT CASE
         WHEN 123.456 = ROUND(123.456, 2)
         THEN 'EXACT'
         ELSE 'WOULD_ROUND'
       END AS precision_check
FROM dual;
~~~

Trong luồng nhập thật, tính predicate trên giá trị `NUMBER` đã được parse an toàn. Nếu nghiệp vụ **cho phép** làm tròn, phải định nghĩa mode và thời điểm làm tròn rõ ràng. Với tiền, việc tính riêng từng dòng rồi cộng thường có thể khác việc cộng rồi làm tròn tổng.

### 9.2. Phát hiện phần thời gian bị mất

Trước khi chuyển từ `TIMESTAMP` sang `DATE`, xác định yêu cầu:

- Nếu chỉ cần ngày hoặc thời gian đến giây, bỏ fractional seconds có thể là quyết định chủ đích.
- Nếu cần sắp thứ tự giao dịch chính xác đến microsecond, phải giữ `TIMESTAMP(p)`.
- Nếu dữ liệu đến từ nhiều timezone, cần bảo toàn thông tin offset/instant trong kiểu hoặc contract tương ứng.

Không nên chuyển qua `TO_CHAR` và `TO_DATE` để “xóa timezone” mà không nêu lý do. Một thay đổi format của màn hình **không yêu cầu** thay đổi kiểu dữ liệu được lưu.

### 9.3. Kiểm soát chiều dài ký tự

~~~sql
SELECT
  LENGTH('ááá') AS length_chars,
  LENGTHB('ááá') AS length_bytes
FROM dual;
~~~

Khi target là `VARCHAR2(n BYTE)`, hãy xét độ dài byte trong character set phù hợp; khi target là `VARCHAR2(n CHAR)`, xét số ký tự nhưng vẫn phải quan tâm các giới hạn byte do Oracle quy định. Không dùng `SUBSTR`/`SUBSTRB` để cắt bớt dữ liệu tên người hoặc mã quan trọng mà không có quy tắc nghiệp vụ cho phép.

## 10. JDBC: bind đúng kiểu thay vì gửi mọi thứ thành String

Một ứng dụng Java thường nhận đầu vào dạng text từ HTTP/JSON/CSV, nhưng **không nên truyền tất cả giá trị đến Oracle bằng `PreparedStatement.setString()`** rồi trông chờ database tự đoán kiểu.

Ví dụ lưu đơn hàng:

~~~sql
CREATE TABLE lab_invoice (
  invoice_id NUMBER PRIMARY KEY,
  amount     NUMBER(12,2) NOT NULL,
  issued_at  TIMESTAMP(6) NOT NULL
);
~~~

Ứng dụng Java có thể parse/validate đầu vào theo contract và bind đúng kiểu:

~~~java
import java.math.BigDecimal;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.Timestamp;
import java.time.LocalDateTime;

String sql = """
    INSERT INTO lab_invoice (invoice_id, amount, issued_at)
    VALUES (?, ?, ?)
    """;

// Các giá trị này phải đã được xác thực theo contract đầu vào.
long invoiceId = 1001L;
BigDecimal amount = new BigDecimal("125.50");
LocalDateTime issuedAt =
    LocalDateTime.of(2026, 11, 14, 8, 30, 12, 123456000);

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setLong(1, invoiceId);                      // NUMBER
    ps.setBigDecimal(2, amount);                   // NUMBER(12,2)
    ps.setTimestamp(3, Timestamp.valueOf(issuedAt)); // TIMESTAMP
    ps.executeUpdate();
}
~~~

Ví dụ minh họa ánh xạ `TIMESTAMP` **không chứa timezone**. Nếu API gửi thời điểm có offset, hãy dùng mô hình thời gian và driver hỗ trợ `TIMESTAMP WITH TIME ZONE` tương ứng (chẳng hạn `OffsetDateTime` trong những phiên bản JDBC/Oracle hỗ trợ), và định nghĩa cách quy đổi timezone rõ ràng.

### 10.1. Những sai sót phổ biến ở tầng Java

| Cách viết | Rủi ro | Hướng đúng |
|---|---|---|
| `setString(1, "125,50")` cho cột NUMBER | Parse ngầm định tùy NLS | Parse bằng contract thành `BigDecimal` rồi `setBigDecimal` |
| `setString(1, "14/11/2026")` cho DATE | Format session có thể không khớp | Parse ngày ở ứng dụng rồi bind date/timestamp phù hợp |
| `new BigDecimal(0.1)` | Mang theo sai số biểu diễn `double` | `new BigDecimal("0.1")` hoặc phương thức phù hợp như `BigDecimal.valueOf` |
| `setDouble` cho tiền | Sai số floating point và độ chính xác | `setBigDecimal` + precision/scale nghiệp vụ |
| Lưu số tài khoản bằng `setLong` | Mất số 0 ở đầu, giới hạn phạm vi số | Cột `VARCHAR2` và `setString` |
| Dùng `java.sql.Date` cho thời điểm có giờ | Có thể mất phần giờ do ánh xạ kiểu ngày | `Timestamp` hoặc kiểu thời gian có timezone phù hợp |

Một giá trị đã bind đúng kiểu làm giảm phụ thuộc NLS, nhưng vẫn phải kiểm tra **precision/scale**, **phạm vi ngày**, **nullability** và các constraint của database. Bind variable chống SQL injection cho giá trị; nó không bảo đảm mọi dữ liệu có ý nghĩa hợp lệ.

### 10.2. Đọc dữ liệu về Java

Với cột `NUMBER(12,2)`, thường đọc bằng `ResultSet.getBigDecimal()`; với `TIMESTAMP` có thể đọc bằng `getTimestamp()` và ánh xạ sang loại `java.time` phù hợp. Tránh `getDouble()` nếu cần giữ độ chính xác của tiền. Với `DATE`, lưu ý Oracle DATE có cả phần thời gian: API chỉ lấy ngày có thể làm mất phần giờ khi ánh xạ vào `LocalDate`.

Ở tầng API JSON, nếu dữ liệu số là tiền hoặc giá trị đòi hỏi chính xác, cần contract serialization phù hợp; không giả định mọi JavaScript client giữ được tất cả chữ số có nghĩa của Oracle NUMBER khi đi qua `Number` dạng dấu phẩy động.

## 11. Bài thực hành theo từng loại lỗi

Các ví dụ dưới đây có thể chạy trên một schema thực hành của PDB; dùng các bảng có tiền tố `LAB_` để không đụng dữ liệu nghiệp vụ. Một số lệnh **cố ý gây lỗi** để quan sát Oracle, nên chạy riêng từng câu và ghi lại thông báo.

### Bài 1 — DATE literal so với chuỗi

~~~sql
SELECT
  TO_CHAR(DATE '2026-11-14', 'YYYY-MM-DD HH24:MI:SS')
    AS typed_date,
  TO_CHAR(
    TO_DATE('14/11/2026', 'DD/MM/YYYY'),
    'YYYY-MM-DD'
  ) AS parsed_date
FROM dual;
~~~

**Câu hỏi:** Tại sao literal `DATE '2026-11-14'` ít phụ thuộc session NLS hơn việc so sánh một cột DATE với chuỗi `'14/11/2026'`?

**Gợi ý:** Literal DATE và `TO_DATE` với format làm rõ kiểu/format, trong khi chuỗi không có kiểu DATE và có thể phụ thuộc cấu hình khi Oracle tự chuyển.

### Bài 2 — Chữ số nhưng là mã

~~~sql
SELECT
  '000123' AS original_code,
  TO_NUMBER('000123') AS converted_number
FROM dual;
~~~

**Câu hỏi:** Vì sao không nên lưu mã khách hàng hay mã bưu chính `000123` trong cột NUMBER nếu cần giữ nguyên chuỗi sáu ký tự?

**Gợi ý:** Giá trị số không chứa thông tin về số 0 đứng đầu. Chỉ có contract mã riêng mới cho phép tái tạo độ dài.

### Bài 3 — Làm tròn và tràn precision

~~~sql
CREATE TABLE lab_precision (
  id NUMBER PRIMARY KEY,
  amount NUMBER(5,2)
);

INSERT INTO lab_precision VALUES (1, 123.456);
SELECT id, amount FROM lab_precision;

-- Câu sau cố ý vượt phạm vi NUMBER(5,2).
INSERT INTO lab_precision VALUES (2, 1234.56);
~~~

**Câu hỏi:** Tại sao hàng 1 có thể lưu thành 123.46 nhưng hàng 2 báo lỗi? Nếu ứng dụng cần giữ 123.456 chính xác, cần thay đổi thiết kế hoặc quy tắc gì?

### Bài 4 — Dữ liệu đầu vào lẫn format

Tạo `LAB_RAW_PAYMENT` ở phần 8 và dùng `VALIDATE_CONVERSION` để tìm những dòng không theo contract số `9999999D99` và ngày `FXYYYY-MM-DD`.

**Câu hỏi:** Dòng chứa `'1,200.50'` có phải số không hợp lệ trong mọi trường hợp không? Tại sao không nên cho hệ thống tự chọn format tùy từng dòng mà không có nguồn gốc và chính sách rõ ràng?

**Gợi ý:** Nó có thể hợp lệ theo format có dấu nhóm; dữ liệu đầu vào cần contract nhất quán hoặc trường phân loại nguồn/locale.

### Bài 5 — Mất phần giây

~~~sql
SELECT
  TO_CHAR(
    TIMESTAMP '2026-11-14 08:30:12.123456',
    'HH24:MI:SS.FF6'
  ) AS source_time,
  TO_CHAR(
    CAST(TIMESTAMP '2026-11-14 08:30:12.123456' AS DATE),
    'HH24:MI:SS'
  ) AS target_time
FROM dual;
~~~

**Câu hỏi:** Nếu đây là timestamp của một giao dịch tài chính, vì sao phép chuyển `TIMESTAMP → DATE` có thể làm mất khả năng phân biệt thứ tự hai sự kiện phát sinh trong cùng giây?

### Bài 6 — Kiểu bind gây implicit conversion

Một bảng có cột `CUSTOMER_CODE VARCHAR2(12)` và chứa `'000123'`, `'A123'`. Hai đoạn Java khác nhau:

~~~java
ps.setLong(1, 123L);
// So sánh với WHERE customer_code = ?

ps.setString(1, "000123");
// Cũng WHERE customer_code = ?
~~~

**Câu hỏi:** Lệnh nào bảo toàn ý nghĩa mã định danh? Lệnh nào có thể khiến Oracle chuyển cột sang số và gặp lỗi với `'A123'`?

**Đáp án định hướng:** `setString` với mã nguyên bản là phù hợp; `setLong` làm mất số 0 đầu và có thể dẫn tới implicit conversion sai ngữ nghĩa.

## 12. Sơ đồ quyết định khi cần chuyển kiểu

~~~text
Giá trị đến từ Java / JSON / CSV / SQL?
                  |
                  v
Xác định NGỮ NGHĨA thật
  - Mã định danh hay số để tính?
  - Ngày hay thời điểm có giờ?
  - Có timezone/offset không?
  - Đơn vị tiền tệ và độ chính xác?
                  |
                  v
Xác định kiểu đích và quy ước format
  - NUMBER(p,s), VARCHAR2(n CHAR/BYTE)
  - DATE, TIMESTAMP(p), TIMESTAMP WITH TIME ZONE
                  |
                  v
Kiểm tra dữ liệu nguồn
  - Parse được theo format và NLS chỉ định?
  - Nằm trong phạm vi hợp lệ?
  - Chuyển đổi có làm tròn/mất thời gian/mất ký tự?
                  |
           +------+------+
           |             |
       Không đạt         Đạt
           |             |
           v             v
   Giữ raw + lý do   Explicit conversion / typed bind
   báo lỗi hoặc       và lưu vào cột đúng kiểu
   đưa vào reject          |
                        v
                  Kiểm tra constraint,
                  dữ liệu sau khi lưu
~~~

**Nguyên tắc thực hành:** Ưu tiên **bind đúng kiểu** và **chuyển kiểu tường minh với format rõ ràng** tại ranh giới dữ liệu; coi implicit conversion là điểm cần kiểm tra khi SQL gặp lỗi hoặc chạy chậm. Với những trường hợp mất độ chính xác, không chỉ hỏi “có chuyển đổi được không?” mà còn phải hỏi **“giá trị sau chuyển đổi còn giữ đúng ý nghĩa và độ chính xác ban đầu không?”**. Đây là sự khác biệt giữa một câu SQL chạy thành công và một hệ thống lưu dữ liệu đáng tin cậy.
