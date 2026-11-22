# Kiểm thử NUMBER, làm tròn, ngày giờ và chuyển múi giờ trong Oracle Database

Các lỗi liên quan số và thời gian thường không xuất hiện trong happy path. Chúng lộ ra ở giá trị sát ranh giới, số có nhiều chữ số thập phân, tháng cuối năm, ngày nhuận, thời điểm đổi giờ mùa hè hoặc khi ứng dụng chạy ở timezone khác database server.

Một bộ kiểm thử Oracle cần xác nhận ít nhất bốn nhóm hành vi:

- **NUMBER:** precision, scale, phép tính, chuyển kiểu và giá trị vượt giới hạn.
- **Làm tròn:** ROUND, TRUNC, FLOOR, CEIL, MOD và cách xử lý số âm/giá trị đúng nửa.
- **Ngày giờ:** DATE, TIMESTAMP, phép cộng/trừ, parse/format và ranh giới ngày/tháng.
- **Múi giờ:** database timezone, session timezone, host timezone, timestamp có/không có timezone, DST overlap/gap và chuyển đổi giữa các vùng.

Kết quả có thể khác nếu ứng dụng dựa vào implicit conversion, NLS session settings hoặc kiểu dữ liệu không phù hợp. Vì vậy, test nên dùng dữ liệu biên có chủ đích, format mask rõ ràng, timezone region cụ thể và kiểm tra lại giá trị lưu trong database.

Bài học lấy Oracle Database 19c làm mốc, dùng SQL và PL/SQL để minh họa. Các ví dụ có thể chạy trong schema test riêng. Tránh chạy DDL hoặc thay đổi NLS/timezone session trên connection dùng chung của ứng dụng đang phục vụ request.

## 1. Nguyên tắc thiết kế test cho số và thời gian

### 1.1. Kiểm thử theo biên

Không chỉ thử số nguyên nhỏ hoặc ngày giữa tháng. Mỗi nhóm dữ liệu nên có:
- Giá trị nhỏ nhất và lớn nhất hợp lệ.
- Giá trị ngay dưới, đúng tại và ngay trên biên.
- Số âm, số 0 và số dương.
- NULL.
- Giá trị có nhiều chữ số thập phân.
- Giá trị đúng nửa đơn vị làm tròn.
- Ngày cuối tháng, đầu tháng, năm nhuận và chuyển năm.
- Thời điểm trước/sau nửa đêm.
- Timestamp có fractional seconds.
- Thời điểm thuộc DST gap/overlap nếu vùng có DST.

### 1.2. Phân biệt giá trị đầu vào, giá trị lưu và giá trị hiển thị

Ba lớp này không giống nhau:

1. **Đầu vào:** chuỗi hoặc giá trị Java/JDBC gửi tới database.
2. **Giá trị lưu:** kết quả sau khi Oracle áp kiểu dữ liệu, precision/scale và conversion.
3. **Giá trị hiển thị:** kết quả TO_CHAR, SQL client hoặc định dạng ứng dụng.

Ví dụ NUMBER(8,2) có thể làm tròn giá trị đầu vào còn hai chữ số thập phân. TO_CHAR có thể hiển thị hai chữ số dù giá trị NUMBER bên trong không bị giới hạn scale như vậy. Một timestamp có timezone có thể biểu diễn cùng một instant nhưng hiển thị giờ khác nhau ở session timezone khác.

Test đúng cần xác định đang kiểm tra lớp nào.

### 1.3. Tránh phụ thuộc NLS mặc định

Không dựa vào:
- NLS_NUMERIC_CHARACTERS mặc định của máy.
- NLS_DATE_FORMAT mặc định của session.
- NLS_TIMESTAMP_FORMAT.
- NLS_DATE_LANGUAGE.
- SESSIONTIMEZONE của connection pool.

Hãy dùng TO_NUMBER/TO_DATE/TO_TIMESTAMP với format mask và NLS parameter rõ ràng. Với ứng dụng, bind giá trị có kiểu qua JDBC thường an toàn hơn gửi chuỗi rồi để Oracle tự parse.

### 1.4. Mỗi test cần có expected result

Ghi lại:
- Input.
- Kiểu dữ liệu input.
- Kiểu cột.
- NLS/timezone session.
- SQL hoặc Java code thực thi.
- Expected result.
- Actual result.
- Sai số được chấp nhận nếu có.
- Database version và COMPATIBLE.

Không ghi “kết quả gần đúng” nếu chưa định nghĩa tolerance.

## 2. NUMBER: precision, scale và phạm vi lưu trữ

### 2.1. NUMBER không khai báo precision/scale

Oracle NUMBER có thể lưu số với tối đa 38 chữ số có nghĩa. Nếu khai báo NUMBER không kèm precision/scale, cột không bị giới hạn theo một p,s cố định, nhưng vẫn chịu giới hạn của kiểu NUMBER.

~~~sql
CREATE TABLE number_lab (
    id NUMBER PRIMARY KEY,
    value_unconstrained NUMBER
);
~~~

Dùng kiểu không khai báo p,s khi nghiệp vụ cần phạm vi linh hoạt, nhưng vẫn phải kiểm tra dữ liệu hợp lệ ở tầng nghiệp vụ.

### 2.2. NUMBER(p,s)

Cú pháp:

~~~sql
NUMBER(precision, scale)
~~~

- precision (p): số chữ số có nghĩa tối đa.
- scale (s): số chữ số ở bên phải dấu thập phân.
- p trong khoảng 1 đến 38.
- s có thể từ -84 đến 127.
- Nếu chỉ khai báo NUMBER(p), scale mặc định là 0.

Ví dụ:

~~~sql
CREATE TABLE amount_lab (
    amount_2dp NUMBER(10,2),
    whole_units NUMBER(8,0),
    round_hundreds NUMBER(8,-2),
    small_fraction NUMBER(4,5)
);
~~~

NUMBER(10,2) có tối đa 10 chữ số có nghĩa, trong đó 2 chữ số nằm sau dấu thập phân. NUMBER(8,0) lưu số nguyên có tối đa 8 chữ số. NUMBER(8,-2) làm tròn đến hàng trăm khi lưu. NUMBER(4,5) dành cho giá trị nhỏ hơn 1 với scale lớn.

### 2.3. Giá trị được làm tròn khi gán vào cột

Khi insert/update vào NUMBER(p,s), Oracle điều chỉnh giá trị theo scale của cột. Ví dụ:

~~~sql
CREATE TABLE amount_round_test (
    id NUMBER PRIMARY KEY,
    amount NUMBER(6,2)
);

INSERT INTO amount_round_test VALUES (1, 12.345);
INSERT INTO amount_round_test VALUES (2, 12.344);
INSERT INTO amount_round_test VALUES (3, -12.345);

SELECT id, amount
FROM   amount_round_test
ORDER  BY id;
~~~

Với scale 2, giá trị được lưu theo hai chữ số thập phân sau khi làm tròn theo quy tắc NUMBER. Hãy quan sát cả số dương và số âm, không giả định phép lưu luôn cắt bỏ chữ số dư.

### 2.4. ORA-01438 khi vượt precision

Nếu giá trị sau khi áp scale vẫn vượt precision của cột, Oracle báo lỗi:

~~~sql
CREATE TABLE precision_test (
    amount NUMBER(5,2)
);

INSERT INTO precision_test VALUES (999.99);
-- Giá trị này nằm trong phạm vi.

INSERT INTO precision_test VALUES (1000.00);
-- Có thể phát sinh ORA-01438 vì vượt precision.
~~~

Với NUMBER(5,2), phần nguyên có tối đa 3 chữ số. Không chỉ kiểm tra giá trị đầu vào lớn nhất; cần kiểm tra kết quả sau làm tròn. Ví dụ một giá trị sát 999.995 có thể được làm tròn thành 1000.00 rồi vượt precision.

### 2.5. Scale âm

Scale âm làm tròn bên trái dấu thập phân:

~~~sql
SELECT
    CAST(12345 AS NUMBER(7,-2)) AS nearest_hundred,
    CAST(12345 AS NUMBER(7,-3)) AS nearest_thousand
FROM dual;
~~~

NUMBER(7,-2) làm tròn tới hàng trăm; NUMBER(7,-3) làm tròn tới hàng nghìn. Dùng scale âm chỉ khi nghiệp vụ thực sự yêu cầu lưu giá trị ở mức độ chính xác đó.

### 2.6. Kiểm thử bằng INSERT và đọc lại

Không chỉ kiểm tra biểu thức SELECT. Cần kiểm tra dữ liệu sau khi đi qua column definition:

~~~sql
INSERT INTO amount_round_test(id, amount)
VALUES (10, 123.456);

SELECT amount,
       DUMP(amount) AS internal_type
FROM   amount_round_test
WHERE  id = 10;
~~~

DUMP giúp quan sát datatype/internal representation ở mức chẩn đoán. Với NUMBER, dùng TO_CHAR có format rõ ràng để xác nhận giá trị nghiệp vụ; không so sánh chuỗi mặc định của SQL client.

## 3. NUMBER arithmetic và kiểu số gần đúng

### 3.1. NUMBER dùng biểu diễn số thập phân

Oracle NUMBER là kiểu số thập phân với độ chính xác cao, phù hợp cho tiền tệ và phép tính cần quy tắc decimal. Tuy nhiên, kết quả phép tính vẫn bị giới hạn bởi precision/scale tối đa và quy tắc chuyển kiểu.

Không nên lưu tiền tệ bằng BINARY_FLOAT hoặc BINARY_DOUBLE nếu nghiệp vụ yêu cầu decimal exact, trừ khi đã định nghĩa rõ sai số cho phép.

### 3.2. BINARY_FLOAT và BINARY_DOUBLE

Đây là các kiểu dấu phẩy động nhị phân, thường phù hợp với tính toán khoa học hoặc workload cần biểu diễn gần đúng theo IEEE 754.

Một số số thập phân như 0.1 không có biểu diễn nhị phân hữu hạn chính xác. Vì vậy:

~~~sql
SELECT
    0.1 + 0.2 AS decimal_number_result,
    CAST(0.1 AS BINARY_DOUBLE)
      + CAST(0.2 AS BINARY_DOUBLE) AS binary_double_result
FROM dual;
~~~

Giá trị hiển thị có thể được làm tròn bởi client. Nếu cần so sánh kiểu số gần đúng, dùng tolerance thay vì yêu cầu bằng tuyệt đối.

### 3.3. So sánh số gần đúng

Mẫu kiểm tra:

~~~sql
WHERE ABS(actual_value - expected_value) < 0.000001
~~~

Tolerance phải được chọn theo đơn vị và quy mô nghiệp vụ. Không dùng một epsilon chung cho mọi đại lượng: sai số 0.000001 có thể rất nhỏ với số đo lớn nhưng lại quá lớn với tỷ lệ hoặc đơn vị nhỏ.

### 3.4. Phép chia và NULLIF

Phép chia cho 0 gây lỗi. Nếu mẫu số có thể bằng 0, xử lý rõ:

~~~sql
SELECT numerator / NULLIF(denominator, 0) AS ratio
FROM   measurement_lab;
~~~

NULLIF trả NULL nếu hai biểu thức bằng nhau. Kết quả ratio sẽ NULL thay vì lỗi chia cho 0. Xác định nghiệp vụ muốn NULL, 0 hay một trạng thái lỗi riêng; đừng tự thay NULL bằng 0 nếu điều đó làm sai ý nghĩa.

### 3.5. Kiểm thử NULL trong phép tính

Phép toán số học với NULL thường cho kết quả NULL. Kiểm tra:

~~~sql
SELECT
    10 + CAST(NULL AS NUMBER) AS add_null,
    10 * CAST(NULL AS NUMBER) AS multiply_null,
    NVL(CAST(NULL AS NUMBER), 0) AS defaulted_value
FROM dual;
~~~

NVL/COALESCE có thể thay NULL bằng giá trị mặc định. Chỉ dùng khi quy tắc nghiệp vụ cho phép; NULL thường biểu thị “không biết/không có dữ liệu”, khác với số 0.

## 4. ROUND, TRUNC, FLOOR và CEIL

### 4.1. ROUND

ROUND làm tròn tới số chữ số được chỉ định:

~~~sql
SELECT
    ROUND(12.345, 2) AS round_2,
    ROUND(12.345, 1) AS round_1,
    ROUND(12.345, 0) AS round_integer,
    ROUND(12345, -2) AS round_hundred
FROM dual;
~~~

Nếu bỏ tham số thứ hai, ROUND mặc định làm tròn tới số nguyên. Với NUMBER, giá trị đúng nửa được làm tròn ra xa 0 theo quy tắc Oracle; test riêng các giá trị dương/âm sát điểm nửa.

~~~sql
SELECT
    ROUND(1.5) AS positive_half,
    ROUND(-1.5) AS negative_half,
    ROUND(2.49) AS below_half,
    ROUND(2.50) AS exact_half,
    ROUND(-2.50) AS negative_exact_half
FROM dual;
~~~

Khi nghiệp vụ tiền tệ có quy định rounding mode riêng, không mặc định rằng ROUND trong database trùng mọi quy tắc làm tròn của Java BigDecimal hoặc hệ thống kế toán.

### 4.2. TRUNC

TRUNC bỏ phần thập phân sau vị trí chỉ định, không làm tròn:

~~~sql
SELECT
    TRUNC(12.349, 2) AS trunc_2,
    TRUNC(12.999, 0) AS trunc_integer,
    TRUNC(12345, -2) AS trunc_hundred,
    TRUNC(-12.99, 0) AS trunc_negative
FROM dual;
~~~

Với số âm, TRUNC tiến về 0. Vì vậy TRUNC(-1.9) là -1, trong khi FLOOR(-1.9) là -2.

### 4.3. FLOOR và CEIL

- FLOOR trả số nguyên lớn nhất không lớn hơn giá trị.
- CEIL trả số nguyên nhỏ nhất không nhỏ hơn giá trị.

~~~sql
SELECT
    FLOOR(1.9) AS floor_positive,
    CEIL(1.1) AS ceil_positive,
    FLOOR(-1.1) AS floor_negative,
    CEIL(-1.1) AS ceil_negative
FROM dual;
~~~

Các hàm này hữu ích khi tính bucket, số trang, số batch hoặc giới hạn nguyên. Đặc biệt test số âm vì kết quả FLOOR và TRUNC khác nhau.

### 4.4. So sánh trên cùng bộ dữ liệu

~~~sql
WITH samples(value) AS (
    SELECT  2.50 FROM dual UNION ALL
    SELECT  2.49 FROM dual UNION ALL
    SELECT -2.50 FROM dual UNION ALL
    SELECT -2.49 FROM dual UNION ALL
    SELECT  0.00 FROM dual
)
SELECT value,
       ROUND(value, 0) AS rounded_value,
       TRUNC(value, 0) AS truncated_value,
       FLOOR(value) AS floor_value,
       CEIL(value) AS ceil_value
FROM   samples
ORDER  BY value DESC;
~~~

Bảng kết quả là bộ regression đơn giản để bảo vệ logic tính phí, phân trang, số lượng kiện hàng hoặc phân bổ.

### 4.5. Làm tròn tiền tệ

Giả sử đơn giá và số lượng:

~~~sql
SELECT unit_price,
       quantity,
       unit_price * quantity AS raw_total,
       ROUND(unit_price * quantity, 2) AS rounded_total
FROM (
    SELECT 19.995 AS unit_price, 3 AS quantity
    FROM dual
);
~~~

Nghiệp vụ có thể yêu cầu:
- Làm tròn từng dòng rồi cộng.
- Cộng toàn bộ rồi làm tròn một lần.
- Làm tròn theo currency scale.
- Dùng quy tắc riêng cho thuế/chiết khấu.

Các cách này có thể tạo tổng khác nhau. Hãy đưa quy tắc vào test case và áp dụng nhất quán ở database/service.

### 4.6. MOD

MOD trả phần dư theo quy tắc Oracle:

~~~sql
SELECT
    MOD(11, 4) AS positive_mod,
    MOD(-11, 4) AS negative_dividend_mod,
    MOD(11, -4) AS negative_divisor_mod,
    MOD(-11, -4) AS both_negative_mod
FROM dual;
~~~

Đừng giả định MOD luôn trả giá trị không âm. Test số âm nếu dùng MOD để chia nhóm, phân trang hoặc tính chu kỳ.

## 5. Chuyển đổi chuỗi số và NLS_NUMERIC_CHARACTERS

### 5.1. TO_NUMBER với format mask

Không nên dựa vào implicit conversion:

~~~sql
SELECT TO_NUMBER('1234.56', '9999D99') AS amount
FROM dual;
~~~

D là ký hiệu decimal separator theo NLS_NUMERIC_CHARACTERS. G là group separator. Ý nghĩa cụ thể phụ thuộc NLS parameter của session hoặc tham số NLS truyền vào hàm.

### 5.2. Kiểm thử hai quy ước dấu thập phân

Có thể thay NLS session trong một session test:

~~~sql
ALTER SESSION SET NLS_NUMERIC_CHARACTERS = '.,';

SELECT TO_NUMBER('1,234.56', '9G999D99') AS amount
FROM dual;

ALTER SESSION SET NLS_NUMERIC_CHARACTERS = ',.';

SELECT TO_NUMBER('1.234,56', '9G999D99') AS amount
FROM dual;
~~~

Trong ví dụ đầu, dấu chấm là decimal separator và dấu phẩy là group separator. Trong ví dụ sau, dấu phẩy là decimal separator và dấu chấm là group separator.

ALTER SESSION chỉ ảnh hưởng session hiện tại. Khi dùng connection pool, session có thể được tái sử dụng; không để thay đổi NLS tồn tại ngoài phạm vi test/request.

### 5.3. Truyền NLS parameter ngay trong TO_NUMBER

Có thể làm cho biểu thức độc lập với session:

~~~sql
SELECT TO_NUMBER(
           '1.234,56',
           '9G999D99',
           'NLS_NUMERIC_CHARACTERS = '',.'''
       ) AS amount
FROM dual;
~~~

Đây là một SQL string có quote escape. Khi viết trong Java, cần xử lý quote ở tầng Java string hoặc dùng bind/SQL template rõ ràng.

### 5.4. Kiểm thử định dạng không hợp lệ

~~~sql
SELECT TO_NUMBER('12,34,56', '999G999D99')
FROM dual;
~~~

Tùy format mask/NLS, chuỗi không khớp có thể phát sinh lỗi chuyển đổi như ORA-01722. Test dữ liệu đầu vào sai và xác định ứng dụng cần reject, ghi lỗi validation hay chuyển thành trạng thái nghiệp vụ.

### 5.5. TO_CHAR và kiểm tra output

~~~sql
SELECT TO_CHAR(
           1234567.8,
           'FM9G999G999D00',
           'NLS_NUMERIC_CHARACTERS = '',.'''
       ) AS formatted_amount
FROM dual;
~~~

TO_CHAR phục vụ hiển thị. Không dùng chuỗi đã format làm giá trị để tính toán tiếp nếu có thể giữ NUMBER. Cần test locale, dấu phân cách và ký hiệu tiền tệ ở tầng trình bày.

## 6. Kiểm thử DATE, TIMESTAMP và các kiểu thời gian

### 6.1. DATE

Oracle DATE lưu:
- Năm.
- Tháng.
- Ngày.
- Giờ.
- Phút.
- Giây.

DATE không lưu fractional seconds và không lưu timezone. Vì vậy, cột DATE không đủ để biểu diễn một instant cùng timezone/offset gốc.

### 6.2. TIMESTAMP

TIMESTAMP bổ sung fractional seconds, với độ chính xác mặc định 6 chữ số thập phân và có thể chỉ định precision từ 0 đến 9:

~~~sql
CREATE TABLE timestamp_lab (
    id NUMBER PRIMARY KEY,
    created_at TIMESTAMP(6),
    high_precision_at TIMESTAMP(9)
);
~~~

Dùng TIMESTAMP khi cần độ chính xác dưới giây nhưng không cần giữ timezone trong chính giá trị cột.

### 6.3. TIMESTAMP WITH TIME ZONE

TIMESTAMP WITH TIME ZONE lưu timestamp cùng timezone displacement hoặc timezone region information theo cách Oracle hỗ trợ. Nó phù hợp khi cần biểu diễn thời điểm gắn với timezone/offset.

~~~sql
CREATE TABLE event_tz_lab (
    id NUMBER PRIMARY KEY,
    event_time TIMESTAMP(6) WITH TIME ZONE
);
~~~

Hai giá trị có offset khác nhau vẫn có thể biểu diễn cùng một instant. Khi so sánh hoặc hiển thị, cần phân biệt instant và local wall-clock time.

### 6.4. TIMESTAMP WITH LOCAL TIME ZONE

TIMESTAMP WITH LOCAL TIME ZONE được chuẩn hóa theo DBTIMEZONE khi lưu; timezone gốc không được lưu như một phần của giá trị. Khi đọc, Oracle hiển thị giá trị theo SESSIONTIMEZONE.

~~~sql
CREATE TABLE event_ltz_lab (
    id NUMBER PRIMARY KEY,
    event_time TIMESTAMP(6) WITH LOCAL TIME ZONE
);
~~~

Kiểu này hữu ích khi ứng dụng muốn hiển thị instant theo timezone session hiện tại. Nếu cần giữ timezone region/offset gốc của người tạo sự kiện, lưu thêm thông tin timezone riêng hoặc dùng TIMESTAMP WITH TIME ZONE.

### 6.5. So sánh bốn loại thường gặp

| Kiểu | Giữ giờ/phút/giây | Fractional seconds | Giữ timezone trong giá trị |
| --- | --- | --- | --- |
| DATE | Có | Không | Không |
| TIMESTAMP | Có | Có | Không |
| TIMESTAMP WITH TIME ZONE | Có | Có | Có |
| TIMESTAMP WITH LOCAL TIME ZONE | Có | Có | Không giữ timezone gốc; normalize theo DBTIMEZONE và hiển thị theo session |

Chọn kiểu dựa trên ý nghĩa dữ liệu:
- Ngày sinh, ngày hiệu lực nghiệp vụ không gắn instant: DATE hoặc TIMESTAMP tùy precision.
- Thời điểm sự kiện cần đối chiếu toàn cầu: TIMESTAMP WITH TIME ZONE.
- Thời điểm muốn hiển thị theo session/user timezone: TIMESTAMP WITH LOCAL TIME ZONE, nếu không cần lưu timezone gốc.
- Chỉ cần thời gian dưới giây nhưng không cần timezone: TIMESTAMP.

## 7. Literal và parse ngày giờ an toàn

### 7.1. ANSI DATE literal

~~~sql
SELECT DATE '2026-11-14' AS test_date
FROM dual;
~~~

ANSI DATE literal có format cố định YYYY-MM-DD và không phụ thuộc NLS_DATE_FORMAT.

### 7.2. ANSI TIMESTAMP literal

~~~sql
SELECT TIMESTAMP '2026-11-14 21:26:30.123456'
FROM dual;
~~~

Timestamp literal có thể có fractional seconds. Dùng format literal chuẩn thay vì chuỗi ngày phụ thuộc locale.

### 7.3. TO_DATE với format mask

~~~sql
SELECT TO_DATE('14-11-2026', 'DD-MM-YYYY') AS parsed_date
FROM dual;
~~~

Không viết:

~~~sql
SELECT TO_DATE('14-11-2026')
FROM dual;
~~~

nếu không có format mask rõ ràng, vì Oracle phải dựa vào NLS_DATE_FORMAT của session.

### 7.4. TO_TIMESTAMP

~~~sql
SELECT TO_TIMESTAMP(
           '2026-11-14 21:26:30.123456',
           'YYYY-MM-DD HH24:MI:SS.FF6'
       ) AS parsed_timestamp
FROM dual;
~~~

FF6 chỉ rõ fractional seconds có sáu chữ số. Nếu input có precision khác, dùng format mask tương ứng hoặc FF theo yêu cầu.

### 7.5. TO_TIMESTAMP_TZ

~~~sql
SELECT TO_TIMESTAMP_TZ(
           '2026-11-14 21:26:30.123456 +07:00',
           'YYYY-MM-DD HH24:MI:SS.FF6 TZH:TZM'
       ) AS parsed_timestamp_tz
FROM dual;
~~~

Nếu input chứa region name, dùng format element TZR và có thể TZD khi cần disambiguate daylight/standard time abbreviation theo dữ liệu.

### 7.6. FX và kiểm tra chuỗi chính xác

FX yêu cầu format khớp chặt chẽ hơn:

~~~sql
SELECT TO_DATE(
           '2026-11-14',
           'FXYYYY-MM-DD'
       )
FROM dual;
~~~

Dùng FX trong test input khi muốn từ chối chuỗi sai format thay vì chấp nhận một số biến thể linh hoạt. Kiểm tra các case có khoảng trắng, dấu phân cách hoặc số 0 bị thiếu.

### 7.7. Ngôn ngữ tên tháng/ngày

Nếu parse chuỗi có tên tháng như NOV hoặc NOVEMBER, kết quả có thể phụ thuộc NLS_DATE_LANGUAGE. Có thể chỉ định NLS parameter:

~~~sql
SELECT TO_DATE(
           '14-NOV-2026',
           'DD-MON-YYYY',
           'NLS_DATE_LANGUAGE=American'
       )
FROM dual;
~~~

Với dữ liệu trao đổi giữa hệ thống, ưu tiên format số không phụ thuộc tên tháng/ngôn ngữ.

## 8. Phép toán ngày giờ và ranh giới lịch

### 8.1. DATE cộng/trừ số ngày

Với DATE, cộng một NUMBER nghĩa là cộng số ngày; phần thập phân biểu diễn phần của ngày:

~~~sql
SELECT
    DATE '2026-11-14' + 1 AS next_day,
    DATE '2026-11-14' + 0.5 AS noon,
    DATE '2026-11-14' - 1 AS previous_day
FROM dual;
~~~

0.5 ngày bằng 12 giờ. Đây là phép tính theo DATE arithmetic, không phải timezone-aware duration.

### 8.2. DATE trừ DATE

~~~sql
SELECT
    DATE '2026-11-15' - DATE '2026-11-14' AS day_difference
FROM dual;
~~~

Kết quả là NUMBER biểu diễn số ngày, có thể có phần thập phân. Nếu cần số giây:

~~~sql
SELECT
    (end_date - start_date) * 24 * 60 * 60 AS elapsed_seconds
FROM   event_interval_test;
~~~

### 8.3. TIMESTAMP trừ TIMESTAMP

Trừ hai TIMESTAMP tạo INTERVAL DAY TO SECOND:

~~~sql
SELECT
    TIMESTAMP '2026-11-14 10:00:00.500000'
    - TIMESTAMP '2026-11-14 09:59:58.000000' AS elapsed
FROM dual;
~~~

Dùng EXTRACT để lấy thành phần ngày/giờ/phút/giây từ interval. Nếu cần tổng số giây, cộng các thành phần theo đơn vị:

~~~sql
WITH diff AS (
    SELECT
        TIMESTAMP '2026-11-14 10:00:00.500000'
        - TIMESTAMP '2026-11-14 09:59:58.000000' AS value
    FROM dual
)
SELECT
    EXTRACT(DAY FROM value) * 86400
  + EXTRACT(HOUR FROM value) * 3600
  + EXTRACT(MINUTE FROM value) * 60
  + EXTRACT(SECOND FROM value) AS elapsed_seconds
FROM diff;
~~~

### 8.4. TIMESTAMP cộng INTERVAL

~~~sql
SELECT
    TIMESTAMP '2026-11-14 10:00:00'
      + INTERVAL '90' MINUTE AS plus_90_minutes,
    TIMESTAMP '2026-11-14 10:00:00'
      + INTERVAL '2' DAY AS plus_2_days
FROM dual;
~~~

Interval biểu diễn khoảng thời gian tường minh, tránh dùng số thập phân không rõ đơn vị.

### 8.5. NUMTODSINTERVAL và NUMTOYMINTERVAL

~~~sql
SELECT
    TIMESTAMP '2026-11-14 10:00:00'
      + NUMTODSINTERVAL(90, 'MINUTE') AS plus_minutes,
    DATE '2026-11-14'
      + NUMTOYMINTERVAL(2, 'MONTH') AS plus_months
FROM dual;
~~~

NUMTODSINTERVAL chuyển NUMBER thành INTERVAL DAY TO SECOND; NUMTOYMINTERVAL chuyển thành INTERVAL YEAR TO MONTH. Chọn đúng loại interval cho phép toán.

### 8.6. ADD_MONTHS và ngày cuối tháng

ADD_MONTHS có quy tắc đặc biệt:
- Nếu ngày nguồn là ngày cuối tháng, kết quả là ngày cuối tháng đích.
- Nếu tháng đích ít ngày hơn ngày nguồn, kết quả là ngày cuối tháng đích.
- Hàm ADD_MONTHS trả về DATE.

~~~sql
SELECT
    ADD_MONTHS(DATE '2024-01-31', 1) AS jan_31_plus_one_month,
    ADD_MONTHS(DATE '2024-01-30', 1) AS jan_30_plus_one_month,
    ADD_MONTHS(DATE '2024-02-29', 12) AS leap_day_plus_year
FROM dual;
~~~

Không giả định ADD_MONTHS(date,1) tương đương cộng 30 ngày. Test riêng ngày 28/29/30/31 và năm nhuận.

### 8.7. MONTHS_BETWEEN

MONTHS_BETWEEN trả NUMBER. Nếu hai ngày cùng ngày trong tháng hoặc cùng là ngày cuối tháng, kết quả nguyên. Trường hợp khác, phần lẻ được tính dựa trên quy ước tháng 31 ngày và thời gian trong ngày.

~~~sql
SELECT
    MONTHS_BETWEEN(
        DATE '2024-03-31',
        DATE '2024-02-29'
    ) AS month_difference,
    MONTHS_BETWEEN(
        DATE '2024-03-15',
        DATE '2024-02-14'
    ) AS fractional_months
FROM dual;
~~~

Đừng dùng MONTHS_BETWEEN để tính số tháng billing nếu nghiệp vụ có quy tắc riêng như ngày kỷ niệm, prorating hoặc số ngày thực tế.

### 8.8. LAST_DAY, NEXT_DAY và TRUNC

~~~sql
SELECT
    LAST_DAY(DATE '2026-02-10') AS month_end,
    NEXT_DAY(DATE '2026-11-14', 'MONDAY') AS next_monday,
    TRUNC(DATE '2026-11-14 21:26:30', 'DD') AS day_start,
    TRUNC(DATE '2026-11-14 21:26:30', 'MM') AS month_start
FROM dual;
~~~

NEXT_DAY sử dụng tên ngày theo NLS_DATE_LANGUAGE. TRUNC(date) trả DATE, kể cả khi input là một datetime datatype khác trong các dạng được hỗ trợ; không dựa vào nó nếu cần giữ timezone/fractional seconds.

### 8.9. Ranh giới ngày trong truy vấn

Tránh lọc ngày bằng cách format cột thành chuỗi hoặc so sánh bằng đúng midnight:

~~~sql
WHERE created_at >= :day_start
AND   created_at <  :next_day_start
~~~

Cách khoảng nửa mở [start, next_start) thường an toàn hơn với cột chứa giờ và fractional seconds, đồng thời có thể tận dụng index tốt hơn so với TRUNC(column) nếu không có function-based index.

## 9. Hàm thời gian hiện tại và timezone context

### 9.1. Phân biệt các hàm hiện tại

| Hàm | Kiểu trả về | Timezone tham chiếu |
| --- | --- | --- |
| SYSDATE | DATE | Thời gian hệ điều hành của database server |
| SYSTIMESTAMP | TIMESTAMP WITH TIME ZONE | Thời gian hệ điều hành của database server, có fractional seconds/offset |
| CURRENT_DATE | DATE | Session timezone |
| CURRENT_TIMESTAMP | TIMESTAMP WITH TIME ZONE | Session timezone |
| LOCALTIMESTAMP | TIMESTAMP | Local timestamp theo session timezone, không mang timezone trong kết quả |
| DBTIMEZONE | VARCHAR2 | Database timezone |
| SESSIONTIMEZONE | VARCHAR2 | Session timezone |

Không thay SYSDATE bằng CURRENT_DATE hoặc ngược lại mà không kiểm tra ý nghĩa. Khi application server và database server ở timezone khác, kết quả có thể lệch ngày/giờ.

### 9.2. Kiểm tra context hiện tại

~~~sql
SELECT
    SYSDATE AS sysdate_value,
    SYSTIMESTAMP AS systimestamp_value,
    CURRENT_DATE AS current_date_value,
    CURRENT_TIMESTAMP AS current_timestamp_value,
    LOCALTIMESTAMP AS localtimestamp_value,
    DBTIMEZONE AS db_timezone,
    SESSIONTIMEZONE AS session_timezone
FROM dual;
~~~

Dùng truy vấn này trong session ứng dụng để xác nhận context thực tế. SQL Developer session của DBA có thể dùng timezone khác session của connection pool.

### 9.3. Đổi session timezone

~~~sql
ALTER SESSION SET TIME_ZONE = 'Asia/Ho_Chi_Minh';
~~~

Hoặc:

~~~sql
ALTER SESSION SET TIME_ZONE = '+07:00';
~~~

Timezone region biểu diễn quy tắc địa phương; offset cố định chỉ biểu diễn độ lệch tại thời điểm đó. Với vùng có DST, dùng region name thay vì offset nếu cần quy tắc mùa hè/mùa đông.

### 9.4. Connection pool và session timezone

ALTER SESSION SET TIME_ZONE thay đổi session state. Connection pool có thể trả cùng physical connection cho request tiếp theo. Nếu mỗi request có timezone riêng:
- Thiết lập timezone khi mượn connection.
- Reset khi trả connection.
- Đảm bảo mọi code path chạy cleanup kể cả exception.
- Kiểm thử song song nhiều timezone.
- Tránh để session state của tenant/user trước rò sang request sau.

Nếu ứng dụng có timezone người dùng, thường an toàn hơn khi chuyển đổi ở tầng Java hoặc bind một giá trị timestamp có timezone phù hợp, tùy mô hình dữ liệu.

## 10. Chuyển đổi timezone

### 10.1. FROM_TZ

FROM_TZ gắn timezone vào một TIMESTAMP không timezone:

~~~sql
SELECT FROM_TZ(
           TIMESTAMP '2026-11-14 09:00:00',
           'Asia/Ho_Chi_Minh'
       ) AS event_with_timezone
FROM dual;
~~~

Giá trị đầu vào là local wall-clock time. Hàm thêm region/offset để xác định instant. Nếu vùng có DST và thời gian rơi vào overlap/gap, cần quy tắc xử lý rõ.

### 10.2. AT TIME ZONE

Chuyển một timestamp có timezone sang vùng khác:

~~~sql
SELECT
    FROM_TZ(
        TIMESTAMP '2026-11-14 09:00:00',
        'Asia/Ho_Chi_Minh'
    ) AT TIME ZONE 'UTC' AS utc_time
FROM dual;
~~~

Đây là cùng một instant được biểu diễn trong timezone đích. Giờ hiển thị thay đổi nhưng thời điểm tuyệt đối không đổi.

### 10.3. SYS_EXTRACT_UTC

~~~sql
SELECT SYS_EXTRACT_UTC(
           FROM_TZ(
               TIMESTAMP '2026-11-14 09:00:00',
               'Asia/Ho_Chi_Minh'
           )
       ) AS utc_timestamp
FROM dual;
~~~

SYS_EXTRACT_UTC trả TIMESTAMP biểu diễn UTC không kèm timezone. Khi lưu kết quả này vào cột TIMESTAMP, quy ước ứng dụng phải ghi rõ giá trị đó là UTC.

### 10.4. AT LOCAL

AT LOCAL chuyển timestamp có timezone sang session timezone:

~~~sql
SELECT
    FROM_TZ(
        TIMESTAMP '2026-11-14 09:00:00',
        'Asia/Ho_Chi_Minh'
    ) AT LOCAL AS session_local_time
FROM dual;
~~~

Cùng câu SQL có thể hiển thị khác nhau ở session timezone khác. Đây là hành vi cần test khi ứng dụng pool connection.

### 10.5. Kiểm tra vùng timezone hợp lệ

~~~sql
SELECT tzname,
       tzabbrev
FROM   v$timezone_names
WHERE  tzname IN (
           'UTC',
           'Asia/Ho_Chi_Minh',
           'America/New_York',
           'Europe/London'
       )
ORDER  BY tzname, tzabbrev;
~~~

Timezone region và abbreviation có thể có nhiều dòng. Dùng region name để áp dụng quy tắc DST. Abbreviation như EST/PST có thể mơ hồ và không phải lúc nào cũng biểu diễn một region duy nhất.

### 10.6. Offset cố định và region name

Hai kiểu khai báo:

~~~sql
FROM_TZ(TIMESTAMP '2026-11-14 09:00:00', '+07:00')
~~~

~~~sql
FROM_TZ(TIMESTAMP '2026-11-14 09:00:00', 'Asia/Ho_Chi_Minh')
~~~

Với Việt Nam hiện không có DST và offset +07:00 phù hợp cho thời điểm hiện tại, nhưng region name thể hiện ý nghĩa địa lý rõ hơn. Với New York/London và vùng có DST, offset cố định sẽ không tự thay đổi theo ngày.

## 11. DST: thời gian bị lặp và thời gian không tồn tại

### 11.1. DST gap

Khi đồng hồ tiến lên vào đầu DST, một khoảng giờ local bị bỏ qua. Ví dụ tại một số vùng, đồng hồ nhảy từ 01:59:59 sang 03:00:00; thời gian 02:30 không tồn tại trong ngày đó.

Một local timestamp không kèm offset có thể không xác định được instant hợp lệ trong gap. Test parse/chuyển đổi ở ngày chuyển DST của region thực tế.

### 11.2. DST overlap

Khi đồng hồ lùi lại cuối DST, một khoảng giờ local xuất hiện hai lần. Ví dụ 01:30 có thể xảy ra một lần ở daylight time và một lần ở standard time.

Nếu chỉ lưu local DATE/TIMESTAMP, hai sự kiện này có thể không phân biệt được. Dùng TIMESTAMP WITH TIME ZONE hoặc lưu instant UTC cùng timezone region/context nếu nghiệp vụ cần xác định duy nhất.

### 11.3. ERROR_ON_OVERLAP_TIME

Oracle hỗ trợ tham số session ERROR_ON_OVERLAP_TIME để kiểm soát thời gian mơ hồ do DST overlap. Có thể kiểm tra:

~~~sql
SHOW PARAMETER error_on_overlap_time;
~~~

Khi bật TRUE, Oracle có thể báo lỗi nếu local time rơi vào overlap mà không đủ thông tin phân biệt. Khi FALSE, Oracle áp dụng quy tắc mặc định để chọn một interpretation. Đối với nghiệp vụ nhạy cảm, không nên dựa vào mặc định; cung cấp timezone displacement hoặc thông tin daylight/standard time phù hợp.

### 11.4. Dùng TZR và TZD

Format elements:
- TZR: timezone region.
- TZD: timezone daylight/standard abbreviation.
- TZH: timezone hour offset.
- TZM: timezone minute offset.

Ví dụ parse chuỗi có region:

~~~sql
SELECT TO_TIMESTAMP_TZ(
           '2026-11-14 09:00:00 Asia/Ho_Chi_Minh',
           'YYYY-MM-DD HH24:MI:SS TZR'
       )
FROM dual;
~~~

Với vùng có overlap, TZD có thể cần để phân biệt daylight/standard time nếu input có thông tin đó và format/model hỗ trợ.

### 11.5. Kiểm thử DST có chủ đích

Không dùng ngày hiện tại để kiểm tra DST nếu vùng đó không đổi giờ hoặc ngày hiện tại nằm ngoài thời điểm chuyển. Chọn region có DST và lấy transition date từ timezone rules của môi trường/database.

Test:
- Một phút trước gap.
- Một local time nằm trong gap.
- Một phút sau gap.
- Một local time nằm trong overlap.
- Cùng giờ local nhưng hai offset khác nhau.
- Chuyển các instant đó về UTC và so sánh.

Timezone file version của Oracle có thể khác OS/JDK timezone database. Ghi lại version và cập nhật theo quy trình database patching.

## 12. NLS_DATE_FORMAT và NLS_TIMESTAMP_FORMAT

### 12.1. Hiển thị DATE không giống giá trị DATE

SQL client có thể hiển thị DATE chỉ gồm ngày hoặc cả thời gian tùy NLS_DATE_FORMAT. Điều này không có nghĩa cột DATE chỉ lưu ngày.

Kiểm tra:

~~~sql
SELECT parameter,
       value
FROM   nls_session_parameters
WHERE  parameter IN (
           'NLS_DATE_FORMAT',
           'NLS_TIMESTAMP_FORMAT',
           'NLS_TIMESTAMP_TZ_FORMAT',
           'NLS_DATE_LANGUAGE',
           'NLS_NUMERIC_CHARACTERS'
       )
ORDER  BY parameter;
~~~

### 12.2. Thay đổi format trong session test

~~~sql
ALTER SESSION SET NLS_DATE_FORMAT = 'YYYY-MM-DD HH24:MI:SS';
ALTER SESSION SET NLS_TIMESTAMP_FORMAT =
    'YYYY-MM-DD HH24:MI:SS.FF6';
~~~

Sau đó so sánh output của SELECT. Thay đổi này ảnh hưởng cách Oracle chuyển đổi/hiển thị trong session; không thay datatype hay giá trị đã lưu.

### 12.3. Không dùng implicit string-to-date

Tránh:

~~~sql
INSERT INTO event_lab(event_date)
VALUES ('14/11/2026');
~~~

Kết quả phụ thuộc NLS_DATE_FORMAT. Dùng:

~~~sql
INSERT INTO event_lab(event_date)
VALUES (TO_DATE('14/11/2026', 'DD/MM/YYYY'));
~~~

Hoặc ANSI literal:

~~~sql
INSERT INTO event_lab(event_date)
VALUES (DATE '2026-11-14');
~~~

### 12.4. NLS ở JDBC

JDBC bind DATE/TIMESTAMP bằng typed setter thường tránh việc parse chuỗi theo NLS. Nếu gửi String vào cột DATE/TIMESTAMP, Oracle có thể thực hiện implicit conversion và phụ thuộc session.

Ưu tiên:
- PreparedStatement.setDate/setTimestamp.
- JDBC 4.2 java.time types nếu driver hỗ trợ.
- Bind Oracle TIMESTAMP WITH TIME ZONE bằng API phù hợp của driver khi cần.
- Không nối ngày giờ thành SQL string.

## 13. Kiểm thử JDBC và Java time types

### 13.1. LocalDate và Oracle DATE

LocalDate biểu diễn ngày lịch không có giờ/timezone. Nó phù hợp với cột dùng như ngày nghiệp vụ nếu ứng dụng và mapping thống nhất.

~~~java
LocalDate businessDate = LocalDate.of(2026, 11, 14);

try (PreparedStatement ps =
         connection.prepareStatement(
             "INSERT INTO business_day(id, business_date) VALUES (?, ?)")) {
    ps.setLong(1, 1L);
    ps.setDate(2, java.sql.Date.valueOf(businessDate));
    ps.executeUpdate();
}
~~~

java.sql.Date không giữ time-of-day. Nếu cột Oracle DATE đang chứa giờ, mapping LocalDate sẽ không biểu diễn đầy đủ dữ liệu đó.

### 13.2. LocalDateTime và TIMESTAMP

LocalDateTime không có timezone/offset. Dùng cho timestamp local nếu hệ thống đã thống nhất cách diễn giải:

~~~java
LocalDateTime localValue =
    LocalDateTime.of(2026, 11, 14, 21, 26, 30, 123_000_000);
~~~

Không dùng LocalDateTime một mình để biểu diễn instant toàn cầu nếu không biết timezone nào áp dụng.

### 13.3. OffsetDateTime và ZonedDateTime

- OffsetDateTime giữ local date-time cùng offset.
- ZonedDateTime giữ timezone region cùng các quy tắc vùng trong Java runtime.
- Instant biểu diễn một điểm trên timeline UTC.

Khi lưu event toàn cầu, mô hình thường rõ hơn nếu lưu Instant/OffsetDateTime với kiểu Oracle có timezone phù hợp, đồng thời lưu region ID riêng nếu cần tái dựng local time theo quy tắc địa phương lịch sử.

### 13.4. JDBC 4.2 và driver compatibility

Hỗ trợ java.time phụ thuộc JDBC driver version và kiểu Oracle column. Kiểm tra Oracle JDBC Developer's Guide cho driver đang dùng. Không giả định mọi version ojdbc8/ojdbc11 xử lý giống nhau.

Với kiểu Oracle-specific như TIMESTAMP WITH LOCAL TIME ZONE, cần integration test round-trip:
1. Bind Java value.
2. Insert.
3. Đổi SESSIONTIMEZONE.
4. Select lại.
5. So sánh instant và local display theo expected semantics.

### 13.5. Test round-trip

Một test cần xác định:
- Java type đầu vào.
- Oracle column datatype.
- Session timezone lúc insert.
- DBTIMEZONE.
- Session timezone lúc select.
- Java type nhận về.
- Expected instant/local value.

Chỉ so sánh LocalDateTime trước/sau là chưa đủ nếu chuyển đổi timezone đã xảy ra.

## 14. Bộ test SQL có thể chạy trong schema lab

### 14.1. Tạo bảng thử nghiệm

~~~sql
CREATE TABLE numeric_time_lab (
    id NUMBER(10) PRIMARY KEY,
    amount NUMBER(12,2),
    exact_value NUMBER,
    event_date DATE,
    event_ts TIMESTAMP(6),
    event_tstz TIMESTAMP(6) WITH TIME ZONE,
    event_ltz TIMESTAMP(6) WITH LOCAL TIME ZONE
);
~~~

DDL có implicit commit. Chỉ tạo bảng trong schema test của riêng bạn.

### 14.2. Insert dữ liệu biên

~~~sql
INSERT INTO numeric_time_lab (
    id, amount, exact_value, event_date,
    event_ts, event_tstz, event_ltz
)
VALUES (
    1,
    123.456,
    0.1 + 0.2,
    DATE '2024-02-29',
    TIMESTAMP '2026-11-14 21:26:30.123456',
    FROM_TZ(TIMESTAMP '2026-11-14 21:26:30.123456',
            'Asia/Ho_Chi_Minh'),
    FROM_TZ(TIMESTAMP '2026-11-14 21:26:30.123456',
            'Asia/Ho_Chi_Minh')
);
~~~

### 14.3. Kiểm tra giá trị lưu

~~~sql
SELECT id,
       TO_CHAR(amount, 'FM9999999990D00') AS amount_text,
       exact_value,
       TO_CHAR(event_date, 'YYYY-MM-DD HH24:MI:SS') AS date_text,
       TO_CHAR(event_ts, 'YYYY-MM-DD HH24:MI:SS.FF6') AS ts_text,
       TO_CHAR(event_tstz,
               'YYYY-MM-DD HH24:MI:SS.FF6 TZH:TZM') AS tstz_text,
       TO_CHAR(event_ltz,
               'YYYY-MM-DD HH24:MI:SS.FF6 TZH:TZM') AS ltz_text
FROM   numeric_time_lab
ORDER  BY id;
~~~

Format mask ở truy vấn giúp output không phụ thuộc NLS format mặc định. Với TSTZ/LTZ, format có timezone offset giúp nhìn rõ session context.

### 14.4. Đổi session timezone rồi đọc lại

~~~sql
ALTER SESSION SET TIME_ZONE = 'UTC';

SELECT id,
       event_tstz,
       event_ltz,
       SESSIONTIMEZONE
FROM   numeric_time_lab
WHERE  id = 1;
~~~

So sánh:
- TIMESTAMP WITH TIME ZONE giữ instant và timezone information.
- TIMESTAMP WITH LOCAL TIME ZONE được hiển thị theo session timezone.
- TIMESTAMP không có timezone không tự chuyển thành instant khác.

Sau đó thử lại với Asia/Ho_Chi_Minh.

### 14.5. Dọn dữ liệu test

~~~sql
ROLLBACK;
~~~

ROLLBACK chỉ hủy DML chưa commit. DDL CREATE TABLE đã implicit commit nên bảng vẫn tồn tại. Khi kết thúc bài lab, chỉ DROP đúng bảng test do bạn tạo nếu được phép.

## 15. PL/SQL test harness cho expected result

### 15.1. Assertion đơn giản

Có thể dùng PL/SQL block để báo lỗi khi actual khác expected:

~~~sql
DECLARE
    actual_value NUMBER;
BEGIN
    SELECT ROUND(12.345, 2)
    INTO   actual_value
    FROM   dual;

    IF actual_value <> 12.35 THEN
        RAISE_APPLICATION_ERROR(
            -20001,
            'ROUND test failed: actual=' || actual_value
        );
    END IF;
END;
/
~~~

Giá trị -20000 đến -20999 dành cho lỗi ứng dụng qua RAISE_APPLICATION_ERROR.

### 15.2. Test nhiều case

~~~sql
DECLARE
    PROCEDURE assert_number(
        p_name     IN VARCHAR2,
        p_actual   IN NUMBER,
        p_expected IN NUMBER
    ) IS
    BEGIN
        IF p_actual IS NULL AND p_expected IS NULL THEN
            RETURN;
        ELSIF p_actual IS NULL OR p_expected IS NULL
           OR p_actual <> p_expected THEN
            RAISE_APPLICATION_ERROR(
                -20002,
                p_name || ' failed; expected=' ||
                NVL(TO_CHAR(p_expected), 'NULL') ||
                ', actual=' || NVL(TO_CHAR(p_actual), 'NULL')
            );
        END IF;
    END;
BEGIN
    assert_number('round-positive', ROUND(1.5), 2);
    assert_number('round-negative', ROUND(-1.5), -2);
    assert_number('trunc-negative', TRUNC(-1.9), -1);
    assert_number('floor-negative', FLOOR(-1.9), -2);
    assert_number('ceil-negative', CEIL(-1.9), -1);
END;
/
~~~

Với số gần đúng, thay so sánh bằng tuyệt đối bằng điều kiện tolerance. Khi format lỗi test, ghi actual/expected với format mask rõ ràng.

### 15.3. Kiểm tra lỗi mong đợi

Có thể viết test bắt exception cho trường hợp vượt precision:

~~~sql
DECLARE
    v_value NUMBER(5,2);
BEGIN
    v_value := 1000.00;
    RAISE_APPLICATION_ERROR(-20003, 'Expected precision error did not occur');
EXCEPTION
    WHEN OTHERS THEN
        IF SQLCODE = -1438 THEN
            DBMS_OUTPUT.PUT_LINE('PASS: precision overflow rejected');
        ELSE
            RAISE;
        END IF;
END;
/
~~~

Kiểu biến PL/SQL NUMBER(5,2) không nhất thiết hành xử giống cột table trong mọi trường hợp test; để kiểm tra insert constraint chính xác, hãy thực hiện INSERT vào cột thật trong bảng lab và bắt lỗi ở block riêng.

## 16. Test matrix: dữ liệu nên có

| Nhóm | Input gợi ý | Điều cần xác nhận |
| --- | --- | --- |
| NUMBER | 0, -0.01, 0.01, max, min | Phạm vi và sign |
| NUMBER(p,s) | Sát biên precision/scale | Làm tròn khi lưu và ORA-01438 |
| ROUND | 1.5, -1.5, 2.49, 2.50 | Quy tắc điểm nửa |
| TRUNC | 1.99, -1.99 | Cắt về 0 |
| FLOOR/CEIL | -1.1, 1.1 | Hướng xuống/lên |
| MOD | Số chia âm/dương | Dấu của phần dư |
| NLS number | 1,234.56 và 1.234,56 | Decimal/group separator |
| DATE | Cuối tháng, ngày nhuận | Ranh giới lịch |
| TIMESTAMP | .000001, .999999 | Fractional seconds |
| DATE arithmetic | +0.5, -1 | Đơn vị ngày |
| ADD_MONTHS | 28/29/30/31 | Quy tắc cuối tháng |
| TSTZ | +07:00, UTC, region | Cùng instant khác biểu diễn |
| LTZ | Insert/select ở TZ khác | Hiển thị theo session timezone |
| DST gap | Local time không tồn tại | Reject/resolve theo policy |
| DST overlap | Local time xuất hiện hai lần | Phân biệt offset/region |
| NLS date | Các format khác nhau | Parse độc lập session |
| JDBC | LocalDate/LocalDateTime/OffsetDateTime | Round-trip đúng semantics |

## 17. Lỗi thường gặp và cách điều tra

| Lỗi/hiện tượng | Nguyên nhân thường gặp | Hướng kiểm tra |
| --- | --- | --- |
| ORA-01438 | Giá trị vượt precision của NUMBER(p,s) | Kiểu cột, giá trị sau rounding |
| ORA-01722 | Chuỗi không chuyển được sang NUMBER | TO_NUMBER format, NLS, input |
| ORA-01843 | Tháng không hợp lệ | Format mask và NLS_DATE_LANGUAGE |
| ORA-01861 | Literal không khớp format string | Input format, FX, format model |
| ORA-01878 | Field thời gian không tồn tại do timezone transition | DST gap, timezone region/file |
| ORA-01883 | Overlap bị từ chối theo cấu hình | ERROR_ON_OVERLAP_TIME và DST ambiguity |
| Giá trị giờ lệch vài tiếng | Session timezone, host timezone hoặc kiểu column | SYSDATE/CURRENT_TIMESTAMP, SESSIONTIMEZONE |
| Timestamp mất fractional seconds | Dùng DATE hoặc precision column thấp | Column datatype và JDBC type |
| Cùng event hiển thị giờ khác | TSTZ/LTZ hiển thị theo timezone | Session timezone và format mask |
| Ngày lệch khi chạy ở máy khác | Implicit string conversion hoặc timezone | Typed bind, explicit format/timezone |
| Test qua H2 nhưng lỗi Oracle | Khác biệt datatype, NLS, timezone và SQL semantics | Integration test trên Oracle |

### 17.1. ORA-01438

Kiểm tra:
- NUMBER(p,s) thực tế trong ALL_TAB_COLUMNS.
- Giá trị đầu vào.
- Kết quả sau scale rounding.
- Precision sau phép tính.
- Mapping Java BigDecimal precision/scale.

Đừng chỉ giảm số chữ số ở UI; có thể làm mất dữ liệu nghiệp vụ. Thay đổi precision/scale cần migration và đánh giá dữ liệu hiện có.

### 17.2. ORA-01722

Tìm chuỗi chứa ký tự không phù hợp, dấu thập phân khác locale hoặc dữ liệu bẩn. Không dựa vào implicit conversion trong predicate:

~~~sql
WHERE numeric_column = '1,25'
~~~

Dùng bind NUMBER hoặc TO_NUMBER với format/NLS rõ ràng.

### 17.3. ORA-01861 và ORA-01843

Kiểm tra:
- Format mask có đúng thứ tự ngày/tháng/năm không.
- Có tên tháng phụ thuộc ngôn ngữ không.
- Chuỗi có whitespace hoặc timezone suffix không.
- Dùng TO_DATE hay TO_TIMESTAMP đúng datatype không.
- Có format exact FX nếu cần không.

### 17.4. Lệch timezone

Ghi lại trong cùng session:
- SYSTIMESTAMP.
- CURRENT_TIMESTAMP.
- SYSDATE.
- SESSIONTIMEZONE.
- DBTIMEZONE.
- CON_NAME/SERVICE_NAME nếu multi-tenant.

Sau đó kiểm tra datatype column và Java type. Không cộng/trừ một số giờ cố định để “sửa” nếu nguyên nhân là timezone conversion tự động.

## 18. Quy trình kiểm thử trước khi phát hành

### Bước 1 — Chốt semantics nghiệp vụ

Xác định:
- Tiền tệ làm tròn theo dòng hay theo tổng.
- Scale của từng đại lượng.
- NULL khác 0 như thế nào.
- Ngày nghiệp vụ hay instant thời gian.
- Timezone nào là nguồn chuẩn.
- Có cần giữ timezone region gốc không.

### Bước 2 — Kiểm tra schema

Đọc datatype thực tế từ ALL_TAB_COLUMNS. Kiểm tra NUMBER precision/scale, DATE/TIMESTAMP/TSTZ/LTZ và default expression.

### Bước 3 — Xây dữ liệu biên

Tạo fixture có số âm, điểm nửa, sát precision, ngày cuối tháng, năm nhuận, fractional seconds, timezone khác và DST edge.

### Bước 4 — Khóa NLS/timezone trong test

Thiết lập NLS_NUMERIC_CHARACTERS, NLS_DATE_FORMAT và SESSIONTIMEZONE rõ ràng. Chạy lại với cấu hình khác để phát hiện phụ thuộc session.

### Bước 5 — Kiểm tra round-trip JDBC

Bind kiểu dữ liệu thực, insert, commit/rollback theo test, select lại và so sánh bằng semantics đúng. Kiểm tra cả pool reuse nếu code thay session state.

### Bước 6 — Kiểm tra lỗi mong đợi

Assert ORA-01438, ORA-01722, ORA-01861 hoặc lỗi timezone khi input sai. Đảm bảo ứng dụng chuyển lỗi thành validation response phù hợp.

### Bước 7 — Kiểm tra trên Oracle tương thích

Dùng Oracle integration test cho behavior đặc thù Oracle. H2 hoặc mock không đủ để xác nhận NLS, quoted type, NUMBER scale, timezone file và DST.

### Bước 8 — Lưu expected result

Version hóa test data và expected result. Ghi Oracle release/RU, COMPATIBLE, timezone file version, JDBC driver và JDK để tái hiện lỗi.

## 19. Bài thực hành

Dùng schema test và connection riêng. Các bài có DDL sẽ commit ngầm; không chạy trên bảng production.

### Bài 1 — NUMBER precision và scale

Tạo các cột NUMBER(5,2), NUMBER(8,0), NUMBER(8,-2). Insert giá trị hợp lệ, sát biên và vượt biên. Ghi nhận giá trị được lưu và lỗi.

### Bài 2 — ROUND với số âm

Chạy ROUND cho 1.5, -1.5, 2.49, -2.49, 2.50 và -2.50. So sánh expected result với quy tắc kế toán của ứng dụng.

### Bài 3 — TRUNC/FLOOR/CEIL

Tạo bảng mẫu có số âm/dương. Xác định hàm phù hợp cho phân trang và bucket.

### Bài 4 — MOD

Thử các tổ hợp dấu của dividend/divisor. Ghi nhận dấu kết quả và ứng dụng phù hợp.

### Bài 5 — NUMBER và BINARY_DOUBLE

So sánh phép cộng 0.1 + 0.2 trong NUMBER và BINARY_DOUBLE. Xây tolerance cho kiểu gần đúng.

### Bài 6 — NLS_NUMERIC_CHARACTERS

Đổi session từ decimal dot sang decimal comma. Thử TO_NUMBER và chứng minh vì sao explicit NLS parameter giúp kết quả ổn định.

### Bài 7 — DATE literal và TO_DATE

Parse cùng một ngày bằng ANSI literal và TO_DATE với format mask. Đổi NLS_DATE_FORMAT và so sánh.

### Bài 8 — DATE arithmetic

Cộng 0.5 ngày, trừ hai DATE và tính elapsed seconds. Kiểm tra phần thời gian trong cột DATE.

### Bài 9 — TIMESTAMP fractional seconds

Insert .000001 và .999999 vào TIMESTAMP(6), đọc lại bằng FF6. Thử cột DATE để thấy mất fractional seconds.

### Bài 10 — ADD_MONTHS và ngày nhuận

Test 28/29/30/31 tháng 1, ngày cuối tháng 2 và năm nhuận. Ghi kết quả ADD_MONTHS.

### Bài 11 — TSTZ và LTZ

Insert cùng instant ở +07:00 và UTC. Đổi SESSIONTIMEZONE rồi select TSTZ/LTZ để so sánh.

### Bài 12 — DST gap/overlap

Chọn vùng có DST. Test local time trong gap và overlap, bật/tắt ERROR_ON_OVERLAP_TIME trong session test, ghi kết quả.

### Bài 13 — JDBC round-trip

Dùng LocalDate, LocalDateTime và OffsetDateTime/Instant để insert/select. Xác định mapping phù hợp với datatype Oracle.

### Bài 14 — Regression test

Viết PL/SQL assertion hoặc JUnit integration test cho NUMBER, rounding, ngày cuối tháng, timezone và NLS. Ghi expected result và version môi trường.

## 20. Tài liệu Oracle tham khảo

- [Oracle Database 19c SQL Language Reference — Numeric Data Types](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/Data-Types.html): NUMBER, BINARY_FLOAT và BINARY_DOUBLE.
- [Oracle Database 19c SQL Language Reference — ROUND (number)](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/ROUND-number.html): quy tắc làm tròn NUMBER.
- [Oracle Database 19c SQL Language Reference — TRUNC (number)](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/TRUNC-number.html): cắt bỏ chữ số.
- [Oracle Database 19c SQL Language Reference — FLOOR](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/FLOOR.html) và [CEIL](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/CEIL.html): làm tròn xuống/lên.
- [Oracle Database 19c SQL Language Reference — Datetime Data Types and Time Zone Support](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/Data-Types.html): DATE, TIMESTAMP, TSTZ và LTZ.
- [Oracle Database 19c SQL Language Reference — Datetime Functions](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/Datetime-Functions.html): chuyển đổi và phép toán ngày giờ.
- [Oracle Database 19c SQL Language Reference — Format Models](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/Format-Models.html): format mask cho số và datetime.
- [Oracle Database 19c SQL Language Reference — FROM_TZ](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/FROM_TZ.html): gắn timezone vào timestamp.
- [Oracle Database 19c SQL Language Reference — AT TIME ZONE](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/Datetime-Expressions.html): chuyển timestamp theo timezone.
- [Oracle Database Globalization Support Guide 19c](https://docs.oracle.com/en/database/oracle/oracle-database/19/nlspg/): NLS, timezone region, daylight saving và globalization behavior.
- [Oracle Database JDBC Developer's Guide 19c](https://docs.oracle.com/en/database/oracle/oracle-database/19/jjdbc/): JDBC type mapping và date/time handling.

Kiểm thử NUMBER và datetime cần xác định rõ kiểu dữ liệu, quy tắc làm tròn, format/NLS và timezone session. NUMBER(p,s) có thể làm tròn hoặc từ chối dữ liệu vượt precision; ROUND khác TRUNC/FLOOR/CEIL, nhất là với số âm; DATE không giữ fractional seconds hoặc timezone; TIMESTAMP WITH TIME ZONE và LOCAL TIME ZONE có semantics khác nhau khi lưu/hiển thị. **Hãy kiểm thử giá trị biên, dùng bind có kiểu và format mask tường minh, khóa timezone/NLS trong test, rồi xác nhận round-trip trên đúng phiên bản Oracle và JDBC sẽ chạy ở production.**
