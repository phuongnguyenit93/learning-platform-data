# ORA-01722, ORA-01843, ORA-01861 và lỗi chuyển đổi phụ thuộc dữ liệu/NLS

Các lỗi chuyển đổi Oracle thường xuất hiện khi một giá trị ký tự được diễn giải thành NUMBER, DATE hoặc TIMESTAMP nhưng dữ liệu thực tế không phù hợp với định dạng mà Oracle đang sử dụng. Lỗi có thể đến từ câu SQL viết tường minh bằng TO_NUMBER/TO_DATE, hoặc từ implicit conversion khi so sánh hai kiểu dữ liệu khác nhau, gán giá trị, gọi procedure hay bind tham số từ ứng dụng Java.

Ba lỗi cần nhận diện:

- **ORA-01722: invalid number** — Oracle không thể chuyển một chuỗi thành NUMBER theo quy tắc hoặc format đang áp dụng.
- **ORA-01843: not a valid month** — phần tháng của giá trị ngày không hợp lệ hoặc không được diễn giải theo month language/format đang dùng.
- **ORA-01861: literal does not match format string** — chuỗi đầu vào không khớp format model mà phép chuyển đổi yêu cầu.

Một nguyên nhân thường gặp là phụ thuộc vào NLS session settings như NLS_NUMERIC_CHARACTERS, NLS_DATE_FORMAT, NLS_DATE_LANGUAGE và NLS_TERRITORY. Cùng một câu SQL có thể chạy trong session này nhưng thất bại trong session khác vì dấu thập phân, dấu phân nhóm, thứ tự ngày/tháng/năm hoặc ngôn ngữ tên tháng khác nhau.

Cách xử lý bền vững là hiểu kiểu dữ liệu ở hai phía, tìm nguồn implicit conversion, kiểm tra dữ liệu lỗi, dùng bind variable đúng kiểu và khai báo format/NLS rõ ràng khi thực sự cần parse text. Không nên sửa bằng cách thay NLS toàn database hoặc tự động loại bỏ ký tự trong dữ liệu khi chưa xác định ý nghĩa nghiệp vụ.

## 1. Oracle chuyển đổi dữ liệu như thế nào?

Oracle hỗ trợ chuyển đổi tường minh và chuyển đổi ngầm định.

### 1.1. Explicit conversion

SQL gọi trực tiếp hàm chuyển đổi:

~~~sql
SELECT TO_NUMBER('1250.75') FROM dual;

SELECT TO_DATE(
         '2026-11-14',
         'YYYY-MM-DD'
       )
FROM dual;
~~~

Người viết SQL chủ động chỉ định phép chuyển đổi và có thể cung cấp format model/NLS parameter. Đây là cách nên dùng khi dữ liệu đầu vào là text và cần parse thành kiểu dữ liệu Oracle.

### 1.2. Implicit conversion

Oracle tự chuyển một toán hạng để hai phía có thể so sánh hoặc thực hiện phép toán.

Ví dụ:

~~~sql
SELECT *
FROM app.orders
WHERE order_id = '10025';
~~~

Nếu ORDER_ID là NUMBER còn literal là character, Oracle có thể chuyển chuỗi '10025' thành NUMBER. Với dữ liệu số hợp lệ, câu lệnh chạy được. Nếu phép so sánh dùng một cột VARCHAR2 chứa giá trị không phải số, cùng kiểu chuyển đổi có thể gây ORA-01722.

Một ví dụ khác:

~~~sql
SELECT *
FROM app.orders
WHERE created_at >= '14/11/2026';
~~~

Nếu CREATED_AT là DATE, Oracle phải diễn giải chuỗi thành DATE theo quy tắc chuyển đổi ngầm định, thường chịu ảnh hưởng NLS_DATE_FORMAT. Session khác có format khác có thể gặp ORA-01861 hoặc diễn giải sai ngày.

### 1.3. Vì sao implicit conversion nguy hiểm?

- SQL phụ thuộc vào cấu hình session.
- Dữ liệu bẩn chỉ làm lỗi khi một execution path chạm tới giá trị đó.
- Thay đổi execution plan có thể làm lỗi xuất hiện hoặc biến mất.
- Oracle có thể phải chuyển đổi cột trong predicate, làm giảm khả năng dùng index.
- Ứng dụng JDBC có thể bind VARCHAR2 thay vì NUMBER/DATE.
- Connection pool tái sử dụng session có thể mang NLS state từ request trước nếu ứng dụng thay đổi session mà không reset.

### 1.4. Kiểu dữ liệu phải được hiểu từ schema

Kiểm tra kiểu cột:

~~~sql
SELECT owner,
       table_name,
       column_name,
       data_type,
       data_length,
       data_precision,
       data_scale,
       nullable
FROM all_tab_columns
WHERE owner = 'APP'
  AND table_name = 'ORDERS'
ORDER BY column_id;
~~~

Nếu cột lưu số tiền là VARCHAR2, trước khi thêm TO_NUMBER vào mọi truy vấn cần xác định lý do schema dùng text: dữ liệu import thô, định dạng địa phương, mã định danh hay thiết kế legacy. Không phải chuỗi chỉ gồm chữ số nào cũng mang ý nghĩa số học.

## 2. ORA-01722 — invalid number

ORA-01722 xuất hiện khi Oracle cần diễn giải một character value thành NUMBER nhưng giá trị không hợp lệ theo quy tắc chuyển đổi hoặc format model.

### 2.1. Ví dụ đơn giản

~~~sql
SELECT TO_NUMBER('ABC') FROM dual;
~~~

Oracle không thể chuyển ABC thành NUMBER.

Các dữ liệu thường gây lỗi:
- Chữ cái trong cột được kỳ vọng là số.
- Chuỗi rỗng hoặc chỉ có dấu phân cách.
- Ký hiệu tiền tệ không phù hợp format model.
- Dấu thập phân/dấu nhóm không đúng NLS.
- Dấu âm hoặc dấu cộng ở vị trí không được format cho phép.
- Ký tự khoảng trắng hoặc ký tự Unicode không được xử lý như dự kiến.
- Chuỗi số có hậu tố, đơn vị hoặc text chú thích.
- Dữ liệu bị cắt hoặc ghép sai trong ETL.

### 2.2. Implicit conversion trong predicate

Giả sử schema có:

~~~sql
CREATE TABLE app.external_orders (
    external_order_id VARCHAR2(40),
    amount_text       VARCHAR2(40)
);
~~~

Dữ liệu:

~~~sql
INSERT INTO app.external_orders VALUES ('1001', '250.50');
INSERT INTO app.external_orders VALUES ('1002', 'UNKNOWN');
~~~

Truy vấn:

~~~sql
SELECT *
FROM app.external_orders
WHERE amount_text > 100;
~~~

Vì một phía là VARCHAR2, phía kia là NUMBER, Oracle có thể chuyển amount_text thành NUMBER để so sánh. Khi gặp UNKNOWN, truy vấn có thể phát sinh ORA-01722.

Không dựa vào thứ tự điều kiện trong WHERE để lọc sạch dữ liệu trước:

~~~sql
SELECT *
FROM app.external_orders
WHERE REGEXP_LIKE(amount_text, '^[0-9]+([.][0-9]+)?$')
  AND TO_NUMBER(amount_text) > 100;
~~~

SQL optimizer được quyền thay đổi cách thực thi predicate; không được giả định điều kiện REGEXP_LIKE luôn chạy trước TO_NUMBER. Dùng CASE với nhánh có kiểm tra hoặc DEFAULT ON CONVERSION ERROR trên phiên bản hỗ trợ, và tốt hơn là chuẩn hóa dữ liệu ngay từ lúc ingest.

### 2.3. So sánh cột NUMBER với cột VARCHAR2

Ví dụ:

~~~sql
SELECT *
FROM app.orders o
JOIN app.imported_orders i
  ON o.order_id = i.order_id_text;
~~~

Nếu ORDER_ID là NUMBER và ORDER_ID_TEXT là VARCHAR2, phép join có thể yêu cầu chuyển đổi. Một giá trị bẩn trong bảng import có thể làm cả câu join lỗi.

Cách xử lý:
- Kiểm tra dữ liệu trong bảng import.
- Parse vào staging numeric column bằng quy tắc rõ.
- Đưa dòng không hợp lệ vào quarantine/error table.
- Join NUMBER với NUMBER sau khi xác nhận dữ liệu.
- Không biến cột NUMBER có index thành TO_CHAR(number_column) chỉ để che lỗi nếu có thể chuyển bind/source đúng kiểu.

### 2.4. Dấu thập phân và dấu phân nhóm

Giá trị 1,234.56 và 1.234,56 có thể mang cùng giá trị số trong hai quy ước địa phương khác nhau.

Oracle dùng NLS_NUMERIC_CHARACTERS:
- Ký tự thứ nhất là dấu thập phân.
- Ký tự thứ hai là dấu phân nhóm.

Xem session:

~~~sql
SELECT parameter, value
FROM nls_session_parameters
WHERE parameter IN (
    'NLS_NUMERIC_CHARACTERS',
    'NLS_TERRITORY'
);
~~~

Ví dụ parse chuỗi dùng dấu chấm thập phân và dấu phẩy nhóm:

~~~sql
SELECT TO_NUMBER(
         '1,234.56',
         '9G999D99',
         'NLS_NUMERIC_CHARACTERS = ''.,'''
       ) AS amount
FROM dual;
~~~

Ví dụ parse chuỗi dùng dấu phẩy thập phân và dấu chấm nhóm:

~~~sql
SELECT TO_NUMBER(
         '1.234,56',
         '9G999D99',
         'NLS_NUMERIC_CHARACTERS = '',.'''
       ) AS amount
FROM dual;
~~~

Trong format model:
- D biểu diễn decimal character theo NLS.
- G biểu diễn group separator theo NLS.

Nếu format model không có G/D phù hợp, hoặc NLS parameter khác dữ liệu nguồn, phép parse có thể lỗi hoặc cho kết quả không đúng ý định. Không thay dấu phẩy bằng dấu chấm một cách mù quáng; chuỗi 1,234 có thể có nghĩa một nghìn hai trăm ba mươi tư hoặc một phẩy hai ba bốn tùy nguồn.

### 2.5. Dấu tiền tệ và format model

Nếu dữ liệu có ký hiệu tiền tệ, cần format model và NLS_CURRENCY/NLS_ISO_CURRENCY phù hợp. Ví dụ:

~~~sql
SELECT TO_NUMBER(
         '$1,250.00',
         'L9G999D99',
         'NLS_NUMERIC_CHARACTERS = ''.,'' NLS_CURRENCY = ''$'''
       )
FROM dual;
~~~

Format model cần khớp độ dài, vị trí ký hiệu và quy tắc của nguồn. Nếu dữ liệu có nhiều loại currency, tốt hơn lưu amount dưới dạng NUMBER và currency code ở cột riêng.

## 3. ORA-01843 — not a valid month

ORA-01843 thường xảy ra khi Oracle không thể nhận diện phần tháng của chuỗi ngày theo format model và NLS_DATE_LANGUAGE đang áp dụng.

### 3.1. Tên tháng phụ thuộc ngôn ngữ

Ví dụ:

~~~sql
SELECT TO_DATE(
         '14-NOV-2026',
         'DD-MON-YYYY'
       )
FROM dual;
~~~

Nếu session dùng ngôn ngữ tháng khác và không nhận diện NOV, phép parse có thể lỗi. Khai báo language rõ:

~~~sql
SELECT TO_DATE(
         '14-NOV-2026',
         'DD-MON-YYYY',
         'NLS_DATE_LANGUAGE = ENGLISH'
       )
FROM dual;
~~~

Nếu nguồn gửi tên tháng tiếng Việt hoặc ngôn ngữ khác, format language phải khớp nguồn và được kiểm tra theo khả năng hỗ trợ của Oracle release.

### 3.2. Tháng không hợp lệ

Ví dụ chuỗi có tháng 13:

~~~sql
SELECT TO_DATE(
         '2026-13-14',
         'YYYY-MM-DD'
       )
FROM dual;
~~~

Tháng nằm ngoài miền 01–12. Tùy trường hợp, Oracle có thể báo ORA-01843 hoặc lỗi ngày liên quan.

### 3.3. NLS_DATE_LANGUAGE

Xem language của session:

~~~sql
SELECT parameter, value
FROM nls_session_parameters
WHERE parameter IN (
    'NLS_DATE_LANGUAGE',
    'NLS_DATE_FORMAT',
    'NLS_TERRITORY'
);
~~~

Có thể parse tên tháng với NLS rõ ràng:

~~~sql
SELECT TO_DATE(
         '14-NOV-2026',
         'DD-MON-YYYY',
         'NLS_DATE_LANGUAGE=ENGLISH'
       )
FROM dual;
~~~

Đừng dùng tên tháng theo ngôn ngữ mặc định của một máy phát triển rồi đưa chuỗi đó sang production mà không xác định NLS.

### 3.4. YY và RR

YY và RR có quy tắc xử lý năm hai chữ số khác nhau. Dùng năm bốn chữ số YYYY khi định dạng dữ liệu cho phép. Tránh phụ thuộc cửa sổ thế kỷ của RR nếu dữ liệu có thể tồn tại lâu hoặc được chuyển giữa hệ thống.

## 4. ORA-01861 — literal does not match format string

ORA-01861 xảy ra khi literal không khớp format model. Lỗi có thể đến từ thứ tự ngày/tháng/năm, dấu phân cách, thành phần thời gian, phần fractional seconds hoặc timezone.

### 4.1. Sai thứ tự ngày và tháng

~~~sql
SELECT TO_DATE(
         '14/11/2026',
         'YYYY-MM-DD'
       )
FROM dual;
~~~

Input dùng DD/MM/YYYY nhưng format model yêu cầu YYYY-MM-DD.

Cách đúng:

~~~sql
SELECT TO_DATE(
         '14/11/2026',
         'DD/MM/YYYY'
       )
FROM dual;
~~~

### 4.2. Dấu phân cách không khớp

2026-11-14 và 2026/11/14 là hai chuỗi khác nhau. Nếu format model chỉ định dấu gạch ngang, không giả định Oracle sẽ tự thay bằng dấu gạch chéo.

~~~sql
SELECT TO_DATE(
         '2026/11/14',
         'YYYY-MM-DD'
       )
FROM dual;
~~~

### 4.3. Có thành phần thời gian nhưng format không có

~~~sql
SELECT TO_DATE(
         '2026-11-14 15:30:00',
         'YYYY-MM-DD'
       )
FROM dual;
~~~

Chuỗi có thêm time component. Format model cần mô tả đúng phần thời gian nếu mục tiêu là parse cả ngày giờ:

~~~sql
SELECT TO_DATE(
         '2026-11-14 15:30:00',
         'YYYY-MM-DD HH24:MI:SS'
       )
FROM dual;
~~~

### 4.4. Format model không phải chuỗi ví dụ

Format model mô tả cách diễn giải input, không phải chỉ là nhãn. Cần kiểm tra:
- YYYY hay RR/YY.
- MM hay MON/MONTH.
- DD.
- HH24, MI, SS.
- FF cho fractional seconds.
- TZH/TZM hoặc TZR/TZD cho timezone.
- Dấu phân cách literal.
- NLS_DATE_LANGUAGE khi dùng tên tháng.

## 5. Phân biệt các lỗi chuyển đổi ngày thường gặp

Các lỗi ngày/giờ gần nhau nhưng chỉ dấu nguyên nhân khác nhau.

| Mã lỗi | Ý nghĩa thường gặp | Hướng kiểm tra |
| --- | --- | --- |
| ORA-01843 | Tháng không hợp lệ/không được nhận diện | MM/MONTH/MON, NLS_DATE_LANGUAGE, dữ liệu tháng |
| ORA-01861 | Literal không khớp format model | Thứ tự field, separator, time component |
| ORA-01858 | Gặp ký tự không phải số ở vị trí cần numeric | Ngày/tháng/năm/giờ và format model |
| ORA-01847 | Ngày trong tháng không hợp lệ | Day value và month/year |
| ORA-01830 | Format model kết thúc trước khi parse hết input | Chuỗi có trailing time/text |
| ORA-01821 | Format code không hợp lệ | Format model token |
| ORA-01841 | Năm không hợp lệ hoặc vượt phạm vi | Year value và calendar |

Không sửa tất cả lỗi ngày bằng cách đổi NLS_DATE_FORMAT. Hãy so sánh chuỗi thực tế, format model, NLS language và kiểu dữ liệu đích.

## 6. NLS settings ảnh hưởng phép chuyển đổi ra sao?

NLS (National Language Support) điều khiển các quy ước ngôn ngữ và vùng miền trong database session.

### 6.1. Các tham số thường gặp

| Tham số | Ảnh hưởng |
| --- | --- |
| NLS_NUMERIC_CHARACTERS | Dấu thập phân và dấu phân nhóm |
| NLS_DATE_FORMAT | Format mặc định khi chuyển đổi/hiển thị DATE trong nhiều ngữ cảnh |
| NLS_DATE_LANGUAGE | Ngôn ngữ tên tháng/ngày và một số text date |
| NLS_TERRITORY | Quy ước vùng miền, có thể ảnh hưởng default date/numeric |
| NLS_TIMESTAMP_FORMAT | Format mặc định cho TIMESTAMP |
| NLS_TIMESTAMP_TZ_FORMAT | Format mặc định cho TIMESTAMP WITH TIME ZONE |
| NLS_CALENDAR | Lịch được sử dụng trong một số phép diễn giải ngày |
| NLS_CURRENCY | Ký hiệu tiền tệ địa phương |
| NLS_ISO_CURRENCY | Ký hiệu tiền tệ ISO theo territory |

### 6.2. Xem NLS session parameters

~~~sql
SELECT parameter,
       value
FROM nls_session_parameters
ORDER BY parameter;
~~~

Chỉ xem các tham số liên quan:

~~~sql
SELECT parameter,
       value
FROM nls_session_parameters
WHERE parameter IN (
    'NLS_NUMERIC_CHARACTERS',
    'NLS_DATE_FORMAT',
    'NLS_DATE_LANGUAGE',
    'NLS_TERRITORY',
    'NLS_TIMESTAMP_FORMAT',
    'NLS_TIMESTAMP_TZ_FORMAT',
    'NLS_CALENDAR'
)
ORDER BY parameter;
~~~

### 6.3. So sánh session, database và instance

~~~sql
SELECT 'SESSION' AS scope, parameter, value
FROM nls_session_parameters
WHERE parameter IN (
    'NLS_NUMERIC_CHARACTERS',
    'NLS_DATE_FORMAT',
    'NLS_DATE_LANGUAGE'
)
UNION ALL
SELECT 'DATABASE', parameter, value
FROM nls_database_parameters
WHERE parameter IN (
    'NLS_NUMERIC_CHARACTERS',
    'NLS_DATE_FORMAT',
    'NLS_DATE_LANGUAGE'
)
ORDER BY parameter, scope;
~~~

NLS_DATABASE_PARAMETERS cho biết cấu hình database-level; session parameters mới là những giá trị cần xem khi câu SQL thực sự chạy. Client, driver và logon environment có thể ảnh hưởng session defaults.

### 6.4. NLS_LANG và JDBC Thin

NLS_LANG là biến môi trường thường gặp ở Oracle Client/OCI, mô tả language, territory và character set của client. Nó không phải cách tổng quát để điều khiển mọi session NLS.

JDBC Thin chạy bằng Java và xử lý Unicode theo cơ chế riêng; không nên giả định thay NLS_LANG trên host sẽ sửa được phép parse của Thin session. Hãy kiểm tra NLS_SESSION_PARAMETERS trên đúng connection.

### 6.5. ALTER SESSION chỉ dùng có chủ đích

Có thể đặt session NLS:

~~~sql
ALTER SESSION SET NLS_NUMERIC_CHARACTERS = '.,';
ALTER SESSION SET NLS_DATE_LANGUAGE = 'ENGLISH';
ALTER SESSION SET NLS_DATE_FORMAT = 'YYYY-MM-DD';
~~~

Đây là cấu hình session, không phải sửa dữ liệu hay thay thế format model rõ ràng. Với connection pool, ALTER SESSION có thể tồn tại sau khi connection được trả về pool và được request khác sử dụng.

Nếu ứng dụng thay đổi NLS session:
- Đặt baseline khi tạo/borrow connection.
- Reset session state khi trả connection.
- Không dựa vào thứ tự request.
- Kiểm tra cả mọi datasource và pool.
- Tốt hơn, dùng explicit conversion và bind đúng kiểu để giảm phụ thuộc session.

## 7. Format model và conversion an toàn

### 7.1. Chuyển text thành NUMBER

~~~sql
SELECT TO_NUMBER(
         :amount_text,
         'FM999G999G999D9999',
         'NLS_NUMERIC_CHARACTERS = ''.,'''
       )
FROM dual;
~~~

Bind amount_text là chuỗi theo contract đã định. Format model phải đáp ứng miền giá trị, precision, scale và dấu âm/dương của nghiệp vụ.

### 7.2. Chuyển text thành DATE

~~~sql
SELECT TO_DATE(
         :date_text,
         'YYYY-MM-DD'
       )
FROM dual;
~~~

Khi dùng tên tháng:

~~~sql
SELECT TO_DATE(
         :date_text,
         'DD-MON-YYYY',
         'NLS_DATE_LANGUAGE=ENGLISH'
       )
FROM dual;
~~~

### 7.3. Chuyển text thành TIMESTAMP

~~~sql
SELECT TO_TIMESTAMP(
         :timestamp_text,
         'YYYY-MM-DD HH24:MI:SS.FF'
       )
FROM dual;
~~~

Với timezone:

~~~sql
SELECT TO_TIMESTAMP_TZ(
         :timestamp_text,
         'YYYY-MM-DD HH24:MI:SS TZH:TZM'
       )
FROM dual;
~~~

Không loại bỏ timezone khỏi dữ liệu nếu nghiệp vụ cần xác định thời điểm tuyệt đối. TIMESTAMP, TIMESTAMP WITH TIME ZONE và TIMESTAMP WITH LOCAL TIME ZONE có semantics khác nhau.

### 7.4. Dùng ANSI date/timestamp literal

Khi literal cố định trong SQL, ANSI literal tránh phụ thuộc NLS:

~~~sql
SELECT *
FROM app.orders
WHERE created_at >= DATE '2026-11-01'
  AND created_at <  DATE '2026-12-01';
~~~

Timestamp literal:

~~~sql
SELECT TIMESTAMP '2026-11-14 15:30:00'
FROM dual;
~~~

Date literal dùng định dạng YYYY-MM-DD. Với giá trị động từ ứng dụng, bind biến kiểu DATE/TIMESTAMP thay vì nối chuỗi literal.

### 7.5. Không gọi TO_DATE trên cột DATE

Sai hoặc không cần thiết:

~~~sql
SELECT TO_DATE(created_at, 'YYYY-MM-DD')
FROM app.orders;
~~~

CREATED_AT đã là DATE. Oracle có thể chuyển DATE sang text theo NLS_DATE_FORMAT rồi lại parse thành DATE, tạo phụ thuộc NLS và làm mất thông tin giờ.

Đúng:

~~~sql
SELECT created_at
FROM app.orders;
~~~

Nếu cần định dạng để hiển thị:

~~~sql
SELECT TO_CHAR(created_at, 'YYYY-MM-DD HH24:MI:SS')
FROM app.orders;
~~~

TO_CHAR dùng cho presentation; giữ kiểu DATE/TIMESTAMP trong logic lọc và join.

## 8. Kiểm tra dữ liệu bẩn trước khi chuyển đổi

Trước khi sửa SQL, cần xác định chính xác giá trị nào không hợp lệ và chúng đến từ đâu.

### 8.1. Tìm giá trị không phải số

Ở Oracle release hỗ trợ REGEXP_LIKE:

~~~sql
SELECT rowid,
       amount_text
FROM app.external_orders
WHERE amount_text IS NOT NULL
  AND NOT REGEXP_LIKE(
        TRIM(amount_text),
        '^[+-]?[0-9]+([.][0-9]+)?$'
      );
~~~

Pattern trên chỉ chấp nhận dấu chấm thập phân, không chấp nhận dấu phân nhóm, exponent, currency symbol hoặc locale khác. Điều chỉnh theo contract nguồn. Không dùng regex này như một định nghĩa phổ quát cho mọi numeric string.

### 8.2. VALIDATE_CONVERSION

Từ Oracle Database 12.2 trở lên, có thể dùng VALIDATE_CONVERSION trong các release hỗ trợ:

~~~sql
SELECT rowid,
       amount_text
FROM app.external_orders
WHERE amount_text IS NOT NULL
  AND VALIDATE_CONVERSION(
        amount_text AS NUMBER,
        'FM999G999G999D9999',
        'NLS_NUMERIC_CHARACTERS = ''.,'''
      ) = 0;
~~~

VALIDATE_CONVERSION trả 1 nếu expression có thể chuyển đổi theo quy tắc chỉ định, 0 nếu không. NULL được xem là có thể chuyển đổi và thường trả 1; vì vậy kiểm tra NULL riêng khi cần.

### 8.3. VALIDATE_CONVERSION cho DATE

~~~sql
SELECT rowid,
       order_date_text
FROM app.external_orders
WHERE order_date_text IS NOT NULL
  AND VALIDATE_CONVERSION(
        order_date_text AS DATE,
        'YYYY-MM-DD'
      ) = 0;
~~~

Với tên tháng, thêm NLS_DATE_LANGUAGE tương ứng.

### 8.4. DEFAULT ON CONVERSION ERROR

Từ Oracle Database 12.2 trở lên trong các release hỗ trợ, TO_NUMBER/TO_DATE/TO_TIMESTAMP có thể dùng DEFAULT ON CONVERSION ERROR:

~~~sql
SELECT TO_NUMBER(
         amount_text DEFAULT NULL ON CONVERSION ERROR,
         'FM999G999G999D9999',
         'NLS_NUMERIC_CHARACTERS = ''.,'''
       ) AS amount
FROM app.external_orders;
~~~

Và:

~~~sql
SELECT TO_DATE(
         order_date_text DEFAULT NULL ON CONVERSION ERROR,
         'YYYY-MM-DD'
       ) AS order_date
FROM app.external_orders;
~~~

Cách này giúp truy vấn không thất bại khi một giá trị không parse được, nhưng NULL có thể làm mất dấu khác biệt giữa dữ liệu nguồn NULL và dữ liệu sai định dạng. Trong ETL, nên ghi nhận lỗi vào quarantine table thay vì âm thầm thay mọi giá trị sai thành NULL.

### 8.5. CASE để kiểm soát phép chuyển đổi

~~~sql
SELECT CASE
         WHEN amount_text IS NOT NULL
          AND VALIDATE_CONVERSION(
                amount_text AS NUMBER,
                'FM999G999G999D9999',
                'NLS_NUMERIC_CHARACTERS = ''.,'''
              ) = 1
         THEN TO_NUMBER(
                amount_text,
                'FM999G999G999D9999',
                'NLS_NUMERIC_CHARACTERS = ''.,'''
              )
         ELSE NULL
       END AS amount
FROM app.external_orders;
~~~

CASE expression có quy tắc short-circuit evaluation. Dùng cùng format/NLS giữa validation và conversion. Nếu phiên bản hỗ trợ DEFAULT ON CONVERSION ERROR, cú pháp đó thường ngắn gọn hơn.

## 9. Chẩn đoán dữ liệu ký tự bất thường

Giá trị nhìn giống nhau trên màn hình có thể chứa byte hoặc ký tự khác nhau.

### 9.1. Khoảng trắng và ký tự điều khiển

Kiểm tra:

~~~sql
SELECT rowid,
       '[' || amount_text || ']' AS visible_value,
       LENGTH(amount_text) AS char_length,
       LENGTHB(amount_text) AS byte_length,
       DUMP(amount_text, 1016) AS hex_dump
FROM app.external_orders
WHERE amount_text IS NOT NULL;
~~~

DUMP giúp xem representation và mã byte/character theo format được chọn. LENGTH và LENGTHB giúp nhận biết chuỗi có độ dài byte khác với số ký tự.

### 9.2. Ký tự Unicode

Một dấu trừ ASCII có thể khác dấu trừ Unicode. Dấu cách thường và non-breaking space cũng khác nhau. Có thể xem biểu diễn Unicode:

~~~sql
SELECT amount_text,
       ASCIISTR(amount_text)
FROM app.external_orders
WHERE amount_text IS NOT NULL;
~~~

ASCIISTR biểu diễn ký tự non-ASCII bằng escape dạng Unicode, hữu ích khi dữ liệu nhập từ Excel, CSV, web form hoặc hệ thống ngoài.

### 9.3. Không tự động TRIM/REPLACE mọi thứ

TRIM có thể xử lý khoảng trắng đầu/cuối theo quy tắc của hàm, nhưng không bảo đảm loại bỏ mọi ký tự Unicode space. REPLACE dấu phẩy/chấm có thể làm sai giá trị khi locale khác nhau.

Trước khi normalize:
1. Xác định encoding và source system.
2. Xem raw bytes/Unicode.
3. Xác định separator theo contract.
4. Định nghĩa quy tắc cho dấu âm, currency và whitespace.
5. Giữ raw input để audit.
6. Lưu normalized value và trạng thái parse.
7. Đưa dòng không hợp lệ vào quarantine.

## 10. NLS và date/time trong truy vấn

### 10.1. Không so sánh DATE với chuỗi

Tránh:

~~~sql
SELECT *
FROM app.orders
WHERE created_at = '14/11/2026';
~~~

Nên dùng:

~~~sql
SELECT *
FROM app.orders
WHERE created_at >= DATE '2026-11-14'
  AND created_at <  DATE '2026-11-15';
~~~

Hoặc bind java.sql.Date/Timestamp theo yêu cầu.

### 10.2. Lọc ngày có cả giờ

DATE trong Oracle chứa cả ngày và giờ tới giây. So sánh bằng DATE literal chỉ khớp đúng midnight.

Để lấy toàn bộ ngày, dùng khoảng nửa mở:

~~~sql
WHERE created_at >= DATE '2026-11-14'
  AND created_at <  DATE '2026-11-15'
~~~

Cách này cũng tránh bọc cột trong TRUNC() nếu cần dùng index range scan. Nếu dùng TRUNC(created_at), cân nhắc function-based index và semantics timezone.

### 10.3. NLS_TIMESTAMP_FORMAT

TIMESTAMP có format mặc định riêng. Không nên dùng chuỗi timestamp thiếu format rõ ràng trong INSERT/UPDATE:

~~~sql
INSERT INTO app.events(event_time)
VALUES ('14-NOV-2026 15:30:00');
~~~

Nên dùng TO_TIMESTAMP với format hoặc bind TIMESTAMP:

~~~sql
INSERT INTO app.events(event_time)
VALUES (
    TO_TIMESTAMP(
        :event_time_text,
        'DD-MON-YYYY HH24:MI:SS',
        'NLS_DATE_LANGUAGE=ENGLISH'
    )
);
~~~

### 10.4. Timezone và session

TIMESTAMP WITH TIME ZONE giữ timezone/offset theo semantics của kiểu dữ liệu. TIMESTAMP WITH LOCAL TIME ZONE chuẩn hóa khi lưu và hiển thị theo session time zone. Khi đối soát thời điểm giữa hệ thống:
- Ghi rõ timezone của source.
- Chuẩn hóa sang UTC nếu contract quy định.
- Bind kiểu dữ liệu có timezone phù hợp.
- Không parse local time rồi giả định nó là UTC.
- Kiểm tra DST nếu nguồn dùng local region.

## 11. Ảnh hưởng của bind variable và JDBC

Một ứng dụng có thể tạo ORA-01722 hoặc ORA-01861 dù SQL trên SQL Developer chạy thành công, vì driver bind giá trị bằng kiểu khác hoặc session NLS khác.

### 11.1. Bind NUMBER bằng setBigDecimal

Ví dụ:

~~~java
String sql =
    "select order_id from app.orders where total_amount > ?";

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setBigDecimal(1, new BigDecimal("1250.50"));

    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            System.out.println(rs.getLong("order_id"));
        }
    }
}
~~~

Nếu cột là NUMBER, bind BigDecimal/long/int theo miền giá trị thay vì gửi một chuỗi và buộc Oracle parse theo NLS.

### 11.2. Bind DATE/TIMESTAMP bằng kiểu thời gian

~~~java
String sql =
    "select order_id from app.orders where created_at >= ?";

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setTimestamp(
        1,
        Timestamp.valueOf(LocalDateTime.of(2026, 11, 14, 0, 0))
    );

    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            System.out.println(rs.getLong("order_id"));
        }
    }
}
~~~

Nếu ứng dụng có LocalDate, có thể dùng java.sql.Date.valueOf(localDate) hoặc JDBC 4.2 setObject khi driver hỗ trợ. Chọn type mapping nhất quán với cột Oracle.

### 11.3. Khi nào bind String?

Chỉ bind String nếu giá trị thực sự là text hoặc cần parse theo contract đã định. Nếu source gửi ngày dạng text:
- Kiểm tra format.
- Dùng TO_DATE/TO_TIMESTAMP với format rõ.
- Xác định NLS language nếu có tên tháng.
- Validate trước khi ghi dữ liệu chính.

Không dùng setString cho mọi tham số vì tất cả input đều đến từ HTTP.

### 11.4. PreparedStatement không tự sửa lỗi dữ liệu

Bind variable giúp tách SQL và value, giảm SQL injection và ổn định cursor sharing. Nó không tự chuyển một chuỗi bẩn thành NUMBER/DATE hợp lệ. Kiểu bind phải đúng với kiểu cột hoặc phải có conversion rõ ràng.

### 11.5. Kiểm tra session của connection pool

Có thể truy vấn NLS trên chính connection được mượn từ pool:

~~~sql
SELECT parameter, value
FROM nls_session_parameters
WHERE parameter IN (
    'NLS_NUMERIC_CHARACTERS',
    'NLS_DATE_FORMAT',
    'NLS_DATE_LANGUAGE',
    'NLS_TERRITORY'
);
~~~

Chạy cùng query trên nhiều connection và sau nhiều request để phát hiện session state bị thay đổi. Nếu ứng dụng dùng ALTER SESSION, đảm bảo reset hoặc cấu hình baseline cho mỗi connection.

## 12. Data ingestion, ETL và staging

Nguồn CSV/Excel/API thường cung cấp text. Không nên parse trực tiếp mọi giá trị vào bảng nghiệp vụ mà không có bước kiểm tra.

### 12.1. Giữ raw input

Staging table có thể lưu raw amount/date text, source file và row number, source system, ingest timestamp, parse status, error code/message và normalized NUMBER/DATE nếu parse thành công.

Ví dụ:

~~~sql
CREATE TABLE app.order_stage (
    source_file       VARCHAR2(255),
    source_row        NUMBER,
    raw_amount        VARCHAR2(100),
    raw_order_date    VARCHAR2(100),
    amount_value      NUMBER,
    order_date        DATE,
    parse_status      VARCHAR2(20),
    parse_error       VARCHAR2(4000)
);
~~~

Bảng này là ví dụ đơn giản; thiết kế thực tế cần batch ID, source key, deduplication và retention.

### 12.2. Validate trước khi insert

~~~sql
SELECT source_file,
       source_row,
       raw_amount,
       CASE
         WHEN raw_amount IS NULL THEN 'MISSING'
         WHEN VALIDATE_CONVERSION(
                raw_amount AS NUMBER,
                'FM999G999G999D9999',
                'NLS_NUMERIC_CHARACTERS = ''.,'''
              ) = 1 THEN 'VALID'
         ELSE 'INVALID_NUMBER'
       END AS amount_status
FROM app.order_stage;
~~~

Tương tự với date:

~~~sql
SELECT source_file,
       source_row,
       raw_order_date,
       CASE
         WHEN raw_order_date IS NULL THEN 'MISSING'
         WHEN VALIDATE_CONVERSION(
                raw_order_date AS DATE,
                'YYYY-MM-DD'
              ) = 1 THEN 'VALID'
         ELSE 'INVALID_DATE'
       END AS date_status
FROM app.order_stage;
~~~

### 12.3. Quarantine record

Đưa dòng sai định dạng vào bảng lỗi có source key và lý do cụ thể. Không bỏ qua âm thầm hoặc chuyển hết thành 0/NULL nếu giá trị đó ảnh hưởng tiền, ngày hiệu lực hoặc khóa nghiệp vụ.

### 12.4. Chuẩn hóa theo nguồn

Mỗi feed cần contract:
- Encoding.
- Decimal/group separators.
- Date/time format.
- Timezone.
- Null representation.
- Currency.
- Sign convention.
- Trimming/whitespace policy.
- Allowed precision/scale.
- Error handling và retry.

Không suy ra locale từ máy chủ hoặc NLS session.

## 13. Chẩn đoán lỗi trong production

Khi ORA-01722/01843/01861 xảy ra, cần thu thập đủ bối cảnh để tái hiện.

### 13.1. Ghi lại câu SQL và bind metadata

Log có kiểm soát:
- SQL_ID hoặc statement identifier.
- Bind position/name.
- Bind datatype.
- Giá trị đã mask nếu nhạy cảm.
- JDK/JDBC driver version.
- Database service/PDB.
- Session NLS parameters.
- Request/batch ID.
- Thời gian và timezone.

Không log password, token, full payment data hoặc dữ liệu nhạy cảm.

### 13.2. Tìm SQL_ID và execution plan

DBA có thể dùng V$SQL/V$SQL_BIND_CAPTURE khi có quyền và dữ liệu capture. Bind capture không bảo đảm có mọi bind value hoặc mọi execution. Với SQL cụ thể, lưu SQL text, bind datatype và application trace.

Xem execution plan:

~~~sql
SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        sql_id => :sql_id,
        format => 'ALLSTATS LAST +PREDICATE'
    )
);
~~~

Plan có thể cho thấy implicit conversion như TO_NUMBER(column) hoặc TO_CHAR(date_column) trong predicate. Predicate conversion cũng có thể làm mất index access hoặc gây cardinality estimate kém.

### 13.3. Tìm nơi có conversion

Tìm trong SQL:
- So sánh NUMBER với VARCHAR2.
- So sánh DATE/TIMESTAMP với text.
- NVL/COALESCE/CASE trộn kiểu dữ liệu.
- UNION/UNION ALL có cột khác datatype.
- JOIN giữa key có datatype khác.
- Function argument nhận text nhưng cần NUMBER/DATE.
- Dynamic SQL nối chuỗi.
- PL/SQL assignment giữa kiểu khác nhau.

### 13.4. NLS snapshot khi lỗi

Ghi nhận:

~~~sql
SELECT parameter,
       value
FROM nls_session_parameters
WHERE parameter LIKE 'NLS_%'
ORDER BY parameter;
~~~

Cùng một application pool có thể có nhiều session với state khác nhau. Lấy NLS từ một SQL Developer session không chứng minh NLS của connection gây lỗi giống nhau.

### 13.5. Error message details

Một số Oracle release có thể cung cấp chi tiết bổ sung cho ORA-01722, bao gồm giá trị hoặc biểu thức gây lỗi. Khi tính năng này được hỗ trợ, dùng chi tiết từ error message/diagnostic để khoanh vùng; không dựa vào nó thay cho việc kiểm tra dữ liệu và SQL.

## 14. Sửa lỗi an toàn theo từng bước

Một quy trình xử lý có thể áp dụng:

1. Ghi nhận nguyên văn ORA code, SQL_ID, bind datatype và thời điểm.
2. Xác định câu lệnh và phép chuyển đổi.
3. Kiểm tra datatype của cột, literal và bind.
4. Ghi lại NLS session parameters trên connection lỗi.
5. Lấy một tập dữ liệu tái hiện, giữ raw value.
6. Tìm giá trị không parse được bằng VALIDATE_CONVERSION/regex theo contract.
7. Phân loại dữ liệu sai: separator, month language, whitespace, ký tự Unicode, format, null hay corruption.
8. Chọn sửa SQL, sửa bind type, chuẩn hóa source hoặc làm sạch dữ liệu.
9. Kiểm thử với cả dữ liệu hợp lệ và dữ liệu lỗi.
10. Kiểm tra execution plan/index và hiệu năng.
11. Triển khai có giám sát, đo số dòng quarantine và lỗi còn lại.
12. Thêm data contract/validation để lỗi không tái diễn.

### 14.1. Không sửa NLS toàn database như phản xạ đầu tiên

Đổi NLS_DATABASE_PARAMETERS hoặc init parameter có thể ảnh hưởng nhiều ứng dụng và session. Nó cũng không sửa các giá trị đã được lưu theo quy ước khác nhau. Trước tiên, xác định source contract và sửa ở đúng boundary.

### 14.2. Không dùng TO_NUMBER trên mọi cột text mà không validate

Một cột VARCHAR2 có thể chứa mã như 00123, A123, N/A hoặc chuỗi tiền tệ. Chuyển hết thành NUMBER có thể phá semantics hoặc mất leading zeros.

### 14.3. Không thay dữ liệu lỗi thành 0

Nếu amount_text không parse được, thay bằng 0 có thể tạo báo cáo sai, hóa đơn sai hoặc mất dấu lỗi nguồn. Giữ raw value và quarantine record.

### 14.4. Không chỉ dựa vào một execution plan

Optimizer có thể thay đổi plan sau stats refresh, bind value, RU hoặc thay đổi dữ liệu. SQL phải an toàn với toàn bộ dữ liệu hợp lệ/bẩn theo contract, không dựa vào predicate order tình cờ.

## 15. Các mẫu SQL nên dùng và nên tránh

| Tình huống | Tránh | Nên dùng |
| --- | --- | --- |
| So NUMBER với input text | number_col = :text | Bind NUMBER hoặc parse text rõ ràng |
| So DATE với chuỗi | date_col = '14/11/2026' | DATE/TIMESTAMP bind hoặc ANSI literal |
| Parse số locale | TO_NUMBER(text_col) không NLS | TO_NUMBER với format và NLS rõ |
| Parse tên tháng | TO_DATE với NLS mặc định | TO_DATE với NLS_DATE_LANGUAGE |
| Cột đã là DATE | TO_DATE(date_col, ...) | Dùng date_col trực tiếp |
| Dữ liệu import chưa tin cậy | Convert trực tiếp trong join | Staging, validate, quarantine rồi join |
| Date range cả ngày | TRUNC(date_col) = ... trong mọi query | Khoảng nửa mở [start, next_day) |
| Conversion có thể lỗi | Dựa vào WHERE predicate order | VALIDATE_CONVERSION/CASE hoặc DEFAULT ON CONVERSION ERROR |
| Giá trị dynamic | Nối chuỗi SQL | PreparedStatement với bind type phù hợp |

## 16. Ví dụ xử lý một feed có lỗi số và ngày

Giả sử feed gửi các giá trị:

| source_row | raw_amount | raw_date |
| --- | --- | --- |
| 1 | 1,250.50 | 2026-11-14 |
| 2 | 1.250,50 | 14-NOV-2026 |
| 3 | UNKNOWN | 2026-13-14 |
| 4 | 500.00 | 2026/11/15 |

Không thể parse tất cả bằng một format mặc định nếu nguồn không có contract thống nhất.

### 16.1. Xác định source locale

Nếu file có hai format số khác nhau, cần xác định feed có trộn nguồn hay không. Không thể chỉ dựa vào chuỗi để biết 1,250 là 1250 hay 1.250 nếu không có locale/contract.

### 16.2. Tách theo feed/format

Nếu nguồn A dùng decimal dot, group comma:

~~~sql
TO_NUMBER(
  raw_amount,
  'FM999G999G999D9999',
  'NLS_NUMERIC_CHARACTERS = ''.,'''
)
~~~

Nếu nguồn B dùng decimal comma, group dot:

~~~sql
TO_NUMBER(
  raw_amount,
  'FM999G999G999D9999',
  'NLS_NUMERIC_CHARACTERS = '',.'''
)
~~~

Ngày nguồn A ISO:

~~~sql
TO_DATE(raw_date, 'YYYY-MM-DD')
~~~

Ngày nguồn B có tên tháng tiếng Anh:

~~~sql
TO_DATE(
  raw_date,
  'DD-MON-YYYY',
  'NLS_DATE_LANGUAGE=ENGLISH'
)
~~~

### 16.3. Quarantine dòng lỗi

Dòng 3 có amount UNKNOWN và tháng 13 nên không nên insert vào bảng nghiệp vụ. Dòng 4 dùng separator ngày khác contract ISO; cần xác minh nguồn trước khi thêm format thứ hai.

Không tự động thử nhiều format rồi lấy kết quả đầu tiên nếu hai format có thể diễn giải cùng chuỗi thành các ngày khác nhau. Format phải được xác định từ metadata/source system.

## 17. Ảnh hưởng tới index và hiệu năng

Implicit conversion không chỉ gây lỗi; nó có thể làm query chậm.

### 17.1. Conversion trên indexed column

Ví dụ:

~~~sql
SELECT *
FROM app.orders
WHERE TO_CHAR(order_id) = :order_id_text;
~~~

Nếu có index trên ORDER_ID, bọc column trong TO_CHAR có thể khiến index thông thường không được dùng như mong muốn. Có thể cần function-based index, nhưng trước hết hãy bind đúng NUMBER.

### 17.2. Conversion do datatype mismatch

Nếu predicate tạo ra TO_NUMBER(varchar_column), Oracle có thể phải tính conversion cho nhiều row và có thể lỗi khi gặp giá trị bẩn. Tùy expression và optimizer, plan có thể không dùng index phù hợp.

### 17.3. Xác nhận plan sau sửa

Dùng DBMS_XPLAN.DISPLAY_CURSOR với predicate information. Kiểm tra:
- Có implicit conversion trên cột index không?
- Predicate có còn SARGable không?
- Estimated/actual rows.
- Full table scan có hợp lý không?
- Bind datatype có khớp cột không?
- Có function-based index cần thiết không?

Không tạo index để che một lỗi dữ liệu hoặc datatype mismatch.

## 18. PL/SQL và conversion errors

PL/SQL cũng có thể phát sinh các lỗi này khi gán biến hoặc gọi function.

~~~sql
DECLARE
    v_amount NUMBER;
BEGIN
    v_amount := '12A.50';
END;
/
~~~

Gán VARCHAR2 sang NUMBER cần implicit conversion; chuỗi không hợp lệ có thể gây ORA-01722.

Tốt hơn:

~~~sql
DECLARE
    v_amount NUMBER;
BEGIN
    v_amount := TO_NUMBER(
        '1250.50',
        '9999990D99',
        'NLS_NUMERIC_CHARACTERS = ''.,'''
    );
END;
/
~~~

Bắt exception có thể giúp ghi nhận lỗi:

~~~sql
BEGIN
    -- phép chuyển đổi hoặc DML
    NULL;
EXCEPTION
    WHEN INVALID_NUMBER THEN
        -- ghi log/quarantine theo transaction policy
        RAISE;
    WHEN OTHERS THEN
        RAISE;
END;
/
~~~

INVALID_NUMBER là predefined exception trong PL/SQL cho ORA-01722. Các lỗi ngày có thể được xử lý qua SQLCODE/exception tương ứng hoặc WHEN OTHERS có kiểm soát. Không nuốt exception sau khi log nếu transaction phải thất bại.

## 19. Kiểm thử regression cho NLS và conversion

Một bộ test tốt không chỉ chạy trên một NLS session.

### 19.1. Ma trận test số

- Decimal dot/group comma.
- Decimal comma/group dot.
- Giá trị âm/dương.
- Zero và leading zeros.
- Precision/scale biên.
- Null/empty.
- Currency symbol nếu contract cho phép.
- Space ASCII và Unicode.
- Ký tự alphabetic/invalid.
- Exponent notation nếu được hỗ trợ.

### 19.2. Ma trận test ngày

- ISO YYYY-MM-DD.
- DD/MM/YYYY và MM/DD/YYYY.
- Tên tháng theo language được hỗ trợ.
- Leap day.
- Ngày cuối tháng.
- Tháng 13/ngày 32.
- Có/không time component.
- Fractional seconds.
- Timezone offset/region.
- DST boundary.
- Null/empty và whitespace.

### 19.3. Chạy với nhiều session NLS

Trong test database, tạo session với các giá trị NLS khác nhau và chạy cùng test case. SQL có explicit format/NLS hoặc bind đúng type phải cho kết quả xác định, không phụ thuộc session default.

### 19.4. Test connection pool

Mượn connection, đổi NLS, trả connection rồi mượn lại. Kiểm tra session state đã được reset theo chính sách. Điều này phát hiện lỗi chỉ xảy ra khi request trước thay đổi ALTER SESSION.

### 19.5. Test optimizer plan

Với dữ liệu có cả giá trị hợp lệ và không hợp lệ:
- Gather stats.
- Chạy query với plan khác nhau nếu có thể.
- Kiểm tra không phụ thuộc thứ tự predicate.
- Thử bind value và datatype khác nhau.
- Xác nhận không có implicit conversion ngoài dự kiến.

## 20. Checklist xử lý sự cố

- [ ] Ghi nguyên văn ORA-01722/01843/01861 và stack.
- [ ] Xác định SQL_ID, module, action và request/batch ID.
- [ ] Xác định column/literal/bind datatype ở hai phía.
- [ ] Xác định conversion tường minh hay ngầm định.
- [ ] Lấy NLS_SESSION_PARAMETERS từ connection lỗi.
- [ ] Giữ raw input và xác định source locale/format.
- [ ] Tìm các giá trị không parse được.
- [ ] Kiểm tra Unicode, whitespace và separator.
- [ ] Kiểm tra date language, format model, timezone.
- [ ] Kiểm tra JOIN, UNION, NVL/CASE và dynamic SQL.
- [ ] Kiểm tra bind datatype trong JDBC.
- [ ] Kiểm tra execution plan và implicit conversion.
- [ ] Sửa tại source contract, staging, SQL hoặc bind boundary.
- [ ] Không thay NLS toàn database khi chưa đánh giá tác động.
- [ ] Không thay dữ liệu lỗi thành 0/NULL một cách âm thầm.
- [ ] Kiểm thử trên nhiều NLS session và pool connection.
- [ ] Đối soát dữ liệu sau remediation.
- [ ] Thêm monitoring/quarantine để ngăn lỗi tái diễn.

## 21. Bài tập tự luyện

1. Phân biệt explicit conversion và implicit conversion.
2. Giải thích nguyên nhân ORA-01722.
3. Nêu các trường hợp có thể phát sinh ORA-01843.
4. Giải thích ORA-01861 bằng ví dụ format mismatch.
5. Vì sao cùng SQL chạy ở SQL Developer nhưng lỗi trong ứng dụng?
6. NLS_NUMERIC_CHARACTERS có hai ký tự theo ý nghĩa nào?
7. Parse 1,234.56 bằng TO_NUMBER với format/NLS rõ ràng.
8. Parse 1.234,56 theo locale decimal comma.
9. Vì sao không thể tự động thay mọi dấu phẩy bằng dấu chấm?
10. NLS_DATE_LANGUAGE ảnh hưởng tên tháng thế nào?
11. Phân biệt NLS_DATE_FORMAT và NLS_DATE_LANGUAGE.
12. Vì sao TO_DATE(date_column, ...) là pattern nguy hiểm?
13. Viết ANSI DATE literal cho ngày 14-11-2026.
14. Viết điều kiện lấy toàn bộ ngày mà không dùng TRUNC trên cột.
15. Phân biệt DATE, TIMESTAMP và TIMESTAMP WITH TIME ZONE.
16. Nêu vai trò VALIDATE_CONVERSION.
17. VALIDATE_CONVERSION xử lý NULL thế nào?
18. Viết truy vấn tìm dòng amount_text không thể chuyển thành NUMBER.
19. Giải thích DEFAULT NULL ON CONVERSION ERROR có thể che giấu điều gì?
20. Vì sao không dựa vào thứ tự predicate trong WHERE?
21. Viết CASE expression kiểm soát TO_NUMBER.
22. DUMP và ASCIISTR giúp tìm ký tự bất thường thế nào?
23. Phân biệt NLS_LANG với NLS_SESSION_PARAMETERS trong JDBC Thin.
24. Vì sao connection pool có thể làm NLS session state rò rỉ giữa request?
25. Viết JDBC PreparedStatement bind NUMBER bằng BigDecimal.
26. Viết JDBC bind timestamp thay vì gửi date string.
27. Tại sao PreparedStatement không tự sửa dữ liệu đầu vào sai?
28. Phân tích ảnh hưởng của implicit conversion lên index và execution plan.
29. Thiết kế staging/quarantine cho feed có số và ngày theo nhiều locale.
30. Lập test matrix cho ORA-01722, ORA-01843 và ORA-01861 trên nhiều JDK/JDBC/NLS session.

**ORA-01722, ORA-01843 và ORA-01861 thường bắt nguồn từ việc Oracle phải diễn giải text theo kiểu dữ liệu hoặc NLS không khớp với dữ liệu nguồn.** Hãy kiểm tra datatype, SQL expression, bind type và NLS session trên đúng connection; giữ raw input, validate theo format contract và quarantine dữ liệu sai. Dùng TO_NUMBER/TO_DATE/TO_TIMESTAMP với format cùng NLS tường minh khi parse text, dùng bind NUMBER/DATE/TIMESTAMP cho giá trị có kiểu, và tránh phụ thuộc vào NLS mặc định hoặc thứ tự predicate.

